/* ════════════════════════════════════════════════════════════════════
   chat-modes.js — Görünüm Modu Yöneticisi (Faz 0)

   2 görünüm modu: chat (SOHBET) · hud-ring (HUD Halka).
   game (Komuta Merkezi) kodda durur ama üründe seçicide YOK.
   2026-10-04: KLASİK + TAM BOY tek SOHBET modunda birleşti. TAM BOY'un
   bekleme klibi yaşıyor ama mod olarak değil, SOHBET sahnesinin VİDEO kipi
   olarak (modes/sohbet-sahne.js). Kayıtlı 'fullbody' → 'chat' + VİDEO kipi.
   index.html'deki toggleViewMode/_applyViewMode ikilisini sarar;
   #mode-toggle butonunu mini menüye çevirir (modlar + GRAFİK bölümü).
   ⚠️ Bu yorumla aşağıdaki MODES listesi ayrışırsa kusur oradadır: kişiselde
   "4 seçenekli menü" yazarken listede 3 vardı ve TAM BOY modu ölmüştü.
   hud-ring ve game modlarının CSS/JS dosyaları ilk seçimde lazy-load edilir.

   ?widget=1 (yuki-widget iframe) modunda TAMAMEN devre dışıdır.
   ════════════════════════════════════════════════════════════════════ */
(function () {
  'use strict';
  if (new URLSearchParams(location.search).has('widget')) return; // widget guard

  /* ── Çeviri (FAZ 3 · Dalga 2 · Blok 7 →  kuyruğu) ─────────────────
   * Dosyanın tamamı 2026-09-22'de çevrildi. MODES/CHARACTERS
   * modül düzeyi sabit — metin OKUMA ANINDA çözülsün diye `get` ile tanımlı
   * (game-mode.js / hud-ring.js `window.MODE_CHARACTERS`'tan `c.title`
   * okuyor; getter onların kodunu değiştirmeden dile uydurur).
   *
   * 🔴 Adı `_t` — düz `t` DEĞİL. Aşağıdaki `TIERS.forEach(t => …)` geri
   * çağırması aynı adı kullanıyor ve yardımcıyı gölgelerdi. Bu depoda `t`
   * gölgelenmesi Blok 1'de üç ayrı yerde yaşandı; burada baştan kaçınıldı.
   */
  function _t(anahtar, degerler) {
    return (window.YukiDil && window.YukiDil.t)
      ? window.YukiDil.t(anahtar, degerler) : String(anahtar);
  }

  // 2026-08-08: TAM BOY eklendi. `fullbody` bu listede olmadığı için `setViewMode`
  // onu geçersiz sayıp 'chat'e çeviriyordu → `body.fullbody-mode` hiç yazılmıyor,
  // mod UI'dan ULAŞILAMIYORDU. CSS'i, markup'ı ve core.js `_applyViewMode`'u vardı;
  // eksik olan tek şey menü girdisiydi. (Kişisel Alice'te de aynı kusur çıktı.)
  // 2026-10-04: `fullbody` listeden ÇIKTI — bu kez bilerek. Klibi
  // SOHBET'in VİDEO kipinde yaşıyor; aşağıdaki göç kayıtlı değeri taşır.
  // `metin`: sözlük kökü. 'chat' anahtarı localStorage'da ve HALKA'da kalıyor
  // (müşteri verisi), görünen adı ise SOHBET — kök ayrı verildi ki 'chat'
  // anahtarını yeniden adlandırmak gerekmesin.
  const _mod = (key, icon, metin) => ({
    key, icon,
    get label() { return _t('gorunum.mod.' + (metin || key) + '.ad'); },
    get desc()  { return _t('gorunum.mod.' + (metin || key) + '.aciklama'); },
  });
  const MODES = [
    _mod('chat', '❄', 'sohbet'),
    _mod('hud-ring', '◎'),
    // OYUN (game) modu P1 üründen çıkarıldı — kod (game-mode.js) kalır, üst tier'da açılabilir
  ];
  const VALID = MODES.map(m => m.key);
  const EXT_CLASSES = ['hud-ring-mode', 'game-mode'];

  // `label` karakterin ADI (dil-nötr, çevrilmez); `title` unvanı — çevrilir.
  const _kar = (key, label) => ({
    key, label,
    get title() { return _t('karakter.' + key + '.unvan'); },
  });
  const CHARACTERS = [
    // 2026-11-14 (geliştirici kararı): yalnız Yuki kalır — Nova/Kira/Sera/Rei ve
    // varlıkları depodan çıktı. Liste yapısı DURUR: ileride karakter eklemek = buraya bir
    // satır + assets/characters/<key>_fullbody.* + backend personas.PERSONAS girdisi.
    // Tek karakterde seçici şerit hiç kurulmaz (COK_KARAKTER) — kişisel chat-modes.js deseni.
    _kar('yuki', 'YUKI'),
  ];
  const COK_KARAKTER = CHARACTERS.length > 1;
  const VALID_CHARS = CHARACTERS.map(c => c.key);

  // Açık kaynak sürüm: karakter kilidi yok — beşi de açık. Dizi ve `_charLocked`
  // korunuyor çünkü hud-ring.js bu referansı okuyor; `/api/yetki` → `characters`
  // ile yerinde tazelenir (backend hepsini döndürür).
  // ⚠️ Dizi **yerinde** güncellenir, yeniden ATANMAZ (hud-ring.js referansı tutar).
  const UNLOCKED_CHARS = VALID_CHARS.slice();
  const _charLocked = (k) => UNLOCKED_CHARS.indexOf(k) === -1;
  window.MODE_UNLOCKED_CHARS = UNLOCKED_CHARS;

  // ── localStorage anahtarları — TEK KAYNAK ──
  // 🔴 2026-08-31: bu dosya versiyonsuz ('yukiViewMode' / 'yukiCharacter') yazıyordu,
  // ama core.js'teki `_migrateLocalStorageKeys` (core.js:305) o anahtarları `_v1`'e
  // KOPYALAYIP ESKİSİNİ SİLİYOR. Sıra şuydu: kullanıcı HALKA seçer → burası
  // 'yukiViewMode'a yazar → sonraki açılışta göç onu alıp götürür → burası null
  // okur → sessizce KLASİK'e döner. Yani HALKA ve OYUN modları ile karakter
  // seçimi sayfa yenilemesinden ASLA sağ çıkmıyordu; kullanıcıya hata da
  // görünmüyordu, sadece seçtiği şey "unutuluyordu".
  // Ölçüldü (3 senaryo): eski anahtar · yeni anahtar · ikisi birden → ÜÇÜNDE de
  // getViewMode()==='chat', #hr-ring yok, HudRing hiç yüklenmiyor.
  // Bu ayrıca "K2 kapısı hep KLASİK'te koştu" gözleminin sebebiydi:
  // tur HALKA'ya geçemiyordu çünkü ürün HALKA'yı geri yükleyemiyordu.
  // Sabit tutuluyor ki üçüncü bir çağrı yeri eklendiğinde aynı tuzağa düşülmesin.
  const LS_MOD  = 'yukiViewMode_v1';
  const LS_KARAKTER = 'yukiCharacter_v1';

  /* ── HALKA palet sabitleme ────────────────────────────────────────────
     HALKA yüzeyi bilerek KOYU bir sci-fi HUD'u; `hud-ring.css` panel
     zeminlerini sabit koyu yazıyor (131 sabit renk — tasarımın kendisi).
     Ama metin `--ink-*` token'larından geliyordu ve AÇIK temada koyuya
     dönüyordu → koyu zemin üstünde koyu yazı. Ölçüldü (3 mod × 3 tema):
     HALKA+AÇIK **41 ihlal**, diğer 8 hücre 0; en kötüsü 1.21:1 (eşik 4.5).
     Arayüz okunmaz hâle geliyordu ve kimse görmemişti çünkü kapı HALKA'ya
     hiç girememişti (localStorage anahtarı — aynı turda kapandı).

     Neden 131 rengi token'a çevirmedik: HALKA'yı açığa çevirmek kusur
     düzeltmek değil TASARIM DEĞİŞTİRMEK olurdu. Kusur, yüzeyin yarısının
     temayla dönüp yarısının dönmemesiydi; tutarlılık koyu tarafta kuruluyor.

     KAPSAM = `#chat-pane` — HALKA modunda zemini zaten `var(--hr-deep)`
     (koyu) olan kap. Kendi başlık şeridi de içinde; o şerit koyu yüzeyin
     üstünde AÇIK kalıyordu, tutarsızlık oradaydı.

     ⚠️ ÜÇ KAPSAM DENENDİ, ikisi elendi — sırayla ölçüldü:
     ① `<body>` (çok geniş): 41→36. Temaya DOĞRU uyan header öğelerinde ters
        kusur doğurdu (`#vol-icon` açık zemin + açık yazı, 1.79:1) — kusuru
        taşımak düzeltme değildir.
     ② id listesi (çok dar): 41→34. Lazy üretilen panelleri (`#hr-mem-detail`)
        kaçırıyordu; damga `activate()` anında basılıyor, o öğeler sonra doğuyor.
     ③ `#chat-pane` (doğru): **0 ihlal.** Tek kap, lazy paneller de altında.
     ①'in ters kusuru burada TEKRARLAMIYOR çünkü aynı turda tokens.css'teki
     eski-ad köprüsü de kapsanabilir hâle getirildi (`[data-tema="koyu"]`
     seçiciye eklendi) — header'ın zemin token'ları da artık yerel çözülüyor.

     `tema.js` data-tema'yı <html>'e yazar; burası alt kapsam olduğu için
     kullanıcının tema seçimi SİLİNMEZ, yalnız bu modda gölgelenir ve
     moddan çıkınca `_halkaPaletiCoz()` ile geri döner. */
  const HALKA_KAPLAR = ['chat-pane'];
  function _halkaPaletiSabitle() {
    HALKA_KAPLAR.forEach((id) => {
      const el = document.getElementById(id);
      if (el) el.setAttribute('data-tema', 'koyu');
    });
  }
  function _halkaPaletiCoz() {
    HALKA_KAPLAR.forEach((id) => {
      const el = document.getElementById(id);
      if (el) el.removeAttribute('data-tema');
    });
  }

  // Varsayılan: HALKA (hud-ring) — 2026-11-13 (arayüz turu, geliştirici seçimi "sohbet kişiseldeki gibi"):
  // ilk açılış portre + 4 öneri kartı değil, halka + sağda PANEL listesi. Kullanıcı mod seçerse
  // localStorage'da hatırlanır; kayıtlı 'chat' olan mevcut kurulum SOHBET'te kalır (seçimi ezilmez).
  // Not: eski 'game' değeri VALID'de yok → aşağıdaki guard onu varsayılana sıfırlar.
  // 'fullbody' kullanıcısı ise HALKA'ya değil SOHBET'e döner (sohbet görünümündeydi, orada kalsın).
  // 🔑 2026-10-04 TAM BOY göçü: 'fullbody' de artık VALID'de yok. O
  // kullanıcı TAM BOY'u bilerek seçmişti; sessizce 'chat'e düşerken klibini
  // kaybetmesin diye sahne kipi VİDEO yazılır — yalnız kip henüz SEÇİLMEMİŞSE
  // (sonradan RESİM seçtiyse onun kararı ezilmez). Anahtar sohbet-sahne.js'le
  // ortak; o dosya bu IIFE'den SONRA yüklenir (defer sırası) ve değeri okur.
  const LS_SAHNE_KIP = 'yukiSohbetKip_v1';
  const VARSAYILAN_MOD = 'hud-ring';
  let _mode = localStorage.getItem(LS_MOD) || VARSAYILAN_MOD;
  if (_mode === 'fullbody') {
    try { if (!localStorage.getItem(LS_SAHNE_KIP)) localStorage.setItem(LS_SAHNE_KIP, 'video'); } catch (e) { /* depo yoksa kip varsayılanda kalır */ }
    _mode = 'chat'; localStorage.setItem(LS_MOD, 'chat');
  }
  if (!VALID.includes(_mode)) { _mode = VARSAYILAN_MOD; localStorage.setItem(LS_MOD, VARSAYILAN_MOD); }

  let _character = localStorage.getItem(LS_KARAKTER) || 'yuki';
  if (!VALID_CHARS.includes(_character)) { _character = 'yuki'; }

  // ── lazy-load altyapısı ──
  // Cloudflare .js/.css'i 4 saat cache'liyor → sürüm sorgusu ile cache baypas.
  // 🔴 index.html'deki `chat-modes.js?v=` ve sw.js `CACHE_VERSION` ile AYNI kalmalı.
  // Üçü birlikte artmazsa mod CSS düzeltmeleri müşteriye ulaşmaz — detay: index.html yorumu.
  const ASSET_V = '199';   // 2026-11-15 son tur: HALKA HAFIZA kişisel liste kartı (hk kart dili, 503 ya da kapalı → kapalı durumu) (hud-ring.js/css) (önce 198: 2026-11-14 tam hizala: telefonda açılışta tek widget + halka üst yarıda, B1 menü katmanı, B2 son cevap satırı, boşta HAZIR yok (hud-ring.js/css) (önce 197: 2026-11-14 kişisel düzen: HALKA PANEL GÖZ/SİTELER, tema kartı mod menüsüne, yalnız Yuki (hud-ring.js/css, characters.css, game-mode, kara-mana-goz) (önce 196: 2026-11-13 halka merkezi/durum satırı/kayan yazı anahtar yokken 'kurulum gerekli' (önce 195: 2026-11-13 sekme başlığı tek tarz: karakter etiketi #sohbet-karakter (önce 194: 2026-11-13 oss arayüz birleştirmesi: HALKA varsayılan, telefon PANEL çekmecesi (önce 193: 2026-10-17 acik kaynak: JOBS sekmesi kalkti, hud-ring kisayol 6=ajan (önce 192: kademe kilidi kaldirildi (önce 191: Halka SITELER kapisi) (önce 190: 2026-10-12 SITELER goz duzeltmeleri (önce 188: 2026-10-11 Odakli Halka SITELER (önce 187: 2026-10-11 Odakli Halka merkez menusu (önce 186: 2026-10-05  secim menusu cumle duzeni (önce 185: 2026-10-04 goz tur2 (önce 184: 2026-10-04:  SOHBET birlesik mod + HALKA dikey panel/tema (önce 183: 2026-09-25: karakter şeridi alt bilgi bloğuna (önce 182:  game-mode)
  const _loaded = {};
  function _loadCss(href) {
    return new Promise((res, rej) => {
      const l = document.createElement('link');
      l.rel = 'stylesheet'; l.href = href;
      l.onload = res; l.onerror = rej;
      document.head.appendChild(l);
    });
  }
  function _loadJs(src) {
    return new Promise((res, rej) => {
      const s = document.createElement('script');
      s.src = src; s.onload = res; s.onerror = rej;
      document.head.appendChild(s);
    });
  }
  // Module script yükler — importmap'i destekleyen type="module" olarak ekler
  function _loadModule(src) {
    return new Promise((res, rej) => {
      const s = document.createElement('script');
      s.type = 'module'; s.src = src; s.onload = res; s.onerror = rej;
      document.head.appendChild(s);
    });
  }
  async function _ensureModeAssets(key) {
    if (_loaded[key]) return;
    const v = '?v=' + ASSET_V;
    if (key === 'hud-ring') {
      await Promise.all([_loadCss('/ui/modes/hud-ring.css' + v), _loadCss('/ui/modes/characters.css' + v)]);
      await _loadJs('/ui/modes/hud-ring.js' + v);
    } else if (key === 'game') {
      await Promise.all([_loadCss('/ui/modes/game-mode.css' + v), _loadCss('/ui/modes/characters.css' + v)]);
      await _loadJs('/ui/modes/game-mode.js' + v);
    }
    _loaded[key] = true;
  }

  // ── ortak veri katmanı (sağ paneller bunu kullanır) ──
  window.ModeData = {
    auth() {
      try { return (typeof _authToken !== 'undefined' && _authToken) ? { Authorization: 'Bearer ' + _authToken } : {}; }
      catch (e) { return {}; }
    },
    async getJSON(url) {
      const r = await fetch(url, { headers: this.auth() });
      if (!r.ok) throw new Error('HTTP ' + r.status);
      return r.json();
    },
    async postJSON(url, body) {
      const r = await fetch(url, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json', ...this.auth() },
        body: JSON.stringify(body),
      });
      if (!r.ok) throw new Error('HTTP ' + r.status);
      return r.json();
    },
    async delJSON(url) {
      const r = await fetch(url, { method: 'DELETE', headers: this.auth() });
      if (!r.ok) throw new Error('HTTP ' + r.status);
      return r.json();
    },
    notes()     { return this.getJSON('/api/memory?limit=20'); },
    reminders() { return this.getJSON('/api/reminders'); },
    cancelReminder(id) { return this.delJSON('/api/reminders/' + encodeURIComponent(id)); },
    todoLists() { return this.getJSON('/api/todo/lists'); },
    todoTasks(id) { return this.getJSON('/api/todo/lists/' + id + '/tasks'); },
    health()    { return this.getJSON('/health'); },
    system()    { return this.getJSON('/api/system'); },
  };

  // ── karakter yönetimi ──
  function _applyCharacter() {
    document.documentElement.setAttribute('data-character', _character);
    const meta = CHARACTERS.find(c => c.key === _character) || CHARACTERS[0];
    // Üst çubuktaki ad (● Yuki hazır) karakteri izler
    const lbl = document.querySelector('#header .hud-unit-label');
    if (lbl) lbl.textContent = meta.label.charAt(0) + meta.label.slice(1).toLowerCase();
    // Klasik sohbetteki avatar HUD'u da karakteri izlesin (sabit "UNIT // YUKI" idi)
    const unit = document.getElementById('av-unit-id');
    if (unit) unit.textContent = 'UNIT // ' + meta.label;
    // 2026-08-08: sohbet portresi de karakteri izlesin.
    // Eskiden yalnız GameMode + HudRing haberdar ediliyordu; sohbetteki görsel
    // sabit Yuki videosuydu → NOVA seçilince persona+ses değişiyor, GÖRÜNTÜ değişmiyordu.
    if (window.applyCharacterImage) window.applyCharacterImage(_character);
    // 2026-08-09: boş sohbet karşılaması da karakteri izlesin. `index.html`de
    // SABİT "Merhaba, ben Yuki." yazıyordu ve hiçbir JS ona dokunmuyordu →
    // NOVA seçen kullanıcı solda Nova'yı, sağda Yuki'nin karşılamasını görüyordu.
    // (Aynı sınıf: kilit listesi sabitti · TAM BOY MODES'ta yoktu · ocr_image'a
    // yol yoktu — veri/kod VAR, yolun ucuna gidilmemiş.)
    const bosBaslik = document.querySelector('#chat-empty-state .empty-title');
    // 🔴 i18n: başlık `data-i18n="sohbet.merhaba-ben-yuki"` taşıyor ama
    // bu satır onu çalışma anında YAZIYOR → dil.js elemanı "artık benim değil"
    // sayıp geri çekiliyor ve EN'e geçince Türkçe "Merhaba, ben Yuki." donuyordu.
    // Sahibi burası; dil değişince de burası tazeler (aşağıdaki dinleyici).
    if (bosBaslik) {
      const ad = meta.label.charAt(0) + meta.label.slice(1).toLowerCase();
      bosBaslik.textContent = _t('sohbet.merhaba-ben', { ad });
    }
    _syncCharBar();
    if (window.GameMode && window.GameMode.onCharacter) window.GameMode.onCharacter(_character);
    if (window.HudRing && window.HudRing.onCharacter) window.HudRing.onCharacter(_character);
  }

  const _etiket = (k) => (CHARACTERS.find(c => c.key === k) || {}).label || k;

  window.setCharacter = function (key, opts) {
    opts = opts || {};
    if (!VALID_CHARS.includes(key)) return;
    if (!opts.fromWs && _charLocked(key)) return;
    const onceki = _character;
    _character = key;
    localStorage.setItem(LS_KARAKTER, key);
    _applyCharacter();
    // Backend'e bildir (persona+ses değişimi) — WS'den geldiyse geri gönderme
    if (!opts.fromWs) {
      window.ModeData.postJSON('/api/character', { name: key })
        .then((d) => {
          // Sunucu reddederse (geçersiz ad vb.) son söz onun.
          if (d && d.locked) _kilitliyeGeriDon(onceki, key);
        })
        .catch(() => {});
    }
  };

  function _kilitliyeGeriDon(onceki, reddedilen) {
    _character = VALID_CHARS.includes(onceki) ? onceki : 'yuki';
    localStorage.setItem(LS_KARAKTER, _character);
    _applyCharacter();
  }
  window.getCharacter = function () { return _character; };
  window.MODE_CHARACTERS = CHARACTERS;

  // ── mod uygulama ──
  function _updateButton() {
    const meta = MODES.find(m => m.key === _mode) || MODES[0];
    const btn = document.getElementById('mode-toggle');
    if (btn) {
      btn.textContent = meta.label;
      btn.title = _t('gorunum.sec-etiket', { mod: meta.label });
      btn.classList.toggle('active', _mode !== 'chat');
    }
    // Mobil FAB — mod etiketinin tek sahibi burası (core.js artık yazmıyor)
    const fab = document.getElementById('mode-toggle-fab');
    if (fab) {
      fab.textContent = meta.label;
      fab.title = _t('gorunum.sec-etiket', { mod: meta.label });
    }
  }

  window.setViewMode = async function (key) {
    if (!VALID.includes(key)) key = 'chat';   // konsoldan geçersiz anahtar → SOHBET (test_ozellik_ilani)

    document.body.classList.remove(...EXT_CLASSES);
    _halkaPaletiCoz();
    if (key === 'hud-ring') {
      try { await _ensureModeAssets('hud-ring'); } catch (e) { console.error('hud-ring yüklenemedi', e); return; }
      document.body.classList.add('hud-ring-mode');
      // 🔴 2026-08-31 — HALKA yüzeyi KOYU palete sabitlenir.
      // Ölçüldü (kontrast turu, 3 mod × 3 tema): HALKA + AÇIK tema = 41 ihlal,
      // diğer 8 hücre 0. Sebep: hud-ring.css'in panel zeminleri sabit koyu
      // (rgba(4,8,22,…) — 131 sabit renk, HUD'un tasarımının kendisi) ama metin
      // `--ink-*` token'larından geliyor ve açık temada KOYUya dönüyordu →
      // koyu zemin üstünde koyu yazı. En kötüsü 1.21:1 (eşik 4.5) — arayüz
      // okunmaz hâle geliyordu ve kimse görmemişti çünkü kapı HALKA'ya
      // hiç girememişti (localStorage anahtarı, aynı turda kapandı).
      // Neden 131 rengi token'a çevirmek değil: HALKA bilerek koyu bir sci-fi
      // yüzeyi ("Great Sage HUD"); onu açığa çevirmek kusur düzeltmek değil
      // TASARIM DEĞİŞTİRMEK olurdu. Kusur, yüzeyin yarısının temayla dönüp
      // yarısının dönmemesiydi — tutarlılık koyu tarafta kuruluyor.
      // `tema.js` data-tema'yı <html>'e yazar, burası <body>; kullanıcının
      // tema seçimi SİLİNMEZ, yalnız bu mod boyunca gölgelenir ve moddan
      // çıkınca `_halkaPaletiCoz()` ile geri döner.
      if (window.HudRing) window.HudRing.activate();
      _halkaPaletiSabitle();
    } else if (window.HudRing) window.HudRing.deactivate();

    if (key === 'game') {
      try { await _ensureModeAssets('game'); } catch (e) { console.error('game-mode yüklenemedi', e); return; }
      document.body.classList.add('game-mode');
      if (window.GameMode) window.GameMode.activate();
    } else if (window.GameMode) window.GameMode.deactivate();

    _mode = key;
    localStorage.setItem(LS_MOD, key);
    _updateButton();
    document.dispatchEvent(new CustomEvent('viewmodechange', { detail: { mode: key } }));
  };
  window.getViewMode = function () { return _mode; };

  // ── görünüm seçici mini menü ──
  let _menu = null;
  function _buildMenu() {
    const m = document.createElement('div');
    m.id = 'view-mode-menu';
    MODES.forEach(mode => {
      const it = document.createElement('button');
      it.className = 'vmm-item';
      it.dataset.mode = mode.key;
      it.innerHTML = '<span class="vmm-icon">' + mode.icon + '</span>' +
        '<span class="vmm-text"><b>' + mode.label + '</b><small>' + mode.desc + '</small></span>';
      it.onclick = () => { _closeMenu(); window.setViewMode(mode.key); };
      m.appendChild(it);
    });
    // ── HALKA teması — tek satır, yalnız HALKA'dayken görünür (11-14, kişisel chat-modes.js deseni).
    // Eskiden HALKA'nın PANEL'inde "HALKA TEMASI" kartıydı; kişiseldeki gibi buraya taşındı.
    // Kaynak: hud-ring.js window.HalkaTema (liste/al/sec) — HALKA yüklenmeden menü kurulursa
    // satır _openMenu'da doldurulur.
    const tr = document.createElement('div');
    tr.className = 'vmm-tema';
    tr.setAttribute('role', 'group');
    tr.setAttribute('aria-label', _t('hudring.tema.baslik'));
    tr.innerHTML = '<span class="vmm-tema-ad">' + _t('gorunum.tema-kisa') + '</span>';
    m.appendChild(tr);
    // ── Grafik kalitesi (modes/gfx.js) — aynı menünün ikinci bölümü ──
    // Sohbet sekmesi ölçümde ~%92 çekirdek yakıyordu; HAFİF kademesi %48 düşürüyor.
    if (window.Gfx) {
      const sep = document.createElement('div');
      sep.className = 'vmm-sep';
      sep.textContent = _t('gfx.menu-basligi');
      m.appendChild(sep);
      /* 🔴 Geri çağırmanın parametresi `t` — çeviri yardımcısıyla AYNI AD.
         `t(t.label)` yazılsaydı yardımcı gölgelenir ve "t is not a function"
         alınırdı. Bu depoda `t` adı Blok 1'de üç yerde gölgelenmişti; burada
         yardımcı bilerek `_t` diye anıldı, döngü değişkeni değiştirilmedi
         (o adı değiştirmek bu turun kapsamı dışındaki satırları da eller). */
      window.Gfx.TIERS.forEach(t => {
        const it = document.createElement('button');
        it.className = 'vmm-item';
        it.dataset.gfx = t.key;
        it.innerHTML = '<span class="vmm-icon">' + t.icon + '</span>' +
          '<span class="vmm-text"><b>' + _t(t.label) + '</b><small>' + _t(t.desc) + '</small></span>';
        it.onclick = () => { _closeMenu(); window.Gfx.set(t.key); };
        m.appendChild(it);
      });
    }
    _pencereBolumunuEkle(m);
    document.body.appendChild(m);
    return m;
  }

  /**
   * ── Pencere modu (js/tab-nav.js) — aynı menünün üçüncü bölümü ──
   *
   * Denetimler 2026-09-06'ya kadar `.kabuk-ust-serit` üst şeridindeydi: şerit tüm
   * genişlikte 44px yer kaplıyor, sağ ucunda tek bir düğme taşıyordu. geliştirici o boş
   * bandı ÜÇ kez bildirdi; ilk iki düzeltme yalnız düğme `[hidden]` iken devreye
   * giriyordu, Electron'da düğme görünür olduğu için boşluk her seferinde geri
   * geliyordu. Denetim menüye alınınca şeridin var olma sebebi kalmadı.
   *
   * 🔑 Markup yeniden YAZILMADI, TAŞINDI: `tab-nav.js` bu düğümleri id/öznitelikle
   * arıyor ve dinleyicilerini açılışta bağlıyor. `appendChild` düğümü taşır,
   * dinleyiciler düğümle birlikte gider — mod değiştirme, klavye gezinmesi, köşe
   * seçici ve "bu pencere yöneticisi desteklemiyor" notu olduğu gibi çalışır.
   *
   * ⚠️ Ayrı fonksiyon ve idempotent: menü TEMBEL kurulur (ilk açılışta) ama
   * `tab-nav.js` destek işaretini kendi bağlanmasında basar. Menü önce kurulsaydı
   * bölüm eksik kalır ve bir daha hiç eklenmezdi — bu yüzden `_openMenu` da çağırır.
   */
  function _pencereBolumunuEkle(m) {
    if (!m || m.querySelector('.vmm-pencere')) return;
    if (!document.documentElement.hasAttribute('data-pencere-destek')) return;
    const kaynak = document.getElementById('pencere-mod-kaynak');
    if (!kaynak || !kaynak.firstElementChild) return;

    const sep = document.createElement('div');
    sep.className = 'vmm-sep';
    sep.textContent = _t('gorunum.pencere-basligi');
    m.appendChild(sep);

    const kutu = document.createElement('div');
    kutu.className = 'vmm-pencere';
    while (kaynak.firstChild) kutu.appendChild(kaynak.firstChild);
    m.appendChild(kutu);
  }
  function _temaSatiriniDoldur(m) {
    const tr = m && m.querySelector('.vmm-tema');
    if (!tr) return;
    const HT = window.HalkaTema;
    tr.hidden = !(HT && _mode === 'hud-ring');
    if (!HT) return;
    if (!tr.querySelector('.vmm-seg')) {
      HT.liste().forEach(t => {
        const b = document.createElement('button');
        b.type = 'button';
        b.className = 'vmm-seg';
        b.dataset.halkatema = t.key;
        b.textContent = t.ad;
        b.onclick = () => { _closeMenu(); HT.sec(t.key); };
        tr.appendChild(b);
      });
    }
    const cur = HT.al();
    tr.querySelectorAll('.vmm-seg').forEach(b => {
      const on = b.dataset.halkatema === cur;
      b.classList.toggle('active', on);
      b.setAttribute('aria-pressed', on ? 'true' : 'false');
    });
  }
  function _closeMenu() {
    if (_menu) _menu.classList.remove('open');
    document.removeEventListener('click', _outside, true);
    document.removeEventListener('keydown', _esc, true);
  }
  function _outside(e) {
    if (_menu && !_menu.contains(e.target) &&
        e.target.id !== 'mode-toggle' && e.target.id !== 'mode-toggle-fab') _closeMenu();
  }
  function _esc(e) { if (e.key === 'Escape') _closeMenu(); }

  function _openMenu() {
    if (!_menu) _menu = _buildMenu();
    _pencereBolumunuEkle(_menu);   // menü tab-nav'dan ÖNCE kurulduysa burada eklenir
    _menu.querySelectorAll('.vmm-item[data-mode]').forEach(it =>
      it.classList.toggle('active', it.dataset.mode === _mode));
    _temaSatiriniDoldur(_menu);
    if (window.Gfx) {
      const g = window.Gfx.get();
      _menu.querySelectorAll('.vmm-item[data-gfx]').forEach(it =>
        it.classList.toggle('active', it.dataset.gfx === g));
    }
    // Görünür butona göre konumla: mobilde #mode-toggle display:none olduğundan
    // getBoundingClientRect() sıfır döner ve menü ekran dışına kaçar → FAB'ı kullan.
    let btn = document.getElementById('mode-toggle');
    if (!btn || btn.offsetParent === null) {
      btn = document.getElementById('mode-toggle-fab') || btn;
    }
    _menu.classList.add('open'); // önce göster ki gerçek boyutunu ölçebilelim
    if (btn) {
      const r = btn.getBoundingClientRect();
      const mh = _menu.offsetHeight || 220;
      const mw = _menu.offsetWidth || 240;
      // Dikey: aşağı sığmıyorsa butonun ÜSTÜNE aç
      const top = (r.bottom + 6 + mh <= window.innerHeight)
        ? r.bottom + 6
        : Math.max(8, r.top - mh - 6);
      // Yatay: butonun sağ kenarına hizala, ama ekran dışına taşma
      let right = Math.max(8, window.innerWidth - r.right);
      right = Math.max(8, Math.min(right, window.innerWidth - mw - 8));
      _menu.style.top = top + 'px';
      _menu.style.right = right + 'px';
    }
    setTimeout(() => {
      document.addEventListener('click', _outside, true);
      document.addEventListener('keydown', _esc, true);
    }, 0);
  }

  // Eski toggleViewMode'u menü açıcıyla değiştir (onclick="toggleViewMode()" buraya düşer)
  window.toggleViewMode = _openMenu;

  // ── menü stili ──
  /* Menü stilleri 2026-08-27'de tema token'larına çevrildi. Öncesi: sabit
     cyan çerçeve + `clip-path` köşe kesmesi = PRODUCT.md'nin kendi
     anti-referansı ("sıkışık askeri HUD, kalın cyan border"). Ayrıca hiçbir
     rengi tema anahtarını görmüyordu → açık temada koyu bir kutu kalıyordu.
     🔴 İki bölüm (mod + grafik) AYNI `.active` sınıfını kullanıyor; ikisi de
     seçili olduğu için ekranda iki öğe birden vurgulu görünüyordu ve hangisi
     ne, anlaşılmıyordu (geliştiricinin 3. ekran görüntüsü). Bölüm başlıkları
     netleştirildi, seçili durum renk+zemin+onay imiyle birlikte anlatılıyor. */
  const st = document.createElement('style');
  st.textContent = `
    #view-mode-menu {
      position: fixed; z-index: var(--z-acilir, 500); min-width: 248px;
      background: var(--yuzey-3);
      border: 1px solid var(--kenar);
      border-radius: var(--r-3, 14px);
      box-shadow: var(--golge-3, 0 12px 32px rgba(0,0,0,.45));
      display: none; flex-direction: column; padding: var(--b-3, 6px);
      overflow: hidden;
    }
    #view-mode-menu.open { display: flex; }
    .vmm-item {
      display: flex; align-items: center; gap: 10px; text-align: left;
      background: transparent; border: 0; cursor: pointer;
      padding: 9px 10px; color: var(--ink-1); font: inherit;
      border-radius: var(--r-2, 10px);
      transition: background var(--sure-2, .15s) var(--egri, ease-out);
    }
    .vmm-item:hover { background: var(--yuzey-2); }
    .vmm-item:focus-visible {
      outline: var(--odak-kalinlik, 2px) solid var(--mor-ink);
      outline-offset: var(--odak-offset, 2px);
    }
    /* Seçili: zemin + metin ağırlığı + sağda onay imi. Renk TEK kanal değil. */
    .vmm-item.active { background: var(--mor-zemin); }
    .vmm-tema { display: flex; align-items: center; gap: 6px; padding: 6px 10px 8px; }
    .vmm-tema[hidden] { display: none; }
    .vmm-tema-ad { font: 600 10px/1 var(--font-mono); letter-spacing: 0.14em; color: var(--ink-3); margin-right: 2px; }
    .vmm-seg { flex: 1; min-height: 32px; padding: 0 10px; border: 1px solid var(--kenar-guclu); border-radius: var(--r-2, 8px);
      background: transparent; color: var(--ink-2); font: 600 11px/1 var(--font-mono); letter-spacing: 0.08em; cursor: pointer; }
    .vmm-seg:hover { background: var(--yuzey-3); color: var(--ink-1); }
    .vmm-seg.active { border-color: color-mix(in oklab, var(--altin-ink) 55%, transparent); background: color-mix(in oklab, var(--altin-ink) 12%, transparent); color: var(--altin-ink); }
    .vmm-seg:focus-visible { outline: 2px solid var(--altin-ink); outline-offset: 2px; }
    .vmm-item.active .vmm-text b { color: var(--mor-ink); font-weight: 600; }
    .vmm-item.active::after {
      content: ""; margin-inline-start: auto; inline-size: 13px; block-size: 8px;
      border-inline-start: 2px solid var(--mor-ink);
      border-block-end: 2px solid var(--mor-ink);
      transform: rotate(-45deg) translateY(-2px); flex: 0 0 auto;
    }
    .vmm-icon { font-size: 17px; width: 22px; text-align: center; color: var(--ink-3); }
    .vmm-item.active .vmm-icon { color: var(--mor-ink); }
    .vmm-text { display: flex; flex-direction: column; gap: 1px; min-width: 0; }
    .vmm-text b { font-size: 12px; letter-spacing: .06em; font-weight: 500; }
    .vmm-text small { font-size: var(--yazi-12, 12px); color: var(--ink-2); }
    /* Bölüm başlığı 9px + --ink-3'tü, okunmuyordu ( M8). */
    .vmm-sep {
      margin: 8px 4px 4px; padding: 8px 6px 0;
      border-top: 1px solid var(--kenar);
      font-size: var(--yazi-12, 12px); font-weight: 600; letter-spacing: .12em;
      color: var(--ink-2);
    }
    /* PENCERE bölümü — üst şeritten taşınan denetimlerin kabı (2026-09-06).
       Denetimlerin KENDİ stilleri css/kabuk.css'te duruyor ve popover'a bağlı
       değildi; burada yalnız menü içindeki yerleşimi veriliyor. */
    .vmm-pencere {
      display: grid; gap: 8px;
      padding: 2px 4px 4px;
      -webkit-app-region: no-drag;
    }
    /* Menüde satır tam genişlik olmalı: şeritte 280px'lik popover'da duruyordu,
       burada kap ~240px ve select varsayılan genişliğiyle taşardı.
       ⚠️ Bu blok bir template literal — içine ters tırnak YAZMA, string'i kapatır. */
    .vmm-pencere .pencere-kose-alani { display: grid; gap: 4px; }
    .vmm-pencere .pencere-kose-alani label {
      font-size: 10px; letter-spacing: .06em; color: var(--ink-3);
    }
    .vmm-pencere .pencere-kose-alani select { inline-size: 100%; }
    .vmm-pencere .pencere-kisit-notu { margin: 0; font-size: 10px; line-height: 1.45; }
    /* Masaüstü kuralı kutusu — konumlandıramadığımızda kullanıcının KENDİ
       yapabilmesi için. Yapamadığımız şeyi söyleyip çıkışsız bırakmıyoruz. */
    .vmm-pencere .pencere-kural-kutusu {
      display: grid; gap: 5px;
      padding: 7px; border-radius: var(--r-2, 10px);
      background: var(--yuzey-2); border: 1px solid var(--kenar);
    }
    .vmm-pencere .pencere-kural-baslik {
      font-size: 9px; letter-spacing: .12em; color: var(--ink-3);
    }
    /* Kural satırları uzun ve KIRILMAMALI (yanlış kopyalanır) → yatay kaydır. */
    .vmm-pencere .pencere-kural-metin {
      margin: 0; padding: 6px; border-radius: 6px;
      background: var(--yuzey-1); color: var(--ink-2);
      font-family: var(--yazi-mono, monospace); font-size: 9.5px; line-height: 1.5;
      white-space: pre; overflow-x: auto;
    }
    .vmm-pencere .pencere-kural-kopyala {
      justify-self: start; padding: 4px 9px; font-size: 10px;
      border-radius: var(--r-2, 8px); cursor: pointer;
    }
  `;
  document.head.appendChild(st);

  // ── karakter şeridi (klasik sohbet) ────────────────────────────────────
  // 2026-08-08: sohbette karakter değiştirmenin yolu yoktu — HALKA modunun kendi
  // seçicisi vardı, KLASİK'in yoktu. Şerit #avatar-hud'un ilk satırı (09-25:
  // üstte yüzü kapatıyordu, alta alındı);
  // hud-ring modunda pane display:none olduğu için kendiliğinden kayboluyor.
  // Kilit kuralı HALKA ile aynı: kilitli karaktere tık → toast, geçiş yok.
  let _charBar = null;
  function _buildCharBar() {
    if (!COK_KARAKTER) return;   // tek karakter → seçecek bir şey yok, şerit çizilmez
    const pane = document.getElementById('avatar-pane');
    if (!pane || document.getElementById('char-bar')) return;

    const bar = document.createElement('div');
    bar.id = 'char-bar';
    bar.setAttribute('role', 'group');
    bar.setAttribute('aria-label', _t('karakter.sec'));

    CHARACTERS.forEach(c => {
      const b = document.createElement('button');
      b.type = 'button';
      b.className = 'char-btn';
      // NOT: 'data-char' DEĞİL — intro-sequences.js `_evolUpdateBadges` `[data-char]`
      // olan her elemana seviye rozeti ekliyor. Rozet metni bozuyor ve dokunmayı
      // engelliyordu (kişiselde ölçüldü).
      b.dataset.charkey = c.key;
      b.textContent = c.label[0];               // Y · N · K · S · R
      _kilitGorunumu(b, c);
      b.addEventListener('click', (e) => {
        e.stopPropagation();
        if (_charLocked(c.key)) return;
        window.setCharacter(c.key);
      });
      bar.appendChild(b);
    });

    const hud = document.getElementById('avatar-hud');
    if (hud) hud.prepend(bar); else pane.appendChild(bar);
    _charBar = bar;
    _syncCharBar();
  }

  // Kilit görünümü tek yerde — hem ilk çizimde hem yetki cevabı gelince aynı kod
  // koşar. İki ayrı yerde yazılsaydı biri güncellenip öbürü unutulurdu.
  function _kilitGorunumu(b, c) {
    const lk = _charLocked(c.key);
    b.classList.toggle('locked', lk);
    b.title = c.label + ' — ' + c.title;
    b.setAttribute('aria-label', c.label + ', ' + c.title);
  }

  function _syncCharBar() {
    if (!_charBar) return;
    _charBar.querySelectorAll('.char-btn').forEach(b => {
      const on = b.dataset.charkey === _character;
      b.classList.toggle('active', on);
      b.setAttribute('aria-pressed', on ? 'true' : 'false');
      const c = CHARACTERS.find(x => x.key === b.dataset.charkey);
      if (c) _kilitGorunumu(b, c);
    });
  }

  // ── yetki senkronu (kilitlerin GERÇEK kaynağı) ─────────────────────────
  // Sunucu `characters` alanında açık karakterleri döndürür (açık kaynakta beşi de).
  async function _kilitleriSenkronla() {
    let izinli = null;
    try {
      const d = await window.ModeData.getJSON('/api/yetki');
      if (d && Array.isArray(d.characters)) {
        izinli = d.characters.filter(k => VALID_CHARS.includes(k));
      }
    } catch (e) { izinli = null; }
    if (!izinli || !izinli.length) return;
    if (izinli.indexOf('yuki') === -1) izinli.push('yuki');  // Yuki her zaman açık
    UNLOCKED_CHARS.length = 0;                                // yerinde güncelle (yukarıdaki not)
    izinli.forEach(k => UNLOCKED_CHARS.push(k));
    _syncCharBar();
    // HALKA sahnesi bu cevaptan ÖNCE kurulmuş olabilir; çizilmiş kilit rozetlerini
    // tazelemesi için haber ver (tıklama davranışı zaten aynı diziyi okuyor).
    document.dispatchEvent(new CustomEvent('yuki:karakter-kilitleri'));
    if (_charLocked(_character)) window.setCharacter('yuki');
  }
  window.MODE_KILIT_SENKRON = _kilitleriSenkronla;

  // ── dil değişimi ──
  // Yalnız ETİKETLER yeniden yazılır: mod/karakter durumu, localStorage ve
  // sunucu çağrısı (POST /api/character, entitlements) TETİKLENMEZ.
  window.addEventListener('yuki-dil-degisti', () => {
    const dene = (ad, f) => { try { f(); } catch (e) { console.warn('[chat-modes] dil tazeleme (' + ad + '):', e); } };
    dene('dugme', _updateButton);
    dene('serit', () => {
      if (_charBar) _charBar.setAttribute('aria-label', _t('karakter.sec'));
      _syncCharBar();
    });
    dene('karsilama', () => {
      const meta = CHARACTERS.find(c => c.key === _character) || CHARACTERS[0];
      const bosBaslik = document.querySelector('#chat-empty-state .empty-title');
      if (bosBaslik) {
        const ad = meta.label.charAt(0) + meta.label.slice(1).toLowerCase();
        bosBaslik.textContent = _t('sohbet.merhaba-ben', { ad });
      }
    });
    // Menü tembel kurulur; metinleri kurulumda gömülü → at, sonraki açılış yeni
    // dille kurar. PENCERE bölümünün düğümleri tab-nav'a ait: atmadan önce
    // kaynağına geri taşı ki dinleyicileriyle birlikte yaşamaya devam etsin.
    dene('menu', () => {
      if (!_menu) return;
      const kaynak = document.getElementById('pencere-mod-kaynak');
      const kutu = _menu.querySelector('.vmm-pencere');
      if (kaynak && kutu) while (kutu.firstChild) kaynak.appendChild(kutu.firstChild);
      const acikti = _menu.classList.contains('open');
      _closeMenu();
      _menu.remove();
      _menu = null;
      if (acikti) _openMenu();
    });
  });

  // ── init ──
  function _init() {
    _buildCharBar();
    _applyCharacter();
    _updateButton();
    _kilitleriSenkronla();   // açık karakterler `/api/yetki` → characters (bkz. UNLOCKED_CHARS)
    document.addEventListener('DOMContentLoaded', _updateButton);
    if (_mode === 'hud-ring' || _mode === 'game') window.setViewMode(_mode);
    // Aktif karakteri backend ile senkronla (backend açılışta yuki olabilir)
    if (_character !== 'yuki') {
      window.ModeData.postJSON('/api/character', { name: _character }).catch(() => {});
    }
  }
  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', _init);
  else _init();
})();
