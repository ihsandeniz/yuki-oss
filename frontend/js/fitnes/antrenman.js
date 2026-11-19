/* ═══ Fitnes ANTRENMAN — ŞABLONLAR · ODAK · LİSTE + bitiş ekranı + şablon düzenleyici ═══
 * Kurallar (sunucuyla aynı):
 *  · Değere dokunmak ya da BİTTİ = yapıldı (girildi damgasını sunucu koyar). Şablondan gelen set "plan"dır
 *    (kesik çerçeve), dokunulana kadar sayılmaz. GERİ AL → girildi:null.
 *  · Bitiş yalnız açık eylemle (POST /bitir); dokunulmamış setler listelenir, istenirse "yaptım" diye onaylanır.
 *  · Şablon güne TEK istekte yüklenir; aynı gün ikinci kez → 409 → "zaten yüklü" ekranı (yine=1 ile bilerek).
 *  · Hazır şablonlar ön yüz sabitidir; düzenlenince kendi kopyası (hazir-<slug>) olur, silinince hazır geri gelir.
 *  · Geçmiş güne giriş: GEÇMİŞ'ten "bu güne idman gir" → _od.hedef; sekmeden çıkınca hedef düşer (yanlışlıkla
 *    geçmişe yazılmasın).
 * Set modeli: {id, reps, weight, completed, girildi, drops, dokun?, geri?}. Süreli harekette reps = saniye.
 */
// "Bench Press 3x10@80", "Squat 4 x 8 @ 100", "Pull-up 3*8"
function parseFitdown(girdi) {
  const m = girdi.match(/^(.+?)\s+(\d+)\s*[xX×*]\s*(\d+)(?:\s*[@＠]\s*(\d+(?:[.,]\d+)?)\s*(?:kg)?)?\s*$/i);
  return m ? { name: m[1].trim(), sets: +m[2], reps: +m[3], weight: m[4] ? parseFloat(m[4].replace(',', '.')) : 0 } : null;
}

// Hazır şablonlar: ad sözlükten (adAnahtar), egzersiz adları çevrilmez (salon terimleri iki dilde de İngilizce).
const _S = (r, w, n) => Array.from({ length: n }, () => ({ reps: r, weight: w }));
const FW_STARTER_TEMPLATES = [
  { id: 'starter_chest', adAnahtar: 'sablon.gogus', exercises: [
    { name: 'Bench Press', sets: _S(8, 60, 4) }, { name: 'Incline DB Press', sets: _S(10, 20, 3) },
    { name: 'Cable Fly', sets: _S(12, 15, 3) }, { name: 'Tricep Pushdown', sets: _S(12, 25, 3) }] },
  { id: 'starter_back', adAnahtar: 'sablon.sirt', exercises: [
    { name: 'Deadlift', sets: _S(5, 80, 3) }, { name: 'Pull-up', sets: _S(8, 0, 3) },
    { name: 'Barbell Row', sets: _S(10, 50, 3) }, { name: 'Face Pull', sets: _S(15, 20, 3) }] },
  { id: 'starter_legs', adAnahtar: 'sablon.bacak', exercises: [
    { name: 'Squat', sets: _S(8, 70, 4) }, { name: 'Leg Press', sets: _S(12, 120, 3) },
    { name: 'Romanian Deadlift', sets: _S(10, 50, 3) }, { name: 'Plank (sn)', sets: _S(45, 0, 3) }] },
];
const _odSablonAd = t => (t.adAnahtar ? fT(t.adAnahtar) : t.name);
const _odHazirSlug = id => id.slice(8).replace(/[^a-z0-9-]/g, '-');   // 'starter_chest' → 'chest'

const _od = { gun: null, hedef: null, ad: null, ex: [], onceki: {}, enIyi: {}, sonYapilma: {}, sablon: [], aktif: null,
  liste: false, sablonlar: false, bosBasla: false, dinlen: null, saat: null, yuklendi: false, sec: null, onizle: null,
  tekrar: null, baslangic: null, bitis: null, sonuc: null, isaret: new Set(), kapandi: false, yeni: { set: 3, tk: 10, kg: 0 },
  duzen: null, durum: '', hata: false, svDoldu: false };

const _odBugunMu = () => !_od.gun || _od.gun === fsTodayStr();
const _odGecerliHedef = t => /^\d{4}-\d{2}-\d{2}$/.test(t || '') && t < fsTodayStr();
const _odTarihAd = t => new Date(t + 'T12:00:00').toLocaleDateString(fYerel(), { day: 'numeric', month: 'long', weekday: 'long' });
function _odGunSifirla() {
  Object.assign(_od, { ad: null, ex: [], onceki: {}, enIyi: {}, aktif: null, liste: false, sablonlar: false, bosBasla: false, sec: null,
    onizle: null, tekrar: null, baslangic: null, bitis: null, sonuc: null, duzen: null, yuklendi: false, isaret: new Set() });
}
function odakGunAc(tarih) { _od.hedef = _odGecerliHedef(tarih) ? tarih : null; _odGunSifirla(); fstripTab('wkt'); }
function odakBugunDon() { _od.hedef = null; _odGunSifirla(); odakYukle(); }

function _odAralik(ad) {
  const k = String(ad || '').toLowerCase();
  for (const t of [..._od.sablon, ...FW_STARTER_TEMPLATES]) for (const e of t.exercises || []) if (e.aralik && String(e.name).toLowerCase() === k) return String(e.aralik);
  return '';
}
// İki dokunuşlu silme: ilk dokunuş "ONAYLA · SİL", 3 sn içinde ikincisi siler (confirm() yok).
function _odOnayIste(btn, metin) {
  if (btn.classList.contains('onay')) return true;
  document.querySelectorAll('#fstrip-pane-wkt .onay').forEach(x => { x.classList.remove('onay'); if (x.dataset.eski) x.textContent = x.dataset.eski; });
  btn.dataset.eski = btn.textContent; btn.classList.add('onay'); btn.textContent = metin || fT('ant.onayla-sil');
  clearTimeout(btn._onay);
  btn._onay = setTimeout(() => { btn.classList.remove('onay'); btn.textContent = btn.dataset.eski; }, 3000);
  return false;
}
function _odSablonListe() {
  const kopya = Object.fromEntries(_od.sablon.filter(t => t.hazir_slug).map(t => [t.hazir_slug, t]));
  return [...FW_STARTER_TEMPLATES.map(h => kopya[_odHazirSlug(h.id)] || h), ..._od.sablon.filter(t => !t.hazir_slug)];
}
const _odSablonBul = id => [...FW_STARTER_TEMPLATES, ..._od.sablon].find(x => x.id === id);
function _odSonMetin(t) {
  const iso = _od.sonYapilma[t.id];
  if (!iso) return fT('ant.henuz-yok');
  const n = _gFark(_od.gun, iso);
  return n <= 0 ? fT('besl.bugun').toLowerCase() : n === 1 ? fT('besl.dun').toLowerCase() : fT('ant.gun-once', { n });
}
function _odDinlenSn() { try { return +localStorage.getItem('yuki_dinlenme_sn') || 90; } catch { return 90; } }
function _odDinlenKaydet(sn) { try { localStorage.setItem('yuki_dinlenme_sn', String(sn)); } catch {} }
function _odSure(ms) {
  const t = Math.max(0, Math.round(ms / 1000)), h = Math.floor(t / 3600), m = Math.floor(t % 3600 / 60), s = t % 60;
  return h ? `${h}:${String(m).padStart(2, '0')}:${String(s).padStart(2, '0')}` : `${String(m).padStart(2, '0')}:${String(s).padStart(2, '0')}`;
}
function _odDk(ms) { const dk = Math.max(0, Math.floor(ms / 60000)); return dk >= 60 ? fT('ant.sa-dk', { sa: Math.floor(dk / 60), dk: dk % 60 }) : fT('ant.dk', { dk }); }

const _odSetOku = x => ({ id: x.id || null, reps: +x.reps, weight: +x.weight, completed: !!x.completed, girildi: x.girildi == null ? null : x.girildi,
  drops: fsDroplar(x).map(d => ({ kg: +d.kg || 0, tekrar: +d.tekrar || 0 })) });
function _odSetYaz(ad, x) {
  if (fsSureliMi(ad)) return fsSureYaz(x.reps) + (+x.weight ? ` +${fsKg(x.weight)}kg` : '');
  const n = fsDroplar(x).length;
  return `${fsKg(x.weight)}×${x.reps}${n ? ` <small class="od-dropek">+${n}D</small>` : ''}`;
}
function _odSetAria(ad, x) {
  if (fsSureliMi(ad)) return fT('ant.aria-sure', { sure: fsSureYaz(x.reps) }) + (+x.weight ? ', ' + fT('ant.aria-ek', { kg: fsKg(x.weight) }) : '');
  const n = fsDroplar(x).length;
  return `${fsKg(x.weight)} kg × ${x.reps}${n ? ', ' + fT('ant.aria-drop', { n }) : ''}`;
}
const _odDropOner = x => { const ds = fsDroplar(x), son = ds.length ? ds[ds.length - 1].kg : x.weight; return { kg: Math.max(0, Math.round(son * 0.8 / 2.5) * 2.5), tekrar: x.reps }; };
function _odDroplarHtml(e, x) {
  if (fsSureliMi(e.name)) return '';
  const ds = fsDroplar(x);
  return `<div class="od-droplar" aria-label="${fT('ant.droplar')}">${ds.map((d, k) => `<div class="od-dz-set od-drop"><span class="hud">DROP ${k + 1}</span>
      <label><input data-drop="kg:${k}" value="${fsKg(d.kg)}" inputmode="decimal" aria-label="${fT('ant.drop-kg', { n: k + 1 })}"><span>kg</span></label>
      <label><input data-drop="tk:${k}" value="${d.tekrar}" inputmode="numeric" aria-label="${fT('ant.drop-tk', { n: k + 1 })}"><span>${fT('ant.tekrar-k')}</span></label>
      <button type="button" class="od-dz-x" data-dropsil="${k}" aria-label="${fT('ant.drop-sil', { n: k + 1 })}">×</button></div>`).join('')}
    <button type="button" class="od-ikinci od-drop-ekle" data-dropekle="1"${ds.length < FS_DROP_EN_COK ? '' : ' disabled'}>DROP +</button></div>`;
}
const _odSayac = (ad, alan, deger, id, adim, birim) => `<div class="od-sayac${alan === 'sn' ? ' sure' : ''}"><small>${ad}</small>
  <input ${id} inputmode="${alan === 'kg' ? 'decimal' : alan === 'sn' ? 'text' : 'numeric'}" value="${deger}" aria-label="${ad}"${alan === 'sn' ? ' autocomplete="off" spellcheck="false"' : ''}>
  <div class="od-pm"><button type="button" data-deg="${alan}:-${adim}" aria-label="${fT('ant.azalt', { n: String(adim), b: birim })}">−${fsKg(adim)}</button><button type="button" data-deg="${alan}:${adim}" aria-label="${fT('ant.artir', { n: String(adim), b: birim })}">+${fsKg(adim)}</button></div></div>`;
function _odOlcuHtml(e, x, kimlik) {
  const kg = kimlik === 'id' ? 'id="od-kg"' : 'data-setal="kg"', tk = kimlik === 'id' ? 'id="od-tk"' : 'data-setal="tk"';
  if (fsSureliMi(e.name)) return _odSayac(fT('ant.sure'), 'sn', fsSureYaz(x.reps), tk, 15, fT('ortak.sn')) + _odSayac(fT('ant.ek-kilo'), 'kg', fsKg(x.weight), kg, 2.5, 'kg');
  return _odSayac(fT('ant.kilo'), 'kg', fsKg(x.weight), kg, 2.5, 'kg') + _odSayac(fT('ant.tekrar'), 'tk', x.reps, tk, 1, fT('ant.tekrar-k'));
}

async function odakYukle() {
  if (!_odGecerliHedef(_od.hedef)) _od.hedef = null;
  _od.gun = _od.hedef || fsTodayStr();
  const [w, sab] = await Promise.all([fsGet('/workouts?date=' + _od.gun), fsGet('/templates')]);
  _od.hata = !w;
  _od.ad = (w && w.notes) || null;
  _od.baslangic = w && w.baslangic ? Date.parse(w.baslangic) : null;
  _od.bitis = (w && w.bitis) || null;
  _od.ex = ((w && w.exercises) || []).map(e => ({ id: e.id, name: e.name, sablon_id: e.sablon_id || null, sets: (e.sets || []).map(_odSetOku) }));
  _od.sablon = (sab || []).map(t => ({ id: t.id, name: t.name, hazir_slug: t.hazir_slug || null, son_yapilma: t.son_yapilma || null, exercises: t.exercises || [] }));
  const adlar = [...new Set(_od.ex.map(e => e.name))], q = adlar.map(a => '&adlar=' + encodeURIComponent(a)).join('');
  const [onc, eni, son] = await Promise.all([
    adlar.length ? fsGet('/workouts/onceki?once=' + _od.gun + q) : null,
    adlar.length ? fsGet('/workouts/en-iyi?once=' + _od.gun + q) : null,
    fsGet('/templates/son-yapilma?' + FW_STARTER_TEMPLATES.map(t => 'hazir=' + _odHazirSlug(t.id)).join('&'))]);
  _od.onceki = onc || {}; _od.enIyi = eni || {};
  _od.sonYapilma = Object.fromEntries(_od.sablon.map(t => [t.id, t.son_yapilma]));
  for (const t of FW_STARTER_TEMPLATES) _od.sonYapilma[t.id] = (son || {})['hazir-' + _odHazirSlug(t.id)] || null;
  if (!_od.aktif || !_odSet(_od.aktif)) _od.aktif = _odSiradaki() || _odSon();
  try { _od.dinlen = JSON.parse(sessionStorage.getItem('yuki_od_dinlen') || 'null'); } catch { _od.dinlen = null; }
  _od.yuklendi = true;
  odakCiz();
  if (!_od.saat) _od.saat = setInterval(_odTik, 250);
}

const _odSet = a => a && _od.ex[a.e] && _od.ex[a.e].sets[a.s];
function _odSiradaki(sonra) {
  const sira = [];
  _od.ex.forEach((e, ei) => e.sets.forEach((x, si) => sira.push({ e: ei, s: si, ok: fsYapildi(x) })));
  const bas = sonra ? sira.findIndex(x => x.e === sonra.e && x.s === sonra.s) + 1 : 0;
  const n = sira.slice(bas).find(x => !x.ok) || sira.find(x => !x.ok);
  return n ? { e: n.e, s: n.s } : null;
}
function _odSon() { for (let e = _od.ex.length - 1; e >= 0; e--) if (_od.ex[e].sets.length) return { e, s: _od.ex[e].sets.length - 1 }; return null; }
function _odToplam() {
  let set = 0, bit = 0, ton = 0;
  _od.ex.forEach(e => e.sets.forEach(x => { set++; if (fsYapildi(x)) { bit++; ton += fsSetTonaj(e.name, x); } }));
  return { set, bit, ton };
}
function _odDokun(x) { x.dokun = true; x.geri = false; if (x.girildi == null) x.girildi = 'yerel'; if (!_od.baslangic) _od.baslangic = Date.now(); }
function _odGeriAl(x) { x.completed = false; x.girildi = null; x.dokun = false; x.geri = true; }

let _odYaziliyor = Promise.resolve(), _odYazZaman = null, _odYazEx = null;
async function _odSetleriYaz(ei) {
  const e = _od.ex[ei];
  if (!e) return false;
  const gonder = e.sets.map(x => ({ ...(x.id ? { id: x.id } : {}), reps: x.reps, weight: x.weight, completed: x.completed, drops: fsDroplar(x),
    ...(x.dokun ? { dokunuldu: true } : {}), ...(x.geri ? { girildi: null } : {}) }));
  e.sets.forEach(x => { x.dokun = false; x.geri = false; });
  const is = fsApiPut(`/workouts/exercise/${e.id}/sets`, { sets: gonder });
  _odYaziliyor = is;
  const r = await is;
  if (!r) { _od.durum = fT('ortak.kaydedilemedi'); odakCiz(); return false; }
  (r.sets || []).forEach((s, i) => { const x = e.sets[i]; if (x && !x.dokun && !x.geri) { x.id = s.id; x.girildi = s.girildi == null ? null : s.girildi; } });
  return true;
}
function _odGecikmeliYaz(ei) {
  if (_odYazEx !== null && _odYazEx !== ei) { clearTimeout(_odYazZaman); _odSetleriYaz(_odYazEx); }
  _odYazEx = ei; clearTimeout(_odYazZaman);
  _odYazZaman = setTimeout(() => { _odYazEx = null; _odSetleriYaz(ei); }, 800);
}
async function _odBekleyeniYaz() {
  if (_odYazEx !== null) { clearTimeout(_odYazZaman); const ei = _odYazEx; _odYazEx = null; await _odSetleriYaz(ei); }
  await _odYaziliyor;
}
window.addEventListener('pagehide', () => { if (_odYazEx !== null) { clearTimeout(_odYazZaman); _odSetleriYaz(_odYazEx); } });

function odakCiz() {
  const T = _odToplam(), var_ = _od.ex.length > 0;
  const ts = document.getElementById('od-tarih');
  if (ts) { ts.hidden = _odBugunMu(); if (!ts.hidden) document.getElementById('od-tarih-ad').textContent = _odTarihAd(_od.gun); }
  document.getElementById('od-ad').textContent = _od.ad || fT('ant.antrenman');
  document.getElementById('od-set').textContent = `${T.bit}/${T.set}`;
  document.getElementById('od-ton').textContent = fsKg(T.ton);
  _odSureCiz();
  const yuzde = T.set ? Math.round(T.bit * 100 / T.set) : 0, z = document.getElementById('od-zincir');
  z.firstElementChild.style.width = yuzde + '%'; z.setAttribute('aria-valuenow', yuzde);
  document.getElementById('od-ozet').hidden = !var_ || !!_od.sonuc;
  document.getElementById('od-gun-bitir').textContent = _od.bitis ? fT('ant.bitis-ozeti') : fT('ant.bitir');
  const sahne = document.getElementById('od-sahne'), sonraki = document.getElementById('od-sonraki');
  const durum = `<div class="od-durum" role="status">${fsKac(_od.durum)}</div>`;
  _od.durum = '';
  const onz = _od.onizle && _odSablonBul(_od.onizle);
  const kip = _od.sonuc ? null : (_od.duzen || onz || _od.tekrar || _od.sablonlar || (!var_ && !_od.bosBasla)) ? 'sablon' : (_od.liste || !var_) ? 'liste' : 'odak';
  for (const b of document.querySelectorAll('#od-kipler [data-kip]')) {
    b.setAttribute('aria-pressed', String(b.dataset.kip === kip));
    b.disabled = b.dataset.kip === 'odak' ? !var_ : b.dataset.kip === 'liste' ? !var_ && !_od.bosBasla : false;
  }
  sonraki.innerHTML = '';
  if (_od.sonuc) { sahne.innerHTML = _odBitisHtml() + durum; return; }
  if (_od.duzen) { sahne.innerHTML = _odDuzenHtml() + durum; return; }
  if (_od.tekrar) { sahne.innerHTML = _odTekrarHtml() + durum; return; }
  if (onz) { sahne.innerHTML = _odOnizleHtml(onz) + durum; return; }
  if (kip === 'sablon') { sahne.innerHTML = _odSablonlarHtml() + durum; return; }
  if (kip === 'liste') { sahne.innerHTML = _odListeHtml() + durum; return; }
  sahne.innerHTML = _odOdakHtml() + durum;
  const a = _od.aktif, n = a && _odSiradaki(a);
  if (a && _od.ex[a.e] && n) {
    const ne = n.e !== a.e ? _od.ex[n.e] : null;
    sonraki.innerHTML = `<span class="hud">${fT('ant.sonraki')}</span> <b>${ne ? fsKac(ne.name) + ' · ' : ''}${fT('ant.set-n', { n: n.s + 1 })} · ${_odSetYaz(_od.ex[n.e].name, _od.ex[n.e].sets[n.s])}</b>`;
  }
}

function _odSablonlarHtml() {
  const tum = _odSablonListe(), bos = !_od.ex.length;
  const setSay = t => (t.exercises || []).reduce((n, e) => n + (e.sets || []).length, 0);
  return `${bos ? `<p class="od-kip-not">${fT('ant.kip-not')}</p>` : ''}
    <section class="od-kart"><h3 class="od-bos-bas">${_od.hata ? fT('ant.alinamadi') : bos ? (_odBugunMu() ? fT('ant.bugun-ne') : fT('ant.o-gun-ne', { gun: fsKac(_odTarihAd(_od.gun)) })) : fT('ant.sablonlar')}</h3>
    <p class="od-acik">${bos ? fT('ant.sablon-ipucu-bos') : fT('ant.sablon-ipucu')}</p>
    <div class="od-sablonlar">${tum.map(t => { const kendi = !t.id.startsWith('starter_') && !t.hazir_slug;
      return `<button type="button" class="od-sablon${kendi ? ' sil-var' : ''}${t.hazir_slug ? ' kopya' : ''}" data-sablon="${fsKac(t.id)}"><b>${fsKac(_odSablonAd(t))}</b><small>${fT('ant.sablon-say', { e: t.exercises.length, s: setSay(t) })}${t.hazir_slug ? ' · <i>' + fT('ant.duzenlendi') + '</i>' : ''}</small>${kendi ? `<span class="sil" data-sablon-sil="${fsKac(t.id)}">${fT('ortak.sil')}</span>` : ''}</button>`; }).join('')}
    ${bos ? `<button type="button" class="od-sablon bos-basla" data-bosbasla="1"><b>${fT('ant.bos-basla')}</b><small>${fT('ant.bos-basla-not')}</small></button>` : ''}</div></section>${bos ? '' : _odKaydetHtml()}`;
}
function _odKaydetHtml() {
  return `<details class="od-katla"><summary>${fT('ant.sablon-yap')}</summary><p>${fT('ant.sablon-yap-not', { n: _od.ex.length })}</p>
    <form class="od-kaydet" id="od-kaydet-form"><input id="od-sablon-ad" placeholder="${fT('ant.sablon-ad-ph')}" aria-label="${fT('ant.sablon-ad')}" maxlength="80"><button class="od-hap" type="submit">${fT('ortak.kaydet')}</button></form></details>`;
}
function _odOnizleHtml(t) {
  return `<section class="od-kart od-onizle"><p class="od-baslik2">${fT('ant.onizle-ust')}</p><h3>${fsKac(_odSablonAd(t))}</h3>
    <p class="od-acik">${fT('ant.son')}: <b>${_odSonMetin(t)}</b></p>
    <ol>${t.exercises.map(e => { const ss = e.sets || [], s0 = ss[0] || { reps: 0, weight: 0 };
      return `<li><b>${fsKac(e.name)}</b><span>${ss.length} × ${e.aralik ? `<em>${fsKac(e.aralik)}</em>` : fsSureliMi(e.name) ? fsSureYaz(s0.reps) : s0.reps}${s0.weight ? ` · ${fsKg(s0.weight)} kg` : ''}</span></li>`; }).join('')}</ol>
    <p class="od-acik">${fT('ant.plan-not')}</p>
    <div class="od-dugmeler"><button type="button" class="od-ikinci" data-vazgec="1">${fT('ortak.vazgec')}</button><button type="button" class="od-ana" data-sablonyukle="${fsKac(t.id)}">${_odBugunMu() ? (_od.ex.length ? fT('ant.bugune-ekle') : fT('ant.bugune-yukle')) : (_od.ex.length ? fT('ant.o-gune-ekle') : fT('ant.o-gune-yukle'))}</button></div>
    <div class="od-dugmeler alt"><button type="button" class="od-ikinci" data-dzac="${fsKac(t.id)}">${fT('ant.duzenle')}</button>${t.hazir_slug ? `<button type="button" class="od-ikinci" data-dzgeri="${fsKac(t.id)}">${fT('ant.hazir-geri')}</button>` : ''}</div></section>`;
}
function _odDuzenAc(id) {
  const t = _odSablonBul(id);
  if (!t) return;
  _od.duzen = { id, slug: id.startsWith('starter_') ? _odHazirSlug(id) : null, kopya: !!t.hazir_slug, name: _odSablonAd(t), yeniAd: '', hata: '',
    exercises: (t.exercises || []).map(e => ({ name: e.name, aralik: e.aralik ? String(e.aralik) : '', sets: (e.sets || []).map(x => ({ reps: +x.reps || 0, weight: +x.weight || 0 })) })) };
  _od.onizle = null; odakCiz();
}
function _odDuzenHtml() {
  const D = _od.duzen, n = D.exercises.length;
  return `<section class="od-kart od-duzen"><p class="od-baslik2">${D.slug ? fT('ant.dz-hazir') : D.kopya ? fT('ant.dz-kopya') : fT('ant.dz')}</p>
    <label class="od-dz-ad"><span class="hud">${fT('ant.ad')}</span><input data-dz="ad" value="${fsKac(D.name)}" maxlength="80" aria-label="${fT('ant.sablon-ad')}"></label>
    <ol class="od-dz-liste">${D.exercises.map((e, i) => `<li class="od-dz-ex">
      <div class="od-dz-bas"><b>${fsKac(e.name)}</b>
        <button type="button" class="od-hap" data-dzsira="${i}:-1" aria-label="${fT('ant.yukari', { ad: fsKac(e.name) })}"${i ? '' : ' disabled'}>↑</button>
        <button type="button" class="od-hap" data-dzsira="${i}:1" aria-label="${fT('ant.asagi', { ad: fsKac(e.name) })}"${i < n - 1 ? '' : ' disabled'}>↓</button>
        <button type="button" class="od-sil" data-dzexsil="${i}" aria-label="${fT('ant.cikar-aria', { ad: fsKac(e.name) })}">${fT('ant.cikar')}</button></div>
      <label class="od-dz-aralik"><span class="hud">${fT('ant.aralik')}</span><input data-dz="aralik:${i}" value="${fsKac(e.aralik)}" placeholder="8-10" inputmode="numeric" maxlength="7"></label>
      <div class="od-dz-setler">${e.sets.map((x, j) => `<div class="od-dz-set"><span class="hud">SET ${j + 1}</span>
        <label><input data-dz="kg:${i}:${j}" value="${fsKg(x.weight)}" inputmode="decimal" aria-label="${fT('ant.dz-kg', { ad: fsKac(e.name), n: j + 1 })}"><span>kg</span></label>
        <label><input data-dz="tk:${i}:${j}" value="${x.reps}" inputmode="numeric" aria-label="${fT('ant.dz-tk', { ad: fsKac(e.name), n: j + 1 })}"><span>${fsSureliMi(e.name) ? fT('ortak.sn') : fT('ant.tekrar-k')}</span></label>
        <button type="button" class="od-dz-x" data-dzsetsil="${i}:${j}" aria-label="${fT('ant.dz-set-sil', { n: j + 1 })}"${e.sets.length > 1 ? '' : ' disabled'}>×</button></div>`).join('')}</div>
      <button type="button" class="od-ikinci" data-dzsetekle="${i}"${e.sets.length < 20 ? '' : ' disabled'}>+ SET</button></li>`).join('')}</ol>
    <div class="od-dz-ekle"><input data-dz="yeniad" value="${fsKac(D.yeniAd)}" placeholder="${fT('ant.egz-ad-ph')}" maxlength="120" aria-label="${fT('ant.yeni-egz')}"><button type="button" class="od-hap" data-dzekle="1"${n < 30 ? '' : ' disabled'}>${fT('ant.egz-ekle')}</button></div>
    ${D.hata ? `<p class="od-dz-hata" role="alert">${fsKac(D.hata)}</p>` : ''}
    <div class="od-dugmeler"><button type="button" class="od-ikinci" data-dzvazgec="1">${fT('ortak.vazgec')}</button><button type="button" class="od-ana" data-dzkaydet="1">${fT('ortak.kaydet')}</button></div></section>`;
}
async function _odDuzenKaydet() {
  const D = _od.duzen, ad = D.name.trim();
  D.hata = !ad ? fT('ant.dz-ad-yok') : !D.exercises.length ? fT('ant.dz-egz-yok')
    : D.exercises.find(e => e.aralik.trim() && !/^\d{1,3}(-\d{1,3})?$/.test(e.aralik.trim())) ? fT('ant.dz-aralik') : '';
  if (D.hata) return odakCiz();
  const govde = { name: ad, exercises: D.exercises.map(e => ({ name: e.name, ...(e.aralik.trim() ? { aralik: e.aralik.trim() } : {}), sets: e.sets })) };
  const r = await fsIstek('PUT', `/templates/${D.slug ? 'hazir-' + D.slug : encodeURIComponent(D.id)}`, govde);
  if (!r.ok) { const d = r.json && r.json.detail; D.hata = typeof d === 'string' ? d : fT('ortak.baglanti'); return odakCiz(); }
  _od.duzen = null; await odakYukle();
  _od.onizle = r.json.id; _od.durum = fT('ant.kaydedildi', { ad }); odakCiz();
}
function _odTekrarHtml() {
  const t = _odSablonBul(_od.tekrar.id) || { name: '', exercises: [] };
  return `<section class="od-kart od-onizle od-tekrar"><p class="od-baslik2">${fT('ant.sablon')}</p><h3>${fsKac(_odSablonAd(t))}</h3>
    <div class="od-uyari" role="alert"><b>${fT(_odBugunMu() ? 'ant.zaten-bugun' : 'ant.zaten-o-gun', { n: _od.tekrar.zaten })}</b><span>${fT('ant.zaten-not', { n: t.exercises.length })}</span></div>
    <div class="od-dugmeler"><button type="button" class="od-ana" data-odakdon="1">${fT('ant.odaga-don')}</button></div>
    <div class="od-dugmeler"><button type="button" class="od-ikinci" data-vazgec="1">${fT('ortak.vazgec')}</button><button type="button" class="od-ikinci" data-sablonyukle="${fsKac(_od.tekrar.id)}" data-yine="1">${fT('ant.yine-ekle')}</button></div></section>`;
}

function _odOdakHtml() {
  const a = _od.aktif, x = _odSet(a);
  if (!x) return '';
  const e = _od.ex[a.e], ar = _odAralik(e.name), yap = fsYapildi(x), hepsi = !_odSiradaki();
  const on = _od.onceki[e.name.toLowerCase()] || {}, once = on.sets || [], o = once[a.s] || once[once.length - 1];
  const gun = on.tarih ? _gFark(_od.gun, on.tarih) : null, en = _od.enIyi[e.name.toLowerCase()];
  const durak = e.sets.map((s, i) => { const y = fsYapildi(s);
    return `<button type="button" class="od-durak ${y ? 'yapildi' : 'plan'}${i === a.s ? ' su' : ''}" data-durak="${a.e}:${i}" aria-label="${fT('ant.set-n', { n: i + 1 })}: ${_odSetAria(e.name, s)}, ${y ? fT('ant.yapildi-k') : fT('ant.plan-k')}"${i === a.s ? ' aria-current="step"' : ''}>${y ? '✓ ' : ''}${_odSetYaz(e.name, s)}</button>`; }).join('');
  const etiket = yap ? `<span class="od-etiket iyi">✓ ${fT('ant.yapildi')}</span>` : `<span class="od-etiket plan">${e.sablon_id ? fT('ant.plan-sablondan') : fT('ant.plan')}</span>`;
  const ana = hepsi && yap ? `<button type="button" class="od-ana" data-gunbitir="1">${fT('ant.hepsi-bitti')}</button>`
    : `<button type="button" id="od-bitir" class="od-ana${x.completed ? ' geri' : ''}">${x.completed ? fT('ant.set-geri', { n: a.s + 1 }) : fT('ant.set-bitti', { n: a.s + 1 })}</button>`;
  return `<section class="od-kart od-odak" aria-label="${fT('ant.odak')}">
    <div class="od-egz-gez"><button type="button" data-egz="-1" aria-label="${fT('ant.onceki-egz')}"${a.e ? '' : ' disabled'}>‹</button>
      <div class="ad"><b class="od-exad">${fsKac(e.name)}</b><small>${a.e + 1} / ${_od.ex.length}${ar ? ` · <span class="hedef">${fT('ant.hedef-tekrar', { ar: fsKac(ar) })}</span>` : ''}</small></div>
      <button type="button" data-egz="1" aria-label="${fT('ant.sonraki-egz')}"${a.e < _od.ex.length - 1 ? '' : ' disabled'}>›</button></div>
    <div class="od-duraklar" aria-label="${fT('ant.setler')}">${durak}</div>
    ${_odHalkaHtml()}
    <div class="od-bas-satir">${etiket}<span class="od-etiket">${fT('ant.set-n', { n: a.s + 1 })} / ${e.sets.length}</span></div>
    <div class="od-olcu${yap ? ' ok' : ''}">${_odOlcuHtml(e, x, 'id')}</div>
    <div class="od-gecen">${o ? `<span>${fT('ant.gecen-sefer')} <b>${_odSetYaz(e.name, o).replace('×', ' × ')}</b>${gun ? ' · ' + fT('ant.gun-once', { n: gun }) : ''}</span>` : `<span>${fT('ant.ilk-kez')}</span>`}${en ? `<span class="od-eniyi">${fsSureliMi(e.name) ? fT('ant.en-uzun') : fT('ant.en-iyi')} <b>${fsSureliMi(e.name) ? fsSureYaz(en.tekrar) : `${fsKg(en.kg)} × ${en.tekrar}`}</b></span>` : ''}</div>
    ${ana}
    ${_odDroplarHtml(e, x)}
    ${_od.dinlen ? '' : `<div class="od-dinlen-ayar">${fT('ant.dinlenme')} <b>${_odSure(_odDinlenSn() * 1000).replace(/^0/, '')}</b><button type="button" class="od-hap" data-dinayar="-15">−15</button><button type="button" class="od-hap" data-dinayar="15">+15</button></div>`}
  </section>`;
}

function _odListeHtml() {
  const sc = _od.sec && _odSet(_od.sec) ? _od.sec : null;
  const duz = ei => { if (!sc || sc.e !== ei) return ''; const x = _odSet(sc);
    return `<div class="od-duz" aria-label="${fT('ant.set-duzenle', { n: sc.s + 1 })}"><div class="od-olcu">${_odOlcuHtml(_od.ex[ei], x, 'setal')}</div>${_odDroplarHtml(_od.ex[ei], x)}
      <div class="od-dugmeler"><button type="button" class="od-ikinci" data-setsil="1">${fT('ant.seti-sil')}</button><button type="button" class="od-ana${x.completed ? ' geri' : ''}" data-tamam="1">${x.completed ? fT('ant.set-geri', { n: sc.s + 1 }) : fT('ant.set-bitti-kisa', { n: sc.s + 1 })}</button></div></div>`; };
  const Y = _od.yeni, adlar = [...new Set([..._od.sablon, ...FW_STARTER_TEMPLATES].flatMap(t => (t.exercises || []).map(e => e.name)))];
  const say = (k, ad, v, adim) => `<label class="od-say"><small>${ad}</small><div><button type="button" data-yeni="${k}:-${adim}" aria-label="${fT('ant.azalt-ad', { ad })}">−</button><input data-yenial="${k}" inputmode="decimal" value="${fsKg(v)}" aria-label="${ad}"><button type="button" data-yeni="${k}:${adim}" aria-label="${fT('ant.artir-ad', { ad })}">+</button></div></label>`;
  return `<div class="od-liste"><p class="od-acik">${_od.ex.length ? fT('ant.liste-ipucu') : fT('ant.liste-bos')}</p>
    ${_od.ex.map((e, ei) => { const ar = _odAralik(e.name);
      return `<section class="od-kart od-lex"><div class="bas"><b>${fsKac(e.name)}</b><small>${fT('ant.yapildi-say', { n: e.sets.filter(fsYapildi).length, m: e.sets.length })}</small><button type="button" class="od-sil" data-exsil="${ei}" aria-label="${fT('ant.egz-sil', { ad: fsKac(e.name) })}">${fT('ortak.sil')}</button></div>${ar ? `<div class="hedef">${fT('ant.hedef-tekrar', { ar: fsKac(ar) })}</div>` : ''}
      <div class="setler">${e.sets.map((x, si) => { const y = fsYapildi(x), s = sc && sc.e === ei && sc.s === si;
        return `<button type="button" data-sec="${ei}:${si}" aria-pressed="${!!s}" class="od-set ${y ? 'yapildi' : 'plan'}${s ? ' sec' : ''}" aria-label="${fT('ant.set-n', { n: si + 1 })}: ${_odSetAria(e.name, x)}, ${y ? fT('ant.yapildi-k') : fT('ant.plan-k')}">${y ? '✓ ' : ''}${_odSetYaz(e.name, x)}</button>`; }).join('')}<button type="button" class="arti" data-setekle="${ei}">${fT('ant.set-ekle')}</button></div>${duz(ei)}</section>`; }).join('')}
    <section class="od-kart"><form class="od-ekle" id="od-ekle-form" autocomplete="off"><p class="od-baslik2">${fT('ant.egz-ekle-bas')}</p>
      <input id="od-ekle-inp" list="od-adlar" placeholder="${fT('ant.egz-ad-ph2')}" aria-label="${fT('ant.yeni-egz')}" enterkeyhint="done"><datalist id="od-adlar">${adlar.map(a => `<option value="${fsKac(a)}">`).join('')}</datalist>
      <div class="say">${say('set', 'SET', Y.set, 1)}${say('tk', fT('ant.tekrar'), Y.tk, 1)}${say('kg', 'KG', Y.kg, 2.5)}</div>
      <button class="od-ana" type="submit">${fT('ant.listeye-ekle')}</button></form></section></div>`;
}

function _odBitisHtml() {
  const r = _od.sonuc, d = r.dokunulmamis || [], liste = !_od.kapandi && d.length;
  return `<section class="od-kart altin od-bitis" aria-label="${fT('ant.bitti-aria')}"><p class="od-baslik2">${fT('ant.tamam-ust')}${_od.ad ? ' · ' + fsKac(_od.ad) : ''}</p>
    <div class="od-xp"><span class="od-xp-buyuk" id="od-xp-gun">+${fsKg(Math.round(r.xp_gun || 0))}<small> XP</small></span>${_odBitisSv(r)}</div>
    <div class="od-ozet3"><div><b id="od-bitti-set">${r.yapilan_set}</b><small>${fT('ant.set-yapildi')}</small></div><div><b>${fsKg(r.tonaj || 0)}</b><small>${fT('ant.kg-tonaj')}</small></div><div><b>${r.sure_sn != null ? _odSure(r.sure_sn * 1000) : '—'}</b><small>${fT('ant.sure-k')}</small></div></div>
    ${(r.yeni_pr || []).map(p => `<div class="od-rekor"><b>${fsKac(String(p.metin).replace(/^Bildirim:\s*/, ''))}</b></div>`).join('')}
    ${_odBitisGorev()}</section>
    ${liste ? `<section class="od-kart od-dokunulmamis"><p class="od-baslik2">${fT('ant.dokunulmamis', { n: d.length })}</p><p class="od-acik">${fT('ant.dokunulmamis-not')}</p>
      ${d.map(s => `<button type="button" role="checkbox" aria-checked="${_od.isaret.has(s.id)}" class="od-isaret${_od.isaret.has(s.id) ? ' secili' : ''}" data-isaret="${fsKac(s.id)}"><i aria-hidden="true"></i><span class="ad">${fsKac(s.egzersiz)}</span><span>${_odSetYaz(s.egzersiz, s).replace('×', ' × ')}</span></button>`).join('')}
      <div class="od-dugmeler yapiskan"><button type="button" class="od-ikinci" data-gunac="1">${fT('ant.geri-don')}</button><button type="button" class="od-ana" data-gunkaydet="1">${_od.isaret.size ? fT('ant.say-kapat', { n: _od.isaret.size }) : fT('ant.kaydet-kapat')}</button></div></section>`
    : `<div class="od-dugmeler"><button type="button" class="od-ikinci" data-gunac="1">${fT('ant.geri-don')}</button></div>`}
    ${_od.ex.length ? _odKaydetHtml() : ''}`;
}
const _odDurum = () => (typeof _fit !== 'undefined' && _fit.durum ? _fit.durum : null);
function _odSvOran(d, eksi) { const son = d.xp_sonraki || 1, ic = Math.max(0, d.xp_seviye_ici || 0); return Math.max(0, Math.min(100, (eksi > ic ? 0 : ic - (eksi || 0)) / son * 100)); }
function _odBitisSv(r) {
  const d = _odDurum();
  if (!d || d.seviye == null) return '';
  const bas = _od.svDoldu ? _odSvOran(d) : _odSvOran(d, r.xp_gun || 0);
  return `<span class="od-sv-etiket" id="od-bitis-sv">Sv. ${d.seviye} · ${fsKg(Math.round(d.xp_seviye_ici || 0))} / ${fsKg(d.xp_sonraki || 0)}</span>
    <div class="od-ray" id="od-bitis-ray" role="progressbar" aria-label="${fT('ant.sv-ilerleme')}" aria-valuemin="0" aria-valuemax="100" aria-valuenow="${Math.round(_odSvOran(d))}"><i style="width:${bas.toFixed(1)}%"></i></div>`;
}
function _odBitisGorev() {
  const d = _odDurum(), g = d && (d.gorevler || []).find(x => x.kod === 'antrenman');
  return g ? `<p class="od-acik" id="od-bitis-gorev">${fT('ant.gorev')}: ${fsKac(g.ad)} → <b>${fsKg(g.ilerleme)} / ${fsKg(g.hedef)}</b>${g.tamam ? ' ✓' : ''}</p>` : '';
}
// Bitişin XP sahnesi: çubuk günün XP'si kadar geriden başlar, /durum tazelenince bugünkü değere dolar.
document.addEventListener('fitnes:durum', () => {
  if (!_od.sonuc || _od.svDoldu) return;
  const d = _odDurum(), ray = document.getElementById('od-bitis-ray');
  _od.svDoldu = true;
  if (!ray) { if (document.querySelector('#fstrip-pane-wkt .od-bitis')) odakCiz(); return; }
  const sv = document.getElementById('od-bitis-sv');
  if (sv) sv.textContent = `${fT('ortak.sv', { n: d.seviye })} · ${fsKg(Math.round(d.xp_seviye_ici || 0))} / ${fsKg(d.xp_sonraki || 0)}`;
  const g = document.getElementById('od-bitis-gorev'), gh = _odBitisGorev();
  if (g && gh) g.outerHTML = gh;
  const son = _odSvOran(d);
  ray.setAttribute('aria-valuenow', Math.round(son));
  requestAnimationFrame(() => requestAnimationFrame(() => { ray.firstElementChild.style.width = son.toFixed(1) + '%'; }));
});

function _odHalkaHtml() {
  return _od.dinlen ? `<div id="od-halka" class="od-dinlen" role="timer" aria-label="${fT('ant.dinlenme')}"><span class="sure">--:--</span><div class="ad"><small>${fT('ant.dinlenme-b')}</small><div class="od-ray"><i></i></div></div>
    <button type="button" class="od-hap" data-dinek="15">+15</button><button type="button" class="od-hap" data-atla="1">${fT('ant.atla')}</button></div>` : '';
}
function _odSureCiz() { const el = document.getElementById('od-sure'); if (el) el.textContent = _od.baslangic ? _odDk(Date.now() - _od.baslangic) : '—'; }
function _odTik() {
  if (typeof _currentMode !== 'undefined' && _currentMode !== 'fitness') return;
  if (!_od.yuklendi) return;
  _odSureCiz();
  const d = _od.dinlen, h = document.getElementById('od-halka');
  if (!d || !h) return;
  const kalan = d.bitis - Date.now();
  h.querySelector('.od-ray i').style.width = Math.max(0, Math.min(100, kalan * 100 / (d.toplam * 1000))) + '%';
  h.querySelector('.sure').textContent = _odSure(Math.max(0, kalan) + 999);
  if (kalan <= 0 && !h.classList.contains('bitti')) {
    h.classList.add('bitti'); h.querySelector('small').textContent = fT('ant.hazir');
    try { navigator.vibrate && navigator.vibrate([200, 100, 200]); } catch {}
    setTimeout(() => { if (_od.dinlen === d) { _odDinlenDur(); odakCiz(); } }, 2500);
  }
}
function _odDinlenBasla() { const sn = _odDinlenSn(); _od.dinlen = { bitis: Date.now() + sn * 1000, toplam: sn }; try { sessionStorage.setItem('yuki_od_dinlen', JSON.stringify(_od.dinlen)); } catch {} }
function _odDinlenDur() { _od.dinlen = null; try { sessionStorage.removeItem('yuki_od_dinlen'); } catch {} }

async function odEkle() {
  const inp = document.getElementById('od-ekle-inp'), yazi = inp.value.trim(), Y = _od.yeni;
  const m = parseFitdown(yazi) || (yazi ? { name: yazi, sets: Y.set, reps: Y.tk, weight: Y.kg } : null);
  if (!m) { _od.durum = fT('ant.egz-ad-yaz'); odakCiz(); document.getElementById('od-ekle-inp').focus(); return; }
  const sets = Array.from({ length: Math.min(m.sets, 20) }, () => ({ reps: m.reps, weight: m.weight, completed: false }));
  if (!await fsApiPost('/workouts/exercise', { name: m.name, sets, session_date: _od.gun })) { _od.durum = fT('ant.eklenemedi'); return odakCiz(); }
  await odakYukle();
}
async function _odSablonYukle(id, yine) {
  const t = _odSablonBul(id);
  if (!t) return;
  const q = `?tarih=${_od.gun}&yine=${yine ? 1 : 0}`;
  const r = id.startsWith('starter_')
    ? await fsIstek('POST', `/templates/hazir-${_odHazirSlug(id)}/yukle${q}`, { ad: _odSablonAd(t), exercises: t.exercises.map(e => ({ name: e.name, sets: (e.sets || []).map(x => ({ reps: x.reps, weight: x.weight })) })) })
    : await fsIstek('POST', `/templates/${encodeURIComponent(id)}/yukle${q}`, {});
  if (r.status === 409) { _od.tekrar = { id, zaten: (r.json && r.json.detail && r.json.detail.zaten) || 1 }; _od.onizle = null; return odakCiz(); }
  if (!r.ok) { _od.durum = fT('ant.yuklenemedi'); return odakCiz(); }
  const once = _od.ex.length;
  Object.assign(_od, { liste: false, sablonlar: false, onizle: null, tekrar: null, bosBasla: false });
  await odakYukle();
  _od.aktif = _od.ex[once] ? { e: once, s: 0 } : (_odSiradaki() || _odSon()); odakCiz();
}
async function odSablonKaydet() {
  const ad = document.getElementById('od-sablon-ad').value.trim();
  if (!ad) { _od.durum = fT('ant.dz-ad-yok'); return odakCiz(); }
  const r = await fsApiPost('/templates', { name: ad, exercises: _od.ex.map(e => ({ name: e.name, ...(_odAralik(e.name) ? { aralik: _odAralik(e.name) } : {}), sets: e.sets.map(x => ({ reps: x.reps, weight: x.weight })) })) });
  const sonuc = _od.sonuc;
  await odakYukle();
  _od.sonuc = sonuc;
  _od.durum = r ? fT('ant.sablon-oldu', { ad }) : fT('ortak.kaydedilemedi'); odakCiz();
}
async function _odGunBitir(onayla) {
  await _odBekleyeniYaz();
  const r = await fsIstek('POST', `/workouts/${_od.gun}/bitir`, { onayla: onayla || [] });
  if (!r.ok || !r.json) { _od.durum = fT('ant.bitirilemedi'); odakCiz(); return null; }
  _od.sonuc = r.json; _od.bitis = r.json.bitis || _od.bitis || 'yerel'; _od.svDoldu = false;
  _odDinlenDur();
  document.dispatchEvent(new CustomEvent('fitnes:bitti', { detail: r.json }));
  document.dispatchEvent(new Event('fitnes:antrenman-degisti'));
  return r.json;
}

document.addEventListener('submit', ev => {
  if (ev.target.id === 'od-ekle-form') { ev.preventDefault(); odEkle(); }
  else if (ev.target.id === 'od-kaydet-form') { ev.preventDefault(); odSablonKaydet(); }
});
document.addEventListener('click', async ev => {
  const t = ev.target.closest && ev.target.closest('#fstrip-pane-wkt button, #fstrip-pane-wkt .sil');
  if (!t) return;
  const d = t.dataset;
  if (d.bugunedon) return odakBugunDon();
  if (d.kip) {
    if (t.disabled) return;
    Object.assign(_od, { sablonlar: d.kip === 'sablon', liste: d.kip === 'liste', onizle: null, sec: null, tekrar: null, sonuc: null, duzen: null });
    return odakCiz();
  }
  if (t.id === 'od-gun-bitir' || d.gunbitir) { t.disabled = true; _od.isaret.clear(); _od.kapandi = false; await _odGunBitir(); t.disabled = false; return odakCiz(); }
  if (d.isaret) { _od.isaret.has(d.isaret) ? _od.isaret.delete(d.isaret) : _od.isaret.add(d.isaret); return odakCiz(); }
  if (d.gunkaydet) {
    t.disabled = true;
    if (_od.isaret.size) { const ids = [..._od.isaret]; _od.isaret.clear(); const s = await _odGunBitir(ids); if (s) { await odakYukle(); _od.sonuc = s; } }
    _od.kapandi = true; return odakCiz();
  }
  if (d.gunac) {
    t.disabled = true;
    if (_od.bitis) await fsIstek('POST', `/workouts/${_od.gun}/ac`);
    Object.assign(_od, { sonuc: null, bitis: null, kapandi: false, liste: false, sablonlar: false });
    return odakYukle();
  }
  if (d.bosbasla) { Object.assign(_od, { bosBasla: true, liste: true, sablonlar: false }); return odakCiz(); }
  if (d.odakdon) { Object.assign(_od, { tekrar: null, onizle: null, sablonlar: false, liste: false }); return odakCiz(); }
  if (d.egz) {
    const ei = Math.max(0, Math.min(_od.ex.length - 1, (_od.aktif ? _od.aktif.e : 0) + +d.egz)), si = _od.ex[ei].sets.findIndex(x => !fsYapildi(x));
    _od.aktif = { e: ei, s: si >= 0 ? si : 0 }; return odakCiz();
  }
  if (d.durak) { const [e, s] = d.durak.split(':').map(Number); _od.aktif = { e, s }; return odakCiz(); }
  if (d.sec) { const [e, s] = d.sec.split(':').map(Number); _od.sec = _od.sec && _od.sec.e === e && _od.sec.s === s ? null : { e, s }; return odakCiz(); }
  if (d.yeni) {
    const [k, adim] = d.yeni.split(':'), Y = _od.yeni;
    Y[k] = Math.max(k === 'kg' ? 0 : 1, Math.min(k === 'set' ? 20 : 999, Math.round((Y[k] + +adim) * 100) / 100));
    const inp = document.querySelector(`[data-yenial="${k}"]`); if (inp) inp.value = fsKg(Y[k]);
    return;
  }
  const hedef = _od.liste ? _od.sec : _od.aktif;
  if (d.deg) {
    const x = _odSet(hedef); if (!x) return;
    const [alan, adim] = d.deg.split(':');
    if (alan === 'kg') x.weight = Math.max(0, Math.round((x.weight + +adim) * 100) / 100); else x.reps = Math.max(0, Math.min(FS_SURE_EN_COK, x.reps + +adim));
    _odDokun(x); odakCiz(); return _odGecikmeliYaz(hedef.e);
  }
  if (d.dropekle || d.dropsil) {
    const x = _odSet(hedef); if (!x) return;
    x.drops = fsDroplar(x).slice();
    if (d.dropekle) { if (x.drops.length >= FS_DROP_EN_COK) return; x.drops.push(_odDropOner(x)); } else x.drops.splice(+d.dropsil, 1);
    _odDokun(x); odakCiz(); _odGecikmeliYaz(hedef.e);
    if (d.dropekle) { const inp = document.querySelector(`#fstrip-pane-wkt [data-drop="kg:${x.drops.length - 1}"]`); if (inp) inp.focus(); }
    return;
  }
  if (d.tamam) {
    const x = _odSet(_od.sec); if (!x) return;
    if (x.completed) _odGeriAl(x); else { x.completed = true; _odDokun(x); }
    const ei = _od.sec.e, sonraki = _od.ex[ei].sets.findIndex(s => !fsYapildi(s));
    _od.sec = x.completed ? (sonraki >= 0 ? { e: ei, s: sonraki } : null) : _od.sec;
    _od.aktif = _odSiradaki() || _odSon();
    clearTimeout(_odYazZaman); _odYazEx = null; odakCiz(); return _odSetleriYaz(ei);
  }
  if (d.setsil) {
    if (!_odOnayIste(t)) return;
    const { e: ei, s } = _od.sec; _od.ex[ei].sets.splice(s, 1); _od.sec = null; _od.aktif = _odSiradaki() || _odSon();
    odakCiz(); return _odSetleriYaz(ei);
  }
  if (t.id === 'od-bitir') {
    const a = _od.aktif, x = _odSet(a); if (!x) return;
    if (x.completed) { _odGeriAl(x); _odDinlenDur(); }
    else { x.completed = true; _odDokun(x); _odDinlenBasla(); const n = _odSiradaki(a); if (n) _od.aktif = n; else _odDinlenDur(); }
    clearTimeout(_odYazZaman); _odYazEx = null; odakCiz();
    return _odSetleriYaz(a.e);
  }
  if (d.atla) { _odDinlenDur(); return odakCiz(); }
  if (d.dinek && _od.dinlen) {
    _od.dinlen.bitis += +d.dinek * 1000; _od.dinlen.toplam = Math.max(5, _od.dinlen.toplam + +d.dinek);
    try { sessionStorage.setItem('yuki_od_dinlen', JSON.stringify(_od.dinlen)); } catch {}
    return _odTik();
  }
  if (d.dinayar) { _odDinlenKaydet(Math.min(600, Math.max(15, _odDinlenSn() + +d.dinayar))); return odakCiz(); }
  if (d.setekle) {
    const e = _od.ex[+d.setekle], son = e.sets[e.sets.length - 1] || { reps: 10, weight: 0 };
    e.sets.push({ id: null, reps: son.reps, weight: son.weight, completed: false, girildi: null, drops: [] });
    odakCiz(); return _odSetleriYaz(+d.setekle);
  }
  if (d.exsil) {
    if (!_odOnayIste(t)) return;
    await fsApiDelete('/workouts/exercise/' + _od.ex[+d.exsil].id);
    _od.aktif = null; _od.sec = null; return odakYukle();
  }
  if (d.sablonSil) {
    ev.stopPropagation();
    if (!_odOnayIste(t)) return;
    await fsApiDelete('/templates/' + encodeURIComponent(d.sablonSil)); return odakYukle();
  }
  if (d.sablon) { _od.onizle = d.sablon; _od.tekrar = null; return odakCiz(); }
  if (d.dzac) return _odDuzenAc(d.dzac);
  if (d.dzgeri) {
    if (!_odOnayIste(t, fT('ant.onayla-geri'))) return;
    const k = _od.sablon.find(x => x.id === d.dzgeri), h = k && FW_STARTER_TEMPLATES.find(x => _odHazirSlug(x.id) === k.hazir_slug);
    if (!(await fsIstek('DELETE', '/templates/' + encodeURIComponent(d.dzgeri))).ok) { _od.durum = fT('ortak.baglanti'); return odakCiz(); }
    await odakYukle(); _od.onizle = h ? h.id : null; _od.durum = h ? fT('ant.hazira-dondu', { ad: _odSablonAd(h) }) : ''; return odakCiz();
  }
  if (_od.duzen) {
    const D = _od.duzen;
    if (d.dzvazgec) { const id = D.id; _od.duzen = null; _od.onizle = id; return odakCiz(); }
    if (d.dzkaydet) { t.disabled = true; return _odDuzenKaydet(); }
    if (d.dzsira) { const [i, y] = d.dzsira.split(':').map(Number), j = i + y; if (j < 0 || j >= D.exercises.length) return;
      [D.exercises[i], D.exercises[j]] = [D.exercises[j], D.exercises[i]]; return odakCiz(); }
    if (d.dzexsil) { D.exercises.splice(+d.dzexsil, 1); return odakCiz(); }
    if (d.dzsetsil) { const [i, j] = d.dzsetsil.split(':').map(Number); if (D.exercises[i].sets.length > 1) D.exercises[i].sets.splice(j, 1); return odakCiz(); }
    if (d.dzsetekle) { const e = D.exercises[+d.dzsetekle], son = e.sets[e.sets.length - 1] || { reps: 10, weight: 0 }; if (e.sets.length < 20) e.sets.push({ ...son }); return odakCiz(); }
    if (d.dzekle) { const ad = D.yeniAd.trim(); if (!ad) { D.hata = fT('ant.egz-ad-yaz'); return odakCiz(); }
      D.exercises.push({ name: ad.slice(0, 120), aralik: '', sets: _S(10, 0, 3) }); D.yeniAd = ''; D.hata = ''; return odakCiz(); }
  }
  if (d.vazgec) { Object.assign(_od, { onizle: null, tekrar: null, duzen: null }); return odakCiz(); }
  if (d.sablonyukle) { t.disabled = true; return _odSablonYukle(d.sablonyukle, !!d.yine); }
});

document.addEventListener('change', ev => {
  const ds = ev.target.dataset || {};
  if (!ev.target.closest || !ev.target.closest('#fstrip-pane-wkt')) return;
  if (ds.yenial) { const v = parseFloat(String(ev.target.value).replace(',', '.')); if (isFinite(v) && v >= 0) _od.yeni[ds.yenial] = ds.yenial === 'kg' ? Math.round(v * 100) / 100 : Math.max(1, Math.round(v)); ev.target.value = fsKg(_od.yeni[ds.yenial]); return; }
  if (ds.drop) {
    const hedef = _od.liste ? _od.sec : _od.aktif, x = _odSet(hedef), [alan, k] = ds.drop.split(':'), dl = fsDroplar(x);
    if (!x || !dl[+k]) return;
    const v = parseFloat(String(ev.target.value).replace(',', '.'));
    if (isFinite(v) && v >= 0) { if (alan === 'kg') dl[+k].kg = Math.min(2000, Math.round(v * 100) / 100); else dl[+k].tekrar = Math.min(999, Math.round(v)); _odDokun(x); _odGecikmeliYaz(hedef.e); }
    return odakCiz();
  }
  if (ev.target.id !== 'od-kg' && ev.target.id !== 'od-tk' && !ds.setal) return;
  const hedef = ds.setal ? _od.sec : _od.aktif, x = _odSet(hedef); if (!x) return;
  const kgAlan = ev.target.id === 'od-kg' || ds.setal === 'kg';
  const v = !kgAlan && fsSureliMi(_od.ex[hedef.e].name) ? fsSureOku(ev.target.value) : parseFloat(String(ev.target.value).replace(',', '.'));
  if (v == null || !isFinite(v) || v < 0) return odakCiz();
  if (kgAlan) x.weight = Math.round(v * 100) / 100; else x.reps = Math.min(FS_SURE_EN_COK, Math.round(v));
  _odDokun(x); odakCiz(); _odGecikmeliYaz(hedef.e);
});
// Düzenleyici alanları: yazarken durum güncellenir, yeniden çizim yok (imleç kaçmasın)
document.addEventListener('input', ev => {
  const k = ev.target.dataset && ev.target.dataset.dz, D = _od.duzen;
  if (!k || !D) return;
  const [alan, i, j] = k.split(':'), v = String(ev.target.value);
  if (alan === 'ad') D.name = v; else if (alan === 'yeniad') D.yeniAd = v; else if (alan === 'aralik') D.exercises[+i].aralik = v;
  else { const n = parseFloat(v.replace(',', '.')), x = D.exercises[+i].sets[+j]; if (isFinite(n) && n >= 0) { if (alan === 'kg') x.weight = Math.min(2000, Math.round(n * 100) / 100); else x.reps = Math.min(999, Math.round(n)); } }
});
document.addEventListener('keydown', ev => { if ((ev.target.id === 'od-kg' || ev.target.id === 'od-tk') && ev.key === 'Enter') ev.target.blur(); });
// Antrenman sekmesinden çıkınca geçmiş-gün hedefi düşer; GEÇMİŞ'e dönülüyorsa yazılan gün seçili gelir.
document.addEventListener('fitnes:sekme', e => {
  const tab = e.detail && e.detail.tab;
  if (tab === 'wkt' || !_od.hedef) return;
  const eski = _od.hedef;
  _od.hedef = null; _odGunSifirla();
  if (tab === 'gecmis' && window.FitnesGecmis) FitnesGecmis.tazele().then(() => FitnesGecmis.gunSec(eski));
});
document.addEventListener('fitnes:dil', () => { if (_od.yuklendi) odakCiz(); });
