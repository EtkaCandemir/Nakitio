"""
Nakitio — Ham Veri Modeli ve Kategori Taksonomisi

Skor motoru (`score_engine.py`) `Features` nesnesi alır. Bu dosya, o
nesneyi üretecek olan HAM veri sözleşmesini tanımlar:

    ham veri (bu dosya) ─▶ normalize.py ─▶ Features ─▶ score_engine.py

PARA BİRİMİ NOTU: Bu referans implementasyon `float` kullanır çünkü
okunabilirlik önceliklidir. ÜRETİMDE PARA ASLA float TUTULMAZ —
kuruş cinsinden tam sayı (int minor units) veya Decimal kullanılmalıdır.
Kayan nokta hatası bir finans uygulamasında mutabakat bozar.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime
from enum import Enum
from typing import Dict, List, Optional, Sequence, Tuple


# ─────────────────────────────────────────────────────────────────────────────
# 1. Hesaplar
# ─────────────────────────────────────────────────────────────────────────────

class AccountType(str, Enum):
    CHECKING = "checking"        # vadesiz mevduat
    CASH = "cash"                # nakit
    SAVINGS = "savings"          # vadeli / birikim
    CREDIT_CARD = "credit_card"
    KMH = "kmh"                  # kredili mevduat hesabı
    LOAN = "loan"                # tüketici / konut / taşıt kredisi
    GOLD = "gold"                # altın hesabı
    FX = "fx"                    # döviz hesabı
    FUND = "fund"                # yatırım fonu
    CRYPTO = "crypto"


#: Likit tampon (runway) hesabında sayılan hesaplar.
LIQUID_TYPES = {AccountType.CHECKING, AccountType.CASH}

#: Kasıtlı birikimin gidebileceği hesaplar. Bunlara yapılan NET TRANSFER
#: tasarruf sayılır; değerleme farkı (altın yükseldi vb.) sayılmaz.
SAVINGS_TYPES = {AccountType.SAVINGS, AccountType.GOLD, AccountType.FX,
                 AccountType.FUND, AccountType.CRYPTO}


@dataclass
class Account:
    id: str
    type: AccountType
    name: str = ""
    currency: str = "TRY"
    balance: float = 0.0             # güncel bakiye (kart için borç, pozitif)
    credit_limit: Optional[float] = None
    statement_day: Optional[int] = None   # ekstre kesim günü
    due_day: Optional[int] = None         # son ödeme günü
    is_linked: bool = False          # otomatik bağlantı mı, manuel mi
    is_emergency_fund: bool = False  # acil durum fonu olarak işaretli mi
    opened_at: Optional[date] = None


# ─────────────────────────────────────────────────────────────────────────────
# 2. İşlem türleri
# ─────────────────────────────────────────────────────────────────────────────

class TxnKind(str, Enum):
    UNKNOWN = "unknown"
    INCOME = "income"                    # maaş, serbest gelir, kira geliri
    PURCHASE = "purchase"                # harcama
    TRANSFER_OUT = "transfer_out"        # hesaptan çıkan transfer
    TRANSFER_IN = "transfer_in"          # hesaba giren transfer
    CARD_PAYMENT = "card_payment"        # kredi kartı borç ödemesi
    LOAN_PAYMENT = "loan_payment"        # kredi taksiti / borç ödemesi
    SAVINGS_CONTRIB = "savings_contrib"  # birikim hesabına katkı
    SAVINGS_WITHDRAW = "savings_withdraw"
    FEE = "fee"
    INTEREST = "interest"
    REFUND = "refund"
    CASH_WITHDRAWAL = "cash_withdrawal"


#: Gider toplamına giren türler. TRANSFER_* ve CARD_PAYMENT bilinçli
#: olarak DIŞARIDADIR — sebebi normalizasyon kuralları N1 ve N2.
EXPENSE_KINDS = {TxnKind.PURCHASE, TxnKind.FEE, TxnKind.INTEREST}


# ─────────────────────────────────────────────────────────────────────────────
# 3. Kategori taksonomisi
# ─────────────────────────────────────────────────────────────────────────────
#
# `essential_weight` ikili bir bayrak DEĞİL, [0,1] arası bir ağırlıktır.
#
# Gerekçe: "market" ne tamamen zorunlu ne tamamen isteğe bağlıdır. Temel
# gıda zorunludur, atıştırmalık değildir. İkili sınıflandırma bu gri
# bölgede sistematik hata üretir — ve `e_essential` üzerinden acil durum
# fonu hedefini, `disc_share` üzerinden disiplin skorunu doğrudan
# bozar. Kesirli ağırlık, tek tek işlemleri doğru bilmek zorunda
# kalmadan toplamda doğru sonuç verir.
#
# Ağırlıklar Türkiye hanehalkı tüketim yapısı dikkate alınarak
# konulmuştur ve gerçek veriyle kalibre edilmelidir.

@dataclass(frozen=True)
class Category:
    key: str
    label: str
    #: [0,1] ağırlık — ya da **None = BİLİNMİYOR**.
    #:
    #: None, "sıfır zorunlu" demek DEĞİLDİR; "bu harcamanın ne kadarının
    #: zorunlu olduğunu bilmiyoruz" demektir. İkisini karıştırmak, modelin
    #: `None ≠ 0` temel kuralının taksonomi düzeyindeki ihlali olur.
    #:
    #: Böyle kategoriler `e_essential` toplamına girmez; oran, ağırlığı
    #: BİLİNEN harcamadan tahmin edilip toplama genişletilir
    #: (`normalize.derive_features`). Ortalama bir sayı uydurmak yerine
    #: bilmediğimizi itiraf edip belirsizliği güvene yansıtırız.
    essential_weight: Optional[float]
    cpi_group: str            # TÜİK COICOP eşlemesi (enflasyon düzeltmesi)


CATEGORIES: Dict[str, Category] = {c.key: c for c in [
    # ── Zorunluya yakın ────────────────────────────────────────────────
    Category("kira",        "Kira / Konut",        1.00, "konut"),
    Category("aidat",       "Aidat",               1.00, "konut"),
    Category("faturalar",   "Faturalar",           1.00, "konut"),
    Category("saglik",      "Sağlık",              1.00, "saglik"),
    Category("egitim",      "Eğitim",              1.00, "egitim"),
    Category("sigorta",     "Sigorta",             1.00, "cesitli"),
    Category("vergi",       "Vergi / Resmi",       1.00, "cesitli"),
    Category("cocuk",       "Çocuk / Bakım",       0.95, "cesitli"),
    Category("market",      "Market",              0.85, "gida"),
    Category("ulasim",      "Ulaşım",              0.75, "ulastirma"),
    Category("iletisim",    "İnternet / Telefon",  0.85, "haberlesme"),
    # ── Karma ──────────────────────────────────────────────────────────
    Category("giyim",       "Giyim",               0.25, "giyim"),
    Category("kisisel",     "Kişisel Bakım",       0.35, "cesitli"),
    Category("ev",          "Ev / Yaşam",          0.40, "ev_esyasi"),
    Category("restoran",    "Restoran & Kafe",     0.15, "lokanta"),
    # ── İsteğe bağlı ───────────────────────────────────────────────────
    Category("abonelik",    "Dijital Abonelik",    0.10, "eglence"),
    Category("eglence",     "Eğlence & Hobi",      0.00, "eglence"),
    Category("tatil",       "Tatil & Seyahat",     0.00, "lokanta"),
    Category("elektronik",  "Elektronik",          0.10, "ev_esyasi"),
    Category("spor",        "Spor & Fitness",      0.10, "eglence"),
    Category("hediye",      "Hediye",              0.05, "cesitli"),
    Category("alkol_tutun", "Alkol & Tütün",       0.00, "alkol_tutun"),
    Category("sans_oyunu",  "Şans Oyunları",       0.00, "eglence"),
    # ── Ağırlığı BİLİNMEYENLER ─────────────────────────────────────────
    # Bu ikisinin ortak özelliği: işyerini biliyoruz, NE ALINDIĞINI
    # bilmiyoruz. Sabit bir ağırlık vermek uydurmak olur.
    #
    # "Pazaryeri": Trendyol/Amazon/Hepsiburada tek satırı giyim de olabilir
    # elektronik de market de. Bilgi metinde YOKTUR; hiçbir kural ya da
    # model onu metinden çıkaramaz. Kullanıcıya sorulur (triyaj).
    Category("pazaryeri",   "Pazaryeri",           None, "cesitli"),
    # Faiz/ücret TÜKETİM DEĞİLDİR — borcun maliyetidir. Zorunlu/isteğe
    # bağlı ekseninde bir yeri yoktur: "zorunlu" saymak borçlu olmayı
    # ödüllendirir (disc_share düşer, disiplin puanı yükselir), "isteğe
    # bağlı" saymak ise P2'nin zaten ölçtüğü borç yükünü ikinci kez
    # cezalandırır. İkisi de yanlış; ağırlık BİLİNMEZ bırakılır.
    Category("faiz_ucret",  "Faiz & Ücret",        None, "cesitli"),
    # "Diğer" bir kategori değil, EŞLEŞMEYENLERİN kovasıdır. Eskiden 0,40
    # ağırlık taşıyordu: motor "bilmiyorum" derken hesap katmanı sessizce
    # ortalama bir tahmin yürütüyordu. Gerçek bir ekstrede bu, harcamanın
    # %37'sinde uydurulmuş bir ağırlık demekti.
    Category("diger",       "Diğer",               None, "cesitli"),
]}

DEFAULT_CATEGORY = "diger"


class CategorySource(str, Enum):
    RULE = "rule"        # merchant kural motoru
    MCC = "mcc"          # kart MCC kodu
    ML = "ml"            # model tahmini
    USER = "user"        # kullanıcı düzeltmesi (en güvenilir)
    NONE = "none"        # kategorize edilmemiş


# ─────────────────────────────────────────────────────────────────────────────
# 4. İşlem
# ─────────────────────────────────────────────────────────────────────────────

@dataclass
class Transaction:
    """Tek bir para hareketi.

    `amount` işaret kuralı: HESAP PERSPEKTİFİNDEN. Çıkış negatif, giriş
    pozitif. Kredi kartı hesabında harcama negatif (borç artışı), ödeme
    pozitiftir. Bu kural tüm hesap türleri için aynıdır ve hiçbir yerde
    tersine çevrilmez.
    """
    id: str
    account_id: str
    ts: datetime
    amount: float
    description_raw: str = ""
    merchant_raw: Optional[str] = None
    mcc: Optional[str] = None
    currency: str = "TRY"
    fx_rate: float = 1.0             # işlem anındaki TRY karşılığı çarpanı

    # Taksit bilgisi (banka verisinde varsa doğrudan gelir)
    installment_index: Optional[int] = None    # 3/12'nin 3'ü
    installment_count: Optional[int] = None    # 3/12'nin 12'si

    # ── Normalizasyon çıktıları (pipeline doldurur) ────────────────────
    kind: TxnKind = TxnKind.UNKNOWN
    category: Optional[str] = None
    category_source: CategorySource = CategorySource.NONE
    #: HANGİ katman karar verdi — telemetri ve açıklanabilirlik için.
    #:
    #: `category_source` kaba ayrımdır (RULE/MCC/USER/NONE) ve RULE'un
    #: içini göstermez: marka sözlüğü mü, Türkçe tür sözcüğü mü, faiz
    #: deseni mi? Üretimde "hangi katmana yatırım yapmalıyız" sorusu
    #: TUTAR ağırlıklı bu kırılımla cevaplanır — adet kırılımıyla değil,
    #: çünkü `e_essential`'i belirleyen tutardır.
    #:
    #: Kullanıcıya "bu neden restoran?" diye sorulduğunda da cevap burada.
    category_layer: Optional[str] = None
    merchant_id: Optional[str] = None
    is_internal_transfer: bool = False
    counterpart_id: Optional[str] = None
    installment_plan_id: Optional[str] = None
    recurrence_id: Optional[str] = None
    amortized: bool = False          # N4 kapsamında aylara dağıtıldı
    is_unusual: bool = False         # N8 aykırı değer
    refunded_amount: float = 0.0     # N7 ile netlenen tutar
    excluded_reason: Optional[str] = None   # gider toplamından çıkarıldıysa neden

    @property
    def try_amount(self) -> float:
        return self.amount * self.fx_rate

    @property
    def outflow(self) -> float:
        """Pozitif çıkış tutarı (iade netlenmiş)."""
        return max(0.0, -self.try_amount) - self.refunded_amount

    @property
    def inflow(self) -> float:
        return max(0.0, self.try_amount)


# ─────────────────────────────────────────────────────────────────────────────
# 5. Yan kayıtlar
# ─────────────────────────────────────────────────────────────────────────────

@dataclass
class InstallmentPlan:
    """Taksitli alışveriş planı.

    Türkiye'ye özgü ve modelin doğruluğu için kritik: 12 taksitle alınan
    12.000 TL'lik bir ürün, aylık 1.000 TL'lik bir GİDER değil, 11 aylık
    bir YÜKÜMLÜLÜKTÜR. İki görünüm ayrı tutulur:
      · tahakkuk (accrual): tam tutar, satın alma ayında  → davranış ölçümü
      · nakit (cash):       aylık taksit                  → nakit akışı, DSR
    """
    id: str
    origin_txn_id: str
    account_id: str
    total_amount: float
    count: int
    monthly_amount: float
    start: date
    category: str = DEFAULT_CATEGORY

    def remaining_after(self, as_of: date) -> float:
        paid = self._paid_count(as_of)
        return max(0.0, (self.count - paid) * self.monthly_amount)

    def due_in_window(self, start: date, end: date) -> float:
        """[start, end) aralığına düşen taksit tutarı."""
        total = 0.0
        for i in range(self.count):
            d = _add_months(self.start, i)
            if start <= d < end:
                total += self.monthly_amount
        return total

    def _paid_count(self, as_of: date) -> int:
        n = 0
        for i in range(self.count):
            if _add_months(self.start, i) <= as_of:
                n += 1
        return n


@dataclass
class Liability:
    """Beyan edilmiş veya bağlantıdan gelen borç kaydı."""
    id: str
    type: str                      # consumer_loan | mortgage | auto | card_revolving | kmh
    principal_outstanding: float
    monthly_payment: float
    interest_rate: Optional[float] = None
    remaining_months: Optional[int] = None
    days_past_due: int = 0
    min_payment_only_months: int = 0


@dataclass
class Goal:
    id: str
    name: str
    target_amount: float
    current_amount: float
    created_at: date
    target_date: date
    monthly_plan: Optional[float] = None
    linked_account_id: Optional[str] = None
    #: Son 3 dönemde plana uygun katkı yapıldı mı (True/False listesi)
    contribution_history: List[bool] = field(default_factory=list)


@dataclass
class Budget:
    category: str
    monthly_limit: float


@dataclass
class BehaviorTag:
    """Kullanıcının bir harcamaya iliştirdiği davranış etiketi.

    Mockup'taki 'Harcama Sonrası Memnuniyet' ve duygu etiketleri buradan
    gelir. v1 modeli bu veriyi topluyor ama kullanmıyordu.
    """
    txn_id: str
    planned: Optional[bool] = None
    emotion: Optional[str] = None        # stres | odul | can_sikintisi | sosyal | aliskanlik
    satisfaction: Optional[int] = None   # 1 düşük · 2 orta · 3 yüksek


EMOTIONAL_TAGS = {"stres", "odul", "can_sikintisi"}


@dataclass
class IncomeDeclaration:
    monthly_net: Optional[float] = None
    source_label: str = "maas"


@dataclass
class CPISeries:
    """Kategori grubu bazlı TÜFE endeksi: {(yyyy, mm): endeks}.

    Üretimde TÜİK'ten beslenir. Enflasyon düzeltmesi olmadan Türkiye'de
    dönemler arası harcama karşılaştırması kullanıcıyı sistematik olarak
    haksız yere suçlar.
    """
    index: Dict[str, Dict[str, float]] = field(default_factory=dict)

    def get(self, cpi_group: str, d: date) -> float:
        key = f"{d.year:04d}-{d.month:02d}"
        grp = self.index.get(cpi_group) or self.index.get("genel") or {}
        return grp.get(key, 100.0)


@dataclass
class RawData:
    """Normalizasyon katmanının tek girdisi."""
    user_id: str
    accounts: List[Account] = field(default_factory=list)
    transactions: List[Transaction] = field(default_factory=list)
    liabilities: List[Liability] = field(default_factory=list)
    goals: List[Goal] = field(default_factory=list)
    budgets: List[Budget] = field(default_factory=list)
    behavior_tags: List[BehaviorTag] = field(default_factory=list)
    income_declaration: Optional[IncomeDeclaration] = None
    onboarding: Dict[str, str] = field(default_factory=dict)
    cpi: CPISeries = field(default_factory=CPISeries)
    accounts_declared: int = 0        # onboarding'de "kaç hesabım var" cevabı
    deleted_txn_ratio: float = 0.0    # bütünlük sinyali
    prev_score: Optional[float] = None

    #: Önceki dönemin HAM skoru ve GÜVENİ.
    #:
    #: `score_engine.smoothing_anchor` bunlarsız "eski davranış"a düşer ve
    #: yumuşatmanın çapasını GÖSTERİLEN önceki skora sabitler. O zaman
    #: ölçümümüzün düzelmesi (güven artışı) de yumuşatılır — yani yanlış
    #: olduğunu bildiğimiz bir sayıyı bile bile göstermeye devam ederiz.
    #: M6 kararının canlı hatta çalışması için bu ikisi taşınmalıdır.
    prev_raw_score: Optional[float] = None
    prev_confidence: Optional[float] = None

    #: Yüklenmiş ekstrelerin kapsadığı dönemler: [(başlangıç, bitiş)].
    #:
    #: `import_statement` her yüklemede buraya yazar. `derive_features`
    #: bundan `data_source` ve `statement_coverage` türetir; ikisi de
    #: güven (C) hesabına girer. Boşsa veri kaynağı ekstre DEĞİLDİR —
    #: bağlı hesap varsa "linked", yoksa "manual".
    statement_periods: List["tuple"] = field(default_factory=list)

    #: Ekstre/bakiye anlık görüntülerinden gelen borç anaparası geçmişi.
    #: [(tarih, toplam_anapara)]. Borç trendi YALNIZCA buradan hesaplanır.
    #: Yoksa trend alt metriği devre dışı kalır — işlem akışından tahmin
    #: ETMEYE ÇALIŞMAYIZ: kart harcaması eksi ödeme farkı, limit içinde
    #: dönen bir kartta bile borcun patladığı yanılsamasını üretir.
    debt_principal_history: List["tuple"] = field(default_factory=list)
    #: İŞYERİ HAFIZASI — `merchant_id` → kategori.
    #:
    #: Kullanıcı düzeltmeleri KALICIDIR: bir kez "AYYILDIZ market'tir"
    #: dendiğinde o işyerinin GEÇMİŞ ve GELECEK tüm işlemleri düzelir.
    #: Tek işleme özel düzeltme değil, işyerine özel bilgidir.
    #:
    #: Anahtar kanonik `merchant_id`'dir; marka tanınıyorsa zincir anahtarı
    #: ("a101"), değilse temizlenmiş ad. Bu yüzden bir düzeltme aynı
    #: zincirin tüm şubelerini kapsar.
    #:
    #: Kuralları ve marka sözlüğünü EZER — kullanıcı kendi bağlamını
    #: bizden iyi bilir (aynı kafeden her gün iş yemeği alıyor olabilir).
    category_overrides: Dict[str, str] = field(default_factory=dict)

    def account(self, aid: str) -> Optional[Account]:
        for a in self.accounts:
            if a.id == aid:
                return a
        return None


# ─────────────────────────────────────────────────────────────────────────────
# 5b. Ekstre kapsamı — dönem aritmetiği
# ─────────────────────────────────────────────────────────────────────────────
#
# `RawData.statement_periods` üzerinde çalışan saf fonksiyonlar. Burada
# dururlar çünkü HEM `statement_ingest` (dönemi üretir) HEM `normalize`
# (kapsamı güvene çevirir) kullanır; ayrıştırma katmanında dursalardı
# çekirdek katman dosya ayrıştırıcıya bağımlı olurdu.

def month_key(d: date) -> str:
    return f"{d.year:04d}-{d.month:02d}"


def covered_months(periods: Sequence[Tuple[date, date]]) -> set:
    out = set()
    for s, e in periods:
        cur = date(s.year, s.month, 1)
        while cur <= e:
            out.add(month_key(cur))
            cur = date(cur.year + (cur.month // 12), cur.month % 12 + 1, 1)
    return out


def statement_coverage(periods: Sequence[Tuple[date, date]], as_of: date,
                       months: int = 6) -> float:
    """Son `months` ayın kaçında ekstre var. Güven (C) hesabına girer."""
    have = covered_months(periods)
    want, cur = [], date(as_of.year, as_of.month, 1)
    for _ in range(months):
        want.append(month_key(cur))
        cur = (date(cur.year - 1, 12, 1) if cur.month == 1
               else date(cur.year, cur.month - 1, 1))
    return sum(1 for m in want if m in have) / len(want)


def missing_months(periods: Sequence[Tuple[date, date]], as_of: date,
                   months: int = 6) -> List[str]:
    have = covered_months(periods)
    out, cur = [], date(as_of.year, as_of.month, 1)
    for _ in range(months):
        if month_key(cur) not in have:
            out.append(month_key(cur))
        cur = (date(cur.year - 1, 12, 1) if cur.month == 1
               else date(cur.year, cur.month - 1, 1))
    return sorted(out)


def effective_as_of(periods: Sequence[Tuple[date, date]],
                    today: date) -> date:
    """Hesaplama tarihi BUGÜN değil, SON EKSTRE tarihidir.

    Ekstre ayın 18'inde kesiliyorsa, 20'sinde yüklendiğinde son 10 günün
    verisi yoktur. `as_of = bugün` alınırsa o 10 gün "sıfır harcama"
    sayılır ve nakit akışı marjı yapay olarak yükselir — kullanıcıya
    gerçekte var olmayan bir iyileşme gösterilir.
    """
    if not periods:
        return today
    return min(today, max(e for _, e in periods))


# ─────────────────────────────────────────────────────────────────────────────
# 6. Tarih yardımcıları
# ─────────────────────────────────────────────────────────────────────────────

def _add_months(d: date, n: int) -> date:
    y, m = d.year, d.month + n
    y += (m - 1) // 12
    m = (m - 1) % 12 + 1
    day = min(d.day, _days_in_month(y, m))
    return date(y, m, day)


def _days_in_month(y: int, m: int) -> int:
    if m == 12:
        return 31
    return (date(y + (m // 12), m % 12 + 1, 1) - date(y, m, 1)).days
