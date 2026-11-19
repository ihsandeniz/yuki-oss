/**
 * SÜRÜM KİMLİĞİ — "hangi sürümdeyim?" sorusunun TEK cevabı.
 *
 * ── Neden ayrı bir modül ─────────────────────────────────────────────────
 * 2026-08-02 saha kusuru (`dfdd47a`): panel çalışan sürümü DOĞRU gösteriyordu,
 * ama *karşılaştırma* başka bir kaynaktan besleniyordu (`app.getVersion()` =
 * ASAR'daki paket sürümü). Delta paket sürümünü değiştirmez — değiştirmemesi
 * delta'nın tanımıdır — dolayısıyla `0.5.7 > 0.5.6` sonsuza kadar doğru kaldı
 * ve güncelleme kullanıcı açısından **hiç bitmedi**.
 *
 * Ders: aynı soruya iki yerde cevap üretilirse er geç ayrışırlar ve ayrıştıkları
 * yere kimse bakmaz. Artık cevap tek yerde üretilir; UI, günlük, hata raporu ve
 * güncelleme karşılaştırması hepsi buradan beslenir.
 *
 * ── Üç sürüm, üç ayrı soru ───────────────────────────────────────────────
 *   paket   : kabuğun sürümü (ASAR + Python runtime + medya). İndirilen dosya.
 *   overlay : delta ile uygulanmış kod sürümü. Yoksa null.
 *   etkin   : kullanıcının GERÇEKTEN çalıştırdığı sürüm — karşılaştırma bunu kullanır.
 *
 * Ayrıca `kabukKimligi` (shell_id): kabuğun parmak izi. Delta yükün bu kuruluma
 * uyup uymadığını belirler; tutmuyorsa istemci tam indirmeye düşer.
 */
// ⚠️ `etkinSurumSec` BURAYA devredilir, kopyalanmaz. 2026-08-03 denetiminde bu
// modül seçimi kendi içinde yeniden yazmış hâlde bulundu — yani bu dosyanın
// varlık sebebi olan "aynı soruya iki cevap" kusuru bizzat burada tekrar etmişti.
const { compareVersions, etkinSurumSec } = require('./updater');

/**
 * @param {object} o
 * @param {string} o.paketSurumu       app.getVersion()
 * @param {?string} o.overlaySurumu    deltaUpdater.applied()?.version
 * @param {?string} o.kabukKimligi     shell-id.txt
 * @param {object} [o.katman]          global.__YUKI_KATMAN__
 * @returns {{paket, overlay, etkin, kabukKimligi, govdeOverlayden, guvenliMod, kaynak}}
 */
function kimlik({ paketSurumu, overlaySurumu = null, kabukKimligi = null, katman = {} }) {
  const etkin = etkinSurumSec(paketSurumu, overlaySurumu);
  // ⚠️ `etkin === overlaySurumu` ile YAZILAMAZ: iki sürüm eşitse etkinSurumSec
  // paketi döndürür ama string'ler birebir aynıdır → overlay geçerli sanılırdı.
  const overlayGecerli = !!overlaySurumu && compareVersions(overlaySurumu, paketSurumu) > 0;
  return {
    paket: paketSurumu,
    overlay: overlaySurumu,
    etkin,
    kabukKimligi,
    // Electron gövdesi (uygulama.js) overlay'den mi yüklendi? Bu, "hangi kod
    // çalışıyor" sorusunun *Python'dan bağımsız* cevabı: v0.5.8 öncesi yüklerde
    // backend güncel ama Electron katmanı paketten gelir.
    govdeOverlayden: !!katman.govdeOverlayden,
    guvenliMod: !!katman.guvenliMod,
    kaynak: overlayGecerli
      ? (katman.govdeOverlayden ? 'overlay (tam)' : 'overlay (yalnız uygulama kodu)')
      : 'paket',
  };
}

/** Kullanıcıya/hata raporuna tek satır: "v0.5.8 (paket v0.5.7 + güncelleme)". */
function ozet(k) {
  if (k.guvenliMod) return `v${k.etkin} — GÜVENLİ MOD (güncelleme yok sayıldı)`;
  if (k.etkin === k.paket) return `v${k.etkin}`;
  const kapsam = k.govdeOverlayden ? '' : ', yalnız uygulama kodu';
  return `v${k.etkin} (paket v${k.paket} + güncelleme${kapsam})`;
}

module.exports = { kimlik, ozet };
