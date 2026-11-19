/* ════════════════════════════════════════════════════════════════════
   gfx.js — Grafik Kalitesi Yöneticisi (kullanıcı seçimi)

   2 kademe:
     normal — Varsayılan. Tüm efektler açık. Mevcut davranışın AYNISI.
     hafif  — Dönen SVG katmanları ve glow filtreleri kapalı. Düşük CPU.

   🔴 ULTRA KADEMESİ BİLEREK YOK. Kişisel Alice'te "rezerve" etiketiyle
   duruyor (menüde var, hiçbir şey yapmıyor). Satılan üründe böyle bir
   seçenek "ilan edilen ama uygulanmamış özellik" sınıfına girer —
   2026-08-01'de tam bu sınıftan bir sorun yaşandı (ilan edilen 8
   özellikten 4'ü sahteydi). Kural: ya uygula, ya menüye koyma.
   İleride gerçekten uygulanırsa TIERS'a eklenir.

   Seçim <html data-gfx="..."> özniteliğine yazılır; kurallar css/gfx.css'te.

   ⚠️ perf-tier.js (data-perf) ile KARIŞTIRMA — o DONANIMA GÖRE OTOMATİK,
   bu KULLANICI SEÇİMİ. Ayrı öznitelikler, birlikte çalışırlar.

   ÖLÇÜM GEREKÇESİ (kişisel Alice, 2026-08-01): sohbet sekmesinde 89
   çalışan animasyon ölçüldü — 77'si dönen SVG katmanı (her kare
   re-raster, ekranın %157'si kadar alan), 6'sı drop-shadow filtreli,
   1'i tam ekran background-position. Toplam ~%92 çekirdek; hafif
   kademesinde CPU %48 düşüyor. Diğer sekmelerde 1 animasyon.
   ════════════════════════════════════════════════════════════════════ */
(function () {
  'use strict';

  var KEY = 'yukiGfx_v1';
  var DEFAULT = 'normal';

  var TIERS = [
    /* 🔴 `label`/`desc` METİN DEĞİL ANAHTAR (FAZ 3 · Dalga 2 · Blok 7).
       Bu dizi modül yüklenirken bir kez değerlenir; içine `t()` yazılsaydı
       iki kademenin adı açılıştaki dilde DONARDI (hata vermeden). Çözüm
       çizim anında: `renderGfxBolumu` ve `chat-modes.js` `t()` ile açar.
       ⚠️ `key` çevrilmez — `VALID` ve localStorage değeri ondan türüyor. */
    { key: 'normal', label: 'gfx.normal.ad', icon: '◆',
      desc: 'gfx.normal.aciklama' },
    { key: 'hafif',  label: 'gfx.hafif.ad',  icon: '◇',
      desc: 'gfx.hafif.aciklama' }
  ];
  var VALID = TIERS.map(function (t) { return t.key; });

  function read() {
    var v;
    try { v = localStorage.getItem(KEY); } catch (e) { v = null; }
    // Kişiselden gelen 'ultra' değeri (ya da bozuk değer) varsayılana düşer.
    if (VALID.indexOf(v) >= 0) return v;
    /* 🔴 Depoda geçerli bir değer yoksa, erken snippet'in <html>'e BASTIĞI değeri
       sürdür — kendi başımıza yeniden karar VERME.
       Sebep: açılış kararını (zayıf makinede otomatik HAFİF) index.html'deki erken
       snippet veriyor, çünkü ilk boyamadan önce olmak zorunda. Burada localStorage'ı
       yeniden okuyup körlemesine uygulamak, aynı soruya ikinci bir cevap üretir ve
       depo bir sebeple okunamadığında snippet'in kararını SESSİZCE geri alır.
       (Bu tam olarak `surum.js` dersi: iki yerde üretilen cevap er geç ayrışır ve
       ayrıştığı yere kimse bakmaz. Canlı testte bizzat görüldü — 2026-08-12.) */
    var damga = document.documentElement.getAttribute('data-gfx');
    return VALID.indexOf(damga) >= 0 ? damga : DEFAULT;
  }

  function apply(pref) {
    document.documentElement.setAttribute('data-gfx', pref);
  }

  var _pref = read();
  apply(_pref);   // index.html'deki inline satır zaten bastıysa da zararsız (aynı değer)

  /**
   * Otomatik geçiş bildirimi (karar D11 = A + B, 2026-08-12).
   *
   * A) Zayıf makinede HAFİF'e otomatik geçiliyor — kararı index.html'deki erken
   *    snippet veriyor (ilk boyamadan önce olmalı, yoksa bir kare tam efektli çizilir).
   * B) Kullanıcıya SÖYLENİYOR ve tek tıkla geri alınabiliyor. Sessizce görünüm
   *    değiştirmek, ürünün "ilan et ama uygulama" karşıtı kuralının aynası:
   *    yapılan işi de saklama.
   *
   * ⚠️ Metin dürüst: HAFİF'in CPU'yu ne kadar düşürdüğü makineye göre değişiyor
   * (geliştiricinin Win10 makinesinde eski sürümü hiç düşürmüyordu, bu yüzden yeniden
   * yazıldı). O yüzden "daha hızlı olacak" DEMİYOR, ne yapıldığını söylüyor.
   */
  function _gft(anahtar, degerler){ return (window.YukiDil && window.YukiDil.t) ? window.YukiDil.t(anahtar, degerler) : String(anahtar); }

  function _otoBildir() {
    if (!window.__YUKI_GFX_OTO__) return;
    var kutu = document.createElement('div');
    kutu.className = 'gfx-oto-bildirim';
    kutu.innerHTML =
      '<span class="gfx-oto-metin">' + _gft('gfx.otobildir.metin') + '</span>'
      + '<button class="gfx-oto-btn" data-eylem="geri">' + _gft('gfx.otobildir.geri') + '</button>'
      + '<button class="gfx-oto-btn gfx-oto-kapat" data-eylem="kapat">' + _gft('gfx.otobildir.tamam') + '</button>';
    kutu.addEventListener('click', function (e) {
      var b = e.target.closest('[data-eylem]');
      if (!b) return;
      if (b.dataset.eylem === 'geri') window.Gfx.set('normal');
      kutu.remove();
    });
    document.body.appendChild(kutu);
    // Kendiliğinden kaybolmasın: kullanıcı görmeden kapanan bildirim, hiç
    // gösterilmemiş sayılır. Kapatma kararı kullanıcıda.
  }
  // Açık bildirim kullanıcı kapatana kadar durur → dil değişince metni tazelenir.
  window.addEventListener('yuki-dil-degisti', function () {
    var kutu = document.querySelector('.gfx-oto-bildirim');
    if (!kutu) return;
    var m = kutu.querySelector('.gfx-oto-metin');
    var g = kutu.querySelector('[data-eylem="geri"]');
    var k = kutu.querySelector('[data-eylem="kapat"]');
    if (m) m.textContent = _gft('gfx.otobildir.metin');
    if (g) g.textContent = _gft('gfx.otobildir.geri');
    if (k) k.textContent = _gft('gfx.otobildir.tamam');
  });
  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', _otoBildir);
  } else {
    _otoBildir();
  }

  window.Gfx = {
    TIERS: TIERS,
    get: function () { return _pref; },
    set: function (key) {
      if (VALID.indexOf(key) < 0) return false;
      _pref = key;
      try { localStorage.setItem(KEY, key); } catch (e) {}
      apply(key);
      document.dispatchEvent(new CustomEvent('gfxchange', { detail: { pref: key } }));
      return true;
    }
  };
})();
