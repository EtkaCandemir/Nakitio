# Nakitio — Ekran Mimarisi ve Kanonik Veri Seti, v1.0

**Durum:** Tasarım ve frontend için uygulanmaya hazır
**Kanonik veri:** `engine/screen_data.py` → `engine/screen_data.json`
**Bağlı olduğu:** `skor-modeli-v2.md`, `veri-katmani-v1.md`, `ekstre-alimi-v1.md`, `ai-koc-v1.md`

```bash
cd engine && python3 screen_data.py
```

---

## 1. Kanonik veri seti — sayı tartışması biter

Mockup'larda aynı kullanıcının tasarruf oranı bir ekranda **%26**, diğerinde
**%25**; geliri bir ekranda **₺28.450**, diğerinde **₺45.000**; tarih bir
ekranda **Temmuz 2026**, diğerinde **Mayıs 2025**.

Bu tür tutarsızlıklar tasarımda zararsız görünür ama mühendislikte
*"hangisi doğru"* sorusu her ekranda yeniden sorulur ve her seferinde
farklı cevaplanır.

**Çözüm:** `screen_data.json` her ekranın göstereceği her sayıyı **tek
kaynaktan** üretir — Didem'in 281 ham işleminden, normalizasyondan ve skor
motorundan geçerek. Tasarım ve frontend aynı dosyadan beslenir.

> Ekran verisi değişecekse `screen_data.json` elle düzenlenmez;
> `fixture_didem.py` değiştirilir ve dosya yeniden üretilir. Sayı uydurmak
> yapısal olarak imkânsız hâle gelir.

### Üç durum — boş ekranlar da kanoniktir

| Durum | Skor | Güven | Ne gösterir |
|---|---|---|---|
| `gun0` | **44–68** (bant) | 0,00 | Hiç veri yok. Ekstre modelinde kaçınılmaz ilk deneyim |
| `ilk_ekstre` | **66–75** (bant) | 0,59 | Tek dönem yüklü, 5 dönem eksik |
| `olgun` | **74** | 0,89 | 5 dönem, tam veri |

Mockup'ların hiçbiri ilk ikisini çizmiyor — oysa **her kullanıcı oradan
başlıyor.** Tasarım borcunun en büyük kalemi bu.

---

## 2. Bilgi mimarisi kararı

Mockup'larda iki farklı alt menü var:

- v1: `Ana Sayfa / Raporlar / + / Planlar / Araçlar`
- v2: `Ana Sayfa / Hedeflerim / İşlemler / AI Koçu / Profilim`

**Karar — 4 sekme + merkez eylem:**

| Sekme | İçerik | Beslendiği motor |
|---|---|---|
| **Ana Sayfa** | Skor kartı, dönem özeti, farkındalık, birincil eylem | `get_score`, `screen_home` |
| **Analiz** | Skor kırılımı, gelir&gider, kategoriler, davranış, riskler, işlemler | `get_score_breakdown`, `get_top_categories`, `get_risks` |
| **➕** | **Ekstre Yükle** · **İşlem Ekle** | `statement_ingest`, hızlı ekleme |
| **Planlar** | Hedefler, aksiyon planı, görevler | `build_action_plan`, `screen_goals` |
| **Koç** | AI sohbet | `coach_tools` + `coach_guard` |

Gerekçe: ürünün çekirdek döngüsü **yükle → gör → anla → aksiyon al**.
Dört sekme bunu birebir karşılıyor.

- **Profil** ana sayfanın sol üstündeki avatara taşınır (mockup 1-0'da zaten orada).
- **İşlemler** Analiz altında bir alt ekran — ayrı sekmeyi hak etmiyor.
- **Araçlar** MVP'de yok.

### Marka

Mockup'ların 6'sı **mor**, 1'i (farkındalık akışı) **yeşil** maskot ve yeşil
logo kullanıyor.

**Karar: mor birincil, yeşil semantik.** Yeşil zaten mor ekranlarda
"olumlu/artış" anlamında kullanılıyor (*+4 puan*, *Gelir*). İki maskot
olmaz — mor robot kalır.

---

## 3. Ana sayfa — aylık ritim

**Bu, hibrit kararının en büyük ekran sonucu.**

Ekstre modelinde **cari ay hiçbir zaman tam değildir.** Ekstre 31 Temmuz'da
kesildi, bugün 8 Ağustos — son 8 günün verisi yok. Mockup'ın
*"Temmuz 2026 · Bu ay tasarruf oranı %26"* kartı bu modelde yalan söyler.

**Çözüm: ana sayfa iki bölgeye ayrılır.**

```
┌──────────────────────────────────────────────┐
│  KAPANAN DÖNEM          1 Tem – 30 Tem       │  ← otoriter
│  31 Temmuz 2026 tarihli ekstreye göre        │
│                                              │
│  Finansal Sağlık Skorun        74/100        │
│  Gelişiyor · veri yeterliliği Yüksek         │
│                                              │
│  Gelir ₺27.890  Gider ₺19.463  Korunan ₺8.426│
│  Tasarruf oranı %19,0                        │
├──────────────────────────────────────────────┤
│  DEVAM EDEN DÖNEM       31 Tem'den beri      │  ← kısmi
│  8 gün · yalnızca elle eklediğin işlemler    │
│                                              │
│  [+ İşlem Ekle]                              │
├──────────────────────────────────────────────┤
│  ⚠ Şubat ekstresi eksik.                     │
│     Yükleyince skorunun kesinliği artar.     │
│                          [Ekstre Yükle]      │
├──────────────────────────────────────────────┤
│  💡 Eğlence & Hobi harcaman %76,5 arttı;     │
│     enflasyondan arındırınca gerçek artış    │
│     %73,1.                                   │
└──────────────────────────────────────────────┘
```

### Birincil eylem duruma göre değişir

Ana sayfada tek büyük CTA vardır ve `_primary_action` onu belirler:

| Koşul | CTA |
|---|---|
| Hiç veri yok | **Ekstre Yükle** — "İlk ekstreni yükle" |
| Eksik dönem var | **Ekstre Yükle** — "Şubat ekstresi eksik" |
| Veri tam | **Planı Gör** — "Kategori limiti koy · Skorun 77'ye çıkabilir (tahmini)" |

---

## 4. Skor kartının sunum kuralları

Bunlar skor modelinden gelen **zorunlu** kurallar, tasarım tercihi değil:

| Kural | Alan | Neden |
|---|---|---|
| `C < 0,65` → skor **bant** olarak | `bant_olarak_sun` | Tek sayı, olmayan bir hassasiyet vaat eder |
| Güven düşükken **seviye etiketi gösterilmez** | `seviye_goster` | 5 onboarding cevabından türetilmiş skora "Dikkat" demek, "hiçbir zaman utandırma" ilkesinin ihlali — kullanıcı henüz ölçülmedi, yargılanamaz |
| Bant gösterilirken alt not zorunlu | `alt_not` | "Veri arttıkça bu aralık daralacak." |
| Aşama adı skordan gelir | `baslik` | Farkındalık Başlangıç / Geçiş / Finansal Sağlık |

`gun0` ekranında bu kuralların hepsi devrededir: **44–68**, seviye etiketi
yok, alt not var.

---

## 5. Yeni akışlar

Bunların hiçbirinin mockup'ı yok ve üçü de hibrit kararının doğrudan sonucu.

### A. Ekstre yükleme

```
1. Kaynak        dosya seç · paylaş menüsünden geldi
2. Tanıma        banka + belge türü (hesap hareketleri / kart ekstresi)
3. Parola        şifreli PDF ise iste + banka bazlı ipucu
                 ⚠ parola saklanmaz, loglanmaz, gönderilmez
4. Önizleme      "142 işlem bulundu · 118 yeni · 24 zaten vardı"
                 dönem: 19 Haz – 18 Tem
5. Onay          içe aktar
6. → Triyaj
```

Hata durumları: taranmış PDF (→ "internet bankacılığından PDF indir"),
tanınmayan düzen (→ "bu bankayı henüz desteklemiyoruz"), yanlış parola.

### B. Triyaj — İKİ AYRI ekran

Yükleme sonrası iki farklı soru sorulur ve **ayrı olmaları yapısal bir
gerekliliktir**, tasarım tercihi değil:

| | Soru | Kime | Cevap neyi çözer |
|---|---|---|---|
| **İmpuls triyajı** | "Bu harcama plansız mıydı?" | İŞLEME | O tek işlem |
| **Kategori triyajı** | "Bu işyeri ne satıyor?" | İŞYERİNE | O işyerinin TÜM işlemleri |

Fark, aynı marketten yapılan iki alışverişten birinin plansız olabilmesinden
gelir — ama bir işyeri ne satıyorsa onu satar. Bu yüzden kategori cevabı
`RawData.category_overrides` üzerinden kalıcıdır ve geçmiş+gelecek tüm
işlemlere yayılır.

Soru başına bilgi kazancı da bu yüzden çok farklıdır. Gerçek bir kart
ekstresinde ölçüldü: **8 kategori sorusu 30.410 TL'yi aydınlatıyor**, ilk
soru tek başına 9 işlemi. Bu yüzden her kartta *"bu işyerinden N harcaman
var"* yazar — kullanıcı ne kazandığını görmeli.

#### B1. İmpuls triyajı — Davranış Analizi ekranını kurtaran şey

Yükleme sonrası 8–12 kart. **Atlanabilir olmalı** — zorunlu tutulursa
yükleme akışı terk edilir.

```
┌────────────────────────────────────────┐
│  Bu harcamalar plansız mıydı?          │
│  Birkaç saniye — davranış analizin     │
│  bunlarla kişiselleşiyor.      [Atla]  │
├────────────────────────────────────────┤
│  ₺900  Giyim              10 Tem       │
│  ilk kez görülen bir yer · bu          │
│  kategoride alışılmışın üzerinde ·     │
│  taksitle alınmış                      │
│                                        │
│  [ Plansızdı ]      [ Planlıydı ]      │
└────────────────────────────────────────┘
```

Gerekçe her kartta gösterilir — çıkarım şeffaf olmalı, kullanıcı neyi
onayladığını bilmeli. İkinci dokunuş isteğe bağlı duygu etiketi.

Kartlar rastgele değil **bilgi kazancına** göre seçilir
(`select_for_triage`): modelin kararsız olduğu **ve** tutarca önemli
işlemler.

### C. Hızlı işlem ekleme (devam eden dönem)

Tutar → kategori → *plansız mıydı?* → *nasıl hissettin?*

Bu akışın asıl değeri **etiketi doğru anda toplamasıdır** — harcamanın
hemen ardından, aylar sonra değil.

---

## 6. Davranış Analizi ekranı — iddia değil, soru

Duygu ekstreden çıkarılamaz. Bu, ekranın sunumunu değiştirir.

`screen_data.json` her davranış bloğuna `iddia_edilebilir` bayrağı koyar
(`etiket_agirligi >= 0,5`):

| `iddia_edilebilir` | Sunum |
|---|---|
| `true` | *"Plansız harcamaların toplam harcamanın %12'si."* |
| `false` | *"Bu harcamalar plansız görünüyor — doğru mu?"* + onay/ret |

İkinci hâlde ekran hem doluyor hem modeli eğitiyor. Pasif rapor yerine
etkileşimli yüzey — ve bu, çözümün en zarif tarafı: sunum problemi ile
veri problemi birbirini çözüyor.

Gece yoğunlaşması ölçülemiyorsa (`gece_olculemedi_notu`) o satır
gizlenmez, **açıklanır**: *"Ekstrede işlem saati yok; gece yoğunlaşması
ölçülemiyor."*

---

## 7. Ekran → motor eşlemesi

Frontend "bu sayı nereden geliyor" diye sormaz:

| Ekran / bileşen | Fonksiyon |
|---|---|
| Ana sayfa skor kartı | `coach_tools.get_score` |
| Skor Kırılımı | `coach_tools.get_score_breakdown` |
| "Geçen döneme göre +4" | `score_engine.attribute` |
| Harcama Dağılımı, Öne Çıkan Değişimler | `coach_tools.get_top_categories` |
| Riskler sekmesi | `coach_tools.get_risks` |
| AI Aksiyon Planı | `coach_tools.build_action_plan` |
| İmpuls triyaj kartları | `behavior_infer.select_for_triage` |
| Kategori triyaj kartları | `normalize.select_category_triage` |
| Kategori cevabı kaydı | `RawData.category_overrides` |
| Davranış sekmesi | `behavior_infer.estimate_behavior` |
| Dönem etiketleri | `screen_data.period_labels` |
| Eksik dönem uyarısı | `statement_ingest.missing_months` |
| Koç sohbeti | `coach_tools` + `coach_guard.verify_response` |

---

## 8. Ekran envanteri

| Ekran | Durum | Öncelik |
|---|---|---|
| Onboarding (5 soru) | **yok** | MVP |
| Ana sayfa — 3 durum | kısmen (yalnızca dolu hâli) | MVP |
| Ekstre yükleme akışı | **yok** | MVP |
| İmpuls triyajı | **yok** | MVP |
| Kategori triyajı | **yok** — motor + ekran verisi hazır | MVP |
| Finansal Sağlık Raporu | var | MVP |
| Analiz — Genel Bakış / Gelir&Gider / Riskler | var | MVP |
| Analiz — Davranış | var, **yeniden tasarım** (§6) | MVP |
| Hızlı işlem ekleme | **yok** | MVP |
| AI Koç sohbet + aksiyon planı | var | MVP |
| Hedefler | **yok** (mockup'ta yalnızca kart) | MVP |
| İşlem listesi | **yok** | v1.1 |
| Görevler / seri | var, **aylık ritme uyarlanmalı** | v1.1 |
| Farkındalık geçmişi | var | v1.1 |
| Raporlar (aylık karşılaştırma) | **yok** | v1.1 |
| Profil / ayarlar | **yok** | v1.1 |
| Araçlar | **yok** | sonra |

---

## 9. Bu çalışmada yakalanan üç hata

Kanonik veri setini üretmek, üç gerçek tutarsızlığı ortaya çıkardı:

**1. Güven kademesi taban yazılmıştı, tavan olmalıydı.** Kaynağı "ekstre"
olan bir kullanıcı, hesapları sistemde "bağlı" işaretli olduğu için
`c_cover = 1,0` alıyordu — tek dönem yüklemiş biri, açık bankacılığa bağlı
biriyle aynı güveni görüyordu. Artık kaynak neyse kapsamı o belirliyor:
`ilk_ekstre` güveni 0,79 → **0,59**.

**2. Plan kartı ile skor kartı çelişiyordu.** Simülasyon yumuşatmasız
hesaplıyor, gösterilen skor yumuşatılmış. Plan kartı ham tabanı gösterince
ana sayfada **71** yazan skor, plan ekranında **"67 → 71"** oluyordu.
Artık çapa gösterilen skor, delta simülasyondan geliyor: **"71 → 74"**.

**3. Farkındalık kartı tek seferlik olayı eğilim gibi gösteriyordu.**
*"Giyim harcaman %148 arttı"* — oysa bu tek bir 4 taksitli alışverişti.
İki filtre eklendi: bu dönemde yeni taksit planı başlayan kategoriler ve
"Diğer" (kategorize edilememişlerin çöp kutusu) elenir. Sıralama da
yüzdeye değil **mutlak reel TL artışına** göre yapılır — ₺1.200'de %148,
₺5.400'de %12'den daha az önemlidir.

---

## 10. Tasarıma geçmeden önce

1. **`screen_data.json` tasarımcıya verilmeli.** Her ekran bu dosyadaki
   sayılarla çizilir. Farklı bir sayı gerekiyorsa fixture değişir.

2. **Üç durum da çizilmeli.** `gun0` ve `ilk_ekstre` ekranları `olgun`
   kadar önemli — kullanıcı orada başlıyor ve orada terk ediyor.

3. **Görev/seri mekaniği aylık ritme uyarlanmalı.** Mockup'taki
   *"4 gün üst üste"* ve *"bugünün görevi"* ekstre modelinde karşılığı
   olmayan bir vaat. Hibrit akışta hızlı ekleme günlük teması taşıyabilir
   ama seri mekaniği yeniden düşünülmeli.

4. **Boş durum metinleri yazıldı.** `metinler.GUN0` yedi metni taşıyor
   (`skor_ustu`, `skor_alti`, `kart_baslik`, `kart_govde`, `cta`, `ikincil`,
   `guven_notu`) ve `screen_data.screen_home` `days_of_data == 0` olduğunda
   bunları ekliyor. Bu madde bir süre "hâlâ belirsiz" yazılı kaldı; ürünün
   kendi karar kaydıyla (`DECISIONS.md` §7) çelişiyordu.

5. **Erişilebilirlik.** Skor rengi tek başına anlam taşımamalı (renk körlüğü),
   bant gösterimi ekran okuyucuda anlaşılır olmalı.

## Ek — Dosya haritası

| Dosya | İçerik |
|---|---|
| `engine/screen_data.py` | Kanonik veri üreteci, 3 durum, 6 ekran |
| `engine/screen_data.json` | Üretilen veri — tasarım ve frontend kaynağı |
