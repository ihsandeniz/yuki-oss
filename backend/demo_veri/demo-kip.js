/* Yuki demo kipi (YUKI_DEMO=1) — arka uç her HTML sayfasının <head>'ine ekler.
   Konumu İstanbul merkeze sabitler: tarayıcının konum sorusu gerçek konumu
   istemez, IP'den konum bulan servislere hiç istek gitmez. Kaynak: app/demo_kip.py */
(function () {
  'use strict';
  var LAT = __LAT__, LON = __LON__;
  window.YUKI_DEMO = true;
  function konum() {
    return { coords: { latitude: LAT, longitude: LON, accuracy: 50, altitude: null,
      altitudeAccuracy: null, heading: null, speed: null }, timestamp: Date.now() };
  }
  var sahte = {
    getCurrentPosition: function (ok) { setTimeout(function () { ok && ok(konum()); }, 0); },
    watchPosition: function (ok) { setTimeout(function () { ok && ok(konum()); }, 0); return 1; },
    clearWatch: function () {}
  };
  try { Object.defineProperty(navigator, 'geolocation', { configurable: true, get: function () { return sahte; } }); } catch (e) {}

  var IP_KONUM = /^(?:[a-z0-9-]+\.)*(?:ipapi\.co|ip-api\.com|ipinfo\.io|ipwho\.is|ipify\.org|icanhazip\.com|ifconfig\.me|freegeoip\.app|geojs\.io|ipgeolocation\.io|geoplugin\.net|db-ip\.com|extreme-ip-lookup\.com)$/i;
  function ipKonumMu(u) {
    try { return IP_KONUM.test(new URL(String(u && u.url ? u.url : u), location.href).hostname); }
    catch (e) { return false; }
  }
  var CEVAP = JSON.stringify({ ip: '203.0.113.10', city: 'İstanbul', country_name: 'Türkiye',
    country_code: 'TR', latitude: LAT, longitude: LON, lat: LAT, lon: LON, demo: true });
  var asilFetch = window.fetch;
  if (asilFetch) {
    window.fetch = function (girdi, ayar) {
      if (ipKonumMu(girdi)) {
        return Promise.resolve(new Response(CEVAP, { status: 200, headers: { 'Content-Type': 'application/json' } }));
      }
      return asilFetch.call(this, girdi, ayar);
    };
  }
  var asilAc = XMLHttpRequest.prototype.open;
  XMLHttpRequest.prototype.open = function (yontem, url) {
    if (ipKonumMu(url)) {
      arguments[1] = 'data:application/json,' + encodeURIComponent(CEVAP);
    }
    return asilAc.apply(this, arguments);
  };
})();
