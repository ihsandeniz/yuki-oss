/**
 * TAM PAKET akışı — `` regresyon takımı.
 *
 * Kusur: `uygulama.js` `fetchManifest`in **`{man, ham}` zarfını** açmadan
 * `indirVeDogrula`'ya geçiriyordu → `manifest.skus` `undefined` → güvenlik kapısı
 * meşru güncellemeyi *"bu sürümün imzalı parmak izinde X yok"* diye reddediyordu.
 * 2026-08-08'den 2026-09-11'e kadar sessiz kaldı (yol yalnız `shell_id` değişince
 * açılıyor) ve mevcut birim testi **göremedi: doğru şekilli bir mock veriyordu.**
 *
 * 🔑 Bu yüzden buradaki manifest fikstürü uydurma değil — **yayındaki gerçek
 * `yuki-update-0.6.15.json`'dan** alındı (imza alanı hariç; `fetchManifest` onu
 * doğruladıktan sonra zaten `delete` ediyor). Testin varsaydığı sözleşme ile
 * üretimdeki sözleşme ayrışırsa kusur yine görünmez olurdu.
 */
const test = require('node:test');
const assert = require('node:assert');
const fs = require('fs');
const path = require('path');

const { tamPaketiIndir, zarfiAc } = require('./tam-akis');
const { TamGuncelleyici, skuTablosu, skuVarligi } = require('./tam-guncelleme');

const SURUM = '0.6.15';

/** Yayındaki v0.6.15 manifestinin birebir alanları (sig doğrulandıktan sonraki hâli). */
function gercekManifest() {
  return {
    schema: 1,
    product: 'yuki',
    version: SURUM,
    shell_id: 'c75a3d6e55a893d0abd4ec416f0407a7',
    files_root: '44646a671c9b9d0abbcb58eaa5affd60544520b195aba1ae7adcff382dc49bb4',
    payload_name: `yuki-update-${SURUM}.tar.gz`,
    payload_sha256: 'af8dbe1c680b4a7e3ac3a46e8d73bff73468409df9f7a26f65cca4799298e6d6',
    payload_size: 1565209,
    skus: [
      'Yuki-0.6.15-lite.AppImage:e29ef9997e98a2872b77b9402f4ef3e4f8a7f6abaecea040f8ad7b0ce971d632:457306516',
      'Yuki-0.6.15-offline.AppImage:571b26c7c42ab348f9844e010a6397216f8c942434e1b98bf68d640099ae6088:986741798',
      'Yuki-0.6.15-win-x64-lite.zip:a3d2b0d917bfbaba010d43c4e1fecb48c287ab3f2120105c9d85f4c9402babf8:393638664',
      'Yuki-0.6.15-win-x64-offline.zip:fc849f781910c588261dd55368ca1b554566ec147e622fb656c5f0c5ecb5cb5a:915570491',
    ].join(';'),
  };
}

/** `fetchManifest`in GERÇEK dönüşü — tek manifest değil, ham gövdeyi de taşıyan zarf. */
function gercekZarf() {
  const man = gercekManifest();
  return { man, ham: JSON.stringify({ ...man, sig: 'x'.repeat(86) }) };
}

function sahteDelta(zarf) {
  return { fetchManifest: async (v) => { assert.equal(v, SURUM); return zarf; } };
}

// ── ① Sözleşme: fetchManifest gerçekten ZARF döndürüyor ────────────────────
// Gövdesini imzasız çalıştıramayız (ağa çıkar + gerçek Ed25519 imzası ister),
// ama sözleşmenin kodda yazılı olduğunu doğrularız: bu satır değişirse
// `zarfiAc` de gözden geçirilmeli.
test('sözleşme: delta-updater.fetchManifest {man, ham} döndürür', () => {
  const kaynak = fs.readFileSync(path.join(__dirname, 'delta-updater.js'), 'utf8');
  assert.match(kaynak, /return \{ man, ham: raw\.toString\('utf8'\) \};/);
});

// ── ② Zarf açma ────────────────────────────────────────────────────────────
test('zarfiAc zarfın İÇİNDEKİ manifesti döndürür', () => {
  const zarf = gercekZarf();
  const man = zarfiAc(zarf);
  assert.equal(man, zarf.man);
  assert.equal(typeof man.skus, 'string');
});

test('çıplak manifest SESSİZCE kabul edilmez — sözleşme tek yönlüdür', () => {
  assert.throws(() => zarfiAc(gercekManifest()), /sözleşmesi bozuldu/);
});

test('boş yanıt net hata verir', () => {
  assert.throws(() => zarfiAc(null), /Manifest alınamadı/);
});

// ── ③ Akış: güvenlik kapısının beklediği şey geçiyor mu ────────────────────
test('akış, indirVeDogrula\'ya SKU TABLOSU ÇÖZÜLEBİLEN manifesti geçirir', async () => {
  let gecen = null;
  const tam = { indirVeDogrula: async (v, man) => { gecen = man; return { ad: 'ok', version: v }; } };
  await tamPaketiIndir({ deltaUpdater: sahteDelta(gercekZarf()), tamGuncelleyici: tam, version: SURUM });

  assert.ok(gecen, 'indirVeDogrula hiç çağrılmadı');
  assert.equal(gecen.man, undefined, 'zarf geçirilmiş — kusur geri geldi');
  // Kapının kendi mantığıyla ölç: bu manifest gerçekten dört SKU'yu çözüyor mu?
  const tablo = skuTablosu(gecen.skus);
  for (const sku of ['lite', 'offline', 'win-x64-lite', 'win-x64-offline']) {
    const ad = skuVarligi(sku, SURUM);
    assert.ok(tablo[ad], `${ad} imzalı parmak izinde bulunamadı`);
  }
});

test('akış ilerlemeyi devreder ve indirilen dosyayı döndürür', async () => {
  const goruldu = [];
  const tam = { indirVeDogrula: async (v, m, onProgress) => { onProgress({ asama: 'x' }); return { ad: 'A', version: v }; } };
  const r = await tamPaketiIndir({
    deltaUpdater: sahteDelta(gercekZarf()), tamGuncelleyici: tam, version: SURUM,
    onProgress: (p) => goruldu.push(p),
  });
  assert.deepEqual(goruldu, [{ asama: 'x' }]);
  assert.equal(r.ad, 'A');
});

// ── ④ Regresyonun kendisi: GERÇEK indirVeDogrula + GERÇEK zarf ─────────────
// Ağa çıkmaz: zarf kapısı indirmeden ÖNCE koşar.
test('gerçek indirVeDogrula zarfı alırsa ÇAĞRIYI suçlar, manifesti değil', async () => {
  const g = new TamGuncelleyici({
    userDataDir: fs.mkdtempSync(path.join(require('os').tmpdir(), 'yuki-tam-')),
    sku: 'lite', platform: 'linux', gunluk: () => {},
  });
  await assert.rejects(
    () => g.indirVeDogrula(SURUM, gercekZarf()),
    (e) => {
      assert.match(e.message, /zarfı .* açılmadan geçirildi/,
        `yanlış yeri gösteren hata döndü: ${e.message}`);
      assert.doesNotMatch(e.message, /parmak izinde/,
        'eski YANILTICI mesaj geri geldi — kusur manifestte sanılır');
      return true;
    });
});

// ── ⑤ Yanlış yerin kapanmadığının kanıtı: doğru manifest kapıyı GEÇER ──────
// `destekleniyor()` gerçek koşar; indirme aşamasına gelindiğini ağa çıkmadan
// ölçmek için indirme fonksiyonunu değil, kapının girdisini doğruluyoruz:
// zarf açılmış manifestle sku kapısı hiçbir hata üretmemeli.
test('doğru manifestte sku kapısı hata üretmez (dört SKU\'nun dördü de)', () => {
  const man = gercekManifest();
  const tablo = skuTablosu(man.skus);
  assert.equal(Object.keys(tablo).length, 4);
  for (const [ad, kayit] of Object.entries(tablo)) {
    assert.match(kayit.sha256, /^[0-9a-f]{64}$/, `${ad} hash biçimi bozuk`);
    assert.ok(kayit.size > 1e8, `${ad} boyutu gerçekçi değil`);
  }
});

// ── ⑥ Kural kodda kalsın: uygulama.js artık zarfı elle açmıyor ─────────────
test('uygulama.js tam paketi akış üzerinden indirir (elle fetchManifest yok)', () => {
  const kod = fs.readFileSync(path.join(__dirname, 'uygulama.js'), 'utf8');
  assert.doesNotMatch(kod, /const man = await getDeltaUpdater\(\)\.fetchManifest/,
    'zarf açılmadan geçiriliyor —  geri geldi');
  assert.match(kod, /tamPaketiIndir\(\{/);
});
