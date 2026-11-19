'use strict';
/*  · model indirme penceresi + tepsi menüsü — dil kapıları.
 *
 * Model indirme penceresinin başlığı/açıklaması arayüzden değil manifestten
 * (`name` / `feature`) geliyordu: EN kullanıcı "Ses Tanıma Modeli" okuyordu.
 * Tepsi menüsü ise bir kez kuruluyordu ve dil değişimi ana sürece olay olarak
 * gelmiyor — etiketler kurulduğu dilde donuyordu.
 */
const test = require('node:test');
const assert = require('node:assert');
const fs = require('fs');
const os = require('os');
const path = require('path');

const dil = require('./dil');
const { ModelManager } = require('./model-manager');

const MANIFEST = JSON.parse(fs.readFileSync(path.join(__dirname, 'models-manifest.json'), 'utf8'));
const TR_HARF = /[çğıöşüÇĞİÖŞÜ]/;
const gecici = () => fs.mkdtempSync(path.join(os.tmpdir(), 'yuki-mdil-'));

function dilKur(kod) {
  const k = gecici();
  fs.writeFileSync(path.join(k, 'config.user.json'), JSON.stringify({ ASSISTANT_LANGUAGE: kod }));
  dil.kokAyarla(k);
  return k;
}

test('manifestteki HER model (planlanan dahil) EN ad + açıklama taşıyor', () => {
  // externalModels: dağıtmadığımız ama arayüzde adı geçen modeller (buffalo_l → resmî kaynak)
  const hepsi = { ...MANIFEST.models, ...(MANIFEST.plannedModels || {}), ...(MANIFEST.externalModels || {}) };
  assert.ok(Object.keys(hepsi).length >= 5);   // yerel ses klonlama modeli açık kaynakta yok
  for (const [id, m] of Object.entries(hepsi)) {
    const en = m.i18n && m.i18n.en;
    assert.ok(en && en.name && en.feature, `${id}: i18n.en.name/feature eksik`);
    assert.ok(!TR_HARF.test(en.name + en.feature), `${id}: EN Türkçe harf taşıyor`);
    assert.ok(m.name && m.feature, `${id}: TR kaynak alanı silinmiş`);
  }
});

test('status() ad/açıklamayı AKTİF dilde verir — dil değişince restart\'sız', () => {
  const mm = new ModelManager({
    manifestPath: path.join(__dirname, 'models-manifest.json'),
    writableDir: path.join(gecici(), 'yok'), bundledDir: null,
  });
  dilKur('tr');
  assert.strictEqual(mm.status('whisper-small').name, 'Ses Tanıma Modeli');
  dilKur('en');
  const s = mm.status('whisper-small');
  assert.strictEqual(s.name, 'Speech Recognition Model');
  assert.strictEqual(s.feature, 'Talking by microphone (STT)');
  dilKur('ja');   // ja kaydı yok → en yedeği, TR'ye DÜŞMEZ
  assert.strictEqual(mm.status('whisper-small').name, 'Speech Recognition Model');
});

test('planlanan modelin "henüz yayınlanmadı" hatası adı aktif dilde taşır', () => {
  const mm = new ModelManager({
    manifestPath: path.join(__dirname, 'models-manifest.json'),
    writableDir: path.join(gecici(), 'yok'), bundledDir: null,
  });
  dilKur('en');
  assert.throws(() => mm.status('vrm-avatar'), (e) => e.message.includes('3D Avatar Pack') && !TR_HARF.test(e.message));
});

test('i18n alanı olmayan eski manifest TR ada düşer (geriye uyum)', () => {
  const d = gecici();
  const p = path.join(d, 'm.json');
  fs.writeFileSync(p, JSON.stringify({ schemaVersion: 1, models: { x: { name: 'Eski Ad', feature: 'Eski', asset: 'a', url: 'u', sha256: 's', presenceDir: 'x', extractTo: '.' } } }));
  dilKur('en');
  const mm = new ModelManager({ manifestPath: p, writableDir: path.join(d, 'yok'), bundledDir: null });
  assert.strictEqual(mm.status('x').name, 'Eski Ad');
});

test('dilIzle dil değişimini yakalar (tepsi menüsünün yeniden kurulma tetiği)', async () => {
  const k = dilKur('tr');
  const gelen = [];
  const dur = dil.dilIzle((d) => gelen.push(d), 20);
  await new Promise((r) => setTimeout(r, 60));
  assert.deepStrictEqual(gelen, [], 'dil değişmeden tetiklenmemeli');
  // mtime'ın değiştiği kesin olsun
  const cfg = path.join(k, 'config.user.json');
  fs.writeFileSync(cfg, JSON.stringify({ ASSISTANT_LANGUAGE: 'en' }));
  const t = new Date(Date.now() + 5000); fs.utimesSync(cfg, t, t);
  await new Promise((r) => setTimeout(r, 80));
  dur();
  assert.deepStrictEqual(gelen, ['en']);
});

test('tepsi menüsü dilIzle ile bağlı (uygulama.js)', () => {
  const src = fs.readFileSync(path.join(__dirname, 'uygulama.js'), 'utf8');
  assert.match(src, /dilIzle\(\s*\(\)\s*=>\s*\{[^}]*setContextMenu\(buildTrayMenu\(\)\)/);
});
