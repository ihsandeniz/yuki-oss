/* ═══════════════════════════════════════════════════════════════════════════
   BİLDİRİM — ürünün TEK bildirim mekanizması          (2026-08-28)

   NEDEN VAR
   ─────────
   C4 kapısı (docs/tasarim-2026-08-20/06-OLCUM-KAPILARI.md) diyor ki:
   *"sessiz başarısızlık = 0 — bir işlem başarısızsa kullanıcı GÖRMELİ."*
   Ölçüm bunun tutulmadığını gösterdi (2026-08-27, FAZ 6 gerçek veri
   ölçümü): 13 `catch` bloğu kullanıcının başlattığı bir eylemi yutuyordu.

   Sebep "toast yoktu" değildi — İKİ toast vardı, üstelik üçüncü bir yerde
   HİÇ yoktu:
     · core.js::showToast         → #toast-container + .toast    (21 çağrı)
     · intro-sequences.js::toast  → #hq-toast + .hq-toast        (46 çağrı)
     · planner.html               → hiçbiri; 9 CRUD catch'i tamamen sessiz
   İlk ikisi ayrıca ESKİ renk sözlüğünü (--accent/--gold/#ff1744) kullanıyordu;
   FAZ 7'nin "3 sözlük → 1" kararını deliyorlardı ve kontrast turu (kontrast-
   turu.py) onları üç temada ölçmüyordu.

   Bu dosya tekini bırakır. Ötekiler SİLİNMEDİ, buraya DEVREDER — 67 çağrı
   yerinin hiçbiri değişmedi. Yeni kod doğrudan `bildir()` çağırır.

   GÖRSEL DİL BURADA TANIMLANMAZ
   ──────────────────────────────
   Renk/ölçü/hareket ogeler.css § 12'den gelir (.bildirim-kap / .bildirim).
   Buraya `style.color = ...` yazma: token dışına çıkan bir yüzey, kontrast
   turunun ölçmediği bir yüzeydir — 62 ihlali 0'a indiren tur onu göremez.

   HATA KENDİLİĞİNDEN KAYBOLMAZ
   ────────────────────────────
   C4'ün yarısı budur: 3 saniyede kaybolan bir hata mesajı, kullanıcı ekrana
   bakmıyorsa hiç gösterilmemiş demektir. `tip='hata'` kapanma düğmesi getirir
   ve zamanlayıcı KURMAZ. Uyarı/olumlu bildirimler kendiliğinden kapanır.
   ═══════════════════════════════════════════════════════════════════════════ */
(function () {
  'use strict';

  var VARSAYILAN_SURE = 4200;   // uyarı/olumlu; hata için kullanılmaz
  var EN_FAZLA        = 4;      // aynı anda ekranda; taşarsa en eskisi düşer

  /* Eski çağrı yerlerinin tip adları buraya çevrilir. `error`/`err` ikisi de
     sahada kullanılıyordu — style.css yalnız `.toast-error` tanımladığı için
     tab-switcher.js'in gönderdiği `'err'` HİÇBİR renk almıyordu (sessizce
     varsayılan kenarla çiziliyordu). Tek sözlük bunu da kapatır. */
  var TIPLER = {
    hata: 'hata', err: 'hata', error: 'hata', hata_: 'hata',
    uyari: 'uyari', warn: 'uyari', warning: 'uyari',
    olumlu: 'olumlu', ok: 'olumlu', success: 'olumlu'
  };

  var _kap = null;

  /* Kap ERKEN kurulur, ilk bildirimde değil. Sebep erişilebilirlik: aria-live
     bölgesi DOM'a içerikle BİRLİKTE girerse ekran okuyucu ilk mesajı çoğu
     zaman duyurmaz — bölgenin önceden var olması gerekir. */
  function kap() {
    if (_kap && _kap.isConnected) return _kap;
    _kap = document.getElementById('bildirim-kap');
    if (!_kap) {
      _kap = document.createElement('div');
      _kap.id = 'bildirim-kap';
      _kap.className = 'bildirim-kap';
      /* polite: hata dışındaki bildirimler kullanıcının okuduğu cümleyi kesmez.
         Hata gelince aşağıda geçici olarak assertive'e çekilir. */
      _kap.setAttribute('role', 'status');
      _kap.setAttribute('aria-live', 'polite');
      _kap.setAttribute('aria-atomic', 'false');
      document.body.appendChild(_kap);
    }
    return _kap;
  }

  function hazirla() { if (document.body) kap(); }
  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', hazirla, { once: true });
  } else {
    hazirla();
  }

  /* Sohbetin giriş alanına binme (göz tur 1, AJAN 8: kademe bildirimi alttaki
     çipin üstüne biniyordu). Konum her bildirimde AYNI kalır — sağ alt köşe;
     yalnız giriş alanı görünürken onun üstüne çıkar. Ölçü JS'te, görsel CSS'te
     (`--bildirim-kacin`, ogeler.css § 12). Kademe kapısı bildirimi sekme
     sohbete DÖNMEDEN çağırır → ölçü bir sonraki karede de tekrarlanır. */
  function kacinmaOlc() {
    var k = kap();
    var alan = document.getElementById('input-area');
    var r = alan && alan.offsetParent ? alan.getBoundingClientRect() : null;
    var kacin = r && r.height ? Math.max(0, Math.round(window.innerHeight - r.top)) : 0;
    k.style.setProperty('--bildirim-kacin', kacin + 'px');
  }
  function kacinmaZamanla() {
    kacinmaOlc();
    requestAnimationFrame(function () { requestAnimationFrame(kacinmaOlc); });
  }
  window.addEventListener('resize', function () { if (_kap && _kap.firstChild) kacinmaOlc(); });
  document.addEventListener('tabchange', function () { if (_kap && _kap.firstChild) kacinmaZamanla(); });

  function kapat(el) {
    if (!el || el.dataset.kapaniyor) return;
    el.dataset.kapaniyor = '1';
    clearTimeout(el._zamanlayici);
    el.classList.add('bildirim-cikis');
    /* animationend'e güvenilmez: `prefers-reduced-motion` altında çıkış
       animasyonu hiç koşmaz ve olay HİÇ gelmez → düğüm ekranda kalırdı. */
    setTimeout(function () { if (el.parentNode) el.parentNode.removeChild(el); }, 200);
  }

  /* Aynı mesaj arka arkaya gelirse üst üste yığmak yerine mevcut olanı tazele.
     Gerekçe: fsApiPost gibi ortak yardımcılar tek kullanıcı eyleminde birden
     çok kez çağrılabiliyor (12 çağrı yeri) — 5 özdeş kutu ekranı kaplardı. */
  function ayniyiBul(mesaj, tip) {
    var mevcut = kap().querySelectorAll('.bildirim');
    for (var i = 0; i < mevcut.length; i++) {
      var el = mevcut[i];
      if (!el.dataset.kapaniyor && el.dataset.mesaj === mesaj && (el.dataset.tip || '') === tip) return el;
    }
    return null;
  }

  function tasmayiKirp() {
    var canli = Array.prototype.slice.call(kap().querySelectorAll('.bildirim'))
      .filter(function (el) { return !el.dataset.kapaniyor; });
    var fazla = canli.length - EN_FAZLA;
    if (fazla <= 0) return;
    /* Hatalar en SON düşer — kullanıcının görmesi gereken tek sınıf onlar.
       Önce eski uyarı/olumlu bildirimler kırpılır, sıra bitmezse hatalara gelinir. */
    var sira = canli.filter(function (el) { return el.dataset.tip !== 'hata'; })
      .concat(canli.filter(function (el) { return el.dataset.tip === 'hata'; }));
    for (var i = 0; i < fazla && i < sira.length; i++) kapat(sira[i]);
  }

  /**
   * Kullanıcıya bir şey söyler.
   * @param {string} mesaj  NE OLDUĞUNU söyleyen TR cümle. "Hata oluştu" DEĞİL —
   *                        "Görev silinemedi, çöp kutusunda duruyor" gibi.
   * @param {string} [tip]  'hata' | 'uyari' | 'olumlu' | '' (eski adlar da geçer)
   * @param {number} [sure] ms; hata tipinde YOK SAYILIR (kullanıcı kapatır).
   * @param {Array<{etiket:string, eylem:Function, birincil?:boolean}>} [eylemler]
   *        Bildirimin içinde düğme(ler) — "Sil / Vazgeç", "Geri al" (UI-F001,
   *        2026-10-09). Düğmeye basılınca eylem koşar ve bildirim kapanır.
   *        `confirm()` yerine bu: native diyalog Electron penceresini kilitler.
   */
  function bildir(mesaj, tip, sure, eylemler) {
    mesaj = String(mesaj == null ? '' : mesaj).trim();
    if (!mesaj) return null;
    tip = TIPLER[String(tip || '').toLowerCase()] || '';

    var k = kap();
    var eski = ayniyiBul(mesaj, tip);
    if (eski) {                      // zamanlayıcıyı tazele, yenisini kurma
      clearTimeout(eski._zamanlayici);
      if (tip !== 'hata') {
        eski._zamanlayici = setTimeout(function () { kapat(eski); }, sure > 0 ? sure : VARSAYILAN_SURE);
      }
      return eski;
    }

    var el = document.createElement('div');
    el.className = 'bildirim';
    if (tip) el.dataset.tip = tip;
    el.dataset.mesaj = mesaj;

    var metin = document.createElement('span');
    metin.className = 'bildirim-metin';
    metin.textContent = mesaj;       // textContent: mesaj sunucu gövdesinden gelebilir
    el.appendChild(metin);

    if (eylemler && eylemler.length) {
      el.classList.add('bildirim-eylemli');
      eylemler.forEach(function (e) {
        var d = document.createElement('button');
        d.type = 'button';
        d.className = 'bildirim-eylem' + (e.birincil ? ' bildirim-eylem-birincil' : '');
        d.textContent = e.etiket;
        d.addEventListener('click', function () {
          kapat(el);
          if (typeof e.eylem === 'function') e.eylem();
        });
        el.appendChild(d);
      });
    }

    if (tip === 'hata') {
      /* Hata duyurusu kullanıcının okuduğunu kesmeli — ama bölge kalıcı olarak
         assertive kalırsa sonraki her olumlu bildirim de araya girer. */
      k.setAttribute('aria-live', 'assertive');
      setTimeout(function () { k.setAttribute('aria-live', 'polite'); }, 1000);

      var dugme = document.createElement('button');
      dugme.type = 'button';
      dugme.className = 'bildirim-kapat';
      dugme.setAttribute('aria-label', 'Bildirimi kapat');
      dugme.textContent = '×';
      dugme.addEventListener('click', function () { kapat(el); });
      el.appendChild(dugme);
    }

    k.appendChild(el);
    kacinmaZamanla();
    tasmayiKirp();

    if (tip !== 'hata') {
      el._zamanlayici = setTimeout(function () { kapat(el); }, sure > 0 ? sure : VARSAYILAN_SURE);
    }
    return el;
  }

  function hepsiniKapat() {
    var mevcut = kap().querySelectorAll('.bildirim');
    for (var i = 0; i < mevcut.length; i++) kapat(mevcut[i]);
  }

  window.bildir = bildir;
  window.Bildirim = { goster: bildir, kapat: kapat, hepsiniKapat: hepsiniKapat };

  /* Geriye dönük ad. core.js kendi showToast'ını bunun üstüne yazmaz —
     orada gövdesi bu çağrıya devredildi; bu satır planner.html gibi core.js
     YÜKLEMEYEN sayfalarda da eski adın çalışmasını sağlar. */
  if (typeof window.showToast !== 'function') {
    window.showToast = function (mesaj, tip, sure) { return bildir(mesaj, tip, sure); };
  }
})();
