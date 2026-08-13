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
         t_missing_data_never_punishes, t_confidence_blending, t_bounds,
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
