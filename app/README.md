# Nakitio — Çalışan Prototip

```bash
python3 app/server.py        # http://localhost:8765
```

Bağımlılık yok — Python standart kütüphanesi + statik dosyalar.

## Bu nedir, ne değildir

**Değildir:** sevk edilecek uygulama. Sevk edilecek sürüm React Native ya
da Flutter olur.

**Nedir:** `engine/` içindeki gerçek motoru bir arayüzün arkasına koyan,
akışları doğrulamak için kurulmuş bir prototip. **Sahte veri yoktur** —
her sayı `engine/` tarafından hesaplanır. Triyajda bir işlemi
"plansızdı" işaretlersen davranış çıkarımı yeniden koşar, bileşen puanı
düşer, skor gerçekten değişir.

Amacı: React Native'e haftalar harcamadan önce ekranların, akışların ve
veri sözleşmesinin doğru olduğunu görmek.

## Yapı

```
app/server.py        stdlib HTTP · oturum durumu · engine çağrıları
app/web/index.html   iskelet
app/web/style.css    mor birincil / yeşil semantik (Docs/ekran-mimarisi-v1.md §2)
app/web/app.js       4 sekme + FAB · triyaj · ekstre · hızlı ekleme · koç
```

Arayüz **hiçbir finansal hesap yapmaz.** Tüm sayılar sunucudan gelir;
`app.js` yalnızca biçimlendirir.

## Denenebilecekler

**Durum geçişi** (üstteki üç hap): `Gün 0` → `İlk ekstre` → `Olgun`.
Boş durumların da kanonik olduğunu gösterir. Gün 0'da skor **bant**
olarak çıkar (44–68), seviye etiketi **gösterilmez**.

**Triyaj** — ana sayfadaki karttan. Her cevap skoru gerçekten değiştirir:

```
6 işlem "plansızdı" işaretlendi
  plansız oran   %12 → %22
  davranış puanı 7,1 → 5,3
  skor           74  → 73
```

**Ekstre yükleme** — FAB → Ekstre Yükle → örnek kart ekstresi:

```
6 satır bulundu · 6 yeni · 0 mükerrer
dönem sonu borcu ₺7.940 yakalandı  → borç anapara geçmişine yazıldı
aynı ekstre tekrar yüklendi        → 0 yeni · 6 mükerrer
güven 0,59 → 0,65                  → skor BANT'tan TEK SAYIYA geçti
```

Son satır tasarımın çalıştığının kanıtı: güven eşiği aşılınca sunum
kendiliğinden değişiyor.

**Koç** — "Paramı nereye yatırmalıyım?" sorusu. Koç reddediyor,
doğrulayıcı geçiriyor, sayı defteri altta görünüyor. Prototipte yanıt
deterministik şablondan gelir; gerçek üründe LLM anlatır ve **aynı**
doğrulayıcıdan geçer.

## Prototip kurulurken yakalanan hatalar

Dördü de `engine/` içinde gerçek hatalardı ve düzeltildi:

1. **N2 çift sayımı geri gelmişti.** `Account.is_linked` iki farklı şeyi
   karıştırıyordu: "API ile bağlı mı" ve "işlemlerini görüyor muyuz".
   Ekstre modelinde kart bağlı değil ama görünür; ödeme vekil harcama
   sayılıp kartın kendi işlemleriyle çift sayılıyordu — gider ₺19.463
   yerine ₺29.978, korunan tutar **negatif**. Artık belirleyici soru
   "bu hesabın işlemleri veride var mı".

2. **Guard, koçun reddetmesini engelliyordu.** *"Yatırım tavsiyesi
   veremem"* cümlesi `investment_advice` kalıbına takılıyordu. Guard,
   koçu doğru davrandığı için cezalandırıyordu. Reddetme ekleri
   (`veremem`, `yetkim yok`, `değilim` …) artık tanınıyor;
   `coach_eval` B09–B11 vakaları bunu kilitliyor.

3. **`projecting` her yanıta uygulanıyordu.** Projeksiyon içermeyen
   yanıtlar çekince dili aranarak reddediliyordu.

4. **`hidden` özniteliği CSS ile eziliyordu.** `.sheet-wrap` üzerindeki
   `display:flex`, `[hidden]`i geçersiz kılıyor ve sheet kapanmıyordu.

## Sonraki adım

Bu prototip doğrulama içindir. Sevk için React Native'e geçilirken
`app/server.py`'deki uç noktalar gerçek API sözleşmesinin taslağıdır:

```
GET  /api/state?s=<gun0|ilk_ekstre|olgun>
GET  /api/bundle
POST /api/triage    {txn_id, planned, emotion}
POST /api/txn       {amount, category, planned, emotion, desc}
POST /api/upload    {sample} | {text, profile, account}
GET  /api/coach?q=<durum|tasarruf|risk|kategori|yatirim>
```
