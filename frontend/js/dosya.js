/* Dosya gezgini — salt okunur.
 *
 * Uçlar: backend/app/api/dosya_api.py. Kimlik (id) ham yol değildir; yol yalnız
 * kırıntıda GÖSTERİLİR, elle yazılan yol POST /git gövdesinde gider.
 * F1 davranışları: geri/ileri/yukarı · kırıntı + yol yazma · liste/ızgara ·
 * sıralama + klasör önce · klavye (oklar, Enter, Backspace, tür-ile-atla) ·
 * Space önizleme · sunucu sayfalama (200'lük, aşağı kaydırınca devamı).
 * Çoklu seçim — Ctrl/⌘+tık, Shift+tık / Shift+ok aralık, Ctrl+A. Bu sürüm YALNIZ GEZER: yazma, silme,
 * taşıma ve kabuk yok; sunucuda da yazma ucu yoktur.
 * 🔴 Blob havuzu sınırlı (galeri dersi): küçük resimler revokeObjectURL ile serbest bırakılır.
 */
(function () {
  'use strict';

  var SAYFA = 200;
  var HAVUZ_AZAMI = 300;
  var $ = function (id) { return document.getElementById(id); };

  var durum = {
    id: null, ust: null, kirinti: [], girdiler: [], toplam: 0, yukleniyor: false,
    secili: -1, cok: new Set(), capa: -1, gecmis: [], ileri: [],
    sira: oku('dy_sira_v1', 'ad'), yon: oku('dy_yon_v1', 'artan'),
    gorunum: oku('dy_gorunum_v1', window.innerWidth < 600 ? 'liste' : 'liste'),
    gizli: oku('dy_gizli_v1', '0') === '1',
    onizlemeAcik: false, kokler: [], suz: '', arama: null
  };

  function oku(k, v) { try { return localStorage.getItem(k) || v; } catch (e) { return v; } }
  function yaz(k, v) { try { localStorage.setItem(k, v); } catch (e) {} }
  function token() { try { return (sessionStorage.getItem('aliceToken') || localStorage.getItem('aliceToken') || ''); } catch (e) { return ''; } }

  function api(yol, opts) {
    opts = opts || {};
    var h = opts.headers || {};
    var t = token();
    if (t) h['Authorization'] = 'Bearer ' + t;
    opts.headers = h;
    return fetch(yol, opts);
  }
  async function json(yol, opts) {
    var r = await api(yol, opts);
    if (!r.ok) {
      var d = '';
      try { d = (await r.json()).detail || ''; } catch (e) {}
      var hata = new Error(d || ('HTTP ' + r.status));
      hata.durum = r.status;
      throw hata;
    }
    return r.json();
  }

  // secenek: { bilgi: true } → hata kırmızısı yerine nötr · { eylem: 'Geri al', fn } → düğme
  function duyur(metin, secenek) {
    secenek = secenek || {};
    var d = $('dy-duyuru'), b = $('dy-duyuru-eylem');
    $('dy-duyuru-metin').textContent = metin;
    d.classList.toggle('dy-duyuru-bilgi', !!secenek.bilgi);
    b.hidden = !secenek.eylem;
    b.textContent = secenek.eylem || '';
    b.onclick = secenek.fn ? function () { d.hidden = true; secenek.fn(); } : null;
    d.hidden = false;
    clearTimeout(duyur._z);
    duyur._z = setTimeout(function () { d.hidden = true; }, secenek.eylem ? 8000 : 3600);
  }
  function el(etiket, sinif, metin) {
    var e = document.createElement(etiket);
    if (sinif) e.className = sinif;
    if (metin != null) e.textContent = metin;
    return e;
  }
  function ikon(ad) {
    var ns = 'http://www.w3.org/2000/svg';
    var s = document.createElementNS(ns, 'svg');
    s.setAttribute('aria-hidden', 'true');
    var u = document.createElementNS(ns, 'use');
    u.setAttribute('href', '#i-' + ad);
    s.appendChild(u);
    return s;
  }
  var IKON = { klasor: 'klasor', resim: 'resim', video: 'video', metin: 'metin', pdf: 'pdf',
    ses: 'ses', arsiv: 'arsiv', dosya: 'dosya' };

  function boyutYaz(b) {
    if (b == null) return '';
    var b1 = ['B', 'KB', 'MB', 'GB', 'TB'], i = 0;
    while (b >= 1024 && i < b1.length - 1) { b /= 1024; i++; }
    return (i ? b.toFixed(b < 10 ? 1 : 0) : b) + ' ' + b1[i];
  }
  function tarihYaz(t) {
    var d = new Date(t * 1000);
    return d.toLocaleDateString('tr-TR', { day: '2-digit', month: '2-digit', year: 'numeric' }) +
      ' ' + d.toLocaleTimeString('tr-TR', { hour: '2-digit', minute: '2-digit' });
  }

  // ── Blob havuzu (küçük resim) ─────────────────────────────────── //
  var havuz = [];
  function havuzaEkle(u) {
    havuz.push(u);
    while (havuz.length > HAVUZ_AZAMI) URL.revokeObjectURL(havuz.shift());
  }
  function havuzuBosalt() { havuz.forEach(URL.revokeObjectURL); havuz = []; }

  var gozcu = 'IntersectionObserver' in window ? new IntersectionObserver(function (ks) {
    ks.forEach(function (k) {
      if (!k.isIntersecting) return;
      gozcu.unobserve(k.target);
      kucukYukle(k.target);
    });
  }, { rootMargin: '200px' }) : null;

  async function kucukYukle(kap) {
    var id = kap.dataset.id;
    try {
      var r = await api('/api/dosya/onizle/' + id + '?k=200' + (durum.gizli ? '&gizli=1' : ''));
      if (!r.ok) return;
      var u = URL.createObjectURL(await r.blob());
      havuzaEkle(u);
      var img = el('img');
      img.alt = '';
      img.src = u;
      kap.textContent = '';
      kap.appendChild(img);
    } catch (e) {}
  }

  // ── Gezinme ──────────────────────────────────────────────────── //
  async function ac(id, gecmiseYaz) {
    if (gecmiseYaz !== false && durum.id && durum.id !== id) {
      durum.gecmis.push(durum.id);
      durum.ileri = [];
    }
    if (durum.id !== id || durum.arama) { durum.suz = ''; $('dy-suz').value = ''; }
    durum.id = id;
    aramaBirak();
    durum.secili = -1;
    if (SABIT.matches) onizlemeBos();
    durum.cok.clear();
    durum.capa = -1;
    durum.girdiler = [];
    havuzuBosalt();
    $('dy-liste').textContent = '';
    await sayfaYukle(true);
  }

  async function sayfaYukle(ilk) {
    if (durum.yukleniyor || durum.arama) return;
    if (!ilk && durum.girdiler.length >= durum.toplam) return;
    durum.yukleniyor = true;
    $('dy-durum').textContent = 'Yükleniyor…';
    var q = '?offset=' + durum.girdiler.length + '&limit=' + SAYFA + '&sira=' + durum.sira +
      '&yon=' + durum.yon + (durum.gizli ? '&gizli=1' : '');
    var istenen = durum.id;
    try {
      var d = await json('/api/dosya/liste/' + istenen + q);
      if (istenen !== durum.id) return;          // bu arada başka klasöre geçildi
      durum.ust = d.ust;
      durum.kirinti = d.kirinti;
      durum.toplam = d.toplam;
      durum.yol = d.yol;
      var bas = durum.girdiler.length;
      durum.girdiler = durum.girdiler.concat(d.girdiler);
      ciz(bas);
      if (ilk) {
        kirintiCiz();
        kokleriIsaretle();
        atalariCiz();
        if (durum.girdiler.length) secimYap(0, false, 'imlec');
        try { history.replaceState(null, '', '#' + d.id); } catch (e) {}
      }
      $('dy-durum').textContent = durum.toplam === 0 ? 'Bu klasör boş.' : '';
      $('dy-panel-ad').textContent = d.ad;
      $('dy-panel-alt').textContent = durum.kirinti.length > 1 ? durum.kirinti.slice(0, -1).map(function (k) { return k.ad; }).join(' · ') : 'kök';
      $('dy-panel-sayi').textContent = durum.toplam + ' öğe';
    } catch (e) {
      $('dy-durum').textContent = '';
      if (e.durum === 404 && ilk) {
        duyur((e.message || 'Klasör yok') + ' — üst klasöre dönülüyor.');
        var hedef = durum.gecmis.pop() || (durum.kokler[0] && durum.kokler[0].id);
        if (hedef && hedef !== istenen) { durum.id = null; ac(hedef, false); }
      } else {
        duyur(e.message || 'Açılamadı.');
        // Açılamayan klasöre (izin yok, gizli…) GEÇİLMEZ — bulunduğun yere geri dön
        if (ilk && durum.gecmis.length) { var once = durum.gecmis.pop(); durum.id = null; ac(once, false); }
      }
    } finally {
      durum.yukleniyor = false;
      altCiz();
    }
  }

  function geri() {
    if (!durum.gecmis.length) return;
    durum.ileri.push(durum.id);
    ac(durum.gecmis.pop(), false);
  }
  function ileri() {
    if (!durum.ileri.length) return;
    durum.gecmis.push(durum.id);
    ac(durum.ileri.pop(), false);
  }
  function yukari() { if (durum.ust) ac(durum.ust); }

  // ── Çizim ────────────────────────────────────────────────────── //
  function ciz(bas) {
    var liste = $('dy-liste');
    var frag = document.createDocumentFragment();
    for (var i = bas; i < durum.girdiler.length; i++) frag.appendChild(satir(durum.girdiler[i], i));
    liste.appendChild(frag);
    $('dy-baslik-satir').hidden = durum.gorunum !== 'liste';
  }

  function satir(g, i) {
    var li = el('li', 'dy-oge dy-' + g.tur);
    li.setAttribute('role', 'option');
    li.dataset.i = i;
    li.id = 'dy-o-' + i;
    if (durum.cok.has(g.id)) li.classList.add('dy-cok');
    var simge = el('span', 'dy-simge');
    if (g.tur === 'resim' && durum.gorunum === 'izgara' && gozcu) {
      simge.dataset.id = g.id;
      simge.appendChild(ikon('resim'));
      gozcu.observe(simge);
    } else {
      simge.appendChild(ikon(IKON[g.tur] || 'dosya'));
    }
    li.appendChild(simge);
    var ad = el('span', 'dy-ad', g.ad);
    ad.title = g.ad;
    if (g.bag) ad.appendChild(ikon('bag'));
    if (g.konum !== undefined) { ad.dataset.konum = '/' + g.konum; ad.title = g.ad + '\n/' + g.konum; }
    li.appendChild(ad);
    li.appendChild(el('span', 'dy-boyut', g.klasor ? '' : boyutYaz(g.boyut)));
    li.appendChild(el('span', 'dy-tarih', tarihYaz(g.tarih)));
    if (durum.suz && !suzUyar(g)) li.hidden = true;
    return li;
  }

  function kirintiCiz() {
    var k = $('dy-kirinti');
    k.textContent = '';
    durum.kirinti.forEach(function (p, i) {
      if (i) k.appendChild(el('span', 'dy-ayrac', '/'));
      var b = el('button', 'dy-kir' + (i === durum.kirinti.length - 1 ? ' dy-burada' : ''), p.ad);
      b.type = 'button';
      b.dataset.id = p.id;                        // F4: bırakma hedefi
      if (i === durum.kirinti.length - 1) b.setAttribute('aria-current', 'location');
      b.addEventListener('click', function (e) { e.stopPropagation(); ac(p.id); });
      k.appendChild(b);
    });
    k.scrollLeft = k.scrollWidth;
    $('dy-geri').disabled = !durum.gecmis.length;
    $('dy-ileri').disabled = !durum.ileri.length;
    $('dy-yukari').disabled = !durum.ust;
    yerimiDugme();
    $('dy-t-geri').disabled = !durum.gecmis.length;
    $('dy-t-ust').disabled = !durum.ust;
  }

  function kokleriIsaretle() {
    var kokId = durum.kirinti[0] && durum.kirinti[0].id;
    Array.prototype.forEach.call($('dy-kokler').children, function (b) {
      var aktif = b.dataset.yol && b.classList.contains('dy-yerimi') ? b.dataset.yol === durum.yol : b.dataset.id === kokId;
      b.classList.toggle('dy-aktif', aktif);
      b.setAttribute('aria-selected', aktif ? 'true' : 'false');
    });
  }

  function altCiz() {
    var g = durum.girdiler;
    var klasor = 0;
    for (var i = 0; i < g.length; i++) if (g[i].klasor) klasor++;
    var s = durum.toplam + ' öğe';
    if (g.length < durum.toplam) s += ' · ' + g.length + ' gösteriliyor';
    if (durum.cok.size > 1) {
      s += ' · ' + durum.cok.size + ' öğe seçili';
    } else if (durum.secili >= 0 && g[durum.secili]) {
      var o = g[durum.secili];
      s += ' · seçili: ' + o.ad + (o.klasor ? '' : ' (' + boyutYaz(o.boyut) + ')');
    }
    $('dy-alt').textContent = s;
    gonderDurum();
  }

  function gorunumUygula() {
    document.body.classList.toggle('dy-izgara-kip', durum.gorunum === 'izgara');
    $('dy-gorunum').querySelector('use').setAttribute('href', durum.gorunum === 'izgara' ? '#i-liste' : '#i-izgara');
    $('dy-yon').textContent = durum.yon === 'artan' ? '↑' : '↓';
    $('dy-sira').value = durum.sira;
    $('dy-gizli').setAttribute('aria-pressed', durum.gizli ? 'true' : 'false');
    $('dy-gizli').classList.toggle('dy-basili', durum.gizli);
  }

  // ── Seçim + klavye ───────────────────────────────────────────── //
  // ── Çoklu seçim (F2) — küme kimlik tutar (sıra/sayfa değişse de doğru öğe) ── //
  function cokCiz() {
    var l = $('dy-liste').children;
    for (var k = 0; k < l.length; k++) {
      var g = durum.girdiler[+l[k].dataset.i];
      l[k].classList.toggle('dy-cok', !!g && durum.cok.has(g.id));
    }
  }
  // kip: 'tek' (varsayılan — imleç = seçim) · 'ekle' (Ctrl: aç/kapa) · 'aralik' (Shift: çapadan i'ye)
  // · 'imlec' (açılıştaki kendiliğinden imleç — kümeye GİRMEZ; telefonda görünmeden çöpe gitmesin)
  function cokGuncelle(i, kip) {
    var g = durum.girdiler;
    if (kip === 'imlec') {
      durum.capa = i;
    } else if (kip === 'aralik' && durum.capa >= 0) {
      durum.cok.clear();
      for (var k = Math.min(durum.capa, i); k <= Math.max(durum.capa, i); k++) if (g[k]) durum.cok.add(g[k].id);
    } else if (kip === 'ekle') {
      if (durum.cok.has(g[i].id)) durum.cok.delete(g[i].id); else durum.cok.add(g[i].id);
      durum.capa = i;
    } else {
      durum.cok.clear();
      durum.cok.add(g[i].id);
      durum.capa = i;
    }
    cokCiz();
  }
  // Açık seçim yoksa masada imleçteki öğe sayılır (klavyeyle Delete/F2 alışkanlığı); dokunmatikte
  // imleç görünmez → yalnız açıkça dokunulanlar.
  function seciliOgeler() {
    var g = durum.girdiler.filter(function (x) { return durum.cok.has(x.id); });
    if (!g.length && durum.girdiler[durum.secili] && !matchMedia('(pointer: coarse)').matches) g = [durum.girdiler[durum.secili]];
    return g;
  }
  function hepsiniSec() {
    durum.girdiler.forEach(function (x) { durum.cok.add(x.id); });
    cokCiz(); altCiz();
  }

  function secimYap(i, kaydir, kip) {
    var n = durum.girdiler.length;
    if (!n) return;
    i = Math.max(0, Math.min(n - 1, i));
    cokGuncelle(i, kip);
    var eski = $('dy-o-' + durum.secili);
    if (eski) { eski.classList.remove('dy-secili'); eski.setAttribute('aria-selected', 'false'); }
    durum.secili = i;
    var yeni = $('dy-o-' + i);
    if (yeni) {
      yeni.classList.add('dy-secili');
      yeni.setAttribute('aria-selected', 'true');
      $('dy-liste').setAttribute('aria-activedescendant', yeni.id);
      if (kaydir !== false) yeni.scrollIntoView({ block: 'nearest' });
    }
    if (i >= n - 20) sayfaYukle(false);
    altCiz();
    // F2: masaüstünde önizleme sütunu hep açık — seçim oturunca TEK istek (oklarla gezerken her satıra değil);
    // açılıştaki kendiliğinden imleç önizlemez (seçimsiz açılış = boş durum)
    if (SABIT.matches) { if (kip !== 'imlec') onizleGecikmeli(durum.girdiler[i]); }
    else if (durum.onizlemeAcik) onizle(durum.girdiler[i]);
  }

  function sutunSayisi() {
    if (durum.gorunum !== 'izgara') return 1;
    var l = $('dy-liste');
    var ilk = l.children[0];
    if (!ilk) return 1;
    return Math.max(1, Math.round(l.clientWidth / ilk.getBoundingClientRect().width));
  }

  function aktif(g) {
    if (!g) return;
    if (g.klasor) ac(g.id);
    else onizle(g, true);
  }

  var arananMetin = '', aramaZaman = 0;
  function turIleAtla(harf) {
    var simdi = Date.now();
    arananMetin = (simdi - aramaZaman > 800 ? '' : arananMetin) + harf.toLocaleLowerCase('tr');
    aramaZaman = simdi;
    var g = durum.girdiler;
    var bas = arananMetin.length === 1 ? durum.secili + 1 : durum.secili;
    for (var k = 0; k < g.length; k++) {
      var i = (bas + k) % g.length;
      if (g[i].ad.toLocaleLowerCase('tr').indexOf(arananMetin) === 0) { secimYap(i); return; }
    }
  }

  document.addEventListener('keydown', function (e) {
    if (e.target && (e.target.tagName === 'INPUT' || e.target.tagName === 'SELECT')) return;
    if (e.altKey && e.key === 'ArrowLeft') { e.preventDefault(); geri(); return; }
    if (e.altKey && e.key === 'ArrowRight') { e.preventDefault(); ileri(); return; }
    if (e.altKey && e.key === 'ArrowUp') { e.preventDefault(); yukari(); return; }
    if ((e.ctrlKey || e.metaKey) && e.key.toLowerCase() === 'l') { e.preventDefault(); yolDuzenle(); return; }
    if (menuAcik()) return;                           // açık menüde tuşlar menünündür
    if ((e.ctrlKey || e.metaKey) && e.key.toLowerCase() === 'd') { e.preventDefault(); yerimiDegistir(); return; }
    if (e.key === 'ContextMenu' || (e.shiftKey && e.key === 'F10')) { e.preventDefault(); menuKlavyeden(); return; }
    if ((e.ctrlKey || e.metaKey) && e.key.toLowerCase() === 'a') { e.preventDefault(); hepsiniSec(); return; }
    var s = durum.secili, c = sutunSayisi(), k = e.shiftKey ? 'aralik' : 'tek';
    if (e.shiftKey && durum.capa < 0) durum.capa = s;
    if (e.key === '/' && !e.ctrlKey && !e.metaKey) { e.preventDefault(); $('dy-suz').focus(); return; }
    if (durum.suz && (e.key === 'ArrowDown' || e.key === 'ArrowUp' || e.key === 'Home' || e.key === 'End')) {
      e.preventDefault();
      var yon = e.key === 'ArrowDown' || e.key === 'Home' ? 1 : -1;
      var bas = e.key === 'Home' ? -1 : e.key === 'End' ? durum.girdiler.length : s;
      var j = gorunurAdim(bas, yon);
      if (j >= 0) secimYap(j, true, k);
      return;
    }
    switch (e.key) {
      case 'ArrowDown': e.preventDefault(); secimYap(s < 0 ? 0 : s + c, true, k); return;
      case 'ArrowUp': e.preventDefault(); secimYap(s - c, true, k); return;
      case 'ArrowRight': if (c > 1) { e.preventDefault(); secimYap(s + 1, true, k); } return;
      case 'ArrowLeft': if (c > 1) { e.preventDefault(); secimYap(s - 1, true, k); } return;
      case 'Home': e.preventDefault(); secimYap(0, true, k); return;
      case 'End': e.preventDefault(); secimYap(durum.girdiler.length - 1, true, k); return;
      case 'PageDown': e.preventDefault(); secimYap(s + 10 * c, true, k); return;
      case 'PageUp': e.preventDefault(); secimYap(s - 10 * c, true, k); return;
      case 'Enter': e.preventDefault(); aktif(durum.girdiler[s]); return;
      case 'Backspace': e.preventDefault(); yukari(); return;
      case ' ': e.preventDefault(); onizlemeAcKapa(); return;
      case 'Escape':
        $('dy-duyuru').hidden = true;
        if (durum.arama) { e.preventDefault(); aramaKapat(); return; }
        if (durum.onizlemeAcik && !SABIT.matches) { e.preventDefault(); onizlemeKapat(); return; }
        if (durum.cok.size > 1 && s >= 0) { e.preventDefault(); secimYap(s, false); }
        return;
    }
    if (e.key.length === 1 && !e.ctrlKey && !e.metaKey && !e.altKey) turIleAtla(e.key);
  });

  $('dy-liste').addEventListener('click', function (e) {
    var li = e.target.closest('.dy-oge');
    if (!li) return;
    var i = +li.dataset.i;
    var dokunmatik = matchMedia('(pointer: coarse)').matches;
    if (e.shiftKey) { secimYap(i, false, 'aralik'); return; }
    if (e.ctrlKey || e.metaKey) { secimYap(i, false, 'ekle'); return; }
    secimYap(i, false);
    // Dokunmatikte tek dokunuş açar (çift tıklama yok); masada çift tık açar
    if (dokunmatik) aktif(durum.girdiler[i]);
  });
  $('dy-liste').addEventListener('dblclick', function (e) {
    var li = e.target.closest('.dy-oge');
    if (li) aktif(durum.girdiler[+li.dataset.i]);
  });

  // ── F2 · Derin arama (alt klasörler, sunucuda) ─────────────────── //
  /* Süz kutusunda Enter → GET /api/dosya/ara/{açık klasör}?q=. Sonuçlar aynı listede, satırda konum.
   * Yeni arama ya da klasör değişimi eskisini iptal eder (AbortController); sunucu 3 sn + 500 sonuç tavanlı. */
  var aramaIptal = null;
  function aramaBirak() {
    if (aramaIptal) { aramaIptal.abort(); aramaIptal = null; }
    if (!durum.arama) return;
    durum.arama = null;
    document.body.classList.remove('dy-arama-kip');
    $('dy-arama-kapat').hidden = true;
  }
  function aramaKapat() { if (durum.arama) ac(durum.id, false); }
  async function aramaYap(q) {
    if (!durum.id) return;
    if (aramaIptal) aramaIptal.abort();
    var iptal = aramaIptal = new AbortController();
    var klasor = durum.id;
    $('dy-durum').textContent = '“' + q + '” aranıyor…';
    try {
      var d = await json('/api/dosya/ara/' + klasor + '?q=' + encodeURIComponent(q) + (durum.gizli ? '&gizli=1' : ''),
        { signal: iptal.signal });
      if (iptal !== aramaIptal || klasor !== durum.id) return;
      aramaIptal = null;
      durum.arama = { q: d.q, tamam: d.tamam, taranan: d.taranan };
      durum.suz = '';
      durum.girdiler = d.sonuclar;
      durum.toplam = d.sonuclar.length;
      durum.secili = -1; durum.cok.clear(); durum.capa = -1;
      havuzuBosalt();
      $('dy-liste').textContent = '';
      document.body.classList.add('dy-arama-kip');
      $('dy-arama-kapat').hidden = false;
      ciz(0);
      $('dy-panel-ad').textContent = '“' + d.q + '”';
      $('dy-panel-alt').textContent = 'alt klasörlerde · ' + ((durum.kirinti[durum.kirinti.length - 1] || {}).ad || '');
      $('dy-panel-sayi').textContent = d.sonuclar.length + ' sonuç' + (d.tamam ? '' : ' · yarıda kesildi');
      $('dy-durum').textContent = d.sonuclar.length ? (d.tamam ? '' : 'Arama tavana ulaştı — aramayı daralt.')
        : 'Alt klasörlerde eşleşen yok (' + d.taranan + ' öğe tarandı).';
      if (d.sonuclar.length) secimYap(0, true, 'imlec');
      altCiz();
      $('dy-liste').focus({ preventScroll: true });
    } catch (e) {
      if (e.name === 'AbortError') return;
      $('dy-durum').textContent = '';
      duyur(e.message || 'Arama yapılamadı.');
    }
  }
  $('dy-arama-kapat').addEventListener('click', aramaKapat);
  // Arama sonucunun bulunduğu klasörü aç ve öğeyi seç
  async function klasorundeGoster(g) {
    if (!g || !g.ust) return;
    await ac(g.ust);
    var i = durum.girdiler.findIndex(function (x) { return x.id === g.id; });
    if (i >= 0) secimYap(i);
  }

  // ── F2 · Yer imleri (kökler şeridinde ★) ────────────────────────── //
  /* Yol saklanır (kimlik değil: kimlik sunucu belleğinde, restart'ta düşer) → açarken POST /git
   * kapılardan yeniden geçer. Yol gizli değil ama yalnız bu tarayıcıda: localStorage dy_yerimi_v1. */
  function yerimiOku() {
    try { var a = JSON.parse(localStorage.getItem('dy_yerimi_v1') || '[]'); return Array.isArray(a) ? a.filter(function (x) { return x && typeof x.yol === 'string'; }) : []; }
    catch (e) { return []; }
  }
  function yerimiYaz(a) { yaz('dy_yerimi_v1', JSON.stringify(a)); }
  function yerimiVar(yol) { return yerimiOku().some(function (x) { return x.yol === yol; }); }
  function yerimiCiz() {
    var kap = $('dy-kokler');
    Array.prototype.slice.call(kap.querySelectorAll('.dy-yerimi')).forEach(function (b) { b.remove(); });
    yerimiOku().forEach(function (y) {
      var b = el('button', 'dy-kok dy-yerimi', y.ad);
      b.type = 'button';
      b.title = 'Yer imi · ' + y.yol;
      b.dataset.yol = y.yol;
      b.setAttribute('role', 'tab');
      b.insertBefore(ikon('yildiz'), b.firstChild);
      b.addEventListener('click', function () { yolaGit(y.yol); });
      b.addEventListener('contextmenu', function (e) {
        e.preventDefault();
        menuAc(e.clientX, e.clientY, [{ ad: 'Yer imini kaldır', fn: function () { yerimiKaldir(y.yol); } }]);
      });
      kap.appendChild(b);
    });
    kokleriIsaretle();
  }
  async function yolaGit(yol) {
    try {
      var d = await json('/api/dosya/git', { method: 'POST', headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ yol: yol, gizli: durum.gizli }) });
      if (d.klasor) await ac(d.id); else duyur('Yer imi bir klasör değil.');
    } catch (e) { duyur('Yer imi açılamadı: ' + (e.message || 'hata') + ' — kaldırmak için sağ tık.'); }
  }
  function yerimiEkle(yol, ad) {
    var a = yerimiOku();
    if (a.some(function (x) { return x.yol === yol; })) return;
    a.push({ yol: yol, ad: ad || yol });
    yerimiYaz(a); yerimiCiz(); yerimiDugme();
    duyur('Yer imlerine eklendi: ' + (ad || yol), { bilgi: true });
  }
  function yerimiKaldir(yol) {
    yerimiYaz(yerimiOku().filter(function (x) { return x.yol !== yol; }));
    yerimiCiz(); yerimiDugme();
    duyur('Yer imi kaldırıldı.', { bilgi: true });
  }
  function yerimiDegistir() {
    if (!durum.yol || durum.arama) return;
    if (yerimiVar(durum.yol)) yerimiKaldir(durum.yol);
    else yerimiEkle(durum.yol, $('dy-panel-ad').textContent || durum.yol);
  }
  function yerimiDugme() {
    var b = $('dy-yerimi');
    if (!b) return;
    var var_ = !!durum.yol && yerimiVar(durum.yol);
    b.setAttribute('aria-pressed', var_ ? 'true' : 'false');
    b.classList.toggle('dy-basili', var_);
    b.title = var_ ? 'Yer iminden çıkar (Ctrl+D)' : 'Bu klasörü yer imlerine ekle (Ctrl+D)';
    b.disabled = !durum.yol || !!durum.arama;
  }
  $('dy-yerimi').addEventListener('click', yerimiDegistir);

  // ── F2 · Sağ tık menüsü ──────────────────────────────────────── //
  /* Okuma işleri her yerde; yazma işleri yalnız masa başında ve düzenleme açıkken çalışır
   * (kapalıyken tek satır "Düzenlemeyi aç…"). Kapılar yine SUNUCUDA — menü yalnız kısayol. */
  var menu = { el: null, ogeler: [], odak: -1 };
  function menuAcik() { return !!menu.el && !menu.el.hidden; }
  function menuKapat() {
    if (!menuAcik()) return;
    menu.el.hidden = true;
    menu.ogeler = [];
    $('dy-liste').focus({ preventScroll: true });
  }
  function menuOdak(j) {
    var d = menu.el.querySelectorAll('.dy-menu-oge:not([disabled])');
    if (!d.length) return;
    menu.odak = (j + d.length) % d.length;
    d[menu.odak].focus();
  }
  function menuAc(x, y, ogeler) {
    if (!menu.el) {
      menu.el = el('div', 'dy-menu');
      menu.el.id = 'dy-menu';
      menu.el.setAttribute('role', 'menu');
      menu.el.hidden = true;
      menu.el.addEventListener('keydown', function (e) {
        if (e.key === 'Escape' || e.key === 'Tab') { e.preventDefault(); menuKapat(); }
        else if (e.key === 'ArrowDown') { e.preventDefault(); menuOdak(menu.odak + 1); }
        else if (e.key === 'ArrowUp') { e.preventDefault(); menuOdak(menu.odak - 1); }
        else if (e.key === 'Home') { e.preventDefault(); menuOdak(0); }
        else if (e.key === 'End') { e.preventDefault(); menuOdak(-1); }
        e.stopPropagation();
      });
      document.body.appendChild(menu.el);
    }
    menu.el.textContent = '';
    menu.ogeler = ogeler;
    ogeler.forEach(function (o) {
      if (o === '-') { menu.el.appendChild(el('div', 'dy-menu-ayrac')); return; }
      var b = el('button', 'dy-menu-oge' + (o.tehlike ? ' dy-tehlike' : ''));
      b.type = 'button';
      b.setAttribute('role', 'menuitem');
      b.appendChild(el('span', null, o.ad));
      if (o.tus) b.appendChild(el('kbd', null, o.tus));
      if (o.kapali) b.disabled = true;
      b.addEventListener('click', function () { menuKapat(); o.fn(); });
      menu.el.appendChild(b);
    });
    menu.el.hidden = false;
    var r = menu.el.getBoundingClientRect();
    menu.el.style.left = Math.max(8, Math.min(x, innerWidth - r.width - 8)) + 'px';
    menu.el.style.top = Math.max(8, Math.min(y, innerHeight - r.height - 8)) + 'px';
    menuOdak(0);
  }
  document.addEventListener('mousedown', function (e) { if (menuAcik() && !menu.el.contains(e.target)) menuKapat(); }, true);
  window.addEventListener('blur', menuKapat);
  window.addEventListener('resize', menuKapat);
  $('dy-alan').addEventListener('scroll', menuKapat, { passive: true });

  /* Eklenti kancası: ayrı bir betik (ör. güvenli dosya işlemleri) menüye satır ekleyebilir.
   * Bu dosya diske yazmaz; ekleyen betik kendi kapısını kendi sunucu ucunda taşır. */
  var ekler = [];
  function ekMenu(m, ogeler) {
    ekler.forEach(function (f) {
      try { var s = f(ogeler.slice(), durum.arama ? null : durum.id); if (s && s.length) { m.push('-'); s.forEach(function (o) { m.push(o); }); } }
      catch (e) { console.error('[dosya menü eki]', e); }
    });
  }

  // ── Yuki'ye gönder: kabuğa yalnız kimlik + ad gider, dosyayı kabuk alır (tab-switcher.js) ── //
  var GONDER_AZAMI = 10;
  function yukiIcinde() { try { return window.parent !== window && window.parent.location.origin === location.origin; } catch (e) { return false; } }
  function yukiyeGonder(ogeler) {
    ogeler = ogeler.filter(function (o) { return o && !o.klasor; });
    if (!ogeler.length) return;
    if (!yukiIcinde()) { duyur('Göndermek için dosyayı Yuki içinden aç.'); return; }
    if (ogeler.length > GONDER_AZAMI) { duyur('En çok ' + GONDER_AZAMI + ' dosya gönderilebilir.'); return; }
    window.parent.postMessage({ tur: 'yuki-dosya-gonder', gizli: !!durum.gizli,
      ogeler: ogeler.map(function (o) { return { id: o.id, ad: o.ad, boyut: o.boyut }; }) }, location.origin);
    duyur(ogeler.length + ' dosya Yuki\'ye gönderiliyor…', { bilgi: true });
  }
  // ── Gönder düğmesi (kip şeridi): seçili dosyalar için tek giriş — Yuki'ye gönder · İndir ── //
  function seciliDosyalar() { return seciliOgeler().filter(function (o) { return o && !o.klasor; }); }
  function gonderDurum() {
    var b = $('dy-gonder');
    if (!b) return;
    var d = seciliDosyalar();
    b.disabled = !d.length;
    b.title = d.length ? 'Gönder — ' + (d.length > 1 ? d.length + ' dosya' : d[0].ad) : 'Gönder — önce dosya seç';
  }
  async function indir(ogeler) {
    for (var i = 0; i < ogeler.length; i++) {
      try {
        var b = await bilet(ogeler[i]);
        var a = el('a'); a.href = b.url + '?indir=1'; a.rel = 'noopener';
        document.body.appendChild(a); a.click(); a.remove();
        if (i < ogeler.length - 1) await new Promise(function (ok) { setTimeout(ok, 350); });   // art arda indirme engeline takılmasın
      } catch (e) { duyur(ogeler[i].ad + ': ' + (e.message || 'İndirilemedi.')); }
    }
  }
  $('dy-gonder').addEventListener('click', function () {
    var d = seciliDosyalar();
    if (!d.length) return;
    var r = this.getBoundingClientRect(), dug = this, n = d.length > 1 ? ' (' + d.length + ')' : '';
    dug.setAttribute('aria-expanded', 'true');
    menuAc(r.left, r.bottom + 6, [
      { ad: 'Yuki\'ye gönder' + n, kapali: !yukiIcinde() || d.length > GONDER_AZAMI, fn: function () { yukiyeGonder(d); } },
      { ad: 'İndir' + n, fn: function () { indir(d); } }
    ]);
    // menüyü düğmenin sağ kenarına yasla; menuAc ekrana sıkıştırmayı korur
    if (menu.el) menu.el.style.left = Math.max(8, Math.min(r.right - menu.el.offsetWidth, innerWidth - menu.el.offsetWidth - 8)) + 'px';
    var gozle = setInterval(function () { if (!menuAcik()) { dug.setAttribute('aria-expanded', 'false'); clearInterval(gozle); } }, 200);
  });

  window.yukiDosya = {
    menuEkle: function (f) { if (typeof f === 'function') ekler.push(f); },
    secili: function () { return seciliOgeler(); },
    gizli: function () { return !!durum.gizli; },
    klasor: function () { return durum.arama ? null : durum.id; },
    yenile: function () { return durum.id ? ac(durum.id, false) : Promise.resolve(); },
    duyur: function (metin, secenek) { duyur(metin, secenek); }
  };

  function ogeYolu(g) {
    var taban = durum.yol || '';
    if (g.konum !== undefined) taban = taban.replace(/\/$/, '') + (g.konum ? '/' + g.konum : '');
    return taban.replace(/\/$/, '') + '/' + g.ad;
  }
  function yoluKopyala(yol) {
    if (!navigator.clipboard) { duyur('Pano kullanılamıyor.'); return; }
    navigator.clipboard.writeText(yol).then(function () { duyur('Yol kopyalandı.', { bilgi: true }); },
      function () { duyur('Yol kopyalanamadı.'); });
  }
  function ogeMenusu(x, y) {
    var ogeler = seciliOgeler(), g = ogeler.length === 1 ? ogeler[0] : null;
    var m = [];
    if (g) {
      m.push({ ad: g.klasor ? 'Aç' : 'Önizle', tus: 'Enter', fn: function () { aktif(g); } });
      if (durum.arama) m.push({ ad: 'Bulunduğu klasörü aç', fn: function () { klasorundeGoster(g); } });
      m.push({ ad: 'Yolu kopyala', fn: function () { yoluKopyala(ogeYolu(g)); } });
      if (g.klasor && !g.bag) {
        var yy = ogeYolu(g), var_ = yerimiVar(yy);
        m.push({ ad: var_ ? 'Yer iminden çıkar' : 'Yer imlerine ekle', fn: function () { if (var_) yerimiKaldir(yy); else yerimiEkle(yy, g.ad); } });
      }
    } else if (ogeler.length) {
      m.push({ ad: ogeler.length + ' öğe seçili', kapali: true, fn: function () {} });
    }
    var dosyalar = ogeler.filter(function (o) { return !o.klasor; });
    if (dosyalar.length && dosyalar.length === ogeler.length && yukiIcinde()) {
      m.push('-');
      m.push({ ad: 'Yuki\'ye gönder', kapali: dosyalar.length > GONDER_AZAMI,
               fn: function () { yukiyeGonder(dosyalar); } });
    }
    ekMenu(m, ogeler);
    menuAc(x, y, m);
  }
  function bosMenu(x, y) {
    var m = [];
    if (durum.arama) m.push({ ad: 'Aramayı kapat', tus: 'Esc', fn: aramaKapat });
    if (durum.yol) {
      var var_ = yerimiVar(durum.yol);
      m.push({ ad: var_ ? 'Bu klasörü yer iminden çıkar' : 'Bu klasörü yer imlerine ekle', tus: 'Ctrl+D', kapali: !!durum.arama, fn: yerimiDegistir });
      m.push({ ad: 'Klasör yolunu kopyala', fn: function () { yoluKopyala(durum.yol); } });
    }
    m.push({ ad: 'Hepsini seç', tus: 'Ctrl+A', fn: hepsiniSec });
    ekMenu(m, []);
    menuAc(x, y, m);
  }
  $('dy-alan').addEventListener('contextmenu', function (e) {
    if (matchMedia('(pointer: coarse)').matches && !e.button) { /* uzun basış da contextmenu üretir — aynı menü */ }
    e.preventDefault();
    var li = e.target.closest('.dy-oge');
    if (li) {
      var i = +li.dataset.i, g = durum.girdiler[i];
      if (g && !durum.cok.has(g.id)) secimYap(i, false);
      ogeMenusu(e.clientX, e.clientY);
    } else bosMenu(e.clientX, e.clientY);
  });
  function menuKlavyeden() {
    var li = $('dy-o-' + durum.secili);
    if (li) { var r = li.getBoundingClientRect(); ogeMenusu(r.left + 40, r.bottom - 4); }
    else { var a = $('dy-alan').getBoundingClientRect(); bosMenu(a.left + 40, a.top + 60); }
  }

  // ── F5 · Süz (yüklü satırlar, istemcide) ──────────────────────── //
  function suzUyar(g) { return g.ad.toLocaleLowerCase('tr').indexOf(durum.suz) >= 0; }
  function gorunurAdim(s, yon) {
    for (var j = s + yon; j >= 0 && j < durum.girdiler.length; j += yon) if (suzUyar(durum.girdiler[j])) return j;
    return -1;
  }
  function suzUygula() {
    var l = $('dy-liste').children, n = 0;
    for (var k = 0; k < l.length; k++) {
      var g = durum.girdiler[+l[k].dataset.i], uy = !durum.suz || (g && suzUyar(g));
      l[k].hidden = !uy; if (uy) n++;
    }
    $('dy-panel-sayi').textContent = durum.toplam + ' öğe' + (durum.suz ? ' · ' + n + ' eşleşti' : '');
    $('dy-durum').textContent = durum.suz && !n ? 'Süzgece uyan öğe yok.' : (durum.toplam === 0 ? 'Bu klasör boş.' : '');
    if (durum.suz && n && (durum.secili < 0 || !suzUyar(durum.girdiler[durum.secili]))) { var j = gorunurAdim(-1, 1); if (j >= 0) secimYap(j, true, 'imlec'); }
  }
  $('dy-suz').addEventListener('input', function () { durum.suz = this.value.trim().toLocaleLowerCase('tr'); suzUygula(); });
  $('dy-suz').addEventListener('keydown', function (e) {
    if (e.key === 'Escape') { e.preventDefault(); this.value = ''; durum.suz = ''; if (durum.arama) aramaKapat(); else suzUygula(); $('dy-liste').focus({ preventScroll: true }); }
    else if (e.key === 'Enter' && this.value.trim()) { e.preventDefault(); aramaYap(this.value.trim()); }
    else if (e.key === 'Enter' || e.key === 'ArrowDown') { e.preventDefault(); $('dy-liste').focus({ preventScroll: true }); }
  });

  // ── F5 · Sütun gezgini: üst klasör sütunları (Taslak B) ─────────────── //
  // Açık klasör (liste) son sütundur; seçim/klavye/düzenleme ona bağlı kalır. Solunda kırıntının son 1-2 atası
  // salt okunur sütun: sütun başına TEK liste GET'i (ilk 200), sonuç önbellekte (sıra/yön/gizli anahtarlı).
  var ataOnbellek = {}, ataSira = 0;
  function ataSayisi() { return window.innerWidth >= 1380 ? 2 : window.innerWidth >= 1100 ? 1 : 0; }
  async function atalariCiz() {
    var kap = $('dy-atalar'), k = durum.kirinti || [], n = ataSayisi(), benim = ++ataSira;
    var atalar = k.slice(Math.max(0, k.length - 1 - n), k.length - 1);
    document.body.dataset.ata = String(atalar.length);
    var parcalar = await Promise.all(atalar.map(function (a) {
      var ank = a.id + '|' + durum.sira + '|' + durum.yon + '|' + (durum.gizli ? 1 : 0);
      if (ataOnbellek[ank]) return ataOnbellek[ank];
      return (ataOnbellek[ank] = json('/api/dosya/liste/' + a.id + '?offset=0&limit=' + SAYFA + '&sira=' + durum.sira +
        '&yon=' + durum.yon + (durum.gizli ? '&gizli=1' : '')).catch(function () { delete ataOnbellek[ank]; return null; }));
    }));
    if (benim !== ataSira) return;
    kap.textContent = '';
    atalar.forEach(function (a, j) {
      var d = parcalar[j], sonraki = k[k.length - atalar.length + j];
      var sut = el('div', 'dy-ata');
      sut.setAttribute('role', 'group');
      sut.setAttribute('aria-label', a.ad);
      var bas = el('div', 'dy-ata-bas');
      bas.appendChild(el('span', null, a.ad));
      bas.appendChild(el('small', null, d ? String(d.toplam) : '—'));
      sut.appendChild(bas);
      (d ? d.girdiler : []).forEach(function (g) {
        var b = el('button', 'dy-ata-oge' + (sonraki && g.id === sonraki.id ? ' dy-ata-yol' : ''));
        b.type = 'button';
        if (sonraki && g.id === sonraki.id) b.setAttribute('aria-current', 'location');
        b.appendChild(ikon(g.klasor ? 'klasor' : (IKON[g.tur] || 'dosya')));
        b.appendChild(el('span', null, g.ad));
        if (g.klasor) { var o = ikon('sag'); o.setAttribute('class', 'dy-ok'); b.appendChild(o); b.dataset.id = g.id; }
        else b.appendChild(el('small', null, boyutYaz(g.boyut)));
        b.addEventListener('click', function () {
          if (g.klasor) ac(g.id);
          else ac(a.id).then(function () { var i = durum.girdiler.findIndex(function (x) { return x.id === g.id; }); if (i >= 0) secimYap(i); });
        });
        sut.appendChild(b);
      });
      kap.appendChild(sut);
      var yol = sut.querySelector('.dy-ata-yol');
      if (yol) yol.scrollIntoView({ block: 'nearest' });
    });
  }
  var ataBoy = 0;
  window.addEventListener('resize', function () {
    clearTimeout(ataBoy);
    ataBoy = setTimeout(function () { if (String(Math.min(ataSayisi(), Math.max(0, (durum.kirinti || []).length - 1))) !== document.body.dataset.ata) atalariCiz(); }, 200);
  });

  // ── Yol yazma ────────────────────────────────────────────────── //
  function yolDuzenle() {
    var f = $('dy-yol-form'), inp = $('dy-yol');
    $('dy-kirinti').hidden = true;
    f.hidden = false;
    inp.value = durum.yol || '';
    inp.focus();
    inp.select();
  }
  function yolBitir() {
    $('dy-yol-form').hidden = true;
    $('dy-kirinti').hidden = false;
    $('dy-liste').focus({ preventScroll: true });
  }
  $('dy-kirinti').addEventListener('click', yolDuzenle);
  $('dy-yol').addEventListener('keydown', function (e) { if (e.key === 'Escape') yolBitir(); });
  $('dy-yol').addEventListener('blur', function () { setTimeout(yolBitir, 120); });
  $('dy-yol-form').addEventListener('submit', async function (e) {
    e.preventDefault();
    try {
      var d = await json('/api/dosya/git', { method: 'POST', headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ yol: $('dy-yol').value, gizli: durum.gizli }) });
      yolBitir();
      if (d.klasor) ac(d.id);
      else duyur('Bu bir dosya — klasörü açıp seçin.');
    } catch (err) { duyur(err.message || 'Yol açılamadı.'); }
  });

  // ── Önizleme ─────────────────────────────────────────────────── //
  var onizlemeSira = 0, onizZaman = 0;
  // F2 · Taslak B: ≥1100 px önizleme sütunu hep açık (kapat düğmesi yok, Esc onu kapatmaz); telefonda alt sayfa.
  var SABIT = window.matchMedia('(min-width: 1100px)');
  function onizleGecikmeli(g) { clearTimeout(onizZaman); onizZaman = setTimeout(function () { onizle(g); }, 160); }
  function onizlemeBos() {
    clearTimeout(onizZaman);
    ++onizlemeSira;
    var ic = $('dy-on-icerik'), v = ic.querySelector('video');
    if (v) { v.pause(); v.removeAttribute('src'); v.load(); }
    ic.textContent = '';
    $('dy-on-ad').textContent = 'Bir öğe seç';
    $('dy-on-bilgi').textContent = '';
    ic.appendChild(ikon('dosya'));
    ic.appendChild(el('p', 'dy-on-not', 'Tıkla ya da oklarla seç — içeriği burada görünür. Klasörü açmak için çift tık ya da Enter.'));
    $('dy-on-indir').hidden = true;
    $('dy-on-gonder').hidden = true;
    $('dy-onizleme').classList.add('dy-on-bos');
  }
  function sabitUygula() {
    var s = SABIT.matches;
    document.body.classList.toggle('dy-on-sabit', s);
    if (s) {
      durum.onizlemeAcik = true;
      $('dy-onizleme').hidden = false;
      document.body.classList.add('dy-on-acik');
      if (durum.secili < 0 || !$('dy-on-ad').textContent) onizlemeBos();
    } else if (durum.onizlemeAcik) {
      durum.onizlemeAcik = false;
      $('dy-onizleme').hidden = true;
      document.body.classList.remove('dy-on-acik');
    }
  }
  if (SABIT.addEventListener) SABIT.addEventListener('change', sabitUygula);
  function onizlemeAcKapa() {
    if (SABIT.matches) onizle(durum.girdiler[durum.secili]);
    else if (durum.onizlemeAcik) onizlemeKapat();
    else onizle(durum.girdiler[durum.secili], true);
  }
  function onizlemeKapat() {
    if (SABIT.matches) { onizlemeBos(); $('dy-liste').focus({ preventScroll: true }); return; }
    durum.onizlemeAcik = false;
    $('dy-onizleme').hidden = true;
    var ic = $('dy-on-icerik');
    var v = ic.querySelector('video');
    if (v) { v.pause(); v.removeAttribute('src'); v.load(); }
    ic.textContent = '';
    document.body.classList.remove('dy-on-acik');
    $('dy-liste').focus({ preventScroll: true });
  }

  async function bilet(g) {
    return json('/api/dosya/bilet/' + g.id + (durum.gizli ? '?gizli=1' : ''));
  }

  async function onizle(g, ac_) {
    if (!g) return;
    clearTimeout(onizZaman);
    $('dy-onizleme').classList.remove('dy-on-bos');
    if (ac_) { durum.onizlemeAcik = true; $('dy-onizleme').hidden = false; document.body.classList.add('dy-on-acik'); }
    var benim = ++onizlemeSira;
    var ic = $('dy-on-icerik');
    var eskiV = ic.querySelector('video');
    if (eskiV) { eskiV.pause(); eskiV.removeAttribute('src'); eskiV.load(); }
    ic.textContent = '';
    $('dy-on-ad').textContent = g.ad;
    $('dy-on-indir').hidden = g.klasor;
    $('dy-on-gonder').hidden = g.klasor || !yukiIcinde();
    var bilgi = $('dy-on-bilgi');
    bilgi.textContent = '';
    function satirEkle(a, b) { bilgi.appendChild(el('dt', null, a)); bilgi.appendChild(el('dd', null, b)); }
    satirEkle('Tür', g.klasor ? 'Klasör' : g.tur);
    if (!g.klasor) { satirEkle('Boyut', boyutYaz(g.boyut)); bilgi.lastChild.className = 'dy-veri'; }
    satirEkle('Değiştirilme', tarihYaz(g.tarih));
    bilgi.lastChild.className = 'dy-mono';
    var sg = durum.gizli ? '&gizli=1' : '';
    try {
      if (g.klasor) {
        ic.appendChild(ikon('klasor'));
        ic.appendChild(el('p', 'dy-on-not', 'Açmak için Enter'));
      } else if (g.tur === 'resim') {
        var r = await api('/api/dosya/onizle/' + g.id + '?k=800' + sg);
        if (!r.ok) throw new Error((await r.json()).detail || 'Önizlenemedi');
        var u = URL.createObjectURL(await r.blob());
        if (benim !== onizlemeSira) { URL.revokeObjectURL(u); return; }
        havuzaEkle(u);
        var img = el('img'); img.alt = g.ad; img.src = u; ic.appendChild(img);
      } else if (g.tur === 'metin') {
        var d = await json('/api/dosya/onizle/' + g.id + '?' + sg.slice(1));
        if (benim !== onizlemeSira) return;
        ic.appendChild(el('pre', 'dy-on-metin', d.metin));
        if (d.kesildi) ic.appendChild(el('p', 'dy-on-not', 'İlk 64 KB gösteriliyor.'));
      } else if (g.tur === 'video' || g.tur === 'ses') {
        var b = await bilet(g);
        if (benim !== onizlemeSira) return;
        var v = el(g.tur === 'video' ? 'video' : 'audio');
        v.controls = true; v.preload = 'metadata'; v.src = b.url;
        ic.appendChild(v);
      } else if (g.tur === 'pdf') {
        var b2 = await bilet(g);
        if (benim !== onizlemeSira) return;
        var f = el('iframe', 'dy-on-pdf'); f.title = g.ad; f.src = b2.url;
        ic.appendChild(f);
      } else {
        ic.appendChild(ikon(IKON[g.tur] || 'dosya'));
        ic.appendChild(el('p', 'dy-on-not', 'Önizleme yok — indirebilirsin.'));
      }
    } catch (e) {
      if (benim !== onizlemeSira) return;
      ic.textContent = '';
      ic.appendChild(el('p', 'dy-on-not', e.message || 'Önizlenemedi.'));
    }
  }

  $('dy-on-kapat').addEventListener('click', onizlemeKapat);
  // Telefonda alt sayfanın arkasındaki karartmaya dokunmak kapatır
  document.addEventListener('click', function (e) { if (durum.onizlemeAcik && !SABIT.matches && e.target === document.body) onizlemeKapat(); });
  $('dy-on-indir').addEventListener('click', async function () {
    var g = durum.girdiler[durum.secili];
    if (!g || g.klasor) return;
    try {
      var b = await bilet(g);
      var a = el('a'); a.href = b.url + '?indir=1'; a.rel = 'noopener';
      document.body.appendChild(a); a.click(); a.remove();
    } catch (e) { duyur(e.message || 'İndirilemedi.'); }
  });

  $('dy-on-gonder').addEventListener('click', function () {
    var g = durum.girdiler[durum.secili];
    if (g && !g.klasor) yukiyeGonder([g]);
  });

  // ── Tema: Grimoire (varsayılan) ⇄ Klasik (css/tema.css) ── //
  var TEMALAR = ['grimoire', 'klasik'];
  var TEMA_AD = { grimoire: 'Grimoire', klasik: 'Klasik' };
  function temaUygula(t) {
    if (TEMALAR.indexOf(t) < 0) t = 'grimoire';
    document.documentElement.dataset.tema = t;
    try { localStorage.setItem('yukiTema_v1', t); } catch (e) {}
    $('dy-tema').title = 'Tema: ' + TEMA_AD[t] + ' (değiştir)';
  }
  $('dy-tema').addEventListener('click', function () {
    var i = TEMALAR.indexOf(document.documentElement.dataset.tema);
    temaUygula(TEMALAR[(i + 1) % TEMALAR.length]);
  });
  temaUygula(document.documentElement.dataset.tema || 'grimoire');

  // ── Araç çubuğu ──────────────────────────────────────────────── //
  $('dy-geri').addEventListener('click', geri);
  $('dy-ileri').addEventListener('click', ileri);
  $('dy-yukari').addEventListener('click', yukari);
  $('dy-sira').addEventListener('change', function () { durum.sira = this.value; yaz('dy_sira_v1', durum.sira); ac(durum.id, false); });
  $('dy-yon').addEventListener('click', function () {
    durum.yon = durum.yon === 'artan' ? 'azalan' : 'artan'; yaz('dy_yon_v1', durum.yon); gorunumUygula(); ac(durum.id, false);
  });
  $('dy-gizli').addEventListener('click', function () {
    durum.gizli = !durum.gizli; yaz('dy_gizli_v1', durum.gizli ? '1' : '0'); gorunumUygula(); ac(durum.id, false);
  });
  $('dy-gorunum').addEventListener('click', function () {
    durum.gorunum = durum.gorunum === 'liste' ? 'izgara' : 'liste'; yaz('dy_gorunum_v1', durum.gorunum);
    gorunumUygula(); var s = durum.secili; ac(durum.id, false).then(function () { if (s >= 0) secimYap(s); });
  });

  // ── F4 · Telefon alt gezinti ─────────────────────────────────── //
  // Kökler/Sırala paneli yalnız var olan denetimlere vekâlet eder: kök düğmesine tıklar, #dy-sira'yı değiştirir.
  var telKip = null;
  function telPanel(kip) {
    var p = $('dy-tel-panel');
    telKip = kip && kip !== telKip ? kip : null;
    p.textContent = '';
    if (telKip === 'kokler') {
      p.setAttribute('aria-label', 'Kökler');
      document.querySelectorAll('#dy-kokler .dy-kok').forEach(function (k) {
        var b = el('button', 'dy-tel-sec', k.textContent);
        b.type = 'button';
        b.insertBefore(ikon('klasor'), b.firstChild);
        if (k.classList.contains('dy-aktif')) b.setAttribute('aria-current', 'true');
        b.addEventListener('click', function () { telPanel(null); k.click(); });
        p.appendChild(b);
      });
    } else if (telKip === 'sira') {
      p.setAttribute('aria-label', 'Sırala');
      [].forEach.call($('dy-sira').options, function (o) {
        var b = el('button', 'dy-tel-sec', o.textContent);
        b.type = 'button';
        b.setAttribute('aria-pressed', String(o.value === durum.sira));
        b.addEventListener('click', function () {
          telPanel(null);
          if (o.value !== durum.sira) { $('dy-sira').value = o.value; $('dy-sira').dispatchEvent(new Event('change')); }
        });
        p.appendChild(b);
      });
      var y = el('button', 'dy-tel-sec dy-tel-yon', durum.yon === 'artan' ? 'Yön: artan ↑' : 'Yön: azalan ↓');
      y.type = 'button';
      y.addEventListener('click', function () { telPanel(null); $('dy-yon').click(); });
      p.appendChild(y);
    }
    p.hidden = !telKip;
    $('dy-t-kokler').setAttribute('aria-expanded', String(telKip === 'kokler'));
    $('dy-t-sira').setAttribute('aria-expanded', String(telKip === 'sira'));
  }
  $('dy-t-geri').addEventListener('click', function () { telPanel(null); geri(); });
  $('dy-t-ust').addEventListener('click', function () { telPanel(null); yukari(); });
  $('dy-t-kokler').addEventListener('click', function (e) { e.stopPropagation(); telPanel('kokler'); });
  $('dy-t-sira').addEventListener('click', function (e) { e.stopPropagation(); telPanel('sira'); });
  document.addEventListener('click', function (e) {
    if (telKip && !$('dy-tel-panel').contains(e.target)) telPanel(null);
  });
  document.addEventListener('keydown', function (e) { if (e.key === 'Escape' && telKip) telPanel(null); });
  $('dy-ara-ac').addEventListener('click', function () {
    var ac_ = document.body.classList.toggle('dy-tel-suz');
    this.setAttribute('aria-expanded', String(ac_));
    if (ac_) $('dy-suz').focus();
  });

  if ('IntersectionObserver' in window) {
    new IntersectionObserver(function (ks) {
      if (ks[0].isIntersecting && durum.id) sayfaYukle(false);
    }, { rootMargin: '400px' }).observe($('dy-sentinel'));
  }

  // ── Açılış ───────────────────────────────────────────────────── //
  async function basla() {
    gorunumUygula();
    sabitUygula();
    try {
      var d = await json('/api/dosya/kokler');
      durum.kokler = d.kokler;
      var kap = $('dy-kokler');
      d.kokler.forEach(function (k) {
        var b = el('button', 'dy-kok', k.ad);
        b.type = 'button';
        b.title = k.yol;
        b.dataset.id = k.id;
        b.setAttribute('role', 'tab');
        b.insertBefore(ikon('klasor'), b.firstChild);
        b.addEventListener('click', function () { ac(k.id); });
        kap.appendChild(b);
      });
      yerimiCiz();
      if (!d.kokler.length) { $('dy-durum').textContent = 'Ayarlı kök yok.'; return; }
      var hash = location.hash.slice(1);
      await ac(/^[0-9a-f]{16}$/.test(hash) ? hash : d.kokler[0].id, false);
      if (!durum.kirinti.length) await ac(d.kokler[0].id, false);
      $('dy-liste').focus({ preventScroll: true });
    } catch (e) {
      $('dy-durum').textContent = e.durum === 401 ? 'Giriş gerekli (Yuki ana ekranından giriş yap).' : (e.message || 'Bağlanılamadı.');
    }
  }
  basla();
})();
