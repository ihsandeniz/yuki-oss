// ── İndir-gerektiğinde Model Yöneticisi ─────────────────────────────────────
// Ağır ML modelleri (whisper STT, ileride VRM) uygulamayla PAKETLENMEZ; ilk
// kullanıldıklarında GitHub Release'ten indirilir. Böylece çekirdek paket küçük kalır
// (~450MB) ve kullanıcı sadece kullandığı özelliğin modelini indirir.
//
// Tasarım kararı — İKİ SKU tek kodla:
//   • Hafif kurulum : model YOK → ilk kullanımda writableDir'e (userData) indirilir.
//   • Tam offline   : model bundled (resources/backend/models-cache) → indirme atlanır.
//   locate() önce writableDir, sonra bundledDir'e bakar → hiçbir kopyalama/symlink gerekmez.
//
// Bağımlılık YOK: https/crypto/fs built-in + sistem `tar` (Win10 17063+/Linux/mac'te var).

const https = require('https');
const http = require('http');
const fs = require('fs');
const path = require('path');
const crypto = require('crypto');
const { execFile } = require('child_process');
const { URL } = require('url');
const _et = require('./dil').t;
const _aktifDil = require('./dil').aktifDil;

/**
 * Manifest kaydının kullanıcıya görünen alanı (`name` / `feature`) aktif dilde.
 * TR kaynak alanın kendisidir; diğer diller `i18n.<dil>` altında, yoksa `i18n.en`,
 * o da yoksa TR. Çağrı ANINDA çözülür — dil değişince bir sonraki `status()` yeni dili görür.
 */
function _yerel(m, alan) {
  const dil = _aktifDil();
  const i = (m && m.i18n) || {};
  if (dil !== 'tr') {
    const v = (i[dil] && i[dil][alan]) || (i.en && i.en[alan]);
    if (v) return v;
  }
  return m ? m[alan] : undefined;
}

/**
 * `process.platform`/`arch` → manifest asset anahtarı. Bilinmeyen kombinasyon → null.
 *
 * 🔑 NEDEN VAR ( Dalga 2): modeller platformdan bağımsızdır (`.onnx` her yerde
 * aynı), ama `kind:"pydeps"` yükleri DEĞİLDİR — içlerinde derlenmiş `.so` (Linux) /
 * `.pyd` (Windows) taşırlar. O yüzden bu tip yüklerde yük başına tek asset yetmez,
 * platform başına bir asset gerekir (`assets: { "linux-x64": …, "win-x64": … }`).
 *
 * ⚠️ Bilinmeyen platformda **null** dönüyoruz, "linux" varsaymıyoruz: yanlış platformun
 * ikilisini indirip açmak, indirmemekten kötüdür (import anında anlaşılmaz hata verir).
 */
function platformAnahtari(platform = process.platform, arch = process.arch) {
  const p = { linux: 'linux', win32: 'win' }[platform];
  const a = { x64: 'x64' }[arch];
  return p && a ? `${p}-${a}` : null;
}

class ModelManager {
  /**
   * @param {object} cfg
   * @param {string} cfg.manifestPath  models-manifest.json yolu
   * @param {string} cfg.writableDir   userData/models-cache (yazılabilir, indirme hedefi)
   * @param {string|null} cfg.bundledDir  resources/backend/models-cache (salt-okunur, tam build) veya null
   * @param {string|null} [cfg.platformKey]  test için geçersiz kılma; yoksa süreçten türetilir
   */
  constructor({ manifestPath, writableDir, bundledDir, platformKey }) {
    this.manifestPath = manifestPath;
    this.writableDir = writableDir;
    this.bundledDir = bundledDir || null;
    this.platformKey = platformKey !== undefined ? platformKey : platformAnahtari();
    this._manifest = null;
    this._active = new Map(); // id -> { canceled }
  }

  /**
   * Kaydın bu platformdaki indirme bilgisi ({url, sha256, sizeBytes, downloadBytes}).
   *
   * İki biçim desteklenir ve ESKİ BİÇİM AYNEN ÇALIŞIR:
   *   • eski (model): alanlar kaydın kendisinde → kayıt olduğu gibi döner
   *   • yeni (pydeps): `assets[<platform>]` → o platformun girdisi, yoksa null
   */
  _asset(m) {
    if (!m.assets) return m;
    if (!this.platformKey) return null;
    return m.assets[this.platformKey] || null;
  }

  manifest() {
    if (!this._manifest) {
      this._manifest = JSON.parse(fs.readFileSync(this.manifestPath, 'utf8'));
    }
    return this._manifest;
  }

  _model(id) {
    const mf = this.manifest();
    const m = mf.models[id];
    if (!m) {
      // Planlanan (henüz yayınlanmamış) model → "bilinmeyen" değil, "yakında".
      const planned = (mf.plannedModels || {})[id];
      if (planned) {
        throw new Error(_et('modelyk.henuz-yayinlanmadi', { ad: _yerel(planned, 'name') }));
      }
      throw new Error(_et('modelyk.bilinmeyen', { id }));
    }
    return m;
  }

  /**
   * "Bu yolda GERÇEKTEN içerik var mı?" — var olmak yetmez, DOLU olmalı.
   *
   * 🔴 NEDEN (2026-09-05'te ölçülerek bulundu): `_extract` hedef dizini tar'dan
   * ÖNCE `mkdirSync` ile yaratıyor. `extractTo` ile `presenceDir` aynı yolsa
   * (pydeps'te öyle) varlık kapısı, **açıcının kendi yarattığı** dizini ölçer →
   * BOŞ bir arşiv "başarıyla kuruldu" sayılır (`{ok:true}` + `present:true`).
   * Aynı tuzağın ikinci yüzü daha sinsi: yarıda kalan bir açma boş dizini geride
   * bırakır, `locate()` "var" der ve özellik **kalıcı olarak** eksik dosyalarla
   * çalışmaya çalışır — indirme bir daha hiç denenmez.
   *
   * Eski modeller (whisper/embedding) kazara güvendeydi: `extractTo:"."` olduğu
   * için mkdir `presenceDir`'i yaratmıyordu. Kuralı koda bağlamak, doğru
   * `presenceDir` seçmeyi insana bırakmaktan güvenli.
   */
  _dolu(p) {
    let st;
    try { st = fs.statSync(p); } catch (_) { return false; }
    if (st.isDirectory()) return fs.readdirSync(p).length > 0;
    return st.size > 0;
  }

  /** Model dosyaları nerede? writable öncelik → bundled → null (yok). */
  locate(id) {
    const m = this._model(id);
    const inWritable = path.join(this.writableDir, m.presenceDir);
    if (this._dolu(inWritable)) return { dir: this.writableDir, location: 'downloaded' };
    if (this.bundledDir) {
      const inBundled = path.join(this.bundledDir, m.presenceDir);
      if (this._dolu(inBundled)) return { dir: this.bundledDir, location: 'bundled' };
    }
    return null;
  }

  /**
   * Modeli barındıran dizin (backend HF_HOME için). Hiç yoksa writableDir döner
   * (indirme hedefi olacak; model gelene kadar backend graceful-degrade eder).
   */
  effectiveDir(id) {
    const loc = this.locate(id);
    return loc ? loc.dir : this.writableDir;
  }

  /**
   * Kurulu `kind:"pydeps"` yüklerinin dizinleri — backend'e `YUKI_PYDEPS` ile
   * geçilir, orada `sys.path`'in SONUNA eklenir (`backend/app/pydeps.py`).
   *
   * Yalnız GERÇEKTEN kurulu olanlar döner (`locate()` → `_dolu` kontrolünden
   * geçmiş). İnmemiş bir yükü listelemek, backend'e var olmayan dizini
   * göstermek olurdu; o da "kütüphane var" yanılsaması üretirdi.
   */
  /**
   * Şu an indirilmekte olan yüklerin kimlikleri.
   *
   * 🔑 Yeniden başlatma kapısı için var (2026-09-08): sürmekte olan bir indirme
   * varken uygulamayı yeniden başlatmak yarım dosya bırakır ve kullanıcı
   * 16-276 MB'ı baştan indirir. `_active` zaten tutuluyordu ama yalnız
   * `status(id)` üzerinden, yani **tek tek sorularak** okunabiliyordu; dışarıdan
   * "herhangi bir indirme var mı" diye sormanın yolu yoktu.
   */
  aktifIndirmeler() {
    /* ⚠️ `.keys()` ŞART — `_active` bir **Map** (`id -> {canceled}`), Set değil.
       İlk yazımda `Array.from(this._active)` yazıldı ve `[[id, {…}]]` döndürdü:
       kapı "engel var" demeyi sürdürürdü ama kullanıcıya gösterilen metin
       `face-pydeps,[object Object]` olurdu. Testi bunu ilk koşuda yakaladı. */
    return Array.from(this._active.keys());
  }

  pydepsDirs() {
    const mf = this.manifest();
    const out = [];
    for (const [id, m] of Object.entries(mf.models || {})) {
      if (m.kind !== 'pydeps') continue;
      const loc = this.locate(id);
      if (loc) out.push(path.join(loc.dir, m.extractTo || '.'));
    }
    return out;
  }

  status(id) {
    const m = this._model(id);
    const loc = this.locate(id);
    const a = this._asset(m);
    const downloadable = !!(a && a.url && a.sha256 && a.sha256 !== 'TBD');
    return {
      id,
      name: _yerel(m, 'name'),
      feature: _yerel(m, 'feature'),
      kind: m.kind || 'model',
      present: !!loc,
      location: loc ? loc.location : null,
      downloadable,
      // Bu platform için asset yoksa arayüz SEBEBİNİ görsün — "indirilemez" tek
      // başına kullanıcıya "bozuk mu, yoksa desteklenmiyor mu" ayrımı vermiyor.
      unsupportedPlatform: !!(m.assets && !a),
      platformKey: this.platformKey,
      downloading: this._active.has(id),
      sizeBytes: (a && a.sizeBytes) || 0,
      downloadBytes: (a && (a.downloadBytes || a.sizeBytes)) || 0,
      tier: m.tier || 'lite',
    };
  }

  /** İptal talebi (indirme devam ediyorsa). */
  cancel(id) {
    const t = this._active.get(id);
    if (t) t.canceled = true;
  }

  /**
   * Modeli indir, doğrula, aç. Zaten varsa {ok:true, already:true} döner.
   * onProgress({phase:'download'|'extract'|'done', received, total})
   */
  async download(id, onProgress) {
    const m = this._model(id);
    if (this.locate(id)) return { ok: true, already: true };
    const a = this._asset(m);
    if (m.assets && !a) {
      // Yanlış platformun ikilisini indirmektense dürüst hata ver.
      throw new Error(_et('modelyk.desteklenmiyor', {
        ad: _yerel(m, 'name'),
        platform: this.platformKey || `${process.platform}/${process.arch}`,
        hazir: Object.keys(m.assets).join(', '),
      }));
    }
    if (!a || !a.url || !a.sha256 || a.sha256 === 'TBD') {
      throw new Error(_et('modelyk.paket-yok', { ad: _yerel(m, 'name') }));
    }
    if (this._active.has(id)) throw new Error(_et('modelyk.zaten-iniyor'));

    const token = { canceled: false };
    this._active.set(id, token);

    fs.mkdirSync(this.writableDir, { recursive: true });
    const tmpDir = path.join(this.writableDir, '.tmp');
    fs.mkdirSync(tmpDir, { recursive: true });
    const tmpFile = path.join(tmpDir, `${id}.download`);

    try {
      const sha = await this._downloadTo(
        a.url, tmpFile, a.downloadBytes || a.sizeBytes || 0, onProgress, token
      );
      if (token.canceled) throw new Error(_et('modelyk.iptal'));
      if (sha.toLowerCase() !== String(a.sha256).toLowerCase()) {
        throw new Error(_et('modelyk.butunluk'));
      }
      if (onProgress) onProgress({ phase: 'extract', received: 0, total: 0 });
      const hedef = path.join(this.writableDir, m.extractTo || '.');
      await this._extract(tmpFile, hedef);
      // ⚠️ `existsSync` yetmez — açıcı bu dizini kendisi yaratmış olabilir (bkz. _dolu).
      if (!this._dolu(path.join(this.writableDir, m.presenceDir))) {
        // Geride BOŞ dizin bırakma: `locate()` onu "kurulu" sanıp indirmeyi
        // sonsuza kadar atlardı. Başarısızlık iz bırakmamalı.
        this._bosDiziniTemizle(hedef);
        throw new Error(_et('modelyk.bos-paket'));
      }
      if (onProgress) onProgress({ phase: 'done', received: 1, total: 1 });
      return { ok: true };
    } finally {
      this._active.delete(id);
      try { fs.unlinkSync(tmpFile); } catch (_) {}
    }
  }

  // --- iç yardımcılar ---

  /**
   * Başarısız açmadan kalan BOŞ dizinleri `writableDir`'e kadar geri sil.
   * Dolu olanda durur — kullanıcının indirdiği başka bir modeli asla silmez.
   */
  _bosDiziniTemizle(dizin) {
    let p = path.resolve(dizin);
    const kok = path.resolve(this.writableDir);
    while (p.startsWith(kok) && p !== kok) {
      try {
        if (fs.readdirSync(p).length > 0) break;
        fs.rmdirSync(p);
      } catch (_) { break; }
      p = path.dirname(p);
    }
  }

  _downloadTo(url, dest, total, onProgress, token, redirects = 0) {
    return new Promise((resolve, reject) => {
      if (redirects > 5) return reject(new Error(_et('modelyk.cok-yonlendirme')));
      const lib = url.startsWith('http:') ? http : https;
      const req = lib.get(url, { headers: { 'User-Agent': 'Yuki-ModelManager' } }, (res) => {
        // GitHub release asset'leri S3'e 302 yönlendirir → takip et
        if ([301, 302, 303, 307, 308].includes(res.statusCode) && res.headers.location) {
          res.resume();
          const next = new URL(res.headers.location, url).toString();
          return resolve(this._downloadTo(next, dest, total, onProgress, token, redirects + 1));
        }
        if (res.statusCode !== 200) {
          res.resume();
          return reject(new Error(_et('modelyk.http', { kod: res.statusCode })));
        }

        const totalBytes = total || parseInt(res.headers['content-length'] || '0', 10);
        const hash = crypto.createHash('sha256');
        const out = fs.createWriteStream(dest);
        let received = 0;
        let lastEmit = 0;

        res.on('data', (chunk) => {
          if (token.canceled) {
            req.destroy(new Error(_et('modelyk.iptal')));
            out.destroy();
            return;
          }
          received += chunk.length;
          hash.update(chunk);
          const now = Date.now();
          if (onProgress && now - lastEmit > 200) {
            lastEmit = now;
            onProgress({ phase: 'download', received, total: totalBytes });
          }
        });

        res.on('error', (e) => { out.destroy(); reject(e); });
        res.pipe(out);

        out.on('error', reject);
        out.on('finish', () => out.close(() => {
          if (token.canceled) return reject(new Error(_et('modelyk.iptal')));
          if (onProgress) onProgress({ phase: 'download', received, total: totalBytes });
          resolve(hash.digest('hex'));
        }));
      });

      req.on('error', reject);
      req.setTimeout(60000, () => req.destroy(new Error(_et('modelyk.zaman-asimi'))));
    });
  }

  _extract(archive, destDir) {
    return new Promise((resolve, reject) => {
      fs.mkdirSync(destDir, { recursive: true });
      // Sistem tar: Win10 17063+ (bsdtar), Linux (GNU tar), mac (bsdtar) — gzip'i otomatik açar.
      execFile('tar', ['-xzf', archive, '-C', destDir], { maxBuffer: 4 * 1024 * 1024 }, (err) => {
        if (err) {
          return reject(new Error(_et('modelyk.tar-yok', { ayrinti: err.message })));
        }
        resolve();
      });
    });
  }
}

module.exports = { ModelManager, platformAnahtari };
