# Nakitio — AI Koç Katmanı, v1.0

**Durum:** Uygulanmaya hazır teknik şartname
**Referans implementasyon:** `engine/coach_tools.py`, `engine/coach_guard.py`, `engine/coach_prompt.py`
**Eval seti:** `engine/coach_eval.py` (65 vaka + 8 akış testi)
**Bağlı olduğu:** `Docs/skor-modeli-v2.md`, `Docs/veri-katmani-v1.md`

---

## 0. Bu katmanın çözdüğü tek problem

Mockup'larda (`Docs/1-3 anasayfa-nakit ai koçu.docx`) koç şunları söylüyor:

> *"Bu planı uygularsan 3 ay içinde finansal sağlık skorunu **85+** seviyesine çıkarabilirsin"*
> *"78 → **86**"* · *"₺7.070 → **₺9.800**"* · *"0,5 ay → **1,2 ay**"* · *"Tahmini tasarruf: **600 TL/ay**"*

**Bu sayılar LLM'den gelemez.** Gelirse uydurur. Finansal bir üründe bu bir
bug değil, kullanıcıya verilmiş yanlış bir taahhüttür — kullanıcı o rakama
göre karar verir.

Katmanın tamamı tek bir kuralı uygulamak için var:

```
LLM hiçbir sayı ÜRETMEZ. Yalnızca deterministik olarak hesaplanmış
sayıları ANLATIR. Ve bunu yaptığı, yanıt gösterilmeden önce DOĞRULANIR.
```

---

## 1. Mimari

```
Kullanıcı sorusu
      │
      ▼
┌─────────────────────────────────────────────────────────┐
│ ORKESTRATÖR                                              │
│  Features + ScoreResult + Ledger yükle → CoachContext    │
└─────────────────────────────────────────────────────────┘
      │
      ▼
┌─────────────────────────────────────────────────────────┐
│ ARAÇ KATMANI (coach_tools.py) — deterministik            │
│  get_score · get_score_breakdown · get_score_change      │
│  get_metric · get_top_categories · get_risks             │
│  simulate_action · build_action_plan                     │
│                                                          │
│  Döndürdüğü HER sayı → NumberLedger'a kaydedilir         │
└─────────────────────────────────────────────────────────┘
      │  araç çıktıları + sistem prompt + bağlam bloğu
      ▼
┌─────────────────────────────────────────────────────────┐
│ LLM — yalnızca anlatır                                   │
└─────────────────────────────────────────────────────────┘
      │  ham yanıt
      ▼
┌─────────────────────────────────────────────────────────┐
│ GUARD (coach_guard.py)                                   │
│  1. Sayı doğrulama: her rakam defterde var mı?           │
│  2. İçerik kuralları: SPK · kesinlik · ton · kimlik      │
│     · belirsizlik dili · somut adım · enflasyon          │
└─────────────────────────────────────────────────────────┘
      │
   GEÇTİ ──▶ kullanıcı
      │
   REDDEDİLDİ ──▶ ihlaller geri beslenir, 1 kez daha denenir
                  ──▶ yine geçmezse DETERMİNİSTİK ŞABLON
```

**Kullanıcı hiçbir koşulda doğrulanmamış bir sayı görmez.** Bozuk bir cevap,
uydurulmuş bir cevaptan iyidir.

### Prompt bir rica, guard bir garanti

Kuralların büyük kısmı hem sistem prompt'unda hem guard'da vardır. Bu
bilinçli tekrardır:

- Yalnızca prompt'a yazılan kural üretimde tutmaz — model uzun
  konuşmalarda, sıra dışı sorularda ve dil kaymalarında kayar.
- Yalnızca guard'a yazılan kural sürekli ret üretir ve ürünü kullanılmaz
  kılar.

---

## 2. Araç katmanı

| Araç | Döndürdüğü | UI karşılığı |
|---|---|---|
| `get_score` | skor, band, seviye, aşama, güven, önceki skor, değişim | Ana sayfa skor kartı |
| `get_score_breakdown` | 6 bileşen + alt metrikler + en zayıf alan | *Skor Kırılımı* kartı |
| `get_score_change` | farkın bileşenlere dağılımı | *"geçen aya göre +4 puan"* |
| `get_metric` / `get_metrics` | 19 adlandırılmış metrik | Özet kartları |
| `get_top_categories` | kategori tutarı + **nominal ve reel** değişim | *Harcama Dağılımı*, *Öne Çıkan Değişimler* |
| `get_risks` | öncelikli risk bayrakları | *Riskler* sekmesi |
| `simulate_action` | tek aksiyonun skor etkisi | *"Bu adımla 77 olur"* |
| `build_action_plan` | sıralı, **kümülatif** plan | *AI Aksiyon Planı* ekranı |

Her araç deterministiktir: aynı bağlam → aynı çıktı (`t_tools_are_deterministic`).

### Aksiyon sözlüğü

Koç serbest metinle aksiyon uyduramaz; 5 parametreli aksiyondan birini seçer:

| Aksiyon | Zorluk | Parametre |
|---|---|---|
| `abonelik_iptali` | 1 | aylık tasarruf |
| `kategori_limiti` | 2 | aylık tasarruf |
| `acil_fon_katkisi` | 2 | aylık katkı, ay |
| `plansiz_azalt` | 3 | hedef oran |
| `ek_borc_odemesi` | 3 | aylık ek ödeme, ay |

Her aksiyon `Features` üzerinde bir değişikliğe çevrilir ve `simulate()`
ile gerçekten hesaplanır.

### Plan neden kümülatif hesaplanır

Aksiyonların etkisi **toplanabilir değildir**. Aynı bileşeni doyuran iki
aksiyonun birlikte etkisi, tek tek etkilerinin toplamından küçüktür
(skor fonksiyonları doygunlaşan eğriler — `sat`, `concave`).

Koç *"toplam +9 puan"* der ve bu ayrı ayrı hesaplanmışların toplamıysa,
vaat tutmaz. `build_action_plan` her adımı bir önceki adımların **üstüne**
uygular. Regresyon: `coach_eval.t_plan_is_cumulative`.

Ayrıca kümülatif skoru **düşüren** adım plana alınmaz.

> Bu, eval yazılırken yakalanan gerçek bir hataydı: `ek_borc_odemesi`
> aksiyonu borç trendini sabit −%10'a çekiyordu. Borcu zaten −%18 hızla
> azalan bir kullanıcıda bu, "ek ödeme yap" adımının skoru **düşürmesine**
> yol açıyordu. Aksiyon artık trendi asla kötüleştirmiyor.

### Gerçek çıktı — Didem (mockup kullanıcısı)

```
build_action_plan
  Kategori limiti koy                → 75  (+2)   aylık tasarruf 640 TL
  Acil durum fonuna düzenli katkı    → 77  (+2)   aylık 1.410 TL, 3 ay
  Plansız harcamayı azalt            → 78  (+1)   hedef oran %15
  şimdi=73   plan sonrası=78   toplam=+5

get_top_categories
  Market            5.409 TL   nominal +%6,9   reel +%3,8
  Restoran & Kafe   3.984 TL   nominal +%5,3   reel +%2,5

get_risks
  [yüksek] acil durum fonu 1 aydan az — 0,7 ay
```

Koç bu sayıları anlatır; üretmez.

---

## 3. Sayı doğrulama

### Kayıt defteri

Araç çıktısındaki her sayı `NumberLedger`'a `(değer, tür, etiket, araç)`
olarak yazılır. Türler: `currency`, `percent`, `score`, `count`, `months`.

Araçların **açıklama metinlerindeki** sayılar da otomatik kaydedilir
(*"acil durum fonu 1 aydan az"* içindeki `1`). Bunlar bizim ürettiğimiz
eşiklerdir; kaydedilmezse koç kendi araç çıktısını aynen aktardığında
doğrulama onu halüsinasyon sanar.

### Metinden sayı çıkarma

```
\d{1,3}(?:\.\d{3})+(?:[.,]\d+)?     12.770 · 1.250,50
|\d+[.,]\d+                          24,9 · 7.6
|\d+                                 78
```

Nokta hem binlik hem ondalık ayracı olabilir. Kural: noktadan sonraki her
grup tam 3 haneyse binlik, değilse ondalık.

> İlk sürümde yalnızca Türkçe biçim (`12.770`, `24,9`) tanınıyordu ve
> `7.6` **iki ayrı sayıya** (7 ve 6) bölünüp doğrulamayı yanlışlıkla
> reddediyordu. LLM'ler İngilizce biçime kayar. **Doğrulayıcının aşırı
> katı olması, hiç olmaması kadar zararlıdır** — ürün sürekli yedek
> şablona düşer ve koç işe yaramaz hâle gelir.

### Tür tespiti ve eşleşme

| Bağlam | Tür | Tolerans |
|---|---|---|
| `%` veya "yüzde" bitişik | percent | ±0,5 |
| `₺` / `TL` / `lira` bitişik | currency | ±1 TL |
| "puan" / "skor" / `/100` bitişik | score | ±0,5 |
| "ay" bitişik | months | ±0,05 |
| diğer | plain | ±0,5 |

**Açık yuvarlamaya izin verilir:** 7.070 kayıtlıysa *"yaklaşık 7.000 TL"*
geçer (10/100/1000'e yuvarlama), ve rapora `approximated` olarak yazılır.

**Yapısal sayılar** (≤31 tam sayı, para/yüzde/skor bağlamında değil)
doğrulama dışıdır: gün, ay, adım sayısı, sıra. Ama `skor`/`puan` bitişikse
istisna kalkar — *"Skorun 25 puan"* reddedilir.

**Ölçek değeri 100** her zaman serbesttir (*"78/100"*).

---

## 4. İçerik kuralları

| Kural | Kod | Örnek ihlal |
|---|---|---|
| Yatırım tavsiyesi yok (SPK) | `investment_advice` | *"Birikimini altına yatır"* |
| Kesin gelecek vaadi yok | `certainty` | *"Skorun 86 olacak"*, *"garanti"* |
| Utandırıcı dil yok | `shaming` | *"Savruksun"*, *"durumun kötü"* |
| Kimlik yanıltması yok | `identity` | *"Lisanslı danışmanım"* |
| Projeksiyonda çekince zorunlu | `missing_hedge` | *"skorun 78'e çıkar"* (çekince yok) |
| Düşük güvende belirsizlik dili zorunlu | `missing_uncertainty` | C<0,65 iken *"Skorun 47/100"* |
| Düşük skorda somut adım zorunlu | `missing_next_step` | *"Skorun 35, riskli seviyede."* (tek başına) |
| Kategori artışında enflasyon (uyarı) | `missing_inflation_context` | *"Restoran +%27 arttı"* |

### SPK sınırı nerede

Ayrım dar ve nettir:

- ✅ **Bütçe yönlendirmesi serbest:** *"Birikimini acil durum fonuna aktarmayı düşünebilirsin."*
- ❌ **Enstrüman tavsiyesi yasak:** *"Şu fona yatır."*, *"Altına gir."*, *"Hisse al."*

`INVESTMENT_PATTERNS` kalıpları bu ayrımı korumak için bilerek dar tutuldu —
"acil durum **fonuna** aktar" tetiklememeli, "şu **fona yatır**" tetiklemeli.

### Ton kuralı

Skor bir **alan** hakkında konuşur, kullanıcı hakkında değil.

| Yanlış | Doğru |
|---|---|
| *"Finansal durumun kötü."* | *"Şu an gelişim alanların var; birlikte önceliklendirelim."* |
| *"Çok savruk harcıyorsun."* | *"Plansız harcamaların toplam harcamanın %8'i."* |
| *"Skorun 3 ay içinde 86 olacak."* | *"Bu adımlarla skorun 3 ay içinde 86 seviyesine çıkabilir (tahmini)."* |
| *"Restoran harcaman %27 arttı."* | *"Restoran +%27 arttı; enflasyondan arındırınca gerçek artış %22."* |

Bu, skor modelinin *"skor hiçbir zaman utandırmaz"* ilkesinin
(v1'den korunan) çalıştırılabilir hâlidir.

---

## 5. Yanıt akışı

```
guarded_reply(ctx, generate, max_attempts=2)
  deneme 1  → doğrula → geçti mi? evet: gönder
  deneme 2  → ihlaller geri beslenir → doğrula → geçti mi? evet: gönder
  yedek     → render_fallback(ctx)  (tanım gereği geçer)
```

### Yedek şablon

Tamamen deterministiktir ve yalnızca hesaplanmış sayıları kullanır.
Düşük güvende bant dilini, düşük skorda somut adımı kendisi uygular.

**Didem (C=0,91):**
> Finansal Sağlık Skorun 73/100 — Gelişiyor. En çok gelişim alanı olan
> başlık: Tasarruf & Güvence. Önerilen ilk adım: Kategori limiti koy.
> Bu adımla skorun 75 seviyesine çıkabilir (tahmini). Detayları Finansal
> Sağlık Raporu ekranından görebilirsin.

**12 günlük kullanıcı (C=0,25):**
> Farkındalık Başlangıç Skorun şu an 31–49 aralığında. Veri arttıkça bu
> aralık daralacak. En çok gelişim alanı olan başlık: Tasarruf & Güvence.
> Önerilen ilk adım: Acil durum fonuna düzenli katkı. Bu adımla skorun 42
> seviyesine çıkabilir (tahmini). Detayları Finansal Sağlık Raporu
> ekranından görebilirsin.

Bant sunumunun otomatik devreye girdiğine dikkat.

---

## 6. Bağlam bloğu sayı içermez

`build_user_context_block()` LLM'e durum özeti verir ama **hiçbir sayı
yazmaz** — yalnızca aşama, seviye, "bant olarak sun" bayrağı, zayıf
alanların adları, maddi olaylar.

Sayılar yalnızca araç çıktılarıyla gelir ve orada deftere kaydedilir.
Bağlam bloğuna sayı yazılırsa, LLM defterde olmayan bir sayıyı meşru
biçimde kullanabilir hâle gelir: doğrulamada **sessiz bir kaçak**.
Regresyon: `coach_eval.t_context_block_has_no_numbers`.

---

## 7. Eval seti

`python3 engine/coach_eval.py` — 65 vaka + 8 akış testi

| Grup | Vaka | Neyi sınar |
|---|---|---|
| sayı | 16 | Doğru sayı geçer, uydurma sayı yakalanır, yuvarlama serbest |
| spk | 11 | Enstrüman tavsiyesi yakalanır, bütçe yönlendirmesi ve **reddetme** geçer |
| kesinlik | 6 | Garanti/kesin vaat yakalanır, çekinceli projeksiyon geçer |
| ton | 8 | Utandırıcı dil yakalanır, ölçüm odaklı dil geçer |
| kimlik | 3 | İnsan/danışman iddiası yakalanır |
| belirsizlik | 5 | Düşük güvende bant dili zorunluluğu |
| adım | 4 | Düşük skorda somut adım zorunluluğu |
| enflasyon | 3 | Nominal artış tek başına uyarı üretir |
| yapısal | 5 | "3 adım" serbest, "skorun 25" değil |
| biçim | 4 | ₺ · binlik ayraçsız · ondalık virgül · sonda % |

Akış testleri: onarım döngüsü, yedeğe düşme, düşük güven/düşük skorda
yedek, plan kümülatifliği, determinizm, bağlam bloğu temizliği, bilinmeyen
araç.

### Bu eval neyi sınamaz

Guard'ı ve araç katmanını sınar — bunlar deterministiktir ve LLM olmadan
tam test edilebilir. **Gerçek modelin yanıt kalitesini sınamaz;** buradaki
"iyi" ve "kötü" yanıtlar elle kurulmuştur.

Canlı modele bağlamak için:

```python
from coach_eval import run_with_model
run_with_model(lambda system, context, question: my_llm(system, context, question))
```

Aynı guard, gerçek model çıktısı üzerinde çalışır. **İkisi ayrı şeydir ve
ayrı raporlanmalıdır:** 65 vaka guard'ı sınar, `run_with_model` modeli.

---

## 8. Üretime geçmeden önce

1. **Model seçimi ve tool-calling entegrasyonu.** `TOOL_SCHEMA` Anthropic
   Messages API formatındadır. Orkestratör: araç çağrılarını döngüde
   yürüt → `CoachContext.numbers` birikir → son yanıtı guard'dan geçir.

2. **Guard telemetrisi.** Üretimde şunlar ölçülmelidir: ret oranı, ret
   kodlarının dağılımı, yedeğe düşme oranı, onarımla kurtarılan oran.
   Yedeğe düşme oranı %5'i aşıyorsa prompt yetersizdir; ret oranı %1'in
   altındaysa guard fazla gevşek olabilir.

3. **Ton eval'ini canlı modelle genişlet.** 65 vaka guard içindir;
   modelin tonu için gerçek yanıtlar üzerinde ayrı bir insan
   değerlendirmesi gerekir.

4. **Konuşma geçmişi.** Bu sürüm tek turluk. Çok turlu konuşmada defter
   turlar arası taşınmalı, eski turların sayıları geçerliliğini
   yitirdiğinde (yeni ay, yeni skor) temizlenmelidir.

5. **Yasal metin.** Her koç ekranında: *"Bu bir kredi notu değildir"* ve
   *"Yatırım tavsiyesi değildir"* uyarıları.

6. **Aksiyon sözlüğünü genişlet.** 5 aksiyon MVP içindir. Gerçek üründe
   abonelik iptali gibi aksiyonlar tespit edilen gerçek aboneliklere
   bağlanmalıdır (veri katmanı N4 yinelenen ödeme tespiti).

---

## Ek — Dosya haritası

| Dosya | İçerik |
|---|---|
| `engine/coach_tools.py` | 8 araç, `NumberLedger`, aksiyon sözlüğü, plan kurucu |
| `engine/coach_guard.py` | Sayı çıkarımı, doğrulama, içerik kuralları, yedek şablon |
| `engine/coach_prompt.py` | Sistem prompt'u, ton örnekleri, bağlam bloğu |
| `engine/coach_eval.py` | 65 vaka + 8 akış testi + canlı model bağlantısı |

```bash
cd engine && python3 coach_eval.py
python3 coach_eval.py --show A02_uydurma_skor      # tek vakayı incele
```
