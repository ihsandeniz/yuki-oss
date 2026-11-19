/**
 * Delta güncelleyici — uygulama kodunu ~1,2 MiB'lık imzalı yükle günceller.
 *
 * NEDEN VAR (ölçüm 2026-08-02): iki sürüm arasında paketin 15.584 dosyası aynı
 * kalıyor, gerçekten değişen ~18 dosya. Buna rağmen müşteri her sürümde GitHub'a
 * gidip **440 MiB** indirip zip'i elle açıyordu. Ölçülen gerçek yük 1,20 MiB → 367×.
 *
 * NE GÜNCELLER : `backend/app/**` + `frontend/**` (assets hariç)
 * NE GÜNCELLEMEZ: Python runtime (pybundle), Electron ikilisi, `app.asar`, medya.
 *   Bunlardan biri değiştiyse manifest'in `shell_id`'si tutmaz → tam indirmeye düşer.
 *
 * 🔒 BU BİR UZAKTAN KOD ÇALIŞTIRMA KANALIDIR. Savunma sırası:
 *   1. Manifest **Ed25519** imzalı; public key aşağıda gömülü, private key repo dışı.
 *   2. İmza tutmazsa payload **indirilmez bile**.
 *   3. Payload sha256'sı manifest'tekiyle tutmazsa **diske hiçbir şey yazılmaz**.
 *   4. Çıkarma sırasında her yol sanitize edilir (zip/tar-slip, mutlak yol,
 *      sürücü harfi, sembolik bağ → hepsi reddedilir).
 *   5. Çıkarma **geçici dizine**, doğrulama bittikten sonra atomik yer değiştirme.
 *   Anahtar lisans anahtarından AYRI: lisans sızıntısı = bedava Pro,
 *   güncelleme sızıntısı = her müşteride kod çalıştırma. Ayrı tutulmalı.
 *
 * ⚠️ Mahremiyet sözleşmesi korunur: varsayılan KAPALI, kapalıyken ağa hiç çıkmaz,
 *    yalnız GitHub'ın public release uçlarına gidilir, hiçbir kullanıcı verisi gitmez.
 */
const crypto = require('crypto');
const fs = require('fs');
const https = require('https');
const path = require('path');
const zlib = require('zlib');
const { compareVersions } = require('./updater');
// Kullanıcıya giden hata/sebep metinleri (delta:apply → updater-ui.js). Günlük satırları çevrilmez.
const _et = require('./dil').t;

// ── Güncelleme imza anahtarı (Ed25519 public, 32 bayt hex) ──────────────────
// `scripts/update_payload.py keygen` ile üretildi. Private eşi ~/.alice-issuer/
// içinde, repoya ASLA girmez. Bunu değiştirmek yayınlanmış tüm yükleri geçersiz kılar.
const UPDATE_PUBLIC_KEY = 'a4e3a2520c097bc6cfeb8edadfa9e606176ff166007610b1d0a66a4bb9d08d90';

const REPO = 'ihsandeniz/yuki-oss';
const TIMEOUT_MS = 30000;
const MAX_PAYLOAD_BYTES = 64 * 1024 * 1024;   // 1,2 MiB bekleniyor; 64 MiB sert tavan
// Medya yükü ayrı ve büyük (ölçüldü 2026-08-08: 24 MiB sıkışık / 31,5 MiB ham).
// Kod yükünün tavanını ona göre büyütmek yanlış olurdu — kod yükü küçük kalmalı
// ki şişen bir "kod" yükü fark edilsin. İki ayrı tavan, iki ayrı beklenti.
const MAX_MEDIA_BYTES = 256 * 1024 * 1024;
// Tek dosya tavanı (2026-09-24): 16 MiB idi, `frontend/assets/characters/
// yuki3d.vrm` (18.235.040 bayt = 17,39 MiB) medya yükünde bunu geçiyor. Müşteriyi
// henüz vurmadı (media_id v0.6.0'dan beri sabit, medya yükü inmiyor) ama medya ilk
// değiştiği sürümde delta "Girdi çok büyük" diye DÜŞERDİ. Ölçüldü: gerçek v0.7.0
// medya yükü (cmd_build çıktısı, 24 dosya / 23,6 MiB) downloadAndApply'dan 16 MiB'de
// reddedildi, 32 MiB'de uygulandı, açılan VRM sha256'sı kaynakla birebir.
// Bu bir güvenlik tavanıdır (tek girdinin tüm yükü yutmasını önler) — kaldırılmaz,
// yalnız gerçek en büyük dosyanın üstüne yükseltilir. 32 MiB = en büyük dosyanın 1,84×'i.
// ⚠️ Bu sınır yalnız YENİ yayınlanan updater.js'i olan kurulumları kurtarır —
// güncellemeyi UYGULAYAN her zaman kurulu (eski) sürümdür. Medya değişmeden
// önce en az bir sürüm bu yeni sınırla (delta-only) çıkmalı, yoksa eski
// kurulumlar yine reddeder (bkz. CLAUDE.md § Delta Güncelleme, shell_id dersi).
const MAX_ENTRY_BYTES = 32 * 1024 * 1024;

// Ed25519 ham public key → SPKI DER (Node `createPublicKey` bunu ister)
const SPKI_PREFIX = Buffer.from('302a300506032b6570032100', 'hex');

function ed25519PublicKey(hex) {
  return crypto.createPublicKey({
    key: Buffer.concat([SPKI_PREFIX, Buffer.from(hex, 'hex')]),
    format: 'der',
    type: 'spki',
  });
}

/**
 * İmzalanan baytlar — Python `_kanonik()` ile BİREBİR aynı olmalı:
 * anahtarlar sıralı, ayraç boşluksuz, ASCII dışı karakter yok.
 * (Builder manifest alanlarının ASCII olduğunu doğrular; burada da varsayıyoruz.)
 */
function canonical(obj) {
  const keys = Object.keys(obj).sort();
  const parts = keys.map((k) => JSON.stringify(k) + ':' + JSON.stringify(obj[k]));
  return Buffer.from('{' + parts.join(',') + '}', 'utf8');
}

function b64urlDecode(s) {
  return Buffer.from(s.replace(/-/g, '+').replace(/_/g, '/'), 'base64');
}

function httpsGet(url, { maxBytes = MAX_PAYLOAD_BYTES, accept } = {}) {
  return new Promise((resolve, reject) => {
    const req = https.get(url, {
      headers: { 'User-Agent': 'Yuki-Updater', ...(accept ? { Accept: accept } : {}) },
      timeout: TIMEOUT_MS,
    }, (res) => {
      if (res.statusCode >= 300 && res.statusCode < 400 && res.headers.location) {
        res.resume();
        return resolve(httpsGet(res.headers.location, { maxBytes, accept }));
      }
      if (res.statusCode !== 200) {
        res.resume();
        return reject(new Error(`HTTP ${res.statusCode}`));
      }
      const parcalar = [];
      let toplam = 0;
      res.on('data', (c) => {
        toplam += c.length;
        if (toplam > maxBytes) {          // kaynak tükenmesine karşı sert tavan
          req.destroy();
          return reject(new Error(_et('guncel.yanit-buyuk')));
        }
        parcalar.push(c);
      });
      res.on('end', () => resolve(Buffer.concat(parcalar)));
    });
    req.on('timeout', () => { req.destroy(); reject(new Error(_et('guncel.zaman-asimi'))); });
    req.on('error', reject);
  });
}

// ── tar.gz okuyucu (bağımlılıksız) ──────────────────────────────────────────
// Format bilinçli olarak tar: sabit 512 baytlık başlık, zip'in merkezi-dizin/EOCD
// kenar durumlarına göre çok daha küçük bir hata yüzeyi. Yalnız düz dosya kabul
// edilir — sembolik bağ, sert bağ, aygıt, dizin girişi hepsi reddedilir.
function tarOku(buf) {
  const girisler = [];
  let off = 0;
  while (off + 512 <= buf.length) {
    const bas = buf.subarray(off, off + 512);
    if (bas.every((b) => b === 0)) break;                 // bitiş bloğu

    const ad = bas.subarray(0, 100).toString('utf8').replace(/\0.*$/, '');
    const boyut = parseInt(bas.subarray(124, 136).toString('ascii').replace(/\0.*$/, '').trim(), 8) || 0;
    const tip = String.fromCharCode(bas[156]) || '0';
    const onek = bas.subarray(345, 500).toString('utf8').replace(/\0.*$/, '');
    const tamAd = onek ? `${onek}/${ad}` : ad;

    // başlık sağlaması — bozuk arşivde rastgele offset'e atlamayalım
    const beklenen = parseInt(bas.subarray(148, 156).toString('ascii').replace(/\0.*$/, '').trim(), 8);
    let toplam = 0;
    for (let i = 0; i < 512; i++) toplam += (i >= 148 && i < 156) ? 32 : bas[i];
    if (!Number.isNaN(beklenen) && toplam !== beklenen) {
      throw new Error(_et('guncel.tar-saglama', { ad: tamAd || _et('guncel.adsiz') }));
    }

    off += 512;
    if (tip === '0' || tip === '\0') {
      if (boyut > MAX_ENTRY_BYTES) throw new Error(_et('guncel.girdi-buyuk', { ad: tamAd }));
      girisler.push({ ad: tamAd, veri: buf.subarray(off, off + boyut) });
    } else if (tip !== '5') {
      // 5 = dizin (yok sayılır, biz kendimiz oluşturuyoruz)
      throw new Error(_et('guncel.tar-tip', { tip, ad: tamAd }));
    }
    off += Math.ceil(boyut / 512) * 512;
  }
  return girisler;
}

/**
 * Arşiv içi yolu güvenli hâle getir. Reddedilenler:
 *   mutlak yol · `..` bileşeni · Windows sürücü harfi · ters bölü · NUL ·
 *   izinli köklerin dışı. Tek bir kaçak, kullanıcının diskine yazma demek.
 */
const IZINLI_KOKLER = ['backend/app/', 'frontend/', 'electron/'];

/**
 * Yükün ASLA yazamayacağı dosyalar — izinli kökün içinde olsalar bile.
 *
 * `electron/main.js` **önyükleyicidir**: overlay'i kullanıp kullanmayacağına ve
 * bozuk bir güncellemeyi geri alıp almayacağına o karar verir. Kendisi
 * güncellenebilir olsaydı, bozuk bir yük hem uygulamayı kırar hem de kurtarma
 * yolunu ortadan kaldırırdı — geri dönüşü olmayan tek hata sınıfı. ASAR'da kalır.
 *
 * `electron/shell-id.txt` kabuğun kimliğidir; yük onu değiştirebilseydi uyumsuz
 * bir yük kendini "uyumlu" ilan edebilirdi.
 */
const YASAK_YOLLAR = new Set([
  'electron/main.js',        // önyükleyici
  'electron/onyukleme.js',   // önyükleme kararı + geri alma — kurtarma yolu
  'electron/shell-id.txt',   // kabuğun kimliği
  // Medyanın kimliği. Yük bunu değiştirebilseydi, eski medyalı bir kurulumu
  // "medyan güncel" diye işaretleyip 33 MB'lık indirmeyi atlatabilirdi —
  // kullanıcı güncellendiğini sanır, görseller eski kalırdı. (Uzantısı `.txt`
  // olduğu için üretici zaten yüke koymuyor; bu ikinci savunma hattı.)
  'electron/media-id.txt',
]);

function guvenliYol(hedefKok, arsivYolu) {
  if (!arsivYolu || arsivYolu.includes('\0')) return null;
  if (arsivYolu.includes('\\')) return null;
  if (path.posix.isAbsolute(arsivYolu)) return null;
  if (/^[a-zA-Z]:/.test(arsivYolu)) return null;
  if (arsivYolu.split('/').some((s) => s === '..' || s === '.')) return null;
  if (!IZINLI_KOKLER.some((k) => arsivYolu.startsWith(k))) return null;
  if (YASAK_YOLLAR.has(arsivYolu)) return null;

  const tam = path.resolve(hedefKok, arsivYolu);
  const kok = path.resolve(hedefKok);
  // path.relative ile son kontrol — yukarıdakiler atlansa bile kaçış yakalanır
  const rel = path.relative(kok, tam);
  if (rel.startsWith('..') || path.isAbsolute(rel)) return null;
  return tam;
}

// ── Güncelleyici ────────────────────────────────────────────────────────────

class DeltaUpdater {
  /**
   * @param {object} o
   * @param {string} o.userDataDir  yazılabilir kök (app.getPath('userData'))
   * @param {string} o.shellId      paketin kabuk parmak izi (electron/shell-id.txt)
   * @param {string} o.currentVersion  çalışan sürüm (overlay varsa onunki)
   */
  constructor({ userDataDir, shellId, currentVersion, packagedBackendDir, gunluk,
                packagedMediaId }) {
    this.updatesDir = path.join(userDataDir, 'updates');
    this.statePath = path.join(this.updatesDir, 'current.json');
    // Medya katmanı: sürümsüz, overlay'den bağımsız (bkz. _medyaUygula)
    this.medyaDir = path.join(this.updatesDir, 'media');
    this.medyaStatePath = path.join(this.updatesDir, 'media.json');
    this.packagedMediaId = packagedMediaId || null;
    this.shellId = shellId;
    this.currentVersion = currentVersion;
    this.packagedBackendDir = packagedBackendDir;
    // Güncelleme günlüğü (eklemeli). Verilmezse sessizce yutulmaz, konsola gider.
    this.gunluk = gunluk || ((s) => console.error('[delta]', s));
  }

  /** Uygulanmış sürümün imzalı manifest'inin yolu. */
  _manifestYolu(version) {
    return path.join(this.updatesDir, `${version}.manifest.json`);
  }

  /**
   * Overlay'in şu ANDAKİ dosya ağacının parmak izi.
   *
   * Yalnız yükün taşıdığı kökler taranır — `_kardesleriAynala()` ile paketten
   * bağlanan kardeşler (`backend/mcp_servers.json`, `backend/skills/`) yükün
   * parçası değildir, onları da saymak kökü daima tutmaz hâle getirirdi.
   *
   * Ekleme/silme/değiştirme üçü de yakalanır: küme tarandığı için eklenen dosya
   * kökü değiştirir, silinen dosya da.
   */
  agacKoku(overlayDir, { medya = false } = {}) {
    const satirlar = [];
    const gez = (mutlak, goreli) => {
      let girdiler;
      try { girdiler = fs.readdirSync(mutlak, { withFileTypes: true }); } catch (_) { return; }
      for (const g of girdiler.sort((a, b) => (a.name < b.name ? -1 : 1))) {
        const alt = path.join(mutlak, g.name);
        const altGoreli = `${goreli}/${g.name}`;
        // 🔴 Medya AYRI yükle gelir ve AYRI kökle (media_root) doğrulanır.
        // Kod kökü onu da sayarsa: kod yükü uygulanır → files_root hesaplanır →
        // içinde medya var (ya da yok) → manifest'le TUTMAZ → sapasağlam overlay
        // her açılışta reddedilirdi. İki yük, iki kök; karıştırılamaz.
        if (!medya && altGoreli === 'frontend/assets') continue;
        // Sembolik bağ izlenmez: overlay dışına işaret eden bir bağ, taranan
        // içerikle çalıştırılan içeriğin ayrışmasına yol açardı.
        if (g.isSymbolicLink()) { satirlar.push(`${altGoreli}:BAĞ`); continue; }
        if (g.isDirectory()) gez(alt, altGoreli);
        else if (g.isFile()) {
          const sha = crypto.createHash('sha256').update(fs.readFileSync(alt)).digest('hex');
          satirlar.push(`${altGoreli}:${sha}`);
        }
      }
    };
    for (const kok of (medya ? ['frontend/assets'] : ['backend/app', 'frontend', 'electron'])) {
      const mutlak = path.join(overlayDir, ...kok.split('/'));
      if (fs.existsSync(mutlak)) gez(mutlak, kok);
    }
    satirlar.sort();
    return crypto.createHash('sha256')
      .update(satirlar.map((s) => s + '\n').join(''))
      .digest('hex');
  }

  /**
   * Açılışta çalışır: overlay hâlâ indirdiğimiz şey mi?
   *
   * 🔴 NEDEN GEREKLİ: imza ve sha256 yalnız **indirme anını** doğruluyordu.
   * Overlay `userData/updates/` altında, kullanıcının (ve kullanıcı olarak çalışan
   * her şeyin) yazabildiği bir yerde duruyor ve her açılışta oradan **kod
   * çalıştırılıyor**. İndirmeden sonra değişen tek bir dosyayı hiçbir şey
   * yakalamıyordu — bu, imzalı bir kanalın sağladığı güveni sessizce boşa
   * düşüren bir açıktı.
   *
   * @returns {{saglam: boolean, sebep?: string}}
   */
  butunlukDogrula(version, overlayDir) {
    let ham;
    try {
      ham = fs.readFileSync(this._manifestYolu(version), 'utf8');
    } catch (_) {
      // v0.5.8 öncesi uygulanmış overlay'lerin saklı manifest'i yok. Bunlar
      // zaten doğrulanmış olarak yazıldı; denetlenemez ama sahte de değil.
      return { saglam: true, sebep: 'manifest saklanmamış (eski overlay)' };
    }
    let man;
    try { man = JSON.parse(ham); } catch (_) { return { saglam: false, sebep: 'saklı manifest bozuk' }; }

    const sig = man.sig;
    delete man.sig;
    if (typeof sig !== 'string'
        || !crypto.verify(null, canonical(man), ed25519PublicKey(UPDATE_PUBLIC_KEY), b64urlDecode(sig))) {
      return { saglam: false, sebep: 'saklı manifest imzası geçersiz' };
    }
    if (!man.files_root) return { saglam: false, sebep: 'manifest bütünlük kökü taşımıyor' };

    const kok = this.agacKoku(overlayDir);
    if (kok !== man.files_root) {
      return { saglam: false, sebep: `dosya ağacı değişmiş (${kok.slice(0, 12)}… ≠ ${man.files_root.slice(0, 12)}…)` };
    }
    return { saglam: true };
  }

  /**
   * Overlay'in `backend/` kökünü paketlenmiş kökle aynala.
   *
   * 🔴 NEDEN GEREKLİ (ölçüldü 2026-08-02, overlay uçtan uca koşulurken):
   * `app/` içindeki kod kardeş dosyaları `__file__`'a göre bulur —
   * `mcp_client` → `backend/mcp_servers.json`, `skill_registry` → `backend/skills/`,
   * `planner`/`live_portrait` → `backend/`. Overlay'de yalnız `app/` olduğu için
   * bunlar bulunamıyordu ve **çökme değil, sessiz kapanma** üretiyordu:
   *     "MCP: etkin sunucu yok" · "skill kaydı: skills/ boş veya yok"
   * Yani güncelleme sonrası iki özellik ölür, log INFO seviyesinde geçer,
   * kimse fark etmez. Bu ürünün defalarca ısırıldığı hata sınıfı.
   *
   * Çözüm: `app` DIŞINDAKİ her girdi paketlenmiş kökten aynalanır.
   * Dizinler bağ (Windows'ta `junction` → yönetici yetkisi İSTEMEZ), dosyalar
   * kopya (hepsi küçük). Listeyi elle tutmuyoruz — paketlenmiş dizin ne
   * içeriyorsa o aynalanır, böylece ileride eklenen bir kardeş dosya unutulmaz.
   */
  _kardesleriAynala(overlayBackendDir) {
    const kaynak = this.packagedBackendDir;
    if (!kaynak || !fs.existsSync(kaynak)) {
      throw new Error(_et('guncel.paket-backend-yok'));
    }
    const atlanan = [];
    for (const ad of fs.readdirSync(kaynak)) {
      if (ad === 'app') continue;                                  // overlay sağlıyor
      const hedef = path.join(overlayBackendDir, ad);
      if (fs.existsSync(hedef)) continue;                          // yük zaten getirmiş
      const src = path.join(kaynak, ad);
      try {
        const st = fs.statSync(src);
        if (st.isDirectory()) {
          fs.symlinkSync(src, hedef, process.platform === 'win32' ? 'junction' : 'dir');
        } else {
          fs.copyFileSync(src, hedef);
        }
      } catch (e) {
        atlanan.push(`${ad} (${e.code || e.message})`);
      }
    }
    // Sessiz kapanmayı önlemek bu fonksiyonun tek amacı — aynalama başarısızsa
    // bunu yutmak, çözdüğümüz hatanın aynısını üretmek olurdu.
    const kritik = ['mcp_servers.json', 'skills', 'run.py'];
    const eksik = kritik.filter((k) => fs.existsSync(path.join(kaynak, k))
                                    && !fs.existsSync(path.join(overlayBackendDir, k)));
    if (eksik.length) {
      throw new Error(_et('guncel.overlay-eksik', { eksik: eksik.join(', ') }));
    }
    return { atlanan };
  }

  // ── Medya katmanı (2026-08-08) ───────────────────────────────────────────
  //
  // Medya (33 MB görsel/klip) kod yükünün dışında, KENDİ sürümsüz katmanında
  // durur: `updates/media/`. Sebebi yukarıda (`downloadAndApply`) yazılı —
  // sürüme bağlansaydı medyanın değişmediği bir sonraki güncellemede kaybolurdu.
  //
  // Statik sunucu zinciri: overlay/frontend → **bu katman** → paketlenmiş frontend.
  // (`uygulama.js` bu dizini `YUKI_MEDIA_DIR` ile backend'e verir.)

  /** Kurulu medyanın kimliği: indirilmiş katman varsa onunki, yoksa paketinki. */
  etkinMediaId() {
    try {
      const s = JSON.parse(fs.readFileSync(this.medyaStatePath, 'utf8'));
      if (s && s.mediaId && fs.existsSync(this.medyaDir)) return s.mediaId;
    } catch (_) { /* katman yok → paketinki geçerli */ }
    return this.packagedMediaId || null;
  }

  /** İndirilmiş medya katmanının frontend kökü (yoksa null). */
  medyaKoku() {
    try {
      const s = JSON.parse(fs.readFileSync(this.medyaStatePath, 'utf8'));
      const kok = path.join(this.medyaDir, 'frontend');
      if (s && s.mediaId && fs.existsSync(path.join(kok, 'assets'))) return kok;
    } catch (_) { /* yok */ }
    return null;
  }

  _medyaUygula(medyaPayload, man) {
    const girisler = tarOku(zlib.gunzipSync(medyaPayload));
    if (girisler.length !== man.media_file_count) {
      throw new Error(_et('guncel.medya-sayi', { bulunan: girisler.length, beklenen: man.media_file_count }));
    }
    fs.mkdirSync(this.updatesDir, { recursive: true });
    const gecici = path.join(this.updatesDir, `.media-staging-${process.pid}`);
    fs.rmSync(gecici, { recursive: true, force: true });
    fs.mkdirSync(gecici, { recursive: true });

    try {
      for (const g of girisler) {
        // Yol güvenliği kod yüküyle AYNI kapıdan geçer; ayrıca medya yükünün
        // `frontend/assets/` dışına yazmasının hiçbir meşru sebebi yok.
        if (!g.ad.startsWith('frontend/assets/')) {
          throw new Error(_et('guncel.medya-kok-disi', { ad: g.ad }));
        }
        const hedef = guvenliYol(gecici, g.ad);
        if (!hedef) throw new Error(_et('guncel.medya-yol', { ad: g.ad }));
        fs.mkdirSync(path.dirname(hedef), { recursive: true });
        fs.writeFileSync(hedef, g.veri);
      }

      // Yazılan ağaç, imzalanan ağaçla birebir aynı mı? (kod yükündeki denetimin
      // aynısı — `media_root` manifest'in içinde olduğu için İMZALIDIR.)
      const mKok = this.agacKoku(gecici, { medya: true });
      if (mKok !== man.media_root) {
        throw new Error(_et('guncel.medya-agac', {
          bulunan: mKok.slice(0, 12), beklenen: String(man.media_root).slice(0, 12) }));
      }

      fs.rmSync(this.medyaDir, { recursive: true, force: true });
      fs.renameSync(gecici, this.medyaDir);
      fs.writeFileSync(this.medyaStatePath, JSON.stringify({
        mediaId: man.media_id, root: man.media_root,
        version: man.version, appliedAt: Date.now(),
      }, null, 2), 'utf8');
      this.gunluk(`MEDYA UYGULANDI ${man.media_id} — ${girisler.length} dosya, `
                + `${(medyaPayload.length / 1048576).toFixed(1)} MiB`);
    } catch (e) {
      fs.rmSync(gecici, { recursive: true, force: true });
      throw e;
    }
  }

  /** Uygulanmış güncelleme (yoksa null). main.js açılışta bunu okur. */
  applied() {
    try {
      const s = JSON.parse(fs.readFileSync(this.statePath, 'utf8'));
      if (!s.version || !s.dir) return null;
      if (!fs.existsSync(path.join(s.dir, 'backend', 'app', 'main.py'))) return null;
      return s;
    } catch (_) { return null; }
  }

  /** Sunucudaki imzalı manifest — doğrulanmadan hiçbir alanına GÜVENİLMEZ. */
  async fetchManifest(version) {
    const url = `https://github.com/${REPO}/releases/download/v${version}/yuki-update-${version}.json`;
    const raw = await httpsGet(url, { maxBytes: 256 * 1024 });
    let man;
    try { man = JSON.parse(raw.toString('utf8')); }
    catch (e) { throw new Error(_et('guncel.manifest-bozuk')); }

    const sig = man.sig;
    if (typeof sig !== 'string') throw new Error(_et('guncel.manifest-imzasiz'));
    delete man.sig;

    const ok = crypto.verify(null, canonical(man), ed25519PublicKey(UPDATE_PUBLIC_KEY),
                             b64urlDecode(sig));
    if (!ok) throw new Error(_et('guncel.manifest-imza'));

    if (man.schema !== 1) throw new Error(_et('guncel.manifest-sema', { sema: man.schema }));
    if (man.product !== 'yuki') throw new Error(_et('guncel.manifest-urun'));
    if (man.version !== version) throw new Error(_et('guncel.manifest-surum'));
    if (!man.files_root) {
      // İsteğe bağlı BIRAKILMADI: "kapı varsa hep kapalı" kuralı. Bu alan imzanın
      // içinde olduğu için saldırgan söküp atamaz; yoksa manifest gerçekten eskidir
      // ve bu istemci yalnız KENDİNDEN YENİ sürümleri uygular (düşürme koruması) →
      // pratikte hep dolu gelir.
      throw new Error(_et('guncel.manifest-kok'));
    }
    return { man, ham: raw.toString('utf8') };
  }

  /**
   * Yükü indir, doğrula, uygula.
   * Hiçbir aşamada doğrulama atlanmaz; hata olursa geçici dizin silinir ve
   * mevcut kurulum **hiç dokunulmamış** kalır.
   */
  async downloadAndApply(version, onProgress = () => {}) {
    onProgress({ asama: 'manifest' });
    const { man, ham: manifestHam } = await this.fetchManifest(version);

    // ── Sürüm düşürme koruması ──────────────────────────────────────────────
    // İmzalı ESKİ bir manifest tekrar oynatılabilir (yeniden yayınlanmış bir
    // etiket, bayat bir ayna, ortadaki bir vekil). Bu, kapatılmış bir açığı geri
    // getirmenin en ucuz yoludur ve imza kontrolünden geçer — çünkü sahte değil,
    // sadece eskidir. Kurulu olandan yeni olmayan hiçbir sürüm uygulanmaz.
    const kurulu = (this.applied() || {}).version || this.currentVersion;
    if (kurulu && compareVersions(version, kurulu) <= 0) {
      this.gunluk(`REDDEDİLDİ: v${version} kurulu v${kurulu}'den yeni değil (düşürme koruması)`);
      return {
        ok: false,
        reason: _et('guncel.yeni-degil', { surum: kurulu }),
      };
    }

    if (man.shell_id !== this.shellId) {
      this.gunluk(`shell_id uyuşmuyor (yük ${man.shell_id} ≠ kurulum ${this.shellId}) → tam paket gerekli`);
      return {
        ok: false,
        requiresFull: true,
        reason: _et('guncel.cekirdek-degisti'),
      };
    }

    // ── Medya gerekiyor mu? ───────────────────────────────────────────────
    // Kurulu medya, manifest'in istediğiyle aynıysa 33 MB'ı hiç indirmeyiz.
    // Farklıysa medya yükü de inmeli — YOKSA tam pakete düşeriz, çünkü yeni kod
    // yeni medyayı bekliyor olabilir (yeni bir karakter görseli, yeni bir klip)
    // ve eksik medyayla çalışan bir sürüm "güncellendi" sayılamaz.
    const medyaGerekli = !!man.media_id && man.media_id !== this.etkinMediaId();
    if (medyaGerekli && !man.media_payload_name) {
      this.gunluk(`media_id uyuşmuyor (${man.media_id} ≠ ${this.etkinMediaId()}) ama yükte medya YOK → tam paket`);
      return {
        ok: false,
        requiresFull: true,
        reason: _et('guncel.medya-yayinlanmamis'),
      };
    }

    const toplamBayt = man.payload_size + (medyaGerekli ? (man.media_payload_size || 0) : 0);
    onProgress({ asama: 'indiriliyor', toplam: toplamBayt, medya: medyaGerekli });
    const url = `https://github.com/${REPO}/releases/download/v${version}/${man.payload_name}`;
    const payload = await httpsGet(url);

    const sha = crypto.createHash('sha256').update(payload).digest('hex');
    if (sha !== man.payload_sha256) {
      throw new Error(_et('guncel.sha-tutmadi'));
    }

    // Medya yükü — kod yükünden AYRI indirilir ama AYNI geçici dizine açılır:
    // ikisi birlikte tek bir atomik `rename` ile devreye girer. Medya yarıda
    // kalırsa kod da uygulanmaz; yarım güncellenmiş bir kurulum oluşmaz.
    let medyaPayload = null;
    if (medyaGerekli) {
      const mUrl = `https://github.com/${REPO}/releases/download/v${version}/${man.media_payload_name}`;
      medyaPayload = await httpsGet(mUrl, { maxBytes: MAX_MEDIA_BYTES });
      const mSha = crypto.createHash('sha256').update(medyaPayload).digest('hex');
      if (mSha !== man.media_payload_sha256) {
        throw new Error(_et('guncel.medya-sha'));
      }
    }

    // Medya ÖNCE uygulanır ve KOD OVERLAY'İNDEN AYRI, sürümsüz bir katmanda durur.
    //
    // 🔴 Neden overlay'in içinde değil (ilk tasarımda öyleydi, kusurlu): overlay
    // sürüme özeldir ve her güncellemede yenisi kurulur. Medya değişmediği bir
    // sonraki sürümde yeni overlay medya taşımaz → statik sunucu paketin İÇİNDEKİ
    // eski medyaya düşer → kullanıcı bir sürüm önce indirdiği görselleri KAYBEDER.
    // Sürümsüz katman bunu yapısal olarak imkânsız kılar.
    //
    // Sıra bilinçli: medya kod'dan ÖNCE. Medya düşerse kod hiç uygulanmaz. Tersi
    // olsaydı yeni kod eksik medyayla açılırdı.
    if (medyaPayload) {
      onProgress({ asama: 'medya uygulanıyor' });
      this._medyaUygula(medyaPayload, man);
    }

    onProgress({ asama: 'uygulanıyor' });
    const girisler = tarOku(zlib.gunzipSync(payload));
    if (girisler.length !== man.file_count) {
      throw new Error(_et('guncel.dosya-sayi', { bulunan: girisler.length, beklenen: man.file_count }));
    }

    // Geçici dizine çıkar; tamamlanmadan asıl yerine taşınmaz →
    // yarıda kesilen bir güncelleme yarım bir kurulum bırakmaz.
    fs.mkdirSync(this.updatesDir, { recursive: true });
    const gecici = path.join(this.updatesDir, `.staging-${version}-${process.pid}`);
    fs.rmSync(gecici, { recursive: true, force: true });
    fs.mkdirSync(gecici, { recursive: true });

    try {
      for (const g of girisler) {
        const hedef = guvenliYol(gecici, g.ad);
        if (!hedef) throw new Error(_et('guncel.dosya-yol', { ad: g.ad }));
        fs.mkdirSync(path.dirname(hedef), { recursive: true });
        fs.writeFileSync(hedef, g.veri);
      }
      // Kardeş dosyaları aynala — HENÜZ geçici dizindeyken. Başarısız olursa
      // aşağıdaki catch geçiciyi siler ve mevcut kurulum hiç dokunulmamış kalır.
      this._kardesleriAynala(path.join(gecici, 'backend'));

      // Yazılan ağaç, imzalanan ağaçla birebir aynı mı? (derinlemesine savunma:
      // payload sha256 zaten tuttu, ama çıkarma yolunda bir hata olsaydı burada
      // yakalanır — ve aynı hesap her açılışta tekrarlanacağı için ilk kez
      // BURADA tuttuğunu görmek şart, yoksa ilk açılışta geri alınırdı.)
      const kokGecici = this.agacKoku(gecici);
      if (kokGecici !== man.files_root) {
        throw new Error(_et('guncel.agac', {
          bulunan: kokGecici.slice(0, 12), beklenen: man.files_root.slice(0, 12) }));
      }

      const nihai = path.join(this.updatesDir, version);
      fs.rmSync(nihai, { recursive: true, force: true });
      fs.renameSync(gecici, nihai);

      // İmzalı manifest saklanır: açılış-zamanı bütünlük denetiminin güven
      // çıpası budur. Saldırgan overlay'i değiştirse bile imzayı üretemez.
      fs.writeFileSync(this._manifestYolu(version), manifestHam, 'utf8');

      fs.writeFileSync(this.statePath, JSON.stringify({
        version, dir: nihai, shellId: man.shellId || man.shell_id,
        appliedAt: Date.now(), failCount: 0,
      }, null, 2), 'utf8');

      this._eskileriTemizle(version);
      this.gunluk(`UYGULANDI v${version} — ${girisler.length} dosya, ${(payload.length / 1048576).toFixed(2)} MiB`);
      return { ok: true, version, files: girisler.length, bytes: payload.length };
    } catch (e) {
      fs.rmSync(gecici, { recursive: true, force: true });
      throw e;
    }
  }

  /** Yeni sürüm dışındaki uygulanmış kopyaları sil (disk şişmesin). */
  _eskileriTemizle(tut) {
    // 🔴 `media`/`media.json` KORUNUR: medya katmanı sürümsüzdür ve kasten
    // overlay'den uzun yaşar. Buraya eklenmeseydi bu temizlik, her kod
    // güncellemesinde kullanıcının indirdiği 33 MB medyayı silip onu sessizce
    // paketin eski görsellerine düşürürdü — tam da bu katmanın önlediği hata.
    const korunan = new Set([tut, 'current.json', `${tut}.manifest.json`,
                             'media', 'media.json']);
    try {
      for (const d of fs.readdirSync(this.updatesDir)) {
        if (korunan.has(d)) continue;
        fs.rmSync(path.join(this.updatesDir, d), { recursive: true, force: true });
      }
    } catch (_) { /* temizlik başarısızlığı güncellemeyi bozmaz */ }
  }

  // ── Geri alma ────────────────────────────────────────────────────────────
  // Bozuk bir güncelleme ürünü tuğlalaştırmamalı. main.js backend'i başlatmadan
  // ÖNCE denemeyi işaretler, sağlıklı yanıt gelince temizler. Üst üste
  // MAX_FAIL başarısızlıkta overlay atılır ve paketlenmiş sürüme dönülür.
  static MAX_FAIL = 3;

  denemeIsaretle() {
    const s = this.applied();
    if (!s) return null;
    s.failCount = (s.failCount || 0) + 1;
    try { fs.writeFileSync(this.statePath, JSON.stringify(s, null, 2), 'utf8'); } catch (_) {}
    return s.failCount;
  }

  basariliIsaretle() {
    const s = this.applied();
    if (!s || !s.failCount) return;
    s.failCount = 0;
    try { fs.writeFileSync(this.statePath, JSON.stringify(s, null, 2), 'utf8'); } catch (_) {}
  }

  /** Overlay'i at, paketlenmiş sürüme dön. Sebep hata günlüğüne yazılır. */
  geriAl(sebep = 'bilinmiyor') {
    const s = this.applied();
    try {
      if (s && s.dir) fs.rmSync(s.dir, { recursive: true, force: true });
      fs.rmSync(this.statePath, { force: true });
    } catch (_) {}
    return { rolledBack: !!s, version: s ? s.version : null, sebep };
  }

  /**
   * Overlay güvenilir mi? Değilse önyükleyici onu kullanmamalı.
   *
   * İki ayrı soru sorulur, karıştırılmamalı:
   *   ① **Çalışıyor mu?**  → `failCount` (üst üste açılamadıysa geri al)
   *   ② **Bizim yazdığımız şey mi?** → imzalı manifest + dosya ağacı kökü
   *
   * ②'nin yanıtı hayırsa geri almak DOĞRU davranıştır: kurcalanmış bir overlay
   * "belki düzelir" diye bir daha denenmez.
   */
  saglikli() {
    const s = this.applied();
    if (!s) return { kullan: false };
    if ((s.failCount || 0) >= DeltaUpdater.MAX_FAIL) {
      return { kullan: false, geriAlinmali: true, version: s.version, sebep: 'üst üste açılamadı' };
    }
    const b = this.butunlukDogrula(s.version, s.dir);
    if (!b.saglam) {
      this.gunluk(`BÜTÜNLÜK BOZUK v${s.version}: ${b.sebep}`);
      return { kullan: false, geriAlinmali: true, version: s.version, sebep: b.sebep };
    }
    return { kullan: true, version: s.version, dir: s.dir };
  }
}

module.exports = { DeltaUpdater, canonical, guvenliYol, tarOku, UPDATE_PUBLIC_KEY };
