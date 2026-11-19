/* Açılış kilidi — parola ve/veya yüzle giriş ekranı.
 *
 * Backend: `app/api/lock_api.py` + `app/services/app_lock.py`.
 *
 * 🔑 Neden `#auth-screen` YENİDEN KULLANILIYOR, yeni bir ekran açılmıyor:
 * uygulamada zaten bir "parola sor" perdesi var (AUTH_TOKEN / tünel kurulumu).
 * İkinci bir kilit ekranı, aynı soruya iki ayrı yerde cevap üretirdi — bu
 * depoda tekrarlayan hata sınıfı (bkz. `electron/surum.js` yorumu). Tek perde,
 * iki mod: `_kilitModu` true ise `/api/lock/unlock`, değilse eski AUTH_TOKEN yolu.
 *
 * ## Yüzle giriş — istemci tarafı BURADA yazıldı
 * Backend'de 9 rota 'de eklenmişti ama onları çağıran bir istemci akışı
 * hiç yoktu; yüzle giriş kâğıt üzerinde vardı, kullanıcı için yoktu.
 *
 * Akış: `/liveness/challenge` → kamera aç → N saniye kare topla → `/verify`.
 * Meydan okuma tek kullanımlık ve sürelidir; kareler **canlılık** için gerekir
 * (göz kırpma geçişi), tek kare göndermek yetmez ve YETMEMELİ.
 */
(function () {
  'use strict';

  var BASE = (typeof BASE_URL !== 'undefined' && BASE_URL) ? BASE_URL : '';

  function _alt(anahtar, degerler) {
    return (window.YukiDil && window.YukiDil.t) ? window.YukiDil.t(anahtar, degerler) : String(anahtar);
  }

  var _kilitModu = false;
  var _durum = null;
  var _akis = null;          // MediaStream — yalnız yüz denemesi sırasında açık
  var _video = null;
  var _mesgul = false;

  function el(id) { return document.getElementById(id); }

  function dugmeMetni(btn, metin) {
    if (!btn) return;
    var etiket = btn.querySelector('.auth-btn-label');
    if (etiket) etiket.textContent = metin;
    else btn.textContent = metin;
  }

  /* Bekleme görseli sunum katmanıdır; auth akışının kararlarına dokunmaz.
     Çalışma durumu mor değil nötr token'la gösterilir. */
  function mesgulGorunum(acik, mod) {
    var kutu = document.querySelector('#auth-screen .auth-box');
    if (!kutu) return;
    if (acik) kutu.setAttribute('aria-busy', 'true');
    else kutu.removeAttribute('aria-busy');
    kutu.dataset.authMode = acik && mod === 'face' ? 'face' : 'password';

    var parolaBtn = kutu.querySelector('.auth-actions .auth-btn:not(#auth-yuz-btn)');
    if (parolaBtn) parolaBtn.disabled = !!acik;
    var yuzBtn = el('auth-yuz-btn');
    if (yuzBtn) {
      yuzBtn.disabled = acik || yuzBtn.dataset.guardLocked === 'true';
    }
  }

  /* Hata satırı iki kaynaktan yazılır: i18n anahtarı (`hata`) ya da sunucunun
     hazır cümlesi (`hataHam`, kalan deneme/kilit süresi orada hesaplanır).
     Son yazılan saklanır: dil değişince anahtarlı olan yeni dilde yeniden yazılır. */
  var _sonHata = null;       // {anahtar, degerler} | {ham} | null
  var _sonHataMetin = '';    // ekrana bizim yazdığımız son metin

  function _hataYaz(k) {
    _sonHata = k;
    var e = el('auth-error');
    if (!e) return;
    var girdi = el('auth-input');
    if (!k) {
      e.textContent = '';
      _sonHataMetin = '';
      if (girdi) girdi.removeAttribute('aria-invalid');
      return;
    }
    e.textContent = k.ham != null ? k.ham : _alt(k.anahtar, k.degerler);
    _sonHataMetin = e.textContent;
    /* Yüz yolunun hatası parola alanını GEÇERSİZ işaretlemez: kırmızı çerçeve
       (style.css) bu özniteliğe bağlı, göz yanlış alana gidiyordu. */
    if (girdi) {
      if (k.yuz) girdi.removeAttribute('aria-invalid');
      else girdi.setAttribute('aria-invalid', 'true');
    }
  }

  function hata(anahtar, degerler) {
    _hataYaz(anahtar ? { anahtar: anahtar, degerler: degerler } : null);
  }

  function hataHam(metin) {
    _hataYaz(metin ? { ham: String(metin) } : null);
  }

  /* Sunucu cümlesi varsa onu, yoksa anahtarın metnini yaz. */
  function hataSunucuYaDa(detay, anahtar) {
    if (detay) hataHam(detay); else hata(anahtar);
  }

  /* Yüz girişinin hatası — aynı satıra yazılır ama parola alanını işaretlemez. */
  function yuzHata(anahtar, detay) {
    _hataYaz(detay ? { ham: String(detay), yuz: true } : { anahtar: anahtar, yuz: true });
  }

  function tokenYaz(token) {
    try { sessionStorage.setItem('aliceToken', token); } catch (_) {}
    if (typeof window.setAuthToken === 'function') window.setAuthToken(token);
  }

  function tokenSil() {
    try { sessionStorage.removeItem('aliceToken'); } catch (_) {}
  }

  /* ── Durum ──────────────────────────────────────────────────────────── */

  async function durumOku() {
    try {
      var r = await fetch(BASE + '/api/lock/status');
      if (!r.ok) return null;
      return await r.json();
    } catch (_) { return null; }
  }

  /** Kilit kurulu mu? Kuruluysa perdeyi kilit moduna geçirir.
   *
   * 🔴 **TEK OKUMA YETMEZ — 2026-09-10'da canlı ölçüldü.** Bu fonksiyon
   * `/api/lock/status`'u bir kez okuyup bir daha sormuyordu. O tek okuma
   * düşerse (backend henüz cevap veremiyor, 429, anlık ağ hatası) zincir
   * şöyle gidiyordu: `gerekliMi()` **false** → `core.js` `_showAuthScreen()`'e
   * düşüyor → ekranda yalnız parola alanı kalıyor, **"Yüzümle gir" düğmesi
   * hiç çizilmiyor** → dahası `_kilitModu` false olduğu için girilen parola
   * `/api/lock/unlock`'a değil **AUTH_TOKEN** yoluna gidiyor ve DOĞRU parola
   * *"Parola yanlış."* ile reddediliyor. Kullanıcı kendi uygulamasından
   * tamamen kilitleniyordu, üstelik ekranda hiçbir sebep yazmadan.
   *
   * Ölçüm (Playwright, ilk `/status` isteği düşürülerek): `btnVar=false` ·
   * `kilitModu=false` · doğru parola → *"Parola yanlış."*
   *
   * ⚠️ Fail-OPEN kaldırılmadı, **geri alınabilir** yapıldı: okuma başarısızsa
   * yine perdeyi kilitlemiyoruz (backend hiç cevap vermiyorsa kullanıcıyı
   * açamayacağı bir ekranda tutmak daha kötü), ama kısa denemelerle tekrar
   * soruyor ve cevap gelince ekranı doğru moda **yükseltiyoruz**.
   */
  var _DENEME = 3, _DENEME_ARA_MS = 400;

  async function durumOkuIsrarla() {
    for (var i = 0; i < _DENEME; i++) {
      var d = await durumOku();
      if (d) return d;
      if (i < _DENEME - 1) await new Promise(function (c) { setTimeout(c, _DENEME_ARA_MS); });
    }
    return null;
  }

  async function gerekliMi() {
    _durum = await durumOkuIsrarla();
    if (!_durum || !_durum.kurulu) {
      /* Okunamadıysa cevap "hayır" değil "bilmiyorum" — nöbet devralsın.
         Okunduysa ve `kurulu:false` ise cevap kesindir, nöbete gerek yok. */
      if (!_durum) nobetiBaslat();
      return false;
    }
    _kilitModu = true;
    return true;
  }

  /* ── Nöbet: durum geç gelirse ekranı yükselt ─────────────────────────────
   * `gerekliMi()` "bilmiyorum" ile döndüğünde perde AUTH_TOKEN modunda açılır.
   * Nöbet arka planda sormaya devam eder; `kurulu:true` gelirse perdeyi kilit
   * moduna çevirir ve yüz düğmesini çizer. Süreli: sonsuz yoklama, cevabı
   * hiç gelmeyecek bir backend'de boşuna istek üretirdi. */
  var _nobet = null;
  var _NOBET_ARA_MS = 1500, _NOBET_TUR = 12;   // ~18 sn

  function nobetiBaslat() {
    if (_nobet || _kilitModu) return;
    var tur = 0;
    _nobet = setInterval(async function () {
      if (_kilitModu || ++tur > _NOBET_TUR) { nobetiDurdur(); return; }
      var d = await durumOku();
      if (!d) return;
      _durum = d;
      if (!d.kurulu) { nobetiDurdur(); return; }   // kesin cevap: kilit yok
      _kilitModu = true;
      nobetiDurdur();
      var perde = el('auth-screen');
      if (perde && !perde.classList.contains('hidden')) ekraniGoster();
    }, _NOBET_ARA_MS);
  }

  function nobetiDurdur() {
    if (_nobet) { clearInterval(_nobet); _nobet = null; }
  }

  /* ── Ekran ──────────────────────────────────────────────────────────── */

  function ekraniGoster() {
    var perde = el('auth-screen');
    if (!perde) return;
    perde.classList.remove('hidden');

    var alt = perde.querySelector('.auth-sub');
    if (alt) {
      alt.textContent = _alt(_durum && _durum.yuzle_girilebilir
        ? 'kilit-ekran.yontem-sec'
        : 'kilit-ekran.acilis-parolasi');
    }

    mesgulGorunum(false, 'password');
    girisDugmesiniDevral();
    yuzDugmesiniKur();
    setTimeout(function () { var i = el('auth-input'); if (i) i.focus(); }, 100);
  }

  function ekraniKapat() {
    var perde = el('auth-screen');
    if (perde) perde.classList.add('hidden');
    mesgulGorunum(false, 'password');
    kamerayiKapat();
    if (typeof window._hideAuthScreen === 'function') {
      try { window._hideAuthScreen(); } catch (_) {}
    }
  }

  /** Perdedeki asıl "Giriş" düğmesini kilit moduna devret.
   *
   * 🔴 **2026-09-10'da canlı ölçüldü — doğru parola REDDEDİLİYORDU.**
   * `index.html`'deki düğme `onclick="_authLogin()"` ile SABİT bağlı ve
   * `_authLogin` AUTH_TOKEN yoludur (`/api/ping` + Bearer). Kilit modunda
   * parola bir token değildir; `oturum_gecerli()` onu tanımaz, 401 döner ve
   * ekranda *"Parola yanlış."* yazar. Enter tuşu bu depoda ayrıca ele alınmış
   * (dosya sonundaki capture dinleyicisi) olduğu için **Enter çalışıyor,
   * düğme çalışmıyordu** — kullanıcının parolasını unuttuğunu sanacağı bir
   * arıza. Ölçüm: düğme → *"Parola yanlış."* · Enter → perde kapandı.
   *
   * 📏 Ders: bir ekranın iki girişi (tuş ve düğme) varsa ikisi de ölçülmeli;
   * biri ele alınıp öbürü unutulunca arıza "bazen çalışıyor" diye görünür.
   *
   * `onclick` **atanarak** devralınır (`addEventListener` değil): atama satır
   * içi işleyiciyi siler ve idempotenttir — `ekraniGoster()` nöbet
   * yükseltmesinde ikinci kez çalışabilir, dinleyici birikmemeli.
   */
  function girisDugmesiniDevral() {
    var kutu = document.querySelector('#auth-screen .auth-box');
    if (!kutu) return;
    var btn = kutu.querySelector('button.auth-btn:not(#auth-yuz-btn)');
    if (btn) btn.onclick = function () { parolaylaGir(); };
  }

  /** Yüz seçeneği yalnız GERÇEKTEN kullanılabilirse çizilir.
   *
   * ⚠️ "Yüz tanıma açık" yetmez: kütüphane inmemişse ya da kayıtlı yüz yoksa
   * düğme her basışta hata verirdi. `yuzle_girilebilir` ikisini birden ölçer.
   * Ayrıca yüz yolu deneme kilidiyle kapanmışsa düğme çizilir ama sebebi
   * söylenir — düğmeyi gizlemek "özellik yok" gibi okunurdu. */
  function yuzDugmesiniKur() {
    var kutu = document.querySelector('#auth-screen .auth-box');
    if (!kutu) return;
    var eski = el('auth-yuz-btn');
    if (eski) eski.remove();
    var eskiNot = el('auth-yuz-not');
    if (eskiNot) eskiNot.remove();

    if (!_durum || !_durum.yuzle_girilebilir) return;

    var kilitli = !!(_durum.guard && _durum.guard.face && _durum.guard.face.locked);
    var btn = document.createElement('button');
    btn.id = 'auth-yuz-btn';
    btn.className = 'auth-btn auth-btn-ikincil';
    btn.type = 'button';
    btn.innerHTML = '<svg aria-hidden="true" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round">'
      + '<path d="M9 4.5H7A2.5 2.5 0 0 0 4.5 7v2"></path>'
      + '<path d="M15 4.5h2A2.5 2.5 0 0 1 19.5 7v2"></path>'
      + '<path d="M9 19.5H7A2.5 2.5 0 0 1 4.5 17v-2"></path>'
      + '<path d="M15 19.5h2a2.5 2.5 0 0 0 2.5-2.5v-2"></path>'
      + '<circle cx="9" cy="10" r=".5" fill="currentColor" stroke="none"></circle>'
      + '<circle cx="15" cy="10" r=".5" fill="currentColor" stroke="none"></circle>'
      + '<path d="M9 15c.8.7 1.8 1 3 1s2.2-.3 3-1"></path>'
      + '</svg><span class="auth-btn-label"></span>';
    dugmeMetni(btn, _alt(kilitli ? 'kilit-ekran.yuz-gecici-kapali' : 'kilit-ekran.yuzumle-gir'));
    btn.dataset.guardLocked = kilitli ? 'true' : 'false';
    btn.disabled = kilitli;
    btn.addEventListener('click', yuzleGir);

    var eylemler = kutu.querySelector('.auth-actions');
    if (eylemler) eylemler.appendChild(btn); else kutu.appendChild(btn);

    var not = document.createElement('div');
    not.id = 'auth-yuz-not';
    not.className = 'auth-not';
    not.textContent = _alt('kilit-ekran.yuz-not');
    var ana = kutu.querySelector('.auth-main');
    var hataKutusu = kutu.querySelector('.auth-assist');
    if (ana && hataKutusu) ana.insertBefore(not, hataKutusu);
    else kutu.appendChild(not);
  }

  /* ── Parola yolu ────────────────────────────────────────────────────── */

  async function parolaylaGir() {
    if (_mesgul) return;
    var girdi = el('auth-input');
    var parola = girdi && girdi.value ? girdi.value.trim() : '';
    if (!parola) return;
    hata('');
    _mesgul = true;
    mesgulGorunum(true, 'password');
    try {
      var r = await fetch(BASE + '/api/lock/unlock', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ parola: parola })
      });
      var d = null;
      try { d = await r.json(); } catch (_) {}
      if (r.ok && d && d.token) {
        tokenYaz(d.token);
        if (girdi) girdi.value = '';
        ekraniKapat();
        basariylaAcildi();
        return;
      }
      /* Sunucunun cümlesi kullanılır, uydurulmaz: kalan deneme hakkı ve kilit
         süresi orada hesaplanıyor. Burada "Parola yanlış" yazmak, 4. denemeden
         sonra gelen "10 dk kapatıldı" bilgisini yutardı. */
      hataSunucuYaDa(d && d.detail, 'giris.parola-yanlis');
      if (girdi) { girdi.value = ''; girdi.focus(); }
      _durum = await durumOku();
      yuzDugmesiniKur();
    } catch (_) {
      hata('kilit.sunucuya-ulasilamadi');
    } finally {
      _mesgul = false;
      mesgulGorunum(false, 'password');
    }
  }

  /* ── Yüz yolu ───────────────────────────────────────────────────────── */

  function kamerayiKapat() {
    if (_akis) {
      try { _akis.getTracks().forEach(function (t) { t.stop(); }); } catch (_) {}
      _akis = null;
    }
    if (_video) {
      try { _video.pause(); _video.srcObject = null; } catch (_) {}
      _video = null;
    }
  }

  async function kamerayiAc() {
    _akis = await navigator.mediaDevices.getUserMedia({ video: { width: 640, height: 480 } });
    _video = document.createElement('video');
    _video.autoplay = true; _video.playsInline = true; _video.muted = true;
    _video.srcObject = _akis;
    await new Promise(function (coz) {
      if (_video.readyState >= 2) return coz();
      _video.onloadeddata = coz;
    });
    await _video.play().catch(function () {});
  }

  function kareAl() {
    if (!_video || !_video.videoWidth) return null;
    var c = document.createElement('canvas');
    c.width = _video.videoWidth; c.height = _video.videoHeight;
    c.getContext('2d').drawImage(_video, 0, 0, c.width, c.height);
    return new Promise(function (coz) {
      c.toBlob(function (b) { coz(b); }, 'image/jpeg', 0.85);
    });
  }

  /* Kilit ekranında canlı kamera önizlemesi + talimat şeridi.
   *
   * 🔴 İlk sürümde önizleme YOKTU ve saha denemesi başarısız oldu (2026-09-06):
   * *"3 kırpma istendi, 0 algılandı"* — yüz `conf=0.936` ile TANINDI, elenen şey
   * canlılıktı. Kullanıcı kendini göremiyor, kadrajda mı bilmiyor, ne zaman
   * kırpacağını kestiremiyordu. Talimat yalnız düğme metnindeydi.
   */
  function sahneKur(mesaj) {
    var kutu = document.querySelector('#auth-screen .auth-box');
    if (!kutu) return null;
    var s = el('auth-yuz-sahne');
    if (!s) {
      s = document.createElement('div');
      s.id = 'auth-yuz-sahne';
      s.className = 'auth-yuz-sahne';
      s.innerHTML = '<div class="auth-yuz-video"></div>'
        + '<div class="auth-yuz-mesaj" role="status" aria-live="polite">'
        + '<span class="auth-yuz-durum-nokta" aria-hidden="true"></span>'
        + '<span class="auth-yuz-metin"></span>'
        + '<span class="auth-yuz-sayac"></span></div>';
      var ana = kutu.querySelector('.auth-main');
      var parolaAlani = kutu.querySelector('.auth-password-group');
      if (ana && parolaAlani) ana.insertBefore(s, parolaAlani); else kutu.appendChild(s);
    }
    s.style.display = '';
    if (mesaj !== undefined) {
      var m = s.querySelector('.auth-yuz-metin');
      if (m) m.textContent = mesaj;
    }
    return s;
  }

  /* `sayac` yalnız hazırlık geri sayımında dolu: talimatın sonuna yapışık
     "· 2" ne saydığını söylemiyordu, kırpma sayısı sanılıyordu ( L6). */
  function sahneMesaj(metin, durum, sayac) {
    var m = document.querySelector('#auth-yuz-sahne .auth-yuz-mesaj');
    if (!m) return;
    var yazi = m.querySelector('.auth-yuz-metin');
    if (yazi) yazi.textContent = metin;
    var say = m.querySelector('.auth-yuz-sayac');
    if (say) say.textContent = sayac || '';
    m.dataset.durum = durum || 'bekliyor';
  }

  function sahneKapat() {
    var s = el('auth-yuz-sahne');
    if (s) s.remove();
  }

  async function yuzleGir() {
    if (_mesgul) return;
    _mesgul = true;
    mesgulGorunum(true, 'face');
    var btn = el('auth-yuz-btn');
    hata('');
    try {
      var rc = await fetch(BASE + '/api/lock/status');   // guard tazelensin
      if (rc.ok) _durum = await rc.json();

      var ch = await fetch(BASE + '/api/face/liveness/challenge', { method: 'POST' });
      var chd = null;
      try { chd = await ch.json(); } catch (_) {}
      if (!ch.ok) { hataSunucuYaDa(chd && chd.detail, 'kilit-ekran.yuz-baslatilamadi'); return; }

      /* 🔥 MODELİ ŞİMDİ ISIT — beklemeden.
         Ölçüm: buffalo_l'ın yüklenmesi 2-4 sn (CPU) sürüyor ve bugüne kadar
         kareler POST edildikten SONRA başlıyordu, yani kullanıcının beklediği
         sürenin üstüne biniyordu. Oysa buradan sonra istemci ~6 sn meşgul:
         kamera açılışı + 3 sn geri sayım + 40 kare toplama. Isıtma o ölü
         zamana sığar.
         ⚠️ `await` YOK ve olmamalı — beklersek kazanç sıfırlanır, üstelik
         ısıtma başarısız olursa giriş akışı da düşerdi. Başarısızlık sessiz:
         gerçek hatayı `/verify` kendi yolunda üretip kullanıcıya söyler. */
      fetch(BASE + '/api/face/warmup', { method: 'POST' }).catch(function () {});

      if (btn) { btn.disabled = true; dugmeMetni(btn, _alt('kilit-ekran.kamera-aciliyor')); }
      sahneKur(_alt('kilit-ekran.kamera-aciliyor'));
      sahneMesaj(_alt('kilit-ekran.kamera-aciliyor'), 'bekliyor');
      await kamerayiAc();

      // Önizlemeyi sahneye tak — kullanıcı kadrajda mı görsün.
      var yuva = document.querySelector('#auth-yuz-sahne .auth-yuz-video');
      if (yuva && _video) { yuva.appendChild(_video); _video.className = 'auth-yuz-onizleme'; }

      /* ⚠️ ALAN ADLARI SUNUCUDAN — ilk sürümde `talimat` / `sure_saniye` diye
         UYDURULMUŞTU ve ikisi de yoktu; talimat hiç gösterilmedi, süre 25 yerine
         6 sn sanıldı. Gerçek şema (`face_liveness.olustur`):
           challenge_id · action · blinks · ttl_seconds · min_frames · instruction */
      var kirpmaSayisi = (chd && chd.blinks) || 2;
      var minKare = (chd && chd.min_frames) || 8;
      var talimat = (chd && chd.instruction) || _alt('kilit-ekran.kameraya-bak-kirp', { n: kirpmaSayisi });
      /* Talimat YALNIZ sahne şeridinde yazar; düğme kısa durum taşır. Düğmeye
         yazılan talimat iki satıra kırılıyor ve aynı cümle üç yerde tekrar
         ediyordu ( L5/L6). */
      if (btn) dugmeMetni(btn, _alt('kilit-ekran.yuz-araniyor'));

      // Hazırlık — kullanıcı kadraja girsin, ne yapacağını okusun.
      for (var g = 3; g > 0; g--) {
        sahneMesaj(talimat, 'araniyor', _alt('kilit-ekran.hazirlan', { n: g }));
        await new Promise(function (c) { setTimeout(c, 700); });
      }

      /* 🔑 ÖRNEKLEME ARALIĞI — kusurun kendisi buydu.
         Bir göz kırpması ~100-150 ms sürer. İlk sürüm 200 ms aralıkla
         örnekliyordu; kapalı-göz karesi tamamen iki örnek ARASINA düşebiliyor ve
         sunucu haklı olarak "0 kırpma" diyordu. 100 ms, kapanma anını en az bir
         karede yakalar.
         Kare sayısı sunucunun tavanına (FACE_LIVENESS_MAX_FRAMES = 40) uyar —
         aşarsa istek 413 döner. 40 × 100 ms ≈ 4 sn, TTL 25 sn'nin çok altında. */
      var TAVAN = 40, araMs = 100;
      var kareler = [];
      sahneMesaj(_alt('kilit-ekran.simdi-kirp', { n: kirpmaSayisi }), 'araniyor');

      /* 🔥 PARÇALI GÖNDERİM — toplama ile analiz artık ÜST ÜSTE koşuyor.
         Ölçüm (2026-09-10, sahte kamera + gerçek model): eskiden istemci 40
         kareyi ~4 sn toplayıp tek pakette yolluyordu ve sunucu o 4 sn boyunca
         BOŞ duruyordu; analiz (40 × ~150 ms ≈ 6 sn) ancak son kareden sonra
         başlıyordu. 12'lik dilimler toplanırken gidince analizin çoğu
         toplamanın altına gizleniyor. Ölçülen: 12,9 sn → ~9,0 sn.

         ⚠️ Dilimler ZİNCİRLE gönderilir (bir önceki bitmeden sonraki
         yollanmaz): aynı anda iki dilim uçarsa sunucu tarafında ikisi de
         model kuyruğuna girer, kazanç kalmaz. Zincir toplamayı BEKLETMEZ —
         kare döngüsü kendi hızında sürer.

         🔴 Bir dilim düşerse parçalı yola devam EDİLMEZ: sunucuda yarım kalmış
         bir birikimle doğrulamak, sebebi hiçbir yerde yazmayan bir canlılık
         reddi üretirdi (eksik kareler = eksik kırpma). O durumda `parca`
         alanı hiç gönderilmez ve sunucu birikimi atıp eski yolu koşar. */
      var PARCA = 12;
      var zincir = Promise.resolve(), siradakiParca = 0, gonderilen = 0, parcaBozuk = false;

      function parcaGonder(dilim, no) {
        var fdp = new FormData();
        fdp.append('challenge_id', (chd && chd.challenge_id) || '');
        fdp.append('parca', String(no));
        dilim.forEach(function (b, i) { fdp.append('files', b, 'p' + no + '_' + i + '.jpg'); });
        return fetch(BASE + '/api/face/frames', { method: 'POST', body: fdp })
          .then(function (res) { if (!res.ok) parcaBozuk = true; })
          .catch(function () { parcaBozuk = true; });
      }

      while (kareler.length < TAVAN) {
        var kare = await kareAl();
        if (kare) kareler.push(kare);
        // Son dilim BİLEREK gönderilmez — onu `/verify` taşır, böylece
        // doğrulama fazladan bir gidiş-dönüş beklemez.
        if (!parcaBozuk && kareler.length - gonderilen >= PARCA
            && kareler.length < TAVAN) {
          (function (dilim, no) {
            zincir = zincir.then(function () {
              return parcaBozuk ? null : parcaGonder(dilim, no);
            });
          })(kareler.slice(gonderilen, gonderilen + PARCA), siradakiParca++);
          gonderilen += PARCA;
        }
        await new Promise(function (c) { setTimeout(c, araMs); });
      }
      sahneMesaj(_alt('kilit-ekran.dogrulaniyor'), 'bekliyor');
      kamerayiKapat();

      if (kareler.length < minKare) { yuzHata('kilit-ekran.yetersiz-kare'); return; }

      if (btn) dugmeMetni(btn, _alt('kilit-ekran.dogrulaniyor'));
      await zincir;   // biriken dilimler sunucuya varmış olsun

      var fd = new FormData();
      fd.append('challenge_id', (chd && chd.challenge_id) || '');
      if (parcaBozuk) gonderilen = 0;   // eski yol: 40 karenin tamamı gider
      else if (gonderilen > 0) fd.append('parca', String(siradakiParca));
      kareler.slice(gonderilen).forEach(function (b, i) {
        fd.append('files', b, 'k' + i + '.jpg');
      });

      var r = await fetch(BASE + '/api/face/verify', { method: 'POST', body: fd });
      var d = null;
      try { d = await r.json(); } catch (_) {}
      if (r.ok && d && d.token) {
        sahneMesaj(_alt('kilit-ekran.yuz-tanindi'), 'basarili');
        await new Promise(function (c) { setTimeout(c, 220); });
        tokenYaz(d.token);
        ekraniKapat();
        basariylaAcildi();
        return;
      }
      sahneMesaj(_alt('kilit-ekran.yuz-taninmadi'), 'hata');
      await new Promise(function (c) { setTimeout(c, 220); });
      yuzHata('kilit-ekran.yuz-dogrulanamadi', d && d.detail);
      _durum = await durumOku();
      yuzDugmesiniKur();
    } catch (e) {
      /* Kamera izni reddi ile ağ hatasını ayır: ikisi için yapılacak şey farklı. */
      var ad = e && e.name ? e.name : '';
      if (ad === 'NotAllowedError' || ad === 'SecurityError') {
        yuzHata('kilit-ekran.kamera-izni-yok-parola');
      } else if (ad === 'NotFoundError' || ad === 'NotReadableError') {
        yuzHata('kilit-ekran.kamera-bulunamadi');
      } else {
        yuzHata('kilit-ekran.yuz-basarisiz');
      }
    } finally {
      kamerayiKapat();
      sahneKapat();
      /* Tıklanabilir düğmenin metni her zaman "Yüzümle gir"dir (kapalı düğmeye
         basılamaz); eski metni saklamak yerine o AN'ın dilinde yeniden yazılır. */
      if (btn) { btn.disabled = false; dugmeMetni(btn, _alt('kilit-ekran.yuzumle-gir')); }
      _mesgul = false;
      mesgulGorunum(false, 'password');
    }
  }

  /* ── Açılış ─────────────────────────────────────────────────────────── */

  function basariylaAcildi() {
    /* Perdenin ardındaki normal başlangıç zinciri. core.js token'lı akışta bunu
       kendi içinde yapıyor; kilit yolundan gelindiğinde de aynı adımlar
       koşmalı, yoksa model/dil seçici boş açılır (core.js'te aynı hata bir kez
       yaşandı ve yorumu orada duruyor). */
    ['connect', '_startMemoryStatsPoll', 'initModelSelector', 'initLanguageSelector']
      .forEach(function (ad) {
        if (typeof window[ad] === 'function') { try { window[ad](); } catch (_) {} }
      });

    /* Sekme/özellik bayraklarını tazele (açık kaynak sürümde hepsi açık; ad korunuyor). */
    if (typeof window.refreshAllAccess === 'function') {
      try { window.refreshAllAccess(); } catch (e) {
        console.warn('[yuki] kilit sonrası sekme bayrakları tazelenemedi:', e);
      }
    }
  }

  /* ── Sahip kaydı ─────────────────────────────────────────────────────────
   * 🔴 Bu fonksiyon EKSİK HALKAYI kapatıyor (2026-09-06 canlı turda bulundu).
   *
   * Yüz tanımada iki ayrı kavram var ve arayüzde yalnız biri vardı:
   *   `register` → "bu kişi kim" (tanıma listesi). faces.js bunu yapıyordu.
   *   `enroll`   → "bu kişi SAHİP" (yüzle giriş hakkı). Ucu vardı, ÇAĞIRANI YOKTU.
   *
   * Sonuç ölçüldü: geliştirici yüzünü kaydetti, `/api/face/list` onu döndürüyor
   * (`"geliştirici deniz"`), ama `enrolled:false` / `owner:null` — yani açılışta yüzle
   * giriş seçeneği hiç çıkmıyordu. Kayıtlı yüzü olan kullanıcı için bu, sessizce
   * çalışmayan bir özellik demekti.
   */
  async function sahipKaydet() {
    if (_mesgul) return { ok: false, mesaj: _alt('kilit-ekran.islem-suruyor') };
    _mesgul = true;
    try {
      await kamerayiAc();
      /* Kamera açılır açılmaz kare almak karanlık/bulanık görüntü yakalıyor —
         sensörün pozlama ayarı oturmuyor. Kısa bir bekleme, kullanıcının
         "yüzüm tanınmadı" diye tekrar denemesinden ucuz. */
      await new Promise(function (c) { setTimeout(c, 600); });
      var kare = await kareAl();
      if (!kare) return { ok: false, mesaj: _alt('kilit-ekran.goruntu-alinamadi') };
      var fd = new FormData();
      fd.append('file', kare, 'sahip.jpg');
      var f = window.authFetch || fetch;
      var r = await f(BASE + '/api/face/enroll', { method: 'POST', body: fd });
      var d = null;
      try { d = await r.json(); } catch (_) {}
      if (!r.ok) return { ok: false, mesaj: (d && d.detail) || _alt('kilit-ekran.yuz-kaydedilemedi') };
      return { ok: true, mesaj: (d && d.message) || _alt('kilit-ekran.yuz-kaydedildi') };
    } catch (e) {
      var ad = e && e.name ? e.name : '';
      if (ad === 'NotAllowedError' || ad === 'SecurityError') {
        return { ok: false, mesaj: _alt('kilit-ekran.kamera-izni-yok') };
      }
      return { ok: false, mesaj: _alt('kilit-ekran.kamera-acilamadi') };
    } finally {
      kamerayiKapat();
      _mesgul = false;
    }
  }

  /* ── Dil tazeleyici ──────────────────────────────────────────────────────
   * `dil.js::uygula` olayı WINDOW'a yayınlar (document'a değil).
   *
   * Yükleme sırası (index.html): `dil.js` satır 95 → `app-lock.js` satır 1907,
   * ikisi de senkron. Bu dosyanın hiçbir çizimi yükleme anında koşmaz
   * (`ekraniGoster` core.js'in async `_authCheckAndInit`'inden çağrılır), yani
   * ilk çizimde `YukiDil` her zaman hazırdır → ham anahtar görünmez. Yine de
   * sıra bir gün değişirse bu dinleyici kilit ekranını dil hazır olduğunda
   * doğru metne çeker.
   *
   * 🔑 `.auth-sub` HTML'de `data-i18n` taşır; kilit modunda metnini BİZ
   * yazdığımız için `dil.js::_sahibiBizMiyiz` onu bırakır → tazelemek bizim işimiz.
   * Parola alanına, kamera akışına ve `/api/lock/*` akışına dokunulmaz;
   * yüz denemesi sürerken (`_mesgul`) düğme yeniden kurulmaz (akış onu tutuyor,
   * `finally` yeni dilde geri yazar). */
  window.addEventListener('yuki-dil-degisti', function () {
    var perde = el('auth-screen');
    if (!_kilitModu || !perde || perde.classList.contains('hidden')) return;
    var alt = perde.querySelector('.auth-sub');
    if (alt) {
      alt.textContent = _alt(_durum && _durum.yuzle_girilebilir
        ? 'kilit-ekran.yontem-sec'
        : 'kilit-ekran.acilis-parolasi');
    }
    if (!_mesgul) {
      yuzDugmesiniKur();
    } else {
      var not = el('auth-yuz-not');
      if (not) not.textContent = _alt('kilit-ekran.yuz-not');
    }
    /* Hata satırını yalnız hâlâ BİZİM yazdığımız metni taşıyorsa tazele —
       arada core.js bir şey yazdıysa onun cümlesini ezme. */
    var hataEl = el('auth-error');
    if (_sonHata && _sonHata.anahtar && hataEl && hataEl.textContent === _sonHataMetin) {
      _hataYaz(_sonHata);
    }
  });

  window.AppLock = {
    gerekliMi: gerekliMi,
    ekraniGoster: ekraniGoster,
    kilitModuMu: function () { return _kilitModu; },
    girisDene: parolaylaGir,
    sahipKaydet: sahipKaydet,
    tokenSil: tokenSil
  };

  /* Enter tuşu: kilit modunda core.js'in `_authLogin`'i yerine bizim yolumuz.
     core.js'in kendi dinleyicisi duruyor — o AUTH_TOKEN modunda çalışır. */
  document.addEventListener('keydown', function (e) {
    if (e.key !== 'Enter' || !_kilitModu) return;
    var perde = el('auth-screen');
    if (!perde || perde.classList.contains('hidden')) return;
    if (document.activeElement !== el('auth-input')) return;
    e.preventDefault();
    e.stopPropagation();
    parolaylaGir();
  }, true);   // capture: core.js'in dinleyicisinden ÖNCE koşsun
})();
