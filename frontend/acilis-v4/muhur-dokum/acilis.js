/* ════════════════════════════════════════════════════════════════
   ⑤ MÜHÜR + DÖKÜM — ① Mühür ile ② Çekirdek Dökümü iç içe
   Veri, mührün mürekkebidir:
     1) Döküm: mürekkep siyahında gerçek sistem satırları daktiloyla akar
        (camgöbeği metin, kehribar değer — kehribar = sayı kuralı).
     2) Akış: satırlar yukarıdan aşağı çözülür; her karakter eğri bir yolla
        merkeze uçar, yolda altına döner ve mührün çizgisine düşer.
        İlk 40 karakter rün halkasının yuvalarına iner — her rün, kendi
        karakteri vardığında yanar.
     3) Mühür: halkalar, heksagram (mor ↑ · buz ↓), gezegen mühürleri.
        Mührün içinde Yuki ASCII'den oluşur (②'nin oluşma anı):
        camgöbeği karakterler yukarıdan aşağı kaynar, yerine oturan altına
        döner; mor/buz yalnız gözlerde. Tek ateşleme anı ASCII'yi gerçek
        görsele çevirir → ışık sütununda Yuki (Poz 2, kollar açık), gözleri
        parlar, ad Fraunces ile mühürlenir, Yuki bir kez göz kırpar.
     4) Çıkış: mühür ışık noktasına iner, portal olup uygulamayı açar.
   Süre 5,8 sn · çıkış 0,7 sn.
   ════════════════════════════════════════════════════════════════ */
(function () {
  'use strict';
  var YOL = YukiAcilis.yolcu(document.currentScript);
  /* görünür metin: YukiDil anahtarı, yoksa Türkçe kaynak (ortak/veri.js YukiVeri.t) */
  function T(k, kaynak, d) { return window.YukiVeri && YukiVeri.t ? YukiVeri.t(k, kaynak, d) : kaynak; }

  var ALTIN = '232,195,106', MOR = '155,123,255', BUZ = '127,214,255';
  var CAM = '95,243,255', KEHR = '255,176,32', SOLUK = '29,111,120';
  var RUN = 'ᚠᚢᚦᚨᚱᚲᚷᚹᚺᚾᛁᛃᛇᛈᛉᛊᛏᛒᛖᛗᛚᛜᛞᛟ';
  var GEZEGEN = ['☉', '☽', '☿', '♀', '♃', '♄'];
  var RUN_N = 40, PARCA_EN = 260, UCUS = 650;
  var RAMPA = ' .:-=+*#%@', GLIF = '01<>/\\|=+*#$%&@';
  /* Görsel: Poz 2 'Mühür açılıyor' — kollar açık, saydam zemin, 1086x1448.
     Bütün koordinatlar görsel pikseli. ASCII oluşma: baştan bele (+ açık kollar, eldiven hizası), mührün iç halkasıyla
     kesilir (kollar/saç halka sınırında kesilebilir, yüz ve gövde ortada); hücre tam olarak
     gerçek görselin düşeceği yere oturur, ateşleme ASCII'yi aynı kadrajda gerçeğe çevirir. */
  var GORSEL = '../../assets/characters/yuki_muhur_poz2.webp', IW = 1086, IH = 1448;
  var KIRP = [134, 20, 818, 620], MERKEZ = [543, 424], GOZ = [[505, 160], [576, 154]], GOZ_YAR = 21, AYAK = 1405;
  var AS_BAS = 2000, AS_YAYIL = 850, AS_SEK = 200, AS_SON = [3200, 3650];
  /* göz kırpma: Yuki belirdikten sonra tek doğal kırpma (açık→yarı→kapalı→yarı→açık).
     Kareler yalnız göz bölgesi (GOZ_KUTU; görsel hazırlarken kullanılan kutuyla aynı), açık gözün üstüne biner. */
  var KIRPMA = [4600, 200], GOZ_KUTU = [478, 126, 128, 64];

  var S = {};

  function yerlesim(ctx) {
    var w = ctx.w, h = ctx.h, dar = ctx.dar;
    var figH = dar ? Math.min(h * 0.6, w * 1.3) : h * 0.9;
    var s = figH / IH, figW = IW * s;
    var cx = w / 2, top = dar ? h * 0.15 : h * 0.06, x0 = cx - figW / 2;
    S.L = {
      s: s, figW: figW, figH: figH, x: x0, y: top, cx: x0 + MERKEZ[0] * s, cy: top + MERKEZ[1] * s,
      R: dar ? Math.min(w * 0.44, h * 0.24) : Math.min(h * 0.31, w * 0.3),
      gozL: [x0 + GOZ[0][0] * s, top + GOZ[0][1] * s],
      gozR: [x0 + GOZ[1][0] * s, top + GOZ[1][1] * s],
      ayak: [x0 + MERKEZ[0] * s, top + AYAK * s],
      fs: dar ? 10 : Math.max(12, Math.min(15, w / 88)),
      dx: dar ? 14 : Math.max(40, w * .06), dy: dar ? 16 : h * .16
    };
    S.parca = null;     /* yerleşim değişince parçacık yolları yeniden kurulur */
    S.izgara = null;
  }

  /* görsel → ASCII ızgarası: hücre = karakter (parlaklık rampası) + altın tonu; göz hücreleri mor/buz */
  function izgaraKur(ctx) {
    if (!S.ham) return;
    var L = S.L, s = L.s, g = S.zemin.g;
    var fs = ctx.dar ? 8 : Math.max(9, Math.min(11, ctx.w / 125));
    g.font = '500 ' + fs + 'px "YA Mono", monospace';
    var cw = g.measureText('M').width * .82, ch = fs * 1.08;
    var kw = KIRP[2] * s, kh = KIRP[3] * s;
    var cols = Math.max(20, Math.floor(kw / cw)), rows = Math.max(12, Math.floor(kh / ch));
    var ox = L.x + KIRP[0] * s + (kw - cols * cw) / 2, oy = L.y + KIRP[1] * s + (kh - rows * ch) / 2;
    var o = document.createElement('canvas');
    o.width = cols; o.height = rows;
    var og = o.getContext('2d', { willReadFrequently: true });
    og.drawImage(S.ham, KIRP[0], KIRP[1], KIRP[2], KIRP[3], 0, 0, cols, rows);
    var d;
    try { d = og.getImageData(0, 0, cols, rows).data; } catch (e) { return; }
    var yar = L.R * .82 / s, hucre = [];
    for (var y = 0; y < rows; y++) for (var x = 0; x < cols; x++) {
      var ix = KIRP[0] + (x + .5) * KIRP[2] / cols, iy = KIRP[1] + (y + .5) * KIRP[3] / rows;
      if (Math.hypot(ix - MERKEZ[0], iy - MERKEZ[1]) > yar) continue;
      var i = (y * cols + x) * 4, lum = (d[i] * .299 + d[i + 1] * .587 + d[i + 2] * .114) / 255 * d[i + 3] / 255;
      if (lum < .045) continue;
      var goz = Math.hypot(ix - GOZ[0][0], iy - GOZ[0][1]) < GOZ_YAR ? MOR : Math.hypot(ix - GOZ[1][0], iy - GOZ[1][1]) < GOZ_YAR ? BUZ : null;
      hucre.push({ x: x, y: y, lum: lum, goz: goz, j: ((x * 73856093) ^ (y * 19349663)) >>> 0 });
    }
    /* kenar: komşu parlaklık farkı — saç teli, kol, yüz hattı yönlü karakter alır (silüet okunsun) */
    /* kesim kenarında komşu dışarıda kalırsa kenar pikseli tekrarlanır — yoksa alt sınır '———' çizgisi olur */
    var lumAt = function (x, y) { x = Math.max(0, Math.min(cols - 1, x)); y = Math.max(0, Math.min(rows - 1, y)); var i = (y * cols + x) * 4; return (d[i] * .299 + d[i + 1] * .587 + d[i + 2] * .114) / 255 * d[i + 3] / 255; };
    hucre.forEach(function (c) {
      var gx = lumAt(c.x + 1, c.y) - lumAt(c.x - 1, c.y), gy = lumAt(c.x, c.y + 1) - lumAt(c.x, c.y - 1);
      c.kenar = Math.hypot(gx, gy);
      var a = Math.atan2(gy, gx) * 180 / Math.PI; a = (a + 180) % 180;
      c.kc = a < 22.5 || a >= 157.5 ? '|' : a < 67.5 ? '\\' : a < 112.5 ? '-' : '/';
    });
    /* beyaz elbise/saç rampayı '@'a doyurur: parlaklığı sıraya göre eşitle ki yüz, saç, elbise ayrı karakter alsın */
    var sira = hucre.slice().sort(function (a, b) { return a.lum - b.lum; });
    sira.forEach(function (c, n) { c.es = .35 * c.lum + .65 * (n / Math.max(1, sira.length - 1)); });
    hucre.forEach(function (c) {
      var k = Math.min(RAMPA.length - 1, 1 + Math.floor(c.es * (RAMPA.length - 1)));
      /* altın tonu: koyu altın → altın → soluk altın */
      var a1 = Math.min(1, c.es * 1.6), a2 = Math.max(0, c.es * 1.6 - 1) / .6;
      c.c = !c.goz && c.kenar > .32 ? c.kc : RAMPA[k];
      if (c.goz) c.c = '@';
      c.renk = c.goz || [Math.round(120 + 112 * a1 + 23 * a2), Math.round(88 + 107 * a1 + 45 * a2), Math.round(40 + 66 * a1 + 99 * a2)].join(',');
      c.a = c.goz ? 1 : Math.min(.92, .32 + c.es * .7);
    });
    S.izgara = { cols: cols, rows: rows, cw: cw, ch: ch, ox: ox, oy: oy, fs: fs, hucre: hucre };
  }

  function hash(n) { n = (n ^ 61) ^ (n >>> 16); n = n + (n << 3); n = n ^ (n >>> 4); n = Math.imul(n, 0x27d4eb2d); return (n ^ (n >>> 15)) >>> 0; }

  /* ASCII oluşma: önce kaynayan camgöbeği glif, sonra yerine oturan karakter (altın flaşla) */
  function asciiCiz(g, t, ctx) {
    if (!S.izgara && S.ham) izgaraKur(ctx);
    var Z = S.izgara;
    if (!Z || t < AS_BAS - 260) return;
    var gor = 1 - ctx.aralik(t, AS_SON[0], AS_SON[1]);
    if (gor <= 0) return;
    g.save();
    g.globalCompositeOperation = 'source-over';
    g.font = '500 ' + Z.fs + 'px "YA Mono", monospace';
    g.textBaseline = 'top';
    var kareNo = Math.floor(t / 45);
    /* yerleşen hücrelerin altına mürekkep: Yuki mührün çizgilerinin ÖNÜNDE durur */
    for (var m = 0; m < Z.hucre.length; m++) {
      var cm = Z.hucre[m];
      /* soluk kenar hücresinde gölge de soluk — silüet kenarı basamak basamak kararmasın */
      g.fillStyle = 'rgba(5,4,9,' + (.78 * gor * Math.min(1, cm.es * 2.2)) + ')';
      if (t >= AS_BAS + (cm.y / Z.rows) * AS_YAYIL + (cm.j % AS_SEK)) g.fillRect(Z.ox + cm.x * Z.cw - .5, Z.oy + cm.y * Z.ch - .5, Z.cw + 1, Z.ch + 1);
    }
    for (var i = 0; i < Z.hucre.length; i++) {
      var c = Z.hucre[i];
      var kilit = AS_BAS + (c.y / Z.rows) * AS_YAYIL + (c.j % AS_SEK);
      if (t < kilit - 260) continue;
      var px = Z.ox + c.x * Z.cw, py = Z.oy + c.y * Z.ch;
      if (t < kilit) {
        g.fillStyle = 'rgba(' + CAM + ',' + (.5 * gor) + ')';
        g.fillText(GLIF[hash(c.j + kareNo) % GLIF.length], px, py);
      } else {
        var fl = 1 - ctx.aralik(t, kilit, kilit + 220), cr = c.renk.split(',');
        g.fillStyle = 'rgba(' + Math.round(+cr[0] + (255 - cr[0]) * fl) + ',' + Math.round(+cr[1] + (240 - cr[1]) * fl) + ',' + Math.round(+cr[2] + (205 - cr[2]) * fl) + ',' + (c.a * gor) + ')';
        g.fillText(c.c, px, py);
      }
    }
    /* gözler: yerine oturunca kendi renginde hafif ışık (mor sol · buz sağ) */
    var L = S.L;
    g.globalCompositeOperation = 'lighter';
    [[L.gozL, MOR], [L.gozR, BUZ]].forEach(function (u) {
      var gy0 = (GOZ[0][1] - KIRP[1]) / KIRP[3];
      var ga = ctx.aralik(t, AS_BAS + gy0 * AS_YAYIL + AS_SEK, AS_BAS + gy0 * AS_YAYIL + AS_SEK + 300) * gor;
      if (ga <= 0) return;
      var r = Z.ch * 1.6, gr = g.createRadialGradient(u[0][0], u[0][1], 0, u[0][0], u[0][1], r);
      gr.addColorStop(0, 'rgba(' + u[1] + ',' + (.55 * ga) + ')');
      gr.addColorStop(1, 'rgba(' + u[1] + ',0)');
      g.fillStyle = gr;
      g.fillRect(u[0][0] - r, u[0][1] - r, r * 2, r * 2);
    });
    g.restore();
  }

  function kur(ctx) {
    var r = ctx.tohum(9);
    S.zemin = ctx.tuval('ya-zemin');
    S.fig = document.createElement('canvas');
    S.figG = S.fig.getContext('2d');
    S.zerre = [];
    for (var j = 0; j < 110; j++) S.zerre.push({ a: r() * Math.PI * 2, d: .3 + r() * .9, h: r(), v: .5 + r(), renk: r() < .45 ? ALTIN : r() < .5 ? MOR : BUZ, b: .6 + r() * 1.6 });
    S.baslik = ctx.el('div', 'md-baslik');
    S.ad = ctx.el('div', 'md-ad', S.baslik);
    S.ad.textContent = 'YUKI';
    S.alt = ctx.el('div', 'md-alt', S.baslik);
    yerlesim(ctx);
    var fontlar = document.fonts ? Promise.all([
      document.fonts.load('500 12px "YA Mono"', 'ağı01'),
      document.fonts.load('700 40px "YA Fraunces"', 'YUKI'),
      document.fonts.load('italic 400 18px "YA Fraunces"', 'Mühür açıldı Çarşamba'),
      document.fonts.load('20px "YA Run"', 'ᚠᚢ'),
      document.fonts.load('20px "YA Sem"', '☽♃'),
      document.fonts.load('20px "YA Mat"', '☉')
    ]).catch(function () {}) : null;
    /* görsel zaten saydam: ctx.alfali() gerekmez. Göz kareleri gelmezse kırpma sessizce atlanır. */
    return Promise.all([ctx.gorsel(YOL(GORSEL)), fontlar,
      ctx.gorsel(YOL('../../assets/characters/yuki_muhur_poz2_goz_yari.webp')),
      ctx.gorsel(YOL('../../assets/characters/yuki_muhur_poz2_goz_kapali.webp'))
    ]).then(function (s) { S.ham = s[0]; S.img = s[0]; S.goz = [s[2], s[3]]; S.izgara = null; });
  }

  /* ── 1 · döküm satırları: yalnız gelen veriden ── */
  function satirlar(v) {
    var s = [];
    s.push([T('acilis.dokum.cekirdek-surum', 'yuki çekirdek '), v.surum || '—', T('acilis.dokum.onyukleme', ' önyükleme')]);
    s.push([T('acilis.dokum.saat', 'saat '), v.saatTam, ' · ' + v.gun + ' ' + v.tarihKisa]);
    if (v.cekirdek) s.push([T('acilis.dokum.islemci', 'işlemci '), T('acilis.dokum.is-parcacigi', '{n} iş parçacığı', { n: v.cekirdek }),
      v.cpu != null ? T('acilis.dokum.yuk', ' · yük %{n}', { n: YukiVeri.sayi(v.cpu) }) : '']);
    if (v.ram) s.push([T('acilis.dokum.bellek', 'bellek '), YukiVeri.sayi(v.ram.used_gb) + '/' + YukiVeri.sayi(v.ram.total_gb) + ' GB', '']);
    if (v.db) s.push(['pgvector ', v.db === 'ok' ? T('acilis.dokum.bagli', 'bağlı') : v.db,
      (v.db_ms != null ? ' · ' + YukiVeri.sayi(v.db_ms) + ' ms' : '') + (v.ani != null ? T('acilis.dokum.ani', ' · {n} anı', { n: YukiVeri.sayi(v.ani, 0) }) : '')]);
    if (v.model) s.push([T('acilis.dokum.model', 'dil modeli '), v.model, v.saglayici ? ' · ' + v.saglayici : '']);
    if (v.stt) s.push(['whisper stt ', v.stt === 'loaded' ? T('acilis.dokum.yuklu', 'yüklü') : v.stt, '']);
    if (v.uptime) s.push([T('acilis.dokum.uyanik', 'uyanık '), v.uptime, '']);
    if (!v.kaynak.health && !v.kaynak.system) s.push([T('acilis.dokum.cekirdek', 'çekirdek '), T('acilis.dokum.baglanti-yok', 'bağlantı yok'), T('acilis.dokum.yerel-kip', ' · yerel kip')]);
    s.push([T('acilis.dokum.kimlik', 'kimlik '), 'yuki', T('acilis.dokum.goz', ' · göz: mor / buz')]);
    s.push(['', T('acilis.dokum.muhur', 'mühür çiziliyor…'), '']);
    return s;
  }
  function satirBas(i) { return 100 + i * 100; }
  function satirKalk(i) { return 1350 + i * 55; }

  /* her karakter → parçacık (eğri yol, hedef mührün üstünde) */
  function parcaKur(ctx) {
    var L = S.L, g = S.zemin.g, fs = L.fs, lh = fs * 1.65;
    g.font = '500 ' + fs + 'px "YA Mono", monospace';
    var tum = [];
    S.satLen = [];
    S.sat.forEach(function (s, i) {
      var x = L.dx + g.measureText('[' + ('    ' + (satirBas(i) / 1000).toFixed(3)).slice(-7) + '] ').width, y = L.dy + lh * (i + 1.3), ix = 0;
      S.satLen.push((s[0] + s[1] + s[2]).length);
      [[s[0], CAM], [s[1], KEHR], [s[2], CAM]].forEach(function (p) {
        for (var k = 0; k < p[0].length; k++, ix++) {
          var c = p[0][k], cw = g.measureText(c).width;
          if (c !== ' ') tum.push({ c: c, x: x, y: y, renk: p[1], sat: i, sira: ix });
          x += cw;
        }
      });
    });
    var adim = Math.max(1, tum.length / PARCA_EN), r = ctx.tohum(31), secili = [];
    for (var f = 0; f < tum.length && secili.length < PARCA_EN; f += adim) secili.push(tum[Math.floor(f)]);
    secili.forEach(function (p, j) {
      p.kalk = satirKalk(p.sat) + Math.min(150, p.sira * 5);
      p.var = p.kalk + UCUS;
      if (j < RUN_N) { p.run = j; }
      else {
        var hal = [1, .86, .5][j % 3];
        p.aci = j * 2.39996;            /* altın açı: çember boyunca eşit dağılır */
        p.yar = hal;
      }
      p.bk = (r() - .5) * 1.2;          /* yol eğriliği */
      p.secili = true;
    });
    /* rün j: j. parçacık vardığında yanar */
    S.runVar = [];
    for (var q = 0; q < RUN_N; q++) S.runVar.push(secili[q] ? secili[q].var : 2400 + q * 20);
    S.parca = secili;
    S.secSet = new Set(secili);
    S.tumKar = tum;
  }

  function don(t, ctx) {
    return t * 0.00012 + ctx.y.girExp(ctx.aralik(t, 2900, 3200)) * 0.9 + ctx.aralik(t, 3200, 5800) * 0.5;
  }
  function hedef(p, t, ctx) {
    var L = S.L, R = L.R * (S.olcek == null ? 1 : S.olcek), d = don(p.var, ctx);
    if (p.run != null) {
      var a = -Math.PI / 2 + p.run / RUN_N * Math.PI * 2 - d * .6;
      return [L.cx + Math.cos(a) * R * .93, L.cy + Math.sin(a) * R * .93];
    }
    return [L.cx + Math.cos(p.aci + d) * R * p.yar, L.cy + Math.sin(p.aci + d) * R * p.yar];
  }

  function dokumCiz(g, t, ctx) {
    var L = S.L, fs = L.fs, lh = fs * 1.65;
    if (!S.sat && (ctx.veri.hazir || t > 650)) { S.sat = satirlar(ctx.veri); S.parca = null; }
    if (!S.sat) return;
    if (!S.parca) parcaKur(ctx);
    var genel = 1 - ctx.aralik(t, 2300, 2700);
    if (genel <= 0) return;
    g.font = '500 ' + fs + 'px "YA Mono", monospace';
    g.textBaseline = 'top';
    g.fillStyle = 'rgba(' + SOLUK + ',' + (.9 * (1 - ctx.aralik(t, 1350, 1700))) + ')';
    g.fillText('yuki:~$ dmesg --follow', L.dx, L.dy);
    /* satırlar: daktilo; kalkışta seçilmeyen karakterler söner, seçilenler parçacık olur */
    var kac = 0;
    for (var i = 0; i < S.sat.length; i++) {
      var t0 = satirBas(i);
      if (t < t0) break;
      var s = S.sat[i], tam = s[0] + s[1] + s[2];
      var n = Math.ceil(tam.length * ctx.aralik(t, t0, t0 + 140));
      var sonme = 1 - ctx.aralik(t, satirKalk(i), satirKalk(i) + 300);
      var y = L.dy + lh * (i + 1.3);
      var dmg = '[' + ('    ' + (t0 / 1000).toFixed(3)).slice(-7) + '] ';
      g.fillStyle = 'rgba(' + SOLUK + ',' + sonme + ')';
      g.fillText(dmg, L.dx, y);
      var x = L.dx + g.measureText(dmg).width, kalan = n;
      if (t < satirKalk(i)) {
        /* kalkıştan önce satır TEK PARÇA yazılır (değer okunur bütün kalsın) */
        [[s[0], CAM, .8], [s[1], KEHR, 1], [s[2], CAM, .8]].forEach(function (p) {
          if (kalan <= 0) return;
          var yz = p[0].slice(0, kalan);
          kalan -= p[0].length;
          g.fillStyle = 'rgba(' + p[1] + ',' + p[2] + ')';
          g.fillText(yz, x, y);
          x += g.measureText(yz).width;
        });
        kac++;
        continue;
      }
      [[s[0], CAM, .8], [s[1], KEHR, 1], [s[2], CAM, .8]].forEach(function (p) {
        for (var k = 0; k < p[0].length && kalan > 0; k++, kalan--) {
          var c = p[0][k], cw = g.measureText(c).width;
          var parca = S.parcaHarita && S.parcaHarita[i + ':' + Math.round(x)];
          if (!parca) {
            g.fillStyle = 'rgba(' + p[1] + ',' + (p[2] * sonme) + ')';
            g.fillText(c, x, y);
          }
          x += cw;
        }
      });
      kac++;
    }
    if (!S.parcaHarita) {
      S.parcaHarita = {};
      S.parca.forEach(function (p) { S.parcaHarita[p.sat + ':' + Math.round(p.x)] = p; });
    }
    /* seçili karakterler kalkışa kadar yerinde yazılı durur (parçacık çizer) */
  }

  function parcaCiz(g, t, ctx) {
    if (!S.parca) return;
    var L = S.L, fs = L.fs;
    g.save();
    g.textBaseline = 'top';
    for (var i = 0; i < S.parca.length; i++) {
      var p = S.parca[i];
      /* daktilo bu karaktere ulaştı mı (dokumCiz ile aynı formül) */
      var n = Math.ceil(S.satLen[p.sat] * ctx.aralik(t, satirBas(p.sat), satirBas(p.sat) + 140));
      if (n <= p.sira) continue;
      if (t >= p.var + 220) continue;
      if (t < satirKalk(p.sat)) continue;          /* satır henüz tek parça çiziliyor */
      var k = ctx.aralik(t, p.kalk, p.var);
      if (k <= 0) {
        g.font = '500 ' + fs + 'px "YA Mono", monospace';
        g.fillStyle = 'rgba(' + p.renk + ',' + (p.renk === KEHR ? 1 : .8) + ')';
        g.fillText(p.c, p.x, p.y);
        continue;
      }
      var e = ctx.y.gitCub(k), h = hedef(p, t, ctx);
      var mx = (p.x + h[0]) / 2 + (h[1] - p.y) * p.bk * .5, my = (p.y + h[1]) / 2 - (h[0] - p.x) * p.bk * .5;
      var x = (1 - e) * (1 - e) * p.x + 2 * (1 - e) * e * mx + e * e * h[0];
      var y = (1 - e) * (1 - e) * p.y + 2 * (1 - e) * e * my + e * e * h[1];
      /* renk: kaynağından (camgöbeği/kehribar) altına */
      var kr = p.renk.split(',').map(Number), ar = ALTIN.split(',').map(Number), cm = Math.min(1, k * 1.5);
      var renk = Math.round(kr[0] + (ar[0] - kr[0]) * cm) + ',' + Math.round(kr[1] + (ar[1] - kr[1]) * cm) + ',' + Math.round(kr[2] + (ar[2] - kr[2]) * cm);
      if (k < .4) {
        g.globalCompositeOperation = 'source-over';
        g.font = '500 ' + (fs * (1 - k * .8)) + 'px "YA Mono", monospace';
        g.fillStyle = 'rgba(' + renk + ',' + (1 - k * .5) + ')';
        g.fillText(p.c, x, y);
      } else {
        g.globalCompositeOperation = 'lighter';
        var ex = (1 - (e - .02)) , px2 = x - (h[0] - p.x) * .03 * ex, py2 = y - (h[1] - p.y) * .03 * ex;
        g.strokeStyle = 'rgba(' + renk + ',.55)';
        g.lineWidth = 1.2;
        g.beginPath(); g.moveTo(px2, py2); g.lineTo(x, y); g.stroke();
        g.fillStyle = 'rgba(' + renk + ',.95)';
        g.fillRect(x - 1, y - 1, 2, 2);
      }
      /* varış kıvılcımı */
      var v = ctx.aralik(t, p.var, p.var + 220);
      if (v > 0) {
        g.globalCompositeOperation = 'lighter';
        var r = 7 * (1 - v);
        var gr = g.createRadialGradient(h[0], h[1], 0, h[0], h[1], r + 1);
        gr.addColorStop(0, 'rgba(255,240,205,' + (1 - v) + ')');
        gr.addColorStop(1, 'rgba(' + ALTIN + ',0)');
        g.fillStyle = gr;
        g.fillRect(h[0] - r - 1, h[1] - r - 1, r * 2 + 2, r * 2 + 2);
      }
    }
    g.restore();
  }

  function parlakCizgi(g, renk, a, kalin, fn) {
    g.strokeStyle = 'rgba(' + renk + ',' + (a * .16) + ')';
    g.lineWidth = kalin * 5;
    fn();
    g.strokeStyle = 'rgba(' + renk + ',' + a + ')';
    g.lineWidth = kalin;
    fn();
  }

  function muhurCiz(g, t, ctx, guc) {
    var L = S.L, cx = L.cx, cy = L.cy, R = L.R * (S.olcek == null ? 1 : S.olcek);
    var d = don(t, ctx);
    g.save();
    g.globalCompositeOperation = 'lighter';
    g.lineCap = 'round';
    var kv = ctx.aralik(t, 1250, 1600) * (1 - ctx.aralik(t, 2000, 2500));
    if (kv > 0) {
      var kg = g.createRadialGradient(cx, cy, 0, cx, cy, 40);
      kg.addColorStop(0, 'rgba(' + ALTIN + ',' + kv + ')');
      kg.addColorStop(1, 'rgba(' + ALTIN + ',0)');
      g.fillStyle = kg;
      g.fillRect(cx - 40, cy - 40, 80, 80);
    }
    var p1 = ctx.y.gitCub(ctx.aralik(t, 1550, 2500));
    if (p1 > 0) {
      parlakCizgi(g, ALTIN, .9 * guc, 1.6, function () { g.beginPath(); g.arc(cx, cy, R, -Math.PI / 2 + d, -Math.PI / 2 + d + Math.PI * 2 * p1); g.stroke(); });
      parlakCizgi(g, ALTIN, .7 * guc, 1, function () { g.beginPath(); g.arc(cx, cy, R * .86, -Math.PI / 2 - d, -Math.PI / 2 - d - Math.PI * 2 * p1, true); g.stroke(); });
      parlakCizgi(g, ALTIN, .45 * guc, .8, function () { g.beginPath(); g.arc(cx, cy, R * .5, Math.PI / 2 + d * 1.5, Math.PI / 2 + d * 1.5 + Math.PI * 2 * p1); g.stroke(); });
    }
    /* rünler: kendi karakteri vardığında yanar */
    if (S.runVar) {
      var fs = Math.max(9, R * .085);
      g.font = fs + 'px "YA Run"';
      g.textAlign = 'center';
      g.textBaseline = 'middle';
      for (var i = 0; i < RUN_N; i++) {
        var gor = ctx.aralik(t, S.runVar[i], S.runVar[i] + 180);
        if (gor <= 0) continue;
        var a = -Math.PI / 2 + i / RUN_N * Math.PI * 2 - d * .6;
        g.save();
        g.translate(cx + Math.cos(a) * R * .93, cy + Math.sin(a) * R * .93);
        g.rotate(a + Math.PI / 2);
        g.fillStyle = 'rgba(' + ALTIN + ',' + (gor * .85 * guc) + ')';
        g.fillText(RUN[i % RUN.length], 0, 0);
        g.restore();
      }
    }
    var p3 = ctx.y.gitCub(ctx.aralik(t, 2200, 2900));
    if (p3 > 0) {
      [[MOR, -Math.PI / 2], [BUZ, Math.PI / 2]].forEach(function (u) {
        var pts = [];
        for (var k = 0; k < 3; k++) { var aa = u[1] + k * Math.PI * 2 / 3 + d * .4; pts.push([cx + Math.cos(aa) * R * .84, cy + Math.sin(aa) * R * .84]); }
        parlakCizgi(g, u[0], .85 * guc, 1.3, function () {
          g.beginPath();
          var top = p3 * 3;
          g.moveTo(pts[0][0], pts[0][1]);
          for (var e = 0; e < 3; e++) {
            var q = Math.min(1, Math.max(0, top - e));
            if (q <= 0) break;
            var A = pts[e], B = pts[(e + 1) % 3];
            g.lineTo(A[0] + (B[0] - A[0]) * q, A[1] + (B[1] - A[1]) * q);
          }
          g.stroke();
        });
      });
    }
    var p4 = ctx.aralik(t, 2600, 3050);
    if (p4 > 0) {
      g.textAlign = 'center';
      g.textBaseline = 'middle';
      for (var m = 0; m < 6; m++) {
        var gp = ctx.y.cikGeri(ctx.aralik(p4, m / 6 * .7, m / 6 * .7 + .3));
        if (gp <= 0) continue;
        var ab = -Math.PI / 2 + m * Math.PI / 3 + d * .4;
        g.font = (R * .09 * gp) + 'px "YA Sem", "YA Mat"';
        g.fillStyle = 'rgba(' + ALTIN + ',' + Math.min(1, gp) * guc + ')';
        g.fillText(GEZEGEN[m], cx + Math.cos(ab) * R * .68, cy + Math.sin(ab) * R * .68);
      }
    }
    g.restore();
  }

  function zeminHalkasi(g, t, ctx, guc) {
    var L = S.L, fx = L.ayak[0], fy = L.ayak[1], rx = L.figW * (ctx.dar ? .62 : .72), ry = rx * .2;
    var p = ctx.y.gitCub(ctx.aralik(t, 1800, 2700));
    if (p <= 0) return;
    var dn = t * 0.0003;
    g.save();
    g.globalCompositeOperation = 'lighter';
    [1, .78, .55].forEach(function (k, i) {
      parlakCizgi(g, i === 1 ? MOR : ALTIN, (.7 - i * .15) * guc, 1.2, function () {
        g.beginPath();
        g.ellipse(fx, fy, rx * k, ry * k, 0, dn * (i % 2 ? -1 : 1), dn * (i % 2 ? -1 : 1) + Math.PI * 2 * p);
        g.stroke();
      });
    });
    g.restore();
  }

  function sutunCiz(g, t, ctx) {
    var p = ctx.aralik(t, 3150, 4000);
    if (p <= 0 || p >= 1) return;
    var L = S.L, gen = L.figW * .5 * Math.sin(p * Math.PI) * (1 - p * .5), a = Math.sin(p * Math.PI);
    g.save();
    g.globalCompositeOperation = 'lighter';
    var gr = g.createLinearGradient(L.cx - gen, 0, L.cx + gen, 0);
    gr.addColorStop(0, 'rgba(255,240,210,0)');
    gr.addColorStop(.5, 'rgba(255,240,210,' + (.55 * a) + ')');
    gr.addColorStop(1, 'rgba(255,240,210,0)');
    g.fillStyle = gr;
    g.fillRect(L.cx - gen, 0, gen * 2, L.ayak[1]);
    g.restore();
  }

  function zerreCiz(g, t, ctx) {
    var p = ctx.aralik(t, 2700, 4300);
    if (p <= 0 || p >= 1) return;
    var L = S.L, fx = L.ayak[0], fy = L.ayak[1];
    g.save();
    g.globalCompositeOperation = 'lighter';
    for (var i = 0; i < S.zerre.length; i++) {
      var z = S.zerre[i], k = (p * z.v + z.h) % 1;
      var dn = z.a + k * 4, rr = L.figW * .6 * z.d * (1 - k * .7);
      var a = Math.sin(k * Math.PI) * Math.sin(p * Math.PI);
      g.fillStyle = 'rgba(' + z.renk + ',' + (a * .9) + ')';
      g.fillRect(fx + Math.cos(dn) * rr, fy - k * (fy - L.y) * .9 + Math.sin(dn) * rr * .2, z.b, z.b);
    }
    g.restore();
  }

  function yukiCiz(g, t, ctx) {
    var p = ctx.aralik(t, 3250, 4100);
    if (p <= 0 || !S.img) return;
    var L = S.L, fw = Math.ceil(L.figW), fh = Math.ceil(L.figH);
    if (S.fig.width !== fw || S.fig.height !== fh) { S.fig.width = fw; S.fig.height = fh; }
    var f = S.figG;
    f.globalCompositeOperation = 'source-over';
    f.clearRect(0, 0, fw, fh);
    f.drawImage(S.img, 0, 0, fw, fh);
    var kg = gozKaresi(t);
    if (kg) f.drawImage(kg, GOZ_KUTU[0] * L.s, GOZ_KUTU[1] * L.s, GOZ_KUTU[2] * L.s, GOZ_KUTU[3] * L.s);
    if (p < 1) {
      var e = ctx.y.cikCub(p), mr = Math.max(fw, fh) * 1.1 * e;
      f.globalCompositeOperation = 'destination-in';
      var gr = f.createRadialGradient(MERKEZ[0] * L.s, MERKEZ[1] * L.s, mr * .55, MERKEZ[0] * L.s, MERKEZ[1] * L.s, mr + 1);
      gr.addColorStop(0, 'rgba(0,0,0,1)');
      gr.addColorStop(1, 'rgba(0,0,0,0)');
      f.fillStyle = gr;
      f.fillRect(0, 0, fw, fh);
    }
    var cs = ctx.sure - ctx.cikis, sol = 1 - ctx.aralik(t, cs, cs + ctx.cikis * .4);
    g.save();
    g.globalAlpha = Math.min(1, p * 1.6) * sol;
    g.drawImage(S.fig, L.x, L.y);
    if (sol < 1) {
      g.globalCompositeOperation = 'lighter';
      g.globalAlpha = Math.sin((1 - sol) * Math.PI) * .7;
      g.drawImage(S.fig, L.x, L.y);
    }
    g.restore();
  }

  /* kırpma: kapanış hızlı, açılış yavaş — %0-20 yarı · %20-55 kapalı · %55-100 yarı */
  function gozKaresi(t) {
    if (!S.goz || t < KIRPMA[0] || t >= KIRPMA[0] + KIRPMA[1]) return null;
    var k = (t - KIRPMA[0]) / KIRPMA[1];
    return S.goz[k >= .2 && k < .55 ? 1 : 0];
  }

  function gozParilti(g, t, ctx) {
    var p = ctx.aralik(t, 3850, 4400);
    if (p <= 0 || p >= 1) return;
    /* boy: ışın yüzün içinde kalır (Poz 2'de yüz dar; .075 saça taşıyordu — göz tur 1) */
    var a = Math.sin(p * Math.PI), L = S.L, boy = L.figW * .045 * ctx.y.cikCub(Math.min(1, p * 1.6));
    g.save();
    g.globalCompositeOperation = 'lighter';
    [[L.gozL, MOR], [L.gozR, BUZ]].forEach(function (u) {
      var x = u[0][0], y = u[0][1];
      var gr = g.createRadialGradient(x, y, 0, x, y, boy * .35);
      gr.addColorStop(0, 'rgba(255,255,255,' + (a * .8) + ')');
      gr.addColorStop(.2, 'rgba(' + u[1] + ',' + (a * .7) + ')');
      gr.addColorStop(1, 'rgba(' + u[1] + ',0)');
      g.fillStyle = gr;
      g.fillRect(x - boy, y - boy, boy * 2, boy * 2);
      g.strokeStyle = 'rgba(' + u[1] + ',' + (a * .7) + ')';
      g.lineWidth = 1;
      g.beginPath();
      g.moveTo(x - boy * .3, y); g.lineTo(x + boy * .3, y);   /* kısa: iki gözün ışını birleşip bant olmasın, saça taşmasın (göz tur 1-2) */
      g.moveTo(x, y - boy * .45); g.lineTo(x, y + boy * .45);
      g.stroke();
    });
    g.restore();
  }

  function kare(t, ctx) {
    if (S.w !== ctx.w || S.h !== ctx.h) { yerlesim(ctx); S.w = ctx.w; S.h = ctx.h; S.parcaHarita = null; }
    var g = S.zemin.g, w = ctx.w, h = ctx.h, L = S.L, cikisBas = ctx.sure - ctx.cikis;
    g.globalCompositeOperation = 'source-over';
    g.globalAlpha = 1;
    /* zemin: döküm sırasında düz mürekkep siyahı; mühürle birlikte merkezde mor ışık */
    var mz = ctx.aralik(t, 1500, 3000);
    var bg = g.createRadialGradient(L.cx, L.cy, 0, L.cx, L.cy, Math.max(w, h) * .8);
    bg.addColorStop(0, 'rgb(' + Math.round(5 + 13 * mz) + ',' + Math.round(4 + 9 * mz) + ',' + Math.round(9 + 22 * mz) + ')');
    bg.addColorStop(1, '#050409');
    g.fillStyle = bg;
    g.fillRect(0, 0, w, h);
    /* döküm anında CRT tarama çizgileri; mühüre geçerken söner */
    var crt = .14 * (1 - ctx.aralik(t, 1800, 2600));
    if (crt > 0) {
      g.fillStyle = 'rgba(0,0,0,' + crt + ')';
      for (var sy = 0; sy < h; sy += 3) g.fillRect(0, sy, w, 1);
    }

    var guc = 1 + ctx.aralik(t, 2950, 3200) * .6 - ctx.aralik(t, 3500, 4300) * .35;
    S.olcek = 1 - ctx.y.gitCub(ctx.aralik(t, cikisBas, cikisBas + ctx.cikis * .45)) * .97;
    guc *= 1 - ctx.aralik(t, cikisBas + ctx.cikis * .3, cikisBas + ctx.cikis * .5);

    dokumCiz(g, t, ctx);
    zeminHalkasi(g, t, ctx, guc);
    muhurCiz(g, t, ctx, guc);
    asciiCiz(g, t, ctx);
    parcaCiz(g, t, ctx);
    sutunCiz(g, t, ctx);
    zerreCiz(g, t, ctx);
    yukiCiz(g, t, ctx);
    gozParilti(g, t, ctx);

    var fl = ctx.aralik(t, 3150, 3250) * (1 - ctx.aralik(t, 3250, 3650));
    if (fl > 0) {
      g.save();
      g.globalCompositeOperation = 'lighter';
      var fg = g.createRadialGradient(L.cx, L.cy, 0, L.cx, L.cy, Math.max(w, h) * .7);
      fg.addColorStop(0, 'rgba(255,236,200,' + (.85 * fl) + ')');
      fg.addColorStop(1, 'rgba(255,236,200,0)');
      g.fillStyle = fg;
      g.fillRect(0, 0, w, h);
      g.restore();
    }

    /* çıkış: mühür ışık noktasına iner, o noktadan portal açılır */
    if (t >= cikisBas) {
      var k = ctx.aralik(t, cikisBas, ctx.sure), cap = Math.hypot(w, h);
      var delik = cap * ctx.y.gitCub(ctx.aralik(k, .32, 1));
      var nokta = Math.sin(ctx.aralik(k, .2, .5) * Math.PI);
      if (nokta > 0) {
        g.save();
        g.globalCompositeOperation = 'lighter';
        var ng = g.createRadialGradient(L.cx, L.cy, 0, L.cx, L.cy, L.R * .5);
        ng.addColorStop(0, 'rgba(255,240,205,' + nokta + ')');
        ng.addColorStop(1, 'rgba(' + ALTIN + ',0)');
        g.fillStyle = ng;
        g.fillRect(L.cx - L.R, L.cy - L.R, L.R * 2, L.R * 2);
        g.restore();
      }
      if (delik > 0) {
        g.save();
        g.globalCompositeOperation = 'destination-out';
        var dg = g.createRadialGradient(L.cx, L.cy, Math.max(0, delik - 40), L.cx, L.cy, delik + 1);
        dg.addColorStop(0, 'rgba(0,0,0,1)');
        dg.addColorStop(1, 'rgba(0,0,0,0)');
        g.fillStyle = dg;
        g.beginPath(); g.arc(L.cx, L.cy, delik + 2, 0, Math.PI * 2); g.fill();
        g.restore();
        g.save();
        g.globalCompositeOperation = 'lighter';
        parlakCizgi(g, ALTIN, .9 * (1 - k), 2, function () { g.beginPath(); g.arc(L.cx, L.cy, delik, 0, Math.PI * 2); g.stroke(); });
        g.restore();
      }
    }

    /* ad: Fraunces, mühürlenir */
    var bp = ctx.aralik(t, 4000, 4650), bs = 1 - ctx.aralik(t, cikisBas, cikisBas + 250);
    S.baslik.style.opacity = String(ctx.y.cikCub(bp) * bs);
    S.ad.style.letterSpacing = (0.6 - ctx.y.cikCub(bp) * 0.38) + 'em';
    S.ad.style.filter = 'blur(' + ((1 - ctx.y.cikCub(bp)) * 10) + 'px)';
    if (!S.altYazildi && bp > 0) {
      var v = ctx.veri;
      S.alt.textContent = T('acilis.muhur-acildi', 'Mühür açıldı · {gun}, {tarih} · {saat}', { gun: v.gun, tarih: v.tarih, saat: v.saat });
      S.altYazildi = true;
    }
    S.alt.style.opacity = String(ctx.aralik(t, 4300, 4750));
  }

  YukiAcilis.sahne('muhur-dokum', { sure: 5800, cikis: 700, kur: kur, kare: kare, boyut: yerlesim });
})();
