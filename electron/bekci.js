'use strict';
/**
 * yuki-bekci entegrasyonu (süreç bekçisi FAZ 5, 2026-10-08).
 *
 * `YUKI_BEKCI=1` iken motor doğrudan değil `resources/bekci/yuki-bekci[.exe]` altında başlar.
 * Bekçi (ayrı Rust programı, `projects/surec-bekcisi`): motor çökerse yeniden kaldırır, asılı
 * kalırsa ya da açılışta donarsa öldürüp yeniden başlatır, kapanışta torunlar dahil bütün ağacı
 * temizler, 8791'de öksüz kalmış eski motorumuzu durdurur. Varsayılan KAPALI; ürüne varsayılan
 * açık gönderme geliştirici onayı.
 *
 * Saf işlevler: dosya sistemi, ortam ve ağ çağrıları enjekte edilir → `bekci.test.js`.
 */
const fs = require('fs');
const path = require('path');

const SAGLIK_URL = 'http://127.0.0.1:8791/health';
const KAPANIS_YOLU = '/api/motor/kapan';   // backend/app/api/motor_api.py
const KAPANIS_URL = 'http://127.0.0.1:8791' + KAPANIS_YOLU;
// İlk 2xx gelmeden bu kadar saniye geçerse motor "açılışta donmuş" sayılır (bekçi `--acilis`).
// Soğuk açılışın sahada görülen en kötüsü ~62 sn (motor-bekle.js); 180 = ~3× pay. Kısa tutulursa
// yavaş diskte sağlıklı bir açılışı öldürür. Asıl işi çökme sonrası yeniden başlatmada: o an
// açılış ekranı yok, donan motoru bekçiden başka gören olmaz.
const ACILIS_SN = 180;

// ── Kapanış süreleri — TEK KAYNAK motorun kendi emniyeti (2026-10-10) ──────────────────
// Motor kapanış isteğini alınca en geç MOTOR_ZORLA_SN sonra kendini `os._exit(0)` ile kapatır
// (backend/app/motor_kapanis.py::ZORLA_SN — `bekci.test.js` iki değeri dosyadan okuyup karşılaştırır).
// Bekleyen taraf bundan KISA beklerse motoru kapanırken zorla öldürür: kapanış işleri yarım kalır,
// çıkış kodu 0 olmaz. Windows CI'da çökme sonrası yeniden kalkmış motor 4 koşunun 2'sinde 12 sn'yi
// aştı (eski bekleme 12 sn'ydi, motor 15). Bu yüzden iki bekleyen de motordan PAY kadar uzun bekler:
//   Electron `kibarKapat` → KAPANIS_BEKLE_MS · bekçi `--bekle` → KAPANIS_BEKLE_SN (varsayılanı 15 = yarış).
// Motor kısaltılmadı: süre kapanış işlerinin (zamanlayıcı, MCP, dosyalar) payıdır; taze motor 1 sn'de çıkar,
// uzun bekleme yalnız takılan kapanışta ödenir ve o zaman da motor kendi isteğiyle (0) çıkar.
const MOTOR_ZORLA_SN = 15;
const KAPANIS_PAY_SN = 3;
const KAPANIS_BEKLE_SN = MOTOR_ZORLA_SN + KAPANIS_PAY_SN;
const KAPANIS_BEKLE_MS = KAPANIS_BEKLE_SN * 1000;

// Bayrak yalnız tam '1' ile açılır. Açıksa ama ikili yoksa/çalıştırılamazsa `kullan:false` + neden
// döner → çağıran eski yola düşer ve nedeni loglar (bekçi yokluğu motoru açılmaz hâle getirmez).
function bekciYolu({ env, platform, resourcesPath, accessSync = fs.accessSync }) {
  if (env.YUKI_BEKCI !== '1') return { kullan: false, neden: null };
  const ad = platform === 'win32' ? 'yuki-bekci.exe' : 'yuki-bekci';
  const yol = path.join(resourcesPath, 'bekci', ad);
  try {
    // AppImage'da +x biti düşebilir — varlık yetmez, çalıştırılabilirlik sorulur.
    accessSync(yol, platform === 'win32' ? fs.constants.F_OK : fs.constants.X_OK);
  } catch (e) {
    return { kullan: false, neden: `bekçi ikilisi çalıştırılamaz (${yol}): ${e.code || e.message}` };
  }
  return { kullan: true, yol };
}

// spawn(komut, args) çifti. Motor komutu `--` sonrasına, dokunulmadan verilir.
function sarmala(bekci, python, pyArgs, logDosyasi) {
  return {
    komut: bekci,
    args: [
      '--yeniden', '--saglik', SAGLIK_URL, '--aralik', '5s', '--acilis', String(ACILIS_SN),
      '--kapanis', KAPANIS_URL, '--bekle', String(KAPANIS_BEKLE_SN), '--log', logDosyasi,
      '--', python, ...pyArgs,
    ],
  };
}

// Bekçinin çıkış kodları (surec-bekcisi/CLAUDE.md) → sözlük anahtarı. Kullanıcıya pencere açılır.
const CIKIS_ANAHTARI = { 70: 'kabuk.bekci-70', 71: 'kabuk.bekci-71', 127: 'kabuk.bekci-127' };
function cikisAnahtari(kod) {
  return CIKIS_ANAHTARI[kod] || null;
}

/**
 * Windows'ta motoru kibarca kapat, olmazsa zorla.
 *
 * Windows'ta SIGTERM yok → bugüne kadar `taskkill /T /F` idi ve motorun kapanış işleri hiç
 * koşmuyordu. Önce motora `POST /api/motor/kapan` (uvicorn'un zarif kapanışı), `sureMs` (varsayılan
 * KAPANIS_BEKLE_MS = motor ZORLA_SN + pay) içinde
 * süreç çıkmazsa çağıran zorla kapatır. Bekçi açıkken de aynı yol: motor 0 koduyla çıkar, bekçi
 * 0'ı "kendi isteğiyle kapandı" sayıp yeniden başlatmaz ve kendisi de çıkar.
 *
 * @returns {Promise<'kibar'|'zorla'>} 'zorla' = çağıran taskkill /F yapmalı
 */
async function kibarKapat({ istekAt, cikisBekle, sureMs = KAPANIS_BEKLE_MS, log = () => {} }) {
  let kod = null;
  try { kod = await istekAt(); } catch (e) { log(`kapanış isteği gitmedi: ${e.message}`); }
  if (!(kod >= 200 && kod < 300)) {
    log(`kapanış isteği reddedildi (${kod}) — zorla`);
    return 'zorla';
  }
  if (await cikisBekle(sureMs)) return 'kibar';
  log(`motor ${Math.round(sureMs / 1000)} sn içinde kapanmadı — zorla`);
  return 'zorla';
}

/**
 * Port sahibini bekçi mi denetlesin? Denetliyorsa Electron "8791 dolu → eski motoru yeniden
 * kullan" dalını ATLAR; bekçi öksüz eski motorumuzu durdurur, başkasınınkine dokunmaz (71).
 * FAZ 6 ( ④, 2026-10-09): Windows'ta da — yuki-bekci `faz6-win-port` ikilisi şart.
 * 🔴 Eski (7b74cd0) Windows ikilisiyle birlikte gitmez: o denetimi "atlandı" diye geçer, motor
 * dolu porta bağlanamaz → çökme döngüsü (70). SURUM bu yüzden aynı dalda güncellenmeli.
 */
function portuBekciDenetler(bekci) {
  return !!(bekci && bekci.kullan);
}

module.exports = {
  bekciYolu, sarmala, cikisAnahtari, kibarKapat, portuBekciDenetler,
  SAGLIK_URL, KAPANIS_YOLU, KAPANIS_URL, ACILIS_SN,
  MOTOR_ZORLA_SN, KAPANIS_PAY_SN, KAPANIS_BEKLE_SN, KAPANIS_BEKLE_MS,
};
