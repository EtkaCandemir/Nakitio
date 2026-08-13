# GLOSSARY.md — Terim Sözlüğü

Kod tanımlayıcıları İngilizce, konuşma dili Türkçe. Bu dosya ikisini
eşler ve alan terimlerini tanımlar.

---

## 1. Skor modeli

| Terim | Kod | Tanım |
|---|---|---|
| **Ham skor** | `raw_score`, `S_ham` | Yalnızca gözlemlenen veriden hesaplanan skor. Güven harmanlamasından önce |
| **Öncül skor** | `prior_score`, `S_öncül` | Onboarding cevaplarından türetilen baz skor. `[28, 75]` |
| **Karma skor** | `blended_score`, `S_karma` | `C × ham + (1−C) × öncül` |
| **Gösterilen skor** | `score` | Yumuşatılmış ve yuvarlanmış nihai skor |
| **Güven** | `confidence`, `C` | Skorun ne kadarının gözlemlenen veriye dayandığı `[0,1]` |
| **Bileşen** | `Pillar` | Skorun 6 ana bölümünden biri |
| **Alt metrik** | `SubScore` | Bir bileşenin içindeki tekil ölçüm |
| **Nominal ağırlık** | `weight_nominal` | Bileşenin sabit ağırlığı (25/20/20/15/10/10) |
| **Etkin ağırlık** | `weight_effective` | Devre dışı bileşenlerden sonra yeniden normalize edilmiş |
| **Aşama** | `stage_label` | Farkındalık Başlangıç / Geçiş / Finansal Sağlık |
| **Seviye** | `level` | Riskli / Dikkat / Gelişiyor / Dengeli / Güçlü |
| **Bant** | `band` | Belirsizlik aralığı. `C < 0,65` iken skor yerine gösterilir |
| **Maddi olay** | `material_events` | Yumuşatmayı aşağı yönde bypass eden durum |
| **Çapa** | `smoothing_anchor` | Yumuşatmanın referans noktası |
| **Katkı ayrıştırma** | `attribute` | "+4 puan"ın bileşenlere dağılımı |

### Altı bileşen

| Türkçe | Kod | Ağırlık | Ölçtüğü |
|---|---|---|---|
| Nakit Akışı | `cashflow` | 25 | Gelir–gider ilişkisi ve kırılganlığı |
| Borç Yükü | `debt` | 20 | Mevcut ve gelecek yükümlülükler |
| Tasarruf & Güvence | `savings` | 20 | Kasıtlı birikim ve şoka dayanıklılık |
| Harcama Disiplini | `discipline` | 15 | Plana uyum |
| Hedef Devamlılığı | `goals` | 10 | Söylediğini yapma |
| Finansal Davranış | `behavior` | 10 | Harcamanın psikolojisi |

---

## 2. Finansal terimler

| Terim | Kod | Tanım |
|---|---|---|
| **DSR** | `dsr` | Debt Service Ratio — aylık borç yükü / net gelir. Taksit dahil |
| **Taahhüt oranı** | `commit_ratio` | (anapara + kalan taksit) / yıllık net gelir |
| **Kart kullanım oranı** | `card_utilization` | Kart bakiyesi / limit |
| **Nakit akışı marjı** | `cf_margin` | (gelir − gider) / gelir |
| **Tasarruf oranı** | `s_rate` | Kasıtlı birikim / gelir |
| **Güvence süresi** | `ef_months` | Acil fon / aylık zorunlu gider — kaç ay dayanır |
| **Likidite tamponu** | `runway_days` | Likit bakiye / günlük gider |
| **İsteğe bağlı pay** | `disc_share` | (toplam − zorunlu) / toplam gider |
| **Zorunlu gider** | `e_essential` | `Σ tutar × essential_weight` — kesirli ağırlıkla |
| **Gelir oynaklığı** | `i_cv` | Varyasyon katsayısı (std/ortalama) |
| **KMH** | `kmh_active` | Kredili Mevduat Hesabı — bankanın verdiği eksi bakiye hakkı |
| **Asgari ödeme** | `min_payment_only_months` | Kart borcunun yalnızca zorunlu kısmını ödeme |
| **Findeks** | — | KKB'nin kredi notu. **Bu skor Findeks DEĞİLDİR** ve her ekranda belirtilmelidir |
| **TÜFE** | `CPISeries` | Tüketici Fiyat Endeksi (TÜİK) |
| **COICOP** | `cpi_group` | TÜİK'in harcama sınıflandırması |

---

## 3. Veri katmanı

| Terim | Kod | Tanım |
|---|---|---|
| **Normalizasyon** | `normalize()` | N1–N9 kurallarının ham veriye uygulanması |
| **Türetilmiş metrik** | `Features` | Normalize veriden hesaplanan, motora giden değerler |
| **Defter** | `Ledger` | Normalize edilmiş işlem kümesi + planlar + amortisman |
| **Pencere** | `Window` | 30 günlük kayan dönem. W0 en yeni |
| **Aktif pencere** | `active_windows()` | İçinde gerçekten veri olan pencereler |
| **Nakit görünüm** | `expenses_cash` | Taksit aylık sayılır |
| **Tahakkuk görünüm** | `expenses_accrual` | Taksit satın alma ayında tam sayılır |
| **İç transfer** | `is_internal_transfer` | Kullanıcının kendi hesapları arası hareket |
| **Amortisman** | `AmortEntry` | Yıllık ödemenin aylara dağıtılması |
| **Aykırı değer** | `is_unusual` | Aylık gelirin 3 katından büyük tek işlem |
| **Merchant anahtarı** | `merchant_id` | Normalleştirilmiş işyeri adı |
| **Parmak izi** | `txn_fingerprint` | İşlemin tekilleştirme kimliği |

### N kuralları

| Kod | Ad |
|---|---|
| N1 | İç transfer eşleştirme |
| N2 | Kredi kartı ödemesi tekilleştirme |
| N3 | Taksit ayrıştırma |
| N4 | Yinelenen ödeme tespiti ve amortisman |
| N5 | Enflasyon düzeltmesi |
| N6 | Döviz / altın / fon — yalnız katkılar |
| N7 | İade eşleştirme |
| N8 | Aykırı değer |
| N9 | Kategorizasyon |

---

## 4. Ekstre alımı

| Terim | Kod | Tanım |
|---|---|---|
| **Ekstre** | statement | Banka hesap hareketi veya kart hesap özeti |
| **Hesap hareketleri** | `DocKind.ACCOUNT` | Vadesiz hesap dökümü |
| **Kart ekstresi** | `DocKind.CARD` | Kredi kartı hesap özeti |
| **Banka profili** | `BankProfile` | Bir bankanın bir ekstre türü için ayrıştırma tarifi |
| **Dönem** | `period_start/end` | Ekstrenin kapsadığı tarih aralığı |
| **Kesim tarihi** | `period_end` | Ekstrenin kapandığı gün |
| **Dönem borcu** | `closing_balance` | Kart ekstresindeki toplam borç |
| **Etkin hesaplama tarihi** | `effective_as_of` | `min(bugün, son ekstre tarihi)` |
| **Kapsam** | `statement_coverage` | Son 6 ayın kaçında ekstre var |
| **Alacak işaretçisi** | `credit_markers` | Kart ekstresinde işareti ters çeviren kelimeler |

---

## 5. Davranış çıkarımı

| Terim | Kod | Tanım |
|---|---|---|
| **Çıkarım** | `impulse_probability` | Etiketsiz plansızlık tahmini |
| **Sinyal** | `Signals` | Bir işlemden çıkarılan 10 özellik |
| **Yinelenen** | `recurring` | Düzenli tekrar eden ödeme — en güçlü PLANLI sinyali |
| **Yeni merchant** | `merchant_novel` | İlk kez görülen işyeri |
| **Tutar sapması** | `amount_z` | Kategori medyanına göre standart sapma |
| **Kümelenme** | `cluster_size` | Aynı gün isteğe bağlı işlem sayısı |
| **Maaş yakınlığı** | `days_since_income` | Gelir gününden bu yana geçen gün |
| **Kalibrasyon** | `calibrate_intercept` | Etiketlerden `b0` kesişimini kaydırma |
| **Etiket ağırlığı** | `label_weight`, `w` | `min(1, etiket_sayısı / 40)` |
| **Triyaj** | `select_for_triage` | Yükleme sonrası sorulacak işlemlerin seçimi |
| **Bilgi kazancı** | `bilgi_degeri` | `tutar_payı × (1 − \|2p−1\|)` |
| **Kapsam** | `beh_coverage` | Davranış ölçümünün etkin kapsamı |
| **Pişmanlık** | `regret_rate` | Düşük memnuniyet payı; iade bir alt sınırdır |

---

## 6. AI koç

| Terim | Kod | Tanım |
|---|---|---|
| **Sayı defteri** | `NumberLedger` | Bağlama giren her sayının kaydı |
| **Doğrulayıcı** | `verify_response` | Yanıttaki her rakamı deftere karşı kontrol |
| **Guard** | `coach_guard` | Sayı + içerik denetimi |
| **Yedek şablon** | `render_fallback` | Deterministik, tanım gereği doğrulamayı geçen yanıt |
| **Onarım** | `guarded_reply` | İhlalleri geri besleyip yeniden üretme |
| **Halüsinasyon** | `hallucinated_number` | Defterde olmayan sayı |
| **Reddetme işaretçisi** | `REFUSAL_MARKERS` | "veremem", "yetkim yok" — tavsiyeyi reddetme eki |
| **Çekince** | `HEDGE_WORDS` | "olabilir", "tahmini" — projeksiyonda zorunlu |
| **Aksiyon** | `ActionSpec` | Simüle edilebilir parametreli eylem |
| **Kümülatif plan** | `build_action_plan` | Adımların birbiri üstüne uygulanması |

---

## 7. Sunum

| Terim | Kod | Tanım |
|---|---|---|
| **Kanonik veri seti** | `screen_data.json` | Her ekranın her sayısı, tek kaynaktan |
| **Kapanan dönem** | `donem.kapanan` | Ekstresi gelmiş, otoriter |
| **Devam eden dönem** | `donem.devam_eden` | Kapanmamış, kısmi, skoru etkilemez |
| **Birincil eylem** | `birincil_eylem` | Ana sayfadaki tek büyük CTA |
| **Farkındalık** | `farkindalik` | Günün içgörü kartı |
| **Güvenlik Ağı** | kademe 1 | 3 aylık acil fon — **skora dahil** |
| **Tam Güvence** | kademe 2 | 6 aylık acil fon — **rozet, skoru etkilemez** |
| **Veri yeterliliği** | `guven_etiketi` | Yüksek / Orta / Düşük |

---

## 8. Onboarding cevap kodları

| Soru | Kod | Seçenekler |
|---|---|---|
| Seni en çok zorlayan konu | `zorluk` | `bilincli_olmak`, `birikim_yapamiyorum`, `nereye_gidiyor`, `impuls`, `borc` |
| Ay sonunda para kalıyor mu | `ay_sonu` | `evet`, `bazen`, `hayir` |
| Harcamalarını takip ediyor musun | `takip` | `duzenli`, `bazen`, `hayir` |
| Kredi kartı / borç durumun | `borc_durumu` | `yok`, `yonetilebilir`, `zorlaniyorum`, `asgari` |
| Son 6 ayda birikim yaptın mı | `birikim_6ay` | `duzenli`, `ara_sira`, `hayir` |

---

## 9. Sık karıştırılan çiftler

| A | B | Fark |
|---|---|---|
| `raw_score` | `score` | Ham = yalnız gözlem. Gösterilen = harmanlanmış + yumuşatılmış |
| `weight_nominal` | `weight_effective` | Nominal sabit. Etkin, devre dışı bileşenlerden sonra |
| `e_total` | `e_essential` | Toplam gider vs zorunlu kısım (kesirli ağırlıkla) |
| `debt_principal` | `installment_remaining` | Krediler + döner kart borcu vs taksit taahhüdü. **Çakışmaz** |
| `card_balance` | `debt_principal` | Kart bakiyesi yalnız kullanım oranı için; `COMMIT`'e girmez |
| `s_deliberate` | `i_net − e_total` | Kasıtlı transfer vs artık bakiye. **Aynı şey değil** |
| Nakit görünüm | Tahakkuk görünüm | Taksit aylık vs satın alma ayında tam |
| Golden test | Invariant test | Güncellenebilir vs asla kırılmamalı |
| `_norm` (guard) | `_fold` (ingest) | Türkçe `I→ı` vs ASCII katlama |
| `prev_score` | `prev_raw_score` | Gösterilen önceki vs ham önceki |
| Çıkarım | Etiket | Model tahmini vs kullanıcı beyanı |
| Skor hedefi (3 ay) | Rozet hedefi (6 ay) | Skora dahil vs skorun dışında |
