/**
 * ÖNYÜKLEME KARARI — hangi gövde çalışacak, overlay geri alınmalı mı?
 *
 * `main.js`'ten ayrı bir dosyada, çünkü burası **tuğlalaşma riskinin tamamının**
 * yaşadığı yer: yanlış karar = açılmayan uygulama = kurtarma yolu yok. Test
 * edilemeyen bir karar noktası olarak bırakılamazdı. `main.js` yalnız yapıştırıcı.
 *
 * ⚠️ Bu dosya da `main.js` gibi ASAR'da kalır — `YASAK_YOLLAR`'da (delta-updater.js).
 * Kendini güncelleyebilen bir kurtarma mekanizması kurtarma mekanizması değildir.
 *
 * Saf tutuldu: `electron`, `fs`, `app` doğrudan çağrılmaz — hepsi parametre.
 */
const path = require('path');
const { compareVersions } = require('./updater');   // saf sürüm karşılaştırma, `electron` çekmez

/**
 * @param {object} o
 * @param {string} o.paketKok        ASAR içindeki electron dizini (__dirname)
 * @param {?string} o.paketSurumu    paketin kendi sürümü — bayat overlay'i elemek için
 * @param {boolean} o.guvenliMod     YUKI_GUVENLI_MOD=1
 * @param {?object} o.updater        DeltaUpdater örneği (yoksa/patlarsa pakete düşülür)
 * @param {function(string): boolean} o.varMi  dosya var mı (fs.existsSync)
 * @param {function(string): void} o.gunluk    eklemeli günlük
 * @returns {{yol, overlayKok, surum, govdeOverlayden, geriAlindi}}
 */
function govdeSec({ paketKok, paketSurumu, guvenliMod, updater, varMi, gunluk }) {
  const paketGovde = path.join(paketKok, 'uygulama.js');
  const pakete = (ek = {}) => ({
    yol: paketGovde, overlayKok: null, surum: null,
    govdeOverlayden: false, geriAlindi: null, ...ek,
  });

  if (guvenliMod) {
    gunluk('GÜVENLİ MOD — overlay yok sayıldı, paketlenmiş sürüm kullanılıyor');
    return pakete();
  }
  if (!updater) return pakete();

  let durum;
  try {
    durum = updater.saglikli();
  } catch (e) {
    gunluk(`overlay durumu okunamadı, pakete dönülüyor: ${e.message}`);
    return pakete();
  }

  if (durum && durum.geriAlinmali) {
    let r = null;
    try { r = updater.geriAl('uygulama üst üste açılamadı'); } catch (_) { /* yine de pakete */ }
    gunluk(`GERİ ALINDI → v${r && r.version} atıldı, paketlenmiş sürüme dönüldü`);
    return pakete({ geriAlindi: r && r.version });
  }
  if (!durum || !durum.kullan) return pakete();

  // ── Bayat overlay: TAM PAKET kurulumu overlay'i geçmiş olabilir ──────────
  // Kurulum `userData`'ya dokunmaz. Müşteri v0.5.7 kullanırken delta almışsa
  // `updates/0.5.7/` orada durur; üstüne v0.5.8 tam paketi kurulunca overlay
  // hâlâ "sağlıklı" görünür (imzası geçerli, ağacı bütün) ve **yeni paketin
  // kodunu gölgeler** — Python overlay'i `sys.path[0]`'a alır, gövde de
  // overlay'den yüklenir. Yani tam paketle gönderilen düzeltmeler sessizce
  // geri alınır; müşteri güncelledim sanır, hiçbir şey değişmez.
  //
  // Düşürme koruması indirme anında vardı (`downloadAndApply`) ama **açılış
  // anında yoktu**: orada kıyaslanan kurulu overlay, burada kıyaslanması
  // gereken ise paketin kendisi. Overlay kümülatiftir → atmakla bilgi kaybolmaz.
  if (paketSurumu && durum.version && compareVersions(durum.version, paketSurumu) <= 0) {
    let r = null;
    try { r = updater.geriAl('paket overlay\'i geçti (tam kurulum)'); } catch (_) { /* yine de pakete */ }
    gunluk(`BAYAT OVERLAY ATILDI → v${durum.version} ≤ paket v${paketSurumu}, paketlenmiş sürüme geçildi`);
    return pakete({ geriAlindi: r && r.version });
  }

  const overlayGovde = path.join(durum.dir, 'electron', 'uygulama.js');
  if (varMi(overlayGovde)) {
    return {
      yol: overlayGovde, overlayKok: durum.dir, surum: durum.version,
      govdeOverlayden: true, geriAlindi: null,
    };
  }

  // Overlay var ama Electron katmanı taşımıyor — v0.5.8 ÖNCESİ yükler böyle.
  // Bu bir hata değil, geçiş durumu: Python/frontend overlay'den, gövde paketten.
  // Bu dalın kaldırılması eski kurulumları güncellemeden koparırdı.
  return {
    yol: paketGovde, overlayKok: durum.dir, surum: durum.version,
    govdeOverlayden: false, geriAlindi: null,
  };
}

/**
 * GELİŞTİRME PROFİLİ — paketlenmemiş koşuda `userData` ayrılır.
 *
 * Paketin `package.json`'unda `productName` YOK, `name: yuki-oss` → `app.getName()`
 * = `yuki-oss` → userData `~/.config/yuki-oss`. Açık kaynak sürüm kendi adını taşır;
 * kişisel Alice (`alice-ai`) ile çakışmaz (kapı: scripts/test_profil_adi.py).
 * Geliştirme koşusu yine ayrı profile gider ki paketlenmiş kurulumla karışmasın. Eskiden
 * iki kurulum aynı adı taşıyordu ve ayrılmazsa ikisi tek dizini paylaşır: tek-örnek
 * kilidi çakışır (kişisel açıkken ürün `npm start` SESSİZCE çıkar, log'a satır bile
 * yazmaz), `Local Storage` · `Partitions` · `models-cache` · `updates/` karışır.
 * 2026-09-08'de bu, "yüz kütüphanesi hiç inmemiş" diye YANLIŞ bir hükme yol açtı —
 * kütüphane kuruluydu, yalnız başka profildeydi.
 *
 * 🔴 **Paketlenmiş müşteride ASLA çalışmaz.** Oradaki yolu değiştirmek her mevcut
 * kurulumun `.env`'ini (API anahtarı), `app_lock.json`'unu, `faces.json`'unu ve
 * sohbet geçmişini terk eder, `models-cache`'i yeniden indirtir. Müşteri kimliğini
 * değiştirmek ayrı bir iştir ve göç kodu ister.
 *
 * ⚠️ Elle verilen `--user-data-dir` KAZANIR — izole ölçüm profilleri (Playwright
 * turları scratchpad'de kendi profilini kurar) bu kuralla ezilirse ölçüm sessizce
 * geliştiricinin gerçek profiline yazar.
 *
 * @param {object} o
 * @param {boolean} o.paketlenmis   app.isPackaged
 * @param {string[]} o.argv         process.argv
 * @param {object} o.env            process.env
 * @param {?string} o.appDataKok    app.getPath('appData') (Linux: ~/.config)
 * @returns {?string} yeni userData yolu · `null` = dokunma
 */
function devProfilYolu({ paketlenmis, argv = [], env = {}, appDataKok }) {
  if (paketlenmis) return null;
  if (argv.some((a) => String(a).startsWith('--user-data-dir'))) return null;
  if (!appDataKok) return null;
  return path.join(appDataKok, env.YUKI_DEV_PROFIL || 'yuki-urun-dev');
}

module.exports = { govdeSec, devProfilYolu };
