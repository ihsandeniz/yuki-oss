/* ════════════════════════════════════════════════════════════════════
   skill-card.js — Beceri/Olay Kazanım Kartı (global)

   API:
     window.SkillCard.show({ type, name, sub, banner, tag, hold })
       type: 'skill' | 'unlock' | 'task' | 'taught' | 'ipucu'   (renk + varsayılan metinler)
       name: büyük TR isim (decode animasyonuyla çözülür)   — zorunlu
       sub/banner/tag: opsiyonel override
       hold: görünür kalış ms (varsayılan 5000)

   Tetik (Faz 2b — backend Event Bus → WS):
     window.dispatchEvent(new CustomEvent('yuki:skill', { detail:{type,name,...} }))
     ya da doğrudan window.SkillCard.show({...})
   ════════════════════════════════════════════════════════════════════ */
(function () {
  'use strict';
  if (window.SkillCard) return;

  // CSS'i bir kez yükle
  (function loadCss() {
    if (document.querySelector('link[data-skillcard]')) return;
    const l = document.createElement('link');
    l.rel = 'stylesheet';
    l.href = '/ui/modes/skill-card.css?v=2';
    l.setAttribute('data-skillcard', '1');
    document.head.appendChild(l);
  })();

  /* i18n: bu dosyanın KENDİ ön eki (`_sct`). Kart klasik script'in
     IIFE'si içinde; core.js'in `window._t`'sine yaslanmaz. */
  function _sct(anahtar, degerler) {
    return (window.YukiDil && window.YukiDil.t)
      ? window.YukiDil.t(anahtar, degerler) : String(anahtar);
  }
  /* Anahtar sözlükte yoksa `t()` anahtarın kendisini döndürür → yedeğe düş. */
  function _sctYa(anahtar, degerler, yedek) {
    if (!anahtar) return yedek;
    const m = _sct(anahtar, degerler);
    return m === anahtar ? yedek : m;
  }

  /* 🔑 Modül düzeyi sabitte METİN değil ANAHTAR tutulur — metin `show()`
     anında çözülür. Metin burada çözülseydi kart ilk yükleme dilinde donardı
     (Dalga 2'de 10 kez düşülen tuzak). */
  const PRESET = {
    skill:  { banner: 'beceri.skill.banner',  sub: 'beceri.skill.sub',  tag: 'beceri.skill.tag' },
    unlock: { banner: 'beceri.unlock.banner', sub: 'beceri.unlock.sub', tag: 'beceri.unlock.tag' },
    task:   { banner: 'beceri.task.banner',   sub: 'beceri.task.sub',   tag: 'beceri.task.tag' },
    taught: { banner: 'beceri.taught.banner', sub: 'beceri.taught.sub', tag: 'beceri.taught.tag' },
    ipucu:  { banner: 'beceri.ipucu.banner',  sub: 'beceri.ipucu.sub',  tag: 'beceri.ipucu.tag' },
    mode:   { banner: 'beceri.mode.banner',   sub: 'beceri.mode.sub',   tag: 'beceri.mode.tag' },
  };
  const HOLD_MS = 5000;
  const DEC_CHARS = 'ABCÇDEFGĞHIİJKLMNOÖPRSŞTUÜVYZ0123456789#%◆▲';

  let _el = null, _hideT = 0, _rmT = 0, _decRAF = 0;

  function _build() {
    if (_el) return _el;
    const d = document.createElement('div');
    d.id = 'yk-skillcard';
    d.setAttribute('data-type', 'skill');
    d.innerHTML =
      '<div class="ysc-shock"></div>' +
      '<div class="ysc-diamond">' +
        '<div class="ysc-halo"></div><div class="ysc-sweep"></div><div class="ysc-flash"></div>' +
        '<div class="ysc-acq" id="ysc-banner"></div>' +
        '<div class="ysc-frame"></div><div class="ysc-frame inner"></div>' +
        '<div class="ysc-content">' +
          '<div class="ysc-type" id="ysc-type"></div>' +
          '<div class="ysc-name" id="ysc-name">—</div>' +
          '<div class="ysc-tag" id="ysc-tag">—</div>' +
        '</div>' +
      '</div>' +
      '<div class="ysc-hint"></div>';
    document.body.appendChild(d);
    d.addEventListener('click', hide);
    _el = d;
    return d;
  }

  function _decode(node, final, dur) {
    const t0 = performance.now(), N = final.length;
    cancelAnimationFrame(_decRAF);
    (function step(t) {
      const p = Math.min(1, (t - t0) / dur), rev = Math.floor(p * N);
      let s = '';
      for (let i = 0; i < N; i++) s += final[i] === ' ' ? ' ' : (i < rev ? final[i] : DEC_CHARS[(Math.random() * DEC_CHARS.length) | 0]);
      node.textContent = s;
      if (p < 1) _decRAF = requestAnimationFrame(step); else node.textContent = final;
    })(t0);
  }

  function hide() {
    if (!_el) return;
    _el.classList.add('closing');
    clearTimeout(_rmT);
    _rmT = setTimeout(() => _el.classList.remove('show', 'closing'), 400);
  }

  /* Büyük harf dile göre: `'beceri'.toUpperCase()` → 'BECERI' (noktasız I) olur. */
  function _buyuk(m) {
    const yer = (window.YukiDil && window.YukiDil.yerel) ? window.YukiDil.yerel() : 'tr-TR';
    try { return m.toLocaleUpperCase(yer); } catch (e) { return m.toUpperCase(); }
  }

  let _son = null;   // dil değişince açık kartı yeniden yazmak için

  /* Backend sözleşmesi (skill_events.py): `name_key`/`tag_key` + `tag_vars`
     gelirse metni arayüz dilinde BİZ kurarız; `name`/`tag` düz metni yalnız
     yedektir (anahtarı olmayan hafıza içeriği, eski backend). */
  function _metinler(opts) {
    const type = PRESET[opts.type] ? opts.type : 'skill';
    const p = PRESET[type];
    return {
      type: type,
      banner: opts.banner || _sct(p.banner),
      sub:    opts.sub    || _sct(p.sub),
      tag:    _sctYa(opts.tag_key, opts.tag_vars, opts.tag || _sct(p.tag)),
      name:   _sctYa(opts.name_key, opts.name_vars, (opts.name || opts.ad || '—').toString()),
    };
  }

  function _etiketleriYaz(el, m) {
    el.querySelector('#ysc-banner').textContent = m.banner;
    el.querySelector('#ysc-type').textContent   = m.sub;
    el.querySelector('#ysc-tag').textContent    = m.tag;
    el.querySelector('.ysc-hint').textContent   = _sct('beceri.dokun-kapat');
  }

  function show(opts) {
    opts = opts || {};
    _son = opts;
    const m = _metinler(opts);
    const type = m.type;
    const name = m.name;
    const el = _build();
    el.setAttribute('data-type', type);
    _etiketleriYaz(el, m);
    // reflow → giriş animasyonlarını yeniden tetikle
    el.classList.remove('show', 'closing');
    void el.offsetWidth;
    el.classList.add('show');
    _decode(el.querySelector('#ysc-name'), _buyuk(name), 950);
    clearTimeout(_hideT);
    _hideT = setTimeout(hide, opts.hold || HOLD_MS);
  }

  /* Açık kartı yeni dile çevir — animasyonu yeniden tetiklemez, süreyi uzatmaz. */
  window.addEventListener('yuki-dil-degisti', function () {
    try {
      if (!_el || !_son || !_el.classList.contains('show')) return;
      const m = _metinler(_son);
      _etiketleriYaz(_el, m);
      cancelAnimationFrame(_decRAF);
      _el.querySelector('#ysc-name').textContent = _buyuk(m.name);
    } catch (e) { console.warn('[skill-card] dil tazeleme:', e); }
  });

  window.SkillCard = { show, hide, PRESET };
  // Esnek tetik: herhangi bir yerden CustomEvent ile çağrılabilir
  window.addEventListener('yuki:skill', function (e) { show(e && e.detail || {}); });
})();
