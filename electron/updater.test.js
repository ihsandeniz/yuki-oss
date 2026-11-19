/**
 * Güncelleme denetleyicisi testleri — `node --test electron/`
 *
 * 🔴 NEDEN VAR — 2026-08-02 saha kusuru (geliştiricinin Windows makinesi, v0.5.7 turu):
 *
 *   Panel şunu gösteriyordu:
 *       Kurulu sürüm: v0.5.7  (paket v0.5.6 + güncelleme)
 *       "v0.5.7 hazır. Değişiklikler Yuki'yi kapatıp açtığında etkin olacak."
 *
 *   Kullanıcı kapatıp açtı — mesaj GİTMEDİ. Çünkü delta güncelleme başarıyla
 *   uygulanmış ve uygulama gerçekten v0.5.7 kodunu çalıştırıyor olsa da,
 *   `UpdateChecker` `app.getVersion()` ile besleniyordu; o da ASAR içindeki
 *   **paket** sürümünü (v0.5.6) döndürür. Delta paket sürümünü değiştirmez —
 *   değiştirmemesi delta'nın tanımıdır. Sonuç: `0.5.7 > 0.5.6` sonsuza kadar
 *   doğru → panel her kontrolde yeniden "ŞİMDİ GÜNCELLE" diyordu.
 *   Kullanıcı açısından **güncelleme hiç bitmiyordu**; her turda aynı 1,15 MiB
 *   yeniden inip yeniden uygulanıyordu.
 *
 *   İronisi: panel çalışan sürümü DOĞRU gösteriyordu (delta durumunu ayrıca
 *   okuyarak). Yalnızca *karşılaştırma* başka bir kaynaktan besleniyordu.
 *   **Ders: "hangi sürümdeyim" sorusunun tek cevabı olmalı; iki kaynak varsa
 *   er geç ayrışırlar ve ayrıştıkları yerde kimse bakmıyordur.**
 *
 *   Bu kusurun kaçma sebebi ölçüldü: `updater.js`'in HİÇ testi yoktu.
 */
const test = require('node:test');
const assert = require('node:assert');
const fs = require('fs');
const os = require('os');
const path = require('path');

// ⚠️ `etkinSurumSec` BURADAN alınıyor, testin içinde yeniden yazılmıyor.
// Sebep: aynı mantığı testte kopyalarsak, main.js eski hâline dönse bile test
// yeşil kalır — iddia ile kanıt ayrı yerlerde yaşayamaz.
const { UpdateChecker, compareVersions, parseVersion, etkinSurumSec } = require('./updater');

function tmpAyar() {
  const d = fs.mkdtempSync(path.join(os.tmpdir(), 'yuki-upd-'));
  return path.join(d, 'updater.json');
}

// ── Sürüm karşılaştırma — temel ─────────────────────────────────────

test('compareVersions sıralamayı doğru yapar', () => {
  assert.strictEqual(compareVersions('0.5.7', '0.5.6'), 1);
  assert.strictEqual(compareVersions('0.5.6', '0.5.7'), -1);
  assert.strictEqual(compareVersions('0.5.7', '0.5.7'), 0);
  assert.strictEqual(compareVersions('v0.5.7', '0.5.7'), 0, 'baştaki v yok sayılmalı');
  assert.strictEqual(compareVersions('0.6.0', '0.5.99'), 1);
  assert.strictEqual(compareVersions('1.0.0', '0.9.9'), 1);
});

test('parseVersion bozuk girdide çökmez', () => {
  assert.strictEqual(parseVersion('abc'), null);
  assert.strictEqual(compareVersions('abc', '0.5.7'), 0, 'okunamayan sürüm "yeni" sayılmamalı');
});

// ── ASIL REGRESYON: delta uygulanmışsa aynı sürüm tekrar önerilmez ──

test('currentVersion sabit string olarak verilebilir (geriye uyum)', () => {
  const u = new UpdateChecker({ settingsPath: tmpAyar(), currentVersion: '0.5.6' });
  assert.strictEqual(u.currentVersion, '0.5.6');
  assert.strictEqual(u.status().currentVersion, '0.5.6');
});

test('currentVersion fonksiyon olarak verilebilir ve HER OKUMADA yeniden hesaplanır', () => {
  let etkin = '0.5.6';
  const u = new UpdateChecker({ settingsPath: tmpAyar(), currentVersion: () => etkin });
  assert.strictEqual(u.currentVersion, '0.5.6');

  etkin = '0.5.7';                       // delta oturum ortasında uygulandı
  assert.strictEqual(u.currentVersion, '0.5.7',
    'sürüm önbelleğe alınmamalı — yeniden başlatmayı beklemeden tazelenmeli');
  assert.strictEqual(u.status().currentVersion, '0.5.7');
});

test('🔴 REGRESYON: delta uygulanmış sürüm YENİDEN önerilmez', () => {
  // Sahadaki tam senaryo: paket 0.5.6, delta 0.5.7 uygulanmış, sunucudaki en
  // yeni de 0.5.7. Eski kod `app.getVersion()` (=0.5.6) ile karşılaştırdığı
  // için sonsuza kadar "yeni sürüm var" diyordu.
  const paket = '0.5.6', uygulanmis = '0.5.7', sunucudaki = '0.5.7';

  assert.strictEqual(etkinSurumSec(paket, uygulanmis), '0.5.7');
  assert.ok(compareVersions(sunucudaki, etkinSurumSec(paket, uygulanmis)) <= 0,
    'delta uygulanmışken aynı sürüm tekrar "yeni" sayılmamalı');

  // Kusurlu davranışın gerçekten kusurlu olduğunu da göster (test kendi
  // kendini kanıtlasın — yoksa "geçti" hiçbir şey söylemez):
  assert.ok(compareVersions(sunucudaki, paket) > 0,
    'paket sürümüyle karşılaştırmak SONSUZ döngü üretir — kusurun kanıtı');
});

test('delta uygulanmışken GERÇEKTEN yeni sürüm hâlâ önerilir', () => {
  // Gürültüyü kısarken sinyali de kısmadığımızı kanıtla.
  assert.ok(compareVersions('0.5.8', etkinSurumSec('0.5.6', '0.5.7')) > 0,
    '0.5.8 çıktığında güncelleme YİNE önerilmeli');
});

test('delta geri alındıysa paket sürümüne dönülür', () => {
  // `geriAl()` durum dosyasını siler → applied() null → etkin sürüm = paket.
  assert.strictEqual(etkinSurumSec('0.5.6', null), '0.5.6');
  assert.ok(compareVersions('0.5.7', etkinSurumSec('0.5.6', null)) > 0,
    'geri alma sonrası güncelleme yeniden önerilebilmeli');
});

test('delta paketten ESKİYSE paket sürümü kazanır', () => {
  // Kullanıcı tam paketi elle indirip kurduysa (0.5.8), diskte kalmış eski
  // bir 0.5.7 overlay'i onu geriye çekmemeli.
  assert.strictEqual(etkinSurumSec('0.5.8', '0.5.7'), '0.5.8');
});

test('bozuk/boş delta sürümü paketi geriye çekmez', () => {
  assert.strictEqual(etkinSurumSec('0.5.6', 'bozuk'), '0.5.6');
  assert.strictEqual(etkinSurumSec('0.5.6', ''), '0.5.6');
});

// ── Ağ yolu: ayar kapalıyken dışarı ÇIKILMAZ (gizlilik sözü) ────────

test('otomatik kontrol kapalıyken ağa çıkılmaz', async () => {
  const u = new UpdateChecker({ settingsPath: tmpAyar(), currentVersion: '0.5.6' });
  u.setEnabled(false);
  const r = await u.check({ manual: false });
  assert.strictEqual(r.skipped, 'disabled',
    'kapalıyken hiçbir istek yapılmamalı — vitrindeki gizlilik sözü bu');
});

test('status() ağ isteği yapmadan cevap verir', () => {
  const u = new UpdateChecker({ settingsPath: tmpAyar(), currentVersion: '0.5.6' });
  const s = u.status();
  assert.strictEqual(typeof s.enabled, 'boolean');
  assert.strictEqual(s.currentVersion, '0.5.6');
  assert.ok('releasesPage' in s);
});
