# ALGORITHM.md — Skor Hesaplama Akışı

Bu dosya bir skorun **adım adım** nasıl üretildiğini anlatır.
Formül ve parametre değerleri için: `Docs/FORMULAS.md`.
Katman haritası için: `Docs/ARCHITECTURE.md`.

---

## 1. Üst düzey akış

```
compute_score(f: Features) → ScoreResult

 1. 6 bileşeni hesapla                    → pillar_*(f)
 2. Devre dışı olanların ağırlığını dağıt → weight_effective
 3. Ham skoru topla                       → S_ham = Σ wᵢ_norm × pᵢ
 4. Güveni hesapla                        → C
 5. Öncül skoru hesapla                   → S_öncül
 6. Harmanla                              → S_karma = C·S_ham + (1−C)·S_öncül
 7. Maddi olayları tespit et               → events
 8. Yumuşatma çapasını bul                 → anchor
 9. Yumuşat                               → S_final
10. Bant, seviye, aşama etiketi
```

---

## 2. Adım 1 — Bileşenler

Altı bileşen, her biri bağımsız hesaplanır. Ortak desen:

```python
def pillar_X(f):
    alt1 = <formül veya None>
    alt2 = <formül veya None>
    ...
    subs = [SubScore("alt1", "Etiket", alt1, P["pX.alt1.w"], detay), ...]
    return _assemble("x", "Ad", P["pX.weight"], subs, modifiers)
```

### `_assemble()` mantığı

```
aktif = [s for s in subs if s.value is not None]
if not aktif: → bileşen DEVRE DIŞI
wsum  = Σ aktif.weight
score = Σ (value × weight) / wsum        ← eksik alt metriğin ağırlığı
                                            kalanlar arasında yeniden dağılır
for m in modifiers: score *= P[m]        ← ceza çarpanları
score = clamp(score, 0, 100)
```

**Kritik:** alt metrik `None` ise ağırlığı kalanlara dağıtılır. Sıfır
puan verilmez. Bu, "eksik veri ceza değildir" ilkesinin uygulaması.

### Bileşen bazında karar noktaları

| Bileşen | Devre dışı kalma koşulu | Özel dallar |
|---|---|---|
| **P1 Nakit Akışı** | Tüm alt metrikler `None` (pratikte olmaz) | `i_net ≤ 0` → marj = 0 (None değil), maddi olay |
| **P2 Borç Yükü** | `has_debt_data = False` | Borçsuz → tek alt metrik, 100 puan · Ceza çarpanları |
| **P3 Tasarruf** | — | `real_return_gap` yoksa o alt metrik devre dışı |
| **P4 Disiplin** | — | Bütçe yoksa 2 alt metrik devre dışı, bileşen çalışır |
| **P5 Hedef** | Hedef yok **ve** gün < 60 | Hedef yok, gün ≥ 60 → 45 puan (bulgu, ceza değil) |
| **P6 Davranış** | `beh_coverage < 0,25` | Saat verisi yoksa gece metriği `None` |

### P1'in özel durumu — sıfır gelir

```python
if f.i_net <= 0:
    marj = 0.0 if f.e_total > 0 else None
```

Gelir yok ama harcama varsa bu "ölçemedik" DEĞİL, gerçek bir
kırılganlıktır. Marj sıfırlanır ve kullanıcıyı ayakta tutan tek şey
likidite tamponu olur. Ayrıca `detect_material_events` "gelir kaydı yok"
üretir (gün ≥ 30 ise).

### P2'nin özel durumu — borçsuz kullanıcı

```python
has_any_debt = (debt_principal + installment_remaining) > 0 or card_balance > 0
if not has_any_debt:
    → tek SubScore("borcsuz", 100.0), ceza yok
```

Findeks'ten farklı olarak "kredi geçmişi yok" bir risk sayılmaz.

### P2 ceza çarpanları

Bileşen skoruna uygulanır, alt metriğe değil — böylece ağırlıkla doğru
ölçeklenir.

```
days_past_due ≥ 30        → ×0,45
days_past_due ≥ 1         → ×0,70
min_only ≥ 3 ay           → ×0,65     (kronik)
min_only ≥ 1 ay           → ×0,80
kmh_active                → ×0,85
```

Çarpanlar birikimlidir (çarpılır).

---

## 3. Adım 2–3 — Ağırlık normalizasyonu ve ham skor

```python
aktif   = [p for p in pillars if p.enabled]
w_aktif = Σ aktif.weight_nominal
for p in pillars:
    p.weight_effective = 100 × p.weight_nominal / w_aktif   (aktifse)
    p.points           = p.score_100 × p.weight_effective / 100
S_ham = Σ aktif.points
```

`weight_effective` toplamı **her zaman tam 100**'dür
(`t_missing_data_never_punishes` denetler).

Örnek: borç verisi yoksa P2 (20) devre dışı → kalan 80 ağırlık 100'e
ölçeklenir → P1 25 → 31,25 olur.

---

## 4. Adım 4 — Güven (C)

```
C = 0,28·c_geçmiş + 0,22·c_kapsam + 0,20·c_bütünlük
  + 0,12·c_doğrulama + 0,18·c_bileşen

C ×= min(1, gün / 21)              ← ilk 3 hafta rampası
C ×= 0,60  eğer integrity_flag
C = clamp(C, 0, 1)
```

| Bileşen | Hesap |
|---|---|
| `c_geçmiş` | `min(1, days_of_data / 90)` |
| `c_kapsam` | **kaynağa göre** — aşağıda |
| `c_bütünlük` | `categorized_ratio` |
| `c_doğrulama` | `1 − |beyan − gözlem| / beyan`; beyan yoksa 0,40 |
| `c_bileşen` | aktif bileşen ağırlığı / toplam ağırlık |

### `c_kapsam` kademeleri — bu bir TAVAN, taban değil

```python
src = f.data_source or ("linked" if not f.manual_entry else "manual")

if src == "statement":
    c_cover = 0,85 × statement_coverage × categorized_ratio
elif src == "manual":
    c_cover = 0,45 × categorized_ratio
else:  # linked
    c_cover = accounts_linked / accounts_declared
```

**Neden tavan:** ilk sürümde `max(bağlı_oran, kademe)` yazılmıştı; kaynağı
"ekstre" olan bir kullanıcı hesapları sistemde "bağlı" işaretli olduğu
için `c_cover = 1,0` alıyordu. Tek dönem yüklemiş biri, açık bankacılığa
bağlı biriyle aynı güveni görüyordu.

**Sert eşik yok.** İlk sürümdeki "14 günden azsa C ≤ 0,15" kuralı 14.
günde C'yi 0,15'ten 0,58'e sıçratıyordu — kaldırmaya çalıştığımız türden
bir süreksizlik. 21 günlük rampa aynı korumayı sürekli sağlar.

---

## 5. Adım 5–6 — Öncül ve harmanlama

```python
S_öncül = clamp(P["prior.baz"] + Σ onboarding_puanları,
                P["prior.min"], P["prior.max"])          # [28, 75]

S_karma = C × S_ham + (1 − C) × S_öncül
```

Bu, v1'in **üç ayrı formülünün** yerini alır. Aşamalar artık kod değil,
sunum etiketidir:

```
C < 0,30 veya gün < 8   → "Farkındalık Başlangıç Skoru"
C < 0,65                → "Geçiş Skoru"          + skor BANT olarak sunulur
C ≥ 0,65                → "Finansal Sağlık Skoru"
```

Gün 30'da hiçbir süreksizlik yoktur — formül değişmez, yalnızca `C` artar.

---

## 6. Adım 7 — Maddi olaylar

```python
def detect_material_events(f) -> List[str]:
    days_past_due ≥ 30              → "30+ gün gecikmiş ödeme"
    days_past_due ≥ 1               → "gecikmiş ödeme"
    kmh_active                      → "KMH kullanımı başladı"
    min_only ≥ 3                    → "3+ ay sadece asgari ödeme"
    i_net < 0,60 × i_declared       → "gelirde %40+ düşüş"
    i_net ≤ 0 ve e_total > 0 ve gün ≥ 30 → "gelir kaydı yok"
    ef_months < 0,25                → "acil durum fonu kritik seviyede"
```

Maddi olay varsa ve yeni skor eskiden **düşükse**:
- α: 0,35 → 0,70
- ±8 sınırı **kalkar**

Yukarı yönde asla bypass yoktur.

---

## 7. Adım 8 — Yumuşatma çapası

Bu, modelin en ince parçasıdır.

```python
def smoothing_anchor(f, c_now, prior):
    if f.prev_score is None:                    return None, False
    if f.prev_raw_score is None or f.prev_confidence is None:
        return f.prev_score, False              # eski davranış (geriye uyum)

    karma_önceki = f.prev_confidence × f.prev_raw_score
                 + (1 − f.prev_confidence) × prior
    offset       = f.prev_score − karma_önceki   # birikmiş yumuşatma gecikmesi
    anchor       = c_now × f.prev_raw_score
                 + (1 − c_now) × prior + offset
    return anchor, ...
```

**Fikir:** yumuşatma, kullanıcının **finansal durumunun** skoru hızlı
oynatmasını engellemek içindir. Bizim **ölçümümüzün** düzelmesi ise onun
durumundaki bir değişiklik değil, bizim hatamızın düzelmesidir. Onu
yumuşatmak, yanlış olduğunu bildiğimiz bir sayıyı bile bile göstermektir.

`offset` korunur — geçmiş finansal değişimlerin yumuşatma gecikmesi
sürer. Yalnızca güven bileşeni bugüne taşınır.

**Ölçülen etki** (sağlıklı kullanıcı, gerçek ham skor 92):

| Aşama | Eski | Yeni |
|---|---|---|
| Gün 0 | 34–58 | 34–58 |
| 1. ekstre | 50–60 | **62–72** |
| 2. ekstre | 63 | 75 |
| 3. ekstre | 70 | 82 |
| 6. ekstre | 79 | 88 |

**Oyunlanamaz:** güven yalnızca gerçek veri yükleyerek artar ve 1'de
doyar. Tek seferlik yukarı düzeltmedir.

---

## 8. Adım 9 — Yumuşatma

```python
def smooth(new, prev, material):
    if prev is None: return new              # ilk hesaplama, yumuşatma yok

    fast  = material and new < prev
    alpha = 0,70 if fast else 0,35
    ewma  = alpha × new + (1 − alpha) × prev

    if not fast:
        lo, hi = prev − 8, prev + 8
        ewma = clamp(ewma, lo, hi)           # ±8 sınırı
    return ewma
```

`prev` burada **çapadır**, önceki gösterilen skor değil.

---

## 9. Adım 10 — Bant, seviye, aşama

```python
yarı  = max(2, 12 × (1 − C))
band  = (final − yarı, final + yarı)
```

`C = 0,25` → ±9 · `C = 0,91` → ±2.

**Seviye HER ZAMAN gösterilen tam sayıdan türetilir:**

```python
def level_of(score):
    s = int(round(score))        # ← kritik
    for lo, hi, name, msg in LEVELS:
        if lo <= s <= hi: return name, msg
```

İlk sürümde ondalıklı skor (39,6) hiçbir banda düşmüyor ve son banda
sarkıyordu: riskli kullanıcıya *"Harika gidiyorsun"* çıkıyordu.

| Skor | Seviye |
|---|---|
| 0–39 | Riskli |
| 40–59 | Dikkat |
| 60–74 | Gelişiyor |
| 75–89 | Dengeli |
| 90–100 | Güçlü |

**Sunum kuralı:** `C < 0,65` iken seviye etiketi **gösterilmez**
(`screen_data.skor_karti.seviye_goster`). 5 onboarding cevabından
türetilmiş skora "Dikkat" demek, "hiçbir zaman utandırma" ilkesinin
ihlalidir.

---

## 10. Yan akışlar

### Katkı ayrıştırma — `attribute(prev, curr)`

"Geçen döneme göre +4 puan" bu fonksiyondan gelir, LLM'den değil.

```
her bileşen için: delta = (p.points − q.points) × curr.confidence
güven değişimi:   delta = (C_yeni − C_eski) × (S_ham − S_öncül)
artık:            gösterilen fark − açıklanan toplam    ← yuvarlama
```

Toplam gösterilen farkı **tam olarak** kapatır.

### Simülasyon — `simulate(f, **changes)`

```python
d = asdict(f); d.pop("prev_score")
sim = Features(**{**d, **changes})
sim.prev_score = None          # simülasyon yumuşatmaya tabi değildir
return compute_score(sim)
```

"Bu planı uygularsan skorun 78 olur" cümlesindeki 78 buradan gelir.

### Aksiyon planı — `build_action_plan(ctx, max_steps)`

1. Her aksiyonu tek tek simüle et, `gain / effort` ile sırala
2. Kümülatif uygula — etki toplanabilir değildir
3. Kümülatif skoru **düşüren** adımı plana alma
4. Çapayı **gösterilen skora** sabitle, delta simülasyondan gelsin

4. madde önemli: simülasyon yumuşatmasız hesaplar, gösterilen skor
yumuşatılmıştır. Ham tabanı gösterirsen ana sayfada 71 yazan skor plan
ekranında "67 → 71" olur.

---

## 11. Davranış çıkarımı akışı

`derive_features()` içinde çağrılır:

```
build_signals(ledger, W0)
  → her işlem için Signals(recurring, novel, amount_z, cluster, ...)

labeled = etiketli işlemler
b0 = calibrate_intercept(labeled)      ← yalnızca kesişim kayar
w  = min(1, len(labeled) / 40)

inf_imp = Σ impulse_probability(s, b0) × tutar / toplam
lab_imp = (plansız_etiketli / etiketli) × isteğe_bağlı_pay

imp_rate = w × lab_imp + (1 − w) × inf_imp
coverage = max(0,55, w)                 ← çıkarım tek başına 0,55 üretir
```

**Gece metriği düzeltmeye tabi değildir** — saat bilgisi her işlemde
vardır, örnekleme yanlılığı yoktur. Ama ekstrelerde saat çoğunlukla
YOKTUR; içe aktarımda 00:00 yazılır ve `Signals.night = None` olur.
Saatli işlem payı %50'nin altındaysa metrik hiç hesaplanmaz.

---

## 12. Sık karıştırılan noktalar

| Kavram | Doğrusu |
|---|---|
| `S_ham` vs gösterilen skor | `S_ham` yalnızca gözlemlenen veriden; gösterilen = harmanlanmış + yumuşatılmış |
| Nakit vs tahakkuk gider | Nakit → marj, acil fon ayı. Tahakkuk → bütçe, davranış |
| `e_total` medyanı | Son 3 pencerenin medyanı, W0'ın kendisi değil |
| Davranış oranlarının paydası | `e_total` (ürünün raporladığı gibi), `e_discretionary` değil |
| `weight_nominal` vs `weight_effective` | Nominal sabit (25/20/20/15/10/10); effective devre dışı bileşenlerden sonra yeniden normalize |
| `prev_score` | Gösterilen önceki skor. Çapa hesabı için `prev_raw_score` + `prev_confidence` de gerekir |
