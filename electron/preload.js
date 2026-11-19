const { contextBridge, ipcRenderer } = require('electron');

contextBridge.exposeInMainWorld('yukiApp', {
  version: '0.5.3',
  close: () => ipcRenderer.send('window-close'),
  minimize: () => ipcRenderer.send('window-minimize'),
  toggleAlwaysOnTop: () => ipcRenderer.send('window-toggle-ontop'),
  setWindowMode: (mod, kose) => ipcRenderer.send('pencere:mod-degistir', { mod, kose }),
  getWindowMode: () => ipcRenderer.invoke('pencere:modu-al'),
  getWindowSupport: () => ipcRenderer.invoke('pencere:yetenek-al'),
  onWindowMode: (cb) => {
    const handler = (_e, payload) => cb(payload);
    ipcRenderer.on('pencere-modu', handler);
    return () => ipcRenderer.removeListener('pencere-modu', handler);
  },
  /* Mod uygulandı sanılıp uygulanmadığında tetiklenir (Wayland: setBounds sessizce
   * yok sayılıyor). Kullanıcıya söylemenin tek yolu bu — sessiz başarısızlık yasak. */
  onWindowModeFailed: (cb) => {
    const handler = (_e, payload) => cb(payload);
    ipcRenderer.on('pencere-modu-uygulanamadi', handler);
    return () => ipcRenderer.removeListener('pencere-modu-uygulanamadi', handler);
  },
});

/* Mini HUD köprüsü — ANA pencere tarafı (2026-10-04, electron/mini-hud.js).
 * Ana pencere durumun TEK kaynağıdır: kart kendi WS'ini/mikrofonunu açmaz, buradan
 * yayınlananı gösterir. Kartın kendi preload'ı ayrı ve daha dar (mini-preload.js).
 * Yalnız Electron'da tanımlı; tarayıcıda `undefined` → menü satırları hiç görünmez. */
const _miniDinle = (kanal) => (cb) => {
  const handler = (_e, ...a) => { try { cb(...a); } catch (_) {} };
  ipcRenderer.on(kanal, handler);
  return () => ipcRenderer.removeListener(kanal, handler);
};
contextBridge.exposeInMainWorld('yukiMiniHud', {
  durum: (durum, detay, duygu) => ipcRenderer.send('mini-hud:durum', durum, detay, duygu),
  mic: (p) => ipcRenderer.send('mini-hud:mic', p),
  acKapat: () => ipcRenderer.send('mini-hud:ac-kapat'),
  yalniz: () => ipcRenderer.send('mini-hud:yalniz'),
  acikMi: () => ipcRenderer.invoke('mini-hud:acik-mi'),
  durumIste: _miniDinle('mini-hud:durum-iste'),   // kart yeni açıldı → mevcut durumu yolla
  komut: _miniDinle('mini-hud:komut'),            // kart → 'mikrofon' | 'her-zaman-dinle'
  degisti: _miniDinle('mini-hud:degisti'),        // kart açıldı/kapandı (bool)
});

/* Güvenli yeniden başlatma (2026-09-08). Yalnız Electron'da tanımlı — tarayıcıda
 * `undefined` kalır ve arayüz düğmeyi DÜRÜSTÇE kapatır. Backend sürecini Electron
 * `spawn` ettiği için `/ui` tarayıcıdan açıldığında yeniden başlatma teknik olarak
 * mümkün değildir; "kapıya bakan arayüz" kuralının aynısı. */
contextBridge.exposeInMainWorld('yukiSistem', {
  // {yapilabilir:boolean, engeller:string[]} — düğmeyi göstermeden ÖNCE sorulur
  yenidenBaslatilabilirMi: () => ipcRenderer.invoke('sistem:yeniden-baslat-durum'),
  // {ok:true} | {ok:false, engeller} — ok:true ise uygulama ~400 ms içinde kapanır
  yenidenBaslat: () => ipcRenderer.invoke('sistem:yeniden-baslat'),
});

/* Klasör seçici ( FAZ 4B, 2026-09-14) — yedekleme paneli için.
 * Yalnız Electron'da tanımlı; tarayıcıda `undefined` kalır ve panel DÜRÜSTÇE
 * metin alanına düşer ("kapıya bakan arayüz" kuralı).
 * 🔑 Neden native diyalog: müşterinin klasör YOLUNU yazması gerçek bir engel —
 *    yanlış yazılan yol sessiz bir "yedeğim var" hissi üretir.
 * ✅ Bu dosya delta yüküyle taşınır (`ELECTRON_YASAK` yalnız main.js+onyukleme.js)
 *    → özellik `shell_id` değiştirmeden müşteriye gidebilir ( kısıtı).
 */
contextBridge.exposeInMainWorld('yukiDosya', {
  // {yol:string} | {iptal:true}
  klasorSec: () => ipcRenderer.invoke('dosya:klasor-sec'),
});

// İndir-gerektiğinde model API'si. Yalnız Electron'da tanımlı; web modunda undefined kalır
// → frontend "bu platformda indirilemez" fallback'ine düşer.
contextBridge.exposeInMainWorld('yukiModels', {
  // Modelin durumu: {id, name, feature, present, downloadable, downloading, sizeBytes, downloadBytes, tier}
  status: (id) => ipcRenderer.invoke('models:status', id),
  // İndir + doğrula + aç. {ok:true} | {ok:false, error}. İlerleme onProgress ile gelir.
  download: (id) => ipcRenderer.invoke('models:download', id),
  cancel: (id) => ipcRenderer.send('models:cancel', id),
  // onProgress(cb): cb({id, phase:'download'|'extract'|'done', received, total}). Aboneliği kaldıran fn döner.
  onProgress: (cb) => {
    const handler = (_e, payload) => cb(payload);
    ipcRenderer.on('models:progress', handler);
    return () => ipcRenderer.removeListener('models:progress', handler);
  },
});

// Güncelleme denetimi. VARSAYILAN KAPALI — kapalıyken check() ağa çıkmaz.
// Web modunda undefined kalır → UI "yalnız masaüstü sürümünde" fallback'ine düşer.
contextBridge.exposeInMainWorld('yukiUpdater', {
  // {enabled, currentVersion, lastCheck, lastSeenVersion, releasesPage}
  status: () => ipcRenderer.invoke('updater:status'),
  setEnabled: (on) => ipcRenderer.invoke('updater:set-enabled', !!on),
  // 'stable' (varsayılan, 24 saat bekler) | 'beta' (ön-yayınları da görür, beklemez)
  setChannel: (c) => ipcRenderer.invoke('updater:set-channel', String(c)),
  // manual:true → kullanıcı düğmeye bastı; ayar kapalıyken de tek seferlik kontrol eder.
  check: (manual = true) => ipcRenderer.invoke('updater:check', { manual }),
  openReleasesPage: () => ipcRenderer.invoke('updater:open-page'),
  // Açılıştaki otomatik kontrol yeni sürüm bulursa tetiklenir.
  onAvailable: (cb) => {
    const handler = (_e, payload) => cb(payload);
    ipcRenderer.on('updater:available', handler);
    return () => ipcRenderer.removeListener('updater:available', handler);
  },

  // ── Tam paket güncelleme (uygulama içinden, imzalı) ───────────────────────
  // Delta'nın yetmediği durumlar için (Python bağımlılığı / Electron sürümü
  // değişti). 2026-08-08'e kadar kullanıcı GitHub sayfasına yollanıyordu.
  // İki adım bilinçli ayrı: "indir" (uzun, iptal edilebilir) ve "kur+yeniden
  // başlat" (uygulamayı kapatır) ayrı onay ister.
  tam: {
    // {ok:true,hedef} | {ok:false,sebep} — teklif etmeden ÖNCE sorulmalı
    destekleniyor: () => ipcRenderer.invoke('tam:destekleniyor'),
    // version → {dosya, ad, boyut} (doğrulanmış); kurulumu DEĞİŞTİRMEZ
    indir: (version) => ipcRenderer.invoke('tam:indir', version),
    // Uygulamayı kapatır ve kurulumu devreder — geri dönüşü yok, onay şart
    kurVeYenidenBaslat: () => ipcRenderer.invoke('tam:kur'),
    onProgress: (cb) => {
      const handler = (_e, payload) => cb(payload);
      ipcRenderer.on('tam:progress', handler);
      return () => ipcRenderer.removeListener('tam:progress', handler);
    },
  },

  // ── Delta güncelleme (~1,2 MiB, imzalı) ───────────────────────────────────
  // Uygulama kendi kodunu günceller; kullanıcı GitHub'a gidip 440 MiB indirmez.
  // Çekirdek bileşenler (Python runtime / Electron) değiştiyse {requiresFull:true}
  // döner ve akış yukarıdaki `tam` yoluna geçer — artık tarayıcıya değil.
  delta: {
    // {applied:{version,appliedAt}|null, packagedVersion, shellId}
    status: () => ipcRenderer.invoke('delta:status'),
    // version → {ok, files, bytes} | {ok:false, requiresFull, reason}
    apply: (version) => ipcRenderer.invoke('delta:apply', version),
    // Overlay'i atıp paketlenmiş sürüme dön (kullanıcı isterse).
    revert: () => ipcRenderer.invoke('delta:revert'),
    onProgress: (cb) => {
      const handler = (_e, payload) => cb(payload);
      ipcRenderer.on('delta:progress', handler);
      return () => ipcRenderer.removeListener('delta:progress', handler);
    },
  },
});
