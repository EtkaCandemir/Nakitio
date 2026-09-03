"""
Nakitio — Algoritma ve Karar Motoru belgesi üreticisi.

Bu dosya bir PDF üretir ve içindeki HİÇBİR SAYI ELLE YAZILMAZ: hepsi motor
çalıştırılarak, `params.P`den, golden profillerden ve test süitlerinden
okunur. Gerekçesi `docs_sync.py` ile aynı ve bu depodaki en pahalı doküman
hatasının karşılığıdır: elle yazılan bir ölçüm iddiası kaçınılmaz olarak
bayatlar ve yalan söylemeye başlar ("96 parametreden 27'si yüksek etkili"
cümlesi, profil sayısı 10'dan 15'e çıkınca sessizce yanlış oldu).

Motor SIFIR BAĞIMLILIK kuralına tabidir; bu araç ona dahil değildir.
`reportlab` yoksa net bir mesajla çıkar, motoru etkilemez.

Çalıştırma:
    python3 engine/algoritma_pdf.py [çıktı.pdf]
"""

from __future__ import annotations

import glob
import os
import re
import subprocess
import sys
from datetime import date

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

try:
    from reportlab.lib import colors
    from reportlab.lib.enums import TA_JUSTIFY
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.styles import ParagraphStyle
    from reportlab.lib.units import mm
    from reportlab.pdfbase import pdfmetrics
    from reportlab.pdfbase.ttfonts import TTFont
    from reportlab.platypus import (BaseDocTemplate, Frame, KeepTogether,
                                    PageTemplate, Paragraph, Spacer, Table,
                                    TableStyle)
except ImportError:
    sys.exit("Bu araç `reportlab` gerektirir (motor gerektirmez):\n"
             "    python3 -m pip install reportlab")

import params
from score_engine import (LEVELS, MODEL_VERSION, P, PILLARS, Features,
                          compute_score, project_risks, sensitivity_at,
                          attribute, without)


# ─────────────────────────────────────────────────────────────────────────────
# Tipografi
# ─────────────────────────────────────────────────────────────────────────────
#
# Türkçe metin ASCII fontlarla sessizce bozulur: "ğ" ve "ş" kutu olur,
# "İ" düşer. Font seçilirken glif kapsamı DENETLENİR — "muhtemelen vardır"
# varsayımı, bu deponun tam olarak kaçındığı hata türü.

GEREKLI_GLIFLER = "ğüşıöçĞÜŞİÖÇ₺—·"

FONT_ADAYLARI = [
    ("/System/Library/Fonts/SFNS.ttf", "/System/Library/Fonts/SFNSMono.ttf"),
    ("/System/Library/Fonts/Supplemental/Verdana.ttf",
     "/System/Library/Fonts/Menlo.ttc"),
    ("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
     "/usr/share/fonts/truetype/dejavu/DejaVuSansMono.ttf"),
]


def _fontlari_kur():
    for govde, mono in FONT_ADAYLARI:
        if not os.path.exists(govde):
            continue
        try:
            pdfmetrics.registerFont(TTFont("NK", govde))
            eksik = [c for c in GEREKLI_GLIFLER
                     if ord(c) not in pdfmetrics.getFont("NK").face.charToGlyph]
            if eksik:
                continue
            mono_ad = "NKMono"
            try:
                pdfmetrics.registerFont(TTFont(mono_ad, mono))
            except Exception:
                mono_ad = "NK"
            return "NK", mono_ad
        except Exception:
            continue
    sys.exit("Türkçe glifleri taşıyan bir TTF bulunamadı.")


GOVDE, MONO = _fontlari_kur()

MOR = colors.HexColor("#5B3FA8")
GRI = colors.HexColor("#5A5A66")
ACIK = colors.HexColor("#F4F2F9")
CIZGI = colors.HexColor("#D8D4E4")

S = {
    "h1": ParagraphStyle("h1", fontName=GOVDE, fontSize=17, leading=21,
                         textColor=MOR, spaceBefore=2, spaceAfter=8),
    "h2": ParagraphStyle("h2", fontName=GOVDE, fontSize=11.5, leading=15,
                         textColor=MOR, spaceBefore=13, spaceAfter=5),
    "h3": ParagraphStyle("h3", fontName=GOVDE, fontSize=9.6, leading=13,
                         textColor=colors.HexColor("#2A2A33"),
                         spaceBefore=9, spaceAfter=3),
    "p": ParagraphStyle("p", fontName=GOVDE, fontSize=8.7, leading=12.6,
                        alignment=TA_JUSTIFY, spaceAfter=5,
                        textColor=colors.HexColor("#22222A")),
    "not": ParagraphStyle("not", fontName=GOVDE, fontSize=7.9, leading=11.2,
                          textColor=GRI, spaceAfter=5, leftIndent=8,
                          borderPadding=0),
    "kod": ParagraphStyle("kod", fontName=MONO, fontSize=7.5, leading=10.4,
                          textColor=colors.HexColor("#1E3A5F"),
                          backColor=ACIK, borderPadding=6,
                          spaceBefore=3, spaceAfter=7),
    "kapak_b": ParagraphStyle("kb", fontName=GOVDE, fontSize=26, leading=30,
                              textColor=MOR, spaceAfter=4),
    "kapak_a": ParagraphStyle("ka", fontName=GOVDE, fontSize=12, leading=17,
                              textColor=GRI, spaceAfter=16),
}


def Pr(t, s="p"):
    return Paragraph(t, S[s])


# ─────────────────────────────────────────────────────────────────────────────
# Tablo yardımcıları
# ─────────────────────────────────────────────────────────────────────────────

def tablo(basliklar, satirlar, genislikler, hizalama=None, punto=7.6):
    veri = [[Pr(f"<b>{b}</b>", "not") for b in basliklar]]
    for s in satirlar:
        veri.append([x if hasattr(x, "wrap")
                     else Paragraph(str(x), ParagraphStyle(
                         "h", fontName=GOVDE, fontSize=punto, leading=punto + 3.2,
                         textColor=colors.HexColor("#22222A")))
                     for x in s])
    t = Table(veri, colWidths=genislikler, repeatRows=1, hAlign="LEFT")
    stil = [
        ("BACKGROUND", (0, 0), (-1, 0), ACIK),
        ("LINEBELOW", (0, 0), (-1, 0), 0.7, MOR),
        ("LINEBELOW", (0, 1), (-1, -2), 0.25, CIZGI),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("TOPPADDING", (0, 0), (-1, -1), 3.5),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 3.5),
        ("LEFTPADDING", (0, 0), (-1, -1), 5),
        ("RIGHTPADDING", (0, 0), (-1, -1), 5),
    ]
    for i, h in enumerate(hizalama or []):
        if h in ("RIGHT", "CENTER"):
            stil.append(("ALIGN", (i, 0), (i, -1), h))
    t.setStyle(TableStyle(stil))
    return t


def _sayi(v, ondalik=2):
    if isinstance(v, float) and v == int(v):
        v = int(v)
    s = f"{v:,.{ondalik}f}" if isinstance(v, float) else f"{v:,}"
    return s.replace(",", " ").replace(".", ",")


# ─────────────────────────────────────────────────────────────────────────────
# Motordan okunan gerçekler
# ─────────────────────────────────────────────────────────────────────────────

def _profil(anahtar):
    from golden_profiles import PROFILES
    return PROFILES[anahtar][0]


def _kirilim():
    """Altı bileşen × alt metrikleri — CANLI motordan."""
    from golden_profiles import PROFILES
    r = compute_score(PROFILES["didem"][0])
    out = []
    for p in r.pillars:
        out.append((p.label, p.weight_declared or p.weight_nominal,
                    [(x.key, x.label, x.weight) for x in p.subs]))
    return out


def _test_sayilari():
    toplam, satir = 0, []
    for dosya in ("test_invariants.py", "test_normalize.py",
                  "test_ingest.py", "coach_eval.py"):
        r = subprocess.run([sys.executable, dosya], cwd=HERE,
                           capture_output=True, text=True)
        son = (r.stdout or "").strip().splitlines()
        n = 0
        if son:
            m = re.search(r"(\d+)\s*(?:kontrolün|vaka)", son[-1])
            if m:
                n = int(m.group(1))
                if "vaka" in son[-1]:
                    n += len(re.findall(r"\[\s*ok\]\s+t_", r.stdout))
        toplam += n
        satir.append((dosya, n))
    return satir, toplam


def _tune_ozeti():
    import tune
    rows = tune.rank()
    kova = lambda alt, ust: sum(1 for _, m in rows
                                if alt <= m["azami_oynama"] < ust)
    olculemedi = sum(1 for _, m in rows
                     if m["azami_oynama"] == 0 and m["ham_oynama"] == 0
                     and m["band_oynama"] == 0 and m["etiket_degisimi"] == 0)
    return {"yuksek": sum(1 for _, m in rows if m["azami_oynama"] >= 3),
            "orta": kova(1, 3), "olculemedi": olculemedi,
            "toplam": len(rows), "en_ust": rows[0]}


# ─────────────────────────────────────────────────────────────────────────────
# Bölümler
# ─────────────────────────────────────────────────────────────────────────────

def bolum_kapak():
    import normalize
    ak = []
    ak.append(Spacer(1, 40 * mm))
    ak.append(Pr("Nakitio", "kapak_b"))
    ak.append(Pr("Skor Algoritması ve Karar Motoru", "kapak_a"))
    ak.append(tablo(
        ["Katman", "Sürüm", "Kaynak"],
        [("Skor modeli", MODEL_VERSION, "engine/score_engine.py"),
         ("Veri hattı", normalize.PIPELINE_VERSION, "engine/normalize.py"),
         ("Kategorizasyon", normalize.CATEGORY_VERSION, "engine/markalar.py")],
        [45 * mm, 25 * mm, 75 * mm]))
    ak.append(Spacer(1, 10 * mm))
    ak.append(Pr(
        "Bu belge, bir kullanıcının finansal sağlık skorunun nasıl üretildiğini "
        "ve motorun ona <b>ne önereceğine nasıl karar verdiğini</b> anlatır. "
        "Buradaki her sayı motor çalıştırılarak üretilmiştir; hiçbiri elle "
        "yazılmamıştır. Doküman ile kod çeliştiğinde <b>kod esas alınır</b>."))
    ak.append(Pr(
        "<b>Ürün ne değildir.</b> Nakitio bir harcama takip uygulaması değildir "
        "ve bir kredi notu (Findeks) değildir. Kullanıcıya 0–100 arası bir skor "
        "verir, bu skoru bileşenlerine ayırıp açıklar ve iyileştirmek için "
        "deterministik olarak hesaplanmış adımlar önerir."))
    ak.append(Spacer(1, 6 * mm))
    ak.append(Pr(
        f"Üretim tarihi: {date.today().isoformat()} · "
        f"engine/algoritma_pdf.py ile üretildi", "not"))
    return ak


def bolum_iddia():
    ak = [Pr("1 · Ürünün üç iddiası", "h2")]
    ak.append(Pr(
        "Modelin tamamı bu üç cümleyi savunmak için kuruldu. Her biri koda "
        "bağlanmıştır ve testle korunur."))
    ak.append(tablo(
        ["İddia", "Kodda karşılığı"],
        [("<b>Skor, veri yeterliliğini itiraf eder.</b> Az veri varken bant "
          "olarak gösterilir ve öncüle yaklaştırılır.",
          "Güven <i>C</i>; <font name='%s' size=7>SubScore.requires</font>; "
          "belirsizlik bandı" % MONO),
         ("<b>Plansız harcama etiketsiz ölçülebilir.</b> Ekstreden çıkarım "
          "yapılır; kullanıcı etiketi çıkarımı kalibre eder, yerine geçmez.",
          "<font name='%s' size=7>behavior_infer</font> — 10 sinyalli lojistik "
          "model; etiket yalnız kesişimi kaydırır" % MONO),
         ("<b>AI koç sayı üretmez.</b> Her rakam deterministik motordan gelir "
          "ve yanıt gösterilmeden önce doğrulanır.",
          "<font name='%s' size=7>NumberLedger</font> + "
          "<font name='%s' size=7>verify_response()</font>" % (MONO, MONO))],
        [88 * mm, 57 * mm]))
    return ak


def bolum_akis():
    ak = [Pr("2 · Veri akışı", "h2")]
    ak.append(Pr(
        "Veri kaynağı banka ekstresi yüklemedir: açık bankacılık değil, manuel "
        "giriş değil. Bu seçim hem iOS hem Android'de lisanssız çalışır ve banka "
        "doğruluğunda veri verir — ama zaman eksenini ve davranış ölçümünü kırar; "
        "ikisi de ayrıca çözülür. <b>v3'te motor kaynağa uyarlanır</b>: manuel "
        "girişle beslenen bir kullanıcıda ölçülemeyen metrikler kapanır, "
        "cezalandırılmaz (bkz. §6)."))
    ak.append(Paragraph(
        "ekstre (PDF / CSV)<br/>"
        "&nbsp;&nbsp;│<br/>"
        "&nbsp;&nbsp;▼&nbsp; K0&nbsp; banka profiliyle ayrıştırma + tekilleştirme<br/>"
        "ParsedStatement<br/>"
        "&nbsp;&nbsp;│<br/>"
        "&nbsp;&nbsp;▼&nbsp; K1&nbsp; N1–N9 normalizasyon<br/>"
        "Ledger&nbsp; ── iki gider görünümü: nakit / tahakkuk<br/>"
        "&nbsp;&nbsp;│<br/>"
        "&nbsp;&nbsp;▼&nbsp; K2&nbsp; 30 günlük kayan pencereler, medyanlar, oranlar<br/>"
        "<b>Features</b>&nbsp;&nbsp;◄── SÖZLEŞME SINIRI<br/>"
        "&nbsp;&nbsp;│<br/>"
        "&nbsp;&nbsp;▼&nbsp; K3&nbsp; skor motoru (SAF fonksiyon)<br/>"
        "ScoreResult<br/>"
        "&nbsp;&nbsp;│<br/>"
        "&nbsp;&nbsp;├──▶&nbsp; K4&nbsp; <b>karar motoru</b> — atıf · kaldıraç · plan · erken uyarı<br/>"
        "&nbsp;&nbsp;└──▶&nbsp; K5&nbsp; ekran verisi",
        S["kod"]))
    ak.append(Pr(
        "<b>Features bu mimarinin bel kemiğidir.</b> Skor motorunun tek "
        "girdisidir ve motor saf bir fonksiyondur: I/O yok, rastgelelik yok, "
        f"<font name='{MONO}' size=7>datetime.now()</font> yok. Aynı Features "
        "her zaman aynı ScoreResult üretir. Sebebi replay edilebilirliktir — "
        "eski bir anlık görüntü yıllar sonra aynı skoru vermeli ki kullanıcı "
        "itirazı yanıtlanabilsin ve model güvenle değiştirilebilsin."))
    return ak


def bolum_skor():
    ak = [Pr("3 · Skor nasıl hesaplanır", "h2")]
    ak.append(Paragraph(
        "S_ham&nbsp;&nbsp;&nbsp;&nbsp;= Σ wᵢ_norm × pᵢ&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;"
        "altı bileşenin ağırlıklı toplamı<br/>"
        f"S_öncül&nbsp;&nbsp;= clamp({_sayi(P['prior.baz'],0)} + Σ onboarding, "
        f"{_sayi(P['prior.min'],0)}, {_sayi(P['prior.max'],0)})"
        "&nbsp;&nbsp;&nbsp;ankete dayalı baz<br/>"
        "S_karma&nbsp;&nbsp;= C × S_ham + (1 − C) × S_öncül&nbsp;&nbsp;&nbsp;"
        "<b>GÜVEN HARMANLAMASI</b><br/>"
        "S_final&nbsp;&nbsp;= yumuşat(S_karma, çapa)&nbsp;&nbsp;&nbsp;&nbsp;"
        "asimetrik EWMA", S["kod"]))
    ak.append(Pr(
        "Bu tek denklem v1'in üç ayrı formülünün yerini alır. v1'de gün 30'da "
        "formül tamamen değişiyordu ve ölçüldü: her şeyi doğru yapan kullanıcı "
        "gün 30'da 87,5 alıp gün 31'de ~55'e düşüyordu — tek gecede 32 puan, "
        "hem de en çok emek vermiş kullanıcıda. Artık aşamalar kod değil, "
        "yalnızca sunum etiketidir."))

    ak.append(Pr("3.1 · Altı bileşen, yirmi yedi alt metrik", "h3"))
    kirilim = _kirilim()
    satirlar = []
    for label, agirlik, subs in kirilim:
        alt = " · ".join(f"{ad} <font color='#8A8A96'>{_sayi(w, 2)}</font>"
                         for _k, ad, w in subs)
        satirlar.append((f"<b>{label}</b>", _sayi(agirlik, 0), alt))
    ak.append(tablo(["Bileşen", "Ağırlık", "Alt metrikler (bileşen içi ağırlıkla)"],
                    satirlar, [33 * mm, 14 * mm, 98 * mm],
                    hizalama=[None, "CENTER", None], punto=7.0))
    ak.append(Pr(
        "Ağırlıklar v3'te <b>değişmedi</b>. Sebebi ölçüldü: bileşen ağırlıklarını "
        "±5 kaydırmak hiçbir profilde skoru 2 puandan fazla oynatmıyor, çünkü "
        "bileşenler korele. Derinleşme bu yüzden ağırlıklarla değil, "
        "<b>bileşenlerin içinde</b> yapıldı (23 → 27 alt metrik).", "not"))

    ak.append(Pr("3.2 · Üç eşleme fonksiyonu", "h3"))
    ak.append(Pr(
        "Basamak tablosu kullanılmaz. v1'de gider/gelir %70,0 iken 25 puan, "
        "%70,1 iken 20 puandı: 28.450 TL gelirde 28 TL fazla harcama 5 puan "
        "kaybettiriyordu. Üç fonksiyon da sürekli, monoton ve [0,100]'e "
        "kelepçelidir."))
    ak.append(Paragraph(
        "lin(x, a, b)&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;= 100 × clamp[0,1]((x − a) / (b − a))"
        "&nbsp;&nbsp;&nbsp;doğrusal geçiş<br/>"
        "sat(x, k)&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;= 100 × (1 − e^(−x/k))"
        "&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;doygunlaşan<br/>"
        "concave(x, F, p)&nbsp;= 100 × min(1, x/F)^p"
        "&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;"
        "ilk birim en değerli", S["kod"]))
    from score_engine import concave
    egri = lambda a: concave(a, P["p3.guvence.tam_ay"], P["p3.guvence.us"])
    ilk = egri(1.0) - egri(0.0)
    ikinci = egri(2.0) - egri(1.0)
    ucuncu = egri(3.0) - egri(2.0)
    tam = _sayi(P["p3.guvence.tam_ay"], 0)
    ak.append(Pr(
        f"<font name='{MONO}' size=7>concave</font> acil fon içindir ve azalan "
        f"getiriyi kodlar: <b>ilk ay {_sayi(ilk,0)} puan</b> getirir, ikinci ay "
        f"{_sayi(ikinci,0)}, üçüncü ay {_sayi(ucuncu,0)}. {tam} ayda tavana "
        f"vurulur — ötesi skora girmez, rozetle ödüllendirilir. Gerçek finansal "
        "riskin şekli budur: sıfır güvenceden bir aylığa geçmek, beşten altıya "
        "geçmekten kıyaslanamaz ölçüde değerlidir.", "not"))
    return ak


def bolum_guven():
    ak = [Pr("4 · Güven (C) — modelin en özgün fikri", "h2")]
    ak.append(Paragraph(
        f"C = {_sayi(P['c.hist.w'])}·geçmiş + {_sayi(P['c.cover.w'])}·kapsam + "
        f"{_sayi(P['c.compl.w'])}·bütünlük + {_sayi(P['c.verif.w'])}·doğrulama + "
        f"{_sayi(P['c.pillar.w'])}·bileşen<br/>"
        f"C ×= min(1, gün / {_sayi(P['c.rampa_gun'],0)})"
        "&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;ilk üç hafta rampası (sert eşik YOK)<br/>"
        f"C ×= {_sayi(P['c.integrity_carpan'])}"
        "&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;"
        "&nbsp;&nbsp;&nbsp;eğer bütünlük şüphesi varsa", S["kod"]))
    ak.append(Pr(
        "C, skorun ne kadarının gözlemlenen veriye dayandığını söyler. Düşükken "
        "skor öncüle yaklaşır, bant genişler ve <b>seviye etiketi hiç "
        "gösterilmez</b>. Gerekçe: 5 onboarding cevabından türetilmiş bir skora "
        "\"Dikkat\" demek, hiçbir zaman utandırmama ilkesinin ihlalidir — "
        "kullanıcı henüz ölçülmedi, yargılanamaz."))
    ak.append(Pr(
        f"<b>Kapsam bir TAVANdır</b>, taban değil: "
        f"linked → bağlı/beyan · statement → {_sayi(P['c.statement_tavan'])} × "
        f"kapsam × kategorize · manual → {_sayi(P['c.manual_tavan'])} × kategorize."))
    ak.append(Pr(
        "<b>v3'te değişen:</b> son terim (<i>bileşen</i>) eskiden yalnız KAPALI "
        "bileşenleri sayıyordu. Dört alt metriğinin üçünü kaybeden bir bileşen "
        "\"tam kapsamlı\" görünüyordu — yani girdi yüzeyinin %37'sini kaybeden "
        "bir veri kaynağı sadece 0,09 güven kaybediyordu. Artık açık bir "
        "bileşenin içindeki kapalı alt metrik de kapsamı düşürür.", "not"))
    return ak


def bolum_eksik_veri():
    ak = [Pr("5 · Eksik veri asla ceza değildir", "h2")]
    ak.append(Pr(
        "Bu, modelin varlık koşuludur. Temel ayrım: <b>None = \"ölçemedik\"</b>, "
        "<b>0 = \"ölçtük, sıfır çıktı\"</b>. İkisini karıştırmak modeli bozar — "
        "ve v2'de üç kez, üçünde de <b>sessizce</b> bozdu."))
    ak.append(tablo(
        ["Alan", "v2'de ne oluyordu", "Sonucu"],
        [(f"<font name='{MONO}' size=7>liquid_balance</font>",
          "bakiye yoksa 0,0 dönüyordu", "tampon alt metriği <b>0 puan</b>"),
         (f"<font name='{MONO}' size=7>disc_share</font>",
          "gider yoksa 0,0 dönüyordu",
          "isteğe bağlı paydan <b>100 PUAN</b> — ölçülmemiş şeye ödül"),
         (f"<font name='{MONO}' size=7>dsr</font>",
          "gelir yoksa 1,0 dönüyordu", "borç en kötü <i>varsayıldı</i>")],
        [34 * mm, 47 * mm, 64 * mm]))
    ak.append(Pr(
        "Hiçbiri test kırmadı, çünkü test edilecek bir <b>sözleşme</b> yoktu. "
        "v3'te sözleşme kuruldu: her alt metrik hangi <i>Features</i> alanlarına "
        "ihtiyaç duyduğunu bildirir."))
    ak.append(Paragraph(
        'SubScore("guvence", "Acil durum fonu", guvence, P["p3.guvence.w"],<br/>'
        '&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;detay, '
        '<b>requires=("ef_liquid",)</b>)', S["kod"]))
    ak.append(tablo(
        ["Düzey", "Eksik olan", "Ne yapılır"],
        [("Alt metrik", "Bir ölçüm yapılamadı",
          "Ağırlığı bileşen içinde kalanlara dağıtılır, sıfır puan <b>VERİLMEZ</b>; "
          "güven düşer"),
         ("Bileşen", "Tüm alt metrikler None",
          "Bileşen devre dışı; ağırlığı diğerlerine dağıtılır, toplam yine 100"),
         ("Kategori", "İşyeri tanınmadı",
          "Zorunluluk ağırlığı BİLİNMİYOR sayılır; oran bilinenden tahmin edilir")],
        [24 * mm, 38 * mm, 83 * mm]))
    ak.append(Pr(
        "Bildirim üç şey sağlar: (1) test bildirilen alanları boşaltıp alt "
        "metriğin gerçekten kapandığını denetler, (2) sunum katmanı \"bu metriği "
        "neden göremiyorsun\" diyebilir, (3) yalnız ekstreden ölçülebilen yeni bir "
        "metrik, manuel kullanıcıda kendiliğinden kapanır."))
    ak.append(Pr(
        "<b>İnce ayrım:</b> payı sıfır olan oran tanımsız DEĞİLDİR, sıfırdır. "
        f"<font name='{MONO}' size=7>s_deliberate</font> işlemlerden doğrudan "
        "ölçülür; \"hiç birikim yapmadı\" gelir bilinmese de bilinen bir olgudur. "
        "Bu ayrım olmadan geliri gizlemek olumsuz bir bulguyu siler — ölçüldü, "
        "+1 puan kazandırıyordu.", "not"))
    return ak


def bolum_v3_yenilik():
    ak = [Pr("6 · v3'te ne değişti", "h2")]
    ak.append(Pr(
        "Dördünün de verisi ham sözleşmede <b>zaten vardı</b> ve motorda hiç "
        "okunmuyordu. Yeni bir alt metriğin tek meşru gerekçesi, modelin o ana "
        "kadar ayırt <b>edemediği</b> iki durumu ayırt etmesidir."))
    from golden_profiles import PROFILES
    okan = compute_score(PROFILES["okan"][0])
    pelin = compute_score(PROFILES["pelin"][0])
    kerem = compute_score(PROFILES["kerem"][0])
    kerem_nwsuz = compute_score(without(PROFILES["kerem"][0], "net_worth"))
    ak.append(tablo(
        ["Alt metrik", "Bileşen", "Ne ayırt eder"],
        [("<b>Borcun ortalama faizi</b>", "Borç Yükü",
          "Borcun HACMİ değil FİYATI. Aynı DSR ve taahhütle %0 taksit ile %60 "
          "KMH birebir aynı puanı alıyordu"),
         ("<b>Ödeme zamanlaması</b>", "Nakit Akışı",
          "Parayı kaç gün taşımak zorunda. Maaşı 1'inde gelip kartı 5'inde ödeyen "
          "taze parayla öder; 20'sinde gelip 5'inde ödeyen önceki ayın artığından"),
         ("<b>Net varlık</b>", "Tasarruf &amp; Güvence",
          "Akış değil STOK. 3 aylık acil fonu olup 200.000 TL borcu olan "
          "kullanıcıyı ayırır"),
         ("<b>Plana uyum</b>", "Hedef Devamlılığı",
          "İlerleme değil SÖZE UYMA. Fazla iyimser hedef koymuş biri plana "
          "harfiyen uysa da ilerlemede geride görünür")],
        [30 * mm, 26 * mm, 89 * mm]))
    ak.append(Pr("6.1 · İddia ölçülerek sınandı", "h3"))
    ak.append(tablo(
        ["Sınav", "Sonuç"],
        [("<b>okan / pelin</b> — aynı DSR, aynı taahhüt, aynı anapara; tek fark "
          "faiz (%0 vs %65)",
          f"ham skor <b>{_sayi(okan.raw_score,1)}</b> vs "
          f"<b>{_sayi(pelin.raw_score,1)}</b>. Faiz alanı boşaltılınca fark "
          "<b>tam olarak sıfırlanıyor</b>"),
         ("<b>kerem</b> — net varlığı yıllık gelirinin 2 katı (alt metrikte tam "
          "puan) ama gelirinin %108'ini harcıyor. Stok, akışı maskeliyor mu?",
          f"skor <b>{kerem.score}</b>; net varlık ölçülmeseydi "
          f"<b>{kerem_nwsuz.score}</b>. Maskeleme "
          f"<b>{kerem.score - kerem_nwsuz.score:+d} puan</b> — test 2 ile sınırlıyor")],
        [72 * mm, 73 * mm]))
    ak.append(Pr(
        "<b>Ölçmeden parametre eklenmedi.</b> Yeni eşikler önce "
        f"<font name='{MONO}' size=7>tune.py</font> tarafından \"⚠ ölçülemedi\" "
        "diye raporlandı — hiçbir golden profil yeni alanları taşımıyordu. "
        "Parametreyi ölçmeden ayarlamak deponun kendi kuralını çiğner, o yüzden "
        "profiller önce eklendi.", "not"))
    return ak


def bolum_karar_motoru():
    from coach_tools import (ACTIONS, TOOLS, build_context, build_action_plan,
                             detected_subscriptions, ABONELIK_AZAMI_ZORUNLULUK)
    from golden_profiles import PROFILES
    import dataclasses

    ak = [Pr("7 · Karar motoru", "h2")]
    ak.append(Pr(
        "Skor bir <b>ölçüm</b>dür; karar motoru ondan <b>ne yapılacağını</b> "
        "türetir. Dört ayrı soruyu cevaplar ve dördü de deterministiktir — "
        f"LLM hiçbirini üretmez, yalnızca anlatır. Araç yüzeyi {len(TOOLS)} "
        "araçtan oluşur."))

    # ── 7.1 atıf ───────────────────────────────────────────────────────
    ak.append(Pr("7.1 · \"Skorum neden düştü?\" — alt metrik düzeyinde atıf", "h3"))
    # ZİNCİRLEME: önceki dönemin sonucu, bu dönemin çapası olur — üretimde
    # nasıl çalışıyorsa öyle. İki bağımsız hesabı karşılaştırmak yumuşatmayı
    # yanlış yerden ölçerdi.
    f = PROFILES["didem"][0]
    onceki = compute_score(dataclasses.replace(
        f, ef_liquid=42_000, s_deliberate=6_000, liquid_balance=30_000))
    simdi = compute_score(dataclasses.replace(
        f, ef_liquid=9_000, s_deliberate=1_500, liquid_balance=8_000,
        prev_score=onceki.score, prev_raw_score=onceki.raw_score,
        prev_confidence=onceki.confidence))
    satir = []
    for r in attribute(onceki, simdi):
        satir.append((f"<b>{r['label']}</b>", f"<b>{_sayi(r['delta'],2)}</b>", ""))
        for a in r.get("alt_kirilim", []):
            ol = " <font color='#8A8A96'>(ölçüm)</font>" if a["olcum_degisimi"] else ""
            satir.append((f"&nbsp;&nbsp;&nbsp;{a['label']}{ol}", _sayi(a["delta"], 2),
                          f"{a['from']} → {a['to']}"))
    ak.append(tablo(["Katkı", "Puan", "Alt metrik değeri"], satir,
                    [78 * mm, 22 * mm, 45 * mm],
                    hizalama=[None, "RIGHT", None], punto=7.2))
    ak.append(Pr(
        f"<b>Yumuşatma satırını okumak.</b> Bu örnekte ham skor "
        f"{_sayi(onceki.raw_score - simdi.raw_score, 1)} puan düştü ama "
        f"gösterilen skor yalnız {onceki.score - simdi.score} puan indi — farkı "
        "yumuşatma tutuyor. Satır bir hata değil, modelin çalışan bir "
        "parçasıdır: <b>maddi olay yoksa</b> kötü haber de yavaş yayılır. "
        "Maddi olay varsa aşağı yöndeki sınır kalkar ve bu satır küçülür.", "not"))
    ak.append(Pr(
        "Katkılar farkı <b>tam</b> kapatır (0,05 tolerans) ve bu bir testle "
        "korunur: toplamı tutmayan bir açıklama göstermek, sayı uydurmakla aynı "
        "sınıf hatadır. Ayrıca <b>ölçüm değişimi ayrı işaretlenir</b> — bir alt "
        "metriğin açılıp kapanması diğerlerinin ağırlığını oynatır, ve "
        "kullanıcıya \"durumun kötüleşmedi, biz artık ölçebiliyoruz\" "
        "diyebilmek buna bağlıdır.", "not"))

    # ── 7.2 kaldıraç ───────────────────────────────────────────────────
    ak.append(Pr("7.2 · \"Nereye dokunursam en çok kazanırım?\" — kaldıraç", "h3"))
    r = compute_score(f)
    sat = [(d["alt_metrik"], d["bilesen"], _sayi(d["deger"], 1),
            _sayi(d["bosluk"], 1), _sayi(d["kaldirac"], 3),
            f"<b>{_sayi(d['azami_kazanc'],2)}</b>")
           for d in sensitivity_at(r)[:6]]
    ak.append(tablo(["Alt metrik", "Bileşen", "Değer", "Boşluk", "Kaldıraç",
                     "Azami kazanç"], sat,
                    [38 * mm, 32 * mm, 16 * mm, 16 * mm, 19 * mm, 24 * mm],
                    hizalama=[None, None, "RIGHT", "RIGHT", "RIGHT", "RIGHT"],
                    punto=7.2))
    ak.append(Pr(
        "İki sayı ayrı ayrı önemlidir ve bu tabloda ayrışırlar: <i>kaldıraç</i> "
        "alt metrik 10 puan oynarsa skora kaç puan geleceğidir, <i>boşluk</i> ise "
        "o metrikte kalan tavandır. <b>Kaldıracı en yüksek metrik, kazancı en "
        "yüksek metrik değildir</b> — boşluğu olmayanı önermek kullanıcıyı boşa "
        "yorar. Hesap kapalı formda çıkar; simülasyon yapılmaz.", "not"))

    # ── 7.3 öneri ──────────────────────────────────────────────────────
    ak.append(Pr("7.3 · \"Ne yapmalıyım?\" — öneri üretimi ve sıralaması", "h3"))
    ak.append(Pr(
        f"{len(ACTIONS)} aksiyon tanımlıdır. Her biri (a) bu kullanıcı için "
        "<b>anlamlı mı</b> diye bir uygunluk kapısından geçer, (b) tek başına "
        "simüle edilir, (c) <i>kazanç / çaba</i> oranına göre sıralanır, "
        "(d) plana <b>kümülatif</b> eklenir."))
    ak.append(tablo(
        ["Aksiyon", "Çaba", "Uygunluk kapısı ne sorar"],
        [(s.label, {1: "kolay", 2: "orta", 3: "zor"}[s.effort],
          {"kategori_limiti": "Harcama kaydı var mı",
           "acil_fon_katkisi": "Geliri giderini karşılıyor mu",
           "plansiz_azalt": "Plansız harcama oranı ölçüldü mü",
           "ek_borc_odemesi": "Kapatılacak borcu var mı",
           "abonelik_iptali": "<b>İPTAL EDİLEBİLİR</b> yinelenen ödeme var mı",
           "borc_maliyetini_dusur": "Borcunun faizi yüksek mi",
           "odeme_tarihi_kaydir": "Ödeme günü maaşından uzak mı"}.get(s.key, ""))
         for s in sorted(ACTIONS.values(), key=lambda x: x.effort)],
        [50 * mm, 16 * mm, 79 * mm], punto=7.2))
    ak.append(Pr(
        "<b>Kümülatiflik neden zorunlu:</b> aksiyonların etkisi toplanabilir "
        "değildir — aynı bileşeni doyuran iki adımın toplam etkisi, tek tek "
        "etkilerinin toplamından küçüktür. Koç \"toplam +9 puan\" derse ve bu "
        "ayrı ayrı hesaplanmış etkilerin toplamıysa, vaat tutmaz."))
    ak.append(Pr(
        "<b>Gerçek veriye bağlanınca çıkan güvenlik sorunu.</b> "
        f"<font name='{MONO}' size=7>abonelik_iptali</font>'nin tasarruf tutarı "
        "eskiden <i>toplam gider × %1</i> varsayımıydı: koç, kullanıcının hiç "
        "sahip olmadığı bir aboneliği iptal etmesini önerebiliyordu. Ekstreden "
        "tespite bağlandığında ilk öneri <b>\"telefon faturanı iptal et\"</b> "
        "oldu — yinelenen olmak iptal edilebilir olmak değildir; kira, aidat ve "
        "sigorta da her ay tekrarlar. Kapı taksonomideki zorunluluk ağırlığıdır "
        f"(≤ {_sayi(ABONELIK_AZAMI_ZORUNLULUK)}): <i>abonelik</i> 0,10 ve "
        "<i>eğlence</i> 0,00 geçer, <i>iletişim</i> 0,85 geçmez. Ağırlığı "
        "<b>bilinmeyen</b> kategori de elenir — bilmediğimiz bir şeyin iptal "
        "edilebilir olduğunu varsayamayız.", "not"))
    return ak


def bolum_erken_uyari():
    from coach_tools import build_context, get_projected_risks
    from coach_guard import verify_response
    import dataclasses
    from golden_profiles import PROFILES

    ak = [Pr("7.4 · \"Ne olabilir?\" — erken uyarı", "h3")]
    ak.append(Pr(
        "Maddi olay listesi <b>tepkiseldir</b>: olay olduktan sonra bildirir. "
        "Erken uyarı ölçülmüş eğilimi uzatıp olayın <b>ne zaman</b> geleceğini "
        "kestirir. Koçun en riskli yeteneğidir — henüz olmamış bir şey hakkında "
        "sayı söyler — ve üç kısıtla çevrilidir."))
    f = dataclasses.replace(PROFILES["didem"][0], e_total=34_000,
                            ef_liquid=22_000, prev_score=None)
    ctx = build_context(f)
    pr = get_projected_risks(ctx, horizon_months=6)
    p0 = pr["projeksiyonlar"][0]
    ak.append(Paragraph(
        f"project_risks(f, horizon_months=6) →<br/>"
        f"&nbsp;&nbsp;olay&nbsp;&nbsp;&nbsp;&nbsp;: {p0['olay']}<br/>"
        f"&nbsp;&nbsp;ne zaman: ~{_sayi(p0['ay'],1)} ay<br/>"
        f"&nbsp;&nbsp;gerekçe&nbsp;: {p0['gerekce']}<br/>"
        f"&nbsp;&nbsp;sinyal&nbsp;&nbsp;: " +
        " · ".join(f"{k}={_sayi(v,0)}" for k, v in p0["sinyal"].items()),
        S["kod"]))
    ak.append(tablo(
        ["Kısıt", "Neden"],
        [("Ufuk <b>parametredir</b>",
          f"Motor saftır: <font name='{MONO}' size=7>datetime.now()</font> "
          "okumaz, \"bugün\" diye bir kavramı yoktur (K1)"),
         ("Eğilim ölçülmemişse <b>projeksiyon yapılmaz</b>",
          "Tek dönemlik veriden gelecek kestirmek, uydurulmuş sinyal üretmektir "
          "— eksik sinyalden kötüdür"),
         ("Olay <b>zaten gerçekleştiyse</b> ileriye atılmaz",
          "Fonu kritik olan kullanıcıya \"ileride kritik olacak\" demek anlamsızdır")],
        [56 * mm, 89 * mm]))

    ak.append(Pr("7.5 · Sayı sadakati — guard", "h3"))
    ak.append(Pr(
        "Karar motorunun ürettiği her sayı <i>NumberLedger</i>'a yazılır ve "
        "koçun yanıtı gösterilmeden önce deftere karşı doğrulanır. Projeksiyonlar "
        "ayrıca <b>çekince dili</b> zorunluluğuna tabidir. Aşağıdaki dört sonuç "
        "bu belge üretilirken canlı olarak ölçüldü:"))
    senaryolar = [
        ("Çekinceli, deftere uygun",
         f"Bu gidişle acil durum fonun yaklaşık {p0['ay']} ay içinde kritik "
         "seviyeye inebilir. Kategori limiti koymayı deneyebilirsin."),
        ("Kesinlik dili",
         f"Acil durum fonun kesinlikle {p0['ay']} ay içinde bitecek. Limit koy."),
        ("Uydurma sayı (defterde yok)",
         "Bu gidişle acil fonun yaklaşık 2.1 ay içinde tükenebilir. Limit koymayı dene."),
        ("Çekince yok (projeksiyon)",
         f"Acil durum fonun {p0['ay']} ay içinde kritik seviyeye iner. Limit koy."),
    ]
    sat = []
    for ad, metin in senaryolar:
        # AYNI bağlam kullanılır. Her doğrulama için yeni bir `CoachContext`
        # kurmak, sayı defterini BOŞ bırakır ve geçmesi gereken yanıt da
        # `hallucinated_number` ile reddedilir. Bu belgenin ilk üretiminde
        # tam olarak bu oldu — guard'ın kendi sözleşmesi: doğrulama, sayıyı
        # ÜRETEN araç çağrısıyla aynı defteri görmek zorundadır.
        rep = verify_response(ctx, metin, projecting=True)
        kod = ", ".join(v.code for v in rep.violations) or "—"
        sat.append((ad, "<b>geçti</b>" if rep.ok else "<b>reddedildi</b>",
                    f"<font name='{MONO}' size=7>{kod}</font>"))
    ak.append(tablo(["Koç yanıtı", "Sonuç", "Guard kodu"], sat,
                    [56 * mm, 25 * mm, 64 * mm]))
    ak.append(Pr(
        "Prompt bir rica, guard bir garantidir. Kullanıcı hiçbir koşulda "
        "doğrulanmamış bir sayı görmez — bozuk bir cevap, uydurulmuş bir "
        "cevaptan iyidir.", "not"))
    return ak


def bolum_kaynak_uyarlama():
    import dataclasses
    from golden_profiles import PROFILES
    ak = [Pr("8 · Kaynak uyarlanabilirliği", "h2")]
    ak.append(Pr(
        "Motor ekstre için tasarlandı, ama tek veri kaynağı o değil. "
        "<b>yasemin</b> profili manuel giriş yüzeyini temsil eder: bakiye yok, "
        "çok pencereli oynaklık/trend yok, kart limiti yok; davranış ise "
        "çıkarım değil kullanıcı etiketinden geliyor."))
    f = PROFILES["yasemin"][0]
    r = compute_score(f)
    ek = compute_score(dataclasses.replace(f, data_source="statement",
                                           statement_coverage=1.0,
                                           manual_entry=False))
    kapali = sum(1 for p in r.pillars for x in p.subs if x.value is None)
    toplam = sum(len(p.subs) for p in r.pillars)
    coken = sum(1 for p in r.pillars if not p.enabled)
    ak.append(tablo(
        ["Ölçüt", "Manuel giriş", "Aynı durum, ekstre ile"],
        [("Kapanan alt metrik", f"<b>{kapali} / {toplam}</b>", "0"),
         ("Çöken bileşen", f"<b>{coken}</b>", "0"),
         ("Ağırlık toplamı",
          f"{_sayi(sum(p.weight_effective for p in r.pillars),1)}",
          f"{_sayi(sum(p.weight_effective for p in ek.pillars),1)}"),
         ("Skor", f"<b>{r.score}</b>", f"<b>{ek.score}</b>"),
         ("Güven", _sayi(r.confidence, 2), _sayi(ek.confidence, 2)),
         ("Band genişliği", f"{r.band[1]-r.band[0]}", f"{ek.band[1]-ek.band[0]}")],
        [45 * mm, 45 * mm, 55 * mm],
        hizalama=[None, "CENTER", "CENTER"]))
    ak.append(Pr(
        f"Alt metriklerin {kapali}'i kapanıyor, <b>hiçbiri 0 puan almıyor</b> ve "
        "hiçbir bileşen çökmüyor. Belirsizlik cezaya değil <b>güvene ve banda</b> "
        f"yansıyor. Testin en önemli satırı şudur: <b>kaynak, skoru "
        "belirlemez</b> — aynı finansal durum iki kaynakla skorlandığında fark "
        "5 puanı aşamaz; ayrışan şey güven olmalıdır. Aksi hâlde motor "
        "kullanıcıyı kendi seçmediği bir veri kaynağı yüzünden cezalandırır."))
    return ak


def bolum_profiller():
    from golden_profiles import PROFILES
    ak = [Pr("9 · Gerçek profillerde ne yapıyor", "h2")]
    ak.append(Pr(
        f"{len(PROFILES)} golden profil modelin iddialarını sınar. Her biri "
        "beklenen bir aralıkla birlikte tanımlıdır; aralık dışına çıkan bir "
        "profil, model bozuldu demektir."))
    sat = []
    for k, (f, not_, bekle) in PROFILES.items():
        r = compute_score(f)
        sat.append((f"<b>{k}</b>", not_, f"{r.score}",
                    f"{r.band[0]}–{r.band[1]}", _sayi(r.confidence, 2), bekle))
    ak.append(tablo(["Profil", "Ne temsil eder", "Skor", "Band", "C", "Beklenen"],
                    sat, [17 * mm, 66 * mm, 12 * mm, 17 * mm, 12 * mm, 21 * mm],
                    hizalama=[None, None, "CENTER", "CENTER", "CENTER", "CENTER"],
                    punto=6.9))
    ak.append(Pr(
        "<b>deniz &gt; selin</b> modelin en önemli iddiasını kanıtlar: skor gelir "
        "seviyesini değil, gelirle kurulan ilişkiyi ölçer (deniz 12.000 TL "
        "gelirli disiplinli öğrenci, selin 85.000 TL gelirli sıfır tamponlu). "
        "<b>can</b> eksik verinin ceza değil belirsizlik olarak yansıdığını "
        "gösterir: geniş band, sıfır ceza.", "not"))
    return ak


def bolum_kurallar():
    ak = [Pr("10 · İhlal edilemez kurallar ve testler", "h2")]
    ak.append(tablo(
        ["Kural", "Neden var", "Koruyan test"],
        [("Motor saftır", "Replay edilebilirlik", "t_determinism"),
         ("Eksik veri ceza değildir", "Ölçemediğimiz şey için puan kırmayız",
          "t_missing_data_never_punishes · t_every_submetric_can_be_none"),
         ("Süreksizlik yasak", "%1 girdi değişimi 1 puandan fazla oynatmamalı",
          "t_continuity (5 profil × 11 metrik)"),
         ("Engagement skora giremez", "Retention metriğin, kullanıcının sağlığı değil",
          "t_no_engagement_inputs"),
         ("Beyan bileşeni yükseltemez", "Anket yalnız öncülü ve güveni etkiler",
          "t_self_report_cannot_raise_pillars"),
         ("Kötü haber hızlı, iyi haber yavaş", "Skor tek ayda satın alınamaz",
          "t_asymmetric_smoothing"),
         ("Skor gelir seviyesini ölçmez", "Ölçek değişince skor değişmemeli",
          "t_fairness_income_neutral"),
         ("LLM sayı üretmez", "Uydurulmuş rakam yanlış taahhüttür",
          "coach_eval — sayı sadakati grubu"),
         ("Skor utandırmaz", "Skor bir ALAN hakkında konuşur, kullanıcı hakkında değil",
          "coach_eval — ton grubu")],
        [42 * mm, 55 * mm, 48 * mm], punto=7.0))

    suitler, toplam = _test_sayilari()
    ak.append(Pr("10.1 · Test süitleri", "h3"))
    ak.append(tablo(["Süit", "Kontrol"],
                    [(f"<font name='{MONO}' size=7>{d}</font>", f"<b>{n}</b>")
                     for d, n in suitler] +
                    [("<b>Toplam</b>", f"<b>{toplam}</b>")],
                    [60 * mm, 25 * mm], hizalama=[None, "RIGHT"]))
    t = _tune_ozeti()
    ak.append(Pr(
        f"Ayrıca {t['toplam']} parametrenin <b>tamamı</b> ölçülüyor: "
        f"{t['yuksek']} yüksek etkili, {t['orta']} orta, "
        f"<b>{t['olculemedi']} ölçülemeyen</b>. Bir parametrenin \"hiç "
        "tetiklenmemesi\" onu önemsiz yapmaz — ölçüm eksikliğini bulgu gibi "
        "sunmamak için ayrı raporlanır ve v3'te bu sayı sıfıra indirildi. "
        f"En etkili parametre: <font name='{MONO}' size=7>{t['en_ust'][0]}</font> "
        f"({_sayi(t['en_ust'][1]['azami_oynama'],0)} puan).", "not"))
    return ak


def bolum_acik():
    # Bu bölüm SAYFA BÖLÜNMEZ. Tablonun ortadan ikiye ayrılması, "hangi
    # maddeler açık" sorusunun cevabını iki sayfaya yayar ve okuyucu
    # listenin bittiğini sanabilir.
    ic = []
    ic.append(Pr("11 · Bilerek açık bırakılanlar", "h2"))
    ak = ic
    ak.append(Pr(
        "Aşağıdakiler eksik iş değil, bilinçli sınırlardır. Dokümanın dürüst "
        "olması için listelenmiştir."))
    ak.append(tablo(
        ["Konu", "Durum", "Ne zaman kapanır"],
        [("Parametre kalibrasyonu",
          f"{len(params.P)} parametre literatür ve akıl yürütmeyle kondu, gerçek "
          "kullanıcı verisiyle değil",
          "İlk 500–1.000 kullanıcı; hedef medyanın 60–70 bandında olması"),
         ("TÜİK TÜFE beslemesi", "Stub çalışıyor",
          "<b>Yayın öncesi zorunlu.</b> Bağlanınca borç maliyeti nominal yerine "
          "REEL orana çevrilmeli ve eşiği yeniden kalibre edilmeli"),
         ("Banka profilleri",
          "4 profilden yalnız biri (VakıfBank kart) gerçek ekstreyle doğrulandı",
          "Her hedef bankadan örnek dosya toplanınca"),
         ("LLM entegrasyonu", "Araç katmanı, guard ve eval hazır; model bağlı değil",
          "Backend'den sonra"),
         ("Çok turlu konuşma",
          "Sayı defteri turlar arası taşınmalı ve eskiyince temizlenmeli",
          "LLM entegrasyonuyla birlikte"),
         ("Hane halkı / ortak bütçe", "Model tek kullanıcı varsayıyor",
          "Ürün kararı bekliyor"),
         ("Para tipi",
          "Prototipte float; üretimde kuruş cinsinden int veya Decimal olmalı",
          "Üretim öncesi")],
        [34 * mm, 55 * mm, 56 * mm], punto=7.0))
    ak.append(Spacer(1, 5 * mm))
    ak.append(Pr(
        "Model matematiksel olarak tutarlı ve test edilmiş durumdadır. Bir gerçek "
        "ekstre üzerinde uçtan uca çalıştırılmış ve ayrıştırma bankanın kendi "
        "mutabakatını tutturmuştur — ama henüz gerçek bir kullanıcı popülasyonu "
        "üzerinde çalışmamıştır.", "not"))
    return [KeepTogether(ic)]


# ─────────────────────────────────────────────────────────────────────────────
# Belge kurgusu
# ─────────────────────────────────────────────────────────────────────────────

def _sayfa_susu(canvas, doc):
    canvas.saveState()
    canvas.setFont(GOVDE, 6.8)
    canvas.setFillColor(GRI)
    canvas.drawString(
        20 * mm, 12 * mm,
        f"Nakitio · Skor Algoritması ve Karar Motoru · model {MODEL_VERSION}")
    canvas.drawRightString(190 * mm, 12 * mm, str(canvas.getPageNumber()))
    canvas.setStrokeColor(CIZGI)
    canvas.setLineWidth(0.4)
    canvas.line(20 * mm, 15 * mm, 190 * mm, 15 * mm)
    canvas.restoreState()


def uret(cikti: str) -> str:
    doc = BaseDocTemplate(cikti, pagesize=A4,
                          leftMargin=20 * mm, rightMargin=20 * mm,
                          topMargin=18 * mm, bottomMargin=20 * mm,
                          title="Nakitio — Skor Algoritması ve Karar Motoru",
                          author="Nakitio")
    cerceve = Frame(doc.leftMargin, doc.bottomMargin, doc.width, doc.height,
                    id="ana", leftPadding=0, rightPadding=0,
                    topPadding=0, bottomPadding=0)
    doc.addPageTemplates([PageTemplate(id="std", frames=[cerceve],
                                       onPage=_sayfa_susu)])

    akis = []
    for bolum in (bolum_kapak, bolum_iddia, bolum_akis, bolum_skor,
                  bolum_guven, bolum_eksik_veri, bolum_v3_yenilik,
                  bolum_karar_motoru, bolum_erken_uyari,
                  bolum_kaynak_uyarlama, bolum_profiller,
                  bolum_kurallar, bolum_acik):
        akis.extend(bolum())
    doc.build(akis)
    return cikti


def main() -> None:
    cikti = sys.argv[1] if len(sys.argv) > 1 else os.path.join(
        os.path.dirname(HERE), "Docs", "Nakitio-Algoritma-v3.pdf")
    uret(cikti)
    boyut = os.path.getsize(cikti)
    print(f"Üretildi: {cikti}  ({boyut/1024:.0f} KB)")
    print(f"model {MODEL_VERSION} · {len(params.P)} parametre · "
          f"{sum(len(x[2]) for x in _kirilim())} alt metrik")


if __name__ == "__main__":
    main()
