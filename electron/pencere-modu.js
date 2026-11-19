// Pencere modu hesapları — Electron'a bağımlı DEĞİL, bu yüzden düz Node ile test edilir.

const MODLAR = {
  tam: { genislik: null, yukseklik: null, ustte: false },
  panel: { genislik: 420, yukseklik: 'tam', ustte: true },
  mini: { genislik: 320, yukseklik: 440, ustte: true },
};

const PAY = 16;

/** Modu ve yapışma köşesini gerçek piksel sınırlarına çevir. */
function modBoyutu(mod, kose, calismaAlani, kayit) {
  const { x: ax, y: ay, width: aw, height: ah } = calismaAlani;
  const m = MODLAR[mod];
  if (!m) throw new Error(`bilinmeyen mod: ${mod}`);

  if (mod === 'tam') {
    return { ...(kayit || { width: 1100, height: 760 }), ustte: false };
  }

  const width = Math.min(m.genislik, aw - PAY * 2);
  const height = m.yukseklik === 'tam'
    ? ah - PAY * 2
    : Math.min(m.yukseklik, ah - PAY * 2);

  const sag = kose.includes('sag');
  const alt = kose.includes('alt');
  const tamY = kose.includes('tam');

  return {
    x: sag ? ax + aw - width - PAY : ax + PAY,
    y: tamY || !alt ? ay + PAY : ay + ah - height - PAY,
    width,
    height,
    ustte: m.ustte,
  };
}

/** Kullanıcı ayarını değiştirmeden dar kabukta uygulanacak avatarı seç. */
function etkinAvatar(ayar, kabukGenisligi) {
  return ayar === 'buyuk' && kabukGenisligi < 380 ? 'kucuk' : ayar;
}

module.exports = { modBoyutu, etkinAvatar, MODLAR, PAY };
