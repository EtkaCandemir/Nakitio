"""Nakitio — Zincir/Marka Sözlüğü

Türkiye'de yaygın işyeri zincirlerinin tanınması. İKİ İŞ birden yapar:

  1. KATEGORİ   — "A101" → market
  2. KİMLİK     — "9922 - 5650 - A101 C" ve "9946-E325-A101 TUNAL" aynı
                  `merchant_id`'ye ("a101") düşer

İkincisi en az birincisi kadar önemli. `merchant_id` şunların temelidir:
yinelenen ödeme tespiti (N4), iade eşleştirme (N7) ve kullanıcı
düzeltmelerinin kalıcılığı. Marka tanınmazsa mağaza kodu anahtara sızar
ve aynı zincirin iki şubesi iki ayrı işyeri sanılır.

NEDEN SÖZLÜK, NEDEN BU BÜYÜKLÜKTE
----------------------------------
Gerçek bir kart ekstresinde ölçüldü: işyeri metinleri Zipf dağılır —
ilk 10 işyeri harcamanın %52'sini, ilk 30'u %82'sini kapsıyordu. Yani
50.000 kayıtlık bir sözlük gerekmiyor; BAŞI iyi kapsayan bir sözlük
gerekiyor. Kuyruk (mahalle marketi, yerel lokanta) sözlükle değil
`normalize.MERCHANT_RULES`'daki Türkçe TÜR SÖZCÜKLERİYLE ve kullanıcı
düzeltmesiyle çözülür — tek şubeli bir işletmeyi ezberlemek değersizdir.

DESENLER ASCII BÜYÜK HARFTİR
-----------------------------
Eşleştirme `normalize._rule_blob`'un ürettiği metne yapılır: aksanlar
düşürülmüş, `ı/İ → i/I`, tamamı büyük harf. Yani "İGDAŞ" burada `IGDAS`
diye yazılır. Aksanlı yazmak sessizce eşleşmemeye yol açar.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import List, Optional, Tuple


@dataclass(frozen=True)
class Marka:
    anahtar: str      # kanonik merchant_id — kısa, sabit, asla değişmez
    ad: str           # kullanıcıya gösterilecek ad
    desen: str        # ASCII büyük harf regex
    kategori: str     # varsayılan kategori


#: Sıra önemlidir — ilk eşleşen kazanır. Daha ÖZEL olan üste yazılır:
#: "TRENDYOL YEMEK" restorandır, "TRENDYOL" pazaryeridir.
MARKALAR: List[Marka] = [
    # ── Abonelik (pazaryerinden ÖNCE: "Amazon Prime" ≠ Amazon alışverişi) ──
    Marka("netflix", "Netflix", r"NETFLIX", "abonelik"),
    Marka("spotify", "Spotify", r"SPOTIFY", "abonelik"),
    Marka("youtube", "YouTube Premium", r"YOUTUBE", "abonelik"),
    Marka("disney", "Disney+", r"DISNEY", "abonelik"),
    Marka("blutv", "BluTV", r"BLUTV", "abonelik"),
    Marka("exxen", "Exxen", r"EXXEN", "abonelik"),
    Marka("gain", "Gain", r"\bGAIN\b", "abonelik"),
    Marka("amazon_prime", "Amazon Prime", r"AMAZON ?PRIME", "abonelik"),
    Marka("apple_svc", "Apple Servisleri", r"ICLOUD|APPLE ?(MUSIC|TV|ONE|COM/BILL)",
          "abonelik"),
    Marka("google_svc", "Google Servisleri",
          r"GOOGLE ?(ONE|WORKSPACE|STORAGE|CLOUD)", "abonelik"),
    Marka("microsoft", "Microsoft", r"MICROSOFT ?365|OFFICE ?365|\bMSFT\b", "abonelik"),
    Marka("adobe", "Adobe", r"\bADOBE\b", "abonelik"),
    Marka("dropbox", "Dropbox", r"DROPBOX", "abonelik"),
    Marka("linkedin", "LinkedIn", r"LINKEDIN", "abonelik"),

    # ── Yemek teslimatı (pazaryerinden ÖNCE) ────────────────────────────
    Marka("yemeksepeti", "Yemeksepeti", r"YEMEKSEPETI", "restoran"),
    Marka("getir_yemek", "Getir Yemek", r"GETIR ?YEMEK", "restoran"),
    Marka("trendyol_yemek", "Trendyol Yemek", r"TRENDYOL ?YEMEK", "restoran"),
    Marka("tikla_gelsin", "Tıkla Gelsin", r"TIKLA ?GELSIN", "restoran"),
    Marka("migros_yemek", "Migros Yemek", r"MIGROS ?YEMEK", "restoran"),

    # ── Pazaryeri — ne alındığı BİLİNMEZ ────────────────────────────────
    Marka("trendyol", "Trendyol", r"TRENDYOL", "pazaryeri"),
    Marka("hepsiburada", "Hepsiburada", r"HEPSIBURADA|HEPSIBU|HEPSIPAY", "pazaryeri"),
    Marka("amazon", "Amazon", r"AMAZON", "pazaryeri"),
    Marka("n11", "n11", r"\bN11\b", "pazaryeri"),
    Marka("gittigidiyor", "GittiGidiyor", r"GITTIGIDIYOR", "pazaryeri"),
    Marka("ciceksepeti", "Çiçeksepeti", r"CICEKSEPETI", "pazaryeri"),
    Marka("pttavm", "PttAVM", r"PTTAVM", "pazaryeri"),
    Marka("morhipo", "Morhipo", r"MORHIPO", "pazaryeri"),
    Marka("modanisa", "Modanisa", r"MODANISA", "pazaryeri"),
    # "DOLAP" Türkçe'de mobilya parçasıdır; çıplak eşleşme bir mobilyacıyı
    # pazaryeri sanır. Alan adı bağlamı zorunlu.
    Marka("dolap", "Dolap", r"DOLAP\.COM|\bDOLAP ?APP\b", "pazaryeri"),

    # ── Market ──────────────────────────────────────────────────────────
    Marka("a101", "A101", r"\bA ?101\b", "market"),
    Marka("bim", "BİM", r"\bBIM\b", "market"),
    # DİKKAT: çıplak "SOK" YASAK. ASCII katlamada "ŞOK" → "SOK" olur ama
    # "SOK" aynı zamanda SOKAK kısaltmasıdır: "POLATLI ZAFER SOK" bir
    # adrestir, market değil. Gerçek ekstrede bu hata ölçümle yakalandı.
    # Bu yüzden "MARKET" bağlamı zorunlu.
    Marka("sok", "ŞOK", r"\bSOK ?MARKET|\bSOK ?MAGAZA", "market"),
    Marka("migros", "Migros", r"MIGROS", "market"),
    Marka("carrefour", "CarrefourSA", r"CARREFOUR", "market"),
    Marka("macrocenter", "Macrocenter", r"MACROCENTER", "market"),
    Marka("file", "File Market", r"\bFILE ?MARKET\b", "market"),
    Marka("hakmar", "Hakmar", r"HAKMAR", "market"),
    Marka("tarim_kredi", "Tarım Kredi", r"TARIM ?KREDI", "market"),
    Marka("bizim_toptan", "Bizim Toptan", r"BIZIM ?TOPTAN", "market"),
    Marka("metro_toptan", "Metro Toptancı", r"METRO ?(GROSSMARKET|TOPTAN)", "market"),
    Marka("getir", "Getir", r"\bGETIR\b", "market"),
    Marka("istegelsin", "İstegelsin", r"ISTEGELSIN", "market"),
    Marka("tugba", "Tuğba Kuruyemiş", r"TUGBA ?KURUYEMIS", "market"),

    # ── Akaryakıt / ulaşım ──────────────────────────────────────────────
    Marka("shell", "Shell", r"\bSHELL\b", "ulasim"),
    Marka("opet", "Opet", r"\bOPET\b", "ulasim"),
    Marka("po", "Petrol Ofisi", r"PETROL ?OFISI|\bPO\b(?= ?AKARYAKIT)", "ulasim"),
    Marka("bp", "BP", r"\bBP\b", "ulasim"),
    Marka("total", "TotalEnergies", r"\bTOTAL\b(?! ?TUTAR)", "ulasim"),
    Marka("lukoil", "Lukoil", r"LUKOIL", "ulasim"),
    Marka("aytemiz", "Aytemiz", r"AYTEMIZ", "ulasim"),
    Marka("alpet", "Alpet", r"\bALPET\b", "ulasim"),
    Marka("tp", "Türkiye Petrolleri", r"TURKIYE ?PETROL", "ulasim"),
    Marka("moil", "Moil", r"\bMOIL\b", "ulasim"),
    Marka("istanbulkart", "İstanbulkart", r"ISTANBULKART|\bIETT\b", "ulasim"),
    Marka("metro_ist", "Metro İstanbul", r"METRO ?ISTANBUL|MARMARAY", "ulasim"),
    Marka("ankarakart", "Ankarakart", r"ANKARAKART|\bEGO\b", "ulasim"),
    Marka("bitaksi", "BiTaksi", r"BITAKSI", "ulasim"),
    Marka("uber", "Uber", r"\bUBER\b", "ulasim"),
    Marka("marti", "Martı", r"\bMARTI\b", "ulasim"),
    Marka("hop", "HOP Scooter", r"HOP ?SCOOTER", "ulasim"),
    Marka("tcdd", "TCDD", r"\bTCDD\b", "ulasim"),

    # ── Restoran / kafe ─────────────────────────────────────────────────
    Marka("starbucks", "Starbucks", r"STARBUCKS|\bSBUX\b", "restoran"),
    Marka("kahve_dunyasi", "Kahve Dünyası", r"KAHVE ?DUNYASI", "restoran"),
    Marka("gloria", "Gloria Jean's", r"GLORIA ?JEAN", "restoran"),
    Marka("espressolab", "Espressolab", r"ESPRESSOLAB", "restoran"),
    Marka("caribou", "Caribou", r"CARIBOU", "restoran"),
    Marka("burger_king", "Burger King", r"BURGER ?KING|\bBK\b(?= ?RESTORAN)", "restoran"),
    Marka("mcdonalds", "McDonald's", r"MCDONALD|\bMCD\b", "restoran"),
    Marka("dominos", "Domino's", r"DOMINO", "restoran"),
    Marka("popeyes", "Popeyes", r"POPEYES", "restoran"),
    Marka("little_caesars", "Little Caesars", r"LITTLE ?CAESAR", "restoran"),
    Marka("tavuk_dunyasi", "Tavuk Dünyası", r"TAVUK ?DUNYASI", "restoran"),
    Marka("baydoner", "Baydöner", r"BAYDONER", "restoran"),
    Marka("kofteci_yusuf", "Köfteci Yusuf", r"KOFTECI ?YUSUF", "restoran"),
    Marka("simit_sarayi", "Simit Sarayı", r"SIMIT ?SARAYI", "restoran"),
    Marka("mado", "Mado", r"\bMADO\b", "restoran"),

    # ── Giyim / ayakkabı ────────────────────────────────────────────────
    Marka("lcw", "LC Waikiki", r"LC ?WAIKIKI|\bLCW\b", "giyim"),
    Marka("defacto", "DeFacto", r"DEFACTO", "giyim"),
    Marka("koton", "Koton", r"\bKOTON\b", "giyim"),
    Marka("mavi", "Mavi", r"\bMAVI ?(JEANS|GIYIM)\b", "giyim"),
    Marka("zara", "Zara", r"\bZARA\b", "giyim"),
    Marka("hm", "H&M", r"H ?& ?M\b|\bHM ?GIYIM", "giyim"),
    Marka("bershka", "Bershka", r"BERSHKA", "giyim"),
    Marka("pullbear", "Pull&Bear", r"PULL ?& ?BEAR", "giyim"),
    Marka("stradivarius", "Stradivarius", r"STRADIVARIUS", "giyim"),
    Marka("boyner", "Boyner", r"BOYNER", "giyim"),
    Marka("network", "Network", r"\bNETWORK ?(GIYIM|MAGAZA)", "giyim"),
    Marka("kigili", "Kiğılı", r"KIGILI", "giyim"),
    Marka("damat", "Damat Tween", r"DAMAT ?TWEEN", "giyim"),
    Marka("penti", "Penti", r"\bPENTI\b", "giyim"),
    Marka("suwen", "Suwen", r"SUWEN", "giyim"),
    Marka("colins", "Colin's", r"COLIN", "giyim"),
    Marka("flo", "FLO", r"\bFLO\b(?! ?RYA)", "giyim"),
    Marka("deichmann", "Deichmann", r"DEICHMANN", "giyim"),
    Marka("hotic", "Hotiç", r"\bHOTIC\b", "giyim"),
    Marka("vakko", "Vakko", r"\bVAKKO\b", "giyim"),
    Marka("beymen", "Beymen", r"BEYMEN", "giyim"),

    # ── Elektronik ──────────────────────────────────────────────────────
    Marka("teknosa", "Teknosa", r"TEKNOSA", "elektronik"),
    Marka("mediamarkt", "MediaMarkt", r"MEDIA ?MARKT", "elektronik"),
    Marka("vatan", "Vatan Bilgisayar", r"VATAN ?(BILGISAYAR|COMPUTER)", "elektronik"),
    Marka("apple_store", "Apple Store", r"APPLE ?STORE", "elektronik"),
    Marka("samsung", "Samsung", r"SAMSUNG", "elektronik"),
    Marka("arcelik", "Arçelik", r"ARCELIK", "elektronik"),
    Marka("vestel", "Vestel", r"VESTEL", "elektronik"),
    Marka("beko", "Beko", r"\bBEKO\b", "elektronik"),
    Marka("casper", "Casper", r"\bCASPER\b", "elektronik"),

    # ── Kişisel bakım ───────────────────────────────────────────────────
    Marka("watsons", "Watsons", r"WATSONS", "kisisel"),
    Marka("gratis", "Gratis", r"\bGRATIS\b", "kisisel"),
    Marka("rossmann", "Rossmann", r"ROSSMANN", "kisisel"),
    Marka("sephora", "Sephora", r"SEPHORA", "kisisel"),
    Marka("flormar", "Flormar", r"FLORMAR", "kisisel"),

    # ── Ev / yaşam ──────────────────────────────────────────────────────
    Marka("ikea", "IKEA", r"\bIKEA\b", "ev"),
    Marka("koctas", "Koçtaş", r"KOCTAS", "ev"),
    Marka("bauhaus", "Bauhaus", r"BAUHAUS", "ev"),
    Marka("tekzen", "Tekzen", r"TEKZEN", "ev"),
    Marka("english_home", "English Home", r"ENGLISH ?HOME", "ev"),
    Marka("madame_coco", "Madame Coco", r"MADAME ?COCO", "ev"),
    Marka("karaca", "Karaca", r"\bKARACA\b", "ev"),
    Marka("pasabahce", "Paşabahçe", r"PASABAHCE", "ev"),
    Marka("mrdiy", "Mr DIY", r"\bMR ?DIY\b|\bMRDIY\b", "ev"),

    # ── Sağlık ──────────────────────────────────────────────────────────
    Marka("acibadem", "Acıbadem", r"ACIBADEM", "saglik"),
    Marka("medicalpark", "Medical Park", r"MEDICAL ?PARK", "saglik"),
    Marka("memorial", "Memorial", r"MEMORIAL", "saglik"),
    Marka("medicana", "Medicana", r"MEDICANA", "saglik"),

    # ── İletişim ────────────────────────────────────────────────────────
    Marka("turkcell", "Turkcell", r"TURKCELL", "iletisim"),
    Marka("vodafone", "Vodafone", r"VODAFONE", "iletisim"),
    Marka("turk_telekom", "Türk Telekom", r"TURK ?TELEKOM|\bTTNET\b", "iletisim"),
    Marka("superonline", "Superonline", r"SUPERONLINE", "iletisim"),

    # ── Faturalar ───────────────────────────────────────────────────────
    Marka("igdas", "İGDAŞ", r"\bIGDAS\b", "faturalar"),
    Marka("bedas", "BEDAŞ", r"\bBEDAS\b", "faturalar"),
    Marka("iski", "İSKİ", r"\bISKI\b", "faturalar"),
    # "ASKI" Türkçe'de giysi askısıdır; su idaresi bağlamı zorunlu.
    Marka("aski", "ASKİ", r"\bASKI ?(GENEL|SU|IDARE)|ASKI ?MUD", "faturalar"),
    Marka("enerjisa", "Enerjisa", r"ENERJISA", "faturalar"),
    Marka("ayedas", "AYEDAŞ", r"AYEDAS", "faturalar"),
    Marka("baskent_gaz", "Başkentgaz", r"BASKENT ?(GAZ|EDAS)", "faturalar"),

    # ── Eğlence / spor ──────────────────────────────────────────────────
    Marka("cinemaximum", "Cinemaximum", r"CINEMAXIMUM|CINEVERSE", "eglence"),
    Marka("biletix", "Biletix", r"BILETIX", "eglence"),
    Marka("passo", "Passo", r"\bPASSO\b", "eglence"),
    Marka("steam", "Steam", r"\bSTEAM\b", "eglence"),
    Marka("playstation", "PlayStation", r"PLAYSTATION|\bPSN\b", "eglence"),
    Marka("xbox", "Xbox", r"\bXBOX\b", "eglence"),
    Marka("macfit", "MACFit", r"MAC ?FIT|MACFIT", "spor"),
    Marka("sports_intl", "Sports International", r"SPORTS ?INTERNATIONAL", "spor"),
    Marka("decathlon", "Decathlon", r"DECATHLON", "spor"),

    # ── Tatil / seyahat ─────────────────────────────────────────────────
    Marka("thy", "Türk Hava Yolları", r"\bTHY\b|TURKISH ?AIRLINES", "tatil"),
    Marka("pegasus", "Pegasus", r"PEGASUS", "tatil"),
    Marka("ajet", "AJet", r"\bAJET\b", "tatil"),
    Marka("sunexpress", "SunExpress", r"SUNEXPRESS", "tatil"),
    Marka("booking", "Booking.com", r"BOOKING", "tatil"),
    Marka("airbnb", "Airbnb", r"AIRBNB", "tatil"),
    Marka("enuygun", "Enuygun", r"ENUYGUN", "tatil"),
    Marka("obilet", "Obilet", r"OBILET", "tatil"),
    Marka("bizigo", "Bizigo", r"BIZIGO", "tatil"),
    Marka("tatilsepeti", "Tatilsepeti", r"TATILSEPETI", "tatil"),
    Marka("setur", "Setur", r"\bSETUR\b", "tatil"),
    Marka("ets", "ETS Tur", r"\bETS ?TUR\b", "tatil"),

    # ── Şans oyunları ───────────────────────────────────────────────────
    Marka("milli_piyango", "Milli Piyango", r"MILLI ?PIYANGO", "sans_oyunu"),
    Marka("iddaa", "İddaa", r"\bIDDAA\b", "sans_oyunu"),
    Marka("nesine", "Nesine", r"NESINE", "sans_oyunu"),
    Marka("bilyoner", "Bilyoner", r"BILYONER", "sans_oyunu"),
    Marka("misli", "Misli", r"\bMISLI\b", "sans_oyunu"),

    # ── Eğitim ──────────────────────────────────────────────────────────
    Marka("udemy", "Udemy", r"\bUDEMY\b", "egitim"),
    Marka("coursera", "Coursera", r"COURSERA", "egitim"),
    Marka("duolingo", "Duolingo", r"DUOLINGO", "egitim"),
]

#: Derlenmiş desenler — her çağrıda yeniden derlemek pahalıdır.
_DERLI: List[Tuple[re.Pattern, Marka]] = [
    (re.compile(m.desen), m) for m in MARKALAR
]


def bul(blob: str) -> Optional[Marka]:
    """Normalleştirilmiş metinde marka ara. İlk eşleşen kazanır."""
    for desen, m in _DERLI:
        if desen.search(blob):
            return m
    return None


def dogrula() -> List[str]:
    """Sözlük kendi içinde tutarlı mı."""
    from data_model import CATEGORIES
    hata = []
    anahtarlar = [m.anahtar for m in MARKALAR]
    for a in set(anahtarlar):
        if anahtarlar.count(a) > 1:
            hata.append(f"tekrar eden anahtar: {a}")
    for m in MARKALAR:
        if m.kategori not in CATEGORIES:
            hata.append(f"{m.anahtar}: '{m.kategori}' CATEGORIES'te yok")
        try:
            re.compile(m.desen)
        except re.error as e:
            hata.append(f"{m.anahtar}: geçersiz regex — {e}")
        # Desen ASCII büyük harf olmalı; aksanlı yazım sessizce kaçar.
        if any(c in m.desen for c in "çğıöşüÇĞİÖŞÜ"):
            hata.append(f"{m.anahtar}: desende aksanlı karakter var "
                        f"(ASCII katlanmış metne karşı eşleşmez)")
    return hata


if __name__ == "__main__":
    import sys
    from collections import Counter
    hata = dogrula()
    print("NAKİTİO — MARKA SÖZLÜĞÜ")
    print("=" * 60)
    print(f"{len(MARKALAR)} marka\n")
    for k, n in Counter(m.kategori for m in MARKALAR).most_common():
        print(f"  {k:<14} {n}")
    if hata:
        print(f"\n✗ {len(hata)} sorun:")
        for h in hata:
            print(f"   {h}")
        sys.exit(1)
    print("\n✓ Sözlük tutarlı.")
