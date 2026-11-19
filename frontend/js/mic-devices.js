/* ════════════════════════════════════════════════════════════════════
   mic-devices.js — Mikrofon cihaz seçici (2026-08-02)

   Sorun: ses yakalayan her yer `getUserMedia({audio:true})` diyordu, yani
   HER ZAMAN sistemin varsayılan mikrofonu. Kulaklık/webcam/harici mikrofon
   takılıyken hangisinin dinlendiğini seçmenin yolu yoktu.

   Çözüm: cihazlar `enumerateDevices()` ile otomatik listelenir, seçim
   localStorage'da tutulur, ses açan tüm yollar `MicDevices.constraints()`
   üzerinden geçer.

   Kullanım (mikrofon butonunda):
     tek tık        → kayıt (mevcut davranış, DEĞİŞMEDİ)
     sağ tık        → cihaz menüsü
     uzun basış     → cihaz menüsü (dokunmatik)

   Not: cihaz ETİKETLERİ ancak bir kez mikrofon izni verildikten sonra
   dolu gelir; izin yokken tarayıcı boş string döndürür. Menü açılırken
   izin yoksa bir kez istenir (kullanıcı jesti içinde olduğu için sorun yok).
   ════════════════════════════════════════════════════════════════════ */
(function () {
  'use strict';

  var KEY = 'yukiMicId_v1';
  var _devices = [];
  var _menu = null;
  var _listeners = [];

  /* i18n: bu dosyanın KENDİ ön eki — core.js `_t`, map-engine `_mt`
     kullanıyor; IIFE içinde olsa da ad ayrı tutulur ki grep'te karışmasın. */
  function _mdt(anahtar, degerler) {
    return (window.YukiDil && window.YukiDil.t)
      ? window.YukiDil.t(anahtar, degerler) : String(anahtar);
  }

  function _read() {
    try { return localStorage.getItem(KEY) || ''; } catch (e) { return ''; }
  }
  function _write(id) {
    try { id ? localStorage.setItem(KEY, id) : localStorage.removeItem(KEY); } catch (e) {}
  }

  function _supported() {
    return !!(navigator.mediaDevices && navigator.mediaDevices.enumerateDevices);
  }

  async function refresh() {
    if (!_supported()) { _devices = []; return _devices; }
    try {
      var all = await navigator.mediaDevices.enumerateDevices();
      _devices = all.filter(function (d) { return d.kind === 'audioinput'; });
    } catch (e) {
      console.warn('[mic] cihaz listesi alınamadı:', e);
      _devices = [];
    }
    // Seçili cihaz çıkarılmışsa sessizce varsayılana dön — yoksa getUserMedia
    // `exact` kısıtıyla OverconstrainedError atar ve mikrofon hiç açılmaz.
    var sel = _read();
    if (sel && !_devices.some(function (d) { return d.deviceId === sel; })) {
      _write('');
      _notify();
    }
    return _devices;
  }

  function _notify() {
    _listeners.forEach(function (fn) { try { fn(_read()); } catch (e) {} });
  }

  /* Ses açan HER yol bunu kullanmalı. Seçim yoksa `true` döner = sistem
     varsayılanı, yani eski davranış birebir korunur. */
  function constraints(extra) {
    var id = _read();
    var audio = id ? { deviceId: { exact: id } } : true;
    if (extra && typeof extra === 'object') {
      audio = (audio === true) ? extra : Object.assign({}, extra, audio);
    }
    return audio;
  }

  function label(d, i) {
    if (d.label) return d.label;
    // İzin verilmeden etiket boş gelir — en azından ayırt edilebilir bir ad ver.
    return _mdt('mik.cihaz-no', { n: i + 1 });
  }

  async function _ensurePermission() {
    // Etiketler boşsa izin hiç verilmemiş demektir; bir kez isteyip hemen kapat.
    if (_devices.length && _devices.some(function (d) { return !!d.label; })) return;
    try {
      var s = await navigator.mediaDevices.getUserMedia({ audio: true });
      s.getTracks().forEach(function (t) { t.stop(); });
      await refresh();
    } catch (e) { /* reddedildiyse menü yine açılır, etiketsiz */ }
  }

  // ── Menü ──────────────────────────────────────────────────────────
  function _closeMenu() {
    if (_menu) { _menu.remove(); _menu = null; }
    document.removeEventListener('mousedown', _outside, true);
    document.removeEventListener('keydown', _esc, true);
  }
  function _outside(e) { if (_menu && !_menu.contains(e.target)) _closeMenu(); }
  function _esc(e) { if (e.key === 'Escape') _closeMenu(); }

  function _row(text, active, onClick) {
    var b = document.createElement('button');
    b.className = 'mic-menu-item' + (active ? ' active' : '');
    b.innerHTML = '<span class="mic-menu-tick">' + (active ? '✓' : '') + '</span>'
                + '<span class="mic-menu-label"></span>';
    b.querySelector('.mic-menu-label').textContent = text;
    b.onclick = onClick;
    return b;
  }

  async function openMenu(anchor) {
    if (_menu) { _closeMenu(); return; }
    if (!_supported()) return;

    await _ensurePermission();
    await refresh();

    var sel = _read();
    _menu = document.createElement('div');
    _menu.id = 'mic-menu';
    _menu.innerHTML = '<div class="mic-menu-hdr"></div>';
    _menu.firstChild.textContent = _mdt('mik.menu-baslik');

    _menu.appendChild(_row(_mdt('mik.varsayilan-sistem'), !sel, function () {
      _write(''); _notify(); _closeMenu();
    }));

    if (!_devices.length) {
      var empty = document.createElement('div');
      empty.className = 'mic-menu-empty';
      empty.textContent = _mdt('mik.cihaz-bulunamadi');
      _menu.appendChild(empty);
    }
    _devices.forEach(function (d, i) {
      _menu.appendChild(_row(label(d, i), d.deviceId === sel, function () {
        _write(d.deviceId); _notify(); _closeMenu();
      }));
    });

    var foot = document.createElement('div');
    foot.className = 'mic-menu-foot';
    foot.textContent = _mdt('mik.sonraki-kayitta-gecerli');
    _menu.appendChild(foot);

    document.body.appendChild(_menu);

    // position:fixed + viewport sıkıştırma — input alanı ekranın altında,
    // menü yukarı doğru açılır.
    var r = (anchor || document.getElementById('mic-btn')).getBoundingClientRect();
    var mr = _menu.getBoundingClientRect();
    var left = Math.max(8, Math.min(r.left, window.innerWidth - mr.width - 8));
    var top = r.top - mr.height - 8;
    if (top < 8) top = Math.min(r.bottom + 8, window.innerHeight - mr.height - 8);
    _menu.style.left = left + 'px';
    _menu.style.top = Math.max(8, top) + 'px';

    document.addEventListener('mousedown', _outside, true);
    document.addEventListener('keydown', _esc, true);
  }

  /* ⋯ menüsündeki "Mikrofon seç" (T3, 10-11): dar kabukta ▾ rozeti gizli, cihaz seçimi bu
     girdiden açılır. Menü mikrofon düğmesine göre konumlanır (rozetle aynı yer). */
  window.micCihazMenusuAc = function () {
    var btn = document.getElementById('mic-btn');
    if (btn) openMenu(btn);
  };

  // ── Mikrofon butonuna bağlan ──────────────────────────────────────
  function _bind() {
    var btn = document.getElementById('mic-btn');
    var box = document.getElementById('mic-container');
    if (!btn || btn.dataset.micDevBound) return;
    btn.dataset.micDevBound = '1';

    _etiketleriYaz();
    if (box && !box.querySelector('.mic-dev-hint')) {
      var hint = document.createElement('span');
      hint.className = 'mic-dev-hint';
      hint.textContent = '▾';
      hint.title = _mdt('mik.sec');
      // İpucu tıklanabilir: sağ tıkı keşfedemeyen kullanıcı buraya basar.
      hint.addEventListener('click', function (e) {
        e.preventDefault(); e.stopPropagation(); openMenu(btn);
      });
      box.appendChild(hint);
    }

    btn.addEventListener('contextmenu', function (e) {
      e.preventDefault(); openMenu(btn);
    });

    // Uzun basış (dokunmatik + fare) — tek tık kayıt yolunu bozmaz.
    var timer = null;
    function down() { timer = setTimeout(function () { timer = null; openMenu(btn); }, 550); }
    function up() { if (timer) { clearTimeout(timer); timer = null; } }
    btn.addEventListener('pointerdown', down);
    btn.addEventListener('pointerup', up);
    btn.addEventListener('pointerleave', up);
    btn.addEventListener('pointercancel', up);
  }

  /* `title`'ı bu dosya çalışma anında YAZIYOR → dil.js'in `data-i18n-title`
     çizicisi elemanı "artık benim değil" sayıp geri çekiliyor (`_sahibiBizMiyiz`).
     Yani bu metnin sahibi biziz; dil değişince tazelemek de bizim işimiz. */
  function _etiketleriYaz() {
    var btn = document.getElementById('mic-btn');
    if (btn && btn.dataset.micDevBound) btn.title = _mdt('mik.konus-sag-tik-sec');
    var hint = document.querySelector('#mic-container .mic-dev-hint');
    if (hint) hint.title = _mdt('mik.sec');
  }
  window.addEventListener('yuki-dil-degisti', function () {
    try {
      _etiketleriYaz();
      // Açık menü eski dilde kalmasın — kapat; sonraki açılış yeni dille kurulur.
      if (_menu) _closeMenu();
    } catch (e) { console.warn('[mic-devices] dil tazeleme:', e); }
  });

  if (_supported() && navigator.mediaDevices.addEventListener) {
    // Kulaklık takılıp çıkarıldığında liste kendini tazeler.
    navigator.mediaDevices.addEventListener('devicechange', function () {
      refresh();
      if (_menu) { _closeMenu(); }
    });
  }

  window.MicDevices = {
    refresh: refresh,
    list: function () { return _devices.slice(); },
    selected: _read,
    select: function (id) { _write(id || ''); _notify(); },
    constraints: constraints,
    openMenu: openMenu,
    onChange: function (fn) { if (typeof fn === 'function') _listeners.push(fn); },
  };

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', function () { _bind(); refresh(); });
  } else {
    _bind(); refresh();
  }
})();
