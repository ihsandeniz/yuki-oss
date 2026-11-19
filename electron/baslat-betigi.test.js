// `npm start` her platformda çalışmalı (denetim 2026-11-16, MIM: README "Linux or Windows → npm start" diyor).
// Eski betik `WAYLAND_DISPLAY=wayland-1 electron . --ozone-platform=wayland` idi: Windows'ta `VAR=değer` sözdizimi
// yok, X11'de Wayland soketi yok → pencere açılmıyordu. Platform seçimi uygulama.js'te (ozone-platform-hint=auto).
const test = require('node:test');
const assert = require('node:assert');
const fs = require('node:fs');
const path = require('node:path');

const paket = JSON.parse(fs.readFileSync(path.join(__dirname, 'package.json'), 'utf8'));

test('npm start platform bağımsız: ortam ataması ve ozone bayrağı yok', () => {
  const s = paket.scripts.start;
  assert.match(s, /^electron \.(\s|$)/, s);
  assert.doesNotMatch(s, /^\s*[A-Z_]+=/, 'POSIX ortam ataması Windows cmd.exe\'de çalışmaz');
  assert.doesNotMatch(s, /ozone-platform|WAYLAND_DISPLAY/, 'platform seçimi uygulama.js\'te yapılır');
});

test('platform seçimi uygulama.js\'te duruyor (betikten çıkarılan iş kaybolmadı)', () => {
  const kod = fs.readFileSync(path.join(__dirname, 'uygulama.js'), 'utf8');
  assert.match(kod, /ozone-platform-hint', 'auto'/);
});
