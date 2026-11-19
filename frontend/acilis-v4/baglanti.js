/* ════════════════════════════════════════════════════════════════
   Açılış v4 → uygulama bağlantısı (⑤ Mühür + Döküm)
   core.js açılışı yalnız window._runOpeningAnimation() ile çağırır
   (_hideAuthScreen ve _runBootAnimation sonrası). Bu dosya o adı devralır;
   core.js'e dokunmak gerekmez.

     <link rel="stylesheet" href="/ui/acilis-v4/ortak/ortak.css?v=1">
     <link rel="stylesheet" href="/ui/acilis-v4/muhur-dokum/acilis.css?v=1">
     <script src="/ui/acilis-v4/ortak/veri.js?v=1"></script>
     <script src="/ui/acilis-v4/ortak/motor.js?v=1"></script>
     <script src="/ui/acilis-v4/muhur-dokum/acilis.js?v=1"></script>
     <script src="/ui/acilis-v4/baglanti.js?v=1" data-sahne="muhur-dokum"></script>

   Kurallar:
   · Oturum başına BİR kez oynar (sessionStorage 'yukiAcilis_v1'); yeniden
     girişte / ikinci çağrıda oynamaz.
   · Widget gömme modunda (?widget=1 → html.widget-embed) OYNAMAZ.
   · prefers-reduced-motion (ya da ?azalt=1) → hiç oynamaz (motor.js), uygulama hemen açılır.
   · Katman #yuki-opening KABUĞUNUN içinde oynar: ön yüz testleri ve widget betiği
     açılışı '#yuki-opening'i gizleyerek geçer; kabuk gizlenince açılış da görünmez,
     tıklamayı yutmaz. Açılış bitince kabuk kalkar.
   · #app'in `hidden` özniteliğine dokunmaz (görünürlük switchTab'ındır).
   ════════════════════════════════════════════════════════════════ */
(function () {
  'use strict';
  var betik = document.currentScript;
  var SAHNE = (betik && betik.getAttribute('data-sahne')) || 'muhur-dokum';
  var BAYRAK = 'yukiAcilis_v1';

  function kabukKaldir() {
    var k = document.getElementById('yuki-opening');
    if (k && k.parentNode && !k.firstChild) k.parentNode.removeChild(k);
  }

  window._runOpeningAnimation = function () {
    var app = document.getElementById('app');
    var gomulu = document.documentElement.classList.contains('widget-embed');
    var oynadi = false;
    try {
      oynadi = !!sessionStorage.getItem(BAYRAK);
      if (!oynadi) sessionStorage.setItem(BAYRAK, '1');
    } catch (e) { /* depolama yok → yine de bir kez oyna */ }

    if (gomulu || oynadi || !window.YukiAcilis) {
      if (app) app.style.display = '';
      window.__acilisDurum = gomulu ? 'gomulu' : oynadi ? 'oynadi' : 'motor-yok';
      kabukKaldir();
      return;
    }
    var kabuk = document.getElementById('yuki-opening');
    if (!kabuk) {
      kabuk = document.createElement('div');
      kabuk.id = 'yuki-opening';
      document.body.appendChild(kabuk);
    }
    window.YukiAcilis.baslat(SAHNE, { app: app, kap: kabuk, onBitti: kabukKaldir });
  };
})();
