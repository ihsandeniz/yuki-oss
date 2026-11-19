/* ═══ Fitnes ortak — API, sekmeler, süreli hareket/drop kuralları, eski yerel kayıt göçü, bildirim mesajları ═══
 * Yükleme sırası (planner.html, klasik <script>): dil.js → ortak.js → hareket.js → ayar.js → beslenme.js →
 * durum.js → antrenman.js → gecmis.js. Hepsi planner'ın büyük betiğinden ÖNCE yüklenir; planner'ın
 * yardımcıları (_tok, esc, _yerelGun, _gGunEkle, _gFark, plHata) çağrı anında vardır.
 *
 * Planner ile sözleşme (adlar sabit): setMode('fitness') → fsHydrate().then(tabakYukle + odakYukle) ·
 * mobil şerit → fstripTab('wkt'|'nutr') · init → fsHydrate().
 */
const FITNESS_API = '/api/fitness';
const FS_NUTR_KEY = 'fitness_nutrition_v1';       // eski (sunucusuz) sürümün yerel öğün kaydı — yalnız göç okur
const FW_KEY = 'fitness_workout_v1';
const FW_TMPL_KEY = 'fitness_templates_v1';

function fsApiHeaders() {
  const h = { 'Content-Type': 'application/json' };
  let t = '';
  try { t = typeof _tok === 'function' ? _tok() : ''; } catch {}
  if (t) h.Authorization = 'Bearer ' + t;
  return h;
}

// Öğün/set yazımı görev ilerlemesini değiştirir → Durum tazelenir (durum.js debounce'lu).
function _fitYazdi(yol) { if (/^\/(workouts|meals)/.test(yol) && typeof fitnesDurumYukle === 'function') fitnesDurumYukle(); }

/* Tek istek kapısı: {ok, status, json}. Ağ yoksa status 0. */
async function fsIstek(yontem, yol, govde) {
  if (yontem !== 'GET') _fitYazdi(yol);
  try {
    const r = await fetch(FITNESS_API + yol, { method: yontem, headers: fsApiHeaders(),
      body: govde === undefined ? undefined : JSON.stringify(govde) });
    let j = null;
    try { j = r.status === 204 ? null : await r.json(); } catch {}
    return { ok: r.ok, status: r.status, json: j };
  } catch { return { ok: false, status: 0, json: null }; }
}
async function fsGet(yol) { const r = await fsIstek('GET', yol); return r.ok ? r.json : null; }
async function fsApiPost(yol, govde) { const r = await fsIstek('POST', yol, govde); return r.ok ? (r.json || {}) : null; }
async function fsApiPut(yol, govde) { const r = await fsIstek('PUT', yol, govde); return r.ok ? (r.json || {}) : null; }
async function fsApiDelete(yol) { const r = await fsIstek('DELETE', yol); return r.ok; }

// YEREL gün (toISOString UTC'ye kayar: gece 00-03 arası girilen kayıt düne düşerdi).
function fsTodayStr() { return _yerelGun(new Date()); }
function fsKac(s) {
  return String(s == null ? '' : s).replace(/[&<>"']/g, c => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));
}
function fsSay(v, ond = 0) {
  return (+v || 0).toLocaleString(fYerel(), { minimumFractionDigits: ond, maximumFractionDigits: ond });
}
function fsKg(n) { return (Math.round((+n || 0) * 100) / 100).toLocaleString(fYerel()); }
const fsAzalt = () => window.matchMedia('(prefers-reduced-motion: reduce)').matches;

/* ── Eski sürümden göç: yalnız bu tarayıcıda kalmış (sunucuya hiç gitmemiş) kayıtları bir kez taşı ──
 * Yerel öğün id'si Date.now() sayısıdır (sunucunun id'si uuid metni). Hepsi gitmeden bayrak yazılmaz. */
let _fsGoc = null;
function fsHydrate() {
  if (_fsGoc) return _fsGoc;
  _fsGoc = (async () => {
    const BAYRAK = 'yuki_fitnes_goc_v2';
    let ogun, seans, sablon;
    try {
      if (localStorage.getItem(BAYRAK)) return;
      ogun = JSON.parse(localStorage.getItem(FS_NUTR_KEY) || '[]');
      seans = JSON.parse(localStorage.getItem(FW_KEY) || '[]');
      sablon = JSON.parse(localStorage.getItem(FW_TMPL_KEY) || '[]');
    } catch { return; }
    let hepsi = true;
    for (const e of ogun || []) {
      if (typeof e.id !== 'number' || !e.name || !e.date) continue;
      if (!await fsApiPost('/meals', { meal: e.meal || 'ara', name: e.name, cal: +e.cal || 0, protein: +e.protein || 0,
        carb: +e.carb || 0, fat: +e.fat || 0, entry_date: e.date })) hepsi = false;
    }
    for (const se of seans || []) for (const ex of se.exercises || []) {
      if (typeof ex.id !== 'number' || !ex.name || !se.date) continue;
      if (!await fsApiPost('/workouts/exercise', { name: ex.name, session_date: se.date,
        sets: (ex.sets || []).map(x => ({ reps: +x.reps || 0, weight: +x.weight || 0, completed: !!x.completed })) })) hepsi = false;
    }
    for (const t of sablon || []) {
      if (!String(t.id || '').startsWith('tmpl_') || !t.name) continue;
      if (!await fsApiPost('/templates', { name: t.name, exercises: t.exercises || [] })) hepsi = false;
    }
    if (hepsi) try { localStorage.setItem(BAYRAK, '1'); [FS_NUTR_KEY, FW_KEY, FW_TMPL_KEY].forEach(k => localStorage.removeItem(k)); } catch {}
  })().finally(() => { _fsGoc = null; });
  return _fsGoc;
}

/* ── Sekmeler: BESLENME · ANTRENMAN · GEÇMİŞ · DURUM ──
 * ≥1000 px'de DURUM sağ sütunda hep açık (css), düğmesi gizli → oradayken ANTRENMAN'a geçilir.
 * Her geçişte 'fitnes:sekme' yayılır: GEÇMİŞ/DURUM tembel yüklemesini, antrenmanın geçmiş-gün hedefini buna bağlar. */
const FITNES_SEKMELER = ['nutr', 'wkt', 'gecmis', 'durum'];
const _fitGenis = () => window.matchMedia('(min-width: 1000px)').matches;
let _fitSekme = 'nutr';
function fstripTab(tab) {
  if (!FITNES_SEKMELER.includes(tab)) tab = 'nutr';
  if (tab === 'durum' && _fitGenis()) tab = 'wkt';
  _fitSekme = tab;
  document.querySelectorAll('#fstrip-tabs .fstrip-tab').forEach(b => {
    const su = b.dataset.tab === tab;
    b.classList.toggle('active', su);
    if (su) b.setAttribute('aria-current', 'page'); else b.removeAttribute('aria-current');
  });
  for (const ad of FITNES_SEKMELER) {
    const p = document.getElementById('fstrip-pane-' + ad);
    if (p) p.classList.toggle('fstrip-pane-active', tab === ad);
  }
  if (tab === 'wkt' && typeof odakYukle === 'function') odakYukle();
  document.dispatchEvent(new CustomEvent('fitnes:sekme', { detail: { tab } }));
}
window.matchMedia('(min-width: 1000px)').addEventListener('change', e => { if (e.matches && _fitSekme === 'durum') fstripTab('wkt'); });
document.addEventListener('click', e => {
  const b = e.target.closest && e.target.closest('#fstrip-tabs .fstrip-tab');
  if (b) fstripTab(b.dataset.tab);
});

// ⚙ AYARLAR: başlıktaki düğme ve beslenmedeki HEDEFLER › aynı çekmeceyi açar.
document.addEventListener('click', e => {
  const b = e.target.closest && e.target.closest('#fitnes-ayar-ac, #tb-hedef-btn');
  if (!b) return;
  e.preventDefault();
  if (window.FitnesAyar) window.FitnesAyar.ac(b.id === 'tb-hedef-btn' ? 'hedefler' : undefined);
});
document.addEventListener('fitnes:hedef-degisti', () => { if (typeof tabakYukle === 'function') tabakYukle(); });

/* ── Süreli hareket + drop set ──
 * Adında "(sn)" olan harekette reps = SANİYE (sunucu fitness_oyun.sureli_mi ile aynı kural).
 * Süreli set tonaja girmez; drop'lar ({kg, tekrar}) ana setin tonajına eklenir, ayrı set sayılmaz. */
const FS_SURE_EN_COK = 999;
const FS_DROP_EN_COK = 10;
function fsSureliMi(ad) { return /\(\s*sn\s*\)/i.test(ad || ''); }
function fsSureYaz(sn) {
  const t = Math.max(0, Math.round(+sn || 0));
  return t < 60 ? `${t} ${fT('ortak.sn')}` : `${Math.floor(t / 60)}:${String(t % 60).padStart(2, '0')}`;
}
// '90' · '90 sn' · '1:30' → saniye; çözülemezse null.
function fsSureOku(metin) {
  const t = String(metin == null ? '' : metin).trim().toLowerCase().replace(/\s*(sn|saniye|sec|s)\.?$/, '');
  let sn = null;
  const m = t.match(/^(\d{1,2})[:.](\d{1,2})$/);
  if (m && +m[2] < 60) sn = +m[1] * 60 + +m[2];
  else if (/^\d{1,4}$/.test(t)) sn = +t;
  return sn == null ? null : Math.min(FS_SURE_EN_COK, sn);
}
function fsDroplar(x) { return Array.isArray(x && x.drops) ? x.drops : []; }
function fsSetTonaj(ad, x) {
  if (fsSureliMi(ad)) return 0;
  return (+x.weight || 0) * (+x.reps || 0) + fsDroplar(x).reduce((a, d) => a + (+d.kg || 0) * (+d.tekrar || 0), 0);
}
// "Yapıldı" tek kural (sunucuyla aynı): girildi damgası ya da completed.
function fsYapildi(x) { return !!x && (x.girildi != null || !!x.completed); }

/* ── Service worker mesajları ──
 * {tur:'fitnes-olay'} → sayfa açıkken gelen fitnes push'u: durumu tazele.
 * {tur:'bildirim-ac', url:'…#fitnes'} → bildirime tıklandı: FİTNES › DURUM aç.
 * Yalnız aynı kökten gelen navigator.serviceWorker mesajı dinlenir; window.postMessage DİNLENMEZ. */
(function () {
  const sw = navigator.serviceWorker;
  let son = 0;
  function tazele() {
    if (Date.now() - son < 1500) return;
    son = Date.now();
    if (typeof fitnesDurumYukle === 'function') fitnesDurumYukle();
  }
  function fitnesAc() {
    if (typeof setMode === 'function') setMode('fitness');
    const d = document.querySelector('#fstrip-tabs [data-tab="durum"]');
    if (d && getComputedStyle(d).display !== 'none') fstripTab('durum');
  }
  function isle(m) {
    if (!m || typeof m !== 'object' || typeof m.tur !== 'string') return false;
    if (m.tur === 'fitnes-olay') { tazele(); return true; }
    if (m.tur === 'bildirim-ac' && /#fitnes\b/.test(String(m.url || ''))) { fitnesAc(); tazele(); return true; }
    return false;
  }
  if (sw) {
    sw.addEventListener('message', e => isle(e.data));
    try { sw.startMessages(); } catch {}
  }
  // Doğrudan bağlantı: /ui/planner.html#fitnes (push bildiriminin adresi)
  function hashBak() { if (location.hash === '#fitnes') setTimeout(fitnesAc, 0); }
  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', hashBak); else hashBak();
  window.FitnesOlay = { isle };
})();
