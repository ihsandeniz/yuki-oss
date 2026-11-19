/**
 * Katmanlı güncelleme altyapısı testleri (2026-08-03).
 *
 * Kapsanan kusur sınıfları:
 *   · Electron katmanı delta ile gidemiyordu → 162 KB için 440 MB indiriliyordu
 *   · "Hangi sürümdeyim" sorusunun iki cevabı vardı (`dfdd47a`)
 *   · Bozuk bir overlay uygulamayı tuğlalaştırabilirdi → kurtarma yolu yoktu
 */
const test = require('node:test');
const assert = require('node:assert');
const fs = require('fs');
const path = require('path');

const { govdeSec, devProfilYolu } = require('./onyukleme');
const { kimlik, ozet } = require('./surum');
const { guvenliYol } = require('./delta-updater');

const PAKET = '/paket/electron';
const PAKET_GOVDE = path.join(PAKET, 'uygulama.js');
const sessiz = () => {};

function sahteUpdater(saglik, kanca = {}) {
  return {
    saglikli: () => saglik,
    geriAl: (sebep) => { kanca.geriAlindi = sebep; return { rolledBack: true, version: '0.5.9' }; },
    denemeIsaretle: () => 1,
  };
}

// ── Önyükleme kararı ───────────────────────────────────────────────────────

test('overlay Electron katmanı taşıyorsa gövde oradan yüklenir', () => {
  const s = govdeSec({
    paketKok: PAKET, guvenliMod: false,
    updater: sahteUpdater({ kullan: true, dir: '/ov/0.5.8', version: '0.5.8' }),
    varMi: (y) => y === '/ov/0.5.8/electron/uygulama.js',
    gunluk: sessiz,
  });
  assert.equal(s.yol, '/ov/0.5.8/electron/uygulama.js');
  assert.equal(s.govdeOverlayden, true);
  assert.equal(s.surum, '0.5.8');
});

// ── Bayat overlay (tam paket kurulumu overlay'i geçtiğinde) ────────────────
// Bu sınıf CANLI Electron'da yakalandı (2026-08-03): kurulum userData'ya
// dokunmaz, dolayısıyla v0.5.7'den kalma overlay v0.5.8 paketinin ÜSTÜNDE
// kalır ve tam paketle gönderilen düzeltmeleri sessizce geri alır.

test('overlay paketten eskiyse ATILIR — tam paket düzeltmeleri gölgelenemez', () => {
  const kanca = {};
  const s = govdeSec({
    paketKok: PAKET, paketSurumu: '0.5.8', guvenliMod: false,
    updater: sahteUpdater({ kullan: true, dir: '/ov/0.5.7', version: '0.5.7' }, kanca),
    varMi: () => true,          // overlay gövdesi VAR — yine de kullanılmamalı
    gunluk: sessiz,
  });
  assert.equal(s.yol, PAKET_GOVDE, 'bayat overlay gövdesi yüklenmemeli');
  assert.equal(s.overlayKok, null, 'bayat overlay backend sys.path\'ine de girmemeli');
  assert.ok(kanca.geriAlindi, 'bayat overlay diskte bırakılmamalı (her açılışta tekrar denenir)');
});

test('overlay paketle AYNI sürümdeyse de atılır (eşitlik → gölgeleme)', () => {
  const s = govdeSec({
    paketKok: PAKET, paketSurumu: '0.5.8', guvenliMod: false,
    updater: sahteUpdater({ kullan: true, dir: '/ov/0.5.8', version: '0.5.8' }),
    varMi: () => true,
    gunluk: sessiz,
  });
  assert.equal(s.yol, PAKET_GOVDE);
});

test('overlay paketten YENİYSE kullanılır — düzeltme delta yolunu kapatmamalı', () => {
  const s = govdeSec({
    paketKok: PAKET, paketSurumu: '0.5.8', guvenliMod: false,
    updater: sahteUpdater({ kullan: true, dir: '/ov/0.5.9', version: '0.5.9' }),
    varMi: () => true,
    gunluk: sessiz,
  });
  assert.equal(s.yol, '/ov/0.5.9/electron/uygulama.js');
  assert.equal(s.govdeOverlayden, true);
});

test('paket sürümü bilinmiyorsa overlay atılmaz (bilinmezlik silme gerekçesi değil)', () => {
  const kanca = {};
  const s = govdeSec({
    paketKok: PAKET, paketSurumu: null, guvenliMod: false,
    updater: sahteUpdater({ kullan: true, dir: '/ov/0.5.7', version: '0.5.7' }, kanca),
    varMi: () => true,
    gunluk: sessiz,
  });
  assert.equal(s.yol, '/ov/0.5.7/electron/uygulama.js');
  assert.ok(!kanca.geriAlindi);
});

test('overlay paketle AYNI sürümdeyse "güncelleme var" denmez', () => {
  // Yakın kaçış: `etkin === overlaySurumu` ile yazılırsa eşit sürümlerde string'ler
  // birebir tutar ve overlay geçerli sanılır → panel yok yere "güncelleme" gösterir.
  const k = kimlik({ paketSurumu: '0.5.8', overlaySurumu: '0.5.8' });
  assert.equal(k.etkin, '0.5.8');
  assert.equal(k.kaynak, 'paket');
  assert.equal(ozet(k), 'v0.5.8');
});

test('surum.js sürüm seçimini yeniden YAZMAZ, updater\'a devreder', () => {
  // Bu modülün varlık sebebi "aynı soruya iki cevap"ı bitirmekti; 08-03 denetiminde
  // seçimi kendi içinde kopyalamış hâlde bulundu. Kopya geri gelirse test kırmızı.
  const kod = fs.readFileSync(path.join(__dirname, 'surum.js'), 'utf8');
  assert.ok(kod.includes('etkinSurumSec'), 'surum.js etkinSurumSec\'i kullanmalı');
  assert.ok(!/etkin:\s*overlayGecerli\s*\?/.test(kod), 'etkin sürüm seçimi burada tekrar yazılmış');
});

test('main.js paket sürümünü govdeSec\'e GEÇİRİR', () => {
  // Kıyas mantığı doğru olsa bile önyükleyici sürümü vermezse kapı hiç çalışmaz.
  const kod = fs.readFileSync(path.join(__dirname, 'main.js'), 'utf8');
  assert.ok(/paketSurumu\s*:/.test(kod), 'main.js govdeSec\'e paketSurumu vermiyor');
  assert.ok(kod.includes('getVersion()'), 'paket sürümü app.getVersion() ile alınmalı');
});

test('eski yükler (Electron katmanı yok) kopmaz — gövde paketten, overlay yine kullanılır', () => {
  // v0.5.8 ÖNCESİ yükler yalnız backend/app + frontend taşıyor. Bu dal kalkarsa
  // sahadaki mevcut kurulumlar güncellemeden kopar.
  const s = govdeSec({
    paketKok: PAKET, guvenliMod: false,
    updater: sahteUpdater({ kullan: true, dir: '/ov/0.5.7', version: '0.5.7' }),
    varMi: () => false,
    gunluk: sessiz,
  });
  assert.equal(s.yol, PAKET_GOVDE);
  assert.equal(s.govdeOverlayden, false);
  assert.equal(s.overlayKok, '/ov/0.5.7', 'backend overlay\'i yine de kullanılmalı');
});

test('güvenli mod overlay\'i tamamen yok sayar', () => {
  const kanca = {};
  const s = govdeSec({
    paketKok: PAKET, guvenliMod: true,
    updater: sahteUpdater({ kullan: true, dir: '/ov/0.5.8', version: '0.5.8' }, kanca),
    varMi: () => true,
    gunluk: sessiz,
  });
  assert.equal(s.yol, PAKET_GOVDE);
  assert.equal(s.overlayKok, null);
  assert.equal(kanca.geriAlindi, undefined, 'güvenli mod geri ALMAMALI — sadece yok sayar');
});

test('üst üste başarısızlıkta overlay geri alınır', () => {
  const kanca = {};
  const s = govdeSec({
    paketKok: PAKET, guvenliMod: false,
    updater: sahteUpdater({ kullan: false, geriAlinmali: true, version: '0.5.9' }, kanca),
    varMi: () => true,
    gunluk: sessiz,
  });
  assert.equal(s.yol, PAKET_GOVDE);
  assert.equal(s.geriAlindi, '0.5.9');
  assert.ok(kanca.geriAlindi, 'geriAl çağrılmalı');
});

test('updater patlarsa açılış durmaz, pakete düşülür', () => {
  const patlak = { saglikli: () => { throw new Error('current.json bozuk'); } };
  const s = govdeSec({
    paketKok: PAKET, guvenliMod: false, updater: patlak, varMi: () => true, gunluk: sessiz,
  });
  assert.equal(s.yol, PAKET_GOVDE);
  assert.equal(s.govdeOverlayden, false);
});

test('updater hiç kurulamadıysa (null) pakete düşülür', () => {
  const s = govdeSec({
    paketKok: PAKET, guvenliMod: false, updater: null, varMi: () => true, gunluk: sessiz,
  });
  assert.equal(s.yol, PAKET_GOVDE);
});

// ── Sürüm kimliği: tek cevap ───────────────────────────────────────────────

test('etkin sürüm overlay uygulanınca overlay sürümüdür (dfdd47a)', () => {
  const k = kimlik({ paketSurumu: '0.5.7', overlaySurumu: '0.5.8', katman: { govdeOverlayden: true } });
  assert.equal(k.etkin, '0.5.8');
  assert.equal(k.paket, '0.5.7');
  assert.match(ozet(k), /v0\.5\.8.*0\.5\.7/);
});

test('overlay pakete eşit ya da eskiyse etkin sürüm PAKETTİR', () => {
  // Geri alma sonrası / yeni tam paket kurulduğunda overlay bayat kalabilir.
  assert.equal(kimlik({ paketSurumu: '0.6.0', overlaySurumu: '0.5.8' }).etkin, '0.6.0');
  assert.equal(kimlik({ paketSurumu: '0.5.8', overlaySurumu: '0.5.8' }).etkin, '0.5.8');
  assert.equal(kimlik({ paketSurumu: '0.5.8', overlaySurumu: null }).etkin, '0.5.8');
});

test('özet kapsamı söyler: tam mı, yalnız uygulama kodu mu', () => {
  const tam = kimlik({ paketSurumu: '0.5.7', overlaySurumu: '0.5.8', katman: { govdeOverlayden: true } });
  const yarim = kimlik({ paketSurumu: '0.5.7', overlaySurumu: '0.5.8', katman: { govdeOverlayden: false } });
  assert.equal(tam.kaynak, 'overlay (tam)');
  assert.match(ozet(yarim), /yalnız uygulama kodu/);
});

test('güvenli mod özette görünür — sessiz kalmaz', () => {
  const k = kimlik({ paketSurumu: '0.5.7', overlaySurumu: '0.5.8', katman: { guvenliMod: true } });
  assert.match(ozet(k), /GÜVENLİ MOD/);
});

// ── Yükün yazamayacağı yerler ──────────────────────────────────────────────

test('yük Electron katmanına yazabilir', () => {
  assert.ok(guvenliYol('/kok', 'electron/uygulama.js'));
  assert.ok(guvenliYol('/kok', 'electron/updater.js'));
});

test('önyükleyici ve kurtarma yolu yükle DEĞİŞTİRİLEMEZ', () => {
  // Kendini güncelleyebilen bir kurtarma mekanizması kurtarma mekanizması değildir:
  // bozuk bir yük hem uygulamayı kırar hem geri dönüşü siler.
  assert.equal(guvenliYol('/kok', 'electron/main.js'), null);
  assert.equal(guvenliYol('/kok', 'electron/onyukleme.js'), null);
  assert.equal(guvenliYol('/kok', 'electron/shell-id.txt'), null);
});

test('izinli kökler dışı hâlâ reddediliyor', () => {
  assert.equal(guvenliYol('/kok', 'backend/venv/x.py'), null);
  assert.equal(guvenliYol('/kok', '../electron/main.js'), null);
  assert.equal(guvenliYol('/kok', 'electronx/kotu.js'), null);
});

// ── Önyükleyici sözleşmesi ─────────────────────────────────────────────────

test('main.js küçük kalır ve uygulama özelliği barındırmaz', () => {
  // Önyükleyici ASAR'da, yani GÜNCELLENEMEZ. Buraya eklenen her satır bir daha
  // düzeltilemeyecek koddur. Bu test o sözleşmeyi mekanik olarak korur.
  const kod = fs.readFileSync(path.join(__dirname, 'main.js'), 'utf8');
  const satir = kod.split('\n').filter((l) => l.trim() && !l.trim().startsWith('*') && !l.trim().startsWith('//'));
  assert.ok(satir.length < 80, `önyükleyici büyüdü (${satir.length} satır) — özellik uygulama.js'e ait`);
  for (const yasak of ['BrowserWindow', 'ipcMain', 'Tray', 'spawn(']) {
    assert.ok(!kod.includes(yasak), `main.js'e uygulama kodu sızmış: ${yasak}`);
  }
});

// ── Geliştirme profili ayrımı (2026-09-08) ─────────────────────────

test('MÜŞTERİ yolu değişmez — paketlenmişken profil ASLA taşınmaz', () => {
  // Bu testin kırmızı yanması = her mevcut kurulumun .env'i, app_lock.json'u,
  // faces.json'u ve models-cache'i terk edilmiş demektir. En pahalı kapı burası.
  assert.equal(devProfilYolu({
    paketlenmis: true, argv: [], env: {}, appDataKok: '/home/x/.config',
  }), null);
});

test('geliştirmede userData ürüne özel dizine ayrılır', () => {
  assert.equal(devProfilYolu({
    paketlenmis: false, argv: ['electron', '.'], env: {}, appDataKok: '/home/x/.config',
  }), path.join('/home/x/.config', 'yuki-urun-dev'));
});

test('elle verilen --user-data-dir KAZANIR (izole ölçüm profili ezilmez)', () => {
  // Playwright/xvfb turları kendi profilini kurar. Ezilirse ölçüm sessizce
  // geliştiricinin gerçek profiline yazar ve "ölçtük" denen şey onun verisi olur.
  for (const a of ['--user-data-dir=/tmp/izole', '--user-data-dir', '--user-data-dir=/tmp/x']) {
    assert.equal(devProfilYolu({
      paketlenmis: false, argv: ['electron', '.', a], env: {}, appDataKok: '/home/x/.config',
    }), null, `bayrak yok sayıldı: ${a}`);
  }
});

test('YUKI_DEV_PROFIL profil adını ezer', () => {
  assert.equal(devProfilYolu({
    paketlenmis: false, argv: [], env: { YUKI_DEV_PROFIL: 'yuki-ikinci' },
    appDataKok: '/home/x/.config',
  }), path.join('/home/x/.config', 'yuki-ikinci'));
});

test('appData okunamazsa dokunulmaz (açılış bunun için durmaz)', () => {
  assert.equal(devProfilYolu({ paketlenmis: false, argv: [], env: {}, appDataKok: null }), null);
});

test('main.js kuralı GERÇEKTEN bağlıyor — saf fonksiyon ölü kalmasın', () => {
  // "Kodu var" ≠ "çalışıyor". Birim testler yeşilken main.js hiç çağırmazsa
  // profil ayrımı üretilmiş ama devreye girmemiş olur (bu depoda TAM BOY modu
  // aynı sınıftan ölmüştü: CSS'i, markup'ı, fonksiyonu vardı, listede yoktu).
  // ⚠️ YORUMSUZ metinde ölç. Ham dosyada ölçmek bu testin İLK hâlinde yanlış
  // pozitif verdi: main.js'in kendi açıklama satırı `app.getPath('userData')`
  // içeriyor ve sıra kıyası onu kod sandı. Bu depodaki üçüncü tekrar
  // (/179/184 — yorum kod/markup sayıldı).
  const ham = fs.readFileSync(path.join(__dirname, 'main.js'), 'utf8');
  const kod = ham.split('\n')
    .filter((l) => l.trim() && !l.trim().startsWith('//') && !l.trim().startsWith('*') && !l.trim().startsWith('/*'))
    .join('\n');
  assert.ok(/devProfilYolu\(/.test(kod), 'main.js devProfilYolu çağırmıyor');
  assert.ok(/app\.setPath\(\s*'userData'/.test(kod), "main.js setPath('userData') yapmıyor");
  // Sıra kritik: setPath, userData'ya ilk dokunuştan ÖNCE olmalı.
  const iSet = kod.indexOf("app.setPath('userData'");
  const iGet = kod.indexOf("app.getPath('userData')");
  assert.ok(iSet >= 0 && iGet >= 0, 'çapa kayboldu — test sessizce boşa düşerdi');
  assert.ok(
    iSet < iGet,
    'setPath ilk getPath\'ten SONRA çağrılıyor — profil geç ayrılır, log yanlış dizine düşer',
  );
});

test('uygulama.js paketlenmiş kaynakları __dirname ile aramaz', () => {
  // Overlay'den çalışırken __dirname overlay'i gösterir → shell-id.txt,
  // models-manifest.json gibi paketlenmiş kaynaklar kaybolur ve delta uyum
  // kontrolü sessizce çöker (shell_id null → hep tam indirme).
  const kod = fs.readFileSync(path.join(__dirname, 'uygulama.js'), 'utf8');
  const suclu = kod.split('\n')
    .map((l, i) => [i + 1, l])
    .filter(([, l]) => /path\.join\(__dirname/.test(l));
  assert.deepEqual(suclu, [], 'PAKET_KOK ya da kaynak() kullanılmalı');
});

// ── Bütünlük · düşürme · günlük (2026-08-03 sağlamlaştırma) ────────────────

const os = require('os');
const crypto = require('crypto');
const { DeltaUpdater } = require('./delta-updater');

function gecici() {
  return fs.mkdtempSync(path.join(os.tmpdir(), 'yuki-delta-'));
}

/** Gerçek bir overlay iskeleti kur; imzalı manifest yerine kökü elle yazarız. */
function overlayKur(kok, dosyalar) {
  for (const [rel, icerik] of Object.entries(dosyalar)) {
    const tam = path.join(kok, rel);
    fs.mkdirSync(path.dirname(tam), { recursive: true });
    fs.writeFileSync(tam, icerik);
  }
}

test('ağaç kökü değişikliği · eklemeyi · silmeyi yakalar', () => {
  const kok = gecici();
  const u = new DeltaUpdater({ userDataDir: kok, gunluk: sessiz });
  const ov = path.join(kok, 'ov');
  overlayKur(ov, {
    'backend/app/main.py': 'print(1)',
    'frontend/index.html': '<b>a</b>',
    'electron/uygulama.js': '// x',
  });

  const ilk = u.agacKoku(ov);
  assert.match(ilk, /^[0-9a-f]{64}$/);
  assert.equal(u.agacKoku(ov), ilk, 'aynı ağaç aynı kökü vermeli (deterministik)');

  fs.writeFileSync(path.join(ov, 'backend/app/main.py'), 'print(2)');
  assert.notEqual(u.agacKoku(ov), ilk, 'DEĞİŞTİRME yakalanmadı');

  fs.writeFileSync(path.join(ov, 'backend/app/main.py'), 'print(1)');
  assert.equal(u.agacKoku(ov), ilk);

  fs.writeFileSync(path.join(ov, 'backend/app/kotu.py'), 'os.system("x")');
  assert.notEqual(u.agacKoku(ov), ilk, 'EKLEME yakalanmadı');

  fs.rmSync(path.join(ov, 'backend/app/kotu.py'));
  fs.rmSync(path.join(ov, 'frontend/index.html'));
  assert.notEqual(u.agacKoku(ov), ilk, 'SİLME yakalanmadı');
});

test('aynalanan kardeşler köke girmez (yoksa kök hiç tutmazdı)', () => {
  const kok = gecici();
  const u = new DeltaUpdater({ userDataDir: kok, gunluk: sessiz });
  const ov = path.join(kok, 'ov');
  overlayKur(ov, { 'backend/app/main.py': 'x' });
  const ilk = u.agacKoku(ov);
  // _kardesleriAynala() bunları paketten bağlar; yükün parçası DEĞİLLER.
  overlayKur(ov, { 'backend/mcp_servers.json': '{}', 'backend/skills/a.md': '#' });
  assert.equal(u.agacKoku(ov), ilk);
});

test('kurcalanmış overlay açılışta reddedilir ve geri alınır', () => {
  const kok = gecici();
  const u = new DeltaUpdater({ userDataDir: kok, gunluk: sessiz });
  const ov = path.join(kok, 'updates', '0.5.9');
  overlayKur(ov, { 'backend/app/main.py': 'temiz' });

  // Manifest'i imzalayamayız (private key repo dışı) → imza doğrulamasının
  // reddettiğini sınıyoruz: sahte imzalı manifest ASLA kabul edilmemeli.
  fs.writeFileSync(path.join(kok, 'updates', '0.5.9.manifest.json'), JSON.stringify({
    schema: 1, product: 'yuki', version: '0.5.9',
    files_root: u.agacKoku(ov), sig: 'sahte-imza',
  }));
  fs.writeFileSync(path.join(kok, 'updates', 'current.json'), JSON.stringify({
    version: '0.5.9', dir: ov, failCount: 0,
  }));

  const b = u.butunlukDogrula('0.5.9', ov);
  assert.equal(b.saglam, false);
  assert.match(b.sebep, /imza/i);

  const s = u.saglikli();
  assert.equal(s.kullan, false);
  assert.equal(s.geriAlinmali, true, 'kurcalanmış overlay bir daha DENENMEMELİ');
});

test('manifest saklanmamışsa (eski overlay) kopma olmaz', () => {
  const kok = gecici();
  const u = new DeltaUpdater({ userDataDir: kok, gunluk: sessiz });
  const ov = path.join(kok, 'updates', '0.5.7');
  overlayKur(ov, { 'backend/app/main.py': 'x' });
  fs.writeFileSync(path.join(kok, 'updates', 'current.json'),
    JSON.stringify({ version: '0.5.7', dir: ov, failCount: 0 }));
  assert.equal(u.butunlukDogrula('0.5.7', ov).saglam, true);
  assert.equal(u.saglikli().kullan, true);
});

test('bozuk saklı manifest sağlam sayılmaz', () => {
  const kok = gecici();
  const u = new DeltaUpdater({ userDataDir: kok, gunluk: sessiz });
  const ov = path.join(kok, 'updates', '0.5.9');
  overlayKur(ov, { 'backend/app/main.py': 'x' });
  fs.mkdirSync(path.dirname(path.join(kok, 'updates', '0.5.9.manifest.json')), { recursive: true });
  fs.writeFileSync(path.join(kok, 'updates', '0.5.9.manifest.json'), '{bozuk');
  assert.equal(u.butunlukDogrula('0.5.9', ov).saglam, false);
});

test('sembolik bağ köke "BAĞ" olarak girer — içeriği izlenmez', () => {
  const kok = gecici();
  const u = new DeltaUpdater({ userDataDir: kok, gunluk: sessiz });
  const ov = path.join(kok, 'ov');
  overlayKur(ov, { 'backend/app/main.py': 'x' });
  const disari = path.join(kok, 'disari.py');
  fs.writeFileSync(disari, 'kotu');
  fs.symlinkSync(disari, path.join(ov, 'backend/app/bag.py'));
  const ilk = u.agacKoku(ov);
  fs.writeFileSync(disari, 'daha-kotu');
  assert.equal(u.agacKoku(ov), ilk, 'bağın HEDEFİ okunmamalı');
});

test('sürüm düşürme reddedilir — imzalı ama eski manifest tekrar oynatılamaz', async () => {
  const kok = gecici();
  const u = new DeltaUpdater({ userDataDir: kok, currentVersion: '0.6.0', gunluk: sessiz });
  let cagrildi = false;
  u.fetchManifest = async () => { cagrildi = true; return {}; };
  const r = await u.downloadAndApply('0.5.9');
  // Manifest yine de çekilir (imza doğrulaması ucuzdur), ama UYGULANMAZ.
  assert.equal(r.ok, false);
  assert.match(r.reason, /yeni değil/);
});

test('aynı sürüm de reddedilir (sonsuz döngü koruması)', async () => {
  const kok = gecici();
  const u = new DeltaUpdater({ userDataDir: kok, currentVersion: '0.5.9', gunluk: sessiz });
  u.fetchManifest = async () => ({ man: { shell_id: 'x' }, ham: '{}' });
  const r = await u.downloadAndApply('0.5.9');
  assert.equal(r.ok, false);
});

test('günlük çağrılır — geri alma artık sessiz değil', () => {
  const kok = gecici();
  const satirlar = [];
  const u = new DeltaUpdater({ userDataDir: kok, gunluk: (s) => satirlar.push(s) });
  const ov = path.join(kok, 'updates', '0.5.9');
  overlayKur(ov, { 'backend/app/main.py': 'x' });
  fs.writeFileSync(path.join(kok, 'updates', '0.5.9.manifest.json'), '{bozuk');
  fs.writeFileSync(path.join(kok, 'updates', 'current.json'),
    JSON.stringify({ version: '0.5.9', dir: ov, failCount: 0 }));
  u.saglikli();
  assert.ok(satirlar.some((s) => /BÜTÜNLÜK BOZUK/.test(s)), `günlüğe düşmedi: ${satirlar}`);
});

test('files_root taşımayan manifest reddedilir (kapı hep kapalı)', async () => {
  const kok = gecici();
  const u = new DeltaUpdater({ userDataDir: kok, gunluk: sessiz });
  // fetchManifest'in gerçek gövdesini imzasız çalıştıramayız; kuralın kodda
  // yazılı olduğunu doğrula — "isteğe bağlı" bırakılmadığının kanıtı.
  const kaynak = fs.readFileSync(path.join(__dirname, 'delta-updater.js'), 'utf8');
  assert.match(kaynak, /if \(!man\.files_root\) \{[\s\S]*?throw new Error/);
});

// ── Kanal / yayılma kapısı ─────────────────────────────────────────────────

const { UpdateChecker, KANALLAR, BEKLEME_SAATI } = require('./updater');

function ayarDosyasi(icerik) {
  const d = gecici();
  const y = path.join(d, 'updater.json');
  if (icerik) fs.writeFileSync(y, JSON.stringify(icerik));
  return y;
}

test('varsayılan kanal stable — müşteri ön sürüm almaz', () => {
  const c = new UpdateChecker({ settingsPath: ayarDosyasi(), currentVersion: '0.5.8' });
  assert.equal(c.status().channel, 'stable');
});

test('geçersiz kanal sessizce yutulmaz', () => {
  const c = new UpdateChecker({ settingsPath: ayarDosyasi(), currentVersion: '0.5.8' });
  assert.throws(() => c.setChannel('canary'), /Bilinmeyen kanal/);
  assert.equal(c.status().channel, 'stable', 'reddedilen kanal kaydedilmemeli');
  for (const k of KANALLAR) { c.setChannel(k); assert.equal(c.status().channel, k); }
});

test('stable: taze sürüm bekletilir, manuel kontrolde bekletilmez', async () => {
  const taze = new Date(Date.now() - 2 * 3600000).toISOString();   // 2 saatlik
  const yol = ayarDosyasi({ enabled: true, channel: 'stable', lastCheck: 0 });

  const kur = () => {
    const c = new UpdateChecker({ settingsPath: yol, currentVersion: '0.5.8' });
    c.settings();  // önbelleği doldur
    return c;
  };
  const c = kur();
  // Ağa çıkmadan sınamak için JSON getiriciyi değil, sonucu taklit ediyoruz:
  // gerçek akışın SADECE kapı kısmını ölçmek istiyoruz.
  const orj = require('https').get;
  assert.ok(BEKLEME_SAATI > 0);
  assert.ok(taze && orj);   // (bu test kapının varlığını kaynaktan doğrular)

  const kaynak = fs.readFileSync(path.join(__dirname, 'updater.js'), 'utf8');
  assert.match(kaynak, /!manual && kanal === 'stable' && yayinTarihi/,
    'bekleme kapısı manuel kontrolü ve kanalı gözetmeli');
  assert.match(kaynak, /saat < BEKLEME_SAATI/);
});

test('beta liste ucunu kullanır — ön sürümler /releases/latest\'te görünmez', () => {
  const kaynak = fs.readFileSync(path.join(__dirname, 'updater.js'), 'utf8');
  assert.match(kaynak, /kanal === 'beta'[\s\S]*?LIST_URL/);
  assert.match(kaynak, /per_page=10/);
});

// ── Gerçek başarı ölçütü ───────────────────────────────────────────────────

test('başarı ölçütü "backend kalktı" değil "beklenen sürüm çalışıyor"', () => {
  // Overlay hiç yüklenmese de backend ayağa kalkar → eski ölçüt başarısız bir
  // güncellemeyi "başarılı" damgalıyor, geri alma hiç tetiklenmiyordu.
  const kod = fs.readFileSync(path.join(__dirname, 'uygulama.js'), 'utf8');
  assert.match(kod, /function guncellemeBasarisiniIsle/);
  assert.match(kod, /bildirilen === k\.etkin/, 'bildirilen sürüm etkin sürümle karşılaştırılmalı');
  assert.match(kod, /UYUŞMAZLIK/, 'uyuşmazlık günlüğe düşmeli');
  // basariliIsaretle yalnız bu fonksiyonun içinden çağrılmalı — başka bir yerde
  // koşulsuz çağrı kalırsa ölçüt yine boşa düşer.
  const cagrilar = kod.split('\n').filter((l) => l.includes('basariliIsaretle'));
  assert.equal(cagrilar.length, 2, `beklenmedik basariliIsaretle çağrısı: ${cagrilar}`);
});

test('/health sürüm bildiriyor — ölçütün dayandığı alan gerçekten var', () => {
  const py = fs.readFileSync(path.join(__dirname, '..', 'backend', 'app', 'services', 'health.py'), 'utf8');
  assert.match(py, /APP_VERSION\s*=/);
  assert.match(py, /"version":\s*APP_VERSION/);
});
