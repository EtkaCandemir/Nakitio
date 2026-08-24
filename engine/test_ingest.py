"""
Nakitio — Ekstre Alımı ve Davranış Çıkarımı Testleri

Çalıştırma:
    python3 engine/test_ingest.py
"""

from __future__ import annotations

import dataclasses
import sys
from datetime import date, datetime, timedelta

from behavior_infer import (
    CATEGORY_IMPULSE_PRIOR, Signals, calibrate_intercept, emotion_probability,
    estimate_behavior, impulse_probability, select_for_triage,
)
from data_model import Account, AccountType, BehaviorTag, RawData, Transaction
from normalize import active_windows, build_features, normalize, windows
from score_engine import compute_score
from statement_ingest import (
    DocKind, PROFILES, PasswordRequired, effective_as_of, import_statement,
    load_pdf_statement, missing_months, parse_amount, parse_date,
    parse_statement, statement_coverage, txn_fingerprint,
)

FAILS: list = []
PASSES = 0


def check(name, cond, detail=""):
    global PASSES
    if cond:
        PASSES += 1
    else:
        FAILS.append(name + (f"  — {detail}" if detail else ""))


# ─────────────────────────────────────────────────────────────────────────────
# Örnek ekstre metinleri
# ─────────────────────────────────────────────────────────────────────────────

CSV_ACCOUNT = """\
Tarih;Açıklama;Tutar
05.07.2026;MAAS ODEMESI ACME TEKNOLOJI;24.000,00
08.07.2026;MIGROS TIC A.S IST *4471;-1.284,50
12.07.2026;KREDI KARTI ODEME;-8.420,00
15.07.2026;KENDI HESABIMA VIRMAN;-2.828,00
18.07.2026;SHELL PETROL;-1.150,75
"""

CSV_DEBIT_CREDIT = """\
Tarih;Açıklama;Borç;Alacak
05.07.2026;MAAS ODEMESI;;24.000,00
08.07.2026;A101 YENI MAGAZA;842,30;
09.07.2026;IGDAS DOGALGAZ;1.240,00;
"""

CARD_PDF = """\
XYZ BANKASI KREDİ KARTI EKSTRESİ
Kart No: 5218 **** **** 4471
Dönem Başlangıcı: 19.06.2026
Ekstre Kesim Tarihi: 18.07.2026
Son Ödeme Tarihi: 28.07.2026
Dönem Borcu: 8.500,00
Asgari Ödeme Tutarı: 1.700,00

İşlem Tarihi  Açıklama                              Tutar
20.06.2026    STARBUCKS KANYON                      184,00
22.06.2026    TEKNOSA TAKSIT 1/6                    900,00
25.06.2026    ZARA AKMERKEZ                         1.450,00
02.07.2026    YEMEKSEPETI ONLINE                    312,50
08.07.2026    ZARA AKMERKEZ IADE                    1.450,00
10.07.2026    BOYNER (1/4)                          900,00
15.07.2026    ODEME - TESEKKURLER                   8.420,00
"""


#: VakıfBank "Kredi Kartı Hesap Özeti (TL)" düzeni.
#:
#: İçeriği SENTETİKtir — gerçek bir ekstrenin YAPISI çıkarılıp uydurma
#: tutar ve işyerleriyle yeniden kurulmuştur; kişisel veri içermez.
#: Ama gerçek dosyadaki dört tuzağın DÖRDÜ de bilerek korunmuştur:
#:
#:   1. EN ondalık biçim — "1,234.56" (virgül BİNLİK, nokta ONDALIK).
#:      `decimal="tr"` ile okunursa 1,23 çıkar: 1000 kat hata, sessiz.
#:   2. Sonda WORLDPUAN sütunu — çıplak tam sayı, tutar sanılabilir.
#:   3. KALAN TAKSİT sütunu — "3x1,200.00" ya da "Son Taksit".
#:      Açıklamada yalnız SIRA var ("4. Taksit"), toplam adet burada.
#:   4. "ÖNCEKİ DÖNEM ... BAKİYENİZ" satırı işlem düzenindedir ama
#:      işlem DEĞİLDİR; elenmezse devir bakiyesi kadar hayalî harcama doğar.
VAKIF_CARD_PDF = """\
Kredi Kartı Hesap Özeti (TL)
HESAP BİLGİLERİNİZ
Dönem Borcunuz : 48,320.50 TL
Asgari Ödeme Tutarı : 19,328.20 TL
Son Ödeme Tarihi : 23.07.2026
Kart No : 5521********9660
Limitiniz : 90,000.00 TL
Hesap Kesim Tarihi : 13.07.2026
İŞLEM TARİHİ AÇIKLAMA TUTAR (TL) KALAN TAKSİT WORLDPUAN
13.06.2026 ÖNCEKİ DÖNEM HESAP ÖZETİ BAKİYENİZ 40,000.00
15.01.2026 BEYAZ ESYA MAGAZASI 6. Taksit 1,200.00 3x1,200.00
20.06.2026 MARKET ALISVERISI 850.25 255
21.06.2026 AKARYAKIT ISTASYONU 2,000.00 600
22.06.2026 ONLINE MAGAZA 4. Taksit 750.00 Son Taksit
25.06.2026 ÖDEMENİZ İÇİN TEŞEKKÜRLER +12,000.00
28.06.2026 KITAPCI 320.00 96 *
01.07.2026 İADE/ ONLINE MAGAZA +450.00
13.07.2026 ALIŞVERİŞ FAİZİ (Oran:4.25) 1,700.25
HESAP ÖZETİ
Önceki Hesap Bakiyesi 40,000.00
Dönem Borcunuz 48,320.50
"""


# ─────────────────────────────────────────────────────────────────────────────
# Ayrıştırma
# ─────────────────────────────────────────────────────────────────────────────

def t_amount_parsing():
    check("tutar: TR biçim", parse_amount("1.284,50") == 1284.50)
    check("tutar: negatif", parse_amount("-8.420,00") == -8420.0)
    check("tutar: sondaki eksi", parse_amount("842,30-") == -842.30)
    check("tutar: TL eki", parse_amount("1.150,75 TL") == 1150.75)
    check("tutar: EN biçim", parse_amount("1,284.50", "en") == 1284.50)
    check("tutar: boş → None", parse_amount("") is None)
    check("tarih: nokta", parse_date("05.07.2026", ("%d.%m.%Y",)) == date(2026, 7, 5))
    check("tarih: eşleşmezse None", parse_date("2026-07-05", ("%d.%m.%Y",)) is None)


def t_parse_account_csv():
    st = parse_statement(CSV_ACCOUNT, "tr_generic_account_csv")
    check("CSV: 5 satır ayrıştı", len(st.rows) == 5, f"{len(st.rows)}")
    check("CSV: gelir pozitif", st.rows[0].amount == 24_000.0)
    check("CSV: harcama negatif", st.rows[1].amount == -1284.50)
    check("CSV: dönem çıkarıldı",
          st.period_start == date(2026, 7, 5) and st.period_end == date(2026, 7, 18))


def t_parse_debit_credit():
    st = parse_statement(CSV_DEBIT_CREDIT, "tr_generic_account_debit_credit")
    check("borç/alacak: 3 satır", len(st.rows) == 3)
    check("borç/alacak: alacak pozitif", st.rows[0].amount == 24_000.0)
    check("borç/alacak: borç negatif", st.rows[1].amount == -842.30,
          f"{st.rows[1].amount}")


def t_parse_card_pdf():
    st = parse_statement(CARD_PDF, "tr_generic_card_pdf")
    check("kart: satırlar ayrıştı", len(st.rows) == 7, f"{len(st.rows)}")
    check("kart: dönem başı", st.period_start == date(2026, 6, 19))
    check("kart: kesim tarihi", st.period_end == date(2026, 7, 18))
    check("kart: son ödeme", st.due_date == date(2026, 7, 28))
    check("kart: dönem borcu", st.closing_balance == 8_500.0)
    check("kart: asgari ödeme", st.minimum_payment == 1_700.0)
    check("kart: kart no maskeli okundu", (st.account_ref or "").endswith("4471"))

    by = {r.description.split()[0]: r for r in st.rows}
    check("kart: harcama negatife çevrildi", by["STARBUCKS"].amount == -184.0)
    check("kart: ödeme satırı pozitif", by["ODEME"].amount == 8_420.0,
          f"{by['ODEME'].amount}")
    check("kart: iade satırı pozitif",
          any(r.amount > 0 and "IADE" in r.description for r in st.rows))


def t_installment_detection():
    st = parse_statement(CARD_PDF, "tr_generic_card_pdf")
    tk = next(r for r in st.rows if "TEKNOSA" in r.description)
    bo = next(r for r in st.rows if "BOYNER" in r.description)
    check("taksit: 'TAKSIT 1/6' okundu",
          (tk.installment_index, tk.installment_count) == (1, 6))
    check("taksit: '(1/4)' okundu",
          (bo.installment_index, bo.installment_count) == (1, 4))
    normal = next(r for r in st.rows if "STARBUCKS" in r.description)
    check("taksit: normal satırda taksit yok", normal.installment_count is None)


def t_parse_vakifbank_card():
    """VakıfBank düzeni — gerçek ekstreyle doğrulanan dört tuzak."""
    st = parse_statement(VAKIF_CARD_PDF, "tr_vakifbank_card_pdf")

    # ── Tuzak 1: EN ondalık biçim ──────────────────────────────────────
    # Gerçek dosyada jenerik profil asgari ödemeyi 117.260,00 yerine
    # 117,26 okumuştu. Yanlış ondalık biçimi UYARI ÜRETMEZ; makul
    # görünen ama üç basamak yanlış bir sayı döndürür.
    check("vakıf: dönem borcu EN biçimle okundu",
          st.closing_balance == 48_320.50, f"{st.closing_balance}")
    check("vakıf: asgari ödeme EN biçimle okundu",
          st.minimum_payment == 19_328.20, f"{st.minimum_payment}")
    check("vakıf: asgari ödeme 1000 kat küçülmedi",
          st.minimum_payment > 1_000)

    check("vakıf: kesim tarihi", st.period_end == date(2026, 7, 13))
    check("vakıf: son ödeme tarihi", st.due_date == date(2026, 7, 23))
    check("vakıf: kart no maskeli okundu",
          (st.account_ref or "").endswith("9660"))

    # ── Tuzak 4: devir bakiyesi işlem sayılmamalı ──────────────────────
    check("vakıf: devir bakiyesi elendi", st.excluded == 1, f"{st.excluded}")
    check("vakıf: devir bakiyesi işleme girmedi",
          not any("BAKİYENİZ" in r.description for r in st.rows))
    check("vakıf: 40.000 TL'lik hayalî harcama yok",
          not any(abs(r.amount) == 40_000.0 for r in st.rows))

    by = {r.description.split()[0]: r for r in st.rows}

    # ── Tuzak 2: sondaki WORLDPUAN tutar sanılmamalı ───────────────────
    check("vakıf: worldpuan tutar olarak okunmadı",
          by["MARKET"].amount == -850.25, f"{by['MARKET'].amount}")
    check("vakıf: sondaki yıldız satırı bozmadı",
          by["KITAPCI"].amount == -320.00, f"{by['KITAPCI'].amount}")

    # İşaret: harcama çıkış (negatif), ödeme ve iade giriş (pozitif).
    check("vakıf: ödeme satırı pozitif",
          by["ÖDEMENİZ"].amount == 12_000.00, f"{by['ÖDEMENİZ'].amount}")
    check("vakıf: iade satırı pozitif",
          any(r.amount == 450.00 and "İADE" in r.description for r in st.rows))


def t_vakifbank_installment_columns():
    """'6. Taksit' + ayrı kalan sütunu → toplam adet türetilir."""
    st = parse_statement(VAKIF_CARD_PDF, "tr_vakifbank_card_pdf")
    by = {r.description.split()[0]: r for r in st.rows}

    # ── Tuzak 3 ────────────────────────────────────────────────────────
    # Açıklama yalnız SIRAyı söyler; kaç taksit KALDIĞI ayrı sütundadır.
    # toplam = sıra + kalan. Varsayılan INSTALLMENT_RE ("TAKSIT 3/12")
    # bu düzeni göremez; gerçek ekstrede 16 taksitli satırın 16'sı da
    # tanınmıyor ve kalan taahhüt görünmez kalıyordu.
    check("vakıf: '6. Taksit' + '3x' → 6/9",
          (by["BEYAZ"].installment_index, by["BEYAZ"].installment_count) == (6, 9),
          f"{by['BEYAZ'].installment_index}/{by['BEYAZ'].installment_count}")
    check("vakıf: 'Son Taksit' → sıra = toplam",
          (by["ONLINE"].installment_index, by["ONLINE"].installment_count) == (4, 4),
          f"{by['ONLINE'].installment_index}/{by['ONLINE'].installment_count}")
    check("vakıf: taksitsiz satırda plan yok",
          by["MARKET"].installment_count is None)

    # Kalan taahhüt COMMIT oranının girdisidir — Borç Yükü'nün dörtte biri.
    kalan = sum((r.installment_count - r.installment_index) * abs(r.amount)
                for r in st.rows if r.installment_count)
    check("vakıf: kalan taahhüt türetildi", kalan == 3_600.0, f"{kalan}")


def t_vakifbank_generic_profile_fails_loudly():
    """Jenerik kart profili bu dosyada SESSİZ kalmamalı."""
    st = parse_statement(VAKIF_CARD_PDF, "tr_generic_card_pdf")
    check("vakıf: jenerik profil hiç satır bulamaz", len(st.rows) == 0)
    check("vakıf: jenerik profil uyarı üretir",
          any("eşleşmedi" in w for w in st.warnings))


def t_bad_profile_warns():
    st = parse_statement(CARD_PDF, "tr_generic_account_csv")
    check("yanlış profil sessizce geçmez",
          bool(st.warnings) or len(st.rows) == 0,
          f"satır={len(st.rows)} uyarı={st.warnings}")


# ─────────────────────────────────────────────────────────────────────────────
# İçe aktarma ve tekilleştirme
# ─────────────────────────────────────────────────────────────────────────────

def _raw() -> RawData:
    return RawData(user_id="t", accounts=[
        Account("ch", AccountType.CHECKING, balance=10_000, is_linked=False),
        Account("cc", AccountType.CREDIT_CARD, balance=8_500,
                credit_limit=25_000, is_linked=False),
    ])


def t_import_and_dedup():
    """EN KRİTİK: aynı ekstre iki kez yüklenirse işlemler ÇİFTLENMEMELİ."""
    raw = _raw()
    st = parse_statement(CSV_ACCOUNT, "tr_generic_account_csv")

    r1 = import_statement(raw, st, "ch")
    check("içe aktarma: 5 işlem eklendi", r1.added == 5, f"{r1.added}")

    r2 = import_statement(raw, st, "ch")
    check("tekilleştirme: ikinci yükleme 0 ekledi", r2.added == 0, f"{r2.added}")
    check("tekilleştirme: 5 mükerrer tespit edildi", r2.duplicates == 5)
    check("tekilleştirme: toplam işlem 5 kaldı", len(raw.transactions) == 5,
          f"{len(raw.transactions)}")
    check("ekstre kimliği kararlı", st.key == parse_statement(
        CSV_ACCOUNT, "tr_generic_account_csv").key)


def t_overlapping_periods():
    """Dönemler üst üste binerse yalnızca yeni işlemler eklenmeli."""
    raw = _raw()
    first = parse_statement(CSV_ACCOUNT, "tr_generic_account_csv")
    import_statement(raw, first, "ch")

    extended = CSV_ACCOUNT + "25.07.2026;BIM BIRLESIK MAGAZA;-640,00\n"
    second = parse_statement(extended, "tr_generic_account_csv")
    r = import_statement(raw, second, "ch")
    check("örtüşen dönem: yalnızca yeni satır eklendi", r.added == 1, f"{r.added}")
    check("örtüşen dönem: eskiler mükerrer sayıldı", r.duplicates == 5)


def t_card_import_gives_debt_snapshot():
    """Kart ekstresi dönem sonu borcu → debt_principal_history.

    Bu, veri katmanında eksik bırakılan girdiydi: onsuz borç trendi alt
    metriği (20 puanlık bileşenin %15'i) hep kapalı kalıyordu.
    """
    raw = _raw()
    st = parse_statement(CARD_PDF, "tr_generic_card_pdf")
    r = import_statement(raw, st, "cc")
    check("kart: borç anlık görüntüsü alındı",
          r.debt_snapshot == (date(2026, 7, 18), 8_500.0), f"{r.debt_snapshot}")
    check("kart: geçmişe yazıldı", raw.debt_principal_history == [
        (date(2026, 7, 18), 8_500.0)])
    import_statement(raw, st, "cc")
    check("kart: anlık görüntü çiftlenmedi",
          len(raw.debt_principal_history) == 1)


def t_fingerprint_sensitivity():
    fp = txn_fingerprint("ch", date(2026, 7, 8), -100.0, "MIGROS  TIC")
    check("parmak izi: boşluk normalleşir",
          fp == txn_fingerprint("ch", date(2026, 7, 8), -100.0, "migros tic"))
    check("parmak izi: tutar farkı ayırır",
          fp != txn_fingerprint("ch", date(2026, 7, 8), -100.5, "MIGROS TIC"))
    check("parmak izi: hesap farkı ayırır",
          fp != txn_fingerprint("cc", date(2026, 7, 8), -100.0, "MIGROS TIC"))


# ─────────────────────────────────────────────────────────────────────────────
# Kapsam ve tarih
# ─────────────────────────────────────────────────────────────────────────────

def t_coverage_and_gaps():
    periods = [(date(2026, 7, 1), date(2026, 7, 31)),
               (date(2026, 6, 1), date(2026, 6, 30)),
               (date(2026, 4, 1), date(2026, 4, 30))]
    cov = statement_coverage(periods, date(2026, 7, 31), months=6)
    check("kapsam: 3/6 dönem", abs(cov - 0.5) < 1e-9, f"{cov}")
    gaps = missing_months(periods, date(2026, 7, 31), months=6)
    check("boşluk: eksik aylar bulundu",
          gaps == ["2026-02", "2026-03", "2026-05"], f"{gaps}")


def t_effective_as_of():
    """Hesaplama tarihi bugün değil, SON EKSTRE tarihi olmalı.

    Ekstre 18'inde kesiliyorsa 31'inde `as_of=bugün` almak, son 13 günü
    'sıfır harcama' saymak demektir: nakit akışı marjı yapay yükselir ve
    kullanıcıya olmayan bir iyileşme gösterilir.
    """
    periods = [(date(2026, 6, 19), date(2026, 7, 18))]
    check("as_of: son ekstre tarihine çekildi",
          effective_as_of(periods, date(2026, 7, 31)) == date(2026, 7, 18))
    check("as_of: gelecek tarihli ekstrede bugün korunur",
          effective_as_of([(date(2026, 7, 1), date(2026, 9, 1))],
                          date(2026, 7, 31)) == date(2026, 7, 31))
    check("as_of: ekstre yoksa bugün", effective_as_of([], date(2026, 7, 31))
          == date(2026, 7, 31))


def t_password_required():
    def failing(data, password):
        if password != "1234":
            raise ValueError("encrypted")
        return CARD_PDF

    try:
        load_pdf_statement(b"x", "tr_generic_card_pdf", failing, password=None)
        check("parola: eksik parolada hata", False, "istisna atılmadı")
    except PasswordRequired as e:
        check("parola: eksik parolada hata", True)
        check("parola: ipucu döndü", bool(e.hint))

    st = load_pdf_statement(b"x", "tr_generic_card_pdf", failing, password="1234")
    check("parola: doğru parolayla ayrıştı", len(st.rows) == 7)


# ─────────────────────────────────────────────────────────────────────────────
# Davranış çıkarımı
# ─────────────────────────────────────────────────────────────────────────────

def t_impulse_signal_directions():
    base = Signals(category="restoran", amount=500)
    p0 = impulse_probability(base)

    check("çıkarım: yinelenen ödeme plansızlığı düşürür",
          impulse_probability(dataclasses.replace(base, recurring=True)) < p0)
    check("çıkarım: yeni merchant yükseltir",
          impulse_probability(dataclasses.replace(base, merchant_novel=True)) > p0)
    check("çıkarım: tutar sapması yükseltir",
          impulse_probability(dataclasses.replace(base, amount_z=3.0)) > p0)
    check("çıkarım: aynı gün kümelenme yükseltir",
          impulse_probability(dataclasses.replace(base, cluster_size=4)) > p0)
    check("çıkarım: iade güçlü biçimde yükseltir",
          impulse_probability(dataclasses.replace(base, refunded=True)) > p0 + 0.2)
    check("çıkarım: gece yükseltir",
          impulse_probability(dataclasses.replace(base, night=True)) > p0)
    check("çıkarım: saat bilinmiyorsa etkisiz",
          impulse_probability(dataclasses.replace(base, night=None)) == p0)

    check("çıkarım: kira ≪ şans oyunu",
          impulse_probability(Signals(category="kira", amount=500)) <
          impulse_probability(Signals(category="sans_oyunu", amount=500)))
    check("çıkarım: yinelenen kira neredeyse sıfır",
          impulse_probability(Signals(category="kira", amount=500,
                                      recurring=True)) < 0.05)
    check("çıkarım: olasılık [0,1]",
          all(0 <= impulse_probability(Signals(category=c, amount=1)) <= 1
              for c in CATEGORY_IMPULSE_PRIOR))


def t_emotion_is_weak_by_design():
    """Duygu çıkarımı bilerek zayıf ve dar kapsamlı."""
    check("duygu: rahatlama dışı kategori ~0",
          emotion_probability(Signals(category="faturalar", amount=500)) < 0.05)
    hot = emotion_probability(Signals(category="eglence", amount=500, night=True,
                                      weekend=True, cluster_size=4, refunded=True))
    check("duygu: yığılmış sinyalde bile aşırı iddialı değil", hot < 0.90,
          f"{hot:.2f}")
    check("duygu: plansızlıktan daha temkinli",
          emotion_probability(Signals(category="restoran", amount=500)) <
          impulse_probability(Signals(category="restoran", amount=500)))


def t_calibration():
    sigs = [Signals(category="restoran", amount=100) for _ in range(30)]
    b_low = calibrate_intercept([(s, False) for s in sigs])
    b_high = calibrate_intercept([(s, True) for s in sigs])
    check("kalibrasyon: hep planlı → kesişim düşer", b_low < b_high)
    check("kalibrasyon: az örnekte varsayılana döner",
          calibrate_intercept([(sigs[0], True)]) == pytest_default())
    mixed = [(s, i % 2 == 0) for i, s in enumerate(sigs)]
    b_mid = calibrate_intercept(mixed)
    check("kalibrasyon: karışık örnekte arada", b_low < b_mid < b_high,
          f"{b_low:.2f} < {b_mid:.2f} < {b_high:.2f}")


def pytest_default() -> float:
    from behavior_infer import W
    return W["b0"]


def t_behavior_without_labels():
    """EN ÖNEMLİ: hiç etiket yokken davranış bileşeni ÇALIŞMAYA DEVAM ETMELİ."""
    from fixture_didem import AS_OF, build_raw
    raw = build_raw()
    raw.behavior_tags = []
    feats, _ = build_features(raw, AS_OF)
    r = compute_score(feats)
    p6 = next(p for p in r.pillars if p.key == "behavior")

    check("etiketsiz: davranış bileşeni açık", p6.enabled,
          p6.disabled_reason)
    check("etiketsiz: plansızlık oranı üretildi", feats.imp_rate is not None)
    check("etiketsiz: oran makul aralıkta", 0.0 < feats.imp_rate < 0.5,
          f"{feats.imp_rate}")
    check("etiketsiz: kapsam eşiğin üzerinde", feats.beh_coverage >= 0.25,
          f"{feats.beh_coverage}")


def t_labels_shift_estimate():
    """Etiket geldikçe tahmin etikete doğru kayar."""
    from fixture_didem import AS_OF, build_raw
    raw_none = build_raw()
    raw_none.behavior_tags = []
    f_none, _ = build_features(raw_none, AS_OF)

    raw_all = build_raw()
    for t in raw_all.behavior_tags:
        t.planned = False                      # hepsi plansız denmiş
    f_all, led = build_features(raw_all, AS_OF)

    check("etiket: tahmini yukarı çeker", f_all.imp_rate > f_none.imp_rate,
          f"{f_none.imp_rate:.3f} → {f_all.imp_rate:.3f}")

    W = active_windows(led, windows(AS_OF, 6))
    est = estimate_behavior(led, W[0], f_all.disc_share)
    check("etiket: ağırlık etiket sayısıyla artıyor", 0 < est.label_weight <= 1,
          f"{est.label_weight}")
    check("etiket: sayı raporlanıyor", est.label_count > 0)


def t_triage_selection():
    from fixture_didem import AS_OF, build_raw
    raw = build_raw()
    raw.behavior_tags = []
    led = normalize(raw, AS_OF)
    W = active_windows(led, windows(AS_OF, 6))
    picks = select_for_triage(led, W[0], k=10)

    check("triyaj: 10 işlem seçildi", len(picks) == 10, f"{len(picks)}")
    check("triyaj: her seçimde gerekçe var", all(p["neden"] for p in picks))
    check("triyaj: bilgi değerine göre sıralı",
          all(picks[i]["bilgi_degeri"] >= picks[i + 1]["bilgi_degeri"]
              for i in range(len(picks) - 1)))
    check("triyaj: hepsi kararsız bölgede (p uçlarda değil)",
          all(0.10 < p["tahmin_plansiz"] < 0.90 for p in picks),
          f"{[p['tahmin_plansiz'] for p in picks]}")

    # Etiketlenmiş işlemler tekrar sorulmamalı
    raw2 = build_raw()
    led2 = normalize(raw2, AS_OF)
    tagged = {t.txn_id for t in raw2.behavior_tags}
    picks2 = select_for_triage(led2, active_windows(led2, windows(AS_OF, 6))[0], k=10)
    check("triyaj: etiketli işlem tekrar sorulmaz",
          not any(p["txn_id"] in tagged for p in picks2))


# ─────────────────────────────────────────────────────────────────────────────
# Güven kademeleri
# ─────────────────────────────────────────────────────────────────────────────

def t_confidence_tiers():
    from fixture_didem import AS_OF, build_raw
    f, _ = build_features(build_raw(), AS_OF)

    linked = dataclasses.replace(f, data_source="linked", manual_entry=False,
                                 accounts_linked=4, accounts_declared=4)
    stmt = dataclasses.replace(f, data_source="statement", manual_entry=True,
                               accounts_linked=0, statement_coverage=1.0)
    stmt_half = dataclasses.replace(stmt, statement_coverage=0.5)
    manual = dataclasses.replace(f, data_source="manual", manual_entry=True,
                                 accounts_linked=0)

    c = {k: compute_score(v).confidence for k, v in
         (("linked", linked), ("statement", stmt),
          ("statement_half", stmt_half), ("manual", manual))}

    check("güven: bağlı > ekstre", c["linked"] > c["statement"],
          f"{c['linked']:.2f} vs {c['statement']:.2f}")
    check("güven: ekstre > manuel", c["statement"] > c["manual"],
          f"{c['statement']:.2f} vs {c['manual']:.2f}")
    check("güven: eksik ekstre dönemi güveni düşürür",
          c["statement"] > c["statement_half"],
          f"{c['statement']:.2f} vs {c['statement_half']:.2f}")
    check("güven: ekstre manuele değil bağlıya yakın",
          abs(c["statement"] - c["linked"]) < abs(c["statement"] - c["manual"]),
          f"{c}")


# ─────────────────────────────────────────────────────────────────────────────
# Uçtan uca: ham ekstre → skor
# ─────────────────────────────────────────────────────────────────────────────

def t_end_to_end_from_statements():
    raw = _raw()
    acc = parse_statement(CSV_ACCOUNT, "tr_generic_account_csv")
    card = parse_statement(CARD_PDF, "tr_generic_card_pdf")
    r1 = import_statement(raw, acc, "ch")
    r2 = import_statement(raw, card, "cc")

    periods = [p for p in (r1.period, r2.period) if p]
    as_of = effective_as_of(periods, date(2026, 7, 31))
    check("uçtan uca: as_of son ekstreye çekildi", as_of == date(2026, 7, 18),
          str(as_of))

    raw.income_declaration = None
    raw.accounts_declared = 2
    feats, led = build_features(raw, as_of)
    feats = dataclasses.replace(
        feats, data_source="statement",
        statement_coverage=statement_coverage(periods, as_of, months=6))
    result = compute_score(feats)

    check("uçtan uca: işlemler yüklendi", len(raw.transactions) == 12,
          f"{len(raw.transactions)}")
    check("uçtan uca: taksit planları çıkarıldı", len(led.plans) == 2,
          f"{len(led.plans)}")
    check("uçtan uca: iade eşleşti",
          led.diagnostics["refunds"]["refunds_matched"] == 1)
    check("uçtan uca: kart ödemesi gider sayılmadı",
          any(t.excluded_reason == "card_payment_to_linked_account" or
              t.kind.value == "card_payment" for t in raw.transactions))
    check("uçtan uca: skor üretildi", 0 <= result.score <= 100, str(result.score))
    check("uçtan uca: kısa geçmişte güven düşük", result.confidence < 0.6,
          f"C={result.confidence:.2f}")
    check("uçtan uca: band geniş", result.band[1] - result.band[0] >= 8,
          f"{result.band}")


TESTS = [t_amount_parsing, t_parse_account_csv, t_parse_debit_credit,
         t_parse_card_pdf, t_installment_detection,
         t_parse_vakifbank_card, t_vakifbank_installment_columns,
         t_vakifbank_generic_profile_fails_loudly, t_bad_profile_warns,
         t_import_and_dedup, t_overlapping_periods,
         t_card_import_gives_debt_snapshot, t_fingerprint_sensitivity,
         t_coverage_and_gaps, t_effective_as_of, t_password_required,
         t_impulse_signal_directions, t_emotion_is_weak_by_design,
         t_calibration, t_behavior_without_labels, t_labels_shift_estimate,
         t_triage_selection, t_confidence_tiers, t_end_to_end_from_statements]


if __name__ == "__main__":
    print("NAKITIO — EKSTRE ALIMI VE DAVRANIŞ ÇIKARIMI TESTLERİ")
    print("=" * 78)
    for t in TESTS:
        before = len(FAILS)
        t()
        mark = "FAIL" if len(FAILS) > before else "ok"
        doc = (t.__doc__ or "").strip().split("\n")[0]
        print(f"  [{mark:>4}] {t.__name__:<38} {doc[:30]}")
    print("=" * 78)
    if FAILS:
        print(f"{PASSES} geçti, {len(FAILS)} KIRILDI:\n")
        for f in FAILS:
            print(f"  ✗ {f}")
        sys.exit(1)
    print(f"{PASSES} kontrolün tamamı geçti.")
