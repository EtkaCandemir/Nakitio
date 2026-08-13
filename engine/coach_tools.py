"""
Nakitio AI Koç — Araç Katmanı (tool-calling sözleşmesi)

TEMEL KURAL: LLM hiçbir finansal sayı ÜRETMEZ. Yalnızca bu dosyadaki
araçların döndürdüğü sayıları anlatır.

Mockup'larda koç şunları söylüyor:
    "3 ay içinde skorunu 85+ seviyesine çıkarabilirsin"
    "78 → 86",  "₺7.070 → ₺9.800",  "0,5 ay → 1,2 ay"

Bu sayılar modelden gelirse uydurulur. Finansal bağlamda bu bir bug
değil, kullanıcıya verilmiş yanlış bir taahhüttür. Buradaki her araç
deterministiktir ve döndürdüğü her sayıyı `NumberLedger`'a kaydeder;
`coach_guard.verify_response()` yanıttaki her rakamın bu deftere
kayıtlı olduğunu doğrular.

Şartname: `Docs/ai-koc-v1.md`
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from datetime import date
from typing import Any, Callable, Dict, List, Optional, Tuple

from score_engine import (
    Features, ScoreResult, attribute, compute_score, simulate,
)

COACH_VERSION = "1.0.0"


# ─────────────────────────────────────────────────────────────────────────────
# Sayı kayıt defteri
# ─────────────────────────────────────────────────────────────────────────────

class Kind:
    CURRENCY = "currency"
    PERCENT = "percent"
    SCORE = "score"
    COUNT = "count"
    MONTHS = "months"


@dataclass
class NumberRecord:
    value: float
    kind: str
    label: str
    tool: str


@dataclass
class NumberLedger:
    """Bağlama giren her sayının kaydı.

    Doğrulayıcı, LLM yanıtındaki her rakamı buraya karşı kontrol eder.
    Deftere kayıtlı olmayan bir sayı = halüsinasyon = yanıt reddedilir.
    """
    records: List[NumberRecord] = field(default_factory=list)

    def add(self, value: Optional[float], kind: str, label: str, tool: str = "") -> Optional[float]:
        if value is None or (isinstance(value, float) and math.isnan(value)):
            return None
        self.records.append(NumberRecord(float(value), kind, label, tool))
        return value

    def values(self, kind: Optional[str] = None) -> List[float]:
        return [r.value for r in self.records if kind is None or r.kind == kind]

    def describe(self) -> List[str]:
        return [f"{r.label}: {r.value:g} ({r.kind})" for r in self.records]


# ─────────────────────────────────────────────────────────────────────────────
# Bağlam
# ─────────────────────────────────────────────────────────────────────────────

@dataclass
class CoachContext:
    features: Features
    score: ScoreResult
    prev_score: Optional[ScoreResult] = None
    #: normalize.Ledger — kategori kırılımı için. Yoksa kategori araçları boş döner.
    ledger: Any = None
    as_of: Optional[date] = None
    numbers: NumberLedger = field(default_factory=NumberLedger)

    @property
    def low_confidence(self) -> bool:
        """C < eşik iken skor BANT olarak sunulmalı (skor modeli §7)."""
        from params import P
        return self.score.confidence < P["stage.saglik_C"]


def build_context(features: Features, prev_features: Optional[Features] = None,
                  ledger: Any = None, as_of: Optional[date] = None) -> CoachContext:
    score = compute_score(features)
    prev = compute_score(prev_features) if prev_features is not None else None
    return CoachContext(features=features, score=score, prev_score=prev,
                        ledger=ledger, as_of=as_of)


# ─────────────────────────────────────────────────────────────────────────────
# Araçlar
# ─────────────────────────────────────────────────────────────────────────────
#
# Her araç:
#   · deterministiktir (aynı bağlam → aynı çıktı)
#   · döndürdüğü her sayıyı deftere kaydeder
#   · LLM'e verilecek kadar kompakt bir sözlük döner

def get_score(ctx: CoachContext) -> Dict[str, Any]:
    """Güncel skor, seviye, aşama ve belirsizlik bandı."""
    s, n = ctx.score, ctx.numbers
    n.add(s.score, Kind.SCORE, "güncel skor", "get_score")
    n.add(s.band[0], Kind.SCORE, "band alt", "get_score")
    n.add(s.band[1], Kind.SCORE, "band üst", "get_score")
    out = {
        "skor": s.score,
        "band": list(s.band),
        "seviye": s.level,
        "asama": s.stage_label,
        "guven": round(s.confidence, 2),
        "bant_olarak_sun": ctx.low_confidence,
        "mesaj": s.message,
    }
    if ctx.prev_score is not None:
        d = s.score - ctx.prev_score.score
        n.add(ctx.prev_score.score, Kind.SCORE, "önceki skor", "get_score")
        n.add(abs(d), Kind.SCORE, "skor değişimi", "get_score")
        out["onceki_skor"] = ctx.prev_score.score
        out["degisim"] = d
    return out


def get_score_breakdown(ctx: CoachContext) -> Dict[str, Any]:
    """Altı bileşenin kırılımı — mockup'taki 'Skor Kırılımı' kartı."""
    n = ctx.numbers
    rows = []
    for p in ctx.score.pillars:
        if not p.enabled:
            rows.append({"bilesen": p.label, "durum": "devre dışı",
                         "neden": p.disabled_reason})
            continue
        n.add(round(p.points, 1), Kind.SCORE, f"{p.label} puanı", "get_score_breakdown")
        n.add(round(p.weight_effective, 1), Kind.SCORE, f"{p.label} ağırlığı",
              "get_score_breakdown")
        rows.append({
            "bilesen": p.label,
            "puan": round(p.points, 1),
            "azami": round(p.weight_effective, 1),
            "yuzde": round(p.score_100, 1),
            "alt_metrikler": [
                {"ad": s.label, "deger": round(s.value, 1), "detay": s.detail}
                for s in p.subs if s.value is not None
            ],
            "uyarilar": p.modifiers,
        })
    active = [p for p in ctx.score.pillars if p.enabled and p.score_100 is not None]
    weakest = min(active, key=lambda p: p.score_100) if active else None
    return {"bilesenler": rows,
            "en_zayif": weakest.label if weakest else None}


def get_score_change(ctx: CoachContext) -> Dict[str, Any]:
    """Skor farkının bileşenlere dağılımı.

    Mockup'taki 'geçen aya göre +4 puan' BU ÇIKTIDAN gelir, LLM'in
    tahmininden değil. Katkıların toplamı gösterilen farkı tam kapatır.
    """
    if ctx.prev_score is None:
        return {"durum": "önceki dönem verisi yok"}
    rows = attribute(ctx.prev_score, ctx.score)
    n = ctx.numbers
    for r in rows:
        n.add(abs(round(r["delta"], 1)), Kind.SCORE, f"katkı: {r['label']}",
              "get_score_change")
    n.add(abs(ctx.score.score - ctx.prev_score.score), Kind.SCORE,
          "toplam değişim", "get_score_change")
    return {
        "toplam_degisim": ctx.score.score - ctx.prev_score.score,
        "katkilar": [{"alan": r["label"], "etki": round(r["delta"], 1)}
                     for r in rows],
    }


#: Kullanıcıya anlatılabilir metrik sözlüğü. Anahtar → (etiket, tür, çıkarıcı)
METRICS: Dict[str, Tuple[str, str, Callable[[Features], Optional[float]]]] = {
    "tasarruf_orani":     ("tasarruf oranı", Kind.PERCENT, lambda f: f.s_rate * 100),
    "nakit_akisi_marji":  ("nakit akışı marjı", Kind.PERCENT, lambda f: f.cf_margin * 100),
    "acil_fon_ay":        ("acil durum fonu süresi", Kind.MONTHS, lambda f: round(f.ef_months, 1)),
    "acil_fon_tutar":     ("acil durum fonu", Kind.CURRENCY, lambda f: f.ef_liquid),
    "gelir":              ("aylık net gelir", Kind.CURRENCY, lambda f: f.i_net),
    "gider":              ("aylık gider", Kind.CURRENCY, lambda f: f.e_total),
    "zorunlu_gider":      ("aylık zorunlu gider", Kind.CURRENCY, lambda f: f.e_essential),
    "korunan_tutar":      ("aylık korunan tutar", Kind.CURRENCY, lambda f: f.i_net - f.e_total),
    "kasitli_tasarruf":   ("aylık kasıtlı birikim", Kind.CURRENCY, lambda f: f.s_deliberate),
    "borc_orani":         ("borç ödeme oranı", Kind.PERCENT, lambda f: f.dsr * 100),
    "borc_anapara":       ("toplam borç", Kind.CURRENCY, lambda f: f.debt_principal),
    "taksit_kalan":       ("kalan taksit taahhüdü", Kind.CURRENCY, lambda f: f.installment_remaining),
    "taksit_aylik":       ("aylık taksit yükü", Kind.CURRENCY, lambda f: f.installment_monthly),
    "kart_kullanimi":     ("kart kullanım oranı", Kind.PERCENT,
                           lambda f: None if f.card_utilization is None else f.card_utilization * 100),
    "plansiz_oran":       ("plansız harcama oranı", Kind.PERCENT,
                           lambda f: None if f.imp_rate is None else f.imp_rate * 100),
    "duygusal_oran":      ("duygusal harcama payı", Kind.PERCENT,
                           lambda f: None if f.emo_rate is None else f.emo_rate * 100),
    "gece_orani":         ("gece harcama yoğunlaşması", Kind.PERCENT,
                           lambda f: None if f.night_conc is None else f.night_conc * 100),
    "istege_bagli_pay":   ("isteğe bağlı harcama payı", Kind.PERCENT,
                           lambda f: f.disc_share * 100),
    "butce_asimi":        ("bütçe aşımı", Kind.CURRENCY, lambda f: f.budget_overrun),
}


def get_metric(ctx: CoachContext, name: str) -> Dict[str, Any]:
    """Tek bir metriği adıyla getirir."""
    if name not in METRICS:
        return {"hata": "bilinmeyen metrik", "gecerli_isimler": sorted(METRICS)}
    label, kind, fn = METRICS[name]
    v = fn(ctx.features)
    if v is None:
        return {"metrik": name, "etiket": label, "durum": "veri yok"}
    v = round(v, 1)
    ctx.numbers.add(v, kind, label, "get_metric")
    return {"metrik": name, "etiket": label, "deger": v, "tur": kind}


def get_metrics(ctx: CoachContext, names: List[str]) -> Dict[str, Any]:
    return {"metrikler": [get_metric(ctx, n) for n in names]}


def get_top_categories(ctx: CoachContext, n: int = 5) -> Dict[str, Any]:
    """Kategori bazlı harcama ve REEL değişim.

    Değişim enflasyondan arındırılmış olarak döner ve nominal değişim
    de ayrıca verilir. Koç, nominal artışı tek başına söylerse kullanıcı
    haksız yere suçlanmış olur (veri katmanı N5).
    """
    if ctx.ledger is None:
        return {"durum": "kategori verisi yok"}

    from normalize import active_windows, real_value, windows  # geç import: döngü yok

    W = active_windows(ctx.ledger, windows(ctx.ledger.as_of, 3))
    if len(W) < 2:
        return {"durum": "karşılaştırma için yeterli dönem yok"}

    def agg(w, deflate: bool):
        out: Dict[str, float] = {}
        for a, c, t in ctx.ledger.expenses_cash(w):
            when = t.ts.date() if t is not None else w.start
            val = (real_value(a, when, c, ctx.ledger.raw.cpi, ctx.ledger.as_of)
                   if deflate else a)
            out[c] = out.get(c, 0.0) + val
        return out

    cur_nom, prev_nom = agg(W[0], False), agg(W[1], False)
    cur_real, prev_real = agg(W[0], True), agg(W[1], True)

    from data_model import CATEGORIES, DEFAULT_CATEGORY
    rows = []
    for cat, amount in sorted(cur_nom.items(), key=lambda kv: -kv[1])[:n]:
        label = CATEGORIES.get(cat, CATEGORIES[DEFAULT_CATEGORY]).label
        pn, pr = prev_nom.get(cat, 0.0), prev_real.get(cat, 0.0)
        nom = ((amount / pn) - 1) * 100 if pn > 0 else None
        real = ((cur_real.get(cat, 0.0) / pr) - 1) * 100 if pr > 0 else None
        ctx.numbers.add(round(amount), Kind.CURRENCY, f"{label} harcaması",
                        "get_top_categories")
        if nom is not None:
            ctx.numbers.add(round(abs(nom), 1), Kind.PERCENT,
                            f"{label} nominal değişim", "get_top_categories")
        if real is not None:
            ctx.numbers.add(round(abs(real), 1), Kind.PERCENT,
                            f"{label} reel değişim", "get_top_categories")
        rows.append({
            "kategori": label, "tutar": round(amount),
            "nominal_degisim_yuzde": None if nom is None else round(nom, 1),
            "reel_degisim_yuzde": None if real is None else round(real, 1),
        })
    return {"kategoriler": rows,
            "not": "Değişim bildirilirken REEL oran kullanılmalı; "
                   "nominal oran enflasyonu da içerir."}


def get_risks(ctx: CoachContext) -> Dict[str, Any]:
    """Öncelik sırasına göre risk bayrakları — mockup'taki 'Riskler' sekmesi."""
    f, n = ctx.features, ctx.numbers
    risks: List[Dict[str, Any]] = []

    def add(key, level, label, value=None, kind=None, vlabel=""):
        if value is not None:
            n.add(value, kind, vlabel or label, "get_risks")
        risks.append({"alan": key, "seviye": level, "aciklama": label,
                      "deger": value})

    if f.days_past_due >= 30:
        add("gecikme", "yuksek", "30 günden uzun gecikmiş ödeme",
            f.days_past_due, Kind.COUNT, "gecikme günü")
    elif f.days_past_due >= 1:
        add("gecikme", "yuksek", "gecikmiş ödeme var",
            f.days_past_due, Kind.COUNT, "gecikme günü")
    if f.min_payment_only_months >= 3:
        add("asgari_odeme", "yuksek", "üst üste sadece asgari ödeme",
            f.min_payment_only_months, Kind.COUNT, "asgari ödeme ayı")
    if f.kmh_active:
        add("kmh", "yuksek", "kredili mevduat kullanımı aktif")

    m = round(f.ef_months, 1)
    if m < 1:
        add("acil_fon", "yuksek", "acil durum fonu 1 aydan az",
            m, Kind.MONTHS, "acil durum fonu süresi")
    elif m < 3:
        add("acil_fon", "orta", "acil durum fonu 3 ayın altında",
            m, Kind.MONTHS, "acil durum fonu süresi")

    dsr = round(f.dsr * 100, 1)
    if f.dsr > 0.40:
        add("borc", "yuksek", "borç ödeme oranı yüksek", dsr, Kind.PERCENT, "borç ödeme oranı")
    elif f.dsr > 0.25:
        add("borc", "orta", "borç ödeme oranı izlenmeli", dsr, Kind.PERCENT, "borç ödeme oranı")

    if f.card_utilization is not None and f.card_utilization > 0.70:
        add("kart", "orta", "kart kullanım oranı yüksek",
            round(f.card_utilization * 100), Kind.PERCENT, "kart kullanım oranı")
    if f.cf_margin < 0:
        add("nakit_akisi", "yuksek", "gider gelirden fazla",
            round(abs(f.cf_margin) * 100, 1), Kind.PERCENT, "negatif marj")
    if f.i_cv is not None and f.i_cv > 0.35:
        add("gelir_oynakligi", "orta", "gelir dalgalanması yüksek")
    if f.installment_remaining > f.i_net * 3:
        add("taksit", "orta", "kalan taksit taahhüdü ağır",
            round(f.installment_remaining), Kind.CURRENCY, "kalan taksit taahhüdü")

    order = {"yuksek": 0, "orta": 1, "dusuk": 2}
    risks.sort(key=lambda r: order.get(r["seviye"], 3))
    return {"riskler": risks, "toplam": len(risks)}


# ─────────────────────────────────────────────────────────────────────────────
# Aksiyonlar ve simülasyon
# ─────────────────────────────────────────────────────────────────────────────

@dataclass(frozen=True)
class ActionSpec:
    key: str
    label: str
    effort: int                     # 1 kolay · 2 orta · 3 zor
    #: parametreleri Features değişikliklerine çeviren fonksiyon
    apply: Callable[[Features, Dict[str, float]], Dict[str, Any]]
    default_params: Callable[[Features], Dict[str, float]]


def _a_category_limit(f: Features, p: Dict[str, float]) -> Dict[str, Any]:
    save = p["aylik_tasarruf"]
    return {"e_total": max(0.0, f.e_total - save),
            "budget_overrun": (None if f.budget_overrun is None
                               else max(0.0, f.budget_overrun - save)),
            "limit_breached": 0 if f.limit_breached else f.limit_breached}


def _a_emergency_fund(f: Features, p: Dict[str, float]) -> Dict[str, Any]:
    m = p["aylik_katki"]
    months = p.get("ay", 3)
    return {"s_deliberate": f.s_deliberate + m,
            "ef_liquid": f.ef_liquid + m * months,
            "s_consistency_months": min(6, f.s_consistency_months + 1)}


def _a_reduce_impulse(f: Features, p: Dict[str, float]) -> Dict[str, Any]:
    target = p["hedef_oran"]
    cur = f.imp_rate or 0.0
    freed = max(0.0, (cur - target)) * f.e_total
    return {"imp_rate": target,
            "night_conc": None if f.night_conc is None else f.night_conc * 0.7,
            "regret_rate": None if f.regret_rate is None else f.regret_rate * 0.7,
            "e_total": max(0.0, f.e_total - freed * 0.5),
            "s_deliberate": f.s_deliberate + freed * 0.5}


def _a_extra_debt_payment(f: Features, p: Dict[str, float]) -> Dict[str, Any]:
    extra = p["aylik_ek_odeme"]
    months = p.get("ay", 3)
    # Trend ASLA kötüleştirilmez. İlk sürümde sabit -0,10 yazılıyordu;
    # borcu zaten -%18 hızla azalan bir kullanıcıda bu, "ek ödeme yap"
    # aksiyonunun skoru DÜŞÜRMESİNE yol açıyordu.
    cur = f.debt_trend_3m if f.debt_trend_3m is not None else 0.0
    return {"debt_principal": max(0.0, f.debt_principal - extra * months),
            "card_balance": (None if f.card_balance is None
                             else max(0.0, f.card_balance - extra * months)),
            "debt_trend_3m": min(-0.10, cur)}


def _a_cancel_subscription(f: Features, p: Dict[str, float]) -> Dict[str, Any]:
    save = p["aylik_tasarruf"]
    return {"e_total": max(0.0, f.e_total - save),
            "s_deliberate": f.s_deliberate + save}


ACTIONS: Dict[str, ActionSpec] = {a.key: a for a in [
    ActionSpec("kategori_limiti", "Kategori limiti koy", 2, _a_category_limit,
               lambda f: {"aylik_tasarruf": round(max(200.0, f.e_total * 0.03), -1)}),
    ActionSpec("acil_fon_katkisi", "Acil durum fonuna düzenli katkı", 2,
               _a_emergency_fund,
               lambda f: {"aylik_katki": round(max(250.0, (f.i_net - f.e_total) * 0.20), -1),
                          "ay": 3}),
    ActionSpec("plansiz_azalt", "Plansız harcamayı azalt", 3, _a_reduce_impulse,
               lambda f: {"hedef_oran": max(0.05, (f.imp_rate or 0.2) - 0.08)}),
    ActionSpec("ek_borc_odemesi", "Borca ek ödeme yap", 3, _a_extra_debt_payment,
               lambda f: {"aylik_ek_odeme": round(max(200.0, f.i_net * 0.03), -1),
                          "ay": 3}),
    ActionSpec("abonelik_iptali", "Kullanılmayan aboneliği iptal et", 1,
               _a_cancel_subscription,
               lambda f: {"aylik_tasarruf": round(max(100.0, f.e_total * 0.01), -1)}),
]}


def _clean(changes: Dict[str, Any]) -> Dict[str, Any]:
    return {k: v for k, v in changes.items() if v is not None}


def simulate_action(ctx: CoachContext, action: str,
                    params: Optional[Dict[str, float]] = None) -> Dict[str, Any]:
    """Tek bir aksiyonun skora etkisini DETERMİNİSTİK olarak hesaplar.

    'Bu planı uygularsan skorun 86 olur' cümlesindeki 86 burada üretilir.
    """
    if action not in ACTIONS:
        return {"hata": "bilinmeyen aksiyon", "gecerli": sorted(ACTIONS)}
    spec = ACTIONS[action]
    f = ctx.features
    p = dict(spec.default_params(f))
    p.update(params or {})

    base = simulate(f)                       # yumuşatmasız temel
    after = simulate(f, **_clean(spec.apply(f, p)))
    delta = after.score - base.score

    n = ctx.numbers
    n.add(base.score, Kind.SCORE, "mevcut skor (simülasyon temeli)", "simulate_action")
    n.add(after.score, Kind.SCORE, f"{spec.label} sonrası skor", "simulate_action")
    n.add(abs(delta), Kind.SCORE, f"{spec.label} skor etkisi", "simulate_action")
    for k, v in p.items():
        kind = Kind.CURRENCY if "tutar" in k or "katki" in k or "odeme" in k or "tasarruf" in k else Kind.COUNT
        if k == "hedef_oran":
            n.add(round(v * 100, 1), Kind.PERCENT, "hedef plansız harcama oranı", "simulate_action")
        else:
            n.add(v, kind, f"{spec.label} parametresi ({k})", "simulate_action")

    return {"aksiyon": spec.label, "parametreler": p, "zorluk": spec.effort,
            "skor_once": base.score, "skor_sonra": after.score, "etki": delta}


def build_action_plan(ctx: CoachContext, max_steps: int = 3) -> Dict[str, Any]:
    """Aksiyonları etkiye göre sıralar ve KÜMÜLATİF sonucu hesaplar.

    Kümülatif olması önemli: aksiyonların etkisi toplanabilir değildir
    (aynı bileşeni doyuran iki aksiyonun toplam etkisi, tek tek
    etkilerinin toplamından küçüktür). Koç 'toplam +9 puan' derse ve bu
    ayrı ayrı hesaplanmış etkilerin toplamıysa, vaat tutmaz.
    """
    f = ctx.features
    base = simulate(f)

    scored = []
    for key, spec in ACTIONS.items():
        p = spec.default_params(f)
        try:
            after = simulate(f, **_clean(spec.apply(f, p)))
        except Exception:
            continue
        gain = after.score - base.score
        if gain <= 0:
            continue
        scored.append((gain / spec.effort, gain, key, spec, p))
    scored.sort(reverse=True, key=lambda x: x[0])

    steps, cumulative, prev = [], dict(), base.score
    for _, _, key, spec, p in scored:
        if len(steps) >= max_steps:
            break
        candidate = dict(cumulative)
        candidate.update(_clean(spec.apply(f, p)))
        after = simulate(f, **candidate)
        # Kümülatif skoru düşüren adım plana ALINMAZ. Aksiyonların etkisi
        # toplanabilir değildir; tek başına faydalı bir adım, önceki
        # adımlarla birlikte skoru geriletebilir.
        if after.score < prev:
            continue
        cumulative = candidate
        steps.append({"aksiyon": spec.label, "anahtar": key, "zorluk": spec.effort,
                      "parametreler": p, "kumulatif_skor": after.score,
                      "ek_etki": after.score - prev})
        prev = after.score

    # ── Gösterilen skora sabitleme ─────────────────────────────────────
    #
    # Simülasyon yumuşatmasız hesaplar; kullanıcıya gösterilen skor ise
    # yumuşatılmıştır (skor modeli §8). İkisi farklı olabilir.
    #
    # Plan kartı ham simülasyon tabanını gösterirse, ana sayfada 71 yazan
    # skor plan ekranında "67 → 71" olur. Kullanıcı için bu bir hatadır —
    # ve tam olarak bu ekran veri setiyle ayıklamaya çalıştığımız
    # tutarsızlık türüdür.
    #
    # Çözüm: ÇAPA gösterilen skordur, DELTA simülasyondan gelir.
    anchor = ctx.score.score
    raw_total = (steps[-1]["kumulatif_skor"] - base.score) if steps else 0
    running = anchor
    for s in steps:
        running += s["ek_etki"]
        s["kumulatif_skor"] = int(round(max(0, min(100, running))))

    total = (steps[-1]["kumulatif_skor"] - anchor) if steps else 0
    final = steps[-1]["kumulatif_skor"] if steps else anchor

    n = ctx.numbers
    n.add(anchor, Kind.SCORE, "plan öncesi skor", "build_action_plan")
    for s in steps:
        n.add(s["kumulatif_skor"], Kind.SCORE,
              f"{s['aksiyon']} sonrası kümülatif skor", "build_action_plan")
        n.add(abs(s["ek_etki"]), Kind.SCORE, f"{s['aksiyon']} ek etkisi",
              "build_action_plan")
        for k, v in s["parametreler"].items():
            if k == "hedef_oran":
                n.add(round(v * 100, 1), Kind.PERCENT, "hedef plansız harcama oranı",
                      "build_action_plan")
            else:
                n.add(v, Kind.CURRENCY if k != "ay" else Kind.COUNT,
                      f"{s['aksiyon']} ({k})", "build_action_plan")
    n.add(abs(total), Kind.SCORE, "planın toplam etkisi", "build_action_plan")

    return {
        "skor_simdi": anchor,
        "adimlar": steps,
        "skor_plan_sonrasi": final,
        "toplam_etki": total,
        "ufuk_ay": 3,
        "uyari": "Bu bir projeksiyondur, taahhüt değildir. Sunumda kesinlik "
                 "ifadesi kullanılmamalı.",
    }


# ─────────────────────────────────────────────────────────────────────────────
# Araç kaydı — orkestratörün LLM'e açacağı yüzey
# ─────────────────────────────────────────────────────────────────────────────

TOOLS: Dict[str, Callable[..., Dict[str, Any]]] = {
    "get_score": get_score,
    "get_score_breakdown": get_score_breakdown,
    "get_score_change": get_score_change,
    "get_metric": get_metric,
    "get_metrics": get_metrics,
    "get_top_categories": get_top_categories,
    "get_risks": get_risks,
    "simulate_action": simulate_action,
    "build_action_plan": build_action_plan,
}

TOOL_SCHEMA: List[Dict[str, Any]] = [
    {"name": "get_score", "description": "Güncel finansal sağlık skoru, seviye, aşama, belirsizlik bandı.",
     "input_schema": {"type": "object", "properties": {}}},
    {"name": "get_score_breakdown", "description": "Altı bileşenin puan kırılımı ve alt metrikleri.",
     "input_schema": {"type": "object", "properties": {}}},
    {"name": "get_score_change", "description": "Skor farkının bileşenlere dağılımı (geçen döneme göre).",
     "input_schema": {"type": "object", "properties": {}}},
    {"name": "get_metric", "description": "Tek bir finansal metriği adıyla getirir.",
     "input_schema": {"type": "object", "required": ["name"], "properties": {
         "name": {"type": "string", "enum": sorted(METRICS)}}}},
    {"name": "get_top_categories", "description": "En yüksek harcama kategorileri; nominal ve REEL değişim.",
     "input_schema": {"type": "object", "properties": {
         "n": {"type": "integer", "default": 5}}}},
    {"name": "get_risks", "description": "Öncelik sırasına göre risk bayrakları.",
     "input_schema": {"type": "object", "properties": {}}},
    {"name": "simulate_action", "description": "Tek bir aksiyonun skora etkisini deterministik hesaplar.",
     "input_schema": {"type": "object", "required": ["action"], "properties": {
         "action": {"type": "string", "enum": sorted(ACTIONS)},
         "params": {"type": "object"}}}},
    {"name": "build_action_plan", "description": "Etkiye göre sıralı, kümülatif hesaplanmış aksiyon planı.",
     "input_schema": {"type": "object", "properties": {
         "max_steps": {"type": "integer", "default": 3}}}},
]


def _register_output_text(ctx: CoachContext, obj: Any, tool: str) -> None:
    """Araç çıktısındaki METİNLERDE geçen sayıları da deftere yazar.

    Araçlar yalnızca alan değeri değil, açıklama cümlesi de döndürür:
    "acil durum fonu 1 aydan az", "3 ayın altında". Bu eşikler bizim
    ürettiğimiz güvenilir sayılardır; deftere girmezse koç kendi araç
    çıktısını aynen aktardığında doğrulama onu halüsinasyon sanır.
    """
    from coach_guard import extract_numbers      # geç import: döngü yok

    def walk(o: Any) -> None:
        if isinstance(o, str):
            for t in extract_numbers(o):
                ctx.numbers.add(t.value,
                                t.kind if t.kind != "plain" else Kind.COUNT,
                                f"{tool} açıklama metni", tool)
        elif isinstance(o, dict):
            for v in o.values():
                walk(v)
        elif isinstance(o, (list, tuple)):
            for v in o:
                walk(v)

    walk(obj)


def call_tool(ctx: CoachContext, name: str, args: Optional[Dict] = None) -> Dict[str, Any]:
    if name not in TOOLS:
        return {"hata": "bilinmeyen araç", "gecerli": sorted(TOOLS)}
    out = TOOLS[name](ctx, **(args or {}))
    _register_output_text(ctx, out, name)
    return out
