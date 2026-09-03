# CLAUDE.md — Nakitio

> Bu dosya bir yapay zekâ asistanının bu depoda **sıfırdan** çalışmaya
> başlayabilmesi için yazıldı. Önce burayı oku, sonra ihtiyaca göre
> `Docs/` altındaki referanslara git.

---

## 1. Proje nedir

**Nakitio**, Türkiye pazarına yönelik bir kişisel finans uygulamasıdır.
Bir harcama takip uygulaması **değildir** — kullanıcıya 0–100 arası bir
**Finansal Sağlık Skoru** verir, bu skoru açıklar ve iyileştirmek için
somut adımlar önerir.

Veri kaynağı **banka ekstresi yüklemedir** (açık bankacılık değil, manuel
giriş değil). Kullanıcı hesap hareketlerini ve kredi kartı ekstresini
yükler; sistem ayrıştırır, normalleştirir, skorlar.

### Ürünün üç ayırt edici iddiası

1. **Skor, veri yeterliliğini itiraf eder.** Az veri varken bant olarak
   gösterilir ve öncüle yaklaştırılır. "Bilmiyoruz" demeyi bilir.
2. **Plansız harcama etiketsiz ölçülebilir.** Ekstreden çıkarım yapılır;
   kullanıcı etiketi çıkarımı *kalibre eder*, yerine geçmez.
3. **AI koç sayı üretmez.** Her rakam deterministik motordan gelir ve
   yanıt gösterilmeden önce doğrulanır.

---

## 2. Kim ne yapıyor

| Alan | Sorumlu |
|---|---|
| Skor modeli, veri katmanı, ekstre alımı, davranış çıkarımı | **Kullanıcı (Etka)** |
| AI koç altyapısı, backend, API, uygulama içi bağlantılar | **Kullanıcı (Etka)** |
| UI/UX tasarım | Ahmet |
| App Store + Google Play yayını | Ahmet |

Yani bu depodaki her şey kullanıcının kapsamında. Uygulamanın beyni burada.

---

## 3. Depo yapısı

```
CLAUDE.md              ← buradasın
Docs/                  ← şartnameler (TR, gerekçeli) + referanslar (bu oturumda eklendi)
engine/                ← MOTOR. Saf Python, sıfır bağımlılık.
app/                   ← Doğrulama prototipi. Sevk edilecek uygulama DEĞİL.
.claude/launch.json    ← prototip sunucu tanımı
```

### `engine/` — modüller

| Dosya | Sorumluluk |
|---|---|
| `params.py` | **96 ayarlanabilir parametrenin tamamı.** Kodda gömülü literal yok |
| `data_model.py` | Ham veri sözleşmesi, 26 kategorilik taksonomi |
| `score_engine.py` | Skor motoru. Saf fonksiyon: `Features → ScoreResult` |
| `normalize.py` | N1–N9 normalizasyon + `Features` türetme |
| `statement_ingest.py` | Ekstre ayrıştırma, tekilleştirme, kapsam |
| `behavior_infer.py` | Etiketsiz plansızlık çıkarımı + triyaj seçimi |
| `coach_tools.py` | AI koç araçları + `NumberLedger` |
| `coach_guard.py` | Sayı doğrulama + içerik kuralları + yedek şablon |
| `coach_prompt.py` | Sistem prompt'u, ton örnekleri |
| `metinler.py` | Kullanıcıya gösterilen tüm metinler |
| `screen_data.py` | Kanonik ekran veri seti üreteci (3 durum × 6 ekran) |
| `tune.py` | Parametre duyarlılık analizi |
| `fixture_didem.py` | 281 işlemlik uçtan uca sentetik fixture |
| `golden_profiles.py` | 15 kullanıcı profili (10 senaryo + 5 kapsam) |
| `test_*.py` | Test süitleri (§6) |

### Bağımlılık yönü

```
params ─┐
        ├─▶ score_engine ─▶ coach_tools ─▶ coach_guard
data_model ─┬─▶ normalize ─┘                    │
            ├─▶ statement_ingest                ▼
            └─▶ behavior_infer            coach_eval
metinler ──────────────┐
                       ▼
                  screen_data ─▶ app/server.py
```

`params.py`, `data_model.py`, `metinler.py` yaprak modüldür — hiçbir şeye
bağımlı değildir. `score_engine.py` yalnızca `params`'a bağımlıdır ve
saf/deterministiktir.

---

## 4. Komutlar

```bash
cd engine

python3 test_invariants.py     # 240 yapısal kural
python3 test_normalize.py      # 124 normalizasyon kontrolü
python3 test_ingest.py         # 109 ekstre + çıkarım kontrolü
python3 coach_eval.py          # 69 koç vakası + akış testleri

python3 golden_profiles.py     # 15 profilin skorları
python3 fixture_didem.py       # ham işlem → skor, uçtan uca
python3 screen_data.py         # screen_data.json üret

python3 tune.py                # parametre duyarlılık sıralaması
python3 tune.py --param <key>  # tek parametrenin eğrisi
python3 tune.py --set k=v      # geçici deneme + etkisi

python3 docs_sync.py           # dokümanlardaki üretilen blokları yenile
python3 docs_sync.py --check   # yalnızca doğrula (CI) — sapma varsa çıkış 1
```

Prototip (asla `python3 app/server.py`'yi Bash'te başlatma, preview aracını kullan):

```bash
python3 app/server.py          # http://localhost:8765
```

**Parametre değiştirdiysen mutlaka** `golden_profiles.py`, `test_invariants.py`
**ve** `docs_sync.py` çalıştır — sonuncusu dokümanlardaki tabloları yeniler.

---

## 5. İhlal edilemez kurallar

Bunlar tasarım tercihi değil, modelin varlık koşuludur. Birini bozan
değişiklik modeli bozar. Ayrıntı: `Docs/CONVENTIONS.md`.

1. **`score_engine` saftır.** I/O yok, rastgelelik yok, `datetime.now()`
   yok. Aynı `Features` her zaman aynı `ScoreResult`.

2. **Eksik veri ceza değildir.** Ölçemediğin şey için puan kırma;
   bileşeni devre dışı bırak, ağırlıkları yeniden normalize et, güveni
   düşür. `None` = "veri yok", `0` = "ölçüldü, sıfır çıktı". Asla karıştırma.

3. **Süreksizlik yasak.** Basamak tablosu kullanma. Girdideki %1'lik
   değişim skorda 1 puandan fazla oynatmamalı (`t_continuity` denetler).

4. **Engagement skora giremez.** Uygulama kullanımı, görev, seri, rozet —
   hiçbiri skorun girdisi değildir. Yalnızca güveni (`C`) etkiler.
   `t_no_engagement_inputs` bunu yapısal olarak engeller.

5. **LLM sayı üretmez.** Koç yanıtındaki her rakam `NumberLedger`'da
   kayıtlı olmalı. `verify_response()` geçmeden kullanıcıya gösterilmez.

6. **Skor utandırmaz.** "kötü", "başarısız", "yetersiz", "savruk",
   "disiplinsiz" kelimeleri hiçbir kullanıcı metninde geçmez. Skor bir
   ALAN hakkında konuşur, kullanıcı hakkında değil.

7. **Kullanıcı beyanı bileşen skorunu yükseltemez.** Onboarding cevapları
   yalnızca öncül skoru ve güveni etkiler.

8. **Kötü haber hızlı, iyi haber yavaş.** Yukarı hareket ±8/dönem ile
   sınırlı; maddi olayda aşağı sınır kalkar.

---

## 6. Test haritası

<!-- OTOMATIK:test-sayilari -->
*Süitler çalıştırılarak üretildi.*

| Süit | Kontrol | Ne garanti eder |
|---|---|---|
| `test_invariants.py` | **391** | Yapısal kurallar — determinizm, monotonluk, süreklilik, anti-gaming, adalet |
| `test_normalize.py` | **138** | N1–N9 normalizasyon kuralları |
| `test_ingest.py` | **109** | Ekstre ayrıştırma, tekilleştirme, davranış çıkarımı |
| `coach_eval.py` | **83** | Koç sayı sadakati, SPK sınırı, ton, akışlar |
| | **721** | |
<!-- /OTOMATIK:test-sayilari -->

**Golden vs invariant farkı:** golden testler "bu profil bu skoru alır"
der ve parametre değişince güncellenebilir. Invariant testler yapısal
kuralları denetler ve **kırılıyorsa model bozulmuştur**.

Ayrıntı: `Docs/TESTING.md`.

---

## 7. Şu anki durum

**Kilitli:**
- Skor modeli v3.0.0 — 108 parametre, 27 alt metrik, kararlar `Docs/DECISIONS.md`'de
- Veri hattı 1.0.0, ekstre alımı 1.0.0, davranış çıkarımı 1.0.0
- Koç sözleşmesi + guard 1.0.0
- Ekran mimarisi + kanonik veri seti
- Çalışan prototip

**Açık — bilinçli olarak:**
- **Kalibrasyon.** Parametreler literatür ve akıl yürütmeyle konuldu,
  gerçek kullanıcı verisiyle değil. İlk 500–1.000 kullanıcıdan sonra
  dağılıma bakılmalı; hedef medyanın 60–70 bandında olması.
- **Banka profilleri.** `statement_ingest.PROFILES` şemayı gösterir,
  gerçek bankaları değil. **Bu katmanın tek gerçek riski budur.**
- **LLM entegrasyonu.** Mimari ve guard hazır, model bağlı değil.
- **Üretim backend'i.** `app/server.py` API sözleşmesinin taslağı.

---

## 8. Daha önce yapılmış hatalar — tekrarlama

Her biri gerçekten yaşandı, testle yakalandı ve düzeltildi. Yeniden
üretilmesi kolay olduğu için buraya yazıldı.

| Hata | Belirti | Kural |
|---|---|---|
| **Kart çift sayımı** | Gider ₺19.463 yerine ₺29.978, korunan tutar negatif | Kart ödemesi, kartın işlemleri görünüyorsa gider DEĞİLDİR. Belirleyici soru "API'ye bağlı mı" değil, "işlemlerini görüyor muyuz" |
| **Türkçe harf katlama** | "ODEME" satırı alacak tanınmıyor, kart ödemesi harcama sayılıyor | Ekstre metninde `I→ı` eşlemesi KULLANMA. Banka aksansız ASCII yazar. `statement_ingest._fold` ile `coach_guard._norm` bilerek farklıdır |
| **Boş pencere = sıfır harcama** | Sabit giden fatura "oynak" işaretleniyor, 5 aylık kullanıcı 6/6 alamıyor | `active_windows()` kullan. Veri OLMAYAN pencere "sıfır harcadı" değildir |
| **Yumuşatma güveni de yutuyor** | Ekstre yükleyen sağlıklı kullanıcıya 72 yerine 55 gösteriliyor | Yumuşatma yalnızca GERÇEK finansal değişime uygulanır. Güven artışı anında yansır (`smoothing_anchor`) |
| **`effective_as_of` bağlanmamış** | Ekstre yüklenince skor DÜŞÜYOR, gelir sayılmıyor | Hesaplama tarihi son ekstre tarihine ilerlemeli |
| **Guard reddetmeyi engelliyor** | "Yatırım tavsiyesi veremem" cümlesi `investment_advice` sayılıyor | Reddetme ekleri tanınmalı (`REFUSAL_MARKERS`) |
| **Seviye eşiğinde float** | Skor 39,6 → hiçbir banda düşmüyor → "Harika gidiyorsun" | Seviye HER ZAMAN gösterilen tam sayıdan türetilir |
| **Marj sıfır noktasında uçurum** | m=0'da 12,2 puanlık sıçrama | Parçalı fonksiyonların iki dalı birleşme noktasında AYNI değeri vermeli |
| **Bayat `.pyc`** | `params.py`'de 0,10 yazarken 0,14 import ediliyor | Python önbellek geçerliliğini (mtime **saniye**, boyut) ile ölçer. Aynı boyutta ve aynı saniyede yapılan düzenleme önbelleği tazelemez. `docs_sync.py` her çalıştığında `__pycache__`'i siler |
| **Bakiye yokluğu sıfır sayılıyor** | Bakiye tutmayan kaynakta `tampon`/`guvence` 0 puan; sağlıklı kullanıcı −7,3, riskli +3,4 (r=−0,93) | `liquid_balance`/`ef_liquid` **Optional**. `sum([])` yokluğu ölçülmüş sıfır gibi gösterir — ayrımı `normalize` yapar. Ölçüt hesabın VARLIĞI, bakiyenin büyüklüğü değil |
| **Güven alt metrik körlüğü** | Girdi yüzeyinin %37'sini kaybeden kaynak yalnızca 0,09 güven kaybediyor | Kural 2 ÜÇ şey ister: bileşeni kapat, ağırlığı normalize et, **güveni düşür**. `c_pillar` artık açık bileşenin içindeki kapalı alt metriği de sayar |
| **Yinelenen ≠ iptal edilebilir** | Abonelik aksiyonu gerçek veriye bağlanınca ilk önerisi "telefon faturanı iptal et" oldu | Kira, fatura, aidat da her ay tekrarlar. Kapı taksonomideki zorunluluk ağırlığıdır (`ABONELIK_AZAMI_ZORUNLULUK`); ağırlığı BİLİNMEYEN kategori de elenir |
| **Uydurma parametre** | `abonelik_iptali` tasarrufu `e_total × %1` varsayımıydı — koç olmayan bir aboneliği iptal ettiriyordu | Aksiyon parametresi ölçülmüş veriden gelir. `_params_for` ham veriyi okur; `default_params` yalnız `Features` görür |
| **Sözleşmesiz kural** | "Eksik veri ceza değildir" üç kez sessizce bozuldu; hiçbiri test kırmadı | Kural niyet beyanı değil, BİLDİRİM olmalı. `SubScore.requires` her alt metriğin girdisini söyler; test onu boşaltıp gerçekten kapandığını denetler |
| **Yazıldı ama bağlanmadı** | `confidence`ın ekstre kademesi ve `smoothing_anchor` üretim yolunda ölüydü | Mekanizma yazmak yetmez, `derive_features` onu ÜRETMELİ. Yeni bir `Features` alanı eklerken "gerçek hat bunu dolduruyor mu" sorusu testle sorulur |
| **Paydası bilinmeyen oran** | Gelir yoksa `dsr=1,0`, gider yoksa `disc_share=0` → disiplinden **100 puan** | Oran ölçülemiyorsa `None`. Ama PAYI sıfırsa oran sıfırdır: `s_deliberate=0` gelirden bağımsız ölçülmüştür — aksi hâlde geliri gizlemek olumsuz bulguyu siler |
| **Sabit sayı iki yerde** | Guard `score < 60` yazıyordu, oysa bu `LEVELS`teki bandın alt ucu | Kural değerden değil KAYNAĞINDAN türetilir. İki yerde yazılan sayı sessizce ayrışır |
| **Ölçüm iddiası elle yazılmış** | "96 parametreden 27'si yüksek etkili" — profil sayısı 10→15 olunca bayatladı, kimse fark etmedi | Ölçüm sonucu `docs_sync` bloğundan üretilir. Ölçüm aracının kendi kapsamı hakkında yanlış konuşması ölçtüğü şeye güveni bozar |
| **Aynı fonksiyon iki kez tanımlı** | `_fold_upper`/`_rule_blob` `normalize.py`de 56 satır birebir iki kez | Python ikincisini geçerli sayar; iki kopya sessizce ayrışır. Hem de en pahalı hata sınıfının (Türkçe katlama) ortasında |
| **Tek seferlik olay eğilim gibi** | "Giyim +%148" — oysa tek taksitli alışveriş | Farkındalık kartında yeni taksit planı olan kategoriler ve "Diğer" elenir; sıralama mutlak reel TL artışına göre |

---

## 9. Dil ve üslup

- **Kod, yorum, doküman, kullanıcı metni: Türkçe.** Kod tanımlayıcıları
  (`Features`, `compute_score`) İngilizce kalır; alan adları Türkçe
  olabilir (`guvence_kademe`).
- **Yorumlar NEDEN'i anlatır**, ne yaptığını değil. Özellikle bir
  değerin neden o değer olduğunu.
- Bir hata düzeltildiğinde yorumu **hatanın kendisini** anlatmalı ki
  tekrar üretilmesin. Yukarıdaki tablo bu yorumlardan derlendi.
- Para birimi `₺` öneki, binlik ayracı nokta, ondalık virgül: `₺12.770`,
  `%24,9`. Biçimlendirme yalnızca `screen_data.tl()` / `pct()` içinde.

---

## 10. Nereye bakmalı

| Soru | Dosya |
|---|---|
| Katmanlar nasıl bağlanıyor? | `Docs/ARCHITECTURE.md` |
| Skor adım adım nasıl hesaplanıyor? | `Docs/ALGORITHM.md` |
| Şu formül / parametre ne? | `Docs/FORMULAS.md` |
| Şu alan ne anlama geliyor? | `Docs/DATA-MODEL.md` |
| Bu neden böyle yapılmış? | `Docs/DECISIONS.md` |
| Hangi kuralı bozmamalıyım? | `Docs/CONVENTIONS.md` |
| Testler ne garanti ediyor? | `Docs/TESTING.md` |
| Şu terim ne demek? | `Docs/GLOSSARY.md` |

**Gerekçeli şartnameler** (uzun, Türkçe, tasarım tartışmalarıyla):

| Konu | Dosya |
|---|---|
| Skor modeli | `Docs/skor-modeli-v2.md` |
| Veri katmanı (N1–N9) | `Docs/veri-katmani-v1.md` |
| Ekstre + davranış çıkarımı | `Docs/ekstre-alimi-v1.md` |
| AI koç | `Docs/ai-koc-v1.md` |
| Ekran mimarisi | `Docs/ekran-mimarisi-v1.md` |

---

## 11. Çalışma tarzı

- **Spec ile kod çelişirse kod esastır.** Şartnamelerdeki tüm sayısal
  örnekler kod çalıştırılarak üretildi.
- **Sayı uydurma.** Bir rakam vereceksen önce hesapla. Bu depodaki
  dokümanların tamamı bu kurala uyar.
- **Parametre değiştirmeden önce ölç.** `tune.py --set` ile etkisini gör.
  Parametrelerin küçük bir kısmı yüksek etkili, gerisi gürültü — güncel
  dağılım `Docs/skor-modeli-v2.md`'de `tune.py`'den üretilir.
- **Test yazmadan davranış değiştirme.** Özellikle §8'deki hata
  sınıflarına dokunuyorsan.
- Kullanıcı Türkçe yazar ve Türkçe yanıt bekler.
