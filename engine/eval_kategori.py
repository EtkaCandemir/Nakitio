"""Nakitio — Kategorizasyon Değerlendirmesi

`gold_kategori.GOLD` setine karşı N9 katmanını ölçer.

BİRİNCİL METRİK 25 YÖNLÜ DOĞRULUK DEĞİLDİR
-------------------------------------------
Skor kategoriyi en ağır olarak `essential_weight` üzerinden görür:
`e_essential` → `ef_months` (P3) ve `disc_share` (P4). Dolayısıyla

    "market" yerine "restoran"  → |0,85 − 0,15| = 0,70 hata   ← pahalı
    "eğlence" yerine "tatil"    → |0,00 − 0,00| = 0,00 hata   ← bedava

Bu yüzden asıl rakam **tutarla ağırlıklı essential_weight mutlak hatası**dır.
Doğruluk yüzdesi ikincil bilgidir; kural yazma emeğini o değil bu yönlendirir.

AŞIRI İDDİA
-----------
Altın sette `kategori=None` olan satırlarda doğru cevap "bilmiyorum"dur.
Model bunlara kategori atarsa, bilmediği şey hakkında `essential_weight`
uydurmuş olur. Şu anki motor bunların hepsine `diger` (0,40) veriyor —
yani %37'lik bir dilimde ortalama bir tahmin yürütüyor. Bu metrik onu ölçer.
"""

from __future__ import annotations

import sys
from datetime import datetime
from typing import Dict, List, Optional, Tuple

from data_model import (CATEGORIES, DEFAULT_CATEGORY, Account, AccountType,
                        CategorySource, Transaction)
from gold_kategori import GOLD, GoldRow, SINIFLAR, essential_of
from normalize import categorize


def _tahmin() -> Dict[str, Tuple[Optional[str], str]]:
    """Her ham metin için motorun kararı: (kategori, kaynak).

    `CategorySource.NONE` → motor eşleştiremedi. Kategori alanında yine
    `diger` yazar ama bu bir KARAR değil, varsayılandır: ayrımı burada
    koruyoruz, çünkü çekimserliği ölçmek istiyoruz.
    """
    txns = [Transaction(id=f"g{i}", account_id="a", ts=datetime(2026, 7, 1),
                        amount=-r.tutar, description_raw=r.ham, merchant_raw=r.ham)
            for i, r in enumerate(GOLD)]
    categorize(txns)
    out = {}
    for r, t in zip(GOLD, txns):
        kat = None if t.category_source == CategorySource.NONE else t.category
        out[r.ham] = (kat, t.category_source.value)
    return out


def calistir(ayrinti: bool = False) -> int:
    tah = _tahmin()

    etiketli = [r for r in GOLD if r.kategori is not None]
    cekimser_beklenen = [r for r in GOLD if r.kategori is None]

    t_etiketli = sum(r.tutar for r in etiketli)
    t_cekimser = sum(r.tutar for r in cekimser_beklenen)
    t_hepsi = t_etiketli + t_cekimser

    # ── Kapsam ────────────────────────────────────────────────────────
    kaps_t = sum(r.tutar for r in GOLD if tah[r.ham][0] is not None)

    # ── Etiketli satırlarda doğruluk ve essential hatası ──────────────
    dogru_t = hata_agirlikli = 0.0
    cozulmeyen_t = olculemeyen_t = 0.0
    hatalar: List[Tuple[GoldRow, Optional[str], float]] = []
    for r in etiketli:
        pred = tah[r.ham][0]
        g_ess = essential_of(r.kategori)
        if pred is None:
            # Motor çekimser kaldı ama cevap vardı → kaçırılmış kapsam.
            # essential hatası hesaplanmaz; ayrı raporlanır.
            cozulmeyen_t += r.tutar
            continue
        p_ess = CATEGORIES[pred].essential_weight
        if pred == r.kategori:
            dogru_t += r.tutar
        # Ağırlığı bilinmeyen kategorilerde essential HATASI ÖLÇÜLEMEZ —
        # bilinmeyen ile bilinmeyeni karşılaştırmak anlamsızdır. Bunlar
        # MAE paydasına da girmez, yoksa metrik sahte biçimde iyileşir.
        if p_ess is None or g_ess is None:
            olculemeyen_t += r.tutar
            continue
        d = abs(p_ess - g_ess)
        hata_agirlikli += d * r.tutar
        if pred != r.kategori and d > 0.001:
            hatalar.append((r, pred, d))

    olculen_t = t_etiketli - cozulmeyen_t - olculemeyen_t
    mae = (hata_agirlikli / olculen_t) if olculen_t else 0.0

    # ── Aşırı iddia: bilinemeyene kategori atama ──────────────────────
    asiri = [r for r in cekimser_beklenen if tah[r.ham][0] is not None]
    asiri_t = sum(r.tutar for r in asiri)

    # ── Uydurulan ağırlık: motor NONE dese bile e_essential 0,40 kullanır
    uydurulan_t = sum(r.tutar for r in cekimser_beklenen
                      if tah[r.ham][0] is None)
    varsayilan_w = CATEGORIES[DEFAULT_CATEGORY].essential_weight

    print("NAKİTİO — KATEGORİZASYON DEĞERLENDİRMESİ")
    print("=" * 74)
    print(f"{len(GOLD)} işyeri metni · {sum(r.adet for r in GOLD)} satır · "
          f"{t_hepsi:,.0f} TL\n")

    print("KAPSAM")
    print("-" * 74)
    print(f"  motor kategori atadı        : {kaps_t:>10,.0f} TL  "
          f"(%{kaps_t/t_hepsi*100:.0f})")
    print(f"  cevabı olup kaçırılan       : {cozulmeyen_t:>10,.0f} TL  "
          f"(%{cozulmeyen_t/t_hepsi*100:.0f})  ← kural/sözlük açığı")

    print("\nDOĞRULUK — cevabı olan ve motorun karar verdiği satırlarda")
    print("-" * 74)
    if olculen_t:
        print(f"  tam isabet (tutarca)        : "
              f"%{dogru_t/(t_etiketli - cozulmeyen_t)*100:.0f}")
        print(f"  essential ölçülemeyen       : {olculemeyen_t:>10,.0f} TL  "
              f"(ağırlığı bilinmeyen kategori)")
        print(f"  essential_weight MAE        : {mae:.3f}   ← BİRİNCİL METRİK")
        print(f"     (0,00 = kusursuz · 0,70 = market'i restoran sanmak)")
    else:
        print("  ölçülecek satır yok")

    print("\nAŞIRI İDDİA — altın set 'bilinemez' diyor, motor ne yaptı")
    print("-" * 74)
    print(f"  bilinemez toplam            : {t_cekimser:>10,.0f} TL  "
          f"(%{t_cekimser/t_hepsi*100:.0f})")
    print(f"  motor yine de kategori attı : {asiri_t:>10,.0f} TL  "
          f"(%{asiri_t/t_cekimser*100:.0f} of bilinemez)")
    print(f"  motor çekimser kaldı        : {uydurulan_t:>10,.0f} TL")
    if varsayilan_w is None:
        print(f"     ✓ e_essential bunlara SABİT ağırlık uygulamıyor; oran"
              f" bilinen\n       harcamadan tahmin edilip toplama genişletiliyor.")
    else:
        print(f"     ⚠ ama e_essential bunlara {varsayilan_w:.2f} ağırlık UYGULUYOR —")
        print(f"       yani {uydurulan_t:,.0f} TL için sessizce tahmin yürütülüyor.")

    # Ağırlığı bilinmeyen kategoriye atamak AŞIRI İDDİA DEĞİLDİR: "pazaryeri"
    # kimden alındığını söyler, ne alındığını değil. Ayrımı ölçelim.
    agirliksiz = [r for r in cekimser_beklenen
                  if tah[r.ham][0] is not None
                  and CATEGORIES[tah[r.ham][0]].essential_weight is None]
    agirlikli = [r for r in cekimser_beklenen
                 if tah[r.ham][0] is not None
                 and CATEGORIES[tah[r.ham][0]].essential_weight is not None]
    if agirliksiz:
        print(f"     · ağırlığı bilinmeyen kategoriye atandı (zararsız): "
              f"{sum(r.tutar for r in agirliksiz):,.0f} TL")
    if agirlikli:
        print(f"     ✗ ağırlığı BİLİNEN kategoriye atandı (GERÇEK aşırı iddia): "
              f"{sum(r.tutar for r in agirlikli):,.0f} TL")
        for r in agirlikli[:5]:
            print(f"         {r.ham[:40]:<42}→ {tah[r.ham][0]}")

    print("\nSINIF BAZINDA KAPSAM")
    print("-" * 74)
    print(f"  {'sınıf':<14}{'tutar':>11}{'kapsanan':>11}{'oran':>7}  ne çözmeli")
    for s in sorted(SINIFLAR, key=lambda x: -sum(
            r.tutar for r in GOLD if r.sinif == x)):
        rows = [r for r in GOLD if r.sinif == s]
        tt = sum(r.tutar for r in rows)
        kt = sum(r.tutar for r in rows if tah[r.ham][0] is not None)
        print(f"  {s:<14}{tt:>11,.0f}{kt:>11,.0f}{kt/tt*100:>6.0f}%  "
              f"{SINIFLAR[s].split('→')[-1].strip()}")

    if ayrinti and hatalar:
        print("\nYANLIŞ KATEGORİLER (essential hatasına göre)")
        print("-" * 74)
        for r, pred, d in sorted(hatalar, key=lambda x: -x[2] * x[0].tutar)[:15]:
            print(f"  Δ{d:.2f} × {r.tutar:>8,.0f} TL | {r.ham[:34]:<36}"
                  f"{pred} ≠ {r.kategori}")

    if ayrinti:
        eksik = [r for r in etiketli if tah[r.ham][0] is None]
        if eksik:
            print("\nKAÇIRILANLAR — cevabı vardı, motor bulamadı (tutarca)")
            print("-" * 74)
            for r in sorted(eksik, key=lambda x: -x.tutar)[:15]:
                print(f"  {r.tutar:>9,.0f} TL | {r.ham[:36]:<38}→ {r.kategori}"
                      f"  [{r.sinif}]")
    return 0


if __name__ == "__main__":
    sys.exit(calistir(ayrinti="--ayrinti" in sys.argv))
