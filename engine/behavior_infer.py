"""
Nakitio — Davranış Çıkarımı (etiketsiz plansızlık ölçümü)

PROBLEM: Ekstre yüklemeyle veri aylık ve toplu gelir. Hiçbir kullanıcı
200 işlemi geriye dönük "plansızdı / streslikken aldım / pişman oldum"
diye etiketlemez. Etikete dayanan davranış bileşeni (P6) ve mockup'taki
Davranış Analizi ekranının tamamı bu yüzden ölür.

ÇÖZÜM: iki kademeli ölçüm.

  Kademe 1 — ÇIKARIM.  Ekstrenin kendisinden, kullanıcı hiçbir şey
      yapmadan hesaplanır. Yinelenen ödeme planlıdır; ilk kez görülen
      bir merchant'ta, hafta sonu, aynı gün üst üste yapılan, kategori
      medyanının çok üzerindeki bir harcama plansızlığa işaret eder.
      İade edilmiş bir harcama neredeyse tanımı gereği pişmanlıktır.

  Kademe 2 — ETİKET.  Yükleme sonrası kısa bir triyaj: 8–12 işlem,
      en bilgi verici olanlar seçilerek sorulur. Etiketler çıkarımı
      KALİBRE eder, yerine geçmez.

Harmanlama, skor modelindeki güven (C) mantığının aynısıdır:

    oran = w × etiketli_oran + (1 − w) × çıkarımsal_oran
    w    = min(1, etiket_sayısı / 40)

DÜRÜSTLÜK SINIRI: plansızlık iyi çıkarılır, DUYGU çıkarılamaz. "Stresliydim"
ile "kendimi ödüllendirdim" arasındaki fark ekstrede yoktur. Duygusal pay
için çıkarım yalnızca zayıf bir vekildir ve UI'da iddia olarak değil,
soru olarak sunulmalıdır (bkz. `Docs/ekstre-alimi-v1.md` §6).

Şartname: `Docs/ekstre-alimi-v1.md`
"""

from __future__ import annotations

import math
import statistics
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta
from typing import Dict, List, Optional, Tuple

from data_model import (
    CATEGORIES, DEFAULT_CATEGORY, EMOTIONAL_TAGS, Transaction, TxnKind,
)

from params import P

INFER_VERSION = "1.0.0"


# ─────────────────────────────────────────────────────────────────────────────
# Kategori bazlı plansızlık ön olasılıkları
# ─────────────────────────────────────────────────────────────────────────────
#
# Bir kategorinin taban plansızlık eğilimi. Kira plansız olmaz; oyun
# harcaması çoğunlukla plansızdır. Bunlar ÖN OLASILIKTIR — tek başına
# karar vermez, diğer sinyallerle birleşir.
#
# Değerler literatür ve makul akıl yürütmeyle konuldu; gerçek etiket
# verisiyle kalibre edilmelidir (bkz. `calibrate_intercept`).

CATEGORY_IMPULSE_PRIOR: Dict[str, float] = {
    "kira": 0.00, "aidat": 0.00, "faturalar": 0.02, "sigorta": 0.02,
    "vergi": 0.02, "egitim": 0.05, "saglik": 0.08, "cocuk": 0.10,
    "iletisim": 0.05, "ulasim": 0.12, "market": 0.15,
    "ev": 0.35, "kisisel": 0.40, "abonelik": 0.30,
    "restoran": 0.45, "giyim": 0.55, "elektronik": 0.55, "spor": 0.35,
    "hediye": 0.50, "tatil": 0.40,
    "eglence": 0.65, "alkol_tutun": 0.60, "sans_oyunu": 0.80,
    "diger": 0.30,
}

#: "Rahatlama" kategorileri — duygusal harcamanın en sık göründüğü yerler.
COMFORT_CATEGORIES = {"restoran", "eglence", "alkol_tutun", "giyim",
                      "sans_oyunu", "kisisel"}


# ─────────────────────────────────────────────────────────────────────────────
# Sinyaller
# ─────────────────────────────────────────────────────────────────────────────

@dataclass
class Signals:
    """Tek bir işlem için ekstreden çıkarılabilen davranış sinyalleri."""
    category: str = DEFAULT_CATEGORY
    amount: float = 0.0
    recurring: bool = False           # düzenli, tanınan ödeme → planlı
    merchant_novel: bool = False      # ilk kez görülen merchant
    amount_z: float = 0.0             # kategori medyanına göre sapma
    cluster_size: int = 1             # aynı gün isteğe bağlı işlem sayısı
    is_installment: bool = False      # taksitle alınmış
    days_since_income: Optional[int] = None
    weekend: bool = False
    refunded: bool = False            # sonradan iade edilmiş
    night: Optional[bool] = None      # saat verisi yoksa None


#: Lojistik model katsayıları. Pozitif = plansızlığa işaret.
#: `b0` kalibrasyonla kaydırılır; diğerleri sabit kalır.
W = {
    "b0": -1.15,
    "recurring": -2.40,        # en güçlü PLANLI sinyali
    "novel": 0.55,
    "category": 2.60,          # (prior − 0.5) ile çarpılır
    "amount": 0.85,
    "cluster": 0.70,
    "installment": 0.45,
    "payday": 0.50,
    "weekend": 0.35,
    "refunded": 1.60,          # iade → neredeyse kesin plansız
    "night": 0.75,
}


def _sigmoid(z: float) -> float:
    return 1.0 / (1.0 + math.exp(-max(-30.0, min(30.0, z))))


def impulse_probability(s: Signals, b0: Optional[float] = None) -> float:
    """Bir işlemin plansız olma olasılığı [0,1]."""
    prior = CATEGORY_IMPULSE_PRIOR.get(s.category, 0.30)
    z = (b0 if b0 is not None else W["b0"])
    z += W["recurring"] * (1.0 if s.recurring else 0.0)
    z += W["novel"] * (1.0 if s.merchant_novel else 0.0)
    z += W["category"] * (prior - 0.5)
    z += W["amount"] * min(1.0, max(0.0, s.amount_z) / 3.0)
    z += W["cluster"] * min(1.0, (s.cluster_size - 1) / 3.0)
    z += W["installment"] * (1.0 if s.is_installment else 0.0)
    z += W["refunded"] * (1.0 if s.refunded else 0.0)
    z += W["weekend"] * (1.0 if s.weekend else 0.0)
    if s.days_since_income is not None and 0 <= s.days_since_income <= 3:
        z += W["payday"]
    if s.night:                                   # None ise sinyal yok
        z += W["night"]
    return _sigmoid(z)


def emotion_probability(s: Signals) -> float:
    """Duygusal harcama olasılığı — ZAYIF vekil.

    Ekstrede duygu yoktur. Buradaki tahmin yalnızca "rahatlama
    kategorisi + gece/hafta sonu + kümelenme" örüntüsüne dayanır ve
    plansızlık tahmininden belirgin biçimde daha güvenilmezdir.

    UI kuralı: bu sayı hiçbir zaman "duygusal harcaman %14" diye İDDİA
    olarak sunulmaz. "Bunlar duygusal harcama olabilir mi?" diye SORU
    olarak sunulur ve cevap etiket olarak toplanır.
    """
    if s.category not in COMFORT_CATEGORIES:
        return 0.03
    z = -1.9
    z += 0.9 if s.night else 0.0
    z += 0.5 if s.weekend else 0.0
    z += 0.8 * min(1.0, (s.cluster_size - 1) / 3.0)
    z += 0.6 * min(1.0, max(0.0, s.amount_z) / 3.0)
    z += 1.2 if s.refunded else 0.0
    return _sigmoid(z)


# ─────────────────────────────────────────────────────────────────────────────
# Sinyal çıkarımı (defterden)
# ─────────────────────────────────────────────────────────────────────────────

RECURRING_MIN_SEEN = 3
RECURRING_AMOUNT_TOL = 0.20


def build_signals(ledger, window) -> List[Tuple[Transaction, Signals]]:
    """Bir penceredeki harcamalar için sinyalleri üretir.

    `ledger` = normalize.Ledger. Tüm geçmiş, merchant tanınırlığı ve
    kategori medyanları için kullanılır; sinyaller yalnızca `window`
    içindeki işlemler için döner.
    """
    raw = ledger.raw
    all_purchases = [t for t in raw.transactions
                     if t.kind == TxnKind.PURCHASE and not t.is_internal_transfer]

    # Merchant geçmişi
    seen: Dict[str, List[Transaction]] = {}
    for t in all_purchases:
        seen.setdefault(t.merchant_id or "", []).append(t)

    # Kategori medyanları (tüm geçmiş)
    by_cat: Dict[str, List[float]] = {}
    for t in all_purchases:
        by_cat.setdefault(t.category or DEFAULT_CATEGORY, []).append(t.outflow)
    cat_med = {c: statistics.median(v) for c, v in by_cat.items() if v}
    cat_sd = {c: (statistics.pstdev(v) or 1.0) for c, v in by_cat.items() if len(v) > 1}

    # Gelir günleri (maaş yakınlığı için)
    income_days = sorted(t.ts.date() for t in raw.transactions
                         if t.kind == TxnKind.INCOME and not t.is_unusual)

    # Aynı gün isteğe bağlı işlem kümeleri
    day_counts: Dict[date, int] = {}
    for t in all_purchases:
        w = CATEGORIES.get(t.category or DEFAULT_CATEGORY,
                           CATEGORIES[DEFAULT_CATEGORY]).essential_weight
        if w <= 0.45:
            day_counts[t.ts.date()] = day_counts.get(t.ts.date(), 0) + 1

    out: List[Tuple[Transaction, Signals]] = []
    for t in all_purchases:
        d = t.ts.date()
        if not window.contains(d):
            continue
        cat = t.category or DEFAULT_CATEGORY
        hist = seen.get(t.merchant_id or "", [])

        recurring = False
        if len(hist) >= RECURRING_MIN_SEEN:
            amts = [x.outflow for x in hist if x.outflow > 0]
            if amts:
                med = statistics.median(amts)
                if med > 0 and abs(t.outflow - med) / med <= RECURRING_AMOUNT_TOL:
                    recurring = True
        if t.recurrence_id:
            recurring = True

        med, sd = cat_med.get(cat, t.outflow), cat_sd.get(cat, 1.0)
        z = (t.outflow - med) / sd if sd > 0 else 0.0

        prev_income = [x for x in income_days if x <= d]
        dsi = (d - prev_income[-1]).days if prev_income else None

        # Saat verisi: ekstrelerde çoğunlukla YOKTUR. 00:00 damgası
        # "gece harcaması" değil, "saat bilinmiyor" demektir.
        night = None if (t.ts.hour == 0 and t.ts.minute == 0) else \
            (t.ts.hour >= 20 or t.ts.hour < 2)

        out.append((t, Signals(
            category=cat, amount=t.outflow,
            recurring=recurring,
            merchant_novel=len(hist) <= 1,
            amount_z=z,
            cluster_size=day_counts.get(d, 1),
            is_installment=bool(t.installment_plan_id),
            days_since_income=dsi,
            weekend=d.weekday() >= 5,
            refunded=t.refunded_amount > 0,
            night=night,
        )))
    return out


# ─────────────────────────────────────────────────────────────────────────────
# Kalibrasyon
# ─────────────────────────────────────────────────────────────────────────────

def calibrate_intercept(pairs: List[Tuple[Signals, bool]],
                        max_shift: float = 2.5) -> float:
    """Etiketli örneklerden `b0` kaymasını bulur.

    Yalnızca kesişim (intercept) kalibre edilir, katsayılar değil.
    Gerekçe: 20–60 etiketle çok parametreli bir model aşırı uyum yapar.
    Kesişim kaydırma az veriyle sağlamdır ve kullanıcının GENEL
    plansızlık düzeyini yakalar — kişiselleştirmenin en değerli kısmı da
    budur.
    """
    if len(pairs) < 8:
        return W["b0"]
    observed = sum(1 for _, y in pairs if y) / len(pairs)
    observed = min(0.95, max(0.05, observed))

    lo, hi = W["b0"] - max_shift, W["b0"] + max_shift
    for _ in range(40):                      # ikili arama
        mid = (lo + hi) / 2
        pred = sum(impulse_probability(s, mid) for s, _ in pairs) / len(pairs)
        if pred < observed:
            lo = mid
        else:
            hi = mid
    return (lo + hi) / 2


# ─────────────────────────────────────────────────────────────────────────────
# Toplu ölçüm ve harmanlama
# ─────────────────────────────────────────────────────────────────────────────

LABEL_FULL_WEIGHT = P["infer.etiket_tam"]   # bu kadar etikette çıkarım devre dışı


@dataclass
class BehaviorEstimate:
    imp_rate: Optional[float] = None
    emo_rate: Optional[float] = None
    regret_rate: Optional[float] = None
    night_conc: Optional[float] = None
    #: Etiketin ağırlığı [0,1]. 0 = tamamen çıkarım, 1 = tamamen etiket.
    label_weight: float = 0.0
    label_count: int = 0
    inferred_only: bool = True
    #: Skor motoruna verilecek etkin kapsam.
    coverage: float = 0.0
    b0: float = W["b0"]
    #: Saat verisi olan işlemlerin payı — 0 ise gece metriği ölçülemez.
    time_available: float = 0.0


#: Çıkarım tek başına bu kapsamı üretir. Etiketli ölçümden düşüktür:
#: söyleyecek bir şeyimiz var ama daha az kesin.
INFERRED_COVERAGE = P["infer.cikarim_kapsam"]


def estimate_behavior(ledger, window,
                      disc_share: float) -> BehaviorEstimate:
    """Çıkarım + etiketleri harmanlayarak davranış oranlarını üretir."""
    sig = build_signals(ledger, window)
    if not sig:
        return BehaviorEstimate()

    tags = {t.txn_id: t for t in ledger.raw.behavior_tags}
    labeled = [(s, tags[t.id].planned is False)
               for t, s in sig if t.id in tags and tags[t.id].planned is not None]

    b0 = calibrate_intercept(labeled)
    n = len(labeled)
    w = min(1.0, n / P["infer.etiket_tam"])

    total = sum(s.amount for _, s in sig) or 1.0
    scale = max(0.0, min(1.0, disc_share))

    # ── Çıkarımsal oranlar (tutar ağırlıklı) ───────────────────────────
    inf_imp = sum(impulse_probability(s, b0) * s.amount for _, s in sig) / total
    inf_emo = sum(emotion_probability(s) * s.amount for _, s in sig) / total

    # ── Etiketli oranlar ───────────────────────────────────────────────
    lab_imp = lab_emo = lab_regret = None
    tagged_amt = sum(s.amount for t, s in sig if t.id in tags)
    if tagged_amt > 0:
        unplanned = sum(s.amount for t, s in sig
                        if t.id in tags and tags[t.id].planned is False)
        emotional = sum(s.amount for t, s in sig
                        if t.id in tags and tags[t.id].emotion in EMOTIONAL_TAGS)
        lab_imp = (unplanned / tagged_amt) * scale
        lab_emo = (emotional / tagged_amt) * scale
        rated = sum(s.amount for t, s in sig
                    if t.id in tags and tags[t.id].satisfaction is not None)
        if rated > 0:
            low = sum(s.amount for t, s in sig
                      if t.id in tags and tags[t.id].satisfaction == 1)
            lab_regret = low / rated

    def blend(lab: Optional[float], inf: float) -> float:
        return inf if lab is None else w * lab + (1 - w) * inf

    # ── Pişmanlık: iade oranı ALT SINIRDIR ─────────────────────────────
    # İnsanlar pişman oldukları her şeyi iade etmez. İade oranı gerçek
    # pişmanlığın altında kalır; bu yüzden bir vekil katsayısıyla
    # ölçeklenir ve etiket geldiğinde hızla ona devredilir.
    refunded_amt = sum(s.amount for _, s in sig if s.refunded)
    inf_regret = min(0.60, (refunded_amt / total) * 2.5)

    # ── Gece: saat verisi yoksa ÖLÇÜLEMEZ ──────────────────────────────
    timed = [(t, s) for t, s in sig if s.night is not None]
    time_avail = (sum(s.amount for _, s in timed) / total) if timed else 0.0
    night_conc = None
    if time_avail >= 0.50:
        night_conc = sum(s.amount for _, s in timed if s.night) / total

    return BehaviorEstimate(
        imp_rate=blend(lab_imp, inf_imp * scale if lab_imp is None else inf_imp),
        emo_rate=blend(lab_emo, inf_emo * scale if lab_emo is None else inf_emo),
        regret_rate=blend(lab_regret, inf_regret),
        night_conc=night_conc,
        label_weight=w, label_count=n, inferred_only=(n == 0),
        coverage=max(P["infer.cikarim_kapsam"], w),
        b0=b0, time_available=time_avail,
    )


# ─────────────────────────────────────────────────────────────────────────────
# Triyaj — hangi işlemler sorulmalı
# ─────────────────────────────────────────────────────────────────────────────

def select_for_triage(ledger, window, k: int = 10) -> List[Dict]:
    """Yükleme sonrası kullanıcıya sorulacak işlemleri seçer.

    Rastgele veya "en büyük k" seçmez. Bilgi kazancına göre seçer:

        değer = tutar_payı × belirsizlik,   belirsizlik = 1 − |2p − 1|

    Yani modelin KARARSIZ olduğu ve tutarca ÖNEMLİ olan işlemler. Zaten
    emin olduğu bir kira ödemesini sormak hiçbir şey öğretmez; 3.400 TL'lik
    kararsız bir harcamayı sormak modeli belirgin biçimde düzeltir.

    Zaten etiketlenmiş işlemler tekrar sorulmaz.
    """
    tags = {t.txn_id for t in ledger.raw.behavior_tags}
    sig = [(t, s) for t, s in build_signals(ledger, window) if t.id not in tags]
    if not sig:
        return []

    total = sum(s.amount for _, s in sig) or 1.0
    labeled = [(s, True) for t, s in build_signals(ledger, window)
               if t.id in {x.txn_id for x in ledger.raw.behavior_tags}]
    b0 = W["b0"] if not labeled else W["b0"]

    scored = []
    for t, s in sig:
        p = impulse_probability(s, b0)
        uncertainty = 1.0 - abs(2 * p - 1)
        value = (s.amount / total) * uncertainty
        scored.append((value, p, t, s))
    scored.sort(reverse=True, key=lambda x: x[0])

    out = []
    for value, p, t, s in scored[:k]:
        out.append({
            "txn_id": t.id,
            "merchant": t.merchant_raw or t.description_raw,
            "kategori": CATEGORIES.get(s.category, CATEGORIES[DEFAULT_CATEGORY]).label,
            "tutar": round(s.amount),
            "tarih": t.ts.date().isoformat(),
            "tahmin_plansiz": round(p, 2),
            "bilgi_degeri": round(value, 4),
            "neden": _explain(s, p),
        })
    return out


def _explain(s: Signals, p: float) -> str:
    """Kullanıcıya gösterilecek kısa gerekçe. Çıkarımı ŞEFFAF kılar —
    kullanıcı neyi onayladığını bilmeli."""
    if s.recurring:
        return "düzenli tekrar eden bir ödeme gibi görünüyor"
    reasons = []
    if s.merchant_novel:
        reasons.append("ilk kez görülen bir yer")
    if s.amount_z > 1.5:
        reasons.append("bu kategoride alışılmışın üzerinde")
    if s.cluster_size >= 3:
        reasons.append(f"aynı gün {s.cluster_size} isteğe bağlı harcama")
    if s.refunded:
        reasons.append("sonradan iade edilmiş")
    if s.is_installment:
        reasons.append("taksitle alınmış")
    if s.weekend:
        reasons.append("hafta sonu")
    return " · ".join(reasons) if reasons else "kategori eğilimine göre"
