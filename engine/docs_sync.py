"""
Nakitio — Doküman Senkronizasyonu

Dokümanlardaki KODDAN TÜRETİLEBİLEN blokları üretir ve doğrular.

Neden: `Docs/FORMULAS.md` §8'deki 96 parametrelik tablo `params.py`'nin
kopyasıdır. El ile senkron tutulan bir kopya er ya da geç bozulur —
ve bozulduğunda kimse fark etmez, çünkü doküman testten geçmez.

Bu araç iki mod çalışır:

    python3 engine/docs_sync.py            # blokları YENİDEN ÜRET
    python3 engine/docs_sync.py --check    # yalnızca DOĞRULA (CI için)

`--check` modu hiçbir dosyaya yazmaz; sapma varsa çıkış kodu 1 döner.

Üretilen bloklar `<!-- OTOMATIK:ad -->` ... `<!-- /OTOMATIK:ad -->`
işaretleri arasındadır. İşaretlerin DIŞINDAKİ metin elle yazılmıştır ve
bu araç ona dokunmaz.
"""

from __future__ import annotations

import os
import re
import subprocess
import sys
from typing import Callable, Dict, List, Tuple

HERE = os.path.dirname(os.path.abspath(__file__))
KOK = os.path.dirname(HERE)
sys.path.insert(0, HERE)


def _onbellegi_temizle() -> None:
    """`__pycache__`'i sil — BAYAT .pyc RİSKİ.

    Python, derlenmiş modülün geçerliliğini kaynak dosyanın (mtime, boyut)
    çiftiyle kontrol eder ve mtime'ı .pyc başlığında **saniye** çözünürlüklü
    tutar. Bir parametreyi `0.14` → `0.10` yapmak boyutu değiştirmez; aynı
    saniye içinde yazılırsa Python önbelleği GEÇERLİ sayar ve eski değeri
    import eder.

    Bu araç için ölümcül: dokümanı koda göre üretiyoruz, kod bayatsa
    doküman yanlış üretilir ve `--check` "senkron" der. Bizzat yaşandı —
    dosyada 0,10 yazarken 0,14 import ediliyordu.
    """
    import shutil
    yol = os.path.join(HERE, "__pycache__")
    if os.path.isdir(yol):
        shutil.rmtree(yol, ignore_errors=True)


_onbellegi_temizle()
sys.dont_write_bytecode = True


def _yol(*p: str) -> str:
    return os.path.join(KOK, *p)


# ─────────────────────────────────────────────────────────────────────────────
# Blok üreticileri
# ─────────────────────────────────────────────────────────────────────────────

def _sayi(v: float) -> str:
    """Türkçe biçim: ondalık virgül, gereksiz sıfır yok."""
    s = f"{v:g}"
    return s.replace("-", "−").replace(".", ",")


def _ondalik(v: float, basamak: int) -> str:
    """Türkçe biçim, SABİT ondalık — sayısal sütunlar için.

    `_sayi` sondaki sıfırı kırpar (`0,60` → `0,6`, `58,0` → `58`); bir
    parametre listesinde bu okunaklıdır ama hizalanmış bir ölçüm
    tablosunda sütunu bozar ve değerler farklı hassasiyetteymiş gibi
    görünür.
    """
    return f"{v:.{basamak}f}".replace("-", "−").replace(".", ",")


def _delta(n: int) -> str:
    """İşaretli tam sayı, Türkçe eksi işaretiyle."""
    return f"{n:+d}".replace("-", "−")


def blok_params_tablosu() -> str:
    """96 parametrenin tam tablosu, gruplara ayrılmış."""
    from params import M, P

    gruplar: Dict[str, List[str]] = {}
    for k in P:
        gruplar.setdefault(M[k].group, []).append(k)

    sira = ["Bileşen", "P1", "P2", "P2 ceza", "P3", "P4", "P5", "P6",
            "Güven", "Yumuşatma", "Aşama", "Öncül", "Çıkarım"]
    bilinmeyen = [g for g in gruplar if g not in sira]
    if bilinmeyen:
        sira += sorted(bilinmeyen)

    out = [f"*{len(P)} parametre. `params.py`'den üretildi — elle düzenleme.*", ""]
    for g in sira:
        if g not in gruplar:
            continue
        out.append(f"### {g}")
        out.append("")
        out.append("| Anahtar | Değer | Aralık | Tür | Açıklama |")
        out.append("|---|---|---|---|---|")
        for k in gruplar[g]:
            m = M[k]
            not_ = " ".join(m.note.split()) if m.note else ""
            if len(not_) > 88:
                not_ = not_[:85] + "…"
            aciklama = m.label + (f" — {not_}" if not_ else "")
            out.append(f"| `{k}` | **{_sayi(P[k])}** | "
                       f"{_sayi(m.lo)}–{_sayi(m.hi)} | {m.kind} | {aciklama} |")
        out.append("")
    return "\n".join(out).rstrip()


#: (modül, sabit adı, açıklama) — dokümana girecek normalizasyon sabitleri
NORM_SABITLERI: List[Tuple[str, str, str]] = [
    ("normalize", "PIPELINE_VERSION", "Veri hattı sürümü"),
    ("normalize", "CATEGORY_VERSION", "Kategorizasyon sürümü — ayrı takip"),
    ("normalize", "WINDOW_DAYS", "Kayan pencere uzunluğu (gün)"),
    ("normalize", "N_WINDOWS", "Tutulan pencere sayısı"),
    ("normalize", "TRANSFER_MATCH_DAYS", "İç transfer eşleştirme penceresi (gün)"),
    ("normalize", "TRANSFER_TOLERANCE_ABS", "Transfer tutar toleransı (TL)"),
    ("normalize", "TRANSFER_TOLERANCE_PCT", "Transfer kur/komisyon payı"),
    ("normalize", "AMORTIZE_MIN_PERIOD_DAYS", "Amortisman eşiği (gün)"),
    ("normalize", "RECURRING_AMOUNT_TOL", "Yinelenen ödeme tutar toleransı"),
    ("normalize", "LIMIT_TOLERANCE", "Kategori limiti ihlal toleransı"),
    ("normalize", "CATVOL_MIN_PRESENT", "Oynaklık: pencere varlık oranı"),
    ("normalize", "CATVOL_MIN_SHARE", "Oynaklık: minimum harcama payı"),
    ("normalize", "REFUND_WINDOW_DAYS", "İade eşleştirme penceresi (gün)"),
    ("normalize", "OUTLIER_INCOME_MULTIPLE", "Aykırı değer eşiği (gelir katı)"),
    ("behavior_infer", "RECURRING_MIN_SEEN", "Yinelenen sayılmak için görülme"),
    ("behavior_infer", "RECURRING_AMOUNT_TOL", "Yinelenen tutar toleransı"),
    ("statement_ingest", "REFUND_WINDOW_DAYS", "Ekstre iade penceresi (gün)"),
    ("statement_ingest", "OUTLIER_INCOME_MULTIPLE", "Ekstre aykırı değer eşiği"),
    ("screen_data", "GUVENCE_ILERI_AY", "Rozet hedefi — skor DIŞI (ay)"),
    ("coach_guard", "STRUCTURAL_MAX", "Yapısal sayılan azami tam sayı"),
    ("coach_guard", "REFUSAL_WINDOW", "Reddetme eki arama penceresi (karakter)"),
    ("coach_tools", "COACH_VERSION", "Koç katmanı sürümü"),
]


def blok_norm_sabitleri() -> str:
    """`params.py` dışındaki modül sabitleri."""
    import importlib

    out = ["*Modül sabitleri — `params.py` dışında. Koddan üretildi.*", "",
           "| Sabit | Değer | Modül | Anlamı |", "|---|---|---|---|"]
    for mod_ad, sabit, aciklama in NORM_SABITLERI:
        mod = importlib.import_module(mod_ad)
        v = getattr(mod, sabit, None)
        if v is None:
            out.append(f"| `{sabit}` | **YOK** | `{mod_ad}` | ⚠ sabit bulunamadı |")
            continue
        gosterim = _sayi(v) if isinstance(v, (int, float)) and not isinstance(v, bool) else str(v)
        out.append(f"| `{sabit}` | **{gosterim}** | `{mod_ad}` | {aciklama} |")

    from normalize import NIGHT_HOURS
    saatler = sorted(NIGHT_HOURS)
    out.append(f"| `NIGHT_HOURS` | **{min(h for h in saatler if h >= 12)}–"
               f"{max(h for h in saatler if h < 12) + 1:02d}** | `normalize` | "
               f"Gece tanımı (saat aralığı) |")
    return "\n".join(out)


def blok_davranis_katsayilari() -> str:
    """Lojistik çıkarım modelinin katsayıları."""
    from behavior_infer import COMFORT_CATEGORIES, W

    etiket = {
        "b0": "kesişim (kalibrasyonla kayar)",
        "recurring": "yinelenen ödeme — en güçlü PLANLI sinyali",
        "novel": "ilk kez görülen merchant",
        "category": "(kategori ön olasılığı − 0,5) ile çarpılır",
        "amount": "kategori medyanından sapma",
        "cluster": "aynı gün isteğe bağlı işlem kümesi",
        "installment": "taksitle alınmış",
        "payday": "maaş gününe yakınlık (0–3 gün)",
        "weekend": "hafta sonu",
        "refunded": "sonradan iade edilmiş",
        "night": "gece harcaması (saat varsa)",
    }
    out = ["*`behavior_infer.W`'den üretildi.*", "",
           "| Katsayı | Değer | Anlamı |", "|---|---|---|"]
    for k, v in W.items():
        out.append(f"| `{k}` | **{_sayi(v)}** | {etiket.get(k, '')} |")
    out.append("")
    out.append("```")
    out.append("p = 1 / (1 + e^(−z))")
    out.append("```")
    out.append("")
    out.append("**Rahatlama kategorileri** (duygu modeli yalnızca bunlarda çalışır): "
               + ", ".join(f"`{c}`" for c in sorted(COMFORT_CATEGORIES)))
    return "\n".join(out)


def blok_kategori_tablosu() -> str:
    """25 kategori: zorunluluk ağırlığı + plansızlık ön olasılığı."""
    from behavior_infer import CATEGORY_IMPULSE_PRIOR
    from data_model import CATEGORIES

    out = ["*`data_model.CATEGORIES` ve `behavior_infer.CATEGORY_IMPULSE_PRIOR`'dan üretildi.*",
           "",
           "| Kategori | `essential_weight` | Plansızlık ön olasılığı | TÜFE grubu |",
           "|---|---|---|---|"]
    # None ağırlıklılar (pazaryeri, diğer) en sona — sıralama anahtarında
    # -1 kullanılır ki 0,00 ağırlıklı gerçek kategorilerin altına düşsünler.
    for c in sorted(CATEGORIES.values(),
                    key=lambda x: (-(x.essential_weight if x.essential_weight
                                     is not None else -1.0), x.key)):
        prior = CATEGORY_IMPULSE_PRIOR.get(c.key)
        p = _sayi(prior) if prior is not None else "—"
        ew = "**bilinmiyor**" if c.essential_weight is None else f"**{_sayi(c.essential_weight)}**"
        out.append(f"| {c.label} (`{c.key}`) | {ew} | "
                   f"{p} | `{c.cpi_group}` |")
    out.append("")
    out.append("```")
    out.append("e_essential = Σ (tutar_i × essential_weight[kategori_i])")
    out.append("")
    out.append("Ağırlığı `bilinmiyor` olanlar bu toplama GİRMEZ; oran, ağırlığı")
    out.append("bilinen harcamadan tahmin edilip toplama genişletilir.")
    out.append("```")
    return "\n".join(out)


def blok_golden_skorlar() -> str:
    """15 golden profilin güncel skorları."""
    from golden_profiles import PROFILES
    from score_engine import compute_score

    out = ["*`golden_profiles.py` çalıştırılarak üretildi.*", "",
           "| Profil | Skor | Band | C | Ne temsil eder |", "|---|---|---|---|---|"]
    for ad, (f, not_, _beklenen) in PROFILES.items():
        r = compute_score(f)
        out.append(f"| `{ad}` | **{r.score}** | {r.band[0]}–{r.band[1]} | "
                   f"{_sayi(round(r.confidence, 2))} | {not_} |")
    return "\n".join(out)


# ── `Docs/skor-modeli-v2.md` blokları ────────────────────────────────────────
# Bu dosya deponun EN ESKİ şartnamesidir ve uzun süre işaretsiz kaldı: elle
# yazılmış tabloları 12 Ağu parametre kararlarının (prior.baz 50→40,
# prior.min 40→28, p3.guvence.tam_ay 6→3) gerisinde kaldı ve `--check` bunu
# göremedi — çünkü işaretlerin dışındaki metne bu araç dokunmaz. Depo aynı
# commit'te didem için hem 73 (üretilen blok) hem 74 (elle yazılan tablo)
# taşıyordu. Aşağıdaki üreticiler o sınıfı kalıcı olarak kapatır.
#
# Hepsi `golden_profiles.veri_*()` saf fonksiyonlarını çağırır; hesap orada
# TEK yerde durur. Buraya kopyalanırsa aynı sapma bu kez kod içinde doğar.

def blok_sm_golden_senaryo() -> str:
    """§10 — 10 senaryo profili. Kapsam profilleri `TESTING.md`'de."""
    from golden_profiles import senaryo_profilleri
    from score_engine import compute_score

    out = ["*`golden_profiles.py` çalıştırılarak üretildi. Kapsam profilleri "
           "dahil tam liste: `Docs/TESTING.md` §6.*", "",
           "| Profil | Skor | Band | Ham | Öncül | C | Seviye |",
           "|---|---|---|---|---|---|---|"]
    for ad, (f, not_, _beklenen) in senaryo_profilleri().items():
        r = compute_score(f)
        out.append(f"| **{ad}** — {not_} | **{r.score}** | {r.band[0]}–{r.band[1]} | "
                   f"{_ondalik(r.raw_score, 1)} | {_ondalik(r.prior_score, 1)} | "
                   f"{_ondalik(r.confidence, 2)} | {r.level} |")
    return "\n".join(out)


def blok_sm_didem_kirilim() -> str:
    """§10 — mockup kullanıcısının tam bileşen kırılımı."""
    from golden_profiles import PROFILES
    from score_engine import compute_score

    f, _, _ = PROFILES["didem"]
    return ("*`compute_score(PROFILES[\"didem\"]).explain()` çıktısı — motor "
            "dökümü olduğu için ondalık ayracı noktadır.*\n\n"
            "```\n" + compute_score(f).explain().rstrip() + "\n```")


def blok_sm_sureklilik() -> str:
    """§5 — gün-30 uçurumunun kalktığının kanıtı."""
    from golden_profiles import veri_sureklilik

    out = ["*`golden_profiles.veri_sureklilik()`'ten üretildi.*", "",
           "| gün | C | ham | öncül | karma | skor | aşama |",
           "|---|---|---|---|---|---|---|"]
    for d, r in veri_sureklilik():
        # Uçurumun iki yanı vurgulanır — iddianın can alıcı noktası orası.
        g = f"**{d}**" if d in (30, 31) else str(d)
        asama = r.stage_label.replace(" Skoru", "")
        out.append(f"| {g} | {_ondalik(r.confidence, 2)} | "
                   f"{_ondalik(r.raw_score, 1)} | {_ondalik(r.prior_score, 1)} | "
                   f"{_ondalik(r.blended_score, 1)} | **{r.score}** | {asama} |")
    return "\n".join(out)


def blok_sm_belirsizlik_bandi() -> str:
    """§7 — bant genişliğinin güvenle daralması."""
    from golden_profiles import PROFILES
    from score_engine import compute_score

    out = ["*`golden_profiles.py`'den üretildi.*", ""]
    for ad in ("can", "didem"):
        f, _, _ = PROFILES[ad]
        r = compute_score(f)
        yari = (r.band[1] - r.band[0]) / 2
        out.append(f"`C = {_ondalik(r.confidence, 2)}` → ±{_sayi(yari)} puan "
                   f"(`{ad}`: **{r.score}**, band `{r.band[0]}–{r.band[1]}`)")
        out.append("")
    return "\n".join(out).rstrip()


def blok_sm_maddi_olay() -> str:
    """§8 — kötü haber hızlı, iyi haber yavaş."""
    from golden_profiles import veri_maddi_olay

    ok, bad, good = veri_maddi_olay()
    return ("*`golden_profiles.veri_maddi_olay()`'dan üretildi.*\n\n"
            "```\n"
            f"Normal ay            : {ok.score}\n"
            f"Gecikmeye düştü      : {bad.score}   "
            f"(Δ {_delta(bad.score - ok.score)})   ← ±8 sınırı bypass edildi\n"
            f"Ani büyük iyileşme   : {good.score}   "
            f"(Δ {_delta(good.score - ok.score)})   ← yukarı yön sınırlı kaldı\n"
            "```\n\n"
            f"Tespit edilen maddi olay: {', '.join(bad.material_events)}.")


def blok_sm_sinir_durumlari() -> str:
    """§11 — sınır durumlarının ÖLÇÜLMÜŞ çıktısı."""
    from golden_profiles import veri_sinir_durumlari

    out = ["*`golden_profiles.veri_sinir_durumlari()`'ndan üretildi. Davranışın "
           "gerekçesi yukarıdaki tabloda; buradaki sayılar ölçümdür.*", "",
           "| Durum | Skor | Band | C | Seviye | Devre dışı |",
           "|---|---|---|---|---|---|"]
    for etiket, r, dis in veri_sinir_durumlari():
        out.append(f"| {etiket} | **{r.score}** | {r.band[0]}–{r.band[1]} | "
                   f"{_ondalik(r.confidence, 2)} | {r.level} | "
                   f"{', '.join(dis) if dis else '—'} |")
    return "\n".join(out)


def blok_sm_simulasyon() -> str:
    """§13 — koçun 'bu planı uygularsan X olur' vaadinin kaynağı."""
    from golden_profiles import veri_simulasyon

    base, adimlar, katki = veri_simulasyon()
    son = adimlar[-1][1] if adimlar else base
    satir = [f"Mevcut durum: {base.score}/100  ({base.level})", ""]
    for etiket, r in adimlar:
        satir.append(f"  {etiket:<42} → {r.score}/100  ({_delta(r.score - base.score)})")
    satir.append("")
    satir.append(f"3 ay sonunda beklenen skor: {son.score} ({son.level}), "
                 f"band {son.band[0]}–{son.band[1]}")

    kat = ["```"]
    for row in katki:
        ok_ = ""
        if row["from"] is not None and row["to"] is not None:
            ok_ = f"   {row['from']} → {row['to']}"
        kat.append(f"  {row['delta']:+6.2f}  {row['label']}{ok_}")
    kat.append("```")

    return ("*`golden_profiles.veri_simulasyon()`'dan üretildi.*\n\n"
            "```\n" + "\n".join(satir) + "\n```\n\n"
            "Katkı ayrıştırma (mevcut → plan sonu) — toplam gösterilen farkı "
            "**tam olarak** kapatır, artık kalemi yuvarlamadır:\n\n"
            + "\n".join(kat))


def blok_test_sayilari() -> str:
    """Test süitlerinin güncel kontrol sayıları."""
    suitler = [
        ("test_invariants.py", "Yapısal kurallar — determinizm, monotonluk, "
                               "süreklilik, anti-gaming, adalet"),
        ("test_normalize.py", "N1–N9 normalizasyon kuralları"),
        ("test_ingest.py", "Ekstre ayrıştırma, tekilleştirme, davranış çıkarımı"),
        ("coach_eval.py", "Koç sayı sadakati, SPK sınırı, ton, akışlar"),
    ]
    out = ["*Süitler çalıştırılarak üretildi.*", "",
           "| Süit | Kontrol | Ne garanti eder |", "|---|---|---|"]
    toplam = 0
    for dosya, aciklama in suitler:
        n = _test_sayisi(dosya)
        toplam += n if isinstance(n, int) else 0
        out.append(f"| `{dosya}` | **{n}** | {aciklama} |")
    out.append(f"| | **{toplam}** | |")
    return "\n".join(out)


def _test_sayisi(dosya: str):
    r = subprocess.run([sys.executable, dosya], cwd=HERE,
                       capture_output=True, text=True)
    son = (r.stdout or "").strip().splitlines()
    if not son:
        return "?"
    m = re.search(r"(\d+)\s*(?:kontrolün|vaka)", son[-1])
    if m:
        n = int(m.group(1))
        # coach_eval "65 vaka + akış testleri" der; akışları da say
        if "vaka" in son[-1]:
            n += len(re.findall(r"\[\s*ok\]\s+t_", r.stdout))
        return n
    return "?"


BLOKLAR: Dict[str, Callable[[], str]] = {
    "params-tablosu": blok_params_tablosu,
    "norm-sabitleri": blok_norm_sabitleri,
    "davranis-katsayilari": blok_davranis_katsayilari,
    "kategori-tablosu": blok_kategori_tablosu,
    "golden-skorlar": blok_golden_skorlar,
    "test-sayilari": blok_test_sayilari,
    # skor-modeli-v2.md — bkz. üreticilerin üstündeki gerekçe
    "sm-sureklilik": blok_sm_sureklilik,
    "sm-belirsizlik-bandi": blok_sm_belirsizlik_bandi,
    "sm-maddi-olay": blok_sm_maddi_olay,
    "sm-golden-senaryo": blok_sm_golden_senaryo,
    "sm-didem-kirilim": blok_sm_didem_kirilim,
    "sm-sinir-durumlari": blok_sm_sinir_durumlari,
    "sm-simulasyon": blok_sm_simulasyon,
}


# ─────────────────────────────────────────────────────────────────────────────
# Blok değiştirme
# ─────────────────────────────────────────────────────────────────────────────

BASLA = "<!-- OTOMATIK:{ad} -->"
BITIR = "<!-- /OTOMATIK:{ad} -->"


def _desen(ad: str) -> re.Pattern:
    # İçerik BOŞ olabilir — işaretler ilk yerleştirildiğinde bitişiktir.
    # `\n.*?\n` yazılırsa boş blok eşleşmez ve araç "işaret yok" der.
    return re.compile(
        re.escape(BASLA.format(ad=ad)) + r"\n(?:.*?\n)??" + re.escape(BITIR.format(ad=ad)),
        re.DOTALL)


def blok_bul(metin: str, ad: str) -> bool:
    return _desen(ad).search(metin) is not None


def blok_yaz(metin: str, ad: str, icerik: str) -> str:
    yeni = f"{BASLA.format(ad=ad)}\n{icerik}\n{BITIR.format(ad=ad)}"
    return _desen(ad).sub(lambda _: yeni, metin)


# ─────────────────────────────────────────────────────────────────────────────
# Ek doğrulamalar — üretilmeyen ama koda bağlı olan iddialar
# ─────────────────────────────────────────────────────────────────────────────

def dogrula_dosya_referanslari() -> List[str]:
    """Dokümanlarda geçen dosya yolları gerçekten var mı."""
    hatalar = []
    desen = re.compile(r"`((?:engine|app|Docs)/[\w\-./]+\.(?:py|md|json|js|css|html))`")
    for md in _dokumanlar():
        for m in desen.finditer(_oku(md)):
            if not os.path.exists(_yol(m.group(1))):
                hatalar.append(f"{os.path.basename(md)}: `{m.group(1)}` yok")
    return hatalar


def dogrula_parametre_adlari() -> List[str]:
    """Dokümanlarda geçen `p1.marj.k` gibi anahtarlar params.py'de var mı."""
    from params import P
    hatalar = []
    desen = re.compile(r"`((?:p[1-6]|c|s|mod|stage|prior|infer)\.[a-z0-9_.]+)`")
    for md in _dokumanlar():
        for m in desen.finditer(_oku(md)):
            k = m.group(1)
            if k not in P:
                hatalar.append(f"{os.path.basename(md)}: `{k}` params.py'de yok")
    return sorted(set(hatalar))


def dogrula_agirlik_toplamlari() -> List[str]:
    """params.check() zaten yapıyor ama açıkça raporla."""
    from params import P
    hatalar = []
    t = sum(P[f"p{i}.weight"] for i in range(1, 7))
    if abs(t - 100) > 1e-9:
        hatalar.append(f"bileşen ağırlıkları {t} (100 olmalı)")
    return hatalar


def _dokumanlar() -> List[str]:
    out = [_yol("CLAUDE.md")]
    d = _yol("Docs")
    out += [os.path.join(d, f) for f in sorted(os.listdir(d)) if f.endswith(".md")]
    return [p for p in out if os.path.exists(p)]


def _oku(p: str) -> str:
    with open(p, encoding="utf-8") as fh:
        return fh.read()


# ─────────────────────────────────────────────────────────────────────────────

def calistir(check_only: bool) -> int:
    print("NAKITIO — DOKÜMAN SENKRONİZASYONU")
    print("=" * 74)

    icerikler = {ad: uretici() for ad, uretici in BLOKLAR.items()}
    bulunan: Dict[str, List[str]] = {ad: [] for ad in BLOKLAR}
    degisen, sapan = [], []

    for md in _dokumanlar():
        metin = _oku(md)
        yeni = metin
        for ad, icerik in icerikler.items():
            if not blok_bul(yeni, ad):
                continue
            bulunan[ad].append(os.path.basename(md))
            yeni = blok_yaz(yeni, ad, icerik)
        if yeni != metin:
            kayit = f"{os.path.basename(md)}"
            (sapan if check_only else degisen).append(kayit)
            if not check_only:
                with open(md, "w", encoding="utf-8") as fh:
                    fh.write(yeni)

    print("\nÜRETİLEN BLOKLAR")
    print("-" * 74)
    yerlesmemis = []
    for ad in BLOKLAR:
        yerler = bulunan[ad]
        if yerler:
            print(f"  ✓ {ad:<24} → {', '.join(yerler)}")
        else:
            yerlesmemis.append(ad)
            print(f"  ⚠ {ad:<24} → hiçbir dokümanda işaret yok")

    print("\nDOĞRULAMALAR")
    print("-" * 74)
    hatalar: List[str] = []
    for ad, fn in (("dosya referansları", dogrula_dosya_referanslari),
                   ("parametre adları", dogrula_parametre_adlari),
                   ("ağırlık toplamları", dogrula_agirlik_toplamlari)):
        h = fn()
        hatalar += h
        print(f"  {'✗' if h else '✓'} {ad}" + (f" — {len(h)} sorun" if h else ""))
        for x in h[:6]:
            print(f"      {x}")

    print("\n" + "=" * 74)
    if check_only:
        if sapan:
            print(f"SAPMA VAR — {len(sapan)} dosya güncel değil: {', '.join(sapan)}")
            print("Düzeltmek için: python3 engine/docs_sync.py")
        if hatalar:
            print(f"{len(hatalar)} doğrulama hatası.")
        if not sapan and not hatalar:
            print("Tüm dokümanlar kodla senkron.")
        return 1 if (sapan or hatalar) else 0

    if degisen:
        print(f"GÜNCELLENDİ: {', '.join(degisen)}")
    else:
        print("Değişiklik yok — dokümanlar zaten güncel.")
    if hatalar:
        print(f"⚠ {len(hatalar)} doğrulama hatası kaldı (elle düzeltilmeli).")
    if yerlesmemis:
        print(f"⚠ Yerleştirilmemiş blok: {', '.join(yerlesmemis)}")
        print("  Dokümana şunu ekle:")
        print(f"    <!-- OTOMATIK:{yerlesmemis[0]} -->")
        print(f"    <!-- /OTOMATIK:{yerlesmemis[0]} -->")
    return 1 if hatalar else 0


if __name__ == "__main__":
    sys.exit(calistir("--check" in sys.argv))
