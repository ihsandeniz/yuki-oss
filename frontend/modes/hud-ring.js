/* ════════════════════════════════════════════════════════════════════
   hud-ring.js — Mod 01 v2: "Great Sage" HUD Halka (ZUZU layout)

   Merkez: 7 katmanlı rünik halka + karakter adı çekirdek + ışık hüzmeleri.
   Alt: "X'e bir şey sor…" + animasyonlu noktalar + durum satırı.
   Sağ: ARAÇLAR paneli (notlar/alarm/görev) + KONUŞMA AKIŞI
        (#messages DOM'u panele taşınır — tüm chat akışı orada yaşar).
   updateState() sarılır: halka rengi/hızı + durum metni state'i izler.
   ════════════════════════════════════════════════════════════════════ */
(function () {
  'use strict';

  // ── i18n sarmalayıcı — hud-ring.js dosyasına özgü ──
  function _hrt(anahtar, degerler) {
    return (window.YukiDil && window.YukiDil.t) ? window.YukiDil.t(anahtar, degerler) : String(anahtar);
  }
  /* Yedekli çeviri: sözlükte henüz olmayan anahtar (şerit i18n.json'u birleştirmede eklenir)
     ekranda anahtar adı değil yedek göstersin. Yedek dil-bağımsız olmalı (test_bl402: çevrilmiş
     dosyada Türkçe literal yok) — ör. rayın kendi adı 'PANEL'. */
  function _hrtY(anahtar, yedek) {
    const m = _hrt(anahtar);
    return m === anahtar ? yedek : m;
  }
  // Tarih/saat biçimi aktif arayüz dilini izler (eskiden sabit 'tr-TR').
  function _hrYerel() {
    return (window.YukiDil && window.YukiDil.yerel) ? window.YukiDil.yerel() : 'tr-TR';
  }

  const RUNES  = 'ᚠᚢᚦᚨᚱᚲᚷᚹᚺᚾᛁᛃᛇᛈᛉᛊᛏᛒᛖᛗᛚᛜᛞᛟ';
  /* Anahtar yokken boşta "Sistemler aktif" / "HAZIR" demez (goz 11-13 #1b): hüküm sohbet rozetiyle
     aynı kaynak (core.js `yukiAnahtarHazir`, /api/llm/key/status). Bilinmiyorsa (null) eski metin. */
  const _anahtarYok = () => typeof window.yukiAnahtarHazir === 'function' && window.yukiAnahtarHazir() === false;
  const STATE = {
    idle:      { cls: 'hr-idle',      get status() { return _hrt(_anahtarYok() ? 'hudring.durum.anahtar-yok' : 'hudring.durum.idle'); } },
    listening: { cls: 'hr-listening', get status() { return _hrt('hudring.durum.listening'); } },
    thinking:  { cls: 'hr-thinking',  get status() { return _hrt('hudring.durum.thinking'); } },
    talking:   { cls: 'hr-talking',   get status() { return _hrt('hudring.durum.talking'); } },
  };
  // "X'e bir şey sor…" — Türkçe yönelme eki ada göre değişir (ye/ya), o yüzden
  // karakter başına ek değil TAM CÜMLE anahtarı: {ad} yer tutucusu, EN'de doğal cümle.
  // Tek karakter (2026-11-14); yeni karakter = buraya ad → anahtar girdisi ('hudring.sor-ya' sözlükte).
  const ASK = { yuki: 'hudring.sor-ye' };
  function _askMetni(k) {
    const anahtar = ASK[k] || ASK.yuki;
    const ad = ASK[k] ? k.charAt(0).toUpperCase() + k.slice(1) : 'Yuki';
    return _hrt(anahtar, { ad });
  }

  let _stage = null, _side = null, _timer = null, _clockTimer = null;
  let _tickerTimer = null;
  let _reminderTimer = null, _modesTimer = null, _todoTimer = null;
  let _activeTab = 'memory';
  // ── localStorage migration: yuki_hr_* → yuki_hr_*_v1 ──
  (function _migrateHudRingKeys() {
    try {
      const old = localStorage.getItem('yuki_hr_collapsed');
      if (old !== null) {
        localStorage.setItem('yuki_hr_collapsed_v1', old);
        localStorage.removeItem('yuki_hr_collapsed');
      }
      const oldLeft = localStorage.getItem('yuki_left_cards');
      if (oldLeft !== null) {
        localStorage.setItem('yuki_left_cards_v1', oldLeft);
        localStorage.removeItem('yuki_left_cards');
      }
      const oldRail = localStorage.getItem('yuki_hr_rail_collapsed');
      if (oldRail !== null) {
        localStorage.setItem('yuki_hr_rail_collapsed_v1', oldRail);
        localStorage.removeItem('yuki_hr_rail_collapsed');
      }
    } catch (_) {}
  })();
  let _panelCollapsed = localStorage.getItem('yuki_hr_collapsed_v1') === '1';
  let _wrapped = false;
  let _msgHome = null; // #messages'ın orijinal konumu {parent, next}
  let _events = [], _tickerIdx = 0, _resizeT = 0;

  // ── HALKA teması (2026-10-04) ───────────────────────────────────
  // Kişisel AliceAi'deki tema seçicinin ürün karşılığı. Tek yazıcı `_temaYaz`
  // → <html data-halka-tema="…">; tema CSS'i yalnız o özniteliğin altında
  // eşleşir. "buz" = ürünün bugünkü buz mavisi halkası, HİÇBİR tema kuralı
  // yok (varsayılan). Süs katmanı (`window.HalkaTemalar[ad].init/kaldir`)
  // yalnız HALKA açıkken kurulur.
  // Seçici üst çubuktaki mod menüsünde (kişiseldeki gibi, 2026-11-14) — API aşağıda `window.HalkaTema`.
  // Dosyalar bu betikle AYNI `?v=` ile dinamik iner (`_V`): ayrı bir sürüm
  // sayacı açılsaydı biri bump edilip öbürü unutulurdu.
  const _V = (() => {
    try {
      const m = /[?&]v=([^&#]+)/.exec((document.currentScript || {}).src || '');
      return m ? '?v=' + m[1] : '';
    } catch (e) { return ''; }
  })();
  // 2026-11-13 (arayüz turu "sohbet kişiseldeki gibi"): varsayılan KARA MANA — kişisel Yuki'nin ilk
  // açılışı bu (kara delik çekirdek + altın disk, mor zemin). BUZ seçilebilir kalır; kayıtlı seçim ezilmez.
  // Sıra = seçicideki sıra: varsayılan önde.
  const HALKA_TEMALAR = [
    { key: 'kara-mana-goz', lk: 'hudring.tema.kara-mana' },
    { key: 'buz',           lk: 'hudring.tema.buz' },
  ];
  const HALKA_TEMA_KEY = 'yuki_halka_tema_v1';
  const HALKA_TEMA_VARSAYILAN = 'kara-mana-goz';
  const _temaGecerli = t => HALKA_TEMALAR.some(x => x.key === t);
  let _halkaTema = HALKA_TEMA_VARSAYILAN;
  try {
    const kayitli = localStorage.getItem(HALKA_TEMA_KEY);
    if (_temaGecerli(kayitli)) _halkaTema = kayitli;
  } catch (e) { /* depolama kapalı: varsayılan */ }
  const _temaYaz = t => document.documentElement.setAttribute('data-halka-tema', t);
  _temaYaz(_halkaTema);

  const _temaVarlik = {};
  function _temaDosyalari(t) {
    if (t === 'buz') return Promise.resolve();
    if (!_temaVarlik[t]) {
      const yol = '/ui/modes/halka-tema/' + t;
      const css = new Promise((ok, hata) => {
        if (document.querySelector('link[data-halka-tema-css="' + t + '"]')) return ok();
        const l = document.createElement('link');
        l.rel = 'stylesheet'; l.href = yol + '.css' + _V; l.dataset.halkaTemaCss = t;
        l.onload = ok; l.onerror = () => { l.remove(); hata(new Error(t + '.css')); };
        document.head.appendChild(l);
      });
      const js = new Promise((ok, hata) => {
        if (window.HalkaTemalar && window.HalkaTemalar[t]) return ok();
        const sc = document.createElement('script');
        sc.src = yol + '.js' + _V;
        sc.onload = ok; sc.onerror = () => { sc.remove(); hata(new Error(t + '.js')); };
        document.head.appendChild(sc);
      });
      _temaVarlik[t] = Promise.all([css, js]).catch(e => { delete _temaVarlik[t]; throw e; });
    }
    return _temaVarlik[t];
  }
  // Seçili tema varsayılan değilse dosyalar HEMEN iner: halka ilk açıldığında
  // önce buz mavisi bir kare görünüp sonra temaya atlamasın.
  if (_halkaTema !== 'buz') _temaDosyalari(_halkaTema).catch(e => console.error('[halka-tema]', e));

  // Süs katmanını duruma eşitle: HALKA açık + tema seçili → init, aksi hâlde kaldir.
  async function _temaSenkron() {
    const halkada = document.body.classList.contains('hud-ring-mode');
    const hedef = halkada ? _halkaTema : 'buz';
    const kurulu = window.HalkaTemalar || {};
    Object.keys(kurulu).forEach(k => { if (k !== hedef) kurulu[k].kaldir(); });
    if (hedef === 'buz') return;
    try { await _temaDosyalari(hedef); } catch (e) { console.error('[halka-tema]', e); return; }
    // bekleme sırasında mod/tema değiştiyse yetim katman kurma
    if (!document.body.classList.contains('hud-ring-mode') || _halkaTema !== hedef) return;
    const m = (window.HalkaTemalar || {})[hedef];
    if (m) m.init();
  }
  function _temaKaldirHepsi() {
    const kurulu = window.HalkaTemalar || {};
    Object.keys(kurulu).forEach(k => kurulu[k].kaldir());
  }

  /* 2026-11-14 (arayüz hizalama, kişiseldeki gibi): PANEL'deki HALKA TEMASI kartı ve dar ekran
     tema hapı KALDIRILDI — kişisel Yuki'de tema üst çubuktaki mod menüsünde. Seçici artık
     bu dosyada değil; menü `window.HalkaTema` üzerinden konuşur:
       liste() → [{ key, ad }]  (ad = o anki dilde çevrilmiş tema adı)
       al()    → seçili tema anahtarı
       sec(k)  → temayı uygular (localStorage + <html data-halka-tema> + süs katmanı senkronu);
                 geçersiz anahtar → false. Değişince `halka:tema-degisti` olayı ({ key }) atılır —
                 menü kendi işaretini buradan tazeler, ikinci bir kayıt tutmaz. */
  function _temaSec(t) {
    if (!_temaGecerli(t)) return false;
    if (t === _halkaTema) return true;
    _halkaTema = t;
    try { localStorage.setItem(HALKA_TEMA_KEY, t); } catch (e) { /* oturumluk kalır */ }
    _temaYaz(t);
    _temaSenkron();
    try { document.dispatchEvent(new CustomEvent('halka:tema-degisti', { detail: { key: t } })); } catch (e) {}
    return true;
  }
  window.HalkaTema = {
    liste() { return HALKA_TEMALAR.map(t => ({ key: t.key, ad: _hrt(t.lk) })); },
    al() { return _halkaTema; },
    sec(key) { return _temaSec(key); },
  };

  // ── Floating widget sistemi ──
  /* 🔑 `grup` (2026-10-04): sağ panel yatay ikon şeridinden DİKEY,
     kategorili listeye döndü (kişisel AliceAi 2026-09-13 düzeni). Altı widget
     yan yana 7px etiketle "altı eşit şey" oluyordu; adlandırılmış küme
     hiyerarşiyi renk harcamadan kurar. Sıra bu dizidendir — panel gruplara
     göre çizer, ayrı bir markup listesi TUTULMAZ (`_sideRayHtml`).
     Kategoriler ürünün içeriğine göre: ZİHİN (Yuki'nin bildiği ve kipi) ·
     İŞ (kullanıcının zamanı) · SİSTEM (konuşma akışı + makine).
     2026-11-14 (kişiseldeki gibi): GÖZ ve SİTELER eklendi — sıra kişisel PANEL'in sırası.
       · GÖZ: kişiselin kamera kodu TAŞINMADI; gövde açık kaynağın kendi rıza ekranlı
         `YukiGorusPanel`'i (js/gorus-panel.js). Kurulum bayrağı GORUS kapalıysa (sunucu 404)
         yalnız "bu kurulumda kapalı" satırı — olmayanı vaat etmez.
       · SİTELER: Odaklı Halka'nın site deposu `window.HalkaSiteler` (localStorage, sunucusuz);
         arka uç çağrısı YOK. Ekleme halkanın kendi site panelinde.
     KRİPTO (kişisel finans) üründe yok, taşınmaz.
     🔴 FİNANS (`stocks`) 2026-10-04'te SÖKÜLDÜ: finans üründen kaldırılmıştı,
     widget yalnız "hazırlanıyor" diyen bir taslaktı (D1=B, 2026-08-12). */
  const RING_GRUPLAR = [
    { ad: 'zihin',  lk: 'hudring.grup.zihin' },
    { ad: 'is',     lk: 'hudring.grup.is' },
    { ad: 'sistem', lk: 'hudring.grup.sistem' },
  ];
  /* Göz turu 2 (2026-10-04): panel + widget başlığı ikonları SVG. Glifler
     (◷ ≋ ▣) JetBrains Mono'da farklı boylarda çiziliyordu — ALARM ve AKIŞ
     yarı boydaydı. Ürün sekme menüsünün ikon dili: 16'lık kutu, 1.5 çizgi,
     currentColor (renk CSS'ten gelir, tema/accent ile döner). */
  const _ikon = d => `<svg viewBox="0 0 16 16" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">${d}</svg>`;
  const RING_IKON = {
    memory: _ikon('<circle cx="8" cy="8" r="5.8"/><circle cx="8" cy="8" r="2.2"/>'),
    modes:  _ikon('<path d="M8 1.8l5.4 3.1v6.2L8 14.2l-5.4-3.1V4.9z"/>'),
    alarms: _ikon('<circle cx="8" cy="8.6" r="5.4"/><path d="M8 5.8v2.8l1.9 1.3M2.4 3.2l2-1.6M13.6 3.2l-2-1.6"/>'),
    todos:  _ikon('<rect x="2.2" y="2.2" width="11.6" height="11.6" rx="2"/><path d="M5.2 8.2l1.9 1.9 3.8-4"/>'),
    chat:   _ikon('<path d="M14 10a2 2 0 01-2 2H5l-3 3V4a2 2 0 012-2h8a2 2 0 012 2v6z"/>'),
    hq:     _ikon('<path d="M2.2 7.4L8 2.4l5.8 5"/><path d="M3.8 6.2v7.4h8.4V6.2"/>'),
    gaze:   _ikon('<path d="M1.6 8s2.4-4.6 6.4-4.6S14.4 8 14.4 8s-2.4 4.6-6.4 4.6S1.6 8 1.6 8z"/><circle cx="8" cy="8" r="2"/>'),
    sites:  _ikon('<rect x="2.2" y="2.2" width="4.6" height="4.6" rx="1"/><rect x="9.2" y="2.2" width="4.6" height="4.6" rx="1"/><rect x="2.2" y="9.2" width="4.6" height="4.6" rx="1"/><rect x="9.2" y="9.2" width="4.6" height="4.6" rx="1"/>'),
  };
  const RING_WIDGET_CFG = [
    { id: 'memory', lk: 'hudring.w.hafiza', icon: '⊙', w: 320, h: 380, grup: 'zihin' },
    { id: 'modes',  lk: 'hudring.w.modlar', icon: '⬡', w: 300, h: 360, grup: 'zihin' },
    { id: 'gaze',   lk: 'hudring.w.goz',    icon: '◉', w: 340, h: 420, grup: 'zihin' },
    { id: 'alarms', lk: 'hudring.w.alarm',  icon: '◷', w: 300, h: 300, grup: 'is' },
    { id: 'todos',  lk: 'hudring.w.gorev',  icon: '▣', w: 300, h: 360, grup: 'is' },
    { id: 'chat',   lk: 'hudring.w.akis',   icon: '≋', w: 320, h: 460, grup: 'sistem' },
    { id: 'hq',     lk: null,               icon: '⌂', w: 340, h: 420, grup: 'sistem' },
    { id: 'sites',  lk: 'hudring.w.siteler', icon: '⊞', w: 320, h: 400, grup: 'sistem' },
  ];
  // `cfg.label` okuyan her yer okuma anındaki dili görür (yükleme anında donmaz).
  RING_WIDGET_CFG.forEach(c => Object.defineProperty(c, 'label', {
    get() { return c.lk ? _hrtY(c.lk, c.id.toUpperCase()) : 'HQ'; },
  }));
  // _v2 (2026-08-03): varsayılan konum değişti — widget'lar `#hr-side` dock'unun
  // (PANEL başlığı) üstüne açılıyordu ve onu tamamen örtüyordu. Anahtar bump
  // edilmezse mevcut kullanıcılar eski çakışan konumla kalırdı; yeni varsayılan
  // yalnız yeni kurulumlarda görünürdü ve kusur "düzeldi" sanılırdı.
  // _v3 (2026-10-04): aynı ders ikinci kez — panel dikey listeye döndü
  // ve ~470px uzadı. _v2'nin "dock altı" konumu (sağ kenar, y=150) artık listenin
  // TAM üstü; widget'lar varsayılan olarak SOL sütunda açılır (`_buildWidgets`).
  // _v4 (2026-11-13): varsayılan yer yine değişti — SOL sütun değil PANEL rayının SOLU,
  // halkanın çekirdeğini örtecekse yalnız başlığıyla (kişisel Yuki'nin düzeni). Anahtar bump'lanmazsa
  // _v3'te kayıtlı kurulum eski solda-açık hâlde kalır ve değişiklik "görünmedi" sanılır (_v2/_v3 dersi).
  const RING_STORAGE_KEY = 'yuki_hr_widgets_v4';
  let _ringState = {}, _ringZTop = 50, _ringLoaded = {};

  // ── Snap bölgeleri — SIĞDIĞI KADAR (2026-08-04) ───────────────────────────
  //
  // 🔴 Eski hâli sabit 12 bölgeydi ve dikey konumlar **boş alanın** (`ch - wh`)
  // kesirleriydi (0.28 · 0.5 · 0.72), ama her bölge kutusu **widget yüksekliği
  // kadar** çiziliyordu. Widget uzadıkça boş alan küçülür, 5 konum daralan bir
  // şeride sıkışır, kutular ise aynı kalır → bölgeler birbirinin üstüne biner.
  //
  // Varsayılan FİNANS widget'ında (320×380, tuval 1532×900) ÖLÇÜLDÜ:
  //   Sol Üst ↔ Sol Üst-Orta   %80 örtüşme (aralarında 76 px)
  //   Sol Üst-Orta ↔ Sol Orta  %70          (114 px)
  //   Sol Orta ↔ Sol Alt-Orta  %70          (114 px)
  //   Sol Alt-Orta ↔ Sol Alt   %64          (136 px)
  // Yani 5 bölge fiilen 1,5 bölgeydi: kullanıcı nereye bıraktığını göremiyor,
  // bıraktığı yer de gösterilenden başkası oluyordu. (geliştiricinin Windows turu.)
  //
  // Çözüm: bölge sayısı SABİT DEĞİL — tuvale kaç tane üst üste binmeden sığıyorsa
  // o kadar. Widget'ın boyutuna dokunulmaz (geliştirici kararı 2026-08-04: büyüttüğün
  // pencere bırakınca küçülmesin) → **önizleme = gerçek**: kutunun gösterdiği yer,
  // widget'ın gerçekten gideceği yer.
  const SNAP_UST = 70;          // üst bar (0-44) + `#hr-side` dock'u altı
  const SNAP_ALT = 10;          // alt kenar payı
  const SNAP_ARA = 12;          // bölgeler arası asgari boşluk
  const SNAP_MAKS_SLOT = 5;     // sütun başına tavan (eski tasarımın 5 kademesi)
  const SNAP_MERKEZ_MAKS = 2;   // merkez sütunu: Merkez + Alt Orta

  // Slot sayısına göre kademe adları — 5'te eski adlandırma birebir korunur.
  // Değerler METİN değil ANAHTAR — etiket bölge üretilirken (sürükleme anında) çözülür.
  const _SNAP_ADLARI = {
    1: ['hudring.snap.orta'],
    2: ['hudring.snap.ust', 'hudring.snap.alt'],
    3: ['hudring.snap.ust', 'hudring.snap.orta', 'hudring.snap.alt'],
    4: ['hudring.snap.ust', 'hudring.snap.ust-orta', 'hudring.snap.alt-orta', 'hudring.snap.alt'],
    5: ['hudring.snap.ust', 'hudring.snap.ust-orta', 'hudring.snap.orta', 'hudring.snap.alt-orta', 'hudring.snap.alt'],
  };

  /** Kaç bölge üst üste binmeden sığar? (en az 1, en çok `tavan`) */
  function _snapSlotSayisi(ch, wh, tavan) {
    const alan = ch - SNAP_UST - SNAP_ALT;
    const n = Math.floor((alan + SNAP_ARA) / (wh + SNAP_ARA));
    return Math.max(1, Math.min(tavan, n));
  }

  /** i. slotun y'si — tek slot ortalanır, çok slot üstten alta eşit dağılır.
   *
   * Tek slot dalında KIRPMA şart: widget kullanılabilir alandan uzun olabilir
   * (900×500 tuvalde 490 px'lik widget). Kırpmasız hâli ölçüldüğünde widget
   * tuvalin 30 px dışına taşıyordu — alt kenarı ekranda görünmezdi.
   * Çok slotlu dalda gerek yok: n≥2 zaten "sığıyor" demek.
   */
  function _snapY(i, n, ch, wh) {
    const alan = ch - SNAP_UST - SNAP_ALT;
    if (n <= 1) {
      const ortali = SNAP_UST + Math.max(0, (alan - wh) / 2);
      // Alt kenar tuvalin içinde kalsın; widget tuvalden de uzunsa üstten başla.
      return Math.max(0, Math.min(ortali, ch - wh - SNAP_ALT));
    }
    return SNAP_UST + (i * Math.max(0, alan - wh)) / (n - 1);
  }

  /**
   * Bölgeleri (cw,ch,ww,wh) girdisinden ÜRET — saf fonksiyon, önbellek yok.
   *
   * `_showSnapZones` (çizim) ve `_findNearestZone` (seçim) ikisi de burayı
   * çağırır. Ayrı hesaplasalardı gösterilen kutu ile bırakılan yer ayrışabilirdi;
   * bu dosyada zaten bir kez yaşanmış bir hata sınıfı ("aynı soruya iki cevap").
   *
   * `id` slot düzenini de taşır (`l2of5`) — çünkü farklı boyuttaki widget'lar
   * farklı düzen görür ve doluluk sayacı yalnız AYNI düzeni paylaşanları
   * gruplamalı, yoksa çakışmayan widget'lar birbirini yana kaydırır.
   */
  function _computeSnapZones(cw, ch, ww, wh, sagSinir) {
    const zones = [];
    const n = _snapSlotSayisi(ch, wh, SNAP_MAKS_SLOT);
    const adlar = _SNAP_ADLARI[n] || _SNAP_ADLARI[1];
    // `sagSinir`: sağ kenara yaslı panelin sol kenarı (yoksa tuval genişliği).
    // Sağ sütun panelin SOLUNA oturur — dikey liste ~340px uzun, sütun ona
    // yaslansaydı bırakılan widget listenin üstüne binerdi.
    const sag = (sagSinir == null) ? cw : sagSinir;
    const sutunlar = [
      { k: 'l', ad: 'hudring.snap.sol', x: 10 },
      { k: 'r', ad: 'hudring.snap.sag', x: Math.max(10, sag - ww - 10) },
    ];
    for (const s of sutunlar) {
      for (let i = 0; i < n; i++) {
        zones.push({
          id: `${s.k}${i}of${n}`,
          label: _hrt('hudring.snap.konum', { kenar: _hrt(s.ad), kademe: _hrt(adlar[i]) }),
          // Görsel dil korunuyor: uçlar rect, aradakiler oct.
          shape: (i === 0 || i === n - 1) ? 'rect' : 'oct',
          x: s.x, y: _snapY(i, n, ch, wh),
        });
      }
    }
    // Merkez sütunu — halkanın üstü. En çok 2 (Merkez + Alt Orta).
    const nc = _snapSlotSayisi(ch, wh, SNAP_MERKEZ_MAKS);
    const merkezX = Math.max(10, (cw - ww) / 2);
    if (nc <= 1) {
      // Tek slot gerçekten ortalanır → "Merkez" adı doğru.
      zones.push({ id: 'c0of1', label: _hrt('hudring.snap.merkez'), shape: 'hex',
                   x: merkezX, y: _snapY(0, 1, ch, wh) });
    } else {
      // İki slotta üstteki artık ortada DEĞİL — ona "Merkez" demek yalan olurdu
      // (etiket kullanıcının nereye bıraktığını okuduğu tek şey).
      zones.push({ id: 'c0of2', label: _hrt('hudring.snap.merkez-ust'), shape: 'hex',
                   x: merkezX, y: _snapY(0, 2, ch, wh) });
      zones.push({ id: 'c1of2', label: _hrt('hudring.snap.merkez-alt'), shape: 'diamond',
                   x: merkezX, y: _snapY(1, 2, ch, wh) });
    }
    return zones;
  }

  const SNAP_THRESHOLD = 110;
  const EDGE_THRESHOLD = 45;
  let _snapOccupancy = {};

  // Ses-senkron durum kapısı: TTS sesi çalarken halkayı 'talking'de tut,
  // backend erken 'idle' yollarsa beklet (ses bitince uygula).
  let _speaking = false, _pendingState = null, _speakOffT = 0;

  // Durum → insan-okur etiket (persona rozeti + ticker)
  // Değerler ANAHTAR (sözlükte zaten var) — `_stateLbl` okuma anında çözer.
  const STATE_LBL = { idle: 'durum.hazir', listening: 'durum.dinliyor', thinking: 'durum.dusunuyor', talking: 'durum.konusuyor' };
  const _stateLbl = s => _hrt((!STATE_LBL[s] || s === 'idle') && _anahtarYok() ? 'durum.anahtar-yok' : (STATE_LBL[s] || STATE_LBL.idle));
  const _tickerVarsayilan = () => '◈ ' + _hrt(_anahtarYok() ? 'hudring.ticker.kurulum-gerekli' : 'hudring.ticker.sistemler-aktif');
  let _curState = 'idle';   // dil değişince #hr-status / #hr-core-status yeniden yazılsın
  const _char = () => (window.getCharacter ? window.getCharacter() : 'yuki');

  // ── ④ Merkez 3B ikosahedron (wireframe küre yerine; RAF ile çizilir) ──
  const _ICO_T = (1 + Math.sqrt(5)) / 2;
  const _ICO_V = [[-1,_ICO_T,0],[1,_ICO_T,0],[-1,-_ICO_T,0],[1,-_ICO_T,0],[0,-1,_ICO_T],[0,1,_ICO_T],
                  [0,-1,-_ICO_T],[0,1,-_ICO_T],[_ICO_T,0,-1],[_ICO_T,0,1],[-_ICO_T,0,-1],[-_ICO_T,0,1]]
                  .map(v => { const l = Math.hypot(v[0],v[1],v[2]); return [v[0]/l, v[1]/l, v[2]/l]; });
  const _ICO_F = [[0,11,5],[0,5,1],[0,1,7],[0,7,10],[0,10,11],[1,5,9],[5,11,4],[11,10,2],[10,7,6],[7,1,8],
                  [3,9,4],[3,4,2],[3,2,6],[3,6,8],[3,8,9],[4,9,5],[2,4,11],[6,2,10],[8,6,7],[9,8,1]];
  let _polys = null, _polyRAF = 0;
  function _polyInit() {
    const g = _stage && _stage.querySelector('#hr-poly');
    if (!g || _polys) return;
    _polys = _ICO_F.map(() => { const p = document.createElementNS('http://www.w3.org/2000/svg', 'polygon'); g.appendChild(p); return p; });
  }
  function _polySpeed() {
    const c = _stage ? _stage.className : '';
    return c.includes('thinking') ? 3.4 : c.includes('talking') ? 2.1 : c.includes('listening') ? 1.5 : 0.8;
  }
  function _polyRender(now) {
    if (document.hidden) { _polyRAF = requestAnimationFrame(_polyRender); return; }  // gizliyken çizme
    const g = _stage && _stage.querySelector('#hr-poly');
    if (!_polys || !g) { _polyRAF = requestAnimationFrame(_polyRender); return; }
    _polyCiz(now, g);
    _polyRAF = requestAnimationFrame(_polyRender);
  }

  /**
   * Tek karelik çizim. HAFİF kademesinde bir kez çağrılır ve döngü kurulmaz —
   * CSS `animation:none` ile duramaz, çünkü bu hareket JS'te (rAF) üretiliyor.
   * Ölçüm (10× kısıtlı CDP): döngünün kendisi 8 sn'lik pencerede ~0,45 sn
   * script zamanı yakıyor. Tek kare çizmek ŞART — hiç çizilmezse merkez boş kalır.
   */
  function _polyCiz(now, g) {
    const ry = now * 0.00040 * _polySpeed();
    const rx = 0.5 + Math.sin(now * 0.0002) * 0.16;
    const R = 60 * (1 + Math.sin(now * 0.0009) * 0.06);
    const cy = Math.cos(ry), sy = Math.sin(ry), cx = Math.cos(rx), sx = Math.sin(rx);
    const P = _ICO_V.map(([x,y,z]) => {
      const X = x*cy + z*sy, Z = -x*sy + z*cy, Y = y;
      const Y2 = Y*cx - Z*sx, Z2 = Y*sx + Z*cx;
      return [300 + X*R, 300 + Y2*R, Z2];
    });
    const ord = _ICO_F.map((f,i) => ({ i, z: (P[f[0]][2]+P[f[1]][2]+P[f[2]][2]) / 3 })).sort((a,b) => a.z - b.z);
    // Layout thrash fix: 20 faset'i tek tek g'ye eklemek yerine (her biri reflow) DocumentFragment'ta
    // biriktir, tek DOM işlemiyle ekle. Görsel BİREBİR aynı (z-order korunur) — yalnız reflow 20→1.
    const _frag = document.createDocumentFragment();
    ord.forEach((o,k) => {
      const f = _ICO_F[o.i], pg = _polys[k];
      pg.setAttribute('points', f.map(v => P[v][0].toFixed(1) + ',' + P[v][1].toFixed(1)).join(' '));
      const lit = Math.max(0, Math.min(1, (o.z / R + 1) / 2));
      const b = (3 + lit * 9) | 0;
      pg.setAttribute('fill', `rgba(${(b*0.5)|0},${(b*1.0)|0},${(b*1.2)|0},${(0.5 + lit*0.42).toFixed(2)})`);
      pg.setAttribute('stroke-opacity', (0.10 + lit*0.55).toFixed(2));
      pg.setAttribute('stroke-width', (0.5 + lit*0.9).toFixed(2));
      _frag.appendChild(pg); // çiz sırası: arka→ön (painter) — fragment'ta batch
    });
    g.appendChild(_frag); // tek DOM ekleme = tek reflow
    _polys[_polys.length - 1].setAttribute('stroke-opacity', '0.95'); // en ön faset parlak
  }
  function _hafifMi() { return document.documentElement.getAttribute('data-gfx') === 'hafif'; }
  function _polyStart() {
    _polyInit();
    if (_hafifMi()) {
      // Donmuş poz: bir kare çiz, döngü kurma.
      const g = _stage && _stage.querySelector('#hr-poly');
      if (g && _polys) _polyCiz(performance.now(), g);
      return;
    }
    if (!_polyRAF) _polyRAF = requestAnimationFrame(_polyRender);
  }
  function _polyStop()  { if (_polyRAF) { cancelAnimationFrame(_polyRAF); _polyRAF = 0; } }
  // Kademe çalışırken değişirse anında uy — kullanıcı ⋯ menüsünden seçiyor,
  // yeniden yükleme beklemesi gerekmesin.
  document.addEventListener('gfxchange', () => {
    if (!_stage) return;
    _polyStop();
    _polyStart();
  });

  // ── Karakter halka spec'leri — her karakter için değişken katmanlar ──
  function _specYuki() {
    const oTxt = (RUNES + '・' + RUNES + '・' + RUNES).slice(0, 64);
    const iTxt = (RUNES + '・' + RUNES).slice(0, 42);
    const _f = v => v.toFixed(1);
    let petals = '';
    for (let i = 0; i < 6; i++) {
      const a = (i * 60) * Math.PI / 180, r1 = 108, r2 = 158, w = 16;
      const pc = Math.cos(a), ps = Math.sin(a), tc = -ps, ts = pc;
      const p1x = 300+r1*pc, p1y = 300+r1*ps, p2x = 300+r2*pc, p2y = 300+r2*ps;
      const arm = (r2-r1)*0.42;
      petals += `<path d="M${_f(p1x)},${_f(p1y)} C${_f(p1x+arm*pc+w*tc)},${_f(p1y+arm*ps+w*ts)} ${_f(p2x-arm*pc+w*tc)},${_f(p2y-arm*ps+w*ts)} ${_f(p2x)},${_f(p2y)} C${_f(p2x-arm*pc-w*tc)},${_f(p2y-arm*ps-w*ts)} ${_f(p1x+arm*pc-w*tc)},${_f(p1y+arm*ps-w*ts)} ${_f(p1x)},${_f(p1y)} Z"/>`;
    }
    return {
      tickRing: `<circle cx="300" cy="300" r="272" stroke-width="11" stroke-dasharray="1.6 11.1" opacity="0.45"/><circle cx="300" cy="300" r="262" stroke-width="0.8" opacity="0.3"/>`,
      segRing:  `<circle cx="300" cy="300" r="248" stroke-width="2" stroke-dasharray="150 16 70 16 230 16 90 16" stroke-linecap="round" opacity="0.85"/><circle cx="300" cy="300" r="241" stroke-width="0.7" stroke-dasharray="4 9" opacity="0.4"/>`,
      mandala:  `<path d="M 515,300 L 300,515 L 85,300 L 300,85 Z"/><path d="M 452,452 L 148,452 L 148,148 L 452,148 Z"/><circle cx="300" cy="300" r="215" stroke-width="0.5" opacity="0.55"/>`,
      outerTxt: oTxt,
      innerTxt: iTxt,
      nodeRing: `<circle cx="300" cy="300" r="112" stroke-width="5" stroke-dasharray="0.1 28.5" stroke-linecap="round" opacity="0.9"/><circle cx="300" cy="300" r="104" stroke-width="0.6" opacity="0.3"/>`,
      innerOrg: `<g class="hr-layer hr-lotus" fill="none" stroke="var(--hr-accent)" stroke-width="1.3" opacity="0.45" filter="drop-shadow(0 0 5px var(--hr-accent))">${petals}</g>`,
    };
  }

  /* Karakter → halka dekoru tablosu. 2026-11-14 (ürün kararı): açık kaynak sürümde tek karakter
     Yuki; öbür dört karakterin dekorları (pentagram, bıçak, çiçek, devre izi) kaldırıldı. Yapı
     tablo olarak kalır: yeni karakter = buraya bir `_specX` + `_SAT_MAP` girdisi. Bilinmeyen
     anahtar Yuki dekoruna düşer. */
  const RING_SPEC = { yuki: _specYuki };
  function _charRingSpec(key) {
    return (RING_SPEC[key] || _specYuki)();
  }

  // ── Arcane zenginleştirme jeneratörleri (referans: Great Sage çok katmanlı sihir çemberi) ──
  // Mandala köşelerine oturan mini sihir çemberleri (uydu çemberler)
  const _SAT_MAP = {
    yuki: { n: 4, r: 215, off: 0 },
  };
  function _satellitesHtml(charKey) {
    const cfg = _SAT_MAP[charKey] || _SAT_MAP.yuki;
    const f = v => v.toFixed(1);
    const s = 21; // uydu yarıçapı
    let out = '';
    for (let i = 0; i < cfg.n; i++) {
      const a = (cfg.off + i * (360 / cfg.n)) * Math.PI / 180;
      const x = 300 + cfg.r * Math.cos(a), y = 300 + cfg.r * Math.sin(a);
      // mini sihir çemberi: dış + dash iç + merkez nokta + 4 tık + 3 mikro uydu
      let ticks = '';
      for (let t = 0; t < 4; t++) {
        const ta = (t * 90) * Math.PI / 180;
        ticks += `<line x1="${f(Math.cos(ta)*(s-3.5))}" y1="${f(Math.sin(ta)*(s-3.5))}" x2="${f(Math.cos(ta)*s)}" y2="${f(Math.sin(ta)*s)}" stroke-width="1.1"/>`;
      }
      let micro = '';
      for (let m = 0; m < 3; m++) {
        const ma = (i * 40 + m * 120) * Math.PI / 180;
        micro += `<circle cx="${f(Math.cos(ma)*(s+6))}" cy="${f(Math.sin(ma)*(s+6))}" r="1.7" fill="var(--hr-accent)" stroke="none"/>`;
      }
      out += `<g transform="translate(${f(x)},${f(y)})">
        <circle r="${s}" stroke-width="1.2" opacity="0.9"/>
        <circle r="${f(s*0.66)}" stroke-width="0.7" stroke-dasharray="2.2 3.4" opacity="0.7"/>
        <circle r="2.2" fill="var(--hr-accent)" stroke="none" opacity="0.95"/>
        ${ticks}${micro}
      </g>`;
    }
    return out;
  }
  // İnce telkari: hairline çemberler + boncuklu kesişimler (detay yoğunluğu)
  function _filigreeHtml() {
    const f = v => v.toFixed(1);
    let beads = '';
    for (let i = 0; i < 12; i++) {
      const a = (i * 30 - 90) * Math.PI / 180;
      beads += `<circle cx="${f(300 + 230 * Math.cos(a))}" cy="${f(300 + 230 * Math.sin(a))}" r="1.6" fill="var(--hr-accent)" stroke="none"/>`;
    }
    return `
      <circle cx="300" cy="300" r="230" stroke-width="0.5" stroke-dasharray="0.5 5" opacity="0.5"/>
      <circle cx="300" cy="300" r="226" stroke-width="0.4" opacity="0.3"/>
      <circle cx="300" cy="300" r="196" stroke-width="0.5" stroke-dasharray="14 5 2 5" opacity="0.42"/>
      <circle cx="300" cy="300" r="168" stroke-width="0.4" stroke-dasharray="1 4" opacity="0.35"/>
      <g opacity="0.8">${beads}</g>`;
  }
  // Merkez starburst — çekirdekten taşan kısa ışıma demeti
  function _starburstHtml() {
    const f = v => v.toFixed(1);
    let lines = '';
    for (let i = 0; i < 16; i++) {
      const a = (i * 22.5) * Math.PI / 180;
      const long = i % 4 === 0;
      const r1 = 64, r2 = long ? 88 : 76;
      lines += `<line x1="${f(300+r1*Math.cos(a))}" y1="${f(300+r1*Math.sin(a))}" x2="${f(300+r2*Math.cos(a))}" y2="${f(300+r2*Math.sin(a))}" stroke-width="${long ? 1 : 0.5}" opacity="${long ? 0.55 : 0.3}"/>`;
    }
    return lines;
  }

  // ── SVG halka (viewBox 600) ──
  function _ringSvg(charKey) {
    const spec = _charRingSpec(charKey || _char());
    const name = (charKey || _char()).toUpperCase();
    const midTxt = (spec.outerTxt + '·' + spec.outerTxt).slice(0, 84);
    // 24 radyal hüzme
    let rays = '';
    for (let i = 0; i < 24; i++) {
      const a = (i * 15) * Math.PI / 180;
      const x1 = 300 + Math.cos(a) * 62,  y1 = 300 + Math.sin(a) * 62;
      const x2 = 300 + Math.cos(a) * 292, y2 = 300 + Math.sin(a) * 292;
      rays += `<line x1="${x1.toFixed(1)}" y1="${y1.toFixed(1)}" x2="${x2.toFixed(1)}" y2="${y2.toFixed(1)}"/>`;
    }
    // Ses-spektrum: çemberi saran 64 çubuk
    let bars = '';
    const NB = 64;
    for (let i = 0; i < NB; i++) {
      const ang = (i * (360 / NB)).toFixed(2);
      const d = (((i * 37) % 100) / 100 * 1.4).toFixed(2);
      bars += `<g transform="rotate(${ang} 300 300)"><rect class="hr-bar" x="297.4" y="30" width="5.2" height="24" rx="1.4" style="animation-delay:-${d}s"/></g>`;
    }
    // Kardinal çıpa noktaları + haç çizgileri (8, r=278)
    let anchors = '', crosses = '';
    const _f = v => v.toFixed(1);
    for (let i = 0; i < 8; i++) {
      const a = (i * 45 - 90) * Math.PI / 180;
      const ac = Math.cos(a), as = Math.sin(a);
      const x = 300 + 278*ac, y = 300 + 278*as;
      if (i % 2 === 0) {
        anchors += `<path class="hr-anc-card" d="M${_f(x)},${_f(y-9)} L${_f(x+9)},${_f(y)} L${_f(x)},${_f(y+9)} L${_f(x-9)},${_f(y)} Z"/>`;
        const xi=_f(300+255*ac), yi=_f(300+255*as), xo=_f(300+300*ac), yo=_f(300+300*as);
        crosses += `<line x1="${xi}" y1="${yi}" x2="${xo}" y2="${yo}"/>`;
        crosses += `<line x1="${_f(300+300*ac-as*6)}" y1="${_f(300+300*as+ac*6)}" x2="${_f(300+300*ac+as*6)}" y2="${_f(300+300*as-ac*6)}"/>`;
      } else {
        anchors += `<circle cx="${_f(x)}" cy="${_f(y)}" r="2.5" class="hr-anc-diag"/>`;
      }
    }
    return `
<svg id="hr-ring" viewBox="0 0 600 600" xmlns="http://www.w3.org/2000/svg">
  <defs>
    <path id="hr-rp-out" d="M 300,300 m -218,0 a 218,218 0 1,1 436,0 a 218,218 0 1,1 -436,0"/>
    <path id="hr-rp-mid" d="M 300,300 m -201,0 a 201,201 0 1,1 402,0 a 201,201 0 1,1 -402,0"/>
    <path id="hr-rp-in"  d="M 300,300 m -148,0 a 148,148 0 1,1 296,0 a 148,148 0 1,1 -296,0"/>
    <radialGradient id="hr-coreglow">
      <stop offset="0%"  stop-color="var(--hr-accent)" stop-opacity="0.32"/>
      <stop offset="55%" stop-color="var(--hr-accent)" stop-opacity="0.10"/>
      <stop offset="100%" stop-color="var(--hr-accent)" stop-opacity="0"/>
    </radialGradient>
  </defs>
  <g class="hr-layer hr-rays" stroke="var(--hr-accent)" stroke-width="0.8">${rays}</g>
  <circle cx="300" cy="300" r="288" fill="none" stroke="var(--hr-accent)" stroke-width="1" opacity="0.14"/>
  <g class="hr-cardinal-cross" fill="none" stroke="var(--hr-accent)" stroke-width="0.9" opacity="0.52">${crosses}</g>
  <g class="hr-anchor-nodes" fill="none" stroke="var(--hr-accent)" stroke-width="1.1" filter="drop-shadow(0 0 5px var(--hr-accent))">${anchors}</g>
  <g class="hr-layer hr-tick-ring" fill="none" stroke="var(--hr-accent)">${spec.tickRing}</g>
  <g class="hr-layer hr-seg-ring" fill="none" stroke="var(--hr-accent)" filter="drop-shadow(0 0 5px var(--hr-accent))">${spec.segRing}</g>
  <g class="hr-layer hr-fili" fill="none" stroke="var(--hr-accent)">${_filigreeHtml()}</g>
  <g class="hr-layer hr-mandala" fill="none" stroke="var(--hr-accent)" stroke-width="1" opacity="0.32" filter="drop-shadow(0 0 5px var(--hr-accent))">${spec.mandala}</g>
  <g class="hr-layer hr-sat-ring" fill="none" stroke="var(--hr-accent)" opacity="0.75" filter="drop-shadow(0 0 4px var(--hr-accent))">${_satellitesHtml(charKey || _char())}</g>
  <g class="hr-spectrum">${bars}</g>
  <g class="hr-layer hr-rune-outer"><text><textPath href="#hr-rp-out">${spec.outerTxt}</textPath></text></g>
  <g class="hr-layer hr-thin-rings" fill="none" stroke="var(--hr-accent)">
    <circle cx="300" cy="300" r="184" stroke-width="0.9" stroke-dasharray="1 7" opacity="0.4"/>
    <circle cx="300" cy="300" r="177" stroke-width="0.6" opacity="0.28"/>
  </g>
  <g class="hr-layer hr-rune-mid"><text><textPath href="#hr-rp-mid">${midTxt}</textPath></text></g>
  <g class="hr-layer hr-rune-inner"><text><textPath href="#hr-rp-in">${spec.innerTxt}</textPath></text></g>
  <g class="hr-layer hr-node-ring" fill="none" stroke="var(--hr-accent)" filter="drop-shadow(0 0 4px var(--hr-accent))">${spec.nodeRing}</g>
  ${spec.innerOrg}
  <g class="hr-layer hr-starburst" stroke="var(--hr-accent)">${_starburstHtml()}</g>
  <circle cx="300" cy="300" r="86" fill="url(#hr-coreglow)"/>
  <g id="hr-poly"></g>
  <text id="hr-core-name" x="307" y="311">${name}</text>
  <text id="hr-core-status" x="303" y="341">${_stateLbl(_curState)}</text>
</svg>`;
  }

  // ── Zaman çemberi: en dış sarıcı katman (dekoratif dönen bant + canlı kronometre) ──
  //  Bant yavaşça döner (dekoratif, blueprint stili); kronometre (dakika yayı + saniye
  //  göstergesi) gerçek zamanı yansıtır ve _tickClock içinde her saniye güncellenir.
  function _timeRingSvg() {
    const f = v => v.toFixed(1);
    // 60 dakika çentiği (her 5'te bir uzun = saat işareti)
    let ticks = '';
    for (let i = 0; i < 60; i++) {
      const a = (i * 6 - 90) * Math.PI / 180, c = Math.cos(a), s = Math.sin(a);
      const big = (i % 5 === 0);
      const r1 = big ? 288 : 295, r2 = 300, w = big ? 1.8 : 0.8, op = big ? 0.85 : 0.4;
      ticks += `<line x1="${f(300+r1*c)}" y1="${f(300+r1*s)}" x2="${f(300+r2*c)}" y2="${f(300+r2*s)}" stroke-width="${w}" opacity="${op}"/>`;
    }
    // 4 kardinal düğüm (elmas)
    let nodes = '';
    for (let i = 0; i < 4; i++) {
      const a = (i * 90 - 90) * Math.PI / 180, c = Math.cos(a), s = Math.sin(a);
      const x = 300 + 293 * c, y = 300 + 293 * s;
      nodes += `<path d="M${f(x)},${f(y-5)} L${f(x+5)},${f(y)} L${f(x)},${f(y+5)} L${f(x-5)},${f(y)} Z"/>`;
    }
    // Çevre metni (blueprint etiket — bantla birlikte döner)
    const label = '· ZUZU CHRONOSPHERE · SYS.TIME · 時 · AETHER FLOW · 刻 ';
    const txt = (label + label).slice(0, 90);
    return `
<svg id="hr-time" viewBox="0 0 600 600" preserveAspectRatio="xMidYMid meet" xmlns="http://www.w3.org/2000/svg">
  <defs>
    <path id="hr-time-tp" d="M 300,300 m -293,0 a 293,293 0 1,1 586,0 a 293,293 0 1,1 -586,0"/>
  </defs>

  <!-- Dekoratif bant (yavaş döner) -->
  <g class="hr-layer hr-time-band">
    <circle cx="300" cy="300" r="300" fill="none" stroke="var(--hr-accent)" stroke-width="0.8" opacity="0.5"/>
    <circle cx="300" cy="300" r="286" fill="none" stroke="var(--hr-accent)" stroke-width="0.8" opacity="0.32"/>
    <g class="hr-time-ticks" stroke="var(--hr-accent)">${ticks}</g>
    <g class="hr-time-nodes" fill="var(--hr-accent)">${nodes}</g>
    <text class="hr-time-txt"><textPath href="#hr-time-tp" startOffset="0">${txt}</textPath></text>
  </g>

  <!-- Canlı kronometre (dönmez; _tickClock günceller) -->
  <g id="hr-chrono">
    <circle cx="300" cy="300" r="282" fill="none" stroke="var(--hr-accent)" stroke-width="1.4" opacity="0.12"/>
    <circle id="hr-min-arc" cx="300" cy="300" r="282" fill="none" stroke="var(--hr-accent)" stroke-width="2.4"
            stroke-linecap="round" opacity="0.9" pathLength="360" stroke-dasharray="0 360"
            transform="rotate(-90 300 300)" filter="drop-shadow(0 0 4px var(--hr-accent))"/>
    <g id="hr-sec-hand" transform="rotate(0 300 300)" filter="drop-shadow(0 0 5px var(--hr-accent))">
      <line x1="300" y1="-2" x2="300" y2="24" stroke="var(--hr-accent)" stroke-width="2.6" stroke-linecap="round"/>
      <circle cx="300" cy="11" r="3.4" fill="var(--hr-accent)"/>
    </g>
  </g>
</svg>`;
  }

  // ② Sekme çarkı (TAB_WHEEL/_wheelHtml) → Odaklı Halka'nın SEKMELER grubuna taşındı (2026-10-11)

  // ③b İç karakter tekerleği (halka çekirdeğinde, RCW=17)
  const CHARS_CW = [
    { key:'yuki', icon:'❄', clr:'#a0d8ff', lbl:'YUKI' },
  ];
  // 2026-11-14 (ürün kararı): tek karakter Yuki — öbür dört karakter kaldırıldı. Kişisel Yuki gibi
  // tek karakterde Odaklı Halka'nın KARAKTER grubu hiç çizilmez (`OD_GRUPLAR`); yeni karakter
  // eklenirse (buraya + chat-modes karakter listesine) grup kendiliğinden geri gelir.
  // Açık kaynak sürüm: karakterlerin hepsi açık (kademe kilidi yok).
  // 2026-08-08: liste artık chat-modes.js'te (karakter listesinin sahibi orası) —
  // burada kopyası tutulursa ikisi ayrışır.
  // Fallback: chat-modes yüklenmemişse (widget/izole test) hepsi açık.
  // ⚠️ Dizi chat-modes.js'te sunucu cevabıyla **yerinde** güncellenir; burada tutulan
  // referans aynı nesnedir → tıklama kapıları kendiliğinden tazelenir. Tazelenmeyen
  // tek şey bir kez çizilmiş DOM'dur (aşağıdaki olay dinleyicisi onu üstleniyor).
  const _UNLOCKED_CHARS = window.MODE_UNLOCKED_CHARS || CHARS_CW.map(c => c.key);
  const _charLocked = (k) => _UNLOCKED_CHARS.indexOf(k) === -1;
  function _lockToast() { /* kilit yok — sessiz */ }

  // Halka sahnesi, yetki cevabı gelmeden ÖNCE kurulmuş olabilir (açılış modu HALKA
  // ise yarış gerçek). O durumda ödeyen müşteri kilit rozetlerini görmeye devam
  // ederdi — tıklayınca çalışırdı ama tıklamayı denemezdi. Odaklı Halka kilidi her
  // çizimde _charLocked'tan okur → yetki gelince yeniden çizmek yeter.
  function _kilitRozetleriniTazele() { if (_odGrup === 'kar') _odCiz(); }
  document.addEventListener('yuki:karakter-kilitleri', _kilitRozetleriniTazele);

  // ════════════════════════════════════════════════════════════════════
  // ODAKLI HALKA — merkez menüsü (kişisel 933779b'nin ürün çevirisi, 2026-10-11)
  //  Eski hâl: sekme düğmeleri (r=38%) + 5 karakter (r=17%) AYNI ANDA, 7px etiketler,
  //  anlamsız işaretler (≋ ⌂). Yeni hâl: aynı anda TEK grup (SEKMELER · KARAKTER),
  //  büyük düğümler, halkanın merkezi bilgi ekranı (ad · ne işe yarar · kısayol).
  //  Ürün farkları:
  //   · SİTELER (2026-10-11 — geliştirici kararı): müşterinin KENDİ kısayolları,
  //     depo js/halka-siteler.js (localStorage, sunucusuz). Kişiselden fark: varsayılan
  //     site yok; açılış iframe değil SİSTEM TARAYICISI (gerekçe o dosyanın başında);
  //     ekleme/yönetim ayrı bir widget değil, halkanın merkezindeki panel (.hr-od-panel).
  //   · Sekmeler gezinme çubuğundan (#tab-items .tab-btn) OKUNUR: ad, ikon ve
  //     görünürlük oradan → kademe kapısı (tab-nav.js `hidden`) kendiliğinden geçerli,
  //     ikinci bir liste tutulmaz (ayrışan iki liste = ödeme duvarında delik).
  //   · Kilitli karakter görünür ama kilitli: tıklayınca _lockToast, geçiş YOK.
  //  Açma/kapama #hr-ring-wrap.hr-wheel-open — kara-mana-goz bu sınıfa bakıp diski
  //  karartıyor, adını değiştirme. Her çizim `halka:odak-ciz` olayı atar (tema yuvaları).
  //  Seçili grup: localStorage halka_menu_grup_v1.
  // ════════════════════════════════════════════════════════════════════
  // Kısayollar core.js tabMap ile AYNI (arayüz turu, 2026-11-13: PANEL sekmesi kalktı, YEDEK eklendi):
  // 1 chat · 2 planner · 3 hq · 4 map · 5 ajan · 6 yedek · 7 galeri · 8 dosya
  const OD_KISAYOL = { chat: 1, planner: 2, hq: 3, map: 4, ajan: 5, yedek: 6, galeri: 7, dosya: 8 };
  // Tek karakterde KARAKTER grubu yok (kişisel hud-ring.js ile aynı kapı) — kayıtlı 'kar' seçimi
  // `_odGrupKayitli` kapısında geçersiz sayılır, SEKMELER'e döner.
  const OD_GRUPLAR = ['sekme', ...(CHARS_CW.length > 1 ? ['kar'] : []), 'site'];
  const _HS = () => window.HalkaSiteler || null;
  let _odPanel = null;   // null · 'ekle' · 'tum' — merkezde açık site paneli
  let _odGrup = 'sekme', _odSec = null;
  const _odGrupKayitli = () => { try { const g = localStorage.getItem('halka_menu_grup_v1'); return OD_GRUPLAR.indexOf(g) !== -1 ? g : null; } catch (_) { return null; } };
  _odGrup = _odGrupKayitli() || 'sekme';

  // SİTELER grubu herkese açık (açık kaynak sürüm: kademe kilidi kaldırıldı 2026-10-17).
  const _siteKilitli = () => false;
  const _odEsc = v => String(v == null ? '' : v).replace(/[&<>"']/g, c => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));

  // Karakter seviyesi — intro-sequences.js FAZ 21'in yazdığı XP (yukiEvolution), aynı eşikler
  const _OD_XP = [0, 100, 250, 500, 1000, 2500, 5000, 10000, 20000];
  function _odSeviye(key) {
    try {
      const xp = (JSON.parse(localStorage.getItem('yukiEvolution') || '{}')[key] || {}).xp || 0;
      for (let i = _OD_XP.length - 1; i >= 0; i--) if (xp >= _OD_XP[i]) return i + 1;
    } catch (_) {}
    return 1;
  }

  const _OD_IK = {
    arti: '<svg viewBox="0 0 24 24" aria-hidden="true"><path d="M12 5v14M5 12h14"/></svg>',
    izgara: '<svg viewBox="0 0 24 24" aria-hidden="true"><rect x="4" y="4" width="6" height="6" rx="1"/><rect x="14" y="4" width="6" height="6" rx="1"/><rect x="4" y="14" width="6" height="6" rx="1"/><rect x="14" y="14" width="6" height="6" rx="1"/></svg>',
  };

  function _odOgeler() {
    if (_odGrup === 'site') {
      const hs = _HS();
      const l = hs ? hs.liste() : [];
      const o = l.map(st => ({ tur: 'site', id: st.id, ad: st.ad, ne: st.host, url: st.url,
        harf: (Array.from(st.ad)[0] || '?').toUpperCase() }));
      if (hs && l.length < hs.MAKS) o.push({ tur: 'ekle', id: '__ekle', ad: _hrt('hudring.od.site.ekle'), ne: _hrt('hudring.od.ne.ekle'), ik: _OD_IK.arti });
      o.push({ tur: 'tum', id: '__tum', ad: _hrt('hudring.od.site.tum'), ne: _hrt('hudring.od.ne.tum', { n: l.length, m: hs ? hs.MAKS : 0 }), ik: _OD_IK.izgara });
      return o;
    }
    if (_odGrup === 'kar') {
      const cur = _char();
      return CHARS_CW.map(c => ({ tur: 'kar', id: c.key, ad: c.lbl.charAt(0) + c.lbl.slice(1).toLowerCase(),
        ne: _hrt('hudring.od.unvan.' + c.key), harf: c.lbl.charAt(0), renk: c.clr,
        aktif: c.key === cur, kilit: _charLocked(c.key), lv: _odSeviye(c.key) }));
    }
    return [...document.querySelectorAll('#tab-items .tab-btn[data-tab]')]
      .filter(b => !b.hidden)
      .map(b => {
        const id = b.dataset.tab;
        const lbl = (b.querySelector('.tab-lbl') || b).textContent.trim();
        const svg = b.querySelector('.tab-icon svg');
        return { tur: 'sekme', id, ad: lbl, ne: _hrt('hudring.od.ne.' + id), no: OD_KISAYOL[id],
                 ik: svg ? svg.outerHTML : '', aktif: b.getAttribute('aria-selected') === 'true' };
      });
  }

  function _odMerkezHtml(o) {
    if (!o) return '';
    if (_odPanel) return _odPanelHtml();
    if (o.tur === 'site' || o.tur === 'ekle' || o.tur === 'tum') {
      const ip = o.tur === 'site' ? _hrt('hudring.od.ipucu.site') : _hrt('hudring.od.ipucu.tikla');
      return `<span class="hr-od-ust">${_odEsc(_hrt('hudring.od.ust.site'))}</span><b class="hr-od-ad">${_odEsc(o.ad)}</b>` +
             `<span class="hr-od-ne">${_odEsc(o.ne)}</span><span class="hr-od-ipucu">${_odEsc(ip)}</span>`;
    }
    const ust = o.tur === 'sekme' ? _hrt('hudring.od.ust.sekme')
      : o.kilit ? _hrt('hudring.od.ust.kilit')
      : o.aktif ? _hrt('hudring.od.ust.konusan') : _hrt('hudring.od.ust.kar');
    const ipucu = o.tur === 'sekme' ? _hrt('hudring.od.ipucu.sekme', { no: o.no })
      : o.lv > 1 ? _hrt('hudring.od.ipucu.seviye', { lv: o.lv }) : _hrt('hudring.od.ipucu.kar');
    const renk = o.tur === 'kar' ? ` style="color:${o.renk}"` : '';
    return `<span class="hr-od-ust">${_odEsc(ust)}</span><b class="hr-od-ad"${renk}>${_odEsc(o.ad)}</b>` +
           `<span class="hr-od-ne">${_odEsc(o.ne)}</span><span class="hr-od-ipucu">${_odEsc(ipucu)}</span>`;
  }

  function _odHtml() {
    const ogeler = _odOgeler();
    if (!ogeler.some(o => o.id === _odSec)) _odSec = (ogeler.find(o => o.aktif) || ogeler[0] || {}).id || null;
    const n = ogeler.length, R = 38;   // % — eski sekme çarkıyla aynı yarıçap (tema yuvaları r=228)
    const bas = -90 + 180 / Math.max(1, n);   // tam tepeye düğüm koyma: grup anahtarıyla çakışır
    const dugum = ogeler.map((o, i) => {
      const a = (bas + i * 360 / n) * Math.PI / 180;
      const x = (50 + R * Math.cos(a)).toFixed(2), y = (50 + R * Math.sin(a)).toFixed(2);
      const ici = o.ik ? `<span class="hr-od-ik">${o.ik}</span>` : `<span class="hr-od-harf">${_odEsc(o.harf)}</span>`;
      const renk = o.tur === 'kar' ? `;--od-k:${o.renk}` : '';
      const lv = o.tur === 'kar' && o.lv > 1 && !o.kilit ? `<span class="hr-od-lv" aria-hidden="true">${o.lv}</span>` : '';
      const kilit = o.kilit ? '<span class="hr-od-kilit" aria-hidden="true"><svg viewBox="0 0 24 24"><rect width="16" height="11" x="4" y="11" rx="2"/><path d="M8 11V7a4 4 0 0 1 8 0v4"/></svg></span>' : '';
      const etiket = o.ad + ' — ' + o.ne;
      return `<button type="button" class="hr-od-dugum hr-od-${o.tur}${o.id === _odSec ? ' hr-od-sec' : ''}${o.aktif ? ' hr-od-aktif' : ''}${o.kilit ? ' hr-od-kilitli' : ''}"` +
        ` data-od="${_odEsc(o.id)}" data-od-tur="${o.tur}" style="left:${x}%;top:${y}%;--od-gec:${(i * 0.035).toFixed(3)}s${renk}"` +
        ` aria-label="${_odEsc(etiket)}"${o.aktif ? ' aria-current="true"' : ''}>${ici}${lv}${kilit}` +
        `<span class="hr-od-etiket"${o.tur === 'kar' || o.tur === 'site' ? ' lang="en"' : ''}>${_odEsc(o.ad)}</span></button>`;   // lang=en: ad Ingilizce kuralla buyuk harfe cevrilsin (tr kurali i harfini noktali yapar)
    }).join('');
    const anahtar = OD_GRUPLAR.map(k => {
      const kilitli = k === 'site' && _siteKilitli();
      const rozet = kilitli ? '<span class="hr-od-kilit" aria-hidden="true"><svg viewBox="0 0 24 24"><rect width="16" height="11" x="4" y="11" rx="2"/><path d="M8 11V7a4 4 0 0 1 8 0v4"/></svg></span>' : '';
      const etiket = '';
      return `<button type="button" class="hr-od-grup${k === _odGrup ? ' hr-od-grup-sec' : ''}${kilitli ? ' hr-od-grup-kilitli' : ''}" data-od-grup="${k}" aria-pressed="${k === _odGrup}"${etiket}>${_odEsc(_hrt('hudring.od.grup.' + k))}${rozet}</button>`;
    }).join('');
    return `<div class="hr-od-ortu" aria-hidden="true"></div>` +
      `<div class="hr-od-anahtar" role="group" aria-label="${_odEsc(_hrt('hudring.od.grup-etiket'))}">${anahtar}</div>` + dugum +
      `<div class="hr-od-merkez${_odPanel ? ' hr-od-panelli' : ''}" aria-live="${_odPanel ? 'off' : 'polite'}">${_odMerkezHtml(ogeler.find(o => o.id === _odSec))}</div>`;
  }

  // ── SİTELER paneli (merkezde): SİTE EKLE formu · TÜM SİTELER listesi ──
  // Modal değil: halkanın içinde, merkez bilgi ekranının yerini alır (PRODUCT.md anti-ref).
  function _odPanelHtml() {
    const hs = _HS();
    if (!hs) return '';
    const l = hs.liste();
    const kapat = `<button type="button" class="hr-sp-kapat" data-sp="kapat" aria-label="${_odEsc(_hrt('hudring.od.site.kapat'))}"><svg viewBox="0 0 24 24" aria-hidden="true"><path d="M6 6l12 12M18 6 6 18"/></svg></button>`;
    if (_odPanel === 'ekle') {
      return `<div class="hr-od-panel" role="group" aria-labelledby="hr-sp-baslik">${kapat}` +
        `<b class="hr-sp-baslik" id="hr-sp-baslik">${_odEsc(_hrt('hudring.od.site.ekle'))}</b>` +
        `<form class="hr-sp-form" novalidate autocomplete="off">` +
        `<label class="gorsel-gizli" for="hr-sp-adres">${_odEsc(_hrt('hudring.od.site.adres'))}</label>` +
        `<input id="hr-sp-adres" class="hr-sp-in" type="url" inputmode="url" spellcheck="false" maxlength="2048" required placeholder="${_odEsc(_hrt('hudring.od.site.adres-ipucu'))}">` +
        `<label class="gorsel-gizli" for="hr-sp-ad">${_odEsc(_hrt('hudring.od.site.ad'))}</label>` +
        `<input id="hr-sp-ad" class="hr-sp-in" type="text" maxlength="24" placeholder="${_odEsc(_hrt('hudring.od.site.ad-ipucu'))}">` +
        `<span class="hr-sp-hata" id="hr-sp-hata" role="alert"></span>` +
        `<div class="hr-sp-eylem"><button type="button" class="hr-sp-dg" data-sp="iptal">${_odEsc(_hrt('hudring.od.site.iptal'))}</button>` +
        `<button type="submit" class="hr-sp-dg hr-sp-birincil">${_odEsc(_hrt('hudring.od.site.kaydet'))}</button></div></form></div>`;
    }
    const satir = l.map(st =>
      `<li class="hr-sp-satir"><button type="button" class="hr-sp-ac" data-sp="ac" data-id="${_odEsc(st.id)}" title="${_odEsc(st.url)}">` +
      `<b>${_odEsc(st.ad)}</b><span>${_odEsc(st.host)}</span></button>` +
      `<button type="button" class="hr-sp-sil" data-sp="sil" data-id="${_odEsc(st.id)}" aria-label="${_odEsc(_hrt('hudring.od.site.sil', { ad: st.ad }))}">` +
      `<svg viewBox="0 0 24 24" aria-hidden="true"><path d="M6 6l12 12M18 6 6 18"/></svg></button></li>`).join('');
    const ekle = l.length < hs.MAKS
      ? `<button type="button" class="hr-sp-dg hr-sp-birincil" data-sp="ekle">+ ${_odEsc(_hrt('hudring.od.site.ekle'))}</button>`
      : `<span class="hr-sp-not">${_odEsc(_hrt('hudring.od.site.dolu', { m: hs.MAKS }))}</span>`;
    return `<div class="hr-od-panel" role="group" aria-labelledby="hr-sp-baslik">${kapat}` +
      `<b class="hr-sp-baslik" id="hr-sp-baslik">${_odEsc(_hrt('hudring.od.site.tum'))} <span>${l.length}/${hs.MAKS}</span></b>` +
      (l.length ? `<ul class="hr-sp-liste">${satir}</ul>` : `<span class="hr-sp-not">${_odEsc(_hrt('hudring.od.site.bos'))}</span>`) +
      `<div class="hr-sp-eylem">${ekle}</div></div>`;
  }

  function _odPanelAc(tur) {
    _odPanel = tur;
    _odCiz();
    const ilk = document.querySelector(tur === 'ekle' ? '#hr-sp-adres' : '#hr-odak .hr-od-panel button');
    if (ilk) setTimeout(() => ilk.focus(), 30);
  }
  function _odPanelKapat() {
    if (!_odPanel) return;
    _odPanel = null;
    _odCiz();
  }
  function _odSiteHata(kod) {
    const el = document.getElementById('hr-sp-hata');
    if (el) el.textContent = _hrt('hudring.od.site.hata.' + kod);
    const inp = document.getElementById(kod === 'var' || kod === 'dolu' || kod === 'kayit' ? 'hr-sp-ad' : 'hr-sp-adres');
    if (inp && kod !== 'kayit') { inp.setAttribute('aria-invalid', 'true'); inp.focus(); }
  }
  function _odSiteAc(url) {
    const hs = _HS();
    if (!hs || !hs.ac(url)) { if (window.showToast) window.showToast(_hrt('hudring.od.site.hata.gecersiz'), 'warn', 2600); return false; }
    if (window.showToast) window.showToast(_hrt('hudring.od.site.acildi'), 'ok', 1800);
    return true;
  }
  document.addEventListener('halka:siteler-degisti', () => { if (_odGrup === 'site') _odCiz(); });
  // Yetki ASYNC gelir (tab-nav.js _yetkiDuyur): kayıtlı SİTELER tercihine dön.
  document.addEventListener('yuki:entitlements', () => {
    if (!_siteKilitli() && _odGrup !== 'site' && _odGrupKayitli() === 'site') { _odGrup = 'site'; _odSec = null; }
    _odCiz();
  });

  // TÜM SİTELER listesi sığmıyorsa alt kenar solar (hud-ring.css .hr-sp-kayar); uçta kalkar.
  function _odListeIpucu(ul) {
    if (!ul) return;
    const yaz = () => {
      ul.classList.toggle('hr-sp-kayar', ul.scrollHeight > ul.clientHeight + 1);
      ul.classList.toggle('hr-sp-son', ul.scrollTop + ul.clientHeight >= ul.scrollHeight - 2);
    };
    ul.addEventListener('scroll', yaz, { passive: true });
    requestAnimationFrame(yaz);
  }

  function _odCiz() {
    const el = document.getElementById('hr-odak');
    if (!el) return;
    if (_odGrup === 'site' && _siteKilitli()) { _odGrup = 'sekme'; _odSec = null; _odPanel = null; }   // tercih localStorage'da kalır
    el.innerHTML = _odHtml();
    _odListeIpucu(el.querySelector('.hr-sp-liste'));
    const n = el.querySelectorAll('.hr-od-dugum').length;
    document.dispatchEvent(new CustomEvent('halka:odak-ciz', { detail: { n, bas: -90 + 180 / Math.max(1, n) } }));
  }

  function _odMerkezYaz(id) {
    const o = _odOgeler().find(x => x.id === id);
    const m = document.querySelector('#hr-odak .hr-od-merkez');
    if (!o || !m) return;
    _odSec = id;
    m.innerHTML = _odMerkezHtml(o);
    document.querySelectorAll('#hr-odak .hr-od-dugum').forEach(b => b.classList.toggle('hr-od-sec', b.dataset.od === id));
  }

  function _odBagla(wrap) {
    const kok = wrap.querySelector('#hr-odak');
    if (!kok) return;
    // Üstüne gelince / klavye odağında merkez o öğeyi anlatır
    const anlat = e => { if (_odPanel) return; const b = e.target.closest('.hr-od-dugum'); if (b && b.dataset.od !== _odSec) _odMerkezYaz(b.dataset.od); };
    kok.addEventListener('mouseover', anlat);
    kok.addEventListener('focusin', anlat);
    kok.addEventListener('click', e => {
      const sp = e.target.closest('[data-sp]');
      if (sp && kok.contains(sp)) {
        e.stopPropagation();
        const ne = sp.dataset.sp, hs = _HS();
        if (ne === 'kapat' || ne === 'iptal') _odPanelKapat();
        else if (ne === 'ekle') _odPanelAc('ekle');
        else if (ne === 'sil' && hs) { hs.sil(sp.dataset.id); _odPanel = 'tum'; _odCiz(); const s2 = kok.querySelector('.hr-sp-sil, [data-sp="ekle"]'); if (s2) s2.focus(); }
        else if (ne === 'ac' && hs) {
          const st = hs.liste().find(x => x.id === sp.dataset.id);
          if (st && _odSiteAc(st.url)) { _odPanel = null; wrap.classList.remove('hr-wheel-open'); }
        }
        return;
      }
      if (e.target.closest('.hr-od-panel')) { e.stopPropagation(); return; }   // panelin boş yeri menüyü kapatmaz
      const g = e.target.closest('.hr-od-grup');
      if (g) {
        e.stopPropagation();
        _odPanel = null;
        _odGrup = g.dataset.odGrup; _odSec = null;
        try { localStorage.setItem('halka_menu_grup_v1', _odGrup); } catch (_) {}
        _odCiz();
        const yeni = kok.querySelector(`.hr-od-grup[data-od-grup="${_odGrup}"]`);
        if (yeni) yeni.focus();
        return;
      }
      const b = e.target.closest('.hr-od-dugum');
      if (!b) return;
      e.stopPropagation();
      const id = b.dataset.od;
      if (b.dataset.odTur === 'sekme') {
        wrap.classList.remove('hr-wheel-open');
        if (typeof window.switchTab === 'function') window.switchTab(id);
        return;
      }
      if (b.dataset.odTur === 'site') {
        const st = (_HS() ? _HS().liste() : []).find(x => x.id === id);
        if (st && _odSiteAc(st.url)) wrap.classList.remove('hr-wheel-open');
        return;
      }
      if (b.dataset.odTur === 'ekle' || b.dataset.odTur === 'tum') { _odPanelAc(b.dataset.odTur); return; }
      if (_charLocked(id)) { _lockToast(id); return; }
      if (window.setCharacter) window.setCharacter(id);
      wrap.classList.add('hr-char-flash');
      setTimeout(() => wrap.classList.remove('hr-char-flash'), 500);
      setTimeout(_odCiz, 60);
    });
    // Site formu: Enter = kaydet (form submit) · yazarken hata satırı temizlenir
    kok.addEventListener('submit', e => {
      const f = e.target.closest('.hr-sp-form');
      if (!f) return;
      e.preventDefault();
      const hs = _HS();
      if (!hs) return;
      const r = hs.ekle((document.getElementById('hr-sp-ad') || {}).value, (document.getElementById('hr-sp-adres') || {}).value);
      if (!r.ok) { _odSiteHata(r.hata); return; }
      _odPanel = 'tum';
      _odCiz();
      if (window.showToast) window.showToast(_hrt('hudring.od.site.eklendi', { ad: r.site.ad }), 'ok', 1800);
      const odak = kok.querySelector('[data-sp="ekle"], .hr-sp-ac');
      if (odak) odak.focus();
    });
    kok.addEventListener('input', e => {
      if (!e.target.classList || !e.target.classList.contains('hr-sp-in')) return;
      e.target.removeAttribute('aria-invalid');
      const h = document.getElementById('hr-sp-hata');
      if (h) h.textContent = '';
    });
    // Panelde Esc yalnız paneli kapatır (yazı alanında da) — menü açık kalır
    kok.addEventListener('keydown', e => {
      if (e.key === 'Escape' && _odPanel) { e.preventDefault(); e.stopPropagation(); _odPanelKapat(); const t = kok.querySelector('.hr-od-tum, .hr-od-ekle'); if (t) t.focus(); }
    });
    // Açıkken: Esc kapatır · ← → grup değiştirir
    document.addEventListener('keydown', e => {
      if (!wrap.classList.contains('hr-wheel-open') || !wrap.isConnected) return;
      if (_odPanel) return;   // panel açıkken ok/Esc panelindir (kok keydown)
      if (e.target.closest && e.target.closest('input, textarea, [contenteditable="true"]')) return;
      if (e.key === 'Escape') { wrap.classList.remove('hr-wheel-open'); return; }
      if (e.key === 'ArrowLeft' || e.key === 'ArrowRight') {
        const adim = e.key === 'ArrowRight' ? 1 : OD_GRUPLAR.length - 1;
        let j = OD_GRUPLAR.indexOf(_odGrup);
        do { j = (j + adim) % OD_GRUPLAR.length; } while (OD_GRUPLAR[j] === 'site' && _siteKilitli());   // kilitli grup okla atlanır
        const hedef = kok.querySelector(`.hr-od-grup[data-od-grup="${OD_GRUPLAR[j]}"]`);
        if (hedef) hedef.click();
        e.preventDefault();
      }
    });
  }

  // ③c Dış orbit (zaman halkasının dışında, widget kısayolları)
  // Dış orbit widget kısayolları kaldırıldı (kullanıcı isteği) — widget'lar sekme çubuğundan açılır
  const ORBIT_NODES = [];
  function _outerOrbitHtml() {
    const RO = 63;
    return ORBIT_NODES.map((o, i) => {
      const a = (-90 + i * (360 / ORBIT_NODES.length)) * Math.PI / 180;
      const x = (50 + RO * Math.cos(a)).toFixed(2);
      const y = (50 + RO * Math.sin(a)).toFixed(2);
      const orbDelay = (i * 0.06).toFixed(2);
      return `<button class="hr-orb-btn" style="left:${x}%;top:${y}%;--orb-delay:${orbDelay}s"
        data-wid="${o.id}" title="${o.lbl}">
        <span class="hr-orb-icon">${o.icon}</span>
        <span class="hr-orb-lbl">${o.lbl}</span>
      </button>`;
    }).join('');
  }

  function _buildStage() {
    const stage = document.createElement('div');
    stage.id = 'hr-stage';
    stage.className = 'hr-idle' + (_anahtarYok() ? ' hr-anahtar-yok' : '');   // sahne yeniden kurulunca anahtar hâli düşmesin
    stage.innerHTML = `
      <div id="hr-particles"></div>
      <div id="hr-clock"><b>--:--:--</b><small>—</small></div>
      <!-- 🔴 2026-09-08 (geliştirici kararı): SOL RAY (#hr-leftrail) KALDIRILDI.
           İçindeki dördü de gitti: başlık «GÖSTERGELER» · KARAKTER seçici ·
           GÖSTERGELER kartı (DURUM/BELLEK/UPTIME) · SİSTEM/vitals · persona ·
           stats · aktif mod · alarmlar. Gerekçe (geliştirici): «hiçbir işe yaramıyor» —
           ölçüldü, üç gösterge de boş veri basıyordu (IDLE · 0 · 1d).

           🔑 KARAKTER DEĞİŞTİRME KAYBOLMADI, ölçülerek doğrulandı: halkanın kendi
           menüsü 5 karakteri de taşıyor; halkaya tıklayınca hr-wheel-open sınıfı
           gelir ve beşi de görünür/tıklanabilir olur. (O gün bu bir karakter
           çarkıydı; 2026-10-11 itibarıyla Odaklı Halka menüsünün KARAKTER grubu —
           kilit kapısı aynen.) Kaldırmadan ÖNCE bu ölçüldü — sol ray tek yol olsaydı bu değişiklik
           kullanıcının 5 karakterini HALKA modunda erişilemez
           kılardı (karakter kilidi dersinin aynısı).

           🧹 ÖLÜ KOD DA TEMİZLENDİ (aynı gün, ikinci adım). Rayın tüm üretici ve
           yenileyici zinciri silindi: _charSelectorHtml · _initCharSelector · _gauge ·
           _vitalsHtml · _personaHtml · _statsHtml · _activeModHtml · _leftAlarmsHtml ·
           _refreshVitals · _refreshPersona · _refreshStats · _refreshGauges ·
           _refreshActiveMode · _refreshLeftAlarms · _initLeftCollapse · _setupLeftDrag ·
           _teardownLeftDrag (JS ~350 satır). CSS karşılıkları o gün BİLEREK bırakıldı ve 2026-09-08'de ayrı bir turda silindi: hud-ring.css dosyasından 56 kural /
           245 satır. Ertelenme sebebi kayda değer — bu depoda ölü CSS avı altı ayrı
           araç körlüğü üretmişti; temizlik ancak kendi öz-sınamalı tarayıcısı
           (scratchpad/olu-css-tara.py) ve kendini kanıtlayan piksel kapısı
           (scratchpad/olu-css-piksel-kapisi.py) yazıldıktan sonra yapıldı.

           🔴 SİLMENİN ASIL SEBEBİ GÖRÜNTÜ DEĞİL, ÖLÇÜM: rayın düğümleri gitmişti ama
           ZAMANLAYICILARI koşmaya devam ediyordu ve var olmayan düğümler için dakikada
           ~35 API isteği atıyordu — vitals 3 sn (ModeData.system, 20/dk) · sol alarm
           10 sn (reminders, 6/dk) · aktif mod 15 sn (/api/modes/list, 4/dk) · gauge +
           istatistik 60 sn'de (health + todoLists + 3× todoTasks, ~5/dk). Hiçbiri hata
           vermiyordu: querySelector null dönüp sessizce çıkıyor, istek yine de atılmış
           oluyordu. 📏 Ders: markup'ı silmek onu besleyen döngüyü susturmaz.

           ⚠️ BU YORUM BİR TEMPLATE LITERAL İÇİNDE — içine ters tırnak YAZMA,
           string'i kapatır ve tüm sahne kurulmaz (halka dahil hiçbir şey çizilmez).
           Ledger'da yazılıydı, yine de düşüldü: ilk sürümünde 3 ters tırnak vardı,
           ölçüm "halka: YOK" dedi, node --check yakaladı. -->
      <div id="hr-ticker"><span id="hr-ticker-txt">${_tickerVarsayilan()}</span></div>
      <div id="hr-ring-wrap">${_ringSvg(_char())}${_timeRingSvg()}<div id="hr-odak">${_odHtml()}</div><div id="hr-outer-orbit">${_outerOrbitHtml()}</div></div>
      <div id="hr-prompt">
        <div id="hr-prompt-text"></div>
        <div id="hr-dots"><span></span><span></span><span></span></div>
        <div id="hr-status">${STATE[_curState].status}</div>
      </div>`;
    // Merkez menüsü (Odaklı Halka): halkaya tıkla → aç/kapat (menünün kendi düğmeleri toggle etmez)
    const wrap = stage.querySelector('#hr-ring-wrap');
    if (wrap) {
      wrap.addEventListener('click', (e) => {
        if (e.target.closest('#hr-odak button')) return;
        if (e.target.closest('.hr-orb-btn')) return;
        const acilacak = !wrap.classList.contains('hr-wheel-open');
        if (acilacak) { _odPanel = null; _odCiz(); }   // kademe/sekme/karakter/site değişmiş olabilir — açarken tazele
        wrap.classList.toggle('hr-wheel-open', acilacak);
      });
      wrap.querySelectorAll('.hr-orb-btn').forEach(btn => {
        btn.addEventListener('click', () => {
          const wid = btn.dataset.wid;
          _showRingWidget(wid);
          const tabBtn = document.querySelector('.hr-tab-btn[data-tab="' + wid + '"]');
          if (tabBtn) tabBtn.classList.add('hr-w-open');
        });
      });
      _odBagla(wrap);
    }

    const pane = document.getElementById('chat-pane');
    const header = document.getElementById('header');
    if (pane && header) header.insertAdjacentElement('afterend', stage);
    else if (pane) pane.prepend(stage);
    return stage;
  }

  // ── Sağ panel — dikey, kategorili widget listesi ──
  /** Liste gövdesi — TEK kaynak `RING_WIDGET_CFG`.
   *
   * 🔴 Markup'ı elle yazma: kişiselde dizi ve HTML ayrı durduğu için
   * ayrışmışlardı (dizide `SİTELER`, ekranda `SİTE`). `data-tab` =
   * `RING_WIDGET_CFG[i].id` — `_initTabs`, kapat düğmesi ve dil tazeleyici bu
   * özniteliğe bağlı, id'leri değiştirme.
   * Grup başlığı dekoratif (aria-hidden) — düğmenin adı zaten okunuyor. */
  function _sideRayHtml() {
    return RING_GRUPLAR.map(g => {
      const uyeler = RING_WIDGET_CFG.filter(w => w.grup === g.ad);
      if (!uyeler.length) return '';
      const bas = `<div class="hr-grup" aria-hidden="true">` +
                  `<span class="hr-grup-ad" data-hr-grup="${g.ad}">${_hrt(g.lk)}</span>` +
                  `<span class="hr-grup-sayi">${uyeler.length}</span>` +
                  `<span class="hr-grup-cizgi"></span></div>`;
      return bas + uyeler.map(w =>
        `<button type="button" class="hr-tab-btn" data-tab="${w.id}" title="${w.label}">` +
        `<span class="hr-tb-icon" aria-hidden="true">${RING_IKON[w.id] || w.icon}</span>` +
        `<span class="hr-tb-label">${w.label}</span></button>`
      ).join('');
    }).join('');
  }

  function _buildSide() {
    const side = document.createElement('div');
    side.id = 'hr-side';
    if (_panelCollapsed) side.classList.add('hr-collapsed');
    side.innerHTML = `
      <div class="hr-side-header">
        <div class="hr-side-title">
          <span class="hr-side-dot"></span>
          <span class="hr-side-name">PANEL</span>
        </div>
        <button type="button" class="hr-collapse-btn" id="hr-collapse-btn" title="${_hrt('hudring.panel.daralt-genislet')}" aria-label="${_hrt('hudring.panel.daralt-genislet')}">${_panelCollapsed ? '▶' : '◀'}</button>
      </div>
      <div class="hr-tabs-bar">${_sideRayHtml()}</div>`;
    document.getElementById('chat-pane').appendChild(side);
    _cekmeceKur();
    _setupSideDrag(side);
    return side;
  }

  /** Sağ kenara yaslı panelin tuvaldeki sol kenarı — widget'lar ve sağ snap
   *  sütunu bunun SOLUNA oturur. Panel gizli/daraltık değil de kullanıcı onu
   *  başka yere sürüklediyse (sağ kenarda değilse) tuvalin tamamı serbest. */
  function _sagSinir(canvas) {
    const side = document.getElementById('hr-side');
    if (!canvas || !side || !side.offsetWidth) return canvas ? canvas.offsetWidth : null;
    const cr = canvas.getBoundingClientRect(), sr = side.getBoundingClientRect();
    const sagda = (cr.right - sr.right) < 40 && (sr.left - cr.left) > cr.width / 2;
    return sagda ? Math.round(sr.left - cr.left) : cr.width;
  }

  function _setupSideDrag(side) {
    const SIDE_POS_KEY = 'yuki_hr_side_pos_v1';
    try {
      const saved = JSON.parse(localStorage.getItem(SIDE_POS_KEY) || 'null');
      if (saved) {
        side.style.right = 'auto';
        side.style.left  = saved.x + 'px';
        side.style.top   = saved.y + 'px';
      }
    } catch(e) {}

    const header = side.querySelector('.hr-side-header');
    if (!header) return;
    let dragging = false, offX = 0, offY = 0;
    header.addEventListener('mousedown', e => {
      if (e.button !== 0 || e.target.closest('button')) return;
      e.preventDefault();
      dragging = true;
      side.classList.add('hr-w-dragging');
      const rect = side.getBoundingClientRect();
      offX = e.clientX - rect.left;
      offY = e.clientY - rect.top;
      side.style.right = 'auto';
    });
    document.addEventListener('mousemove', e => {
      if (!dragging) return;
      const canvas = document.getElementById('chat-pane');
      if (!canvas) return;
      const cr = canvas.getBoundingClientRect();
      const nx = Math.max(0, Math.min(cr.width  - side.offsetWidth,  e.clientX - cr.left - offX));
      const ny = Math.max(0, Math.min(cr.height - side.offsetHeight, e.clientY - cr.top  - offY));
      side.style.left = nx + 'px';
      side.style.top  = ny + 'px';
    });
    document.addEventListener('mouseup', () => {
      if (!dragging) return;
      dragging = false;
      side.classList.remove('hr-w-dragging');
      try {
        localStorage.setItem(SIDE_POS_KEY, JSON.stringify({
          x: parseInt(side.style.left, 10) || 0,
          y: parseInt(side.style.top,  10) || 0,
        }));
      } catch(e) {}
    });
  }

  // ── Widget state yönetimi ──
  function _loadRingState() {
    try { _ringState = JSON.parse(localStorage.getItem(RING_STORAGE_KEY) || '{}'); }
    catch (e) { _ringState = {}; }
    // Eski v2 anahtarı artık okunmuyor (yukarıdaki _v3 notu) — artığı temizle.
    try { localStorage.removeItem('yuki_hr_widgets_v2'); } catch (e) {}
  }
  function _saveRingState() {
    try { localStorage.setItem(RING_STORAGE_KEY, JSON.stringify(_ringState)); }
    catch (e) {}
  }

  function _focusRingWidget(widget) {
    widget.style.zIndex = ++_ringZTop;
    document.querySelectorAll('.hr-widget').forEach(w => w.classList.remove('hr-w-active'));
    widget.classList.add('hr-w-active');
  }

  /* ── DAR EKRAN (≤1100px): PANEL alt çekmece + tek widget tabakası (2026-11-13) ──────────
     Eskiden dar ekranda ray ve widget'lar `display:none` idi: telefonda HAFIZA/MODLAR/ALARM/GÖREV'e
     HİÇBİR yol yoktu (ana sekme çubuğunda yoklar). Kişisel Yuki'deki gibi ray alt çekmeceye iner,
     sağ ortadaki ▴ düğmesi açar; seçilen widget giriş çubuğunun üstünde tam genişlik tabaka olur.
     Gizleme yalnız GÖRSEL (`hr-w-mobil-gizli`): `_ringState`'e yazılmaz — telefonda bir widget açıp
     kapatmak masaüstü yerleşimini (aynı localStorage) bozmasın. */
  const _darMi = () => !!(window.matchMedia && window.matchMedia('(max-width: 1100px)').matches);
  function _mobilTekWidget(aktif) {
    if (!_darMi()) return;
    document.querySelectorAll('.hr-widget').forEach(w => {
      w.classList.toggle('hr-w-mobil-gizli', w !== aktif);
    });
  }
  /* Dar ekranda açılışta kişisel Yuki'deki gibi TEK widget görünür: kayıtlı açık olanların en üstteki
     (son açılan). Halka o zaman üst yarıya çıkar (hud-ring.css "widget açıkken halka üst yarıya"),
     tabaka giriş çubuğunun üstünde durur — alt payı _widgetAltPay ölçer. (11-14 tam hizala: eskiden
     telefonda açılışta hepsi gizliydi; halka ortada kalıyor, kişiselden ayrışıyordu.) */
  function _mobilAcilisGizle() {
    if (!_darMi()) {
      document.querySelectorAll('.hr-widget.hr-w-mobil-gizli').forEach(w => w.classList.remove('hr-w-mobil-gizli'));
      return;
    }
    const acik = [...document.querySelectorAll('.hr-widget')].filter(w => !w.classList.contains('hr-w-hidden'));
    if (!acik.length) return;
    _mobilTekWidget(acik.reduce((a, b) => ((+b.style.zIndex || 0) > (+a.style.zIndex || 0) ? b : a)));
  }
  /* Tabakanın alt payı GİRİŞ ÇUBUĞUNDAN ölçülür (sabit sayı her giriş değişikliğinde bayatlar —
     kişiselde 76px sabiti, çubuğun altına durum satırı gelince gönder düğmesini örttü). */
  let _girisGozcu = null;
  function _widgetAltPay() {
    let pay = 76;
    for (const id of ['input-area', 'gorev-serit']) {
      const el = document.getElementById(id);
      if (!el || el.hidden || el.offsetParent === null) continue;
      const r = el.getBoundingClientRect();
      if (r.height > 0 && r.top > 0 && r.top < innerHeight)
        pay = Math.max(pay, Math.ceil(innerHeight - r.top) + 8);
    }
    document.body.style.setProperty('--hr-widget-alt', pay + 'px');
  }
  function _widgetAltPayIzle(ac) {
    if (_girisGozcu) { _girisGozcu.disconnect(); _girisGozcu = null; }
    if (!ac) { document.body.style.removeProperty('--hr-widget-alt'); return; }
    _widgetAltPay();
    const ic = document.getElementById('input-area');
    if (ic && window.ResizeObserver) {
      _girisGozcu = new ResizeObserver(_widgetAltPay);
      _girisGozcu.observe(ic);
    }
  }

  // Çekmece düğmesi + perde: index.html'e değil buraya — HALKA'ya ait, HALKA ile kurulur.
  // 🔴 body'ye DEĞİL #chat-pane'e eklenir: `.kabuk` `container-type: inline-size` ile yığın bağlamı
  // açıyor; body'deki perde (z 71) kabuğun içindeki çekmecenin (z 72) ÜSTÜNDE kalıyor, çekmece
  // düğmeleri tıklanamıyordu (390'da ölçüldü: elementFromPoint = #hr-cekmece-backdrop).
  function _cekmeceAc(v) {
    document.body.classList.toggle('hr-cekmece-acik', !!v);
    const fab = document.getElementById('hr-cekmece-fab');
    if (fab) {
      fab.setAttribute('aria-expanded', v ? 'true' : 'false');
      fab.setAttribute('aria-label', _hrtY(v ? 'hudring.cekmece.kapat' : 'hudring.cekmece.ac', 'PANEL'));
    }
  }
  const _cekmeceAcikMi = () => document.body.classList.contains('hr-cekmece-acik');
  function _cekmeceKur() {
    if (document.getElementById('hr-cekmece-fab')) return;
    const fab = document.createElement('button');
    fab.type = 'button'; fab.id = 'hr-cekmece-fab';
    fab.setAttribute('aria-controls', 'hr-side');
    fab.setAttribute('aria-expanded', 'false');
    fab.setAttribute('aria-label', _hrtY('hudring.cekmece.ac', 'PANEL'));
    fab.title = _hrtY('hudring.cekmece.ac', 'PANEL');
    fab.innerHTML = '<svg viewBox="0 0 16 16" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M3.5 10l4.5-4.5 4.5 4.5"/></svg>';
    const perde = document.createElement('div');
    perde.id = 'hr-cekmece-backdrop';
    const pane = document.getElementById('chat-pane') || document.body;
    pane.appendChild(perde);
    pane.appendChild(fab);
    fab.addEventListener('click', () => _cekmeceAc(!_cekmeceAcikMi()));
    perde.addEventListener('click', () => _cekmeceAc(false));
    document.addEventListener('keydown', e => { if (e.key === 'Escape' && _cekmeceAcikMi()) _cekmeceAc(false); });
    // Widget seçilince çekmece kapansın — açılan tabaka çekmecenin altında kalırdı ("hiçbir şey olmadı").
    document.addEventListener('click', e => {
      const btn = e.target && e.target.closest && e.target.closest('#hr-side .hr-tab-btn');
      if (btn && _cekmeceAcikMi()) setTimeout(() => _cekmeceAc(false), 120);
    }, true);
  }

  function _showRingWidget(id, widget) {
    widget = widget || document.querySelector('.hr-widget[data-hr-tab="' + id + '"]');
    if (!widget) return;
    widget.classList.remove('hr-w-hidden');
    if (_ringState[id]) _ringState[id].hidden = false;
    _focusRingWidget(widget);
    _mobilTekWidget(widget);
    _saveRingState();
    _triggerRingLoad(id);
  }

  function _hideRingWidget(id, widget) {
    widget = widget || document.querySelector('.hr-widget[data-hr-tab="' + id + '"]');
    if (!widget) return;
    widget.classList.add('hr-w-hidden');
    // Dar ekranda sıra arkadakine geçmez: tabaka kapanınca halka + akış görünür kalsın.
    if (_ringState[id]) _ringState[id].hidden = true;
    _saveRingState();
  }

  const _isWidgetVisible = id => {
    const w = document.querySelector('.hr-widget[data-hr-tab="' + id + '"]');
    return w && !w.classList.contains('hr-w-hidden');
  };

  function _triggerRingLoad(id) {
    if (id === 'memory') _renderMemMap();
    if (id === 'alarms') _renderReminders();
    if (id === 'modes')  _renderModes();
    if (id === 'todos')  _renderTodos();
    if (id === 'hq')     _renderHq();
    if (id === 'gaze')   _gozKur();
    if (id === 'sites')  _sitelerCiz();
  }

  function _showSnapZones(canvas, dragWidget) {
    _hideSnapZones();
    const cr = canvas.getBoundingClientRect();
    const ww = dragWidget.offsetWidth, wh = dragWidget.offsetHeight;
    _computeSnapZones(cr.width, cr.height, ww, wh, _sagSinir(canvas)).forEach(zone => {
      const el = document.createElement('div');
      el.className = 'hr-snap-zone hr-sz-' + (zone.shape || 'rect');
      el.dataset.zoneId = zone.id;
      el.style.left   = zone.x + 'px';
      el.style.top    = zone.y + 'px';
      el.style.width  = ww + 'px';
      el.style.height = wh + 'px';
      const lbl = document.createElement('span');
      lbl.className = 'hr-sz-label';
      lbl.textContent = zone.label;
      el.appendChild(lbl);
      canvas.appendChild(el);
    });
  }

  function _hideSnapZones() {
    document.querySelectorAll('.hr-snap-zone').forEach(el => el.remove());
  }

  function _findNearestZone(canvas, wx, wy, ww, wh) {
    const cr = canvas.getBoundingClientRect();
    let best = null, bestDist = SNAP_THRESHOLD;
    _computeSnapZones(cr.width, cr.height, ww, wh, _sagSinir(canvas)).forEach(zone => {
      const dist = Math.hypot((wx + ww/2) - (zone.x + ww/2), (wy + wh/2) - (zone.y + wh/2));
      if (dist < bestDist) { best = zone; bestDist = dist; }
    });
    return best;
  }

  function _applyEdgeSnap(nx, ny, cw, ch, ww, wh) {
    let rx = nx, ry = ny;
    if (nx < EDGE_THRESHOLD)             rx = 10;
    if (nx > cw - ww - EDGE_THRESHOLD)   rx = cw - ww - 10;
    if (ny < EDGE_THRESHOLD)             ry = 10;
    if (ny > ch - wh - EDGE_THRESHOLD)   ry = ch - wh - 10;
    return { x: rx, y: ry };
  }

  function _zoneOccupiedOffset(zoneId, ww) {
    const occupants = _snapOccupancy[zoneId];
    if (!occupants || occupants.length === 0) return 0;
    return occupants.length * (ww + 10);
  }

  function _setupRingDrag(widget, handle, id) {
    let dragging = false, offX = 0, offY = 0;
    handle.addEventListener('mousedown', e => {
      if (e.button !== 0) return;
      e.preventDefault();
      _focusRingWidget(widget);
      dragging = true;
      widget.classList.add('hr-w-dragging');
      const rect = widget.getBoundingClientRect();
      offX = e.clientX - rect.left;
      offY = e.clientY - rect.top;
      // Önceki zone'dan çıkar
      Object.keys(_snapOccupancy).forEach(zid => {
        _snapOccupancy[zid] = (_snapOccupancy[zid] || []).filter(wid => wid !== id);
      });
      const canvas = document.getElementById('chat-pane');
      if (canvas) _showSnapZones(canvas, widget);
    });
    document.addEventListener('mousemove', e => {
      if (!dragging) return;
      const canvas = document.getElementById('chat-pane');
      if (!canvas) return;
      const cr = canvas.getBoundingClientRect();
      const nx = Math.max(0, Math.min(cr.width - widget.offsetWidth, e.clientX - cr.left - offX));
      const ny = Math.max(0, Math.min(cr.height - 40, e.clientY - cr.top - offY));
      widget.style.left = nx + 'px';
      widget.style.top  = ny + 'px';
      // En yakın zone'u vurgula
      const nearZone = _findNearestZone(canvas, nx, ny, widget.offsetWidth, widget.offsetHeight);
      document.querySelectorAll('.hr-snap-zone').forEach(el => {
        el.classList.toggle('hr-snap-active', !!(nearZone && el.dataset.zoneId === nearZone.id));
      });
    });
    document.addEventListener('mouseup', () => {
      if (!dragging) return;
      dragging = false;
      widget.classList.remove('hr-w-dragging');
      const canvas = document.getElementById('chat-pane');
      let fx = parseInt(widget.style.left, 10) || 0;
      let fy = parseInt(widget.style.top,  10) || 0;
      if (canvas) {
        const cr = canvas.getBoundingClientRect();
        const ww = widget.offsetWidth, wh = widget.offsetHeight;
        const nearZone = _findNearestZone(canvas, fx, fy, ww, wh);
        if (nearZone) {
          const offset = _zoneOccupiedOffset(nearZone.id, ww);
          // Konum bölgenin KENDİSİNDEN okunur — `_findNearestZone` zaten aynı
          // üreticiden geldiği için gösterilen kutu ile bırakılan yer birebir aynı.
          fx = Math.min(nearZone.x + offset, Math.max(10, cr.width - ww - 10));
          fy = nearZone.y;
          if (!_snapOccupancy[nearZone.id]) _snapOccupancy[nearZone.id] = [];
          _snapOccupancy[nearZone.id].push(id);
        } else {
          const snapped = _applyEdgeSnap(fx, fy, cr.width, cr.height, ww, wh);
          fx = snapped.x; fy = snapped.y;
        }
        widget.style.left = fx + 'px';
        widget.style.top  = fy + 'px';
        _hideSnapZones();
      }
      if (_ringState[id]) {
        _ringState[id].x = fx;
        _ringState[id].y = fy;
      }
      _saveRingState();
    });
  }

  function _setupRingResize(widget, knob, body, id) {
    let resizing = false, sx = 0, sy = 0, sw = 0, sh = 0;
    knob.addEventListener('mousedown', e => {
      e.preventDefault(); e.stopPropagation();
      resizing = true;
      sx = e.clientX; sy = e.clientY;
      sw = widget.offsetWidth;
      sh = widget.offsetHeight;
    });
    document.addEventListener('mousemove', e => {
      if (!resizing) return;
      widget.style.width  = Math.max(240, sw + (e.clientX - sx)) + 'px';
      widget.style.height = Math.max(120, sh + (e.clientY - sy)) + 'px';
    });
    document.addEventListener('mouseup', () => {
      if (!resizing) return;
      resizing = false;
      if (_ringState[id]) {
        _ringState[id].w = parseInt(widget.style.width,  10) || 300;
        _ringState[id].h = parseInt(widget.style.height, 10) || 400;
      }
      _saveRingState();
    });
  }

  // ── Floating widget'ları oluştur ──
  function _buildWidgets() {
    if (document.querySelector('.hr-widget')) return; // zaten kurulu
    _loadRingState();
    const canvas = document.getElementById('chat-pane');
    if (!canvas) return;
    // Kurulumda #chat-pane çoğu kez henüz gizli (offsetWidth 0); pane tam genişlik → innerWidth.
    const cw = canvas.offsetWidth || window.innerWidth || 1200;

    const CONTENTS = {
      memory: `<div id="hr-mem-body" class="hk"><div class="hr-pane-loading">${_hrt('genel.yukleniyor')}</div></div>`,
      alarms: `<div id="hr-alarms-body"><div class="hr-pane-loading">${_hrt('genel.yukleniyor')}</div></div>`,
      modes:  `<div id="hr-modes-body"><div class="hr-pane-loading">${_hrt('genel.yukleniyor')}</div></div>`,
      todos:  `<div id="hr-todos-body"><div class="hr-pane-loading">${_hrt('genel.yukleniyor')}</div></div>`,
      chat:   `<div class="hr-panel-head"><span data-hr-k="hudring.akis-baslik">${_hrt('hudring.akis-baslik')}</span><span class="hr-head-dot"></span></div>
               <div id="hr-flow-body"></div>`,
      hq:     `<div class="hr-panel-head"><span data-hr-k="hudring.hq-baslik">${_hrt('hudring.hq-baslik')}</span><span class="hr-head-dot"></span></div>
               <div id="hr-hq-body"><div class="hr-pane-loading">${_hrt('genel.yukleniyor')}</div></div>`,
      gaze:   `<div id="hr-goz-body"><div class="hr-pane-loading">${_hrt('genel.yukleniyor')}</div></div>`,
      sites:  `<div id="hr-sites-body"><div class="hr-pane-loading">${_hrt('genel.yukleniyor')}</div></div>`,
    };

    /* Varsayılan yer PANEL rayının SOLU (_v4, kişisel Yuki'nin düzeni). Ray kurulumda çoğu kez henüz
       görünmez (body sınıfı sonra gelir, genişlik 0) → CSS geometrisinden: right:10 + ray genişliği
       (`--nav-w`, daraltıkta hedef boyu). Ray sürüklenip sağdan alındıysa tuvalin tamamı serbest.
       Widget halkanın çekirdeğini (YUKI) örtecekse yalnız BAŞLIĞIYLA açılır; kullanıcı ▼ ile açar,
       tercih `_ringState`'te kalır. Geniş ekranda (≥ ~1500) gövdesiyle açık başlar.
       ≤1100'de ray alt çekmecedir, widget alt tabakadır — bu hesap orada kullanılmaz. */
    const dar = window.matchMedia && window.matchMedia('(max-width: 1100px)').matches;
    let sagSinir = _sagSinir(canvas);
    const side = document.getElementById('hr-side');
    if (!dar && side && !side.offsetWidth && !side.style.left) {
      const kok = getComputedStyle(document.documentElement);
      const navW = parseFloat(kok.getPropertyValue('--nav-w')) || 268;
      sagSinir = cw - 10 - (side.classList.contains('hr-collapsed') ? 60 : navW);
    }
    if (!Number.isFinite(sagSinir) || sagSinir <= 0) sagSinir = cw;
    const CEKIRDEK_PAY = 160;
    const cekirdegeBiner = w => !dar && sagSinir - w - 20 < cw / 2 + CEKIRDEK_PAY;
    RING_WIDGET_CFG.forEach((cfg, idx) => {
      if (!_ringState[cfg.id]) {
        _ringState[cfg.id] = {
          x: Math.max(10, sagSinir - cfg.w - 20),
          y: SNAP_UST + idx * 22,
          w: cfg.w, h: cfg.h,
          collapsed: cekirdegeBiner(cfg.w),
          hidden: cfg.id !== 'memory',
        };
      }
      const st = _ringState[cfg.id];

      const widget = document.createElement('div');
      widget.className = 'hr-widget'
        + (st.hidden    ? ' hr-w-hidden'    : '')
        + (st.collapsed ? ' hr-w-collapsed' : '');
      widget.dataset.hrTab = cfg.id;
      widget.style.cssText = `left:${st.x}px;top:${st.y}px;width:${st.w}px;height:${st.h || cfg.h}px;z-index:${++_ringZTop}`;

      // Header
      const header = document.createElement('div');
      header.className = 'hr-widget-header';
      const colBtn = document.createElement('button');
      colBtn.type = 'button'; colBtn.className = 'hr-widget-btn hr-wb-collapse';
      colBtn.title = _hrt('hudring.widget.kucult-buyut'); colBtn.textContent = st.collapsed ? '▲' : '▼';
      const closeBtn = document.createElement('button');
      closeBtn.type = 'button'; closeBtn.className = 'hr-widget-btn hr-wb-close';
      closeBtn.title = _hrt('hudring.widget.kapat'); closeBtn.textContent = '✕';
      const btns = document.createElement('div');
      btns.className = 'hr-widget-btns';
      btns.appendChild(colBtn); btns.appendChild(closeBtn);
      header.innerHTML = `<span class="hr-widget-dot"></span><span class="hr-widget-icon" aria-hidden="true">${RING_IKON[cfg.id] || cfg.icon}</span><span class="hr-widget-title">${cfg.label}</span>`;
      header.appendChild(btns);

      // Body
      const body = document.createElement('div');
      body.className = 'hr-widget-body';
      body.innerHTML = CONTENTS[cfg.id] || '';
      body.addEventListener('click', e => {
        const b = e.target.closest('[data-hk-git]');
        if (b) _hkEylem(b.dataset.hkGit);
      });

      // Resize knob
      const knob = document.createElement('div');
      knob.className = 'hr-widget-resize';

      widget.appendChild(header);
      widget.appendChild(body);
      widget.appendChild(knob);
      canvas.appendChild(widget);

      _setupRingDrag(widget, header, cfg.id);
      _setupRingResize(widget, knob, body, cfg.id);

      colBtn.addEventListener('click', e => {
        e.stopPropagation();
        const collapsed = widget.classList.toggle('hr-w-collapsed');
        colBtn.textContent = collapsed ? '▲' : '▼';
        if (_ringState[cfg.id]) _ringState[cfg.id].collapsed = collapsed;
        _saveRingState();
      });

      closeBtn.addEventListener('click', e => {
        e.stopPropagation();
        _hideRingWidget(cfg.id, widget);
        const btn = document.querySelector('.hr-tab-btn[data-tab="' + cfg.id + '"]');
        if (btn) btn.classList.remove('hr-w-open');
      });

      widget.addEventListener('mousedown', () => _focusRingWidget(widget));
    });

    _saveRingState();
  }

  function _togglePanel() {
    _panelCollapsed = !_panelCollapsed;
    const side = document.getElementById('hr-side');
    if (side) {
      side.classList.toggle('hr-collapsed', _panelCollapsed);
      const btn = side.querySelector('#hr-collapse-btn');
      if (btn) btn.textContent = _panelCollapsed ? '▶' : '◀';
    }
    localStorage.setItem('yuki_hr_collapsed_v1', _panelCollapsed ? '1' : '0');
    if (!_panelCollapsed) _syncMessagesPlacement();
  }

  function _initTabs() {
    const bar = document.querySelector('.hr-tabs-bar');
    if (bar) {
      bar.addEventListener('click', e => {
        const btn = e.target.closest('.hr-tab-btn');
        if (!btn) return;
        const id = btn.dataset.tab;
        // Dar ekranda kayıtlı-açık ama görsel gizli (`hr-w-mobil-gizli`) widget "kapalı" sayılır:
        // dokunuş onu GÖSTERMELİ — yoksa ilk dokunuş kayıtlı durumu kapatır, ekranda hiçbir şey olmaz.
        const wEl = document.querySelector('.hr-widget[data-hr-tab="' + id + '"]');
        const mobilGizli = _darMi() && wEl && wEl.classList.contains('hr-w-mobil-gizli');
        if (_isWidgetVisible(id) && !mobilGizli) {
          _hideRingWidget(id);
          btn.classList.remove('hr-w-open');
        } else {
          _showRingWidget(id);
          btn.classList.add('hr-w-open');
        }
      });
    }
    // Başlangıçta buton durumunu widget state'ine senkronla
    RING_WIDGET_CFG.forEach(cfg => {
      const btn = document.querySelector('.hr-tab-btn[data-tab="' + cfg.id + '"]');
      const w = document.querySelector('.hr-widget[data-hr-tab="' + cfg.id + '"]');
      const gorsel = !(w && w.classList.contains('hr-w-mobil-gizli'));   // dar ekranda açılışta hepsi gizli
      if (btn && _isWidgetVisible(cfg.id) && gorsel) btn.classList.add('hr-w-open');
    });
    const collapseBtn = document.getElementById('hr-collapse-btn');
    if (collapseBtn) collapseBtn.addEventListener('click', _togglePanel);
  }

  function _switchTab(tabId) {
    _activeTab = tabId;
    document.querySelectorAll('.hr-tab-btn').forEach(b =>
      b.classList.toggle('active', b.dataset.tab === tabId));
    document.querySelectorAll('.hr-tab-pane').forEach(p =>
      p.classList.toggle('active', p.id === 'hr-tab-' + tabId));
    if (tabId === 'chat') {
      const msgs = document.getElementById('messages');
      if (msgs) msgs.scrollTop = msgs.scrollHeight;
    }
    if (tabId === 'alarms') _renderReminders();
    if (tabId === 'modes')  _renderModes();
    if (tabId === 'todos')  _renderTodos();
    if (tabId === 'hq')     _renderHq();
  }

  // #messages → KONUŞMA AKIŞI paneline taşı / geri getir
  function _adoptMessages() {
    const msgs = document.getElementById('messages');
    const slot = document.getElementById('hr-flow-body');
    if (!msgs || !slot || msgs.parentElement === slot) return;
    if (!_msgHome) _msgHome = { parent: msgs.parentElement, next: msgs.nextElementSibling };
    slot.appendChild(msgs);
    msgs.scrollTop = msgs.scrollHeight;
  }
  function _releaseMessages() {
    const msgs = document.getElementById('messages');
    if (!msgs || !_msgHome || msgs.parentElement === _msgHome.parent) return;
    if (_msgHome.next && _msgHome.next.parentElement === _msgHome.parent) {
      _msgHome.parent.insertBefore(msgs, _msgHome.next);
    } else {
      _msgHome.parent.appendChild(msgs);
    }
  }

  // Mobil (≤1100px): sağ panel gizli → #messages'ı KONUŞMA AKIŞI'na TAŞIMA,
  // normal akışta (halkanın altında) görünür kalsın. Geniş ekranda panele taşı.
  const _isNarrow = () => window.matchMedia('(max-width: 1100px)').matches;
  function _syncMessagesPlacement() {
    if (_isNarrow()) _releaseMessages();
    else _adoptMessages();
  }
  // Döndürme / yeniden boyutlandırma breakpoint'i geçince yerleşimi düzelt
  function _onResize() {
    clearTimeout(_resizeT);
    _resizeT = setTimeout(() => {
      if (document.body.classList.contains('hud-ring-mode')) {
        _syncMessagesPlacement();
        // Breakpoint geçişi: genişe dönünce görsel gizleme kalkar; dara inince açık widget tabakası açılmaz.
        if (!_darMi()) { _mobilAcilisGizle(); _cekmeceAc(false); }
        _widgetAltPay();
      }
    }, 200);
  }

  // ── Veri yardımcıları ──
  const esc = s => String(s == null ? '' : s).replace(/</g, '&lt;');
  const _arr = (r, keys) => {
    if (Array.isArray(r)) return r;
    for (const k of keys) if (r && Array.isArray(r[k])) return r[k];
    return [];
  };

  // ── Ortak kart dili (kişisel Yuki "C · Harita" kart dilinden, 11-15 tam hizala) ──
  // Kart: durum şeridi · gövde (kayar) · alt eylem. Boş veri ile uç hatası ayrı yazılır; sahte değer yok.
  const _hkSonVeri = {};   // kart → son başarılı veri zamanı (yalnız bellekte)
  const _hkSaat = t => { const d = new Date(t), p = n => String(n).padStart(2, '0'); return p(d.getHours()) + ':' + p(d.getMinutes()); };
  const _hkTl = n => { try { return Number(n).toLocaleString(document.documentElement.lang || undefined); } catch (_) { return String(n); } };
  const _hkSerit = (sol, sag) => '<div class="hk-serit"><span class="hk-sol">' + sol + '</span>'
    + (sag ? '<span class="hk-sag">' + sag + '</span>' : '') + '</div>';
  const _hkAlt = (metin, git) => '<div class="hk-alt"><button type="button" class="hk-eylem" data-hk-git="' + git + '">' + metin + '</button></div>';
  const _hkBos = (ana, sonra) => '<div class="hk-bos"><b>' + ana + '</b>' + (sonra ? '<span>' + sonra + '</span>' : '') + '</div>';
  const _hkHata = (ana, kart) => '<div class="hk-bos hk-hata"><b>' + ana + '</b><span>'
    + esc(_hkSonVeri[kart] ? _hrt('hudring.kart.son-veri', { saat: _hkSaat(_hkSonVeri[kart]) }) : _hrt('hudring.kart.veri-gelmedi')) + '</span></div>';
  const _hkCubuk = (ad, yuzde, deger, renk) => {
    const p = Math.max(0, Math.min(100, Number(yuzde) || 0));
    return '<div class="hk-cubuk"><span>' + ad + '</span><p><i class="' + (renk || '') + '" style="width:'
      + Math.max(2, p).toFixed(1) + '%"></i></p><em>' + deger + '</em></div>';
  };
  // Gövde kayıyorsa alt kenarda solma + "▾" devamı şeridi (gövdenin hemen ardındaki kardeş).
  function _hkTasma(g) {
    let ok = g.nextElementSibling;
    if (!ok || !ok.classList.contains('hk-devam-ok')) {
      ok = document.createElement('div');
      ok.className = 'hk-devam-ok';
      ok.setAttribute('aria-hidden', 'true');
      g.after(ok);
    }
    // Ölçüm bir sonraki kareye: geri çağrı içinde sınıf değişirse "ResizeObserver loop" uyarısı basılır.
    if (!g._hkRO && window.ResizeObserver) {
      g._hkRO = new ResizeObserver(() => {
        if (g._hkKare) return;
        g._hkKare = requestAnimationFrame(() => { g._hkKare = 0; _hkTasma(g); });
      });
      g._hkRO.observe(g);
    }
    g.classList.toggle('hk-devam', g.scrollTop + g.clientHeight < g.scrollHeight - 2);
  }
  // Aynı veriyle DOM'a dokunmaz: periyodik yenileme kaydırmayı bozmasın.
  function _hkYaz(el, serit, govde, alt) {
    const html = serit + '<div class="hk-govde">' + govde + '</div>' + (alt || '');
    if (el._hkHtml === html) { const g0 = el.querySelector('.hk-govde'); if (g0) _hkTasma(g0); return; }
    const eski = el.querySelector('.hk-govde');
    const y = eski ? eski.scrollTop : 0;
    if (eski && eski._hkRO) eski._hkRO.disconnect();
    el.innerHTML = html;
    el._hkHtml = html;
    const g = el.querySelector('.hk-govde');
    g.scrollTop = y;
    g.addEventListener('scroll', () => _hkTasma(g), { passive: true });
    _hkTasma(g);
  }
  function _hkEylem(git) {
    if (typeof window.switchTab === 'function') window.switchTab(git);
  }

  // ── HAFIZA: dağılım + önemli olgu/tercihler (kişiseldeki liste kartı; eski SVG düğüm haritasının yerine) ──
  // Durumlar: uç 503 ya da `enabled:false` → "hafıza kapalı" · ağ/diğer hata → "alınamadı" · 0 anı → boş.
  // `_memSon` son veriyi tutar: dil değişince ağa gitmeden yeniden çizilir (_drawHafiza).
  let _memSon = null, _memSecili = null;
  const _memAd = k => _hrtY('hudring.hafiza.kat.' + k, k);
  const _escA = s => esc(s).replace(/"/g, '&quot;');
  function _drawHafiza() {
    const el = document.getElementById('hr-mem-body');
    if (!el || !_memSon) return;
    const v = _memSon;
    if (v.tur === 'hata') {
      _hkYaz(el, _hkSerit(esc(_hrt('hudring.kart.veri-yok'))), _hkHata(esc(_hrt('hudring.hafiza.alinamadi')), 'memory'), '');
      return;
    }
    if (v.tur === 'kapali') {
      _hkYaz(el, _hkSerit(esc(_hrt('hudring.hafiza.serit-kapali'))),
        _hkBos(esc(_hrt('hudring.hafiza.kapali')), esc(_hrt('hudring.hafiza.kapali-alt'))), '');
      return;
    }
    if (v.tur === 'bos') {
      _hkYaz(el, _hkSerit(esc(_hrt('hudring.hafiza.serit-ani', { n: 0 }))),
        _hkBos(esc(_hrt('hudring.hafiza.bos')), esc(_hrt('hudring.hafiza.bos-alt'))), '');
      return;
    }
    const dagilim = v.kume.map(([k, n]) => _hkCubuk(esc(_memAd(k)), n / v.toplam * 100, _hkTl(n),
      k === 'preference' ? 'hk-esik' : (k === 'fact' ? 'hk-acik' : ''))).join('');
    const liste = v.anilar.map(m => {
      const sel = String(_memSecili) === String(m.id);
      return '<button type="button" class="hk-ani' + (sel ? ' sel' : '') + '" data-id="' + _escA(String(m.id)) + '"><span>' + esc(m.content || '') + '</span>'
        + (sel ? '<small>' + esc(_memAd(m.category || '')) + (m.created_at ? ' · ' + esc(String(m.created_at).slice(0, 16).replace('T', ' ')) : '') + '</small>' : '')
        + '</button>';
    }).join('') || '<div class="hk-not">' + esc(_hrt(v.listeHata ? 'hudring.hafiza.liste-hata' : 'hudring.hafiza.liste-bos')) + '</div>';
    _hkYaz(el, _hkSerit(esc(_hrt('hudring.hafiza.serit-ani', { n: _hkTl(v.toplam) })), esc(_hrt('hudring.hafiza.serit-tur', { n: v.kume.length }))),
      '<div class="hk-et">' + esc(_hrt('hudring.hafiza.dagilim')) + '</div>' + dagilim
      + '<div class="hk-ara">' + esc(_hrt('hudring.hafiza.olgu-tercih')) + '</div>' + liste,
      _hkAlt(esc(_hrt('hudring.hafiza.hq-ac')), 'hq'));
    if (!el.dataset.bagli) {
      el.dataset.bagli = '1';
      el.addEventListener('click', e => {
        const b = e.target.closest('.hk-ani');
        if (!b) return;
        _memSecili = String(_memSecili) === b.dataset.id ? null : b.dataset.id;
        _drawHafiza();
      });
    }
  }
  async function _renderMemMap() {
    const el = document.getElementById('hr-mem-body');
    if (!el || !window.ModeData) return;
    let st;
    try { st = await ModeData.getJSON('/api/memory/stats'); }
    catch (e) {
      _memSon = { tur: /HTTP 503/.test(String(e && e.message)) ? 'kapali' : 'hata' };
      _drawHafiza();
      return;
    }
    _hkSonVeri.memory = Date.now();
    if (!st || st.enabled === false) { _memSon = { tur: 'kapali' }; _drawHafiza(); return; }
    const toplam = st.total || 0;
    if (!toplam) { _memSon = { tur: 'bos' }; _drawHafiza(); return; }
    // Süzgeç sayaçları `categories`'ten (api/memory.py stats yorumu); yoksa `scopes`.
    const kaynak = st.categories && Object.keys(st.categories).length ? st.categories : (st.scopes || {});
    const kume = Object.entries(kaynak).map(([k, v]) => [k, typeof v === 'number' ? v : ((v && v.count) || 0)])
      .filter(([, n]) => n > 0).sort((a, b) => b[1] - a[1]);
    const [olgu, tercih] = await Promise.allSettled([
      ModeData.getJSON('/api/memory?category=fact&limit=8'), ModeData.getJSON('/api/memory?category=preference&limit=8')]);
    const anilar = [olgu, tercih].flatMap(r => r.status === 'fulfilled' ? _arr(r.value, ['items', 'memories', 'results']) : [])
      .filter((m, i, d) => d.findIndex(x => x.id === m.id) === i)
      .sort((a, b) => (b.importance || 0) - (a.importance || 0)).slice(0, 8);
    _memSon = { tur: 'dolu', toplam, kume, anilar, listeHata: olgu.status === 'rejected' && tercih.status === 'rejected' };
    _drawHafiza();
  }

  // ── ALARM sekmesi ──
  let _remSon = null;   // son alarm cevabı — dil tazeleyici ağsız yeniden çizer
  async function _renderReminders() {
    const el = document.getElementById('hr-alarms-body');
    if (!el || !window.ModeData) return;
    try {
      const r = await ModeData.reminders();
      _remSon = { items: _arr(r, ['reminders', 'items', 'results']) };
    } catch (e) {
      _remSon = { hata: true };
    }
    _drawReminders();
  }
  function _drawReminders() {
    const el = document.getElementById('hr-alarms-body');
    if (!el || !_remSon) return;
    if (_remSon.hata) {
      el.innerHTML = '<div class="hr-pane-empty">' + esc(_hrt('hudring.alarm.alinamadi')) + '</div>'; return;
    }
    const items = _remSon.items;
    if (!items.length) {
      el.innerHTML = '<div class="hr-pane-empty">' + esc(_hrt('hudring.alarm.yok')) + '</div>'; return;
    }
    const now = Date.now();
    el.innerHTML = items.slice(0, 20).map(r => {
      const repeat = r.kind === 'repeat';
      const ts = r.next_run || r.trigger_at || r.scheduled_at || r.time || r.datetime || '';
      let timeStr = '';
      if (repeat) {
        // r.human backend'den aktif dilde gelir ("her 20 dakikada" / "every 20 minutes").
        timeStr = (r.human ? _hrt('hudring.alarm.aralik', { aralik: r.human }) : _hrt('hudring.alarm.tekrarli'));
      } else if (ts) {
        const d = new Date(ts);
        const diff = d - now;
        if (diff > 0) {
          const mins = Math.floor(diff / 60000);
          timeStr = mins < 60 ? _hrt('hudring.sure.dk', { n: mins })
            : _hrt('hudring.sure.sa-dk', { sa: Math.floor(mins / 60), dk: mins % 60 });
        } else {
          timeStr = d.toLocaleTimeString(_hrYerel(), { hour: '2-digit', minute: '2-digit' });
        }
      }
      const done = r.is_done || r.completed || r.done || false;
      const id = r.id || r.job_id || '';
      return '<div class="hr-reminder-item' + (done ? ' done' : '') + '">'
        + '<span class="hr-rem-icon">' + (done ? '✓' : (repeat ? '🔁' : '⏰')) + '</span>'
        + '<div class="hr-rem-body">'
        + '<span class="hr-rem-text">' + esc(r.text || r.message || r.title || '—') + '</span>'
        + (timeStr ? '<span class="hr-rem-time">' + esc(timeStr) + '</span>' : '')
        + '</div>'
        + (id ? '<button class="hr-rem-cancel" data-id="' + esc(id) + '" title="' + esc(_hrt('hudring.alarm.kapat')) + '" aria-label="' + esc(_hrt('hudring.alarm.kapat')) + '">✕</button>' : '')
        + '</div>';
    }).join('');

    // Tekil iptal (×) — her kartın kapat butonu
    el.querySelectorAll('.hr-rem-cancel').forEach(btn => {
      btn.addEventListener('click', async (e) => {
        e.stopPropagation();
        const id = btn.getAttribute('data-id');
        if (!id) return;
        btn.disabled = true;
        try {
          await ModeData.cancelReminder(id);
          btn.closest('.hr-reminder-item')?.remove();
          if (_remSon && _remSon.items) _remSon.items = _remSon.items.filter(x => String(x.id || x.job_id || '') !== String(id));
          if (!el.querySelector('.hr-reminder-item')) {
            el.innerHTML = '<div class="hr-pane-empty">' + esc(_hrt('hudring.alarm.yok')) + '</div>';
          }
        } catch (err) {
          btn.disabled = false;
        }
      });
    });
  }

  // ── MODLAR sekmesi ──
  let _modSon = null;
  async function _renderModes() {
    const el = document.getElementById('hr-modes-body');
    if (!el || !window.ModeData) return;
    try {
      const r = await ModeData.getJSON('/api/modes/list');
      _modSon = { items: _arr(r, ['modes', 'items', 'results']) };
    } catch (e) {
      _modSon = { hata: true };
    }
    _drawModes();
  }
  function _drawModes() {
    const el = document.getElementById('hr-modes-body');
    if (!el || !_modSon) return;
    if (_modSon.hata) {
      el.innerHTML = '<div class="hr-pane-empty">' + esc(_hrt('hudring.mod.alinamadi')) + '</div>'; return;
    }
    const items = _modSon.items;
    if (!items.length) {
      el.innerHTML = '<div class="hr-pane-empty">' + esc(_hrt('hudring.mod.yok')) + '</div>'; return;
    }
    el.innerHTML = '<div class="hr-modes-grid">'
      + items.slice(0, 18).map(m => {
        const name = esc(m.name || m.id || '?');
        const ws = esc(m.workspace || m.alan || '');
        return '<div class="hr-mode-badge" title="' + name + (ws ? ' → ' + ws : '') + '">'
          + '<span class="hr-mode-name">' + name + '</span>'
          + (ws ? '<span class="hr-mode-ws">' + ws + '</span>' : '')
          + '</div>';
      }).join('') + '</div>';
  }

  // ── GÖREV sekmesi ──
  let _todoSon = null;
  async function _renderTodos() {
    const el = document.getElementById('hr-todos-body');
    if (!el || !window.ModeData) return;
    let lists;
    try {
      const r = await ModeData.todoLists();
      lists = _arr(r, ['lists', 'items', 'results']);
    } catch (e) {
      _todoSon = { hata: true }; _drawTodos(); return;
    }
    if (!lists.length) {
      _todoSon = { chunks: null }; _drawTodos(); return;
    }
    const chunks = await Promise.all(
      lists.slice(0, 3).map(async l => {
        try {
          const r2 = await ModeData.todoTasks(l.id || l.list_id);
          const tasks = _arr(r2, ['tasks', 'items', 'results']);
          return { list: l, tasks: tasks.filter(t => !t.completed && !t.done).slice(0, 5) };
        } catch { return { list: l, tasks: [] }; }
      })
    );
    _todoSon = { chunks };
    _drawTodos();
  }
  function _drawTodos() {
    const el = document.getElementById('hr-todos-body');
    if (!el || !_todoSon) return;
    if (_todoSon.hata) {
      el.innerHTML = '<div class="hr-pane-empty">' + esc(_hrt('hudring.gorev.alinamadi')) + '</div>'; return;
    }
    if (!_todoSon.chunks) {
      el.innerHTML = '<div class="hr-pane-empty">' + esc(_hrt('hudring.gorev.yok')) + '</div>'; return;
    }
    const html = _todoSon.chunks.map(({ list, tasks }) => {
      if (!tasks.length) return '';
      return '<div class="hr-todo-list">'
        + '<div class="hr-todo-list-name">' + esc(list.name || list.title || '—') + '</div>'
        + tasks.map(t =>
          '<div class="hr-todo-item">'
          + '<span class="hr-todo-dot"></span>'
          + '<span class="hr-todo-text">' + esc(t.title || t.text || t.name || '—') + '</span>'
          + '</div>'
        ).join('') + '</div>';
    }).join('');
    el.innerHTML = html || '<div class="hr-pane-empty">' + esc(_hrt('hudring.gorev.hepsi-tamam')) + '</div>';
  }

  let _hqSon = null;
  async function _renderHq() {
    const el = document.getElementById('hr-hq-body');
    if (!el) return;
    let health = {}, sys = {};
    try { health = await ModeData.getJSON('/health'); } catch (e) {}
    try { sys = await ModeData.system(); } catch (e) {}
    _hqSon = { health, sys };
    _drawHq();
  }
  function _drawHq() {
    const el = document.getElementById('hr-hq-body');
    if (!el || !_hqSon) return;
    const { health, sys } = _hqSon;
    const cpu = (sys.cpu || 0).toFixed(0);
    const ram = (sys.ram && sys.ram.percent != null ? sys.ram.percent : 0).toFixed(0);
    const ver  = health.version || health.app_version || '—';
    const uptime = health.uptime_seconds != null
      ? (health.uptime_seconds < 3600
          ? _hrt('hudring.sure.dk', { n: Math.round(health.uptime_seconds / 60) })
          : _hrt('hudring.sure.sa', { n: (health.uptime_seconds / 3600).toFixed(1) }))
      : '—';
    const tools = health.tools || health.tool_count || '—';
    const char  = health.character || health.active_character || (typeof getCharacter === 'function' ? getCharacter() : '—');
    el.innerHTML = `
      <div class="hr-hq-grid">
        <div class="hr-hq-card">
          <span class="hr-hq-lbl">${_hrt('hudring.hq.surum')}</span>
          <span class="hr-hq-val">${esc(String(ver))}</span>
        </div>
        <div class="hr-hq-card">
          <span class="hr-hq-lbl">${_hrt('hudring.hq.calisma')}</span>
          <span class="hr-hq-val">${esc(String(uptime))}</span>
        </div>
        <div class="hr-hq-card">
          <span class="hr-hq-lbl">CPU</span>
          <span class="hr-hq-val">${cpu}%</span>
        </div>
        <div class="hr-hq-card">
          <span class="hr-hq-lbl">RAM</span>
          <span class="hr-hq-val">${ram}%</span>
        </div>
        <div class="hr-hq-card">
          <span class="hr-hq-lbl">${_hrt('hudring.hq.arac')}</span>
          <span class="hr-hq-val">${esc(String(tools))}</span>
        </div>
        <div class="hr-hq-card">
          <span class="hr-hq-lbl">${_hrt('hudring.hq.karakter')}</span>
          <span class="hr-hq-val">${esc(String(char)).toUpperCase()}</span>
        </div>
      </div>
      <div class="hr-hq-status">
        <span class="hr-hq-dot"></span>
        <span>${health.status === 'ok' || health.status === 'healthy' ? _hrt('hudring.hq.sistem-hazir') : _hrt('hudring.hq.baglanti-yok')}</span>
      </div>`;
  }
  // ── GÖZ widget'ı — açık kaynağın kendi kamera görüşü paneli (2026-11-14) ──
  /* Kişiselin GÖZ'ü kendi kamerasını açıp kareyi işliyor; o kod TAŞINMADI. Burada gövde
     `YukiGorusPanel.kur()` (js/gorus-panel.js): rıza ekranı, başlat/durdur, "Yuki bak" orada.
     🔴 Önce bayrak yoklanır (`/api/gorus/durum`): 404/hata = kurulum bayrağı GORUS kapalı →
     yalnız dürüst bir satır; kamera düğmesi, rıza ekranı ya da "yakında" vaadi YOK.
     `kur()` ses kimliği kartını da ekler — GÖZ yalnız kamera kartını tutar (ilk kart; ses
     kimliği HQ › Sistem'de yaşar). Bir kez kurulur; widget kapanıp açılınca yeniden istek atmaz. */
  let _gozDurum = null;   // null · 'bekliyor' · 'acik' · 'kapali'
  function _gozKapaliCiz(el) {
    el.innerHTML = `<div class="hr-goz-kapali" data-goz="kapali" role="status">` +
      `<span class="hr-goz-ikon" aria-hidden="true">${RING_IKON.gaze}</span>` +
      `<b data-hr-k="hudring.goz.kapali">${esc(_hrt('hudring.goz.kapali'))}</b>` +
      `<small data-hr-k="hudring.goz.kapali-ipucu">${esc(_hrt('hudring.goz.kapali-ipucu'))}</small></div>`;
  }
  async function _gozKur() {
    const el = document.getElementById('hr-goz-body');
    if (!el || _gozDurum === 'bekliyor' || _gozDurum === 'acik') return;
    if (_gozDurum === 'kapali') { _gozKapaliCiz(el); return; }
    _gozDurum = 'bekliyor';
    const panel = window.YukiGorusPanel;
    let bayrak = false;
    if (panel && typeof panel.kur === 'function' && window.ModeData) {
      try { await ModeData.getJSON('/api/gorus/durum'); bayrak = true; } catch (e) { bayrak = false; }
    }
    if (!bayrak) { _gozDurum = 'kapali'; _gozKapaliCiz(el); return; }
    const kap = document.createElement('div');
    kap.className = 'hr-goz-panel';
    el.textContent = '';
    el.appendChild(kap);
    try {
      const ok = await panel.kur(kap);
      const kartlar = kap.querySelectorAll('.gp-kart');
      kartlar.forEach((k, i) => { if (i > 0) k.remove(); });   // ses kimliği kartı GÖZ'e ait değil
      if (!ok || !kartlar.length) { _gozDurum = 'kapali'; _gozKapaliCiz(el); return; }
      kap.hidden = false;
      _gozDurum = 'acik';
    } catch (e) {
      _gozDurum = 'kapali'; _gozKapaliCiz(el);
    }
  }

  // ── SİTELER widget'ı — Odaklı Halka'nın site listesi (2026-11-14) ──
  /* Kaynak `window.HalkaSiteler` (localStorage, sunucuya hiçbir şey gitmez); görünüm kişiselin
     SİTELER listesini örnek alır: yuvarlak harf · ad + adres · ✕. Açılış SİSTEM TARAYICISINDA
     (`HalkaSiteler.ac` adresi açmadan önce yeniden doğrular). Ekleme ayrı bir form değil:
     halkanın kendi site paneli açılır (tek ekleme yolu, tek doğrulama). */
  function _sitelerCiz() {
    const el = document.getElementById('hr-sites-body');
    if (!el) return;
    const hs = _HS();
    const l = hs ? hs.liste() : [];
    const maks = hs ? hs.MAKS : 0;
    const satir = l.map(st =>
      `<li class="hr-site-item" data-id="${_odEsc(st.id)}">` +
      `<span class="hr-si-glyph" aria-hidden="true">${_odEsc((Array.from(st.ad)[0] || '?').toUpperCase())}</span>` +
      `<button type="button" class="hr-si-txt" data-site="ac" data-id="${_odEsc(st.id)}" title="${_odEsc(_hrt('hudring.od.ipucu.site'))}">` +
      `<b>${_odEsc(st.ad)}</b><small>${_odEsc(st.host)}</small></button>` +
      `<button type="button" class="hr-si-btn hr-si-del" data-site="sil" data-id="${_odEsc(st.id)}" aria-label="${_odEsc(_hrt('hudring.od.site.sil', { ad: st.ad }))}">✕</button></li>`
    ).join('');
    const govde = l.length
      ? `<ul class="hr-site-list" id="hr-site-list">${satir}</ul>`
      : `<div class="hr-pane-empty hr-site-bos">${_odEsc(_hrt('hudring.od.site.bos'))}</div>`;
    const alt = !hs ? ''
      : l.length < maks
        ? `<button type="button" class="hr-site-ekle" data-site="ekle">+ ${_odEsc(_hrt('hudring.od.site.ekle'))}</button>`
        : `<span class="hr-site-not">${_odEsc(_hrt('hudring.od.site.dolu', { m: maks }))}</span>`;
    el.innerHTML = `<div class="hr-site-serit"><span>${_odEsc(_hrt('hudring.od.site.tum'))}</span><span>${l.length}/${maks}</span></div>` +
      govde + `<div class="hr-site-alt">${alt}</div>`;
    if (!el.dataset.bagli) {
      el.dataset.bagli = '1';
      el.addEventListener('click', e => {
        const b = e.target.closest('[data-site]');
        if (!b || !el.contains(b)) return;
        const h = _HS();
        if (!h) return;
        const ne = b.dataset.site;
        if (ne === 'ac') {
          const st = h.liste().find(x => x.id === b.dataset.id);
          if (st) _odSiteAc(st.url);
        } else if (ne === 'sil') {
          h.sil(b.dataset.id);   // 'halka:siteler-degisti' → yeniden çizim
        } else if (ne === 'ekle') {
          const wrap = document.getElementById('hr-ring-wrap');
          if (!wrap) return;
          _odGrup = 'site'; _odSec = null;
          try { localStorage.setItem('halka_menu_grup_v1', 'site'); } catch (_) {}
          wrap.classList.add('hr-wheel-open');
          _odPanelAc('ekle');
        }
      });
    }
  }
  document.addEventListener('halka:siteler-degisti', () => { if (document.getElementById('hr-sites-body')) _sitelerCiz(); });


  // ── Sol alt: mini olay ticker (ring buffer + rotasyon) ──
  function _pushEvent(k) {
    const p = n => String(n).padStart(2, '0');
    const d = new Date();
    _events.unshift({ t: p(d.getHours()) + ':' + p(d.getMinutes()), k });
    _events = _events.slice(0, 8);
    _tickerIdx = 0;
    _rotateTicker();
  }
  function _rotateTicker() {
    const el = document.getElementById('hr-ticker-txt');
    if (!el || !_events.length) return;
    const e = _events[_tickerIdx % _events.length];
    el.textContent = '◈ ' + _hrt(e.k) + ' · ' + e.t;
    el.style.animation = 'none'; void el.offsetWidth; el.style.animation = '';
    _tickerIdx++;
  }

  // ── Saat ──
  function _tickClock() {
    if (!_stage) return;
    const el = _stage.querySelector('#hr-clock');
    if (!el) return;
    const now = new Date();
    const p = n => String(n).padStart(2, '0');
    el.querySelector('b').textContent = `${p(now.getHours())}:${p(now.getMinutes())}:${p(now.getSeconds())}`;
    el.querySelector('small').textContent = now.toLocaleDateString(_hrYerel(),
      { day: '2-digit', month: 'long', weekday: 'long' });
    // Zaman çemberi: saniye göstergesi (atlamalı) + dakika ilerleme yayı (canlı)
    const sec = now.getSeconds(), min = now.getMinutes();
    const hand = _stage.querySelector('#hr-sec-hand');
    if (hand) hand.setAttribute('transform', `rotate(${sec * 6} 300 300)`);
    const arc = _stage.querySelector('#hr-min-arc');
    if (arc) arc.setAttribute('stroke-dasharray', `${((min + sec / 60) / 60 * 360).toFixed(1)} 360`);
  }

  /* B2 (11-14, temiz kurulum denetimi): HALKA'da cevap sahnede hiç görünmüyordu — #messages
     telefonda gizli, masaüstünde yalnız AKIŞ penceresi açıksa görünür. Yeni kullanıcı "yazdım,
     cevap yok" diyordu. Son cevap "X'e bir şey sor…" satırının yerine yazılır (en çok 3 satır,
     tıklanınca AKIŞ açılır); kullanıcı yeni mesaj gönderince satır yeniden soruya döner.
     Geçmişten yüklenen satırlar (data-gecmis) sayılmaz. Kişisel Yuki'de yok — bilinçli ek. */
  let _sonCevap = '';
  function _sonCevapBul() {
    const kap = document.getElementById('messages');
    if (!kap) return '';
    const satirlar = [...kap.querySelectorAll('.msg-row')].filter(r => r.id !== 'thinking-row');
    const son = satirlar[satirlar.length - 1];
    if (!son || !son.classList.contains('yuki') || son.dataset.gecmis) return '';
    const b = son.querySelector('.msg-bubble');
    return b ? b.textContent.replace(/\s+/g, ' ').trim() : '';
  }
  function _promptYaz() {
    const t = _stage && _stage.querySelector('#hr-prompt-text');
    if (!t) return;
    t.classList.toggle('hr-son-cevap', !!_sonCevap);
    t.textContent = _sonCevap || _askMetni(_char());
    t.title = _sonCevap ? _hrt('hudring.son-cevap-ipucu') : '';
  }
  (function _sonCevapIzle() {
    let bekliyor = false;
    const izle = () => {
      const kap = document.getElementById('messages');
      if (!kap) { setTimeout(izle, 500); return; }
      new MutationObserver(() => {
        if (bekliyor) return;
        bekliyor = true;
        requestAnimationFrame(() => {
          bekliyor = false;
          const m = _sonCevapBul();
          if (m !== _sonCevap) { _sonCevap = m; _promptYaz(); }
        });
      }).observe(kap, { childList: true, subtree: true, characterData: true });
    };
    izle();
    document.addEventListener('click', (e) => {
      if (!e.target.closest('#hr-prompt-text.hr-son-cevap')) return;
      if (typeof _showRingWidget === 'function') _showRingWidget('chat');
    });
  })();

  function _updatePrompt() {
    if (!_stage) return;
    _promptYaz();
    const n = _stage.querySelector('#hr-core-name');
    if (n) n.textContent = _char().toUpperCase();
  }


  // ── ② Çark eylemleri: karakter döngüsü + input odak ──
  window.__hrCycle = function () {
    const keys = (window.MODE_CHARACTERS || []).map(c => c.key);
    if (!keys.length || !window.getCharacter || !window.setCharacter) return;
    const i = keys.indexOf(window.getCharacter());
    window.setCharacter(keys[(i + 1) % keys.length]);
  };
  window.__hrFocus = function () {
    const inp = document.getElementById('msg-input');
    if (inp) inp.focus();
  };

  // ── updateState kancası ──
  function _hookState() {
    if (_wrapped || typeof window.updateState !== 'function') return;
    const orig = window.updateState;
    window.updateState = function (s) {
      try { orig(s); } catch (e) { /* orijinal akış bozulmasın */ }
      window.HudRing.onState(s);
    };
    _wrapped = true;
  }

  // Durumu fiilen halkaya uygula (renk/animasyon + status + persona + ticker)
  function _applyState(s) {
    if (!_stage) return;
    const st = STATE[s] || STATE.idle;
    _curState = STATE[s] ? s : 'idle';
    _stage.className = st.cls + (_anahtarYok() ? ' hr-anahtar-yok' : '');
    const el = _stage.querySelector('#hr-status');
    if (el) el.textContent = st.status;
    // Halkanın merkezi (geliştirici, 2026-08-30: "halka içini düzenlemedik").
    // Durum bugüne kadar YALNIZ renkle anlatılıyordu (--hr-accent duruma göre
    // değişir); STATE_LBL zaten vardı ama hiçbir yerde merkeze bağlanmamıştı.
    // Yeni etiket icat edilmedi, var olan tablo görünür kılındı.
    const cs = _stage.querySelector('#hr-core-status');
    if (cs) cs.textContent = _stateLbl(s);
    if (s && s !== 'idle' && STATE_LBL[s]) _pushEvent(STATE_LBL[s]);
  }

  // Core'dan 'yuki:speaking' olayı: TTS sesi gerçekten çalıyor mu?
  // Ses başlayınca halka 'talking'; bitince beklemedeki backend durumunu uygula.
  // Chunk araları (kısa sessizlikler) halkayı düşürmesin diye kapanış debounce'lu.
  function _onSpeaking(e) {
    const on = !!(e && e.detail && e.detail.on);
    if (on) {
      clearTimeout(_speakOffT);
      _speaking = true;
      _pendingState = null;
      _applyState('talking');
    } else {
      clearTimeout(_speakOffT);
      _speakOffT = setTimeout(() => {
        _speaking = false;
        const s = _pendingState || 'idle';
        _pendingState = null;
        _applyState(s);
      }, 320);
    }
  }

  window.HudRing = {
    init() {
      if (!_stage) _stage = _buildStage();
      if (!_side) _side = _buildSide();
      _hookState();
      _updatePrompt();
    },
    activate() {
      this.init();
      _buildWidgets();
      _mobilAcilisGizle();
      _initTabs();
      _syncMessagesPlacement();
      _widgetAltPayIzle(true);
      window.addEventListener('resize', _onResize);
      window.addEventListener('yuki:speaking', _onSpeaking);
      _updatePrompt();
      _renderMemMap();
      _polyStart();
      _temaSenkron();
      _pushEvent('hudring.ticker.halka-aktif');
      if (_tickerTimer) clearInterval(_tickerTimer);
      _tickerTimer = setInterval(() => {
        // Diğer timer'lar gibi guard: mod kapalıysa veya pencere arka plandaysa boşuna repaint yapma
        if (document.body.classList.contains('hud-ring-mode') && !document.hidden) _rotateTicker();
      }, 3800);
      if (_timer) clearInterval(_timer);
      _timer = setInterval(() => {
        if (document.body.classList.contains('hud-ring-mode')) {
          _renderMemMap();
        }
      }, 60000);
      // Widget görünürlüğüne göre periyodik yenile
      if (_reminderTimer) clearInterval(_reminderTimer);
      _reminderTimer = setInterval(() => {
        if (document.body.classList.contains('hud-ring-mode') && _isWidgetVisible('alarms')) _renderReminders();
      }, 10000);
      if (_modesTimer) clearInterval(_modesTimer);
      _modesTimer = setInterval(() => {
        if (document.body.classList.contains('hud-ring-mode') && _isWidgetVisible('modes')) _renderModes();
      }, 30000);
      if (_todoTimer) clearInterval(_todoTimer);
      _todoTimer = setInterval(() => {
        if (document.body.classList.contains('hud-ring-mode') && _isWidgetVisible('todos')) _renderTodos();
      }, 8000);
    },
    deactivate() {
      window.removeEventListener('resize', _onResize);
      window.removeEventListener('yuki:speaking', _onSpeaking);
      clearTimeout(_speakOffT);
      _speaking = false; _pendingState = null;
      _releaseMessages();
      _cekmeceAc(false);          // HALKA dışında açık kalırsa geri dönüşte kendiliğinden açılırdı
      _widgetAltPayIzle(false);
      // Floating widget'ları temizle (mod değişince yeniden oluşturulur)
      document.querySelectorAll('.hr-widget').forEach(w => w.remove());
      _ringLoaded = {};
      _polyStop();
      _temaKaldirHepsi();   // süs katmanı (canvas rAF + gözcü) HALKA dışında yaşamasın
      if (_timer)         { clearInterval(_timer);         _timer = null; }
      if (_clockTimer)    { clearInterval(_clockTimer);    _clockTimer = null; }
      if (_tickerTimer)   { clearInterval(_tickerTimer);   _tickerTimer = null; }
      if (_reminderTimer)  { clearInterval(_reminderTimer);  _reminderTimer = null; }
      if (_modesTimer)     { clearInterval(_modesTimer);     _modesTimer = null; }
      if (_todoTimer)      { clearInterval(_todoTimer);      _todoTimer = null; }
    },
    onState(s) {
      if (!_stage) return;
      // Ses çalarken backend 'talking' dışı (idle/listening) yollasa bile halkayı
      // talking'de tut; gelen durumu beklet, ses bitince _onSpeaking uygular.
      if (_speaking && s !== 'talking') { _pendingState = s; return; }
      _applyState(s);
    },
    onCharacter() {
      _updatePrompt();
      // Tema canvas'ı karakter rengini (--gm-accent) piksel olarak önbellekler.
      const tm = (window.HalkaTemalar || {})[_halkaTema];
      if (tm && tm.renkTazele) tm.renkTazele();
      // Ring SVG yeniden oluştur
      const oldRing = document.getElementById('hr-ring');
      if (oldRing) {
        const wrap = oldRing.parentElement;
        const tmp = document.createElement('div');
        tmp.innerHTML = _ringSvg(_char());
        const newRing = tmp.firstElementChild;
        wrap.replaceChild(newRing, oldRing);
        _polys = null;
        _polyStop();
        _polyStart();
      }
      // Karakter seçici aktif durumu güncelle
      const cur = _char();
      document.querySelectorAll('.hr-cs-btn').forEach(b => {
        b.classList.toggle('hr-cs-active', b.dataset.char === cur);
      });
      if (_odGrup === 'kar') _odCiz();   // Odaklı Halka: aktif karakter + seviye
    },
  };

  // ── Anahtar hâli değişince (ilk yoklama, kayıt, silme) boştaki metinler yeniden yazılır ──
  window.addEventListener('yuki-anahtar-durum', () => {
    if (!_stage) return;
    _stage.classList.toggle('hr-anahtar-yok', _anahtarYok());
    const hs = _stage.querySelector('#hr-status');
    if (hs) hs.textContent = (STATE[_curState] || STATE.idle).status;
    const cs = _stage.querySelector('#hr-core-status');
    if (cs) cs.textContent = _stateLbl(_curState);
    const tk = document.getElementById('hr-ticker-txt');
    if (tk && !_events.length) tk.textContent = _tickerVarsayilan();
  });

  // ── Dil değişim dinleyicisi ──
  // Yalnız ŞU AN çizili metni yeniden yazar: ağ isteği yok (paneller son cevabı
  // saklıyor), widget konumu/açık-kapalı durumu ve kullanıcı girdisi korunur.
  window.addEventListener('yuki-dil-degisti', () => {
    _updatePrompt();
    const hs = _stage && _stage.querySelector('#hr-status');
    if (hs) hs.textContent = (STATE[_curState] || STATE.idle).status;
    const cs = _stage && _stage.querySelector('#hr-core-status');
    if (cs) cs.textContent = _stateLbl(_curState);
    const tk = document.getElementById('hr-ticker-txt');
    if (tk) {
      if (_events.length) { _tickerIdx = 0; _rotateTicker(); }
      else tk.textContent = _tickerVarsayilan();
    }
    // Odaklı Halka: grup adları, açıklamalar, merkez metni (sekme adları nav'dan — dil.js çevirmiş olur)
    _odCiz();
    // Sağ panel: daralt düğmesi + grup adları + sekme etiketleri
    const cb = document.getElementById('hr-collapse-btn');
    if (cb) { cb.title = _hrt('hudring.panel.daralt-genislet'); cb.setAttribute('aria-label', cb.title); }
    RING_GRUPLAR.forEach(g => {
      const el = document.querySelector('.hr-grup-ad[data-hr-grup="' + g.ad + '"]');
      if (el) el.textContent = _hrt(g.lk);
    });
    RING_WIDGET_CFG.forEach(cfg => {
      const tb = document.querySelector('.hr-tab-btn[data-tab="' + cfg.id + '"]');
      if (tb) tb.title = cfg.label;
      const tl = document.querySelector('.hr-tab-btn[data-tab="' + cfg.id + '"] .hr-tb-label');
      if (tl) tl.textContent = cfg.label;
      const w = document.querySelector('.hr-widget[data-hr-tab="' + cfg.id + '"]');
      if (!w) return;
      const tt = w.querySelector('.hr-widget-title');
      if (tt) tt.textContent = cfg.label;
      const cbtn = w.querySelector('.hr-wb-collapse');
      if (cbtn) cbtn.title = _hrt('hudring.widget.kucult-buyut');
      const xbtn = w.querySelector('.hr-wb-close');
      if (xbtn) xbtn.title = _hrt('hudring.widget.kapat');
      const yk = w.querySelector('.hr-pane-loading');
      if (yk) yk.textContent = _hrt('genel.yukleniyor');
    });
    document.querySelectorAll('.hr-panel-head [data-hr-k]').forEach(el => {
      el.textContent = _hrt(el.dataset.hrK);
    });
    // Widget gövdeleri — son veriyle, ağsız
    _drawHafiza();
    _drawReminders();
    _drawModes();
    _drawTodos();
    _drawHq();
    if (_gozDurum === 'kapali') { const g = document.getElementById('hr-goz-body'); if (g) _gozKapaliCiz(g); }
    if (document.querySelector('#hr-sites-body .hr-site-serit')) _sitelerCiz();
    // Snap bölgeleri yalnız sürükleme sırasında var; etiketleri her sürüklemede
    // `_computeSnapZones` içinde o anki dille yeniden üretilir.
  });

  window.HudRing.init();
})();
