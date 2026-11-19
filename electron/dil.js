/* ════════════════════════════════════════════════════════════════════
   dil.js — Electron ANA SÜRECİNİN çevirmeni  (Electron kabuğu)

   Arayüzün `window.YukiDil`'i ana süreçte yok. Ama ana süreç de kullanıcıya
   metin gösteriyor: açılış ekranı, "motor yanıt vermedi" penceresi, tepsi
   menüsü, klasör seçici, güncelleme/model indirme hata sebepleri. Bunlar
   arayüz YÜKLENMEDEN ÖNCE de çizilebilir — yani dili arayüzden soramaz.

   ── 🔑 OTORİTE: ikinci bir kaynak YOK ───────────────────────────────────
   Dilin gerçeği backend'dir (`config.set_language` → `config.user.json`,
   frontend/js/dil.js başlığı). O dosya `YUKI_DATA_DIR`'de, yani Electron'un
   `userData`'sında durur — ana süreç onu **doğrudan okur**. IPC ile dil
   bildirmek ya da ayrı bir `dil.json` tutmak ikinci bir yazma yolu olurdu
   ve iki kaynak er geç ayrışır (tema.js `data-theme`/`data-tema` dersi).

   Kabuk ARAYÜZ dilini gösterir (2026-10-04, iki eksen: arayüz tr/en ≠ konuşma
   tr/en/ja).
   Okuma sırası backend'in açılış sırasıyla AYNI (`config.py` dosya sonu):
     config.user.json ARAYUZ_DILI → .env ARAYUZ_DILI
     → (kayıt yok = iki eksenden önceki kurulum) konuşma dilinin karşılığı:
       config.user.json → .env ASSISTANT_LANGUAGE, `ja` → `en` → 'tr'
   Dosya mtime'ı değişmedikçe yeniden okunmaz; dil değişince bir sonraki
   `t()` çağrısı yeni dili görür (yeniden başlatma gerekmez).

   ── Günlük satırları ÇEVRİLMEZ ───────────────────────────────────────────
   `acilis.log` / `guncelleme.log` destek içindir; hep aynı dilde olmaları
   arıza incelerken aranabilir olmalarını sağlar. Bu modül yalnız
   KULLANICININ GÖRDÜĞÜ metin içindir.

   Sözlük: `dil-sozluk.js` ({tr, en}). Eksik anahtar zinciri frontend'le
   aynı: aktif → (ja ise en) → tr → anahtarın kendisi.
   ════════════════════════════════════════════════════════════════════ */
'use strict';

const fs = require('fs');
const path = require('path');
const SOZLUK = require('./dil-sozluk');

const KAYNAK = 'tr';
const YEDEK = { ja: ['en'] };

let _kok = null;          // test için elle verilebilir (kokAyarla)
let _onbellek = { imza: null, dil: KAYNAK };

function _veriKoku() {
  if (_kok) return _kok;
  if (process.env.YUKI_DATA_DIR) return process.env.YUKI_DATA_DIR;
  try {
    const { app } = require('electron');
    if (app && typeof app.getPath === 'function') return app.getPath('userData');
  } catch (_) { /* electron dışında (node --test) */ }
  return null;
}

function _kodla(v) {
  const k = String(v || '').trim().toLowerCase().replace(/^["']|["']$/g, '');
  return SOZLUK[k] || k === 'ja' ? k : null;
}

/* Konuşma dili → arayüz karşılığı. Backend `config._arayuz_karsiligi` ile aynı göç
   kuralı: sözlüğü olmayan konuşma dili (`ja`) bugün gördüğü `en`'e düşer. */
function _arayuzKarsiligi(k) { return k && SOZLUK[k] ? k : (k ? 'en' : null); }

function _envdenOku(dosya, anahtar) {
  const ham = fs.readFileSync(dosya, 'utf8');
  const m = ham.match(new RegExp('^\\s*' + anahtar + '\\s*=\\s*([^\\s#]+)', 'm'));
  return m ? _kodla(m[1]) : null;
}

/** Aktif ARAYÜZ dil kodu (tr/en) — backend'in yazdığı dosyadan. */
function aktifDil() {
  const kok = _veriKoku();
  if (!kok) return KAYNAK;
  const cfg = path.join(kok, 'config.user.json');
  const env = path.join(kok, '.env');
  let imza = '';
  for (const f of [cfg, env]) {
    try { imza += f + ':' + fs.statSync(f).mtimeMs + ';'; } catch (_) { imza += f + ':-;'; }
  }
  if (imza === _onbellek.imza) return _onbellek.dil;

  let j = null;
  try { j = JSON.parse(fs.readFileSync(cfg, 'utf8')); } catch (_) { /* yok ya da bozuk → .env'e düş */ }
  const envden = (anahtar) => { try { return _envdenOku(env, anahtar); } catch (_) { return null; } };
  const arayuz = (k) => (k && SOZLUK[k] ? k : null);   // arayüz kaydı yalnız tr/en
  let dil = arayuz(_kodla(j && j.ARAYUZ_DILI)) || arayuz(envden('ARAYUZ_DILI'));
  if (!dil) dil = _arayuzKarsiligi(_kodla(j && j.ASSISTANT_LANGUAGE) || envden('ASSISTANT_LANGUAGE'));
  _onbellek = { imza, dil: dil || KAYNAK };
  return _onbellek.dil;
}

/** Çeviri. `{ad}` yer tutucuları `degerler`'den dolar. */
function t(anahtar, degerler) {
  const aktif = aktifDil();
  const zincir = [aktif].concat(YEDEK[aktif] || [], [KAYNAK]);
  let metin = null;
  for (const k of zincir) {
    if (SOZLUK[k] && Object.prototype.hasOwnProperty.call(SOZLUK[k], anahtar)) { metin = SOZLUK[k][anahtar]; break; }
  }
  if (metin == null) return String(anahtar);
  if (degerler) {
    metin = metin.replace(/\{(\w+)\}/g, (tam, ad) =>
      (Object.prototype.hasOwnProperty.call(degerler, ad) ? String(degerler[ad]) : tam));
  }
  return metin;
}

/**
 * Dil değişimini izle — ana süreçte dil değişim OLAYI yok (arayüzün `yuki-dil-degisti`
 * olayı yalnız pencerede yayınlanır), ama dil backend'in yazdığı dosyadan okunur. Tepsi
 * menüsü gibi bir kez kurulan yüzeyler bununla yeniden kurulur. Maliyet: aralık başına
 * iki `stat` (aktifDil mtime önbellekli). Aralık `unref`'li — süreci ayakta tutmaz.
 * Dönüş: durdurma fonksiyonu.
 */
function dilIzle(geriCagir, aralikMs = 3000) {
  let son = aktifDil();
  const zam = setInterval(() => {
    let d;
    try { d = aktifDil(); } catch (_) { return; }
    if (d !== son) {
      son = d;
      try { geriCagir(d); } catch (_) { /* izleyici kabuğu asla düşürmez */ }
    }
  }, aralikMs);
  if (zam.unref) zam.unref();
  return () => clearInterval(zam);
}

/** Test/araç kancası: veri kökünü elle ver, önbelleği sıfırla. */
function kokAyarla(kok) { _kok = kok; _onbellek = { imza: null, dil: KAYNAK }; }

module.exports = { t, aktifDil, dilIzle, kokAyarla, KAYNAK };
