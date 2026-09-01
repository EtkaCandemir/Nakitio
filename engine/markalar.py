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
    # "GAIN VERGİSİ" (sermaye kazancı) ile çakışıyordu.
    Marka("gain", "Gain", r"\bGAIN\b(?! ?VERGI)", "abonelik"),
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
    # "ZARA HOME" ev mağazasıdır; çıplak ZARA onu gölgeliyordu.
    Marka("zara", "Zara", r"\bZARA\b(?! ?HOME)", "giyim"),
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
    # "KARACA AHMET" (mezarlık/semt adı) ile çakışıyordu.
    Marka("karaca", "Karaca", r"\bKARACA\b(?! ?AHMET)", "ev"),
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
    # "BİR MİSLİ" (kat anlamında) ile çakışıyordu; alan adı bağlamı şart.
    Marka("misli", "Misli", r"MISLI ?\.? ?COM|\bMISLI ?BAHIS\b", "sans_oyunu"),

    # ── Market — 2. dalga ───────────────────────────────────────────────
    Marka("onur", "Onur Market", r"ONUR ?MARKET", "market"),
    Marka("ozdilek", "Özdilek", r"OZDILEK", "market"),
    Marka("happy_center", "Happy Center", r"HAPPY ?CENTER", "market"),
    Marka("begendik", "Beğendik", r"BEGENDIK", "market"),
    Marka("uyum", "Uyum Market", r"UYUM ?(MARKET|GIDA)", "market"),
    Marka("mopas", "Mopaş", r"\bMOPAS\b", "market"),
    Marka("seyhanlar", "Seyhanlar", r"SEYHANLAR", "market"),
    Marka("makro", "Makro Market", r"MAKRO ?MARKET", "market"),
    Marka("altunbilekler", "Altunbilekler", r"ALTUNBILEK", "market"),
    Marka("yunus", "Yunus Market", r"YUNUS ?MARKET", "market"),
    Marka("ekomini", "Ekomini", r"EKOMINI", "market"),
    Marka("kiler", "Kiler", r"\bKILER ?(MARKET|AVM)\b", "market"),

    # ── Akaryakıt — 2. dalga ────────────────────────────────────────────
    Marka("sunpet", "Sunpet", r"SUNPET", "ulasim"),
    Marka("kadoil", "Kadoil", r"KADOIL", "ulasim"),
    Marka("termopet", "Termo Petrol", r"TERMOPET|TERMO ?PETROL", "ulasim"),

    # ── Ulaşım — şehir kartları ve otobüs ───────────────────────────────
    Marka("kentkart", "Kentkart", r"KENTKART|IZMIRIM ?KART|BURSAKART", "ulasim"),
    Marka("kamil_koc", "Kâmil Koç", r"KAMIL ?KOC", "ulasim"),
    Marka("metro_turizm", "Metro Turizm", r"METRO ?TURIZM", "ulasim"),
    Marka("pamukkale", "Pamukkale Turizm", r"PAMUKKALE ?TURIZM", "ulasim"),
    Marka("ulusoy", "Ulusoy", r"ULUSOY ?(TURIZM|SEYAHAT)", "ulasim"),
    Marka("havaist", "HAVAIST", r"HAVAIST|HAVABUS|HAVARAY", "ulasim"),

    # ── Restoran — 2. dalga ─────────────────────────────────────────────
    Marka("kfc", "KFC", r"\bKFC\b", "restoran"),
    Marka("subway", "Subway", r"\bSUBWAY\b", "restoran"),
    Marka("pizza_hut", "Pizza Hut", r"PIZZA ?HUT", "restoran"),
    Marka("arbys", "Arby's", r"ARBY", "restoran"),
    Marka("usta_donerci", "Usta Dönerci", r"USTA ?DONERCI", "restoran"),
    Marka("komagene", "Komagene", r"KOMAGENE", "restoran"),
    Marka("oses", "Oses Çiğköfte", r"\bOSES\b", "restoran"),
    Marka("bursa_kebap", "Bursa Kebap Evi", r"BURSA ?KEBAP", "restoran"),
    Marka("hd_iskender", "HD İskender", r"HD ?ISKENDER", "restoran"),
    Marka("gunaydin", "Günaydın", r"GUNAYDIN ?(ET|RESTORAN|KASAP)", "restoran"),
    Marka("nusret", "Nusr-Et", r"NUSR ?-? ?ET\b", "restoran"),
    Marka("big_chefs", "Big Chefs", r"BIG ?CHEFS", "restoran"),
    Marka("midpoint", "Midpoint", r"MIDPOINT", "restoran"),
    Marka("kitchenette", "Kitchenette", r"KITCHENETTE", "restoran"),
    Marka("tchibo", "Tchibo", r"TCHIBO", "restoran"),
    Marka("caffe_nero", "Caffè Nero", r"CAFFE ?NERO", "restoran"),
    Marka("dunkin", "Dunkin'", r"DUNKIN", "restoran"),
    Marka("krispy", "Krispy Kreme", r"KRISPY", "restoran"),
    Marka("cinnabon", "Cinnabon", r"CINNABON", "restoran"),
    Marka("sultanahmet", "Sultanahmet Köftecisi", r"SULTANAHMET ?KOFTE", "restoran"),
    Marka("coffy", "Coffy", r"\bCOFFY\b", "restoran"),
    Marka("arabica", "%100 Arabica", r"ARABICA", "restoran"),

    # ── Giyim — 2. dalga ────────────────────────────────────────────────
    Marka("massimo", "Massimo Dutti", r"MASSIMO ?DUTTI", "giyim"),
    Marka("oysho", "Oysho", r"\bOYSHO\b", "giyim"),
    Marka("nike", "Nike", r"\bNIKE\b", "giyim"),
    Marka("adidas", "Adidas", r"ADIDAS", "giyim"),
    Marka("puma", "Puma", r"\bPUMA\b", "giyim"),
    Marka("skechers", "Skechers", r"SKECHERS", "giyim"),
    Marka("new_balance", "New Balance", r"NEW ?BALANCE", "giyim"),
    Marka("lacoste", "Lacoste", r"LACOSTE", "giyim"),
    Marka("us_polo", "U.S. Polo Assn.", r"U ?\.? ?S ?\.? ?POLO", "giyim"),
    Marka("altinyildiz", "Altınyıldız Classics", r"ALTINYILDIZ", "giyim"),
    Marka("sarar", "Sarar", r"\bSARAR\b", "giyim"),
    Marka("ramsey", "Ramsey", r"RAMSEY", "giyim"),
    Marka("ipekyol", "İpekyol", r"IPEKYOL", "giyim"),
    Marka("twist", "Twist", r"\bTWIST ?(GIYIM|MAGAZA)\b", "giyim"),
    Marka("adil_isik", "Adil Işık", r"ADIL ?ISIK", "giyim"),
    Marka("pierre_cardin", "Pierre Cardin", r"PIERRE ?CARDIN", "giyim"),
    Marka("mudo", "Mudo", r"\bMUDO\b", "giyim"),
    Marka("yargici", "Yargıcı", r"YARGICI", "giyim"),
    Marka("derimod", "Derimod", r"DERIMOD", "giyim"),
    Marka("desa", "Desa", r"\bDESA ?(DERI|MAGAZA)\b", "giyim"),
    Marka("greyder", "Greyder", r"GREYDER", "giyim"),
    Marka("lumberjack", "Lumberjack", r"LUMBERJACK", "giyim"),
    Marka("kinetix", "Kinetix", r"KINETIX", "giyim"),
    Marka("levis", "Levi's", r"LEVI ?S?\b|LEVIS ?STORE", "giyim"),

    # ── Elektronik — 2. dalga ───────────────────────────────────────────
    Marka("xiaomi", "Xiaomi", r"XIAOMI|\bMI ?STORE\b", "elektronik"),
    Marka("huawei", "Huawei", r"HUAWEI", "elektronik"),
    Marka("lg", "LG", r"\bLG ?(ELEKTRONIK|STORE|TURKIYE)\b", "elektronik"),
    Marka("philips", "Philips", r"PHILIPS", "elektronik"),
    Marka("siemens", "Siemens", r"SIEMENS", "elektronik"),
    Marka("bosch", "Bosch", r"\bBOSCH\b", "elektronik"),
    Marka("monster", "Monster Notebook", r"MONSTER ?NOTEBOOK", "elektronik"),
    Marka("itopya", "İtopya", r"ITOPYA", "elektronik"),
    Marka("incehesap", "İnce Hesap", r"INCEHESAP", "elektronik"),

    # ── Ev — 2. dalga ───────────────────────────────────────────────────
    Marka("jumbo", "Jumbo", r"\bJUMBO\b", "ev"),
    Marka("chakra", "Chakra", r"CHAKRA", "ev"),
    Marka("tepe_home", "Tepe Home", r"TEPE ?HOME", "ev"),
    Marka("dogtas", "Doğtaş", r"DOGTAS", "ev"),
    Marka("bellona", "Bellona", r"BELLONA", "ev"),
    Marka("istikbal", "İstikbal", r"ISTIKBAL ?(MOBILYA|MAGAZA)", "ev"),
    Marka("yatas", "Yataş", r"YATAS", "ev"),
    Marka("linens", "Linens", r"\bLINENS\b", "ev"),
    Marka("zara_home", "Zara Home", r"ZARA ?HOME", "ev"),
    Marka("evkur", "Evkur", r"EVKUR", "ev"),
    Marka("vivense", "Vivense", r"VIVENSE", "ev"),
    Marka("kelebek", "Kelebek Mobilya", r"KELEBEK ?MOBILYA", "ev"),

    # ── Kişisel bakım — 2. dalga ────────────────────────────────────────
    Marka("yves_rocher", "Yves Rocher", r"YVES ?ROCHER", "kisisel"),
    Marka("body_shop", "The Body Shop", r"BODY ?SHOP", "kisisel"),
    Marka("tekin_acar", "Tekin Acar", r"TEKIN ?ACAR", "kisisel"),
    Marka("atelier_rebul", "Atelier Rebul", r"ATELIER ?REBUL", "kisisel"),

    # ── Sağlık — 2. dalga ───────────────────────────────────────────────
    Marka("liv", "Liv Hospital", r"LIV ?HOSPITAL", "saglik"),
    Marka("florence", "Florence Nightingale", r"FLORENCE ?NIGHTINGALE", "saglik"),
    Marka("amerikan_hastanesi", "Amerikan Hastanesi", r"AMERIKAN ?HASTANE", "saglik"),
    Marka("dunyagoz", "Dünyagöz", r"DUNYAGOZ", "saglik"),
    Marka("anadolu_saglik", "Anadolu Sağlık", r"ANADOLU ?SAGLIK", "saglik"),

    # ── Faturalar — 2. dalga ────────────────────────────────────────────
    Marka("izsu", "İZSU", r"\bIZSU\b", "faturalar"),
    Marka("buski", "BUSKİ", r"\bBUSKI\b", "faturalar"),
    Marka("asat", "ASAT", r"\bASAT\b", "faturalar"),
    Marka("izgaz", "İzgaz", r"\bIZGAZ\b|BURSAGAZ|AKSA ?DOGALGAZ", "faturalar"),
    Marka("uludag_elektrik", "Uludağ Elektrik", r"ULUDAG ?ELEKTRIK|\bUEDAS\b", "faturalar"),
    Marka("toroslar", "Toroslar EDAŞ", r"TOROSLAR ?EDAS", "faturalar"),
    Marka("sepas", "Sepaş", r"\bSEPAS ?ENERJI\b", "faturalar"),

    # ── Eğlence / spor — 2. dalga ───────────────────────────────────────
    Marka("epic", "Epic Games", r"EPIC ?GAMES", "eglence"),
    Marka("nintendo", "Nintendo", r"NINTENDO", "eglence"),
    Marka("avsar", "Avşar Sinema", r"AVSAR ?SINEMA", "eglence"),
    Marka("prestige", "Prestige Sinema", r"PRESTIGE ?SINEMA", "eglence"),
    Marka("bfit", "B-Fit", r"\bB ?- ?FIT\b", "spor"),
    Marka("fit_center", "Fit Center", r"FIT ?CENTER", "spor"),

    # ── Tatil — 2. dalga ────────────────────────────────────────────────
    Marka("corendon", "Corendon", r"CORENDON", "tatil"),
    Marka("trivago", "Trivago", r"TRIVAGO", "tatil"),
    Marka("expedia", "Expedia", r"EXPEDIA", "tatil"),
    Marka("jolly", "Jolly Tur", r"\bJOLLY ?TUR\b", "tatil"),
    Marka("touristica", "Touristica", r"TOURISTICA", "tatil"),
    Marka("anex", "Anex Tour", r"ANEX ?TOUR", "tatil"),

    # ── Şans oyunları — 2. dalga ────────────────────────────────────────
    Marka("tuttur", "Tuttur", r"TUTTUR", "sans_oyunu"),
    Marka("birebin", "Birebin", r"BIREBIN", "sans_oyunu"),

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


#: DESEN GÜVENLİK AĞI — marka desenleri bunların HİÇBİRİNİ yakalamamalı.
#:
#: Türkçe'de kısa marka adları sıradan kelimelerle çakışır ve sonuç sessiz
#: bir hatadır: adres "market" sayılır, mobilyacı "pazaryeri" olur. Elle
#: yakalananlar: "ŞOK"→SOK (sokak kısaltması), "DOLAP" (mobilya parçası),
#: "ASKI" (giysi askısı), "ALTIN" (ALTINDAĞ ilçesi, "altındaki" kelimesi).
#:
#: Sözlük büyüdükçe bunları göz kararı yakalamak imkânsızlaşır. Bu liste
#: her yeni desende otomatik denenir — çakışan desen testi kırar.
#:
#: Metinler ASCII katlanmış ve büyük harflidir (`normalize._fold_upper`).
RISKLI_METINLER: Tuple[str, ...] = (
    # Adres bileşenleri — ekstrede işyeri adı yerine adres yazılabiliyor
    "POLATLI ZAFER SOK", "BESTEKAR SOKAK ANKARA", "ATATURK CAD NO 12",
    "CUMHURIYET MAH", "MERKEZ SUBE", "1 SANAYI SITESI", "BULVAR 34",
    "KARSIYAKA MAHALLESI", "ISTIKLAL CADDESI", "GAZI BULVARI",
    # Yer adları — marka adıyla çakışan
    "ALTINDAG BELEDIYESI", "ALTINPARK AVM", "ALTINOLUK PLAJ",
    "GOLBASI ANKARA", "ETIMESGUT SUBE", "BAHCELIEVLER MAH",
    "SULTANBEYLI", "KARTAL ISTANBUL", "MALTEPE ANKARA",
    # Sıradan Türkçe kelimeler — işyeri adında geçebilir
    "MOBILYA DOLAP DUNYASI", "ASKI VE RAF SISTEMLERI", "TOTAL TUTAR",
    "GENEL TOPLAM", "NAKIT CEKIM", "PARA TRANSFERI", "HAVALE EFT",
    "FATURA ODEME MERKEZI", "OTOMATIK ODEME TALIMATI",
    # Marka adı sıradan kelimeyle çakışanlar — en sinsi sınıf
    "MAVI DENIZ TURIZM ACENTESI",      # MAVI: renk sıfatı
    "NETWORK MARKETING EGITIMI",       # NETWORK: İngilizce kelime
    "BIR MISLI ARTIS BEDELI",          # MISLI: "kat" anlamında
    "FILE DOSYA KIRTASIYE",            # FILE: dosya
    "FLORYA YEMEK TICARET",            # FLO: FLORYA'nın içinde
    "GAIN VERGISI HESABI",             # GAIN: İngilizce kazanç
    "KARACA AHMET MEZARLIGI",          # KARACA: yer/kişi adı
    # Kurumsal unvan gürültüsü
    "SAN VE TIC LTD STI", "ANONIM SIRKETI", "KOLLEKTIF SIRKET",
    # Banka/kart işlemleri — işyeri değil
    "KREDI KARTI ODEMESI", "EKSTRE BORCU", "ASGARI ODEME",
    "ALISVERIS FAIZI", "GECIKME FAIZI", "KART AIDATI",
)


def desen_guvenligi() -> List[str]:
    """Her marka deseni riskli metinlerden HİÇBİRİNİ yakalamamalı.

    Bir desenin yanlış yakalaması sessizdir: hata vermez, sadece yanlış
    kategori üretir ve `essential_weight` üzerinden skoru kaydırır.
    Bu yüzden otomatik denenmesi şart — sözlük büyüdükçe göz kararı
    denetim imkânsızlaşır.
    """
    hata = []
    for desen, m in _DERLI:
        for metin in RISKLI_METINLER:
            if desen.search(metin):
                hata.append(f"{m.anahtar}: {m.desen!r} deseni "
                            f"{metin!r} metnini yakalıyor")
    return hata


def golgeleme_kontrolu() -> List[str]:
    """Her markanın KENDİ adı yine kendisine çözülmeli.

    Sıra önemli olduğu için genel bir desen daha özelini GÖLGELEYEBİLİR:
    "ZARA HOME" bir ev mağazasıdır ama çıplak `\\bZARA\\b` deseni listede
    önce geldiği için onu giyim sanıyordu. Elle fark edilmesi zor, çünkü
    ikisi de "çalışıyor" görünür.

    Bu kontrol markanın görünen adını normalleştirip sözlüğe geri sorar.
    Farklı bir markaya düşüyorsa gölgeleme vardır ve daha ÖZEL olan
    yukarı taşınmalı ya da genel desene bağlam koşulu eklenmelidir.
    """
    import unicodedata
    hata = []
    for m in MARKALAR:
        ad = unicodedata.normalize("NFKD", m.ad)
        ad = "".join(c for c in ad if not unicodedata.combining(c))
        ad = ad.replace("ı", "i").replace("İ", "I").upper()
        bulunan = bul(ad)
        # HİÇ eşleşmemek hata DEĞİLDİR: bazı desenler bilerek bağlam
        # ister ("SOK" yalnız "SOK MARKET" olarak, "TOTAL" yalnız
        # "TUTAR" değilse). Aranan şey ÇAPRAZ gölgeleme: markanın adının
        # BAŞKA bir markaya düşmesi.
        if bulunan is not None and bulunan.anahtar != m.anahtar:
            hata.append(f"{m.anahtar}: kendi adı ({m.ad!r}) "
                        f"{bulunan.anahtar!r} tarafından gölgeleniyor")
    return hata


def dogrula() -> List[str]:
    """Sözlük kendi içinde tutarlı mı."""
    from data_model import CATEGORIES
    hata = []
    anahtarlar = [m.anahtar for m in MARKALAR]
    for a in set(anahtarlar):
        if anahtarlar.count(a) > 1:
            hata.append(f"tekrar eden anahtar: {a}")
    hata += desen_guvenligi()
    hata += golgeleme_kontrolu()
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
