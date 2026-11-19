/* ⚙ HQ → TEMA — ORTAM SEÇ ( panel 14, 2026-10-01 — geliştirici taslak B'yi seçti).
 *
 * Taslak B (2026-09-26 HQ taslakları). Tema ADI değil ORTAM seçtirir
 * (gece odası · kapalı oda · pencere kenarı) + "Bilgisayarım karar versin" anahtarı. `tema.js` bir
 * 'sistem' DEĞERİ tanımlamaz: "kaydı sil, bilgisayarı dinle" der → arayüzde kart değil ANAHTAR.
 *
 * Durum tek kaynaktan: `YukiTema.sistemde()` (Sistem takibi açık mı) · `al()` (şu an görünen) · `os()` (bilgisayarın tercihi).
 *   anahtar AÇIK  = kayıt yok → kartların hiçbiri seçili değil, görünen oda "şu an bu" (kesik çerçeve)
 *   anahtar KAPALI = kayıt var → görünen oda seçili
 *
 * 🔴 Kartlar BİR KEZ kurulur, sonra YERİNDE güncellenir (`guncelle`). Eski panel her seçimde
 *    `innerHTML`'i baştan yazıyordu → klavyeyle seçen kullanıcının odağı BODY'ye düşüyordu, ve dil
 *    değişince kartlar çevrilmiyordu (yalnız ilk açılışta çizilirdi).
 * 🔴 Klavye: role=radio grubu → TEK Tab durağı (roving tabindex), ok tuşları gezer VE seçer,
 *    Home/End uçlara gider, odak seçimden sonra yerinde kalır.
 */
(function () {
  'use strict';

  var ODALAR = ['koyu', 'orta', 'acik'];
  var _kuruldu = false;

  function _tpt(anahtar, degerler) {
    return (window.YukiDil && window.YukiDil.t) ? window.YukiDil.t(anahtar, degerler) : String(anahtar);
  }
  /* Sözlük metni: önce kaçırılır, sonra **kalın** (google-baglanti `_vurgu` ile aynı kural) */
  function _vurgu(s) {
    return String(s == null ? '' : s).replace(/[&<>"']/g, function (c) {
      return { '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c];
    }).replace(/\*\*(.+?)\*\*/g, '<b>$1</b>')
      .replace(/→/g, '<span class="tm-ok" aria-hidden="true">→</span>');   // ok glifi metne göre büyütülür (goz tur1 #10)
  }

  /* Metinli her şey çeviri anahtarıyla — ad/ne/neden tablosu GETTER gibi okunur (dil değişince tazelenir) */
  function _oda(k) {
    if (k === 'koyu') return { ad: _tpt('tema.koyu.ad'), ne: _tpt('tema.oda.koyu.ne'), neden: _tpt('tema.oda.koyu.neden') };
    if (k === 'orta') return { ad: _tpt('tema.orta.ad'), ne: _tpt('tema.oda.orta.ne'), neden: _tpt('tema.oda.orta.neden') };
    return { ad: _tpt('tema.acik.ad'), ne: _tpt('tema.oda.acik.ne'), neden: _tpt('tema.oda.acik.neden') };
  }
  function _temaAdi(k) { return _oda(k).ad; }

  /* Dizüstü ekranı: gerçek Yuki ekranının çizgilerle küçültülmüşü; `data-tema` ile kendi temasını taşır */
  function _mini(t) {
    return '<span class="tm-mini" data-tema="' + t + '" aria-hidden="true">'
      + '<span class="y"><span class="m"><i></i><b></b></span>'
      + '<span class="n ak"><i></i><b></b></span><span class="n"><i></i><b></b></span><span class="n"><i></i><b></b></span>'
      + '<span class="n"><i></i><b></b></span><span class="n"><i></i><b></b></span></span>'
      + '<span class="i"><span class="u"><b></b><span><i></i><i></i></span></span>'
      + '<span class="b k"><b></b><b></b></span><span class="b s"><b></b></span><span class="b k"><b></b></span>'
      + '<span class="g"><span class="a"></span><span class="d"></span></span></span></span>';
  }
  var _YILDIZ = [[8, 14], [22, 30], [38, 10], [52, 24], [66, 8], [76, 34], [90, 20], [14, 52], [86, 48]];
  function _yildizlar() {
    return _YILDIZ.map(function (p) { return '<i class="tm-yildiz" style="left:' + p[0] + '%;top:' + p[1] + '%"></i>'; }).join('');
  }

  function _kur() {
    var kap = document.getElementById('tema-secenekler');
    var sis = document.getElementById('tema-sistem');
    if (!kap || !sis) return false;
    kap.classList.add('tm-izgara');
    kap.innerHTML = ODALAR.map(function (k) {
      return '<button type="button" class="tm-oda" role="radio" aria-checked="false" tabindex="-1" data-tema-secim="' + k + '">'
        + '<span class="tm-sahne tm-s-' + k + '" aria-hidden="true"><span class="tm-isik"></span>' + (k === 'koyu' ? _yildizlar() : '')
        + '<span class="tm-lap">' + _mini(k) + '</span></span>'
        + '<span class="tm-govde"><span class="tm-ad"><span class="tm-ad-metin"></span><span class="tm-et" hidden></span><span class="tm-tik" aria-hidden="true"></span></span>'
        + '<span class="tm-ne"></span><span class="tm-neden"></span></span></button>';
    }).join('');
    sis.className = 'tm-sistem';
    sis.innerHTML = '<button type="button" class="tm-sw" role="switch" id="tema-sistem-anahtar" aria-checked="false"'
      + ' aria-labelledby="tema-sistem-ad" aria-describedby="tema-sistem-durum"></button>'
      + '<span class="tm-sw-et" id="tema-sistem-et"></span>'
      + '<div class="tm-yay"><span class="tm-sis-ad" id="tema-sistem-ad"></span>'
      + '<span class="tm-sis-ne" id="tema-sistem-durum" aria-live="polite"></span></div>';

    var oge = [].slice.call(kap.querySelectorAll('[role=radio]'));
    oge.forEach(function (b, i) {
      b.addEventListener('click', function () { _sec(b.getAttribute('data-tema-secim')); });
      b.addEventListener('keydown', function (e) {
        var d = { ArrowRight: 1, ArrowDown: 1, ArrowLeft: -1, ArrowUp: -1 }[e.key];
        var n = null;
        if (d) n = oge[(i + d + oge.length) % oge.length];
        else if (e.key === 'Home') n = oge[0];
        else if (e.key === 'End') n = oge[oge.length - 1];
        if (!n) return;
        e.preventDefault();
        _sec(n.getAttribute('data-tema-secim'));
        n.focus();                    // odak seçimin yanında kalır — yeniden çizim yok
      });
    });
    document.getElementById('tema-sistem-anahtar').addEventListener('click', function () {
      var T = window.YukiTema; if (!T) return;
      /* Açıkken kapat: şu an görünen odayı SEÇ (kullanıcı bir şeyin değişmesini beklemez);
         kapalıyken aç: 'sistem' kaydı yaz, bilgisayarı dinle */
      if (T.sistemde()) T.ayarla(T.al()); else T.sistemeBirak();
      guncelle();
    });
    return true;
  }

  function _sec(k) {
    var T = window.YukiTema; if (!T) return;
    T.ayarla(k);
    guncelle();
  }

  /* Yerinde güncelleme: odak, kaydırma, hover bozulmaz */
  function guncelle() {
    var T = window.YukiTema; if (!T || !_kuruldu) return;
    var kap = document.getElementById('tema-secenekler'); if (!kap) return;
    var takip = T.sistemde();
    var simdi = T.al();                 // şu an görünen ('koyu' | 'orta' | 'acik')
    var os = T.os();                    // bilgisayarın tercihi ('koyu' | 'acik')
    kap.classList.toggle('takipte', takip);
    [].forEach.call(kap.querySelectorAll('[role=radio]'), function (b) {
      var k = b.getAttribute('data-tema-secim'), m = _oda(k);
      var secili = !takip && k === simdi;
      var buAn = takip && k === simdi;
      b.setAttribute('aria-checked', secili ? 'true' : 'false');
      /* roving tabindex: grupta TEK durak — seçili oda; seçili yoksa görünen oda */
      b.setAttribute('tabindex', (secili || buAn) ? '0' : '-1');
      b.classList.toggle('takip', buAn);
      b.querySelector('.tm-ad-metin').textContent = m.ad;
      b.querySelector('.tm-ne').textContent = m.ne;
      b.querySelector('.tm-neden').textContent = m.neden;
      var et = b.querySelector('.tm-et');
      et.textContent = _tpt('tema.oda.simdi-bu');
      et.hidden = !buAn;
    });
    var sis = document.getElementById('tema-sistem');
    sis.classList.toggle('acik', takip);
    var sw = document.getElementById('tema-sistem-anahtar');
    sw.setAttribute('aria-checked', takip ? 'true' : 'false');
    document.getElementById('tema-sistem-et').textContent = takip ? _tpt('tema.sistem.acik') : _tpt('tema.sistem.kapali');
    document.getElementById('tema-sistem-ad').textContent = _tpt('tema.sistem.baslik');
    var osAd = os === 'koyu' ? _tpt('tema.sistem.os-gece') : _tpt('tema.sistem.os-gunduz');
    var durum = takip
      ? _tpt('tema.sistem.acik-durum', { os: osAd, tema: _temaAdi(simdi) })
      : _tpt('tema.sistem.kapali-durum', { os: osAd, tema: _temaAdi(os).toLowerCase() });
    document.getElementById('tema-sistem-durum').innerHTML = _vurgu(_tpt('tema.sistem.anlat') + ' ' + durum);
  }

  /* HQ menüsü paneli her açışında çağırır (kayıt/OS panel dışında değişmiş olabilir) */
  window.temaPanelAc = function () {
    if (!_kuruldu) _kuruldu = _kur();
    guncelle();
  };

  window.addEventListener('yuki-tema-degisti', guncelle);   // bilgisayar temayı değiştirdi (Sistem açıkken), başka yoldan ayarlandı
  window.addEventListener('yuki-dil-degisti', guncelle);    // kartlar + durum satırı yeni dilde
})();
