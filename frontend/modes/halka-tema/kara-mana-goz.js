/* HALKA teması — KARA MANA · GÖZ (kara-mana-goz) · ürün portu 2026-10-04
   Kaynak: kişisel AliceAi `frontend/modes/halka-tema/kara-mana-goz.js` (2026-10-03, geliştirici seçti).
   Kara deliğin fiziği (mercek, Hawking, foton halkası, ISCO, kutup jetleri, dinleme girdabı,
   gelgit) + düşünürken yarı açık tarayan / konuşurken tam açık altın göz; jetler göz bebeğinin
   dikey uzantısı (aynı ses zarfı). Göz açıkken YUKI adı küçülüp gözün altına iner.

   ÜRÜN FARKLARI (kişiselden):
     · RENK SABİT YOK. Kişiselde 50+ hex vardı; burada her renk kara-mana-goz.css'teki
       `--kg-*` değişkenlerinden gelir, onlar da ürün token'larından (--altin, --mor-ink,
       --bg, --ink-1) ve karakter renginden (--gm-accent) türer. SVG gradyan duraklarına
       `style="stop-color:var(…)"` ile bağlanır; canvas `var()` okuyamadığı için renkler
       kurulumda bir yoklama öğesiyle çözülüp piksel olarak önbelleklenir (`paletOku`).
       Karakter değişince hud-ring.js `renkTazele()` çağırır.
     · Sekme çarkı yuvaları SABİT 7 değil: üründe çarkta 2 düğme var (CHAT · AYAR);
       sayı DOM'dan okunur, yuvalar düğmelerin tam altına gelir.
     · ULTRA/3D katmanı yok (üründe HudRing3D yok) → kg-ufuk-ultra / kg-ad atıldı.

   Yaşam döngüsü hud-ring.js'te (`_temaSenkron`): HALKA açık ve tema seçiliyken init(),
   HALKA'dan çıkınca / tema değişince kaldir(). İkisi de idempotent.
     · init(): #hr-ring-wrap içine TEK kapsayıcı (.kg-sus) koyar — canvas .kg-gok (z -1,
       halkanın arkası) + svg .kg-svg (z 1). Sahne yeniden kurulmuşsa eskisini söküp yeniden kurar.
     · kaldir(): rAF, aralık ve gözcüyü durdurur, kapsayıcıyı siler, ad inişini geri alır.
   Mevcut düğümlerin id/sınıf/olaylarına DOKUNMAZ; fetch/localStorage YOK.
   Tek rAF döngüsü (30 fps'e kısılı); sekme gizliyken, tema kapalıyken ve HALKA dışında
   çizmez. HAFİF kademede / "hareketi azalt"ta tek kare çizilir, döngü kurulmaz.
   🔴 .kg-sus'a z-index/opacity verme: yığın bağlamı açar, canvas halkanın önüne fırlar. */
(function () {
  'use strict';

  const AD = 'kara-mana-goz';
  const NS = 'http://www.w3.org/2000/svg';
  const f = (v) => v.toFixed(1);
  const RAD = Math.PI / 180;

  // Halka geometrisi (viewBox 600): ufuk r=86 · foton halkası r=100 ·
  // karakter çarkı r=102 (17%) · sekme çarkı r=228 (38%, -90°'den başlar)
  const UFUK = 86, FOTON = 100, ISCO = 228, EINSTEIN = 400;   // Einstein yarıçapı halkanın ve zaman çemberinin DIŞINDA: bükülen yaylar halkayı dıştan sarar
  // Yuvalar Odaklı Halka'nın düğümlerine oturur (hud-ring.js `halka:odak-ciz` → n + başlangıç açısı).
  // Grup değişince düğüm sayısı değişir (SEKMELER kademeye göre 2-7 · KARAKTER yalnız 2+ karakterde) → yuvalar yeniden çizilir.
  const carkN = () => Math.max(1, document.querySelectorAll('#hr-odak .hr-od-dugum').length);
  const carkBas = () => -90 + 180 / carkN();

  // SVG durak rengi: değişken adı + opaklık (renk CSS'te, burada yalnız ad)
  const dur = (o, v, a) => `<stop offset="${o}" style="stop-color:var(${v})${a == null ? '' : ';stop-opacity:' + a}"/>`;

  // Kurulu örneğin durumu — kaldir() hepsini sıfırlar
  const S = { kap: null, raf: 0, aralik: 0, gozcu: null, yenidenCiz: null };

  let tohum = 7;
  const rnd = () => { tohum = (tohum * 16807) % 2147483647; return (tohum - 1) / 2147483646; };

  // ── cyan enerji damarları (kara-mana'dan) ──
  function damarlar() {
    const acilar = [-142, -104, -66, 38, 72, 112, 146];
    let ana = '', kol = '';
    acilar.forEach((derece, i) => {
      let a = derece, r = 112;
      const son = 205 + rnd() * 45;
      const pts = [];
      while (r < son) {
        const rad = a * RAD;
        pts.push([300 + r * Math.cos(rad), 300 + r * Math.sin(rad)]);
        r += 13 + rnd() * 12;
        a += (rnd() - 0.5) * 9;
      }
      ana += `<path class="kg-damar" style="--kg-i:${i}" d="M${pts.map(p => f(p[0]) + ',' + f(p[1])).join(' L')}"/>`;
      const k = pts[Math.floor(pts.length / 2)];
      const ka = (derece + (i % 2 ? 24 : -24)) * RAD;
      const k2 = [k[0] + 22 * Math.cos(ka), k[1] + 22 * Math.sin(ka)];
      const k3 = [k2[0] + 12 * Math.cos(ka + 0.4), k2[1] + 12 * Math.sin(ka + 0.4)];
      kol += `<path class="kg-damar kg-kol" style="--kg-i:${i}" d="M${f(k[0])},${f(k[1])} L${f(k2[0])},${f(k2[1])} L${f(k3[0])},${f(k3[1])}"/>`;
    });
    return ana + kol;
  }

  // ── altın korlar: dıştan içeri sarmal (n adet; ikinci takım yalnız düşünürken) ──
  function korlar(n, sinif) {
    let s = '';
    for (let i = 0; i < n; i++) {
      const a = i * (360 / n) + rnd() * 18;
      const r = 215 + rnd() * 55;
      const sure = (sinif ? 3.2 + rnd() * 2 : 8 + rnd() * 5).toFixed(1);
      const gecik = (-rnd() * 10).toFixed(1);
      s += `<g class="kg-kor ${sinif}" style="animation-duration:${sure}s;animation-delay:${gecik}s">` +
           `<circle cx="${f(300 + r * Math.cos(a * RAD))}" cy="${f(300 + r * Math.sin(a * RAD))}" r="${(sinif ? 2 + rnd() * 1.4 : 1.3 + rnd() * 1.2).toFixed(1)}"/></g>`;
    }
    return s;
  }

  function lekeler(n) {
    let s = '';
    for (let i = 0; i < n; i++) {
      const a = rnd() * Math.PI * 2, r = 108 + rnd() * 150;
      s += `<circle cx="${f(r * Math.cos(a))}" cy="${f(r * Math.sin(a))}" r="${(2 + rnd() * 2.6).toFixed(1)}" opacity="${(0.35 + rnd() * 0.55).toFixed(2)}"/>`;
    }
    return s;
  }

  // ── kararlı yörünge: sekme çarkının 7 düğme yuvası (r=228'de, CSS ile küçülüp büyür) ──
  function yuvalar() {
    let s = '';
    const n = carkN();
    for (let i = 0; i < n; i++) {
      const a = (carkBas() + i * 360 / n);
      const a1 = (a - 9) * RAD, a2 = (a + 9) * RAD;
      // düğmenin iki yanında kısa altın yay + dışa bakan çentik
      const yay = (b1, b2) => `M${f(300 + ISCO * Math.cos(b1))},${f(300 + ISCO * Math.sin(b1))} A${ISCO},${ISCO} 0 0 1 ${f(300 + ISCO * Math.cos(b2))},${f(300 + ISCO * Math.sin(b2))}`;
      const uc = (b, d) => `M${f(300 + (ISCO - d) * Math.cos(b))},${f(300 + (ISCO - d) * Math.sin(b))} L${f(300 + (ISCO + d) * Math.cos(b))},${f(300 + (ISCO + d) * Math.sin(b))}`;
      s += `<path class="kg-yuva" d="${yay(a1 - 6 * RAD, a1)} ${yay(a2, a2 + 6 * RAD)} ${uc(a1 - 6 * RAD, 9)} ${uc(a2 + 6 * RAD, 9)}"/>`;
      const ac = a * RAD;
      s += `<line class="kg-yuva-cent" x1="${f(300 + (ISCO + 30) * Math.cos(ac))}" y1="${f(300 + (ISCO + 30) * Math.sin(ac))}" x2="${f(300 + (ISCO + 38) * Math.cos(ac))}" y2="${f(300 + (ISCO + 38) * Math.sin(ac))}"/>`;
    }
    return s;
  }

  // Odaklı Halka yeniden çizilince (grup / kademe / karakter değişimi) yuvalar ona uyar.
  document.addEventListener('halka:odak-ciz', () => {
    const g = document.querySelector('.kg-yuvalar');
    if (g) g.innerHTML = yuvalar();
  });

  // ── göz: iris lifleri (C'den) ──
  function irisCizgileri() {
    let s = '';
    for (let i = 0; i < 40; i++) {
      const a = i * Math.PI * 2 / 40 + (rnd() - 0.5) * 0.06;
      const r1 = 9 + rnd() * 4, r2 = 24 + rnd() * 11;
      s += `<line x1="${f(r1 * Math.cos(a))}" y1="${f(r1 * Math.sin(a))}" x2="${f(r2 * Math.cos(a))}" y2="${f(r2 * Math.sin(a))}"/>`;
    }
    return s;
  }

  // ── dinleme girdabı: logaritmik sarmal kollar r=290 → ufuk ──
  function girdap() {
    let s = '';
    const r0 = 292, r1 = UFUK + 8, tur = 0.85 * Math.PI * 2;
    const kk = Math.log(r0 / r1) / tur;
    for (let k = 0; k < 5; k++) {
      const pts = [];
      for (let t = 0; t <= tur; t += 0.06) {
        const r = r0 * Math.exp(-kk * t), a = t + k * (Math.PI * 2 / 5);
        pts.push(f(300 + r * Math.cos(a)) + ',' + f(300 + r * Math.sin(a)));
      }
      s += `<path class="kg-kol-sarmal" d="M${pts.join(' L')}"/>`;
    }
    return s;
  }

  // ── kutup jeti (üst; alt olan aynısının aynası) ──
  // jet içinde dönen iki sarmal plazma ipliği (helis): 2 periyot fazla çizilir, CSS kaydırır
  function sarmal(b, u) {
    const yon = u < b ? -1 : 1, P = 26, boy = Math.abs(u - b) + 2 * P;
    let s = '';
    for (const faz of [0, Math.PI]) {
      const pts = [];
      for (let d = -2 * P; d <= boy; d += 2) {
        const gen = 2.2 + 3.2 * Math.min(1, Math.max(0, d) / (boy * 0.5));   // dışa doğru açılır
        pts.push(f(300 + gen * Math.sin(d / P * Math.PI * 2 + faz)) + ',' + f(b + yon * d));
      }
      s += `<path class="kg-iplik" d="M${pts.join(' L')}"/>`;
    }
    return `<g class="${yon < 0 ? 'kg-sarmal-u' : 'kg-sarmal-a'}">${s}</g>`;
  }

  function jet(yon) {
    const b = yon < 0 ? 300 - UFUK - 4 : 300 + UFUK + 4;   // ufkun kutbu
    const u = yon < 0 ? -28 : 628;                         // uç (r≈328)
    const id = yon < 0 ? 'kg-jet-g-u' : 'kg-jet-g-a';
    return `
    <linearGradient id="${id}" gradientUnits="userSpaceOnUse" x1="300" y1="${b}" x2="300" y2="${u}">
      ${dur(0, '--kg-isik', 0.85)}
      ${dur(0.15, '--kg-buz-acik', 0.75)}
      ${dur(0.5, '--kg-buz', 0.35)}
      ${dur(0.85, '--kg-buz', 0.06)}
      ${dur(1, '--kg-buz', 0)}
    </linearGradient>
    <!-- maske TAM kutupta başlar: sarmalın kaydırma payı (2 periyot) ufkun içine, isme taşmasın -->
    <mask id="${id}-m" maskUnits="userSpaceOnUse" x="250" y="${Math.min(b, u)}" width="100" height="${Math.abs(u - b)}">
      <rect x="250" y="${Math.min(b, u)}" width="100" height="${Math.abs(u - b)}" fill="url(#${id})"/>
    </mask>
    <g class="kg-jet ${yon < 0 ? 'kg-jet-ust' : 'kg-jet-alt'}" style="transform-origin:300px ${b}px">
      <polygon class="kg-jet-hale" points="285,${b} 315,${b} 301.5,${u} 298.5,${u}" fill="url(#${id})"/>
      <polygon class="kg-jet-govde" points="296.5,${b} 303.5,${b} 300.3,${u} 299.7,${u}" fill="url(#${id})"/>
      <g mask="url(#${id}-m)"><g class="kg-sarmal">${sarmal(b, u)}</g></g>
      <line class="kg-jet-oz" x1="300" y1="${b}" x2="300" y2="${(b + u) / 2}"/>
      <ellipse class="kg-kutup" cx="300" cy="${b}" rx="6" ry="3"/>
      <ellipse class="kg-dugum" cx="300" cy="${b + (u - b) * 0.18}" rx="3.2" ry="7"/>
      <ellipse class="kg-dugum kg-dugum2" cx="300" cy="${b + (u - b) * 0.18}" rx="2.4" ry="5"/>
    </g>`;
  }

  function svg() {
    const halkalar = [
      [112, 17, 2.4, 0.95], [126, 20, 5.5, 0.6], [146, 23, 3, 0.55],
      [170, 27, 6, 0.3], [198, 31, 2, 0.35], [232, 36, 1.2, 0.25], [268, 41, 0.8, 0.16],
    ].map(([rx, ry, w, o]) => `<ellipse cx="300" cy="300" rx="${rx}" ry="${ry}" stroke-width="${w}" opacity="${o}"/>`).join('');
    return `
<svg class="kg-svg" viewBox="0 0 600 600" xmlns="${NS}" aria-hidden="true" focusable="false">
  <defs>
    <linearGradient id="kg-disk-g" gradientUnits="userSpaceOnUse" x1="32" y1="300" x2="568" y2="300">
      ${dur(0, '--kg-altin-isik')}
      ${dur(0.22, '--kg-altin-acik')}
      ${dur(0.5, '--kg-altin')}
      ${dur(0.8, '--kg-altin-koyu')}
      ${dur(1, '--kg-mor')}
    </linearGradient>
    <linearGradient id="kg-kemer-g" gradientUnits="userSpaceOnUse" x1="176" y1="0" x2="424" y2="0">
      ${dur(0, '--kg-altin', 0.15)}
      ${dur(0.2, '--kg-altin', 0.7)}
      ${dur(0.42, '--kg-altin-isik', 1)}
      ${dur(0.7, '--kg-altin', 0.7)}
      ${dur(1, '--kg-mor', 0.25)}
    </linearGradient>
    <filter id="kg-yumusak" x="-30%" y="-60%" width="160%" height="220%"><feGaussianBlur stdDeviation="5"/></filter>
    <mask id="kg-isim" maskUnits="userSpaceOnUse" x="-200" y="-200" width="1000" height="1000">
      <rect x="-200" y="-200" width="1000" height="1000" fill="#fff"/>
      <rect x="232" y="280" width="136" height="36" rx="14" fill="#000" filter="url(#kg-yumusak)"/>
      <!-- göz açıkken disk gözün çevresinde açılır: alt kapak diskin altın bandıyla kaynaşmasın -->
      <ellipse class="kg-maske-goz" cx="300" cy="300" rx="88" ry="50" fill="#000" filter="url(#kg-yumusak)"/>
    </mask>
    <mask id="kg-arka" maskUnits="userSpaceOnUse" x="0" y="0" width="600" height="600">
      <rect x="0" y="0" width="600" height="600" fill="#fff"/>
      <path d="M 210,300 A 90,90 0 0 1 390,300 Z" fill="#000"/>
    </mask>
    <linearGradient id="kg-ip-g" gradientUnits="userSpaceOnUse" x1="${300 + FOTON}" y1="0" x2="630" y2="0">
      ${dur(0, '--kg-altin-isik', 1)}
      ${dur(0.35, '--kg-altin', 0.75)}
      ${dur(0.75, '--kg-buz', 0.35)}
      ${dur(1, '--kg-buz', 0)}
    </linearGradient>
    <radialGradient id="kg-iris-g" cx="0" cy="0" r="36" gradientUnits="userSpaceOnUse">
      ${dur(0, '--kg-altin-derin')}${dur(0.24, '--kg-altin-koyu')}
      ${dur(0.5, '--kg-altin')}${dur(0.74, '--kg-altin-acik')}
      ${dur(0.92, '--kg-altin-koyu')}${dur(1, '--kg-altin-derin')}
    </radialGradient>
    <radialGradient id="kg-ak-g" cx="300" cy="300" r="82" gradientUnits="userSpaceOnUse">
      ${dur(0, '--kg-mor-gece')}${dur(0.7, '--kg-bosluk')}${dur(1, '--kg-bosluk-derin')}
    </radialGradient>
    <linearGradient id="kg-tarama-g" x1="0" y1="0" x2="1" y2="0">
      ${dur(0, '--kg-buz', 0)}${dur(0.5, '--kg-buz', 0.75)}
      ${dur(1, '--kg-buz', 0)}
    </linearGradient>
    <clipPath id="kg-goz-kesit"><path class="kg-goz-yol" d="M300,300 Z"/></clipPath>
    ${jet(-1)}${jet(1)}
  </defs>

  <!-- düşen korlar (ikinci takım yalnız düşünürken görünür) -->
  <g class="kg-korlar">${korlar(12, '')}${korlar(28, 'kg-kor-yogun')}</g>

  <!-- cyan damarlar: dinlerken içe kıvrılır -->
  <g class="kg-damarlar" fill="none">${damarlar()}</g>

  <!-- dinleme girdabı: ufka doğru dönen 5 cyan sarmal kol (yalnız dinlerken) -->
  <g class="kg-girdap" fill="none">${girdap()}</g>

  <!-- kararlı yörünge (ISCO): sekme çarkı açılınca foton halkasından düğme yarıçapına genişler -->
  <g class="kg-isco" fill="none">
    <circle cx="300" cy="300" r="${ISCO}" class="kg-isco-halka"/>
    <circle cx="300" cy="300" r="${ISCO - 5}" class="kg-isco-ince"/>
    <g class="kg-yuvalar">${yuvalar()}</g>
  </g>

  <!-- kutup jetleri: yalnız konuşurken -->
  <g class="kg-jetler">${''}</g>

  <!-- toplanma diski (ismin önünde yumuşak boşluk) -->
  <g mask="url(#kg-isim)"><g class="kg-disk">
    <g class="kg-mercek" fill="none" stroke="url(#kg-kemer-g)" stroke-linecap="round">
      <path d="M 176,300 A 124,124 0 0 1 424,300" stroke-width="11" opacity="0.32"/>
      <path d="M 188,300 A 112,112 0 0 1 412,300" stroke-width="2.8"/>
      <path d="M 202,300 A 98,98 0 0 0 398,300" stroke-width="1.8" opacity="0.65"/>
    </g>
    <g mask="url(#kg-arka)">
      <g class="kg-halkalar" fill="none" stroke="url(#kg-disk-g)">${halkalar}</g>
      <g transform="translate(300 300) scale(1 0.162)">
        <g class="kg-leke">${lekeler(26)}</g>
      </g>
    </g>
  </g></g>

  <!-- ufuk: kenar + düşünürken nabız + şok halkası -->
  <g class="kg-ufuk" fill="none">
    <circle cx="300" cy="300" r="${UFUK + 1.5}" class="kg-ufuk-kenar"/>
    <circle cx="300" cy="300" r="${UFUK + 2}" class="kg-sok"/>
    <circle cx="300" cy="300" r="${UFUK + 2}" class="kg-sok kg-sok2"/>
  </g>

  <!-- foton halkası: ince, parlak, çift (n=1 ve n=2 alt halka); karakter çarkı buna oturur -->
  <g class="kg-foton" fill="none">
    <circle cx="300" cy="300" r="${FOTON}" class="kg-foton-1"/>
    <circle cx="300" cy="300" r="${FOTON - 3.2}" class="kg-foton-2"/>
  </g>

  <!-- GÖZ (C'den): kapaklar/iris/bebek JS'te her karede; açıklık 0 iken görünmez -->
  <g class="kg-goz" opacity="0">
    <path class="kg-kapak-hale kg-goz-yol" d="M300,300 Z"/>
    <g clip-path="url(#kg-goz-kesit)">
      <circle cx="300" cy="300" r="84" fill="url(#kg-ak-g)"/>
      <g class="kg-iris" transform="translate(300 300)">
        <circle r="36" fill="url(#kg-iris-g)"/>
        <g class="kg-cizgi">${irisCizgileri()}</g>
        <g class="kg-cizgi kg-cizgi-koyu">${irisCizgileri()}</g>
        <circle class="kg-iris-ic" r="24" fill="none" stroke-width="2.2" stroke-dasharray="5 3 2 4" opacity="0.7"/>
        <circle class="kg-limbus" r="36"/>
        <circle class="kg-iris-mor" r="15" fill="none" stroke-width="1" opacity="0.6"/>
        <ellipse class="kg-bebek" rx="4" ry="31"/>
        <ellipse class="kg-parilti" cx="-13" cy="-14" rx="4.5" ry="3" opacity="0.85"/>
        <circle class="kg-parilti" cx="10" cy="12" r="1.6" opacity="0.55"/>
      </g>
      <rect class="kg-tarama" x="0" y="230" width="22" height="140" opacity="0"/>
    </g>
    <path class="kg-kapak kg-kapak-alt" d="M300,300 Z"/>
    <path class="kg-kapak kg-kapak-ust" d="M300,300 Z"/>
    <path class="kg-kanat" d="M300,300 Z"/>
  </g>
  <!-- göz–jet ekseni: konuşurken göz bebeğinden iki kutba ince ışık (tek eksen) -->
  <g class="kg-eksen" opacity="0">
    <line x1="300" y1="252" x2="300" y2="${300 - UFUK - 4}"/>
    <line x1="300" y1="342" x2="300" y2="349"/>      <!-- isim (y≈353-377) eksenin önünde kalır -->
  </g>

  <!-- gelgit dalgası: widget açılınca ufuktan dışa yayılan tek altın halka -->
  <circle cx="300" cy="300" r="${FOTON}" class="kg-dalga" fill="none"/>
  <circle cx="300" cy="300" r="${FOTON}" class="kg-dalga kg-dalga2" fill="none"/>
  <!-- gelgit ipi: açılan widget yönüne uzanıp söner (açı JS'ten) -->
  <g class="kg-gelgit" transform="rotate(0 300 300)">
    <g class="kg-gelgit-ic">
      <polygon class="kg-ip" points="${300 + FOTON},297.5 ${300 + FOTON},302.5 ${300 + 330},300.6 ${300 + 330},299.4"/>
      <path class="kg-ip-alev" d="M${f(300 + FOTON * Math.cos(-28 * RAD))},${f(300 + FOTON * Math.sin(-28 * RAD))} A${FOTON},${FOTON} 0 0 1 ${f(300 + FOTON * Math.cos(28 * RAD))},${f(300 + FOTON * Math.sin(28 * RAD))}"/>
    </g>
  </g>
</svg>`;
  }

  // ═════════════════════ GÖZ SÜRÜCÜSÜ (C'den, sadeleştirildi) ═════════════════════
  //  ap: göz açıklığı · tara: iris tarama · ses: konuşma nabzı. Durum A'nın tablosuyla:
  //  boşta/dinliyor kapalı (A fiziği) · düşünüyor yarı açık tarar · konuşuyor tam açık.
  const HEDEF = {
    idle:      { ap: 0,   tara: 0, ses: 0 },
    listening: { ap: 0,   tara: 0, ses: 0 },
    thinking:  { ap: 0.5, tara: 1, ses: 0 },
    talking:   { ap: 1,   tara: 0, ses: 1 },
  };
  const P = { ap: 0, tara: 0, ses: 0 };
  let G = null, bakis = null, isimInik = false;
  const durumAdi = (st) => {
    const c = st ? st.className : '';
    return c.includes('hr-talking') ? 'talking' : c.includes('hr-thinking') ? 'thinking'
      : c.includes('hr-listening') ? 'listening' : 'idle';
  };
  // Konuşma nabzı — DOM'da gerçek ses seviyesi yok; hece ritminde sentetik zarf (C ile aynı)
  function sesZarfi(t) {
    const hece = Math.max(0, Math.sin(t * 5.3) + 0.35);
    const v = 0.55 + 0.3 * Math.sin(t * 11.3) * Math.sin(t * 3.1 + 1) + 0.15 * Math.sin(t * 23.7);
    return Math.max(0, Math.min(1, v * Math.min(1, hece)));
  }
  // Bakış zarfı: 0,2 sn'de açılır, ~1 sn tutar, 0,4 sn'de kapanır
  function bakisZarfi(t) {
    if (!bakis) return 0;
    const u = t - bakis.t0;
    if (u < 0 || u > 1.6) { bakis = null; return 0; }
    return u < 0.2 ? u / 0.2 : u < 1.2 ? 1 : 1 - (u - 1.2) / 0.4;
  }
  function gozBak(aci) { bakis = { a: aci, t0: performance.now() / 1000 }; }

  function gozKur(kap, stage) {
    G = {
      kap, stage,
      g: kap.querySelector('.kg-goz'),
      yollar: kap.querySelectorAll('.kg-goz-yol'),
      ust: kap.querySelector('.kg-kapak-ust'), alt: kap.querySelector('.kg-kapak-alt'),
      kanat: kap.querySelector('.kg-kanat'), iris: kap.querySelector('.kg-iris'),
      bebek: kap.querySelector('.kg-bebek'), tarama: kap.querySelector('.kg-tarama'),
      eksen: kap.querySelector('.kg-eksen'),
      govde: [...kap.querySelectorAll('.kg-jet-govde')], hale: [...kap.querySelectorAll('.kg-jet-hale')],
      acik: false,
    };
  }

  function gozAdim(dt, aniden) {
    if (!G) return;
    if (!G.stage || !G.stage.isConnected) G.stage = document.getElementById('hr-stage');
    const t = performance.now() / 1000;
    const h = HEDEF[durumAdi(G.stage)];
    const oran = aniden ? 1 : 1 - Math.exp(-dt * 5.5);
    for (const k in h) P[k] += (h[k] - P[k]) * oran;
    const bz = bakisZarfi(t);
    let ap = Math.max(P.ap, 0.8 * bz);
    // isim: göz belirgin açıkken küçülüp gözün altına iner (gizlenmez) — CSS sınıfla
    const inik = ap > 0.12;
    if (inik !== isimInik) { isimInik = inik; G.kap.classList.toggle('kg-goz-acik', inik); }
    if (P.ses > 0.5) {                                 // konuşurken 5,3 sn'de bir kırpış
      const b = t % 5.3;
      if (b < 0.16) ap *= 0.1 + 0.9 * Math.abs(b - 0.08) / 0.08;
    }
    const v = sesZarfi(t) * P.ses;
    // jetler bebekle aynı zarfla atar (CSS ritmi yerine) + göz–jet ekseni
    G.govde.forEach(j => { j.style.opacity = (0.7 + 0.3 * v).toFixed(3); });
    G.hale.forEach(j => { j.style.transform = `scaleX(${(1 + 0.55 * v).toFixed(3)})`; j.style.opacity = (0.22 + 0.18 * v).toFixed(3); });
    G.eksen.setAttribute('opacity', (P.ses * Math.min(1, ap * 1.4) * (0.35 + 0.65 * v)).toFixed(3));
    if (ap < 0.015) {
      if (G.acik) { G.g.setAttribute('opacity', '0'); G.acik = false; }
      return;
    }
    G.acik = true;
    G.g.setAttribute('opacity', Math.min(1, ap * 3).toFixed(3));
    const W = 74, H = 46 * ap;
    const ust = `M${300 - W},300 Q300,${f(300 - 2 * H)} ${300 + W},300`;
    const alt = `M${300 - W},300 Q300,${f(300 + 1.7 * H)} ${300 + W},300`;
    const kapali = `${ust} Q300,${f(300 + 1.7 * H)} ${300 - W},300 Z`;
    G.yollar.forEach(p => p.setAttribute('d', kapali));
    G.ust.setAttribute('d', ust);
    G.alt.setAttribute('d', alt);
    const k = 9 * ap;
    G.kanat.setAttribute('d', `M${300 + W - 8},${f(300 - 3)} Q${300 + W + 6},${f(300 - 4)} ${300 + W + 12},${f(300 - k - 4)} M${300 - W + 8},${f(300 - 3)} Q${300 - W - 6},${f(300 - 4)} ${300 - W - 12},${f(300 - k - 4)}`);
    let ix = 0, iy = 0;
    if (P.tara > 0.05) ix += P.tara * 26 * Math.sin(t * 1.9);
    if (P.ses > 0.05) { const sk = Math.floor(t * 0.8); ix += P.ses * 5 * Math.sin(sk * 12.9); iy += P.ses * 3 * Math.sin(sk * 7.3); }
    if (bz > 0) { ix += 26 * Math.cos(bakis.a) * bz; iy += 34 * Math.sin(bakis.a) * bz; }   // dikeyde de belirgin
    G.iris.setAttribute('transform', `translate(${f(300 + ix)} ${f(300 + iy)}) scale(${(1 + 0.05 * v).toFixed(3)})`);
    G.bebek.setAttribute('rx', f(2.2 + 1.4 * (1 - P.tara) + 6.5 * v));
    G.bebek.setAttribute('ry', f(13 + 18 * Math.min(1, ap)));
    if (P.tara > 0.05) {
      const u = (t * 0.75) % 1;
      G.tarama.setAttribute('x', f(300 - W + u * (2 * W) - 11));
      G.tarama.setAttribute('opacity', (P.tara * 0.65 * Math.sin(u * Math.PI)).toFixed(3));
    } else G.tarama.setAttribute('opacity', '0');
  }

  // ═════════════════════ canvas paleti (token → piksel) ═════════════════════
  // Canvas `var()`/`color-mix()` çözemez. Her `--kg-*` değişkeni bir yoklama
  // öğesinin `color`'ına yazılır, tarayıcının hesapladığı renk 1×1 tuvale
  // boyanıp "r,g,b" olarak okunur — oklch/color-mix hangi biçimde dönerse dönsün.
  // Yoklama #hr-ring-wrap İÇİNDE: HALKA koyu palete sabitlenmiş kapta çözülsün
  // (html açık temadayken bile; chat-modes.js `data-tema="koyu"`).
  const PALET_ADLARI = ['bosluk', 'bosluk-derin', 'mor', 'mor-derin', 'mor-acik', 'altin', 'buz', 'buz-acik', 'isik'];
  let R = null;
  function paletOku(wrap) {
    const yok = document.createElement('span');
    yok.style.cssText = 'position:absolute;visibility:hidden;pointer-events:none';
    wrap.appendChild(yok);
    const tv = document.createElement('canvas');
    tv.width = tv.height = 1;
    const c = tv.getContext('2d', { willReadFrequently: true });
    const p = {};
    for (const ad of PALET_ADLARI) {
      yok.style.color = 'var(--kg-' + ad + ')';
      c.clearRect(0, 0, 1, 1);
      c.fillStyle = getComputedStyle(yok).color;
      c.fillRect(0, 0, 1, 1);
      const d = c.getImageData(0, 0, 1, 1).data;
      p[ad] = d[0] + ',' + d[1] + ',' + d[2];
    }
    yok.remove();
    return p;
  }

  // ═════════════════════ canvas: mercek + Hawking ═════════════════════
  function gokKur(cv, wrap, stage, kap) {
    const ctx = cv.getContext('2d');
    const N = 420, YAY = 600;              // yıldız sayısı · dağılım yarı-genişliği (birim)
    const yildiz = [];
    // arka plandaki galaksi kümeleri: merceklenince Einstein halkası boyunca dev yay çizerler
    //  Çevreye yayılmış 6 küme (her biri iki yanda yay verir → yaylar halkanın her yanında);
    //  çok sayıda ince, soluk nokta üst üste binip SÜREKLİ bir ışık yayı oluşturur.
    //  `renk` bir PALET ADI — piksel değeri her karede R'den (karakter değişince tazelenir).
    [[-60, -70, 'buz-acik'], [110, 40, 'altin'], [-20, 130, 'mor-acik'],
     [-150, 30, 'buz-acik'], [60, -150, 'mor-acik'], [190, -60, 'altin']].forEach(([gx, gy, renk]) => {
      for (let i = 0; i < 120; i++) {
        const a = rnd() * Math.PI * 2, r = Math.sqrt(rnd()) * 24;
        yildiz.push({ x: gx + Math.cos(a) * r * 1.5, y: gy + Math.sin(a) * r, r: 0.6 + rnd() * 0.5, a: 0.09 + rnd() * 0.1, renk, gal: 1 });
      }
    });
    for (let i = 0; i < N; i++) {
      const t = rnd();
      yildiz.push({
        x: (rnd() * 2 - 1) * YAY, y: (rnd() * 2 - 1) * YAY,
        r: 0.45 + Math.pow(rnd(), 3) * 1.25,
        a: 0.35 + rnd() * 0.6,
        renk: t < 0.07 ? 'altin' : t < 0.2 ? 'buz' : t < 0.42 ? 'mor-acik' : 'isik',
      });
    }
    const kivilcim = [];
    let olcek = 1, boyut = 0, dpr = 1, son = 0, birikim = 0;

    function boyutla() {
      const s = cv.clientWidth;
      const w = wrap.clientWidth || 1;
      if (!s) return false;
      dpr = Math.min(window.devicePixelRatio || 1, 1.5);
      if (s !== boyut) {
        boyut = s;
        cv.width = Math.round(s * dpr);
        cv.height = Math.round(s * dpr);
      }
      olcek = (w / 600) * dpr;             // birim → canvas pikseli
      return true;
    }

    function durumHiz() {
      const c = stage ? stage.className : '';
      if (c.includes('hr-listening')) return { surukle: 3.2, hawking: 16 };
      if (c.includes('hr-talking')) return { surukle: 1.6, hawking: 40 };
      if (c.includes('hr-thinking')) return { surukle: 0.6, hawking: 12 };
      return { surukle: 1, hawking: 10 };
    }

    function ciz(dt) {
      if (!boyutla()) return;
      const W = cv.width, H = cv.height, cx = W / 2, cy = H / 2, k = olcek;
      const yariMax = W / 2 / k + 30;
      const dar = W / 2 / k < 420;                              // telefon: canvas yalnız halkanın karesi
      const EIN = dar ? 286 : EINSTEIN;                         // dar ekranda yaylar dış çentik bandında
      const IC_SINIR = dar ? 268 : 0;                           // dar ekranda rün bandının içine görüntü çizme
      const { surukle, hawking } = durumHiz();
      if (!R) R = paletOku(wrap);
      ctx.setTransform(1, 0, 0, 1, 0, 0);
      ctx.clearRect(0, 0, W, H);

      // zemin: merkez koyulaşan boşluk (alttaki düz yıldızları örter) + Einstein halkasında soluk mor ışık
      const g = ctx.createRadialGradient(cx, cy, 0, cx, cy, W / 2);
      g.addColorStop(0, `rgba(${R['bosluk-derin']},0.97)`);
      g.addColorStop(0.42, `rgba(${R.bosluk},0.9)`);
      g.addColorStop(0.78, `rgba(${R.bosluk},0.55)`);
      g.addColorStop(1, `rgba(${R.bosluk},0)`);
      ctx.fillStyle = g;
      ctx.fillRect(0, 0, W, H);
      const e = EIN * k;
      const h = ctx.createRadialGradient(cx, cy, e * 0.62, cx, cy, e * 1.45);
      // ürünün --mor-ink'i kişiselin morundan açık → hale derin morla çizilir,
      // yoksa canvas maskesinin kenarında seçilen bir bant oluşuyordu (ölçüldü)
      h.addColorStop(0, `rgba(${R['mor-derin']},0)`);
      h.addColorStop(0.36, `rgba(${R['mor-derin']},0.075)`);
      h.addColorStop(0.55, `rgba(${R['mor-derin']},0.035)`);
      h.addColorStop(1, `rgba(${R['mor-derin']},0)`);
      ctx.fillStyle = h;
      ctx.fillRect(0, 0, W, H);
      // Einstein halkasının kendisi: çok soluk ince çizgi — yayların "neye büküldüğü" okunsun
      ctx.strokeStyle = `rgba(${R['mor-acik']},0.10)`;
      ctx.lineWidth = 1.2 * dpr;
      ctx.beginPath(); ctx.arc(cx, cy, e, 0, Math.PI * 2); ctx.stroke();

      // yıldızlar: gerçek nokta-kütle merceği — θ± = (β ± √(β²+4θE²)) / 2
      const E = EIN, E2 = 4 * E * E;
      for (const s of yildiz) {
        s.x += 5 * surukle * dt;
        if (s.x > YAY) s.x -= 2 * YAY;
        const b = Math.max(0.5, Math.hypot(s.x, s.y));
        const ux = s.x / b, uy = s.y / b;
        const kok = Math.sqrt(b * b + E2);
        const u = b / E, m0 = (u * u + 2) / (2 * u * Math.sqrt(u * u + 4));
        const yon = Math.atan2(uy, ux);   // elipsin x ekseni = radyal, y ekseni = teğet (yay boyunca uzar)
        for (let i = 0; i < 2; i++) {
          const t = i === 0 ? (b + kok) / 2 : (b - kok) / 2;      // ikinci görüntü ters yanda
          const at = Math.abs(t);
          if (at > yariMax) continue;
          if (i === 1 && at < UFUK + 6) continue;                  // gölgenin içinde
          if (at < IC_SINIR) continue;
          const mu = Math.min(3.2, m0 + (i === 0 ? 0.5 : -0.5));
          if (mu < 0.04) continue;
          const teget = Math.min(s.gal ? 9 : 7, at / b);
          const radyal = Math.max(s.gal ? 1.6 : 0.35, 0.5 * (1 + (i === 0 ? 1 : -1) * b / kok));   // galaksi noktaları radyalde kalın → üst üste binip tek bant olur
          const r0 = s.r * dpr * Math.sqrt(Math.max(0.6, mu));
          // istem yazısının bölgesi (alt, dar koni, halkanın dışı): yaylar yazının üstüne binmesin
          const iy = (i === 0 ? uy : -uy) * at, ix = (i === 0 ? ux : -ux) * at;
          const yaziBolgesi = iy > 250 && Math.abs(ix) < iy * 0.8;
          ctx.globalAlpha = Math.min(1, s.a * (0.45 + mu * 0.4)) * (yaziBolgesi ? 0.12 : 1);
          ctx.fillStyle = `rgb(${R[s.renk]})`;
          ctx.beginPath();
          ctx.ellipse(cx + ux * t * k, cy + uy * t * k, Math.max(0.5, r0 * radyal), r0 * teget, yon, 0, Math.PI * 2);
          ctx.fill();
        }
      }

      // Hawking ışıması: ufuktan dışarı kaçan soğuk kıvılcımlar
      birikim += hawking * dt;
      while (birikim >= 1) {
        birikim -= 1;
        if (kivilcim.length < 90) {
          kivilcim.push({ a: rnd() * Math.PI * 2, r: UFUK + 3, v: 26 + rnd() * 46, o: 0, omur: 0.7 + rnd() * 0.9 });
        }
      }
      ctx.globalCompositeOperation = 'lighter';
      for (let i = kivilcim.length - 1; i >= 0; i--) {
        const p = kivilcim[i];
        p.o += dt; p.r += p.v * dt;
        if (p.o > p.omur) { kivilcim.splice(i, 1); continue; }
        const x = cx + Math.cos(p.a) * p.r * k, y = cy + Math.sin(p.a) * p.r * k;
        const ka = 1 - p.o / p.omur;
        ctx.globalAlpha = ka * 0.9;
        ctx.fillStyle = `rgb(${R['buz-acik']})`;
        ctx.beginPath();
        ctx.arc(x, y, Math.max(0.8, 1.7 * dpr * ka + 0.4), 0, Math.PI * 2);
        ctx.fill();
        ctx.globalAlpha = ka * 0.5;                                // kısa iz
        ctx.strokeStyle = `rgb(${R.buz})`;
        ctx.lineWidth = 1.1 * dpr;
        ctx.beginPath();
        ctx.moveTo(x, y);
        ctx.lineTo(x - Math.cos(p.a) * 14 * k, y - Math.sin(p.a) * 14 * k);
        ctx.stroke();
      }
      ctx.globalCompositeOperation = 'source-over';
      ctx.globalAlpha = 1;
    }

    const sakin = document.documentElement.dataset.gfx === 'hafif' ||
      (window.matchMedia && matchMedia('(prefers-reduced-motion: reduce)').matches);
    // ilk kare: biraz "ileri sarılmış" hâl (kıvılcımlar yerinde olsun)
    for (let i = 0; i < 40; i++) ciz(1 / 30);
    gozAdim(0, true);
    if (sakin) {
      S.yenidenCiz = () => { if (S.kap === kap) ciz(0); };
      // donuk kip: döngü yok; durum değişince göz tek kare yenilenir
      let imza = '';
      S.aralik = setInterval(() => {
        const st = durumAdi(document.getElementById('hr-stage'));
        if (st !== imza) { imza = st; gozAdim(0, true); }
      }, 400);
      return;
    }
    (function dongu(now) {
      if (S.kap !== kap) return;                       // söküldü
      S.raf = requestAnimationFrame(dongu);
      if (document.hidden || document.documentElement.dataset.halkaTema !== AD ||
          !document.body.classList.contains('hud-ring-mode')) { son = now; return; }
      if (now - son < 33) return;
      const dt = Math.min(0.1, (now - (son || now)) / 1000);
      son = now;
      ciz(dt);
      gozAdim(dt, false);
    })(performance.now());
  }

  // ═════════════════════ widget açılınca gelgit ipi ═════════════════════
  function gelgitKur(kap, wrap) {
    const g = kap.querySelector('.kg-gelgit');
    const ic = kap.querySelector('.kg-gelgit-ic');
    function tetik(widget) {
      const wr = wrap.getBoundingClientRect(), r = widget.getBoundingClientRect();
      if (!r.width) return;
      const ax = r.left + r.width / 2 - (wr.left + wr.width / 2);
      const ay = r.top + r.height / 2 - (wr.top + wr.height / 2);
      g.setAttribute('transform', `rotate(${(Math.atan2(ay, ax) / RAD).toFixed(1)} 300 300)`);
      gozBak(Math.atan2(ay, ax));                // göz kısa süre açılıp o widget'a bakar
      kap.classList.remove('kg-cekim');
      void ic.getBoundingClientRect();     // animasyonu yeniden başlat
      kap.classList.add('kg-cekim');
    }
    S.gozcu = new MutationObserver((ms) => {
      for (const m of ms) {
        const el = m.target;
        if (!el.classList || !el.classList.contains('hr-widget')) continue;
        const once = (m.oldValue || '').includes('hr-w-hidden');
        if (once && !el.classList.contains('hr-w-hidden')) { tetik(el); break; }
      }
    });
    S.gozcu.observe(document.body, { subtree: true, attributes: true, attributeFilter: ['class'], attributeOldValue: true });
  }

  function kaldir() {
    if (S.raf) cancelAnimationFrame(S.raf);
    if (S.aralik) clearInterval(S.aralik);
    if (S.gozcu) S.gozcu.disconnect();
    if (S.kap) S.kap.remove();
    S.kap = null; S.raf = 0; S.aralik = 0; S.gozcu = null; S.yenidenCiz = null;
    G = null; bakis = null; isimInik = false; R = null;
  }

  // Karakter değişti (--gm-accent → --kg-buz): canvas paletini yeniden çöz.
  // Donuk kipte (HAFİF / hareketi azalt) döngü yok → tek kare yeniden çizilsin diye
  // `S.yenidenCiz` (gokKur kurar) çağrılır.
  function renkTazele() {
    R = null;
    if (S.yenidenCiz) S.yenidenCiz();
  }

  function init() {
    const wrap = document.getElementById('hr-ring-wrap');
    if (!wrap) return false;
    if (S.kap && S.kap.parentNode === wrap) return true;      // zaten kurulu
    kaldir();                                                  // sahne yeniden kurulduysa eskisini sök
    wrap.querySelectorAll(':scope > .kg-sus').forEach(e => e.remove());
    tohum = 7;                                                 // her kurulumda aynı gökyüzü
    P.ap = 0; P.tara = 0; P.ses = 0;
    const kap = document.createElement('div');
    kap.className = 'kg-sus';
    kap.setAttribute('aria-hidden', 'true');
    kap.innerHTML = '<canvas class="kg-gok"></canvas>' + svg();
    // jetleri defs'ten çıkarıp kendi gruplarına taşı (gradyan defs'te kalır)
    const s = kap.querySelector('.kg-svg');
    const jetler = s.querySelector('.kg-jetler');
    s.querySelectorAll('defs > .kg-jet').forEach(j => jetler.appendChild(j));
    wrap.appendChild(kap);
    S.kap = kap;
    const stage = document.getElementById('hr-stage');
    gozKur(kap, stage);
    gokKur(kap.querySelector('.kg-gok'), wrap, stage, kap);
    gelgitKur(kap, wrap);
    return true;
  }

  function durum() {
    return { kurulu: !!(S.kap && S.kap.isConnected), rafAktif: !!S.raf, aralikAktif: !!S.aralik, gozcu: !!S.gozcu };
  }

  window.HalkaTemalar = window.HalkaTemalar || {};
  window.HalkaTemalar[AD] = { init, kaldir, durum, renkTazele };
})();
