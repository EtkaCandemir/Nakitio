"""
Nakitio — Ekstre Alım Katmanı

    ekstre dosyası ─▶ [profil tabanlı ayrıştırma] ─▶ ParsedStatement
                   ─▶ [tekilleştirme] ─▶ RawData.transactions ─▶ normalize.py

TASARIM KURALI: yeni bir banka eklemek KOD DEĞİL, KONFİGÜRASYON olmalı.
Bir banka profili bir `BankProfile` kaydıdır; ayrıştırıcı jeneriktir.
Aksi hâlde her banka için ayrı kod yazılır, hiçbiri test edilmez ve
kapsam 5 bankadan öteye geçmez.

PDF METNİ BU MODÜLÜN İŞİ DEĞİLDİR. `extract_text(bytes, password) -> str`
dışarıdan enjekte edilir (üretimde pdfplumber / PyMuPDF). Böylece
ayrıştırma mantığı PDF kütüphanesinden bağımsız test edilebilir.

GÜVENLİK: PDF parolası hiçbir zaman saklanmaz, loglanmaz, sunucuya
gönderilmez. Ayrıştırma sırasında bellekte tutulur ve atılır. Türkiye'de
ekstre parolaları TCKN/doğum tarihi türevi olduğu için bu bir kimlik
verisidir.

Şartname: `Docs/ekstre-alimi-v1.md`
"""

from __future__ import annotations

import hashlib
import re
import unicodedata
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta
from typing import Callable, Dict, List, Optional, Sequence, Tuple

from data_model import Account, AccountType, RawData, Transaction

INGEST_VERSION = "1.0.0"


# ─────────────────────────────────────────────────────────────────────────────
# Profil şeması
# ─────────────────────────────────────────────────────────────────────────────

class DocKind:
    ACCOUNT = "account"      # hesap hareketleri
    CARD = "card"            # kredi kartı ekstresi


class Fmt:
    DELIMITED = "delimited"  # CSV / TSV / Excel'den dışa aktarım
    PDF_TEXT = "pdf_text"    # metin katmanlı PDF


@dataclass(frozen=True)
class BankProfile:
    """Bir bankanın bir ekstre türü için ayrıştırma tarifi.

    ⚠ Buradaki profiller ŞEMAYI gösterir. Üretime alınmadan önce her biri
    ilgili bankadan alınmış GERÇEK örnek dosyalarla doğrulanmalıdır;
    sütun adları, tarih biçimleri ve satır düzenleri bankadan bankaya ve
    sürümden sürüme değişir.
    """
    key: str
    bank: str
    doc_kind: str
    fmt: str

    # ── delimited ──────────────────────────────────────────────────────
    delimiter: str = ";"
    skip_rows: int = 0
    col_date: str = ""
    col_desc: str = ""
    col_amount: str = ""
    col_debit: str = ""
    col_credit: str = ""

    # ── pdf_text ───────────────────────────────────────────────────────
    #: Adlandırılmış gruplar: date, desc, amount (+ isteğe bağlı sign, inst)
    line_re: str = ""
    #: Üstbilgi alanları için desenler: period_start/end, account_ref,
    #: closing_balance, minimum_payment, due_date
    header_re: Dict[str, str] = field(default_factory=dict)

    # ── ortak ──────────────────────────────────────────────────────────
    date_formats: Tuple[str, ...] = ("%d.%m.%Y", "%d/%m/%Y", "%d.%m.%y")
    decimal: str = "tr"                  # "tr" → 1.234,56 · "en" → 1,234.56
    #: Kart ekstrelerinde harcama pozitif yazılır; alacak satırları
    #: kelimeyle işaretlenir. Bu kelimeler işareti ters çevirir.
    credit_markers: Tuple[str, ...] = ("ödeme", "iade", "iptal", "alacak",
                                       "puan kullanım")
    password_hint: str = ""


#: Taksit deseni — kart ekstrelerinde yaygın: "TAKSIT 3/12", "(3/12)"
INSTALLMENT_RE = re.compile(r"(?:taksit\s*)?\(?(\d{1,2})\s*/\s*(\d{1,2})\)?",
                            re.IGNORECASE)


PROFILES: Dict[str, BankProfile] = {
    p.key: p for p in [
        # Hesap hareketleri — internet bankacılığından CSV/Excel dışa aktarım.
        # Türkiye'de en yaygın ve en kolay ayrıştırılan biçim.
        BankProfile(
            key="tr_generic_account_csv",
            bank="(jenerik)", doc_kind=DocKind.ACCOUNT, fmt=Fmt.DELIMITED,
            delimiter=";", col_date="Tarih", col_desc="Açıklama",
            col_amount="Tutar", decimal="tr",
        ),
        # Borç/alacak sütunları ayrı olan düzen.
        BankProfile(
            key="tr_generic_account_debit_credit",
            bank="(jenerik)", doc_kind=DocKind.ACCOUNT, fmt=Fmt.DELIMITED,
            delimiter=";", col_date="Tarih", col_desc="Açıklama",
            col_debit="Borç", col_credit="Alacak", decimal="tr",
        ),
        # Kredi kartı ekstresi — metin katmanlı PDF.
        BankProfile(
            key="tr_generic_card_pdf",
            bank="(jenerik)", doc_kind=DocKind.CARD, fmt=Fmt.PDF_TEXT,
            line_re=r"^(?P<date>\d{2}[./]\d{2}[./]\d{4})\s+"
                    r"(?P<desc>.+?)\s+"
                    r"(?P<amount>-?[\d.]+,\d{2})\s*(?P<sign>TL)?\s*$",
            header_re={
                # "Başlangıcı" · "Başlangıç" · "Baslangici" — ekstreler
                # aksanlı da aksansız da yazabilir.
                "period_start": r"[Dd]önem\s*[Bb]a[şs]lang[ıi][cç][ıi]?\s*:?\s*(\d{2}[./]\d{2}[./]\d{4})",
                "period_end": r"(?:[Ee]kstre|[Hh]esap)\s*[Kk]esim\s*[Tt]arihi\s*:?\s*(\d{2}[./]\d{2}[./]\d{4})",
                "due_date": r"[Ss]on\s*[Öö]deme\s*[Tt]arihi\s*:?\s*(\d{2}[./]\d{2}[./]\d{4})",
                "closing_balance": r"[Dd]önem\s*[Bb]orcu\s*:?\s*([\d.]+,\d{2})",
                "minimum_payment": r"[Aa]sgari\s*[Öö]deme\s*[Tt]utar[ıi]\s*:?\s*([\d.]+,\d{2})",
                "account_ref": r"[Kk]art\s*[Nn]o\s*:?\s*([\d*\s]{8,25})",
            },
            password_hint="Genellikle TCKN/doğum tarihi/kart son hanelerinden "
                          "türetilir; bankaya göre değişir.",
        ),
    ]
}


# ─────────────────────────────────────────────────────────────────────────────
# Ayrıştırma çıktısı
# ─────────────────────────────────────────────────────────────────────────────

@dataclass
class ParsedRow:
    d: date
    description: str
    amount: float                 # işaretli, hesap perspektifi
    installment_index: Optional[int] = None
    installment_count: Optional[int] = None
    raw_line: str = ""


@dataclass
class ParsedStatement:
    profile_key: str
    bank: str
    doc_kind: str
    account_ref: Optional[str] = None
    period_start: Optional[date] = None
    period_end: Optional[date] = None
    rows: List[ParsedRow] = field(default_factory=list)
    closing_balance: Optional[float] = None
    minimum_payment: Optional[float] = None
    due_date: Optional[date] = None
    warnings: List[str] = field(default_factory=list)

    @property
    def key(self) -> str:
        """Aynı ekstrenin ikinci kez yüklendiğini anlamak için kimlik."""
        base = f"{self.bank}|{self.account_ref or ''}|{self.period_start}|{self.period_end}"
        return hashlib.sha256(base.encode()).hexdigest()[:16]


# ─────────────────────────────────────────────────────────────────────────────
# Yardımcılar
# ─────────────────────────────────────────────────────────────────────────────

def parse_amount(s: str, decimal: str = "tr") -> Optional[float]:
    s = (s or "").strip().replace("\xa0", " ").replace(" ", "")
    s = s.replace("TL", "").replace("₺", "").strip()
    if not s:
        return None
    neg = s.startswith("-") or s.endswith("-")
    s = s.strip("-")
    if decimal == "tr":
        s = s.replace(".", "").replace(",", ".")
    else:
        s = s.replace(",", "")
    try:
        v = float(s)
    except ValueError:
        return None
    return -v if neg else v


def parse_date(s: str, formats: Sequence[str]) -> Optional[date]:
    s = (s or "").strip()
    for f in formats:
        try:
            return datetime.strptime(s, f).date()
        except ValueError:
            continue
    return None


def _fold(s: str) -> str:
    """ASCII katlama — ekstre metni için doğru normalleştirme.

    DİKKAT: burada Türkçe'ye özgü `I → ı` eşlemesi KULLANILMAZ, oysa
    `coach_guard._norm` kullanır. İkisi bilerek farklıdır:

      · Koç yanıtı düzgün Türkçe metindir; orada 'I' gerçekten 'ı'dır.
      · Banka ekstresi aksansız ASCII yazar: "ÖDEME" → "ODEME",
        "MİGROS" → "MIGROS", "İADE" → "IADE". Burada 'I' aslında 'i'dir.

    Türkçe eşlemesi ekstrede uygulanırsa "IADE" → "ıade" olur ve "iade"
    işaretçisiyle EŞLEŞMEZ. Sonucu ağırdır: kart ödemesi ve iade satırları
    alacak olarak tanınmaz, harcama sayılır — yani N2'nin (kredi kartı
    çift sayımı) tam olarak engellemeye çalıştığı felaket, bir harf
    katlama hatası yüzünden geri gelir.
    """
    s = (s or "").lower()
    s = unicodedata.normalize("NFKD", s)
    s = "".join(c for c in s if not unicodedata.combining(c))
    return s.replace("ı", "i")


def _extract_installment(desc: str) -> Tuple[Optional[int], Optional[int]]:
    m = INSTALLMENT_RE.search(desc or "")
    if not m:
        return None, None
    idx, cnt = int(m.group(1)), int(m.group(2))
    if cnt < 2 or idx > cnt or cnt > 36:
        return None, None
    return idx, cnt


# ─────────────────────────────────────────────────────────────────────────────
# Ayrıştırıcılar
# ─────────────────────────────────────────────────────────────────────────────

def parse_delimited(text: str, profile: BankProfile) -> ParsedStatement:
    st = ParsedStatement(profile.key, profile.bank, profile.doc_kind)
    lines = [l for l in text.splitlines() if l.strip()]
    lines = lines[profile.skip_rows:]
    if not lines:
        st.warnings.append("boş dosya")
        return st

    header = [h.strip().strip('"') for h in lines[0].split(profile.delimiter)]
    idx = {h: i for i, h in enumerate(header)}

    need = [c for c in (profile.col_date, profile.col_desc) if c]
    missing = [c for c in need if c not in idx]
    if missing:
        st.warnings.append(f"beklenen sütunlar yok: {missing} (bulunan: {header})")
        return st

    for line in lines[1:]:
        cells = [c.strip().strip('"') for c in line.split(profile.delimiter)]
        if len(cells) < len(header):
            continue

        def cell(name: str) -> str:
            return cells[idx[name]] if name and name in idx else ""

        d = parse_date(cell(profile.col_date), profile.date_formats)
        if d is None:
            continue
        desc = cell(profile.col_desc)

        if profile.col_amount:
            amt = parse_amount(cell(profile.col_amount), profile.decimal)
        else:
            debit = parse_amount(cell(profile.col_debit), profile.decimal) or 0.0
            credit = parse_amount(cell(profile.col_credit), profile.decimal) or 0.0
            amt = credit - abs(debit)
        if amt is None:
            continue

        i, c = _extract_installment(desc)
        st.rows.append(ParsedRow(d, desc, amt, i, c, line))

    if st.rows:
        st.period_start = min(r.d for r in st.rows)
        st.period_end = max(r.d for r in st.rows)
    return st


def parse_pdf_text(text: str, profile: BankProfile) -> ParsedStatement:
    st = ParsedStatement(profile.key, profile.bank, profile.doc_kind)

    for fieldname, pattern in (profile.header_re or {}).items():
        m = re.search(pattern, text)
        if not m:
            continue
        val = m.group(1).strip()
        if fieldname in ("period_start", "period_end", "due_date"):
            setattr(st, fieldname, parse_date(val, profile.date_formats))
        elif fieldname in ("closing_balance", "minimum_payment"):
            setattr(st, fieldname, parse_amount(val, profile.decimal))
        else:
            setattr(st, fieldname, re.sub(r"\s+", "", val))

    line_re = re.compile(profile.line_re, re.MULTILINE)
    for m in line_re.finditer(text):
        g = m.groupdict()
        d = parse_date(g.get("date", ""), profile.date_formats)
        amt = parse_amount(g.get("amount", ""), profile.decimal)
        if d is None or amt is None:
            continue
        desc = (g.get("desc") or "").strip()

        # Kart ekstresinde harcama pozitif yazılır → hesap perspektifine
        # çevrilir (çıkış negatif). Alacak satırları kelimeyle işaretlidir.
        if profile.doc_kind == DocKind.CARD:
            folded = _fold(desc)
            is_credit = any(_fold(k) in folded for k in profile.credit_markers)
            amt = abs(amt) if is_credit else -abs(amt)

        i, c = _extract_installment(desc)
        st.rows.append(ParsedRow(d, desc, amt, i, c, m.group(0)))

    if not st.rows:
        st.warnings.append("hiç işlem satırı eşleşmedi — profil düzeni "
                           "dosyayla uyuşmuyor olabilir")
    if st.period_start is None and st.rows:
        st.period_start = min(r.d for r in st.rows)
    if st.period_end is None and st.rows:
        st.period_end = max(r.d for r in st.rows)
    return st


def parse_statement(text: str, profile_key: str) -> ParsedStatement:
    profile = PROFILES[profile_key]
    if profile.fmt == Fmt.DELIMITED:
        return parse_delimited(text, profile)
    return parse_pdf_text(text, profile)


# ─────────────────────────────────────────────────────────────────────────────
# PDF metni — enjekte edilen bağımlılık
# ─────────────────────────────────────────────────────────────────────────────

#: `extract_text(data: bytes, password: Optional[str]) -> str`
TextExtractor = Callable[[bytes, Optional[str]], str]


class PasswordRequired(Exception):
    """Parola gerekiyor ya da yanlış. Mesaj kullanıcıya gösterilir;
    parola HİÇBİR YERDE saklanmaz."""

    def __init__(self, hint: str = ""):
        super().__init__("Bu ekstre parola korumalı.")
        self.hint = hint


def load_pdf_statement(data: bytes, profile_key: str,
                       extractor: TextExtractor,
                       password: Optional[str] = None) -> ParsedStatement:
    profile = PROFILES[profile_key]
    try:
        text = extractor(data, password)
    except Exception as e:                       # kütüphaneye özgü hata
        raise PasswordRequired(profile.password_hint) from e
    if not text or not text.strip():
        raise PasswordRequired(profile.password_hint)
    return parse_pdf_text(text, profile)


# ─────────────────────────────────────────────────────────────────────────────
# Tekilleştirme
# ─────────────────────────────────────────────────────────────────────────────
#
# Aynı ekstre iki kez yüklenebilir; dönemler üst üste binebilir (kart
# ekstresi 18'inde keser, hesap hareketleri ay başından itibarendir).
# Parmak izi olmadan işlemler çiftlenir ve kullanıcının gideri iki
# katına çıkar — sessiz ve ölümcül.

def txn_fingerprint(account_id: str, d: date, amount: float, desc: str) -> str:
    norm = re.sub(r"\s+", " ", _fold(desc)).strip()
    base = f"{account_id}|{d.isoformat()}|{round(amount, 2)}|{norm}"
    return hashlib.sha256(base.encode()).hexdigest()[:20]


@dataclass
class ImportResult:
    statement_key: str
    added: int = 0
    duplicates: int = 0
    rows_total: int = 0
    period: Optional[Tuple[date, date]] = None
    warnings: List[str] = field(default_factory=list)
    debt_snapshot: Optional[Tuple[date, float]] = None


def import_statement(raw: RawData, parsed: ParsedStatement,
                     account_id: str) -> ImportResult:
    """Ayrıştırılmış ekstreyi `RawData`ya ekler. İdempotenttir."""
    existing = {txn_fingerprint(t.account_id, t.ts.date(), t.try_amount,
                               t.description_raw or t.merchant_raw or "")
                for t in raw.transactions}

    res = ImportResult(statement_key=parsed.key, rows_total=len(parsed.rows),
                       warnings=list(parsed.warnings))
    if parsed.period_start and parsed.period_end:
        res.period = (parsed.period_start, parsed.period_end)

    for i, r in enumerate(parsed.rows):
        fp = txn_fingerprint(account_id, r.d, r.amount, r.description)
        if fp in existing:
            res.duplicates += 1
            continue
        existing.add(fp)
        raw.transactions.append(Transaction(
            id=f"st_{parsed.key}_{i:04d}",
            account_id=account_id,
            ts=datetime(r.d.year, r.d.month, r.d.day),   # saat YOK — bkz. not
            amount=r.amount,
            description_raw=r.description,
            merchant_raw=r.description,
            installment_index=r.installment_index,
            installment_count=r.installment_count,
        ))
        res.added += 1

    # Kart ekstresi dönem sonu borcu → borç trendi için anapara geçmişi.
    # Bu, veri katmanında eksik bırakılan `debt_principal_history`
    # girdisidir; ekstre yüklemenin beklenmedik kazancıdır.
    if parsed.doc_kind == DocKind.CARD and parsed.closing_balance and parsed.period_end:
        snap = (parsed.period_end, float(parsed.closing_balance))
        if snap not in raw.debt_principal_history:
            raw.debt_principal_history.append(snap)
        res.debt_snapshot = snap

    return res


# NOT — SAAT VERİSİ: ekstrelerde işlem saati çoğunlukla YOKTUR. Yukarıda
# saat 00:00 olarak yazılır ve `behavior_infer` bunu "gece harcaması"
# değil "saat bilinmiyor" olarak yorumlar. Gece yoğunlaşması metriği,
# saat verisi olan işlemlerin payı %50'nin altındaysa hiç hesaplanmaz.


# ─────────────────────────────────────────────────────────────────────────────
# Kapsam ve boşluk tespiti
# ─────────────────────────────────────────────────────────────────────────────

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
