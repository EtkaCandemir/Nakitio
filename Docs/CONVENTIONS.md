# CONVENTIONS.md — İhlal Edilemez Kurallar

Bunlar üslup tercihi değil. Her biri bir hatanın önlenmesi için var ve
çoğu bir testle korunuyor. Bir kuralı bozan değişiklik modeli bozar.

---

## 1. Model kuralları

### K1 — `score_engine` saftır

I/O yok, rastgelelik yok, `datetime.now()` yok, global durum yok.
Aynı `Features` her zaman aynı `ScoreResult`.

**Neden:** replay edilebilirlik. Eski bir snapshot yıllar sonra aynı
skoru üretmeli ki kullanıcı itirazı yanıtlanabilsin ve model güvenle
değiştirilebilsin.

**Test:** `t_determinism`

### K2 — Eksik veri ceza değildir

Ölçemediğin şey için puan kırma. Bileşeni devre dışı bırak, ağırlıkları
yeniden normalize et, güveni düşür.

```python
alt = None if veri_yok else formül(veri)     # 0.0 DEĞİL
```

`weight_effective` toplamı her zaman tam 100 olmalı.

**Bu kural üç kez SESSİZCE bozuldu** — çünkü bir niyet beyanıydı, yapısal
bir garanti değildi: `liquid_balance` 0,0 dönüp tamponu sıfırlıyordu,
`disc_share` 0,0 dönüp isteğe bağlı paydan **100 puan** veriyordu, `dsr`
1,0 dönüp borcu en kötü varsayıyordu. Hiçbiri test kırmadı, çünkü test
edilecek bir sözleşme yoktu.

Sözleşme artık `SubScore.requires`: her alt metrik hangi `Features`
alanlarına ihtiyaç duyduğunu **bildirir**.

```python
SubScore("guvence", "Acil durum fonu", guvence, P["p3.guvence.w"],
         detay, requires=("ef_liquid",))
```

Bildirim üç şey sağlar:

1. `t_every_submetric_can_be_none` bildirilen alanları boşaltır ve alt
   metriğin GERÇEKTEN `None` döndüğünü denetler. `t_requires_covers_real_inputs`
   ters yönü sorar: bildirilen alan gerçekten belirleyici mi.
2. Sunum katmanı "bu metriği neden göremiyorsun" diyebilir — gerekçe
   cümleleri `metinler.VERI_YOK_NEDEN`dedir (bkz. S5).
3. Yeni alt metrik eklemek güvenli olur: yalnız ekstreden ölçülebilen bir
   metrik, manuel giriş kullanıcısında kendiliğinden kapanır. Ölçüldü —
   manuel yüzeyde 23 alt metriğin 9'u kapanıyor, hiçbiri 0 puan almıyor,
   güven 0,90 → 0,79 iniyor ve band genişliyor.

`requires` boş bırakmak "her koşulda ölçülebilir" iddiasıdır ve yalnızca
sentetik alt metrikler için doğrudur (`borcsuz`, `hedefsiz`). Test bunu da
denetler: bildirimsiz her alt metrik gerekçeli listede olmalıdır.

**Ayrım:** payı sıfır olan oran tanımsız DEĞİLDİR, sıfırdır. `s_deliberate`
işlemlerden doğrudan ölçülür; "hiç birikim yapmadı" gelir bilinmese de
bilinen bir olgudur. Bu ayrım olmadan geliri gizlemek olumsuz bir bulguyu
siler — ölçüldü, +1 puan kazandırıyordu.

**Test:** `t_missing_data_never_punishes`, `t_absent_balance_is_not_zero`,
`t_undefined_ratios_disable_submetrics`, `t_every_submetric_can_be_none`,
`t_requires_covers_real_inputs`

### K3 — Süreksizlik yasak

Basamak tablosu kullanma. Girdideki küçük değişim skorda küçük değişim
yaratmalı. Parçalı fonksiyonların dalları birleşme noktasında **aynı
değeri** vermeli.

**Test:** `t_continuity` — 6 metriği 400 adımda tarar, 1 puandan büyük
sıçrama arar.

### K4 — Monotonluk

Bir metriği tek başına iyileştirmek skoru asla düşürmemeli.
Tersi de geçerli: kötüleştirmek yükseltmemeli.

**Test:** `t_monotonicity` — 4 artan, 9 azalan metrik.

### K5 — Engagement skora giremez

Uygulama kullanımı, görev tamamlama, seri, rozet — hiçbiri skorun girdisi
değildir. Yalnızca güveni (`C`) etkileyebilir.

**Neden:** engagement senin retention metriğindir, kullanıcının finansal
sağlığı değil. Skora koymak çıkar çatışması yaratır ve skoru manipüle
edilebilir kılar.

**Test:** `t_no_engagement_inputs` — `Features` alan adlarında ve motor
kaynağında yasaklı kelime arar.

### K6 — Kullanıcı beyanı bileşen skorunu yükseltemez

Onboarding cevapları yalnızca `S_öncül` ve `C`'yi etkiler. `S_ham`'a
dokunamaz. Etkisi veri biriktikçe sönümlenir.

**Test:** `t_self_report_cannot_raise_pillars`

### K7 — Kötü haber hızlı, iyi haber yavaş

Yukarı hareket her zaman yumuşatılır ve ±8 ile sınırlıdır.
Maddi olayda aşağı yönde sınır kalkar ve α yükselir.

**Test:** `t_asymmetric_smoothing`

### K8 — Güven değişimi yumuşatılmaz

Yumuşatma yalnızca **gerçek finansal değişime** uygulanır. Ölçümün
düzelmesi kullanıcının durumundaki bir değişiklik değildir.

**Test:** `t_confidence_change_is_not_smoothed`

### K9 — Skor gelir seviyesini değil, ilişkiyi ölçer

Tüm parasal alanlar aynı katsayıyla ölçeklendiğinde skor değişmemeli.

**Test:** `t_fairness_income_neutral` — ×0,25'ten ×8'e kadar tarar,
yayılım 0,5 puandan küçük olmalı.

---

## 2. Veri katmanı kuralları

### V1 — N2: kart ödemesi çift sayımı

```python
# YANLIŞ
linked_cards = {a.id for a in accounts if a.is_linked}

# DOĞRU
accounts_with_txns = {t.account_id for t in transactions}
visible_cards = {a.id for a in accounts
                 if a.type == CREDIT_CARD
                 and (a.is_linked or a.id in accounts_with_txns)}
```

**Belirleyici soru "API'ye bağlı mı" değil, "işlemlerini görüyor muyuz".**
Ekstre modelinde kart bağlı olmadan da tamamen görünür olabilir.

Yanlışı: gider ₺19.463 yerine ₺29.978, korunan tutar negatif.

**Test:** `t_n2_linked_card_no_double_count`, `t_n2_unlinked_card_is_proxy`

### V2 — Türkçe harf katlama iki farklıdır

| Yer | Kural | Neden |
|---|---|---|
| `coach_guard._norm` | Türkçe: `I → ı`, `İ → i` | Koç yanıtı düzgün Türkçe metindir |
| `statement_ingest._fold` | **ASCII katlama, Türkçe eşleme YOK** | Banka aksansız yazar: "ÖDEME" → "ODEME" |

```python
# statement_ingest._fold — DOĞRU
s = s.lower()
s = unicodedata.normalize("NFKD", s)
s = "".join(c for c in s if not unicodedata.combining(c))
return s.replace("ı", "i")
```

Türkçe eşlemesi ekstrede uygulanırsa `"IADE"` → `"ıade"` olur, `"iade"`
işaretçisiyle eşleşmez, kart ödemesi ve iade satırları **harcama sayılır**
— yani N2 felaketi bir harf katlama hatasından geri gelir.

**Test:** `t_fingerprint_sensitivity`, `t_parse_card_pdf`

### V3 — Boş pencere ≠ sıfır harcama

`active_windows()` kullan. Veri OLMAYAN pencereyi "o ay sıfır harcadı"
saymak eksik veriyi cezaya çevirir.

**Test:** `t_short_history_not_penalized`

### V4 — İki gider görünümü karıştırılmaz

| Görünüm | Taksit nasıl | Nerede |
|---|---|---|
| **Nakit** (`expenses_cash`) | aylık taksit | nakit akışı, marj, acil fon ayı, oynaklık |
| **Tahakkuk** (`expenses_accrual`) | satın alma ayında tam | bütçe uyumu, davranış oranları |

Karıştırmak "12 taksitle telefon aldım" davranışını görünmez kılar.

### V5 — Hesaplama tarihi ekstreyle ilerler

```python
as_of = effective_as_of(periods, today)   # = min(bugün, son ekstre tarihi)
```

`as_of = bugün` almak, ekstre kesiminden sonraki günleri "sıfır harcama"
saymak demektir; marj yapay yükselir. Ters yönde de: ekstre yüklendiğinde
`as_of` ilerlemezse yeni işlemler pencerenin dışına düşer ve **skor
yükleme sonrası düşer**.

**Test:** `t_effective_as_of`

### V6 — İdempotent içe aktarma

`txn_fingerprint(hesap, tarih, tutar, normalleştirilmiş_açıklama)`.
Aynı ekstre ikinci kez yüklendiğinde `added = 0` olmalı.

**Test:** `t_import_and_dedup`, `t_overlapping_periods`

### V7 — Enflasyon düzeltmesi yalnız dönemler arası

```
reel(tutar, tarih) = tutar × (TÜFE[bugün] / TÜFE[tarih])
```

**Aynı dönem içi oranlarda kullanılmaz** — pay ve payda aynı enflasyona
maruz kaldığı için oran nötrdür, düzeltme çift sayım olur.

Kullanıldığı yerler: `i_cv`, `cat_volatility`, kategori değişimi.

### V8 — Değerleme farkı tasarruf değildir

Altın/döviz/fon hesaplarında yalnızca **katkılar** sayılır. Fiyat artışı
kullanıcının davranışı değil, piyasanın hareketidir.

**Test:** `t_n6_valuation_not_savings`

### V9 — Borç trendi tahmin edilmez

Yalnızca ölçülmüş `debt_principal_history`'den hesaplanır. İşlem
akışından türetmek limiti içinde dönen bir kartta bile "borç %88 arttı"
üretir. **Uydurulmuş sinyal, eksik sinyalden kötüdür.**

---

## 3. Koç kuralları

### C1 — LLM sayı üretmez

Yanıttaki her rakam `NumberLedger`'da kayıtlı olmalı.
`verify_response()` geçmeden kullanıcıya gösterilmez.

### C2 — Bağlam bloğu sayı içermez

`build_user_context_block()` yalnızca aşama, seviye, bayrak, alan adı
verir. Sayı yazılırsa LLM defterde olmayan bir sayıyı meşru biçimde
kullanabilir hâle gelir — doğrulamada sessiz kaçak.

**Test:** `t_context_block_has_no_numbers`

### C3 — Guard reddetmeyi engellememelidir

"Yatırım tavsiyesi veremem" cümlesi `investment_advice` sayılmamalı.
`REFUSAL_MARKERS` eşleşmenin ardından ±40 karakter içinde aranır.

SPK sınırı tam olarak reddedebilmeyi gerektirir; guard koçu doğru
davrandığı için cezalandırmamalı.

**Test:** `B09`–`B11` vakaları

### C4 — Doğrulayıcı aşırı katı olmamalı

Türkçe (`24,9`) ve İngilizce (`7.6`) ondalık biçimlerinin ikisi de
tanınmalı. Açık yuvarlama serbest. Yapısal küçük tam sayılar (≤31,
para/yüzde/skor bağlamında değilse) muaf.

Aşırı katı doğrulayıcı, hiç olmaması kadar zararlıdır — ürün sürekli
yedek şablona düşer.

### C5 — Plan kümülatif hesaplanır ve gösterilen skora sabitlenir

Aksiyonların etkisi toplanabilir değildir. Ayrıca simülasyon
yumuşatmasız, gösterilen skor yumuşatılmıştır; çapa gösterilen skor
olmalı, delta simülasyondan gelmeli.

**Test:** `t_plan_is_cumulative`

---

## 4. Sunum kuralları

### S1 — Ton

Skor bir **alan** hakkında konuşur, kullanıcı hakkında değil.

| Yasak | Yerine |
|---|---|
| "Finansal durumun kötü" | "Şu an gelişim alanların var" |
| "Savruksun" | "Plansız harcamaların toplam harcamanın %12'si" |
| "Skorun 86 olacak" | "86 seviyesine çıkabilir (tahmini)" |
| "Restoran +%27 arttı" | "+%27 arttı; enflasyondan arındırınca %22" |

Yasaklı kelimeler: kötü, başarısız, yetersiz, savruk, müsrif,
disiplinsiz, kontrolsüz.

### S2 — Belirsizlik gizlenmez

`C < 0,65` → skor **bant** olarak gösterilir, seviye etiketi
**gösterilmez**, "veri arttıkça daralacak" notu eşlik eder.

5 onboarding cevabından türetilmiş skora "Dikkat" demek, "hiçbir zaman
utandırma" ilkesinin ihlalidir.

### S3 — Düşük skor daima somut adımla

`score < 60` iken yanıt bir sonraki adımı içermeli.

### S4 — Çıkarım iddia edilmez

`etiket_agirligi < 0,5` → davranış değerleri "senin duygusal harcaman
%14" diye **iddia** edilmez, "bunlar duygusal olabilir mi?" diye **soru**
olarak sunulur.

### S5 — Metinler `metinler.py`'de

Kullanıcıya gösterilen hiçbir cümle koda gömülmez.

### S6 — Biçimlendirme tek yerde

`screen_data.tl()` ve `pct()`. Para `₺12.770`, oran `%24,9`.
Binlik nokta, ondalık virgül.

---

## 5. Kod kuralları

### Dil
Kod, yorum, doküman, kullanıcı metni **Türkçe**. Tanımlayıcılar
(`Features`, `compute_score`) İngilizce kalır; yeni alan adları Türkçe
olabilir (`guvence_kademe`).

### Yorumlar NEDEN'i anlatır
Ne yaptığını değil. Özellikle bir değerin neden o değer olduğunu.
Bir hata düzeltildiğinde yorum **hatanın kendisini** anlatmalı ki tekrar
üretilmesin.

```python
# İYİ
# İlk sürümde bu, kart harcaması eksi ödeme akışından tahmin ediliyordu.
# Sonuç saçmaydı: limiti içinde dönen bir kartta bile "borç %88 arttı"
# çıkıyordu — aynı ay harcanıp ödenen tutar net borç değişimi değildir.

# KÖTÜ
# Borç trendini hesapla
```

### Parametreler `params.py`'de, çalışma anında okunur

```python
# YANLIŞ — import anında yakalanır, tune.py etkileyemez
BREAKEVEN = P["p1.breakeven"]
def f(): return BREAKEVEN * 2

# DOĞRU
def f(): return P["p1.breakeven"] * 2
```

### Sabitler adlandırılır

Sihirli sayı bırakma. `params.py` dışındaki sabitler modül başında
adlandırılmış ve yorumlanmış olmalı.

### Testler değeri değil kuralı denetler

```python
# KIRILGAN — her parametre kararı testi kırar
check("öncül kelepçesi", prior_score(kotu) == 40)

# SAĞLAM
check("alt kelepçe uygulanıyor", prior_score(kotu) == P["prior.min"])
```

---

## 6. Değişiklik öncesi kontrol listesi

**Parametre değiştirdim:**
```bash
python3 tune.py --set "anahtar=değer"   # etkisini gör
# params.py'yi düzenle, KARAR yorumu ekle
python3 golden_profiles.py              # skorlar nasıl kaydı
python3 test_invariants.py              # yapısal kural kırıldı mı
# Docs/DECISIONS.md'ye satır ekle
```

**Formül/mantık değiştirdim:**
```bash
python3 test_invariants.py && python3 test_normalize.py \
  && python3 test_ingest.py && python3 coach_eval.py
python3 fixture_didem.py                # uçtan uca hâlâ tutuyor mu
python3 screen_data.py                  # ekran verisi üretiliyor mu
```

**Yeni davranış ekledim:** önce test yaz. Özellikle `CLAUDE.md` §8'deki
hata sınıflarına dokunuyorsan.

**Metin değiştirdim:** ton kurallarını (§4) gözden geçir, `coach_eval.py`
çalıştır.
