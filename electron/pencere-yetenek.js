'use strict';
/**
 * Pencere KONUMLANDIRMA yeteneği — platforma göre, tahminle değil kuralla.
 *
 * 🔴 **Neden var (ölçüldü 2026-09-06, Hyprland 0.56.2 + Electron 29):**
 * Wayland'de bir uygulama kendi pencere konumunu belirleyemez. Bu bir Electron
 * kusuru değil, protokol kararıdır. Ölçüm:
 *
 *   setBounds({x:1020, y:0, 420x900})
 *     Electron  getBounds() →  0,0  945x1015     (300 ms sonra)
 *     compositor hyprctl    →  2405,55 945x1015
 *
 * Yani ne konum ne boyut tuttu. Daha kötüsü, **yalnız konum** değiştirildiğinde
 * (boyut aynı kalınca) Electron istenen değeri geri veriyor:
 *
 *   setBounds({x:+600, y:+300, boyut aynı})
 *     Electron  getBounds() →  600,300   → sapma 0  → "başarılı" sanılır
 *     compositor hyprctl    →  4325,55   → pencere hiç kıpırdamadı
 *
 * `uygulama.js`'teki 8px'lik sapma kapısı bu vakayı **kaçırır**: yakalayabildiği
 * tek şey boyut uyuşmazlığıdır. Panel/Mini'ye geçerken boyut da değiştiği için
 * yakalanıyordu; **aynı boyutta sol köşeden sağ köşeye** geçişte sapma 0 çıkıp
 * sessizce geçiyordu. geliştiricinin *"sol/sağ kenara yapışma sıkıntılı"* şikâyetinin
 * kök nedeni budur.
 *
 * 🔑 Çözüm sapma kapısını sıkılaştırmak DEĞİL — `getBounds()` Wayland'de
 * güvenilmez bir kaynak, ne kadar beklersen bekle. Doğru hamle **önden kapı**:
 * konumlandırmanın mümkün olmadığı yerde özelliği sunmamak ve sebebini söylemek.
 *
 * ⚠️ Bu dosya Electron'a bağımlı DEĞİL (saf fonksiyon) — testleri gerçek pencere
 * kurmadan koşabilsin diye. `uygulama.js` içine gömülseydi yalnız canlı Electron
 * ile sınanabilirdi; `motor-bekle.js` ve `dis-baglanti.js` de aynı sebeple ayrı.
 */

/** Pencerenin Wayland `app_id` / X11 sınıfı — ÖLÇÜLDÜ (`hyprctl clients`). */
const PENCERE_SINIFI = 'yuki-oss';

const _et = require('./dil').t;

/**
 * Compositor kural şablonları. Kullanıcı konumlandıramadığımızda **bunu
 * yapıştırarak** aynı sonucu kendi masaüstünde elde eder.
 *
 * ⚠️ Hyprland sözdizimi sürümle DEĞİŞİYOR: 0.56.2'de `windowrulev2` kaldırıldı
 * (*"is deprecated"*) ve eşleştirici öne alındı. Aşağıdaki üç conf satırı bu makinede
 * `hyprctl keyword windowrule …` ile tek tek denendi ve üçü de **ok** döndü;
 * ezberden yazılmadı. Eski sürümlerde `windowrulev2 = float, class:^(…)$`
 * biçimi geçerliydi — not metinde söyleniyor, kullanıcı sürümüne göre seçsin.
 *
 * 🔴 Hyprland 0.56+ `hyprland.lua` ile açılınca `.conf` satırları OKUNMAZ, 0.57'de
 * conf biçimi tamamen kalkıyor. Lua karşılığı bu yüzden önde. Ölçüldü 2026-10-03 (0.56.2):
 * `Hyprland --verify-config` → ok · iç içe Lua oturumunda `hyprctl eval` → ok ve pencere,
 * conf oturumundaki üç `keyword windowrule` satırıyla birebir aynı sonuçlandı. Hangi
 * biçimde olduğunu kullanıcı bilmeyebilir → ikisi de verilir, etiketler dosya adıdır.
 */
function hyprlandKurali(sinif) {
  return [
    '-- hyprland.lua (Hyprland 0.56+)',
    `hl.window_rule({ name = "yuki", match = { class = "^(${sinif})$" }, float = true, size = { 420, "100%" }, move = { "100%-420", 0 } })`,
    '',
    '# hyprland.conf',
    `windowrule = match:class ^(${sinif})$, float true`,
    `windowrule = match:class ^(${sinif})$, size 420 100%`,
    `windowrule = match:class ^(${sinif})$, move 100%-420 0`,
    '# ' + _et('pencere.hypr-eski-surum') + ': windowrulev2 = float, class:^(' + sinif + ')$',
  ].join('\n');
}

function swayKurali(sinif) {
  return [
    `for_window [app_id="${sinif}"] floating enable`,
    `for_window [app_id="${sinif}"] resize set 420 1000`,
    `for_window [app_id="${sinif}"] move position 1500 0`,
  ].join('\n');
}

/** Masaüstüne göre "bunu sen yapabilirsin" reçetesi. */
function compositorKurali(masaustu, sinif) {
  const m = String(masaustu || '').toLowerCase();
  if (m.includes('hyprland')) {
    return { tur: 'kural', baslik: 'Hyprland — hyprland.lua / hyprland.conf', metin: hyprlandKurali(sinif) };
  }
  if (m.includes('sway')) {
    return { tur: 'kural', baslik: 'sway — config', metin: swayKurali(sinif) };
  }
  if (m.includes('kde') || m.includes('plasma')) {
    return {
      tur: 'yol',
      baslik: _et('pencere.kde-baslik'),
      metin: _et('pencere.kde-metin', { sinif }),
    };
  }
  if (m.includes('gnome')) {
    return {
      tur: 'yol',
      baslik: _et('pencere.gnome-baslik'),
      metin: _et('pencere.gnome-metin'),
    };
  }
  return {
    tur: 'yol',
    baslik: _et('pencere.genel-baslik'),
    metin: _et('pencere.genel-metin', { sinif }),
  };
}

/**
 * Konumlandırma bu ortamda mümkün mü?
 *
 * @param {object} ortam - hepsi opsiyonel; verilmezse `process`ten okunur.
 *   `platform` · `sessionType` (XDG_SESSION_TYPE) · `waylandDisplay` ·
 *   `zorlananOzone` (--ozone-platform, boşsa hint=auto) · `masaustu` (XDG_CURRENT_DESKTOP)
 * @returns {{destekli:boolean, arkaUc:string, sebep:string|null, kural:object|null}}
 */
function konumlandirmaYetenegi(ortam = {}) {
  const platform = ortam.platform || process.platform;
  const sinif = ortam.sinif || PENCERE_SINIFI;

  if (platform === 'win32') return { destekli: true, arkaUc: 'win32', sebep: null, kural: null };
  if (platform === 'darwin') return { destekli: true, arkaUc: 'darwin', sebep: null, kural: null };
  if (platform !== 'linux') {
    // Bilinmeyen platformda ENGELLEMİYORUZ: yanlışlıkla kapatmak çalışan bir
    // özelliği öldürür; yanlışlıkla açık bırakmak yalnız mevcut uyarıyı üretir.
    return { destekli: true, arkaUc: platform, sebep: null, kural: null };
  }

  /* Linux: belirleyici olan dağıtım DEĞİL, oturumun görüntü sunucusu.
     Aynı Arch'ta X11 oturumunda çalışır, Wayland oturumunda çalışmaz. */
  const zorlanan = String(ortam.zorlananOzone || '').toLowerCase();
  let wayland;
  if (zorlanan === 'x11') {
    wayland = false;      // XWayland istemcisi → X11 kuralları geçerli, konum ÇALIŞIR
  } else if (zorlanan === 'wayland') {
    wayland = true;
  } else {
    // hint=auto → oturum ne diyorsa o
    const st = String(ortam.sessionType ?? process.env.XDG_SESSION_TYPE ?? '').toLowerCase();
    const wd = ortam.waylandDisplay ?? process.env.WAYLAND_DISPLAY;
    wayland = st === 'wayland' || (!st && !!wd);
  }

  if (!wayland) return { destekli: true, arkaUc: 'x11', sebep: null, kural: null };

  const masaustu = ortam.masaustu ?? process.env.XDG_CURRENT_DESKTOP ?? '';
  return {
    destekli: false,
    arkaUc: 'wayland',
    /* Metin DÜRÜST: "çalışmıyor" değil "izin verilmiyor". Kullanıcı bunu bizim
       kusurumuz sanıp sürüm değiştirerek zaman harcamasın (ElevenLabs 401 dersi:
       yanlış teşhis kullanıcıyı yanlış çözüme yollar). */
    sebep: _et('pencere.wayland-sebep'),
    kural: compositorKurali(masaustu, sinif),
  };
}

module.exports = { konumlandirmaYetenegi, compositorKurali, PENCERE_SINIFI };
