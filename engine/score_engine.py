"""
Nakitio Finansal Sağlık Skoru — Referans Implementasyon (Model v2.0)

Bu dosya `Docs/skor-modeli-v2.md` spec'inin çalıştırılabilir karşılığıdır.
Spec ile bu kod çeliştiğinde SPEC değil BU KOD esas alınır; spec'teki tüm
sayısal örnekler bu dosya çalıştırılarak üretilmiştir.

Tasarım kuralları:
  1. Saf fonksiyon. I/O yok, rastgelelik yok, zamana bağlılık yok.
     Aynı girdi her zaman aynı çıktıyı verir (replay edilebilirlik).
  2. Girdi = Katman-2 türetilmiş metrikler (Features). Ham işlem değil.
     Ham işlem -> Features dönüşümü ayrı bir servistir (spec Bölüm 4-5).
  3. Hiçbir eksik veri "0 puan" değildir. Eksik veri bileşeni DEVRE DIŞI
     bırakır, ağırlıkları yeniden normalize eder ve güveni (C) düşürür.
  4. Tüm eşikler MODEL_VERSION ile birlikte versiyonlanır.

Python 3.9+
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field, asdict
from typing import Optional, Dict, List, Tuple

from params import P

MODEL_VERSION = "2.0.0"


# ─────────────────────────────────────────────────────────────────────────────
# 0. Yardımcı matematik
# ─────────────────────────────────────────────────────────────────────────────

def clamp(x: float, lo: float = 0.0, hi: float = 1.0) -> float:
    return max(lo, min(hi, x))


def lin(x: float, zero_at: float, hundred_at: float) -> float:
    """Parçalı-doğrusal eşleme, 0-100 arası.

    `hundred_at` noktasında 100, `zero_at` noktasında 0 döner ve arada
    doğrusaldır. hundred_at < zero_at ise "küçük olan iyidir" demektir
    (örn. borç oranı). Uçurum (basamak) yaratmaz, monotondur.
    """
    if hundred_at == zero_at:
        return 100.0 if x == hundred_at else 0.0
    return 100.0 * clamp((x - zero_at) / (hundred_at - zero_at))


def sat(x: float, k: float) -> float:
    """Doygunlaşan eğri: 100*(1-e^(-x/k)). x=k -> 63, x=2k -> 86, x=3k -> 95.

    "Daha fazlası hep iyidir ama getirisi azalır" ilişkileri için.
    Örn: tasarruf oranı. %30 tasarruf %20'den iyidir, ama fark %0->%10
    kadar büyük değildir.
    """
    if x <= 0:
        return 0.0
    return 100.0 * (1.0 - math.exp(-x / k))


def concave(x: float, full_at: float, power: float = 0.6) -> float:
    """İçbükey doyum: 100*min(1, x/full_at)^power.

    "İlk birim en değerlidir" ilişkileri için. Örn: acil durum fonu.
    Sıfırdan 1 aya geçmek, 5 aydan 6 aya geçmekten çok daha değerlidir.
    """
    if x <= 0:
        return 0.0
    return 100.0 * (clamp(x / full_at) ** power)


# ─────────────────────────────────────────────────────────────────────────────
# 1. Girdi sözleşmesi (Katman-2 türetilmiş metrikler)
# ─────────────────────────────────────────────────────────────────────────────

@dataclass
class Features:
    """Skor motorunun TEK girdisi. Tüm alanlar normalizasyon katmanından
    (spec Bölüm 4) geçmiş, enflasyondan arındırılmış, amortize edilmiş,
    iç transferlerden temizlenmiş değerlerdir.

    None = "veri yok" demektir ve ilgili alt metriği devre dışı bırakır.
    0 = "ölçüldü ve sıfır çıktı" demektir. İkisi ASLA karıştırılmamalıdır.
    """

    # ── Kimlik / dönem ────────────────────────────────────────────────────
    user_id: str = "u"
    days_of_data: int = 0                 # ilk işlemden bugüne geçen gün

    # ── Gelir ─────────────────────────────────────────────────────────────
    i_net: float = 0.0                    # son 3 ay net gelir MEDYANI (TRY)
    i_cv: Optional[float] = None          # son 6 ay gelir varyasyon katsayısı
    i_primary_share: Optional[float] = None   # en büyük gelir kaynağının payı
    i_declared: Optional[float] = None    # onboarding'de beyan edilen aylık net

    # ── Gider ─────────────────────────────────────────────────────────────
    e_total: float = 0.0                  # amortize toplam gider (transfer hariç)
    e_essential: float = 0.0              # zorunlu gider (kira/fatura/ulaşım/sağlık/kredi)
    #: Anında erişilebilir bakiye (vadesiz + nakit).
    #:
    #: `Optional` OLMASI ZORUNLUDUR. İlk sürümde `float = 0.0` yazılmıştı ve
    #: motor "bakiyeyi bilmiyorum" ile "bakiyesi sıfır" arasında ayrım
    #: yapamıyordu. Bakiye tutmayan bir veri kaynağı (manuel giriş) bağlanınca
    #: `tampon` alt metriği 0 puan alıyor, yani EKSİK VERİ CEZAYA dönüşüyordu
    #: — 2. kuralın doğrudan ihlali. Ölçüldü: 15 golden profilde sapmanın
    #: %54'ü tek başına bu alandan geliyordu, sağlıklı kullanıcılar -7,3 puan
    #: kaybederken riskliler +3,4 puan kazanıyordu (r = -0,93).
    liquid_balance: Optional[float] = None

    # ── Tasarruf & güvence ────────────────────────────────────────────────
    s_deliberate: float = 0.0             # KASITLI birikim (net transfer, değerleme hariç)
    #: Acil durum fonu likit tutarı. `liquid_balance` ile aynı gerekçeyle
    #: `Optional` — yokluğu `guvence` alt metriğini devre dışı bırakır, 0 puan
    #: vermez.
    ef_liquid: Optional[float] = None
    #: Son 6 ayın kaçında `s_deliberate > 0`. **None = ölçülemedi.**
    #:
    #: `0` ile `None` farkı burada da kritiktir: "altı ayın hiçbirinde
    #: birikim yapmadı" ölçülmüş bir olgudur, "üç aylık geçmişi var, altı
    #: aylık süreklilik ölçülemez" değildir. İkisi karıştırılınca yeni
    #: kullanıcı hiç birikim yapmamış gibi 0 puan alır.
    s_consistency_months: Optional[int] = None
    real_return_gap: Optional[float] = None   # yıllık (birikim getirisi − TÜFE)

    # ── Borç ──────────────────────────────────────────────────────────────
    has_debt_data: bool = True
    debt_principal: float = 0.0           # toplam kalan anapara
    debt_monthly_service: float = 0.0     # aylık kredi + kart asgari üstü ödeme
    installment_monthly: float = 0.0      # aylık taksit yükü
    installment_remaining: float = 0.0    # kalan toplam taksit taahhüdü
    card_balance: Optional[float] = None
    card_limit: Optional[float] = None
    debt_trend_3m: Optional[float] = None     # (anapara_now/anapara_3ay_önce)-1
    days_past_due: int = 0
    min_payment_only_months: int = 0      # üst üste sadece asgari ödenen ay
    kmh_active: bool = False

    # ── Harcama disiplini ─────────────────────────────────────────────────
    budget_planned: Optional[float] = None    # bütçelenen toplam
    budget_overrun: Optional[float] = None    # kategori bazlı AŞIM toplamı (pozitif kısım)
    limit_categories: Optional[int] = None
    limit_breached: Optional[int] = None
    cat_volatility: Optional[float] = None    # kategori harcamalarının ort. CV'si

    # ── Hedefler ──────────────────────────────────────────────────────────
    goals_active: int = 0
    goal_ontrack: Optional[float] = None      # 0-1, hedef büyüklüğüne göre ağırlıklı
    goal_consistency: Optional[float] = None  # 0-1, son 3 ayda plana uyan hedef oranı
    goal_required_monthly: Optional[float] = None  # tüm hedefler için gereken aylık katkı

    # ── Davranış ──────────────────────────────────────────────────────────
    beh_coverage: float = 0.0             # etiketlenmiş/sınıflanmış harcama oranı (TL bazlı)
    imp_rate: Optional[float] = None      # plansız TL / e_total
    emo_rate: Optional[float] = None      # duygusal etiketli TL / e_total
    night_conc: Optional[float] = None    # 20:00-02:00 harcama TL / e_total
    regret_rate: Optional[float] = None   # "düşük memnuniyet" TL / etiketlenmiş TL

    # ── Veri güveni girdileri ─────────────────────────────────────────────
    accounts_declared: int = 1
    accounts_linked: int = 0              # otomatik bağlı hesap sayısı
    categorized_ratio: float = 0.0        # kategorize edilmiş TL / toplam TL
    manual_entry: bool = True             # veri manuel mi giriliyor
    integrity_flag: bool = False          # toplu silme/şüpheli düzenleme tespiti

    #: "linked" (açık bankacılık) · "statement" (ekstre yükleme) · "manual".
    #: Ekstre yükleme ayrı bir kademedir: veri BANKA kaynaklıdır ve
    #: doğruluğu yüksektir, yalnızca SÜREKLİ değildir. Manuel girişle
    #: aynı kefeye konursa güven haksız yere düşük çıkar.
    #: None ise `manual_entry`den çıkarılır (geriye dönük uyumluluk).
    data_source: Optional[str] = None
    #: Son 6 ayın kaçında ekstre yüklenmiş [0,1].
    statement_coverage: Optional[float] = None

    # ── Onboarding (öncül skor için) ──────────────────────────────────────
    onboarding: Dict[str, str] = field(default_factory=dict)

    # ── Önceki dönem (yumuşatma için) ─────────────────────────────────────
    prev_score: Optional[float] = None
    #: Önceki dönemin HAM skoru ve GÜVENİ. Yumuşatmanın yalnızca gerçek
    #: finansal değişime uygulanması için gerekli (bkz. `smoothing_anchor`).
    #: Yoksa eski davranışa düşülür — geriye dönük uyumluluk.
    prev_raw_score: Optional[float] = None
    prev_confidence: Optional[float] = None

    # ── Türetilmişler ─────────────────────────────────────────────────────
    @property
    def cf_margin(self) -> float:
        """Net nakit akışı marjı. Gelir <= 0 ise tanımsız kabul edilir."""
        if self.i_net <= 0:
            return 0.0
        return (self.i_net - self.e_total) / self.i_net

    @property
    def s_rate(self) -> Optional[float]:
        """Kasıtlı tasarruf / gelir. Gelir bilinmiyorsa ORAN TANIMSIZDIR.

        Eskiden 0,0 dönüyordu ve P3'ün `oran` alt metriği 0 puan alıyordu —
        yani gelir kaydı olmayan kullanıcı "hiç birikim yapmıyor" sayılıyordu.
        Paydası olmayan bir oran ölçülememiştir; ceza verilmez, alt metrik
        devre dışı kalır ve güven düşer.
        """
        # PAYI SIFIR OLAN ORAN TANIMSIZ DEĞİL, SIFIRDIR. `s_deliberate`
        # işlemlerden doğrudan ölçülür ve gelire ihtiyaç duymaz: "hiç
        # birikim yapmadı" gelir bilinmese de bilinen bir olgudur. Aksi
        # hâlde geliri gizlemek ölçülmüş bir olumsuzluğu siler — oyunlama
        # kapısı açılır (bkz. t_undefined_ratios_disable_submetrics/E).
        if self.s_deliberate <= 0:
            return 0.0
        if self.i_net <= 0:
            return None
        return self.s_deliberate / self.i_net

    @property
    def ef_months(self) -> Optional[float]:
        """Acil fonun kaç aylık gideri karşıladığı. None = ölçülemedi."""
        if self.ef_liquid is None:
            return None
        base = self.e_essential if self.e_essential > 0 else self.e_total
        if base <= 0:
            return 0.0
        return self.ef_liquid / base

    @property
    def dsr(self) -> Optional[float]:
        """Borç servisi / net gelir. Gelir bilinmiyorsa TANIMSIZ (bkz. `s_rate`).

        Eskiden 1,0 (en kötü) dönüyordu. Bu bir ölçüm değil varsayımdı:
        "geliri yok, demek ki borcu ağır". Gelirsizliğin gerçek riski
        `detect_material_events`'in "gelir kaydı yok" olayıyla ve P1'in
        marj dalıyla zaten bildiriliyor; burada ikinci kez cezalandırmak
        hem çift sayım hem eksik veriye ceza olurdu.
        """
        servis = self.debt_monthly_service + self.installment_monthly
        if servis <= 0:
            return 0.0            # payı sıfır → oran sıfır (bkz. `s_rate`)
        if self.i_net <= 0:
            return None
        return servis / self.i_net

    @property
    def commit_ratio(self) -> Optional[float]:
        """Toplam taahhüt / yıllık net gelir. Gelir yoksa TANIMSIZ (bkz. `dsr`)."""
        taahhut = self.debt_principal + self.installment_remaining
        if taahhut <= 0:
            return 0.0            # payı sıfır → oran sıfır (bkz. `s_rate`)
        if self.i_net <= 0:
            return None
        return taahhut / (self.i_net * 12)

    @property
    def card_utilization(self) -> Optional[float]:
        if self.card_balance is None or not self.card_limit:
            return None
        return self.card_balance / self.card_limit

    @property
    def runway_days(self) -> Optional[float]:
        """Mevcut bakiyenin kaç gün yettiği. None = bakiye verisi yok."""
        if self.liquid_balance is None:
            return None
        if self.e_total <= 0:
            return 90.0
        return self.liquid_balance / (self.e_total / 30.0)

    @property
    def disc_share(self) -> Optional[float]:
        """İsteğe bağlı harcamanın payı. Gider yoksa TANIMSIZ.

        Bu, hatanın en görünür olduğu yerdi: `e_total <= 0` iken 0,0
        dönüyordu ve `lin(0; 0,60 → 0,20)` = **100 puan** veriyordu. Yani
        hiç gider verisi olmayan kullanıcı Harcama Disiplini'nden tam puan
        alıyordu — ölçülmemiş bir şey için ÖDÜL.
        """
        if self.e_total <= 0:
            return None
        return max(0.0, (self.e_total - self.e_essential) / self.e_total)


# ─────────────────────────────────────────────────────────────────────────────
# 2. Çıktı sözleşmesi
# ─────────────────────────────────────────────────────────────────────────────

@dataclass
class SubScore:
    key: str
    label: str
    value: Optional[float]        # 0-100, None = devre dışı
    weight: float                 # bileşen içi ağırlık
    detail: str = ""


@dataclass
class Pillar:
    key: str
    label: str
    weight_nominal: float         # 100'lük skordaki nominal ağırlığı
    weight_effective: float       # yeniden normalize edilmiş ağırlık
    score_100: Optional[float]    # 0-100 bileşen skoru
    points: float                 # skora katkısı (weight_effective ölçeğinde)
    enabled: bool
    subs: List[SubScore]
    modifiers: List[str] = field(default_factory=list)
    disabled_reason: str = ""


@dataclass
class ScoreResult:
    model_version: str
    user_id: str
    score: int                    # kullanıcıya gösterilen nihai skor
    band: Tuple[int, int]         # belirsizlik bandı
    raw_score: float              # S_ham  (yalnız gözlemlenen veriden)
    prior_score: float            # S_öncül (onboarding)
    blended_score: float          # S_karma
    confidence: float             # C ∈ [0,1]
    stage_label: str              # kullanıcıya gösterilen skor adı
    level: str                    # Riskli / Dikkat / Gelişiyor / Dengeli / Güçlü
    message: str
    pillars: List[Pillar]
    smoothing: Dict[str, object]
    material_events: List[str]

    def explain(self) -> str:
        out = [
            f"{self.stage_label}: {self.score}/100  ({self.level})",
            f"  ham={self.raw_score:.1f}  öncül={self.prior_score:.1f}  "
            f"karma={self.blended_score:.1f}  güven C={self.confidence:.2f}  "
            f"band={self.band[0]}-{self.band[1]}",
        ]
        for p in self.pillars:
            if not p.enabled:
                out.append(f"  [-] {p.label:<24} DEVRE DIŞI ({p.disabled_reason})")
                continue
            out.append(
                f"  [{p.score_100:5.1f}] {p.label:<24} "
                f"{p.points:5.2f} / {p.weight_effective:.1f} puan"
                + (f"   ⚠ {', '.join(p.modifiers)}" if p.modifiers else "")
            )
            for s in p.subs:
                if s.value is None:
                    out.append(f"        · {s.label:<28} —      (veri yok)")
                else:
                    out.append(
                        f"        · {s.label:<28} {s.value:5.1f}  ×{s.weight:.2f}"
                        + (f"   {s.detail}" if s.detail else "")
                    )
        if self.material_events:
            out.append(f"  MADDİ OLAY: {', '.join(self.material_events)}")
        return "\n".join(out)


# ─────────────────────────────────────────────────────────────────────────────
# 3. Öncül skor (onboarding) — mevcut v1 modeli korunur
# ─────────────────────────────────────────────────────────────────────────────

ONBOARDING_WEIGHTS: Dict[str, Dict[str, int]] = {
    "zorluk": {
        "birikim_yapamiyorum": -3,
        "impuls": -5,
        "borc": -6,
        "nereye_gidiyor": -4,
        "bilincli_olmak": +2,
    },
    "ay_sonu": {"evet": +8, "bazen": +2, "hayir": -6},
    "takip": {"duzenli": +8, "bazen": +3, "hayir": -5},
    "borc_durumu": {"yok": +8, "yonetilebilir": +2, "zorlaniyorum": -6, "asgari": -8},
    "birikim_6ay": {"duzenli": +8, "ara_sira": +3, "hayir": -5},
}

PRIOR_BASE = P["prior.baz"]
PRIOR_MIN, PRIOR_MAX = P["prior.min"], P["prior.max"]


def prior_score(answers: Dict[str, str]) -> float:
    """Onboarding cevaplarından öncül skor. [40, 75] arasına kelepçelenir.

    Bu skor SADECE öncül olarak kullanılır; gözlemlenen veri arttıkça
    ağırlığı otomatik olarak azalır. Kullanıcı beyanı hiçbir zaman
    bileşen skorlarını (p_i) doğrudan etkilemez — anti-gaming kuralı.
    """
    s = float(P["prior.baz"])
    for q, ans in answers.items():
        s += ONBOARDING_WEIGHTS.get(q, {}).get(ans, 0)
    return clamp(s, P["prior.min"], P["prior.max"])


# ─────────────────────────────────────────────────────────────────────────────
# 4. Bileşenler
# ─────────────────────────────────────────────────────────────────────────────

def _assemble(key, label, weight, subs, modifiers=None, hard_floor=0.0):
    """Alt metrikleri birleştirir. Devre dışı alt metriklerin ağırlığı
    kalanlar arasında yeniden dağıtılır."""
    active = [s for s in subs if s.value is not None]
    if not active:
        return Pillar(key, label, weight, 0.0, None, 0.0, False, subs,
                      modifiers or [], "hiçbir alt metrik hesaplanamadı")
    wsum = sum(s.weight for s in active)
    score = sum(s.value * s.weight for s in active) / wsum
    for m in (modifiers or []):
        score *= P[MODIFIER_KEYS[m]]
    score = max(hard_floor, clamp(score, 0.0, 100.0))
    return Pillar(key, label, weight, weight, score, 0.0, True, subs,
                  modifiers or [], "")


#: Ceza adı -> parametre anahtarı. Değerler ÇALIŞMA ANINDA `P`den okunur.
MODIFIER_KEYS = {
    "gecikme_1_29g": "mod.gecikme_1_29",
    "gecikme_30g+": "mod.gecikme_30",
    "sadece_asgari": "mod.asgari",
    "sadece_asgari_kronik": "mod.asgari_kronik",   # 3+ ay üst üste
    "kmh_aktif": "mod.kmh",
}
def modifiers_now() -> Dict[str, float]:
    """Ceza çarpanlarının ŞU ANKİ değerleri.

    Eskiden bu bir modül düzeyi sözlüktü ve import anında snapshot alıyordu.
    `tune.py` çalışma anında `P`yi değiştirdiğinde sözlük eski değerleri
    göstermeye devam ediyordu — yani parametre taramasında yalan söylüyordu.
    Parametreler ÇALIŞMA ANINDA okunur (CONVENTIONS §5).
    """
    return {k: P[v] for k, v in MODIFIER_KEYS.items()}


# ── P1: Nakit Akışı (nominal 25) ─────────────────────────────────────────────

BREAKEVEN = P["p1.breakeven"]    # gelir = gider noktasının marj alt-skoru


def pillar_cashflow(f: Features) -> Pillar:
    m = f.cf_margin

    if f.i_net <= 0:
        # Gelir yok. "Ölçemedik" DEĞİL, "gelir kaydı yok ama harcama var"
        # durumudur ve gerçek bir kırılganlıktır. Bu durumda kullanıcıyı
        # ayakta tutan tek şey likidite tamponudur; marj sıfırlanır.
        marj = 0.0 if f.e_total > 0 else None
    elif m >= 0:
        # Başabaş nokta (m=0) BREAKEVEN_SCORE'dur, 0 değil: gelirini tam
        # harcamak kırılgandır ama borçlanmak değildir. Tasarruf yokluğu
        # zaten P3'te ayrıca cezalandırılır; burada iki kez sayılmaz.
        be = P["p1.breakeven"]
        marj = be + (100.0 - be) * sat(m, P["p1.marj.k"]) / 100.0
    else:
        # Negatif marj başabaştan aşağı doğrusal iner ve -%10'da sıfırlanır.
        # İki dalın m=0'da AYNI değeri vermesi zorunludur; ilk sürümde bu
        # sağlanmadığı için sıfır noktasında 12 puanlık uçurum oluşmuştu
        # (test_invariants.t_continuity tarafından yakalandı).
        marj = max(0.0, P["p1.breakeven"] * (1.0 + m / P["p1.marj.neg_sifir"]))

    istikrar = None if f.i_cv is None else lin(f.i_cv, P["p1.istikrar.sifir"], P["p1.istikrar.yuz"])
    # Bakiye verisi yoksa tampon ÖLÇÜLEMEZ. Eskiden `runway_days` 0 döndüğü
    # için 0 puan veriliyordu; bu "parası yok" demekti, oysa "bilmiyoruz"du.
    rw = f.runway_days
    tampon = None if rw is None else concave(rw, P["p1.tampon.tam_gun"], P["p1.tampon.us"])

    cesitlilik = None
    if f.i_primary_share is not None:
        # Tek gelir kaynağına bağımlılık bir kırılganlıktır, ama maaşlı
        # çalışan çoğunluğu cezalandırmamak için ağırlığı düşük tutulur.
        cesitlilik = lin(f.i_primary_share, P["p1.cesitlilik.sifir"], P["p1.cesitlilik.yuz"])

    subs = [
        SubScore("marj", "Net nakit akışı marjı", marj, P["p1.marj.w"],
                 "gelir kaydı yok" if f.i_net <= 0 else f"m={m:+.1%}"),
        SubScore("istikrar", "Gelir istikrarı (CV)", istikrar, P["p1.istikrar.w"],
                 "" if f.i_cv is None else f"cv={f.i_cv:.2f}"),
        SubScore("tampon", "Kısa vadeli likidite", tampon, P["p1.tampon.w"],
                 "" if rw is None else f"{rw:.0f} gün"),
        SubScore("cesitlilik", "Gelir çeşitliliği", cesitlilik, P["p1.cesitlilik.w"],
                 "" if f.i_primary_share is None else f"ana kaynak %{f.i_primary_share*100:.0f}"),
    ]
    return _assemble("cashflow", "Nakit Akışı", P["p1.weight"], subs)


# ── P2: Borç Yükü (nominal 20) ───────────────────────────────────────────────

def pillar_debt(f: Features) -> Pillar:
    if not f.has_debt_data:
        return Pillar("debt", "Borç Yükü", P["p2.weight"], 0.0, None, 0.0, False, [],
                      [], "borç verisi bağlanmamış")

    has_any_debt = (f.debt_principal + f.installment_remaining) > 0 or \
                   (f.card_balance or 0) > 0

    if not has_any_debt:
        # Borçsuz kullanıcı. Ceza yok, tam puan. Ancak "hiç kredi geçmişi
        # yok" bir risk değildir — Findeks'ten farklı olarak burada
        # ödüllendirilir.
        subs = [SubScore("borcsuz", "Borç yok", 100.0, 1.0, "")]
        return _assemble("debt", "Borç Yükü", P["p2.weight"], subs)

    # DSR: %10 altı tam puan, %50'de sıfır. Sıfır borç ile %20 DSR'yi
    # ayırt eder (v1 modelindeki hata buydu).
    # Gelir bilinmiyorsa DSR ve taahhüt oranı ölçülemez; ağırlıkları
    # `kart` ve `trend` arasında yeniden dağıtılır (bkz. `Features.dsr`).
    dsr_v = f.dsr
    dsr = None if dsr_v is None else lin(dsr_v, P["p2.dsr.sifir"], P["p2.dsr.yuz"])

    cu = f.card_utilization
    kart = None if cu is None else lin(cu, P["p2.kart.sifir"], P["p2.kart.yuz"])

    cr = f.commit_ratio
    taahhut = None if cr is None else lin(cr, P["p2.taahhut.sifir"], P["p2.taahhut.yuz"])

    trend = None
    if f.debt_trend_3m is not None:
        # Borç azalıyorsa 100, sabitse ~55, artıyorsa düşer.
        trend = lin(f.debt_trend_3m, P["p2.trend.sifir"], P["p2.trend.yuz"])

    subs = [
        SubScore("dsr", "Aylık borç servisi / gelir", dsr, P["p2.dsr.w"],
                 "" if dsr_v is None else f"DSR=%{dsr_v*100:.1f}"),
        SubScore("kart", "Kart kullanım oranı", kart, P["p2.kart.w"],
                 "" if cu is None else f"%{cu*100:.0f}"),
        SubScore("taahhut", "Toplam taahhüt / yıllık gelir", taahhut, P["p2.taahhut.w"],
                 "" if cr is None else f"%{cr*100:.0f}"),
        SubScore("trend", "Borç trendi (3 ay)", trend, P["p2.trend.w"],
                 "" if f.debt_trend_3m is None else f"{f.debt_trend_3m:+.1%}"),
    ]

    mods = []
    if f.days_past_due >= 30:
        mods.append("gecikme_30g+")
    elif f.days_past_due >= 1:
        mods.append("gecikme_1_29g")
    if f.min_payment_only_months >= 3:
        mods.append("sadece_asgari_kronik")
    elif f.min_payment_only_months >= 1:
        mods.append("sadece_asgari")
    if f.kmh_active:
        mods.append("kmh_aktif")

    return _assemble("debt", "Borç Yükü", P["p2.weight"], subs, mods)


# ── P3: Tasarruf & Güvence (nominal 20) ──────────────────────────────────────

def pillar_savings(f: Features) -> Pillar:
    sr = f.s_rate
    # Gelir yoksa oran tanımsızdır → alt metrik kapanır, 0 puan verilmez.
    oran = None if sr is None else (sat(sr, P["p3.oran.k"]) if sr > 0 else 0.0)  # %10 -> 63, %20 -> 86
    # Acil fon verisi yoksa güvence ÖLÇÜLEMEZ (bkz. `tampon`, aynı hata).
    efm = f.ef_months
    guvence = None if efm is None else concave(efm, P["p3.guvence.tam_ay"], P["p3.guvence.us"])   # 1 ay -> 46, 3 ay -> 76
    scm = f.s_consistency_months
    sureklilik = None if scm is None else 100.0 * clamp(scm / 6.0)

    reel = None
    if f.real_return_gap is not None:
        # Enflasyonun altında kalmak bir kayıptır ama davranış hatası
        # değildir; ağırlığı bilinçli olarak düşük.
        reel = lin(f.real_return_gap, P["p3.reel.sifir"], P["p3.reel.yuz"])

    subs = [
        SubScore("oran", "Kasıtlı tasarruf oranı", oran, P["p3.oran.w"],
                 "" if sr is None else f"%{sr*100:.1f}"),
        SubScore("guvence", "Acil durum fonu", guvence, P["p3.guvence.w"],
                 "" if efm is None else f"{efm:.1f} ay"),
        SubScore("sureklilik", "Tasarruf sürekliliği", sureklilik, P["p3.sureklilik.w"],
                 "" if scm is None else f"{scm}/6 ay"),
        SubScore("reel", "Enflasyona karşı koruma", reel, P["p3.reel.w"],
                 "" if f.real_return_gap is None else f"{f.real_return_gap:+.1%}"),
    ]
    return _assemble("savings", "Tasarruf & Güvence", P["p3.weight"], subs)


# ── P4: Harcama Disiplini (nominal 15) ───────────────────────────────────────

def pillar_discipline(f: Features) -> Pillar:
    butce = None
    if f.budget_planned and f.budget_planned > 0 and f.budget_overrun is not None:
        adh = 1.0 - (f.budget_overrun / f.budget_planned)
        butce = 100.0 * clamp(adh)

    limit = None
    if f.limit_categories:
        limit = 100.0 * (1.0 - clamp((f.limit_breached or 0) / f.limit_categories))

    # İsteğe bağlı harcama payı. Not: bu metrik BİLEREK burada ölçülür,
    # P6'da değil. P6 davranış oranları e_total paydası kullandığı için
    # zorunlu gider payından etkilenir; o etki tam olarak burada
    # nötrlenir. Aynı olguyu iki bileşende ölçmek v1'in temel hatasıydı.
    ds = f.disc_share
    istege_bagli = None if ds is None else lin(ds, P["p4.istege_bagli.sifir"],
                                               P["p4.istege_bagli.yuz"])

    oynaklik = None if f.cat_volatility is None else lin(f.cat_volatility, P["p4.oynaklik.sifir"], P["p4.oynaklik.yuz"])

    subs = [
        SubScore("butce", "Bütçe uyumu", butce, P["p4.butce.w"],
                 "" if butce is None else f"aşım {f.budget_overrun:,.0f}/{f.budget_planned:,.0f}"),
        SubScore("limit", "Kategori limitlerine uyum", limit, P["p4.limit.w"],
                 "" if limit is None else f"{f.limit_breached}/{f.limit_categories} aşıldı"),
        SubScore("istege_bagli", "İsteğe bağlı harcama payı", istege_bagli,
                 P["p4.istege_bagli.w"], "" if ds is None else f"%{ds*100:.0f}"),
        SubScore("oynaklik", "Kategori oynaklığı", oynaklik, P["p4.oynaklik.w"],
                 "" if f.cat_volatility is None else f"cv={f.cat_volatility:.2f}"),
    ]
    return _assemble("discipline", "Harcama Disiplini", P["p4.weight"], subs)


# ── P5: Hedef Devamlılığı (nominal 10) ───────────────────────────────────────

GOAL_GRACE_DAYS = int(P["p5.grace_gun"])


def pillar_goals(f: Features) -> Pillar:
    if f.goals_active == 0:
        if f.days_of_data < P["p5.grace_gun"]:
            # Yeni kullanıcıyı hedef koymadı diye cezalandırma.
            return Pillar("goals", "Hedef Devamlılığı", P["p5.weight"], 0.0, None, 0.0,
                          False, [], [], f"hedef yok (ilk {int(P['p5.grace_gun'])} gün muafiyeti)")
        # 60 günden sonra hedefsizlik bir bulgudur, ama sert değildir.
        subs = [SubScore("hedefsiz", "Aktif hedef yok", P["p5.hedefsiz_puan"], 1.0, "")]
        return _assemble("goals", "Hedef Devamlılığı", P["p5.weight"], subs)

    ontrack = None if f.goal_ontrack is None else 100.0 * clamp(f.goal_ontrack)
    tutarlilik = None if f.goal_consistency is None else 100.0 * clamp(f.goal_consistency)

    gercekcilik = None
    if f.goal_required_monthly is not None:
        surplus = f.i_net - f.e_total
        if surplus <= 0:
            gercekcilik = 0.0
        else:
            ratio = f.goal_required_monthly / surplus
            # <=0.8 tam puan (rahat ulaşılabilir), >=1.6 sıfır (imkânsız hedef).
            gercekcilik = lin(ratio, P["p5.gercekcilik.sifir"], P["p5.gercekcilik.yuz"])

    subs = [
        SubScore("ontrack", "Hedeflerin ilerleme durumu", ontrack, P["p5.ontrack.w"],
                 "" if ontrack is None else f"%{f.goal_ontrack*100:.0f}"),
        SubScore("tutarlilik", "Katkı sürekliliği", tutarlilik, P["p5.tutarlilik.w"],
                 "" if tutarlilik is None else f"%{f.goal_consistency*100:.0f}"),
        SubScore("gercekcilik", "Hedef gerçekçiliği", gercekcilik, P["p5.gercekcilik.w"], ""),
    ]
    # Nominal ağırlık `P`den okunur. Literal `10.0` yazılıydı: değer bugün
    # eşit olduğu için sessizdi, ama `p5.weight` değiştirildiğinde bu dal
    # eski değeri kullanacak, `tune.py` P5'i yanlış ölçecek ve `check()`in
    # "bileşenler 100'e toplanır" garantisi kırılacaktı.
    return _assemble("goals", "Hedef Devamlılığı", P["p5.weight"], subs)


# ── P6: Finansal Davranış (nominal 10) ───────────────────────────────────────

BEH_MIN_COVERAGE = P["p6.min_kapsam"]


def pillar_behavior(f: Features) -> Pillar:
    if f.beh_coverage < P["p6.min_kapsam"]:
        return Pillar("behavior", "Finansal Davranış", P["p6.weight"], 0.0, None, 0.0,
                      False, [], [],
                      f"etiketleme kapsamı yetersiz (%{f.beh_coverage*100:.0f} < %{P['p6.min_kapsam']*100:.0f})")

    impuls = None if f.imp_rate is None else lin(f.imp_rate, P["p6.impuls.sifir"], P["p6.impuls.yuz"])
    duygusal = None if f.emo_rate is None else lin(f.emo_rate, P["p6.duygusal.sifir"], P["p6.duygusal.yuz"])
    gece = None if f.night_conc is None else lin(f.night_conc, P["p6.gece.sifir"], P["p6.gece.yuz"])
    pismanlik = None if f.regret_rate is None else lin(f.regret_rate, P["p6.pismanlik.sifir"], P["p6.pismanlik.yuz"])

    subs = [
        SubScore("impuls", "Plansız harcama oranı", impuls, P["p6.impuls.w"],
                 "" if f.imp_rate is None else f"%{f.imp_rate*100:.0f}"),
        SubScore("duygusal", "Duygusal harcama payı", duygusal, P["p6.duygusal.w"],
                 "" if f.emo_rate is None else f"%{f.emo_rate*100:.0f}"),
        SubScore("gece", "Gece harcama yoğunlaşması", gece, P["p6.gece.w"],
                 "" if f.night_conc is None else f"%{f.night_conc*100:.0f}"),
        SubScore("pismanlik", "Harcama sonrası pişmanlık", pismanlik, P["p6.pismanlik.w"],
                 "" if f.regret_rate is None else f"%{f.regret_rate*100:.0f}"),
    ]
    return _assemble("behavior", "Finansal Davranış", P["p6.weight"], subs)


PILLARS = [pillar_cashflow, pillar_debt, pillar_savings,
           pillar_discipline, pillar_goals, pillar_behavior]


# ─────────────────────────────────────────────────────────────────────────────
# 5. Veri güveni (C)
# ─────────────────────────────────────────────────────────────────────────────

C_HIST_FULL_DAYS = P["c.hist_tam_gun"]
C_RAMP_DAYS = P["c.rampa_gun"]          # ilk 3 haftada güven doğrusal olarak açılır


def confidence(f: Features, pillars: List[Pillar]) -> Tuple[float, Dict[str, float]]:
    """C ∈ [0,1]. Skorun ne kadarının gözlemlenen veriye dayandığını söyler.

    C, v1'deki 3 aşamalı formül geçişinin YERİNE geçer. Aşamalar artık
    ayrı formüller değil, C'nin farklı değerlerindeki aynı formüldür.
    Bu sayede gün 30'daki süreksizlik tamamen ortadan kalkar.
    """
    c_hist = clamp(f.days_of_data / P["c.hist_tam_gun"])

    # Veri kaynağı kademeleri. Kaynak neyse kapsamı O belirler — bu bir
    # TAVAN'dır, taban değil.
    #
    #   linked    — sürekli ve banka kaynaklı; bağlı hesap oranı
    #   statement — banka kaynaklı ama KESİNTİLİ; yüklenmemiş dönem kadar
    #               eksik. Kapsam × kategorize oranıyla ölçeklenir.
    #   manual    — kullanıcı beyanı; unutulan işlem riski yapısaldır.
    #
    # İlk sürümde `max(bağlı_oran, kademe)` yazılmıştı. Sonuç: kaynağı
    # "ekstre" olan bir kullanıcı, hesapları sistemde "bağlı" işaretli
    # olduğu için c_cover=1,0 alıyordu — yani tek dönem yüklemiş biri,
    # açık bankacılığa bağlı biriyle aynı güveni görüyordu.
    src = f.data_source or ("linked" if not f.manual_entry else "manual")
    if src == "statement":
        cov = f.statement_coverage if f.statement_coverage is not None else 0.5
        c_cover = P["c.statement_tavan"] * clamp(cov) * clamp(f.categorized_ratio)
    elif src == "manual":
        c_cover = P["c.manual_tavan"] * clamp(f.categorized_ratio)
    elif f.accounts_declared > 0:
        c_cover = clamp(f.accounts_linked / f.accounts_declared)
    else:
        c_cover = 0.0

    c_compl = clamp(f.categorized_ratio)

    if f.i_declared and f.i_declared > 0 and f.i_net > 0:
        c_verif = 1.0 - clamp(abs(f.i_declared - f.i_net) / f.i_declared)
    else:
        c_verif = P["c.verif_varsayilan"]   # beyan yok / doğrulanamıyor -> nötr-düşük

    # Bileşen kapsamı: kapanan bileşenler VE açık bir bileşenin içinde verisi
    # olmayan ALT METRİKLER güveni düşürür.
    #
    # İlk sürümde yalnızca `p.enabled` sayılıyordu. Bir bileşen dört alt
    # metriğinin üçünü kaybetse bile "tam kapsamlı" görünüyordu. Sonuç:
    # bakiye tutmayan bir veri kaynağı P1'in tamponunu ve P3'ün güvencesini
    # kaybediyor, ama güven 0,88'de kalıyordu — motor kör olduğunu bilmiyordu.
    # Ölçüldü: girdi yüzeyinin %37'sini kaybeden bir kaynak yalnızca 0,09
    # güven kaybediyordu.
    #
    # 2. kural üç şey ister: bileşeni devre dışı bırak, ağırlıkları yeniden
    # normalize et, GÜVENİ DÜŞÜR. İlk ikisi `_assemble`da yapılıyordu;
    # üçüncüsü burada eksikti.
    total_w = sum(p.weight_nominal for p in pillars)
    covered_w = 0.0
    for p_ in pillars:
        if not p_.enabled:
            continue
        sub_w = sum(x.weight for x in p_.subs)
        act_w = sum(x.weight for x in p_.subs if x.value is not None)
        covered_w += p_.weight_nominal * ((act_w / sub_w) if sub_w > 0 else 1.0)
    c_pillar = covered_w / total_w if total_w else 0.0

    c = (P["c.hist.w"] * c_hist + P["c.cover.w"] * c_cover
         + P["c.compl.w"] * c_compl + P["c.verif.w"] * c_verif
         + P["c.pillar.w"] * c_pillar)

    # İlk 3 hafta rampası. Sert bir eşik (örn. "14 günden azsa C<=0.15")
    # kullanmıyoruz; eşik, tam da kaldırmaya çalıştığımız türden bir
    # süreksizlik yaratır. Rampa aynı korumayı sürekli biçimde sağlar.
    c *= clamp(f.days_of_data / P["c.rampa_gun"])

    if f.integrity_flag:
        # Veri bütünlüğü şüphesi skoru DÜŞÜRMEZ (suçlu saymayız), yalnızca
        # güveni düşürür: band genişler ve UI'da inceleme bayrağı çıkar.
        c *= P["c.integrity_carpan"]

    parts = {"c_hist": c_hist, "c_cover": c_cover, "c_compl": c_compl,
             "c_verif": c_verif, "c_pillar": c_pillar}
    return clamp(c), parts


# ─────────────────────────────────────────────────────────────────────────────
# 6. Aşama etiketi, seviye, mesaj
# ─────────────────────────────────────────────────────────────────────────────

def stage_label(c: float, days: int) -> str:
    """Aşama artık bir FORMÜL değil, yalnızca bir SUNUM etiketidir."""
    if c < P["stage.gecis_C"] or days < 8:
        return "Farkındalık Başlangıç Skoru"
    if c < P["stage.saglik_C"]:
        return "Geçiş Skoru"
    return "Finansal Sağlık Skoru"


LEVELS = [
    (0,  39,  "Riskli",    "Bazı alanlarda desteğe ihtiyacın var. Küçük bir adımla başlayabiliriz."),
    (40, 59,  "Dikkat",    "Bazı alanlarda kontrol kaybı oluşabilir. Öncelikleri birlikte belirleyelim."),
    (60, 74,  "Gelişiyor", "İyi bir başlangıç var, düzenli devam etmek önemli."),
    (75, 89,  "Dengeli",   "Finansal davranışların oldukça dengeli."),
    (90, 100, "Güçlü",     "Harika gidiyorsun, finansal farkındalığın yüksek."),
]


def level_of(score: float) -> Tuple[str, str]:
    """Seviye HER ZAMAN gösterilen tam sayı skordan türetilir.

    Ondalıklı skorla karşılaştırma yapılırsa (örn. 39.6) aralıkların
    arasına düşer ve yanlış seviye döner. Bu, ilk implementasyonda
    yakalanan gerçek bir hataydı; regresyon testi test_level_bands().
    """
    s = int(round(score))
    for lo, hi, name, msg in LEVELS:
        if lo <= s <= hi:
            return name, msg
    return (LEVELS[0][2], LEVELS[0][3]) if s < 0 else (LEVELS[-1][2], LEVELS[-1][3])


# ─────────────────────────────────────────────────────────────────────────────
# 7. Yumuşatma ve maddi olaylar
# ─────────────────────────────────────────────────────────────────────────────

EWMA_ALPHA = P["s.alpha"]
EWMA_ALPHA_MATERIAL = P["s.alpha_maddi"]    # maddi olayda aşağı yönde hızlı tepki
MAX_MONTHLY_MOVE = P["s.max_hareket"]


def detect_material_events(f: Features) -> List[str]:
    """Yumuşatmayı ve aylık hareket sınırını AŞAĞI yönde bypass eden olaylar.

    Kural asimetriktir: kötü haber hemen görünür, iyi haber yumuşatılır.
    Bu hem dürüstlük hem anti-gaming gereğidir.
    """
    ev = []
    if f.days_past_due >= 30:
        ev.append("30+ gün gecikmiş ödeme")
    elif f.days_past_due >= 1:
        ev.append("gecikmiş ödeme")
    if f.kmh_active:
        ev.append("KMH kullanımı başladı")
    if f.min_payment_only_months >= 3:
        ev.append("3+ ay sadece asgari ödeme")
    if f.i_declared and f.i_net > 0 and f.i_net < 0.60 * f.i_declared:
        ev.append("gelirde %40+ düşüş")
    if f.i_net <= 0 and f.e_total > 0 and f.days_of_data >= 30:
        ev.append("gelir kaydı yok")
    # Maddi olay ÖLÇÜLMÜŞ bir olgudur. Acil fon verisi yokken "kritik" demek
    # kullanıcıya olmayan bir bulguyu bildirmek olur — üstelik bu olay
    # yumuşatmanın aşağı sınırını kaldırdığı için skoru serbest bırakır.
    if f.ef_months is not None and f.ef_months < 0.25 and f.e_essential > 0:
        ev.append("acil durum fonu kritik seviyede")
    return ev


def smoothing_anchor(f: Features, c_now: float, prior: float) -> Tuple[Optional[float], bool]:
    """Yumuşatmanın çapası: önceki dönemin ÖLÇÜMÜ, BUGÜNKÜ güvenle.

    Yumuşatma, kullanıcının FİNANSAL DURUMUNUN skoru çok hızlı
    oynatmasını engellemek için vardır. Ama bizim ÖLÇÜMÜMÜZÜN düzelmesi
    onun finansal durumundaki bir değişiklik değildir — bizim kendi
    hatamızın düzelmesidir. Onu yumuşatmak, yanlış olduğunu bildiğimiz
    bir sayıyı bile bile göstermek demektir.

    Somut sonucu: anket sonrası ilk ekstresini yükleyen sağlıklı bir
    kullanıcı, eski davranışta 46'dan 55'e çıkıyordu — oysa en iyi
    tahminimiz 72'ydi. 17 puan saklıyorduk ve bu kullanıcıyı demotive
    ediyordu. Yeni davranışta anında 72 görür; sonraki aylar ise finansal
    durumu gerçekten değişmedikçe yavaş hareket eder.

    Oyunlanamaz: güven yalnızca gerçek veri yükleyerek artar ve 1'de
    doyar. Yukarı yönlü tek seferlik bir düzeltmedir, tekrarlanamaz.

    Döner: (çapa, güven_düzeltmesi_uygulandı_mı)
    """
    if f.prev_score is None:
        return None, False
    if f.prev_raw_score is None or f.prev_confidence is None:
        return f.prev_score, False        # eski davranış

    # Önceki dönemin kendi güveniyle üretilmiş karma skoru
    blended_prev = (f.prev_confidence * f.prev_raw_score
                    + (1 - f.prev_confidence) * prior)
    # Gösterilen ile aradaki fark = geçmiş yumuşatmadan birikmiş gecikme.
    # Bu gecikme KORUNUR (yumuşatmanın kendisi budur), yalnızca güven
    # bileşeni bugüne taşınır.
    offset = f.prev_score - blended_prev
    anchor = c_now * f.prev_raw_score + (1 - c_now) * prior + offset
    return anchor, abs(anchor - f.prev_score) >= 0.5


def smooth(new: float, prev: Optional[float], material: bool) -> Tuple[float, Dict]:
    """Asimetrik yumuşatma.

    Yukarı yön her zaman yavaştır (skor tek ayda satın alınamaz).
    Aşağı yönde maddi olay varsa hem alfa yükselir hem ±8 sınırı kalkar
    (kullanıcı kötü haberi gecikmeli öğrenmemeli).
    """
    if prev is None:
        return new, {"applied": False, "reason": "ilk hesaplama"}

    fast = bool(material and new < prev)
    alpha = P["s.alpha_maddi"] if fast else P["s.alpha"]
    ewma = alpha * new + (1 - alpha) * prev

    capped, limited = ewma, False
    if not fast:
        mm = P["s.max_hareket"]
        lo, hi = prev - mm, prev + mm
        if not (lo <= ewma <= hi):
            capped = clamp(ewma, lo, hi)
            limited = True
    return capped, {
        "applied": True, "alpha": alpha, "prev": round(prev, 1),
        "ewma": round(ewma, 1), "cap_applied": limited,
        "material_bypass": fast,
    }


# ─────────────────────────────────────────────────────────────────────────────
# 8. Ana giriş noktası
# ─────────────────────────────────────────────────────────────────────────────

def compute_score(f: Features) -> ScoreResult:
    pillars = [fn(f) for fn in PILLARS]

    # Devre dışı bileşenlerin ağırlığı aktifler arasında yeniden dağıtılır.
    active = [p for p in pillars if p.enabled and p.score_100 is not None]
    w_active = sum(p.weight_nominal for p in active)
    for p in pillars:
        if p.enabled and w_active > 0:
            p.weight_effective = 100.0 * p.weight_nominal / w_active
            p.points = p.score_100 * p.weight_effective / 100.0
        else:
            p.weight_effective, p.points = 0.0, 0.0

    raw = sum(p.points for p in active)
    c, _ = confidence(f, pillars)
    prior = prior_score(f.onboarding)
    blended = c * raw + (1 - c) * prior

    events = detect_material_events(f)
    anchor, conf_adjusted = smoothing_anchor(f, c, prior)
    final, sm = smooth(blended, anchor, bool(events))
    final = clamp(final, 0.0, 100.0)
    sm["guven_duzeltmesi"] = conf_adjusted
    if conf_adjusted:
        sm["capa"] = round(anchor, 1)
        sm["gosterilen_onceki"] = f.prev_score

    half = max(P["s.band_min"], P["s.band_k"] * (1 - c))
    band = (int(round(max(0, final - half))), int(round(min(100, final + half))))

    level, msg = level_of(final)
    return ScoreResult(
        model_version=MODEL_VERSION, user_id=f.user_id, score=int(round(final)),
        band=band, raw_score=raw, prior_score=prior, blended_score=blended,
        confidence=c, stage_label=stage_label(c, f.days_of_data), level=level,
        message=msg, pillars=pillars, smoothing=sm, material_events=events,
    )


# ─────────────────────────────────────────────────────────────────────────────
# 9. Katkı ayrıştırma — "geçen aya göre +4 puan" bunun çıktısıdır
# ─────────────────────────────────────────────────────────────────────────────

def attribute(prev: ScoreResult, curr: ScoreResult) -> List[Dict]:
    """İki skor arasındaki farkı bileşenlere dağıtır.

    Toplam fark, bileşen katkıları + güven değişimi + yumuşatma artığı
    olarak TAM olarak kapanır. UI'daki "+4 puan" bu listeden gelir,
    LLM'den değil.
    """
    rows = []
    pm = {p.key: p for p in prev.pillars}
    for p in curr.pillars:
        q = pm.get(p.key)
        if q is None:
            continue
        d = (p.points - q.points) * curr.confidence
        if abs(d) < 0.01:
            continue
        rows.append({"key": p.key, "label": p.label, "delta": round(d, 2),
                     "from": None if q.score_100 is None else round(q.score_100, 1),
                     "to": None if p.score_100 is None else round(p.score_100, 1)})

    d_conf = (curr.confidence - prev.confidence) * (curr.raw_score - curr.prior_score)
    if abs(d_conf) >= 0.01:
        rows.append({"key": "confidence", "label": "Veri güveni artışı",
                     "delta": round(d_conf, 2),
                     "from": round(prev.confidence, 2), "to": round(curr.confidence, 2)})

    explained = sum(r["delta"] for r in rows)
    residual = (curr.score - prev.score) - explained
    if abs(residual) >= 0.01:
        rows.append({"key": "smoothing", "label": "Yumuşatma / yuvarlama",
                     "delta": round(residual, 2), "from": None, "to": None})

    rows.sort(key=lambda r: -abs(r["delta"]))
    return rows


# ─────────────────────────────────────────────────────────────────────────────
# 10. Simülasyon — AI koçun vaat ettiği sayılar BURADAN gelir
# ─────────────────────────────────────────────────────────────────────────────

def simulate(f: Features, **changes) -> ScoreResult:
    """Bir senaryoyu deterministik olarak yeniden hesaplar.

    Kritik mimari kural: "Bu planı uygularsan skorun 86 olur" cümlesindeki
    86 sayısı BU FONKSİYONDAN gelir. LLM sayı üretmez, yalnızca bu çıktıyı
    anlatır. Aksi hâlde model sayı uydurur ve kullanıcıya yanlış finansal
    beklenti verilir.
    """
    d = asdict(f)
    d.pop("prev_score", None)
    sim = Features(**{**d, **changes})
    sim.prev_score = None          # simülasyon yumuşatmaya tabi değildir
    return compute_score(sim)
