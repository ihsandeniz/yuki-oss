/* ═══ Fitnes olay hareketleri — Web Animations API ile (dış kitaplık yok) ═══
 * Yalnız OLAY ANLARI: seviye, rekor, lig terfisi, beceri, evrim. Sıradan arayüz geçişi CSS'tedir.
 *
 * Kurallar:
 *  · prefers-reduced-motion HER ZAMAN kazanır: sahne son kareyi anında kurar, yalnız kart 120 ms'de belirir.
 *  · Kullanıcı ayarı (ayar.js → window.HareketAyar.etkin(an)): an açık/kapalı, hız çarpanı, eğri, "sade"
 *    yoğunluk (yer değiştirme/taşma/ışık yok). ayar.js yoksa varsayılan oynar.
 *  · Hız yalnız bu sahnenin animasyonlarına uygulanır (playbackRate); başka animasyon etkilenmez.
 *  · Her sahne Promise döner → {an, kapali, hiz, sure} (sure = planlanan ms, hız dahil).
 *
 * Sahne işaretlemesi (durum.js ve ayar.js önizlemesi bu sınıfları kurar; eksik öğe atlanır):
 *  seviye  .kd-tik · .kd-altin (çizgi) · .sv-eski/.sv-yeni · .xp-dolu · .xp-sayi · .xp-payda · .sv-isik · .bildirim
 *          data-xp-bas · data-xp-esik · data-xp-son · data-oran-bas · data-oran-son · data-payda-son
 *  rekor   .rk-kart · .rk-hat (çizgi) · .rk-sayi · .rk-fark · .bildirim   data-eski · data-yeni
 *  lig     .lg-eski · .lg-yeni (satır içi rozet svg) · .gl-dolu · .lg-ad · .bildirim   data-golge-oran
 *  beceri  .bc-dal (çizgi) · .bc-yeni > .bc-kesik + .bc-dolu + .bc-ad · .bildirim
 *  evrim   .bc-yeni .bc-dolu polygon · .bc-yeni .bc-ad · .bildirim   data-yildiz (hedef points, aynı nokta sayısı)
 *  .bildirim içindeki [data-satir] öğeleri sırayla belirir.
 */
(function () {
  "use strict";
  const SURE = { olay: 720, toren: 3200, kart: 360 };
  const EGRI = { cikis: "cubic-bezier(.16,1,.3,1)", giris: "cubic-bezier(.55,0,1,.45)", yerles: "cubic-bezier(.34,1.56,.64,1)" };
  const sistemAzalt = () => window.matchMedia("(prefers-reduced-motion: reduce)").matches;

  function etkin(an) {
    const H = window.HareketAyar;
    const e = H && typeof H.etkin === "function" ? H.etkin(an) : null;
    const v = { kapali: false, hiz: 1, sade: false, egri: null, ...(e || {}) };
    if (sistemAzalt()) v.kapali = true;
    if (!(v.hiz > 0)) v.hiz = 1;
    return v;
  }
  function T(e) {
    const cikis = e.egri || EGRI.cikis;
    return { ...SURE, cikis, giris: EGRI.giris, yerles: e.sade ? cikis : EGRI.yerles, kayma: e.sade ? 0 : 6, isik: !e.sade };
  }
  const sayi = (v, ond = 0) => v.toLocaleString(window.fYerel ? fYerel() : "tr-TR", { minimumFractionDigits: ond, maximumFractionDigits: ond });

  /* Küçük zaman çizelgesi: adımlar (başlangıç ms + Web Animation ya da sayaç) toplanır, sonra birlikte sürülür. */
  function cizelge() {
    const adimlar = [];
    let son = 0;
    const tl = {
      get sure() { return adimlar.reduce((m, a) => Math.max(m, a.bas + a.sure), 0); },
      get son() { return son; },
      // keyframes: Web Animations biçimi; el yoksa/boşsa atlanır
      ekle(el, kare, sure, bas, egri, ayrik = 0) {
        const liste = !el ? [] : el instanceof Element ? [el] : [...el];
        liste.forEach((x, i) => adimlar.push({ tur: "anim", el: x, kare, sure, bas: bas + i * ayrik, egri }));
        if (liste.length) son = Math.max(son, bas + sure + (liste.length - 1) * ayrik);
        return tl;
      },
      sayac(baslangic, bitis, sure, bas, yaz, egri) {
        adimlar.push({ tur: "sayac", baslangic, bitis, sure, bas, yaz, egri });
        son = Math.max(son, bas + sure);
        return tl;
      },
      cagir(bas, fn) { adimlar.push({ tur: "cagri", bas, sure: 0, fn }); return tl; },
      // bitişe atla (kapalı kip): her animasyonun son karesini uygula, sayaçları son değere yaz
      sonKare() {
        adimlar.sort((a, b) => a.bas - b.bas).forEach(a => {
          if (a.tur === "anim") { const k = a.kare[a.kare.length - 1]; for (const p in k) if (p !== "offset" && p !== "easing") a.el.style[p] = k[p]; }
          else if (a.tur === "sayac") a.yaz(a.bitis);
          else a.fn();
        });
      },
      oynat(hiz) {
        const vaatler = [];
        for (const a of adimlar) {
          if (a.tur === "anim") {
            const an = a.el.animate(a.kare, { duration: a.sure, delay: a.bas, easing: a.egri || "linear", fill: "both" });
            an.playbackRate = hiz;
            vaatler.push(an.finished.catch(() => {}));
          } else if (a.tur === "sayac") {
            vaatler.push(new Promise(bitti => {
              const t0 = performance.now() + a.bas / hiz, uz = a.sure / hiz;
              const adim = (s) => {
                const p = Math.max(0, Math.min(1, (s - t0) / uz)), q = 1 - Math.pow(1 - p, 3);
                if (s >= t0) a.yaz(a.baslangic + (a.bitis - a.baslangic) * q);
                if (p < 1) requestAnimationFrame(adim); else bitti();
              };
              requestAnimationFrame(adim);
            }));
          } else vaatler.push(new Promise(b => setTimeout(() => { a.fn(); b(); }, a.bas / hiz)));
        }
        return Promise.all(vaatler);
      },
    };
    return tl;
  }

  // SVG çizgisini "çiz": uzunluğu ölç, dasharray = uzunluk, offset uzunluk → 0
  function cizgiHazirla(el) {
    if (!el || typeof el.getTotalLength !== "function") return null;
    let L = 0;
    try { L = el.getTotalLength(); } catch { L = 0; }
    if (!L) L = 600;
    el.style.strokeDasharray = `${L}`;
    el.style.strokeDashoffset = `${L}`;
    return [{ strokeDashoffset: `${L}` }, { strokeDashoffset: "0" }];
  }

  function oynat(an, e, tl, kok) {
    const sure = e.kapali ? 0 : Math.round(tl.sure / e.hiz);
    const bilgi = { an, kapali: e.kapali, hiz: e.hiz, sure };
    if (e.kapali) {
      tl.sonKare();
      if (kok && kok.animate) kok.animate([{ opacity: 0 }, { opacity: 1 }], { duration: 120 });
      return Promise.resolve(bilgi);
    }
    return tl.oynat(e.hiz).then(() => bilgi);
  }

  function kartGir(tl, t, kart, bas) {
    if (!kart) return;
    tl.ekle(kart, [{ opacity: 0, transform: `translateY(${t.kayma}px)` }, { opacity: 1, transform: "none" }], t.kart, bas, t.cikis);
    tl.ekle(kart.querySelectorAll("[data-satir]"), [{ opacity: 0, transform: `translateY(${t.kayma / 2}px)` }, { opacity: 1, transform: "none" }],
      t.kart, bas + 80, t.cikis, 70);
  }

  /* 1 · SEVİYE: XP dolar, tikler yanar, eski sayı çıkar / yenisi girer, altın halka bir kez çizilir */
  function seviye(s) {
    const e = etkin("seviye"), t = T(e), tl = cizelge(), d = s.dataset;
    const tik = s.querySelectorAll(".kd-tik"), cubuk = s.querySelector(".xp-dolu"), isik = s.querySelector(".sv-isik");
    const xpYazi = s.querySelector(".xp-sayi"), yaz = v => { if (xpYazi) xpYazi.textContent = sayi(Math.round(v)); };
    const dolum = t.toren * 0.4, ciz = t.toren * 0.45;
    tl.ekle(cubuk, [{ transform: `scaleX(${+d.oranBas || 0})` }, { transform: "scaleX(1)" }], dolum, 0, t.cikis);
    tl.sayac(+d.xpBas || 0, +d.xpEsik || 0, dolum, 0, yaz);
    tl.ekle(tik, [{ opacity: 0.18 }, { opacity: 1 }], 160, 0, "linear", ciz / Math.max(1, tik.length));
    tl.ekle(s.querySelector(".sv-eski"), [{ transform: "translateY(0)", opacity: 1 }, { transform: "translateY(-100%)", opacity: 0 }], t.olay * 0.6, ciz, t.giris);
    tl.ekle(s.querySelector(".sv-yeni"), [{ transform: "translateY(100%)" }, { transform: "translateY(0)" }], t.olay, ciz + 60, t.yerles);
    const halka = s.querySelector(".kd-altin"), hk = cizgiHazirla(halka);
    if (hk) tl.ekle(halka, hk, t.toren * 0.55, ciz + 60, t.cikis);
    if (isik) {
      if (t.isik) tl.ekle(isik, [{ opacity: 0 }, { opacity: 1 }, { opacity: 1, offset: 0.7 }, { opacity: 0 }], t.olay * 3, ciz + 60, t.cikis);
      else isik.style.opacity = 0;
    }
    const ikinci = ciz + 260;
    tl.cagir(ikinci, () => { const p = s.querySelector(".xp-payda"); if (p && d.paydaSon) p.textContent = d.paydaSon; });
    tl.ekle(cubuk, [{ transform: "scaleX(0)" }, { transform: `scaleX(${+d.oranSon || 0})` }], t.olay, ikinci, t.cikis);
    tl.sayac(0, +d.xpSon || 0, t.olay, ikinci, yaz);
    kartGir(tl, t, s.querySelector(".bildirim"), ikinci + 120);
    return oynat("seviye", e, tl, s);
  }

  /* 2 · REKOR: altın dış hat çizilir, değer sayılır, fark çipi yerleşir */
  function rekor(s) {
    const e = etkin("rekor"), t = T(e), tl = cizelge();
    const yazi = s.querySelector(".rk-sayi");
    tl.ekle(s.querySelector(".rk-kart"), [{ opacity: 0, transform: `translateY(${t.kayma}px)` }, { opacity: 1, transform: "none" }], t.kart, 0, t.cikis);
    const hat = s.querySelector(".rk-hat"), hk = cizgiHazirla(hat);
    if (hk) tl.ekle(hat, hk, t.olay, 60, t.cikis);
    tl.sayac(+s.dataset.eski || 0, +s.dataset.yeni || 0, t.olay, 140, v => { if (yazi) yazi.textContent = sayi(v, 1); });
    tl.ekle(s.querySelector(".rk-fark"), [{ opacity: 0, transform: `scale(${t.isik ? 0.8 : 1})` }, { opacity: 1, transform: "scale(1)" }], t.kart, 140 + t.olay * 0.6, t.yerles);
    kartGir(tl, t, s.querySelector(".bildirim"), 240);
    return oynat("rekor", e, tl, s);
  }

  /* 3 · LİG: Gölge çubuğu dolar, eski rozet çekilir, yenisinin çizgileri çizilir, dolgular belirir */
  function lig(s) {
    const e = etkin("lig"), t = T(e), tl = cizelge();
    const yeni = s.querySelector(".lg-yeni");
    const sekil = yeni ? [...yeni.querySelectorAll("path,circle,polygon,line,rect")] : [];
    const cizgi = sekil.filter(el => getComputedStyle(el).fill === "none"), dolgu = sekil.filter(el => getComputedStyle(el).fill !== "none");
    tl.ekle(s.querySelector(".gl-dolu"), [{ transform: "scaleX(0)" }, { transform: `scaleX(${+s.dataset.golgeOran || 0})` }], t.olay, 0, t.cikis);
    tl.ekle(s.querySelector(".lg-eski"), [{ opacity: 1, transform: "scale(1)" }, { opacity: 0, transform: `scale(${t.isik ? 0.9 : 1})` }], t.olay * 0.7, t.olay * 0.8, t.giris);
    const yb = t.olay * 1.2;
    tl.ekle(yeni, [{ opacity: 0 }, { opacity: 1 }], 1, yb);
    cizgi.forEach((el, i) => { const k = cizgiHazirla(el); if (k) tl.ekle(el, k, t.toren * 0.6, yb + i * (t.toren * 0.3 / Math.max(1, cizgi.length)), t.cikis); });
    tl.ekle(dolgu, [{ opacity: 0 }, { opacity: 1 }], t.olay, yb + t.toren * 0.35, "linear");
    tl.ekle(s.querySelector(".lg-ad"), [{ opacity: 0, transform: `translateY(${t.kayma}px)` }, { opacity: 1, transform: "none" }], t.kart, yb + t.toren * 0.35, t.cikis);
    kartGir(tl, t, s.querySelector(".bildirim"), yb + t.toren * 0.35 + 160);
    return oynat("lig", e, tl, s);
  }

  /* 4 · BECERİ: dal çizgisi uzanır, kesik düğüm dolar */
  function beceri(s) {
    const e = etkin("beceri"), t = T(e), tl = cizelge();
    const dal = s.querySelector(".bc-dal"), dk = cizgiHazirla(dal), dugum = s.querySelector(".bc-yeni");
    if (dk) tl.ekle(dal, dk, t.olay, 0, t.cikis);
    if (dugum) {
      tl.ekle(dugum.querySelector(".bc-kesik"), [{ opacity: 1 }, { opacity: 0 }], t.kart, t.olay * 0.6, "linear");
      tl.ekle(dugum.querySelector(".bc-dolu"), [{ opacity: 0, transform: `scale(${t.isik ? 0.6 : 1})` }, { opacity: 1, transform: "scale(1)" }], t.olay, t.olay * 0.6, t.yerles);
      tl.ekle(dugum.querySelector(".bc-ad"), [{ opacity: 0.35 }, { opacity: 1 }], t.kart, t.olay * 0.6 + 80, t.cikis);
    }
    kartGir(tl, t, s.querySelector(".bildirim"), t.olay + 100);
    return oynat("beceri", e, tl, s);
  }

  /* 5 · EVRİM: ◆ → ★ (aynı nokta sayısı, points aradeğeri sayaçla) */
  function evrim(s) {
    const e = etkin("evrim"), t = T(e), tl = cizelge();
    const sekil = s.querySelector(".bc-yeni .bc-dolu polygon");
    if (sekil && s.dataset.yildiz) {
      const nok = v => String(v).trim().split(/[\s,]+/).map(Number);
      const a = nok(sekil.getAttribute("points")), b = nok(s.dataset.yildiz);
      if (a.length === b.length) tl.sayac(0, 1, t.toren * 0.5, 0, p => {
        const v = a.map((x, i) => x + (b[i] - x) * p);
        sekil.setAttribute("points", v.reduce((m, x, i) => m + (i % 2 ? "," : i ? " " : "") + x.toFixed(2), ""));
      });
    }
    tl.ekle(s.querySelector(".bc-yeni .bc-ad"), [{ opacity: 0 }, { opacity: 1 }], t.kart, t.olay * 0.5, t.cikis);
    kartGir(tl, t, s.querySelector(".bildirim.evrim") || s.querySelector(".bildirim"), t.olay * 0.5 + 100);
    return oynat("evrim", e, tl, s);
  }

  const kapaliKademe = () => { const H = window.HareketAyar; return !!(H && typeof H.etkinYogunluk === "function" && H.etkinYogunluk() === "kapali"); };

  function kapat(el) {
    if (!el) return Promise.resolve();
    if (sistemAzalt() || kapaliKademe() || !el.animate) { el.style.opacity = 0; return Promise.resolve(); }
    return el.animate([{ opacity: 1 }, { opacity: 0, transform: "translateY(-3px)" }], { duration: 200, easing: EGRI.giris, fill: "forwards" })
      .finished.catch(() => {});
  }

  const azalt = (an) => (an ? etkin(an).kapali : sistemAzalt());
  window.Hareket = { seviye, rekor, lig, beceri, evrim, kapat, azalt, etkin, ANLAR: ["seviye", "rekor", "lig", "beceri", "evrim"] };
})();
