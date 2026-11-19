// Mini HUD — durum dosyası, konum geçerliliği, Hyprland algılama, güvenlik ayarları,
// gönderen kapısı ve "Yalnız Mini HUD" geri dönüşü. Electron olmadan düz Node.
//
//   node --test electron/mini-hud.test.js

const test = require('node:test');
const assert = require('node:assert');
const fs = require('fs');
const os = require('os');
const path = require('path');
const { EventEmitter } = require('events');
const m = require('./mini-hud');

const gecici = () => path.join(fs.mkdtempSync(path.join(os.tmpdir(), 'mini-hud-')), 'mini-state.json');
const ALAN_A = { x: 0, y: 0, width: 1920, height: 1080 };
const ALAN_B = { x: 1920, y: 0, width: 1440, height: 900 };

// ── durum dosyası ─────────────────────────────────────────────────────────

test('durum: dosya yok / bozuk / sayı olmayan konum → varsayılan, konum düşer', () => {
  const d = gecici();
  assert.deepStrictEqual(m.miniDurumOku(d, fs), { x: undefined, y: undefined, acik: false });
  fs.writeFileSync(d, '{bozuk');
  assert.deepStrictEqual(m.miniDurumOku(d, fs), { x: undefined, y: undefined, acik: false });
  fs.writeFileSync(d, JSON.stringify({ x: '100', y: null, acik: 'evet' }));
  assert.deepStrictEqual(m.miniDurumOku(d, fs), { x: undefined, y: undefined, acik: false });
  fs.writeFileSync(d, JSON.stringify({ x: 12, y: 34, acik: true }));
  assert.deepStrictEqual(m.miniDurumOku(d, fs), { x: 12, y: 34, acik: true });
});

test('durum: yazım birleştirir, Wayland 0,0 konumu KAYDETMEZ (eski konum korunur)', () => {
  const d = gecici();
  m.miniDurumYaz(d, { acik: true }, { x: 500, y: 60 }, fs);
  assert.deepStrictEqual(m.miniDurumOku(d, fs), { x: 500, y: 60, acik: true });
  m.miniDurumYaz(d, { acik: false }, { x: 0, y: 0 }, fs);
  assert.deepStrictEqual(m.miniDurumOku(d, fs), { x: 500, y: 60, acik: false });
  m.miniDurumYaz(d, null, null, fs);
  assert.deepStrictEqual(m.miniDurumOku(d, fs), { x: 500, y: 60, acik: false });
});

test('durum: yazılamayan dizin açılışı bozmaz (false döner, fırlatmaz)', () => {
  const sahteFs = { ...fs, writeFileSync: () => { throw new Error('EROFS'); }, mkdirSync: () => {} };
  assert.strictEqual(m.miniDurumYaz('/yok/mini-state.json', { acik: true }, null, sahteFs), false);
});

// ── konum ────────────────────────────────────────────────────────────────

test('konum: bir ekranla kesişen kayıt geçerli, monitör çıkınca geçersiz', () => {
  assert.strictEqual(m.konumGecerliMi(2000, 40, [ALAN_A, ALAN_B]), true);
  assert.strictEqual(m.konumGecerliMi(2000, 40, [ALAN_A]), false);        // B çıkarıldı
  assert.strictEqual(m.konumGecerliMi(-m.MINI_W, 10, [ALAN_A]), false);   // tam sol dışı
  assert.strictEqual(m.konumGecerliMi(-m.MINI_W + 1, 10, [ALAN_A]), true); // 1px içeride
  assert.strictEqual(m.konumGecerliMi(10, -m.MINI_H, [ALAN_A]), false);  // tam üst dışı
  assert.strictEqual(m.konumGecerliMi(10, 1080, [ALAN_A]), false);        // tam alt dışı
  assert.strictEqual(m.konumGecerliMi(NaN, 10, [ALAN_A]), false);
  assert.strictEqual(m.konumGecerliMi(10, 10, null), false);
});

test('konum: varsayılan = imleç ekranının SAĞ ÜSTÜ (ham masaüstü genişliği değil)', () => {
  assert.deepStrictEqual(m.varsayilanKonum(ALAN_B), { x: 1920 + 1440 - m.MINI_W - 24, y: 36 });
  // kayıt geçersiz → imleç ekranı; kayıt geçerli → kayıt
  assert.deepStrictEqual(m.konumSec({ x: 9000, y: 9000 }, [ALAN_A, ALAN_B], ALAN_B),
    m.varsayilanKonum(ALAN_B));
  assert.deepStrictEqual(m.konumSec({ x: 300, y: 200 }, [ALAN_A], ALAN_A), { x: 300, y: 200 });
});

// ── Hyprland ─────────────────────────────────────────────────────────────

test('hyprland: yalnız linux + HYPRLAND_INSTANCE_SIGNATURE', () => {
  assert.strictEqual(m.hyprlandMi('linux', { HYPRLAND_INSTANCE_SIGNATURE: 'abc' }), true);
  assert.strictEqual(m.hyprlandMi('linux', {}), false);
  assert.strictEqual(m.hyprlandMi('linux', { HYPRLAND_INSTANCE_SIGNATURE: '' }), false);
  assert.strictEqual(m.hyprlandMi('win32', { HYPRLAND_INSTANCE_SIGNATURE: 'abc' }), false);
  assert.strictEqual(m.hyprlandMi('darwin', { HYPRLAND_INSTANCE_SIGNATURE: 'abc' }), false);
});

test('hyprctl: Lua biçimi önce, eski biçim yedek; mutlak + tam sayı + sabit başlık', () => {
  const [lua, eski] = m.hyprctlKomutlari(1200.4, 36.6);
  assert.deepStrictEqual(lua[0], 'dispatch');
  assert.match(lua[1], /x = 1200, y = 37, relative = false/);
  assert.ok(lua[1].includes(`title:^(${m.MINI_BASLIK})$`));
  assert.deepStrictEqual(eski, ['dispatch', 'movewindowpixel', `exact 1200 37,title:^(${m.MINI_BASLIK})$`]);
});

test('durum paketi: bilinmeyen durum reddedilir, detay kırpılır, duygu süzülür', () => {
  assert.strictEqual(m.durumPaketi('rm -rf', 'x'), null);
  assert.strictEqual(m.durumPaketi(42), null);
  const p = m.durumPaketi('talking', 'a'.repeat(500), 'happy');
  assert.strictEqual(p.detay.length, 160);
  assert.strictEqual(p.duygu, 'happy');
  assert.strictEqual(m.durumPaketi('idle', null, '<img onerror=1>').duygu, undefined);
});

// ── denetleyici (sahte Electron) ─────────────────────────────────────────

function sahteOrtam({ platform = 'linux', env = {}, anaGorunur = true } = {}) {
  const pencereler = [];
  class SahteWC extends EventEmitter {
    constructor(url) { super(); this.url = url; this.gonderilen = []; }
    getURL() { return this.url; }
    send(kanal, ...a) { this.gonderilen.push([kanal, ...a]); }
    setWindowOpenHandler(f) { this.acmaIsleyici = f; }
  }
  class SahteBW extends EventEmitter {
    constructor(opts) {
      super(); this.opts = opts; this.yok = false; this.gorunur = false;
      this.webContents = new SahteWC('');
      pencereler.push(this);
    }
    isDestroyed() { return this.yok; }
    loadURL(u) { this.webContents.url = u; }
    setAlwaysOnTop() {} setVisibleOnAllWorkspaces() {}
    getBounds() { return { x: this.opts.x, y: this.opts.y, width: 240, height: 180 }; }
    show() { this.gorunur = true; } showInactive() { this.gorunur = true; }
    hide() { this.gorunur = false; }
    isVisible() { return this.gorunur; }
    isMinimized() { return false; } restore() {} focus() { this.odak = true; }
    close() { this.yok = true; this.emit('closed'); }
  }
  const ana = new SahteBW({});
  ana.webContents.url = 'http://127.0.0.1:8791/';
  ana.gorunur = anaGorunur;
  pencereler.length = 0;
  const cagrilar = [];
  const ipc = { on: new Map(), handle: new Map() };
  const ipcMain = {
    on: (k, f) => ipc.on.set(k, f),
    handle: (k, f) => ipc.handle.set(k, f),
  };
  const d = gecici();
  const kurallar = m.miniHudKurallari({
    BrowserWindow: SahteBW,
    screen: {
      getAllDisplays: () => [{ workArea: ALAN_A }],
      getCursorScreenPoint: () => ({ x: 5, y: 5 }),
      getDisplayNearestPoint: () => ({ workArea: ALAN_A }),
    },
    anaPencere: () => ana,
    icOnEk: 'http://127.0.0.1:8791',
    durumDosyasi: d,
    preload: '/x/mini-preload.js',
    fs,
    execFile: (...a) => cagrilar.push(a),
    platform,
    env,
  });
  kurallar.ipcBagla(ipcMain);
  return { kurallar, ana, pencereler, cagrilar, ipc, d };
}

test('kart: güvenlik ayarları (contextIsolation · sandbox · node yok · webview yok · ayrı preload)', () => {
  const { kurallar } = sahteOrtam();
  const kart = kurallar.ac();
  const wp = kart.opts.webPreferences;
  assert.strictEqual(wp.contextIsolation, true);
  assert.strictEqual(wp.sandbox, true);
  assert.strictEqual(wp.nodeIntegration, false);
  assert.strictEqual(wp.webviewTag, false);
  assert.strictEqual(wp.preload, '/x/mini-preload.js');
  assert.strictEqual(kart.opts.title, m.MINI_BASLIK);
  assert.strictEqual(kart.opts.width, m.MINI_W);
  assert.strictEqual(kart.opts.skipTaskbar, true);
  // URL'de token/sorgu YOK ( sınıfı)
  assert.strictEqual(kart.webContents.getURL(), 'http://127.0.0.1:8791/ui/mini.html');
  // Yeni pencere açamaz
  assert.deepStrictEqual(kart.webContents.acmaIsleyici({ url: 'https://ornek.com' }), { action: 'deny' });
});

test('kart: ikinci ac() yeni pencere açmaz', () => {
  const { kurallar, pencereler } = sahteOrtam();
  kurallar.ac(); kurallar.ac();
  assert.strictEqual(pencereler.length, 1);
});

test('hyprctl yalnız Hyprland algılanınca çağrılır (yükleme SONRASI)', () => {
  const h = sahteOrtam({ env: { HYPRLAND_INSTANCE_SIGNATURE: 'sig' } });
  const kart = h.kurallar.ac();
  assert.strictEqual(h.cagrilar.length, 0, 'yüklenmeden çağrıldı');
  kart.webContents.emit('did-finish-load');
  assert.strictEqual(h.cagrilar.length, 1);
  assert.strictEqual(h.cagrilar[0][0], 'hyprctl');
  // Lua biçimi "ok" demezse eski biçim denenir
  h.cagrilar[0][3](null, 'Invalid dispatcher');
  assert.strictEqual(h.cagrilar.length, 2);
  assert.strictEqual(h.cagrilar[1][1][1], 'movewindowpixel');

  for (const [platform, env] of [['linux', {}], ['win32', { HYPRLAND_INSTANCE_SIGNATURE: 'sig' }], ['darwin', {}]]) {
    const o = sahteOrtam({ platform, env });
    o.kurallar.ac().webContents.emit('did-finish-load');
    assert.strictEqual(o.cagrilar.length, 0, `${platform} hyprctl çağırdı`);
  }
});

test('Yalnız Mini HUD: ana pencere GİZLENİR (kapanmaz); kart kapanınca geri gelir', () => {
  const { kurallar, ana, d } = sahteOrtam();
  kurallar.yalniz();
  assert.strictEqual(kurallar.acikMi(), true);
  assert.strictEqual(ana.isVisible(), false);
  assert.strictEqual(ana.isDestroyed(), false);
  assert.strictEqual(m.miniDurumOku(d, fs).acik, true);
  kurallar.kapat();
  assert.strictEqual(kurallar.acikMi(), false);
  assert.strictEqual(ana.isVisible(), true, 'kart kapandı ama ana pencere gizli kaldı — çıkış yolu yok');
  assert.strictEqual(m.miniDurumOku(d, fs).acik, false);
});

test('büyüt: kart açık kalır, ana pencere gösterilir ve odaklanır', () => {
  const { kurallar, ana } = sahteOrtam();
  kurallar.yalniz();
  assert.strictEqual(kurallar.buyut(), true);
  assert.strictEqual(ana.isVisible(), true);
  assert.strictEqual(ana.odak, true);
  assert.strictEqual(kurallar.acikMi(), true);
});

test('ana pencere kapandı → kart da kapanır ve "bağlı değil" yollanır', () => {
  const { kurallar } = sahteOrtam();
  const kart = kurallar.ac();
  kurallar.anaKapandi();
  assert.deepStrictEqual(kart.webContents.gonderilen.at(-1), ['mini-hud:veri', { tip: 'bagli', deger: false }]);
  assert.strictEqual(kurallar.acikMi(), false);
});

test('gönderen kapısı: yayın yalnız ANA pencereden, komut yalnız KARTTAN', () => {
  const { kurallar, ana, ipc } = sahteOrtam();
  const kart = kurallar.ac();
  const durum = ipc.on.get('mini-hud:durum');
  durum({ sender: kart.webContents }, 'talking', 'sahte');          // kart kendi adına yayınlayamaz
  assert.strictEqual(kart.webContents.gonderilen.length, 0);
  durum({ sender: ana.webContents }, 'talking', 'merhaba', 'happy');
  assert.deepStrictEqual(kart.webContents.gonderilen.at(-1),
    ['mini-hud:veri', { tip: 'durum', durum: 'talking', detay: 'merhaba', duygu: 'happy' }]);

  const komut = ipc.on.get('mini-hud:komut');
  komut({ sender: ana.webContents }, 'mikrofon');                    // ana kendine komut yollamaz
  komut({ sender: kart.webContents }, 'rm');                         // beyaz liste dışı
  assert.strictEqual(ana.webContents.gonderilen.filter((g) => g[0] === 'mini-hud:komut').length, 0);
  komut({ sender: kart.webContents }, 'her-zaman-dinle');
  assert.deepStrictEqual(ana.webContents.gonderilen.at(-1), ['mini-hud:komut', 'her-zaman-dinle']);

  // Kart ana pencerenin "Yalnız" kanalını tetikleyemez
  ana.gorunur = true;
  ipc.on.get('mini-hud:yalniz')({ sender: kart.webContents });
  assert.strictEqual(ana.isVisible(), true);
  // Ana pencere adresi dışarı gitmişse (öneki tutmuyorsa) reddedilir
  ana.webContents.url = 'https://kotu.example/';
  ipc.on.get('mini-hud:yalniz')({ sender: ana.webContents });
  assert.strictEqual(ana.isVisible(), true);
});

test('önceki oturumda açık bırakıldıysa geri yüklenir, kapalıysa açılmaz', () => {
  const o = sahteOrtam();
  o.kurallar.oncekiDurumuGeriYukle();
  assert.strictEqual(o.kurallar.acikMi(), false);
  m.miniDurumYaz(o.d, { acik: true }, null, fs);
  o.kurallar.oncekiDurumuGeriYukle();
  assert.strictEqual(o.kurallar.acikMi(), true);
});

test('kademe kapısı YOK: modül lisans/kademe okumuyor', () => {
  const kod = fs.readFileSync(path.join(__dirname, 'mini-hud.js'), 'utf8');
  assert.doesNotMatch(kod, /entitlement|license|lisans|kademe\s*[=(]|tier/i);
});
