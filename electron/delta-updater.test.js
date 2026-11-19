/**
 * Delta güncelleyici testleri — `node --test electron/`
 *
 * 🔒 Bu modül UZAKTAN KOD ÇALIŞTIRMA kanalıdır: doğru yükü kabul etmesi yetmez,
 * YANLIŞ olanı reddettiği kanıtlanmalı. Testlerin ağırlığı bilerek reddetme
 * tarafında — "kabul etti" kolay, "reddetmesi gerekeni reddetti" zor olan.
 *
 * Bağımlılık yok (node:test + node:assert), çünkü güvenlik-kritik yolun test
 * takımına üçüncü parti sokmak tedarik zinciri yüzeyini büyütür.
 */
const test = require('node:test');
const assert = require('node:assert');
const crypto = require('crypto');
const fs = require('fs');
const os = require('os');
const path = require('path');
const zlib = require('zlib');

const { DeltaUpdater, canonical, guvenliYol, tarOku } = require('./delta-updater');

// ── yardımcılar ─────────────────────────────────────────────────────────────

const SPKI = Buffer.from('302a300506032b6570032100', 'hex');
const pubKeyOf = (raw) => crypto.createPublicKey({
  key: Buffer.concat([SPKI, raw]), format: 'der', type: 'spki',
});

function ciftUret() {
  const { publicKey, privateKey } = crypto.generateKeyPairSync('ed25519');
  return {
    priv: privateKey,
    pubRaw: publicKey.export({ format: 'der', type: 'spki' }).subarray(12),
  };
}

/** Minimal tar üretici — testin kendi girdisini kurabilmesi için. */
function tarUret(girdiler) {
  const bloklar = [];
  for (const { ad, veri } of girdiler) {
    const bas = Buffer.alloc(512);
    bas.write(ad, 0, 100, 'utf8');
    bas.write('0000644\0', 100, 8, 'ascii');
    bas.write('0000000\0', 108, 8, 'ascii');
    bas.write('0000000\0', 116, 8, 'ascii');
    bas.write(veri.length.toString(8).padStart(11, '0') + '\0', 124, 12, 'ascii');
    bas.write('00000000000\0', 136, 12, 'ascii');
    bas.write('        ', 148, 8, 'ascii');          // sağlama alanı: hesaplarken boşluk
    bas.write('0', 156, 1, 'ascii');                 // düz dosya
    let toplam = 0;
    for (let i = 0; i < 512; i++) toplam += bas[i];
    bas.write(toplam.toString(8).padStart(6, '0') + '\0 ', 148, 8, 'ascii');
    bloklar.push(bas, veri, Buffer.alloc((512 - (veri.length % 512)) % 512));
  }
  bloklar.push(Buffer.alloc(1024));
  return Buffer.concat(bloklar);
}

// ── kanonik biçim ───────────────────────────────────────────────────────────

test('kanonik biçim anahtar sırasından bağımsız', () => {
  const a = canonical({ b: 2, a: 1, c: 'x' });
  const b = canonical({ c: 'x', a: 1, b: 2 });
  assert.strictEqual(a.toString(), b.toString());
  assert.strictEqual(a.toString(), '{"a":1,"b":2,"c":"x"}');
});

test('kanonik biçim Python json.dumps(sort_keys,separators) ile aynı', () => {
  // Python: json.dumps({"v":"1.0","n":3}, sort_keys=True, separators=(",",":"))
  assert.strictEqual(canonical({ v: '1.0', n: 3 }).toString(), '{"n":3,"v":"1.0"}');
});

// ── imza ────────────────────────────────────────────────────────────────────

test('imza: değiştirilmemiş manifest kabul, her kurcalama RED', () => {
  const { priv, pubRaw } = ciftUret();
  const man = {
    schema: 1, product: 'yuki', version: '0.5.6',
    shell_id: 'a'.repeat(32), payload_name: 'p.tar.gz',
    payload_sha256: 'b'.repeat(64), payload_size: 100, file_count: 5,
  };
  const sig = crypto.sign(null, canonical(man), priv);
  const dogrula = (m) => crypto.verify(null, canonical(m), pubKeyOf(pubRaw), sig);

  assert.ok(dogrula(man), 'orijinal kabul edilmeli');
  for (const [alan, deger] of [
    ['version', '9.9.9'],
    ['payload_sha256', 'c'.repeat(64)],
    ['payload_name', 'kotu.tar.gz'],
    ['shell_id', 'd'.repeat(32)],
    ['product', 'baska'],
    ['file_count', 6],
  ]) {
    assert.ok(!dogrula({ ...man, [alan]: deger }), `'${alan}' kurcalandı → reddedilmeliydi`);
  }
  assert.ok(!dogrula({ ...man, ekstra: 'x' }), 'alan eklendi → reddedilmeliydi');
  const { pubRaw: baskaPub } = ciftUret();
  assert.ok(!crypto.verify(null, canonical(man), pubKeyOf(baskaPub), sig),
            'saldırganın anahtarı → reddedilmeliydi');
});

// ── yol güvenliği (tar-slip) ────────────────────────────────────────────────

test('yol: yalnız izinli kökler kabul edilir', () => {
  const kok = path.join(os.tmpdir(), 'yuki-yol-testi');
  for (const y of ['backend/app/main.py', 'frontend/js/core.js', 'frontend/index.html']) {
    assert.ok(guvenliYol(kok, y), `${y} kabul edilmeliydi`);
  }
});

test('yol: kaçış denemelerinin HEPSİ reddedilir', () => {
  const kok = path.join(os.tmpdir(), 'yuki-yol-testi');
  const saldirilar = [
    '../../../../etc/passwd',
    'backend/app/../../../../etc/passwd',
    '/etc/passwd',
    'C:/Windows/System32/evil.dll',
    'backend\\app\\evil.py',           // ters bölü (Windows ayracı)
    'backend/app/evil\u0000.py',       // NUL enjeksiyonu
    'pybundle-win/python.exe',          // izinli kök dışı — runtime'a dokunma
    'backend/run.py',                   // app/ dışı — kabuk dosyası
    '../updates/current.json',          // güncelleyicinin kendi durumu
    'backend/app/./x.py',
    '',
  ];
  for (const y of saldirilar) {
    assert.strictEqual(guvenliYol(kok, y), null, `${JSON.stringify(y)} REDDEDİLMELİYDİ`);
  }
});

// ── tar ayrıştırıcı ─────────────────────────────────────────────────────────

test('tar: düz dosyaları doğru okur', () => {
  const buf = tarUret([
    { ad: 'backend/app/x.py', veri: Buffer.from('print(1)') },
    { ad: 'frontend/a.css', veri: Buffer.from('body{}') },
  ]);
  const g = tarOku(buf);
  assert.strictEqual(g.length, 2);
  assert.strictEqual(g[0].ad, 'backend/app/x.py');
  assert.strictEqual(g[0].veri.toString(), 'print(1)');
  assert.strictEqual(g[1].veri.toString(), 'body{}');
});

test('tar: bozuk başlık sağlaması REDDEDİLİR', () => {
  const buf = tarUret([{ ad: 'backend/app/x.py', veri: Buffer.from('x') }]);
  buf[0] = 'Z'.charCodeAt(0);                 // adı boz → sağlama tutmaz
  assert.throws(() => tarOku(buf), /sağlaması tutmadı/);
});

test('tar: sembolik bağ girdisi REDDEDİLİR', () => {
  const buf = tarUret([{ ad: 'backend/app/x.py', veri: Buffer.alloc(0) }]);
  buf[156] = '2'.charCodeAt(0);               // tip 2 = symlink
  let toplam = 0;
  for (let i = 0; i < 512; i++) toplam += (i >= 148 && i < 156) ? 32 : buf[i];
  buf.write(toplam.toString(8).padStart(6, '0') + '\0 ', 148, 8, 'ascii');
  assert.throws(() => tarOku(buf), /Beklenmeyen tar girdi tipi/);
});

test('tar: 18 MB girdi (yuki3d.vrm boyutu) artık KABUL EDİLİR', () => {
  const buf = tarUret([
    { ad: 'frontend/assets/characters/yuki3d.vrm', veri: Buffer.alloc(18 * 1024 * 1024) },
  ]);
  const g = tarOku(buf);
  assert.strictEqual(g.length, 1);
  assert.strictEqual(g[0].veri.length, 18 * 1024 * 1024);
});

test('tar: 33 MB girdi (yeni 32 MiB tavanın üstü) yine REDDEDİLİR', () => {
  const buf = tarUret([
    { ad: 'frontend/assets/characters/dev.vrm', veri: Buffer.alloc(33 * 1024 * 1024) },
  ]);
  assert.throws(() => tarOku(buf), /çok büyük|too large|Girdi/i);
});

// ── geri alma ───────────────────────────────────────────────────────────────

test('geri alma: MAX_FAIL denemeden sonra overlay atılır', () => {
  const tmp = fs.mkdtempSync(path.join(os.tmpdir(), 'yuki-geri-'));
  const ovDir = path.join(tmp, 'updates', '0.5.6');
  fs.mkdirSync(path.join(ovDir, 'backend', 'app'), { recursive: true });
  fs.writeFileSync(path.join(ovDir, 'backend', 'app', 'main.py'), '# x');
  fs.writeFileSync(path.join(tmp, 'updates', 'current.json'),
    JSON.stringify({ version: '0.5.6', dir: ovDir, failCount: 0 }));

  const u = new DeltaUpdater({ userDataDir: tmp, shellId: 'x', currentVersion: '0.5.5' });
  assert.strictEqual(u.saglikli().kullan, true, 'sağlam overlay kullanılmalı');

  for (let i = 0; i < DeltaUpdater.MAX_FAIL; i++) u.denemeIsaretle();
  const s = u.saglikli();
  assert.strictEqual(s.kullan, false, 'üst üste başarısızlıkta kullanılmamalı');
  assert.strictEqual(s.geriAlinmali, true);

  u.geriAl('test');
  assert.strictEqual(u.applied(), null, 'geri alma sonrası overlay kalmamalı');
  assert.ok(!fs.existsSync(ovDir), 'overlay dizini silinmeliydi');
  fs.rmSync(tmp, { recursive: true, force: true });
});

test('geri alma: başarılı açılış sayacı sıfırlar', () => {
  const tmp = fs.mkdtempSync(path.join(os.tmpdir(), 'yuki-geri2-'));
  const ovDir = path.join(tmp, 'updates', '0.5.6');
  fs.mkdirSync(path.join(ovDir, 'backend', 'app'), { recursive: true });
  fs.writeFileSync(path.join(ovDir, 'backend', 'app', 'main.py'), '# x');
  fs.writeFileSync(path.join(tmp, 'updates', 'current.json'),
    JSON.stringify({ version: '0.5.6', dir: ovDir, failCount: 0 }));

  const u = new DeltaUpdater({ userDataDir: tmp, shellId: 'x', currentVersion: '0.5.5' });
  u.denemeIsaretle();
  u.denemeIsaretle();
  u.basariliIsaretle();
  assert.strictEqual(u.applied().failCount, 0, 'sağlıklı açılış sayacı sıfırlamalı');
  // Sayaç sıfırlanmasaydı sağlam bir güncelleme 3. açılışta boş yere geri alınırdı.
  assert.strictEqual(u.saglikli().kullan, true);
  fs.rmSync(tmp, { recursive: true, force: true });
});

test('overlay: main.py yoksa uygulanmış sayılmaz (yarım kurulum)', () => {
  const tmp = fs.mkdtempSync(path.join(os.tmpdir(), 'yuki-yarim-'));
  const ovDir = path.join(tmp, 'updates', '0.5.6');
  fs.mkdirSync(ovDir, { recursive: true });
  fs.writeFileSync(path.join(tmp, 'updates', 'current.json'),
    JSON.stringify({ version: '0.5.6', dir: ovDir }));
  const u = new DeltaUpdater({ userDataDir: tmp, shellId: 'x', currentVersion: '0.5.5' });
  assert.strictEqual(u.applied(), null, 'içi boş overlay geçerli sayılmamalı');
  fs.rmSync(tmp, { recursive: true, force: true });
});

// ── kardeş aynalama ─────────────────────────────────────────────────────────

test('aynalama: app dışı kardeşler overlay köküne gelir', () => {
  const tmp = fs.mkdtempSync(path.join(os.tmpdir(), 'yuki-ayna-'));
  const paket = path.join(tmp, 'paket-backend');
  fs.mkdirSync(path.join(paket, 'app'), { recursive: true });
  fs.mkdirSync(path.join(paket, 'skills'), { recursive: true });
  fs.writeFileSync(path.join(paket, 'mcp_servers.json'), '{}');
  fs.writeFileSync(path.join(paket, 'run.py'), '# run');
  fs.writeFileSync(path.join(paket, 'app', 'main.py'), '# PAKET');

  const ov = path.join(tmp, 'ov', 'backend');
  fs.mkdirSync(path.join(ov, 'app'), { recursive: true });
  fs.writeFileSync(path.join(ov, 'app', 'main.py'), '# OVERLAY');

  const u = new DeltaUpdater({ userDataDir: tmp, shellId: 'x', currentVersion: '1',
                               packagedBackendDir: paket });
  u._kardesleriAynala(ov);

  assert.ok(fs.existsSync(path.join(ov, 'mcp_servers.json')), 'mcp_servers.json aynalanmalı');
  assert.ok(fs.existsSync(path.join(ov, 'skills')), 'skills/ aynalanmalı');
  assert.ok(fs.existsSync(path.join(ov, 'run.py')), 'run.py aynalanmalı');
  // app OVERLAY'inki kalmalı — aynalama onu ezmemeli, yoksa güncelleme hiç uygulanmaz
  assert.strictEqual(fs.readFileSync(path.join(ov, 'app', 'main.py'), 'utf8'), '# OVERLAY');
  fs.rmSync(tmp, { recursive: true, force: true });
});

test('aynalama: kritik kardeş kurulamazsa HATA verir (sessizce geçmez)', () => {
  const tmp = fs.mkdtempSync(path.join(os.tmpdir(), 'yuki-ayna2-'));
  const u = new DeltaUpdater({ userDataDir: tmp, shellId: 'x', currentVersion: '1',
                               packagedBackendDir: path.join(tmp, 'olmayan') });
  assert.throws(() => u._kardesleriAynala(path.join(tmp, 'ov')),
                /Paketlenmiş backend dizini bulunamadı/);
  fs.rmSync(tmp, { recursive: true, force: true });
});

// ── Medya katmanı (2026-08-08) ──────────────────────────────────────────────
//
// Bu katman `frontend/assets`'i (33 MB görsel/klip) delta ile taşınabilir kıldı.
// Öncesinde medya `shell_id`'ye giriyordu, yani DEĞİŞTİĞİ her sürümde müşteri
// tarayıcıya gönderilip 440 MB tam paket indiriyordu.
//
// Testlerin ağırlığı yine reddetme ve KAYBETMEME tarafında: en pahalı hata
// "medya indi ama gösterilmiyor" ya da "indirdiği medya silindi" olurdu —
// ikisi de sessizdir, kullanıcı güncellendiğini sanar.

function medyaKurulumu(mediaId) {
  const tmp = fs.mkdtempSync(path.join(os.tmpdir(), 'yuki-medya-'));
  const u = new DeltaUpdater({
    userDataDir: tmp,
    shellId: 'kabuk1',
    currentVersion: '0.5.9',
    packagedBackendDir: tmp,
    packagedMediaId: mediaId,
    gunluk: () => {},
  });
  fs.mkdirSync(u.updatesDir, { recursive: true });
  return { tmp, u };
}

test('medya: kimlik yoksa paketinki geçerlidir', () => {
  const { u } = medyaKurulumu('paket-medya-1');
  assert.strictEqual(u.etkinMediaId(), 'paket-medya-1');
  assert.strictEqual(u.medyaKoku(), null, 'indirilmiş katman yokken kök verilmemeli');
});

test('medya: uygulanan katman paketinkini GÖLGELER', () => {
  const { u } = medyaKurulumu('paket-medya-1');
  fs.mkdirSync(path.join(u.medyaDir, 'frontend', 'assets'), { recursive: true });
  fs.writeFileSync(path.join(u.medyaStatePath),
    JSON.stringify({ mediaId: 'yeni-medya-2' }), 'utf8');
  assert.strictEqual(u.etkinMediaId(), 'yeni-medya-2');
  assert.ok(u.medyaKoku().endsWith(path.join('media', 'frontend')),
    'backend bu kökü YUKI_MEDIA_DIR olarak almalı');
});

test('medya: state var ama dosyalar yoksa katman YOK sayılır', () => {
  // Kullanıcı `updates/media`'yı elle silerse state yalancı şahit olmamalı.
  const { u } = medyaKurulumu('paket-medya-1');
  fs.writeFileSync(u.medyaStatePath, JSON.stringify({ mediaId: 'hayalet' }), 'utf8');
  assert.strictEqual(u.medyaKoku(), null);
  assert.strictEqual(u.etkinMediaId(), 'paket-medya-1',
    'dizin yoksa paketin kimliğine dönülmeli, "hayalet" değil');
});

test('🔴 medya: kod güncellemesinin temizliği medya katmanını SİLMEZ', () => {
  // Bu testin varlık sebebi: `_eskileriTemizle` başlangıçta `updates/` altında
  // korunanlar dışındaki HER ŞEYİ siliyordu. Medya oraya konunca, her kod
  // güncellemesi kullanıcının indirdiği 33 MB'ı silip onu sessizce paketin
  // fabrika görsellerine düşürürdü.
  const { u } = medyaKurulumu('paket-1');
  fs.mkdirSync(path.join(u.medyaDir, 'frontend', 'assets'), { recursive: true });
  fs.writeFileSync(path.join(u.medyaDir, 'frontend', 'assets', 'yuki.png'), 'PNG');
  fs.writeFileSync(u.medyaStatePath, JSON.stringify({ mediaId: 'm2' }), 'utf8');
  fs.mkdirSync(path.join(u.updatesDir, '0.5.8'), { recursive: true });   // eski overlay

  u._eskileriTemizle('0.5.9');

  assert.ok(fs.existsSync(path.join(u.medyaDir, 'frontend', 'assets', 'yuki.png')),
    'medya katmanı korunmalıydı');
  assert.ok(fs.existsSync(u.medyaStatePath), 'medya durumu korunmalıydı');
  assert.ok(!fs.existsSync(path.join(u.updatesDir, '0.5.8')),
    'eski overlay yine de temizlenmeli (temizlik büsbütün kapanmasın)');
});

test('🔴 medya: kod bütünlük kökü medyayı SAYMAZ (iki yük, iki kök)', () => {
  // Kod kökü medyayı sayarsa: kod yükü uygulanır → files_root hesaplanır →
  // medya ayrı geldiği için tutmaz → sapasağlam overlay her açılışta reddedilir.
  const { u, tmp } = medyaKurulumu('m1');
  const ov = path.join(tmp, 'ov');
  fs.mkdirSync(path.join(ov, 'frontend', 'assets'), { recursive: true });
  fs.writeFileSync(path.join(ov, 'frontend', 'core.js'), 'kod');
  const kokMedyasiz = u.agacKoku(ov);

  fs.writeFileSync(path.join(ov, 'frontend', 'assets', 'dev.png'), 'X'.repeat(1000));
  assert.strictEqual(u.agacKoku(ov), kokMedyasiz,
    'assets altına dosya eklemek KOD kökünü değiştirmemeli');

  const mKok = u.agacKoku(ov, { medya: true });
  assert.notStrictEqual(mKok, kokMedyasiz, 'medya kökü ayrı bir şey ölçmeli');
  fs.writeFileSync(path.join(ov, 'frontend', 'assets', 'dev.png'), 'Y'.repeat(1000));
  assert.notStrictEqual(u.agacKoku(ov, { medya: true }), mKok,
    'medya değişimi MEDYA kökünde görünmeli');
});

test('medya: yükün assets dışına yazması REDDEDİLİR', () => {
  const { u } = medyaKurulumu('m1');
  const man = { media_file_count: 1, media_root: 'x', media_id: 'm2' };
  const kotu = zlib.gzipSync(tarUret([{ ad: 'backend/app/main.py', veri: Buffer.from('zararlı') }]));
  assert.throws(() => u._medyaUygula(kotu, man), /kendi kökünün dışına/);
  assert.ok(!fs.existsSync(u.medyaDir), 'reddedilen yükten sonra katman oluşmamalı');
});

test('medya: kök tutmazsa hiçbir şey yazılmaz (atomik)', () => {
  const { u } = medyaKurulumu('m1');
  const man = { media_file_count: 1, media_root: 'tutmayan-kok', media_id: 'm2' };
  const yuk = zlib.gzipSync(tarUret([
    { ad: 'frontend/assets/a.png', veri: Buffer.from('PNG') },
  ]));
  assert.throws(() => u._medyaUygula(yuk, man), /manifest'le tutmuyor/);
  assert.ok(!fs.existsSync(u.medyaDir), 'başarısız uygulama katman bırakmamalı');
  assert.strictEqual(u.etkinMediaId(), 'm1', 'kimlik güncellenmemeli');
});

test('medya: geçerli yük uygulanır ve kimlik güncellenir', () => {
  const { u } = medyaKurulumu('m1');
  const girisler = [{ ad: 'frontend/assets/a.png', veri: Buffer.from('PNG-VERI') }];
  const yuk = zlib.gzipSync(tarUret(girisler));

  // Beklenen kökü, uygulamanın kendi hesabıyla üret (elle yazılan bir sabit,
  // formül değişince testi sessizce yanlış yere bağlardı).
  const gec = fs.mkdtempSync(path.join(os.tmpdir(), 'yuki-mkok-'));
  fs.mkdirSync(path.join(gec, 'frontend', 'assets'), { recursive: true });
  fs.writeFileSync(path.join(gec, 'frontend', 'assets', 'a.png'), 'PNG-VERI');
  const beklenenKok = u.agacKoku(gec, { medya: true });

  u._medyaUygula(yuk, { media_file_count: 1, media_root: beklenenKok, media_id: 'm2' });

  assert.strictEqual(u.etkinMediaId(), 'm2');
  assert.strictEqual(
    fs.readFileSync(path.join(u.medyaDir, 'frontend', 'assets', 'a.png'), 'utf8'),
    'PNG-VERI');
});
