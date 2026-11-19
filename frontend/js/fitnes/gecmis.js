/* ═══ Fitnes GEÇMİŞ — son 20 hafta ısı haritası + ay takvimi + gün ayrıntısı ═══
 * Veri: GET /workouts/ozet?bas=&bit= (≤ 62 gün → 20 hafta 3 parçada) · GET /workouts?date= (gün ayrıntısı).
 * Bölme görünür olunca kendiliğinden çizilir (sınıf gözlemcisi); FitnesGecmis.tazele() yeniden çeker.
 */
(function () {
  "use strict";
  const HAFTA = 20, PARCA = 62;
  const g = { kap: null, ozet: new Map(), yuklu: false, yukleniyor: null, ay: null, secili: null, istek: 0, aralik: null };
  const iki = n => String(n).padStart(2, "0");
  const ymd = d => `${d.getFullYear()}-${iki(d.getMonth() + 1)}-${iki(d.getDate())}`;
  const coz = s => { const [y, m, d] = s.split("-").map(Number); return new Date(y, m - 1, d); };
  const ekle = (d, n) => new Date(d.getFullYear(), d.getMonth(), d.getDate() + n);
  const pzt = d => ekle(d, -((d.getDay() + 6) % 7));
  const bugun = () => coz(fsTodayStr());
  const ayAd = (d, uz) => d.toLocaleDateString(fYerel(), { month: uz ? "long" : "short" });
  const gunKisa = i => new Date(2024, 0, 1 + i).toLocaleDateString(fYerel(), { weekday: "short" });   // 2024-01-01 pazartesi
  const yapildi = x => !!x && (x.yapilan || 0) > 0;

  async function ozetCek(bas, bit) {
    const isler = [];
    for (let p = bas; p <= bit; p = ekle(p, PARCA)) {
      const son = ekle(p, PARCA - 1) < bit ? ekle(p, PARCA - 1) : bit;
      isler.push(fsGet(`/workouts/ozet?bas=${ymd(p)}&bit=${ymd(son)}`));
    }
    const sonuc = await Promise.all(isler);
    sonuc.forEach(l => (Array.isArray(l) ? l : []).forEach(x => g.ozet.set(x.tarih, x)));
    return sonuc.every(Boolean);
  }
  async function yukle() {
    const b = bugun(), bas = pzt(ekle(b, -7 * (HAFTA - 1)));
    g.aralik = { bas, bit: b };
    g.ozet.clear();
    const tamam = await ozetCek(bas, b);
    g.yuklu = true;
    return tamam;
  }
  function dortSayi() {
    const b = bugun(), bas = g.aralik.bas, buPzt = pzt(b), hafta = new Array(HAFTA).fill(0);
    let gun = 0, rekor = 0;
    g.ozet.forEach((x, t) => {
      const d = coz(t);
      if (d < bas || d > b) return;
      if (yapildi(x)) { gun++; hafta[Math.floor((d - bas) / 864e5 / 7)]++; }
      rekor += x.pr || 0;
    });
    const bitmis = Math.round((buPzt - bas) / 864e5 / 7);
    const kacan = hafta.slice(0, bitmis).filter(n => n === 0).length;
    let seri = 0, i = hafta[bitmis] > 0 ? bitmis : bitmis - 1;   // bu hafta boşsa geçen haftadan say
    while (i >= 0 && hafta[i] > 0) { seri++; i--; }
    return { gun, seri, kacan, rekor };
  }
  // Kademe 1-4 = günün tonajının aralıktaki sırası (çeyreklik); "en çoğa oran" haritayı tek renk yapıyordu.
  function kademeler() {
    const v = x => +x.tonaj || +x.yapilan || 0;
    const d = [...g.ozet.values()].filter(yapildi).map(v).sort((a, b) => a - b);
    const esik = [0.25, 0.5, 0.75].map(q => d[Math.min(d.length - 1, Math.floor(q * d.length))]);
    return x => (!yapildi(x) ? 0 : 1 + esik.filter(e => v(x) > e).length);
  }
  function yay(cx, cy, r, a0, a1) {
    const k = a => [cx + r * Math.cos((a - 90) * Math.PI / 180), cy + r * Math.sin((a - 90) * Math.PI / 180)];
    const [x0, y0] = k(a0), [x1, y1] = k(a1);
    return `M${x0.toFixed(2)} ${y0.toFixed(2)}A${r} ${r} 0 ${a1 - a0 > 180 ? 1 : 0} 1 ${x1.toFixed(2)} ${y1.toFixed(2)}`;
  }

  function iskelet() {
    g.kap.innerHTML = `<div class="fg">
  <section class="fg-ana" aria-labelledby="fg-baslik">
    <span class="f-etiket">${fT("gec.ust", { n: HAFTA })}</span><h2 class="fg-baslik" id="fg-baslik">${fT("gec.baslik")}</h2>
    <div class="fg-dort" id="fg-dort"></div>
    <div class="fg-isi-kap"><div class="fg-isi-gun" aria-hidden="true">${[0, 1, 2, 3, 4, 5, 6].map(i => `<span>${i % 2 ? "" : gunKisa(i)}</span>`).join("")}</div><div class="fg-isi" id="fg-isi" role="img"></div></div>
    <div class="fg-isi-ay" aria-hidden="true"><span></span><div id="fg-aylar"></div></div>
    <div class="fg-lejant" aria-hidden="true">${fT("gec.az")} <i class="k0"></i><i class="k1"></i><i class="k2"></i><i class="k3"></i><i class="k4"></i> ${fT("gec.cok")} · <i class="rk"></i> ${fT("gec.rekor-k")} · <i class="bg"></i> ${fT("besl.bugun").toLowerCase()}</div>
    <div class="fg-ay-bas"><button type="button" class="fg-ok" id="fg-geri" aria-label="${fT("gec.onceki-ay")}">‹</button>
      <div class="fg-ortala" aria-live="polite"><h3 id="fg-ay-ad"></h3><span id="fg-yil"></span></div>
      <button type="button" class="fg-ok" id="fg-ileri" aria-label="${fT("gec.sonraki-ay")}">›</button></div>
    <div class="fg-takvim" id="fg-takvim" role="grid" aria-label="${fT("gec.takvim")}"></div>
    <div class="fg-anahtar" aria-hidden="true">
      <span><svg width="18" height="18" viewBox="0 0 18 18"><circle cx="9" cy="9" r="7" class="fg-h-dolu"/></svg>${fT("gec.yapildi")}</span>
      <span><svg width="18" height="18" viewBox="0 0 18 18"><circle cx="9" cy="9" r="7" class="fg-h-kalan"/><path d="${yay(9, 9, 7, 0, 230)}" class="fg-h-dolu"/></svg>${fT("gec.plan-kaldi")}</span>
      <span><svg width="18" height="18" viewBox="0 0 18 18"><circle cx="9" cy="9" r="8" class="fg-h-rekor"/><circle cx="9" cy="9" r="5.5" class="fg-h-dolu"/></svg>${fT("gec.rekor-gunu")}</span></div>
    <p class="fg-uyari" id="fg-uyari" hidden>${fT("gec.eksik")}</p>
  </section>
  <aside class="fg-yan" id="fg-yan" aria-label="${fT("gec.secili-gun")}" aria-live="polite"></aside></div>`;
    g.kap.querySelector("#fg-geri").addEventListener("click", () => ayGit(-1));
    g.kap.querySelector("#fg-ileri").addEventListener("click", () => ayGit(1));
    g.kap.querySelector("#fg-takvim").addEventListener("click", e => { const b = e.target.closest("button[data-tarih]"); if (b) gunSec(b.dataset.tarih); });
    g.kap.querySelector("#fg-yan").addEventListener("click", e => { const b = e.target.closest("button[data-gungir]"); if (b) odakGunAc(b.dataset.gungir); });
    g.kap.querySelector("#fg-isi").addEventListener("click", e => {
      const i = e.target.closest("i[data-tarih]");
      if (!i) return;
      const d = coz(i.dataset.tarih);
      g.ay = new Date(d.getFullYear(), d.getMonth(), 1);
      takvimCiz(); gunSec(i.dataset.tarih);
    });
  }
  function dortCiz() {
    const s = dortSayi();
    g.kap.querySelector("#fg-dort").innerHTML = [["antrenman", s.gun, "gun"], ["seri", s.seri, "hafta"], ["kacan", s.kacan, ""], ["rekor", s.rekor, ""]]
      .map(([k, n, b]) => `<div data-sayi="${k}"><span class="f-etiket">${fT("gec.s-" + k)}</span><span class="fg-n${k === "seri" ? " fg-mavi" : ""}">${fsSay(n)}${b ? `<small> ${fT("gec.b-" + b)}</small>` : ""}</span></div>`).join("");
  }
  function isiCiz() {
    const b = bugun(), bas = g.aralik.bas, bt = ymd(b), kademe = kademeler();
    let h = "", aylar = "", gunN = 0, oncekiAy = -1;
    for (let w = 0; w < HAFTA; w++) {
      const eski = w < HAFTA - 13 ? "eski" : "", ilk = ekle(bas, w * 7), ay = ekle(ilk, 6);
      aylar += `<span class="${eski}">${ay.getMonth() !== oncekiAy ? ayAd(ay) : ""}</span>`;
      oncekiAy = ay.getMonth();
      for (let d = 0; d < 7; d++) {
        const gun = ekle(ilk, d), t = ymd(gun);
        if (gun > b) { h += `<i class="gelecek ${eski}" aria-hidden="true"></i>`; continue; }
        const x = g.ozet.get(t), k = kademe(x);
        if (k) gunN++;
        const cls = [eski, t === bt ? "bugun" : "", x && x.pr ? "rekor" : ""].filter(Boolean).join(" ");
        h += `<i data-k="${k}" data-tarih="${t}" class="${cls}" title="${gun.getDate()} ${ayAd(gun, 1)}${k ? " · " + fT("gec.set-say", { n: x.yapilan }) : ""}"></i>`;
      }
    }
    const isi = g.kap.querySelector("#fg-isi");
    isi.innerHTML = h;
    isi.setAttribute("aria-label", fT("gec.isi-aria", { h: HAFTA, n: gunN }));
    g.kap.querySelector("#fg-aylar").innerHTML = aylar;
  }
  function takvimCiz() {
    const b = bugun(), bt = ymd(b), y = g.ay.getFullYear(), m = g.ay.getMonth();
    g.kap.querySelector("#fg-ay-ad").textContent = ayAd(g.ay, 1);
    g.kap.querySelector("#fg-yil").textContent = y;
    g.kap.querySelector("#fg-ileri").disabled = y === b.getFullYear() && m === b.getMonth();
    const gunSay = new Date(y, m + 1, 0).getDate(), bosluk = (new Date(y, m, 1).getDay() + 6) % 7;
    let h = [0, 1, 2, 3, 4, 5, 6].map(i => `<span class="fg-gb" role="columnheader">${gunKisa(i)}</span>`).join("");
    for (let i = 0; i < bosluk; i++) h += `<span class="fg-bos" aria-hidden="true"></span>`;
    for (let gn = 1; gn <= gunSay; gn++) {
      const gun = new Date(y, m, gn), t = ymd(gun), x = g.ozet.get(t), gelecek = gun > b;
      const o = x && x.set ? Math.min(1, (x.yapilan || 0) / x.set) : 0, rek = !!(x && x.pr), sec = t === g.secili, bug = t === bt;
      let svg = `<svg viewBox="0 0 40 40" aria-hidden="true">${rek ? `<circle cx="20" cy="20" r="19" class="fg-h-rekor"/>` : ""}<circle cx="20" cy="20" r="15.5" class="${gelecek ? "fg-h-gelecek" : o > 0 && o < 1 ? "fg-h-kalan" : "fg-h-taban"}"/>`;
      if (o >= 1) svg += `<circle cx="20" cy="20" r="15.5" class="fg-h-dolu"/>`;   // tam gün = çember (359,99°'lik yay çizilmiyordu)
      else if (o > 0) svg += `<path d="${yay(20, 20, 15.5, 0, 359.99 * o)}" class="fg-h-dolu"/>`;
      if (bug) svg += `<circle cx="20" cy="4.5" r="3.4" class="fg-h-bugun"/>`;
      const durum = o >= 1 ? ", " + fT("gec.yapildi") : o > 0 ? ", " + fT("gec.plan-kaldi") : "";
      h += `<button type="button" role="gridcell" data-tarih="${t}" class="${o > 0 ? "var" : ""}${sec ? " secili" : ""}" aria-pressed="${sec}"` +
        ` aria-label="${gn} ${ayAd(gun, 1)}${durum}${rek ? ", " + fT("gec.rekor-k") : ""}${bug ? ", " + fT("besl.bugun").toLowerCase() : ""}"${gelecek ? " disabled" : ""}>${svg}</svg><span>${gn}</span></button>`;
    }
    g.kap.querySelector("#fg-takvim").innerHTML = h;
  }
  async function ayGit(yon) {
    const yeni = new Date(g.ay.getFullYear(), g.ay.getMonth() + yon, 1);
    if (yeni > bugun()) return;
    g.ay = yeni;
    if (yeni < g.aralik.bas) g.kap.querySelector("#fg-uyari").hidden = await ozetCek(yeni, new Date(yeni.getFullYear(), yeni.getMonth() + 1, 0));
    takvimCiz();
  }
  async function gunSec(t) {
    if (!g.kap) return;
    g.secili = t;
    g.kap.querySelectorAll("#fg-takvim button[data-tarih]").forEach(b => { const s = b.dataset.tarih === t; b.classList.toggle("secili", s); b.setAttribute("aria-pressed", String(s)); });
    const yan = g.kap.querySelector("#fg-yan"), x = g.ozet.get(t), d = coz(t), no = ++g.istek;
    const bas = `<div class="fg-bas"><span class="f-etiket">${d.toLocaleDateString(fYerel(), { day: "numeric", month: "long", weekday: "long" })}</span></div>`;
    const gir = d <= bugun() ? `<button type="button" class="fg-gir" data-gungir="${t}">${x ? fT("gec.duzenle") : fT("gec.idman-gir")}</button>` : "";
    if (!x) { yan.innerHTML = `${bas}<h3 class="fg-gun-ad">${fT("gec.kayit-yok")}</h3><p class="fg-not">${fT("gec.kayit-yok-not")}</p>${gir}${ayOzeti()}`; return; }
    const sure = x.sure_sn ? Math.round(x.sure_sn / 60) : null;
    yan.innerHTML = `${bas}<h3 class="fg-gun-ad">${fsKac(x.ad || fT("ant.antrenman"))}</h3>
      <ul class="fg-cetvel">
        <li><span class="ad">${fT("gec.yapilan-set")}</span><span class="deger">${fsSay(x.yapilan)}<small>/ ${fsSay(x.set)}</small></span></li>
        <li><span class="ad">${fT("gec.tonaj")}</span><span class="deger">${fsSay(x.tonaj)}<small>kg</small></span></li>
        <li><span class="ad">${fT("ant.sure-k")}</span><span class="deger">${sure == null ? "—" : fsSay(sure) + `<small>${fT("gec.dk")}</small>`}</span></li>
        <li><span class="ad">${fT("gec.kazanilan")}</span><span class="deger fg-mavi">+${fsSay(x.xp)}<small>XP</small></span></li>
        ${x.pr ? `<li class="rekor"><span class="ad">${fT("gec.rekor")}</span><span class="deger">${fsSay(x.pr)}</span></li>` : ""}
      </ul><div class="fg-bas"><span class="f-etiket">${fT("gec.kayit")}</span></div>
      <ol class="fg-kayit" id="fg-kayit"><li class="fg-yukleniyor">${fT("gec.yukleniyor")}</li></ol>${gir}${ayOzeti()}`;
    const w = await fsGet(`/workouts?date=${t}`);
    if (no !== g.istek) return;   // bu arada başka gün seçildi
    const ol = yan.querySelector("#fg-kayit");
    if (!w) { ol.innerHTML = `<li class="fg-yukleniyor">${fT("gec.okunamadi")}</li>`; return; }
    ol.innerHTML = (w.exercises || []).map((e, i) => {
      const ss = e.sets || [], yp = ss.filter(fsYapildi), sureli = fsSureliMi(e.name);
      const olcu = s => (sureli ? +s.reps || 0 : (+s.weight || 0) * (+s.reps || 0));
      const en = yp.reduce((a, s) => (!a || olcu(s) > olcu(a) ? s : a), null);
      const ton = yp.reduce((a, s) => a + fsSetTonaj(e.name, s), 0), drop = yp.reduce((a, s) => a + fsDroplar(s).length, 0), kalan = ss.length - yp.length;
      const deger = !en ? "—" : sureli ? fsSureYaz(en.reps) : `${+en.weight ? fsSay(en.weight, en.weight % 1 ? 1 : 0) : fT("gec.va")}×${fsSay(en.reps)}`;
      const ozet = sureli ? fT("gec.toplam-sure", { s: fsSureYaz(yp.reduce((a, s) => a + (+s.reps || 0), 0)) }) : `${fsSay(ton)} kg${drop ? " · " + fT("ant.aria-drop", { n: drop }) : ""}`;
      const alt = kalan ? fT("gec.kalan-set", { y: yp.length, n: ss.length, k: kalan }) : `${fT("gec.set-say", { n: ss.length })} · ${ozet}`;
      return `<li${e.rekor ? ' class="rekor"' : ""}><span class="no">${iki(i + 1)}</span><span class="ad">${fsKac(e.name)}${e.rekor ? ` <small class="fg-rekor">${fT("gec.rekor-buyuk")}</small>` : ""}</span><span class="deger">${deger}</span><span class="setler">${alt}</span></li>`;
    }).join("") || `<li class="fg-yukleniyor">${fT("gec.hareket-yok")}</li>`;
  }
  function ayOzeti() {
    const y = g.ay.getFullYear(), m = g.ay.getMonth();
    const say = (yy, mm) => { let n = 0; g.ozet.forEach((x, t) => { const d = coz(t); if (d.getFullYear() === yy && d.getMonth() === mm && yapildi(x)) n++; }); return n; };
    const bu = say(y, m), once = new Date(y, m - 1, 1);
    const kapsar = g.aralik && once >= new Date(g.aralik.bas.getFullYear(), g.aralik.bas.getMonth() + 1, 1);
    let ek = "";
    if (kapsar) { const f = bu - say(once.getFullYear(), once.getMonth()); ek = " " + (f > 0 ? fT("gec.fazla", { n: f }) : f < 0 ? fT("gec.az-n", { n: -f }) : fT("gec.ayni")); }
    return `<p class="fg-yuki">${fT("gec.ay-ozet", { ay: ayAd(g.ay, 1), n: bu })}${ek}</p>`;
  }
  async function ac() {
    g.kap = document.getElementById("fstrip-pane-gecmis");
    if (!g.kap) return false;
    if (g.yukleniyor) return g.yukleniyor;
    if (g.yuklu && g.kap.querySelector(".fg")) return true;
    g.yukleniyor = (async () => {
      iskelet();
      const tamam = await yukle();
      const b = bugun();
      let son = null;
      g.ozet.forEach((x, t) => { if (yapildi(x) && (!son || t > son)) son = t; });
      g.secili = g.ozet.has(ymd(b)) ? ymd(b) : son || ymd(b);
      const s = coz(g.secili);
      g.ay = new Date(s.getFullYear(), s.getMonth(), 1);
      dortCiz(); isiCiz(); takvimCiz();
      g.kap.querySelector("#fg-uyari").hidden = tamam;
      await gunSec(g.secili);
      g.kap.dispatchEvent(new CustomEvent("fitnes:gecmis-hazir", { bubbles: true }));
      return true;
    })();
    try { return await g.yukleniyor; } finally { g.yukleniyor = null; }
  }
  async function tazele() { g.yuklu = false; return ac(); }
  function izle() {
    const p = document.getElementById("fstrip-pane-gecmis");
    if (!p) return;
    const bak = () => { if (p.classList.contains("fstrip-pane-active") && !g.yuklu && !g.yukleniyor) ac(); };
    new MutationObserver(bak).observe(p, { attributes: true, attributeFilter: ["class"] });
    bak();
  }
  if (document.readyState === "loading") document.addEventListener("DOMContentLoaded", izle); else izle();
  document.addEventListener("fitnes:antrenman-degisti", () => { g.yuklu = false; const p = document.getElementById("fstrip-pane-gecmis"); if (p && p.classList.contains("fstrip-pane-active")) ac(); });
  document.addEventListener("fitnes:dil", () => { if (g.yuklu) { g.yuklu = false; const p = document.getElementById("fstrip-pane-gecmis"); if (p && p.classList.contains("fstrip-pane-active")) ac(); } });
  window.FitnesGecmis = { ac, tazele, gunSec, ayGit, get durum() { return { secili: g.secili, ay: g.ay && ymd(g.ay), gun: g.ozet.size, yuklu: g.yuklu }; } };
})();
