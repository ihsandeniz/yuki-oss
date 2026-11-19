/* Güvenli dosya işlemleri (çöpe at · taşı · geri al) — dosya gezgininin isteğe bağlı eki.
 *
 * Varsayılan KAPALI. Sunucu ucu yoksa (yönlendirici bağlı değil) ya da kapalıysa bu betik
 * yalnız kilit düğmesini gösterir; menüye hiçbir yazma satırı eklemez. Asıl kapılar SUNUCUDA
 * (`/api/guvenli-dosya/*`, services/guvenli_dosya.py): bu dosya yalnız arayüzdür.
 *
 * Akış: menü → hazırla (diske dokunmaz) → onay penceresi → uygula → "Geri al" duyurusu.
 * Kalıcı silme yok: "Çöpe at" öğeyi Yuki'nin çöp klasörüne taşır, geri alınır.
 */
(function () {
  'use strict';
  var D = window.yukiDosya;
  if (!D) return;
  var durum = { var_: false, acik: false, anahtar: false, tasinacak: null };

  var G = window.YukiGuvenli;
  if (!G) return;
  var istek = G.istek, el = G.el, pencere = G.pencere, kapat = G.kapat, adListesi = G.adListesi;
  function acikPencere() { return G.acikMi(); }

  function hazirlaOnayla(govde) {
    return G.onayla(govde, {
      hata: function (m) { D.duyur(m); },
      bitti: async function (u, cop) {
        durum.tasinacak = null; seritCiz();
        await D.yenile();
        D.duyur(u.sayi + ' öğe ' + (cop ? 'çöpe atıldı.' : 'taşındı.'), { bilgi: true, eylem: 'Geri al', fn: function () { geriAl(u.islem); } });
      }
    });
  }

  async function geriAl(islem) {
    try {
      var r = await istek('/geri-al/' + encodeURIComponent(islem), 'POST');
      await D.yenile();
      D.duyur(r.sayi + ' öğe eski yerine döndü.', { bilgi: true });
      return true;
    } catch (e) { D.duyur(e.message || 'Geri alınamadı.'); return false; }
  }

  // ── Taşıma şeridi: seç → klasöre git → "Buraya taşı" ─────────── //
  var serit = el('div', 'gd-serit');
  serit.setAttribute('role', 'status');
  serit.hidden = true;
  document.body.appendChild(serit);
  function seritCiz() {
    serit.textContent = '';
    var t = durum.tasinacak;
    serit.hidden = !t || !durum.acik;
    document.body.classList.toggle('gd-serit-acik', !serit.hidden);
    if (serit.hidden) return;
    serit.appendChild(el('span', null, t.ogeler.length + ' öğe taşınacak — hedef klasörü aç, sonra:'));
    var b = el('button', 'dy-dugme gd-ana', 'Buraya taşı'); b.type = 'button';
    b.addEventListener('click', function () { buraya(); });
    var v = el('button', 'dy-dugme', 'Vazgeç'); v.type = 'button';
    v.addEventListener('click', function () { durum.tasinacak = null; seritCiz(); });
    serit.appendChild(b); serit.appendChild(v);
  }
  function buraya() {
    var t = durum.tasinacak, sonKlasor = D.klasor();
    if (!t) return;
    if (!sonKlasor) { D.duyur('Önce hedef klasörü aç (arama sonucunda taşınmaz).'); return; }
    hazirlaOnayla({ tur: 'tasi', ogeler: t.ogeler.map(function (o) { return o.id; }), hedef: sonKlasor, gizli: t.gizli });
  }

  D.menuEkle(function (ogeler, klasorId) {
    if (!durum.acik) return [];
    var m = [];
    if (ogeler.length) {
      m.push({ ad: 'Taşımak için seç', fn: function () {
        durum.tasinacak = { ogeler: ogeler, gizli: D.gizli() }; seritCiz();
      } });
      m.push({ ad: 'Çöpe at…', tus: 'Del', tehlike: true, fn: function () {
        hazirlaOnayla({ tur: 'cop', ogeler: ogeler.map(function (o) { return o.id; }), gizli: D.gizli() });
      } });
    } else if (durum.tasinacak && klasorId) {
      m.push({ ad: 'Buraya taşı (' + durum.tasinacak.ogeler.length + ' öğe)', fn: buraya });
    }
    m.push({ ad: 'Son işlemler…', fn: panelAc });
    return m;
  });

  document.addEventListener('keydown', function (e) {
    if (e.key !== 'Delete' || !durum.acik || acikPencere()) return;
    var a = document.activeElement;
    if (a && (a.tagName === 'INPUT' || a.tagName === 'TEXTAREA' || a.tagName === 'SELECT')) return;
    if (document.getElementById('dy-menu') && !document.getElementById('dy-menu').hidden) return;
    var s = D.secili();
    if (!s.length) return;
    e.preventDefault();
    hazirlaOnayla({ tur: 'cop', ogeler: s.map(function (o) { return o.id; }), gizli: D.gizli() });
  });

  // ── Ayar + son işlemler paneli ────────────────────────────────── //
  // Kilit: var olan "Salt okunur" rozeti (#dy-kip-rozet) anahtara dönüşür — yalnız uç varsa.
  var kilit = document.getElementById('dy-kip-rozet'), kipYazi = document.getElementById('dy-kip');
  var kapiNot = document.getElementById('dy-kapi-not');
  function notCiz() {
    // Kip notu (dosya.html): uç yoksa "yalnız gezilir" (HTML'deki metin); uç varsa nasıl açılacağını söyler; açıkken gizlenir.
    if (!kapiNot) return;
    kapiNot.hidden = durum.acik;
    if (durum.var_ && !durum.acik) kapiNot.textContent = durum.anahtar
      ? 'Salt okunur — çöpe atma ve taşıma rozetten, erişim anahtarıyla açılır'
      : 'Salt okunur — düzenleme için .env içinde erişim anahtarı gerekir';
  }
  function kilitCiz() {
    notCiz();
    if (!kilit) return;
    if (!durum.var_) {                      // uç yok: rozet eskisi gibi düz etiket
      kilit.classList.remove('gd-kilit', 'gd-acik');
      kilit.removeAttribute('role'); kilit.removeAttribute('tabindex'); kilit.removeAttribute('title');
      kilit.removeAttribute('aria-pressed');
      return;
    }
    kilit.classList.add('gd-kilit');
    kilit.classList.toggle('gd-acik', durum.acik);
    kilit.setAttribute('role', 'button');
    kilit.setAttribute('tabindex', '0');
    kilit.setAttribute('aria-pressed', String(durum.acik));
    if (kipYazi) kipYazi.textContent = durum.acik ? 'Düzenleme açık' : 'Salt okunur';
    kilit.title = durum.acik ? 'Düzenleme açık: çöpe at, taşı, geri al — son işlemler ve kapatma için tıkla'
                             : 'Salt okunur — düzenlemeyi açmak için tıkla';
  }
  if (kilit) {
    kilit.addEventListener('click', function () { if (durum.var_) panelAc(); });
    kilit.addEventListener('keydown', function (e) {
      if (durum.var_ && (e.key === 'Enter' || e.key === ' ')) { e.preventDefault(); e.stopPropagation(); panelAc(); }
    });
  }

  async function panelAc() {
    if (!durum.acik) {
      pencere('Düzenleme kapalı', function (k) {
        k.appendChild(el('p', 'gd-not', 'Dosya gezgini salt okunur. Açarsan seçtiğin öğeleri çöpe atabilir, taşıyabilir ve geri alabilirsin. Kalıcı silme hiçbir zaman yok; her işlem önce senden onay ister.'));
        if (!durum.anahtar) {
          k.appendChild(el('p', 'gd-not gd-uyari', 'Bu kurulumda erişim anahtarı (.env içinde AUTH_TOKEN) yok — düzenleme açılamaz.'));
          return;
        }
        var lb = el('label', 'gd-etiket', 'Erişim anahtarı');
        var inp = el('input', 'gd-girdi'); inp.type = 'password'; inp.id = 'gd-anahtar'; inp.autocomplete = 'off';
        lb.htmlFor = 'gd-anahtar';
        k.appendChild(lb); k.appendChild(inp);
        inp.addEventListener('keydown', function (e) { if (e.key === 'Enter') { e.preventDefault(); k.querySelector('.gd-ana').click(); } });
      }, [
        { ad: 'Vazgeç', fn: kapat }
      ].concat(durum.anahtar ? [{ ad: 'Düzenlemeyi aç', ana: true, fn: async function (b) {
        var inp = document.getElementById('gd-anahtar');
        b.disabled = true;
        try {
          await istek('/ayar', 'PUT', { acik: true, anahtar: inp.value });
          await tazele();
          kapat();
          D.duyur('Düzenleme açık. Sağ tık menüsünde çöpe at / taşı var.', { bilgi: true });
        } catch (e) { b.disabled = false; D.duyur(e.message || 'Açılamadı.'); inp.select(); }
      } }] : []));
      return;
    }
    var g = [];
    try { g = (await istek('/gunluk')).islemler; } catch (e) { D.duyur(e.message || 'Günlük okunamadı.'); return; }
    pencere('Son işlemler', function (k) {
      if (!g.length) { k.appendChild(el('p', 'gd-not', 'Henüz işlem yok.')); return; }
      var ul = el('ul', 'gd-gunluk');
      g.slice(0, 20).forEach(function (i) {
        var li = el('li');
        var ad = el('div', 'gd-g-ad');
        ad.appendChild(el('strong', null, i.tur === 'cop' ? 'Çöpe atıldı' : 'Taşındı'));
        ad.appendChild(el('span', 'gd-soluk', ' · ' + i.sayi + ' öğe · ' + new Date(i.zaman * 1000).toLocaleString('tr-TR', { dateStyle: 'short', timeStyle: 'short' })));
        ad.appendChild(el('div', 'gd-g-dosya', i.adlar.join(', ')));
        li.appendChild(ad);
        if (i.geri_alindi) li.appendChild(el('span', 'gd-rozet', 'geri alındı'));
        else {
          var b = el('button', 'dy-dugme gd-dugme', 'Geri al'); b.type = 'button';
          b.addEventListener('click', async function () { b.disabled = true; if (await geriAl(i.id)) { li.replaceChild(el('span', 'gd-rozet', 'geri alındı'), b); } else b.disabled = false; });
          li.appendChild(b);
        }
        ul.appendChild(li);
      });
      k.appendChild(ul);
    }, [
      { ad: 'Düzenlemeyi kapat', fn: async function () {
        try { await istek('/ayar', 'PUT', { acik: false }); } catch (e) {}
        durum.tasinacak = null;
        await tazele(); kapat(); seritCiz();
        D.duyur('Düzenleme kapandı — salt okunur.', { bilgi: true });
      } },
      { ad: 'Kapat', ana: true, fn: kapat }
    ]);
  }

  async function tazele() {
    try {
      var d = await istek('/durum');
      durum.var_ = true; durum.acik = d.acik === true; durum.anahtar = d.anahtar_kurulu === true;
    } catch (e) {
      durum.var_ = false; durum.acik = false;       // uç yok ya da giriş yok → hiçbir şey eklenmez
    }
    kilitCiz();
    seritCiz();
  }
  tazele();
})();
