# ARCHITECTURE.md — Katman Mimarisi

Giriş noktası: `CLAUDE.md`. Bu dosya **katmanların nasıl bağlandığını**
ve her modülün tam sorumluluğunu anlatır.

---

## 1. Yedi katman

```
┌─ K0  HAM VERİ ────────────────────────────────────────────────────┐
│  Banka ekstresi (CSV / metin katmanlı PDF)                        │
│  → statement_ingest.py                                            │
└───────────────────────────────────────────────────────────────────┘
                              │  ParsedStatement
                              ▼
┌─ K1  NORMALİZASYON ───────────────────────────────────────────────┐
│  N1 iç transfer · N2 kart tekilleştirme · N3 taksit                │
│  N4 amortisman  · N5 enflasyon        · N6 döviz/altın             │
│  N7 iade        · N8 aykırı değer     · N9 kategorizasyon          │
│  → normalize.py                                                    │
└───────────────────────────────────────────────────────────────────┘
                              │  Ledger
                              ▼
┌─ K2  TÜRETİLMİŞ METRİKLER ────────────────────────────────────────┐
│  Kayan 30 günlük pencereler, medyanlar, oranlar                   │
│  Davranış çıkarımı → behavior_infer.py                            │
│  → normalize.derive_features()                                     │
└───────────────────────────────────────────────────────────────────┘
                              │  Features   ← SÖZLEŞME SINIRI
                              ▼
┌─ K3  SKOR MOTORU ─────────────────────────────────────────────────┐
│  6 bileşen · sürekli fonksiyonlar · güven harmanlaması             │
│  yumuşatma · katkı ayrıştırma · simülasyon                         │
│  → score_engine.py  (SAF, params.py'ye bağımlı)                    │
└───────────────────────────────────────────────────────────────────┘
                              │  ScoreResult
                    ┌─────────┴─────────┐
                    ▼                   ▼
┌─ K4  KOÇ ──────────────┐   ┌─ K5  EKRAN VERİSİ ───────────────────┐
│  8 araç + NumberLedger │   │  3 durum × 6 ekran                    │
│  → coach_tools.py      │   │  metinler.py'den metin                │
│  guard: sayı + içerik  │   │  → screen_data.py                     │
│  → coach_guard.py      │   └───────────────────────────────────────┘
└────────────────────────┘                   │
                    │                        ▼
                    └──────────▶  ┌─ K6  ARAYÜZ ────────────────────┐
                                  │  app/server.py + app/web/        │
                                  │  PROTOTİP — sevk edilmez         │
                                  └──────────────────────────────────┘
```

### Katmanlar arası tek sözleşme: `Features`

`Features` (score_engine.py) bu mimarinin bel kemiğidir. K2'nin çıktısı,
K3'ün tek girdisidir. Bu ayrım bilinçlidir:

- **Motor replay edilebilir kalır.** Eski bir `Features` snapshot'ı yıllar
  sonra aynı skoru üretir.
- **Normalizasyon kuralları motor sürümünden bağımsız evrilir.**
- Her katman kendi test setine sahiptir; bir hatanın hangi katmanda
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

## 2. Modül sorumlulukları

### Yaprak modüller (hiçbir şeye bağımlı değil)

#### `params.py`
Modelin **96 ayarlanabilir sayısı**. `P` (değerler) ve `M` (açıklama +
tarama aralığı) sözlükleri. Import anında `check()` çalışır ve şunları
doğrular: her değerin açıklaması var mı, bileşen ağırlıkları 100 ediyor
mu, alt ağırlık grupları 1,0 ediyor mu.

**Kural:** kodda gömülü sayısal literal kalmaz. Motor bu tablodan okur ve
**çalışma anında** okur — import anında yakalanan sabit bırakma, yoksa
`tune.py` parametreyi değiştirdiğinde etkilemez.

#### `data_model.py`
Ham veri sözleşmesi: `Account`, `Transaction`, `InstallmentPlan`,
`Liability`, `Goal`, `Budget`, `BehaviorTag`, `CPISeries`, `RawData`.

26 kategorilik taksonomi. Her kategorinin `essential_weight ∈ [0,1]`
değeri var — ikili bayrak değil, çünkü "market" ne tamamen zorunlu ne
tamamen isteğe bağlıdır.

#### `metinler.py`
Kullanıcıya gösterilen her cümle. Gün-0 çerçevesi, güvence kademeleri,
kapsam uyarıları, dönem etiketleri. Ton kurallarına tabidir ve gözden
geçirilebilir olmalıdır.

---

### Veri katmanı

#### `statement_ingest.py`
**Profil tabanlı** ekstre ayrıştırma. `BankProfile` bir veri kaydıdır;
ayrıştırıcı jeneriktir. Yeni banka eklemek kod değil konfigürasyondur.

- `parse_delimited()` — CSV/Excel dışa aktarım
- `parse_pdf_text()` — metin katmanlı PDF (satır regex + üstbilgi regex)
- `load_pdf_statement()` — PDF metin çıkarıcı **enjekte edilir**
  (üretimde pdfplumber/PyMuPDF); parola asla saklanmaz
- `import_statement()` — **idempotent**; `txn_fingerprint` ile tekilleştirir
- `effective_as_of()` — hesaplama tarihi = min(bugün, son ekstre tarihi)
- `statement_coverage()`, `missing_months()` — kapsam ve boşluklar

Kart ekstresinden ayrıca **dönem sonu borcu** çıkar → `debt_principal_history`.

#### `normalize.py`
En büyük modül (993 satır). İki iş yapar:

**(a) N1–N9 hattı** (`normalize()`), sırayla:
`categorize → classify_kinds → match_internal_transfers →
resolve_card_payments → extract_installments →
detect_recurring_and_amortize → match_refunds → flag_outliers`

**(b) `Features` türetme** (`derive_features()`): kayan 30 günlük
pencereler, medyanlar, oranlar, güven girdileri.

`Ledger` sınıfı **iki gider görünümü** sunar:
- `expenses_cash()` — taksit aylık; nakit akışı, marj, acil fon ayı
- `expenses_accrual()` — taksit satın alma ayında tam; bütçe, davranış

Bu ayrım zorunludur. Karıştırmak "12 taksitle telefon aldım" davranışını
görünmez kılar.

#### `behavior_infer.py`
Etiketsiz plansızlık ölçümü. İki kademe:

1. **Çıkarım** — 10 sinyalli lojistik model. En güçlüsü *yinelenen ödeme*
   (−2,40): düzenli tekrar eden harcama tanımı gereği planlıdır.
2. **Etiket** — triyaj. `calibrate_intercept()` yalnızca kesişimi kaydırır
   (az veriyle çok parametreli fit aşırı uyum yapar).

Harman: `oran = w × etiketli + (1−w) × çıkarımsal`, `w = min(1, n/40)`.

`select_for_triage()` bilgi kazancına göre seçer:
`değer = tutar_payı × (1 − |2p − 1|)` — kararsız VE önemli işlemler.

**Dürüstlük sınırı:** plansızlık iyi çıkarılır, **duygu çıkarılamaz**.
`emotion_probability()` bilerek zayıftır ve UI'da iddia değil soru olarak
sunulmalıdır.

---

### Skor katmanı

#### `score_engine.py`
**Saf fonksiyon.** I/O yok, rastgelelik yok, zamana bağlılık yok.

```
compute_score(Features) → ScoreResult
```

İçerik:
- 3 eşleme fonksiyonu: `lin`, `sat`, `concave`
- 6 bileşen fonksiyonu: `pillar_cashflow` … `pillar_behavior`
- `_assemble()` — alt metrikleri birleştirir, devre dışı olanların
  ağırlığını yeniden dağıtır
- `confidence()` — güven `C`
- `smoothing_anchor()` + `smooth()` — asimetrik yumuşatma
- `attribute()` — iki skor arasındaki farkı bileşenlere dağıtır
- `simulate()` — "bu adımı atarsam ne olur"

Ayrıntılı akış: `Docs/ALGORITHM.md`.

---

### Koç katmanı

#### `coach_tools.py`
8 araç + `NumberLedger`. Her araç deterministiktir ve döndürdüğü **her
sayıyı deftere kaydeder**. `call_tool()` ayrıca araç çıktısındaki
METİNLERDE geçen sayıları da kaydeder (örn. "1 aydan az" içindeki `1`).

`ACTIONS` sözlüğü 5 parametreli aksiyon içerir. `build_action_plan()`
etkiyi **kümülatif** hesaplar ve gösterilen skora sabitler.

#### `coach_guard.py`
İki iş:
1. **Sayı doğrulama** — `extract_numbers()` Türkçe ve İngilizce biçimleri
   tanır; her rakam deftere karşı kontrol edilir
2. **İçerik kuralları** — SPK, kesinlik, ton, kimlik, belirsizlik dili,
   somut adım, enflasyon bağlamı

`guarded_reply()`: üret → doğrula → onar → yedek şablon.
`render_fallback()` tanım gereği doğrulamayı geçer.

#### `coach_prompt.py`
Sistem prompt'u ve `build_user_context_block()`. **Bağlam bloğu sayı
içermez** — sayılar yalnızca araç çıktılarıyla gelir ve orada deftere
kaydedilir.

---

### Sunum katmanı

#### `screen_data.py`
Kanonik ekran veri seti. 3 durum (`gun0`, `ilk_ekstre`, `olgun`) ×
6 ekran. `screen_data.json` üretir — tasarım ve frontend aynı dosyadan
beslenir, sayı uydurmak yapısal olarak imkânsız hâle gelir.

`guvence_kademe()` acil fonu kademelendirir: 3 ay skora dahil, 6 ay rozet.

#### `app/server.py` + `app/web/`
Doğrulama prototipi. **Sahte veri yoktur** — her sayı `engine/`'den gelir.
Triyaj yapıldığında skor gerçekten değişir.

Uç noktalar üretim API sözleşmesinin taslağıdır:
```
GET  /api/state?s=<gun0|ilk_ekstre|olgun>
GET  /api/bundle
POST /api/triage   {txn_id, planned, emotion}
POST /api/txn      {amount, category, planned, emotion, desc}
POST /api/upload   {sample} | {text, profile, account}
GET  /api/coach?q=<durum|tasarruf|risk|kategori|yatirim>
```

---

## 3. Veri akışı — uçtan uca

`fixture_didem.py` bu akışın tamamını çalıştırır:

```
281 ham işlem
  ↓ categorize            → 233 kural eşleşmesi, 48 varsayılan
  ↓ classify_kinds        → income/purchase/transfer/card_payment/...
  ↓ N1 iç transfer        → 10 çift eşleşti
  ↓ N2 kart ödemesi       → 5 ödeme gider dışı
  ↓ N3 taksit             → 2 plan (6×900, 4×900)
  ↓ N4 amortisman         → 1 seri, 12 sanal kayıt (kasko 8.400 → 700/ay)
  ↓ N7 iade               → 1/1 eşleşti
  ↓ N8 aykırı değer       → 1 işlem (95.000 TL toplu hakediş)
  ↓ derive_features       → gelir 27.890 · gider 19.463 · marj %30,2
  ↓ behavior_infer        → plansız %12 · kapsam %55
  ↓ compute_score         → 75/100 (ham 76,4 · C 0,98)
```

Elle kurulmuş `golden_profiles.didem` **73** verir. İkisi **aynı kullanıcı
değildir** — bakiyeler ve onboarding aynı, akış metrikleri 281 işlemden
türetildiği için farklı (golden profilin hiç taksiti yok, fixture'ın iki
planı var). Dolayısıyla bu bir determinizm denetimi değil, **hattın hiçbir
yerinde kopukluk olmadığının** göstergesidir: bir N kuralı atlansa fark
2 puan değil onlarca puan olurdu. Ayrıntı: `Docs/TESTING.md` §7.

---

## 4. Neden bu ayrımlar

### Neden `Features` bir sınır?
Motor saf kalsın diye. Ham işlem alsaydı test edilemez, replay edilemez
ve normalizasyon değişimi motoru bozardı.

### Neden `params.py` ayrı?
"Skorlama tablosunu ayarlayalım" demek 96 sayıyı tartışmak demektir.
Kodun içine dağılmışken ne tartışılabilir ne etkisi ölçülebilir.
`tune.py` bu tablo sayesinde her parametrenin etkisini ölçebiliyor.

### Neden `metinler.py` ayrı?
Metinler ton kurallarına tabidir ve bir editör tarafından gözden
geçirilebilir olmalıdır. Ayrıca ileride çeviri gerekirse tek nokta.

### Neden koç guard'ı prompt'tan ayrı?
**Prompt bir rica, guard bir garantidir.** Yalnızca prompt'a yazılan kural
uzun konuşmalarda kayar; yalnızca guard'a yazılan kural sürekli ret
üretir. İkisi birlikte çalışır.

### Neden prototip ayrı klasörde?
`app/` sevk edilecek uygulama değil. Sevk sürümü React Native olur.
Prototibin amacı akışları ve veri sözleşmesini haftalar harcamadan
doğrulamak.
