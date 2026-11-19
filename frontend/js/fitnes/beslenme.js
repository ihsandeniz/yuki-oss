/* ═══ Fitnes BESLENME — tabak görünümü + son 7 gün + yemek arama ═══
 * Veri: GET /meals?date · /meals/gunluk (7 gün tek istek) · /config · POST/DELETE /meals.
 * Silme iki dokunuşlu (ilk dokunuş SİL gösterir; confirm() yok). Hızlı öğün/favori: durum.js.
 * Yemek arama: Open Food Facts'in açık API'si (yalnız yazılan arama metni gider; anahtar/kimlik gitmez).
 */
const _TB_OGUN = ['kahvalti', 'ogle', 'ara', 'aksam'];
const _tb = { gun: null, liste: [], dun: [], hafta: { bitis: null, gunler: [] }, cfg: { calGoal: 2000, proteinGoal: 150, carbGoal: 200, fatGoal: 65 }, formOgun: null, hata: false };
const _tbSayi = v => { const n = parseFloat(String(v || '').replace(',', '.')); return isFinite(n) && n > 0 ? n : 0; };
const _tbGunKisa = iso => new Date(iso + 'T12:00:00').toLocaleDateString(fYerel(), { weekday: 'short' }).toLocaleUpperCase(fYerel());
const _tbGunAy = iso => new Date(iso + 'T12:00:00').toLocaleDateString(fYerel(), { day: 'numeric', month: 'short' }).toLocaleUpperCase(fYerel());

async function tabakYukle() {
  if (!_tb.gun) _tb.gun = fsTodayStr();
  const bugun = fsTodayStr();
  const bitis = _gFark(bugun, _tb.gun) > 6 ? _gGunEkle(_tb.gun, 3) : bugun;
  const [liste, dun, hafta, cfg] = await Promise.all([
    fsGet('/meals?date=' + _tb.gun), fsGet('/meals?date=' + _gGunEkle(_tb.gun, -1)),
    fsGet(`/meals/gunluk?bitis=${bitis}&gun=7`), fsGet('/config')]);
  _tb.liste = liste || []; _tb.dun = dun || []; _tb.cfg = cfg || _tb.cfg;
  _tb.hafta = { bitis, gunler: hafta || [] };
  _tb.hata = !liste;
  tabakCiz();
  if (typeof fitnesHizliYukle === 'function') fitnesHizliYukle();
  if (typeof fitnesDurumYukle === 'function') fitnesDurumYukle();
}

function tabakGun(delta) {
  const yeni = _gGunEkle(_tb.gun || fsTodayStr(), delta);
  if (yeni > fsTodayStr()) return;
  _tb.gun = yeni; tabakFormKapat(); tabakYukle();
}

function _tbTopla(l) { return l.reduce((a, e) => ({ cal: a.cal + +e.cal, P: a.P + +e.protein, K: a.K + +e.carb, Y: a.Y + +e.fat }), { cal: 0, P: 0, K: 0, Y: 0 }); }

function tabakCiz() {
  const bugun = fsTodayStr(), g = _tb.gun;
  const onEk = g === bugun ? fT('besl.bugun') : g === _gGunEkle(bugun, -1) ? fT('besl.dun') : _tbGunKisa(g);
  document.getElementById('tb-gun-ad').textContent = `${onEk} · ${_tbGunAy(g)}`;
  document.getElementById('tb-ileri').disabled = g >= bugun;

  const c = _tb.cfg, T = _tbTopla(_tb.liste), oran = c.calGoal ? T.cal / c.calGoal : 0;
  const dolu = document.getElementById('tb-halka-dolu'), cevre = 2 * Math.PI * 54;
  dolu.setAttribute('stroke-dasharray', `${cevre * Math.min(1, oran)} ${cevre}`);
  dolu.classList.toggle('asti', oran > 1.05);
  dolu.style.opacity = T.cal > 0 ? 1 : 0;   // 0'da yuvarlak uç tepede nokta bırakıyordu
  document.getElementById('tb-kcal').textContent = fsSay(T.cal);
  document.getElementById('tb-hedef').textContent = `/ ${fsSay(c.calGoal)} KCAL`;
  const kal = c.calGoal - T.cal, kalEl = document.getElementById('tb-kalan');
  kalEl.textContent = _tb.hata ? fT('besl.alinamadi') : kal >= 0 ? fT('besl.kalan', { n: fsSay(kal) }) : fT('besl.fazla', { n: fsSay(-kal) });
  kalEl.classList.toggle('asti', kal < 0 || _tb.hata);
  document.getElementById('tb-makro').innerHTML = [['P', 'protein', c.proteinGoal], ['K', 'karb', c.carbGoal], ['Y', 'yag', c.fatGoal]].map(([k, ad, h]) =>
    `<div class="tb-m tb-${k}"><span>${fT('besl.' + ad)}</span><span><b>${Math.round(T[k])}</b> / ${h}g</span><i style="--w:${h ? Math.min(100, T[k] / h * 100) : 0}%"></i></div>`).join('') +
    `<button id="tb-hedef-btn" type="button">${fT('besl.hedefler')}</button>`;

  const form = document.getElementById('tb-form');
  document.getElementById('fstrip-pane-nutr').appendChild(form);   // yeniden çizim formu silmesin
  document.getElementById('tb-tabaklar').innerHTML = _TB_OGUN.map((k, i) => {
    const ad = fT('ogun.' + k), l = _tb.liste.filter(e => e.meal === k), t = _tbTopla(l);
    const dunL = _tb.dun.filter(e => e.meal === k);
    const dunD = dunL.length && !l.length ? `<button type="button" data-dun="${k}">${fT('besl.dunku', { n: dunL.length })}</button>` : '';
    if (!l.length) return `<article class="tb-kart tb-bos" data-ogun="${k}" style="--i:${i}"><button type="button" class="tb-tabak" data-ekle="${k}" aria-label="${fT('besl.ekle-aria', { ad })}"><span>+</span></button>` +
      `<div class="tb-ic"><div class="tb-bas"><b>${ad}</b><em>${fT('besl.bos')}</em></div><div class="tb-eylem"><button type="button" data-ekle="${k}">${fT('besl.ekle')}</button>${dunD}</div></div></article>`;
    const p = t.P * 4, kb = t.K * 4, y = t.Y * 9, top = p + kb + y, a1 = top ? p / top * 360 : 0, a2 = top ? a1 + kb / top * 360 : 0;
    const halka = top ? `conic-gradient(var(--f-protein) 0 ${a1}deg, var(--f-karb) ${a1}deg ${a2}deg, var(--f-yag) ${a2}deg 360deg)` : 'var(--f-yuzey-2)';
    return `<article class="tb-kart" data-ogun="${k}" style="--i:${i}"><button type="button" class="tb-tabak" data-ekle="${k}" style="background:${halka}" aria-label="${fT('besl.tabak-aria', { ad, n: fsSay(t.cal) })}"><span>${fsSay(t.cal)}</span></button>` +
      `<div class="tb-ic"><div class="tb-bas"><b>${ad}</b><em>${fsSay(t.cal)} kcal · P${Math.round(t.P)} K${Math.round(t.K)} Y${Math.round(t.Y)}</em></div><ul class="tb-liste">` +
      l.map(e => `<li><button type="button" class="tb-s" data-id="${fsKac(e.id)}" aria-label="${fT('besl.sil-aria', { ad: fsKac(e.name) })}"><span class="ad">${fsKac(e.name)}</span><small>${fsSay(e.cal)}</small><span class="sil">${fT('ortak.sil')}</span></button>${typeof fitnesYildiz === 'function' ? fitnesYildiz(e) : ''}</li>`).join('') +
      `</ul><div class="tb-eylem"><button type="button" data-ekle="${k}">${fT('besl.ekle')}</button></div></div></article>`;
  }).join('');
  if (_tb.formOgun) tabakFormAc(_tb.formOgun, true); else form.hidden = true;

  // Son 7 gün: kesik çizgi hedef; seçili gün vurgulu, bugün etiketli
  const harita = Object.fromEntries((_tb.hafta.gunler || []).map(x => [x.tarih, x.cal]));
  const gunler = Array.from({ length: 7 }, (_, i) => _gGunEkle(_tb.hafta.bitis, i - 6));
  const maks = Math.max(c.calGoal * 1.2, ...gunler.map(x => harita[x] || 0), 1);
  document.getElementById('tb-hafta-bas').textContent = fT('besl.son7');
  document.getElementById('tb-hafta-hedef').textContent = fT('besl.hedef-cizgi', { n: fsSay(c.calGoal) });
  document.getElementById('tb-cubuk').innerHTML = `<span class="hedef" style="bottom:calc(${c.calGoal / maks} * (100% - 17px) + 17px)"></span>` + gunler.map(x => {
    const kc = harita[x] || 0;
    const cls = ['tb-g', !kc && 'yok', kc > c.calGoal * 1.05 && 'asti', x === bugun && 'bugun', x === g && 'secili'].filter(Boolean).join(' ');
    return `<button type="button" class="${cls}" data-gun="${x}" ${x > bugun ? 'disabled' : ''} aria-label="${_tbGunAy(x)}: ${fsSay(kc)} kcal"><i style="height:calc(${kc / maks} * (100% - 17px))"></i><span>${_tbGunKisa(x)}</span></button>`;
  }).join('');
}

function tabakFormAc(ogun, yerinde) {
  const form = document.getElementById('tb-form'), kart = document.querySelector(`.tb-kart[data-ogun="${ogun}"] .tb-ic`);
  if (!kart) return;
  _tb.formOgun = ogun;
  kart.appendChild(form);
  form.hidden = false;
  if (!yerinde) { document.getElementById('tb-durum').textContent = ''; setTimeout(() => document.getElementById('tb-ad').focus(), 30); }
}
function tabakFormKapat() {
  const form = document.getElementById('tb-form');
  _tb.formOgun = null; form.hidden = true; form.classList.remove('hata');
  document.getElementById('tb-durum').textContent = '';
  ['tb-ad', 'tb-kcal-inp', 'tb-p', 'tb-k', 'tb-y'].forEach(id => { document.getElementById(id).value = ''; });
}
async function tabakEkle(e) {
  e.preventDefault();
  const form = document.getElementById('tb-form'), durum = document.getElementById('tb-durum');
  const ad = document.getElementById('tb-ad').value.trim(), cal = _tbSayi(document.getElementById('tb-kcal-inp').value);
  if (!ad || !cal) { form.classList.add('hata'); durum.textContent = !ad ? fT('besl.ad-yaz') : fT('besl.kcal-yaz'); return; }
  const r = await fsApiPost('/meals', { meal: _tb.formOgun, name: ad, cal, protein: _tbSayi(document.getElementById('tb-p').value),
    carb: _tbSayi(document.getElementById('tb-k').value), fat: _tbSayi(document.getElementById('tb-y').value), entry_date: _tb.gun });
  if (!r) { form.classList.add('hata'); durum.textContent = fT('besl.eklenemedi'); return; }
  tabakFormKapat();
  await tabakYukle();
}

document.addEventListener('submit', e => { if (e.target.id === 'tb-form') tabakEkle(e); });
document.addEventListener('click', async e => {
  if (!e.target.closest || !e.target.closest('#fstrip-pane-nutr')) return;
  const t = e.target;
  if (t.closest('#tb-geri')) return tabakGun(-1);
  if (t.closest('#tb-ileri')) return tabakGun(1);
  if (t.closest('#tb-ara')) return fsFoodSearchOpen(_tb.formOgun);
  if (t.closest('#tb-vazgec')) return tabakFormKapat();
  const ekle = t.closest('[data-ekle]');
  if (ekle) return tabakFormAc(ekle.dataset.ekle);
  const dun = t.closest('[data-dun]');
  if (dun) {
    dun.disabled = true;
    for (const x of _tb.dun.filter(m => m.meal === dun.dataset.dun))
      await fsApiPost('/meals', { meal: x.meal, name: x.name, cal: +x.cal, protein: +x.protein, carb: +x.carb, fat: +x.fat, entry_date: _tb.gun });
    return tabakYukle();
  }
  const gun = t.closest('.tb-g[data-gun]');
  if (gun) { _tb.gun = gun.dataset.gun; tabakFormKapat(); return tabakYukle(); }
  const s = t.closest('.tb-s');
  document.querySelectorAll('.tb-s.acik').forEach(x => { if (x !== s) x.classList.remove('acik'); });
  if (!s) return;
  if (!s.classList.contains('acik')) { s.classList.add('acik'); return; }
  await fsApiDelete('/meals/' + encodeURIComponent(s.dataset.id));
  await tabakYukle();
});

/* ── Yemek arama (Open Food Facts) → açık tabak formunu doldurur ── */
const _fss = { ogun: 'ara', zaman: null, urunler: [] };
function fsFoodSearchOpen(ogun) {
  document.getElementById('fss-input').value = document.getElementById('tb-ad').value || '';
  document.getElementById('fss-results').innerHTML = '';
  document.getElementById('fss-status').textContent = fT('ara.basla');
  document.getElementById('fss-qty').value = '100';
  _fss.urunler = [];
  fssSetMeal(ogun || _tb.formOgun || 'ara');
  document.getElementById('fs-search-overlay').classList.add('open');
  const q = document.getElementById('fss-input').value.trim();
  if (q.length >= 2) fsFoodSearchDebounce(q);
  setTimeout(() => document.getElementById('fss-input').focus(), 100);
}
function fsFoodSearchClose() { document.getElementById('fs-search-overlay').classList.remove('open'); }
function fssSetMeal(k) { _fss.ogun = k; document.querySelectorAll('#fs-search-overlay [data-fss-ogun]').forEach(b => b.classList.toggle('active', b.dataset.fssOgun === k)); }
function fsFoodSearchDebounce(q) {
  clearTimeout(_fss.zaman);
  const st = document.getElementById('fss-status');
  if (q.trim().length < 2) { st.textContent = fT('ara.en-az'); document.getElementById('fss-results').innerHTML = ''; return; }
  st.textContent = fT('ara.araniyor');
  _fss.zaman = setTimeout(() => fsFoodSearchFetch(q.trim()), 500);
}
async function fsFoodSearchFetch(q) {
  const st = document.getElementById('fss-status');
  try {
    const url = `https://world.openfoodfacts.org/cgi/search.pl?search_terms=${encodeURIComponent(q)}&search_simple=1&action=process&json=1&page_size=10&fields=product_name,brands,nutriments`;
    const data = await (await fetch(url)).json();
    _fss.urunler = (data.products || []).filter(p => { const n = p.nutriments || {}; return p.product_name && (n['energy-kcal_100g'] != null || n['energy_100g'] != null); });
    if (!_fss.urunler.length) { st.textContent = fT('ara.yok'); document.getElementById('fss-results').innerHTML = ''; return; }
    st.textContent = fT('ara.bulundu', { n: _fss.urunler.length });
    fsFoodRenderResults();
  } catch { st.textContent = fT('ara.hata'); }
}
function _fssMakro(p, qty) {
  const n = p.nutriments || {}, f = qty / 100;
  return { cal: Math.round((n['energy-kcal_100g'] ?? (n['energy_100g'] || 0) / 4.184) * f), p: +((n.proteins_100g || 0) * f).toFixed(1),
    k: +((n.carbohydrates_100g || 0) * f).toFixed(1), y: +((n.fat_100g || 0) * f).toFixed(1) };
}
function fsFoodRenderResults() {
  const qty = parseFloat(document.getElementById('fss-qty').value) || 100;
  document.getElementById('fss-results').innerHTML = _fss.urunler.map((p, i) => {
    const m = _fssMakro(p, qty), marka = p.brands ? `<div class="fss-marka">${fsKac(p.brands.split(',')[0].trim())}</div>` : '';
    return `<button type="button" class="fss-item" data-fss-sec="${i}"><span class="fss-ad">${fsKac(p.product_name)}</span>${marka}
      <span class="fss-makro">${fT('ara.makro', { kcal: m.cal, p: m.p, k: m.k, y: m.y, g: qty })}</span></button>`;
  }).join('');
}
function fsFoodSelect(i) {
  const qty = parseFloat(document.getElementById('fss-qty').value) || 100, p = _fss.urunler[i], m = _fssMakro(p, qty);
  tabakFormAc(_fss.ogun);
  document.getElementById('tb-ad').value = p.product_name + (qty !== 100 ? ` (${qty}g)` : '');
  document.getElementById('tb-kcal-inp').value = m.cal; document.getElementById('tb-p').value = m.p;
  document.getElementById('tb-k').value = m.k; document.getElementById('tb-y').value = m.y;
  fsFoodSearchClose();
}
document.addEventListener('click', e => {
  const ov = document.getElementById('fs-search-overlay');
  if (!ov || !e.target.closest || !ov.contains(e.target)) return;
  if (e.target === ov || e.target.closest('#fss-kapat')) return fsFoodSearchClose();
  const o = e.target.closest('[data-fss-ogun]');
  if (o) return fssSetMeal(o.dataset.fssOgun);
  const s = e.target.closest('[data-fss-sec]');
  if (s) fsFoodSelect(+s.dataset.fssSec);
});
document.addEventListener('input', e => {
  if (e.target.id === 'fss-input') fsFoodSearchDebounce(e.target.value);
  else if (e.target.id === 'fss-qty' && _fss.urunler.length) fsFoodRenderResults();
});
document.addEventListener('keydown', e => { if (e.key === 'Escape' && document.getElementById('fs-search-overlay')?.classList.contains('open')) fsFoodSearchClose(); });
