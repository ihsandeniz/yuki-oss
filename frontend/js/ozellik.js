/* ══════════════════════════════════════════════════════════════════
   ÖZELLİK KAPISI — bayraklı özelliklerin ön yüz girişleri (Atölye, Fitnes)
   İlk sürümde üçü de kapalıydı (karar 2026-11-01). g4 (2026-11-12): Atölye sunucuda
   varsayılan AÇIK, Fitnes KAPALI (HQ › Sistem anahtarı; kaydedince intro-sequences tazele() çağırır).
   Ön yüz yine fail-closed: sunucu açıkça "açık" demedikçe giriş görünmez.

     atolye          GET /api/gorev 2xx → açık. 404 (`ATOLYE=false`, arka uç kapısı
                     `api/gorev.atolye_kapisi`) ya da ağ/yetki hatası → kapalı.
     fitnes          GET /api/yetki → features.fitnes === true
   Komuta kanvası 2026-11-13'te ön ve arka uçtan tamamen silindi; kapıda adı da yok.

   Girişler `data-ozellik="<ad>"` ile işaretlenir; bu dosyanın eklediği stil, kökte
   `data-oz-<ad>="acik"` yoksa onları gizler. `hidden` kullanılmaz: tab-nav başka
   sekme düğmelerini `hidden=false` yaparak açıyor, öznitelik onu ezer.
   Senkron, <head>'de, girişlerden ÖNCE yüklenir → kapalı giriş bir kare bile görünmez.
   API: YukiOzellik.acik(ad) · .hazir (Promise) · .tazele() · olay `yuki:ozellik`
   Bekçi: frontend/tests/test_ozellik_kapisi.py
   ══════════════════════════════════════════════════════════════════ */
(function () {
  'use strict';

  var ADLAR = ['atolye', 'fitnes'];
  var durum = { atolye: false, fitnes: false };
  var kok = document.documentElement;

  var st = document.createElement('style');
  st.id = 'yuki-ozellik-kapisi';
  st.textContent = ADLAR.map(function (ad) {
    return 'html:not([data-oz-' + ad + '="acik"]) [data-ozellik="' + ad + '"]{display:none!important}';
  }).join('');
  (document.head || kok).appendChild(st);

  function _token() {
    try { return sessionStorage.getItem('aliceToken') || localStorage.getItem('aliceToken') || ''; }
    catch (_) { return ''; }
  }
  function _istek(yol) {
    var t = _token();
    return fetch(yol, t ? { headers: { Authorization: 'Bearer ' + t } } : {});
  }

  function _yaz(yeni) {
    var degisti = false;
    ADLAR.forEach(function (ad) {
      var v = yeni[ad] === true;
      if (v !== durum[ad]) degisti = true;
      durum[ad] = v;
      if (v) kok.setAttribute('data-oz-' + ad, 'acik');
      else kok.removeAttribute('data-oz-' + ad);
    });
    if (degisti) {
      try { document.dispatchEvent(new CustomEvent('yuki:ozellik', { detail: acikKopya() })); } catch (_) {}
    }
  }
  function acikKopya() { var k = {}; ADLAR.forEach(function (a) { k[a] = durum[a]; }); return k; }

  function tazele() {
    var atolye = _istek('/api/gorev').then(function (r) { return r.ok; }, function () { return false; });
    var yetki = _istek('/api/yetki').then(function (r) { return r.ok ? r.json() : null; })
      .then(function (d) { return (d && d.features) || {}; }, function () { return {}; });
    return Promise.all([atolye, yetki]).then(function (s) {
      _yaz({ atolye: s[0] === true, fitnes: s[1].fitnes === true });
      return acikKopya();
    });
  }

  var hazir = tazele();
  // Token girişten sonra gelir: bağlantı kurulunca bir kez daha sor (ilk sorgu 401 almış olabilir).
  window.addEventListener('yuki-baglanti', function (e) {
    if (e && e.detail && e.detail.bagli) tazele();
  });

  window.YukiOzellik = {
    acik: function (ad) { return durum[ad] === true; },
    hazir: hazir,
    tazele: function () { var p = tazele(); window.YukiOzellik.hazir = p; return p; },
  };
})();
