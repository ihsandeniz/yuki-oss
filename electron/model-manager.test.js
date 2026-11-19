/**
 * Model yöneticisi testleri — `node --test electron/`
 *
 * 🔑 NEDEN VAR ( Dalga 2, 2026-09-05): katman `kind:"pydeps"` yüklerini
 * öğrendi — bunlar MODELLERDEN farklı olarak PLATFORMA ÖZELDİR (derlenmiş
 * `.so`/`.pyd` taşırlar), yani yük başına tek asset yetmez.
 *
 * Testlerin ağırlığı iki yerde:
 *   ① REGRESYON — whisper + embedding (eski biçim) davranışı DEĞİŞMEDİ.
 *      Bu ikisi üretimde ve müşteri kurulumlarında çalışıyor; yeni tip onları
 *      bozmamalı. Gerçek `models-manifest.json` okunur, kopyası değil.
 *   ② REDDETME — yanlış platformun ikilisini indirmeyi reddediyor mu.
 *      "İndirdi" kolay; "indirmemesi gerekeni indirmedi" zor olan.
 *
 * Bağımlılık yok (node:test + node:assert) — mevcut test dosyalarının deseni.
 */
const test = require('node:test');
const assert = require('node:assert');
const fs = require('fs');
const os = require('os');
const path = require('path');
const http = require('http');
const crypto = require('crypto');
const { execFileSync } = require('child_process');

const { ModelManager, platformAnahtari } = require('./model-manager');

const GERCEK_MANIFEST = path.join(__dirname, 'models-manifest.json');

const gecici = () => fs.mkdtempSync(path.join(os.tmpdir(), 'mm-test-'));

/** Test için manifest yaz, yolunu dön. */
function manifestYaz(dir, veri) {
  const p = path.join(dir, 'manifest.json');
  fs.writeFileSync(p, JSON.stringify(veri), 'utf8');
  return p;
}

// ── ① REGRESYON: eski biçim (platformsuz model) aynen çalışıyor ─────────────

test('regresyon — whisper + embedding gerçek manifest\'te hâlâ indirilebilir', () => {
  const mm = new ModelManager({
    manifestPath: GERCEK_MANIFEST,
    writableDir: path.join(gecici(), 'yok'),   // kasten yok → present:false
    bundledDir: null,
  });

  for (const id of ['whisper-small', 'embedding-onnx']) {
    const s = mm.status(id);
    assert.equal(s.downloadable, true, `${id} indirilebilir olmalı`);
    assert.equal(s.present, false);
    assert.equal(s.unsupportedPlatform, false, `${id} platformdan bağımsız olmalı`);
    assert.equal(s.kind, 'model', `${id} varsayılan tip 'model' olmalı`);
    assert.ok(s.sizeBytes > 0, `${id} sizeBytes kayboldu`);
    assert.ok(s.downloadBytes > 0, `${id} downloadBytes kayboldu`);
  }
});

test('regresyon — eski biçimde assets{} yokken kaydın kendisi asset\'tir', () => {
  const dir = gecici();
  const mp = manifestYaz(dir, {
    models: {
      eski: {
        name: 'Eski', url: 'https://x/y.tar.gz', sha256: 'ab'.repeat(32),
        sizeBytes: 100, downloadBytes: 60, presenceDir: 'e', extractTo: '.',
      },
    },
  });
  const mm = new ModelManager({ manifestPath: mp, writableDir: dir, bundledDir: null });
  const s = mm.status('eski');
  assert.equal(s.downloadable, true);
  assert.equal(s.sizeBytes, 100);
  assert.equal(s.downloadBytes, 60);
});

// ── platform anahtarı ───────────────────────────────────────────────────────

test('platformAnahtari — bilinenler eşleşir, bilinmeyen null döner', () => {
  assert.equal(platformAnahtari('linux', 'x64'), 'linux-x64');
  assert.equal(platformAnahtari('win32', 'x64'), 'win-x64');
  // Desteklenmeyenler: "linux varsay" YOK — yanlış ikili indirmektense null.
  assert.equal(platformAnahtari('darwin', 'x64'), null);
  assert.equal(platformAnahtari('linux', 'arm64'), null);
  assert.equal(platformAnahtari('win32', 'ia32'), null);
});

// ── ② pydeps: doğru platformun asset'i seçiliyor ────────────────────────────

const PYDEPS_MANIFEST = {
  models: {
    'face-pydeps': {
      name: 'Yüz Tanıma Kütüphanesi', kind: 'pydeps',
      presenceDir: 'pydeps/face', extractTo: 'pydeps/face', tier: 'lite',
      assets: {
        'linux-x64': { url: 'https://x/lin.tar.gz', sha256: 'aa'.repeat(32), sizeBytes: 182, downloadBytes: 64 },
        'win-x64': { url: 'https://x/win.tar.gz', sha256: 'bb'.repeat(32), sizeBytes: 168, downloadBytes: 62 },
      },
    },
  },
};

test('pydeps — her platform KENDİ asset\'ini görüyor', () => {
  const dir = gecici();
  const mp = manifestYaz(dir, PYDEPS_MANIFEST);

  const lin = new ModelManager({ manifestPath: mp, writableDir: dir, bundledDir: null, platformKey: 'linux-x64' });
  assert.equal(lin.status('face-pydeps').downloadBytes, 64);
  assert.equal(lin.status('face-pydeps').kind, 'pydeps');
  assert.equal(lin.status('face-pydeps').downloadable, true);

  const win = new ModelManager({ manifestPath: mp, writableDir: dir, bundledDir: null, platformKey: 'win-x64' });
  assert.equal(win.status('face-pydeps').downloadBytes, 62);
  assert.equal(win.status('face-pydeps').downloadable, true);
});

test('pydeps — desteklenmeyen platformda indirilemez VE sebebi belli', () => {
  const dir = gecici();
  const mp = manifestYaz(dir, PYDEPS_MANIFEST);
  const mac = new ModelManager({ manifestPath: mp, writableDir: dir, bundledDir: null, platformKey: null });

  const s = mac.status('face-pydeps');
  assert.equal(s.downloadable, false);
  // "indirilemez" tek başına yetmez — arayüz 'desteklenmiyor' ile 'henüz
  // yayınlanmadı'yı ayırt edebilmeli, yoksa kullanıcıya yanlış şey söyler.
  assert.equal(s.unsupportedPlatform, true);
  assert.equal(s.downloadBytes, 0);
});

test('pydeps — desteklenmeyen platformda download() REDDEDİYOR', async () => {
  const dir = gecici();
  const mp = manifestYaz(dir, PYDEPS_MANIFEST);
  const mac = new ModelManager({ manifestPath: mp, writableDir: dir, bundledDir: null, platformKey: null });

  await assert.rejects(
    () => mac.download('face-pydeps'),
    (e) => /desteklenmiyor/.test(e.message) && /linux-x64/.test(e.message),
    'yanlış platformda net hata vermeli, sessizce Linux ikilisini indirmemeli'
  );
});

// ── uçtan uca: gerçek indirme + SHA + açma, platform seçimiyle ──────────────

/** Tek dosyalık gerçek bir .tar.gz üret. */
function tarUret(dir, icerikAdi) {
  const kaynak = path.join(dir, 'kaynak');
  fs.mkdirSync(path.join(kaynak, 'pydeps', 'face'), { recursive: true });
  fs.writeFileSync(path.join(kaynak, 'pydeps', 'face', 'isaret.txt'), icerikAdi);
  const arsiv = path.join(dir, `${icerikAdi}.tar.gz`);
  execFileSync('tar', ['-czf', arsiv, '-C', kaynak, '.']);
  return arsiv;
}

test('uçtan uca — doğru platformun arşivi iniyor, SHA doğrulanıyor, açılıyor', async () => {
  const dir = gecici();
  const linArsiv = tarUret(dir, 'LINUX');
  const winArsiv = tarUret(dir, 'WINDOWS');
  const sha = (p) => crypto.createHash('sha256').update(fs.readFileSync(p)).digest('hex');

  const sunucu = http.createServer((req, res) => {
    const dosya = req.url.includes('win') ? winArsiv : linArsiv;
    res.writeHead(200); res.end(fs.readFileSync(dosya));
  });
  await new Promise((r) => sunucu.listen(0, '127.0.0.1', r));
  const kok = `http://127.0.0.1:${sunucu.address().port}`;

  try {
    const mp = manifestYaz(dir, {
      models: {
        'face-pydeps': {
          name: 'Yüz Tanıma Kütüphanesi', kind: 'pydeps',
          presenceDir: 'pydeps/face', extractTo: '.',
          assets: {
            'linux-x64': { url: `${kok}/lin.tar.gz`, sha256: sha(linArsiv), downloadBytes: fs.statSync(linArsiv).size },
            'win-x64': { url: `${kok}/win.tar.gz`, sha256: sha(winArsiv), downloadBytes: fs.statSync(winArsiv).size },
          },
        },
      },
    });

    // Windows istemcisi WINDOWS arşivini almalı — linux'unkini değil.
    const hedef = path.join(dir, 'cache-win');
    const win = new ModelManager({ manifestPath: mp, writableDir: hedef, bundledDir: null, platformKey: 'win-x64' });
    const asamalar = [];
    const r = await win.download('face-pydeps', (p) => asamalar.push(p.phase));

    assert.equal(r.ok, true);
    assert.equal(
      fs.readFileSync(path.join(hedef, 'pydeps', 'face', 'isaret.txt'), 'utf8'), 'WINDOWS',
      'win-x64 istemcisine LINUX arşivi inmiş — platform seçimi çalışmıyor'
    );
    assert.ok(asamalar.includes('download') && asamalar.includes('done'), 'ilerleme bildirimi kesildi');
    assert.equal(win.status('face-pydeps').present, true);

    // İkinci çağrı yeniden indirmemeli.
    assert.equal((await win.download('face-pydeps')).already, true);
  } finally {
    sunucu.close();
  }
});

// ── ③ DÜŞMANCA TUR (2026-09-05) — kapıyı kandırmayı dene ───────────────────
//
// İlk turun körlüğü: uçtan uca test `extractTo:"."` kullanıyordu, ÜRETİMDEKİ ayar
// ise `extractTo:"pydeps/face"` (presenceDir ile AYNI yol). O fark tam da açığın
// yaşadığı yerdi ve test oraya hiç bakmamıştı.
// 📏 Ders: testi üretimin ayarıyla koş; "benzer" ayar, ölçülmemiş ayardır.

/** Verilen dizin ağacından .tar.gz üret (boş ağaç da olabilir). */
function arsivle(kokDizin, cikti) {
  execFileSync('tar', ['-czf', cikti, '-C', kokDizin, '.']);
  return cikti;
}

/** Bir arşivi servis eden yerel sunucu + o arşivi kullanan manifest kur. */
async function ortamKur(dir, arsiv, { presenceDir, extractTo }) {
  const sunucu = http.createServer((q, r) => { r.writeHead(200); r.end(fs.readFileSync(arsiv)); });
  await new Promise((r) => sunucu.listen(0, '127.0.0.1', r));
  const sha = crypto.createHash('sha256').update(fs.readFileSync(arsiv)).digest('hex');
  const mp = manifestYaz(dir, {
    models: {
      'face-pydeps': {
        name: 'Yüz Tanıma Kütüphanesi', kind: 'pydeps', presenceDir, extractTo,
        assets: {
          'linux-x64': {
            url: `http://127.0.0.1:${sunucu.address().port}/a.tar.gz`,
            sha256: sha, downloadBytes: fs.statSync(arsiv).size,
          },
        },
      },
    },
  });
  return { sunucu, mp };
}

test('düşmanca — BOŞ arşiv "kuruldu" sayılmıyor (üretim ayarıyla)', async () => {
  const dir = gecici();
  const bos = path.join(dir, 'bos'); fs.mkdirSync(bos);
  const arsiv = arsivle(bos, path.join(dir, 'bos.tar.gz'));
  // 🔴 ÜRETİMDEKİ ayar: extractTo === presenceDir. Açıcı hedefi mkdir'liyor,
  //    kapı da onu ölçüyordu → boş arşiv {ok:true} + present:true veriyordu.
  const { sunucu, mp } = await ortamKur(dir, arsiv, { presenceDir: 'pydeps/face', extractTo: 'pydeps/face' });
  const hedef = path.join(dir, 'cache');
  const mm = new ModelManager({ manifestPath: mp, writableDir: hedef, bundledDir: null, platformKey: 'linux-x64' });

  try {
    await assert.rejects(() => mm.download('face-pydeps'), /oluşmadı|boş/i,
      'boş arşiv başarılı sayıldı — varlık kapısı açıcının kendi mkdir\'ini ölçüyor');
    assert.equal(mm.status('face-pydeps').present, false, 'boş kurulum "var" görünüyor');
    assert.equal(fs.existsSync(path.join(hedef, 'pydeps', 'face')), false,
      'başarısız açma geride BOŞ dizin bıraktı — locate() bunu "kurulu" sanar, indirme bir daha denenmez');
  } finally { sunucu.close(); }
});

test('düşmanca — geride kalmış BOŞ dizin modeli "kurulu" göstermiyor', () => {
  const dir = gecici();
  const mp = manifestYaz(dir, {
    models: { x: { name: 'X', presenceDir: 'pydeps/face', extractTo: 'pydeps/face',
                   url: 'https://x/y', sha256: 'aa'.repeat(32) } },
  });
  const hedef = path.join(dir, 'cache');
  fs.mkdirSync(path.join(hedef, 'pydeps', 'face'), { recursive: true });   // elle boş dizin
  const mm = new ModelManager({ manifestPath: mp, writableDir: hedef, bundledDir: null });
  assert.equal(mm.status('x').present, false, 'boş dizin "kurulu" sayıldı → indirme sonsuza kadar atlanır');
});

test('düşmanca — arşiv YANLIŞ yere açılırsa reddediliyor', async () => {
  const dir = gecici();
  const kaynak = path.join(dir, 'yanlis');
  fs.mkdirSync(path.join(kaynak, 'baska-klasor'), { recursive: true });
  fs.writeFileSync(path.join(kaynak, 'baska-klasor', 'a.txt'), 'x');
  const arsiv = arsivle(kaynak, path.join(dir, 'yanlis.tar.gz'));
  // Arşiv dolu ama beklenen paket dizinini İÇERMİYOR → "kuruldu" denmemeli.
  const { sunucu, mp } = await ortamKur(dir, arsiv, { presenceDir: 'pydeps/face/insightface', extractTo: 'pydeps/face' });
  const mm = new ModelManager({ manifestPath: mp, writableDir: path.join(dir, 'c'), bundledDir: null, platformKey: 'linux-x64' });
  try {
    await assert.rejects(() => mm.download('face-pydeps'), /oluşmadı|boş/i,
      'beklenen paket gelmediği hâlde kurulum başarılı sayıldı');
  } finally { sunucu.close(); }
});

test('düşmanca — üretim ayarıyla DOĞRU arşiv sorunsuz kuruluyor (yanlış-pozitif kapısı)', async () => {
  const dir = gecici();
  const kaynak = path.join(dir, 'dogru');
  fs.mkdirSync(path.join(kaynak, 'insightface'), { recursive: true });
  fs.writeFileSync(path.join(kaynak, 'insightface', '__init__.py'), '# paket');
  const arsiv = arsivle(kaynak, path.join(dir, 'dogru.tar.gz'));
  const { sunucu, mp } = await ortamKur(dir, arsiv, { presenceDir: 'pydeps/face/insightface', extractTo: 'pydeps/face' });
  const hedef = path.join(dir, 'c');
  const mm = new ModelManager({ manifestPath: mp, writableDir: hedef, bundledDir: null, platformKey: 'linux-x64' });
  try {
    // Sıkılaştırma sağlam kurulumu ENGELLEMEMELİ — kapı iki yönde de sınanır.
    assert.equal((await mm.download('face-pydeps')).ok, true);
    assert.equal(mm.status('face-pydeps').present, true);
    assert.ok(fs.existsSync(path.join(hedef, 'pydeps', 'face', 'insightface', '__init__.py')));
  } finally { sunucu.close(); }
});

// ── ④ pydepsDirs() — backend'e geçilecek sys.path adayları (FAZ 3) ─────────

test('pydepsDirs — yalnız GERÇEKTEN kurulu pydeps yükleri dönüyor', () => {
  const dir = gecici();
  const mp = manifestYaz(dir, {
    models: {
      'whisper-small': { name: 'W', presenceDir: 'hub/w', extractTo: '.', url: 'u', sha256: 'a'.repeat(64) },
      'face-pydeps': { name: 'F', kind: 'pydeps', presenceDir: 'pydeps/face/insightface', extractTo: 'pydeps/face', assets: {} },
    },
  });
  const kok = path.join(dir, 'cache');
  const mm = new ModelManager({ manifestPath: mp, writableDir: kok, bundledDir: null, platformKey: 'linux-x64' });

  // Hiçbiri kurulu değil → boş. İnmemiş bir yükü listelemek backend'e var
  // olmayan dizini göstermek olurdu ve "kütüphane var" yanılsaması üretirdi.
  assert.deepEqual(mm.pydepsDirs(), []);

  // Boş dizin de sayılmamalı (yarım kalmış indirme artığı).
  fs.mkdirSync(path.join(kok, 'pydeps', 'face', 'insightface'), { recursive: true });
  assert.deepEqual(mm.pydepsDirs(), [], 'boş ağaç sys.path\'e aday gösterildi');

  // İçerik gelince listelenmeli — ve extractTo dizini, presenceDir DEĞİL:
  // sys.path'e paketin KENDİSİ değil, paketleri İÇEREN dizin eklenir.
  fs.writeFileSync(path.join(kok, 'pydeps', 'face', 'insightface', '__init__.py'), '#');
  assert.deepEqual(mm.pydepsDirs(), [path.join(kok, 'pydeps', 'face')]);

  // whisper `kind:"model"` — pydeps listesine ASLA karışmamalı.
  fs.mkdirSync(path.join(kok, 'hub', 'w'), { recursive: true });
  fs.writeFileSync(path.join(kok, 'hub', 'w', 'x.bin'), 'x');
  assert.deepEqual(mm.pydepsDirs(), [path.join(kok, 'pydeps', 'face')],
    'model yükü pydeps listesine sızdı');
});

test('uçtan uca — SHA tutmazsa REDDEDİLİYOR ve yarım dosya kalmıyor', async () => {
  const dir = gecici();
  const arsiv = tarUret(dir, 'LINUX');
  const sunucu = http.createServer((req, res) => { res.writeHead(200); res.end(fs.readFileSync(arsiv)); });
  await new Promise((r) => sunucu.listen(0, '127.0.0.1', r));

  try {
    const hedef = path.join(dir, 'cache-bozuk');
    const mp = manifestYaz(dir, {
      models: {
        'face-pydeps': {
          name: 'Yüz Tanıma Kütüphanesi', kind: 'pydeps',
          presenceDir: 'pydeps/face', extractTo: '.',
          assets: {
            'linux-x64': {
              url: `http://127.0.0.1:${sunucu.address().port}/lin.tar.gz`,
              sha256: 'cc'.repeat(32),          // ← kasten YANLIŞ
              downloadBytes: fs.statSync(arsiv).size,
            },
          },
        },
      },
    });
    const mm = new ModelManager({ manifestPath: mp, writableDir: hedef, bundledDir: null, platformKey: 'linux-x64' });

    await assert.rejects(() => mm.download('face-pydeps'), /Bütünlük hatası/);
    assert.equal(fs.existsSync(path.join(hedef, 'pydeps')), false, 'bozuk arşiv açılmış');
    const tmp = path.join(hedef, '.tmp');
    const kalan = fs.existsSync(tmp) ? fs.readdirSync(tmp) : [];
    assert.deepEqual(kalan, [], `yarım dosya bırakıldı: ${kalan}`);
  } finally {
    sunucu.close();
  }
});

// ── ⑤ aktifIndirmeler() — güvenli yeniden başlatma kapısının veri kaynağı ────
// 🔑 2026-09-08: yeniden başlatma düğmesi eklendi (geliştirici isteği). Sürmekte olan
// bir indirme varken uygulamayı yeniden başlatmak yarım dosya bırakır ve
// kullanıcı 16-276 MB'ı BAŞTAN indirir. `_active` zaten tutuluyordu ama yalnız
// `status(id)` üzerinden tek tek sorularak okunabiliyordu; "herhangi bir indirme
// var mı" sorusunun cevabı yoktu. Kapı bu fonksiyona bağlı — sessizce boş dönerse
// kapı hep açık kalır ve kusur GÖRÜNMEZ olur, o yüzden testi var.
test('aktifIndirmeler — indirme yokken boş, varken kimliği döner', () => {
  const dir = gecici();
  const mp = manifestYaz(dir, { models: { 'face-pydeps': { name: 'x', kind: 'pydeps',
    presenceDir: 'pydeps/face/insightface', extractTo: 'pydeps/face', tier: 'lite', assets: {} } } });
  const mm = new ModelManager({ manifestPath: mp, writableDir: dir, bundledDir: null });

  assert.deepEqual(mm.aktifIndirmeler(), [], 'indirme yokken boş olmalı');

  mm._active.set('face-pydeps', { canceled: false });   // _active bir Map (Set degil)
  assert.deepEqual(mm.aktifIndirmeler(), ['face-pydeps']);

  // Dönen dizi CANLI kümeye referans OLMAMALI: çağıran onu değiştirirse
  // indirme kaydını sessizce silmiş olurdu ve kapı yanlış "güvenli" derdi.
  const d = mm.aktifIndirmeler();
  d.pop();
  assert.deepEqual(mm.aktifIndirmeler(), ['face-pydeps'], 'iç durum dışarıdan bozulabiliyor');
});
