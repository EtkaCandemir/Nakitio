/* Nakitio prototip arayüzü.
   Tüm sayılar sunucudan gelir; burada hiçbir finansal hesap yapılmaz. */

const $ = (s, r = document) => r.querySelector(s);
const el = (h) => { const d = document.createElement('div'); d.innerHTML = h.trim(); return d.firstElementChild; };
const esc = (s) => String(s ?? '').replace(/[&<>"]/g, c => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;' }[c]));

let B = null;            // bundle
let TAB = 'home';
let TRIAGE_I = 0;

async function api(path, opts) {
  const r = await fetch(path, opts);
  const j = await r.json();
  if (j.hata) { toast('Sunucu hatası'); console.error(j.hata); throw new Error(j.hata); }
  return j;
}

function toast(msg, ms = 2200) {
  const t = $('#toast'); t.textContent = msg; t.hidden = false;
  clearTimeout(toast._t); toast._t = setTimeout(() => t.hidden = true, ms);
}

/* ── ortak parçalar ─────────────────────────────────────────────────── */

function scoreCard(k) {
  const seviye = k.seviye_goster
    ? `<div class="chip">✓ ${esc(k.seviye)}</div>` : '';
  const degisim = (k.degisim != null && k.degisim !== 0)
    ? `<span>Geçen döneme göre ${k.degisim > 0 ? '+' : ''}${k.degisim} puan</span>` : '';
  return `<div class="score">
    <div class="lbl">${esc(k.gun0_ust || k.baslik)}</div>
    <div class="big">${esc(k.goster)}<small>/100</small></div>
    ${seviye}
    ${k.gun0_alt ? `<div class="note">${esc(k.gun0_alt)}</div>` : ''}
    ${k.alt_not ? `<div class="note">${esc(k.alt_not)}</div>` : ''}
    <div class="meta"><span>${k.guven_notu ? esc(k.guven_notu) : 'Veri yeterliliği: ' + esc(k.guven_etiketi)}</span>${degisim}</div>
  </div>`;
}

function barClass(p) { return p >= 75 ? 'g' : p >= 50 ? 'a' : 'r'; }

/* ── ANA SAYFA ──────────────────────────────────────────────────────── */

function viewHome() {
  const h = B.ana_sayfa, d = h.donem, o = h.kapanan_ozet, ong = B.devam_eden_islemler;
  let out = scoreCard(h.skor_karti);

  if (o && d) {
    out += `<div class="card">
      <div class="zone-head"><b>Kapanan dönem</b><span>${esc(d.kapanan.etiket)}</span></div>
      <div class="tiny muted">${esc(d.kapanan.kaynak_notu)}</div>
      <div class="trio">
        <div><div class="k">Gelir</div><div class="v">${esc(o.gelir)}</div></div>
        <div><div class="k">Gider</div><div class="v">${esc(o.gider)}</div></div>
        <div><div class="k">Korunan</div><div class="v" style="color:var(--${o.korunan_ham >= 0 ? 'yesil' : 'kirmizi'})">${esc(o.korunan)}</div></div>
      </div>
      <div class="row" style="margin-top:12px">
        <span class="tiny muted">Tasarruf oranı</span>
        <span class="tag m">${esc(o.tasarruf_orani)}</span>
      </div>
      <div class="row" style="margin-top:7px">
        <span class="tiny muted">Acil durum fonu</span>
        <span class="tag ${o.acil_fon_ay >= 3 ? 'g' : o.acil_fon_ay >= 1 ? 'a' : 'r'}">${String(o.acil_fon_ay).replace('.', ',')} ay</span>
      </div>
    </div>`;

    out += `<div class="card partial">
      <div class="zone-head"><b>Devam eden dönem</b><span>${esc(d.devam_eden.etiket)}</span></div>
      <div class="tiny muted">${esc(d.devam_eden.uyari)}</div>
      ${ong.adet ? `<div class="row" style="margin-top:11px">
          <span class="tiny">${ong.adet} işlem</span><b>${esc(ong.toplam)}</b></div>`
      : `<div class="tiny muted" style="margin-top:9px">Henüz işlem eklemedin.</div>`}
      <button class="cta ghost sm" onclick="openAdd()">+ İşlem Ekle</button>
    </div>`;
  }

  if (h.guvence) {
    const g = h.guvence;
    out += `<div class="card">
      <div class="row"><b>${esc(g.baslik)}</b>
        <span class="tag ${g.mevcut_ay >= 3 ? 'g' : g.mevcut_ay >= 1 ? 'a' : 'r'}">${String(g.mevcut_ay).replace('.', ',')} ay</span></div>
      <div class="tiny muted" style="margin-top:4px">${esc(g.durum_metni)}</div>
      ${g.kademeler.map(k => `
        <div style="margin-top:13px;opacity:${k.no === 1 || k.tamamlandi ? 1 : .55}">
          <div class="row">
            <span style="font-size:13px;font-weight:600">
              ${k.tamamlandi ? '✓ ' : ''}${esc(k.ad)}
              <span class="muted" style="font-weight:400">· ${k.ay} ay</span>
            </span>
            <span class="tiny"><b>${esc(k.hedef_tutar)}</b></span>
          </div>
          <div class="bar ${k.tamamlandi ? 'g' : k.no === 1 ? '' : 'a'}" style="margin-top:6px">
            <i style="width:${k.ilerleme_yuzde}%"></i></div>
          <div class="row tiny muted" style="margin-top:5px">
            <span>${esc(k.alt)}</span><span>kalan ${esc(k.kalan)}</span></div>
        </div>`).join('')}
      ${g.tahmini_sure_metni ? `<div class="tiny muted" style="margin-top:12px">📈 ${esc(g.tahmini_sure_metni)}</div>` : ''}
      <div class="tiny muted" style="margin-top:7px">ℹ️ ${esc(g.neden_3_ay)}</div>
    </div>`;
  }

  if (h.kapsam && h.kapsam.uyari) {
    out += `<div class="alert"><span>⚠️</span><div>${esc(h.kapsam.uyari)}
      <button class="cta sm" onclick="openUpload()">Ekstre Yükle</button></div></div>`;
  }

  if (h.farkindalik) {
    out += `<div class="insight"><span>💡</span><div><b>Bugünün farkındalığı</b><br>${esc(h.farkindalik.metin)}</div></div>`;
  }

  const pa = h.birincil_eylem;
  if (pa && pa.tip !== 'ekstre_yukle') {
    out += `<div class="card"><div class="row"><div>
      <b>${esc(pa.baslik)}</b><div class="tiny muted" style="margin-top:3px">${esc(pa.alt)}</div>
      </div></div><button class="cta" onclick="go('plan')">${esc(pa.cta)}</button></div>`;
  }

  if (!o) {
    out += `<div class="card empty"><div class="ico">📄</div>
      <h3>${esc(pa.baslik)}</h3><p>${esc(pa.alt)}</p>
      <button class="cta" onclick="openUpload()">${esc(pa.cta)}</button>
      ${pa.ikincil ? `<div class="tiny muted" style="margin-top:11px">${esc(pa.ikincil)}</div>` : ''}
      </div>`;
  }

  if (B.triyaj.kartlar.length) {
    out += `<div class="card"><div class="row"><div>
      <b>${esc(B.triyaj.baslik)}</b>
      <div class="tiny muted" style="margin-top:3px">${B.triyaj.kartlar.length} işlem bekliyor · ${B.etiket_sayisi} etiket verildi</div>
      </div></div><button class="cta ghost" onclick="openTriage()">Başla</button></div>`;
  }

  // Kategori triyajı AYRI bir kart. İmpuls triyajıyla birleştirilmemeli:
  // biri işleme sorulur ("plansız mıydı"), diğeri işyerine ("ne satıyor").
  // Kullanıcı iki farklı iş yaptığını görmeli.
  const kt = B.kategori_triyaji;
  if (kt && kt.kartlar && kt.kartlar.length) {
    const toplam = kt.kartlar.reduce((a, k) => a + k.adet, 0);
    out += `<div class="card"><div class="row"><div>
      <b>${esc(kt.baslik)}</b>
      <div class="tiny muted" style="margin-top:3px">${kt.kartlar.length} işyeri · ${toplam} harcamayı birden düzeltir</div>
      </div></div><button class="cta ghost" onclick="openCatTriage()">Başla</button></div>`;
  }
  return out;
}

/* ── ANALİZ ─────────────────────────────────────────────────────────── */

function viewAnalysis() {
  const r = B.skor_raporu, a = B.analiz;
  let out = `<div class="card">
    <div class="row"><b>Skor Kırılımı</b><span class="tag m">${esc(r.veri_yeterliligi)} veri</span></div>
    <div class="tiny muted" style="margin-top:3px">${esc(r.hesaplama_notu)}</div>
    <div style="margin-top:10px">`;
  for (const p of r.bilesenler) {
    if (p.durum === 'devre dışı') {
      out += `<div class="pillar"><div class="nm">${esc(p.bilesen)}
        <div class="tiny muted">${esc(p.neden)}</div></div><span class="tag a">ölçülemedi</span></div>`;
      continue;
    }
    out += `<div class="pillar"><div style="flex:1">
      <div class="row"><span class="nm">${esc(p.bilesen)}</span>
        <span class="pt">${String(p.puan).replace('.', ',')}<span class="muted">/${String(p.azami).replace('.', ',')}</span></span></div>
      <div class="bar ${barClass(p.yuzde)}"><i style="width:${p.yuzde}%"></i></div>
    </div></div>`;
  }
  out += `</div></div>`;

  if (a.davranis) {
    const dv = a.davranis;
    out += `<h2 class="sec">Davranış</h2><div class="card">`;
    if (!dv.iddia_edilebilir) {
      out += `<div class="alert" style="margin:-2px 0 12px"><span>❓</span><div>
        Bu değerler <b>çıkarımdır</b>, ölçüm değil. Triyajı tamamladıkça kesinleşir.
        <button class="cta sm" onclick="openTriage()">Doğrula</button></div></div>`;
    }
    const rows = [['Plansız harcama', dv.plansiz_oran], ['Duygusal harcama', dv.duygusal_pay],
    ['Pişmanlık', dv.pismanlik], ['Gece yoğunlaşması', dv.gece_yogunlasmasi]];
    for (const [k, v] of rows) {
      if (v == null) continue;
      out += `<div class="li"><span class="nm">${esc(k)}</span><span class="v">${esc(v)}</span></div>`;
    }
    if (dv.gece_olculemedi_notu)
      out += `<div class="tiny muted" style="margin-top:9px">ℹ️ ${esc(dv.gece_olculemedi_notu)}</div>`;
    out += `<div class="tiny muted" style="margin-top:9px">${dv.etiket_sayisi} etiket · çıkarım ağırlığı ${(1 - dv.etiket_agirligi).toFixed(2).replace('.', ',')}</div></div>`;
  }

  if (a.kategoriler) {
    out += `<h2 class="sec">Kategoriler</h2><div class="card">`;
    for (const c of a.kategoriler) {
      const rd = c.reel_degisim_yuzde;
      const t = rd == null ? '' :
        `<span class="tag ${rd > 8 ? 'r' : rd > 0 ? 'a' : 'g'}">${rd > 0 ? '+' : ''}${String(rd).replace('.', ',')}% reel</span>`;
      out += `<div class="li"><span class="nm">${esc(c.kategori)}
        ${c.nominal_degisim_yuzde != null ? `<small>nominal ${c.nominal_degisim_yuzde > 0 ? '+' : ''}${String(c.nominal_degisim_yuzde).replace('.', ',')}%</small>` : ''}
        </span>${t}<span class="v">₺${c.tutar.toLocaleString('tr-TR')}</span></div>`;
    }
    out += `</div>`;
  }

  if (a.riskler && a.riskler.length) {
    out += `<h2 class="sec">Riskler</h2><div class="card">`;
    for (const k of a.riskler) {
      const cls = k.seviye === 'yuksek' ? 'r' : k.seviye === 'orta' ? 'a' : 'g';
      out += `<div class="li"><span class="nm">${esc(k.aciklama)}</span>
        <span class="tag ${cls}">${k.seviye === 'yuksek' ? 'Yüksek' : k.seviye === 'orta' ? 'Orta' : 'Düşük'}</span></div>`;
    }
    out += `</div>`;
  }

  const b = a.borc;
  out += `<h2 class="sec">Borç</h2><div class="card">
    <div class="li"><span class="nm">Toplam anapara</span><span class="v">${esc(b.anapara)}</span></div>
    <div class="li"><span class="nm">Borç ödeme oranı (DSR)</span><span class="v">${esc(b.dsr)}</span></div>
    <div class="li"><span class="nm">Aylık taksit</span><span class="v">${esc(b.taksit_aylik)}</span></div>
    <div class="li"><span class="nm">Kalan taksit taahhüdü</span><span class="v">${esc(b.taksit_kalan)}</span></div>
    ${b.kart_kullanimi ? `<div class="li"><span class="nm">Kart kullanım oranı</span><span class="v">${esc(b.kart_kullanimi)}</span></div>` : ''}
  </div>`;
  return out;
}

/* ── PLANLAR ────────────────────────────────────────────────────────── */

function viewPlan() {
  const p = B.plan, g = B.hedefler;
  let out = '';
  if (p.adimlar.length) {
    out += `<div class="card">
      <b>AI Aksiyon Planı</b>
      <div class="tiny muted" style="margin-top:3px">${p.ufuk_ay} aylık projeksiyon — taahhüt değil</div>
      <div class="row" style="margin-top:14px;align-items:center">
        <div style="text-align:center;flex:1"><div class="tiny muted">Şu an</div>
          <div style="font-size:26px;font-weight:800">${p.skor_simdi}</div></div>
        <div style="font-size:20px;color:var(--soluk)">→</div>
        <div style="text-align:center;flex:1"><div class="tiny muted">Plan sonrası</div>
          <div style="font-size:26px;font-weight:800;color:var(--yesil)">${p.skor_plan_sonrasi}</div></div>
      </div></div>`;
    out += `<div class="card">`;
    p.adimlar.forEach((a, i) => {
      out += `<div class="li"><span class="nm"><b>${i + 1}. ${esc(a.aksiyon)}</b>
        <small>zorluk ${'●'.repeat(a.zorluk)}${'○'.repeat(3 - a.zorluk)}</small></span>
        <span class="tag ${a.ek_etki > 0 ? 'g' : 'm'}">${a.ek_etki > 0 ? '+' : ''}${a.ek_etki} puan</span></div>`;
    });
    out += `<div class="tiny muted" style="margin-top:10px">${esc(p.sunum_uyarisi)}</div></div>`;
  }
  if (g.hedefler && g.hedefler.length) {
    out += `<h2 class="sec">Hedefler</h2><div class="card">`;
    for (const h of g.hedefler) {
      const pctNum = parseFloat(String(h.ilerleme).replace('%', '').replace(',', '.'));
      out += `<div style="padding:11px 0;border-bottom:1px solid var(--cizgi)">
        <div class="row"><b style="font-size:13.5px">${esc(h.ad)}</b>
          <span class="tag ${h.durumda_mi ? 'g' : 'a'}">${h.durumda_mi ? 'Yolunda' : 'Geride'}</span></div>
        <div class="bar ${h.durumda_mi ? 'g' : 'a'}" style="margin-top:8px"><i style="width:${Math.min(100, pctNum)}%"></i></div>
        <div class="row tiny muted" style="margin-top:6px">
          <span>${esc(h.mevcut)} / ${esc(h.hedef)}</span><span>${h.kalan_ay} ay kaldı</span></div>
      </div>`;
    }
    out += `</div>`;
  }
  if (!out) out = `<div class="card empty"><div class="ico">🎯</div><h3>Henüz plan yok</h3>
    <p>Ekstre yükledikçe sana özel aksiyon planı oluşur.</p></div>`;
  return out;
}

/* ── KOÇ ────────────────────────────────────────────────────────────── */

function viewCoach() {
  return `<div class="card">
      <b>Nakitio AI Koçu</b>
      <div class="tiny muted" style="margin:3px 0 12px">Sayılar motordan gelir, modelden değil.</div>
      <div class="qchips">
        <button onclick="ask('durum')">Bu ay durumum nasıl?</button>
        <button onclick="ask('tasarruf')">Tasarrufumu nasıl artırırım?</button>
        <button onclick="ask('risk')">Nelere dikkat etmeliyim?</button>
        <button onclick="ask('kategori')">Harcamalarım nerede arttı?</button>
        <button onclick="ask('yatirim')">Paramı nereye yatırmalıyım?</button>
      </div></div>
    <div id="coachOut"></div>`;
}

async function ask(q) {
  const box = $('#coachOut');
  box.innerHTML = `<div class="card"><div class="muted tiny">Hesaplanıyor…</div></div>`;
  const r = await api('/api/coach?q=' + q);
  const v = r.dogrulama;
  box.innerHTML = `
    <div class="card"><div class="tiny muted" style="margin-bottom:8px">${esc(r.soru)}</div>
      <div class="bubble">${esc(r.yanit)}</div>
      <div class="tiny muted" style="margin-top:9px">Çağrılan araçlar: ${r.araclar.map(esc).join(' · ')}</div>
      <div class="verify ${v.gecti ? 'ok' : 'no'}">
        <b>${v.gecti ? '✓ Doğrulama geçti' : '✕ Doğrulama reddetti'}</b><br>${esc(v.ozet)}
      </div>
      <div class="ledger">${r.defter.map(esc).join('<br>')}</div>
      <div class="tiny muted" style="margin-top:9px">ℹ️ ${esc(r.not)}</div>
    </div>`;
}

/* ── TRİYAJ ─────────────────────────────────────────────────────────── */

function openTriage() {
  TRIAGE_I = 0;
  if (!B.triyaj.kartlar.length) { toast('Şu an sorulacak işlem yok'); return; }
  renderTriage();
}

function renderTriage() {
  const k = B.triyaj.kartlar[TRIAGE_I];
  if (!k) { closeSheet(); toast('Triyaj tamamlandı — davranış analizin güncellendi'); return; }
  sheet(`
    <h3>${esc(B.triyaj.baslik)}</h3>
    <div class="sub">${esc(B.triyaj.alt)}</div>
    <div class="triage-card">
      <div class="row"><span class="amt">₺${k.tutar.toLocaleString('tr-TR')}</span>
        <span class="tag m">${esc(k.kategori)}</span></div>
      <div class="tiny muted" style="margin-top:4px">${esc(k.merchant)} · ${esc(k.tarih)}</div>
      <div class="why">🔍 ${esc(k.neden)}</div>
      <div class="tbtns">
        <button class="no" onclick="answer('${k.txn_id}',false)">Plansızdı</button>
        <button class="yes" onclick="answer('${k.txn_id}',true)">Planlıydı</button>
      </div>
    </div>
    <div class="row tiny muted" style="margin-top:12px">
      <span>${TRIAGE_I + 1} / ${B.triyaj.kartlar.length}</span>
      <button class="qchips" style="border:0;background:none;color:var(--mor);font-weight:700;cursor:pointer"
        onclick="closeSheet()">Atla</button>
    </div>`);
}

async function answer(id, planned) {
  const before = B.ana_sayfa.skor_karti.skor;
  B = await api('/api/triage', {
    method: 'POST', headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ txn_id: id, planned })
  });
  const after = B.ana_sayfa.skor_karti.skor;
  if (after !== before) toast(`Skor ${before} → ${after}`);
  TRIAGE_I++;
  renderTriage();
  render();
}

/* ── KATEGORİ TRİYAJI ───────────────────────────────────────────────── */
//
// İmpuls triyajından AYRI tutulur ve ayrı olması yapısal bir gerekliliktir:
// impuls sorusu işleme sorulur (aynı marketten iki alışverişten biri
// plansız olabilir), kategori sorusu işyerine sorulur (bir işyeri ne
// satıyorsa onu satar). Cevap o işyerinin TÜM işlemlerine yayıldığı için
// her kartta kaç harcamayı düzelttiği yazar — kullanıcı ne kazandığını
// görmeli, yoksa soruyu cevaplamak için sebebi olmaz.

let CAT_I = 0;

function openCatTriage() {
  CAT_I = 0;
  const kt = B.kategori_triyaji;
  if (!kt || !kt.kartlar.length) { toast(kt ? kt.bos_mesaji : 'Sorulacak bir şey yok'); return; }
  renderCatTriage();
}

function renderCatTriage() {
  const kt = B.kategori_triyaji;
  const k = kt.kartlar[CAT_I];
  if (!k) { closeSheet(); toast('Teşekkürler — harcama analizin netleşti'); return; }
  const secenekler = kt.secenekler.map(c =>
    `<button onclick="answerCat('${esc(k.merchant_id)}','${esc(c.anahtar)}')">${esc(c.etiket)}</button>`
  ).join('');
  sheet(`
    <h3>${esc(kt.baslik)}</h3>
    <div class="sub">${esc(kt.alt)}</div>
    <div class="triage-card">
      <div class="row"><span class="amt">${esc(k.tutar)}</span>
        <span class="tag m">${k.adet} harcama</span></div>
      <div class="tiny muted" style="margin-top:4px">${esc(k.isyeri)}</div>
      <div class="why">🔍 ${esc(k.neden)}</div>
      <div class="why" style="color:var(--mor-2)">↩︎ ${esc(k.kapsam)} — ${esc(kt.kapsam_notu)}</div>
    </div>
    <div class="tiny muted" style="margin:12px 0 7px">Ne satıyor?</div>
    <div class="qchips">${secenekler}</div>
    <div class="row tiny muted" style="margin-top:12px">
      <span>${CAT_I + 1} / ${kt.kartlar.length}</span>
      <button class="qchips" style="border:0;background:none;color:var(--mor);font-weight:700;cursor:pointer"
        onclick="closeSheet()">${esc(kt.atla_etiketi)}</button>
    </div>`);
}

async function answerCat(merchantId, kategori) {
  const oncekiSkor = B.ana_sayfa.skor_karti.skor;
  const oncekiKart = B.kategori_triyaji.kartlar.length;
  B = await api('/api/kategori', {
    method: 'POST', headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ merchant_id: merchantId, kategori })
  });
  const sonraSkor = B.ana_sayfa.skor_karti.skor;
  if (sonraSkor !== oncekiSkor) toast(`Skor ${oncekiSkor} → ${sonraSkor}`);

  // Cevaplanan işyeri listeden düştüğü için indeks İLERLETİLMEZ —
  // aksi hâlde her cevapta bir kart atlanır. Liste kısalmadıysa
  // (beklenmedik durum) ilerlet ki döngüye girilmesin.
  if (B.kategori_triyaji.kartlar.length >= oncekiKart) CAT_I++;
  renderCatTriage();
  render();
}

/* ── EKLE / YÜKLE ───────────────────────────────────────────────────── */

function openFab() {
  sheet(`<h3>Ne yapmak istersin?</h3><div class="sub">Ekstre geçmişin omurgası, hızlı ekleme devam eden dönem için.</div>
    <button class="opt" onclick="openUpload()"><span style="font-size:24px">📄</span>
      <div><b>Ekstre Yükle</b><small>Hesap hareketleri veya kart ekstresi</small></div></button>
    <button class="opt" onclick="openAdd()"><span style="font-size:24px">➕</span>
      <div><b>İşlem Ekle</b><small>Devam eden döneme elle ekle</small></div></button>`);
}

function openUpload() {
  sheet(`<h3>Ekstre Yükle</h3>
    <div class="sub">Prototipte örnek ekstreler hazır. Gerçek üründe dosya seçilir; şifreli PDF ise parola istenir.</div>
    <button class="opt" onclick="upload('hesap')"><span style="font-size:24px">🏦</span>
      <div><b>Hesap Hareketleri (CSV)</b><small>Ağustos · 4 işlem</small></div></button>
    <button class="opt" onclick="upload('kart')"><span style="font-size:24px">💳</span>
      <div><b>Kredi Kartı Ekstresi (PDF)</b><small>19 Tem – 18 Ağu · 6 işlem · taksit içerir</small></div></button>
    <div class="tiny muted" style="margin-top:6px">Aynı ekstreyi iki kez yüklersen işlemler çiftlenmez — parmak izi ile tekilleştirilir.</div>`);
}

async function upload(sample) {
  const r = await api('/api/upload', {
    method: 'POST', headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ sample })
  });
  B = r.bundle;
  const s = r.sonuc;
  sheet(`<h3>Ekstre işlendi</h3>
    <div class="sub">${s.donem ? s.donem[0] + ' → ' + s.donem[1] : ''}</div>
    <div class="card flat"><div class="li"><span class="nm">Bulunan satır</span><span class="v">${s.toplam_satir}</span></div>
      <div class="li"><span class="nm">Yeni eklenen</span><span class="v" style="color:var(--yesil)">${s.eklenen}</span></div>
      <div class="li"><span class="nm">Zaten vardı (mükerrer)</span><span class="v">${s.mukerrer}</span></div>
      ${s.borc_anlik ? `<div class="li"><span class="nm">Dönem sonu borcu</span><span class="v">₺${s.borc_anlik[1].toLocaleString('tr-TR')}</span></div>` : ''}
    </div>
    ${s.uyarilar.length ? `<div class="alert" style="margin-top:10px"><span>⚠️</span><div>${s.uyarilar.map(esc).join('<br>')}</div></div>` : ''}
    <button class="cta" onclick="closeSheet();render()">Tamam</button>
    ${B.triyaj.kartlar.length ? `<button class="cta ghost" onclick="openTriage()">Plansız harcamaları işaretle</button>` : ''}
    ${B.kategori_triyaji && B.kategori_triyaji.kartlar.length
      ? `<button class="cta ghost" onclick="openCatTriage()">Tanımadığımız ${B.kategori_triyaji.kartlar.length} işyerini tanıt</button>` : ''}`);
  render();
}

const CATS = [['restoran', 'Restoran & Kafe'], ['market', 'Market'], ['ulasim', 'Ulaşım'],
['giyim', 'Giyim'], ['eglence', 'Eğlence & Hobi'], ['saglik', 'Sağlık'],
['faturalar', 'Faturalar'], ['diger', 'Diğer']];
let ADD = { planned: null, emotion: null };

function openAdd() {
  ADD = { planned: null, emotion: null };
  sheet(`<h3>İşlem Ekle</h3>
    <div class="sub">Devam eden döneme eklenir. Skoru dönem kapanınca etkiler.</div>
    <div class="field"><label>Tutar (₺)</label><input id="amt" type="number" inputmode="decimal" placeholder="0"></div>
    <div class="field"><label>Açıklama</label><input id="desc" placeholder="Nereye harcadın?"></div>
    <div class="field"><label>Kategori</label><select id="cat">
      ${CATS.map(([v, l]) => `<option value="${v}">${l}</option>`).join('')}</select></div>
    <div class="field"><label>Planlı mıydı?</label><div class="seg" id="segP">
      <button onclick="setP(false,this)">Plansızdı</button>
      <button onclick="setP(true,this)">Planlıydı</button></div></div>
    <div class="field"><label>Nasıl hissettin? (isteğe bağlı)</label><div class="seg" id="segE" style="flex-wrap:wrap">
      <button onclick="setE('odul',this)">Ödül</button>
      <button onclick="setE('stres',this)">Stres</button>
      <button onclick="setE('sosyal',this)">Sosyal</button></div></div>
    <button class="cta" onclick="saveTxn()">Ekle</button>
    <div class="tiny muted" style="margin-top:9px">Etiketi burada topluyoruz çünkü doğru an bu — aylar sonra değil.</div>`);
}
function setP(v, b) { ADD.planned = v; [...b.parentNode.children].forEach(x => x.classList.remove('on')); b.classList.add('on'); }
function setE(v, b) {
  const on = b.classList.contains('on');
  [...b.parentNode.children].forEach(x => x.classList.remove('on'));
  ADD.emotion = on ? null : v; if (!on) b.classList.add('on');
}

async function saveTxn() {
  const amount = parseFloat($('#amt').value);
  if (!amount || amount <= 0) { toast('Tutar gir'); return; }
  B = await api('/api/txn', {
    method: 'POST', headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({
      amount, category: $('#cat').value, desc: $('#desc').value,
      planned: ADD.planned, emotion: ADD.emotion
    })
  });
  closeSheet(); render(); toast('Devam eden döneme eklendi');
}

/* ── sheet / navigasyon ─────────────────────────────────────────────── */

function sheet(html) { $('#sheet').innerHTML = html; $('#sheetWrap').hidden = false; }
function closeSheet() { $('#sheetWrap').hidden = true; }
function go(tab) { TAB = tab; document.querySelectorAll('.tabbar [data-tab]').forEach(b => b.classList.toggle('on', b.dataset.tab === tab)); render(); }

function render() {
  $('#view').innerHTML = { home: viewHome, analysis: viewAnalysis, plan: viewPlan, coach: viewCoach }[TAB]();
  $('#view').scrollTop = 0;
}

async function boot(state) {
  B = await api('/api/state?s=' + state);
  document.querySelectorAll('#statePills button').forEach(b => b.classList.toggle('on', b.dataset.state === state));
  TAB = 'home'; go('home');
}

document.addEventListener('click', (e) => {
  const t = e.target.closest('[data-tab]'); if (t) return go(t.dataset.tab);
  const s = e.target.closest('#statePills button'); if (s) return boot(s.dataset.state);
  if (e.target.closest('#fab')) return openFab();
  if (e.target.closest('[data-close]')) return closeSheet();
});

boot('olgun');
