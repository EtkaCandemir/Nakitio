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
    Account, AccountType, BehaviorTag, Budget, CATEGORIES, CategorySource,
    CPISeries,
    Goal, IncomeDeclaration, Liability, RawData, Transaction, TxnKind,
)
from normalize import (
    Ledger, build_features, normalize, real_value, windows,
    _merchant_key, active_windows, select_category_triage,
    category_fingerprint, category_telemetry,
    CATEGORY_VERSION, CATEGORY_FINGERPRINT,
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


def t_n9_turkish_folding():
    """Aksanlı işyeri adı aksansız kuralla eşleşmeli."""
    # Kural tablosu "PETROL OFISI" yazar; banka "PETROL OFİSİ" yazar.
    # Yalnız .upper() yapmak YETMEZ: "İ".upper() yine "İ"dir, "I" olmaz.
    # Gerçek bir kart ekstresinde akaryakıt ve sigorta satırları tam
    # olarak bu yüzden "diğer"e düşüyordu.
    raw = RD([CH], [
        T("ch", 20, 40_000, "ACME", "MAAS ODEMESI"),
        T("ch", 10, -900, "PETROL OFİSİ A.Ş./ESKİŞEHİR", "POS"),
        T("ch", 9, -1_895, "HEPİYİ SİGORTA ANONİ", "POS"),
    ])
    normalize(raw, AS_OF)
    by = {t.merchant_raw: t for t in raw.transactions}
    check("N9: aksanlı 'PETROL OFİSİ' eşleşti",
          by["PETROL OFİSİ A.Ş./ESKİŞEHİR"].category == "ulasim",
          by["PETROL OFİSİ A.Ş./ESKİŞEHİR"].category)
    check("N9: aksanlı 'SİGORTA' eşleşti",
          by["HEPİYİ SİGORTA ANONİ"].category == "sigorta",
          by["HEPİYİ SİGORTA ANONİ"].category)


def t_n9_payment_intermediary_unwrapped():
    """Aracı soyulur; kategori arkadaki işyerinden gelir."""
    # "IYZICO/AMAZON.COM.TR" satırında kategoriyi Iyzico değil Amazon
    # belirler. Soyulmazsa bu satırlar toptan "diğer"e düşer ve "diğer"
    # bir kategori değil çöp kutusudur — hem disc_share'i hem farkındalık
    # kartını bozar.
    raw = RD([CH], [
        T("ch", 20, 40_000, "ACME", "MAAS ODEMESI"),
        T("ch", 10, -250, "IYZICO/YEMEKSEPETI", "POS"),
        T("ch", 9, -400, "HEPSIPAY /TEKNOSA", "POS"),
        T("ch", 8, -100, "IYZICO", "POS"),          # arkasında işyeri yok
    ])
    normalize(raw, AS_OF)
    by = {t.merchant_raw: t for t in raw.transactions}
    check("N9: IYZICO/YEMEKSEPETI → restoran",
          by["IYZICO/YEMEKSEPETI"].category == "restoran",
          by["IYZICO/YEMEKSEPETI"].category)
    check("N9: HEPSIPAY /TEKNOSA → elektronik",
          by["HEPSIPAY /TEKNOSA"].category == "elektronik",
          by["HEPSIPAY /TEKNOSA"].category)
    check("N9: çıplak aracı 'diğer' kalır",
          by["IYZICO"].category == "diger")


def t_n9_generic_turkish_patterns():
    """Yerel işletme türünü adından söyler; jenerik kalıplar onu yakalar."""
    # Zincir adı ezberlemek Türkiye'de yetmiyor: gerçek bir ekstrede
    # satırların yalnızca %21'i marka kurallarıyla eşleşti. Türkçe
    # işletme adları türü neredeyse her zaman içinde barındırır.
    raw = RD([CH], [T("ch", 20, 40_000, "ACME", "MAAS ODEMESI")] + [
        T("ch", 10 - i, -300, ad, "POS") for i, ad in enumerate([
            "METIN GIDA LTD.STI.", "BUYUKKAYALAR MARKET", "TUNALI KOFTECISI",
            "BAKLAVACI KARDESLER", "BASKENTLILER AKARYAKIT", "S/HOP SCOOTER",
            "TUNALI GIYIM IMALAT", "MELISA MOBILYA",
        ])])
    normalize(raw, AS_OF)
    by = {t.merchant_raw: t.category for t in raw.transactions}
    for ad, beklenen in (("METIN GIDA LTD.STI.", "market"),
                         ("BUYUKKAYALAR MARKET", "market"),
                         ("TUNALI KOFTECISI", "restoran"),
                         ("BAKLAVACI KARDESLER", "restoran"),
                         ("BASKENTLILER AKARYAKIT", "ulasim"),
                         ("S/HOP SCOOTER", "ulasim"),
                         ("TUNALI GIYIM IMALAT", "giyim"),
                         ("MELISA MOBILYA", "ev")):
        check(f"N9: jenerik kalıp '{ad.split()[-1]}' → {beklenen}",
              by[ad] == beklenen, f"{ad} → {by[ad]}")

    # Marka kuralı jenerik kalıptan ÖNCE gelmeli: "MEDIAMARKT" içinde
    # "MARKT" var ama elektronikçidir; jenerik "\bMARKET\b" onu yakalamaz.
    raw2 = RD([CH], [T("ch", 20, 40_000, "ACME", "MAAS"),
                     T("ch", 10, -5_000, "MEDIAMARKT ANKARA", "POS")])
    normalize(raw2, AS_OF)
    check("N9: marka kuralı jenerik kalıbı yener",
          raw2.transactions[1].category == "elektronik",
          raw2.transactions[1].category)


def t_marka_sozlugu_kisa_desen_tuzagi():
    """Kısa marka desenleri Türkçe kısaltmalarla çakışmamalı."""
    # ASCII katlamada "ŞOK" → "SOK" olur; ama "SOK" Türkçe'de SOKAK
    # kısaltmasıdır. Çıplak `\bSOK\b` deseni "POLATLI ZAFER SOK" adresini
    # market sanıyordu — gerçek bir ekstrede ölçümle yakalandı ve tam da
    # bu yüzden essential_weight metriği var: sessiz, makul görünen hata.
    raw = RD([CH], [
        T("ch", 20, 40_000, "ACME", "MAAS ODEMESI"),
        T("ch", 10, -500, "POLATLI ZAFER SOK", "POS"),
        T("ch", 9, -800, "SOK MARKET BAHCELIEVLER", "POS"),
        T("ch", 8, -700, "MOBILYA DOLAP DUNYASI", "POS"),
    ])
    normalize(raw, AS_OF)
    by = {t.merchant_raw: t.category for t in raw.transactions}
    check("marka: 'SOK' sokak kısaltması market sayılmaz",
          by["POLATLI ZAFER SOK"] == "diger", by["POLATLI ZAFER SOK"])
    check("marka: 'SOK MARKET' market sayılır",
          by["SOK MARKET BAHCELIEVLER"] == "market",
          by["SOK MARKET BAHCELIEVLER"])
    check("marka: 'DOLAP' mobilya, pazaryeri değil",
          by["MOBILYA DOLAP DUNYASI"] == "ev", by["MOBILYA DOLAP DUNYASI"])


def t_marka_kanonik_kimlik():
    """Aynı zincirin farklı şubeleri TEK işyeri sayılmalı."""
    # `merchant_id` yinelenen ödeme tespiti (N4), iade eşleştirme (N7) ve
    # kullanıcı düzeltmelerinin kalıcılığının temelidir. Marka tanınmazsa
    # mağaza kodu anahtara sızar: "9922-5650-A101 C" → 'a c',
    # "9946-E325-A101 TUNAL" → 'e a' — aynı zincir iki ayrı işyeri olur.
    check("kimlik: A101 mağaza kodundan bağımsız",
          _merchant_key("9922 - 5650 - A101 C")
          == _merchant_key("9946-E325-A101 TUNAL") == "a101")
    check("kimlik: BİM şubeden bağımsız",
          _merchant_key("BIM O831 GORDION POL")
          == _merchant_key("BIM T288 YENIMAHALLE") == "bim")
    check("kimlik: ticari unvan gürültüsü elenir",
          _merchant_key("METIN GIDA LTD.STI.") == _merchant_key("METIN GIDA"))
    check("kimlik: aksanlı yazım aynı anahtara düşer",
          _merchant_key("PETROL OFİSİ A.Ş.") == _merchant_key("PETROL OFISI AS"))
    # Farklı zincirler AYRI kalmalı — aşırı birleştirme de hatadır.
    check("kimlik: farklı zincirler ayrı",
          _merchant_key("OPET ANKARA") != _merchant_key("SHELL ANKARA"))


def t_faiz_ucret_tuketim_sayilmaz():
    """Faiz/ücret harcama kategorisi almamalı ve impuls havuzuna girmemeli."""
    # Kart faizi bir "plansız alışveriş" değildir. Yanlış sınıflanırsa
    # gerçek bir ekstrede 6.693 TL'lik faiz, davranış analizinde impuls
    # harcaması gibi görünür ve P6'yı anlamsız kılar.
    #
    # Ama nakit akışından ÇIKARILMAZ: para gerçekten çıkıyor.
    raw = RD([CH, _cc()], [
        T("ch", 25, 40_000, "ACME", "MAAS ODEMESI"),
        T("cc", 10, -6_693, "ALIŞVERİŞ FAİZİ (Oran:4.25)", ""),
        T("cc", 10, -1_004, "BSMV", ""),
        T("cc", 10, -1_004, "KKDF", ""),
        T("cc", 9, -500, "MIGROS ANKARA", "POS"),
    ])
    led = normalize(raw, AS_OF)
    by = {t.description_raw or t.merchant_raw: t for t in raw.transactions}
    faiz = by["ALIŞVERİŞ FAİZİ (Oran:4.25)"]
    check("faiz: kind = interest", faiz.kind == TxnKind.INTEREST, faiz.kind.value)
    check("faiz: kategori faiz_ucret", faiz.category == "faiz_ucret", faiz.category)
    check("faiz: BSMV kind = fee", by["BSMV"].kind == TxnKind.FEE)
    check("faiz: zorunluluk ağırlığı BİLİNMEZ",
          CATEGORIES["faiz_ucret"].essential_weight is None)

    # Nakit akışında kalır: 6.693 + 1.004 + 1.004 + 500
    w = windows(AS_OF, 1)[0]
    check("faiz: nakit akışında KALIR",
          abs(expense_total(led, w) - 9_201) < 1,
          f"gider={expense_total(led, w):,.0f}")


def t_turkce_katlama_tur_siniflandirmada():
    """Aksanlı yazım ASCII desenle eşleşmeli — tür sınıflandırmada da."""
    # Bu hata depoda ÜÇ katmanda ayrı ayrı çıktı: ekstre ayrıştırma,
    # kategorizasyon, tür sınıflandırma. `.upper()` Türkçe'de yetmez:
    # "İ".upper() yine "İ"dir. "ALIŞVERİŞ FAİZİ" satırı `ALISVERIS FAIZI`
    # desenini kaçırıyor ve faiz harcama sanılıyordu.
    raw = RD([CH], [
        T("ch", 20, 40_000, "ACME", "MAAŞ ÖDEMESİ"),      # aksanlı gelir
        T("ch", 10, -900, "PETROL OFİSİ A.Ş.", "POS"),
    ])
    led = normalize(raw, AS_OF)
    by = {t.merchant_raw: t for t in raw.transactions}
    check("katlama: aksanlı 'MAAŞ' gelir tanındı",
          by["ACME"].kind == TxnKind.INCOME, by["ACME"].kind.value)
    check("katlama: aksanlı 'PETROL OFİSİ' ulaşım",
          by["PETROL OFİSİ A.Ş."].category == "ulasim")


def t_isyeri_hafizasi_kalicidir():
    """Bir düzeltme, o işyerinin TÜM işlemlerine uygulanmalı."""
    # `Docs/veri-katmani-v1.md` §10.5'in "üretim öncesi" diye işaretlediği
    # eksik: düzeltme işlem id'siyle anahtarlıydı, yani kullanıcı aynı
    # dükkânı her ay yeniden düzeltmek zorundaydı.
    #
    # Kanonik `merchant_id` sayesinde düzeltme zincirin TÜM şubelerini de
    # kapsar — mağaza kodu anahtara sızsaydı kapsamazdı.
    txns = [T("cc", 20, -300, "AYYILDIZ/ESKİŞEHİR", "POS"),
            T("cc", 15, -400, "AYYILDIZ/ESKİŞEHİR", "POS"),
            T("cc", 10, -500, "BIM O831 GORDION POL", "POS"),
            T("cc", 5, -600, "BIM T288 YENIMAHALLE", "POS")]
    raw = RD([CH, _cc()], [T("ch", 25, 40_000, "ACME", "MAAS")] + txns)
    normalize(raw, AS_OF)
    mid = txns[0].merchant_id
    check("hafıza: tanınmayan işyeri çekimser kalır",
          txns[0].category == "diger"
          and txns[0].category_source == CategorySource.NONE)

    # Kullanıcı bir kez düzeltir
    txns2 = [T("cc", 20, -300, "AYYILDIZ/ESKİŞEHİR", "POS"),
             T("cc", 15, -400, "AYYILDIZ/ESKİŞEHİR", "POS"),
             T("cc", 10, -500, "BIM O831 GORDION POL", "POS"),
             T("cc", 5, -600, "BIM T288 YENIMAHALLE", "POS")]
    raw2 = RD([CH, _cc()], [T("ch", 25, 40_000, "ACME", "MAAS")] + txns2,
              category_overrides={mid: "giyim", "bim": "restoran"})
    normalize(raw2, AS_OF)
    check("hafıza: düzeltme aynı işyerinin HER işlemine yayıldı",
          all(t.category == "giyim" for t in txns2[:2]),
          [t.category for t in txns2[:2]])
    check("hafıza: kaynak USER olarak işaretlendi",
          txns2[0].category_source == CategorySource.USER)
    check("hafıza: zincirin FARKLI şubeleri tek düzeltmeyle kapsandı",
          all(t.category == "restoran" for t in txns2[2:]),
          [t.category for t in txns2[2:]])


def t_hafiza_marka_sozlugunu_ezer():
    """Kullanıcı bilgisi marka varsayılanından üstündür."""
    # Aynı zincirden düzenli iş yemeği alan biri "BİM → restoran" diyebilir
    # ve haklıdır. Sözlük genel doğruyu bilir, kullanıcı kendi bağlamını.
    txns = [T("cc", 10, -500, "BIM T288 YENIMAHALLE", "POS")]
    raw = RD([CH, _cc()], [T("ch", 25, 40_000, "ACME", "MAAS")] + txns,
             category_overrides={"bim": "restoran"})
    normalize(raw, AS_OF)
    check("hafıza: marka sözlüğünü ezer", txns[0].category == "restoran",
          txns[0].category)

    # Ama TEK İŞLEME özel düzeltme hafızayı da ezer — en özel kazanır.
    txns2 = [T("cc", 10, -500, "BIM T288 YENIMAHALLE", "POS")]
    raw2 = RD([CH, _cc()], [T("ch", 25, 40_000, "ACME", "MAAS")] + txns2,
              category_overrides={"bim": "restoran"})
    normalize(raw2, AS_OF, user_overrides={txns2[0].id: "hediye"})
    check("hafıza: işlem düzeltmesi hafızayı ezer",
          txns2[0].category == "hediye", txns2[0].category)


def t_kategori_triyaji_isyeri_bazli():
    """Kategori sorusu işleme değil İŞYERİNE sorulmalı."""
    # İmpuls triyajı işlem bazlıdır ("bu plansız mıydı" her işlemde ayrı
    # cevaplanır). Kategori öyle değil: bir işyeri ne satıyorsa onu satar.
    # İşyeri bazlı sormak, bir soruyla onlarca işlemi çözer — gerçek bir
    # ekstrede 8 soru 30.410 TL'yi aydınlatıyordu.
    txns = ([T("cc", 20 - i, -400, "BILINMEYEN AAA", "POS") for i in range(5)]
            + [T("cc", 10, -3_000, "BILINMEYEN BBB", "POS")]
            + [T("cc", 9, -800, "TRENDYOL.COM", "POS")]
            + [T("cc", 8, -500, "MIGROS ANKARA", "POS")])
    raw = RD([CH, _cc()], [T("ch", 25, 40_000, "ACME", "MAAS")] + txns)
    led = normalize(raw, AS_OF)
    q = select_category_triage(led, windows(AS_OF, 1)[0], k=5)
    by = {x["merchant_id"]: x for x in q}

    check("triyaj: tanınan işyeri sorulmaz", "migros" not in by)
    check("triyaj: 5 işlem TEK soruya toplandı",
          any(x["adet"] == 5 for x in q), [(x['merchant_id'], x['adet']) for x in q])
    check("triyaj: tutara göre sıralı",
          q == sorted(q, key=lambda x: -x["tutar"]))
    check("triyaj: pazaryeri de aday — işyeri belli, içerik değil",
          "trendyol" in by and "pazaryeri" in by["trendyol"]["neden"])
    # Kullanıcıya verilen söz "cevabın HEPSİNE uygulanır" olduğuna göre
    # gösterilen adet TÜM geçmişi kapsamalı, yalnızca pencereyi değil.
    # Aksi hâlde kart 2 işlem vaat ederken cevap 4'ünü düzeltir ve
    # ekranda yazan sayı ile yapılan iş tutmaz.
    check("triyaj: toplam adet raporlanıyor",
          all("toplam_adet" in x and x["toplam_adet"] >= x["adet"] for x in q),
          [(x["merchant_id"], x["adet"], x.get("toplam_adet")) for x in q])

    # Zaten düzeltilmiş işyeri bir daha sorulmaz.
    txns2 = [T("cc", 10, -3_000, "BILINMEYEN BBB", "POS")]
    raw2 = RD([CH, _cc()], [T("ch", 25, 40_000, "ACME", "MAAS")] + txns2)
    normalize(raw2, AS_OF)
    mid = txns2[0].merchant_id
    txns3 = [T("cc", 10, -3_000, "BILINMEYEN BBB", "POS")]
    raw3 = RD([CH, _cc()], [T("ch", 25, 40_000, "ACME", "MAAS")] + txns3,
              category_overrides={mid: "ev"})
    led3 = normalize(raw3, AS_OF)
    q3 = select_category_triage(led3, windows(AS_OF, 1)[0], k=5)
    check("triyaj: cevaplanmış işyeri tekrar sorulmaz",
          mid not in {x["merchant_id"] for x in q3})

    # Faiz/ücret bir işyeri değildir; sorulacak bir şey yok.
    txns4 = [T("cc", 10, -6_693, "ALIŞVERİŞ FAİZİ", "")]
    raw4 = RD([CH, _cc()], [T("ch", 25, 40_000, "ACME", "MAAS")] + txns4)
    led4 = normalize(raw4, AS_OF)
    q4 = select_category_triage(led4, windows(AS_OF, 1)[0], k=5)
    check("triyaj: faiz/ücret aday değil",
          "faiz_ucret" not in {x["merchant_id"] for x in q4})


def t_altin_doviz_birikimdir_ama_kartla_degil():
    """Kuyumcudan alım tasarruftur — likit hesaptan yapıldıysa."""
    # Türkiye'de hanehalkı altını birikim aracı olarak alır. "Harcama"
    # sayılırsa hem gider şişer hem tasarruf eksik ölçülür: kullanıcı
    # gerçekte biriktirirken savruk görünür.
    raw = RD([CH, _cc()], [
        T("ch", 25, 40_000, "ACME", "MAAS ODEMESI"),
        T("ch", 20, -10_000, "HAS KUYUMCU/ANKARA", "POS"),
        T("cc", 18, -10_000, "HAS KUYUMCU/ANKARA", "POS"),
    ])
    led = normalize(raw, AS_OF)
    w = windows(AS_OF, 1)[0]
    likit = next(t for t in raw.transactions if t.account_id == "ch"
                 and "KUYUMCU" in (t.merchant_raw or ""))
    kartli = next(t for t in raw.transactions if t.account_id == "cc")

    check("altın: likit hesaptan alım birikim sayılır",
          likit.kind == TxnKind.SAVINGS_CONTRIB, likit.kind.value)
    # FİNANSMAN KOŞULU: %51 faizle borçlanıp altın almak tasarruf değildir.
    # Tasarruf sayarsak P3 yükselirken P2'deki gerçek kötüleşme görünmez
    # olur — model kendi kendini kandırır.
    check("altın: KARTLA alım birikim SAYILMAZ",
          kartli.kind == TxnKind.PURCHASE, kartli.kind.value)
    check("altın: yalnızca likit finansman birikim akışına girer",
          abs(led.savings_flow(w) - 10_000) < 1, f"{led.savings_flow(w):,.0f}")


def t_altin_kelime_tuzagi():
    """'ALTIN' içeren yer adları altın alımı sayılmamalı."""
    # Gerçek bir ekstrede "ALTIN" üç kez geçiyordu ve hiçbiri altın alımı
    # değildi: "ALTINDAĞ" (Ankara ilçesi) ve "altındaki" (sıradan kelime).
    # Çıplak desen üçünü de yakalar ve HARCAMAYI TASARRUF sanar — yani
    # skoru yukarı yönde şişiren, sessiz bir hata.
    raw = RD([CH], [
        T("ch", 25, 40_000, "ACME", "MAAS ODEMESI"),
        T("ch", 20, -500, "ALTINDAĞ MARKET", "POS"),
        T("ch", 19, -300, "ALTINDAKI CAFE", "POS"),
        T("ch", 18, -800, "ALTINPARK AVM", "POS"),
    ])
    led = normalize(raw, AS_OF)
    for t in raw.transactions[1:]:
        check(f"altın tuzağı: {t.merchant_raw[:14]!r} birikim değil",
              t.kind == TxnKind.PURCHASE, t.kind.value)
    check("altın tuzağı: birikim akışı sıfır",
          abs(led.savings_flow(windows(AS_OF, 1)[0])) < 1)


def t_category_version_fingerprint():
    """Kategorizasyon değiştiyse CATEGORY_VERSION bumplanmalı."""
    # ELLE BUMPLANAN SÜRÜM KAÇINILMAZ OLARAK KAYAR. Biri sözlüğe marka
    # ekler, sürümü bumplamayı unutur — ve o andan sonra sürüm YALAN
    # söyler. Yalan söyleyen sürüm, olmayandan kötüdür: skor farkını
    # uzlaştırırken ona güvenirsin.
    #
    # Bu test tam olarak bu oturumda dokümanlarda yaşanan sapmanın
    # kod tarafındaki karşılığını engeller.
    hesaplanan = category_fingerprint()
    check("sürüm: parmak izi CATEGORY_VERSION ile uyumlu",
          hesaplanan == CATEGORY_FINGERPRINT,
          f"\n      hesaplanan : {hesaplanan}"
          f"\n      beyan      : {CATEGORY_FINGERPRINT}"
          f"\n      → Kategorizasyonu etkileyen bir şey değişmiş."
          f"\n        CATEGORY_VERSION'ı bumpla ve CATEGORY_FINGERPRINT'i"
          f"\n        '{hesaplanan}' yap.")

    # Parmak izi gerçekten DUYARLI olmalı — değişikliği kaçırırsa işe yaramaz.
    import markalar as _mk
    orij = _mk.MARKALAR[:]
    try:
        _mk.MARKALAR.append(_mk.Marka("test_x", "Test", r"TESTX", "diger"))
        check("sürüm: parmak izi sözlük değişimine duyarlı",
              category_fingerprint() != CATEGORY_FINGERPRINT)
    finally:
        _mk.MARKALAR[:] = orij
    check("sürüm: geri alınca parmak izi eski hâline döner",
          category_fingerprint() == CATEGORY_FINGERPRINT)


def t_kategori_telemetrisi_tutar_agirlikli():
    """Telemetri adet değil TUTAR kırılımı vermeli."""
    # Adet yanıltıcıdır: 12 tane 30 TL'lik scooter işlemi, tek bir
    # 12.000 TL'lik taksitten daha çok "kapsam" gibi görünür. Oysa
    # `e_essential`'i belirleyen tutardır — yatırım kararı ona bakmalı.
    txns = ([T("cc", 20 - i, -30, "HOP SCOOTER/ANKARA", "POS") for i in range(12)]
            + [T("cc", 5, -12_000, "BILINMEYEN BUYUK", "POS")])
    raw = RD([CH, _cc()], [T("ch", 25, 40_000, "ACME", "MAAS")] + txns)
    led = normalize(raw, AS_OF)
    tel = category_telemetry(led, windows(AS_OF, 1)[0])

    check("telemetri: sürüm raporlanıyor",
          tel["category_version"] == CATEGORY_VERSION)
    check("telemetri: 12 küçük işlem kapsamı ŞİŞİRMİYOR",
          tel["katman_pay"].get("marka", 0) < 0.05,
          f"marka payı={tel['katman_pay'].get('marka')}")
    check("telemetri: tek büyük çekimser satır payı domine ediyor",
          tel["cekimser_payi"] > 0.95, f"{tel['cekimser_payi']}")
    # Ağırlığı bilinmeyen pay = tahmin edicinin ekstrapoladığı kısım.
    check("telemetri: bilinmeyen ağırlık payı raporlanıyor",
          tel["bilinmeyen_agirlik_payi"] > 0.95,
          f"{tel['bilinmeyen_agirlik_payi']}")


def t_marka_sozlugu_korumalari():
    """Sözlük kendi kendini denetlemeli — 282 deseni göz kararı okuyamayız."""
    import markalar as _mk

    # 1) DESEN GÜVENLİĞİ — hiçbir marka deseni sıradan Türkçe metni
    #    yakalamamalı. Elle yakalananlar: ŞOK→SOK (sokak), DOLAP (mobilya),
    #    ASKI (giysi askısı), GAIN (vergi), KARACA (mezarlık), MİSLİ (kat).
    #    Sözlük 164→282'ye çıkarken bunların üçünü BU KONTROL buldu.
    check("sözlük: hiçbir desen sıradan metni yakalamıyor",
          not _mk.desen_guvenligi(), _mk.desen_guvenligi()[:3])

    # 2) GÖLGELEME — genel desen daha özelini örtmemeli. "ZARA HOME" bir
    #    ev mağazasıdır ama çıplak `\bZARA\b` listede önce geldiği için
    #    onu giyim sanıyordu. İkisi de "çalışıyor" göründüğü için elle
    #    fark edilmesi zor.
    check("sözlük: marka kendi adında gölgelenmiyor",
          not _mk.golgeleme_kontrolu(), _mk.golgeleme_kontrolu()[:3])

    # Korumaların GERÇEKTEN çalıştığı: bozuk desen eklenince yakalanmalı.
    import re as _re
    orij_m, orij_d = _mk.MARKALAR[:], _mk._DERLI[:]
    try:
        kotu = _mk.Marka("test_kotu", "Test", r"\bSOK\b", "market")
        _mk.MARKALAR.append(kotu)
        _mk._DERLI.append((_re.compile(kotu.desen), kotu))
        check("sözlük: riskli desen YAKALANIYOR", bool(_mk.desen_guvenligi()))
    finally:
        _mk.MARKALAR[:], _mk._DERLI[:] = orij_m, orij_d
    check("sözlük: geri alınca temiz", not _mk.desen_guvenligi())


def t_merchant_key():
    check("merchant: gürültü temizlenir",
          _merchant_key("MIGROS TIC A.S IST *4471") == _merchant_key("MIGROS TIC SUBE 12"),
          f"{_merchant_key('MIGROS TIC A.S IST *4471')} vs {_merchant_key('MIGROS TIC SUBE 12')}")


# ── Zorunlu/isteğe bağlı ağırlıklandırma ─────────────────────────────────────

def t_essential_weighting():
    check("taksonomi: bilinen ağırlıklar [0,1]",
          all(0.0 <= c.essential_weight <= 1.0 for c in CATEGORIES.values()
              if c.essential_weight is not None))
    # None = "bilinmiyor", 0.0 = "ölçtük, sıfır çıktı". Bu ayrım modelin
    # `None ≠ 0` temel kuralının taksonomi düzeyindeki karşılığıdır.
    check("taksonomi: pazaryeri ağırlığı BİLİNMİYOR",
          CATEGORIES["pazaryeri"].essential_weight is None)
    check("taksonomi: 'diğer' ağırlığı BİLİNMİYOR",
          CATEGORIES["diger"].essential_weight is None)
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

def t_essential_estimator_not_biased():
    """Bilinmeyen kategori `ef_months`'u İYİMSER yönde saptırmamalı.

    `e_essential` bir PAYDADIR: `ef_months = ef_liquid / e_essential`.
    Bilinmeyen harcamayı toplamdan düşmek paydayı küçültür ve acil fon
    daha uzun dayanıyor GÖSTERİR — yani veri eksikliği ödüle dönüşür.

    Gerçek bir kart ekstresinde ölçüldü: harcamanın %37'si bilinemezken
    naif çekimserlik ef_months'u 0,74 yerine 1,30 gösteriyordu (%76 ödül).

    Doğru davranış: bilinen kısımdaki zorunluluk oranını toplama genişlet.
    """
    # Bilinen harcamanın tamamı zorunlu (kira) → oran 1,0.
    # Bilinmeyen aynı büyüklükte → tahmin edici toplamı 1,0 ile ölçekler.
    raw = RD([CH, SAV], [
        T("ch", 20, 40_000, "ACME", "MAAS ODEMESI"),
        T("ch", 15, -10_000, "KIRA ODEMESI", "EV SAHIBI"),      # 1,00 bilinir
        T("ch", 14, -10_000, "BILINMEYEN ISYERI QQQ", "POS"),   # bilinmez
    ])
    feats, _ = build_features(raw, AS_OF)
    check("tahmin edici: bilinmeyen toplama genişletildi",
          abs(feats.e_essential - 20_000) < 1,
          f"e_essential={feats.e_essential:,.0f} (beklenen 20.000; "
          f"naif çekimserlikte 10.000 çıkardı)")

    # Karşı yön: bilinen kısım tamamen isteğe bağlıysa oran 0 olmalı.
    raw2 = RD([CH, SAV], [
        T("ch", 20, 40_000, "ACME", "MAAS ODEMESI"),
        T("ch", 15, -10_000, "CINEMAXIMUM", "POS"),             # 0,00 bilinir
        T("ch", 14, -10_000, "BILINMEYEN ISYERI QQQ", "POS"),
    ])
    f2, _ = build_features(raw2, AS_OF)
    check("tahmin edici: sıfır oran da genişletilir",
          abs(f2.e_essential) < 1, f"e_essential={f2.e_essential:,.0f}")

    # Hiç bilinen yoksa 0 döner → ef_months e_total'a düşer (en muhafazakâr).
    raw3 = RD([CH, SAV], [
        T("ch", 20, 40_000, "ACME", "MAAS ODEMESI"),
        T("ch", 15, -10_000, "BILINMEYEN ISYERI QQQ", "POS"),
    ])
    f3, _ = build_features(raw3, AS_OF)
    check("tahmin edici: hiç bilgi yoksa e_total'a düşer",
          f3.e_essential == 0.0 and f3.ef_months == f3.ef_liquid / f3.e_total,
          f"e_essential={f3.e_essential}, ef_months={f3.ef_months:.2f}")


def t_pazaryeri_agirlik_uydurmaz():
    """Pazaryeri satırı sabit bir zorunluluk ağırlığı TAŞIMAZ."""
    # "İşyerini biliyoruz, ne alındığını bilmiyoruz." Trendyol'dan alınan
    # şey giyim de olabilir elektronik de market de; sabit ağırlık vermek
    # bilinmeyen hakkında iddiada bulunmaktır.
    check("pazaryeri ağırlığı None", CATEGORIES["pazaryeri"].essential_weight is None)
    check("pazaryeri 'diğer'den ayrı bir kategori",
          "pazaryeri" in CATEGORIES and CATEGORIES["pazaryeri"].label == "Pazaryeri")


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
         t_n7_refund, t_n8_outlier, t_n9_categorization,
         t_n9_turkish_folding, t_n9_payment_intermediary_unwrapped,
         t_n9_generic_turkish_patterns, t_merchant_key,
         t_essential_weighting, t_essential_estimator_not_biased,
         t_pazaryeri_agirlik_uydurmaz, t_marka_sozlugu_kisa_desen_tuzagi,
         t_marka_kanonik_kimlik, t_marka_sozlugu_korumalari,
         t_faiz_ucret_tuketim_sayilmaz,
         t_turkce_katlama_tur_siniflandirmada,
         t_isyeri_hafizasi_kalicidir, t_hafiza_marka_sozlugunu_ezer,
         t_kategori_triyaji_isyeri_bazli,
         t_altin_doviz_birikimdir_ama_kartla_degil, t_altin_kelime_tuzagi,
         t_category_version_fingerprint,
         t_kategori_telemetrisi_tutar_agirlikli,
         t_short_history_not_penalized,
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
