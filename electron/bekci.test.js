'use strict';
/*  · yuki-bekci entegrasyonu — bayrak, yol, argümanlar, çıkış kodları, kibar kapanış. */
const test = require('node:test');
const assert = require('node:assert');
const {
  bekciYolu, sarmala, cikisAnahtari, kibarKapat, portuBekciDenetler, ACILIS_SN,
  MOTOR_ZORLA_SN, KAPANIS_BEKLE_SN, KAPANIS_BEKLE_MS,
} = require('./bekci');
const fs = require('fs');
const path = require('path');
const SOZLUK = require('./dil-sozluk');

const yok = () => { const e = new Error('x'); e.code = 'ENOENT'; throw e; };
const var_ = () => {};

test('bayrak yok/boş/0/true → kapalı (varsayılan KAPALI)', () => {
  for (const v of [undefined, '', '0', 'true', ' 1']) {
    const r = bekciYolu({ env: { YUKI_BEKCI: v }, platform: 'linux', resourcesPath: '/r', accessSync: var_ });
    assert.deepStrictEqual(r, { kullan: false, neden: null }, String(v));
  }
});

test('bayrak açık + ikili var → yol (Windows .exe)', () => {
  assert.strictEqual(bekciYolu({ env: { YUKI_BEKCI: '1' }, platform: 'linux', resourcesPath: '/r', accessSync: var_ }).yol, '/r/bekci/yuki-bekci');
  assert.match(bekciYolu({ env: { YUKI_BEKCI: '1' }, platform: 'win32', resourcesPath: 'C:\\r', accessSync: var_ }).yol, /yuki-bekci\.exe$/);
});

test('bayrak açık + ikili yok/çalıştırılamaz → eski yol, neden dolu', () => {
  const r = bekciYolu({ env: { YUKI_BEKCI: '1' }, platform: 'linux', resourcesPath: '/r', accessSync: yok });
  assert.strictEqual(r.kullan, false);
  assert.match(r.neden, /ENOENT/);
});

test('sarmala: motor komutu -- sonrasında bozulmadan, bekçi seçenekleri önce', () => {
  const s = sarmala('/b', 'py', ['-c', 'x --yeniden'], '/l.log');
  assert.strictEqual(s.komut, '/b');
  const i = s.args.indexOf('--');
  assert.deepStrictEqual(s.args.slice(i), ['--', 'py', '-c', 'x --yeniden']);
  const once = s.args.slice(0, i);
  for (const sec of ['--yeniden', '--saglik', '--acilis', '--kapanis', '--log']) {
    assert.ok(once.includes(sec), sec);
  }
  assert.strictEqual(once[once.indexOf('--acilis') + 1], String(ACILIS_SN));
  assert.match(once[once.indexOf('--kapanis') + 1], /^http:\/\/127\.0\.0\.1:8791\/api\/motor\/kapan$/);
});

test('açılış tavanı sahadaki en kötü soğuk açılışın (~62 sn) en az 2 katı', () => {
  assert.ok(ACILIS_SN >= 120, 'kısa tavan yavaş diskte sağlıklı açılışı öldürür');
});

test('çıkış kodları → sözlük anahtarı, iki dilde de metni var', () => {
  for (const k of [70, 71, 127]) {
    const a = cikisAnahtari(k);
    assert.ok(a, String(k));
    assert.ok(SOZLUK.tr[a] && SOZLUK.en[a], a);
  }
  for (const k of [0, 1, 137, null]) assert.strictEqual(cikisAnahtari(k), null);
});

test('kibar kapanış: istek 202 + süreç çıktı → kibar', async () => {
  const r = await kibarKapat({ istekAt: async () => 202, cikisBekle: async () => true });
  assert.strictEqual(r, 'kibar');
});

test('kibar kapanış: istek kabul ama süreç çıkmadı → zorla', async () => {
  let beklenen = null;
  const r = await kibarKapat({ istekAt: async () => 202, cikisBekle: async (ms) => { beklenen = ms; return false; }, sureMs: 50 });
  assert.strictEqual(r, 'zorla');
  assert.strictEqual(beklenen, 50);
});

test('kibar kapanış: istek reddedildi/gitmedi → beklemeden zorla', async () => {
  let beklendi = false;
  const bekle = async () => { beklendi = true; return true; };
  assert.strictEqual(await kibarKapat({ istekAt: async () => 401, cikisBekle: bekle }), 'zorla');
  assert.strictEqual(await kibarKapat({ istekAt: async () => { throw new Error('ECONNREFUSED'); }, cikisBekle: bekle }), 'zorla');
  assert.strictEqual(beklendi, false, 'reddedilen istekten sonra beklemek kapanışı boşuna uzatır');
});

test('port sahibi: bekçi açıksa her platformda bekçi denetler (FAZ 6), kapalıysa eski yol', () => {
  for (const platform of ['win32', 'linux']) {
    const acik = bekciYolu({ env: { YUKI_BEKCI: '1' }, platform, resourcesPath: '/r', accessSync: () => {} });
    assert.strictEqual(portuBekciDenetler(acik), true, platform);
  }
  assert.strictEqual(portuBekciDenetler(bekciYolu({ env: {}, platform: 'win32', resourcesPath: '/r' })), false);
  assert.strictEqual(portuBekciDenetler(null), false);
});

test('uygulama.js port kararını bekci.js\'den alır (platform istisnası geri gelmesin)', () => {
  const kod = require('fs').readFileSync(require('path').join(__dirname, 'uygulama.js'), 'utf8');
  assert.match(kod, /const bekciPortuDenetler = bekciMod\.portuBekciDenetler\(bekci\);/);
  assert.doesNotMatch(kod, /bekci\.kullan && process\.platform !== 'win32'/);
});

//  (2026-10-10): bekleyen taraf motorun kendi zorla süresinden kısa beklerse motor kapanırken
// öldürülür (Windows CI: çökme sonrası motor 2/4 koşuda 12 sn'yi aştı, Electron 12 sn bekliyordu).
test('kapanış süreleri: JS kopyası motorun ZORLA_SN\'siyle aynı (tek kaynak motor_kapanis.py)', () => {
  const py = fs.readFileSync(path.join(__dirname, '..', 'backend', 'app', 'motor_kapanis.py'), 'utf8');
  const m = py.match(/^ZORLA_SN\s*=\s*([\d.]+)/m);
  assert.ok(m, 'motor_kapanis.py içinde ZORLA_SN bulunamadı');
  assert.strictEqual(Number(m[1]), MOTOR_ZORLA_SN, 'motor süresi değişti → bekci.js::MOTOR_ZORLA_SN de değişmeli');
});

test('kapanış süreleri: Electron ve bekçi motordan en az 2 sn uzun bekler', async () => {
  assert.ok(KAPANIS_BEKLE_SN >= MOTOR_ZORLA_SN + 2);
  let beklenen = null;
  await kibarKapat({ istekAt: async () => 202, cikisBekle: async (ms) => { beklenen = ms; return true; } });
  assert.strictEqual(beklenen, KAPANIS_BEKLE_MS, 'kibarKapat varsayılanı tek kaynaktan gelmeli');
  const a = sarmala('/b', 'py', ['run.py'], '/l.log').args;
  const once = a.slice(0, a.indexOf('--'));
  assert.ok(once.includes('--bekle'), "bekçi --bekle verilmezse varsayılanı 15 = motorla yarış");
  assert.strictEqual(Number(once[once.indexOf('--bekle') + 1]), KAPANIS_BEKLE_SN);
});
