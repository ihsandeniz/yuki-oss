// Yerel motor oturum anahtarı (v0.8.1 güvenlik yaması, 2026-10-06).
//
// Motor yalnız 127.0.0.1'de dinliyor ama müşterinin TARAYICISI da aynı makinede: açtığı herhangi bir
// site motora istek atabiliyordu (denetim C1/H1/H3). Artık:
//   ① her açılışta rastgele bir anahtar üretilir → motora `YUKI_OTURUM_ANAHTARI` ile verilir
//   ② aynı anahtar Electron'un KENDİ oturumlarına HttpOnly + SameSite=Strict çerez olarak konur
//   ③ motor (backend/app/yerel_kapi.py) bu makineden gelen her isteği bu çerezle tanır.
// Çerez seçildi çünkü <img>/<video>/<iframe>/WebSocket onu kendiliğinden gönderir: arayüze tek satır
// dokunmadan bütün yollar çalışır. Müşterinin normal tarayıcısında bu çerez yoktur.
//
// Anahtar dosyaya da yazılır (0600): pencere ölüp motor sağ kalırsa (uygulama.js "sağ kalmış motor"
// dalı) yeni pencere o motorun anahtarını buradan okur — yoksa her istek 401 olurdu.
//
// Electron'a doğrudan bağımlı DEĞİL (fs/crypto/oturumlar dışarıdan) → `npm test` Electron'suz koşar.

const CEREZ_ADI = 'yuki_oturum';
const DOSYA_ADI = 'oturum-anahtari';
const ANAHTAR_DESENI = /^[0-9a-f]{64}$/;

/** Yeni anahtar üret ve dosyaya yaz (motoru BİZ başlatıyorsak). */
function yeniAnahtar({ fs, path, crypto, dizin }) {
  const anahtar = crypto.randomBytes(32).toString('hex');
  const dosya = path.join(dizin, DOSYA_ADI);
  try {
    fs.writeFileSync(dosya, anahtar, { mode: 0o600 });
    try { fs.chmodSync(dosya, 0o600); } catch (_) {}   // dosya önceden varsa mode yazılmaz
  } catch (_) { /* yazılamazsa da bu açılış çalışır; yalnız sağ kalan motor yeniden kullanılamaz */ }
  return anahtar;
}

/** Sağ kalmış motorun anahtarını oku. Yoksa/bozuksa null. */
function kayitliAnahtar({ fs, path, dizin }) {
  try {
    const a = String(fs.readFileSync(path.join(dizin, DOSYA_ADI), 'utf8')).trim();
    return ANAHTAR_DESENI.test(a) ? a : null;
  } catch (_) { return null; }
}

/** Çerezi verilen her oturuma koy. Bitince yüklenebilir. Hata yutulmaz → çağıran açılış günlüğüne yazar. */
async function cerezleriKur({ oturumlar, url, anahtar }) {
  const sonuc = [];
  for (const s of oturumlar) {
    if (!s || !s.cookies) continue;
    await s.cookies.set({
      url, name: CEREZ_ADI, value: anahtar,
      httpOnly: true, sameSite: 'strict', secure: false,
      // expirationDate YOK → oturum çerezi: diske düşmez, uygulama kapanınca biter.
    });
    sonuc.push(s);
  }
  return sonuc.length;
}

module.exports = { CEREZ_ADI, DOSYA_ADI, yeniAnahtar, kayitliAnahtar, cerezleriKur };
