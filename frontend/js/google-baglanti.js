/* ⚙ AYAR → GOOGLE — BAĞLANTI KARTI ( panel 11, 2026-09-28 — geliştirici taslak A'yı seçti).
 *
 * 🔑 Karar (2026-09-14): OAuth kimliği MÜŞTERİNİNDİR. Ürünle birlikte bizim
 *    client_id/secret'ımız dağıtılmaz; müşteri kendi Google Cloud projesini açar.
 *
 * Taslak A (2026-09-26 HQ taslakları). ANAHTAR kartının dili:
 *   · kurulmamışken ÜÇ ADIM (① Cloud'da kimlik ② iki değeri yapıştır ③ Google ile bağla)
 *   · kuruluyken DURUM SATIRLARI (Takvim · Drive · Kimlik · Bağlantı) + güven notu
 *   · kopukken kırmızı hüküm + "Neden olabilir" kutusu, çözümü SEBEBE göre
 *
 * 🔴 Yalan yeşil kapandı: "Bağlı" yalnız GERÇEKTEN denenmiş bağlantıya denir. Işık backend'in
 *    `durum` alanından (yok · hazir · denenmedi · bagli · kopuk); token dosyasının varlığı
 *    (`connected`) bağlantının sağlığı DEĞİLDİR. Son deneme 10 dakikadan eskiyse panel açılışta
 *    kendiliğinden bir kez dener (`POST /google/dene` — Google'a tek küçük istek).
 *
 * 🔴 Panel kendi markup'ını ÇİZER (`duvar.js::panelCiz` deseni). HTML'e ikinci
 *    kez yazmak "aynı soruya iki cevap" olurdu (`surum.js` dersi).
 */
(function () {
  'use strict';

  var UC = '/api/planner/google';
  var BAYAT_MS = 10 * 60 * 1000;   // son deneme bundan eskiyse açılışta bir kez denenir

  var _durum = null;         // /status cevabı ya da {kilitli} · {cok_istek} · null
  var _yedek = null;         // /api/yedekleme/durum → son_tur (yalnız GERÇEK veri varsa satıra yazılır)
  var _cizildi = false;      // panel en az bir kez çizildi mi (dil tazeleyici için)
  var _sonMesaj = null;      // {anahtar, degerler, hata} — çizimler arasında KALIR (Kaydet mesajı kaybolmasın)
  var _formHata = null;      // kimlik formunun KENDİ hatası (Kaydet 400) — hatalı alanın yanında, üstte değil
  var _duzenle = false;      // kimlik düzenleniyor mu (Değiştir → Vazgeç)
  var _kesOnay = false, _kesSayac = null;
  var _deneniyor = false;
  var _otoDenendi = false;   // bu açılışta kendiliğinden deneme yapıldı mı (döngü olmasın)
  var _mesgul = {};          // eylem → true (düğme pasif + aria-busy)
  var _tek = {};             // eylem → sürmekte olan söz (çift tık = 1 istek)

  function _gbt(anahtar, degerler) {
    return (window.YukiDil && window.YukiDil.t) ? window.YukiDil.t(anahtar, degerler) : String(anahtar);
  }

  function _el() { return document.getElementById('hq-panel-google'); }

  function _esc(s) {
    return String(s == null ? '' : s).replace(/[&<>"']/g, function (c) {
      return { '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c];
    });
  }
  /* Sözlük metni: önce kaçırılır, sonra **kalın** ve `kod` (SAĞLIK `_anVurgu` ile aynı kural) */
  function _vurgu(s) {
    return _esc(s || '').replace(/\*\*(.+?)\*\*/g, '<b>$1</b>').replace(/`([^`]+)`/g, '<code>$1</code>');
  }
  function _t(anahtar, degerler) { return _vurgu(_gbt(anahtar, degerler)); }

  /* Yetkili fetch — token'ı core.js `authFetch` ekler.
     🔴 2026-09-28: bu dosya `window._yetkiFetch`'i arıyordu; o ad tab-nav.js'in İÇİNDE kalıyor,
        window'a hiç verilmiyor → panel her istekte çıplak `fetch`'e düşüyordu. Uygulama kilidi
        kuruluyken her şey 401 → "oturum kilitli". */
  function _fetch(yol, secenek) {
    if (typeof window.authFetch === 'function') return window.authFetch(yol, secenek || {});
    if (window._yetkiFetch) return window._yetkiFetch(yol, secenek);
    return fetch(yol, secenek);
  }

  /* Tek uçuş: aynı eylem sürerken ikinci çağrı yeni istek atmaz, ilkini bekler. */
  function _tekUcus(ad, fn) {
    if (_tek[ad]) return _tek[ad];
    _mesgul[ad] = true;
    _tek[ad] = Promise.resolve().then(fn).finally(function () {
      _tek[ad] = null; _mesgul[ad] = false;
      /* Düğme `disabled` çizimle gelir → iş bitince yeniden çiz, yoksa pasif kalır (tur 1'de ölçüldü) */
      if (_cizildi) ciz();
    });
    return _tek[ad];
  }

  async function durumAl() {
    try {
      var r = await _fetch(UC + '/status');
      /* 401 = oturum kilitli/düşmüş — "durum okunamadı" demek sebebi saklıyordu (09-27) */
      if (r.status === 401) return { kilitli: true };
      if (r.status === 429) return { cok_istek: true };
      /* Yuki'ye ulaşıldı ama cevap bozuk (5xx) — bu, ulaşılamadı DEĞİL */
      if (!r.ok) return { hata: true };
      return await r.json();
    } catch (e) { return null; }
  }

  /* Drive satırının "son yedek"i YALNIZ gerçek veriden: yedekleme ucu yoksa/kapalıysa satır yazılmaz. */
  async function yedekAl() {
    try {
      var r = await _fetch('/api/yedekleme/durum');
      if (!r.ok) return null;
      var d = await r.json();
      return (d && d.son_tur) ? d.son_tur : null;
    } catch (e) { return null; }
  }

  // ── Zaman: "az önce" · "12 dk önce" · "bugün 14:02" · "dün 22:40" · "26 Eylül 22:40" ──
  function _yerel() { return (window.YukiDil && window.YukiDil.yerel) ? window.YukiDil.yerel() : 'tr-TR'; }
  function _zaman(iso) {
    var z = new Date(iso);
    if (!iso || isNaN(z)) return '';
    var fark = Date.now() - z.getTime();
    if (fark >= 0 && fark < 60 * 1000) return _gbt('google.zaman-az-once');
    if (fark >= 0 && fark < 60 * 60 * 1000) return _gbt('google.zaman-dk-once', { n: Math.floor(fark / 60000) });
    var saat = z.toLocaleTimeString(_yerel(), { hour: '2-digit', minute: '2-digit' });
    var bugun = new Date(); bugun.setHours(0, 0, 0, 0);
    var gun = new Date(z); gun.setHours(0, 0, 0, 0);
    var gunFark = Math.round((bugun - gun) / 86400000);
    if (gunFark === 0) return _gbt('saglik.zaman-bugun', { saat: saat });
    if (gunFark === 1) return _gbt('saglik.zaman-dun', { saat: saat });
    return z.toLocaleDateString(_yerel(), { day: 'numeric', month: 'long' }) + ' ' + saat;
  }
  function _bayat(son) {
    if (!son || !son.zaman) return true;
    var z = Date.parse(son.zaman);
    return isNaN(z) || (Date.now() - z) > BAYAT_MS;
  }

  // ── Parçalar ────────────────────────────────────────────────────────────────
  function _isik(d) { return '<span class="gg-isik durum-isik ' + d + '" aria-hidden="true"></span>'; }
  function _etiket(tur, anahtar) { return '<span class="gg-etiket ' + tur + '">' + _t(anahtar) + '</span>'; }
  function _dugme(eylem, sinif, anahtar, pasif) {
    var m = !!_mesgul[eylem];
    return '<button type="button" class="dg ' + sinif + '" data-g="' + eylem + '"'
      + ((pasif || m) ? ' disabled' : '') + (m ? ' aria-busy="true"' : '') + '>' + _t(anahtar) + '</button>';
  }
  function _mesajKutusu() {
    var m = _sonMesaj, metin = m ? _gbt(m.anahtar, m.degerler) : '';
    return '<p id="g-mesaj" class="ak-mesaj gg-mesaj" role="status"' + (m && m.hata ? ' data-hata="1"' : '') + '>'
      + _vurgu(metin) + '</p>';
  }
  function _bas(isik, baslikAnahtar, alt) {
    return '<div class="gg-bas"><h4>' + _isik(isik) + _t(baslikAnahtar) + '</h4>'
      + (alt ? '<p class="gg-alt">' + alt + '</p>' : '') + '</div>' + _mesajKutusu();
  }
  function _guven() { return '<p class="gg-guven">' + _t('google.guven') + '</p>'; }

  /* ② kimlik formu — kurulumda adımın içinde, bağlıyken Kimlik satırının içinde açılır */
  function _kimlikFormu() {
    /* Aynı tür uyarı TEK yerde, TEK renkte: formun içinde altın kutu (tur 5 #3). Kaydet'in 400'ü
       backend'in müşteri-dilindeki cümlesidir; yoksa kayıtlı değerin biçimsizliği söylenir. */
    var bicimsiz = _formHata
      ? '<p class="ak-uyari" role="alert">' + _vurgu(_formHata) + '</p>'
      : (_durum.kimlik_bicimsiz && !_durum.kimlik_var)
        ? '<p class="ak-uyari">' + _t('google.kimlik-bicimsiz-yeni') + '</p>' : '';
    var gecersiz = _formHata ? ' aria-invalid="true"' : '';
    var degisim = _duzenle && _durum.connected
      ? '<p class="gg-kucuk">' + _t('google.degistir-uyari') + '</p>' : '';
    return '<div class="ak-form gg-form">' + bicimsiz + degisim
      + '<div class="gg-iki-alan">'
      + '<div class="alan"><label for="g-cid">' + _t('google.kimlik-etiket-tam') + '</label>'
      + '<input class="girdi gg-mono" id="g-cid" type="text" autocomplete="off" spellcheck="false"' + gecersiz
      + ' placeholder="….apps.googleusercontent.com"></div>'
      + '<div class="alan"><label for="g-sec">' + _t('google.gizli-etiket-tam') + '</label>'
      + '<input class="girdi gg-mono" id="g-sec" type="password" autocomplete="off" spellcheck="false"' + gecersiz
      + ' placeholder="GOCSPX-…"></div></div>'
      + '<div class="ak-dugmeler gg-eylem">' + _dugme('kaydet', 'dg-birincil', 'hq.bildirim.kaydet')
      + (_duzenle ? _dugme('vazgec', 'dg-ikincil', 'google.vazgec') : '')
      + '<span class="gg-kucuk">' + _t('google.saklanir') + '</span></div></div>';
  }

  // ── Kurulum: üç adım (yok · hazir · hazir+düzenle) ───────────────────────────
  function _kurulumCiz() {
    var hazir = _durum.durum === 'hazir';
    var form = !hazir || _duzenle;
    var h = _bas('kurulum', hazir && !_duzenle ? 'google.baslik-son-adim' : 'google.baslik-kurulum');
    h += '<ol class="gg-adimlar">';

    h += '<li class="gg-adim' + (hazir ? ' bitti' : ' simdi') + '"><span class="gg-no" aria-hidden="true">' + (hazir ? '✓' : '1') + '</span><div>'
      + '<h5>' + _t('google.adim1-baslik') + '</h5>';
    if (hazir) h += '<p class="gg-kucuk">' + _t('google.adim-yapildi') + '</p>';
    else {
      h += '<p class="gg-kucuk">' + _t('google.adim1-alt') + '</p><ol class="gg-alt-adim">'
        + ['a', 'b', 'c', 'd'].map(function (x) { return '<li>' + _t('google.adim1-' + x) + '</li>'; }).join('')
        + '</ol><div class="ak-dugmeler gg-eylem">' + _dugme('rehber', 'dg-ikincil', 'google.rehber-resimli')
        + _dugme('cloud', 'dg-ikincil', 'google.cloud-ac') + '</div>';
    }
    h += '</div></li>';

    h += '<li class="gg-adim ' + (hazir ? (form ? 'simdi' : 'bitti') : '') + '"><span class="gg-no" aria-hidden="true">' + (form || !hazir ? '2' : '✓') + '</span><div>'
      + '<h5>' + _t('google.adim2-baslik') + '</h5>';
    if (form) h += _kimlikFormu();
    else h += '<p class="gg-kucuk">' + _t('google.kimlik-kayitli-satir') + ' <code>' + _esc(_durum.client_id) + '</code> '
      + '<span class="gg-bitisik">· <button type="button" class="gg-bag" data-g="degistir">' + _t('google.degistir-kucuk') + '</button></span></p>';
    h += '</div></li>';

    var bagla = hazir && !_duzenle;
    h += '<li class="gg-adim' + (bagla ? ' simdi' : '') + '"><span class="gg-no" aria-hidden="true">3</span><div>'
      + '<h5>' + _t('google.adim3-baslik') + '</h5><p class="gg-kucuk">' + _t('google.adim3-alt') + '</p>'
      + '<div class="ak-dugmeler gg-eylem">' + _dugme('bagla', bagla ? 'dg-birincil' : 'dg-ikincil', 'google.ile-bagla', !bagla)
      + (bagla ? '' : '<span class="gg-kucuk">' + _t('google.adim3-once') + '</span>') + '</div></div></li>';

    return h + '</ol>' + _guven();
  }

  // ── Kurulu: durum satırları (denenmedi · bagli · kopuk) ─────────────────────
  var _KOPUK = {
    invalid_grant:        { bas: 'google.baslik-kopuk',          kisa: 'google.neden-kisa-grant',    neden: 'google.neden-grant',          cozum: 'yeniden' },
    invalid_client:       { bas: 'google.baslik-kopuk-client',         kisa: 'google.neden-kisa-client',   neden: 'google.neden-client',         cozum: 'degistir' },
    unauthorized_client:  { bas: 'google.baslik-kopuk',          kisa: 'google.neden-kisa-yetkisiz', neden: 'google.neden-yetkisiz',       cozum: 'yeniden' },
    'kimlik-degisti':     { bas: 'google.baslik-kopuk-kimlik',   alt: 'google.kimlik-degisti-alt',  neden: 'google.neden-kimlik-degisti', cozum: 'yeniden' },
    'kimlik-gecersiz':    { bas: 'google.baslik-kopuk-gecersiz', alt: 'google.kimlik-gecersiz-alt', neden: 'google.neden-gecersiz',       cozum: 'degistir' }
  };

  function _eksik() {
    var e = _durum.eksik_izin || [];
    return {
      takvim: e.some(function (s) { return /calendar/.test(s); }),
      drive: e.some(function (s) { return /drive/.test(s); })
    };
  }

  function _kuruluCiz() {
    var d = _durum.durum, son = _durum.son_deneme, eksik = _eksik();
    var yedekHata = d === 'bagli' && !!(_yedek && _yedek.hata);
    var kopuk = d === 'kopuk', bilgi = kopuk ? (_KOPUK[_durum.sebep] || _KOPUK.invalid_grant) : null;
    var h;
    if (kopuk) {
      var alt = bilgi.alt ? _t(bilgi.alt)
        : (son && son.zaman ? _t('google.son-kopuk', { zaman: _zaman(son.zaman), neden: _gbt(bilgi.kisa) }) : '');
      h = _bas('kritik', bilgi.bas, alt);
      h += '<div class="gg-neden"><p><b>' + _t('google.neden-olabilir') + '</b> ' + _t(bilgi.neden) + '</p>'
        + (bilgi.cozum === 'degistir' ? _dugme('degistir', 'dg-birincil', 'google.kimligi-degistir')
          : _dugme('bagla', 'dg-birincil', 'google.yeniden-bagla')) + '</div>';
    } else if (d === 'bagli') {
      var eksikVar = eksik.takvim || eksik.drive;
      /* Uyarı başlığının altında "başarılı" yazmaz (tur 5 #6): eksik izinde yalnız deneme zamanı */
      var uyariVar = eksikVar || yedekHata;
      h = _bas(uyariVar ? 'uyari' : 'iyi', eksikVar ? 'google.baslik-bagli-eksik' : yedekHata ? 'google.baslik-bagli-yedek' : 'google.baslik-bagli',
        _deneniyor ? _t('google.deneniyor')
          : _t(uyariVar ? 'google.son-deneme-zaman' : 'google.son-basarili', { zaman: _zaman(son && son.zaman) }));
      if (eksikVar) {
        h += '<div class="gg-neden uyari"><p>' + _t(eksik.takvim && eksik.drive ? 'google.eksik-ikisi'
          : eksik.takvim ? 'google.eksik-takvim' : 'google.eksik-drive') + '</p>'
          + _dugme('bagla', 'dg-birincil', 'google.yeniden-bagla') + '</div>';
      }
    } else {
      /* Başlık ile alt satır aynı şeyi söyler (tur 5 #4 #5): sürerken "soruluyor", ulaşılamadıysa
         "sorulmadı" DENMEZ (altındaki mesaj sebebi söylüyor), hiç sorulmadıysa "henüz sorulmadı". */
      h = _bas('olculemedi', _deneniyor ? 'google.baslik-deneniyor' : 'google.baslik-denenmedi',
        _deneniyor ? _t('google.deneniyor') : (_durum.gecici ? '' : _t('google.denenmedi-alt')));
    }

    function izin(eksikMi, ne) {
      if (kopuk) return _etiket('kritik', 'google.etiket-calismiyor');
      if (d !== 'bagli') return _etiket('sessiz', 'google.etiket-denenmedi') + ' <span class="gg-kucuk">' + ne + '</span>';
      if (eksikMi) return _etiket('uyari', 'google.etiket-izin-yok') + ' <span class="gg-kucuk">' + _t('google.izin-onayda-yok') + '</span>';
      return _etiket('iyi', 'google.etiket-izin-var') + ' <span class="gg-kucuk">' + ne + '</span>';
    }
    /* Drive: izin var ama SON YEDEK hata verdi → gri meta yazısı hatayı gizlerdi (tur 5 #2) */
    function driveHucre() {
      if (yedekHata && !kopuk && !eksik.drive) return _etiket('uyari', 'google.etiket-yedek-hata') + ' <span class="gg-kucuk gg-hata">' + driveNe + '</span>';
      return izin(eksik.drive, driveNe);
    }
    var driveNe = _t('google.drive-ne');
    if (d === 'bagli' && _yedek) {
      /* Yalnız gerçek tur: bitmiş ve hatasız → "son yedek"; hatalı → bunu söyler; yoksa yalnız "yedekleme" */
      if (_yedek.hata) driveNe = _t('google.drive-son-hata');
      else if (_yedek.bitti) driveNe = _t('google.drive-son-yedek', { zaman: _zaman(_yedek.bitti) });
    }

    h += '<dl class="gg-satirlar">'
      + '<div class="gg-satir"><dt>' + _t('google.satir-takvim') + '</dt><dd>' + izin(eksik.takvim, _t('google.takvim-ne')) + '</dd><dd class="gg-eylem-hucre"></dd></div>'
      + '<div class="gg-satir"><dt>' + _t('google.satir-drive') + '</dt><dd>' + driveHucre() + '</dd><dd class="gg-eylem-hucre"></dd></div>';
    if (_duzenle) {
      h += '<div class="gg-satir acik"><dt>' + _t('google.satir-kimlik') + '</dt><dd>' + _kimlikFormu() + '</dd></div>';
    } else {
      h += '<div class="gg-satir"><dt>' + _t('google.satir-kimlik') + '</dt><dd><code>' + _esc(_durum.client_id) + '</code></dd>'
        + '<dd class="gg-eylem-hucre">' + (kopuk && bilgi.cozum === 'degistir' ? '' : _dugme('degistir', 'dg-ikincil', 'google.degistir')) + '</dd></div>';
    }
    h += '<div class="gg-satir"><dt>' + _t('google.satir-baglanti') + '</dt><dd>' + _t(kopuk ? 'google.baglanti-kopuk' : 'google.baglanti-sakli') + '</dd>'
      + '<dd class="gg-eylem-hucre">' + (kopuk ? '' : _dugme('dene', 'dg-ikincil', 'google.simdi-dene'))
      + '<button type="button" class="dg dg-ikincil" data-g="kes"' + (_mesgul.kes ? ' disabled aria-busy="true"' : '')
      + (_kesOnay ? ' data-onay="1"' : '') + '>' + _t(_kesOnay ? 'google.emin-misin' : 'google.baglantiyi-kes') + '</button></dd></div>'
      + '</dl>';
    return h + _guven();
  }

  /* Durum okunamadı: başlık kısa, SEBEP altında (oturum · çok sık · ulaşılamadı · hata) */
  function _bosCiz(sebepAnahtari) {
    /* Son hâl: kesik halka (olculemedi) 'soruluyor'a ayrılır; okunamadı = bitmiş, dikkat ister → uyarı ışığı */
    return _bas('uyari', 'google.baslik-okunamadi', _t(sebepAnahtari))
      + '<div class="ak-dugmeler gg-eylem">' + _dugme('tazele', 'dg-ikincil', 'google.yeniden-dene') + '</div>';
  }

  function _oda(kart) {
    return '<div class="oda gg-oda"><h2 class="gorsel-gizli">' + _t('hq.menu.google') + '</h2>'
      + '<div class="oda-bas"><div class="oda-bas-metin"><h3 class="oda-baslik">' + _t('hq.menu.google') + '</h3>'
      + '<p class="oda-amac">' + _t('google.amac') + '</p></div></div>'
      + '<div class="oda-govde"><section class="gg-kart" aria-live="polite">' + kart + '</section></div></div>';
  }

  function ciz() {
    var k = _el();
    if (!k) return;
    _cizildi = true;
    /* Formdaki yazı yeniden çizimde kaybolmasın (dil değişimi, deneme sonucu) */
    var cid = document.getElementById('g-cid'), sec = document.getElementById('g-sec');
    var cidDeger = cid ? cid.value : null, secDeger = sec ? sec.value : null;

    var kart;
    if (!_durum) kart = _bosCiz('google.yukiye-ulasilamadi');
    else if (_durum.hata) kart = _bosCiz('google.durum-hata');
    else if (_durum.kilitli) kart = _bosCiz('hq.oturum-kilitli');
    else if (_durum.cok_istek) kart = _bosCiz('google.cok-sik');
    else if (_durum.durum === 'yok' || _durum.durum === 'hazir') kart = _kurulumCiz();
    else kart = _kuruluCiz();
    k.innerHTML = _oda(kart);

    if (cidDeger != null && document.getElementById('g-cid')) document.getElementById('g-cid').value = cidDeger;
    if (secDeger != null && document.getElementById('g-sec')) document.getElementById('g-sec').value = secDeger;
  }

  function _mesaj(anahtar, hata, degerler) {
    _sonMesaj = anahtar ? { anahtar: anahtar, degerler: degerler, hata: !!hata } : null;
    var m = document.getElementById('g-mesaj');
    if (!m) return;
    m.innerHTML = anahtar ? _vurgu(_gbt(anahtar, degerler)) : '';
    // Renk sınıfla verilir: satır içi stil tema değişince yerinde kalır.
    if (hata) m.dataset.hata = '1'; else delete m.dataset.hata;
  }

  /* Ortak ret okuma: 401 = bizim oturum kilidi · 429 = çok sık · ağ = Yuki'ye ulaşılamadı.
     Ham `detail` ya da `String(e)` EKRANA ÇIKMAZ (401'in detail'i "Unauthorized"dı). */
  function _retAnahtari(r, yedek) {
    if (!r) return 'google.yukiye-ulasilamadi';
    if (r.status === 401) return 'google.oturum-kilitli-eylem';
    if (r.status === 429) return 'google.cok-sik';
    return yedek;
  }

  // ── Eylemler ────────────────────────────────────────────────────────────────
  function kaydet() {
    return _tekUcus('kaydet', async function () {
      var cid = ((document.getElementById('g-cid') || {}).value || '').trim();
      var sec = ((document.getElementById('g-sec') || {}).value || '').trim();
      var baglantiVardi = !!(_durum && _durum.connected);
      _formHata = null;
      _mesaj('google.kaydediliyor');
      ciz();
      var r = null, d = {};
      try {
        r = await _fetch(UC + '/kimlik', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ client_id: cid, client_secret: sec })
        });
        d = await r.json().catch(function () { return {}; });
      } catch (e) { r = null; }
      if (!r || !r.ok) {
        /* 400 = biçim/boş alan: backend'in cümlesi müşteri dilindedir (katalog), aynen gösterilir */
        if (r && r.status === 400 && typeof d.detail === 'string') { _formHata = d.detail; _sonMesaj = null; }
        else _sonMesaj = { anahtar: _retAnahtari(r, 'google.kaydedilemedi'), hata: true };
        ciz();
        return;
      }
      _formHata = null;
      _duzenle = false;
      var yeni = await durumAl();
      if (yeni) _durum = yeni;
      if (baglantiVardi && d.ayni_kimlik) {
        /* Aynı kimliğin gizli anahtarı düzeltildi → bağlantı yeniden sınanır (invalid_client'tan dönüş yolu) */
        _mesaj('google.kaydedildi');
        ciz();
        await dene(false);
        return;
      }
      _sonMesaj = { anahtar: _durum && _durum.sebep === 'kimlik-degisti' ? 'google.kaydedildi-yeniden'
        : (_durum && _durum.durum === 'hazir' ? 'google.kaydedildi-bagla' : 'google.kaydedildi') };
      ciz();
    });
  }

  function bagla() {
    return _tekUcus('bagla', async function () {
      ciz();
      var r = null, d = {};
      try {
        r = await _fetch(UC + '/auth-url');
        d = await r.json().catch(function () { return {}; });
      } catch (e) { r = null; }
      if (!r || !r.ok || !d.url) {
        if (r && (r.status === 503 || r.status === 400) && typeof d.detail === 'string') _sonMesaj = { anahtar: 'google.ham', degerler: { metin: d.detail }, hata: true };
        else _sonMesaj = { anahtar: _retAnahtari(r, 'google.baglanti-baslatilamadi'), hata: true };
        ciz();
        return;
      }
      /* Dış bağlantı: Electron `dis-baglanti.js` bunu SİSTEM TARAYICISINA devreder. */
      window.open(d.url, '_blank');
      _sonMesaj = { anahtar: 'google.onay-acildi' };
      ciz();
      _gorunurlugeBagla();
    });
  }

  function dene(elle) {
    return _tekUcus('dene', async function () {
      _deneniyor = true;
      if (elle) _sonMesaj = null;
      ciz();
      var r = null, d = null;
      try {
        r = await _fetch(UC + '/dene', { method: 'POST' });
        if (r.ok) d = await r.json().catch(function () { return null; });
      } catch (e) { r = null; }
      _deneniyor = false;
      if (!d) {
        _sonMesaj = { anahtar: _retAnahtari(r, 'google.dene-olmadi'), hata: true };
      } else {
        _durum = d;
        if (d.gecici) _sonMesaj = { anahtar: 'google.dene-ulasilamadi' };
        else if (elle && d.durum === 'bagli') _sonMesaj = { anahtar: 'google.dene-basarili' };
      }
      ciz();
    });
  }

  function kes() {
    /* ⚠️ `confirm()` KULLANILMAZ — native diyalog Electron penceresini kilitler ve
       otomatik ölçümü asar. İki adımlı tık: ilk tık düğmeyi "Emin misin?"e çevirir. */
    var b = _el() && _el().querySelector('[data-g="kes"]');
    if (!b || b.dataset.onay !== '1') {
      _kesOnay = true;
      ciz();
      clearTimeout(_kesSayac);
      _kesSayac = setTimeout(function () { if (_kesOnay) { _kesOnay = false; ciz(); } }, 4000);
      return Promise.resolve();
    }
    return _tekUcus('kes', async function () {
      clearTimeout(_kesSayac);
      ciz();
      var r = null, d = {};
      try {
        r = await _fetch(UC + '/disconnect', { method: 'POST' });
        d = await r.json().catch(function () { return {}; });
      } catch (e) { r = null; }
      _kesOnay = false;
      if (!r || !r.ok) {
        _sonMesaj = { anahtar: _retAnahtari(r, 'google.kesilemedi'), hata: true };
        ciz();
        return;
      }
      _sonMesaj = { anahtar: d.iptal ? 'google.kesildi-google' : 'google.kesildi-yerel' };
      var yeni = await durumAl();
      if (yeni) _durum = yeni;
      ciz();
    });
  }

  function _olay(e) {
    var b = e.target.closest && e.target.closest('[data-g]');
    if (!b || !_el() || !_el().contains(b) || b.disabled) return;
    var g = b.dataset.g;
    if (g === 'kaydet') kaydet();
    else if (g === 'bagla') bagla();
    else if (g === 'dene') dene(true);
    else if (g === 'kes') kes();
    else if (g === 'tazele') tazele();
    else if (g === 'degistir') { _duzenle = true; _formHata = null; _sonMesaj = null; ciz(); var c = document.getElementById('g-cid'); if (c) c.focus(); }
    else if (g === 'vazgec') { _duzenle = false; _formHata = null; _sonMesaj = null; ciz(); }
    else if (g === 'rehber') window.open('/ui/docs/google-kurulum.html', '_blank');
    else if (g === 'cloud') window.open('https://console.cloud.google.com/apis/credentials', '_blank');
  }
  var _olayBagli = false;
  function _olaylariBagla() {
    var k = _el();
    if (_olayBagli || !k) return;
    _olayBagli = true;
    k.addEventListener('click', _olay);
    /* Enter formda Kaydet'e basar — form etiketi yok (innerHTML yeniden çizimi submit'i kaçırırdı) */
    k.addEventListener('keydown', function (e) {
      if (e.key === 'Enter' && e.target && (e.target.id === 'g-cid' || e.target.id === 'g-sec')) { e.preventDefault(); kaydet(); }
    });
  }

  var _gorunurlukBagli = false;
  function _gorunurlugeBagla() {
    if (_gorunurlukBagli) return;
    _gorunurlukBagli = true;
    /* Onay BAŞKA PENCEREDE tamamlanır; kullanıcı dönünce durum tazelenir (yoklama yok —
       HQ'nun `offsetParent` dersi: görünmeyen panel istek atmaz). */
    document.addEventListener('visibilitychange', function () {
      if (!document.hidden && _el() && _el().offsetParent !== null) tazele();
    });
  }

  function tazele() {
    return _tekUcus('tazele', async function () {
      var sonuc = await Promise.all([durumAl(), yedekAl()]);
      _durum = sonuc[0]; _yedek = sonuc[1];
      ciz();
      /* Son deneme bayatsa bir kez kendiliğinden dene — "bağlı" ancak böyle hak edilir */
      if (_durum && !_otoDenendi && (_durum.durum === 'bagli' || _durum.durum === 'denenmedi')
          && _bayat(_durum.son_deneme)) {
        _otoDenendi = true;
        dene(false);
      }
    });
  }

  /* Panel her açılışta tazelenir (`switchHqTab` → önbellek YOK: bağlantı panel dışında değişir). */
  window.googlePanelAc = function () {
    _olaylariBagla();
    _sonMesaj = null; _formHata = null; _duzenle = false; _kesOnay = false; _otoDenendi = false;
    tazele();
  };

  /* Dil tazeleyici — `dil.js::uygula` olayı WINDOW'a yayınlar (document'a değil).
     Ağa gitmez: son okunan durumla aynı çizimi tekrarlar; formdaki yazı ve son mesaj korunur.
     Panel hiç açılmadıysa dokunmaz (boş kutu BİLEREK boş kalır). */
  window.addEventListener('yuki-dil-degisti', function () {
    if (!_cizildi || !_el()) return;
    ciz();
  });
  window.googlePanelTazele = tazele;
})();
