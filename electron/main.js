/**
 * ÖNYÜKLEYİCİ — ASAR'ın içinde kalan, ASLA güncellenmeyen giriş noktası.
 *
 * ⚠️ BU DOSYAYA ÖZELLİK EKLEME. Buradaki her satır, güncellenemeyen koddur.
 * Uygulamanın gerçek gövdesi `uygulama.js`'tedir ve delta ile güncellenir.
 *
 * ── Neden var ────────────────────────────────────────────────────────────
 * Delta güncelleyici `backend/app` + `frontend` taşıyordu; Electron katmanı
 * (`main.js` & kardeşleri) taşımıyordu. Ölçüm (2026-08-03, win-unpacked):
 *
 *     pybundle-win  764 MB   ·  frontend/assets   97 MB
 *     Electron      ~180 MB  ·  backend/app      1,0 MB
 *     app.asar     162 KB  ← TÜM Electron JS'i
 *
 * Yani müşteriye **440 MB** indirten şey paketin **on binde biri**ydi. İki fix
 * tam bu yüzden sahada mahsur kaldı: Windows log encoding'i ve — ironisi burada —
 * *güncellemenin hiç bitmemesini* düzelten yamanın kendisi (`dfdd47a`).
 *
 * ── Nasıl çalışır ────────────────────────────────────────────────────────
 * Python tarafındaki desenin aynısı: orada `-c` önyükleyicisi overlay'i
 * `sys.path[0]`'a sokuyor. Burada da ASAR'da küçük bir önyükleyici kalıyor,
 * gövde overlay'den geliyor:
 *
 *     main.js (ASAR, dokunulmaz)
 *       ├─ sağlıklı overlay var mı? → <overlay>/electron/uygulama.js
 *       └─ yoksa · güvenli mod · patladı → paketlenmiş uygulama.js
 *
 * ── Neden burada ROLLBACK kararı da veriliyor ────────────────────────────
 * Eskiden geri alma kararı main.js'in *içindeydi*. Artık o dosya overlay'den
 * gelebiliyor → kendi bozukluğuna kendisi karar veremez. Karar, güncellenemeyen
 * tek yere yani buraya taşındı. `uygulama.js` require anında patlarsa sayaç
 * artar, üst üste MAX_FAIL olursa overlay atılır.
 *
 * ── Güvenli mod ──────────────────────────────────────────────────────────
 *     YUKI_GUVENLI_MOD=1 ./Yuki...      → overlay tamamen yok sayılır
 * Bozuk bir güncelleme uygulamayı açılmaz hale getirirse kurtarma yolu budur.
 */
const path = require('path');
const fs = require('fs');
const { app } = require('electron');
const { govdeSec, devProfilYolu } = require('./onyukleme');

const PAKET_KOK = __dirname;
const GUVENLI_MOD = process.env.YUKI_GUVENLI_MOD === '1';

// Geliştirme profili — paketlenmiş kurulumla karışmasın diye paketlenmemiş
// koşuda userData ayrılır. Kararın tamamı (ve neden müşteride ASLA koşmadığı)
// onyukleme.js::devProfilYolu'da. Burada olmak ZORUNDA: aşağıdaki her satır
// app.getPath('userData')'ya dokunuyor.
const DEV_PROFIL = devProfilYolu({
  paketlenmis: app.isPackaged, argv: process.argv, env: process.env,
  appDataKok: (() => { try { return app.getPath('appData'); } catch (_) { return null; } })(),
});
if (DEV_PROFIL) app.setPath('userData', DEV_PROFIL);

/** Önyükleyici günlüğü — eklemeli. "Açılmadı" şikâyetinde ilk bakılacak yer. */
function gunlukYaz(satir) {
  try {
    const dosya = path.join(app.getPath('userData'), 'guncelleme.log');
    fs.mkdirSync(path.dirname(dosya), { recursive: true });
    fs.appendFileSync(dosya, `[${new Date().toISOString()}] ${satir}\n`, 'utf8');
  } catch (_) { /* günlük yazılamaması açılışı engellemez */ }
  console.error('[önyükleyici]', satir);
}

function yeniUpdater() {
  const { DeltaUpdater } = require('./delta-updater');   // ⚠️ bilerek PAKETLENMİŞ kopya
  return new DeltaUpdater({ userDataDir: app.getPath('userData'), gunluk: gunlukYaz });
}

const secim = govdeSec({
  paketKok: PAKET_KOK,
  // Paketin kendi sürümü — kurulum userData'ya dokunmadığı için tam paket
  // bir overlay'in üstüne gelebilir; bayat overlay bu kıyasla eleniyor.
  paketSurumu: (() => { try { return app.getVersion(); } catch (_) { return null; } })(),
  guvenliMod: GUVENLI_MOD,
  updater: (() => { try { return yeniUpdater(); } catch (_) { return null; } })(),
  varMi: (y) => { try { return fs.existsSync(y); } catch (_) { return false; } },
  gunluk: gunlukYaz,
});

const overlaydanMi = secim.govdeOverlayden;

// Gövdeye bağlam: overlay'den çalışıyorsa `__dirname` artık paketi göstermez,
// paketlenmiş kaynakları (shell-id.txt, models-manifest.json, splash.html…)
// bulmak için kökü AÇIKÇA taşımak gerekir.
global.__YUKI_KATMAN__ = {
  paketKok: PAKET_KOK,
  overlayKok: secim.overlayKok,
  overlaySurum: secim.surum,
  govdeOverlayden: overlaydanMi,
  guvenliMod: GUVENLI_MOD,
};

try {
  if (overlaydanMi) gunlukYaz(`gövde overlay'den yükleniyor: v${secim.surum}`);
  require(secim.yol);
} catch (e) {
  if (!overlaydanMi) throw e;   // paketlenmiş gövde patlıyorsa kurtaracak bir şey yok

  // Overlay'in gövdesi require anında patladı → bu overlay bozuk. Sayacı artır,
  // tavanı aşarsa at, HER HÂLÜKÂRDA bu açılışta paketlenmiş sürümle devam et.
  gunlukYaz(`overlay gövdesi PATLADI (${e.message}) — paketlenmiş sürüme dönülüyor`);
  try {
    const { DeltaUpdater } = require('./delta-updater');
    const u = new DeltaUpdater({ userDataDir: app.getPath('userData'), gunluk: gunlukYaz });
    const sayac = u.denemeIsaretle();
    if (sayac && sayac >= DeltaUpdater.MAX_FAIL) {
      const r = u.geriAl('overlay gövdesi yüklenemedi');
      gunlukYaz(`GERİ ALINDI → v${r.version} atıldı (${sayac} başarısız deneme)`);
    }
  } catch (_) { /* sayaç tutulamazsa da açılış sürmeli */ }

  global.__YUKI_KATMAN__.govdeOverlayden = false;
  global.__YUKI_KATMAN__.overlayKok = null;
  require(path.join(PAKET_KOK, 'uygulama.js'));
}
