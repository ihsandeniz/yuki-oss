/* ═══════════════════════════════════════════════════════════════════════════
   SOHBET GEÇMİŞİNİ TEMİZLE — onay + geri al        (UI-F001 · H9 · 2026-10-09)

   NEDEN VAR
   ─────────
   10-06 güvenlik denetimi (bulgu
   H9): çöp kutusu, komut paletindeki "temizle" ve Ctrl+L sohbet geçmişini
   ONAYSIZ ve KALICI siliyordu; Ctrl+L yazarken bile tetikleniyordu. Tek yanlış
   tuş, müşterinin bütün konuşma geçmişi demekti.

   AKIŞ
   ────
   1) `iste()` → bildirimde "Sil / Vazgeç" sorusu. `confirm()` YOK: native
      diyalog Electron penceresini kilitler (ürün kuralı, bkz. yedekleme.js).
   2) "Sil" → mesajlar ekrandan kalkar ama sunucuya HENÜZ gitmez; 5 sn'lik
      "Geri al" bildirimi çıkar. Geri al → düğümler aynen yerine döner.
   3) 5 sn dolunca (ya da sayfa kapanırken) silme isteği gider. İstek düşerse
      geçmiş sunucuda duruyor demektir → mesajlar geri konur + hata bildirimi
      (C4: sessiz başarısızlık yok).

   Sunucu isteği dışarıdan verilir (`gonder`) — core.js `authFetch` ile bağlar,
   test sahte bir gonder verir.
   ═══════════════════════════════════════════════════════════════════════════ */
(function () {
  'use strict';

  var GERI_AL_MS = 5000;
  var ONAY_MS    = 8000;   // soru bu kadar açık kalır; dokunulmazsa = vazgeç

  var bekleyen = null;     // { kutu, parca, zamanlayici, gonder }

  function t(k) {
    return (window.YukiDil && window.YukiDil.t) ? window.YukiDil.t(k) : String(k);
  }
  function bildir(mesaj, tip, sure, eylemler) {
    if (typeof window.bildir === 'function') return window.bildir(mesaj, tip, sure, eylemler);
    console.warn('[yuki] bildirim:', mesaj);
    return null;
  }

  function geriKoy(b) {
    // Bekleme sırasında yeni mesaj geldiyse eski geçmiş ONLARIN üstüne döner.
    b.kutu.insertBefore(b.parca, b.kutu.firstChild);
  }

  function kesinlestir(sayfaKapaniyor) {
    if (!bekleyen) return Promise.resolve(false);
    var b = bekleyen;
    bekleyen = null;
    clearTimeout(b.zamanlayici);
    return Promise.resolve()
      .then(function () { return b.gonder(!!sayfaKapaniyor); })
      .then(function (r) {
        if (r && r.ok === false) throw new Error('HTTP ' + r.status);
        return true;
      })
      .catch(function () {
        if (sayfaKapaniyor) return false;
        geriKoy(b);
        bildir(t('sohbet.temizlenemedi'), 'hata');
        return false;
      });
  }

  function geriAl() {
    if (!bekleyen) return false;
    var b = bekleyen;
    bekleyen = null;
    clearTimeout(b.zamanlayici);
    geriKoy(b);
    return true;
  }

  function sil(gonder) {
    var kutu = document.getElementById('messages');
    if (!kutu) return;
    kesinlestir(false);    // önceki bekleyen silme varsa önce o biter
    var parca = document.createDocumentFragment();
    while (kutu.firstChild) parca.appendChild(kutu.firstChild);
    bekleyen = {
      kutu: kutu, parca: parca, gonder: gonder,
      zamanlayici: setTimeout(function () { kesinlestir(false); }, GERI_AL_MS)
    };
    bildir(t('sohbet.temizlendi'), 'olumlu', GERI_AL_MS,
      [{ etiket: t('sohbet.geri-al'), eylem: geriAl, birincil: true }]);
  }

  /** Kullanıcı temizlemek istedi (çöp kutusu · palet · Ctrl+L). Hemen SİLMEZ. */
  function iste(gonder) {
    var kutu = document.getElementById('messages');
    if (!kutu || !kutu.firstChild) {
      bildir(t('sohbet.temizle-bos'), '', 2500);
      return;
    }
    bildir(t('sohbet.temizle-sor'), 'uyari', ONAY_MS, [
      { etiket: t('sohbet.temizle-evet'), eylem: function () { sil(gonder); }, birincil: true },
      { etiket: t('sohbet.temizle-vazgec'), eylem: function () {} }
    ]);
  }

  // Geri alma süresi dolmadan pencere kapanırsa kullanıcı "Sil"e basmıştı —
  // istek yine gitsin (keepalive).
  window.addEventListener('pagehide', function () { kesinlestir(true); });

  window.gecmisTemizle = {
    iste: iste,
    geriAl: geriAl,
    _kesinlestir: kesinlestir,
    GERI_AL_MS: GERI_AL_MS
  };
})();
