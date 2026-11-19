/* ============================================================================
   YUKI · MİNİ HUD KÖPRÜSÜ — ana pencere tarafı  (2026-10-04)

   Ana penceredeki durumu Mini HUD kartına taşır ve menüdeki iki satırı
   (GÖRÜNÜM › PENCERE: "Mini HUD" · "Yalnız Mini HUD") çalıştırır.

   ── Veri: yeni bağlantı YOK ─────────────────────────────────────────────
   Hepsi zaten var olan yüzeylerden OKUNUR, hiçbiri yeniden üretilmez:
     · durum      → core.js `updateState()`'in yaydığı `yuki-state` olayı
                    (WS `state` mesajının kendisi)
     · duygu      → sohbet sahnesinin etiketi `#ss-duygu[data-duygu]`
                    (modes/sohbet-sahne.js — WS `emotion`/`behavior`)
     · son mesaj  → `#messages` içindeki son Yuki balonu
     · mikrofon   → `#mic-btn.recording` ve `#always-on-btn.active`
   🔴 getUserMedia / AudioContext / WebSocket bu dosyada GEÇMEZ.
   ⚠️ Duygu ve son mesaj DOM'dan okunur: seçici değişirse o iki alan sessizce
   boş kalır, kart çalışmaya devam eder (durum ayrı yoldan gelir).

   ── Kademe kapısı YOK ───────────────────────────────────────────────────
   Mini HUD herkese açık.

   Electron dışında (tarayıcı/PWA) `yukiMiniHud` yoktur: satırlar gizli kalır,
   dosya hiçbir şey yapmaz.
   ============================================================================ */
(function () {
  'use strict';

  function _mkt(anahtar, degerler) {
    return (window.YukiDil && window.YukiDil.t)
      ? window.YukiDil.t(anahtar, degerler) : String(anahtar);
  }

  var api = window.yukiMiniHud;
  var satirlar = document.getElementById('mini-hud-satirlari');
  if (!api || typeof api.durum !== 'function') {
    if (satirlar) satirlar.hidden = true;
    return;
  }

  var son = { durum: 'idle', detay: '', duygu: '' };

  function yolla() {
    try { api.durum(son.durum, son.detay, son.duygu); } catch (e) { console.warn('[mini-hud] durum yollanamadı:', e); }
  }

  document.addEventListener('yuki-state', function (ev) {
    var s = ev && ev.detail && ev.detail.state;
    if (typeof s !== 'string') return;
    // core.js'in dört durumu dışındakiler ("busy" vb.) kartta "düşünüyor"dur.
    son.durum = /^(idle|listening|thinking|talking)$/.test(s) ? s : 'thinking';
    duyguBagla();   // sahne `defer` yüklenir — etiket ilk turda henüz olmayabilir
    yolla();
  });

  /* ── Duygu: sahne etiketinin data-duygu'su ── */
  var duyguGozcu = null;
  function duyguBagla() {
    var el = document.getElementById('ss-duygu');
    if (!el || duyguGozcu) return !!el;
    var oku = function () {
      var k = el.getAttribute('data-duygu') || '';
      if (k !== son.duygu) { son.duygu = k; yolla(); }
    };
    duyguGozcu = new MutationObserver(oku);
    duyguGozcu.observe(el, { attributes: true, attributeFilter: ['data-duygu'] });
    oku();
    return true;
  }

  /* ── Son Yuki mesajı ── */
  function kisalt(t) {
    t = (t || '').replace(/\s+/g, ' ').trim();
    return t.length > 90 ? t.slice(0, 89).replace(/[\s.,;:!?·…-]+$/, '') + '…' : t;
  }
  var mesajlar = document.getElementById('messages');
  if (mesajlar && 'MutationObserver' in window) {
    new MutationObserver(function () {
      var balonlar = mesajlar.querySelectorAll('.msg-row.yuki .msg-bubble');
      if (!balonlar.length) return;
      var b = balonlar[balonlar.length - 1];
      if (b.classList.contains('thinking-indicator')) return;
      var metin = kisalt(b.textContent);
      if (metin && metin !== son.detay) { son.detay = metin; yolla(); }
    }).observe(mesajlar, { childList: true, subtree: true, characterData: true });
  }

  /* ── Mikrofon: durum yayını + karttan gelen komut ──
     isRecording/alwaysOnMode core.js'te yerel; ikisi de DOM'a yansıyor.
     Komut düğmeye TIKLAYARAK uygulanır → core.js'in kendi yolu (izin, VAD,
     wake-word) aynen çalışır, karar ana pencerede kalır. */
  var micBtn = document.getElementById('mic-btn');
  var dinleBtn = document.getElementById('always-on-btn');
  var sonMic = null;
  function micYayinla(zorla) {
    var p = {
      kayit: !!(micBtn && micBtn.classList.contains('recording')),
      dinle: !!(dinleBtn && dinleBtn.classList.contains('active')),
      dinleVar: !!dinleBtn,
    };
    var imza = p.kayit + '|' + p.dinle + '|' + p.dinleVar;
    if (imza === sonMic && zorla !== true) return;
    sonMic = imza;
    try { api.mic(p); } catch (_) {}
  }
  if ('MutationObserver' in window) {
    var micGozcu = new MutationObserver(micYayinla);
    if (micBtn) micGozcu.observe(micBtn, { attributes: true, attributeFilter: ['class'] });
    if (dinleBtn) micGozcu.observe(dinleBtn, { attributes: true, attributeFilter: ['class'] });
  }
  if (typeof api.komut === 'function') {
    api.komut(function (ad) {
      if (ad === 'mikrofon' && micBtn) micBtn.click();
      else if (ad === 'her-zaman-dinle' && dinleBtn) dinleBtn.click();
    });
  }

  // Kart yeni açıldı → ilk durum değişimini beklemeden mevcut hâli yolla.
  if (typeof api.durumIste === 'function') {
    api.durumIste(function () { duyguBagla(); yolla(); micYayinla(true); });
  }

  /* ── Menü satırları (GÖRÜNÜM › PENCERE) ─────────────────────────────────
     Markup index.html `#mini-hud-satirlari` içinde, `#pencere-mod-kaynak`'ın
     çocuğu: chat-modes.js PENCERE bölümünü kurarken onu da menüye TAŞIR,
     dinleyiciler düğümle birlikte gider. Bölüm yalnız Electron'da çizilir
     (`data-pencere-destek`), bu satırlar da yalnız köprü varken görünür. */
  if (!satirlar) return;
  var acKapat = document.getElementById('mini-hud-ac-kapat');
  var yalniz = document.getElementById('mini-hud-yalniz');
  var acik = false;

  function satirYaz() {
    if (!acKapat) return;
    var b = acKapat.querySelector('b');
    var s = acKapat.querySelector('small');
    // Metin gerçeği söyler: kart açıkken "göster" yazıp kapatmak sessiz yalan olurdu.
    if (b) b.textContent = _mkt(acik ? 'mini-hud.menu.kapat' : 'mini-hud.menu.ac');
    if (s) s.textContent = _mkt(acik ? 'mini-hud.menu.kapat-alt' : 'mini-hud.menu.ac-alt');
    acKapat.classList.toggle('active', acik);
    acKapat.setAttribute('aria-pressed', acik ? 'true' : 'false');
  }
  function tazele() {
    if (typeof api.acikMi !== 'function') return;
    Promise.resolve(api.acikMi()).then(function (a) { acik = !!a; satirYaz(); })
      .catch(function (e) { console.warn('[mini-hud] durum okunamadı:', e); });
  }
  function menuyuKapat() {
    var m = document.getElementById('view-mode-menu');
    if (m) m.classList.remove('open');   // chat-modes.js `_closeMenu` dışarıdan erişilemez
  }

  if (acKapat) acKapat.addEventListener('click', function () { menuyuKapat(); api.acKapat(); });
  if (yalniz) yalniz.addEventListener('click', function () { menuyuKapat(); api.yalniz(); });
  if (typeof api.degisti === 'function') {
    api.degisti(function (a) { acik = !!a; satirYaz(); if (acik) duyguBagla(); });
  }
  window.addEventListener('yuki-dil-degisti', satirYaz);

  satirlar.hidden = false;
  satirYaz();
  tazele();
  duyguBagla();
  micYayinla(true);
})();
