/* Güvenli dosya işlemleri — ORTAK: sunucu isteği + onay penceresi (dosya-guvenli.js, galeri-guvenli.js).
 * Kapılar SUNUCUDA (`/api/guvenli-dosya/*`); bu dosya yalnız arayüz. Stil: css/guvenli-onay.css. */
(function () {
  'use strict';
  var KOK = '/api/guvenli-dosya';
  function token() { try { return (sessionStorage.getItem('aliceToken') || localStorage.getItem('aliceToken') || ''); } catch (e) { return ''; } }
  async function istek(yol, yontem, govde) {
    var h = { 'Content-Type': 'application/json' }, t = token();
    if (t) h['Authorization'] = 'Bearer ' + t;
    var r = await fetch(yol.indexOf('/api/') === 0 ? yol : KOK + yol, { method: yontem || 'GET', headers: h, body: govde ? JSON.stringify(govde) : undefined });
    var d = {};
    try { d = await r.json(); } catch (e) {}
    if (!r.ok) { var err = new Error(d.detail || ('HTTP ' + r.status)); err.durum = r.status; throw err; }
    return d;
  }
  function el(etiket, sinif, metin) {
    var e = document.createElement(etiket);
    if (sinif) e.className = sinif;
    if (metin != null) e.textContent = metin;
    return e;
  }

  // ── Onay penceresi ─────────────────────────────────────────── //
  var pen = null, onceki = null;
  function pencere(baslik, govdeFn, dugmeler) {
    if (!pen) {
      pen = el('div', 'gd-perde');
      pen.hidden = true;
      pen.addEventListener('mousedown', function (e) { if (e.target === pen) kapat(); });
      pen.addEventListener('keydown', function (e) {
        if (e.key === 'Escape') { e.preventDefault(); e.stopPropagation(); kapat(); }
        else if (e.key === 'Tab') {
          var o = pen.querySelectorAll('button:not([disabled]), input');
          if (!o.length) return;
          if (e.shiftKey && document.activeElement === o[0]) { e.preventDefault(); o[o.length - 1].focus(); }
          else if (!e.shiftKey && document.activeElement === o[o.length - 1]) { e.preventDefault(); o[0].focus(); }
        }
        e.stopPropagation();
      });
      document.body.appendChild(pen);
    }
    onceki = document.activeElement;
    pen.textContent = '';
    var k = el('div', 'gd-pencere');
    k.setAttribute('role', 'dialog');
    k.setAttribute('aria-modal', 'true');
    k.setAttribute('aria-labelledby', 'gd-baslik');
    var h = el('h2', null, baslik); h.id = 'gd-baslik';
    k.appendChild(h);
    govdeFn(k);
    var alt = el('div', 'gd-eylem');
    dugmeler.forEach(function (d) {
      var b = el('button', 'dy-dugme gd-dugme' + (d.tehlike ? ' gd-tehlike' : d.ana ? ' gd-ana' : ''), d.ad);
      b.type = 'button';
      b.addEventListener('click', function () { d.fn(b); });
      alt.appendChild(b);
    });
    k.appendChild(alt);
    pen.appendChild(k);
    pen.hidden = false;
    var ilk = k.querySelector('input') || k.querySelector('.gd-eylem button');   // ilk odak: Vazgeç (yıkıcı değil)
    if (ilk) ilk.focus();
  }
  function kapat() {
    if (!pen || pen.hidden) return;
    pen.hidden = true;
    if (onceki && onceki.focus) onceki.focus({ preventScroll: true });
  }

  function adListesi(k, adlar, toplam) {
    var ul = el('ul', 'gd-adlar');
    adlar.forEach(function (a) { ul.appendChild(el('li', null, a)); });
    if (toplam > adlar.length) ul.appendChild(el('li', 'gd-soluk', '… ve ' + (toplam - adlar.length) + ' öğe daha'));
    k.appendChild(ul);
  }

  /* hazırla → onay penceresi → uygula. sayfa: { hata(metin), bitti(sonuc, copMu) } */
  async function onayla(govde, sayfa) {
    var h;
    try { h = await istek('/hazirla', 'POST', govde); }
    catch (e) { sayfa.hata(e.message || 'İşlem hazırlanamadı.'); return; }
    var oz = h.ozet, cop = oz.tur === 'cop';
    pencere(cop ? oz.sayi + ' öğe çöpe atılsın mı?' : oz.sayi + ' öğe taşınsın mı?', function (k) {
      adListesi(k, oz.adlar, oz.sayi);
      if (cop) k.appendChild(el('p', 'gd-not', 'Kalıcı silinmez: Yuki\'nin çöp klasörüne taşınır. "Son işlemler"den geri alabilirsin.'));
      else {
        k.appendChild(el('p', 'gd-not', 'Hedef klasör:'));
        k.appendChild(el('p', 'gd-yol', oz.hedef));
        k.appendChild(el('p', 'gd-not', 'Hedefte aynı adlı öğe varsa hiçbir şey taşınmaz.'));
      }
      if (oz.klasor_var) k.appendChild(el('p', 'gd-not gd-uyari', 'Seçimde klasör var: içindekilerin hepsi birlikte gider.'));
    }, [
      { ad: 'Vazgeç', fn: kapat },
      { ad: cop ? 'Çöpe at' : 'Taşı', tehlike: cop, ana: !cop, fn: async function (b) {
        b.disabled = true;
        try {
          var u = await istek('/uygula', 'POST', { onay: h.onay });
          kapat();
          await sayfa.bitti(u, cop);
        } catch (e) { kapat(); sayfa.hata(e.message || 'İşlem yapılamadı.'); }
      } }
    ]);
  }

  window.YukiGuvenli = {
    istek: istek, el: el, pencere: pencere, kapat: kapat, adListesi: adListesi, onayla: onayla,
    acikMi: function () { return !!pen && !pen.hidden; }
  };
})();
