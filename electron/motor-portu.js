'use strict';
/**
 * Motor portu seçimi — iki Yuki kopyası (ayrı profiller) aynı anda açılabilsin.
 *
 * Eskiden port 8791'e sabitti: ikinci kopya 8791'i dolu görüp ÖBÜR kopyanın motorunu
 * "sağ kalmış motorum" sanıp ona bağlanıyordu (2026-10-18 deneme: yabancı motor
 * istekleri reddetti, sonra kapandı, iki pencere birden gitti).
 *
 * Kural (sırayla):
 *  1. Bu profilin kayıtlı portunda bir motor var VE bu profilin oturum anahtarını kabul
 *     ediyorsa → o motor BİZİM öksüz motorumuz, yeniden kullan.
 *  2. 8791 boşsa → 8791 (alışılmış port).
 *  3. Değilse → işletim sisteminden boş bir port.
 * Başkasının motoruna (anahtarımızı kabul etmeyen) ASLA bağlanılmaz.
 *
 * Seçim senkron yapılır (`secSenkron`): uygulama.js modül yüklenirken BACKEND_URL'ü
 * kuruyor ve app-ready öncesi ayarlar var; bekletmeli yükleme sırayı bozardı.
 */
const VARSAYILAN_PORT = 8791;
const PORT_DOSYASI = 'motor-portu';
const CEREZ_ADI = 'yuki_oturum';

function portBos(net, port) {
  return new Promise((resolve) => {
    const s = net.createServer();
    s.once('error', () => resolve(false));
    s.once('listening', () => s.close(() => resolve(true)));
    s.listen(port, '127.0.0.1');
  });
}

function bosPort(net) {
  return new Promise((resolve, reject) => {
    const s = net.createServer();
    s.once('error', reject);
    s.listen(0, '127.0.0.1', () => { const p = s.address().port; s.close(() => resolve(p)); });
  });
}

/** Bu porttaki motor bizim anahtarımızı kabul ediyor mu (korumalı uç 200 dönüyor mu). */
function anahtariKabulEder(http, port, anahtar, zamanAsimiMs = 800) {
  return new Promise((resolve) => {
    const istek = http.get({
      host: '127.0.0.1', port, path: '/api/ping', timeout: zamanAsimiMs,
      headers: { cookie: `${CEREZ_ADI}=${anahtar}` },
    }, (res) => { res.resume(); resolve(res.statusCode === 200); });
    istek.on('timeout', () => { istek.destroy(); resolve(false); });
    istek.on('error', () => resolve(false));
  });
}

/**
 * @returns {Promise<{port:number, neden:'yeniden'|'varsayilan'|'bos'}>}
 */
async function sec({ net, http, kayitliPort, anahtar, varsayilan = VARSAYILAN_PORT }) {
  if (kayitliPort && anahtar && await anahtariKabulEder(http, kayitliPort, anahtar)) {
    return { port: kayitliPort, neden: 'yeniden' };
  }
  if (await portBos(net, varsayilan)) return { port: varsayilan, neden: 'varsayilan' };
  return { port: await bosPort(net), neden: 'bos' };
}

function oku(fs, path, dizin) {
  let kayitliPort = null; let anahtar = null;
  try {
    const p = parseInt(fs.readFileSync(path.join(dizin, PORT_DOSYASI), 'utf8').trim(), 10);
    if (p > 0 && p < 65536) kayitliPort = p;
  } catch (_) { /* ilk açılış */ }
  try { anahtar = fs.readFileSync(path.join(dizin, 'oturum-anahtari'), 'utf8').trim() || null; } catch (_) { /* yok */ }
  return { kayitliPort, anahtar };
}

/**
 * Senkron sarmalayıcı: Electron'u kısa ömürlü Node süreci olarak çağırıp `sec`'i koşturur.
 * Yoklama çökerse güvenli düşüş: 8791 (eski davranış).
 */
function secSenkron({ dizin, fs = require('fs'), path = require('path'), spawnSync = require('child_process').spawnSync,
  execPath = process.execPath, gunluk = () => {} }) {
  const { kayitliPort, anahtar } = oku(fs, path, dizin);
  const betik = `require(${JSON.stringify(__filename)}).sec({net:require('net'),http:require('http'),`
    + `kayitliPort:${JSON.stringify(kayitliPort)},anahtar:${JSON.stringify(anahtar)}})`
    + `.then(r=>process.stdout.write(JSON.stringify(r)),()=>process.exit(1))`;
  let sonuc = { port: VARSAYILAN_PORT, neden: 'varsayilan' };
  try {
    const r = spawnSync(execPath, ['-e', betik], {
      env: { ...process.env, ELECTRON_RUN_AS_NODE: '1' }, encoding: 'utf8', timeout: 5000,
    });
    if (r.status === 0 && r.stdout) sonuc = JSON.parse(r.stdout);
    else gunluk(`UYARI: motor portu yoklanamadı (çıkış ${r.status}) — ${VARSAYILAN_PORT}`);
  } catch (e) { gunluk(`UYARI: motor portu yoklanamadı (${e.message}) — ${VARSAYILAN_PORT}`); }
  try { fs.mkdirSync(dizin, { recursive: true }); fs.writeFileSync(path.join(dizin, PORT_DOSYASI), String(sonuc.port)); } catch (_) { /* yazılamazsa sonraki açılış yeniden yoklar */ }
  return sonuc;
}

module.exports = { VARSAYILAN_PORT, PORT_DOSYASI, sec, secSenkron, portBos, anahtariKabulEder, oku };
