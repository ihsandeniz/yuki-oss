/**
 * Kamera görüşü istemcisi (frontend/js/gorus.js) — sahte kamera, sahte WS, elle saat.
 * Çalıştırma: node --test frontend/tests/test_gorus.mjs
 *
 *  · kamera yalnız görüntü ister (ses yok), video DOM'a eklenmez
 *  · cevap gelmeden ikinci kare yollanmaz (geri basınç)
 *  · sekme 10 sn gizli kalırsa kamera kapanır, gizliyken kare gitmez
 *  · sunucu 4409 (rıza geri çekildi) ile kapatırsa kamera izleri durur, neden 'riza'
 *  · cevaptaki `soyle` cümlesi soyle()'ye gider; yoksa çağrılmaz
 *  · tarayıcı izni vermezse neden 'izin-yok'
 *  · durdur() kamerayı ve WS'i kapatır
 */
import { test } from 'node:test';
import assert from 'node:assert/strict';
import { createRequire } from 'node:module';

const require = createRequire(import.meta.url);
const { GorusOlustur, GIZLI_SINIR_MS } = require('../js/gorus.js');

function sahneKur(ayar = {}) {
  const izler = [{ durdu: false, stop() { this.durdu = true; } }];
  const istekler = [];
  const zamanlar = [];
  const gonderilen = [];
  const soylenen = [];
  const olaylar = [];
  let ws = null;
  const belge = {
    hidden: false,
    eklenen: [],
    createElement(ad) {
      if (ad === 'video') return { videoWidth: 1280, videoHeight: 720, play() { return Promise.resolve(); }, srcObject: null };
      return { width: 0, height: 0, getContext: () => ({ drawImage() {} }), toBlob(f) { f({ boyut: 10 }); } };
    },
  };
  const md = {
    getUserMedia(kisit) {
      istekler.push(kisit);
      if (ayar.izinYok) return Promise.reject(Object.assign(new Error('x'), { name: 'NotAllowedError' }));
      return Promise.resolve({ getTracks: () => izler });
    },
  };
  const g = GorusOlustur({
    mediaDevices: md, belge, jeton: 'j',
    konum: { protocol: 'http:', host: '127.0.0.1:8001' },
    zamanla(f, ms) { zamanlar.push(f); return zamanlar.length; },
    iptal() {},
    wsAc(url) {
      ws = { url, readyState: 1, kapandi: false, send(b) { gonderilen.push(b); }, close() { this.kapandi = true; } };
      return ws;
    },
    soyle(m) { soylenen.push(m); },
    dinle(m) { olaylar.push(m); },
  });
  return {
    g, izler, istekler, gonderilen, soylenen, olaylar, belge,
    ws: () => ws,
    tik() { const f = zamanlar.shift(); if (f) f(); },
    cevap(m) { ws.onmessage({ data: JSON.stringify(m) }); },
  };
}

test('kamera yalnız görüntü ister, url yerel /ws/gorus + jeton', async () => {
  const s = sahneKur();
  await s.g.baslat();
  assert.equal(s.istekler[0].audio, false);
  assert.ok(s.istekler[0].video);
  assert.equal(s.ws().url, 'ws://127.0.0.1:8001/ws/gorus?token=j');
  assert.equal(s.g.durum().durum, 'acik');
});

test('cevap gelmeden ikinci kare yollanmaz', async () => {
  const s = sahneKur();
  await s.g.baslat();
  s.tik();
  s.tik();
  assert.equal(s.gonderilen.length, 1);
  s.cevap({ tip: 'tamam' });
  s.tik();
  assert.equal(s.gonderilen.length, 2);
});

test('gizli sekmede kare gitmez, 10 sn sonra kamera kapanır', async () => {
  const s = sahneKur();
  await s.g.baslat();
  s.belge.hidden = true;
  for (let i = 0; i < GIZLI_SINIR_MS / 1000 - 1; i++) s.tik();
  assert.equal(s.gonderilen.length, 0);
  assert.equal(s.g.durum().durum, 'acik');
  s.tik();
  assert.equal(s.g.durum().durum, 'kapali');
  assert.equal(s.g.durum().neden, 'gizli');
  assert.ok(s.izler.every((t) => t.durdu));
});

test('sunucu 4409 ile kapatınca kamera durur, neden riza', async () => {
  const s = sahneKur();
  await s.g.baslat();
  s.ws().onclose({ code: 4409 });
  assert.equal(s.g.durum().durum, 'kapali');
  assert.equal(s.g.durum().neden, 'riza');
  assert.ok(s.izler.every((t) => t.durdu));
  assert.ok(s.olaylar.some((o) => o.tip === 'durum-degisti' && o.neden === 'riza'));
});

test('soyle cümlesi iletilir, yoksa çağrılmaz', async () => {
  const s = sahneKur();
  await s.g.baslat();
  s.cevap({ tip: 'durum', yuz: 1, soyle: null });
  s.cevap({ tip: 'durum', yuz: 1, soyle: 'Tekrar hoş geldin Deniz.' });
  assert.deepEqual(s.soylenen, ['Tekrar hoş geldin Deniz.']);
});

test('izin verilmezse neden izin-yok, durum kapali', async () => {
  const s = sahneKur({ izinYok: true });
  await assert.rejects(s.g.baslat());
  assert.equal(s.g.durum().durum, 'kapali');
  assert.equal(s.g.durum().neden, 'izin-yok');
});

test('durdur kamerayı ve WS i kapatır, video DOM a eklenmez', async () => {
  const s = sahneKur();
  await s.g.baslat();
  const w = s.ws();
  s.g.durdur();
  assert.ok(w.kapandi);
  assert.ok(s.izler.every((t) => t.durdu));
  assert.equal(s.belge.eklenen.length, 0);
  s.tik();
  assert.equal(s.gonderilen.length, 0);
});
