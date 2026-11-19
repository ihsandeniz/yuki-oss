/**
 * Yedek › BULUTTA / AYARLAR / Kontrol et / Kuru çalıştır — rclone denetim yüzü.
 *
 * Kişisel Yuki'deki rclone panosunun (drive.html) oss uyarlaması. Arka uç
 * `/api/yedekleme/rclone/*` (backend/app/services/rclone_yedek.py) — yalnız OKUR:
 * uzak gezgini, `rclone check`, `rclone copy --dry-run`. Asıl yedeği Yuki'nin Drive turu alır.
 *
 * Bu modül kendi başına çizmez: `yedekleme.js` odayı çizerken buradan üst çubuk
 * sekmelerini (`ustCubuk`), seçili sekmenin gövdesini (`govde`) ve sonuç penceresini
 * (`pencere`) ister; tıklamaları `olay` ile buraya devreder. Yeniden çizim
 * `window.yedeklemeCiz`. Uzak adı / yol / hesap kodda YOK — hepsi ayardan.
 */
(function () {
  'use strict';

  var UC = '/api/yedekleme/rclone';
  var _sekme = 'yedek';       // yedek · bulutta · ayarlar
  var _d = null;              // /durum cevabı · {hata:true} · null (okunmadı)
  var _okunuyor = false;
  var _gez = { yol: '', ogeler: null, hata: null, suzgec: '' };
  var _taslak = null;         // AYARLAR formu — yeniden çizimde korunur
  var _ayarMesaj = null;      // {anahtar, hata}
  var _pencere = null;        // {ad: kontrol|kuru, durum: {...}} — açık sonuç penceresi
  var _yoklama = null;

  function t(a, d) { return (window.YukiDil && window.YukiDil.t) ? window.YukiDil.t(a, d) : String(a); }
  function esc(s) {
    return String(s == null ? '' : s).replace(/[&<>"']/g, function (c) {
      return { '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c];
    });
  }
  function f(yol, secenek) {
    if (typeof window.authFetch === 'function') return window.authFetch(yol, secenek || {});
    return fetch(yol, secenek);
  }
  function ciz() { if (typeof window.yedeklemeCiz === 'function') window.yedeklemeCiz(); }
  function boyut(b) {
    if (b == null) return '';
    var birim = ['B', 'KB', 'MB', 'GB', 'TB'], i = 0, n = Number(b) || 0;
    while (n >= 1024 && i < birim.length - 1) { n /= 1024; i++; }
    return (i ? n.toFixed(1) : String(n)) + ' ' + birim[i];
  }

  async function durumOku() {
    if (_okunuyor) return;
    _okunuyor = true;
    try {
      var r = await f(UC + '/durum');
      _d = r.ok ? await r.json() : { hata: true };
    } catch (e) { _d = { hata: true }; }
    _okunuyor = false;
    if (!_taslak && _d && _d.ayar) _taslak = taslakKur(_d.ayar);
    ciz();
  }

  function taslakKur(a) {
    return { uzak: a.uzak || '', yol: a.yol || '', bant: a.bant || '',
             aktarim: a.aktarim || 4, denetleyici: a.denetleyici || 8,
             haric: (a.haric || []).join('\n') };
  }

  /* Neden kodu → sade cümle + ne yapmalı */
  function nedenHtml(n) {
    return '<div class="yb-r-durum" role="status"><span class="durum-isik uyari" aria-hidden="true"></span><div>'
      + '<p class="yb-r-durum-bas">' + esc(t('yedek.r-neden-' + n)) + '</p>'
      + (t('yedek.r-neden-' + n + '-alt') ? '<p class="yb-kucuk">' + esc(t('yedek.r-neden-' + n + '-alt')) + '</p>' : '') + '</div></div>';
  }

  // ── Üst çubuk ─────────────────────────────────────────────────────
  function ustCubuk() {
    var sek = ['yedek', 'bulutta', 'ayarlar'].map(function (s) {
      var on = s === _sekme;
      return '<button type="button" class="yb-sekme" role="tab" data-y="r-sekme" data-sekme="' + s + '"'
        + ' aria-selected="' + on + '" tabindex="' + (on ? 0 : -1) + '">' + esc(t('yedek.r-sekme-' + s)) + '</button>';
    }).join('');
    var mesgul = function (ad) { return _pencere && _pencere.ad === ad && _pencere.durum && _pencere.durum.calisiyor; };
    return '<nav class="yb-sekmeler" role="tablist" aria-label="' + esc(t('yedek.r-sekmeler')) + '">' + sek + '</nav>'
      + '<div class="yb-cubuk-eylem">'
      + '<button type="button" class="dg dg-ikincil" data-y="r-kontrol" title="' + esc(t('yedek.r-kontrol-ipucu')) + '"'
      + (mesgul('kontrol') ? ' aria-busy="true"' : '') + '>' + esc(t(mesgul('kontrol') ? 'yedek.r-kontrol-suruyor' : 'yedek.r-kontrol')) + '</button>'
      + '<button type="button" class="dg dg-ikincil" data-y="r-kuru" title="' + esc(t('yedek.r-kuru-ipucu')) + '"'
      + (mesgul('kuru') ? ' aria-busy="true"' : '') + '>' + esc(t(mesgul('kuru') ? 'yedek.r-kuru-suruyor' : 'yedek.r-kuru')) + '</button>'
      + '</div>';
  }

  // ── BULUTTA ───────────────────────────────────────────────────────
  function bulutta() {
    if (!_d) { durumOku(); return '<p class="yb-kucuk yb-r-bos">' + esc(t('yedek.r-okunuyor')) + '</p>'; }
    if (_d.hata) return nedenHtml('ulasilamadi');
    if (!_d.hazir) return nedenHtml(_d.neden);
    if (_gez.ogeler === null && !_gez.hata) { gozat(_gez.yol); return '<p class="yb-kucuk yb-r-bos">' + esc(t('yedek.r-okunuyor')) + '</p>'; }

    var kok = (_d.ayar.uzak || '') + ':' + (_d.ayar.yol || '');
    var parca = _gez.yol ? _gez.yol.split('/') : [];
    var iz = '<button type="button" class="yb-r-iz" data-y="r-git" data-yol="">' + esc(kok) + '</button>';
    parca.forEach(function (p, i) {
      iz += '<span aria-hidden="true">/</span><button type="button" class="yb-r-iz" data-y="r-git" data-yol="'
        + esc(parca.slice(0, i + 1).join('/')) + '">' + esc(p) + '</button>';
    });
    var h = '<div class="yb-r-arac"><nav class="yb-r-izler" aria-label="' + esc(t('yedek.r-konum')) + '">' + iz + '</nav>'
      + '<input id="yr-suz" class="girdi yb-r-suz" type="search" autocomplete="off" placeholder="' + esc(t('yedek.r-suz')) + '"'
      + ' aria-label="' + esc(t('yedek.r-suz')) + '" value="' + esc(_gez.suzgec) + '"></div>';
    if (_gez.hata) return h + nedenHtml(_gez.hata);

    var s = (_gez.suzgec || '').toLowerCase();
    var ogeler = _gez.ogeler.filter(function (o) { return !s || o.ad.toLowerCase().indexOf(s) >= 0; });
    var satir = '';
    if (_gez.yol) {
      satir += '<li><button type="button" class="yb-r-oge klasor" data-y="r-git" data-yol="' + esc(parca.slice(0, -1).join('/')) + '">'
        + '<span class="yb-r-ad">' + esc(t('yedek.r-ust')) + '</span></button></li>';
    }
    ogeler.forEach(function (o) {
      var yeni = (_gez.yol ? _gez.yol + '/' : '') + o.ad;
      var ic = '<span class="yb-r-ad">' + esc(o.ad) + '</span><span class="yb-r-boyut">' + esc(o.klasor ? '' : boyut(o.boyut))
        + '</span><span class="yb-r-tarih">' + esc((o.tarih || '').replace('T', ' ').slice(0, 16)) + '</span>';
      satir += o.klasor
        ? '<li><button type="button" class="yb-r-oge klasor" data-y="r-git" data-yol="' + esc(yeni) + '">' + ic + '</button></li>'
        : '<li><div class="yb-r-oge">' + ic + '</div></li>';
    });
    if (!ogeler.length) satir += '<li class="yb-kucuk yb-r-bos">' + esc(t(s ? 'yedek.r-eslesme-yok' : 'yedek.r-bos-klasor')) + '</li>';
    return h + '<ul class="yb-r-liste">' + satir + '</ul>';
  }

  async function gozat(yol) {
    _gez = { yol: yol || '', ogeler: null, hata: null, suzgec: _gez.suzgec && yol === _gez.yol ? _gez.suzgec : '' };
    try {
      var r = await f(UC + '/gozat' + (yol ? '?yol=' + encodeURIComponent(yol) : ''));
      var d = await r.json();
      if (r.ok && d.ok) _gez.ogeler = d.ogeler || [];
      else { _gez.ogeler = []; _gez.hata = (d && (d.neden || (d.detail && d.detail.kod))) || 'okunamadi'; }
    } catch (e) { _gez.ogeler = []; _gez.hata = 'ulasilamadi'; }
    ciz();
  }

  // ── AYARLAR ───────────────────────────────────────────────────────
  function alan(id, etiket, ipucu, girdi) {
    return '<div class="yb-r-alan"><label for="' + id + '"><span class="yb-r-etiket">' + esc(t(etiket)) + '</span>'
      + (ipucu ? '<span class="yb-kucuk">' + esc(t(ipucu)) + '</span>' : '') + '</label>' + girdi + '</div>';
  }

  function ayarlar() {
    if (!_d) { durumOku(); return '<p class="yb-kucuk yb-r-bos">' + esc(t('yedek.r-okunuyor')) + '</p>'; }
    if (_d.hata) return nedenHtml('ulasilamadi');
    var x = _taslak || taslakKur(_d.ayar || {});
    var uzaklar = _d.uzaklar || [];
    var rclone = _d.kurulu
      ? '<p class="yb-r-surum"><span class="durum-isik iyi" aria-hidden="true"></span>' + esc(t('yedek.r-kurulu', { surum: _d.surum || 'rclone' })) + '</p>'
      : '';
    var uyari = (!_d.kurulu || !uzaklar.length) ? nedenHtml(_d.kurulu ? 'uzak-yok' : 'kurulu-degil') : '';

    var secim = '<select id="yr-uzak" class="girdi"' + (uzaklar.length ? '' : ' disabled') + '>'
      + '<option value="">' + esc(t('yedek.r-uzak-sec')) + '</option>'
      + uzaklar.map(function (u) { return '<option value="' + esc(u) + '"' + (u === x.uzak ? ' selected' : '') + '>' + esc(u) + '</option>'; }).join('')
      + (x.uzak && uzaklar.indexOf(x.uzak) < 0 ? '<option value="' + esc(x.uzak) + '" selected>' + esc(x.uzak) + ' ' + esc(t('yedek.r-tanimsiz')) + '</option>' : '')
      + '</select>';
    var ornek = (x.uzak || t('yedek.r-uzak-yer')) + ':' + (x.yol ? x.yol + '/' : '') + t('yedek.r-klasor-adi');

    var mesaj = _ayarMesaj
      ? '<p class="yb-r-mesaj' + (_ayarMesaj.hata ? ' hata' : '') + '" role="' + (_ayarMesaj.hata ? 'alert' : 'status') + '">' + esc(t(_ayarMesaj.anahtar)) + '</p>' : '';

    return '<div class="yb-r-ayar">' + rclone + uyari
      + '<section class="yb-r-bolum"><h4>' + esc(t('yedek.r-b-uzak')) + '</h4>'
      + alan('yr-uzak', 'yedek.r-uzak', 'yedek.r-uzak-ipucu', secim)
      + alan('yr-yol', 'yedek.r-yol', 'yedek.r-yol-ipucu',
             '<input id="yr-yol" class="girdi" type="text" autocomplete="off" spellcheck="false" placeholder="' + esc(t('yedek.r-yol-ornek')) + '" value="' + esc(x.yol) + '">')
      + '<p class="yb-kucuk yb-r-esleme">' + esc(t('yedek.r-esleme')) + ' <code>' + esc(ornek) + '</code></p></section>'
      + '<section class="yb-r-bolum"><h4>' + esc(t('yedek.r-b-performans')) + '</h4>'
      + alan('yr-bant', 'yedek.r-bant', 'yedek.r-bant-ipucu',
             '<input id="yr-bant" class="girdi" type="text" autocomplete="off" placeholder="' + esc(t('yedek.r-sinirsiz')) + '" value="' + esc(x.bant) + '">')
      + alan('yr-aktarim', 'yedek.r-aktarim', 'yedek.r-aktarim-ipucu',
             '<input id="yr-aktarim" class="girdi" type="number" min="1" max="32" value="' + esc(x.aktarim) + '">')
      + alan('yr-denetleyici', 'yedek.r-denetleyici', 'yedek.r-denetleyici-ipucu',
             '<input id="yr-denetleyici" class="girdi" type="number" min="1" max="64" value="' + esc(x.denetleyici) + '">')
      + '</section>'
      + '<section class="yb-r-bolum"><h4>' + esc(t('yedek.r-b-haric')) + '</h4>'
      + '<p class="yb-kucuk">' + esc(t('yedek.r-haric-ipucu')) + '</p>'
      + '<textarea id="yr-haric" class="girdi yb-r-haric" rows="4" spellcheck="false" aria-label="' + esc(t('yedek.r-b-haric')) + '" placeholder="*.tmp&#10;node_modules/">' + esc(x.haric) + '</textarea></section>'
      + mesaj
      + '<div class="yb-r-kaydet"><button type="button" class="dg dg-birincil" data-y="r-ayar-kaydet">' + esc(t('yedek.r-kaydet')) + '</button></div>'
      + '</div>';
  }

  async function ayarKaydet() {
    var x = _taslak || {};
    var govde = { uzak: x.uzak || '', yol: x.yol || '', bant: x.bant || '',
                  aktarim: parseInt(x.aktarim, 10) || 4, denetleyici: parseInt(x.denetleyici, 10) || 8,
                  haric: String(x.haric || '').split('\n').map(function (s) { return s.trim(); }).filter(Boolean) };
    try {
      var r = await f(UC + '/ayar', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(govde) });
      var d = await r.json();
      if (r.ok) { _d = d; _taslak = taslakKur(d.ayar); _ayarMesaj = { anahtar: 'yedek.r-kaydedildi' }; _gez = { yol: '', ogeler: null, hata: null, suzgec: '' }; }
      else _ayarMesaj = { anahtar: 'yedek.r-hata-' + ((d.detail && d.detail.kod) || 'genel'), hata: true };
    } catch (e) { _ayarMesaj = { anahtar: 'yedek.r-neden-ulasilamadi', hata: true }; }
    ciz();
  }

  // ── Kontrol et · Kuru çalıştır ────────────────────────────────────
  async function isBaslat(ad) {
    _pencere = { ad: ad, durum: { calisiyor: true, sonuc: null, ilerleme: '' }, neden: null };
    ciz();
    var kapat = document.querySelector('.yb-r-pencere [data-y="r-kapat"]');
    if (kapat && kapat.focus) kapat.focus();      // odak pencereye — Esc ve Tab orada
    try {
      var r = await f(UC + '/' + ad, { method: 'POST' });
      var d = await r.json();
      if (!r.ok || !d.ok) { _pencere.neden = (d && (d.neden || (d.detail && 'genel'))) || 'genel'; _pencere.durum.calisiyor = false; ciz(); return; }
    } catch (e) { _pencere.neden = 'ulasilamadi'; _pencere.durum.calisiyor = false; ciz(); return; }
    yokla();
  }

  function yokla() {
    clearTimeout(_yoklama);
    _yoklama = setTimeout(async function () {
      if (!_pencere) return;
      try {
        var r = await f(UC + '/' + _pencere.ad + '/sonuc');
        if (r.ok && _pencere) _pencere.durum = await r.json();
      } catch (e) { /* bir sonraki turda yeniden */ }
      ciz();
      if (_pencere && _pencere.durum && _pencere.durum.calisiyor) yokla();
    }, 1500);
  }

  function klasorSatiri(k, ad) {
    var bas = '<li class="yb-r-k"><div class="yb-r-k-bas"><span class="yb-r-ad">' + esc(k.klasor) + '</span>';
    if (!k.ok) return bas + '<span class="yb-hap uyari">' + esc(t('yedek.r-atlandi')) + '</span></div><p class="yb-kucuk">' + esc(t('yedek.r-neden-' + (k.neden || 'okunamadi'))) + '</p></li>';
    var hap, satirlar = [];
    if (ad === 'kontrol') {
      hap = k.esit ? '<span class="yb-hap iyi">' + esc(t('yedek.r-esit')) + '</span>'
        : '<span class="yb-hap kritik">' + esc(t('yedek.r-eksik-fark', { eksik: k.eksik, fark: k.fark })) + '</span>';
      satirlar = (k.eksik_satir || []).map(function (s) { return '+ ' + s; }).concat((k.fark_satir || []).map(function (s) { return '≠ ' + s; }));
    } else {
      hap = '<span class="yb-hap ' + (k.gidecek ? 'uyari' : 'iyi') + '">' + esc(t('yedek.r-gidecek', { n: k.gidecek })) + '</span>';
      satirlar = k.satirlar || [];
    }
    return bas + hap + '</div><p class="yb-kucuk yb-r-hedef"><code>' + esc(k.hedef || '') + '</code></p>'
      + (satirlar.length ? '<pre class="yb-r-satirlar">' + esc(satirlar.join('\n')) + '</pre>' : '') + '</li>';
  }

  function pencere() {
    if (!_pencere) return '';
    var ad = _pencere.ad, d = _pencere.durum || {}, s = d.sonuc, ozet, govde = '';
    if (_pencere.neden) ozet = nedenHtml(_pencere.neden);
    else if (d.calisiyor || !s) ozet = '<p class="yb-r-ozet" role="status">' + esc(t('yedek.r-suruyor', { ilerleme: d.ilerleme || '' })) + '</p>';
    else {
      ozet = ad === 'kontrol'
        ? '<p class="yb-r-ozet ' + (s.hepsi_esit ? 'iyi' : 'kritik') + '" role="status">' + esc(s.hepsi_esit ? t('yedek.r-hepsi-esit') : t('yedek.r-eksik-fark', { eksik: s.eksik, fark: s.fark })) + ' · ' + esc(t('yedek.r-denetlenen', { n: s.denetlenen, toplam: s.toplam })) + '</p>'
        : '<p class="yb-r-ozet" role="status">' + esc(t('yedek.r-gidecek', { n: s.gidecek })) + ' · ' + esc(t('yedek.r-denetlenen', { n: s.denetlenen, toplam: s.toplam })) + '</p>';
      govde = '<ul class="yb-r-klasorler">' + (s.klasorler || []).map(function (k) { return klasorSatiri(k, ad); }).join('') + '</ul>';
    }
    return '<div class="yb-r-perde" data-y="r-kapat"></div>'
      + '<div class="yb-r-pencere" role="dialog" aria-modal="true" aria-labelledby="yr-p-bas">'
      + '<header><h3 id="yr-p-bas">' + esc(t(ad === 'kontrol' ? 'yedek.r-p-kontrol' : 'yedek.r-p-kuru')) + '</h3>'
      + '<button type="button" class="dg dg-sessiz" data-y="r-kapat">' + esc(t('yedek.r-kapat')) + '</button></header>'
      + '<p class="yb-kucuk">' + esc(t(ad === 'kontrol' ? 'yedek.r-kontrol-ipucu' : 'yedek.r-kuru-ipucu')) + '</p>'
      + ozet + govde + '</div>';
  }

  // ── Olaylar ───────────────────────────────────────────────────────
  function olay(y, b) {
    if (y === 'r-sekme') {
      _sekme = b.dataset.sekme || 'yedek';
      if (_sekme !== 'yedek') durumOku();
      ciz();
      var on = document.querySelector('.yb-sekme[aria-selected="true"]');
      if (on && on.focus) on.focus();
      return true;
    }
    if (y === 'r-git') { gozat(b.dataset.yol || ''); return true; }
    if (y === 'r-ayar-kaydet') { ayarKaydet(); return true; }
    if (y === 'r-kontrol') { isBaslat('kontrol'); return true; }
    if (y === 'r-kuru') { isBaslat('kuru'); return true; }
    if (y === 'r-kapat') { _pencere = null; clearTimeout(_yoklama); ciz(); return true; }
    return false;
  }

  /* Form alanları taslağa yazılır — yedekleme.js'nin 2 sn'lik yeniden çizimi yazıyı silmez. */
  function girdi(e) {
    var h = e.target;
    if (!h || !h.id || h.id.indexOf('yr-') !== 0) return;
    if (h.id === 'yr-suz') { _gez.suzgec = h.value; ciz(); var s = document.getElementById('yr-suz'); if (s) { s.focus(); s.setSelectionRange(s.value.length, s.value.length); } return; }
    _taslak = _taslak || taslakKur((_d && _d.ayar) || {});
    _taslak[h.id.slice(3)] = h.value;
    _ayarMesaj = null;
  }

  function tus(e) {
    var b = e.target && e.target.closest && e.target.closest('.yb-sekme');
    if (!b || (e.key !== 'ArrowRight' && e.key !== 'ArrowLeft')) return;
    var sira = ['yedek', 'bulutta', 'ayarlar'], i = sira.indexOf(_sekme);
    i = (i + (e.key === 'ArrowRight' ? 1 : 2)) % 3;
    olay('r-sekme', { dataset: { sekme: sira[i] } });
    e.preventDefault();
  }

  /* Esc odak nerede olursa olsun açık pencereyi kapatır (oda dışındaki odak dahil). */
  document.addEventListener('keydown', function (e) {
    if (e.key === 'Escape' && _pencere) { _pencere = null; clearTimeout(_yoklama); ciz(); e.preventDefault(); }
  });

  window.YedekRclone = {
    sekme: function () { return _sekme; },
    ustCubuk: ustCubuk,
    govde: function () { return _sekme === 'bulutta' ? bulutta() : _sekme === 'ayarlar' ? ayarlar() : null; },
    pencere: pencere,
    olay: olay,
    girdi: girdi,
    tus: tus,
    sifirla: function () { _d = null; _gez = { yol: '', ogeler: null, hata: null, suzgec: '' }; _ayarMesaj = null; }
  };
})();
