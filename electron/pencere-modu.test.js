// Pencere modu hesapları — Electron olmadan düz Node testinden çalışır.
//
//   node --test electron/pencere-modu.test.js

const test = require('node:test');
const assert = require('node:assert');
const { modBoyutu, etkinAvatar, MODLAR, PAY } = require('./pencere-modu');

const ALAN = { x: 100, y: 50, width: 1000, height: 800 };
const KAYIT = { x: 175, y: 95, width: 900, height: 700 };
const KOSELER = ['sol-ust', 'sag-ust', 'sol-tam', 'sag-tam', 'sol-alt', 'sag-alt'];

function beklenen(mod, kose) {
  if (mod === 'tam') return { ...KAYIT, ustte: false };

  const width = mod === 'panel' ? 420 : 320;
  const height = mod === 'panel' ? 768 : 440;
  const sag = kose.startsWith('sag');
  const alt = kose.endsWith('alt');
  return {
    x: sag ? 100 + 1000 - width - 16 : 100 + 16,
    y: alt ? 50 + 800 - height - 16 : 50 + 16,
    width,
    height,
    ustte: mod !== 'tam',
  };
}

for (const mod of Object.keys(MODLAR)) {
  for (const kose of KOSELER) {
    test(`${mod} / ${kose} doğru sınırlara oturur`, () => {
      const sonuc = modBoyutu(mod, kose, ALAN, KAYIT);
      assert.deepEqual(sonuc, beklenen(mod, kose));
    });
  }
}

test('tam modu kayıt yoksa 1100x760 varsayar ve üstte değildir', () => {
  assert.deepEqual(modBoyutu('tam', 'sag-tam', ALAN, null), {
    width: 1100,
    height: 760,
    ustte: false,
  });
});

test('PAY=16 sol/sağ/üst/alt kenarların tamamında uygulanır', () => {
  const alan = { x: 0, y: 0, width: 800, height: 600 };
  const solUst = modBoyutu('mini', 'sol-ust', alan, null);
  const sagAlt = modBoyutu('mini', 'sag-alt', alan, null);
  const panel = modBoyutu('panel', 'sag-tam', alan, null);

  assert.equal(PAY, 16);
  assert.equal(solUst.x - alan.x, PAY);
  assert.equal(solUst.y - alan.y, PAY);
  assert.equal(alan.x + alan.width - (sagAlt.x + sagAlt.width), PAY);
  assert.equal(alan.y + alan.height - (sagAlt.y + sagAlt.height), PAY);
  assert.equal(panel.y - alan.y, PAY);
  assert.equal(alan.y + alan.height - (panel.y + panel.height), PAY);
});

test('dar çalışma alanında panel ve mini boyutları Math.min ile sınırlanır', () => {
  const dar = { x: 0, y: 0, width: 300, height: 400 };
  assert.deepEqual(modBoyutu('panel', 'sol-tam', dar, null), {
    x: 16, y: 16, width: 268, height: 368, ustte: true,
  });
  assert.deepEqual(modBoyutu('mini', 'sag-alt', dar, null), {
    x: 16, y: 16, width: 268, height: 368, ustte: true,
  });
});

test('negatif başlangıçlı soldaki monitörde koordinatlar doğru hesaplanır', () => {
  const soldaki = { x: -1920, y: -200, width: 1920, height: 1080 };
  assert.deepEqual(modBoyutu('mini', 'sag-alt', soldaki, null), {
    x: -336, y: 424, width: 320, height: 440, ustte: true,
  });
  assert.deepEqual(modBoyutu('panel', 'sol-tam', soldaki, null), {
    x: -1904, y: -184, width: 420, height: 1048, ustte: true,
  });
});

test('bilinmeyen mod sessizce başka moda düşmez', () => {
  assert.throws(
    () => modBoyutu('bilinmeyen', 'sag-tam', ALAN, null),
    /bilinmeyen mod: bilinmeyen/,
  );
});

test('etkinAvatar 379/380 sınırını uygular, kullanıcı ayarını değiştirmez', () => {
  const kullaniciAyari = { avatar: 'buyuk' };
  assert.equal(etkinAvatar(kullaniciAyari.avatar, 379), 'kucuk');
  assert.equal(etkinAvatar(kullaniciAyari.avatar, 380), 'buyuk');
  assert.equal(kullaniciAyari.avatar, 'buyuk');
  assert.equal(etkinAvatar('kucuk', 200), 'kucuk');
  assert.equal(etkinAvatar('gizli', 200), 'gizli');
});
