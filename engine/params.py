"""
Nakitio — Skor Modeli Parametre Tablosu

Modelin AYARLANABİLİR her sayısı burada. Kodun içinde gömülü literal
kalmaz; motor bu tablodan okur.

Neden: "skorlama tablosunu ayarlayalım" demek, ~85 sayıyı tartışmak
demektir. Bunlar kodun içine dağılmışken ne tartışılabilir ne de
değiştirildiğinde ne olduğu görülebilir. Tek tabloda toplanınca
`tune.py` her birinin skora etkisini ölçebilir ve hangilerinin
gerçekten önemli olduğu görünür hâle gelir.

Kullanım:
    from params import P
    P["p1.marj.k"]

Değer değiştirdikten sonra MUTLAKA:
    python3 engine/golden_profiles.py     # skorlar nasıl kaydı
    python3 engine/test_invariants.py     # yapısal kural kırıldı mı
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Dict


@dataclass(frozen=True)
class Meta:
    label: str
    group: str
    kind: str          # weight | threshold | shape | modifier | gate
    lo: float          # duyarlılık taraması için makul alt sınır
    hi: float
    note: str = ""


# ─────────────────────────────────────────────────────────────────────────────
# Değerler
# ─────────────────────────────────────────────────────────────────────────────

P: Dict[str, float] = {

    # ── Bileşen ağırlıkları (toplam 100) ──────────────────────────────
    "p1.weight": 25.0,
    "p2.weight": 20.0,
    "p3.weight": 20.0,
    "p4.weight": 15.0,
    "p5.weight": 10.0,
    "p6.weight": 10.0,

    # ── P1 Nakit Akışı ────────────────────────────────────────────────
    "p1.marj.w": 0.560,
    "p1.istikrar.w": 0.120,
    "p1.tampon.w": 0.180,
    "p1.cesitlilik.w": 0.070,
    "p1.zamanlama.w": 0.070,
    "p1.breakeven": 20.0,          # gelir = gider noktasının puanı
    "p1.marj.k": 0.12,             # doygunluk sabiti
    "p1.marj.neg_sifir": 0.10,     # bu negatif marjda 0'a iner
    "p1.istikrar.sifir": 0.45,     # gelir CV'si burada 0 puan
    "p1.istikrar.yuz": 0.05,
    "p1.tampon.tam_gun": 45.0,
    "p1.tampon.us": 0.70,
    "p1.zamanlama.sifir": 28.0,
    "p1.zamanlama.yuz": 5.0,
    "p1.cesitlilik.sifir": 1.00,   # tek gelir kaynağı
    "p1.cesitlilik.yuz": 0.60,

    # ── P2 Borç Yükü ──────────────────────────────────────────────────
    "p2.dsr.w": 0.32,
    "p2.kart.w": 0.18,
    "p2.taahhut.w": 0.22,
    "p2.trend.w": 0.12,
    "p2.maliyet.w": 0.16,
    "p2.dsr.sifir": 0.50,
    "p2.dsr.yuz": 0.10,
    "p2.kart.sifir": 0.90,
    "p2.kart.yuz": 0.20,
    "p2.taahhut.sifir": 0.60,
    "p2.taahhut.yuz": 0.05,
    "p2.trend.sifir": 0.20,
    "p2.trend.yuz": -0.15,
    "p2.maliyet.sifir": 0.80,
    "p2.maliyet.yuz": 0.00,
    "mod.gecikme_1_29": 0.70,
    "mod.gecikme_30": 0.45,
    "mod.asgari": 0.80,
    "mod.asgari_kronik": 0.65,
    "mod.kmh": 0.85,

    # ── P3 Tasarruf & Güvence ─────────────────────────────────────────
    "p3.oran.w": 0.30,
    "p3.guvence.w": 0.31,
    "p3.sureklilik.w": 0.20,
    "p3.reel.w": 0.09,
    "p3.net_varlik.w": 0.10,
    "p3.oran.k": 0.10,
    "p3.guvence.tam_ay": 3.0,
    "p3.guvence.us": 0.60,
    "p3.net_varlik.sifir": -0.50,
    "p3.net_varlik.yuz": 1.00,
    "p3.reel.sifir": -0.25,
    "p3.reel.yuz": 0.00,

    # ── P4 Harcama Disiplini ──────────────────────────────────────────
    "p4.butce.w": 0.38,
    "p4.limit.w": 0.20,
    "p4.istege_bagli.w": 0.27,
    "p4.oynaklik.w": 0.15,
    "p4.istege_bagli.sifir": 0.60,
    "p4.istege_bagli.yuz": 0.20,
    "p4.oynaklik.sifir": 0.70,
    "p4.oynaklik.yuz": 0.15,

    # ── P5 Hedef Devamlılığı ──────────────────────────────────────────
    "p5.ontrack.w": 0.38,
    "p5.tutarlilik.w": 0.28,
    "p5.gercekcilik.w": 0.17,
    "p5.plan_uyumu.w": 0.17,
    "p5.plan_uyumu.sifir": 0.30,
    "p5.plan_uyumu.yuz": 1.00,
    "p5.gercekcilik.sifir": 1.60,
    "p5.gercekcilik.yuz": 0.80,
    "p5.hedefsiz_puan": 45.0,
    "p5.grace_gun": 60.0,

    # ── P6 Finansal Davranış ──────────────────────────────────────────
    "p6.impuls.w": 0.35,
    "p6.duygusal.w": 0.25,
    "p6.gece.w": 0.20,
    "p6.pismanlik.w": 0.20,
    "p6.impuls.sifir": 0.40,
    "p6.impuls.yuz": 0.05,
    "p6.duygusal.sifir": 0.30,
    "p6.duygusal.yuz": 0.03,
    "p6.gece.sifir": 0.35,
    "p6.gece.yuz": 0.05,
    "p6.pismanlik.sifir": 0.50,
    "p6.pismanlik.yuz": 0.05,
    "p6.min_kapsam": 0.25,

    # ── Güven (C) ─────────────────────────────────────────────────────
    "c.hist.w": 0.28,
    "c.cover.w": 0.22,
    "c.compl.w": 0.20,
    "c.verif.w": 0.12,
    "c.pillar.w": 0.18,
    "c.hist_tam_gun": 90.0,
    "c.rampa_gun": 21.0,
    "c.statement_tavan": 0.85,
    "c.manual_tavan": 0.45,
    "c.verif_varsayilan": 0.40,
    "c.integrity_carpan": 0.60,

    # ── Yumuşatma ─────────────────────────────────────────────────────
    "s.alpha": 0.35,
    "s.alpha_maddi": 0.70,
    "s.max_hareket": 8.0,
    "s.band_k": 12.0,
    "s.band_min": 2.0,

    # ── Aşama etiketi eşikleri ────────────────────────────────────────
    "stage.gecis_C": 0.30,
    "stage.saglik_C": 0.65,

    # ── Öncül skor ────────────────────────────────────────────────────
    "prior.baz": 40.0,
    "prior.min": 28.0,
    "prior.max": 75.0,

    # ── Davranış çıkarımı ─────────────────────────────────────────────
    "infer.etiket_tam": 40.0,      # bu kadar etikette çıkarım devre dışı
    "infer.cikarim_kapsam": 0.55,  # çıkarımın tek başına ürettiği kapsam
}


# ─────────────────────────────────────────────────────────────────────────────
# Açıklamalar ve tarama aralıkları
# ─────────────────────────────────────────────────────────────────────────────

M: Dict[str, Meta] = {
    "p1.weight": Meta("Nakit Akışı ağırlığı", "Bileşen", "weight", 15, 35,
                      "Gelir–gider ilişkisi ve kırılganlığı"),
    "p2.weight": Meta("Borç Yükü ağırlığı", "Bileşen", "weight", 10, 30,
                      "Mevcut ve gelecek yükümlülükler"),
    "p3.weight": Meta("Tasarruf & Güvence ağırlığı", "Bileşen", "weight", 10, 30,
                      "Kasıtlı birikim ve şoka dayanıklılık"),
    "p4.weight": Meta("Harcama Disiplini ağırlığı", "Bileşen", "weight", 5, 25,
                      "Plana uyum"),
    "p5.weight": Meta("Hedef Devamlılığı ağırlığı", "Bileşen", "weight", 5, 20,
                      "Söylediğini yapma"),
    "p6.weight": Meta("Finansal Davranış ağırlığı", "Bileşen", "weight", 5, 20,
                      "Harcamanın psikolojisi"),

    "p1.marj.w": Meta("Marj alt ağırlığı", "P1", "weight", 0.3, 0.75),
    "p1.istikrar.w": Meta("Gelir istikrarı ağırlığı", "P1", "weight", 0.05, 0.35),
    "p1.tampon.w": Meta("Likidite tamponu ağırlığı", "P1", "weight", 0.05, 0.35),
    "p1.cesitlilik.w": Meta("Gelir çeşitliliği ağırlığı", "P1", "weight", 0.0, 0.25),
    "p1.zamanlama.w": Meta("Ödeme zamanlaması ağırlığı", "P1", "weight", 0.0, 0.20,
                           "KARAR: 0,07. Aynı marjda çok farklı kırılganlık: "
                           "maaşı 1'inde gelip kartı 5'inde ödeyen taze parayla "
                           "öder, 20'sinde gelip 5'inde ödeyen bir önceki ayın "
                           "artığından. Gerçek ama ikincil bir eksen; marjın "
                           "yerine geçmez."),
    "p1.zamanlama.sifir": Meta("Taşıma süresi sıfır eşiği (gün)", "P1",
                               "threshold", 20.0, 30.0,
                               "KARAR: 28. Neredeyse tam ay taşımak."),
    "p1.zamanlama.yuz": Meta("Taşıma süresi tam puan eşiği (gün)", "P1",
                             "threshold", 0.0, 12.0,
                             "KARAR: 5. Gelirden hemen sonra ödeme."),
    "p1.breakeven": Meta("Başabaş puanı", "P1", "shape", 0, 40,
                         "Gelir=gider noktası. 0 yaparsan başabaş 'kötü' olur"),
    "p1.marj.k": Meta("Marj doygunluk sabiti", "P1", "shape", 0.06, 0.25,
                      "Küçültürsen düşük marj bile yüksek puan alır"),
    "p1.marj.neg_sifir": Meta("Negatif marj sıfır noktası", "P1", "threshold", 0.05, 0.25),
    "p1.istikrar.sifir": Meta("Gelir CV sıfır eşiği", "P1", "threshold", 0.25, 0.80),
    # KARAR (12 Ağu 2026): ağırlık 0,20 → 0,13. Gelir dalgalanması gerçek bir
    # kırılganlıktır ama buna karşı tutulan acil fon zaten P3'te ödüllendiriliyor.
    # 0,20'de aynı risk iki kez cezalandırılıyordu; serbest çalışan profili
    # (zeynep) 7 puan kaybediyordu.
    "p1.istikrar.yuz": Meta("Gelir CV tam puan eşiği", "P1", "threshold", 0.0, 0.20),
    "p1.tampon.tam_gun": Meta("Likidite tam puan (gün)", "P1", "threshold", 20, 90),
    "p1.tampon.us": Meta("Likidite eğri üssü", "P1", "shape", 0.4, 1.0),
    "p1.cesitlilik.sifir": Meta("Tek kaynak eşiği", "P1", "threshold", 0.85, 1.0),
    "p1.cesitlilik.yuz": Meta("Çeşitlilik tam puan", "P1", "threshold", 0.3, 0.8),

    "p2.dsr.w": Meta("DSR ağırlığı", "P2", "weight", 0.2, 0.6),
    "p2.kart.w": Meta("Kart kullanımı ağırlığı", "P2", "weight", 0.05, 0.4),
    "p2.taahhut.w": Meta("Taahhüt yükü ağırlığı", "P2", "weight", 0.1, 0.4),
    "p2.trend.w": Meta("Borç trendi ağırlığı", "P2", "weight", 0.05, 0.3),
    "p2.maliyet.w": Meta("Borç maliyeti ağırlığı", "P2", "weight", 0.05, 0.35,
                         "KARAR: 0,16. Borcun FİYATI, hacminden bağımsız bir "
                         "olgudur ve motor onu hiç ölçmüyordu — %0 taksitle "
                         "%60 KMH aynı puanı alıyordu. DSR (ödeyebiliyor mu) "
                         "birincil kalır; maliyet ikinci sıraya konur, çünkü "
                         "ödenemeyen ucuz borç, ödenebilen pahalı borçtan "
                         "daha risklidir."),
    "p2.dsr.sifir": Meta("DSR sıfır eşiği", "P2", "threshold", 0.35, 0.70,
                         "Bu orandan sonra borç bileşeni sıfırlanır"),
    "p2.dsr.yuz": Meta("DSR tam puan eşiği", "P2", "threshold", 0.0, 0.25),
    "p2.kart.sifir": Meta("Kart kullanımı sıfır eşiği", "P2", "threshold", 0.7, 1.0),
    "p2.maliyet.sifir": Meta("Borç maliyeti sıfır eşiği (yıllık nominal)",
                             "P2", "threshold", 0.40, 1.20,
                             "KARAR: 0,80. Yayılım şöyle olsun istendi — "
                             "%0 taksit 100, ~%30 konut/taşıt 62, ~%42 normal "
                             "tüketici kredisi 47, ~%60 kart döneri 25, %80+ "
                             "KMH/ceza 0. NOMİNAL eşiktir ve enflasyon "
                             "rejimine BAĞIMLIDIR: N5 (TÜFE) gerçek veriyle "
                             "beslendiğinde metrik reel orana çevrilmeli ve "
                             "bu eşik yeniden kalibre edilmelidir."),
    "p2.maliyet.yuz": Meta("Borç maliyeti tam puan eşiği", "P2", "threshold",
                           0.0, 0.25,
                           "KARAR: 0,00. Faizsiz borç bir yük değildir; "
                           "taksitin kendisi P2'nin taahhüt alt metriğinde "
                           "zaten ölçülüyor, burada ikinci kez sayılmaz."),
    "p2.kart.yuz": Meta("Kart kullanımı tam puan", "P2", "threshold", 0.05, 0.4),
    "p2.taahhut.sifir": Meta("Taahhüt/yıllık gelir sıfır", "P2", "threshold", 0.35, 1.0),
    "p2.taahhut.yuz": Meta("Taahhüt tam puan", "P2", "threshold", 0.0, 0.2),
    "p2.trend.sifir": Meta("Borç artışı sıfır eşiği", "P2", "threshold", 0.08, 0.4),
    "p2.trend.yuz": Meta("Borç azalışı tam puan", "P2", "threshold", -0.35, -0.05),
    "mod.gecikme_1_29": Meta("Gecikme 1–29 gün çarpanı", "P2 ceza", "modifier", 0.4, 0.95),
    "mod.gecikme_30": Meta("Gecikme 30+ gün çarpanı", "P2 ceza", "modifier", 0.2, 0.8),
    "mod.asgari": Meta("Sadece asgari ödeme çarpanı", "P2 ceza", "modifier", 0.55, 0.95),
    "mod.asgari_kronik": Meta("Kronik asgari ödeme çarpanı", "P2 ceza", "modifier", 0.35, 0.9),
    "mod.kmh": Meta("KMH kullanımı çarpanı", "P2 ceza", "modifier", 0.6, 1.0),

    "p3.oran.w": Meta("Tasarruf oranı ağırlığı", "P3", "weight", 0.15, 0.55),
    "p3.guvence.w": Meta("Acil fon ağırlığı", "P3", "weight", 0.15, 0.55),
    "p3.sureklilik.w": Meta("Süreklilik ağırlığı", "P3", "weight", 0.05, 0.4),
    "p3.reel.w": Meta("Enflasyon koruması ağırlığı", "P3", "weight", 0.0, 0.25),
    "p3.net_varlik.w": Meta("Net varlık ağırlığı", "P3", "weight", 0.0, 0.30,
                            "KARAR: 0,10. DECISIONS §6'nın v2.1'e ertelediği "
                            "boyut, bileşen eklemeden. Ağırlık DÜŞÜK çünkü "
                            "`tampon` ve `guvence` ile kısmen örtüşüyor; "
                            "ayırt ettiği şey net POZİSYON (3 aylık fonu olup "
                            "200k borcu olan kullanıcı)."),
    "p3.net_varlik.sifir": Meta("Net varlık sıfır eşiği (yıllık gelir katı)",
                                "P3", "threshold", -1.5, 0.0,
                                "KARAR: -0,50. Sıfır net varlık NÖTRdür (33 "
                                "puan), ceza değil: borcu da varlığı da olmayan "
                                "genç kullanıcı cezalandırılmamalı. Ceza yalnız "
                                "net BORÇLU olmaya başlar."),
    "p3.net_varlik.yuz": Meta("Net varlık tam puan eşiği", "P3", "threshold",
                              0.5, 3.0, "KARAR: 1,00 yıllık gelir."),
    "p3.oran.k": Meta("Tasarruf doygunluk sabiti", "P3", "shape", 0.05, 0.22,
                      "0,10 → %10 tasarruf 63 puan, %20 → 86"),
    "p3.guvence.tam_ay": Meta("Acil fon hedefi (ay)", "P3", "threshold", 3, 12,
                              "KARAR: 6 → 3. Kullanıcıya GÖSTERİLEN hedefle SKORUN "
                              "hedefi aynı olmalı; aksi hâlde gösterilen hedefe ulaşan "
                              "kullanıcı tam puan alamaz ve kale direği kaymış olur. "
                              "6 ay skorun dışında bir ileri seviye rozeti olarak kalır."),
    "p3.guvence.us": Meta("Acil fon eğri üssü", "P3", "shape", 0.35, 1.0,
                          "Düşürürsen ilk ay daha çok ödüllenir"),
    "p3.reel.sifir": Meta("Enflasyon farkı sıfır", "P3", "threshold", -0.5, -0.1),
    "p3.reel.yuz": Meta("Enflasyon farkı tam puan", "P3", "threshold", -0.05, 0.1),

    "p4.butce.w": Meta("Bütçe uyumu ağırlığı", "P4", "weight", 0.2, 0.6),
    "p4.limit.w": Meta("Limit uyumu ağırlığı", "P4", "weight", 0.05, 0.4),
    "p4.istege_bagli.w": Meta("İsteğe bağlı pay ağırlığı", "P4", "weight", 0.1, 0.45),
    "p4.oynaklik.w": Meta("Kategori oynaklığı ağırlığı", "P4", "weight", 0.0, 0.3),
    "p4.istege_bagli.sifir": Meta("İsteğe bağlı pay sıfır eşiği", "P4", "threshold", 0.4, 0.8),
    "p4.istege_bagli.yuz": Meta("İsteğe bağlı pay tam puan", "P4", "threshold", 0.1, 0.35),
    "p4.oynaklik.sifir": Meta("Oynaklık sıfır eşiği", "P4", "threshold", 0.4, 1.0),
    "p4.oynaklik.yuz": Meta("Oynaklık tam puan", "P4", "threshold", 0.05, 0.3),

    "p5.ontrack.w": Meta("Hedef ilerlemesi ağırlığı", "P5", "weight", 0.25, 0.65),
    "p5.tutarlilik.w": Meta("Katkı sürekliliği ağırlığı", "P5", "weight", 0.15, 0.55),
    "p5.gercekcilik.w": Meta("Hedef gerçekçiliği ağırlığı", "P5", "weight", 0.0, 0.4),
    "p5.plan_uyumu.w": Meta("Plana uyum ağırlığı", "P5", "weight", 0.0, 0.35,
                            "KARAR: 0,17. `ontrack` hedefe YAKLAŞMAYI ölçer, "
                            "bu SÖZE UYMAYI. İkisi ayrışır: fazla iyimser hedef "
                            "koymuş biri plana harfiyen uysa da geride görünür. "
                            "P5'in adı zaten 'söylediğini yapma'."),
    "p5.plan_uyumu.sifir": Meta("Plana uyum sıfır eşiği", "P5", "threshold",
                                0.0, 0.60, "KARAR: 0,30. Planın üçte birinden "
                                "azı gerçekleştiyse plan yaşamıyor demektir."),
    "p5.plan_uyumu.yuz": Meta("Plana uyum tam puan eşiği", "P5", "threshold",
                              0.85, 1.30, "KARAR: 1,00. Planı AŞMAK ek puan "
                              "getirmez; fazla katkı zaten `ontrack`ta görünür."),
    "p5.gercekcilik.sifir": Meta("Gerçekçilik sıfır eşiği", "P5", "threshold", 1.2, 2.5),
    "p5.gercekcilik.yuz": Meta("Gerçekçilik tam puan", "P5", "threshold", 0.5, 1.0),
    "p5.hedefsiz_puan": Meta("Hedefsizlik puanı", "P5", "gate", 0, 70,
                             "60 gün sonra hedef yoksa verilen nötr puan"),
    "p5.grace_gun": Meta("Hedefsizlik muafiyeti (gün)", "P5", "gate", 14, 120),

    "p6.impuls.w": Meta("Plansızlık ağırlığı", "P6", "weight", 0.2, 0.55),
    "p6.duygusal.w": Meta("Duygusal pay ağırlığı", "P6", "weight", 0.1, 0.45),
    "p6.gece.w": Meta("Gece yoğunlaşması ağırlığı", "P6", "weight", 0.0, 0.4),
    "p6.pismanlik.w": Meta("Pişmanlık ağırlığı", "P6", "weight", 0.05, 0.4),
    "p6.impuls.sifir": Meta("Plansızlık sıfır eşiği", "P6", "threshold", 0.25, 0.65),
    "p6.impuls.yuz": Meta("Plansızlık tam puan", "P6", "threshold", 0.0, 0.2),
    "p6.duygusal.sifir": Meta("Duygusal pay sıfır eşiği", "P6", "threshold", 0.18, 0.5),
    "p6.duygusal.yuz": Meta("Duygusal pay tam puan", "P6", "threshold", 0.0, 0.12),
    "p6.gece.sifir": Meta("Gece payı sıfır eşiği", "P6", "threshold", 0.2, 0.55),
    "p6.gece.yuz": Meta("Gece payı tam puan", "P6", "threshold", 0.0, 0.18),
    "p6.pismanlik.sifir": Meta("Pişmanlık sıfır eşiği", "P6", "threshold", 0.3, 0.75),
    "p6.pismanlik.yuz": Meta("Pişmanlık tam puan", "P6", "threshold", 0.0, 0.2),
    "p6.min_kapsam": Meta("Davranış min. kapsam", "P6", "gate", 0.1, 0.5,
                          "Altındaysa bileşen devre dışı"),

    "c.hist.w": Meta("Geçmiş uzunluğu ağırlığı", "Güven", "weight", 0.1, 0.5),
    "c.cover.w": Meta("Kaynak kapsamı ağırlığı", "Güven", "weight", 0.1, 0.45),
    "c.compl.w": Meta("Kategorizasyon ağırlığı", "Güven", "weight", 0.05, 0.4),
    "c.verif.w": Meta("Gelir doğrulama ağırlığı", "Güven", "weight", 0.0, 0.3),
    "c.pillar.w": Meta("Bileşen + alt metrik kapsamı", "Güven", "weight", 0.05, 0.35),
    "c.hist_tam_gun": Meta("Tam geçmiş (gün)", "Güven", "threshold", 45, 180),
    "c.rampa_gun": Meta("İlk rampa (gün)", "Güven", "gate", 7, 45),
    "c.statement_tavan": Meta("Ekstre kaynağı tavanı", "Güven", "threshold", 0.6, 1.0,
                              "Ekstre yüklemenin ulaşabileceği en yüksek kapsam"),
    "c.manual_tavan": Meta("Manuel giriş tavanı", "Güven", "threshold", 0.2, 0.7),
    "c.verif_varsayilan": Meta("Doğrulama yoksa varsayılan", "Güven", "threshold", 0.1, 0.7),
    "c.integrity_carpan": Meta("Bütünlük şüphesi çarpanı", "Güven", "modifier", 0.3, 0.9),

    "s.alpha": Meta("EWMA alfa (normal)", "Yumuşatma", "shape", 0.15, 0.7,
                    "Yükseltirsen skor daha hızlı tepki verir"),
    "s.alpha_maddi": Meta("EWMA alfa (maddi olay)", "Yumuşatma", "shape", 0.4, 1.0),
    "s.max_hareket": Meta("Aylık azami hareket", "Yumuşatma", "gate", 3, 20),
    "s.band_k": Meta("Belirsizlik bandı katsayısı", "Yumuşatma", "shape", 6, 20),
    "s.band_min": Meta("Bandın en dar hâli", "Yumuşatma", "gate", 0, 6),

    "stage.gecis_C": Meta("Geçiş Skoru eşiği", "Aşama", "gate", 0.15, 0.5),
    "stage.saglik_C": Meta("Finansal Sağlık eşiği", "Aşama", "gate", 0.45, 0.85,
                           "Aynı zamanda 'bant olarak sun' eşiği"),

    "prior.baz": Meta("Onboarding baz puanı", "Öncül", "shape", 40, 60,
                      "KARAR: 50 → 40. Ölçmediğimiz bir şey hakkında iyimser "
                      "iddiada bulunmuyoruz; düşük başlangıç ekstre yüklemeyi teşvik eder"),
    "prior.min": Meta("Öncül alt sınırı", "Öncül", "gate", 25, 50,
                      "KARAR: 40 → 28. 40 tabanında 'zayıf' ve 'kötü' anket "
                      "cevapları AYNI skoru alıyordu (ham 29 ve 10, ikisi de 40'a "
                      "kelepçeleniyordu). 28 ayrımı geri getirir."),
    "prior.max": Meta("Öncül üst sınırı", "Öncül", "gate", 60, 85),

    "infer.etiket_tam": Meta("Etiketin tam ağırlık sayısı", "Çıkarım", "gate", 15, 100),
    "infer.cikarim_kapsam": Meta("Çıkarımın ürettiği kapsam", "Çıkarım", "gate", 0.3, 0.8),
}


def check() -> None:
    """Tabloyu doğrular. Import sırasında çalışır."""
    missing = set(P) - set(M)
    if missing:
        raise ValueError(f"açıklaması olmayan parametre: {sorted(missing)}")
    extra = set(M) - set(P)
    if extra:
        raise ValueError(f"değeri olmayan açıklama: {sorted(extra)}")

    total = sum(P[f"p{i}.weight"] for i in range(1, 7))
    if abs(total - 100.0) > 1e-9:
        raise ValueError(f"bileşen ağırlıkları 100 etmiyor: {total}")

    for grup, anahtarlar in (
        ("P1", ["p1.marj.w", "p1.istikrar.w", "p1.tampon.w", "p1.cesitlilik.w",
                "p1.zamanlama.w"]),
        ("P2", ["p2.dsr.w", "p2.kart.w", "p2.taahhut.w", "p2.trend.w",
                "p2.maliyet.w"]),
        ("P3", ["p3.oran.w", "p3.guvence.w", "p3.sureklilik.w", "p3.reel.w",
                "p3.net_varlik.w"]),
        ("P4", ["p4.butce.w", "p4.limit.w", "p4.istege_bagli.w", "p4.oynaklik.w"]),
        ("P5", ["p5.ontrack.w", "p5.tutarlilik.w", "p5.gercekcilik.w",
                "p5.plan_uyumu.w"]),
        ("P6", ["p6.impuls.w", "p6.duygusal.w", "p6.gece.w", "p6.pismanlik.w"]),
        ("Güven", ["c.hist.w", "c.cover.w", "c.compl.w", "c.verif.w", "c.pillar.w"]),
    ):
        s = sum(P[k] for k in anahtarlar)
        if abs(s - 1.0) > 1e-9:
            raise ValueError(f"{grup} alt ağırlıkları 1,0 etmiyor: {s:.4f}")


check()
