// B2 uçtan uca testi — GERÇEK GitHub Releases'e karşı (yuki-oss).
// Electron gerekmez: UpdateChecker saf Node (fs + https).
const os = require('os');
const path = require('path');
const fs = require('fs');
const P = path.join(__dirname, '..', 'electron', 'updater.js');
const { UpdateChecker, compareVersions } = require(P);

const tmp = path.join(os.tmpdir(), 'yuki-upd-test');
fs.rmSync(tmp, { recursive: true, force: true });
const settings = path.join(tmp, 'updater.json');

function assert(cond, msg) {
  console.log((cond ? '✅' : '❌') + '  ' + msg);
  if (!cond) process.exitCode = 1;
}

(async () => {
  console.log('── 1) semver karşılaştırma ──');
  assert(compareVersions('v0.5.0', '0.4.0') === 1, 'v0.5.0 > 0.4.0');
  assert(compareVersions('0.5.0', '0.5.0') === 0, '0.5.0 == 0.5.0');
  assert(compareVersions('0.5.0', '0.5.1') === -1, '0.5.0 < 0.5.1');
  assert(compareVersions('bozuk', '0.5.0') === 0, 'ayrıştırılamayan sürüm → güncelleme yok sayılır');

  console.log('\n── 2) VARSAYILAN KAPALI: ağa çıkmamalı ──');
  const u = new UpdateChecker({ settingsPath: settings, currentVersion: '0.4.0' });
  assert(u.status().enabled === false, 'varsayılan ayar: kapalı');
  const t0 = Date.now();
  const off = await u.check();                       // manual DEĞİL
  const dt = Date.now() - t0;
  assert(off.skipped === 'disabled', 'kapalıyken check() → skipped:disabled');
  assert(dt < 50, `ağ isteği yapılmadı (${dt} ms — HTTP olsaydı yüzlerce ms sürerdi)`);
  assert(!fs.existsSync(settings) || !JSON.parse(fs.readFileSync(settings, 'utf8')).lastCheck,
         'kapalıyken lastCheck yazılmadı');

  console.log('\n── 3) elle kontrol (kapalıyken bile, kullanıcı eylemi) ──');
  const man = await u.check({ manual: true });
  assert(man.ok, 'kontrol başarılı: ' + JSON.stringify(man));
  assert(man.updateAvailable === true, `0.4.0 → v${man.latestVersion} güncelleme BULUNDU`);
  // Sürüm SABİT YAZILMAZ — her yayında testi kırardı. Şekil + mantık doğrulanır.
  assert(/^\d+\.\d+\.\d+/.test(man.latestVersion), `son sürüm semver: ${man.latestVersion}`);
  assert(u.status().enabled === false, 'elle kontrol ayarı AÇMADI (kapalı kaldı)');

  console.log('\n── 4) güncel sürümde "güncelsin" demeli ──');
  // Yayındaki sürümün kendisini kurulu say → "güncelsin" demeli (sürümden bağımsız).
  const u2 = new UpdateChecker({ settingsPath: path.join(tmp, 'b.json'), currentVersion: man.latestVersion });
  const cur = await u2.check({ manual: true });
  assert(cur.ok && cur.updateAvailable === false, `v${man.latestVersion} kurulu → güncelleme yok`);

  console.log('\n── 5) açıp kapatma kalıcı ──');
  u.setEnabled(true);
  const u3 = new UpdateChecker({ settingsPath: settings, currentVersion: '0.4.0' });
  assert(u3.status().enabled === true, 'açık ayar diske yazıldı ve geri okundu');
  const th = await u3.check();       // otomatik: az önce kontrol edildi → throttle
  assert(th.skipped === 'throttled', 'günde 1 kez sınırı çalışıyor');
  u3.setEnabled(false);
  assert(new UpdateChecker({ settingsPath: settings, currentVersion: '0.4.0' }).status().enabled === false,
         'kapatma da kalıcı');

  fs.rmSync(tmp, { recursive: true, force: true });
})();
