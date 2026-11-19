const { app, BrowserWindow, dialog, ipcMain, shell, Tray, Menu, screen } = require('electron');
const { spawn } = require('child_process');
const http = require('http');
const path = require('path');
const fs = require('fs');
const { ModelManager } = require('./model-manager');
const { gorunurAlanaSigdir } = require('./pencere-konum');
const { modBoyutu, MODLAR } = require('./pencere-modu');
const { konumlandirmaYetenegi } = require('./pencere-yetenek');
const { UpdateChecker } = require('./updater');
const { kimlik: surumKimlik, ozet: surumOzeti } = require('./surum');
const { disBaglantiKurallari } = require('./dis-baglanti');
const { miniHudKurallari } = require('./mini-hud');
const { motorBekle, saglikSorucu } = require('./motor-bekle');
const bekciMod = require('./bekci');
const { tamPaketiIndir } = require('./tam-akis');
const oturumAnahtari = require('./oturum-anahtari');
// Kullanıcının GÖRDÜĞÜ metin buradan çözülür; günlük satırları Türkçe kalır.
const _et = require('./dil').t;

/**
 * Katman bağlamı — `main.js` (ASAR'daki önyükleyici) doldurur.
 *
 * 🔴 Bu dosya artık overlay'den de çalışabiliyor (delta ile güncellenir).
 * O durumda `__dirname` **paketi göstermez**, overlay dizinini gösterir →
 * `shell-id.txt` gibi paketlenmiş kaynaklar kaybolur. Bu yüzden paket kökü
 * açıkça taşınır. Geliştirmede (doğrudan `uygulama.js` çalıştırılırsa)
 * `__dirname`'e düşer.
 *
 * ⚠️ 2026-09-05: `models-manifest.json` bu listeden ÇIKTI — artık delta yüküyle
 * de gelebiliyor (indir-gerektiğinde yüklerin kayıt defteri, her yeni yükle
 * değişir) ve `kaynak()` ile okunuyor: overlay'de varsa oradan, yoksa paketten.
 * Eskiden `PAKET_KOK`'ten okunuyordu ve yeni yükler mevcut müşteriye HİÇ
 * ULAŞMIYORDU. → `backend/tests/test_manifest_musteriye_ulasiyor.py`
 */
const KATMAN = global.__YUKI_KATMAN__ || {
  paketKok: __dirname, overlayKok: null, overlaySurum: null,
  govdeOverlayden: false, guvenliMod: false,
};
const PAKET_KOK = KATMAN.paketKok;

/**
 * Katmanlı kaynak çözümü: overlay'de varsa oradan, yoksa paketten.
 *
 * `preload.js`/`splash.html` gibi *kod* dosyaları güncellenebilmeli;
 * `shell-id.txt` gibi *kabuğu tanımlayan* dosyalar ASLA — onlar paketin
 * kimliğidir, overlay onları geçersiz kılarsa delta uyum kontrolü çöker.
 */
function kaynak(...parcalar) {
  if (KATMAN.overlayKok) {
    const aday = path.join(KATMAN.overlayKok, 'electron', ...parcalar);
    if (fs.existsSync(aday)) return aday;
  }
  return path.join(PAKET_KOK, ...parcalar);
}

// GPU stratejisi (2026-07-10): eski 'use-gl=swiftshader' Chromium 148'de GEÇERSİZ —
// WebGL'i korumak yerine TAMAMEN öldürüyordu (webgl2=false → OYUN 3D kapısı kapalı).
// Yerine 'use-angle=swiftshader' (çalışan yazılım WebGL2) kondu.
//
// 🔴 VARSAYILAN = YAZILIM GL, ve YALNIZ LINUX'TA (2026-08-09'da düzeltildi).
// Burada eskiden *"varsayılan artık gerçek GPU"* yazıyordu; 2026-08-02'de güvenli
// varsayılan yazılım GL'e çevrilirken bu cümle güncellenmedi ve aşağıdaki kodla
// çelişik kaldı — kodu okuyanı yanılttı (bizzat oldu). Tek gerçek, alttaki blok:
//   Linux + YUKI_GPU != 'hardware'  →  use-angle=swiftshader + disable-gpu-compositing
//   Windows / macOS                 →  hiçbir bayrak yok, donanım hızlandırma AÇIK
// Gerçek GPU isteyen (3D avatar akıcılığı): YUKI_GPU=hardware.
// ⚠️ Yazılım GL kompozisyonu CPU'ya biner — "CPU yüksek" şikâyeti Linux'tan
// geliyorsa ilk deneyecek şey YUKI_GPU=hardware'dir (Windows'ta bu blok koşmaz).
// Electron 29'un GPU yolu birçok Linux'ta pencere oluşturmayı bozuyor: native Wayland'da (wlroots/
// Hyprland) GBM/SCANOUT ("Cannot create bo"), XWayland+GPU'da EGL_BAD_NATIVE_WINDOW (transparan
// pencere). Güvenli VARSAYILAN: XWayland (x11 ozone) + yazılım GL (SwiftShader) → pencere her yerde
// açılır (Geliştirici Hyprland'de doğrulandı). Gerçek GPU (3D avatar akıcılığı) isteyen: YUKI_GPU=hardware.
// Native Wayland denemek isteyen: YUKI_WAYLAND=1.
// OZONE PLATFORMU SEÇİLMEZ — Chromium'a seçtirilir (2026-08-02).
// Eskiden `ozone-platform=x11` ZORLANIYORDU. Bu makinede (Hyprland + XWayland) Electron 29
// o yolda GERÇEK BİR PENCERE KURAMIYOR: `XGetWindowAttributes failed for window 1` basıp
// sessizce devam ediyor → uygulama çalışır, ekranda hiçbir şey yok. Ölçüldü (2026-08-02):
// x11 + swiftshader ❌ · x11 + gerçek GPU ❌ · wayland + swiftshader ✅ · wayland + GPU ✅
// → suçlu GPU anahtarı değil, ozone platformu.
// Uygulama bu arızayı İÇERİDEN ANLAYAMIYOR (ölçüldü: `isVisible()=true`,
// `capturePage()` dolu kare döndürüyor, `getNativeWindowHandle()` iki durumda da aynı)
// → "algıla ve yedeğe düş" yazılamaz; doğru platformu baştan seçmek tek yol.
// `ozone-platform-hint=auto`: Wayland oturumunda Wayland, değilse X11.
// Elle zorlamak: YUKI_OZONE=wayland|x11|auto (eski YUKI_WAYLAND=1 hâlâ çalışır).
if (process.platform === 'linux') {
  const _ozone = process.env.YUKI_OZONE
    || (process.env.YUKI_WAYLAND === '1' ? 'wayland' : 'auto');
  if (_ozone === 'auto') app.commandLine.appendSwitch('ozone-platform-hint', 'auto');
  else app.commandLine.appendSwitch('ozone-platform', _ozone);
  if (process.env.YUKI_GPU !== 'hardware') {
    app.commandLine.appendSwitch('use-angle', 'swiftshader');
    app.commandLine.appendSwitch('disable-gpu-compositing');
  }
}

let backend = null;
// Motor beklemesinin iki girdisi (motor-bekle.js): en son ne zaman çıktı üretti, ve öldü mü.
// Sabit süre değil, ilerleme ölçülüyor — R7 (2026-08-11).
let sonBackendCiktisi = 0;
let backendCikisi = null;
let win = null;
let tray = null;
let modelManager = null;   // İndir-gerektiğinde model yöneticisi (whenReady'de kurulur)
let updateChecker = null;  // Güncelleme denetleyicisi — VARSAYILAN KAPALI (updater.js)
let deltaUpdater = null;   // Delta güncelleyici — imzalı ~1,2 MiB yük (delta-updater.js)
// Motor portu: tercihen 8791 (kişisel Alice 8000 + yaygın dev portlarıyla çakışmasın).
// Doluysa — başka bir Yuki kopyası ya da başka bir program — boş bir port seçilir; başkasının
// motoruna bağlanılmaz. Kural ve gerekçe: motor-portu.js.
const motorPortu = require('./motor-portu');
const MOTOR_PORT_SECIMI = motorPortu.secSenkron({ dizin: app.getPath('userData') });
const BACKEND_PORT = MOTOR_PORT_SECIMI.port;
const BACKEND_URL = 'http://127.0.0.1:' + BACKEND_PORT;
// Yerel motor oturum anahtarı (v0.8.1) — startBackend belirler, arayüz yüklenmeden çereze konur.
// → oturum-anahtari.js + backend/app/yerel_kapi.py
let OTURUM_ANAHTARI = null;
// Süreç bekçisi (`YUKI_BEKCI=1`, varsayılan KAPALI) — bu açılışta motor bekçi altında mı,
// motor bir kez hazır oldu mu, uygulama kapanıyor mu (kapanışta bekçinin çıkışı arıza değildir),
// bekçi hangi arızayla çıktı (sözlük anahtarı; açılış penceresi de bunu gösterir). → bekci.js
let bekciKullanildi = false;
let motorHazir = false;
let uygulamaKapaniyor = false;
let bekciArizasi = null;

// Tek örnek kilidi — ikinci başlatma yeni pencere/backend açmak yerine mevcut pencereyi öne getirir
if (!app.requestSingleInstanceLock()) {
  app.quit();
} else {
  app.on('second-instance', () => {
    if (!win) return;
    if (win.isMinimized()) win.restore();
    if (!win.isVisible()) win.show();
    win.focus();
  });
}

// ── Pencere Durumu Kalıcılığı ─────────────────────────────────────── //
const STATE_FILE = path.join(app.getPath('userData'), 'window-state.json');
// Backend hata günlüğü — paketlenmiş üründe (windowsHide) backend stdout/stderr görünmez bir
// console'a gider; bu dosya "Backend başlamadı" durumunda gerçek Python traceback'ini kalıcı saklar.
const BACKEND_LOG = path.join(app.getPath('userData'), 'backend-error.log');
// Açılış aşama günlüğü — "açılmadı" şikâyeti geldiğinde HANGİ aşamada takıldığını söyler.
// BACKEND_LOG'dan ayrı ve EKLEMELİ: kullanıcı kapatıp tekrar açtığında başarısız açılışın
// kaydı silinmesin (backend log'u her açılışta sıfırlanıyor — o yüzden oraya yazmak işe yaramaz).
const ACILIS_LOG = path.join(app.getPath('userData'), 'acilis.log');
// Süreç bekçisinin olay günlüğü (bekçi kendi yazar, 256 KB tavanlı) — yalnız YUKI_BEKCI=1 iken.
const BEKCI_LOG = path.join(app.getPath('userData'), 'bekci.log');
const ACILIS_LOG_TAVANI = 256 * 1024;
let _acilisT0 = Date.now();

function acilisKaydi(mesaj) {
  const satir = `[${new Date().toISOString()}] +${String(Date.now() - _acilisT0).padStart(6)}ms  ${mesaj}\n`;
  console.error('[açılış]', mesaj);
  try {
    if (fs.existsSync(ACILIS_LOG) && fs.statSync(ACILIS_LOG).size > ACILIS_LOG_TAVANI) {
      const tut = fs.readFileSync(ACILIS_LOG, 'utf8').split('\n').slice(-400).join('\n');
      fs.writeFileSync(ACILIS_LOG, tut, 'utf8');
    }
    fs.appendFileSync(ACILIS_LOG, satir, 'utf8');
  } catch (_) { /* günlük yazılamaması açılışı bozmasın */ }
}

/**
 * Güncelleme günlüğü — `main.js`'in yazdığı dosyanın aynısı, EKLEMELİ.
 *
 * Geri alma eskiden **sessizdi**: müşteride bir güncelleme üç kez patlayıp
 * atılıyordu ve bunun hiçbir izi kalmıyordu. "Güncelledim ama değişmedi"
 * şikâyetinin tek okunabilir kaydı burası.
 */
const GUNCELLEME_LOG = path.join(app.getPath('userData'), 'guncelleme.log');
const GUNCELLEME_LOG_TAVANI = 128 * 1024;

function guncellemeKaydi(mesaj) {
  console.error('[delta]', mesaj);
  try {
    if (fs.existsSync(GUNCELLEME_LOG) && fs.statSync(GUNCELLEME_LOG).size > GUNCELLEME_LOG_TAVANI) {
      const tut = fs.readFileSync(GUNCELLEME_LOG, 'utf8').split('\n').slice(-300).join('\n');
      fs.writeFileSync(GUNCELLEME_LOG, tut, 'utf8');
    }
    fs.appendFileSync(GUNCELLEME_LOG, `[${new Date().toISOString()}] ${mesaj}\n`, 'utf8');
  } catch (_) { /* günlük yazılamaması güncellemeyi bozmasın */ }
}

/** Bir sözü süreyle sınırla — takılan API açılışı sonsuza kadar kilitlemesin. */
function sureSiniri(soz, ms, etiket) {
  return Promise.race([
    Promise.resolve(soz).then((v) => ({ ok: true, v })),
    new Promise((r) => setTimeout(() => r({ ok: false, etiket }), ms)),
  ]);
}
const DEFAULT_STATE = {
  x: undefined,
  y: undefined,
  width: 1100,
  height: 760,
  alwaysOnTop: false,
  mod: 'tam',
  kose: 'sag-tam',
};
const YAPISMA_KOSELERI = new Set(['sol-ust', 'sag-ust', 'sol-tam', 'sag-tam', 'sol-alt', 'sag-alt']);

/* setBounds sonucunun doğrulanması (bkz. moduUygula sonu).
 * Tolerans 8px: bazı pencere yöneticileri kenarlığı/gölgeyi hesaba katıp birkaç piksel
 * kaydırır — bu başarısızlık değildir. Wayland'deki arıza ise yüzlerce piksellik sapma
 * üretiyor (ölçüldü: istenen 420x1003, gerçek 1900x1015). */
const KONUM_TOLERANS_PX = 8;
const KONUM_DOGRULAMA_MS = 300;
let pencereDurumu = null;

function loadWindowState() {
  try {
    const raw = fs.readFileSync(STATE_FILE, 'utf8');
    const parsed = JSON.parse(raw);
    const kayit = parsed && typeof parsed === 'object' && !Array.isArray(parsed) ? parsed : {};
    const state = { ...DEFAULT_STATE, ...kayit };
    if (!Object.hasOwn(MODLAR, state.mod)) state.mod = DEFAULT_STATE.mod;
    if (!YAPISMA_KOSELERI.has(state.kose)) state.kose = DEFAULT_STATE.kose;
    if (typeof state.alwaysOnTop !== 'boolean') state.alwaysOnTop = DEFAULT_STATE.alwaysOnTop;
    if (!Number.isFinite(state.width)) state.width = DEFAULT_STATE.width;
    if (!Number.isFinite(state.height)) state.height = DEFAULT_STATE.height;
    return state;
  } catch {
    return { ...DEFAULT_STATE };
  }
}

function saveWindowState() {
  if (!win) return;
  try {
    const b = win.getBounds();
    const state = {
      ...(pencereDurumu || DEFAULT_STATE),
      alwaysOnTop: win.isAlwaysOnTop(),
    };
    // Panel/mini sınırları Tam modun serbest konum hafızasını ezmesin.
    if (state.mod === 'tam') {
      Object.assign(state, { x: b.x, y: b.y, width: b.width, height: b.height });
    }
    pencereDurumu = state;
    fs.writeFileSync(STATE_FILE, JSON.stringify(pencereDurumu), 'utf8');
  } catch (e) {
    console.error('[window-state] kaydetme hatası:', e.message);
  }
}

function tamModKaydi() {
  if (!pencereDurumu) return null;
  const { x, y, width, height } = pencereDurumu;
  return { x, y, width, height };
}

/** Mod hesaplama → görünür alan koruması → Electron penceresi → renderer → kalıcılık. */
function moduUygula(pencere, mod, kose) {
  if (!pencere || pencere.isDestroyed()) return;
  if (!Object.hasOwn(MODLAR, mod)) throw new Error(_et('kabuk.bilinmeyen-mod', { mod }));
  if (!YAPISMA_KOSELERI.has(kose)) throw new Error(_et('kabuk.bilinmeyen-kose', { kose }));

  /* 🔴 ÖNDEN KAPI (2026-09-06) — aşağıdaki 300 ms'lik sapma ölçümü YETMİYOR.
   * Ölçüldü: `setBounds` yalnız KONUMU değiştiriyorsa (boyut aynı kalıyorsa)
   * Wayland'de `getBounds()` istenen değeri geri veriyor → sapma 0 → başarısızlık
   * SESSİZCE geçiyor. Yani "sol köşeden sağ köşeye" gibi eşit boyutlu geçişlerde
   * kullanıcı hiçbir şey yapmayan bir düğmeye basıyordu (geliştiricinin şikâyeti).
   * Sapma eşiğini sıkılaştırmak çözmez: `getBounds()` orada güvenilir bir kaynak
   * değil. Doğru hamle, mümkün olmadığını BİLDİĞİMİZ yerde denememek ve söylemek. */
  const yetenek = konumlandirmaYetenegi({
    zorlananOzone: app.commandLine.getSwitchValue('ozone-platform'),
  });
  if (!yetenek.destekli && mod !== 'tam') {
    console.log('[pencere-modu] konumlandırma desteklenmiyor —', yetenek.arkaUc);
    pencere.webContents.send('pencere-modu-uygulanamadi', {
      mod, kose, istenen: null, gercek: null, sapma: null,
      sebep: yetenek.sebep, kural: yetenek.kural, arkaUc: yetenek.arkaUc,
    });
    return;   // pencereDurumu'na YAZMIYORUZ: olmayan bir mod kaydedilmemeli
  }

  // Tam'dan ayrılırken kullanıcının serbest konumunu panel sınırlarından önce al.
  if (pencereDurumu && pencereDurumu.mod === 'tam' && mod !== 'tam') {
    Object.assign(pencereDurumu, pencere.getBounds());
  }

  const alan = screen.getDisplayMatching(pencere.getBounds()).workArea;
  const ham = modBoyutu(mod, kose, alan, mod === 'tam' ? tamModKaydi() : null);
  const guvenli = gorunurAlanaSigdir(
    ham,
    screen.getAllDisplays().map((d) => d.workArea),
  );
  const mevcut = pencere.getBounds();
  const bounds = {
    x: Number.isFinite(guvenli.x)
      ? guvenli.x
      : Math.round(alan.x + (alan.width - guvenli.width) / 2),
    y: Number.isFinite(guvenli.y)
      ? guvenli.y
      : Math.round(alan.y + (alan.height - guvenli.height) / 2),
    width: guvenli.width || mevcut.width,
    height: guvenli.height || mevcut.height,
  };

  pencereDurumu = { ...(pencereDurumu || DEFAULT_STATE), mod, kose };
  pencere.setBounds(bounds);
  if (ham.ustte) pencere.setAlwaysOnTop(true, 'normal');
  else pencere.setAlwaysOnTop(false);
  pencere.webContents.send('pencere-modu', { mod, kose });
  saveWindowState();

  /* 🔴 setBounds SESSİZCE yok sayılabilir. Ölçüldü (2026-08-21, gerçek Electron 29 +
   * Hyprland/Wayland): panel ve mini modlarının hiçbirinde pencere kıpırdamadı —
   * IPC ulaşıyor, setAlwaysOnTop etkili oluyor, window-state.json güncelleniyor, ama
   * pencere 1900x1015 sabit kalıyor. Sebep protokol düzeyinde: Wayland'de bir uygulama
   * kendi pencere konumunu belirleyemez. Elenen hipotezler: tiling (floating'de de
   * kıpırdamadı) ve fullscreen (fullscreen=0).
   *
   * Platformu TAHMİN ETMİYORUZ, sonucu ÖLÇÜYORUZ — "ilan edilen yetenek ≠ ölçülen
   * yetenek" (BLOCKED_FREE dersi). Windows/macOS'ta çalışıyorsa bu dal hiç tetiklenmez.
   *
   * Kullanıcı bunu görmezse arayüz "oldu" der (yazı küçülür, cam gelir) ama pencere
   * durur — C4 kapısı: sessiz başarısızlık YASAK. */
  if (mod !== 'tam') {
    setTimeout(() => {
      if (!pencere || pencere.isDestroyed()) return;
      const sonra = pencere.getBounds();
      const sapma = Math.max(
        Math.abs(sonra.x - bounds.x),
        Math.abs(sonra.y - bounds.y),
        Math.abs(sonra.width - bounds.width),
        Math.abs(sonra.height - bounds.height),
      );
      if (sapma > KONUM_TOLERANS_PX) {
        /* Teşhis izi: "panel çalışmıyor" şikâyetinde ilk bakılacak satır bu.
           Sessiz kalırsa kusur yeniden ölçülmek zorunda kalınır. */
        console.log('[pencere-modu] uygulanamadı — istenen=', JSON.stringify(bounds),
          'gerçek=', JSON.stringify(sonra), 'sapma=', sapma);
        pencere.webContents.send('pencere-modu-uygulanamadi', {
          mod, kose, istenen: bounds, gercek: sonra, sapma,
        });
      }
    }, KONUM_DOGRULAMA_MS);
  }
}

function getBackendDir() {
  // Paketlenmiş (AppImage): backend extraResources ile resources/backend'e konur.
  if (app.isPackaged) {
    return path.join(process.resourcesPath, 'backend');
  }
  // Geliştirme: electron/../backend
  return path.join(PAKET_KOK, '..', 'backend');
}

function getFrontendDir() {
  return app.isPackaged
    ? path.join(process.resourcesPath, 'frontend')
    : path.join(PAKET_KOK, '..', 'frontend');
}

/**
 * Ayar şablonunu kullanıcının YAZILABİLİR dizinine bırakır.
 *
 * Depo yarısı `bfe2b5e` ile kapanmıştı ama paket yarısı açıktı: 142 satırlık
 * gerçek şablon `extraResources`'ta hiç yoktu, yani AppImage/zip kuran müşteri
 * onu **hiçbir yerde göremiyordu** — FACE_* gibi ayarların varlığından haberi
 * bile olmuyordu.
 *
 * ⚠️ Çözüm builder filtresini gevşetmek DEĞİL (ölçüldü 09-08): `!.env.*`
 * filtresi `../backend`'e uygulanıyor, kökteki gerçek şablon zaten o kapsamda
 * değil. Filtreyi açmak yalnız `backend/.env.example`'ı (488 baytlık yol tarifi
 * notu) paketler — işe yaramaz, üstelik geliştiricinin gerçek `.env`'ini paketleme
 * riskini davet eder.
 *
 * 🔴 Düz kopya da yanlış olurdu: şablonun kendi başlığı `cp .env.example .env`
 * diyor. Bu GELİŞTİRİCİ için doğru (kökte `.env` yok, fallback okunur), müşteri
 * için YIKICI — `DATA_DIR/.env`'i anahtar sihirbazı yazıyor ve üstüne kopyalayan
 * müşteri kendi API anahtarını siler. O yüzden gövdenin başına müşteri bağlamına
 * ait bir başlık ekleniyor; gövdenin kendisi depodaki dosyayla birebir.
 */
function envSablonunuYerlestir() {
  const dataDir = app.getPath('userData');
  const hedef = path.join(dataDir, '.env.example');
  // Varsa ASLA ezme: kullanıcı üzerine not almış olabilir ve bu dosya onun.
  if (fs.existsSync(hedef)) return;

  const kaynakYol = app.isPackaged
    ? path.join(process.resourcesPath, '.env.example')
    : path.join(PAKET_KOK, '..', '.env.example');

  // 🌐 İKİ DİLLİ: dosya bir kez, ilk açılışta yazılır ve bir daha ASLA ezilmez
  // (yukarıdaki kural). O anda dil çoğu kurulumda henüz seçilmemiştir (varsayılan tr) —
  // tek dilde yazılsaydı İngilizce müşteri bu uyarıyı hiç okuyamazdı. Gövde (depodaki
  // şablon) Türkçe; bu başlık müşteriyi koruyan kısım, o yüzden iki dilde.
  const baslik = [
    '# ═══════════════════════════════════════════════════════════',
    "# ⚠️  BU DOSYA BİR ÖRNEKTİR — Yuki bunu OKUMAZ.",
    "#     Yuki'nin okuduğu dosya aynı klasördeki  .env  dosyasıdır.",
    '#',
    "# ⛔ Bu dosyayı kopyalayıp .env'in ÜSTÜNE YAZMA — anahtar sihirbazının",
    "#    (⚙ AYAR › 🔑 ANAHTAR) yazdığı API anahtarın silinir.",
    '#',
    "# ✅ Bir ayarı elle eklemek istersen: aşağıdan İLGİLİ SATIRI kopyalayıp",
    "#    .env dosyasının SONUNA yapıştır ve Yuki'yi yeniden başlat.",
    '#',
    '# ───────────────────────────────────────────────────────────',
    '# ⚠️  THIS FILE IS AN EXAMPLE — Yuki does NOT read it.',
    "#     Yuki reads the  .env  file in this same folder.",
    '#',
    "# ⛔ Do NOT copy this file OVER .env — the API key written by the key",
    '#    wizard (⚙ SETTINGS › 🔑 KEY) would be erased.',
    '#',
    '# ✅ To add a setting by hand: copy the RELEVANT LINE from below,',
    "#    paste it at the END of .env and restart Yuki.",
    '#',
    `# Bu klasör / This folder: ${dataDir}`,
    '# ═══════════════════════════════════════════════════════════',
    '',
    '',
  ].join('\n');

  try {
    const govde = fs.readFileSync(kaynakYol, 'utf8');
    fs.writeFileSync(hedef, baslik + govde, 'utf8');
    acilisKaydi(`ayar şablonu yerleştirildi: ${hedef}`);
  } catch (e) {
    // Şablonun yokluğu açılışı ENGELLEMEZ — bu bir kolaylık, bağımlılık değil.
    acilisKaydi(`ayar şablonu yerleştirilemedi (${e.message})`);
  }
}

/** Paketin kabuk parmak izi — delta yükün bu kuruluma uyup uymadığını belirler. */
function getShellId() {
  try {
    return fs.readFileSync(path.join(PAKET_KOK, 'shell-id.txt'), 'utf8').trim();
  } catch (_) {
    return null;   // eski paket → delta güncelleme kapalı, tam indirmeye düşer
  }
}

/**
 * Paketlenmiş medyanın kimliği (2026-08-08).
 *
 * `shell-id.txt`in kardeşi. Bununla "bendeki görseller güncel mi" sorusu
 * 33 MB'ı yeniden hash'lemeden cevaplanır. Yoksa `null` → medya kimliği
 * bilinmiyor demektir; güncelleyici o durumda medyayı ihtiyatla İNDİRİR
 * (yanlış tarafa düşmek, eski görselle kalmaktan iyidir).
 */
function getPackagedMediaId() {
  try {
    return fs.readFileSync(path.join(PAKET_KOK, 'media-id.txt'), 'utf8').trim();
  } catch (_) {
    return null;
  }
}

/**
 * Delta güncelleme overlay'i — uygulanmışsa app kodu oradan çalışır.
 *
 * Ağır kısım (Python runtime, Electron, 121 MiB medya) HER ZAMAN paketten gelir;
 * overlay yalnız `backend/app` + `frontend` (assets hariç) taşır (~1,2 MiB).
 *
 * Geri alma: backend ayağa kalkamazsa sayaç artar; MAX_FAIL'de overlay atılıp
 * paketlenmiş sürüme dönülür — bozuk bir güncelleme ürünü tuğlalaştırmamalı.
 */
function getDeltaUpdater() {
  if (deltaUpdater) return deltaUpdater;
  const { DeltaUpdater } = require('./delta-updater');
  deltaUpdater = new DeltaUpdater({
    userDataDir: app.getPath('userData'),
    shellId: getShellId(),
    currentVersion: app.getVersion(),
    // Overlay yalnız `app/` taşır; `mcp_servers.json`, `skills/` gibi kardeşler
    // buradan aynalanır (yoksa o özellikler güncelleme sonrası SESSİZCE kapanır).
    packagedBackendDir: getBackendDir(),
    // Medya artık güncellenebiliyor; paketinki referans nokta (bkz. media-id.txt)
    packagedMediaId: getPackagedMediaId(),
    // Günlük önyükleyicininkiyle AYNI dosyaya gider — güncellemenin hikâyesi
    // (indirildi → uygulandı → açıldı / geri alındı) tek yerde okunsun.
    gunluk: guncellemeKaydi,
  });
  return deltaUpdater;
}

/** Kullanılacak app-kodu kökü: {overlayDir|null, version} */
function resolveAppOverlay() {
  // 🔴 KARAR BURADA VERİLMEZ — `main.js` (ASAR önyükleyicisi) verdi.
  // Eskiden sağlık/geri-alma kararı buradaydı; ama bu dosya artık overlay'den de
  // yüklenebiliyor, yani kendi bozukluğuna kendisi karar veremez. Aynı soruya iki
  // yerde cevap üretmek `dfdd47a`'nın ta kendisiydi ("hangi sürümdeyim" iki kaynaktan
  // besleniyordu ve ayrıştıkları yerde kimse bakmıyordu). Tek karar noktası: önyükleyici.
  if (KATMAN.overlayKok) return { dir: KATMAN.overlayKok, version: KATMAN.overlaySurum };
  return { dir: null, version: app.getVersion() };
}

// İndir-gerektiğinde model yöneticisini kur. writableDir = userData/models-cache (indirme hedefi),
// bundledDir = resources/backend/models-cache (yalnız TAM offline build'de dolu).
function initModelManager() {
  const BACKEND_DIR = getBackendDir();
  const bundledDir = path.join(BACKEND_DIR, 'models-cache');
  modelManager = new ModelManager({
    // 🔴 `kaynak()` ŞART, `PAKET_KOK` DEĞİL (2026-09-05): manifest indir-gerektiğinde
    // yüklerin kayıt defteridir ve yeni yük eklendikçe DEĞİŞİR. Paket kökünden
    // okunursa delta ile gelen güncel manifest hiç kullanılmaz → yeni yük
    // "Bilinmeyen model" olur. `kaynak()` overlay'de varsa oradan alır.
    manifestPath: kaynak('models-manifest.json'),
    writableDir: path.join(app.getPath('userData'), 'models-cache'),
    bundledDir: fs.existsSync(bundledDir) ? bundledDir : null,
  });
  return modelManager;
}

function isBackendRunning() {
  return new Promise((resolve) => {
    http.get(BACKEND_URL + '/health', (res) => {
      resolve(res.statusCode === 200);
    }).on('error', () => resolve(false));
  });
}

async function startBackend() {
  // Bekleme ölçütünün başlangıç noktası. Süreci biz başlatmasak bile (aşağıdaki
  // "sağ kalmış motor" dalı) taban buradan kurulur — yoksa `sonBackendCiktisi` 0
  // kalır ve durgunluk epoch'tan hesaplanıp anlamsız çıkar.
  sonBackendCiktisi = Date.now();
  backendCikisi = null;

  // Ayar şablonunu kullanıcının klasörüne bırak. Motoru BEKLETMEZ:
  // tek küçük dosya, hatası yutuluyor. Burada çağrılıyor çünkü aşağıda
  // `YUKI_DATA_DIR` olarak verilen dizinin ta kendisine yazıyor — ikisi
  // ayrışırsa şablon müşterinin bakacağı yerde olmaz.
  envSablonunuYerlestir();

  // 8791'de zaten biri cevap veriyor. Tek-örnek kilidi ikinci bir Yuki'yi engellediğine
  // göre bu, önceki açılıştan SAĞ KALMIŞ bir motordur (pencere Görev Yöneticisi'nden
  // kapatılmış, python arkada kalmış olur). Yeniden kullanmak açılışı anında bitirir —
  // "bazen hemen geliyor" dalgalanmasının kaynağı da budur. Sessiz geçme: delta
  // güncellemeden sonra bu artık ESKİ KODU çalıştırıyor olabilir.
  // Bekçi açıkken bu dal ATLANIR: bekçi portun sahibine bakıp öksüz kalmış eski motorumuzu
  // durdurur ve güncel kodu başlatır (delik 3); başkasınınsa dokunmaz, 71 ile çıkar → pencere.
  // Windows'ta da (FAZ 6 ④) — bekci.js::portuBekciDenetler, eski ikiliyle gitmez.
  let bekci = bekciMod.bekciYolu({ env: process.env, platform: process.platform, resourcesPath: process.resourcesPath });
  // Bekçi ikilisi 8791'e sabit; başka porttaki motoru denetleyemez → o durumda bekçisiz.
  if (bekci.kullan && BACKEND_PORT !== motorPortu.VARSAYILAN_PORT) {
    bekci = { kullan: false, neden: `port ${BACKEND_PORT} != ${motorPortu.VARSAYILAN_PORT}` };
  }
  acilisKaydi(`motor portu ${BACKEND_PORT} (${MOTOR_PORT_SECIMI.neden})`);
  if (bekci.neden) acilisKaydi(`UYARI: süreç bekçisi kapalı, eski yola düşülüyor — ${bekci.neden}`);
  const bekciPortuDenetler = bekciMod.portuBekciDenetler(bekci);
  if (!bekciPortuDenetler && await isBackendRunning()) {
    acilisKaydi(`UYARI: ${BACKEND_PORT} zaten dolu — önceki açılıştan kalan motor yeniden kullanılıyor `
      + '(kod sürümü güncel olmayabilir)');
    // O motor önceki pencerenin anahtarını taşıyor — dosyadan al, yoksa arayüz her istekte 401 alır.
    OTURUM_ANAHTARI = oturumAnahtari.kayitliAnahtar({ fs, path, dizin: app.getPath('userData') });
    if (!OTURUM_ANAHTARI) acilisKaydi('UYARI: sağ kalan motorun oturum anahtarı bulunamadı');
    return;
  }
  OTURUM_ANAHTARI = oturumAnahtari.yeniAnahtar({
    fs, path, crypto: require('crypto'), dizin: app.getPath('userData'),
  });
  acilisKaydi('motor başlatılıyor');

  const BACKEND_DIR = getBackendDir();
  // Taşınabilir standalone Python (pybundle) — venv yerine (torch'suz lean P1 runtime).
  const isWin = process.platform === 'win32';
  // Windows bundle'ı ayrı dizin (pybundle-win/python.exe); Linux/mac pybundle/bin/python3.
  // İki bundle backend/ altında yan yana durur; her platform build'i diğerini hariç tutar.
  const python = isWin
    ? path.join(BACKEND_DIR, 'pybundle-win', 'python.exe')
    : path.join(BACKEND_DIR, 'pybundle', 'bin', 'python3');

  // Whisper modeli hangi dizinde? İndir-gerektiğinde: indirilmişse userData/models-cache,
  // tam offline build'de bundled, hiçbiri yoksa userData (indirme hedefi — model gelene kadar
  // backend STT'yi graceful-degrade eder). effectiveDir tek noktadan çözer, iki SKU tek kod.
  if (!modelManager) initModelManager();
  const hfHome = modelManager.effectiveDir('whisper-small');
  // Embedding modeli (Ultra semantik hafıza) — aynı indir-gerektiğinde mantığı.
  // Yoksa backend hafızayı graceful-degrade eder (lite hafıza devrede kalır).
  const embedDir = path.join(modelManager.effectiveDir('embedding-onnx'), 'embedding-onnx');
  // İndirilmiş Python paket ağaçları (yüz tanıma vb.) — backend sys.path'in SONUNA
  // ekler. Hiç kurulu yoksa boş string geçer ve backend hiçbir şey bağlamaz;
  // özellik "kütüphane inmemiş" diye DÜRÜST bildirir (hata koduyla değil).
  const pydeps = modelManager.pydepsDirs().join(path.delimiter);

  // ── Delta overlay ─────────────────────────────────────────────────────────
  // Overlay varsa app kodu oradan yüklenmeli. Yalnız PYTHONPATH vermek YETMEZ:
  // `python run.py` çalıştırıldığında `sys.path[0]` script'in dizini olur ve
  // PYTHONPATH'ten ÖNCE gelir → paketlenmiş `app/` kazanır. Bu yüzden küçük bir
  // `-c` önyükleyici ile overlay `sys.path`'in başına konuyor.
  // cwd BİLEREK paketlenmiş dizinde bırakılıyor: `modes.json`, `skills/`,
  // `mcp_servers.json` gibi kardeş dosyalar yüke girmiyor, yerlerinde bulunmalı.
  const overlay = resolveAppOverlay();
  const overlayBackend = overlay.dir ? path.join(overlay.dir, 'backend') : null;
  const overlayFrontend = overlay.dir ? path.join(overlay.dir, 'frontend') : null;
  // İndirilmiş medya katmanı (varsa) — overlay'den ayrı yaşar, ayrı sorulur.
  let medyaKok = null;
  try { medyaKok = getDeltaUpdater().medyaKoku(); } catch (_) { medyaKok = null; }
  if (medyaKok) console.log(`[delta] medya katmanı etkin → ${medyaKok}`);
  if (overlayBackend) {
    console.log(`[delta] overlay etkin → v${overlay.version} (${overlayBackend})`);
    getDeltaUpdater().denemeIsaretle();   // sağlıklı yanıt gelince sıfırlanır
  }
  const bootstrap = [
    'import os,sys,runpy',
    'ov=os.environ.get("YUKI_APP_OVERLAY")',
    'if ov: sys.path.insert(0, ov)',
    'runpy.run_path("run.py", run_name="__main__")',
  ].join('\n');
  const pyArgs = overlayBackend ? ['-c', bootstrap] : ['run.py'];

  // Bekleme ölçütü "motor ilerliyor mu"ya bağlı (bkz. motor-bekle.js) → süreç hakkındaki
  // iki gerçeği burada tutuyoruz: en son ne zaman çıktı üretti, ve öldü mü.
  sonBackendCiktisi = Date.now();
  backendCikisi = null;

  // YUKI_BEKCI=1: motor `yuki-bekci` altında başlar. Bekçi YUKI_EBEVEYN_PID'i kendi PID'iyle ezer
  // (Python ebeveyn bekçisinin sözleşmesi) ve YUKI_OTURUM_ANAHTARI'nı Windows'taki kibar kapanış
  // isteğinde çerez olarak kullanır. Bayrak kapalıysa çağrı birebir eskisi.
  bekciKullanildi = bekci.kullan;
  bekciArizasi = null;
  const baslat = bekci.kullan
    ? bekciMod.sarmala(bekci.yol, python, pyArgs, BEKCI_LOG)
    : { komut: python, args: pyArgs };
  if (bekci.kullan) acilisKaydi(`motor süreç bekçisi altında başlıyor (${bekci.yol})`);

  backend = spawn(baslat.komut, baslat.args, {
    cwd: BACKEND_DIR,
    env: {
      ...process.env,
      ...(overlayBackend ? {
        YUKI_APP_OVERLAY: overlayBackend,
        // Overlay'de `frontend/assets` YOK (121 MiB, yüke girmiyor) → backend
        // statik sunumu bulamadığını paketlenmiş dizinden versin.
        YUKI_FRONTEND_FALLBACK: getFrontendDir(),
      } : {}),
      // Medya katmanı — overlay'den BAĞIMSIZ verilir (2026-08-08).
      // 🔴 `overlayBackend ? {...}` bloğunun içine konmamalı: medya katmanı
      // sürümsüzdür ve kod overlay'i geri alınsa bile yerinde kalır. İçeri
      // konsaydı, bir geri alma kullanıcının indirdiği görselleri de sessizce
      // fabrika hâline döndürürdü — oysa geri alınan şey KOD'du.
      ...(medyaKok ? { YUKI_MEDIA_DIR: medyaKok } : {}),
      PYTHONNOUSERSITE: '1',   // hedef makinedeki ~/.local paketleri sızmasın (izole runtime)
      // Windows'ta Python stdout/stderr'i yerel kod sayfasını (TR: cp1254) kullanır; aşağıdaki
      // tee() ise Buffer'ı UTF-8 sanıp çözer → her Türkçe harf "�" olur ve kod sayfasında
      // olmayan karakterler ("→") ham "→" diye yazılır. Müşteriden istediğimiz teşhis
      // dosyası bu yüzden okunamaz geliyordu (2026-08-03 saha raporu). İkisi birlikte şart:
      // PYTHONUTF8 dosya/argüman katmanını, PYTHONIOENCODING akış katmanını UTF-8'e sabitler.
      PYTHONUTF8: '1',
      PYTHONIOENCODING: 'utf-8',
      YUKI_RELOAD: 'false',   // paketlenmiş üründe reload kapalı (read-only mount)
      PORT: String(BACKEND_PORT),   // BACKEND_URL ile uyum (motor-portu.js seçer)
      // Motor bu pencere ölünce kendini kapatsın: detached olduğu için Electron'la
      // ölmüyor; before-quit yalnız ZARİF kapanışta koşar — SIGKILL'de ve oturum kapanışında
      // (ekran sunucusu gidince Electron çöker) motor 8791'de öksüz kalıyordu. → app/ebeveyn_bekcisi.py
      YUKI_EBEVEYN_PID: String(process.pid),
      YUKI_OTURUM_ANAHTARI: OTURUM_ANAHTARI,     // yerel motor kapısı (v0.8.1) → app/yerel_kapi.py
      // Paketli sürümde lisans env override'ı (YUKI_PACKAGE/YUKI_ENABLED_TOOLS) kapalı (v0.8.1, H6)
      // → backend/app/services/licensing/entitlements.py::_paketli_surum. Geliştirmede verilmez.
      ...(app.isPackaged ? { YUKI_PAKETLI: '1' } : {}),
      YUKI_DATA_DIR: app.getPath('userData'),   // yazılabilir dizin → .env/key/notes/todos/reminders (read-only mount fix)
      HF_HOME: hfHome,                            // whisper modeli (indirilmiş userData veya bundled)
      HUGGINGFACE_HUB_CACHE: path.join(hfHome, 'hub'),
      EMBED_ONNX_DIR: embedDir,   // semantik hafıza embedding motoru (torch yok → ONNX)
      YUKI_PYDEPS: pydeps,        // indirilen Python paket ağaçları → backend/app/pydeps.py
      // InsightFace modelini KENDİ indirdiğinde ev dizinine ($HOME/.insightface)
      // yazar; paketlenmiş üründe orası yönetilmeyen bir yer. models-cache'e
      // yönlendiriyoruz: yazılabilir, kaldırılabilir ve modellerle aynı yerde.
      INSIGHTFACE_HOME: path.join(app.getPath('userData'), 'models-cache', 'insightface'),
      EMBED_BACKEND: 'onnx',      // pakette sentence-transformers YOK, tereddütsüz ONNX
      // config.py varsayılanı 'pgvector' — üründe Postgres YOK, .env de paketlenmiyor.
      // Bu satır olmadan MEMORY_ENABLED=False kalır → semantik hafıza hiç açılmaz
      // ("DATABASE_URL ayarlanmamış — hafıza devre dışı"). Gömülü sqlite-vec tek doğru seçim.
      MEMORY_BACKEND: 'sqlite',
      HF_HUB_OFFLINE: '1',        // paketlenmiş/indirilmiş model → HF hub ağ denemesi yapmasın (offline)
      TRANSFORMERS_OFFLINE: '1',
    },
    detached: true,   // kendi süreç grubu → child süreçler de grup-kill ile temizlenir
    windowsHide: true, // Windows'ta arkada açılan konsol (cmd) penceresini gizle
  });

  // Backend stdout/stderr'i kalıcı log dosyasına yaz — paketlenmiş üründe bu çıktı görünmez bir
  // console'a gider; "Backend başlamadı" olduğunda gerçek Python traceback'i buraya düşsün.
  let logStream = null;
  try {
    logStream = fs.createWriteStream(BACKEND_LOG, { flags: 'w' });   // her açılışta temiz başla
    logStream.write(
      `=== Yuki backend log — ${new Date().toISOString()} ===\n` +
      `python  : ${python}\n` +
      (bekci.kullan ? `guard   : ${bekci.yol} (log: ${BEKCI_LOG})\n` : '') +
      `cwd     : ${BACKEND_DIR}\n` +
      `port    : ${BACKEND_PORT}\n` +
      `platform: ${process.platform} ${process.arch}\n` +
      `${'='.repeat(60)}\n`
    );
  } catch (e) {
    console.error('[backend] log dosyası açılamadı:', e.message);
  }
  const tee = (prefix) => (d) => {
    const s = d.toString();
    sonBackendCiktisi = Date.now();   // "motor ilerliyor mu" ölçütünün tek kaynağı
    console.error(prefix, s);
    if (logStream) { try { logStream.write(s); } catch (_) {} }
  };
  if (backend.stdout) backend.stdout.on('data', tee('[backend:out]'));
  if (backend.stderr) backend.stderr.on('data', tee('[backend:err]'));

  // Backend beklenmedik şekilde kapanırsa çıkış kodunu logla (native DLL/crash tanısı için kritik)
  backend.on('exit', (code, signal) => {
    const line = `\n[backend] süreç sonlandı — code=${code} signal=${signal}\n`;
    backendCikisi = { code, signal };   // ölü sürece "belki gelir" diye beklenmez
    console.error(line);
    if (logStream) { try { logStream.write(line); logStream.end(); } catch (_) {} }
    // Bekçi vazgeçtiyse (70 çökme döngüsü · 71 port başkasında · 127 başlatamadı) kullanıcı bilsin.
    // Açılışta bunu motor-bekle penceresi gösterir (bekciArizasi'ni okur); burada yalnız motor
    // hazır olduktan SONRAKİ duruş — o an ekranda başka bir şey yok, arayüz sessizce ölürdü.
    const anahtar = bekciKullanildi ? bekciMod.cikisAnahtari(code) : null;
    if (anahtar) {
      bekciArizasi = anahtar;
      acilisKaydi(`süreç bekçisi vazgeçti — kod ${code}`);
      if (motorHazir && !uygulamaKapaniyor) bekciArizaPenceresi(anahtar);
    }
  });

  // spawn başarısız olursa (pybundle yok / python bulunamadı) 'error' yayılır — yakalanmazsa main crash eder
  backend.on('error', (err) => {
    console.error('[backend] başlatılamadı:', err.message);
    backendCikisi = { hata: err.message };
    if (logStream) { try { logStream.write(`\n[backend] spawn error: ${err.message}\n`); } catch (_) {} }
    dialog.showErrorBox(_et('kabuk.backend-hatasi'),
      _et('kabuk.backend-hatasi-detay', { hata: err.message, python, log: BACKEND_LOG }));
  });
}

/** Son satırlar — arıza pencerelerinde günlük kesiti. */
function gunlukKuyrugu(dosya, satir = 15) {
  try {
    return fs.readFileSync(dosya, 'utf8').split('\n').slice(-satir).join('\n').trim() || _et('kabuk.log-bos');
  } catch (_) {
    return _et('kabuk.log-okunamadi');
  }
}

// Motor hazır olduktan sonra bekçi vazgeçti → kullanıcıya pencere (geliştirici kararı 10-08: yalnız log yetmez).
async function bekciArizaPenceresi(anahtar) {
  const dugmeler = ['yeniden', 'log', 'tamam'];
  const etiket = { yeniden: 'kabuk.bekci-yeniden-baslat', log: 'kabuk.log-klasoru-ac', tamam: 'kabuk.tamam' };
  let secim = 'tamam';
  try {
    const { response } = await dialog.showMessageBox(win && !win.isDestroyed() ? win : undefined, {
      type: 'error',
      title: _et('kabuk.bekci-baslik'),
      message: _et('kabuk.bekci-baslik'),
      detail: _et('kabuk.bekci-detay', {
        aciklama: _et(anahtar), bekciGunlugu: gunlukKuyrugu(BEKCI_LOG, 8), motorGunlugu: gunlukKuyrugu(BACKEND_LOG, 12),
      }),
      buttons: dugmeler.map((d) => _et(etiket[d])),
      defaultId: 0,
      cancelId: dugmeler.length - 1,
      noLink: true,
    });
    secim = dugmeler[response] || 'tamam';
  } catch (_) { /* pencere açılamadıysa log zaten yazıldı */ }
  acilisKaydi(`bekçi arıza penceresi — seçim: ${secim}`);
  if (secim === 'log') {
    try { require('electron').shell.showItemInFolder(BEKCI_LOG); } catch (_) {}
  } else if (secim === 'yeniden') {
    app.relaunch();
    app.quit();
  }
}

/**
 * Windows'ta motoru önce kibarca kapat. SIGTERM yok; motora `POST /api/motor/kapan`,
 * motorun kendi zorla süresi + pay (bekci.js::KAPANIS_BEKLE_MS, 18 sn) içinde çıkmazsa çağıran
 * `stopBackend()` ile zorla (taskkill /T /F). Bekçi açıkken de aynı:
 * motor 0 koduyla çıkar, bekçi bunu "kendi isteğiyle" sayıp yeniden başlatmaz ve kendisi çıkar.
 */
function windowsKibarKapat() {
  const surec = backend;
  if (!surec || surec.killed || backendCikisi) return Promise.resolve('yok');
  const istekAt = () => new Promise((resolve, reject) => {
    const istek = http.request(BACKEND_URL + bekciMod.KAPANIS_YOLU, {
      method: 'POST',
      headers: {
        'Content-Length': 0,
        ...(OTURUM_ANAHTARI ? { Cookie: `${oturumAnahtari.CEREZ_ADI}=${OTURUM_ANAHTARI}` } : {}),
      },
      timeout: 3000,
    }, (res) => { res.resume(); resolve(res.statusCode); });
    istek.on('timeout', () => istek.destroy(new Error('timeout')));
    istek.on('error', reject);
    istek.end();
  });
  const cikisBekle = (ms) => new Promise((resolve) => {
    if (backendCikisi) return resolve(true);
    const t = setTimeout(() => resolve(false), ms);
    surec.once('exit', () => { clearTimeout(t); resolve(true); });
  });
  return bekciMod.kibarKapat({ istekAt, cikisBekle, log: (m) => acilisKaydi(`kapanış: ${m}`) });
}

// Backend'i (ve uvicorn reload child süreçlerini) güvenle durdur.
function stopBackend() {
  if (!backend || backend.killed) return;
  const pid = backend.pid;
  backend = null;
  if (process.platform === 'win32') {
    // Windows POSIX süreç-grubu (-pid) desteklemez → taskkill /T ile ağacı (child uvicorn dahil) kapat
    try { require('child_process').execFileSync('taskkill', ['/pid', String(pid), '/T', '/F']); } catch (_) {}
    return;
  }
  try {
    // detached spawn → negatif PID tüm süreç GRUBUNU öldürür (reload worker dahil)
    process.kill(-pid, 'SIGTERM');
  } catch (_) {
    try { process.kill(pid, 'SIGTERM'); } catch (_) {}
  }
}

/**
 * Motoru bekle — kural + `/health` yoklaması `motor-bekle.js`'te (orada test edilebiliyor),
 * süreç gerçekleri (son çıktı zamanı, süreç öldü mü) burada.
 * (Eski hâli: `waitForBackend(retries = 120)` = sabit 60 sn tavan. R7'de sahada düştü.)
 */
const saglikSor = saglikSorucu(BACKEND_URL);

function motoruBekle(ilerleme) {
  return motorBekle({
    saglikSor,
    sonCikti: () => sonBackendCiktisi,
    surecDurumu: () => backendCikisi,
    ilerleme,
  });
}

/**
 * Güncelleme GERÇEKTEN devreye girdi mi?
 *
 * 🔴 Eski ölçüt "backend ayağa kalktı"ydı — ama backend, overlay hiç
 * yüklenmemişken de ayağa kalkar. Yani sessizce devreye girmeyen bir
 * güncelleme "başarılı" damgası yiyor, geri alma hiç tetiklenmiyordu.
 * Doğru ölçüt: çalışan motorun BİLDİRDİĞİ sürüm, beklenen sürüme eşit mi.
 *
 * Eksik `version` alanına (eski backend) hoşgörülü davranılır — orada
 * katı olmak çalışan bir kurulumu geri aldırırdı; ama sessiz kalmaz.
 */
function guncellemeBasarisiniIsle(bildirilen) {
  const k = surumKimligi();
  const u = getDeltaUpdater();
  if (!bildirilen) {
    guncellemeKaydi(`açılış OK — motor sürüm bildirmedi (eski backend?), beklenen v${k.etkin}`);
    u.basariliIsaretle();
    return;
  }
  if (bildirilen === k.etkin) {
    if (k.overlay) guncellemeKaydi(`açılış OK — v${k.etkin} çalışıyor (${k.kaynak})`);
    u.basariliIsaretle();
    return;
  }
  guncellemeKaydi(
    `UYUŞMAZLIK: motor v${bildirilen} bildiriyor, beklenen v${k.etkin} (${k.kaynak}) — `
    + 'başarı işaretlenmedi, üst üste tekrarlarsa geri alınacak'
  );
}

async function createWindow() {
  pencereDurumu = gorunurAlanaSigdir(
    loadWindowState(),
    screen.getAllDisplays().map((d) => d.workArea),
  );
  const state = pencereDurumu;
  acilisKaydi(`pencere kuruluyor — ${state.width}x${state.height} @ `
    + `${state.x === undefined ? 'ortalanmış' : state.x + ',' + state.y}`);

  win = new BrowserWindow({
    x: state.x,
    y: state.y,
    width: state.width,
    height: state.height,
    // Pencere BOŞ gösterilmez: içeriği (açılış ekranı) gelene kadar gizli durur.
    // Eskiden burası görünürdü ve `transparent:true` yüzünden bomboş/şeffaf açılıyordu.
    show: false,
    minWidth: 480,   // altına inince layout kesilir (responsive drawer alt sınırı)
    minHeight: 600,  // header + sohbet + input için asgari yükseklik
    title: 'Yuki',
    frame: false,
    transparent: true,
    // Electron 43+: Linux'ta çerçevesiz pencere, masaüstü CSD destekliyorsa
    // (GNOME) köşeleri yuvarlatır. 29'da yoktu; kabuk kendi kartını çiziyor ve
    // pencere modlarında (yapışık/yüzen) kenar kenara durur → kapalı tutulur.
    // Windows'a dokunulmaz: orada Win11 yuvarlatması 29'da da vardı.
    ...(process.platform === 'linux' ? { roundedCorners: false } : {}),
    alwaysOnTop: state.alwaysOnTop,
    resizable: true,
    webPreferences: {
      preload: kaynak('preload.js'),
      contextIsolation: true,
      nodeIntegration: false,
      sandbox: true,
      // <webview> yok: onu kullanan tek özellik (Komuta Paneli) 2026-11-13'te tamamen kalktı.
      // Açık bırakılırsa sayfaya gömülen konuk sitelerin güvenlik kuralları da gerekir.
      webviewTag: false,
    },
    backgroundColor: '#00000000',
  });

  // Boyut/konum değişince kaydet (debounce 500ms)
  let _saveTimer = null;
  const debouncedSave = () => {
    clearTimeout(_saveTimer);
    _saveTimer = setTimeout(saveWindowState, 500);
  };
  win.on('resize', debouncedSave);
  win.on('move', debouncedSave);
  win.on('close', saveWindowState);
  // Ana pencere gerçekten KAPANIRSA (gizlenmek değil) Mini HUD kartı da gider:
  // sohbet ve mikrofon zinciri burada yaşıyor, kart tek başına yalan söylerdi.
  // Ayrıca kart açık kalsaydı 'window-all-closed' hiç tetiklenmez, motor kapanmazdı.
  win.on('closed', () => { if (miniHud) miniHud.anaKapandi(); });
  moduUygula(win, state.mod, state.kose);

  // ── Dış bağlantılar: sistem tarayıcısı ────────────────────────────────────
  // Kural + ölçüm + tuzaklar `dis-baglanti.js` başında yazılı. Özet: işleyici
  // kurulmazsa `target="_blank"` sistem tarayıcısını açmaz, uygulamanın İÇİNDE
  // adres çubuğu olmayan bir pencere açar — BYOK rehberinin 1. adımı orada ölür.
  const disBaglanti = disBaglantiKurallari({
    openExternal: shell.openExternal,
    icOnEk: BACKEND_URL,
    kaydet: acilisKaydi,
  });
  win.webContents.setWindowOpenHandler(disBaglanti.pencereAcmaIsleyicisi);
  win.webContents.on('will-navigate', disBaglanti.gezinmeIsleyicisi);

  // ── 1) Açılış ekranını HEMEN göster ───────────────────────────────────────
  // Motorun hazırlanması kullanıcıya GÖRÜNÜR olmalı. Eskiden pencere boş ve şeffaf
  // açılıyordu: soğuk bir Windows'ta motor gelene kadar ekranda hiçbir şey yoktu,
  // "açılmadı" sanılıp kapatılıyordu — bildirilen "ilk çalıştırmada arayüz gelmiyor,
  // kapat-aç yapınca bazen geliyor" davranışının birinci nedeni budur.
  let pencereGosterildi = false;
  const pencereyiGoster = (nereden) => {
    if (pencereGosterildi || !win || win.isDestroyed()) return;
    pencereGosterildi = true;
    acilisKaydi(`pencere gösterildi (${nereden})`);
    try { win.show(); win.focus(); } catch (_) {}
  };
  const splashYaz = (metin, sari) => {
    if (!win || win.isDestroyed()) return;
    win.webContents
      .executeJavaScript(`window.splashDurum && window.splashDurum(${JSON.stringify(metin)},${!!sari})`)
      .catch(() => { /* açılış ekranından ayrıldıysak önemsiz */ });
  };

  win.webContents.once('did-finish-load', () => pencereyiGoster('açılış ekranı'));
  // Emniyet kemeri: açılış ekranı bile yüklenemezse pencere yine de görünsün.
  // Görünmez ama çalışan bir süreç kullanıcı için en kötü sonuçtur.
  setTimeout(() => pencereyiGoster('emniyet zamanlayıcısı'), 2500);
  try {
    // Açılış ekranı file:// ile yüklenir, sözlüğe erişemez → dili sorgu parametresiyle alır,
    // metin tablosunu kendisi taşır.
    await win.loadFile(kaynak('splash.html'), { query: { dil: require('./dil').aktifDil() } });
  } catch (e) {
    acilisKaydi(`açılış ekranı yüklenemedi: ${e.message}`);
    pencereyiGoster('açılış ekranı hatası');
  }

  acilisKaydi('motor bekleniyor');
  // ⚠️ Vazgeçmek KAPATMAK değildir. Eskiden tavan dolunca `app.quit()` çağrılıyordu:
  // müşterinin elindeki tek seçenek "Kapat"tı — üstelik motor gerçekten geliyorken
  // (sahada 62. saniyede geldi, tavan 60'tı). Artık her turda "beklemeye devam et"
  // sunuluyor ve döngü baştan başlıyor.
  let saglik = await motoruBekle((m) => splashYaz(m));
  while (!saglik.hazir) {
    const sn = Math.round(saglik.gecenMs / 1000);
    acilisKaydi(`motor yanıt vermedi — sebep=${saglik.sebep} geçen=${sn}sn`
      + (saglik.durgunMs != null ? ` durgun=${Math.round(saglik.durgunMs / 1000)}sn` : '')
      + (saglik.detay ? ` detay=${JSON.stringify(saglik.detay)}` : ''));

    // Gerçek nedeni göster: backend log dosyasının son satırlarını dialog'a ekle + klasörü açma seçeneği.
    let tail = '';
    try {
      const raw = fs.readFileSync(BACKEND_LOG, 'utf8');
      tail = raw.split('\n').slice(-25).join('\n').trim() || _et('kabuk.log-bos');
    } catch (_) {
      tail = _et('kabuk.log-okunamadi');
    }
    // 🔑 Metin DÜRÜST olmalı: "Backend başlamadı" bu vakada YANLIŞTI — backend başlıyordu,
    // sadece geç kalmıştı. Yanlış teşhis ürünün daha önce iki kez düştüğü sınıf
    // (ElevenLabs 401 = kota ama "anahtar geçersiz" · 429 = kota ama "lisans geçersiz").
    // **Geç kalma ≠ başlamama.**
    const oldu = saglik.sebep === 'surec-oldu';
    const baslik = oldu ? _et('kabuk.motor-kapandi') : _et('kabuk.motor-yanit-vermedi');
    const mesaj = oldu
      ? _et('kabuk.motor-sonlandi')
      : _et('kabuk.motor-sn-yanitsiz', { sn });
    const aciklama = oldu
      ? (bekciArizasi ? _et(bekciArizasi) : _et('kabuk.motor-sonlandi-aciklama'))
      : _et('kabuk.motor-yavas-aciklama');

    const { shell } = require('electron');
    // Düğmeler KİMLİKLE seçilir, etiketle değil: etiket dile göre değişir,
    // `secim === 'Kapat'` İngilizcede hiç tutmaz ve "Kapat"a basan kullanıcı beklemeye düşerdi.
    const dugmeler = oldu ? ['log', 'kapat'] : ['bekle', 'log', 'kapat'];
    const DUGME_ETIKETI = {
      bekle: 'kabuk.beklemeye-devam-et', log: 'kabuk.log-klasoru-ac', kapat: 'kabuk.kapat',
    };
    const resp = dialog.showMessageBoxSync({
      type: oldu ? 'error' : 'warning',
      title: baslik,
      message: mesaj,
      detail: _et('kabuk.motor-detay', {
        aciklama, kayitlar: tail, tamGunluk: BACKEND_LOG, acilisGunlugu: ACILIS_LOG,
      }),
      buttons: dugmeler.map((d) => _et(DUGME_ETIKETI[d])),
      defaultId: 0,
      cancelId: dugmeler.length - 1,
      noLink: true,
    });
    const secim = dugmeler[resp] || 'kapat';
    if (secim === 'log') {
      try { shell.showItemInFolder(BACKEND_LOG); } catch (_) {}
    }
    if (secim === 'kapat' || oldu) {
      // Ölü süreçte "beklemeye devam et" sunulmuyor: beklemek onu geri getirmez.
      acilisKaydi(`kullanıcı seçimi: ${secim} → çıkılıyor`);
      app.quit();
      return;
    }
    acilisKaydi(`kullanıcı seçimi: ${secim} → beklemeye devam`);
    splashYaz(_et('kabuk.beklemeye-devam-ediliyor'));
    saglik = await motoruBekle((m) => splashYaz(m));
  }
  motorHazir = true;
  acilisKaydi(`motor hazır${saglik.surum ? ` (v${saglik.surum})` : ''} — ${Math.round(saglik.gecenMs / 1000)}sn`);
  // Sayaç yalnız güncelleme GERÇEKTEN devreye girdiyse sıfırlanır.
  try { guncellemeBasarisiniIsle(saglik.surum); } catch (_) {}
  splashYaz(_et('kabuk.arayuz-hazirlaniyor'));

  // Her başlangıçta SW + HTTP cache temizle (stale önbellek önleme).
  // ⚠️ SÜRE SINIRI ŞART: bu iki çağrının zaman sınırı yoktu. Kayıtlı bir service
  // worker'la clearStorageData'nın dönmediği durumlar var; dönmezse `loadURL`'e HİÇ
  // gelinmez → pencere açık kalır, içerik asla yüklenmez, hata da verilmez. Temizlik
  // bir iyileştirmedir; uygulamayı açmaya engel olma yetkisi yoktur.
  const { session } = require('electron');
  const temizle = async (etiket, soz) => {
    const r = await sureSiniri(soz, 8000, etiket);
    if (!r.ok) acilisKaydi(`UYARI: ${etiket} 8 sn içinde dönmedi — atlandı`);
  };
  await temizle('clearStorageData',
    session.defaultSession.clearStorageData({ storages: ['serviceworkers', 'cachestorage'] }));
  await temizle('clearCache', session.defaultSession.clearCache());

  // İzinleri otomatik kabul et (yerel güvenli overlay: mic/kamera/bildirim) — loadURL'den ÖNCE kayıt
  // ki sayfa yüklenirken erken gelen mic isteği handler'sız kalmasın
  session.defaultSession.setPermissionCheckHandler(() => true);
  session.defaultSession.setPermissionRequestHandler((_wc, _permission, callback) => callback(true));

  // Oturum çerezi — loadURL'den ÖNCE. Ana pencere + Mini HUD varsayılan oturumda.
  // Dış siteler çerezi görmez: çerez yalnız 127.0.0.1'e gider, SameSite=Strict siteler arası isteği keser.
  if (OTURUM_ANAHTARI) {
    try {
      const n = await sureSiniri(oturumAnahtari.cerezleriKur({
        oturumlar: [session.defaultSession],
        url: BACKEND_URL, anahtar: OTURUM_ANAHTARI,
      }), 5000, 'cerezleriKur');
      acilisKaydi(n.ok ? `oturum çerezi kuruldu (${n.v} oturum)` : 'UYARI: oturum çerezi 5 sn içinde kurulamadı');
    } catch (e) { acilisKaydi(`HATA: oturum çerezi kurulamadı — ${e.message}`); }
  }

  // ── 2) Uygulamayı yükle — başarısızlık SESSİZ KALAMAZ ─────────────────────
  // `did-fail-load` ele alınmıyordu: motor /health'e cevap verdikten sonra ölürse ya da
  // bağlantı düşerse yükleme sessizce başarısız oluyor, kullanıcı donmuş bir pencereyle
  // kalıyordu. Artık yeniden denenir, denemeler biterse sebebi yazılı olarak söylenir.
  const EN_FAZLA_DENEME = 5;
  let yuklemeDenemesi = 0;

  win.webContents.on('did-fail-load', (_e, kod, aciklama, url, anaCerceve) => {
    if (!anaCerceve) return;                     // iframe hatası uygulamayı bozmaz
    if (kod === -3) return;                      // ERR_ABORTED — kullanıcı/yönlendirme kaynaklı, hata değil
    acilisKaydi(`YÜKLEME BAŞARISIZ — ${kod} ${aciklama} (${url})`);
    pencereyiGoster('yükleme hatası');
    if (++yuklemeDenemesi <= EN_FAZLA_DENEME) {
      splashYaz(_et('kabuk.baglanti-yeniden-deneniyor',
        { deneme: yuklemeDenemesi, enFazla: EN_FAZLA_DENEME }), true);
      setTimeout(() => {
        if (win && !win.isDestroyed()) win.loadURL(BACKEND_URL + '/');
      }, 1500);
      return;
    }
    splashYaz(_et('kabuk.arayuz-yuklenemedi-durum'), true);
    dialog.showMessageBoxSync({
      type: 'error',
      title: _et('kabuk.arayuz-yuklenemedi'),
      message: _et('kabuk.arayuz-acilamadi'),
      detail: _et('kabuk.arayuz-yuklenemedi-detay', {
        aciklama, kod, acilisGunlugu: ACILIS_LOG, motorGunlugu: BACKEND_LOG,
      }),
      buttons: [_et('kabuk.tamam')],
      noLink: true,
    });
  });

  let miniGeriYuklendi = false;
  win.webContents.on('did-finish-load', () => {
    pencereyiGoster('arayüz yüklendi');
    // Önceki oturumda Mini HUD açık bırakıldıysa geri getir — motor + arayüz
    // HAZIR olduktan sonra (kart da /ui/mini.html'i motordan yükler). Bir kez.
    if (!miniGeriYuklendi) {
      miniGeriYuklendi = true;
      try { miniHud.oncekiDurumuGeriYukle(); } catch (e) { acilisKaydi(`mini HUD geri yüklenemedi: ${e.message}`); }
    }
    if (pencereDurumu) {
      win.webContents.send('pencere-modu', {
        mod: pencereDurumu.mod,
        kose: pencereDurumu.kose,
      });
    }
  });

  // NOT: Eski "fade in" (setOpacity 0 → 1) KALDIRILDI. İki nedeni var:
  //  ① Windows'ta `transparent:true` pencereler piksel-başına alfa kullanır; `setOpacity`
  //     bununla çakışan bir mekanizmadır ve pencereyi şeffaf bırakabilir.
  //  ② Fade yalnızca `did-finish-load`'da başlıyordu — yükleme düşerse opaklık 0'da
  //     KALIYORDU: çalışan ama kalıcı olarak görünmez bir pencere.
  // Boş pencere yanıp sönmesini artık açılış ekranı örtüyor; fade'in yapacak işi kalmadı.
  win.loadURL(BACKEND_URL + '/');
}

// IPC Handlers — sadece güvenilir localhost origin'den gelen mesajları kabul et
function _isTrustedSender(event) {
  try {
    return event.sender.getURL().startsWith(BACKEND_URL);
  } catch {
    return false;
  }
}

ipcMain.on('window-close', (event) => {
  if (!_isTrustedSender(event)) return;
  win.close();
});

ipcMain.on('window-minimize', (event) => {
  if (!_isTrustedSender(event)) return;
  win.minimize();
});

ipcMain.on('window-toggle-ontop', (event) => {
  if (!_isTrustedSender(event)) return;
  if (!win) return;
  const next = !win.isAlwaysOnTop();
  win.setAlwaysOnTop(next);
  saveWindowState();
});

ipcMain.on('pencere:mod-degistir', (event, istek) => {
  if (!_isTrustedSender(event)) return;
  if (!win || !istek || !Object.hasOwn(MODLAR, istek.mod) || !YAPISMA_KOSELERI.has(istek.kose)) return;
  moduUygula(win, istek.mod, istek.kose);
});

/* Arayüz, konumlandırmanın mümkün olup olmadığını ÖNDEN sorar; böylece
   çalışmayan bir düğmeyi hiç göstermez. "Yetenek sorusu veri ile sorulur,
   hata koduyla değil" (ledger: ui/yetenek-sorusu-hata-koduyla-sorulmaz). */
/* Klasör seçici — yedekleme paneli ( FAZ 4B).
 * ⚠️ `properties:['openDirectory']` TEK BAŞINA yeterli: dosya seçtirmek yanlış
 *    olurdu, motor klasör bekliyor ve tek dosyayı reddediyor (`kaynak_ekle`).
 * ⚠️ Diyalog ANA PENCEREYE bağlanır (modal) — bağlanmazsa Wayland'de arkada
 *    açılıp kilitlenmiş gibi görünebilir. */
ipcMain.handle('dosya:klasor-sec', async (event) => {
  if (!_isTrustedSender(event)) throw new Error('Yetkisiz kaynak.');
  const pencere = BrowserWindow.fromWebContents(event.sender);
  const sonuc = await dialog.showOpenDialog(pencere, {
    title: _et('kabuk.klasor-sec-baslik'),
    // Electron 43+: defaultPath yoksa seçici İndirilenler'de açılır (29'da son
    // klasör/ev). Yedeklenecek klasörler çoğunlukla evin altında → ev dizini.
    // (Linux portal <4 bunu yok sayar; zararsız.)
    defaultPath: app.getPath('home'),
    properties: ['openDirectory'],
    buttonLabel: _et('kabuk.klasor-sec-dugme'),
  });
  if (sonuc.canceled || !sonuc.filePaths || !sonuc.filePaths.length) return { iptal: true };
  return { yol: sonuc.filePaths[0] };
});

ipcMain.handle('pencere:yetenek-al', (event) => {
  if (!_isTrustedSender(event)) throw new Error('Yetkisiz kaynak.');
  return konumlandirmaYetenegi({
    zorlananOzone: app.commandLine.getSwitchValue('ozone-platform'),
  });
});

ipcMain.handle('pencere:modu-al', (event) => {
  if (!_isTrustedSender(event)) throw new Error('Yetkisiz kaynak.');
  const state = pencereDurumu || DEFAULT_STATE;
  return {
    mod: state.mod,
    kose: state.kose,
    ustte: win ? win.isAlwaysOnTop() : state.alwaysOnTop,
  };
});

// ── İndir-gerektiğinde model IPC ─────────────────────────────────────
ipcMain.handle('models:status', (event, id) => {
  if (!_isTrustedSender(event)) throw new Error('Yetkisiz kaynak.');
  if (!modelManager) initModelManager();
  return modelManager.status(id);
});

ipcMain.handle('models:download', async (event, id) => {
  if (!_isTrustedSender(event)) throw new Error('Yetkisiz kaynak.');
  if (!modelManager) initModelManager();
  const send = (payload) => {
    try { event.sender.send('models:progress', { id, ...payload }); } catch (_) {}
  };
  try {
    const res = await modelManager.download(id, send);
    return { ok: true, ...res };
  } catch (e) {
    return { ok: false, error: e.message };
  }
});

ipcMain.on('models:cancel', (event, id) => {
  if (!_isTrustedSender(event)) return;
  if (modelManager) modelManager.cancel(id);
});

// ── Güncelleme denetimi IPC (varsayılan KAPALI — updater.js) ─────────
/**
 * ETKİN sürüm = paket sürümü ile uygulanmış delta'nın BÜYÜĞÜ.
 *
 * 🔴 2026-08-02 saha kusuru: burası düz `app.getVersion()` idi. Delta güncelleme
 * paket sürümünü değiştirmez (değiştirmemesi delta'nın tanımı), dolayısıyla
 * güncelleme başarıyla uygulanıp uygulama v0.5.7 kodunu çalıştırırken bile
 * karşılaştırma v0.5.6'ya bakıyor, "yeni sürüm var" sonsuza kadar doğru kalıyordu.
 * Kullanıcı açısından güncelleme HİÇ BİTMİYORDU.
 *
 * `applied()` geri alma sonrası null döner (`geriAl` durum dosyasını siler) →
 * o durumda doğru şekilde pakete, yani yeniden "güncelleme var"a düşeriz.
 * Fonksiyon olarak veriliyor: delta oturum ortasında uygulanırsa bir sonraki
 * kontrol taze değeri okusun, yeniden başlatmayı beklemesin.
 */
function surumKimligi() {
  let uygulanmis = null;
  try {
    uygulanmis = (getDeltaUpdater().applied() || {}).version || null;
  } catch (_) { /* delta yoksa/okunamıyorsa paket sürümü doğru cevaptır */ }
  return surumKimlik({
    paketSurumu: app.getVersion(),
    overlaySurumu: uygulanmis,
    kabukKimligi: getShellId(),
    katman: KATMAN,
  });
}

function etkinSurum() {
  return surumKimligi().etkin;
}

function initUpdateChecker() {
  if (updateChecker) return updateChecker;
  updateChecker = new UpdateChecker({
    settingsPath: path.join(app.getPath('userData'), 'updater.json'),
    currentVersion: etkinSurum,   // fonksiyon — her okumada yeniden hesaplanır
  });
  return updateChecker;
}

ipcMain.handle('updater:status', (event) => {
  if (!_isTrustedSender(event)) throw new Error('Yetkisiz kaynak.');
  return initUpdateChecker().status();
});

ipcMain.handle('updater:set-enabled', (event, enabled) => {
  if (!_isTrustedSender(event)) throw new Error('Yetkisiz kaynak.');
  initUpdateChecker().setEnabled(enabled);
  return updateChecker.status();
});

ipcMain.handle('updater:set-channel', (event, channel) => {
  if (!_isTrustedSender(event)) throw new Error('Yetkisiz kaynak.');
  initUpdateChecker().setChannel(channel);   // geçersiz kanal patlar, sessizce yutulmaz
  guncellemeKaydi(`kanal değişti → ${channel}`);
  return updateChecker.status();
});

// manual=true → kullanıcı düğmeye bastı; ayar kapalıyken de tek seferlik kontrol eder.
ipcMain.handle('updater:check', async (event, opts) => {
  if (!_isTrustedSender(event)) throw new Error('Yetkisiz kaynak.');
  try {
    return await initUpdateChecker().check({ manual: !!(opts && opts.manual) });
  } catch (e) {
    return { ok: false, error: e.message };
  }
});

ipcMain.handle('updater:open-page', async (event) => {
  if (!_isTrustedSender(event)) throw new Error('Yetkisiz kaynak.');
  await shell.openExternal(initUpdateChecker().status().releasesPage);
  return { ok: true };
});

// ── Delta güncelleme IPC ────────────────────────────────────────────────────
// Uygulama kendi kodunu ~1,2 MiB'lık İMZALI yükle günceller. Ağır bileşenler
// (Python runtime / Electron / 121 MiB medya) yükte YOK — onlar değiştiyse
// manifest'in shell_id'si tutmaz ve akış tam indirmeye düşer.

ipcMain.handle('delta:status', (event) => {
  if (!_isTrustedSender(event)) throw new Error('Yetkisiz kaynak.');
  const u = getDeltaUpdater();
  return {
    applied: u.applied(),
    packagedVersion: app.getVersion(),
    shellId: getShellId(),
    supported: !!getShellId(),   // shell-id yoksa bu paket delta alamaz
  };
});

ipcMain.handle('delta:apply', async (event, version) => {
  if (!_isTrustedSender(event)) throw new Error('Yetkisiz kaynak.');
  if (typeof version !== 'string' || !/^\d+\.\d+\.\d+([-.\w]*)$/.test(version)) {
    return { ok: false, error: _et('kabuk.gecersiz-surum') };   // URL'e giden değer — biçimi kısıtlı
  }
  const gonder = (p) => {
    try { if (win && !win.isDestroyed()) win.webContents.send('delta:progress', p); } catch (_) {}
  };
  try {
    return await getDeltaUpdater().downloadAndApply(version, gonder);
  } catch (e) {
    // Doğrulama hataları buraya düşer — kullanıcı ne olduğunu görmeli, sessizce yutulmamalı.
    console.error('[delta] uygulanamadı:', e.message);
    return { ok: false, error: e.message };
  }
});

ipcMain.handle('delta:revert', (event) => {
  if (!_isTrustedSender(event)) throw new Error('Yetkisiz kaynak.');
  return getDeltaUpdater().geriAl('kullanıcı isteği');
});

// ── Tam paket güncelleme (2026-08-08) ───────────────────────────────────────
// Delta'nın yetmediği durumda kullanıcıyı tarayıcıya göndermek yerine paketi
// uygulama içinden indirip kuruyoruz. İki adım ayrı: indirme uzun ve zararsız,
// kurulum uygulamayı kapatır.

let tamGuncelleyici = null;
function getTamGuncelleyici() {
  if (tamGuncelleyici) return tamGuncelleyici;
  const { TamGuncelleyici } = require('./tam-guncelleme');
  let sku = null;
  // SKU damgası build zamanında `extraMetadata.yukiSku` ile package.json'a girer.
  try { sku = require('./package.json').yukiSku || null; } catch (_) { sku = null; }
  tamGuncelleyici = new TamGuncelleyici({
    sku,
    execPath: process.execPath,
    appImagePath: process.env.APPIMAGE || null,
    userDataDir: app.getPath('userData'),
    gunluk: guncellemeKaydi,
  });
  return tamGuncelleyici;
}

/** İndirilmiş ve DOĞRULANMIŞ paket — `tam:kur` bunu bekler. */
let _tamIndirilen = null;

/* ── Güvenli yeniden başlatma (2026-09-08, geliştirici isteği) ────────────────────
 *
 * geliştirici: *"Sağlık kısmına ve diğer alanlara güvenli ve sağlıklı yeniden
 * başlatma butonu koyalım — herhangi bir ayarı değiştirdikten sonra onu
 * kullanabilirler."*
 *
 * 🔑 NEDEN GEREKLİ: `YUKI_RELOAD=false` — paketlenmiş üründe backend reload
 * KAPALI (read-only mount). Ayar çoğu durumda ancak süreç yeniden başlayınca
 * uygulanır; bugüne kadar kullanıcının tek yolu uygulamayı elle kapatıp açmaktı
 * ve arayüz bunu hiçbir yerde söylemiyordu.
 *
 * 🔑 NEDEN "yalnız backend'i yeniden başlat" DEĞİL: backend'i tek başına
 * öldürüp doğurmak, açılışın test edilmiş zincirini (katmanlı önyükleme ·
 * `motor-bekle` ilerleme ölçütü · açılış ekranı · kilit perdesi) atlar ve
 * ikinci bir açılış yolu doğururdu. Bu depoda "aynı soruya iki cevap er geç
 * ayrışır" dersi (`surum.js`) yazılı. `app.relaunch()` mevcut yolu aynen kullanır.
 *
 * ⚠️ "Güvenli" bir slogan değil, kapı: sürmekte olan bir indirme varken yeniden
 * başlatmak yarım dosya bırakır ve kullanıcı 16-276 MB'ı yeniden indirir.
 * Kapı ÖNCE sorulur, düğme ona göre kapanır.
 */
function _yenidenBaslatmaEngelleri() {
  const engeller = [];
  try {
    const indiriliyor = modelManager.aktifIndirmeler();
    if (indiriliyor.length) {
      engeller.push(_et('kabuk.indirme-suruyor', { liste: indiriliyor.join(', ') }));
    }
  } catch (_) { /* model yöneticisi yoksa engel de yok */ }
  if (_tamIndirilen) {
    engeller.push(_et('kabuk.guncelleme-kurulmayi-bekliyor'));
  }
  return engeller;
}

ipcMain.handle('sistem:yeniden-baslat-durum', (event) => {
  if (!_isTrustedSender(event)) throw new Error('Yetkisiz kaynak.');
  const engeller = _yenidenBaslatmaEngelleri();
  return { yapilabilir: engeller.length === 0, engeller };
});

ipcMain.handle('sistem:yeniden-baslat', (event) => {
  if (!_isTrustedSender(event)) throw new Error('Yetkisiz kaynak.');
  const engeller = _yenidenBaslatmaEngelleri();
  if (engeller.length) return { ok: false, engeller };

  guncellemeKaydi('YENİDEN BAŞLATMA: kullanıcı isteğiyle (ayar değişikliği)');
  app.relaunch();
  /* Kapanış bir tık geciktiriliyor: `relaunch` yeni süreci ancak BİZ çıkınca
     başlatır, ama IPC yanıtının pencereye ulaşması gerekiyor — yoksa arayüz
     "başlatılıyor" mesajını hiç gösteremeden kapanır ve kullanıcı düğmenin
     çalışmadığını sanar. Aynı pay `tam:kur`'da da var. */
  setTimeout(() => { try { app.quit(); } catch (_) { process.exit(0); } }, 400);
  return { ok: true };
});

ipcMain.handle('tam:destekleniyor', (event) => {
  if (!_isTrustedSender(event)) throw new Error('Yetkisiz kaynak.');
  return getTamGuncelleyici().destekleniyor();
});

ipcMain.handle('tam:indir', async (event, version) => {
  if (!_isTrustedSender(event)) throw new Error('Yetkisiz kaynak.');
  if (typeof version !== 'string' || !/^\d+\.\d+\.\d+([-.\w]*)$/.test(version)) {
    return { ok: false, error: _et('kabuk.gecersiz-surum') };
  }
  const gonder = (p) => {
    try { if (win && !win.isDestroyed()) win.webContents.send('tam:progress', p); } catch (_) {}
  };
  try {
    // Akış `tam-akis.js`'te — Electron kurmadan test edilebilsin diye (// burada `fetchManifest`in {man, ham} ZARFI açılmadan geçiriliyordu ve
    // güvenlik kapısı meşru güncellemeyi bir ay boyunca sessizce reddetti).
    _tamIndirilen = await tamPaketiIndir({
      deltaUpdater: getDeltaUpdater(),
      tamGuncelleyici: getTamGuncelleyici(),
      version,
      onProgress: gonder,
    });
    return { ok: true, ...(_tamIndirilen) };
  } catch (e) {
    guncellemeKaydi(`TAM indirme başarısız: ${e.message}`);
    return { ok: false, error: e.message };
  }
});

ipcMain.handle('tam:kur', (event) => {
  if (!_isTrustedSender(event)) throw new Error('Yetkisiz kaynak.');
  if (!_tamIndirilen) return { ok: false, error: _et('kabuk.once-indirilmeli') };
  try {
    const { yenidenBaslat } = getTamGuncelleyici().kur(_tamIndirilen);
    guncellemeKaydi('TAM: kurulum devrediliyor, uygulama kapanıyor');
    // Kapanış ile devir arasına kısa bir pay: Windows yardımcısı bizim
    // kapanmamızı bekliyor, ama önce doğmuş olması gerek.
    yenidenBaslat();
    setTimeout(() => { try { app.quit(); } catch (_) { process.exit(0); } }, 400);
    return { ok: true };
  } catch (e) {
    guncellemeKaydi(`TAM kurulum başarısız: ${e.message}`);
    return { ok: false, error: e.message };
  }
});

// ── Mini HUD — ana pencere gizliyken ekranda kalan durum kartı ────────────
// Kural + gerekçe: mini-hud.js başlığı. Ürünün "Mini" PENCERE MODU (pencere-modu.js)
// ile karıştırma: o ana pencereyi küçültür, bu ayrı bir karttır. Herkese açık.
let tepsiTazele = () => {};
const miniHud = miniHudKurallari({
  BrowserWindow,
  screen,
  anaPencere: () => win,
  icOnEk: BACKEND_URL,
  durumDosyasi: path.join(app.getPath('userData'), 'mini-state.json'),
  preload: kaynak('mini-preload.js'),
  fs,
  execFile: require('child_process').execFile,
  disBaglanti: disBaglantiKurallari({ openExternal: shell.openExternal, icOnEk: BACKEND_URL,
    kaydet: (m) => console.warn('[mini-hud]', m) }),
  kaydet: (m) => console.log(m),
  degisti: (acik) => {
    tepsiTazele();
    if (win && !win.isDestroyed()) { try { win.webContents.send('mini-hud:degisti', acik); } catch (_) {} }
  },
});
miniHud.ipcBagla(ipcMain);

app.whenReady().then(async () => {
  if (!app.hasSingleInstanceLock()) return;   // kilidi alamayan instance backend/pencere açmasın
  _acilisT0 = Date.now();
  acilisKaydi(`=== Yuki v${app.getVersion()} açılıyor — ${process.platform} ${process.arch} ===`);
  initModelManager();   // HF_HOME çözümlemesi + IPC için hazır olsun
  await startBackend();
  createWindow();

  const yapisikModuYenidenUygula = () => {
    if (!win || win.isDestroyed() || !pencereDurumu || pencereDurumu.mod === 'tam') return;
    moduUygula(win, pencereDurumu.mod, pencereDurumu.kose);
  };
  screen.on('display-removed', yapisikModuYenidenUygula);
  screen.on('display-metrics-changed', yapisikModuYenidenUygula);

  // Tray support — ikon okunamazsa `new Tray` FIRLATIR ve bu async blok orada biterdi
  // (güncelleme denetimi hiç kurulmazdı). Tepsi ikonu uygulamayı açmaya engel olamaz.
  try {
    const iconPath = path.join(PAKET_KOK, '..', 'frontend', 'assets', 'characters', 'yuki_avatar.png');
    tray = new Tray(iconPath);
  } catch (e) {
    acilisKaydi(`tepsi ikonu kurulamadı (yok sayıldı): ${e.message}`);
  }

  const buildTrayMenu = () => Menu.buildFromTemplate([
    { label: 'Yuki AI Assistant', enabled: false },
    { type: 'separator' },
    { label: _et('kabuk.tepsi-goster-gizle'), click: () => { win.isVisible() ? win.hide() : win.show(); } },
    {
      label: _et('kabuk.tepsi-her-zaman-ustte'),
      type: 'checkbox',
      checked: win ? win.isAlwaysOnTop() : true,
      click: (item) => {
        win.setAlwaysOnTop(item.checked);
        saveWindowState();
      }
    },
    { type: 'separator' },
    // Mini HUD — arayüzdeki GÖRÜNÜM › PENCERE satırlarının ikizi (tepsi tek yol
    // olamaz: bazı masaüstlerinde Electron'un tepsi ikonu hiç görünmüyor).
    {
      label: _et('kabuk.tepsi-mini-hud'),
      type: 'checkbox',
      checked: miniHud.acikMi(),
      click: () => miniHud.acKapat(),
    },
    { label: _et('kabuk.tepsi-yalniz-mini-hud'), click: () => miniHud.yalniz() },
    { type: 'separator' },
    { label: _et('kabuk.tepsi-cikis'), click: () => app.quit() }
  ]);

  if (tray) {
    tray.setToolTip('Yuki AI Assistant');
    tray.setContextMenu(buildTrayMenu());
    tepsiTazele = () => { if (!tray.isDestroyed()) tray.setContextMenu(buildTrayMenu()); };
  }

  // Güncelleme kontrolü — YALNIZ kullanıcı ⚙ AYAR'dan açtıysa. Kapalıysa check()
  // ağa çıkmadan döner (mahremiyet iddiası korunur). Açılışı yavaşlatmasın diye 20 sn gecikmeli.
  initUpdateChecker();
  setTimeout(async () => {
    try {
      const res = await updateChecker.check();
      if (res.ok && res.updateAvailable && win && !win.isDestroyed()) {
        win.webContents.send('updater:available', res);
      }
    } catch (_) { /* güncelleme kontrolü uygulamayı asla bozmaz */ }
  }, 20000);

  // Tray menüsünü pencere durumu değişince güncelle
  if (win && tray) win.on('always-on-top-changed', () => tray.setContextMenu(buildTrayMenu()));
  // …ve dil değişince: menü bir kez kurulur, etiketler kurulduğu dilde donardı.
  if (tray) require('./dil').dilIzle(() => {
    if (!tray.isDestroyed()) tray.setContextMenu(buildTrayMenu());
  });
});

app.on('window-all-closed', () => {
  // Windows'ta durdurma before-quit'teki kibar yoldan geçer; burada zorla kapatılırsa o yol boşa düşer.
  if (process.platform !== 'win32') stopBackend();
  app.quit();
});

// app.quit() / Çıkış yolu da backend'i (ve reload child'ı) garanti durdursun.
// Windows: önce kibar kapanış — çıkış bir kez ertelenir, sonuç ne olursa olsun
// stopBackend() (gerekirse taskkill /F) ve çıkış. Linux: SIGTERM zaten kibar, eski yol.
let _kibarKapanisDenendi = false;
app.on('before-quit', (e) => {
  uygulamaKapaniyor = true;
  if (process.platform !== 'win32' || _kibarKapanisDenendi || !backend || backend.killed || backendCikisi) {
    stopBackend();
    return;
  }
  _kibarKapanisDenendi = true;
  e.preventDefault();
  windowsKibarKapat()
    .then((sonuc) => acilisKaydi(`kapanış: ${sonuc}`))
    .catch(() => {})
    .finally(() => { stopBackend(); app.quit(); });
});
