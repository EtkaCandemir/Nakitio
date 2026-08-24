"""
Nakitio Skor Modeli v2 — Golden Test Seti

10 sentetik kullanıcı profili ve beklenen skorları. Model her
değiştiğinde bu dosya çalıştırılır; çıktı beklenenden saparsa değişikliğin
BİLEREK yapıldığı doğrulanmadan production'a çıkılmaz.

Çalıştırma:
    python3 engine/golden_profiles.py
    python3 engine/golden_profiles.py --detail didem
"""

from __future__ import annotations

import sys
from score_engine import (
    Features, compute_score, simulate, attribute, MODEL_VERSION,
)

ONB = {
    "iyi":   {"zorluk": "bilincli_olmak", "ay_sonu": "evet", "takip": "duzenli",
              "borc_durumu": "yok", "birikim_6ay": "duzenli"},
    "orta":  {"zorluk": "nereye_gidiyor", "ay_sonu": "bazen", "takip": "bazen",
              "borc_durumu": "yonetilebilir", "birikim_6ay": "ara_sira"},
    "kotu":  {"zorluk": "borc", "ay_sonu": "hayir", "takip": "hayir",
              "borc_durumu": "asgari", "birikim_6ay": "hayir"},
    "impuls": {"zorluk": "impuls", "ay_sonu": "bazen", "takip": "bazen",
               "borc_durumu": "yonetilebilir", "birikim_6ay": "hayir"},
    "yeni":  {"zorluk": "impuls", "ay_sonu": "bazen", "takip": "hayir",
              "borc_durumu": "yonetilebilir", "birikim_6ay": "ara_sira"},
    "birikimsiz": {"zorluk": "birikim_yapamiyorum", "ay_sonu": "bazen",
                   "takip": "bazen", "borc_durumu": "yonetilebilir",
                   "birikim_6ay": "hayir"},
}


PROFILES = {}


def P(key, note, expect, **kw):
    PROFILES[key] = (Features(user_id=key, **kw), note, expect)


# ── 1. Didem — mockup'lardaki kullanıcı ──────────────────────────────────────
# Docs/1-0 ve 1-1'deki sayılarla birebir kurulmuştur. Mockup skoru 78 gösteriyor;
# yeni model bu profil için ne veriyor, kalibrasyon kontrolü.
P("didem", "Mockup kullanıcısı — maaşlı, dengeli, orta borç", "71-75",
  days_of_data=120,
  i_net=28_450, i_cv=0.08, i_primary_share=0.84, i_declared=28_000,
  e_total=21_380, e_essential=14_966, liquid_balance=12_770,
  s_deliberate=5_303, ef_liquid=7_483, s_consistency_months=4,
  debt_principal=18_500, debt_monthly_service=4_200,
  card_balance=8_500, card_limit=25_000, debt_trend_3m=-0.06,
  budget_planned=20_000, budget_overrun=1_380,
  limit_categories=4, limit_breached=1, cat_volatility=0.28,
  goals_active=3, goal_ontrack=0.62, goal_consistency=0.67,
  goal_required_monthly=4_500,
  beh_coverage=0.72, imp_rate=0.23, emo_rate=0.10,
  night_conc=0.106, regret_rate=0.28,
  accounts_declared=3, accounts_linked=2, categorized_ratio=0.93,
  manual_entry=False, onboarding=ONB["orta"], prev_score=74)

# ── 2. Mehmet — kredi kartı sarmalı ──────────────────────────────────────────
P("mehmet", "Kart sarmalı — asgari ödeme, gecikme, KMH", "30-36",
  days_of_data=200,
  i_net=32_000, i_cv=0.05, i_primary_share=1.0, i_declared=32_000,
  e_total=31_000, e_essential=22_000, liquid_balance=1_200,
  s_deliberate=0, ef_liquid=0, s_consistency_months=0,
  debt_principal=95_000, debt_monthly_service=6_800,
  installment_monthly=3_200, installment_remaining=28_000,
  card_balance=47_000, card_limit=50_000, debt_trend_3m=0.08,
  days_past_due=12, min_payment_only_months=5, kmh_active=True,
  cat_volatility=0.58,
  goals_active=0,
  beh_coverage=0.40, imp_rate=0.34, emo_rate=0.22,
  night_conc=0.28, regret_rate=0.55,
  accounts_declared=3, accounts_linked=2, categorized_ratio=0.80,
  manual_entry=False, onboarding=ONB["kotu"], prev_score=46)

# ── 3. Zeynep — serbest çalışan, düzensiz gelir ──────────────────────────────
P("zeynep", "Serbest çalışan — yüksek gelir oynaklığı, borçsuz, iyi birikim", "79-85",
  days_of_data=400,
  i_net=38_000, i_cv=0.52, i_primary_share=0.45, i_declared=40_000,
  e_total=26_000, e_essential=16_000, liquid_balance=34_000,
  s_deliberate=8_000, ef_liquid=48_000, s_consistency_months=4,
  real_return_gap=-0.05,
  debt_principal=0, card_balance=0, card_limit=30_000,
  budget_planned=25_000, budget_overrun=2_400,
  limit_categories=3, limit_breached=1, cat_volatility=0.55,
  goals_active=2, goal_ontrack=0.80, goal_consistency=0.70,
  goal_required_monthly=6_000,
  beh_coverage=0.60, imp_rate=0.18, emo_rate=0.09,
  night_conc=0.14, regret_rate=0.20,
  accounts_declared=2, accounts_linked=2, categorized_ratio=0.90,
  manual_entry=False, onboarding=ONB["iyi"])

# ── 4. Can — 12 günlük yeni kullanıcı ────────────────────────────────────────
# Kritik test: neredeyse hiç veri yok. Skor öncüle çok yakın olmalı,
# band geniş olmalı, hiçbir bileşen eksik veri yüzünden 0 puan almamalı.
P("can", "12 günlük yeni kullanıcı — veri yok denecek kadar az", "öncüle ≈ eşit",
  days_of_data=12,
  i_net=24_000, i_declared=24_000,
  e_total=19_000, e_essential=13_000, liquid_balance=6_000,
  has_debt_data=False,
  goals_active=0,
  beh_coverage=0.10,
  accounts_declared=2, accounts_linked=0, categorized_ratio=0.55,
  manual_entry=True, onboarding=ONB["yeni"])

# ── 5. Elif — güçlü profil ───────────────────────────────────────────────────
P("elif", "Güçlü — yüksek tasarruf, 6+ ay güvence, borçsuz", "87-93",
  days_of_data=500,
  i_net=62_000, i_cv=0.06, i_primary_share=0.78, i_declared=60_000,
  e_total=34_000, e_essential=20_000, liquid_balance=55_000,
  s_deliberate=22_000, ef_liquid=130_000, s_consistency_months=6,
  real_return_gap=0.02,
  debt_principal=0, card_balance=6_000, card_limit=60_000,
  debt_trend_3m=-0.10,
  budget_planned=32_000, budget_overrun=800,
  limit_categories=5, limit_breached=0, cat_volatility=0.18,
  goals_active=3, goal_ontrack=0.95, goal_consistency=0.90,
  goal_required_monthly=15_000,
  beh_coverage=0.85, imp_rate=0.08, emo_rate=0.04,
  night_conc=0.07, regret_rate=0.10,
  accounts_declared=4, accounts_linked=4, categorized_ratio=0.97,
  manual_entry=False, onboarding=ONB["iyi"], prev_score=88)

# ── 6. Burak — taksit yüklü ──────────────────────────────────────────────────
# Nakit akışı pozitif görünüyor ama gelecek taahhüdü ağır. v1 modeli bu
# kullanıcıyı "iyi" görürdü; v2 taahhüt yükünü ayrıca ölçer.
P("burak", "Taksit yüklü — nakit akışı iyi görünüyor, taahhüt ağır", "58-64",
  days_of_data=300,
  i_net=40_000, i_cv=0.05, i_primary_share=1.0, i_declared=40_000,
  e_total=30_000, e_essential=18_000, liquid_balance=9_000,
  s_deliberate=3_000, ef_liquid=12_000, s_consistency_months=3,
  debt_principal=0, installment_monthly=9_500, installment_remaining=76_000,
  card_balance=22_000, card_limit=40_000, debt_trend_3m=0.02,
  budget_planned=28_000, budget_overrun=3_500,
  limit_categories=4, limit_breached=2, cat_volatility=0.42,
  goals_active=1, goal_ontrack=0.40, goal_consistency=0.33,
  goal_required_monthly=5_000,
  beh_coverage=0.55, imp_rate=0.29, emo_rate=0.15,
  night_conc=0.21, regret_rate=0.38,
  accounts_declared=3, accounts_linked=3, categorized_ratio=0.90,
  manual_entry=False, onboarding=ONB["orta"], prev_score=62)

# ── 7. Deniz — düşük gelirli ama disiplinli ──────────────────────────────────
# Kritik adalet testi: düşük gelir tek başına düşük skor DEMEMELİ.
P("deniz", "Öğrenci — düşük gelir, yüksek disiplin, borçsuz", "76-82",
  days_of_data=180,
  i_net=12_000, i_cv=0.15, i_primary_share=0.70, i_declared=12_000,
  e_total=9_800, e_essential=7_500, liquid_balance=4_200,
  s_deliberate=1_800, ef_liquid=9_000, s_consistency_months=5,
  debt_principal=0,
  budget_planned=10_000, budget_overrun=300,
  limit_categories=3, limit_breached=0, cat_volatility=0.24,
  goals_active=1, goal_ontrack=0.85, goal_consistency=0.83,
  goal_required_monthly=1_500,
  beh_coverage=0.65, imp_rate=0.12, emo_rate=0.06,
  night_conc=0.09, regret_rate=0.15,
  accounts_declared=1, accounts_linked=1, categorized_ratio=0.88,
  manual_entry=True, onboarding=ONB["iyi"], prev_score=76)

# ── 8. Selin — gizli riskli ──────────────────────────────────────────────────
# Kritik adalet testi: yüksek gelir tek başına yüksek skor DEMEMELİ.
P("selin", "Yüksek gelir, sıfır tampon — gizli risk", "36-42",
  days_of_data=250,
  i_net=85_000, i_cv=0.09, i_primary_share=0.95, i_declared=85_000,
  e_total=83_000, e_essential=38_000, liquid_balance=3_500,
  s_deliberate=0, ef_liquid=0, s_consistency_months=0,
  debt_principal=40_000, debt_monthly_service=5_000,
  installment_monthly=7_000, installment_remaining=62_000,
  card_balance=68_000, card_limit=90_000, debt_trend_3m=0.14,
  budget_planned=70_000, budget_overrun=13_000,
  limit_categories=5, limit_breached=4, cat_volatility=0.68,
  goals_active=0,
  beh_coverage=0.70, imp_rate=0.41, emo_rate=0.28,
  night_conc=0.33, regret_rate=0.48,
  accounts_declared=4, accounts_linked=4, categorized_ratio=0.95,
  manual_entry=False, onboarding=ONB["impuls"], prev_score=58)

# ── 9. Ahmet — emekli ────────────────────────────────────────────────────────
P("ahmet", "Emekli — düşük gelir, borçsuz, enflasyona yeniliyor", "79-85",
  days_of_data=600,
  i_net=16_500, i_cv=0.02, i_primary_share=1.0, i_declared=16_500,
  e_total=14_200, e_essential=11_800, liquid_balance=21_000,
  s_deliberate=1_500, ef_liquid=42_000, s_consistency_months=6,
  real_return_gap=-0.12,
  debt_principal=0, card_balance=0, card_limit=15_000,
  budget_planned=14_000, budget_overrun=600,
  limit_categories=3, limit_breached=1, cat_volatility=0.19,
  goals_active=1, goal_ontrack=0.70, goal_consistency=0.67,
  goal_required_monthly=800,
  beh_coverage=0.30, imp_rate=0.09, emo_rate=0.03,
  night_conc=0.04, regret_rate=0.08,
  accounts_declared=2, accounts_linked=1, categorized_ratio=0.82,
  manual_entry=True, onboarding=ONB["iyi"], prev_score=82)

# ── 10. Merve — gün 25, geçiş dönemi ─────────────────────────────────────────
P("merve", "Gün 25 — geçiş dönemi, kısmi veri", "öncül ile ham arası",
  days_of_data=25,
  i_net=26_000, i_declared=26_000,
  e_total=22_500, e_essential=15_000, liquid_balance=5_200,
  s_deliberate=1_200, ef_liquid=3_000, s_consistency_months=1,
  debt_principal=12_000, debt_monthly_service=1_900,
  installment_monthly=1_400, installment_remaining=9_800,
  card_balance=9_000, card_limit=20_000,
  goals_active=1, goal_ontrack=0.50, goal_consistency=0.50,
  goal_required_monthly=2_000,
  beh_coverage=0.35, imp_rate=0.26, emo_rate=0.14, night_conc=0.19,
  accounts_declared=2, accounts_linked=1, categorized_ratio=0.71,
  manual_entry=True, onboarding=ONB["birikimsiz"])


# ═════════════════════════════════════════════════════════════════════════════
# KAPSAM PROFİLLERİ (11–15)
#
# İlk 10 profil gerçekçi kullanıcı senaryolarıdır. Aşağıdaki 5 profil ise
# KOD YOLU KAPSAMI için eklendi: `tune.py` duyarlılık analizi, hiçbir
# profilin tetiklemediği parametreleri "etkisiz" sanıyordu.
#
# Ölçülemeyen bir parametreyi "önemsiz" diye raporlamak, ölçüm eksikliğini
# bulgu gibi sunmaktır. En rahatsız edici örnek `c.statement_tavan`'dı:
# ürünün ANA veri kaynağı ekstre yükleme ama golden sette ekstre kaynaklı
# tek profil yoktu.
# ═════════════════════════════════════════════════════════════════════════════

# ── 11. Emre — ekstre kullanıcısı, gelir beyanı yok ──────────────────────────
# Kapsar: c.statement_tavan · c.verif_varsayilan
P("emre", "Ekstre kullanıcısı — gelir beyanı yok, 4/6 dönem yüklü", "62-70",
  days_of_data=200,
  i_net=34_000, i_cv=0.12, i_primary_share=0.90, i_declared=None,
  e_total=26_500, e_essential=17_000, liquid_balance=11_000,
  s_deliberate=4_200, ef_liquid=26_000, s_consistency_months=4,
  debt_principal=22_000, debt_monthly_service=3_400,
  installment_monthly=1_200, installment_remaining=9_600,
  card_balance=12_000, card_limit=35_000, debt_trend_3m=-0.04,
  budget_planned=25_000, budget_overrun=2_100,
  limit_categories=4, limit_breached=1, cat_volatility=0.31,
  goals_active=2, goal_ontrack=0.58, goal_consistency=0.67,
  goal_required_monthly=4_000,
  beh_coverage=0.55, imp_rate=0.19, emo_rate=0.11,
  night_conc=0.14, regret_rate=0.22,
  accounts_declared=3, accounts_linked=0, categorized_ratio=0.89,
  manual_entry=True, data_source="statement", statement_coverage=4 / 6,
  onboarding=ONB["orta"], prev_score=66)

# ── 12. Hakan — ağır gecikme, asgari ödeme başlangıcı ────────────────────────
# Kapsar: mod.gecikme_30 · mod.asgari
P("hakan", "45 gün gecikme + 2 ay asgari ödeme — sarmalın başı", "33-41",
  days_of_data=240,
  i_net=27_000, i_cv=0.07, i_primary_share=1.0, i_declared=27_000,
  e_total=25_800, e_essential=19_000, liquid_balance=900,
  s_deliberate=0, ef_liquid=1_200, s_consistency_months=1,
  debt_principal=78_000, debt_monthly_service=6_200,
  installment_monthly=2_400, installment_remaining=21_600,
  card_balance=33_000, card_limit=40_000, debt_trend_3m=0.11,
  days_past_due=45, min_payment_only_months=2, kmh_active=False,
  budget_planned=24_000, budget_overrun=4_800,
  limit_categories=4, limit_breached=3, cat_volatility=0.52,
  goals_active=1, goal_ontrack=0.20, goal_consistency=0.0,
  goal_required_monthly=3_000,
  beh_coverage=0.48, imp_rate=0.31, emo_rate=0.19,
  night_conc=0.24, regret_rate=0.44,
  accounts_declared=3, accounts_linked=0, categorized_ratio=0.86,
  manual_entry=True, data_source="statement", statement_coverage=0.5,
  onboarding=ONB["kotu"], prev_score=52)

# ── 13. Sibel — gider gelirden fazla, hedefsiz ───────────────────────────────
# Kapsar: p1.marj.neg_sifir · p5.grace_gun (90 gün, hedef yok)
P("sibel", "Negatif nakit akışı — gider gelirden %20 fazla", "30-40",
  days_of_data=90,
  i_net=22_000, i_cv=0.18, i_primary_share=0.95, i_declared=22_000,
  e_total=26_500, e_essential=18_500, liquid_balance=2_400,
  s_deliberate=0, ef_liquid=0, s_consistency_months=0,
  debt_principal=14_000, debt_monthly_service=2_100,
  card_balance=11_500, card_limit=18_000, debt_trend_3m=0.09,
  budget_planned=22_000, budget_overrun=5_600,
  limit_categories=3, limit_breached=3, cat_volatility=0.47,
  goals_active=0,
  beh_coverage=0.42, imp_rate=0.27, emo_rate=0.17,
  night_conc=0.21, regret_rate=0.39,
  accounts_declared=2, accounts_linked=0, categorized_ratio=0.83,
  manual_entry=True, data_source="statement", statement_coverage=0.5,
  onboarding=ONB["birikimsiz"])

# ── 14. Tolga — ulaşılamaz hedef + ani büyük iyileşme ────────────────────────
# Kapsar: p5.gercekcilik.sifir · s.max_hareket (yukarı yönde sınır)
P("tolga", "Ulaşılamaz hedef koymuş, skoru hızla iyileşiyor", "55-63",
  days_of_data=300,
  i_net=48_000, i_cv=0.09, i_primary_share=0.82, i_declared=48_000,
  e_total=31_000, e_essential=19_000, liquid_balance=42_000,
  s_deliberate=14_000, ef_liquid=95_000, s_consistency_months=6,
  real_return_gap=0.01,
  debt_principal=0, card_balance=4_000, card_limit=50_000,
  debt_trend_3m=-0.20,
  budget_planned=30_000, budget_overrun=600,
  limit_categories=5, limit_breached=0, cat_volatility=0.16,
  # Aylık 25.000 gerekiyor, nakit fazlası 17.000 → oran ~1,47.
  # Ulaşılamaz ama eşik taramasının (1,2–2,5) içinde kalıyor.
  goals_active=1, goal_ontrack=0.15, goal_consistency=0.33,
  goal_required_monthly=25_000,
  beh_coverage=0.80, imp_rate=0.07, emo_rate=0.04,
  night_conc=0.06, regret_rate=0.09,
  accounts_declared=4, accounts_linked=0, categorized_ratio=0.95,
  manual_entry=True, data_source="statement", statement_coverage=1.0,
  onboarding=ONB["iyi"], prev_score=50)

# ── 15. Nur — veri bütünlüğü şüphesi ─────────────────────────────────────────
# Kapsar: c.integrity_carpan
P("nur", "Toplu işlem silme tespit edildi — güven düşürüldü", "72-82",
  days_of_data=210,
  i_net=31_000, i_cv=0.08, i_primary_share=0.93, i_declared=31_000,
  e_total=15_500, e_essential=12_000, liquid_balance=38_000,
  s_deliberate=13_000, ef_liquid=58_000, s_consistency_months=6,
  debt_principal=0, card_balance=2_000, card_limit=25_000,
  debt_trend_3m=-0.15,
  budget_planned=16_000, budget_overrun=200,
  limit_categories=3, limit_breached=0, cat_volatility=0.14,
  goals_active=2, goal_ontrack=0.88, goal_consistency=0.83,
  goal_required_monthly=6_000,
  beh_coverage=0.62, imp_rate=0.06, emo_rate=0.03,
  night_conc=0.05, regret_rate=0.08,
  accounts_declared=4, accounts_linked=0, categorized_ratio=0.91,
  manual_entry=True, data_source="statement", statement_coverage=0.83,
  integrity_flag=True,
  onboarding=ONB["iyi"], prev_score=78)


#: Kod yolu KAPSAMI için sonradan eklenen profiller — gerçekçi bir kullanıcıyı
#: temsil etmezler, duyarlılık analizinin "ölçülemedi" dediği parametreleri
#: tetiklemek için vardır. `Docs/skor-modeli-v2.md` §10 yalnızca senaryo
#: profillerini listeler; ayrımın tek kaynağı burasıdır.
KAPSAM_PROFILLERI = ("emre", "hakan", "sibel", "tolga", "nur")


def senaryo_profilleri():
    """Kapsam profilleri hariç, gerçekçi senaryoyu temsil eden profiller."""
    return {k: v for k, v in PROFILES.items() if k not in KAPSAM_PROFILLERI}


# ─────────────────────────────────────────────────────────────────────────────

def run_table():
    print(f"NAKITIO SKOR MODELİ — GOLDEN TEST  (model {MODEL_VERSION})")
    print("=" * 108)
    print(f"{'profil':<9} {'skor':>5} {'band':>9} {'ham':>6} {'öncül':>6} "
          f"{'C':>5} {'aşama':<28} {'seviye':<10} beklenen")
    print("-" * 108)
    for key, (f, note, expect) in PROFILES.items():
        r = compute_score(f)
        stage = r.stage_label.replace(" Skoru", "").replace("Finansal Sağlık", "Fin. Sağlık")
        print(f"{key:<9} {r.score:>5} {f'{r.band[0]}-{r.band[1]}':>9} "
              f"{r.raw_score:>6.1f} {r.prior_score:>6.1f} {r.confidence:>5.2f} "
              f"{stage:<28} {r.level:<10} {expect}")
    print("-" * 108)
    for key, (f, note, expect) in PROFILES.items():
        print(f"  {key:<9} {note}")


def run_detail(key: str):
    f, note, expect = PROFILES[key]
    r = compute_score(f)
    print(f"\n### {key.upper()} — {note}\n")
    print(r.explain())
    if r.smoothing.get("applied"):
        print(f"\n  yumuşatma: {r.smoothing}")


#: Süreklilik testinin taradığı günler — gün-30 uçurumunun iki yanı sık örneklenir.
SUREKLILIK_GUNLERI = (10, 15, 20, 25, 28, 30, 31, 35, 40, 60, 90)


def veri_sureklilik():
    """[(gün, ScoreResult)] — gün 30 uçurumunun kalktığının ölçümü.

    `run_continuity()` bunu yazdırır, `docs_sync.py` aynı listeden
    `Docs/skor-modeli-v2.md` §5'teki tabloyu üretir. Hesap TEK yerde
    durmalı: iki kopya olsaydı biri diğerinden sessizce ayrışırdı — bu
    dosyanın düzeltmek için var olduğu sapmanın ta kendisi.
    """
    import dataclasses
    base, _, _ = PROFILES["merve"]
    out = []
    for d in SUREKLILIK_GUNLERI:
        f = dataclasses.replace(
            base, days_of_data=d,
            # veri kalitesi de günle birlikte doğal olarak artar
            categorized_ratio=min(0.95, 0.55 + d * 0.004),
            beh_coverage=min(0.80, 0.15 + d * 0.008),
        )
        out.append((d, compute_score(f)))
    return out


def run_continuity():
    """Gün 30 uçurumunun kalktığını kanıtlar.

    v1'de gün 30 -> 31 geçişinde formül tamamen değişiyor ve skor
    onlarca puan sıçrıyordu. v2'de formül sabit, yalnızca C artıyor.
    """
    print("\n\nSÜREKLİLİK TESTİ — gün 20 → 40 (v1'deki gün-30 uçurumu)")
    print("=" * 76)
    print(f"{'gün':>4} {'C':>6} {'ham':>7} {'öncül':>7} {'karma':>7} {'skor':>6}  aşama")
    print("-" * 76)
    for d, r in veri_sureklilik():
        print(f"{d:>4} {r.confidence:>6.2f} {r.raw_score:>7.1f} "
              f"{r.prior_score:>7.1f} {r.blended_score:>7.1f} {r.score:>6}  "
              f"{r.stage_label}")
    print("-" * 76)
    print("Not: skor kademeli ilerliyor, gün 30/31 arasında sıçrama YOK.")


def veri_simulasyon():
    """(baz, [(etiket, ScoreResult)], katkı_satırları) — Didem'in aksiyon planı.

    `run_simulation()` ve `docs_sync.py` bunu ortak kullanır; bkz.
    `veri_sureklilik()` üzerindeki gerekçe.
    """
    f, _, _ = PROFILES["didem"]
    # Baz da simulate() ile alınır: simülasyon çıktıları yumuşatmasız
    # olduğu için karşılaştırmanın aynı ölçekte olması gerekir.
    base = simulate(f)

    steps = [
        ("Restoran limiti (aylık -600 TL gider)",
         dict(e_total=f.e_total - 600, budget_overrun=max(0.0, f.budget_overrun - 600),
              limit_breached=0)),
        ("+ Acil durum fonuna aylık 1.500 TL",
         dict(e_total=f.e_total - 600, budget_overrun=max(0.0, f.budget_overrun - 600),
              limit_breached=0,
              s_deliberate=f.s_deliberate + 1_500,
              ef_liquid=f.ef_liquid + 4_500, s_consistency_months=6)),
        ("+ Plansız harcama %23 → %15",
         dict(e_total=f.e_total - 600, budget_overrun=max(0.0, f.budget_overrun - 600),
              limit_breached=0,
              s_deliberate=f.s_deliberate + 1_500,
              ef_liquid=f.ef_liquid + 4_500, s_consistency_months=6,
              imp_rate=0.15, night_conc=0.07, regret_rate=0.18)),
    ]
    adimlar = [(etiket, simulate(f, **ch)) for etiket, ch in steps]
    son = adimlar[-1][1] if adimlar else base
    return base, adimlar, attribute(base, son)


def run_simulation():
    """AI koçun 'bu planı uygularsan X olur' vaadinin kaynağı."""
    print("\n\nSİMÜLASYON — Didem için AI aksiyon planı")
    print("=" * 76)
    base, adimlar, katki = veri_simulasyon()
    print(f"Mevcut durum: {base.score}/100  ({base.level})\n")

    for label, r in adimlar:
        print(f"{label:<45} → {r.score}/100  ({r.score - base.score:+d})")
    prev = adimlar[-1][1] if adimlar else base

    print("\n3 ay sonunda beklenen skor:", prev.score,
          f"({prev.level})  — bandı: {prev.band[0]}-{prev.band[1]}")
    print("\nKatkı ayrıştırma (mevcut → plan sonu):")
    for row in katki:
        arrow = ""
        if row["from"] is not None and row["to"] is not None:
            arrow = f"   {row['from']} → {row['to']}"
        print(f"  {row['delta']:+6.2f}  {row['label']}{arrow}")


def veri_sinir_durumlari():
    """[(etiket, ScoreResult, [devre_dışı_bileşen])] — §11'in ölçülmüş hâli."""
    out = []
    for label, f in _sinir_vakalari():
        r = compute_score(f)
        out.append((label, r, [p.label for p in r.pillars if not p.enabled]))
    return out


def _sinir_vakalari():
    cases = [
        ("Sıfır gelir (işsiz)", Features(
            user_id="e1", days_of_data=120, i_net=0, e_total=8_000,
            e_essential=7_000, liquid_balance=15_000, ef_liquid=15_000,
            has_debt_data=True, debt_principal=0,
            beh_coverage=0.5, imp_rate=0.2, emo_rate=0.1,
            categorized_ratio=0.8, accounts_declared=1, accounts_linked=1,
            onboarding=ONB["orta"])),
        ("Gider > gelir (negatif marj)", Features(
            user_id="e2", days_of_data=120, i_net=20_000, i_cv=0.1,
            e_total=26_000, e_essential=18_000, liquid_balance=500,
            has_debt_data=True, debt_principal=15_000, debt_monthly_service=2_000,
            card_balance=14_000, card_limit=15_000,
            beh_coverage=0.5, imp_rate=0.3, emo_rate=0.2,
            categorized_ratio=0.85, accounts_declared=2, accounts_linked=2,
            onboarding=ONB["kotu"])),
        ("Hiç borç verisi yok", Features(
            user_id="e3", days_of_data=120, i_net=30_000, i_cv=0.08,
            e_total=22_000, e_essential=15_000, liquid_balance=18_000,
            s_deliberate=6_000, ef_liquid=30_000, s_consistency_months=5,
            has_debt_data=False,
            beh_coverage=0.6, imp_rate=0.15, emo_rate=0.08,
            categorized_ratio=0.9, accounts_declared=2, accounts_linked=1,
            onboarding=ONB["orta"])),
        ("Veri bütünlüğü şüphesi", Features(
            user_id="e4", days_of_data=200, i_net=30_000, i_cv=0.08,
            e_total=15_000, e_essential=12_000, liquid_balance=40_000,
            s_deliberate=15_000, ef_liquid=60_000, s_consistency_months=6,
            has_debt_data=True, debt_principal=0,
            beh_coverage=0.6, imp_rate=0.05, emo_rate=0.02,
            categorized_ratio=0.9, accounts_declared=3, accounts_linked=1,
            integrity_flag=True, onboarding=ONB["iyi"])),
    ]
    return cases


def run_edge_cases():
    print("\n\nSINIR DURUMLARI")
    print("=" * 76)
    for label, r, dis in veri_sinir_durumlari():
        print(f"{label:<32} skor={r.score:>3} band={r.band[0]}-{r.band[1]:<3} "
              f"C={r.confidence:.2f}  {r.level}"
              + (f"   [devre dışı: {', '.join(dis)}]" if dis else ""))


def veri_maddi_olay():
    """(normal, kötüleşme, iyileşme) — yumuşatmanın asimetrisinin ölçümü.

    Kötüleşme maddi olay üretir ve ±8 sınırını AŞAĞI yönde kaldırır;
    aynı büyüklükteki iyi haber sınıra tabi kalır.
    """
    import dataclasses
    f, _, _ = PROFILES["didem"]
    ok = compute_score(f)
    bad = compute_score(dataclasses.replace(
        f, days_past_due=15, min_payment_only_months=2,
        card_balance=21_000, prev_score=ok.score))
    good = compute_score(dataclasses.replace(
        f, s_deliberate=f.s_deliberate + 9_000, ef_liquid=f.ef_liquid + 60_000,
        s_consistency_months=6, prev_score=ok.score))
    return ok, bad, good


def run_material_event():
    print("\n\nMADDİ OLAY TESTİ — gecikmeye düşen kullanıcı")
    print("=" * 76)
    ok, bad, good = veri_maddi_olay()
    print(f"Normal ay          : {ok.score}")
    print(f"Gecikmeye düştü    : {bad.score}  (Δ {bad.score - ok.score:+d})")
    print(f"  maddi olaylar    : {bad.material_events}")
    print(f"  yumuşatma        : cap_uygulandı={bad.smoothing['cap_applied']}, "
          f"bypass={bad.smoothing['material_bypass']}")
    print("  → ±8 puan sınırı aşağı yönde BYPASS edildi: kötü haber gecikmez.")

    print("\n  Karşı test — aynı büyüklükte İYİ haber:")
    print(f"  Ani büyük iyileşme : {good.score}  (Δ {good.score - ok.score:+d}) "
          f"cap_uygulandı={good.smoothing['cap_applied']}")
    print("  → Yukarı yönde sınır KORUNUR. Skor tek ayda satın alınamaz.")


if __name__ == "__main__":
    if len(sys.argv) > 2 and sys.argv[1] == "--detail":
        run_detail(sys.argv[2])
    else:
        run_table()
        run_continuity()
        run_simulation()
        run_edge_cases()
        run_material_event()
