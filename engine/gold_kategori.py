"""Nakitio — Kategorizasyon Altın Standart Seti

GERÇEK bir VakıfBank kredi kartı ekstresinden (13.06–13.07.2026) çıkarılmış
79 farklı işyeri metni, 107 harcama satırı. Her satır ELLE etiketlenmiştir.

NEDEN VAR
---------
Kategorizasyon `essential_weight` üzerinden `e_essential`'i, o da `ef_months`
(P3) ve `disc_share` (P4) metriklerini belirler. Ölçülmeden iyileştirilemez:
"kapsam %56'ya çıktı" demek, kuralın KENDİ KENDİNİ ölçmesidir — yanlış
kategorize ettiklerini göremez. Bu set o boşluğu kapatır.

ÖLÇÜLEN ŞEY 25 YÖNLÜ DOĞRULUK DEĞİLDİR
---------------------------------------
Skor kategoriyi yalnızca dört kanaldan görür ve en ağırı `essential_weight`.
"market"i "restoran" sanmak pahalıdır (0,85 vs 0,15); "eğlence"yi "tatil"
sanmak bedavadır (0,00 vs 0,00). Bu yüzden birincil metrik **essential_weight
uzayındaki tutarla ağırlıklı mutlak hata**dır. `eval_kategori.py` bunu ölçer.

ÇEKİMSERLİK BEKLENEN SATIRLAR
------------------------------
`kategori=None` "etiketlenemedi" demek DEĞİLDİR — "bilgi metinde yok, model
de bilememeli" demektir. Bunlara kategori atamak hata sayılır; çekimser
kalmak doğru cevaptır. Adres adı taşıyan bir işyerinin ne sattığı, o metinden
çıkarılamaz.

GİZLİLİK
--------
Bu set GERÇEK bir kişinin ekstresinden türetilmiştir ve o kişi bu deponun
sahibi DEĞİLDİR. Uygulanan önlemler:

  · tutarlar 10 TL'ye yuvarlandı
  · kart numarası, isim, adres, müşteri numarası HİÇ alınmadı
  · vergi tahsilat referans numarası maskelendi (`XXXXXXXXXX`)

İşyeri metinleri ham hâliyle gereklidir — ayrıştırıcıyı ve kuralları sınayan
şey tam olarak o metinlerin düzensizliğidir. Yine de bu dosya bir kişinin bir
dönemlik alışkanlığını gösterir; depo herkese açık hâle gelecekse veri
sahibinin onayı alınmalıdır. Bu dosya tek bir kişinin bir dönemlik alışkanlığıdır — kapsama
oranları buradan genellenmemelidir (bkz. §Kısıtlar).
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, List, Optional

from data_model import CATEGORIES, DEFAULT_CATEGORY


@dataclass(frozen=True)
class GoldRow:
    ham: str                      # ekstredeki ham açıklama
    tutar: float                  # dönem toplamı, 10 TL'ye yuvarlanmış
    adet: int                     # dönemde kaç kez göründü
    kategori: Optional[str]       # beklenen kategori · None = ÇEKİMSER kalmalı
    guven: str                    # kesin · orta · belirsiz (etiketleyenin güveni)
    sinif: str                    # yapısal sınıf — hangi katman çözmeli
    not_: str = ""                # NEDEN bu etiket


#: Yapısal sınıflar — her biri farklı bir katmanın sorumluluğu.
SINIFLAR = {
    "zincir":      "Bilinen zincir/marka → SÖZLÜK katmanı çözmeli",
    "tur_sozcugu": "Ad türü söylüyor (GIDA, ECZANE, KÖFTECİ) → KURAL katmanı",
    "pazaryeri":   "Pazaryeri/aracı → içerik bilinemez, ÇEKİMSER + triyaj",
    "kurumsal":    "Kurumsal ad, tür belirsiz → triyaj veya kullanıcı hafızası",
    "kisi":        "Kişi adına kayıtlı işletme → triyaj",
    "adres":       "Yalnız adres/şube adı → çözülemez, ÇEKİMSER",
    "islem_disi":  "Faiz/vergi/harç → harcama DEĞİL, kind ile ayrılmalı",
}

GOLD: List[GoldRow] = [
    # ── İşlem dışı: harcama kategorisi değil, kind meselesi ──────────────
    GoldRow("ALIŞVERİŞ FAİZİ (Oran:4.25)", 6690, 1, None, "kesin", "islem_disi",
            "Kart faizi. TxnKind.INTEREST olmalı; harcama kategorisi almamalı"),
    GoldRow("BSMV", 1000, 1, None, "kesin", "islem_disi",
            "Banka ve Sigorta Muameleleri Vergisi → TxnKind.FEE"),
    GoldRow("KKDF", 1000, 1, None, "kesin", "islem_disi",
            "Kaynak Kullanımını Destekleme Fonu → TxnKind.FEE"),
    GoldRow("Vergi Th/XXXXXXXXXX/ 2.Taksit", 9870, 1, "vergi", "kesin", "islem_disi",
            "Vergi tahsilatı. Referans numarası MASKELENDİ — ölçüm için "
            "işlevi yok, kimlik verisi riski var"),
    GoldRow("S/TAPU KAD. DON.SER. 2.Taksit", 2230, 1, "vergi", "kesin", "islem_disi",
            "Tapu Kadastro Döner Sermaye harcı — resmî ödeme"),

    # ── Zincirler: sözlük katmanının işi ────────────────────────────────
    GoldRow("MEDIA MARKT ISKENDER 6. Taksit", 3610, 1, "elektronik", "kesin", "zincir",
            "MediaMarkt. 20 karakterde kesilmiş ('İSKENDERUN')"),
    GoldRow("MIGROS ANKARA KUCUKE", 320, 1, "market", "kesin", "zincir",
            "Migros. 20 karakterde kesilmiş ('KÜÇÜKESAT')"),
    GoldRow("BIM O831 GORDION POL", 890, 1, "market", "kesin", "zincir",
            "BİM + mağaza kodu. Kod ortada, marka başta"),
    GoldRow("BIM T288 YENIMAHALLE", 450, 1, "market", "kesin", "zincir", "BİM"),
    GoldRow("9922 - 5650 - A101 C", 760, 1, "market", "kesin", "zincir",
            "A101 — DİKKAT: mağaza kodu ÖNDE, marka ortada. Önek eşleşmesi çalışmaz"),
    GoldRow("9946-E325-A101 TUNAL", 60, 1, "market", "kesin", "zincir", "A101"),
    GoldRow("PETROL OFİSİ A.Ş./ESKİŞEHİR", 380, 2, "ulasim", "kesin", "zincir",
            "Akaryakıt. Aksanlı 'OFİSİ' — ASCII katlama şart"),
    GoldRow("MİRAP POLATLI OPET/ANKARA", 1500, 1, "ulasim", "kesin", "zincir", "OPET bayi"),
    GoldRow("OPET EMEK TİCARET/ANKARA", 1500, 1, "ulasim", "kesin", "zincir", "OPET bayi"),
    GoldRow("OPET BOLU DAGI GUNEY", 1470, 2, "ulasim", "kesin", "zincir", "OPET"),
    GoldRow("BAŞKENT OPET/ESKİŞEHİR", 190, 1, "ulasim", "kesin", "zincir", "OPET bayi"),
    GoldRow("WATSONS KARASU", 1590, 1, "kisisel", "kesin", "zincir", "Watsons kişisel bakım"),
    GoldRow("PENTI-ANKA TUNALI HI", 1500, 1, "giyim", "kesin", "zincir",
            "Penti çorap/iç giyim. 20 karakterde kesilmiş"),
    GoldRow("SBUX ESK BASKENT MOL", 640, 1, "restoran", "kesin", "zincir",
            "SBUX = Starbucks kısaltması. Sözlükte kısaltma da bulunmalı"),
    GoldRow("MRDIY ÇANKAYA BARBAR", 800, 1, "ev", "kesin", "zincir", "Mr DIY ev/hırdavat"),
    GoldRow("TCDD Taşımacılık A.Ş", 230, 1, "ulasim", "kesin", "zincir",
            "Devlet demiryolları. 20 karakterde kesilmiş"),
    GoldRow("S/HOP SCOOTER/ANKARA", 670, 12, "ulasim", "kesin", "zincir",
            "HOP scooter paylaşımı. 12 kez — 'S/' öneki muhtemelen sanal POS"),
    GoldRow("GOOGLE *Google One/LONDON", 50, 1, "abonelik", "kesin", "zincir",
            "Google One aboneliği. 'GOOGLE *' küresel kart kuralı; /LONDON yurtdışı"),
    GoldRow("Google Workspace_nakit/Dublin", 10, 1, "abonelik", "orta", "zincir",
            "Google Workspace. Kurumsal araç olabilir ama abonelik yapısı aynı"),
    GoldRow("IYZICO/AmazonPrimeTR", 70, 1, "abonelik", "kesin", "zincir",
            "Amazon Prime aboneliği — aracı soyulunca marka görünür"),

    # ── Tür sözcüğü: kural katmanının işi ───────────────────────────────
    GoldRow("MELISA MOBILYA 9. Taksit", 7220, 1, "ev", "kesin", "tur_sozcugu", "MOBİLYA"),
    GoldRow("FLORYA YEMEK TICARET ANON/ANKARA", 4700, 1, "restoran", "orta", "tur_sozcugu",
            "'YEMEK' + 'TİCARET ANONİM' (kesik). Toplu yemek firması olabilir"),
    GoldRow("BAKLAVACI KARDEŞLER/ESKİŞEHİR", 3250, 1, "restoran", "kesin", "tur_sozcugu",
            "BAKLAVACI — Türkçe meslek eki '-cı' güçlü sinyal"),
    GoldRow("BUYUKKAYALAR MARKET/ANKARA", 2520, 1, "market", "kesin", "tur_sozcugu", "MARKET"),
    GoldRow("BAŞKENTLİLER AKARYAKIT/ESKİŞEHİR", 2250, 1, "ulasim", "kesin", "tur_sozcugu",
            "AKARYAKIT"),
    GoldRow("MIRAP AKARYAKIT A.S 002/ANKARA", 1500, 1, "ulasim", "kesin", "tur_sozcugu",
            "AKARYAKIT + 'A.S' unvanı + bayi kodu"),
    GoldRow("METIN GIDA LTD.STI.", 1940, 2, "market", "kesin", "tur_sozcugu",
            "GIDA + 'LTD.ŞTİ.' unvan gürültüsü"),
    GoldRow("ÜSTÜNLER GIDA ZAFER/ANKARA", 1450, 1, "market", "kesin", "tur_sozcugu", "GIDA"),
    GoldRow("ELİZİN GIDA TUNALI/ANKARA", 1080, 2, "market", "kesin", "tur_sozcugu", "GIDA"),
    GoldRow("HEPİYİ SİGORTA ANONİ 3. Taksit", 1900, 1, "sigorta", "kesin", "tur_sozcugu",
            "SİGORTA. 'ANONİ' 20 karakterde kesilmiş"),
    GoldRow("TUĞBA KURUYEMİŞ/ANKARA", 1810, 2, "market", "kesin", "tur_sozcugu",
            "KURUYEMİŞ zinciri"),
    GoldRow("TUNALI KOFTECISI/ANKARA", 1400, 2, "restoran", "kesin", "tur_sozcugu",
            "KÖFTECİ — meslek eki"),
    GoldRow("YENİ BAHAR ECZANESİ", 1300, 3, "saglik", "kesin", "tur_sozcugu",
            "ECZANE + '-si' iyelik eki → kök eşleştirme gerek"),
    GoldRow("BİLİR ECZANESİ/ANKARA", 800, 1, "saglik", "kesin", "tur_sozcugu", "ECZANE"),
    GoldRow("POLATLI TUGBA ECZANESI/ANKARA", 460, 1, "saglik", "kesin", "tur_sozcugu", "ECZANE"),
    GoldRow("MEŞHUR KONYALILAR ET", 1120, 1, "restoran", "orta", "tur_sozcugu",
            "20 karakterde kesik. 'ET' muhtemelen 'ET LOKANTASI' — kasap da olabilir"),
    GoldRow("TUNALI GIYIM IMALAT", 1100, 1, "giyim", "kesin", "tur_sozcugu", "GİYİM"),
    GoldRow("TANINMIS HELVACI/ESKISEHIR", 960, 1, "restoran", "orta", "tur_sozcugu",
            "HELVACI — tatlıcı. Market de sayılabilir; essential 0,15 vs 0,85 farkı önemli"),
    GoldRow("TRABZONLULAR ZÜCCACİYE/ESKİŞEHİR", 530, 1, "ev", "kesin", "tur_sozcugu",
            "ZÜCCACİYE = ev eşyası"),
    GoldRow("LEVENT BÖREK", 500, 1, "restoran", "kesin", "tur_sozcugu", "BÖREK"),
    GoldRow("MADRİD CAFE/ANKARA", 470, 1, "restoran", "kesin", "tur_sozcugu", "CAFE"),
    GoldRow("BİRLİK SANDVİÇ/ANKARA", 360, 1, "restoran", "kesin", "tur_sozcugu", "SANDVİÇ"),
    GoldRow("ŞAHİN PETROL/ANKARA", 330, 1, "ulasim", "kesin", "tur_sozcugu",
            "PETROL — DİKKAT: 'PETROL OFİSİ' zinciriyle karışmamalı, ikisi de ulaşım"),
    GoldRow("ESA UNLU MAMÜLLERİ/ANKARA", 330, 1, "market", "orta", "tur_sozcugu",
            "UNLU MAMÜLLER = fırın. Ekmek temel gıda → market (0,85). Pastane olsa restoran"),
    GoldRow("ÇAĞDAŞ MARKET TUNALI-2 ŞB/ANKARA", 230, 1, "market", "kesin", "tur_sozcugu",
            "MARKET + 'ŞB' şube kısaltması"),
    GoldRow("ŞEKERCİLER BÜLBÜLDER", 170, 1, "restoran", "orta", "tur_sozcugu",
            "ŞEKERCİ. Hediye de olabilir; ikisi de düşük essential"),
    GoldRow("COFFEBUS/ANKARA", 420, 1, "restoran", "orta", "tur_sozcugu",
            "COFFEE varyantı — 'COFFEBUS' tek B ile yazılmış, esnek eşleşme gerek"),
    GoldRow("KOCZER OTOMAT/ISTANBUL", 40, 1, "restoran", "belirsiz", "tur_sozcugu",
            "OTOMAT = satış makinesi. İçecek/atıştırmalık varsayımı"),

    # ── Pazaryeri: İŞYERİ bilinir, İÇERİK bilinmez ──────────────────────
    # Beklenen cevap `pazaryeri` kategorisidir — çekimserlik DEĞİL.
    # Ayrım ince ama önemli: kategori KİMDEN alındığını söyler; ne
    # alındığını `essential_weight=None` ile bilmediğimizi ilan ederiz.
    # Yani "Trendyol'dan alışveriş" bilgisi gerçektir ve gösterilmelidir;
    # uydurulmayan şey o alışverişin zorunluluk derecesidir.
    GoldRow("IYZICO/AMAZON.COM.TR", 6430, 3, "pazaryeri", "kesin", "pazaryeri",
            "Amazon: giyim de olabilir elektronik de. Metinde cevap yok → triyaj"),
    GoldRow("IYZICO/AMAZON.COM.TR 2. Taksit", 3810, 3, "pazaryeri", "kesin", "pazaryeri", "Amazon"),
    GoldRow("IYZICO/AMAZON.COM.TR 3. Taksit", 2020, 2, "pazaryeri", "kesin", "pazaryeri", "Amazon"),
    GoldRow("İyzico/amazon.com.tr 3. Taksit", 860, 1, "pazaryeri", "kesin", "pazaryeri",
            "Amazon — küçük harf varyantı, katlama gerek"),
    GoldRow("TRENDYOL.COM", 3590, 1, "pazaryeri", "kesin", "pazaryeri", "Trendyol pazaryeri"),
    GoldRow("HEPSIPAY /HEPSIBU 3. Taksit", 1760, 1, "pazaryeri", "kesin", "pazaryeri",
            "Hepsiburada, 20 karakterde kesik"),
    GoldRow("HEPSIPAY /HEPSIBU 6. Taksit", 1690, 1, "pazaryeri", "kesin", "pazaryeri", "Hepsiburada"),
    GoldRow("HEPSIPAY /HEPSIBU", 70, 1, "pazaryeri", "kesin", "pazaryeri", "Hepsiburada"),

    # ── Kurumsal ad: tür belirsiz, triyaj/kullanıcı hafızası ────────────
    GoldRow("Bizigo-Milplus 4. Taksit", 12040, 1, "tatil", "orta", "kurumsal",
            "Bizigo = uçak bileti/seyahat. 'Milplus' mil programı. Sözlüğe girmeli"),
    GoldRow("HANTECH 2. Taksit", 6700, 1, None, "belirsiz", "kurumsal",
            "Kurumsal ad, tür yok. Elektronik olabilir ama METİNDE KANIT YOK"),
    GoldRow("ARASLAR GLOBAL/ANKARA", 4200, 1, None, "belirsiz", "kurumsal",
            "'GLOBAL' tür bildirmez. Çekimser doğru cevap"),
    GoldRow("BUYUKKAYALAR/ANKARA", 2080, 1, "market", "orta", "kurumsal",
            "'BUYUKKAYALAR MARKET' ile AYNI işyeri, 'MARKET' eki düşmüş. "
            "Kullanıcı hafızası aynı merchant_id'ye bağlamalı"),
    GoldRow("AYYILDIZ/ESKİŞEHİR", 1350, 3, None, "belirsiz", "kurumsal",
            "Tür yok, 3 kez görülmüş — triyaj için iyi aday"),
    GoldRow("ZUHAL TİCARET/ANKARA", 1580, 1, None, "belirsiz", "kurumsal",
            "'TİCARET' tür bildirmez. Zuhal Müzik olabilir ama kanıt yok"),
    GoldRow("DETSAN KİMYA SANAYİ VE Tİ/ESKİŞEHİR", 870, 1, None, "belirsiz", "kurumsal",
            "'KİMYA SANAYİ' — B2B görünüyor, tüketici kategorisi belirsiz"),
    GoldRow("EVE-1279 TUNALI HILM", 610, 1, None, "belirsiz", "kurumsal",
            "'EVE' mağaza kodu mu marka mı belli değil, 20 karakterde kesik"),
    GoldRow("EMEK TİCARET/ANKARA", 220, 1, None, "belirsiz", "kurumsal",
            "'TİCARET' tür bildirmez"),
    GoldRow("MERKEZ ŞUBE", 60, 1, None, "belirsiz", "kurumsal",
            "Banka şubesi — ücret mi nakit çekim mi belirsiz"),

    # ── Kişi adı: triyaj ────────────────────────────────────────────────
    GoldRow("RECEP USTA/ANKARA", 2300, 1, "restoran", "orta", "kisi",
            "'USTA' Türkçe'de sıklıkla lokanta/kebapçı adı — ama garanti değil"),
    GoldRow("GUVEN CADIR/ANKARA", 1600, 2, None, "belirsiz", "kisi",
            "'ÇADIR' soyadı mı ürün mü? Kamp malzemesi de olabilir"),
    GoldRow("CANAN KAPTAN/ANKARA 2.Taksit", 740, 1, None, "belirsiz", "kisi",
            "Kişi adı. Taksitli olması ciddi bir alım olduğunu gösterir, türünü değil"),
    GoldRow("ADEM SÖNMEZ/ANKARA", 500, 1, None, "belirsiz", "kisi", "Kişi adı"),
    GoldRow("MENEKŞE AYDINOĞLU/ESKİŞEHİR", 130, 1, None, "belirsiz", "kisi", "Kişi adı"),

    # ── Adres/şube: çözülemez ───────────────────────────────────────────
    GoldRow("ANKARA POLATLI TURAN CAD./ANKARA", 2200, 2, None, "kesin", "adres",
            "İşyeri adı yerine CADDE adı yazılmış. Ne sattığı metinde yok"),
    GoldRow("BESTEKAR SOKAK ANKAR", 500, 1, None, "kesin", "adres",
            "Sokak adı, 20 karakterde kesik"),
    GoldRow("POLATLI ZAFER SOK", 210, 1, None, "kesin", "adres", "Sokak adı"),
]


def essential_of(kategori: Optional[str]) -> Optional[float]:
    """Beklenen kategorinin zorunluluk ağırlığı. None → ölçüme girmez."""
    if kategori is None:
        return None
    return CATEGORIES[kategori].essential_weight


def ozet() -> Dict[str, Dict[str, float]]:
    """Sınıf bazında satır ve tutar dağılımı."""
    out: Dict[str, Dict[str, float]] = {}
    for r in GOLD:
        d = out.setdefault(r.sinif, {"kayit": 0, "satir": 0, "tutar": 0.0,
                                     "cekimser": 0})
        d["kayit"] += 1
        d["satir"] += r.adet
        d["tutar"] += r.tutar
        d["cekimser"] += 1 if r.kategori is None else 0
    return out


def dogrula() -> List[str]:
    """Set kendi içinde tutarlı mı — kategori adları gerçek mi vb."""
    hata = []
    for r in GOLD:
        if r.kategori is not None and r.kategori not in CATEGORIES:
            hata.append(f"{r.ham!r}: '{r.kategori}' CATEGORIES'te yok")
        if r.guven not in ("kesin", "orta", "belirsiz"):
            hata.append(f"{r.ham!r}: geçersiz güven '{r.guven}'")
        if r.sinif not in SINIFLAR:
            hata.append(f"{r.ham!r}: geçersiz sınıf '{r.sinif}'")
        if not r.not_:
            hata.append(f"{r.ham!r}: gerekçe yazılmamış")
    hams = [r.ham for r in GOLD]
    for h in set(hams):
        if hams.count(h) > 1:
            hata.append(f"{h!r}: tekrar eden kayıt")
    return hata


if __name__ == "__main__":
    import sys as _s
    hata = dogrula()
    print("NAKİTİO — KATEGORİZASYON ALTIN STANDART SETİ")
    print("=" * 72)
    top_t = sum(r.tutar for r in GOLD)
    top_s = sum(r.adet for r in GOLD)
    print(f"{len(GOLD)} farklı işyeri metni · {top_s} harcama satırı · "
          f"{top_t:,.0f} TL\n")
    print(f"{'sınıf':<14}{'kayıt':>7}{'satır':>7}{'tutar':>12}{'pay':>7}"
          f"{'çekimser':>10}")
    print("-" * 72)
    for s, d in sorted(ozet().items(), key=lambda x: -x[1]["tutar"]):
        print(f"{s:<14}{d['kayit']:>7}{d['satir']:>7}{d['tutar']:>12,.0f}"
              f"{d['tutar']/top_t*100:>6.0f}%{d['cekimser']:>10}")
    print("-" * 72)
    ce = [r for r in GOLD if r.kategori is None]
    print(f"\nÇEKİMSER beklenen : {len(ce)} kayıt · "
          f"{sum(r.tutar for r in ce):,.0f} TL "
          f"(%{sum(r.tutar for r in ce)/top_t*100:.0f})")
    for g in ("kesin", "orta", "belirsiz"):
        n = [r for r in GOLD if r.guven == g]
        print(f"etiket güveni {g:<9}: {len(n):>2} kayıt · "
              f"{sum(r.tutar for r in n):>9,.0f} TL")
    if hata:
        print(f"\n✗ {len(hata)} tutarsızlık:")
        for h in hata:
            print(f"   {h}")
        _s.exit(1)
    print("\n✓ Set tutarlı.")
