/* ═══ Fitnes oyun katmanı — DURUM sekmesi, olay kartları, hızlı öğün/favori ═══
 * Veri yalnız GET /durum (⚠ yan etkili: yeni olayları yazar). Kart kuralı:
 *  · teslim "anlik" ve "kart" olan olay ekranda kart olur; "ozet"/"bekleyen" Durum'da sessiz satır.
 *  · Aynı olay iki kez kart olmaz (sunucuda "görüldü" + bu tarayıcıda id defteri).
 *  · Günlük tavanı SUNUCU sayar (bugun_kalan); yoksa tarayıcı defteri yedek (5).
 *  · Tören kartları (SEVİYE, HAFTALIK RAPOR, UYANIŞ) ortada perdede tek tek, TAMAM'la kapanır;
 *    diğerleri sağ altta yığın, 1,5 sn arayla girer. Olay anlarının hareketi hareket.js'te.
 * Görünüm: #fitnes-v2[data-gorunum] = durum | lig | beceri (‹ DURUM ile geri).
 */
const FITNES_BK_KEY = 'yuki_fitnes_bildirim_v1';
const FITNES_TAVAN = 5;
const FITNES_KARTLI = new Set(['anlik', 'kart']);
const _fit = { durum: null, fav: [], zaman: null };
const FIT_LIGLER = ['E', 'D', 'C', 'B', 'A', 'S'];
const FIT_ELMAS = '20,6 24,16 34,20 24,24 20,34 16,24 6,20 16,16';
const FIT_YILDIZ = '20,3 24.5,15.5 37,20 24.5,24.5 20,37 15.5,24.5 3,20 15.5,15.5';   // aynı nokta sayısı → ◆→★
function fitLigAd(k) { return fT('lig.' + k); }
const _fitLigNo = k => Math.max(0, FIT_LIGLER.indexOf(k));
const _fitSv = d => { const n = d && d.seviye; return n != null && n !== '' && isFinite(n) ? String(n) : '—'; };
const _fitAzalt = () => { const H = window.HareketAyar; return H && H.etkinYogunluk ? H.etkinYogunluk() === 'kapali' : fsAzalt(); };

/* Lig rozeti — satır içi SVG (dış çember çizgi + iç simge dolgu). Her lig ayrı simge; renk --rz-<lig>. */
const _ROZET_SIMGE = {
  E: '<circle cx="48" cy="48" r="10"/>',
  D: '<path d="M48 26L53 43L70 48L53 53L48 70L43 53L26 48L43 43Z"/>',
  C: '<path d="M48 28a20 20 0 1 0 0 40a14 14 0 1 1 0-40Z"/>',
  B: '<path d="M60 30a22 22 0 1 0 0 36a17 17 0 1 1 0-36Z"/><circle cx="62" cy="40" r="3"/>',
  A: '<circle cx="34" cy="36" r="4"/><circle cx="58" cy="30" r="4"/><circle cx="64" cy="56" r="4"/><circle cx="40" cy="62" r="4"/><path class="rz-cizgi" d="M34 36L58 30L64 56L40 62Z"/>',
  S: '<circle cx="48" cy="48" r="18"/><circle class="rz-oyuk" cx="54" cy="44" r="15"/>',
};
function fitRozet(k, px, sinif) {
  const lig = FIT_LIGLER.includes(k) ? k : 'E';
  return `<svg class="fit-rozet rz-${lig}${sinif ? ' ' + sinif : ''}" width="${px}" height="${px}" viewBox="0 0 96 96" aria-hidden="true" focusable="false">` +
    `<circle class="rz-halka" cx="48" cy="48" r="43"/><circle class="rz-halka ic" cx="48" cy="48" r="36"/>${_ROZET_SIMGE[lig]}</svg>`;
}

/* Kadran: 60 tik (.kd-tik) + XP yayı + tek altın halka (.kd-altin, Hareket.seviye çizer) */
function fitKadranSvg(oran, px) {
  const c = 100, R = 92, kut = (r, a) => [c + r * Math.sin(a * Math.PI / 180), c - r * Math.cos(a * Math.PI / 180)];
  let tik = '';
  for (let i = 0; i < 60; i++) {
    const uzun = i % 5 === 0, [x0, y0] = kut(R, i * 6), [x1, y1] = kut(R - (uzun ? 7 : 3), i * 6);
    tik += `<line class="kd-tik${uzun ? ' uzun' : ''}" x1="${x0.toFixed(1)}" y1="${y0.toFixed(1)}" x2="${x1.toFixed(1)}" y2="${y1.toFixed(1)}"/>`;
  }
  const o = Math.max(0.001, Math.min(0.9999, oran || 0)), [ax, ay] = kut(76, 360 * o);
  return `<svg class="fd-kadran-svg" viewBox="0 0 200 200" width="${px}" height="${px}" aria-hidden="true">
    <circle class="kd-halka" cx="${c}" cy="${c}" r="96"/>${tik}<circle class="kd-iz" cx="${c}" cy="${c}" r="76"/>
    <path class="kd-yay" d="M${c} ${c - 76} A76 76 0 ${o > 0.5 ? 1 : 0} 1 ${ax.toFixed(2)} ${ay.toFixed(2)}"/><circle class="kd-uc" cx="${ax.toFixed(2)}" cy="${ay.toFixed(2)}" r="3.5"/>
    <circle class="kd-altin" cx="${c}" cy="${c}" r="84" transform="rotate(-90 100 100)"/></svg>`;
}

function _fitBk() {
  let k = null;
  try { k = JSON.parse(localStorage.getItem(FITNES_BK_KEY) || 'null'); } catch {}
  if (!k || typeof k !== 'object') k = { gun: '', sayi: 0, ids: [] };
  if (k.gun !== fsTodayStr()) { k.gun = fsTodayStr(); k.sayi = 0; }
  if (!Array.isArray(k.ids)) k.ids = [];
  return k;
}
function _fitBkYaz(k) { k.ids = k.ids.slice(-300); try { localStorage.setItem(FITNES_BK_KEY, JSON.stringify(k)); } catch {} }

function fitnesDurumYukle() {
  clearTimeout(_fit.zaman);
  _fit.zaman = setTimeout(async () => {
    const d = await fsGet('/durum');
    if (!d) return;
    _fit.durum = d;
    fitnesV2Ciz(d);
    document.dispatchEvent(new CustomEvent('fitnes:durum', { detail: d }));
    fitnesBildirim(d.bekleyen_olaylar || []);
  }, 250);
}

/* ── Kartlar ── */
const FIT_TOREN = new Set(['SEVIYE', 'HAFTALIK_OZET', 'UYANIS']);
const _fitPerde = { sira: [], acik: null, yigin: [] };
function fitnesBildirim(olaylar) {
  const k = _fitBk(), d = _fit.durum || {};
  let hak = Number.isFinite(d.bugun_kalan) ? Math.max(0, d.bugun_kalan) : FITNES_TAVAN - k.sayi;
  for (const o of olaylar) {
    if (!FITNES_KARTLI.has(o.teslim) || k.ids.includes(o.id)) continue;
    if (hak <= 0) break;
    k.ids.push(o.id); k.sayi++; hak--;
    const kart = _fitKart(o, d);
    (FIT_TOREN.has(o.tur) ? _fitPerde.sira : _fitPerde.yigin).push(kart);
    fsApiPost('/olaylar/' + encodeURIComponent(o.id) + '/goruldu', {});
  }
  _fitBkYaz(k);
  _fitPerdeSonraki();
}

function _fitKart(o, d) {
  const v = o.veri || {}, tur = o.tur === 'PR' ? 'REKOR' : o.tur, toren = FIT_TOREN.has(tur);
  const kart = document.createElement('div');
  kart.className = `fitnes-bildirim fk fk-${tur.toLowerCase()}`;
  kart.dataset.olay = o.id; kart.dataset.tur = tur;
  kart.setAttribute('role', toren ? 'dialog' : 'status');
  kart.setAttribute('aria-label', fT('tur.' + tur));
  const bas = `<small class="fk-onek">${fT('kart.onek', { tur: fT('tur.' + tur) })}</small>`;
  const metin = `<p class="fk-metin" data-satir>${fsKac(String(o.metin || '').replace(/^Bildirim:\s*/, ''))}</p>`;
  let govde = bas + metin;
  if (tur === 'SEVIYE') {
    const L = +v.seviye || +d.seviye || 0, onceki = +v.onceki_zirve || Math.max(0, L - 1);
    const acilan = (v.acilan || []).map(a => fsKac(a.ad)).join(' · '), sonraki = d.oduller && d.oduller.sonraki;
    const oran = d.xp_sonraki ? Math.min(1, (d.xp_seviye_ici || 0) / d.xp_sonraki) : 0;
    Object.assign(kart.dataset, { xpBas: 0, xpEsik: 0, oranBas: 0, oranSon: oran.toFixed(3), xpSon: Math.round(d.xp_seviye_ici || 0) });
    govde = `<div class="fk-sv">${fitKadranSvg(oran, 120)}<div class="fk-sv-no"><span class="sv-eski">${onceki}</span><span class="sv-yeni">${L}</span></div><div class="sv-isik"></div></div>
      <div class="bildirim">${bas}${metin}${acilan ? `<p class="fk-ek" data-satir>${fT('kart.acilan', { liste: acilan })}</p>` : ''}
      ${sonraki ? `<p class="fk-ek" data-satir>${fT('kart.sonraki-odul', { sv: sonraki.seviye, ad: fsKac(sonraki.ad) })}</p>` : ''}</div>`;
  } else if (tur === 'REKOR') {
    const yeni = +v.kilo || 0;
    kart.dataset.eski = +v.onceki_kilo || yeni; kart.dataset.yeni = yeni;
    govde = `<div class="rk-kart"><div class="fk-buyuk"><span class="rk-sayi">${fsSay(yeni, 1)}</span><small> KG${v.tekrar ? ' × ' + fsKac(v.tekrar) : ''}</small></div></div>
      <div class="bildirim">${bas}${metin}${v.e1rm ? `<p class="fk-ek" data-satir>${fT('kart.e1rm', { kg: fsSay(v.e1rm, 1) })}</p>` : ''}</div>`;
  } else if (tur === 'BECERI' || tur === 'EVRIM') {
    if (tur === 'EVRIM') kart.dataset.yildiz = FIT_YILDIZ;
    govde = `<div class="fk-bc"><svg class="bc-yeni" viewBox="0 0 40 40" aria-hidden="true"><polygon class="bc-kesik" points="${FIT_ELMAS}"/><g class="bc-dolu"><polygon points="${FIT_ELMAS}"/></g></svg>
      <b class="bc-ad">${fsKac(v.ad || '')}</b></div><div class="bildirim${tur === 'EVRIM' ? ' evrim' : ''}">${bas}${metin}</div>`;
  } else if (tur === 'HAFTALIK_OZET') {
    govde = bas + metin + _fitOzetSatirlar(d.haftalik_ozet);
  } else if (tur === 'UYANIS') {
    govde = bas + metin + `<div class="fk-statlar" data-satir>${['guc', 'day', 'dis', 'bes'].map(a =>
      `<div><small>${fT('stat.' + a)}</small><b>${v[a] == null ? '—' : fsKac(v[a])}</b></div>`).join('')}</div>`;
  } else if ((tur === 'GOLGE' || tur === 'HAFTA_HEDEFI') && d.lig_ilerleme && d.lig_ilerleme.golge) {
    const li = d.lig_ilerleme;
    govde += _fitKiyas(li.xp, li.golge, li.terfi_esik);
  }
  kart.innerHTML = `<div class="fk-ic">${govde}</div><button type="button" class="fk-kapat" aria-label="${toren ? fT('ortak.tamam') : fT('ortak.kapat')}">${toren ? fT('ortak.tamam-buyuk') : '✕'}</button>`;
  return kart;
}

function _fitOynat(kart) {
  const H = window.Hareket, sahne = H && { SEVIYE: 'seviye', REKOR: 'rekor', BECERI: 'beceri', EVRIM: 'evrim' }[kart.dataset.tur];
  kart.classList.add(sahne ? 'fk-hareket' : _fitAzalt() ? 'fk-durgun' : 'fk-css');
  const p = sahne ? H[sahne](kart) : Promise.resolve({ kapali: _fitAzalt(), sure: _fitAzalt() ? 0 : 320 });
  return p.then(r => { kart.dataset.hareketSure = r.sure; return r; }, () => ({}));
}
function _fitYigina(kart, i) {
  const yer = document.getElementById('fitnes-bildirimler');
  if (!yer) return;
  yer.appendChild(kart);
  kart.querySelector('.fk-kapat').onclick = () => kart.remove();
  const bekle = _fitAzalt() ? 0 : i * 1500;
  if (bekle) kart.style.visibility = 'hidden';
  setTimeout(() => { kart.style.visibility = ''; _fitOynat(kart); }, bekle);
  setTimeout(() => kart.remove(), 9000 + bekle);
}
function _fitPerdeSonraki() {
  if (_fitPerde.acik) return;
  if (!_fitPerde.sira.length) { _fitPerde.yigin.splice(0).forEach((k, i) => _fitYigina(k, i)); return; }
  let perde = document.getElementById('fitnes-perde');
  if (!perde) {
    perde = document.createElement('div'); perde.id = 'fitnes-perde'; perde.hidden = true;
    document.body.appendChild(perde);
    perde.addEventListener('keydown', e => { if (e.key === 'Escape') _fitPerdeKapat(); });
  }
  const kart = _fitPerde.sira.shift();
  _fitPerde.acik = kart;
  perde.replaceChildren(kart); perde.hidden = false;
  kart.querySelector('.fk-kapat').onclick = _fitPerdeKapat;
  _fitOynat(kart);
  kart.querySelector('.fk-kapat').focus({ preventScroll: true });
}
async function _fitPerdeKapat() {
  const kart = _fitPerde.acik, perde = document.getElementById('fitnes-perde');
  if (!kart) return;
  if (window.Hareket) await window.Hareket.kapat(kart);
  perde.hidden = true; perde.replaceChildren(); _fitPerde.acik = null;
  setTimeout(_fitPerdeSonraki, _fitAzalt() ? 0 : 1500);
}

function _fitKiyas(xp, golge, esik) {
  const tavan = Math.max(xp || 0, golge || 0, esik || 0) * 1.08 || 1, y = v => Math.min(100, (v || 0) / tavan * 100).toFixed(1);
  return `<div class="fd-kiyas" data-satir><div class="fd-kiyas-sat"><span>${fT('durum.bu-hafta')}</span><span class="fd-ray"><i style="width:${y(xp)}%"></i>${esik ? `<em class="fd-esik" style="left:${y(esik)}%"></em>` : ''}</span><b>${fsSay(xp)}</b></div>
    <div class="fd-kiyas-sat golge"><span>${fT('durum.golge')}</span><span class="fd-ray"><i style="width:${y(golge)}%"></i></span><b>${fsSay(golge)}</b></div></div>`;
}
function _fitOzetSatirlar(z) {
  if (!z) return '';
  const s = [], a = z.antrenman || {};
  const lig = z.lig_once && z.lig_sonra && z.lig_once !== z.lig_sonra
    ? `${fitLigAd(z.lig_once)} → ${fitLigAd(z.lig_sonra)}`
    : z.sonuc === 'degerlendirilmedi' ? fT('ozet.degerlendirilmedi') + (z.sebep ? ' · ' + z.sebep : '') : fT('ozet.kaldin', { lig: fitLigAd(z.lig_sonra || 'E') });
  s.push([fT('ozet.lig'), lig]);
  if (a.gun || a.yapilan_set) s.push([fT('ozet.antrenman'), fT('ozet.antrenman-deger', { gun: a.gun || 0, hedef: a.hedef || 0, set: a.yapilan_set || 0, ton: fsSay(a.tonaj) })]);
  if ((z.rekorlar || []).length) s.push([fT('ozet.rekorlar'), z.rekorlar.map(r => `${r.hareket} ${fsSay(r.kilo, r.kilo % 1 ? 1 : 0)} × ${r.tekrar}`).join(' · ') + (z.rekor_fazla ? ` · +${z.rekor_fazla}` : '')]);
  const sd = z.stat_degisim || {};
  if (Object.values(sd).some(x => x)) s.push([fT('ozet.stat'), ['guc', 'day', 'dis', 'bes'].map(k => `${fT('stat.' + k)} ${sd[k] > 0 ? '▲' : sd[k] < 0 ? '▼' : '·'}${Math.abs(sd[k] || 0)}`).join(' · ')]);
  if ((z.beceriler || []).length) s.push([fT('ozet.beceri'), z.beceriler.map(b => `${b.durum === 'evrim' ? '★' : '◆'} ${b.ad}`).join(' · ')]);
  if (z.seviye && z.seviye.son > z.seviye.bas) s.push([fT('ozet.seviye'), `${fT('ortak.sv', { n: z.seviye.bas })} → ${fT('ortak.sv', { n: z.seviye.son })}`]);
  if (z.bu_hafta && z.bu_hafta.terfi_esik != null) s.push([fT('ozet.bu-hafta'), fT('ozet.terfi-icin', { xp: fsSay(z.bu_hafta.terfi_esik) })]);
  return _fitKiyas(z.xp, z.golge, z.golge ? z.golge * 1.1 : null) +
    `<ul class="fk-ozet">${s.map(([k, x]) => `<li data-satir><span>${k}</span><b>${fsKac(x)}</b></li>`).join('')}</ul>`;
}

/* ── DURUM sekmesi ── */
const _fv = { gorunum: 'durum', secili: null, haftaNot: '' };
const FIT_DAL = ['guc', 'day', 'dis', 'bes', 'golge'];

function _fitKap() {
  let el = document.getElementById('fitnes-v2');
  if (el) return el;
  const pano = document.getElementById('fstrip-pane-durum');
  if (!pano) return null;
  el = document.createElement('div'); el.id = 'fitnes-v2'; el.className = 'fd';
  pano.prepend(el);
  return el;
}
function fitnesV2Ciz(d) {
  d = d || _fit.durum;
  if (!d) return;
  const lig = d.lig || d.rutbe || 'E', yuva = document.getElementById('fitnes-ust-sv');
  if (yuva) yuva.innerHTML = `<button type="button" class="fd-cip" data-fd-git="lig" aria-label="${fT('durum.cip-aria', { sv: _fitSv(d), lig: fitLigAd(lig) })}">${fitRozet(lig, 24)}<span>${fT('ortak.sv', { n: _fitSv(d) })}</span><span class="fd-cip-lig">${fitLigAd(lig)}</span></button>`;
  const kap = _fitKap();
  if (!kap) return;
  kap.dataset.gorunum = _fv.gorunum;
  kap.innerHTML = _fv.gorunum === 'lig' ? _fitLigGorunum(d) : _fv.gorunum === 'beceri' ? _fitBeceriGorunum(d) : _fitDurumGorunum(d);
}

function _fitDurumGorunum(d) {
  const lig = d.lig || d.rutbe || 'E', li = d.lig_ilerleme || {}, st = d.stat || {};
  const oran = d.xp_sonraki ? Math.min(1, (d.xp_seviye_ici || 0) / d.xp_sonraki) : 0;
  const unv = d.unvanlar || [], secili = unv.find(u => u.kod === d.unvan_secili);
  const sd = (d.haftalik_ozet && d.haftalik_ozet.stat_degisim) || {};
  const bec = d.beceriler || [], edin = bec.filter(b => b.durum === 'edinildi' || b.durum === 'evrim');
  const son = edin.slice().sort((a, b) => String(b.tarih || '').localeCompare(String(a.tarih || '')))[0];
  const sonraki = d.oduller && d.oduller.sonraki, g = d.gorevler || [], h = d.hafta_hedefi;
  const stat = k => `<div class="fd-stat" data-fd-stat="${k}"><span class="f-etiket">${fT('stat-uzun.' + k)}</span><span class="fd-stat-ust"><b>${st[k] == null ? '—' : fsKac(st[k])}</b>
    <em class="${sd[k] ? '' : 'yok'}">${sd[k] ? fT('durum.gecen-hafta', { n: (sd[k] > 0 ? '+' : '') + sd[k] }) : fT('stat-not.' + k)}</em></span></div>`;
  const ozet = (d.bekleyen_olaylar || []).filter(o => !FITNES_KARTLI.has(o.teslim));
  return `<section class="fd-kart fd-pencere" aria-label="${fT('durum.pencere')}">
    <div class="fd-kimlik"><div><span class="f-etiket">${fT('durum.unvan')}</span><h2 class="fd-unvan" data-fd-unvan>${fsKac(secili ? secili.ad : fT('durum.unvan-yok'))}</h2></div>
      <button type="button" class="fd-lig" data-fd-git="lig">${fitRozet(lig, 32)}<span><small class="f-etiket">${fT('durum.lig')}</small><b>${fitLigAd(lig)}</b></span><span class="fd-ok">›</span></button></div>
    <div class="fd-govde">
      <div class="fd-sut">${stat('guc')}${stat('day')}</div>
      <div class="fd-kadran" role="img" aria-label="${fT('durum.kadran-aria', { sv: _fitSv(d), xp: fsSay(d.xp_seviye_ici), son: fsSay(d.xp_sonraki) })}">${fitKadranSvg(oran, 168)}
        <div class="fd-merkez"><span class="f-etiket">${fT('durum.seviye')}</span><b data-fd-sv>${_fitSv(d)}</b><small><span class="fd-mavi">${fsSay(d.xp_seviye_ici)}</span> / ${fsSay(d.xp_sonraki)} XP</small></div></div>
      <div class="fd-sut sag">${stat('dis')}${stat('bes')}</div>
    </div>
    ${d.kalibrasyon ? `<p class="fd-not" id="fitnes-kalib">${fT('durum.kalibrasyon')}</p>` : ''}
    ${sonraki ? `<p class="fd-not" data-fd-sonraki>${fT('durum.sonraki-odul', { sv: sonraki.seviye, ad: fsKac(sonraki.ad) })}</p>` : ''}
  </section>
  <section class="fd-kart" aria-label="${fT('durum.gorev')}">
    <div class="fd-bas"><span class="f-etiket">${fT('durum.gorev')}</span><span class="fd-sag" id="fitnes-gsay">${fT('durum.gorev-say', { n: g.filter(x => x.tamam).length, m: g.length })}</span></div>
    <div id="fitnes-gorevler">${g.map(x => `<div class="fitnes-gorev${x.tamam ? ' tamam' : ''}" data-gorev="${fsKac(x.kod)}"><span class="durum" aria-label="${x.tamam ? fT('durum.tamam') : fT('durum.acik')}">${x.tamam ? '✓' : '○'}</span>
      <span>${fsKac(x.ad)}</span><span class="fd-ray"><i style="width:${x.hedef ? Math.min(100, x.ilerleme / x.hedef * 100) : 0}%"></i></span><span class="d">${fsSay(x.ilerleme)}/${fsSay(x.hedef)}</span></div>`).join('')}</div>
    ${h ? `<p class="fd-not">${fT('durum.hafta-hedef', { n: h.hedef, i: h.ilerleme })}</p>` : ''}
    ${ozet.slice(0, FITNES_TAVAN).map(o => `<div class="fitnes-ozet-k" data-olay="${fsKac(o.id)}"><span>${fsKac(String(o.metin).replace(/^Bildirim:\s*/, ''))}</span><button type="button" data-goruldu="${fsKac(o.id)}">${fT('ortak.tamam-buyuk')}</button></div>`).join('')}
  </section>
  <section class="fd-kart" aria-label="${fT('durum.bu-hafta-lig')}">
    <div class="fd-bas"><span class="f-etiket">${fT('durum.bu-hafta-lig')}</span><button type="button" class="fd-metin-dug" data-fd-git="lig">${fT('durum.lig')} ›</button></div>
    ${li.golge != null ? _fitKiyas(li.xp, li.golge, li.terfi_esik) + `<p class="fd-not">${_fitLigCumle(li)}</p>`
      : `<p class="fd-not">${d.kalibrasyon ? fT('durum.golge-kalib') : fT('durum.golge-yok')}</p>`}
  </section>
  <section class="fd-kart" aria-label="${fT('durum.beceriler')}">
    <div class="fd-bas"><span class="f-etiket">${fT('durum.beceriler')} · ${edin.length} / ${bec.length}</span><button type="button" class="fd-metin-dug" data-fd-git="beceri">${fT('durum.agac')} ›</button></div>
    <p class="fd-not">${son ? fT('durum.son-beceri', { ad: fsKac(son.ad) }) : fT('durum.beceri-yok')}</p>
  </section>
  <section class="fd-kart" aria-label="${fT('durum.unvanlar')}">
    <div class="fd-bas"><span class="f-etiket">${fT('durum.unvanlar')} · ${unv.length}</span>${unv.length > 1 ? `<span class="fd-sag">${fT('durum.dokun-tak')}</span>` : ''}</div>
    <div class="fd-unvanlar">${unv.map(u => `<button type="button" class="fd-madalyon${u.kod === d.unvan_secili ? ' takili' : ''}" data-fd-unvan-sec="${fsKac(u.kod)}" aria-pressed="${u.kod === d.unvan_secili}">${_fitMadalyon()}<span>${fsKac(u.ad)}</span></button>`).join('')}
      ${sonraki && sonraki.tur === 'unvan' ? `<div class="fd-madalyon kilitli" aria-label="${fT('durum.kilitli', { ad: fsKac(sonraki.ad), sv: sonraki.seviye })}">${_fitMadalyon(sonraki.seviye)}<span>${fsKac(sonraki.ad)}</span></div>` : ''}
      ${unv.length ? '' : `<p class="fd-not">${fT('durum.ilk-unvan')}</p>`}</div>
  </section>`;
}
function _fitMadalyon(sv) {
  return `<svg viewBox="0 0 56 56" aria-hidden="true"><circle class="m-dis" cx="28" cy="28" r="26"/><circle class="m-ic" cx="28" cy="28" r="20"/>${sv ? `<text x="28" y="29" text-anchor="middle" dominant-baseline="middle">${sv}</text>` : '<path class="m-elmas" d="M28 19 L37 28 L28 37 L19 28 Z"/>'}</svg>`;
}
function _fitLigCumle(li) {
  if (li.guvende) return fT('durum.guvende');
  const kalan = Math.max(0, Math.ceil((li.terfi_esik || 0) - (li.xp || 0)));
  return kalan ? fT('durum.terfiye-kalan', { n: fsSay(kalan) }) : fT('durum.terfi-bolgesi');
}

function _fitLigGorunum(d) {
  const lig = d.lig || d.rutbe || 'E', no = _fitLigNo(lig), li = d.lig_ilerleme || {}, z = d.haftalik_ozet, dort = li.dort_hafta_once ?? null;
  const deg = [[fT('durum.golge-kisa'), li.golge, ''], [fT('durum.sen'), li.xp, 'sen'], [fT('durum.dort-hafta'), dort, '']];
  const tavan = Math.max(...deg.map(x => x[1] || 0), li.terfi_esik || 0) * 1.08 || 1;
  const sira = deg.map(x => x[1]).filter(v => v != null).sort((a, b) => b - a);
  const h = v => (v == null ? 6 : Math.max(6, v / tavan * 100)).toFixed(1);
  const tur = d.hafta_turu || null, hak = z && z.bu_hafta && z.bu_hafta.dondurma_hakki;
  const dug = (k, ad) => `<button type="button" class="fd-hafta-dug${tur === k ? ' secili' : ''}" data-fd-hafta="${k}" aria-pressed="${tur === k}">${tur === k ? '✓ ' : ''}${ad}</button>`;
  return `<button type="button" class="fd-metin-dug fd-geri" data-fd-git="durum">‹ ${fT('durum.durum')}</button>
  <section class="fd-kart" aria-label="${fT('durum.lig-haftasi')}">
    <div class="fd-lig-bas">${fitRozet(lig, 72)}<div><span class="f-etiket">${fT('durum.lig')} · ${no + 1} / 6</span><h2>${fitLigAd(lig)}</h2></div></div>
    <div class="fd-podyum" role="img" aria-label="${fT('durum.podyum-aria', { sen: fsSay(li.xp), golge: li.golge == null ? '—' : fsSay(li.golge), dort: dort == null ? '—' : fsSay(dort) })}">
      ${deg.map(([ad, v, s]) => `<div class="fd-basamak ${s}" style="--h:${h(v)}%"><span class="fd-kim"><span class="ad">${ad}</span><b>${v == null ? '—' : fsSay(v)}</b></span><span class="fd-sira">${v == null ? '' : sira.indexOf(v) + 1}</span></div>`).join('')}
      ${li.terfi_esik ? `<div class="fd-esik-cizgi" style="--e:${h(li.terfi_esik)}"><span>${fT('durum.terfi')} · <b>${fsSay(li.terfi_esik)}</b></span></div>` : ''}
    </div>
    <p class="fd-not">${li.golge != null ? _fitLigCumle(li) : fT('durum.podyum-bos')}</p>
  </section>
  <section class="fd-kart" aria-label="${fT('durum.hafta-turu')}"><div class="fd-bas"><span class="f-etiket">${fT('durum.bu-hafta')} · ${fT('hafta-tur.' + (tur || 'normal'))}</span></div>
    <p class="fd-not">${fT('hafta-tur-not.' + (tur || 'normal'))}</p>
    <div class="fd-hafta-dugmeler">${dug('dondurma', fT('durum.dondur') + (hak != null && tur !== 'dondurma' ? ' · ' + fT('durum.hak', { n: hak }) : ''))}${dug('deload', fT('durum.deload'))}</div>
    <p class="fd-not fd-hafta-not" role="status">${fsKac(_fv.haftaNot)}</p></section>
  <section class="fd-kart" aria-label="${fT('durum.ligler')}"><div class="fd-bas"><span class="f-etiket">${fT('durum.ligler')}</span></div>
    <div class="fd-yorunge">${FIT_LIGLER.map((k, i) => `<div class="fd-l${i < no ? ' gecti' : i === no ? ' burada' : ' uzak'}" style="--y:${-Math.round(Math.sin(Math.PI * i / 5) * 18)}px" data-fd-lig="${k}">${fitRozet(k, 40)}<span>${fitLigAd(k)}</span></div>`).join('')}</div>
  </section>
  ${z ? `<section class="fd-kart" aria-label="${fT('durum.gecen')}"><div class="fd-bas"><span class="f-etiket">${fT('durum.gecen')}</span></div>
    <ul class="fd-cetvel"><li><span><b>${fsKac(z.hafta)}</b><small>${fsSay(z.xp)} / ${fT('durum.golge-kisa')} ${z.golge == null ? '—' : fsSay(z.golge)}${z.sebep ? ' · ' + fsKac(z.sebep) : ''}</small></span>
    <span class="fd-sonuc ${z.sonuc === 'terfi' ? 'yuk' : z.sonuc === 'dusme' ? 'dus' : ''}">${fT('sonuc.' + (z.sonuc || 'degerlendirilmedi'))}</span></li></ul></section>` : ''}
  <section class="fd-kart" aria-label="${fT('durum.kural')}"><div class="fd-bas"><span class="f-etiket">${fT('durum.kural')}</span></div>
    <ul class="fd-cetvel kural"><li><span>${fT('kural.terfi')}</span><b>×1,10</b></li><li><span>${fT('kural.seri')}</span><b>3</b></li>
    <li><span>${fT('kural.dusme')}</span><b>&lt;0,70</b></li><li><span>${fT('kural.zaman')}</span><b>${fT('kural.pzt')}</b></li></ul></section>`;
}

function _fitBeceriGorunum(d) {
  const bec = d.beceriler || [], edin = bec.filter(b => b.durum === 'edinildi' || b.durum === 'evrim').length;
  const sec = bec.find(b => b.kod === _fv.secili) || bec.find(b => b.durum === 'edinildi' || b.durum === 'evrim') || bec[0];
  const gizli = b => b.gizli && b.durum === 'kapali';
  const dugum = (b, evrim) => {
    const ad = gizli(b) ? '???' : evrim ? b.evrim_ad : b.ad;
    const cls = evrim ? (b.durum === 'evrim' ? 'evrim acik' : 'evrim kilit') : gizli(b) ? 'gizli kilit' : b.durum;
    const s = sec && sec.kod === b.kod && !evrim;
    return `<button type="button" class="fd-dugum ${cls}${s ? ' secili' : ''}" data-fd-beceri="${fsKac(b.kod)}" aria-pressed="${s}"
      aria-label="${fsKac(ad)}, ${evrim ? fT(b.durum === 'evrim' ? 'beceri-d.evrim-acik' : 'beceri-d.evrim-kilit') : gizli(b) ? fT('beceri-d.gizli') : fT('beceri-d.' + b.durum)}">
      <span class="el" aria-hidden="true">${b.durum === 'askida' && !evrim ? '⏸' : ''}</span><span class="ad">${fsKac(ad)}</span></button>`;
  };
  const panel = sec ? `<section class="fd-kart fd-panel" aria-live="polite"><div class="fd-tur"><span class="el ${sec.durum}"></span><span class="f-etiket">${fT('dal.' + sec.dal)} · ${fT('beceri-d.' + sec.durum)}</span></div>
      <h3>${gizli(sec) ? '???' : fsKac(sec.ad)}</h3><p>${gizli(sec) ? fT('beceri.gizli-not') : fsKac(sec.kosul || '')}${sec.tarih ? ` · ${fsKac(String(sec.tarih).slice(0, 10))}` : ''}</p>
      ${sec.evrim_ad && !gizli(sec) ? `<div class="fd-kosul"><span class="f-etiket">${fT('beceri.evrim')} · ${fsKac(sec.evrim_ad)}</span><p>${fsKac(sec.evrim_kosul || '')}</p><small>${fT('beceri.evrim-not')}</small></div>` : ''}</section>` : '';
  return `<button type="button" class="fd-metin-dug fd-geri" data-fd-git="durum">‹ ${fT('durum.durum')}</button>
  <section class="fd-kart" aria-label="${fT('beceri.agac')}"><div class="fd-bas"><span class="f-etiket">${fT('beceri.agac-say', { n: edin, m: bec.length })}</span></div>
    <div class="fd-agac">${FIT_DAL.map((k, di) => { const l = bec.filter(b => b.dal === k); return l.length ? `<div class="fd-dal" style="--i:${di}"><span class="fd-dal-ad">${fT('dal.' + k)}</span>
      ${l.map(b => dugum(b) + (b.evrim_kod ? dugum(b, true) : '')).join('')}</div>` : ''; }).join('')}</div>
    <p class="fd-lejant"><span><i class="el edinildi"></i>${fT('beceri-d.edinildi')}</span><span><i class="el evrim acik"></i>${fT('beceri.evrim')}</span><span><i class="el askida"></i>${fT('beceri-d.askida')}</span><span><i class="el kapali"></i>${fT('beceri-d.kapali')}</span></p>
  </section>${panel}`;
}

function _fitPazartesi() { const g = new Date(fsTodayStr() + 'T12:00:00'); g.setDate(g.getDate() - (g.getDay() + 6) % 7); return _yerelGun(g); }

document.addEventListener('click', async e => {
  const t = e.target.closest && e.target.closest('[data-fd-git],[data-fd-beceri],[data-fd-unvan-sec],[data-fd-hafta],[data-goruldu]');
  if (!t || !_fit.durum) return;
  const D = _fit.durum;
  if (t.dataset.goruldu) {
    t.disabled = true;
    await fsApiPost('/olaylar/' + encodeURIComponent(t.dataset.goruldu) + '/goruldu', {});
    D.bekleyen_olaylar = (D.bekleyen_olaylar || []).filter(o => o.id !== t.dataset.goruldu);
  } else if (t.dataset.fdGit) {
    _fv.gorunum = t.dataset.fdGit;
    if (t.closest('#fitnes-ust-sv') && !_fitGenis()) fstripTab('durum');
  } else if (t.dataset.fdBeceri) {
    _fv.secili = t.dataset.fdBeceri;
  } else if (t.dataset.fdHafta) {
    const tur = D.hafta_turu === t.dataset.fdHafta ? null : t.dataset.fdHafta;
    t.disabled = true; _fv.haftaNot = '';
    const r = await fsIstek('PUT', '/hafta-turu', { hafta: _fitPazartesi(), tur });
    if (r.ok) { D.hafta_turu = r.json ? r.json.tur : tur; fitnesDurumYukle(); }
    else _fv.haftaNot = (r.json && typeof r.json.detail === 'string' && r.json.detail) || fT('ortak.baglanti');
  } else if (t.dataset.fdUnvanSec && t.getAttribute('aria-pressed') !== 'true') {
    t.disabled = true;
    if (await fsApiPut('/oyun/unvan', { kod: t.dataset.fdUnvanSec })) {
      D.unvan_secili = t.dataset.fdUnvanSec;
      (D.unvanlar || []).forEach(u => { u.secili = u.kod === D.unvan_secili; });
    }
  } else return;
  fitnesV2Ciz();
  const kap = document.getElementById('fitnes-v2');
  if (kap && t.dataset.fdGit) { kap.scrollIntoView({ block: 'nearest' }); const g = kap.querySelector('[data-fd-git]'); if (g) g.focus({ preventScroll: true }); }
  if (t.dataset.fdBeceri) { const y = document.querySelector(`[data-fd-beceri="${CSS.escape(_fv.secili)}"]`); if (y) y.focus({ preventScroll: true }); }
});
document.addEventListener('fitnes:sekme', e => { if (e.detail && e.detail.tab === 'durum') { _fv.gorunum = 'durum'; fitnesV2Ciz(); } });
document.addEventListener('fitnes:bitti', () => fitnesDurumYukle());
// Olay/görev/ödül adları SUNUCUDAN dile göre gelir: önce yeniden çiz (yerel metin), sonra tazele (sunucu metni)
document.addEventListener('fitnes:dil', () => { fitnesV2Ciz(); fitnesDurumYukle(); });

/* ── Hızlı öğün: son öğünü kopyala (bugünün, yoksa dünün son kalemi) + favoriler (sunucuda, ≤ 12) ── */
function _fitSon() { return _tb.liste.length ? _tb.liste[_tb.liste.length - 1] : _tb.dun.length ? _tb.dun[_tb.dun.length - 1] : null; }
function _fitFavMi(e) { return _fit.fav.some(f => f.name === e.name && f.meal === e.meal); }
function fitnesYildiz(e) {
  const on = _fitFavMi(e);
  return `<button type="button" class="fitnes-yildiz" data-fav="${fsKac(e.id)}" aria-pressed="${on}" aria-label="${fT(on ? 'fav.cikar' : 'fav.ekle', { ad: fsKac(e.name) })}">${on ? '★' : '☆'}</button>`;
}
async function fitnesHizliYukle() {
  const f = await fsGet('/favoriler');
  if (Array.isArray(f)) _fit.fav = f;
  fitnesHizliCiz();
  document.querySelectorAll('.tb-liste .fitnes-yildiz').forEach(b => { const e = _tb.liste.find(x => String(x.id) === b.dataset.fav); if (e) b.outerHTML = fitnesYildiz(e); });
}
function fitnesHizliCiz() {
  const yer = document.getElementById('fitnes-hizli'), son = _fitSon();
  if (!yer) return;
  yer.innerHTML = (son ? `<button type="button" class="fitnes-kopya" data-kopya="1">${fT('fav.kopyala', { ad: fsKac(son.name) })}</button>` : '') +
    _fit.fav.map((f, i) => `<button type="button" data-favekle="${i}" aria-label="${fT('fav.ekle-ogun', { ad: fsKac(f.name) })}">★ ${fsKac(f.name)}<small>${fsSay(f.cal)}</small></button>`).join('');
}
const _fitOgunGovde = x => ({ meal: x.meal || 'ara', name: x.name, cal: +x.cal || 0, protein: +x.protein || 0, carb: +x.carb || 0, fat: +x.fat || 0, entry_date: _tb.gun });
document.addEventListener('click', async e => {
  if (!e.target.closest || !e.target.closest('#fstrip-pane-nutr')) return;
  const kop = e.target.closest('[data-kopya]'), fe = e.target.closest('[data-favekle]'), yil = e.target.closest('.fitnes-yildiz');
  if (kop || fe) {
    const x = kop ? _fitSon() : _fit.fav[+fe.dataset.favekle];
    if (!x) return;
    (kop || fe).disabled = true;
    await fsApiPost('/meals', _fitOgunGovde(x));
    return tabakYukle();
  }
  if (yil) {
    e.stopPropagation();
    const m = _tb.liste.find(x => String(x.id) === yil.dataset.fav);
    if (!m) return;
    const yeni = _fitFavMi(m) ? _fit.fav.filter(f => !(f.name === m.name && f.meal === m.meal))
      : [..._fit.fav, { name: m.name, meal: m.meal, cal: +m.cal, protein: +m.protein, carb: +m.carb, fat: +m.fat }].slice(-12);
    const r = await fsApiPut('/favoriler', { favoriler: yeni });
    if (r) _fit.fav = Array.isArray(r) ? r : yeni;
    fitnesHizliCiz(); yil.outerHTML = fitnesYildiz(m);
  }
}, true);
