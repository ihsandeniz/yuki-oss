// ── C4: Tema — ARTIK `js/tema.js` YÖNETİYOR (2026-08-27) ────────────────────
// 🔴 Burada İKİNCİ bir tema sistemi vardı: `data-theme="light|dark"` yazıyor,
// eski tema anahtarını kullanıyor, style.css + theme-violet.css'teki
// eski açık tema bloklarını açıyordu. Yeni sistem (`data-tema`, üç kademe)
// gelince İKİSİ AYNI ANDA koştu ve ölçülebilir bir kusur üretti:
//
//   kullanıcı KOYU seçmiş + işletim sistemi açık temada
//   → data-tema kalkar (koyu), ama data-theme="light" yazılı kalır
//   → köprülenmemiş eski değişkenler (--bg-msg-yuki, --bg-msg-user, --muted-2)
//     AÇIK tema değerinde kalır: koyu ekranda açık mesaj balonları.
//
// (PRODUCT.md zaten "Tema yalnız koyu, açık tema kaldırıldı" diyordu — bu kod
// o kaldırmadan sağ çıkmış bir artıktı.) Eski adlar API olarak korunuyor,
// çağıran yerler kırılmasın diye yeni sisteme devrediyorlar.
function applyTema(t) {
  if (window.YukiTema) window.YukiTema.ayarla(t);
}
function toggleTheme() {
  // Eski ikili anahtar: koyu ↔ açık. Üç kademeli seçim AYARLAR > Tema'da.
  const simdiki = (window.YukiTema && window.YukiTema.al()) || 'koyu';
  applyTema(simdiki === 'acik' ? 'koyu' : 'acik');
}
function applyTheme(theme) {   // eski imza (light|dark)
  applyTema(theme === 'light' ? 'acik' : 'koyu');
}

const BASE_URL = `${location.protocol}//${location.host}`;
const _WS_BASE = `${location.protocol === 'https:' ? 'wss' : 'ws'}://${location.host}`;

/* ── Çeviri (FAZ 3 · Dalga 2 · dosya kuyruğu 2/4, 2026-09-20) ───────────────
   `index.html`'in `data-i18n` çapaları buraya ULAŞMAZ: bu dosyanın metinlerinin
   tamamı JS'ten doğuyor (toast, `addMessage`, `title`, `innerHTML` şablonu),
   yani `dil.js::ciz()` onları hiç görmez. JS'in kancası bu fonksiyondur ve her
   çağrı yeri ELLE sarılır.

   🔴 ADI `t` DEĞİL `_t`. Bu dosyada `t` **dört yerde** yerel değişken
   (`sendMessage`'daki girdi metni, wake-word banner düğümü, ambient metin
   düğümü, `getTracks().forEach(t => …)`). `t` adı seçilseydi o kapsamlarda
   çeviri çağrısı SESSİZCE gölgelenirdi — `t is not a function` bile demeden,
   çünkü o kapsamda `t` gerçekten var ve bir DOM düğümü. `planner.html`'de aynı
   tuzak yirmi yerde çıkmıştı, `intro-sequences.js`'te üç yerde.

   ⚠️ `core.js` klasik script — bu bildirimler `window`'a da yazılır. Ön eki bu
   yüzden `_`: `t`/`tc` global adları başka bir dosyanın yerel sarmalayıcısıyla
   çakışmasın. */
function _t(anahtar, degerler) {
  return (window.YukiDil && window.YukiDil.t)
    ? window.YukiDil.t(anahtar, degerler) : String(anahtar);
}

/* Sayıya bağlı metin (`dil.js::tc` — backend `Mc` ile aynı sözleşme). */
function _tc(anahtar, sayi, degerler) {
  return (window.YukiDil && window.YukiDil.tc)
    ? window.YukiDil.tc(anahtar, sayi, degerler) : String(anahtar);
}

/* Tarih/saat/sayı biçimi etiketi. `'tr-TR'` yazmak metin çevrilse bile biçimi
   Türkçe bırakır — "15 Eyl 2026" İngilizce ekranda Türkçe bir ay adıdır
   (Blok 3'ün TR BİÇİM dersi; `planner.html`'de `formatDate` bunu bir kez daha
   ödedi). Bu dosyada dört `toLocaleTimeString('tr-TR')` vardı, dördü de buraya
   bağlandı. */
function _yerel() {
  return (window.YukiDil && window.YukiDil.yerel) ? window.YukiDil.yerel() : 'tr-TR';
}

// ── Auth ─────────────────────────────────────────────────────────────
// Token bellek-içi + sessionStorage (XSS'e karşı kalıcılık penceresi daraltılmış)
// Eski localStorage key varsa migrate et + temizle (ADIM 0)
(function _migrateAuthToken() {
  try {
    const old = localStorage.getItem('aliceToken');
    if (old) {
      sessionStorage.setItem('aliceToken', old);
      localStorage.removeItem('aliceToken');
    }
  } catch (_) {}
})();

let _authToken = sessionStorage.getItem('aliceToken') || '';

function _getToken() {
  return sessionStorage.getItem('aliceToken') || '';
}

function _wsUrl(path) {
  return _authToken ? `${_WS_BASE}${path}?token=${encodeURIComponent(_authToken)}` : `${_WS_BASE}${path}`;
}

const WS_URL = null; // _wsUrl('/ws/realtime') ile dinamik oluşturulur

/* ── Token bekleyenler — açılış yarışını kapatan halka (2026-09-08) ─────────
 *
 * 🔴 ÖLÇÜLEN KUSUR: uygulama kilidi kuruluyken sayfa açılışında **8 istek**
 * t=0,42–0,47 sn'de token'sız gidiyor ve 401 yiyor; kilit ise t=6,06 sn'de
 * açılıyor (Playwright ölçümü, 2026-09-08 ayar turu).
 * `app-lock.js::basariylaAcildi()` kilit sonrası `refreshAllAccess()` çağırıp
 * KADEME KAPILARINI tazeliyor — ama o liste yalnız kapıları kapsıyor.
 * Panellerin ve `ensureFaceLib`'in erken sorusu bir daha sorulmuyordu:
 *   · Sağlık → "undefined kritik" + ham `{"detail":"Unauthorized"}`
 *   · Bildirim → "Hatırlatıcılar/Bildirimler yüklenemedi: HTTP 401"
 *   · Güvenlik → kurulu kütüphane için sürekli "indir" ekranı
 *
 * 🔑 Düzeltme çağrı başına DEĞİL burada: kusur 4 yerde göründü ama sebebi tek
 * ve ortaktı. Tek tek yamamak, beşinci çağrı eklendiğinde aynı hatayı geri
 * getirirdi ('de bu bir kez yaşandı: `model-downloader.js` düz `fetch`
 * kullanıyordu, `authFetch`'e çevrildi, ama sınıf kapanmadı).
 */
const _tokenBekleyenler = [];

/** Token gelene kadar bekler. Gelmezse `false` döner — SÜRESİZ ASILMAZ. */
function _tokenBekle(msTavan = 90000) {
  if (_authToken) return Promise.resolve(true);
  return new Promise((coz) => {
    let bitti = false;
    const kapat = (sonuc) => { if (!bitti) { bitti = true; coz(sonuc); } };
    _tokenBekleyenler.push(() => kapat(true));
    /* ⚠️ Tavan şart: kullanıcı kilit ekranını hiç açmadan uygulamayı bırakabilir.
       Tavansız beklemek isteği (ve onu bekleyen paneli) sonsuza asardı — bu
       depoda `motor-bekle.js` aynı dersi taşıyor: beklemenin sonu olmalı. */
    setTimeout(() => kapat(false), msTavan);
  });
}

/**
 * Token'lı `fetch`. 401 dönerse ve istek **token'sız gitmişse**, token'ın
 * gelmesini bekleyip BİR KEZ yeniden dener.
 *
 * ⚠️ Yalnız "token'sız gittiyse" yeniden denenir. Token varken alınan 401
 * gerçek bir yetki reddidir (süresi dolmuş/yanlış oturum); onu tekrar denemek
 * sonsuz döngü üretir ve kilit ekranını hiç göstermez.
 */
function authFetch(url, opts = {}) {
  const tokenVardi = !!_authToken;
  const baslikli = (t) => (t
    ? { ...opts, headers: { ...(opts.headers || {}), Authorization: `Bearer ${t}` } }
    : opts);

  const ilk = fetch(url, baslikli(_authToken));
  if (tokenVardi) return ilk;

  return ilk.then(async (r) => {
    if (r.status !== 401) return r;
    const geldi = await _tokenBekle();
    if (!geldi || !_authToken) return r;   // token hiç gelmedi → ilk yanıtı olduğu gibi ver
    return fetch(url, baslikli(_authToken));
  });
}

/* 🔴 AÇIKÇA `window`'a yazılıyor (2026-09-08). Bugüne kadar yalnız `core.js`'in
   klasik script olması sayesinde `window.authFetch` tanımlıydı (üst düzey
   `function` bildirimi global nesneye de yazar). Ama **7 dosya**
   `typeof window.authFetch === 'function' ? ... : fetch` diye SESSİZ yedeğe
   düşüyordu (faces.js · tab-nav.js · panel-view.js ·
   alice-canvas.js · model-downloader.js · app-lock.js · intro-sequences.js;
   panel-view/alice-canvas 2026-11-13'te Komuta Paneli ile silindi).
   core.js bir gün IIFE'ye ya da modüle sarılsa yedisi birden token'sız `fetch`'e
   düşerdi — hata vermeden, yalnız 401 üreterek. Tam bu turda teşhis edilen
   kusurun sınıfı bu. Örtük bağımlılık açık hâle getirildi. */
window.authFetch = authFetch;

async function _authCheckAndInit() {
  // Auth gerekli mi? Korumalı /api/ping'e tokensiz çağır, 401 gelirse login ekranını göster
  try {
    const r = await fetch(`${BASE_URL}/api/ping`);
    if (r.status === 401) {
      /* 401'in İKİ sebebi olabilir ve ikisinin girişi farklıdır:
         ① AUTH_TOKEN (tünel kurulumu) → parolanın kendisi token'dır, `_authLogin`.
         ② Uygulama kilidi (Ayarlar → Güvenlik) → `/api/lock/unlock` + yüz seçeneği.
         Hangisi olduğunu backend söyler; tahmin edilmez. Kilit yoluysa perdeyi
         AppLock devralır (js/app-lock.js), aynı `#auth-screen` üstünde. */
      if (window.AppLock && await window.AppLock.gerekliMi()) {
        window.AppLock.ekraniGoster();
        return false;
      }
      _showAuthScreen();
      return false;
    }
  } catch (_) {}
  return true;
}

/* AppLock kilidi açtığında token'ı buraya yazar — `_authToken` modül kapsamında
   ve `authFetch` onu okuyor. sessionStorage tek başına YETMEZ: `_authToken`
   açılışta bir kez okunuyor, sonradan yazılan değeri görmez. */
window.setAuthToken = function (token) {
  _authToken = token || '';
  /* Token geldi — açılışta 401 yiyip bekleyen istekler serbest bırakılır
     (bkz. `_tokenBekle`). Kuyruk boşaltılırken KOPYALANIYOR: uyandırılan bir
     istek yeniden 401 alıp kuyruğa girerse, üzerinde döndüğümüz diziyi
     değiştirmiş olurdu. */
  if (_authToken && _tokenBekleyenler.length) {
    const uyandir = _tokenBekleyenler.splice(0, _tokenBekleyenler.length);
    uyandir.forEach((f) => { try { f(); } catch (_) {} });
  }
};

function _showAuthScreen() {
  document.getElementById('auth-screen').classList.remove('hidden');
  setTimeout(() => document.getElementById('auth-input')?.focus(), 100);
}

function _hideAuthScreen() {
  document.getElementById('auth-screen').classList.add('hidden');
  if (typeof window._runOpeningAnimation === 'function') window._runOpeningAnimation();
}

function _runBootAnimation() {
  const boot   = document.getElementById('boot-screen');
  const bar    = document.getElementById('boot-bar');
  const status = document.getElementById('boot-status');
  const app    = document.getElementById('app');
  if (!boot) { app.style.display = ''; return; }

  /* Anahtar tutulur, metin ÇİZİMDE çözülür. Dizi bir `const` olsaydı modül
     yüklenirken çözülür ve dil değişiminden sonra açılan ikinci bir boot
     animasyonu eski dilde koşardı — bu dalgada altı kez çıkan "modül düzeyi
     sabit" sınıfı. Burada dizi fonksiyonun içinde ama kural aynı. */
  const steps = [
    { pct: 30,  k: 'boot.baglaniyor' },
    { pct: 60,  k: 'boot.modeller-yukleniyor' },
    { pct: 85,  k: 'boot.sistem-hazirlaniyor' },
    { pct: 100, k: 'boot.hazir' },
  ];

  boot.classList.remove('hidden', 'fade-out');
  bar.style.width = '0%';

  let i = 0;
  function next() {
    if (i >= steps.length) {
      boot.classList.add('fade-out');
      setTimeout(() => {
        boot.classList.add('hidden');
      }, 700);
      return;
    }
    const s = steps[i++];
    bar.style.width = s.pct + '%';
    status.textContent = _t(s.k);
    setTimeout(next, i < steps.length ? 380 : 500);
  }
  setTimeout(next, 100);
}

async function _authLogin() {
  const input = document.getElementById('auth-input');
  const errEl = document.getElementById('auth-error');
  const token = input?.value?.trim();
  if (!token) return;
  const authBox = document.querySelector('#auth-screen .auth-box');
  const authBtn = authBox?.querySelector('.auth-actions .auth-btn:not(#auth-yuz-btn)');
  errEl.textContent = '';
  input.removeAttribute('aria-invalid');
  authBox?.setAttribute('aria-busy', 'true');
  if (authBtn) authBtn.disabled = true;

  try {
    const r = await fetch(`${BASE_URL}/api/ping`, {
      headers: { Authorization: `Bearer ${token}` },
    });
    if (r.ok) {
      _authToken = token;
      sessionStorage.setItem('aliceToken', token);
      _hideAuthScreen();
      connect();
      _startMemoryStatsPoll();
      // Tokensiz akışla simetri (bkz. aşağıdaki "Auth kapısı ve başlangıç bağlantıları"
      // bloğu): orada da connect + poll'den sonra bu ikisi çağrılır. Buraya eklenmemişti,
      // bu yüzden parolalı kurulumda model/dil seçici boş açılıyordu.
      initModelSelector();
      initLanguageSelector();
    } else {
      errEl.textContent = _t('giris.parola-yanlis');
      input.setAttribute('aria-invalid', 'true');
      input.value = '';
      input.focus();
    }
  } catch (e) {
    errEl.textContent = _t('giris.sunucuya-ulasilamiyor');
    input.setAttribute('aria-invalid', 'true');
  } finally {
    authBox?.removeAttribute('aria-busy');
    if (authBtn) authBtn.disabled = false;
  }
}

// Enter tuşu ile login
document.addEventListener('keydown', (e) => {
  if (e.key === 'Enter' && !document.getElementById('auth-screen').classList.contains('hidden')) {
    _authLogin();
  }
});

// ── Global Keyboard Shortcuts ──────────────────────────────── //
document.addEventListener('keydown', (e) => {
  const authScreen = document.getElementById('auth-screen');
  if (authScreen && !authScreen.classList.contains('hidden')) return;

  const inp = document.getElementById('msg-input');
  const tag = document.activeElement ? document.activeElement.tagName : '';
  const inInput = (tag === 'INPUT' || tag === 'TEXTAREA');

  // Ctrl+Tab → sonraki sekme · Ctrl+Shift+Tab → önceki (menü sırası, sonda başa
  // döner, gizli/kademe dışı sekmeler atlanır).  (2026-09-25, geliştirici): kişisel
  // AliceAi düz Tab kullanıyor; ürün müşteriye gittiği için düz Tab tarayıcının odak
  // gezintisine bırakıldı (klavyeyle gezen kullanıcı kaybetmesin). Yazarken de
  // çalışır — Ctrl+Tab metin girişinde bir iş yapmaz. Açık diyalogda dokunulmaz.
  // ⚠️ Tarayıcıdan açılan üründe Ctrl+Tab'ı tarayıcı yakalar (kendi sekmesi);
  // bu kısayol Electron penceresinde çalışır, tarayıcıda ☰ / F / 1-6 kalır.
  if (e.key === 'Tab' && e.ctrlKey && !e.altKey && !e.metaKey &&
      !(document.activeElement && document.activeElement.closest &&
        document.activeElement.closest('[role="dialog"], [aria-modal="true"], dialog[open]'))) {
    const btns = [...document.querySelectorAll('#tab-items .tab-btn:not([hidden])')];
    if (btns.length) {
      e.preventDefault();
      const i = btns.findIndex(b => b.getAttribute('aria-selected') === 'true');
      const hedef = btns[(i + (e.shiftKey ? -1 : 1) + btns.length) % btns.length];
      switchTab(hedef.dataset.tab);
      if (document.body.classList.contains('nav-acik')) hedef.focus({ preventScroll: true });
    }
    return;
  }

  // Alt+H → Hafıza paneli (B8: gör/sil/dışa aktar)
  if (e.altKey && (e.key === 'h' || e.key === 'H')) { e.preventDefault(); if (typeof openMemoryPanel === 'function') openMemoryPanel(); return; }

  // / → yazı alanına odak (zaten bir alandaysa değil). Küçültülmüşse önce açar.
  // Taslak SİLİNMEZ: eskiden `inp.value = ''` yarım mesajı yok ediyordu (kişisel 933779b'de düzeltildi).
  if (e.key === '/' && !inInput && !e.ctrlKey && !e.metaKey) {
    e.preventDefault();
    if (window.GirisKonsol) window.GirisKonsol.ac();
    if (inp) inp.focus();
  }

  // Escape → stop audio / cancel streaming
  if (e.key === 'Escape' && !inInput) {
    if (typeof stopAudio === 'function') stopAudio();
  }

  // Ctrl+E → export chat
  if ((e.ctrlKey || e.metaKey) && e.key === 'e') {
    e.preventDefault();
    if (typeof exportChat === 'function') exportChat();
  }

  // Ctrl+L → geçmişi temizle — ONAY sorar (UI-F001). Yazarken tetiklenmez:
  // metin kutusundaki Ctrl+L eskiden bütün geçmişi tek tuşla siliyordu.
  if ((e.ctrlKey || e.metaKey) && e.key === 'l' && !inInput) {
    e.preventDefault();
    if (typeof clearHistory === 'function') clearHistory();
  }

  // 1-11 → tab switching (only when not typing in an input)
  if (!inInput && !e.ctrlKey && !e.metaKey && !e.altKey) {
    // Sekmeler menü sırasıyla: CHAT · PLAN · AYAR · MAP · PANEL · AJAN · GALERİ · DOSYA. Rakamlar index.html'deki title etiketleriyle
    // ([n] …) BİREBİR olmalı — düğme "[2] PLAN" yazarken 2'nin AYAR'ı açması
    // 2026-08-03'e kadar süren bir kusurdu. Rakam SABİT (gizli sekme atlanıp
    // numara kaymaz); kademe dışı sekmeye switchTab sohbete düşürüp sebebini söyler.
    const tabMap = {
      '1':'chat', '2':'planner', '3':'hq', '4':'map', '5':'ajan', '6':'yedek', '7':'galeri', '8':'dosya'
    };
    if (tabMap[e.key]) { e.preventDefault(); switchTab(tabMap[e.key]); }
    // F → sekme menüsü aç/kapat (eski M/Alt+M kalktı — kişiselle aynı tuş)
    if (e.key === 'f' || e.key === 'F') { e.preventDefault(); toggleTabDropdown(); }
  }

});

let socket = null;
let currentStreamingBubble = null;
let collectedText = '';
let audioQueue = [];
let isPlayingAudio = false;
let _currentAudio = null;
let _mainAudioCtx = null;
let _mainAudioGain = null;
let _mainAudioSource = null;
let _transcriptionPending = false;
let _transcriptionText = '';
let _transcriptionTimer = null;

/* ── Ses veri yolu (CANLI kipi, 2026-10-11 — kişisel AliceAi'den) ──────
   Yalnız OKUMA kaydı: TTS çalarken analyser burada durur, ses bitince null.
   Tüketici: modes/sohbet-sahne.js CANLI kipi (ağız sesi izler). Tüketiciler
   yeni akış açmaz, destination'a bağlanmaz — yalnız getFloatTimeDomainData. */
window.YukiAudioBus = window.YukiAudioBus || { tts: null };

// ── δ: Lip-sync — Web Audio API RMS → VRM aa (mouthOpen) ────────────
// Paylaşılan AudioContext (kullanıcı etkileşiminden sonra oluşturulur)
let _lipSyncCtx    = null;
let _lipSyncRafId  = null;

function _getLipSyncCtx() {
  if (!_lipSyncCtx || _lipSyncCtx.state === 'closed') {
    _lipSyncCtx = new (window.AudioContext || window.webkitAudioContext)();
  }
  return _lipSyncCtx;
}

function _getMainAudioCtx() {
  if (!_mainAudioCtx || _mainAudioCtx.state === 'closed') {
    _mainAudioCtx = new (window.AudioContext || window.webkitAudioContext)();
    _mainAudioGain = _mainAudioCtx.createGain();
    _mainAudioGain.connect(_mainAudioCtx.destination);
    _mainAudioGain.gain.value = _audioMuted ? 0 : _audioVolume;
  }
  return _mainAudioCtx;
}

function _startLipSync(audioEl) {
  if (!yukiRive) return; // VRM aktif değilse lip-sync çalışmaz

  const ctx      = _getLipSyncCtx();
  const source   = ctx.createMediaElementSource(audioEl);
  const analyser = ctx.createAnalyser();
  analyser.fftSize = 512;
  const buf = new Float32Array(analyser.fftSize);

  // source → analyser → speakers (analyser arada dinliyor)
  source.connect(analyser);
  analyser.connect(ctx.destination);

  function tick() {
    analyser.getFloatTimeDomainData(buf);
    let sum = 0;
    for (let i = 0; i < buf.length; i++) sum += buf[i] * buf[i];
    const rms = Math.sqrt(sum / buf.length);
    // RMS → mouthOpen: 0.02 RMS = tam açık, hafif abartıyoruz (x10)
    yukiRive.setMouthOpen(Math.min(rms * 10, 1));
    _lipSyncRafId = requestAnimationFrame(tick);
  }
  _lipSyncRafId = requestAnimationFrame(tick);
}

function _startLipSyncFromAnalyser(analyser) {
  if (!yukiRive && !window.Yuki3D) return; // VRM veya 3D avatar aktif değilse çalışmaz
  const buf = new Float32Array(analyser.fftSize || 512);
  function tick() {
    analyser.getFloatTimeDomainData(buf);
    let sum = 0;
    for (let i = 0; i < buf.length; i++) sum += buf[i] * buf[i];
    const v = Math.min(Math.sqrt(sum / buf.length) * 10, 1);
    // Ağız değerini yukiRive'ye ve Yuki3D'ye yaz
    if (yukiRive) yukiRive.setMouthOpen(v);
    if (window.Yuki3D && window.Yuki3D.setMouth) window.Yuki3D.setMouth(v);
    _lipSyncRafId = requestAnimationFrame(tick);
  }
  _lipSyncRafId = requestAnimationFrame(tick);
}

function _stopLipSync() {
  if (_lipSyncRafId) {
    cancelAnimationFrame(_lipSyncRafId);
    _lipSyncRafId = null;
  }
  if (yukiRive) yukiRive.setMouthOpen(0);
  // Dış kontrol bırak
  if (window.Yuki3D && window.Yuki3D.setMouth) {
    try { window.Yuki3D.setMouth(null); } catch (_) {}
  }
}

function _setStopBtn(visible) {
  /* 🔴 2026-09-06: satır içi `style.display` YERİNE sınıf.
   * Sebep: `#input-container` bir grid ve düğmenin yeri CSS'te söyleniyor
   * (`grid-column: 5`). Satır içi display, yeri belirtmediği için düğmeyi
   * otomatik yerleşime bırakıyordu → 2. satırın 1. sütununa düşüyor, çubuğun
   * altında sol köşede duruyordu (geliştiricinin bildirdiği kayma).
   * Kapsayıcı da işaretleniyor: 5. sütun YALNIZ konuşurken açılmalı, kalıcı
   * olsaydı düğme gizliyken 44px ölü alan kalırdı. */
  const btn = document.getElementById('stop-audio-btn');
  if (btn) btn.classList.toggle('gorunur', !!visible);
  const kap = document.getElementById('input-container');
  if (kap) kap.classList.toggle('konusuyor', !!visible);
}

// ── localStorage Migration — Versiyonsuz şema → _v1 suffix (ADIM 0) ──
(function _migrateLocalStorageKeys() {
  const keys = [
    { old: 'yukiAudioVolume', new: 'yukiAudioVolume_v1' },
    { old: 'yukiAudioMuted', new: 'yukiAudioMuted_v1' },
    { old: 'yukiViewMode', new: 'yukiViewMode_v1' },
    { old: 'yukiCharacter', new: 'yukiCharacter_v1' },
    { old: 'yuki_amb_interval', new: 'yuki_amb_interval_v1' },
  ];
  try {
    keys.forEach(({ old, new: n }) => {
      const val = localStorage.getItem(old);
      if (val !== null) {
        localStorage.setItem(n, val);
        localStorage.removeItem(old);
      }
    });
  } catch (_) {}
})();

// Ses çıkışı tercihleri — CİHAZA ÖZEL + kalıcı (localStorage). Birden çok istemci
// (masaüstü + telefon) aynı backend'e bağlıyken sesi yalnızca istediğin cihazda çalmak
// için: sesi istemediğin cihazda 🔇 ile sustur — tercih o cihazda kalıcı kalır.
let _audioVolume = (() => { const v = parseFloat(localStorage.getItem('yukiAudioVolume_v1')); return isNaN(v) ? 1.0 : v; })();
let _audioMuted  = localStorage.getItem('yukiAudioMuted_v1') === '1';

function _persistAudioPrefs() {
  try {
    localStorage.setItem('yukiAudioVolume_v1', String(_audioVolume));
    localStorage.setItem('yukiAudioMuted_v1', _audioMuted ? '1' : '0');
  } catch (_) { /* localStorage yoksa sessizce geç */ }
}

// Kalıcı ses tercihini görsel kontrollere (ikon + slider) yansıt (yüklemede).
// 11-14: ikon durumu `data-durum` (acik/kisik/kapali) — eskiden textContent emojiye çevrilip
// düğmenin SVG'sini siliyordu (HALKA'da 🔈 görünüyordu). Çizim css/sohbet-kisisel.css.
function _syncAudioUI() {
  const icon = document.getElementById('vol-icon');
  if (icon) icon.dataset.durum = _audioMuted ? 'kapali' : _audioVolume < 0.5 ? 'kisik' : 'acik';
  const slider = document.getElementById('vol-slider');
  if (slider) slider.value = _audioMuted ? 0 : _audioVolume;
}
if (document.readyState === 'loading') window.addEventListener('DOMContentLoaded', _syncAudioUI);
else _syncAudioUI();

function _setVolume(val) {
  _audioVolume = parseFloat(val);
  _audioMuted = _audioVolume === 0;
  if (_mainAudioGain) _mainAudioGain.gain.value = _audioMuted ? 0 : _audioVolume;
  if (_currentAudio) _currentAudio.volume = _audioMuted ? 0 : _audioVolume;
  const icon = document.getElementById('vol-icon');
  if (icon) icon.dataset.durum = _audioMuted ? 'kapali' : _audioVolume < 0.5 ? 'kisik' : 'acik';
  _persistAudioPrefs();
}

function _toggleMute() {
  const slider = document.getElementById('vol-slider');
  if (_audioMuted) {
    _audioMuted = false;
    const v = _audioVolume || 0.8;
    if (slider) slider.value = v;
    _setVolume(v);
  } else {
    _audioMuted = true;
    if (_mainAudioGain) _mainAudioGain.gain.value = 0;
    if (_currentAudio) _currentAudio.volume = 0;
    const icon = document.getElementById('vol-icon');
    if (icon) icon.dataset.durum = 'kapali';
  }
  _persistAudioPrefs();
}

// Halka HUD (ve diğer modlar) için: TTS sesi gerçekten çalıyor mu sinyali.
// Halka bunu dinleyip ses sürerken kendini 'talking'de tutar (backend erken
// 'idle' yollasa bile), böylece "Yuki konuşuyor ama halka idle" desync'i biter.
function _emitSpeaking(on) {
  try { window.dispatchEvent(new CustomEvent('yuki:speaking', { detail: { on: !!on } })); } catch (_) {}
}

function stopAudio() {
  audioQueue = [];
  if (_mainAudioSource) {
    try { _mainAudioSource.stop(); } catch (_) {}
    _mainAudioSource = null;
  }
  if (_currentAudio) {
    try { _currentAudio.pause(); } catch (_) {}
    _currentAudio = null;
  }
  _stopLipSync();
  window.YukiAudioBus.tts = null;
  isPlayingAudio = false;
  _setStopBtn(false);
  _emitSpeaking(false);
}

async function playVoice(audioBase64) {
  try {
    console.log("[Audio] Ses çalınıyor...");
    const ctx = _getMainAudioCtx();
    if (ctx.state === 'suspended') await ctx.resume();

    // Base64 MP3 → ArrayBuffer → AudioBuffer (mobil autoplay bypass)
    const binary = atob(audioBase64);
    const bytes = new Uint8Array(binary.length);
    for (let i = 0; i < binary.length; i++) bytes[i] = binary.charCodeAt(i);
    const audioBuffer = await ctx.decodeAudioData(bytes.buffer);

    const source = ctx.createBufferSource();
    source.buffer = audioBuffer;
    _mainAudioSource = source;
    _currentAudio = null;

    // Gain node için ses seviyesi güncelle
    if (_mainAudioGain) _mainAudioGain.gain.value = _audioMuted ? 0 : _audioVolume;

    // Analyser KOŞULSUZ: CANLI kipi (sohbet-sahne.js) ağzı YukiAudioBus.tts'ten
    // okur; eskiden yalnız Rive/3D varken kuruluyordu. Maliyet tek AnalyserNode,
    // sinyal yolu aynı (source → analyser → gain).
    const analyser = ctx.createAnalyser();
    analyser.fftSize = 512;
    source.connect(analyser);
    analyser.connect(_mainAudioGain);
    window.YukiAudioBus.tts = analyser;
    if (yukiRive || window.Yuki3D) _startLipSyncFromAnalyser(analyser);

    source.onended = () => {
      console.log("[Audio] Ses bitti.");
      window.YukiAudioBus.tts = null;   // tüketiciler ölü düğümü okumasın
      _stopLipSync();
      _mainAudioSource = null;
      isPlayingAudio = false;
      if (audioQueue.length > 0) {
        playVoice(audioQueue.shift());
      } else {
        _setStopBtn(false);
        _emitSpeaking(false);
      }
    };

    isPlayingAudio = true;
    _emitSpeaking(true);
    _setStopBtn(true);
    source.start(0);
  } catch (err) {
    console.error("[Audio] Playback error:", err);
    window.YukiAudioBus.tts = null;
    _stopLipSync();
    _mainAudioSource = null;
    _currentAudio = null;
    isPlayingAudio = false;
    _setStopBtn(false);
    if (audioQueue.length > 0) playVoice(audioQueue.shift());
    else _emitSpeaking(false);
  }
}

// ── Karakter görseli ────────────────────────────────────────────────────────
// 2026-08-08: video sprite sistemi (VIDEOS / FB_VIDEOS / VIDEO_FALLBACK) kaldırıldı,
// 26 mp4 `_arsiv-medya/`ya arşivlendi (frontend/assets 121 MB → 32 MB). Tek görsel
// kaynağı karakterin fullbody PNG'si (11-14: yalnız Yuki; karakter eklenince listeye). Duygu/davranış artık görüntüyü DEĞİŞTİRMEZ;
// yalnız seçili karakter belirler.
// Kişisel Alice'ten aktarıldı (2026-08-07, `d73e817..d9bcff0`).
const CHARACTER_KEYS = ['yuki'];

function characterImage(key) {
  const k = CHARACTER_KEYS.includes(key) ? key : 'yuki';
  return '/ui/assets/characters/' + k + '_fullbody.png';
}

// Seçili karakteri chat-modes.js tutar; o yüklenmeden önce localStorage'a düş.
function currentCharacter() {
  try {
    if (typeof window.getCharacter === 'function') return window.getCharacter();
    // 🔴 `_migrateLocalStorageKeys` (yukarıda) 'yukiCharacter'ı `_v1`'e taşıyıp
    // eskisini SİLİYOR → versiyonsuz okuma daima null döner ve chat-modes.js
    // yüklenmeden önceki bu yedek yol her zaman 'yuki'ye düşerdi. core.js:1628
    // zaten `_v1` okuyordu; iki yer aynı soruya farklı cevap veriyordu.
    return localStorage.getItem('yukiCharacter_v1') || 'yuki';
  } catch (_) { return 'yuki'; }
}

// Bekleme (idle) klipleri — karakter başına EN FAZLA bir tane, döngüsel.
// 2026-10-04: eski TAM BOY modunun klibi; artık SOHBET sahnesinin VİDEO
// kipinde oynar (modes/sohbet-sahne.js). Listede olmayan karakterde VİDEO kipi yok.
// Şu an yalnız Yuki'nin var. Listede olmayan karakter sessizce durağan PNG'de kalır —
// eksik dosya için 404 yolu YOK, çünkü hiç istenmiyor.
// (Eski sistemde `yuki_fb_idle.mp4` FB_VIDEOS'un son çare fallback'iydi ama diskte
//  hiç yoktu → tam boy modda sessizce 404. Artık gerçekten var.)
const CHARACTER_VIDEOS = {
  yuki: '/ui/assets/characters/yuki_fb_idle.mp4',
};

// Klip 2,9 MB. Kullanıcı "veri tasarrufu" açtıysa ya da bağlantı yavaşsa klibi HİÇ
// indirme — durağan PNG zaten orada duruyor.
function _klipIndirilebilirMi() {
  try {
    const c = navigator.connection || navigator.mozConnection || navigator.webkitConnection;
    if (!c) return true;                       // bilgi yoksa engelleme
    if (c.saveData) return false;
    if (/(^|-)2g$/.test(c.effectiveType || '')) return false;   // 2g · slow-2g
    return true;
  } catch (_) { return true; }
}

// Sahne portresini (ve klibini) seçili karaktere sabitler.
// chat-modes.js `_applyCharacter` içinden de çağrılır → karakter değişince görsel de değişir.
window.applyCharacterImage = function (key) {
  const ch  = key || currentCharacter();
  const src = characterImage(ch);
  ['yuki-video', 'op-avatar-img'].forEach(id => {
    const el = document.getElementById(id);
    if (el && !el.src.endsWith(src)) el.src = src;
  });
  _applyFullbodyVideo(ch);
};

// Karakterin bu cihazda oynatılabilir bekleme klibi var mı? SOHBET sahnesi
// VİDEO kipini buna göre gösterir/gizler — klibi olmayan karaktere boş bir
// "VİDEO" düğmesi sunulmaz. Hareket azaltma açıksa da yok sayılır (klibi CSS
// zaten hiç göstermiyordu; düğme kalsaydı basınca hiçbir şey olmazdı).
function karakterKlibiVar(key) {
  if (!CHARACTER_VIDEOS[key || currentCharacter()]) return false;
  if (!_klipIndirilebilirMi()) return false;
  try { if (window.matchMedia && window.matchMedia('(prefers-reduced-motion: reduce)').matches) return false; }
  catch (_) {}
  return true;
}
window.karakterKlibiVar = karakterKlibiVar;

// SOHBET'in VİDEO kipinde (body.sk-video) karakterin idle klibini oynat, yoksa
// durağan portrede kal. Portre (#yuki-video) her zaman ALTTA durur → klip
// yüklenemezse (404/codec/autoplay reddi) altındaki görsel görünür kalır, boş kutu olmaz.
function _applyFullbodyVideo(key) {
  const v   = document.getElementById('yuki-fb-video');
  if (!v) return;
  const full = document.body.classList.contains('sk-video');
  const src  = karakterKlibiVar(key) ? CHARACTER_VIDEOS[key || currentCharacter()] : null;

  if (!full || !src) {
    v.classList.remove('on');
    if (!v.paused) v.pause();
    if (v.getAttribute('src')) { v.removeAttribute('src'); v.load(); }
    return;
  }

  if (!v.src.endsWith(src)) {
    v.onerror = () => { v.classList.remove('on'); };
    // Klip gerçekten oynamaya başlayınca görünür ol — 'canplay' yetmez, autoplay
    // reddedilirse siyah kare gösterirdik.
    v.onplaying = () => { v.classList.add('on'); };
    v.src = src;
    v.load();
  }
  const p = v.play();
  if (p && p.catch) p.catch(() => { v.classList.remove('on'); });
}
window.applyFullbodyVideo = _applyFullbodyVideo;

// Sekme/uygulama arkaya alınınca klibi durdur, dönünce sürdür.
// `pagehide` KULLANILMADI: Electron penceresi tepsiye gizlenince atmıyor.
document.addEventListener('visibilitychange', () => {
  const v = document.getElementById('yuki-fb-video');
  if (!v || !v.getAttribute('src')) return;
  if (document.hidden) { if (!v.paused) v.pause(); }
  else if (document.body.classList.contains('sk-video')) { v.play().catch(() => {}); }
});

// ── γ: VRM Animation System — askıya alındı (VRoid Studio asset bekleniyor)
// Aktifleştirmek için: importmap'i aç + aşağıdaki class'ı uncomment et
// const VRM_MODEL = '/ui/AvatarSample_A.vrm';
/*
class YukiVRM {
  constructor() {
    this._vrm          = null;
    this._ready        = false;
    this._clock        = null;
    this._renderer     = null;
    this._scene        = null;
    this._camera       = null;
    this._currentEmotion = 'neutral';
    this._mouthValue   = 0;
    this._blinkTimer   = 2 + Math.random() * 2;
    this._blinkPhase   = 'open'; // open | closing | closed | opening
    this._blinkProgress = 0;
  }

  async init() {
    try {
      const [THREE, { GLTFLoader }, { VRMLoaderPlugin, VRMUtils }] = await Promise.all([
        import('three'),
        import('three/addons/loaders/GLTFLoader.js'),
        import('https://cdn.jsdelivr.net/npm/@pixiv/three-vrm@2.1.3/lib/three-vrm.module.min.js'),
      ]);

      const canvas = document.getElementById('yuki-canvas');
      const pane   = document.getElementById('avatar-pane');
      const w = pane.clientWidth || 400;
      const h = pane.clientHeight || 700;

      // Renderer — premultipliedAlpha:false zorunlu (Electron şeffaf pencere + VRM)
      // premultipliedAlpha:true (default) → şeffaf piksel kenarlarında renk halesine yol açar.
      // alpha:true + premultipliedAlpha:false → doğru straight alpha compositing.
      this._renderer = new THREE.WebGLRenderer({
        canvas,
        alpha: true,
        antialias: true,
        premultipliedAlpha: false,
      });
      this._renderer.setPixelRatio(Math.min(window.devicePixelRatio, 2));
      this._renderer.setSize(w, h);
      this._renderer.outputColorSpace = THREE.SRGBColorSpace;
      this._renderer.setClearColor(0x000000, 0); // tam şeffaf arka plan

      // Scene + Camera (üst-beden portre görünümü)
      this._scene  = new THREE.Scene();
      this._camera = new THREE.PerspectiveCamera(18, w / h, 0.1, 20);
      this._camera.position.set(0, 1.25, 3.2);
      this._camera.lookAt(0, 1.05, 0);

      // Aydınlatma
      this._scene.add(new THREE.AmbientLight(0xffffff, 1.8));
      const key = new THREE.DirectionalLight(0xffeedd, 1.2);
      key.position.set(1, 2, 2);
      this._scene.add(key);
      const fill = new THREE.DirectionalLight(0xddeeff, 0.5);
      fill.position.set(-1, 0.5, 1);
      this._scene.add(fill);

      // VRM yükle
      const loader = new GLTFLoader();
      loader.register(parser => new VRMLoaderPlugin(parser));
      const gltf = await loader.loadAsync(VRM_MODEL);
      const vrm  = gltf.userData.vrm;
      VRMUtils.removeUnnecessaryJoints(gltf.scene);
      vrm.scene.rotation.y = 0; // VRM default +Z = kameraya dönük

      // VRM materyal alpha düzeltmesi — Z-fighting ve depth sorting sorunlarını giderir.
      // depthWrite:false → şeffaf katmanlar birbirini doğru sıralar (hair, clothes overlap).
      // alphaTest:0.5  → %50 alpha altı piksel tamamen kesilerek Z artefaktı önlenir.
      // renderOrder   → hair (2) > body (1) > default (0) — Painter's Algorithm sırası.
      vrm.scene.traverse(obj => {
        if (!obj.isMesh) return;
        const mats = Array.isArray(obj.material) ? obj.material : [obj.material];
        mats.forEach(mat => {
          if (!mat) return;
          if (mat.transparent || mat.opacity < 1.0) {
            mat.depthWrite  = false;   // şeffaf materyaller Z-buffer'a yazmaz
            mat.alphaTest   = 0.0;     // blended mode — threshold yok
            mat.transparent = true;
          } else {
            mat.alphaTest   = 0.5;     // opaque + punch-through alpha
            mat.transparent = false;
            mat.depthWrite  = true;
          }
          mat.needsUpdate = true;
        });
        // Hair mesh'lerini daha üst render order'a al
        const name = (obj.name || '').toLowerCase();
        if (name.includes('hair'))       obj.renderOrder = 2;
        else if (name.includes('body'))  obj.renderOrder = 1;
      });

      this._vrm = vrm;
      this._scene.add(vrm.scene);

      // A-pose: Raw bone'lar kullan (normalized yerine — daha güvenilir)
      this._lArm = vrm.humanoid.getRawBoneNode('leftUpperArm');
      this._rArm = vrm.humanoid.getRawBoneNode('rightUpperArm');
      console.log('[VRM] lArm bone:', this._lArm?.name, '| rArm bone:', this._rArm?.name);

      this._clock = new THREE.Clock();

      // Web Worker — animasyon math hesaplamalarını ana thread'den ayır
      // Worker yoksa (eski tarayıcı) inline fallback _animate() devreye girer
      if (typeof Worker !== 'undefined') {
        this._worker = new Worker('vrm-worker.js');
        this._worker.onmessage = ({ data }) => this._applyWorkerFrame(data);
      }

      this._ready = true;
      pane.classList.add('rive-mode'); // video gizle, canvas göster
      console.log('[VRM] Hazır!', vrm.meta?.name || '');

      // Boyut takibi
      new ResizeObserver(() => {
        const w2 = pane.clientWidth, h2 = pane.clientHeight;
        if (!w2 || !h2) return;
        this._camera.aspect = w2 / h2;
        this._camera.updateProjectionMatrix();
        this._renderer.setSize(w2, h2);
      }).observe(pane);

      this._animate();
    } catch (e) {
      console.error('[VRM] Yüklenemedi:', e);
    }
  }

  _animate() {
    requestAnimationFrame(() => this._animate());
    if (!this._vrm || !this._clock) return;
    const delta   = this._clock.getDelta();
    const elapsed = this._clock.elapsedTime;

    if (this._worker) {
      // Worker varsa — hesaplamayı Worker'a gönder, sonuç _applyWorkerFrame()'de gelir
      this._worker.postMessage({ type: 'tick', delta, elapsed, mouthValue: this._mouthValue });
    } else {
      // Fallback: Worker yoksa inline hesapla (eski tarayıcı/Electron eski sürüm)
      this._applyInlineFrame(delta, elapsed);
    }

    this._vrm.update(delta);
    this._renderer.render(this._scene, this._camera);
  }

  // Worker'dan gelen frame verisini VRM bone'larına uygula (main thread, mikro-süre).
  _applyWorkerFrame(data) {
    if (!this._vrm || data.type !== 'frame') return;
    try {
      const chest = this._vrm.humanoid.getNormalizedBoneNode('chest');
      if (chest) chest.rotation.x = data.chestX;
    } catch(_){}
    try {
      const head = this._vrm.humanoid.getNormalizedBoneNode('head');
      if (head) { head.rotation.y = data.head.y; head.rotation.x = data.head.x; }
    } catch(_){}
    if (this._lArm) this._lArm.rotation.z = data.arms.left;
    if (this._rArm) this._rArm.rotation.z = data.arms.right;
    try { this._vrm.expressionManager.setValue('blink', data.eyeValue); } catch(_){}
    try { this._vrm.expressionManager.setValue('aa',    data.mouthOpen); } catch(_){}
  }

  // Worker olmadığında inline hesaplama (fallback).
  _applyInlineFrame(delta, t) {
    this._tickBlink(delta);
    try { this._vrm.expressionManager.setValue('aa', this._mouthValue); } catch(_){}
    if (this._lArm) this._lArm.rotation.z = -Math.PI / 4.5;
    if (this._rArm) this._rArm.rotation.z =  Math.PI / 4.5;
    try {
      const chest = this._vrm.humanoid.getNormalizedBoneNode('chest');
      if (chest) chest.rotation.x = Math.sin(t * 0.7) * 0.014;
    } catch(_){}
    try {
      const head = this._vrm.humanoid.getNormalizedBoneNode('head');
      if (head) {
        head.rotation.y = Math.sin(t * 0.4) * 0.06;
        head.rotation.x = Math.sin(t * 0.31) * 0.04 - 0.03;
      }
    } catch(_){}
  }

  _tickBlink(delta) {
    this._blinkTimer -= delta;
    const CLOSE = 0.07, OPEN = 0.09;
    if (this._blinkPhase === 'open' && this._blinkTimer <= 0) {
      this._blinkPhase = 'closing'; this._blinkProgress = 0;
    } else if (this._blinkPhase === 'closing') {
      this._blinkProgress = Math.min(1, this._blinkProgress + delta / CLOSE);
      try { this._vrm.expressionManager.setValue('blink', this._blinkProgress); } catch(_){}
      if (this._blinkProgress >= 1) { this._blinkPhase = 'closed'; this._blinkTimer = 0.06; }
    } else if (this._blinkPhase === 'closed' && this._blinkTimer <= 0) {
      this._blinkPhase = 'opening'; this._blinkProgress = 1;
    } else if (this._blinkPhase === 'opening') {
      this._blinkProgress = Math.max(0, this._blinkProgress - delta / OPEN);
      try { this._vrm.expressionManager.setValue('blink', this._blinkProgress); } catch(_){}
      if (this._blinkProgress <= 0) { this._blinkPhase = 'open'; this._blinkTimer = 2 + Math.random() * 3; }
    }
  }

  setEmotion(emotion) {
    if (!this._ready) return;
    const MAP = { happy:'happy', sad:'sad', angry:'angry', surprised:'surprised', shy:'relaxed', tired:'neutral', neutral:'neutral' };
    const prev = MAP[this._currentEmotion] || 'neutral';
    if (prev !== 'neutral') try { this._vrm.expressionManager.setValue(prev, 0); } catch(_){}
    this._currentEmotion = emotion;
    const next = MAP[emotion] || 'neutral';
    if (next !== 'neutral') try { this._vrm.expressionManager.setValue(next, 1.0); } catch(_){}
  }

  setMouthOpen(val) {
    this._mouthValue = Math.max(0, Math.min(1, val));
  }

  setAction(type) {
    const A = { nod:'happy', wave:'happy', thinking:'neutral', surprised:'surprised', happy:'happy', sad:'sad', idle:'neutral' };
    this.setEmotion(A[type] || 'neutral');
  }

  setEyeOffset(x, y) { // gelecekte: bakış yönü
  }
}
*/
// VRM aktif değil — video sprite sistemi kullanılıyor
let yukiRive = null;

// 2026-08-08: `_playFbVideo` kaldırıldı — oynatacak fullbody videosu kalmadı.
// (Tam boy bekleme klibi artık `_applyFullbodyVideo` ile yönetiliyor: tek klip,
//  döngüsel, davranışa göre değişmiyor.)

// Davranış tetikleyicisi. İmza korundu: WS `behavior` mesajı, duygu HUD'u ve
// GameMode buradan besleniyor. Video yolu artık yok; sohbet/tam boy katmanında
// yalnız seçili karakterin görseli sabit durur.
function playBehaviorVideo(type) {
  // Oyun modu → GameMode kendi crossfade motorunu kullanır
  if (document.body.classList.contains('game-mode') && window.GameMode) {
    window.GameMode.playAnimation(type);
    return;
  }

  // VRM modu aktif ve hazırsa — VRM expression tetikle
  if (yukiRive) {
    yukiRive.setAction(type);
    return;
  }

  // Durağan mod: görsel seçili karakterde sabit kalır (davranışa göre değişmez).
  window.applyCharacterImage();
}


// ── Faz 13 — fal.ai Micro-Animation ─────────────────────────────────────────
const _FAL_ACTIONS = new Set([
  'eye_blink', 'eye_blink_double', 'breath',
  'head_tilt', 'look_away', 'look_at_user', 'head_nod',
]);
let _falErrorCount = 0;
const _FAL_MAX_ERRORS = 3;
let _falBusy = false;
let _falDisabledReported = false;

function _disableFalAnimations(reason) {
  _falErrorCount = _FAL_MAX_ERRORS;
  const pane = document.getElementById('avatar-pane');
  if (pane) pane.dataset.falDurum = 'devre-disi';
  if (_falDisabledReported) return;
  _falDisabledReported = true;
  console.warn(`FAL mikro animasyon katmanı kalıcı olarak devre dışı bırakıldı (${reason}).`);
}

/*  · C1: yetenek sorusunu HATA KODUYLA sorma.
   Eskiden ilk animasyon isteğinde `/clip` HEAD'i atılıyordu; FAL_KEY yoksa 503
   dönüyor, katman doğru şekilde kapanıyor ve tek bir console.warn basılıyordu —
   ama tarayıcı her 4xx/5xx için KENDİ "Failed to load resource" **error**
   satırını yazıyor. Sonuç: C1 kapısı (açılışta konsol hatası = 0) her müşteride
   düşüyordu, üstelik ürün hatasız çalışırken. Artık 200 dönen `/status` ucuna
   bir kez sorulur; sebep de tahmin değil, sunucunun bildiği cümle. */
let _falYetenek = null;   // null = henüz sorulmadı · true/false = ölçüldü

async function _falKullanilabilirMi() {
  if (_falYetenek !== null) return _falYetenek;
  try {
    const r = await authFetch('/api/live-portrait/status');
    if (!r.ok) {
      _falYetenek = false;
      _disableFalAnimations(`durum ucu ${r.status}`);
      return false;
    }
    const d = await r.json();
    _falYetenek = d.available !== false;   // alan yoksa (eski backend) engelleme
    if (!_falYetenek) _disableFalAnimations(d.unavailable_reason || 'sunucu kullanılamaz bildirdi');
  } catch (e) {
    // Ağ hatası kalıcı bir yargı değil — bir sonraki denemede yeniden sorulsun.
    console.warn('[yuki] mikro animasyon durumu okunamadı, bu tur atlanıyor:', e);
    return false;
  }
  return _falYetenek;
}

async function playFalAnimation(action) {
  if (_falBusy) return;
  if (_falErrorCount >= _FAL_MAX_ERRORS) return;
  if (!(await _falKullanilabilirMi())) return;
  const overlay = document.getElementById('yuki-fal-overlay');
  if (!overlay) return;
  _falBusy = true;
  try {
    const url = `/api/live-portrait/clip?action=${encodeURIComponent(action)}&token=${_authToken}`;
    // Fetch first to check HTTP status — avoids silent video element errors
    let resp;
    try { resp = await fetch(url, {method:'HEAD'}); } catch(e) { resp = {ok:false,status:0}; }
    if (!resp.ok) {
      // 503 = service down → disable permanently
      if (resp.status === 503 || resp.status === 0) {
        _disableFalAnimations(`HEAD ${resp.status || 'ağ hatası'}`);
      } else {
        _falErrorCount++;
        if (_falErrorCount >= _FAL_MAX_ERRORS) _disableFalAnimations(`HEAD ${resp.status}`);
      }
      return;
    }
    overlay.src = url;
    overlay.load();
    await new Promise((res, rej) => {
      overlay.oncanplay = res;
      overlay.onerror = rej;
      setTimeout(rej, 8000);
    });
    overlay.style.opacity = '1';
    overlay.play().catch(() => {});
    await new Promise((res) => { overlay.onended = res; setTimeout(res, 6000); });
  } catch (e) {
    _falErrorCount++;
    if (_falErrorCount >= _FAL_MAX_ERRORS) _disableFalAnimations('oynatma hatası');
  } finally {
    overlay.style.opacity = '0';
    overlay.src = '';
    _falBusy = false;
  }
}

// 2026-08-08: iki video yardımcısı kaldırıldı — ikisi de <video> API'sine bağlıydı
// (`.play()` / `.paused` / `.currentTime` / `ended` olayı), eleman artık <img>:
//   ① mobilde sekme dönüşünde donmuş videoyu yeniden başlatan dinleyici
//   ② idle loop'un başa sarmasını gizleyen crossfade sarmalayıcısı
// Durağan görselde ikisinin de karşılığı yok.

// Açılışta seçili karakterin görselini uygula (chat-modes.js henüz yüklenmemiş
// olabilir → localStorage'a düşer).
document.addEventListener('DOMContentLoaded', function () {
  if (window.applyCharacterImage) window.applyCharacterImage();
});

let thinkingBubble = null;

/* 🔴 i18n (2026-09-22): rozet metni CSS'te `content: 'HAZIR'` diye
   SABİTTİ → EN kullanıcı "HAZIR" görüyordu ve hiçbir canlı tur görmedi, çünkü
   turlar DOM metnini ölçer, sözde-eleman içeriğini değil. Metin artık öznitelikte;
   CSS `content: attr(data-durum-metni)` ile okur. */
const _DURUM_ANAHTAR = {
  'state-idle': 'durum.hazir', 'state-listening': 'durum.dinliyor',
  'state-thinking': 'durum.dusunuyor', 'state-talking': 'durum.konusuyor',
  'state-busy': 'durum.mesgul',
};
function _durumMetniYaz() {
  const b = document.getElementById('state-badge');
  if (!b) return;
  const k = _DURUM_ANAHTAR[b.className] || 'durum.mesgul';
  b.setAttribute('data-durum-metni', _t(k));
}
_durumMetniYaz();

function updateState(s) {
  const b = document.getElementById('state-badge');
  const stateMap = {
    'idle': 'state-idle',
    'listening': 'state-listening',
    'thinking': 'state-thinking',
    'talking': 'state-talking',
  };
  b.className = stateMap[s] || 'state-busy';
  _durumMetniYaz();

  // E2: Thinking indicator — thinking durumunda göster
  if (s === 'thinking' && !thinkingBubble) {
    const container = document.getElementById('messages');
    const row = document.createElement('div');
    row.className = 'msg-row yuki';
    row.id = 'thinking-row';
    const av = document.createElement('div');
    av.className = 'msg-avatar';
    av.textContent = '❄';
    row.appendChild(av);
    const bubble = document.createElement('div');
    bubble.className = 'msg-bubble thinking-indicator';
    bubble.innerHTML = '<span></span><span></span><span></span>';
    row.appendChild(bubble);
    container.appendChild(row);
    container.scrollTop = container.scrollHeight;
    thinkingBubble = row;
  } else if (s !== 'thinking' && thinkingBubble) {
    thinkingBubble.remove();
    thinkingBubble = null;
  }

  // Always-on: idle'a geçince otomatik mikrofonu yeniden başlat
  if (s === 'idle' && alwaysOnMode && !isRecording) {
    setTimeout(() => {
      if (alwaysOnMode && !isRecording) $micBtn.click();
    }, 600);
  }

  // FAZ 3a: yuki-3d.js'ye durum sinyali gönder
  try { document.dispatchEvent(new CustomEvent('yuki-state', { detail: { state: s } })); } catch (_) {}
}

function _fmtTime() {
  return new Date().toLocaleTimeString(_yerel(), { hour: '2-digit', minute: '2-digit' });
}

// ── Bildirim ───────────────────────────────────────────── //
//  (2026-08-28): gövde `js/bildirim.js`'e DEVREDİLDİ. Ad korundu —
// 21 çağrı yeri var ve hiçbirini değiştirmek gerekmedi.
//
// Eski gövde `#toast-container` + `.toast` kullanıyordu; iki kusuru vardı:
//   ① `.toast` eski renk sözlüğünde (--accent/--gold/#ff1744) yazılmıştı →
//      FAZ 7'nin "3 sözlük → 1" kararının dışında kaldı, üç temada ölçülmedi.
//   ② `type` olarak sahada `'err'` gönderiliyordu (tab-switcher.js ×5) ama
//      style.css yalnız `.toast-error` tanımlıyordu → hata bildirimleri
//      KIRMIZI DEĞİL, varsayılan kenarla çiziliyordu. Kimse fark etmedi.
// Tip adlarının çevirisi artık tek yerde: bildirim.js::TIPLER.
function showToast(msg, type = '', duration = 4000) {
  if (typeof window.bildir === 'function') return window.bildir(msg, type, duration);
  // bildirim.js yüklenmediyse mesaj YUTULMAZ — C4 sessiz başarısızlığı yasaklıyor.
  console.warn('[yuki] bildirim:', type || 'bilgi', msg);
  return null;
}

// ── Quick Actions ──────────────────────────────────────── //
function qaScreenshot() {
  const inp = document.getElementById('msg-input');
  if (!inp) return;
  inp.value = _t('komut.ekran.doldur');
  sendMessage();
}

function qaClipboard() {
  navigator.clipboard.readText().then(text => {
    if (!text.trim()) return showToast(_t('hizli.pano-bos'), 'warn');
    const inp = document.getElementById('msg-input');
    if (!inp) return;
    inp.value = text.trim();
    inp.focus();
    inp.dispatchEvent(new Event('input'));
    showToast(_t('hizli.pano-yapistirildi'), 'ok', 1500);
  }).catch(() => showToast(_t('hizli.pano-izin-yok'), 'warn'));
}

function qaSearch() {
  const inp = document.getElementById('msg-input');
  if (!inp) return;
  inp.value = _t('hizli.ara-oneki');
  inp.focus();
  inp.setSelectionRange(inp.value.length, inp.value.length);
}

// ── Companion ekibi (R5 FAZ 3) ─────────────────────────── //
// Düğme keşfedilebilirlik içindir (açık kaynak sürümde kilit yok).
// ⚠️ Düğme mesajı GÖNDERMEZ, yazma alanını doldurur: hedefi kullanıcı yazar,
// gönderme kararı onda kalır. Maliyet onayı ayrıca sorulacak (backend).
// Varsayılan açık; `/api/yetki` → features yalnız meclis/uzman ayrımı için okunur.
let _ekipYetki = { team: true, council: true };

async function _ekipYetkiSenkronla() {
  try {
    const d = await (window.ModeData
      ? window.ModeData.getJSON('/api/yetki')
      : fetch('/api/yetki').then(r => r.json()));
    const f = (d && d.features) || {};
    if ('companion_team' in f || 'companion_council' in f) {
      _ekipYetki = { team: f.companion_team !== false, council: f.companion_council !== false };
    }
  } catch (e) { /* bilinmiyor → varsayılan açık kalır */ }
  _ekipDugmesiTazele();
}
window.EKIP_KILIT_SENKRON = _ekipYetkiSenkronla;
document.addEventListener('DOMContentLoaded', _ekipYetkiSenkronla);

function _ekipDugmesiTazele() {
  const btn = document.getElementById('team-btn');
  if (!btn) return;
  btn.dataset.locked = '0';
  const kilit = btn.querySelector('.mi-kilit');
  if (kilit) kilit.remove();
  btn.title = _t('ekip.dugme-acik');
}

async function ekibeSor() {
  const inp = document.getElementById('msg-input');
  if (!inp) return;
  // Meclis (run_team) varsa "ekiple", yoksa "bir uzmana".
  inp.value = _ekipYetki.council ? _t('ekip.oneki-meclis') : _t('ekip.oneki-uzman');
  inp.focus();
  inp.setSelectionRange(inp.value.length, inp.value.length);
  // Menüyü burada kapatmıyoruz: `document` dinleyicisi (⋯ menüsü) öğeye
  // tıklanınca zaten kapatıyor.
}

// ── Chat Export ────────────────────────────────────────── //
function exportChat() {
  const rows = document.querySelectorAll('#messages .msg-row');
  if (!rows.length) return showToast(_t('aktar.mesaj-yok'), 'warn');
  /* 🔑 Dışa aktarma DİSKE YAZAR ve yazdığı dili dondurur. Blok 10'da
     `reminders.json::human` tam bu yüzden düzeltilmişti — ama orada kayıt
     SONRADAN OKUNUYOR, burada dosya kullanıcının aldığı bir ANLIK GÖRÜNTÜ.
     Anlık görüntünün o anki arayüz dilinde olması doğru; geri okunmuyor. */
  let md = _t('aktar.baslik') + '\n\n';
  md += `> ${_t('aktar.tarih', { tarih: new Date().toLocaleString(_yerel()) })}\n\n---\n\n`;
  rows.forEach(row => {
    if (row.id === 'thinking-row') return;
    const isYuki = row.classList.contains('yuki');
    const bubble = row.querySelector('.msg-bubble');
    if (!bubble) return;
    const content = isYuki ? bubble.innerText : bubble.textContent;
    if (!content.trim()) return;
    md += isYuki
      ? `**${_t('aktar.konusan-yuki')}** ${content.trim()}\n\n`
      : `**${_t('aktar.konusan-sen')}** ${content.trim()}\n\n`;
  });
  const blob = new Blob([md], { type: 'text/markdown' });
  const a = document.createElement('a');
  a.href = URL.createObjectURL(blob);
  /* ⚪ Dosya adı BİLEREK çevrilmedi (`yuki-hafiza.json` ile aynı karar):
     ad bir kimliktir, dile göre değişirse aynı kullanıcının arşivi iki farklı
     desende birikir ve eski dosyalar aranamaz olur. */
  a.download = `yuki-sohbet-${Date.now()}.md`;
  a.click();
  URL.revokeObjectURL(a.href);
  showToast(_t('aktar.tamamlandi'), 'ok', 2000);
}

// qaExport alias
const qaExport = exportChat;

function _renderMarkdown(el, text) {
  if (window.marked) {
    let html = window.marked.parse(text, { breaks: true, gfm: true });
    // ── XSS Prevention (SEC-F001): DOMPurify yüklü ise kullan, aksi text fallback ──
    if (window.DOMPurify) {
      // DOMPurify mevcut: HTML rendered markup + sanitized
      html = window.DOMPurify.sanitize(html);
      el.innerHTML = html;
      el.classList.add('md-rendered');
      if (window.Prism) Prism.highlightAllUnder(el);
      // Add copy button to each <pre> block
      el.querySelectorAll('pre').forEach(pre => {
        const btn = document.createElement('button');
        btn.className = 'code-copy-btn';
        btn.textContent = 'COPY';
        btn.onclick = () => {
          const code = pre.querySelector('code');
          navigator.clipboard.writeText(code ? code.innerText : pre.innerText).then(() => {
            btn.textContent = 'OK';
            btn.classList.add('copied');
            setTimeout(() => { btn.textContent = 'COPY'; btn.classList.remove('copied'); }, 1500);
          });
        };
        pre.appendChild(btn);
      });
    } else {
      // DOMPurify yüklü değil: safe fallback — düz metin
      el.textContent = text;
      el.classList.remove('md-rendered');
    }
  } else {
    el.textContent = text;
  }
}

function scrollToBottom() {
  const c = document.getElementById('messages');
  c.scrollTo({ top: c.scrollHeight, behavior: 'smooth' });
}

function addMessage(role, text) {
  const container = document.getElementById('messages');
  const emptyState = document.getElementById('chat-empty-state');
  if (emptyState) emptyState.classList.add('hidden');
  const row = document.createElement('div');
  row.className = `msg-row ${role}`;

  // Yuki avatar thumbnail (sol alt köşede)
  if (role === 'yuki') {
    const av = document.createElement('div');
    av.className = 'msg-avatar';
    av.textContent = '❄';
    row.appendChild(av);
  }

  const wrap = document.createElement('div');
  wrap.style.cssText = 'display:flex;flex-direction:column;max-width:85%;position:relative;';

  const bubble = document.createElement('div');
  bubble.className = 'msg-bubble';

  if (role === 'yuki' && text) {
    _renderMarkdown(bubble, text);
  } else {
    bubble.textContent = text;
  }

  // Copy button
  const copyBtn = document.createElement('button');
  copyBtn.className = 'msg-copy-btn';
  copyBtn.textContent = _t('sohbet.kopyala');
  const _rawText = text || '';
  copyBtn.onclick = () => {
    navigator.clipboard.writeText(_rawText).then(() => {
      copyBtn.textContent = _t('sohbet.kopyalandi');
      copyBtn.classList.add('copied');
      setTimeout(() => { copyBtn.textContent = _t('sohbet.kopyala'); copyBtn.classList.remove('copied'); }, 1500);
    });
  };

  const ts = document.createElement('span');
  ts.className = 'msg-ts';
  ts.textContent = _fmtTime();

  wrap.appendChild(bubble);
  wrap.appendChild(copyBtn);
  wrap.appendChild(ts);
  row.appendChild(wrap);
  container.appendChild(row);
  container.scrollTop = container.scrollHeight;
  return bubble;
}

// Scroll-to-bottom butonu görünürlüğü
document.addEventListener('DOMContentLoaded', () => {
  const msgs = document.getElementById('messages');
  if (!msgs) return;

  // Kalıcı sohbet geçmişini geri yükle (lite memory — kapat/aç sonrası devam)
  (async () => {
    try {
      const r = await authFetch(`${BASE_URL}/api/chat/history`);
      if (!r.ok) return;
      const data = await r.json();
      for (const m of (data.messages || [])) {
        const b = addMessage(m.role === 'user' ? 'user' : 'yuki', m.content);
        // HALKA son-cevap satırı (hud-ring.js) geçmişi yeni cevap sanmasın
        const r = b && b.closest('.msg-row'); if (r) r.dataset.gecmis = '1';
      }
      msgs.scrollTop = msgs.scrollHeight;
    } catch (e) { /* backend henüz hazır değil / offline — sessiz geç */ }
  })();

  msgs.addEventListener('scroll', () => {
    const btn = document.getElementById('scroll-btn');
    const distFromBottom = msgs.scrollHeight - msgs.scrollTop - msgs.clientHeight;
    if (btn) btn.classList.toggle('visible', distFromBottom > 100);
  });

  // Mobil: transkripsiyon swipe-to-dismiss
  // → sola kaydır: iptal | sağa kaydır: onayla
  const inputArea = document.getElementById('input-area');
  let _touchStartX = 0;
  inputArea.addEventListener('touchstart', (e) => {
    _touchStartX = e.touches[0].clientX;
  }, { passive: true });
  inputArea.addEventListener('touchend', (e) => {
    if (!_transcriptionPending) return;
    const dx = e.changedTouches[0].clientX - _touchStartX;
    if (Math.abs(dx) < 60) return; // yeterli mesafe değil
    const inp = document.getElementById('msg-input');
    if (dx < 0) {
      // Sola → iptal
      clearTimeout(_transcriptionTimer);
      _transcriptionPending = false;
      inp.value = ''; inp.style.height = 'auto';
    } else {
      // Sağa → onayla
      sendMessage();
    }
  }, { passive: true });
});

// ── Avatar — Göster / Gizle ─────────────────────────
// 11-15 kararı: kişisel Yuki'deki gibi iki durum (göster ↔ gizle). Eski üç
// kademeden kalan 'kucuk' kaydı 'buyuk' (göster) okunur. Dar kabukta Büyük'ün
// otomatik Küçük'e inmesi (`_etkinAvatar`) yerleşim kuralıdır, kullanıcı kademesi değil.
const _AVATAR_AYARLARI = ['buyuk', 'gizli'];
const _AVATAR_DEPO_ANAHTARI = 'yuki_avatar_v1';
let _avatarAyar = _avatarAyarOku();
let _avatarResizeObserver = null;

function _avatarAyarOku() {
  const kayitli = localStorage.getItem(_AVATAR_DEPO_ANAHTARI);
  return kayitli === 'gizli' ? 'gizli' : 'buyuk';
}

// electron/pencere-modu.js::etkinAvatar ile aynı saf kural. Main tarafındaki
// dosya renderer'a import edilmez; kullanıcının ayarı hiçbir zaman değiştirilmez.
function _etkinAvatar(ayar, kabukGenisligi) {
  return ayar === 'buyuk' && kabukGenisligi < 380 ? 'kucuk' : ayar;
}

/* 🔑 Eşleme FONKSİYONUN İÇİNDE, modül düzeyinde bir `const` DEĞİL. Modül
   düzeyine alınsaydı çözülmüş etiketler dosya yüklenirken donar ve dil
   değişiminde eski dilde kalırdı — bu dalgada altı kez çıkan sınıf. Anahtarlar
   (`buyuk`/`kucuk`/`gizli`) VERİDİR: `localStorage`'a yazılıyor ve
   `electron/pencere-modu.js::etkinAvatar` aynı adları biliyor → çevrilmez. */
function _avatarEtiketi(ayar) {
  return _t({ buyuk: 'avatar.buyuk', kucuk: 'avatar.kucuk', gizli: 'avatar.gizli' }[ayar]);
}

function _avatarDurumunuUygula(kabukGenisligi) {
  const app = document.getElementById('app');
  const pane = document.getElementById('avatar-pane');
  const btn = document.getElementById('avatar-toggle');
  if (!app || !pane || !btn) return;

  const etkin = _etkinAvatar(_avatarAyar, kabukGenisligi);
  const sonraki = _AVATAR_AYARLARI[
    (_AVATAR_AYARLARI.indexOf(_avatarAyar) + 1) % _AVATAR_AYARLARI.length
  ];
  const otomatikNot = etkin !== _avatarAyar
    ? ' ' + _t('avatar.dar-alanda', { etkin: _avatarEtiketi(etkin) })
    : '';

  // `.collapsed` eski iki durumlu düğmeden kalmış uyumluluk sınıfıdır. Yeni tek
  // kaynak data-avatar-ayar; sınıfın yanlışlıkla düzeni ezmesine izin verilmez.
  pane.classList.remove('collapsed');
  app.dataset.avatarAyar = _avatarAyar;
  app.dataset.avatarEtkin = etkin;
  btn.dataset.avatarAyar = _avatarAyar;
  btn.dataset.avatarEtkin = etkin;
  btn.classList.toggle('active', etkin !== 'gizli');

  // Kişiseldeki gibi düğme YAPILACAK işi söyler: "Karakteri gizle" / "Karakteri göster".
  const eylem = _t(sonraki === 'gizli' ? 'avatar.gizle-eylem' : 'avatar.goster-eylem');
  btn.setAttribute('aria-label', eylem + otomatikNot);
  btn.setAttribute('aria-pressed', String(_avatarAyar !== 'gizli'));
  btn.title = eylem;
}

function toggleAvatarPane() {
  const sira = (_AVATAR_AYARLARI.indexOf(_avatarAyar) + 1) % _AVATAR_AYARLARI.length;
  _avatarAyar = _AVATAR_AYARLARI[sira];
  localStorage.setItem(_AVATAR_DEPO_ANAHTARI, _avatarAyar);
  const kabuk = document.querySelector('.kabuk');
  _avatarDurumunuUygula(kabuk?.getBoundingClientRect().width || 0);
}

document.addEventListener('DOMContentLoaded', () => {
  const kabuk = document.querySelector('.kabuk');
  if (!kabuk) return;

  _avatarDurumunuUygula(kabuk.getBoundingClientRect().width);
  if ('ResizeObserver' in window) {
    _avatarResizeObserver = new ResizeObserver((entries) => {
      const genislik = entries[0]?.contentRect.width ?? kabuk.getBoundingClientRect().width;
      _avatarDurumunuUygula(genislik);
    });
    _avatarResizeObserver.observe(kabuk);
  }
});

// ── Görünüm modu ─────────────────────────────────────
// 🔄 2026-10-04: KLASİK/TAM BOY ikilisi burada yaşıyordu (`_viewMode`,
// `body.fullbody-mode`, düğmeye "CHAT"/"FULL" yazımı). İkisi tek SOHBET modunda
// birleşti: mod listesinin ve düğme etiketinin TEK sahibi `modes/chat-modes.js`,
// klibin kipi `modes/sohbet-sahne.js`. Burada yalnız klibin durumunu tazeleyen
// kanca kalır — dil değişince ve açılışta çağrılıyor. Etiket yazmaz: iki dosya
// aynı düğmeye yazarsa aynı alanın iki sahibi olur ('da ölçülen arıza).
// `toggleViewMode` chat-modes.js'te menü açıcıyla değiştirilir; bu tanım yalnız o
// dosya yüklenmeden önceki tıklamaya karşı emniyettir.
function toggleViewMode() {}

function _applyViewMode() {
  document.body.classList.remove('fullbody-mode');   // eski oturumdan kalan sınıf
  if (window.applyFullbodyVideo) window.applyFullbodyVideo();
}

document.addEventListener('DOMContentLoaded', () => { _applyViewMode(); });

let _wsRetryDelay = 2000;
let _wsRetryTimer = null;

/* Bağlantı durumu TEK kaynaktan ( M3). Hap WebSocket'e, çevrimdışı şeridi
   `navigator.onLine`'a bakıyordu: ağ düşünce şerit "Bağlantı yok" derken hap "BAĞLI",
   backend durunca hap "BAĞLANTI YOK" derken şerit susuyordu (ikisi de ölçüldü).
   Artık ikisi aynı cevabı okur: WS açık VE ağ var. Şerit `yuki-baglanti` olayını
   dinler; argümansız çağrı yalnız yeniden çizer (dil değişimi, online/offline). */
let _wsAcik = false;
/* null = bilinmiyor (rozet eski iki hâlde kalır), true/false = ölçüldü — `_anahtarYokla`. */
let _anahtarHazir = null;
let _baglantiSon = null;
window.yukiBaglanti = () => _baglantiSon;

function _setWsPill(online) {
  if (typeof online === 'boolean') _wsAcik = online;
  online = _wsAcik && navigator.onLine !== false;
  if (online !== _baglantiSon) {
    _baglantiSon = online;
    window.dispatchEvent(new CustomEvent('yuki-baglanti', { detail: { bagli: online } }));
  }
  const pill = document.getElementById('ws-pill');
  const lbl  = document.getElementById('ws-label');
  if (!pill) return;
  /* Üçüncü hâl: backend bağlı ama yapay zekâ servisi kurulu değil. Eskiden rozet yeşil
     "BAĞLI" derken HQ › Anahtar "Henüz bağlı değil" diyordu (goz 11-13, demo kipi) —
     kullanıcı Yuki'nin cevap vereceğini sanıyordu. Hüküm Anahtar ekranıyla AYNI kaynaktan
     (`/api/llm/key/status`, `set || yerel`). Durum bilinmiyorsa (istek düştü) eski hâl. */
  const anahtarYok = online && _anahtarHazir === false;
  pill.className = !online ? 'offline' : (anahtarYok ? 'online anahtar-yok' : 'online');
  pill.title = anahtarYok ? _t('ust.anahtar-yok-ipucu') : '';
  const rozetA = document.getElementById('state-badge');
  if (rozetA) rozetA.setAttribute('data-anahtar-metni', _t('ust.anahtar-yok'));
  if (lbl && anahtarYok) { lbl.textContent = _t('ust.anahtar-yok'); return; }
  // Durum rozetiyle (#state-badge) karışmasın diye BAĞLANTIYI anlatan sözcük
  // seçildi — ikisi de 'ONLINE' derken kullanıcı hangisinin ne olduğunu ayırt
  // edemiyordu (2026-08-03).
  /* `ust.baglanti-yok` Dalga 1'de `index.html` için yazıldı; burada YENİDEN
     tanımlamıyoruz — aynı cümlenin iki anahtarı olsaydı biri çevrilip öbürü
     unutulabilirdi. */
  if (lbl) lbl.textContent = _t(online ? 'ust.bagli' : 'ust.baglanti-yok');
  // Telefonda (HALKA) rozet görsel olarak çekilir; kopukluğu durum rozeti söyler (kabuk.css).
  const rozet = document.getElementById('state-badge');
  if (rozet) rozet.setAttribute('data-baglanti-metni', _t('ust.baglanti-yok'));
}
window.addEventListener('online',  () => _setWsPill());
window.addEventListener('offline', () => _setWsPill());

/* Anahtar hâli (`_anahtarHazir`, yukarıda) bağlanınca ve anahtar kaydedilince/değişince
   (`yuki-anahtar-degisti`) tazelenir. */
async function _anahtarYokla() {
  try {
    const r = await authFetch(`${BASE_URL}/api/llm/key/status`);
    if (!r.ok) return;                       // 401/403 = oturum kilitli, veri değil
    const d = await r.json();
    _anahtarHazir = !!(d && (d.set || d.yerel));
  } catch (_) { return; }
  _setWsPill();
  // Halka (merkez · durum satırı · kayan yazı) ve model çipi aynı hükmü okur — tek kaynak.
  window.dispatchEvent(new CustomEvent('yuki-anahtar-durum', { detail: { hazir: _anahtarHazir } }));
}
/* null = bilinmiyor (yoklanmadı / oturum reddi), true/false = ölçüldü. */
window.yukiAnahtarHazir = () => _anahtarHazir;
window.addEventListener('yuki-anahtar-degisti', _anahtarYokla);

function _scheduleReconnect() {
  if (_wsRetryTimer) return;
  const delay = _wsRetryDelay;
  _wsRetryDelay = Math.min(_wsRetryDelay * 1.5, 30000);
  console.log(`WS reconnect in ${(delay / 1000).toFixed(1)}s…`);
  _wsRetryTimer = setTimeout(() => { _wsRetryTimer = null; connect(); }, delay);
}

// ── Tool Approval Modal ──────────────────────────────
function _showToolApprovalModal(approvalId, toolName, args, timeoutSecs, sunum) {
  const overlay = document.createElement('div');
  overlay.style.cssText = `position: fixed; top: 0; left: 0; right: 0; bottom: 0; background: rgba(0,0,0,0.6); display: flex; align-items: center; justify-content: center; z-index: 10000; padding: 16px; box-sizing: border-box;`;

  const modal = document.createElement('div');
  modal.style.cssText = `background: var(--yuzey-2, #1f1e26); border: 1px solid var(--kenar-guclu, #605e6a); border-radius: 8px; padding: 24px; max-width: 500px; box-shadow: 0 8px 32px rgba(0,0,0,0.6); font-family: var(--font, system-ui, sans-serif);`;
  /* Göz tur 1 (AJAN): kutu sekmenin orantılı fontunda; eş aralıklı yalnız ham JSON'da (geliştirici görünümü). */

  // `sunum` varsa insan diline çevrilmiş kutu çizilir (maliyet onayı gibi
  // KULLANICI kararı gerektiren durumlar), yoksa eski geliştirici görünümü
  // (araç adı + ham JSON) — geri uyumlu.
  const title = document.createElement('h3');
  /* ⚠️ `sunum.baslik`/`sunum.mesaj` BACKEND'den gelir ve orası kendi dil
     kataloğunu kullanır (`mesajlar/`); burada yalnız YEDEK metin çevrilir. */
  title.textContent = (sunum && sunum.baslik) || _t('onay.baslik');
  /* Renkler ürün token'larından (10-04): eski --text/--text-dim ürün tokens.css'te YOK →
     başlık koyu zeminde okunmuyordu. */
  title.style.cssText = 'margin: 0 0 12px 0; color: var(--ink-1, #f5f5f8); font-size: 16px;';
  modal.appendChild(title);

  const desc = document.createElement('p');
  desc.style.cssText = 'margin: 0 0 16px 0; color: var(--ink-2, #bebcc4); line-height: 1.5; font-size: 14px; white-space: pre-wrap;';
  desc.textContent = (sunum && sunum.mesaj) || _t('onay.arac-calistirmak-istiyor', { arac: toolName });
  modal.appendChild(desc);

  const argsLabel = document.createElement('p');
  argsLabel.style.cssText = 'margin: 0 0 8px 0; color: var(--ink-2, #bebcc4); font-size: 12px;';
  argsLabel.textContent = (sunum && sunum.etiket)
    || _t(sunum ? 'onay.gorev-dagilimi' : 'onay.parametreler');
  modal.appendChild(argsLabel);

  const argsBox = document.createElement('pre');
  argsBox.style.cssText = `margin: 0 0 16px 0; padding: 8px; background: var(--yuzey-1, #141319); border-radius: 4px; font-size: 12px; color: var(--ink-1, #f5f5f8); overflow-x: auto; max-height: 120px; overflow-y: auto; white-space: pre-wrap; font-family: ${(sunum && Array.isArray(sunum.satirlar)) ? 'inherit' : 'var(--font-mono, monospace)'};`;
  argsBox.textContent = (sunum && Array.isArray(sunum.satirlar))
    ? sunum.satirlar.map(s => '• ' + s).join('\n')
    : JSON.stringify(args, null, 2);
  modal.appendChild(argsBox);

  const countdownEl = document.createElement('p');
  countdownEl.style.cssText = 'margin: 0 0 16px 0; color: var(--ink-3, #98979f); font-size: 12px;';
  modal.appendChild(countdownEl);

  const btnContainer = document.createElement('div');
  btnContainer.style.cssText = 'display: flex; flex-wrap: wrap; gap: 12px; justify-content: flex-end;';

  const approveBtn = document.createElement('button');
  approveBtn.textContent = _t('onay.onayla');
  /* Geri alınamaz iş (`sunum.yikici`, ör. takvimden silme) → onay düğmesi kırmızı. */
  approveBtn.style.cssText = (sunum && sunum.yikici)
    ? `min-height: var(--hedef, 44px); padding: 8px 20px; background: var(--kirmizi-yuzey, #a51f1e); color: var(--kirmizi-ustu, #fff); border: none; border-radius: 4px; cursor: pointer; font-weight: 600; font-size: 13px; font-family: inherit;`
    : `min-height: var(--hedef, 44px); padding: 8px 20px; background: var(--mor-yuzey, #643fab); color: #fff; border: none; border-radius: 4px; cursor: pointer; font-weight: 600; font-size: 13px; font-family: inherit;`;

  const denyBtn = document.createElement('button');
  denyBtn.textContent = _t('onay.reddet');
  denyBtn.style.cssText = `min-height: var(--hedef, 44px); padding: 8px 20px; background: transparent; color: var(--ink-1, #f5f5f8); border: 1px solid var(--kenar-guclu, #605e6a); border-radius: 4px; cursor: pointer; font-weight: 600; font-size: 13px; font-family: inherit;`;

  btnContainer.appendChild(approveBtn);
  btnContainer.appendChild(denyBtn);
  modal.appendChild(btnContainer);
  overlay.appendChild(modal);
  document.body.appendChild(overlay);

  let resolved = false;

  async function _resolve(approved) {
    if (resolved) return;
    resolved = true;
    overlay.remove();
    try {
      const resp = await authFetch(`${BASE_URL}/api/tool-approval`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ approval_id: approvalId, approved }),
      });
      if (!resp.ok) { console.error('Onay POST başarısız:', resp.status); }
    } catch (e) {
      console.error('Onay POST hatası:', e);
    }
  }

  approveBtn.onclick = () => _resolve(true);
  denyBtn.onclick = () => _resolve(false);

  let remaining = timeoutSecs;
  const _tick = () => {
    countdownEl.textContent = _t('onay.sure', { sn: remaining });
    remaining--;
    if (remaining < 0) {
      if (!resolved) _resolve(false);
    } else {
      setTimeout(_tick, 1000);
    }
  };
  _tick();
}

function connect() {
  socket = new WebSocket(_wsUrl('/ws/realtime'));
  socket.onopen = () => {
    console.log('Connected');
    _wsRetryDelay = 2000;
    updateState('idle');
    _setWsPill(true);
    _anahtarYokla();
  };
  socket.onclose = (ev) => {
    _setWsPill(false);
    if (ev.code === 4003) { console.warn('WS: Origin not allowed, not retrying.'); return; }
    _scheduleReconnect();
  };
  socket.onerror = (err) => { console.error('WS Error:', err); };
  socket.onmessage = (e) => {
    const d = JSON.parse(e.data);
    // AJAN sekmesi: ekip olaylarını sekmeye de ilet — tek kaynak bu WS.
    // Aşağıdaki sohbet şeridi aynı olayları ayrıca çizmeye devam eder.
    if (d && typeof d.type === 'string' && (d.type.indexOf('companion_') === 0 || d.type === 'team_start' || d.type === 'team_end')) {
      try { document.dispatchEvent(new CustomEvent('yuki:ekip', { detail: d })); } catch (_) {}
    }
    // Atölye: görev kaydı her yazımda `gorev` olayı yollar → şerit + araştırma sahnesi dinler.
    if (d && d.type === 'gorev') {
      try { window.dispatchEvent(new CustomEvent('yuki:gorev', { detail: d })); } catch (_) {}
    }
    // SOHBET sahnesinin duygu etiketi — modes/sohbet-sahne.js OPSİYONEL:
    // dosya yüklenmezse sohbet eskisi gibi çalışır. Tek giriş noktası burası,
    // aşağıdaki dallar mevcut işlerini aynen sürdürür.
    if (window.SohbetSahne) {
      try {
        if (d.type === 'state') window.SohbetSahne.durum(d.to);
        else if (d.type === 'emotion') window.SohbetSahne.duygu(d.emotion, d);
        else if (d.type === 'behavior') window.SohbetSahne.davranis(d.action);
      } catch (err) { console.warn('[sahne] duygu kancası:', err); }
    }
    if (d.type === 'state') updateState(d.to);
    // `_applyLangUI` YETMEZ (2026-09-18, FAZ 2): o yalnız çizer, YukiDil'in
    // aktif dilini güncellemez. Sesli komutla dil değişince ekran doğru görünür
    // ama bir sonraki toggle ESKİ dilden devam ederdi. `sunucudan()` durumu da
    // günceller ve sunucuya geri yazmaz (döngü kırma).
    // 2026-10-04 (iki eksen): olay `{language, arayuz}` taşır; arayüz yalnız
    // `arayuz`'dan değişir — "Japoncaya geç" ekranı Japonca'ya/İngilizce'ye atmaz.
    else if (d.type === 'language_changed') {
      if (window.YukiDil) window.YukiDil.sunucudan(d);
      else _applyLangUI();
    }
    else if (d.type === 'behavior') {
      if (_FAL_ACTIONS.has(d.action)) playFalAnimation(d.action);
      else playBehaviorVideo(d.action);
    }
    else if (d.type === 'emotion' && yukiRive) yukiRive.setEmotion(d.emotion);
    //  · C4: aşağıdaki üçü Yuki'nin BAŞLATTIĞI ekran eylemleri. Sessizce
    // düşerlerse kullanıcı "dedim, yapmadı" görür ve sebebini hiçbir yerde bulamaz.
    else if (d.type === 'switch_tab' && d.tab && typeof window.switchTab === 'function') {
      try { window.switchTab(d.tab); }
      catch (e) {
        console.error('[yuki] switch_tab başarısız:', e);
        showToast(_t('ws.sekme-acilamadi'), 'hata');
      }
    }
    // Galeri — Yuki `show_media` ile bir dosyayı gösteriyor (backend services/tools/galeri.py).
    else if (d.type === 'galeri_ac' && d.id) {
      var galeriTamam = false;
      try { galeriTamam = typeof window.galeriAc === 'function' && window.galeriAc(d.id) === true; }
      catch (e) { console.error('[yuki] galeri_ac başarısız:', e); }
      if (!galeriTamam) showToast(_t('ws.sekme-acilamadi'), 'hata');
    }
    // Harita köprüsü — komutu uygula ve CEVAP VER (cevapsız kalırsa backend
    // "harita cevap vermedi" der; sessizce yutmak "yaptım" yalanına yol açardı).
    else if (d.type === 'harita_komut' && d.istek_id && window.YukiHarita) {
      window.YukiHarita.komutIsle(d, (m) => socket.send(JSON.stringify(m)));
    }
    else if (d.type === 'switch_character' && d.character && typeof window.setCharacter === 'function') {
      try { window.setCharacter(d.character, { fromWs: true }); }
      catch (e) {
        console.error('[yuki] switch_character başarısız:', e);
        // Kritik: karakter arka planda DEĞİŞMİŞ olabilir, ekranda değişmemiştir.
        showToast(_t('ws.karakter-degistirilemedi'), 'hata');
      }
    }
    else if (d.type === 'skill_event' && d.payload) {
      try { window.SkillCard && window.SkillCard.show(d.payload); }
      catch (e) {
        console.error('[yuki] skill_event kartı açılamadı:', e);
        showToast(_t('ws.beceri-karti-gosterilemedi'), 'uyari');
      }
    }
    // Faz 22 — Companion meclisi: hangi uzman çalışıyor (chip'li şerit)
    else if (d.type === 'companion_active') {
      if (!document.getElementById('cmp-style')) {
        const s = document.createElement('style'); s.id = 'cmp-style';
        s.textContent = '@keyframes cmpspin{to{transform:rotate(360deg)}}';
        document.head.appendChild(s);
      }
      const msgs = document.getElementById('messages');
      let strip = document.getElementById('companion-strip');
      if (!strip) {
        strip = document.createElement('div'); strip.id = 'companion-strip';
        strip.style.cssText = 'display:flex;flex-wrap:wrap;gap:6px;margin:4px 0 4px 25px;animation:msgIn .3s ease-out;';
        msgs.appendChild(strip);
      }
      let chip = strip.querySelector('[data-persona="' + d.persona + '"]');
      if (!chip) {
        chip = document.createElement('div'); chip.dataset.persona = d.persona;
        chip.style.cssText = 'display:flex;align-items:center;gap:6px;font-size:11px;padding:3px 9px;border-radius:11px;max-width:340px;background:rgba(240,180,41,.10);border:1px solid rgba(240,180,41,.30);color:var(--gold,#f0b429);';
        const spin = document.createElement('span'); spin.className = 'cmp-spin'; spin.textContent = '⟳';
        spin.style.cssText = 'display:inline-block;animation:cmpspin 1s linear infinite;';
        const nm = document.createElement('b'); nm.className = 'cmp-name';
        const st = document.createElement('span'); st.className = 'cmp-sub';
        st.style.cssText = 'opacity:.75;overflow:hidden;text-overflow:ellipsis;white-space:nowrap;';
        chip.append(spin, nm, st); strip.appendChild(chip);
      }
      chip.dataset.state = 'active';
      chip.querySelector('.cmp-name').textContent = d.label || d.persona;   // textContent: XSS yok
      chip.querySelector('.cmp-sub').textContent = d.subtask || '';
      const sp = chip.querySelector('.cmp-spin'); sp.textContent = '⟳'; sp.style.animation = 'cmpspin 1s linear infinite';
      msgs.scrollTop = msgs.scrollHeight;
    }
    else if (d.type === 'companion_done') {
      const chip = document.querySelector('#companion-strip [data-persona="' + d.persona + '"]');
      if (chip) {
        chip.dataset.state = 'done'; chip.style.opacity = '.6';
        const sp = chip.querySelector('.cmp-spin');
        // Durum işareti dürüst olsun: kota/zaman aşımı "tamamlandı" değildir.
        const im = { kota: '⏳', timeout: '⌛', hata: '⚠' }[d.durum] || '✓';
        if (sp) { sp.style.animation = 'none'; sp.textContent = im; }
      }
    }
    // FAZ 3.3 — "kim ne dedi". Sentez tek bir Yuki cevabı üretir; kullanıcı
    // uzmanların HAM çıktısını göremezse "ekip" hissi oluşmaz ve özellik
    // satılamaz — müşteri yalnız "biraz daha yavaş cevap" görür.
    else if (d.type === 'companion_result') {
      const chip = document.querySelector('#companion-strip [data-persona="' + d.persona + '"]');
      if (chip) {
        chip.style.cursor = 'pointer';
        chip.title = _t('ekip.ayrinti-ac-kapat');
        let det = chip._detay;
        if (!det) {
          det = document.createElement('div');
          det.style.cssText = 'display:none;flex-basis:100%;margin:2px 0 6px 0;padding:8px 10px;' +
            'border-radius:8px;font-size:11.5px;line-height:1.55;white-space:pre-wrap;' +
            'background:rgba(255,255,255,.04);border:1px solid rgba(240,180,41,.18);' +
            'max-height:260px;overflow:auto;';
          chip.parentElement.appendChild(det);
          chip._detay = det;
          chip.addEventListener('click', () => {
            det.style.display = det.style.display === 'none' ? 'block' : 'none';
            const msgs = document.getElementById('messages');
            if (msgs) msgs.scrollTop = msgs.scrollHeight;
          });
        }
        // textContent: uzman çıktısı MODEL ürünüdür, HTML olarak yorumlanmaz.
        det.textContent = (d.label || d.persona) + ' — ' + (d.subtask || '') + '\n\n' + (d.result || '');
      }
    }
    else if (d.type === 'text') {
      if (!currentStreamingBubble) {
        currentStreamingBubble = addMessage('yuki', '');
        currentStreamingBubble.parentElement.parentElement.style.display = 'none';
        collectedText = '';
      }
      collectedText += d.chunk;

      const clean = collectedText
        .replace(/[\[\(](?:EMOTION|BEHAVIOR):\s*\{[^}]*\}\s*[\]\)]/g, '')
        .replace(/[\[\(](?:EMOTION|BEHAVIOR):.*/g, '')
        .replace(/\n?"(wave|nod|idle|thinking|happy|sad|angry|surprised|shy|tired|neutral)"\s*$/gi, '')
        .trimEnd();

      if (clean) {
        currentStreamingBubble.innerHTML = '';
        _renderMarkdown(currentStreamingBubble, clean);
        currentStreamingBubble.parentElement.parentElement.style.display = 'flex';
      }
      document.getElementById('messages').scrollTop = document.getElementById('messages').scrollHeight;
    }
    else if (d.type === 'image_msg') {
      const container = document.getElementById('messages');
      const row = document.createElement('div');
      row.className = 'msg-row yuki';
      const img = document.createElement('img');
      img.src = `data:${d.mime || 'image/jpeg'};base64,${d.data}`;
      img.style.cssText = 'max-width:100%;max-height:400px;border-radius:12px;box-shadow:0 4px 20px rgba(0,0,0,0.4);cursor:pointer;';
      img.onclick = () => openLightbox(img.src, 'screenshot.jpg');
      row.appendChild(img);
      container.appendChild(row);
      container.scrollTop = container.scrollHeight;
    }
    // 🔴 2026-09-27: Yuki'nin kendiliğinden söyledikleri (alarm · sabah özeti · rutin) HİÇ
    // karşılanmıyordu — yalnız ardından gelen `audio` çalıyordu. Hoparlör kapalıysa ya da TTS
    // zaman aşımına düşerse alarm ekranda hiçbir iz bırakmıyordu. BİLDİRİM odası da
    // `yuki:proaktif` olayıyla günlüğünü tazeler.
    else if (d.type === 'proactive_message') {
      if (d.text) addMessage('yuki', d.text);
      if (d.text && window.toast) window.toast(String(d.text).slice(0, 120));
      try { window.dispatchEvent(new CustomEvent('yuki:proaktif', { detail: d })); } catch (_) {}
    }
    else if (d.type === 'audio') { if (isPlayingAudio) audioQueue.push(d.data); else playVoice(d.data); }
    else if (d.type === 'done') {
      const statusEl = document.getElementById('status-info');
      const toolWasUsed = !!statusEl;
      if (currentStreamingBubble && !currentStreamingBubble.textContent.trim()) {
        currentStreamingBubble.textContent = _t('sohbet.tamam');
        currentStreamingBubble.parentElement.parentElement.style.display = 'flex';
      } else if (currentStreamingBubble && collectedText.trim()) {
        // Streaming bitti — HEMEN ÖNCE behavior tag'lerini GameMode'a gönder (FINAL/tam-mesaj)
        if (window.GameMode && window.GameMode.handleBehaviorTag) {
          try { window.GameMode.handleBehaviorTag(collectedText); } catch (_) {}
        }
        // textContent'i markdown'a dönüştür
        const clean = collectedText
          .replace(/[\[\(](?:EMOTION|BEHAVIOR):\s*\{[^}]*\}\s*[\]\)]/g, '')
          .replace(/[\[\(](?:EMOTION|BEHAVIOR):.*/g, '')
          .replace(/\n?"(wave|nod|idle|thinking|happy|sad|angry|surprised|shy|tired|neutral)"\s*$/gi, '')
          .trimEnd();
        if (clean) _renderMarkdown(currentStreamingBubble, clean);
        // Zaman damgası ekle (wrap'ın içindeyse zaten var, yoksa ekle)
        const wrap = currentStreamingBubble.parentElement;
        if (wrap && !wrap.querySelector('.msg-ts')) {
          const ts = document.createElement('span');
          ts.className = 'msg-ts';
          ts.textContent = _fmtTime();
          wrap.appendChild(ts);
        }
      } else if (!currentStreamingBubble && toolWasUsed) {
        addMessage('yuki', _t('sohbet.tamam'));
      }
      // Faz 21 — Karakter XP (mesaj tamamlandı)
      if (window.evolAddXP) {
        var _ck = (window.getCharacter ? window.getCharacter() : null) || localStorage.getItem('yukiCharacter_v1') || 'yuki';
        window.evolAddXP(_ck, 15);
      }
      currentStreamingBubble = null;
      statusEl?.remove();
      document.getElementById('companion-strip')?.remove();  // Faz 22 — meclis şeridini temizle
      // (HARİTA'nın YUKI KANALI'na cevap yansıtması 2026-10-04'te kalktı — kanal da
      //  kalktı; cevap yalnız SOHBET'te. Kişisel 09-28 kararı: kontrolleri örtüyordu.)
    }
    else if (d.type === 'tool_approval') {
      // Aynı onay iki kez gelirse ikinci kutu açılmaz (backend'de çift yayın vardı).
      window._acikOnaylar = window._acikOnaylar || new Set();
      if (!window._acikOnaylar.has(d.approval_id)) {
        window._acikOnaylar.add(d.approval_id);
        setTimeout(() => window._acikOnaylar.delete(d.approval_id), ((d.timeout || 30) + 5) * 1000);
        _showToolApprovalModal(d.approval_id, d.tool, d.args, d.timeout, d.sunum);
      }
    }
    else if (d.type === 'voice_hint') {
      // 🔴 2026-08-01: ses gönderilip hiçbir şey olmaması ("konuşma algılanmıyor")
      // teşhis edilemiyordu — backend üç noktada sessizce vazgeçiyordu. Artık sebebi
      // söylüyor; teşhis verisi varsa konsola da bas ki kullanıcı paylaşabilsin.
      addMessage('yuki', d.text || _t('ses.islenemedi'));
      if (d.diagnostics) console.warn('[ses-teşhis]', JSON.stringify(d.diagnostics));
    }
    else if (d.type === 'transcription') {
      _transcriptionText = d.text;
      _transcriptionPending = true;
      // Input kutusuna yaz — kullanıcı düzenleyebilir
      const inp = document.getElementById('msg-input');
      inp.value = d.text;
      inp.style.height = 'auto';
      inp.style.height = Math.min(inp.scrollHeight, 120) + 'px';
      inp.focus();
      inp.select();
      // B6 — otomatik onay backend penceresiyle (1.5s) hizalı; DÜZENLENEN metni onurlandırır
      clearTimeout(_transcriptionTimer);
      _transcriptionTimer = setTimeout(_autoConfirmTranscription, 1300);
    }
    else if (d.type === 'state_info') {
      // Faz J: ambient öneri → turuncu banner
      if (d.ambient) {
        showAmbientBanner(d.text);
      } else {
        let statusEl = document.getElementById('status-info');
        if (!statusEl) {
          statusEl = document.createElement('div');
          statusEl.id = 'status-info';
          statusEl.style = 'font-size: 11px; color: var(--muted); margin-left: 25px; font-style: italic; animation: msgIn 0.3s ease-out;';
          document.getElementById('messages').appendChild(statusEl);
        }
        statusEl.textContent = d.text;
        document.getElementById('messages').scrollTop = document.getElementById('messages').scrollHeight;
      }
    }
    // Faz I: göz takibi → Rive input veya CSS parallax (smooth)
    else if (d.type === 'live2d' && d.params) {
      const gx = d.params.ParamEyeBallX;
      const gy = d.params.ParamEyeBallY;
      if (gx !== undefined && gy !== undefined) {
        if (yukiRive) {
          yukiRive.setEyeOffset(gx, gy);
        } else {
          const m = parseInt(getComputedStyle(document.documentElement).getPropertyValue('--eye-multiplier')) || 8;
          const v = document.getElementById('yuki-video');
          if (v) v.style.transform = `translate(${gx * m}px, ${gy * m}px)`;
        }
        const ei = document.getElementById('eye-indicator');
        if (ei && ei.style.opacity !== '1') ei.style.opacity = '1';
      }
    }
  };
}

// Faz J: Ambient öneri banner'ı (C2 refactor)
function showAmbientBanner(text) {
  let banner = document.getElementById('ambient-banner');
  if (banner) banner.remove();

  banner = document.createElement('div');
  banner.id = 'ambient-banner';
  banner.className = 'ambient-banner';

  const suggestion = text.replace('[Ambient] ', '');
  banner.dataset.suggestion = suggestion;

  banner.innerHTML = `<span class="ambient-icon">⚡</span>`
    + `<span class="ambient-text">${_t('amb.oneri-oneki')}</span>`
    + `<button class="ambient-close" title="${_t('amb.kapat')}">×</button>`;
  banner.querySelector('.ambient-text').appendChild(document.createTextNode(suggestion));

  banner.querySelector('.ambient-text').onclick = () => {
    document.getElementById('msg-input').value = suggestion;
    banner.remove();
  };
  banner.querySelector('.ambient-close').onclick = (e) => {
    e.stopPropagation();
    banner.remove();
  };

  document.body.appendChild(banner);
  clearTimeout(banner._timer);
  banner._timer = setTimeout(() => banner.remove(), 10000);
}

// B6 — ses transkripti otomatik onayı: kullanıcının DÜZENLEDİĞİ metni kullanır ve
// backend'e confirm gönderir (düzenleme penceresiyle hizalı). Çift/yanlış mesaj önlenir.
function _autoConfirmTranscription() {
  if (!_transcriptionPending) return;
  const inp = document.getElementById('msg-input');
  const finalText = (inp.value.trim() || _transcriptionText);
  _transcriptionPending = false;
  //  · C4: gönderilemezse mesaj aşağıda EKRANA yazılır ama Yuki'ye hiç
  // ulaşmaz. Sessiz kalırsa kullanıcı "gönderdim" sanıp cevap bekler.
  let _gonderildi = false;
  try {
    if (socket && socket.readyState === WebSocket.OPEN) {
      socket.send(JSON.stringify({ type: 'confirm_transcription', text: finalText }));
      _gonderildi = true;
    }
  } catch (e) {
    console.error('[yuki] transkripsiyon onayı gönderilemedi:', e);
  }
  if (!_gonderildi) {
    showToast(_t('ses.gonderilemedi-baglanti'), 'hata');
  }
  addMessage('user', finalText);
  if (inp.value.trim() === finalText) { inp.value = ''; inp.style.height = 'auto'; }
}

async function sendMessage() {
  const i = document.getElementById('msg-input');
  const t = i.value.trim();
  if (!t) return;
  if (isRecording) { try { stopRecording(); } catch (_) {} }  // B6 — yazı gönderilince kaydı temiz kapat
  if (!socket || socket.readyState !== WebSocket.OPEN) {
    addMessage('yuki', _t('sohbet.baglanti-bekleniyor'));
    return;
  }
  // Kullanıcı hareketi sırasında AudioContext'i unlock et (mobil autoplay için)
  try { const _ac = _getMainAudioCtx(); if (_ac.state === 'suspended') await _ac.resume(); } catch (_) {}
  if (_transcriptionPending) {
    // Transkripsiyon düzenleme modunda — backend'e düzenlenmiş metni gönder
    clearTimeout(_transcriptionTimer);
    _transcriptionPending = false;
    socket.send(JSON.stringify({ type: 'confirm_transcription', text: t }));
    addMessage('user', t);
    i.value = ''; i.style.height = 'auto';
    return;
  }
  addMessage('user', t);
  const _ctx = window.YukiState ? window.YukiState.buildContext() : '';
  updateState('thinking');
  socket.send(JSON.stringify({ type: 'text', message: t + _ctx }));
  i.value = ''; i.style.height = 'auto';
}

// UI-F001 (H9, 2026-10-09): eskiden onaysız ve kalıcı siliyordu (çöp kutusu ·
// palet 'temizle' · Ctrl+L). Onay + 5 sn geri al → js/gecmis-temizle.js.
function clearHistory() {
  if (!window.gecmisTemizle) {   // modül yüklenmediyse SİLME — sessizce de geçme
    showToast(_t('sohbet.temizlenemedi'), 'hata');
    return;
  }
  window.gecmisTemizle.iste((keepalive) =>
    authFetch(`${BASE_URL}/api/chat/clear-messages`, { method: 'POST', keepalive }));
}

/* ── B7 "Ne lazım?" karşılama ekranı KALDIRILDI (geliştirici kararı, 2026-09-06) ──
   Açılışta gelen tam ekran perde ("Merhaba, ben Yuki 🌸") sohbet arayüzünün
   önüne bir adım daha koyuyordu; kullanıcı zaten yazmak için gelmiş oluyor.
   HTML'i (`#onboard-overlay`) ve `localStorage` göç kaydı da kaldırıldı —
   çağrıyı kesip markup'ı bırakmak ölü kod olurdu. */

// ── B8 — Hafıza paneli: gör / sil (unut) / dışa aktar ──
// Alt+H artık kendi overlay'ini açmıyor: HQ > Hafıza Yöneticisi'ne götürüyor.
// Eski overlay memmgr'ın filtresiz/aramasız kopyasıydı, ikisi aynı veriyi iki
// ayrı ekranda gösteriyordu (FAZ 4, 2026-08-23).
function openMemoryPanel() {
  /* Hedefi geçişten ÖNCE bildir. Sekme geçişi View Transition'ın callback'inde,
     yani bir sonraki frame'de koşuyor; oraya "hangi panel" bilgisini taşımanın
     tek güvenilir yolu bu bayrak (tab-nav.js § tab === 'hq'). Beklemeye ya da
     zamanlayıcıya dayanan her çözüm yarışı gizler, çözmez. */
  window._hqHedefPanel = 'memmgr';
  if (typeof window.switchTab === 'function') window.switchTab('hq');
  // HQ zaten açıkken sekme geçişi tetiklenmeyebilir → paneli doğrudan da uygula.
  // Çifte çağrı zararsız: ikisi de aynı paneli seçiyor.
  if (typeof window.hqGoto === 'function') {
    window.hqGoto('panel', 'memmgr');       // menüyü de işaretler
  } else if (typeof window.switchHqTab === 'function') {
    window.switchHqTab('memmgr');
  }
}
// Kapatma artık HQ sekmesinden çıkmakla olur; ayrı bir kapat düğmesi yok.
// Fonksiyon adı dışarıdan çağrılıyor olabilir diye zararsız bir kabuk olarak duruyor.
function closeMemoryPanel() {}
// _renderMemoryList KALDIRILDI (FAZ 4): #memory-panel-list / #memory-panel-count
// kancaları artık DOM'da yok. Listeyi memmgrLoadList() çiziyor (intro-sequences.js),
// o sürüm arama + kategori filtresi + sayfalama da yapıyor.

async function _exportMemory() {
  try {
    const r = await authFetch(`${BASE_URL}/api/memory/export`);
    const blob = await r.blob();
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url; a.download = 'yuki-hafiza.json';
    document.body.appendChild(a); a.click(); a.remove();
    URL.revokeObjectURL(url);
  } catch (e) { console.warn('Hafıza dışa aktarma başarısız:', e); }
}
window.openMemoryPanel = openMemoryPanel;

let isRecording = false;
let mediaRecorder = null;
let audioCtx = null;
let analyser = null;
let vadInterval = null;
let silenceStart = 0;
let micTimerInterval = null;
let micStartTime = 0;
const SILENCE_THRESHOLD = 0.015;   // RMS enerji eşiği (0-1) — artık yalnız ALT SINIR
const SILENCE_DURATION = 1500;     // 1.5s sessizlik → otomatik dur

// ── 🎤 Mikrofon teşhisi (2026-08-02, kişisel Alice ölçümlerinden aktarıldı) ──
// 🔑 Ana ders: SES GÜCÜ (RMS) MİKROFONUN İYİ OLDUĞUNU GÖSTERMEZ.
//    Doğru ölçüt konuşma bandı payı (300–3400 Hz).
//
// 1) Sabit eşik sorunu: gürültü tabanı 0.015'ten yüksek olan bir mikrofonda VAD
//    sessizliği HİÇ göremez → kayıt kendi kendine durmaz → düğme kırmızı kalır →
//    kullanıcı "mikrofonu algılamıyor" der. Ölçülen boşta RMS değerleri:
//      Brio 100 @%100 → 0.0059 (temiz) · @%130 → 0.0124 (sınırda) · analog giriş → 0.020+ (ölü)
//    Çözüm: kaydın ilk 1 sn'sinde GERÇEK tabanı ölç, eşiği ondan türet.
const NOISE_FLOOR_YUZDELIK = 0.20;   // en sessiz %20'lik dilim
const NOISE_FLOOR_CARPANI  = 2.5;
const VAD_ESIK_TAVANI      = 0.05;
// ⚠️ MEDYAN KULLANMA. Kullanıcı düğmeye basar basmaz konuşursa medyan KONUŞMAYI
//    taban sanar, eşik tavana fırlar ve hiçbir ses geçemez. Hecelerin arasındaki
//    boşlukları yakalamak için ALT YÜZDELİK şart. (Bu regresyon kişiselde ölçümle
//    yakalandı — kod okuyarak görünmüyordu.)
//
// 2) "Cihaz ölü mü" ≠ "biri konuşuyor mu" → AYRI eşik.
// ⚠️ SILENCE_THRESHOLD'u ölü-cihaz testi olarak KULLANMA: çalışan mikrofonlar sessiz
//    odada bile taban gürültüsü verir (Brio 0.00595) → 0.015 çalışan mikrofona "ölü" der.
const DEAD_MIC_RMS = 0.0005;
// 3) Uğultu körlüğü: uğultu da enerjidir, RMS ikisini ayırt edemez. Ölçüm (aynı
//    kişi, aynı oda, iki mikrofon): Brio %55,5 → Whisper anlamlı · analog giriş
//    %3,6 → Whisper uyduruyor ('6 teremesez'). İkisi de RMS olarak "ses var"dı.
const KONUSMA_BANDI_ESIGI = 0.18;

let _vadEsigi = SILENCE_THRESHOLD;   // ölçümle güncellenir
let _gurultuOrnekleri = null;        // grace period örnekleri (hesaplanınca null)
let _tepeRms = 0;                    // ölü cihaz testi
let _bandOranlari = [];              // konuşma bandı payı örnekleri
let _ugultuUyarisiVerildi = false;   // oturumda bir kez uyar, her kayıtta değil
const $micBtn = document.getElementById('mic-btn');
const $micContainer = document.getElementById('mic-container');
let alwaysOnMode = false;
let _wakeLock = null;
const $micRingLevel = document.querySelector('#mic-level-ring .ring-level');
const $micTimer = document.getElementById('mic-timer');
const MIC_RING_CIRCUMFERENCE = 2 * Math.PI * 23; // ~144.51

function getRMS(analyserNode) {
  const data = new Float32Array(analyserNode.fftSize);
  analyserNode.getFloatTimeDomainData(data);
  let sum = 0;
  for (let i = 0; i < data.length; i++) sum += data[i] * data[i];
  return Math.sqrt(sum / data.length);
}

/** Sinyalin ne kadarı insan konuşma bandında (300–3400 Hz)? 0-1 arası oran.
 *  Uğultulu bir mikrofon yüksek RMS verir ama bu oran çok düşük kalır. */
function getKonusmaBandiOrani(analyserNode, ctx) {
  const n = analyserNode.frequencyBinCount;
  const dbf = new Float32Array(n);
  analyserNode.getFloatFrequencyData(dbf);
  const binHz = ctx.sampleRate / analyserNode.fftSize;
  let konusma = 0, toplam = 0;
  for (let i = 1; i < n; i++) {
    if (dbf[i] === -Infinity) continue;      // sessiz bin — dB ölçeğinde -sonsuz
    const g = Math.pow(10, dbf[i] / 10);     // dB → doğrusal güç
    toplam += g;
    const hz = i * binHz;
    if (hz >= 300 && hz < 3400) konusma += g;
  }
  return toplam > 0 ? konusma / toplam : 0;
}

function _medyan(a) {
  if (!a || !a.length) return 0;
  const s = [...a].sort((x, y) => x - y);
  const m = Math.floor(s.length / 2);
  return s.length % 2 ? s[m] : (s[m - 1] + s[m]) / 2;
}

function stopRecording() {
  if (vadInterval) { clearInterval(vadInterval); vadInterval = null; }
  if (micTimerInterval) { clearInterval(micTimerInterval); micTimerInterval = null; }
  if (mediaRecorder && mediaRecorder.state === 'recording') mediaRecorder.stop();
  isRecording = false;
  $micBtn.classList.remove('recording');
  $micBtn.classList.remove('vad-silence');
  $micContainer.classList.remove('active');
  $micRingLevel.setAttribute('stroke-dasharray', '0 ' + MIC_RING_CIRCUMFERENCE);
  $micTimer.textContent = '00:00';
  _updateWakeWordDurum(null);
}

/**
 * Wake-word banner'a durum class'ları ekle/kaldır.
 * @param {string|null} durum - "dinliyor" | "duyuldu" | null (kapat)
 */
function _updateWakeWordDurum(durum) {
  const banner = document.getElementById('wake-word-banner');
  if (!banner) return;

  // Mevcut durum class'larını temizle
  banner.classList.remove('dinliyor', 'duyuldu');

  if (durum) {
    banner.classList.add(durum);
  }
}

function updateMicTimer() {
  const elapsed = Math.floor((Date.now() - micStartTime) / 1000);
  const m = String(Math.floor(elapsed / 60)).padStart(2, '0');
  const s = String(elapsed % 60).padStart(2, '0');
  $micTimer.textContent = m + ':' + s;
}

$micBtn.onclick = async () => {
  if (!isRecording) {
    // İndir-gerektiğinde: STT modeli yoksa indirme akışını başlat (masaüstü) / bilgi ver (web).
    // ensureSTT false dönerse (iptal / model yok / web modu) kayıt başlatma.
    if (window.ModelDownloader && !(await window.ModelDownloader.ensureSTT())) return;
    let s;
    const _izinMesaji = ' ' + _t('mik.izin-nasil-verilir');
    try {
      // Seçili mikrofon (js/mic-devices.js) — seçim yoksa `true` = sistem varsayılanı,
      // yani eski davranış birebir korunur.
      s = await navigator.mediaDevices.getUserMedia({
        audio: window.MicDevices ? window.MicDevices.constraints() : true,
      });
    } catch (err) {
      // Seçili cihaz çıkarılmışsa `exact` kısıtı OverconstrainedError atar —
      // kullanıcı susmuş bir mikrofonla kalmasın diye varsayılana düşülür.
      if (err && (err.name === 'OverconstrainedError' || err.name === 'NotFoundError')
          && window.MicDevices && window.MicDevices.selected()) {
        window.MicDevices.select('');
        try {
          s = await navigator.mediaDevices.getUserMedia({ audio: true });
          addMessage('yuki', _t('mik.secili-bulunamadi-varsayilana-donuldu'));
        } catch (e2) {
          addMessage('yuki', _t('mik.erisim-reddedildi', { sebep: e2.message }) + _izinMesaji);
          return;
        }
      } else {
        // ⚠️ Argümanlar TERSTİ (`addMessage(role, text)`) → mikrofon reddedildiğinde
        // hata mesajı bozuk render oluyordu. Windows'ta izin reddi tam olarak bu yolu
        // kullanır; kullanıcı "hiçbir şey olmuyor" diye görüyordu.
        addMessage('yuki', _t('mik.erisim-reddedildi', { sebep: err.message }) + _izinMesaji);
        return;
      }
    }
    // Audio analiz pipeline
    audioCtx = new (window.AudioContext || window.webkitAudioContext)();
    if (audioCtx.state === 'suspended') await audioCtx.resume();
    const source = audioCtx.createMediaStreamSource(s);
    analyser = audioCtx.createAnalyser();
    analyser.fftSize = 2048;
    source.connect(analyser);

    // Tarayıcı desteğine göre en iyi mimeType seç (iOS Safari webm desteklemez)
    const MIME_CANDIDATES = [
      'audio/webm;codecs=opus',
      'audio/webm',
      'audio/ogg;codecs=opus',
      'audio/mp4',
      '',
    ];
    const mimeType = MIME_CANDIDATES.find(m => !m || MediaRecorder.isTypeSupported(m)) || '';
    mediaRecorder = new MediaRecorder(s, mimeType ? { mimeType } : {});
    const chunks = [];
    mediaRecorder.ondataavailable = (e) => e.data.size > 0 && chunks.push(e.data);
    mediaRecorder.onstop = async () => {
      if (vadInterval) { clearInterval(vadInterval); vadInterval = null; }
      const b = new Blob(chunks, { type: mediaRecorder.mimeType || 'audio/webm' });
      try {
        // 🔴 2026-08-02: ÖLÜ CİHAZ ile "kullanıcı sessiz kaldı" ayrı şeyler.
        // Gerçek vaka: sistem varsayılanı A2DP profilindeki Bluetooth kulaklıktı,
        // tepe RMS 0.00000 (o profilde mikrofon YOK). Kullanıcı "sesimi duymuyor"
        // diyordu, hiçbir geri bildirim yoktu.
        const oluCihaz = _tepeRms < DEAD_MIC_RMS;
        if (oluCihaz) {
          addMessage('yuki', _t('mik.olu-cihaz'));
        }
        // Sessiz audio filtresi: çok kısa kayıt gönderme
        else if (b.size <= 1000) {
          // 🔴 2026-08-01: burası sessizce düşüyordu. Mikrofon izinli görünüp sessizlik
          // ürettiğinde (Windows'ta sık) kullanıcı konuşuyor, kayıt atılıyor, ekranda
          // hiçbir şey olmuyordu. Artık sebebini söylüyor.
          addMessage('yuki', _t('mik.kayit-bos'));
        }

        // Uğultu teşhisi — ses VAR ama konuşma değil. Kayıt yine de gönderilir
        // (Whisper bir şey çıkarabilir), ama kullanıcı sebebi öğrensin.
        if (!oluCihaz && _bandOranlari.length >= 5 && !_ugultuUyarisiVerildi) {
          const oran = _medyan(_bandOranlari);
          if (oran < KONUSMA_BANDI_ESIGI) {
            _ugultuUyarisiVerildi = true;
            /* 🔴 Yüzde İŞARETİ SAYIYA ÖNDEN EKLENEMEZ: Türkçe'de "%55", İngilizce'de
               "55%". Eski kod `'%' + sayı` diye kuruyordu — çeviri bunu düzeltmez,
               SIRAYI da anahtar taşımalı (planner.html'in tarih sırası dersi). */
            addMessage('yuki', _t('mik.ugultu-uyarisi', { yuzde: Math.round(oran * 100) }));
          }
          console.log('[mikrofon] konuşma bandı payı (medyan) = %' + (oran * 100).toFixed(1) +
                      ' · tepe RMS = ' + _tepeRms.toFixed(5) + ' · VAD eşiği = ' + _vadEsigi.toFixed(5));
        }

        if (!oluCihaz && b.size > 1000) {
          // Faz α: native mod aktifse nativeWs'e gönder, yoksa normal socket
          const sentNative = window._nativeSendAudio ? await window._nativeSendAudio(b) : false;
          if (!sentNative) {
            if (socket && socket.readyState === WebSocket.OPEN) {
              socket.send(await b.arrayBuffer());
            } else {
              addMessage('yuki', _t('ses.baglanti-yok-yenile'));
            }
          }
        }
      } finally {
        s.getTracks().forEach(t => t.stop());
        if (audioCtx) { audioCtx.close(); audioCtx = null; }
      }
    };
    mediaRecorder.start(100);
    isRecording = true;
    $micBtn.classList.add('recording');
    $micContainer.classList.add('active');
    _updateWakeWordDurum('dinliyor');
    silenceStart = 0;
    // Teşhis durumunu her kayıtta sıfırla (onstop bunları okur).
    _vadEsigi = SILENCE_THRESHOLD;
    _gurultuOrnekleri = [];
    _tepeRms = 0;
    _bandOranlari = [];
    micStartTime = Date.now();
    micTimerInterval = setInterval(updateMicTimer, 1000);

    // VAD: sessizlik algılama → otomatik dur + görsel feedback
    // 1s grace period: mobil AudioContext ilk açılışta sıfır okur
    const vadGraceEnd = Date.now() + 1000;
    vadInterval = setInterval(() => {
      if (!analyser) return;
      const rms = getRMS(analyser);

      // C3: SVG ring — RMS seviyesini görselleştir
      const level = Math.min(rms / 0.1, 1); // normalize: 0.1 RMS = full
      const dashLen = level * MIC_RING_CIRCUMFERENCE;
      $micRingLevel.setAttribute('stroke-dasharray', dashLen + ' ' + (MIC_RING_CIRCUMFERENCE - dashLen));

      // Grace period artık boşa gitmiyor — gerçek gürültü tabanını ÖLÇÜYOR.
      if (Date.now() < vadGraceEnd) {
        if (_gurultuOrnekleri) _gurultuOrnekleri.push(rms);
        return;
      }
      if (_gurultuOrnekleri) {
        if (_gurultuOrnekleri.length >= 5) {
          const sirali = [..._gurultuOrnekleri].sort((a, b) => a - b);
          const taban = sirali[Math.floor(sirali.length * NOISE_FLOOR_YUZDELIK)];
          _vadEsigi = Math.min(
            Math.max(SILENCE_THRESHOLD, taban * NOISE_FLOOR_CARPANI),
            VAD_ESIK_TAVANI
          );
          console.log('[VAD] gürültü tabanı=' + taban.toFixed(5) + ' → eşik=' + _vadEsigi.toFixed(5));
        }
        _gurultuOrnekleri = null;   // bir kez hesapla
      }

      _tepeRms = Math.max(_tepeRms, rms);
      // Bant payını yalnız SİNYAL VARKEN ölç — sessizlikte oran anlamsızdır.
      if (rms >= _vadEsigi && audioCtx) {
        _bandOranlari.push(getKonusmaBandiOrani(analyser, audioCtx));
        // Ses duyuldu — banner durum class'ını güncelle
        _updateWakeWordDurum('duyuldu');
      }

      if (rms < _vadEsigi) {
        $micBtn.classList.add('vad-silence');
        if (!silenceStart) silenceStart = Date.now();
        else if (Date.now() - silenceStart > SILENCE_DURATION) {
          console.log('[VAD] Sessizlik algılandı, kayıt durduruluyor.');
          stopRecording();
        }
      } else {
        $micBtn.classList.remove('vad-silence');
        silenceStart = 0;
      }
    }, 100);
  } else {
    stopRecording();
  }
};

// ── Always-on dinleme modu ─────────────────────────── //
// 🔴 2026-08-05: burada iki AYRI şey tek düğmeye binmişti.
//   ① "Her zaman dinle"  = mikrofon döngüsü (bu dosya)
//   ② "Uyandırma kelimesi" = filtre (backend, WAKE_WORD_ENABLED, varsayılan KAPALI)
// Banner ②'yi varsayarak "Hey Yuki dinleniyor" yazıyordu; ② kapalı olduğu için
// Yuki aslında duyduğu HER cümleye yanıt veriyordu — yanındaki konuşmaya da.
// Artık banner gerçeği yazıyor ve mod ilk açıldığında seçim soruluyor.
let _wakeWordAcik = null;   // null = henüz bilinmiyor

async function _wakeWordDurum() {
  try {
    const r = await authFetch(`${BASE_URL}/api/settings/wake-word`);
    const d = await r.json();
    _wakeWordAcik = !!(d && d.enabled);
  } catch (_) {
    _wakeWordAcik = null;   // bilinmiyor → banner iddiada bulunmaz
  }
  return _wakeWordAcik;
}

function _wakeBannerYaz() {
  const t = document.getElementById('wake-word-text');
  if (!t) return;
  if (_wakeWordAcik === true)       t.textContent = _t('wake.bekleniyor');
  else if (_wakeWordAcik === false) t.textContent = _t('wake.surekli-dinleniyor');
  else                              t.textContent = _t('wake.dinleniyor');
  const dugmeler = document.querySelectorAll('#wake-word-secim [role="radio"]');
  dugmeler.forEach((dugme, i) => {
    const secili = _wakeWordAcik === (i === 1);
    dugme.setAttribute('aria-checked', secili ? 'true' : 'false');
    dugme.tabIndex = secili ? 0 : -1;
  });
}

function _wakeSecimGoster(goster) {
  const secim = document.getElementById('wake-word-secim');
  const btn = document.getElementById('always-on-btn');
  if (!secim) return;
  // `hidden=true` odağı anında <body>'ye düşürebilir; kapanmadan önce kaydet.
  const odakSecimdeydi = secim.contains(document.activeElement);
  secim.hidden = !goster;
  if (btn) btn.setAttribute('aria-expanded', goster ? 'true' : 'false');
  if (!goster) {
    if (odakSecimdeydi) {
      if (btn) btn.focus();
      // Tetik kapalı ⋯ menüsünde (0×0) → focus() sessizce boşa düşer; yazma alanına dön.
      if (document.activeElement !== btn) {
        const giris = document.getElementById('msg-input');
        if (giris) giris.focus();
      }
    }
    return;
  }
  _wakeBannerYaz();
  if (!secim.dataset.klavyeBagli) {
    secim.dataset.klavyeBagli = '1';
    secim.addEventListener('keydown', (e) => {
      const dugmeler = Array.from(secim.querySelectorAll('[role="radio"]'));
      const sira = dugmeler.indexOf(document.activeElement);
      if (!dugmeler.length) return;
      if (e.key === 'Escape') {
        e.preventDefault();
        _wakeSecimGoster(false);
        return;
      }
      let hedef = sira;
      if (e.key === 'ArrowRight' || e.key === 'ArrowDown') hedef = (sira + 1 + dugmeler.length) % dugmeler.length;
      else if (e.key === 'ArrowLeft' || e.key === 'ArrowUp') hedef = (sira - 1 + dugmeler.length) % dugmeler.length;
      else if (e.key === 'Home') hedef = 0;
      else if (e.key === 'End') hedef = dugmeler.length - 1;
      else return;
      e.preventDefault();
      /* Seçim odakla birlikte yürür (radyo grubu deseni M6): eskiden ok
         tuşu yalnız odağı taşıyordu → biri mor zeminli (uygulanan), öbürü mor
         çerçeveli (odak) iki düğme aynı anda vurgulu kalıyordu. Uygulama yine
         Enter/Space/tık ile; Esc ya da dışarı çıkış _wakeBannerYaz'la gerçeğe döner.
         Şeridin metni her an UYGULANAN durumu söylemeye devam eder. */
      dugmeler.forEach((dugme, i) => {
        dugme.tabIndex = i === hedef ? 0 : -1;
        dugme.setAttribute('aria-checked', i === hedef ? 'true' : 'false');
      });
      dugmeler[hedef].focus();
    });
    // Seçmeden gruptan çıkılırsa vurgu uygulanan duruma döner.
    secim.addEventListener('focusout', (e) => {
      if (!secim.contains(e.relatedTarget)) _wakeBannerYaz();
    });
  }
  const secili = secim.querySelector('[role="radio"][aria-checked="true"]')
              || secim.querySelector('[role="radio"]');
  if (secili) secili.focus();
}

/** Banner'daki seçim: filtreyi aç/kapat, anında uygula (restart gerekmez). */
window.wakeWordSec = async function (acik) {
  try {
    const r = await authFetch(`${BASE_URL}/api/settings/WAKE_WORD_ENABLED`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ value: !!acik }),
    });
    if (!r.ok) throw new Error('HTTP ' + r.status);
    _wakeWordAcik = !!acik;
    showToast(_t(acik ? 'wake.secim-yalniz-hey-yuki' : 'wake.secim-her-cumle'), 'success');
  } catch (e) {
    showToast(_t('wake.ayar-kaydedilemedi'), 'warn');
    await _wakeWordDurum();   // gerçeği tekrar oku, iddiayı düzelt
  }
  _wakeSecimGoster(false);
  _wakeBannerYaz();
};

/* Durum satırındaki "Hep dinle" anahtarı (11-14, kişiseldeki gibi) — asıl #always-on-btn
   araç yayında gizli kalsa da açık/kapalı buradan görünür. Durumu HER ZAMAN alwaysOnMode'dan alır. */
function _hepDinleAnahtarTazele() {
  const a = document.getElementById('hep-dinle-anahtar');
  if (!a) return;
  a.classList.toggle('acik', alwaysOnMode);
  a.setAttribute('aria-checked', alwaysOnMode ? 'true' : 'false');
  const y = document.getElementById('hep-dinle-yazi');
  if (y) y.textContent = _t(alwaysOnMode ? 'girdi.hep-dinle-acik' : 'girdi.hep-dinle-kapali');
}
document.addEventListener('DOMContentLoaded', _hepDinleAnahtarTazele);
window.addEventListener('yuki-dil-degisti', _hepDinleAnahtarTazele);

async function toggleAlwaysOn() {
  alwaysOnMode = !alwaysOnMode;
  _hepDinleAnahtarTazele();
  const btn = document.getElementById('always-on-btn');
  const banner = document.getElementById('wake-word-banner');
  if (alwaysOnMode) {
    btn.classList.add('active');
    banner.classList.add('visible');
    // Wake Lock — ekranı uyutma
    if ('wakeLock' in navigator) {
      try { _wakeLock = await navigator.wakeLock.request('screen'); } catch(_) {}
    }
    await _wakeWordDurum();
    _wakeBannerYaz();
    // Filtre kapalıysa seçim sun. Zorlamıyoruz: seçmezse banner zaten
    // "sürekli dinleniyor" diyor — kullanıcı yanlış bilgilendirilmiş olmuyor.
    _wakeSecimGoster(_wakeWordAcik === false);
    showToast(_t(_wakeWordAcik ? 'wake.acik-uyandirmali' : 'wake.acik-surekli'), 'success');
    if (!isRecording) $micBtn.click();
  } else {
    _wakeSecimGoster(false);
    btn.classList.remove('active');
    banner.classList.remove('visible');
    if (_wakeLock) { _wakeLock.release(); _wakeLock = null; }
    showToast(_t('wake.kapatildi'), '');
    if (isRecording) stopRecording();
  }
}

// Sayfa görünür olduğunda wake lock'u yenile
document.addEventListener('visibilitychange', async () => {
  if (alwaysOnMode && document.visibilityState === 'visible' && 'wakeLock' in navigator) {
    try { _wakeLock = await navigator.wakeLock.request('screen'); } catch(_) {}
  }
});

// ══════════════════════════════════════════════════════
//  GEMINI NATIVE AUDIO  (Faz α)
//  /ws/native — tek API çağrısıyla STT+LLM+TTS
// ══════════════════════════════════════════════════════
(function() {
  let nativeMode = false;
  let nativeWs = null;
  let nativeCtx = null;       // AudioContext (24kHz)
  let nativeNextTime = 0;     // scheduled playback cursor
  const $btn = document.getElementById('native-audio-btn');

  // ── PCM oynatımı ──────────────────────────────────── //
  function _ensureCtx() {
    if (!nativeCtx || nativeCtx.state === 'closed') {
      nativeCtx = new (window.AudioContext || window.webkitAudioContext)({ sampleRate: 24000 });
      nativeNextTime = 0;
    }
  }

  function _playPcmChunk(base64) {
    _ensureCtx();
    const raw = atob(base64);
    const bytes = new Uint8Array(raw.length);
    for (let i = 0; i < raw.length; i++) bytes[i] = raw.charCodeAt(i);

    // PCM16 LE → Float32
    const pcm = new Int16Array(bytes.buffer);
    const f32 = new Float32Array(pcm.length);
    for (let i = 0; i < pcm.length; i++) f32[i] = pcm[i] / 32768;

    const buf = nativeCtx.createBuffer(1, f32.length, 24000);
    buf.copyToChannel(f32, 0);

    const src = nativeCtx.createBufferSource();
    src.buffer = buf;
    src.connect(nativeCtx.destination);

    // Lip-sync: gainNode'a yönlendir
    if (_lipSyncCtx && yukiRive) {
      try {
        const gain = nativeCtx.createGain();
        gain.gain.value = _audioMuted ? 0 : _audioVolume;
        src.connect(gain);
        gain.connect(nativeCtx.destination);
      } catch (_) {}
    }

    const now = nativeCtx.currentTime;
    const startAt = Math.max(nativeNextTime, now + 0.05);
    src.start(startAt);
    nativeNextTime = startAt + buf.duration;

    isPlayingAudio = true;
    _setStopBtn(true);
  }

  // ── WebSocket bağlantısı ───────────────────────────── //
  let _nativeFails = 0;   // hiç açılamadan kapanan bağlantı sayacı (sonsuz döngü freni)

  function _connect() {
    const url = _wsUrl('/ws/native');
    nativeWs = new WebSocket(url);
    $btn.classList.add('native-connecting');
    let _opened = false;

    nativeWs.onopen = () => {
      console.log('[Native] Bağlandı');
      _opened = true;
      _nativeFails = 0;
      $btn.classList.remove('native-connecting');
      $btn.classList.add('native-active');
      $btn.title = _t('native.aktif');
    };

    nativeWs.onclose = (ev) => {
      console.warn('[Native] Bağlantı kesildi:', ev.code, ev.reason);
      $btn.classList.remove('native-active', 'native-connecting');
      nativeWs = null;
      if (ev.code === 4503) {
        // Sunucu tarafında devre dışı (backend artık accept+close ile kodu iletiyor)
        addMessage('yuki', _t('native.sunucuda-kapali'));
        nativeMode = false;
        $btn.title = _t('native.baslik');
        return;
      }
      // Hiç açılamadan kapandıysa (el sıkışma reddi / sunucu kapalı → 1006):
      // sonsuza dek deneme — 2 denemede pes et ve kullanıcıya söyle.
      if (!_opened) {
        _nativeFails += 1;
        if (_nativeFails >= 2) {
          addMessage('yuki', _t('native.baglanamadi'));
          nativeMode = false;
          _nativeFails = 0;
          $btn.title = _t('native.baslik');
          return;
        }
      }
      if (nativeMode) {
        // Otomatik yeniden bağlan
        setTimeout(_connect, 3000);
      }
    };

    nativeWs.onerror = (err) => {
      console.error('[Native] WS hatası:', err);
    };

    nativeWs.onmessage = (ev) => {
      let d;
      try { d = JSON.parse(ev.data); } catch { return; }

      if (d.type === 'audio_chunk' && d.data) {
        updateState('talking');
        _playPcmChunk(d.data);
      } else if (d.type === 'text' && d.chunk) {
        // Transkript / asistan metni
        if (!currentStreamingBubble) {
          currentStreamingBubble = addMessage('yuki', '');
          currentStreamingBubble.parentElement.parentElement.style.display = 'none';
          collectedText = '';
        }
        collectedText += d.chunk;
        const clean = collectedText.replace(/[\[\(](?:EMOTION|BEHAVIOR):\s*\{[^}]*\}\s*[\]\)]/g, '').trimEnd();
        if (clean) {
          currentStreamingBubble.innerHTML = '';
          _renderMarkdown(currentStreamingBubble, clean);
          currentStreamingBubble.parentElement.parentElement.style.display = 'flex';
        }
        document.getElementById('messages').scrollTop = document.getElementById('messages').scrollHeight;
      } else if (d.type === 'done') {
        updateState('idle');
        isPlayingAudio = false;
        currentStreamingBubble = null;
        _setStopBtn(false);
      } else if (d.type === 'error') {
        addMessage('yuki', _t('native.hata', { sebep: d.message || '?' }));
        updateState('idle');
      } else if (d.type === 'ping') {
        // heartbeat — sessizce geç
      }
    };
  }

  function _disconnect() {
    if (nativeWs) {
      nativeWs.onclose = null;  // otomatik yeniden bağlanmayı engelle
      nativeWs.close();
      nativeWs = null;
    }
    $btn.classList.remove('native-active', 'native-connecting');
    $btn.title = _t('native.baslik');
    if (nativeCtx) { nativeCtx.close().catch(() => {}); nativeCtx = null; }
  }

  // ── Toggle ────────────────────────────────────────── //
  window.toggleNativeMode = function() {
    nativeMode = !nativeMode;
    if (nativeMode) {
      _connect();
    } else {
      _disconnect();
    }
  };

  // ── Mic entegrasyonu: native modda nativeWs'e gönder ─ //
  // MediaRecorder.onstop'u monkey-patch yerine event-tabanlı hook:
  // Orijinal $micBtn.onclick'in onstop callback'ini genişletiyoruz.
  const _origOnstop = Object.getOwnPropertyDescriptor(HTMLMediaElement.prototype, 'onstop');
  // Basit yaklaşım: window.nativeAudioSend açık API olarak export et
  window._nativeSendAudio = async function(blob) {
    if (!nativeWs || nativeWs.readyState !== WebSocket.OPEN) return false;
    const buf = await blob.arrayBuffer();
    nativeWs.send(buf);
    updateState('thinking');
    return true;
  };
})();

// ══════════════════════════════════════════════════════
//  GESTURE CONTROL  (Faz β)
//  MediaPipe Hands — CDN, lazy-load, sıfır npm
//  pinch=gönder · wave=durdur · palm(1.5s)=sessiz
// ══════════════════════════════════════════════════════
(function() {
  let gestureEnabled = false;
  let _hands = null;
  let _camera = null;
  let _vid = null;
  const $btn = document.getElementById('gesture-btn');

  // ── Geometri yardımcıları ──────────────────────────── //
  function _dist2d(a, b) {
    return Math.hypot(a.x - b.x, a.y - b.y);
  }

  // Pinch: başparmak ucu (4) ↔ işaret parmağı ucu (8) < eşik
  function _isPinch(lm) {
    return _dist2d(lm[4], lm[8]) < 0.06;
  }

  // Açık avuç: 4 parmak ucu (8,12,16,20) PIP eklemlerinin (6,10,14,18) üstünde
  function _isPalmOpen(lm) {
    return [0,1,2,3].every(i => lm[8 + i*4].y < lm[6 + i*4].y);
  }

  // ── Dalga algılama (wrist X zig-zag sayısı) ───────── //
  let _wristHist = [];
  function _isWave(wristX) {
    const now = Date.now();
    _wristHist = _wristHist.filter(e => now - e.t < 900);
    if (!_wristHist.length || Math.abs(wristX - _wristHist.at(-1).x) > 0.04) {
      _wristHist.push({ t: now, x: wristX });
    }
    let changes = 0;
    for (let i = 2; i < _wristHist.length; i++) {
      const d1 = _wristHist[i].x   - _wristHist[i-1].x;
      const d2 = _wristHist[i-1].x - _wristHist[i-2].x;
      if (d1 * d2 < 0) changes++;
    }
    return changes >= 3;
  }

  // ── Zamanlayıcılar (cooldown) ─────────────────────── //
  let _pinchCooldown = 0;
  let _waveCooldown  = 0;
  let _palmStart     = 0;   // avuç ne zaman açıldı
  let _palmFired     = false;

  // ── Sonuç işleyici ─────────────────────────────────── //
  function _onResults(results) {
    if (!results.multiHandLandmarks?.length) {
      _wristHist = [];
      _palmStart = 0;
      _palmFired = false;
      return;
    }
    const lm  = results.multiHandLandmarks[0];
    const now = Date.now();

    // Pinch → gönder
    if (_isPinch(lm) && now > _pinchCooldown) {
      const inp = document.getElementById('msg-input');
      if (inp?.value?.trim()) {
        sendMessage();
        _pinchCooldown = now + 2500;
      }
    }

    // Wave → durdur
    if (_isWave(lm[0].x) && now > _waveCooldown) {
      stopAudio();
      _waveCooldown = now + 2000;
      _wristHist = [];
    }

    // Palm açık 1.5s → sessiz/sesli toggle
    if (_isPalmOpen(lm)) {
      if (!_palmStart) { _palmStart = now; _palmFired = false; }
      else if (!_palmFired && now - _palmStart > 1500) {
        _toggleMute();
        _palmFired = true;
      }
    } else {
      _palmStart = 0;
      _palmFired = false;
    }
  }

  // ── Başlatma ──────────────────────────────────────── //
  async function _loadScript(src) {
    return new Promise((ok, fail) => {
      if (document.querySelector(`script[src="${src}"]`)) { ok(); return; }
      const s = document.createElement('script');
      s.src = src; s.crossOrigin = 'anonymous';
      s.onload = ok; s.onerror = fail;
      document.head.appendChild(s);
    });
  }

  async function _init() {
    const CDN = 'https://cdn.jsdelivr.net/npm/@mediapipe';
    await _loadScript(`${CDN}/hands/hands.js`);
    await _loadScript(`${CDN}/camera_utils/camera_utils.js`);

    _vid = document.createElement('video');
    _vid.style.cssText = 'position:fixed;bottom:0;right:0;width:1px;height:1px;opacity:0;pointer-events:none;';
    document.body.appendChild(_vid);

    _hands = new window.Hands({
      locateFile: f => `${CDN}/hands/${f}`,
    });
    _hands.setOptions({
      maxNumHands: 1,
      modelComplexity: 0,          // 0=lite, hız öncelikli
      minDetectionConfidence: 0.7,
      minTrackingConfidence: 0.5,
    });
    _hands.onResults(_onResults);

    _camera = new window.Camera(_vid, {
      onFrame: async () => { if (_hands) await _hands.send({ image: _vid }); },
      width: 320,
      height: 240,
      facingMode: 'user',
    });
    await _camera.start();
  }

  function _destroy() {
    if (_camera) { _camera.stop(); _camera = null; }
    if (_hands)  { _hands.close().catch(()=>{}); _hands = null; }
    if (_vid)    { _vid.remove(); _vid = null; }
    _wristHist = [];
    _palmStart = 0;
    _palmFired = false;
  }

  // ── Toggle (global) ───────────────────────────────── //
  window.toggleGestureMode = async function() {
    gestureEnabled = !gestureEnabled;
    if (gestureEnabled) {
      $btn?.classList.add('gesture-connecting');
      try {
        await _init();
        $btn?.classList.remove('gesture-connecting');
        $btn?.classList.add('gesture-active');
        if ($btn) $btn.title = _t('jest.aktif');
      } catch (err) {
        gestureEnabled = false;
        $btn?.classList.remove('gesture-connecting');
        addMessage('yuki', _t('ortak.hata-ayrinti', { mesaj: _t('jest.baslatilamadi'), ayrinti: String(err?.message || err) }));
      }
    } else {
      _destroy();
      $btn?.classList.remove('gesture-active', 'gesture-connecting');
      if ($btn) $btn.title = _t('jest.baslik');
    }
  };
})();

document.getElementById('msg-input').oninput = function() {
  this.style.height = 'auto'; this.style.height = (this.scrollHeight) + 'px';
  _cmdPaletteInput(this.value);
};

// ══════════════════════════════════════════════════════
//  COMMAND PALETTE  (/ prefix)
// ══════════════════════════════════════════════════════
(function() {
  /* 🔴 MODÜL DÜZEYİ SABİT — bu dalgada YEDİNCİ kez. Eskiden bu dizi çözülmüş
     Türkçe `label`/`hint`/`fill` taşıyordu ve modül yüklenirken donuyordu.
     Artık yalnız KİMLİK (`ad`) tutuluyor; metin çizimde çözülüyor.

     🔑 `ad` bir KİMLİKTİR, görünen etiket değil: kod (`_ctxSearch`) ve filtre
     bu adı kullanır, kullanıcının gördüğü `/ara` ise `komut.<ad>.etiket`ten
     gelir ve İngilizce'de `/search` olur.

     🔴 `ogren` ÖZEL: backend onu METİNDEN tanıyor
     (`api/websocket.py::_ut.lower().startswith(("/öğren", "/ogren", …))`) ve
     LLM'i ATLAYIP beceri belleğine yazıyor. Etiketi çevirince o eşleşme
     ölürdü — hata vermeden: cümle düz sohbet olarak modele giderdi ve
     kullanıcı "öğretmiştim" derken hiçbir şey kaydedilmemiş olurdu. Backend'in
     ön ek listesine İngilizce karşılık EKLENDİ; iki taraf
     `test_komut_onekleri_iki_dilde_eslesiyor` ile birbirine bağlandı. */
  const _KOMUTLAR = [
    { ad: 'ekran' },
    { ad: 'ara',       etiketiDoldur: true },
    { ad: 'hafiza',    etiketiDoldur: true },
    { ad: 'ogren',     etiketiDoldur: true },
    { ad: 'hatirlat' },
    { ad: 'pano' },
    { ad: 'sistem' },
    { ad: 'karakter' },
    { ad: 'dil',       eylem: () => { try { toggleLanguage(); } catch (_) {} } },
    { ad: 'sekme' },
    { ad: 'medya' },
    { ad: 'ses' },
    { ad: 'oyun' },
    { ad: 'uygulama' },
    { ad: 'web' },
    { ad: 'temizle',   eylem: () => clearHistory() },
    { ad: 'aktar',     eylem: () => exportChat() },
    { ad: 'yardim' },
  ];

  const _etiket = (c) => _t('komut.' + c.ad + '.etiket');
  const _ipucu  = (c) => _t('komut.' + c.ad + '.ipucu');
  /* Doldurulan metin: üç komutta etiketin kendisi (`/ara ` gibi bir ÖN EK),
     ötekilerde ayrı bir cümle. Ön ek ayrı bir anahtarda tutulsaydı etiketle
     ayrışabilirdi — `/search` yazıp `/ara ` doldurmak sessiz bir arıza olurdu. */
  const _doldur = (c) => (c.etiketiDoldur ? _etiket(c) + ' ' : _t('komut.' + c.ad + '.doldur'));
  window._komutEtiketi = (ad) => _t('komut.' + ad + '.etiket');

  const palette = document.getElementById('cmd-palette');
  const inp = document.getElementById('msg-input');
  let _selIdx = -1;
  let _visible = false;
  let _filtered = [];

  function _render(cmds) {
    _filtered = cmds;
    _selIdx = cmds.length ? 0 : -1;
    palette.innerHTML = '';
    cmds.forEach((c, i) => {
      const div = document.createElement('button');
      div.type = 'button';
      div.id = 'cmd-palette-sec-' + i;
      div.className = 'cmd-item' + (i === 0 ? ' selected' : '');
      div.dataset.idx = i;
      div.setAttribute('role', 'option');
      div.setAttribute('aria-selected', i === 0 ? 'true' : 'false');
      div.tabIndex = -1;
      /* 🔑 `innerHTML` + dizge birleştirme YERİNE DOM API. Metin artık
         sözlükten geliyor; bir çeviride `&` ya da `<` geçse eski kod onu
         işaretleme olarak yorumlardı. Aynı dosyadaki `_fillModelSheet` bu
         kararı zaten vermişti (satır içi yorumu okuyun) — kural burada da
         geçerli, istisna değil. */
      for (const [sinif, metin] of [
        ['cmd-item-label', _etiket(c)], ['cmd-item-hint', _ipucu(c)],
      ]) {
        const sp = document.createElement('span');
        sp.className = sinif;
        sp.textContent = metin;
        div.appendChild(sp);
      }
      div.addEventListener('mousedown', e => e.preventDefault());
      div.addEventListener('click', () => _pick(i));
      palette.appendChild(div);
    });
    palette.classList.toggle('open', cmds.length > 0);
    _visible = cmds.length > 0;
    /* Palet yazma alanından YUKARI açılır; dar ekranda sabit üst sınır (64dvh)
       onu sohbetin üstündeki portre/başlık katmanının altına sokuyordu (ilk
       satır görünmüyordu). Yükseklik mesaj alanının üst kenarına kadar sınırlanır. */
    const mesajlar = document.getElementById('messages');
    if (_visible && mesajlar) {
      palette.style.maxHeight = '';
      const ust = mesajlar.getBoundingClientRect().top;
      const alt = palette.getBoundingClientRect().bottom;
      if (ust > 0 && alt > ust) {
        let tavan = Math.max(132, Math.floor(alt - ust - 8));
        // Tam satıra yuvarla: alt kenarda yarım kesik satır bozuk görünüyordu.
        const ogeler = palette.querySelectorAll('.cmd-item');
        if (ogeler.length > 1) {
          const adim = ogeler[1].offsetTop - ogeler[0].offsetTop;
          const ic = ogeler[0].offsetTop;
          if (adim > 0 && palette.scrollHeight > tavan) {
            const kenar = palette.clientTop * 2;   // border-box: max-height kenarı da içerir
            // Alt iç boşluk BIRAKILMAZ: kayan içerik o boşluğa da taşar ve bir
            // sonraki satırın birkaç pikseli görünürdü. Son satır alt kenara oturur.
            tavan = kenar + ic + Math.max(3, Math.floor((tavan - kenar - ic) / adim)) * adim - (adim - ogeler[0].offsetHeight);
          }
        }
        palette.style.maxHeight = tavan + 'px';
      }
    }
    inp.setAttribute('aria-expanded', _visible ? 'true' : 'false');
    if (_selIdx >= 0) inp.setAttribute('aria-activedescendant', 'cmd-palette-sec-' + _selIdx);
    else inp.removeAttribute('aria-activedescendant');
  }

  function _pick(i) {
    const c = _filtered[i];
    if (!c) return;
    if (c.eylem) {
      inp.value = '';
      _render([]);
      c.eylem();
    } else {
      inp.value = _doldur(c);
      inp.style.height = 'auto';
      inp.style.height = inp.scrollHeight + 'px';
      _render([]);
      inp.focus();
      // place cursor at end
      setTimeout(() => { inp.selectionStart = inp.selectionEnd = inp.value.length; }, 0);
    }
  }

  function _updateSel(idx) {
    _selIdx = idx;
    palette.querySelectorAll('.cmd-item').forEach((el, i) => {
      el.classList.toggle('selected', i === idx);
      el.setAttribute('aria-selected', i === idx ? 'true' : 'false');
    });
    const aktif = palette.querySelector('#cmd-palette-sec-' + idx);
    if (aktif) {
      inp.setAttribute('aria-activedescendant', aktif.id);
      aktif.scrollIntoView({ block: 'nearest' });
    }
  }

  window._cmdPaletteInput = function(val) {
    if (!val.startsWith('/')) { _render([]); return; }
    /* 🔴 Süzme ÇEVRİLMİŞ etikete bakar (`_etiket(c)`), koddaki `ad`'a değil.
       Etiketler dilden dile değişir; sabit bir listeye bakılsaydı İngilizce
       kullanıcı `/se` yazınca hiçbir şey eşleşmezdi.
       ⚠️ `toLowerCase()` DEĞİL `toLocaleLowerCase()`: Türkçe'de `I` → `ı`'dır
       ve `/HATIRLAT` yazan kullanıcı `tolowercase` ile `/hatirlat`a düşerdi
       ama etiket `/hatırlat` — eşleşmezdi. (Blok 10'un TR 'i'→'I' tuzağının
       ters yönü.) */
    const yerel = (window.YukiDil && window.YukiDil.al) ? window.YukiDil.al() : 'tr';
    const q = val.toLocaleLowerCase(yerel);
    const matches = _KOMUTLAR.filter(c => _etiket(c).toLocaleLowerCase(yerel).startsWith(q) || q === '/');
    _render(matches);
  };

  inp.addEventListener('keydown', e => {
    if (!_visible) return;
    if (e.key === 'ArrowDown') {
      e.preventDefault();
      _updateSel(Math.min(_selIdx + 1, _filtered.length - 1));
    } else if (e.key === 'ArrowUp') {
      e.preventDefault();
      _updateSel(Math.max(_selIdx - 1, 0));
    } else if (e.key === 'Enter' && _selIdx >= 0) {
      e.preventDefault();
      e.stopImmediatePropagation();
      _pick(_selIdx);
    } else if (e.key === 'Escape') {
      _render([]);
    } else if (e.key === 'Tab' && _selIdx >= 0) {
      e.preventDefault();
      _pick(_selIdx);
    }
  });

  // Close when clicking outside
  document.addEventListener('mousedown', e => {
    if (_visible && !palette.contains(e.target) && e.target !== inp) {
      _render([]);
    }
  });
})();

// ══════════════════════════════════════════════════════
//  ENTER → GÖNDER, Alt+Enter → ALT SATIR
//  (Komut paleti açık + öğe seçiliyken palet handler'ı Enter'ı
//   stopImmediatePropagation ile yakalar; bu listener ONDAN SONRA
//   kayıtlı olmalı ki palet seçimini bozmasın.)
// ══════════════════════════════════════════════════════
(function() {
  const inp = document.getElementById('msg-input');
  if (!inp) return;
  inp.addEventListener('keydown', (e) => {
    if (e.key !== 'Enter' || e.isComposing || e.keyCode === 229) return; // IME besteleme sırasında dokunma
    // Alt+Enter veya Shift+Enter → imleç konumuna satır sonu ekle
    if (e.altKey || e.shiftKey) {
      e.preventDefault();
      const s = inp.selectionStart, end = inp.selectionEnd;
      inp.value = inp.value.slice(0, s) + '\n' + inp.value.slice(end);
      inp.selectionStart = inp.selectionEnd = s + 1;
      inp.dispatchEvent(new Event('input')); // auto-grow + palet senkron
      return;
    }
    // Düz Enter → gönder
    e.preventDefault();
    sendMessage();
  });
})();

// ══════════════════════════════════════════════════════
//  SELECTION CONTEXT MENU
// ══════════════════════════════════════════════════════
(function() {
  const menu = document.getElementById('sel-ctx-menu');
  const mesajlar = document.getElementById('messages');
  let _sel = '';
  let _oncekiOdak = null;

  function _ogeler() {
    return Array.from(menu.querySelectorAll('[role="menuitem"]'));
  }

  /* `cumle` = seçimin kutusu. Menü seçimin ALTINA açılır; altta yer yoksa
     ÜSTÜNE çevrilir — eskiden ekrana sığdırmak için yukarı itiliyor ve seçilen
     metnin üstüne biniyordu. */
  function _show(x, cumle, oncekiOdak) {
    _oncekiOdak = oncekiOdak instanceof HTMLElement ? oncekiOdak : document.activeElement;
    menu.classList.add('open');
    const bosluk = 12;
    const genislik = menu.offsetWidth;
    const yukseklik = menu.offsetHeight;
    let y = cumle.bottom + 4;
    if (y + yukseklik > window.innerHeight - bosluk && cumle.top - 4 - yukseklik >= bosluk) {
      y = cumle.top - 4 - yukseklik;
    }
    menu.style.left = Math.max(bosluk, Math.min(x, window.innerWidth - genislik - bosluk)) + 'px';
    menu.style.top = Math.max(bosluk, Math.min(y, window.innerHeight - yukseklik - bosluk)) + 'px';
    const ogeler = _ogeler();
    ogeler.forEach((oge, i) => { oge.tabIndex = i === 0 ? 0 : -1; });
    if (ogeler[0]) ogeler[0].focus();
  }

  function _hide(odagiGeriVer) {
    menu.classList.remove('open');
    _ogeler().forEach(oge => { oge.tabIndex = -1; });
    if (odagiGeriVer && _oncekiOdak && _oncekiOdak.isConnected) _oncekiOdak.focus();
  }

  // Show on mouseup inside #messages if text is selected
  mesajlar.addEventListener('mouseup', (e) => {
    const s = window.getSelection();
    const text = s ? s.toString().trim() : '';
    if (!text) { _hide(false); return; }
    _sel = text;
    const kutu = s.rangeCount ? s.getRangeAt(0).getBoundingClientRect() : null;
    _show(e.clientX + 4, kutu && kutu.height ? kutu : { top: e.clientY, bottom: e.clientY }, e.target);
  });

  // Klavye yolu: seçili metinde Menü tuşu veya Shift+F10 aynı menüyü açar.
  mesajlar.addEventListener('keydown', (e) => {
    if (e.key !== 'ContextMenu' && !(e.shiftKey && e.key === 'F10')) return;
    const s = window.getSelection();
    const text = s ? s.toString().trim() : '';
    if (!text || !s.rangeCount || !mesajlar.contains(s.anchorNode)) return;
    e.preventDefault();
    _sel = text;
    const rect = s.getRangeAt(0).getBoundingClientRect();
    _show(rect.left, rect, document.activeElement);
  });

  menu.addEventListener('keydown', (e) => {
    const ogeler = _ogeler();
    const sira = ogeler.indexOf(document.activeElement);
    if (!ogeler.length) return;
    let hedef = sira;
    if (e.key === 'ArrowDown') hedef = (sira + 1 + ogeler.length) % ogeler.length;
    else if (e.key === 'ArrowUp') hedef = (sira - 1 + ogeler.length) % ogeler.length;
    else if (e.key === 'Home') hedef = 0;
    else if (e.key === 'End') hedef = ogeler.length - 1;
    else if (e.key === 'Escape') {
      e.preventDefault();
      _hide(true);
      return;
    } else if (e.key === 'Tab') {
      e.preventDefault();
      hedef = e.shiftKey
        ? (sira - 1 + ogeler.length) % ogeler.length
        : (sira + 1 + ogeler.length) % ogeler.length;
    } else return;
    e.preventDefault();
    ogeler.forEach((oge, i) => { oge.tabIndex = i === hedef ? 0 : -1; });
    ogeler[hedef].focus();
  });

  // Hide on click outside
  document.addEventListener('mousedown', (e) => {
    if (!menu.contains(e.target)) _hide(false);
  });

  window._ctxAsk = function() {
    const inp = document.getElementById('msg-input');
    if (inp) inp.value = _sel;
    _hide(true);
    sendMessage();
  };
  window._ctxSearch = function() {
    const inp = document.getElementById('msg-input');
    // Ön ek komut paletindeki ETİKETTEN gelir — ikinci bir yerde yazılsaydı
    // etiket çevrilince burası eski dilde kalır ve komut tanınmazdı.
    if (inp) inp.value = window._komutEtiketi('ara') + ' ' + _sel;
    _hide(true);
    sendMessage();
  };
  window._ctxCopy = function() {
    navigator.clipboard.writeText(_sel).then(() => showToast(_t('secim.kopyalandi'), 'ok', 1500));
    _hide(true);
  };
  window._ctxDefine = function() {
    const inp = document.getElementById('msg-input');
    if (inp) inp.value = _t('secim.ne-demek', { metin: _sel.slice(0, 120) });
    _hide(true);
    sendMessage();
  };
  window._ctxTranslate = function() {
    const inp = document.getElementById('msg-input');
    /* 🔴 HEDEF DİL SABİT YAZILAMAZ: İngilizce arayüzde "Türkçe'ye çevir"
       demek yanlış olurdu. Hedef dil artık çevirinin kendisinde. */
    if (inp) inp.value = _t('secim.cevir', { metin: _sel.slice(0, 300) });
    _hide(true);
    sendMessage();
  };
})();

// ── Lightbox ────────────────────────────────────────────────────
let _lightboxOncekiOdak = null;

function openLightbox(src, filename) {
  const lb = document.getElementById('lightbox');
  _lightboxOncekiOdak = document.activeElement instanceof HTMLElement ? document.activeElement : null;
  document.getElementById('lightbox-img').src = src;
  const dl = document.getElementById('lightbox-download');
  dl.href = src;
  dl.download = filename || 'screenshot.jpg';
  lb.hidden = false;
  document.body.style.overflow = 'hidden';
  document.getElementById('lightbox-close').focus();
}
function closeLightbox() {
  const lb = document.getElementById('lightbox');
  if (!lb || lb.hidden) return;
  lb.hidden = true;
  document.getElementById('lightbox-img').src = '';
  document.body.style.overflow = '';
  if (_lightboxOncekiOdak && _lightboxOncekiOdak.isConnected) _lightboxOncekiOdak.focus();
  _lightboxOncekiOdak = null;
}
document.getElementById('lightbox-backdrop').onclick = closeLightbox;
document.getElementById('lightbox-close').onclick = closeLightbox;
document.addEventListener('keydown', e => {
  const lb = document.getElementById('lightbox');
  if (!lb || lb.hidden) return;
  if (e.key === 'Escape') {
    e.preventDefault();
    closeLightbox();
    return;
  }
  if (e.key !== 'Tab') return;
  const odaklanabilir = Array.from(lb.querySelectorAll('a[href], button:not([disabled])'));
  if (!odaklanabilir.length) return;
  const ilk = odaklanabilir[0];
  const son = odaklanabilir[odaklanabilir.length - 1];
  if (!lb.contains(document.activeElement)) {
    e.preventDefault();
    (e.shiftKey ? son : ilk).focus();
  } else if (e.shiftKey && document.activeElement === ilk) {
    e.preventDefault();
    son.focus();
  } else if (!e.shiftKey && document.activeElement === son) {
    e.preventDefault();
    ilk.focus();
  }
});

function _startMemoryStatsPoll() {
  setInterval(async () => {
    try {
      const r = await authFetch(`${BASE_URL}/api/memory/stats`);
      if (!r.ok) return;
      const d = await r.json();
      document.getElementById('mem-num').textContent = d.total || 0;
    } catch (_) {}
  }, 5000);
}

// Auth kapısı ve başlangıç bağlantıları
(async () => {
  // Auth sunucuda aktif mi? Değilse bypass et
  const ok = await _authCheckAndInit();
  if (ok) {
    // Auth gerekmiyor (sunucu tokensiz kabul etti) → chat sekmesi zaten switchTab ile görünür
    document.getElementById('auth-screen').classList.add('hidden');
    if (typeof window._runOpeningAnimation === 'function') window._runOpeningAnimation();
    connect();
    _startMemoryStatsPoll();
    initModelSelector();
    initLanguageSelector();
  }
  // Auth gerekliyse _authCheckAndInit şifre ekranını gösterdi;
  // kullanıcı şifre girdikten sonra _hideAuthScreen auth perdesini kapatır.
})();

// ── Model Selector ───────────────────────────────────────────────────
let _currentProvider = 'openrouter';
let _currentModelId  = 'google/gemma-4-26b-a4b-it:free';   // .env.example / config.py varsayılanıyla aynı (B7, 11-14)

const _PRESETS = {
  openrouter: [
    { id: 'openai/gpt-4.1-mini',                 label: 'GPT-4.1 Mini',    fast: true  },
    { id: 'openai/gpt-4.1',                      label: 'GPT-4.1',         fast: false },
    { id: 'openai/gpt-4o-mini',                  label: 'GPT-4o Mini',     fast: true  },
    { id: 'anthropic/claude-haiku-4-5-20251001', label: 'Haiku 4.5',       fast: true  },
    { id: 'anthropic/claude-sonnet-4-5',         label: 'Sonnet 4.5',      fast: false },
    { id: 'anthropic/claude-sonnet-4-6',         label: 'Sonnet 4.6 ◆',    fast: false },
    { id: 'anthropic/claude-opus-4-5',           label: 'Opus 4.5',        fast: false },
    { id: 'anthropic/claude-opus-4-7',           label: 'Opus 4.7',        fast: false },
    { id: 'google/gemini-3.5-flash-lite',        label: 'Gemini Flash-lite', fast: true  },
  ],
  anthropic: [
    { id: 'claude-haiku-4-5-20251001', label: 'Haiku 4.5',  fast: true  },
    { id: 'claude-sonnet-4-6',         label: 'Sonnet 4.6 ◆', fast: false },
    { id: 'claude-opus-4-7',           label: 'Opus 4.7',   fast: false },
  ],
};

// ── Claude Brain Modu ────────────────────────────────────────────────
// claude_code → claude CLI subprocess, üyelik kullanır, API key gereksiz
// Araçlar çalışmaz ama analiz/sohbet için ideal
const _CLAUDE_BRAIN_MODEL    = 'claude-code';
const _CLAUDE_BRAIN_PROVIDER = 'claude_code';
/* B7 (11-14): Claude modu kapanınca dönülen model ücretliydi (gpt-4.1-mini); kurulumun varsayılanı
   ücretsiz Gemma (.env.example, config.LLM_MODEL). Kapatınca kullanıcı sessizce ücretli modele geçmesin. */
const _DEFAULT_MODEL         = 'google/gemma-4-26b-a4b-it:free';
const _DEFAULT_PROVIDER      = 'openrouter';
let   _claudeBrainActive     = false;

function _syncClaudeBrainBtn() {
  const btn   = document.getElementById('claude-brain-btn');
  const label = document.getElementById('claude-brain-label');
  if (!btn) return;
  const isActive = _currentProvider === _CLAUDE_BRAIN_PROVIDER;
  _claudeBrainActive = isActive;
  btn.classList.toggle('active', isActive);
  // ⋯ menüsünde tam ad kullanılıyor (2026-08-03) — ikon-only düğmede 'Claude'
  // yetiyordu, etiketli menüde ne olduğu anlaşılmalı.
  // Araç yayında kısa ad (11-14); açık/kapalı durumu düğümün altın rengi + title söyler.
  if (label) label.textContent = _t('girdi.yay.claude');
  btn.title = _t(isActive ? 'model.claude-beyni-acik' : 'girdi.claude-beyni');
}

async function toggleClaudeBrain() {
  if (_claudeBrainActive) {
    await selectModel(_DEFAULT_PROVIDER, _DEFAULT_MODEL);
  } else {
    try {
      const r = await authFetch(`${BASE_URL}/api/llm/config`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ provider: 'claude_code', model: 'claude-code' }),
      });
      const d = await r.json();
      if (d.ok) {
        _currentProvider = 'claude_code';
        _currentModelId  = 'claude-code';
        _renderModelLabel();
      } else {
        console.error('Claude Brain hatası:', d.error);
      }
    } catch(e) { console.error('Claude Brain:', e); }
  }
  _syncClaudeBrainBtn();
}

const _MODEL_LABEL = {};
for (const [, models] of Object.entries(_PRESETS))
  for (const m of models) _MODEL_LABEL[m.id] = m.label;

function _renderModelLabel() {
  const el = document.getElementById('model-label');
  if (!el) return;
  if (_currentProvider === 'claude_code') { el.textContent = _t('model.claude-rozet'); return; }
  el.textContent = _MODEL_LABEL[_currentModelId] || _currentModelId.split('/').pop() || _t('girdi.model');
}

// Seçenekler <div onclick> DEĞİL <button role="radio"> olarak üretilir: div'e Tab ile
// ulaşılamıyordu, Enter/Space çalışmıyordu. innerHTML yerine DOM API — model etiketi
// ileride /api/llm/models'ten gelecek, kaçışsız şablon oraya XSS taşırdı.
function _fillModelSheet() {
  const liste = document.getElementById('model-popover-liste');
  if (!liste) return;
  liste.textContent = '';
  for (const [prov, models] of Object.entries(_PRESETS)) {
    const bolum = document.createElement('div');
    bolum.className = 'model-bolum';

    const baslik = document.createElement('div');
    baslik.className = 'model-bolum-baslik';
    // ⚪ 'OpenRouter' marka adı — çevrilmez. 'Direkt' sıfatı çevrilir.
    baslik.textContent = prov === 'openrouter' ? 'OpenRouter' : _t('model.anthropic-direkt');
    bolum.appendChild(baslik);

    for (const m of models) {
      const secili = prov === _currentProvider && m.id === _currentModelId;
      const dugme = document.createElement('button');
      dugme.type = 'button';
      dugme.className = 'dg dg-sessiz model-secenek';
      dugme.setAttribute('role', 'radio');
      dugme.setAttribute('aria-checked', secili ? 'true' : 'false');
      // Roving tabindex: gruba tek Tab'la girilir, içinde ok tuşlarıyla gezilir.
      dugme.tabIndex = secili ? 0 : -1;
      dugme.dataset.saglayici = prov;
      dugme.dataset.model = m.id;

      const ad = document.createElement('span');
      ad.className = 'model-secenek-ad';
      ad.textContent = m.label;
      dugme.appendChild(ad);

      if (m.fast) {
        const hizli = document.createElement('span');
        hizli.className = 'model-secenek-hizli';
        hizli.textContent = _t('model.hizli');
        // Rozet metni ekran okuyucuya da geçsin — ⚡ tek başına anlam taşımıyordu.
        dugme.setAttribute('aria-label', _t('model.aria-hizli', { model: m.label }));
        dugme.appendChild(hizli);
      }

      dugme.addEventListener('click', () => selectModel(prov, m.id));
      bolum.appendChild(dugme);
    }
    liste.appendChild(bolum);
  }

  /* Kullanılan model ön ayarlarda yoksa (ör. ücretsiz başlangıç modeli, AYAR'dan
     elle seçilen) listede HİÇBİR şey seçili görünmüyordu ( M5). En üste
     "Şu an kullanılan" bölümüyle eklenir; tıklamak yeniden POST etmez, kapatır. */
  if (_currentModelId && !liste.querySelector('[role="radio"][aria-checked="true"]')) {
    const bolum = document.createElement('div');
    bolum.className = 'model-bolum';
    const baslik = document.createElement('div');
    baslik.className = 'model-bolum-baslik';
    baslik.textContent = _t('model.su-an-kullanilan');
    bolum.appendChild(baslik);
    const dugme = document.createElement('button');
    dugme.type = 'button';
    dugme.className = 'dg dg-sessiz model-secenek';
    dugme.setAttribute('role', 'radio');
    dugme.setAttribute('aria-checked', 'true');
    dugme.tabIndex = 0;
    dugme.dataset.saglayici = _currentProvider;
    dugme.dataset.model = _currentModelId;
    const ad = document.createElement('span');
    ad.className = 'model-secenek-ad';
    ad.textContent = _MODEL_LABEL[_currentModelId] || _currentModelId.split('/').pop();
    dugme.title = _currentModelId;
    dugme.appendChild(ad);
    dugme.addEventListener('click', closeModelDropdown);
    bolum.appendChild(dugme);
    liste.insertBefore(bolum, liste.firstChild);
  }

  // Grupta seçili öğe yoksa (kayıtlı model listeden kalkmış) ilk seçenek Tab'la
  // ulaşılabilir kalmalı; yoksa gruba klavyeyle hiç girilemez.
  if (!liste.querySelector('[role="radio"][tabindex="0"]')) {
    const ilk = liste.querySelector('[role="radio"]');
    if (ilk) ilk.tabIndex = 0;
  }
}

// Ok tuşları yalnız ODAĞI taşır, seçimi uygulamaz. Standart radiogroup deseni
// odakla birlikte seçer; burada her ok tuşu bir POST /api/llm/config demek olurdu.
// Seçim Enter/Space/tık ile — aria-checked daima gerçekten uygulanmış modeli gösterir.
function _modelKlavyeBagla() {
  const liste = document.getElementById('model-popover-liste');
  if (!liste) return;
  liste.addEventListener('keydown', (e) => {
    const secenekler = Array.prototype.slice.call(liste.querySelectorAll('[role="radio"]'));
    const sira = secenekler.indexOf(document.activeElement);
    if (sira === -1 || !secenekler.length) return;
    const ileri = e.key === 'ArrowRight' || e.key === 'ArrowDown';
    const geri  = e.key === 'ArrowLeft'  || e.key === 'ArrowUp';
    if (!ileri && !geri && e.key !== 'Home' && e.key !== 'End') return;
    e.preventDefault();
    const hedefSira = e.key === 'Home' ? 0
      : e.key === 'End' ? secenekler.length - 1
      : (sira + (ileri ? 1 : -1) + secenekler.length) % secenekler.length;
    secenekler.forEach((d, i) => { d.tabIndex = i === hedefSira ? 0 : -1; });
    secenekler[hedefSira].focus();
  });
}

async function initModelSelector() {
  _modelPopoverBagla();
  _renderModelLabel();
  _fillModelSheet();
  // API'den gerçek aktif modeli al
  try {
    const r = await authFetch(`${BASE_URL}/api/llm/config`);
    if (r.ok) {
      const d = await r.json();
      _currentProvider = d.provider || _currentProvider;
      _currentModelId  = d.model   || _currentModelId;
      _renderModelLabel();
      _fillModelSheet();
    }
  } catch (_) {}
  _syncClaudeBrainBtn();
}

// Açma/kapama artık markup'taki popovertarget'ın işi. Bu iki fonksiyon kodun başka
// yerlerinden (selectModel, kısayollar) gelen çağrılar için duruyor.
function toggleModelDropdown(e) {
  e && e.stopPropagation();
  const pop = document.getElementById('model-popover');
  if (pop && typeof pop.togglePopover === 'function') pop.togglePopover();
}

function closeModelDropdown() {
  const pop = document.getElementById('model-popover');
  if (pop && typeof pop.hidePopover === 'function' && pop.matches(':popover-open')) {
    pop.hidePopover();
  }
}

/* Popover açan düğmeye bağlı açılır ( M4). Eskiden ekranın ortasında, hapın
   ~600px solunda açılıyordu — kullanıcı neyin açıldığını düğmeyle eşleyemiyordu.
   Yer: tetiğin üstü (sığmazsa altı), tetiğin yakın kenarına hizalı, ekrana kıstırılmış.
   Tetik ⋯ menüsündeyse menü kapanınca 0×0 kalır → ⋯ düğmesine bağlanır. */
function _modelPopoverKonumla(pop, tetik) {
  if (!pop) return;
  let r = tetik && tetik.getBoundingClientRect();
  if (!r || !r.width) {
    const daha = document.getElementById('input-more-btn');
    r = daha && daha.getBoundingClientRect();
  }
  if (!r || !r.width) return;   // bağlanacak yer yok → CSS varsayılanı kalır
  const vw = document.documentElement.clientWidth, vh = window.innerHeight;
  const pay = vw <= 480 ? 6 : 12, ara = 8;
  const gen = Math.min(420, vw - pay * 2);
  const ust = r.top - ara - pay, alt = vh - r.bottom - ara - pay;
  const yukari = ust >= Math.min(240, alt);
  let sol = (r.left + r.width / 2 > vw / 2) ? r.right - gen : r.left;
  sol = Math.max(pay, Math.min(sol, vw - pay - gen));
  const s = pop.style;
  s.inset = 'auto';
  s.translate = 'none';
  s.left = Math.round(sol) + 'px';
  s.inlineSize = Math.round(gen) + 'px';
  s.maxBlockSize = Math.round(Math.min(vw <= 480 ? 560 : 420, yukari ? ust : alt)) + 'px';
  if (yukari) s.bottom = Math.round(vh - r.top + ara) + 'px';
  else s.top = Math.round(r.bottom + ara) + 'px';
}

/* Taşan listede kenar solar ( M5): kaydırılabilir olduğu, yarım kesik bir
   satırdan anlaşılmasın diye. Sınıf yalnız o yönde daha içerik varken durur. */
function _modelTasmaIpucu(pop) {
  if (!pop) return;
  const kalanAlt = pop.scrollHeight - pop.clientHeight - pop.scrollTop;
  pop.classList.toggle('tasma-ust', pop.scrollTop > 2);
  pop.classList.toggle('tasma-alt', kalanAlt > 2);
}

function _modelPopoverBagla() {
  const pop   = document.getElementById('model-popover');
  const tetik = document.getElementById('model-selector-btn');
  const tetikler = Array.from(document.querySelectorAll('[popovertarget="model-popover"]'));
  let acan = null;
  if (!pop || pop.dataset.bagli) return;

  // Yapılamayan özellik ilan edilmez (S16): Popover API yoksa tetik gizlenir,
  // yarım çalışan bir menü bırakılmaz.
  if (typeof pop.showPopover !== 'function') {
    if (tetik) tetik.hidden = true;
    return;
  }
  pop.dataset.bagli = '1';

  // Açıcıyı UA odağı top-layer'a taşımadan önce yakala. `toggle` bu iş için
  // bazı Chromium sürümlerinde geç kalır ve kapanışta odak gövdeye düşer.
  pop.addEventListener('beforetoggle', (e) => {
    if (e.newState === 'open' && tetikler.includes(document.activeElement)) {
      acan = document.activeElement;
    }
  });

  pop.addEventListener('toggle', (e) => {
    const acik = e.newState === 'open';
    tetikler.forEach(d => d.setAttribute('aria-expanded', acik ? 'true' : 'false'));
    if (acik) {
      if (tetikler.includes(document.activeElement)) acan = document.activeElement;
      else if (!acan) acan = tetik;
      // Liste açılış anında tazelenir: model API'den değişmiş olabilir.
      _fillModelSheet();
      _modelPopoverKonumla(pop, acan || tetik);
      const aktif = pop.querySelector('[role="radio"][aria-checked="true"]')
                 || pop.querySelector('[role="radio"]');
      if (aktif) {
        aktif.focus({ preventScroll: true });
        /* Seçili satır listenin ortasına gelsin — kenarda yarım görünmesin (M5).
           scrollIntoView değil: o, sayfanın kaydırılabilir atalarını da kaydırır. */
        const a = aktif.getBoundingClientRect(), p = pop.getBoundingClientRect();
        pop.scrollTop += (a.top - p.top) - (pop.clientHeight - a.height) / 2;
      }
      _modelTasmaIpucu(pop);
    } else {
      const hedef = acan && acan.isConnected && !acan.hidden ? acan : tetik;
      requestAnimationFrame(() => {
        /* Fareyle başka bir öğeye tıklanarak kapandıysa odak o öğededir; çalmayız.
           Yalnız odak sahipsiz kaldıysa (Esc → body) ya da hâlâ popover'daysa geri veririz. */
        const odak = document.activeElement;
        if (odak && odak !== document.body && !pop.contains(odak)) return;
        if (hedef) hedef.focus();
        /* Taşma menüsündeki tetik popover açılınca 0×0 kalabilir. Görünmez öğeye
           focus() sessizce başarısız olursa yazma alanı güvenli geri dönüş noktası. */
        if (document.activeElement !== hedef) {
          const giris = document.getElementById('msg-input');
          if (giris) giris.focus();
        }
      });
      acan = null;
    }
  });

  pop.addEventListener('keydown', (e) => {
    if (e.key !== 'Tab') return;
    const odaklanabilir = Array.from(pop.querySelectorAll('button:not([disabled])'));
    if (!odaklanabilir.length) return;
    const ilk = odaklanabilir[0];
    const son = odaklanabilir[odaklanabilir.length - 1];
    if (e.shiftKey && document.activeElement === ilk) {
      e.preventDefault();
      son.focus();
    } else if (!e.shiftKey && document.activeElement === son) {
      e.preventDefault();
      ilk.focus();
    }
  });

  pop.addEventListener('scroll', () => _modelTasmaIpucu(pop), { passive: true });
  window.addEventListener('resize', () => {
    if (!pop.matches(':popover-open')) return;
    _modelPopoverKonumla(pop, acan || tetik);
    _modelTasmaIpucu(pop);
  });

  _modelKlavyeBagla();
}

async function selectModel(provider, modelId) {
  closeModelDropdown();
  try {
    const r = await authFetch(`${BASE_URL}/api/llm/config`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ provider, model: modelId }),
    });
    const d = await r.json();
    if (d.ok) {
      _currentProvider = provider;
      _currentModelId  = modelId;
      _renderModelLabel();
      addMessage('yuki', _t('canli.model-degisti', { ad: _MODEL_LABEL[modelId] || modelId }));
    } else {
      addMessage('yuki', _t('model.degistirilemedi', { sebep: d.error || '?' }));
    }
  } catch (e) {
    addMessage('yuki', _t('model.api-hatasi', { sebep: e.message }));
  }
}

// ── Dil seçici ───────────────────────────────────────────────────────
// 🔴 2026-09-18 (FAZ 1): burası İKİ DİLE sabitlenmişti ve üçüncü dil eklenince
// sessizce yalan söylüyordu:
//   · `_applyLangUI` → `(lang === 'ja') ? 'ja' : 'tr'` yani `en` gelince arayüz
//     TR gösteriyordu. Backend `en`, rozet `TR` — `tema.js`'in `data-theme` /
//     `data-tema` çift-sistem arızasının dil hâli.
//   · `toggleLanguage` → iki durumlu; `en` düğmeyle HİÇ seçilemezdi, üstelik
//     `en` seçiliyken düğme onu `ja`'ya atardı.
// Liste artık `/api/language`'ten (yani `config.LANGUAGES`'ten) gelir — ikinci
// bir dil kaydı tutulmaz. Dördüncü dil bu dosyaya dokunmadan çalışır.
// ── 2026-09-18 (FAZ 2): dil durumu ARTIK BURADA TUTULMUYOR ────────────────
// `_currentLang` + `_LANGS` bu dosyadan kalktı ve `js/dil.js`'e (window.YukiDil)
// taşındı. Sebep: `dil.js` <head>'de senkron yüklenip ilk kareyi çizerken burada
// ikinci bir "aktif dil" değişkeni durursa ikisi ayrışır — düzelttiğimiz
// `data-theme`/`data-tema` çift-sistem arızasının aynısı, bir tur sonra.
//
// 🔑 Her eksenin TEK KAPISI `YukiDil`'de (2026-10-04, iki eksen):
// arayüz → `YukiDil.ayarla()`, konuşma → `YukiDil.konusmaAyarla()`. Buradaki
// fonksiyonlar dil DEĞİŞTİRMİYOR, yalnız kullanıcı niyetini o kapılara iletiyor
// ve sonucu çiziyor. Backend karşılıkları `config.set_arayuz_dili()` / `set_language()`.

function _applyLangUI() {
  // Yalnız ÇİZER, iki satırı: konuşma (`#lang-*`) + arayüz (`#arayuz-label`).
  const D = window.YukiDil;
  if (!D) return;
  const konusma = D.konusma && D.konusma();
  const kSecenek = konusma ? D.konusmaSecenekleri().find((o) => o.anahtar === konusma) : null;

  const flag = document.getElementById('lang-flag');
  const label = document.getElementById('lang-label');
  if (flag) flag.textContent = kSecenek ? kSecenek.aciklama : '';   // aciklama = bayrak
  // `#lang-label` SEÇİLİ KONUŞMA DİLİNİN ADI — sunucunun `available` listesinden
  // gelir, sözlükten DEĞİL. HTML'de `data-i18n-yok` ile işaretli: çizici dokunursa
  // İngilizce'ye geçen kullanıcı düğmede "Turkish" görürdü. Açılış sorgusu
  // dönmeden konuşma bilinmez → HTML'deki değer kalır (tahmin yazılmaz).
  if (label && konusma) label.textContent = kSecenek ? kSecenek.ad : konusma.toUpperCase();

  const arayuz = D.al();
  const aSecenek = D.secenekler().find((o) => o.anahtar === arayuz);
  const aLabel = document.getElementById('arayuz-label');
  if (aLabel) aLabel.textContent = aSecenek ? aSecenek.ad : arayuz.toUpperCase();
  // ── 2026-09-18 (FAZ 3): `#lang-baslik` yazımı BURADAN KALKTI ────────────
  // O sabit bir etiket ("Konuşma dili:") ve artık `data-i18n="dil.baslik"`
  // taşıyor → sahibi `YukiDil.ciz()`. İkisi birden yazsaydı aynı alanın iki
  // sahibi olurdu; bu depoda o arıza sınıfının bedeli `data-theme`/`data-tema`
  // ile bir kez ödendi (core.js:1-14). Bir alanın tek sahibi olur.
}

// Backend dili kendi başına değiştirdiyse (WS `language_changed`, sesli komut)
// ekranı hizala ama sunucuya GERİ YAZMA — yoksa sonsuz gidiş-geliş olur.
window.addEventListener('yuki-dil-degisti', () => _applyLangUI());
window.addEventListener('yuki-konusma-dili-degisti', () => _applyLangUI());

/* ── Dil tazeleyici (FAZ 3 · Dalga 2, 2026-09-20) ───────────────────────────
   🔴 BEŞİNCİ KEZ: `dil.js::ciz()` yalnız `data-i18n` ÇAPASI taşıyan statik
   markup'ı tazeler. `core.js`'in yüzeylerinin çoğu JS'ten doğuyor ve açık
   ekranda dil değiştirildiğinde ESKİ DİLDE DONUYOR — Blok 6/8/9/10'da aynı
   arıza dört kez ayrı ayrı bulundu. Burada baştan kuruluyor.

   🔑 Tazelenen şey KABUK, içerik değil. Canlı veri (mesaj balonları, ekran
   analizi metni, hafıza sayacı) hiç ellenmez: çeviri veriyi silmemelidir.

   ⚠️ Her çağrı KENDİ kapısını taşır — panel kapalıyken çizim yapan bir
   fonksiyonu çağırmak, kullanıcı görmediği bir yüzeyi kurmak demektir. */
window.addEventListener('yuki-dil-degisti', () => {
  const dene = (ad, f) => { try { f(); } catch (e) { console.warn('[dil] tazeleme düştü:', ad, e); } };

  dene('durum-rozeti', _durumMetniYaz);
  dene('ws-rozeti', () => _setWsPill());
  dene('avatar', () => {
    const kabuk = document.querySelector('.kabuk');
    if (kabuk) _avatarDurumunuUygula(kabuk.getBoundingClientRect().width);
  });
  dene('gorunum-modu', _applyViewMode);
  dene('ekip-dugmesi', _ekipDugmesiTazele);
  dene('claude-beyni', _syncClaudeBrainBtn);
  dene('model-etiketi', () => { _renderModelLabel(); _fillModelSheet(); });
  // Wake-word banner'ı yalnız GÖRÜNÜRKEN yaz: kapalıyken metni kurmak,
  // kullanıcının hiç açmadığı bir moda ait iddiayı ekrana hazırlamak olurdu.
  dene('wake-banner', () => {
    const b = document.getElementById('wake-word-banner');
    if (b && b.classList.contains('visible')) _wakeBannerYaz();
  });
  // Ekran izleme paneli: YENİDEN KURULMAZ, yalnız etiketleri tazelenir.
  dene('ekran-izleme', () => { if (_ambIsOpen()) _ambEtiketleriTazele(); });
});

async function initLanguageSelector() {
  try {
    const r = await authFetch(`${BASE_URL}/api/language`);
    if (!r.ok) return;
    const d = await r.json();
    const D = window.YukiDil;
    if (!D) return;                       // dil.js yüklenmediyse sessiz kalma yok:
    D.listeyiKur(d.available, d.arayuz_available);   // ad + bayrak listeleri backend'den
    // 🔑 Otorite backend: localStorage'daki önbellek ayrışmışsa burada düzelir.
    // `d.arayuz` yoksa (eski backend) arayüze DOKUNMA — `language` konuşmadır.
    await D.sunucudan(d);                 // olay yayar → _applyLangUI çizer
    _applyLangUI();                       // olay yayılmadıysa da (değişmeyen dil) etiketler dolsun
  } catch (_) {}
}

// KONUŞMA dilini döndürür (menü "Konuşma dili", hap, `/dil`). Arayüze dokunmaz.
async function toggleLanguage() {
  const D = window.YukiDil;
  if (!D) return;
  // Döngüsel: tr → ja → en → tr. Liste boşsa tek dil varmış gibi davranıp
  // kullanıcıyı yanıltmaktansa sessiz kalmak dürüst.
  let secenekler = D.konusmaSecenekleri();
  if (secenekler.length < 2) {
    await initLanguageSelector();
    secenekler = D.konusmaSecenekleri();
    if (secenekler.length < 2) return;
  }
  const i = secenekler.findIndex((o) => o.anahtar === D.konusma());
  const sonraki = secenekler[(i + 1) % secenekler.length].anahtar;
  try {
    const d = await D.konusmaAyarla(sonraki);   // TEK KAPI: backend + ayna
    if (d && d.ok) {
      // Onay cümlesi backend'den (dil kaydından) gelir — burada sabit yazılıydı
      // ve yalnız iki dal taşıyordu.
      addMessage('yuki', d.mesaj || D.t('dil.bilinmeyen'));
    } else {
      addMessage('yuki', D.t('dil.degistirilemedi', { sebep: (d && d.error) || '?' }));
    }
  } catch (e) {
    addMessage('yuki', D.t('dil.apiHatasi', { mesaj: e.message }));
  }
}

// ARAYÜZ dilini döndürür (menü "Arayüz dili"): yalnız TR ↔ EN — Japonca arayüz yok.
// Konuşma dili ayrıca seçilmemişse (arayüzle aynıysa) backend onu da taşır.
async function toggleArayuzDili() {
  const D = window.YukiDil;
  if (!D) return;
  const secenekler = D.secenekler();
  if (secenekler.length < 2) return;
  const i = secenekler.findIndex((o) => o.anahtar === D.al());
  const sonraki = secenekler[(i + 1) % secenekler.length].anahtar;
  try {
    const d = await D.ayarla(sonraki);   // TEK KAPI: DOM + önbellek + backend
    if (!d || d.ok === false) addMessage('yuki', D.t('dil.degistirilemedi', { sebep: (d && d.error) || '?' }));
  } catch (e) {
    addMessage('yuki', D.t('dil.apiHatasi', { mesaj: e.message }));
  }
}

// ── Input More (mobil ⋯ butonu) ─────────────────────────────────────

// ── ⋯ menüsü (2026-08-03) ───────────────────────────────────────────
// Eskiden yalnız mobilde açılan bir düğme kümesiydi ve dışarı tıklayınca
// kapanmıyordu; masaüstünde de kullanılınca bu "açık kalan panel" sorununa
// dönüşüyordu. Artık dışarı tıklama + Esc kapatıyor ve düğme kendi durumunu
// `aria-expanded` ile bildiriyor (ekran okuyucu ve CSS ikisi de okuyor).
function inputMoreKapat() {
  const sec = document.getElementById('input-secondary-btns');
  const btn = document.getElementById('input-more-btn');
  if (sec) sec.classList.remove('acik');
  if (btn) btn.setAttribute('aria-expanded', 'false');
}

function toggleInputMore(ev) {
  if (ev) ev.stopPropagation();           // aşağıdaki belge dinleyicisi hemen kapatmasın
  const sec = document.getElementById('input-secondary-btns');
  const btn = document.getElementById('input-more-btn');
  if (!sec) return;
  if (!sec.classList.contains('acik')) _girisYayiDiz(sec);
  const acik = sec.classList.toggle('acik');
  if (btn) btn.setAttribute('aria-expanded', acik ? 'true' : 'false');
}

/* Araç yayı (11-14, kişisel core.js _girisYayiDiz'in karşılığı): görünür araçları hapın üstünde
   yay hâlinde dizer — uçlar aşağıda, orta yukarıda. Telefonda CSS ızgarası ezer (css/sohbet-kisisel.css).
   Gizli öğe (kademe kapısı `hidden`, model/dil vekilleri) sayılmaz. */
function _girisYayiDiz(sec) {
  const dugumler = [...sec.querySelectorAll(':scope > .more-item')].filter(b => !b.hidden && getComputedStyle(b).display !== 'none');
  const n = dugumler.length;
  dugumler.forEach((b, i) => {
    const t = n > 1 ? i / (n - 1) : 0.5;
    b.style.setProperty('--x', (4 + t * 92).toFixed(2) + '%');
    b.style.setProperty('--y', (8 + 62 * Math.pow(2 * t - 1, 2)).toFixed(1) + 'px');
    b.style.setProperty('--i', String(Math.abs(i - (n - 1) / 2) | 0));
  });
}

document.addEventListener('click', (e) => {
  const sec = document.getElementById('input-secondary-btns');
  if (!sec || !sec.classList.contains('acik')) return;
  if (sec.contains(e.target)) {
    // Menü öğesine tıklandı → eylemi çalıştıktan sonra menüyü kapat.
    // Kapatmayı ertelemiyoruz çünkü eylemler kendi panellerini açabiliyor;
    // menü açık kalırsa onların üstünü örtüyordu.
    if (e.target.closest('.more-item')) inputMoreKapat();
    return;
  }
  if (e.target.closest('#input-more-btn')) return;   // toggle kendi işini yapar
  inputMoreKapat();
});

document.addEventListener('keydown', (e) => {
  if (e.key === 'Escape') inputMoreKapat();
});

/// ── Map search bar: konumlandırma artık css/map-controls.css'te (redesign 2026-07) ──

// ── ε: Service Worker kayıt ─────────────────────────────────────────
if ('serviceWorker' in navigator) {
  window.addEventListener('load', () => {
    navigator.serviceWorker.register('/sw.js?v=55', { scope: '/' })
      .then((reg) => {
        console.log('[SW] Kayıtlı, scope:', reg.scope);
        reg.addEventListener('updatefound', () => {
          const nw = reg.installing;
          if (!nw) return;
          // 🔴 2026-08-13 — İLK KURULUMDA YENİLEME YOK.
          // `controller` yoksa bu sayfayı yöneten bir service worker HİÇ yoktu, yani
          // sayfa zaten ağdan/pakettten taze geldi: yenilemenin tazeleyeceği bayat
          // içerik ortada yok. Buna rağmen eski kod her `activated` olayında
          // yeniliyordu → ürünün İLK açılışında (ve her temiz kurulumda) ekran
          // kendiliğinden bir kez sıfırlanıyordu. geliştiricinin 08-13 saha raporu:
          // "bir anda tekrar Ctrl+R yapıyormuş gibi yeniden yükleniyor."
          // Güncelleme durumunda (controller VAR) yenileme korunur — orada sayfa
          // gerçekten eski önbellekten yüklenmiş olabilir ve tazelenmesi gerekir.
          const guncelleme = !!navigator.serviceWorker.controller;
          nw.addEventListener('statechange', () => {
            if (nw.state !== 'activated') return;
            if (!guncelleme) {
              console.log('[SW] İlk kurulum — yenileme gerekmiyor');
              return;
            }
            console.log('[SW] Güncellendi — sayfa yenileniyor');
            window.location.reload();
          });
        });
      })
      .catch((err) => console.warn('[SW] Kayıt hatası:', err));
  });
}

// ── Faz 12: Web Push Bildirimleri ───────────────────────────────────
(async function _initWebPush() {
  if (!('PushManager' in window) || !('serviceWorker' in navigator)) return;

  // Daha önce izin verilmişse sessizce abone ol
  if (Notification.permission === 'granted') {
    await _subscribeToPush(false);
  }
  // Mobil PWA — ilk açılışta bildirim iste
  else if (Notification.permission === 'default' && window.matchMedia('(max-width: 768px)').matches) {
    const perm = await Notification.requestPermission();
    if (perm === 'granted') await _subscribeToPush(true);
  }
})();

async function _subscribeToPush(isNew) {
  try {
    const reg = await navigator.serviceWorker.ready;
    let sub = await reg.pushManager.getSubscription();
    /* Tarayıcıda abonelik olsa bile sunucuya YENİDEN bildir (sunucu upsert eder). Eskiden
       `existing` varsa hemen dönülüyordu: sunucu aboneyi silmişse (push.py 410/404 temizliği)
       cihaz bir daha hiç kaydolmuyordu — tarayıcı "aboneyim", sunucu "0 abone" (09-27 ölçüldü,
       kişiselde a0d2dc4). `authFetch`: kilitli kurulumda açılıştaki istek token'ı bekler,
       düz fetch'le sessizce 401 alıp düşmez. */
    if (!sub) {
      const resp = await authFetch('/api/push/vapid-public-key');
      if (!resp.ok) return;
      const { publicKey } = await resp.json();
      if (!publicKey) return;
      sub = await reg.pushManager.subscribe({
        userVisibleOnly: true,
        applicationServerKey: _urlBase64ToUint8Array(publicKey),
      });
    }
    const r = await authFetch('/api/push/subscribe', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(sub.toJSON()),
    });
    if (!r.ok) { console.warn('[Push] Sunucu aboneliği kaydetmedi: HTTP ' + r.status); return false; }
    console.log('[Push] Bildirim aboneliği ' + (isNew ? 'oluşturuldu.' : 'sunucuya bildirildi.'));
    return true;
  } catch (e) {
    console.warn('[Push] Abonelik hatası:', e);
    return false;
  }
}

/* BİLDİRİM odasının "BU CİHAZI BAĞLA" düğmesi — izin KULLANICI HAREKETİYLE istenir
   (masaüstünde açılış izni istemiyoruz). `neden`: desteklenmiyor · reddedildi · sunucu. */
window.yukiBildirimBagla = async function () {
  if (!('PushManager' in window) || !('serviceWorker' in navigator) || !window.Notification) {
    return { ok: false, neden: 'desteklenmiyor' };
  }
  let izin = Notification.permission;
  if (izin === 'default') izin = await Notification.requestPermission();
  if (izin !== 'granted') return { ok: false, neden: 'reddedildi' };
  return (await _subscribeToPush(true)) ? { ok: true } : { ok: false, neden: 'sunucu' };
};
/* Bu pencere Yuki'nin sesini/mesajını alıyor mu (BİLDİRİM odasının EKRAN ışığı). */
window.yukiEkranBagli = function () {
  return !!(typeof socket !== 'undefined' && socket && socket.readyState === WebSocket.OPEN);
};

function _urlBase64ToUint8Array(base64String) {
  const padding = '='.repeat((4 - base64String.length % 4) % 4);
  const b64 = (base64String + padding).replace(/-/g, '+').replace(/_/g, '/');
  const raw = atob(b64);
  return Uint8Array.from([...raw].map((c) => c.charCodeAt(0)));
}

// ── ε: PWA Install Prompt (Android Chrome "Ana ekrana ekle") ────────
let _installPrompt = null;

window.addEventListener('beforeinstallprompt', (e) => {
  e.preventDefault();
  _installPrompt = e;
  _showInstallBanner();
});

function _showInstallBanner() {
  if (document.getElementById('pwa-install-banner')) return;
  const banner = document.createElement('div');
  banner.id = 'pwa-install-banner';
  banner.style.cssText = [
    'position:fixed', 'bottom:80px', 'left:50%', 'transform:translateX(-50%)',
    'background:rgba(0,212,255,0.92)', 'color:#000', 'padding:10px 18px',
    'border-radius:10px', 'font-size:13px', 'font-weight:600', 'z-index:1000',
    'display:flex', 'align-items:center', 'gap:10px', 'box-shadow:0 4px 16px rgba(0,0,0,0.3)',
    'cursor:pointer', 'animation:ambientSlideUp 0.35s ease-out',
  ].join(';');
  /* DOM API — metin sözlükten geliyor; `innerHTML` birleştirmesi bir çeviride
     `&`/`<` geçtiği an işaretleme olarak yorumlardı. */
  const yazi = document.createElement('span');
  yazi.textContent = _t('pwa.ana-ekrana-ekle');
  const kapat = document.createElement('button');
  kapat.style.cssText = 'background:none;border:none;color:#000;font-size:18px;cursor:pointer;opacity:.6';
  kapat.textContent = '×';
  kapat.setAttribute('aria-label', _t('amb.kapat'));
  banner.append(yazi, kapat);
  banner.querySelector('span').onclick = async () => {
    banner.remove();
    if (!_installPrompt) return;
    _installPrompt.prompt();
    const { outcome } = await _installPrompt.userChoice;
    console.log('[PWA] Install outcome:', outcome);
    _installPrompt = null;
  };
  banner.querySelector('button').onclick = (e) => { e.stopPropagation(); banner.remove(); };
  document.body.appendChild(banner);
  setTimeout(() => banner.remove(), 15000);
}

window.addEventListener('appinstalled', () => {
  console.log('[PWA] Yüklendi.');
  document.getElementById('pwa-install-banner')?.remove();
});

// ── Ambient Watch Panel — Canlı Ekran İzleme (WebSocket) ────────────
// 2026-07-05 yenilendi (widget js/ambient.js ile aynı tasarım):
// - Yapılandırılmış AI analiz kartı — metinler textContent ile basılır (innerHTML
//   XSS riski kaldırıldı; LLM çıktısı doğrudan DOM'a HTML olarak gidiyordu)
// - Tarama aralığı seçici 10s/20s/60s/KAPALI (localStorage kalıcı) + TARA
// - ⏸ DONDUR: WS yayını + otomatik Vision taraması durur
// - Artan backoff'lu reconnect (2s→4s→8s→15s, bağlanınca sıfırlanır)
let _ambientDescTimer  = null;
let _ambientDescBusy   = false;
let _ambientPaused     = false;
let _ambientIntervalMs = parseInt(localStorage.getItem('yuki_amb_interval_v1') || '20000', 10);
let _screenWs          = null;
let _screenBlobUrl     = null;
let _screenReconnTimer = null;
let _screenReconnTry   = 0;
let _screenOutput      = null;  // null = tüm ekran, string = output adı (ör. "DP-1")
let _ambSonDurum       = 'connecting';  // rozetin son DURUMU (metni değil) — dil değişiminde gerekli
/* Backend'in "pencere adını okuyamadım" nöbetçisi. ÇEVRİLMEZ — bkz.
   `_renderAmbientDesc`. Adı sabite alındı ki grep'lenebilir olsun. */
const _AMB_BILINMEYEN = 'bilinmiyor';

/* 🔴 Değer sabit, ETİKET anahtar. Eskiden `'KAPALI'` doğrudan buradaydı ve
   modül yüklenirken donuyordu (bu dalganın yedinci modül-düzeyi sabiti).
   `10s`/`20s`/`60s` birim kısaltmaları da çevrilir: İngilizce'de de "10s" ama
   bunu VARSAYMAK yerine sözlüğe koyuyoruz — dördüncü dilde doğru olmayabilir. */
const _AMB_INTERVALS = [[10000, 'amb.aralik-10s'], [20000, 'amb.aralik-20s'],
                        [60000, 'amb.aralik-60s'], [0, 'amb.aralik-kapali']];

function _ambIsOpen() {
  return !!document.getElementById('ambient-panel')?.classList.contains('open');
}

function toggleAmbientPanel() {
  const panel = document.getElementById('ambient-panel');
  const btn   = document.getElementById('ambient-watch-btn');
  if (!panel) return;
  const open = panel.classList.toggle('open');
  btn?.classList.toggle('active', open);
  document.body.classList.toggle('ambient-open', open);   // arka plan karartması
  if (open) {
    _ambientPaused = false;
    _screenReconnTry = 0;
    _buildAmbientSkeleton();
    _loadMonitorButtons();
    _screenWsConnect();
    _ambientRefreshDesc();
    _scheduleAmbientScan();
  } else {
    _screenWsDisconnect();
    clearInterval(_ambientDescTimer); _ambientDescTimer = null;
  }
}

function toggleApFullscreen() {
  let overlay = document.getElementById('ap-fullscreen-overlay');
  if (!overlay) {
    overlay = document.createElement('div');
    overlay.id = 'ap-fullscreen-overlay';
    const img = document.createElement('img');
    img.id = 'ap-fullscreen-img';
    overlay.appendChild(img);
    overlay.onclick = () => overlay.classList.remove('open');
    document.body.appendChild(overlay);
  }
  const src = document.getElementById('ap-img')?.src;
  if (!src || src === location.href) return;
  document.getElementById('ap-fullscreen-img').src = src;
  overlay.classList.add('open');
}

function _buildAmbientSkeleton() {
  const panel = document.getElementById('ambient-panel');
  if (!panel) return;
  /* 🔑 Kabuk `data-i18n` ÇAPALARIYLA doğuyor, `_t()` ile değil.
     Sebep: bu panel dil değişiminde YENİDEN KURULAMAZ — `#ap-ai-text` canlı
     LLM analizini, `#ap-img` canlı kareyi, `#ap-help-sug` öneriyi taşıyor.
     Yeniden kurmak o üçünü silerdi, yani çeviri VERİYİ silerdi (`dil.js`'in
     `_sahibiBizMiyiz` gerekçesinin aynısı, bir kat yukarıda). Çapa koyunca
     `YukiDil.ciz(panel)` yalnız ETİKETLERİ tazeliyor, içeriğe dokunmuyor. */
  panel.innerHTML = `
    <div class="ap-header">
      <div class="ap-header-left">
        <span class="ap-title" data-i18n="amb.baslik"></span>
        <span class="ap-live-badge" id="ap-live" data-i18n-yok></span>
      </div>
      <div class="ap-header-right">
        <button class="ap-ctl-btn" id="ap-pause" data-i18n-title="amb.dondur-surdur" onclick="_ambientTogglePause()">⏸</button>
        <button class="ap-close-btn" data-i18n-aria-label="amb.kapat" onclick="toggleAmbientPanel()">✕</button>
      </div>
    </div>
    <div class="ap-monitor-bar" id="ap-monitor-bar">
      <span class="ap-mon-label" data-i18n="amb.ekran-etiketi"></span>
      <button class="ap-mon-btn active" data-output="" data-i18n="amb.tumu" onclick="_selectMonitor(this, '')"></button>
    </div>
    <div class="ap-screen" id="ap-screen" onclick="toggleApFullscreen()" data-i18n-title="amb.tam-ekran-icin-tikla">
      <img id="ap-img" src="" data-i18n-alt="amb.ekran-yukleniyor" alt="">
      <span class="ap-ts" id="ap-ts"></span>
      <div class="ap-overlay" id="ap-overlay" style="display:none"></div>
      <div class="ap-corner tl"></div><div class="ap-corner tr"></div>
      <div class="ap-corner bl"></div><div class="ap-corner br"></div>
    </div>
    <div class="ap-ai" id="ap-ai">
      <div class="ap-ai-head">
        <span class="ap-ai-label" data-i18n="amb.ai-analiz"></span>
        <span class="ap-ai-time" id="ap-ai-time"></span>
        <span style="flex:1"></span>
        <span class="ap-int-chips" id="ap-int-chips"></span>
        <button class="ap-ctl-btn" id="ap-scan-now" data-i18n-title="amb.simdi-analiz-et" data-i18n="amb.tara" onclick="_ambientRefreshDesc()"></button>
      </div>
      <div class="ap-description" id="ap-ai-text" data-i18n-yok>—</div>
      <div class="ap-suggestion" id="ap-ai-help" hidden>
        <span class="ap-help-badge" data-i18n="amb.yardim-rozeti"></span>
        <span class="ap-help-sug" id="ap-help-sug" data-i18n-yok></span>
        <button class="ap-help-ask" data-i18n="amb.yuki-ye-sor" onclick="_ambientAskYuki()"></button>
      </div>
    </div>`;
  _ambEtiketleriTazele();
  _renderAmbIntervalChips();
}

/* Panelin YALNIZ etiketlerini tazeler — canlı kare, analiz metni ve öneri
   yerinde kalır. Dil değişiminde `_buildAmbientSkeleton` çağrılsaydı üçü de
   silinirdi. `data-i18n-yok` taşıyan üç düğüme çizici zaten dokunmuyor. */
function _ambEtiketleriTazele() {
  const panel = document.getElementById('ambient-panel');
  if (!panel) return;
  if (window.YukiDil && window.YukiDil.ciz) window.YukiDil.ciz(panel);
  _apBadge(_ambSonDurum);                 // rozet çapasızdır (durum taşır)
  _renderAmbIntervalChips();              // çipler JS'ten doğuyor
  const ilk = panel.querySelector('.ap-mon-btn[data-output=""]');
  if (ilk) ilk.textContent = _t('amb.tumu');
}

function _apBadge(state) {
  const badge = document.getElementById('ap-live');
  if (!badge) return;
  const map = {
    live:      [_t('amb.rozet-canli'), 'ap-live-badge'],
    reconnect: [_t('amb.rozet-yeniden', { deneme: _screenReconnTry }), 'ap-live-badge paused'],
    error:     [_t('amb.rozet-hata'), 'ap-live-badge paused'],
    paused:    [_t('amb.rozet-dondu'), 'ap-live-badge paused'],
    connecting:[_t('amb.rozet-baglaniyor'), 'ap-live-badge paused'],
  };
  const [txt, cls] = map[state] || map.connecting;
  /* Son durum SAKLANIR: dil değiştiğinde rozeti yeniden çizmek için hangi
     durumda olduğumuzu bilmek gerekiyor. Saklanmasaydı tazeleyici rozeti
     `connecting`e düşürür ve CANLI yayını "bağlanıyor" gösterirdi. */
  _ambSonDurum = map[state] ? state : 'connecting';
  badge.textContent = txt;
  badge.className = cls;
}

function _renderAmbIntervalChips() {
  const box = document.getElementById('ap-int-chips');
  if (!box) return;
  box.innerHTML = '';
  _AMB_INTERVALS.forEach(([ms, anahtar]) => {
    const label = _t(anahtar);
    const b = document.createElement('button');
    b.className = 'ap-int-chip' + (ms === _ambientIntervalMs ? ' active' : '');
    b.textContent = label;
    /* 🔴 KİMLİK METİNDE DEĞİL: aktif çip `ms === _ambientIntervalMs` ile
       bulunuyor, etiketle değil — `planner.html`'de `budgetSetCatFilter`
       tam bu yüzden ölmüştü (çipi metninden arıyordu). Burada zaten
       sayıyla eşleşiyor; `data-ms` kimliği ölçüm için açığa çıkarıldı. */
    b.dataset.ms = String(ms);
    b.title = ms ? _t('amb.aralik-title', { aralik: label }) : _t('amb.aralik-kapali-title');
    b.onclick = () => {
      _ambientIntervalMs = ms;
      localStorage.setItem('yuki_amb_interval_v1', String(ms));
      _renderAmbIntervalChips();
      _scheduleAmbientScan();
    };
    box.appendChild(b);
  });
}

function _scheduleAmbientScan() {
  clearInterval(_ambientDescTimer);
  _ambientDescTimer = null;
  if (_ambIsOpen() && !_ambientPaused && _ambientIntervalMs > 0) {
    _ambientDescTimer = setInterval(_ambientRefreshDesc, _ambientIntervalMs);
  }
}

function _ambientTogglePause() {
  if (!_ambIsOpen()) return;
  _ambientPaused = !_ambientPaused;
  const btn = document.getElementById('ap-pause');
  if (btn) { btn.textContent = _ambientPaused ? '▶' : '⏸'; btn.classList.toggle('active', _ambientPaused); }
  if (_ambientPaused) {
    _screenWsDisconnect();
    clearInterval(_ambientDescTimer); _ambientDescTimer = null;
    _apBadge('paused');
  } else {
    _screenReconnTry = 0;
    _screenWsConnect();
    _scheduleAmbientScan();
  }
}

async function _loadMonitorButtons() {
  try {
    const res  = await authFetch(`${BASE_URL}/api/screen/outputs`);
    const data = await res.json();
    const bar  = document.getElementById('ap-monitor-bar');
    if (!bar || !data.outputs?.length) return;
    data.outputs.forEach((mon, i) => {
      const btn = document.createElement('button');
      btn.className = 'ap-mon-btn' + (mon.name === (_screenOutput || '') ? ' active' : '');
      btn.dataset.output = mon.name;
      btn.textContent = _t('amb.monitor-etiket', { sira: i + 1, ad: mon.name });
      btn.onclick = () => _selectMonitor(btn, mon.name);
      bar.appendChild(btn);
    });
  } catch (e) {
    console.warn('[screen] Monitor listesi alınamadı:', e);
  }
}

function _selectMonitor(btn, outputName) {
  document.querySelectorAll('.ap-mon-btn').forEach(b => b.classList.remove('active'));
  btn.classList.add('active');
  if (_screenOutput === (outputName || null)) return;
  _screenOutput = outputName || null;
  _screenReconnTry = 0;
  _screenWsDisconnect();
  _screenWsConnect();
}

function _screenWsConnect() {
  if (_screenReconnTimer) { clearTimeout(_screenReconnTimer); _screenReconnTimer = null; }
  if (_ambientPaused || !_ambIsOpen()) return;
  const params = new URLSearchParams();
  if (_screenOutput) params.set('output', _screenOutput);
  if (_authToken)    params.set('token', _authToken);
  const qs = params.toString() ? `?${params.toString()}` : '';
  _screenWs = new WebSocket(`${_WS_BASE}/ws/screen${qs}`);
  _screenWs.binaryType = 'arraybuffer';

  _screenWs.onopen = () => { _screenReconnTry = 0; _apBadge('live'); };

  _screenWs.onmessage = (e) => {
    if (_ambientPaused) return;
    const blob = new Blob([e.data], { type: 'image/jpeg' });
    const url  = URL.createObjectURL(blob);
    const img  = document.getElementById('ap-img');
    const ts   = document.getElementById('ap-ts');
    if (img) img.src = url;
    if (ts)  ts.textContent = new Date().toLocaleTimeString(_yerel());
    if (_screenBlobUrl) URL.revokeObjectURL(_screenBlobUrl);
    _screenBlobUrl = url;
  };

  _screenWs.onerror = () => { _apBadge('error'); };

  _screenWs.onclose = () => {
    _screenWs = null;
    if (_ambIsOpen() && !_ambientPaused) {
      _screenReconnTry += 1;
      _apBadge('reconnect');
      const wait = Math.min(2000 * Math.pow(2, _screenReconnTry - 1), 15000);
      _screenReconnTimer = setTimeout(_screenWsConnect, wait);
    }
  };
}

function _screenWsDisconnect() {
  if (_screenReconnTimer) { clearTimeout(_screenReconnTimer); _screenReconnTimer = null; }
  if (_screenWs) { _screenWs.onclose = null; _screenWs.close(); _screenWs = null; }
  if (_screenBlobUrl) { URL.revokeObjectURL(_screenBlobUrl); _screenBlobUrl = null; }
}

async function _ambientRefreshDesc() {
  if (_ambientDescBusy || !_ambIsOpen()) return;
  _ambientDescBusy = true;
  const scanBtn = document.getElementById('ap-scan-now');
  if (scanBtn) { scanBtn.disabled = true; scanBtn.textContent = '…'; }   // '…' dilden bağımsız
  try {
    const r = await authFetch(`${BASE_URL}/api/ambient/scan`, { method: 'POST' });
    if (r.ok) _renderAmbientDesc(await r.json());
    else if (r.status === 403) {
      const t = document.getElementById('ap-ai-text');
      if (t) t.textContent = _t('amb.kapali-env');
    }
  } catch (_) {} finally {
    _ambientDescBusy = false;
    const b = document.getElementById('ap-scan-now');
    if (b) { b.disabled = false; b.textContent = _t('amb.tara'); }
  }
}

function _renderAmbientDesc(la) {
  const textEl  = document.getElementById('ap-ai-text');
  const timeEl  = document.getElementById('ap-ai-time');
  const helpEl  = document.getElementById('ap-ai-help');
  const sugEl   = document.getElementById('ap-help-sug');
  const overlay = document.getElementById('ap-overlay');

  const desc = (la.description || '').trim();
  const sug  = (la.needs_help && la.suggestion) ? String(la.suggestion).trim() : '';
  /* 🔴 `'bilinmiyor'` bir SÖZLEŞME NÖBETÇİSİ, ekrana basılan metin değil:
     backend (`services/ambient.py::_get_active_window`,
     `services/screen_context.py::active_window`) pencere adını okuyamadığında
     tam bu dizgeyi döndürür ve biz onu GİZLİYORUZ. Türkçe göründüğü için
     çeviri turunda "kaçak" sanılıp çevrilmesi, süzgecin sessizce ölmesi
     demekti — ekranda "bilinmiyor" yazan bir kaplama belirirdi.
     ⚠️ İki taraf `test_ambient_bilinmeyen_nobetcisi_esitligi` ile bağlandı:
     backend'deki dizge değişirse test kırmızı yanar. */
  const win  = (la.active_window && la.active_window !== _AMB_BILINMEYEN) ? la.active_window : null;

  // Hepsi textContent — LLM çıktısı HTML olarak ASLA basılmaz (XSS)
  if (overlay) {
    overlay.textContent = win || '';
    overlay.style.display = win ? 'block' : 'none';
  }
  if (textEl) textEl.textContent = desc || '—';
  if (timeEl) timeEl.textContent = new Date().toLocaleTimeString(_yerel(), { hour: '2-digit', minute: '2-digit' });
  if (helpEl) helpEl.hidden = !sug;
  if (sugEl)  sugEl.textContent = sug;
}

function _ambientAskYuki() {
  const sug = document.getElementById('ap-help-sug')?.textContent.trim();
  if (!sug) return;
  const input = document.getElementById('msg-input');
  if (!input) return;
  input.value = _t('amb.yuki-ye-sor-doldur', { oneri: sug });
  sendMessage();
}
