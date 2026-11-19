/* Mini HUD kartının preload'ı — ANA pencerenin preload.js'inden AYRI (2026-10-04).
 *
 * Kart yalnız gösterir; güncelleme, model, klasör seçici, yeniden başlatma,
 * pencere modu köprülerinin hiçbirine ihtiyacı yok. Ana preload'ı yüklemek
 * kartın sayfasına bunların hepsini açmak olurdu → burada yalnız dört şey var.
 * Ana süreç (mini-hud.js) ayrıca GÖNDEREN PENCEREYİ denetler: bu kanallar
 * ana pencereden gelse de yok sayılır, ana pencerenin kanalları buradan
 * gelse de. Bu dosya delta yüküyle taşınır (ELECTRON_YASAK'ta değil).
 */
const { contextBridge, ipcRenderer } = require('electron');

contextBridge.exposeInMainWorld('yukiMini', {
  // {tip:'durum'|'mic'|'bagli', ...} — ana pencerenin yayını, ana süreç aktarır
  dinle: (cb) => {
    const handler = (_e, paket) => { try { cb(paket); } catch (_) {} };
    ipcRenderer.on('mini-hud:veri', handler);
    return () => ipcRenderer.removeListener('mini-hud:veri', handler);
  },
  buyut: () => ipcRenderer.send('mini-hud:buyut'),
  gizle: () => ipcRenderer.send('mini-hud:gizle'),
  // Beyaz liste ana süreçte: 'mikrofon' | 'her-zaman-dinle'
  komut: (ad) => ipcRenderer.send('mini-hud:komut', String(ad)),
});
