/* ════════════════════════════════════════════════════════════════════
   sohbet-sahne.js — SOHBET görünümünün sahnesi (2026-10-04)

   KLASİK + TAM BOY tek SOHBET modunda birleşti (kişiseldeki 'ün ürün
   karşılığı; kişiselden yalnız DÜZEN ve ÖZELLİK alındı, renk ürünün tokenları).
   #avatar-pane karakterin sahnesi; içinde üç kip var (localStorage
   `yukiSohbetKip_v1`):
     · RESİM — portre belden yukarı kadraj (modes/sohbet-sahne.css)
     · VİDEO — eski TAM BOY'un bekleme klibi (core.js `_applyFullbodyVideo`).
               Klibi olmayan karakterde anahtar GÖRÜNMEZ, kip RESİM sayılır;
               kayıtlı tercih silinmez (Yuki'ye dönünce video geri gelir).
     · CANLI — portre yerine hareketli Yuki (mesh-avatar-studio motoru, WebGL2,
               vendor/mesh-avatar, MIT). Ağız TTS sesini izler (YukiAudioBus.tts),
               duygu yüze yansır, göz kırpar, nefes alır. Kişisel AliceAi'den
               (10-10/10-11, c53b052…bea6c21) ürüne çevrildi — .
               🔴 Kapılar (ikisi de seçeneği GİZLER, kayıtlı tercih silinmez):
                 ① yalnız Yuki — öbür dört karakterin rig'i yok
                 ② HAFİF grafik kademesinde (data-gfx="hafif") KAPALI — zayıf
                    makinede sürekli WebGL yükü olmasın (kişiselde HAFİF yalnız
                    salınımı kesiyordu; ürün müşteri donanımını bilmez → tam kapalı).
               Motor yalnız bu kipte, SOHBET'te ve sahne Büyük'ken yüklenir
               (dinamik import → başka kipte hiç inmez); çıkınca kapatılır, GL
               bağlamı bırakılır. Motor/WebGL2 kurulamazsa sessizce RESİM'e düşer.

   Duygu etiketi "ŞU AN · <DUYGU>" — ürünün duygu motorunu DİNLER, yeni istek
   ya da LLM çağrısı YOK. Kaynak (core.js WS kancası çağırır):
     WS `emotion`  → neutral happy sad angry surprised shy tired
                     (emotion_engine.py; neutral = motorun sönümü → SAKİN)
     WS `state`    → thinking = DÜŞÜNÜYOR (tur boyunca, duygu gelene kadar)
     WS `behavior` → wave = EL SALLIYOR (4 sn)
   `source: 'voice'` olan duygu KULLANICININ ses tonudur, karakterin değil → atlanır.
   Veri hiç gelmezse etiket SAKİN'de kalır.

   Durum satırı (#hizli-satir; 10-11'den beri çipsiz — eylemler ⋯ menüsünde): ücretli araca dayanan menü öğesi yalnız kademe
   yetkisi `=== true` gelince açılır; cevap yoksa kapalı kalır (fail-closed).

   🔴 core.js bu dosyayı `window.SohbetSahne` üzerinden OPSİYONEL çağırır —
   dosya yüklenmezse sohbet eskisi gibi çalışır. Sınıflar (sohbet-mode ·
   sk-video · sk-resim) yalnız SOHBET'te; HALKA #avatar-pane'i zaten gizliyor.

   ?widget=1 (yuki-widget iframe) modunda devre dışı.
   ════════════════════════════════════════════════════════════════════ */
(function () {
  'use strict';
  if (new URLSearchParams(location.search).has('widget')) return;

  // Çeviri yardımcısı — adı `_t` (bkz. chat-modes.js başlığı: düz `t` gölgelenir).
  function _t(anahtar, degerler) {
    return (window.YukiDil && window.YukiDil.t)
      ? window.YukiDil.t(anahtar, degerler) : String(anahtar);
  }

  // Anahtar chat-modes.js ile ORTAK: oradaki TAM BOY göçü buraya 'video' yazar.
  var KIP_ANAHTAR = 'yukiSohbetKip_v1';

  // Kişisel SOHBET'in dokuz duygusu. `nod` = SAKİN (nötrün kendi adı yok).
  var DUYGULAR = ['nod', 'happy', 'sad', 'angry', 'surprised', 'shy', 'tired', 'thinking', 'wave'];
  function anahtar(e) {
    e = String(e || '').toLowerCase();
    if (!e || e === 'neutral' || e === 'idle') return 'nod';
    return DUYGULAR.indexOf(e) !== -1 ? e : 'nod';
  }

  var KIPLER = ['video', 'resim', 'canli'];
  // CANLI motoru — sürüm sayacı burada (sw.js cache-first'ü için ?v=)
  var AVATAR_JS = '/ui/vendor/mesh-avatar/avatar.js?v=1';
  var AVATAR_TEMEL = '/ui/assets/avatar/yuki/';

  var S = {
    kip: 'resim',       // kullanıcının KAYITLI tercihi
    durum: 'idle',
    duygu: 'nod',       // motorun son duygusu (nod = nötr)
    el: 0,              // el sallama bitiş zamanı (ms)
    gosterilen: null,   // ekrandaki duygu (geçiş animasyonu yalnız değişince)
    olay: 0,            // duygu/davranış olayı sayacı (CANLI aynı duyguyu yeniden oynatsın)
  };
  try {
    var _k = localStorage.getItem(KIP_ANAHTAR);
    S.kip = KIPLER.indexOf(_k) !== -1 ? _k : 'resim';
  } catch (_) {}

  // ── yardımcılar ──
  var SVG_NS = 'http://www.w3.org/2000/svg';
  var IKON = {
    film:  'M3 5h18v14H3zM7 5v14M17 5v14M3 9.5h4M3 14.5h4M17 9.5h4M17 14.5h4',
    resim: 'M3 4h18v16H3zM21 15.5l-5-5L5 20',
    canli: 'M12 3.5a5 5 0 0 1 5 5v1.5a5 5 0 0 1-10 0V8.5a5 5 0 0 1 5-5zM9.5 9.5h.01M14.5 9.5h.01M10 13q2 1.5 4 0M6 21q1.5-4.5 6-4.5t6 4.5',
  };
  function ikon(ad) {
    var s = document.createElementNS(SVG_NS, 'svg');
    s.setAttribute('viewBox', '0 0 24 24');
    s.setAttribute('aria-hidden', 'true');
    var p = document.createElementNS(SVG_NS, 'path');
    p.setAttribute('d', IKON[ad]);
    s.appendChild(p);
    if (ad === 'resim') {
      var c = document.createElementNS(SVG_NS, 'circle');
      c.setAttribute('cx', '9'); c.setAttribute('cy', '9.5'); c.setAttribute('r', '1.8');
      s.appendChild(c);
    }
    return s;
  }
  function el(tag, cls, metin) {
    var e = document.createElement(tag);
    if (cls) e.className = cls;
    if (metin != null) e.textContent = metin;
    return e;
  }
  function karakter() {
    try { return (window.getCharacter && window.getCharacter()) || 'yuki'; }
    catch (_) { return 'yuki'; }
  }
  function sohbetteMi() {
    try { return (window.getViewMode ? window.getViewMode() : 'chat') === 'chat'; }
    catch (_) { return true; }
  }
  // Bu karakterin bu cihazda oynayabilen klibi var mı (core.js karar verir:
  // klip listesi · veri tasarrufu · hareket azaltma).
  function klipVar() {
    try { return !!(window.karakterKlibiVar && window.karakterKlibiVar(karakter())); }
    catch (_) { return false; }
  }
  function hafifMi() { return document.documentElement.getAttribute('data-gfx') === 'hafif'; }
  // CANLI bu karakterde/kademede seçilebilir mi (kapılar dosya başlığında).
  function canliMumkun() { return karakter() === 'yuki' && !hafifMi() && !C.hata; }
  function secenekler() {
    var l = [];
    if (klipVar()) l.push('video');
    l.push('resim');
    if (canliMumkun()) l.push('canli');
    return l;
  }
  // Ekrandaki kip: tercih edilen kip bu karakterde/cihazda yoksa RESİM.
  function etkinKip() { return secenekler().indexOf(S.kip) !== -1 ? S.kip : 'resim'; }

  // ── DOM ──
  var R = {};
  function kur() {
    var pane = document.getElementById('avatar-pane');
    if (!pane || document.getElementById('ss-kip')) return;

    // Sahne iki temada da KOYU: beş karakter görseli siyah fonlu; açık temada
    // alt karartma açık renge dönünce görüntü "yıkanıyordu" (urun-chat.png,
    // 10-04 kıyası). Kapsam yalnız sahne — sohbet sütunu temayı izler.
    // Aynı desen HALKA'da var (chat-modes.js `_halkaPaletiSabitle`).
    pane.setAttribute('data-tema', 'koyu');
    pane.setAttribute('role', 'region');
    pane.setAttribute('aria-label', _t('sahne.bolge'));

    // VİDEO | RESİM anahtarı — değiştirdiği sahnenin üstünde
    R.kip = el('div', 'ss-kip');
    R.kip.id = 'ss-kip';
    R.kip.setAttribute('role', 'radiogroup');
    [['video', 'film'], ['resim', 'resim'], ['canli', 'canli']].forEach(function (t) {
      var b = el('button');
      b.type = 'button';
      b.setAttribute('role', 'radio');
      b.dataset.kip = t[0];
      b.append(ikon(t[1]), el('span', 'ss-kip-ad'));
      b.addEventListener('click', function () { kip(t[0]); });
      R.kip.appendChild(b);
    });
    // Ok tuşlarıyla radyo grubunda gezinme — yalnız GÖRÜNEN seçenekler arasında, döngülü
    R.kip.addEventListener('keydown', function (e) {
      var yon = { ArrowLeft: -1, ArrowUp: -1, ArrowRight: 1, ArrowDown: 1 }[e.key];
      if (!yon) return;
      e.preventDefault();
      var l = secenekler();
      var yeni = l[(l.indexOf(etkinKip()) + yon + l.length) % l.length];
      kip(yeni);
      var hedef = R.kip.querySelector('[data-kip="' + yeni + '"]');
      if (hedef) hedef.focus();
    });
    pane.appendChild(R.kip);

    // ŞU AN · DUYGU — #avatar-hud'un ilk satırı (karakter şeridinin üstünde).
    // Akışta, mutlak konum yok: şerit 09-25'te aynı gerekçeyle akışa alınmıştı.
    R.duygu = el('div', 'ss-duygu');
    R.duygu.id = 'ss-duygu';
    var ust = el('span', 'ss-duygu-ust');
    ust.append(el('i', 'ss-nabiz'), (R.suAn = el('span')));
    R.duyguAd = el('b', 'ss-duygu-ad');
    R.duygu.append(ust, R.duyguAd);
    var hud = document.getElementById('avatar-hud');
    if (hud) hud.prepend(R.duygu); else pane.appendChild(R.duygu);

    etiketleriYaz();
  }

  function etiketleriYaz() {
    if (!R.kip) return;
    R.kip.setAttribute('aria-label', _t('sahne.kip-grup'));
    R.kip.querySelectorAll('button').forEach(function (b) {
      var k = b.dataset.kip;
      b.querySelector('.ss-kip-ad').textContent = _t('sahne.kip.' + k);
      b.setAttribute('aria-label', _t('sahne.kip.' + k + '-etiket'));
      b.title = _t('sahne.kip.' + k + '-etiket');
    });
    R.suAn.textContent = _t('sahne.su-an');
    var pane = document.getElementById('avatar-pane');
    if (pane) pane.setAttribute('aria-label', _t('sahne.bolge'));
    S.gosterilen = null;          // dil değişti → ad yeniden yazılsın
    ciz();
  }

  // ── çizim ──
  // Canlı duygu: el sallama → motorun duygusu → düşünüyor → sakin
  function canli() {
    if (S.el > Date.now()) return 'wave';
    if (S.duygu !== 'nod') return S.duygu;
    if (S.durum === 'thinking') return 'thinking';
    return 'nod';
  }
  function ciz() {
    if (!R.duygu) return;
    var k = canli();
    canliYuz(k);
    R.duygu.dataset.duygu = k;
    if (k !== S.gosterilen) {
      S.gosterilen = k;
      R.duyguAd.textContent = _t('sahne.duygu.' + k);
      // Değişimi göster: kısa giriş geçişi (CSS, hareket azaltmada yok)
      R.duygu.classList.remove('ss-yeni');
      void R.duygu.offsetWidth;
      R.duygu.classList.add('ss-yeni');
    }
  }

  // ── kip ──
  function kipUygula() {
    var b = document.body;
    var on = b.classList.contains('sohbet-mode');
    var ek = etkinKip();
    b.classList.toggle('sk-video', on && ek === 'video');
    // CANLI, RESİM'in kadrajını BİLEREK paylaşır (sk-resim + sk-canli): canvas
    // yüklenene kadar ya da kurulamazsa altındaki portre görünür kalır.
    b.classList.toggle('sk-resim', on && ek !== 'video');
    b.classList.toggle('sk-canli', on && ek === 'canli');
    if (R.kip) {
      var l = secenekler();
      // Tek seçenekli anahtar anlamsız → hiç gösterme.
      R.kip.hidden = l.length < 2;
      // Üç seçenekte anahtar yalnız ikon (ad aria-label/title'da): yazılı hâli 1280'de
      // ~275px uzayıp CANLI'da saçın üstüne biniyordu (göz 10-11 tur 2 #1-#2).
      R.kip.classList.toggle('ss-kip-uc', l.length > 2);
      R.kip.querySelectorAll('button').forEach(function (btn) {
        btn.hidden = l.indexOf(btn.dataset.kip) === -1;
        var sec = btn.dataset.kip === ek;
        btn.setAttribute('aria-checked', sec ? 'true' : 'false');
        btn.tabIndex = sec ? 0 : -1;
      });
    }
    if (window.applyFullbodyVideo) window.applyFullbodyVideo();
    canliEsitle();
  }
  function kip(k) {
    if (secenekler().indexOf(k) === -1) return;
    S.kip = k;
    try { localStorage.setItem(KIP_ANAHTAR, k); } catch (_) {}
    kipUygula();
    document.dispatchEvent(new CustomEvent('sohbetkipchange', { detail: { kip: k } }));
  }

  // ════ CANLI — hareketli Yuki (mesh-avatar-studio motoru) ════
  // Yaşam döngüsü tek yerde: canliEsitle() istenen durumu ölçer, motoru kurar ya
  // da kapatır. Kurulum async → arada kip değişirse (C.no) yarım kurulum atılır.
  // C.hata sayfa ömrü boyunca kalır: motor bir kez kurulamadıysa yeniden denenmez.
  var C = { av: null, canvas: null, kuruluyor: false, no: 0, raf: 0, konusuyor: false,
            hata: null, buf: null, az: false, yuz: null, yuzAnahtar: null, yuzT: 0, yuzSondu: false };
  function buyukMu() {
    var app = document.getElementById('app');
    return !app || app.dataset.avatarEtkin === undefined || app.dataset.avatarEtkin === 'buyuk';
  }
  function canliIstenir() {
    return etkinKip() === 'canli' && document.body.classList.contains('sohbet-mode') && buyukMu();
  }
  function canliEsitle() {
    if (canliIstenir()) { if (!C.av && !C.kuruluyor) canliKur(); }
    else canliKapat();
  }
  function canliKur() {
    var pane = document.getElementById('avatar-pane');
    if (!pane) return;
    var no = ++C.no;
    C.kuruluyor = true;
    var cv = document.createElement('canvas');
    cv.className = 'ss-canli';
    cv.setAttribute('aria-hidden', 'true');
    var hud = document.getElementById('avatar-hud');
    pane.insertBefore(cv, hud || null);   // HUD'un (karartma + yazı) ALTINDA
    C.canvas = cv;
    import(AVATAR_JS).then(function (m) {
      // Canvas KARE ve kadrajı portreden türetilmiş (sohbet-sahne.css § CANLI) → ölçek = kenar/1024
      return m.olustur(cv, AVATAR_TEMEL, { fit: 'contain' });
    }).then(function (av) {
      if (no !== C.no || !canliIstenir()) { try { av.kapat(); } catch (_) {} if (cv.parentNode) cv.remove(); return; }
      C.av = av; C.kuruluyor = false;
      canliHareket();
      C.yuzAnahtar = null;
      canliYuz(canli());
      pane.classList.add('ss-canli-hazir');
      C.raf = requestAnimationFrame(canliSes);
    }).catch(function (err) {
      if (no !== C.no) return;
      C.kuruluyor = false;
      C.hata = String((err && err.message) || err);
      console.warn('[SohbetSahne] CANLI kurulamadi, resme dusuldu:', C.hata);
      if (cv.parentNode) cv.remove();
      C.canvas = null;
      kipUygula();          // CANLI seçeneği gizlenir, sahne RESİM'e döner
    });
  }
  function canliKapat() {
    C.no++;
    if (C.raf) cancelAnimationFrame(C.raf);
    C.raf = 0; C.kuruluyor = false;
    clearTimeout(C.yuzT); C.yuz = C.yuzAnahtar = null;
    if (C.av) { try { C.av.kapat(); } catch (_) {} C.av = null; }
    if (C.canvas && C.canvas.parentNode) C.canvas.remove();
    C.canvas = null;
    var pane = document.getElementById('avatar-pane');
    if (pane) pane.classList.remove('ss-canli-hazir');
  }
  // Hareket azaltma tercihi: salınım + kendiliğinden jest yok; kırpma, nefes, konuşma kalır.
  // (HAFİF'te motor hiç kurulmaz — kapı canliMumkun'da.)
  function canliHareket() {
    if (!C.av) return;
    var az = false;
    try { az = window.matchMedia('(prefers-reduced-motion: reduce)').matches; } catch (_) {}
    C.az = az;
    C.av.setSwayGain(az ? 0 : 1);
    canliOtomatik();
  }
  // Duygu → yüz: sahnenin canlı duygusu motorun gözü AÇIK konuşma yüzlerine (setEmotion)
  // ve ifade katmanına (setExpression) eşlenir; YUZ_SURE sonra sakine döner.
  // 'smile' bilerek yok: gözü kapatıyor. Kızgın: çizilmiş kızgın göz (setKizgin).
  var YUZ = {
    nod: ['neutral', 'neutral'], thinking: ['neutral', 'neutral'],
    happy: ['happy', 'neutral'], wave: ['happy', 'neutral'],
    sad: ['sad', 'sad'], angry: ['angry', 'angry'], surprised: ['surprised', 'neutral'],
    shy: ['relaxed', 'shy'], tired: ['neutral', 'halfLidded'],
  };
  var YUZ_SURE = 8000;
  function yuzEtkin() {
    var y = C.yuz && !C.yuzSondu ? YUZ[C.yuz] : null;
    return !!y && (y[0] !== 'neutral' || y[1] !== 'neutral');
  }
  // Yüz açıkken yeni boşta/tepki hareketi başlamaz (yüzün üstüne yazıyorlardı).
  function canliOtomatik() {
    if (!C.av) return;
    var etkin = yuzEtkin();
    C.av.setAutoMotion(!C.az && !etkin);
    C.av.setAutoIdle(!etkin);
  }
  function canliYuz(k) {
    if (!C.av) return;
    // Aynı duygu yeni bir olayla gelirse de yeniden oynar (anahtar = duygu + olay sayacı)
    var anahtar = k + '|' + S.olay;
    if (anahtar === C.yuzAnahtar) return;
    var y = YUZ[k] || YUZ.nod;
    var ayni = C.yuz === k && !C.yuzSondu;
    C.yuzAnahtar = anahtar;
    C.yuz = k; C.yuzSondu = false;
    clearTimeout(C.yuzT);
    if (!ayni) {
      C.av.setEmotion(y[0], { playMotion: !C.az });
      C.av.setExpression(y[1]);
      if (C.av.setKizgin) C.av.setKizgin(k === 'angry');
    }
    canliOtomatik();
    if (y[0] !== 'neutral' || y[1] !== 'neutral') {
      C.yuzT = setTimeout(function () {
        if (!C.av) return;
        C.av.setEmotion('neutral', { playMotion: false });
        C.av.setExpression('neutral');
        if (C.av.setKizgin) C.av.setKizgin(false);
        C.yuzSondu = true;
        canliOtomatik();
      }, YUZ_SURE);
    }
  }
  // Ağız: TTS analyser'ı (core.js playVoice yayınlar, ses bitince null) → RMS × 10, tavan 1.
  function canliSes() {
    C.raf = 0;
    if (!C.av) return;
    var an = window.YukiAudioBus && window.YukiAudioBus.tts;
    var v = 0;
    if (an && an.getFloatTimeDomainData) {
      var n = an.fftSize || 512;
      if (!C.buf || C.buf.length !== n) C.buf = new Float32Array(n);
      an.getFloatTimeDomainData(C.buf);
      var top = 0;
      for (var i = 0; i < n; i++) top += C.buf[i] * C.buf[i];
      v = Math.min(Math.sqrt(top / n) * 10, 1);
    }
    var konus = C.konusuyor || !!an;
    C.av.setSpeaking(konus);
    C.av.setVoiceLevel(konus ? v : 0);
    C.raf = requestAnimationFrame(canliSes);
  }
  window.addEventListener('yuki:speaking', function (e) {
    C.konusuyor = !!(e && e.detail && e.detail.on);
  });

  // ── görünüm (SOHBET mi?) ──
  function gorunumUygula() {
    var on = sohbetteMi();
    document.body.classList.toggle('sohbet-mode', on);
    var satir = document.getElementById('hizli-satir');
    // Durum satırı (model · dil · küçült) HALKA'da da görünür — kişisel Yuki'deki gibi (arayüz turu,
    // 2026-11-13). HALKA varsayılan açılış oldu; satır yalnız SOHBET'te kalsaydı ilk ekranda
    // model/dil seçimi ve "küçült" hiç görünmezdi (test_giris_konsol küçült'ü bulamıyordu).
    var halkada = false;
    try { halkada = !!window.getViewMode && window.getViewMode() === 'hud-ring'; } catch (_) { /* SOHBET'te kalır */ }
    if (satir) satir.hidden = !(on || halkada);
    kipUygula();
    ciz();
  }

  // ── WS kancaları (core.js çağırır) ──
  function duygu(e, veri) {
    veri = veri || {};
    if (veri.source === 'voice') return;   // KULLANICININ ses tonu — karakterin duygusu değil
    S.duygu = anahtar(e);
    S.olay++;
    ciz();
  }
  function durum(to) {
    var onceki = S.durum;
    S.durum = to || 'idle';
    // Yeni tur: kullanıcı yazdı/konuştu → önceki turun duygusu biter, DÜŞÜNÜYOR görünür
    if ((to === 'thinking' || to === 'listening') && onceki !== 'thinking' && onceki !== 'talking') S.duygu = 'nod';
    ciz();
  }
  function davranis(a) {
    if (a !== 'wave') return;
    S.el = Date.now() + 4000;
    S.olay++;
    ciz();
    setTimeout(ciz, 4100);
  }

  // ════ KISAYOL SATIRI ════
  function goster(id, acik) {
    var e = document.getElementById(id);
    if (e) e.hidden = !acik;
  }
  // Kapı: `/api/yetki` → `tools` (açık araç listesi).
  // Bilinmeyen = KAPALI. Pano ve aktarma yalnız tarayıcıda çalışır, araç istemez.
  var _yetkiNo = 0;
  async function hizliYetki() {
    var no = ++_yetkiNo;
    var d = null;
    try { d = window.ModeData ? await window.ModeData.getJSON('/api/yetki') : null; }
    catch (_) { d = null; }
    if (no !== _yetkiNo) return;              // arada yeni bir sorgu başladı
    var araclar = d && d.tools;
    var izin = function (arac) {
      return araclar === 'all' || (Array.isArray(araclar) && araclar.indexOf(arac) !== -1);
    };
    // 10-11: EKRAN çipi kalktı, eylem yalnız ⋯ menüsünde — kapı aynen burada.
    goster('menu-ekran', izin('take_screenshot') === true);
  }
  function hizliKur() {
    var pano = !!(navigator.clipboard && typeof navigator.clipboard.readText === 'function');
    goster('menu-pano', pano);              // eski PANO çipinin kapısı → ⋯ menüsündeki eşi
    hizliYetki();

    // Model/dil hapları ⋯ menüsündeki asıl düğmelerin vekili: etiketi oradan kopyala.
    // Asılları core.js yazıyor (_renderModelLabel · _applyLangUI); ikinci bir yazar
    // açmamak için onları İZLİYORUZ, aynı veriyi yeniden hesaplamıyoruz.
    var esle = function (kaynakId, hedefId) {
      var k = document.getElementById(kaynakId), h = document.getElementById(hedefId);
      if (!k || !h) return;
      var yaz = function () { h.textContent = k.textContent.trim(); };
      yaz();
      new MutationObserver(yaz).observe(k, { childList: true, characterData: true, subtree: true });
    };
    esle('model-label', 'hap-model-ad');
    esle('lang-label', 'hap-dil-ad');
    // Durum satırında dil KISA kodla görünür ("TR" — kişiselle birebir); tam ad
    // (#hap-dil-ad) ekran okuyucuda kalır. Kod konuşma dilinin anahtarından gelir,
    // anahtar henüz yoksa etiketin ilk iki harfi (açılış sorgusu dönmeden).
    var dilKod = function () {
      var h = document.getElementById('hap-dil-kod'), k = document.getElementById('lang-label');
      if (!h) return;
      var D = window.YukiDil, an = D && typeof D.konusma === 'function' ? D.konusma() : '';
      h.textContent = String(an || (k ? k.textContent.trim().slice(0, 2) : '')).slice(0, 3).toUpperCase();
    };
    dilKod();
    var lk = document.getElementById('lang-label');
    if (lk) new MutationObserver(dilKod).observe(lk, { childList: true, characterData: true, subtree: true });
    window.addEventListener('yuki-konusma-dili-degisti', dilKod);

    // Dar ekranda model adının KISA biçimi (tur 2, göz): "gemma-4-2…" gibi bir
    // kesik hiçbir şey söylemiyordu. Kısa biçim = sağlayıcı öneki ve ":free"
    // gibi ekler atılmış adın ilk iki parçası → aile + sürüm ("gemma-4",
    // "GPT-4.1", "llama-3.3"). Tam ad title'da ve ekran okuyucuda kalır
    // (kısa span aria-hidden, tam span yalnız görsel olarak gizlenir).
    var tam = document.getElementById('hap-model-ad');
    var kisa = document.getElementById('hap-model-kisa');
    var hapM = document.getElementById('hap-model');
    if (tam && kisa) {
      var kisalt = function () {
        var ad = tam.textContent.trim();
        var govde = ad.split('/').pop().replace(/:.*$/, '');
        var parca = govde.split(/[-_\s]+/).filter(Boolean);
        kisa.textContent = parca.length > 2 ? parca[0] + '-' + parca[1] : govde;
        if (hapM && !hapM.classList.contains('anahtar-yok')) hapM.title = _t('girdi.model-sec') + ' — ' + ad;
      };
      kisalt();
      new MutationObserver(kisalt).observe(tam, { childList: true, characterData: true, subtree: true });
    }

    // Anahtar yokken çip model listesini değil Ayar › Anahtar'ı açar: popovertarget geçici
    // olarak kaldırılır, anahtar gelince geri konur (tek kaynak: core.js yukiAnahtarHazir).
    var hapMod = document.getElementById('hap-model');
    if (hapMod) {
      var hedefPop = hapMod.getAttribute('popovertarget');
      var anahtarCiz = function () {
        var yok = typeof window.yukiAnahtarHazir === 'function' && window.yukiAnahtarHazir() === false;
        hapMod.classList.toggle('anahtar-yok', yok);
        if (yok) {
          hapMod.removeAttribute('popovertarget');
          hapMod.setAttribute('aria-haspopup', 'false');
          hapMod.title = _t('ust.anahtar-yok-ipucu');
        } else if (hedefPop) {
          hapMod.setAttribute('popovertarget', hedefPop);
          hapMod.setAttribute('aria-haspopup', 'dialog');
          var tamAd = document.getElementById('hap-model-ad');
          hapMod.title = _t('girdi.model-sec') + (tamAd ? ' — ' + tamAd.textContent.trim() : '');
        }
      };
      hapMod.addEventListener('click', function (e) {
        if (!hapMod.classList.contains('anahtar-yok')) return;
        e.preventDefault();
        if (typeof window.switchTab === 'function') window.switchTab('hq');
        if (typeof window.switchHqTab === 'function') window.switchHqTab('key');
      });
      window.addEventListener('yuki-anahtar-durum', anahtarCiz);
      anahtarCiz();
    }

    // Model hapı popover'ı doğrudan açar (popovertarget). core.js kapanışta odağı
    // menüdeki asıl tetiğe vermeye çalışır; menü kapalıyken o 0×0'dır ve odak
    // yazma alanına düşer. Hap açtıysa odak haba döner.
    var hap = document.getElementById('hap-model');
    var pop = document.getElementById('model-popover');
    if (hap && pop) {
      if (typeof pop.showPopover !== 'function') { hap.hidden = true; }   // S16: yarım menü yok
      var hapActi = false;
      hap.addEventListener('click', function () { hapActi = true; });
      pop.addEventListener('toggle', function (e) {
        var acik = e.newState === 'open';
        hap.setAttribute('aria-expanded', acik && hapActi ? 'true' : 'false');
        if (!acik && hapActi) {
          hapActi = false;
          var odak = document.activeElement;
          if (!odak || odak === document.body) hap.focus();   // msg-input'a tıklayıp kapatan kullanıcının odağını çalma (10-04)
        }
      });
    }

    // Giriş alanının yüksekliği → "aşağı git" düğmesi ve model listesi onun ÜSTÜNDE
    // dursun. Satır eklendi diye sabit sayıyı büyütmek kırılgan olurdu (dil, tema,
    // kip ve dar ekran yüksekliği değiştirir) — ölçülür.
    var giris = document.getElementById('input-area');
    var pane = document.getElementById('chat-pane');
    if (giris && pane && window.ResizeObserver) {
      // ⋯ menüsünün tavanı (10-11): menü giriş alanından YUKARI açılır ve
      // #chat-pane'in dışına taşan kısmı kırpılıyordu — dar kabukta sahne üstte olduğu
      // için Model · Fotoğraf · Galeri · Panodan yapıştır sahnenin ALTINDA kalıyor,
      // tıklama karakter şeridine gidiyordu (ölçüldü 390: menü üstü 104, sohbet sütunu 292).
      // PANO çipi kalkıp tek yolu menü olunca bu bir işlev kaybı oldu → menü sütuna sığar,
      // gerisi kaydırılır.
      var kap = document.getElementById('input-container');
      var olc = function () {
        var r = giris.getBoundingClientRect();
        pane.style.setProperty('--ss-giris-h', Math.round(r.height) + 'px');
        pane.style.setProperty('--ss-giris-alt', Math.round(window.innerHeight - r.top) + 'px');
        var ust = (kap || giris).getBoundingClientRect().top - pane.getBoundingClientRect().top;
        pane.style.setProperty('--ss-menu-tavan', Math.max(160, Math.round(ust - 12)) + 'px');
      };
      var ro = new ResizeObserver(olc);
      ro.observe(giris);
      ro.observe(pane);
    }
  }

  // ── init ──
  function init() {
    kur();
    hizliKur();
    gorunumUygula();
    document.addEventListener('viewmodechange', gorunumUygula);
    // Lisans girilince chat-modes kilitleri yeniden senkronlar ve bu olayı atar →
    // kısayol kapıları da aynı anda tazelensin (kademe değişmiş olabilir).
    document.addEventListener('yuki:karakter-kilitleri', hizliYetki);
    window.addEventListener('yuki-dil-degisti', function () {
      try { etiketleriYaz(); } catch (e) { console.warn('[sahne] dil tazeleme:', e); }
    });
    // Karakter değişince VİDEO anahtarı karakterin klibine göre görünsün/gizlensin.
    // chat-modes `_applyCharacter` `window.applyCharacterImage`ı çağırıyor —
    // imzayı koruyarak sarıyoruz (kişisel sohbet-sahne.js'le aynı desen).
    var eski = window.applyCharacterImage;
    if (typeof eski === 'function' && !eski._ssSarili) {
      var sar = function () { var r = eski.apply(this, arguments); try { kipUygula(); } catch (_) {} return r; };
      sar._ssSarili = true;
      window.applyCharacterImage = sar;
    }
    // Hareket azaltma tercihi oturum içinde değişirse klip kararı da değişir.
    try {
      var mq = window.matchMedia('(prefers-reduced-motion: reduce)');
      if (mq.addEventListener) mq.addEventListener('change', function () { kipUygula(); canliHareket(); });
    } catch (_) {}
    // Grafik kademesi değişince CANLI kapısı yeniden değerlenir (HAFİF → motor kapanır).
    document.addEventListener('gfxchange', kipUygula);
    // Sahne Küçük/Gizli'ye inince motor boşa çizmesin.
    var app = document.getElementById('app');
    if (app && window.MutationObserver) {
      new MutationObserver(canliEsitle).observe(app, { attributes: true, attributeFilter: ['data-avatar-etkin'] });
    }
  }

  window.SohbetSahne = {
    duygu: duygu, durum: durum, davranis: davranis,
    kip: kip, ciz: ciz, anahtar: anahtar,
    // Salt okuma — test ve teşhis için
    durumOku: function () {
      return { kip: S.kip, etkinKip: etkinKip(), klip: klipVar(), canli: canli(), durum: S.durum,
               secenekler: secenekler(), canliMotor: !!C.av, canliHata: C.hata };
    },
    // Test/teşhis: canlı motorun anlık parametreleri (ağız açıklığı dahil)
    canliOku: function () {
      if (!C.av) return null;
      var p = C.av.getParameters();
      return { mouthOpen: p.mouthOpen, eyeROpen: p.eyeROpen, konusuyor: C.konusuyor, az: C.az,
               yuz: C.yuz, yuzSondu: C.yuzSondu, ifade: C.av.getExpression().name };
    },
  };

  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', init);
  else init();
})();
