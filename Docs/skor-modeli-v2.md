# Nakitio — Finansal Sağlık Skoru, Model v2.0

**Durum:** Uygulanmaya hazır teknik şartname
**Referans implementasyon:** `engine/score_engine.py`
**Parametre tablosu:** `engine/params.py` · **Duyarlılık analizi:** `engine/tune.py`
**Metinler:** `engine/metinler.py`
**Golden test:** `engine/golden_profiles.py` (15 profil) · **Değişmez kural testleri:** `engine/test_invariants.py` (240 kontrol)
**Yerini aldığı doküman:** `Docs/finansal skor yapısı.docx` (v1)

> Bu doküman ile `engine/score_engine.py` çeliştiğinde **kod esas alınır.**
> Buradaki tüm sayısal örnekler kodun çalıştırılmasıyla üretilmiştir, elle
> yazılmamıştır.

---

## 0. Neden yeni bir model

v1 modeli iyi bir üründü ama dokuz yapısal sorun taşıyordu. Bunların her biri
v2'de belirli bir tasarım kararına karşılık gelir:

| # | v1'deki sorun | v2'deki karşılığı |
|---|---|---|
| 1 | Harcama Kontrolü (gider/gelir) ve Tasarruf (tasarruf/gelir) matematiksel olarak aynı değişken; 100 puanın 50'si tek olguyu ölçüyordu | Nakit akışı, tasarruf ve disiplin üç ayrı olguya bağlandı (§6.1, §6.3, §6.4) |
| 2 | Gün 30'da formül tamamen değişiyor, skor onlarca puan sıçrıyordu | Tek formül + güven katsayısı `C`; aşamalar artık sunum etiketi (§5) |
| 3 | Basamak tabloları uçurum yaratıyordu (%70,0 → 25 puan, %70,1 → 20 puan) | Tüm eşlemeler sürekli fonksiyon; `t_continuity` ile test ediliyor (§3) |
| 4 | Tek bir işlem impuls puanının tamamını sıfırlayabiliyordu | Davranış metriklerinin hepsi oran bazlı (§6.6) |
| 5 | Görev tamamlama sağlık skorunu şişiriyordu (+2 puan/görev) | Engagement skorun girdisi olmaktan çıkarıldı; `t_no_engagement_inputs` ile yapısal olarak engelleniyor (§9) |
| 6 | Borçsuz kullanıcı ile %20 DSR'li kullanıcı aynı puanı alıyordu | DSR sürekli ölçekte; taksit ve kart kullanımı ayrı ölçülüyor (§6.2) |
| 7 | Enflasyon hiç yoktu | Normalizasyon katmanında kategori bazlı deflasyon zorunlu (§4) |
| 8 | Aylık snapshot, yıllık ödemeler skoru sallıyordu | Amortisman + asimetrik yumuşatma (§4, §8) |
| 9 | Sıfır gelir, düzensiz gelir, eksik veri tanımsızdı | Her biri tanımlı; eksik veri asla ceza değil (§7, §11) |

---

## 1. Tasarım ilkeleri

Bunlar pazarlık konusu değildir. Bir eşiği tartışabiliriz; bu ilkeleri
bozan bir değişiklik modeli bozar.

1. **Skor bir ölçüm aracıdır, bir motivasyon aracı değildir.**
   Motivasyon görev/rozet/seri katmanının işidir. İkisi karıştırıldığında
   ölçüm güvenilirliğini, motivasyon da dürüstlüğünü kaybeder.

2. **Durum, davranış ve kullanım ayrı şeylerdir.** Skora yalnızca ilk
   ikisi girer. Uygulama kullanımı yalnızca *güveni* (`C`) etkiler.

3. **Eksik veri ceza değildir.** Ölçemediğimiz şey için puan kırmayız;
   bileşeni devre dışı bırakır, ağırlığı yeniden dağıtır ve güveni
   düşürürüz.

4. **Süreksizlik yasaktır.** Girdideki küçük değişim skorda küçük değişim
   yaratmalıdır. Basamak tablosu kullanılmaz.

5. **Skor gelir seviyesini değil, gelirle kurulan ilişkiyi ölçer.**
   12.000 TL geliri olan disiplinli biri, 85.000 TL geliri olan
   savrukdan yüksek skor alabilmelidir — ve alır (§10, `deniz` vs `selin`).

6. **Kötü haber hızlı, iyi haber yavaş yayılır.** Skor tek ayda satın
   alınamaz; ama kullanıcı krizini gecikmeli öğrenmez (§8).

7. **Kullanıcı beyanı bileşen skorlarını asla yükseltemez.** Beyan
   yalnızca öncül skoru ve güveni etkiler, veri biriktikçe etkisi sönümlenir.

8. **Skor hiçbir zaman utandırmaz.** v1'in bu ilkesi korunmuştur ve §12'de
   metin kurallarına çevrilmiştir.

---

## 2. Mimari — tek bakışta

```
  Ham işlemler ─┐
  Hesaplar     ─┤
  Krediler     ─┼──▶ [K1: Normalizasyon] ──▶ [K2: Türetilmiş metrikler]
  Hedefler     ─┤     transfer eşleştirme      Features nesnesi
  Bütçeler     ─┘     kart tekilleştirme              │
                      taksit ayrıştırma               ▼
                      amortisman              [K3: Skor motoru]
                      enflasyon düzeltmesi     6 bileşen · sürekli fn
                                                      │
                            ┌─────────────────────────┼──────────────────┐
                            ▼                         ▼                  ▼
                     [K4: Güven C]           [K5: Yumuşatma]     [K6: Ayrıştırma]
                     veri yeterliliği        EWMA + asimetri     "+4 puan neden"
                            │                         │                  │
                            └─────────────┬───────────┘                  │
                                          ▼                              ▼
                                    GÖSTERİLEN SKOR ◀────────── [K7: Simülasyon]
                                                                 "plan sonrası: 78"
                                                                          │
                                                                          ▼
                                                                    [K8: AI Koç]
                                                                 yalnızca ANLATIR
```

**Katman 8 kritik:** AI koç hiçbir sayı üretmez. `engine`'in döndürdüğü
sayıları Türkçeye çevirir. Bunun gerekçesi §13'te.

---

## 3. Matematiksel temel

Üç eşleme fonksiyonu kullanılır. Hepsi süreklidir, monotondur ve
0–100 aralığına kelepçelenmiştir.

### `lin(x, zero_at, hundred_at)` — parçalı doğrusal

```
lin(x, a, b) = 100 × clamp₀¹( (x − a) / (b − a) )
```

`b < a` ise "küçük olan iyidir" demektir. Basamak tablolarının yerini alır.

> **Örnek — v1'deki uçurumun kaybolması.** v1'de gider/gelir %70,0 iken
> 25 puan, %70,1 iken 20 puandı: 28.450 TL gelirde **28 TL fazla harcama
> 5 puan kaybettiriyordu.** v2'de aynı geçiş 0,01 puanlık bir değişim
> üretir.

### `sat(x, k)` — doygunlaşan

```
sat(x, k) = 100 × (1 − e^(−x/k))
```

`x = k` → 63, `x = 2k` → 86, `x = 3k` → 95. "Daha fazlası hep iyidir ama
getirisi azalır" ilişkileri için: tasarruf oranı, nakit akışı marjı.
%30 tasarruf %20'den iyidir, ama aradaki fark %0 → %10 kadar büyük değildir.

### `concave(x, full_at, p=0.6)` — içbükey doyum

```
concave(x, F, p) = 100 × min(1, x/F)^p
```

"İlk birim en değerlidir" ilişkileri için: acil durum fonu. Sıfırdan 1 aylık
güvenceye geçmek (0 → 46 puan), 5 aydan 6 aya geçmekten (95 → 100)
çok daha değerlidir. Bu, gerçek finansal riskin şeklidir.

---

## 4. Katman 1 — Normalizasyon (atlanamaz)

Skor motoruna giren her rakam bu adımlardan geçmiş olmalıdır. Bu katman
atlanırsa model matematiksel olarak doğru ama **finansal olarak yanlış**
sonuç üretir.

| Kod | Kural | Atlanırsa ne olur |
|---|---|---|
| **N1** | **İç transfer eşleştirme.** ±3 gün içinde, ≤1 TL farkla eşleşen (−X, +X) çiftleri `is_internal_transfer` işaretlenir; gelir ve giderden düşülür | Kendi hesapları arasında para gezdiren kullanıcı hem devasa gelir hem devasa gider görünür |
| **N2** | **Kart ödemesi tekilleştirme.** Kredi kartına yapılan ödeme gider *değildir*; harcamalar zaten `purchase` olarak sayılmıştır | **Her harcama iki kez sayılır.** En sık ve en ölümcül hata |
| **N3** | **Taksit ayrıştırma.** Taksitli alışveriş iki görünüme ayrılır: *tahakkuk* (satın alma ayında tam tutar — davranış ölçümü için) ve *nakit* (aylık taksit — nakit akışı ve borç için). Kalan taksit toplamı `installment_remaining` olarak taahhüt sayılır | 12 taksitle alınan 12.000 TL'lik telefon "aylık 1.000 TL gider" görünür, 11 aylık yükümlülük görünmez. Türkiye'de bu tek başına modeli geçersiz kılar |
| **N4** | **Amortisman.** Periyodu ≥90 gün olan düzenli ödemeler (sigorta, vergi, aidat, okul taksiti) aylara eşit dağıtılır | Sigorta ödenen ay skor çöker, ertesi ay fırlar; kullanıcı sebebini anlamaz |
| **N5** | **Enflasyon düzeltmesi.** Kategori bazlı TÜFE ile deflate edilir: `reel = nominal × (TÜFE_bugün / TÜFE_ay)`. Karşılaştırmalı tüm metrikler reel değer kullanır | *"Restoran harcaman +%27 arttı"* denir; oysa %4'ü enflasyondur. Kullanıcı haksız yere suçlanır |
| **N6** | **Döviz/altın/fon.** TRY'ye çevrilir. **Yalnızca katkılar tasarruf sayılır, değerleme farkı sayılmaz.** Altın yükseldi diye kullanıcı "tasarruf etti" sayılmaz | Piyasa hareketi davranış gibi ölçülür; skor kullanıcının kontrolü dışındaki şeye tepki verir |
| **N7** | **İade eşleştirme.** Refund, eşleştiği `purchase`'ı azaltır | İade edilen alışveriş harcama olarak kalır |
| **N8** | **Aykırı değer.** Tek işlem > 3× aylık gelir ise `unusual` bayrağı; ilgili ayın disiplin metriklerinden çıkarılır, ayrıca raporlanır | Ev/araba alımı skoru yok eder |
| **N9** | **Zorunlu/isteğe bağlı sınıflandırma.** `e_essential`: kira, fatura, market-temel, ulaşım, sağlık, eğitim, kredi ödemesi | `disc_share` ve `ef_months` hesaplanamaz |

---

## 5. Skor formülü

```
S_ham   = Σᵢ wᵢ_norm × pᵢ                 pᵢ ∈ [0,100]
S_öncül = onboarding baz skoru            ∈ [28, 75]
S_karma = C × S_ham + (1 − C) × S_öncül
S_final = yumuşat(S_karma, S_önceki)      §8
```

`wᵢ_norm`: devre dışı bileşenlerin ağırlığı aktifler arasında yeniden
dağıtıldıktan sonraki ağırlık. Toplamı her zaman tam olarak 100'dür
(`t_missing_data_never_punishes` ile test edilir).

### Aşamalar artık formül değil, etiket

v1'in üç ayrı formülü kaldırıldı. Aynı formül, farklı `C` değerlerinde
çalışır. Kullanıcıya gösterilen isim `C`'ye bağlıdır:

| Koşul | Gösterilen ad |
|---|---|
| `C < 0,30` veya gün < 8 | Farkındalık Başlangıç Skoru |
| `0,30 ≤ C < 0,65` | Geçiş Skoru |
| `C ≥ 0,65` | Finansal Sağlık Skoru |

**Gün 30 uçurumunun kalktığının kanıtı** (`golden_profiles.py` süreklilik testi):

<!-- OTOMATIK:sm-sureklilik -->
*`golden_profiles.veri_sureklilik()`'ten üretildi.*

| gün | C | ham | öncül | karma | skor | aşama |
|---|---|---|---|---|---|---|
| 10 | 0,21 | 60,1 | 39,0 | 43,4 | **43** | Farkındalık Başlangıç |
| 15 | 0,33 | 60,0 | 39,0 | 45,9 | **46** | Geçiş |
| 20 | 0,46 | 59,9 | 39,0 | 48,6 | **49** | Geçiş |
| 25 | 0,51 | 59,7 | 39,0 | 49,5 | **50** | Geçiş |
| 28 | 0,52 | 59,6 | 39,0 | 49,8 | **50** | Geçiş |
| **30** | 0,53 | 59,5 | 39,0 | 49,9 | **50** | Geçiş |
| **31** | 0,54 | 59,5 | 39,0 | 50,0 | **50** | Geçiş |
| 35 | 0,56 | 59,3 | 39,0 | 50,3 | **50** | Geçiş |
| 40 | 0,58 | 59,2 | 39,0 | 50,7 | **51** | Geçiş |
| 60 | 0,67 | 59,1 | 39,0 | 52,4 | **52** | Finansal Sağlık |
| 90 | 0,80 | 59,1 | 39,0 | 55,0 | **55** | Finansal Sağlık |
<!-- /OTOMATIK:sm-sureklilik -->

Karşılaştırma: v1'de aynı kullanıcı gün 30'da 87,5 alıp gün 31'de ~55'e
düşüyordu — **tek gecede 32 puan**, hem de en çok emek vermiş kullanıcıda.

---

## 6. Bileşenler

| # | Bileşen | Ağırlık | Ölçtüğü olgu |
|---|---|---|---|
| P1 | Nakit Akışı | 25 | Gelir–gider ilişkisi ve kırılganlığı |
| P2 | Borç Yükü | 20 | Mevcut ve gelecek yükümlülükler |
| P3 | Tasarruf & Güvence | 20 | Kasıtlı birikim ve şoka dayanıklılık |
| P4 | Harcama Disiplini | 15 | Plana uyum |
| P5 | Hedef Devamlılığı | 10 | Söylediğini yapma |
| P6 | Finansal Davranış | 10 | Harcamanın psikolojisi |

> Bu 6'lı yapı, `Docs/1-1 anasayfa-finansal sağlık raporu.docx`
> mockup'ındaki kırılımla uyumludur. v1 dokümanındaki 5'li yapı terk
> edilmiştir — mockup zaten daha doğru modeli çiziyordu.

Her bileşen içinde alt metrikler 0–100 hesaplanır ve bileşen-içi
ağırlıklarla birleşir. Devre dışı alt metriklerin ağırlığı, o bileşen
içinde kalanlar arasında yeniden dağıtılır.

### 6.1 P1 — Nakit Akışı (25)

| Alt metrik | Ağırlık | Fonksiyon |
|---|---|---|
| Net nakit akışı marjı | 0,60 | `m ≥ 0`: `20 + 80×sat(m, 0,12)/100` · `m < 0`: `20×(1 + m/0,10)` |
| Gelir istikrarı (CV) | **0,13** | `lin(CV, 0,45 → 0,05)` |
| Kısa vadeli likidite | 0,195 | `concave(runway_gün, 45, 0,7)` |
| Gelir çeşitliliği | 0,075 | `lin(ana_kaynak_payı, 1,00 → 0,60)` |

`m = (i_net − e_total) / i_net`, son 3 ayın medyanı.

**Başabaş noktası 20 puandır, 0 değil.** Gelirini tam harcamak kırılgandır
ama borçlanmak değildir; tasarruf yokluğu zaten P3'te ölçülür ve iki kez
cezalandırılmamalıdır. İki dalın `m = 0`'da aynı değeri vermesi
**zorunludur** — ilk implementasyonda bu sağlanmadığı için sıfır noktasında
12,2 puanlık bir uçurum oluşmuş, `t_continuity` tarafından yakalanmıştır.

**Gelir çeşitliliğinin ağırlığı bilerek düşüktür (0,07).** Tek gelir
kaynağı gerçek bir kırılganlıktır, ama Türkiye'de maaşlı çalışan çoğunluğu
bunun için ciddi biçimde cezalandırmak adil değildir.

### 6.2 P2 — Borç Yükü (20)

| Alt metrik | Ağırlık | Fonksiyon |
|---|---|---|
| Borç servisi / gelir (DSR) | 0,38 | `lin(DSR, 0,50 → 0,10)` |
| Kart kullanım oranı | 0,22 | `lin(CU, 0,90 → 0,20)` |
| Toplam taahhüt / yıllık gelir | 0,25 | `lin(COMMIT, 0,60 → 0,05)` |
| Borç trendi (3 ay) | 0,15 | `lin(Δanapara, +0,20 → −0,15)` |

```
DSR    = (aylık_kredi_ödemesi + aylık_taksit) / i_net
COMMIT = (kalan_anapara + kalan_taksit) / (i_net × 12)
```

**Çarpanlar** (bileşen skoruna uygulanır, alt metriğe değil — böylece
ağırlıkla doğru ölçeklenir):

| Durum | Çarpan |
|---|---|
| 1–29 gün gecikme | ×0,70 |
| 30+ gün gecikme | ×0,45 |
| Sadece asgari ödeme (1–2 ay) | ×0,80 |
| Sadece asgari ödeme (3+ ay, kronik) | ×0,65 |
| Aktif KMH | ×0,85 |

Sadece asgari ödemenin bu kadar ağır olması bilinçlidir: Türkiye'de kronik
borç sarmalının en güçlü tek sinyalidir. v1'de bu −5 puandı.

**Borçsuz kullanıcı 100 alır.** Findeks'ten farklı olarak "kredi geçmişi
yok" bir risk sayılmaz; bu bir kredi notu değildir (§14).

### 6.3 P3 — Tasarruf & Güvence (20)

| Alt metrik | Ağırlık | Fonksiyon |
|---|---|---|
| Kasıtlı tasarruf oranı | 0,33 | `sat(S/i_net, 0,10)` |
| Acil durum fonu | 0,34 | `concave(ef_ay, **3**, 0,6)` |
| Tasarruf sürekliliği | 0,23 | `100 × (pozitif_ay / 6)` |
| Enflasyona karşı koruma | 0,10 | `lin(getiri − TÜFE, −0,25 → 0,00)` |

**`s_deliberate` = kasıtlı transferler.** `gelir − gider` **değildir.**
Bu ayrım v1'in en büyük hatasını düzeltir: v1'de tasarruf artık bakiye
olarak tanımlıydı ve bu, `Harcama Kontrolü` ile matematiksel olarak aynı
değişkendi (`tasarruf/gelir = 1 − gider/gelir`), yani 100 puanın 50'si tek
olguyu iki kez ölçüyordu.

Kaynak: tasarruf/yatırım/altın/döviz/fon hesaplarına giden net transferler.
**30 gün kuralı:** aynı ay içinde geri çekilen transferler sayılmaz —
"ayın son günü aktar, 1'inde geri al" oyununu kapatır (§9).

### Acil fon hedefi: 3 ay (skor) + 6 ay (rozet)

**KARAR (12 Ağu 2026):** skor **3 ay** üzerinden hesaplanır. 6 ay skorun
DIŞINDA bir ileri seviye rozetidir.

Gerekçe: kullanıcıya gösterilen hedefle skorun hedefi aynı olmalıdır.
Aksi hâlde gösterilen 3 aylık hedefe ulaşan kullanıcı o alt metrikte tam
puan alamaz ve kale direği kaymış gibi hisseder. Ayrıca 6 ay uluslararası
standarttır ama düşük enflasyonlu ülkeler için üretilmiştir; Türkiye'de
nakit tutmanın reel maliyeti yüksektir.

`concave` sayesinde 1 aylık fon zaten 52 puan getirir — kullanıcı erken
ödüllendirilir. Kademelendirme `engine/screen_data.guvence_kademe()`
içinde; metinler `engine/metinler.GUVENCE`.

### 6.4 P4 — Harcama Disiplini (15)

| Alt metrik | Ağırlık | Fonksiyon |
|---|---|---|
| Bütçe uyumu | 0,38 | `100 × (1 − aşım/planlanan)` |
| Kategori limitlerine uyum | 0,20 | `100 × (1 − aşılan/limitli)` |
| İsteğe bağlı harcama payı | 0,27 | `lin(disc_share, 0,60 → 0,20)` |
| Kategori oynaklığı | 0,15 | `lin(CV_kategori, 0,70 → 0,15)` |

Bu bileşen **gider/gelir oranını kullanmaz** — o P1'in işidir. Burada
ölçülen şey "ne kadar harcadığın" değil, **"dediğini yapıp yapmadığın"**dır.
Mockup'taki `Planlanan / Gerçekleşen` kartı tam olarak bunun girdisidir.

> **İsteğe bağlı harcama payı neden P6'da değil de burada?**
> P6'daki davranış oranları paydada `e_total` kullanır, dolayısıyla yüksek
> kira gibi zorunlu giderleri olan kullanıcı otomatik olarak "disiplinli"
> görünür. Bu çarpıklık tam olarak burada nötrlenir. Aynı olguyu iki
> bileşende ölçmek v1'in temel hatasıydı; bilinçli olarak tekrarlanmıyor.

### 6.5 P5 — Hedef Devamlılığı (10)

| Alt metrik | Ağırlık | Fonksiyon |
|---|---|---|
| Hedeflerin ilerleme durumu | 0,45 | `100 × ontrack_oranı` |
| Katkı sürekliliği | 0,35 | `100 × son_3_ay_uyum` |
| Hedef gerçekçiliği | 0,20 | `lin(gerekli_katkı / fazla, 1,60 → 0,80)` |

```
ontrack_i = min(1, mevcut_i / beklenen_i)
beklenen_i = hedef_i × (geçen_süre / toplam_süre)
```
Hedef büyüklüğüne göre ağırlıklı ortalama alınır.

**Hedef gerçekçiliği** yeni bir boyuttur ve önemlidir: ulaşılamayacak hedef
koyan kullanıcı sürekli başarısız olur ve uygulamayı bırakır. Model bunu
erken yakalar ve AI koç hedefi yeniden boyutlandırmayı önerebilir.

**60 gün muafiyeti:** hedef koymamış yeni kullanıcı için bileşen tamamen
devre dışıdır. 60 günden sonra hedefsizlik 45 puanlık nötr-düşük bir
değer alır — bulgudur, ceza değildir.

### 6.6 P6 — Finansal Davranış (10)

| Alt metrik | Ağırlık | Fonksiyon |
|---|---|---|
| Plansız harcama oranı | 0,35 | `lin(plansız/e_total, 0,40 → 0,05)` |
| Duygusal harcama payı | 0,25 | `lin(duygusal/e_total, 0,30 → 0,03)` |
| Gece harcama yoğunlaşması | 0,20 | `lin(gece/e_total, 0,35 → 0,05)` |
| Harcama sonrası pişmanlık | 0,20 | `lin(düşük_memnuniyet, 0,50 → 0,05)` |

**Hepsi orandır, olay sayısı değil.** v1'de risk puanları toplanıyordu:
gece +3, online +3, plansız +5, stres +5. Saat 23:00'te stresliyken
yapılan tek bir plansız online alışveriş **16 risk** üretiyor ve 15 puanlık
bileşeni 4'e düşürüyordu; iki tanesi sıfırlıyordu. 50 TL'lik alışveriş ile
5.000 TL'lik aynı cezayı alıyordu. v2'de tek bir işlem bileşeni patlatamaz.

**Kapsam eşiği:** `beh_coverage < %25` ise bileşen devre dışıdır. Yeterince
etiketlenmiş işlem yoksa davranış hakkında konuşulmaz.

Pişmanlık metriği, mockup'taki *"Harcama Sonrası Memnuniyet"* ekranının
zaten topladığı veriden gelir — ürün bu sinyali topluyor ama v1 modeli
kullanmıyordu.

---

## 7. Katman 4 — Veri güveni (C)

```
C = 0,28·c_geçmiş + 0,22·c_kapsam + 0,20·c_bütünlük
  + 0,12·c_doğrulama + 0,18·c_bileşen
C × = min(1, gün / 21)          ← ilk 3 hafta rampası
C × = 0,60  eğer bütünlük şüphesi varsa
```

| Bileşen | Tanım |
|---|---|
| `c_geçmiş` | `min(1, veri_günü / 90)` |
| `c_kapsam` | **kaynağa göre tavan** — aşağıdaki tablo |
| `c_bütünlük` | kategorize edilmiş TL / toplam TL |
| `c_doğrulama` | `1 − |beyan − gözlem| / beyan`; beyan yoksa 0,40 |
| `c_bileşen` | Σ(bileşen ağırlığı × alt metrik kapsamı) / toplam ağırlık — kapalı bileşen 0 sayılır, AÇIK bileşenin içinde verisi olmayan alt metrik de kapsamı düşürür |

### `c_kapsam` üç kademelidir ve kademe bir TAVANDIR

| Kaynak (`data_source`) | Hesap |
|---|---|
| `linked` (açık bankacılık) | `bağlı_hesap / beyan_edilen_hesap` — tavan yok |
| `statement` (ekstre) | `0,85 × statement_coverage × kategorize_oran` |
| `manual` | `0,45 × kategorize_oran` |

İlk sürümde bu `max(bağlı_oran, kademe)` yazılmıştı — yani taban. Kaynağı
"ekstre" olan bir kullanıcı, hesapları sistemde "bağlı" işaretli olduğu
için `c_cover = 1,0` alıyordu: tek dönem yüklemiş biri, açık bankacılığa
bağlı biriyle **aynı güveni** görüyordu. Artık kaynak neyse kapsamı o
belirler.

**Sert eşik kullanılmaz.** İlk sürümde "14 günden azsa C ≤ 0,15" kuralı
vardı; bu, 14. günde C'nin 0,15'ten 0,58'e sıçramasına yol açtı — tam da
kaldırmaya çalıştığımız türden bir süreksizlik. 21 günlük doğrusal rampa
aynı korumayı sürekli biçimde sağlar.

**Bütünlük şüphesi skoru düşürmez, güveni düşürür.** Toplu işlem silme
tespit edildiğinde kullanıcı suçlu sayılmaz; band genişler ve UI'da
inceleme bayrağı çıkar.

### Belirsizlik bandı

```
yarı_genişlik = max(2, 12 × (1 − C))
```

<!-- OTOMATIK:sm-belirsizlik-bandi -->
*`golden_profiles.py`'den üretildi.*

`C = 0,21` → ±9,5 puan (`can`: **39**, band `30–49`)

`C = 0,90` → ±2 puan (`didem`: **73**, band `71–75`)
<!-- /OTOMATIK:sm-belirsizlik-bandi -->

**UI kuralı:** `C < 0,65` iken skor **bant olarak** gösterilmelidir.
Tek bir sayı, olmayan bir hassasiyet vaat eder.

---

## 8. Katman 5 — Asimetrik yumuşatma

```
α      = 0,70  eğer (maddi_olay ve yeni < önceki)  aksi hâlde  0,35
EWMA   = α × yeni + (1 − α) × çapa
sınır  = ±8 puan/ay          ← maddi olayda AŞAĞI yönde kalkar
```

### Çapa: güven değişimi yumuşatılmaz

**KARAR (12 Ağu 2026).** Yumuşatmanın çapası, önceki dönemin gösterilen
skoru DEĞİL, önceki dönemin **ölçümünün bugünkü güvenle** değerlendirilmiş
hâlidir:

```
karma_önceki = C_önceki × ham_önceki + (1 − C_önceki) × öncül
offset       = gösterilen_önceki − karma_önceki      ← birikmiş gecikme, KORUNUR
çapa         = C_şimdi × ham_önceki + (1 − C_şimdi) × öncül + offset
```

Gerekçe: yumuşatma, kullanıcının **finansal durumunun** skoru hızlı
oynatmasını engellemek içindir. Bizim **ölçümümüzün** düzelmesi ise onun
durumundaki bir değişiklik değil, bizim hatamızın düzelmesidir. Onu
yumuşatmak, yanlış olduğunu bildiğimiz bir sayıyı bile bile göstermektir.

Ölçülen etki — anket sonrası ilk ekstresini yükleyen sağlıklı kullanıcı
(gerçek ham skoru 92):

| Aşama | Eski davranış | Yeni davranış |
|---|---|---|
| Gün 0 — sadece anket | 34–58 | 34–58 |
| **1. ekstre** | **50–60** | **62–72** |
| 2. ekstre | 63 | 75 |
| 3. ekstre | 70 | 82 |
| 6. ekstre | 79 | 88 |

Eski davranışta en iyi tahminimiz 72 iken kullanıcıya 55 gösteriyorduk —
17 puan saklıyorduk ve bu, ekstre yükleyen kullanıcıyı cezalandırıyordu.

**Oyunlanamaz:** güven yalnızca gerçek veri yükleyerek artar ve 1'de doyar.
Yukarı yönlü tek seferlik bir düzeltmedir. Gerçek finansal kötüleşme hâlâ
yumuşatılır ve ±8 sınırına tabidir.
Regresyon: `test_invariants.t_confidence_change_is_not_smoothed`.

**Maddi olaylar:** 30+ gün gecikme · gecikmiş ödeme · KMH kullanımının
başlaması · 3+ ay sadece asgari ödeme · gelirde %40+ düşüş · gelir kaydının
kesilmesi · acil fonun 0,25 ayın altına inmesi.

Kanıt (`golden_profiles.py` maddi olay testi):

<!-- OTOMATIK:sm-maddi-olay -->
*`golden_profiles.veri_maddi_olay()`'dan üretildi.*

```
Normal ay            : 73
Gecikmeye düştü      : 66   (Δ −7)   ← ±8 sınırı bypass edildi
Ani büyük iyileşme   : 75   (Δ +2)   ← yukarı yön sınırlı kaldı
```

Tespit edilen maddi olay: gecikmiş ödeme.
<!-- /OTOMATIK:sm-maddi-olay -->

Asimetri hem dürüstlük hem anti-gaming gereğidir: skor tek ayda satın
alınamaz, ama kriz gizlenmez.

---

## 9. Anti-gaming

| Vektör | Önlem | Test |
|---|---|---|
| Görev/seri/giriş ile skor şişirme | Engagement `Features` içinde alan olarak **yok**; motor kaynağında `streak`/`gorev_puani` geçmiyor | `t_no_engagement_inputs` |
| Onboarding'de yalan söyleme | Beyan yalnızca `S_öncül` ve `C`'yi etkiler; `S_ham` değişmez ve etkisi zamanla sönümlenir | `t_self_report_cannot_raise_pillars` |
| Ay sonu tasarruf transferi, ertesi gün geri çekme | 30 gün bekleme kuralı; aynı dönemde geri çekilen transfer sayılmaz | N6 + §6.3 |
| Kötü işlemleri silme | Silinen işlem oranı >%10 → bütünlük bayrağı → `C × 0,60` | §7 |
| Tek ayda skor sıçratma | Yukarı hareket ±8 ile sınırlı, EWMA α=0,35 | `t_asymmetric_smoothing` |
| Kategori düzeltmeleriyle oynama | Düzeltme `c_bütünlük`'ü artırır ama `pᵢ`'yi doğrudan yükseltmez | §7 |

---

## 10. Golden test seti

`python3 engine/golden_profiles.py`

İlk 10 senaryo profili (5 kapsam profiliyle birlikte **güncel ve otomatik
üretilen** tam liste: `Docs/TESTING.md` §6):

<!-- OTOMATIK:sm-golden-senaryo -->
*`golden_profiles.py` çalıştırılarak üretildi. Kapsam profilleri dahil tam liste: `Docs/TESTING.md` §6.*

| Profil | Skor | Band | Ham | Öncül | C | Seviye |
|---|---|---|---|---|---|---|
| **didem** — Mockup kullanıcısı — maaşlı, dengeli, orta borç | **73** | 71–75 | 74,7 | 46,0 | 0,90 | Gelişiyor |
| **mehmet** — Kart sarmalı — asgari ödeme, gecikme, KMH | **33** | 31–35 | 27,2 | 28,0 | 0,85 | Riskli |
| **zeynep** — Serbest çalışan — yüksek gelir oynaklığı, borçsuz, iyi birikim | **83** | 81–85 | 83,4 | 74,0 | 0,97 | Dengeli |
| **can** — 12 günlük yeni kullanıcı — veri yok denecek kadar az | **39** | 30–49 | 48,3 | 37,0 | 0,21 | Riskli |
| **elif** — Güçlü — yüksek tasarruf, 6+ ay güvence, borçsuz | **90** | 88–92 | 94,6 | 74,0 | 0,98 | Güçlü |
| **burak** — Taksit yüklü — nakit akışı iyi görünüyor, taahhüt ağır | **60** | 58–62 | 57,4 | 46,0 | 0,97 | Gelişiyor |
| **deniz** — Öğrenci — düşük gelir, yüksek disiplin, borçsuz | **78** | 76–80 | 83,5 | 74,0 | 0,84 | Dengeli |
| **selin** — Yüksek gelir, sıfır tampon — gizli risk | **40** | 38–42 | 32,8 | 37,0 | 0,98 | Dikkat |
| **ahmet** — Emekli — düşük gelir, borçsuz, enflasyona yeniliyor | **83** | 80–85 | 86,1 | 74,0 | 0,81 | Dengeli |
| **merve** — Gün 25 — geçiş dönemi, kısmi veri | **50** | 44–56 | 59,7 | 39,0 | 0,53 | Dikkat |
| **okan** — Taksitle yaşayan — aynı borç hacmi, faizsiz | **69** | 67–71 | 68,8 | 46,0 | 0,97 | Gelişiyor |
| **pelin** — Kart döneri — aynı borç hacmi, yıllık %65 faiz | **66** | 64–68 | 66,2 | 46,0 | 0,97 | Gelişiyor |
| **kerem** — Ev sahibi — net varlık yüksek, nakit akışı negatif | **46** | 44–48 | 33,5 | 46,0 | 0,98 | Dikkat |
| **yasemin** — Manuel giriş — bakiye yok, tek pencere, kullanıcı etiketli | **66** | 64–69 | 71,2 | 46,0 | 0,80 | Gelişiyor |
<!-- /OTOMATIK:sm-golden-senaryo -->

Üç profil doğrudan modelin iddialarını sınar:

- **deniz (78) > selin (40)** — 12.000 TL gelirli disiplinli öğrenci,
  85.000 TL gelirli savruk profesyonelden yüksek. Skor gelir seviyesini
  değil ilişkiyi ölçüyor. `t_fairness_income_neutral` bunu ayrıca
  ölçekten bağımsız olarak doğrular.
- **burak (61)** — nakit akışı pozitif, aylık tablosu iyi görünüyor;
  ama 76.000 TL kalan taksit taahhüdü var. v1 bu kullanıcıyı "iyi"
  görürdü.
- **can (40, band 31–49)** — 12 günlük kullanıcı. Skor öncüle neredeyse
  eşit, band çok geniş, hiçbir bileşen veri yokluğu yüzünden 0 almadı.

### Didem'in kırılımı (mockup kullanıcısı)

<!-- OTOMATIK:sm-didem-kirilim -->
*`compute_score(PROFILES["didem"]).explain()` çıktısı — motor dökümü olduğu için ondalık ayracı noktadır.*

```
Finansal Sağlık Skoru: 73/100  (Gelişiyor)
  ham=74.7  öncül=46.0  karma=71.9  güven C=0.90  band=71-75
  [ 78.6] Nakit Akışı              19.64 / 25.0 puan
        · Net nakit akışı marjı         89.9  ×0.56   m=+24.9%
        · Gelir istikrarı (CV)          92.5  ×0.12   cv=0.08
        · Kısa vadeli likidite          52.5  ×0.18   18 gün
        · Ödeme zamanlaması             69.6  ×0.07   12 gün taşıma
        · Gelir çeşitliliği             40.0  ×0.07   ana kaynak %84
  [ 87.3] Borç Yükü                17.46 / 20.0 puan
        · Aylık borç servisi / gelir    88.1  ×0.32   DSR=%14.8
        · Kart kullanım oranı           80.0  ×0.18   %34
        · Toplam taahhüt / yıllık gelir  99.2  ×0.22   %5
        · Borcun ortalama faizi        —      (veri yok)
        · Borç trendi (3 ay)            74.3  ×0.12   -6.0%
  [ 60.0] Tasarruf & Güvence       12.01 / 20.0 puan
        · Kasıtlı tasarruf oranı        84.5  ×0.30   %18.6
        · Acil durum fonu               34.1  ×0.31   0.5 ay
        · Tasarruf sürekliliği          66.7  ×0.20   4/6 ay
        · Net varlık                    53.8  ×0.10   yıllık gelirin 0.3 katı
        · Enflasyona karşı koruma      —      (veri yok)
  [ 82.1] Harcama Disiplini        12.31 / 15.0 puan
        · Bütçe uyumu                   93.1  ×0.38   aşım 1,380/20,000
        · Kategori limitlerine uyum     75.0  ×0.20   1/4 aşıldı
        · İsteğe bağlı harcama payı     75.0  ×0.27   %30
        · Kategori oynaklığı            76.4  ×0.15   cv=0.28
  [ 71.5] Hedef Devamlılığı         7.15 / 10.0 puan
        · Hedeflerin ilerleme durumu    62.0  ×0.38   %62
        · Katkı sürekliliği             67.0  ×0.28   %67
        · Plana uyum                    71.4  ×0.17   planın %80'si
        · Hedef gerçekçiliği           100.0  ×0.17
  [ 61.6] Finansal Davranış         6.16 / 10.0 puan
        · Plansız harcama oranı         48.6  ×0.35   %23
        · Duygusal harcama payı         74.1  ×0.25   %10
        · Gece harcama yoğunlaşması     81.3  ×0.20   %11
        · Harcama sonrası pişmanlık     48.9  ×0.20   %28
```
<!-- /OTOMATIK:sm-didem-kirilim -->

Model, mockup'ın kendi *Riskler* ekranında *"Acil Durum Fonu Riski: Yüksek"*
diye işaretlediği zayıflığı bağımsız olarak en düşük alt metrik olarak
buldu (34,1/100). Bu, kalibrasyonun doğru yönde olduğunun iyi bir işareti.

> Mockup 78 gösteriyor, model 73 veriyor. Fark beklenen ve kabul
> edilebilirdir; mockup'taki 78 bir tasarım örneğidir, hesaplanmış bir
> değer değildir. Ürün lansmanı öncesi kalibrasyon gerçek kullanıcı
> verisiyle yapılmalıdır (§15).

---

## 11. Sınır durumları

| Durum | Davranış | Gerekçe |
|---|---|---|
| Gelir = 0, gider var | Marj alt metriği **0** (None değil), maddi olay: "gelir kaydı yok" | Gelirsiz harcama gerçek bir kırılganlıktır; "ölçemedik" demek yanlış olur |
| Gelir = 0, gider = 0 | Marj devre dışı, C düşük | Gerçekten veri yok |
| Gider > gelir | Marj `20×(1+m/0,10)`, −%10'da sıfır | Sürekli iniş, uçurum yok |
| Borç verisi hiç yok | P2 devre dışı, ağırlık yeniden dağıtılır, C düşer | Eksik veri ceza değildir |
| Borç var ama sıfırlanmış | P2 = 100 | Borçsuzluk ödüllendirilir |
| Bütçe kurulmamış | P4'ün 2 alt metriği devre dışı, bileşen çalışmaya devam eder | Bütçesiz kullanıcı disiplinden 0 almaz |
| Hedef yok, gün < 60 | P5 tamamen devre dışı | Yeni kullanıcı muafiyeti |
| Hedef yok, gün ≥ 60 | P5 = 45 | Bulgu, ceza değil |
| Davranış etiketi < %25 | P6 devre dışı | Yetersiz veriyle psikoloji yorumu yapılmaz |
| Kart limiti yok/0 | Kart alt metriği devre dışı | Sıfıra bölme |
| Veri bütünlüğü şüphesi | `C × 0,60`, band genişler, inceleme bayrağı | Suçlu sayılmaz, güven düşer |
| İlk hesaplama (önceki skor yok) | Yumuşatma uygulanmaz | Referans yok |

Yukarıdaki tablo **davranışı** anlatır; aşağıdaki blok o davranışın
**ölçülmüş** hâlidir:

<!-- OTOMATIK:sm-sinir-durumlari -->
*`golden_profiles.veri_sinir_durumlari()`'ndan üretildi. Davranışın gerekçesi yukarıdaki tabloda; buradaki sayılar ölçümdür.*

| Durum | Skor | Band | C | Seviye | Devre dışı |
|---|---|---|---|---|---|
| Sıfır gelir (işsiz) | **56** | 52–60 | 0,69 | Dikkat | — |
| Gider > gelir (negatif marj) | **34** | 30–38 | 0,69 | Riskli | — |
| Hiç borç verisi yok | **67** | 63–71 | 0,70 | Gelişiyor | Borç Yükü |
| Veri bütünlüğü şüphesi | **83** | 76–90 | 0,44 | Dengeli | — |
<!-- /OTOMATIK:sm-sinir-durumlari -->

---

## 12. Sunum kuralları

### Seviyeler

| Skor | Seviye | Mesaj |
|---|---|---|
| 0–39 | Riskli | Bazı alanlarda desteğe ihtiyacın var. Küçük bir adımla başlayabiliriz. |
| 40–59 | Dikkat | Bazı alanlarda kontrol kaybı oluşabilir. Öncelikleri birlikte belirleyelim. |
| 60–74 | Gelişiyor | İyi bir başlangıç var, düzenli devam etmek önemli. |
| 75–89 | Dengeli | Finansal davranışların oldukça dengeli. |
| 90–100 | Güçlü | Harika gidiyorsun, finansal farkındalığın yüksek. |

> **Seviye her zaman gösterilen tam sayıdan türetilir.** İlk
> implementasyonda ondalıklı skor (39,6) aralıkların arasına düşüp son
> banda sarkıyordu: riskli kullanıcıya *"Harika gidiyorsun"* mesajı
> çıkıyordu. `t_level_bands` bu regresyonu kalıcı olarak engeller.

### Metin kuralları

v1'in *"skor asla utandırmamalı"* ilkesi korunur ve şu kurallara çevrilir:

- Skor bir **alan** hakkında konuşur, kullanıcı hakkında değil.
  ✗ *"Savruksun"* → ✓ *"Restoran harcamalarında gelişim alanı var"*
- Düşük skor daima **tek bir sonraki adımla** birlikte gösterilir.
- *"Kötü", "başarısız", "yetersiz"* kelimeleri hiçbir skor metninde geçmez.
- Enflasyon ayrıştırılmadan artış bildirilmez:
  ✓ *"Restoran +%27 (enflasyon %4 → gerçek artış %22)"*
- `C < 0,65` iken skor bant olarak gösterilir ve *"veri arttıkça
  kişiselleşecek"* açıklaması eşlik eder.

---

## 13. AI koç sözleşmesi

**Kural: LLM hiçbir finansal sayı üretmez.**

Mockup'larda AI şunları söylüyor: *"3 ay içinde skorunu 85+ seviyesine
çıkarabilirsin"*, *"78 → 86"*, *"₺7.070 → ₺9.800"*, *"0,5 ay → 1,2 ay"*.
Bu sayılar modelden gelirse uydurulur; finansal bağlamda bu sadece bir bug
değil, kullanıcıya verilmiş yanlış bir taahhüttür.

Doğru akış:

```
1. Kullanıcı: "Tasarrufumu nasıl artırırım?"
2. Orkestratör → skor motoru: mevcut Features + bileşen kırılımı
3. Orkestratör → simulate(): aday senaryolar deterministik hesaplanır
4. LLM'e giden bağlam: yalnızca hesaplanmış sayılar + ton kılavuzu
5. LLM: bu sayıları Türkçe anlatır. Yeni sayı türetmesi YASAK.
6. Çıktı doğrulaması: yanıttaki her sayı bağlamda var mı? Yoksa reddet.
```

`simulate()` çıktısı (`golden_profiles.py`, Didem için):

Mockup'taki *"geçen aya göre +4 puan"* satırı `attribute()`'tan gelir:

<!-- OTOMATIK:sm-simulasyon -->
*`golden_profiles.veri_simulasyon()`'dan üretildi.*

```
Mevcut durum: 72/100  (Gelişiyor)

  Restoran limiti (aylık -600 TL gider)      → 73/100  (+1)
  + Acil durum fonuna aylık 1.500 TL         → 76/100  (+4)
  + Plansız harcama %23 → %15                → 77/100  (+5)

3 ay sonunda beklenen skor: 77 (Dengeli), band 75–79
```

Katkı ayrıştırma (mevcut → plan sonu) — toplam gösterilen farkı **tam olarak** kapatır, artık kalemi yuvarlamadır:

```
   +2.38  Tasarruf & Güvence   60.0 → 73.3
   +1.34  Finansal Davranış   61.6 → 76.4
   +1.02  Harcama Disiplini   82.1 → 89.6
   +0.25  Nakit Akışı   78.6 → 79.7
```
<!-- /OTOMATIK:sm-simulasyon -->

### Guardrail'ler

- Yatırım tavsiyesi verilmez (§14). *"Acil durum fonuna aktar"* ✓ ·
  *"Şu fona yatır"* ✗
- Kesin gelecek vaadi verilmez: *"olur"* değil *"olabilir"*, ve daima
  bandıyla birlikte.
- Skor metinleri §12'deki ton kurallarına tabidir; bunlar hem sistem
  prompt'una hem de bir eval setine yazılmalıdır — yalnızca prompt'a
  yazılırsa üretimde tutmaz.

---

## 14. Uyum notları (Türkiye)

| Konu | Gereklilik |
|---|---|
| **Findeks karışıklığı** | *"Finansal Sağlık Skoru"* kullanıcı kafasında kredi notuyla karışır. Her skor ekranında **"Bu bir kredi notu değildir, kredi başvurularınızı etkilemez"** uyarısı zorunludur |
| **SPK** | AI koç yatırım tavsiyesi veremez. Birikim yönlendirmesi (acil fon, hedef) ile enstrüman tavsiyesi (fon, hisse, kripto) arasındaki sınır UI'da ve prompt'ta net çizilmelidir |
| **KVKK** | Finansal veri hassas biçimde işlenmeli: açık rıza, aydınlatma metni, VERBIS kaydı, saklama süresi, silme hakkı. Skor girdilerinin snapshot'ı da kişisel veridir |
| **BDDK** | Banka verisi otomatik toplanacaksa açık bankacılık çerçevesi; AISP lisansı veya lisanslı aracı gereklidir |
| **Denetlenebilirlik** | Her skor hesabı `model_version` + girdi snapshot + çıktı ile saklanmalıdır. Kullanıcı itirazını yanıtlayabilmek ve modeli güvenle değiştirebilmek için zorunludur |

---

## 15. Yayına alma öncesi yapılacaklar

1. **Kalibrasyon.** Buradaki eşikler finansal literatür ve makul akıl
   yürütmeyle belirlendi, gerçek Nakitio verisiyle değil. İlk 500–1.000
   kullanıcıdan sonra skor dağılımına bakılmalı; hedef, medyanın 60–70
   bandında olmasıdır. Dağılım aşırı sağa yığılırsa `sat`/`concave`
   parametreleri sıkılaştırılır.
2. **`model_version` altyapısı.** Eşik değişikliği herkesin skorunu
   değiştirir. Sürüm geçişi duyurulmalı, eski sürümle hesaplanmış skorlar
   saklanmalıdır.
3. **Kategorizasyon doğruluğu.** Bu modelin kalitesi kategorizasyon
   motorunun kalitesine eşittir. `c_bütünlük` bunu güvene yansıtır ama
   yerine geçmez.
4. **TÜFE entegrasyonu.** N5 olmadan yayına çıkılmamalıdır; Türkiye'de
   enflasyonu ayrıştırmayan bir harcama analizi kullanıcıyı sistematik
   olarak yanlış suçlar.
5. **Ton eval seti.** §12'deki metin kuralları için 50–100 örnekten
   oluşan bir değerlendirme seti hazırlanmalı ve her model/prompt
   değişikliğinde çalıştırılmalıdır.

---

## Ek 0 — Karar günlüğü

| Tarih | Parametre | Eski → Yeni | Gerekçe |
|---|---|---|---|
| 12 Ağu 2026 | `p1.istikrar.w` | 0,20 → **0,13** | Gelir dalgalanmasına karşı tutulan fon zaten P3'te ödüllendiriliyor; 0,20'de aynı risk iki kez cezalandırılıyordu. Serbest çalışan profili 7 puan kaybediyordu |
| 12 Ağu 2026 | `prior.baz` | 50 → **40** | Ölçmediğimiz bir şey hakkında iyimser iddiada bulunmuyoruz; düşük başlangıç ekstre yüklemeyi teşvik eder |
| 12 Ağu 2026 | `prior.min` | 40 → **28** | 40 tabanında "zayıf" (ham 29) ve "kötü" (ham 10) anket cevapları AYNI skoru alıyordu; anket ayırt etmiyordu |
| 12 Ağu 2026 | `p3.guvence.tam_ay` | 6 → **3** | Gösterilen hedefle skorun hedefi aynı olmalı; 6 ay rozete taşındı |
| 12 Ağu 2026 | Yumuşatma çapası | gösterilen → **ölçüm** | Güven artışı finansal değişim değildir; yumuşatılmamalı |
| 12 Ağu 2026 | `s.alpha_maddi` | 0,70 → 0,70 | Değişmedi. 1,0 tek ayda −10 puanlık şok verir; 0,70 iki ayda gerçeğe oturur |
| 12 Ağu 2026 | `s.max_hareket` | 8 → 8 | Değişmedi. Ölçümde hiçbir senaryoda devreye girmediği görüldü — tıkayan EWMA'ydı |
| 12 Ağu 2026 | Bileşen ağırlıkları | değişmedi | ±5 kaydırma hiçbir profilde 2 puandan fazla oynatmıyor; bileşenler korele |

Parametre kararları `engine/tune.py` duyarlılık analiziyle ölçülerek verildi.
Yüksek etkili olanlar beraber ayarlanır; kalanlar varsayılanda bırakılır.

<!-- OTOMATIK:tune-etki -->
*`tune.py` çalıştırılarak üretildi — 109 parametre, 19 golden profil, 7 nokta.*

| Etki | Parametre | Ölçüt |
|---|---|---|
| **Yüksek** | **33** | aralığın uçları arasında en az bir profilin gösterilen skoru ≥3 puan oynuyor |
| Orta | 60 | 1–3 puan |
| Düşük | 12 | <1 puan, ham skorda ölçülebilir |
| **Ölçülemedi** | **0** | hiçbir golden profil o kod yolundan geçmiyor — *etkisiz değil, tetiklenmemiş* |

En etkili parametre: `prior.baz` (16.0 puan, en çok `can` profilinde).
<!-- /OTOMATIK:tune-etki -->

---

## Ek A — Dosya haritası

| Dosya | İçerik |
|---|---|
| `engine/score_engine.py` | Motor. `Features` girdi sözleşmesi, 6 bileşen, güven, yumuşatma, ayrıştırma, simülasyon |
| `engine/golden_profiles.py` | 15 kullanıcı profili (10 senaryo + 5 kapsam), süreklilik testi, simülasyon demosu, sınır durumları, maddi olay testi |
| `engine/params.py` | 96 ayarlanabilir parametre, açıklama ve tarama aralığı |
| `engine/tune.py` | Duyarlılık analizi · `--param` eğrisi · `--set` denemesi |
| `engine/metinler.py` | Kullanıcıya gösterilen tüm metinler |
| `engine/test_invariants.py` | 240 yapısal kontrol: determinizm, monotonluk, süreklilik, eksik veri, güven, sınırlar, seviye bantları, anti-gaming, adalet |

```bash
cd engine && python3 test_invariants.py && python3 golden_profiles.py
```

## Ek B — Açık kararlar

Bunlar modeli bloke etmez ama ürün kararı bekler:

1. **Net worth boyutu eklenecek mi?** Şu an skor akış (flow) odaklı; varlık
   (stock) yalnızca acil fon ve likidite üzerinden giriyor. Konut/araç gibi
   varlıklar hiç sayılmıyor. Kapsam kararı gerekiyor.
2. **Kredi kartı ekstre döngüsü.** Tahakkuk/nakit ayrımı N3'te tanımlı ama
   ekstre kesim tarihi bazlı görünüm ürün tarafında ayrıca kararlaştırılmalı.
3. **Hane halkı / ortak bütçe.** Model tek kullanıcı varsayıyor. Eş/partner
   ortak hesabı yaygın; v2.1 konusu.

### Kapanmış

- ~~**Acil fon hedefi 6 ay mı 3 ay mı?**~~ **12 Ağu 2026'da kapandı:**
  skor **3 ay** üzerinden hesaplanır, 6 ay skorun dışında bir rozettir.
  Gerekçe §6.3'te, karar kaydı Ek 0'da. (Bu madde bir süre "model 6 ay
  alıyor" diyerek açık listede kaldı — oysa `p3.guvence.tam_ay` çoktan
  3'e çekilmişti.)
