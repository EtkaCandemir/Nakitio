"""
Nakitio AI Koç — Doğrulama ve Güvenlik Katmanı

LLM yanıtı kullanıcıya GÖSTERİLMEDEN ÖNCE buradan geçer. İki iş yapar:

  1. SAYI DOĞRULAMA. Yanıttaki her rakam, araç katmanının `NumberLedger`
     defterine kayıtlı olmalıdır. Kayıtlı olmayan bir sayı halüsinasyondur
     ve yanıt reddedilir. Finansal bir üründe uydurulmuş bir rakam,
     yanlış yazılmış bir cümleden farklı bir şeydir: kullanıcı ona göre
     karar verir.

  2. İÇERİK KURALLARI. Yatırım tavsiyesi (SPK), kesin gelecek vaadi,
     utandırıcı dil, insan olduğunu ima etme — hepsi engellenir.
     Düşük skorda somut adım, düşük güvende belirsizlik dili ZORUNLUDUR.

Reddedilen yanıt için akış: onarım denemesi → yine geçmezse deterministik
şablon (`render_fallback`). Kullanıcı hiçbir koşulda doğrulanmamış bir
sayı görmez.

Şartname: `Docs/ai-koc-v1.md`
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple

from coach_tools import CoachContext, Kind, NumberLedger

GUARD_VERSION = "1.0.0"


# ─────────────────────────────────────────────────────────────────────────────
# Metin normalleştirme
# ─────────────────────────────────────────────────────────────────────────────

def _norm(text: str) -> str:
    """Türkçe'ye duyarlı küçültme. `str.lower()` tek başına 'İ' ve 'I'yı
    yanlış eşler ve kural tabloları sessizce kaçırır."""
    return (text.replace("İ", "i").replace("I", "ı")
                .replace("Ş", "ş").replace("Ğ", "ğ").replace("Ü", "ü")
                .replace("Ö", "ö").replace("Ç", "ç").lower())


# ─────────────────────────────────────────────────────────────────────────────
# 1. Sayı çıkarımı
# ─────────────────────────────────────────────────────────────────────────────
#
# Türkçe biçim: binlik ayırıcı NOKTA, ondalık ayırıcı VİRGÜL.
#   12.770  ·  24,9  ·  %26  ·  ₺7.070  ·  1.250,50  ·  78/100

# Sıra önemlidir: önce binlik ayraçlı biçim, sonra ondalıklı, sonra sade.
#
# Nokta hem binlik ayracı (12.770) hem de ondalık ayracı (7.6) olabilir.
# İkincisi Türkçe yazımda beklenmez ama LLM'ler İngilizce biçime kayar ve
# ilk sürümde "7.6" iki AYRI sayı (7 ve 6) olarak parçalanıp doğrulamayı
# yanlışlıkla reddediyordu. Doğrulayıcının aşırı katı olması, hiç
# olmaması kadar zararlıdır: ürün sürekli yedek şablona düşer.
NUM_RE = re.compile(
    r"\d{1,3}(?:\.\d{3})+(?:[.,]\d+)?"   # 12.770 · 1.250,50
    r"|\d+[.,]\d+"                        # 24,9 · 7.6
    r"|\d+"                               # 78
)

CTX = 14        # sağ/sol bağlam penceresi (karakter)

CURRENCY_MARKS = ("₺", " tl", "tl'", "lira", "türk lirası")
PERCENT_MARKS = ("%", "yüzde", "oran")
SCORE_MARKS = ("puan", "skor", "/100")
MONTH_MARKS = (" ay", "aylık", "ay'")


@dataclass
class Token:
    raw: str
    value: float
    kind: str
    start: int
    left: str
    right: str


def _to_float(s: str) -> Optional[float]:
    s = s.strip()
    try:
        if "." in s and "," in s:
            return float(s.replace(".", "").replace(",", "."))
        if "." in s:
            # Nokta binlik mi ondalık mı? Kural: noktadan sonraki her grup
            # tam 3 haneyse binlik ayracıdır (12.770), değilse ondalıktır (7.6).
            parts = s.split(".")
            if all(len(p) == 3 for p in parts[1:]):
                return float(s.replace(".", ""))
            return float(s)
        if "," in s:
            return float(s.replace(",", "."))
        return float(s)
    except ValueError:
        return None


def extract_numbers(text: str) -> List[Token]:
    out: List[Token] = []
    for m in NUM_RE.finditer(text):
        v = _to_float(m.group())
        if v is None:
            continue
        left = _norm(text[max(0, m.start() - CTX):m.start()])
        right = _norm(text[m.end():m.end() + CTX])

        if "%" in left[-2:] or right.lstrip().startswith("%") or \
           any(k in left for k in ("yüzde",)) or right.lstrip().startswith("'lik") and "%" in left:
            kind = Kind.PERCENT
        elif "₺" in left[-3:] or any(right.lstrip().startswith(k.strip()) for k in ("tl", "lira", "₺")):
            kind = Kind.CURRENCY
        elif right.lstrip().startswith("/100") or any(k in right[:8] for k in ("puan", "skor")) \
                or any(k in left[-10:] for k in ("skor", "puan")):
            kind = Kind.SCORE
        elif right.lstrip().startswith("ay"):
            kind = Kind.MONTHS
        else:
            kind = "plain"
        out.append(Token(m.group(), v, kind, m.start(), left, right))
    return out


# ─────────────────────────────────────────────────────────────────────────────
# 2. Deftere karşı doğrulama
# ─────────────────────────────────────────────────────────────────────────────

#: Yapısal küçük tam sayılar (gün, ay, adım sayısı, sıra) doğrulama
#: dışıdır — ama YALNIZCA para/yüzde/skor bağlamında değillerse.
STRUCTURAL_MAX = 31

#: Skor ölçeğinin kendisi her zaman serbesttir ("78/100").
SCALE_VALUES = {100.0}

TOL = {Kind.CURRENCY: 1.0, Kind.PERCENT: 0.5, Kind.SCORE: 0.5,
       Kind.MONTHS: 0.05, Kind.COUNT: 0.5, "plain": 0.5}


def _rounding_variants(v: float) -> List[float]:
    """Açık yuvarlamaya izin ver: 7.070 → 'yaklaşık 7.000' kabul edilir."""
    out = [v]
    for k in (1, 2, 3):
        out.append(round(v, -k))
    return out


def _matches(value: float, kind: str, ledger: NumberLedger) -> Tuple[bool, bool]:
    """(eşleşti_mi, yuvarlanmış_mı)"""
    tol = TOL.get(kind, 0.5)
    pool = ledger.values(kind if kind != "plain" else None)
    if kind == "plain":
        pool = ledger.values()
    elif kind == Kind.SCORE:
        pool = ledger.values(Kind.SCORE) + ledger.values(Kind.COUNT)
    elif kind == Kind.MONTHS:
        pool = ledger.values(Kind.MONTHS) + ledger.values(Kind.COUNT)

    for r in pool:
        if abs(value - r) <= tol:
            return True, False
    for r in pool:
        if any(abs(value - x) <= tol for x in _rounding_variants(r)):
            return True, True
    return False, False


@dataclass
class Violation:
    code: str
    severity: str          # "blocker" | "warning"
    detail: str


@dataclass
class GuardReport:
    ok: bool
    violations: List[Violation] = field(default_factory=list)
    checked_numbers: int = 0
    approximated: int = 0
    structural: int = 0

    @property
    def blockers(self) -> List[Violation]:
        return [v for v in self.violations if v.severity == "blocker"]

    def summary(self) -> str:
        if self.ok:
            return (f"GEÇTİ — {self.checked_numbers} sayı doğrulandı "
                    f"({self.approximated} yuvarlanmış, {self.structural} yapısal)"
                    + (f", {len(self.violations)} uyarı" if self.violations else ""))
        return "REDDEDİLDİ — " + " · ".join(f"[{v.code}] {v.detail}"
                                            for v in self.blockers)


def verify_numbers(text: str, ledger: NumberLedger) -> GuardReport:
    rep = GuardReport(ok=True)
    for t in extract_numbers(text):
        if t.value in SCALE_VALUES and t.kind in (Kind.SCORE, "plain"):
            continue
        if t.kind == "plain" and float(t.value).is_integer() and t.value <= STRUCTURAL_MAX:
            ok, _ = _matches(t.value, t.kind, ledger)
            if not ok:
                rep.structural += 1
            else:
                rep.checked_numbers += 1
            continue

        rep.checked_numbers += 1
        ok, approx = _matches(t.value, t.kind, ledger)
        if not ok:
            rep.ok = False
            rep.violations.append(Violation(
                "hallucinated_number", "blocker",
                f"'{t.raw}' ({t.kind}) araç çıktılarında yok"))
        elif approx:
            rep.approximated += 1
    return rep


# ─────────────────────────────────────────────────────────────────────────────
# 3. İçerik kuralları
# ─────────────────────────────────────────────────────────────────────────────

#: SPK — yatırım tavsiyesi. "acil durum FONUNA aktar" bir yönlendirmedir,
#: "şu FONA yatır" tavsiyedir. Kalıplar bu ayrımı korumak için dar tutuldu.
INVESTMENT_PATTERNS = [
    (r"\bhisse\b", "hisse senedi yönlendirmesi"),
    (r"\bborsa\b", "borsa yönlendirmesi"),
    (r"\bkripto|bitcoin|ethereum\b", "kripto yönlendirmesi"),
    (r"\byatırım (yap|tavsiye|öner)", "doğrudan yatırım tavsiyesi"),
    (r"\b(altın|döviz|dolar|euro|eurobond|fon)a\s+(yatır|gir|geç)", "enstrüman yönlendirmesi"),
    (r"\b(getiri|faiz) (garanti|kesin)", "getiri vaadi"),
    (r"\bportföy(ün)?ü? (öner|dağıt|oluştur)", "portföy tavsiyesi"),
]

CERTAINTY_PATTERNS = [
    (r"\bgaranti\b", "garanti ifadesi"),
    (r"\bkesinlikle\b", "kesinlik ifadesi"),
    (r"\bkesin olarak\b", "kesinlik ifadesi"),
    (r"\beminim\b", "kesinlik ifadesi"),
    (r"\bmutlaka (kazan|artacak|yüksel)", "kesin gelecek vaadi"),
    (r"\bskorun \d+ olacak\b", "kesin skor vaadi"),
]

SHAMING_PATTERNS = [
    (r"\bkötüsün\b|\bkötü durumdasın\b|durumun kötü", "utandırıcı dil"),
    (r"\bsavruk|müsrif|savurgan", "utandırıcı dil"),
    (r"\bbaşarısız|beceremi|yetersizsin", "utandırıcı dil"),
    (r"\bkontrolsüz|disiplinsiz(sin)?", "utandırıcı dil"),
    (r"\byanlış yapıyorsun|hata yapıyorsun", "suçlayıcı dil"),
    (r"\butanmalısın|ayıp", "utandırıcı dil"),
]

IDENTITY_PATTERNS = [
    (r"\bben bir insan|gerçek bir (finansal )?danışman(ım)?\b", "kimlik yanıltması"),
    (r"\blisanslı (danışman|uzman)ım\b", "kimlik yanıltması"),
]

HEDGE_WORDS = ("olabilir", "yaklaşık", "tahmini", "projeksiyon", "civarında",
               "beklenen", "öngörü", "civarı")

UNCERTAINTY_WORDS = ("arası", "yaklaşık", "veri arttıkça", "±", "kesinleşecek",
                     "netleşecek", "tahmini", "aralık", "civarında",
                     "başlangıç", "kişiselleş")

ACTION_HINTS = ("başlayabilir", "deneyebilir", "koyabilir", "aktarabilir",
                "azaltabilir", "ayarlayabilir", "belirleyebilir", "kur",
                "oluştur", "iptal et", "limit", "adım", "hedef", "planla")


def _scan(text_n: str, patterns) -> List[Tuple[str, str]]:
    return [(p, why) for p, why in patterns if re.search(p, text_n)]


#: Reddetme ekleri. Bunlardan biri eşleşmenin hemen ardından geliyorsa
#: cümle tavsiye DEĞİL, tavsiye vermeyi reddetmedir.
REFUSAL_MARKERS = (
    "veremem", "vermem", "veremiyorum", "veremeyeceğim", "yapamam",
    "öneremem", "önermem", "yetkim yok", "lisansım yok", "değilim",
    "yasak", "uygun değil", "yetkili değilim", "sunamam",
)
REFUSAL_WINDOW = 40


def _scan_unless_refusal(text_n: str, patterns) -> List[Tuple[str, str]]:
    """Yatırım kalıplarını tarar ama REDDETME cümlelerini geçirir.

    Koçun "Yatırım tavsiyesi veremem" diyebilmesi ZORUNLUDUR — SPK sınırı
    tam olarak bunu gerektirir. İlk sürümde `\\byatırım (yap|tavsiye|öner)`
    kalıbı bu cümleyi de yakalıyor ve REDDETMENİN KENDİSİNİ engelliyordu:
    guard, koçu doğru davrandığı için cezalandırıyordu.
    """
    hits = []
    for p, why in patterns:
        for m in re.finditer(p, text_n):
            after = text_n[m.end():m.end() + REFUSAL_WINDOW]
            if any(k in after for k in REFUSAL_MARKERS):
                continue
            hits.append((p, why))
            break
    return hits


def check_content(ctx: CoachContext, text: str,
                 projecting: bool = False,
                 reporting_category_change: bool = False) -> List[Violation]:
    t = _norm(text)
    v: List[Violation] = []

    for _, why in _scan_unless_refusal(t, INVESTMENT_PATTERNS):
        v.append(Violation("investment_advice", "blocker", why))
    for _, why in _scan(t, CERTAINTY_PATTERNS):
        v.append(Violation("certainty", "blocker", why))
    for _, why in _scan(t, SHAMING_PATTERNS):
        v.append(Violation("shaming", "blocker", why))
    for _, why in _scan(t, IDENTITY_PATTERNS):
        v.append(Violation("identity", "blocker", why))

    # Projeksiyon yapılıyorsa çekince dili ZORUNLU.
    if projecting and not any(h in t for h in HEDGE_WORDS):
        v.append(Violation("missing_hedge", "blocker",
                           "gelecek projeksiyonu çekince dili olmadan sunulmuş"))

    # Düşük güvende skor bant/belirsizlik diliyle sunulmalı.
    if ctx.low_confidence and re.search(r"skor|puan", t):
        if not any(w in t for w in UNCERTAINTY_WORDS):
            v.append(Violation("missing_uncertainty", "blocker",
                               f"C={ctx.score.confidence:.2f} < 0,65 iken skor "
                               f"kesin bir sayı gibi sunulmuş"))

    # Düşük skor daima somut bir sonraki adımla birlikte gösterilir.
    if ctx.score.score < 60 and not any(a in t for a in ACTION_HINTS):
        v.append(Violation("missing_next_step", "blocker",
                           "düşük skor somut bir adım önerilmeden sunulmuş"))

    # Kategori artışı bildiriliyorsa enflasyon ayrıştırılmalı.
    if reporting_category_change and not re.search(r"enflasyon|reel|tüfe", t):
        v.append(Violation("missing_inflation_context", "warning",
                           "kategori artışı enflasyondan arındırılmadan bildirilmiş"))

    return v


# ─────────────────────────────────────────────────────────────────────────────
# 4. Tek giriş noktası
# ─────────────────────────────────────────────────────────────────────────────

def verify_response(ctx: CoachContext, text: str, *,
                    projecting: bool = False,
                    reporting_category_change: bool = False) -> GuardReport:
    """Yanıtı kullanıcıya göstermeden önce çağrılır."""
    rep = verify_numbers(text, ctx.numbers)
    rep.violations.extend(check_content(
        ctx, text, projecting=projecting,
        reporting_category_change=reporting_category_change))
    if any(v.severity == "blocker" for v in rep.violations):
        rep.ok = False
    return rep


# ─────────────────────────────────────────────────────────────────────────────
# 5. Deterministik yedek yanıt
# ─────────────────────────────────────────────────────────────────────────────

def _tl(v: float) -> str:
    return f"{v:,.0f}".replace(",", ".") + " TL"


def render_fallback(ctx: CoachContext) -> str:
    """LLM iki denemede de doğrulamayı geçemezse gösterilecek yanıt.

    Tamamen şablondur ve yalnızca hesaplanmış sayıları kullanır; tanım
    gereği doğrulamayı geçer. Ürün hiçbir koşulda kullanıcıya
    doğrulanmamış bir rakam göstermez — bozuk bir cevap, uydurulmuş bir
    cevaptan iyidir.
    """
    from coach_tools import build_action_plan, get_score, get_score_breakdown

    s = get_score(ctx)
    br = get_score_breakdown(ctx)
    plan = build_action_plan(ctx, max_steps=1)

    if s["bant_olarak_sun"]:
        head = (f"{s['asama']}n şu an {s['band'][0]}–{s['band'][1]} aralığında. "
                f"Veri arttıkça bu aralık daralacak.")
    else:
        head = f"{s['asama']}n {s['skor']}/100 — {s['seviye']}."

    lines = [head]
    if br["en_zayif"]:
        lines.append(f"En çok gelişim alanı olan başlık: {br['en_zayif']}.")
    if plan["adimlar"]:
        a = plan["adimlar"][0]
        lines.append(f"Önerilen ilk adım: {a['aksiyon']}. "
                     f"Bu adımla skorun {a['kumulatif_skor']} seviyesine "
                     f"çıkabilir (tahmini).")
    lines.append("Detayları Finansal Sağlık Raporu ekranından görebilirsin.")
    return " ".join(lines)


def guarded_reply(ctx: CoachContext, generate, *, max_attempts: int = 2,
                  **verify_kw) -> Tuple[str, GuardReport, int]:
    """Üret → doğrula → onar → yedek.

    `generate(attempt, feedback) -> str` çağrılabilir bir üretici alır
    (gerçek LLM ya da testte kayıtlı yanıt). Doğrulama geçmezse
    ihlaller geri beslenerek bir kez daha denenir; yine geçmezse
    deterministik şablona düşülür.
    """
    feedback: Optional[str] = None
    last: Optional[GuardReport] = None
    for attempt in range(1, max_attempts + 1):
        text = generate(attempt, feedback)
        rep = verify_response(ctx, text, **verify_kw)
        if rep.ok:
            return text, rep, attempt
        last = rep
        feedback = ("Önceki yanıt reddedildi. İhlaller: "
                    + "; ".join(f"{v.code}: {v.detail}" for v in rep.blockers)
                    + ". Yalnızca araç çıktılarındaki sayıları kullan.")
    fb = render_fallback(ctx)
    return fb, (last or GuardReport(ok=False)), max_attempts + 1
