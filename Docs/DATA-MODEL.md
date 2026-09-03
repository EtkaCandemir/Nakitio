# DATA-MODEL.md — Veri Sözleşmeleri

Her veri yapısı, her alan, her alanın anlamı. Kaynak: `engine/data_model.py`
ve `engine/score_engine.py`.

---

## 0. İki temel kural

### `None` ≠ `0`

```
None  →  "veri yok / ölçemedik"     → alt metrik devre dışı, ağırlık dağıtılır
0     →  "ölçtük, sıfır çıktı"      → normal hesaplanır
```

Bu ayrım modelin bel kemiğidir. Karıştırmak "eksik veri ceza değildir"
ilkesini bozar.

### Para birimi

Referans implementasyon `float` kullanır — okunabilirlik için.
**Üretimde para asla `float` tutulmaz**: kuruş cinsinden `int` veya
`Decimal`. Kayan nokta hatası bir finans uygulamasında mutabakat bozar.

---

## 1. `Features` — katmanlar arası sözleşme

Skor motorunun **tek girdisi**. Normalizasyondan geçmiş, enflasyondan
arındırılmış, amortize edilmiş, iç transferlerden temizlenmiş değerler.

### Kimlik / dönem

| Alan | Tip | Anlam |
|---|---|---|
| `user_id` | `str` | Kullanıcı kimliği |
| `days_of_data` | `int` | İlk işlemden `as_of`'a geçen gün |

### Gelir

| Alan | Tip | Anlam |
|---|---|---|
| `i_net` | `float` | Son 3 pencerenin net gelir **medyanı** |
| `i_cv` | `float?` | Son 6 pencerenin varyasyon katsayısı (std/ort), **reel** değerle |
| `i_primary_share` | `float?` | En büyük gelir kaynağının payı `[0,1]` |
| `i_declared` | `float?` | Onboarding'de beyan edilen aylık net |

`i_net ≤ 0` özel bir durumdur — bkz. `Docs/ALGORITHM.md` §2.

### Gider

| Alan | Tip | Anlam |
|---|---|---|
| `e_total` | `float` | Amortize toplam gider, **nakit görünüm**, 3 pencere medyanı |
| `e_essential` | `float` | `Σ tutar × essential_weight` — kesirli ağırlıkla |
| `liquid_balance` | `float?` | Vadesiz + nakit hesap bakiyeleri. **`None` = likit hesap yok, ölçülemedi** — `tampon` alt metriği devre dışı kalır. `0.0` = hesap var, bakiyesi sıfır (ölçüldü) |

Transfer, kart ödemesi ve iade **dahil değildir**.

### Tasarruf & güvence

| Alan | Tip | Anlam |
|---|---|---|
| `s_deliberate` | `float` | **Kasıtlı** birikim — net transfer, değerleme hariç |
| `ef_liquid` | `float?` | Acil durum fonu (`is_emergency_fund` hesapları). **`None` = böyle hesap yok** — `guvence` alt metriği devre dışı kalır |
| `s_consistency_months` | `int` | Son 6 pencerenin kaçında pozitif katkı, 6'lık ölçeğe yansıtılmış |
| `real_return_gap` | `float?` | Yıllık (birikim getirisi − TÜFE). Portföy geçmişi gerektirir |

**`s_deliberate` ≠ `i_net − e_total`.** v1'in en büyük hatası buydu:
tasarruf artık bakiye olarak tanımlıydı ve `Harcama Kontrolü` ile
matematiksel olarak aynı değişkendi.

### Borç

| Alan | Tip | Anlam |
|---|---|---|
| `has_debt_data` | `bool` | Borç verisi bağlandı mı. `False` → P2 devre dışı |
| `debt_principal` | `float` | Krediler + **döner** kart borcu. Taksit HARİÇ |
| `debt_monthly_service` | `float` | `Σ Liability.monthly_payment` |
| `installment_monthly` | `float` | Cari pencereye düşen taksit |
| `installment_remaining` | `float` | Kalan toplam taksit taahhüdü |
| `card_balance` | `float?` | Kart bakiyesi — yalnızca kullanım oranı için |
| `card_limit` | `float?` | Kart limiti |
| `debt_trend_3m` | `float?` | `(anapara_şimdi / anapara_3ay_önce) − 1`. **Yalnızca ölçülmüş geçmişten** |
| `days_past_due` | `int` | Gecikme günü (maksimum) |
| `min_payment_only_months` | `int` | Üst üste sadece asgari ödenen ay |
| `kmh_active` | `bool` | Kredili mevduat kullanımı |

**`debt_principal` ve `installment_remaining` çakışmaz** — `COMMIT`
hesabında ikisi toplanır. `card_balance` `COMMIT`'e girmez; farklı bir
olguyu (limite yakınlık) ölçer.

### Harcama disiplini

| Alan | Tip | Anlam |
|---|---|---|
| `budget_planned` | `float?` | Bütçelenen toplam |
| `budget_overrun` | `float?` | Kategori bazlı **aşım** toplamı (yalnız pozitif kısım) |
| `limit_categories` | `int?` | Limitli kategori sayısı |
| `limit_breached` | `int?` | Aşılan kategori sayısı (%5 toleransla) |
| `cat_volatility` | `float?` | Kategori harcamalarının pencereler arası ort. CV'si |

### Hedefler

| Alan | Tip | Anlam |
|---|---|---|
| `goals_active` | `int` | Aktif hedef sayısı |
| `goal_ontrack` | `float?` | Hedef büyüklüğüne göre ağırlıklı ilerleme `[0,1]` |
| `goal_consistency` | `float?` | Son 3 dönemde plana uyan hedef oranı |
| `goal_required_monthly` | `float?` | Tüm hedefler için gereken aylık katkı |

### Davranış

| Alan | Tip | Anlam |
|---|---|---|
| `beh_coverage` | `float` | Etkin kapsam. `< 0,25` → P6 devre dışı |
| `imp_rate` | `float?` | Plansız TL / `e_total` |
| `emo_rate` | `float?` | Duygusal TL / `e_total` |
| `night_conc` | `float?` | 20:00–02:00 TL / `e_total`. Saat verisi yoksa `None` |
| `regret_rate` | `float?` | Düşük memnuniyet TL / puanlanan TL |

Bu oranlar `behavior_infer.estimate_behavior()` tarafından üretilir —
çıkarım + etiket harmanı.

### Veri güveni

| Alan | Tip | Anlam |
|---|---|---|
| `accounts_declared` | `int` | Beyan edilen hesap sayısı |
| `accounts_linked` | `int` | Otomatik bağlı hesap sayısı |
| `categorized_ratio` | `float` | Kategorize edilmiş TL / toplam TL |
| `manual_entry` | `bool` | Geriye dönük uyumluluk; `data_source` yoksa kullanılır |
| `integrity_flag` | `bool` | Toplu silme/şüpheli düzenleme |
| `data_source` | `str?` | `"linked"` · `"statement"` · `"manual"` · `None` |
| `statement_coverage` | `float?` | Son 6 ayın kaçında ekstre var `[0,1]` |

### Önceki dönem

| Alan | Tip | Anlam |
|---|---|---|
| `prev_score` | `float?` | Önceki dönemin **gösterilen** skoru |
| `prev_raw_score` | `float?` | Önceki dönemin **ham** skoru |
| `prev_confidence` | `float?` | Önceki dönemin güveni |

Son ikisi `smoothing_anchor()` için gereklidir. Yoksa eski davranışa
düşülür (çapa = `prev_score`).

### Türetilmiş özellikler (property)

| Property | Formül |
|---|---|
| `cf_margin` | `(i_net − e_total) / i_net`; `i_net ≤ 0` → 0 |
| `s_rate` | `s_deliberate / i_net` |
| `ef_months` | `ef_liquid / e_essential` (yoksa `e_total`) |
| `dsr` | `(debt_monthly_service + installment_monthly) / i_net` |
| `commit_ratio` | `(debt_principal + installment_remaining) / (i_net × 12)` |
| `card_utilization` | `card_balance / card_limit`; limit yoksa `None` |
| `ef_months` | `ef_liquid / e_essential` (paydası 0 ise `e_total`); acil fon yoksa `None` |
| `runway_days` | `liquid_balance / (e_total / 30)`; bakiye yoksa `None` |
| `disc_share` | `(e_total − e_essential) / e_total` |

---

## 2. `ScoreResult` — motor çıktısı

| Alan | Tip | Anlam |
|---|---|---|
| `model_version` | `str` | `MODEL_VERSION` |
| `score` | `int` | **Gösterilen** skor |
| `band` | `(int, int)` | Belirsizlik bandı |
| `raw_score` | `float` | `S_ham` — yalnız gözlemlenen veriden |
| `prior_score` | `float` | `S_öncül` |
| `blended_score` | `float` | `S_karma` |
| `confidence` | `float` | `C ∈ [0,1]` |
| `stage_label` | `str` | Farkındalık Başlangıç / Geçiş / Finansal Sağlık |
| `level` | `str` | Riskli / Dikkat / Gelişiyor / Dengeli / Güçlü |
| `message` | `str` | Seviye mesajı |
| `pillars` | `List[Pillar]` | 6 bileşen |
| `smoothing` | `dict` | `applied`, `alpha`, `cap_applied`, `material_bypass`, `guven_duzeltmesi` |
| `material_events` | `List[str]` | Tespit edilen maddi olaylar |

`.explain()` insan okunur kırılım döner.

### `Pillar`

| Alan | Anlam |
|---|---|
| `key`, `label` | `cashflow`, `debt`, … / Türkçe ad |
| `weight_nominal` | Sabit ağırlık (25/20/20/15/10/10) |
| `weight_effective` | Devre dışı bileşenlerden sonra yeniden normalize |
| `score_100` | Bileşen skoru `[0,100]`, `None` = devre dışı |
| `points` | Toplam skora katkı |
| `enabled` | Aktif mi |
| `subs` | `List[SubScore]` |
| `modifiers` | Uygulanan ceza çarpanları |
| `disabled_reason` | Devre dışıysa neden |

### `SubScore`

`key`, `label`, `value` (`None` = ölçülemedi), `weight` (bileşen içi),
`detail` (UI'da gösterilecek kısa açıklama).

---

## 3. Ham veri modeli

### `Account`

| Alan | Anlam |
|---|---|
| `type` | `checking`, `cash`, `savings`, `credit_card`, `kmh`, `loan`, `gold`, `fx`, `fund`, `crypto` |
| `balance` | Güncel bakiye (kart için borç, pozitif) |
| `credit_limit`, `statement_day`, `due_day` | Kart alanları |
| `is_linked` | Otomatik bağlantı mı |
| `is_emergency_fund` | Acil durum fonu olarak işaretli mi |

```
LIQUID_TYPES   = {checking, cash}
SAVINGS_TYPES  = {savings, gold, fx, fund, crypto}
```

> `is_linked` **N2'de kullanılmaz.** Belirleyici soru "API'ye bağlı mı"
> değil, "bu hesabın işlemlerini görüyor muyuz". Ekstre modelinde bir
> kart bağlı olmadan da tamamen görünür olabilir.

### `Transaction`

**İşaret kuralı:** hesap perspektifinden. Çıkış negatif, giriş pozitif.
Kredi kartında harcama negatif, ödeme pozitif. İstisnasız.

| Alan | Anlam |
|---|---|
| `ts` | İşlem/tahakkuk zamanı. Ekstrede saat yoksa 00:00 |
| `amount`, `currency`, `fx_rate` | Tutar ve kur |
| `description_raw`, `merchant_raw`, `mcc` | Ham metin |
| `installment_index/count` | `3/12`'nin 3'ü ve 12'si |
| **Normalizasyon çıktıları** | |
| `kind` | `TxnKind` |
| `category`, `category_source` | Kategori ve kaynağı |
| `merchant_id` | Normalleştirilmiş merchant anahtarı |
| `is_internal_transfer`, `counterpart_id` | N1 |
| `installment_plan_id` | N3 |
| `recurrence_id`, `amortized` | N4 |
| `is_unusual` | N8 |
| `refunded_amount` | N7 ile netlenen tutar |
| `excluded_reason` | Gider dışı bırakıldıysa neden |

Property: `try_amount`, `outflow` (iade netlenmiş), `inflow`.

### `TxnKind`

```
INCOME · PURCHASE · TRANSFER_IN/OUT · CARD_PAYMENT · LOAN_PAYMENT
SAVINGS_CONTRIB/WITHDRAW · FEE · INTEREST · REFUND · CASH_WITHDRAWAL

EXPENSE_KINDS = {PURCHASE, FEE, INTEREST}
```

`TRANSFER_*` ve `CARD_PAYMENT` bilerek dışarıdadır — N1 ve N2.

### `Category`

`key`, `label`, `essential_weight ∈ [0,1]`, `cpi_group` (TÜİK COICOP).
25 kategori. Tablo: `Docs/FORMULAS.md` §7.

### `InstallmentPlan`

`total_amount`, `count`, `monthly_amount`, `start`, `category`.
Metotlar: `remaining_after(as_of)`, `due_in_window(start, end)`.

### `Liability`

`type` (`consumer_loan`, `mortgage`, `auto`, `card_revolving`, `kmh`),
`principal_outstanding`, `monthly_payment`, `days_past_due`,
`min_payment_only_months`.

### `Goal`

`target_amount`, `current_amount`, `created_at`, `target_date`,
`monthly_plan`, `linked_account_id`, `contribution_history: List[bool]`.

### `BehaviorTag`

`txn_id`, `planned: bool?`, `emotion: str?`, `satisfaction: 1|2|3?`.

```
EMOTIONAL_TAGS = {stres, odul, can_sikintisi}
```

### `RawData`

Tüm ham veriyi taşıyan kap: hesaplar, işlemler, borçlar, hedefler,
bütçeler, davranış etiketleri, gelir beyanı, onboarding, TÜFE,
`debt_principal_history`, `deleted_txn_ratio`, `prev_score`.

`debt_principal_history: [(tarih, anapara)]` — **borç trendi yalnızca
buradan hesaplanır**, işlem akışından tahmin edilmez.

---

## 4. Ekstre alım modeli

### `BankProfile`

Bir bankanın bir ekstre türü için ayrıştırma tarifi. **Veri kaydıdır**;
yeni banka eklemek kod değil konfigürasyondur.

| Alan | Anlam |
|---|---|
| `doc_kind` | `account` \| `card` |
| `fmt` | `delimited` \| `pdf_text` |
| `delimiter`, `col_*` | Delimited alanları |
| `line_re` | PDF satır regex'i (`date`, `desc`, `amount` grupları) |
| `header_re` | Üstbilgi desenleri (dönem, bakiye, asgari, son ödeme) |
| `date_formats`, `decimal` | Biçim |
| `credit_markers` | İşareti ters çeviren kelimeler |
| `password_hint` | Parola kuralı ipucu |

### `ParsedStatement`

`bank`, `doc_kind`, `account_ref`, `period_start/end`, `rows`,
`closing_balance`, `minimum_payment`, `due_date`, `warnings`.
`.key` — aynı ekstrenin ikinci kez yüklendiğini anlamak için hash.

### `ImportResult`

`statement_key`, `added`, `duplicates`, `rows_total`, `period`,
`warnings`, `debt_snapshot`.

---

## 5. Davranış çıkarımı modeli

### `Signals`

Bir işlem için ekstreden çıkarılabilen sinyaller:
`category`, `amount`, `recurring`, `merchant_novel`, `amount_z`,
`cluster_size`, `is_installment`, `days_since_income`, `weekend`,
`refunded`, `night` (`None` = saat bilinmiyor).

### `BehaviorEstimate`

`imp_rate`, `emo_rate`, `regret_rate`, `night_conc`, `label_weight`,
`label_count`, `inferred_only`, `coverage`, `b0`, `time_available`.

---

## 6. Koç modeli

### `NumberLedger` / `NumberRecord`

Bağlama giren her sayının kaydı: `value`, `kind`, `label`, `tool`.
`Kind`: `currency`, `percent`, `score`, `count`, `months`.

Doğrulayıcı LLM yanıtındaki her rakamı buraya karşı kontrol eder.

### `CoachContext`

`features`, `score`, `prev_score`, `ledger`, `as_of`, `numbers`.
Property `low_confidence` → `C < P["stage.saglik_C"]`.

### `GuardReport` / `Violation`

`ok`, `violations`, `checked_numbers`, `approximated`, `structural`.
`Violation`: `code`, `severity` (`blocker` \| `warning`), `detail`.

İhlal kodları: `hallucinated_number`, `investment_advice`, `certainty`,
`shaming`, `identity`, `missing_hedge`, `missing_uncertainty`,
`missing_next_step`, `missing_inflation_context`.

---

## 7. Pencere modeli

```python
Window(start, end)        # end dışlayıcı
windows(as_of, n=6)       # W0 = (as_of−30, as_of], W1, ...
active_windows(ledger, W) # yalnızca İÇİNDE VERİ OLAN pencereler
```

**Boş pencere "sıfır harcama" değildir.** `active_windows()` kullanmamak,
kısa geçmişli kullanıcıyı cezalandırır — sabit giden bir fatura "oynak"
görünür, her ay biriktiren kullanıcı 6/6 alamaz.
