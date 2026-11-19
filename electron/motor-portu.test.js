'use strict';
const test = require('node:test');
const assert = require('node:assert');
const net = require('net');
const http = require('http');
const fs = require('fs');
const os = require('os');
const path = require('path');
const mp = require('./motor-portu');

// Sahte motor: /api/ping yalnız doğru çerezle 200, yoksa 401 (yerel_kapi.py davranışı)
function sahteMotor(anahtar) {
  return new Promise((resolve) => {
    const s = http.createServer((req, res) => {
      const ok = req.url === '/api/ping' && (req.headers.cookie || '').includes(`yuki_oturum=${anahtar}`);
      res.statusCode = ok ? 200 : 401; res.end();
    });
    s.listen(0, '127.0.0.1', () => resolve(s));
  });
}
const kapat = (s) => new Promise((r) => s.close(r));

test('varsayılan port boşsa onu seçer', async () => {
  const bos = await new Promise((r) => { const s = net.createServer(); s.listen(0, '127.0.0.1', () => { const p = s.address().port; s.close(() => r(p)); }); });
  const r = await mp.sec({ net, http, kayitliPort: null, anahtar: null, varsayilan: bos });
  assert.deepStrictEqual(r, { port: bos, neden: 'varsayilan' });
});

test('varsayılan port BAŞKA kopyanın motorundaysa ona bağlanmaz, boş port seçer', async () => {
  const yabanci = await sahteMotor('baskasinin-anahtari');
  const dolu = yabanci.address().port;
  // Kayıtlı port da o (eski sabit 8791 düzeni), ama anahtarımız orada geçmiyor
  const r = await mp.sec({ net, http, kayitliPort: dolu, anahtar: 'benim-anahtarim', varsayilan: dolu });
  await kapat(yabanci);
  assert.strictEqual(r.neden, 'bos');
  assert.notStrictEqual(r.port, dolu);
});

test('kendi öksüz motorumuz (anahtarı kabul ediyor) yeniden kullanılır', async () => {
  const bizim = await sahteMotor('benim-anahtarim');
  const p = bizim.address().port;
  const r = await mp.sec({ net, http, kayitliPort: p, anahtar: 'benim-anahtarim', varsayilan: p });
  await kapat(bizim);
  assert.deepStrictEqual(r, { port: p, neden: 'yeniden' });
});

test('secSenkron: ayrı süreçte yoklar, kendi motorunu bulur ve portu kaydeder', async () => {
  const bizim = await sahteMotor('k1');
  const p = bizim.address().port;
  const dizin = fs.mkdtempSync(path.join(os.tmpdir(), 'motor-portu-'));
  fs.writeFileSync(path.join(dizin, mp.PORT_DOSYASI), String(p));
  fs.writeFileSync(path.join(dizin, 'oturum-anahtari'), 'k1');
  // spawnSync ana döngüyü bloklar → sahte motor cevap veremez; motoru ayrı süreçte koştur
  await kapat(bizim);
  const { spawn } = require('child_process');
  const cocuk = spawn(process.execPath, ['-e', `require('http').createServer((q,s)=>{s.statusCode=(q.headers.cookie||'').includes('yuki_oturum=k1')?200:401;s.end()}).listen(${p},'127.0.0.1',()=>console.log('hazir'))`]);
  await new Promise((r) => cocuk.stdout.once('data', r));
  const r = mp.secSenkron({ dizin });
  cocuk.kill();
  assert.deepStrictEqual(r, { port: p, neden: 'yeniden' });
  assert.strictEqual(fs.readFileSync(path.join(dizin, mp.PORT_DOSYASI), 'utf8'), String(p));
});

test('uygulama.js sabit 8791 taşımıyor, portu motor-portu.js seçiyor', () => {
  const src = fs.readFileSync(path.join(__dirname, 'uygulama.js'), 'utf8');
  assert.ok(!/BACKEND_URL\s*=\s*'http:\/\/127\.0\.0\.1:8791'/.test(src), 'sabit BACKEND_URL geri gelmiş');
  assert.ok(!/PORT:\s*'8791'/.test(src), 'motora sabit PORT veriliyor');
  assert.match(src, /motorPortu\.secSenkron\(/);
});
