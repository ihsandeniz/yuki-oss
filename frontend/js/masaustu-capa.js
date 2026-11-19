// ══════════════════════════════════════════════════════════════════════════
//  MASAÜSTÜ YUKİ ÇAPASI
//
//  Masaüstü Yuki PANEL'in (#hr-side) üst kenarına oturur, giriş hapının (#giris-hap)
//  üstüne uzanır. Masaüstü süreci bu öğelerin YERİNİ bilemez: Electron Wayland'de kendi
//  ekran konumunu bilmez (masaustu/README § Neden Electron değil). Burası CSS px kutuları
//  + görünüm boyunu `/ws/realtime`'a yollar; ekran konumunu masaüstü, pencere konumu kaynağı varsa (masaustu/etkilesim.py), ekler
//  (masaustu/etkilesim.py). Backend süzüp yayınlar (websocket.py masaustu_capa_suz).
//
//  Yalnız masaüstü uygulamasında (Electron, window.yukiApp): telefon/tarayıcıdan yollanmaz.
//  Değişince (≥2 px) hemen, değişmese de 5 sn'de bir (masaüstü 12 sn'den eski çapayı yok sayar);
//  sayfa gizliyken yollanmaz. Öğe görünmüyorsa (başka sekme, daraltılmış giriş) o kutu null.
//  `core.js`'in üst düzey `socket`'i kullanılır; core.js'e dokunulmadı.
//
//  `paneller`: açık pencere-panellerin (AKIŞ, HAFIZA… `.hr-widget`) kutuları; Yuki
//  bunlara da oturur. Gizli/mobil-gizli olanlar ve görünmeyenler gitmez; en çok 12. Eski backend bu alanı süzüp
//  atar → yalnız PANEL'e oturulur (zarar yok).
//
//  🔴 Yankı kapısı: bu tipi tanımayan (eski) backend iletiyi boş kullanıcı turu sayar → LISTENING'e geçip IDLE'a
//  zorlar (websocket.py § Metin girişi). 5 sn'de bir yollansa Yuki konuşurken durumu bozardı. Bu yüzden her yeni
//  sokette ÖNCE tek yoklama gider; backend süzüp geri yayınlarsa (yankı) yayın sürer, 4 sn'de yankı yoksa o soket
//  boyunca susar. Backend yeniden başlayınca soket yenilenir → kendiliğinden yeniden yoklar.
// ══════════════════════════════════════════════════════════════════════════
(function () {
  'use strict';
  const ARALIK_MS = 1000, TAZELE_MS = 5000, ESIK = 2, YANKI_MS = 4000;

  function kutu(sec) {
    return kutuEl(document.querySelector(sec));
  }

  function kutuEl(e) {
    if (!e) return null;
    const s = getComputedStyle(e);
    if (s.display === 'none' || s.visibility === 'hidden' || +s.opacity === 0) return null;
    const r = e.getBoundingClientRect();
    if (r.width < 24 || r.height < 8 || r.bottom <= 0 || r.top >= innerHeight || r.right <= 0 || r.left >= innerWidth) return null;
    return [Math.round(r.left), Math.round(r.top), Math.round(r.width), Math.round(r.height)];
  }

  const PANEL_EN_COK = 12;
  function olc() {
    const paneller = [];
    for (const e of document.querySelectorAll('.hr-widget:not(.hr-w-hidden):not(.hr-w-mobil-gizli)')) {
      const k = kutuEl(e);
      if (k) paneller.push(k);
      if (paneller.length >= PANEL_EN_COK) break;
    }
    return { type: 'masaustu_capa', vw: innerWidth, vh: innerHeight,
             panel: kutu('#hr-side'), cubuk: kutu('#giris-hap'), paneller: paneller };
  }

  function farkli(a, b) {
    if (!a || !b) return true;
    if (a.vw !== b.vw || a.vh !== b.vh) return true;
    const kutuFark = (x, y) => (!x !== !y) || (x && x.some((v, i) => Math.abs(v - y[i]) >= ESIK));
    for (const k of ['panel', 'cubuk']) if (kutuFark(a[k], b[k])) return true;
    const pa = a.paneller || [], pb = b.paneller || [];
    return pa.length !== pb.length || pa.some((x, i) => kutuFark(x, pb[i]));
  }

  let son = null, sonT = 0;
  function tur(simdi, gonder) {
    if (document.hidden) return null;
    const m = olc();
    if (!farkli(m, son) && simdi - sonT < TAZELE_MS) return null;
    if (!gonder(m)) return null;
    son = m; sonT = simdi;
    return m;
  }

  // Yankı kapısı (yukarıda): soket başına durum — null: yoklanmadı · 'bekle' · true: destekli · false: sus
  const kapi = { soket: null, durum: null, t: 0 };
  function soketGonder(m, simdi, s) {
    if (!s || s.readyState !== 1) return false;
    if (kapi.soket !== s) {                      // yeni soket (ilk bağlantı ya da yeniden bağlanma): yeniden yokla
      kapi.soket = s; kapi.durum = null;
      try { s.addEventListener('message', e => {
        if (kapi.soket === s && typeof e.data === 'string' && e.data.indexOf('"masaustu_capa"') >= 0) kapi.durum = true;
      }); } catch (_) {}
    }
    if (kapi.durum === false) return false;
    if (kapi.durum === 'bekle') {
      if (simdi - kapi.t < YANKI_MS) return false;
      kapi.durum = false; return false;           // eski backend: bu soket boyunca sus
    }
    try { s.send(JSON.stringify(m)); } catch (_) { return false; }
    if (kapi.durum === null) { kapi.durum = 'bekle'; kapi.t = simdi; }
    return true;
  }
  // core.js'in `let socket`'i sayfa genelinde (klasik betik, aynı global sözcük alanı)
  const aktifSoket = () => (typeof socket !== 'undefined') ? socket : null;

  window.MasaustuCapa = { olc: olc, farkli: farkli, tur: tur, soketGonder: soketGonder, kapi: kapi };
  if (window.yukiApp) setInterval(() => { const t = Date.now(); tur(t, m => soketGonder(m, t, aktifSoket())); }, ARALIK_MS);
})();
