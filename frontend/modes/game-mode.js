/* ════════════════════════════════════════════════════════════════════
   game-mode.js — Mod 02: "UNIT DOSSIER" Oyun Görünümü (v2 — 2026-07-09)

   Merkez vitrin: seamless 2-video crossfade (idle loop) + 7 one-shot
   animasyon. Crossfade motoru v1'den AYNEN korunur (test edilmiş):
   vid-A oynar → %82'de vid-B başlatılır → 0.4s opacity geçiş → sonsuz.

   v2 yenilikleri:
     · Katmanlı sahne markup'ı (bigname / halo / floor / vertag)
     · SVG skill ikonları (emoji yerine hairline çizgi ikonlar)
     · Sağ modüller = widget: collapse + dikey sürükle-sırala +
       localStorage (gmModulesV1) — HALKA widget deseni
     · Sayaç rozetleri (.gm-count) + sahte LV rozetleri kaldırıldı

   window.GameMode.playAnimation(name)      — dış tetikleyici (behavior tag)
   window.GameMode.handleBehaviorTag(raw)   — "[BEHAVIOR:{wave}]" parse + tetikle
   ════════════════════════════════════════════════════════════════════ */
(function () {
  'use strict';

  /* i18n: bu dosyanın KENDİ ön eki (`_gmt`). Moda git-mode IIFE'si içinde;
     core.js'in `window._t`'sine yaslanmaz. */
  function _gmt(anahtar, degerler) {
    return (window.YukiDil && window.YukiDil.t)
      ? window.YukiDil.t(anahtar, degerler) : String(anahtar);
  }
  /* `[data-gmt]` taşıyan her öğenin metnini, `[data-gmt-aria]`nın aria-label'ını
     sözlükten yazar. Çizimde VE dil değişince aynı yol → iki kopya yok. */
  function _gmtCiz(kok) {
    if (!kok) return;
    kok.querySelectorAll('[data-gmt]').forEach(el => { el.textContent = _gmt(el.dataset.gmt); });
    kok.querySelectorAll('[data-gmt-aria]').forEach(el => { el.setAttribute('aria-label', _gmt(el.dataset.gmtAria)); });
  }

  const CHAR_PNG  = k => '/ui/assets/characters/' + k + '_fullbody.png';
  const CHAR_IMG  = k => '/ui/assets/characters/' + k + '_fullbody.jpg';
  const ANIM_VID  = (k, n) => '/ui/assets/characters/animations/' + k + '_' + n + '.mp4';

  const FADE_MS  = 400;   // opacity crossfade süresi (ms)
  const CROSS_AT = 0.82;  // video süresinin bu oranında crossfade başlar

  // ── SVG ikon seti (stroke: currentColor, hairline) ──
  const _svg = inner =>
    '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.6" ' +
    'stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">' + inner + '</svg>';

  const ICO = {
    wave:      _svg('<path d="M3 13.5a4 4 0 0 1 6 0 4 4 0 0 0 6 0 4 4 0 0 1 6 0"/>'),
    nod:       _svg('<path d="M5 13l4 4L19 7"/>'),
    shake:     _svg('<path d="M6 6l12 12M18 6L6 18"/>'),
    bow:       _svg('<path d="M4 8c4 7.5 12 7.5 16 0"/><path d="M7 18h10"/>'),
    think:     _svg('<path d="M9.4 9a2.6 2.6 0 1 1 3.9 2.2c-.9.6-1.3 1.2-1.3 2.3"/><circle cx="12" cy="17.6" r=".9" fill="currentColor" stroke="none"/>'),
    shy:       _svg('<path d="M4.5 12c1.6 2.2 3.9 2.2 5.5 0M14 12c1.6 2.2 3.9 2.2 5.5 0"/>'),
    surprised: _svg('<path d="M12 5v8.5"/><circle cx="12" cy="17.8" r=".9" fill="currentColor" stroke="none"/>'),
    todos:     _svg('<rect x="4" y="4" width="16" height="16"/><path d="M8.5 12l2.5 2.5 5-5.5"/>'),
    notes:     _svg('<path d="M5 5.5h14M5 12h10M5 18.5h7"/>'),
    reminders: _svg('<path d="M6.5 15.5v-5a5.5 5.5 0 0 1 11 0v5l1.5 2.5H5z"/><path d="M10.5 20.5h3"/>'),
  };

  const MODULES = [
    { key: 'todos',     label: 'gorunum.modul.todos.label' },
    { key: 'notes',     label: 'gorunum.modul.notes.label' },
    { key: 'reminders', label: 'gorunum.modul.reminders.label' },
  ];

  let _root = null, _timer = null;
  let _char = 'yuki';
  let _vidA = null, _vidB = null, _img = null;
  let _active = null, _standby = null;
  let _oneShot = false;
  let _crossing = false;
  let _crossTimer = null;

  // ── Widget durumu (sıra + kapalılık) — HALKA deseni ────────
  const WST_KEY = 'gmModulesV1';
  function _loadWst() {
    try { return JSON.parse(localStorage.getItem(WST_KEY)) || {}; }
    catch (e) { return {}; }
  }
  function _saveWst() {
    if (!_root) return;
    const right = _root.querySelector('#gm-right');
    const st = { order: [], closed: {} };
    right.querySelectorAll('.gm-box').forEach(b => {
      st.order.push(b.dataset.box);
      st.closed[b.dataset.box] = b.classList.contains('closed');
    });
    try { localStorage.setItem(WST_KEY, JSON.stringify(st)); } catch (e) { /* dolu */ }
  }

  // ── Statik PNG göster (anlık görsel geri bildirim + fallback) ──
  function _showPng(key) {
    if (!_img) return;
    _img.style.opacity = '0';
    _img.style.display = 'none';
    _img.onload = () => { _img.style.display = 'block'; _img.style.opacity = '1'; };
    _img.onerror = () => {
      if (_img.src.endsWith('.png')) { _img.src = CHAR_IMG(key); }
      else { _img.style.display = 'none'; }
    };
    _img.src = CHAR_PNG(key);
  }

  function _hidePng() {
    // onload iptali şart: geç gelen onload opacity'yi tekrar 1 yapıyordu
    // (3D sahne cache'liyken VID→3D geçişinde PNG arkada kalıyordu)
    if (_img) { _img.onload = null; _img.style.opacity = '0'; }
  }

  // ── Video crossfade motoru (v1'den değişmedi) ──────────────
  function _clearCross() {
    if (_crossTimer) { clearTimeout(_crossTimer); _crossTimer = null; }
    _crossing = false;
    if (_vidA) _vidA.ontimeupdate = null;
    if (_vidB) _vidB.ontimeupdate = null;
  }

  function _fadeTo(vid, opacity, ms) {
    vid.style.transition = 'opacity ' + ms + 'ms ease';
    vid.style.opacity = String(opacity);
  }

  function _swap() {
    const tmp = _active; _active = _standby; _standby = tmp;
  }

  function _attachCross(vid) {
    vid.ontimeupdate = function () {
      if (_crossing || _oneShot || !vid.duration || vid.duration === Infinity) return;
      if (vid.currentTime / vid.duration < CROSS_AT) return;
      _crossing = true;
      vid.ontimeupdate = null;

      _standby.src = vid.src;
      _standby.currentTime = 0;
      _standby.play().catch(() => {});
      _fadeTo(_standby, 1, FADE_MS);
      _fadeTo(vid, 0, FADE_MS);

      _crossTimer = setTimeout(() => {
        _crossing = false;
        _swap();
        _attachCross(_active);
      }, FADE_MS + 60);
    };
  }

  function _startIdle() {
    if (!_vidA || !_vidB) return;
    _clearCross();
    _oneShot = false;
    const src = ANIM_VID(_char, 'idle');

    _active  = _vidA;
    _standby = _vidB;

    _vidA.src = src; _vidA.loop = false; _vidA.currentTime = 0;
    _vidB.src = src; _vidB.loop = false; _vidB.currentTime = 0;

    // Standby invisible immediately (no transition)
    _vidB.style.transition = 'none';
    _vidB.style.opacity = '0';

    _vidA.play().then(() => {
      _hidePng();
      _fadeTo(_vidA, 1, FADE_MS);
      _attachCross(_vidA);
    }).catch(() => {
      // Idle video yok — PNG göster
      _fadeTo(_vidA, 0, 0);
    });
  }

  function _playOneShot(name) {
    if (!_vidA || !_vidB) return;
    _clearCross();
    _oneShot = true;

    const animSrc = ANIM_VID(_char, name);
    const tmpVid  = (_standby === _vidB) ? _vidB : _vidA;

    tmpVid.src = animSrc;
    tmpVid.loop = false;
    tmpVid.currentTime = 0;

    tmpVid.play().then(() => {
      _fadeTo(tmpVid, 1, FADE_MS);
      _fadeTo(_active, 0, FADE_MS);
      _crossTimer = setTimeout(() => { _swap(); }, FADE_MS + 60);

      tmpVid.onended = () => {
        tmpVid.onended = null;
        // Idle'a geri dön
        const idleSrc = ANIM_VID(_char, 'idle');
        _standby.src = idleSrc;
        _standby.currentTime = 0;
        _standby.play().catch(() => {});
        _fadeTo(_standby, 1, FADE_MS);
        _fadeTo(_active, 0, FADE_MS);
        _crossTimer = setTimeout(() => {
          _oneShot = false;
          _swap();
          _attachCross(_active);
          _setBtn(null);
        }, FADE_MS + 60);
      };
    }).catch(() => {
      // Animasyon videosu yok — idle'a dön
      _oneShot = false;
      _startIdle();
      _setBtn(null);
    });
  }

  function _setBtn(name) {
    if (!_root) return;
    _root.querySelectorAll('.gm-anim-btn').forEach(b =>
      b.classList.toggle('active', b.dataset.anim === name));
  }

  // 2026-08-08: karakter animasyon videoları (`assets/characters/animations/`)
  // `_arsiv-medya/`ya arşivlendi → oynatılacak klip yok. Eski akış her tetiklemede
  // bir HEAD isteği atıp 404 alıp PNG'ye düşüyordu; artık doğrudan PNG.
  // Video motoru (_startIdle / _playOneShot / crossfade) yerinde bırakıldı —
  // klipler geri gelirse ANIM_VID'i tekrar bağlamak yeter.
  function _tryPlay(name) {
    _oneShot = false;
    _setBtn(null);
    _showPng(_char);
  }

  // ── 3D katman (FAZ 0) — masaüstü kapısı + Yuki3D köprüsü ──
  // Kapıyı geçemeyen cihaz (mobil/WebGL2 yok) three.js'i HİÇ indirmez.
  const V3D = '137';                 // yuki-3d.js / 3d-mode.css cache sürümü
  const T3D_KEY = 'gm3dV1';          // localStorage: '0' = kullanıcı 3D'yi kapattı
  const HAS_3D = { yuki: true };     // FAZ 2'de diğer karakterler eklenir
  let _3dActive = false, _y3dLoading = null, _can3DCache = null;

  function _can3D() {
    if (_can3DCache !== null) return _can3DCache;
    try {
      // Telefonu asıl eleyen pointer:fine + hover; genişlik eşiği düşük tutuldu
      // (Hyprland tiling'de yarım-ekran pencere ~960px — masaüstü sayılmalı)
      const ok = window.innerWidth >= 900 &&
        matchMedia('(pointer:fine)').matches &&
        matchMedia('(hover:hover)').matches &&
        !!document.createElement('canvas').getContext('webgl2');
      _can3DCache = ok;
    } catch (e) { _can3DCache = false; }
    return _can3DCache;
  }
  const _3dOn  = () => localStorage.getItem(T3D_KEY) !== '0';
  // 3B model depoda dağıtılmıyor (lisans: NOTICE). Kullanıcı kendi .vrm'ini bu yola
  // koyarsa 3B açılır; dosya yoksa 3D/2D seçici hiç görünmez, three.js de inmez.
  const VRM_URL = '/ui/assets/characters/yuki3d.vrm';
  let _vrmVar = null;                // null = henüz bakılmadı · true/false = HEAD sonucu
  function _vrmKontrol() {
    if (_vrmVar !== null) return Promise.resolve(_vrmVar);
    return fetch(VRM_URL, { method: 'HEAD', cache: 'no-store' })
      .then(r => { _vrmVar = r.ok; return _vrmVar; })
      .catch(() => { _vrmVar = false; return false; });
  }
  const _use3D = () => !!HAS_3D[_char] && _vrmVar === true && _can3D() && _3dOn();

  function _loadYuki3D() {
    if (window.Yuki3D) return Promise.resolve();
    if (_y3dLoading) return _y3dLoading;
    _y3dLoading = new Promise((res, rej) => {
      if (!document.querySelector('link[href*="3d-mode.css"]')) {
        const l = document.createElement('link');
        l.rel = 'stylesheet'; l.href = '/ui/modes/3d-mode.css?v=' + V3D;
        document.head.appendChild(l);
      }
      const s = document.createElement('script');
      s.src = '/ui/modes/yuki-3d.js?v=' + V3D;
      s.onload = res;
      s.onerror = () => { _y3dLoading = null; rej(new Error('yuki-3d.js failed to load'))   /* yalnız konsola gider */; };
      document.head.appendChild(s);
    });
    return _y3dLoading;
  }

  async function _enter3D() {
    const pane = _root && _root.querySelector('#gm-3d-pane');
    if (!pane) return false;
    try {
      await _loadYuki3D();
      _clearCross(); _oneShot = false;
      if (_vidA) { _vidA.pause(); _fadeTo(_vidA, 0, 200); }
      if (_vidB) { _vidB.pause(); _fadeTo(_vidB, 0, 200); }
      pane.style.display = 'block';           // activate'ten ÖNCE: _resize boyut bulsun
      const ok = await window.Yuki3D.activate();
      if (ok === false) throw new Error('Yuki3D.activate failed');
      _3dActive = true;
      _hidePng();
      return true;
    } catch (e) {
      console.error('gm 3D başlatılamadı, videoya dönülüyor:', e);
      if (pane) pane.style.display = 'none';
      _3dActive = false;
      return false;
    }
  }

  function _exit3D() {
    if (!_3dActive) { const p = _root && _root.querySelector('#gm-3d-pane'); if (p) p.style.display = 'none'; return; }
    _3dActive = false;
    if (window.Yuki3D) { try { window.Yuki3D.deactivate(); } catch (e) { /* yut */ } }
    const pane = _root && _root.querySelector('#gm-3d-pane');
    if (pane) pane.style.display = 'none';
  }

  function _updateToggle() {
    const seg = _root && _root.querySelector('#gm-mode-seg');
    if (!seg) return;
    const capable = !!HAS_3D[_char] && _vrmVar === true && _can3D();
    seg.style.display = capable ? '' : 'none';
    if (!capable) return;
    const on = _3dOn();
    seg.querySelectorAll('.gm-seg-btn').forEach(b =>
      b.classList.toggle('on', (b.dataset.vmode === '3d') === on));
  }

  // ── Modül sürükle-sırala + collapse (pointer events) ──────
  function _initModuleDrag(head, box, right) {
    head.addEventListener('pointerdown', e => {
      if (e.button !== 0) return;
      const startY = e.clientY;
      let moved = false;
      try { head.setPointerCapture(e.pointerId); } catch (err) { /* eski tarayıcı */ }

      const onMove = ev => {
        if (!moved && Math.abs(ev.clientY - startY) > 6) {
          moved = true;
          box.classList.add('gm-drag');
        }
        if (!moved) return;
        const sibs = Array.from(right.querySelectorAll('.gm-box')).filter(el => el !== box);
        const over = sibs.find(s => {
          const r = s.getBoundingClientRect();
          return ev.clientY > r.top && ev.clientY < r.bottom;
        });
        if (over) {
          const r = over.getBoundingClientRect();
          if (ev.clientY < r.top + r.height / 2) right.insertBefore(box, over);
          else right.insertBefore(box, over.nextSibling);
        }
      };
      const onUp = ev => {
        head.removeEventListener('pointermove', onMove);
        head.removeEventListener('pointerup', onUp);
        head.removeEventListener('pointercancel', onUp);
        try { head.releasePointerCapture(ev.pointerId); } catch (err) { /* yok */ }
        box.classList.remove('gm-drag');
        if (!moved) {
          // sürüklenmedi → tık = aç/kapa (yükseklik SADECE CSS'te — ledger dersi)
          box.classList.toggle('closed');
        }
        _saveWst();
      };
      head.addEventListener('pointermove', onMove);
      head.addEventListener('pointerup', onUp);
      head.addEventListener('pointercancel', onUp);
    });
  }

  // ── Karakter sahneleri (#gm-scene) — "kendi doğasına göre oda" ──
  // Saf DOM+CSS. 2026-11-14 (ürün kararı): tek karakter Yuki — öbür karakterlerin sahneleri
  // (rün, radar, tüy, telemetri terminali + ticker'ı) kaldırıldı. Tablo yapısı kalır:
  // yeni karakter = `SCENES`'e bir girdi (+ characters.css'te palet).

  // Çalışma süresi: TR "2s 5d" (saat/dakika) · EN "2h 5m" — durum kartı (#gm-st-up)
  function _sure(sn) {
    const m = Math.floor(sn / 60);
    return m >= 60
      ? _gmt('gorunum.oyun.sure-sa-dk', { sa: Math.floor(m / 60), dk: m % 60 })
      : _gmt('gorunum.oyun.sure-dk', { dk: m });
  }
  // n adet parçacık span'ı üret (içerik CSS ile şekillenir)
  const _spans = (n, cls, txts) => Array.from({ length: n }, (_, i) =>
    `<i class="${cls}" style="--i:${i}">${txts ? txts[i % txts.length] : ''}</i>`).join('');

  const SCENES = {
    yuki: () => _spans(11, 'gm-snow'),
  };

  function _buildScene(key) {
    if (!_root) return;
    const scene = _root.querySelector('#gm-scene');
    if (!scene) return;
    const make = SCENES[key];
    scene.innerHTML = make ? make() : '';
    scene.dataset.scene = key;
  }

  // ── DOM inşası ─────────────────────────────────────────────
  function _build() {
    const root = document.createElement('div');
    root.id = 'gm-root';

    const chars  = window.MODE_CHARACTERS || [{ key: 'yuki', label: 'YUKI', title: _gmt('gorunum.oyun.ana-cekirdek') }];
    const active = window.getCharacter ? window.getCharacter() : 'yuki';
    const meta   = chars.find(c => c.key === active) || chars[0];
    const idx    = Math.max(0, chars.findIndex(c => c.key === active));
    _char = active;

    const wst    = _loadWst();
    const order  = Array.isArray(wst.order) && wst.order.length
      ? MODULES.slice().sort((a, b) => wst.order.indexOf(a.key) - wst.order.indexOf(b.key))
      : MODULES;

    root.innerHTML = `
      <div id="gm-bigname" aria-hidden="true">${meta.label}</div>
      <div id="gm-halo" aria-hidden="true"></div>
      <div id="gm-floor" aria-hidden="true"></div>
      <div id="gm-scene" aria-hidden="true"></div>
      <video id="gm-vid-a" muted playsinline disablepictureinpicture style="opacity:0"></video>
      <video id="gm-vid-b" muted playsinline disablepictureinpicture style="opacity:0"></video>
      <img id="gm-character" alt="" style="display:none;opacity:0;transition:opacity 0.4s ease">
      <div id="gm-3d-pane" style="display:none"><canvas id="yuki-3d-canvas"></canvas></div>
      <div id="gm-vertag" aria-hidden="true">COMPANION OS // ALICE v0.6</div>

      <div id="gm-char-title">
        <small class="gm-serial"><i></i>FILE ${String(idx + 1).padStart(2, '0')} · <span data-gmt="gorunum.oyun.aktif"></span></small>
        <b>${meta.label}</b>
        <small class="gm-role">${(meta.title || '').toUpperCase()}</small>
        <span class="gm-title-rule"></span>
      </div>

      <div id="gm-status">
        <div class="gm-stat"><b id="gm-st-state">—</b><small data-gmt="gorunum.oyun.durum"></small></div>
        <div class="gm-stat"><b id="gm-st-mem">—</b><small data-gmt="gorunum.oyun.bellek"></small></div>
        <div class="gm-stat"><b id="gm-st-up">—</b><small>UPTIME</small></div>
      </div>

      <div id="gm-left">
        ${chars.map(c => `
          <button class="gm-char-btn ${c.key === active ? 'active' : ''}" data-char="${c.key}" title="${c.label} — ${c.title}">
            <img src="${CHAR_IMG(c.key)}" alt="" loading="lazy" onerror="this.remove()">
            <span>${c.label}</span>
          </button>`).join('')}
      </div>

      <div id="gm-stage-spacer" aria-hidden="true"></div>

      <div id="gm-anim-btns">
        <!-- 2026-08-08: ANIM_BTNS (wave/nod/shake/bow/think/...) çıkarıldı —
             tetikleyecek klip kalmadı, hepsi aynı durağan PNG'yi gösteriyordu.
             İlan edilen ama iş yapmayan düğme bırakma kuralı (gfx ULTRA dersi).
             3D/2D seçici duruyor: 3D = kullanıcının koyduğu yuki3d.vrm (depoda yok), 2D = fullbody PNG. -->
        <span id="gm-mode-seg" style="display:none">
          <button class="gm-anim-btn gm-seg-btn" data-vmode="3d" data-gmt-aria="gorunum.oyun.mod-3d">3D</button>
          <button class="gm-anim-btn gm-seg-btn" data-vmode="video" data-gmt-aria="gorunum.oyun.mod-2d">2D</button>
        </span>
      </div>

      <div id="gm-right">
        ${order.map(m => `
          <div class="gm-box ${wst.closed && wst.closed[m.key] ? 'closed' : ''}" data-box="${m.key}">
            <div class="gm-box-head">
              ${ICO[m.key]}
              <span class="gm-box-label" data-gmt="${m.label}"></span>
              <em class="gm-count">0</em>
              <em class="gm-fold">▾</em>
            </div>
            <div class="gm-box-body"><div class="gm-empty" data-gmt="gorunum.oyun.yukleniyor"></div></div>
          </div>`).join('')}
      </div>`;

    _gmtCiz(root);
    document.getElementById('chat-pane').appendChild(root);

    _vidA = root.querySelector('#gm-vid-a');
    _vidB = root.querySelector('#gm-vid-b');
    _img  = root.querySelector('#gm-character');
    _active  = _vidA;
    _standby = _vidB;

    root.querySelectorAll('.gm-char-btn').forEach(b => {
      b.onclick = () => window.setCharacter && window.setCharacter(b.dataset.char);
    });
    const right = root.querySelector('#gm-right');
    root.querySelectorAll('.gm-box').forEach(box => {
      _initModuleDrag(box.querySelector('.gm-box-head'), box, right);
    });
    root.querySelectorAll('.gm-anim-btn').forEach(b => {
      b.onclick = () => _tryPlay(b.dataset.anim);
    });
    // Segment handler'ları anim-loop'tan SONRA ata (onclick'i ezer)
    root.querySelectorAll('.gm-seg-btn').forEach(b => {
      b.onclick = () => {
        const want3d = b.dataset.vmode === '3d';
        if (want3d === _3dOn()) return; // zaten o moddayız
        try { localStorage.setItem(T3D_KEY, want3d ? '1' : '0'); } catch (e) { /* dolu */ }
        window.GameMode.onCharacter(_char);
      };
    });

    _root = root;
    return root;
  }

  // ── Veri yenileme ──────────────────────────────────────────
  const esc  = s => String(s == null ? '' : s).replace(/</g, '&lt;');
  const _itm = (t, sub, cls) =>
    '<div class="gm-item ' + (cls || '') + '">' + esc(t) +
    (sub ? '<small>' + esc(sub) + '</small>' : '') + '</div>';
  const _arr = (r, keys) => {
    if (Array.isArray(r)) return r;
    for (const k of keys) if (r && Array.isArray(r[k])) return r[k];
    return [];
  };
  function _fill(boxKey, html, count) {
    if (!_root) return;
    const box = _root.querySelector('.gm-box[data-box="' + boxKey + '"]');
    if (!box) return;
    const body = box.querySelector('.gm-box-body');
    if (body) body.innerHTML = html || '<div class="gm-empty">' + _gmt('gorunum.oyun.kayit-yok') + '</div>';
    const badge = box.querySelector('.gm-count');
    if (badge) badge.textContent = String(count != null ? count : 0);
  }

  async function _refresh() {
    if (!_root || !window.ModeData) return;
    try {
      const lists = _arr(await ModeData.todoLists(), ['items', 'lists']);
      let open = 0;
      const parts = await Promise.all(lists.slice(0, 3).map(async l => {
        try {
          const tasks = _arr(await ModeData.todoTasks(l.id), ['items', 'tasks']);
          return tasks.slice(0, 8).map(t => {
            const done = (t.completed || t.done || t.status === 'completed');
            if (!done) open++;
            return _itm(t.title || t.text || t.name || '—', l.name || l.title || '', done ? 'done' : '');
          }).join('');
        } catch (e) { return ''; }
      }));
      _fill('todos', parts.join(''), open);
    } catch (e) { _fill('todos', '<div class="gm-empty">' + _gmt('gorunum.oyun.veri-alinamadi') + '</div>', 0); }
    try {
      const items = _arr(await ModeData.notes(), ['items', 'memories', 'results']);
      _fill('notes', items.slice(0, 12).map(m =>
        _itm(m.content || m.text || m.memory || '—',
             m.created_at ? String(m.created_at).slice(0, 16).replace('T', ' ') : '')).join(''),
        Math.min(items.length, 12));
    } catch (e) { _fill('notes', '<div class="gm-empty">' + _gmt('gorunum.oyun.veri-alinamadi') + '</div>', 0); }
    try {
      const items = _arr(await ModeData.reminders(), ['items', 'reminders', 'jobs']);
      _fill('reminders', items.map(r =>
        _itm(r.message || r.text || r.name || _gmt('gorunum.oyun.hatirlatici'),
             r.when || r.next_run || r.run_at || '')).join(''), items.length);
    } catch (e) { _fill('reminders', '<div class="gm-empty">' + _gmt('gorunum.oyun.veri-alinamadi') + '</div>', 0); }
    try {
      const h  = await ModeData.health();
      const st = _root.querySelector('#gm-st-state');
      const mm = _root.querySelector('#gm-st-mem');
      const up = _root.querySelector('#gm-st-up');
      if (st) st.textContent = (h.state || '—').toUpperCase();
      if (mm) {
        const n = document.getElementById('mem-num');
        mm.textContent = n ? n.textContent : (h.memory ? 'ON' : 'OFF');
      }
      if (up && h.uptime_seconds != null) {
        up.textContent = _sure(h.uptime_seconds);
      }
    } catch (e) { /* health yoksa kartlar kalır */ }
  }

  // ── Dışa açık API (v1 ile birebir aynı yüzey) ─────────────
  window.GameMode = {
    init() { if (!_root) _build(); },

    activate() {
      this.init();
      const key = window.getCharacter ? window.getCharacter() : 'yuki';
      this.onCharacter(key);
      _refresh();
      if (_timer) clearInterval(_timer);
      _timer = setInterval(() => {
        if (document.body.classList.contains('game-mode')) _refresh();
      }, 60000);
    },

    deactivate() {
      if (_timer) { clearInterval(_timer); _timer = null; }
      _exit3D();
      // 3D modundan çıktıktan SONRA VRAM bırak
      if (window.Yuki3D && window.Yuki3D.dispose) {
        try { window.Yuki3D.dispose(); } catch (e) { /* yut */ }
      }
      _clearCross();
      if (_vidA) { _vidA.pause(); _vidA.src = ''; }
      if (_vidB) { _vidB.pause(); _vidB.src = ''; }
    },

    onCharacter(key) {
      if (!_root) return;
      _char = key;
      const chars = window.MODE_CHARACTERS || [];
      const meta  = chars.find(c => c.key === key) || { label: key.toUpperCase(), title: '' };
      const idx   = Math.max(0, chars.findIndex(c => c.key === key));

      const title = _root.querySelector('#gm-char-title');
      if (title) {
        title.querySelector('.gm-serial').innerHTML =
          '<i></i>FILE ' + String(idx + 1).padStart(2, '0') + ' · <span data-gmt="gorunum.oyun.aktif">'
          + _gmt('gorunum.oyun.aktif') + '</span>';
        title.querySelector('b').textContent = meta.label;
        title.querySelector('.gm-role').textContent = (meta.title || '').toUpperCase();
      }
      const big = _root.querySelector('#gm-bigname');
      if (big) big.textContent = meta.label;
      _buildScene(key);

      _root.querySelectorAll('.gm-char-btn').forEach(b =>
        b.classList.toggle('active', b.dataset.char === key));
      // Anında statik PNG göster; 3D uygunsa 3D'ye, değilse videoya geç
      _clearCross();
      if (_vidA) { _vidA.pause(); _fadeTo(_vidA, 0, 200); }
      if (_vidB) { _vidB.pause(); _fadeTo(_vidB, 0, 200); }
      _updateToggle();
      if (_vrmVar === null && HAS_3D[key] && _can3D()) {
        // Model varlığı ilk kez soruluyor: cevaba kadar 2D göster, varsa 3B'ye yeniden gir.
        _vrmKontrol().then(var_ => {
          if (!var_ || _char !== key) return;
          _updateToggle();
          if (_use3D()) _enter3D();
        });
      }
      if (_use3D()) {
        _showPng(key); // VRM yüklenene kadar anlık görsel
        _enter3D().then(ok => {
          if (!ok) {
            // 3D açılamadı → tercihi videoya çek ki segment gerçeği göstersin
            try { localStorage.setItem(T3D_KEY, '0'); } catch (e) { /* dolu */ }
            _updateToggle();
            _showPng(key); setTimeout(() => _tryPlay('idle'), 300);
          }
        });
      } else {
        _exit3D();
        _showPng(key);
        setTimeout(() => _tryPlay('idle'), 300);
      }
    },

    // Dışarıdan animasyon tetikle (behavior tag parser vb.)
    playAnimation(name) {
      if (!_root || !document.body.classList.contains('game-mode')) return;
      const safe = String(name).toLowerCase().replace(/[^a-z]/g, '');
      // 3D aktifken video yerine VRM jesti (FAZ 0 eşlemesi; FAZ 3'te genişler)
      if (_3dActive && window.Yuki3D) {
        const GEST_MAP = { wave: 'wave', nod: 'greet', shake: 'point', bow: 'bow', shy: 'curtsy', surprised: 'greet' };
        if (safe === 'think') {
          window.Yuki3D.setState('thinking');
          setTimeout(() => window.Yuki3D.setState('idle'), 3500);
        } else if (GEST_MAP[safe]) {
          window.Yuki3D.gesture(GEST_MAP[safe]);
        }
        _setBtn(safe);
        setTimeout(() => _setBtn(null), 2600);
        return;
      }
      _tryPlay(safe);
    },

    // "[BEHAVIOR:{wave}]" formatındaki ham etiketi parse et ve tetikle
    handleBehaviorTag(raw) {
      const m = String(raw).match(/\[BEHAVIOR:\{([^}]+)\}\]/i);
      if (m) this.playAnimation(m[1]);
    },
  };

  /* i18n: açık ekran dil değişince yeni dile geçer — statik etiketler
     `_gmtCiz`, karakter sahnesi yeniden kurulur, kutu içerikleri ve süre tazelenir. */
  function _onDilDegisti() {
    if (!_root) return;
    _gmtCiz(_root);
    // Karakter unvanı MODE_CHARACTERS'tan okuma anında dile göre gelir (chat-modes)
    const chars = window.MODE_CHARACTERS || [];
    const meta = chars.find(c => c.key === _char);
    const rol = _root.querySelector('#gm-char-title .gm-role');
    if (rol && meta) rol.textContent = (meta.title || '').toUpperCase();
    _root.querySelectorAll('.gm-char-btn').forEach(btn => {
      const c = chars.find(x => x.key === btn.dataset.char);
      if (c) btn.title = c.label + ' — ' + c.title;
    });
    if (_char) _buildScene(_char);
    if (document.body.classList.contains('game-mode')) _refresh();
  }
  window.addEventListener('yuki-dil-degisti', _onDilDegisti);

  window.GameMode.init();
})();
