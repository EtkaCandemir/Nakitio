"""
Nakitio Skor Modeli v2 — Değişmez Kural (Invariant) Testleri

Golden test "bu profil bu skoru alır" der. Bu dosya ondan farklı bir şey
yapar: modelin eşikleri değişse bile ASLA bozulmaması gereken yapısal
kuralları test eder. Bir eşiği ayarlarken golden testler değişebilir;
buradaki testlerden biri kırılıyorsa model bozulmuş demektir.

Çalıştırma:
    python3 engine/test_invariants.py
"""

from __future__ import annotations

import dataclasses
import inspect
import math
import sys

from score_engine import (
    Features, compute_score, prior_score, level_of, LEVELS,
    lin, sat, concave, MODEL_VERSION,
)
from golden_profiles import PROFILES

FAILS = []
PASSES = 0


def check(name, cond, detail=""):
    global PASSES
    if cond:
        PASSES += 1
    else:
        FAILS.append(f"{name}" + (f"  — {detail}" if detail else ""))


def base_user(**kw) -> Features:
    d = dict(
        days_of_data=180,
        i_net=30_000, i_cv=0.10, i_primary_share=0.85, i_declared=30_000,
        e_total=22_000, e_essential=15_000, liquid_balance=14_000,
        s_deliberate=4_000, ef_liquid=15_000, s_consistency_months=3,
        debt_principal=20_000, debt_monthly_service=3_000,
        installment_monthly=1_000, installment_remaining=12_000,
        card_balance=9_000, card_limit=30_000, debt_trend_3m=-0.03,
        budget_planned=21_000, budget_overrun=1_500,
        limit_categories=4, limit_breached=1, cat_volatility=0.30,
        goals_active=2, goal_ontrack=0.60, goal_consistency=0.60,
        goal_required_monthly=4_000,
        beh_coverage=0.70, imp_rate=0.20, emo_rate=0.10,
        night_conc=0.12, regret_rate=0.25,
        accounts_declared=3, accounts_linked=2, categorized_ratio=0.90,
        manual_entry=False,
        onboarding={"zorluk": "nereye_gidiyor", "ay_sonu": "bazen",
                    "takip": "bazen", "borc_durumu": "yonetilebilir",
                    "birikim_6ay": "ara_sira"},
    )
    d.update(kw)
    return Features(user_id="inv", **d)


# ── 1. Determinizm ───────────────────────────────────────────────────────────

def t_determinism():
    f = base_user()
    a, b = compute_score(f), compute_score(f)
    check("determinizm: aynı girdi → aynı skor", a.score == b.score)
    check("determinizm: ham skor da aynı",
          abs(a.raw_score - b.raw_score) < 1e-12)


# ── 2. Monotonluk ────────────────────────────────────────────────────────────
# Bir metriği tek başına iyileştirmek skoru ASLA düşürmemeli.

MONOTONIC = [
    ("tasarruf tutarı",      "s_deliberate",      [0, 2_000, 4_000, 8_000, 12_000]),
    ("acil durum fonu",      "ef_liquid",         [0, 15_000, 45_000, 90_000, 150_000]),
    ("tasarruf sürekliliği", "s_consistency_months", [0, 1, 2, 3, 4, 5, 6]),
    ("likit bakiye",         "liquid_balance",    [0, 5_000, 14_000, 40_000, 80_000]),
]
ANTITONIC = [
    ("toplam gider",         "e_total",           [12_000, 18_000, 22_000, 28_000, 34_000]),
    ("aylık borç servisi",   "debt_monthly_service", [0, 2_000, 5_000, 9_000, 14_000]),
    ("kart bakiyesi",        "card_balance",      [0, 6_000, 15_000, 24_000, 29_000]),
    ("kalan taksit",         "installment_remaining", [0, 30_000, 90_000, 180_000, 300_000]),
    ("plansız harcama oranı", "imp_rate",         [0.02, 0.10, 0.20, 0.32, 0.45]),
    ("duygusal harcama payı", "emo_rate",         [0.01, 0.06, 0.14, 0.24, 0.35]),
    ("gelir oynaklığı (CV)", "i_cv",              [0.02, 0.12, 0.25, 0.40, 0.60]),
    ("bütçe aşımı",          "budget_overrun",    [0, 800, 2_500, 6_000, 12_000]),
    ("gecikme günü",         "days_past_due",     [0, 3, 15, 45, 120]),
]


def t_monotonicity():
    for label, fieldname, values in MONOTONIC:
        scores = [compute_score(base_user(**{fieldname: v})).blended_score
                  for v in values]
        ok = all(scores[i] <= scores[i + 1] + 1e-9 for i in range(len(scores) - 1))
        check(f"monotonluk ↑: {label}", ok,
              " → ".join(f"{s:.1f}" for s in scores))

    for label, fieldname, values in ANTITONIC:
        scores = [compute_score(base_user(**{fieldname: v})).blended_score
                  for v in values]
        ok = all(scores[i] >= scores[i + 1] - 1e-9 for i in range(len(scores) - 1))
        check(f"monotonluk ↓: {label}", ok,
              " → ".join(f"{s:.1f}" for s in scores))


# ── 3. Süreklilik (uçurum yok) ───────────────────────────────────────────────
# v1'in en büyük hatası basamak tablolarıydı: gider/gelir %70.0 → 25 puan,
# %70.1 → 20 puan. Girdideki %1'lik değişim skorda 1 puandan fazla
# oynamamalı.

CONTINUITY = [
    ("gider/gelir", "e_total", 6_000, 34_000),
    ("borç servisi", "debt_monthly_service", 0, 15_000),
    ("tasarruf", "s_deliberate", 0, 15_000),
    ("acil fon", "ef_liquid", 0, 200_000),
    ("plansız oran", "imp_rate", 0.0, 0.6),
    ("kart bakiyesi", "card_balance", 0, 30_000),
]
MAX_JUMP = 1.0


def t_continuity():
    for label, fieldname, lo, hi in CONTINUITY:
        steps = 400
        prev_s = None
        worst, worst_at = 0.0, None
        for i in range(steps + 1):
            v = lo + (hi - lo) * i / steps
            s = compute_score(base_user(**{fieldname: v})).blended_score
            if prev_s is not None:
                j = abs(s - prev_s)
                if j > worst:
                    worst, worst_at = j, v
            prev_s = s
        check(f"süreklilik: {label} (uçurum yok)", worst <= MAX_JUMP,
              f"en büyük sıçrama {worst:.3f} puan @ {worst_at:,.0f}")


# ── 4. Eksik veri asla ceza değildir ─────────────────────────────────────────

def t_missing_data_never_punishes():
    full = compute_score(base_user())

    # Borç verisi hiç yoksa bileşen devre dışı kalmalı, 0 puan almamalı.
    nodebt = compute_score(base_user(has_debt_data=False))
    dp = [p for p in nodebt.pillars if p.key == "debt"][0]
    check("eksik veri: borç bileşeni devre dışı (0 puan değil)",
          not dp.enabled and dp.points == 0.0)
    check("eksik veri: kalan ağırlıklar 100'e normalize edilir",
          abs(sum(p.weight_effective for p in nodebt.pillars) - 100.0) < 1e-9,
          f"toplam={sum(p.weight_effective for p in nodebt.pillars):.4f}")

    # Davranış etiketi yoksa bileşen kapanır ve C düşer, skor çökmez.
    nobeh = compute_score(base_user(beh_coverage=0.0))
    bp = [p for p in nobeh.pillars if p.key == "behavior"][0]
    check("eksik veri: davranış bileşeni devre dışı", not bp.enabled)
    check("eksik veri: güven düşer", nobeh.confidence < full.confidence)

    # Bütçe kurmamış kullanıcı disiplin bileşeninden sıfır almamalı.
    nobudget = compute_score(base_user(budget_planned=None, budget_overrun=None,
                                       limit_categories=None, limit_breached=None,
                                       cat_volatility=None))
    d = [p for p in nobudget.pillars if p.key == "discipline"][0]
    check("eksik veri: bütçesiz kullanıcı disiplinden 0 almaz",
          d.enabled and d.score_100 > 0)


def t_absent_balance_is_not_zero():
    """Bakiye YOKLUĞU ile bakiyenin SIFIR olması ayrı şeylerdir."""
    # Bu test bir hatanın anıtıdır. `liquid_balance` ve `ef_liquid` başta
    # `float = 0.0` idi; motor "bakiyeyi bilmiyorum" ile "bakiyesi sıfır"
    # arasında ayrım yapamıyordu. Bakiye tutmayan bir veri kaynağı (manuel
    # giriş) bağlanınca `tampon` ve `guvence` alt metrikleri 0 puan alıyor,
    # yani EKSİK VERİ CEZAYA dönüşüyordu. 15 golden profilde ölçüldü:
    # sağlıklı kullanıcılar -7,3 puan kaybederken riskliler +3,4 puan
    # kazanıyordu — skor ortalamaya sıkışıyor, ayırt etme gücünü
    # kaybediyordu (korelasyon r = -0,93).
    var  = base_user()
    sifir = base_user(liquid_balance=0.0, ef_liquid=0.0)
    yok   = base_user(liquid_balance=None, ef_liquid=None)

    r_var, r_sifir, r_yok = map(compute_score, (var, sifir, yok))

    # ── 1. Türetilmişler yokluğu taşımalı ────────────────────────────────
    check("bakiye yok: runway_days None döner", yok.runway_days is None)
    check("bakiye yok: ef_months None döner", yok.ef_months is None)
    check("bakiye sıfır: runway_days SAYI döner (0 gün ölçülmüştür)",
          sifir.runway_days == 0.0)
    check("bakiye sıfır: ef_months SAYI döner", sifir.ef_months == 0.0)

    def sub(res, pillar_key, sub_key):
        pl = [p for p in res.pillars if p.key == pillar_key][0]
        return pl, [x for x in pl.subs if x.key == sub_key][0]

    # ── 2. Alt metrik DEVRE DIŞI kalmalı, 0 puan almamalı ────────────────
    p1_yok, tampon_yok = sub(r_yok, "cashflow", "tampon")
    p3_yok, guvence_yok = sub(r_yok, "savings", "guvence")
    check("bakiye yok: tampon alt metriği devre dışı", tampon_yok.value is None)
    check("bakiye yok: güvence alt metriği devre dışı", guvence_yok.value is None)

    _, tampon_sifir = sub(r_sifir, "cashflow", "tampon")
    _, guvence_sifir = sub(r_sifir, "savings", "guvence")
    check("bakiye sıfır: tampon ÖLÇÜLÜR (0 puan)", tampon_sifir.value == 0.0)
    check("bakiye sıfır: güvence ÖLÇÜLÜR (0 puan)", guvence_sifir.value == 0.0)

    # ── 3. Bileşen ayakta kalmalı, ağırlık yeniden dağıtılmalı ───────────
    check("bakiye yok: nakit akışı bileşeni kapanmaz",
          p1_yok.enabled and p1_yok.score_100 is not None and p1_yok.score_100 > 0)
    check("bakiye yok: tasarruf bileşeni kapanmaz",
          p3_yok.enabled and p3_yok.score_100 is not None and p3_yok.score_100 > 0)
    check("bakiye yok: ağırlıklar 100'e normalize kalır",
          abs(sum(p.weight_effective for p in r_yok.pillars) - 100.0) < 1e-9)

    # ── 4. Uydurma metin olmamalı ────────────────────────────────────────
    check("bakiye yok: tampon açıklaması '0 gün' uydurmaz",
          tampon_yok.detail == "", f"detail={tampon_yok.detail!r}")
    check("bakiye yok: güvence açıklaması '0,0 ay' uydurmaz",
          guvence_yok.detail == "", f"detail={guvence_yok.detail!r}")

    # ── 5. Yokluk, ölçülmüş sıfırdan DAHA KÖTÜ olamaz ────────────────────
    # 2. kuralın çekirdeği: ölçemediğin şey için puan kırma.
    check("bakiye yok >= bakiye sıfır (eksik veri ceza değildir)",
          r_yok.score >= r_sifir.score,
          f"yok={r_yok.score} < sifir={r_sifir.score}")

    # ── 6. Ama güven DÜŞMELİ ─────────────────────────────────────────────
    # Kural 2 üç şey ister: bileşeni kapat, ağırlığı normalize et, GÜVENİ
    # DÜŞÜR. İlk sürümde üçüncüsü yoktu: `c_pillar` yalnız kapalı BİLEŞENİ
    # sayıyor, açık bir bileşenin içinde kaybolan alt metriği görmüyordu.
    # Sonuç: girdi yüzeyinin %37'sini kaybeden bir kaynak yalnızca 0,09
    # güven kaybediyordu — motor kör olduğunu bilmiyordu.
    check("bakiye yok: güven düşer", r_yok.confidence < r_var.confidence,
          f"C {r_var.confidence:.3f} -> {r_yok.confidence:.3f}")
    check("bakiye yok: band genişler",
          (r_yok.band[1] - r_yok.band[0]) >= (r_var.band[1] - r_var.band[0]))

    # ── 7. Ölçülmemiş şey maddi olay olarak bildirilemez ─────────────────
    check("bakiye yok: 'acil durum fonu kritik' olayı üretilmez",
          not any("acil durum fonu" in e for e in r_yok.material_events),
          str(r_yok.material_events))
    check("bakiye sıfır: 'acil durum fonu kritik' olayı ÜRETİLİR",
          any("acil durum fonu" in e for e in r_sifir.material_events),
          str(r_sifir.material_events))

    # ── 8. Sistematik sıkışma olmamalı ───────────────────────────────────
    # Asıl hata buydu: sapma gürültü değil, ortalamaya doğru sistematik
    # çekimdi. Bakiyeyi kaldırınca sağlıklı profiller düşüyor, riskliler
    # yükseliyordu. Korelasyon -0,93'ten -0,44'e indi; eşik ona göre.
    import statistics as _st
    xs, ys = [], []
    for _k, (_f, _n, _e) in PROFILES.items():
        t = compute_score(_f)
        u = compute_score(dataclasses.replace(_f, liquid_balance=None, ef_liquid=None))
        xs.append(t.score); ys.append(u.score - t.score)
        check(f"golden/{_k}: bakiye yokluğu ölçülmüş sıfırdan kötü değil",
              u.score >= compute_score(dataclasses.replace(
                  _f, liquid_balance=0.0, ef_liquid=0.0)).score)
        check(f"golden/{_k}: bakiye yokluğu güveni düşürür",
              u.confidence < t.confidence)
    mx, my = _st.fmean(xs), _st.fmean(ys)
    cov = sum((a - mx) * (b - my) for a, b in zip(xs, ys))
    sx = math.sqrt(sum((a - mx) ** 2 for a in xs))
    sy = math.sqrt(sum((b - my) ** 2 for b in ys))
    r = cov / (sx * sy) if sx and sy else 0.0
    check("bakiye yokluğu skoru ortalamaya SİSTEMATİK olarak sıkıştırmaz",
          r > -0.60, f"korelasyon={r:+.2f} (düzeltme öncesi -0,93)")



def t_undefined_ratios_disable_submetrics():
    """Paydası bilinmeyen ORAN ölçülememiştir — 0 puan değil, devre dışı."""
    # Bakiye düzeltmesinin (bkz. `t_absent_balance_is_not_zero`) aynı hatası
    # beş alt metrikte daha duruyordu: bunlar yapısal olarak `None` DÖNEMİYOR,
    # eksik veriyi sessizce bir sayıya çeviriyorlardı.
    def sub(res, pk, sk):
        pl = [p for p in res.pillars if p.key == pk][0]
        return pl, [x for x in pl.subs if x.key == sk][0]

    # ── A. Gider yok → isteğe bağlı pay ÖLÇÜLEMEZ ────────────────────────
    #
    # En görünür hâliydi: `disc_share` 0,0 dönüyor, `lin(0; 0,60 → 0,20)`
    # 100 puan veriyordu. Yani hiç gider verisi olmayan kullanıcı Harcama
    # Disiplini'nden TAM PUAN alıyordu — ölçülmemiş bir şey için ödül.
    nogider = base_user(e_total=0.0, e_essential=0.0, budget_planned=None,
                        budget_overrun=None, limit_categories=None,
                        limit_breached=None, cat_volatility=None)
    check("gider yok: disc_share None döner", nogider.disc_share is None)
    r = compute_score(nogider)
    p4, ib = sub(r, "discipline", "istege_bagli")
    check("gider yok: isteğe bağlı pay devre dışı", ib.value is None)
    check("gider yok: disiplin bileşeni TAM PUAN vermez",
          not p4.enabled or (p4.score_100 or 0) < 100.0,
          f"enabled={p4.enabled} score={p4.score_100}")
    check("gider yok: uydurma açıklama metni yok", ib.detail == "")

    # ── B. Gelir yok → gelire oranlanan hiçbir metrik ölçülemez ──────────
    nogelir = base_user(i_net=0.0)
    check("gelir yok: s_rate None", nogelir.s_rate is None)
    check("gelir yok: dsr None", nogelir.dsr is None)
    check("gelir yok: commit_ratio None", nogelir.commit_ratio is None)
    r = compute_score(nogelir)
    for pk, sk, ad in (("debt", "dsr", "DSR"),
                       ("debt", "taahhut", "taahhüt"),
                       ("savings", "oran", "tasarruf oranı")):
        _, sc = sub(r, pk, sk)
        check(f"gelir yok: {ad} devre dışı (0 puan değil)", sc.value is None)
        check(f"gelir yok: {ad} açıklaması uydurmaz", sc.detail == "")

    # Gelirsizliğin GERÇEK riski susturulmaz — başka kanaldan bildirilir.
    check("gelir yok: maddi olay yine de bildirilir",
          any("gelir" in e for e in r.material_events), str(r.material_events))

    # ── C. Kısa geçmiş → süreklilik ölçülemez ────────────────────────────
    kisa = base_user(s_consistency_months=None)
    r = compute_score(kisa)
    _, su = sub(r, "savings", "sureklilik")
    check("kısa geçmiş: süreklilik devre dışı", su.value is None)
    check("kısa geçmiş: '0/6 ay' uydurulmaz", su.detail == "")

    # ── D. Ölçememek, ölçülmüş kötü değerden KÖTÜ olamaz ─────────────────
    for ad, yok_kw, sifir_kw in (
        ("isteğe bağlı pay", dict(e_total=0.0, e_essential=0.0, budget_planned=None,
                                  budget_overrun=None, limit_categories=None,
                                  limit_breached=None, cat_volatility=None),
                             dict(e_total=1.0, e_essential=0.0, budget_planned=None,
                                  budget_overrun=None, limit_categories=None,
                                  limit_breached=None, cat_volatility=None)),
        ("süreklilik", dict(s_consistency_months=None),
                       dict(s_consistency_months=0)),
    ):
        yok = compute_score(base_user(**yok_kw))
        sifir = compute_score(base_user(**sifir_kw))
        check(f"{ad}: 'ölçülemedi' >= 'ölçüldü, en kötü'",
              yok.score >= sifir.score, f"yok={yok.score} sifir={sifir.score}")

    # ── E. Geliri GİZLEMEK skoru yükseltmemeli (anti-gaming, K6 ruhu) ────
    borclu = base_user(i_net=20_000, i_declared=20_000, e_total=19_000,
                       e_essential=13_000, s_deliberate=0,
                       debt_principal=180_000, debt_monthly_service=9_000,
                       card_balance=40_000, card_limit=50_000)
    check("geliri gizlemek skoru yükseltmez",
          compute_score(dataclasses.replace(borclu, i_net=0.0)).score
          <= compute_score(borclu).score)


def t_smoothing_anchor_uses_measurement():
    """Yumuşatmanın çapası GÖSTERİLEN skor değil, bugünkü güvenle
    değerlendirilmiş ÖLÇÜMdür."""
    # M6 kararı. Mekanizma `smoothing_anchor`da yazılıydı ama `derive_features`
    # `prev_raw_score`/`prev_confidence` üretmediği için canlı hatta HİÇ
    # devreye girmiyordu; her zaman "eski davranış"a düşüyordu.
    f = base_user(prev_score=55.0, prev_raw_score=None, prev_confidence=None)
    eski = compute_score(f)
    yeni = compute_score(dataclasses.replace(
        f, prev_raw_score=74.0, prev_confidence=0.20))

    check("çapa: girdi yoksa eski davranış (gösterilen skora sabitlenir)",
          eski.smoothing.get("guven_duzeltmesi") is False)
    check("çapa: girdi varsa güven düzeltmesi uygulanır",
          yeni.smoothing.get("guven_duzeltmesi") is True,
          str(yeni.smoothing))
    # Ölçümü öncülünden yüksek olan kullanıcı, güven arttığında saklanan
    # puanı ANINDA görmeli — bu bir finansal değişiklik değil, bizim
    # ölçümümüzün düzelmesidir (K8).
    check("çapa: güven artışı yumuşatılmaz, anında yansır",
          yeni.score > eski.score, f"{eski.score} -> {yeni.score}")


def t_pillar_weights_come_from_params():
    """Hiçbir bileşen nominal ağırlığını literal olarak taşımaz."""
    # `pillar_goals`ın aktif-hedef dalı `P["p5.weight"]` yerine literal 10.0
    # okuyordu. Değerler eşit olduğu için sessizdi; `p5.weight` değişince
    # `tune.py` P5'i yanlış ölçecek ve toplam 100 garantisi kırılacaktı.
    import score_engine as SE
    orig = SE.P["p5.weight"]
    try:
        SE.P["p5.weight"] = 14.0
        r = compute_score(base_user(goals_active=2, goal_ontrack=0.6,
                                    goal_consistency=0.6, goal_required_monthly=4_000))
        p5 = [p for p in r.pillars if p.key == "goals"][0]
        check("P5 nominal ağırlığı params'tan okunur",
              p5.weight_nominal == 14.0, f"={p5.weight_nominal}")
        check("ağırlık değişince toplam yine 100",
              abs(sum(p.weight_effective for p in r.pillars) - 100.0) < 1e-9)
    finally:
        SE.P["p5.weight"] = orig



# ── 5. Güven ve karma ────────────────────────────────────────────────────────

def t_confidence_blending():
    # Veri arttıkça skor öncülden uzaklaşıp hama yaklaşmalı.
    prev_gap = None
    for d in (5, 15, 30, 60, 120, 240):
        r = compute_score(base_user(days_of_data=d))
        gap = abs(r.blended_score - r.raw_score)
        if prev_gap is not None:
            check(f"güven: gün {d} — ham skora yakınsama", gap <= prev_gap + 1e-9,
                  f"fark {prev_gap:.2f} → {gap:.2f}")
        prev_gap = gap

    # C ∈ [0,1] her zaman
    for d in (0, 1, 7, 21, 90, 3650):
        r = compute_score(base_user(days_of_data=d))
        check(f"güven: C ∈ [0,1] (gün {d})", 0.0 <= r.confidence <= 1.0)

    # Gün 29 → 31 arasında süreksizlik olmamalı (v1'in gün-30 uçurumu)
    s29 = compute_score(base_user(days_of_data=29)).blended_score
    s31 = compute_score(base_user(days_of_data=31)).blended_score
    check("güven: gün 29→31 arasında uçurum yok", abs(s31 - s29) <= 1.0,
          f"{s29:.2f} → {s31:.2f}")


# ── 6. Sınırlar ──────────────────────────────────────────────────────────────

def t_bounds():
    extreme_bad = base_user(
        i_net=8_000, e_total=20_000, e_essential=18_000, liquid_balance=0,
        s_deliberate=0, ef_liquid=0, s_consistency_months=0,
        debt_principal=400_000, debt_monthly_service=9_000,
        installment_monthly=6_000, installment_remaining=300_000,
        card_balance=30_000, card_limit=30_000, debt_trend_3m=0.5,
        days_past_due=180, min_payment_only_months=12, kmh_active=True,
        budget_planned=10_000, budget_overrun=12_000,
        limit_categories=4, limit_breached=4, cat_volatility=1.2,
        goals_active=1, goal_ontrack=0.0, goal_consistency=0.0,
        goal_required_monthly=9_000,
        imp_rate=0.9, emo_rate=0.8, night_conc=0.9, regret_rate=0.95,
        onboarding={"zorluk": "borc", "ay_sonu": "hayir", "takip": "hayir",
                    "borc_durumu": "asgari", "birikim_6ay": "hayir"})
    extreme_good = base_user(
        i_net=200_000, e_total=40_000, e_essential=25_000, liquid_balance=400_000,
        s_deliberate=120_000, ef_liquid=900_000, s_consistency_months=6,
        real_return_gap=0.15,
        debt_principal=0, debt_monthly_service=0, installment_monthly=0,
        installment_remaining=0, card_balance=0, card_limit=100_000,
        debt_trend_3m=-0.5,
        budget_planned=45_000, budget_overrun=0,
        limit_categories=6, limit_breached=0, cat_volatility=0.02,
        goals_active=4, goal_ontrack=1.0, goal_consistency=1.0,
        goal_required_monthly=10_000,
        beh_coverage=0.99, imp_rate=0.0, emo_rate=0.0,
        night_conc=0.0, regret_rate=0.0,
        i_cv=0.01, i_primary_share=0.4, accounts_linked=3,
        categorized_ratio=1.0,
        onboarding={"zorluk": "bilincli_olmak", "ay_sonu": "evet",
                    "takip": "duzenli", "borc_durumu": "yok",
                    "birikim_6ay": "duzenli"})
    for label, f in (("en kötü", extreme_bad), ("en iyi", extreme_good)):
        r = compute_score(f)
        check(f"sınır: {label} profil 0-100 arasında", 0 <= r.score <= 100,
              f"skor={r.score}")
        for p in r.pillars:
            if p.enabled:
                check(f"sınır: {label} — {p.key} bileşeni 0-100",
                      0 <= p.score_100 <= 100)
    check("sınır: en kötü < en iyi",
          compute_score(extreme_bad).score < compute_score(extreme_good).score)


# ── 7. Seviye bantları ───────────────────────────────────────────────────────

def t_level_bands():
    """0-100 arasındaki HER tam sayı tam olarak bir seviyeye düşmeli.

    İlk implementasyonda skor float olarak (örn. 39.6) karşılaştırılıyordu
    ve hiçbir banda düşmediği için son banda ("Güçlü") sarkıyordu:
    riskli kullanıcıya "Harika gidiyorsun" mesajı çıkıyordu.
    """
    for s in range(0, 101):
        hits = [n for lo, hi, n, _ in LEVELS if lo <= s <= hi]
        check(f"seviye: {s} tam bir banda düşer", len(hits) == 1, f"eşleşme={hits}")
    for frac in (39.4, 39.5, 39.6, 59.7, 74.5, 89.9):
        name, _ = level_of(frac)
        expected = [n for lo, hi, n, _ in LEVELS if lo <= int(round(frac)) <= hi][0]
        check(f"seviye: ondalık {frac} doğru banda düşer", name == expected,
              f"{name} != {expected}")


# ── 8. Anti-gaming ───────────────────────────────────────────────────────────

FORBIDDEN_INPUTS = [
    "streak", "login", "session", "task_completed", "gorev", "rozet",
    "badge", "engagement", "app_open", "notification_opened",
]


def t_no_engagement_inputs():
    """Uygulama kullanımı skorun GİRDİSİ olmamalı.

    v1'de "Farkındalık/Kullanım 15 puan" ve görev başına "+2 Finansal
    Sağlık Puanı" vardı. Bu, kullanıcının finansal durumunu hiç
    değiştirmeden skorunu yükseltmesine izin veriyordu — ve aslında
    ürünün retention metriğini kullanıcının sağlığı diye sunuyordu.
    """
    fields = set(Features.__dataclass_fields__.keys())
    for bad in FORBIDDEN_INPUTS:
        hit = [f for f in fields if bad in f.lower()]
        check(f"anti-gaming: '{bad}' skor girdisi değil", not hit, f"bulundu: {hit}")

    src = inspect.getsource(sys.modules["score_engine"])
    check("anti-gaming: motorda görev/seri puanı geçmiyor",
          "gorev_puani" not in src and "streak" not in src.lower())


def t_self_report_cannot_raise_pillars():
    """Kullanıcı beyanı bileşen skorlarını (p_i) etkilememeli.

    Beyan yalnızca öncül skoru ve güveni etkiler. Aksi hâlde kullanıcı
    onboarding'de yalan söyleyerek skorunu yükseltir.
    """
    good = {"zorluk": "bilincli_olmak", "ay_sonu": "evet", "takip": "duzenli",
            "borc_durumu": "yok", "birikim_6ay": "duzenli"}
    bad = {"zorluk": "borc", "ay_sonu": "hayir", "takip": "hayir",
           "borc_durumu": "asgari", "birikim_6ay": "hayir"}
    a = compute_score(base_user(onboarding=good))
    b = compute_score(base_user(onboarding=bad))
    check("anti-gaming: beyan ham skoru değiştirmez",
          abs(a.raw_score - b.raw_score) < 1e-9,
          f"{a.raw_score:.4f} vs {b.raw_score:.4f}")
    check("anti-gaming: beyan yalnızca öncülü değiştirir",
          a.prior_score != b.prior_score)

    # Ve veri biriktikçe beyanın etkisi sıfıra gitmeli.
    a90 = compute_score(base_user(onboarding=good, days_of_data=900))
    b90 = compute_score(base_user(onboarding=bad, days_of_data=900))
    early = abs(compute_score(base_user(onboarding=good, days_of_data=20)).blended_score
                - compute_score(base_user(onboarding=bad, days_of_data=20)).blended_score)
    late = abs(a90.blended_score - b90.blended_score)
    check("anti-gaming: beyanın etkisi zamanla sönümlenir", late < early,
          f"gün20 fark={early:.2f} → gün900 fark={late:.2f}")


def t_asymmetric_smoothing():
    """İyi haber yavaş, kötü haber hızlı yansımalı."""
    up = compute_score(base_user(s_deliberate=15_000, ef_liquid=120_000,
                                 s_consistency_months=6, prev_score=60))
    check("anti-gaming: yukarı hareket ±8 ile sınırlı",
          up.score - 60 <= 8, f"Δ={up.score - 60}")

    down = compute_score(base_user(days_past_due=45, min_payment_only_months=6,
                                   kmh_active=True, ef_liquid=0, prev_score=75))
    check("dürüstlük: maddi olayda aşağı sınır kalkar",
          down.smoothing["material_bypass"] is True)
    check("dürüstlük: maddi olayda düşüş 8 puandan fazla olabilir",
          75 - down.score > 8, f"Δ={down.score - 75}")


# ── 9. Adalet ────────────────────────────────────────────────────────────────

def t_confidence_change_is_not_smoothed():
    """Güven artışı yumuşatılmaz, gerçek finansal değişim yumuşatılır.

    Yumuşatma, kullanıcının FİNANSAL DURUMUNUN skoru hızlı oynatmasını
    engellemek içindir. Bizim ÖLÇÜMÜMÜZÜN düzelmesi ise onun durumundaki
    bir değişiklik değil, bizim hatamızın düzelmesidir.

    Eski davranışta anket sonrası ilk ekstresini yükleyen sağlıklı
    kullanıcı 46'dan 55'e çıkıyordu; oysa en iyi tahminimiz 72'ydi.
    17 puan saklıyorduk.
    """
    # Ham skor SABİT, yalnızca güven artıyor → yumuşatma devreye girmemeli
    onceki = compute_score(base_user(days_of_data=30))
    sonraki = compute_score(base_user(
        days_of_data=120, prev_score=onceki.score,
        prev_raw_score=onceki.raw_score, prev_confidence=onceki.confidence))
    beklenen = sonraki.blended_score
    check("güven artışı anında yansır",
          abs(sonraki.score - beklenen) <= 1.5,
          f"gösterilen {sonraki.score} vs karma {beklenen:.1f}")

    # Ham skor DEĞİŞİYOR, güven sabit → yumuşatma UYGULANMALI.
    #
    # Dikkat: acil fonu SIFIRLAMAK bir MADDİ OLAYDIR ve sınırı bilerek
    # kaldırır. Bu testin ölçmek istediği sıradan bir kötüleşme olduğu
    # için fon eşiğin (0,25 ay) üstünde tutulur.
    iyi = compute_score(base_user(days_of_data=200, s_deliberate=12_000,
                                  ef_liquid=120_000))
    kotu = compute_score(base_user(
        days_of_data=200, s_deliberate=0, ef_liquid=30_000, e_total=29_000,
        prev_score=iyi.score, prev_raw_score=iyi.raw_score,
        prev_confidence=iyi.confidence))
    check("sıradan kötüleşme maddi olay sayılmaz", not kotu.material_events,
          f"{kotu.material_events}")
    from params import P as _P
    check("gerçek finansal düşüş hâlâ yumuşatılıyor",
          iyi.score - kotu.score <= _P["s.max_hareket"] + 0.5,
          f"tek ayda {kotu.score - iyi.score} puan düştü")

    # Geriye dönük uyumluluk: önceki ham/güven yoksa eski davranış
    eski = compute_score(base_user(days_of_data=120, prev_score=40))
    check("eski çağrı biçimi bozulmadı", eski.smoothing["applied"] is True)


def t_fairness_income_neutral():
    """Skor gelir SEVİYESİNİ değil, gelirle KURULAN İLİŞKİYİ ölçmeli.

    Aynı oranlara sahip düşük ve yüksek gelirli iki kullanıcı yakın skor
    almalı. Aksi hâlde ürün "zengin olan sağlıklıdır" der ki bu hem
    yanlış hem de hedef kitlenin çoğunu dışlar.
    """
    def scaled(k):
        return base_user(
            i_net=30_000 * k, e_total=22_000 * k, e_essential=15_000 * k,
            liquid_balance=14_000 * k, s_deliberate=4_000 * k,
            ef_liquid=15_000 * k, debt_principal=20_000 * k,
            debt_monthly_service=3_000 * k, installment_monthly=1_000 * k,
            installment_remaining=12_000 * k, card_balance=9_000 * k,
            card_limit=30_000 * k, budget_planned=21_000 * k,
            budget_overrun=1_500 * k, goal_required_monthly=4_000 * k,
            i_declared=30_000 * k)

    scores = {k: compute_score(scaled(k)).blended_score for k in (0.25, 0.5, 1, 3, 8)}
    spread = max(scores.values()) - min(scores.values())
    check("adalet: skor gelir ölçeğinden bağımsız", spread < 0.5,
          "  ".join(f"×{k}={v:.2f}" for k, v in scores.items()))


def t_math_helpers():
    check("lin: uç noktalar", lin(0.10, 0.50, 0.10) == 100.0 and lin(0.50, 0.50, 0.10) == 0.0)
    check("lin: kelepçeleme", lin(-1, 0.5, 0.1) == 100.0 and lin(99, 0.5, 0.1) == 0.0)
    check("sat: k noktasında ~63", abs(sat(0.10, 0.10) - 63.2) < 0.2)
    check("sat: negatif girdi 0", sat(-0.5, 0.1) == 0.0)
    check("concave: tam noktada 100", abs(concave(6, 6) - 100.0) < 1e-9)
    check("concave: içbükey (ilk birim daha değerli)",
          concave(1, 6) - concave(0, 6) > concave(6, 6) - concave(5, 6))
    # Kelepçe DEĞERLERİ params.py'den okunur; test sabit sayı varsaymaz.
    # Aksi hâlde her parametre kararı testi kırar ve test "değişmez kural"
    # olmaktan çıkıp "mevcut değerin fotoğrafı" hâline gelir.
    from params import P as _P
    en_kotu = prior_score({"zorluk": "borc", "ay_sonu": "hayir", "takip": "hayir",
                           "borc_durumu": "asgari", "birikim_6ay": "hayir"})
    en_iyi = prior_score({"zorluk": "bilincli_olmak", "ay_sonu": "evet",
                          "takip": "duzenli", "borc_durumu": "yok",
                          "birikim_6ay": "duzenli"})
    check("öncül: alt kelepçe uygulanıyor", en_kotu == _P["prior.min"],
          f"{en_kotu} != {_P['prior.min']}")
    check("öncül: üst kelepçe aşılmıyor", en_iyi <= _P["prior.max"])
    check("öncül: iyi cevap kötüden yüksek", en_iyi > en_kotu)


TESTS = [t_determinism, t_monotonicity, t_continuity,
         t_missing_data_never_punishes, t_absent_balance_is_not_zero,
         t_undefined_ratios_disable_submetrics,
         t_smoothing_anchor_uses_measurement, t_pillar_weights_come_from_params,
         t_confidence_blending, t_bounds,
         t_level_bands, t_no_engagement_inputs,
         t_self_report_cannot_raise_pillars, t_asymmetric_smoothing,
         t_confidence_change_is_not_smoothed,
         t_fairness_income_neutral, t_math_helpers]


if __name__ == "__main__":
    print(f"NAKITIO SKOR MODELİ — DEĞİŞMEZ KURAL TESTLERİ (model {MODEL_VERSION})")
    print("=" * 78)
    for t in TESTS:
        before = len(FAILS)
        t()
        status = "FAIL" if len(FAILS) > before else "ok"
        doc = (t.__doc__ or "").strip().split("\n")[0]
        print(f"  [{status:>4}] {t.__name__:<38} {doc[:32]}")
    print("=" * 78)
    if FAILS:
        print(f"{PASSES} geçti, {len(FAILS)} KIRILDI:\n")
        for f in FAILS:
            print(f"  ✗ {f}")
        sys.exit(1)
    print(f"{PASSES} kontrolün tamamı geçti.")
