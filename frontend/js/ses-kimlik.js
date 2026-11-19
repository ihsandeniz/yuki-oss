/* Ses kimliği — mikrofondan kısa kayıt al (sunucu: backend/app/api/ses_kimlik_api.py).
   Kayıt yalnız bellekte (Blob) tutulur ve doğrudan bu bilgisayardaki sunucuya yüklenir;
   sunucu sesi saklamaz, yalnız ses izini (gömme) yazar. Mikrofon kayıt bitince kapanır.
   API: YukiSesKimlikApi.kaydet(sn, o) → Promise<Blob> · CUMLELER (okunacak metinler) */
(function (kok) {
  'use strict';

  var CUMLELER = [
    'Bugün hava güzel, biraz yürüyüşe çıkmayı düşünüyorum.',
    'Yuki, akşam yedide bana toplantıyı hatırlatır mısın?',
    'Kahvemi şekersiz içerim, yanında da bir bardak su.',
    'Bu kayıt yalnız benim sesimi tanıman için.',
  ];
  var KLIP_SN = 5;

  function kaydet(sn, o) {
    o = o || {};
    var md = o.mediaDevices || (kok.navigator && kok.navigator.mediaDevices);
    var MR = o.MediaRecorder || kok.MediaRecorder;
    var zamanla = o.zamanla || function (f, ms) { return setTimeout(f, ms); };
    if (!md || !md.getUserMedia || !MR) return Promise.reject(new Error('mikrofon-yok'));
    return md.getUserMedia({ audio: { echoCancellation: true, noiseSuppression: true }, video: false }).then(function (akis) {
      return new Promise(function (coz, reddet) {
        var parcalar = [];
        var kayit;
        function kapat() { akis.getTracks().forEach(function (t) { try { t.stop(); } catch (e) { /* */ } }); }
        try { kayit = new MR(akis); } catch (e) { kapat(); reddet(e); return; }
        kayit.ondataavailable = function (e) { if (e.data && e.data.size) parcalar.push(e.data); };
        kayit.onstop = function () {
          kapat();
          var tur = kayit.mimeType || 'audio/webm';
          coz(new kok.Blob(parcalar, { type: tur }));
          parcalar = [];
        };
        kayit.onerror = function (e) { kapat(); reddet(e.error || e); };
        kayit.start();
        zamanla(function () { if (kayit.state !== 'inactive') kayit.stop(); }, Math.round((sn || KLIP_SN) * 1000));
      });
    });
  }

  var api = { kaydet: kaydet, CUMLELER: CUMLELER, KLIP_SN: KLIP_SN };
  if (typeof module !== 'undefined' && module.exports) module.exports = api;
  else kok.YukiSesKimlikApi = api;
})(typeof window !== 'undefined' ? window : this);
