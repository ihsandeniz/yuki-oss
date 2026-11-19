/* ════════════════════════════════════════════════════════════════════════
   map-engine.js — ürüne taşındı (Dalga 3 kalanı, 2026-09-18)

   Kaynak: kişisel AliceAi `frontend/js/map-engine.js`.
   Uçlar `backend/app/api/map.py` — 22 katman, 20'si anahtarsız.

   ÜRÜNE AİT OLMAYAN üç bağ temizlendi (bkz. scratchpad/map-js-tasi.py):
   `intelBrief` (tanımı kişiselin index.html'indeydi) · `mcRunAgent`
   (Mission Control, kendi LLM çağrısı) · `updateSysVitals` (/api/metrics;
   ürünün HQ → SİSTEM paneli aynı işi yapıyor).

   2026-10-04 (HARİTA ÖNCE — kişisel 8dd7587'nin çevirisi): katman
   satırı = anahtar (`_katmanUiSenk`), şeride Kp, GÜNDEM süzgeci (`_haberAyir`),
   işaretçi brifingi sohbet yolundan (`_brifingDugme` → `mapSendMessage` →
   core.js `sendMessage`), görsel mod `mapGorselMod` (setViewMode çakışması).
   Silinen: akan şerit, radar, PORTAL + STATE→PORTAL, PİYASA (CoinGecko),
   mini sohbet (YUKI KANALI) ve `mapQA`.
   ════════════════════════════════════════════════════════════════════════ */

/* ── Çeviri (FAZ 3 · Dalga 2 · dosya kuyruğu 3/4, 2026-09-20) ───────────────
   Bu dosyanın metinlerinin tamamı JS'ten doğuyor (marker tooltip'i, popup
   `innerHTML`'i, HUD kartı, toast) — `dil.js::ciz()` hiçbirini görmez.

   🔴 ADI `_t` DEĞİL `_mt`. `core.js` de klasik script ve `function _t`
   bildiriyor, yani `window._t`ye yazıyor; `index.html`'de core.js **1908.**
   satırda, bu dosya **2027.** satırda yükleniyor. Burada `_t` bildirseydik
   core.js'in sarmalayıcısını **ezerdik** — bugün zararsız görünürdü (iki gövde
   aynı), ama o an itibarıyla core.js'in 100 çağrı yeri bu dosyanın kopyasını
   çağırıyor olurdu. Aynı işin iki kaynağı: biri düzeltilir, öbürü bayatlar
   (`tur_olcum.py` kararının aynısı, `esc()`/`af()`/`start.sh` üç kez ödedi).

   ⚠️ `t` bu dosyada iki yerde yerel değişken (`stops` tokenleri, satır ~2951) —
   `t` adı seçilseydi o kapsamda çeviri çağrısı sessizce gölgelenirdi. */
function _mt(anahtar, degerler) {
  return (window.YukiDil && window.YukiDil.t)
    ? window.YukiDil.t(anahtar, degerler) : String(anahtar);
}

/* Sayıya bağlı metin (`dil.js::tc` — backend `Mc` ile aynı sözleşme). */
function _mtc(anahtar, sayi, degerler) {
  return (window.YukiDil && window.YukiDil.tc)
    ? window.YukiDil.tc(anahtar, sayi, degerler) : String(anahtar);
}

/* Tarih/saat/sayı biçimi etiketi — `'tr-TR'` yazmak metin çevrilse bile biçimi
   Türkçe bırakır (Blok 3'ün TR BİÇİM dersi). */
function _myerel() {
  return (window.YukiDil && window.YukiDil.yerel) ? window.YukiDil.yerel() : 'tr-TR';
}

// ══════════════════════════════════════════════════════
//  MAP TAB — Tab Switching
// ══════════════════════════════════════════════════════
let _mapInited = false;

let _controlInited = false;
let _driveInited   = false;
let _galeriInited  = false;
let _kriptoInited  = false;
let _plannerInited  = false;
let _odakInited     = false;
let _ajanInited     = false;

// ── Sekme yönlendirmesi ARTIK BURADA DEĞİL (2026-09-18) ─────────────
//
// Burada `switchTab` · `switchTabFromDropdown` · `toggleTabDropdown` +
// açma/kapama yardımcıları duruyordu (234 satır). Üçü de **üst düzey
// bildirimdi**, yani `window`'a yazılıyorlardı; bu dosya `index.html`'de
// `tab-nav.js`'ten SONRA yüklendiği için hoisting ile onun
// `window.switchTab = sekmeGec` atamasını **eziyorlardı**.
//
// 🔴 Sonucu ölçüldü: AYAR sekmesi hiç açılmıyordu. Buradaki eski sürüm
// görünürlüğü `style.display` ile yönetiyor, oysa markup `hidden`
// özniteliğiyle yönetiliyor (`kabuk.css:434` sözleşmesi) ve
// `temel.css:183` `[hidden]{display:none!important}` satır içi stili bile
// yeniyor. Tıklamadan sonra `#tab-hq`: inline `display:flex`, hesaplanan
// `display:none`, `hidden=true` — hata YOK, panel de YOK.
//
// Silinen gövde kişisel Alice'ten toptan kopyaydı: `tab-drive` · `tab-galeri`
// · `tab-kripto` · `tab-odak` · `tab-ajan` dallarının hiçbiri
// üründe yok. 📏 *Bir dosyayı komşu projeden kopyalamak, içindeki adresleri
// de kopyalar* — bu depoda dördüncü kez ödendi (`start.sh` · `hq-monitor.css`
// · `docker-compose.yml` · burası).
//
// Kuyruğundaki dört işin üçü ölçülerek ÖLÜ bulundu, o yüzden taşınmadı:
//   · `body.dataset.tab` → üründe `data-tab` okuyan **tek bir CSS kuralı yok**
//     (tek eşleşme `duvar.css`'te bir YORUM). `tab-nav.js` zaten
//     `documentElement`'e yazıyor ve okuyan da kendisi (`tab-nav.js:715`).
//   · `hr-bugun-acik` / `hr-cekmece-acik` temizliği → bu iki sınıf ürün
//     genelinde **başka hiçbir yerde** geçmiyor; kimse set etmiyor.
//   · `_DROPDOWN_TABS` vurgusu → liste kişiselin sekmeleri (`drive`,`control`).
//   · `duvarUygula(tab)` → GEREKSİZ: `duvar.js:424` `tabchange` olayını zaten
//     dinliyor ve o olayı `tab-nav.js:143` yayınlıyor. Kanca dosyanın
//     içinde kalır (duvar.js'in kendi notu: *"başka bir dosyaya satır
//     eklemekten iyidir"*). Bugüne kadar çalışan yol buradaki elle çağrıydı;
//     artık tasarlandığı yoldan geçiyor.
//
// Taşınan TEK şey haritanın tembel kurulumu — o gerçekten bu dosyanın işi ve
// hemen aşağıdaki `tabchange` kancasına alındı (sarmalayıcıya DEĞİL; sebebi
// orada yazılı).

// ── Haritanın TEMBEL kurulumu — `tabchange` kancası ────────────────
//
// 🔴 Neden `window.switchTab` SARMALANMIYOR: `tab-nav.js::sekmeGec` gövdeyi
// `document.startViewTransition` içinde koşturuyor, yani `sekmeGecHam` BİR
// SONRAKİ FRAME'de çalışıyor. Sarmalayıcıdan `origSwitch(tab)` dönüşünde
// `#tab-map` hâlâ `hidden`'dır; Leaflet o an kurulursa 0 yükseklikli bir kapta
// kurulur ve karoları yanlış hesaplar. İlk denemede tam bu oldu: sekme
// açılıyordu ama `.leaflet-container` hiç oluşmuyordu, üstelik HATA DA YOKTU.
// (Ürün CLAUDE.md § HQ aynı tuzağı ölçüm yazanlar için not etmiş: "View
// Transition callback'inde bir sonraki frame'de koşar".)
//
// `tabchange` olayı `sekmeGecHam`'in İÇİNDE, `hidden` kalktıktan sonra
// yayınlanıyor (`tab-nav.js:143`). Doğru kanca o. `duvar.js:424`
// çoktan bu deseni kullanıyor ve gerekçesini de yazmış: *"olayı dinlemek,
// başka bir dosyaya satır eklemekten iyidir"*.
document.addEventListener('tabchange', function (e) {
  if (!e || !e.detail || e.detail.tab !== 'map') return;
  var kap = document.getElementById('tab-map');
  if (!kap || kap.hidden) return;        // kademe kapısı sohbete düşürmüş olabilir
  if (!_mapInited) {
    initLeafletMap();
    _mapInited = true;
  } else if (_lmap) {
    // Gizliyken boyut değiştiyse Leaflet bunu bilmez; karolar kayık kalır.
    setTimeout(function () {
      if (document.visibilityState !== 'hidden') _lmap.invalidateSize();
    }, 50);
  }
});


// ══════════════════════════════════════════════════════
//  FACES TAB → frontend/js/faces.js
//  (2026-07-29: yüz paneli tek kaynağa taşındı; burada ve
//   faces.html içinde iki ayrışmış kopya duruyordu)
// ══════════════════════════════════════════════════════

function _escHtml(s) {
  return String(s).replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;').replace(/"/g,'&quot;');
}

// ══════════════════════════════════════════════════════
//  LEAFLET MAP INIT
// ══════════════════════════════════════════════════════
let _lmap = null, _userMarker = null, _clickMarker = null;

function initLeafletMap() {
  _lmap = L.map('leaflet-map', {
    center: [20, 10],
    zoom: 2,
    zoomControl: false,
    attributionControl: false
  });

  // Zemin: Esri Dark Gray Canvas (anahtarsız, referer bağımsız).
  // 🔴 CARTO dark_all'dan 2026-08-28'de çıkıldı: CARTO anonim kullanımı kapatıp
  //    tile'ın ÜSTÜNE "API KEY REQUIRED" filigranı basmaya başladı. HTTP 200
  //    dönüyordu, yani kod hatası gibi görünmüyordu — resmin içindeydi.
  // ⚠️ Esri'de URL sırası {z}/{y}/{x} (Leaflet'in alışıldık {z}/{x}/{y}'si DEĞİL).
  // ⚠️ Bu servis zoom 16'ya kadar tile üretir; maxNativeZoom olmadan 17+ zoom'da
  //    ekran boşalır. Leaflet 16'nın karesini esnetsin diye ayrıldı.
  const _ESRI = 'https://server.arcgisonline.com/ArcGIS/rest/services/Canvas/World_Dark_Gray_';
  L.tileLayer(_ESRI + 'Base/MapServer/tile/{z}/{y}/{x}', {
    maxZoom: 19,
    maxNativeZoom: 16,
    attribution: '&copy; Esri'
  }).addTo(_lmap);

  // Etiketler ayrı katman — Esri'de yer adları zeminde değil "Reference"ta.
  // Sonra eklendiği için zeminin üstünde çizilir (Leaflet tilePane sırası).
  // Gözlemevi (11-13): etiketler işaretlerin üstünde ama tıklamayı yutmaz
  _lmap.createPane('mhEtiket'); _lmap.getPane('mhEtiket').style.zIndex = 640;
  _lmap.getPane('mhEtiket').style.pointerEvents = 'none';
  L.tileLayer(_ESRI + 'Reference/MapServer/tile/{z}/{y}/{x}', {
    maxZoom: 19,
    maxNativeZoom: 16,
    pane: 'mhEtiket'
  }).addTo(_lmap);

  L.control.zoom({ position: 'bottomright' }).addTo(_lmap);
  if (document.visibilityState !== 'hidden') setTimeout(() => _lmap.invalidateSize(), 100);

  // Mouse move → coords bar
  _lmap.on('mousemove', function(e) {
    const lat = e.latlng.lat.toFixed(4);
    const lon = e.latlng.lng.toFixed(4);
    document.getElementById('map-coords').textContent = `LAT ${lat} · LON ${lon}`;
  });
  // İmleç haritada değilken kutu harita MERKEZİNİ gösterir — açılışta "LAT — · LON —"
  // boş/bozuk görünüyordu (kişisel 09-28; telefonda imleç hiç yok).
  let _imlecHaritada = false;
  const _merkezYaz = () => {
    const el = document.getElementById('map-coords');
    if (!el || _imlecHaritada) return;
    const c = _lmap.getCenter();
    el.textContent = `LAT ${c.lat.toFixed(4)} · LON ${c.lng.toFixed(4)}`;
  };
  _lmap.on('mouseover', () => { _imlecHaritada = true; });
  _lmap.on('mouseout',  () => { _imlecHaritada = false; _merkezYaz(); });
  _lmap.on('moveend', _merkezYaz);
  _merkezYaz();

  // Click → confirm popup → ask Yuki
  _lmap.on('click', function(e) {
    const lat = e.latlng.lat.toFixed(4);
    const lon = e.latlng.lng.toFixed(4);

    if (_clickMarker) _lmap.removeLayer(_clickMarker);
    // Renk CSS'te (`.lf-isaret-secim`, token) — SVG özniteliğine var() yazılamaz,
    // sınıf kuralı özniteliği ezer. Eskiden altındı (#c8962a): haritada seçim mor.
    _clickMarker = L.circleMarker([e.latlng.lat, e.latlng.lng], {
      radius: 7, fillOpacity: 0.85, weight: 2, className: 'lf-isaret-secim'
    }).addTo(_lmap);

    fetchCityName(parseFloat(lat), parseFloat(lon)).then(city => {
      const query = city
        ? _mt('harita.sor.konum-sehirli', { sehir: city, lat, lon })
        : _mt('harita.sor.konum-koordinat', { lat, lon });
      updateMapLocation(parseFloat(lat), parseFloat(lon), city);
      mapConfirmShow(lat, lon, city, query);
    });
  });

  // Geolocation
  if (navigator.geolocation) {
    navigator.geolocation.getCurrentPosition(
      pos => _onGeoSuccess(pos.coords.latitude, pos.coords.longitude),
      ()  => fetchIPLocation()
    );
  } else {
    fetchIPLocation();
  }
}

function _onGeoSuccess(lat, lon) {
  if (_userMarker) _lmap.removeLayer(_userMarker);
  _userMarker = L.circleMarker([lat, lon], {
    radius: 6, fillOpacity: 0.25, weight: 2, className: 'lf-marker-user'   // renk CSS'te (mor)
  }).addTo(_lmap).bindTooltip(_mt('harita.konumunuz'), { permanent: false });
  _lmap.setView([lat, lon], 8);
  fetchCityName(lat, lon).then(city => updateMapLocation(lat, lon, city));
  fetchWeather(lat, lon);
  updateSpaceCard(lat, lon);
  startMapRefresh();
  if (window.mapYakinGuncelle) window.mapYakinGuncelle();   // YAKINDA: uzaklıklar artık hesaplanabilir (map-hud.js)
}

// ══════════════════════════════════════════════════════
//  MAP LAYERS — Earthquakes / Wildfires / Flights
// ══════════════════════════════════════════════════════
const _layerGroups = { eq: null, fire: null, plane: null, iss: null, volcano: null, weather: null, air: null, ship: null, adsb: null, eonet: null, sat: null, cctv: null, asteroid: null, military: null, livestream: null, poi: null, kpindex: null, osmplaces: null };
const _layerActive = { eq: false, fire: false, plane: false, iss: false, volcano: false, weather: false, air: false, ship: false, adsb: false, eonet: false, sat: false, cctv: false, asteroid: false, military: false, livestream: false, poi: false, kpindex: false, osmplaces: false };
const _layerMeta   = {};
const _layerFilters = { eq: { min_mag: 2.5, period: 'day' } };

/* ── Katman adı TEK KAYNAK (i18n, 2026-09-20) ──────────────────────────────
   Adlar bu dosyada **iki yerde** duruyordu: `_fetchLayer`'ın simgeli
   `_labelMap`'i (düğme metni) ve `renderLayerList`'in simgesiz `labelMap`'i
   (liste satırı). Çeviriye açarken ikisini ayrı anahtarlara bağlamak, aynı
   adın iki sözlük girdisi demekti — biri düzeltilir, öbürü bayatlar.

   2026-10-04: simgeli düğme etiketi (`_KATMAN_SIMGE` + `_katmanEtiketi`)
   mod çubuğuyla birlikte kalktı. KATMANLAR çekmecesinin satır adı aynı
   anahtarı `data-i18n="harita.katman.<k>"` ile okuyor — tek kaynak bozulmadı. */

/* Simgesiz ad — liste satırı, toast, `_staleNote` etiketi. */
function _katmanAdi(key) {
  const a = _mt('harita.katman.' + key);
  return a === 'harita.katman.' + key ? String(key).toUpperCase() : a;
}

/* PM2.5 → hava kalitesi sınıfı. Eşikler koddaydı, metin de koddaydı; metin
   çeviriye açılınca eşiğin ayrı bir yerde kalması iki kaynak üretirdi. */
function _aqiSinif(pm25) {
  return pm25 <= 50 ? 'iyi' : pm25 <= 100 ? 'orta' : pm25 <= 150 ? 'hassas' : 'sagliksiz';
}

/* NASA EONET kategori adı — API **İngilizce** döndürür (`Wildfires`,
   `Severe Storms`). Türkçe arayüzde ham değeri basmak, çevrilmemiş bir kalem
   değil **çevrilmemiş bir veri kaynağıdır**; ikisi de kullanıcıya aynı görünür.
   ⚠️ Bilinmeyen kategori gelirse ham değere düşülür — NASA listeye yeni tür
   eklediğinde ekranda anahtar adı görünmesin. */
function _eonetKat(ad) {
  if (!ad) return '';
  const k = 'harita.eonet-kat.' + String(ad).toLowerCase().replace(/[^a-z0-9]+/g, '-');
  const c = _mt(k);
  return c === k ? ad : c;
}

/* NOAA Kp fırtına seviyesi. Eski `kpLabelsTR` adı çeviriden sonra yanıltıcı
   olurdu — "TR" soneki metnin dilini iddia ediyordu. */
function _kpSeviye(level) {
  return _mt('harita.kp-seviye.' + (level || 'calm'));
}

/* 🔴 Üçüncü taraf URL'siyle bağlantı kurar. `href`e ham dizge yazmak
   `javascript:` / `data:` şemalarını da kabul eder; bu dosyanın URL kaynakları
   OpenStreetMap (herkesin düzenleyebildiği) ve NASA/USGS beslemeleridir.
   Şema beyaz listeyle sınırlanır; geçersizse bağlantı DEĞİL düz metin döner —
   kullanıcı bilgiyi yine görür, tıklanabilir olmaz. */
function _guvenliBag(url, metin) {
  let u;
  try { u = new URL(String(url), window.location.href); }
  catch (_) { return _escHtml(metin); }
  if (u.protocol !== 'http:' && u.protocol !== 'https:') return _escHtml(metin);
  return `<a href="${_escHtml(u.href)}" target="_blank" rel="noopener noreferrer">${_escHtml(metin)}</a>`;
}

/* ── İşaretçi BRİFİNGİ (2026-10-04) ────────────────────────────────
   Kişiselde işaretçiye tık `intelBrief` → `POST /api/intel/brief` idi (kendi
   LLM çağrısı + TTS paneli). Üründe o uç YOK ve ikinci bir LLM yolu açılmaz
   (tek motor kuralı — chat_sync 3 ay araçsız koştu). Brifing sohbetin KENDİ
   gönderim yolundan gider (`mapSendMessage` → core.js `sendMessage`), cevap
   SOHBET'te akar; haritada yalnız "cevap SOHBET'te" onayı kalır.
   🔑 Tık → popup, brifing popup'taki DÜĞMEDE: her işaretçi tıklaması sohbete
   mesaj atsaydı yanlış dokunuş kullanıcının mesaj hakkını yer ve sohbet
   geçmişini kirletirdi (kişiselde bedeli geliştirici ödüyordu, üründe müşteri).
   Düğme satır içi onclick TAŞIMAZ: soru `data-brifing`'de kaçışlı durur, tek
   belge dinleyicisi okur (başlık tırnak/HTML içerse de kaçış sorunu çıkmaz). */
function _brifingDugme(soru) {
  return `<br><button type="button" class="lf-brifing" data-brifing="${_escHtml(soru)}">` +
         `${_escHtml(_mt('harita.brifing-iste'))}</button>`;
}
document.addEventListener('click', function (e) {
  const b = e.target.closest && e.target.closest('.lf-brifing');
  if (!b) return;
  const soru = b.getAttribute('data-brifing') || '';
  if (!soru) return;
  if (_lmap) _lmap.closePopup();
  mapSendMessage(soru);
});
let _issInterval = null;
let _adsbInterval = null;
let _satInterval  = null;
let _eqInterval   = null;
let _fireInterval = null;

// ── Katman anahtarının GÖRÜNÜR durumu (2026-10-04, HARİTA ÖNCE — kişisel 09-28) ──
// Anahtar artık KATMANLAR çekmecesindeki satırın kendisi (role="switch"). Eski
// kod `_fetchLayer`'da düğmenin textContent'ine "⏳ …" yazıp geri alıyordu; satırın
// içinde ad + sayı + açıklama + anahtar olduğu için o yazım satırı SİLERDİ.
// Yükleniyor durumu artık sınıf + aria-busy, açık/kapalı aria-checked; metne
// dokunulmuyor (ad `data-i18n` ile dil.js'in).
function _katmanYukleniyor(key, on) {
  const b = document.getElementById('map-layer-' + key);
  if (!b) return;
  b.classList.toggle('yukleniyor', !!on);
  b.setAttribute('aria-busy', on ? 'true' : 'false');
}
function _katmanUiSenk(key) {
  const b = document.getElementById('map-layer-' + key);
  if (b) {
    const on = !!_layerActive[key];
    b.classList.toggle(key + '-on', on);
    b.setAttribute('aria-checked', on ? 'true' : 'false');
    if (!on) { const n = b.querySelector('.mk-sayi'); if (n) n.textContent = ''; }
  }
  if (typeof window.mapKatmanSay === 'function') window.mapKatmanSay();
}

function toggleLayer(key) {
  _layerActive[key] = !_layerActive[key];
  _katmanUiSenk(key);
  if (_layerActive[key]) {
    _fetchLayer(key);
    if (key === 'iss') {
      _issInterval = setInterval(() => { if (_layerActive['iss']) _fetchLayer('iss'); }, 5000);
    }
    if (key === 'adsb') {
      _adsbInterval = setInterval(() => { if (_layerActive['adsb']) _fetchLayer('adsb'); }, 15000);
    }
    if (key === 'sat') {
      _satInterval = setInterval(() => { if (_layerActive['sat']) _fetchLayer('sat'); }, 30000);
    }
    if (key === 'eq') {
      // backend TTL 120s — canlı afet takibi, katman açıkken kendiliğinden tazelenir
      _eqInterval = setInterval(() => { if (_layerActive['eq']) _fetchLayer('eq'); }, 120000);
    }
    if (key === 'fire') {
      // backend TTL 600s — daha sık istek cache'ten döner, boşa gürültü olur
      _fireInterval = setInterval(() => { if (_layerActive['fire']) _fetchLayer('fire'); }, 600000);
    }
  } else {
    if (_layerGroups[key]) { _lmap.removeLayer(_layerGroups[key]); _layerGroups[key] = null; }
    if (key === 'iss'  && _issInterval)  { clearInterval(_issInterval);  _issInterval  = null; }
    if (key === 'adsb' && _adsbInterval) { clearInterval(_adsbInterval); _adsbInterval = null; }
    if (key === 'sat'  && _satInterval)  { clearInterval(_satInterval);  _satInterval  = null; }
    if (key === 'eq'   && _eqInterval)   { clearInterval(_eqInterval);   _eqInterval   = null; }
    if (key === 'fire' && _fireInterval) { clearInterval(_fireInterval); _fireInterval = null; }
    delete _layerMeta[key];
  }
  saveLayerState();
  renderLayerList();
}

function _staleNote(d, label) {
  // Backend dayanıklılık katmanı upstream düşünce son-iyi-veriyi stale:true ile döner
  if (d && d.stale) {
    const dk = Math.max(1, Math.round((d.age_s || 0) / 60));
    showToast(_mt('harita.kaynak-bayat', { katman: label, dk }), 'error');
  }
}

async function _fetchLayer(key) {
  if (!_lmap) return;
  if (_layerGroups[key]) _lmap.removeLayer(_layerGroups[key]);
  let g = L.layerGroup();
  const btn = document.getElementById('map-layer-' + key);
  _katmanYukleniyor(key, true);
  const _safetyTimer = setTimeout(() => {
    if (btn && btn.classList.contains('yukleniyor')) {
      _katmanYukleniyor(key, false);
      _layerActive[key] = false;
      _katmanUiSenk(key);
      showToast(_mt('harita.zaman-asimi', { katman: _katmanAdi(key) }), 'error');
    }
  }, 30000);
  try {
    if (key === 'eq') {
      const f = _layerFilters.eq || { min_mag: 2.5, period: 'day' };
      const r = await authFetch(`${BASE_URL}/api/map/earthquakes?min_mag=${f.min_mag}&period=${f.period}`);
      const d = await r.json();
      if (d.error) throw new Error(d.error);
      _staleNote(d, _katmanAdi(key));
      for (const feat of d.features) {
        const [lon, lat, depth] = feat.geometry.coordinates;
        const mag   = feat.properties.mag;
        const place = feat.properties.place;
        const r_px  = Math.max(5, mag * 3);
        const sz    = r_px * 2;
        const col   = mag >= 6 ? '#ff1744' : mag >= 4 ? '#ff9100' : '#ff6b35';
        const eqIcon = L.divIcon({
          html: `<div class="map-pulse-dot mh-dep${Date.now() - feat.properties.time < 3600000 ? ' yeni' : ''}" style="width:${sz}px;height:${sz}px;background:${col}40;border:1.5px solid ${col};color:${col};border-radius:50%;"></div>`,
          className: '', iconSize: [sz, sz], iconAnchor: [sz/2, sz/2]
        });
        // Yer adı backend'den kaynak ekiyle gelir: "Saimbeyli (Adana) (AFAD)" — çift
        // parantez. Ek ayrılır, kaynak ayrı ve sönük yazılır (göz tur 2).
        const _ek  = String(place || '').match(/\s*\((AFAD|USGS|EMSC|Kandilli|KOERI|Sismik[^)]*)\)\s*$/i);
        const _yer = _ek ? String(place).slice(0, _ek.index) : String(place || '');
        L.marker([lat, lon], { icon: eqIcon })
          .bindPopup(`<b>M${mag}</b><br>${_escHtml(_yer)}` +
                     (_ek ? ` <span class="lf-kaynak">· ${_escHtml(_ek[1])}</span>` : '') +
                     `<br>${_escHtml(_mt('harita.derinlik', { km: depth.toFixed(0) }))}` +
                     _brifingDugme(_mt('harita.sor.brifing-deprem', { mag, yer: _yer, km: depth.toFixed(0) })))
          .addTo(g);
      }
      _layerMeta[key] = { count: d.features.length, ts: Date.now() };
      window._mapEqSon = d.features; if (window.mapYakinGuncelle) window.mapYakinGuncelle();   // YAKINDA (map-hud.js)
      _3dCache['eq'] = d.features; if (_3dActive && _3dReady) _3dUpdateEq();
      _katmanYukleniyor(key, false);
      // Kaynak dağılımı: hangi besleme kaç olay kattı — sismikharita.com'un
      // (Kandilli/EMSC) katkısı çift-marker elemesinden SONRAKİ sayıdır
      const _kaynak = [
        d.afad   ? `AFAD ${d.afad}`     : '',
        d.usgs   ? `USGS ${d.usgs}`     : '',
        d.sismik ? `Sismik ${d.sismik}` : '',
      ].filter(Boolean).join(' · ').replace(/ /g, '\u00a0');   // bölünmez boşluk: "·" satır sonunda kalmasın
      showToast(_mtc('harita.deprem-yuklendi', d.features.length, { sayi: d.features.length, mag: f.min_mag, period: _mt('harita.periyot.' + f.period) })
                + (_kaynak ? ` — ${_kaynak}` : ''));
      // Sessiz kırpma "her şey kapsandı" gibi okunur — AFAD tavana dayandıysa söyle
      if (d.afad_kirpildi) showToast(_mt('harita.afad-kirpildi'), 'error');
      renderLayerList();
    } else if (key === 'fire') {
      // NASA FIRMS — backend proxy (CORS engeli)
      const r = await authFetch(BASE_URL + '/api/map/fires');
      const d = await r.json();
      if (d.error) throw new Error(d.error);
      _staleNote(d, _katmanAdi(key));
      for (const f of d.fires) {
        const color = f.conf === 'h' ? '#ff1744' : '#ff6d00';
        L.circleMarker([f.lat, f.lon], {
          radius: 3, color, fillColor: color,
          fillOpacity: 0.6, weight: 0
        }).bindPopup(`🔥 ${_escHtml(_mt('harita.aktif-yangin'))}<br>${_escHtml(_mt('harita.guven', { deger: f.conf }))}`)
          .addTo(g);
      }
      _3dCache['fire'] = d.fires; if (_3dActive && _3dReady) _3dUpdateFire();
      _katmanYukleniyor(key, false);
      showToast(_mtc('harita.yangin-yuklendi', d.fires.length, { sayi: d.fires.length }));
    } else if (key === 'plane') {
      // OpenSky Network — backend proxy (CORS + rate limit)
      const r = await authFetch(BASE_URL + '/api/map/flights');
      const d = await r.json();
      if (d.error === 'rate_limited') throw new Error(_mt('harita.opensky-limit'));
      if (d.error) throw new Error(d.error);
      _staleNote(d, _katmanAdi(key));
      const states = d.states || [];
      for (const s of states) {
        const lon  = s[5], lat = s[6];
        const call = (s[1] || '').trim() || '—';
        const alt  = s[7] ? (s[7] / 1000).toFixed(1) + ' km' : '—';
        if (!lat || !lon) continue;
        L.circleMarker([lat, lon], {
          radius: 3, color: '#00e676', fillColor: '#00e676',
          fillOpacity: 0.7, weight: 0
        }).bindPopup(`✈ ${_escHtml(call)}<br>${_escHtml(_mt('harita.irtifa', { deger: alt }))}`)
          .addTo(g);
      }
      _3dCache['plane'] = states; if (_3dActive && _3dReady) _3dUpdatePlane();
      _katmanYukleniyor(key, false);
      showToast(_mtc('harita.ucus-yuklendi', states.length, { sayi: states.length }));
    } else if (key === 'iss') {
      // ISS anlık konum — wheretheiss.at, CORS-safe
      const r = await fetch('https://api.wheretheiss.at/v1/satellites/25544');
      const d = await r.json();
      // Gözlemevi (11-13): elmas + "ISS · irtifa" etiketi (stil map-gozlemevi.css .mh-iss)
      const issIcon = L.divIcon({
        html: `<div class="mh-iss"><i></i><span>ISS · ${Math.round(d.altitude)} km</span></div>`,
        className: '', iconSize: [16, 16], iconAnchor: [8, 8]
      });
      L.marker([d.latitude, d.longitude], { icon: issIcon })
        .bindPopup(`🛸 ISS<br>Lat: ${d.latitude.toFixed(4)}<br>Lon: ${d.longitude.toFixed(4)}<br>${_escHtml(_mt('harita.irtifa-km', { km: (d.altitude).toFixed(1) }))}<br>${_escHtml(_mt('harita.hiz-kms', { hiz: (d.velocity).toFixed(0) }))}`)
        .addTo(g);
      _katmanYukleniyor(key, false);
      if (!_layerActive['iss']) showToast(_mt('harita.iss-yuklendi'));
    } else if (key === 'volcano') {
      // USGS Volcano Hazards — CORS-safe, backend proxy daha güvenli
      const r = await authFetch(BASE_URL + '/api/map/volcanoes');
      const d = await r.json();
      if (d.error) throw new Error(d.error);
      _staleNote(d, _katmanAdi(key));
      const alertColor = { 'Normal': '#69f0ae', 'Advisory': '#ffd740', 'Watch': '#ff9100', 'Warning': '#ff1744' };
      for (const v of d.volcanoes) {
        const color = alertColor[v.alert] || '#aaa';
        L.circleMarker([v.lat, v.lon], {
          radius: 6, color, fillColor: color,
          fillOpacity: 0.7, weight: 1
        }).bindPopup(`🌋 ${_escHtml(v.name)}<br>${_escHtml(_mt('harita.uyari-seviyesi', { seviye: _mt('harita.volkan-alarm.' + String(v.alert || '').toLowerCase()) }))}<br>${_escHtml(_mt('harita.ulke', { ad: v.country }))}` +
                   _brifingDugme(_mt('harita.sor.brifing-volkan', { ad: v.name, seviye: _mt('harita.volkan-alarm.' + String(v.alert || '').toLowerCase()), ulke: v.country || '—' })))
          .addTo(g);
      }
      _3dCache['volcano'] = d.volcanoes; if (_3dActive && _3dReady) _3dUpdateVolcano();
      _katmanYukleniyor(key, false);
      showToast(_mtc('harita.volkan-yuklendi', d.volcanoes.length, { sayi: d.volcanoes.length }));
    } else if (key === 'weather') {
      // Open-Meteo hava durumu (şehirler) — backend proxy
      const r = await authFetch(BASE_URL + '/api/map/weather');
      const d = await r.json();
      if (d.error) throw new Error(d.error);
      _staleNote(d, _katmanAdi(key));
      const wmoEmoji = wc => {
        if (wc === 0) return '☀️';
        if (wc <= 3) return '⛅';
        if (wc <= 48) return '🌫️';
        if (wc <= 67) return '🌧️';
        if (wc <= 77) return '❄️';
        if (wc <= 82) return '🌦️';
        return '⛈️';
      };
      for (const c of d.cities) {
        const emoji = wmoEmoji(c.wmo);
        const icon = L.divIcon({
          html: `<div style="font-size:14px;line-height:1;text-shadow:0 0 4px #000;">${emoji}</div>`,
          className: '', iconAnchor: [7, 7]
        });
        L.marker([c.lat, c.lon], { icon })
          .bindPopup(`${emoji} ${_escHtml(c.city)}<br>${c.temp}°C<br>${_escHtml(_mt('harita.wmo-kodu', { kod: c.wmo }))}`)
          .addTo(g);
      }
      _katmanYukleniyor(key, false);
      showToast(_mtc('harita.hava-yuklendi', d.cities.length, { sayi: d.cities.length }));
    } else if (key === 'air') {
      // OpenAQ PM2.5 hava kalitesi — backend proxy (API key gerekli)
      const r = await authFetch(BASE_URL + '/api/map/airquality');
      const d = await r.json();
      if (d.error) throw new Error(d.error);
      _staleNote(d, _katmanAdi(key));
      const aqiColor = v => v <= 50 ? '#69f0ae' : v <= 100 ? '#ffd740' : v <= 150 ? '#ff9100' : '#ff1744';
      for (const s of d.stations) {
        const color = aqiColor(s.pm25);
        L.circleMarker([s.lat, s.lon], {
          radius: 5, color, fillColor: color,
          fillOpacity: 0.75, weight: 1
        }).bindPopup(`🌬 ${_escHtml(s.city)}<br>PM2.5: ${s.pm25} µg/m³<br>${_escHtml(_mt('harita.hava-kalitesi.' + _aqiSinif(s.pm25)))}`)
          .addTo(g);
      }
      _katmanYukleniyor(key, false);
      showToast(_mtc('harita.pm25-yuklendi', d.stations.length, { sayi: d.stations.length }));
    } else if (key === 'ship') {
      // AISStream gemi trafiği — backend proxy (WebSocket cache)
      const r = await authFetch(BASE_URL + '/api/map/ships');
      const d = await r.json();
      if (d.error) throw new Error(d.error);
      const shipIcon = L.divIcon({
        html: '<div style="font-size:14px;line-height:1;">🚢</div>',
        className: '', iconAnchor: [7, 7]
      });
      for (const s of d.ships) {
        L.marker([s.lat, s.lon], { icon: shipIcon })
          .bindPopup(`🚢 ${_escHtml(s.name || s.mmsi)}<br>${_escHtml(_mt('harita.hiz-kn', { hiz: s.sog || '—' }))}<br>${_escHtml(_mt('harita.baslik', { derece: s.cog || '—' }))}` +
                     _brifingDugme(_mt('harita.sor.brifing-gemi', { ad: s.name || s.mmsi, lat: Number(s.lat).toFixed(2), lon: Number(s.lon).toFixed(2), hiz: s.sog || '—', derece: s.cog || '—' })))
          .addTo(g);
      }
      _3dCache['ship'] = d.ships; if (_3dActive && _3dReady) _3dUpdateShip();
      _katmanYukleniyor(key, false);
      showToast(_mtc('harita.gemi-yuklendi', d.ships.length, { sayi: d.ships.length }));
    } else if (key === 'adsb') {
      // airplanes.live ADS-B — backend proxy (CORS engeli)
      const r = await authFetch(BASE_URL + '/api/map/adsb');
      const d = await r.json();
      if (d.error) throw new Error(d.error);
      for (const ac of d.aircraft) {
        if (!ac.lat || !ac.lon) continue;
        const hdg = ac.track || 0;
        const icon = L.divIcon({
          html: `<div style="font-size:16px;line-height:1;transform:rotate(${hdg}deg);display:inline-block;">✈</div>`,
          className: '', iconAnchor: [8, 8]
        });
        L.marker([ac.lat, ac.lon], { icon })
          .bindPopup(`✈ ${_escHtml(ac.flight || ac.hex || '—')}<br>${_escHtml(_mt('harita.irtifa', { deger: ac.alt_baro ? ac.alt_baro + ' ft' : '—' }))}<br>${_escHtml(_mt('harita.hiz-kn', { hiz: ac.gs ? Math.round(ac.gs) : '—' }))}<br>${_escHtml(_mt('harita.baslik', { derece: hdg }))}`)
          .addTo(g);
      }
      _3dCache['adsb'] = d.aircraft; if (_3dActive && _3dReady) _3dUpdateAdsb();
      _katmanYukleniyor(key, false);
      showToast(_mtc('harita.adsb-yuklendi', d.aircraft.length, { sayi: d.aircraft.length }));
    } else if (key === 'eonet') {
      // NASA EONET — doğal afetler, CORS-safe, direkt fetch
      const r = await fetch('https://eonet.gsfc.nasa.gov/api/v3/events?status=open&limit=100');
      const d = await r.json();
      const catEmoji = { 'Wildfires': '🔥', 'Volcanoes': '🌋', 'Severe Storms': '🌪️', 'Floods': '🌊', 'Earthquakes': '📍', 'Drought': '☀️', 'Dust and Haze': '🌫️', 'Sea and Lake Ice': '🧊', 'Snow': '❄️', 'Landslides': '⛰️' };
      let count = 0;
      const _eonetPts = [];
      for (const ev of d.events) {
        const cat = ev.categories?.[0]?.title || '';
        const emoji = catEmoji[cat] || '⚠️';
        const geo = ev.geometry?.[ev.geometry.length - 1];
        if (!geo || geo.type !== 'Point') continue;
        const [lon, lat] = geo.coordinates;
        _eonetPts.push({ lon, lat, title: ev.title, cat });
        L.circleMarker([lat, lon], {
          radius: 6, color: '#ff9100', fillColor: '#ff9100',
          fillOpacity: 0.65, weight: 1
        }).bindPopup(`${emoji} ${_escHtml(ev.title)}<br>${_escHtml(_mt('harita.kategori', { ad: _eonetKat(cat) }))}` +
                     _brifingDugme(_mt('harita.sor.brifing-afet', { baslik: ev.title, kategori: _eonetKat(cat) })))
          .addTo(g);
        count++;
      }
      _3dCache['eonet'] = _eonetPts; if (_3dActive && _3dReady) _3dUpdateEonet();
      _katmanYukleniyor(key, false);
      showToast(_mtc('harita.afet-yuklendi', count, { sayi: count }));
    } else if (key === 'sat') {
      // CelesTrak TLE + satellite.js SGP4 — uydu takımyıldızı konumları
      if (typeof satellite === 'undefined') throw new Error(_mt('harita.satellitejs-yok'));
      const r = await authFetch(BASE_URL + '/api/map/satellites?group=visual');
      const d = await r.json();
      if (d.error) throw new Error(d.error);
      const now = new Date();
      let count = 0;
      const _satPts = [];
      for (const sat of d.satellites) {
        try {
          const satrec  = satellite.twoline2satrec(sat.tle1, sat.tle2);
          const posVel  = satellite.propagate(satrec, now);
          if (!posVel || !posVel.position || posVel.position === false) continue;
          const gmst    = satellite.gstime(now);
          const geo     = satellite.eciToGeodetic(posVel.position, gmst);
          const lat     = satellite.degreesLat(geo.latitude);
          const lon     = satellite.degreesLong(geo.longitude);
          const alt     = (geo.height).toFixed(0);
          const vel     = posVel.velocity
            ? Math.sqrt(posVel.velocity.x**2 + posVel.velocity.y**2 + posVel.velocity.z**2).toFixed(2)
            : '—';
          if (!isFinite(lat) || !isFinite(lon)) continue;
          if (lat < -90 || lat > 90 || lon < -180 || lon > 180) continue;
          _satPts.push({ lat, lon, name: sat.name });
          L.circleMarker([lat, lon], {
            radius: 3, color: '#00d4ff', fillColor: '#00d4ff',
            fillOpacity: 0.85, weight: 1
          }).bindPopup(`🛰 ${_escHtml(sat.name)}<br>${_escHtml(_mt('harita.irtifa-km', { km: alt }))}<br>${_escHtml(_mt('harita.hiz-kms', { hiz: vel }))}`)
            .addTo(g);
          count++;
        } catch (_) { continue; }
      }
      _3dCache['sat'] = _satPts; if (_3dActive && _3dReady) _3dUpdateSat();
      _katmanYukleniyor(key, false);
      showToast(_mtc('harita.uydu-yuklendi', count, { sayi: count }));
    } else if (key === 'cctv') {
      // NYC DOT / Chicago / Austin açık trafik kameraları — Faz 2: stream proxy + auto-refresh
      // Cluster group: yüzlerce işaretçiyi zoom seviyesine göre kümeler
      if (typeof L.markerClusterGroup !== 'undefined') {
        g = L.markerClusterGroup({
          maxClusterRadius: 60,
          spiderfyOnMaxZoom: true,
          showCoverageOnHover: false,
          zoomToBoundsOnClick: true,
          iconCreateFunction: function(cluster) {
            const cnt = cluster.getChildCount();
            const size = cnt > 100 ? 44 : cnt > 50 ? 38 : cnt > 20 ? 32 : 26;
            return L.divIcon({
              html: `<div style="width:${size}px;height:${size}px;display:flex;align-items:center;justify-content:center;background:rgba(0,13,31,0.88);border:1.5px solid rgba(0,212,255,0.7);border-radius:50%;font-family:monospace;font-size:${size > 36 ? 12 : 11}px;color:#00d4ff;font-weight:700;box-shadow:0 0 10px rgba(0,212,255,0.4),inset 0 0 8px rgba(0,212,255,0.08);">📷${cnt}</div>`,
              className: '',
              iconSize: [size, size],
              iconAnchor: [size/2, size/2]
            });
          }
        });
      }
      const r = await authFetch(BASE_URL + '/api/map/cctv');
      const d = await r.json();
      if (d.error) throw new Error(d.error);
      const cctvIcon = L.divIcon({
        html: '<div style="font-size:16px;line-height:1;filter:drop-shadow(0 0 4px #00d4ff);">📷</div>',
        className: '', iconAnchor: [8, 8]
      });
      // Auto-refresh timer — popup açıkken 10s'de bir snapshot yeniler
      let _cctvRefreshTimer = null;
      const _cctvTok = localStorage.getItem('aliceToken') || '';
      const _cctvTokParam = _cctvTok ? '&token=' + encodeURIComponent(_cctvTok) : '';
      for (const cam of d.cameras) {
        if (!cam.lat || !cam.lon) continue;
        const camIdx = Date.now() + Math.random(); // benzersiz img ID
        const imgId  = 'cctv-img-' + camIdx.toString(36);
        // Stream proxy URL (MJPEG varsa canlı, snapshot'sa tek kare)
        const streamSrc = cam.img_url
          ? BASE_URL + '/api/stream/proxy?url=' + encodeURIComponent(cam.img_url) + _cctvTokParam
          : '';
        const fallbackSrc = cam.img_url
          ? BASE_URL + '/api/cctv/img?url=' + encodeURIComponent(cam.img_url) + _cctvTokParam
          : '';
        const imgHtml = streamSrc
          ? `<div style="position:relative;display:inline-block;">` +
            `<img id="${imgId}" src="${streamSrc}" ` +
            `style="width:240px;height:135px;object-fit:cover;border:1px solid #00d4ff;border-radius:2px;display:block;margin-top:4px;" ` +
            `onerror="this.src='${fallbackSrc}'" ` +
            `crossorigin="anonymous">` +
            `<span style="position:absolute;top:8px;right:4px;background:#e53935;color:#fff;font-size:9px;` +
            `font-family:monospace;padding:1px 5px;border-radius:2px;letter-spacing:1px;">${_escHtml(_mt('harita.canli'))}</span>` +
            `</div>`
          : `<span style="color:#888;font-size:11px;">${_escHtml(_mt('harita.goruntu-yok'))}</span>`;
        const marker = L.marker([cam.lat, cam.lon], { icon: cctvIcon });
        marker.bindPopup(
          `<div style="font-family:monospace;font-size:12px;color:#00d4ff;">` +
          `📷 ${_escHtml(cam.name)}<br><span style="color:#aaa;font-size:10px;">${_escHtml(cam.city)}</span>` +
          `</div>${imgHtml}`,
          { maxWidth: 264, minWidth: 264 }
        );
        // Popup açılınca auto-refresh başlat (snapshot kameralar için), kapanınca durdur
        if (fallbackSrc) {
          marker.on('popupopen', () => {
            _cctvRefreshTimer = setInterval(() => {
              const el = document.getElementById(imgId);
              if (el) el.src = fallbackSrc + '&_t=' + Date.now();
            }, 10000);
          });
          marker.on('popupclose', () => {
            if (_cctvRefreshTimer) { clearInterval(_cctvRefreshTimer); _cctvRefreshTimer = null; }
          });
        }
        marker.addTo(g);
      }
      _katmanYukleniyor(key, false);
      showToast(_mtc('harita.cctv-yuklendi', d.cameras.length, { sayi: d.cameras.length }));

    } else if (key === 'asteroid') {
      const r = await authFetch(BASE_URL + '/api/map/asteroids');
      const d = await r.json();
      if (d.error) throw new Error(d.error);
      const asteroids = d.asteroids || [];
      // Dünya etrafında ring'e dağıt (gerçek koordinat yok)
      asteroids.forEach((ast, i) => {
        const angle = (i / asteroids.length) * 360;
        const lat = 20 * Math.sin((angle * Math.PI) / 180);
        const lon = ((angle + 180) % 360) - 180;
        const isHaz = ast.hazardous;
        const color = isHaz ? '#ff3333' : '#ff9100';
        const icon = L.divIcon({
          html: `<div style="font-size:${isHaz ? 18 : 13}px;filter:drop-shadow(0 0 5px ${color});">${isHaz ? '☄️' : '🪨'}</div>`,
          className: '', iconAnchor: [9, 9]
        });
        const marker = L.marker([lat, lon], { icon });
        const diamAvg = ((ast.diam_min + ast.diam_max) / 2).toFixed(3);
        marker.bindPopup(
          `<div style="font-family:monospace;font-size:11px;color:${color};">` +
          `${isHaz ? '⚠️ ' + _escHtml(_mt('harita.tehlikeli')) : '🪨 ' + _escHtml(_mt('harita.katman.asteroid'))}<br>` +
          `<b>${_escHtml(ast.name)}</b><br>` +
          `<span style="color:#aaa;">${_escHtml(_mt('harita.cap-km', { km: diamAvg }))}<br>` +
          `${_escHtml(_mt('harita.hiz-kms', { hiz: ast.vel_kms }))}<br>` +
          `${_escHtml(_mt('harita.mesafe-mkm', { mkm: (ast.miss_km / 1e6).toFixed(2) }))}<br>` +
          `${_escHtml(_mt('harita.tarih', { deger: ast.date }))}</span>` +
          _brifingDugme(_mt('harita.sor.brifing-asteroid', { ad: ast.name, km: diamAvg, mkm: (ast.miss_km / 1e6).toFixed(2), tarih: ast.date })) +
          `</div>`
        );
        marker.addTo(g);
      });
      _katmanYukleniyor(key, false);
      const hazCount = asteroids.filter(a => a.hazardous).length;
      showToast(_mt('harita.asteroid-yuklendi', { sayi: asteroids.length, tehlikeli: hazCount }));

    } else if (key === 'military') {
      const r = await authFetch(BASE_URL + '/api/map/military');
      const d = await r.json();
      if (d.error) throw new Error(d.error);
      const catColors = { airstrike: '#ff1744', missile: '#ff6d00', naval: '#00b0ff', ground: '#ff9100' };
      const catEmoji  = { airstrike: '💥', missile: '🚀', naval: '⚓', ground: '🎯' };
      for (const ev of (d.events || [])) {
        const color = catColors[ev.category] || '#ff1744';
        const emoji = catEmoji[ev.category] || '⚔️';
        const icon = L.divIcon({
          html: `<div style="font-size:16px;filter:drop-shadow(0 0 5px ${color});">${emoji}</div>`,
          className: '', iconAnchor: [8, 8]
        });
        const marker = L.marker([ev.lat, ev.lon], { icon });
        marker.bindPopup(
          `<div style="font-family:monospace;font-size:11px;color:${color};">` +
          `${emoji} <b>${_escHtml(ev.name)}</b><br>` +
          `<span style="color:#aaa;font-size:10px;text-transform:uppercase;">${_escHtml(_mt('harita.askeri-kat.' + ev.category))}</span><br>` +
          `<span style="color:#ccc;font-size:10px;">${_escHtml(ev.snippet)}</span>` +
          _brifingDugme(_mt('harita.sor.brifing-askeri', { baslik: ev.name, tur: _mt('harita.askeri-kat.' + ev.category) })) +
          `</div>`,
          { maxWidth: 280 }
        );
        marker.addTo(g);
      }
      _katmanYukleniyor(key, false);
      showToast(_mtc('harita.askeri-yuklendi', d.events.length, { sayi: d.events.length }));

    } else if (key === 'livestream') {
      const r = await authFetch(BASE_URL + '/api/map/livestreams');
      const d = await r.json();
      if (d.error) throw new Error(d.error);
      const catColor = { city: '#e040fb', landmark: '#ffd740', harbor: '#00b0ff', nature: '#69f0ae' };
      const catEmoji = { city: '🌆', landmark: '🏛', harbor: '⚓', nature: '🌿' };
      for (const s of (d.streams || [])) {
        const color = catColor[s.category] || '#e040fb';
        const emoji = catEmoji[s.category] || '📺';
        const icon = L.divIcon({
          html: `<div style="width:28px;height:28px;display:flex;align-items:center;justify-content:center;background:rgba(0,0,0,0.75);border:1.5px solid ${color};border-radius:4px;font-size:14px;box-shadow:0 0 8px ${color}40;">▶</div>`,
          className: '', iconSize: [28, 28], iconAnchor: [14, 14]
        });
        const ytUrl = `https://www.youtube.com/watch?v=${s.video_id}`;
        const embedUrl = `https://www.youtube.com/embed/${s.video_id}?autoplay=1&mute=1&controls=1`;
        const marker = L.marker([s.lat, s.lon], { icon });
        marker.bindPopup(
          `<div style="font-family:monospace;font-size:11px;color:${color};">` +
          `${emoji} <b>${_escHtml(s.name)}</b><br>` +
          `<span style="color:#aaa;font-size:10px;">${_escHtml(s.city)}</span>` +
          `</div>` +
          `<div style="margin-top:6px;">` +
          `<iframe width="256" height="144" src="${embedUrl}" frameborder="0" ` +
          `allow="autoplay;encrypted-media" allowfullscreen ` +
          `style="border:1px solid ${color}40;border-radius:3px;display:block;"></iframe>` +
          `</div>` +
          `<div style="margin-top:4px;text-align:right;">` +
          `<a href="${ytUrl}" target="_blank" style="color:${color};font-size:10px;font-family:monospace;text-decoration:none;">▶ ${_escHtml(_mt('harita.youtubeda-ac'))} ↗</a>` +
          `</div>`,
          { maxWidth: 280, minWidth: 270 }
        );
        marker.addTo(g);
      }
      _katmanYukleniyor(key, false);
      showToast(_mtc('harita.yayin-yuklendi', d.streams.length, { sayi: d.streams.length }));
      _layerMeta[key] = { count: d.streams.length, ts: Date.now() };

    } else if (key === 'osmplaces') {
      const zoom = _lmap.getZoom();
      if (zoom < 10) {
        showToast(_mt('harita.yerler-zoom-gerek'), 'warning');
        _layerActive[key] = false;
        _katmanYukleniyor(key, false); _katmanUiSenk(key);
        clearTimeout(_safetyTimer); return;
      }
      const b = _lmap.getBounds();
      const bbox = `${b.getSouth()},${b.getWest()},${b.getNorth()},${b.getEast()}`;
      const query = `
[out:json][timeout:20];
(
  node["amenity"~"restaurant|cafe|bar|fast_food"](${bbox});
  node["amenity"~"hospital|clinic|pharmacy|doctors"](${bbox});
  node["amenity"~"hotel|hostel|motel|guest_house"](${bbox});
  node["tourism"~"museum|attraction|gallery|viewpoint"](${bbox});
  node["amenity"~"bank|atm"](${bbox});
  node["shop"~"mall|supermarket|department_store"](${bbox});
  node["amenity"~"school|university|college"](${bbox});
  node["leisure"~"park|garden"](${bbox});
  node["amenity"="fuel"](${bbox});
);
out body 400;`;
      const overpassRes = await fetch('https://overpass-api.de/api/interpreter', {
        method: 'POST',
        body: 'data=' + encodeURIComponent(query)
      });
      const od = await overpassRes.json();
      const elements = od.elements || [];

      const catMap = {
        restaurant: { icon: '🍽️', color: '#ff7043', label: _mt('harita.poi.restaurant') },
        cafe:       { icon: '☕', color: '#a1887f', label: _mt('harita.poi.cafe') },
        bar:        { icon: '🍺', color: '#ffa726', label: _mt('harita.poi.bar') },
        fast_food:  { icon: '🍔', color: '#ef5350', label: _mt('harita.poi.fast_food') },
        hospital:   { icon: '🏥', color: '#ef5350', label: _mt('harita.poi.hospital') },
        clinic:     { icon: '🏥', color: '#ec407a', label: _mt('harita.poi.clinic') },
        pharmacy:   { icon: '💊', color: '#ab47bc', label: _mt('harita.poi.pharmacy') },
        doctors:    { icon: '👨‍⚕️', color: '#7e57c2', label: _mt('harita.poi.doctors') },
        hotel:      { icon: '🏨', color: '#42a5f5', label: _mt('harita.poi.hotel') },
        hostel:     { icon: '🛏️', color: '#29b6f6', label: _mt('harita.poi.hostel') },
        motel:      { icon: '🛏️', color: '#26c6da', label: _mt('harita.poi.motel') },
        guest_house:{ icon: '🏠', color: '#4dd0e1', label: _mt('harita.poi.guest_house') },
        museum:     { icon: '🏛️', color: '#ce93d8', label: _mt('harita.poi.museum') },
        attraction: { icon: '⭐', color: '#ffca28', label: _mt('harita.poi.attraction') },
        gallery:    { icon: '🖼️', color: '#ba68c8', label: _mt('harita.poi.gallery') },
        viewpoint:  { icon: '🔭', color: '#80cbc4', label: _mt('harita.poi.viewpoint') },
        bank:       { icon: '🏦', color: '#66bb6a', label: _mt('harita.poi.bank') },
        atm:        { icon: '💳', color: '#81c784', label: _mt('harita.poi.atm') },
        mall:       { icon: '🛍️', color: '#4db6ac', label: _mt('harita.poi.mall') },
        supermarket:{ icon: '🛒', color: '#4caf50', label: _mt('harita.poi.supermarket') },
        department_store:{ icon: '🏬', color: '#26a69a', label: _mt('harita.poi.department_store') },
        school:     { icon: '🏫', color: '#ffa000', label: _mt('harita.poi.school') },
        university: { icon: '🎓', color: '#ff8f00', label: _mt('harita.poi.university') },
        college:    { icon: '📚', color: '#ffc107', label: _mt('harita.poi.college') },
        park:       { icon: '🌳', color: '#66bb6a', label: _mt('harita.poi.park') },
        garden:     { icon: '🌸', color: '#81c784', label: _mt('harita.poi.garden') },
        fuel:       { icon: '⛽', color: '#90a4ae', label: _mt('harita.poi.fuel') },
      };

      let count = 0;
      for (const el of elements) {
        if (!el.lat || !el.lon) continue;
        const amenity = el.tags?.amenity || el.tags?.tourism || el.tags?.shop || el.tags?.leisure || '';
        const meta = catMap[amenity] || { icon: '📍', color: '#00d4ff', label: amenity };
        const name = el.tags?.name || el.tags?.['name:tr'] || meta.label;

        const icon = L.divIcon({
          html: `<div style="
            display:flex;align-items:center;justify-content:center;
            width:26px;height:26px;border-radius:50%;
            background:rgba(10,12,18,0.88);
            border:1.5px solid ${meta.color};
            font-size:13px;cursor:pointer;
            box-shadow:0 0 6px ${meta.color}55;
            ">${meta.icon}</div>`,
          className: '',
          iconSize: [26, 26],
          iconAnchor: [13, 13]
        });

        const placeData = {
          name: name,
          label: meta.label,
          icon: meta.icon,
          color: meta.color,
          lat: el.lat,
          lon: el.lon,
          address: [el.tags?.['addr:street'], el.tags?.['addr:housenumber'], el.tags?.['addr:city']]
                     .filter(Boolean).join(' ') || el.tags?.['addr:full'] || '',
          phone:   el.tags?.phone || el.tags?.['contact:phone'] || '',
          website: el.tags?.website || el.tags?.['contact:website'] || '',
          hours:   el.tags?.opening_hours || '',
          email:   el.tags?.email || el.tags?.['contact:email'] || '',
          wikipedia: el.tags?.wikipedia?.replace(/^[a-z]+:/, '') || '',
        };

        L.marker([el.lat, el.lon], { icon })
          .on('click', () => showPlaceDetail(placeData))
          .addTo(g);
        count++;
      }

      // Auto-reload when map moves (debounced)
      if (!_lmap._osmplacesHook) {
        _lmap._osmplacesHook = true;
        _lmap.on('moveend', () => {
          if (_layerActive['osmplaces']) reloadLayer('osmplaces');
        });
      }

      _layerMeta[key] = { count, ts: Date.now() };
      _katmanYukleniyor(key, false);
      showToast(_mtc('harita.yerler-yuklendi', count, { sayi: count }));
      renderLayerList();

    } else if (key === 'poi') {
      const r = await authFetch(BASE_URL + '/api/map/pois');
      const d = await r.json();
      const pois = d.pois || [];
      for (const p of pois) {
        const color = p.color || '#64ffda';
        const emoji = p.icon  || '📍';
        const icon = L.divIcon({
          html: `<div style="font-size:18px;filter:drop-shadow(0 0 4px ${color});cursor:pointer">${emoji}</div>`,
          className: '', iconAnchor: [9, 9]
        });
        L.marker([p.lat, p.lng], { icon })
          .bindPopup(
            `<div style="font-family:monospace;font-size:11px;color:${color};">` +
            `${emoji} <b>${_escHtml(p.name)}</b><br>` +
            `<span style="color:#aaa;font-size:10px;">${_escHtml(p.category || _mt('harita.poi-ozel'))}</span>` +
            `${p.description ? `<br><span style="color:#ccc;font-size:10px;">${p.description}</span>` : ''}` +
            `<br><span style="color:#555;font-size:9px;">${p.lat.toFixed(5)}, ${p.lng.toFixed(5)}</span></div>`,
            { maxWidth: 240 }
          )
          .addTo(g);
      }
      _layerMeta[key] = { count: pois.length, ts: Date.now() };
      _katmanYukleniyor(key, false);
      showToast(_mtc('harita.poi-yuklendi', pois.length, { sayi: pois.length }));
      renderLayerList();
      renderPoiList();

    } else if (key === 'kpindex') {
      const r = await authFetch(BASE_URL + '/api/map/kpindex');
      const d = await r.json();
      if (d.error) throw new Error(d.error);
      const kpColors = { extreme:'#ff1744', severe:'#ff6d00', strong:'#ffab00', moderate:'#f9a825', minor:'#ffd740', calm:'#00e676', unknown:'#607d8b' };
      const kp = d.kp || 0;
      const level = d.level || 'calm';
      const color = kpColors[level];
      // Show a ring around Earth's poles to symbolize geomagnetic disturbance
      const rings = [
        [90, 0], [70, 30], [70, -30], [70, 90], [70, -90], [70, 150], [70, -150],
        [-90, 0], [-70, 30], [-70, -30], [-70, 90], [-70, -90], [-70, 150], [-70, -150],
      ];
      for (const [lat, lon] of rings) {
        L.circleMarker([lat, lon], {
          radius: Math.max(5, kp * 2.5), color, fillColor: color,
          fillOpacity: 0.2, weight: 1.5, dashArray: '3,3'
        }).bindPopup(
          `<div style="font-family:monospace;font-size:11px;color:${color};">` +
          `🌐 <b>${_escHtml(_mt('harita.kp-indeksi', { deger: kp.toFixed(1) }))}</b><br>` +
          `<span style="color:${color};font-size:10px;text-transform:uppercase;">${_escHtml(_kpSeviye(level))}</span><br>` +
          `<span style="color:#aaa;font-size:10px;">${_escHtml(_mt('harita.olcum', { deger: d.time || '—' }))}</span></div>`,
          { maxWidth: 220 }
        ).addTo(g);
      }
      _layerMeta[key] = { count: rings.length, ts: Date.now() };
      _katmanYukleniyor(key, false);
      showToast(`Kp: ${kp.toFixed(1)} — ${_kpSeviye(level)}`);
      renderLayerList();
      refreshKpGauge();
    }
  } catch (e) {
    console.warn('[MAP LAYER] ' + key + ' yüklenemedi:', e);
    _katmanYukleniyor(key, false);
    showToast(_mt('harita.katman-yuklenemedi', { katman: _katmanAdi(key), hata: e.message }), 'error');
    _layerActive[key] = false;
    _katmanUiSenk(key);
  } finally {
    clearTimeout(_safetyTimer);
    _katmanYukleniyor(key, false);   // hiçbir dal "yükleniyor"da takılı kalmasın
  }
  _layerGroups[key] = g;
  if (_layerActive[key]) g.addTo(_lmap);
}

// ── MAP HUD ENHANCEMENTS ─────────────────────────────────────

// Katmanın haritaya koyduğu nesne sayısı → çekmece satırındaki `.mk-sayi` (canlı değer).
// (Eski mod çubuğunun `.mmb-badge` rozeti çubukla birlikte kalktı, 10-04.)
function updateMmbBadge(key, count) {
  const btn = document.getElementById('map-layer-' + key);
  const n = btn && btn.querySelector('.mk-sayi');
  if (!n) return;
  n.textContent = (count > 0 && _layerActive[key]) ? (count > 999 ? '999+' : String(count)) : '';
}

function _syncBadgesFromMeta() {
  for (const [k, meta] of Object.entries(_layerMeta)) {
    if (meta && meta.count != null) updateMmbBadge(k, meta.count);
  }
  for (const [k, active] of Object.entries(_layerActive)) {
    if (!active) updateMmbBadge(k, 0);
  }
}

// 2026-10-04 (HARİTA ÖNCE): akan olay şeridi (`_tickerItems` · tickerPush ·
// _renderTicker · _initTicker) ve radar süsü (_initRadar) silindi — ikisi de
// kalkan markup'a (#map-event-ticker, #map-radar-hud) çiziyordu; tickerPush'u
// çağıran kimse yoktu.

// ══════════════════════════════════════════════════════
//  3D HOLOGRAPHIC MAP MODULE — MapLibre GL JS v4
// ══════════════════════════════════════════════════════

let _3dMap     = null;   // MapLibre instance
let _3dActive  = false;  // toggle state
let _3dReady   = false;  // map loaded flag
let _3dCache   = {};     // layer data cache {eq, fire, plane, iss, volcano, ship, adsb, eonet, sat}
let _3dRotId   = null;   // auto-rotation RAF
let _3dIdleTimer = null; // idle detection timer
// (_3D_TILE kaldırıldı 2026-08-28 — CARTO'ya işaret eden ÖLÜ sabitti; 3D harita
//  zemini OpenFreeMap vektör stilinden geliyor, initMap3D'ye bak.)

// ── Geometry helpers ───────────────────────────────────
function _geo_circle(lon, lat, r, steps) {
  steps = steps || 8;
  const coords = [];
  for (let i = 0; i <= steps; i++) {
    const a = (i / steps) * Math.PI * 2;
    coords.push([lon + Math.cos(a) * r, lat + Math.sin(a) * r]);
  }
  return { type: 'Feature', geometry: { type: 'Polygon', coordinates: [coords] }, properties: {} };
}

function _emptyFC() { return { type: 'FeatureCollection', features: [] }; }

// ── Init ───────────────────────────────────────────────
function initMap3D() {
  if (_3dMap) return;
  if (typeof maplibregl === 'undefined') { console.warn('[3D] maplibregl not loaded'); return; }

  // OpenFreeMap "dark" vector style — OSM tabanlı, ücretsiz, API key gerektirmez
  // Gerçek bina yükseklik verisi (render_height), yollar, etiketler dahil
  _3dMap = new maplibregl.Map({
    container: 'maplibre-map',
    style: 'https://tiles.openfreemap.org/styles/dark',
    center: [28.979, 41.015],
    pitch: 62,
    bearing: -25,
    zoom: 15,
    antialias: false,
    fadeDuration: 0,
    maxTileCacheSize: 20,
    attributionControl: false,
  });

  _3dMap.on('load', () => {
    _3dReady = true;
    _3d_applyHoloTheme();
    _3d_addDataSources();
    _3dBridgeAll();
    _start3DRotate();
  });

  _3dMap.on('mousedown', _stop3DRotate);
  _3dMap.on('touchstart', _stop3DRotate);
}

// ── Dark city theme — Apple Maps / Image#6 tarzı gri binalar, siyah zemin ──
function _3d_applyHoloTheme() {
  // Yönlü ışık: binalar üstten aydınlatılır → doğal gölge + kenar kontrası
  try {
    _3dMap.setLight({
      anchor: 'viewport',
      color: '#ffffff',
      intensity: 0.35,
      position: [1.5, 210, 30]
    });
  } catch(_) {}

  const style = _3dMap.getStyle();
  if (!style?.layers) return;
  for (const layer of style.layers) {
    try {
      // Binalar: zemine göre yeterince açık → 3D kenar efekti ortaya çıkar
      if (layer.type === 'fill-extrusion') {
        _3dMap.setPaintProperty(layer.id, 'fill-extrusion-color', [
          'interpolate', ['linear'], ['zoom'],
          12, '#22242c',
          14, '#2c2f3a',
          16, '#343740',
          18, '#3c4050'
        ]);
        _3dMap.setPaintProperty(layer.id, 'fill-extrusion-opacity', 0.97);
        // AO: bina diplerinde gölge → derinlik hissi
        try {
          _3dMap.setPaintProperty(layer.id, 'fill-extrusion-ambient-occlusion-intensity', 0.5);
          _3dMap.setPaintProperty(layer.id, 'fill-extrusion-ambient-occlusion-radius', 3);
        } catch(_) {}
      }
      // Arkaplan/zemin: tam siyah
      if (layer.type === 'background') {
        _3dMap.setPaintProperty(layer.id, 'background-color', '#07080d');
      }
      // Arazi (land, earth): çok koyu
      if (layer.type === 'fill' && /land|earth|ground|park|grass|pitch|garden/.test(layer.id)) {
        _3dMap.setPaintProperty(layer.id, 'fill-color', '#0a0c12');
      }
      // Su: koyu
      if (layer.type === 'fill' && /water|ocean|sea|lake|river/.test(layer.id)) {
        _3dMap.setPaintProperty(layer.id, 'fill-color', '#050912');
      }
      // Yollar: koyu gri, binalar arası boşluk görünsün
      if (layer.type === 'line' && /road|street|highway|path|motorway|trunk|primary|secondary|tertiary/.test(layer.id)) {
        _3dMap.setPaintProperty(layer.id, 'line-color', '#111318');
      }
    } catch(_) {}
  }
}

// ── Data spike sources & layers (on top of OSM buildings) ──
function _3d_addDataSources() {
  const emptyFC = _emptyFC();
  const keys = ['eq','fire','plane','volcano','ship','adsb','sat','eonet'];
  for (const k of keys) {
    _3dMap.addSource('src-' + k, { type: 'geojson', data: emptyFC });
  }

  // Earthquake spikes — red/orange, height by magnitude
  _3dMap.addLayer({
    id: 'lyr-eq', type: 'fill-extrusion', source: 'src-eq',
    paint: {
      'fill-extrusion-color': ['interpolate', ['linear'], ['get', 'mag'],
        2.5, '#ff6b35', 5, '#ff9100', 7, '#ff1744'],
      'fill-extrusion-height': ['*', ['get', 'mag'], 40000],
      'fill-extrusion-base': 0,
      'fill-extrusion-opacity': 0.88
    }
  });

  // Fire spikes — flame red
  _3dMap.addLayer({
    id: 'lyr-fire', type: 'fill-extrusion', source: 'src-fire',
    paint: {
      'fill-extrusion-color': '#ff3d00',
      'fill-extrusion-height': 35000,
      'fill-extrusion-base': 0,
      'fill-extrusion-opacity': 0.8
    }
  });

  // Volcano spikes — alert-colored
  _3dMap.addLayer({
    id: 'lyr-volcano', type: 'fill-extrusion', source: 'src-volcano',
    paint: {
      'fill-extrusion-color': ['case',
        ['==', ['get', 'alert'], 'Warning'], '#ff1744',
        ['==', ['get', 'alert'], 'Watch'],   '#ff9100',
        ['==', ['get', 'alert'], 'Advisory'],'#ffd740',
        '#69f0ae'],
      'fill-extrusion-height': 70000,
      'fill-extrusion-base': 0,
      'fill-extrusion-opacity': 0.9
    }
  });

  // Plane dots — circle (GPU-native, polygon yerine çok daha hızlı)
  _3dMap.addLayer({
    id: 'lyr-plane', type: 'circle', source: 'src-plane',
    paint: {
      'circle-color': '#00e676',
      'circle-radius': 4,
      'circle-opacity': 0.85,
      'circle-stroke-width': 1,
      'circle-stroke-color': '#00ff8880'
    }
  });

  // Ship dots — circle, ocean blue
  _3dMap.addLayer({
    id: 'lyr-ship', type: 'circle', source: 'src-ship',
    paint: {
      'circle-color': '#40c4ff',
      'circle-radius': 4,
      'circle-opacity': 0.85,
      'circle-stroke-width': 1,
      'circle-stroke-color': '#40c4ff80'
    }
  });

  // ADSB — circle, lime
  _3dMap.addLayer({
    id: 'lyr-adsb', type: 'circle', source: 'src-adsb',
    paint: {
      'circle-color': '#76ff03',
      'circle-radius': 3,
      'circle-opacity': 0.8,
      'circle-stroke-width': 0
    }
  });

  // Satellite dots — circle, holographic cyan
  _3dMap.addLayer({
    id: 'lyr-sat', type: 'circle', source: 'src-sat',
    paint: {
      'circle-color': '#00d4ff',
      'circle-radius': 4,
      'circle-opacity': 0.75,
      'circle-stroke-width': 1,
      'circle-stroke-color': '#00d4ff60'
    }
  });

  // EONET — circle, orange
  _3dMap.addLayer({
    id: 'lyr-eonet', type: 'circle', source: 'src-eonet',
    paint: {
      'circle-color': '#ff9100',
      'circle-radius': 5,
      'circle-opacity': 0.85,
      'circle-stroke-width': 1,
      'circle-stroke-color': '#ff910060'
    }
  });
}

// ── Bridge: push cached data to 3D layers ─────────────
function _3dBridgeAll() {
  _3dUpdateEq();
  _3dUpdateFire();
  _3dUpdateVolcano();
  _3dUpdatePlane();
  _3dUpdateShip();
  _3dUpdateAdsb();
  _3dUpdateSat();
  _3dUpdateEonet();
  _update3DHUD();
}

function _3dSetSource(id, fc) {
  if (!_3dReady || !_3dMap) return;
  const src = _3dMap.getSource('src-' + id);
  if (src) src.setData(fc);
}

function _3dUpdateEq() {
  const data = _3dCache['eq'];
  if (!data || !data.length) return _3dSetSource('eq', _emptyFC());
  const fc = {
    type: 'FeatureCollection',
    features: data.map(f => {
      const [lon, lat] = f.geometry.coordinates;
      const c = _geo_circle(lon, lat, 0.08);
      c.properties = { mag: f.properties.mag || 3, place: f.properties.place || '' };
      return c;
    })
  };
  _3dSetSource('eq', fc);
  const el = document.getElementById('h3d-eq');
  if (el) el.textContent = _mt('harita.h3d.eq', { n: data.length });
}

function _3dUpdateFire() {
  const data = _3dCache['fire'];
  if (!data || !data.length) return _3dSetSource('fire', _emptyFC());
  const fc = {
    type: 'FeatureCollection',
    features: data.map(f => {
      const c = _geo_circle(f.lon, f.lat, 0.06);
      c.properties = { conf: f.conf };
      return c;
    })
  };
  _3dSetSource('fire', fc);
  const el = document.getElementById('h3d-fire');
  if (el) el.textContent = `FIRE: ${data.length}`;
}

function _3dUpdateVolcano() {
  const data = _3dCache['volcano'];
  if (!data || !data.length) return _3dSetSource('volcano', _emptyFC());
  const fc = {
    type: 'FeatureCollection',
    features: data.map(v => {
      const c = _geo_circle(v.lon, v.lat, 0.12);
      c.properties = { alert: v.alert || 'Normal', name: v.name };
      return c;
    })
  };
  _3dSetSource('volcano', fc);
  const el = document.getElementById('h3d-vol');
  if (el) el.textContent = `VOLCANO: ${data.length}`;
}

function _3dUpdatePlane() {
  const data = _3dCache['plane'];
  if (!data || !data.length) return _3dSetSource('plane', _emptyFC());
  const features = data.filter(s => s[5] && s[6]).map(s => ({
    type: 'Feature',
    geometry: { type: 'Point', coordinates: [s[5], s[6]] },
    properties: { call: (s[1] || '').trim() }
  }));
  _3dSetSource('plane', { type: 'FeatureCollection', features });
  const el = document.getElementById('h3d-plane');
  if (el) el.textContent = `PLANE: ${features.length}`;
}

function _3dUpdateShip() {
  const data = _3dCache['ship'];
  if (!data || !data.length) return _3dSetSource('ship', _emptyFC());
  const features = data.map(s => ({
    type: 'Feature',
    geometry: { type: 'Point', coordinates: [s.lon, s.lat] },
    properties: { name: s.name || s.mmsi }
  }));
  _3dSetSource('ship', { type: 'FeatureCollection', features });
  const el = document.getElementById('h3d-ship');
  if (el) el.textContent = `SHIP: ${features.length}`;
}

function _3dUpdateAdsb() {
  const data = _3dCache['adsb'];
  if (!data || !data.length) return _3dSetSource('adsb', _emptyFC());
  const features = data.filter(a => a.lat && a.lon).map(a => ({
    type: 'Feature',
    geometry: { type: 'Point', coordinates: [a.lon, a.lat] },
    properties: { alt: a.alt_baro || 0 }
  }));
  _3dSetSource('adsb', { type: 'FeatureCollection', features });
}

function _3dUpdateSat() {
  const data = _3dCache['sat'];
  if (!data || !data.length) return _3dSetSource('sat', _emptyFC());
  const features = data.map(s => ({
    type: 'Feature',
    geometry: { type: 'Point', coordinates: [s.lon, s.lat] },
    properties: { name: s.name }
  }));
  _3dSetSource('sat', { type: 'FeatureCollection', features });
  const el = document.getElementById('h3d-sat');
  if (el) el.textContent = `SAT: ${features.length}`;
}

function _3dUpdateEonet() {
  const data = _3dCache['eonet'];
  if (!data || !data.length) return _3dSetSource('eonet', _emptyFC());
  const features = data.map(ev => ({
    type: 'Feature',
    geometry: { type: 'Point', coordinates: [ev.lon, ev.lat] },
    properties: { title: ev.title }
  }));
  _3dSetSource('eonet', { type: 'FeatureCollection', features });
}

// ── Auto-rotation ──────────────────────────────────────
function _start3DRotate() {
  if (_3dRotId) return;
  _3dRotId = setInterval(() => {
    if (!_3dMap) return;
    _3dMap.setBearing((_3dMap.getBearing() + 0.3) % 360);
  }, 100);
}

function _stop3DRotate() {
  if (_3dRotId) { clearInterval(_3dRotId); _3dRotId = null; }
  clearTimeout(_3dIdleTimer);
  _3dIdleTimer = setTimeout(() => {
    if (_3dActive && _3dReady) _start3DRotate();
  }, 10000);
}

// ── HUD update ─────────────────────────────────────────
function _update3DHUD() {
  /* Sayaç metni sözlükten (`harita.h3d.*`) — elemanlar `data-i18n-yok`, çünkü
     `{n}` canlı sayı; dil değişince dil tazeleyicisinin ⑥ adımı yeniden yazar. */
  const fields = {
    'h3d-eq':    ['eq',      v => v.length],
    'h3d-fire':  ['fire',    v => v.length],
    'h3d-plane': ['plane',   v => v.filter(s => s[5] && s[6]).length],
    'h3d-ship':  ['ship',    v => v.length],
    'h3d-sat':   ['sat',     v => v.length],
    'h3d-vol':   ['volcano', v => v.length],
  };
  for (const [id, [key, say]] of Object.entries(fields)) {
    const el = document.getElementById(id);
    if (!el) continue;
    const d = _3dCache[key];
    el.textContent = _mt('harita.h3d.' + id.replace('h3d-', ''), { n: d && d.length ? say(d) : '—' });
  }
}

// ══════════════════════════════════════════════════════
//  PLACE DETAIL PANEL
// ══════════════════════════════════════════════════════
let _pdpCurrentPlace = null;

function showPlaceDetail(data) {
  _pdpCurrentPlace = data;
  const panel = document.getElementById('place-detail-panel');
  if (!panel) return;

  // Photo placeholder
  const ph = document.getElementById('pdp-photo-placeholder');
  const img = document.getElementById('pdp-photo');
  if (ph) ph.textContent = data.icon || '📍';
  if (img) { img.classList.remove('loaded'); img.src = ''; }

  // Name & category
  const nameEl = document.getElementById('pdp-name');
  const catEl  = document.getElementById('pdp-category');
  if (nameEl) nameEl.textContent = data.name || '—';
  if (catEl)  catEl.textContent  = data.label || '—';

  // Action buttons
  const actEl = document.getElementById('pdp-actions');
  if (actEl) {
    const mapsUrl = `https://www.google.com/maps/dir/?api=1&destination=${data.lat},${data.lon}`;
    const shareUrl = `https://www.google.com/maps/search/?api=1&query=${data.lat},${data.lon}`;
    actEl.innerHTML = `
      <a class="pdp-action-btn" href="${mapsUrl}" target="_blank">
        <span class="pdp-ab-icon">🗺️</span>${_escHtml(_mt('harita.yol-tarifi'))}
      </a>
      <button class="pdp-action-btn" onclick="_pdpAskYuki()">
        <span class="pdp-ab-icon">◈</span>${_escHtml(_mt('harita.yukiye-sor'))}
      </button>
      <a class="pdp-action-btn" href="${shareUrl}" target="_blank">
        <span class="pdp-ab-icon">📤</span>${_escHtml(_mt('harita.paylas'))}
      </a>
      <button class="pdp-action-btn" onclick="_pdpCopyCoords()">
        <span class="pdp-ab-icon">📋</span>${_escHtml(_mt('harita.konum-kopyala'))}
      </button>
    `;
  }

  // Detail rows
  const detEl = document.getElementById('pdp-details');
  if (detEl) {
    const rows = [];
    // 🔴 GÜVENLİK: bu alanların TAMAMI OpenStreetMap'ten gelir — herkesin
    // düzenleyebildiği açık bir veritabanı. `innerHTML`'e ham basılıyorlardı
    // (`planner.html` turundaki openfoodfacts vakasının birebir aynısı) ve
    // `href` de hamdı, yani `javascript:` şeması da geçiyordu.
    if (data.address)  rows.push(['📍', _escHtml(data.address)]);
    if (data.phone)    rows.push(['📞', `<a href="tel:${encodeURIComponent(data.phone)}">${_escHtml(data.phone)}</a>`]);
    if (data.website)  rows.push(['🌐', _guvenliBag(data.website, data.website.replace(/^https?:\/\//,'').slice(0,40))]);
    if (data.hours)    rows.push(['🕐', _escHtml(data.hours)]);
    if (data.email)    rows.push(['✉️', `<a href="mailto:${encodeURIComponent(data.email)}">${_escHtml(data.email)}</a>`]);
    if (data.wikipedia)rows.push(['📖', `<a href="https://wikipedia.org/wiki/${encodeURIComponent(data.wikipedia)}" target="_blank">Wikipedia</a>`]);
    rows.push(['📌', `${data.lat.toFixed(5)}, ${data.lon.toFixed(5)}`]);
    detEl.innerHTML = rows.map(([icon, text]) =>
      `<div class="pdp-detail-row"><span class="pdp-detail-icon">${icon}</span><span class="pdp-detail-text">${text}</span></div>`
    ).join('');
  }

  // Open panel
  panel.classList.add('open');

  // Fetch Wikipedia photo async
  _pdpFetchPhoto(data.name, data.lat, data.lon);
}

function closePlaceDetail() {
  const panel = document.getElementById('place-detail-panel');
  if (panel) panel.classList.remove('open');
  _pdpCurrentPlace = null;
}

async function _pdpFetchPhoto(name, lat, lon) {
  const img = document.getElementById('pdp-photo');
  const ph  = document.getElementById('pdp-photo-placeholder');
  if (!img || !name) return;
  try {
    // Wikipedia pageimages API
    const url = `https://en.wikipedia.org/w/api.php?action=query&titles=${encodeURIComponent(name)}&prop=pageimages&format=json&pithumbsize=480&origin=*`;
    const r = await fetch(url);
    const d = await r.json();
    const pages = d?.query?.pages || {};
    const page = Object.values(pages)[0];
    const src = page?.thumbnail?.source;
    if (src) {
      img.onload = () => { img.classList.add('loaded'); if (ph) ph.style.display = 'none'; };
      img.onerror = () => {};
      img.src = src;
      return;
    }
    // Fallback: Wikimedia Commons search
    const commUrl = `https://commons.wikimedia.org/w/api.php?action=query&list=search&srsearch=${encodeURIComponent(name)}&srnamespace=6&srlimit=1&format=json&origin=*`;
    const cr = await fetch(commUrl);
    const cd = await cr.json();
    const title = cd?.query?.search?.[0]?.title;
    if (title) {
      const fileUrl = `https://commons.wikimedia.org/wiki/Special:FilePath/${encodeURIComponent(title.replace('File:',''))}?width=480`;
      img.onload = () => { img.classList.add('loaded'); if (ph) ph.style.display = 'none'; };
      img.src = fileUrl;
    }
  } catch(_) {}
}

function _pdpAskYuki() {
  if (!_pdpCurrentPlace) return;
  const p = _pdpCurrentPlace;
  const q = _mt('harita.sor.yer', {
    ad: p.name,
    kategori: p.label ? _mt('harita.sor.kategori-eki', { ad: p.label }) : '',
    adres: p.address ? _mt('harita.sor.adres-eki', { adres: p.address }) : '',
  });
  closePlaceDetail();
  if (typeof sendMessage === 'function') sendMessage(q);
}

function _pdpCopyCoords() {
  if (!_pdpCurrentPlace) return;
  const text = `${_pdpCurrentPlace.lat.toFixed(6)}, ${_pdpCurrentPlace.lon.toFixed(6)}`;
  navigator.clipboard?.writeText(text).then(() => showToast(_mt('harita.konum-kopyalandi', { konum: text })));
}

// ── Toggle ─────────────────────────────────────────────
function toggle3DMode() {
  _3dActive = !_3dActive;
  const btn     = document.getElementById('map-btn-3d');
  const con3d   = document.getElementById('map-3d-container');
  const lmap    = document.getElementById('leaflet-map');
  const scanOvr = document.getElementById('map-scan-overlay');

  if (_3dActive) {
    if (btn) btn.classList.add('active');
    if (con3d) con3d.classList.add('active');
    if (lmap) lmap.classList.add('hidden-3d');
    if (scanOvr) scanOvr.style.display = 'none';
    // clear 2D mode buttons
    document.getElementById('map-btn-world')?.classList.remove('active');
    document.getElementById('map-btn-turkey')?.classList.remove('active');
    initMap3D();
    if (_3dReady) { _3dBridgeAll(); _start3DRotate(); }
  } else {
    if (btn) btn.classList.remove('active');
    if (con3d) con3d.classList.remove('active');
    if (lmap) lmap.classList.remove('hidden-3d');
    if (scanOvr) scanOvr.style.display = '';
    _stop3DRotate();
    // restore 2D world view active button
    document.getElementById('map-btn-world')?.classList.add('active');
  }
}

// ══════════════════════════════════════════════════════
//  MAP INFRASTRUCTURE v2 — Layer Manager & Helpers
// ══════════════════════════════════════════════════════

function saveLayerState() {
  try { localStorage.setItem('yuki_layer_state', JSON.stringify(_layerActive)); } catch(_) {}
}

function loadLayerState() {
  try {
    const s = JSON.parse(localStorage.getItem('yuki_layer_state') || '{}');
    for (const [k, v] of Object.entries(s)) {
      if (k in _layerActive && v) toggleLayer(k);
    }
  } catch(_) {}
}

// ── Kaynak sağlık göstergesi (FAZ 2) — /api/map/health → katman satırı noktası ──
let _mapHealth = {};
let _mapHealthTimer = null;

async function refreshMapHealth() {
  try {
    const r = await authFetch(BASE_URL + '/api/map/health');
    const d = await r.json();
    _mapHealth = d.sources || {};
    renderLayerList();
  } catch (_) {}
}

function _healthInfo(k) {
  // katman anahtarı → backend dayanıklılık katmanı kaynak anahtarı
  const map = { eq: 'earthquakes:', fire: 'fires', plane: 'flights', volcano: 'volcanoes',
                weather: 'weather', air: 'airquality', military: 'military',
                kpindex: 'kpindex', cctv: 'cctv' };
  const hk = map[k];
  if (!hk) return null;
  if (hk.endsWith(':')) { // earthquakes:day gibi parametreli anahtarlar
    const found = Object.keys(_mapHealth).find(s => s.startsWith(hk));
    return found ? _mapHealth[found] : null;
  }
  return _mapHealth[hk] || null;
}

function _healthDot(k) {
  const h = _healthInfo(k);
  if (!h) return `<span title="${_escHtml(_mt('harita.saglik.izlenmiyor'))}" style="display:inline-block;width:7px;height:7px;border-radius:50%;background:var(--ink-3);flex:none"></span>`;
  // DOM'a yazılıyor → var() çözülür, tema izlenir (Leaflet/canvas renkleri ayrı: var() okuyamaz)
  // bayat veri = nötr (altın değil — göz tur 2); ölü = kırmızı, sağlıklı = yeşil
  const col = h.ok ? 'var(--yesil-ink)' : (h.has_data ? 'var(--ink-2)' : 'var(--kirmizi-ink)');
  const err = String(h.error || '').replace(/"/g, '&quot;').slice(0, 90);
  const tip = h.ok
    ? _mt('harita.saglik.iyi', { ms: h.latency_ms, dk: Math.round((h.data_age_s || 0) / 60) })
    : (h.has_data
        ? _mt('harita.saglik.bayat', { dk: Math.round((h.data_age_s || 0) / 60), hata: err })
        : _mt('harita.saglik.olu', { hata: err }));
  return `<span title="${_escHtml(tip)}" style="display:inline-block;width:7px;height:7px;border-radius:50%;background:${col};flex:none"></span>`;
}

function toggleLayerMgr() {
  const panel = document.getElementById('map-layer-mgr');
  if (!panel) return;
  panel.classList.toggle('open');
  const mgrBtn = document.getElementById('map-btn-layer-mgr');
  if (mgrBtn) mgrBtn.setAttribute('aria-expanded', panel.classList.contains('open') ? 'true' : 'false');
  if (panel.classList.contains('open')) {
    renderLayerList();
    renderPoiList();
    refreshKpGauge();
    refreshMapHealth();
    if (!_mapHealthTimer) _mapHealthTimer = setInterval(refreshMapHealth, 60000);
  } else if (_mapHealthTimer) {
    clearInterval(_mapHealthTimer); _mapHealthTimer = null;
  }
}

function renderLayerList() {
  const el = document.getElementById('mlm-layer-list');
  if (!el) return;
  const active = Object.entries(_layerActive).filter(([,v]) => v).map(([k]) => k);
  if (!active.length) { el.innerHTML = `<div class="mlm-bos">${_escHtml(_mt('harita.aktif-katman-yok'))}</div>`; return; }
  el.innerHTML = active.map(k => {
    const meta  = _layerMeta[k];
    const count = meta ? meta.count : '—';
    const age   = meta ? Math.round((Date.now() - meta.ts) / 1000) + 's' : '—';
    return `<div class="mlm-layer-row">
      ${_healthDot(k)}
      <span class="mlm-layer-name">${_escHtml(_katmanAdi(k))}</span>
      <span class="mlm-layer-count">${count}</span>
      <span class="mlm-layer-yas">${age}</span>
      <button class="mlm-refresh-btn" onclick="reloadLayer('${k}')">⟳</button>
    </div>`;
  }).join('');
  _syncBadgesFromMeta();
}

function reloadLayer(key) {
  if (!_layerActive[key]) return;
  if (_layerGroups[key]) { _lmap.removeLayer(_layerGroups[key]); _layerGroups[key] = null; }
  _fetchLayer(key);
}

function updateLayerFilter(key, param, val) {
  if (!_layerFilters[key]) _layerFilters[key] = {};
  _layerFilters[key][param] = param === 'min_mag' ? parseFloat(val) : val;
  if (_layerActive[key]) reloadLayer(key);
}

async function searchMapLocation() {
  const input = document.getElementById('map-search-input');
  if (!input) return;
  const q = input.value.trim();
  if (!q) return;
  input.disabled = true;
  try {
    const url = `https://nominatim.openstreetmap.org/search?q=${encodeURIComponent(q)}&format=json&limit=1`;
    const r = await fetch(url, { headers: { 'Accept-Language': 'tr,en' } });
    const d = await r.json();
    if (!d.length) { showToast(_mt('harita.konum-bulunamadi', { arama: q }), 'error'); return; }
    const { lat, lon, display_name } = d[0];
    _lmap.setView([parseFloat(lat), parseFloat(lon)], 12, { animate: true });
    L.popup({ maxWidth: 260 })
      .setLatLng([parseFloat(lat), parseFloat(lon)])
      .setContent(`<div style="font-family:monospace;font-size:10px;color:#00d4ff;">◈ ${_escHtml(display_name)}</div>`)
      .openOn(_lmap);
  } catch(e) {
    showToast(_mt('harita.arama-hatasi', { hata: e.message }), 'error');
  } finally {
    input.disabled = false;
  }
}

// ── Custom POI ────────────────────────────────────────
let _poiPendingLatLng = null;
let _poiAddMode = false;

function startPoiAdd() {
  _poiAddMode = true;
  _poiPendingLatLng = null;
  const form = document.getElementById('mlm-poi-form');
  if (form) form.classList.add('visible');
  showToast(_mt('harita.poi-konum-sec'));
  // Listen for next map click to capture lat/lng
  _lmap.once('click', (e) => {
    if (!_poiAddMode) return;
    _poiPendingLatLng = e.latlng;
    showToast(_mt('harita.poi-secildi', { lat: e.latlng.lat.toFixed(5), lon: e.latlng.lng.toFixed(5) }));
  });
}

function cancelPoiAdd() {
  _poiAddMode = false;
  _poiPendingLatLng = null;
  const form = document.getElementById('mlm-poi-form');
  if (form) form.classList.remove('visible');
  ['mlm-poi-name','mlm-poi-icon','mlm-poi-desc','mlm-poi-color'].forEach(id => {
    const el = document.getElementById(id); if (el) el.value = '';
  });
}

async function confirmPoiAdd() {
  const name = (document.getElementById('mlm-poi-name')?.value || '').trim();
  if (!name) { showToast(_mt('harita.poi-isim-zorunlu'), 'error'); return; }
  if (!_poiPendingLatLng) { showToast(_mt('harita.poi-konum-zorunlu'), 'error'); return; }
  const payload = {
    name,
    lat: _poiPendingLatLng.lat,
    lng: _poiPendingLatLng.lng,
    icon:        (document.getElementById('mlm-poi-icon')?.value  || '📍').trim() || '📍',
    description: (document.getElementById('mlm-poi-desc')?.value  || '').trim(),
    color:       (document.getElementById('mlm-poi-color')?.value || '#64ffda').trim() || '#64ffda',
    category:    'custom',
  };
  try {
    const r = await authFetch(BASE_URL + '/api/map/pois', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(payload),
    });
    const d = await r.json();
    if (d.error) throw new Error(d.error);
    showToast(_mt('harita.poi-eklendi', { ad: name }));
    cancelPoiAdd();
    if (_layerActive['poi']) reloadLayer('poi');
    else { toggleLayer('poi'); }
    renderPoiList();
  } catch(e) {
    showToast(_mt('harita.poi-eklenemedi', { hata: e.message }), 'error');
  }
}

async function renderPoiList() {
  const el = document.getElementById('mlm-poi-list');
  if (!el) return;
  try {
    const r = await authFetch(BASE_URL + '/api/map/pois');
    const d = await r.json();
    const pois = d.pois || [];
    if (!pois.length) { el.innerHTML = `<div class="mlm-bos">${_escHtml(_mt('harita.poi-yok'))}</div>`; return; }
    el.innerHTML = pois.map(p =>
      `<div class="mlm-poi-item">
        <span class="mlm-poi-item-icon">${p.icon || '📍'}</span>
        <span class="mlm-poi-item-name" title="${_escHtml(p.description || '')}">${_escHtml(p.name)}</span>
        <button class="mlm-poi-item-del" onclick="deletePoi('${p.id}')">✕</button>
      </div>`
    ).join('');
  } catch(e) { el.innerHTML = `<div class="mlm-bos mlm-hata">⚠ ${_escHtml(e.message)}</div>`; }
}

async function deletePoi(id) {
  try {
    const r = await authFetch(BASE_URL + '/api/map/pois/' + id, { method: 'DELETE' });
    const d = await r.json();
    if (d.error) throw new Error(d.error);
    showToast(_mt('harita.poi-silindi'));
    if (_layerActive['poi']) reloadLayer('poi');
    renderPoiList();
  } catch(e) { showToast(_mt('harita.silinemedi', { hata: e.message }), 'error'); }
}

// ── Kp Index Gauge ────────────────────────────────────
async function refreshKpGauge() {
  const valEl   = document.getElementById('mlm-kp-val');
  const levelEl = document.getElementById('mlm-kp-level');
  const barEl   = document.getElementById('mlm-kp-bar');
  if (!valEl) return;
  // DOM'a yazılıyor → token çözülür (katmanın Leaflet çemberleri ayrı sözlük kullanır, var() okuyamaz)
  // 🔴 ALTIN YOK (göz tur 2): altın üründe nadir vurgu (başarı), uyarı değil.
  //    Ürünün durum sözlüğünde yalnız iki anlamlı renk var: yeşil = olumlu, kırmızı =
  //    tehlike. Sakin → yeşil · güçlü/şiddetli/aşırı fırtına → kırmızı · hafif/orta →
  //    nötr ink (bilgi, alarm değil). Çubuk aynı renkte.
  const kpColors = { extreme:'var(--kirmizi-ink)', severe:'var(--kirmizi-ink)', strong:'var(--kirmizi-ink)', moderate:'var(--ink-1)', minor:'var(--ink-1)', calm:'var(--yesil-ink)', unknown:'var(--mh-soluk)' };
  try {
    const r = await authFetch(BASE_URL + '/api/map/kpindex');
    const d = await r.json();
    const kp    = d.kp    || 0;
    const level = d.level || 'calm';
    const color = kpColors[level] || 'var(--ink-1)';
    valEl.textContent   = kp.toFixed(1);
    valEl.style.color   = color;
    levelEl.textContent = _kpSeviye(level);
    levelEl.style.color = color;
    if (barEl) { barEl.style.width = `${Math.min(100, kp / 9 * 100)}%`; barEl.style.background = color; }
  } catch(e) {
    if (levelEl) levelEl.textContent = _mt('harita.hata-kisa');
  }
}

// ── Mission Control ────────────────────────────────────
// ── Map Modes ──────────────────────────────────────────
function setMapMode(mode) {
  clearPlanetMode();
  document.getElementById('map-btn-world').classList.toggle('active', mode === 'world');
  document.getElementById('map-btn-turkey').classList.toggle('active', mode === 'turkey');

  if (!_lmap) return;
  if (mode === 'world')  _lmap.setView([20, 10], 2);
  if (mode === 'turkey') _lmap.setView([39.0, 35.0], 6);
}


// ── Planet Mode Engine ────────────────────────────────
/* 🔴 MODÜL DÜZEYİ SABİT — DOKUZUNCU vaka, ve bu dosyanın en büyüğü.
   14 gök cismi × 11 metin alanı modül yüklenirken çözülüyordu. Alanların
   çoğu "sayı + birim" (`12.742 km`, `5,97 × 10²⁴ kg`) ve **sayı biçimi de
   dile bağlıdır**: TR'de binlik ayıracı nokta, ondalık virgül; EN'de tersi.
   Metin çevirisi bunu tek başına düzeltmez — değerin kendisi ayrı yazılır.
   Teknik alanlar (`color` · `symbol` · `orbitR` · `orbitPeriod` · `bands`
   · `type`) çeviriye AÇILMADI; onlar çizimin girdisi, ekranın değil. */

/* Gök cismini EKRANA HAZIR hâlde verir: teknik alanlar prototipten gelir,
   metin alanları her çağrıda sözlükten çözülür. `_PLANETS`'a doğrudan
   bakılmaz — bakılsaydı ekrana ham anahtar (`uzay.mars.desc`) basılırdı. */
const _GOK_METIN = ['name', 'diameter', 'mass', 'gravity', 'temp', 'moons',
                    'orbit', 'day', 'atmosphere', 'distance', 'desc'];

function _gok(key) {
  const p = _PLANETS[key];
  if (!p) return null;
  const c = Object.create(p);
  for (const a of _GOK_METIN) {
    const ham = p[a];
    if (typeof ham !== 'string' || !ham.startsWith('uzay.')) { c[a] = ham; continue; }
    const cev = _mt(ham);
    c[a] = (cev === ham) ? '—' : cev;   // sözlükte yoksa anahtar DEĞİL '—' göster
  }
  return c;
}

const _PLANETS = {
  sun: {
    name: 'uzay.sun.name', symbol: '☀',
    color: '#ffd740', glow: '#ff6d00', dark: '#b34700',
    type: 'star',
    diameter: 'uzay.sun.diameter', mass: 'uzay.sun.mass',
    gravity: 'uzay.sun.gravity', temp: 'uzay.sun.temp', moons: '—',
    orbit: '—', day: 'uzay.sun.day',
    atmosphere: 'uzay.sun.atmosphere',
    distance: 'uzay.sun.distance', desc: 'uzay.sun.desc',
    orbitR: 0, orbitPeriod: 1,
    bands: [
      { pct: 0.0, color: 'rgba(255,220,60,0.9)' },
      { pct: 0.25, color: 'rgba(255,180,20,0.8)' },
      { pct: 0.5, color: 'rgba(255,140,0,0.7)' },
      { pct: 0.75, color: 'rgba(200,80,0,0.6)' },
      { pct: 1.0, color: 'rgba(180,50,0,0.5)' },
    ]
  },
  mercury: {
    name: 'uzay.mercury.name', symbol: '☿',
    color: '#b0bec5', glow: '#78909c', dark: '#37474f',
    type: 'rocky',
    diameter: 'uzay.mercury.diameter', mass: 'uzay.mercury.mass',
    gravity: 'uzay.mercury.gravity', temp: 'uzay.mercury.temp', moons: 'uzay.mercury.moons',
    orbit: 'uzay.mercury.orbit', day: 'uzay.mercury.day',
    atmosphere: 'uzay.mercury.atmosphere',
    distance: 'uzay.mercury.distance', desc: 'uzay.mercury.desc',
    orbitR: 38, orbitPeriod: 0.24
  },
  venus: {
    name: 'uzay.venus.name', symbol: '♀',
    color: '#ffcc80', glow: '#ff8f00', dark: '#e65100',
    type: 'rocky',
    diameter: 'uzay.venus.diameter', mass: 'uzay.venus.mass',
    gravity: 'uzay.venus.gravity', temp: 'uzay.venus.temp', moons: 'uzay.venus.moons',
    orbit: 'uzay.venus.orbit', day: 'uzay.venus.day',
    atmosphere: 'uzay.venus.atmosphere',
    distance: 'uzay.venus.distance', desc: 'uzay.venus.desc',
    orbitR: 52, orbitPeriod: 0.62
  },
  mars: {
    name: 'uzay.mars.name', symbol: '♂',
    color: '#ff5252', glow: '#d32f2f', dark: '#7f0000',
    type: 'rocky',
    diameter: 'uzay.mars.diameter', mass: 'uzay.mars.mass',
    gravity: 'uzay.mars.gravity', temp: 'uzay.mars.temp', moons: 'uzay.mars.moons',
    orbit: 'uzay.mars.orbit', day: 'uzay.mars.day',
    atmosphere: 'uzay.mars.atmosphere',
    distance: 'uzay.mars.distance', desc: 'uzay.mars.desc',
    orbitR: 75, orbitPeriod: 1.88
  },
  jupiter: {
    name: 'uzay.jupiter.name', symbol: '♃',
    color: '#ffab40', glow: '#e65100', dark: '#bf360c',
    type: 'gas',
    diameter: 'uzay.jupiter.diameter', mass: 'uzay.jupiter.mass',
    gravity: 'uzay.jupiter.gravity', temp: 'uzay.jupiter.temp', moons: 'uzay.jupiter.moons',
    orbit: 'uzay.jupiter.orbit', day: 'uzay.jupiter.day',
    atmosphere: 'uzay.jupiter.atmosphere',
    distance: 'uzay.jupiter.distance', desc: 'uzay.jupiter.desc',
    orbitR: 101, orbitPeriod: 11.86,
    bands: [
      { pct: 0.05, color: 'rgba(200,120,60,0.5)' },
      { pct: 0.18, color: 'rgba(160,80,30,0.6)' },
      { pct: 0.32, color: 'rgba(220,150,80,0.4)' },
      { pct: 0.48, color: 'rgba(140,70,20,0.55)' },
      { pct: 0.62, color: 'rgba(200,120,60,0.45)' },
      { pct: 0.78, color: 'rgba(160,80,30,0.5)' },
      { pct: 0.92, color: 'rgba(220,150,80,0.35)' },
    ]
  },
  saturn: {
    name: 'uzay.saturn.name', symbol: '♄',
    color: '#ffe082', glow: '#f9a825', dark: '#e65100',
    type: 'gas', rings: true,
    diameter: 'uzay.saturn.diameter', mass: 'uzay.saturn.mass',
    gravity: 'uzay.saturn.gravity', temp: 'uzay.saturn.temp', moons: 'uzay.saturn.moons',
    orbit: 'uzay.saturn.orbit', day: 'uzay.saturn.day',
    atmosphere: 'uzay.saturn.atmosphere',
    distance: 'uzay.saturn.distance', desc: 'uzay.saturn.desc',
    orbitR: 125, orbitPeriod: 29.46
  },
  uranus: {
    name: 'uzay.uranus.name', symbol: '⛢',
    color: '#80deea', glow: '#0097a7', dark: '#006064',
    type: 'ice', rings: true, thinRings: true,
    diameter: 'uzay.uranus.diameter', mass: 'uzay.uranus.mass',
    gravity: 'uzay.uranus.gravity', temp: 'uzay.uranus.temp', moons: 'uzay.uranus.moons',
    orbit: 'uzay.uranus.orbit', day: 'uzay.uranus.day',
    atmosphere: 'uzay.uranus.atmosphere',
    distance: 'uzay.uranus.distance', desc: 'uzay.uranus.desc',
    orbitR: 148, orbitPeriod: 84
  },
  neptune: {
    name: 'uzay.neptune.name', symbol: '♆',
    color: '#7986cb', glow: '#1a237e', dark: '#0d47a1',
    type: 'ice',
    diameter: 'uzay.neptune.diameter', mass: 'uzay.neptune.mass',
    gravity: 'uzay.neptune.gravity', temp: 'uzay.neptune.temp', moons: 'uzay.neptune.moons',
    orbit: 'uzay.neptune.orbit', day: 'uzay.neptune.day',
    atmosphere: 'uzay.neptune.atmosphere',
    distance: 'uzay.neptune.distance', desc: 'uzay.neptune.desc',
    orbitR: 168, orbitPeriod: 165
  },
  earth: {
    name: 'uzay.earth.name', symbol: '♁',
    color: '#4fc3f7', glow: '#0288d1', dark: '#01579b',
    type: 'rocky',
    diameter: 'uzay.earth.diameter', mass: 'uzay.earth.mass',
    gravity: 'uzay.earth.gravity', temp: 'uzay.earth.temp', moons: 'uzay.earth.moons',
    orbit: 'uzay.earth.orbit', day: 'uzay.earth.day',
    atmosphere: 'uzay.earth.atmosphere',
    distance: 'uzay.earth.distance', desc: 'uzay.earth.desc',
    orbitR: 100, orbitPeriod: 1
  },
  ceres: {
    name: 'uzay.ceres.name', symbol: '⚳',
    color: '#9e9e9e', glow: '#757575', dark: '#424242',
    type: 'dwarf',
    diameter: 'uzay.ceres.diameter', mass: 'uzay.ceres.mass',
    gravity: 'uzay.ceres.gravity', temp: 'uzay.ceres.temp', moons: 'uzay.ceres.moons',
    orbit: 'uzay.ceres.orbit', day: 'uzay.ceres.day',
    atmosphere: 'uzay.ceres.atmosphere',
    distance: 'uzay.ceres.distance', desc: 'uzay.ceres.desc',
    orbitR: 143, orbitPeriod: 4.6
  },
  pluto: {
    name: 'uzay.pluto.name', symbol: '♇',
    color: '#bcaaa4', glow: '#8d6e63', dark: '#4e342e',
    type: 'dwarf',
    diameter: 'uzay.pluto.diameter', mass: 'uzay.pluto.mass',
    gravity: 'uzay.pluto.gravity', temp: 'uzay.pluto.temp', moons: 'uzay.pluto.moons',
    orbit: 'uzay.pluto.orbit', day: 'uzay.pluto.day',
    atmosphere: 'uzay.pluto.atmosphere',
    distance: 'uzay.pluto.distance', desc: 'uzay.pluto.desc',
    orbitR: 185, orbitPeriod: 248
  },
  eris: {
    name: 'uzay.eris.name', symbol: '⯰',
    color: '#e0e0e0', glow: '#bdbdbd', dark: '#757575',
    type: 'dwarf',
    diameter: 'uzay.eris.diameter', mass: 'uzay.eris.mass',
    gravity: 'uzay.eris.gravity', temp: 'uzay.eris.temp', moons: 'uzay.eris.moons',
    orbit: 'uzay.eris.orbit', day: 'uzay.eris.day',
    atmosphere: 'uzay.eris.atmosphere',
    distance: 'uzay.eris.distance', desc: 'uzay.eris.desc',
    orbitR: 205, orbitPeriod: 559
  },
  makemake: {
    name: 'uzay.makemake.name', symbol: '🝼',
    color: '#ff8a65', glow: '#e64a19', dark: '#bf360c',
    type: 'dwarf',
    diameter: 'uzay.makemake.diameter', mass: 'uzay.makemake.mass',
    gravity: 'uzay.makemake.gravity', temp: 'uzay.makemake.temp', moons: 'uzay.makemake.moons',
    orbit: 'uzay.makemake.orbit', day: 'uzay.makemake.day',
    atmosphere: 'uzay.makemake.atmosphere',
    distance: 'uzay.makemake.distance', desc: 'uzay.makemake.desc',
    orbitR: 220, orbitPeriod: 305
  },
  haumea: {
    name: 'uzay.haumea.name', symbol: '🝿',
    color: '#e8f5e9', glow: '#a5d6a7', dark: '#388e3c',
    type: 'dwarf',
    diameter: 'uzay.haumea.diameter', mass: 'uzay.haumea.mass',
    gravity: 'uzay.haumea.gravity', temp: 'uzay.haumea.temp', moons: 'uzay.haumea.moons',
    orbit: 'uzay.haumea.orbit', day: 'uzay.haumea.day',
    atmosphere: 'uzay.haumea.atmosphere',
    distance: 'uzay.haumea.distance', desc: 'uzay.haumea.desc',
    orbitR: 235, orbitPeriod: 285, rings: true, thinRings: true
  }
};

let _planetRAF = null, _planetActive = null;

function clearPlanetMode() {
  if (_planetRAF) { cancelAnimationFrame(_planetRAF); _planetRAF = null; }
  _planetActive = null;
  document.getElementById('planet-canvas').style.display = 'none';
  document.getElementById('planet-hud').style.display = 'none';
  // Satır içi '1' yazılmaz: `#leaflet-map.hidden-3d { opacity: 0 }` kuralını ezip 3B'yi 2B haritanın
  // altında bırakıyordu — TÜRKİYE/DÜNYA'ya bir kez basınca 3B hiç görünmüyordu.
  document.getElementById('leaflet-map').style.opacity = '';
  document.querySelectorAll('.planet-popup-btn').forEach(b => b.classList.remove('active'));
}

/* Gezegen panelinin YALNIZ METNİ. `setPlanetMode`'dan ayrıldı çünkü dil
   değişiminde onu çağırmak canvas'ı yeniden boyutlandırır ve dönüş
   animasyonunu sıfırlardı — çeviri, kullanıcının baktığı sahneyi bozmamalı. */
function _planetHudMetni(key) {
  const p = _gok(key);
  if (!p) return;
  const adEl = document.getElementById('planet-hud-name');
  if (adEl) {
    adEl.textContent = p.symbol + '  ' + p.name;
    adEl.style.color = p.color;
    adEl.style.textShadow = '0 0 30px ' + p.glow;
  }
  const statsEl = document.getElementById('planet-hud-stats');
  if (statsEl) {
    statsEl.innerHTML = [
      ['cap', p.diameter], ['kutle', p.mass],
      ['yercekimi', p.gravity], ['sicaklik', p.temp],
      ['uydular', p.moons], ['yorunge', p.orbit],
      ['gun', p.day], ['mesafe', p.distance],
    ].map(([l, v]) => `<div class="phstat-row"><span class="phstat-lbl">${_escHtml(_mt('uzay.alan.' + l))}</span><span class="phstat-val">${_escHtml(v)}</span></div>`).join('');
  }
}

function setPlanetMode(key) {
  const p = _gok(key);
  if (!p) return;
  // clear other active states
  document.getElementById('map-btn-world').classList.remove('active');
  document.getElementById('map-btn-turkey').classList.remove('active');
  document.querySelectorAll('.planet-popup-btn').forEach(b => b.classList.remove('active'));
  const btnEl = document.getElementById('map-btn-' + key);
  if (btnEl) btnEl.classList.add('active');

  _planetActive = key;
  const cvs = document.getElementById('planet-canvas');
  const hud = document.getElementById('planet-hud');
  cvs.style.display = 'block';
  hud.style.display = 'block';
  document.getElementById('leaflet-map').style.opacity = '0';
  if (_planetRAF) cancelAnimationFrame(_planetRAF);

  // Size canvas
  const center = document.getElementById('map-center');
  cvs.width  = center.offsetWidth  || 800;
  cvs.height = center.offsetHeight || 600;
  const ctx = cvs.getContext('2d');

  _planetHudMetni(key);

  // Draw orrery
  _drawOrrery(key);

  // Planet render loop
  let angle = 0;
  const R = Math.min(cvs.width, cvs.height) * (p.type === 'star' ? 0.28 : 0.22);
  const cx = cvs.width * 0.5, cy = cvs.height * 0.5;

  function frame() {
    if (_planetActive !== key) return;
    ctx.clearRect(0, 0, cvs.width, cvs.height);
    _drawStarField(ctx, cvs.width, cvs.height);
    _drawPlanet(ctx, p, cx, cy, R, angle);
    angle += 0.003;
    _planetRAF = requestAnimationFrame(frame);
  }
  frame();
}

// Persistent star field (drawn once, stored)
let _starCache = null, _starW = 0, _starH = 0;
function _drawStarField(ctx, w, h) {
  if (_starCache && _starW === w && _starH === h) {
    ctx.drawImage(_starCache, 0, 0);
    return;
  }
  const off = document.createElement('canvas');
  off.width = w; off.height = h;
  const oc = off.getContext('2d');
  oc.fillStyle = '#000814';
  oc.fillRect(0, 0, w, h);
  for (let i = 0; i < 320; i++) {
    const x = Math.random() * w, y = Math.random() * h;
    const r = Math.random() * 1.2;
    const a = Math.random() * 0.8 + 0.2;
    oc.beginPath();
    oc.arc(x, y, r, 0, 6.283);
    oc.fillStyle = `rgba(255,255,255,${a})`;
    oc.fill();
  }
  _starCache = off; _starW = w; _starH = h;
  ctx.drawImage(off, 0, 0);
}

function _drawPlanet(ctx, p, cx, cy, R, angle) {
  ctx.save();

  // Rings behind planet (Saturn, Uranus)
  if (p.rings && !p.thinRings) {
    _drawRings(ctx, cx, cy, R, p.color, p.glow, false, angle);
  }
  if (p.rings && p.thinRings) {
    _drawThinRings(ctx, cx, cy, R, p.color, angle);
  }

  // Atmosphere glow
  const gGlow = ctx.createRadialGradient(cx, cy, R * 0.85, cx, cy, R * 1.35);
  gGlow.addColorStop(0, p.glow + '40');
  gGlow.addColorStop(1, 'transparent');
  ctx.beginPath();
  ctx.arc(cx, cy, R * 1.35, 0, Math.PI * 2);
  ctx.fillStyle = gGlow;
  ctx.fill();

  // Main sphere gradient (lit from upper-left)
  const lx = cx - R * 0.4, ly = cy - R * 0.4;
  const gSphere = ctx.createRadialGradient(lx, ly, R * 0.05, cx, cy, R);
  if (p.type === 'star') {
    gSphere.addColorStop(0,   '#fff7e0');
    gSphere.addColorStop(0.25, '#ffd740');
    gSphere.addColorStop(0.6,  p.color);
    gSphere.addColorStop(0.85, p.glow);
    gSphere.addColorStop(1,    p.dark);
  } else if (p.type === 'gas') {
    gSphere.addColorStop(0,   '#fff8e1');
    gSphere.addColorStop(0.3,  p.color);
    gSphere.addColorStop(0.7,  p.glow);
    gSphere.addColorStop(1,    p.dark);
  } else if (p.type === 'ice') {
    gSphere.addColorStop(0,   '#e8f5e9');
    gSphere.addColorStop(0.3,  p.color);
    gSphere.addColorStop(0.7,  p.glow);
    gSphere.addColorStop(1,    p.dark);
  } else {
    gSphere.addColorStop(0,   '#f5f5f5');
    gSphere.addColorStop(0.4,  p.color);
    gSphere.addColorStop(0.75, p.glow);
    gSphere.addColorStop(1,    p.dark);
  }
  ctx.beginPath();
  ctx.arc(cx, cy, R, 0, Math.PI * 2);
  ctx.fillStyle = gSphere;
  ctx.fill();

  // Animated surface bands (gas giants + sun)
  if (p.bands) {
    ctx.save();
    ctx.beginPath();
    ctx.arc(cx, cy, R, 0, Math.PI * 2);
    ctx.clip();
    const bandW = R * 2;
    p.bands.forEach(b => {
      const offset = ((angle * (p.type === 'star' ? 0.5 : 0.3)) % 1);
      const yPos = cy - R + (b.pct + offset) % 1 * bandW;
      const thick = bandW * 0.08;
      const gBand = ctx.createLinearGradient(cx - R, yPos, cx - R, yPos + thick);
      gBand.addColorStop(0, 'transparent');
      gBand.addColorStop(0.5, b.color);
      gBand.addColorStop(1, 'transparent');
      ctx.fillStyle = gBand;
      ctx.fillRect(cx - R, yPos, bandW, thick);
    });
    ctx.restore();
  }

  // Star surface flares
  if (p.type === 'star') {
    for (let i = 0; i < 5; i++) {
      const fa = angle * 0.7 + i * 1.257;
      const fx = cx + Math.cos(fa) * R * 0.92;
      const fy = cy + Math.sin(fa) * R * 0.92;
      const gFlare = ctx.createRadialGradient(fx, fy, 0, fx, fy, R * 0.18);
      gFlare.addColorStop(0, 'rgba(255,255,200,0.35)');
      gFlare.addColorStop(1, 'transparent');
      ctx.beginPath();
      ctx.arc(fx, fy, R * 0.18, 0, Math.PI * 2);
      ctx.fillStyle = gFlare;
      ctx.fill();
    }
  }

  // Highlight glint
  const gHigh = ctx.createRadialGradient(
    cx - R * 0.35, cy - R * 0.35, 0,
    cx - R * 0.35, cy - R * 0.35, R * 0.5
  );
  gHigh.addColorStop(0, 'rgba(255,255,255,0.28)');
  gHigh.addColorStop(1, 'transparent');
  ctx.beginPath();
  ctx.arc(cx, cy, R, 0, Math.PI * 2);
  ctx.fillStyle = gHigh;
  ctx.fill();

  // Shadow side
  const gDark = ctx.createRadialGradient(cx + R * 0.4, cy + R * 0.3, 0, cx, cy, R);
  gDark.addColorStop(0, 'rgba(0,0,0,0.55)');
  gDark.addColorStop(0.6, 'transparent');
  ctx.beginPath();
  ctx.arc(cx, cy, R, 0, Math.PI * 2);
  ctx.fillStyle = gDark;
  ctx.fill();

  // Rings in front (Saturn)
  if (p.rings && !p.thinRings) {
    _drawRings(ctx, cx, cy, R, p.color, p.glow, true, angle);
  }

  ctx.restore();
}

function _drawRings(ctx, cx, cy, R, color, glow, frontHalf, angle) {
  ctx.save();
  ctx.translate(cx, cy);
  ctx.scale(1, 0.28);
  const r1 = R * 1.35, r2 = R * 2.1;
  for (let ri = 0; ri < 6; ri++) {
    const rr = r1 + (r2 - r1) * (ri / 5);
    const alpha = frontHalf ? (0.22 - ri * 0.02) : (0.18 - ri * 0.015);
    ctx.beginPath();
    ctx.arc(0, 0, rr, frontHalf ? 0 : Math.PI, frontHalf ? Math.PI : Math.PI * 2);
    ctx.strokeStyle = color + Math.round(alpha * 255).toString(16).padStart(2,'0');
    ctx.lineWidth = (r2 - r1) / 6.5;
    ctx.stroke();
  }
  ctx.restore();
}

function _drawThinRings(ctx, cx, cy, R, color, angle) {
  ctx.save();
  ctx.translate(cx, cy);
  ctx.rotate(0.4);
  ctx.scale(1, 0.22);
  [R * 1.3, R * 1.55, R * 1.75].forEach((r, i) => {
    ctx.beginPath();
    ctx.arc(0, 0, r, 0, Math.PI * 2);
    ctx.strokeStyle = color + '28';
    ctx.lineWidth = 2;
    ctx.stroke();
  });
  ctx.restore();
}

function _drawOrrery(activeKey) {
  const cvs = document.getElementById('planet-orrery');
  const ctx = cvs.getContext('2d');
  const W = cvs.width, H = cvs.height;
  const cx = W / 2, cy = H / 2;
  ctx.clearRect(0, 0, W, H);
  ctx.fillStyle = 'rgba(0,4,12,0.8)';
  ctx.fillRect(0, 0, W, H);

  // Border
  ctx.strokeStyle = 'rgba(0,212,255,0.15)';
  ctx.lineWidth = 1;
  ctx.strokeRect(0, 0, W, H);

  // Label
  ctx.font = '7px monospace';
  ctx.fillStyle = 'rgba(0,212,255,0.4)';
  ctx.letterSpacing = '2px';
  ctx.fillText('◈ ' + _mt('harita.gunes-sistemi'), 8, 14);

  // Sun dot
  const sunG = ctx.createRadialGradient(cx, cy, 0, cx, cy, 10);
  sunG.addColorStop(0, '#fff7e0');
  sunG.addColorStop(0.5, '#ffd740');
  sunG.addColorStop(1, '#ff6d00');
  ctx.beginPath();
  ctx.arc(cx, cy, 7, 0, Math.PI * 2);
  ctx.fillStyle = sunG;
  ctx.fill();

  const now = Date.now() / 1000;
  const order = ['mercury','venus','mars','jupiter','saturn','uranus','neptune'];
  order.forEach(key => {
    const p = _gok(key);
    // Scale orbit radii to fit in 110px max
    const r = p.orbitR * 0.62;
    // Orbit ring
    ctx.beginPath();
    ctx.arc(cx, cy, r, 0, Math.PI * 2);
    ctx.strokeStyle = key === activeKey ? p.color + '60' : 'rgba(255,255,255,0.06)';
    ctx.lineWidth = key === activeKey ? 1.5 : 0.5;
    ctx.stroke();
    // Planet dot
    const speed = (2 * Math.PI) / (p.orbitPeriod * 365 * 86400);
    const pa = now * speed * 5000000 + key.charCodeAt(0); // phase offset by name
    const px = cx + Math.cos(pa) * r;
    const py = cy + Math.sin(pa) * r;
    const dotR = key === activeKey ? 4 : 2;
    ctx.beginPath();
    ctx.arc(px, py, dotR, 0, Math.PI * 2);
    ctx.fillStyle = p.color;
    ctx.fill();
    if (key === activeKey) {
      ctx.strokeStyle = p.color + 'a0';
      ctx.lineWidth = 1;
      ctx.stroke();
    }
  });

  // Earth
  const earthP = _gok('mercury'); // reuse orbit logic
  const earthR = 62; // ~1 AU scaled
  ctx.beginPath();
  ctx.arc(cx, cy, earthR, 0, Math.PI * 2);
  ctx.strokeStyle = activeKey === 'earth' ? '#64ffda60' : 'rgba(255,255,255,0.06)';
  ctx.lineWidth = activeKey === 'earth' ? 1.5 : 0.5;
  ctx.stroke();
  const eSpeed = (2 * Math.PI) / (365 * 86400);
  const eAngle = now * eSpeed * 5000000 + 42;
  const ex = cx + Math.cos(eAngle) * earthR;
  const ey = cy + Math.sin(eAngle) * earthR;
  ctx.beginPath();
  ctx.arc(ex, ey, activeKey === 'earth' ? 4 : 2, 0, Math.PI * 2);
  ctx.fillStyle = '#64ffda';
  ctx.fill();
}

// ── View Mode Filters (M7) ─────────────────────────────
// 🔴 Ad `mapGorselMod` (2026-10-04): eskiden `setViewMode`'du ve global bir
// bildirimdi. modes/chat-modes.js bu dosyadan SONRA yükleniyor ve
// `window.setViewMode`'u SOHBET görünümü (chat/hud-ring) için yeniden yazıyor →
// EO/FLIR/NV/CRT tıklaması `setViewMode('flir')` = sohbet moduna 'flir' isteği
// oluyor, chat-modes geçersiz anahtarı 'chat'e çeviriyordu. Harita filtresi
// hiç uygulanmıyor, hata da çıkmıyordu (Playwright ölçümü, 10-04).
let _currentViewMode = 'eo';
function mapGorselMod(mode) {
  const map = document.getElementById('leaflet-map');
  if (!map) return;
  ['vf-flir', 'vf-night', 'vf-crt'].forEach(c => map.classList.remove(c));
  ['vbtn-eo', 'vbtn-flir', 'vbtn-night', 'vbtn-crt'].forEach(id => {
    const el = document.getElementById(id);
    if (el) el.classList.remove('active', 'flir-active', 'night-active', 'crt-active');
  });
  _currentViewMode = mode;
  ['eo', 'flir', 'night', 'crt'].forEach(m => {
    const el = document.getElementById('vbtn-' + m);
    if (el) el.setAttribute('aria-pressed', m === mode ? 'true' : 'false');
  });
  const btn = document.getElementById('vbtn-' + mode);
  if (mode === 'eo') {
    if (btn) btn.classList.add('active');
  } else if (mode === 'flir') {
    map.classList.add('vf-flir');
    if (btn) btn.classList.add('active', 'flir-active');
  } else if (mode === 'night') {
    map.classList.add('vf-night');
    if (btn) btn.classList.add('active', 'night-active');
  } else if (mode === 'crt') {
    map.classList.add('vf-crt');
    if (btn) btn.classList.add('active', 'crt-active');
  }
}

// ── Scope Overlay (M8) ────────────────────────────────
let _scopeActive = false;
function toggleScope() {
  _scopeActive = !_scopeActive;
  const overlay = document.getElementById('map-scope-overlay');
  const btn = document.getElementById('vbtn-scope');
  if (overlay) overlay.classList.toggle('active', _scopeActive);
  if (btn) btn.classList.toggle('active', _scopeActive);
}

// ── Timeline Scrubber (Step 7) ────────────────────────
let _tlEvents = [];
let _tlCursorMs = null;
let _tlIsLive = true;
let _tlLoaded = false;
const _TL_WINDOW_MS = 6 * 3600 * 1000; // ±6h filter window
const _TL_SPAN_MS   = 7 * 24 * 3600 * 1000; // 7 days

function tlToggle() {
  const tl  = document.getElementById('map-timeline');
  const vb  = document.getElementById('map-view-bar');
  const btn = document.getElementById('vbtn-tl');
  if (!tl.classList.contains('tl-open')) {
    tl.classList.add('tl-open');
    if (vb) vb.classList.add('tl-shift');
    if (btn) btn.classList.add('active');
    if (!_tlLoaded) tlLoad();
    else tlDraw();
  } else {
    tlCollapse();
  }
}

function tlCollapse() {
  const tl  = document.getElementById('map-timeline');
  const vb  = document.getElementById('map-view-bar');
  const btn = document.getElementById('vbtn-tl');
  tl.classList.remove('tl-open');
  if (vb) vb.classList.remove('tl-shift');
  if (btn) btn.classList.remove('active');
  tlGoLive();
}


async function tlLoad() {
  const label = document.getElementById('tl-window-label');
  if (label) label.textContent = _mt('harita.yukleniyor');
  try {
    const r = await fetch('https://earthquake.usgs.gov/earthquakes/feed/v1.0/summary/2.5_week.geojson');
    const d = await r.json();
    _tlEvents = d.features.map(f => ({
      lat:   f.geometry.coordinates[1],
      lon:   f.geometry.coordinates[0],
      depth: f.geometry.coordinates[2],
      mag:   f.properties.mag,
      place: f.properties.place,
      time_ms: f.properties.time
    })).sort((a, b) => a.time_ms - b.time_ms);
    _tlLoaded = true;
    if (label) label.textContent = _mtc('harita.tl-pencere', _tlEvents.length, { sayi: _tlEvents.length });
    tlDraw();
  } catch (e) {
    if (label) label.textContent = _mt('harita.veri-yuklenemedi');
  }
}

function _tlMagColor(mag) {
  if (mag >= 6)  return '#ff1744';
  if (mag >= 5)  return '#ff6d00';
  if (mag >= 4)  return '#ffd740';
  return '#69f0ae';
}

function tlDraw() {
  const canvas = document.getElementById('tl-canvas');
  if (!canvas || !_tlLoaded) return;
  const W = canvas.offsetWidth || canvas.parentElement.offsetWidth;
  const H = 60;
  canvas.width  = W;
  canvas.height = H;
  const ctx = canvas.getContext('2d');
  const now    = Date.now();
  const start  = now - _TL_SPAN_MS;

  const toX = ms => Math.round(((ms - start) / _TL_SPAN_MS) * (W - 20) + 10);

  // Day ticks
  ctx.strokeStyle = 'rgba(0,212,255,0.12)';
  ctx.lineWidth = 1;
  ctx.fillStyle = 'rgba(0,212,255,0.35)';
  ctx.font = '8px "Space Mono", monospace';
  ctx.textAlign = 'center';
  const dayMs = 86400000;
  let day = new Date(start); day.setHours(0,0,0,0);
  while (day.getTime() <= now) {
    const x = toX(day.getTime());
    if (x >= 0 && x <= W) {
      ctx.beginPath(); ctx.moveTo(x, 0); ctx.lineTo(x, H - 12); ctx.stroke();
      const lbl = day.toLocaleDateString('tr-TR', { month: '2-digit', day: '2-digit' });
      ctx.fillText(lbl, Math.min(Math.max(x, 20), W - 20), H - 2);
    }
    day = new Date(day.getTime() + dayMs);
  }

  // Earthquake dots
  for (const ev of _tlEvents) {
    const x = toX(ev.time_ms);
    if (x < 0 || x > W) continue;
    const r = Math.max(2, Math.min(5, (ev.mag - 1.5)));
    const dimmed = _tlCursorMs !== null && Math.abs(ev.time_ms - _tlCursorMs) > _TL_WINDOW_MS;
    ctx.beginPath();
    ctx.arc(x, H / 2 - 8, r, 0, Math.PI * 2);
    ctx.fillStyle = dimmed ? 'rgba(255,255,255,0.1)' : _tlMagColor(ev.mag);
    ctx.globalAlpha = dimmed ? 0.18 : 0.85;
    ctx.fill();
    ctx.globalAlpha = 1;
  }

  // NOW marker
  const nowX = toX(now);
  ctx.beginPath();
  ctx.strokeStyle = 'rgba(255,68,68,0.7)';
  ctx.lineWidth = 1.5;
  ctx.setLineDash([3,3]);
  ctx.moveTo(nowX, 0); ctx.lineTo(nowX, H - 14);
  ctx.stroke();
  ctx.setLineDash([]);

  // Cursor line (via DOM element for smooth drag)
  const cursorEl = document.getElementById('tl-cursor-line');
  if (_tlCursorMs !== null && cursorEl) {
    const cx = toX(_tlCursorMs);
    cursorEl.style.display = 'block';
    cursorEl.style.left = cx + 'px';
  } else if (cursorEl) {
    cursorEl.style.display = 'none';
  }
}

function _tlXToMs(x, W) {
  const now   = Date.now();
  const start = now - _TL_SPAN_MS;
  return start + ((x - 10) / (W - 20)) * _TL_SPAN_MS;
}

function _tlNearestEvent(ms) {
  let best = null, bestDiff = Infinity;
  for (const ev of _tlEvents) {
    const diff = Math.abs(ev.time_ms - ms);
    if (diff < bestDiff) { bestDiff = diff; best = ev; }
  }
  return { event: best, diff: bestDiff };
}

// Attach canvas events after DOM ready
(function _tlAttachEvents() {
  const run = () => {
    const canvas = document.getElementById('tl-canvas');
    if (!canvas) return;

    canvas.addEventListener('click', e => {
      if (!_tlLoaded) return;
      const rect = canvas.getBoundingClientRect();
      const ms = _tlXToMs(e.clientX - rect.left, canvas.offsetWidth);
      _tlSetCursor(ms);
      const { event: ev } = _tlNearestEvent(ms);
      if (ev && _lmap) _lmap.flyTo([ev.lat, ev.lon], 5, { duration: 0.9 });
    });

    canvas.addEventListener('mousemove', e => {
      if (!_tlLoaded) return;
      const rect = canvas.getBoundingClientRect();
      const x    = e.clientX - rect.left;
      const ms   = _tlXToMs(x, canvas.offsetWidth);
      const tip  = document.getElementById('tl-hover-tip');
      const { event: ev, diff } = _tlNearestEvent(ms);
      const snapPx = Math.abs(x - (10 + ((ev ? ev.time_ms - (Date.now() - _TL_SPAN_MS) : 0) / _TL_SPAN_MS) * (canvas.offsetWidth - 20)));
      if (ev && snapPx < 12 && tip) {
        const dt = new Date(ev.time_ms);
        tip.style.display = 'block';
        tip.style.left = Math.min(x + 10, canvas.offsetWidth - 160) + 'px';
        tip.textContent = `M${ev.mag.toFixed(1)} · ${ev.place} · ${dt.toLocaleDateString('tr-TR', {month:'2-digit',day:'2-digit',hour:'2-digit',minute:'2-digit'})}`;
      } else if (tip) {
        tip.style.display = 'none';
      }
    });

    canvas.addEventListener('mouseleave', () => {
      const tip = document.getElementById('tl-hover-tip');
      if (tip) tip.style.display = 'none';
    });
  };
  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', run);
  else run();
})();

function _tlSetCursor(ms) {
  _tlCursorMs = ms;
  _tlIsLive = false;
  const liveBtn = document.getElementById('tl-btn-live');
  if (liveBtn) liveBtn.classList.remove('live-pulse');
  const dt = new Date(ms);
  const label = document.getElementById('tl-window-label');
  if (label) label.textContent = `±6s · ${dt.toLocaleDateString('tr-TR',{month:'2-digit',day:'2-digit',hour:'2-digit',minute:'2-digit'})}`;
  tlDraw();
  tlApplyFilter();
}

function tlGoLive() {
  _tlCursorMs = null;
  _tlIsLive = true;
  const liveBtn = document.getElementById('tl-btn-live');
  if (liveBtn) liveBtn.classList.add('live-pulse');
  const label = document.getElementById('tl-window-label');
  if (_tlLoaded && label) label.textContent = _mtc('harita.tl-pencere', _tlEvents.length, { sayi: _tlEvents.length });
  else if (label) label.textContent = '—';
  tlDraw();
  // Restore eq layer to 24h live data
  if (_layerActive['eq'] && _layerGroups['eq']) {
    _fetchLayer('eq');
  }
}

function tlApplyFilter() {
  if (!_layerActive['eq'] || !_tlCursorMs) return;
  const lg = _layerGroups['eq'];
  if (!lg) return;
  lg.clearLayers();
  const filtered = _tlEvents.filter(ev => Math.abs(ev.time_ms - _tlCursorMs) <= _TL_WINDOW_MS);
  for (const ev of filtered) {
    const r_px = Math.max(4, ev.mag * 3);
    L.circleMarker([ev.lat, ev.lon], {
      radius: r_px, color: '#ff6b35', fillColor: '#ff6b35',
      fillOpacity: 0.35, weight: 1
    }).bindPopup(`<b>M${ev.mag.toFixed(1)}</b><br>${_escHtml(ev.place)}<br>${_escHtml(_mt('harita.derinlik', { km: ev.depth.toFixed(0) }))}`)
      .addTo(lg);
  }
  showToast(_mtc('harita.tl-gosteriliyor', filtered.length, { sayi: filtered.length }));
}

// (SYS VITALS · TOOL FEED · MAP QUICK ACTIONS: `mapQA` YUKI KANALI mini sohbetine
//  yazıyordu; kanal 2026-10-04'te kalktı, fonksiyon da.)

// ── Location helpers ───────────────────────────────────
function updateMapLocation(lat, lon, city) {
  document.getElementById('map-lat').textContent  = lat.toFixed(4);
  document.getElementById('map-lon').textContent  = lon.toFixed(4);
  document.getElementById('map-city').textContent = city || '—';
}

async function fetchCityName(lat, lon) {
  try {
    const r = await fetch(
      `https://nominatim.openstreetmap.org/reverse?lat=${lat}&lon=${lon}&format=json`,
      { headers: { 'Accept-Language': 'tr' } }
    );
    const d = await r.json();
    return d.address?.city || d.address?.town || d.address?.village || d.address?.county || null;
  } catch { return null; }
}

async function fetchIPLocation() {
  try {
    const d = await (await fetch('https://ipapi.co/json/')).json();
    if (d.latitude) _onGeoSuccess(d.latitude, d.longitude);
  } catch {}
}

// ── Weather ────────────────────────────────────────────
async function fetchWeather(lat, lon) {
  try {
    const url = `https://api.open-meteo.com/v1/forecast?latitude=${lat}&longitude=${lon}&current=temperature_2m,wind_speed_10m,weather_code`;
    const d = await (await fetch(url)).json();
    const c = d.current;
    // Ondalık ayracı dile göre (tr: "14,7 °C") — YAKINDA kartıyla aynı yazım (Gözlemevi, goz 11-13)
    document.getElementById('map-temp').textContent         = Number(c.temperature_2m).toLocaleString(_myerel()) + ' °C';
    document.getElementById('map-wind').textContent         = Number(c.wind_speed_10m).toLocaleString(_myerel()) + ' km/h';
    _sonWmoKodu = c.weather_code;
    document.getElementById('map-weather-desc').textContent = wmoCode(c.weather_code);
  } catch {}
}

/* Son okunan WMO kodu — dil değişiminde metni yeniden üretmek için.
   Saklamasaydık tazeleme Open-Meteo'ya yeni bir istek atmak zorunda kalırdı. */
let _sonWmoKodu = null;

function wmoCode(code) {
  // Eşik → kimlik; metin sözlükten. Eşikler WMO standardı (teknik), metin değil.
  const k = code === 0 ? 'acik'
    : code <= 3  ? 'parcali-bulutlu'
    : code <= 9  ? 'sisli'
    : code <= 19 ? 'yagis-izi'
    : code <= 29 ? 'firtinali'
    : code <= 39 ? 'tozlu'
    : code <= 49 ? 'sis'
    : code <= 59 ? 'cisenti'
    : code <= 69 ? 'yagmurlu'
    : code <= 79 ? 'karli'
    : code <= 84 ? 'saganak'
    : code <= 94 ? 'dolu'
    : 'gokgurultulu-firtina';
  return _mt('harita.hava-kodu.' + k);
}

// ══════════════════════════════════════════════════════
//  GÖKYÜZÜ (yer şeridinin GÖK bölümü) + GÜNDEM
// ══════════════════════════════════════════════════════
let _mapRefreshInterval = null;
let _mapUserLat = null, _mapUserLon = null;

async function updateSpaceCard(userLat, userLon) {
  _mapUserLat = userLat; _mapUserLon = userLon;

  // Kp — jeomanyetik fırtına (NOAA, backend proxy). Şeridin GÖK bölümü; aynı veri
  // Kp katmanında ve yöneticideki göstergede de (tek sözlük: _kpSeviye).
  // BEKLENMEDEN başlar: aşağıdaki üç dış istek (ISS, Open-Meteo, DONKI) sırayla
  // bekleniyor ve biri yavaşsa Kp şeritte "—" kalıyordu (ölçüldü, 10-04).
  (async () => {
    try {
      const r = await authFetch(BASE_URL + '/api/map/kpindex');
      const d = await r.json();
      const kpEl = document.getElementById('map-kp');
      const lvEl = document.getElementById('map-kp-level');
      if (kpEl && typeof d.kp === 'number') kpEl.textContent = d.kp.toLocaleString(_myerel(), { minimumFractionDigits: 1, maximumFractionDigits: 1 });
      if (lvEl) lvEl.textContent = d.level ? _kpSeviye(d.level) : '—';
    } catch {}
  })();

  // ISS uzaklık (Haversine + altitude)
  try {
    const r = await fetch('https://api.wheretheiss.at/v1/satellites/25544');
    const d = await r.json();
    const R = 6371;
    const dLat = (d.latitude  - userLat) * Math.PI / 180;
    const dLon = (d.longitude - userLon) * Math.PI / 180;
    const a = Math.sin(dLat/2)**2 +
      Math.cos(userLat*Math.PI/180)*Math.cos(d.latitude*Math.PI/180)*Math.sin(dLon/2)**2;
    const ground = R * 2 * Math.atan2(Math.sqrt(a), Math.sqrt(1-a));
    const total  = Math.round(Math.sqrt(ground**2 + d.altitude**2));
    document.getElementById('map-iss-dist').textContent = total.toLocaleString() + ' km';
  } catch {}

  // Ay fazı — saf JS hesabı (Open-Meteo moon_phase parametresini desteklemiyor)
  try {
    const lp = 2551443000; // 29.53 gün ms
    const ref = new Date(2000, 0, 6, 18, 14, 0).getTime(); // bilinen yeni ay referansı
    const p = ((Date.now() - ref) % lp + lp) % lp / lp;
    // ⚠️ İki ayrı faz da 'HİLAL' der ama AYNI ŞEY DEĞİL: ilki büyüyen,
    // ikincisi küçülen hilal. TR'de ikisine de hilal denir, EN'de ayrışır
    // (waxing/waning crescent) — tek anahtara bağlamak İngilizceyi bozardı.
    const moonKey = p < 0.04 || p > 0.96 ? 'yeni-ay'
      : p < 0.22 ? 'hilal-buyuyen'
      : p < 0.28 ? 'ilk-dordun'
      : p < 0.46 ? 'sisan-ay'
      : p < 0.54 ? 'dolunay'
      : p < 0.72 ? 'azalan-ay'
      : p < 0.78 ? 'son-dordun'
      : 'hilal-kuculen';
    const moonLabel = _mt('harita.ay-fazi.' + moonKey);
    document.getElementById('map-moon').textContent = moonLabel;
  } catch {}

  // Güneş doğuş/batış — Open-Meteo (sadece sunrise+sunset)
  try {
    const url = `https://api.open-meteo.com/v1/forecast?latitude=${userLat}&longitude=${userLon}&daily=sunrise,sunset&timezone=auto&forecast_days=1`;
    const d = await (await fetch(url)).json();
    const rise = (d.daily?.sunrise?.[0] || '').slice(11, 16) || '—';
    const set_ = (d.daily?.sunset?.[0]  || '').slice(11, 16) || '—';
    document.getElementById('map-sunrise').textContent = rise;
    document.getElementById('map-sunset').textContent  = set_;
  } catch {}

  // Solar flarlar — backend proxy
  try {
    const r = await authFetch(BASE_URL + '/api/map/solar');
    const d = await r.json();
    const el = document.getElementById('map-solar');
    const grup = document.getElementById('map-solar-grup');
    if (d.flares && d.flares.length > 0) {
      const latest = d.flares[d.flares.length - 1];
      el.textContent = latest.cls + ' ' + latest.time.slice(5, 10);
    } else {
      el.textContent = _mt('harita.kp-seviye.calm');
    }
    if (grup) grup.hidden = false;
  } catch {
    // Veri yoksa öğe görünmez — "güneş —" boş hücre bırakmasın (göz tur 2)
    const grup = document.getElementById('map-solar-grup');
    if (grup) grup.hidden = true;
  }

}

// (PİYASA kartı 2026-10-04'te kalktı: `updateMarketCard` CoinGecko + /api/map/stocks +
//  frankfurter'a dakikada bir istek atıyordu; kart da çağrılar da gitti.)

// ── GÜNDEM (sol alt kart) ─────────────────────────────
// Google Haberler RSS'inde haber başlığı "Başlık - Kaynak" kalıbındadır. Akışın ilk
// <title>'ı ise KANALIN adıdır ("Google Haberler") ve backend onu da öğe diye döndürür.
// 🔴 Süzgeç ADA değil KALIBA bakar: kaynak eki olmayan ve 4 kelimeden kısa satır bir
// haber değil akış başlığıdır. Ada bakan süzgeç ("Google Haberler" !==) dil ya da
// bölge değişince ("Google News") sessizce çöpü geri getirirdi. (kişisel 09-28)
function _haberAyir(ham) {
  const t = String(ham || '').replace(/\s+/g, ' ').trim();
  const m = t.match(/^(.*\S)\s+[-–—]\s+([^-–—]{2,40})$/);
  if (m) return { baslik: m[1], kaynak: m[2].trim() };
  if (t.split(' ').length < 4) return null;          // kanal/akış başlığı — haber değil
  return { baslik: t, kaynak: '' };
}

async function updateNewsCard() {
  const list = document.getElementById('map-news-list');
  if (!list) return;
  const sayiEl = document.getElementById('map-gundem-sayi');
  try {
    const r = await authFetch(BASE_URL + '/api/map/news');
    const d = await r.json();
    const gorulen = new Set();
    // Backend aynı olayın başlıklarını tek öğeye toplar (services/gundem_kume.py):
    // `kaynaklar` o olayı veren kaynaklar, ilki temsilci başlığınki. Kümeleme kapalıysa alanlar yok.
    const haberler = (d.items || []).map(it => {
      const h = _haberAyir(it && it.title);
      if (h) h.diger = (Array.isArray(it.kaynaklar) ? it.kaynaklar : [])
        .map(k => String(k || '').trim()).filter(k => k && k !== h.kaynak);
      return h;
    }).filter(h => {
      if (!h || gorulen.has(h.baslik)) return false;
      gorulen.add(h.baslik); return true;
    }).slice(0, 6);
    if (sayiEl) sayiEl.textContent = String(haberler.length);
    if (!haberler.length) { list.innerHTML = `<li class="mh-bos">${_escHtml(_mt('harita.haber-yok'))}</li>`; return; }
    list.innerHTML = haberler.map(h =>
      `<li><button type="button" class="mh-haber" data-soru="${_escHtml(h.baslik)}" title="${_escHtml(_mt('harita.gundem-ipucu'))}">` +
      `<span class="mh-haber-t">${_escHtml(h.baslik)}</span>` +
      (h.diger.length
        ? `<span class="mh-haber-k mh-haber-k2"><span class="mh-haber-ka">${_escHtml(h.kaynak)}</span>` +
          `<span class="mh-haber-n" title="${_escHtml(_mt('harita.gundem-kaynak', { n: h.diger.length, adlar: h.diger.join(' · ') }))}">+${h.diger.length}</span></span>`
        : (h.kaynak ? `<span class="mh-haber-k">${_escHtml(h.kaynak)}</span>` : '')) +
      `</button></li>`
    ).join('');
  } catch (e) {
    if (sayiEl) sayiEl.textContent = '—';
    list.innerHTML = `<li class="mh-bos">${_escHtml(_mt('harita.haber-alinamadi', { hata: e.message || '—' }))}</li>`;
  }
}

// Habere tık → sohbete soru (mapSendMessage). Tek dinleyici, satır başına inline
// onclick yok: eski kart başlığı `onclick="mapSendMessage('…')"` içine yalnız
// tek tırnağı kaçırarak koyuyordu — `"` ya da `<` taşıyan başlık özniteliği bozardı.
document.addEventListener('click', function (e) {
  const b = e.target.closest && e.target.closest('#map-news-list .mh-haber');
  if (!b) return;
  const baslik = b.getAttribute('data-soru') || '';
  if (baslik) mapSendMessage(_mt('harita.sor.haber', { baslik }));
});

function startMapRefresh() {
  updateNewsCard();
  if (_mapUserLat !== null) updateSpaceCard(_mapUserLat, _mapUserLon);
  // Tek zamanlayıcı; konum her gelişinde yeniden kurulur, eskisi temizlenir.
  if (_mapRefreshInterval) clearInterval(_mapRefreshInterval);
  _mapRefreshInterval = setInterval(() => {
    updateNewsCard();
    if (_mapUserLat !== null) updateSpaceCard(_mapUserLat, _mapUserLon);
  }, 60000);
}

// ══════════════════════════════════════════════════════
//  MAP CONFIRM POPUP
// ══════════════════════════════════════════════════════
let _pendingMapQuery = null;

function mapConfirmShow(lat, lon, city, query) {
  _pendingMapQuery = query;
  const panel = document.getElementById('map-confirm');
  const locEl = document.getElementById('map-confirm-loc');
  const qEl   = document.getElementById('map-confirm-query');
  const okBtn = document.getElementById('map-confirm-ok');
  if (!panel) return;
  locEl.textContent = `◈ ${lat}, ${lon}${city ? ' — ' + city.toUpperCase() : ''}`;
  qEl.textContent   = '"' + query + '"';
  okBtn.onclick     = function() { const q = _pendingMapQuery; mapConfirmClose(); if (q) mapSendMessage(q); };
  panel.classList.add('show');
}

function mapConfirmClose() {
  const panel = document.getElementById('map-confirm');
  if (panel) panel.classList.remove('show');
  _pendingMapQuery = null;
}

// ══════════════════════════════════════════════════════
//  HARİTADAN SORU — geri bildirim
// ══════════════════════════════════════════════════════
// YUKI KANALI mini sohbeti 2026-10-04'te kalktı (SOHBET sekmesinin ikiziydi —
// kişisel 09-28 kararı). Ad korunuyor: rota/bölge/canlı takip kodu (~15 çağrı)
// bunu `typeof` ile çağırıyor. Artık kısa bir bildirim basıyor:
//   'system' → durum satırı (rota çizildi, konum alınamadı …)
//   'user' / 'yuki' → sessiz. Cevap SOHBET'te; harita cevabı YANSITMAZ
//   (geliştirici 09-28: "Yuki:" bildirimi 5 satır · 7 sn kontrolleri örtüyordu).
function appendMapMessage(role, text) {
  if (role !== 'system' || !text || typeof showToast !== 'function') return;
  showToast(String(text), /^⚠/.test(text) ? 'error' : '', 4000);
}

let _mapLastCoords = null; // { lat, lon, city }

// ── Konum sorgusunu AI'dan BAĞIMSIZ haritada göster ──────────────
// LLM'in harita tool'u patlasa da ("harita oluşturma sırasında hata"),
// konumu frontend Nominatim ile geocode edip _lmap üzerinde gösterir.
// (Yuki Widget'taki _ssbTryMapLocation ile aynı mantık.)
const _MAP_LOC_KEYWORDS = /(?<![\wçğıöşüÇĞİÖŞÜ])(nerede|nerde|konum|haritada|haritasın|haritaya|konumu|konumunu|nerededir|lokasyon|neresi|göster|location|where is|show on map|map it|coordinates of)(?![\wçğıöşüÇĞİÖŞÜ])/i;
const _MAP_TR_STOP = /(?<![\wçğıöşüÇĞİÖŞÜ])(selam|merhaba|evet|hayır|tamam|lütfen|acaba|galiba|sanırım|yani|şimdi|biraz|çok|az|hani|şu|bu|ben|sen|o|biz|siz|bir|ve|de|da|ile|için|ne|nasıl|neden|niçin|çünkü|fakat|ama|ya|veya|hem|ya da|peki)(?![\wçğıöşüÇĞİÖŞÜ])/gi;

async function _mapTryShowLocation(text) {
  if (!_lmap || typeof L === 'undefined') return false;
  if (!_MAP_LOC_KEYWORDS.test(text)) return false;
  // Stop-word + konum keyword'lerini temizle → saf konum sorgusu
  const query = text
    .replace(_MAP_LOC_KEYWORDS, '')
    .replace(_MAP_TR_STOP, '')
    .replace(/[^a-zA-ZığüşöçİĞÜŞÖÇ0-9\s]/g, ' ')
    .replace(/\s+/g, ' ')
    .trim();
  if (!query || query.length < 2) return false;
  try {
    const r = await fetch(
      `https://nominatim.openstreetmap.org/search?q=${encodeURIComponent(query)}&format=json&limit=1`,
      { headers: { 'Accept-Language': 'tr,en' } }
    );
    const d = await r.json();
    if (!d || !d[0]) return false;
    const la = parseFloat(d[0].lat), lo = parseFloat(d[0].lon);
    const shortName = (d[0].display_name || query).split(',')[0];
    _lmap.flyTo([la, lo], 11, { animate: true, duration: 1.2 });
    if (window._mapChatLocMarker) { try { _lmap.removeLayer(window._mapChatLocMarker); } catch (_) {} window._mapChatLocMarker = null; }
    window._mapChatLocMarker = L.circleMarker([la, lo], {
      radius: 7, fillOpacity: 0.85, weight: 2, className: 'lf-isaret-secim'
    }).bindPopup(`◈ ${_escHtml(shortName)}`).addTo(_lmap).openPopup();
    return true;
  } catch (_) { return false; }
}

// ── Yol tarifi (rota) — AI'dan BAĞIMSIZ, OSRM ile ────────────────
// "benim konumumdan Manisa yol tarifi", "X'den Y'ye rota", "Ankara nasıl gidilir"
// gibi sorguları yakalar; LLM yanıtından bağımsız _lmap üzerinde rota çizer.
const _MAP_ROUTE_KEYWORDS = /(?<![\wçğıöşüÇĞİÖŞÜ])(yol\s*tarif[a-zığüşöçİĞÜŞÖÇ]*|tarif\s*ver[a-zığüşöçİĞÜŞÖÇ]*|nasıl\s*gid[a-zığüşöçİĞÜŞÖÇ]*|rota[a-zığüşöçİĞÜŞÖÇ]*|güzergah[a-zığüşöçİĞÜŞÖÇ]*|yol\s*göster[a-zığüşöçİĞÜŞÖÇ]*|directions?|route\s*to|navigate\s*to|how\s*to\s*get|get\s*directions)(?![\wçğıöşüÇĞİÖŞÜ])/i;

// "Benim konumum" / GPS koordinatını döndür (yoksa null)
function _mapGetMyCoords() {
  return new Promise((resolve) => {
    if (_mapLastCoords) return resolve(_mapLastCoords);
    if (!navigator.geolocation) return resolve(null);
    navigator.geolocation.getCurrentPosition(
      (pos) => { _mapLastCoords = { lat: pos.coords.latitude, lon: pos.coords.longitude, city: '' }; resolve(_mapLastCoords); },
      () => resolve(null),
      { timeout: 5000, maximumAge: 60000 }
    );
  });
}

// ── Opsiyonel Mapbox katmanı: token varsa trafikli rota + geocoding + isochrone ──
// Token kaynağı: localStorage('MAPBOX_TOKEN') → backend /api/map/config (.env MAPBOX_TOKEN).
// Yoksa → OSRM/Nominatim'e şeffaf fallback (sıfır regresyon).
let _mapboxToken = (typeof localStorage !== 'undefined' && localStorage.getItem('MAPBOX_TOKEN')) || '';
let _mapboxChecked = false;
async function _mapEnsureMapbox() {
  if (_mapboxChecked) return _mapboxToken;
  _mapboxChecked = true;
  if (_mapboxToken) return _mapboxToken;
  try {
    const base = (typeof BASE_URL !== 'undefined' ? BASE_URL : '');
    const _f = (typeof authFetch === 'function') ? authFetch : fetch;   // /api/* auth middleware → Bearer gerekli
    const r = await _f(base + '/api/map/config');
    if (r.ok) { const d = await r.json(); if (d && d.mapbox_token) _mapboxToken = d.mapbox_token; }
  } catch (_) {}
  return _mapboxToken;
}

async function _mapGeocode(q) {
  try {
    const tok = await _mapEnsureMapbox();
    if (tok) {
      const r = await fetch(`https://api.mapbox.com/geocoding/v5/mapbox.places/${encodeURIComponent(q)}.json?access_token=${tok}&limit=1&language=tr`).then(x => x.json());
      const f = r && r.features && r.features[0];
      if (f && Array.isArray(f.center)) return { lat: f.center[1], lon: f.center[0], name: (f.text || f.place_name || q) };
      return null;
    }
    const r2 = await fetch(`https://nominatim.openstreetmap.org/search?q=${encodeURIComponent(q)}&format=json&limit=1`,
      { headers: { 'Accept-Language': 'tr,en' } }).then(x => x.json());
    if (!r2 || !r2[0]) return null;
    return { lat: parseFloat(r2[0].lat), lon: parseFloat(r2[0].lon), name: (r2[0].display_name || q).split(',')[0] };
  } catch (_) { return null; }
}

function _mapCleanPlaceStr(s) {
  return s
    .replace(_MAP_ROUTE_KEYWORDS, ' ')
    .replace(/(?<![\wçğıöşüÇĞİÖŞÜ])(benim|konumumdan|konumumu|konumum|buradan|bulunduğum|mevcut|konum|gösterir|göster|verir|ver|misin|mısın|musun|lütfen|bana|nasıl|gidilir|giderim|en|yakın|yakını|yakında|yakınında|kısa|hızlı|güzergah|güzergahı|arası|arasında|nearest|shortest|fastest|route|directions|show|me|please|from|here|my|location|to|için|ile)(?![\wçğıöşüÇĞİÖŞÜ])/gi, ' ')
    .replace(/['’‘](y?[ae])(?![\wçğıöşüÇĞİÖŞÜ])/gi, ' ')
    .replace(/['’‘]?(d[ae]n|t[ae]n)(?![\wçğıöşüÇĞİÖŞÜ])/gi, ' ')
    .replace(/[^a-zA-ZığüşöçİĞÜŞÖÇ0-9\s]/g, ' ')
    .replace(/\s+/g, ' ').trim();
}

function _mapManeuverArrow(st) {
  const mod  = (st.maneuver && st.maneuver.modifier) || '';
  const type = (st.maneuver && st.maneuver.type) || '';
  if (type === 'depart') return '▸';
  if (type === 'arrive') return '◉';
  if (mod.indexOf('uturn') >= 0)    return '⮌';
  if (mod.indexOf('left') >= 0)     return '↰';
  if (mod.indexOf('right') >= 0)    return '↱';
  if (mod.indexOf('straight') >= 0) return '↑';
  return '•';
}

function _mapClearRoute(hideHud) {
  if (window._mapRouteAnimRaf) { cancelAnimationFrame(window._mapRouteAnimRaf); window._mapRouteAnimRaf = null; }
  if (window._mapRouteAnimMarker) { try { _lmap.removeLayer(window._mapRouteAnimMarker); } catch (_) {} window._mapRouteAnimMarker = null; }
  if (window._mapRouteLine) { try { _lmap.removeLayer(window._mapRouteLine); } catch (_) {} window._mapRouteLine = null; }
  (window._mapRouteMarkers || []).forEach(m => { try { _lmap.removeLayer(m); } catch (_) {} });
  window._mapRouteMarkers = [];
  if (hideHud) { const c = document.getElementById('map-card-route'); if (c) c.style.display = 'none'; }
}

function _mapRenderRouteHud(from, dests, km, mins, route) {
  const card = document.getElementById('map-card-route');
  if (!card) return;
  card.style.display = '';
  const setT = (id, v) => { const e = document.getElementById(id); if (e) e.textContent = v; };
  setT('map-route-from', from.name);
  setT('map-route-to', dests[dests.length - 1].name);
  setT('map-route-dist', _mt('harita.km', { km }));
  setT('map-route-eta', _mt('harita.dk', { dk: mins }));
  const stopsRow = document.getElementById('map-route-stops-row');
  if (stopsRow) { if (dests.length > 1) { stopsRow.style.display = ''; setT('map-route-stops', _mtc('harita.durak-sayisi', dests.length, { sayi: dests.length })); } else stopsRow.style.display = 'none'; }
  const stepsEl = document.getElementById('map-route-steps');
  if (stepsEl) {
    const rows = [];
    (route.legs || []).forEach(leg => (leg.steps || []).forEach(st => {
      const nm = (st.maneuver && st.maneuver.instruction) || st.name || (st.maneuver && st.maneuver.type) || '';
      const d  = st.distance >= 1000 ? (st.distance / 1000).toFixed(1) + ' km' : Math.round(st.distance) + ' m';
      rows.push(`<div>${_mapManeuverArrow(st)} ${_escHtml(nm || '—')} <span style="opacity:.55">· ${_escHtml(d)}</span></div>`);
    }));
    stepsEl.innerHTML = rows.slice(0, 60).join('') || `<div style="opacity:.55">${_escHtml(_mt('harita.adim-verisi-yok'))}</div>`;
  }
  const clearBtn = document.getElementById('map-route-clear');
  if (clearBtn && !clearBtn._wired) { clearBtn._wired = true; clearBtn.addEventListener('click', () => _mapClearRoute(true)); }
}

async function _mapTryShowRoute(text) {
  if (!_lmap || typeof L === 'undefined') return false;
  if (!_MAP_ROUTE_KEYWORDS.test(text)) return false;

  const fromIsMe = /(?<![\wçğıöşüÇĞİÖŞÜ])(benim konum|konumumdan|konumumu|konumum|buradan|bulunduğum|mevcut konum|from here|my location)(?![\wçğıöşüÇĞİÖŞÜ])/i.test(text);

  // Açık "X'den" başlangıcı (fromIsMe değilse)
  let fromName = null, restText = text;
  if (!fromIsMe) {
    const m = text.match(/(.+?)['’‘"]?(?:d[ae]n|t[ae]n)\s+(.+)/i);
    if (m) { fromName = m[1].replace(/(?<![\wçğıöşüÇĞİÖŞÜ])(benim|yol tarifi|rota)(?![\wçğıöşüÇĞİÖŞÜ])/gi, '').trim(); restText = m[2]; }
  }

  // Durakları ayır: "sonra/ardından/then/→/>" ayraçları → çoklu hedef
  const SEP = '|~|';
  const stops = restText
    .replace(/\s*(?:→|>)\s*/g, ' ' + SEP + ' ')
    .replace(/\s+(?:sonra|ardından|then)\s+/gi, ' ' + SEP + ' ')
    .split(SEP)
    .map(s => _mapCleanPlaceStr(s))
    .filter(s => s.length >= 2);
  if (!stops.length) return false;

  try {
    let from = fromName ? await _mapGeocode(fromName) : null;
    if (!from) { const me = await _mapGetMyCoords(); if (me) from = { lat: me.lat, lon: me.lon, name: me.city || _mt('harita.konumum') }; }
    if (!from) { const c = _lmap.getCenter(); from = { lat: c.lat, lon: c.lng, name: _mt('harita.harita-merkezi') }; }

    let dests = [];
    for (const s of stops) { const g = await _mapGeocode(s); if (g) dests.push(g); }

    // Ayraçsız "Şehir1 Şehir2" (ör. "Muğla Antalya") veya kalıntı/typo kelime → token-token çöz
    if (!dests.length) {
      const toks = stops.join(' ').split(/\s+/).filter(t => t.length >= 2);
      const resolved = [];
      for (const t of toks) { const g = await _mapGeocode(t); if (g) resolved.push(g); }
      if (resolved.length >= 2 && !fromName && !fromIsMe) { from = resolved[0]; dests = resolved.slice(1); }
      else if (resolved.length >= 1) { dests = resolved; }
    }
    if (!dests.length) { if (typeof appendMapMessage === 'function') appendMapMessage('system', _mt('harita.hedef-bulunamadi', { hedef: stops.join(', ') })); return false; }

    const pts = [from].concat(dests);
    const coordStr = pts.map(p => `${p.lon},${p.lat}`).join(';');

    // Token varsa Mapbox trafikli rota, yoksa OSRM
    const tok = await _mapEnsureMapbox();
    let route = null, trafficUsed = false;
    if (tok) {
      try {
        const mb = await fetch(
          `https://api.mapbox.com/directions/v5/mapbox/driving-traffic/${coordStr}?access_token=${tok}&overview=full&geometries=geojson&steps=true&language=tr`
        ).then(r => r.json());
        if (mb && mb.routes && mb.routes[0]) { route = mb.routes[0]; trafficUsed = true; }
      } catch (_) {}
    }
    if (!route) {
      const osrm = await fetch(
        `https://router.project-osrm.org/route/v1/driving/${coordStr}?overview=full&geometries=geojson&steps=true`
      ).then(r => r.json());
      if (!osrm.routes || !osrm.routes[0]) { if (typeof appendMapMessage === 'function') appendMapMessage('system', _mt('harita.rota-bulunamadi')); return false; }
      route = osrm.routes[0];
    }

    const coords = route.geometry.coordinates.map(([lo, la]) => [la, lo]);
    const km     = (route.distance / 1000).toFixed(1);
    const mins   = Math.round(route.duration / 60);

    _mapClearRoute(false);

    window._mapRouteLine = L.polyline(coords, { color: '#00d4ff', weight: 4, opacity: 0.85 }).addTo(_lmap);
    window._mapRouteMarkers.push(
      L.circleMarker([from.lat, from.lon], { radius: 7, color: '#4caf50', fillColor: '#4caf50', fillOpacity: 1, weight: 2 })
        .bindPopup(`<div style="font-family:monospace;font-size:10px;color:#4caf50;">▸ ${from.name}</div>`).addTo(_lmap)
    );
    dests.forEach((d, i) => {
      const last = i === dests.length - 1;
      const col = last ? '#ff5252' : '#ffd740';
      window._mapRouteMarkers.push(
        L.circleMarker([d.lat, d.lon], { radius: 7, color: col, fillColor: col, fillOpacity: 1, weight: 2 })
          .bindPopup(`<div style="font-family:monospace;font-size:10px;color:${col};">${last ? '◉' : '(' + (i + 1) + ')'} ${d.name}</div>`).addTo(_lmap)
      );
    });
    _lmap.fitBounds(window._mapRouteLine.getBounds(), { padding: [40, 40] });

    // Animasyonlu navigasyon işaretçisi — rota boyunca akar (realtime-tracker marker-animation paterni)
    window._mapRouteAnimMarker = L.circleMarker(coords[0], { radius: 6, color: '#ffffff', fillColor: '#00e5ff', fillOpacity: 1, weight: 2 }).addTo(_lmap);
    let _navI = 0;
    const _navStep = Math.max(1, Math.floor(coords.length / 240));   // ~4 sn'de bir tur
    const _navTick = () => {
      if (!window._mapRouteAnimMarker) return;
      _navI += _navStep;
      if (_navI >= coords.length) _navI = 0;
      window._mapRouteAnimMarker.setLatLng(coords[_navI]);
      window._mapRouteAnimRaf = requestAnimationFrame(_navTick);
    };
    window._mapRouteAnimRaf = requestAnimationFrame(_navTick);

    _mapRenderRouteHud(from, dests, km, mins, route);

    const _tb = trafficUsed ? ' · 🚦 trafik' : '';
    if (typeof appendMapMessage === 'function') appendMapMessage('system', `🧭 ${from.name} → ${dests.map(d => d.name).join(' → ')} · ${km} km · ${mins} dk${_tb}`);
    if (typeof showToast === 'function') showToast(`🧭 Rota: ${km} km · ${mins} dk${_tb}`);
    return true;
  } catch (_) { return false; }
}

// ── Canlı konum izleme (realtime-tracker breadcrumb paterni) ──────
let _mapWatchId = null, _mapTrailLine = null, _mapTrailPts = [], _mapMeMarker = null;
function _mapTryLiveTrack(text) {
  if (!_lmap || typeof L === 'undefined') return false;
  if (/(?<![\wçğıöşüÇĞİÖŞÜ])(takibi durdur|izlemeyi durdur|takibi kapat|izlemeyi kapat|stop tracking)(?![\wçğıöşüÇĞİÖŞÜ])/i.test(text)) { _mapStopLiveTrack(); return true; }
  if (!/(?<![\wçğıöşüÇĞİÖŞÜ])(konumumu izle|beni izle|takip et|canlı takip|canlı izle|track me|follow me|izlemeye başla)(?![\wçğıöşüÇĞİÖŞÜ])/i.test(text)) return false;
  if (!navigator.geolocation) { if (typeof appendMapMessage === 'function') appendMapMessage('system', _mt('harita.geolocation-yok')); return true; }
  if (_mapWatchId != null) { if (typeof appendMapMessage === 'function') appendMapMessage('system', _mt('harita.takip-zaten-acik')); return true; }
  _mapTrailPts = [];
  _mapTrailLine = L.polyline([], { color: '#00e676', weight: 3, opacity: 0.8, dashArray: '4 6' }).addTo(_lmap);
  if (typeof appendMapMessage === 'function') appendMapMessage('system', _mt('harita.takip-basladi'));
  if (typeof showToast === 'function') showToast(_mt('harita.takip-acik'));
  _mapWatchId = navigator.geolocation.watchPosition(
    (pos) => {
      const ll = [pos.coords.latitude, pos.coords.longitude];
      _mapLastCoords = { lat: ll[0], lon: ll[1], city: '' };
      _mapTrailPts.push(ll);
      if (_mapTrailLine) _mapTrailLine.setLatLngs(_mapTrailPts);
      if (!_mapMeMarker) _mapMeMarker = L.circleMarker(ll, { radius: 7, color: '#ffffff', fillColor: '#00e676', fillOpacity: 1, weight: 2 }).bindPopup(_mt('harita.konumum')).addTo(_lmap);
      else _mapMeMarker.setLatLng(ll);
      _lmap.panTo(ll, { animate: true });
    },
    () => { if (typeof appendMapMessage === 'function') appendMapMessage('system', _mt('harita.konum-alinamadi')); },
    { enableHighAccuracy: true, maximumAge: 2000, timeout: 8000 }
  );
  return true;
}
function _mapStopLiveTrack() {
  if (_mapWatchId != null && navigator.geolocation) { navigator.geolocation.clearWatch(_mapWatchId); _mapWatchId = null; }
  if (typeof appendMapMessage === 'function') appendMapMessage('system', _mt('harita.takip-durduruldu'));
  if (typeof showToast === 'function') showToast('■ Takip durdu');
}

// ── Tarama / tehdit bölgesi (POI HUD canvas-overlay esinli, self-contained) ──
async function _mapTryDrawZone(text) {
  if (!_lmap || typeof L === 'undefined') return false;
  if (!/(?<![\wçğıöşüÇĞİÖŞÜ])(bölge|tarama|tehdit|scan zone|zone|kuşatma|çember|yarıçap|radius)(?![\wçğıöşüÇĞİÖŞÜ])/i.test(text)) return false;
  if (/(?<![\wçğıöşüÇĞİÖŞÜ])(bölge(leri|ler)?\s*(temizle|kaldır|sil)|clear zones?|taramayı temizle)(?![\wçğıöşüÇĞİÖŞÜ])/i.test(text)) { _mapClearZones(); if (typeof appendMapMessage === 'function') appendMapMessage('system', _mt('harita.bolgeler-temizlendi')); return true; }
  let radiusKm = 5;
  const rm = text.match(/(\d+(?:[.,]\d+)?)\s*(km|kilometre|metre|m)(?![\wçğıöşüÇĞİÖŞÜ])/i);
  if (rm) { let v = parseFloat(rm[1].replace(',', '.')); if (/^m(etre)?$/i.test(rm[2])) v = v / 1000; if (!isNaN(v)) radiusKm = Math.max(0.2, Math.min(500, v)); }
  const place = text
    .replace(/(?<![\wçğıöşüÇĞİÖŞÜ])(bölge|tarama|tehdit|scan zone|zone|kuşatma|çember|yarıçap|radius)(?![\wçğıöşüÇĞİÖŞÜ])/gi, ' ')
    .replace(/(\d+(?:[.,]\d+)?)\s*(km|kilometre|metre|m)(?![\wçğıöşüÇĞİÖŞÜ])/gi, ' ')
    .replace(/(?<![\wçğıöşüÇĞİÖŞÜ])(çevresinde|etrafında|merkezli|içinde|çiz|oluştur|göster|bana|bir|lütfen|around|near|of)(?![\wçğıöşüÇĞİÖŞÜ])/gi, ' ')
    .replace(/['’‘](y?[ae])(?![\wçğıöşüÇĞİÖŞÜ])/gi, ' ').replace(/['’‘]?(d[ae]n|t[ae]n)(?![\wçğıöşüÇĞİÖŞÜ])/gi, ' ')
    .replace(/[^a-zA-ZığüşöçİĞÜŞÖÇ0-9\s]/g, ' ').replace(/\s+/g, ' ').trim();
  let center = (place && place.length >= 2) ? await _mapGeocode(place) : null;
  if (!center) { const me = await _mapGetMyCoords(); if (me) center = { lat: me.lat, lon: me.lon, name: _mt('harita.konumum') }; }
  if (!center) { const c = _lmap.getCenter(); center = { lat: c.lat, lon: c.lng, name: _mt('harita.harita-merkezi') }; }
  _mapDrawZone(center.lat, center.lon, radiusKm, center.name);
  _lmap.flyTo([center.lat, center.lon], radiusKm > 50 ? 6 : radiusKm > 10 ? 9 : 11, { duration: 1.0 });
  if (typeof appendMapMessage === 'function') appendMapMessage('system', _mt('harita.tarama-bolgesi', { yer: center.name, km: radiusKm }));
  return true;
}
function _mapDrawZone(lat, lon, radiusKm, name) {
  window._mapZones = window._mapZones || [];
  const maxR = radiusKm * 1000;
  const ring = L.circle([lat, lon], { radius: maxR, color: '#ff3b6b', weight: 1.5, fillColor: '#ff3b6b', fillOpacity: 0.07, dashArray: '6 8' }).addTo(_lmap);
  const core = L.circleMarker([lat, lon], { radius: 5, color: '#ff3b6b', fillColor: '#ff3b6b', fillOpacity: 0.9, weight: 1 })
    .bindPopup(`<div style="font-family:monospace;font-size:10px;color:#ff3b6b;">⊚ ${name} · ${radiusKm} km</div>`).addTo(_lmap);
  const pulse = L.circle([lat, lon], { radius: 0, color: '#ff3b6b', weight: 1.2, fill: false, opacity: 0.6 }).addTo(_lmap);
  const z = { ring, core, pulse, raf: null, pr: 0 };
  const tick = () => {
    z.pr += maxR / 90;
    let op = 0.6 * (1 - z.pr / maxR);
    if (z.pr >= maxR) { z.pr = 0; op = 0.6; }
    try { pulse.setRadius(z.pr); pulse.setStyle({ opacity: Math.max(0, op) }); } catch (_) {}
    z.raf = requestAnimationFrame(tick);
  };
  z.raf = requestAnimationFrame(tick);
  window._mapZones.push(z);
}
function _mapClearZones() {
  (window._mapZones || []).forEach(z => {
    if (z.raf) cancelAnimationFrame(z.raf);
    [z.ring, z.core, z.pulse].forEach(l => { try { _lmap.removeLayer(l); } catch (_) {} });
  });
  window._mapZones = [];
}

// ── Isochrone (erişim alanı) — sadece Mapbox token varsa ──────────
async function _mapTryIsochrone(text) {
  if (!_lmap || typeof L === 'undefined') return false;
  if (!/(?<![\wçğıöşüÇĞİÖŞÜ])(erişim alan|menzil|isochrone|dakikada nereye|kaç dakikada|kaç dk|dk içinde nereye|reachability)(?![\wçğıöşüÇĞİÖŞÜ])/i.test(text)) return false;
  const tok = await _mapEnsureMapbox();
  if (!tok) { if (typeof appendMapMessage === 'function') appendMapMessage('system', _mt('harita.izokron-token-gerek')); return true; }
  const mm = text.match(/(\d+)\s*(dk|dakika|minute|min)(?![\wçğıöşüÇĞİÖŞÜ])/i);
  const minutes = mm ? Math.max(1, Math.min(60, parseInt(mm[1], 10))) : 30;
  const place = text
    .replace(/(?<![\wçğıöşüÇĞİÖŞÜ])(erişim alan[ıi]?|menzil|isochrone|dakikada nereye|kaç dakikada|kaç dk|dk içinde nereye|reachability|nereye|gidilebilir|ulaşılabilir|içinde|göster|bana|lütfen)(?![\wçğıöşüÇĞİÖŞÜ])/gi, ' ')
    .replace(/(\d+)\s*(dk|dakika|minute|min)(?![\wçğıöşüÇĞİÖŞÜ])/gi, ' ')
    .replace(/['’‘](y?[ae])(?![\wçğıöşüÇĞİÖŞÜ])/gi, ' ').replace(/['’‘]?(d[ae]n|t[ae]n)(?![\wçğıöşüÇĞİÖŞÜ])/gi, ' ')
    .replace(/[^a-zA-ZığüşöçİĞÜŞÖÇ0-9\s]/g, ' ').replace(/\s+/g, ' ').trim();
  let center = (place && place.length >= 2) ? await _mapGeocode(place) : null;
  if (!center) { const me = await _mapGetMyCoords(); if (me) center = { lat: me.lat, lon: me.lon, name: _mt('harita.konumum') }; }
  if (!center) { const c = _lmap.getCenter(); center = { lat: c.lat, lon: c.lng, name: 'Merkez' }; }
  try {
    const iso = await fetch(
      `https://api.mapbox.com/isochrone/v1/mapbox/driving/${center.lon},${center.lat}?contours_minutes=${minutes}&polygons=true&denoise=1&access_token=${tok}`
    ).then(r => r.json());
    if (!iso || !iso.features || !iso.features[0]) { if (typeof appendMapMessage === 'function') appendMapMessage('system', _mt('harita.izokron-alinamadi')); return true; }
    if (window._mapIso) { try { _lmap.removeLayer(window._mapIso); } catch (_) {} window._mapIso = null; }
    window._mapIso = L.geoJSON(iso, { style: { color: '#00e5ff', weight: 2, fillColor: '#00e5ff', fillOpacity: 0.12 } }).addTo(_lmap);
    try { _lmap.fitBounds(window._mapIso.getBounds(), { padding: [40, 40] }); } catch (_) {}
    if (typeof appendMapMessage === 'function') appendMapMessage('system', _mt('harita.izokron-yerli', { yer: center.name, dk: minutes }));
    if (typeof showToast === 'function') showToast(_mt('harita.izokron', { dk: minutes }));
  } catch (_) { if (typeof appendMapMessage === 'function') appendMapMessage('system', _mt('harita.izokron-hatasi')); }
  return true;
}

// Komut önceliği: canlı takip → erişim alanı → bölge → rota → tekil konum
async function _mapTryRouteOrLocation(text) {
  if (_mapTryLiveTrack(text)) return true;
  if (await _mapTryIsochrone(text)) return true;
  if (await _mapTryDrawZone(text)) return true;
  const routed = await _mapTryShowRoute(text);
  if (routed) return true;
  return _mapTryShowLocation(text);
}

// 🔑 Haritadan giden HER soru (GÜNDEM, işaretçi brifingi, konum onayı, yer detayı)
// sohbetin KENDİ gönderim yolundan geçer: core.js `sendMessage` → kullanıcı balonu
// SOHBET'e yazılır, YukiState bağlamı eklenir, `{type:'text'}` /ws/realtime'a gider,
// cevap SOHBET'te akar. Kendi LLM çağrısı YOK (tek motor kuralı).
// Eskiden soket doğrudan `{type:'chat'}` ile yazılıyordu: soru sohbette görünmüyor,
// cevap "nereden çıktı" belirsiz bir balon olarak düşüyordu.
// Kullanıcının yazma alanında yarım bir taslağı varsa ezilmez: gönderimden sonra geri konur.
function _mapSendWithLocation(text) {
  let msg = text;
  if (_mapLastCoords) {
    msg = `[Konumum: ${_mapLastCoords.lat.toFixed(5)},${_mapLastCoords.lon.toFixed(5)}${_mapLastCoords.city ? ' (' + _mapLastCoords.city + ')' : ''}] ${text}`;
  }
  const mainInput = document.getElementById('msg-input');
  if (mainInput && typeof sendMessage === 'function') {
    const taslak = mainInput.value;
    mainInput.value = msg;
    Promise.resolve(sendMessage()).finally(() => {
      if (taslak && !mainInput.value) mainInput.value = taslak;
    });
  } else if (typeof socket !== 'undefined' && socket && socket.readyState === WebSocket.OPEN) {
    socket.send(JSON.stringify({ type: 'text', message: msg }));
  }
}

function mapSendMessage(prefill) {
  const text = String(prefill || '').trim();
  if (!text) return;
  if (typeof showToast === 'function') showToast(_mt('harita.soruldu'), '', 2500);

  // Rota/konumu AI'dan BAĞIMSIZ ve PARALEL haritada göster (LLM map tool patlasa da çalışır)
  _mapTryRouteOrLocation(text);

  // Konum bilgisi varsa direkt gönder, yoksa GPS dene
  if (_mapLastCoords) {
    _mapSendWithLocation(text);
    return;
  }
  if (navigator.geolocation) {
    navigator.geolocation.getCurrentPosition(
      (pos) => {
        _mapLastCoords = { lat: pos.coords.latitude, lon: pos.coords.longitude, city: '' };
        _mapSendWithLocation(text);
      },
      () => _mapSendWithLocation(text), // izin yoksa koordinatsız gönder
      { timeout: 4000, maximumAge: 60000 }
    );
  } else {
    _mapSendWithLocation(text);
  }
}

document.addEventListener('DOMContentLoaded', function() {
  // SOHBET'e yazılan kullanıcı mesajı harita açıkken de rota/konum komutu olabilir
  // ("İzmir'e yol tarifi") — haritada AI'dan bağımsız göster. (Mini sohbete
  // yansıtma 10-04'te kalktı. Görünürlük `hidden`'dan: üründe `style.display` yok.)
  const mainMessages = document.getElementById('messages');
  if (mainMessages) {
    const observer = new MutationObserver(function(mutations) {
      if (document.getElementById('tab-map')?.hidden !== false) return;
      mutations.forEach(function(m) {
        m.addedNodes.forEach(function(node) {
          if (node.nodeType !== 1) return;
          if (!node.classList.contains('user')) return; // sadece user mesajları
          const bubble = node.querySelector('.msg-bubble');
          const text   = (bubble || node).textContent.trim();
          if (text) _mapTryRouteOrLocation(text);
        });
      });
    });
    observer.observe(mainMessages, { childList: true });
  }
});

// 2026-10-04 (HARİTA ÖNCE): PORTAL kanvas animasyonu (IIFE, `MODES` + `_portalSetMode`)
// ve STATE → PORTAL eşitleyicisi (500 ms'lik setInterval) silindi. İkisi de DOM'da
// olmayan öğelere yazıyordu (#portal-canvas 07-05'te, SİSTEM kartı #map-ai-state
// 10-04'te kalktı) — setInterval her yarım saniyede boşa koşuyordu.

/* ── Dil tazeleyici (FAZ 3 · Dalga 2 · dosya kuyruğu 3/4, 2026-09-20) ───────
   🔴 ALTINCI KEZ: `dil.js::ciz()` yalnız `data-i18n` çapası taşıyan statik
   markup'ı tazeler. MAP panosunun yüzeylerinin TAMAMI JS'ten doğuyor
   (katman düğmeleri, liste, HUD kartları, akan şerit, gezegen paneli), yani
   açık ekranda dil değiştirildiğinde eski dilde DONARLAR.

   🔑 Tazelenen şey KABUK, içerik değil — ve bu dosyada fark daha keskin:
   katman verisi ağdan gelir. `_fetchLayer` çağrılsaydı çeviri, kullanıcının
   açtığı her katmanı YENİDEN İNDİRİRDİ (OpenSky'ın istek sınırı buna bir
   dakika dayanır). Yalnız ETİKETLER yeniden yazılır, veri korunur.

   ⚠️ Her çağrı kendi kapısını taşır: panel kapalıyken çizen bir fonksiyonu
   çağırmak, kullanıcının görmediği bir yüzeyi kurmak demektir. */
window.addEventListener('yuki-dil-degisti', () => {
  const dene = (ad, f) => { try { f(); } catch (e) { console.warn('[dil] harita tazeleme düştü:', ad, e); } };

  // ① Katman satırlarının adı artık `data-i18n="harita.katman.<k>"` — dil.js çizer.
  //    (Eskiden düğmenin textContent'i buradan yazılıyordu; satır = ad + sayı +
  //    açıklama + anahtar olunca o yazım satırı silerdi.)

  // ② Aktif katman listesi + POI listesi — yalnız panel AÇIKKEN.
  dene('katman-listesi', () => {
    const panel = document.getElementById('map-layer-mgr');
    if (panel && panel.classList.contains('open')) {
      renderLayerList();
      renderPoiList();
      refreshKpGauge();
    }
  });

  // ③ (Akan şerit 10-04'te kalktı.) GÜNDEM'in boş/hata satırı JS'ten doğuyor;
  //    haber başlıkları veridir, çevrilmez — yalnız sayaç metni yeniden çizilmez.

  // ④ Gezegen paneli — yalnız AÇIKSA ve seçili bir cisim varsa.
  //    `_gok()` metni okuma anında çözdüğü için tek iş yeniden çizmek.
  dene('gezegen-paneli', () => {
    const hud = document.getElementById('planet-hud');
    if (hud && hud.style.display !== 'none' && _planetActive) {
      _planetHudMetni(_planetActive);   // canvas'a ve RAF'a DOKUNMAZ
    }
  });

  // ⑤ Hava kartı — metin `wmoCode()`'tan gelir, ham kod DOM'da yok.
  //    Bu yüzden son kodu saklıyoruz; saklamasaydık tazeleme için yeni bir
  //    ağ isteği gerekirdi (③'ün aynı kararı).
  dene('hava-karti', () => {
    const el = document.getElementById('map-weather-desc');
    if (el && _sonWmoKodu != null) el.textContent = wmoCode(_sonWmoKodu);
  });

  // ⑥ 3D sayaçları — önbellekten yeniden yazılır, ağ isteği yok.
  dene('3d-sayaclar', _update3DHUD);

  // ⑥ Yer şeridinin GÖK bölümü (Kp seviyesi · ay evresi · güneş) — metin
  //    çizim anında `_mt`'den çözülüyor; tazelenmezse dil değişince şerit
  //    yarım çevrilmiş kalıyordu (ölçüldü 10-04: "Kp 5.0 orta · son dördün"
  //    İngilizce arayüzde). Katman DEĞİL, beş küçük istek — dil değişimi seyrek.
  dene('serit-gok', () => { if (_mapUserLat !== null) updateSpaceCard(_mapUserLat, _mapUserLon); });

  // 🔴 BİLEREK TAZELENMEYENLER — çeviri VERİYİ SİLMEMELİ:
  //    · harita üzerindeki marker/popup'lar (yeniden indirme gerektirir)
  //    · rota kartı (kullanıcının hesaplattığı sonuç)
  //    · canlı takip izi · zaman çizelgesi seçimi · haber listesi
  //    Bunlar bir sonraki doğal çizimlerinde yeni dile geçer.
});
