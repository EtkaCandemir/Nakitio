"""
Nakitio — Katman 1 (Normalizasyon) + Katman 2 (Türetilmiş Metrikler)

    ham veri ─▶ [normalize] ─▶ [derive_features] ─▶ Features ─▶ score_engine

Bu katman skor motorundan DAHA kritiktir. Motor matematiksel olarak
kusursuz olsa bile, buraya yanlış girdi verilirse çıktı finansal olarak
anlamsız olur. En sık ve en pahalı hata N2'dir (kredi kartı ödemesinin
gider sayılması → her harcamanın iki kez sayılması).

Şartname: `Docs/veri-katmani-v1.md`
"""

from __future__ import annotations

import math
import re
import statistics
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta
from typing import Dict, List, Optional, Tuple

from data_model import (
    Account, AccountType, BehaviorTag, Budget, CATEGORIES, Category,
    CategorySource, CPISeries, DEFAULT_CATEGORY, EMOTIONAL_TAGS,
    EXPENSE_KINDS, Goal, InstallmentPlan, LIQUID_TYPES, Liability,
    RawData, SAVINGS_TYPES, Transaction, TxnKind, _add_months,
)
from score_engine import Features

PIPELINE_VERSION = "1.0.0"

WINDOW_DAYS = 30
N_WINDOWS = 6          # W0..W5 — 6 pencerelik geçmiş tutulur


# ─────────────────────────────────────────────────────────────────────────────
# Pencereler
# ─────────────────────────────────────────────────────────────────────────────
#
# Karar: takvim ayı DEĞİL, 30 günlük KAYAN pencere kullanılır.
#
# Gerekçe: skor günlük hesaplanır. Takvim ayı kullanılırsa ayın 1'inde
# tüm metrikler sıfırlanır ve skor her ay başı yapay bir sıçrama yapar.
# Kayan pencere bunu ortadan kaldırır. Kullanıcıya gösterilen "Temmuz
# 2026" gibi takvim etiketleri ayrı bir sunum meselesidir.

@dataclass(frozen=True)
class Window:
    start: date
    end: date        # dışlayıcı

    def contains(self, d: date) -> bool:
        return self.start <= d < self.end


def windows(as_of: date, n: int = N_WINDOWS) -> List[Window]:
    """W0 en yeni pencere: (as_of-30, as_of]."""
    out = []
    for k in range(n):
        end = as_of - timedelta(days=WINDOW_DAYS * k)
        out.append(Window(end - timedelta(days=WINDOW_DAYS), end))
    return out


# ─────────────────────────────────────────────────────────────────────────────
# N9 — Kategorizasyon
# ─────────────────────────────────────────────────────────────────────────────
#
# Üretimde bu bir ML modeli + kural motoru + kullanıcı düzeltme geri
# beslemesi olacaktır. Buradaki kural tablosu sözleşmeyi ve kalite
# ölçümünü göstermek içindir; kapsamı kasıtlı olarak sınırlıdır.

MERCHANT_RULES: List[Tuple[str, str]] = [
    (r"MIGROS|A101|BIM|ŞOK|SOK MARKET|CARREFOUR|MACROCENTER|GETIR(?! YEMEK)", "market"),
    (r"STARBUCKS|KAHVE|COFFEE|YEMEKSEPETI|GETIR YEMEK|TRENDYOL YEMEK|DOMINO|BURGER|RESTORAN|LOKANTA|CAFE", "restoran"),
    (r"SHELL|OPET|PETROL OFISI|BP |TOTAL|ISTANBULKART|IETT|METRO ISTANBUL|UBER|BITAKSI|MARTI", "ulasim"),
    (r"TURKCELL|VODAFONE|TURK TELEKOM|SUPERONLINE|TTNET", "iletisim"),
    (r"IGDAS|BEDAS|ISKI|ENERJISA|AYEDAS|ASKI|BASKENT GAZ|ELEKTRIK|DOGALGAZ|SU FATURA", "faturalar"),
    (r"NETFLIX|SPOTIFY|YOUTUBE PREMIUM|DISNEY|BLUTV|EXXEN|AMAZON PRIME|ICLOUD|GOOGLE ONE", "abonelik"),
    (r"ZARA|LC WAIKIKI|LCW|DEFACTO|KOTON|MAVI|H&M|BERSHKA|PULL&BEAR|BOYNER", "giyim"),
    (r"TEKNOSA|VATAN BILGISAYAR|MEDIAMARKT|APPLE STORE|SAMSUNG", "elektronik"),
    (r"ECZANE|HASTANE|MEDICAL|POLIKLINIK|LABORATUVAR|DENT", "saglik"),
    (r"KIRA ODEMESI|KIRA TRANSFER", "kira"),
    (r"AIDAT|SITE YONETIM|APARTMAN", "aidat"),
    (r"SIGORTA|ANADOLU SIG|AXA|ALLIANZ|KASKO|DASK", "sigorta"),
    (r"MAC FIT|MACFIT|SPORTS INTERNATIONAL|FITNESS|GYM", "spor"),
    (r"SINEMA|CINEMAXIMUM|TIYATRO|BILETIX|PASSO|KONSER|STEAM|PLAYSTATION", "eglence"),
    (r"THY|TURKISH AIRLINES|PEGASUS|BOOKING|OTEL|HOTEL|TATIL", "tatil"),
    (r"OKUL|UNIVERSITE|KURS|UDEMY|KOLEJ", "egitim"),
    (r"MILLI PIYANGO|IDDAA|NESINE|BILYONER", "sans_oyunu"),
    (r"TEKEL|ALKOL|VINOLUS", "alkol_tutun"),
    (r"WATSONS|GRATIS|ROSSMANN|KUAFOR|BERBER", "kisisel"),
    (r"IKEA|KOCTAS|BAUHAUS|ENGLISH HOME|MADAME COCO", "ev"),
    (r"VERGI|MTV|GELIR IDARESI|E-DEVLET", "vergi"),
]

MCC_RULES: Dict[str, str] = {
    "5411": "market", "5812": "restoran", "5814": "restoran",
    "5541": "ulasim", "4111": "ulasim", "5651": "giyim",
    "5912": "saglik", "4814": "iletisim", "4900": "faturalar",
    "7997": "spor", "7832": "eglence", "4722": "tatil",
}


def categorize(txns: List[Transaction], user_overrides: Dict[str, str] = None) -> Dict[str, int]:
    """Öncelik: kullanıcı düzeltmesi > kural > MCC > varsayılan."""
    user_overrides = user_overrides or {}
    stats = {"user": 0, "rule": 0, "mcc": 0, "default": 0}

    for t in txns:
        if t.id in user_overrides:
            t.category, t.category_source = user_overrides[t.id], CategorySource.USER
            stats["user"] += 1
            continue

        blob = f"{t.merchant_raw or ''} {t.description_raw or ''}".upper()
        hit = None
        for pattern, cat in MERCHANT_RULES:
            if re.search(pattern, blob):
                hit = cat
                break
        if hit:
            t.category, t.category_source = hit, CategorySource.RULE
            t.merchant_id = _merchant_key(t.merchant_raw or t.description_raw)
            stats["rule"] += 1
        elif t.mcc and t.mcc in MCC_RULES:
            t.category, t.category_source = MCC_RULES[t.mcc], CategorySource.MCC
            t.merchant_id = _merchant_key(t.merchant_raw or t.description_raw)
            stats["mcc"] += 1
        else:
            t.category, t.category_source = DEFAULT_CATEGORY, CategorySource.NONE
            t.merchant_id = _merchant_key(t.merchant_raw or t.description_raw)
            stats["default"] += 1
    return stats


def _merchant_key(s: Optional[str]) -> str:
    """Merchant adı normalleştirme: 'MIGROS TIC A.S IST *1234' → 'migros tic'.

    Yinelenen ödeme tespiti (N4) ve iade eşleştirme (N7) buna dayanır.
    """
    if not s:
        return ""
    s = s.upper()
    s = re.sub(r"[*#]\d+", " ", s)
    s = re.sub(r"\b\d{4,}\b", " ", s)
    s = re.sub(r"\b(A\.?S\.?|LTD|STI|TIC|SAN|IST|ANKARA|IZMIR|SUBE|POS)\b", " ", s)
    s = re.sub(r"[^A-ZÇĞİÖŞÜ ]", " ", s)
    return " ".join(s.split()[:2]).lower()


# ─────────────────────────────────────────────────────────────────────────────
# Tür sınıflandırma
# ─────────────────────────────────────────────────────────────────────────────

INCOME_PATTERNS = r"MAAS|MAAŞ|UCRET|ÜCRET|SERBEST MESLEK|KIRA GELIRI|FATURA TAHSIL|HAKEDIS|EMEKLI"
CARD_PAY_PATTERNS = r"KREDI KARTI ODEME|KART BORC|KKB ODEME|EKSTRE ODEME"
LOAN_PAY_PATTERNS = r"KREDI TAKSIT|IHTIYAC KREDISI|KONUT KREDISI|TASIT KREDISI|KREDI ODEME"
REFUND_PATTERNS = r"IADE|IPTAL|REFUND|CHARGEBACK"


def classify_kinds(raw: RawData) -> Dict[str, int]:
    stats: Dict[str, int] = {}
    for t in raw.transactions:
        acc = raw.account(t.account_id)
        atype = acc.type if acc else AccountType.CHECKING
        blob = f"{t.merchant_raw or ''} {t.description_raw or ''}".upper()

        if re.search(REFUND_PATTERNS, blob) and t.try_amount > 0:
            t.kind = TxnKind.REFUND
        elif atype == AccountType.CREDIT_CARD:
            # Kart hesabında: çıkış = harcama, giriş = borç ödemesi
            t.kind = TxnKind.PURCHASE if t.try_amount < 0 else TxnKind.CARD_PAYMENT
        elif atype == AccountType.LOAN:
            t.kind = TxnKind.LOAN_PAYMENT
        elif atype in SAVINGS_TYPES:
            t.kind = (TxnKind.SAVINGS_CONTRIB if t.try_amount > 0
                      else TxnKind.SAVINGS_WITHDRAW)
        elif t.try_amount > 0:
            t.kind = (TxnKind.INCOME if re.search(INCOME_PATTERNS, blob)
                      else TxnKind.TRANSFER_IN)
        else:
            if re.search(CARD_PAY_PATTERNS, blob):
                t.kind = TxnKind.CARD_PAYMENT
            elif re.search(LOAN_PAY_PATTERNS, blob):
                t.kind = TxnKind.LOAN_PAYMENT
            else:
                t.kind = TxnKind.PURCHASE
        stats[t.kind.value] = stats.get(t.kind.value, 0) + 1
    return stats


# ─────────────────────────────────────────────────────────────────────────────
# N1 — İç transfer eşleştirme
# ─────────────────────────────────────────────────────────────────────────────

TRANSFER_MATCH_DAYS = 3
TRANSFER_TOLERANCE_ABS = 1.0      # TRY
TRANSFER_TOLERANCE_PCT = 0.005    # kur/komisyon payı


def match_internal_transfers(raw: RawData) -> Dict[str, int]:
    """Kullanıcının kendi hesapları arasındaki hareketleri eşleştirir.

    Eşleşmeyenler gider/gelir olarak kalır. Eşleşenler her iki taraftan
    da düşülür — aksi hâlde hesaplar arası para gezdiren kullanıcı hem
    devasa gelir hem devasa gider görünür ve tasarruf oranı anlamsızlaşır.

    Açgözlü eşleştirme: en küçük zaman farkı, sonra en küçük tutar farkı.
    Her işlem en fazla bir kez eşleşir.
    """
    outs = [t for t in raw.transactions
            if t.try_amount < 0 and not t.is_internal_transfer
            and t.kind in (TxnKind.TRANSFER_OUT, TxnKind.PURCHASE,
                           TxnKind.SAVINGS_WITHDRAW, TxnKind.UNKNOWN)]
    ins = [t for t in raw.transactions
           if t.try_amount > 0 and not t.is_internal_transfer
           and t.kind in (TxnKind.TRANSFER_IN, TxnKind.SAVINGS_CONTRIB,
                          TxnKind.INCOME, TxnKind.UNKNOWN)]

    used = set()
    matched = 0
    for o in sorted(outs, key=lambda x: x.ts):
        amt = -o.try_amount
        tol = max(TRANSFER_TOLERANCE_ABS, amt * TRANSFER_TOLERANCE_PCT)
        best, best_key = None, None
        for i in ins:
            if i.id in used or i.account_id == o.account_id:
                continue
            dt = (i.ts - o.ts).total_seconds()
            if not (0 <= dt <= TRANSFER_MATCH_DAYS * 86400):
                continue
            diff = abs(i.try_amount - amt)
            if diff > tol:
                continue
            key = (dt, diff)
            if best_key is None or key < best_key:
                best, best_key = i, key
        if best is not None:
            used.add(best.id)
            for t, other in ((o, best), (best, o)):
                t.is_internal_transfer = True
                t.counterpart_id = other.id
                t.excluded_reason = "internal_transfer"
            # Birikim hesabına giden transfer ayrıca tasarruf katkısıdır.
            dest = raw.account(best.account_id)
            if dest and dest.type in SAVINGS_TYPES:
                best.kind = TxnKind.SAVINGS_CONTRIB
            o.kind = TxnKind.TRANSFER_OUT
            matched += 1
    return {"matched_pairs": matched}


# ─────────────────────────────────────────────────────────────────────────────
# N2 — Kredi kartı ödemesi tekilleştirme
# ─────────────────────────────────────────────────────────────────────────────

def resolve_card_payments(raw: RawData) -> Dict[str, object]:
    """Kart ödemesinin gider sayılıp sayılmayacağına karar verir.

    İKİ FARKLI DURUM VARDIR ve karıştırılırsa sonuç felakettir:

    (a) Kart hesabı BAĞLI. Harcamalar zaten `purchase` olarak görünüyor.
        Ödeme bir gider DEĞİLDİR, borç transferidir. Sayılırsa her
        harcama iki kez sayılır: gider iki katına çıkar, tasarruf oranı
        negatife düşer, skor çöker.

    (b) Kart hesabı BAĞLI DEĞİL. Tek görünen şey ödemedir; altındaki
        harcamalar görünmüyor. Ödeme gider olarak SAYILMAK ZORUNDADIR,
        yoksa kullanıcının giderinin büyük kısmı yok olur ve skor
        haksız yere yükselir.

    (b) durumunda veri kalitesi bayrağı konur ve güven (C) düşürülür:
        kategori kırılımı yoktur, davranış analizi yapılamaz.
    """
    # Belirleyici soru "hesap API ile bağlı mı" DEĞİL, "bu kartın
    # harcamalarını GÖRÜYOR MUYUZ" olmalıdır. Ekstre modelinde bir kart
    # açık bankacılığa bağlı olmadan da tamamen görünür olabilir: kart
    # ekstresi yüklenmiştir.
    #
    # İlk sürümde `a.is_linked` kullanılıyordu. Ekstreyle çalışan bir
    # kullanıcıda kart "bağlı değil" göründüğü için ödeme VEKİL harcama
    # sayılıyor, kartın kendi işlemleriyle birlikte ÇİFT SAYILIYORDU:
    # gider 19.463 TL yerine 29.978 TL, korunan tutar negatif çıkıyordu.
    accounts_with_txns = {t.account_id for t in raw.transactions}
    visible_cards = {a.id for a in raw.accounts
                     if a.type == AccountType.CREDIT_CARD
                     and (a.is_linked or a.id in accounts_with_txns)}
    linked_cards = visible_cards
    any_card = any(a.type == AccountType.CREDIT_CARD for a in raw.accounts)

    proxy_count = 0
    for t in raw.transactions:
        if t.kind != TxnKind.CARD_PAYMENT or t.try_amount >= 0:
            continue
        # Ödemenin hedefi bağlı bir kart mı?
        target_linked = False
        if t.counterpart_id:
            for o in raw.transactions:
                if o.id == t.counterpart_id and o.account_id in linked_cards:
                    target_linked = True
                    break
        if not target_linked and linked_cards and not t.counterpart_id:
            # Eşleşme yok ama bağlı kart var: büyük ihtimalle o karta ödeme.
            target_linked = True

        if target_linked:
            t.excluded_reason = "card_payment_to_linked_account"
        else:
            # Bağlı olmayan karta ödeme → giderin vekili olarak sayılır.
            t.kind = TxnKind.PURCHASE
            t.category = t.category or DEFAULT_CATEGORY
            t.excluded_reason = None
            proxy_count += 1

    return {"proxy_payments": proxy_count,
            "unlinked_card_present": any_card and not linked_cards}


# ─────────────────────────────────────────────────────────────────────────────
# N3 — Taksit ayrıştırma
# ─────────────────────────────────────────────────────────────────────────────

INSTALLMENT_RE = re.compile(r"(\d{1,2})\s*/\s*(\d{1,2})")


def extract_installments(raw: RawData) -> List[InstallmentPlan]:
    """Taksitli alışverişleri plana çevirir.

    Yalnızca ilk taksit (index 1) plan başlatır; sonraki taksitler plana
    bağlanır ve tekil gider olarak sayılmaz — aksi hâlde aynı alışveriş
    hem plan hem de 12 ayrı gider olarak iki kez sayılır.
    """
    plans: List[InstallmentPlan] = []
    for t in raw.transactions:
        idx, cnt = t.installment_index, t.installment_count
        if cnt is None:
            m = INSTALLMENT_RE.search(t.description_raw or "")
            if m:
                idx, cnt = int(m.group(1)), int(m.group(2))
        if not cnt or cnt < 2:
            continue

        monthly = abs(t.try_amount)
        if idx in (None, 1):
            plan = InstallmentPlan(
                id=f"plan_{t.id}", origin_txn_id=t.id, account_id=t.account_id,
                total_amount=monthly * cnt, count=cnt, monthly_amount=monthly,
                start=t.ts.date(), category=t.category or DEFAULT_CATEGORY)
            plans.append(plan)
            t.installment_plan_id = plan.id
        else:
            t.excluded_reason = "installment_followup"
            t.installment_plan_id = "unlinked"
    return plans


# ─────────────────────────────────────────────────────────────────────────────
# N4 — Yinelenen ödeme tespiti ve amortisman
# ─────────────────────────────────────────────────────────────────────────────

AMORTIZE_MIN_PERIOD_DAYS = 90
RECURRING_AMOUNT_TOL = 0.15
LIMIT_TOLERANCE = 0.05        # kategori limiti ihlal sayılma toleransı


@dataclass
class AmortEntry:
    """Yıllık/üç aylık bir ödemenin aylara dağıtılmış sanal parçası."""
    origin_txn_id: str
    d: date
    amount: float
    category: str


def detect_recurring_and_amortize(raw: RawData, as_of: date) -> Tuple[List[AmortEntry], Dict]:
    """Periyodu ≥90 gün olan düzenli ödemeleri aylara dağıtır.

    Sigorta, vergi, aidat, okul taksiti gibi ödemeler ödendikleri ay
    skoru çökertir, ertesi ay fırlatır. Kullanıcı sebebini anlamaz ve
    skora güveni gider. Amortisman bunu ortadan kaldırır.

    Tespit: aynı merchant_id + ±%15 tutar + düzenli aralık.
    """
    by_merchant: Dict[str, List[Transaction]] = {}
    for t in raw.transactions:
        if t.kind != TxnKind.PURCHASE or t.is_internal_transfer:
            continue
        if t.excluded_reason:
            continue
        key = t.merchant_id or ""
        if key:
            by_merchant.setdefault(key, []).append(t)

    entries: List[AmortEntry] = []
    series = 0
    for key, group in by_merchant.items():
        if len(group) < 2:
            continue
        group.sort(key=lambda x: x.ts)
        gaps = [(group[i + 1].ts - group[i].ts).days for i in range(len(group) - 1)]
        amounts = [abs(t.try_amount) for t in group]
        med_amt = statistics.median(amounts)
        if med_amt <= 0:
            continue
        regular = all(abs(a - med_amt) / med_amt <= RECURRING_AMOUNT_TOL for a in amounts)
        med_gap = statistics.median(gaps)
        if not (regular and med_gap >= AMORTIZE_MIN_PERIOD_DAYS):
            continue

        series += 1
        months = max(1, round(med_gap / 30))
        for t in group:
            t.recurrence_id = f"rec_{key}"
            t.amortized = True
            t.excluded_reason = "amortized"
            share = abs(t.try_amount) / months
            for k in range(months):
                entries.append(AmortEntry(
                    origin_txn_id=t.id, d=_add_months(t.ts.date(), k),
                    amount=share, category=t.category or DEFAULT_CATEGORY))

    # Tek seferlik büyük ödemeler de amortize edilir (henüz seri oluşmamış).
    for t in raw.transactions:
        if t.kind != TxnKind.PURCHASE or t.excluded_reason or t.amortized:
            continue
        if t.category in ("sigorta", "vergi", "egitim") and abs(t.try_amount) > 0:
            t.amortized = True
            t.excluded_reason = "amortized"
            months = 12 if t.category in ("sigorta", "vergi") else 9
            share = abs(t.try_amount) / months
            for k in range(months):
                entries.append(AmortEntry(t.id, _add_months(t.ts.date(), k),
                                          share, t.category))
            series += 1

    return entries, {"recurring_series": series, "amort_entries": len(entries)}


# ─────────────────────────────────────────────────────────────────────────────
# N7 — İade eşleştirme
# ─────────────────────────────────────────────────────────────────────────────

REFUND_WINDOW_DAYS = 90


def match_refunds(raw: RawData) -> Dict[str, int]:
    """İadeyi kaynak harcamayla netler.

    Netlenmezse iade edilen alışveriş hem gider hem gelir olarak durur:
    gider şişer, gelir sahte biçimde artar, tasarruf oranı bozulur.
    """
    refunds = [t for t in raw.transactions if t.kind == TxnKind.REFUND]
    purchases = [t for t in raw.transactions
                 if t.kind == TxnKind.PURCHASE and not t.excluded_reason]
    matched = 0
    for r in refunds:
        cands = [p for p in purchases
                 if p.merchant_id == r.merchant_id
                 and 0 <= (r.ts - p.ts).days <= REFUND_WINDOW_DAYS
                 and p.outflow >= r.inflow - 0.01]
        if not cands:
            continue
        p = min(cands, key=lambda x: abs(x.outflow - r.inflow))
        p.refunded_amount += r.inflow
        r.excluded_reason = "refund_netted"
        matched += 1
    return {"refunds_matched": matched, "refunds_total": len(refunds)}


# ─────────────────────────────────────────────────────────────────────────────
# N8 — Aykırı değer
# ─────────────────────────────────────────────────────────────────────────────

OUTLIER_INCOME_MULTIPLE = 3.0


def flag_outliers(raw: RawData, monthly_income: float) -> Dict[str, int]:
    """Aylık gelirin 3 katından büyük tek işlemleri işaretler.

    Ev/araba alımı, miras, tazminat gibi hareketler AYLIK ORAN
    metriklerini yok eder (bir ayda -%1500 marj). Bunlar oran
    metriklerinden çıkarılır, kullanıcıya AYRICA raporlanır ve
    bakiye/borç üzerindeki etkileri korunur.
    """
    if monthly_income <= 0:
        return {"outliers": 0}
    limit = monthly_income * OUTLIER_INCOME_MULTIPLE
    n = 0
    for t in raw.transactions:
        if t.is_internal_transfer or t.excluded_reason:
            continue
        if abs(t.try_amount) > limit:
            t.is_unusual = True
            n += 1
    return {"outliers": n}


# ─────────────────────────────────────────────────────────────────────────────
# N5 — Enflasyon düzeltmesi
# ─────────────────────────────────────────────────────────────────────────────

def real_value(amount: float, when: date, category: Optional[str],
               cpi: CPISeries, as_of: date) -> float:
    """Geçmiş tutarı bugünün parasına çevirir.

    KULLANIM SINIRI: yalnızca DÖNEMLER ARASI karşılaştırmada kullanılır
    (gelir oynaklığı, borç trendi, kategori oynaklığı). Aynı dönem içi
    ORANLARDA kullanılmaz — pay ve payda zaten aynı enflasyona maruz
    kaldığı için oran nötrdür ve düzeltme uygulanırsa çift sayım olur.
    """
    grp = CATEGORIES.get(category or DEFAULT_CATEGORY, CATEGORIES[DEFAULT_CATEGORY]).cpi_group
    now_i = cpi.get(grp, as_of)
    then_i = cpi.get(grp, when)
    if then_i <= 0:
        return amount
    return amount * (now_i / then_i)


# ─────────────────────────────────────────────────────────────────────────────
# Normalize edilmiş defter
# ─────────────────────────────────────────────────────────────────────────────

@dataclass
class Ledger:
    raw: RawData
    as_of: date
    plans: List[InstallmentPlan] = field(default_factory=list)
    amort: List[AmortEntry] = field(default_factory=list)
    diagnostics: Dict[str, object] = field(default_factory=dict)

    # ── Gider görünümleri ──────────────────────────────────────────────
    #
    # İKİ AYRI GÖRÜNÜM ZORUNLUDUR:
    #
    #  · NAKİT (cash):  taksitli alışveriş aylık taksit olarak sayılır.
    #                   Nakit akışı, marj, acil fon ayı buradan hesaplanır.
    #  · TAHAKKUK (accrual): taksitli alışveriş satın alma ayında tam
    #                   tutarla sayılır. Davranış ve bütçe disiplini
    #                   buradan hesaplanır — çünkü kullanıcı o kararı o
    #                   gün verdi.
    #
    # İkisini karıştırmak, "12 taksitle telefon aldım" davranışını
    # görünmez kılar.

    def expenses_cash(self, w: Window) -> List[Tuple[float, str, Transaction]]:
        out = []
        for t in self.raw.transactions:
            if not w.contains(t.ts.date()):
                continue
            if t.kind not in EXPENSE_KINDS or t.is_internal_transfer:
                continue
            if t.is_unusual or t.excluded_reason:
                continue
            if t.installment_plan_id:      # nakit görünümde plan taksiti sayılır
                continue
            out.append((t.outflow, t.category or DEFAULT_CATEGORY, t))
        for e in self.amort:
            if w.contains(e.d):
                out.append((e.amount, e.category, None))
        for p in self.plans:
            due = p.due_in_window(w.start, w.end)
            if due > 0:
                out.append((due, p.category, None))
        return out

    def expenses_accrual(self, w: Window) -> List[Tuple[float, str, Transaction]]:
        out = []
        for t in self.raw.transactions:
            if not w.contains(t.ts.date()):
                continue
            if t.kind not in EXPENSE_KINDS or t.is_internal_transfer:
                continue
            if t.is_unusual:
                continue
            if t.excluded_reason in ("installment_followup", "amortized",
                                     "internal_transfer", "refund_netted"):
                continue
            if t.installment_plan_id and t.installment_plan_id != "unlinked":
                plan = next((p for p in self.plans if p.id == t.installment_plan_id), None)
                if plan:
                    out.append((plan.total_amount, plan.category, t))
                    continue
            out.append((t.outflow, t.category or DEFAULT_CATEGORY, t))
        for e in self.amort:
            if w.contains(e.d):
                out.append((e.amount, e.category, None))
        return out

    def income(self, w: Window) -> List[Transaction]:
        return [t for t in self.raw.transactions
                if w.contains(t.ts.date()) and t.kind == TxnKind.INCOME
                and not t.is_internal_transfer and not t.is_unusual]

    def savings_flow(self, w: Window) -> float:
        """Birikim hesaplarına NET katkı. Değerleme farkı sayılmaz.

        Altın yükseldiği için kullanıcı 'tasarruf etmiş' sayılamaz —
        bu onun davranışı değil, piyasanın hareketidir.
        """
        net = 0.0
        for t in self.raw.transactions:
            if not w.contains(t.ts.date()):
                continue
            acc = self.raw.account(t.account_id)
            if not acc or acc.type not in SAVINGS_TYPES:
                continue
            if t.kind == TxnKind.SAVINGS_CONTRIB:
                net += t.inflow
            elif t.kind == TxnKind.SAVINGS_WITHDRAW:
                net -= t.outflow
        return net


def normalize(raw: RawData, as_of: date,
              user_overrides: Dict[str, str] = None) -> Ledger:
    """N1–N9 hattını sırayla çalıştırır. Sıra önemlidir."""
    diag: Dict[str, object] = {"pipeline_version": PIPELINE_VERSION}

    diag["categorize"] = categorize(raw.transactions, user_overrides)   # N9
    diag["classify"] = classify_kinds(raw)
    diag["transfers"] = match_internal_transfers(raw)                   # N1
    diag["card"] = resolve_card_payments(raw)                           # N2
    plans = extract_installments(raw)                                   # N3
    diag["installments"] = {"plans": len(plans)}
    amort, d4 = detect_recurring_and_amortize(raw, as_of)               # N4
    diag["amortize"] = d4
    diag["refunds"] = match_refunds(raw)                                # N7

    ledger = Ledger(raw=raw, as_of=as_of, plans=plans, amort=amort, diagnostics=diag)

    # N8 aykırı değer eşiği gelir gerektirir; kaba gelir tahminiyle yapılır.
    w = windows(as_of, 3)
    rough = statistics.median([sum(t.inflow for t in ledger.income(x)) for x in w] or [0])
    diag["outliers"] = flag_outliers(raw, rough)                        # N8

    return ledger


# ─────────────────────────────────────────────────────────────────────────────
# Katman 2 — Türetilmiş metrikler
# ─────────────────────────────────────────────────────────────────────────────

def _median(xs: List[float]) -> float:
    xs = [x for x in xs if x is not None]
    return statistics.median(xs) if xs else 0.0


def _cv(xs: List[float]) -> Optional[float]:
    xs = [x for x in xs if x > 0]
    if len(xs) < 3:
        return None
    m = statistics.mean(xs)
    if m <= 0:
        return None
    return statistics.pstdev(xs) / m


def derive_features(ledger: Ledger) -> Features:
    """Normalize edilmiş defterden `Features` üretir.

    Her alanın penceresi ve görünümü (nakit/tahakkuk) bilinçli seçilmiştir;
    `Docs/veri-katmani-v1.md` Bölüm 6'daki eşleme tablosuna bakınız.
    """
    raw, as_of = ledger.raw, ledger.as_of
    W = active_windows(ledger, windows(as_of, N_WINDOWS))
    if not W:
        W = windows(as_of, 1)
    W3 = W[:3]

    # ── Gelir ──────────────────────────────────────────────────────────
    inc_w = [sum(t.inflow for t in ledger.income(w)) for w in W]
    inc_w_real = []
    for w, _ in zip(W, inc_w):
        inc_w_real.append(sum(real_value(t.inflow, t.ts.date(), None, raw.cpi, as_of)
                              for t in ledger.income(w)))
    i_net = _median(inc_w[:3])
    i_cv = _cv(inc_w_real)          # dönemler arası → reel değer

    src: Dict[str, float] = {}
    for w in W3:
        for t in ledger.income(w):
            src[t.merchant_id or "diger"] = src.get(t.merchant_id or "diger", 0.0) + t.inflow
    i_primary_share = (max(src.values()) / sum(src.values())) if src else None

    # ── Gider (nakit görünüm) ──────────────────────────────────────────
    exp_w, ess_w = [], []
    for w in W:
        rows = ledger.expenses_cash(w)
        exp_w.append(sum(a for a, _, _ in rows))
        ess_w.append(sum(a * CATEGORIES.get(c, CATEGORIES[DEFAULT_CATEGORY]).essential_weight
                         for a, c, _ in rows))
    e_total = _median(exp_w[:3])
    e_essential = _median(ess_w[:3])

    # ── Bakiyeler ──────────────────────────────────────────────────────
    liquid = sum(a.balance for a in raw.accounts if a.type in LIQUID_TYPES)
    ef = sum(a.balance for a in raw.accounts if a.is_emergency_fund)

    # ── Tasarruf ───────────────────────────────────────────────────────
    sav_w = [ledger.savings_flow(w) for w in W]
    s_deliberate = max(0.0, _median(sav_w[:3]))
    positive = sum(1 for x in sav_w if x > 0)
    # 6'lık ölçeğe MEVCUT pencere sayısı üzerinden yansıtılır: 5 aylık
    # bir kullanıcı, her ay biriktirmiş olsa bile 5/6'da takılı kalmamalı.
    # 3 pencereden az veri varsa yansıtma yapılmaz (aşırı iyimser olurdu).
    s_consistency = (round(6 * positive / len(sav_w)) if len(sav_w) >= 3
                     else positive)

    # ── Borç ───────────────────────────────────────────────────────────
    cards = [a for a in raw.accounts if a.type == AccountType.CREDIT_CARD]
    card_balance = sum(a.balance for a in cards) if cards else None
    card_limit = sum(a.credit_limit or 0 for a in cards) or None

    loans = [l for l in raw.liabilities if l.type != "card_revolving"]
    revolving = [l for l in raw.liabilities if l.type == "card_revolving"]
    has_debt_data = bool(raw.liabilities) or bool(cards)

    debt_principal = (sum(l.principal_outstanding for l in loans)
                      + sum(l.principal_outstanding for l in revolving))
    debt_monthly_service = sum(l.monthly_payment for l in raw.liabilities)

    inst_monthly = sum(p.due_in_window(W[0].start, W[0].end) for p in ledger.plans)
    inst_remaining = sum(p.remaining_after(as_of) for p in ledger.plans)

    days_past_due = max([l.days_past_due for l in raw.liabilities], default=0)
    min_only = max([l.min_payment_only_months for l in raw.liabilities], default=0)
    kmh_active = any(a.type == AccountType.KMH and a.balance > 0 for a in raw.accounts) or \
                 any(a.type == AccountType.CHECKING and a.balance < 0 for a in raw.accounts)

    debt_trend = _debt_trend(ledger, debt_principal)

    # ── Bütçe / disiplin (tahakkuk görünüm) ────────────────────────────
    budget_planned = sum(b.monthly_limit for b in raw.budgets) or None
    budget_overrun = None
    limit_breached = None
    if raw.budgets:
        acc0: Dict[str, float] = {}
        for a, c, _ in ledger.expenses_accrual(W[0]):
            acc0[c] = acc0.get(c, 0.0) + a
        budget_overrun = sum(max(0.0, acc0.get(b.category, 0.0) - b.monthly_limit)
                             for b in raw.budgets)
        # %5 tolerans: limiti 5 TL aşmak "ihlal" sayılmaz. İkili sayım,
        # kaldırmaya çalıştığımız uçurumun ta kendisidir; aşımın BÜYÜKLÜĞÜ
        # zaten `budget_overrun` ile ölçülüyor.
        limit_breached = sum(1 for b in raw.budgets
                             if acc0.get(b.category, 0.0) > b.monthly_limit * (1 + LIMIT_TOLERANCE))

    cat_vol = _category_volatility(ledger, W)

    # ── Hedefler ───────────────────────────────────────────────────────
    goals = raw.goals
    goal_ontrack = goal_consistency = goal_required = None
    if goals:
        num = den = 0.0
        for g in goals:
            span = max(1, (g.target_date - g.created_at).days)
            elapsed = min(span, max(0, (as_of - g.created_at).days))
            expected = g.target_amount * (elapsed / span)
            ratio = 1.0 if expected <= 0 else min(1.0, g.current_amount / expected)
            num += ratio * g.target_amount
            den += g.target_amount
        goal_ontrack = num / den if den else None

        hist = [h for g in goals for h in g.contribution_history[-3:]]
        goal_consistency = (sum(1 for h in hist if h) / len(hist)) if hist else None

        req = 0.0
        for g in goals:
            months_left = max(1.0, (g.target_date - as_of).days / 30.0)
            req += max(0.0, (g.target_amount - g.current_amount) / months_left)
        goal_required = req

    # ── Davranış (çıkarım + etiket harmanı, W0) ────────────────────────
    #
    # Etiketlerin tek başına yeterli olduğu varsayımı ekstre yükleme
    # modelinde geçersizdir: veri aylık ve toplu gelir, kimse 200 işlemi
    # geriye dönük etiketlemez. `estimate_behavior` çıkarımı taban alır,
    # etiket geldikçe ona devreder. Bkz. `behavior_infer.py`.
    from behavior_infer import estimate_behavior

    disc_share = ((e_total - e_essential) / e_total) if e_total > 0 else 0.0
    est = estimate_behavior(ledger, W[0], disc_share)
    beh = {"coverage": est.coverage, "imp": est.imp_rate, "emo": est.emo_rate,
           "night": est.night_conc, "regret": est.regret_rate}

    # ── Güven girdileri ────────────────────────────────────────────────
    cat_rows = ledger.expenses_accrual(W[0])
    total0 = sum(a for a, _, _ in cat_rows) or 1.0
    categorized = sum(a for a, _, t in cat_rows
                      if t is None or t.category_source != CategorySource.NONE)
    linked = sum(1 for a in raw.accounts if a.is_linked)
    manual = linked == 0

    first_ts = min((t.ts.date() for t in raw.transactions), default=as_of)
    days_of_data = max(0, (as_of - first_ts).days)

    return Features(
        user_id=raw.user_id,
        days_of_data=days_of_data,
        i_net=i_net, i_cv=i_cv, i_primary_share=i_primary_share,
        i_declared=raw.income_declaration.monthly_net if raw.income_declaration else None,
        e_total=e_total, e_essential=e_essential, liquid_balance=liquid,
        s_deliberate=s_deliberate, ef_liquid=ef,
        s_consistency_months=s_consistency,
        real_return_gap=None,        # portföy değerleme geçmişi gerektirir — v2.1
        has_debt_data=has_debt_data,
        debt_principal=debt_principal,
        debt_monthly_service=debt_monthly_service,
        installment_monthly=inst_monthly,
        installment_remaining=inst_remaining,
        card_balance=card_balance, card_limit=card_limit,
        debt_trend_3m=debt_trend,
        days_past_due=days_past_due, min_payment_only_months=min_only,
        kmh_active=kmh_active,
        budget_planned=budget_planned, budget_overrun=budget_overrun,
        limit_categories=len(raw.budgets) or None, limit_breached=limit_breached,
        cat_volatility=cat_vol,
        goals_active=len(goals), goal_ontrack=goal_ontrack,
        goal_consistency=goal_consistency, goal_required_monthly=goal_required,
        beh_coverage=beh["coverage"], imp_rate=beh["imp"], emo_rate=beh["emo"],
        night_conc=beh["night"], regret_rate=beh["regret"],
        accounts_declared=raw.accounts_declared or len(raw.accounts) or 1,
        accounts_linked=linked,
        categorized_ratio=categorized / total0,
        manual_entry=manual,
        integrity_flag=raw.deleted_txn_ratio > 0.10,
        onboarding=raw.onboarding,
        prev_score=raw.prev_score,
    )


def _debt_trend(ledger: Ledger, principal_now: float) -> Optional[float]:
    """3 aylık borç anaparası değişimi — YALNIZCA ölçülmüş geçmişten.

    İlk sürümde bu, kart harcaması eksi kart ödemesi akışından tahmin
    ediliyordu. Sonuç saçmaydı: limiti içinde normal dönen bir kartta
    bile "borç %88 arttı" çıkıyor ve alt metrik sıfırlanıyordu — çünkü
    aynı ay içinde harcanıp ödenen tutar net borç değişimi değildir.

    Ölçülmüş anapara geçmişi yoksa bu alt metrik DEVRE DIŞI bırakılır
    (None). Uydurulmuş bir sinyal, eksik sinyalden kötüdür.
    """
    hist = sorted(ledger.raw.debt_principal_history or [], key=lambda x: x[0])
    if len(hist) < 2 or principal_now <= 0:
        return None
    cutoff = ledger.as_of - timedelta(days=WINDOW_DAYS * 3)
    past = [p for d, p in hist if d <= cutoff]
    before = past[-1] if past else hist[0][1]
    if before <= 0:
        return None
    return (principal_now / before) - 1.0


CATVOL_MIN_PRESENT = 0.75       # kategori aktif pencerelerin en az %75'inde görünmeli
CATVOL_MIN_SHARE = 0.02         # toplam harcamanın en az %2'si olmalı
CATVOL_EXCLUDE = {DEFAULT_CATEGORY}   # 'diğer' bir kategori değil, bir çöp kutusudur


def active_windows(ledger: "Ledger", W: List[Window]) -> List[Window]:
    """İçinde gerçekten veri olan pencereler.

    Kullanıcının geçmişi 6 pencereden kısaysa, veri OLMAYAN pencereyi
    'o ay sıfır harcadı / sıfır biriktirdi' saymak eksik veriyi cezaya
    çevirir — modelin 3 numaralı tasarım ilkesinin ihlalidir.

    Somut etkisi: 5 aylık bir kullanıcıda her kategori 6. pencerede 0
    görünür ve tamamen sabit giden bir kalem (örn. 700 TL telefon
    faturası) cv=0,45 ile 'oynak' işaretlenir. Aynı şekilde tasarruf
    sürekliliği hiçbir zaman 6/6 olamaz.
    """
    out = []
    for w in W:
        if any(True for _ in ledger.expenses_cash(w)) or ledger.income(w):
            out.append(w)
    return out


def _category_volatility(ledger: Ledger, W: List[Window]) -> Optional[float]:
    """Kategori harcamalarının pencereler arası varyasyon katsayısı ortalaması.

    Reel değerle hesaplanır: dönemler arası karşılaştırma olduğu için
    enflasyon ayıklanmazsa Türkiye'de HER kullanıcı 'oynak' görünür.

    İki filtre zorunludur, yoksa metrik gürültü ölçer: bir kategori
    yalnızca bir ayda göründüğünde CV mekanik olarak ~2,0 çıkar ve
    ortalamayı yukarı çeker. Tek seferlik bir elektronik alışverişi,
    kullanıcının 'düzensiz' olduğu anlamına gelmez.
    """
    # NAKİT görünüm kullanılır, tahakkuk değil: oynaklık harcama RİTMİNİ
    # ölçer, karar zamanlamasını değil. Tahakkuk kullanılırsa 4 taksitli
    # tek bir alışveriş, o kategoriyi yapay olarak "oynak" gösterir.
    per_cat: Dict[str, List[float]] = {}
    for w in W:
        agg: Dict[str, float] = {}
        for a, c, t in ledger.expenses_cash(w):
            when = t.ts.date() if t is not None else w.start
            agg[c] = agg.get(c, 0.0) + real_value(a, when, c, ledger.raw.cpi, ledger.as_of)
        for c in set(list(agg.keys()) + list(per_cat.keys())):
            per_cat.setdefault(c, []).append(agg.get(c, 0.0))

    grand = sum(sum(xs) for xs in per_cat.values())
    if grand <= 0 or len(W) < 3:
        return None

    cvs = []
    for c, xs in per_cat.items():
        if c in CATVOL_EXCLUDE or len(xs) < 3:
            continue
        if sum(1 for x in xs if x > 0) < CATVOL_MIN_PRESENT * len(xs):
            continue
        if sum(xs) / grand < CATVOL_MIN_SHARE:
            continue
        m = statistics.mean(xs)
        if m > 0:
            cvs.append(statistics.pstdev(xs) / m)
    return (sum(cvs) / len(cvs)) if cvs else None


NIGHT_HOURS = set(range(20, 24)) | set(range(0, 2))


def _behavior_metrics(ledger: Ledger, w: Window,
                      disc_share: float) -> Dict[str, Optional[float]]:
    """Davranış oranları — hepsi TUTAR bazlı, adet bazlı değil.

    v1'de risk puanları olay başına toplanıyordu; 50 TL'lik gece
    alışverişi 5.000 TL'lik ile aynı cezayı alıyordu ve tek bir işlem
    bileşeni sıfırlayabiliyordu. Oran bazlı ölçüm bunu yapısal olarak
    imkânsız kılar.

    TAHMİN EDİCİ (önemli): plansız/duygusal bilgisi YALNIZCA etiketlenmiş
    işlemler için gözlenebilir. Payda olarak doğrudan toplam harcamayı
    almak, etiketleme kapsamı düştükçe plansız harcamayı sistematik
    olarak EKSİK ölçer — kapsamı %36 olan kullanıcı, gerçekte savruk
    olsa bile "disiplinli" görünür.

    Doğru tahmin edici iki varsayıma dayanır:
      1. Zorunlu harcama tanımı gereği planlıdır (kira plansız olmaz).
      2. Etiketlenmiş harcamada gözlenen plansızlık oranı, isteğe bağlı
         harcamanın tamamı için geçerlidir.

        oran = (plansız_etiketli / etiketli) × isteğe_bağlı_pay

    Gece yoğunlaşması bu düzeltmeye TABİ DEĞİLDİR: saat bilgisi her
    işlemde vardır, örnekleme yanlılığı yoktur, doğrudan ölçülür.
    """
    tags = {t.txn_id: t for t in ledger.raw.behavior_tags}
    rows = ledger.expenses_accrual(w)
    total = sum(a for a, _, _ in rows)
    if total <= 0:
        return {"coverage": 0.0, "imp": None, "emo": None,
                "night": None, "regret": None}

    tagged = unplanned = emotional = night = 0.0
    rated = low_sat = 0.0
    for amt, _cat, t in rows:
        if t is None:
            continue
        if t.ts.hour in NIGHT_HOURS:
            night += amt
        tag = tags.get(t.id)
        if tag is None:
            continue
        tagged += amt
        if tag.planned is False:
            unplanned += amt
        if tag.emotion in EMOTIONAL_TAGS:
            emotional += amt
        if tag.satisfaction is not None:
            rated += amt
            if tag.satisfaction == 1:
                low_sat += amt

    scale = max(0.0, min(1.0, disc_share))
    return {
        "coverage": tagged / total,
        "imp": (unplanned / tagged) * scale if tagged > 0 else None,
        "emo": (emotional / tagged) * scale if tagged > 0 else None,
        "night": night / total,
        "regret": (low_sat / rated) if rated > 0 else None,
    }


# ─────────────────────────────────────────────────────────────────────────────
# Uçtan uca
# ─────────────────────────────────────────────────────────────────────────────

def build_features(raw: RawData, as_of: date,
                   user_overrides: Dict[str, str] = None) -> Tuple[Features, Ledger]:
    ledger = normalize(raw, as_of, user_overrides)
    return derive_features(ledger), ledger
