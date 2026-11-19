/* ════════════════════════════════════════════════════════════════
   YUKI AÇILIŞ v4 — ortak motor
   Her öneri tek bir sahne kaydeder:
     YukiAcilis.sahne('<ad>', {
       sure:  toplam ms (3000-6000),
       cikis: son kaç ms uygulamaya geçiş (uygulama bu anda görünür olur),
       kur(ctx)     → Promise  (görsel yükle, DOM kur — bir kez),
       kare(t, ctx)            (t ms'deki görüntüyü ÇİZ — saf: yalnız t'ye bağlı)
     })
   ve YukiAcilis.baslat('<ad>', {app, onBitti}) ile oynar.

   Sözleşme (tests/test_acilis_animasyonu.py bunları ölçer):
     · tık / Enter / Esc / Space → doğrudan çıkış geçişine atlar; ikinci basış anında bitirir
     · prefers-reduced-motion (ya da ?azalt=1) → hiç oynamaz, uygulama hemen açılır
     · sahne hata fırlatırsa ya da rAF durursa (arka plan sekmesi) → bekçi bitirir;
       açılış uygulamayı ASLA kilitlemez
     · ?kayit=1 → zaman dışarıdan sürülür: window.__acilis.kare(ms) (Playwright kare kare kaydeder)
   Rastgelelik tohumlu (ctx.rnd) → canlı oynatma ile kayıt aynı görüntüyü verir.
   ════════════════════════════════════════════════════════════════ */
window.YukiAcilis = (function () {
  'use strict';

  var sahneler = {};
  var q = new URLSearchParams(location.search);
  var KAYIT = q.has('kayit');

  function azaltilmis() {
    if (q.has('azalt')) return true;
    return !!(window.matchMedia && window.matchMedia('(prefers-reduced-motion: reduce)').matches);
  }

  /* ── yardımcılar ── */
  function sinir(x, a, b) { return x < a ? a : x > b ? b : x; }
  function aralik(t, a, b) { return sinir((t - a) / (b - a), 0, 1); }
  function karis(a, b, k) { return a + (b - a) * k; }
  var yumusak = {
    cikCub: function (k) { return 1 - Math.pow(1 - k, 3); },
    gitCub: function (k) { return k < .5 ? 4 * k * k * k : 1 - Math.pow(-2 * k + 2, 3) / 2; },
    cikExp: function (k) { return k >= 1 ? 1 : 1 - Math.pow(2, -10 * k); },
    girExp: function (k) { return k <= 0 ? 0 : Math.pow(2, 10 * k - 10); },
    cikGeri: function (k) { var c = 1.70158, c3 = c + 1; return 1 + c3 * Math.pow(k - 1, 3) + c * Math.pow(k - 1, 2); },
    gitSin: function (k) { return -(Math.cos(Math.PI * k) - 1) / 2; }
  };
  function tohum(s) {           /* mulberry32 */
    return function () {
      s |= 0; s = s + 0x6D2B79F5 | 0;
      var t = Math.imul(s ^ s >>> 15, 1 | s);
      t = t + Math.imul(t ^ t >>> 7, 61 | t) ^ t;
      return ((t ^ t >>> 14) >>> 0) / 4294967296;
    };
  }
  function gorsel(src) {
    return new Promise(function (coz) {
      var im = new Image();
      im.decoding = 'async';
      im.onload = function () { coz(im); };
      im.onerror = function () { coz(null); };
      im.src = src;
    });
  }

  /* Siyah zeminli karakter görselini (yuki_fullbody.jpg) alfalı tuvale çevirir:
     zemin (en parlak kanal ≤ alt) saydam, çorap/eldiven gibi koyu ama gerçek
     kısımlar (≈ 29-60) opak kalır. Böylece Yuki 'screen' yerine normal çizilir
     ve arkasındaki efektleri örter. Görsel değişmez — yalnız zemini düşer. */
  function alfali(img, alt, ust) {
    if (!img) return null;
    alt = alt == null ? 10 : alt; ust = ust == null ? 32 : ust;
    var c = document.createElement('canvas');
    c.width = img.naturalWidth; c.height = img.naturalHeight;
    var g = c.getContext('2d', { willReadFrequently: true });
    g.drawImage(img, 0, 0);
    try {
      var d = g.getImageData(0, 0, c.width, c.height), p = d.data, k = 255 / (ust - alt);
      for (var i = 0; i < p.length; i += 4) {
        var m = p[i] > p[i + 1] ? p[i] : p[i + 1];
        if (p[i + 2] > m) m = p[i + 2];
        p[i + 3] = m <= alt ? 0 : m >= ust ? 255 : (m - alt) * k;
      }
      g.putImageData(d, 0, 0);
    } catch (e) { /* farklı köken → olduğu gibi */ }
    return c;
  }

  /* Varlık yolunu SAHNE BETİĞİNİN konumuna göre çözer, sayfanınkine göre değil:
     prototip /ui/acilis-v4/<ad>/ altında, canlı uygulama /ui/index.html'de açılır;
     sayfaya göre çözülseydi 'istasyon.webp' uygulamada /ui/istasyon.webp'e (404) giderdi.
     ('../../assets/…' canlıda tesadüfen çalışırdı: main.py /assets'i de kökten bağlıyor.) */
  function yolcu(betik) {
    var taban = betik && betik.src ? betik.src : location.href;
    return function (goreli) { return new URL(goreli, taban).href; };
  }

  function sahne(ad, tanim) { sahneler[ad] = tanim; }

  function baslat(ad, opts) {
    opts = opts || {};
    var tanim = sahneler[ad];
    var app = opts.app || document.getElementById('app');
    var gosterildi = false;
    function uygulamayiGoster() {
      if (gosterildi) return;
      gosterildi = true;
      if (app) app.style.display = '';
    }

    if (!tanim) { uygulamayiGoster(); return; }
    if (azaltilmis() && !KAYIT) {
      uygulamayiGoster();
      window.__acilisDurum = 'azaltilmis';
      if (opts.onBitti) opts.onBitti({ neden: 'azaltilmis' });
      return;
    }

    var kok = document.createElement('div');
    kok.id = 'yuki-acilis-v4';
    kok.className = 'ya-kok ya-' + ad;
    var _t = (window.YukiVeri && YukiVeri.t) || function (k, kaynak) { return kaynak; };
    kok.setAttribute('aria-label', _t('acilis.aria', 'Yuki açılış animasyonu — atlamak için tıkla ya da Esc'));
    kok.setAttribute('role', 'img');
    /* opts.kap: katmanın konacağı kap (canlıda baglanti.js'in #yuki-opening kabuğu) */
    (opts.kap || document.body).appendChild(kok);

    var ipucu = document.createElement('div');
    ipucu.className = 'ya-atla';
    ipucu.textContent = _t('acilis.atla', 'atla · esc');
    kok.appendChild(ipucu);

    var tuvaller = [];
    var ctx = {
      kok: kok, ad: ad, kayit: KAYIT,
      w: innerWidth, h: innerHeight,
      dpr: Math.min(window.devicePixelRatio || 1, 2),
      veri: {}, sure: tanim.sure, cikis: tanim.cikis,
      sinir: sinir, aralik: aralik, karis: karis, y: yumusak, tohum: tohum, gorsel: gorsel, alfali: alfali,
      dar: innerWidth < 640,
      tuval: function (sinif) {
        var cv = document.createElement('canvas');
        cv.className = 'ya-tuval ' + (sinif || '');
        kok.insertBefore(cv, ipucu);
        var o = { cv: cv, g: cv.getContext('2d') };
        tuvaller.push(o);
        boyutla(o);
        return o;
      },
      el: function (etiket, sinif, ebeveyn) {
        var e = document.createElement(etiket);
        if (sinif) e.className = sinif;
        (ebeveyn || kok).insertBefore(e, ebeveyn ? null : ipucu);
        return e;
      }
    };
    function boyutla(o) {
      o.cv.width = Math.round(ctx.w * ctx.dpr);
      o.cv.height = Math.round(ctx.h * ctx.dpr);
      o.cv.style.width = ctx.w + 'px';
      o.cv.style.height = ctx.h + 'px';
      o.g.setTransform(ctx.dpr, 0, 0, ctx.dpr, 0, 0);
    }
    function yenidenBoyut() {
      ctx.w = innerWidth; ctx.h = innerHeight; ctx.dar = ctx.w < 640;
      tuvaller.forEach(boyutla);
      if (tanim.boyut) tanim.boyut(ctx);
    }
    addEventListener('resize', yenidenBoyut);

    var veriSoz = window.YukiVeri ? YukiVeri.topla(ctx.veri, 900) : Promise.resolve(ctx.veri);
    var kurSoz = Promise.resolve().then(function () { return tanim.kur ? tanim.kur(ctx) : null; });

    var bitti = false, cikista = false;
    function bitir(neden) {
      if (bitti) return;
      bitti = true;
      cancelAnimationFrame(raf);
      clearTimeout(bekci);
      removeEventListener('resize', yenidenBoyut);
      kok.removeEventListener('click', atla);
      document.removeEventListener('keydown', tus);
      if (tanim.temizle) try { tanim.temizle(ctx); } catch (e) { /* yut */ }
      uygulamayiGoster();
      if (kok.parentNode) kok.parentNode.removeChild(kok);
      window.__acilisDurum = 'bitti';
      window.__acilisBitis = performance.now();
      if (opts.onBitti) opts.onBitti({ neden: neden || 'sure' });
    }

    function ciz(t) {
      if (bitti) return;
      if (t >= tanim.sure - tanim.cikis && !cikista) {
        cikista = true;
        kok.classList.add('ya-cikista');
        uygulamayiGoster();
        window.__acilisDurum = 'cikis';
      }
      ipucu.style.opacity = String(aralik(t, 600, 1000) * (1 - aralik(t, tanim.sure - tanim.cikis - 200, tanim.sure - tanim.cikis)) * .55);
      try {
        tanim.kare(t, ctx);
      } catch (e) {
        console.error('[acilis-v4] sahne hatası, açılış kapatılıyor:', e);
        bitir('hata');
        return;
      }
      if (t >= tanim.sure && !KAYIT) bitir('sure');
    }

    /* ── kayıt modu: zaman dışarıdan ── */
    if (KAYIT) {
      window.__acilis = {
        sure: tanim.sure, cikis: tanim.cikis, ctx: ctx,
        hazir: Promise.all([veriSoz, kurSoz]).then(function () {
          return tanim.hazirla ? tanim.hazirla(ctx) : null;
        }).then(function () { return true; }),
        kare: function (ms) { ciz(ms); return true; }
      };
      window.__acilisDurum = 'kayit';
      return;
    }

    /* ── canlı mod ── */
    var raf = 0, t0 = 0, ileri = 0, bekci = 0;
    function atla() {
      if (bitti) return;
      if (!t0) { bitir('atla'); return; }
      var t = performance.now() - t0 + ileri;
      var hedef = tanim.sure - tanim.cikis;
      if (t < hedef) ileri += hedef - t;
      else bitir('atla');
      window.__acilisAtlandi = performance.now();
    }
    function tus(e) {
      if (e.key === 'Enter' || e.key === 'Escape' || e.key === ' ') { e.preventDefault(); atla(); }
    }
    kok.addEventListener('click', atla);
    document.addEventListener('keydown', tus);

    function dongu() {
      if (bitti) return;
      ciz(performance.now() - t0 + ileri);
      raf = requestAnimationFrame(dongu);
    }
    /* görseller en çok 1,2 sn beklenir — sonra eksikle başlar (sahne null görseli tolere eder) */
    var basladi = false;
    function basla() {
      if (basladi || bitti) return;
      basladi = true;
      t0 = performance.now();
      window.__acilisDurum = 'oynuyor';
      window.__acilisBaslangic = t0;
      if (tanim.basla) tanim.basla(ctx);
      bekci = setTimeout(function () { bitir('bekci'); }, tanim.sure + 2500);
      dongu();
    }
    window.__acilisDurum = 'yukleniyor';
    kurSoz.then(basla, function (e) { console.error('[acilis-v4] kur hatası:', e); bitir('hata'); });
    setTimeout(basla, 1200);
    /* ilk boyama: siyah zemin hemen (uygulama göz kırpmasın) */
    return { atla: atla, bitir: bitir, ctx: ctx };
  }

  return { sahne: sahne, baslat: baslat, azaltilmis: azaltilmis, yolcu: yolcu };
})();
