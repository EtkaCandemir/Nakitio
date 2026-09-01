"""
Nakitio Prototip Sunucusu

Bu SEVK EDİLECEK UYGULAMA DEĞİLDİR. Amacı, `engine/` içindeki gerçek
motoru bir arayüzün arkasına koyup akışları doğrulamaktır: triyaj
yapıldığında skor gerçekten değişir, ekstre yüklendiğinde işlemler
gerçekten normalizasyondan geçer.

Sahte veri yoktur. Her sayı `engine/` tarafından hesaplanır.

Bağımlılık yok — yalnızca Python standart kütüphanesi.

Çalıştırma:
    python3 app/server.py          # http://localhost:8765
"""

from __future__ import annotations

import copy
import json
import os
import sys
import traceback
from datetime import date, datetime, timedelta
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any, Dict, Optional
from urllib.parse import parse_qs, urlparse

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, os.path.join(ROOT, "engine"))

from behavior_infer import estimate_behavior                     # noqa: E402
from coach_guard import render_fallback, verify_response          # noqa: E402
from coach_tools import (                                         # noqa: E402
    build_context, call_tool,
)
from data_model import (                                          # noqa: E402
    CATEGORIES, DEFAULT_CATEGORY, BehaviorTag, RawData, Transaction, TxnKind,
)
from normalize import (active_windows, build_features, windows,          # noqa: E402
                       _merchant_key)
import screen_data as SD                                          # noqa: E402
from statement_ingest import (                                    # noqa: E402
    effective_as_of, import_statement, parse_statement, statement_coverage,
)

PORT = int(os.environ.get("NAKITIO_PORT", "8765"))
TODAY = SD.DEMO_TODAY


# ─────────────────────────────────────────────────────────────────────────────
# Oturum durumu
# ─────────────────────────────────────────────────────────────────────────────

class Session:
    """Tek kullanıcılı prototip oturumu. Bellekte tutulur."""

    def __init__(self, state: str = "olgun"):
        self.load(state)

    def load(self, state: str) -> None:
        from fixture_didem import AS_OF, build_raw
        self.state = state
        self.as_of = AS_OF
        self.periods: list = []
        self.log: list = []

        if state == "gun0":
            self.raw = RawData(
                user_id="didem",
                accounts=copy.deepcopy(build_raw().accounts),
                accounts_declared=4,
                onboarding={"zorluk": "nereye_gidiyor", "ay_sonu": "bazen",
                            "takip": "bazen", "borc_durumu": "yonetilebilir",
                            "birikim_6ay": "ara_sira"},
            )
            for a in self.raw.accounts:
                a.balance = 0.0
                a.is_linked = False
            self.coverage = 0.0
            return

        raw = build_raw()
        for a in raw.accounts:
            a.is_linked = False          # ekstre modeli: bağlı hesap yok
        if state == "ilk_ekstre":
            cutoff = AS_OF - timedelta(days=30)
            raw.transactions = [t for t in raw.transactions
                                if t.ts.date() >= cutoff]
            raw.debt_principal_history = raw.debt_principal_history[-1:]
            self.coverage = 1 / 6
        else:
            self.coverage = 5 / 6
        self.raw = raw

    # ── Türetme ────────────────────────────────────────────────────────
    def compute(self):
        import dataclasses
        if not self.raw.transactions:
            from score_engine import Features
            f = Features(
                user_id="didem", days_of_data=0,
                accounts_declared=4, accounts_linked=0, categorized_ratio=0.0,
                data_source="statement", statement_coverage=0.0,
                manual_entry=True, onboarding=self.raw.onboarding,
            )
            return f, None
        f, led = build_features(copy.deepcopy(self.raw), self.as_of)
        f = dataclasses.replace(f, data_source="statement", accounts_linked=0,
                                statement_coverage=self.coverage)
        return f, led

    def bundle(self) -> Dict[str, Any]:
        f, led = self.compute()
        b = SD._bundle(f, led, TODAY)
        b["durum"] = self.state
        b["devam_eden_islemler"] = self._ongoing()
        b["log"] = self.log[-8:]
        b["etiket_sayisi"] = len(self.raw.behavior_tags)
        return b

    def _ongoing(self) -> Dict[str, Any]:
        """Devam eden dönem — kapanmamış, yalnızca elle eklenenler.

        Bu işlemler skoru ETKİLEMEZ ve etkilememelidir: dönem kapanmadı,
        ekstre gelmedi. Ana sayfanın iki bölgeli tasarımının sebebi bu.
        """
        items = []
        for t in self.raw.transactions:
            if t.ts.date() <= self.as_of or t.kind == TxnKind.INCOME:
                continue
            cat = CATEGORIES.get(t.category or DEFAULT_CATEGORY,
                                 CATEGORIES[DEFAULT_CATEGORY])
            items.append({
                "id": t.id, "tarih": t.ts.date().isoformat(),
                "aciklama": t.merchant_raw or t.description_raw,
                "kategori": cat.label, "tutar": round(abs(t.try_amount)),
                "tutar_str": SD.tl(abs(t.try_amount)),
            })
        items.sort(key=lambda x: x["tarih"], reverse=True)
        return {"islemler": items, "toplam": SD.tl(sum(i["tutar"] for i in items)),
                "adet": len(items)}

    # ── Eylemler ───────────────────────────────────────────────────────
    def triage(self, txn_id: str, planned: bool, emotion: Optional[str]) -> None:
        self.raw.behavior_tags = [t for t in self.raw.behavior_tags
                                  if t.txn_id != txn_id]
        self.raw.behavior_tags.append(
            BehaviorTag(txn_id=txn_id, planned=planned, emotion=emotion))
        self.log.append(f"Triyaj: {'planlıydı' if planned else 'plansızdı'}"
                        + (f" · {emotion}" if emotion else ""))

    def kategori_ata(self, merchant_id: str, kategori: str) -> None:
        """İŞYERİ hafızasına yaz — o işyerinin TÜM işlemlerine yayılır.

        İmpuls triyajından farkı burada görünür: `triage()` tek bir
        `txn_id` etiketler, bu ise `merchant_id` üzerinden kalıcı bir
        kural koyar. Bir cevap, o işyerinin geçmiş ve gelecek bütün
        harcamalarını düzeltir — bu yüzden soru başına bilgi kazancı
        çok daha yüksektir.
        """
        if not merchant_id:
            raise ValueError("merchant_id boş olamaz")
        if kategori not in CATEGORIES:
            raise ValueError(f"bilinmeyen kategori: {kategori}")
        self.raw.category_overrides[merchant_id] = kategori

        # DİKKAT: `t.merchant_id` burada OKUNAMAZ. `compute()` normalize'ı
        # bilerek `deepcopy` üzerinde çalıştırır (mutasyonlar oturum
        # verisine sızmasın diye), dolayısıyla `self.raw.transactions`
        # üzerindeki merchant_id hep None kalır. Kanonik anahtarı aynı
        # fonksiyonla yeniden türetiyoruz — `_merchant_key` marka
        # aramasını da içerdiği için categorize ile aynı sonucu verir.
        etkilenen = sum(1 for t in self.raw.transactions
                        if _merchant_key(t.merchant_raw or t.description_raw)
                        == merchant_id)
        self.log.append(f"Kategori: {merchant_id} → "
                        f"{CATEGORIES[kategori].label} ({etkilenen} işlem)")

    def add_txn(self, amount: float, category: str, planned: Optional[bool],
                emotion: Optional[str], desc: str) -> None:
        d = TODAY
        tid = f"live_{len(self.raw.transactions):04d}"
        t = Transaction(
            id=tid, account_id=self.raw.accounts[0].id,
            ts=datetime(d.year, d.month, d.day, datetime.now().hour or 12, 0),
            amount=-abs(amount), description_raw=desc or "Elle eklendi",
            merchant_raw=desc or "Elle eklendi",
        )
        t.category = category
        t.kind = TxnKind.PURCHASE
        self.raw.transactions.append(t)
        if planned is not None or emotion:
            self.raw.behavior_tags.append(
                BehaviorTag(txn_id=tid, planned=planned, emotion=emotion))
        self.log.append(f"İşlem eklendi: {SD.tl(abs(amount))} · "
                        f"{CATEGORIES.get(category, CATEGORIES[DEFAULT_CATEGORY]).label}")

    def upload(self, text: str, profile: str, account_id: str) -> Dict[str, Any]:
        parsed = parse_statement(text, profile)
        res = import_statement(self.raw, parsed, account_id)
        self.coverage = min(1.0, self.coverage + 1 / 6)

        # HESAPLAMA TARİHİ EKSTREYLE İLERLER.
        #
        # `effective_as_of` kuralı (veri katmanı §5) prototipe bağlanmamıştı:
        # Ağustos tarihli bir ekstre yüklenip as_of 31 Temmuz'da kalınca
        # yeni işlemler pencerenin DIŞINA düşüyor, gelir hiç sayılmıyor ve
        # skor yükleme sonrası DÜŞÜYORDU. Ekstre yüklemenin ödüllendirilmesi
        # gereken yerde cezalandırıyordu.
        if res.period:
            self.periods.append(res.period)
        yeni = effective_as_of(self.periods, TODAY)
        if yeni > self.as_of:
            self.as_of = yeni
        self.log.append(f"Ekstre: {res.added} yeni, {res.duplicates} mükerrer")
        return {
            "eklenen": res.added, "mukerrer": res.duplicates,
            "toplam_satir": res.rows_total,
            "donem": ([res.period[0].isoformat(), res.period[1].isoformat()]
                      if res.period else None),
            "borc_anlik": ([res.debt_snapshot[0].isoformat(), res.debt_snapshot[1]]
                           if res.debt_snapshot else None),
            "uyarilar": res.warnings,
        }


SESSION = Session("olgun")


# ─────────────────────────────────────────────────────────────────────────────
# Koç
# ─────────────────────────────────────────────────────────────────────────────

#: (soru, çağrılacak araçlar, projeksiyon mu)
#: `projecting` yalnızca gelecek projeksiyonu içeren yanıtlarda True olur;
#: aksi hâlde guard her yanıtta çekince dili arar ve reddeder.
QUESTIONS = {
    "durum": ("Bu ay durumum nasıl?",
              ["get_score", "get_score_breakdown"], True),
    "tasarruf": ("Tasarrufumu nasıl artırırım?",
                 ["get_score", "build_action_plan"], True),
    "risk": ("Nelere dikkat etmeliyim?", ["get_score", "get_risks"], True),
    "kategori": ("Harcamalarım nerede arttı?",
                 ["get_score", "get_top_categories"], True),
    "yatirim": ("Paramı nereye yatırmalıyım?", ["get_score"], False),
}


def coach_turn(key: str) -> Dict[str, Any]:
    """Prototipte LLM yok; yanıt deterministik şablondan gelir.

    Gerçek üründe akış aynıdır — tek fark, şablonun yerini LLM alır ve
    çıktısı yine `verify_response`'tan geçer. Burada mimarinin kendisi
    gösteriliyor: araçlar çalışır, sayılar deftere yazılır, yanıt
    doğrulanır.
    """
    f, led = SESSION.compute()
    ctx = build_context(f, ledger=led, as_of=SESSION.as_of)
    soru, tools, projecting = QUESTIONS.get(key, QUESTIONS["durum"])
    outs = {name: call_tool(ctx, name) for name in tools}

    if key == "yatirim":
        # Ondalık ayracı YALNIZCA sayıya uygulanır. İlk sürümde
        # `.replace(".", ",")` tüm cümleye uygulanıyor ve cümle
        # sonlarındaki noktaları da virgüle çeviriyordu.
        ay = f"{round(f.ef_months, 1)}".replace(".", ",")
        text = ("Yatırım tavsiyesi veremem — lisanslı bir finansal danışman "
                "değilim. Ama birikimini önce acil durum fonuna ayırmayı "
                f"düşünebilirsin; güvence süren şu an {ay} ay.")
        ctx.numbers.add(round(f.ef_months, 1), "months", "güvence süresi", "manual")
    else:
        text = render_fallback(ctx)

    rep = verify_response(ctx, text, projecting=projecting)
    return {
        "soru": soru, "yanit": text,
        "araclar": list(outs.keys()),
        "dogrulama": {
            "gecti": rep.ok, "ozet": rep.summary(),
            "sayi_adedi": rep.checked_numbers,
            "ihlaller": [{"kod": v.code, "seviye": v.severity, "detay": v.detail}
                         for v in rep.violations],
        },
        "defter": ctx.numbers.describe()[:14],
        "not": "Prototipte yanıt deterministik şablondan geliyor. Gerçek "
               "üründe LLM anlatır, aynı doğrulayıcıdan geçer.",
    }


# ─────────────────────────────────────────────────────────────────────────────
# HTTP
# ─────────────────────────────────────────────────────────────────────────────

SAMPLES = {
    "kart": ("tr_generic_card_pdf", "cc", """\
XYZ BANKASI KREDİ KARTI EKSTRESİ
Kart No: 5218 **** **** 4471
Dönem Başlangıcı: 19.07.2026
Ekstre Kesim Tarihi: 18.08.2026
Son Ödeme Tarihi: 28.08.2026
Dönem Borcu: 7.940,00
Asgari Ödeme Tutarı: 1.588,00

İşlem Tarihi  Açıklama                              Tutar
20.07.2026    STARBUCKS KANYON                      212,00
23.07.2026    MIGROS TIC A.S IST                    1.480,50
27.07.2026    YEMEKSEPETI ONLINE                    389,00
02.08.2026    ZARA AKMERKEZ                         2.150,00
05.08.2026    TEKNOSA TAKSIT 1/8                    1.100,00
07.08.2026    ODEME - TESEKKURLER                   8.100,00
"""),
    "hesap": ("tr_generic_account_csv", "ch", """\
Tarih;Açıklama;Tutar
05.08.2026;MAAS ODEMESI ACME TEKNOLOJI;24.000,00
06.08.2026;IGDAS DOGALGAZ;-980,00
07.08.2026;ISTANBULKART DOLUM;-450,00
08.08.2026;KENDI HESABIMA VIRMAN;-3.000,00
"""),
}


class Handler(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"

    def log_message(self, fmt, *args):
        pass

    # ── yardımcılar ────────────────────────────────────────────────────
    def _send(self, obj: Any, code: int = 200) -> None:
        body = json.dumps(obj, ensure_ascii=False).encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def _file(self, rel: str) -> None:
        path = os.path.join(HERE, "web", rel)
        if not os.path.isfile(path):
            self.send_error(404)
            return
        ctype = {".html": "text/html; charset=utf-8",
                 ".css": "text/css; charset=utf-8",
                 ".js": "application/javascript; charset=utf-8"}.get(
            os.path.splitext(path)[1], "application/octet-stream")
        with open(path, "rb") as fh:
            body = fh.read()
        self.send_response(200)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def _body(self) -> Dict[str, Any]:
        n = int(self.headers.get("Content-Length") or 0)
        if not n:
            return {}
        return json.loads(self.rfile.read(n).decode("utf-8"))

    # ── yönlendirme ────────────────────────────────────────────────────
    def do_GET(self):
        u = urlparse(self.path)
        q = parse_qs(u.query)
        try:
            if u.path in ("/", "/index.html"):
                return self._file("index.html")
            if u.path.startswith("/web/"):
                return self._file(u.path[5:])
            if u.path in ("/app.js", "/style.css"):
                return self._file(u.path[1:])
            if u.path == "/api/bundle":
                return self._send(SESSION.bundle())
            if u.path == "/api/state":
                SESSION.load((q.get("s") or ["olgun"])[0])
                return self._send(SESSION.bundle())
            if u.path == "/api/samples":
                return self._send({k: {"profil": v[0], "hesap": v[1], "metin": v[2]}
                                   for k, v in SAMPLES.items()})
            if u.path == "/api/coach":
                return self._send(coach_turn((q.get("q") or ["durum"])[0]))
            self.send_error(404)
        except (ValueError, KeyError) as e:
            # İSTEMCİ hatası: geçersiz kategori, eksik alan. 500 dönmek
            # yanıltıcıdır — sunucu bozulmadı, istek geçersizdi. Arayüz
            # bu ayrımı gösterip kullanıcıya anlamlı mesaj verebilmeli.
            self._send({"hata": str(e), "tur": "gecersiz_istek"}, 400)
        except Exception:
            traceback.print_exc()
            self._send({"hata": traceback.format_exc(limit=3)}, 500)

    def do_POST(self):
        u = urlparse(self.path)
        try:
            b = self._body()
            if u.path == "/api/kategori":
                # DİKKAT: `_body()` yukarıda BİR KEZ okundu. İkinci çağrı
                # `rfile.read(n)` ile soketten n bayt daha bekler ve asla
                # gelmez — istek sonsuza kadar asılı kalır. Gövde tek sefer
                # okunur, aşağıdaki tüm yollar aynı `b`'yi kullanır.
                SESSION.kategori_ata(str(b.get("merchant_id") or ""),
                                     str(b.get("kategori") or ""))
                return self._send(SESSION.bundle())
            if u.path == "/api/triage":
                SESSION.triage(b["txn_id"], bool(b["planned"]), b.get("emotion"))
                return self._send(SESSION.bundle())
            if u.path == "/api/txn":
                SESSION.add_txn(float(b["amount"]), b["category"],
                                b.get("planned"), b.get("emotion"),
                                b.get("desc", ""))
                return self._send(SESSION.bundle())
            if u.path == "/api/upload":
                key = b.get("sample")
                if key in SAMPLES:
                    profile, acct, text = SAMPLES[key]
                else:
                    profile, acct, text = (b.get("profile", "tr_generic_account_csv"),
                                           b.get("account", "ch"), b.get("text", ""))
                res = SESSION.upload(text, profile, acct)
                return self._send({"sonuc": res, "bundle": SESSION.bundle()})
            self.send_error(404)
        except (ValueError, KeyError) as e:
            # İSTEMCİ hatası: geçersiz kategori, eksik alan. 500 dönmek
            # yanıltıcıdır — sunucu bozulmadı, istek geçersizdi.
            self._send({"hata": str(e), "tur": "gecersiz_istek"}, 400)
        except Exception:
            traceback.print_exc()
            self._send({"hata": traceback.format_exc(limit=3)}, 500)


def main() -> None:
    srv = ThreadingHTTPServer(("127.0.0.1", PORT), Handler)
    print(f"Nakitio prototip → http://localhost:{PORT}")
    print(f"  motor: engine/  ·  demo bugün: {TODAY}  ·  son ekstre: {SESSION.as_of}")
    srv.serve_forever()


if __name__ == "__main__":
    main()
