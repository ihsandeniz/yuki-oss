'use strict';
/**
 * Pencere konumlandırma yeteneği — platform kapısı.
 *
 * 🔴 **Neden bu dosya var (ölçüldü 2026-09-06, Hyprland 0.56.2 + Electron 29):**
 * `setBounds` yalnız KONUMU değiştirdiğinde Wayland'de `getBounds()` istenen
 * değeri geri veriyor → `uygulama.js`'teki 8px sapma kapısı sapmayı 0 görüyor →
 * başarısızlık **sessizce** geçiyor. Ölçüm:
 *
 *   istenen 600,300 (boyut aynı) → getBounds 600,300 (sapma 0, "başarılı")
 *                                → hyprctl   4325,55 (pencere kıpırdamadı)
 *
 * Bu yüzden karar `getBounds()`'a bırakılamaz; önden platform kapısı şart.
 * Testler o kapıyı koruyor — kapı gevşerse Wayland kullanıcısı yine hiçbir şey
 * yapmayan bir düğmeye basar.
 */
const test = require('node:test');
const assert = require('node:assert');
const { konumlandirmaYetenegi, compositorKurali, PENCERE_SINIFI } = require('./pencere-yetenek');

// ── Konumlandırmanın ÇALIŞTIĞI platformlar ────────────────────────────────

test('Windows: konumlandırma desteklenir', () => {
  const y = konumlandirmaYetenegi({ platform: 'win32' });
  assert.strictEqual(y.destekli, true);
  assert.strictEqual(y.sebep, null);
});

test('macOS: konumlandırma desteklenir', () => {
  assert.strictEqual(konumlandirmaYetenegi({ platform: 'darwin' }).destekli, true);
});

test('Linux X11 oturumu: desteklenir', () => {
  const y = konumlandirmaYetenegi({ platform: 'linux', sessionType: 'x11', waylandDisplay: '' });
  assert.strictEqual(y.destekli, true);
  assert.strictEqual(y.arkaUc, 'x11');
});

test('bilinmeyen platform ENGELLENMEZ', () => {
  /* Yanlışlıkla kapatmak çalışan bir özelliği öldürür; yanlışlıkla açık bırakmak
     yalnız mevcut "uygulanamadı" uyarısını üretir. Asimetri bilinçli. */
  assert.strictEqual(konumlandirmaYetenegi({ platform: 'freebsd' }).destekli, true);
});

// ── Konumlandırmanın MÜMKÜN OLMADIĞI yer ──────────────────────────────────

test('Linux Wayland oturumu: desteklenmez ve sebebi vardır', () => {
  const y = konumlandirmaYetenegi({ platform: 'linux', sessionType: 'wayland', masaustu: 'Hyprland' });
  assert.strictEqual(y.destekli, false);
  assert.strictEqual(y.arkaUc, 'wayland');
  assert.ok(y.sebep && y.sebep.length > 20, 'sebep metni boş olmamalı');
});

test('sebep metni suçu Yukiye ATMAZ', () => {
  /* ElevenLabs 401 dersi: yanlış teşhis kullanıcıyı yanlış çözüme yollar.
     "Yuki bozuk" diye okunursa müşteri sürüm değiştirip zaman yakar. */
  const y = konumlandirmaYetenegi({ platform: 'linux', sessionType: 'wayland' });
  assert.ok(/arıza değil|izin ver/i.test(y.sebep), 'sebep, kısıtın kaynağını söylemeli');
  assert.ok(/X11|Windows/.test(y.sebep), 'nerede çalıştığını da söylemeli');
});

test('XDG_SESSION_TYPE boş ama WAYLAND_DISPLAY varsa Wayland sayılır', () => {
  const y = konumlandirmaYetenegi({ platform: 'linux', sessionType: '', waylandDisplay: 'wayland-1' });
  assert.strictEqual(y.destekli, false);
});

// ── Ozone zorlaması — X11'e zorlanmış Electron XWayland istemcisidir ───────

test('YUKI_OZONE=x11 ile Wayland oturumunda bile DESTEKLENİR', () => {
  /* Kritik: Wayland oturumunda `--ozone-platform=x11` verilirse uygulama
     XWayland istemcisi olur ve X11 kuralları geçerlidir — konum ÇALIŞIR.
     Oturuma bakıp "Wayland, kapat" demek burada yanlış cevap olurdu. */
  const y = konumlandirmaYetenegi({
    platform: 'linux', sessionType: 'wayland', zorlananOzone: 'x11',
  });
  assert.strictEqual(y.destekli, true);
  assert.strictEqual(y.arkaUc, 'x11');
});

test('ozone=wayland zorlanmışsa X11 oturumunda bile desteklenmez', () => {
  const y = konumlandirmaYetenegi({
    platform: 'linux', sessionType: 'x11', zorlananOzone: 'wayland',
  });
  assert.strictEqual(y.destekli, false);
});

// ── Kullanıcıya çıkış: masaüstü kuralı ────────────────────────────────────

test('Hyprland kuralı 0.56 sözdizimini kullanır', () => {
  /* ⚠️ 0.56.2'de `windowrulev2` KALDIRILDI ("is deprecated") ve eşleştirici öne
     alındı. Üç satır da bu makinede `hyprctl keyword windowrule …` ile denendi,
     üçü de "ok" döndü. Bu test, birinin ezberden eski biçime dönmesini engeller. */
  const k = compositorKurali('Hyprland', PENCERE_SINIFI);
  assert.strictEqual(k.tur, 'kural');
  assert.ok(k.metin.includes('windowrule = match:class'), 'yeni eşleştirici biçimi');
  assert.ok(!/^windowrulev2 =/m.test(k.metin), 'kaldırılan windowrulev2 KULLANILMAMALI');
  assert.ok(k.metin.includes(PENCERE_SINIFI), 'ölçülen pencere sınıfını taşımalı');
});

test('Hyprland kuralı Lua ayarını da kapsar', () => {
  /* 0.56+ `hyprland.lua` ile açılan oturum `.conf` satırlarını okumaz, 0.57'de conf
     biçimi tamamen kalkıyor. Lua satırı `Hyprland --verify-config` ve iç içe oturumda
     `hyprctl eval` ile ölçüldü (2026-10-03) — ezberden eski biçime dönülmesin. */
  const k = compositorKurali('Hyprland', PENCERE_SINIFI);
  const satirlar = k.metin.split('\n');
  const lua = satirlar.find((s) => s.startsWith('hl.window_rule('));
  assert.ok(lua, 'Lua kuralı olmalı');
  assert.ok(lua.includes(`class = "^(${PENCERE_SINIFI})$"`), 'aynı pencere sınıfı');
  assert.ok(lua.includes('float = true') && lua.includes('size = { 420, "100%" }')
    && lua.includes('move = { "100%-420", 0 }'), 'conf satırlarıyla aynı üç kural');
  assert.ok(satirlar.indexOf(lua) < satirlar.findIndex((s) => s.startsWith('windowrule =')),
    'Lua önde: gelecek biçim o');
  assert.ok(k.baslik.includes('hyprland.lua'), 'başlık Lua dosyasını da söylemeli');
  /* Lua bloğunda `#` yorum olmaz — yapıştırılınca sözdizimi hatası verir. */
  const luaBlok = satirlar.slice(0, satirlar.indexOf(''));
  assert.ok(luaBlok.every((s) => !s.startsWith('#')), 'Lua bloğunda # yorumu yok');
});

test('sway kuralı app_id kullanır', () => {
  const k = compositorKurali('sway', PENCERE_SINIFI);
  assert.ok(k.metin.includes(`app_id="${PENCERE_SINIFI}"`));
});

test('KDE ve GNOME için kural değil YOL tarif edilir', () => {
  /* İkisinde de yapıştırılacak tek satırlık bir kural yok; olmayan bir komut
     vermek kullanıcıyı boşa uğraştırır. */
  assert.strictEqual(compositorKurali('KDE', PENCERE_SINIFI).tur, 'yol');
  assert.strictEqual(compositorKurali('GNOME', PENCERE_SINIFI).tur, 'yol');
});

test('bilinmeyen masaüstünde bile pencere sınıfı verilir', () => {
  const k = compositorKurali('bilinmeyen-wm', PENCERE_SINIFI);
  assert.ok(k.metin.includes(PENCERE_SINIFI), 'kullanıcı en azından sınıfı bilmeli');
});

test('desteklenmeyen ortamda kural HER ZAMAN üretilir', () => {
  /* Kullanıcıyı çıkışsız bırakmama kuralı: "yapamıyoruz" tek başına yetmez. */
  for (const m of ['Hyprland', 'sway', 'KDE', 'GNOME', '', 'garip-wm']) {
    const y = konumlandirmaYetenegi({ platform: 'linux', sessionType: 'wayland', masaustu: m });
    assert.ok(y.kural && y.kural.metin, `kural yok: ${m || '(boş)'}`);
  }
});

test('desteklenen ortamda kural üretilmez', () => {
  assert.strictEqual(konumlandirmaYetenegi({ platform: 'win32' }).kural, null);
});
