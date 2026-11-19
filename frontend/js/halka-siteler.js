/* ════════════════════════════════════════════════════════════════════
   halka-siteler.js — Odaklı Halka SİTELER grubunun deposu (2026-10-11)

   Müşterinin kendi site kısayolları: ekle · sil · aç. Sunucuya hiçbir şey gitmez,
   liste yalnız bu cihazda (localStorage `yuki_halka_siteler_v1`).

   🔑 Açılış HER ZAMAN sistem tarayıcısında (kişiselde iframe sekmesiydi):
     · Ürünün kuralı: uygulama penceresi yalnız kendi arayüzünü gösterir —
       electron/dis-baglanti.js `window.open`'ı reddedip `openExternal`'a verir.
     · CSP `frame-src` yalnız self + localhost; iframe için genişletmek gerekirdi.
     · Ölçüldü (10-11): 14 popüler sitenin 12'si gömülmeyi başlıkla reddediyor
       (X-Frame-Options / frame-ancestors) — iframe çoğu sitede boş kutu olurdu.
   🔴 Adres kapısı `dogrula` TEK yerde ve üç kez uygulanır: eklerken, depodan
      okurken (elle bozulmuş localStorage'a karşı) ve açmadan hemen önce.
      Yalnız http/https; javascript:, data:, file:, blob:, kullanıcı:parola@ reddedilir.
   ════════════════════════════════════════════════════════════════════ */
(function () {
  'use strict';

  var ANAHTAR = 'yuki_halka_siteler_v1';
  // Halkada en çok 8 düğüm: 7 site + TÜM SİTELER (6 sitede + SİTE EKLE). 8 sitede (9 düğüm)
  // 390'da TÜM SİTELER etiketi komşu düğüme biniyordu (ölçüldü, test_halka_siteler.py).
  var MAKS = 7;
  var AD_MAKS = 24;
  var ADRES_MAKS = 2048;

  // Şemasız girdi ("youtube.com", "localhost:8080") → https:// varsayılır.
  // "javascript:alert(1)" gibi ŞEMALI girdi şemasız sanılmamalı: iki nokta
  // sonrası yalnız rakam (port) ise ana makine sayılır, değilse şemadır.
  function dogrula(girdi) {
    var s = String(girdi == null ? '' : girdi).trim();
    if (!s) return { ok: false, hata: 'bos' };
    if (s.length > ADRES_MAKS) return { ok: false, hata: 'uzun' };
    if (/[\u0000- \u007f-\u009f]/.test(s)) return { ok: false, hata: 'gecersiz' };
    if (!/^[a-z][a-z0-9+.\-]*:\/\//i.test(s)) {
      var sema = /^([a-z][a-z0-9+.\-]*):(.*)$/i.exec(s);
      if (sema && !/^\d+(?:[\/?#]|$)/.test(sema[2])) return { ok: false, hata: 'sema' };
      if (s.indexOf('//') === 0) return { ok: false, hata: 'gecersiz' };
      s = 'https://' + s;
    }
    var u;
    try { u = new URL(s); } catch (_) { return { ok: false, hata: 'gecersiz' }; }
    if (u.protocol !== 'http:' && u.protocol !== 'https:') return { ok: false, hata: 'sema' };
    if (u.username || u.password) return { ok: false, hata: 'kimlik' };
    var host = u.hostname;
    if (!host) return { ok: false, hata: 'gecersiz' };
    // "youtube" gibi noktasız ad çoğunlukla yazım hatası; localhost ve IPv6 hariç
    if (host.indexOf('.') === -1 && host !== 'localhost' && host.charAt(0) !== '[') return { ok: false, hata: 'gecersiz' };
    return { ok: true, url: u.href, host: host.replace(/^www\./, '') };
  }

  function adTemizle(ad, host) {
    var a = String(ad == null ? '' : ad).replace(/[\u0000-\u001f\u007f]/g, '').replace(/\s+/g, ' ').trim();
    if (!a) {
      var ilk = String(host || '').split('.')[0] || '';
      a = ilk.charAt(0).toUpperCase() + ilk.slice(1);
    }
    return Array.from(a).slice(0, AD_MAKS).join('');
  }

  function _ham() {
    try {
      var v = JSON.parse(localStorage.getItem(ANAHTAR) || '[]');
      return Array.isArray(v) ? v : [];
    } catch (_) { return []; }
  }

  function liste() {
    var cikti = [], gorulen = {};
    _ham().forEach(function (s) {
      if (!s || typeof s !== 'object') return;
      var d = dogrula(s.url);
      if (!d.ok || gorulen[d.url]) return;       // bozuk/tehlikeli kayıt sessizce düşer
      gorulen[d.url] = 1;
      cikti.push({ id: String(s.id || d.url).slice(0, 64), ad: adTemizle(s.ad, d.host), url: d.url, host: d.host });
    });
    return cikti.slice(0, MAKS);
  }

  function _yaz(l) {
    try { localStorage.setItem(ANAHTAR, JSON.stringify(l.map(function (s) { return { id: s.id, ad: s.ad, url: s.url }; }))); return true; }
    catch (_) { return false; }
  }

  function _bildir() {
    try { document.dispatchEvent(new CustomEvent('halka:siteler-degisti')); } catch (_) {}
  }

  function ekle(ad, adres) {
    var d = dogrula(adres);
    if (!d.ok) return d;
    var l = liste();
    if (l.some(function (s) { return s.url === d.url; })) return { ok: false, hata: 'var' };
    if (l.length >= MAKS) return { ok: false, hata: 'dolu' };
    var kayit = { id: 's' + Date.now().toString(36) + Math.random().toString(36).slice(2, 6), ad: adTemizle(ad, d.host), url: d.url, host: d.host };
    l.push(kayit);
    if (!_yaz(l)) return { ok: false, hata: 'kayit' };
    _bildir();
    return { ok: true, site: kayit };
  }

  function sil(id) {
    var l = liste(), yeni = l.filter(function (s) { return s.id !== id; });
    if (yeni.length === l.length) return false;
    _yaz(yeni);
    _bildir();
    return true;
  }

  // Sistem tarayıcısında aç. noopener: açılan sayfa window.opener ile bu
  // arayüze uzanamaz. Electron'da dis-baglanti.js bunu openExternal'a çevirir.
  function ac(adres) {
    var d = dogrula(adres);
    if (!d.ok) return false;
    window.open(d.url, '_blank', 'noopener,noreferrer');
    return true;
  }

  window.HalkaSiteler = { dogrula: dogrula, liste: liste, ekle: ekle, sil: sil, ac: ac, MAKS: MAKS, ANAHTAR: ANAHTAR };
})();
