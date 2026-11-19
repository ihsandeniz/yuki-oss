/* ============================================================================
   YUKI · TEMA ANAHTARI  (2026-08-27 — geliştirici: "dark, orta, beyaz")

   Üç kademe: koyu (varsayılan, ilk açılış hep koyu) · orta · acik · + 'sistem' (OS'u izle, yalnız açık seçimle). Değerler tokens.css'te,
   burada YALNIZ seçim + kalıcılık + yayma mantığı var.

   🔴 Bu dosya <head>'de, CSS'ten SONRA, SENKRON yüklenir. Sebebi FOUC:
   defer/async olsaydı sayfa önce koyu boyanır, sonra açığa atlardı — açık
   tema seçmiş kullanıcı her açılışta gözüne koyu bir flaş yer.

   PLAN ekranı ayrı bir belge (iframe: planner.html). Tema değişince ona
   postMessage ile haber verilir; kendi başına da localStorage'dan okur —
   iki yol da var çünkü iframe ana pencereden ÖNCE de yüklenebilir.
   ========================================================================= */
(function () {
  'use strict';

  var ANAHTAR = 'yukiTema_v1';
  var GECERLI = ['koyu', 'orta', 'acik'];
  /* 'sistem' ayrı tutulur: bir DEĞER değil, "kaydı sil ve OS'u dinle" demek.
     GECERLI'ye koysaydık data-tema="sistem" diye anlamsız bir öznitelik
     yazılırdı ve hiçbir CSS bloğu eşleşmezdi. */

  /* 'sistem' kaydı = kullanıcı HQ › Tema'da "Bilgisayarım karar versin"i AÇIKÇA açtı. */
  var SISTEM = 'sistem';

  function _kayit() {
    try { return localStorage.getItem(ANAHTAR); } catch (e) { return null; }
  }

  function _osTercihi() {
    try {
      if (window.matchMedia && window.matchMedia('(prefers-color-scheme: light)').matches) return 'acik';
    } catch (e) {}
    return 'koyu';
  }

  /* İlk açılış HEP KOYU (tasarım kararı 2026-11-12): kullanıcı bir şey seçmemişse
     bilgisayarın açık/koyu tercihine BAKILMAZ. Bilgisayarı izlemek yalnız kullanıcı
     "Sistem"i açıkça seçtiyse ('sistem' kaydı) olur; kullanıcının seçimi her zaman korunur. */
  function oku() {
    var t = _kayit();
    if (GECERLI.indexOf(t) !== -1) return t;
    if (t === SISTEM) return _osTercihi();
    return 'koyu';
  }

  function uygula(tema, kaydet) {
    if (GECERLI.indexOf(tema) === -1) tema = 'koyu';
    // Varsayılan koyu :root'ta tanımlı; öznitelik yalnız diğer ikisinde durur.
    // Böylece "tema yok" ile "koyu seçildi" aynı CSS yolundan geçer.
    if (tema === 'koyu') document.documentElement.removeAttribute('data-tema');
    else document.documentElement.setAttribute('data-tema', tema);

    if (kaydet) {
      try { localStorage.setItem(ANAHTAR, tema); } catch (e) {}
    }
    // PLAN iframe'ine haber ver (varsa)
    try {
      var f = document.getElementById('planner-iframe');
      if (f && f.contentWindow) f.contentWindow.postMessage({ type: 'tema', tema: tema }, location.origin);
    } catch (e) {}
    try {
      window.dispatchEvent(new CustomEvent('yuki-tema-degisti', { detail: { tema: tema } }));
    } catch (e) {}
  }

  // İlk boyamadan önce uygula
  uygula(oku(), false);

  /* iframe tarafı: ebeveynden gelen tema mesajını UYGULAR, KAYDETMEZ.
     🔴 Eskiden `uygula(tema, true)` idi: kullanıcı "Sistem"e bırakınca ebeveyn OS'un
     çözdüğü değeri ('koyu') iframe'e yollar, iframe onu AYNI origin'in localStorage'ına
     yazar ve "Sistem" seçimi 1 sn içinde 'koyu'ya kilitlenirdi (PLAN bir kez açılmışsa;
     OS değişiminde de aynı yol). Kayıt YALNIZ kullanıcı eyleminin yaptığı pencerede
     (`YukiTema.ayarla` / `sistemeBirak`) yazılır.
     Mesaj kapısı: yalnız bir çerçevenin içindeysek (üst pencere hiç dinlemez — kendi
     `postMessage`'ı ile tema değiştirilemesin), gönderen doğrudan ebeveynimiz ve aynı
     origin olmalı, değer geçerli olmalı (geçersiz değer 'koyu'ya DÜŞMEZ, yok sayılır). */
  window.addEventListener('message', function (e) {
    if (!e || !e.data || e.data.type !== 'tema') return;
    if (window.parent === window || e.source !== window.parent) return;
    if (e.origin !== location.origin) return;
    if (GECERLI.indexOf(e.data.tema) === -1) return;
    uygula(e.data.tema, false);
  });

  // Kullanıcı "Sistem"i seçtiyse OS teması değişince izle (başka durumda dokunma)
  try {
    var mq = window.matchMedia('(prefers-color-scheme: light)');
    var dinle = function () {
      if (_kayit() === SISTEM) uygula(mq.matches ? 'acik' : 'koyu', false);
    };
    if (mq.addEventListener) mq.addEventListener('change', dinle);
    else if (mq.addListener) mq.addListener(dinle);
  } catch (e) {}

  /* `YukiTema.secenekler` getter'ı metni çağrı anında çözer, burada tutulan çeviri
     durumu yok. Panel kartlarını `tema-panel.js` kendi dinleyicisiyle tazeler; bu dosya
     çevrilmiş sayıldığı için (test_bl402_kuyruk) olayı yine de dinler. */
  window.addEventListener('yuki-dil-degisti', function () {});

  function _tmt(anahtar, degerler){ return (window.YukiDil && window.YukiDil.t) ? window.YukiDil.t(anahtar, degerler) : String(anahtar); }

  window.YukiTema = {
    al: oku,
    /* Geçersiz değer YOK SAYILIR (eskiden sessizce 'koyu' yazılırdı) */
    ayarla: function (t) { if (GECERLI.indexOf(t) === -1) return; uygula(t, true); },
    /* Kullanıcı bir ODA (koyu/orta/acik) seçmiş mi */
    secimVar: function () { return GECERLI.indexOf(_kayit()) !== -1; },
    /* "Sistemi takip et" açık mı — yalnız açık 'sistem' kaydı; kayıt yoksa koyu (izleme yok) */
    sistemde: function () { return _kayit() === SISTEM; },
    /* Bilgisayarın şu anki tercihi ('koyu' | 'acik') — "Sistem"de Yuki'nin NE göstereceği
       ve panelin "şu an" satırı için; kayıttan bağımsız */
    os: _osTercihi,
    sistemeBirak: function () {
      try { localStorage.setItem(ANAHTAR, SISTEM); } catch (e) {}
      uygula(oku(), false);
    },
    /* Kaydı yeniden oku ve uygula, YAZMA — başka pencere kaydı değiştirdiğinde (storage olayı) */
    yenile: function () { uygula(oku(), false); },
    get secenekler() {
      return [
        { anahtar: 'koyu', ad: _tmt('tema.koyu.ad'),  aciklama: _tmt('tema.koyu.aciklama') },
        { anahtar: 'orta', ad: _tmt('tema.orta.ad'),  aciklama: _tmt('tema.orta.aciklama') },
        { anahtar: 'acik', ad: _tmt('tema.acik.ad'),  aciklama: _tmt('tema.acik.aciklama') },
        { anahtar: 'sistem', ad: _tmt('tema.sistem.ad'), aciklama: _tmt('tema.sistem.aciklama') }
      ];
    }
  };
})();
