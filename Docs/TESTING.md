# TESTING.md — Test Stratejisi

Dört süit, her biri farklı bir soruya cevap verir. Güncel kontrol
sayıları `CLAUDE.md` §6'da (koddan üretiliyor).

```bash
cd engine
python3 test_invariants.py    # yapısal kurallar
python3 test_normalize.py     # N1–N9
python3 test_ingest.py        # ekstre + davranış çıkarımı
python3 coach_eval.py         # koç vakaları + akış testleri
python3 golden_profiles.py    # 15 profilin skorları
python3 fixture_didem.py      # uçtan uca: ham işlem → skor
python3 docs_sync.py --check  # dokümanlar kodla senkron mu
```

---

## 1. İki farklı test türü — karıştırma

### Golden test — "bu profil bu skoru alır"

`golden_profiles.py`. Parametre değiştiğinde **güncellenebilir**.
Beklenen aralık dışına çıkmak bir hata değil, bir sinyaldir: değişikliğin
bilerek yapıldığını doğrula ve aralığı güncelle.

### Invariant test — "bu kural asla bozulmaz"

`test_invariants.py`. Parametre değişse bile **geçmek zorundadır**.
Kırılıyorsa model bozulmuştur.

**Kritik fark:** invariant test sabit sayı varsaymaz.

```python
# KIRILGAN — her parametre kararı testi kırar
check("öncül kelepçesi", prior_score(kotu) == 40)

# SAĞLAM
check("alt kelepçe uygulanıyor", prior_score(kotu) == P["prior.min"])
```

Bu, `prior.min` 40 → 28 kararında bizzat yaşandı; test kırıldı ve
düzeltildi.

---

## 2. `test_invariants.py`

| Test | Ne garanti eder |
|---|---|
| `t_determinism` | Aynı girdi → aynı skor, aynı ham skor |
| `t_monotonicity` | 4 artan + 9 azalan metrik; iyileştirme skoru düşürmez |
| `t_continuity` | 6 metrik × 400 adım; en büyük sıçrama ≤ 1 puan |
| `t_missing_data_never_punishes` | Devre dışı bileşen 0 puan almaz, ağırlıklar 100'e normalize |
| `t_confidence_blending` | Veri arttıkça ham skora yakınsama, C ∈ [0,1], gün 29→31 uçurumu yok |
| `t_bounds` | En kötü ve en iyi profiller [0,100] içinde, kötü < iyi |
| `t_level_bands` | 0–100 arası her tam sayı tam bir banda düşer; ondalık doğru yuvarlanır |
| `t_no_engagement_inputs` | `Features`'ta ve motor kaynağında engagement yok |
| `t_self_report_cannot_raise_pillars` | Beyan ham skoru değiştirmez, etkisi sönümlenir |
| `t_asymmetric_smoothing` | Yukarı ±8 sınırlı, maddi olayda aşağı sınır kalkar |
| `t_confidence_change_is_not_smoothed` | Güven artışı anında, finansal düşüş yumuşatılmış |
| `t_fairness_income_neutral` | ×0,25–×8 ölçekte yayılım < 0,5 puan |
| `t_math_helpers` | `lin`, `sat`, `concave`, öncül kelepçesi |

### Neden bunlar

Her invariant, ya bir tasarım ilkesinin ya da yaşanmış bir hatanın
koruyucusudur:

- `t_continuity` → v1'in basamak tabloları
- `t_level_bands` → skor 39,6'nın "Güçlü" banda sarkması
- `t_no_engagement_inputs` → v1'in görev başına +2 puanı
- `t_confidence_change_is_not_smoothed` → ekstre yükleyene 55 gösterme

---

## 3. `test_normalize.py`

| Test | Ne garanti eder |
|---|---|
| `t_n1_internal_transfer` | Transfer hem gelirden hem giderden düşer, birikim akışına yazılır |
| `t_n1_no_false_match` | 3 günden uzak aralık eşleşmez |
| **`t_n2_linked_card_no_double_count`** | **10.000 TL kart harcaması + 10.000 TL ödeme → gider 10.000, 20.000 değil** |
| `t_n2_unlinked_card_is_proxy` | Bağlantısız kart ödemesi gider olarak sayılır |
| `t_n3_installments` | Plan doğru, kalan taahhüt doğru, nakit/tahakkuk farklı |
| `t_n3_followups_not_double_counted` | Sonraki taksitler tekil gider sayılmaz |
| `t_n4_amortization` | Yıllık prim 12'ye bölünür; amortismansız 3,75× fark |
| `t_n5_inflation` | Düzeltme yönü ve kategori bazlılığı |
| `t_n6_valuation_not_savings` | Değer artışı tasarruf sayılmaz |
| `t_n7_refund` | İade harcamayı netler, gelir sayılmaz |
| `t_n8_outlier` | Aykırı değer medyan geliri bozmaz |
| `t_n9_categorization` | Öncelik: kullanıcı > kural > MCC > diğer |
| `t_essential_weighting` | Kesirli ağırlık doğru toplanır |
| `t_short_history_not_penalized` | Boş pencere elenir, 5 aylık kullanıcı 6/6 alabilir |
| `t_end_to_end_*` | Determinizm ve makullük |

**En kritik test `t_n2_linked_card_no_double_count`.** Kart çift sayımı
prototip kurulurken bir kez daha ortaya çıktı (`is_linked` semantiği
yüzünden) — bu test o sınıfın nöbetçisi.

---

## 4. `test_ingest.py`

| Grup | Testler |
|---|---|
| **Ayrıştırma** | `t_amount_parsing`, `t_parse_account_csv`, `t_parse_debit_credit`, `t_parse_card_pdf`, `t_installment_detection`, `t_bad_profile_warns` |
| **İçe aktarma** | `t_import_and_dedup`, `t_overlapping_periods`, `t_card_import_gives_debt_snapshot`, `t_fingerprint_sensitivity` |
| **Kapsam / tarih** | `t_coverage_and_gaps`, `t_effective_as_of`, `t_password_required` |
| **Çıkarım** | `t_impulse_signal_directions`, `t_emotion_is_weak_by_design`, `t_calibration` |
| **Harman** | `t_behavior_without_labels`, `t_labels_shift_estimate`, `t_triage_selection` |
| **Güven** | `t_confidence_tiers` |
| **Uçtan uca** | `t_end_to_end_from_statements` |

**`t_behavior_without_labels`** en önemlisi: hiç etiket yokken davranış
bileşeni **çalışmaya devam etmeli**. Bu, ekstre modelinin yaşayabilirlik
koşulu.

**`t_emotion_is_weak_by_design`** ilginç bir test: duygu çıkarımının
*fazla iddialı olmadığını* denetler. Sinyaller yığılsa bile 0,90'ı
geçmemeli ve plansızlık tahmininden temkinli olmalı.

---

## 5. `coach_eval.py`

| Grup | Vaka | Ne sınar |
|---|---|---|
| sayı | 16 | Doğru sayı geçer, uydurma yakalanır, yuvarlama serbest |
| spk | 11 | Enstrüman tavsiyesi yakalanır, bütçe yönlendirmesi ve **reddetme** geçer |
| kesinlik | 6 | Garanti/kesin vaat yakalanır, çekinceli projeksiyon geçer |
| ton | 8 | Utandırıcı dil yakalanır, ölçüm odaklı dil geçer |
| kimlik | 3 | İnsan/danışman iddiası yakalanır |
| belirsizlik | 5 | Düşük güvende bant dili zorunluluğu |
| adım | 4 | Düşük skorda somut adım zorunluluğu |
| enflasyon | 3 | Nominal artış tek başına uyarı üretir |
| yapısal | 5 | "3 adım" serbest, "skorun 25" değil |
| biçim | 4 | ₺ · binlik ayraçsız · ondalık virgül · sonda % |

Akış testleri: onarım döngüsü, yedeğe düşme, düşük güven/skorda yedek,
plan kümülatifliği, determinizm, bağlam bloğu temizliği, bilinmeyen araç.

### Bu eval neyi sınamaz

Guard'ı ve araç katmanını sınar — deterministik, LLM olmadan tam test
edilebilir. **Gerçek modelin yanıt kalitesini sınamaz;** buradaki "iyi" ve
"kötü" yanıtlar elle kurulmuştur.

Canlı modele bağlamak için:

```python
from coach_eval import run_with_model
run_with_model(lambda system, context, question: my_llm(...))
```

İkisi ayrı şeydir ve **ayrı raporlanmalıdır**.

---

## 6. Golden profiller

15 profil: 10 gerçekçi senaryo + 5 kod yolu kapsamı.

<!-- OTOMATIK:golden-skorlar -->
*`golden_profiles.py` çalıştırılarak üretildi.*

| Profil | Skor | Band | C | Ne temsil eder |
|---|---|---|---|---|
| `didem` | **73** | 71–75 | 0,9 | Mockup kullanıcısı — maaşlı, dengeli, orta borç |
| `mehmet` | **33** | 31–35 | 0,86 | Kart sarmalı — asgari ödeme, gecikme, KMH |
| `zeynep` | **83** | 81–85 | 0,97 | Serbest çalışan — yüksek gelir oynaklığı, borçsuz, iyi birikim |
| `can` | **39** | 30–49 | 0,21 | 12 günlük yeni kullanıcı — veri yok denecek kadar az |
| `elif` | **90** | 88–92 | 0,98 | Güçlü — yüksek tasarruf, 6+ ay güvence, borçsuz |
| `burak` | **60** | 58–62 | 0,97 | Taksit yüklü — nakit akışı iyi görünüyor, taahhüt ağır |
| `deniz` | **78** | 76–80 | 0,84 | Öğrenci — düşük gelir, yüksek disiplin, borçsuz |
| `selin` | **40** | 38–42 | 0,98 | Yüksek gelir, sıfır tampon — gizli risk |
| `ahmet` | **83** | 81–85 | 0,83 | Emekli — düşük gelir, borçsuz, enflasyona yeniliyor |
| `merve` | **50** | 44–55 | 0,54 | Gün 25 — geçiş dönemi, kısmi veri |
| `emre` | **67** | 64–69 | 0,78 | Ekstre kullanıcısı — gelir beyanı yok, 4/6 dönem yüklü |
| `hakan` | **35** | 33–37 | 0,82 | 45 gün gecikme + 2 ay asgari ödeme — sarmalın başı |
| `sibel` | **36** | 34–39 | 0,81 | Negatif nakit akışı — gider gelirden %20 fazla |
| `tolga` | **58** | 56–60 | 0,93 | Ulaşılamaz hedef koymuş, skoru hızla iyileşiyor |
| `nur` | **81** | 75–86 | 0,53 | Toplu işlem silme tespit edildi — güven düşürüldü |
| `okan` | **69** | 67–71 | 0,97 | Taksitle yaşayan — aynı borç hacmi, faizsiz |
| `pelin` | **66** | 64–68 | 0,97 | Kart döneri — aynı borç hacmi, yıllık %65 faiz |
| `kerem` | **46** | 44–48 | 0,98 | Ev sahibi — net varlık yüksek, nakit akışı negatif |
<!-- /OTOMATIK:golden-skorlar -->

Son beşi **kapsam** için eklendi: duyarlılık analizi 16 parametreyi
"etkisiz" sanıyordu; aslında hiçbir profil o kod yolundan geçmiyordu.

### Modelin iddialarını sınayan üçlü

- **deniz (78) > selin (40)** — ₺12.000 gelirli disiplinli öğrenci,
  ₺85.000 gelirli savruktan yüksek. Skor gelir seviyesini değil ilişkiyi
  ölçüyor.
- **burak (61)** — nakit akışı pozitif ama ₺76.000 kalan taksit taahhüdü.
  v1 bu kullanıcıyı "iyi" görürdü.
- **can (40, band 31–49)** — 12 günlük kullanıcı. Skor öncüle yakın, band
  geniş, hiçbir bileşen veri yokluğundan 0 almadı.

---

## 7. Uçtan uca fixture

`fixture_didem.py` — 281 sentetik ham işlem, her N kuralını bilerek
tetikler:

| Kural | Fixture'daki tetikleyici |
|---|---|
| N1 | Aylık birikim transferleri (10 çift) |
| N2 | Kredi kartı ekstre ödemeleri (5) |
| N3 | İki taksit planı (6×900, 4×900) |
| N4 | Yıllık kasko primi ₺8.400 → ₺700/ay |
| N5 | Dönemler arası TÜFE farkı |
| N7 | İade edilmiş giyim alışverişi |
| N8 | ₺95.000 toplu hakediş |

**Sonuç: 75** (ham 76,4 · C 0,98). Elle kurulmuş `golden_profiles.didem`
ise **73** verir.

### Bu iki sayı özdeş değildir — ve olmamalıdır

İlk sürümde burada *"fixture golden ile aynı skoru veriyor, demek ki hat
tutarlı"* yazıyordu. Bu iddia yanlıştı: iki "didem" **aynı kullanıcı
değil.**

`Features`'ın 25 alanı (bakiyeler, borç, kart limiti, onboarding) bilerek
aynı tutulmuştur; ama **24 akış alanı** 281 işlemden türetildiği için
farklı çıkar — gelir 28.450 → 27.890, gider 21.380 → 19.463, plansızlık
%23 → %12. En belirgini: **golden profilin hiç taksiti yok**
(`installment_remaining = 0`), fixture'ın iki aktif planı var.

Yani bu bir *"aynı girdi → aynı çıktı"* denetimi değildir. Onu
`t_determinism` yapar ve fixture'ın orada söyleyecek sözü yoktur.

### Fixture gerçekte neyi garanti eder

**281 ham işlem hattın tamamından geçtiğinde N1–N9'un hepsi tetikleniyor
ve sonuç elle kurulmuş profille aynı komşulukta kalıyor** — 2 puan fark.

Değeri buradadır: bir N kuralı sessizce atlanırsa fark 2 puan olmaz.
Yalnızca N2 çift sayımı gideri ₺19.463'ten ₺29.978'e çıkarır (%54) ve
skoru onlarca puan oynatır. Fixture'ın 73–75 aralığında kalması, hattın
hiçbir yerinde böyle bir kopukluk olmadığının kanıtıdır.

Bu yüzden fixture'ın beklentisi **tek bir sayı değil, bir aralık** olarak
okunmalıdır; parametre kararları iki tarafı farklı miktarlarda oynatır.

---

## 8. Yeni test yazarken

### Invariant mi golden mi?

- Değer değişse de geçmeli mi? → **invariant**
- "Bu profil şu skoru alır" mı? → **golden**

### Invariant testte sabit sayı yazma

```python
from params import P as _P
check("...", deger == _P["anahtar"])
```

### Maddi olay tuzağı

Bir kötüleşme senaryosu kurarken dikkat: acil fonu sıfırlamak, gecikmeye
düşürmek, KMH açmak **maddi olaydır** ve yumuşatma sınırını bilerek
kaldırır. Sıradan bir kötüleşme ölçmek istiyorsan bu eşiklerin üstünde
kal.

Bu, `t_confidence_change_is_not_smoothed` yazılırken bizzat yaşandı —
test kırıldı, kod doğruydu.

### Yeni kod yolu eklediysen kapsam profili ekle

`tune.py` çıktısında "⚠ ÖLÇÜLEMEDİ" bölümüne bak. Oradaki parametreler
"etkisiz" değil, **hiç tetiklenmemiş** demektir.

---

## 9. Doküman senkronu

`docs_sync.py` dokümanlardaki **koddan türetilebilen** blokları üretir ve
doğrular. `<!-- OTOMATIK:ad -->` … `<!-- /OTOMATIK:ad -->` işaretleri
arasındaki içerik ona aittir; dışarısı elle yazılmıştır.

| Blok | Nerede | Kaynak |
|---|---|---|
| `params-tablosu` | `FORMULAS.md` §8 | `params.P` + `params.M` |
| `norm-sabitleri` | `FORMULAS.md` §9 | modül sabitleri |
| `davranis-katsayilari` | `FORMULAS.md` §6 | `behavior_infer.W` |
| `kategori-tablosu` | `FORMULAS.md` §7 | `CATEGORIES` + `CATEGORY_IMPULSE_PRIOR` |
| `golden-skorlar` | `TESTING.md` §6 | `golden_profiles` çalıştırılır |
| `test-sayilari` | `CLAUDE.md` §6 | süitler çalıştırılır |
| `sm-sureklilik` | `skor-modeli-v2.md` §5 | `veri_sureklilik()` |
| `sm-belirsizlik-bandi` | `skor-modeli-v2.md` §7 | `can` + `didem` bandı |
| `sm-maddi-olay` | `skor-modeli-v2.md` §8 | `veri_maddi_olay()` |
| `sm-golden-senaryo` | `skor-modeli-v2.md` §10 | `senaryo_profilleri()` |
| `sm-didem-kirilim` | `skor-modeli-v2.md` §10 | `didem`'in `explain()`'i |
| `sm-sinir-durumlari` | `skor-modeli-v2.md` §11 | `veri_sinir_durumlari()` |
| `sm-simulasyon` | `skor-modeli-v2.md` §13 | `veri_simulasyon()` |

### `sm-*` blokları neden sonradan eklendi

`skor-modeli-v2.md` deponun en eski şartnamesidir ve uzun süre işaretsiz
kaldı. 12 Ağu parametre kararları (`prior.baz` 50→40, `prior.min` 40→28,
`p3.guvence.tam_ay` 6→3) elle yazılmış tablolarını geçersiz kıldı ama
`--check` bunu göremedi — işaretlerin dışındaki metne bu araç dokunmaz.
Sonuç: depo aynı commit'te `didem` için hem **73** (üretilen blok) hem
**74** (elle yazılan tablo) taşıyordu.

Bu bloklar `golden_profiles.veri_*()` **saf fonksiyonlarını** çağırır;
hesap orada tek yerde durur. `run_*()` yazdırıcıları da aynı fonksiyonları
kullanır — CLI çıktısı ile doküman aynı kaynaktan beslenmezse aradaki
sapma bu kez kod içinde doğardı.

Ayrıca üretilmeyen ama koda bağlı iddiaları doğrular: dokümanlardaki
dosya yolları var mı, geçen parametre adları `params.py`'de mevcut mu,
bileşen ağırlıkları 100 ediyor mu.

`--check` hiçbir dosyaya yazmaz; sapma varsa çıkış kodu 1.

---

## 10. CI için önerilen sıra

```bash
cd engine
python3 test_invariants.py   || exit 1    # en hızlı, en temel
python3 test_normalize.py    || exit 1
python3 test_ingest.py       || exit 1
python3 coach_eval.py        || exit 1
python3 golden_profiles.py   || exit 1    # skor kayması görünür
python3 fixture_didem.py     || exit 1    # uçtan uca
python3 screen_data.py       || exit 1    # ekran verisi üretilebiliyor mu
python3 docs_sync.py --check || exit 1    # dokümanlar kodla senkron mu
```

Hepsi bağımsız çalışır, sıfır bağımsızlık gerektirir, saniyeler sürer.
