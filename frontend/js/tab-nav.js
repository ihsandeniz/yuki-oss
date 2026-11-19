/* ── Sade Sekme Yöneticisi — Alice ürün sürümü ──────────────────────────────
 * Kaynak: map-engine.js'in switchTab'ından ayıklandı (ADIM 3 frontend derin temizlik).
 * Sekmeler: chat · planner · hq(ayarlar) · map · ajan · yedek · galeri · dosya — kademe kilidi yok
 * (açık kaynak sürüm). PANEL (Komuta kanvası) 11-13'te kaldırıldı ; YEDEK HQ'dan sekmeye çıktı.
 * ⚠️ Bu satır 2026-09-18'e kadar *"yalnız 3 sekme var; map/drive/finance
 * kaldırıldı, map-engine/map-hud SİLİNDİ"* diyordu. **map GERİ GELDİ** (Dalga 3
 * kalanı): `map-engine.js` + `map-hud.js` ürüne çevrilerek taşındı.
 * drive/finance hâlâ yok. HUD/duygu çekirdeği map-init.js'te KORUNDU
 * (o dosya adına rağmen harita DEĞİL — ses dalga formu çizer).
 * intro-sequences.js bu window.switchTab'ı sararak sekme açılış overlay'i ekler. */
(function () {
  'use strict';

  function _tnt(anahtar, degerler) {
    return (window.YukiDil && window.YukiDil.t) ? window.YukiDil.t(anahtar, degerler) : String(anahtar);
  }

  function sekmeAdi(hedef) {
    if (hedef === 'hq' || hedef === 'control' || hedef === 'ayarlar') return 'hq';
    if (hedef === 'planner') return 'planner';
    /* PANEL (Komuta kanvası) 11-13'te kaldırıldı : eski kısayol, widget `#wtab=panel`
       ve `switchTab('panel')` sohbete düşer (aşağıdaki son satır). */
    if (hedef === 'yedek' || hedef === 'yedekleme' || hedef === 'drive' || hedef === 'backup') return 'yedek';
    if (hedef === 'ajan' || hedef === 'agents') return 'ajan';
    if (hedef === 'map' || hedef === 'harita') return 'map';
    if (hedef === 'galeri' || hedef === 'gallery') return 'galeri';
    if (hedef === 'dosya' || hedef === 'files') return 'dosya';
    /* YÜZ sekmesi kaldırıldı (2026-09-06) → Ayarlar → Güvenlik odası.
       Ad yine de TANINIYOR: eski klavye kısayolu, kayıtlı bağlantı ya da
       `switchTab('faces')` çağıran eski bir delta katmanı kullanıcıyı sohbete
       atmasın, gideceği yere götürsün. */
    if (hedef === 'faces' || hedef === 'yuz') return 'guvenlik';
    return 'chat';
  }

  function sekmeGecHam(hedef) {
    var tab = sekmeAdi(hedef);
    var appEl = document.getElementById('app');
    var hqEl = document.getElementById('tab-hq');
    var plannerEl = document.getElementById('tab-planner');
    var yedekEl = document.getElementById('tab-yedek');
    var ajanEl = document.getElementById('tab-ajan');
    var mapEl = document.getElementById('tab-map');
    var galeriEl = document.getElementById('tab-galeri');
    var dosyaEl = document.getElementById('tab-dosya');
    var btnChat = document.getElementById('tab-btn-chat');
    var btnPlanner = document.getElementById('tab-btn-planner');
    var btnHq = document.getElementById('tab-btn-hq');
    var btnYedek = document.getElementById('tab-btn-yedek');
    var btnAjan = document.getElementById('tab-btn-ajan');
    var btnMap = document.getElementById('tab-btn-map');
    var btnGaleri = document.getElementById('tab-btn-galeri');
    var btnDosya = document.getElementById('tab-btn-dosya');

    /* 'guvenlik' bir sekme değil, AYARLAR içindeki bir oda. HQ'ya geç ve odayı
       seç — iki adımı kullanıcıya yaptırmayalım. `hqSelectCat` HQ paneli
       görünür olmadan çağrılırsa çizdiği gövde gizli kalır, o yüzden sekme
       geçişinden SONRA (bu turun sonunda) çağrılıyor. */
    var _guvenligeGit = (tab === 'guvenlik');
    if (_guvenligeGit) tab = 'hq';

    [
      { ad: 'chat', panel: appEl, dugme: btnChat },
      { ad: 'planner', panel: plannerEl, dugme: btnPlanner },
      { ad: 'hq', panel: hqEl, dugme: btnHq },
      { ad: 'map', panel: mapEl, dugme: btnMap },
      { ad: 'ajan', panel: ajanEl, dugme: btnAjan },
      { ad: 'yedek', panel: yedekEl, dugme: btnYedek },
      { ad: 'galeri', panel: galeriEl, dugme: btnGaleri },
      { ad: 'dosya', panel: dosyaEl, dugme: btnDosya }
    ].forEach(function (sekme) {
      var aktif = sekme.ad === tab;
      if (sekme.panel) {
        sekme.panel.hidden = !aktif;
        sekme.panel.toggleAttribute('data-aktif', aktif);
        sekme.panel.classList.toggle('active', aktif);
      }
      if (sekme.dugme) {
        sekme.dugme.classList.toggle('active', aktif);
        sekme.dugme.toggleAttribute('data-aktif', aktif);
        sekme.dugme.setAttribute('aria-selected', aktif ? 'true' : 'false');
        sekme.dugme.setAttribute('tabindex', aktif ? '0' : '-1');
      }
    });

    document.documentElement.setAttribute('data-tab', tab);

    /* Sekme değişimini duyur.
     * Gizli sekmenin konteyneri 0×0'dır: PANEL'in kanvası çizgilerini yanlış
     * hesaplar; bu olayı dinleyip yalnız görünür olduklarında iş yapar. `data-tab` özniteliğini
     * MutationObserver ile izlemek de mümkündü ama olay hem ucuz hem açık. */
    try { document.dispatchEvent(new CustomEvent('tabchange', { detail: { tab: tab } })); } catch (e) {}

    if (tab === 'hq') {
      /* 🔴 HEDEF PANEL PARAMETRELİ (FAZ 4, canlı ölçüldü 2026-08-23).
         Eskiden koşulsuz 'key' yazılıyordu. Bu fonksiyon View Transition'ın
         callback'i içinde, yani BİR SONRAKİ FRAME'de koşuyor — dışarıdan
         "HQ'yu aç ve şu paneli göster" demenin yolu yoktu: çağıran taraf
         switchHqTab('memmgr') dese bile bu satır gecikmeli çalışıp üstüne
         'key' yazıyordu (Alt+H bu yüzden Anahtar panelini açıyordu).
         Çağıran, geçişten ÖNCE window._hqHedefPanel'i set eder. */
      var hedefPanel = _guvenligeGit ? 'ayarlar' : (window._hqHedefPanel || 'key');
      window._hqHedefPanel = null;
      if (typeof window.switchHqTab === 'function') window.switchHqTab(hedefPanel);
      /* Ayarlar paneli açıldıktan SONRA odayı seç — `hqSelectCat` çizdiği
         gövdeyi `#hq-settings-main`e yazar ve o panel görünür olmadan çizmek
         gizli bir gövde üretirdi. */
      if (_guvenligeGit && typeof window.hqSelectCat === 'function') {
        try { window.hqSelectCat('guvenlik'); } catch (e) { console.warn('[nav] Güvenlik odası açılamadı:', e); }
      }
    } else if (tab === 'planner') {
      var p = document.getElementById('planner-iframe');
      if (p && !window._plannerInited) {
        var tok = (typeof _getToken === 'function') ? _getToken() : '';
        p.src = window.location.origin + '/ui/planner.html?v=' + Date.now() + (tok ? '&token=' + tok : '');
        window._plannerInited = true;
      }
    } else if (tab === 'yedek') {
      /* Her açılışta tazelenir (eski HQ panelinin kuralı): tur arka planda koşabilir. */
      if (typeof window.yedeklemePanelAc === 'function') window.yedeklemePanelAc();
    } else if (tab === 'galeri') {
      /* Tembel: src yalnız sekme İLK açıldığında atanır — büyük bir klasör
         taraması uygulamanın açılışını bekletmez. Token URL'e YAZILMAZ: iframe
         aynı origin, ana pencerenin sessionStorage'ını paylaşır (galeri.js okur). */
      var g = document.getElementById('galeri-iframe');
      if (g && !window._galeriInited) {
        g.src = window.location.origin + '/ui/galeri.html?v=' + Date.now();
        window._galeriInited = true;
      }
    } else if (tab === 'dosya') {
      /* Tembel + token URL'e YAZILMAZ (galeri ile aynı gerekçe). */
      var d = document.getElementById('dosya-iframe');
      if (d && !window._dosyaInited) {
        d.src = window.location.origin + '/ui/dosya.html?v=' + Date.now();
        window._dosyaInited = true;
      }
    }
  }

  function sekmeGec(hedef) {
    if (!document.startViewTransition) return sekmeGecHam(hedef);
    /* Geçiş sürerken ikinci geçiş başlarsa tarayıcı ilkini atlar ve `ready` sözünü REDDEDER
       ("Transition was skipped"). Yakalanmazsa her hızlı sekme değişimi yakalanmamış istisna bırakır
       (11-04: Yuki'nin galeri_ac mesajı sekme geçişinin hemen ardından geldiğinde ölçüldü).
       Sekme yine değişir — `sekmeGecHam` geri çağrısı atlansa da koşar; yalnız animasyon düşer. */
    var vt = document.startViewTransition(function () { sekmeGecHam(hedef); });
    if (vt && vt.ready && vt.ready.catch) vt.ready.catch(function () {});
    return vt;
  }

  // Eski çağrı yolları için ince sarmalayıcı (dropdown navigasyonu üründe yok)
  function switchTabFromDropdown(tabId) { sekmeGec(tabId); }

  /* ── Sekme menüsü çekmecesi (2026-09-25) ──────────────────────────
   * ☰ (#nav-ac) · perde (#nav-backdrop) · çekmece (#tab-nav). Stil kabuk.css
   * "SEKME MENÜSÜ". Eski adı (`toggleTabDropdown`) korunuyor: F kısayolu
   * (core.js) ve eski çağıranlar bu adı biliyor. Argümansız = aç/kapa,
   * boolean = o duruma getir.
   * Kapalıyken `inert`: ekran dışındaki düğmeler Tab ile odak almasın, ekran
   * okuyucu görmesin. Açılınca odak seçili sekmeye, kapanırken (odak
   * çekmecedeyse) ☰'a döner — görünmeyen bir elemanda kalmasın. */
  function _navAcikMi() { return document.body.classList.contains('nav-acik'); }

  function _navEtiket() {
    var btn = document.getElementById('nav-ac');
    if (btn) btn.setAttribute('aria-label', _tnt(_navAcikMi() ? 'genel.menuyu-kapat' : 'genel.menuyu-ac'));
  }

  function toggleTabDropdown(v) {
    var btn = document.getElementById('nav-ac');
    var nav = document.getElementById('tab-nav');
    if (!nav) return;
    var ac = (typeof v === 'boolean') ? v : !_navAcikMi();
    document.body.classList.toggle('nav-acik', ac);
    if (btn) btn.setAttribute('aria-expanded', ac ? 'true' : 'false');
    _navEtiket();
    if (ac) {
      nav.removeAttribute('inert');
      var etkin = nav.querySelector('.tab-btn[aria-selected="true"]') || nav.querySelector('.tab-btn:not([hidden])');
      if (etkin) etkin.focus({ preventScroll: true });
    } else {
      nav.setAttribute('inert', '');
      if (btn && nav.contains(document.activeElement)) btn.focus({ preventScroll: true });
    }
  }

  (function _navCekmeceBagla() {
    var btn = document.getElementById('nav-ac');
    var nav = document.getElementById('tab-nav');
    var bd = document.getElementById('nav-backdrop');
    if (!nav) return;
    /* Eski rayın anahtarları (daraltma + sürüklenebilir ☰) — artık okunmuyor */
    try { localStorage.removeItem('alice_nav_collapsed'); localStorage.removeItem('yuki_fab_pos'); } catch (e) {}
    if (btn) btn.addEventListener('click', function () { toggleTabDropdown(); });
    if (bd) bd.addEventListener('click', function () { toggleTabDropdown(false); });
    /* Esc YALNIZ çekmeceyi kapatır. Yakalama evresinde + yayılım durdurulur:
       yoksa aynı tuş AYARLAR katmanını da kapatır (aşağıda) ve Yuki'nin sesini
       keser (core.js genel Esc) — kullanıcı yalnız menüyü kapatmak istedi. */
    window.addEventListener('keydown', function (e) {
      if (e.key !== 'Escape' || !_navAcikMi()) return;
      e.preventDefault();
      e.stopImmediatePropagation();
      toggleTabDropdown(false);
    }, true);
    /* Sekme seçilince kapan — seçilen sekme çekmecenin arkasında kalmasın */
    nav.addEventListener('click', function (e) {
      if (e.target.closest && e.target.closest('.tab-btn')) setTimeout(function () { toggleTabDropdown(false); }, 120);
    });
    document.addEventListener('viewmodechange', function () { toggleTabDropdown(false); });
    /* PLAN aynı kökenli iframe: ☰ onun sol üst köşesine biner (masaüstünde
       #tab-bar, ≤768'de gizlenince #stats-bar + #filter-bar). Pay kabuktan
       verilir — planner.html tek başına açılınca ☰ yoktur, pay da olmamalı. */
    function navPayi(id, css) {
      var fr = document.getElementById(id);
      if (fr) fr.addEventListener('load', function () {
        try {
          var d = fr.contentDocument;
          if (!d || !d.head || d.getElementById('yuki-nav-bosluk')) return;
          var st = d.createElement('style');
          st.id = 'yuki-nav-bosluk';
          st.textContent = css;
          d.head.appendChild(st);
        } catch (e) { console.warn('[nav] ' + id + ' payı eklenemedi:', e); }
      });
    }
    navPayi('planner-iframe', '#tab-bar{padding-inline-start:52px!important}'
      + '@media (max-width:768px){#stats-bar,#filter-bar,.g-ust,#defter-sayfalar,#ayp-ust,#fstrip-tabs{padding-inline-start:52px!important}}');  // .g-ust: GÜNDEM başlığı · #ayp-ust: TAKVİM ay şeridi · #fstrip-tabs: FİTNES alt sekmeleri (09-26) — bunlar açıkken üst şeritler gizli
    /* GALERİ + DOSYA da aynı kökenli iframe; 11-02'ye kadar pay yoktu → ☰ Galeri'nin
       klasör simgesini, Dosya'nın mührünü/başlığını (390'da "DOSYALAR" → "SYALAR") örtüyordu. */
    navPayi('galeri-iframe', '.gl-ust{padding-inline-start:52px!important}'
      + '@media (max-width:1239px){.gl-ray-bas{padding-inline-start:28px!important}}');  // telefonda çekmece başlığı da ☰ altında kalmasın: 24 px çekmece payı + 28 = 52 (goz 11-15)
    navPayi('dosya-iframe', '.dy-ust{padding-inline-start:52px!important}');
  })();

  /* ── Sekme/özellik bayrakları (açık kaynak sürüm) ─────────────────────────
   * Kademe kilidi kaldırıldı: PLAN · AJAN · MAP · Yedek ·
   * Bildirim · Cihazlar · Yüz herkese açık. Bayraklar ve `refresh*Access`
   * adları korunuyor çünkü ajan-view/intro-sequences
   * bunları okuyor; artık ağa gitmeden hepsi `true` yazar.
   * Araç kapısı BURADA DEĞİL — `/api/yetki` → `tools`, sohbet-sahne okur. */
  var _SEKME_DUGMELERI = ['tab-btn-planner', 'tab-btn-map', 'tab-btn-ajan', 'tab-btn-yedek', 'tab-btn-galeri', 'tab-btn-dosya'];
  function _hepsiAcik() {
    window._yukiPlannerOk = true;
    window._yukiYedekOk = true;
    window._yukiPushOk = true;
    window._yukiCihazOk = true;
    window._yukiMapOk = true;
    window._yukiPanelOk = true;
    window._yukiAjanOk = true;
    window._yukiFacesOk = true;
    _SEKME_DUGMELERI.forEach(function (id) {
      var b = document.getElementById(id);
      if (b) b.hidden = false;
    });
  }
  _hepsiAcik();

  /* Bayraklar yazıldığında duyur: HQ menüsü ve görünümler bu olayı dinliyor. */
  function _yetkiDuyur() {
    try { document.dispatchEvent(new CustomEvent('yuki:entitlements')); } catch (e) {}
  }

  function _ac() { _hepsiAcik(); _yetkiDuyur(); return Promise.resolve(true); }
  var refreshPlannerAccess = _ac;
  var refreshPanelAccess = _ac;
  var refreshAjanAccess = _ac;
  var refreshFaceAccess = _ac;

  /* ── Electron pencere modu ────────────────────────────────────────────────
   * Tek gerçek kaynak main/window-state.json. localStorage yalnız hızlı boyama
   * ve getWindowMode ulaşılamazsa yedektir; main'den gelen her durum onu ezer. */
  var PENCERE_KAYIT_ANAHTARI = 'yuki_pencere_v1';
  var PENCERE_MODLARI = ['tam', 'panel', 'mini'];
  var PENCERE_KOSELERI = ['sol-ust', 'sag-ust', 'sol-tam', 'sag-tam', 'sol-alt', 'sag-alt'];
  function _pencereEtiketleri() {
    return {
      tam: _tnt('pencere.tam'),
      panel: _tnt('pencere.panel'),
      mini: _tnt('pencere.mini')
    };
  }

  /* Köşe seçenekleri MODA BAĞLI — 6'sını birden sunmak yanıltıcı olurdu.
   * Ölçüldü (modBoyutu, 1920x1035 çalışma alanı): panel tam yükseklikte olduğu için
   * sol-ust / sol-tam / sol-alt ÜÇÜ DE aynı konumu veriyor (x=1456 y=61). Kullanıcıya
   * üç seçenek gösterip aynı sonucu vermek, bu depodaki "ilan edilen ama uygulanmamış
   * özellik" yasağının ta kendisi. Mini'de de -tam ile -ust aynı sonucu veriyor.
   * Sunulan: panel 2 · mini 4. Etiketler moda göre okunur ("Sol kenar" ≠ "Sol üst").
   * burada METİN değil ANAHTAR tutulur — metin çizim anında çözülür, yoksa
   * yükleme anındaki dilde donardı. */
  var PENCERE_KOSE_SECENEKLERI = {
    panel: [
      { deger: 'sol-tam', anahtar: 'tab-nav.pencere-sol-kenar' },
      { deger: 'sag-tam', anahtar: 'tab-nav.pencere-sag-kenar' }
    ],
    mini: [
      { deger: 'sol-ust', anahtar: 'tab-nav.pencere-sol-ust' },
      { deger: 'sag-ust', anahtar: 'tab-nav.pencere-sag-ust' },
      { deger: 'sol-alt', anahtar: 'tab-nav.pencere-sol-alt' },
      { deger: 'sag-alt', anahtar: 'tab-nav.pencere-sag-alt' }
    ]
  };

  /* Mod değişince eldeki köşe o modda anlamlı olmayabilir (mini'de 'sol-alt' iken
   * panel'e geçiş). Sol/sağ ekseni KORUNUR — kullanıcının asıl tercihi odur. */
  function pencereKosesiniUyarla(mod, kose) {
    var secenekler = PENCERE_KOSE_SECENEKLERI[mod];
    if (!secenekler) return kose;
    for (var i = 0; i < secenekler.length; i++) {
      if (secenekler[i].deger === kose) return kose;
    }
    var sag = String(kose).indexOf('sag') === 0;
    return mod === 'panel'
      ? (sag ? 'sag-tam' : 'sol-tam')
      : (sag ? 'sag-ust' : 'sol-ust');
  }
  var pencereDurumu = { mod: 'tam', kose: 'sag-tam' };
  var pencereApi = null;
  var pencereKonumlandirmaKapali = false;
  var pencereKisitSebebiVar = false;   // not metni ana süreçten mi geldi (o zaman dil tazeleyici dokunmaz)   // main konumlandırmayı uygulayamadığını bildirirse true olur

  function pencereDurumuGecerli(durum) {
    return !!durum
      && PENCERE_MODLARI.indexOf(durum.mod) !== -1
      && PENCERE_KOSELERI.indexOf(durum.kose) !== -1;
  }

  function pencereYedeginiOku() {
    try {
      var durum = JSON.parse(localStorage.getItem(PENCERE_KAYIT_ANAHTARI) || 'null');
      return pencereDurumuGecerli(durum) ? durum : null;
    } catch (e) {
      return null;
    }
  }

  function pencereDurumunuKaydet(durum) {
    try {
      localStorage.setItem(PENCERE_KAYIT_ANAHTARI, JSON.stringify(durum));
    } catch (e) {}
  }

  /* Köşe listesini moda göre yeniden çiz. Seçili değer korunur (uyarlanmışsa uyarlanmış hâli). */
  function pencereKoseSecenekleriniCiz(mod, secili) {
    var koseSec = document.getElementById('pencere-kose-sec');
    var secenekler = PENCERE_KOSE_SECENEKLERI[mod];
    if (!koseSec || !secenekler) return;

    var mevcut = koseSec.getAttribute('data-mod');
    if (mevcut !== mod) {
      koseSec.textContent = '';
      secenekler.forEach(function (s) {
        var opt = document.createElement('option');
        opt.value = s.deger;
        opt.textContent = _tnt(s.anahtar);
        koseSec.appendChild(opt);
      });
      koseSec.setAttribute('data-mod', mod);
    }
    koseSec.value = secili;
  }

  function pencereModuUygula(durum, kaydet) {
    if (!pencereDurumuGecerli(durum)) return false;

    pencereDurumu = { mod: durum.mod, kose: pencereKosesiniUyarla(durum.mod, durum.kose) };
    document.documentElement.setAttribute('data-pencere', pencereDurumu.mod);

    var tetik = document.getElementById('pencere-mod-dugme');
    if (tetik) {
      var etiketler = _pencereEtiketleri();
      tetik.setAttribute('aria-label', _tnt('tab-nav.pencere-modu-label', { mod: etiketler[pencereDurumu.mod] }));
      tetik.querySelectorAll('[data-pencere-ikon]').forEach(function (ikon) {
        ikon.toggleAttribute('hidden', ikon.getAttribute('data-pencere-ikon') !== pencereDurumu.mod);
      });
    }

    document.querySelectorAll('[data-pencere-mod]').forEach(function (dugme) {
      var aktif = dugme.getAttribute('data-pencere-mod') === pencereDurumu.mod;
      dugme.setAttribute('aria-checked', aktif ? 'true' : 'false');
      dugme.setAttribute('tabindex', aktif ? '0' : '-1');
    });

    var koseAlani = document.getElementById('pencere-kose-alani');
    if (koseAlani) koseAlani.hidden = pencereDurumu.mod === 'tam';

    if (pencereDurumu.mod !== 'tam') {
      pencereKoseSecenekleriniCiz(pencereDurumu.mod, pencereDurumu.kose);
    }

    if (kaydet) pencereDurumunuKaydet(pencereDurumu);
    return true;
  }

  function pencereModunuIste(mod, kose) {
    if (!pencereApi || typeof pencereApi.setWindowMode !== 'function') return;
    var istek = { mod: mod, kose: kose };
    if (!pencereModuUygula(istek, true)) return;
    try {
      /* pencereDurumu.kose — istek.kose DEĞİL. Köşe moda göre uyarlanmış olabilir
       * (mini'de 'sol-alt' iken panel'e geçiş → 'sol-tam'). Ham hâlini main'e
       * gönderirsek arayüz bir köşeyi, pencere başka köşeyi gösterir. */
      pencereApi.setWindowMode(pencereDurumu.mod, pencereDurumu.kose);
    } catch (e) {
      /*  · LOG: kullanıcıya SÖYLENMEZ çünkü main zaten `onWindowModeFailed`
         ile ölçüp haber veriyor (aşağıda) — iki mesaj çift uyarı olurdu. Ama izsiz
         kalırsa "Panel'e bastım, pencere kıpırdamadı" şikâyeti teşhis edilemez. */
      console.warn('[yuki] pencere modu isteği gönderilemedi:', e);
    }
  }

  function pencereArayuzunuBagla() {
    var tetik = document.getElementById('pencere-mod-dugme');
    var popover = document.getElementById('pencere-mod-popover');
    var modDugmeleri = Array.prototype.slice.call(document.querySelectorAll('[data-pencere-mod]'));
    var koseSec = document.getElementById('pencere-kose-sec');

    modDugmeleri.forEach(function (dugme, sira) {
      dugme.addEventListener('click', function () {
        pencereModunuIste(dugme.getAttribute('data-pencere-mod'), pencereDurumu.kose);
      });
      dugme.addEventListener('keydown', function (event) {
        var ileri = event.key === 'ArrowRight' || event.key === 'ArrowDown';
        var geri = event.key === 'ArrowLeft' || event.key === 'ArrowUp';
        if (!ileri && !geri && event.key !== 'Home' && event.key !== 'End') return;
        event.preventDefault();
        var hedefSira = event.key === 'Home' ? 0
          : event.key === 'End' ? modDugmeleri.length - 1
          : (sira + (ileri ? 1 : -1) + modDugmeleri.length) % modDugmeleri.length;
        var hedef = modDugmeleri[hedefSira];
        hedef.focus();
        pencereModunuIste(hedef.getAttribute('data-pencere-mod'), pencereDurumu.kose);
      });
    });

    if (koseSec) {
      koseSec.addEventListener('change', function () {
        pencereModunuIste(pencereDurumu.mod, koseSec.value);
      });
    }

    if (popover && tetik) {
      popover.addEventListener('toggle', function () {
        var acik = popover.matches(':popover-open');
        tetik.setAttribute('aria-expanded', acik ? 'true' : 'false');
        if (acik) {
          var aktif = popover.querySelector('[data-pencere-mod][aria-checked="true"]');
          if (aktif) aktif.focus();
        } else if (popover.contains(document.activeElement)) {
          tetik.focus();
        }
      });
    }
  }

  function pencereModunuBagla() {
    var tetik = document.getElementById('pencere-mod-dugme');
    var api = window.yukiApp;

    // Web/PWA'da çalışmayan bir özellik ilan edilmez.
    if (!api || typeof api.setWindowMode !== 'function') {
      if (tetik) tetik.hidden = true;
      /* Destek işareti BASILMAZ → GÖRÜNÜM menüsü PENCERE bölümünü hiç çizmez.
         Tarayıcıda çalışmayan bir bölümü soluk göstermek yerine yok sayıyoruz;
         "ilan et ama uygulama" karşıtı kural (C4). */
      document.documentElement.removeAttribute('data-pencere-destek');
      return;
    }

    pencereApi = api;
    pencereModuUygula(pencereYedeginiOku() || pencereDurumu, false);
    pencereArayuzunuBagla();
    if (tetik) tetik.hidden = false;
    /* 🔑 Denetimler artık üst şeritte değil, GÖRÜNÜM menüsünün PENCERE bölümünde
       (2026-09-06). Menü lazy kurulur ve bu bağlamadan SONRA açılabilir; bu yüzden
       destek bilgisi DOM'a yazılıyor — menü kurulurken okur, çağrı sırasına
       bağımlılık kalmaz. */
    document.documentElement.setAttribute('data-pencere-destek', '1');

    /* 🔑 ÖNDEN SOR (2026-09-06). Eskiden kısıt yalnız bir DENEME başarısız olunca
     * öğreniliyordu — ve Wayland'de o deneme "başarılı" görünebiliyordu (eşit
     * boyutlu köşe değişiminde sapma 0 çıkıyor, ölçüldü). Yani kullanıcı düğmeye
     * basıyor, hiçbir şey olmuyor, uyarı da gelmiyordu. Yetenek artık ana süreçten
     * VERİ olarak alınıyor; özellik daha ilk açılışta dürüstçe kapanıyor. */
    if (typeof api.getWindowSupport === 'function') {
      try {
        Promise.resolve(api.getWindowSupport()).then(function (y) {
          if (!y || y.destekli) return;
          pencereKonumlandirmaKapali = true;
          pencereKonumlandirmaKisitiniIsle(y.sebep, y.kural);
        }).catch(function (e) {
          /* Yetenek okunamadıysa ENGELLEME: yanlışlıkla kapatmak çalışan bir
             özelliği öldürür, açık bırakmak yalnız eski davranışa döner. */
          console.warn('[yuki] pencere yeteneği okunamadı — özellik açık bırakıldı:', e);
        });
      } catch (e) { console.warn('[yuki] getWindowSupport çağrılamadı:', e); }
    }

    if (typeof api.onWindowMode === 'function') {
      try {
        api.onWindowMode(function (durum) { pencereModuUygula(durum, true); });
      } catch (e) { console.warn('[yuki] pencere modu dinleyicisi bağlanamadı:', e); }
    }
    if (typeof api.getWindowMode === 'function') {
      try {
        Promise.resolve(api.getWindowMode())
          .then(function (durum) { pencereModuUygula(durum, true); })
          .catch(function (e) { console.warn('[yuki] pencere modu okunamadı (kayıtlı mod korunuyor):', e); });
      } catch (e) { console.warn('[yuki] getWindowMode çağrılamadı:', e); }
    }

    /* 🔴 Mod uygulanmadıysa kullanıcı GÖRMELİ. Ölçüldü (2026-08-21, Hyprland/Wayland):
     * Panel'e basınca yazı küçülüyor ve cam geliyor ama pencere kıpırdamıyor — arayüz
     * "oldu" diyor, iş olmuyor. Sessiz başarısızlık bu üründe yasak (C4).
     * Main sonucu ÖLÇÜP haber veriyor; burada tahmin yapılmıyor. */
    if (typeof api.onWindowModeFailed === 'function') {
      try {
        api.onWindowModeFailed(function (bilgi) {
          if (pencereKonumlandirmaKapali) return;   // bir kez söyle, her denemede değil
          pencereKonumlandirmaKapali = true;
          pencereModuUygula({ mod: 'tam', kose: pencereDurumu.kose }, true);
          /* Ana süreç artık sebebi ve masaüstü kuralını da yolluyor; yoksa
             fonksiyon kendi genel metnine düşer (eski davranış korunur). */
          pencereKonumlandirmaKisitiniIsle(bilgi && bilgi.sebep, bilgi && bilgi.kural);
        });
      } catch (e) {
        /* 🔴 Bunun sessiz kalması C4'ün EN pahalı hâli: bu dinleyici bağlanamazsa
           Panel/Mini'nin çalışmadığını söyleyen tek kanal ölür ve kullanıcı
           "oldu" görüp iş olmuyor. Kullanıcıya buradan mesaj basılamaz (henüz
           başarısızlık YOK), ama iz zorunlu. */
        console.warn('[yuki] pencere başarısızlık dinleyicisi bağlanamadı — Panel/Mini uyarısı çalışmayabilir:', e);
      }
    }
  }

  /* Konumlandırma bu pencere yöneticisinde çalışmıyor: Panel/Mini'yi devre dışı bırak
   * ve SEBEBİNİ söyle. Gizlemek yerine devre dışı bırakıyoruz — kullanıcı seçeneğin
   * var olduğunu ama neden çalışmadığını bilsin. Devre dışı olan GERÇEKTEN devre dışı
   * (soluk ama tıklanabilir bırakmak daha kötüsü olurdu). */
  function pencereKonumlandirmaKisitiniIsle(sebep, kural) {
    document.querySelectorAll('[data-pencere-mod]').forEach(function (dugme) {
      var mod = dugme.getAttribute('data-pencere-mod');
      if (mod === 'tam') return;
      dugme.disabled = true;
      dugme.setAttribute('aria-disabled', 'true');
      dugme.setAttribute('title', _tnt('tab-nav.pencere-konumlandirma-kisitli'));
    });

    var koseAlani = document.getElementById('pencere-kose-alani');
    if (koseAlani) koseAlani.hidden = true;

    /* Not, denetimlerin YANINDA durmalı. 2026-09-06'da denetimler üst şeritten
       GÖRÜNÜM menüsüne taşındı; not eski popover'a yazılsaydı DOM'da öksüz kalır
       ve kullanıcı Panel/Mini'nin neden kapalı olduğunu HİÇ göremezdi — kısıtı
       ölçüp iletip göstermemek'te bir kez düşülen tuzağın aynısı.
       ⚠️ Hedef önce `.vmm-pencere`: kaynak kabın çocukları menü kurulurken
       TAŞINIYOR; menü zaten kurulmuşsa kaynağa yazmak notu boş kaba gömerdi. */
    var kap = document.querySelector('.vmm-pencere')
      || document.getElementById('pencere-mod-kaynak');
    if (kap && !document.getElementById('pencere-kisit-notu')) {
      var not = document.createElement('p');
      not.id = 'pencere-kisit-notu';
      not.className = 'pencere-kisit-notu';
      pencereKisitSebebiVar = !!sebep;
      not.textContent = sebep || _tnt('tab-nav.pencere-kisit-notu');
      kap.appendChild(not);

      /* Kullanıcıyı çıkışsız bırakma: yapamadığımız şeyi ONUN yapabileceği
         biçimde ver. Metin `textContent` ile basılıyor — kural dizesi ana
         süreçten geliyor ve innerHTML olsaydı enjeksiyon yüzeyi açılırdı. */
      if (kural && kural.metin) {
        var kutu = document.createElement('div');
        kutu.className = 'pencere-kural-kutusu';

        var baslik = document.createElement('div');
        baslik.className = 'pencere-kural-baslik';
        if (!kural.baslik) baslik.setAttribute('data-varsayilan', '1');
        baslik.textContent = kural.baslik || _tnt('tab-nav.masaustu-kurali');
        kutu.appendChild(baslik);

        var pre = document.createElement('pre');
        pre.className = 'pencere-kural-metin';
        pre.textContent = kural.metin;
        kutu.appendChild(pre);

        if (kural.tur === 'kural' && navigator.clipboard) {
          var kop = document.createElement('button');
          kop.type = 'button';
          kop.className = 'dg dg-sessiz pencere-kural-kopyala';
          kop.textContent = _tnt('tab-nav.kurali-kopyala');
          kop.addEventListener('click', function () {
            navigator.clipboard.writeText(kural.metin).then(function () {
              kop.textContent = _tnt('tab-nav.kopyalandi');
              setTimeout(function () { kop.textContent = _tnt('tab-nav.kurali-kopyala'); }, 2000);
            }).catch(function () { kop.textContent = _tnt('tab-nav.kopyalanamadi'); });
          });
          kutu.appendChild(kop);
        }
        kap.appendChild(kutu);
      }
    }

    /* 'in son adımı. Main süreci sonucu ÖLÇÜP bildiriyor
       (uygulama.js::moduUygula → 'pencere-modu-uygulanamadi'), düğmeler
       kapanıyor, açılıra not ekleniyor — ama ANLIK bildirim `window.toast`
       ile yazılmıştı ve o hiç tanımlı değildi. Zincirin son halkası kopuktu:
       ölçüm doğru, iletim doğru, GÖSTERİM yok. */
    if (typeof window.bildir === 'function') {
      window.bildir(_tnt('tab-nav.panel-modu-uygulanamadi'), 'uyari', 6000);
    }
  }

  document.addEventListener('keydown', function (event) {
    if (!pencereApi || !event.ctrlKey || !event.shiftKey || event.altKey || event.metaKey) return;
    var tag = document.activeElement ? document.activeElement.tagName : '';
    var girdiAktif = tag === 'INPUT' || tag === 'TEXTAREA';
    if (girdiAktif) return;

    var mod = event.key === '1' ? 'tam' : event.key === '2' ? 'panel' : event.key === '3' ? 'mini' : '';
    if (!mod) return;
    event.preventDefault();
    pencereModunuIste(mod, pencereDurumu.kose);
  });

  /* AYARLAR katmanı Escape ile kapanır.
     Katman rayı örttüğü için geri dönüş yolu görünmez; tek çıkışı bir düğmeye
     bağlamak, o düğmeyi kaçıran kullanıcıyı kilitler. Escape klavye kullanıcısı
     için zaten beklenen davranış.
     ⚠️ Yalnız katman AÇIKKEN ve odak bir metin alanında DEĞİLKEN — yoksa
     ayar yazarken Escape ekranı kapatırdı. */
  document.addEventListener('keydown', function (e) {
    if (e.key !== 'Escape') return;
    var hq = document.getElementById('tab-hq');
    if (!hq || !hq.hasAttribute('data-aktif')) return;
    var a = document.activeElement;
    if (a && (a.tagName === 'INPUT' || a.tagName === 'TEXTAREA' || a.isContentEditable)) return;
    if (document.querySelector('[popover]:popover-open, dialog[open]')) return;  // önce o kapansın
    sekmeGec('chat');
  });

  window.switchTab = sekmeGec;

  /* Yuki `show_media` → WS `{type:'galeri_ac', id}` (core.js): GALERİ'ye geç ve o dosyayı fişte aç.
     galeri.js `?ac=` parametresini yalnız YÜKLENİRKEN okur → iframe her çağrıda yeni src ile kurulur
     (sekme önceden açıksa da). src sekme geçişinden ÖNCE atanır: tembel ilk kurulum `?ac`'siz src ile
     ezmesin diye `_galeriInited` önce işaretlenir. Kimlik yalnız URL parametresi olarak girer (kodlanır). */
  window.galeriAc = function (id) {
    id = String(id == null ? '' : id);
    if (!id || id.length > 64) return false;
    var g = document.getElementById('galeri-iframe');
    if (!g) return false;
    g.src = window.location.origin + '/ui/galeri.html?ac=' + encodeURIComponent(id) + '&v=' + Date.now();
    window._galeriInited = true;
    sekmeGec('galeri');
    return true;
  };
  window.switchTabFromDropdown = switchTabFromDropdown;
  window.toggleTabDropdown = toggleTabDropdown;
  window.refreshPlannerAccess = refreshPlannerAccess;
  window.refreshPanelAccess = refreshPanelAccess;
  window.refreshAjanAccess = refreshAjanAccess;
  window.refreshFaceAccess = refreshFaceAccess;

  /* Eski çağıranlar (app-lock.js kilit açılınca) için korunur. */
  function refreshAllAccess() { return _ac(); }
  window.refreshAllAccess = refreshAllAccess;

  /*  · dil tazeleyici — bu dosyanın ŞU AN ekranda olan metinleri.
     Köşe <select>'i index.html'de data-i18n'liydi ama pencereKoseSecenekleriniCiz
     seçenekleri silip yeniden kuruyor → sahibi bu dosya, tazeleme de burada.
     Seçili değer korunur; ağa gidilmez; ana süreçten gelen sebep/kural metnine dokunulmaz. */
  window.addEventListener('yuki-dil-degisti', function () {
    _navEtiket();
    var tetik = document.getElementById('pencere-mod-dugme');
    if (tetik && pencereApi) {
      tetik.setAttribute('aria-label', _tnt('tab-nav.pencere-modu-label', { mod: _pencereEtiketleri()[pencereDurumu.mod] }));
    }
    var koseSec = document.getElementById('pencere-kose-sec');
    if (koseSec && koseSec.hasAttribute('data-mod')) {
      var mod = koseSec.getAttribute('data-mod');
      var secili = koseSec.value;
      koseSec.removeAttribute('data-mod');   // zorla yeniden çiz
      pencereKoseSecenekleriniCiz(mod, secili);
    }
    if (pencereKonumlandirmaKapali) {
      document.querySelectorAll('[data-pencere-mod][aria-disabled="true"]').forEach(function (dugme) {
        dugme.setAttribute('title', _tnt('tab-nav.pencere-konumlandirma-kisitli'));
      });
    }
    var not = document.getElementById('pencere-kisit-notu');
    if (not && !pencereKisitSebebiVar) not.textContent = _tnt('tab-nav.pencere-kisit-notu');
    document.querySelectorAll('.pencere-kural-baslik[data-varsayilan]').forEach(function (b) {
      b.textContent = _tnt('tab-nav.masaustu-kurali');
    });
    document.querySelectorAll('.pencere-kural-kopyala').forEach(function (k) {
      k.textContent = _tnt('tab-nav.kurali-kopyala');
    });
  });

  // HTML başlangıç durumu da aynı tek mekanizmadan geçsin.
  sekmeGecHam(document.documentElement.getAttribute('data-tab') || 'chat');
  pencereModunuBagla();

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', refreshAllAccess);
  } else {
    refreshAllAccess();
  }
})();
