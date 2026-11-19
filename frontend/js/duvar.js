/* ═══ DUVAR KÂĞIDI — sekme bazlı arka plan ═══════════════════════
 *
 * Ne yapar: her sekmeye ayrı duvar kâğıdı (resim · GIF · kısa video),
 * ya da tek duvar tüm sekmelere. Ayar backend'de tutulur.
 *
 * 🔴 Neden blob: `<img src>` ve `<video src>` `Authorization` başlığı
 * GÖNDEREMEZ. Bu depoda kripto sekmesinde öğrenilen ders. İki kaçış yolu
 * vardı — dosyaları token'sız statik sunmak ya da URL'e `?token=` koymak;
 * ikisi de reddedildi (cloudflared tüneli canlı; token URL'e konursa
 * geçmişe/loglara sızar). Yerine dosya `authFetch` ile blob olarak inip
 * `URL.createObjectURL` ile veriliyor.
 *
 * ⚠️ Blob'lar önbelleklenir (`_blobs`). Önbelleklenmezse her sekme
 * geçişinde aynı video yeniden indirilir ve `createObjectURL` sızdırır.
 */
(function () {
  'use strict';

  const API = '/api/duvar';
  const _blobs = new Map();      // duvar_id → objectURL
  let _ayar = null;
  let _liste = [];
  /* 🔑 Sekme listesi SUNUCUDAN gelir, burada sabit yazılmaz (2026-09-08).
     Kişiselde `SEKME_ADLARI` sözlüğünün ANAHTARLARI geziliyordu; o sözlük 8
     kişisel sekmeyi sayıyordu ve ürüne kopyalanınca panel HARİTA · SÜRÜCÜ ·
     KRİPTO · ODAK · AĞ satırlarını gösterecekti — üründe var olmayan sekmeler
     için duvar seçtirmek. Aynı liste hem `duvar_api.SEKMELER`de hem burada
     tutulsaydı er geç ayrışırlardı ("aynı soruya iki cevap", `surum.js` dersi).
     Artık `/liste` ne diyorsa o çizilir; aşağıdaki sözlük yalnız GÖRÜNEN AD. */
  let _sekmeler = [];
  let _aktifSekme = 'chat';

  function _f(url, opts) {
    return (typeof window.authFetch === 'function')
      ? window.authFetch(url, opts)
      : fetch(url, opts);
  }
  const _kok = () => (typeof BASE_URL !== 'undefined' ? BASE_URL : '');

  // ── Blob getir (önbellekli) ───────────────────────────────────
  async function _medyaUrl(id) {
    if (!id) return null;
    if (_blobs.has(id)) return _blobs.get(id);
    try {
      const r = await _f(_kok() + API + '/dosya/' + encodeURIComponent(id));
      if (!r.ok) throw new Error('HTTP ' + r.status);
      const url = URL.createObjectURL(await r.blob());
      _blobs.set(id, url);
      return url;
    } catch (e) {
      console.warn('[duvar] medya alınamadı:', id, e);
      return null;
    }
  }

  function _tip(id) {
    const k = _liste.find(x => x.id === id);
    return k ? k.tip : (/\.(mp4|m4v|webm|ogv)$/i.test(id || '') ? 'video' : 'resim');
  }

  // ── Katmanı kur ───────────────────────────────────────────────
  function _katman() {
    let k = document.getElementById('duvar-katman');
    if (k) return k;
    k = document.createElement('div');
    k.id = 'duvar-katman';
    k.setAttribute('aria-hidden', 'true');   // dekoratif — ekran okuyucu atlasın
    k.innerHTML =
      '<img id="duvar-medya-img" alt="">' +
      '<video id="duvar-medya-video" loop playsinline muted></video>' +
      '<div id="duvar-perde"></div>';
    // Katman DOM'un başına: pozisyonlu kardeşler onun üstünde çizilsin.
    document.body.insertBefore(k, document.body.firstChild);
    return k;
  }

  // ── iframe'li sekmeler ────────────────────────────────────────
  // 🔴 CSS buraya ULAŞMAZ: iframe ayrı bir belgedir, `body.duvar-acik #x`
  // kuralı onun içine işlemez. `drive` · `planner` · `odak` iframe'lerinin
  // İÇ belgesi opak arka plan taşıyor (ölçüldü: rgb(3,6,9) · rgb(5,6,8) ·
  // rgb(10,12,18)) ve duvar kâğıdını tamamen örtüyordu. `kripto`nunki zaten
  // şeffaf olduğu için orada sorun görünmemişti — tek sekmeye bakıp
  // "çalışıyor" demenin bedeli buydu.
  //
  // Hepsi AYNI ORIGIN olduğu için içeriden şeffaflaştırılabiliyor. Farklı
  // origin bir iframe gelirse `try/catch` sessizce geçer — duvar o sekmede
  // görünmez, ama hiçbir şey kırılmaz.
  function _iframeleriAyarla(acik) {
    document.querySelectorAll('iframe').forEach(f => {
      const uygula = () => {
        try {
          const d = f.contentDocument;
          if (!d || !d.body) return;
          for (const el of [d.documentElement, d.body]) {
            if (acik) {
              if (el.dataset.duvarEski === undefined) {
                el.dataset.duvarEski = el.style.getPropertyValue('background-color') || '';
              }
              // `!important`: iç sayfanın kendi kuralı da opak arka plan veriyor.
              el.style.setProperty('background-color', 'transparent', 'important');
            } else if (el.dataset.duvarEski !== undefined) {
              el.style.removeProperty('background-color');
              if (el.dataset.duvarEski) el.style.background = el.dataset.duvarEski;
              delete el.dataset.duvarEski;
            }
          }
        } catch (_) { /* cross-origin — dokunamayız, sorun değil */ }
      };
      uygula();
      // iframe geç yükleniyorsa (drive/planner ilk açılışta) tekrar dene.
      if (!f.dataset.duvarDinliyor) {
        f.dataset.duvarDinliyor = '1';
        f.addEventListener('load', () => setTimeout(uygula, 60));
      }
    });
  }

  // ── Sekme için duvar seç ──────────────────────────────────────
  function _sekmeIcinDuvar(sekme) {
    if (!_ayar || _ayar.mod === 'kapali') return null;
    if (_ayar.mod === 'tek') return _ayar.tek || null;
    return (_ayar.sekmeler || {})[sekme] || null;
  }

  // ── Uygula ────────────────────────────────────────────────────
  async function uygula(sekme) {
    if (sekme) _aktifSekme = sekme;
    if (!_ayar) return;

    const k = _katman();
    const img = document.getElementById('duvar-medya-img');
    const vid = document.getElementById('duvar-medya-video');
    const perde = document.getElementById('duvar-perde');
    const id = _sekmeIcinDuvar(_aktifSekme);

    if (!id) {
      document.body.classList.remove('duvar-acik');
      _iframeleriAyarla(false);
      img.classList.remove('acik'); vid.classList.remove('acik');
      // ⚠️ Videoyu DURDUR. Görünmez bir video arka planda oynamaya devam
      // eder ve boşuna CPU/GPU yakar — laptopta pil, masaüstünde fan.
      try { vid.pause(); } catch (_) {}
      return;
    }

    const url = await _medyaUrl(id);
    if (!url) {                       // dosya silinmiş olabilir
      document.body.classList.remove('duvar-acik');
      _iframeleriAyarla(false);
      return;
    }

    const filtre = _ayar.bulanik ? `blur(${_ayar.bulanik}px)` : 'none';
    img.style.filter = filtre;
    vid.style.filter = filtre;
    perde.style.opacity = String((_ayar.perde ?? 55) / 100);

    if (_tip(id) === 'video') {
      img.classList.remove('acik'); img.removeAttribute('src');
      if (vid.getAttribute('src') !== url) vid.setAttribute('src', url);
      vid.muted = _ayar.sessiz !== false;   // sessiz değilse tarayıcı oto-oynatmaz
      vid.classList.add('acik');
      // play() Promise döndürür ve kullanıcı etkileşimi yoksa reddedilebilir —
      // yakalamazsan konsola "Uncaught (in promise)" düşer.
      try { await vid.play(); } catch (_) {}
    } else {
      try { vid.pause(); } catch (_) {}
      vid.classList.remove('acik'); vid.removeAttribute('src');
      if (img.getAttribute('src') !== url) img.setAttribute('src', url);
      img.classList.add('acik');
    }
    document.body.classList.add('duvar-acik');
    _iframeleriAyarla(true);
  }

  // ── Veri ──────────────────────────────────────────────────────
  async function yenile() {
    try {
      const r = await _f(_kok() + API + '/liste');
      if (!r.ok) return false;
      const d = await r.json();
      _liste = d.duvarlar || [];
      _ayar = d.ayar || null;
      _sekmeler = Array.isArray(d.sekmeler) ? d.sekmeler : [];
      return true;
    } catch (e) {
      console.warn('[duvar] liste alınamadı:', e);
      return false;
    }
  }

  /* Kayıt SUNUCU CEVABINA bakar (09-27): eskiden `r.ok` okunmuyordu — 422 gelse de
     ekrandaki iyimser değer kalıyordu. Reddedilirse eski ayar geri gelir, sebep yazılır. */
  async function ayarKaydet(yeni) {
    const eski = _ayar;
    _ayar = Object.assign({}, _ayar, yeni || {});
    try {
      const r = await _f(_kok() + API + '/ayar', {
        method: 'PUT',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(_ayar),
      });
      const d = await r.json().catch(() => ({}));
      if (!r.ok) throw new Error(_detay(d, r));
      if (d && d.ayar) _ayar = d.ayar;   // sunucu elediyse gerçeği o söyler
      _durumYaz('');
    } catch (e) {
      _ayar = eski;
      _durumYaz(_dvt('duvar.kaydedilemedi', { detay: e.message || String(e) }), 'err');
    }
    await uygula(_aktifSekme);
    panelCiz();
  }

  // ── Ayar paneli · ÖNİZLEME ÖNCE (2026-09-27, kişisel 54de771 yeniden yazıldı) ──
  /* Solda seçili sekmenin "böyle görünecek" sahnesi (perde + bulanıklık canlı), sağda
     sekme → duvar listesi + kitaplık. Sekme listesi SUNUCUDAN (`_sekmeler`) — kişiselin
     sabit 9'lu listesi taşınmadı. Metnin tamamı sözlükten (`_dvt`); ad ekleri
     ("'nun duvarı") kalıpta, kodda değil — EN'e çevrilemezdi. */
  function _dvt(anahtar, degerler){ return (window.YukiDil && window.YukiDil.t) ? window.YukiDil.t(anahtar, degerler) : String(anahtar); }
  function _dvtc(anahtar, n, degerler){ return (window.YukiDil && window.YukiDil.tc) ? window.YukiDil.tc(anahtar, n, degerler) : _dvt(anahtar, Object.assign({ n: n }, degerler)); }

  /* Görünen ad = üst menüdeki ad (CHAT · PLAN · AYAR · PANEL). Tabloda karşılığı
     olmayan sekme büyük harfle basılır: backend'e yeni sekme eklenip buraya yazılmayı
     unutulursa kullanıcı onu yine görür (menüye yazmayı unutmak = ulaşılamaz özellik). */
  const SEKME_ADLARI_ANAHTARLARI = {
    chat: 'duvar.sekme.sohbet', planner: 'duvar.sekme.plan', hq: 'duvar.sekme.ayar',
    panel: 'duvar.sekme.panel',
  };
  function _sekmeAdi(s) {
    const anahtar = SEKME_ADLARI_ANAHTARLARI[s];
    return anahtar ? _dvt(anahtar) : String(s).toUpperCase();
  }

  function _esc(s) {
    return String(s == null ? '' : s).replace(/[&<>"']/g,
      c => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));
  }
  function _detay(d, r) { return (d && (d.detail || d.error)) ? String(d.detail || d.error) : ('HTTP ' + (r ? r.status : '?')); }

  let _secili = null;        // sahnede gösterilen sekme
  let _silSor = null;        // satır içi silme onayı bekleyen duvar
  let _durum = null;         // yeniden çizimde kaybolmasın: {metin, sinif}
  function _durumYaz(metin, sinif) {
    _durum = metin ? { metin: metin, sinif: sinif || '' } : null;
    const el = document.getElementById('dv-durum');
    if (el) { el.textContent = metin || ''; el.className = 'dv-durum ' + (sinif || ''); }
  }
  const _kullanan = id => _sekmeler.filter(s => _sekmeIcinDuvar(s) === id).map(_sekmeAdi);
  const _kok2 = () => document.getElementById('dv-govde') || document.getElementById('hq-panel-duvar');

  function panelCiz() {
    const kok = _kok2();
    if (!kok) return;
    if (!_ayar) {
      /* Liste alınamadı: sonsuza dek "YÜKLENİYOR" demek yerine söyle + yeniden dene */
      kok.innerHTML = '<div class="bos"><p class="bos-bas">' + _esc(_dvt('duvar.okunamadi')) + '</p>' +
        '<button type="button" class="dg dg-ikincil" id="dv-tekrar">' + _esc(_dvt('duvar.tekrar-dene')) + '</button></div>';
      const b = kok.querySelector('#dv-tekrar');
      if (b) b.onclick = async () => { await yenile(); await uygula(_aktifSekme); panelCiz(); };
      return;
    }
    const mod = _ayar.mod || 'sekme';
    if (!_secili || _sekmeler.indexOf(_secili) < 0) {
      _secili = _sekmeler.find(s => _sekmeIcinDuvar(s)) || (_sekmeler.indexOf('hq') >= 0 ? 'hq' : _sekmeler[0]) || 'chat';
    }
    const secAd = _sekmeAdi(_secili);
    const secId = _sekmeIcinDuvar(_secili);
    const secK = _liste.find(k => k.id === secId);
    const perde = _ayar.perde ?? 55, bulanik = _ayar.bulanik ?? 0;

    let bos = '';
    if (!secK) {
      const [b1, b2] = mod === 'kapali' ? ['duvar.sahne.kapali-bas', 'duvar.sahne.kapali-metin']
        : !_liste.length ? ['duvar.sahne.kitaplik-bas', 'duvar.sahne.kitaplik-metin']
        : ['duvar.sahne.sekme-bas', 'duvar.sahne.sekme-metin'];
      /* Kitaplık boşken yükleme DOĞRUDAN burada: telefonda "+ Yükle" ilk ekranın altında kalıyordu */
      bos = '<div class="dv-sahne-bos"><b>' + _esc(_dvt(b1, { sekme: secAd })) + '</b><span>' + _esc(_dvt(b2)) + '</span>' +
        (mod !== 'kapali' && !_liste.length ? '<button type="button" class="dg dg-birincil" data-duvar-yukle-ac>' + _esc(_dvt('duvar.sahne.yukle')) + '</button>' : '') + '</div>';
    }
    let h = '<section class="dv-sol">' +
      '<h4 class="dv-h">' + _esc(_dvt('duvar.sahne.baslik', { sekme: secAd })) + '</h4>' +
      '<div class="dv-mod-satir" role="group" aria-label="' + _esc(_dvt('duvar.mod.grup')) + '">' +
      [['kapali', 'duvar.mod.kapali'], ['tek', 'duvar.mod.tek'], ['sekme', 'duvar.mod.sekme']].map(([v, a]) =>
        '<button type="button" class="dv-mod-btn' + (mod === v ? ' aktif' : '') + '" aria-pressed="' + (mod === v) + '" data-duvar-mod="' + v + '">' + _esc(_dvt(a)) + '</button>').join('') +
      '</div>' +
      /* Sahne ekranın KENDİ oranında: telefonda yatay kutu dikey duvarın yalnız bir dilimini gösteriyordu (goz tur 2) */
      '<div class="dv-sahne" id="dv-sahne" style="--dv-oran:' + (innerWidth / Math.max(1, innerHeight)).toFixed(3) + '">' +
        (secK ? '<div class="dv-sahne-zemin" data-duvar-sahne="' + _esc(secK.id) + '" data-tip="' + _esc(secK.tip) + '"></div>' +
                '<div class="dv-sahne-perde" style="opacity:' + (perde / 100) + '"></div>' : '') +
        '<div class="dv-sahne-ui" aria-hidden="true"><div class="dv-sahne-bar"><b>' + _esc(secAd) + '</b><span></span><span></span><span></span></div>' +
        '<div class="dv-sahne-gov"><div><i class="b"></i><i></i><i style="width:80%"></i><i style="width:60%"></i></div><div><i class="b"></i><i></i><i style="width:70%"></i></div></div></div>' +
        (secK ? '<span class="dv-sahne-etiket">' + _esc(secK.ad) + ' · ' + _esc(_dvt('duvar.sahne.karartma', { n: perde })) + '</span>' : bos) +
      '</div>';
    if (mod !== 'kapali') {
      h += '<div class="dv-kaydiricilar">' +
        '<label class="dv-kaydirici"><span>' + _esc(_dvt('duvar.perde.etiketi')) + ' <b data-deger="perde">' + _esc(_dvt('duvar.yuzde', { n: perde })) + '</b></span>' +
        '<small>' + _esc(_dvt('duvar.perde.ipucu')) + '</small>' +
        '<input type="range" min="0" max="95" value="' + perde + '" data-duvar-perde></label>' +
        '<label class="dv-kaydirici"><span>' + _esc(_dvt('duvar.bulaniklik.etiketi')) + ' <b data-deger="bulanik">' + bulanik + ' px</b></span>' +
        '<small>' + _esc(_dvt('duvar.bulaniklik.ipucu')) + '</small>' +
        '<input type="range" min="0" max="20" value="' + bulanik + '" data-duvar-bulanik></label></div>';
    }
    h += '</section><aside class="dv-sag">';

    const duvarli = _sekmeler.filter(s => _sekmeIcinDuvar(s)).length;
    h += '<div class="dv-hud">' + _esc(_dvt('duvar.bolum.sekmeler')) + ' <span>' +
      _esc(mod === 'tek' ? _dvt('duvar.mod.tek') : mod === 'kapali' ? _dvt('duvar.mod.kapali') : _dvtc('duvar.sekmede-duvar', duvarli)) + '</span></div>' +
      '<div class="dv-sekmeler">' + _sekmeler.map(s => {
        const id = _sekmeIcinDuvar(s), k = _liste.find(x => x.id === id);
        return '<button type="button" class="dv-sekme-satir' + (s === _secili ? ' secili' : '') + '" data-duvar-secili="' + _esc(s) + '" aria-pressed="' + (s === _secili) + '">' +
          '<b>' + _esc(_sekmeAdi(s)) + '</b><span class="' + (k ? '' : 'yok') + '">' + _esc(k ? k.ad : _dvt(mod === 'kapali' ? 'duvar.durum.kapali' : 'duvar.durum.yok')) + '</span>' +
          '<i class="dv-kucuk"' + (k ? ' data-duvar-onizleme="' + _esc(k.id) + '" data-tip="' + _esc(k.tip) + '"' : '') + '></i></button>';
      }).join('') + '</div>';
    if (mod === 'sekme' && secId) {
      h += '<button type="button" class="dv-kaldir" data-duvar-kaldir="' + _esc(_secili) + '">' + _esc(_dvt('duvar.kaldir', { sekme: secAd })) + '</button>';
    }

    const ipucu = mod === 'kapali' ? _dvt('duvar.ipucu.kapali') : mod === 'tek' ? _dvt('duvar.ipucu.tek') : _dvt('duvar.ipucu.sekme', { sekme: secAd });
    h += '<div class="dv-hud dv-hud-kit">' + _esc(_dvt('duvar.bolum.kitaplik')) + ' <span>' + (_liste.length ? _esc(_dvtc('duvar.oge-sayisi', _liste.length)) : '') + '</span></div>' +
      '<p class="dv-ipucu">' + _esc(ipucu) + '</p><div class="dv-kit">' + _liste.map(k => {
        const kul = _kullanan(k.id);
        if (_silSor === k.id) {
          return '<div class="dv-oge sor"><span class="dv-oge-mini">' + (k.tip === 'video' ? '<video muted playsinline data-duvar-onizleme="' + _esc(k.id) + '"></video>' : '<img alt="" data-duvar-onizleme="' + _esc(k.id) + '">') + '</span>' +
            '<p>' + _esc(_dvt('duvar.sil.soru', { ad: k.ad })) +
            (kul.length ? '<small>' + _esc(_dvt('duvar.sil.kalir', { sekmeler: kul.join(', ') })) + '</small>' : '') + '</p>' +
            '<button type="button" class="dg dg-sessiz" data-duvar-vazgec>' + _esc(_dvt('duvar.vazgec')) + '</button>' +
            '<button type="button" class="dg dg-yikici" data-duvar-sil-evet="' + _esc(k.id) + '">' + _esc(_dvt('duvar.islem.sil')) + '</button></div>';
        }
        return '<div class="dv-oge' + (k.id === secId ? ' secili' : '') + '">' +
          '<button type="button" class="dv-oge-sec" data-duvar-ata="' + _esc(k.id) + '" aria-label="' + _esc(k.ad) + '" title="' + _esc(k.ad) + (kul.length ? ' · ' + _esc(kul.join(', ')) : '') + '"' + (mod === 'kapali' ? ' disabled' : '') + '>' +
          (k.tip === 'video' ? '<video muted loop playsinline data-duvar-onizleme="' + _esc(k.id) + '"></video><span class="dv-rozet">' + _esc(_dvt('duvar.tur.video')) + '</span>'
                             : '<img alt="" data-duvar-onizleme="' + _esc(k.id) + '">') + '</button>' +
          '<button type="button" class="dv-oge-sil" data-duvar-sil="' + _esc(k.id) + '" aria-label="' + _esc(_dvt('duvar.sil.aria', { ad: k.ad })) + '">✕</button></div>';
      }).join('') +
      /* `accept` uzantı listesi, joker DEĞİL: `image/…` jokerindeki eğik çizgi + yıldız,
         test_bl402'nin yorum söken regex'ine yorum başı gibi görünüp dosyanın yarısını
         kör ediyordu (09-27 harita). Liste backend BICIMLER ile aynı. */
      '<label class="dv-yukle" id="dv-yukle-alan"><input type="file" id="dv-dosya" multiple hidden accept=".jpg,.jpeg,.png,.gif,.webp,.avif,.mp4,.m4v,.webm,.ogv">' +
      '<b>' + _esc(_dvt('duvar.yukle.dugme')) + '</b><small>' + _esc(_dvt(_liste.length && !matchMedia('(hover: none)').matches ? 'duvar.yukle.surukle' : 'duvar.yukle.turleri')) + '</small></label></div>' +
      '<p class="dv-durum" id="dv-durum" role="status"></p></aside>';

    kok.innerHTML = h;
    if (_durum) _durumYaz(_durum.metin, _durum.sinif);
    _panelBagla(kok);
    _onizlemeleriDoldur(kok);
  }

  async function _onizlemeleriDoldur(kok) {
    const sahne = kok.querySelector('[data-duvar-sahne]');
    if (sahne) {
      const url = await _medyaUrl(sahne.getAttribute('data-duvar-sahne'));
      if (url) {
        const el = document.createElement(sahne.dataset.tip === 'video' ? 'video' : 'img');
        el.src = url; el.alt = '';
        el.style.filter = _ayar.bulanik ? 'blur(' + _ayar.bulanik + 'px)' : 'none';
        if (el.tagName === 'VIDEO') { el.muted = true; el.loop = true; el.playsInline = true; try { await el.play(); } catch (_) {} }
        sahne.appendChild(el);
      }
    }
    for (const el of kok.querySelectorAll('[data-duvar-onizleme]')) {
      const url = await _medyaUrl(el.getAttribute('data-duvar-onizleme'));
      if (!url) continue;
      if (el.tagName === 'I') {               // sekme satırındaki küçük kare
        if (el.dataset.tip === 'video') { const v = document.createElement('video'); v.muted = true; v.src = url; el.appendChild(v); }
        else el.style.backgroundImage = 'url("' + url + '")';
        continue;
      }
      el.src = url;
      if (el.tagName === 'VIDEO') { el.muted = true; try { await el.play(); } catch (_) {} }
    }
  }

  function _canliGorunum() {
    // Kaydırıcı sürüklenirken sahne + gerçek arka plan birlikte değişir
    const p = document.querySelector('#dv-sahne .dv-sahne-perde');
    if (p) p.style.opacity = String((_ayar.perde ?? 55) / 100);
    const m = document.querySelector('#dv-sahne [data-duvar-sahne] > *');
    if (m) m.style.filter = _ayar.bulanik ? 'blur(' + _ayar.bulanik + 'px)' : 'none';
    const e = document.querySelector('#dv-sahne .dv-sahne-etiket');
    const k = _liste.find(x => x.id === _sekmeIcinDuvar(_secili));
    if (e && k) e.textContent = k.ad + ' · ' + _dvt('duvar.sahne.karartma', { n: _ayar.perde ?? 55 });
    uygula(_aktifSekme);
  }

  function _panelBagla(kok) {
    /* "Hepsinde aynı"ya geçerken tek duvar boşsa sahnede görünen duvar alınır —
       yoksa mod değişir ama ekran duvarsız kalırdı (09-27 ölçümü) */
    kok.querySelectorAll('[data-duvar-mod]').forEach(b =>
      b.onclick = () => {
        const m = b.getAttribute('data-duvar-mod');
        const yeni = { mod: m };
        if (m === 'tek' && !_ayar.tek) yeni.tek = _sekmeIcinDuvar(_secili) || (_liste[0] && _liste[0].id) || null;
        ayarKaydet(yeni);
      });

    kok.querySelectorAll('[data-duvar-secili]').forEach(b =>
      b.onclick = () => { _secili = b.getAttribute('data-duvar-secili'); _silSor = null; panelCiz(); });

    // Kitaplıkta dokunulan duvar: tek modda hepsine, sekme modunda seçili sekmeye
    kok.querySelectorAll('[data-duvar-ata]').forEach(b =>
      b.onclick = () => {
        const id = b.getAttribute('data-duvar-ata');
        if ((_ayar.mod || 'sekme') === 'tek') return ayarKaydet({ tek: id });
        const y = Object.assign({}, _ayar.sekmeler || {});
        y[_secili] = id;
        ayarKaydet({ sekmeler: y });
      });
    kok.querySelectorAll('[data-duvar-kaldir]').forEach(b =>
      b.onclick = () => {
        const y = Object.assign({}, _ayar.sekmeler || {});
        delete y[b.getAttribute('data-duvar-kaldir')];
        ayarKaydet({ sekmeler: y });
      });

    // Kaydırıcılar: sürüklerken CANLI önizle, bırakınca kaydet.
    // Her `input` olayında PUT atmak saniyede onlarca istek demekti.
    const canli = (el, alan, bicim) => {
      if (!el) return;
      const deger = kok.querySelector('[data-deger="' + alan + '"]');
      el.oninput = () => {
        _ayar[alan] = parseInt(el.value, 10);
        if (deger) deger.textContent = bicim(el.value);
        _canliGorunum();
      };
      el.onchange = () => ayarKaydet({ [alan]: parseInt(el.value, 10) });
    };
    canli(kok.querySelector('[data-duvar-perde]'), 'perde', v => _dvt('duvar.yuzde', { n: v }));
    canli(kok.querySelector('[data-duvar-bulanik]'), 'bulanik', v => v + ' px');

    // Silme: satır içi onay (confirm() YOK — tarayıcı modali otomasyonu kilitler);
    // onay hangi sekmelerin duvarsız kalacağını söyler.
    kok.querySelectorAll('[data-duvar-sil]').forEach(b =>
      b.onclick = (ev) => { ev.stopPropagation(); _silSor = b.getAttribute('data-duvar-sil'); panelCiz(); });
    kok.querySelectorAll('[data-duvar-vazgec]').forEach(b =>
      b.onclick = () => { _silSor = null; panelCiz(); });
    kok.querySelectorAll('[data-duvar-sil-evet]').forEach(b =>
      b.onclick = async () => {
        const id = b.getAttribute('data-duvar-sil-evet');
        b.disabled = true;
        try {
          const r = await _f(_kok() + API + '/' + encodeURIComponent(id), { method: 'DELETE' });
          const d = await r.json().catch(() => ({}));
          if (!r.ok) throw new Error(_detay(d, r));
          const u = _blobs.get(id);
          if (u) { URL.revokeObjectURL(u); _blobs.delete(id); }
          _durumYaz('');
        } catch (e) {
          _durumYaz(_dvt('duvar.silinemedi', { detay: e.message || String(e) }), 'err');
        }
        _silSor = null;
        await yenile(); await uygula(_aktifSekme); panelCiz();
      });

    kok.querySelectorAll('[data-duvar-yukle-ac]').forEach(b =>
      b.onclick = () => { const g = kok.querySelector('#dv-dosya'); if (g) g.click(); });

    const alan = kok.querySelector('#dv-yukle-alan');
    const girdi = kok.querySelector('#dv-dosya');
    if (alan && girdi) {
      girdi.onchange = () => girdi.files.length && _yukleHepsi(girdi.files);
      alan.ondragover = (e) => { e.preventDefault(); alan.classList.add('surukleniyor'); };
      alan.ondragleave = () => alan.classList.remove('surukleniyor');
      alan.ondrop = (e) => {
        e.preventDefault(); alan.classList.remove('surukleniyor');
        if (e.dataTransfer.files.length) _yukleHepsi(e.dataTransfer.files);
      };
    }
  }

  /* Birden çok dosya SIRAYLA yüklenir (eskiden yalnız ilki alınıyordu), sonuç özetlenir */
  async function _yukleHepsi(dosyalar) {
    const liste = Array.from(dosyalar);
    let iyi = 0, sonHata = '';
    for (const dosya of liste) {
      _durumYaz(_dvt('duvar.yukle.devam', { ad: dosya.name }));
      const fd = new FormData();
      fd.append('dosya', dosya);
      try {
        const r = await _f(_kok() + API + '/yukle', { method: 'POST', body: fd });
        const d = await r.json().catch(() => ({}));
        if (!r.ok || d.ok === false) throw new Error(_detay(d, r));
        iyi++;
      } catch (e) {
        sonHata = dosya.name + ': ' + (e.message || String(e));
      }
    }
    const kotu = liste.length - iyi;
    await yenile(); panelCiz();
    if (!kotu) _durumYaz(_dvtc('duvar.yukle.basarili', iyi), 'ok');
    else _durumYaz(_dvt('duvar.yukle.karma', { iyi: iyi, kotu: kotu, detay: sonHata }), 'err');
  }

  // ── Başlat ────────────────────────────────────────────────────
  async function baslat() {
    if (!(await yenile())) return;
    _katman();
    await uygula(_aktifSekme);
  }

  window.duvarUygula   = uygula;
  window.duvarPanelCiz = panelCiz;    // AYAR › Duvar Kâğıdı açılınca
  window.duvarBaslat   = baslat;
  window.duvarYenile   = yenile;

  /* 🔑 SEKME KANCASI — ürüne taşınırken DEĞİŞTİ (2026-09-08).
     Kişiselde `map-engine.js::switchTab`'ın sonuna elle bir `duvarUygula(tab)`
     satırı eklenmişti. Üründe buna gerek yok: `tab-nav.js` sekme değişiminde
     zaten bir `tabchange` CustomEvent yayınlıyor ('te PANEL için
     eklenmiş). Olayı dinlemek, başka bir dosyaya satır eklemekten iyidir —
     kanca `duvar.js`'in İÇİNDE kalır, özelliği kaldırmak tek dosya silmek olur
     ve `tab-nav.js`'te unutulmuş yetim bir çağrı kalmaz. */
  document.addEventListener('tabchange', (e) => {
    const sekme = e && e.detail && e.detail.tab;
    if (sekme) uygula(sekme);
  });

  window.addEventListener('yuki-dil-degisti', () => {
    panelCiz();
  });

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', () => setTimeout(baslat, 900));
  } else {
    setTimeout(baslat, 900);          // auth oturana kadar bekle
  }
})();
