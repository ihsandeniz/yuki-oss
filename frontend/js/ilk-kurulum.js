/* ============================================================================
   İLK AÇILIŞ SİHİRBAZI — açık kaynak kullanıcısı için adım adım kurulum
   dil → sağlayıcı (yerel model ya da kendi anahtarı) → anahtar gir/sına → hazır

   Neden: temiz kurulumda hiçbir şey sormadan sohbet ekranı açılıyordu; kullanıcı
   "anahtar ayarlanmadı" uyarısını ancak ilk mesajda görüyordu (2026-10-18 ölçümü,
   reports/…/yuki-oss-surum/RAPOR.md).

   🔴 Yeni sır yolu YOK: anahtar mevcut BYOK ucuna gider (`POST /api/llm/key` —
   önce canlı dener, ancak geçerse kaydeder), yerel model `POST /api/llm/yerel`.
   Bu dosya hiçbir şeyi kendisi saklamaz; yalnız "sihirbaz bitti/atlandı"
   bayrağı localStorage'da durur (sır değil).

   Ne zaman açılır: hiçbir sağlayıcının anahtarı yoksa VE aktif sağlayıcı yerel
   değilse VE bayrak yoksa. Anahtarı olan kurulumda asla açılmaz.
   ============================================================================ */
(function () {
  'use strict';

  var BAYRAK = 'yuki-ilk-kurulum_v1';
  var t = function (k, d) { return (window.YukiDil ? window.YukiDil.t(k, d) : k); };

  function esc(s) {
    return String(s == null ? '' : s).replace(/[&<>"']/g, function (c) {
      return { '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c];
    });
  }
  function bayrakVar() { try { return !!localStorage.getItem(BAYRAK); } catch (_) { return false; } }
  function bayrakKoy(v) { try { localStorage.setItem(BAYRAK, v); } catch (_) { /* gizli pencere */ } }

  async function getJSON(url) {
    var r = await fetch(url, { credentials: 'same-origin' });
    if (!r.ok) throw new Error('HTTP ' + r.status);
    return r.json();
  }
  async function postJSON(url, govde) {
    var r = await fetch(url, {
      method: 'POST', credentials: 'same-origin',
      headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(govde),
    });
    var j = null;
    try { j = await r.json(); } catch (_) { /* gövdesiz */ }
    if (!r.ok && !(j && j.error)) return { ok: false, error: (j && j.detail) || ('HTTP ' + r.status) };
    return j || { ok: false };
  }

  /** Saf karar (test edilir): sihirbaz gösterilmeli mi. */
  function gosterilmeliMi(saglayicilar, aktif, bayrak) {
    if (bayrak) return false;
    var liste = saglayicilar || [];
    if (liste.some(function (s) { return s.anahtar_var; })) return false;
    var a = liste.filter(function (s) { return s.kimlik === aktif; })[0];
    if (a && a.yerel) return false;
    return true;
  }

  var durum = { adim: 'dil', diller: [], saglayicilar: [], secili: null, mesaj: '', mesajTur: '', mesgul: false };
  var kok = null;

  function kapat(neden) {
    bayrakKoy(neden);
    if (kok) { kok.remove(); kok = null; }
    document.documentElement.classList.remove('ilk-kurulum-acik');
  }

  function adimNoktalari() {
    var adimlar = ['dil', 'saglayici', 'anahtar', 'hazir'];
    var i = adimlar.indexOf(durum.adim);
    return '<ol class="ik-adimlar" aria-label="' + esc(t('ik.adimlar')) + '">' + adimlar.map(function (a, j) {
      return '<li class="' + (j < i ? 'bitti' : j === i ? 'simdi' : '') + '">' + esc(t('ik.adim.' + a)) + '</li>';
    }).join('') + '</ol>';
  }

  function govde() {
    if (durum.adim === 'dil') {
      var aktifDil = window.YukiDil ? window.YukiDil.al() : 'tr';
      return '<h2>' + esc(t('ik.dil.baslik')) + '</h2>'
        + '<div class="ik-secenekler">' + durum.diller.map(function (d) {
          // /api/language → arayuz_available: [{code, name, flag}] (eski biçim: düz kod)
          var kod = (d && d.code) || String(d);
          var ad = (d && d.name) || t('ik.dil.' + kod);
          return '<button type="button" class="ik-kart' + (kod === aktifDil ? ' secili' : '') + '" data-dil="' + esc(kod) + '">'
            + esc(ad) + '</button>';
        }).join('') + '</div>'
        + '<div class="ik-alt"><button type="button" class="ik-ileri" data-git="saglayici">' + esc(t('ik.ileri')) + '</button></div>';
    }
    if (durum.adim === 'saglayici') {
      var sirali = durum.saglayicilar.slice().sort(function (a, b) { return (b.yerel ? 1 : 0) - (a.yerel ? 1 : 0); });
      return '<h2>' + esc(t('ik.saglayici.baslik')) + '</h2>'
        + '<p class="ik-aciklama">' + esc(t('ik.saglayici.aciklama')) + '</p>'
        + '<div class="ik-secenekler ik-liste">' + sirali.map(function (s) {
          return '<button type="button" class="ik-kart' + (durum.secili === s.kimlik ? ' secili' : '') + '" data-sag="' + esc(s.kimlik) + '">'
            + '<b>' + esc(s.ad) + '</b>'
            + (s.yerel ? '<span class="ik-rozet">' + esc(t('ik.rozet.yerel')) + '</span>' : '')
            + (s.ucretsiz ? '<span class="ik-rozet">' + esc(t('ik.rozet.ucretsiz')) + '</span>' : '')
            + (s.not ? '<small>' + esc(s.not) + '</small>' : '')
            + '</button>';
        }).join('') + '</div>'
        + '<div class="ik-alt"><button type="button" class="ik-geri" data-git="dil">' + esc(t('ik.geri')) + '</button>'
        + '<button type="button" class="ik-ileri" data-git="anahtar"' + (durum.secili ? '' : ' disabled') + '>' + esc(t('ik.ileri')) + '</button></div>';
    }
    if (durum.adim === 'anahtar') {
      var s = durum.saglayicilar.filter(function (x) { return x.kimlik === durum.secili; })[0] || {};
      var ic = s.yerel
        ? '<p class="ik-aciklama">' + esc(t('ik.yerel.aciklama', { ad: s.ad || '' })) + '</p>'
        : '<p class="ik-aciklama">' + esc(t('ik.anahtar.aciklama', { ad: s.ad || '' })) + '</p>'
          + (s.anahtar_url ? '<p><a href="' + esc(s.anahtar_url) + '" target="_blank" rel="noopener">' + esc(t('ik.anahtar.al')) + ' ↗</a></p>' : '')
          + '<input type="password" class="ik-girdi" autocomplete="off" spellcheck="false" placeholder="' + esc(t('ik.anahtar.yer-tutucu')) + '" aria-label="' + esc(t('ik.anahtar.yer-tutucu')) + '">';
      return '<h2>' + esc(s.yerel ? t('ik.yerel.baslik') : t('ik.anahtar.baslik')) + '</h2>' + ic
        + (durum.mesaj ? '<p class="ik-mesaj ' + durum.mesajTur + '" role="status">' + esc(durum.mesaj) + '</p>' : '')
        + '<div class="ik-alt"><button type="button" class="ik-geri" data-git="saglayici">' + esc(t('ik.geri')) + '</button>'
        + '<button type="button" class="ik-ileri" data-sina="1"' + (durum.mesgul ? ' disabled' : '') + '>'
        + esc(durum.mesgul ? t('ik.siniyor') : t('ik.sina')) + '</button></div>';
    }
    return '<h2>' + esc(t('ik.hazir.baslik')) + '</h2>'
      + '<p class="ik-aciklama">' + esc(t('ik.hazir.aciklama')) + '</p>'
      + '<div class="ik-alt"><button type="button" class="ik-ileri" data-bitir="1">' + esc(t('ik.basla')) + '</button></div>';
  }

  /* B5 (11-14, temiz kurulum denetimi): sağlayıcının ham hatası (`Error code: 401 - {'error': …}`)
     yeni kullanıcıya bir şey anlatmıyordu. Kimlik reddi sade cümleye çevrilir; ham metin konsolda kalır. */
  function _hataMetni(ham) {
    if (!ham) return t('ik.hata.genel');
    try { console.warn('[ilk-kurulum] sağlayıcı hatası:', ham); } catch (_) { /* yok */ }
    if (/\b40[13]\b|unauthori[sz]ed|invalid[ _-]?api[ _-]?key|incorrect api key|user not found|authentication|permission denied|api key not valid/i.test(String(ham))) {
      return t('ik.hata.anahtar');
    }
    return String(ham).length > 140 || /[{}]/.test(String(ham)) ? t('ik.hata.genel') : String(ham);
  }

  function ciz() {
    if (!kok) return;
    kok.querySelector('.ik-kutu').innerHTML =
      '<div class="ik-ust"><span class="ik-etiket">' + esc(t('ik.etiket')) + '</span>'
      + (durum.adim !== 'hazir' ? '<button type="button" class="ik-atla" data-atla="1">' + esc(t('ik.atla')) + '</button>' : '')
      + '</div>' + adimNoktalari() + govde();
    var girdi = kok.querySelector('.ik-girdi');
    if (girdi) girdi.focus();
  }

  async function sina() {
    var s = durum.saglayicilar.filter(function (x) { return x.kimlik === durum.secili; })[0];
    if (!s) return;
    var girdi = kok.querySelector('.ik-girdi');
    var anahtar = girdi ? girdi.value.trim() : '';
    if (!s.yerel && !anahtar) { durum.mesaj = t('ik.anahtar.bos'); durum.mesajTur = 'hata'; ciz(); return; }
    durum.mesgul = true; durum.mesaj = ''; ciz();
    var sonuc;
    try {
      sonuc = s.yerel
        ? await postJSON('/api/llm/yerel', { provider: s.kimlik })
        : await postJSON('/api/llm/key', { key: anahtar, provider: s.kimlik });
    } catch (e) { sonuc = { ok: false, error: e.message }; }
    durum.mesgul = false;
    if (sonuc && sonuc.ok) {
      durum.adim = 'hazir'; durum.mesaj = '';
      try { window.dispatchEvent(new CustomEvent('yuki-anahtar-degisti')); } catch (_) { /* rozet bir sonraki bağlanışta tazelenir */ }
    }
    else { durum.mesaj = _hataMetni(sonuc && sonuc.error); durum.mesajTur = 'hata'; }
    ciz();
  }

  async function tikla(e) {
    var b = e.target.closest('button');
    if (!b || b.disabled) return;
    if (b.dataset.atla) { kapat('atlandi'); return; }
    if (b.dataset.bitir) { kapat('tamam'); return; }
    if (b.dataset.dil) {
      if (window.YukiDil) { try { await window.YukiDil.ayarla(b.dataset.dil); } catch (_) { /* dil yazılamazsa da sürer */ } }
      ciz(); return;
    }
    if (b.dataset.sag) { durum.secili = b.dataset.sag; durum.mesaj = ''; ciz(); return; }
    if (b.dataset.sina) { sina(); return; }
    if (b.dataset.git) { durum.adim = b.dataset.git; durum.mesaj = ''; ciz(); }
  }

  async function ac() {
    var veri;
    try { veri = await getJSON('/api/llm/providers'); } catch (_) { return; }   // motor yoksa sessiz geç
    if (!gosterilmeliMi(veri.saglayicilar, veri.aktif, bayrakVar())) return;
    durum.saglayicilar = veri.saglayicilar || [];
    durum.secili = null;
    try { durum.diller = ((await getJSON('/api/language')).arayuz_available) || ['tr', 'en']; } catch (_) { durum.diller = ['tr', 'en']; }
    kok = document.createElement('div');
    kok.className = 'ilk-kurulum';
    kok.setAttribute('role', 'dialog');
    kok.setAttribute('aria-modal', 'true');
    kok.innerHTML = '<div class="ik-kutu"></div>';
    kok.addEventListener('click', tikla);
    kok.addEventListener('keydown', function (e) {
      if (e.key === 'Enter' && e.target.classList.contains('ik-girdi')) sina();
    });
    document.body.appendChild(kok);
    document.documentElement.classList.add('ilk-kurulum-acik');
    ciz();
  }

  window.YukiIlkKurulum = { gosterilmeliMi: gosterilmeliMi, ac: ac, BAYRAK: BAYRAK, hataMetni: _hataMetni };
  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', ac);
  else ac();
})();
