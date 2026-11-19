/* ============================================================================
   YUKI · MİNİ HUD — kart tarafı  (mini.html · 2026-10-04)

   Tek işi: "Yuki şu an ne yapıyor" sorusunu bir bakışta cevaplamak.
   Kişisel AliceAi'nin mini HUD'undan (6ba78e2 + sonrası) uyarlandı.

   ── MİMARİ ───────────────────────────────────────────────────────────────
   Bu sayfa WS AÇMAZ, API ÇAĞIRMAZ, getUserMedia/AudioContext KULLANMAZ.
   Durum, duygu, son mesaj ve mikrofon durumu ana pencereden gelir
   (js/mini-kopru.js → electron/mini-hud.js → preload `yukiMini`). İkinci bir
   bağlantı iki yüzeyin aynı durumu farklı bilmesi demekti; ikinci bir
   mikrofon akışı mikrofonu kilitlerdi.

   ⚠️ Ses SEVİYESİ yok: ürünün ana penceresinde paylaşılan bir ses veri yolu
   yok ve yeni bir ölçer yazmak bu işin sınırı dışında. Konuşma dalgası bu
   yüzden kendi ritmiyle salınır — "konuşuyor" bilgisini biçim taşır.

   ── DURUM = BİÇİM ────────────────────────────────────────────────────────
     idle      sabit halka + merkez nokta       nötr (--ink-3)
     listening halka + dışa yayılan nabız       yeşil (canlı ses)
     thinking  dönen yay                         nötr (--ink-2)
     talking   dikey dalga çubukları             yeşil (canlı ses)
     sleeping  küçük sönük nokta                 nötr (--ink-3)
     error     kesik halka, DÖNMEZ               kırmızı
   ============================================================================ */
(function () {
  'use strict';

  // Çeviri yardımcısı — ad dosyaya özel (klasik script'te `_t` core.js'inkini ezerdi).
  function _mht(anahtar, degerler) {
    return (window.YukiDil && window.YukiDil.t)
      ? window.YukiDil.t(anahtar, degerler) : String(anahtar);
  }

  var hud     = document.getElementById('hud');
  var tuval   = document.getElementById('hud-tuval');
  var etiketE = document.getElementById('hud-etiket');
  var metinE  = document.getElementById('hud-metin');
  var micD    = document.getElementById('hud-mic');
  var kulakD  = document.getElementById('hud-kulak');
  var ctx     = tuval.getContext('2d');

  /* `renk`: tokens.css değişken ADI — hex burada yazılmaz, çalışma anında
     okunur; tema değişince önbellek boşaltılır. */
  var DURUMLAR = {
    idle:      { renk: '--ink-3',       bicim: 'halka' },
    listening: { renk: '--yesil-ink',   bicim: 'nabiz' },
    thinking:  { renk: '--ink-2',       bicim: 'yay'   },
    talking:   { renk: '--yesil-ink',   bicim: 'dalga' },
    sleeping:  { renk: '--ink-3',       bicim: 'nokta' },
    error:     { renk: '--kirmizi-ink', bicim: 'kesik' }
  };
  // Sahne duygusu (modes/sohbet-sahne.js · DUYGULAR) — etiketin ikinci yarısı.
  var DUYGULAR = ['nod', 'happy', 'sad', 'angry', 'surprised', 'shy', 'tired', 'thinking', 'wave'];

  var S = { durum: 'idle', onceki: 'idle', duygu: null, bagli: false, mic: null };
  var gecisT = 1;
  var t0 = null;
  var raf = null;
  var hareketAzalt = window.matchMedia('(prefers-reduced-motion: reduce)');

  /* ── Token rengi → canvas ─────────────────────────────────────────────────
     Token'lar OKLCH; canvas'ın fillStyle'ı onu doğrudan almayabilir. Gizli bir
     ölçüm öğesine `color: var(--x)` yazıp hesaplanmış değeri okumak her
     tarayıcıda rgb()/color() verir — elle dönüşüm yok. */
  var _olcer = null;
  var _renk = {};
  function tokenRenk(ad) {
    if (_renk[ad]) return _renk[ad];
    if (!_olcer) {
      _olcer = document.createElement('span');
      _olcer.style.cssText = 'position:absolute;width:0;height:0;overflow:hidden;visibility:hidden';
      document.body.appendChild(_olcer);
    }
    _olcer.style.color = 'var(' + ad + ')';
    var v = getComputedStyle(_olcer).color || 'rgb(152,151,159)';
    _renk[ad] = v;
    return v;
  }
  // Alfa'yı canvas'ın globalAlpha'sıyla veriyoruz → renk biçimini ayrıştırmaya gerek yok.
  function boya(renk, alfa) { ctx.globalAlpha = Math.max(0, Math.min(1, alfa)); return renk; }

  var g = { w: 0, h: 0 };
  function olcekle() {
    var dpr = window.devicePixelRatio || 1;
    var r = tuval.getBoundingClientRect();
    if (!r.width || !r.height) return;
    g.w = r.width; g.h = r.height;
    tuval.width = Math.round(r.width * dpr);
    tuval.height = Math.round(r.height * dpr);
    ctx.setTransform(dpr, 0, 0, dpr, 0, 0);   // SIFIRLA — katlanarak birikmesin
  }

  /* ══ ÇİZİMLER — ortak sözleşme: (renk, alfa, faz, R), merkeze çizer ══ */
  function cizHalka(renk, a, faz, R) {
    var nefes = hareketAzalt.matches ? 1 : 1 + Math.sin(faz * 1.2) * 0.03;
    ctx.strokeStyle = boya(renk, 0.6 * a); ctx.lineWidth = 1.5;
    ctx.beginPath(); ctx.arc(0, 0, R * 0.72 * nefes, 0, Math.PI * 2); ctx.stroke();
    ctx.fillStyle = boya(renk, 0.9 * a);
    ctx.beginPath(); ctx.arc(0, 0, R * 0.16, 0, Math.PI * 2); ctx.fill();
  }
  function cizNabiz(renk, a, faz, R) {
    var p = hareketAzalt.matches ? 0.5 : (faz * 0.9) % 1;
    ctx.strokeStyle = boya(renk, (1 - p) * 0.5 * a); ctx.lineWidth = 1.5;
    ctx.beginPath(); ctx.arc(0, 0, R * (0.5 + p * 0.5), 0, Math.PI * 2); ctx.stroke();
    ctx.strokeStyle = boya(renk, 0.8 * a); ctx.lineWidth = 2;
    ctx.beginPath(); ctx.arc(0, 0, R * 0.5, 0, Math.PI * 2); ctx.stroke();
    ctx.fillStyle = boya(renk, 0.9 * a);
    ctx.beginPath(); ctx.arc(0, 0, R * 0.16, 0, Math.PI * 2); ctx.fill();
  }
  function cizYay(renk, a, faz, R) {
    ctx.strokeStyle = boya(renk, 0.2 * a); ctx.lineWidth = 2;
    ctx.beginPath(); ctx.arc(0, 0, R * 0.62, 0, Math.PI * 2); ctx.stroke();
    var bas = hareketAzalt.matches ? -Math.PI / 2 : faz * 2.2;
    ctx.strokeStyle = boya(renk, 0.95 * a); ctx.lineWidth = 2.5; ctx.lineCap = 'round';
    ctx.beginPath(); ctx.arc(0, 0, R * 0.62, bas, bas + Math.PI * 0.42); ctx.stroke();
    ctx.lineCap = 'butt';
    ctx.fillStyle = boya(renk, 0.5 * a);
    ctx.beginPath(); ctx.arc(0, 0, R * 0.12, 0, Math.PI * 2); ctx.fill();
  }
  function cizDalga(renk, a, faz, R) {
    var adet = 7, ara = R * 0.30, kal = Math.max(2, R * 0.10);
    var x0 = -((adet - 1) * ara) / 2;
    ctx.lineCap = 'round'; ctx.lineWidth = kal;
    for (var i = 0; i < adet; i++) {
      var merkezlik = 1 - Math.abs(i - (adet - 1) / 2) / ((adet - 1) / 2);
      var salinim = hareketAzalt.matches ? 0.5 : (Math.sin(faz * 3.4 + i * 0.9) * 0.5 + 0.5);
      var y = R * (0.10 + (0.16 + merkezlik * 0.42) * (0.45 + 0.55 * salinim));
      ctx.strokeStyle = boya(renk, (0.5 + merkezlik * 0.5) * a);
      ctx.beginPath(); ctx.moveTo(x0 + i * ara, -y); ctx.lineTo(x0 + i * ara, y); ctx.stroke();
    }
    ctx.lineCap = 'butt';
  }
  function cizNokta(renk, a, faz, R) {
    var nefes = hareketAzalt.matches ? 1 : 1 + Math.sin(faz * 0.5) * 0.12;
    ctx.fillStyle = boya(renk, 0.6 * a);
    ctx.beginPath(); ctx.arc(0, 0, R * 0.15 * nefes, 0, Math.PI * 2); ctx.fill();
  }
  function cizKesik(renk, a, faz, R) {
    // Hata DÖNMEZ: hareket "çalışıyor" demektir.
    ctx.strokeStyle = boya(renk, 0.9 * a); ctx.lineWidth = 2;
    ctx.setLineDash([R * 0.22, R * 0.16]);
    ctx.beginPath(); ctx.arc(0, 0, R * 0.62, 0, Math.PI * 2); ctx.stroke();
    ctx.setLineDash([]);
    ctx.fillStyle = boya(renk, 0.9 * a);
    ctx.beginPath(); ctx.arc(0, 0, R * 0.13, 0, Math.PI * 2); ctx.fill();
  }
  var CIZERLER = { halka: cizHalka, nabiz: cizNabiz, yay: cizYay, dalga: cizDalga, nokta: cizNokta, kesik: cizKesik };

  function cizDurum(ad, a, faz, R) {
    var d = DURUMLAR[ad] || DURUMLAR.idle;
    (CIZERLER[d.bicim] || cizHalka)(tokenRenk(d.renk), a, faz, R);
  }

  function kare(zaman) {
    if (t0 === null) t0 = zaman;
    var faz = (zaman - t0) / 1000;
    if (gecisT < 1) gecisT = Math.min(1, gecisT + (hareketAzalt.matches ? 1 : 1 / 11));
    ctx.globalAlpha = 1;
    ctx.clearRect(0, 0, g.w, g.h);
    ctx.save();
    ctx.translate(g.w / 2, g.h / 2);
    var R = Math.min(g.w, g.h) / 2;
    var e = 1 - Math.pow(1 - gecisT, 4);   // ease-out — tokens --egri ailesi
    if (gecisT < 1 && S.onceki !== S.durum) cizDurum(S.onceki, 1 - e, faz, R);
    cizDurum(S.durum, e, faz, R);
    ctx.restore();
    ctx.globalAlpha = 1;
    raf = (!hareketAzalt.matches || gecisT < 1) ? requestAnimationFrame(kare) : null;
  }
  function dongu() { if (raf === null) raf = requestAnimationFrame(kare); }

  /* ── Metinler ─────────────────────────────────────────────────────────── */
  function etiketYaz() {
    if (!S.bagli) { etiketE.textContent = _mht('mini-hud.durum.baglanti-yok'); return; }
    var durum = _mht('mini-hud.durum.' + S.durum);
    // Duygu yalnız "sakin" değilse eklenir: "HAZIR · SAKİN" bilgi taşımaz.
    if (S.duygu && S.duygu !== 'nod' && S.duygu !== 'thinking' && DUYGULAR.indexOf(S.duygu) !== -1) {
      etiketE.textContent = _mht('mini-hud.etiket', { durum: durum, duygu: _mht('sahne.duygu.' + S.duygu) });
    } else {
      etiketE.textContent = durum;
    }
  }

  function micYaz() {
    var p = S.mic || {};
    var kayit = !!p.kayit, dinle = !!p.dinle;
    micD.setAttribute('aria-pressed', kayit ? 'true' : 'false');
    micD.classList.toggle('kayitta', kayit);
    var mt = _mht(kayit ? 'mini-hud.mikrofon-durdur' : 'mini-hud.mikrofon');
    micD.title = mt; micD.setAttribute('aria-label', mt);
    kulakD.hidden = p.dinleVar === false;
    kulakD.setAttribute('aria-pressed', dinle ? 'true' : 'false');
    var kt = _mht(dinle ? 'mini-hud.dinle-acik' : 'mini-hud.dinle');
    kulakD.title = kt; kulakD.setAttribute('aria-label', kt);
  }

  /* Son mesaj kutuya sığmazsa SÖZCÜK sınırında kısalır, sondaki boşluk ve
     noktalama atılır, tek '…' eklenir ( M15). CSS'in text-overflow'u harf
     ortasından kesip boşluk bırakıyordu ("planında …"). Tam metin title'da. */
  var _tamMetin = '';
  function metinYaz(tam) {
    _tamMetin = tam || '';
    metinE.textContent = _tamMetin;
    metinE.title = _tamMetin;
    if (!_tamMetin || metinE.scrollWidth <= metinE.clientWidth + 1) return;
    var kes = function (n) {
      return _tamMetin.slice(0, n).replace(/[\s.,;:!?·…-]+$/, '') + '…';
    };
    var lo = 0, hi = _tamMetin.length;
    while (lo < hi) {
      var orta = (lo + hi + 1) >> 1;
      metinE.textContent = kes(orta);
      if (metinE.scrollWidth <= metinE.clientWidth + 1) lo = orta; else hi = orta - 1;
    }
    // Sözcük ortasında bitmesin: sığan kısımda boşluk varsa son sözcüğü bütün at.
    var parca = _tamMetin.slice(0, lo), bosluk = parca.lastIndexOf(' ');
    if (bosluk > 0 && /\S/.test(_tamMetin.charAt(lo))) parca = parca.slice(0, bosluk);
    metinE.textContent = parca.replace(/[\s.,;:!?·…-]+$/, '') + '…';
  }

  /* ── Dış API ──────────────────────────────────────────────────────────── */
  function durumAyarla(yeni, detay, duygu) {
    if (!DURUMLAR[yeni]) yeni = 'idle';
    if (yeni !== S.durum) { S.onceki = S.durum; S.durum = yeni; gecisT = 0; }
    hud.setAttribute('data-state', S.durum);
    if (typeof duygu === 'string') S.duygu = duygu;
    if (typeof detay === 'string') metinYaz(detay);
    etiketYaz();
    dongu();
  }

  function bagliAyarla(bagli) {
    S.bagli = !!bagli;
    hud.setAttribute('data-bagli', S.bagli ? 'evet' : 'hayir');
    if (!S.bagli) {
      // Köprü kopunca eski durum YALANDIR — "dinliyor" yazıp dinlememek.
      S.durum = S.onceki = 'sleeping'; gecisT = 1;
      hud.setAttribute('data-state', 'sleeping');
      metinYaz(_mht('mini-hud.ana-kapali'));
    }
    etiketYaz();
    dongu();
  }

  /* ── Köprü ─────────────────────────────────────────────────────────────── */
  if (window.yukiMini && typeof window.yukiMini.dinle === 'function') {
    window.yukiMini.dinle(function (p) {
      if (!p) return;
      if (p.tip === 'durum') { if (!S.bagli) bagliAyarla(true); durumAyarla(p.durum, p.detay, p.duygu); }
      else if (p.tip === 'bagli') bagliAyarla(!!p.deger);
      else if (p.tip === 'mic') { S.mic = p; micYaz(); }
    });
    micD.addEventListener('click', function () { window.yukiMini.komut('mikrofon'); });
    kulakD.addEventListener('click', function () { window.yukiMini.komut('her-zaman-dinle'); });
    document.getElementById('hud-buyut').addEventListener('click', function () { window.yukiMini.buyut(); });
    document.getElementById('hud-gizle').addEventListener('click', function () { window.yukiMini.gizle(); });
  } else {
    // Tarayıcıda açıldı: kart çizilir ama veri gelmez — sessizce ölmez, "bağlantı yok" der.
    document.querySelector('.hud-kontrol').hidden = true;
    micD.disabled = true;
    kulakD.disabled = true;
    bagliAyarla(false);
  }

  /* Tema / dil başka pencerede (ana pencere) değişir; aynı origin'in
     localStorage'ı paylaşıldığı için `storage` olayı buraya da düşer. Kayıt
     yazmayız — yalnız aynı değeri bu belgeye uygularız. */
  window.addEventListener('storage', function (e) {
    if (e.key === 'yukiTema_v1' && window.YukiTema) {
      window.YukiTema.yenile();   // ortak kaydı oku (oda · 'sistem' · yok=koyu), YAZMA
    } else if (e.key === 'yukiDil_v1' && window.YukiDil && e.newValue) {
      window.YukiDil.sunucudan(e.newValue);
    }
  });
  window.addEventListener('yuki-tema-degisti', function () { _renk = {}; dongu(); });
  window.addEventListener('yuki-dil-degisti', function () { etiketYaz(); micYaz(); });

  /* ── Başlat ───────────────────────────────────────────────────────────── */
  olcekle();
  micYaz();
  dongu();
  window.addEventListener('resize', function () { olcekle(); dongu(); metinYaz(_tamMetin); });
  // Yazı tipi geç yüklenirse genişlik değişir — kısaltma yeniden ölçülsün.
  if (document.fonts && document.fonts.ready) document.fonts.ready.then(function () { metinYaz(_tamMetin); });
  if ('ResizeObserver' in window) {
    new ResizeObserver(function () { olcekle(); dongu(); }).observe(tuval.parentNode);
  }
  hareketAzalt.addEventListener('change', function () { t0 = null; dongu(); });

  // Ölçüm/hata ayıklama: konsoldan durum sürmek.
  window.YukiMiniHUD = { durumAyarla: durumAyarla, bagliAyarla: bagliAyarla };
})();
