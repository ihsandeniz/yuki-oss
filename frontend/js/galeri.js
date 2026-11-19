/* ═══ GALERİ — PC medya gezgini  ═══════════════
 * ═══ ARŞİV düzeni (Taslak B, 2026-09-28) ══════════════════════════
 *
 * Üç sütun: klasör RAYI (sayı + pay çubuğu, ağaç) · ay ay gruplanmış NEHİR ·
 * zaman OMURGASI (ay yoğunluğu, bulunduğun ay altın, tıkla → o aydan başla).
 * Büyük görünüm = sağda FİŞ; ızgara görünür kalır. ⛶ → tüm pencere (tam kip).
 *
 * İki kullanım, TEK yüzey:
 *   A) kullanıcı sekmeden/panelden açar, klasörlerde gezer
 *   B) Yuki `show_media` ile `?ac=<id>` açar → aynı ızgara, o dosya fişte
 * B, A'nın üstüne kurulur — ayrı gösterim yolu yazılmaz (bu depoda `chat_sync`
 * tam olarak ikinci bir yol açtığı için 3 ay araçsız koştu).
 *
 * 🔴 `<img src>` `Authorization` başlığı GÖNDEREMEZ → küçük resim blob olarak
 *    indirilir (duvar.js deseni, ikinci kez icat edilmiyor).
 * 🔴 Video BLOB OLMAZ — bellek şişer, ileri sarma ölür. Video için kısa ömürlü
 *    bilet alınır ve `<video src="/api/galeri/akis/<bilet>">` Range ile akar.
 * 🔴 Tek seferde 6.981 kart çizilmez — hem `hepsi` akışı hem klasör listesi
 *    SAYFA SAYFA çizilir (`SAYFA`), sentinel görününce devamı gelir.
 * ⚠️ Nehir düzeninde kartın oranı SUNUCUDAN gelir (`en`/`boy`);
 *    gelmezse resim yüklenince sütun yüksekliği değişir ve ızgara zıplar.
 * 🔑 Aya atlama HAFİF SÜRÜM: liste o ayın OFSETİNDEN yeniden kurulur (ofseti
 *    sunucu hesaplar, `/aylik`), üstte "↑ daha yeni aylar". İki yönlü sayfalama
 *    YOK — `_nesil` yarışını yeniden açmamak için (SENTEZ kararı).
 * 🔑 Yeni uçlar (`/klasorler`, `/aylik`) yoksa (eski backend) galeri ÇÖKMEZ:
 *    ray yalnız kökleri gösterir, omurga `/istatistik`'ten yedeklenir ya da gizlenir.
 */
(function () {
  'use strict';

  var API = '/api/galeri';
  var SAYFA = 120;                 // hem sunucu sayfası hem çizim öbeği
  var BOYUTLAR = ['kucuk', 'orta', 'buyuk', 'cokbuyuk'];
  var BOYUT_ETIKET = { kucuk: 'Küçük', orta: 'Orta', buyuk: 'Büyük', cokbuyuk: 'Çok büyük' };
  var BOYUT_PX = { kucuk: 120, orta: 190, buyuk: 290, cokbuyuk: 440 };  // hedef sütun genişliği
  // 🔴 Dar ekranda (telefon) sütun sayısı SABİT: genişlikten türetince 375px'te
  // orta/büyük/çok büyük üçü de 1 sütuna düşüyordu → düğme "çalışmıyor" gibiydi
  // (ölçüldü). 640px'ten geniş ekranda formül zaten dört ayrı sonuç verir.
  var SUTUN_DAR = { kucuk: 4, orta: 3, buyuk: 2, cokbuyuk: 1 };
  var DAR_ESIK = 640;
  // Sunucunun ürettiği küçük resim kademeleri (galeri_api.KUCUK_KADEMELER ile aynı).
  var KUCUK_KADEMELER = [200, 400, 800, 1400];
  // Kart GÖSTERİM sınırları. Oran sunucudan gelir ve kademe seçimi ona bakar;
  // yalnız kutunun görünen oranı kıstırılır (aşırı panorama 44px altına inip
  // dokunulamaz olmasın, aşırı dikey ekran görüntüsü sütunu boğmasın).
  var KART_MIN = 44;
  var ORAN_ALT = 0.4;

  var AYLAR = ['Ocak', 'Şubat', 'Mart', 'Nisan', 'Mayıs', 'Haziran', 'Temmuz',
               'Ağustos', 'Eylül', 'Ekim', 'Kasım', 'Aralık'];
  var AYK = ['OCA', 'ŞUB', 'MAR', 'NİS', 'MAY', 'HAZ', 'TEM', 'AĞU', 'EYL', 'EKİ', 'KAS', 'ARA'];

  var TEL = window.matchMedia('(max-width: 768px)');
  var KOMPAKT = window.matchMedia('(max-width: 1239px)');   // css/galeri.css KOMPAKT eşiğiyle AYNI

  /* 🔴 Neden CSS `column-count` DEĞİL (ölçüldü 2026-09-12):
   * CSS sütunlarında içerik eklenince BÜTÜN düzen yeniden akar. Sonsuz akışta
   * ikinci sayfa gelince 41. kart 3764px'den 9261px'e atladı ve sütun değiştirdi
   * (5497px kayma). Bunun yerine sabit sütunlar, her yeni kart O ANDA EN KISA
   * sütuna eklenir. Eklenen kart kimseyi yerinden oynatmaz.
   * Sütun durumu KABIN üstünde tutulur (`kap._gl`): ay grupları kipinde her
   * grubun kendi nehri var ve fiş açılınca HEPSİ yeniden dağıtılmalı. */

  var _blob = new Map();           // id → objectURL
  var _durum = {
    kokler: [],
    mod: 'hepsi',                  // 'hepsi' | 'klasor' | 'arama'
    klasorId: null,
    klasorAd: null,
    seciliKok: null,
    dosyalar: [],                  // akıştaki TÜM kayıtlar (sırayla, `baslangic`tan itibaren)
    cizilen: 0,                    // ızgaraya basılmış kart sayısı
    offset: 0, baslangic: 0, toplam: 0, bitti: true, yukleniyor: false,
    acik: -1,
    seciciYol: null,
    boyut: 'orta',
    uzantilar: { resim: [], video: [] },
    // ── Görünüm ayarları ─────────────────────────────────────────────
    // 🔴 `sirala`/`yon`/`tip` SUNUCUYA gider, istemcide dizilmez: akış sayfalı
    //    ve elde olan 120 kaydı dizmek "en büyük dosya"ya yanlış cevap verirdi.
    sirala: 'tarih',
    yon: '',                       // '' = ölçüye göre doğal yön
    tip: '',                       // '' | 'resim' | 'video'
    grupla: true,                  // B: ay başlıkları varsayılan
    altklasor: true,               // B: raydaki sayı alt ağaç sayısıdır
    sonGrup: null,
    grupAktifKap: null,
    // ── Arşiv ────────────────────────────────────────────────────────
    agacVar: false,                // `/klasorler` ucu cevap verdi mi
    aylik: null,                   // {anahtar, zaman, toplam, aylar[], harita{}, yedek}
    omurgaCizildi: false
  };
  var _dugum = {};                 // id → ray düğümü (kökler dahil)
  var _agacKokler = [];

  function $(id) { return document.getElementById(id); }
  function fmt(n) { return Number(n || 0).toLocaleString('tr-TR'); }
  function iki(n) { return (n < 10 ? '0' : '') + n; }
  function svgIk(ad, sinif) {
    var ns = 'http://www.w3.org/2000/svg';
    var s = document.createElementNS(ns, 'svg');
    s.setAttribute('class', 'gl-ik' + (sinif ? ' ' + sinif : ''));
    s.setAttribute('aria-hidden', 'true');
    var u = document.createElementNS(ns, 'use');
    u.setAttribute('href', '#' + ad);
    s.appendChild(u);
    return s;
  }
  function el(etiket, sinif, metin) {
    var e = document.createElement(etiket);
    if (sinif) e.className = sinif;
    if (metin != null) e.textContent = metin;
    return e;
  }

  function token() {
    try { return (sessionStorage.getItem('aliceToken') || localStorage.getItem('aliceToken') || ''); } catch (e) { return ''; }
  }

  function api(yol, opts) {
    opts = opts || {};
    var h = opts.headers || {};
    var t = token();
    if (t) h['Authorization'] = 'Bearer ' + t;
    opts.headers = h;
    return fetch(API + yol, opts);
  }

  async function json(yol, opts) {
    var r = await api(yol, opts);
    if (!r.ok) {
      var d = '';
      try { d = (await r.json()).detail || ''; } catch (e) {}
      var hata = new Error(d || ('HTTP ' + r.status));
      hata.durum = r.status;
      throw hata;
    }
    return r.json();
  }

  function duyur(metin) {
    var d = $('gl-duyuru');
    d.textContent = metin;
    d.hidden = false;
    clearTimeout(duyur._z);
    duyur._z = setTimeout(function () { d.hidden = true; }, 3200);
  }

  // 🔴 Blob havuzu SINIRLI. Her küçük resim `createObjectURL` ile bellekte kalır
  // ve `revokeObjectURL` çağrılmadıkça sekme kapanana dek serbest bırakılmaz —
  // 6.981 kartlık bir akışta kaydırmaya devam etmek belleği sürekli şişirirdi.
  // En eski kayıt düşürülür (Map ekleme sırasını korur = LRU'nun ucuz hâli).
  var BLOB_SINIR = 500;

  async function medyaUrl(anahtar, yol) {
    if (_blob.has(anahtar)) {
      var v = _blob.get(anahtar);          // tazele: sona taşı
      _blob.delete(anahtar); _blob.set(anahtar, v);
      return v;
    }
    var r = await api(yol);
    if (!r.ok) {
      var hata = new Error('HTTP ' + r.status);
      hata.durum = r.status;
      if (r.status === 503 && r.headers.get('X-Galeri-Hata') === 'disk') diskUyar();
      throw hata;
    }
    var url = URL.createObjectURL(await r.blob());
    _blob.set(anahtar, url);
    while (_blob.size > BLOB_SINIR) {
      var ilk = _blob.keys().next().value;
      var eski = _blob.get(ilk);
      _blob.delete(ilk);
      // ⚠️ Büyük görünümde AÇIK olan blob'u iptal etme — resim anında kararırdı.
      if (eski !== _acikBlob) { try { URL.revokeObjectURL(eski); } catch (e) {} }
    }
    return url;
  }
  var _acikBlob = null;

  // 🔴 503 + `X-Galeri-Hata: disk` = dosya değil AYGIT okunamıyor (USB koptu,
  // şifreli disk eski aygıta bağlı kaldı). Kırık kutular "resim bozuk" sanılmasın;
  // ızgarada yüzlerce kart aynı anda düşer → duyuru 30 sn'de bir kez.
  var _diskUyariZaman = 0;
  function diskUyar() {
    var simdi = Date.now();
    if (simdi - _diskUyariZaman < 30000) return;
    _diskUyariZaman = simdi;
    duyur('Disk okunamıyor — USB bağlantısı kopmuş olabilir. Diski yeniden bağlayıp galeriyi yenile.');
  }

  // ── Küçük resim gözlemcisi (tembel) ─────────────────────────────
  /** Bu kart için gereken küçük resim kademesi (uzun kenar px).
   *
   * 🔴 İki ayrı kusur burada buluşuyor, ikisi de ÖLÇÜMLE bulundu:
   * ① En yakın ÜST kademeye yuvarlanmalı ("çok büyük"te 400px → bulanık).
   * ② Kademe UZUN KENARI sınırlar, ama kartı dolduran GENİŞLİKtir. Dikey
   *    resimlerde istenen kenar 1/oran ile büyütülür.
   */
  function kucukKenar(oran) {
    var hedef = (_sutunGenislik > 8 ? _sutunGenislik : (BOYUT_PX[_durum.boyut] || 190));
    var dpr = Math.min(window.devicePixelRatio || 1, 2);
    var istenen = hedef * dpr;
    var o = parseFloat(oran);
    if (o > 0 && o < 1) istenen = istenen / o;      // dikey: uzun kenar boy'dur
    for (var i = 0; i < KUCUK_KADEMELER.length; i++) {
      if (istenen <= KUCUK_KADEMELER[i]) return KUCUK_KADEMELER[i];
    }
    return KUCUK_KADEMELER[KUCUK_KADEMELER.length - 1];
  }

  // 🔑 Kök = kaydırılan kap (#gl-icerik). Kök `null` (görünüm alanı) olsaydı
  // `rootMargin` iç kaydırma kabının kırpmasını aşamaz, ön yükleme çalışmazdı.
  var _gozlemci = new IntersectionObserver(function (girdiler) {
    girdiler.forEach(function (g) {
      if (!g.isIntersecting) return;
      var img = g.target;
      _gozlemci.unobserve(img);
      var k = kucukKenar(img.parentNode && img.parentNode.dataset.oran);
      medyaUrl('k' + k + ':' + img.dataset.id, '/kucuk/' + img.dataset.id + '?k=' + k)
        .then(function (u) { img.src = u; img.classList.add('yuklendi'); })
        .catch(function () { img.classList.add('kirik'); });
    });
  }, { root: $('gl-icerik'), rootMargin: '400px' });

  // ── Sonsuz akış sentineli ───────────────────────────────────────
  var _sentinel = new IntersectionObserver(function (g) {
    if (g[0] && g[0].isIntersecting) dahaGetir();
  }, { root: $('gl-icerik'), rootMargin: '600px' });

  // ── Boyut kademesi ──────────────────────────────────────────────
  function boyutKur() {
    try {
      var b = localStorage.getItem('galeriBoyut');
      if (BOYUTLAR.indexOf(b) >= 0) _durum.boyut = b;
    } catch (e) {}
    var kap = $('gl-boyut');
    kap.innerHTML = '';
    var IZ = { kucuk: [4, 5], orta: [3, 7], buyuk: [2, 10], cokbuyuk: [1, 14] };
    BOYUTLAR.forEach(function (b) {
      var d = document.createElement('button');
      d.className = 'gl-boyut-btn';
      d.type = 'button';
      d.dataset.boyut = b;
      d.setAttribute('role', 'radio');
      d.setAttribute('aria-label', BOYUT_ETIKET[b] + ' kutucuk');
      var i = document.createElement('i');
      i.style.gridTemplateColumns = 'repeat(' + IZ[b][0] + ',' + IZ[b][1] + 'px)';
      for (var n = 0; n < IZ[b][0]; n++) {
        var k = document.createElement('b'); k.style.height = IZ[b][1] + 'px'; i.appendChild(k);
      }
      d.appendChild(i);
      d.addEventListener('click', function () { boyutSec(b); });
      kap.appendChild(d);
    });
    $('gl-kucult').addEventListener('click', function () { boyutAdim(-1); });
    $('gl-buyult').addEventListener('click', function () { boyutAdim(1); });
    boyutUI();
    $('gl-izgara').dataset.boyut = _durum.boyut;
  }

  function boyutAdim(y) {
    var i = BOYUTLAR.indexOf(_durum.boyut) + y;
    if (i >= 0 && i < BOYUTLAR.length) boyutSec(BOYUTLAR[i]);
  }

  function boyutSec(b) {
    if (b === _durum.boyut) return;
    _durum.boyut = b;
    try { localStorage.setItem('galeriBoyut', b); } catch (e) {}
    boyutUI();
    $('gl-izgara').dataset.boyut = b;
    duzenTazele(true);
    kademeTazele();
  }

  function boyutUI() {
    Array.prototype.forEach.call($('gl-boyut').children, function (x) {
      x.setAttribute('aria-checked', String(x.dataset.boyut === _durum.boyut));
    });
    var i = BOYUTLAR.indexOf(_durum.boyut);
    $('gl-kucult').disabled = i <= 0;
    $('gl-buyult').disabled = i >= BOYUTLAR.length - 1;
    $('gl-kucult').title = 'Küçült — şu an ' + BOYUT_ETIKET[_durum.boyut];
    $('gl-buyult').title = 'Büyüt — şu an ' + BOYUT_ETIKET[_durum.boyut];
  }

  /** Kutucuk büyüdüyse görünen kartları DAHA BÜYÜK kademeden yeniden yükle.
   * ⚠️ Yalnız BÜYÜTMEDE çalışır: küçültürken elde daha net resim varken onu
   * atıp yeniden indirmek boşuna trafiktir. */
  var _sonGenislik = 0;
  function kademeTazele() {
    if (_sutunGenislik <= _sonGenislik) { _sonGenislik = _sutunGenislik; return; }
    _sonGenislik = _sutunGenislik;
    var ic = $('gl-icerik').getBoundingClientRect();
    Array.prototype.forEach.call(document.querySelectorAll('.gl-kart img'), function (img) {
      if (!img.dataset.id) return;
      var k = kucukKenar(img.parentNode && img.parentNode.dataset.oran);
      var r = img.getBoundingClientRect();
      var gorunur = r.bottom > ic.top - 600 && r.top < ic.bottom + 600;
      if (!gorunur) {                      // ekran dışındakiler sıraya girsin
        img.classList.remove('yuklendi');
        img.removeAttribute('src');
        _gozlemci.observe(img);
        return;
      }
      medyaUrl('k' + k + ':' + img.dataset.id, '/kucuk/' + img.dataset.id + '?k=' + k)
        .then(function (u) { img.src = u; img.classList.add('yuklendi'); })
        .catch(function () {});
    });
  }

  // ══ NEHİR ═══════════════════════════════════════════════════════════
  function araPx() { return TEL.matches ? 4 : 8; }   // CSS gap ile aynı

  /** Kartların YERLEŞTİRİLECEĞİ kap. Normalde `#gl-izgara`; ay grupları
   * açıkken son grubun kendi nehri.
   *
   * 🔴 Her grup KENDİ sütun setini açar. Tek bir nehre başlık serpiştirmek
   * mümkün değil: tam genişlikte bir başlık sütunların akışını keser. Grup
   * başına ayrı nehir sonsuz akışla da uyumludur — yeni ay gelince yeni kap
   * açılır, öncekiler yerinde kalır. */
  function aktifKap() {
    return _durum.grupAktifKap || $('gl-izgara');
  }

  function izgaraGruplu() {
    return _durum.grupla && _durum.sirala === 'tarih';
  }

  /** Kabın sütunlarını kur; sütun SAYISI değişmediyse yalnız genişliği güncelle.
   * 🔴 Sütun genişliği BİR KEZ ölçülür — her kartta `clientWidth` okumak
   * appendChild sonrası senkron reflow'a zorlar (layout thrashing). */
  function kapKur(kap, zorla) {
    var genislik = kap.clientWidth || kap.getBoundingClientRect().width;
    var ara = araPx();
    var hedef = BOYUT_PX[_durum.boyut] || 190;
    var n = genislik < DAR_ESIK
      ? (SUTUN_DAR[_durum.boyut] || 2)
      : Math.max(1, Math.floor((genislik + ara) / (hedef + ara)));
    var st = kap._gl;
    var gen = Math.max(1, (genislik - (n - 1) * ara) / n);
    if (!zorla && st && st.n === n) { st.gen = gen; return false; }

    // Mevcut kartları sırayla topla (DOM sırası = akış sırası değil, data-i doğru)
    var kartlar = Array.prototype.slice.call(kap.querySelectorAll('.gl-kart'));
    kartlar.sort(function (a, b) { return (+a.dataset.i) - (+b.dataset.i); });

    kap.innerHTML = '';
    st = kap._gl = { n: n, gen: gen, ara: ara, sutunlar: [] };
    for (var i = 0; i < n; i++) {
      var d = document.createElement('div');
      d.className = 'gl-sutun';
      kap.appendChild(d);
      st.sutunlar.push({ el: d, yukseklik: 0, parca: null });
    }
    obek(st, function () { kartlar.forEach(function (k) { yerlestir(st, k); }); });
    return true;
  }

  var _sutunGenislik = 1;

  /** Kartı o anda EN KISA sütuna koy ve o sütunun yüksekliğini güncelle. */
  function yerlestir(st, kart) {
    var en_kisa = st.sutunlar[0];
    for (var i = 1; i < st.sutunlar.length; i++) {
      if (st.sutunlar[i].yukseklik < en_kisa.yukseklik) en_kisa = st.sutunlar[i];
    }
    (en_kisa.parca || en_kisa.el).appendChild(kart);
    var og = parseFloat(kart.dataset.og) || 1;
    en_kisa.yukseklik += Math.max(KART_MIN, st.gen / og) + st.ara;
  }

  /** Bir öbek kartı tek DOM yazımıyla yerleştir (sütun başına 1 appendChild). */
  function obek(st, ciz) {
    st.sutunlar.forEach(function (s) { s.parca = document.createDocumentFragment(); });
    ciz();
    st.sutunlar.forEach(function (s) {
      if (s.parca && s.parca.childNodes.length) s.el.appendChild(s.parca);
      s.parca = null;
    });
  }

  /** Genişlik değişti (pencere, fiş açıldı/kapandı, ray çekmeceye döndü):
   * sütun SAYISI değişen HER kabı yeniden dağıt. Grup kipinde eskiden görünüm
   * baştan istenirdi (tazele) — fiş her açılışta ağa gitmesin diye artık
   * yerinde dağıtılır. */
  function duzenTazele(zorla) {
    var degisti = false;
    var kaplar = $('gl-izgara').classList.contains('gl-gruplu')
      ? document.querySelectorAll('#gl-izgara > .gl-grup > .gl-izgara')
      : [$('gl-izgara')];
    Array.prototype.forEach.call(kaplar, function (k) {
      if (kapKur(k, !!zorla)) degisti = true;
    });
    var ak = aktifKap();
    if (ak && ak._gl) _sutunGenislik = ak._gl.gen;
    if (degisti) { acikKartiGoster(); aktifAyIste(); }
    return degisti;
  }

  // ── Ay grupları ─────────────────────────────────────────────────
  function ayAnahtari(ts) {
    if (!ts) return '0000-00';
    var t = new Date(ts * 1000);
    return t.getFullYear() + '-' + iki(t.getMonth() + 1);
  }
  function ayAdi(ay) { var m = +ay.slice(5) - 1; return AYLAR[m] || ay; }

  function grupAc(ay) {
    var kap = document.createElement('section');
    kap.className = 'gl-grup';
    kap.dataset.ay = ay;
    var bas = el('h2', 'gl-grup-bas');
    if (ay === '0000-00') {
      bas.appendChild(el('span', 'gl-grup-ay', 'Tarihsiz'));
    } else {
      bas.appendChild(el('span', 'gl-grup-ay', ayAdi(ay)));
      bas.appendChild(document.createTextNode(' '));
      bas.appendChild(el('span', 'gl-grup-yil', ay.slice(0, 4)));
    }
    bas.appendChild(document.createTextNode(' '));
    var sayi = el('span', 'gl-grup-sayi gl-d');
    bas.appendChild(sayi);
    bas.appendChild(el('span', 'gl-grup-not gl-hud', 'medya bu ayda'));
    kap.appendChild(bas);
    var izg = el('div', 'gl-izgara');
    izg.dataset.boyut = _durum.boyut;
    kap.appendChild(izg);
    $('gl-izgara').appendChild(kap);
    _durum.grupAktifKap = izg;
    grupSayisiYaz(kap);
    kapKur(izg, true);
    _sutunGenislik = izg._gl.gen;
    return izg;
  }

  /** Başlıktaki sayı o ayın GERÇEK toplamı (süzgece göre, `/aylik`). Uç yoksa
   * yazılmaz — elde olan 120'yi "ayın toplamı" diye göstermek yalan olurdu. */
  function grupSayisiYaz(sek) {
    var a = _durum.aylik && _durum.aylik.harita[sek.dataset.ay];
    var s = sek.querySelector('.gl-grup-sayi');
    var not = sek.querySelector('.gl-grup-not');
    s.textContent = a ? fmt(a.sayi) : '';
    not.hidden = !a;
  }
  function grupSayilariniYaz() {
    Array.prototype.forEach.call(document.querySelectorAll('#gl-izgara > .gl-grup'), grupSayisiYaz);
  }

  // ══ RAY — klasör ağacı ═══════════════════════════════════════════════
  async function koklerYukle() {
    var d = await json('/kokler');
    _durum.kokler = d.kokler;
    _durum.uzantilar = d.uzantilar;
    return d.kokler;
  }

  var RAY_ANAHTAR = 'galeriRay_v1';
  var _rayAcik = {};
  try { _rayAcik = JSON.parse(localStorage.getItem(RAY_ANAHTAR) || '{}') || {}; } catch (e) { _rayAcik = {}; }

  async function agacYukle() {
    _dugum = {};
    _agacKokler = [];
    var d = null;
    try { d = await json('/klasorler'); _durum.agacVar = true; }
    catch (e) { _durum.agacVar = false; }       // eski backend → yalnız kökler

    var kokler = d ? d.kokler : _durum.kokler.map(function (k) {
      return { id: k.id, ad: k.ad, sayi: k.sayi, dogrudan: null };
    });
    kokler.forEach(function (k) {
      var n = { id: k.id, ad: k.ad, toplam: k.sayi, sayi: k.dogrudan, cocuk: [], kok: true, ust: null };
      _dugum[k.id] = n;
      _agacKokler.push(n);
    });
    if (d) {
      d.klasorler.forEach(function (x) {
        _dugum[x.id] = { id: x.id, ad: x.ad, ust: x.ust, kokId: x.kok, goreli: x.goreli,
                         derinlik: x.derinlik, sayi: x.sayi, toplam: x.toplam, cocuk: [] };
      });
      d.klasorler.forEach(function (x) {
        var u = _dugum[x.ust];
        if (u) u.cocuk.push(_dugum[x.id]);
      });
      Object.keys(_dugum).forEach(function (k) {
        _dugum[k].cocuk.sort(function (a, b) { return b.toplam - a.toplam || a.ad.localeCompare(b.ad, 'tr'); });
      });
    }
    rayCiz();
  }

  function rayCiz() {
    _rayTemsil = {};
    var liste = $('gl-ray-liste');
    liste.innerHTML = '';
    var toplam = _agacKokler.reduce(function (t, k) { return t + (k.toplam || 0); }, 0);

    // Hepsi
    liste.appendChild(raySatir({ id: '', ad: 'Hepsi', toplam: toplam, cocuk: [] }, 1, 'i-izgara', null));

    // Tek kök varsa kökün çocukları doğrudan üst düzeydir (taslaktaki gibi);
    // birden çok kök varsa kökler grup başlığı olur.
    // Ağaç yoksa (eski backend) kökler satır olarak kalır — rayda Hepsi'den başka bir şey olsun.
    var ust = (_agacKokler.length === 1 && _durum.agacVar) ? _agacKokler[0].cocuk : _agacKokler;
    var enBuyuk = 1;
    Object.keys(_dugum).forEach(function (k) { if (!_dugum[k].kok || ust === _agacKokler) enBuyuk = Math.max(enBuyuk, _dugum[k].toplam || 0); });
    ust.forEach(function (n) { dugumCiz(liste, n, 1, enBuyuk, toplam); });

    var klSay = Object.keys(_dugum).filter(function (k) { return !_dugum[k].kok; }).length;
    $('gl-kl-sayi').textContent = _durum.agacVar ? fmt(klSay) : fmt(_agacKokler.length);
    if (!_durum.agacVar && _agacKokler.length) {
      var not = el('p', 'gl-salt', 'Klasör ağacı için backend yeniden başlatılmalı — şimdilik kökler.');
      liste.appendChild(not);
    }
    if (!_agacKokler.length) liste.appendChild(el('span', 'gl-bos-etiket', 'kök klasör yok — aşağıdan ekle'));
    koklerCiz();
    rayVurgula();
  }

  /** Ağaç satırı. 🔑 Tek çocuklu, kendi içinde dosyası olmayan ara klasör
   * zinciri (ör. `tatil/2026/yaz`) TEK satıra katlanır: üç
   * satır aynı sayıyı üç kez söyler ve asıl klasörleri iki girinti derine iterdi.
   * Zincir soluk ek olarak yazılır; çocuklar zincirin dibinden gelir. */
  var _rayTemsil = {};
  function dugumCiz(kap, n, derinlik, enBuyuk, toplam) {
    var dip = n, zincir = [];
    while (dip.cocuk.length === 1 && !dip.sayi && !dip.kok) {
      dip = dip.cocuk[0];
      zincir.push(dip.ad);
    }
    // Satır zincirin TEPESİNİ açar: başlıkta raydaki adın aynısı yazsın
    // (dibi açınca üst satıra basıp alt klasör başlığı görülüyordu).
    // Alt ağaç dahilken içerik aynıdır; zincirin hiçbir halkasında doğrudan dosya yok.
    var satirDugum = dip === n ? n : {
      id: n.id, ad: n.ad, zincir: zincir, toplam: n.toplam, cocuk: dip.cocuk,
      goreli: dip.goreli || n.goreli
    };
    var z = n;
    while (z) { _rayTemsil[z.id] = n.id; if (z === dip) break; z = z.cocuk[0]; }
    var ikon = dip.cocuk.length ? null : (derinlik === 1 ? 'i-klasor' : null);
    var acik = varsayilanAcik(dip, derinlik, toplam);
    kap.appendChild(raySatir(satirDugum, derinlik, ikon, dip.cocuk.length ? acik : null, enBuyuk));
    if (dip.cocuk.length) {
      var alt = el('div', 'gl-kl-alt');
      alt.dataset.ust = dip.id;
      alt.hidden = !acik;
      dip.cocuk.forEach(function (c) { dugumCiz(alt, c, derinlik + 1, enBuyuk, toplam); });
      kap.appendChild(alt);
    }
  }

  function varsayilanAcik(n, derinlik, toplam) {
    if (Object.prototype.hasOwnProperty.call(_rayAcik, n.id)) return !!_rayAcik[n.id];
    return derinlik === 1 && toplam > 0 && n.toplam >= toplam * 0.1;
  }

  function raySatir(n, derinlik, ikon, acik, enBuyuk) {
    var sat = el('div', 'gl-kl-sat' + (derinlik === 1 ? ' gl-ust-duzey' : ''));
    sat.style.paddingLeft = ((derinlik - 1) * 14) + 'px';
    if (acik !== null && acik !== undefined) {
      var ac = el('button', 'gl-kl-ac');
      ac.type = 'button';
      ac.dataset.ac = n.id;
      ac.setAttribute('aria-expanded', String(!!acik));
      ac.setAttribute('aria-label', n.ad + ' — alt klasörleri ' + (acik ? 'gizle' : 'göster'));
      ac.appendChild(svgIk('i-asagi'));
      sat.appendChild(ac);
    } else {
      var yer = el('span', 'gl-kl-ac-yer');
      if (ikon) yer.appendChild(svgIk(ikon));
      sat.appendChild(yer);
    }
    var b = el('button', 'gl-kl');
    b.type = 'button';
    b.dataset.kl = n.id;
    b.title = (n.goreli || n.ad) + ' · ' + fmt(n.toplam) + ' medya';
    var ad;
    if (n.zincir && n.zincir.length) {
      ad = el('span', 'gl-kl-ad', n.ad);
      ad.appendChild(el('span', 'gl-kl-zincir', ' / ' + n.zincir.join(' / ')));
    } else if ((n.ad || '').length > 16) {
      // Uzun ad İKİ SATIRA yayılır, baştaki yıl düşer (tam ad title'da):
      // "2026-09-26-…" satırları tek satırda birbirinin aynısı görünüyordu,
      // ayırt eden kısım adın ORTASI — kısaltma hiçbir uçtan kurtarmıyor.
      ad = el('span', 'gl-kl-ad gl-kl-uzun', n.ad.replace(/^20\d\d-(?=\d\d-\d\d-)/, ''));
    } else {
      ad = el('span', 'gl-kl-ad', n.ad);
    }
    b.appendChild(ad);
    var pay = el('span', 'gl-kl-pay');
    if (n.id && enBuyuk) {
      var i = document.createElement('i');
      i.style.width = Math.max(6, Math.sqrt((n.toplam || 0) / enBuyuk) * 100).toFixed(1) + '%';
      pay.appendChild(i);
    }
    b.appendChild(pay);
    b.appendChild(el('span', 'gl-d', fmt(n.toplam)));
    sat.appendChild(b);
    return sat;
  }

  function koklerCiz() {
    var kap = $('gl-kokler');
    kap.innerHTML = '';
    _durum.kokler.forEach(function (k) {
      var s = el('div', 'gl-kok-sat');
      s.appendChild(svgIk('i-klasor', 'gl-ik-k'));
      var ad = el('span', 'gl-kok-ad', 'kök: ' + k.ad);
      ad.title = k.yol || k.ad;
      s.appendChild(ad);
      var sil = el('button', 'gl-kok-sil');
      sil.type = 'button';
      sil.setAttribute('aria-label', '"' + k.ad + '" galeri listesinden çıkar (dosyalara dokunulmaz)');
      sil.title = 'Galeriden çıkar — dosyalara dokunulmaz';
      sil.appendChild(svgIk('i-kapat'));
      sil.addEventListener('click', function () { kokCikar(k); });
      s.appendChild(sil);
      kap.appendChild(s);
    });
  }

  async function kokCikar(k) {
    // 🔑 Salt okunur galeri: bu yalnız LİSTEDEN çıkarır, diske dokunmaz.
    if (!confirm('"' + k.ad + '" galeri listesinden çıkarılsın mı?\n(Dosyalara dokunulmaz.)')) return;
    try { await json('/kok/' + k.id, { method: 'DELETE' }); }
    catch (e) { duyur('Çıkarılamadı: ' + e.message); return; }
    if (_durum.seciliKok === k.id) _durum.seciliKok = null;
    await koklerYukle();
    await agacYukle();
    hepsiAc();
  }

  // ── Klasör seçici (kök ekleme) ──────────────────────────────────
  // Kapı sunucuda (`galeri_api._ekleme_kapisi`): ev + takılı diskler + izinli
  // kökler; gizli/sistem klasörü yok; yalnız bu bilgisayardan.
  function seciciSatir(metin, ikon, sag) {
    var b = el('button', 'gl-secici-satir');
    b.type = 'button';
    var sol = el('span');
    if (ikon) sol.appendChild(svgIk(ikon, 'gl-ik-k'));
    sol.appendChild(el('span', null, metin));
    b.appendChild(sol);
    if (sag) b.appendChild(svgIk('i-sag', 'gl-ik-k'));
    return b;
  }

  async function seciciAc(yol) {
    var d;
    try {
      d = await json('/gozat' + (yol ? '?yol=' + encodeURIComponent(yol) : ''));
    } catch (e) {
      if (!$('gl-secici').hidden) $('gl-secici-bilgi').textContent = 'Açılamadı: ' + e.message;
      else duyur('Klasör açılamadı: ' + e.message);
      return;
    }
    _durum.seciciYol = d.yol;
    modalAc('gl-secici');
    $('gl-secici-yol').textContent = d.yol;
    $('gl-secici-bilgi').textContent = fmt(d.medya) + ' medya dosyası burada';

    var liste = $('gl-secici-liste');
    liste.innerHTML = '';
    // Takılı diskler / izinli kökler en üstte: seçici ev dizininden başlar,
    // oraya çıkan başka yol yoktur.
    var diskler = d.diskler || [];
    if (diskler.length) {
      liste.appendChild(el('div', 'gl-secici-bolum', 'DİSKLER'));
      diskler.forEach(function (dk) {
        var db = seciciSatir(dk.ad, 'i-disk', true);
        db.title = dk.yol;
        db.addEventListener('click', function () { seciciAc(dk.yol); });
        liste.appendChild(db);
      });
      liste.appendChild(el('div', 'gl-secici-bolum', 'KLASÖRLER'));
    }
    if (d.ust) {
      var ust = seciciSatir('üst klasör', 'i-sol', false);
      ust.addEventListener('click', function () { seciciAc(d.ust); });
      liste.appendChild(ust);
    }
    d.klasorler.forEach(function (k) {
      var b = seciciSatir(k.ad, 'i-klasor', true);
      b.addEventListener('click', function () { seciciAc(k.yol); });
      liste.appendChild(b);
    });
    if (!d.klasorler.length && !d.ust && !diskler.length) {
      var bos = el('div', 'gl-bos-etiket', 'alt klasör yok');
      bos.style.padding = '12px';
      liste.appendChild(bos);
    }
  }

  async function seciliKlasoruEkle() {
    if (!_durum.seciciYol) return;
    try {
      await json('/kok', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ yol: _durum.seciciYol })
      });
    } catch (e) {
      $('gl-secici-bilgi').textContent = 'Eklenemedi: ' + e.message;
      return;
    }
    modalKapat('gl-secici');
    await koklerYukle();
    await agacYukle();
    hepsiAc();          // yeni klasör eklendi → hepsini göster, farkı görsün
  }

  /** Neredesin → altın (aria-current). Seçili düğümün ataları açılır. */
  function rayVurgula() {
    var hedef = _durum.mod === 'hepsi' ? '' : (_durum.mod === 'klasor' ? _durum.klasorId : null);
    if (hedef && _rayTemsil[hedef]) hedef = _rayTemsil[hedef];
    var bulundu = null;
    Array.prototype.forEach.call(document.querySelectorAll('#gl-ray-liste .gl-kl'), function (b) {
      var on = hedef !== null && b.dataset.kl === hedef;
      if (on) { b.setAttribute('aria-current', 'true'); bulundu = b; }
      else b.removeAttribute('aria-current');
    });
    if (!bulundu) return;
    // Atalar açık olsun — seçili satır katlanmış bir dalın içinde kalmasın
    var p = bulundu.parentNode;
    while (p && p !== $('gl-ray-liste')) {
      if (p.classList && p.classList.contains('gl-kl-alt') && p.hidden) {
        p.hidden = false;
        var ac = $('gl-ray-liste').querySelector('.gl-kl-ac[data-ac="' + p.dataset.ust + '"]');
        if (ac) ac.setAttribute('aria-expanded', 'true');
      }
      p = p.parentNode;
    }
    // Rayı kaydır (scrollIntoView DEĞİL — o bütün sekmeyi de kaydırır)
    var ray = $('gl-ray');
    var r = bulundu.getBoundingClientRect(), rr = ray.getBoundingClientRect();
    if (r.top < rr.top + 40 || r.bottom > rr.bottom - 40) ray.scrollTop += (r.top - rr.top) - rr.height / 3;
  }

  function rayBagla() {
    $('gl-ray-liste').addEventListener('click', function (e) {
      var ac = e.target.closest('.gl-kl-ac');
      if (ac) {
        var alt = $('gl-ray-liste').querySelector('.gl-kl-alt[data-ust="' + ac.dataset.ac + '"]');
        var yeni = ac.getAttribute('aria-expanded') !== 'true';
        ac.setAttribute('aria-expanded', String(yeni));
        if (alt) alt.hidden = !yeni;
        _rayAcik[ac.dataset.ac] = yeni;
        try { localStorage.setItem(RAY_ANAHTAR, JSON.stringify(_rayAcik)); } catch (er) {}
        return;
      }
      var b = e.target.closest('.gl-kl');
      if (!b) return;
      cekmece(null, false);
      if (!b.dataset.kl) hepsiAc();
      else klasorAc(b.dataset.kl);
    });
    $('gl-altklasor').addEventListener('click', function () {
      _durum.altklasor = !_durum.altklasor;
      ayarlariYaz();
      ayarUI();
      if (_durum.mod === 'klasor') tazele();
    });    $('gl-ekle').addEventListener('click', function () { cekmece(null, false); seciciAc(null); });
    $('gl-secici-kapat').addEventListener('click', function () { modalKapat('gl-secici'); });
    $('gl-secici-ekle').addEventListener('click', seciliKlasoruEkle);
  }

  /** Ray düğümünden kökten bu klasöre giden zincir (fiş kırıntısı için). */
  function yolZinciri(kid) {
    var z = [], n = _dugum[kid], tur = 0;
    while (n && tur++ < 20) { z.unshift(n); n = n.ust ? _dugum[n.ust] : null; }
    return z;
  }

  // ══ BAŞLIK ═══════════════════════════════════════════════════════════
  function baslikYaz() {
    var ad, sayi;
    if (_durum.mod === 'arama') {
      ad = 'Arama: ' + $('gl-ara').value.trim();
      sayi = fmt(_durum.dosyalar.length) + ' sonuç';
    } else {
      ad = _durum.mod === 'hepsi' ? 'Hepsi'
        : ((_dugum[_durum.klasorId] && _dugum[_durum.klasorId].ad) || _durum.klasorAd || 'Klasör');
      sayi = _durum.toplam || _durum.dosyalar.length ? fmt(_durum.toplam) + ' medya' : '';
    }
    $('gl-yol-ad').textContent = ad;
    $('gl-yol-sayi').textContent = sayi;
    $('gl-tel-ad').textContent = ad;
    $('gl-tel-sayi').textContent = _durum.mod === 'arama' ? fmt(_durum.dosyalar.length) : fmt(_durum.toplam);
    document.title = ad + ' · Galeri · Yuki';
  }

  // ══ AKIŞ ═════════════════════════════════════════════════════════════
  /* 🔴 İSTEK NESLİ — görünüm ayarları eklenince ortaya çıkan yarış koşulu.
   * Ölçüldü 2026-09-20: `tazele()` üst üste çağrıldığında ① `yukleniyor` hâlâ
   * true olduğu için yeni akış SESSİZCE başlamıyordu, ② önceki isteğin yanıtı
   * yeni temizlenmiş ızgaraya yazıyordu. Her görünüm değişimi nesli artırır;
   * nesli eskimiş yanıt ÇÖPE ATILIR. Aya atlama da yeni bir nesildir. */
  var _nesil = 0;

  function yeniNesil() {
    _durum.yukleniyor = false;      // eski akışın kilidi yeni görünümü bloklamasın
    return ++_nesil;
  }

  /** Listeyi `ofset`ten yeniden kur (0 = baştan). Açık fiş kapanır: indeksi
   * eski listeye aittir. */
  function akisSifirla(ofset) {
    if (!$('gl-buyuk').hidden) buyukKapat();
    _durum.dosyalar = [];
    _durum.offset = ofset;
    _durum.baslangic = ofset;
    _durum.bitti = false;
    izgaraTemizle();
    $('gl-icerik').scrollTop = 0;
    var y = $('gl-yeni-aylar');
    y.hidden = !(ofset > 0);
    $('gl-yeni-sayi').textContent = ofset > 0 ? fmt(ofset) : '';
  }

  async function hepsiAc() {
    yeniNesil();
    _durum.mod = 'hepsi';
    _durum.klasorId = null;
    _durum.klasorAd = null;
    _durum.seciliKok = null;
    $('gl-ara').value = '';
    akisSifirla(0);
    ayarUI();
    rayVurgula();
    baslikYaz();
    aylikYukle();
    await dahaGetir(true);
  }

  async function klasorAc(id) {
    yeniNesil();
    // 🔴 Klasör de SAYFALI çekilir (5.124 dosyalık klasörde tek istek 25,2 sn'ydi).
    _durum.mod = 'klasor';
    _durum.klasorId = id;
    _durum.klasorAd = null;
    if (_dugum[id] && _dugum[id].kok) _durum.seciliKok = id;
    $('gl-ara').value = '';
    akisSifirla(0);
    ayarUI();
    rayVurgula();
    baslikYaz();
    aylikYukle();
    await dahaGetir(true);
  }

  async function dahaGetir(ilk) {
    if (_durum.yukleniyor) return;
    var nesil = _nesil;

    // Arama sonucu tek seferde gelir (≤200) — yalnız ÇİZİM sayfalanır.
    if (_durum.mod === 'arama') {
      if (_durum.cizilen < _durum.dosyalar.length) {
        kartlariCiz(_durum.dosyalar.slice(_durum.cizilen, _durum.cizilen + SAYFA));
      }
      return;
    }
    if (_durum.bitti && !ilk) return;

    _durum.yukleniyor = true;
    try {
      var uc = (_durum.mod === 'klasor')
        ? '/liste?id=' + encodeURIComponent(_durum.klasorId) +
          '&offset=' + _durum.offset + '&limit=' + SAYFA + gorunumSorgu() +
          '&altklasor=' + (_durum.altklasor ? 1 : 0)
        : '/hepsi?offset=' + _durum.offset + '&limit=' + SAYFA + gorunumSorgu();
      var d = await json(uc);
      if (nesil !== _nesil) return;      // görünüm değişti — bu yanıt bayat
      if (_durum.mod === 'klasor') {
        _durum.klasorAd = d.ad || _durum.klasorAd;
        if (d.kok_mu) _durum.seciliKok = _durum.klasorId;
        _durum._altKlasorSayisi = ilk ? (d.klasorler || []).length : _durum._altKlasorSayisi;
      }
      _durum.dosyalar = _durum.dosyalar.concat(d.dosyalar);
      _durum.offset += d.dosyalar.length;
      _durum.toplam = d.toplam;
      _durum.bitti = d.bitti;
      kartlariCiz(d.dosyalar);
      baslikYaz();
      if (!d.dosyalar.length && ilk && !_durum.baslangic) bosAciklama();
      aktifAyIste();
    } catch (e) {
      if (nesil === _nesil) {
        bosGoster((_durum.mod === 'klasor' ? 'Klasör açılamadı: ' : 'Akış alınamadı: ') + metinKacis(e.message));
        _durum.bitti = true;
      }
    } finally {
      if (nesil === _nesil) { _durum.yukleniyor = false; sentinelAyarla(); }
    }
  }

  function metinKacis(s) {
    var d = document.createElement('div'); d.textContent = String(s); return d.innerHTML;
  }

  function bosAciklama() {
    if (_durum.mod === 'hepsi') {
      bosGoster('Hiçbir klasörde medya yok.<br><b>Kök klasör ekle</b> ile bir klasör ekle.');
      return;
    }
    if (_durum.tip) {
      bosGoster('Bu klasörde <b>' + (_durum.tip === 'video' ? 'video' : 'resim') + '</b> yok.');
      return;
    }
    if (!_durum.altklasor && _durum._altKlasorSayisi) {
      bosGoster('Bu klasörün kendi içinde medya yok — ' + _durum._altKlasorSayisi +
                ' alt klasörü var.<br>Raydaki <b>Alt klasörler dahil</b> anahtarını aç.');
      return;
    }
    var uz = _durum.uzantilar;
    bosGoster('Bu klasörde gösterilecek medya yok.<br>Taranan türler: <b>' +
              metinKacis(uz.resim.concat(uz.video).join(' ')) + '</b>');
  }

  function sentinelAyarla() {
    var s = $('gl-sentinel');
    var kalan = (_durum.mod === 'arama')
      ? _durum.cizilen < _durum.dosyalar.length
      : !_durum.bitti;
    s.hidden = !kalan;
    if (kalan) _sentinel.observe(s); else _sentinel.unobserve(s);
  }

  /** Görünüm ayarlarının sunucu sorgusu (sıralama + tür filtresi). */
  function gorunumSorgu() {
    return '&sirala=' + _durum.sirala +
           (_durum.yon ? '&yon=' + _durum.yon : '') +
           (_durum.tip ? '&tip=' + _durum.tip : '');
  }

  // ── Izgara (nehir) ──────────────────────────────────────────────
  function izgaraTemizle() {
    var iz = $('gl-izgara');
    iz.innerHTML = '';
    iz._gl = null;
    _durum.cizilen = 0;
    // Grup durumu da sıfırlanır — yoksa yeni görünüm eski ayın başlığının
    // altına akmaya devam eder.
    _durum.grupAktifKap = null;
    _durum.sonGrup = null;
    $('gl-bos').hidden = true;
    var gruplu = izgaraGruplu();
    iz.classList.toggle('gl-gruplu', gruplu);
    if (!gruplu) { kapKur(iz, true); _sutunGenislik = iz._gl.gen; }
  }

  function kartlariCiz(dosyalar) {
    if (!dosyalar.length) return;
    $('gl-bos').hidden = true;

    // ── Aylara göre gruplama ───────────────────────────────────────
    // 🔴 Yalnız sıralama TARİH iken anlamlı. Ada göre dizilmiş listeye tarih
    // başlığı koymak her kartta bir başlık üretir.
    if (izgaraGruplu()) {
      var parca = [];
      dosyalar.forEach(function (f) {
        var ay = ayAnahtari(f.tarih);
        if (ay !== _durum.sonGrup) {
          if (parca.length) { grubaCiz(parca); parca = []; }
          grupAc(ay);
          _durum.sonGrup = ay;
        }
        parca.push(f);
      });
      if (parca.length) grubaCiz(parca);
      sentinelAyarla();
      return;
    }

    var iz = $('gl-izgara');
    if (!iz._gl) kapKur(iz, true);
    grubaCiz(dosyalar);
    sentinelAyarla();
  }

  /** Bir öbek kartı O ANKİ kaba (nehir ya da grup nehri) çiz. */
  function grubaCiz(dosyalar) {
    var kap = aktifKap();
    if (!kap._gl) kapKur(kap, true);
    var st = kap._gl;
    var klasorKipi = _durum.mod === 'klasor';
    obek(st, function () {
      dosyalar.forEach(function (f) {
        var i = _durum.cizilen++;
        var kart = document.createElement('button');
        kart.className = 'gl-kart' + (i === _durum.acik ? ' gl-acik' : '');
        kart.type = 'button';
        kart.dataset.tip = f.tip;
        kart.dataset.i = i;
        kart.title = f.ad;

        // 🔴 Oran SUNUCUDAN: kutu daha resim inmeden doğru yüksekliği alır.
        var en = f.en || (f.tip === 'video' ? 16 : 1);
        var boy = f.boy || (f.tip === 'video' ? 9 : 1);
        var oran = en / boy;
        var og = Math.max(ORAN_ALT, oran);
        kart.style.aspectRatio = String(og);
        kart.dataset.oran = oran;            // kademe seçimi (sunucu oranı)
        kart.dataset.og = og;                // yerleştirme yüksekliği (gösterim oranı)

        var img = document.createElement('img');
        img.alt = f.ad;
        img.dataset.id = f.id;
        img.decoding = 'async';          // kod çözme ana iş parçacığını kilitlemesin
        kart.appendChild(img);
        _gozlemci.observe(img);
        // Video da küçük resim taşır (ffmpeg ilk kare). Üretilemezse rozet ortaya
        // gelir — rozet kaldırılmadı, YEDEĞE alındı.
        if (f.tip === 'video') {
          var rozet = el('span', 'gl-video-rozet');
          rozet.appendChild(svgIk('i-oynat'));
          kart.appendChild(rozet);
        }
        var isaret = el('span', 'gl-secim-isaret');
        isaret.appendChild(svgIk('i-onay'));
        kart.appendChild(isaret);
        // Etiket: klasör kipinde dosya adı, HEPSİ/aramada klasör adı (bilgi taşısın)
        kart.appendChild(el('span', 'gl-kart-ad', klasorKipi ? f.ad : (f.klasor || f.ad)));
        // Seçim kipi açıkken tık BÜYÜTMEZ, işaretler (kip şeritte açıkça görünür).
        kart.dataset.id = f.id;
        kart.dataset.kl = f.klasor_id || '';
        kart.addEventListener('click', function () {
          if (_kiyas.acik) kartSec(kart, f); else buyukAc(i);
        });
        yerlestir(st, kart);
      });
    });
  }

  function bosGoster(html) {
    izgaraTemizle();
    var b = $('gl-bos');
    b.innerHTML = html;
    b.hidden = false;
  }

  // ══ ZAMAN OMURGASI ═══════════════════════════════════════════════════
  var _aylikNesil = 0;

  function aylikAnahtar() {
    var q = [];
    if (_durum.mod === 'klasor') q.push('id=' + encodeURIComponent(_durum.klasorId),
                                        'altklasor=' + (_durum.altklasor ? 1 : 0));
    if (_durum.tip) q.push('tip=' + _durum.tip);
    if (_durum.yon) q.push('yon=' + _durum.yon);
    return q.join('&');
  }

  async function aylikYukle() {
    var n = ++_aylikNesil;
    if (_durum.mod === 'arama' || _durum.sirala !== 'tarih') {
      _durum.aylik = null;
      omurgaCiz();
      grupSayilariniYaz();
      return;
    }
    var anahtar = aylikAnahtar();
    var a = _durum.aylik;
    if (a && a.anahtar === anahtar && Date.now() - a.zaman < 30000) { omurgaCiz(); return; }

    var d = null, yedek = false;
    try {
      d = await json('/aylik' + (anahtar ? '?' + anahtar : ''));
    } catch (e) {
      // Eski backend: `/istatistik.aylik` yalnız HEPSİ + tür yok + yeniden eskiye
      // için ofset verebilir (ayların kümülatif toplamı). Başka süzgeçte omurga gizlenir.
      if (_durum.mod === 'hepsi' && !_durum.tip && _durum.yon !== 'artan') {
        try {
          var s = await json('/istatistik');
          var of = 0;
          d = { toplam: s.toplam, aylar: (s.aylik || []).slice().reverse().map(function (x) {
            var r = { ay: x.ay, sayi: x.sayi, ofset: of }; of += x.sayi; return r;
          }) };
          yedek = true;
        } catch (e2) { d = null; }
      }
    }
    if (n !== _aylikNesil) return;
    if (d && d.aylar && d.aylar.length) {
      var harita = {};
      d.aylar.forEach(function (x) { harita[x.ay] = x; });
      _durum.aylik = { anahtar: anahtar, zaman: Date.now(), toplam: d.toplam,
                       aylar: d.aylar, harita: harita, yedek: yedek,
                       artan: _durum.yon === 'artan' };
    } else {
      _durum.aylik = null;
    }
    omurgaCiz();
    grupSayilariniYaz();
  }

  /** Ardışık ay listesi (boş aylar dahil), listenin yönünde. */
  function tumAylar(a) {
    var ks = a.aylar.map(function (x) { return x.ay; }).sort();
    var bas = ks[0], son = ks[ks.length - 1];
    var y = +bas.slice(0, 4), m = +bas.slice(5), sy = +son.slice(0, 4), sm = +son.slice(5);
    var out = [], tur = 0;
    while ((y < sy || (y === sy && m <= sm)) && tur++ < 600) {
      out.push(y + '-' + iki(m));
      m++; if (m > 12) { m = 1; y++; }
    }
    return a.artan ? out : out.reverse();
  }

  function omurgaCiz() {
    var om = $('gl-omurga'), liste = $('gl-om-liste'), not = $('gl-om-not');
    var a = _durum.aylik;
    var tarihte = _durum.sirala === 'tarih' && _durum.mod !== 'arama';
    if (!a) {
      if (!tarihte && _durum.omurgaCizildi) {
        om.classList.add('gl-om-pasif');
        not.hidden = false;
        not.textContent = _durum.mod === 'arama' ? 'Aramada omurga yok' : 'Omurga tarih sırasında çalışır';
        return;
      }
      if (!document.body.classList.contains('gl-om-yok')) {
        document.body.classList.add('gl-om-yok');
        duzenTazeleBekle();
      }
      return;
    }
    om.classList.remove('gl-om-pasif');
    not.hidden = true;
    if (document.body.classList.contains('gl-om-yok')) {
      document.body.classList.remove('gl-om-yok');
      duzenTazeleBekle();
    }
    liste.innerHTML = '';
    var aylar = tumAylar(a);
    // Tek ay varken omurganın atlayacağı yer yok: telefonda altın başparmak ekranın ortasında
    // anlamsız bir turuncu çubuk olarak kalıyordu (goz 11-13). Dar düzen bu sınıfla çeker.
    document.body.classList.toggle('gl-om-tek', aylar.length < 2);
    var enCok = 1;
    a.aylar.forEach(function (x) { enCok = Math.max(enCok, x.sayi); });
    var yil = null;
    aylar.forEach(function (ay) {
      if (ay.slice(0, 4) !== yil) {
        yil = ay.slice(0, 4);
        liste.appendChild(el('div', 'gl-om-yil', yil));
      }
      var x = a.harita[ay], n = x ? x.sayi : 0, m = +ay.slice(5) - 1;
      var b = el('button', 'gl-om-ay' + (n ? '' : ' gl-om-bos'));
      b.type = 'button';
      b.dataset.ay = ay;
      b.setAttribute('aria-label', AYLAR[m] + ' ' + ay.slice(0, 4) + ' · ' + fmt(n) + ' medya');
      b.appendChild(el('span', 'gl-om-e', AYK[m]));
      var c = el('span', 'gl-om-c');
      var i = document.createElement('i');
      i.style.width = (n ? Math.max(6, Math.sqrt(n / enCok) * 100) : 0).toFixed(1) + '%';
      c.appendChild(i);
      b.appendChild(c);
      liste.appendChild(b);
    });
    _durum.omurgaCizildi = true;
    aktifAyIste();
  }

  var _aktifIstek = 0;
  function aktifAyIste() {
    if (_aktifIstek) return;
    _aktifIstek = requestAnimationFrame(function () { _aktifIstek = 0; aktifAyGuncelle(); });
  }

  function kartNoktada(y) {
    var r = $('gl-icerik').getBoundingClientRect();
    var xs = [r.left + 24, r.left + r.width / 2, r.right - 30];
    for (var j = 0; j < xs.length; j++) {
      var e = document.elementFromPoint(xs[j], y);
      var k = e && e.closest ? e.closest('.gl-kart') : null;
      if (k) return +k.dataset.i;
    }
    return null;
  }

  /** Bulunduğun ay (altın) + ekranda görünen aylar (parlak cyan). */
  function gorunenAylar() {
    var ic = $('gl-icerik');
    var r = ic.getBoundingClientRect();
    var gruplar = document.querySelectorAll('#gl-izgara > .gl-grup');
    var akt = null, gor = {};
    if (gruplar.length) {
      for (var i = 0; i < gruplar.length; i++) {
        var b = gruplar[i].getBoundingClientRect();
        if (b.top - r.top <= 72) akt = gruplar[i].dataset.ay;
        if (b.bottom > r.top + 4 && b.top < r.bottom) gor[gruplar[i].dataset.ay] = 1;
      }
      if (!akt) akt = gruplar[0].dataset.ay;
      return { akt: akt, gor: gor };
    }
    var ust = kartNoktada(r.top + 30), alt = kartNoktada(r.bottom - 30);
    if (ust == null && _durum.dosyalar.length) ust = 0;
    if (ust == null) return { akt: null, gor: gor };
    if (alt == null) alt = Math.min(_durum.dosyalar.length - 1, ust + 40);
    var a = Math.min(ust, alt), z = Math.max(ust, alt);
    for (var j = a; j <= z; j++) { var f = _durum.dosyalar[j]; if (f) gor[ayAnahtari(f.tarih)] = 1; }
    var fu = _durum.dosyalar[ust];
    return { akt: fu ? ayAnahtari(fu.tarih) : null, gor: gor };
  }

  function aktifAyGuncelle() {
    if (!_durum.aylik || $('gl-omurga').classList.contains('gl-om-pasif')) return;
    var g = gorunenAylar();
    var onEl = null;
    Array.prototype.forEach.call(document.querySelectorAll('#gl-om-liste .gl-om-ay'), function (b) {
      var on = b.dataset.ay === g.akt;
      if (on) { b.setAttribute('aria-current', 'true'); onEl = b; } else b.removeAttribute('aria-current');
      b.classList.toggle('gl-om-gorunur', !!g.gor[b.dataset.ay]);
    });
    var bp = $('gl-om-basparmak');
    if (onEl && !_basparmakSuruk) {
      bp.style.top = (onEl.offsetTop + onEl.offsetHeight / 2 - $('gl-om-liste').scrollTop) + 'px';
      // Omurga kendi içinde kayarsa (60+ ay) bulunduğun ay görünür kalsın
      var l = $('gl-om-liste');
      if (onEl.offsetTop < l.scrollTop || onEl.offsetTop > l.scrollTop + l.clientHeight - 20) {
        l.scrollTop = onEl.offsetTop - l.clientHeight / 3;
      }
    }
  }

  /** Omurgadan aya atla — HAFİF SÜRÜM.
   * Ay listede YÜKLÜYSE oraya kaydırılır. Değilse liste o ayın ofsetinden
   * yeniden kurulur (sunucu ofseti); üstte "↑ daha yeni aylar" çıkar. */
  function ayaAtla(ay) {
    var a = _durum.aylik;
    if (!a || _durum.sirala !== 'tarih' || _durum.mod === 'arama') return;
    var hedef = a.harita[ay];
    if (!hedef) {                           // boş ay → listenin yönünde sıradaki dolu ay
      var sonraki = a.aylar.filter(function (x) { return a.artan ? x.ay > ay : x.ay < ay; })[0];
      hedef = sonraki || a.aylar[a.aylar.length - 1];
    }
    ay = hedef.ay;
    if (hedef.ofset >= _durum.baslangic) {
      var sek = document.querySelector('#gl-izgara > .gl-grup[data-ay="' + ay + '"]');
      if (sek && sek.querySelector('.gl-kart')) {
        $('gl-icerik').scrollTop = sek.offsetTop;
        aktifAyIste();
        return;
      }
      if (!izgaraGruplu()) {
        var i = _durum.dosyalar.findIndex(function (f) { return ayAnahtari(f.tarih) === ay; });
        var k = i >= 0 ? document.querySelector('.gl-kart[data-i="' + i + '"]') : null;
        if (k) { kartaKaydir(k, 12); aktifAyIste(); return; }
      }
    }
    yeniNesil();
    akisSifirla(hedef.ofset);
    dahaGetir(true);
  }

  function ayKomsu(yon) {
    var a = _durum.aylik;
    if (!a) return;
    var g = gorunenAylar();
    var i = a.aylar.findIndex(function (x) { return x.ay === g.akt; });
    var j = i + yon;
    if (i < 0) j = 0;
    if (a.aylar[j]) ayaAtla(a.aylar[j].ay);
  }

  function balonGoster(ay, x, y) {
    var a = _durum.aylik;
    var b = $('gl-balon');
    var n = a && a.harita[ay] ? a.harita[ay].sayi : 0;
    b.textContent = '';
    b.appendChild(document.createTextNode(ayAdi(ay).toLocaleUpperCase('tr') + ' ' + ay.slice(0, 4) + ' · '));
    b.appendChild(el('span', 'gl-d', fmt(n)));
    b.style.left = Math.max(8, x - b.offsetWidth) + 'px';
    b.style.top = (y - b.offsetHeight / 2) + 'px';
    b.classList.add('gl-acik');
  }
  function balonGizle() { $('gl-balon').classList.remove('gl-acik'); }

  function ayYdeki(y) {
    var sat = document.querySelectorAll('#gl-om-liste .gl-om-ay');
    var en = null, fark = Infinity;
    for (var i = 0; i < sat.length; i++) {
      var r = sat[i].getBoundingClientRect();
      var f = Math.abs((r.top + r.height / 2) - y);
      if (f < fark) { fark = f; en = sat[i]; }
    }
    return en;
  }

  var _basparmakSuruk = false;
  function omurgaBagla() {
    var om = $('gl-omurga');
    var liste = $('gl-om-liste');
    liste.addEventListener('mousemove', function (e) {
      var b = e.target.closest('.gl-om-ay');
      if (!b) { balonGizle(); return; }
      var r = b.getBoundingClientRect();
      balonGoster(b.dataset.ay, r.left - 10, r.top + r.height / 2);
    });
    liste.addEventListener('mouseleave', balonGizle);
    liste.addEventListener('click', function (e) {
      var b = e.target.closest('.gl-om-ay');
      if (b) { balonGizle(); ayaAtla(b.dataset.ay); }
    });
    liste.addEventListener('scroll', aktifAyIste, { passive: true });

    // Telefon: tek dokunma hedefi altın başparmak — sürükle, bırakınca o aya git
    var bp = $('gl-om-basparmak');
    var secili = null;
    bp.addEventListener('pointerdown', function (e) {
      _basparmakSuruk = true;
      try { bp.setPointerCapture(e.pointerId); } catch (er) {}
      e.preventDefault();
    });
    bp.addEventListener('pointermove', function (e) {
      if (!_basparmakSuruk) return;
      var r = om.getBoundingClientRect();
      var y = Math.max(r.top, Math.min(r.bottom, e.clientY));
      bp.style.top = (y - r.top) + 'px';
      secili = ayYdeki(y);
      if (secili) balonGoster(secili.dataset.ay, r.left - 52, y);
    });
    function birak() {
      if (!_basparmakSuruk) return;
      _basparmakSuruk = false;
      balonGizle();
      if (secili) ayaAtla(secili.dataset.ay);
      secili = null;
      aktifAyIste();
    }
    bp.addEventListener('pointerup', birak);
    bp.addEventListener('pointercancel', birak);
    bp.addEventListener('keydown', function (e) {
      if (e.key === 'ArrowUp') { ayKomsu(-1); e.preventDefault(); }
      else if (e.key === 'ArrowDown') { ayKomsu(1); e.preventDefault(); }
    });

    $('gl-icerik').addEventListener('scroll', aktifAyIste, { passive: true });
    $('gl-yeni-aylar').addEventListener('click', function () {
      yeniNesil();
      akisSifirla(0);
      dahaGetir(true);
    });
  }

  // ══ İNDİRME BAĞLANTISI ══════════════════════════════════════════════
  /* 🔴 İndirme gerçek bir `<a href>` ile yapılır, blob + programatik tıklama
   *    ile DEĞİL: mobil tarayıcı `await`ten sonra JS'in ürettiği tıklamayı
   *    engelleyebilir; 200 MB'lık videoyu belleğe çekmek K4'ün tersi.
   * 🔴 `<a>` de `Authorization` GÖNDEREMEZ → yetkiyi BİLET taşır (video
   *    oynatmanın kapısının aynısı; beş katman `/akis` içinde yine koşar).
   * 🔴 Hükmü SUNUCU verir (`?indir=1` → `Content-Disposition: attachment`).
   * ⚠️ Bilet dokunulmazsa 5 dk'da düşer; fiş açık kaldıkça tazelenir. */
  var _indirZaman = null;

  function indirGizle() {
    if (_indirZaman) { clearInterval(_indirZaman); _indirZaman = null; }
    var a = $('gl-indir');
    a.hidden = true;
    a.removeAttribute('href');
    a.removeAttribute('download');
  }

  function indirKur(i, f) {
    var a = $('gl-indir');
    function tazele() {
      return json('/bilet/' + f.id).then(function (b) {
        if (_durum.acik !== i) return;
        a.href = b.url + '?indir=1';
        a.download = f.ad;
        a.title = f.ad + ' — indir';
        a.hidden = false;
      });
    }
    // Bilet alınamazsa düğme HİÇ görünmez — çalışmayan düğme, olmayan düğmeden kötüdür.
    tazele().then(function () {
      if (_durum.acik !== i || a.hidden) return;
      _indirZaman = setInterval(function () {
        if (_durum.acik !== i) { indirGizle(); return; }
        tazele().catch(function () {});
      }, 240000);                       // bilet ömrü 300 sn (BILET_OMUR)
    }).catch(function () {});
  }

  // ══ ZOOM / KAYDIRMA ═════════════════════════════════════════════════
  /* 🔴 `transform: scale()` kullanılır, `width` DEĞİL (kompozitörde koşar).
   * 🔴 VİDEODA ZOOM YOK — `controls` şeridinin ileri sarmasını yutardı.
   * 🔑 Fişte tekerlek fişi KAYDIRIR (belge okunuyor); tekerlekle yakınlaştırma
   *    tam kipte ya da Ctrl ile. Tuşlar (+ − 0) iki kipte de çalışır. */
  var ZOOM_MIN = 1, ZOOM_MAX = 8;
  var _z = { k: 1, x: 0, y: 0, suruk: null };

  function zoomSifirla() {
    _z.k = 1; _z.x = 0; _z.y = 0;
    var sahne = $('gl-sahne');
    sahne.classList.remove('gl-zoomlu', 'gl-suruk');
    var img = sahne.querySelector('img');
    if (img) img.style.transform = '';
    $('gl-zoom-rozet').hidden = true;
  }

  function zoomUygula() {
    var sahne = $('gl-sahne');
    var img = sahne.querySelector('img');
    if (!img) return;
    // Kaydırma payı sınırlı: kullanıcı resmi ekrandan tamamen kaçıramasın.
    var r = sahne.getBoundingClientRect();
    var pay = Math.max(0, (_z.k - 1) / 2);
    var sinirX = r.width * pay, sinirY = r.height * pay;
    _z.x = Math.max(-sinirX, Math.min(sinirX, _z.x));
    _z.y = Math.max(-sinirY, Math.min(sinirY, _z.y));
    img.style.transform = 'translate(' + _z.x + 'px,' + _z.y + 'px) scale(' + _z.k + ')';
    sahne.classList.toggle('gl-zoomlu', _z.k > 1);
    var rozet = $('gl-zoom-rozet');
    rozet.hidden = _z.k <= 1;
    rozet.textContent = '%' + Math.round(_z.k * 100);
  }

  function zoomEt(carpan, merkezX, merkezY) {
    var sahne = $('gl-sahne');
    if (!sahne.querySelector('img')) return;         // video → zoom yok
    var eski = _z.k;
    _z.k = Math.max(ZOOM_MIN, Math.min(ZOOM_MAX, _z.k * carpan));
    if (_z.k === eski) return;
    if (_z.k === 1) { _z.x = 0; _z.y = 0; }
    else if (merkezX != null) {
      // İmlecin altındaki nokta yerinde kalsın — sabit noktalı yakınlaştırma.
      var r = sahne.getBoundingClientRect();
      var dx = merkezX - (r.left + r.width / 2);
      var dy = merkezY - (r.top + r.height / 2);
      var o = _z.k / eski;
      _z.x = dx - (dx - _z.x) * o;
      _z.y = dy - (dy - _z.y) * o;
    }
    zoomUygula();
  }

  function tamKipte() { return $('gl-buyuk').classList.contains('gl-tam'); }

  function zoomBagla() {
    var sahne = $('gl-sahne');

    sahne.addEventListener('wheel', function (e) {
      if (!sahne.querySelector('img')) return;
      if (!tamKipte() && !e.ctrlKey && _z.k <= 1) return;   // fişte tekerlek kaydırır
      e.preventDefault();
      zoomEt(e.deltaY < 0 ? 1.15 : 1 / 1.15, e.clientX, e.clientY);
    }, { passive: false });

    sahne.addEventListener('dblclick', function (e) {
      if (!tamKipte()) { tamCevir(true); return; }          // fişte çift tık = büyüt
      if (!sahne.querySelector('img')) return;
      if (_z.k > 1) zoomSifirla(); else zoomEt(3, e.clientX, e.clientY);
    });

    sahne.addEventListener('mousedown', function (e) {
      if (_z.k <= 1 || !sahne.querySelector('img')) return;
      e.preventDefault();                 // tarayıcının kendi resim sürüklemesi
      _z.suruk = { x: e.clientX, y: e.clientY, bx: _z.x, by: _z.y };
      sahne.classList.add('gl-suruk');
    });
    // 🔴 mousemove/up PENCEREDE dinlenir: sahnede dinlenseydi imleç dışarı
    // çıkınca sürükleme takılı kalırdı.
    window.addEventListener('mousemove', function (e) {
      if (!_z.suruk) return;
      _z.x = _z.suruk.bx + (e.clientX - _z.suruk.x);
      _z.y = _z.suruk.by + (e.clientY - _z.suruk.y);
      zoomUygula();
    });
    window.addEventListener('mouseup', function () {
      _z.suruk = null;
      $('gl-sahne').classList.remove('gl-suruk');
    });

    // ── Dokunma: iki parmak yakınlaştırma + tek parmak kaydırma ──
    var _pinch = 0, _tek = null;
    sahne.addEventListener('touchstart', function (e) {
      if (!sahne.querySelector('img')) return;
      if (e.touches.length === 2) {
        _pinch = Math.hypot(e.touches[0].clientX - e.touches[1].clientX,
                            e.touches[0].clientY - e.touches[1].clientY);
        _tek = null;
      } else if (e.touches.length === 1 && _z.k > 1) {
        _tek = { x: e.touches[0].clientX, y: e.touches[0].clientY, bx: _z.x, by: _z.y };
      }
    }, { passive: true });

    sahne.addEventListener('touchmove', function (e) {
      if (!sahne.querySelector('img')) return;
      if (e.touches.length === 2 && _pinch) {
        e.preventDefault();
        var d = Math.hypot(e.touches[0].clientX - e.touches[1].clientX,
                           e.touches[0].clientY - e.touches[1].clientY);
        zoomEt(d / _pinch,
               (e.touches[0].clientX + e.touches[1].clientX) / 2,
               (e.touches[0].clientY + e.touches[1].clientY) / 2);
        _pinch = d;
      } else if (e.touches.length === 1 && _tek && _z.k > 1) {
        // ⚠️ Yalnız zoomluyken parmak hareketi yutulur; 1× iken sayfanın kendi davranışı.
        e.preventDefault();
        _z.x = _tek.bx + (e.touches[0].clientX - _tek.x);
        _z.y = _tek.by + (e.touches[0].clientY - _tek.y);
        zoomUygula();
      }
    }, { passive: false });

    sahne.addEventListener('touchend', function (e) {
      if (e.touches.length < 2) _pinch = 0;
      if (!e.touches.length) _tek = null;
    }, { passive: true });
  }

  // ══ SLAYT GÖSTERİSİ ════════════════════════════════════════════════
  /* Hız localStorage'da kalır. Fiş kapalıyken başlatılırsa ilk dosyadan
   * açar — "slayt" bir gezinme değil, bir GÖSTERİM kipidir. */
  var HIZLAR = [2000, 3000, 5000, 10000];
  var _slayt = { zaman: null, hiz: 3000 };

  function hizKur() {
    try {
      var h = parseInt(localStorage.getItem('galeriSlaytHiz'), 10);
      if (HIZLAR.indexOf(h) >= 0) _slayt.hiz = h;
    } catch (e) {}
    var kap = $('gl-hiz');
    kap.innerHTML = '';
    HIZLAR.forEach(function (ms) {
      var b = document.createElement('button');
      b.className = 'gl-hiz-btn';
      b.type = 'button';
      b.textContent = (ms / 1000) + ' sn';
      b.setAttribute('aria-pressed', String(ms === _slayt.hiz));
      b.addEventListener('click', function () {
        _slayt.hiz = ms;
        try { localStorage.setItem('galeriSlaytHiz', String(ms)); } catch (e) {}
        Array.prototype.forEach.call(kap.children, function (x) {
          x.setAttribute('aria-pressed', String(x === b));
        });
        if (_slayt.zaman) { slaytDur(); slaytBaslat(); }   // yeni hız hemen geçsin
      });
      kap.appendChild(b);
    });
  }

  function slaytDugme(acik) {
    var b = $('gl-slayt-btn');
    b.setAttribute('aria-pressed', String(acik));
    b.querySelector('use').setAttribute('href', acik ? '#i-durdur' : '#i-oynat');
    b.querySelector('span').textContent = acik ? 'DURDUR' : 'SLAYT';
  }

  function slaytBaslat() {
    if (!_durum.dosyalar.length) return;
    if (_durum.acik < 0) buyukAc(0);
    _slayt.zaman = setInterval(function () { gez(1); }, _slayt.hiz);
    slaytDugme(true);
  }

  function slaytDur() {
    if (_slayt.zaman) { clearInterval(_slayt.zaman); _slayt.zaman = null; }
    slaytDugme(false);
  }

  function slaytCevir() { if (_slayt.zaman) slaytDur(); else slaytBaslat(); }

  // ══ TAM KİP + TAM EKRAN ════════════════════════════════════════════
  /* Tam kip = sahne bütün pencere (bugünkü büyük görünüm). Tam ekran =
   * tarayıcının `requestFullscreen`'i — galeri bir IFRAME'de koşar, orada yalnız
   * `allowfullscreen` varsa çalışır (var, ölçüldü 2026-09-20). Hata yutulmaz. */
  function tamCevir(ac) {
    var b = $('gl-buyuk');
    if (b.hidden) return;
    if (ac === undefined) ac = !b.classList.contains('gl-tam');
    b.classList.toggle('gl-tam', ac);
    zoomSifirla();
    var btn = $('gl-buyut-btn');
    btn.querySelector('use').setAttribute('href', ac ? '#i-kucuk' : '#i-tam');
    btn.setAttribute('aria-label', ac ? 'Fişe dön' : 'Büyüt — tüm pencere');
    btn.title = ac ? 'Fişe dön' : 'Büyüt';
    if (!ac && document.fullscreenElement && document.exitFullscreen) {
      document.exitFullscreen().catch(function () {});
    }
  }

  function tamEkranCevir() {
    var d = document;
    if (!d.fullscreenElement) {
      tamCevir(true);
      (d.documentElement.requestFullscreen
        ? d.documentElement.requestFullscreen()
        : Promise.reject(new Error('desteklenmiyor'))
      ).catch(function () { duyur('Tam ekran bu pencerede açılamadı.'); });
    } else if (d.exitFullscreen) {
      d.exitFullscreen().catch(function () {});
    }
  }

  // ══ FİŞ — büyük görünüm ═════════════════════════════════════════════
  function bayt(n) {
    if (!n && n !== 0) return '—';
    var b = ['B', 'KB', 'MB', 'GB', 'TB'], i = 0;
    while (n >= 1024 && i < b.length - 1) { n /= 1024; i++; }
    return (i ? n.toLocaleString('tr-TR', { maximumFractionDigits: n < 10 ? 1 : 0 }) : n) + ' ' + b[i];
  }

  function tarihStr(ts) {
    if (!ts) return '—';
    try { return new Date(ts * 1000).toLocaleString('tr-TR', { dateStyle: 'medium', timeStyle: 'short' }); }
    catch (e) { return '—'; }
  }

  function acikKartIsaretle(i) {
    Array.prototype.forEach.call(document.querySelectorAll('.gl-kart.gl-acik'), function (k) {
      k.classList.remove('gl-acik');
    });
    if (i < 0) return;
    var k = document.querySelector('.gl-kart[data-i="' + i + '"]');
    if (k) k.classList.add('gl-acik');
  }

  /** Kartı kaydırma kabında görünür yap (scrollIntoView DEĞİL — o, overflow
   * gizli ataları da kaydırır ve bütün sekme kayar; defter dersi). */
  function kartaKaydir(k, ust) {
    var ic = $('gl-icerik');
    var r = k.getBoundingClientRect(), ir = ic.getBoundingClientRect();
    ic.scrollTop += (r.top - ir.top) - (ust == null ? (ir.height - r.height) / 3 : ust + 64);
  }

  function acikKartiGoster() {
    if (_durum.acik < 0) return;
    var k = document.querySelector('.gl-kart[data-i="' + _durum.acik + '"]');
    if (!k) return;
    var r = k.getBoundingClientRect(), ir = $('gl-icerik').getBoundingClientRect();
    if (r.bottom < ir.top + 60 || r.top > ir.bottom - 40) kartaKaydir(k);
  }

  function fisDoldur(f, i) {
    var sayac = $('gl-fis-sayac');
    sayac.textContent = '· ';
    sayac.appendChild(el('span', 'gl-d', fmt(_durum.baslangic + i + 1)));
    sayac.appendChild(document.createTextNode(' / ' + fmt(_durum.mod === 'arama' ? _durum.dosyalar.length : (_durum.toplam || _durum.dosyalar.length))));

    // Kırıntı: kökten klasöre; her parça o klasörü açar (ağaç yoksa yalnız ad)
    var yol = $('gl-fis-yol');
    yol.innerHTML = '';
    var zincir = f.klasor_id ? yolZinciri(f.klasor_id) : [];
    if (zincir.length) {
      zincir.forEach(function (n, j) {
        if (j) yol.appendChild(svgIk('i-sag'));
        var b = el('button', null, n.ad);
        b.type = 'button';
        b.title = n.ad + ' klasörünü aç';
        b.addEventListener('click', function () { klasorAc(n.id); });
        yol.appendChild(b);
      });
    } else if (f.klasor) {
      yol.appendChild(el('span', null, f.klasor));
    }
    $('gl-fis-ad').textContent = f.ad;

    var kv = $('gl-fis-kv');
    kv.innerHTML = '';
    function satir(ad, deger, sinif) {
      kv.appendChild(el('dt', null, ad));
      var dd = el('dd', sinif || null, deger);
      kv.appendChild(dd);
    }
    satir('Tarih', tarihStr(f.tarih));
    satir('Ölçü', f.en && f.boy ? fmt(f.en) + ' × ' + fmt(f.boy) : '—', f.en ? 'gl-d' : 'gl-yok');
    satir('Boyut', bayt(f.boyut), 'gl-d');
    var uz = (f.ad.split('.').pop() || '').toLocaleUpperCase('tr');
    satir('Tür', uz + (f.tip === 'video' ? ' · video' : ''));
    // Eklenti kancası (ör. galeri-guvenli.js): fiş her dolduğunda haber ver. Bu dosya diske yazmaz.
    try { window.dispatchEvent(new CustomEvent('yuki-galeri-fis', { detail: { id: f.id } })); } catch (e) {}
  }

  function komsuCiz(f, i) {
    var kap = $('gl-komsu-sira');
    kap.innerHTML = '';
    var ayni = function (x) { return f.klasor_id ? x.klasor_id === f.klasor_id : x.klasor === f.klasor; };
    var sec = [], L = _durum.dosyalar;
    // Baktığın karenin KOMŞULARI — önce en yakınlar, iki yöne açılarak
    for (var d = 1; sec.length < 6 && (i - d >= 0 || i + d < L.length); d++) {
      if (L[i + d] && ayni(L[i + d])) sec.push(i + d);
      if (sec.length < 6 && L[i - d] && ayni(L[i - d])) sec.push(i - d);
      if (d > 400) break;
    }
    $('gl-komsu').hidden = !sec.length;
    if (!sec.length) return;
    var n = f.klasor_id && _dugum[f.klasor_id] ? _dugum[f.klasor_id].sayi : null;
    $('gl-komsu-sayi').textContent = n ? sec.length + ' / ' + fmt(n) : '';
    $('gl-komsu-bas').textContent = 'Aynı klasörden';
    sec.sort(function (a, b) { return a - b; }).forEach(function (j) {
      var x = L[j];
      var b = el('button');
      b.type = 'button';
      b.title = x.ad;
      b.setAttribute('aria-label', x.ad + ' — fişte aç');
      var img = document.createElement('img');
      img.alt = '';
      kucukBas(img, x.id, 200);
      b.appendChild(img);
      b.addEventListener('click', function () { buyukAc(j); });
      kap.appendChild(b);
    });
  }

  async function buyukAc(i) {
    var f = _durum.dosyalar[i];
    if (!f) return;
    var ilk = $('gl-buyuk').hidden;
    _durum.acik = i;
    indirGizle();                        // önceki dosyanın bileti bu dosyayı AÇMAZ
    indirKur(i, f);                      // medya yüklemesini bekletme — paralel koşsun
    zoomSifirla();                       // yeni dosya 1x'te açılır
    var kutu = $('gl-buyuk');
    var sahne = $('gl-sahne');
    kutu.hidden = false;
    document.body.classList.add('gl-fis-acik');
    acikKartIsaretle(i);
    fisDoldur(f, i);
    komsuCiz(f, i);
    if (!$('gl-exif').hidden) exifYukle(f);   // panel açıksa künye de ilerlesin
    if (ilk) { $('gl-fis-gov').scrollTop = 0; setTimeout(acikKartiGoster, 180); }
    else acikKartiGoster();

    var v0 = sahne.querySelector('video');
    if (v0) { try { v0.pause(); v0.removeAttribute('src'); v0.load(); } catch (e) {} }
    sahne.innerHTML = '<span class="gl-bos-etiket">yükleniyor…</span>';
    try {
      if (f.tip === 'video') {
        // 🔴 Bilet: `<video src>` auth başlığı gönderemez, blob da olamaz.
        var b = await json('/bilet/' + f.id);
        if (_durum.acik !== i) return;            // kullanıcı bu arada ilerlediyse
        sahne.innerHTML = '';
        var v = document.createElement('video');
        v.src = b.url;
        v.controls = true; v.autoplay = true; v.playsInline = true;
        sahne.appendChild(v);
      } else {
        var u = await medyaUrl('b:' + f.id, '/dosya/' + f.id);
        if (_durum.acik !== i) return;
        _acikBlob = u;                      // havuz temizliği bunu atlasın
        sahne.innerHTML = '';
        var img = document.createElement('img');
        img.src = u; img.alt = f.ad;
        sahne.appendChild(img);
      }
    } catch (e) {
      sahne.innerHTML = '';
      sahne.appendChild(el('span', 'gl-bos-etiket', 'açılamadı: ' + e.message));
    }
  }

  // Dış betiklere salt-okunur köprü: açık dosya, tazele, fişi kapat.
  window.yukiGaleri = {
    acikDosya: function () { return _durum.acik >= 0 && !$('gl-buyuk').hidden ? _durum.dosyalar[_durum.acik] || null : null; },
    yenile: function () { tazele(); },
    kapat: function () { buyukKapat(); }
  };

  function buyukKapat() {
    var sahne = $('gl-sahne');
    // ⚠️ Video durdurulmalı: kapatılan kaplamada oynayan video CPU/GPU yakar.
    var v = sahne.querySelector('video');
    if (v) { try { v.pause(); v.removeAttribute('src'); v.load(); } catch (e) {} }
    sahne.innerHTML = '';
    var b = $('gl-buyuk');
    b.hidden = true;
    b.classList.remove('gl-tam');
    $('gl-buyut-btn').querySelector('use').setAttribute('href', '#i-tam');
    document.body.classList.remove('gl-fis-acik');
    if (document.fullscreenElement && document.exitFullscreen) document.exitFullscreen().catch(function () {});
    acikKartIsaretle(-1);
    _durum.acik = -1;
    _acikBlob = null;
    indirGizle();                        // tazeleme timer'ı kapalı görünümde koşmasın
    slaytDur();                          // görünmeyen slayt arkadan dönmesin
    zoomSifirla();
    exifKapat();
  }

  async function gez(adim) {
    if (_durum.acik < 0) return;
    var hedef = _durum.acik + adim;
    // Akışın sonuna gelindiyse bir sayfa daha çek (yoksa 120. resimde duvar).
    if (hedef >= _durum.dosyalar.length && _durum.mod !== 'arama' && !_durum.bitti) {
      await dahaGetir();
    }
    var n = _durum.dosyalar.length;
    if (!n) return;
    buyukAc((hedef + n) % n);
  }

  // ══ ARAMA ═══════════════════════════════════════════════════════════
  var _aramaZaman = null;

  function aramaYap(q) {
    var nesil = yeniNesil();
    // ⚠️ Tür filtresi aramada da geçerli — bir yerde çalışıp bir yerde
    // çalışmayan filtre, filtre değildir.
    return json('/bul?ara=' + encodeURIComponent(q) + '&limit=200' +
                (_durum.tip ? '&tip=' + _durum.tip : '')).then(function (d) {
      if (nesil !== _nesil) return;        // görünüm değişti — bayat sonuç
      _durum.mod = 'arama';
      akisSifirla(0);
      _durum.dosyalar = d.sonuc;
      _durum.bitti = true;
      _durum.toplam = d.sonuc.length;
      ayarUI();
      rayVurgula();
      baslikYaz();
      aylikYukle();
      izgaraTemizle();
      if (!d.sonuc.length) bosGoster('"' + metinKacis(q) + '" ile eşleşen medya yok.');
      else kartlariCiz(d.sonuc.slice(0, SAYFA));
      sentinelAyarla();
      aktifAyIste();
    }).catch(function (err) { bosGoster('Arama başarısız: ' + metinKacis(err.message)); });
  }

  function aramaBagla() {
    $('gl-ara').addEventListener('input', function (e) {
      var q = e.target.value.trim();
      clearTimeout(_aramaZaman);
      _aramaZaman = setTimeout(function () {
        if (!q) {
          if (_durum.mod === 'arama') hepsiAc();
          return;
        }
        aramaYap(q);
      }, 220);
    });
    $('gl-ara-ac').addEventListener('click', function () {
      document.body.classList.add('gl-ara-acik');
      setTimeout(function () { $('gl-ara').focus(); }, 30);
    });
    $('gl-ara-kapat').addEventListener('click', function () {
      document.body.classList.remove('gl-ara-acik');
      if ($('gl-ara').value) { $('gl-ara').value = ''; if (_durum.mod === 'arama') hepsiAc(); }
    });
  }

  // ══ GÖRÜNÜM AYARLARI — sıralama · tür · gruplama · alt klasör ═════
  /* 🔑 Tercihler localStorage'da kalır. Anahtar adı `galeriGorunum` SABİT;
   *    içinde sürüm alanı var (`v:2`). v2'den eski kayıtta `grupla` ve
   *    `altklasor` ARŞİV varsayılanına (açık) geçer — eski kapalı değer
   *    taşınsaydı kullanıcının tarayıcısında ay başlıkları hiç görünmezdi. */
  var AYAR_ANAHTAR = 'galeriGorunum';
  var AYAR_SURUM = 2;

  function ayarlariOku() {
    try {
      var d = JSON.parse(localStorage.getItem(AYAR_ANAHTAR) || '{}');
      if (['tarih', 'ad', 'boyut', 'tip'].indexOf(d.sirala) >= 0) _durum.sirala = d.sirala;
      if (['artan', 'azalan', ''].indexOf(d.yon) >= 0) _durum.yon = d.yon || '';
      if (['', 'resim', 'video'].indexOf(d.tip) >= 0) _durum.tip = d.tip || '';
      if (d.v === AYAR_SURUM) {
        _durum.grupla = !!d.grupla;
        _durum.altklasor = !!d.altklasor;
      }
    } catch (e) {}
  }

  function ayarlariYaz() {
    try {
      localStorage.setItem(AYAR_ANAHTAR, JSON.stringify({
        v: AYAR_SURUM,
        sirala: _durum.sirala, yon: _durum.yon, tip: _durum.tip,
        grupla: _durum.grupla, altklasor: _durum.altklasor
      }));
    } catch (e) {}
  }

  function segYaz(kapId, deger) {
    Array.prototype.forEach.call($(kapId).querySelectorAll('button'), function (b) {
      var on = b.dataset.deger === deger;
      b.setAttribute('aria-checked', String(on));
      b.tabIndex = on ? 0 : -1;
    });
  }

  function ayarUI() {
    $('gl-sirala').value = _durum.sirala;
    $('gl-tip').value = _durum.tip;
    segYaz('gl-sirala-seg', _durum.sirala);
    segYaz('gl-tip-seg', _durum.tip);
    // Yön oku ÖLÇÜYE göre okunur: tarihte ↓ "yeniden eskiye", adda ↓ "Z→A".
    var dogalTers = (_durum.sirala === 'tarih' || _durum.sirala === 'boyut');
    var ters = _durum.yon ? (_durum.yon === 'azalan') : dogalTers;
    var b = $('gl-yon');
    b.querySelector('use').setAttribute('href', ters ? '#i-sirala' : '#i-sirala-ters');
    b.title = 'Sıralama yönü — şu an ' + (ters ? 'azalan' : 'artan');
    b.setAttribute('aria-label', b.title);
    b.dataset.yon = ters ? 'azalan' : 'artan';
    var YON_AD = { tarih: ['Eskiden yeniye', 'Yeniden eskiye'], ad: ['A → Z', 'Z → A'],
                   boyut: ['Küçükten büyüğe', 'Büyükten küçüğe'], tip: ['A → Z', 'Z → A'] };
    b.querySelector('.gl-etiket').textContent = (YON_AD[_durum.sirala] || YON_AD.ad)[ters ? 1 : 0];
    $('gl-grupla').setAttribute('aria-pressed', String(_durum.grupla));
    // Aylara bölme yalnız tarih sıralamasında anlamlı → başka ölçüde pasif.
    $('gl-grupla').disabled = _durum.sirala !== 'tarih';
    $('gl-altklasor').setAttribute('aria-pressed', String(_durum.altklasor));
  }

  /** Ayar değişti → aynı görünümü baştan çiz (aynı klasör/akış, yeni sıra). */
  function tazele() {
    ayarlariYaz();
    ayarUI();
    if (_durum.mod === 'klasor' && _durum.klasorId) klasorAc(_durum.klasorId);
    else if (_durum.mod === 'arama') { var q = $('gl-ara').value.trim(); if (q) aramaYap(q); else hepsiAc(); }
    else hepsiAc();
  }

  function gorunumBagla() {
    ayarlariOku();
    ayarUI();
    $('gl-sirala').addEventListener('change', function (e) {
      _durum.sirala = e.target.value;
      _durum.yon = '';                    // yeni ölçü → doğal yönüne dön
      tazele();
    });
    $('gl-tip').addEventListener('change', function (e) {
      _durum.tip = e.target.value;
      tazele();
    });
    // Segment → gizli select'e yaz ve `change` ateşle (tek gerçek kaynak select)
    [['gl-sirala-seg', 'gl-sirala'], ['gl-tip-seg', 'gl-tip']].forEach(function (p) {
      var seg = $(p[0]);
      seg.addEventListener('click', function (e) {
        var b = e.target.closest('button');
        if (!b || $(p[1]).value === b.dataset.deger) return;
        $(p[1]).value = b.dataset.deger;
        $(p[1]).dispatchEvent(new Event('change'));
      });
      // Radyo grubu klavyesi: ← → seçer
      seg.addEventListener('keydown', function (e) {
        if (e.key !== 'ArrowLeft' && e.key !== 'ArrowRight') return;
        var bs = Array.prototype.slice.call(seg.querySelectorAll('button'));
        var i = bs.findIndex(function (x) { return x.getAttribute('aria-checked') === 'true'; });
        var j = Math.max(0, Math.min(bs.length - 1, i + (e.key === 'ArrowRight' ? 1 : -1)));
        if (j !== i) { bs[j].click(); bs[j].focus(); }
        e.preventDefault();
      });
    });
    $('gl-yon').addEventListener('click', function () {
      var dogalTers = (_durum.sirala === 'tarih' || _durum.sirala === 'boyut');
      var ters = _durum.yon ? (_durum.yon === 'azalan') : dogalTers;
      _durum.yon = ters ? 'artan' : 'azalan';
      tazele();
    });
    $('gl-grupla').addEventListener('click', function () {
      _durum.grupla = !_durum.grupla;
      tazele();
    });
    $('gl-yenile').addEventListener('click', yenile);
  }

  /** Yenile (R): kök sayıları + klasör ağacı + omurga + akış diskten. */
  async function yenile() {
    _durum.aylik = null;
    try { await koklerYukle(); await agacYukle(); } catch (e) {}
    tazele();
  }

  // ══ ÇEKMECELER (kompakt/telefon) ════════════════════════════════════
  function cekmece(ad, ac) {
    var ray = ad === 'ray' && ac, kontrol = ad === 'kontrol' && ac;
    if (ac && !KOMPAKT.matches) { ray = false; kontrol = false; }
    document.body.classList.toggle('gl-ray-acik', ray);
    document.body.classList.toggle('gl-kontrol-acik', kontrol);
    $('gl-perde').hidden = !(ray || kontrol);
    $('gl-ray-ac').setAttribute('aria-expanded', String(ray));
    $('gl-kontrol-ac').setAttribute('aria-expanded', String(kontrol));
    if (ray) rayVurgula();
  }

  function cekmeceBagla() {
    $('gl-ray-ac').addEventListener('click', function () { cekmece('ray', !document.body.classList.contains('gl-ray-acik')); });
    $('gl-ray-kapat').addEventListener('click', function () { cekmece(null, false); });
    $('gl-kontrol-ac').addEventListener('click', function () { cekmece('kontrol', !document.body.classList.contains('gl-kontrol-acik')); });
    $('gl-kontrol-kapat').addEventListener('click', function () { cekmece(null, false); });
    $('gl-perde').addEventListener('click', function () { cekmece(null, false); });
    // Sayfadaki araç satırına dokununca sayfa kapansın, araç açılsın
    $('gl-kontrol').addEventListener('click', function (e) {
      if (e.target.closest('.gl-arac') && KOMPAKT.matches) cekmece(null, false);
    });
    KOMPAKT.addEventListener('change', function () { cekmece(null, false); document.body.classList.remove('gl-ara-acik'); });
  }

  // ══════════════════════════════════════════════════════════════════
  // BİLGİ & KEŞİF (2026-09-20) — GalleryWeb'den taşınan yüzeyler.
  // Hepsi SALT OKUMA: bakarlar, sayarlar; hiçbiri diske yazmaz (K6).
  // ══════════════════════════════════════════════════════════════════

  var MODALLAR = ['gl-harita', 'gl-kopya', 'gl-stat', 'gl-yardim', 'gl-secici'];
  var MODAL_DUGME = { 'gl-harita': 'gl-harita-btn', 'gl-kopya': 'gl-kopya-btn', 'gl-stat': 'gl-stat-btn', 'gl-yardim': 'gl-yardim-btn' };

  function modalAc(id) {
    MODALLAR.forEach(function (m) { if (m !== id) $(m).hidden = true; });
    Object.keys(MODAL_DUGME).forEach(function (m) {
      $(MODAL_DUGME[m]).setAttribute('aria-pressed', String(m === id));
    });
    $(id).hidden = false;
  }

  function modalKapat(id) {
    $(id).hidden = true;
    Object.keys(MODAL_DUGME).forEach(function (m) { $(MODAL_DUGME[m]).setAttribute('aria-pressed', 'false'); });
  }

  function acikModal() {
    for (var i = 0; i < MODALLAR.length; i++) if (!$(MODALLAR[i]).hidden) return MODALLAR[i];
    return null;
  }

  /** Küçük resmi blob olarak bir <img>'e bas (kopya listesi, harita balonu, komşular).
   * 🔴 `<img src>` ile doğrudan API adresi YAZILAMAZ — `Authorization` gitmez, 401 döner. */
  function kucukBas(img, id, kenar) {
    medyaUrl('k' + kenar + ':' + id, '/kucuk/' + id + '?k=' + kenar)
      .then(function (u) { img.src = u; })
      .catch(function () { img.alt = '·'; });
  }

  // ── EXIF künyesi ────────────────────────────────────────────────
  /* Künye fişin İÇİNDE durur ve gezinmeyle birlikte ilerler: `buyukAc` panel
   * açıksa künyeyi tazeler. Tam kipte sağdan panel olur. */
  var EXIF_ETIKET = {
    Make: 'Marka', Model: 'Makine', LensModel: 'Objektif',
    DateTimeOriginal: 'Çekim', DateTime: 'Tarih',
    FNumber: 'Diyafram', ExposureTime: 'Pozlama', ISOSpeedRatings: 'ISO',
    FocalLength: 'Odak', FocalLengthIn35mmFilm: 'Odak (35mm)',
    Flash: 'Flaş', WhiteBalance: 'Beyaz ayarı', Orientation: 'Yön',
    Software: 'Yazılım', Artist: 'Çeken', Copyright: 'Telif',
    ExposureBiasValue: 'Pozlama telafisi', MeteringMode: 'Ölçüm'
  };

  function exifBicim(ad, v) {
    if (v == null || v === '') return null;
    if (ad === 'FNumber') return 'f/' + v;
    if (ad === 'ExposureTime') return v < 1 ? '1/' + Math.round(1 / v) + ' sn' : v + ' sn';
    if (ad === 'FocalLength' || ad === 'FocalLengthIn35mmFilm') return Math.round(v) + ' mm';
    if (ad === 'ISOSpeedRatings') return 'ISO ' + v;
    if (Array.isArray(v)) return v.join(', ');
    return String(v);
  }

  function exifSatir(kap, etiket, deger) {
    var d = el('div', 'gl-exif-satir');
    d.appendChild(el('b', null, etiket));
    d.appendChild(el('span', null, deger));
    kap.appendChild(d);
  }

  function exifBolum(kap, ad) {
    kap.appendChild(el('div', 'gl-exif-bolum', ad));
  }

  async function exifYukle(f) {
    var g = $('gl-exif-govde');
    g.innerHTML = '<span class="gl-bos-etiket">okunuyor…</span>';
    var d;
    try { d = await json('/exif/' + f.id); }
    catch (e) { g.innerHTML = ''; exifSatir(g, 'Hata', e.message); return; }
    if (_durum.acik < 0 || _durum.dosyalar[_durum.acik] !== f) return;   // gezindi

    g.innerHTML = '';
    exifBolum(g, 'DOSYA');
    exifSatir(g, 'Ad', d.ad);
    exifSatir(g, 'Klasör', d.klasor);
    exifSatir(g, 'Boyut', bayt(d.boyut));
    if (d.en && d.boy) {
      var mp = (d.en * d.boy) / 1e6;
      exifSatir(g, 'Çözünürlük', d.en + ' × ' + d.boy + (mp >= 0.5 ? ' (' + mp.toFixed(1) + ' MP)' : ''));
    }
    exifSatir(g, 'Değişti', tarihStr(d.degisti));

    if (d.tip === 'video') {
      var v = d.video || {};
      exifBolum(g, 'VİDEO');
      if (Object.keys(v).length) {
        if (v.duration) {
          var sn = Math.round(parseFloat(v.duration));
          exifSatir(g, 'Süre', Math.floor(sn / 60) + ':' + String(sn % 60).padStart(2, '0'));
        }
        if (v.codec_name) exifSatir(g, 'Kodek', v.codec_name);
        if (v.bit_rate) exifSatir(g, 'Bit hızı', Math.round(v.bit_rate / 1000) + ' kbps');
        if (v.r_frame_rate && v.r_frame_rate.indexOf('/') > 0) {
          var p = v.r_frame_rate.split('/');
          if (+p[1]) exifSatir(g, 'Kare hızı', (+p[0] / +p[1]).toFixed(2).replace(/\.00$/, '') + ' fps');
        }
      } else {
        exifSatir(g, 'Künye', 'ffprobe okunamadı');
      }
      return;
    }

    var ex = d.exif || {};
    var yazildi = 0;
    exifBolum(g, 'ÇEKİM');
    Object.keys(EXIF_ETIKET).forEach(function (k) {
      var val = exifBicim(k, ex[k]);
      if (val != null) { exifSatir(g, EXIF_ETIKET[k], val); yazildi++; }
    });
    if (!yazildi) {
      // ⚠️ "EXIF yok" bir ARIZA DEĞİL: ekran görüntüleri ve indirilen görseller
      // çekim verisi taşımaz (ölçüldü: 3.000 resmin 0'ında kamera EXIF'i var).
      exifSatir(g, 'Çekim verisi', 'yok — bu dosya fotoğraf makinesinden gelmemiş');
    }

    if (d.gps) {
      exifBolum(g, 'KONUM');
      exifSatir(g, 'Koordinat', d.gps.lat.toFixed(5) + ', ' + d.gps.lon.toFixed(5));
      var b = el('button', 'gl-exif-harita');
      b.type = 'button';
      b.appendChild(svgIk('i-konum', 'gl-ik-k'));
      b.appendChild(document.createTextNode('haritada göster'));
      b.addEventListener('click', function () { haritaAc(d.gps); });
      g.appendChild(b);
    }
  }

  function exifCevir() {
    var p = $('gl-exif');
    if (p.hidden) {
      var f = _durum.dosyalar[_durum.acik];
      if (!f) return;
      p.hidden = false;
      // Tam kipte kapat/indir panelin soluna kayar (CSS bu sınıftan okur)
      $('gl-buyuk').classList.add('gl-exif-acik');
      $('gl-exif-btn').setAttribute('aria-pressed', 'true');
      exifYukle(f);
      // Fişte künyeye kaydır — fiş kendi kabında kayar (scrollIntoView DEĞİL)
      if (!tamKipte()) {
        var gov = $('gl-fis-gov');
        gov.scrollTop = Math.max(0, p.offsetTop - 120);
      }
    } else {
      exifKapat();
    }
  }

  function exifKapat() {
    $('gl-exif').hidden = true;
    $('gl-buyuk').classList.remove('gl-exif-acik');
    $('gl-exif-btn').setAttribute('aria-pressed', 'false');
  }

  // ── Harita ──────────────────────────────────────────────────────
  /* 🔴 Leaflet TEMBEL yüklenir (163 KB'ı haritayı açmayan kullanıcıya yazmamak için).
   * 🔴 Altlık (OSM döşemeleri) AÇIK İZİNLE gelir — döşeme isteği fotoğrafların
   *    çekildiği bölgeyi openstreetmap.org'a söyler. */
  var TASLIK_ANAHTAR = 'galeriHaritaTasl';
  var HARITA_OZET = 'galeriHaritaOzet_v1';
  var _harita = { nesne: null, katman: null, tasl: null, yukluyor: null, veri: [], tarandi: false };

  function taslikTercih() {
    try {
      var v = localStorage.getItem(TASLIK_ANAHTAR);
      return (v === 'izin' || v === 'ret') ? v : null;
    } catch (e) { return null; }
  }

  function taslikEkle() {
    if (_harita.tasl || !_harita.nesne || !window.L) return;
    _harita.tasl = window.L.tileLayer('https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png', {
      attribution: '© OpenStreetMap', maxZoom: 19
    }).addTo(_harita.nesne);
  }

  function taslikUI() {
    var t = taslikTercih();
    $('gl-harita-onay').hidden = t !== null;
    $('gl-harita-onay-sifirla').hidden = t === null;
  }

  function taslikSec(t) {
    try { localStorage.setItem(TASLIK_ANAHTAR, t); } catch (e) {}
    if (t === 'izin') taslikEkle();
    taslikUI();
  }

  /** Son taramanın özeti: 0 konum bulunduysa araç SÖNÜK durur (silinmez). */
  function haritaOzetUI() {
    var o = null;
    try { o = JSON.parse(localStorage.getItem(HARITA_OZET) || 'null'); } catch (e) {}
    var b = $('gl-harita-btn');
    var sonuk = !!(o && o.sayi === 0);
    b.classList.toggle('gl-sonuk', sonuk);
    $('gl-harita-ozet').textContent = o ? 'konum bilgili fotoğraf: ' + fmt(o.sayi) : 'konum bilgili fotoğraflar';
    b.title = 'Harita — GPS\'li fotoğraflar (M)' + (o ? ' · son tarama: ' + fmt(o.sayi) + ' konumlu' : '');
  }

  function leafletYukle() {
    if (window.L) return Promise.resolve();
    if (_harita.yukluyor) return _harita.yukluyor;
    _harita.yukluyor = new Promise(function (coz, red) {
      var css = document.createElement('link');
      css.rel = 'stylesheet';
      css.href = '/ui/vendor/leaflet-1.9.4/leaflet.css';
      document.head.appendChild(css);
      var s = document.createElement('script');
      s.src = '/ui/vendor/leaflet-1.9.4/leaflet.js';   // yerel kopya — CDN KULLANILMAZ
      s.onload = coz;
      s.onerror = function () { red(new Error('Leaflet yüklenemedi')); };
      document.head.appendChild(s);
    });
    return _harita.yukluyor;
  }

  async function haritaAc(odak) {
    modalAc('gl-harita');
    taslikUI();
    try { await leafletYukle(); }
    catch (e) { $('gl-harita-bilgi').textContent = e.message; return; }

    var L = window.L;
    if (!_harita.nesne) {
      _harita.nesne = L.map('gl-harita-tuval', { attributionControl: true }).setView([39.0, 35.0], 5);
      if (taslikTercih() === 'izin') taslikEkle();
      _harita.katman = L.layerGroup().addTo(_harita.nesne);
    }
    // ⚠️ Modal gizliyken kurulan harita kendi boyutunu 0 ölçer → gri kalır.
    setTimeout(function () { if (_harita.nesne) _harita.nesne.invalidateSize(); }, 60);

    if (odak) _harita.nesne.setView([odak.lat, odak.lon], 13);
    if (!_harita.tarandi) await haritaTara();
    else if (!odak) haritaSigdir();
  }

  async function haritaTara() {
    var cubuk = $('gl-harita-ilerleme');
    var ic = cubuk.firstElementChild;
    cubuk.hidden = false;
    var offset = 0, toplam = 0;
    _harita.veri = [];
    try {
      while (true) {
        // 🔴 Kademeli: uç 400'lük dilimlerle tarar (tek istek dakikalar sürerdi).
        var d = await json('/harita?offset=' + offset + '&limit=400');
        toplam = d.toplam;
        d.noktalar.forEach(haritaNokta);
        _harita.veri = _harita.veri.concat(d.noktalar);
        offset = d.taranan;
        ic.style.width = (toplam ? (d.taranan / toplam * 100) : 100).toFixed(1) + '%';
        $('gl-harita-sayac').textContent =
          fmt(d.taranan) + ' / ' + fmt(toplam) + ' tarandı · ' + fmt(_harita.veri.length) + ' konumlu';
        if (d.bitti) break;
      }
      _harita.tarandi = true;
      haritaSigdir();
      try { localStorage.setItem(HARITA_OZET, JSON.stringify({ sayi: _harita.veri.length, t: Date.now() })); } catch (e) {}
      haritaOzetUI();
      $('gl-harita-bilgi').textContent = _harita.veri.length
        ? fmt(_harita.veri.length) + ' fotoğrafta konum bulundu.'
        : 'Hiçbir fotoğrafta GPS verisi yok — bu klasördeki dosyalar makineden değil ekrandan/indirmeden gelmiş olabilir.';
    } catch (e) {
      $('gl-harita-bilgi').textContent = 'Tarama durdu: ' + e.message;
    } finally {
      cubuk.hidden = true;
    }
  }

  function haritaNokta(n) {
    var L = window.L;
    if (!L || !_harita.katman) return;
    var m = L.marker([n.lat, n.lon]);
    // 🔴 Balon içeriği DOM ile kurulur, HTML şablonuyla DEĞİL: dosya adı
    // kullanıcı verisidir ve `innerHTML`e girerse XSS yüzeyi açar.
    var kutu = document.createElement('div');
    var img = document.createElement('img');
    img.alt = n.ad; img.width = 160;
    img.style.cursor = 'pointer';
    kucukBas(img, n.id, 200);
    img.addEventListener('click', function () { modalKapat('gl-harita'); dosyayaGit(n.id); });
    var ad = document.createElement('div');
    ad.style.cssText = 'margin-top:4px;font-size:var(--fs-xs);max-width:160px;overflow-wrap:anywhere';
    ad.textContent = n.ad;
    kutu.appendChild(img); kutu.appendChild(ad);
    m.bindPopup(kutu);
    _harita.katman.addLayer(m);
  }

  function haritaSigdir() {
    if (!_harita.nesne || !_harita.veri.length) return;
    _harita.nesne.fitBounds(_harita.veri.map(function (n) { return [n.lat, n.lon]; }),
                            { padding: [30, 30], maxZoom: 14 });
  }

  /** Bir kimliği akışta bul ve fişte aç (harita/kopya/istatistik listelerinden).
   * Akışta yoksa dosyanın klasörüne git — `?ac=` yolunun aynısı. */
  async function dosyayaGit(id) {
    var i = _durum.dosyalar.findIndex(function (f) { return f.id === id; });
    if (i >= 0) { buyukAc(i); return; }
    try {
      var b = await json('/bilgi/' + id);
      await klasorAc(b.klasor_id);
      var tur = 0;
      i = _durum.dosyalar.findIndex(function (f) { return f.id === id; });
      while (i < 0 && !_durum.bitti && tur++ < 20) {
        await dahaGetir();
        i = _durum.dosyalar.findIndex(function (f) { return f.id === id; });
      }
      if (i >= 0) buyukAc(i);
    } catch (e) { /* dosya taşınmış olabilir — sessiz geç */ }
  }

  // ── Kopya bulucu ────────────────────────────────────────────────
  var _kopya = { calisiyor: false, esik: 6 };

  function kopyaAc() {
    modalAc('gl-kopya');
    if (!$('gl-kopya-liste').children.length) kopyaTara();
  }

  async function kopyaTara() {
    if (_kopya.calisiyor) return;
    _kopya.calisiyor = true;
    var liste = $('gl-kopya-liste');
    var cubuk = $('gl-kopya-ilerleme');
    var ic = cubuk.firstElementChild;
    liste.innerHTML = '<div class="gl-bos-etiket">özetler çıkarılıyor… ilk tarama uzun sürer, sonrası anında gelir</div>';
    cubuk.hidden = false;
    var offset = 0, son = null;
    try {
      while (true) {
        var d = await json('/kopyalar?offset=' + offset + '&limit=800&esik=' + _kopya.esik);
        offset = d.taranan;
        ic.style.width = (d.toplam ? (d.taranan / d.toplam * 100) : 100).toFixed(1) + '%';
        $('gl-kopya-sayac').textContent = fmt(d.taranan) + ' / ' + fmt(d.toplam) + ' tarandı';
        if (d.bitti) { son = d; break; }
      }
      kopyaCiz(son);
    } catch (e) {
      liste.innerHTML = '';
      liste.appendChild(el('div', 'gl-bos-etiket', 'Tarama durdu: ' + e.message));
    } finally {
      cubuk.hidden = true;
      _kopya.calisiyor = false;
    }
  }

  function kopyaCiz(d) {
    var liste = $('gl-kopya-liste');
    liste.innerHTML = '';
    $('gl-kopya-sayac').textContent = fmt(d.gruplar.length) + ' grup · ' + fmt(d.kopya_sayisi) +
      ' fazlalık · ' + bayt(d.kazanc || 0) + ' geri kazanılabilir' +
      // ⚠️ Sessiz kırpma yok: sınıra dayandıysak bunu YAZ.
      (d.kesildi ? ' · (ilk 200 grup gösteriliyor)' : '');

    // ⚠️ Eleme SESSİZ yapılmaz — düz/kontrastsız resimler kıyaslamaya girmiyor.
    if (d.elenen_duz) {
      var not = el('div', 'gl-bos-etiket',
        fmt(d.elenen_duz) + ' resim kıyaslama dışı bırakıldı — düz/az kontrastlı görüntüler ' +
        '(ekran görüntüsü, belge taraması) birbirinden ayırt edilemiyor ve yanlış eşleşme üretiyorlar.');
      not.style.marginBottom = 'var(--sp-3)';
      liste.appendChild(not);
    }

    if (!d.gruplar.length) {
      liste.appendChild(el('div', 'gl-bos-etiket', 'Bu benzerlik seviyesinde kopya bulunamadı.'));
      return;
    }

    d.gruplar.forEach(function (grup, gi) {
      var kap = el('div', 'gl-kopya-grup');
      var bas = el('div', 'gl-kopya-bas');
      var enBuyuk = grup.reduce(function (a, b) { return b.boyut > a.boyut ? b : a; }, grup[0]);
      bas.appendChild(el('span', null, '#' + (gi + 1)));
      bas.appendChild(el('b', null, grup.length + ' dosya · ' +
        bayt(grup.reduce(function (t, x) { return t + x.boyut; }, 0) - enBuyuk.boyut) + ' fazlalık'));
      kap.appendChild(bas);

      var satir = el('div', 'gl-kopya-satir');
      grup.forEach(function (x) {
        var b = el('button', 'gl-kopya-oge' + (x === enBuyuk ? ' gl-asil' : ''));
        b.type = 'button';
        b.title = x.ad + '\n' + x.klasor;
        var img = document.createElement('img');
        img.alt = x.ad;
        kucukBas(img, x.id, 200);
        b.appendChild(img);
        b.appendChild(el('span', null, x.ad));
        b.appendChild(el('small', null, bayt(x.boyut) + (x === enBuyuk ? ' · en büyük' : '')));
        b.addEventListener('click', function () { modalKapat('gl-kopya'); dosyayaGit(x.id); });
        satir.appendChild(b);
      });
      kap.appendChild(satir);
      liste.appendChild(kap);
    });
  }

  // ── İstatistik ──────────────────────────────────────────────────
  async function statAc() {
    modalAc('gl-stat');
    var g = $('gl-stat-govde');
    g.innerHTML = '<span class="gl-bos-etiket">hesaplanıyor…</span>';
    var d;
    try { d = await json('/istatistik'); }
    catch (e) { g.innerHTML = ''; g.textContent = 'Alınamadı: ' + e.message; return; }
    g.innerHTML = '';

    var kutular = el('div', 'gl-stat-kutular');
    [['Toplam', fmt(d.toplam)], ['Resim', fmt(d.resim)], ['Video', fmt(d.video)], ['Disk', bayt(d.bayt)]]
      .forEach(function (p) {
        var k = el('div', 'gl-stat-kutu');
        k.appendChild(el('b', null, p[1]));
        k.appendChild(el('span', null, p[0]));
        kutular.appendChild(k);
      });
    g.appendChild(kutular);

    var aralik = statSatir(g, 'En eski → en yeni',
                           tarihStr(d.en_eski) + '  →  ' + tarihStr(d.en_yeni));
    aralik.style.marginBottom = '4px';

    if (d.aylik && d.aylik.length) {
      statBolum(g, 'AYLIK DAĞILIM (son ' + d.aylik.length + ' ay)');
      var enCok = Math.max.apply(null, d.aylik.map(function (a) { return a.sayi; }));
      var cubuk = el('div', 'gl-cubuk');
      var etiket = el('div', 'gl-cubuk-etiket');
      d.aylik.forEach(function (a, i) {
        var o = el('div', 'gl-cubuk-oge');
        o.title = a.ay + ' · ' + fmt(a.sayi) + ' dosya';
        var ic = document.createElement('i');
        ic.style.height = Math.max(2, a.sayi / enCok * 100) + '%';
        o.appendChild(ic);
        cubuk.appendChild(o);
        // 24 sütunda her ayın etiketi okunmaz → yalnız 3'te bir yaz.
        etiket.appendChild(el('span', null, (i % 3 === 0 || i === d.aylik.length - 1) ? a.ay.slice(2).replace('-', '/') : ''));
      });
      g.appendChild(cubuk);
      g.appendChild(etiket);
    }

    if (d.kokler && d.kokler.length) {
      statBolum(g, 'KLASÖRLER');
      d.kokler.forEach(function (k) {
        statSatir(g, k.ad, fmt(k.sayi) + ' dosya · ' + bayt(k.bayt));
      });
    }

    statBolum(g, 'DOSYA TÜRLERİ');
    (d.uzantilar || []).forEach(function (u) { statSatir(g, u.uz, fmt(u.sayi)); });

    if (d.en_buyuk && d.en_buyuk.length) {
      statBolum(g, 'EN BÜYÜK DOSYALAR');
      d.en_buyuk.forEach(function (x) {
        var s = statSatir(g, x.ad, bayt(x.boyut));
        s.style.cursor = 'pointer';
        s.addEventListener('click', function () { modalKapat('gl-stat'); dosyayaGit(x.id); });
      });
    }
  }

  function statBolum(kap, ad) { kap.appendChild(el('div', 'gl-stat-bolum', ad)); }

  function statSatir(kap, sol, sag) {
    var d = el('div', 'gl-liste-satir');
    d.appendChild(el('span', null, sol));
    d.appendChild(el('b', null, sag));
    kap.appendChild(d);
    return d;
  }

  // ── Karşılaştırma ───────────────────────────────────────────────
  /* İki resim yan yana, **ORTAK** zoom/kaydırma. 🔴 Tek bir dönüşüm iki resme
   * birden yazılır — ayrı hesaplanırsa kıyas anlamını yitirir. */
  var _kiyas = { acik: false, secim: [], k: 1, x: 0, y: 0, suruk: null };

  function secimCevir() {
    if (_kiyas.acik) { secimIptal(); return; }
    _kiyas.acik = true;
    _kiyas.secim = [];
    document.body.classList.add('gl-secim-acik');
    $('gl-secim-serit').hidden = false;
    $('gl-kiyas-btn').setAttribute('aria-pressed', 'true');
    secimBilgi();
  }

  function secimIptal() {
    _kiyas.acik = false;
    _kiyas.secim = [];
    document.body.classList.remove('gl-secim-acik');
    $('gl-secim-serit').hidden = true;
    $('gl-kiyas-btn').setAttribute('aria-pressed', 'false');
    Array.prototype.forEach.call(document.querySelectorAll('.gl-kart.gl-secili'),
      function (k) { k.classList.remove('gl-secili'); });
  }

  function secimBilgi() {
    $('gl-secim-bilgi').textContent = _kiyas.secim.length === 0
      ? 'Karşılaştırmak için 2 resim seç'
      : (_kiyas.secim.length + ' seçildi — ' + (2 - _kiyas.secim.length) + ' tane daha');
  }

  function kartSec(kart, f) {
    // Video karşılaştırılmaz: senkron zoom oynatma denetimleriyle çakışır.
    if (f.tip !== 'resim') { $('gl-secim-bilgi').textContent = 'Yalnız resim karşılaştırılır'; return; }
    var i = _kiyas.secim.findIndex(function (x) { return x.f.id === f.id; });
    if (i >= 0) {
      _kiyas.secim[i].kart.classList.remove('gl-secili');
      _kiyas.secim.splice(i, 1);
      secimBilgi();
      return;
    }
    if (_kiyas.secim.length >= 2) return;
    kart.classList.add('gl-secili');
    _kiyas.secim.push({ kart: kart, f: f });
    secimBilgi();
    if (_kiyas.secim.length === 2) kiyasAc(_kiyas.secim[0].f, _kiyas.secim[1].f);
  }

  /** Fişteki KIYASLA: baktığın resim birinci seçim olur, ikinciyi ızgaradan
   * seçersin — fiş açıkken ızgara görünür kaldığı için bu tek tıktır. */
  function fistenKiyasla() {
    var f = _durum.dosyalar[_durum.acik];
    if (!f) return;
    if (f.tip !== 'resim') { duyur('Yalnız resim karşılaştırılır.'); return; }
    if (!_kiyas.acik) secimCevir();
    var kart = document.querySelector('.gl-kart[data-i="' + _durum.acik + '"]');
    if (kart && !kart.classList.contains('gl-secili')) kartSec(kart, f);
  }

  async function kiyasAc(a, b) {
    $('gl-kiyas').hidden = false;
    $('gl-kiyas-ad-sol').textContent = a.ad;
    $('gl-kiyas-ad-sag').textContent = b.ad;
    kiyasSifirla();
    var sol = $('gl-kiyas-sol'), sag = $('gl-kiyas-sag');
    sol.removeAttribute('src'); sag.removeAttribute('src');
    try {
      var us = await medyaUrl('b:' + a.id, '/dosya/' + a.id);
      var ug = await medyaUrl('b:' + b.id, '/dosya/' + b.id);
      sol.src = us; sag.src = ug;
    } catch (e) {
      $('gl-kiyas-ad-sol').textContent = 'Açılamadı: ' + e.message;
    }
  }

  function kiyasKapat() {
    $('gl-kiyas').hidden = true;
    secimIptal();
  }

  function kiyasSifirla() { _kiyas.k = 1; _kiyas.x = 0; _kiyas.y = 0; kiyasUygula(); }

  function kiyasUygula() {
    var t = 'translate(calc(-50% + ' + _kiyas.x + 'px), calc(-50% + ' + _kiyas.y + 'px)) scale(' + _kiyas.k + ')';
    $('gl-kiyas-sol').style.transform = t;
    $('gl-kiyas-sag').style.transform = t;
  }

  function kiyasBagla() {
    var bol = $('gl-kiyas-bol');
    bol.addEventListener('wheel', function (e) {
      e.preventDefault();
      _kiyas.k = Math.max(0.2, Math.min(12, _kiyas.k * (e.deltaY < 0 ? 1.12 : 1 / 1.12)));
      kiyasUygula();
    }, { passive: false });
    bol.addEventListener('mousedown', function (e) {
      e.preventDefault();
      _kiyas.suruk = { x: e.clientX, y: e.clientY, bx: _kiyas.x, by: _kiyas.y };
    });
    window.addEventListener('mousemove', function (e) {
      if (!_kiyas.suruk) return;
      _kiyas.x = _kiyas.suruk.bx + (e.clientX - _kiyas.suruk.x);
      _kiyas.y = _kiyas.suruk.by + (e.clientY - _kiyas.suruk.y);
      kiyasUygula();
    });
    window.addEventListener('mouseup', function () { _kiyas.suruk = null; });
  }

  // ── Yeniden boyutlanma ──────────────────────────────────────────
  // Yalnız sütun SAYISI değiştiğinde yeniden dağıtılır; her pikselde dağıtmak
  // pencere sürüklenirken ızgarayı titretirdi. Kap genişliği pencereden
  // bağımsız da değişir (fiş açılır, omurga gizlenir) → ResizeObserver.
  var _boyutZaman = null;
  function duzenTazeleBekle() {
    clearTimeout(_boyutZaman);
    _boyutZaman = setTimeout(function () { duzenTazele(false); }, 120);
  }
  window.addEventListener('resize', duzenTazeleBekle);
  if (window.ResizeObserver) new ResizeObserver(duzenTazeleBekle).observe($('gl-icerik'));

  // ── Klavye ──────────────────────────────────────────────────────
  /* Kesin öncelik sırası: kaplama (seçici/karşılaştırma/modal/çekmece) → fiş →
   * ızgara. Sıra karışırsa Esc yanlış katmanı kapatır.
   * 🔴 Yazı alanında kısayol ÇALIŞMAZ — arama kutusuna "m" yazmak haritayı açmamalı. */
  document.addEventListener('keydown', function (e) {
    var hedef = e.target;
    var yaziyor = hedef && (hedef.tagName === 'INPUT' || hedef.tagName === 'TEXTAREA' ||
                            hedef.tagName === 'SELECT' || hedef.isContentEditable);
    if (yaziyor) {
      if (e.key === 'Escape') { hedef.blur(); document.body.classList.remove('gl-ara-acik'); }
      return;
    }
    if (e.ctrlKey || e.metaKey || e.altKey) return;   // tarayıcı kısayollarını yeme

    // ① Kaplamalar
    if (!$('gl-kiyas').hidden) {
      if (e.key === 'Escape' || e.key.toLowerCase() === 'q') { kiyasKapat(); e.preventDefault(); }
      else if (e.key === '0') { kiyasSifirla(); e.preventDefault(); }
      return;
    }
    var modal = acikModal();
    if (modal) {
      if (e.key === 'Escape') { modalKapat(modal); e.preventDefault(); }
      return;
    }
    if (document.body.classList.contains('gl-ray-acik') || document.body.classList.contains('gl-kontrol-acik')) {
      if (e.key === 'Escape') { cekmece(null, false); e.preventDefault(); }
      return;
    }

    // ② Fiş (büyük görünüm). Tam kipte değilse ızgara kısayolları da çalışır —
    //    fiş açıkken ızgara görünür, T/C/M'ye basmak için fişi kapatmak gerekmesin.
    if (!$('gl-buyuk').hidden) {
      var t = e.key.toLowerCase();
      var islendi = true;
      if (e.key === 'Escape' || t === 'q') { if (tamKipte()) tamCevir(false); else buyukKapat(); }
      else if (e.key === 'ArrowRight') gez(1);
      else if (e.key === 'ArrowLeft') gez(-1);
      else if (t === 'j') gez(10);
      else if (t === 'k') gez(-10);
      else if (t === 'i') exifCevir();
      else if (t === 's') slaytCevir();
      else if (t === 'f') tamEkranCevir();
      else if (e.key === '+' || e.key === '=') zoomEt(1.3);
      else if (e.key === '-' || e.key === '_') zoomEt(1 / 1.3);
      else if (e.key === '0') zoomSifirla();
      else islendi = false;
      if (islendi) { e.preventDefault(); return; }
      if (tamKipte()) return;
    }

    // ③ Izgara
    var g = e.key.toLowerCase();
    if (e.key === '/') { if (KOMPAKT.matches) document.body.classList.add('gl-ara-acik'); $('gl-ara').focus(); e.preventDefault(); }
    else if (e.key === '?') { modalAc('gl-yardim'); e.preventDefault(); }
    else if (g === 'm') { haritaAc(); e.preventDefault(); }
    else if (g === 'd') { kopyaAc(); e.preventDefault(); }
    else if (g === 't') { statAc(); e.preventDefault(); }
    else if (g === 'c') { secimCevir(); e.preventDefault(); }
    else if (g === 's') { slaytCevir(); e.preventDefault(); }
    else if (g === 'r') { yenile(); e.preventDefault(); }
    else if (e.key === '[') { ayKomsu(-1); e.preventDefault(); }
    else if (e.key === ']') { ayKomsu(1); e.preventDefault(); }
    else if (e.key === 'Escape' && _kiyas.acik) { secimIptal(); e.preventDefault(); }
    else if (g === 'g') {
      var kap = $('gl-icerik');
      kap.scrollTo({ top: e.shiftKey ? kap.scrollHeight : 0, behavior: 'smooth' });
      e.preventDefault();
    }
  });

  // ── Açılış ──────────────────────────────────────────────────────
  async function kur() {
    boyutKur();
    $('gl-kapat').addEventListener('click', buyukKapat);
    $('gl-onceki').addEventListener('click', function () { gez(-1); });
    $('gl-sonraki').addEventListener('click', function () { gez(1); });
    $('gl-tel-onceki').addEventListener('click', function () { gez(-1); });
    $('gl-tel-sonraki').addEventListener('click', function () { gez(1); });
    $('gl-buyut-btn').addEventListener('click', function () { tamCevir(); });
    $('gl-fis-kiyas').addEventListener('click', fistenKiyasla);
    aramaBagla();
    gorunumBagla();
    rayBagla();
    omurgaBagla();
    cekmeceBagla();
    haritaOzetUI();

    // ── Keşif araçları (2026-09-20) ───────────────────────────────
    zoomBagla();
    kiyasBagla();
    hizKur();

    $('gl-harita-btn').addEventListener('click', function () { haritaAc(); });
    $('gl-kopya-btn').addEventListener('click', kopyaAc);
    $('gl-stat-btn').addEventListener('click', statAc);
    $('gl-kiyas-btn').addEventListener('click', secimCevir);
    $('gl-yardim-btn').addEventListener('click', function () { modalAc('gl-yardim'); });

    $('gl-harita-kapat').addEventListener('click', function () { modalKapat('gl-harita'); });
    $('gl-kopya-kapat').addEventListener('click', function () { modalKapat('gl-kopya'); });
    $('gl-stat-kapat').addEventListener('click', function () { modalKapat('gl-stat'); });
    $('gl-yardim-kapat').addEventListener('click', function () { modalKapat('gl-yardim'); });

    $('gl-harita-izin').addEventListener('click', function () { taslikSec('izin'); });
    $('gl-harita-ret').addEventListener('click', function () { taslikSec('ret'); });
    $('gl-harita-onay-sifirla').addEventListener('click', function () {
      // "Sıfırla" dedikten sonra istek DEVAM ETMEMELİ — yüklü altlık da kalkar.
      try { localStorage.removeItem(TASLIK_ANAHTAR); } catch (e) {}
      if (_harita.tasl && _harita.nesne) { _harita.nesne.removeLayer(_harita.tasl); _harita.tasl = null; }
      taslikUI();
    });

    $('gl-kopya-esik').addEventListener('change', function (e) {
      _kopya.esik = parseInt(e.target.value, 10) || 6;
      $('gl-kopya-liste').innerHTML = '';
      kopyaTara();          // özetler önbellekte — yeniden gruplama ms sürer
    });

    $('gl-exif-btn').addEventListener('click', exifCevir);
    $('gl-exif-kapat').addEventListener('click', exifKapat);
    $('gl-slayt-btn').addEventListener('click', slaytCevir);
    $('gl-tamekran-btn').addEventListener('click', tamEkranCevir);
    $('gl-secim-iptal').addEventListener('click', secimIptal);
    $('gl-kiyas-kapat').addEventListener('click', kiyasKapat);
    $('gl-kiyas-sifirla').addEventListener('click', kiyasSifirla);
    document.addEventListener('fullscreenchange', function () {
      if (!document.fullscreenElement && tamKipte()) zoomSifirla();
    });

    // Modalın dışına tıklayınca kapat
    MODALLAR.forEach(function (m) {
      $(m).addEventListener('click', function (e) {
        if (e.target === e.currentTarget) modalKapat(m);
      });
    });

    var ac = new URLSearchParams(location.search).get('ac');
    try {
      await koklerYukle();
    } catch (e) {
      bosGoster('Galeri açılamadı: ' + metinKacis(e.message));
      $('gl-ray-liste').innerHTML = '';
      return;
    }
    agacYukle();                          // ray paralel gelsin; akışı bekletmez

    if (ac) {
      // Yuki yolu: dosyanın klasörünü aç, ızgarayı kur, sonra o dosyayı fişte aç.
      // Tek dosyalık çıkmaz sokak DEĞİL — komşularında gezilebilir.
      try {
        var b = await json('/bilgi/' + encodeURIComponent(ac));
        await klasorAc(b.klasor_id);
        var i = _durum.dosyalar.findIndex(function (f) { return f.id === b.id; });
        // Hedef ilk sayfada değilse sayfa sayfa ilerle (en çok 20 sayfa = 2400 dosya).
        var tur = 0;
        while (i < 0 && !_durum.bitti && tur++ < 20) {
          await dahaGetir();
          i = _durum.dosyalar.findIndex(function (f) { return f.id === b.id; });
        }
        if (i >= 0) { buyukAc(i); return; }
      } catch (e) {
        bosGoster('İstenen dosya açılamadı: ' + metinKacis(e.message));
        return;
      }
    }
    hepsiAc();
  }

  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', kur);
  else kur();
})();
