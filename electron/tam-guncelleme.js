/**
 * TAM PAKET SELF-UPDATE — uygulama içinden indir, doğrula, kur, yeniden başlat.
 *
 * ═══ NEDEN VAR ═══════════════════════════════════════════════════════════════
 * Delta güncelleme (`delta-updater.js`) yalnız app kodunu ve medyayı taşır.
 * Python bağımlılık ağacı ya da Electron ikilisi değiştiğinde `shell_id` tutmaz
 * ve delta reddedilir. O ana kadar kullanıcıya söylenen şey şuydu: *"tam paketi
 * indirmen gerekiyor"* + GitHub sayfasına bir link. Yani kullanıcı uygulamadan
 * çıkıyor, tarayıcı açıyor, 500 MB indiriyor, zip açıyor, elle değiştiriyordu.
 *
 * geliştirici (2026-08-08): *"insanların siteye girip indirmesini istemiyorum;
 * uygulama içinden herhangi bir güncellemeyi indirebilsinler."*
 *
 * ═══ NEDEN electron-updater DEĞİL ════════════════════════════════════════════
 * Ölçüldü/doğrulandı (2026-08-08): electron-updater Windows'ta YALNIZ NSIS
 * hedefiyle çalışıyor; satılan Windows SKU'ları `zip`. Linux AppImage'ı
 * destekliyor ama dört SKU'nun ikisinde çalışmayan bir çözüm, iki ayrı güncelleme
 * yolu bakmak demek. NSIS'e geçmek kod imzalama sertifikası (masraf) + SmartScreen
 * sorunu getiriyordu. Karar: tek kod yolu, kendi implementasyonumuz.
 *
 * ═══ GÜVENLİK — bu bir UZAKTAN KOD ÇALIŞTIRMA kanalıdır ══════════════════════
 * İndirilen şey doğrudan çalıştırılacak bir ikili. Güven zinciri delta ile AYNI:
 * hash'ler Ed25519 **imzalı** manifest'te taşınır (`skus` alanı) ve indirilen
 * dosya ona karşı doğrulanır. GitHub'ın kendi bütünlüğüne GÜVENİLMEZ: release
 * varlığı yeniden yüklenebilir, etiket taşınabilir, ayna bayat olabilir.
 * İmza/hash tutmazsa diske kalıcı hiçbir şey yazılmaz.
 *
 * ═══ TUĞLALAŞTIRMAMA ═════════════════════════════════════════════════════════
 * Bu modül kurulum dizinini değiştirir — üründeki en tehlikeli işlem. Kurallar:
 *   · Devir ATOMİK olabildiği yerde atomik (AppImage: tek `rename`).
 *   · Windows'ta atomik olamaz (çalışan .exe kilitli) → eski kurulum ÖNCE
 *     yedeklenir, kopyalama biterse yedek silinir, bitmezse yardımcı geri koyar.
 *   · Yardımcı süreç her adımı `guncelleme.log`'a yazar — sessiz başarısızlık yok.
 *   · Hiçbir aşamada kullanıcı verisi (`userData`) elleçlenmez.
 */
const crypto = require('crypto');
const fs = require('fs');
const https = require('https');
const os = require('os');
const path = require('path');
const { spawn } = require('child_process');
// Kullanıcıya giden hata/sebep metinleri (tam:* → updater-ui.js). Günlük + PowerShell `Yaz` satırları çevrilmez.
const _et = require('./dil').t;

const REPO = 'ihsandeniz/yuki-oss';
// Tam paketler büyük: lite ~520 MB, offline ~1,05 GB. Tavan ikisinin de üstünde
// ama sınırsız değil — bozuk/şişmiş bir varlık diski doldurmasın.
const MAX_SKU_BYTES = 3 * 1024 * 1024 * 1024;

/** `ad:sha256:boyut;…` → {ad: {sha256, size}} */
function skuTablosu(ham) {
  const t = {};
  if (typeof ham !== 'string' || !ham) return t;
  for (const kayit of ham.split(';')) {
    const i = kayit.indexOf(':');
    if (i < 0) continue;
    const ad = kayit.slice(0, i);
    if (!ad) continue;                       // `:sha:1` → adsız kayıt, tabloya girmez
    const kalan = kayit.slice(i + 1).split(':');
    if (kalan.length !== 2) continue;
    const [sha, boyut] = kalan;
    if (!/^[0-9a-f]{64}$/.test(sha)) continue;
    // Boyut sayı değilse kayıt eksiktir; `NaN` bir karşılaştırmayı sessizce
    // geçmez ama tabloya girmesi de doğru değil — burada eleriz.
    const n = Number(boyut);
    if (!Number.isInteger(n) || n <= 0) continue;
    t[ad] = { sha256: sha, size: n };
  }
  return t;
}

/**
 * Bu kurulumun indirmesi gereken varlığın adı.
 *
 * SKU damgası build zamanında `extraMetadata.yukiSku` ile package.json'a yazılır.
 * Çalışma anında tespit etmeye çalışmak kırılgandı: AppImage adından okunabilir
 * ama Windows zip'te kurulum dizini hiçbir ipucu taşımıyor ("lite mi offline mı"
 * sorusunu whisper modelinin varlığından tahmin etmek, modeli sonradan indiren
 * lite kurulumu offline sanardı).
 */
function skuVarligi(sku, surum) {
  const kalip = {
    'lite': `Yuki-${surum}-lite.AppImage`,
    'offline': `Yuki-${surum}-offline.AppImage`,
    'win-x64-lite': `Yuki-${surum}-win-x64-lite.zip`,
    'win-x64-offline': `Yuki-${surum}-win-x64-offline.zip`,
  };
  return kalip[sku] || null;
}

function indir(url, { maxBytes = MAX_SKU_BYTES, onProgress = () => {} } = {}) {
  return new Promise((resolve, reject) => {
    const istek = https.get(url, { headers: { 'User-Agent': 'Yuki-Updater' } }, (res) => {
      if (res.statusCode >= 300 && res.statusCode < 400 && res.headers.location) {
        res.resume();
        return resolve(indir(res.headers.location, { maxBytes, onProgress }));
      }
      if (res.statusCode !== 200) {
        res.resume();
        return reject(new Error(_et('guncel.indirme-http', { kod: res.statusCode })));
      }
      const toplam = Number(res.headers['content-length']) || 0;
      const parcalar = [];
      let alinan = 0;
      res.on('data', (p) => {
        alinan += p.length;
        if (alinan > maxBytes) {
          istek.destroy();
          return reject(new Error(_et('guncel.indirilen-buyuk')));
        }
        parcalar.push(p);
        onProgress({ alinan, toplam });
      });
      res.on('end', () => resolve(Buffer.concat(parcalar)));
      res.on('error', reject);
    });
    istek.on('error', reject);
    istek.setTimeout(120000, () => { istek.destroy(); reject(new Error(_et('guncel.indirme-zaman'))); });
  });
}

class TamGuncelleyici {
  /**
   * @param {object} o
   * @param {string} o.sku          package.json `yukiSku` (build damgası)
   * @param {string} o.execPath     process.execPath
   * @param {string} o.appImagePath process.env.APPIMAGE (Linux AppImage ise)
   * @param {string} o.userDataDir  yalnız geçici indirme + günlük için
   */
  constructor({ sku, execPath, appImagePath, userDataDir, gunluk, platform }) {
    this.sku = sku || null;
    this.execPath = execPath;
    this.appImagePath = appImagePath || null;
    this.userDataDir = userDataDir;
    this.platform = platform || process.platform;
    this.gunluk = gunluk || ((s) => console.error('[tam-guncelleme]', s));
  }

  /**
   * Bu kurulum uygulama içi tam güncelleme YAPABİLİR mi?
   *
   * Dürüstlük kapısı: yapamayacağı bir şeyi teklif eden bir düğme, kullanıcıyı
   * yarıda kalmış bir kuruluma götürür. Emin olunamayan her durumda `false`.
   */
  destekleniyor() {
    if (!this.sku) return { ok: false, sebep: _et('guncel.sku-damgasi-yok') };
    if (this.platform === 'linux') {
      if (!this.appImagePath || !fs.existsSync(this.appImagePath)) {
        // 🔑 2026-08-13 — SEBEP DÜRÜST OLMALI, yoksa yanlış teşhis üretir.
        // Eski metin her durumda "AppImage yolu bulunamadı (paketlenmemiş çalışma?)"
        // diyordu. Ama Linux'ta iki SKU var ve İKİSİ DE `yukiSku: lite` damgası
        // taşıyor (`electron-builder.yml:18` — AppImage ve tar.gz aynı yml'den
        // çıkıyor). tar.gz kullanıcısı AppImage kullanmıyor; ona "AppImage yolu
        // bulunamadı" demek, ElevenLabs'ın kota hatasına "geçersiz anahtar"
        // demesinin aynısı: doğru kapı, yanlış sebep → kullanıcı yanlış çözümü arar.
        //
        // Ayrım: AppImage çalışırken `process.env.APPIMAGE` set edilir, tar.gz'de
        // edilmez. Paketlenmiş bir uygulamada bu değişkenin yokluğu "tar.gz (ya da
        // elle açılmış paket)" demektir.
        //
        // ⚠️ Kapının kendisi DEĞİŞMEDİ — tar.gz yine tam paket güncellemesi almıyor
        // (kurulum kökünü yerinde değiştirmek ayrı bir iş ve hiç test edilmedi;
        // yapamayacağını teklif etme kuralı duruyor). Değişen yalnız NE SÖYLEDİĞİ.
        // Bilinmesi gereken: **delta güncellemeleri tar.gz'de sorunsuz çalışıyor**
        // (`delta-updater.js` yalnız `userData/updates/` altına yazar, kabuğa
        // dokunmaz) — yani sürümlerin çoğu normal iniyor, elle indirme yalnız
        // `shell_id` değişen turlarda gerekiyor.
        const paketli = !!this.execPath && !/[/\\]electron$/.test(this.execPath);
        if (paketli) {
          return {
            ok: false,
            targz: true,
            sebep: _et('guncel.targz'),
          };
        }
        return { ok: false, sebep: _et('guncel.appimage-yok') };
      }
      if (!this._yazilabilir(path.dirname(this.appImagePath))) {
        return { ok: false, sebep: _et('guncel.appimage-izin') };
      }
      return { ok: true, hedef: this.appImagePath };
    }
    if (this.platform === 'win32') {
      const kok = this.kurulumKoku();
      if (!kok) return { ok: false, sebep: _et('guncel.kok-yok') };
      // Program Files altına yazmak yönetici ister; portable zip genelde
      // kullanıcı klasöründedir. Yazamıyorsak DENEMEYİZ — yarıda kalmış bir
      // kopyalama, çalışan bir kurulumu bozardı.
      if (!this._yazilabilir(kok)) {
        return { ok: false, sebep: _et('guncel.kok-izin') };
      }
      return { ok: true, hedef: kok };
    }
    return { ok: false, sebep: _et('guncel.platform-desteklenmiyor', { platform: this.platform }) };
  }

  kurulumKoku() {
    try { return path.dirname(this.execPath); } catch (_) { return null; }
  }

  _yazilabilir(dizin) {
    try {
      const deneme = path.join(dizin, `.yuki-yazma-testi-${process.pid}`);
      fs.writeFileSync(deneme, 'x');
      fs.unlinkSync(deneme);
      return true;
    } catch (_) { return false; }
  }

  /**
   * İndir + doğrula. Kurulumu DEĞİŞTİRMEZ — yalnız doğrulanmış dosyayı
   * geçici bir yere koyar ve yolunu döner. Kurulum `kur()` ile ayrı adımda,
   * çünkü kullanıcı "indir" ile "şimdi yeniden başlat"ı ayrı ayrı onaylamalı.
   */
  async indirVeDogrula(version, manifest, onProgress = () => {}) {
    // çağıran `fetchManifest`in `{man, ham}` ZARFINI açmadan geçirirse
    // `manifest.skus` undefined kalır ve aşağıdaki güvenlik kapısı *"imzalı
    // parmak izinde X yok"* der — yani manifesti suçlar, oysa kusur çağrıdadır.
    // 🔴 Bu denetim EN BAŞTA: çağıran sözleşmeyi bozduysa bunu makineye
    // sormadan söyleyebilmeliyiz. Aşağıya konsaydı geliştirici/test makinesinde
    // önce `destekleniyor()` düşerdi ("AppImage yolu bulunamadı") ve yanıltıcı
    // mesaj tam da teşhisin yapıldığı yerde hayatta kalırdı.
    if (manifest && typeof manifest === 'object'
        && manifest.man && typeof manifest.man === 'object' && manifest.skus === undefined) {
      throw new Error(_et('guncel.ic-hata-zarf'));
    }

    const d = this.destekleniyor();
    if (!d.ok) throw new Error(_et('guncel.tam-yapilamiyor', { sebep: d.sebep }));

    const ad = skuVarligi(this.sku, version);
    if (!ad) throw new Error(_et('guncel.sku-bilinmeyen', { sku: this.sku }));

    const tablo = skuTablosu(manifest && manifest.skus);
    const beklenen = tablo[ad];
    if (!beklenen) {
      // İmzalı manifest bu varlığın hash'ini taşımıyorsa indirmeyiz. İmzasız bir
      // ikiliyi indirip çalıştırmak, delta kanalında kapattığımız açığı arka
      // kapıdan geri açardı.
      throw new Error(_et('guncel.parmak-izi-yok', { ad }));
    }

    this.gunluk(`TAM: ${ad} indiriliyor (${(beklenen.size / 1e6).toFixed(0)} MB)`);
    const url = `https://github.com/${REPO}/releases/download/v${version}/${ad}`;
    const veri = await indir(url, {
      maxBytes: Math.max(MAX_SKU_BYTES, beklenen.size + 1024),
      onProgress: (p) => onProgress({ asama: 'indiriliyor', ...p }),
    });

    if (veri.length !== beklenen.size) {
      throw new Error(_et('guncel.boyut', { bulunan: veri.length, beklenen: beklenen.size }));
    }
    const sha = crypto.createHash('sha256').update(veri).digest('hex');
    if (sha !== beklenen.sha256) {
      throw new Error(_et('guncel.paket-sha'));
    }

    const gecici = path.join(this.userDataDir, 'updates', 'tam');
    fs.mkdirSync(gecici, { recursive: true });
    const hedef = path.join(gecici, ad);
    fs.writeFileSync(hedef, veri);
    if (this.platform === 'linux') fs.chmodSync(hedef, 0o755);

    this.gunluk(`TAM: ${ad} doğrulandı (sha256 ✓) → ${hedef}`);
    return { dosya: hedef, ad, boyut: veri.length, version };
  }

  /**
   * Doğrulanmış paketi kur. Uygulamanın KAPANMASI gerekir.
   * @returns {{yenidenBaslat: function}} çağıran uygulamayı kapatmalı
   */
  kur(indirilen) {
    if (!indirilen || !fs.existsSync(indirilen.dosya)) {
      throw new Error(_et('guncel.kurulacak-yok'));
    }
    if (this.platform === 'linux') return this._kurAppImage(indirilen);
    if (this.platform === 'win32') return this._kurWindows(indirilen);
    throw new Error(_et('guncel.platform-hata', { platform: this.platform }));
  }

  /**
   * AppImage: tek dosya → devir ATOMİK yapılabilir.
   *
   * Linux'ta çalışan bir dosyayı `rename` ile değiştirmek güvenlidir: çekirdek
   * açık inode'u tutmaya devam eder, çalışan süreç etkilenmez. Windows'un aksine
   * yardımcı sürece gerek yok.
   */
  _kurAppImage(indirilen) {
    const hedef = this.appImagePath;
    const yedek = `${hedef}.eski`;
    // Aynı dosya sistemi olsun diye yeni sürümü hedefin YANINA taşı; `rename`
    // ancak aynı bölümde atomiktir (userData başka bir bölümde olabilir).
    const yan = path.join(path.dirname(hedef), `.${path.basename(hedef)}.yeni`);
    fs.copyFileSync(indirilen.dosya, yan);
    fs.chmodSync(yan, 0o755);
    try { fs.rmSync(yedek, { force: true }); } catch (_) {}
    fs.renameSync(hedef, yedek);        // eskisini sakla (geri dönüş)
    fs.renameSync(yan, hedef);          // atomik devir
    this.gunluk(`TAM: AppImage değiştirildi → v${indirilen.version} (yedek: ${path.basename(yedek)})`);
    try { fs.rmSync(indirilen.dosya, { force: true }); } catch (_) {}
    return {
      yenidenBaslat: () => {
        const c = spawn(hedef, [], { detached: true, stdio: 'ignore' });
        c.unref();
      },
    };
  }

  /**
   * Windows zip: çalışan `.exe` KİLİTLİ → yerinde değiştirilemez.
   *
   * Klasik desen: uygulama bir yardımcı süreç doğurur, kendisi kapanır, yardımcı
   * kilit kalkınca dosyaları değiştirir ve uygulamayı yeniden başlatır.
   *
   * Yardımcı PowerShell'de yazıldı, .bat değil: `.bat` yolları boşluklu
   * dizinlerde ve Türkçe karakterli kullanıcı adlarında (C:\Users\Geliştirici) kod
   * sayfası yüzünden bozuluyor — bu üründe daha önce Windows log encoding'i
   * tam bu sınıftan bir arıza çıkarmıştı. PowerShell UTF-8 okur.
   */
  _kurWindows(indirilen) {
    const kok = this.kurulumKoku();
    const yardimci = path.join(this.userDataDir, 'updates', 'yuki-guncelle.ps1');
    const gunlukYolu = path.join(this.userDataDir, 'guncelleme.log');

    const ps = `
# Yuki tam güncelleme yardımcısı — uygulama kapandıktan SONRA çalışır.
$ErrorActionPreference = 'Stop'
$log = ${JSON.stringify(gunlukYolu)}
function Yaz($m) { Add-Content -Path $log -Value ("[" + (Get-Date -Format "yyyy-MM-dd HH:mm:ss") + "] tam-guncelleme: " + $m) -Encoding UTF8 }

$kok    = ${JSON.stringify(kok)}
$zip    = ${JSON.stringify(indirilen.dosya)}
$exe    = ${JSON.stringify(this.execPath)}
$pidEski = ${process.pid}
$gecici = Join-Path $env:TEMP ("yuki-yeni-" + [guid]::NewGuid().ToString("N"))
$yedek  = $kok + ".yedek"

try {
  Yaz "başladı (pid $pidEski bekleniyor)"
  # Uygulamanın kapanmasını bekle — kilit kalkmadan kopyalama yapılamaz.
  for ($i = 0; $i -lt 60; $i++) {
    if (-not (Get-Process -Id $pidEski -ErrorAction SilentlyContinue)) { break }
    Start-Sleep -Milliseconds 500
  }
  if (Get-Process -Id $pidEski -ErrorAction SilentlyContinue) {
    Yaz "İPTAL: uygulama 30 sn'de kapanmadı, hiçbir şeye dokunulmadı"
    exit 1
  }

  Yaz "zip açılıyor → $gecici"
  Expand-Archive -Path $zip -DestinationPath $gecici -Force

  # Zip tek bir kök klasör içeriyorsa onun İÇİNİ al (electron-builder öyle üretir).
  $icerik = Get-ChildItem -Path $gecici
  if ($icerik.Count -eq 1 -and $icerik[0].PSIsContainer) { $kaynak = $icerik[0].FullName }
  else { $kaynak = $gecici }

  # Yeni sürümün gerçekten çalıştırılabilir taşıdığını doğrula — yarım/bozuk bir
  # arşivle çalışan kurulumu değiştirmek, kurtarılamaz tek hatadır.
  $yeniExe = Join-Path $kaynak (Split-Path $exe -Leaf)
  if (-not (Test-Path $yeniExe)) {
    Yaz "İPTAL: yeni pakette $(Split-Path $exe -Leaf) yok — kurulum korundu"
    Remove-Item -Recurse -Force $gecici -ErrorAction SilentlyContinue
    exit 1
  }

  # Eski kurulumu YEDEKLE (yeniden adlandırma; kopyalamıyoruz, disk ve süre)
  if (Test-Path $yedek) { Remove-Item -Recurse -Force $yedek }
  Yaz "eski kurulum yedekleniyor → $yedek"
  Move-Item -Path $kok -Destination $yedek

  try {
    Yaz "yeni sürüm yerleştiriliyor"
    Move-Item -Path $kaynak -Destination $kok
  } catch {
    # Devir başarısız → eskisini GERİ KOY. Kullanıcı güncellenememiş olur,
    # ama çalışan bir uygulamayla kalır. Kabul edilebilir tek başarısızlık bu.
    Yaz "HATA: yerleştirme başarısız ($($_.Exception.Message)) → eski kurulum geri konuyor"
    if (Test-Path $kok) { Remove-Item -Recurse -Force $kok }
    Move-Item -Path $yedek -Destination $kok
    Start-Process -FilePath $exe
    exit 1
  }

  Yaz "başarılı — yedek siliniyor, uygulama başlatılıyor"
  Remove-Item -Recurse -Force $yedek -ErrorAction SilentlyContinue
  Remove-Item -Force $zip -ErrorAction SilentlyContinue
  Remove-Item -Recurse -Force $gecici -ErrorAction SilentlyContinue
  Start-Process -FilePath $exe
} catch {
  Yaz "BEKLENMEYEN HATA: $($_.Exception.Message)"
  # Kurulum kaybolmuşsa yedekten döndür — hiçbir senaryoda kullanıcı
  # uygulamasız kalmamalı.
  if ((-not (Test-Path $kok)) -and (Test-Path $yedek)) {
    Move-Item -Path $yedek -Destination $kok
    Yaz "yedekten geri döndürüldü"
  }
  if (Test-Path $exe) { Start-Process -FilePath $exe }
  exit 1
}
`;
    fs.mkdirSync(path.dirname(yardimci), { recursive: true });
    fs.writeFileSync(yardimci, ps, 'utf8');
    this.gunluk(`TAM: Windows yardımcısı yazıldı → ${yardimci}`);

    return {
      yenidenBaslat: () => {
        const c = spawn('powershell.exe',
          ['-NoProfile', '-ExecutionPolicy', 'Bypass', '-WindowStyle', 'Hidden',
           '-File', yardimci],
          { detached: true, stdio: 'ignore' });
        c.unref();
      },
    };
  }
}

module.exports = { TamGuncelleyici, skuTablosu, skuVarligi };
