/**
 * Tam paket self-update testleri — `node --test electron/`
 *
 * 🔒 Bu modül indirdiği ikiliyi KURULUMUN ÜSTÜNE yazar. Delta'dan da tehlikeli:
 * delta yalnız app kodunu değiştirir, bu her şeyi. Testlerin ağırlığı bu yüzden
 * "doğru olanı kabul etti"de değil, **"yanlış olanı reddetti"** ve
 * **"yapamayacağı şeyi teklif etmedi"** tarafında.
 */
const test = require('node:test');
const assert = require('node:assert');
const fs = require('fs');
const os = require('os');
const path = require('path');

const { TamGuncelleyici, skuTablosu, skuVarligi } = require('./tam-guncelleme');

const SHA_A = 'a'.repeat(64);
const SHA_B = 'b'.repeat(64);

function kur(opts = {}) {
  const tmp = fs.mkdtempSync(path.join(os.tmpdir(), 'yuki-tam-'));
  return {
    tmp,
    g: new TamGuncelleyici({
      sku: 'lite',
      execPath: path.join(tmp, 'kurulum', 'Yuki'),
      appImagePath: null,
      userDataDir: tmp,
      gunluk: () => {},
      platform: 'linux',
      ...opts,
    }),
  };
}

// ── SKU tablosu ayrıştırma ──────────────────────────────────────────────────

test('sku tablosu: düz string doğru ayrıştırılır', () => {
  const t = skuTablosu(`Yuki-1.0.0-lite.AppImage:${SHA_A}:123;Yuki-1.0.0-win-x64-lite.zip:${SHA_B}:456`);
  assert.strictEqual(t['Yuki-1.0.0-lite.AppImage'].sha256, SHA_A);
  assert.strictEqual(t['Yuki-1.0.0-lite.AppImage'].size, 123);
  assert.strictEqual(t['Yuki-1.0.0-win-x64-lite.zip'].size, 456);
});

test('sku tablosu: bozuk kayıtlar SESSİZCE atlanır, tablo kirlenmez', () => {
  // Bozuk bir kayıt yüzünden tüm tabloyu çöpe atmak da, geçersiz bir hash'i
  // tabloya almak da yanlış olurdu. Geçersiz olan girmez, geçerli olan kalır.
  const t = skuTablosu(`iyi:${SHA_A}:1;kotu-hash:xyz:2;eksik-alan:3;:${SHA_B}:4`);
  assert.deepStrictEqual(Object.keys(t), ['iyi']);
});

test('sku tablosu: boş/tanımsız girdi çökertmez', () => {
  assert.deepStrictEqual(skuTablosu(''), {});
  assert.deepStrictEqual(skuTablosu(undefined), {});
  assert.deepStrictEqual(skuTablosu(null), {});
});

test('sku varlığı: dört SKU da doğru dosya adına eşlenir', () => {
  assert.strictEqual(skuVarligi('lite', '0.6.0'), 'Yuki-0.6.0-lite.AppImage');
  assert.strictEqual(skuVarligi('offline', '0.6.0'), 'Yuki-0.6.0-offline.AppImage');
  assert.strictEqual(skuVarligi('win-x64-lite', '0.6.0'), 'Yuki-0.6.0-win-x64-lite.zip');
  assert.strictEqual(skuVarligi('win-x64-offline', '0.6.0'), 'Yuki-0.6.0-win-x64-offline.zip');
  assert.strictEqual(skuVarligi('uydurma', '0.6.0'), null);
});

// ── Dürüstlük kapısı: yapamayacağını teklif etme ────────────────────────────

test('destek: SKU damgası yoksa DESTEKLENMİYOR (eski paket)', () => {
  const { g } = kur({ sku: null });
  const d = g.destekleniyor();
  assert.strictEqual(d.ok, false);
  assert.match(d.sebep, /SKU damgası/);
});

test('destek: AppImage yolu yoksa DESTEKLENMİYOR', () => {
  const { g } = kur({ platform: 'linux', appImagePath: null });
  assert.strictEqual(g.destekleniyor().ok, false);
});

test('destek: tar.gz kullanıcısına AppImage sebebi SÖYLENMEZ (dürüst teşhis)', () => {
  // Linux'ta iki SKU var ve İKİSİ DE `yukiSku: lite` damgası taşıyor
  // (electron-builder.yml — AppImage ve tar.gz aynı yml'den çıkıyor). Yani SKU'ya
  // bakarak ayırt edilemezler; ayrım `process.env.APPIMAGE` (tar.gz'de YOK).
  //
  // Eski davranış: tar.gz kullanıcısına "AppImage yolu bulunamadı" deniyordu.
  // Bu, ElevenLabs'ın kota hatasına "geçersiz anahtar" demesinin aynısı — doğru
  // kapı, YANLIŞ sebep. Kullanıcı olmayan bir AppImage'ı aramaya gider.
  const { tmp } = kur({ platform: 'linux', appImagePath: null });
  const g = new TamGuncelleyici({
    sku: 'lite',
    execPath: path.join(tmp, 'yuki-0.6.2-lite', 'yuki'),   // paketli tar.gz kurulumu
    appImagePath: null,                                     // ← tar.gz'de APPIMAGE yok
    userDataDir: tmp, gunluk: () => {}, platform: 'linux',
  });
  const d = g.destekleniyor();
  assert.strictEqual(d.ok, false, 'tar.gz tam paket güncellemesi YAPAMAZ — kapı doğru');
  assert.strictEqual(d.targz, true, 'tar.gz olarak tanınmalı');
  assert.match(d.sebep, /tar\.gz/, 'sebep tar.gz demeli');
  assert.doesNotMatch(d.sebep, /AppImage/,
    'tar.gz kullanıcısına AppImage sebebi söylenirse yanlış çözümü arar');
});

// root için chmod 0555 yazmayı engellemez → bu ortamda klasör salt okunur kurulamaz, test ölçemez
// (konteynerde root olarak `node --test` koşunca kırmızıydı).
const ROOT = typeof process.getuid === 'function' && process.getuid() === 0;
test('destek: yazma izni yoksa DESTEKLENMİYOR (yarım kurulum riski)', { skip: ROOT && 'root: chmod yazmayı engellemez' }, () => {
  const { tmp, g } = kur({ platform: 'win32' });
  const kok = path.join(tmp, 'salt-okunur');
  fs.mkdirSync(kok);
  fs.chmodSync(kok, 0o555);
  const g2 = new TamGuncelleyici({
    sku: 'win-x64-lite', execPath: path.join(kok, 'Yuki.exe'),
    userDataDir: tmp, gunluk: () => {}, platform: 'win32',
  });
  const d = g2.destekleniyor();
  fs.chmodSync(kok, 0o755);   // temizlik yapılabilsin
  assert.strictEqual(d.ok, false, 'yazamadığı yere kurmayı teklif etmemeli');
  assert.match(d.sebep, /yazma izni/);
});

test('destek: bilinmeyen platformda DESTEKLENMİYOR', () => {
  const { g } = kur({ platform: 'darwin' });
  assert.strictEqual(g.destekleniyor().ok, false);
});

test('destek: yazılabilir AppImage → DESTEKLENİYOR', () => {
  const { tmp } = kur();
  const ai = path.join(tmp, 'Yuki-0.5.9-lite.AppImage');
  fs.writeFileSync(ai, 'ELF');
  const g = new TamGuncelleyici({
    sku: 'lite', execPath: ai, appImagePath: ai,
    userDataDir: tmp, gunluk: () => {}, platform: 'linux',
  });
  assert.strictEqual(g.destekleniyor().ok, true);
});

// ── Güvenlik: imzasız/eşleşmeyen indirme reddedilir ─────────────────────────

test('🔒 imzalı manifest o SKU için hash taşımıyorsa İNDİRİLMEZ', async () => {
  const { tmp } = kur();
  const ai = path.join(tmp, 'Yuki-0.5.9-lite.AppImage');
  fs.writeFileSync(ai, 'ELF');
  const g = new TamGuncelleyici({
    sku: 'lite', execPath: ai, appImagePath: ai,
    userDataDir: tmp, gunluk: () => {}, platform: 'linux',
  });
  // Manifest başka bir SKU'nun hash'ini taşıyor → bizimki imzalı değil demektir.
  const man = { skus: `Yuki-0.5.9-win-x64-lite.zip:${SHA_A}:10` };
  await assert.rejects(() => g.indirVeDogrula('0.5.9', man),
    /imzalı parmak izinde .* yok/);
});

test('🔒 skus alanı boşsa İNDİRİLMEZ (imzasız ikili çalıştırılmaz)', async () => {
  const { tmp } = kur();
  const ai = path.join(tmp, 'Yuki-0.5.9-lite.AppImage');
  fs.writeFileSync(ai, 'ELF');
  const g = new TamGuncelleyici({
    sku: 'lite', execPath: ai, appImagePath: ai,
    userDataDir: tmp, gunluk: () => {}, platform: 'linux',
  });
  await assert.rejects(() => g.indirVeDogrula('0.5.9', { skus: '' }), /güvenli indirilemez/);
  await assert.rejects(() => g.indirVeDogrula('0.5.9', {}), /güvenli indirilemez/);
});

test('desteklenmeyen kurulumda indirme bile denenmez', async () => {
  const { g } = kur({ sku: null });
  await assert.rejects(() => g.indirVeDogrula('0.5.9', { skus: `x:${SHA_A}:1` }),
    /yapılamıyor/);
});

// ── AppImage devri: eskisi YEDEKLENİR, yenisi yerine geçer ──────────────────

test('AppImage: devir sonrası eski sürüm .eski olarak DURUR (geri dönüş)', () => {
  const { tmp } = kur();
  const ai = path.join(tmp, 'Yuki-0.5.9-lite.AppImage');
  fs.writeFileSync(ai, 'ESKI-SURUM');
  const g = new TamGuncelleyici({
    sku: 'lite', execPath: ai, appImagePath: ai,
    userDataDir: tmp, gunluk: () => {}, platform: 'linux',
  });

  const indirme = path.join(tmp, 'yeni.AppImage');
  fs.writeFileSync(indirme, 'YENI-SURUM');

  g.kur({ dosya: indirme, ad: 'Yuki-0.6.0-lite.AppImage', version: '0.6.0' });

  assert.strictEqual(fs.readFileSync(ai, 'utf8'), 'YENI-SURUM', 'yeni sürüm yerine geçmeli');
  assert.strictEqual(fs.readFileSync(`${ai}.eski`, 'utf8'), 'ESKI-SURUM',
    'eski sürüm geri dönüş için durmalı');
  assert.ok(fs.statSync(ai).mode & 0o111, 'çalıştırılabilir olmalı');
});

test('kur: doğrulanmamış/eksik dosyayla çağrılırsa REDDEDİLİR', () => {
  const { tmp, g } = kur();
  assert.throws(() => g.kur({ dosya: path.join(tmp, 'yok.AppImage') }), /bulunamadı/);
  assert.throws(() => g.kur(null), /bulunamadı/);
});

// ── Windows yardımcısı ──────────────────────────────────────────────────────

test('Windows: yardımcı script yazılır ve kritik korumaları içerir', () => {
  const tmp = fs.mkdtempSync(path.join(os.tmpdir(), 'yuki-win-'));
  const kok = path.join(tmp, 'kurulum');
  fs.mkdirSync(kok);
  const exe = path.join(kok, 'Yuki.exe');
  fs.writeFileSync(exe, 'MZ');
  const zip = path.join(tmp, 'yeni.zip');
  fs.writeFileSync(zip, 'PK');

  const g = new TamGuncelleyici({
    sku: 'win-x64-lite', execPath: exe, userDataDir: tmp,
    gunluk: () => {}, platform: 'win32',
  });
  const r = g.kur({ dosya: zip, ad: 'Yuki-0.6.0-win-x64-lite.zip', version: '0.6.0' });
  assert.strictEqual(typeof r.yenidenBaslat, 'function');

  const ps = fs.readFileSync(path.join(tmp, 'updates', 'yuki-guncelle.ps1'), 'utf8');
  // Kurtarılamaz tek hata: kurulumu silip yerine bozuk/yarım bir şey koymak.
  assert.match(ps, /Get-Process -Id \$pidEski/, 'uygulamanın kapanmasını beklemeli');
  assert.match(ps, /Move-Item -Path \$kok -Destination \$yedek/, 'eskisini yedeklemeli');
  assert.match(ps, /if \(-not \(Test-Path \$yeniExe\)\)/,
    'yeni pakette exe yoksa DURMALI — bozuk arşivle kurulum değiştirilmemeli');
  assert.match(ps, /Move-Item -Path \$yedek -Destination \$kok/,
    'başarısızlıkta eskisini geri koymalı');
  assert.match(ps, /Add-Content -Path \$log/, 'her adımı günlüğe yazmalı');
  // PowerShell tercihi bilinçli (.bat kod sayfası sorunu) — sessizce .bat'a dönülmesin
  assert.ok(!/\.bat/i.test(ps));
});

test('Windows: yollar JSON ile kodlanır (boşluk/Türkçe karakter kırmaz)', () => {
  const tmp = fs.mkdtempSync(path.join(os.tmpdir(), 'yuki-win2-'));
  const kok = path.join(tmp, 'Program Files', 'Yuki AI');
  fs.mkdirSync(kok, { recursive: true });
  const exe = path.join(kok, 'Yuki.exe');
  fs.writeFileSync(exe, 'MZ');
  const zip = path.join(tmp, 'y.zip');
  fs.writeFileSync(zip, 'PK');

  const g = new TamGuncelleyici({
    sku: 'win-x64-lite', execPath: exe, userDataDir: tmp,
    gunluk: () => {}, platform: 'win32',
  });
  g.kur({ dosya: zip, ad: 'a.zip', version: '0.6.0' });
  const ps = fs.readFileSync(path.join(tmp, 'updates', 'yuki-guncelle.ps1'), 'utf8');
  assert.ok(ps.includes(JSON.stringify(kok)), 'boşluklu yol tırnaklanmış olmalı');
});
