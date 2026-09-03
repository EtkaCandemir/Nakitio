# DECISIONS.md — Karar Günlüğü

Bu projedeki her önemli karar, **gerekçesiyle ve ölçülen etkisiyle**.
Altı ay sonra "bunu neden böyle yaptık" sorusunun cevabı burada.

Değişmeyen kararlar da yazılıdır — bir şeyi değiştirmemek de karardır.

---

## 1. Ürün kararları

### Ü1 — Veri kaynağı: ekstre yükleme

**Alternatifler:** açık bankacılık (BDDK/AISP lisansı), manuel giriş,
SMS/bildirim parse (Android'e özgü).

**Karar:** ekstre yükleme + cari dönem için hızlı ekleme (hibrit).

**Gerekçe:** hem iOS hem Android'de çalışır, lisans gerektirmez, banka
doğruluğunda veri verir. Manuel giriş terk oranı yüksek; açık bankacılık
aylar sürer.

**Sonuçları:**
- Cari ay hiçbir zaman tam değil → ana sayfa iki bölgeye ayrıldı
- Davranış etiketi toplu gelemez → çıkarım katmanı gerekti (Ü2)
- Kart ekstresi dönem sonu borcu verir → `debt_principal_history` doldu
- Taksitler ekstrede açık yazar → N3 sorunsuz çalışıyor

### Ü2 — Davranış: çıkarım + triyaj

**Problem:** ekstrede "plansızdı" bilgisi yok. Kimse 200 işlemi geriye
dönük etiketlemez. P6 bileşeni ve Davranış Analizi ekranı ölür.

**Karar:** iki kademeli ölçüm. Çıkarım taban, etiket kalibre eder.

**Ölçülen etki:** etiketsiz durumda bile P6 açık kalıyor (82,8/100).
Eskiden tamamen kapanıyordu.

**Dürüstlük sınırı:** plansızlık iyi çıkarılır, **duygu çıkarılamaz**.
Duygu tahmini bilinçli olarak zayıf; UI'da iddia değil soru olarak
sunulur. Bu, Davranış Analizi ekranını pasif rapordan etkileşimli
yüzeye çevirdi — gösterirken etiket topluyor.

### Ü3 — Ana sayfa: kapanan / devam eden dönem ayrımı

Ekstre 18'inde kesiliyorsa 31'inde son 13 günün verisi yok. Mockup'ın
*"Bu ay tasarruf oranı %26"* kartı bu modelde yalan söyler.

**Karar:** iki bölge. Kapanan dönem otoriter, devam eden dönem açıkça
kısmi ve skoru etkilemiyor.

### Ü4 — Acil fon: 3 ay skor + 6 ay rozet

**Karar (12 Ağu 2026):** skor 3 ay üzerinden. 6 ay skorun dışında rozet.

**Gerekçe:** gösterilen hedefle skorun hedefi aynı olmalı; aksi hâlde
3 aylık hedefe ulaşan kullanıcı tam puan alamaz ve kale direği kaymış
gibi hisseder. Ayrıca 6 ay uluslararası standarttır ama düşük enflasyonlu
ülkeler için üretilmiştir.

**Ölçülen etki:** 6 → 3 geçişi toplam skorları 0–2 puan oynatıyor. Ucuz.

**Not:** bu finansal tavsiye sınırında bir karar. Kullanıcı bilinçli
verdi; UI'da gerekçe kullanıcıya da gösteriliyor.

### Ü5 — Bilgi mimarisi: 4 sekme + merkez eylem

Mockup'larda iki farklı alt menü vardı.

**Karar:** `Ana Sayfa / Analiz / ➕ / Planlar / Koç`. Profil avatara,
İşlemler Analiz altına, Araçlar MVP dışına.

**Marka:** mor birincil, yeşil semantik. İki maskot olmaz.

### Ü6 — Onboarding: 5 soru, genişletilmiyor

Proje sahibinin kararı (12 Ağu 2026): *"Yok sade kalsın."*

Modelle uyumlu — anket yalnızca öncül üretir ve etkisi veri geldikçe
sönümlenir.

---

## 2. Model mimarisi kararları

### M1 — Üç formül yerine tek formül + güven

**v1'in sorunu:** gün 30'da formül tamamen değişiyor, skor sıçrıyordu.
Ölçüldü: her şeyi doğru yapan kullanıcı gün 30'da 87,5 alıp gün 31'de
~55'e düşüyordu. **Tek gecede 32 puan**, hem de en çok emek vermiş
kullanıcıda.

**Karar:**
```
S_karma = C × S_ham + (1 − C) × S_öncül
```
Aşamalar artık kod değil, sunum etiketi.

**Doğrulama:** gün 28 → 30 → 31 boyunca skor 55, 55, 55.

### M2 — Bileşenler: 6'lı yapı

v1 dokümanında 5, mockup'ta 6 bileşen vardı. Mockup'ınki daha doğruydu.

**Karar:** Nakit 25 · Borç 20 · Tasarruf 20 · Disiplin 15 · Hedef 10 ·
Davranış 10.

**v1'in en büyük hatası:** `Harcama Kontrolü` (gider/gelir) ve `Tasarruf`
(tasarruf/gelir) matematiksel olarak aynı değişkendi
(`tasarruf/gelir = 1 − gider/gelir`). 100 puanın 50'si tek olguyu iki kez
ölçüyordu. Düzeltme: tasarruf artık **kasıtlı transfer**, artık bakiye
değil.

### M3 — Sürekli fonksiyonlar

v1'de basamak tabloları vardı: gider/gelir %70,0 → 25 puan, %70,1 → 20
puan. ₺28.450 gelirde **₺28 fazla harcama 5 puan** kaybettiriyordu.

**Karar:** `lin`, `sat`, `concave`. Aynı geçiş artık 0,01 puan.

### M4 — Davranış metrikleri oran bazlı

v1'de risk puanları olay başına toplanıyordu. Saat 23:00'te stresliyken
yapılan tek bir plansız online alışveriş 16 risk üretiyor, 15 puanlık
bileşeni 4'e düşürüyordu. 50 TL'lik alışveriş 5.000 TL'lik ile aynı ceza.

**Karar:** hepsi tutar bazlı oran. Tek işlem bileşeni patlatamaz.

### M5 — Engagement skordan çıkarıldı

v1'de görev başına +2 sağlık puanı vardı. Ayda 30 görev = 60 puan.
Kullanıcı finansal durumunu değiştirmeden skorunu şişirebiliyordu.

**Karar:** engagement `Features`'ta alan olarak yok. Yapısal olarak
engellendi (`t_no_engagement_inputs`).

**Daha derin gerekçe:** engagement senin retention metriğin, kullanıcının
finansal sağlığı değil.

### M6 — Yumuşatma güven değişimini muaf tutar

**Karar (12 Ağu 2026):** yumuşatmanın çapası önceki dönemin gösterilen
skoru değil, **ölçümünün bugünkü güvenle** değerlendirilmiş hâli.

**Gerekçe:** yumuşatma kullanıcının *finansal durumunun* skoru hızlı
oynatmasını engellemek içindir. Bizim *ölçümümüzün* düzelmesi onun
durumundaki bir değişiklik değil, bizim hatamızın düzelmesidir.

**Ölçülen etki** (sağlıklı kullanıcı, gerçek ham 92):

| Aşama | Eski | Yeni |
|---|---|---|
| Gün 0 | 34–58 | 34–58 |
| 1. ekstre | 50–60 | **62–72** |
| 3. ekstre | 70 | 82 |
| 6. ekstre | 79 | 88 |

Eskiden en iyi tahmin 72 iken 55 gösteriliyordu — 17 puan saklanıyordu.

### M7 — Ceza çarpanları bileşen seviyesinde

Alt metriğe değil bileşen skoruna uygulanır, böylece ağırlıkla doğru
ölçeklenir. v1'de "sadece asgari ödeme" −5 puandı — Türkiye'de kronik
borç sarmalının en güçlü sinyali için çok hafif.

---

## 3. Parametre kararları (12 Ağu 2026)

`tune.py` duyarlılık analiziyle ölçülerek verildi; yüksek etkili olanlar
beraber ayarlandı, kalanlar varsayılanda bırakıldı. Güncel etki dağılımı
`Docs/skor-modeli-v2.md` §14'te `tune.py`'den ÜRETİLİR — buraya sayı
yazılmaz, çünkü golden profil kümesi büyüdükçe dağılım değişir (nitekim
"27" rakamı profil sayısı 10'dan 15'e çıkınca sessizce bayatlamıştı).

| Parametre | Eski → Yeni | Ölçülen etki | Gerekçe |
|---|---|---|---|
| `p1.istikrar.w` | 0,20 → **0,13** | zeynep 79 → 82 | Gelir dalgalanmasına karşı tutulan fon zaten P3'te ödüllendiriliyor. 0,20'de **aynı risk iki kez** cezalandırılıyordu |
| `prior.baz` | 50 → **40** | orta cevap 56 → 46 | Ölçmediğimiz şey hakkında iyimser iddiada bulunmuyoruz; düşük başlangıç ekstre yüklemeyi teşvik eder |
| `prior.min` | 40 → **28** | zayıf/kötü ayrıştı | 40 tabanında "zayıf" (ham 29) ve "kötü" (ham 10) **aynı skoru** alıyordu; anket ayırt etmiyordu |
| `p3.guvence.tam_ay` | 6 → **3** | 0–2 puan | Gösterilen hedefle skorun hedefi aynı olmalı (Ü4) |
| Yumuşatma çapası | gösterilen → **ölçüm** | 1. ekstrede +12 puan | M6 |
| `s.alpha_maddi` | 0,70 → **0,70** | — | 1,0 tek ayda −10 puanlık şok verir; 0,70 iki ayda gerçeğe oturur. Etik karar |
| `s.max_hareket` | 8 → **8** | — | Ölçümde **hiçbir senaryoda devreye girmediği** görüldü; tıkayan EWMA'ydı. Önerilen 10'a çıkarma geri çekildi |
| Bileşen ağırlıkları | **değişmedi** | ±5 → max 2 puan | Bileşenler korele; ağırlık kaydırmak toplamı oynatmıyor. Sezgisel olarak en önemli görünen, pratikte en az önemli |

### Duyarlılık sıralaması (ilk 10)

| Parametre | Aralık | Azami oynama |
|---|---|---|
| `s.alpha_maddi` | 0,4–1,0 | 14 puan |
| `prior.baz` | 40–60 | 13 puan |
| `s.max_hareket` | 3–20 | 9 puan |
| `p2.weight` | 10–30 | 8 puan |
| `p3.weight` | 10–30 | 7 puan |
| `p1.istikrar.w` | 0,05–0,35 | 7 puan |
| `p4.weight` | 5–25 | 5 puan |
| `p1.marj.k` | 0,06–0,25 | 5 puan |
| `p4.istege_bagli.yuz` | 0,1–0,35 | 5 puan |
| `p5.hedefsiz_puan` | 0–70 | 5 puan |

### Ölçüm metodolojisi kararları

**Sıfır oynama ≠ önemsiz.** İlk analizde 16 parametre "etkisiz"
görünüyordu; aslında golden profillerden hiçbiri o kod yolundan
geçmiyordu. `c.statement_tavan` — ürünün ana veri kaynağı — ölçülemiyordu.
5 kapsam profili eklendi (emre, hakan, sibel, tolga, nur).

**Sadece gösterilen skora bakmak yetmez.** `p6.min_kapsam` bileşeni
tamamen kapatıyor (ham 84,87 → 83,78) ama yumuşatma ve yuvarlama yutuyor.
Ham skor, bant genişliği ve etiket değişimi de ölçülmeli.

**Bazı parametreler skoru değil sunumu etkiler.** `s.band_k` bandı ±21,
`stage.saglik_C` 7 etiket kayması. Ayrı kategori.

---

## 4. Veri katmanı kararları

### D1 — Kesirli `essential_weight`

İkili bayrak değil `[0,1]` ağırlık. "Market" ne tamamen zorunlu ne
tamamen isteğe bağlıdır; ikili sınıflandırma gri bölgede sistematik hata
üretir ve hem `ef_months` hem `disc_share`'i bozar.

### D2 — Nakit ve tahakkuk iki ayrı görünüm

Taksitli alışveriş nakit görünümde aylık taksit, tahakkuk görünümde satın
alma ayında tam tutar. Karar o gün verildi ama para aylara yayılıyor.

### D3 — Kayan 30 günlük pencere, takvim ayı değil

Skor günlük hesaplanır. Takvim ayı kullanılırsa ayın 1'inde tüm metrikler
sıfırlanır ve skor yapay sıçrama yapar.

### D4 — Borç trendi tahmin edilmez

Yalnızca ölçülmüş anapara geçmişinden. İşlem akışından türetme denendi ve
limiti içinde dönen bir kartta bile "borç %88 arttı" üretti.
**Uydurulmuş sinyal, eksik sinyalden kötüdür.**

### D5 — Güven kademesi tavandır, taban değil

`max(bağlı_oran, kademe)` yazılmıştı; kaynağı "ekstre" olan kullanıcı
hesapları "bağlı" işaretli olduğu için `c_cover = 1,0` alıyordu.
Kaynak neyse kapsamı o belirler.

### D6 — Davranış oranlarında tahmin edici

Payda olarak doğrudan toplam harcamayı almak, etiketleme kapsamı
düştükçe plansız harcamayı sistematik olarak **eksik ölçer**.

```
oran = (plansız_etiketli / etiketli) × isteğe_bağlı_pay
```

İki varsayıma dayanır: zorunlu harcama tanımı gereği planlıdır; etiketli
örnekteki oran isteğe bağlı harcamanın tamamı için geçerlidir.

Gece yoğunlaşması bu düzeltmeye **tabi değildir** — saat her işlemde
vardır, örnekleme yanlılığı yok.

---

## 5. Koç kararları

### K1 — LLM sayı üretmez

Mockup'larda koç *"3 ay içinde 85+"*, *"₺7.070 → ₺9.800"* gibi kesin
sayılar veriyor. Bunlar modelden gelirse uydurulur — finansal bağlamda
bu bug değil, yanlış taahhüt.

**Karar:** deterministik simülasyon → LLM anlatır → guard doğrular.

### K2 — Prompt bir rica, guard bir garanti

Kuralların büyük kısmı hem prompt'ta hem guard'da. Bilinçli tekrar:
yalnızca prompt'a yazılan kural uzun konuşmalarda kayar; yalnızca guard'a
yazılan sürekli ret üretir.

### K3 — Guard reddetmeyi engellememelidir

"Yatırım tavsiyesi veremem" cümlesi `investment_advice` kalıbına
takılıyordu. Guard koçu **doğru davrandığı için** cezalandırıyordu.
SPK sınırı tam olarak reddedebilmeyi gerektirir.

### K4 — Doğrulayıcı aşırı katı olmamalı

`7.6` gibi İngilizce ondalık iki ayrı sayıya bölünüp doğru yanıtı
reddediyordu. **Aşırı katı doğrulayıcı, hiç olmaması kadar zararlıdır.**

### K5 — Araç metinlerindeki sayılar da deftere yazılır

*"acil durum fonu 1 aydan az"* içindeki `1` kayıtlı değildi; koç kendi
araç çıktısını aktardığında halüsinasyon sanılıyordu.

---

## 6. Reddedilen / ertelenen

| Öneri | Durum | Neden |
|---|---|---|
| `s.max_hareket` 8 → 10 | **Geri çekildi** | Ölçümde hiç devreye girmiyor; yanlış düğme |
| Bileşen ağırlıklarını değiştirme | Ertelendi | ±5 kaydırma max 2 puan oynatıyor |
| Onboarding'i genişletme | Reddedildi | Proje sahibi kararı; modelle de uyumlu |
| Net worth boyutu | v2.1 | Skor akış odaklı; varlık yalnızca acil fon ve likidite üzerinden |
| Hane halkı / ortak bütçe | v2.1 | Model tek kullanıcı varsayıyor |
| OCR (taranmış ekstre) | v1.1 | Metin katmanlı PDF öncelikli |
| `infer.cikarim_kapsam` ayarı | Açık | Ölçülemiyor; kapsam eşiğini tetikleyen profil yok |

---

## 7. Açık bırakılanlar — bilinçli

| Konu | Neden açık | Ne zaman kapanır |
|---|---|---|
| **Parametre kalibrasyonu** | Gerçek veri yok | İlk 500–1.000 kullanıcı; hedef medyan 60–70 |
| **Banka profilleri** | Gerçek örnek dosya yok | Her hedef bankadan ekstre örneği toplanınca |
| **LLM entegrasyonu** | Sıra gelmedi | Backend'den sonra |
| **Üretim backend'i** | Sıra gelmedi | — |
| **TÜİK TÜFE beslemesi** | Stub çalışıyor | Yayın öncesi zorunlu |
| **Para tipi (`float` → `Decimal`)** | Prototip | Üretim öncesi |
| **Gün-0 metinleri** | Yazıldı | ✓ |
| **Görev/seri mekaniği** | Aylık ritme uyarlanmadı | Ürün kararı bekliyor |
