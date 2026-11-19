/**
 * G3 Fitnes — metin kapsamı (tr/en). Kaynaklar CANLI okunur, teste kopyalanmaz.
 *
 * Ölçülenler:
 *   1. js/fitnes/*.js içindeki her sabit fT('…') anahtarı iki dilde de var.
 *   2. Birleştirilerek kurulan anahtarlar (fT('lig.' + k) gibi) bilinen değerlerin hepsinde var.
 *   3. planner.html fitnes iskeletindeki data-ft / data-ft-aria / data-ft-ph anahtarları var.
 *   4. TR ve EN aynı anahtar kümesini taşıyor; yer tutucular ({ad}) iki dilde aynı.
 *   5. fT yer tutucuyu doldurur, eksik anahtarda anahtarın kendisini döndürür; dil EN'e geçince EN metin gelir.
 *
 * Koşum:  node --test frontend/tests/fitnes-dil.test.mjs
 */
import test from 'node:test';
import assert from 'node:assert/strict';
import { readFileSync, readdirSync } from 'node:fs';
import { fileURLToPath } from 'node:url';
import { dirname, join } from 'node:path';
import vm from 'node:vm';

const KOK = join(dirname(fileURLToPath(import.meta.url)), '..');
const DIZIN = join(KOK, 'js', 'fitnes');

function yukle(yerel = 'tr-TR') {
  const olay = () => {};
  const ctx = {
    window: { addEventListener: olay, YukiDil: { yerel: () => yerel } },
    document: { addEventListener: olay, readyState: 'complete', querySelectorAll: () => [], documentElement: { lang: 'tr' } },
    setTimeout, location: { origin: 'http://x' },
  };
  vm.createContext(ctx);
  vm.runInContext(readFileSync(join(DIZIN, 'dil.js'), 'utf8'), ctx);
  return ctx.window;
}
const W = yukle();
const { tr: TR, en: EN } = W.FitnesDil.KATALOG;
const MODULLER = readdirSync(DIZIN).filter(f => f.endsWith('.js') && f !== 'dil.js');

// Birleştirilen önekler ve alabilecekleri değerler (kod ↔ test sözleşmesi)
const DINAMIK = {
  'an.': ['seviye', 'rekor', 'lig', 'beceri', 'evrim'],
  'onizle.': ['seviye', 'rekor', 'lig', 'beceri', 'evrim'],
  'ayar.': ['kalori', 'protein', 'karb', 'yag'],
  'beceri-d.': ['edinildi', 'evrim', 'askida', 'kapali', 'gizli', 'evrim-acik', 'evrim-kilit'],
  'besl.': ['protein', 'karb', 'yag'],
  'dal.': ['guc', 'day', 'dis', 'bes', 'golge'],
  'egri.': ['yumusak', 'keskin', 'yorunge', 'dogrusal'],
  'hafta-tur.': ['normal', 'dondurma', 'deload'],
  'hafta-tur-not.': ['normal', 'dondurma', 'deload'],
  'lig.': ['E', 'D', 'C', 'B', 'A', 'S'],
  'ogun.': ['kahvalti', 'ogle', 'ara', 'aksam'],
  'sonuc.': ['terfi', 'dusme', 'kalis', 'degerlendirilmedi'],
  'stat.': ['guc', 'day', 'dis', 'bes'],
  'stat-not.': ['guc', 'day', 'dis', 'bes'],
  'stat-uzun.': ['guc', 'day', 'dis', 'bes'],
  'tur.': ['SEVIYE', 'REKOR', 'BECERI', 'EVRIM', 'LIG', 'HAFTALIK_OZET', 'UYANIS', 'GOREV_TAMAM', 'HAFTA_HEDEFI', 'GOLGE', 'HATIRLATMA', 'DONDURMA'],
  'yog.': ['tam', 'sade', 'kapali'],
  'yog-not.': ['tam', 'sade', 'kapali'],
  'gec.s-': ['antrenman', 'seri', 'kacan', 'rekor'],
  'gec.b-': ['gun', 'hafta'],
  'sablon.': ['gogus', 'sirt', 'bacak'],
  'beceri-ad.': ['demir_tutus', 'celik_irade'],
};

const sabitler = [], onekler = new Set();
for (const f of MODULLER) {
  const s = readFileSync(join(DIZIN, f), 'utf8');
  for (const m of s.matchAll(/fT\(\s*(["'`])([^"'`$]+)\1\s*([,)+])/g)) {
    if (m[3] === '+') onekler.add(m[2]); else sabitler.push([f, m[2]]);
  }
}

test('her sabit fT anahtarı tr ve en sözlükte var', () => {
  assert.ok(sabitler.length > 300, `beklenenden az anahtar bulundu (${sabitler.length}) — tarayıcı bozuk olabilir`);
  const eksik = sabitler.filter(([, k]) => !(k in TR) || !(k in EN)).map(([f, k]) => `${f}: ${k}`);
  assert.deepEqual(eksik, []);
});

test('birleştirilen her önek sözleşmede ve bütün değerleri sözlükte', () => {
  const bilinmeyen = [...onekler].filter(o => !(o in DINAMIK));
  assert.deepEqual(bilinmeyen, [], 'koddaki önek testin DINAMIK listesinde yok');
  const eksik = [];
  for (const [o, degerler] of Object.entries(DINAMIK))
    for (const d of degerler) { if (!(o + d in TR)) eksik.push('tr ' + o + d); if (!(o + d in EN)) eksik.push('en ' + o + d); }
  assert.deepEqual(eksik, []);
});

test('planner.html fitnes iskeletinin anahtarları sözlükte', () => {
  const html = readFileSync(join(KOK, 'planner.html'), 'utf8');
  const iskelet = html.slice(html.indexOf('<div id="fitness-view"'), html.indexOf('<div id="shortcut-hint">'));
  assert.ok(iskelet.length > 1000, 'fitnes iskeleti bulunamadı');
  const anahtarlar = [...iskelet.matchAll(/data-ft(?:-aria|-ph)?="([^"]+)"/g)].map(m => m[1]);
  assert.ok(anahtarlar.length > 30);
  assert.deepEqual(anahtarlar.filter(k => !(k in TR) || !(k in EN)), []);
  assert.ok(!/\sonclick=/.test(iskelet), 'iskelette satır içi onclick kaldı');
});

test('tr ve en aynı anahtarları ve aynı yer tutucuları taşıyor', () => {
  assert.deepEqual(Object.keys(TR).filter(k => !(k in EN)), []);
  assert.deepEqual(Object.keys(EN).filter(k => !(k in TR)), []);
  const yt = s => [...String(s).matchAll(/\{(\w+)\}/g)].map(x => x[1]).sort().join();
  assert.deepEqual(Object.keys(TR).filter(k => yt(TR[k]) !== yt(EN[k])), []);
});

test('fT doldurur, eksikte anahtarı döndürür, dil değişince EN verir', () => {
  assert.equal(W.fT('ant.set-n', { n: 3 }), 'set 3');
  assert.equal(W.fT('yok.boyle-anahtar'), 'yok.boyle-anahtar');
  assert.equal(W.fYerel(), 'tr-TR');
  const E = yukle('en-US');
  assert.equal(E.fT('ant.sablon-say', { e: 4, s: 12 }), '4 exercises · 12 sets');
  assert.equal(E.fYerel(), 'en-GB');
});
