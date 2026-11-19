/* Kamera görüşü — kamera istemcisi (sunucu: backend/app/api/gorus_api.py).
   Saniyede ≤1 kare: kamera → kanvas (≤640) → JPEG → /ws/gorus. Sunucu cevabını beklemeden yeni
   kare yollanmaz (geri basınç).
   Gizlilik: kare yalnız bellekte. Video öğesi DOM'a eklenmez, kare ekrana çizilmez, diske ya da
   localStorage'a yazılmaz. Sekme 10 sn'den uzun gizli kalırsa kamera kapanır (kullanılmayan
   kamera tutulmaz). Sunucu rızayı geri çekilmiş bulursa (4409) kamera hemen kapanır.
   Cevapta `soyle` varsa (selam / mola cümlesi) `soyle(metin)` çağrılır; varsayılanı Yuki'nin
   ses motoruyla (/api/tts/test) çalar.
   API: YukiGorusApi.GorusOlustur(o) → { baslat, durdur, durum } · Test: frontend/tests/test_gorus.mjs */
(function (kok) {
  'use strict';

  var ARALIK_MS = 1000;
  var EN_BUYUK = 640;
  var KALITE = 0.7;
  var GIZLI_SINIR_MS = 10000;
  var KAPANIS = { 4401: 'yetki', 4403: 'yerel', 4404: 'kapali', 4409: 'riza', 4003: 'koken' };

  function jetonAl() {
    try { return (kok.sessionStorage && kok.sessionStorage.getItem('aliceToken')) ||
                 (kok.localStorage && kok.localStorage.getItem('aliceToken')) || ''; }
    catch (e) { return ''; }
  }

  function varsayilanSoyle(metin) {
    var t = jetonAl();
    var h = { 'Content-Type': 'application/json' };
    if (t) h.Authorization = 'Bearer ' + t;
    return kok.fetch('/api/tts/test', { method: 'POST', headers: h, body: JSON.stringify({ text: String(metin).slice(0, 300) }) })
      .then(function (r) { return r.ok ? r.json() : null; })
      .then(function (d) {
        if (!d || !d.audio_base64) return;
        var a = new kok.Audio('data:audio/' + (d.format === 'wav' ? 'wav' : 'mpeg') + ';base64,' + d.audio_base64);
        var p = a.play(); if (p && p.catch) p.catch(function () { /* otomatik çalma engeli */ });
      }, function () { /* ses yoksa sessiz geç */ });
  }

  function GorusOlustur(o) {
    o = o || {};
    var md = o.mediaDevices || (kok.navigator && kok.navigator.mediaDevices);
    var belge = o.belge || kok.document;
    var zamanla = o.zamanla || function (f, ms) { return setTimeout(f, ms); };
    var iptal = o.iptal || clearTimeout;
    var aralik = o.aralikMs || ARALIK_MS;
    var wsAc = o.wsAc || function (url) { return new WebSocket(url); };
    var dinle = o.dinle || function () {};
    var soyle = o.soyle || varsayilanSoyle;
    var d = { durum: 'kapali', son: null, gonderilen: 0, neden: '' };
    var akis = null, ws = null, video = null, kanvas = null, saat = null, bekliyor = false, gizliMs = 0;

    function url() {
      var konum = o.konum || kok.location;
      var jeton = o.jeton != null ? o.jeton : jetonAl();
      var sema = konum.protocol === 'https:' ? 'wss:' : 'ws:';
      return sema + '//' + konum.host + '/ws/gorus' + (jeton ? '?token=' + encodeURIComponent(jeton) : '');
    }

    function bildir(m) { try { dinle(m); } catch (e) { /* dinleyici hatası akışı durdurmasın */ } }

    function planla() { if (!saat) saat = zamanla(kareAl, aralik); }

    function kareAl() {
      saat = null;
      if (d.durum !== 'acik') return;
      if (belge.hidden) {
        gizliMs += aralik;
        if (gizliMs >= GIZLI_SINIR_MS) { durdur('gizli'); return; }
        planla(); return;
      }
      gizliMs = 0;
      planla();
      if (!ws || ws.readyState !== 1 || bekliyor || !video) return;
      var g = video.videoWidth, y = video.videoHeight;
      if (!g || !y) return;
      var oran = Math.min(1, EN_BUYUK / Math.max(g, y));
      if (!kanvas) kanvas = belge.createElement('canvas');
      kanvas.width = Math.round(g * oran); kanvas.height = Math.round(y * oran);
      kanvas.getContext('2d').drawImage(video, 0, 0, kanvas.width, kanvas.height);
      bekliyor = true;
      kanvas.toBlob(function (b) {
        if (!b || d.durum !== 'acik' || !ws || ws.readyState !== 1) { bekliyor = false; return; }
        ws.send(b); d.gonderilen++;
      }, 'image/jpeg', KALITE);
    }

    function wsKur() {
      ws = wsAc(url());
      ws.binaryType = 'arraybuffer';
      ws.onmessage = function (ev) {
        bekliyor = false;
        var m = null; try { m = JSON.parse(ev.data); } catch (e) { return; }
        d.son = m;
        if (m && typeof m.soyle === 'string' && m.soyle) { try { soyle(m.soyle); } catch (e) { /* */ } }
        bildir(m);
      };
      ws.onclose = function (ev) {
        ws = null; bekliyor = false;
        if (d.durum !== 'kapali') durdur(KAPANIS[ev && ev.code] || ('ws:' + (ev && ev.code)));
      };
    }

    function baslat() {
      if (d.durum !== 'kapali') return Promise.resolve(d);
      if (!md || !md.getUserMedia) { d.neden = 'kamera-yok'; return Promise.reject(new Error('kamera-yok')); }
      d.durum = 'aciliyor'; d.neden = ''; gizliMs = 0;
      bildir({ tip: 'durum-degisti', durum: d.durum });
      return md.getUserMedia({ video: { width: 640, height: 480 }, audio: false }).then(function (s) {
        if (d.durum !== 'aciliyor') { s.getTracks().forEach(function (t) { t.stop(); }); return d; }
        akis = s;
        video = belge.createElement('video');
        video.muted = true; video.playsInline = true; video.srcObject = s;
        var p = video.play && video.play(); if (p && p.catch) p.catch(function () { /* */ });
        wsKur();
        d.durum = 'acik'; planla();
        bildir({ tip: 'durum-degisti', durum: d.durum });
        return d;
      }, function (e) {
        d.durum = 'kapali'; d.neden = (e && e.name === 'NotAllowedError') ? 'izin-yok' : 'kamera-acilamadi';
        bildir({ tip: 'durum-degisti', durum: d.durum, neden: d.neden });
        throw e;
      });
    }

    function durdur(neden) {
      var onceki = d.durum;
      d.durum = 'kapali';
      if (typeof neden === 'string') d.neden = neden;
      if (saat) { iptal(saat); saat = null; }
      if (akis) { akis.getTracks().forEach(function (t) { try { t.stop(); } catch (e) { /* */ } }); akis = null; }
      if (video) { video.srcObject = null; video = null; }
      if (ws) { var w = ws; ws = null; try { w.close(); } catch (e) { /* */ } }
      bekliyor = false;
      if (onceki !== 'kapali') bildir({ tip: 'durum-degisti', durum: 'kapali', neden: d.neden });
      return onceki;
    }

    return { baslat: baslat, durdur: function () { return durdur('kullanici'); }, durum: function () { return d; } };
  }

  var api = { GorusOlustur: GorusOlustur, ARALIK_MS: ARALIK_MS, GIZLI_SINIR_MS: GIZLI_SINIR_MS, KAPANIS: KAPANIS };
  if (typeof module !== 'undefined' && module.exports) module.exports = api;
  else kok.YukiGorusApi = api;
})(typeof window !== 'undefined' ? window : this);
