// Yerel motor oturum anahtarı — üretim, sağ kalan motor için dosyadan okuma, çerez ayarları.
//   node --test electron/oturum-anahtari.test.js

const test = require('node:test');
const assert = require('node:assert');
const fs = require('fs');
const os = require('os');
const path = require('path');
const crypto = require('crypto');
const m = require('./oturum-anahtari');

const dizin = () => fs.mkdtempSync(path.join(os.tmpdir(), 'oturum-'));

test('yeni anahtar: 64 hex, her açılışta farklı, dosyaya 0600 yazılır', () => {
  const d = dizin();
  const a = m.yeniAnahtar({ fs, path, crypto, dizin: d });
  const b = m.yeniAnahtar({ fs, path, crypto, dizin: d });
  assert.match(a, /^[0-9a-f]{64}$/);
  assert.notStrictEqual(a, b);
  assert.strictEqual(m.kayitliAnahtar({ fs, path, dizin: d }), b, 'son üretilen okunmalı');
  if (process.platform !== 'win32') {
    assert.strictEqual(fs.statSync(path.join(d, m.DOSYA_ADI)).mode & 0o777, 0o600);
  }
});

test('kayıtlı anahtar: dosya yok ya da bozuk → null', () => {
  const d = dizin();
  assert.strictEqual(m.kayitliAnahtar({ fs, path, dizin: d }), null);
  fs.writeFileSync(path.join(d, m.DOSYA_ADI), 'kısa');
  assert.strictEqual(m.kayitliAnahtar({ fs, path, dizin: d }), null);
});

test('çerez: her oturuma HttpOnly + SameSite=Strict + süresiz (diske düşmez)', async () => {
  const kayit = [];
  const oturum = () => ({ cookies: { set: async (c) => { kayit.push(c); } } });
  const n = await m.cerezleriKur({ oturumlar: [oturum(), null, oturum()], url: 'http://127.0.0.1:8791', anahtar: 'x' });
  assert.strictEqual(n, 2);
  for (const c of kayit) {
    assert.deepStrictEqual(
      { url: c.url, name: c.name, value: c.value, httpOnly: c.httpOnly, sameSite: c.sameSite },
      { url: 'http://127.0.0.1:8791', name: m.CEREZ_ADI, value: 'x', httpOnly: true, sameSite: 'strict' });
    assert.strictEqual(c.expirationDate, undefined);
  }
});

test('çerez adı motorla aynı (backend/app/yerel_kapi.py CEREZ_ADI)', () => {
  const py = fs.readFileSync(path.join(__dirname, '..', 'backend', 'app', 'yerel_kapi.py'), 'utf8');
  assert.ok(py.includes(`CEREZ_ADI = "${m.CEREZ_ADI}"`), 'iki taraf ayrışırsa her istek 401 olur');
});

test('uygulama.js: anahtar motora verilir ve loadURL öncesi çerez kurulur', () => {
  const src = fs.readFileSync(path.join(__dirname, 'uygulama.js'), 'utf8');
  assert.ok(src.includes('YUKI_OTURUM_ANAHTARI: OTURUM_ANAHTARI'));
  const cerez = src.indexOf('oturumAnahtari.cerezleriKur(');
  const yukle = src.lastIndexOf("win.loadURL(BACKEND_URL + '/')");
  assert.ok(cerez > 0 && cerez < yukle, 'çerez arayüz yüklenmeden ÖNCE kurulmalı');
});
