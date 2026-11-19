// Pencere konumu doğrulaması — "uygulama çalışıyor ama pencere görünmüyor"
// sınıfının regresyon testi.
//
// Gerçek arıza: kayıtlı x/y hiç doğrulanmıyordu. Harici monitör çıkarılınca ya da
// çözünürlük değişince pencere masaüstünün dışında açılıyor; kullanıcı bunu
// "açılmadı"dan ayırt edemiyor.
//
//   node --test electron/pencere-konum.test.js

const test = require('node:test');
const assert = require('node:assert');
const { gorunurAlanaSigdir } = require('./pencere-konum');

const TEK_EKRAN = [{ x: 0, y: 0, width: 1920, height: 1040 }];
const IKI_EKRAN = [
  { x: 0, y: 0, width: 1920, height: 1040 },
  { x: 1920, y: 0, width: 2560, height: 1400 },   // sağdaki harici monitör
];

test('ekran içindeki konum olduğu gibi korunur', () => {
  const s = gorunurAlanaSigdir({ x: 100, y: 80, width: 900, height: 700 }, TEK_EKRAN);
  assert.equal(s.x, 100);
  assert.equal(s.y, 80);
  assert.equal(s.width, 900);
  assert.equal(s.height, 700);
});

test('harici monitör çıkarılınca oradaki pencere ortalanmaya döner', () => {
  // Kullanıcı pencereyi sağdaki monitöre koydu, sonra kabloyu çıkardı.
  const kayitli = { x: 2400, y: 300, width: 900, height: 700 };
  const iki = gorunurAlanaSigdir(kayitli, IKI_EKRAN);
  assert.equal(iki.x, 2400, 'monitör takılıyken konum korunmalı');

  const tek = gorunurAlanaSigdir(kayitli, TEK_EKRAN);
  assert.equal(tek.x, undefined, 'monitör yokken x düşürülmeli (Electron ortalar)');
  assert.equal(tek.y, undefined);
});

test('negatif/ekran dışı koordinatlar düşürülür', () => {
  for (const kotu of [
    { x: -5000, y: 0 },      // solda hiçbir ekran yok
    { x: 0, y: -3000 },      // yukarıda hiçbir ekran yok
    { x: 99999, y: 99999 },  // tamamen dışarıda
  ]) {
    const s = gorunurAlanaSigdir({ ...kotu, width: 900, height: 700 }, TEK_EKRAN);
    assert.equal(s.x, undefined, `ekran dışı ${JSON.stringify(kotu)} düşürülmeli`);
  }
});

test('kenardan azıcık görünen pencere de kurtarılamaz sayılır', () => {
  // Sağ kenarda yalnız 40px görünüyor → ne okunur ne de sürüklenebilir.
  const s = gorunurAlanaSigdir({ x: 1880, y: 500, width: 900, height: 700 }, TEK_EKRAN);
  assert.equal(s.x, undefined);
});

test('kenardan yeterince görünen pencere korunur', () => {
  // 200px görünür + başlık şeridi ekranda → kullanıcı geri sürükleyebilir.
  const s = gorunurAlanaSigdir({ x: 1720, y: 500, width: 900, height: 700 }, TEK_EKRAN);
  assert.equal(s.x, 1720);
});

test('ekrana sığmayan boyut kırpılır, asgarinin altına inmez', () => {
  const buyuk = gorunurAlanaSigdir({ x: 0, y: 0, width: 9000, height: 9000 }, TEK_EKRAN);
  assert.equal(buyuk.width, 1920);
  assert.equal(buyuk.height, 1040);

  const kucuk = gorunurAlanaSigdir({ x: 0, y: 0, width: 10, height: 10 }, TEK_EKRAN);
  assert.equal(kucuk.width, 480, 'minWidth altına düşmemeli');
  assert.equal(kucuk.height, 600, 'minHeight altına düşmemeli');
});

test('konum yoksa (ilk açılış) dokunulmaz', () => {
  const s = gorunurAlanaSigdir({ width: 900, height: 700 }, TEK_EKRAN);
  assert.equal(s.x, undefined);
  assert.equal(s.y, undefined);
  assert.equal(s.width, 900);
});

test('bozuk kayıt (NaN/null/metin) çökertmez, ortalanmaya döner', () => {
  for (const kotu of [
    { x: NaN, y: 0 }, { x: null, y: null }, { x: '100', y: '100' }, { x: Infinity, y: 0 },
  ]) {
    const s = gorunurAlanaSigdir({ ...kotu, width: 900, height: 700 }, TEK_EKRAN);
    assert.equal(s.x, undefined, `${JSON.stringify(kotu)} için x düşürülmeli`);
  }
});

test('ekran listesi boşsa girdi bozulmadan döner', () => {
  // Ekran bilgisi alınamadıysa tahminde bulunma — kullanıcının kaydını silme.
  const s = gorunurAlanaSigdir({ x: 100, y: 100, width: 900, height: 700 }, []);
  assert.equal(s.x, 100);
  assert.equal(s.width, 900);
});

test('girdi nesnesi değiştirilmez (yan etki yok)', () => {
  const girdi = { x: 99999, y: 99999, width: 9000, height: 9000, alwaysOnTop: true };
  const kopya = { ...girdi };
  gorunurAlanaSigdir(girdi, TEK_EKRAN);
  assert.deepEqual(girdi, kopya);
});

test('ilgisiz alanlar (alwaysOnTop) taşınır', () => {
  const s = gorunurAlanaSigdir({ x: 0, y: 0, width: 900, height: 700, alwaysOnTop: false }, TEK_EKRAN);
  assert.equal(s.alwaysOnTop, false);
});
