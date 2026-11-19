/**
 * dis-baglanti.js — birim testleri (Electron gerektirmez, `npm test` içinde koşar).
 *
 * ⚠️ Bu testler kuralın DOĞRU olduğunu gösterir, Electron'un o kuralı gerçekten
 * uyguladığını DEĞİL. İkincisinin tek kanıtı canlı koşumdur:
 *   ../scratchpad/dis-link-canli-test.js  (gerçek Electron 29, xvfb; 6 kontrol)
 * 2026-08-06'da kusuru bulan da o oldu — statik okuma "link var ✅" diyordu.
 */
const test = require('node:test');
const assert = require('node:assert');
const { disBaglantiKurallari } = require('./dis-baglanti');

const IC = 'http://127.0.0.1:8791';

function kur() {
  const acilanlar = [];
  const gunluk = [];
  const d = disBaglantiKurallari({
    openExternal: (url) => { acilanlar.push(url); return Promise.resolve(); },
    icOnEk: IC,
    kaydet: (m) => gunluk.push(m),
  });
  return { d, acilanlar, gunluk };
}

test('https dış bağlantı sistem tarayıcısına gider', () => {
  const { d, acilanlar } = kur();
  assert.strictEqual(d.ac('https://openrouter.ai/keys'), true);
  assert.deepStrictEqual(acilanlar, ['https://openrouter.ai/keys']);
});

test('pencere açma işleyicisi uygulama içinde ASLA pencere açtırmaz', () => {
  const { d, acilanlar } = kur();
  const sonuc = d.pencereAcmaIsleyicisi({ url: 'https://aistudio.google.com/apikey' });
  assert.deepStrictEqual(sonuc, { action: 'deny' });
  assert.deepStrictEqual(acilanlar, ['https://aistudio.google.com/apikey']);
});

test('http/https dışı şema açılmaz (file/javascript/özel şema)', () => {
  for (const url of ['file:///etc/passwd', 'javascript:alert(1)', 'yuki://calistir']) {
    const { d, acilanlar, gunluk } = kur();
    assert.strictEqual(d.ac(url), false, url);
    assert.deepStrictEqual(acilanlar, [], url);
    assert.ok(gunluk.join(' ').includes('reddedildi'), url);
  }
});

test('çözümlenemeyen URL patlatmaz, reddeder', () => {
  const { d, acilanlar } = kur();
  assert.strictEqual(d.ac('bu bir url değil'), false);
  assert.deepStrictEqual(acilanlar, []);
});

test('🔴 REGRESYON: uygulamanın kendi sayfaları dışarı gönderilmez', () => {
  // Ölçüt yanlışlıkla `file://` ile sınırlanırsa PLAN ekranına geçiş ve her
  // yeniden yükleme kesilir — düzeltmenin ürünü kırdığı hâli tam burasıdır.
  const { d, acilanlar } = kur();
  let engellendi = false;
  const olay = { preventDefault: () => { engellendi = true; } };

  assert.strictEqual(d.gezinmeIsleyicisi(olay, IC + '/ui/planner.html'), false);
  assert.strictEqual(d.gezinmeIsleyicisi(olay, IC + '/'), false);
  assert.strictEqual(d.gezinmeIsleyicisi(olay, 'file:///opt/yuki/splash.html'), false);
  assert.strictEqual(engellendi, false, 'iç gezinme engellenmemeli');
  assert.deepStrictEqual(acilanlar, [], 'iç sayfa tarayıcıya gönderilmemeli');
});

test('target olmadan dışarı giden gezinme engellenip tarayıcıya devredilir', () => {
  const { d, acilanlar } = kur();
  let engellendi = false;
  const olay = { preventDefault: () => { engellendi = true; } };
  assert.strictEqual(d.gezinmeIsleyicisi(olay, 'https://example.org/proje.html?p=demo'), true);
  assert.strictEqual(engellendi, true);
  assert.deepStrictEqual(acilanlar, ['https://example.org/proje.html?p=demo']);
});

test('openExternal patlarsa uygulama düşmez, günlüğe yazılır', () => {
  const gunluk = [];
  const d = disBaglantiKurallari({
    openExternal: () => { throw new Error('tarayıcı yok'); },
    icOnEk: IC,
    kaydet: (m) => gunluk.push(m),
  });
  assert.strictEqual(d.ac('https://example.com'), false);
  assert.ok(gunluk.join(' ').includes('açılamadı'));
});

test('reddedilen söz (promise) yakalanır — unhandled rejection üretmez', () => {
  const gunluk = [];
  const d = disBaglantiKurallari({
    openExternal: () => Promise.reject(new Error('xdg-open yok')),
    icOnEk: IC,
    kaydet: (m) => gunluk.push(m),
  });
  assert.strictEqual(d.ac('https://example.com'), true);
  return new Promise((r) => setTimeout(() => {
    assert.ok(gunluk.join(' ').includes('açılamadı'));
    r();
  }, 20));
});
