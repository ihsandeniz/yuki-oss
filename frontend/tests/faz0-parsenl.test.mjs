/**
 * FAZ 0 · A2 + A3 + A8 — planner.html doğal dil ayrıştırıcısının davranış testi.
 *
 * Kaynak ölçüm: 2026-09-18 i18n taraması § 4
 *   A2 — JS `\b` ASCII-only → "salı", "çarşamba", "önemli" hiç eşleşmiyordu
 *   A3 — "SALI" (büyük harf) → toLowerCase() "sali" → dayMap undefined → NaN →
 *        toISOString() `RangeError: Invalid time value` FIRLATIYORDU
 *   A8 — "bugün" UTC gününden hesaplanıyordu (TR'de 00:00–03:00 arası DÜNÜ verir)
 *
 * Fonksiyonlar planner.html'den CANLI çıkarılır — teste kopyalanmaz.
 * Kopyalansaydı dosya değişince test yeşil kalır, ürün bozulurdu.
 *
 * Koşum:  node --test frontend/tests/faz0-parsenl.test.mjs
 */
import test from 'node:test';
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { fileURLToPath } from 'node:url';
import { dirname, join } from 'node:path';

const KOK = join(dirname(fileURLToPath(import.meta.url)), '..', '..');
const HTML = readFileSync(join(KOK, 'frontend', 'planner.html'), 'utf8');

/** Adı verilen `function X(...) { ... }` bloğunu süslü parantez sayarak çıkar. */
function fonksiyonuCikar(kaynak, ad) {
  const bas = kaynak.indexOf(`function ${ad}(`);
  assert.notEqual(bas, -1, `planner.html içinde function ${ad} bulunamadı`);
  let i = kaynak.indexOf('{', bas);
  let derinlik = 0;
  for (; i < kaynak.length; i++) {
    if (kaynak[i] === '{') derinlik++;
    else if (kaynak[i] === '}') { derinlik--; if (derinlik === 0) return kaynak.slice(bas, i + 1); }
  }
  throw new Error(`function ${ad} kapanmadı`);
}

// `_trKucuk` / `_parcaSil` ok fonksiyonudur (const) — ayrı çıkarıcıyla alınır.
function sabitiCikar(kaynak, ad) {
  const m = kaynak.match(new RegExp(`^const ${ad} = [\\s\\S]*?;$`, 'm'));
  assert.ok(m, `planner.html içinde const ${ad} bulunamadı`);
  return m[0];
}
const kod = [
  sabitiCikar(HTML, '_trKucuk'),
  sabitiCikar(HTML, '_parcaSil'),
  ...['_yerelGun', '_yerelDakika', 'parseNL'].map(a => fonksiyonuCikar(HTML, a)),
].join('\n');
const { parseNL, _yerelGun, _yerelDakika } = new Function(`${kod}; return { parseNL, _yerelGun, _yerelDakika };`)();

const bugun = _yerelGun(new Date());

// ─── A2: Türkçe harfle başlayan/biten kelimeler artık tanınıyor ───────────────

test('A2 · "önemli" önceliği yükseltir (ö ile başlıyor, eski \\b ile ölüydü)', () => {
  const r = parseNL('önemli fatura öde');
  assert.equal(r.priority, 'high');
  assert.ok(!r.title.includes('önemli'), `başlıktan silinmedi: ${r.title}`);
});

test('A2 · "acil" hâlâ çalışıyor (ASCII regresyonu olmasın)', () => {
  assert.equal(parseNL('acil fatura öde').priority, 'high');
});

for (const gun of ['salı', 'çarşamba', 'perşembe', 'pazartesi', 'cuma', 'cumartesi', 'pazar']) {
  test(`A2 · "${gun}" gününe tarih atanıyor`, () => {
    const r = parseNL(`${gun} toplantı`);
    assert.match(r.due_date ?? '', /^\d{4}-\d{2}-\d{2}$/, `tarih atanmadı: ${JSON.stringify(r)}`);
  });
}

test('A2 · kelime İÇİNDE geçen eşleşme tetiklemez (sınır gerçekten sınır mı)', () => {
  // "salıncak" içinde "salı" var ama ayrı kelime değil → tarih ATANMAMALI
  assert.equal(parseNL('salıncak boya').due_date, null);
  // "acilen" içinde "acil" var → öncelik yükselMEMELİ
  assert.equal(parseNL('acilen degil').priority, 'mid');
});

// ─── A3: büyük harfli gün adı çökertmemeli ───────────────────────────────────

test('A3 · "SALI" RangeError fırlatmıyor ve doğru güne atanıyor', () => {
  let r;
  assert.doesNotThrow(() => { r = parseNL('SALI toplantı'); }, /Invalid time value/);
  assert.match(r.due_date ?? '', /^\d{4}-\d{2}-\d{2}$/, `büyük harfli gün tanınmadı: ${JSON.stringify(r)}`);
  assert.equal(r.due_date, parseNL('salı toplantı').due_date, 'büyük/küçük harf farklı gün veriyor');
});

test('A3 · "ÇARŞAMBA" ve "PERŞEMBE" de çökertmiyor', () => {
  for (const g of ['ÇARŞAMBA', 'PERŞEMBE', 'CUMARTESİ']) {
    assert.doesNotThrow(() => parseNL(`${g} iş`), `${g} çökertti`);
  }
});

// `target !== undefined` koruması bugün parseNL üzerinden ULAŞILAMAZ (regex
// alternatifleri dayMap anahtarlarıyla birebir aynı). Bunu mutasyon turunda ölçtüm:
// korumayı kaldırmak testleri kırmıyordu. Yani korumayı doğrulamanın tek dürüst yolu
// ① iki listenin AYRIŞMADIĞINI ölçmek (asıl risk bu — `sabit liste kopyalayan her yer
//    gizli bir dokunma noktasıdır`), ② ayrışma OLSAYDI çökmediğini göstermek.

test('A3 · dayMap anahtarları ile regex alternatifleri AYRIŞMAMIŞ', () => {
  const dm = HTML.match(/const dayMap = \{([^}]*)\}/);
  assert.ok(dm, 'dayMap bulunamadı');
  const anahtarlar = new Set([...dm[1].matchAll(/([\wçğıöşüÇĞİÖŞÜ]+)\s*:/g)].map(m => m[1]));

  const rx = HTML.match(/const dayMatch = lc\(\)\.match\(\/.*?\)\((pazartesi[^)]*)\)/);
  assert.ok(rx, 'gün regex\'i bulunamadı');
  const alternatifler = new Set(rx[1].split('|'));

  const eksik = [...alternatifler].filter(a => !anahtarlar.has(a));
  assert.deepEqual(eksik, [],
    `regex'te olup dayMap'te olmayan gün: ${eksik} → target undefined olur`);
});

test('A3 · liste ayrışsa BİLE çökmüyor (koruma canlı sınandı)', () => {
  // dayMap'ten "salı"yı söküp parseNL'i yeniden kur → eski kod burada
  // RangeError: Invalid time value fırlatıyordu.
  const sakat = kod.replace(/salı:2,/, '');
  assert.notEqual(sakat, kod, 'mutasyon uygulanamadı — test kendini kandırıyor');
  const { parseNL: sakatParse } = new Function(`${sakat}; return { parseNL };`)();
  let r;
  assert.doesNotThrow(() => { r = sakatParse('salı toplantı'); },
    'dayMap eksikken parseNL çöküyor — undefined koruması yok');
  assert.equal(r.due_date, null, 'tanınmayan gün için tarih atanmamalı');
  assert.ok(r.title.includes('salı'), 'başlık korunmalı, görev kaybolmamalı');
});

// ─── A2b: `/i` bayrağı Türkçe büyük harfi KATLAYAMIYOR ───────────────────────
// Bu sınıf taramada değil bu turda ölçüldü: JS case-folding `ı↔I` ve `i↔İ`
// çiftlerini bilmez, 9 anahtar kelimenin 6'sı büyük harfli girdide ölüydü.

test('A2b · "ACİL" önceliği yükseltir (düz ASCII gibi görünür ama /i katlayamıyor)', () => {
  assert.equal(parseNL('ACİL fatura').priority, 'high',
    '"ACİL" yazan kullanıcı yüksek öncelik alamıyor');
});

for (const [buyuk, kucuk] of [['SALI','salı'], ['PAZARTESİ','pazartesi'], ['CUMARTESİ','cumartesi'],
                              ['ÖNEMLİ','önemli'], ['YARIN','yarın'], ['BUGÜN','bugün']]) {
  test(`A2b · "${buyuk}" ile "${kucuk}" aynı sonucu verir`, () => {
    const b = parseNL(`${buyuk} iş`);
    const k = parseNL(`${kucuk} iş`);
    assert.deepEqual(
      { d: b.due_date, p: b.priority },
      { d: k.due_date, p: k.priority },
      `büyük harf farklı sonuç verdi: ${JSON.stringify(b)} vs ${JSON.stringify(k)}`,
    );
  });
}

test('A2b · eşleşen kelime başlıktan temizleniyor, gerisi bozulmuyor', () => {
  assert.equal(parseNL('ACİL SALI saat 09:30 fatura öde').title, 'fatura öde');
  assert.equal(parseNL('önemli bugün market').title, 'market');
});

// ─── A8: gün/saat YEREL hesaplanmalı, UTC değil ──────────────────────────────

test('A8 · "bugün" yerel günü verir', () => {
  assert.equal(parseNL('bugün spor').due_date, bugun);
});

test('A8 · "yarın" yerel günün bir fazlası', () => {
  const y = new Date(); y.setDate(y.getDate() + 1);
  assert.equal(parseNL('yarın spor').due_date, _yerelGun(y));
});

test('A8 · "saat 14:00" NAIVE YEREL kaydedilir (UTC kaymaz)', () => {
  const r = parseNL('bugün saat 14:00 toplantı');
  assert.equal(r.reminder_at, `${bugun}T14:00`,
    `hatırlatma UTC'ye kaydı: ${r.reminder_at} (beklenen ${bugun}T14:00)`);
});

test('A8 · _yerelGun UTC değil yerel takvimi kullanır', () => {
  // Yerel gece yarısından hemen sonrası — UTC+ bölgelerde toISOString() DÜNÜ verirdi
  const gece = new Date(); gece.setHours(0, 30, 0, 0);
  assert.equal(_yerelGun(gece), _yerelGun(new Date(gece.getTime())));
  assert.equal(_yerelGun(gece).slice(8, 10), String(gece.getDate()).padStart(2, '0'));
});

test('A8 · _yerelDakika saat dilimi eki taşımaz (datetime-local sözleşmesi)', () => {
  const d = new Date(2026, 8, 18, 14, 5);
  assert.equal(_yerelDakika(d), '2026-09-18T14:05');
});
