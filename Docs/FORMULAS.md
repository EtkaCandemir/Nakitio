# FORMULAS.md — Formül ve Parametre Referansı

Arama amaçlı referans. Akış için `Docs/ALGORITHM.md`, gerekçeler için
`Docs/DECISIONS.md`.

> Değerler `engine/params.py`'den okunur. Bu dosyadaki tablo o dosyadan
> üretildi; çeliştiğinde **kod esastır**.

---

## 1. Eşleme fonksiyonları

Üçü de sürekli, monoton ve `[0, 100]`'e kelepçeli. Basamak tablosu
kullanılmaz — v1'in en büyük hatası oydu.

### `lin(x, zero_at, hundred_at)` — parçalı doğrusal

```
lin(x, a, b) = 100 × clamp₀¹((x − a) / (b − a))
```

`b < a` ise "küçük olan iyidir". Örn. `lin(DSR, 0.50, 0.10)`: DSR %10 ve
altı 100 puan, %50 ve üstü 0 puan.

### `sat(x, k)` — doygunlaşan

```
sat(x, k) = 100 × (1 − e^(−x/k))
```

| x | Sonuç |
|---|---|
| `k` | 63,2 |
| `2k` | 86,5 |
| `3k` | 95,0 |

"Daha fazlası hep iyidir ama getirisi azalır" için. `x ≤ 0` → 0.

### `concave(x, full_at, power)` — içbükey doyum

```
concave(x, F, p) = 100 × min(1, x/F)^p
```

"İlk birim en değerlidir" için. `p < 1` içbükeydir.

Acil fon örneği (`F=3`, `p=0.6`):

| Fon (ay) | Puan |
|---|---|
| 0,5 | 34 |
| 1 | 52 |
| 2 | 78 |
| 3 | 100 |

---

## 2. Bileşen formülleri

### P1 — Nakit Akışı (ağırlık 25)

| Alt metrik | Ağırlık | Formül |
|---|---|---|
| Marj | 0,600 | `m ≥ 0`: `20 + 80×sat(m, 0,12)/100`<br>`m < 0`: `max(0, 20×(1 + m/0,10))` |
| Gelir istikrarı | 0,130 | `lin(i_cv, 0,45 → 0,05)` |
| Likidite tamponu | 0,195 | `concave(runway_gün, 45, 0,70)` |
| Gelir çeşitliliği | 0,075 | `lin(i_primary_share, 1,00 → 0,60)` |

```
m           = (i_net − e_total) / i_net          ← 3 pencerelik medyan
runway_gün  = liquid_balance / (e_total / 30)      ← bakiye None ise tampon KAPALI
```

`liquid_balance` `None` olduğunda `tampon` alt metriği hesaplanmaz; ağırlığı
`marj`, `istikrar` ve `cesitlilik` arasında yeniden dağıtılır ve güven düşer.
Sıfır puan **verilmez** — ölçemediğimiz şey için puan kırmayız.

**Başabaş noktası 20 puandır, 0 değil.** İki dal `m = 0`'da AYNI değeri
vermek zorundadır — ilk sürümde vermiyordu ve 12,2 puanlık uçurum vardı.

`i_net ≤ 0` ise: `marj = 0` (e_total > 0 ise), yoksa `None`.

### P2 — Borç Yükü (ağırlık 20)

| Alt metrik | Ağırlık | Formül |
|---|---|---|
| DSR | 0,38 | `lin(dsr, 0,50 → 0,10)` |
| Kart kullanımı | 0,22 | `lin(card_util, 0,90 → 0,20)` |
| Taahhüt | 0,25 | `lin(commit_ratio, 0,60 → 0,05)` |
| Borç trendi | 0,15 | `lin(debt_trend_3m, +0,20 → −0,15)` |

```
dsr          = (debt_monthly_service + installment_monthly) / i_net
commit_ratio = (debt_principal + installment_remaining) / (i_net × 12)
card_util    = card_balance / card_limit
```

**Ceza çarpanları** (bileşen skoruna, alt metriğe değil):

```
gecikme 1–29 gün       ×0,70
gecikme 30+ gün        ×0,45
sadece asgari 1–2 ay   ×0,80
sadece asgari 3+ ay    ×0,65
KMH aktif              ×0,85
```

Borçsuz kullanıcı: tek alt metrik, 100 puan, ceza yok.

### P3 — Tasarruf & Güvence (ağırlık 20)

| Alt metrik | Ağırlık | Formül |
|---|---|---|
| Tasarruf oranı | 0,33 | `sat(s_rate, 0,10)` |
| Acil fon | 0,34 | `concave(ef_months, 3, 0,60)` |
| Süreklilik | 0,23 | `100 × s_consistency_months / 6` |
| Enflasyon koruması | 0,10 | `lin(real_return_gap, −0,25 → 0,00)` |

```
s_rate     = s_deliberate / i_net        ← KASITLI transfer, artık bakiye değil
ef_months  = ef_liquid / e_essential
```

Acil fon hedefi **3 ay**dır (skor). 6 ay skorun dışında bir rozettir —
gerekçe `Docs/DECISIONS.md`.

### P4 — Harcama Disiplini (ağırlık 15)

| Alt metrik | Ağırlık | Formül |
|---|---|---|
| Bütçe uyumu | 0,38 | `100 × (1 − budget_overrun / budget_planned)` |
| Limit uyumu | 0,20 | `100 × (1 − limit_breached / limit_categories)` |
| İsteğe bağlı pay | 0,27 | `lin(disc_share, 0,60 → 0,20)` |
| Kategori oynaklığı | 0,15 | `lin(cat_volatility, 0,70 → 0,15)` |

```
disc_share = (e_total − e_essential) / e_total
```

Bu bileşen **gider/gelir oranını kullanmaz** — o P1'in işidir. Burada
ölçülen "ne kadar harcadığın" değil, "dediğini yapıp yapmadığın"dır.

### P5 — Hedef Devamlılığı (ağırlık 10)

| Alt metrik | Ağırlık | Formül |
|---|---|---|
| İlerleme | 0,45 | `100 × goal_ontrack` |
| Katkı sürekliliği | 0,35 | `100 × goal_consistency` |
| Gerçekçilik | 0,20 | `lin(gerekli/fazla, 1,60 → 0,80)` |

```
ontrack_i  = min(1, mevcut_i / beklenen_i)
beklenen_i = hedef_i × (geçen_süre / toplam_süre)
goal_ontrack = Σ(ontrack_i × hedef_i) / Σ hedef_i     ← büyüklüğe göre ağırlıklı
gerçekçilik girdisi = goal_required_monthly / (i_net − e_total)
```

Hedef yok + gün < 60 → bileşen devre dışı.
Hedef yok + gün ≥ 60 → 45 puan.

### P6 — Finansal Davranış (ağırlık 10)

| Alt metrik | Ağırlık | Formül |
|---|---|---|
| Plansızlık | 0,35 | `lin(imp_rate, 0,40 → 0,05)` |
| Duygusal pay | 0,25 | `lin(emo_rate, 0,30 → 0,03)` |
| Gece yoğunlaşması | 0,20 | `lin(night_conc, 0,35 → 0,05)` |
| Pişmanlık | 0,20 | `lin(regret_rate, 0,50 → 0,05)` |

`beh_coverage < 0,25` → bileşen devre dışı.

Hepsi **oran**dır, olay sayısı değil. v1'de tek bir işlem bileşeni
sıfırlayabiliyordu.

---

## 3. Güven (C)

```
C = 0,28·c_geçmiş + 0,22·c_kapsam + 0,20·c_bütünlük
  + 0,12·c_doğrulama + 0,18·c_bileşen

C ×= min(1, days_of_data / 21)
C ×= 0,60  eğer integrity_flag
```

```
c_geçmiş    = min(1, days_of_data / 90)
c_bütünlük  = categorized_ratio
c_doğrulama = 1 − |i_declared − i_net| / i_declared   ya da 0,40
c_bileşen   = Σ aktif ağırlık / Σ toplam ağırlık

c_kapsam:
  statement → 0,85 × statement_coverage × categorized_ratio
  manual    → 0,45 × categorized_ratio
  linked    → accounts_linked / accounts_declared
```

---

## 4. Harmanlama, yumuşatma, bant

```
S_öncül = clamp(40 + Σ onboarding, 28, 75)
S_karma = C × S_ham + (1 − C) × S_öncül

karma_önceki = C_eski × ham_eski + (1 − C_eski) × S_öncül
offset       = gösterilen_eski − karma_önceki
çapa         = C_yeni × ham_eski + (1 − C_yeni) × S_öncül + offset

α        = 0,70 eğer (maddi_olay ve yeni < çapa) yoksa 0,35
EWMA     = α × S_karma + (1 − α) × çapa
S_final  = clamp(EWMA, çapa − 8, çapa + 8)     ← maddi olayda sınır kalkar

yarı_bant = max(2, 12 × (1 − C))
```

### Onboarding puanları

Baz **40**, sonuç `[28, 75]`'e kelepçelenir.

| Soru | Cevap | Etki |
|---|---|---|
| **Zorluk** | bilinçli olmak | +2 |
| | birikim yapamıyorum | −3 |
| | nereye gidiyor bilmiyorum | −4 |
| | impuls | −5 |
| | borç | −6 |
| **Ay sonu** | evet | +8 · bazen +2 · hayır −6 |
| **Takip** | düzenli | +8 · bazen +3 · hayır −5 |
| **Borç durumu** | yok | +8 · yönetilebilir +2 · zorlanıyorum −6 · asgari −8 |
| **Birikim (6 ay)** | düzenli | +8 · ara sıra +3 · hayır −5 |

Ham uçlar: en iyi 74, orta 46, zayıf 29, kötü 10.
Kelepçe sonrası: 74 / 46 / 29 / 28.

---

## 5. Aşama ve seviye eşikleri

```
C < 0,30 veya gün < 8  → Farkındalık Başlangıç Skoru
C < 0,65               → Geçiş Skoru          + BANT olarak sun
C ≥ 0,65               → Finansal Sağlık Skoru
```

| Skor | Seviye |
|---|---|
| 0–39 | Riskli |
| 40–59 | Dikkat |
| 60–74 | Gelişiyor |
| 75–89 | Dengeli |
| 90–100 | Güçlü |

---

## 6. Davranış çıkarımı modeli

```
z = b0 + Σ (katsayı × sinyal)
```

<!-- OTOMATIK:davranis-katsayilari -->
*`behavior_infer.W`'den üretildi.*

| Katsayı | Değer | Anlamı |
|---|---|---|
| `b0` | **−1,15** | kesişim (kalibrasyonla kayar) |
| `recurring` | **−2,4** | yinelenen ödeme — en güçlü PLANLI sinyali |
| `novel` | **0,55** | ilk kez görülen merchant |
| `category` | **2,6** | (kategori ön olasılığı − 0,5) ile çarpılır |
| `amount` | **0,85** | kategori medyanından sapma |
| `cluster` | **0,7** | aynı gün isteğe bağlı işlem kümesi |
| `installment` | **0,45** | taksitle alınmış |
| `payday` | **0,5** | maaş gününe yakınlık (0–3 gün) |
| `weekend` | **0,35** | hafta sonu |
| `refunded` | **1,6** | sonradan iade edilmiş |
| `night` | **0,75** | gece harcaması (saat varsa) |

```
p = 1 / (1 + e^(−z))
```

**Rahatlama kategorileri** (duygu modeli yalnızca bunlarda çalışır): `alkol_tutun`, `eglence`, `giyim`, `kisisel`, `restoran`, `sans_oyunu`
<!-- /OTOMATIK:davranis-katsayilari -->

Kalibrasyon: `calibrate_intercept()` yalnızca `b0`'ı ikili aramayla
kaydırır (±2,5), en az 8 etiket gerekir. Katsayılar sabit kalır — az
veriyle çok parametreli fit aşırı uyum yapar.

### Duygu modeli (zayıf vekil)

```
kategori ∉ COMFORT_CATEGORIES → 0,03
z = −1,9 + 0,9·night + 0,5·weekend
         + 0,8·min(1,(cluster−1)/3) + 0,6·min(1,amount_z/3) + 1,2·refunded
```

Sinyaller yığılsa bile 0,90'ı geçmez. **UI'da iddia değil soru olarak
sunulur.**

### Harmanlama ve triyaj

```
w        = min(1, etiket_sayısı / infer.etiket_tam)
oran     = w × etiketli + (1 − w) × çıkarımsal
coverage = max(infer.cikarim_kapsam, w)

triyaj değeri = (tutar / toplam) × (1 − |2p − 1|)
```

---

## 7. Kategori taksonomisi

<!-- OTOMATIK:kategori-tablosu -->
*`data_model.CATEGORIES` ve `behavior_infer.CATEGORY_IMPULSE_PRIOR`'dan üretildi.*

| Kategori | `essential_weight` | Plansızlık ön olasılığı | TÜFE grubu |
|---|---|---|---|
| Aidat (`aidat`) | **1** | 0 | `konut` |
| Eğitim (`egitim`) | **1** | 0,05 | `egitim` |
| Faturalar (`faturalar`) | **1** | 0,02 | `konut` |
| Kira / Konut (`kira`) | **1** | 0 | `konut` |
| Sağlık (`saglik`) | **1** | 0,08 | `saglik` |
| Sigorta (`sigorta`) | **1** | 0,02 | `cesitli` |
| Vergi / Resmi (`vergi`) | **1** | 0,02 | `cesitli` |
| Çocuk / Bakım (`cocuk`) | **0,95** | 0,1 | `cesitli` |
| İnternet / Telefon (`iletisim`) | **0,85** | 0,05 | `haberlesme` |
| Market (`market`) | **0,85** | 0,15 | `gida` |
| Ulaşım (`ulasim`) | **0,75** | 0,12 | `ulastirma` |
| Ev / Yaşam (`ev`) | **0,4** | 0,35 | `ev_esyasi` |
| Kişisel Bakım (`kisisel`) | **0,35** | 0,4 | `cesitli` |
| Giyim (`giyim`) | **0,25** | 0,55 | `giyim` |
| Restoran & Kafe (`restoran`) | **0,15** | 0,45 | `lokanta` |
| Dijital Abonelik (`abonelik`) | **0,1** | 0,3 | `eglence` |
| Elektronik (`elektronik`) | **0,1** | 0,55 | `ev_esyasi` |
| Spor & Fitness (`spor`) | **0,1** | 0,35 | `eglence` |
| Hediye (`hediye`) | **0,05** | 0,5 | `cesitli` |
| Alkol & Tütün (`alkol_tutun`) | **0** | 0,6 | `alkol_tutun` |
| Eğlence & Hobi (`eglence`) | **0** | 0,65 | `eglence` |
| Şans Oyunları (`sans_oyunu`) | **0** | 0,8 | `eglence` |
| Tatil & Seyahat (`tatil`) | **0** | 0,4 | `lokanta` |
| Diğer (`diger`) | **bilinmiyor** | 0,3 | `cesitli` |
| Faiz & Ücret (`faiz_ucret`) | **bilinmiyor** | — | `cesitli` |
| Pazaryeri (`pazaryeri`) | **bilinmiyor** | 0,45 | `cesitli` |

```
e_essential = Σ (tutar_i × essential_weight[kategori_i])

Ağırlığı `bilinmiyor` olanlar bu toplama GİRMEZ; oran, ağırlığı
bilinen harcamadan tahmin edilip toplama genişletilir.
```
<!-- /OTOMATIK:kategori-tablosu -->

Kesirli ağırlık bilinçlidir: "market" ne tamamen zorunlu ne tamamen
isteğe bağlıdır. İkili bayrak gri bölgede sistematik hata üretir ve hem
`ef_months` hem `disc_share`'i bozar.

---

## 8. Tam parametre tablosu

`tune.py` ile ölçülen etkiler için `Docs/DECISIONS.md` §3.

<!-- OTOMATIK:params-tablosu -->
*109 parametre. `params.py`'den üretildi — elle düzenleme.*

### Bileşen

| Anahtar | Değer | Aralık | Tür | Açıklama |
|---|---|---|---|---|
| `p1.weight` | **25** | 15–35 | weight | Nakit Akışı ağırlığı — Gelir–gider ilişkisi ve kırılganlığı |
| `p2.weight` | **20** | 10–30 | weight | Borç Yükü ağırlığı — Mevcut ve gelecek yükümlülükler |
| `p3.weight` | **20** | 10–30 | weight | Tasarruf & Güvence ağırlığı — Kasıtlı birikim ve şoka dayanıklılık |
| `p4.weight` | **15** | 5–25 | weight | Harcama Disiplini ağırlığı — Plana uyum |
| `p5.weight` | **10** | 5–20 | weight | Hedef Devamlılığı ağırlığı — Söylediğini yapma |
| `p6.weight` | **10** | 5–20 | weight | Finansal Davranış ağırlığı — Harcamanın psikolojisi |

### P1

| Anahtar | Değer | Aralık | Tür | Açıklama |
|---|---|---|---|---|
| `p1.marj.w` | **0,56** | 0,3–0,75 | weight | Marj alt ağırlığı |
| `p1.istikrar.w` | **0,12** | 0,05–0,35 | weight | Gelir istikrarı ağırlığı |
| `p1.tampon.w` | **0,18** | 0,05–0,35 | weight | Likidite tamponu ağırlığı |
| `p1.cesitlilik.w` | **0,07** | 0–0,25 | weight | Gelir çeşitliliği ağırlığı |
| `p1.zamanlama.w` | **0,07** | 0–0,2 | weight | Ödeme zamanlaması ağırlığı — KARAR: 0,07. Aynı marjda çok farklı kırılganlık: maaşı 1'inde gelip kartı 5'inde ödey… |
| `p1.breakeven` | **20** | 0–40 | shape | Başabaş puanı — Gelir=gider noktası. 0 yaparsan başabaş 'kötü' olur |
| `p1.marj.k` | **0,12** | 0,06–0,25 | shape | Marj doygunluk sabiti — Küçültürsen düşük marj bile yüksek puan alır |
| `p1.marj.neg_sifir` | **0,1** | 0,05–0,25 | threshold | Negatif marj sıfır noktası |
| `p1.istikrar.sifir` | **0,45** | 0,25–0,8 | threshold | Gelir CV sıfır eşiği |
| `p1.istikrar.yuz` | **0,05** | 0–0,2 | threshold | Gelir CV tam puan eşiği |
| `p1.tampon.tam_gun` | **45** | 20–90 | threshold | Likidite tam puan (gün) |
| `p1.tampon.us` | **0,7** | 0,4–1 | shape | Likidite eğri üssü |
| `p1.zamanlama.sifir` | **28** | 20–30 | threshold | Taşıma süresi sıfır eşiği (gün) — KARAR: 28. Neredeyse tam ay taşımak. |
| `p1.zamanlama.yuz` | **5** | 0–12 | threshold | Taşıma süresi tam puan eşiği (gün) — KARAR: 5. Gelirden hemen sonra ödeme. |
| `p1.cesitlilik.sifir` | **1** | 0,85–1 | threshold | Tek kaynak eşiği |
| `p1.cesitlilik.yuz` | **0,6** | 0,3–0,8 | threshold | Çeşitlilik tam puan |

### P2

| Anahtar | Değer | Aralık | Tür | Açıklama |
|---|---|---|---|---|
| `p2.dsr.w` | **0,32** | 0,2–0,6 | weight | DSR ağırlığı |
| `p2.kart.w` | **0,18** | 0,05–0,4 | weight | Kart kullanımı ağırlığı |
| `p2.taahhut.w` | **0,22** | 0,1–0,4 | weight | Taahhüt yükü ağırlığı |
| `p2.trend.w` | **0,12** | 0,05–0,3 | weight | Borç trendi ağırlığı |
| `p2.maliyet.w` | **0,16** | 0,05–0,35 | weight | Borç maliyeti ağırlığı — KARAR: 0,16. Borcun FİYATI, hacminden bağımsız bir olgudur ve motor onu hiç ölçmüyord… |
| `p2.dsr.sifir` | **0,5** | 0,35–0,7 | threshold | DSR sıfır eşiği — Bu orandan sonra borç bileşeni sıfırlanır |
| `p2.dsr.yuz` | **0,1** | 0–0,25 | threshold | DSR tam puan eşiği |
| `p2.kart.sifir` | **0,9** | 0,7–1 | threshold | Kart kullanımı sıfır eşiği |
| `p2.kart.yuz` | **0,2** | 0,05–0,4 | threshold | Kart kullanımı tam puan |
| `p2.taahhut.sifir` | **0,6** | 0,35–1 | threshold | Taahhüt/yıllık gelir sıfır |
| `p2.taahhut.yuz` | **0,05** | 0–0,2 | threshold | Taahhüt tam puan |
| `p2.trend.sifir` | **0,2** | 0,08–0,4 | threshold | Borç artışı sıfır eşiği |
| `p2.trend.yuz` | **−0,15** | −0,35–−0,05 | threshold | Borç azalışı tam puan |
| `p2.maliyet.sifir` | **0,8** | 0,4–1,2 | threshold | Borç maliyeti sıfır eşiği (yıllık nominal) — KARAR: 0,80. Yayılım şöyle olsun istendi — %0 taksit 100, ~%30 konut/taşıt 62, ~%42 n… |
| `p2.maliyet.yuz` | **0** | 0–0,25 | threshold | Borç maliyeti tam puan eşiği — KARAR: 0,00. Faizsiz borç bir yük değildir; taksitin kendisi P2'nin taahhüt alt metri… |

### P2 ceza

| Anahtar | Değer | Aralık | Tür | Açıklama |
|---|---|---|---|---|
| `mod.gecikme_1_29` | **0,7** | 0,4–0,95 | modifier | Gecikme 1–29 gün çarpanı |
| `mod.gecikme_30` | **0,45** | 0,2–0,8 | modifier | Gecikme 30+ gün çarpanı |
| `mod.asgari` | **0,8** | 0,55–0,95 | modifier | Sadece asgari ödeme çarpanı |
| `mod.asgari_kronik` | **0,65** | 0,35–0,9 | modifier | Kronik asgari ödeme çarpanı |
| `mod.kmh` | **0,85** | 0,6–1 | modifier | KMH kullanımı çarpanı |

### P3

| Anahtar | Değer | Aralık | Tür | Açıklama |
|---|---|---|---|---|
| `p3.oran.w` | **0,3** | 0,15–0,55 | weight | Tasarruf oranı ağırlığı |
| `p3.guvence.w` | **0,31** | 0,15–0,55 | weight | Acil fon ağırlığı |
| `p3.sureklilik.w` | **0,2** | 0,05–0,4 | weight | Süreklilik ağırlığı |
| `p3.reel.w` | **0,09** | 0–0,25 | weight | Enflasyon koruması ağırlığı |
| `p3.net_varlik.w` | **0,1** | 0–0,3 | weight | Net varlık ağırlığı — KARAR: 0,10. DECISIONS §6'nın v2.1'e ertelediği boyut, bileşen eklemeden. Ağırlık DÜŞ… |
| `p3.oran.k` | **0,1** | 0,05–0,22 | shape | Tasarruf doygunluk sabiti — 0,10 → %10 tasarruf 63 puan, %20 → 86 |
| `p3.guvence.tam_ay` | **3** | 3–12 | threshold | Acil fon hedefi (ay) — KARAR: 6 → 3. Kullanıcıya GÖSTERİLEN hedefle SKORUN hedefi aynı olmalı; aksi hâlde gö… |
| `p3.guvence.us` | **0,6** | 0,35–1 | shape | Acil fon eğri üssü — Düşürürsen ilk ay daha çok ödüllenir |
| `p3.net_varlik.sifir` | **−0,5** | −1,5–0 | threshold | Net varlık sıfır eşiği (yıllık gelir katı) — KARAR: -0,50. Sıfır net varlık NÖTRdür (33 puan), ceza değil: borcu da varlığı da olm… |
| `p3.net_varlik.yuz` | **1** | 0,5–3 | threshold | Net varlık tam puan eşiği — KARAR: 1,00 yıllık gelir. |
| `p3.reel.sifir` | **−0,25** | −0,5–−0,1 | threshold | Enflasyon farkı sıfır |
| `p3.reel.yuz` | **0** | −0,05–0,1 | threshold | Enflasyon farkı tam puan |

### P4

| Anahtar | Değer | Aralık | Tür | Açıklama |
|---|---|---|---|---|
| `p4.butce.w` | **0,38** | 0,2–0,6 | weight | Bütçe uyumu ağırlığı |
| `p4.limit.w` | **0,2** | 0,05–0,4 | weight | Limit uyumu ağırlığı |
| `p4.istege_bagli.w` | **0,27** | 0,1–0,45 | weight | İsteğe bağlı pay ağırlığı |
| `p4.oynaklik.w` | **0,15** | 0–0,3 | weight | Kategori oynaklığı ağırlığı |
| `p4.istege_bagli.sifir` | **0,6** | 0,4–0,8 | threshold | İsteğe bağlı pay sıfır eşiği |
| `p4.istege_bagli.yuz` | **0,2** | 0,1–0,35 | threshold | İsteğe bağlı pay tam puan |
| `p4.oynaklik.sifir` | **0,7** | 0,4–1 | threshold | Oynaklık sıfır eşiği |
| `p4.oynaklik.yuz` | **0,15** | 0,05–0,3 | threshold | Oynaklık tam puan |

### P5

| Anahtar | Değer | Aralık | Tür | Açıklama |
|---|---|---|---|---|
| `p5.ontrack.w` | **0,38** | 0,25–0,65 | weight | Hedef ilerlemesi ağırlığı |
| `p5.tutarlilik.w` | **0,28** | 0,15–0,55 | weight | Katkı sürekliliği ağırlığı |
| `p5.gercekcilik.w` | **0,17** | 0–0,4 | weight | Hedef gerçekçiliği ağırlığı |
| `p5.plan_uyumu.w` | **0,17** | 0–0,35 | weight | Plana uyum ağırlığı — KARAR: 0,17. `ontrack` hedefe YAKLAŞMAYI ölçer, bu SÖZE UYMAYI. İkisi ayrışır: fazla … |
| `p5.plan_uyumu.sifir` | **0,3** | 0–0,6 | threshold | Plana uyum sıfır eşiği — KARAR: 0,30. Planın üçte birinden azı gerçekleştiyse plan yaşamıyor demektir. |
| `p5.plan_uyumu.yuz` | **1** | 0,85–1,3 | threshold | Plana uyum tam puan eşiği — KARAR: 1,00. Planı AŞMAK ek puan getirmez; fazla katkı zaten `ontrack`ta görünür. |
| `p5.gercekcilik.sifir` | **1,6** | 1,2–2,5 | threshold | Gerçekçilik sıfır eşiği |
| `p5.gercekcilik.yuz` | **0,8** | 0,5–1 | threshold | Gerçekçilik tam puan |
| `p5.hedefsiz_puan` | **45** | 0–70 | gate | Hedefsizlik puanı — 60 gün sonra hedef yoksa verilen nötr puan |
| `p5.grace_gun` | **60** | 14–120 | gate | Hedefsizlik muafiyeti (gün) |

### P6

| Anahtar | Değer | Aralık | Tür | Açıklama |
|---|---|---|---|---|
| `p6.impuls.w` | **0,35** | 0,2–0,55 | weight | Plansızlık ağırlığı |
| `p6.duygusal.w` | **0,25** | 0,1–0,45 | weight | Duygusal pay ağırlığı |
| `p6.gece.w` | **0,2** | 0–0,4 | weight | Gece yoğunlaşması ağırlığı |
| `p6.pismanlik.w` | **0,2** | 0,05–0,4 | weight | Pişmanlık ağırlığı |
| `p6.impuls.sifir` | **0,4** | 0,25–0,65 | threshold | Plansızlık sıfır eşiği |
| `p6.impuls.yuz` | **0,05** | 0–0,2 | threshold | Plansızlık tam puan |
| `p6.duygusal.sifir` | **0,3** | 0,18–0,5 | threshold | Duygusal pay sıfır eşiği |
| `p6.duygusal.yuz` | **0,03** | 0–0,12 | threshold | Duygusal pay tam puan |
| `p6.gece.sifir` | **0,35** | 0,2–0,55 | threshold | Gece payı sıfır eşiği |
| `p6.gece.yuz` | **0,05** | 0–0,18 | threshold | Gece payı tam puan |
| `p6.pismanlik.sifir` | **0,5** | 0,3–0,75 | threshold | Pişmanlık sıfır eşiği |
| `p6.pismanlik.yuz` | **0,05** | 0–0,2 | threshold | Pişmanlık tam puan |
| `p6.min_kapsam` | **0,25** | 0,1–0,5 | gate | Davranış min. kapsam — Altındaysa bileşen devre dışı |
| `p6.tam_kapsam` | **0,5** | 0,3–0,9 | threshold | Davranış tam kapsam eşiği — KARAR: 0,50. Bileşen bu kapsamda TAM ağırlığına ulaşır; min_kapsam ile arasında ağırl… |

### Güven

| Anahtar | Değer | Aralık | Tür | Açıklama |
|---|---|---|---|---|
| `c.hist.w` | **0,28** | 0,1–0,5 | weight | Geçmiş uzunluğu ağırlığı |
| `c.cover.w` | **0,22** | 0,1–0,45 | weight | Kaynak kapsamı ağırlığı |
| `c.compl.w` | **0,2** | 0,05–0,4 | weight | Kategorizasyon ağırlığı |
| `c.verif.w` | **0,12** | 0–0,3 | weight | Gelir doğrulama ağırlığı |
| `c.pillar.w` | **0,18** | 0,05–0,35 | weight | Bileşen + alt metrik kapsamı |
| `c.hist_tam_gun` | **90** | 45–180 | threshold | Tam geçmiş (gün) |
| `c.rampa_gun` | **21** | 7–45 | gate | İlk rampa (gün) |
| `c.statement_tavan` | **0,85** | 0,6–1 | threshold | Ekstre kaynağı tavanı — Ekstre yüklemenin ulaşabileceği en yüksek kapsam |
| `c.manual_tavan` | **0,45** | 0,2–0,7 | threshold | Manuel giriş tavanı |
| `c.verif_varsayilan` | **0,4** | 0,1–0,7 | threshold | Doğrulama yoksa varsayılan |
| `c.integrity_carpan` | **0,6** | 0,3–0,9 | modifier | Bütünlük şüphesi çarpanı |

### Yumuşatma

| Anahtar | Değer | Aralık | Tür | Açıklama |
|---|---|---|---|---|
| `s.alpha` | **0,35** | 0,15–0,7 | shape | EWMA alfa (normal) — Yükseltirsen skor daha hızlı tepki verir |
| `s.alpha_maddi` | **0,7** | 0,4–1 | shape | EWMA alfa (maddi olay) |
| `s.max_hareket` | **8** | 3–20 | gate | Aylık azami hareket |
| `s.band_k` | **12** | 6–20 | shape | Belirsizlik bandı katsayısı |
| `s.band_min` | **2** | 0–6 | gate | Bandın en dar hâli |

### Aşama

| Anahtar | Değer | Aralık | Tür | Açıklama |
|---|---|---|---|---|
| `stage.gecis_C` | **0,3** | 0,15–0,5 | gate | Geçiş Skoru eşiği |
| `stage.saglik_C` | **0,65** | 0,45–0,85 | gate | Finansal Sağlık eşiği — Aynı zamanda 'bant olarak sun' eşiği |

### Öncül

| Anahtar | Değer | Aralık | Tür | Açıklama |
|---|---|---|---|---|
| `prior.baz` | **40** | 40–60 | shape | Onboarding baz puanı — KARAR: 50 → 40. Ölçmediğimiz bir şey hakkında iyimser iddiada bulunmuyoruz; düşük baş… |
| `prior.min` | **28** | 25–50 | gate | Öncül alt sınırı — KARAR: 40 → 28. 40 tabanında 'zayıf' ve 'kötü' anket cevapları AYNI skoru alıyordu (h… |
| `prior.max` | **75** | 60–85 | gate | Öncül üst sınırı |

### Çıkarım

| Anahtar | Değer | Aralık | Tür | Açıklama |
|---|---|---|---|---|
| `infer.etiket_tam` | **40** | 15–100 | gate | Etiketin tam ağırlık sayısı |
| `infer.cikarim_kapsam` | **0,55** | 0,3–0,8 | gate | Çıkarımın ürettiği kapsam |
<!-- /OTOMATIK:params-tablosu -->

---

## 9. Modül sabitleri

<!-- OTOMATIK:norm-sabitleri -->
*Modül sabitleri — `params.py` dışında. Koddan üretildi.*

| Sabit | Değer | Modül | Anlamı |
|---|---|---|---|
| `PIPELINE_VERSION` | **1.0.0** | `normalize` | Veri hattı sürümü |
| `CATEGORY_VERSION` | **1.2.0** | `normalize` | Kategorizasyon sürümü — ayrı takip |
| `WINDOW_DAYS` | **30** | `normalize` | Kayan pencere uzunluğu (gün) |
| `N_WINDOWS` | **6** | `normalize` | Tutulan pencere sayısı |
| `TRANSFER_MATCH_DAYS` | **3** | `normalize` | İç transfer eşleştirme penceresi (gün) |
| `TRANSFER_TOLERANCE_ABS` | **1** | `normalize` | Transfer tutar toleransı (TL) |
| `TRANSFER_TOLERANCE_PCT` | **0,005** | `normalize` | Transfer kur/komisyon payı |
| `AMORTIZE_MIN_PERIOD_DAYS` | **90** | `normalize` | Amortisman eşiği (gün) |
| `RECURRING_AMOUNT_TOL` | **0,15** | `normalize` | Yinelenen ödeme tutar toleransı |
| `LIMIT_TOLERANCE` | **0,05** | `normalize` | Kategori limiti ihlal toleransı |
| `CATVOL_MIN_PRESENT` | **0,75** | `normalize` | Oynaklık: pencere varlık oranı |
| `CATVOL_MIN_SHARE` | **0,02** | `normalize` | Oynaklık: minimum harcama payı |
| `REFUND_WINDOW_DAYS` | **90** | `normalize` | İade eşleştirme penceresi (gün) |
| `OUTLIER_INCOME_MULTIPLE` | **3** | `normalize` | Aykırı değer eşiği (gelir katı) |
| `RECURRING_MIN_SEEN` | **3** | `behavior_infer` | Yinelenen sayılmak için görülme |
| `RECURRING_AMOUNT_TOL` | **0,2** | `behavior_infer` | Yinelenen tutar toleransı |
| `GUVENCE_ILERI_AY` | **6** | `screen_data` | Rozet hedefi — skor DIŞI (ay) |
| `STRUCTURAL_MAX` | **31** | `coach_guard` | Yapısal sayılan azami tam sayı |
| `REFUSAL_WINDOW` | **40** | `coach_guard` | Reddetme eki arama penceresi (karakter) |
| `COACH_VERSION` | **1.0.0** | `coach_tools` | Koç katmanı sürümü |
| `NIGHT_HOURS` | **20–02** | `normalize` | Gece tanımı (saat aralığı) |
<!-- /OTOMATIK:norm-sabitleri -->
