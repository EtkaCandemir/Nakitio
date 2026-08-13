# Nakitio

Türkiye pazarına yönelik kişisel finans uygulamasının **motoru**.

Bir harcama takip uygulaması değil: kullanıcıya 0–100 arası bir **Finansal
Sağlık Skoru** verir, bu skoru açıklar ve iyileştirmek için somut adımlar
önerir. Veri kaynağı banka ekstresi yüklemedir.

---

## Ürünün üç iddiası

**1. Skor, veri yeterliliğini itiraf eder.**
Az veri varken tek sayı yerine bant gösterir ve onboarding öncülüne
yaklaştırır. Veri arttıkça bant daralır. "Bilmiyoruz" demeyi bilir.

**2. Plansız harcama etiketsiz ölçülebilir.**
Ekstrede "plansızdı" bilgisi yoktur. 10 sinyalli bir model bunu çıkarır;
kullanıcı etiketi çıkarımı *kalibre eder*, yerine geçmez.

**3. AI koç sayı üretmez.**
Yanıttaki her rakam deterministik motordan gelir ve gösterilmeden önce
bir sayı defterine karşı doğrulanır.

---

## Hızlı başlangıç

```bash
cd engine

python3 test_invariants.py     # yapısal kurallar
python3 test_normalize.py      # normalizasyon (N1–N9)
python3 test_ingest.py         # ekstre + davranış çıkarımı
python3 coach_eval.py          # koç guard vakaları

python3 golden_profiles.py     # 15 kullanıcı profilinin skorları
python3 fixture_didem.py       # 281 ham işlem → skor, uçtan uca
python3 tune.py                # parametre duyarlılık analizi
```

Sıfır bağımlılık — yalnızca Python 3.9+ standart kütüphanesi.

Doğrulama prototipi (gerçek motoru çalıştırır, sahte veri yoktur):

```bash
python3 app/server.py          # http://localhost:8765
```

---

## Yapı

```
engine/     Motor. Saf Python, deterministik, test edilmiş.
app/        Doğrulama prototipi. Sevk edilecek uygulama DEĞİL.
Docs/       Şartnameler ve referanslar.
CLAUDE.md   Yapay zekâ asistanları için oryantasyon dosyası.
```

### Katmanlar

```
ekstre → [normalizasyon N1–N9] → [türetilmiş metrikler] → Features
       → [skor motoru] → ScoreResult → [koç | ekran verisi]
```

`Features` katmanlar arası tek sözleşmedir. Skor motoru saftır: aynı
girdi her zaman aynı çıktı, bu yüzden eski bir snapshot yıllar sonra
replay edilebilir.

---

## Dokümantasyon

| Dosya | İçerik |
|---|---|
| [CLAUDE.md](CLAUDE.md) | Giriş noktası — komutlar, kurallar, durum, geçmiş hatalar |
| [Docs/ARCHITECTURE.md](Docs/ARCHITECTURE.md) | Katman haritası, modül sorumlulukları |
| [Docs/ALGORITHM.md](Docs/ALGORITHM.md) | Skor adım adım nasıl hesaplanır |
| [Docs/FORMULAS.md](Docs/FORMULAS.md) | Formül ve 96 parametrenin tam referansı |
| [Docs/DATA-MODEL.md](Docs/DATA-MODEL.md) | Veri sözleşmeleri, alan anlamları |
| [Docs/CONVENTIONS.md](Docs/CONVENTIONS.md) | İhlal edilemez kurallar |
| [Docs/DECISIONS.md](Docs/DECISIONS.md) | Karar günlüğü — neden böyle yapıldı |
| [Docs/TESTING.md](Docs/TESTING.md) | Test stratejisi |
| [Docs/GLOSSARY.md](Docs/GLOSSARY.md) | Terim sözlüğü |

Gerekçeli uzun şartnameler: `Docs/skor-modeli-v2.md`,
`veri-katmani-v1.md`, `ekstre-alimi-v1.md`, `ai-koc-v1.md`,
`ekran-mimarisi-v1.md`.

---

## Durum

**Kilitli:** skor modeli 2.0.0 · veri hattı 1.0.0 · ekstre alımı 1.0.0 ·
davranış çıkarımı 1.0.0 · koç sözleşmesi 1.0.0 · ekran mimarisi ·
çalışan prototip.

**Açık — bilinçli olarak:**

- **Kalibrasyon.** Parametreler literatür ve akıl yürütmeyle konuldu,
  gerçek kullanıcı verisiyle değil. İlk 500–1.000 kullanıcıdan sonra
  dağılıma bakılmalı.
- **Banka profilleri.** `statement_ingest.PROFILES` şemayı gösterir,
  gerçek bankaları değil. Bu katmanın tek gerçek riski budur.
- **LLM entegrasyonu.** Mimari ve doğrulayıcı hazır, model bağlı değil.
- **Üretim backend'i.** `app/server.py` API sözleşmesinin taslağıdır.

Model matematiksel olarak tutarlı ve test edilmiş durumda, ancak **henüz
hiçbir gerçek kullanıcı verisi üzerinde çalışmadı.**

---

## Katkı

Değişiklik yapmadan önce [Docs/CONVENTIONS.md](Docs/CONVENTIONS.md)
okunmalıdır — özellikle §6'daki kontrol listesi.

Parametre değiştirdiysen:

```bash
python3 tune.py --set "anahtar=değer"   # etkisini ölç
python3 golden_profiles.py              # skorlar nasıl kaydı
python3 test_invariants.py              # yapısal kural kırıldı mı
python3 docs_sync.py                    # dokümanları yenile
```

---

Tüm hakları saklıdır.
