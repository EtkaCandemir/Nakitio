"""
Nakitio — Kanonik Ekran Veri Seti

Her ekranın göstereceği HER sayıyı tek bir kaynaktan üretir: Didem'in ham
işlem geçmişi → normalizasyon → skor motoru → ekran verisi.

NEDEN VAR: mockup'larda aynı kullanıcının tasarruf oranı bir ekranda %26,
diğerinde %25; geliri bir ekranda 28.450 TL, diğerinde 45.000 TL. Bu tür
tutarsızlıklar tasarım aşamasında zararsız görünür ama mühendisliğe
geçtiğinde "hangisi doğru" sorusu her ekranda yeniden sorulur ve her
seferinde farklı cevaplanır.

Bu dosya çalıştırıldığında `screen_data.json` üretilir. Tasarım ve
frontend AYNI dosyadan beslenir. Sayı uydurmak yapısal olarak imkânsız
hâle gelir.

Üç durum üretilir — boş ekranlar da kanonik olmalıdır:
    gun0          · hiç veri yok, yalnızca onboarding
    ilk_ekstre    · tek dönem yüklenmiş, güven düşük
    olgun         · 5 dönem, tam veri

Çalıştırma:
    python3 engine/screen_data.py            # özet + JSON yaz
    python3 engine/screen_data.py --json     # yalnızca JSON, stdout
"""

from __future__ import annotations

import dataclasses
import json
import sys
from datetime import date, datetime, timedelta
from typing import Any, Dict, List, Optional

from behavior_infer import estimate_behavior, select_for_triage
from coach_tools import (
    CoachContext, build_action_plan, build_context, get_risks, get_score,
    get_score_breakdown, get_top_categories,
)
import metinler as MET
from data_model import CATEGORIES, DEFAULT_CATEGORY
from normalize import Ledger, active_windows, build_features, windows
from score_engine import MODEL_VERSION, Features, ScoreResult, compute_score
from statement_ingest import INGEST_VERSION, missing_months

SCREEN_DATA_VERSION = "1.0.0"

#: Demo "bugün". Son ekstre 31 Temmuz; bugün 8 Ağustos → devam eden
#: dönem 8 günlük ve kısmi. Ekranların bu ayrımı göstermesi gerekir.
DEMO_TODAY = date(2026, 8, 8)

TR_MONTHS = ["", "Ocak", "Şubat", "Mart", "Nisan", "Mayıs", "Haziran",
             "Temmuz", "Ağustos", "Eylül", "Ekim", "Kasım", "Aralık"]


# ─────────────────────────────────────────────────────────────────────────────
# Biçimlendirme — tek yerde tanımlı
# ─────────────────────────────────────────────────────────────────────────────

def tl(v: Optional[float]) -> Optional[str]:
    if v is None:
        return None
    return "₺" + f"{round(v):,}".replace(",", ".")


def pct(v: Optional[float], digits: int = 0) -> Optional[str]:
    if v is None:
        return None
    s = f"{v:.{digits}f}".replace(".", ",")
    return f"%{s}"


def d_short(d: date) -> str:
    return f"{d.day} {TR_MONTHS[d.month][:3]}"


def d_long(d: date) -> str:
    return f"{d.day} {TR_MONTHS[d.month]} {d.year}"


# ─────────────────────────────────────────────────────────────────────────────
# Dönem etiketleri — aylık ritmin temeli
# ─────────────────────────────────────────────────────────────────────────────

def period_labels(ledger: Ledger, today: date) -> Dict[str, Any]:
    """Kapanan dönem ve devam eden dönem.

    Ekstre modelinde CARİ AY HİÇBİR ZAMAN TAM DEĞİLDİR. Ana sayfa "Temmuz
    2026" deyip yarım veriyi tam gibi gösteremez; kapanan dönemi
    otoriter kaynak olarak sunar, devam eden dönemi ayrı ve açıkça
    kısmi olarak gösterir.
    """
    W = active_windows(ledger, windows(ledger.as_of, 6))
    if not W:
        return {"kapanan": None, "devam_eden": None}
    w0 = W[0]
    return {
        "kapanan": {
            "baslangic": w0.start.isoformat(),
            "bitis": (w0.end - timedelta(days=1)).isoformat(),
            "etiket": f"{d_short(w0.start)} – {d_short(w0.end - timedelta(days=1))}",
            "kaynak_notu": MET.DONEM["kaynak"].format(tarih=d_long(ledger.as_of)),
        },
        "devam_eden": {
            "baslangic": ledger.as_of.isoformat(),
            "bitis": today.isoformat(),
            "etiket": f"{d_short(ledger.as_of)}'den beri",
            "gun": max(0, (today - ledger.as_of).days),
            "uyari": MET.DONEM["devam_uyari"],
        },
    }


def coverage_state(ledger: Ledger) -> Dict[str, Any]:
    """Eksik ekstre dönemleri — kullanıcıya gösterilecek uyarı."""
    W = active_windows(ledger, windows(ledger.as_of, 6))
    periods = [(w.start, w.end - timedelta(days=1)) for w in W]
    missing = missing_months(periods, ledger.as_of, months=6)
    label = MET.eksik_ay_metni(
        missing, {i: TR_MONTHS[i] for i in range(1, 13)}) or None
    return {"eksik_aylar": missing, "uyari": label,
            "donem_sayisi": len(W)}


# ─────────────────────────────────────────────────────────────────────────────
# Ekranlar
# ─────────────────────────────────────────────────────────────────────────────

def screen_home(ctx: CoachContext, ledger: Optional[Ledger],
                today: date) -> Dict[str, Any]:
    f, s = ctx.features, ctx.score
    sc = get_score(ctx)

    skor_karti = {
        "baslik": s.stage_label,
        "bant_olarak_sun": ctx.low_confidence,
        "skor": s.score,
        "band": list(s.band),
        "goster": (f"{s.band[0]}–{s.band[1]}" if ctx.low_confidence
                   else str(s.score)),
        # Güven düşükken SEVİYE ETİKETİ GÖSTERİLMEZ. 5 onboarding
        # cevabından türetilmiş bir skora "Dikkat" demek, skor modelinin
        # "hiçbir zaman utandırma" ilkesinin ihlalidir: kullanıcı henüz
        # ölçülmedi, yargılanamaz.
        "seviye_goster": not ctx.low_confidence,
        "seviye": s.level,
        "mesaj": s.message,
        "degisim": sc.get("degisim"),
        "guven": round(s.confidence, 2),
        "guven_etiketi": ("Yüksek" if s.confidence >= 0.80 else
                          "Orta" if s.confidence >= 0.55 else "Düşük"),
        "alt_not": (None if not ctx.low_confidence else MET.BANT["alt_not"]),
        "bant_aciklama": (MET.BANT["aciklama"] if ctx.low_confidence else None),
        # Gün 0'da düşüklüğü bir YARGI değil bir DAVET olarak çerçevele:
        # belirsizlik kullanıcıda değil bizde.
        "gun0_ust": (MET.GUN0["skor_ustu"] if f.days_of_data == 0 else None),
        "gun0_alt": (MET.GUN0["skor_alti"] if f.days_of_data == 0 else None),
        "guven_notu": (MET.GUN0["guven_notu"] if f.days_of_data == 0 else None),
    }

    kapanan = {
        "gelir": tl(f.i_net), "gelir_ham": round(f.i_net),
        "gider": tl(f.e_total), "gider_ham": round(f.e_total),
        "korunan": tl(f.i_net - f.e_total), "korunan_ham": round(f.i_net - f.e_total),
        "tasarruf_orani": pct(f.s_rate * 100, 1),
        "tasarruf_orani_ham": round(f.s_rate * 100, 1),
        "acil_fon_ay": round(f.ef_months, 1),
    } if f.i_net > 0 else None

    return {
        "skor_karti": skor_karti,
        "donem": period_labels(ledger, today) if ledger else None,
        "kapanan_ozet": kapanan,
        "kapsam": coverage_state(ledger) if ledger else None,
        "birincil_eylem": _primary_action(ctx, ledger),
        "farkindalik": _insight(ctx, ledger),
        "harcama_dagilimi": _spend_split(ctx),
        "guvence": guvence_kademe(ctx),
    }


def _primary_action(ctx: CoachContext, ledger: Optional[Ledger]) -> Dict[str, Any]:
    """Ana sayfadaki tek büyük CTA. Kullanıcının durumuna göre değişir."""
    f = ctx.features
    if f.days_of_data == 0:
        return {"tip": "ekstre_yukle", "baslik": MET.GUN0["kart_baslik"],
                "alt": MET.GUN0["kart_govde"], "cta": MET.GUN0["cta"],
                "ikincil": MET.GUN0["ikincil"]}
    cov = coverage_state(ledger) if ledger else {"eksik_aylar": []}
    if cov["eksik_aylar"]:
        return {"tip": "ekstre_yukle", "baslik": "Eksik dönem var",
                "alt": cov["uyari"], "cta": "Ekstre Yükle"}
    plan = build_action_plan(ctx, max_steps=1)
    if plan["adimlar"]:
        a = plan["adimlar"][0]
        return {"tip": "aksiyon", "baslik": a["aksiyon"],
                "alt": f"Skorun {a['kumulatif_skor']} seviyesine çıkabilir (tahmini).",
                "cta": "Planı Gör", "hedef_skor": a["kumulatif_skor"]}
    return {"tip": "analiz", "baslik": "Analizini gör",
            "alt": "Dönem raporun hazır.", "cta": "Raporu Aç"}


def _insight(ctx: CoachContext, ledger: Optional[Ledger]) -> Optional[Dict[str, Any]]:
    """'Bugünün Farkındalığı' kartı — deterministik seçilir.

    En yüksek REEL artış gösteren isteğe bağlı kategori. Nominal artış
    ASLA tek başına gösterilmez: bir kısmı enflasyondur ve kullanıcıyı
    haksız yere suçlar (veri katmanı N5).
    """
    if ledger is None:
        return None
    cats = get_top_categories(ctx, n=8)
    if "kategoriler" not in cats:
        return None
    # Sıralama YÜZDEYE göre değil, MUTLAK REEL ARTIŞA (TL) göre yapılır.
    # ₺1.200'lük bir kalemde %148 artış, ₺5.400'lük bir kalemde %12
    # artıştan daha az önemlidir — ama yüzdeye göre sıralarsak birincisi
    # kazanır ve kullanıcıya tek bir taksitli alışverişi "sorun" diye
    # sunarız.
    # Bu dönemde YENİ taksit planı başlayan kategoriler elenir. Onlardaki
    # artış bir EĞİLİM değil, tek seferlik bir OLAYDIR; "Giyim harcaman
    # %148 arttı" demek kullanıcıya tek bir taksitli alışverişi sürekli
    # bir sorun gibi göstermektir.
    W = active_windows(ledger, windows(ledger.as_of, 6))
    olay_kategorileri = {p.category for p in ledger.plans
                         if W and W[0].contains(p.start)}

    # "Diğer" de elenir: bir kategori değil, kategorize edilememişlerin
    # çöp kutusudur. Oradaki artış kullanıcının davranışı değil, bizim
    # kategorizasyon kalitemizin artefaktıdır — ve kullanıcıya
    # "Diğer harcaman %68 arttı" demek hiçbir şey öğretmez.
    cop_kutusu = CATEGORIES[DEFAULT_CATEGORY].label

    aday = []
    for k in cats["kategoriler"]:
        r = k["reel_degisim_yuzde"]
        if r is None or r <= 3 or k["kategori"] == cop_kutusu:
            continue
        if any(CATEGORIES.get(c, CATEGORIES[DEFAULT_CATEGORY]).label == k["kategori"]
               for c in olay_kategorileri):
            continue
        onceki = k["tutar"] / (1 + r / 100)
        aday.append((k["tutar"] - onceki, k))
    if not aday:
        return None
    _, k = max(aday, key=lambda x: x[0])
    return {
        "kategori": k["kategori"],
        "tutar": tl(k["tutar"]),
        "nominal": pct(abs(k["nominal_degisim_yuzde"]), 1),
        "reel": pct(abs(k["reel_degisim_yuzde"]), 1),
        "metin": (f"{k['kategori']} harcaman {pct(abs(k['nominal_degisim_yuzde']), 1)} "
                  f"arttı; enflasyondan arındırınca gerçek artış "
                  f"{pct(abs(k['reel_degisim_yuzde']), 1)}."),
    }


#: İleri seviye hedefi. Skorun DIŞINDADIR — `params.P["p3.guvence.tam_ay"]`
#: skorun hedefi, bu ise rozet hedefi.
GUVENCE_ILERI_AY = 6.0


def guvence_kademe(ctx: CoachContext) -> Optional[Dict[str, Any]]:
    """Acil durum fonu — kademeli hedef.

    Skor 3 ay üzerinden hesaplanır (params: p3.guvence.tam_ay).
    6 ay skorun DIŞINDA bir ileri seviye rozetidir.

    Bu ayrım bilinçlidir: kullanıcıya gösterilen hedefle skorun hedefi
    aynı olmazsa, gösterilen hedefe ulaşan kullanıcı tam puan alamaz ve
    kale direği kaymış gibi hisseder.
    """
    from params import P as _P

    f = ctx.features
    aylik = f.e_essential if f.e_essential > 0 else f.e_total
    if aylik <= 0:
        return None

    k1_ay = _P["p3.guvence.tam_ay"]
    k2_ay = GUVENCE_ILERI_AY
    mevcut = f.ef_months

    def kademe(no, ay, ad, alt, skora_dahil):
        hedef = aylik * ay
        return {
            "no": no, "ad": ad, "alt": alt, "ay": ay,
            "hedef_tutar": tl(hedef), "hedef_ham": round(hedef),
            "ilerleme_yuzde": round(100 * min(1.0, f.ef_liquid / hedef)),
            "kalan": tl(max(0.0, hedef - f.ef_liquid)),
            "tamamlandi": mevcut >= ay,
            "skora_dahil": skora_dahil,
        }

    # Mevcut birikim hızıyla kaç ayda ulaşır
    kalan1 = max(0.0, aylik * k1_ay - f.ef_liquid)
    hiz = f.s_deliberate
    sure = round(kalan1 / hiz) if hiz > 0 and kalan1 > 0 else None

    return {
        "baslik": MET.GUVENCE["baslik"],
        "aciklama": MET.GUVENCE["aciklama"],
        "mevcut_ay": round(mevcut, 1),
        "mevcut_tutar": tl(f.ef_liquid),
        "aylik_zorunlu_gider": tl(aylik),
        "aktif_kademe": 1 if mevcut < k1_ay else 2,
        "durum_metni": MET.guvence_durum(mevcut, k1_ay, k2_ay),
        "kademeler": [
            kademe(1, k1_ay, MET.GUVENCE["kademe1_ad"],
                   MET.GUVENCE["kademe1_alt"], True),
            kademe(2, k2_ay, MET.GUVENCE["kademe2_ad"],
                   MET.GUVENCE["kademe2_alt"], False),
        ],
        "tahmini_sure_ay": sure,
        "tahmini_sure_metni": (None if sure is None else
                               f"Bu hızla yaklaşık {sure} ayda ulaşırsın."),
        "neden_3_ay": MET.GUVENCE["neden_3_ay"],
    }


def _spend_split(ctx: CoachContext) -> Optional[Dict[str, Any]]:
    f = ctx.features
    if f.e_total <= 0:
        return None
    zorunlu = f.e_essential / f.e_total
    return {"zorunlu_pay": pct(zorunlu * 100), "istege_bagli_pay": pct(f.disc_share * 100),
            "zorunlu_tutar": tl(f.e_essential),
            "istege_bagli_tutar": tl(f.e_total - f.e_essential)}


def screen_score_report(ctx: CoachContext) -> Dict[str, Any]:
    s = ctx.score
    br = get_score_breakdown(ctx)
    return {
        "skor": s.score, "band": list(s.band), "seviye": s.level,
        "asama": s.stage_label,
        "guven": round(s.confidence, 2),
        "veri_yeterliligi": ("Yüksek" if s.confidence >= 0.80 else
                             "Orta" if s.confidence >= 0.55 else "Düşük"),
        "hesaplama_notu": f"{ctx.features.days_of_data} günlük veriye göre hesaplandı",
        "bilesenler": br["bilesenler"],
        "en_zayif": br["en_zayif"],
        "maddi_olaylar": s.material_events,
    }


def screen_analysis(ctx: CoachContext, ledger: Optional[Ledger]) -> Dict[str, Any]:
    f = ctx.features
    est = None
    if ledger is not None:
        W = active_windows(ledger, windows(ledger.as_of, 6))
        if W:
            est = estimate_behavior(ledger, W[0], f.disc_share)

    davranis = None
    if est is not None:
        davranis = {
            # ⚠ Sunum kuralı: bu değerler ÇIKARIMDIR. `iddia_edilebilir`
            # false ise UI bunları "senin duygusal harcaman %X" diye
            # göstermez; "bunlar duygusal olabilir mi?" diye sorar.
            "iddia_edilebilir": est.label_weight >= 0.5,
            "etiket_sayisi": est.label_count,
            "etiket_agirligi": round(est.label_weight, 2),
            "plansiz_oran": pct((f.imp_rate or 0) * 100),
            "duygusal_pay": pct((f.emo_rate or 0) * 100),
            "pismanlik": pct((f.regret_rate or 0) * 100),
            "gece_yogunlasmasi": (pct(f.night_conc * 100)
                                  if f.night_conc is not None else None),
            "gece_olculemedi_notu": (None if f.night_conc is not None else
                                     "Ekstrede işlem saati yok; gece "
                                     "yoğunlaşması ölçülemiyor."),
        }

    return {
        "genel_bakis": {
            "skor": ctx.score.score,
            "tasarruf_orani": pct(f.s_rate * 100, 1),
            "korunan_tutar": tl(f.i_net - f.e_total),
            "guvence_suresi_ay": round(f.ef_months, 1),
        },
        "gelir_gider": {
            "gelir": tl(f.i_net), "gider": tl(f.e_total),
            "zorunlu": tl(f.e_essential),
            "istege_bagli": tl(f.e_total - f.e_essential),
            "ana_gelir_payi": (pct(f.i_primary_share * 100)
                               if f.i_primary_share else None),
            "gelir_oynakligi": (round(f.i_cv, 2) if f.i_cv is not None else None),
        },
        "kategoriler": (get_top_categories(ctx, n=6).get("kategoriler")
                        if ledger else None),
        "davranis": davranis,
        "riskler": get_risks(ctx)["riskler"],
        "borc": {
            "anapara": tl(f.debt_principal),
            "dsr": pct(f.dsr * 100, 1),
            "taksit_aylik": tl(f.installment_monthly),
            "taksit_kalan": tl(f.installment_remaining),
            "kart_kullanimi": (pct(f.card_utilization * 100)
                               if f.card_utilization is not None else None),
        },
    }


def screen_plan(ctx: CoachContext) -> Dict[str, Any]:
    p = build_action_plan(ctx, max_steps=3)
    return {
        "skor_simdi": p["skor_simdi"],
        "skor_plan_sonrasi": p["skor_plan_sonrasi"],
        "toplam_etki": p["toplam_etki"],
        "ufuk_ay": p["ufuk_ay"],
        "adimlar": [
            {"aksiyon": a["aksiyon"], "zorluk": a["zorluk"],
             "kumulatif_skor": a["kumulatif_skor"], "ek_etki": a["ek_etki"],
             "parametreler": a["parametreler"]}
            for a in p["adimlar"]
        ],
        "sunum_uyarisi": "Projeksiyon; kesinlik dili kullanılmaz.",
    }


def screen_triage(ledger: Optional[Ledger], k: int = 10) -> Dict[str, Any]:
    if ledger is None:
        return {"kartlar": [], "durum": "veri yok"}
    W = active_windows(ledger, windows(ledger.as_of, 6))
    if not W:
        return {"kartlar": [], "durum": "veri yok"}
    kartlar = select_for_triage(ledger, W[0], k=k)
    return {
        "baslik": "Bu harcamalar plansız mıydı?",
        "alt": "Birkaç saniye — davranış analizin bunlarla kişiselleşiyor.",
        "atlanabilir": True,
        "kartlar": kartlar,
        "secenekler": ["Plansızdı", "Planlıydı"],
        "opsiyonel_duygu": ["Kendimi ödüllendirdim", "Streslidim",
                            "Canım sıkıldı", "Sosyal etki", "Alışkanlık"],
    }


def screen_goals(ctx: CoachContext, ledger: Optional[Ledger]) -> Dict[str, Any]:
    if ledger is None or not ledger.raw.goals:
        return {"hedefler": [], "durum": "hedef yok"}
    out = []
    for g in ledger.raw.goals:
        span = max(1, (g.target_date - g.created_at).days)
        elapsed = min(span, max(0, (ledger.as_of - g.created_at).days))
        beklenen = g.target_amount * (elapsed / span)
        out.append({
            "ad": g.name,
            "hedef": tl(g.target_amount), "mevcut": tl(g.current_amount),
            "ilerleme": pct(100 * g.current_amount / g.target_amount),
            "beklenen_ilerleme": pct(100 * beklenen / g.target_amount),
            "durumda_mi": g.current_amount >= beklenen * 0.95,
            "kalan_ay": max(0, round((g.target_date - ledger.as_of).days / 30)),
        })
    return {"hedefler": out,
            "ontrack_oran": pct((ctx.features.goal_ontrack or 0) * 100)}


# ─────────────────────────────────────────────────────────────────────────────
# Durumlar
# ─────────────────────────────────────────────────────────────────────────────

def _bundle(f: Features, ledger: Optional[Ledger], today: date,
            prev: Optional[Features] = None) -> Dict[str, Any]:
    ctx = build_context(f, prev_features=prev, ledger=ledger,
                        as_of=ledger.as_of if ledger else today)
    return {
        "ana_sayfa": screen_home(ctx, ledger, today),
        "skor_raporu": screen_score_report(ctx),
        "analiz": screen_analysis(ctx, ledger),
        "plan": screen_plan(ctx),
        "triyaj": screen_triage(ledger),
        "hedefler": screen_goals(ctx, ledger),
    }


def state_gun0() -> Dict[str, Any]:
    """Hiç veri yok. Yalnızca onboarding cevapları var.

    Bu durum ekstre modelinde KAÇINILMAZDIR: kullanıcı ilk gün tanım
    gereği boş ekran görür. Mockup'ların hiçbiri bu durumu çizmiyor.
    """
    f = Features(
        user_id="didem", days_of_data=0,
        accounts_declared=2, accounts_linked=0, categorized_ratio=0.0,
        data_source="statement", statement_coverage=0.0, manual_entry=True,
        onboarding={"zorluk": "nereye_gidiyor", "ay_sonu": "bazen",
                    "takip": "bazen", "borc_durumu": "yonetilebilir",
                    "birikim_6ay": "ara_sira"},
    )
    return _bundle(f, None, DEMO_TODAY)


def state_ilk_ekstre() -> Dict[str, Any]:
    """Tek dönem yüklenmiş. Güven düşük, skor bant olarak sunulmalı."""
    from fixture_didem import AS_OF, build_raw
    raw = build_raw()
    cutoff = AS_OF - timedelta(days=30)
    raw.transactions = [t for t in raw.transactions if t.ts.date() >= cutoff]
    raw.debt_principal_history = raw.debt_principal_history[-1:]
    f, led = build_features(raw, AS_OF)
    f = dataclasses.replace(f, data_source="statement", accounts_linked=0,
                            statement_coverage=1 / 6)
    return _bundle(f, led, DEMO_TODAY)


def state_olgun() -> Dict[str, Any]:
    """5 dönem yüklenmiş. Tam veri."""
    from fixture_didem import AS_OF, build_raw
    f, led = build_features(build_raw(), AS_OF)
    f = dataclasses.replace(f, data_source="statement", accounts_linked=0,
                            statement_coverage=5 / 6)
    prev = dataclasses.replace(f, s_deliberate=f.s_deliberate * 0.7,
                               ef_liquid=f.ef_liquid * 0.6, prev_score=None)
    return _bundle(f, led, DEMO_TODAY, prev=prev)


STATES = {"gun0": state_gun0, "ilk_ekstre": state_ilk_ekstre, "olgun": state_olgun}


def build_all() -> Dict[str, Any]:
    from normalize import PIPELINE_VERSION
    return {
        "meta": {
            "surum": SCREEN_DATA_VERSION,
            "skor_modeli": MODEL_VERSION,
            "veri_hatti": PIPELINE_VERSION,
            "ekstre_alimi": INGEST_VERSION,
            "kullanici": "Didem (kanonik demo profili)",
            "not": "Tüm sayılar engine/fixture_didem.py'deki ham işlemlerden "
                   "hesaplanmıştır. Elle değiştirilmemeli; ekran verisi "
                   "değişecekse fixture değiştirilir ve bu dosya yeniden "
                   "üretilir.",
        },
        "durumlar": {k: fn() for k, fn in STATES.items()},
    }


# ─────────────────────────────────────────────────────────────────────────────

def _summary(data: Dict[str, Any]) -> None:
    print("NAKITIO — KANONİK EKRAN VERİ SETİ")
    print("=" * 78)
    m = data["meta"]
    print(f"skor modeli {m['skor_modeli']} · veri hattı {m['veri_hatti']} · "
          f"ekstre {m['ekstre_alimi']}\n")

    for ad, st in data["durumlar"].items():
        h = st["ana_sayfa"]
        k = h["skor_karti"]
        print(f"── {ad.upper()} " + "─" * (72 - len(ad)))
        print(f"  skor kartı     {k['baslik']}: {k['goster']}"
              f"  ({k['seviye']}, güven {k['guven']} = {k['guven_etiketi']})")
        if h["donem"] and h["donem"]["kapanan"]:
            print(f"  kapanan dönem  {h['donem']['kapanan']['etiket']}"
                  f"   ({h['donem']['kapanan']['kaynak_notu']})")
            print(f"  devam eden     {h['donem']['devam_eden']['etiket']}"
                  f"   ({h['donem']['devam_eden']['gun']} gün, kısmi)")
        if h["kapanan_ozet"]:
            o = h["kapanan_ozet"]
            print(f"  özet           gelir {o['gelir']} · gider {o['gider']} · "
                  f"korunan {o['korunan']} · tasarruf {o['tasarruf_orani']}")
        if h["kapsam"] and h["kapsam"]["uyari"]:
            print(f"  kapsam uyarısı {h['kapsam']['uyari']}")
        pa = h["birincil_eylem"]
        print(f"  birincil eylem [{pa['cta']}] {pa['baslik']} — {pa['alt']}")
        if h["farkindalik"]:
            print(f"  farkındalık    {h['farkindalik']['metin']}")

        d = st["analiz"]["davranis"]
        if d:
            print(f"  davranış       plansız {d['plansiz_oran']} · duygusal "
                  f"{d['duygusal_pay']} · pişmanlık {d['pismanlik']}"
                  f"   [iddia edilebilir: {'evet' if d['iddia_edilebilir'] else 'HAYIR → soru olarak sun'}]")
            if d["gece_olculemedi_notu"]:
                print(f"                 {d['gece_olculemedi_notu']}")
        p = st["plan"]
        if p["adimlar"]:
            print(f"  plan           {p['skor_simdi']} → {p['skor_plan_sonrasi']} "
                  f"({p['toplam_etki']:+d}) / {len(p['adimlar'])} adım")
        print(f"  triyaj         {len(st['triyaj']['kartlar'])} kart")
        print()


def main() -> None:
    data = build_all()
    if "--json" in sys.argv:
        print(json.dumps(data, ensure_ascii=False, indent=2))
        return
    _summary(data)
    path = "screen_data.json"
    with open(path, "w", encoding="utf-8") as fh:
        json.dump(data, fh, ensure_ascii=False, indent=2)
    print(f"→ {path} yazıldı ({len(json.dumps(data, ensure_ascii=False)):,} bayt)"
          .replace(",", "."))


if __name__ == "__main__":
    main()
