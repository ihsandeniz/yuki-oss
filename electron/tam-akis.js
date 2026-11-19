/**
 * TAM PAKET indirme AKIŞI — manifesti çek, ZARFI AÇ, tam güncelleyiciye ver.
 *
 * ═══ NEDEN AYRI DOSYA ════════════════════════════════════════════════════════
 * Bu üç satır `uygulama.js`'in `ipcMain.handle('tam:indir')` gövdesinde duruyordu
 * ve **hiç test edilemiyordu** (Electron penceresi kurmadan çalıştırılamaz).
 * Orada 2026-08-08'den 2026-09-11'e kadar sessiz bir kusur yaşadı (``):
 *
 *     const man = await getDeltaUpdater().fetchManifest(version);   // ❌ ZARF
 *
 * `fetchManifest` tek bir manifest değil **`{man, ham}` zarfı** döndürür (ham
 * gövde imzayla birlikte saklanmak zorunda). Zarf açılmadan geçirilince
 * `manifest.skus` `undefined` kaldı, `indirVeDogrula`'nın güvenlik kapısı meşru
 * güncellemeyi *"bu sürümün imzalı parmak izinde X yok"* diye reddetti ve
 * **hata mesajı yanlış yeri gösterdi**: sorun manifestte değil, çağrıdaydı.
 *
 * Yol seyrek — yalnız `shell_id` değişen sürümlerde açılıyor — bu yüzden bir ay
 * boyunca kimse görmedi. Birim testi de göremedi: doğru şekilli bir mock
 * veriyordu, yani **testin varsaydığı sözleşme ile üretimdeki çağrı ayrışmıştı.**
 *
 * 📏 Ders (`motor-bekle.js` ve `dis-baglanti.js` ile aynı): kuralı Electron'dan
 * ayır ki **ölçülen kod ile satılan kod aynı olsun**.
 */

/**
 * `fetchManifest` sözleşmesi: `{ man, ham }`.
 *
 * Burada hoşgörülü davranmıyoruz (çıplak manifesti de kabul etmiyoruz): zarfla
 * çıplağı aynı kapıdan geçirmek, çağıranın hangisini verdiğini bir daha kimsenin
 * bilmemesi demektir — kusurun ilk hâli tam olarak bu belirsizlikten doğdu.
 */
const _et = require('./dil').t;

function zarfiAc(zarf) {
  if (!zarf || typeof zarf !== 'object') {
    throw new Error(_et('guncel.manifest-bos'));
  }
  if (!zarf.man || typeof zarf.man !== 'object') {
    throw new Error(_et('guncel.zarf-sozlesme'));
  }
  return zarf.man;
}

/**
 * Tam paketi indir + doğrula.
 *
 * Hash'ler İMZALI delta manifestinden gelir — imza doğrulaması `fetchManifest`
 * içinde yapılır. Ayrı/imzasız bir kaynaktan hash almak tüm güven zincirini
 * boşa çıkarırdı.
 *
 * @returns {Promise<{dosya:string, ad:string, boyut:number, version:string}>}
 */
async function tamPaketiIndir({ deltaUpdater, tamGuncelleyici, version, onProgress = () => {} }) {
  const man = zarfiAc(await deltaUpdater.fetchManifest(version));
  return tamGuncelleyici.indirVeDogrula(version, man, onProgress);
}

module.exports = { tamPaketiIndir, zarfiAc };
