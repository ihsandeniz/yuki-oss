'use strict';
/*  · Electron kabuğu — ana süreç çevirmeni (`dil.js`) kapıları. */
const test = require('node:test');
const assert = require('node:assert');
const fs = require('fs');
const os = require('os');
const path = require('path');

const SOZLUK = require('./dil-sozluk');
const dil = require('./dil');

function gecici() { return fs.mkdtempSync(path.join(os.tmpdir(), 'yuki-dil-')); }

test('kök yoksa ya da dosya yoksa kaynak dil (tr) — backend varsayılanıyla aynı', () => {
  const k = gecici();
  dil.kokAyarla(k);
  assert.strictEqual(dil.aktifDil(), 'tr');
});

test('dil BACKEND dosyasından okunur: config.user.json kazanır', () => {
  const k = gecici();
  fs.writeFileSync(path.join(k, '.env'), 'ASSISTANT_LANGUAGE=tr\n');
  fs.writeFileSync(path.join(k, 'config.user.json'), JSON.stringify({ ASSISTANT_LANGUAGE: 'en' }));
  dil.kokAyarla(k);
  assert.strictEqual(dil.aktifDil(), 'en');
});

test('config.user.json yoksa .env ASSISTANT_LANGUAGE okunur (satır sonu yorumu değer sayılmaz)', () => {
  const k = gecici();
  fs.writeFileSync(path.join(k, '.env'), 'OPENROUTER_API_KEY=x\nASSISTANT_LANGUAGE=en  # yorum\n');
  dil.kokAyarla(k);
  assert.strictEqual(dil.aktifDil(), 'en');
});

test('bozuk config.user.json çökertmez, .env\'e düşer', () => {
  const k = gecici();
  fs.writeFileSync(path.join(k, 'config.user.json'), '{bozuk');
  fs.writeFileSync(path.join(k, '.env'), 'ASSISTANT_LANGUAGE=en\n');
  dil.kokAyarla(k);
  assert.strictEqual(dil.aktifDil(), 'en');
});

test('çalışırken dil değişince YENİDEN BAŞLATMADAN görülür (mtime önbelleği)', () => {
  const k = gecici();
  const cfg = path.join(k, 'config.user.json');
  fs.writeFileSync(cfg, JSON.stringify({ ASSISTANT_LANGUAGE: 'tr' }));
  dil.kokAyarla(k);
  assert.strictEqual(dil.aktifDil(), 'tr');
  fs.writeFileSync(cfg, JSON.stringify({ ASSISTANT_LANGUAGE: 'en' }));
  const t = new Date(Date.now() + 5000);
  fs.utimesSync(cfg, t, t);
  assert.strictEqual(dil.aktifDil(), 'en');
});

test('t(): yer tutucu dolar, eksik anahtar anahtarın kendisini döndürür, ja → en yedeği', () => {
  SOZLUK.tr['__test.x'] = 'Merhaba {ad}';
  SOZLUK.en['__test.x'] = 'Hello {ad}';
  try {
    const k = gecici();
    const cfg = path.join(k, 'config.user.json');
    fs.writeFileSync(cfg, JSON.stringify({ ASSISTANT_LANGUAGE: 'en' }));
    dil.kokAyarla(k);
    assert.strictEqual(dil.t('__test.x', { ad: 'Yuki' }), 'Hello Yuki');
    assert.strictEqual(dil.t('__test.yok'), '__test.yok');
    fs.writeFileSync(cfg, JSON.stringify({ ASSISTANT_LANGUAGE: 'ja' }));
    dil.kokAyarla(k);
    assert.strictEqual(dil.t('__test.x', { ad: 'Yuki' }), 'Hello Yuki');
  } finally {
    delete SOZLUK.tr['__test.x'];
    delete SOZLUK.en['__test.x'];
  }
});

test('sözlük: tr ve en AYNI anahtar kümesini taşır, en değerinde Türkçe harf yok, yer tutucular eş', () => {
  const tr = Object.keys(SOZLUK.tr).sort();
  const en = Object.keys(SOZLUK.en).sort();
  assert.deepStrictEqual(en, tr);
  const yt = (s) => (s.match(/\{\w+\}/g) || []).sort().join(',');
  for (const k of tr) {
    assert.ok(!/[çğıöşüÇĞİÖŞÜ]/.test(SOZLUK.en[k]), `en'de Türkçe harf: ${k}`);
    assert.strictEqual(yt(SOZLUK.en[k]), yt(SOZLUK.tr[k]), `yer tutucu farkı: ${k}`);
  }
});

/* İki eksen (2026-10-04): kabuk ARAYÜZ dilini gösterir; konuşma dili (ja dahil) onu sürmez. */
test('ARAYUZ_DILI konuşma dilini yener: arayüz tr + konuşma ja → kabuk tr', () => {
  const k = gecici();
  fs.writeFileSync(path.join(k, 'config.user.json'), JSON.stringify({ ARAYUZ_DILI: 'tr', ASSISTANT_LANGUAGE: 'ja' }));
  dil.kokAyarla(k);
  assert.strictEqual(dil.aktifDil(), 'tr');
});

test('göç: ARAYUZ_DILI kaydı yok + konuşma ja → en (bugün gördüğü; backend _arayuz_karsiligi ile aynı)', () => {
  const k = gecici();
  fs.writeFileSync(path.join(k, 'config.user.json'), JSON.stringify({ ASSISTANT_LANGUAGE: 'ja' }));
  dil.kokAyarla(k);
  assert.strictEqual(dil.aktifDil(), 'en');
});

test('ARAYUZ_DILI=ja kaydı (elle bozulmuş) arayüz sayılmaz → konuşma karşılığına düşer', () => {
  const k = gecici();
  fs.writeFileSync(path.join(k, 'config.user.json'), JSON.stringify({ ARAYUZ_DILI: 'ja', ASSISTANT_LANGUAGE: 'tr' }));
  dil.kokAyarla(k);
  assert.strictEqual(dil.aktifDil(), 'tr');
});

test('.env ARAYUZ_DILI, .env ASSISTANT_LANGUAGE\'dan önce okunur', () => {
  const k = gecici();
  fs.writeFileSync(path.join(k, '.env'), 'ASSISTANT_LANGUAGE=ja\nARAYUZ_DILI=tr\n');
  dil.kokAyarla(k);
  assert.strictEqual(dil.aktifDil(), 'tr');
});
