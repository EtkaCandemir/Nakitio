"""
Nakitio — Kullanıcıya Gösterilen Metinler

Arayüzde görünen her cümle burada. Kodun içine gömülü metin kalmaz.

Neden: bu metinler `Docs/skor-modeli-v2.md` §12'deki ton kurallarına
tabidir ve gözden geçirilebilir olmaları gerekir. Kodun içine dağılmış
hâldeyken ne toplu okunabilir, ne bir editör düzeltebilir, ne de
ileride başka dile çevrilebilir.

TON KURALLARI (ihlali blocker'dır):
  · Skor bir ALAN hakkında konuşur, kullanıcı hakkında değil.
  · "kötü", "başarısız", "yetersiz", "savruk", "disiplinsiz" YASAK.
  · Düşük skor daima somut bir sonraki adımla birlikte verilir.
  · Belirsizlik gizlenmez, açıkça söylenir.
  · Kategori artışı enflasyondan arındırılmadan bildirilmez.
"""

from __future__ import annotations

from typing import Dict

METIN_VERSION = "1.0.0"


# ─────────────────────────────────────────────────────────────────────────────
# Gün 0 — hiç veri yok
# ─────────────────────────────────────────────────────────────────────────────
#
# Bu ekran ekstre modelinde KAÇINILMAZ ilk deneyimdir ve mockup'ların
# hiçbirinde yoktu. Öncül baz 40'a çekildiği için gösterilen bant düşük
# (34–58 gibi). Metnin işi bu düşüklüğü bir YARGI değil, bir DAVET
# hâline getirmek: "seni tanımıyoruz" diyoruz, "kötüsün" demiyoruz.
#
# Belirsizliği bize yükleyen bu çerçeve aynı zamanda ürünün istediği
# teşviki yaratır: gerçek skoru görmenin tek yolu ekstre yüklemek.

GUN0 = {
    "skor_ustu": "Henüz seni tanımıyoruz",
    "skor_alti": "Bu aralık yalnızca 5 sorudan çıktı. "
                 "Hiçbir finansal verini görmedik.",
    "kart_baslik": "Gerçek skorunu gör",
    "kart_govde": "İlk ekstreni yükle. Gelirin, giderin, borcun ve "
                  "harcama düzenin hesaba katılınca skorun kişiselleşir "
                  "— genelde de yükselir.",
    "cta": "Ekstre Yükle",
    "ikincil": "Nasıl ekstre indiririm?",
    "guven_notu": "Bu bir tahmin, ölçüm değil.",
}

#: İlk ekstre yüklendikten hemen sonra gösterilen geçiş mesajı.
#: Skorun neden sıçradığını açıklar — kullanıcı "iyileştim" sanmasın.
ILK_EKSTRE_SONRASI = {
    "baslik": "Skorun gerçek verilerinle güncellendi",
    "govde": "Değişimin sebebi finansal durumunun düzelmesi değil; "
             "artık seni ölçebiliyoruz. Buradan sonrası gerçekten sana bağlı.",
}


# ─────────────────────────────────────────────────────────────────────────────
# Acil durum fonu — kademeli hedef
# ─────────────────────────────────────────────────────────────────────────────
#
# KARAR (12 Ağu 2026): skor 3 ay üzerinden hesaplanır, 6 ay skorun
# DIŞINDA bir ileri seviye hedefidir.
#
# Gerekçe: kullanıcıya gösterilen hedefle skorun hedefi aynı olmalı.
# Aksi hâlde gösterilen 3 aylık hedefe ulaşan kullanıcı o alt metrikte
# tam puan alamaz ve kale direği kaymış gibi hisseder. Türkiye'nin
# enflasyon ortamında 6 ay nakit tutmanın reel maliyeti de yüksek.

GUVENCE = {
    "baslik": "Acil Durum Fonu",
    "aciklama": "İşini kaybettiğinde ya da beklenmedik bir gider "
                "çıktığında borçlanmadan kaç ay dayanabileceğin.",
    "kademe1_ad": "Güvenlik Ağı",
    "kademe1_alt": "3 aylık zorunlu giderin. Skorun bu hedefe göre hesaplanır.",
    "kademe2_ad": "Tam Güvence",
    "kademe2_alt": "6 aylık zorunlu giderin. Skorunu etkilemez — "
                   "ulaşırsan rozet kazanırsın.",
    "kademe1_tamam": "Güvenlik ağını kurdun. İstersen Tam Güvence'ye "
                     "devam edebilirsin.",
    "kademe2_tamam": "Tam Güvence'ye ulaştın.",
    "sifir": "Henüz acil durum fonun yok. Küçük bir tutarla başlamak "
             "bile fark yaratır.",
    "neden_3_ay": "6 ay uluslararası standart, ama düşük enflasyonlu "
                  "ülkeler için üretildi. Türkiye'de nakit tutmanın "
                  "maliyeti yüksek olduğu için ilk hedefi 3 ay tuttuk.",
}


def guvence_durum(ay: float, kademe1: float, kademe2: float) -> str:
    """Fon süresine göre tek cümlelik durum metni."""
    if ay <= 0:
        return GUVENCE["sifir"]
    if ay >= kademe2:
        return GUVENCE["kademe2_tamam"]
    if ay >= kademe1:
        return GUVENCE["kademe1_tamam"]
    return (f"Zorunlu giderinin {_ay(ay)} kadarını karşılıyor. "
            f"Hedef {_ay(kademe1)}.")


def _ay(x: float) -> str:
    s = f"{x:.1f}".replace(".", ",").rstrip("0").rstrip(",")
    return f"{s} ay"


# ─────────────────────────────────────────────────────────────────────────────
# Veri kapsamı
# ─────────────────────────────────────────────────────────────────────────────

KAPSAM = {
    "eksik_tekil": "{aylar} ekstresi eksik. Yükleyince skorunun "
                   "kesinliği artar.",
    "eksik_coklu": "{aylar} ekstreleri eksik. Yükledikçe skorun netleşir.",
    "tam": "Son 6 dönemin tamamı yüklü.",
}

BANT = {
    "alt_not": "Veri arttıkça bu aralık daralacak.",
    "aciklama": "Skorunu tek sayı yerine aralık olarak gösteriyoruz, "
                "çünkü elimizdeki veri henüz kesin bir sonuç için yeterli değil.",
}


# ─────────────────────────────────────────────────────────────────────────────
# Devam eden dönem
# ─────────────────────────────────────────────────────────────────────────────

DONEM = {
    "kapanan_ust": "Kapanan dönem",
    "devam_ust": "Devam eden dönem",
    "devam_uyari": "Bu dönem henüz kapanmadı. Yalnızca elle eklediğin "
                   "işlemleri içerir ve skorunu henüz etkilemez.",
    "devam_bos": "Henüz işlem eklemedin.",
    "kaynak": "{tarih} tarihli ekstreye göre",
}


def eksik_ay_metni(aylar: list, ay_adlari: Dict[int, str]) -> str:
    if not aylar:
        return ""
    adlar = [ay_adlari[int(m.split("-")[1])] for m in aylar]
    sablon = KAPSAM["eksik_tekil"] if len(adlar) == 1 else KAPSAM["eksik_coklu"]
    return sablon.format(aylar=", ".join(adlar))


# ─────────────────────────────────────────────────────────────────────────────
# Kategori triyajı — "bu ne harcamasıydı?"
# ─────────────────────────────────────────────────────────────────────────────
#
# İMPULS TRİYAJINDAN AYRI bir ekrandır ve ayrı olması gerekir:
#
#   · İmpuls sorusu İŞLEME sorulur ("bu alışveriş plansız mıydı"), çünkü
#     aynı marketten yapılan iki alışverişten biri plansız olabilir.
#   · Kategori sorusu İŞYERİNE sorulur ("burası ne satıyor"), çünkü bir
#     işyeri ne satıyorsa onu satar. Cevap o işyerinin GEÇMİŞ ve GELECEK
#     tüm işlemlerine yayılır.
#
# Bu fark kullanıcıya da yansıtılmalı: bir cevabın kaç işlemi çözdüğünü
# görmek, soruyu cevaplama motivasyonunu doğrudan artırır.
#
# TON: soru "bilmiyoruz" diye çerçevelenir, kullanıcının eksiği olarak
# değil. Ekstrede o bilgi GERÇEKTEN yoktur — bu bizim sınırımızdır.

KATEGORI_TRIYAJ = {
    "baslik": "Bu işyerleri ne satıyor?",
    "alt": "Ekstrede yazmıyor, o yüzden soruyoruz. Bir cevap o işyerinin "
           "tüm harcamalarını düzeltir.",
    "atlanabilir": True,
    "atla": "Şimdilik atla",
    # Neden sorulduğu her kartta gösterilir — çıkarım şeffaf olmalı.
    "neden_tanimiyoruz": "Bu işyerini tanımıyoruz",
    "neden_pazaryeri": "Pazaryeri — ne alındığı ekstrede yazmıyor",
    # Cevabın kapsamı: kullanıcı ne kazandığını görsün.
    "kapsam_tekil": "Bu işyerinden 1 harcaman var",
    "kapsam_coklu": "Bu işyerinden {adet} harcaman var",
    "kapsam_not": "Cevabın hepsine ve bundan sonrakilere uygulanır.",
    # Ekran tamamlandığında
    "bitti": "Teşekkürler — harcama analizin bu cevaplarla netleşti.",
    "bos": "Şu an sorulacak bir şey yok; harcamalarının tamamı tanındı.",
    # Neden önemli olduğunun açıklaması (bilgi kutusu)
    "aciklama": "Tanımadığımız harcamalar için zorunlu/isteğe bağlı ayrımını "
                "tahmin ediyoruz. Cevapladıkça tahmin yerini ölçüme bırakır.",
}


# ─────────────────────────────────────────────────────────────────────────────
# Ölçülemeyen alt metriğin GEREKÇESİ
# ─────────────────────────────────────────────────────────────────────────────
#
# Bir alt metrik kapandığında kullanıcıya "bu bileşen eksik" demek yetmez;
# NEDEN eksik olduğunu ve NE YAPARSA açılacağını söylemek gerekir. Aksi
# hâlde belirsizlik gizlenmiş olur (kural S2) ve kullanıcı düzeltemeyeceği
# bir eksikliğe bakar.
#
# Anahtar `SubScore.requires` içindeki `Features` alan adıdır. Motor hangi
# alanın eksik olduğunu bilir; cümleyi buradan alır.

VERI_YOK_NEDEN: Dict[str, str] = {
    "liquid_balance":       "Vadesiz hesap bakiyesi görünmüyor.",
    "ef_liquid":            "Acil durum fonu olarak işaretli bir hesap yok.",
    "i_net":                "Gelir kaydı görünmüyor.",
    "i_cv":                 "Gelir oynaklığı için en az üç dönem gerekiyor.",
    "i_primary_share":      "Gelir kaynakları ayrıştırılamadı.",
    "e_total":              "Harcama kaydı görünmüyor.",
    "card_balance":         "Kredi kartı bakiyesi görünmüyor.",
    "card_limit":           "Kredi kartı limiti girilmemiş.",
    "debt_avg_rate":        "Borçlarının faiz oranı girilmemiş.",
    "net_worth":            "Varlık hesapların görünmüyor.",
    "payment_carry_days":   "Son ödeme günü veya gelir tarihi görünmüyor.",
    "goal_plan_adherence":  "Hedeflerine aylık katkı planı koymamışsın.",
    "debt_trend_3m":        "Borç trendi için üç dönemlik geçmiş gerekiyor.",
    "s_consistency_months": "Birikim sürekliliği için en az üç dönem gerekiyor.",
    "real_return_gap":      "Birikimin getirisi hesaplanamadı.",
    "budget_planned":       "Bütçe belirlenmemiş.",
    "budget_overrun":       "Bütçe belirlenmemiş.",
    "limit_categories":     "Kategori limiti konmamış.",
    "cat_volatility":       "Kategori oynaklığı için daha fazla dönem gerekiyor.",
    "goal_ontrack":         "Aktif hedef yok.",
    "goal_consistency":     "Hedef katkı geçmişi henüz oluşmadı.",
    "goal_required_monthly": "Hedefin aylık katkı planı belirlenmemiş.",
    "imp_rate":             "Yeterli harcama etiketi yok.",
    "emo_rate":             "Yeterli harcama etiketi yok.",
    "night_conc":           "İşlem saatleri görünmüyor.",
    "regret_rate":          "Harcama sonrası değerlendirme kaydı yok.",
}


def veri_yok_neden(alanlar) -> str:
    """Eksik alanlardan tek bir gerekçe cümlesi.

    Birden fazla alan eksikse İLK bilineni söylenir — kullanıcıya liste
    değil, tek bir eyleme dönüştürülebilir cümle verilir.
    """
    for a in alanlar:
        if a in VERI_YOK_NEDEN:
            return VERI_YOK_NEDEN[a]
    return ""
