/* ════════════════════════════════════════════════════════════════
   YUKI AÇILIŞ v4 — gerçek veri katmanı
   Açılışta yazan her sayı/ad buradan gelir; kaynakta GÖMÜLÜ değer YOK.
   v3'ün dersi: "GPT-4.1-MINI", "v0.6.0" elle yazılmıştı ve aylarca bayat kaldı.

   Kaynaklar (aynı köken, uygulamanın kendi uçları):
     /health          → sürüm, çalışma süresi, DB gecikmesi, anı sayısı, STT durumu
     /api/system      → CPU %, çekirdek, RAM            (Bearer gerekir)
     /api/llm/config  → sağlayıcı + model               (Bearer gerekir)
   + tarayıcının kendisi: saat, tarih, gün, ekran.

   Bir uç yanıt vermezse alan BOŞ kalır (null) — sahne o satırı yazmaz ya da
   "—" basar. Yedek olarak uydurma değer yazmak yasak.
   Gizlilik: açılış makine adı, kullanıcı adı ya da dosya yolu YAZMAZ — yalnız
   sayılar (CPU/RAM/sürüm/süre) ve model adı; tests/test_acilis_animasyonu.py tarar.
   Metinler YukiVeri.t ile çevrilir (YukiDil yoksa Türkçe kaynağa düşer);
   gün/ay adları Intl ile aktif arayüz dilinde.
   ════════════════════════════════════════════════════════════════ */
window.YukiVeri = (function () {
  'use strict';

  /* Çeviri: YukiDil anahtarı bilirse onun metni, yoksa verilen Türkçe kaynak. */
  function t(anahtar, kaynak, degerler) {
    var m = null;
    try {
      if (window.YukiDil && window.YukiDil.t) {
        var c = window.YukiDil.t(anahtar, degerler);
        if (c != null && c !== anahtar) m = String(c);
      }
    } catch (e) { /* yut */ }
    if (m == null) {
      m = String(kaynak);
      if (degerler) m = m.replace(/\{(\w+)\}/g, function (tam, ad) {
        return Object.prototype.hasOwnProperty.call(degerler, ad) ? String(degerler[ad]) : tam;
      });
    }
    return m;
  }
  function dil() {
    try { if (window.YukiDil && window.YukiDil.yerel) return window.YukiDil.yerel(); } catch (e) { /* yut */ }
    return 'tr-TR';
  }
  function bicim(d, secenek) {
    try { return d.toLocaleDateString(dil(), secenek); } catch (e) { return d.toLocaleDateString('tr-TR', secenek); }
  }

  function token() {
    try { return sessionStorage.getItem('aliceToken') || localStorage.getItem('aliceToken') || ''; } catch (e) { return ''; }
  }

  function iki(n) { return (n < 10 ? '0' : '') + n; }

  /* Zaman aşımlı GET — hata/401/zaman aşımı → null (asla fırlatmaz) */
  function al(yol, ms) {
    var ctrl = ('AbortController' in window) ? new AbortController() : null;
    var zs = setTimeout(function () { if (ctrl) ctrl.abort(); }, ms || 900);
    var h = {};
    var t = token();
    if (t) h.Authorization = 'Bearer ' + t;
    return fetch(yol, { headers: h, cache: 'no-store', signal: ctrl ? ctrl.signal : undefined })
      .then(function (r) { return r.ok ? r.json() : null; })
      .catch(function () { return null; })
      .then(function (j) { clearTimeout(zs); return j; });
  }

  function yerel(an) {
    var d = an || new Date();
    var s = d.getHours();
    return {
      saat: iki(s) + ':' + iki(d.getMinutes()),
      saatTam: iki(s) + ':' + iki(d.getMinutes()) + ':' + iki(d.getSeconds()),
      tarih: bicim(d, { day: 'numeric', month: 'long', year: 'numeric' }),
      tarihKisa: bicim(d, { day: '2-digit', month: '2-digit', year: 'numeric' }),
      gun: bicim(d, { weekday: 'long' }),
      ekran: Math.round(innerWidth) + '×' + Math.round(innerHeight),
      dpr: Math.round((window.devicePixelRatio || 1) * 100) / 100
    };
  }

  function sureYaz(sn) {
    if (sn == null || isNaN(sn)) return null;
    sn = Math.max(0, Math.floor(sn));
    var g = Math.floor(sn / 86400), sa = Math.floor(sn % 86400 / 3600), dk = Math.floor(sn % 3600 / 60);
    if (g) return t('acilis.sure.gun-saat', '{g} g {sa} sa', { g: g, sa: sa });
    if (sa) return t('acilis.sure.saat-dakika', '{sa} sa {dk} dk', { sa: sa, dk: dk });
    if (dk) return t('acilis.sure.dakika-saniye', '{dk} dk {sn} sn', { dk: dk, sn: sn % 60 });
    return t('acilis.sure.saniye', '{sn} sn', { sn: sn });
  }

  function sayi(n, basamak) {
    if (n == null || isNaN(n)) return null;
    return Number(n).toLocaleString(dil(), { maximumFractionDigits: basamak == null ? 1 : basamak });
  }

  /* hedef nesneyi kademeli doldurur (sahne her karede okur); hepsi bitince çözülür */
  function topla(hedef, ms) {
    hedef = hedef || {};
    var y = yerel();
    for (var k in y) hedef[k] = y[k];
    hedef.kaynak = hedef.kaynak || {};
    hedef.cpuOrnek = hedef.cpuOrnek || [];

    var p1 = al('/health', ms).then(function (j) {
      if (!j) return;
      var alt = j.subsystems || {};
      hedef.surum = j.version || null;
      hedef.durum = j.status || null;
      hedef.uptime = sureYaz(j.uptime_seconds);
      hedef.db_ms = alt.database && alt.database.latency_ms != null ? alt.database.latency_ms : null;
      hedef.db = alt.database ? alt.database.status : null;
      hedef.ani = alt.memory && alt.memory.count != null ? alt.memory.count : null;
      hedef.stt = alt.stt_model ? alt.stt_model.status : null;
      hedef.tarayici = alt.browser ? !!alt.browser.enabled : null;
      hedef.karakter = j.character || null;
      hedef.kaynak.health = true;
    });
    var p2 = al('/api/system', ms).then(function (j) {
      if (!j || j.error) return;
      hedef.cpu = j.cpu;
      hedef.cekirdek = j.cores;
      hedef.ram = j.ram || null;
      hedef.disk = j.disk ? j.disk.percent : null;
      hedef.cpuOrnek.push(j.cpu);
      hedef.kaynak.system = true;
    });
    var p3 = al('/api/llm/config', ms).then(function (j) {
      if (!j) return;
      hedef.model = j.model || null;
      hedef.saglayici = j.provider || null;
      hedef.kaynak.llm = true;
    });
    return Promise.all([p1, p2, p3]).then(function () { hedef.hazir = true; return hedef; });
  }

  /* /api/system'i aralıkla yokla, CPU örneklerini biriktir — durdurucu döner */
  function izle(hedef, aralik, adet) {
    var n = 0, dur = false;
    function tur() {
      if (dur || n++ >= (adet || 20)) return;
      al('/api/system', 700).then(function (j) {
        if (j && !j.error) {
          hedef.cpuOrnek.push(j.cpu);
          hedef.cpu = j.cpu;
          if (j.ram) hedef.ram = j.ram;
        }
        if (!dur) setTimeout(tur, aralik || 250);
      });
    }
    tur();
    return function () { dur = true; };
  }

  return { topla: topla, izle: izle, yerel: yerel, sureYaz: sureYaz, sayi: sayi, al: al, t: t };
})();
