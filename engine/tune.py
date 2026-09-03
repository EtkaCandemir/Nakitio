"""
Nakitio — Parametre Duyarlılık Analizi

"Skorlama tablosunu ayarlayalım" demek `params.P`deki her sayıyı
tartışmak demektir. Ama hepsi eşit önemde DEĞİLDİR: bazılarını iki
katına çıkarsan hiçbir kullanıcının skoru 1 puan bile oynamaz;
bazılarında %10'luk bir değişiklik herkesi bir seviye kaydırır.

Bu araç her parametreyi makul aralığında tarar, golden profillerin
skorunu yeniden hesaplar ve **etkiyi ölçer**. Sonuç: hangi sayıları
tartışmaya değer, hangilerini varsayılanda bırakabiliriz.

Sayılar burada YAZILMAZ. Docstring'e "85 parametre · 10 profil" diye
sabit yazılmıştı ve ikisi de bayatlamıştı (gerçekte 96 ve 15). Ölçüm
aracının kendi kapsamı hakkında yanlış konuşması, ölçtüğü şeye olan
güveni de bozar — sayılar `len(P)` ve `len(_profiles())`ten okunur.

Çalıştırma:
    python3 engine/tune.py                 # duyarlılık sıralaması
    python3 engine/tune.py --param <key>   # tek parametrenin eğrisi
    python3 engine/tune.py --set k=v,k=v   # geçici değişiklik + etkisi
"""

from __future__ import annotations

import statistics
import sys
from typing import Dict, List, Optional, Tuple

from params import M, P
from score_engine import compute_score

STEPS = 7          # her parametre için tarama noktası


def _profiles():
    from golden_profiles import PROFILES
    return [(k, v[0]) for k, v in PROFILES.items()]


def _scores() -> Dict[str, int]:
    return {k: compute_score(f).score for k, f in _profiles()}


def _measure() -> Dict[str, Dict[str, object]]:
    """Her profil için DÖRT ölçü.

    Yalnızca gösterilen tam sayı skora bakmak yanıltıcıdır: yumuşatma ve
    yuvarlama, ham skordaki gerçek değişimi yutar. `p6.min_kapsam`
    örneğinde bileşen tamamen KAPANIYOR (ham 84,87 → 83,78) ama
    gösterilen skor 82'de kalıyordu ve parametre "etkisiz" görünüyordu.

    Ayrıca bazı parametreler skoru hiç etkilemez ama SUNUMU değiştirir:
    `s.band_k` bandı, `stage.saglik_C` aşama etiketini ve skorun bant mı
    tek sayı mı gösterileceğini belirler. Bunlar da ölçülmeli.
    """
    out = {}
    for k, f in _profiles():
        r = compute_score(f)
        out[k] = {"skor": r.score, "ham": r.raw_score,
                  "band": r.band[1] - r.band[0],
                  "asama": r.stage_label, "seviye": r.level}
    return out


BASE = _scores()
BASE_M = _measure()


def sweep(key: str, steps: int = STEPS) -> List[Tuple[float, Dict[str, int]]]:
    """Parametreyi [lo, hi] aralığında tarar, her noktada skorları döner."""
    meta = M[key]
    orig = P[key]
    out = []
    try:
        for i in range(steps):
            v = meta.lo + (meta.hi - meta.lo) * i / (steps - 1)
            P[key] = v
            _renormalize_if_weight(key, orig, v)
            out.append((v, _scores()))
    finally:
        P[key] = orig
        _restore_weights()
    return out


#: Ağırlık grupları — biri değişince kalanlar orantılı olarak yeniden dağıtılır.
#: Aksi hâlde "P1 ağırlığını 35 yap" dediğinde toplam 110 olur ve ölçüm
#: parametrenin etkisini değil, bozuk toplamı ölçer.
WEIGHT_GROUPS = {
    "bilesen": ["p1.weight", "p2.weight", "p3.weight", "p4.weight",
                "p5.weight", "p6.weight"],
    "p1": ["p1.marj.w", "p1.istikrar.w", "p1.tampon.w", "p1.cesitlilik.w",
           "p1.zamanlama.w"],
    "p2": ["p2.dsr.w", "p2.kart.w", "p2.taahhut.w", "p2.trend.w",
                "p2.maliyet.w"],
    "p3": ["p3.oran.w", "p3.guvence.w", "p3.sureklilik.w", "p3.reel.w",
           "p3.net_varlik.w"],
    "p4": ["p4.butce.w", "p4.limit.w", "p4.istege_bagli.w", "p4.oynaklik.w"],
    "p5": ["p5.ontrack.w", "p5.tutarlilik.w", "p5.gercekcilik.w",
           "p5.plan_uyumu.w"],
    "p6": ["p6.impuls.w", "p6.duygusal.w", "p6.gece.w", "p6.pismanlik.w"],
    "c": ["c.hist.w", "c.cover.w", "c.compl.w", "c.verif.w", "c.pillar.w"],
}
_SNAPSHOT = dict(P)


def _group_of(key: str) -> Optional[str]:
    for g, keys in WEIGHT_GROUPS.items():
        if key in keys:
            return g
    return None


def _renormalize_if_weight(key: str, orig: float, new: float) -> None:
    g = _group_of(key)
    if g is None:
        return
    others = [k for k in WEIGHT_GROUPS[g] if k != key]
    total = sum(_SNAPSHOT[k] for k in WEIGHT_GROUPS[g])
    kalan = total - new
    pay = sum(_SNAPSHOT[k] for k in others)
    if pay <= 0:
        return
    for k in others:
        P[k] = _SNAPSHOT[k] * kalan / pay


def _restore_weights() -> None:
    for k, v in _SNAPSHOT.items():
        P[k] = v


def sensitivity(key: str) -> Dict[str, float]:
    """Bir parametrenin etkisi: aralık boyunca skorların ne kadar oynadığı."""
    meta = M[key]
    orig = P[key]
    seri = []
    try:
        for i in range(STEPS):
            v = meta.lo + (meta.hi - meta.lo) * i / (STEPS - 1)
            P[key] = v
            _renormalize_if_weight(key, orig, v)
            seri.append(_measure())
    finally:
        P[key] = orig
        _restore_weights()

    skor_d, ham_d, band_d, etiket_d = {}, {}, 0.0, 0
    for name, _ in _profiles():
        sv = [m[name]["skor"] for m in seri]
        hv = [m[name]["ham"] for m in seri]
        skor_d[name] = max(sv) - min(sv)
        ham_d[name] = max(hv) - min(hv)
        band_d = max(band_d, max(m[name]["band"] for m in seri)
                     - min(m[name]["band"] for m in seri))
        etiket_d += len({m[name]["asama"] for m in seri}) - 1
        etiket_d += len({m[name]["seviye"] for m in seri}) - 1

    swings = list(skor_d.values())
    return {
        "azami_oynama": max(swings),
        "ortalama_oynama": statistics.mean(swings),
        "ham_oynama": max(ham_d.values()),
        "band_oynama": band_d,
        "etiket_degisimi": etiket_d,
        "en_cok_etkilenen": max(skor_d, key=skor_d.get),
        "etkilenen_profil": sum(1 for v in swings if v >= 1),
    }


#: Bu parametreler `compute_score` içinde DEĞİL, `derive_features`
#: aşamasında çalışır (ham işlem → Features). Golden profiller Features
#: seviyesinde sabit olduğu için oradan ölçülemezler; fixture'ı baştan
#: kurarak ölçmek gerekir.
DERIVATION_PARAMS = {"infer.etiket_tam", "infer.cikarim_kapsam"}


def sensitivity_derivation(key: str) -> Dict[str, float]:
    """Türetme aşaması parametrelerini fixture'ı yeniden kurarak ölçer."""
    from fixture_didem import AS_OF, build_raw
    from normalize import build_features

    meta, orig = M[key], P[key]
    skorlar, hamlar, impler = [], [], []
    try:
        for i in range(5):
            P[key] = meta.lo + (meta.hi - meta.lo) * i / 4
            f, _ = build_features(build_raw(), AS_OF)
            r = compute_score(f)
            skorlar.append(r.score)
            hamlar.append(r.raw_score)
            impler.append((f.imp_rate or 0) * 100)
    finally:
        P[key] = orig
    return {
        "azami_oynama": max(skorlar) - min(skorlar),
        "ortalama_oynama": float(max(skorlar) - min(skorlar)),
        "ham_oynama": max(hamlar) - min(hamlar),
        # Skoru oynatmasa bile kullanıcının GÖRDÜĞÜ metriği değiştirebilir:
        # `infer.etiket_tam` plansız harcama oranını %8'den %15'e çıkarıyor.
        # Davranış ekranındaki sayı bu; skor sabit kalsa da kullanıcı için
        # anlamı tamamen farklı.
        "metrik_oynama": max(impler) - min(impler),
        "band_oynama": 0.0, "etiket_degisimi": 0,
        "en_cok_etkilenen": "didem (fixture)",
        "etkilenen_profil": 1 if max(skorlar) != min(skorlar) else 0,
    }


def rank() -> List[Tuple[str, Dict[str, float]]]:
    out = [(k, sensitivity_derivation(k) if k in DERIVATION_PARAMS
            else sensitivity(k)) for k in P]
    out.sort(key=lambda x: (-x[1]["azami_oynama"], -x[1]["ortalama_oynama"]))
    return out


# ─────────────────────────────────────────────────────────────────────────────

def report() -> None:
    print("NAKITIO — PARAMETRE DUYARLILIK ANALİZİ")
    print(f"{len(P)} parametre · {len(_profiles())} golden profil · "
          f"her parametre {STEPS} noktada tarandı")
    print("=" * 92)
    print("Aşağıdaki 'oynama', parametre makul aralığının bir ucundan diğerine")
    print("götürüldüğünde bir kullanıcının skorunun kaç puan değiştiğidir.\n")

    rows = rank()
    onemli = [r for r in rows if r[1]["azami_oynama"] >= 3]
    orta = [r for r in rows if 1 <= r[1]["azami_oynama"] < 3]
    # SIFIR oynama ile KÜÇÜK oynama aynı şey değildir.
    #
    # Oynama tam olarak 0 ise parametre muhtemelen "önemsiz" değil,
    # HİÇ TETİKLENMEMİŞTİR: golden profillerden hiçbiri o kod yolundan
    # geçmiyordur. Örneğin hiçbir profilde `data_source="statement"`
    # yok, dolayısıyla `c.statement_tavan` ölçülemiyor — oysa ürünün
    # ana veri kaynağı o. Bunu "etkisiz" diye raporlamak, ölçüm
    # eksikliğini bulgu gibi sunmak olur.
    kucuk = [r for r in rows
             if r[1]["azami_oynama"] < 1 and r[1]["ham_oynama"] >= 0.05]
    sunum = [r for r in rows
             if r[1]["azami_oynama"] < 1 and r[1]["ham_oynama"] < 0.05
             and (r[1]["band_oynama"] > 0 or r[1]["etiket_degisimi"] > 0
                  or r[1].get("metrik_oynama", 0) >= 1)]
    olculemedi = [r for r in rows
                  if r[1]["azami_oynama"] < 1 and r[1]["ham_oynama"] < 0.05
                  and r[1]["band_oynama"] == 0 and r[1]["etiket_degisimi"] == 0
                  and r[1].get("metrik_oynama", 0) < 1]

    def blok(baslik, items, limit=None):
        print(f"── {baslik} ({len(items)}) " + "─" * max(0, 68 - len(baslik)))
        print(f"  {'parametre':<26} {'şimdi':>8} {'aralık':>14} "
              f"{'azami':>6} {'ort':>5}  en çok etkilenen")
        for k, s in (items[:limit] if limit else items):
            m = M[k]
            print(f"  {k:<26} {P[k]:>8.3g} "
                  f"{f'{m.lo:g} – {m.hi:g}':>14} "
                  f"{s['azami_oynama']:>6.1f} {s['ortalama_oynama']:>5.1f}"
                  f"  {s['en_cok_etkilenen']}")
        print()

    blok("YÜKSEK ETKİ — bunları beraber ayarlamalıyız", onemli)
    blok("ORTA ETKİ — ikinci turda bakılır", orta, limit=14)

    print(f"── DÜŞÜK ETKİ ({len(kucuk)}) " + "─" * 58)
    print("  Ham skoru oynatıyor ama yumuşatma/yuvarlama yutuyor.")
    for k, s_ in kucuk:
        print(f"    {k:<26} ham oynama {s_['ham_oynama']:.2f} puan")
    print()

    print(f"── SUNUMU ETKİLER ({len(sunum)}) " + "─" * 52)
    print("  Skoru değiştirmez, GÖSTERİMİ değiştirir: bant genişliği,")
    print("  aşama adı, seviye etiketi. Ayrı bir karar konusu.")
    for k, s_ in sunum:
        parts = []
        if s_["band_oynama"]:
            parts.append(f"bant ±{s_['band_oynama']:.0f}")
        if s_["etiket_degisimi"]:
            parts.append(f"{s_['etiket_degisimi']} etiket kayması")
        if s_.get("metrik_oynama", 0) >= 1:
            parts.append(f"gösterilen metrik ±{s_['metrik_oynama']:.0f} puan")
        print(f"    {k:<26} {' · '.join(parts)}")
    print()

    print(f"── ⚠ ÖLÇÜLEMEDİ ({len(olculemedi)}) " + "─" * 54)
    print("  Bu parametreler HİÇ TETİKLENMEDİ: golden profillerden hiçbiri")
    print("  ilgili kod yolundan geçmiyor. 'Etkisiz' DEĞİL, 'ölçülemedi'.")
    print("  Bunları ayarlamadan önce golden sete uygun profil eklenmeli.")
    print("  " + ", ".join(k for k, _ in olculemedi))
    print()
    print("=" * 92)
    print(f"ÖZET: {len(onemli)} yüksek · {len(orta)} orta · {len(kucuk)} düşük "
          f"· {len(sunum)} sunum · {len(olculemedi)} ölçülemedi")
    print(f"Beraber ayarlanacak olan {len(onemli)} sayı. "
          f"{len(olculemedi)} sayı için önce test profili gerekiyor.")


def curve(key: str) -> None:
    if key not in P:
        print(f"bilinmeyen parametre: {key}")
        print("geçerli olanlar:", ", ".join(sorted(P)))
        return
    m = M[key]
    print(f"{key} — {m.label}")
    print(f"grup: {m.group} · tür: {m.kind} · şu an: {P[key]:g}")
    if m.note:
        print(f"not: {m.note}")
    print("=" * 92)
    rows = sweep(key, steps=9)
    names = [n for n, _ in _profiles()]
    print(f"  {'değer':>9}  " + "".join(f"{n[:7]:>8}" for n in names))
    for v, s in rows:
        mark = " ←" if abs(v - P[key]) < 1e-9 else ""
        print(f"  {v:>9.4g}  " + "".join(f"{s[n]:>8}" for n in names) + mark)
    print()
    print(f"  {'şimdiki':>9}  " + "".join(f"{BASE[n]:>8}" for n in names))


def apply_set(spec: str) -> None:
    """Geçici değişiklik uygular ve etkisini gösterir."""
    changes = {}
    for part in spec.split(","):
        k, _, v = part.partition("=")
        k, v = k.strip(), v.strip()
        if k not in P:
            print(f"bilinmeyen parametre: {k}")
            return
        changes[k] = float(v)

    print("DEĞİŞİKLİK ETKİSİ")
    print("=" * 92)
    for k, v in changes.items():
        print(f"  {k:<26} {P[k]:>9.4g}  →  {v:<9.4g}   {M[k].label}")
    for k, v in changes.items():
        P[k] = v
    yeni = _scores()
    print()
    print(f"  {'profil':<10} {'önce':>6} {'sonra':>6} {'fark':>6}")
    toplam = 0
    for n in BASE:
        d = yeni[n] - BASE[n]
        toplam += abs(d)
        isaret = f"{d:+d}" if d else "—"
        print(f"  {n:<10} {BASE[n]:>6} {yeni[n]:>6} {isaret:>6}")
    print(f"\n  toplam mutlak kayma: {toplam} puan / {len(BASE)} profil")
    print("\n  ⚠ Bu geçici bir denemedir. Kalıcı yapmak için params.py'yi düzenle,")
    print("    sonra golden_profiles.py ve test_invariants.py'yi çalıştır.")
    _restore_weights()


if __name__ == "__main__":
    if len(sys.argv) > 2 and sys.argv[1] == "--param":
        curve(sys.argv[2])
    elif len(sys.argv) > 2 and sys.argv[1] == "--set":
        apply_set(sys.argv[2])
    else:
        report()
