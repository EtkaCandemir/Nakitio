"""
Nakitio — Normalizasyon Katmanı Testleri (N1–N9)

Her normalizasyon kuralının hem DOĞRU çalıştığını hem de atlandığında
ne bozulduğunu gösterir. Bu katmandaki bir hata, skor motoru kusursuz
olsa bile çıktıyı finansal olarak anlamsız kılar.

Çalıştırma:
    python3 engine/test_normalize.py
"""

from __future__ import annotations

import sys
from datetime import date, datetime, timedelta

from data_model import (
    Account, AccountType, BehaviorTag, Budget, CATEGORIES, CPISeries,
    Goal, IncomeDeclaration, Liability, RawData, Transaction, TxnKind,
)
from normalize import (
    Ledger, build_features, normalize, real_value, windows,
    _merchant_key, active_windows,
)

FAILS: list = []
PASSES = 0
AS_OF = date(2026, 7, 31)


def check(name, cond, detail=""):
    global PASSES
    if cond:
        PASSES += 1
    else:
        FAILS.append(name + (f"  — {detail}" if detail else ""))


def D(days_ago: int, hour: int = 12) -> datetime:
    d = AS_OF - timedelta(days=days_ago)
    return datetime(d.year, d.month, d.day, hour, 0)


_n = [0]


def T(account, days_ago, amount, merchant="", desc="", **kw) -> Transaction:
    _n[0] += 1
    return Transaction(f"t{_n[0]:04d}", account, D(days_ago, kw.pop("hour", 12)),
                       amount, merchant_raw=merchant, description_raw=desc, **kw)


def RD(accounts, txns, **kw) -> RawData:
    base = dict(user_id="test", accounts=accounts, transactions=txns,
                income_declaration=IncomeDeclaration(monthly_net=30_000),
                onboarding={"ay_sonu": "bazen"}, accounts_declared=len(accounts))
    base.update(kw)
    return RawData(**base)


CH = Account("ch", AccountType.CHECKING, balance=10_000, is_linked=True)
SAV = Account("sav", AccountType.SAVINGS, balance=20_000, is_linked=True,
              is_emergency_fund=True)
GOLD = Account("gold", AccountType.GOLD, balance=30_000, is_linked=True)


def _cc(linked=True):
    return Account("cc", AccountType.CREDIT_CARD, balance=5_000,
                   credit_limit=20_000, is_linked=linked)


def expense_total(ledger: Ledger, w) -> float:
    return sum(a for a, _, _ in ledger.expenses_cash(w))


def income_total(ledger: Ledger, w) -> float:
    return sum(t.inflow for t in ledger.income(w))


# ── N1 — İç transfer eşleştirme ──────────────────────────────────────────────

def t_n1_internal_transfer():
    raw = RD([CH, SAV], [
        T("ch", 20, 50_000, "ACME", "MAAS ODEMESI"),
        T("ch", 15, -8_000, "KENDI HESABIMA", "VIRMAN"),
        T("sav", 15, 8_000, "KENDI HESABIMDAN", "VIRMAN"),
        T("ch", 10, -3_000, "MIGROS TIC", "POS"),
    ])
    led = normalize(raw, AS_OF)
    w = windows(AS_OF, 1)[0]

    check("N1: çift eşleşti", led.diagnostics["transfers"]["matched_pairs"] == 1)
    check("N1: transfer giderden düşüldü", abs(expense_total(led, w) - 3_000) < 1,
          f"gider={expense_total(led, w):,.0f} (beklenen 3.000)")
    check("N1: transfer gelire eklenmedi", abs(income_total(led, w) - 50_000) < 1,
          f"gelir={income_total(led, w):,.0f}")
    check("N1: birikim akışı transferi gördü",
          abs(led.savings_flow(w) - 8_000) < 1, f"{led.savings_flow(w):,.0f}")


def t_n1_no_false_match():
    """Tutarı/zamanı tutmayan hareketler transfer sayılmamalı."""
    raw = RD([CH, SAV], [
        T("ch", 20, 50_000, "ACME", "MAAS ODEMESI"),
        T("ch", 20, -8_000, "ZARA AKMERKEZ", "POS"),
        T("sav", 8, 8_000, "KENDI HESABIMDAN", "VIRMAN"),   # 12 gün sonra
    ])
    led = normalize(raw, AS_OF)
    check("N1: 3 günden uzak aralık eşleşmez",
          led.diagnostics["transfers"]["matched_pairs"] == 0)


# ── N2 — Kredi kartı ödemesi ─────────────────────────────────────────────────

def t_n2_linked_card_no_double_count():
    """EN KRİTİK TEST.

    Kart bağlıyken hem harcamalar hem ekstre ödemesi gider sayılırsa
    her harcama İKİ KEZ sayılır: gider iki katına çıkar, tasarruf oranı
    negatife düşer, skor çöker. Bu, veri katmanının en pahalı hatasıdır.
    """
    raw = RD([CH, _cc(linked=True)], [
        T("ch", 25, 40_000, "ACME", "MAAS ODEMESI"),
        T("cc", 20, -6_000, "MIGROS TIC", "POS"),
        T("cc", 18, -4_000, "STARBUCKS", "POS"),
        T("ch", 5, -10_000, "KART BORC ODEMESI", "KREDI KARTI ODEME"),
        T("cc", 5, 10_000, "EKSTRE TAHSILAT", "KREDI KARTI ODEME"),
    ])
    led = normalize(raw, AS_OF)
    w = windows(AS_OF, 1)[0]
    total = expense_total(led, w)
    check("N2: bağlı kartta çift sayım yok", abs(total - 10_000) < 1,
          f"gider={total:,.0f} (beklenen 10.000, çift sayımda 20.000 çıkardı)")
    check("N2: ödeme gider dışı işaretlendi",
          any(t.excluded_reason == "card_payment_to_linked_account"
              for t in raw.transactions))


def t_n2_unlinked_card_is_proxy():
    """Kart BAĞLI DEĞİLSE ödeme gider sayılmalı.

    Aksi hâlde kullanıcının giderinin büyük kısmı yok olur ve skor
    haksız yere yükselir — sessiz ve tehlikeli bir hata.
    """
    raw = RD([CH], [
        T("ch", 25, 40_000, "ACME", "MAAS ODEMESI"),
        T("ch", 5, -10_000, "KART BORC ODEMESI", "KREDI KARTI ODEME"),
    ])
    led = normalize(raw, AS_OF)
    w = windows(AS_OF, 1)[0]
    check("N2: bağlantısız kart ödemesi gider sayılır",
          abs(expense_total(led, w) - 10_000) < 1,
          f"gider={expense_total(led, w):,.0f}")
    check("N2: vekil ödeme sayacı arttı",
          led.diagnostics["card"]["proxy_payments"] == 1)


# ── N3 — Taksit ──────────────────────────────────────────────────────────────

def t_n3_installments():
    raw = RD([CH, _cc()], [
        T("ch", 25, 40_000, "ACME", "MAAS ODEMESI"),
        T("cc", 40, -1_000, "TEKNOSA", "TAKSITLI 1/6",
          installment_index=1, installment_count=6),
    ])
    led = normalize(raw, AS_OF)
    w = windows(AS_OF, 1)[0]
    plan = led.plans[0]

    check("N3: plan oluştu", len(led.plans) == 1)
    check("N3: toplam tutar 6 × 1.000", abs(plan.total_amount - 6_000) < 1)
    check("N3: kalan taahhüt 4 × 1.000",
          abs(plan.remaining_after(AS_OF) - 4_000) < 1,
          f"{plan.remaining_after(AS_OF):,.0f}")

    cash = expense_total(led, w)
    accrual = sum(a for a, _, _ in led.expenses_accrual(w))
    check("N3: nakit görünüm aylık taksiti sayar", abs(cash - 1_000) < 1,
          f"nakit={cash:,.0f}")
    check("N3: tahakkuk görünümü ile nakit görünümü farklı", accrual != cash)


def t_n3_followups_not_double_counted():
    raw = RD([CH, _cc()], [
        T("ch", 25, 40_000, "ACME", "MAAS ODEMESI"),
        T("cc", 70, -1_000, "TEKNOSA", "TAKSITLI 1/3",
          installment_index=1, installment_count=3),
        T("cc", 40, -1_000, "TEKNOSA", "TAKSITLI 2/3",
          installment_index=2, installment_count=3),
        T("cc", 10, -1_000, "TEKNOSA", "TAKSITLI 3/3",
          installment_index=3, installment_count=3),
    ])
    led = normalize(raw, AS_OF)
    w = windows(AS_OF, 1)[0]
    check("N3: sonraki taksitler tekil gider sayılmaz",
          abs(expense_total(led, w) - 1_000) < 1,
          f"gider={expense_total(led, w):,.0f} (çift sayımda 2.000 çıkardı)")


# ── N4 — Amortisman ──────────────────────────────────────────────────────────

def t_n4_amortization():
    raw = RD([CH], [
        T("ch", 25, 40_000, "ACME", "MAAS ODEMESI"),
        T("ch", 20, -12_000, "ANADOLU SIGORTA KASKO", "YILLIK PRIM"),
        T("ch", 15, -3_000, "MIGROS TIC", "POS"),
    ])
    led = normalize(raw, AS_OF)
    w = windows(AS_OF, 1)[0]
    total = expense_total(led, w)
    check("N4: yıllık prim aylara dağıtıldı", abs(total - 4_000) < 1,
          f"gider={total:,.0f} (beklenen 3.000 + 12.000/12 = 4.000)")
    check("N4: sanal kayıt üretildi", len(led.amort) == 12, f"{len(led.amort)}")

    # Amortisman olmasaydı: aynı ay 15.000, sonraki aylar 3.000 → skor sallanır
    naive = 3_000 + 12_000
    check("N4: amortisman olmadan gider 3,75× fazla görünürdü",
          abs(naive / total - 3.75) < 0.01)


# ── N5 — Enflasyon ───────────────────────────────────────────────────────────

def t_n5_inflation():
    cpi = CPISeries(index={"genel": {"2026-01": 100.0, "2026-07": 120.0},
                           "gida": {"2026-01": 100.0, "2026-07": 130.0}})
    v = real_value(1_000, date(2026, 1, 15), "market", cpi, date(2026, 7, 15))
    check("N5: geçmiş tutar bugüne taşınır", abs(v - 1_300) < 1, f"{v:.0f}")
    v2 = real_value(1_000, date(2026, 7, 15), "market", cpi, date(2026, 7, 15))
    check("N5: aynı dönemde düzeltme yok", abs(v2 - 1_000) < 1)
    check("N5: kategori bazlı endeks kullanılır",
          real_value(1_000, date(2026, 1, 1), "market", cpi, date(2026, 7, 1)) >
          real_value(1_000, date(2026, 1, 1), "eglence", cpi, date(2026, 7, 1)))


# ── N6 — Değerleme farkı tasarruf değildir ───────────────────────────────────

def t_n6_valuation_not_savings():
    """Altın yükseldi diye kullanıcı 'tasarruf etmiş' sayılamaz.

    Bu onun davranışı değil, piyasanın hareketidir. Skor kullanıcının
    kontrol edemediği bir şeye tepki vermemelidir.
    """
    raw = RD([CH, GOLD], [
        T("ch", 25, 40_000, "ACME", "MAAS ODEMESI"),
        T("ch", 20, -5_000, "KENDI HESABIMA", "VIRMAN"),
        T("gold", 20, 5_000, "KENDI HESABIMDAN", "VIRMAN"),
    ])
    # Hesap bakiyesi 30.000 (değer artışı dahil) ama katkı yalnızca 5.000
    led = normalize(raw, AS_OF)
    w = windows(AS_OF, 1)[0]
    check("N6: yalnızca katkı tasarruf sayılır",
          abs(led.savings_flow(w) - 5_000) < 1, f"{led.savings_flow(w):,.0f}")


# ── N7 — İade ────────────────────────────────────────────────────────────────

def t_n7_refund():
    raw = RD([CH, _cc()], [
        T("ch", 25, 40_000, "ACME", "MAAS ODEMESI"),
        T("cc", 20, -3_000, "ZARA AKMERKEZ", "POS HARCAMA"),
        T("cc", 10, 3_000, "ZARA AKMERKEZ", "IADE ISLEMI"),
        T("cc", 15, -2_000, "MIGROS TIC", "POS"),
    ])
    led = normalize(raw, AS_OF)
    w = windows(AS_OF, 1)[0]
    check("N7: iade eşleşti", led.diagnostics["refunds"]["refunds_matched"] == 1)
    check("N7: iade edilen harcama netlendi",
          abs(expense_total(led, w) - 2_000) < 1,
          f"gider={expense_total(led, w):,.0f} (netlenmezse 5.000)")
    check("N7: iade gelir olarak sayılmadı",
          abs(income_total(led, w) - 40_000) < 1)


# ── N8 — Aykırı değer ────────────────────────────────────────────────────────

def t_n8_outlier():
    txns = []
    for k in range(3):
        txns += [T("ch", 20 + 30 * k, 30_000, "ACME", "MAAS ODEMESI"),
                 T("ch", 15 + 30 * k, -20_000, "MIGROS TIC", "POS")]
    txns.append(T("ch", 45, 200_000, "PROJE HAKEDIS", "HAKEDIS ODEMESI"))
    raw = RD([CH], txns)
    led = normalize(raw, AS_OF)
    check("N8: aykırı işlem işaretlendi", led.diagnostics["outliers"]["outliers"] == 1)

    feats, _ = build_features(RD([CH], txns), AS_OF)
    check("N8: medyan gelir aykırı değerden etkilenmedi",
          abs(feats.i_net - 30_000) < 1, f"i_net={feats.i_net:,.0f}")


# ── N9 — Kategorizasyon ──────────────────────────────────────────────────────

def t_n9_categorization():
    raw = RD([CH], [
        T("ch", 20, 40_000, "ACME", "MAAS ODEMESI"),
        T("ch", 10, -500, "MIGROS TIC A.S IST *4471", "POS"),
        T("ch", 9, -300, "BILINMEYEN ISYERI XYZ", "POS"),
        T("ch", 8, -200, "", "POS", mcc="5812"),
    ])
    normalize(raw, AS_OF)
    by = {t.merchant_raw: t for t in raw.transactions}
    check("N9: kural eşleşti", by["MIGROS TIC A.S IST *4471"].category == "market")
    check("N9: MCC yedeği çalıştı", by[""].category == "restoran")
    check("N9: eşleşmeyen 'diğer' oldu",
          by["BILINMEYEN ISYERI XYZ"].category == "diger")

    raw2 = RD([CH], [T("ch", 10, -500, "MIGROS TIC", "POS")])
    tid = raw2.transactions[0].id
    normalize(raw2, AS_OF, user_overrides={tid: "hediye"})
    check("N9: kullanıcı düzeltmesi kuralı ezer",
          raw2.transactions[0].category == "hediye")


def t_merchant_key():
    check("merchant: gürültü temizlenir",
          _merchant_key("MIGROS TIC A.S IST *4471") == _merchant_key("MIGROS TIC SUBE 12"),
          f"{_merchant_key('MIGROS TIC A.S IST *4471')} vs {_merchant_key('MIGROS TIC SUBE 12')}")


# ── Zorunlu/isteğe bağlı ağırlıklandırma ─────────────────────────────────────

def t_essential_weighting():
    check("taksonomi: tüm ağırlıklar [0,1]",
          all(0.0 <= c.essential_weight <= 1.0 for c in CATEGORIES.values()))
    check("taksonomi: kira tam zorunlu", CATEGORIES["kira"].essential_weight == 1.0)
    check("taksonomi: eğlence tam isteğe bağlı",
          CATEGORIES["eglence"].essential_weight == 0.0)
    check("taksonomi: market kısmi zorunlu",
          0.5 < CATEGORIES["market"].essential_weight < 1.0)

    raw = RD([CH], [
        T("ch", 20, 40_000, "ACME", "MAAS ODEMESI"),
        T("ch", 15, -10_000, "MIGROS TIC", "POS"),        # 0,85 → 8.500
        T("ch", 14, -10_000, "CINEMAXIMUM", "POS"),       # 0,00 → 0
    ])
    feats, _ = build_features(raw, AS_OF)
    check("zorunlu gider kesirli ağırlıkla hesaplanır",
          abs(feats.e_essential - 8_500) < 1, f"{feats.e_essential:,.0f}")


# ── Eksik pencere cezası olmamalı (regresyon) ────────────────────────────────

def t_short_history_not_penalized():
    """5 aylık kullanıcı, 6. pencere boş diye cezalandırılmamalı.

    İlk implementasyonda boş pencere 'o ay sıfır harcadı' sayılıyordu:
    tamamen sabit giden 700 TL'lik telefon faturası cv=0,45 ile 'oynak'
    işaretleniyor, her ay biriktiren kullanıcı 6/6 yerine 5/6 alıyordu.
    """
    txns = []
    for k in range(5):
        txns += [
            T("ch", 10 + 30 * k, 30_000, "ACME", "MAAS ODEMESI"),
            T("ch", 12 + 30 * k, -8_000, "MIGROS TIC", "POS"),
            T("ch", 13 + 30 * k, -700, "TURKCELL FATURA", "POS"),
            T("ch", 14 + 30 * k, -2_000, "KENDI HESABIMA", "VIRMAN"),
        ]
        txns.append(T("sav", 14 + 30 * k, 2_000, "KENDI HESABIMDAN", "VIRMAN"))
    raw = RD([CH, SAV], txns)
    led = normalize(raw, AS_OF)

    aw = active_windows(led, windows(AS_OF, 6))
    check("kısa geçmiş: boş pencere elendi", len(aw) == 5, f"{len(aw)} aktif pencere")

    feats, _ = build_features(RD([CH, SAV], txns), AS_OF)
    check("kısa geçmiş: her ay biriktiren 6/6 alır",
          feats.s_consistency_months == 6, f"{feats.s_consistency_months}/6")
    check("kısa geçmiş: sabit kalem oynak görünmez",
          feats.cat_volatility is None or feats.cat_volatility < 0.25,
          f"cv={feats.cat_volatility}")


# ── Uçtan uca ────────────────────────────────────────────────────────────────

def t_end_to_end_determinism():
    from fixture_didem import build_raw
    a, _ = build_features(build_raw(), AS_OF)
    b, _ = build_features(build_raw(), AS_OF)
    check("uçtan uca: determinizm",
          a.i_net == b.i_net and a.e_total == b.e_total and a.imp_rate == b.imp_rate)


def t_end_to_end_sanity():
    from fixture_didem import build_raw
    from score_engine import compute_score
    feats, led = build_features(build_raw(), AS_OF)
    r = compute_score(feats)

    check("uçtan uca: gelir makul aralıkta", 25_000 < feats.i_net < 31_000,
          f"{feats.i_net:,.0f}")
    check("uçtan uca: gider gelirden küçük", feats.e_total < feats.i_net)
    check("uçtan uca: marj pozitif", feats.cf_margin > 0)
    check("uçtan uca: tüm bileşenler aktif",
          all(p.enabled for p in r.pillars),
          f"kapalı: {[p.key for p in r.pillars if not p.enabled]}")
    check("uçtan uca: skor makul aralıkta", 60 <= r.score <= 85, f"skor={r.score}")
    check("uçtan uca: taksit taahhüdü görüldü", feats.installment_remaining > 0)
    check("uçtan uca: kategorize oran %100 değil (gerçekçi)",
          feats.categorized_ratio < 1.0, f"%{feats.categorized_ratio*100:.0f}")


TESTS = [t_n1_internal_transfer, t_n1_no_false_match,
         t_n2_linked_card_no_double_count, t_n2_unlinked_card_is_proxy,
         t_n3_installments, t_n3_followups_not_double_counted,
         t_n4_amortization, t_n5_inflation, t_n6_valuation_not_savings,
         t_n7_refund, t_n8_outlier, t_n9_categorization, t_merchant_key,
         t_essential_weighting, t_short_history_not_penalized,
         t_end_to_end_determinism, t_end_to_end_sanity]


if __name__ == "__main__":
    print("NAKITIO — NORMALİZASYON KATMANI TESTLERİ")
    print("=" * 78)
    for t in TESTS:
        before = len(FAILS)
        t()
        status = "FAIL" if len(FAILS) > before else "ok"
        doc = (t.__doc__ or "").strip().split("\n")[0]
        print(f"  [{status:>4}] {t.__name__:<38} {doc[:30]}")
    print("=" * 78)
    if FAILS:
        print(f"{PASSES} geçti, {len(FAILS)} KIRILDI:\n")
        for f in FAILS:
            print(f"  ✗ {f}")
        sys.exit(1)
    print(f"{PASSES} kontrolün tamamı geçti.")
