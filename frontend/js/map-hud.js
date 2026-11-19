/* ════════════════════════════════════════════════════════════════════════
   map-hud.js — HARİTA ÖNCE: yüzen yüzeylerin denetçisi (2026-10-04)

   Kaynak: kişisel AliceAi `frontend/js/map-hud.js` @ 8dd7587 (09-28, Taslak A).
   Klasik script (defer YOK); map-engine.js'ten
   ÖNCE yüklenir — `toggleLayer`/`toggleLayerMgr`'ı yalnız çağrı anında arar.
   Global: mapKatmanCekmece · mapGundemAc · mapAraAc · mapSeritAc · mapKatmanSay
           · mapBosBasla · mapYakinGuncelle · mapYakinSor · mapKonumumaDon (Gözlemevi, 11-13)

   Ne yapar: KATMANLAR çekmecesini, GÜNDEM kartını ve konum aramasını açar/
   kapar; katman sayaçlarını (grup "açık/toplam" + düğmedeki "N açık")
   satırların `aria-checked`inden sayar.
   Ne YAPMAZ: katman açıp kapatmaz — o `toggleLayer` (map-engine.js); bu dosya
   onun bıraktığı `aria-checked`i okur. Sekme geçişine dokunmaz (tek sahip
   tab-nav.js; görünürlük `hidden` özniteliği, `tabchange` olayı).

   Ürüne taşınırken değişen iki şey:
     · Kişisel görünürlüğü `style.display`den okuyordu; üründe `hidden`.
     · Kişiseldeki 09-18 sürümünde bu dosya yalnız sol/sağ panel katlama
       tutamaçlarıydı (mapHudToggle). İki panel de kalktı → o mantık da.

   Durum: localStorage `yukiHarita_v1` = { katman: bool, gundem: bool } —
   yalnız masaüstü. Telefonda her açılış kapalı başlar (iki sayfa haritanın
   üstünü kapatmasın). Eski anahtarlar (mapPanelLeft/Right, mapModeBar) ilk
   kurulumda silinir.
   ════════════════════════════════════════════════════════════════════════ */
(function () {
  'use strict';
  var ANAHTAR = 'yukiHarita_v1';
  var telMQ = window.matchMedia ? window.matchMedia('(max-width: 768px)') : null;

  function tab() { return document.getElementById('tab-map'); }
  function gorunur() { var t = tab(); return !!(t && !t.hidden); }
  function tel() { return !!(telMQ && telMQ.matches); }
  function oku() {
    try { return JSON.parse(localStorage.getItem(ANAHTAR) || '{}') || {}; } catch (e) { return {}; }
  }
  function yaz(k, v) {
    var d = oku(); d[k] = v;
    try { localStorage.setItem(ANAHTAR, JSON.stringify(d)); } catch (e) {}
  }
  function aria(id, acik) {
    var b = document.getElementById(id);
    if (b) b.setAttribute('aria-expanded', acik ? 'true' : 'false');
  }

  // ── Sayaçlar ────────────────────────────────────────────────────────────
  window.mapKatmanSay = function () {
    var t = tab(); if (!t) return;
    var toplam = 0;
    t.querySelectorAll('.mk-grup').forEach(function (g) {
      var n = g.querySelectorAll('.mk-satir[aria-checked="true"]').length;
      var b = g.querySelector('.mk-grup-sayi b');
      if (b) b.textContent = String(n);
      g.classList.toggle('mk-grup-acik', n > 0);
      toplam += n;
    });
    var s = document.getElementById('map-katman-sayi');
    if (s) s.textContent = String(toplam);
    var k = document.getElementById('map-katman-ac');
    if (k) k.classList.toggle('mh-var', toplam > 0);
    var bos = document.getElementById('map-bos');          // boş durum yalnız 0 katmanda
    if (bos) bos.hidden = toplam > 0;
    if (typeof window.mapYakinGuncelle === 'function') window.mapYakinGuncelle();   // deprem kapanınca YAKINDA da söylesin
  };

  // ── Boş durum: deprem + ISS'i aç (açık olanı kapatmaz — toggleLayer aç/kapa yapar) ──
  window.mapBosBasla = function () {
    if (typeof toggleLayer !== 'function') return;
    ['eq', 'iss'].forEach(function (k) {
      var b = document.getElementById('map-layer-' + k);
      if (b && b.getAttribute('aria-checked') !== 'true') toggleLayer(k);
    });
  };

  // ── KATMANLAR çekmecesi ─────────────────────────────────────────────────
  window.mapKatmanCekmece = function (ac) {
    var t = tab(); if (!t) return;
    if (typeof ac !== 'boolean') ac = !t.classList.contains('katman-acik');
    t.classList.toggle('katman-acik', ac);
    aria('map-katman-ac', ac);
    if (ac && tel()) window.mapGundemAc(false);          // telefonda iki sayfa üst üste binmez
    if (!ac) {                                            // yönetici çekmecenin üstünde açılır — birlikte kapanır
      var m = document.getElementById('map-layer-mgr');
      if (m && m.classList.contains('open') && typeof toggleLayerMgr === 'function') toggleLayerMgr();
    }
    if (!tel()) yaz('katman', ac);
    _sagGenislik();
    if (ac) requestAnimationFrame(_cekmeceSonu);
  };

  // ── GÜNDEM kartı ────────────────────────────────────────────────────────
  window.mapGundemAc = function (ac) {
    var g = document.getElementById('map-gundem'); if (!g) return;
    if (typeof ac !== 'boolean') ac = !g.classList.contains('acik');
    g.classList.toggle('acik', ac);
    aria('map-gundem-bas', ac);
    if (ac && tel()) window.mapKatmanCekmece(false);
    if (!tel()) yaz('gundem', ac);
  };

  // ── Konum araması ───────────────────────────────────────────────────────
  window.mapAraAc = function (ac) {
    var t = tab(); if (!t) return;
    if (typeof ac !== 'boolean') ac = !t.classList.contains('ara-acik');
    t.classList.toggle('ara-acik', ac);
    aria('map-ara-ac', ac);
    var i = document.getElementById('map-search-input');
    if (ac && i) setTimeout(function () { i.focus(); if (i.select) i.select(); }, 30);
    if (!ac && i && document.activeElement === i) {
      var b = document.getElementById('map-ara-ac'); if (b) b.focus();
    }
  };

  // ── Yer şeridinin tamamı (yalnız telefonda anlamlı: masaüstünde şerit sarar,
  //    hiçbir bölüm gizlenmez) ─────────────────────────────────────────────
  window.mapSeritAc = function (ac) {
    var s = document.getElementById('map-serit'); if (!s) return;
    if (typeof ac !== 'boolean') ac = !s.classList.contains('acik');
    s.classList.toggle('acik', ac);
    aria('map-serit-ac', ac);
    _sagGenislik();
  };

  // Telefonda GÜNDEM başlığı, sağdaki düğme grubunun (⌕ + KATMANLAR) solunda biter;
  // masaüstünde yer şeridi sağ üst grubun solunda biter. İkisinin genişliği de yazıya
  // (ve dile) bağlı — CSS'te sabit sayı yerine ölçülüp değişkene yazılır
  // (--mh-sag-gen / --mh-sag-ust-gen). Sekme gizliyken genişlik 0 ölçülür → atlanır.
  function _sagGenislik() {
    var t = tab(), s = document.getElementById('map-sag-ust');
    if (!t || !s || !gorunur()) return;
    var w = 0;
    ['map-ara-ac', 'map-katman-ac'].forEach(function (id) {
      var e = document.getElementById(id); if (e) w += e.getBoundingClientRect().width;
    });
    var v = Math.ceil(w + 8 + 16) + 'px';
    var u = Math.ceil(s.getBoundingClientRect().width) + 'px';   // masaüstü: şeridin sağ sınırı
    if (w > 0 && t.style.getPropertyValue('--mh-sag-gen') !== v) t.style.setProperty('--mh-sag-gen', v);
    if (!tel() && parseInt(u, 10) > 0 && t.style.getPropertyValue('--mh-sag-ust-gen') !== u) t.style.setProperty('--mh-sag-ust-gen', u);
    // Şerit dar masaüstünde ikinci satıra sarabilir → ROTA kartı onun GERÇEK altına
    var sr = document.getElementById('map-serit');
    _seritSatirlari(sr);
    if (sr && sr.offsetHeight > 0) {
      var a = (sr.offsetTop + sr.offsetHeight + 8) + 'px';
      if (t.style.getPropertyValue('--mh-serit-alt') !== a) t.style.setProperty('--mh-serit-alt', a);
    }
  }

  // Sarmada ayraç satır başında olmaz: her satırın ilk görünür bölümü işaretlenir
  // (ayraç CSS'te bölümün SOL kenarında). `mh-sarili` → satırlar boşluksuz dolar.
  function _seritSatirlari(sr) {
    if (!sr || sr.offsetHeight === 0) return;
    var onceki = null, sarili = false;
    sr.querySelectorAll('.mh-bolum').forEach(function (b) {
      b.classList.remove('mh-satir-basi');
      if (b.offsetParent === null) return;                 // gizli bölüm (telefonda kapalıyken)
      if (onceki && b.offsetTop > onceki.offsetTop + 4) { b.classList.add('mh-satir-basi'); sarili = true; }
      onceki = b;
    });
    sr.classList.toggle('mh-sarili', sarili);
  }

  // KATMANLAR çekmecesi: altta devam eden satır varken solma (CSS maskesi); sonda kalkar
  function _cekmeceSonu() {
    var ic = document.querySelector('#map-katman-cekmece .mk-ic');
    if (ic) ic.classList.toggle('mk-sonda', ic.scrollTop + ic.clientHeight >= ic.scrollHeight - 2);
  }
  document.addEventListener('scroll', function (e) {
    if (e.target && e.target.classList && e.target.classList.contains('mk-ic')) _cekmeceSonu();
  }, true);

  // Esc: arama → yönetici → çekmece sırasıyla kapanır. Yalnız HARİTA görünürken
  // ve sekme menüsü açık değilken (menünün kendi Esc'i var, yakalama evresinde).
  document.addEventListener('keydown', function (e) {
    if (e.key !== 'Escape' || !gorunur() || document.body.classList.contains('nav-acik')) return;
    var t = tab();
    if (t.classList.contains('ara-acik')) { window.mapAraAc(false); return; }
    var m = document.getElementById('map-layer-mgr');
    if (m && m.classList.contains('open') && typeof toggleLayerMgr === 'function') { toggleLayerMgr(); return; }
    if (t.classList.contains('katman-acik')) { window.mapKatmanCekmece(false); return; }
    if (tel()) { var g = document.getElementById('map-gundem'); if (g && g.classList.contains('acik')) window.mapGundemAc(false); }
  });

  // ── YAKINDA · DÜNYA · GÜNDEM (Gözlemevi "Kubbe", kişiselden 11-13) ──────────
  // Veri yeni uç DEĞİL: deprem katmanının son yanıtı (map-engine `window._mapEqSon`),
  // ISS uzaklığı ve Kp şeridin yazdığı alanlardan okunur. Dış metin (yer adı)
  // yalnız esc() ile girer. Konum = map-engine'in bildiği konum; burada hiçbir
  // konum kaydedilmez ya da dışarı gönderilmez.
  var YK = { km: 300, saat: 24 };
  var _ykSecili = null;
  /* Çeviri: sözlükte yoksa dil.js anahtarın kendisini döndürür → Türkçe yedek */
  function _t(anahtar, tr, d) {
    var m = (window.YukiDil && window.YukiDil.t) ? window.YukiDil.t(anahtar, d) : anahtar;
    if (m !== anahtar) return m;
    return String(tr).replace(/\{(\w+)\}/g, function (x, a) { return d && Object.prototype.hasOwnProperty.call(d, a) ? String(d[a]) : x; });
  }
  function yerel() { return (window.YukiDil && window.YukiDil.yerel) ? window.YukiDil.yerel() : 'tr-TR'; }
  function esc(t) { return (typeof _escHtml === 'function') ? _escHtml(t) : String(t == null ? '' : t).replace(/[&<>"']/g, function (c) { return '&#' + c.charCodeAt(0) + ';'; }); }
  function km(a, b, c, d) {
    var r = Math.PI / 180, x = Math.sin((c - a) * r / 2), y = Math.sin((d - b) * r / 2);
    return 6371 * 2 * Math.asin(Math.sqrt(x * x + Math.cos(a * r) * Math.cos(c * r) * y * y));
  }
  var YONLER = [['k', 'kuzey'], ['kd', 'kuzeydoğu'], ['d', 'doğu'], ['gd', 'güneydoğu'], ['g', 'güney'], ['gb', 'güneybatı'], ['b', 'batı'], ['kb', 'kuzeybatı']];
  function yon(a, b, c, d) {   // a,b = sen; c,d = olay → olay senin neresinde
    var r = Math.PI / 180, y = Math.sin((d - b) * r) * Math.cos(c * r),
        x = Math.cos(a * r) * Math.sin(c * r) - Math.sin(a * r) * Math.cos(c * r) * Math.cos((d - b) * r);
    var y8 = YONLER[Math.round(((Math.atan2(y, x) / r + 360) % 360) / 45) % 8];
    return _t('harita.yon-' + y8[0], y8[1]);
  }
  function once(ms) {
    var dk = Math.max(0, Math.round((Date.now() - ms) / 60000));
    return dk < 60 ? _t('harita.once-dk', '{n} dk', { n: dk })
      : dk < 1440 ? _t('harita.once-sa', '{n} sa', { n: Math.round(dk / 60) })
      : _t('harita.once-gun', '{n} gün', { n: Math.round(dk / 1440) });
  }
  function sayi(n, h) { return Number(n).toLocaleString(yerel(), { minimumFractionDigits: h, maximumFractionDigits: h }); }
  var KAYNAK = { afad: 'AFAD', sismik: 'Kandilli/EMSC' };
  function konum() {
    var la = (typeof _mapUserLat !== 'undefined') ? _mapUserLat : null, lo = (typeof _mapUserLon !== 'undefined') ? _mapUserLon : null;
    return la === null || lo === null ? null : [la, lo];
  }
  function olaylar() {
    var fs = window._mapEqSon || [], k = konum();
    return fs.map(function (f) {
      var c = (f.geometry && f.geometry.coordinates) || [], p = f.properties || {};
      var o = { lon: +c[0], lat: +c[1], der: +c[2] || 0, mag: +p.mag, yer: String(p.place || ''), t: +p.time || 0, kay: KAYNAK[p.src] || 'USGS' };
      if (k) { o.km = km(k[0], k[1], o.lat, o.lon); o.yon = yon(k[0], k[1], o.lat, o.lon); }
      return o;
    }).filter(function (o) { return isFinite(o.lat) && isFinite(o.lon) && isFinite(o.mag); });
  }
  function satirDeprem(o, uzak) {
    var yeni = o.t && Date.now() - o.t < 3600000;
    var alt = (o.km != null ? sayi(o.km, 0) + ' km ' + (uzak ? '' : o.yon + ' · ') : '') +
      _t('harita.yakin-derinlik', '{n} km derinlik', { n: sayi(o.der, 0) }) + ' · ' + o.kay;
    return '<li><button type="button" class="mh-olay' + (yeni ? ' yeni' : '') + (_ykSecili === o.lat + ',' + o.lon ? ' secili' : '') +
      '" data-lat="' + o.lat + '" data-lon="' + o.lon + '">' +
      '<span class="mh-o-tur">M ' + sayi(o.mag, 1) + '</span>' +
      '<span class="mh-o-ne">' + esc(o.yer.replace(/\s*\((AFAD|Kandilli|EMSC)\)\s*$/i, '')) + '<small>' + esc(alt) + '</small></span>' +
      '<time>' + (o.t ? esc(once(o.t)) : '—') + '</time></button></li>';
  }
  function satirBilgi(tur, ne, alt, sag, notr) {
    return '<li><div class="mh-olay mh-bilgi"><span class="mh-o-tur' + (notr ? ' notr' : '') + '">' + esc(tur) + '</span>' +
      '<span class="mh-o-ne">' + esc(ne) + '<small>' + esc(alt) + '</small></span><time>' + esc(sag) + '</time></div></li>';
  }
  function metin(id) { var e = document.getElementById(id); return e ? e.textContent.trim() : ''; }
  window.mapYakinGuncelle = function () {
    var yl = document.getElementById('map-yakin-list'), dl = document.getElementById('map-dunya-list');
    if (!yl || !dl) return;
    var eqAcik = (typeof _layerActive !== 'undefined') && !!_layerActive.eq;
    var hepsi = eqAcik ? olaylar() : [], k = konum(), h = '';
    if (!eqAcik) {
      h += '<li class="mh-bos mh-bos-dugme">' + esc(_t('harita.yakin-deprem-kapali', 'Deprem katmanı kapalı.')) +
        ' <button type="button" data-yk-ac="eq">' + esc(_t('harita.yakin-deprem-ac', 'Depremleri aç')) + '</button></li>';
    } else {
      var simdi = Date.now(), pen = YK.saat * 3600000;
      var yakin = hepsi.filter(function (o) { return o.km != null && o.km <= YK.km && (!o.t || simdi - o.t <= pen); });
      yakin.sort(function (a, b) { return (a.km / YK.km + (simdi - a.t) / pen) - (b.km / YK.km + (simdi - b.t) / pen); });
      if (!k) h += '<li class="mh-bos">' + esc(_t('harita.yakin-konum-yok', 'Konum bekleniyor — yakınlık hesaplanamıyor.')) + '</li>';
      else if (!yakin.length) h += '<li class="mh-bos">' + esc(_t('harita.yakin-olay-yok', 'Son 24 saatte {km} km içinde M ≥ 2,5 deprem yok.', { km: YK.km })) + '</li>';
      yakin.slice(0, 3).forEach(function (o) { h += satirDeprem(o, false); });
    }
    var iss = metin('map-iss-dist');
    if (iss && iss !== '—') h += satirBilgi('ISS', _t('harita.yakin-iss', 'Uzay istasyonu şu an {uzak} uzakta', { uzak: iss }),
      _t('harita.yakin-iss-alt', 'konumuna göre düz çizgi uzaklık'), _t('harita.yakin-canli', 'canlı'));
    var kp = metin('map-kp'), kpl = metin('map-kp-level');
    if (kp && kp !== '—') {
      var kpS = parseFloat(kp.replace(',', '.'));
      h += satirBilgi('Kp ' + (isFinite(kpS) ? sayi(kpS, 1) : kp),
        _t('harita.yakin-kp', 'Jeomanyetik alan {durum}', { durum: (kpl || '—').toLocaleLowerCase(yerel()) }),
        kpS >= 5 ? _t('harita.yakin-isik-var', 'kuzey ışığı ihtimali var') : _t('harita.yakin-isik-yok', 'kuzey ışığı ihtimali yok'), 'NOAA', true);
    }
    yl.innerHTML = h;
    // DÜNYA: aynı veriden en büyük 5
    var dunya = hepsi.slice().sort(function (a, b) { return b.mag - a.mag; }).slice(0, 5);
    dl.innerHTML = !eqAcik ? '<li class="mh-bos">' + esc(_t('harita.yakin-deprem-kapali', 'Deprem katmanı kapalı.')) + '</li>'
      : dunya.length ? dunya.map(function (o) { return satirDeprem(o, true); }).join('')
      : '<li class="mh-bos">' + esc(_t('harita.dunya-olay-yok', 'Son 24 saatte olay yok.')) + '</li>';
    _senEtiketi(); _konumDugmesi();
  };
  function _senEtiketi() {   // "Sen" etiketi — kullanıcı işareti mor (CSS)
    if (typeof _userMarker === 'undefined' || !_userMarker || _userMarker._mhSen) return;
    try {
      _userMarker.unbindTooltip();
      _userMarker.bindTooltip(_t('harita.sen', 'Sen'), { permanent: true, direction: 'right', offset: [8, 6], className: 'mh-sen-et' });
      _userMarker._mhSen = true;
    } catch (e) {}
  }
  function _sekme(ad) {
    document.querySelectorAll('#map-gundem .mh-yk-sekme').forEach(function (b) { b.setAttribute('aria-selected', b.dataset.yk === ad ? 'true' : 'false'); });
    var p = { yakin: 'map-yakin-list', dunya: 'map-dunya-list', gundem: 'map-news-list' };
    Object.keys(p).forEach(function (k) { var e = document.getElementById(p[k]); if (e) e.hidden = k !== ad; });
    var g = document.getElementById('map-gundem'); if (g) g.dataset.sekme = ad;
  }
  var _seciliKatman = null;
  function _sec(lat, lon) {
    if (typeof _lmap === 'undefined' || !_lmap || typeof L === 'undefined') return;
    _ykSecili = lat + ',' + lon;
    if (_seciliKatman) _lmap.removeLayer(_seciliKatman);
    _seciliKatman = L.circleMarker([lat, lon], { radius: 16, className: 'mh-secili-halka', interactive: false }).addTo(_lmap);
    _lmap.flyTo([lat, lon], Math.max(_lmap.getZoom(), 8), { duration: .8 });
    document.querySelectorAll('#map-gundem .mh-olay').forEach(function (b) { b.classList.toggle('secili', b.dataset.lat + ',' + b.dataset.lon === _ykSecili); });
  }
  document.addEventListener('click', function (e) {
    if (!e.target.closest) return;
    var t = e.target.closest('#map-gundem .mh-yk-sekme');
    if (t) { _sekme(t.dataset.yk); if (!document.getElementById('map-gundem').classList.contains('acik')) window.mapGundemAc(true); return; }
    var ac = e.target.closest('#map-gundem [data-yk-ac]');
    if (ac) { if (typeof toggleLayer === 'function') toggleLayer(ac.getAttribute('data-yk-ac')); return; }
    // Telefonda çekmecenin GÖRÜNÜM düğmeleri etkisini göstermek için çekmeceyi kapatır
    if (tel() && e.target.closest('#map-katman-cekmece .mk-gorunum button')) { setTimeout(function () { window.mapKatmanCekmece(false); }, 0); return; }
    if (e.target.closest('#map-gundem .mh-tutamak')) { document.getElementById('map-gundem').classList.toggle('genis'); return; }
    var o = e.target.closest('#map-gundem button.mh-olay');
    if (o) _sec(+o.dataset.lat, +o.dataset.lon);
  });
  // Sekmelerde ok tuşu (rol tablist)
  document.addEventListener('keydown', function (e) {
    var t = e.target && e.target.closest && e.target.closest('#map-gundem .mh-yk-sekme');
    if (!t || (e.key !== 'ArrowRight' && e.key !== 'ArrowLeft')) return;
    var hepsi = Array.prototype.slice.call(document.querySelectorAll('#map-gundem .mh-yk-sekme'));
    var i = (hepsi.indexOf(t) + (e.key === 'ArrowRight' ? 1 : hepsi.length - 1)) % hepsi.length;
    hepsi[i].focus(); _sekme(hepsi[i].dataset.yk); e.preventDefault();
  });
  window.mapYakinSor = function () {
    var ol = document.querySelectorAll('#map-yakin-list .mh-olay');
    var ozet = Array.prototype.map.call(ol, function (b) { return b.innerText.replace(/\s+/g, ' ').trim(); }).slice(0, 5).join('; ');
    if (typeof mapSendMessage === 'function')
      mapSendMessage(_t('harita.yakin-sor', 'Yakınımda son 24 saatte olanları kısaca yorumla{ozet}. Endişelenmem gereken bir şey var mı?', { ozet: ozet ? ': ' + ozet : '' }));
  };
  // ◎ zoom sütununun altına (Leaflet denetimi geç kurulur → her tazelemede bir kez dener)
  function _konumDugmesi() {
    var z = document.querySelector('#tab-map .leaflet-control-zoom');
    if (!z || z.querySelector('.mh-konum')) return;
    var a = document.createElement('a');
    a.href = '#'; a.className = 'mh-konum'; a.setAttribute('role', 'button');
    a.setAttribute('aria-label', _t('harita.konumuma-don', 'Konumuma dön')); a.title = a.getAttribute('aria-label'); a.textContent = '◎';
    a.addEventListener('click', function (e) { e.preventDefault(); e.stopPropagation(); window.mapKonumumaDon(); });
    if (typeof L !== 'undefined' && L.DomEvent) L.DomEvent.disableClickPropagation(a);
    z.appendChild(a);
  }
  window.mapKonumumaDon = function () {
    var k = konum();
    if (k && typeof _lmap !== 'undefined' && _lmap) _lmap.flyTo(k, Math.max(_lmap.getZoom(), 8), { duration: .8 });
  };
  setInterval(function () { if (gorunur()) window.mapYakinGuncelle(); }, 60000);
  // ISS uzaklığı ve Kp şeride yazılınca YAKINDA satırları da tazelensin
  function _gozle() {
    if (!window.MutationObserver) return;
    var bekle = null, g = new MutationObserver(function () { clearTimeout(bekle); bekle = setTimeout(window.mapYakinGuncelle, 300); });
    ['map-iss-dist', 'map-kp', 'map-kp-level'].forEach(function (id) {
      var e = document.getElementById(id); if (e) g.observe(e, { childList: true, characterData: true, subtree: true });
    });
  }
  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', _gozle); else _gozle();
  window.addEventListener('yuki-dil-degisti', function () {
    var k = document.querySelector('#tab-map .mh-konum');
    if (k) { k.setAttribute('aria-label', _t('harita.konumuma-don', 'Konumuma dön')); k.title = k.getAttribute('aria-label'); }
    if (typeof _userMarker !== 'undefined' && _userMarker) _userMarker._mhSen = false;
    window.mapYakinGuncelle();
  });

  function kur() {
    if (!tab()) return;
    try { ['mapPanelLeft', 'mapPanelRight', 'mapModeBar'].forEach(function (k) { localStorage.removeItem(k); }); } catch (e) {}
    var d = oku();
    // Telefonda YAKINDA alt sayfası açık başlar (ilk 2 olay) — kişiseldeki gibi
    if (tel()) { window.mapKatmanCekmece(false); window.mapGundemAc(true); window.mapSeritAc(false); }
    else { window.mapKatmanCekmece(d.katman === true); window.mapGundemAc(d.gundem !== false); }
    window.mapKatmanSay();
    _sagGenislik();
  }

  // Masaüstü ↔ telefon geçişinde (pencere daraltma, döndürme) açık sayfaları yeniden kur
  if (telMQ) {
    var degis = function () { kur(); };
    if (telMQ.addEventListener) telMQ.addEventListener('change', degis);
    else if (telMQ.addListener) telMQ.addListener(degis);
  }
  window.addEventListener('resize', _sagGenislik);
  // Sekme görünür olunca (ve dil değişince: yazı genişliği değişir) bir kez daha ölç.
  // `tabchange` `hidden` kalktıktan SONRA yayınlanır (tab-nav.js).
  document.addEventListener('tabchange', function (e) {
    if (e && e.detail && e.detail.tab === 'map') requestAnimationFrame(_sagGenislik);
  });
  window.addEventListener('yuki-dil-degisti', function () { requestAnimationFrame(_sagGenislik); });
  // Şeridin yüksekliği VERİYLE değişir (değerler ağdan geç gelir, uzun şehir adı
  // ya da dil satırı sarar) — boyutu izlenir, --mh-serit-alt güncel kalır.
  if (window.ResizeObserver) {
    var izle = function () {
      var sr = document.getElementById('map-serit');
      if (sr) new ResizeObserver(function () { _sagGenislik(); }).observe(sr);
    };
    if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', izle);
    else izle();
  }

  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', kur);
  else kur();
})();
