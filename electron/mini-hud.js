'use strict';
/**
 * MİNİ HUD — ana pencere gizliyken ekranda kalan 240×180 durum kartı
 * (2026-10-04; kişisel AliceAi 6ba78e2'nin ürün karşılığı).
 *
 * ── Ürünün "Mini" PENCERE MODUYLA karıştırma ─────────────────────────────
 * İkisi ayrı şeydir ve adları da ayrı tutulur:
 *   · Mini pencere modu  (`pencere-modu.js`, MODLAR.mini) — ANA pencerenin
 *     kendisi 320×440'a küçülüp köşeye yapışır; sohbet orada sürer.
 *   · Mini HUD (bu dosya) — AYRI, çerçevesiz, her zaman üstte bir KART.
 *     Ana pencere açık da olabilir gizli de ("Yalnız Mini HUD").
 * Kod adları `miniHud…`/`mini-hud:` önekini taşır; `mini` tek başına
 * kullanılmaz ki `pencere:mod-degistir {mod:'mini'}` ile karışmasın.
 *
 * ── Veri yolu: TEK kaynak ana penceredir ─────────────────────────────────
 * Kart kendi WebSocket'ini, mikrofonunu, ses ölçerini AÇMAZ. Ana penceredeki
 * `js/mini-kopru.js` zaten var olan olayları (`yuki-state`, sahne duygusu,
 * son Yuki balonu, mikrofon düğmelerinin sınıfı) okuyup IPC ile yollar; bu
 * modül yalnız aktarır. Kart ana pencereye durum YAZAMAZ, yalnız beyaz
 * listedeki komutları isteyebilir (mikrofon · her zaman dinle · büyüt · kapat).
 *
 * ── Gönderen kapısı (en dar köprü) ───────────────────────────────────────
 * `_isTrustedSender` (URL öneki) iki pencerede de doğru döner — yani tek başına
 * "kart, ana pencere adına durum yayınlayabilir" demektir. Burada her kanal
 * GÖNDEREN PENCEREYİ de denetler: yayın kanalları yalnız ana pencereden,
 * komut kanalları yalnız karttan kabul edilir.
 *
 * ── Konum ────────────────────────────────────────────────────────────────
 * Wayland'de istemci kendi konumunu belirleyemez (pencere-yetenek.js başlığı,
 * ölçülü). Hyprland algılanırsa konum compositor'a `hyprctl` ile yazdırılır;
 * algılanmazsa hiç çağrılmaz — X11/Windows/macOS'ta Electron'un x/y'si çalışır.
 *
 * ⚠️ Electron'a doğrudan bağımlı DEĞİL: BrowserWindow/screen/ipcMain/execFile
 * dışarıdan verilir. Birim testleri düz Node ile, canlı ölçüm (reports/…/
 * mini-olcum/olc.js) ise SATILAN bu dosyayla koşar — kopya değil.
 */

const path = require('path');

const MINI_W = 240;
const MINI_H = 180;
// Pencere başlığı SABİT: Hyprland kuralı/dispatch'i başlıkla eşleşir. Sayfa
// başlığı dile göre değişseydi eşleşme sessizce tutmazdı → çevrilmez.
const MINI_BASLIK = 'Yuki Mini HUD';
const KENAR_PAY = 24;
const UST_PAY = 36;

const KOMUTLAR = new Set(['mikrofon', 'her-zaman-dinle']);
const DURUMLAR = new Set(['idle', 'listening', 'thinking', 'talking', 'sleeping', 'error']);
const DETAY_TAVAN = 160;

/* ── Saf yardımcılar (testler bunları doğrudan sınar) ───────────────────── */

/** Kayıtlı durum. Bozuk/eksik dosya → varsayılan; sayı olmayan x/y düşer. */
function miniDurumOku(dosya, fs) {
  let ham = null;
  try { ham = JSON.parse(fs.readFileSync(dosya, 'utf8')); } catch (_) { ham = null; }
  const s = { x: undefined, y: undefined, acik: false };
  if (!ham || typeof ham !== 'object') return s;
  if (Number.isFinite(ham.x) && Number.isFinite(ham.y)) { s.x = ham.x; s.y = ham.y; }
  s.acik = ham.acik === true;
  return s;
}

/**
 * Durumu birleştirerek yaz. `sinirlar` kartın getBounds()'u (yoksa null).
 * 🔴 Wayland'de getBounds() (0,0) döner — pencere gerçekte başka yerdeyken.
 * Bunu kaydetmek kartı bir sonraki açılışta sol üst köşeye çivilerdi
 * (kişiselde ölçüldü: gerçek 4200,473 iken kayda 0,0 yazılmıştı) → yok sayılır.
 */
function miniDurumYaz(dosya, ekstra, sinirlar, fs) {
  const s = { ...miniDurumOku(dosya, fs), ...(ekstra || {}) };
  if (sinirlar && Number.isFinite(sinirlar.x) && Number.isFinite(sinirlar.y)
      && !(sinirlar.x === 0 && sinirlar.y === 0)) {
    s.x = sinirlar.x;
    s.y = sinirlar.y;
  }
  try {
    fs.mkdirSync(path.dirname(dosya), { recursive: true });
    fs.writeFileSync(dosya, JSON.stringify({ x: s.x, y: s.y, acik: !!s.acik }), 'utf8');
    return true;
  } catch (_) {
    return false;   // yazılamaması kartı açmaya engel değil
  }
}

/** Kartın en az bir köşesi bir çalışma alanının içinde mi? Monitör çıkınca
 *  eski konum kimsenin görmediği bir koordinata düşer → "açılmadı" sanılır. */
function konumGecerliMi(x, y, alanlar) {
  if (!Number.isFinite(x) || !Number.isFinite(y) || !Array.isArray(alanlar)) return false;
  return alanlar.some((a) => a
    && x + MINI_W > a.x && x < a.x + a.width
    && y + MINI_H > a.y && y < a.y + a.height);
}

/** İmlecin bulunduğu ekranın SAĞ ÜSTÜ. Ham masaüstü genişliğinden çıkarma
 *  yapılmaz (3 monitörde kart ortadaki ekrana düşerdi — kişisel ölçümü). */
function varsayilanKonum(alan) {
  return { x: alan.x + alan.width - MINI_W - KENAR_PAY, y: alan.y + UST_PAY };
}

/** Konum kararı: geçerli kayıt varsa o, yoksa imleç ekranının sağ üstü. */
function konumSec(kayit, alanlar, imlecAlani) {
  if (kayit && konumGecerliMi(kayit.x, kayit.y, alanlar)) return { x: kayit.x, y: kayit.y };
  return varsayilanKonum(imlecAlani || alanlar[0] || { x: 0, y: 0, width: 1280, height: 800 });
}

/** Hyprland yalnız Linux'ta ve compositor kendi imzasını ortama koyduysa var. */
function hyprlandMi(platform, env) {
  return platform === 'linux' && !!(env && env.HYPRLAND_INSTANCE_SIGNATURE);
}

/**
 * Hyprland'e konum yazdıran komutlar, SIRAYLA denenir: önce Lua ayarının
 * biçimi, çıktı tam "ok" değilse eski biçim (kişisel Lua ayarında eski
 * biçim ölü, conf'ta Lua biçimi iş yapmaz). İkisi de MUTLAK masaüstü
 * koordinatı alır — Electron'un workArea'sıyla aynı uzay, dönüşüm yok.
 */
function hyprctlKomutlari(x, y) {
  const xi = Math.round(x);
  const yi = Math.round(y);
  const eslesme = `title:^(${MINI_BASLIK})$`;
  return [
    ['dispatch', `hl.dsp.window.move({ x = ${xi}, y = ${yi}, relative = false, window = "${eslesme}" })`],
    ['dispatch', 'movewindowpixel', `exact ${xi} ${yi},${eslesme}`],
  ];
}

/** Ana pencereden gelen durum paketini süz (tip/uzunluk). Geçersizse null. */
function durumPaketi(durum, detay, duygu) {
  if (typeof durum !== 'string' || !DURUMLAR.has(durum)) return null;
  const p = { tip: 'durum', durum };
  if (typeof detay === 'string') p.detay = detay.slice(0, DETAY_TAVAN);
  if (typeof duygu === 'string' && /^[a-z]{1,16}$/.test(duygu)) p.duygu = duygu;
  return p;
}

/* ── Denetleyici ────────────────────────────────────────────────────────── */

/**
 * @param {object} o
 * @param {Function} o.BrowserWindow
 * @param {object}   o.screen          getAllDisplays · getCursorScreenPoint · getDisplayNearestPoint
 * @param {Function} o.anaPencere      () => ana BrowserWindow | null
 * @param {string}   o.icOnEk          BACKEND_URL
 * @param {string}   o.durumDosyasi    userData/mini-state.json
 * @param {string}   o.preload         mini-preload.js yolu
 * @param {object}   o.fs
 * @param {Function} [o.execFile]      child_process.execFile (Hyprland yolu)
 * @param {string}   [o.platform]      process.platform
 * @param {object}   [o.env]           process.env
 * @param {object}   [o.disBaglanti]   disBaglantiKurallari(...) — kartta da aynı kural
 * @param {Function} [o.degisti]       (acik:boolean) => void — tepsi menüsü tazelensin
 * @param {Function} [o.kaydet]        günlük
 */
function miniHudKurallari(o) {
  const kaydet = o.kaydet || (() => {});
  const platform = o.platform || process.platform;
  const env = o.env || process.env;
  let kart = null;

  const ana = () => {
    const w = o.anaPencere();
    return w && !w.isDestroyed() ? w : null;
  };
  const acikMi = () => !!(kart && !kart.isDestroyed());

  function gonder(paket) {
    if (acikMi()) {
      try { kart.webContents.send('mini-hud:veri', paket); } catch (_) {}
    }
  }

  function konumuCompositoreYazdir(x, y) {
    if (!hyprlandMi(platform, env) || typeof o.execFile !== 'function') return false;
    const [lua, eski] = hyprctlKomutlari(x, y);
    try {
      o.execFile('hyprctl', lua, { timeout: 4000 }, (err, stdout) => {
        if (!err && String(stdout).trim() === 'ok') return;
        o.execFile('hyprctl', eski, { timeout: 4000 }, (e2) => {
          if (e2) kaydet(`[mini-hud] konum yazılamadı: ${e2.message}`);
        });
      });
    } catch (e) {
      kaydet(`[mini-hud] hyprctl çağrılamadı: ${e.message}`);
      return false;
    }
    return true;
  }

  function durumYaz(ekstra) {
    let sinir = null;
    if (acikMi()) { try { sinir = kart.getBounds(); } catch (_) { sinir = null; } }
    miniDurumYaz(o.durumDosyasi, ekstra, sinir, o.fs);
  }

  function ac() {
    if (acikMi()) { kart.showInactive ? kart.showInactive() : kart.show(); return kart; }

    const alanlar = o.screen.getAllDisplays().map((d) => d.workArea);
    let imlecAlani = null;
    try {
      imlecAlani = o.screen.getDisplayNearestPoint(o.screen.getCursorScreenPoint()).workArea;
    } catch (_) { imlecAlani = null; }
    const konum = konumSec(miniDurumOku(o.durumDosyasi, o.fs), alanlar, imlecAlani);

    kart = new o.BrowserWindow({
      x: konum.x,
      y: konum.y,
      width: MINI_W,
      height: MINI_H,
      title: MINI_BASLIK,
      frame: false,
      transparent: true,
      alwaysOnTop: true,
      resizable: false,
      minimizable: false,
      maximizable: false,
      fullscreenable: false,
      skipTaskbar: true,     // bir HUD, uygulama değil — görev çubuğunu kirletmez
      focusable: true,       // düğmeler klavyeyle de kullanılabilsin
      show: false,
      ...(platform === 'linux' ? { roundedCorners: false } : {}),
      webPreferences: {
        preload: o.preload,
        contextIsolation: true,
        nodeIntegration: false,
        sandbox: true,
        webviewTag: false,
      },
      backgroundColor: '#00000000',
    });
    const bu = kart;

    try { bu.setAlwaysOnTop(true, 'screen-saver'); } catch (_) {}
    try { bu.setVisibleOnAllWorkspaces(true, { visibleOnFullScreen: true }); } catch (_) {}

    // Dış bağlantı kuralı ana pencereyle AYNI (kartta bağlantı yok, ama kart
    // hiçbir koşulda tarayıcı penceresine dönüşmemeli).
    if (o.disBaglanti) {
      bu.webContents.setWindowOpenHandler(o.disBaglanti.pencereAcmaIsleyicisi);
      bu.webContents.on('will-navigate', o.disBaglanti.gezinmeIsleyicisi);
    } else {
      bu.webContents.setWindowOpenHandler(() => ({ action: 'deny' }));
      bu.webContents.on('will-navigate', (e) => e.preventDefault());
    }
    // Başlık sabit kalsın (Hyprland eşleşmesi) — sayfanın <title>'ı ezmesin.
    bu.on('page-title-updated', (e) => e.preventDefault());

    let saklaZaman = null;
    bu.on('move', () => {
      clearTimeout(saklaZaman);
      saklaZaman = setTimeout(() => durumYaz(), 500);
    });
    bu.on('closed', () => {
      clearTimeout(saklaZaman);
      if (kart === bu) kart = null;
      kaydet('[mini-hud] kart kapandı');
      // 🔴 Kurtarma: kart kapanırken ana pencere gizliyse ("Yalnız Mini HUD")
      // geri getir. Yoksa uygulama ekranda HİÇBİR yüzeyi olmadan çalışmaya
      // devam eder; tepsi ikonu bazı masaüstlerinde hiç görünmüyor (kişisel
      // ölçümü: waybar'a kaydolmuyor) → tek çıkış yolu kaybolurdu.
      const w = ana();
      if (w && !w.isVisible()) { try { w.show(); } catch (_) {} }
      if (o.degisti) o.degisti(false);
    });

    bu.webContents.on('did-fail-load', (_e, kod, aciklama, url) => {
      kaydet(`[mini-hud] yüklenemedi: ${kod} ${aciklama} ${url}`);
    });
    bu.webContents.on('render-process-gone', (_e, ayrinti) => {
      kaydet(`[mini-hud] renderer öldü: ${ayrinti && ayrinti.reason}`);
    });
    bu.webContents.on('did-finish-load', () => {
      gonder({ tip: 'bagli', deger: !!ana() });
      const w = ana();
      if (w) { try { w.webContents.send('mini-hud:durum-iste'); } catch (_) {} }
      // Konum yükleme SONRASI yazılır: pencere eşlenmeden dispatch eşleşecek
      // pencere bulamaz ve sessizce hiçbir şey yapmaz.
      konumuCompositoreYazdir(konum.x, konum.y);
    });
    bu.once('ready-to-show', () => { try { bu.showInactive(); } catch (_) { bu.show(); } });

    // Token/kimlik URL'de TAŞINMAZ: kart hiçbir API çağırmaz, veri IPC'den
    // gelir ( dersi burada sorun hiç doğmadan kapanıyor).
    bu.loadURL(o.icOnEk + '/ui/mini.html');
    durumYaz({ acik: true });
    kaydet(`[mini-hud] kart açıldı @ ${konum.x},${konum.y}`);
    if (o.degisti) o.degisti(true);
    return bu;
  }

  function kapat() {
    durumYaz({ acik: false });
    if (acikMi()) kart.close();
  }

  function acKapat() { if (acikMi()) kapat(); else ac(); return acikMi(); }

  /** Yalnız Mini HUD: kart açılır, ana pencere GİZLENİR (kapanmaz — mikrofon
   *  ve sohbet orada yaşıyor; kapatmak Yuki'yi sağır bırakırdı). */
  function yalniz() {
    ac();
    const w = ana();
    if (w && w.isVisible()) w.hide();
  }

  /** Karttan ana pencereye dönüş. Kart açık kalır; kapatma kararı kullanıcının. */
  function buyut() {
    const w = ana();
    if (!w) return false;
    if (w.isMinimized()) w.restore();
    w.show();
    w.focus();
    return true;
  }

  /** Ana pencere GERÇEKTEN kapandı: kart yalan söylemesin, o da gider. */
  function anaKapandi() {
    gonder({ tip: 'bagli', deger: false });
    if (acikMi()) kart.close();
  }

  /** Açılışta önceki oturumda açık bıraktıysa kartı geri getir. */
  function oncekiDurumuGeriYukle() {
    if (miniDurumOku(o.durumDosyasi, o.fs).acik) ac();
  }

  const anadanMi = (ev) => { const w = ana(); return !!(w && ev && ev.sender === w.webContents); };
  const karttanMi = (ev) => !!(acikMi() && ev && ev.sender === kart.webContents);
  const onekTutar = (ev) => {
    try { return ev.sender.getURL().startsWith(o.icOnEk); } catch (_) { return false; }
  };

  function ipcBagla(ipcMain) {
    // ── ana pencere → kart (yayın) ──
    ipcMain.on('mini-hud:durum', (ev, durum, detay, duygu) => {
      if (!anadanMi(ev) || !onekTutar(ev)) return;
      const p = durumPaketi(durum, detay, duygu);
      if (p) gonder(p);
    });
    ipcMain.on('mini-hud:mic', (ev, p) => {
      if (!anadanMi(ev) || !onekTutar(ev) || !p || typeof p !== 'object') return;
      gonder({ tip: 'mic', kayit: !!p.kayit, dinle: !!p.dinle, dinleVar: p.dinleVar !== false });
    });
    ipcMain.on('mini-hud:ac-kapat', (ev) => {
      if (!anadanMi(ev) || !onekTutar(ev)) return;
      acKapat();
    });
    ipcMain.on('mini-hud:yalniz', (ev) => {
      if (!anadanMi(ev) || !onekTutar(ev)) return;
      yalniz();
    });
    ipcMain.handle('mini-hud:acik-mi', (ev) => {
      if (!anadanMi(ev) || !onekTutar(ev)) return false;
      return acikMi();
    });
    // ── kart → ana pencere (yalnız beyaz liste) ──
    ipcMain.on('mini-hud:buyut', (ev) => {
      if (!karttanMi(ev) || !onekTutar(ev)) return;
      buyut();
    });
    ipcMain.on('mini-hud:gizle', (ev) => {
      if (!karttanMi(ev) || !onekTutar(ev)) return;
      kapat();
    });
    ipcMain.on('mini-hud:komut', (ev, ad) => {
      if (!karttanMi(ev) || !onekTutar(ev) || !KOMUTLAR.has(ad)) return;
      const w = ana();
      if (w) { try { w.webContents.send('mini-hud:komut', ad); } catch (_) {} }
    });
  }

  return {
    ac, kapat, acKapat, yalniz, buyut, acikMi, gonder, anaKapandi,
    oncekiDurumuGeriYukle, ipcBagla, konumuCompositoreYazdir,
    kart: () => (acikMi() ? kart : null),
  };
}

module.exports = {
  miniHudKurallari,
  miniDurumOku, miniDurumYaz, konumGecerliMi, varsayilanKonum, konumSec,
  hyprlandMi, hyprctlKomutlari, durumPaketi,
  MINI_W, MINI_H, MINI_BASLIK, KOMUTLAR,
};
