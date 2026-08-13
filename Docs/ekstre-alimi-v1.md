# Nakitio — Ekstre Alımı ve Davranış Çıkarımı, v1.0

**Durum:** Uygulanmaya hazır teknik şartname
**Referans implementasyon:** `engine/statement_ingest.py`, `engine/behavior_infer.py`
**Testler:** `engine/test_ingest.py` (90 kontrol)
**Bağlı olduğu:** `Docs/veri-katmani-v1.md`, `Docs/skor-modeli-v2.md`

```
ekstre dosyası ─▶ [ayrıştırma] ─▶ [tekilleştirme] ─▶ RawData
               ─▶ [N1…N9 normalizasyon] ─▶ [davranış çıkarımı] ─▶ Features ─▶ skor
```

---

## 0. Karar ve iki sonucu

Veri girişi olarak **ekstre yükleme** seçildi. Hem iOS hem Android'de
çalışır, lisans gerektirmez, banka doğruluğunda veri verir.

Ama iki şeyi kırar ve ikisi de çözülmek zorundadır:

| Kırılan | Neden | Çözüm |
|---|---|---|
| **Davranış ölçümü** | Veri aylık ve toplu gelir; kimse 200 işlemi geriye dönük etiketlemez. P6 bileşeni ve Davranış Analizi ekranı ölür | §6 — çıkarım + triyaj |
| **Zaman ekseni** | Ekstre ayın 18'inde keser; son 13 günün verisi yoktur | §5 — `effective_as_of` |

Bu doküman ikisini de çözer.

---

## 1. Format gerçekleri

| Kaynak | Biçim | Zorluk |
|---|---|---|
| Hesap hareketleri | CSV / Excel dışa aktarım | **Kolay** — en güvenilir yol |
| Hesap hareketleri | PDF | Orta — metin katmanı var |
| Kredi kartı ekstresi | PDF (e-posta ile aylık) | **Zor** — parola + banka başına düzen |
| Kâğıt ekstre fotoğrafı | Taranmış PDF / görsel | OCR gerekir — v1 kapsamı dışı |

**Ürün önerisi:** hesap hareketlerinde kullanıcıyı CSV/Excel'e yönlendir
(internet bankacılığında birkaç tık), kart ekstresi için PDF'i destekle.
İlk sürüm 5-6 banka ile çıkar, kapsam profil ekleyerek büyür.

---

## 2. Profil tabanlı ayrıştırma

**Tasarım kuralı: yeni banka eklemek kod değil, konfigürasyon olmalı.**
Aksi hâlde her banka için ayrı kod yazılır, hiçbiri test edilmez ve kapsam
5 bankadan öteye geçmez.

Bir banka profili (`BankProfile`) bir veri kaydıdır:

```python
BankProfile(
    key="tr_generic_card_pdf", bank="…", doc_kind="card", fmt="pdf_text",
    line_re=r"^(?P<date>\d{2}[./]\d{2}[./]\d{4})\s+(?P<desc>.+?)\s+"
            r"(?P<amount>-?[\d.]+,\d{2})\s*(?P<sign>TL)?\s*$",
    header_re={"period_end": r"…Kesim Tarihi\s*:?\s*(\d{2}[./]\d{2}[./]\d{4})",
               "closing_balance": r"Dönem Borcu\s*:?\s*([\d.]+,\d{2})", …},
    decimal="tr",
    credit_markers=("ödeme", "iade", "iptal", "alacak"),
    password_hint="…",
)
```

Ayrıştırıcı jeneriktir: `parse_delimited` ve `parse_pdf_text`.

> ⚠ Repodaki 3 profil **şemayı** gösterir. Üretime alınmadan önce her biri
> ilgili bankadan alınmış **gerçek örnek dosyalarla** doğrulanmalıdır;
> sütun adları, tarih biçimleri ve satır düzenleri bankadan bankaya ve
> sürümden sürüme değişir.

### PDF metni enjekte edilen bağımlılıktır

```python
extract_text: Callable[[bytes, Optional[str]], str]
```

Üretimde pdfplumber / PyMuPDF. Bu ayrım sayesinde ayrıştırma mantığı PDF
kütüphanesinden bağımsız test edilir.

### Parola

Türkiye'de kart ekstreleri sık sık TCKN/doğum tarihi/kart son hanelerinden
türetilen bir parolayla korumalı gelir.

```
PasswordRequired(hint)  →  kullanıcıdan iste  →  ayrıştır  →   At.
```

**Parola hiçbir zaman saklanmaz, loglanmaz, sunucuya gönderilmez.**
Bellekte tutulur ve atılır. Bu bir kimlik verisidir; kaybı KVKK olayıdır.

---

## 3. ⚠ Harf katlama — sessiz felaket

Türkçe metin normalleştirmesi iki farklı yerde iki farklı şekilde
yapılmalıdır ve karıştırılması ağır sonuç doğurur.

| Yer | Kural | Neden |
|---|---|---|
| `coach_guard._norm` | Türkçe: `I → ı`, `İ → i` | Koç yanıtı düzgün Türkçe metindir |
| `statement_ingest._fold` | **ASCII katlama, Türkçe eşleme YOK** | Ekstre aksansız ASCII yazar |

Banka sistemleri aksanları düşürür: **"ÖDEME" → "ODEME"**, "İADE" → "IADE",
"MİGROS" → "MIGROS".

Türkçe eşlemesi ekstrede uygulanırsa `"IADE"` → `"ıade"` olur ve `"iade"`
işaretçisiyle **eşleşmez**. Sonucu ağırdır:

> Kart ödemesi ve iade satırları alacak olarak tanınmaz, **harcama
> sayılır**. Yani veri katmanı N2'nin (kredi kartı çift sayımı) tam olarak
> engellemeye çalıştığı felaket, bir harf katlama hatası yüzünden geri
> gelir — ve hiçbir yerde hata vermez.

Bu, testler yazılırken yakalandı: 6 başarısızlığın 4'ünün tek kök nedeni
buydu. Doğru katlama:

```python
s = s.lower()
s = unicodedata.normalize("NFKD", s)
s = "".join(c for c in s if not unicodedata.combining(c))
return s.replace("ı", "i")
```

---

## 4. Tekilleştirme

Aynı ekstre iki kez yüklenebilir. Dönemler üst üste biner (kart 18'inde
keser, hesap hareketleri ay başından itibaren). Parmak izi olmadan
işlemler çiftlenir ve kullanıcının gideri iki katına çıkar.

```
txn_fingerprint = sha256(hesap | tarih | tutar | normalleştirilmiş_açıklama)
statement_key   = sha256(banka | hesap_ref | dönem_başı | dönem_sonu)
```

`import_statement` idempotenttir: aynı ekstre ikinci kez yüklendiğinde
`added=0, duplicates=N` döner. Örtüşen dönemde yalnızca yeni satırlar
eklenir. Regresyon: `test_ingest.t_import_and_dedup`,
`t_overlapping_periods`.

### Beklenmedik kazanç: borç anapara geçmişi

Kart ekstresi **dönem sonu borcunu** verir. Bu, veri katmanında eksik
bırakılan `debt_principal_history` girdisinin ta kendisidir — onsuz borç
trendi alt metriği (20 puanlık bileşenin %15'i) hep kapalı kalıyordu.

Ekstre ayrıca **asgari ödeme tutarını** ve **son ödeme tarihini** verir:
`min_payment_only_months` ve gecikme tespiti için doğrudan girdi.

Taksitler ekstrede açıkça yazar (`TAKSIT 3/12`, `(1/4)`) → N3 sorunsuz
çalışır.

---

## 5. Zaman ekseni

```python
as_of = effective_as_of(periods, today)   # = min(bugün, son ekstre tarihi)
```

Ekstre ayın 18'inde kesiliyorsa, 31'inde `as_of = bugün` almak son 13 günü
**"sıfır harcama"** saymak demektir. Nakit akışı marjı yapay olarak
yükselir ve kullanıcıya gerçekte var olmayan bir iyileşme gösterilir.

Ürün sonucu: ana ekranda **cari ay hiçbir zaman tam değildir.** Mockup'ların
*"Bu ay tasarruf oranı %26"* kartı, ekstre modelinde son kapanan dönemi
göstermek zorundadır. Bunun UI'da açıkça belirtilmesi gerekir:
*"18 Temmuz'a kadar"*.

### Kapsam ve boşluklar

```python
statement_coverage(periods, as_of, months=6)  # → [0,1]
missing_months(periods, as_of)                # → ["2026-03", "2026-05"]
```

Eksik aylar kullanıcıya gösterilir (*"Mart ve Mayıs ekstreleri eksik"*) ve
güveni düşürür.

---

## 6. Davranış çıkarımı — asıl problem

**Sorun:** Ekstrede "plansızdı", "streslikken aldım", "pişman oldum"
bilgisi yoktur. Etikete dayanan P6 bileşeni ve mockup'taki Davranış
Analizi ekranının tamamı bu yüzden ölür.

**Çözüm: iki kademeli ölçüm.**

### Kademe 1 — Çıkarım (kullanıcı hiçbir şey yapmaz)

Plansızlık, ekstrenin kendisinden makul doğrulukla çıkarılabilir. Lojistik
bir modelle 10 sinyal birleştirilir:

| Sinyal | Yön | Katsayı |
|---|---|---|
| Yinelenen ödeme (tanınan merchant, düzenli tutar) | **planlı** | −2,40 |
| Kategori ön olasılığı (kira 0,00 … şans oyunu 0,80) | ± | 2,60 |
| İade edilmiş | plansız | +1,60 |
| Kategori medyanına göre tutar sapması | plansız | +0,85 |
| Gece harcaması *(saat varsa)* | plansız | +0,75 |
| Aynı gün isteğe bağlı harcama kümesi | plansız | +0,70 |
| İlk kez görülen merchant | plansız | +0,55 |
| Maaş gününe yakınlık (0–3 gün) | plansız | +0,50 |
| Taksitle alınmış | plansız | +0,45 |
| Hafta sonu | plansız | +0,35 |

En güçlü sinyal **yinelenen ödemedir**: düzenli tekrar eden bir harcama
tanımı gereği planlıdır. Yinelenen bir kira ödemesinin plansızlık
olasılığı < 0,05.

**İade, pişmanlığın doğrudan gözlemidir** — ve ekstrede vardır. Ama alt
sınırdır: insanlar pişman oldukları her şeyi iade etmez. Bu yüzden bir
vekil katsayısıyla ölçeklenir ve etiket geldiğinde hızla ona devredilir.

### Kademe 2 — Triyaj (yükleme sonrası 8–12 soru)

Rastgele veya "en büyük k" değil, **bilgi kazancına** göre seçilir:

```
değer = tutar_payı × belirsizlik,    belirsizlik = 1 − |2p − 1|
```

Modelin **kararsız** olduğu ve tutarca **önemli** olan işlemler. Zaten emin
olduğu bir kira ödemesini sormak hiçbir şey öğretmez.

Her soru gerekçesiyle birlikte gelir — çıkarım şeffaftır, kullanıcı neyi
onayladığını bilir:

```
  900 TL  Giyim            p=0,67  ilk kez görülen bir yer · bu kategoride
                                   alışılmışın üzerinde · taksitle alınmış
  432 TL  Restoran & Kafe  p=0,59  bu kategoride alışılmışın üzerinde ·
                                   aynı gün 3 isteğe bağlı harcama
```

### Harmanlama

Skor modelindeki güven (C) mantığının aynısı:

```
oran = w × etiketli_oran + (1 − w) × çıkarımsal_oran
w    = min(1, etiket_sayısı / 40)
```

Etiketler ayrıca **kesişimi kalibre eder** (`calibrate_intercept`).
Yalnızca kesişim, katsayılar değil: 20–60 etiketle çok parametreli bir
model aşırı uyum yapar. Kesişim kaydırma az veriyle sağlamdır ve
kullanıcının **genel plansızlık düzeyini** yakalar — kişiselleştirmenin en
değerli kısmı da budur.

### Ölçülen sonuç

| Davranış | plansız | duygusal | pişman | kapsam |
|---|---|---|---|---|
| Saf çıkarım (0 etiket) | %9 | %5 | %0 | %55 |
| Harman (21 etiket) | %12 | %10 | %14 | %55 |

Kritik olan: **etiketsiz durumda bile P6 bileşeni açık kalır** (82,8/100).
Eskiden tamamen kapanıyordu. Regresyon:
`test_ingest.t_behavior_without_labels`.

### Dürüstlük sınırı — duygu çıkarılamaz

Plansızlık iyi çıkarılır. **Duygu çıkarılamaz.** "Streslikken aldım" ile
"kendimi ödüllendirdim" arasındaki fark ekstrede yoktur.

`emotion_probability` yalnızca zayıf bir vekildir: rahatlama kategorisi +
gece/hafta sonu + kümelenme örüntüsü. Sinyaller yığıldığında bile 0,90'ı
geçmez, ve plansızlık tahmininden bilinçli olarak daha temkinlidir.

**UI kuralı (zorunlu):** bu sayı hiçbir zaman *"duygusal harcaman %14"*
diye **iddia** olarak sunulmaz. *"Bunlar duygusal harcama olabilir mi?"*
diye **soru** olarak sunulur ve cevap etiket olarak toplanır.

> Bu, mockup'taki Davranış Analizi ekranını da kurtarır: pasif bir rapor
> yerine, gösterirken aynı anda etiket toplayan etkileşimli bir yüzeye
> dönüşür. Ekran hem doluyor hem modeli eğitiyor.

### Saat verisi

**Ekstrelerde işlem saati çoğunlukla yoktur.** İçe aktarımda saat 00:00
yazılır ve `behavior_infer` bunu *"gece harcaması"* değil *"saat
bilinmiyor"* olarak yorumlar (`Signals.night = None`).

Gece yoğunlaşması metriği, saat verisi olan işlemlerin payı %50'nin
altındaysa **hiç hesaplanmaz**. Alternatif sinyal: hafta içi/hafta sonu ve
gün örüntüsü — tarih her zaman vardır.

---

## 7. Güven kademeleri

`c_cover` artık üç kademelidir:

| Kaynak | Tavan | Gerekçe |
|---|---|---|
| `linked` (açık bankacılık) | tavan yok | sürekli ve banka kaynaklı |
| `statement` (ekstre) | `0,85 × kapsam × kategorize_oran` | banka kaynaklı ama **kesintili** |
| `manual` | `0,45 × kategorize_oran` | unutulan işlem riski yapısal |

Ölçülen etki (Didem profili):

| Kaynak | C | Skor | Band |
|---|---|---|---|
| Açık bankacılık | 0,98 | 74 | 72–76 |
| Ekstre — 6/6 dönem | 0,92 | 74 | 72–76 |
| Ekstre — 4/6 dönem | 0,87 | 74 | 72–76 |
| Ekstre — 3/6 dönem | 0,84 | 73 | 71–75 |
| Manuel giriş | 0,84 | 73 | 71–75 |

Ekstre yükleme, manuele değil **açık bankacılığa yakın** konumlanır — hak
ettiği yer orası. Eksik dönem güveni düşürür ve kullanıcıya *"Mart ekstresi
eksik, skorun kesinliği artabilir"* mesajı verilebilir hâle gelir.

---

## 8. Ürün sonucu: aylık ritim

Bu, spec'ten çok ürün kararı ama burada kayıt altına alınmalı.

Mockup'lar **günlük ritim** üzerine kurulu: *Bugünün Finansal Görevi*,
*Bugünün Farkındalığı*, görev serisi, *"4 gün üst üste"*. Ekstre yükleme
yılda 12 temas demek ve veri 13–45 gün gecikmeli.

Üç seçenek:

1. **Aylık ritme geç.** Ana sayfa "bu ay" değil "kapanan dönem" gösterir.
   Görev/seri mekaniği aylık hedefe dönüşür. Tutarlı ama mockup'ların
   yeniden tasarımı gerekir.
2. **Hibrit (önerilen).** Ekstre geçmişin omurgası; cari ay için hızlı
   ekleme. Kullanıcı dikkat çeken birkaç harcamayı anında ekler — hem
   günlük ritim yaşar hem **davranış etiketi doğru anda** toplanır
   (harcamanın hemen ardından, aylar sonra değil).
3. **Sadece ekstre.** En düşük efor, en düşük etkileşim. Retention riski.

Hibrit ayrıca §6'daki etiket problemini üçüncü bir kanaldan besler: triyaj
(aylık, toplu) + anlık ekleme (günlük, taze).

---

## 9. Test kapsamı

`python3 engine/test_ingest.py` — 90 kontrol

| Test | Neyi garanti eder |
|---|---|
| `t_amount_parsing` | TR/EN ondalık, negatif, sondaki eksi, TL eki |
| `t_parse_card_pdf` | Üstbilgi alanları, harcama/alacak işareti |
| `t_installment_detection` | `TAKSIT 1/6` ve `(1/4)` biçimleri |
| `t_import_and_dedup` | **Aynı ekstre iki kez → çiftlenme yok** |
| `t_overlapping_periods` | Örtüşen dönemde yalnızca yeni satır |
| `t_card_import_gives_debt_snapshot` | Borç anapara geçmişi doldu |
| `t_fingerprint_sensitivity` | Boşluk/aksan normalleşir, tutar ayırır |
| `t_effective_as_of` | Hesaplama tarihi son ekstreye çekilir |
| `t_password_required` | Parola akışı, ipucu döner |
| `t_impulse_signal_directions` | 10 sinyalin yönü doğru |
| `t_emotion_is_weak_by_design` | Duygu çıkarımı temkinli kalır |
| `t_calibration` | Kesişim etiketle kayar, az örnekte varsayılana döner |
| `t_behavior_without_labels` | **Etiketsiz P6 açık kalır** |
| `t_labels_shift_estimate` | Etiket tahmini kendine çeker |
| `t_triage_selection` | Kararsız+önemli seçilir, etiketli tekrar sorulmaz |
| `t_confidence_tiers` | Ekstre, manuele değil bağlıya yakın |
| `t_end_to_end_from_statements` | Ham ekstre → skor |

---

## 10. Üretime geçmeden önce

1. **Gerçek örnek dosyalar.** Her hedef bankadan hesap hareketleri ve kart
   ekstresi örneği toplanmalı, profiller onlarla doğrulanmalı. Bu, bu
   katmanın **tek gerçek riski** — geri kalanı test edilmiş durumda.

2. **Parola akışı UX'i.** Banka başına parola kuralı farklı. Kullanıcıya
   doğru ipucunu göstermek için her profilin `password_hint`'i gerçek
   kuralla doldurulmalı.

3. **PDF kütüphanesi seçimi.** pdfplumber (saf Python, yavaş) veya PyMuPDF
   (hızlı, AGPL lisans dikkat). Şifre çözme desteği ikisinde de var.

4. **Çıkarım modelinin kalibrasyonu.** Katsayılar akıl yürütmeyle konuldu.
   İlk 200–300 gerçek etiketten sonra katsayılar da (yalnızca kesişim
   değil) yeniden fit edilmeli.

5. **Triyaj UX'i.** 8–12 kart, tek dokunuşla "plansızdı / planlıydı",
   isteğe bağlı duygu etiketi. Atlanabilir olmalı — zorunlu tutulursa
   yükleme akışı terk edilir.

6. **OCR.** Taranmış ekstre v1 kapsamı dışı. Kullanıcı fotoğraf yüklerse
   net bir hata mesajı ve "internet bankacılığından PDF indir" yönlendirmesi.

7. **Banka profillerinin uzaktan güncellenmesi.** Banka ekstre düzenini
   değiştirdiğinde uygulama güncellemesi beklemeden profil
   yenilenebilmeli — profiller sunucudan çekilmeli.

## Ek — Dosya haritası

| Dosya | İçerik |
|---|---|
| `engine/statement_ingest.py` | Profil şeması, ayrıştırıcılar, tekilleştirme, kapsam |
| `engine/behavior_infer.py` | Çıkarım modeli, kalibrasyon, harmanlama, triyaj |
| `engine/test_ingest.py` | 90 kontrol |

```bash
cd engine && python3 test_ingest.py
```
