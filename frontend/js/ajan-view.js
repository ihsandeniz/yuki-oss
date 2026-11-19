/* ════════════════════════════════════════════════════════════════════
   ajan-view.js — AJAN sekmesi

   Kişisel "Ajan Komuta Merkezi"nin (projects/ajan-komuta/ofis.js, Grimoire
   kart dili) müşteriye anlamlı karşılığı: bilgisayarda çalışan yapay zekâ
   ajanlarını desteler hâlinde izler. Kart dili aynı — deste · kart · üstüne
   gelince/uzun basınca önizleme · tıklayınca kart açılır — renkler ürünün
   token'ları (altın/camgöbeği değil). Renk rolleri (göz tur 1, MAP lane'iyle
   aynı çizgi): yeşil = canlı/çalışıyor (semantik), mor = yalnız seçili ve
   etkileşim (odak, birincil düğme), kırmızı = yalnız hata/eşik aşımı.

   DESTELER ve kaynakları (ikinci bir toplayıcı YOK — her deste mevcut ucu okur):
     EKİP      Yuki'nin uzmanları   /api/ajan/ekip (kadro) + WS olayları (canlı)
     CLAUDE    Claude Code          /api/ajan/oturumlar  (kurulu değilse deste yok)
     CODEX     Codex                /api/ajan/oturumlar  (kurulu değilse deste yok)
     RUTİNLER  zamanlı işler        /api/ajan/rutinler
     SİSTEM    bilgisayar           /api/monitor/snapshot + /processes

   🔒 Sekme yalnız İZLEYİCİ: oturumlara komut gönderme ve süreç sonlandırma
   açık kaynak sürümde yok (arka uçta uçları da yok). Arka Plan İşleri destesi de
   yok — kabuk komutu çalıştıran özellik açık kaynak sürümden çıkarıldı (2026-10-17).

   LLM'den/diskten gelen her metin (görev, rutin eylemi, uzman çıktısı)
   DOM'a esc() ya da textContent ile girer.
   ════════════════════════════════════════════════════════════════════ */
(function () {
  'use strict';

  function _ajt(anahtar, degerler) {
    return (window.YukiDil && window.YukiDil.t) ? window.YukiDil.t(anahtar, degerler) : String(anahtar);
  }

  var kok = document.getElementById('ajan-content');
  if (!kok) return;

  var BEKLEME_MS = 8000;
  var YOKLAMA_MS = 120;
  var HIZLI_MS = 4000;          // oturum · sistem
  var YAVAS_MS = 30000;         // kadro · rutin
  var ONIZLEME_GECIKME = 260;   // kişisel ofisle aynı
  var UZUN_BAS_MS = 450;

  var veri = { oturum: null, snap: null, surec: null, rutin: null, ekip: null };
  var hata = {};
  var imzalar = {};
  var KAYIT = new Map();        // kart anahtarı → {tur, o}
  var EKIP = { calismalar: [], uye: {} };
  var sonHizli = 0, sonYavas = 0, zamanlayici = null, baslatildi = false;
  var acikKart = null;          // kitapta açık kartın anahtarı

  /* ── yardımcılar ───────────────────────────────────────────────── */
  function esc(s) {
    return String(s == null ? '' : s)
      .replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;')
      .replace(/"/g, '&quot;').replace(/'/g, '&#39;');
  }
  function kirp(s, n) { s = String(s == null ? '' : s); return s.length > n ? s.slice(0, n - 1) + '…' : s; }
  function istek(url, secenek) {
    var f = (typeof window.authFetch === 'function') ? window.authFetch : window.fetch.bind(window);
    return f(url, secenek || {}).then(function (r) {
      return r.json().catch(function () { return {}; }).then(function (j) {
        if (!r.ok) { var e = new Error((j && j.detail) || ('HTTP ' + r.status)); e.kod = r.status; throw e; }
        return j;
      });
    });
  }
  /* Süre tek parça kalır: "3 sa 33 dk" sayı ile birim arasından kırılmasın
     (göz tur 1 — "3 / sa 33 dk"). Boşluklar bölünmez boşluk olur. */
  function sure(sn) {
    if (sn == null) return '—';
    sn = Math.max(0, Math.round(Number(sn) || 0));
    var m = sn < 60 ? _ajt('ajan-view.sure-sn', { n: sn })
      : sn < 3600 ? _ajt('ajan-view.sure-dk', { n: Math.floor(sn / 60) })
      : _ajt('ajan-view.sure-sa', { sa: Math.floor(sn / 3600), dk: Math.floor((sn % 3600) / 60) });
    return m.replace(/ /g, '\u00a0');
  }
  /* "… · 6 dk": ayırıcı satır başına tek başına düşmesin — önündeki boşluk bölünmez. */
  function ayirici(s) { return String(s == null ? '' : s).replace(/ · /g, '\u00a0· '); }
  function yuzde(n) { return _ajt('ajan-view.yuzde', { n: Math.round(Number(n) || 0) }); }
  /* Sözlükte anahtar yoksa t() anahtarı döndürür → yedek değer. */
  function cevirVeya(anahtar, yedek) { var m = _ajt(anahtar); return m === anahtar ? yedek : m; }
  function yerel() { return (window.YukiDil && window.YukiDil.yerel) ? window.YukiDil.yerel() : undefined; }
  function saat(iso) {
    try { return new Date(iso).toLocaleString(yerel(), { weekday: 'short', hour: '2-digit', minute: '2-digit' }); }
    catch (e) { return String(iso || '—'); }
  }
  /* "sn saniye önce" → saat:dakika (oturumun başladığı an). */
  function onceSaat(sn) {
    if (sn == null) return '';
    try { return new Date(Date.now() - Number(sn) * 1000).toLocaleTimeString(yerel(), { hour: '2-digit', minute: '2-digit' }); }
    catch (e) { return ''; }
  }
  function roma(n) { return ['', 'I', 'II', 'III', 'IV', 'V', 'VI', 'VII', 'VIII', 'IX', 'X', 'XI', 'XII'][n] || String(n); }
  function dokunmatik() { return window.matchMedia && window.matchMedia('(hover: none)').matches; }
  function hareketAz() { return window.matchMedia && window.matchMedia('(prefers-reduced-motion: reduce)').matches; }

  /* ── mühür (sigil) — tohumdan belirlenimci SVG, kartın "resmi" ──────
     Kişisel ofisin sigil fikri; renk currentColor (kart durumundan gelir). */
  function tohum(s) {
    var h = 2166136261;
    s = String(s || '');
    for (var i = 0; i < s.length; i++) { h ^= s.charCodeAt(i); h = Math.imul(h, 16777619); }
    return h >>> 0;
  }
  var KOSE = { ekip: 5, claude: 6, codex: 4, rutin: 12, sistem: 3 };
  function sigil(seed, tur) {
    var h = tohum(seed + '|' + tur);
    var n = KOSE[tur] || 5;
    var adim = 1 + (h % Math.max(1, n - 1));
    if (n % adim === 0 && adim !== 1) adim = 1;
    var r1 = 30, r2 = 12 + (h >> 5) % 10, d = [], ic = [];
    var don = ((h >> 9) % 360) * Math.PI / 180;
    for (var i = 0; i < n; i++) {
      var a = don + i * 2 * Math.PI / n;
      d.push([50 + r1 * Math.cos(a), 50 + r1 * Math.sin(a)]);
      ic.push([50 + r2 * Math.cos(a + Math.PI / n), 50 + r2 * Math.sin(a + Math.PI / n)]);
    }
    var yol = '', j = 0;
    for (var k = 0; k <= n; k++) { var p = d[j % n]; yol += (k ? 'L' : 'M') + p[0].toFixed(1) + ' ' + p[1].toFixed(1); j += adim; }
    var icYol = ic.map(function (p, x) { return (x ? 'L' : 'M') + p[0].toFixed(1) + ' ' + p[1].toFixed(1); }).join('') + 'Z';
    var tik = '';
    if (tur === 'rutin') {
      for (var t = 0; t < 12; t++) {
        var ta = t * Math.PI / 6;
        tik += '<path d="M' + (50 + 40 * Math.cos(ta)).toFixed(1) + ' ' + (50 + 40 * Math.sin(ta)).toFixed(1) +
          'L' + (50 + 44 * Math.cos(ta)).toFixed(1) + ' ' + (50 + 44 * Math.sin(ta)).toFixed(1) + '"/>';
      }
    }
    return '<svg viewBox="0 0 100 100" aria-hidden="true" focusable="false">' +
      '<circle cx="50" cy="50" r="44" class="s-halka"/>' + tik +
      '<path d="' + yol + '" class="s-yildiz"/>' +
      '<path d="' + icYol + '" class="s-ic"/>' +
      '<circle cx="50" cy="50" r="' + (3 + (h >> 13) % 4) + '" class="s-goz"/></svg>';
  }

  /* ── deste iskeleti (bir kez) ─────────────────────────────────── */
  var IKON = {
    ekip: '<path d="M7 9a3 3 0 1 0 0-6 3 3 0 0 0 0 6zM17 11a2.5 2.5 0 1 0 0-5 2.5 2.5 0 0 0 0 5zM1.5 20c0-3 2.5-5.5 5.5-5.5s5.5 2.5 5.5 5.5M13 19.5c.3-2.4 2-4.2 4-4.2 2.3 0 4 1.9 4 4.7"/>',
    claude: '<path d="M4 17l6-6-6-6M12 19h8"/>',
    codex: '<path d="M8 6l-6 6 6 6M16 6l6 6-6 6"/>',
    rutin: '<circle cx="12" cy="12" r="9"/><path d="M12 7v5l3 2"/>',
    sistem: '<rect x="3" y="4" width="18" height="12" rx="2"/><path d="M8 20h8M12 16v4"/>'
  };
  function ikon(ad) {
    return '<svg viewBox="0 0 24 24" width="18" height="18" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">' + IKON[ad] + '</svg>';
  }
  var DESTELER = [
    { id: 'ekip', ikon: 'ekip', ad: 'ajan-view.deste.ekip', alt: 'ajan-view.deste.ekip-alt' },
    { id: 'claude', ikon: 'claude', ad: 'ajan-view.deste.claude', alt: 'ajan-view.deste.claude-alt' },
    { id: 'codex', ikon: 'codex', ad: 'ajan-view.deste.codex', alt: 'ajan-view.deste.codex-alt' },
    { id: 'rutin', ikon: 'rutin', ad: 'ajan-view.deste.rutin', alt: 'ajan-view.deste.rutin-alt' },
    { id: 'sistem', ikon: 'sistem', ad: 'ajan-view.deste.sistem', alt: 'ajan-view.deste.sistem-alt' }
  ];

  function iskeletKur() {
    kok.innerHTML =
      '<div class="aj-sar">' +
        '<header class="aj-bas">' +
          '<div class="aj-bas-metin"><div class="sekme-baslik"><span class="sekme-baslik__etiket">YUKI</span>' +
          '<h2 class="aj-baslik sekme-baslik__ad" data-i="ajan-view.baslik"></h2></div>' +
          '<p class="aj-alt" data-i="ajan-view.alt"></p></div>' +
          '<div class="aj-ozet" id="aj-ozet" aria-live="polite"></div>' +
        '</header>' +
        '<div class="aj-desteler">' +
          DESTELER.map(function (d) {
            return '<section class="aj-deste aj-deste-' + d.id + '" id="aj-d-' + d.id + '" aria-labelledby="aj-h-' + d.id + '"' +
              (d.id === 'claude' || d.id === 'codex' ? ' hidden' : '') + '>' +
              '<header class="aj-deste-bas">' + ikon(d.ikon) +
                '<h3 id="aj-h-' + d.id + '" data-i="' + d.ad + '"></h3>' +
                '<em data-i="' + d.alt + '"></em>' +
                '<span class="aj-deste-not" id="aj-n-' + d.id + '"></span>' +
                '<span class="aj-sayi" id="aj-s-' + d.id + '">0</span>' +
              '</header>' +
              '<div class="aj-serit" id="aj-l-' + d.id + '"></div>' +
            '</section>';
          }).join('') +
        '</div>' +
      '</div>' +
      '<div class="aj-onizleme" id="aj-onizleme" role="tooltip" hidden></div>' +
      '<div class="aj-perde" id="aj-perde" hidden></div>' +
      '<aside class="aj-kitap" id="aj-kitap" role="dialog" aria-modal="false" aria-labelledby="aj-kitap-ad" hidden></aside>';
    etiketleriYaz();
  }
  function etiketleriYaz() {
    kok.querySelectorAll('[data-i]').forEach(function (el) { el.textContent = _ajt(el.getAttribute('data-i')); });
  }

  /* ── kart modeli ──────────────────────────────────────────────── */
  var DURUM_SINIF = {
    calisiyor: 'canli', bekliyor: 'bekliyor', bitti: 'bitti', bosta: 'bitti',
    ok: 'bitti', hata: 'hata', kota: 'hata', timeout: 'hata', iptal: 'bitti',
    normal: 'olcu', yuksek: 'hata'       // ölçü kartları — durum değil eşik
  };
  var ESIK = 90;                         // ölçü kartı bu yüzdede kırmızıya döner (çubukla aynı)
  function durumEt(d) { return _ajt('ajan-view.durum.' + (d || 'bilinmiyor')); }

  function kartHtml(o) {
    var olcu = '', kritik = false;
    if (o.olcu) {
      var w = Math.max(0, Math.min(100, Number(o.olcu.oran) || 0));
      kritik = o.tur === 'olcu' && w >= ESIK;
      olcu = '<div class="aj-olcu' + (kritik ? ' kritik' : '') + '"><div class="aj-olcu-bas"><span>' + esc(o.olcu.etiket) +
        '</span><b>' + esc(o.olcu.sag || '') + '</b></div><div class="aj-olcu-ray"><i style="width:' + w.toFixed(1) + '%"></i></div></div>';
    }
    /* Ölçü/süreç kartında "bekliyor" gibi bir durum anlamsız (göz tur 1) — hap yerine değer. */
    var sag = o.olcu
      ? '<b class="aj-k-deger">' + esc(o.olcu.deger) + '</b>'
      : '<span class="aj-k-durum"><i class="aj-nabiz" aria-hidden="true"></i>' + esc(durumEt(o.durum)) + '</span>';
    return '<article class="aj-kart d-' + (DURUM_SINIF[o.durum] || 'bitti') + (o.kucuk ? ' kucuk' : '') + '" data-k="' + esc(o.k) +
      '" tabindex="0" role="button" aria-haspopup="dialog" aria-label="' + esc(o.ad + ' — ' + (o.olcu ? o.olcu.deger : durumEt(o.durum))) + '">' +
      '<div class="aj-k-ust"><span class="aj-k-no">' + esc(o.no) + '</span>' + sag + '</div>' +
      '<div class="aj-k-sigil">' + sigil(o.seed || o.k, o.sigil) + '</div>' +
      '<div class="aj-k-ad" title="' + esc(o.ad) + '">' + esc(o.ad) + '</div>' +
      '<div class="aj-k-kimlik" title="' + esc(o.kimlikUzun || o.kimlik || '') + '">' + esc(o.kimlik || '') + '</div>' +
      (o.metin ? '<p class="aj-k-metin">' + esc(ayirici(kirp(o.metin, 90))) + '</p>' : '<p class="aj-k-metin bos"></p>') +
      olcu + '</article>';
  }

  /* Kartın ayrıntı satırları — önizleme ve kitap aynı kaynaktan çizer. */
  function satir(et, deger) {
    /* Noktasız etiket (CPU) çevrilmez — ölçü birimi, her dilde aynı. */
    return '<div class="aj-kv"><span>' + esc(et.indexOf('.') > 0 ? _ajt(et) : et) + '</span><b>' + esc(deger == null || deger === '' ? '—' : deger) + '</b></div>';
  }

  /* ── deste modelleri ──────────────────────────────────────────── */
  function ekipKartlari() {
    var e = veri.ekip;
    if (!e) return null;
    return (e.uzmanlar || []).map(function (u, i) {
      var s = EKIP.uye[u.name] || {};
      var o = {
        /* Rol adı sözlükten (EN'de "Cyber-Mage"); sözlükte yoksa backend'in Türkçe unvanı. */
        k: 'ekip:' + u.name, tur: 'ekip', no: roma(i + 1), ad: u.label || u.name,
        kimlik: cevirVeya('karakter.' + u.name + '.unvan', u.title || ''),
        durum: s.durum || 'bosta', metin: s.subtask || _ajt('ajan-view.ekip.bosta-metin'),
        seed: 'persona-' + u.name, sigil: 'ekip', ham: u, son: s
      };
      return o;
    });
  }
  /* Aynı klasörde birden çok oturum (göz tur 1: 12 kartın 8'i aynı klasör):
     ada sıra eklenir — canlılar başlangıca göre (en eski 1), sonra kapananlar.
     Sıra konuşma içeriğinden değil yalnız zamandan gelir. */
  function siraNo(liste) {
    var gruplar = {}, sira = {};
    liste.forEach(function (s) { (gruplar[s.proje || '—'] = gruplar[s.proje || '—'] || []).push(s); });
    Object.keys(gruplar).forEach(function (ad) {
      var g = gruplar[ad];
      if (g.length < 2) return;
      g.slice().sort(function (a, b) {
        var ac = a.durum === 'bitti', bc = b.durum === 'bitti';
        if (ac !== bc) return ac ? 1 : -1;
        var f = !ac ? (b.sure_sn || 0) - (a.sure_sn || 0) : (b.sessiz_sn || 0) - (a.sessiz_sn || 0);
        return f || (a.id < b.id ? -1 : 1);     // aynı anda açılanlar: kimliğe göre, sıra yenilemede oynamasın
      }).forEach(function (s, i) { sira[s.id] = i + 1; });
    });
    return sira;
  }
  function oturumKartlari(tur) {
    var d = veri.oturum && veri.oturum[tur];
    if (!d || !d.kurulu) return null;
    var sira = siraNo(d.oturumlar || []);
    return (d.oturumlar || []).map(function (s, i) {
      var bas = s.durum !== 'bitti' ? onceSaat(s.sure_sn) : '';
      var kimlik = [bas, s.dal].filter(Boolean).join(' · ') || s.id;
      return {
        k: tur + ':' + s.id, tur: tur, no: roma(i + 1),
        ad: (s.proje || '—') + (sira[s.id] ? '\u00a0·\u00a0' + sira[s.id] : ''),
        kimlik: kimlik + (s.otomatik ? ' · ' + _ajt('ajan-view.otomatik') : ''),
        kimlikUzun: [bas && _ajt('ajan-view.et.basladi') + ': ' + bas, s.dal && _ajt('ajan-view.et.dal') + ': ' + s.dal,
          _ajt('ajan-view.et.oturum') + ': ' + s.id].filter(Boolean).join(' · '),
        durum: s.durum,
        metin: s.durum === 'calisiyor' ? _ajt('ajan-view.oturum.suruyor', { sure: sure(s.sure_sn) })
          : s.durum === 'bekliyor' ? _ajt('ajan-view.oturum.bekliyor', { sure: sure(s.sessiz_sn) })
          : _ajt('ajan-view.oturum.bitti', { sure: sure(s.sessiz_sn) }),
        seed: s.id, sigil: tur, ham: s
      };
    });
  }
  function rutinKartlari() {
    var r = veri.rutin;
    if (!r) return null;
    return (r.rutinler || []).map(function (x, i) {
      return {
        k: 'rutin:' + x.id, tur: 'rutin', no: roma(i + 1), ad: x.ad, kimlik: x.zaman,
        durum: x.etkin ? (x.sonraki ? 'bekliyor' : 'bitti') : 'bitti',
        metin: x.sonraki ? _ajt('ajan-view.rutin.sonraki', { zaman: saat(x.sonraki) }) : _ajt('ajan-view.rutin.zamanlanmadi'),
        seed: x.id, sigil: 'rutin', ham: x
      };
    });
  }
  function sistemKartlari() {
    var s = veri.snap;
    if (!s) return null;
    var out = [];
    var cpu = s.cpu || {}, mem = s.mem || {}, gpu = s.gpu_nvidia || s.gpu_amd, disk = (s.disks || [])[0];
    function esik(oran) { return (oran || 0) >= ESIK ? 'yuksek' : 'normal'; }
    var esikMetni = _ajt('ajan-view.sistem.esik', { n: yuzde(ESIK) });
    out.push({ k: 'sistem:cpu', tur: 'olcu', no: 'CPU', ad: _ajt('ajan-view.sistem.islemci'),
      kimlik: cpu.temp_c != null ? Math.round(cpu.temp_c) + '°C' : '', durum: esik(cpu.total),
      olcu: { oran: cpu.total, etiket: _ajt('ajan-view.sistem.yuk'), deger: yuzde(cpu.total), sag: esikMetni },
      seed: 'cpu', sigil: 'sistem', kucuk: true, ham: { cpu: cpu, makine: s.makine } });
    out.push({ k: 'sistem:ram', tur: 'olcu', no: 'RAM', ad: _ajt('ajan-view.sistem.bellek'),
      kimlik: (mem.used_gb || 0).toFixed(1) + ' / ' + Math.round(mem.total_gb || 0) + '\u00a0GB', durum: esik(mem.percent),
      olcu: { oran: mem.percent, etiket: _ajt('ajan-view.sistem.dolu'), deger: yuzde(mem.percent), sag: esikMetni },
      seed: 'ram', sigil: 'sistem', kucuk: true, ham: { mem: mem } });
    if (gpu) {
      var gy = gpu.util != null ? gpu.util : gpu.busy;
      out.push({ k: 'sistem:gpu', tur: 'olcu', no: 'GPU', ad: kirp(gpu.name || 'GPU', 28),
        kimlik: gpu.vram_total_mb ? Math.round(gpu.vram_used_mb / 1024 * 10) / 10 + ' / ' + Math.round(gpu.vram_total_mb / 1024) + '\u00a0GB' : '',
        durum: esik(gy),
        olcu: { oran: gy, etiket: _ajt('ajan-view.sistem.yuk'), deger: yuzde(gy), sag: esikMetni },
        seed: 'gpu', sigil: 'sistem', kucuk: true, ham: { gpu: gpu } });
    }
    if (disk) {
      out.push({ k: 'sistem:disk', tur: 'olcu', no: _ajt('ajan-view.sistem.no-disk'), ad: disk.mount || '/',
        kimlik: Math.round(disk.used_gb || 0) + ' / ' + Math.round(disk.total_gb || 0) + '\u00a0GB', durum: esik(disk.percent),
        olcu: { oran: disk.percent, etiket: _ajt('ajan-view.sistem.dolu'), deger: yuzde(disk.percent), sag: esikMetni },
        seed: 'disk', sigil: 'sistem', kucuk: true, ham: { disk: disk } });
    }
    (veri.surec || []).slice(0, 5).forEach(function (p, i) {
      /* Süreç adı kartın başlığı (iki satıra sığar); köşede sıra değil "SÜREÇ" + değer. */
      out.push({ k: 'surec:' + p.pid, tur: 'surec', no: _ajt('ajan-view.sistem.no-surec') + ' ' + roma(i + 1), ad: p.name || String(p.pid),
        kimlik: 'pid ' + p.pid, durum: 'normal',
        olcu: { oran: Math.min(100, p.cpu || 0), etiket: 'CPU', deger: yuzde(p.cpu), sag: '' },
        metin: Math.round(p.mem_mb || 0) + '\u00a0MB', seed: p.name, sigil: 'sistem', kucuk: true, ham: p });
    });
    return out;
  }

  /* ── çizim ────────────────────────────────────────────────────── */
  function desteYaz(id, kartlar, bosAnahtar, not) {
    var bolum = document.getElementById('aj-d-' + id);
    var kap = document.getElementById('aj-l-' + id);
    var sayi = document.getElementById('aj-s-' + id);
    var notEl = document.getElementById('aj-n-' + id);
    if (!bolum || !kap) return;
    if (kartlar === null && !hata[id]) {           // henüz okunmadı → iskelet
      if (!kap.firstChild) kap.innerHTML = '<div class="aj-iskelet"></div><div class="aj-iskelet"></div><div class="aj-iskelet"></div>';
      return;
    }
    if (notEl) notEl.textContent = not || '';
    var liste = kartlar || [];
    liste.forEach(function (o) { KAYIT.set(o.k, o); });
    var imza = hata[id] ? 'hata|' + hata[id] : liste.map(function (o) {
      return [o.k, o.durum, o.ad, o.kimlik, o.metin, o.olcu ? o.olcu.deger : ''].join('|');
    }).join('~') + '#' + (bosAnahtar || '');
    if (sayi) sayi.textContent = String(liste.filter(function (o) { return o.tur === 'olcu' ? false : true; }).length);
    if (imzalar[id] === imza) return;
    imzalar[id] = imza;
    if (hata[id]) {
      kap.innerHTML = '<p class="aj-bos aj-hata-metin">' + esc(_ajt('ajan-view.okunamadi', { sebep: hata[id] })) + '</p>';
      return;
    }
    kap.innerHTML = liste.length ? liste.map(kartHtml).join('')
      : '<p class="aj-bos">' + esc(_ajt(bosAnahtar)) + '</p>';
  }

  function ozetYaz() {
    var el = document.getElementById('aj-ozet');
    if (!el) return;
    var calisan = 0, bekleyen = 0;
    KAYIT.forEach(function (o) {
      if (o.tur === 'olcu' || o.tur === 'surec') return;
      if (o.durum === 'calisiyor') calisan++;
      else if (o.durum === 'bekliyor' && o.tur !== 'rutin') bekleyen++;
    });
    /* Sıfır sayaç gösterilmez (göz tur 1: "0 çalışıyor" bilgi değil gürültü). */
    el.innerHTML = (calisan ? '<span class="aj-hap canli"><i class="aj-nabiz"></i>' + esc(_ajt('ajan-view.ozet.calisan', { n: calisan })) + '</span>' : '') +
      (bekleyen ? '<span class="aj-hap">' + esc(_ajt('ajan-view.ozet.bekleyen', { n: bekleyen })) + '</span>' : '');
  }

  function ciz() {
    KAYIT.clear();
    /* Not satırı: SÜREN çalışma öncelikli (tekli delege meclisin üstüne binince
       meclis kaybolmasın), hiçbiri sürmüyorsa en yenisi. */
    var e = veri.ekip;
    var suren = EKIP.calismalar.filter(function (c) { return !c.bitis; });
    var son = suren.filter(function (c) { return c.kip === 'meclis'; })[0] || suren[0] || EKIP.calismalar[0];
    var ekipNot = son ? _ajt(son.bitis ? 'ajan-view.ekip.son' : 'ajan-view.ekip.suruyor', { hedef: kirp(son.goal, 60) }) : '';
    desteYaz('ekip', ekipKartlari(), e && !e.uzman_acik ? 'ajan-view.ekip.kapali' : 'ajan-view.ekip.bos', ekipNot);

    ['claude', 'codex'].forEach(function (tur) {
      var bolum = document.getElementById('aj-d-' + tur);
      var d = veri.oturum && veri.oturum[tur];
      if (bolum) bolum.hidden = !(d && d.kurulu);      // kurulu değilse deste HİÇ görünmez
      desteYaz(tur, oturumKartlari(tur), 'ajan-view.' + tur + '.bos');
    });
    desteYaz('rutin', rutinKartlari(), veri.rutin && !veri.rutin.acik ? 'ajan-view.rutin.kapali' : 'ajan-view.rutin.bos');
    desteYaz('sistem', sistemKartlari(), 'ajan-view.sistem.bos');
    ozetYaz();
    if (acikKart) kitapTazele();
    if (_ozA) onizlemeTazele();
  }

  /* ── veri ─────────────────────────────────────────────────────── */
  function oku(ad, url, donustur) {
    return istek(url).then(function (d) { veri[ad] = donustur ? donustur(d) : d; delete hata[ad]; })
      .catch(function (e) { hata[ad] = String(e.message || e); });
  }
  function hizliTur() {
    sonHizli = Date.now();
    return Promise.all([
      oku('oturum', '/api/ajan/oturumlar'),
      oku('snap', '/api/monitor/snapshot'),
      oku('surec', '/api/monitor/processes?sort=cpu&limit=6', function (d) { return (d && d.processes) || []; })
    ]).then(function () {
      hata.claude = hata.oturum; hata.codex = hata.oturum; hata.sistem = hata.snap;
      ciz();
    });
  }
  function yavasTur() {
    sonYavas = Date.now();
    return Promise.all([oku('ekip', '/api/ajan/ekip'), oku('rutin', '/api/ajan/rutinler')]).then(ciz);
  }
  function gorunur() {
    if (document.hidden) return false;
    var el = document.getElementById('tab-ajan');
    return !!el && !el.hidden;
  }
  function dongu() {
    if (zamanlayici) clearInterval(zamanlayici);
    zamanlayici = setInterval(function () {
      if (!gorunur()) return;
      if (Date.now() - sonHizli >= HIZLI_MS - 50) hizliTur();
      if (Date.now() - sonYavas >= YAVAS_MS - 50) yavasTur();
    }, 1000);
    if (gorunur()) { hizliTur(); yavasTur(); }
  }

  /* ── ekip — canlı olaylar (core.js `yuki:ekip` köprüsü, kaynak WS) ── */
  function calisma(id) {
    for (var i = 0; i < EKIP.calismalar.length; i++) if (EKIP.calismalar[i].run_id === id) return EKIP.calismalar[i];
    return null;
  }
  document.addEventListener('yuki:ekip', function (ev) {
    var d = ev.detail || {};
    var t = Date.now();
    if (d.type === 'team_start') {
      EKIP.calismalar.unshift({ run_id: d.run_id, kip: d.kip, goal: d.goal || '', plan: d.plan || [], baslangic: t, bitis: null, durum: null });
      EKIP.calismalar = EKIP.calismalar.slice(0, 6);
      (d.plan || []).forEach(function (p) {
        EKIP.uye[p.persona] = { durum: 'bekliyor', subtask: p.subtask, run_id: d.run_id, t: t, result: null };
      });
    } else if (d.type === 'team_end') {
      var c = calisma(d.run_id);
      if (c) { c.bitis = t; c.durum = d.durum; }
    } else if (d.persona) {
      var u = EKIP.uye[d.persona] || (EKIP.uye[d.persona] = {});
      if (d.run_id && u.run_id && u.run_id !== d.run_id && d.type !== 'companion_active') return;  // eski çalışmanın geç olayı
      u.run_id = d.run_id || u.run_id;
      u.t = t;
      if (d.type === 'companion_active') { u.durum = 'calisiyor'; u.subtask = d.subtask || u.subtask; u.result = null; }
      else if (d.type === 'companion_done') { u.durum = d.durum || 'ok'; }
      else if (d.type === 'companion_result') { u.result = d.result || ''; u.subtask = d.subtask || u.subtask; u.durum = d.durum || u.durum; }
    }
    if (baslatildi) ciz();
  });

  /* ── önizleme (üstüne gel 260 ms · uzun bas 450 ms) ───────────────── */
  var _ozA = null, _ozEl = null, _ozZaman = null, _ozKapatZ = null, _uzunBasildi = false, _basZaman = null;

  /* Önizleme KISA özet (2-3 satır, göz tur 1: "önizleme açılan panelin aynısı"),
     kitap TAM döküm. Komut metni satır değil ayrı blok (kitapta, sola yaslı). */
  function ayrintiSatirlari(o, kisa) {
    var s = o.ham || {}, h = [];
    if (o.tur === 'claude' || o.tur === 'codex') {
      var bas = s.durum !== 'bitti' ? onceSaat(s.sure_sn) : '';
      if (kisa) {
        if (bas) h.push(satir('ajan-view.et.basladi', bas));
        h.push(satir('ajan-view.et.sessiz', sure(s.sessiz_sn)));
        if (s.dal) h.push(satir('ajan-view.et.dal', s.dal));
      } else {
        h.push(satir('ajan-view.et.oturum', s.id), satir('ajan-view.et.klasor', s.proje));
        if (s.dal) h.push(satir('ajan-view.et.dal', s.dal));
        if (bas) h.push(satir('ajan-view.et.basladi', bas));
        h.push(satir('ajan-view.et.sure', sure(s.sure_sn)), satir('ajan-view.et.sessiz', sure(s.sessiz_sn)));
        if (o.tur === 'claude') h.push(satir('ajan-view.et.yuzey', s.yuzey ? 'tmux' : _ajt('ajan-view.yuzey-yok')));
      }
    } else if (o.tur === 'ekip') {
      var son = o.son || {};
      if (!kisa) h.push(satir('ajan-view.et.rol', o.kimlik), satir('ajan-view.et.durum', durumEt(o.durum)));
      if (son.subtask) h.push(satir('ajan-view.et.gorev', kirp(son.subtask, kisa ? 90 : 140)));
      else if (kisa) h.push(satir('ajan-view.et.rol', o.kimlik));
    } else if (o.tur === 'rutin') {
      h.push(satir('ajan-view.et.sonraki', s.sonraki ? saat(s.sonraki) : _ajt('ajan-view.rutin.zamanlanmadi')));
      if (!kisa) h.push(satir('ajan-view.et.zaman', s.zaman), satir('ajan-view.et.tur', _ajt('ajan-view.rutin.tur.' + (s.tur || 'message'))));
    } else if (o.tur === 'surec') {
      h.push(satir('CPU', yuzde(s.cpu)), satir('ajan-view.et.bellek', Math.round(s.mem_mb || 0) + '\u00a0MB'));
      if (!kisa) h.push(satir('ajan-view.et.pid', String(s.pid)), satir('ajan-view.et.calisma', sure(s.uptime_s)));
    } else if (o.tur === 'olcu') {
      h.push(satir('ajan-view.et.deger', o.olcu ? o.olcu.deger : ''));
      if (!kisa) h.push(satir('ajan-view.et.ayrinti', o.kimlik), satir('ajan-view.et.esik', yuzde(ESIK)));
    }
    return h.join('');
  }
  function onizlemeHtml(o) {
    return '<div class="aj-oz-bas d-' + (DURUM_SINIF[o.durum] || 'bitti') + '"><div class="aj-oz-sigil">' + sigil(o.seed || o.k, o.sigil) + '</div>' +
      '<div><h4>' + esc(o.ad) + '</h4><span class="aj-rozet">' + esc(o.olcu ? o.olcu.deger : durumEt(o.durum)) + '</span></div></div>' +
      ayrintiSatirlari(o, true) +
      '<p class="aj-oz-ipucu">' + esc(_ajt(dokunmatik() ? 'ajan-view.ipucu-dokun' : 'ajan-view.ipucu-tikla')) + '</p>';
  }
  function onizlemeAc(el, k) {
    var o = KAYIT.get(k); if (!o) return;
    clearTimeout(_ozKapatZ);
    var p = document.getElementById('aj-onizleme');
    _ozA = k; _ozEl = el;
    p.innerHTML = onizlemeHtml(o);
    p.hidden = false;
    onizlemeKonumla();
    el.classList.add('vurgu');
  }
  function onizlemeKonumla() {
    var p = document.getElementById('aj-onizleme');
    if (!_ozEl || !p) return;
    var r = _ozEl.getBoundingClientRect(), w = p.offsetWidth || 300, h = p.offsetHeight;
    var x = r.right + 12;
    if (x + w > innerWidth - 12) x = r.left - w - 12;
    if (x < 12) x = Math.max(12, Math.min(innerWidth - w - 12, r.left));
    var y = Math.min(Math.max(12, r.top), innerHeight - h - 12);
    if (dokunmatik()) y = (innerHeight - r.bottom - 12 >= h) ? r.bottom + 8 : Math.max(12, r.top - h - 8);
    p.style.left = x + 'px';
    p.style.top = Math.max(12, y) + 'px';
  }
  function onizlemeTazele() {
    var o = KAYIT.get(_ozA);
    if (!o) return onizlemeKapat();
    var el = kok.querySelector('.aj-kart[data-k="' + CSS.escape(_ozA) + '"]');
    if (el) { _ozEl = el; el.classList.add('vurgu'); }
    var p = document.getElementById('aj-onizleme');
    var h = onizlemeHtml(o);
    if (p._html !== h) { p.innerHTML = h; p._html = h; }
  }
  function onizlemeKapat() {
    clearTimeout(_ozZaman); clearTimeout(_ozKapatZ);
    var p = document.getElementById('aj-onizleme');
    if (p) p.hidden = true;
    kok.querySelectorAll('.aj-kart.vurgu').forEach(function (e) { e.classList.remove('vurgu'); });
    _ozA = null; _ozEl = null;
  }

  /* ── kitap (kart açılır) ──────────────────────────────────────── */
  function kitapAc(k) {
    var o = KAYIT.get(k); if (!o) return;
    onizlemeKapat();
    acikKart = k;
    var kitap = document.getElementById('aj-kitap');
    kitap._son = null;
    kitapTazele(true);
    kitap.hidden = false;
    document.getElementById('aj-perde').hidden = false;
    document.body.classList.add('aj-kitap-acik');     // ☰ perdenin altına iner (ajan.css)
    var kapat = kitap.querySelector('.aj-kitap-kapat');
    if (kapat) kapat.focus({ preventScroll: true });
  }
  function kitapKapat() {
    var kitap = document.getElementById('aj-kitap');
    if (!kitap || kitap.hidden) return;
    kitap.hidden = true;
    document.getElementById('aj-perde').hidden = true;
    document.body.classList.remove('aj-kitap-acik');
    var k = acikKart; acikKart = null;
    var el = k && kok.querySelector('.aj-kart[data-k="' + CSS.escape(k) + '"]');
    if (el) el.focus({ preventScroll: true });
  }

  function eylemAlani(o) {
    var s = o.ham || {};
    if (o.tur === 'ekip' && o.son && o.son.result) {
      return '<div class="aj-cikti-baslik">' + esc(_ajt('ajan-view.ekip.ham-cikti')) + '</div><pre class="aj-cikti ekip"></pre>';
    }
    if (o.tur === 'rutin' && s.eylem) {
      return '<div class="aj-cikti-baslik">' + esc(_ajt('ajan-view.rutin.eylem')) + '</div><pre class="aj-cikti rutin"></pre>';
    }
    return '';
  }
  function gecmisAlani(o) {
    if (o.tur !== 'ekip' || !EKIP.calismalar.length) return '';
    var ilgili = EKIP.calismalar.filter(function (c) { return (c.plan || []).some(function (p) { return p.persona === o.ham.name; }); });
    if (!ilgili.length) return '';
    return '<div class="aj-cikti-baslik">' + esc(_ajt('ajan-view.ekip.son-calismalar')) + '</div><ul class="aj-gecmis">' +
      ilgili.map(function (c) {
        return '<li><span>' + esc(kirp(c.goal, 80)) + '</span><b>' + esc(_ajt(c.bitis ? 'ajan-view.durum.' + (c.durum || 'ok') : 'ajan-view.durum.calisiyor')) + '</b></li>';
      }).join('') + '</ul>';
  }
  function kitapTazele(ilk) {
    var o = KAYIT.get(acikKart);
    var kitap = document.getElementById('aj-kitap');
    if (!kitap) return;
    if (!o) {   // kart kayboldu (oturum kapandı)
      if (!kitap.hidden) {
        var gov = kitap.querySelector('.aj-kitap-govde');
        if (gov && !gov.querySelector('.aj-kayip')) gov.insertAdjacentHTML('afterbegin', '<p class="aj-not aj-kayip">' + esc(_ajt('ajan-view.kart-kayboldu')) + '</p>');
      }
      return;
    }
    // Çıktı açıkken yeniden çizme — yalnız bilgi satırları tazelenir.
    var imza = [o.k, o.durum, o.ad, o.kimlik, o.metin].join('|');
    var bilgi = kitap.querySelector('.aj-kitap-bilgi');
    if (!ilk && kitap._son === imza) return;
    if (!ilk && bilgi && kitap.querySelector('.aj-cikti:not([hidden])')) {
      bilgi.innerHTML = ayrintiSatirlari(o);
      var rz = kitap.querySelector('.aj-kitap-bas .aj-rozet');
      if (rz) rz.textContent = o.olcu ? o.olcu.deger : durumEt(o.durum);
      kitap._son = imza;
      return;
    }
    kitap._son = imza;
    kitap.innerHTML =
      '<div class="aj-kitap-bas d-' + (DURUM_SINIF[o.durum] || 'bitti') + '">' +
        '<div class="aj-oz-sigil">' + sigil(o.seed || o.k, o.sigil) + '</div>' +
        '<div class="aj-kitap-ad"><h4 id="aj-kitap-ad">' + esc(o.ad) + '</h4><span class="aj-rozet">' + esc(o.olcu ? o.olcu.deger : durumEt(o.durum)) + '</span></div>' +
        '<button type="button" class="aj-kitap-kapat" aria-label="' + esc(_ajt('ajan-view.kapat')) + '">' +
          '<svg viewBox="0 0 16 16" width="16" height="16" fill="none" stroke="currentColor" stroke-width="1.6" stroke-linecap="round" aria-hidden="true"><path d="M4 4l8 8M12 4l-8 8"/></svg></button>' +
      '</div>' +
      '<div class="aj-kitap-govde">' +
        '<div class="aj-kitap-bilgi">' + ayrintiSatirlari(o) + '</div>' +
        eylemAlani(o) + gecmisAlani(o) +
      '</div>';
    var ham = kitap.querySelector('.aj-cikti.ekip');
    if (ham) ham.textContent = o.son.result;        // uzman çıktısı MODEL ürünüdür — textContent
    var rt = kitap.querySelector('.aj-cikti.rutin');
    if (rt) rt.textContent = o.ham.eylem;
  }

  /* ── eylemler ─────────────────────────────────────────────────── */
  kok.addEventListener('click', function (ev) {
    var t = ev.target;
    if (!t.closest) return;
    if (t.closest('.aj-kitap-kapat') || t.closest('#aj-perde')) { kitapKapat(); return; }
    var kart = t.closest('.aj-kart');
    if (kart) kitapAc(kart.getAttribute('data-k'));
  });
  kok.addEventListener('keydown', function (ev) {
    var kart = ev.target.closest && ev.target.closest('.aj-kart');
    if (kart && (ev.key === 'Enter' || ev.key === ' ')) { ev.preventDefault(); kitapAc(kart.getAttribute('data-k')); }
  });
  /* Esc yalnız açık kartı kapatır; yakalama evresinde, sekme Esc'inden önce. */
  window.addEventListener('keydown', function (ev) {
    if (ev.key !== 'Escape') return;
    var kitap = document.getElementById('aj-kitap');
    if (kitap && !kitap.hidden) { ev.preventDefault(); ev.stopImmediatePropagation(); kitapKapat(); return; }
    if (_ozA) { onizlemeKapat(); }
  }, true);

  /* Masaüstü: üstüne gel → önizleme. */
  kok.addEventListener('mouseover', function (ev) {
    if (dokunmatik()) return;
    var kart = ev.target.closest && ev.target.closest('.aj-kart');
    if (!kart || kart.getAttribute('data-k') === _ozA) return;
    clearTimeout(_ozZaman);
    _ozZaman = setTimeout(function () { onizlemeAc(kart, kart.getAttribute('data-k')); }, ONIZLEME_GECIKME);
  });
  kok.addEventListener('mouseout', function (ev) {
    var kart = ev.target.closest && ev.target.closest('.aj-kart');
    if (!kart || (ev.relatedTarget && kart.contains(ev.relatedTarget))) return;
    clearTimeout(_ozZaman);
    clearTimeout(_ozKapatZ);
    _ozKapatZ = setTimeout(onizlemeKapat, 120);
  });
  /* Telefon: uzun bas → önizleme, kart AÇILMAZ (bırakınca gelen tık yutulur). */
  kok.addEventListener('pointerdown', function (ev) {
    _uzunBasildi = false;
    if (ev.pointerType === 'mouse') return;
    var kart = ev.target.closest && ev.target.closest('.aj-kart');
    if (!kart) { if (_ozA) onizlemeKapat(); return; }
    clearTimeout(_basZaman);
    _basZaman = setTimeout(function () { _uzunBasildi = true; onizlemeAc(kart, kart.getAttribute('data-k')); }, UZUN_BAS_MS);
  });
  ['pointerup', 'pointercancel', 'pointerleave'].forEach(function (ad) {
    kok.addEventListener(ad, function () { clearTimeout(_basZaman); });
  });
  kok.addEventListener('click', function (ev) {
    if (!_uzunBasildi) return;
    ev.preventDefault(); ev.stopImmediatePropagation();
    _uzunBasildi = false;
  }, true);
  kok.addEventListener('contextmenu', function (ev) {
    if (ev.target.closest && ev.target.closest('.aj-kart') && dokunmatik()) ev.preventDefault();
  });
  kok.addEventListener('scroll', function () { if (_ozA) onizlemeKapat(); }, true);

  /* ── yetki ─────────────────────────────────────────────────────── */
  function yetkiBekle() {
    return new Promise(function (resolve) {
      if (typeof window._yukiAjanOk === 'boolean') { resolve(window._yukiAjanOk); return; }
      var bitti = false, t0 = Date.now();
      function karar(v) {
        if (bitti) return;
        bitti = true; clearInterval(t);
        document.removeEventListener('yuki:entitlements', dinle);
        resolve(v);
      }
      function dinle() { if (typeof window._yukiAjanOk === 'boolean') karar(window._yukiAjanOk); }
      document.addEventListener('yuki:entitlements', dinle);
      var t = setInterval(function () {
        if (typeof window._yukiAjanOk === 'boolean') { karar(window._yukiAjanOk); return; }
        if (Date.now() - t0 > BEKLEME_MS) karar(false);   // fail-closed
      }, YOKLAMA_MS);
    });
  }

  function bilgi(anahtar) {
    kok.innerHTML = '<div class="pv-bilgi"><p>' + esc(_ajt(anahtar)) + '</p></div>';
    kok._bilgi = anahtar;
  }

  window.addEventListener('yuki-dil-degisti', function () {
    if (!baslatildi) { if (kok._bilgi) bilgi(kok._bilgi); return; }
    etiketleriYaz();
    imzalar = {};
    var kitap = document.getElementById('aj-kitap');
    if (kitap) kitap._son = null;
    ciz();
  });

  bilgi('ajan-view.hazirlaniyor');

  function basla() {
    if (baslatildi) return;
    baslatildi = true;
    kok._bilgi = null;
    iskeletKur();
    ciz();
    dongu();
    document.addEventListener('tabchange', function (e) {
      if (e.detail && e.detail.tab === 'ajan') { hizliTur(); yavasTur(); }
      else { onizlemeKapat(); kitapKapat(); }
    });
    document.addEventListener('visibilitychange', function () { if (gorunur()) hizliTur(); });
    window.addEventListener('resize', function () { if (_ozA) onizlemeKonumla(); });
  }

  /* Kapı sonradan açılabilir (kilit açılınca refreshAllAccess) — ilk cevap
     "kapalı" olsa da sonraki duyuruyu dinlemeye devam et. */
  yetkiBekle().then(function (ok) {
    if (ok) { basla(); return; }
    bilgi('ajan-view.ultra-gerekli');
    document.addEventListener('yuki:entitlements', function () { if (window._yukiAjanOk) basla(); });
  });
  if (hareketAz()) kok.classList.add('az-hareket');
})();
