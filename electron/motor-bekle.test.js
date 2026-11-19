/**
 * motor-bekle.js — açılış beklemesinin kuralları.
 *
 * Bu testlerin varlık sebebi (R7, 2026-08-11): eski bekleme sabit 60 sn tavandı,
 * `uygulama.js` içine gömülüydü ve **hiç test edilmemişti**. Sahada motor 62. saniyede
 * hazır oldu, uygulama 60. saniyede pes edip kendini kapattı.
 *
 * Saat enjekte ediliyor (`simdi`/`uyu`) → testler deterministik ve anlıktır;
 * gerçek zamanlı beklemez.
 */
'use strict';

const test = require('node:test');
const assert = require('node:assert');
const http = require('node:http');
const { motorBekle, saglikSorucu } = require('./motor-bekle');

/** Sahte saat — `uyu` çağrıldıkça zaman ilerler, gerçek gecikme yok. */
function sahteSaat(baslangic = 1_000) {
  let t = baslangic;
  return {
    simdi: () => t,
    uyu: async (ms) => { t += ms; },
    ileri: (ms) => { t += ms; },
  };
}

/** Verilen anda hazır olan motor. */
function hazirOlur(saat, ms) {
  const t0 = saat.simdi();
  return async () => ({ ok: saat.simdi() - t0 >= ms, surum: '0.6.1' });
}

const hicHazirOlmaz = async () => ({ ok: false });
const yasiyor = () => null;

test('hazır motorda anında döner ve sürümü taşır', async () => {
  const saat = sahteSaat();
  const r = await motorBekle({
    saglikSor: hazirOlur(saat, 0),
    sonCikti: () => saat.simdi(),
    surecDurumu: yasiyor,
    ...saat,
  });
  assert.equal(r.hazir, true);
  assert.equal(r.surum, '0.6.1');
  assert.equal(r.gecenMs, 0);
});

test('REGRESYON: 62. saniyede hazır olan motor artık yakalanır (eski 60 sn tavanı düşürüyordu)', async () => {
  const saat = sahteSaat();
  const r = await motorBekle({
    saglikSor: hazirOlur(saat, 62_000),
    // Soğuk Windows açılışının gerçek hâli: import fazı boyunca stdout sessiz.
    // Son çıktı başlangıçta kalır — buna rağmen vazgeçilmemeli.
    sonCikti: () => saat.simdi() - 40_000,
    surecDurumu: yasiyor,
    ...saat,
  });
  assert.equal(r.hazir, true, '62. saniyedeki motor hazır sayılmalı');
  assert.ok(r.gecenMs > 60_000, 'eski sabit tavan tam burada düşüyordu');
});

test('motor hiç ses çıkarmazsa DURGUN diye vazgeçer — ama en az bekleme dolmadan değil', async () => {
  const saat = sahteSaat();
  const donma = saat.simdi();
  const r = await motorBekle({
    saglikSor: hicHazirOlmaz,
    sonCikti: () => donma,          // hiçbir yeni çıktı yok = takılmış süreç
    surecDurumu: yasiyor,
    ...saat,
  });
  assert.equal(r.hazir, false);
  assert.equal(r.sebep, 'durgun');
  assert.equal(r.gecenMs, 120_000, 'durgunluk 90 sn dolsa bile en az 120 sn beklenir');
  assert.ok(r.durgunMs >= 90_000);
});

test('çıktı akmaya devam ettiği sürece beklenir — durgunluk sayacı sıfırlanır', async () => {
  const saat = sahteSaat();
  const r = await motorBekle({
    saglikSor: hicHazirOlmaz,
    sonCikti: () => saat.simdi(),   // her yoklamada taze çıktı
    surecDurumu: yasiyor,
    tavanMs: 300_000,
    ...saat,
  });
  assert.equal(r.hazir, false);
  assert.equal(r.sebep, 'tavan', 'ilerleyen motor yalnız mutlak tavanda kesilir');
  assert.equal(r.gecenMs, 300_000);
});

test('süreç öldüyse en az bekleme süresi DOLMADAN döner — beklemek anlamsız', async () => {
  const saat = sahteSaat();
  let olu = null;
  const r = await motorBekle({
    saglikSor: async () => { if (saat.simdi() >= 3_000) olu = { code: 1, signal: null }; return { ok: false }; },
    sonCikti: () => saat.simdi(),
    surecDurumu: () => olu,
    ...saat,
  });
  assert.equal(r.hazir, false);
  assert.equal(r.sebep, 'surec-oldu');
  assert.deepEqual(r.detay, { code: 1, signal: null });
  assert.ok(r.gecenMs < 10_000, `ölü süreç için ${r.gecenMs}ms beklendi — anında dönmeliydi`);
});

test('ilerleme mesajları sırayla ve HER AŞAMA BİR KEZ basılır', async () => {
  const saat = sahteSaat();
  const basilan = [];
  await motorBekle({
    saglikSor: hazirOlur(saat, 130_000),
    sonCikti: () => saat.simdi(),
    surecDurumu: yasiyor,
    ilerleme: (m) => basilan.push(m),
    asamalar: [[10_000, 'bir'], [50_000, 'iki'], [100_000, 'üç']],
    ...saat,
  });
  assert.deepEqual(basilan, ['bir', 'iki', 'üç'], 'her aşama tam bir kez, sırayla');
});

// ── saglikSorucu — GERÇEK HTTP'ye karşı ────────────────────────────────────────
// Sahte istemciyle değil gerçek sunucuyla ölçülüyor: burada yanlış giden şey
// (asılı kalan soket) yalnız gerçek soket davranışında görünür.

/** İstenen davranışı sergileyen tek kullanımlık sunucu. */
function sunucu(isleyici) {
  const s = http.createServer(isleyici);
  return new Promise((r) => s.listen(0, '127.0.0.1', () => r({
    url: `http://127.0.0.1:${s.address().port}`,
    kapat: () => new Promise((k) => s.close(k)),
    sunucuNesnesi: s,
  })));
}

test('saglikSorucu: 200 + sürüm → hazır', async () => {
  const s = await sunucu((_q, y) => { y.writeHead(200, { 'content-type': 'application/json' }); y.end('{"version":"0.6.1"}'); });
  const r = await saglikSorucu(s.url)();
  assert.deepEqual(r, { ok: true, surum: '0.6.1' });
  await s.kapat();
});

test('saglikSorucu: sürüm bildirmeyen eski backend yine de HAZIR sayılır', async () => {
  const s = await sunucu((_q, y) => { y.writeHead(200); y.end('merhaba, ben json değilim'); });
  const r = await saglikSorucu(s.url)();
  assert.equal(r.ok, true, 'bozuk/eksik gövde hazır olmayı iptal etmemeli');
  assert.equal(r.surum, null);
  await s.kapat();
});

test('saglikSorucu: 200 dışı yanıt hazır SAYILMAZ', async () => {
  const s = await sunucu((_q, y) => { y.writeHead(503); y.end('starting'); });
  const r = await saglikSorucu(s.url)();
  assert.equal(r.ok, false);
  await s.kapat();
});

test('saglikSorucu: kapalı porta bağlanamama sessizce "hazır değil" döner', async () => {
  const s = await sunucu((_q, y) => y.end());
  const url = s.url;
  await s.kapat();
  const r = await saglikSorucu(url)();
  assert.equal(r.ok, false);
});

test('saglikSorucu: CEVAP VERMEYEN soket zaman aşımına düşer — sonsuza kadar asılmaz', async () => {
  // Bağlantıyı kabul edip hiç yanıt yazmayan sunucu: `http.get`'in varsayılan
  // zaman aşımı olmadığı için eski kodda bu, bekleme döngüsünün ölümü demekti.
  const s = await sunucu(() => { /* bilerek yanıt yok */ });
  const t0 = Date.now();
  const r = await saglikSorucu(s.url, { zamanAsimiMs: 300 })();
  assert.equal(r.ok, false);
  assert.ok(Date.now() - t0 < 3000, 'zaman aşımı devreye girmedi — istek asılı kaldı');
  s.sunucuNesnesi.closeAllConnections?.();
  await s.kapat();
});

test('kapanış ölçütü ÜÇ KOŞULA bağlı — biri eksikse beklemeye devam edilir', async () => {
  // Durgunluk dolmuş ama en az süre dolmamış → hâlâ beklenir; ve o sırada motor gelirse yakalanır.
  const saat = sahteSaat();
  const donma = saat.simdi();
  const r = await motorBekle({
    saglikSor: hazirOlur(saat, 100_000),
    sonCikti: () => donma,
    surecDurumu: yasiyor,
    ...saat,
  });
  assert.equal(r.hazir, true, '90 sn durgun olsa da en az bekleme dolmadan vazgeçilmez');
  assert.equal(r.gecenMs, 100_000);
});
