"""
Nakitio — Uçtan uca fixture: HAM İŞLEMLER → Features → Skor

`Docs/1-0 anasayfa.docx` ve `1-1 anasayfa-finansal sağlık raporu.docx`
mockup'larındaki kullanıcının (Didem) 5 aylık ham işlem geçmişi sentetik
olarak üretilir ve tüm hattan geçirilir.

Amaç kalibrasyon değil, HATTIN BAĞLANDIĞINI KANITLAMAK: ham banka
hareketinden skora giden yolda her normalizasyon kuralının gerçekten
çalıştığını, elle kurulmuş `Features` nesnesine ihtiyaç kalmadığını
göstermek.

Fixture bilerek şunları içerir (her biri bir N kuralını tetikler):
  · hesaplar arası birikim transferleri        → N1
  · kredi kartı ekstre ödemeleri               → N2
  · iki ayrı taksit planı                      → N3
  · yıllık kasko primi (tek seferde ödenmiş)   → N4
  · dönemler arası TÜFE farkı                  → N5
  · iade edilmiş bir giyim alışverişi          → N7
  · olağandışı büyük tek seferlik gelir        → N8

Çalıştırma:  python3 engine/fixture_didem.py
"""

from __future__ import annotations

import random
from datetime import date, datetime, timedelta
from typing import Dict, List

from data_model import (
    Account, AccountType, BehaviorTag, Budget, CPISeries, Goal,
    IncomeDeclaration, Liability, RawData, Transaction,
)
from normalize import build_features, windows
from score_engine import compute_score

AS_OF = date(2026, 7, 31)
RNG = random.Random(20260731)          # deterministik

_seq = 0


def _tid(prefix: str) -> str:
    global _seq
    _seq += 1
    return f"{prefix}{_seq:04d}"


def _spread(total: float, n: int, rng: random.Random) -> List[float]:
    """`total` tutarını n işleme dağıtır; toplam korunur."""
    w = [rng.uniform(0.55, 1.65) for _ in range(n)]
    s = sum(w)
    out = [round(total * x / s, 2) for x in w]
    out[-1] = round(total - sum(out[:-1]), 2)
    return out


def _dt(w_start: date, rng: random.Random, night: bool = False) -> datetime:
    d = w_start + timedelta(days=rng.randint(0, 29))
    hour = rng.choice([20, 21, 22, 23]) if night else rng.randint(8, 19)
    return datetime(d.year, d.month, d.day, hour, rng.randint(0, 59))


# ─────────────────────────────────────────────────────────────────────────────
# TÜFE serisi (sentetik — üretimde TÜİK)
# ─────────────────────────────────────────────────────────────────────────────

def _cpi() -> CPISeries:
    groups = {"genel": 0.022, "gida": 0.030, "lokanta": 0.028, "ulastirma": 0.019,
              "konut": 0.024, "giyim": 0.012, "haberlesme": 0.010, "saglik": 0.021,
              "egitim": 0.015, "eglence": 0.020, "ev_esyasi": 0.018,
              "alkol_tutun": 0.035, "cesitli": 0.022}
    idx: Dict[str, Dict[str, float]] = {}
    for g, rate in groups.items():
        series, v = {}, 100.0
        for m in range(1, 13):
            series[f"2026-{m:02d}"] = round(v, 3)
            v *= (1 + rate)
        for m in range(1, 13):
            series[f"2027-{m:02d}"] = round(v, 3)
            v *= (1 + rate)
        idx[g] = series
    return CPISeries(index=idx)


# ─────────────────────────────────────────────────────────────────────────────
# Kategori şablonu — mockup'taki Gider Kategorileri kırılımına sadık
# ─────────────────────────────────────────────────────────────────────────────
#
# NOT: mockup'ın kategori listesinde KONUT/KİRA yoktur. Türkiye'de bu
# gerçekçi değildir ve `e_essential`'ı sistematik olarak düşürür.
# Fixture mockup'a sadık kalır; bulgu raporlanır (bkz. çıktı sonu).

MONTHLY = [
    # (kategori, tutar, işlem adedi, gece olasılığı, merchant havuzu)
    ("market",     5_980, 11, 0.05, ["MIGROS TIC A.S IST", "A101 YENI MAGAZA",
                                     "BIM BIRLESIK MAGAZA", "SOK MARKET"]),
    ("restoran",   4_275, 14, 0.45, ["STARBUCKS KANYON", "YEMEKSEPETI ONLINE",
                                     "GETIR YEMEK", "KAHVE DUNYASI", "DOMINO PIZZA"]),
    ("ulasim",     3_205,  9, 0.10, ["ISTANBULKART DOLUM", "SHELL PETROL",
                                     "BITAKSI ODEME", "OPET AKARYAKIT"]),
    ("faturalar",  2_350,  3, 0.00, ["IGDAS DOGALGAZ", "BEDAS ELEKTRIK", "ISKI SU FATURA"]),
    ("iletisim",     700,  1, 0.00, ["TURKCELL FATURA"]),
    ("giyim",      1_190,  3, 0.20, ["ZARA AKMERKEZ", "LC WAIKIKI", "DEFACTO"]),
    ("eglence",    1_180,  4, 0.55, ["CINEMAXIMUM", "SPOTIFY PREMIUM",
                                     "STEAM GAMES", "BILETIX"]),
]

BEHAVIOR_CATS = {"restoran", "giyim", "eglence", "market", "elektronik"}

#: Kural tablosunda karşılığı olmayan merchant'lar — kategorizasyonun
#: gerçek hayatta hiçbir zaman %100 olmadığını yansıtır.
UNKNOWN_MERCHANTS = ["OZKAN GIDA SAN", "MERKEZ BUFE", "SIMIT EVI 34",
                     "PLATFORM ODEME", "ISYERI TAHSILAT", "NET ODEME SISTEMI"]


def build_raw() -> RawData:
    # Her çağrıda sıfırlanır: fixture'ın kendisi de deterministik olmalı,
    # yoksa "aynı girdi → aynı skor" testi anlamını yitirir.
    global _seq
    _seq = 0
    rng = random.Random(20260731)
    W = windows(AS_OF, 5)          # W0 en yeni

    accounts = [
        Account("ch1", AccountType.CHECKING, "Vadesiz TRY", balance=12_770,
                is_linked=True, opened_at=date(2024, 1, 1)),
        Account("cc1", AccountType.CREDIT_CARD, "Kredi Kartı", balance=8_500,
                credit_limit=25_000, statement_day=18, due_day=28, is_linked=True),
        Account("sav1", AccountType.SAVINGS, "Acil Durum Fonu", balance=7_483,
                is_linked=True, is_emergency_fund=True),
        Account("sav2", AccountType.SAVINGS, "Tatil Fonu", balance=4_100, is_linked=True),
    ]

    txns: List[Transaction] = []
    tags: List[BehaviorTag] = []

    for wi, w in enumerate(W):
        # Aylık toplamlar W0'da tam, geçmişte hafif dalgalı (gerçekçilik)
        scale = 1.0 if wi == 0 else rng.uniform(0.90, 1.06)

        # ── Gelir ──────────────────────────────────────────────────────
        txns.append(Transaction(_tid("t"), "ch1", _dt(w.start, rng),
                                24_000 * (1 if wi == 0 else rng.uniform(0.98, 1.02)),
                                description_raw="MAAS ODEMESI",
                                merchant_raw="ACME TEKNOLOJI MAAS"))
        txns.append(Transaction(_tid("t"), "ch1", _dt(w.start, rng),
                                3_200 * (1 if wi == 0 else rng.uniform(0.7, 1.3)),
                                description_raw="SERBEST MESLEK MAKBUZU",
                                merchant_raw="FREELANCE HAKEDIS"))
        txns.append(Transaction(_tid("t"), "ch1", _dt(w.start, rng),
                                1_250, description_raw="KIRA GELIRI",
                                merchant_raw="KIRACI HAVALE"))

        # N8 — olağandışı tek seferlik büyük giriş (W1'e konur)
        if wi == 1:
            txns.append(Transaction(_tid("t"), "ch1", _dt(w.start, rng),
                                    95_000, description_raw="HAKEDIS ODEMESI",
                                    merchant_raw="PROJE HAKEDIS TOPLU"))

        # ── Harcamalar ─────────────────────────────────────────────────
        card_spend = 0.0
        for cat, amount, n, night_p, merchants in MONTHLY:
            for amt in _spread(amount * scale, n, rng):
                night = rng.random() < night_p
                acct = "cc1" if rng.random() < 0.65 else "ch1"
                # %8 ihtimalle kural tablosunda olmayan bir merchant —
                # gerçek hayatta kategorizasyon hiçbir zaman %100 değildir
                # ve `categorized_ratio` bunu güvene yansıtmalıdır.
                merchant = (rng.choice(UNKNOWN_MERCHANTS) if rng.random() < 0.08
                            else rng.choice(merchants))
                t = Transaction(_tid("t"), acct, _dt(w.start, rng, night), -amt,
                                merchant_raw=merchant, description_raw="POS HARCAMA")
                txns.append(t)
                if acct == "cc1":
                    card_spend += amt
                if cat in BEHAVIOR_CATS and rng.random() < 0.80:
                    tags.append(BehaviorTag(
                        t.id,
                        planned=rng.random() > 0.30,
                        emotion=rng.choices(
                            ["odul", "stres", "can_sikintisi", "sosyal",
                             "aliskanlik", None],
                            weights=[9, 6, 5, 22, 38, 20])[0],
                        satisfaction=rng.choices([1, 2, 3], weights=[28, 34, 38])[0]))

        # ── Birikim transferleri (N1) ──────────────────────────────────
        for dest, amt in (("sav1", 2_828), ("sav2", 2_475)):
            d = _dt(w.start, rng)
            out = Transaction(_tid("t"), "ch1", d, -amt,
                              description_raw="HESAPLAR ARASI VIRMAN",
                              merchant_raw="KENDI HESABIMA")
            inn = Transaction(_tid("t"), dest, d + timedelta(minutes=2), amt,
                              description_raw="HESAPLAR ARASI VIRMAN",
                              merchant_raw="KENDI HESABIMDAN")
            txns += [out, inn]

        # ── Kredi kartı ekstre ödemesi (N2) ────────────────────────────
        # Ödeme, o dönemin kart harcamasını takip eder: kart bakiyesi
        # dönüyor ama patlamıyor. Tutarsız bir fixture, normalizasyon
        # hatası gibi görünen sahte bulgular üretir.
        pay = round(card_spend * rng.uniform(0.94, 1.02), 2)
        d = _dt(w.start, rng)
        txns.append(Transaction(_tid("t"), "ch1", d, -pay,
                                description_raw="KREDI KARTI ODEME",
                                merchant_raw="KART BORC ODEMESI"))
        txns.append(Transaction(_tid("t"), "cc1", d, pay,
                                description_raw="KREDI KARTI ODEME",
                                merchant_raw="EKSTRE TAHSILAT"))

        # ── Kredi taksiti ──────────────────────────────────────────────
        txns.append(Transaction(_tid("t"), "ch1", _dt(w.start, rng), -2_400,
                                description_raw="KREDI TAKSIT ODEMESI",
                                merchant_raw="IHTIYAC KREDISI"))

    # ── N4: yıllık kasko primi, tek seferde ödenmiş ────────────────────
    txns.append(Transaction(_tid("t"), "ch1",
                            datetime(2026, 4, 10, 11, 30), -8_400,
                            description_raw="YILLIK PRIM",
                            merchant_raw="ANADOLU SIGORTA KASKO"))

    # ── N3: iki taksit planı ───────────────────────────────────────────
    txns.append(Transaction(_tid("t"), "cc1", datetime(2026, 6, 5, 14, 10), -900,
                            merchant_raw="TEKNOSA", description_raw="TAKSITLI 1/6",
                            installment_index=1, installment_count=6))
    txns.append(Transaction(_tid("t"), "cc1", datetime(2026, 7, 20, 16, 45), -900,
                            merchant_raw="BOYNER", description_raw="TAKSITLI 1/4",
                            installment_index=1, installment_count=4))

    # ── N7: iade edilmiş giyim alışverişi ──────────────────────────────
    buy = Transaction(_tid("t"), "cc1", datetime(2026, 7, 8, 15, 0), -1_450,
                      merchant_raw="ZARA AKMERKEZ", description_raw="POS HARCAMA")
    ret = Transaction(_tid("t"), "cc1", datetime(2026, 7, 15, 12, 0), 1_450,
                      merchant_raw="ZARA AKMERKEZ", description_raw="IADE ISLEMI")
    txns += [buy, ret]

    liabilities = [
        Liability("l1", "consumer_loan", principal_outstanding=10_000,
                  monthly_payment=2_400, interest_rate=0.42, remaining_months=5),
        Liability("l2", "card_revolving", principal_outstanding=8_500,
                  monthly_payment=1_800, days_past_due=0, min_payment_only_months=0),
    ]

    goals = [
        Goal("g1", "Acil Durum Fonu", 45_000, 7_483, date(2026, 3, 1),
             date(2027, 6, 30), monthly_plan=2_800, linked_account_id="sav1",
             contribution_history=[True, True, True]),
        Goal("g2", "Tatil Fonu", 15_000, 4_100, date(2026, 4, 1),
             date(2026, 12, 31), monthly_plan=2_400, linked_account_id="sav2",
             contribution_history=[True, False, True]),
        Goal("g3", "Borç Kapatma", 18_500, 6_000, date(2026, 3, 1),
             date(2027, 3, 1), monthly_plan=1_500,
             contribution_history=[False, True, False]),
    ]

    budgets = [Budget("market", 5_800), Budget("restoran", 4_000),
               Budget("ulasim", 3_300), Budget("giyim", 1_500)]

    # Ekstre anlık görüntülerinden gelen anapara geçmişi. Borç trendi
    # yalnızca buradan hesaplanır (işlem akışından tahmin edilmez).
    debt_history = [(date(2026, 3, 31), 24_800), (date(2026, 4, 30), 22_600),
                    (date(2026, 5, 31), 21_100), (date(2026, 6, 30), 19_700),
                    (date(2026, 7, 31), 18_500)]

    return RawData(
        user_id="didem", accounts=accounts, transactions=txns,
        liabilities=liabilities, goals=goals, budgets=budgets,
        behavior_tags=tags,
        income_declaration=IncomeDeclaration(monthly_net=28_000),
        onboarding={"zorluk": "nereye_gidiyor", "ay_sonu": "bazen",
                    "takip": "bazen", "borc_durumu": "yonetilebilir",
                    "birikim_6ay": "ara_sira"},
        cpi=_cpi(), accounts_declared=4, prev_score=74,
        debt_principal_history=debt_history,
    )


# ─────────────────────────────────────────────────────────────────────────────

def main() -> None:
    raw = build_raw()
    feats, ledger = build_features(raw, AS_OF)
    result = compute_score(feats)

    print("NAKITIO — UÇTAN UCA HAT DOĞRULAMASI")
    print("=" * 78)
    print(f"Ham işlem sayısı : {len(raw.transactions)}")
    print(f"Hesap sayısı     : {len(raw.accounts)}")
    print(f"Hesaplama tarihi : {AS_OF}\n")

    print("NORMALİZASYON TANILARI")
    print("-" * 78)
    d = ledger.diagnostics
    print(f"  N9 kategorizasyon : {d['categorize']}")
    print(f"     tür dağılımı   : {d['classify']}")
    print(f"  N1 iç transfer    : {d['transfers']['matched_pairs']} çift eşleşti")
    print(f"  N2 kart ödemesi   : bağlı karta {sum(1 for t in raw.transactions if t.excluded_reason == 'card_payment_to_linked_account')} ödeme gider dışı bırakıldı")
    print(f"     vekil ödeme    : {d['card']['proxy_payments']} (bağlantısız kart)")
    print(f"  N3 taksit planı   : {d['installments']['plans']} plan")
    for p in ledger.plans:
        print(f"       · {p.category:<12} {p.count} × {p.monthly_amount:,.0f} TL "
              f"(başlangıç {p.start}, kalan {p.remaining_after(AS_OF):,.0f} TL)")
    print(f"  N4 amortisman     : {d['amortize']['recurring_series']} seri → "
          f"{d['amortize']['amort_entries']} sanal kayıt")
    print(f"  N7 iade           : {d['refunds']['refunds_matched']}/"
          f"{d['refunds']['refunds_total']} eşleşti")
    print(f"  N8 aykırı değer   : {d['outliers']['outliers']} işlem işaretlendi")

    print("\nTÜRETİLMİŞ METRİKLER (Features)")
    print("-" * 78)
    rows = [
        ("gelir (i_net, 3 ay medyan)", f"{feats.i_net:,.0f} TL"),
        ("gelir oynaklığı (i_cv)", f"{feats.i_cv:.3f}" if feats.i_cv else "—"),
        ("ana gelir kaynağı payı", f"%{feats.i_primary_share*100:.0f}" if feats.i_primary_share else "—"),
        ("gider (e_total, nakit görünüm)", f"{feats.e_total:,.0f} TL"),
        ("zorunlu gider (e_essential)", f"{feats.e_essential:,.0f} TL"),
        ("isteğe bağlı pay", f"%{feats.disc_share*100:.0f}"),
        ("nakit akışı marjı", f"%{feats.cf_margin*100:.1f}"),
        ("kasıtlı tasarruf", f"{feats.s_deliberate:,.0f} TL  (oran %{feats.s_rate*100:.1f})"),
        ("acil durum fonu",
         "veri yok" if feats.ef_liquid is None
         else f"{feats.ef_liquid:,.0f} TL  ({feats.ef_months:.2f} ay)"),
        ("tasarruf sürekliliği", f"{feats.s_consistency_months}/6 ay"),
        ("borç anaparası", f"{feats.debt_principal:,.0f} TL"),
        ("DSR", f"%{feats.dsr*100:.1f}"),
        ("aylık taksit / kalan", f"{feats.installment_monthly:,.0f} / {feats.installment_remaining:,.0f} TL"),
        ("kart kullanımı", f"%{feats.card_utilization*100:.0f}" if feats.card_utilization else "—"),
        ("bütçe aşımı", f"{feats.budget_overrun:,.0f} / {feats.budget_planned:,.0f} TL"
                        if feats.budget_overrun is not None else "—"),
        ("kategori oynaklığı", f"{feats.cat_volatility:.3f}" if feats.cat_volatility else "—"),
        ("hedef ilerlemesi", f"%{feats.goal_ontrack*100:.0f}" if feats.goal_ontrack else "—"),
        ("davranış kapsamı", f"%{feats.beh_coverage*100:.0f}"),
        ("plansız harcama oranı", f"%{feats.imp_rate*100:.0f}" if feats.imp_rate is not None else "—"),
        ("duygusal harcama payı", f"%{feats.emo_rate*100:.0f}" if feats.emo_rate is not None else "—"),
        ("gece yoğunlaşması", f"%{feats.night_conc*100:.0f}" if feats.night_conc is not None else "—"),
        ("pişmanlık oranı", f"%{feats.regret_rate*100:.0f}" if feats.regret_rate is not None else "—"),
        ("kategorize oran", f"%{feats.categorized_ratio*100:.0f}"),
        ("veri günü", f"{feats.days_of_data}"),
    ]
    for k, v in rows:
        print(f"  {k:<32} {v}")

    print("\nSKOR")
    print("-" * 78)
    print(result.explain())


if __name__ == "__main__":
    main()
