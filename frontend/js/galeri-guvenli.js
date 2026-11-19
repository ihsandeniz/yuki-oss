/* Güvenli dosya işlemleri — GALERİ fişi: çöpe at · taşı · geri al. Varsayılan KAPALI.
 *
 * Açma/kapama DOSYA sayfasındaki "Salt okunur" rozetinden yapılır (tek ayar, tek yer).
 * Kapalıyken ya da uç yoksa bu betik hiçbir düğme eklemez — galeri salt okunur kalır.
 * Kapılar SUNUCUDA (`/api/guvenli-dosya/*`, kaynak: "galeri" → galerinin kendi beş kapısı).
 */
(function () {
  'use strict';
  var Y = window.yukiGaleri, G = window.YukiGuvenli;
  if (!Y || !G) return;
  var el = G.el, acik = false;

  // ── Duyuru (geri al düğmeli) ──────────────────────────────────── //
  var duy = el('div', 'gd-duyuru');
  duy.setAttribute('role', 'status');
  duy.hidden = true;
  var duyMetin = el('span'), duyDugme = el('button', 'gd-dugme gd-ana');
  duyDugme.type = 'button';
  duy.appendChild(duyMetin); duy.appendChild(duyDugme);
  document.body.appendChild(duy);
  function duyur(metin, secenek) {
    secenek = secenek || {};
    duyMetin.textContent = metin;
    duy.classList.toggle('gd-hata', !!secenek.hata);
    duyDugme.hidden = !secenek.eylem;
    duyDugme.textContent = secenek.eylem || '';
    duyDugme.onclick = secenek.fn ? function () { duy.hidden = true; secenek.fn(); } : null;
    duy.hidden = false;
    clearTimeout(duyur._z);
    duyur._z = setTimeout(function () { duy.hidden = true; }, secenek.eylem ? 8000 : 3600);
  }
  function hata(m) { duyur(m, { hata: true }); }

  async function geriAl(islem) {
    try {
      var r = await G.istek('/geri-al/' + encodeURIComponent(islem), 'POST');
      Y.yenile();
      duyur(r.sayi + ' öğe eski yerine döndü.');
    } catch (e) { hata(e.message || 'Geri alınamadı.'); }
  }

  function islem(govde) {
    return G.onayla(govde, {
      hata: hata,
      bitti: async function (u, cop) {
        Y.kapat();
        Y.yenile();
        duyur(u.sayi + ' öğe ' + (cop ? 'çöpe atıldı.' : 'taşındı.'), { eylem: 'Geri al', fn: function () { geriAl(u.islem); } });
      }
    });
  }

  function copeAt() {
    var f = Y.acikDosya();
    if (f) islem({ kaynak: 'galeri', tur: 'cop', ogeler: [f.id] });
  }

  async function tasi() {
    var f = Y.acikDosya();
    if (!f) return;
    var d;
    try { d = await G.istek('/api/galeri/klasorler'); }
    catch (e) { hata(e.message || 'Klasörler okunamadı.'); return; }
    var hedefler = (d.kokler || []).map(function (k) { return { id: k.id, ad: k.ad, yol: k.ad }; })
      .concat((d.klasorler || []).map(function (k) {
        var kok = (d.kokler || []).find(function (x) { return x.id === k.kok; });
        return { id: k.id, ad: k.ad, yol: (kok ? kok.ad + '/' : '') + (k.goreli || k.ad) };
      }))
      .filter(function (h) { return h.id !== f.klasor_id; });
    var secili = null;
    G.pencere('"' + f.ad + '" nereye taşınsın?', function (k) {
      if (!hedefler.length) { k.appendChild(el('p', 'gd-not', 'Taşınacak başka galeri klasörü yok.')); return; }
      var liste = el('div', 'gd-sec');
      liste.setAttribute('role', 'group');
      liste.setAttribute('aria-label', 'Hedef klasör');
      hedefler.forEach(function (h) {
        var b = el('button', 'gd-dugme', h.yol);
        b.type = 'button';
        b.setAttribute('aria-pressed', 'false');
        b.addEventListener('click', function () {
          secili = h.id;
          liste.querySelectorAll('button').forEach(function (x) { x.setAttribute('aria-pressed', String(x === b)); });
        });
        liste.appendChild(b);
      });
      k.appendChild(liste);
    }, [
      { ad: 'Vazgeç', fn: G.kapat },
      { ad: 'Devam', ana: true, fn: function () {
        if (!secili) { hata('Önce bir hedef klasör seç.'); return; }
        G.kapat();
        islem({ kaynak: 'galeri', tur: 'tasi', ogeler: [f.id], hedef: secili });
      } }
    ]);
  }

  // ── Fiş düğmeleri ─────────────────────────────────────────────── //
  // Doğrudan .gl-fis-eylem'in çocuğu: telefondaki alt çubuk biçimi (`.gl-fis-eylem > *`) onlara da işlesin.
  var IKON = {
    tasi: 'M3 7a2 2 0 0 1 2-2h4l2 2h8a2 2 0 0 1 2 2v8a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2zM10 13h6M13 10l3 3-3 3',
    cop: 'M4 7h16M9 7V4h6v3M6 7l1 13h10l1-13M10 11v6M14 11v6'
  };
  var dugmeler = null;
  function dugme(etiket, ikon, sinif, baslik, fn) {
    var b = el('button', 'gl-eylem gg-dugme ' + sinif);
    b.type = 'button';
    b.title = baslik;
    b.innerHTML = '<svg class="gl-ik gl-ik-k" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.6" ' +
      'stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="' + IKON[ikon] + '"/></svg>';
    b.appendChild(el('span', null, etiket));
    b.addEventListener('click', fn);
    return b;
  }
  var saltYazi = document.querySelector('.gl-salt:not(.gl-salt-duzen)');
  var saltIlk = saltYazi ? saltYazi.lastChild.textContent : '';
  function fisCiz() {
    if (saltYazi && saltYazi.lastChild) saltYazi.lastChild.textContent = acik
      ? 'Düzenleme açık — fişten çöpe atılır, taşınır; geri alınır, kalıcı silinmez.' : saltIlk;
    var eylem = document.querySelector('.gl-fis-eylem');
    if (!eylem) return;
    if (!dugmeler) {
      dugmeler = [dugme('TAŞI', 'tasi', 'gg-tasi-dugme', 'Bu dosyayı başka galeri klasörüne taşı', tasi),
                  dugme('ÇÖPE AT', 'cop', 'gg-cop-dugme', 'Çöpe at (Del) — kalıcı silinmez, geri alınır', copeAt)];
      dugmeler.forEach(function (b) { eylem.appendChild(b); });
    }
    dugmeler.forEach(function (b) { b.hidden = !acik; });
    document.body.classList.toggle('gg-acik', acik);
  }
  window.addEventListener('yuki-galeri-fis', fisCiz);

  document.addEventListener('keydown', function (e) {
    if (e.key !== 'Delete' || !acik || G.acikMi() || !Y.acikDosya()) return;
    var a = document.activeElement;
    if (a && (a.tagName === 'INPUT' || a.tagName === 'TEXTAREA' || a.tagName === 'SELECT')) return;
    e.preventDefault();
    copeAt();
  });

  async function tazele() {
    try { acik = (await G.istek('/durum')).acik === true; }
    catch (e) { acik = false; }
    fisCiz();
  }
  // Ayar DOSYA sayfasında değişir; galeri sekmesine dönülünce tazelensin.
  document.addEventListener('visibilitychange', function () { if (!document.hidden) tazele(); });
  window.addEventListener('focus', tazele);
  tazele();
})();
