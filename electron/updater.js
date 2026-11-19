/**
 * Güncelleme denetleyicisi — GitHub Releases'e bakar, YENİ SÜRÜM VARSA HABER VERİR.
 *
 * ⚠️ Mahremiyet sözleşmesi: Yuki'nin vitrin iddiası "bizim sunucumuza hiç bağlanmaz".
 * Bu modül o iddiayı korur:
 *   • VARSAYILAN KAPALI — kullanıcı ⚙ AYAR'dan açana kadar hiçbir ağ isteği yapılmaz.
 *   • Kapalıyken check() ağa ÇIKMADAN {skipped:'disabled'} döner.
 *   • Açıkken bile yalnız GitHub'ın public Releases API'sine gidilir; hiçbir kullanıcı
 *     verisi, kimlik, telemetri gönderilmez (istek gövdesi yok, çerez yok).
 *   • "Şimdi kontrol et" düğmesi tek seferliktir (manual=true) — kullanıcının kendi
 *     eylemi olduğu için ayar kapalıyken de çalışır, ama ayarı açmaz.
 *
 * Neden yerinde otomatik kurulum değil: satılan Windows SKU'ları `zip` hedefi
 * (electron-updater Windows'ta NSIS/MSI ister), Linux tarafı AppImage. Dört SKU'nun
 * ikisinde çalışmayan bir "oto-kurulum" yerine dördünde de çalışan "haber ver +
 * indirme sayfasını aç" tercih edildi. NSIS installer üretilebildiğinde (CI/gerçek
 * Windows) electron-updater bu modülün üstüne eklenebilir — publish yapılandırması
 * builder yml'lerinde hazır.
 */
const fs = require('fs');
const https = require('https');
const path = require('path');
// Kullanıcıya giden hata/sebep metinleri (updater:check → updater-ui.js).
const _et = require('./dil').t;

const REPO = 'ihsandeniz/yuki-oss';
const API_URL = `https://api.github.com/repos/${REPO}/releases/latest`;
const ATOM_URL = `https://github.com/${REPO}/releases.atom`;
const RELEASES_PAGE = `https://github.com/${REPO}/releases/latest`;
const LIST_URL = `https://api.github.com/repos/${REPO}/releases?per_page=10`;
const TIMEOUT_MS = 10000;
const MIN_AUTO_INTERVAL_MS = 24 * 60 * 60 * 1000;   // otomatik kontrol günde en fazla 1

/**
 * KANALLAR — sürüm önce bir kişide denenir, sonra herkese gider.
 *
 * Son iki turdaki kusurları (PLAN sekmesi · boş yanıt · Windows'ta ölü medya
 * kontrolü) **müşteri** buldu; oysa hepsi ilk açılışta görülebilecek şeylerdi.
 * `beta` = geliştiricinin kendi makinesi: ön-yayınları da görür, bekleme uygulanmaz.
 * `stable` = müşteri: yalnız ön-yayın olmayan sürümleri, hem de yayınlanmasının
 * üstünden BEKLEME_SAATI geçtikten sonra görür.
 *
 * ⚠️ Bu bir GÜVENLİK denetimi değil, bir yayılma denetimi. Yaş bilgisi
 * GitHub API'sinden gelir; Atom yedeğinde yoktur ve orada kapı uygulanmaz.
 * Güvenlik, delta-updater.js'teki imza zincirinde.
 */
const KANALLAR = ['stable', 'beta'];
const BEKLEME_SAATI = 24;

const DEFAULTS = { enabled: false, lastCheck: 0, lastSeenVersion: null, channel: 'stable' };

/** "v0.5.0" / "0.5.0-beta.1" → [0,5,0]. Karşılaştırma yalnız sayısal üçlü üzerinden. */
function parseVersion(s) {
  const m = String(s || '').trim().replace(/^v/i, '').match(/^(\d+)\.(\d+)\.(\d+)/);
  return m ? [Number(m[1]), Number(m[2]), Number(m[3])] : null;
}

/** a > b ise 1, a < b ise -1, eşitse 0. Ayrıştırılamayan sürüm → 0 (güncelleme yok say). */
function compareVersions(a, b) {
  const va = parseVersion(a);
  const vb = parseVersion(b);
  if (!va || !vb) return 0;
  for (let i = 0; i < 3; i++) {
    if (va[i] > vb[i]) return 1;
    if (va[i] < vb[i]) return -1;
  }
  return 0;
}

function httpsGetJson(url, { accept = 'application/vnd.github+json' } = {}) {
  return new Promise((resolve, reject) => {
    const req = https.get(
      url,
      { headers: { 'User-Agent': 'Yuki-UpdateChecker', Accept: accept } },
      (res) => {
        if (res.statusCode >= 300 && res.statusCode < 400 && res.headers.location) {
          res.resume();
          return resolve(httpsGetJson(res.headers.location, { accept }));
        }
        if (res.statusCode !== 200) {
          res.resume();
          return reject(new Error(`HTTP ${res.statusCode}`));
        }
        let body = '';
        res.setEncoding('utf8');
        res.on('data', (c) => { body += c; });
        res.on('end', () => resolve(body));
      }
    );
    req.setTimeout(TIMEOUT_MS, () => req.destroy(new Error(_et('guncel.surum-zaman-asimi'))));
    req.on('error', reject);
  });
}

class UpdateChecker {
  /**
   * @param {string} settingsPath  userData altında updater.json yolu
   * @param {string|function(): string} currentVersion  ETKİN sürüm — sabit değer
   *   ya da her okumada yeniden hesaplayan bir fonksiyon.
   *
   * 🔴 2026-08-02 saha kusuru — neden fonksiyon olabiliyor:
   *   Burası `app.getVersion()` ile besleniyordu; o da ASAR içindeki **paket**
   *   sürümünü döndürür. Delta güncelleme uygulandığında paket sürümü DEĞİŞMEZ
   *   (zaten değişmemesi delta'nın tanımı) → çalışan sürüm v0.5.7 olduğu hâlde
   *   karşılaştırma hep v0.5.6'ya bakıyordu ve `0.5.7 > 0.5.6` sonsuza kadar
   *   doğru kalıyordu. Kullanıcı güncelliyor, kapatıp açıyor, panel yine
   *   "ŞİMDİ GÜNCELLE" diyor — güncelleme hiç **bitmiyordu**.
   *   İronisi: panel çalışan sürümü zaten DOĞRU gösteriyordu (delta durumunu
   *   ayrıca okuyarak); yalnızca *karşılaştırma* başka bir kaynaktan besleniyordu.
   *   Ders: "hangi sürümdeyim" sorusunun tek bir cevabı olmalı — iki kaynak
   *   varsa er geç ayrışırlar.
   */
  constructor({ settingsPath, currentVersion }) {
    this.settingsPath = settingsPath;
    this._surum = typeof currentVersion === 'function'
      ? currentVersion
      : () => currentVersion;
    this._cache = null;
  }

  /** Karşılaştırmada ve panelde kullanılacak ETKİN sürüm. */
  get currentVersion() {
    try { return this._surum(); } catch (_) { return undefined; }
  }

  settings() {
    if (this._cache) return this._cache;
    let stored = {};
    try {
      stored = JSON.parse(fs.readFileSync(this.settingsPath, 'utf8'));
    } catch (_) { /* dosya yok / bozuk → varsayılan */ }
    this._cache = { ...DEFAULTS, ...stored };
    return this._cache;
  }

  _save(patch) {
    const next = { ...this.settings(), ...patch };
    this._cache = next;
    try {
      fs.mkdirSync(path.dirname(this.settingsPath), { recursive: true });
      fs.writeFileSync(this.settingsPath, JSON.stringify(next, null, 2), 'utf8');
    } catch (_) { /* yazılamıyorsa bellekte kalsın, çökme sebebi değil */ }
    return next;
  }

  setEnabled(enabled) {
    return this._save({ enabled: !!enabled });
  }

  /** 'stable' | 'beta'. Bilinmeyen değer sessizce yutulmaz, reddedilir. */
  setChannel(channel) {
    if (!KANALLAR.includes(channel)) {
      throw new Error(_et('guncel.kanal-bilinmeyen', { kanal: channel, gecerli: KANALLAR.join(', ') }));
    }
    return this._save({ channel });
  }

  /** Kullanıcıya gösterilecek durum — ağ isteği YAPMAZ. */
  status() {
    const s = this.settings();
    return {
      enabled: s.enabled,
      currentVersion: this.currentVersion,
      lastCheck: s.lastCheck,
      lastSeenVersion: s.lastSeenVersion,
      channel: s.channel || 'stable',
      releasesPage: RELEASES_PAGE,
    };
  }

  /**
   * Yeni sürüm var mı?
   * @param {boolean} manual  kullanıcı düğmeye bastıysa true (ayar kapalıyken de çalışır)
   */
  async check({ manual = false } = {}) {
    const s = this.settings();
    if (!manual) {
      if (!s.enabled) return { ok: true, skipped: 'disabled' };          // ← ağa ÇIKMAZ
      if (Date.now() - (s.lastCheck || 0) < MIN_AUTO_INTERVAL_MS) {
        return { ok: true, skipped: 'throttled' };
      }
    }

    const kanal = s.channel || 'stable';
    let latest = null;
    let yayinTarihi = null;
    try {
      if (kanal === 'beta') {
        // Ön-yayınlar `/releases/latest`'te GÖRÜNMEZ — liste ucu şart.
        const liste = JSON.parse(await httpsGetJson(LIST_URL))
          .filter((r) => !r.draft)
          .sort((a, b) => new Date(b.published_at || 0) - new Date(a.published_at || 0));
        if (liste.length) { latest = liste[0].tag_name; yayinTarihi = liste[0].published_at; }
      } else {
        const r = JSON.parse(await httpsGetJson(API_URL));
        latest = r.tag_name;
        yayinTarihi = r.published_at;
      }
    } catch (apiErr) {
      // API kotası dolmuş olabilir (kimliksiz istek saatte 60) → Atom yedeği.
      try {
        const atom = await httpsGetJson(ATOM_URL, { accept: 'application/atom+xml' });
        const m = atom.match(/<title>\s*([^<]*?v?\d+\.\d+\.\d+[^<]*?)\s*<\/title>/i);
        latest = m ? (m[1].match(/v?\d+\.\d+\.\d+/) || [null])[0] : null;
      } catch (atomErr) {
        return { ok: false, error: _et('guncel.surum-alinamadi', { hata: apiErr.message }) };
      }
    }
    if (!latest) return { ok: false, error: _et('guncel.surum-okunamadi') };

    this._save({ lastCheck: Date.now(), lastSeenVersion: latest });
    let newer = compareVersions(latest, this.currentVersion) > 0;

    // Yayılma kapısı: stable kanalda taze sürüm bekletilir. Kullanıcı DÜĞMEYE
    // BASTIYSA (manual) bekletilmez — kendi isteğiyle öne geçmek hakkı.
    let bekliyor = false;
    if (newer && !manual && kanal === 'stable' && yayinTarihi) {
      const saat = (Date.now() - new Date(yayinTarihi).getTime()) / 3600000;
      if (saat < BEKLEME_SAATI) { bekliyor = true; newer = false; }
    }

    return {
      ok: true,
      updateAvailable: newer,
      channel: kanal,
      ...(bekliyor ? { pending: true, reason: _et('guncel.bekleme', { saat: BEKLEME_SAATI }) } : {}),
      currentVersion: this.currentVersion,
      latestVersion: String(latest).replace(/^v/i, ''),
      releasesPage: RELEASES_PAGE,
    };
  }
}

/**
 * ETKİN sürüm — "hangi sürümdeyim?" sorusunun TEK cevabı.
 *
 * Delta güncelleme paket sürümünü değiştirmez (değiştirmemesi delta'nın tanımı),
 * bu yüzden `app.getVersion()` tek başına yanlış cevaptır: uygulama v0.5.7 kodunu
 * çalıştırırken bile v0.5.6 der. Karşılaştırma bu fonksiyondan geçmezse
 * "yeni sürüm var" sonsuza kadar doğru kalır ve güncelleme kullanıcı açısından
 * hiç bitmez (2026-08-02 saha kusuru).
 *
 * Burada duruyor ki `updater.test.js` **gerçekten sevk edilen** mantığı sınasın —
 * testin içinde yeniden yazılan bir kopyayı değil.
 *
 * @param {string} paketSurumu      app.getVersion() — ASAR içindeki sürüm
 * @param {?string} uygulanmisSurum deltaUpdater.applied()?.version (yoksa null)
 */
function etkinSurumSec(paketSurumu, uygulanmisSurum) {
  if (uygulanmisSurum && compareVersions(uygulanmisSurum, paketSurumu) > 0) {
    return uygulanmisSurum;
  }
  return paketSurumu;
}

module.exports = {
  UpdateChecker, compareVersions, parseVersion, etkinSurumSec,
  RELEASES_PAGE, KANALLAR, BEKLEME_SAATI,
};
