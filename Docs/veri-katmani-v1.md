# Nakitio — Veri Katmanı, v1.0

**Durum:** Uygulanmaya hazır teknik şartname
**Kapsam:** Ham banka hareketinden `Features` nesnesine kadar olan her şey
**Referans implementasyon:** `engine/data_model.py`, `engine/normalize.py`
**Testler:** `engine/test_normalize.py` · `engine/fixture_didem.py` (uçtan uca) · `engine/eval_kategori.py` (kategorizasyon ölçümü)
**Devamı:** `Docs/skor-modeli-v2.md`

```
ham veri ─▶ [K1 Normalizasyon] ─▶ [K2 Türetilmiş metrikler] ─▶ Features ─▶ skor
             N1…N9 kuralları        pencereler, oranlar
```

> Bu katman skor motorundan **daha kritiktir.** Motor matematiksel olarak
> kusursuz olsa bile buraya yanlış girdi verilirse çıktı finansal olarak
> anlamsız olur — ve yanlışlığı skor ekranında görünmez.

---

## 1. Neden ayrı bir katman

Skor motoru saf bir fonksiyondur: `Features → skor`. `Features`'ın nereden
geldiği onun sorunu değildir. Bu ayrım bilinçlidir:

- Motor **replay edilebilir** kalır: eski bir `Features` snapshot'ı yıllar
  sonra aynı skoru üretir.
- Normalizasyon kuralları **motor sürümünden bağımsız** evrilebilir.
- Her katman **kendi test setine** sahiptir; bir hatanın hangi katmanda
  olduğu belirsiz kalmaz.

**Üç sürüm ayrı takip edilir:** `PIPELINE_VERSION`, `MODEL_VERSION` ve
`CATEGORY_VERSION`. Bir skor kaydı **üçünü birden** saklamalıdır.

Kategorizasyonun ayrı sürümlenmesi bilinçlidir: N9, hattın geri kalanından
çok daha hızlı evrilir. Sözlüğe bir marka eklemek N1–N8'i etkilemez ama
**herkesin skorunu değiştirir** — "Diğer"e düşen bir harcama kategorize
olunca `e_essential` değişir, o da `ef_months` ve `disc_share` üzerinden
P3/P4'ü oynatır. Tek bir sürüm numarası bu farkı uzlaştıramaz.

`CATEGORY_VERSION` elle bumplanır ama **kendini denetler**: `normalize.
category_fingerprint()` taksonomi + marka sözlüğü + tür sözcükleri + MCC +
özel desenlerin içerik özetini hesaplar, `t_category_version_fingerprint`
onu beyan edilen değere karşı kontrol eder. Sürümü bumplamadan sözlüğü
değiştirirsen test kırılır ve yeni parmak izini söyler — çünkü yalan
söyleyen bir sürüm, olmayandan kötüdür.

---

## 2. Ham veri sözleşmesi

| Varlık | Zorunlu alanlar | Not |
|---|---|---|
| `Account` | `id, type, balance` | `credit_limit`, `statement_day`, `due_day` kartlar için · `is_emergency_fund` acil fon işareti |
| `Transaction` | `id, account_id, ts, amount` | İşaret kuralı aşağıda |
| `InstallmentPlan` | otomatik türetilir (N3) | Banka verisi `installment_index/count` veriyorsa doğrudan |
| `Liability` | `principal_outstanding, monthly_payment` | `days_past_due`, `min_payment_only_months` |
| `Goal` | `target_amount, current_amount, created_at, target_date` | `contribution_history` |
| `Budget` | `category, monthly_limit` | |
| `BehaviorTag` | `txn_id` + en az bir sinyal | `planned`, `emotion`, `satisfaction` |
| `CPISeries` | kategori grubu → aylık endeks | TÜİK'ten beslenir |
| `debt_principal_history` | `[(tarih, anapara)]` | Borç trendi **yalnızca** buradan |

### İşaret kuralı (tek kural, istisnasız)

`amount` **hesap perspektifindendir**: çıkış negatif, giriş pozitif.
Kredi kartı hesabında harcama negatif (borç artışı), ödeme pozitiftir.
Bu kural hiçbir yerde tersine çevrilmez — çevrildiği an mutabakat bozulur.

### Para birimi

Referans implementasyon okunabilirlik için `float` kullanır.
**Üretimde para asla `float` tutulmaz**: kuruş cinsinden tam sayı veya
`Decimal`. Kayan nokta hatası bir finans uygulamasında er ya da geç
mutabakatsızlık üretir.

---

## 3. Kategori taksonomisi

26 kategori. Her biri bir `essential_weight ∈ [0,1]` **ya da `None`** taşır.

### Neden ikili bayrak değil, kesirli ağırlık

"Market" ne tamamen zorunlu ne tamamen isteğe bağlıdır. Temel gıda
zorunludur, atıştırmalık değildir. İkili sınıflandırma bu gri bölgede
**sistematik** hata üretir ve iki yerden birden vurur:

- `e_essential` yanlış çıkar → acil durum fonu hedefi (`ef_months`) yanlış
- `disc_share` yanlış çıkar → harcama disiplini skoru yanlış

Kesirli ağırlık, tek tek işlemleri doğru bilmek zorunda kalmadan
**toplamda** doğru sonuç verir.

```
e_essential = Σ tutar_i × essential_weight[kategori_i]
```

| Ağırlık | Kategoriler |
|---|---|
| 1,00 | kira, aidat, faturalar, sağlık, eğitim, sigorta, vergi |
| 0,95 | çocuk / bakım |
| 0,85 | market, iletişim |
| 0,75 | ulaşım |
| 0,40 | ev / yaşam |
| 0,35 | kişisel bakım |
| 0,25 | giyim |
| 0,15 | restoran & kafe |
| 0,10 | dijital abonelik, elektronik, spor |
| 0,05 | hediye |
| 0,00 | eğlence, tatil, alkol & tütün, şans oyunları |
| **bilinmiyor** | **pazaryeri, faiz & ücret, diğer** |

Ağırlıklar Türkiye hanehalkı tüketim yapısı dikkate alınarak konuldu ve
**gerçek veriyle kalibre edilmelidir**.

### `None` ağırlık: "sıfır" değil, "bilmiyoruz"

Üç kategorinin ağırlığı bilerek `None`'dır ve ortak özellikleri şu:
**işyerini biliyoruz, ne alındığını bilmiyoruz.**

- **pazaryeri** — Trendyol/Amazon tek satırı giyim de olabilir elektronik de
- **faiz & ücret** — tüketim değil, borcun maliyeti
- **diğer** — hiç eşleşmedi

`None ≠ 0` kuralının taksonomi düzeyindeki karşılığıdır. Bunlar
`e_essential` toplamına **girmez**; oran, ağırlığı bilinen harcamadan
tahmin edilip toplama genişletilir.

Naif çözüm — bilinmeyeni toplamdan düşmek — **daha kötüdür**, çünkü
`e_essential` bir PAYDADIR: `ef_months = ef_liquid / e_essential`. Payda
küçülünce acil fon daha uzun dayanıyor GÖRÜNÜR. Gerçek bir kart
ekstresinde ölçüldü: harcamanın %37'si bilinemezken naif çekimserlik
`ef_months`'u 0,74 yerine 1,30 gösteriyordu — bilmemek %76 ödül
kazandırıyordu. Regresyon: `t_essential_estimator_not_biased`.

### Kategorizasyon önceliği

Katmanlı, en özelden en genele:

```
L0   işlem düzeltmesi   user_overrides[txn_id]      → bu TEK işlem
L0'  işyeri hafızası    category_overrides[mid]     → o işyerinin HEPSİ
L1   faiz/ücret         desen                       → tüketim değil
L2   marka sözlüğü      markalar.py (164 zincir)    → zincirler
L3   tür sözcüğü        MERCHANT_RULES (18 kalıp)   → yerel işletmeler
L4   MCC                kart kodu                   → ekstrede genelde YOK
L5   ÇEKİMSER           diger + CategorySource.NONE
```

**İşyeri hafızası kalıcıdır.** Kullanıcı bir kez "AYYILDIZ market'tir"
dediğinde o işyerinin GEÇMİŞ ve GELECEK tüm işlemleri düzelir
(`RawData.category_overrides`). Marka sözlüğünü de ezer — kullanıcı kendi
bağlamını bizden iyi bilir.

**L4 pratikte ölüdür:** kart ekstresinde MCC YOKTUR (gerçek bir dosyada
sıfır eşleşme). Yük tamamen L2+L3'tedir.

### Kanonik merchant kimliği

`_merchant_key()` merchant adını normalleştirir; marka tanınıyorsa
**kanonik anahtar** döner. Bu, hafızanın ve N4/N7'nin temelidir:

```
"9922 - 5650 - A101 C"   ┐
"9946-E325-A101 TUNAL"   ┴→  "a101"
"BIM O831 GORDION POL"   ┐
"BIM T288 YENIMAHALLE"   ┴→  "bim"
```

Marka tanınmazsa mağaza kodu anahtara sızar ve aynı zincirin iki şubesi
iki ayrı işyeri sanılır — bir düzeltme diğerini kapsamazdı.

---

## 4. Katman 1 — Normalizasyon kuralları

Sıra önemlidir: `N9 → tür sınıflandırma → N1 → N2 → N3 → N4 → N7 → N8`.

### N1 — İç transfer eşleştirme

Kullanıcının kendi hesapları arasındaki hareketler gelir ve giderden düşülür.

```
eşleşme koşulu:
  farklı hesap  ∧  0 ≤ Δt ≤ 3 gün
  ∧  |tutar_giriş − tutar_çıkış| ≤ max(1 TL, tutarın %0,5'i)
açgözlü seçim: en küçük Δt, sonra en küçük tutar farkı
her işlem en fazla bir kez eşleşir
```

Tolerans kur farkı ve komisyon içindir. Birikim hesabına giden transfer
ayrıca `SAVINGS_CONTRIB` olarak işaretlenir.

**Atlanırsa:** hesaplar arası para gezdiren kullanıcı hem devasa gelir hem
devasa gider görünür; tasarruf oranı ve nakit akışı marjı anlamsızlaşır.

### N2 — Kredi kartı ödemesi ⚠ en pahalı hata

**İki farklı durum vardır ve karıştırılırsa sonuç felakettir.**

**(a) Kart hesabı BAĞLI.** Harcamalar zaten `purchase` olarak görünüyor.
Ödeme bir gider **değildir**, borç transferidir.

> Sayılırsa her harcama iki kez sayılır: gider iki katına çıkar, tasarruf
> oranı negatife düşer, skor çöker. `test_normalize.t_n2_linked_card_no_double_count`
> bu regresyonu kalıcı olarak engeller — 10.000 TL kart harcaması + 10.000 TL
> ekstre ödemesi, gider olarak **10.000** çıkmalıdır, 20.000 değil.

**(b) Kart hesabı BAĞLI DEĞİL.** Tek görünen şey ödemedir; altındaki
harcamalar görünmüyor. Ödeme gider olarak **sayılmak zorundadır**.

> Sayılmazsa kullanıcının giderinin büyük kısmı yok olur ve skor haksız
> yere yükselir. Bu, sessiz ve tehlikeli bir hatadır — ekranda hiçbir şey
> yanlış görünmez.

(b) durumunda veri kalitesi bayrağı konur ve güven (`C`) düşer: kategori
kırılımı yoktur, davranış analizi yapılamaz.

### N3 — Taksit ayrıştırma

Türkiye'ye özgü ve modelin doğruluğu için kritik. **İki görünüm zorunludur:**

| Görünüm | Taksitli alışverişi nasıl sayar | Nerede kullanılır |
|---|---|---|
| **Nakit** | aylık taksit | nakit akışı marjı, `e_total`, DSR, acil fon ayı |
| **Tahakkuk** | satın alma ayında tam tutar | bütçe uyumu, davranış oranları |

Gerekçe: 12 taksitle alınan 12.000 TL'lik telefon **aylık 1.000 TL'lik bir
gider değil, 11 aylık bir yükümlülüktür**. Ama kullanıcı o kararı o gün
verdi — davranış ölçümü tam tutarı görmelidir.

Yalnızca ilk taksit plan başlatır; sonraki taksitler plana bağlanır ve tekil
gider **sayılmaz** (aksi hâlde aynı alışveriş hem plan hem 12 ayrı gider
olarak iki kez sayılır).

```
installment_monthly   = cari pencereye düşen taksit toplamı
installment_remaining = Σ (kalan taksit sayısı × aylık tutar)   → DSR ve COMMIT
```

### N4 — Yinelenen ödeme tespiti ve amortisman

Periyodu ≥90 gün olan düzenli ödemeler aylara eşit dağıtılır.

```
tespit: aynı merchant_id ∧ tutar ±%15 ∧ medyan aralık ≥ 90 gün
ek kural: sigorta / vergi / eğitim kategorileri tek seferlik de olsa amortize edilir
```

**Atlanırsa:** 12.000 TL kasko primi ödenen ay gider 15.000 TL, ertesi ay
3.000 TL görünür — **3,75 kat** fark. Skor sallanır, kullanıcı sebebini
anlamaz ve skora güveni gider.

### N5 — Enflasyon düzeltmesi

```
reel(tutar, tarih) = tutar × (TÜFE_kategori[bugün] / TÜFE_kategori[tarih])
```

**Kullanım sınırı (önemli):** yalnızca **dönemler arası** karşılaştırmada
kullanılır — gelir oynaklığı, borç trendi, kategori oynaklığı.
**Aynı dönem içi oranlarda kullanılmaz**: pay ve payda zaten aynı
enflasyona maruz kaldığı için oran nötrdür, düzeltme uygulanırsa çift
sayım olur.

**Atlanırsa:** *"Restoran harcaman +%27 arttı"* denir; oysa %4'ü
enflasyondur. Kullanıcı haksız yere suçlanır — ve Türkiye'de bu her ay,
her kategoride olur.

### N6 — Döviz / altın / fon

TRY'ye çevrilir. **Yalnızca katkılar tasarruf sayılır, değerleme farkı
sayılmaz.**

> Altın yükseldi diye kullanıcı "tasarruf etmiş" sayılamaz — bu onun
> davranışı değil, piyasanın hareketidir. Skor, kullanıcının kontrol
> edemediği bir şeye tepki vermemelidir.

**30 gün kuralı:** aynı dönemde geri çekilen transferler net alınır.
"Ayın son günü aktar, 1'inde geri al" oyununu kapatır.

### N7 — İade eşleştirme

Aynı `merchant_id`, ≤90 gün, tutar ≤ harcama → kaynak harcamayı azaltır.

**Atlanırsa:** iade edilen alışveriş hem gider hem gelir olarak durur;
gider şişer, gelir sahte biçimde artar.

### N8 — Aykırı değer

Tek işlem > 3 × aylık gelir → `is_unusual`.

Oran metriklerinden çıkarılır (bir ayda −%1500 marj olmaz), bakiye ve borç
üzerindeki etkisi korunur, kullanıcıya **ayrıca** raporlanır.

Eşik hesabında **medyan** kullanılır (ortalama değil) — aykırı değerin
kendi eşiğini bozmaması için.

**UI karşılığı:** *"Bu ay olağandışı bir işlem tespit ettik; skorunu bundan
arındırdık."*

### N9 — Kategorizasyon

Bölüm 3'te. Modelin kalitesi bu adımın kalitesine eşittir;
`categorized_ratio` bunu güvene yansıtır ama **yerine geçmez**.

---

## 5. Katman 2 — Pencereler

### Karar: kayan 30 günlük pencere, takvim ayı değil

```
W0 = (as_of − 30, as_of]     W1 = (as_of − 60, as_of − 30]     …  W5
```

Skor günlük hesaplanır. Takvim ayı kullanılırsa ayın 1'inde tüm metrikler
sıfırlanır ve skor her ay başı yapay bir sıçrama yapar. Kullanıcıya
gösterilen "Temmuz 2026" etiketi ayrı bir **sunum** meselesidir.

### Boş pencere ≠ sıfır harcama

`active_windows()` yalnızca içinde gerçekten veri olan pencereleri döndürür.

> Bu, ilk implementasyonda yakalanan gerçek bir hataydı. 5 aylık bir
> kullanıcıda 6. pencere boştur; boş pencere "o ay sıfır harcadı" sayılınca
> tamamen sabit giden 700 TL'lik telefon faturası bile **cv = 0,45** ile
> "oynak" işaretleniyordu. Aynı şekilde her ay biriktiren kullanıcı
> **hiçbir zaman 6/6 alamıyordu.** Eksik veriyi cezaya çevirmek, skor
> modelinin 3 numaralı tasarım ilkesinin doğrudan ihlalidir.
> Regresyon: `test_normalize.t_short_history_not_penalized`

---

## 6. `Features` eşleme tablosu

| Alan | Pencere | Görünüm | Hesap |
|---|---|---|---|
| `i_net` | W0–W2 | — | gelir toplamlarının **medyanı** |
| `i_cv` | W0–W5 | reel | std/ort, <3 pencere varsa `None` |
| `i_primary_share` | W0–W2 | — | en büyük kaynağın payı |
| `e_total` | W0–W2 | **nakit** | gider toplamlarının medyanı |
| `e_essential` | W0–W2 | **nakit** | `Σ tutar × essential_weight` medyanı |
| `liquid_balance` | anlık | — | vadesiz + nakit hesap bakiyeleri |
| `s_deliberate` | W0–W2 | — | birikim hesaplarına **net katkı** medyanı |
| `ef_liquid` | anlık | — | `is_emergency_fund` hesapların bakiyesi |
| `s_consistency_months` | aktif pencereler | — | pozitif ay sayısı, 6'lık ölçeğe yansıtılır |
| `debt_principal` | anlık | — | krediler + döner kart borcu (**taksit hariç**) |
| `debt_monthly_service` | anlık | — | `Liability.monthly_payment` toplamı |
| `installment_monthly` / `_remaining` | W0 / gelecek | — | aktif planlardan |
| `card_balance` / `card_limit` | anlık | — | yalnızca kullanım oranı alt metriği için |
| `debt_trend_3m` | 3 pencere | — | **yalnızca ölçülmüş anapara geçmişinden**, yoksa `None` |
| `budget_planned` / `_overrun` | W0 | **tahakkuk** | kategori bazlı aşım toplamı |
| `limit_breached` | W0 | tahakkuk | **%5 toleransla** |
| `cat_volatility` | aktif pencereler | **nakit** | kategori CV ortalaması, filtreli |
| `goal_*` | anlık | — | `Goal` kayıtlarından |
| `beh_*` | W0 | **tahakkuk** | Bölüm 7 |
| `categorized_ratio` | W0 | tahakkuk | kategorize TL / toplam TL |

### Neden `debt_principal` ve `installment_remaining` ayrı

`COMMIT = (debt_principal + installment_remaining) / (i_net × 12)`

İkisi çakışmamalıdır. `debt_principal` krediler ve **döner** kart borcunu
içerir; taksit planları ayrı tutulur. `card_balance` yalnızca kullanım
oranı (limite yakınlık) sinyali için kullanılır — o **farklı bir olgudur**,
`COMMIT`'e girmez.

### `limit_breached` toleransı

Limiti 5 TL aşmak "ihlal" sayılmaz. İkili sayım, tam da skor modelinden
ayıkladığımız uçurumun kendisidir; aşımın **büyüklüğü** zaten
`budget_overrun` ile sürekli olarak ölçülüyor.

### `cat_volatility` filtreleri

```
· "diğer" kategorisi hariç      → bir kategori değil, çöp kutusudur;
                                   varyansı kategorizasyon kalitesinin
                                   artefaktıdır, kullanıcı davranışının değil
· aktif pencerelerin ≥%75'inde görünmeli
· toplam harcamanın ≥%2'si olmalı
· NAKİT görünüm kullanılır      → oynaklık harcama RİTMİDİR; tahakkuk
                                   kullanılırsa 4 taksitli tek bir alışveriş
                                   o kategoriyi yapay olarak oynak gösterir
```

### `debt_trend_3m` neden tahmin edilmiyor

İlk implementasyonda bu, *kart harcaması − kart ödemesi* akışından tahmin
ediliyordu. Sonuç saçmaydı: limiti içinde normal dönen bir kartta bile
**"borç %88 arttı"** çıkıyor ve alt metrik sıfırlanıyordu — çünkü aynı ay
içinde harcanıp ödenen tutar net borç değişimi değildir.

Ölçülmüş anapara geçmişi yoksa alt metrik devre dışı bırakılır.
**Uydurulmuş bir sinyal, eksik sinyalden kötüdür.**

---

## 7. Davranış metrikleri — tahmin edici

Plansız/duygusal bilgisi **yalnızca etiketlenmiş** işlemler için gözlenebilir.
Payda olarak doğrudan toplam harcamayı almak, etiketleme kapsamı düştükçe
plansız harcamayı **sistematik olarak eksik ölçer**: kapsamı %36 olan bir
kullanıcı, gerçekte savruk olsa bile "disiplinli" görünür.

Doğru tahmin edici iki varsayıma dayanır:

1. Zorunlu harcama tanımı gereği planlıdır (kira plansız olmaz).
2. Etiketlenmiş harcamada gözlenen oran, isteğe bağlı harcamanın tamamı
   için geçerlidir.

```
imp_rate = (plansız_etiketli / etiketli) × isteğe_bağlı_pay
emo_rate = (duygusal_etiketli / etiketli) × isteğe_bağlı_pay
night_conc = gece_harcaması / toplam          ← düzeltme YOK
regret_rate = düşük_memnuniyet / puanlanan
```

`night_conc` bu düzeltmeye tabi değildir: saat bilgisi **her** işlemde
vardır, örnekleme yanlılığı yoktur, doğrudan ölçülür.

Kapsam %25'in altındaysa davranış bileşeni tamamen devre dışı bırakılır
(skor motoru, `BEH_MIN_COVERAGE`).

---

## 8. Uçtan uca doğrulama

`python3 engine/fixture_didem.py`

Mockup kullanıcısının (Didem) 5 aylık **281 ham işlemi** sentetik olarak
üretilir ve tüm hattan geçirilir. Fixture her N kuralını bilerek tetikler.

```
NORMALİZASYON TANILARI
  N9 kategorizasyon : 233 kural · 48 varsayılan
  N1 iç transfer    : 10 çift eşleşti
  N2 kart ödemesi   : bağlı karta 5 ödeme gider dışı bırakıldı
  N3 taksit planı   : 2 plan
       · elektronik   6 × 900 TL (kalan 3.600 TL)
       · giyim        4 × 900 TL (kalan 2.700 TL)
  N4 amortisman     : 1 seri → 12 sanal kayıt (kasko 8.400 → 700/ay)
  N7 iade           : 1/1 eşleşti
  N8 aykırı değer   : 1 işlem işaretlendi (95.000 TL toplu hakediş)

TÜRETİLMİŞ METRİKLER
  gelir (3 ay medyan)      27.890 TL      DSR                    %21,5
  gider (nakit görünüm)    19.463 TL      aylık taksit / kalan   1.800 / 6.300 TL
  zorunlu gider            11.480 TL      kart kullanımı         %34
  nakit akışı marjı        %30,2          bütçe aşımı            3.290 / 14.600 TL
  kasıtlı tasarruf          5.303 TL      kategori oynaklığı     0,201
  acil durum fonu           0,65 ay       davranış kapsamı       %55
  tasarruf sürekliliği      6/6 ay        kategorize oran        %88

SKOR
  Finansal Sağlık Skoru: 75/100  (Dengeli)
  ham=76,4  öncül=46,0  karma=75,6  C=0,98  band=73-77
```

**Sonuç 75.** Elle kurulmuş golden profil (`golden_profiles.didem`) **73**
verir — ve bu ikisinin **aynı olması beklenmez.** İki profil aynı
bakiyeleri ve onboarding cevaplarını paylaşır, ama akış metrikleri 281
işlemden türetildiği için ayrışır: golden profilin hiç taksiti yokken
fixture'ın iki aktif planı vardır.

Fixture'ın doğruladığı şey determinizm değil **hattın bütünlüğüdür**: bu
kadar farklı bir yoldan gelen iki hesabın 2 puan içinde buluşması,
N1–N9'un hiçbirinin sessizce atlanmadığı anlamına gelir. Tek başına N2
çift sayımı gideri ₺19.463'ten ₺29.978'e çıkarırdı.

### Fixture'ın ortaya çıkardığı bir ürün bulgusu

Mockup'ın *Gider Kategorileri* listesinde **konut/kira yoktur**
(market, yeme-içme, ulaşım, alışveriş, faturalar, diğer). Türkiye'de bu
gerçekçi değildir ve doğrudan iki metriği bozar:

- `e_essential` sistematik olarak düşük çıkar → `ef_months` yapay yüksek
- `disc_share` yapay yüksek çıkar → harcama disiplini skoru haksız düşük

Kategori listesine konut eklenmelidir.

---

## 9. Test kapsamı

`python3 engine/test_normalize.py` — 48 kontrol

| Test | Neyi garanti eder |
|---|---|
| `t_n1_internal_transfer` | Transfer hem gelirden hem giderden düşer, birikim akışına yazılır |
| `t_n1_no_false_match` | 3 günden uzak aralık eşleşmez |
| `t_n2_linked_card_no_double_count` | **Çift sayım regresyonu** — 10.000, 20.000 değil |
| `t_n2_unlinked_card_is_proxy` | Bağlantısız kart ödemesi gider olarak sayılır |
| `t_n3_installments` | Plan doğru, kalan taahhüt doğru, iki görünüm farklı |
| `t_n3_followups_not_double_counted` | Sonraki taksitler tekil gider sayılmaz |
| `t_n4_amortization` | Yıllık prim 12'ye bölünür; amortismansız 3,75× fark |
| `t_n5_inflation` | Düzeltme yönü ve kategori bazlılığı |
| `t_n6_valuation_not_savings` | Değer artışı tasarruf sayılmaz |
| `t_n7_refund` | İade harcamayı netler, gelir sayılmaz |
| `t_n8_outlier` | Aykırı değer medyan geliri bozmaz |
| `t_n9_categorization` | Öncelik zinciri: kullanıcı > kural > MCC > diğer |
| `t_essential_weighting` | Kesirli ağırlık doğru toplanır |
| `t_short_history_not_penalized` | **Boş pencere regresyonu** |
| `t_end_to_end_*` | Determinizm ve makullük |

---

## 10. Üretime geçmeden önce

1. **Kategorizasyon motoru.** Buradaki 22 kurallık tablo sözleşmeyi
   gösterir, ürünü değil. Gerçek çözüm: merchant normalleştirme + kural
   motoru + ML fallback + **kullanıcı düzeltmesinin geri beslenmesi**.
   Hedef doğruluk %90+; `categorized_ratio` bunu ölçer ve güvene yansıtır.

2. **TÜİK TÜFE entegrasyonu.** N5 stub'la çalışıyor. Kategori grubu →
   COICOP eşlemesi kurulmalı ve aylık beslenmelidir.

3. **Ekstre anlık görüntüleri.** `debt_principal_history` olmadan borç
   trendi alt metriği hep kapalı kalır (20 puanlık bileşenin %15'i).
   Aylık bakiye snapshot'ı saklanmalıdır.

4. **Para tipi.** `float` → kuruş cinsinden `int` veya `Decimal`.

5. **Kullanıcı düzeltmelerinin kalıcılığı.** Bir merchant için yapılan
   düzeltme, aynı merchant'ın gelecekteki işlemlerine uygulanmalıdır.

6. **`Features` snapshot'ı saklanmalı.** Skor kaydı `PIPELINE_VERSION` +
   `MODEL_VERSION` + girdi snapshot'ı ile birlikte tutulur. Kullanıcı
   itirazını yanıtlayabilmek ve modeli güvenle değiştirebilmek için zorunlu.

7. **Hesap türü tespiti.** Fixture hesap türlerini bilir. Gerçekte açık
   bankacılıktan gelen hesapların türü her zaman net olmayabilir; yanlış
   tür N1/N2'yi bozar.

## Ek — Dosya haritası

| Dosya | İçerik |
|---|---|
| `engine/data_model.py` | Ham veri sözleşmesi, kategori taksonomisi |
| `engine/normalize.py` | N1–N9 + `derive_features()` |
| `engine/fixture_didem.py` | 281 işlemlik uçtan uca fixture |
| `engine/test_normalize.py` | 48 kontrol |

```bash
cd engine && python3 test_normalize.py && python3 test_invariants.py && python3 fixture_didem.py
```
