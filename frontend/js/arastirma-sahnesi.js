/* ══════════════════════════════════════════════════════════════════
   ARAŞTIRMA SAHNESİ — Yuki Atölye, `sahne` türü görevin ön yüzü.
   Yükleme: gorev-serit.js Atölye açıkken bu dosyayı ve css/arastirma-sahnesi.css'i
   tembel ekler (index.html'e ayrı etiket gerekmez).

     1) İLERLEME KARTI (#sahne-kart): koşan sahne görevinin aşaması, KAYNAK / BLOK
        sayaçları, geçen süre, maliyet. Veri yalnız `gorev` olayının `sahne` sayaçları
        (window 'yuki:gorev'); istek metni olayda yok — kart görev adını gösterir.
     2) SAHNE (#sahne-katman): görev `bitti`/`yarim` + `sahne.hazir` → GET
        /api/gorev/sahne/<ad>; bloklar türüne göre (metin · sayı + kıvılcım · liste ·
        zaman · kıyas · görsel) sırayla dizilir. KAPAT / Esc kapatır.
     3) GEÇMİŞ: diskteki sahneler (GET /api/gorev/sahne) — katmandaki GEÇMİŞ menüsünden
        ya da boşta köşedeki ◈ düğmesinden yeniden açılır.
   Görsel yalnız https, referrer gönderilmez; kaynaklar yeni pencerede, `noopener`.
   Hareketi azalt tercihinde dizilme animasyonu yok. confirm()/alert() yok.
   ══════════════════════════════════════════════════════════════════ */
(function () {
  'use strict';
  if (window.ArastirmaSahnesi) return;           // iki kez yüklenirse ikinci sessiz

  // Metinler sözlükten (`sahne.*`, diller/tr.js · en.js); sözlük yoksa Türkçe yedek.
  const YEDEK = {
    'sahne.asama-hazirlik': 'HAZIRLANIYOR', 'sahne.asama-arama': 'KAYNAK TARANIYOR',
    'sahne.asama-yazim': 'RAPOR YAZILIYOR', 'sahne.asama-dizim': 'SAHNE DİZİLİYOR',
    'sahne.asama-bitti': 'HAZIR', 'sahne.asama-durdu': 'DURDU', 'sahne.asama-hata': 'HATA',
    'sahne.asama-yarim': 'EKSİK', 'sahne.kart-baslik': 'ARAŞTIRMA', 'sahne.kaynak': 'KAYNAK',
    'sahne.blok': 'BLOK', 'sahne.sure': 'SÜRE', 'sahne.maliyet': 'MALİYET', 'sahne.ucretsiz': 'ücretsiz',
    'sahne.etiket': 'ARAŞTIRMA SAHNESİ', 'sahne.gecmis': 'GEÇMİŞ', 'sahne.kapat': 'KAPAT',
    'sahne.kaynaksiz': 'kaynaksız', 'sahne.ozet': '{blok} blok · {kaynak} kaynak',
    'sahne.ornek-motor': ' · örnek motor (ağsız, ücretsiz)', 'sahne.kayit-yok': 'Kayıtlı sahne yok',
    'sahne.gecmis-satir': '{ad} · {blok} blok', 'sahne.son': 'Son araştırma sahnesi: {ad}',
  };
  function _t(k, v) {
    let m = null;
    try { if (window.YukiDil) m = window.YukiDil.t(k, v); } catch (_) { m = null; }
    if (m && m !== k) return m;
    return String(YEDEK[k] || k).replace(/\{(\w+)\}/g, (_, a) => (v && v[a] != null ? v[a] : ''));
  }
  function _asamaAd(a) { return YEDEK['sahne.asama-' + a] ? _t('sahne.asama-' + a) : ''; }
  const ASAMA_SIRA = ['hazirlik', 'arama', 'yazim', 'dizim', 'bitti'];
  const ACILAN = new Set();                 // bu sekmede kendiliğinden açılmış gid'ler
  let kart = null, katman = null, dugme = null;
  let kartGid = null, kartGizleZ = null, saatZ = null, baslangic = 0;
  let acikGid = null, sonListe = [], oncekiOdak = null;

  function _token() {
    try { return sessionStorage.getItem('aliceToken') || localStorage.getItem('aliceToken') || ''; }
    catch (_) { return ''; }
  }
  async function _get(yol) {
    const t = _token();
    const r = await fetch(yol, t ? { headers: { Authorization: `Bearer ${t}` } } : {});
    if (!r.ok) throw new Error(`HTTP ${r.status}`);
    return r.json();
  }
  function _el(tag, cls, metin) {
    const e = document.createElement(tag);
    if (cls) e.className = cls;
    if (metin != null) e.textContent = metin;
    return e;
  }
  function _azHareket() {
    try { return window.matchMedia('(prefers-reduced-motion: reduce)').matches; } catch (_) { return false; }
  }
  function _usd(v) {
    const n = Number(v) || 0;
    return n < 0.01 ? (n > 0 ? '<0,01 $' : '0 $') : n.toFixed(2).replace('.', ',') + ' $';
  }
  function _https(u) { try { return new URL(u).protocol === 'https:'; } catch (_) { return false; } }
  function _ad(gid) { return String(gid || '').split('/').pop(); }

  // ── 1) İlerleme kartı ─────────────────────────────────────────────
  function _kartKur() {
    if (kart) return kart;
    kart = _el('section', 'sh-kart');
    kart.id = 'sahne-kart';
    kart.hidden = true;
    kart.setAttribute('role', 'status');
    kart.setAttribute('aria-live', 'polite');
    kart.innerHTML =
      '<header class="sh-kart-ust"><span class="sh-isaret"></span>' +
      '<span class="sh-kart-baslik">' + _t('sahne.kart-baslik') + '</span><span class="sh-kart-ad"></span></header>' +
      '<p class="sh-asama"></p>' +
      '<ol class="sh-adimlar">' + ASAMA_SIRA.slice(0, 4).map(a => `<li data-a="${a}"></li>`).join('') + '</ol>' +
      '<dl class="sh-sayac">' +
      '<div><dt>' + _t('sahne.kaynak') + '</dt><dd data-k="kaynak">0</dd></div>' +
      '<div><dt>' + _t('sahne.blok') + '</dt><dd data-k="blok">0</dd></div>' +
      '<div><dt>' + _t('sahne.sure') + '</dt><dd data-k="sure">0:00</dd></div>' +
      '<div><dt>' + _t('sahne.maliyet') + '</dt><dd data-k="usd">0 $</dd></div></dl>';
    document.body.appendChild(kart);
    return kart;
  }
  function _saat() {
    if (!kart || kart.hidden) return;
    const s = Math.max(0, Math.round((Date.now() - baslangic) / 1000));
    kart.querySelector('[data-k="sure"]').textContent = `${Math.floor(s / 60)}:${String(s % 60).padStart(2, '0')}`;
  }
  function _kartGuncelle(g) {
    const sh = g.sahne || {};
    _kartKur();
    if (kartGid !== g.id) { kartGid = g.id; baslangic = Date.now(); }
    clearTimeout(kartGizleZ);
    const asama = g.durum === 'kosuyor' ? (sh.asama || 'hazirlik') : (g.durum === 'bitti' ? 'bitti' : g.durum);
    kart.dataset.asama = asama;
    kart.querySelector('.sh-kart-ad').textContent = g.ad || _ad(g.id);
    kart.querySelector('.sh-asama').textContent = _asamaAd(asama) || String(asama || '').toUpperCase();
    const sira = ASAMA_SIRA.indexOf(asama);
    kart.querySelectorAll('.sh-adimlar li').forEach((li, i) => {
      li.classList.toggle('gecti', sira > i || asama === 'bitti');
      li.classList.toggle('simdi', sira === i);
    });
    kart.querySelector('[data-k="kaynak"]').textContent = sh.kaynak || 0;
    kart.querySelector('[data-k="blok"]').textContent = sh.blok || 0;
    kart.querySelector('[data-k="usd"]').textContent = sh.motor === 'sahte' ? _t('sahne.ucretsiz') : _usd(sh.maliyet_usd);
    kart.hidden = false;
    if (dugme) dugme.hidden = true;
    if (!saatZ) saatZ = setInterval(_saat, 1000);
    _saat();
    if (g.durum !== 'kosuyor') {
      clearInterval(saatZ); saatZ = null;
      kartGizleZ = setTimeout(() => { kart.hidden = true; _dugmeTazele(); }, g.durum === 'bitti' ? 2500 : 8000);
    }
  }

  // ── 2) Sahne katmanı ──────────────────────────────────────────────
  function _katmanKur() {
    if (katman) return katman;
    katman = _el('section', 'sh-katman');
    katman.id = 'sahne-katman';
    katman.hidden = true;
    katman.setAttribute('role', 'dialog');
    katman.setAttribute('aria-modal', 'true');
    katman.setAttribute('aria-labelledby', 'sahne-baslik');
    katman.innerHTML =
      '<div class="sh-cerceve">' +
      '<header class="sh-ust"><div class="sh-ust-sol"><span class="sh-etiket">' + _t('sahne.etiket') + '</span>' +
      '<h2 id="sahne-baslik" class="sh-baslik"></h2><p class="sh-ozet"></p></div>' +
      '<div class="sh-ust-sag"><button type="button" class="sh-dugme sh-gecmis-d" aria-haspopup="true" aria-expanded="false">' + _t('sahne.gecmis') + '</button>' +
      '<button type="button" class="sh-dugme sh-kapat">' + _t('sahne.kapat') + '</button>' +
      '<ul class="sh-gecmis" hidden></ul></div></header>' +
      '<div class="sh-izgara"></div>' +
      '<footer class="sh-alt"></footer></div>';
    document.body.appendChild(katman);
    katman.querySelector('.sh-kapat').addEventListener('click', kapat);
    katman.querySelector('.sh-gecmis-d').addEventListener('click', _gecmisAcKapa);
    katman.addEventListener('click', (e) => { if (e.target === katman) kapat(); });
    return katman;
  }

  function _kivilcim(seri) {
    const n = seri.length;
    if (n < 3) return null;
    const en = Math.min(...seri), ust = Math.max(...seri), aralik = (ust - en) || 1;
    const G = 120, Y = 32;
    const noktalar = seri.map((v, i) => `${(i / (n - 1) * G).toFixed(1)},${(Y - 3 - (v - en) / aralik * (Y - 6)).toFixed(1)}`);
    const ns = 'http://www.w3.org/2000/svg';
    const svg = document.createElementNS(ns, 'svg');
    svg.setAttribute('viewBox', `0 0 ${G} ${Y}`);
    svg.setAttribute('class', 'sh-kivilcim');
    svg.setAttribute('aria-hidden', 'true');
    const p = document.createElementNS(ns, 'polyline');
    p.setAttribute('points', noktalar.join(' '));
    svg.appendChild(p);
    return svg;
  }

  function _blok(b) {
    const el = _el('article', 'sh-blok');
    el.dataset.tur = b.tur || 'metin';
    if (b.one_cikan) el.classList.add('one-cikan');
    if (b.tur === 'sayi' && b.sayi) {
      const s = _el('div', 'sh-sayi');
      s.appendChild(_el('span', 'sh-sayi-deger', b.sayi));
      if (b.sayi_etiket) s.appendChild(_el('span', 'sh-sayi-etiket', b.sayi_etiket));
      el.appendChild(s);
      if (Array.isArray(b.seri)) { const k = _kivilcim(b.seri.map(Number).filter(Number.isFinite)); if (k) el.appendChild(k); }
    }
    el.appendChild(_el('h3', 'sh-blok-baslik', b.baslik || ''));
    if (b.metin) el.appendChild(_el('p', 'sh-blok-metin', b.metin));
    if (b.tur === 'liste' && Array.isArray(b.maddeler)) {
      const ul = _el('ul', 'sh-maddeler');
      b.maddeler.forEach(m => ul.appendChild(_el('li', '', String(m))));
      el.appendChild(ul);
    } else if (b.tur === 'zaman' && Array.isArray(b.olaylar)) {
      const ol = _el('ol', 'sh-zaman');
      b.olaylar.forEach(o => {
        const li = _el('li');
        li.appendChild(_el('time', '', o.tarih));
        li.appendChild(_el('span', '', o.metin));
        ol.appendChild(li);
      });
      el.appendChild(ol);
    } else if (b.tur === 'kiyas' && Array.isArray(b.satirlar)) {
      const dl = _el('dl', 'sh-kiyas');
      b.satirlar.forEach(r => {
        const d = _el('div');
        d.appendChild(_el('dt', '', r.ad));
        d.appendChild(_el('dd', '', r.deger));
        dl.appendChild(d);
      });
      el.appendChild(dl);
    } else if (b.tur === 'gorsel' && _https(b.gorsel)) {
      const img = _el('img', 'sh-gorsel');
      img.src = b.gorsel;
      img.alt = b.baslik || '';
      img.loading = 'lazy';
      img.referrerPolicy = 'no-referrer';
      img.addEventListener('error', () => img.remove());
      el.insertBefore(img, el.firstChild);
    }
    if (b.kaynak && _https(b.kaynak.url)) {
      const a = _el('a', 'sh-kaynak', b.kaynak.alan || b.kaynak.ad || 'kaynak');
      a.href = b.kaynak.url;
      a.target = '_blank';
      a.rel = 'noopener noreferrer';
      a.title = b.kaynak.ad || b.kaynak.url;
      el.appendChild(a);
    } else {
      el.appendChild(_el('span', 'sh-kaynak yok', _t('sahne.kaynaksiz')));
    }
    return el;
  }

  async function ac(gid) {
    const ad = _ad(gid);
    if (!ad) return false;
    let s;
    try { s = await _get(`/api/gorev/sahne/${encodeURIComponent(ad)}`); }
    catch (e) { console.warn('[sahne] açılamadı:', e.message); return false; }
    _katmanKur();
    acikGid = `sahne/${ad}`;
    katman.querySelector('.sh-baslik').textContent = s.baslik || s.konu || ad;
    katman.querySelector('.sh-ozet').textContent = s.ozet || '';
    const iz = katman.querySelector('.sh-izgara');
    iz.replaceChildren();
    const az = _azHareket();
    (s.bloklar || []).forEach((b, i) => {
      const el = _blok(b);
      if (!az) el.style.animationDelay = `${Math.min(i, 11) * 70}ms`;
      iz.appendChild(el);
    });
    katman.classList.toggle('az-hareket', az);
    const m = s.meta || {};
    const kaynakSay = (s.kaynaklar || []).length;
    katman.querySelector('.sh-alt').textContent =
      _t('sahne.ozet', { blok: (s.bloklar || []).length, kaynak: kaynakSay }) +
      (m.motor === 'sahte' ? _t('sahne.ornek-motor') : (m.maliyet_usd != null ? ` · ${_usd(m.maliyet_usd)}` : ''));
    katman.querySelector('.sh-gecmis').hidden = true;
    oncekiOdak = document.activeElement;
    katman.hidden = false;
    document.body.classList.add('sahne-acik');
    try { katman.querySelector('.sh-kapat').focus({ preventScroll: true }); } catch (_) {}
    if (dugme) dugme.hidden = true;
    return true;
  }

  function kapat() {
    if (!katman || katman.hidden) return;
    katman.hidden = true;
    acikGid = null;
    document.body.classList.remove('sahne-acik');
    _dugmeTazele();
    try { if (oncekiOdak && oncekiOdak.focus) oncekiOdak.focus({ preventScroll: true }); } catch (_) {}
  }

  // ── 3) Geçmiş ─────────────────────────────────────────────────────
  async function _gecmisAcKapa(e) {
    e.stopPropagation();
    const ul = katman.querySelector('.sh-gecmis');
    const d = katman.querySelector('.sh-gecmis-d');
    if (!ul.hidden) { ul.hidden = true; d.setAttribute('aria-expanded', 'false'); return; }
    await _listeTazele();
    ul.replaceChildren();
    if (!sonListe.length) ul.appendChild(_el('li', 'bos', _t('sahne.kayit-yok')));
    sonListe.slice(0, 12).forEach(s => {
      const li = _el('li');
      const b = _el('button', '', s.baslik || _ad(s.id));
      b.type = 'button';
      if (s.id === acikGid) b.setAttribute('aria-current', 'true');
      b.appendChild(_el('small', '', `${_t('sahne.gecmis-satir', { ad: _ad(s.id), blok: s.blok })}${s.tarih ? ' · ' + String(s.tarih).slice(0, 16) : ''}`));
      b.addEventListener('click', () => { ul.hidden = true; d.setAttribute('aria-expanded', 'false'); ac(s.id); });
      li.appendChild(b);
      ul.appendChild(li);
    });
    ul.hidden = false;
    d.setAttribute('aria-expanded', 'true');
  }

  async function _listeTazele() {
    try { sonListe = (await _get('/api/gorev/sahne')).sahneler || []; } catch (_) { sonListe = []; }
    _dugmeTazele();
  }

  function _dugmeTazele() {
    const kartAcik = kart && !kart.hidden;
    if (!sonListe.length || kartAcik || (katman && !katman.hidden)) { if (dugme) dugme.hidden = true; return; }
    if (!dugme) {
      dugme = _el('button', 'sh-ac-dugme', '◈');
      dugme.type = 'button';
      dugme.id = 'sahne-ac';
      dugme.addEventListener('click', () => { if (sonListe[0]) ac(sonListe[0].id); });
      document.body.appendChild(dugme);
    }
    dugme.title = _t('sahne.son', { ad: sonListe[0].baslik || _ad(sonListe[0].id) });
    dugme.setAttribute('aria-label', dugme.title);
    dugme.hidden = false;
  }

  // ── olaylar ───────────────────────────────────────────────────────
  function _gorev(g) {
    if (!g || g.tur !== 'sahne') return;
    if (g.durum === 'kosuyor' || kartGid === g.id) _kartGuncelle(g);
    const hazir = (g.durum === 'bitti' || g.durum === 'yarim') && g.sahne && g.sahne.hazir;
    if (hazir && !ACILAN.has(g.id)) {
      ACILAN.add(g.id);
      _listeTazele();
      ac(g.id);
    }
  }

  window.addEventListener('yuki:gorev', (e) => _gorev(e.detail));
  document.addEventListener('keydown', (e) => { if (e.key === 'Escape' && katman && !katman.hidden) kapat(); });

  async function _acilis() {
    try {
      const v = await _get('/api/gorev');
      (v.gorevler || []).forEach(g => {
        if (g.tur !== 'sahne') return;
        if (g.durum === 'kosuyor') _kartGuncelle(g);
        else ACILAN.add(g.id);          // açılışta eski sahneler kendiliğinden açılmaz
      });
    } catch (_) {}
    _listeTazele();
  }
  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', _acilis);
  else _acilis();

  window.ArastirmaSahnesi = { ac, kapat, _gorev, durum: () => ({ acikGid, kartGid, liste: sonListe.length }) };
})();
