/* ═══ Fitnes ⚙ AYARLAR — hareket ayarı (veri) + çekmece (HEDEFLER · BİLDİRİM · HAREKET) ═══
 * window.HareketAyar — ekransız veri katmanı; hareket.js her sahnede HareketAyar.etkin(an)'ı okur.
 *   Saklama: sunucu GET/PUT /api/fitness/ayar/hareket + localStorage önbelleği (açılır açılmaz uygulanır,
 *   çevrimdışında son değer kalır; başka cihazdaki değişiklik bir sonraki açılışta gelir).
 * window.FitnesAyar — çekmece. ac('hedefler'|'bildirim'|'hareket') o bölüme kayar.
 *   Hedef kaydı 'fitnes:hedef-degisti' yayar → beslenme ekranı tazelenir.
 * Hareket JSON: {surum:1, hiz, yogunluk:'tam'|'sade'|'kapali', anlar:{seviye|rekor|lig|beceri|evrim:{acik, hiz, egri}}}
 *   Etkin süre = taban / (genel hız × an hızı); sade ise ayrıca ÷0,6. prefers-reduced-motion her zaman kazanır.
 */
(function () {
  "use strict";
  const ANAHTAR = "yuki_fitnes_hareket_v1";
  const HIZ_MIN = 0.25, HIZ_MAX = 2, SADE = 0.6;
  const ANLAR = { seviye: 3200, rekor: 720, lig: 3200, beceri: 720, evrim: 1600 };   // taban ms (yalnız gösterim)
  const EGRILER = { yumusak: null, keskin: "cubic-bezier(.05,.9,.1,1)", yorunge: "cubic-bezier(.45,0,.15,1)", dogrusal: "linear" };
  const YOGUNLUK = ["tam", "sade", "kapali"];
  const sistemAzalt = () => window.matchMedia("(prefers-reduced-motion: reduce)").matches;

  function varsayilan() {
    const anlar = {};
    for (const k in ANLAR) anlar[k] = { acik: true, hiz: 1, egri: "yumusak" };
    return { surum: 1, hiz: 1, yogunluk: "tam", anlar };
  }
  const kirp = (v, y) => (typeof v === "number" && Number.isFinite(v) ? Math.round(Math.min(HIZ_MAX, Math.max(HIZ_MIN, v)) * 100) / 100 : y);
  function temizle(ham) {
    const v = varsayilan();
    if (!ham || typeof ham !== "object") return v;
    v.hiz = kirp(ham.hiz, 1);
    if (YOGUNLUK.includes(ham.yogunluk)) v.yogunluk = ham.yogunluk;
    for (const k in ANLAR) {
      const a = ham.anlar && ham.anlar[k];
      if (!a || typeof a !== "object") continue;
      v.anlar[k].acik = a.acik !== false;
      v.anlar[k].hiz = kirp(a.hiz, 1);
      if (Object.prototype.hasOwnProperty.call(EGRILER, a.egri)) v.anlar[k].egri = a.egri;
    }
    return v;
  }
  function onbellekOku() { try { return temizle(JSON.parse(localStorage.getItem(ANAHTAR) || "null")); } catch { return varsayilan(); } }
  function onbellekYaz(a) { try { localStorage.setItem(ANAHTAR, JSON.stringify(a)); return true; } catch { return false; } }
  const istek = async (y, yol, g) => { const r = await fsIstek(y, yol, g); return r.ok ? r.json : null; };

  let ayar = onbellekOku(), kaynak = "onbellek";
  const dinleyiciler = new Set();
  const duyur = () => dinleyiciler.forEach(f => { try { f(ayar, kaynak); } catch {} });
  let tazeleSoz = null;
  function sunucudan() {
    tazeleSoz = istek("GET", "/ayar/hareket").then(r => {
      if (r) { ayar = temizle(r); onbellekYaz(ayar); kaynak = "sunucu"; duyur(); }
      return ayar;
    });
    return tazeleSoz;
  }
  // Önbellek hemen, sunucu 400 ms sonra (kaydırıcı sürüklenirken her adımda PUT atılmasın)
  let zaman = null, bekleyen = null;
  function kaydet(yeni, sec) {
    ayar = temizle(yeni);
    const yerel = onbellekYaz(ayar);
    clearTimeout(zaman);
    const gonder = () => {
      const giden = ayar;
      bekleyen = istek("PUT", "/ayar/hareket", giden).then(r => {
        kaynak = r ? "sunucu" : "yerel";
        if (r && giden === ayar && JSON.stringify(temizle(r)) !== JSON.stringify(giden)) { ayar = temizle(r); onbellekYaz(ayar); }
        duyur();
        return !!r;
      });
      return bekleyen;
    };
    const p = sec && sec.hemen ? gonder() : new Promise(c => { zaman = setTimeout(() => gonder().then(c), 400); });
    bekleyen = p;
    return p.then(s => ({ yerel, sunucu: s }));
  }
  const etkinYogunluk = (a) => (sistemAzalt() ? "kapali" : (a || ayar).yogunluk);
  function etkin(an, a) {
    a = a || ayar;
    const ay = a.anlar[an] || { acik: true, hiz: 1, egri: "yumusak" }, y = etkinYogunluk(a);
    let hiz = a.hiz * ay.hiz;
    if (y === "sade") hiz /= SADE;
    return { kapali: y === "kapali" || !ay.acik, hiz, sade: y === "sade", egri: EGRILER[ay.egri] || null, yogunluk: y };
  }
  window.HareketAyar = {
    ANAHTAR, ANLAR, EGRILER, YOGUNLUK, HIZ_MIN, HIZ_MAX, SADE,
    get ayar() { return ayar; }, get kaynak() { return kaynak; },
    varsayilan, temizle, etkin, etkinYogunluk, sistemAzalt, sunucudan, kaydet,
    bekle: () => Promise.resolve(bekleyen), tazelendi: () => Promise.resolve(tazeleSoz),
    dinle: f => { dinleyiciler.add(f); return () => dinleyiciler.delete(f); },
  };
  sunucudan();

  /* ════════════ ÇEKMECE ════════════ */
  const SIRA = ["seviye", "rekor", "beceri", "lig", "evrim"];
  const ond = (v, n) => Number(v).toLocaleString(fYerel(), { minimumFractionDigits: n, maximumFractionDigits: n });
  let kok = null, onceOdak = null, kosu = 0, taslak = null, bildirim = null;
  const $ = s => kok.querySelector(s);

  function sablon() {
    return `<div class="fa-perde" data-kapat></div>
<section class="fa-panel" role="dialog" aria-modal="true" aria-labelledby="fa-baslik" tabindex="-1">
  <header class="fa-ust"><div><span class="f-etiket">${fT("ayar.ust")}</span><h2 id="fa-baslik">${fT("ayar.baslik")}</h2></div>
    <button type="button" class="fa-kapat" data-kapat>${fT("ortak.kapat")}</button></header>
  <nav class="fa-gezinti" aria-label="${fT("ayar.bolumler")}">
    <a href="#fa-hedefler" data-bolum="hedefler">${fT("ayar.hedefler")}</a><a href="#fa-bildirim" data-bolum="bildirim">${fT("ayar.bildirim")}</a><a href="#fa-hareket" data-bolum="hareket">${fT("ayar.hareket")}</a></nav>
  <div class="fa-govde">
    <section id="fa-hedefler" class="fa-bolum"><h3 class="f-etiket">${fT("ayar.hedefler")}</h3><p class="fa-not">${fT("ayar.hedef-not")}</p>
      <div class="fa-izgara">
        ${[["cal", "kalori", "kcal", 9999], ["prot", "protein", "g", 999], ["carb", "karb", "g", 999], ["fat", "yag", "g", 999]].map(([id, ad, b, m]) =>
          `<label class="fa-kuyu"><span>${fT("ayar." + ad)}</span><input id="fa-${id}" type="number" inputmode="numeric" min="0" max="${m}"><small>${b}</small></label>`).join("")}
      </div>
      <div class="fa-satir-d"><button type="button" class="fa-d ana" id="fa-hedef-kaydet">${fT("ayar.hedef-kaydet")}</button><p class="fa-durum" id="fa-hedef-durum" role="status"></p></div></section>
    <section id="fa-bildirim" class="fa-bolum"><h3 class="f-etiket">${fT("ayar.bildirim")}</h3>
      <div class="fa-cetvel">
        <div class="fa-cs"><span><b>${fT("ayar.push")}</b><small>${fT("ayar.push-not")}</small></span><button type="button" class="fa-anahtar" role="switch" id="fa-push" aria-label="${fT("ayar.push")}"></button></div>
        <div class="fa-cs"><span><b>${fT("ayar.hatirlat")}</b><small>${fT("ayar.hatirlat-not")}</small></span><button type="button" class="fa-anahtar" role="switch" id="fa-hatirlat" aria-label="${fT("ayar.hatirlat")}"></button></div>
        <div class="fa-cs"><span><b>${fT("ayar.sessiz")}</b><small>${fT("ayar.sessiz-not")}</small></span>
          <span class="fa-saat"><input id="fa-sessiz-bas" type="number" min="0" max="23" aria-label="${fT("ayar.sessiz-bas")}"><i>–</i><input id="fa-sessiz-bit" type="number" min="0" max="23" aria-label="${fT("ayar.sessiz-bit")}"></span></div>
      </div><p class="fa-durum" id="fa-bildirim-durum" role="status"></p></section>
    <section id="fa-hareket" class="fa-bolum"><h3 class="f-etiket">${fT("ayar.hareket")}</h3>
      <div class="fa-hareket-duzen">
        <div class="fa-onizle"><div class="fa-onizle-bas"><b id="fa-sahne-ad">${fT("an.seviye")}</b><p class="fa-olcum" id="fa-olcum" aria-live="polite">${fT("ayar.onizle-bekle")}</p></div><div class="fa-alan" id="fa-alan"></div></div>
        <div class="fa-kontrol">
          <p class="fa-not">${fT("ayar.hareket-not")}</p>
          <p class="fa-uyari" id="fa-azalt" hidden>${fT("ayar.azalt-uyari")}</p>
          <div class="fa-satir"><div class="fa-satir-bas"><label for="fa-hiz">${fT("ayar.genel-hiz")}</label><output id="fa-hiz-deger" for="fa-hiz"></output></div>
            <input type="range" id="fa-hiz" min="${HIZ_MIN}" max="${HIZ_MAX}" step="0.05"></div>
          <div class="fa-satir"><span id="fa-yog-etiket">${fT("ayar.yogunluk")}</span><div class="fa-hap-grup" role="group" aria-labelledby="fa-yog-etiket" id="fa-yogunluk">
            ${YOGUNLUK.map(k => `<button type="button" class="fa-hap" data-yog="${k}">${fT("yog." + k)}</button>`).join("")}</div><p class="fa-not" id="fa-yog-not"></p></div>
          <ol class="fa-anlar" id="fa-anlar">${SIRA.map(anSatiri).join("")}</ol>
          <div class="fa-satir-d"><button type="button" class="fa-d ana" id="fa-sirayla">${fT("ayar.sirayla")}</button><button type="button" class="fa-d" id="fa-varsayilan">${fT("ayar.varsayilan")}</button></div>
          <p class="fa-durum" id="fa-hareket-durum" role="status"></p>
        </div></div></section>
  </div></section>`;
  }
  function anSatiri(an) {
    const ad = fT("an." + an);
    return `<li class="fa-an" data-an="${an}">
      <button type="button" class="fa-anahtar" role="switch" aria-label="${fT("ayar.an-acik", { ad })}"></button>
      <span class="fa-an-ad"><b>${ad}</b><small>${fT("ayar.taban", { ms: ANLAR[an] })}</small></span>
      <button type="button" class="fa-d kucuk" data-onizle="${an}">${fT("ayar.onizle")}</button>
      <label class="fa-an-hiz"><span>${fT("ayar.hiz")}</span><input type="range" min="${HIZ_MIN}" max="${HIZ_MAX}" step="0.05" aria-label="${fT("ayar.an-hiz", { ad })}"><output></output></label>
      <label class="fa-an-egri"><span>${fT("ayar.egri")}</span><select aria-label="${fT("ayar.an-egri", { ad })}">${Object.keys(EGRILER).map(k => `<option value="${k}">${fT("egri." + k)}</option>`).join("")}</select></label></li>`;
  }

  async function hedefYukle() {
    const c = await istek("GET", "/config"), d = c || { calGoal: 2000, proteinGoal: 150, carbGoal: 200, fatGoal: 65 };
    $("#fa-cal").value = d.calGoal; $("#fa-prot").value = d.proteinGoal; $("#fa-carb").value = d.carbGoal; $("#fa-fat").value = d.fatGoal;
    $("#fa-hedef-durum").textContent = c ? "" : fT("ayar.sunucu-yok-varsayilan");
  }
  async function hedefKaydet() {
    const v = id => parseInt($(id).value, 10) || 0;
    const r = await istek("PUT", "/config", { calGoal: v("#fa-cal") || 2000, proteinGoal: v("#fa-prot") || 150, carbGoal: v("#fa-carb") || 200, fatGoal: v("#fa-fat") || 65 });
    $("#fa-hedef-durum").textContent = r ? fT("ayar.hedef-kaydedildi") : fT("ayar.kaydedilemedi");
    if (r) document.dispatchEvent(new CustomEvent("fitnes:hedef-degisti", { detail: r }));
  }
  function bildirimYaz() {
    kok.querySelectorAll("#fa-bildirim .fa-anahtar, #fa-bildirim input").forEach(el => { el.disabled = !bildirim; });
    const b = bildirim || { push: true, sessiz: [23, 8], hatirlatma: true };
    $("#fa-push").setAttribute("aria-checked", String(b.push !== false));
    $("#fa-hatirlat").setAttribute("aria-checked", String(b.hatirlatma !== false));
    $("#fa-sessiz-bas").value = b.sessiz[0]; $("#fa-sessiz-bit").value = b.sessiz[1];
  }
  async function bildirimYukle() {
    bildirim = await istek("GET", "/bildirim-ayar");
    bildirimYaz();
    $("#fa-bildirim-durum").textContent = bildirim ? "" : fT("ayar.bildirim-okunamadi");
  }
  async function bildirimKaydet() {
    const saat = (id, y) => { const n = parseInt($(id).value, 10); return Number.isFinite(n) ? Math.min(23, Math.max(0, n)) : y; };
    const yeni = { push: $("#fa-push").getAttribute("aria-checked") === "true", hatirlatma: $("#fa-hatirlat").getAttribute("aria-checked") === "true",
      sessiz: [saat("#fa-sessiz-bas", 23), saat("#fa-sessiz-bit", 8)] };
    const r = await istek("PUT", "/bildirim-ayar", yeni);
    if (r) bildirim = r;
    bildirimYaz();
    $("#fa-bildirim-durum").textContent = r ? fT("ayar.kaydedildi") : fT("ayar.kaydedilemedi");
  }

  function doluluk(inp) { inp.style.setProperty("--dolu", ((+inp.value - +inp.min) / (+inp.max - +inp.min) * 100) + "%"); }
  function hareketKaydet() {
    const d = $("#fa-hareket-durum");
    d.textContent = fT("ayar.kaydediliyor");
    window.HareketAyar.kaydet(taslak).then(s => { if (kok) d.textContent = s.sunucu ? fT("ayar.kaydedildi-her") : s.yerel ? fT("ayar.kaydedildi-yerel") : fT("ayar.kayit-izin-yok"); });
  }
  function hareketYaz() {
    const h = $("#fa-hiz");
    h.value = taslak.hiz; $("#fa-hiz-deger").textContent = "×" + ond(taslak.hiz, 2); doluluk(h);
    const az = sistemAzalt(), y = etkinYogunluk(taslak);
    kok.querySelectorAll("#fa-yogunluk .fa-hap").forEach(b => { b.setAttribute("aria-pressed", String(b.dataset.yog === y)); b.disabled = az; });
    $("#fa-yog-not").textContent = fT("yog-not." + y);
    $("#fa-azalt").hidden = !az;
    kok.querySelectorAll(".fa-an").forEach(li => {
      const a = taslak.anlar[li.dataset.an], kapali = !a.acik || y === "kapali";
      const r = li.querySelector("input"), sel = li.querySelector("select");
      li.querySelector(".fa-anahtar").setAttribute("aria-checked", String(a.acik));
      li.classList.toggle("kapali", kapali);
      r.value = a.hiz; r.disabled = kapali; doluluk(r); li.querySelector("output").textContent = "×" + ond(a.hiz, 2);
      sel.value = a.egri; sel.disabled = kapali;
    });
  }

  /* Önizleme sahneleri — gerçek kart işaretlemesinin küçük kopyası; panelin TASLAK ayarıyla oynar */
  const KART = (ust, satir) => `<div class="bildirim" role="status"><small data-satir>${ust}</small>${satir.map(s => `<p data-satir>${s}</p>`).join("")}</div>`;
  function sahneKur(an) {
    const s = document.createElement("div");
    s.className = "fa-sahne " + an;
    if (an === "seviye") {
      Object.assign(s.dataset, { xpBas: 210, xpEsik: 238, xpSon: 52, oranBas: ".88", oranSon: ".13", paydaSon: 395 });
      s.innerHTML = `<div class="fa-sv">${typeof fitKadranSvg === "function" ? fitKadranSvg(0.13, 120) : ""}<div class="fk-sv-no"><span class="sv-eski">2</span><span class="sv-yeni">3</span></div><div class="sv-isik"></div></div>
        <div class="xp"><span><b class="xp-sayi">210</b> / <span class="xp-payda">238</span> XP</span><div class="xp-kanal"><div class="xp-dolu"></div></div></div>
        ${KART(fT("kart.onek", { tur: fT("tur.SEVIYE") }), [fT("onizle.seviye")])}`;
    } else if (an === "rekor") {
      Object.assign(s.dataset, { eski: "111", yeni: "116.7" });
      s.innerHTML = `<div class="rk-kart"><svg viewBox="0 0 300 120" aria-hidden="true"><rect class="rk-hat" x="1" y="1" width="298" height="118" rx="10"/></svg>
        <div class="rk-ic"><span class="rk-sayi">111,0</span> <small>kg · e1RM</small> <span class="rk-fark">+5,7 kg</span></div></div>
        ${KART(fT("kart.onek", { tur: fT("tur.REKOR") }), [fT("onizle.rekor")])}`;
    } else if (an === "lig") {
      s.dataset.golgeOran = ".83";
      s.innerHTML = `<div class="gl-kanal"><div class="gl-dolu"></div></div><div class="lg-sahne"><div class="lg-eski"></div><div class="lg-yeni"></div></div>
        <div class="lg-ad">${fitLigAd("C")} → ${fitLigAd("B")}</div>${KART(fT("kart.onek", { tur: fT("tur.LIG") }), [fT("onizle.lig", { eski: fitLigAd("C"), yeni: fitLigAd("B") })])}`;
      if (typeof fitRozet === "function") { s.querySelector(".lg-eski").innerHTML = fitRozet("C", 72); s.querySelector(".lg-yeni").innerHTML = fitRozet("B", 72); }
    } else {
      s.dataset.yildiz = FIT_YILDIZ;
      s.innerHTML = `<svg class="fa-bc" viewBox="0 0 220 60" aria-hidden="true"><path class="bc-dal" d="M8 30H60"/>
        <g class="bc-yeni"><polygon class="bc-kesik" points="${FIT_ELMAS}" transform="translate(60 10)"/><g class="bc-dolu" transform="translate(60 10)"><polygon points="${FIT_ELMAS}"/></g>
        <text class="bc-ad" x="108" y="35">${an === "evrim" ? fT("beceri-ad.celik_irade") : fT("beceri-ad.demir_tutus")}</text></g></svg>
        ${KART(fT("kart.onek", { tur: fT("tur." + an.toUpperCase()) }), [fT("onizle." + an)])}`;
    }
    return s;
  }
  async function oynat(anlar) {
    const H = window.Hareket;
    if (!H || !kok) return [];
    const benim = ++kosu, sonuc = [];
    for (let i = 0; i < anlar.length; i++) {
      if (benim !== kosu || !kok) return sonuc;
      const an = anlar[i], s = sahneKur(an), e = etkin(an, taslak);
      kok.querySelectorAll(".fa-an").forEach(li => li.setAttribute("aria-current", String(li.dataset.an === an)));
      $("#fa-sahne-ad").textContent = fT("an." + an);
      $("#fa-alan").replaceChildren(s);
      $("#fa-olcum").textContent = e.kapali ? fT("ayar.olcum-kapali") : fT("ayar.olcum-oynuyor", { hiz: ond(e.hiz, 2) });
      const asil = window.HareketAyar.etkin;
      window.HareketAyar.etkin = a => etkin(a, taslak);
      const t0 = performance.now();
      let bilgi;
      try { const p = H[an](s); window.HareketAyar.etkin = asil; bilgi = await p; } finally { window.HareketAyar.etkin = asil; }
      sonuc.push({ ...bilgi, gecen: Math.round(performance.now() - t0) });
      if (benim !== kosu || !kok) return sonuc;
      $("#fa-olcum").textContent = bilgi.kapali ? fT("ayar.olcum-kapali") : fT("ayar.olcum-toplam", { sn: ond((performance.now() - t0) / 1000, 2) });
      if (i < anlar.length - 1) await new Promise(r => setTimeout(r, 1500));
    }
    return sonuc;
  }

  function kur() {
    kok = document.createElement("div");
    kok.id = "fa-cekmece";
    kok.innerHTML = sablon();
    document.body.appendChild(kok);
    kok.addEventListener("click", ev => {
      const t = ev.target;
      if (t.closest("[data-kapat]")) return kapat();
      const a = t.closest(".fa-gezinti a");
      if (a) { ev.preventDefault(); return bolumeGit(a.dataset.bolum); }
      if (t.closest("#fa-hedef-kaydet")) return hedefKaydet();
      const sw = t.closest("#fa-push, #fa-hatirlat");
      if (sw) { sw.setAttribute("aria-checked", String(sw.getAttribute("aria-checked") !== "true")); return bildirimKaydet(); }
      const yog = t.closest("[data-yog]");
      if (yog) { taslak.yogunluk = yog.dataset.yog; hareketYaz(); return hareketKaydet(); }
      const on = t.closest("[data-onizle]");
      if (on) return oynat([on.dataset.onizle]);
      const anSw = t.closest(".fa-an .fa-anahtar");
      if (anSw) { const a = taslak.anlar[anSw.closest(".fa-an").dataset.an]; a.acik = !a.acik; hareketYaz(); return hareketKaydet(); }
      if (t.closest("#fa-sirayla")) return oynat(SIRA);
      if (t.closest("#fa-varsayilan")) { taslak = varsayilan(); hareketYaz(); return hareketKaydet(); }
    });
    kok.addEventListener("input", ev => {
      const t = ev.target;
      if (t.id === "fa-hiz") { taslak.hiz = +t.value; hareketYaz(); return hareketKaydet(); }
      const li = t.closest(".fa-an");
      if (li && t.type === "range") { taslak.anlar[li.dataset.an].hiz = +t.value; hareketYaz(); hareketKaydet(); }
    });
    kok.addEventListener("change", ev => {
      const t = ev.target;
      if (t.id === "fa-sessiz-bas" || t.id === "fa-sessiz-bit") return bildirimKaydet();
      const li = t.closest(".fa-an");
      if (li && t.tagName === "SELECT") { taslak.anlar[li.dataset.an].egri = t.value; hareketKaydet(); }
    });
    kok.addEventListener("keydown", ev => { if (ev.key === "Escape") kapat(); });
    window.matchMedia("(prefers-reduced-motion: reduce)").addEventListener("change", () => { if (kok && taslak) hareketYaz(); });
  }
  function bolumeGit(ad) {
    const b = kok && kok.querySelector("#fa-" + ad);
    if (!b) return;
    kok.querySelectorAll(".fa-gezinti a").forEach(a => a.toggleAttribute("aria-current", a.dataset.bolum === ad));
    b.scrollIntoView({ block: "start", behavior: sistemAzalt() ? "auto" : "smooth" });
  }
  function ac(bolum) {
    if (!kok) kur();
    onceOdak = document.activeElement;
    taslak = temizle(window.HareketAyar.ayar);
    hareketYaz();
    kok.classList.add("acik");
    document.documentElement.classList.add("fa-acik");
    hedefYukle(); bildirimYukle();
    $(".fa-panel").focus({ preventScroll: true });
    if (bolum) bolumeGit(bolum);
  }
  function kapat() {
    if (!kok) return;
    kosu++;
    kok.classList.remove("acik");
    document.documentElement.classList.remove("fa-acik");
    if (onceOdak && onceOdak.focus) onceOdak.focus({ preventScroll: true });
  }
  // Dil değişince çekmece yeniden kurulur (açıksa açık kalır)
  document.addEventListener("fitnes:dil", () => { if (!kok) return; const acik = kok.classList.contains("acik"); kok.remove(); kok = null; if (acik) ac(); });
  window.HareketAyar.dinle(() => { if (kok && kok.classList.contains("acik")) { taslak = temizle(window.HareketAyar.ayar); hareketYaz(); } });
  window.FitnesAyar = { ac, kapat, oynat, get acik() { return !!(kok && kok.classList.contains("acik")); } };
})();
