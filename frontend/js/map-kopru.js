// ══════════════════════════════════════════════════════════════════════════
//  YUKI ↔ HARİTA KÖPRÜSÜ
//
//  Yuki'nin `map_goto` / `map_layer` / `map_status` araçları buraya düşer.
//  Backend WS ile `{type:'harita_komut', istek_id, eylem, ...}` yollar; burası
//  uygular ve `{type:'harita_sonuc', istek_id, veri}` ile CEVAP VERİR.
//
//  🔴 Cevap vermek zorunludur. Ateşle-unut olsaydı Yuki "Ankara'yı gösterdim"
//  derken harita hiç kıpırdamamış olabilirdi (canlı ölçümle yakalanan
//  sınıf: model işi yapmadan "yaptım" diyordu). Başarısızlık da bir cevaptır.
//
//  🔑 Geocoding BURADA — `map-engine.js` zaten Nominatim kullanıyor. Backend'e
//  ikinci bir çözücü koymak ikinci bir bayatlama kaynağı olurdu.
// ══════════════════════════════════════════════════════════════════════════
(function () {
  'use strict';

  // Zoom seçimi: kullanıcı vermediyse yerin türüne göre. Nominatim `type`
  // alanını döner; şehir ile bina aynı zoom'da gösterilirse biri anlamsız olur.
  const ZOOM_VARSAYILAN = {
    country: 5, state: 7, city: 11, town: 12, village: 13,
    suburb: 14, neighbourhood: 15, road: 16, building: 17, house: 17,
  };

  function _harita() {
    // `_lmap` map-engine.js'in Leaflet örneği. MAP sekmesi hiç açılmadıysa
    // tanımsızdır — "yok" ile "boş" ayrımı burada yapılır.
    return (typeof _lmap !== 'undefined' && _lmap) ? _lmap : null;
  }

  async function _coz(yer) {
    const url = 'https://nominatim.openstreetmap.org/search?q='
      + encodeURIComponent(yer) + '&format=json&limit=1';
    const r = await fetch(url, { headers: { 'Accept-Language': 'tr' } });
    if (!r.ok) throw new Error('Yer araması başarısız (' + r.status + ').');
    const d = await r.json();
    if (!d || !d.length) throw new Error('"' + yer + '" bulunamadı.');
    return {
      lat: parseFloat(d[0].lat),
      lon: parseFloat(d[0].lon),
      ad: d[0].display_name || yer,
      zoom: ZOOM_VARSAYILAN[d[0].type] || ZOOM_VARSAYILAN[d[0].addresstype] || 12,
    };
  }

  async function _git(k) {
    const m = _harita();
    if (!m) return { ok: false, hata: 'MAP sekmesi henüz açılmadı.' };

    let lat = k.lat, lon = k.lon, ad = null, zoom = k.zoom;
    if (lat === null || lat === undefined || lon === null || lon === undefined) {
      const c = await _coz(k.yer);
      lat = c.lat; lon = c.lon; ad = c.ad;
      if (!zoom) zoom = c.zoom;
    }
    if (!zoom) zoom = 11;

    // 🔴 Sekmeyi de aç: harita arka plandayken "götürdüm" demek, kullanıcının
    // göremediği bir şeyi olmuş saymaktır. switchTab yoksa yine de uçarız —
    // komutun asıl işi budur, sekme açmak yardımcı bir nezakettir.
    try {
      if (typeof window.switchTab === 'function') window.switchTab('map');
    } catch (_) {}

    m.flyTo([lat, lon], zoom, { animate: true, duration: 1.2 });
    return { ok: true, lat: Math.round(lat * 10000) / 10000,
             lon: Math.round(lon * 10000) / 10000, zoom: zoom, ad: ad };
  }

  function _katman(k) {
    const m = _harita();
    if (!m) return { ok: false, hata: 'MAP sekmesi henüz açılmadı.' };
    if (typeof toggleLayer !== 'function') {
      return { ok: false, hata: 'Katman denetimi yüklenmedi.' };
    }
    // `toggleLayer` bir ANAHTAR değil bir ÇEVİRİCİDİR: istenen durum zaten
    // geçerliyse çağırmak onu tersine çevirirdi ("aç" dedik, kapandı).
    const suAn = !!(typeof _layerActive !== 'undefined' && _layerActive
                    && _layerActive[k.katman]);
    if (suAn !== !!k.ac) toggleLayer(k.katman);
    return { ok: true, acik: !!k.ac, katman: k.katman };
  }

  function _durum() {
    const m = _harita();
    if (!m) return { ok: false, hata: 'MAP sekmesi henüz açılmadı.' };
    const c = m.getCenter();
    const acik = [];
    if (typeof _layerActive !== 'undefined' && _layerActive) {
      Object.keys(_layerActive).forEach(function (k) {
        if (_layerActive[k]) acik.push(k);
      });
    }
    return { ok: true, lat: Math.round(c.lat * 10000) / 10000,
             lon: Math.round(c.lng * 10000) / 10000,
             zoom: m.getZoom(), acik_katmanlar: acik };
  }

  /** Komutu uygular. Her yoldan bir SONUÇ döner — istisna dışarı sızmaz. */
  async function uygula(k) {
    try {
      if (k.eylem === 'git')    return await _git(k);
      if (k.eylem === 'katman') return _katman(k);
      if (k.eylem === 'durum')  return _durum();
      return { ok: false, hata: 'Bilinmeyen harita eylemi: ' + k.eylem };
    } catch (e) {
      return { ok: false, hata: (e && e.message) || String(e) };
    }
  }

  /** WS'ten gelen komutu işleyip cevabı geri yollar. core.js buradan çağırır. */
  async function komutIsle(d, gonder) {
    const veri = await uygula(d);
    try {
      gonder({ type: 'harita_sonuc', istek_id: d.istek_id, veri: veri });
    } catch (_) {
      // Cevap yollanamadıysa backend zaman aşımına düşer ve kullanıcıya
      // "harita cevap vermedi" der — sessiz başarı iddiasından iyidir.
    }
  }

  window.YukiHarita = { uygula: uygula, komutIsle: komutIsle, _coz: _coz };
})();
