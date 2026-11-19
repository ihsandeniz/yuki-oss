/* ════════════════════════════════════════════════════════════════════
   giris-konsol.js — Halka Konsolu yazı çubuğunun küçültme hâli (2026-10-11)

   Kişisel AliceAi 933779b'nin "Halka Konsolu"ndan ürüne çevrildi.
   Görünüm css/giris-konsol.css'te; burada yalnız DURUM:
     · #input-area.kucuk → yazı hapı + kısayol satırı gizli, mikrofon + YAZ kalır
       (sesle konuşan kullanıcıya sohbet alanı açılır)
     · kalıcı: localStorage `giris_kucuk_v1` ('1' / '0')
     · "/" kısayolu core.js'te → window.GirisKonsol.ac()

   🔑 Ürün kişiseldeki araç YAYINI almadı: ⋯ menüsü etiketli kalır (2026-08-03
   kararı: etiketsiz ikon kümesi kaldırılmıştı — yay o sınıfa geri dönerdi).

   Metin yok: etiketler index.html'de data-i18n ile, dil.js çevirir.
   ════════════════════════════════════════════════════════════════════ */
(function () {
  'use strict';
  if (new URLSearchParams(location.search).has('widget')) return;

  var ANAHTAR = 'giris_kucuk_v1';

  // Çeviri yardımcısı — ad dosyaya özel (klasik script'te `_t` window'u ezer).
  function _gkt(anahtar, degerler) {
    return (window.YukiDil && window.YukiDil.t) ? window.YukiDil.t(anahtar, degerler) : String(anahtar);
  }

  function alan() { return document.getElementById('input-area'); }
  function kucukMu() { var a = alan(); return !!(a && a.classList.contains('kucuk')); }

  function uygula(k) {
    var a = alan();
    if (!a) return;
    a.classList.toggle('kucuk', k);
    var ac = document.getElementById('giris-ac');
    if (ac) ac.hidden = !k;
    var kb = document.getElementById('giris-kucult');
    if (kb) kb.title = _gkt('girdi.kucult');
  }

  function kucult(k) {
    k = !!k;
    try { localStorage.setItem(ANAHTAR, k ? '1' : '0'); } catch (_) {}
    uygula(k);
    // Odak kaybolmasın: küçülünce YAZ düğmesine, açılınca yazı alanına.
    var hedef = document.getElementById(k ? 'giris-ac' : 'msg-input');
    if (hedef) hedef.focus();
  }

  window.girisKucult = kucult;
  window.GirisKonsol = {
    ac: function () { if (kucukMu()) kucult(false); },
    kucukMu: kucukMu,
  };

  function init() {
    var k = false;
    try { k = localStorage.getItem(ANAHTAR) === '1'; } catch (_) {}
    uygula(k);
    window.addEventListener('yuki-dil-degisti', function () { uygula(kucukMu()); });
  }

  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', init);
  else init();
})();
