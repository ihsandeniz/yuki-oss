'use strict';
/*  · Electron kabuğu — kullanıcıya giden metin sözlükten gelir (kalıcı kapı).

   Ne korur: kabuk dosyalarına yeni bir Türkçe kullanıcı metni YAZILIRSA kırmızı yanar.
   İngilizce kullanıcı açılış ekranında, hata kutusunda, tepside Türkçe görmesin.

   Kural: Türkçe harfli bir string literal ya
     · günlük satırındadır (acilisKaydi · guncellemeKaydi · gunluk · gunlukYaz · kaydet ·
       console.* · PowerShell `Yaz "…"`) — destek günlüğü tek dilde kalır, aranabilsin, ya
     · aşağıdaki İSTİSNA listesindedir (gerekçesiyle), ya da
     · kusurdur → `_et('kabuk.…')` + `dil-sozluk.js`.

   ⚠️ Kör nokta (bilerek): Türkçe HARFSİZ Türkçe metni ("Bilinmeyen SKU") göremez.
   Taşıma turunda elle tarandı; yeni metin yazarken bunu kendin düşün.
   Tarama: 2026-09-18 i18n taraması (electron bölümü). */
const test = require('node:test');
const assert = require('node:assert');
const fs = require('fs');
const path = require('path');

const SOZLUK = require('./dil-sozluk');

const TR_HARF = /[çğıöşüÇĞİÖŞÜ]/;
const LITERAL = /'((?:[^'\\\n]|\\.)*)'|"((?:[^"\\\n]|\\.)*)"|`((?:[^`\\\n]|\\.)*)`/g;
const GUNLUK = /\b(acilisKaydi|guncellemeKaydi|gunluk|gunlukYaz|kaydet|console\.\w+)\s*\(|^\s*Yaz\s+"/;

/* Dosya → bilerek Türkçe kalan literaller. Gerekçesiz satır istisna değil, unutulmuş açıktır. */
const ISTISNA = {
  'uygulama.js': [
    // Çok satırlı günlük çağrısının DEVAM satırları (araç satırın başını göremez)
    'gerçek=', '(kod sürümü güncel olmayabilir)',
    'UYUŞMAZLIK: motor v${bildirilen} bildiriyor, beklenen v${k.etkin} (${k.kaynak}) —',
    'başarı işaretlenmedi, üst üste tekrarlarsa geri alınacak',
    "${state.x === undefined ? 'ortalanmış' : state.x + ',' + state.y}",
    '\\n[backend] süreç sonlandı — code=${code} signal=${signal}\\n',
    // pencereyiGoster(sebep) / geriAl(sebep): argüman yalnız acilisKaydi'ye gider
    'açılış ekranı', 'emniyet zamanlayıcısı', 'açılış ekranı hatası', 'yükleme hatası',
    'arayüz yüklendi', 'kullanıcı isteği',
    // .env.example başlığı İKİ DİLLİ yazılır: dosya ilk açılışta bir kez, dil seçilmeden
    // yazılıyor ve bir daha ezilmiyor → tek dil EN müşteriye uyarıyı hiç okutmazdı.
    '# ⚠️  BU DOSYA BİR ÖRNEKTİR — Yuki bunu OKUMAZ.',
    "#     Yuki'nin okuduğu dosya aynı klasördeki  .env  dosyasıdır.",
    "# ⛔ Bu dosyayı kopyalayıp .env'in ÜSTÜNE YAZMA — anahtar sihirbazının",
    '#    (⚙ AYAR › 🔑 ANAHTAR) yazdığı API anahtarın silinir.',
    '# ✅ Bir ayarı elle eklemek istersen: aşağıdan İLGİLİ SATIRI kopyalayıp',
    "#    .env dosyasının SONUNA yapıştır ve Yuki'yi yeniden başlat.",
    '# Bu klasör / This folder: ${dataDir}',
  ],
  'delta-updater.js': [
    // 🔴 SÖZLEŞME: `asama` değeri — frontend/js/updater-ui.js `=== 'uygulanıyor'` ile okur
    'uygulanıyor', 'medya uygulanıyor',
    // 🔴 SÖZLEŞME: dosya ağacı kökünün hash girdisi — değişirse files_root tutmaz,
    // kurulu her overlay "kurcalanmış" sayılıp geri alınır
    '${altGoreli}:BAĞ',
    // butunlukDogrula/saglikli sebepleri — yalnız günlüğe ve onyukleme.js'e gider
    // (onyukleme `sebep`'i okumaz, kendi geriAl metnini verir)
    'manifest saklanmamış (eski overlay)', 'saklı manifest bozuk',
    'saklı manifest imzası geçersiz', 'manifest bütünlük kökü taşımıyor',
    'dosya ağacı değişmiş (${kok.slice(0, 12)}… ≠ ${man.files_root.slice(0, 12)}…)',
    'üst üste açılamadı',
  ],
  // surum.js: ozet() hiçbir yerde çağrılmıyor, kimlik().kaynak yalnız guncellemeKaydi'ye
  // gidiyor; guncelleme-katmani.test.js ozet() için TR metin bekliyor. UI'ya çıkarsa çevir.
  'surum.js': [
    'overlay (yalnız uygulama kodu)', 'v${k.etkin} — GÜVENLİ MOD (güncelleme yok sayıldı)',
    ', yalnız uygulama kodu', 'v${k.etkin} (paket v${k.paket} + güncelleme${kapsam})',
  ],
};
const TARANAN = [
  'uygulama.js', 'motor-bekle.js', 'delta-updater.js', 'tam-guncelleme.js', 'tam-akis.js',
  'updater.js', 'model-manager.js', 'pencere-yetenek.js', 'surum.js', 'dis-baglanti.js',
];

function yorumsuzSatirlar(src) {
  src = src.replace(/\/\*[\s\S]*?\*\//g, (m) => '\n'.repeat((m.match(/\n/g) || []).length));
  return src.split('\n').map((s) => (s.trimStart().startsWith('//') ? '' : s));
}

function turkceKacaklar(dosya, kaynak) {
  const istisna = new Set(ISTISNA[dosya] || []);
  const kacak = [];
  yorumsuzSatirlar(kaynak).forEach((s, i) => {
    if (GUNLUK.test(s)) return;
    for (const m of s.matchAll(LITERAL)) {
      const lit = m[1] ?? m[2] ?? m[3];
      if (TR_HARF.test(lit) && !istisna.has(lit) && !istisna.has(lit.trim())) {
        kacak.push(`${dosya}:${i + 1} ${JSON.stringify(lit.slice(0, 70))}`);
      }
    }
  });
  return kacak;
}

test('kabuk dosyalarında günlük dışı Türkçe kullanıcı metni YOK (yeni metin → _et + sözlük)', () => {
  const hepsi = [];
  for (const f of TARANAN) hepsi.push(...turkceKacaklar(f, fs.readFileSync(path.join(__dirname, f), 'utf8')));
  assert.deepStrictEqual(hepsi, [], 'sözlüğe taşınmamış metin:\n' + hepsi.join('\n'));
});

test('istisna listesi bayat değil: her istisna dosyada gerçekten duruyor', () => {
  for (const [f, liste] of Object.entries(ISTISNA)) {
    const src = fs.readFileSync(path.join(__dirname, f), 'utf8');
    for (const s of liste) {
      const ham = s.replace(/\\\\/g, '\\');
      assert.ok(src.includes(s) || src.includes(ham), `${f}: istisna artık yok → listeden sil: ${s}`);
    }
  }
});

test("her _et('anahtar') sözlükte iki dilde de var — eksikse kullanıcı ham anahtar görür", () => {
  const eksik = [];
  for (const f of fs.readdirSync(__dirname).filter((x) => x.endsWith('.js') && !x.endsWith('.test.js'))) {
    const src = fs.readFileSync(path.join(__dirname, f), 'utf8');
    for (const m of src.matchAll(/\b_et\(\s*'([^']+)'/g)) {
      if (!(m[1] in SOZLUK.tr) || !(m[1] in SOZLUK.en)) eksik.push(`${f}: ${m[1]}`);
    }
    if (/\b_et\(/.test(src)) {
      assert.match(src, /const _et = require\('\.\/dil'\)\.t;/, `${f}: _et bağlanmamış`);
    }
  }
  assert.deepStrictEqual(eksik, []);
});

test('splash.html: tr ve en tablosu aynı anahtarları taşır, en Türkçe harf içermez', () => {
  const src = fs.readFileSync(path.join(__dirname, 'splash.html'), 'utf8');
  const blok = /var METIN = (\{[\s\S]*?\n {2}\});/.exec(src);
  assert.ok(blok, 'splash METIN tablosu bulunamadı');
  const METIN = new Function(`return ${blok[1]};`)();
  assert.deepStrictEqual(Object.keys(METIN.en).sort(), Object.keys(METIN.tr).sort());
  for (const [k, v] of Object.entries(METIN.en)) assert.ok(!TR_HARF.test(v), `splash en.${k}: ${v}`);
  // ja gibi tablosu olmayan dil İngilizceye düşer, Türkçeye değil
  assert.match(src, /METIN\[dil\] \|\| METIN\.en/);
});

test('sözlük anahtarları kabuk ön ekleriyle sınırlı (frontend anahtarı karışmasın)', () => {
  const yabanci = Object.keys(SOZLUK.tr).filter((k) => !/^(kabuk|guncel|modelyk|pencere)\./.test(k));
  assert.deepStrictEqual(yabanci, []);
});
