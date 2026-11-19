/* ⚙ AYAR → CİHAZLAR — CİHAZ RAFI ( panel 13, 2026-10-01 — geliştirici taslak B'yi seçti).
 *
 * Taslak B (2026-09-26 HQ taslakları)
 * Motor: `backend/app/services/cihaz_eslestirme.py` · uçlar `/api/devices/*` · istemci `remote_agent/agent.py`
 *
 * Düzen: üstte ağ şeridi · ortada cihaz kartları ızgarası (+ kesikli "Cihaz ekle" kartı) · ekleme SAĞ
 * ÇEKMECEDE (telefonda ızgaranın üstünde sayfa). Çekmece menü değil, bir form — panel içinde ikinci
 * menü yasak (`test_ayar_menusu`).
 *
 * 🔴 Gerçek vaat: eşleşen şey bir MASAÜSTÜ AJAN PROGRAMI (`remote_agent/agent.py`). Telefon uygulaması
 *    YOK ve QR'ı okuyan hiçbir istemci yok → eşleştirme kodu METİN olarak gösterilir ve programa nasıl
 *    girileceği (adres + kod, kopyalanabilir komut) söylenir. QR üreteci (`vendor/qr-uret.js`) SİLİNMEDİ:
 *    ileride telefon istemcisi gelirse `QR_GOSTER = true` yeter.
 *
 * 🔴 Rıza: eşleşen cihazda Yuki ekran görüntüsü alır, ev klasöründe dosya okur/yazar/siler, komut
 *    çalıştırır, programları kapatır, panoyu okur (`agent.py::handle_command` ile doğrulandı). Kod
 *    üretilmeden ÖNCE bu liste açıkça gösterilir ("Anladım, kod üret").
 *
 * 🔴 Panel ağın DURUMUNU saklamaz: sunucu söyler (`GET /api/devices/ag`) ve **yeşil ışık yalnız süreç ağ adresinden
 *    gerçekten cevap veriyorsa** yanar (`dinleniyor`, soketten ölçülür). Ayar açık ama süreç hâlâ 127.0.0.1'deyse
 *    "yeniden başlatma bekliyor" der — yalan yeşil yok. "Yuki'yi ağa aç" ANAHTARI müşterinin yoludur
 *    (`PUT /api/devices/ag`, ayar yeniden başlatınca geçerli; mevcut yeniden başlatma akışı kullanılır).
 *    🔴 Uygulama kilidi kurulu değilse anahtar PASİF: "önce kilidi kur" + Güvenlik'e götürür (sunucu da 409 verir).
 *    Kapatmak her zaman serbest. Kopyalanabilir `HOST=0.0.0.0` metni KALKTI.
 *
 * 🔴 Riskli eylemler (karar 2026-11-01): dosya yazma · dosya silme · program kapatma kurulumdan KAPALI.
 *    Her biri için bir anahtar: AÇMAK erişim anahtarı ister (`.env` → `AUTH_TOKEN`) — panel satır içinde sorar,
 *    sunucunun cevabını söyler (409 = kurulumda anahtar yok · 403 = anahtar yanlış/boş). Kapatmak anahtarsız.
 *    Durum sunucudan okunur (`GET /api/devices/izinler`); anahtar hiçbir yerde saklanmaz, istekten sonra silinir.
 *
 * Kod açıkken liste 3 sn'de bir yoklanır: yeni cihaz düşünce çekmece "eşleşti" der (yoklama yalnız kod
 * açıkken ve panel görünürken koşar — görünmeyen panel istek atmaz, HQ monitörünün dersi).
 */
(function () {
  'use strict';

  var UC = '/api/devices';
  var YOKLAMA_SN = 3;          // kod açıkken liste kaç saniyede bir yoklanır
  /* QR yalnız bir telefon istemcisi onu OKUYABİLİRSE anlamlı. Şimdilik yok → saklı (kod silinmedi). */
  var QR_GOSTER = false;

  var _veri = null;            // {durum, ag, liste} — son okuma
  var _cek = null;             // çekmece: null · onay · kod · doldu · eslesti · hata
  var _kod = null;             // {kod, omur_sn, adres, baglanti}
  var _bitis = 0;              // kodun bitiş anı (Date.now ms) — sayaç duvar saatinden okur
  var _sayac = null, _tikSay = 0, _yoklaniyor = false;
  var _oncekiIds = [];         // kod üretildiği andaki cihaz kimlikleri — yenisi = eşleşme
  var _yeni = null;            // {id, ad} — eşleşen cihaz
  var _onaylandi = false;      // bu açılışta rıza listesi görüldü mü
  var _kodHata = null;         // çekmecedeki hata cümlesinin anahtarı
  var _kaldirId = null;        // iki adımlı silmenin beklediği cihaz
  var _kaldirHata = null;
  var _mesgul = {};            // eylem → true (düğme pasif + aria-busy)
  var _tek = {};               // eylem → sürmekte olan söz (çift tık = 1 istek)
  var _cizildi = false, _bagli = false, _odakCekmece = false;
  var _sonListe = null;        // son BAŞARILI cihaz listesi — hata ekranında eski-liste etiketiyle kalır
  var _agHata = null;          // ağ anahtarının hata cümlesi (sözlük anahtarı)
  var _bekleBitis = 0, _bekleSayac = null;   // 429 sonrası 'Tekrar dene' kilidi (ms)
  var BEKLE_SN = 60;
  /* eylem → [ad, ne yapar] — sözlük anahtarları DÜZ yazılır (test_cihaz_rafi ölü/eksik anahtarı böyle tarar) */
  var IZIN_METIN = {
    writefile:  ['cihaz.izin-writefile', 'cihaz.izin-writefile-ne'],
    deletefile: ['cihaz.izin-deletefile', 'cihaz.izin-deletefile-ne'],
    killproc:   ['cihaz.izin-killproc', 'cihaz.izin-killproc-ne']
  };
  var IZIN_EYLEMLER = ['writefile', 'deletefile', 'killproc'];
  var _izinForm = null;        // anahtarı sorulan eylem (satır içi form açık)
  var _izinGirdi = '';         // formdaki yazı — yeniden çizimde kaybolmasın diye bellekte, istekten sonra silinir
  var _izinHata = null;        // {eylem, anahtar} — o satırın hata cümlesi
  var _odakIzin = false;       // form açılınca odak anahtar alanına

  function _czt(anahtar, degerler) {
    return (window.YukiDil && window.YukiDil.t) ? window.YukiDil.t(anahtar, degerler) : String(anahtar);
  }

  function _el() { return document.getElementById('hq-panel-cihazlar'); }

  function _esc(s) {
    return String(s == null ? '' : s).replace(/[&<>"']/g, function (c) {
      return { '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c];
    });
  }
  /* Sözlük metni: önce kaçırılır, sonra **kalın** ve `kod` (SAĞLIK/GOOGLE ile aynı kural) */
  function _vurgu(s) {
    return _esc(s || '').replace(/\*\*(.+?)\*\*/g, '<b>$1</b>').replace(/`([^`]+)`/g, '<code>$1</code>');
  }
  function _t(anahtar, degerler) { return _vurgu(_czt(anahtar, degerler)); }

  /* Yetkili fetch — token'ı core.js `authFetch` ekler.
     🔴 Eskiden `window._yetkiFetch` aranıyordu; o ad tab-nav.js'in İÇİNDE kalıyor, window'a verilmiyor →
        panel çıplak `fetch`'e düşüyor, uygulama kilidi kuruluyken her uç 401 veriyordu. */
  function _fetch(yol, secenek) {
    if (typeof window.authFetch === 'function') return window.authFetch(yol, secenek || {});
    if (window._yetkiFetch) return window._yetkiFetch(yol, secenek);
    return fetch(yol, secenek);
  }

  function _yerel() {
    return (window.YukiDil && window.YukiDil.yerel) ? window.YukiDil.yerel() : undefined;
  }

  /* "az önce" · "12 dk önce" · "3 sa önce" · "dün" · "5 gün önce" · 30 günden eskiyse tarih */
  function _goreli(ts) {
    if (!ts) return '—';
    var sn = Math.floor(Date.now() / 1000 - ts);
    if (sn < 0) sn = 0;
    if (sn < 60) return _czt('cihaz.zaman-simdi');
    if (sn < 3600) return _czt('cihaz.zaman-dk', { n: Math.floor(sn / 60) });
    if (sn < 86400) return _czt('cihaz.zaman-sa', { n: Math.floor(sn / 3600) });
    var gun = Math.floor(sn / 86400);
    if (gun === 1) return _czt('cihaz.zaman-dun');
    if (gun < 30) return _czt('cihaz.zaman-gun', { n: gun });
    try {
      return new Date(ts * 1000).toLocaleDateString(_yerel(), { day: 'numeric', month: 'short', year: 'numeric' });
    } catch (e) { return '—'; }
  }

  function _mmss(sn) {
    if (sn < 0) sn = 0;
    return Math.floor(sn / 60) + ':' + (sn % 60 < 10 ? '0' : '') + (sn % 60);
  }

  // ── Veri ───────────────────────────────────────────────────────────────────

  /* 401 (oturum kilitli) "veri yok" DEĞİLDİR — yoksa eşleşmiş cihazları olan kilitli
     kullanıcıya "henüz cihaz yok" denir (eski panelin yalanı). */
  function _sinif(r) {
    if (r.status === 401) return 'kilitli';
    if (r.status === 429) return 'cok_istek';
    if (!r.ok) return 'hata';
    return null;
  }

  async function _al(yol) {
    try {
      var r = await _fetch(UC + yol);
      var s = _sinif(r);
      if (s) return { durum: s };
      return { durum: 'ok', veri: await r.json() };
    } catch (e) { return { durum: 'ulasilamadi' }; }
  }

  async function _oku() {
    var s = await Promise.all([_al('/ag'), _al('/eslestirilmis'), _al('/izinler')]);
    var ag = s[0], liste = s[1], izin = s[2], durum = liste.durum;
    if (ag.durum === 'kilitli') durum = ag.durum;
    if (liste.durum === 'ok' && Array.isArray(liste.veri)) _sonListe = liste.veri;
    return {
      durum: durum,
      ag: ag.durum === 'ok' ? ag.veri : null,       // okunamadıysa "bilinmiyor" — kod üretilemez
      izin: izin.durum === 'ok' && izin.veri && izin.veri.izinler ? izin.veri : null,   // okunamadıysa anahtar YOK (yalan kapalı görüntüsü yok)
      liste: liste.durum === 'ok' && Array.isArray(liste.veri) ? liste.veri : []
    };
  }

  /* Tek uçuş: aynı eylem sürerken ikinci çağrı yeni istek atmaz, ilkini bekler (çift tık = 1 istek). */
  function _tekUcus(ad, fn, goster) {
    if (_tek[ad]) return _tek[ad];
    _mesgul[ad] = true;
    if (goster !== false && _cizildi) ciz();           // düğme İSTEK SÜRERKEN pasif görünür
    _tek[ad] = Promise.resolve().then(fn).finally(function () {
      _tek[ad] = null; _mesgul[ad] = false;
      if (_cizildi) ciz();
    });
    return _tek[ad];
  }

  function yenile(goster) {
    return _tekUcus('yenile', async function () {
      _veri = await _oku();
      if (_veri.durum === 'cok_istek') _beklet();
    }, goster === true);
  }

  /* Kod isteği — ağ kapalıyken GİTMEZ (kod 127.0.0.1'e işaret ederdi: başka cihaz için işe yaramaz). */
  function kodUret() {
    if (!_veri || !_agAcik(_veri.ag)) return Promise.resolve();
    return _tekUcus('kod-uret', async function () {
      var r;
      try {
        r = await _fetch(UC + '/eslestirme', { method: 'POST' });
      } catch (e) { _cek = 'hata'; _kodHata = 'cihaz.hata-ulasilamadi'; return; }
      var s = _sinif(r);
      if (s) {
        if (s === 'cok_istek') _beklet();
        _cek = 'hata';
        _kodHata = s === 'cok_istek' ? 'cihaz.hata-cok-sik' : s === 'kilitli' ? 'cihaz.kilitli-baslik'
          : 'cihaz.kod-alinamadi';
        return;
      }
      var c = await r.json();
      _kod = c; _bitis = Date.now() + (c.omur_sn || 300) * 1000;
      /* Eşleşme = bu andan sonra düşen YENİ kimlik. Liste bayat olabilir → anlık görüntü tazesinden */
      var taze = await _al('/eslestirilmis');
      _oncekiIds = ((taze.durum === 'ok' && Array.isArray(taze.veri)) ? taze.veri : (_veri && _veri.liste) || [])
        .map(function (x) { return x.id; });
      _cek = 'kod'; _kodHata = null; _yeni = null; _odakCekmece = true;
      _sayacBaslat();
    });
  }

  /* 429: "bir dakika bekle" diyen ekran etkin 'Tekrar dene' göstermesin — süre bitene kadar pasif + geri sayım. */
  function _beklet() {
    _bekleBitis = Date.now() + BEKLE_SN * 1000;
    if (_bekleSayac) clearInterval(_bekleSayac);
    _bekleSayac = setInterval(function () {
      if (Date.now() >= _bekleBitis) { clearInterval(_bekleSayac); _bekleSayac = null; }
      if (_cizildi) ciz();
    }, 1000);
  }
  function _bekleKalan() { return Math.max(0, Math.ceil((_bekleBitis - Date.now()) / 1000)); }

  function _kodIptalEt() {
    try { _fetch(UC + '/eslestirme', { method: 'DELETE' }).catch(function () {}); } catch (e) {}
  }

  // ── Panoya kopyala ─────────────────────────────────────────────────────────

  async function _kopyala(metin) {
    try {
      if (navigator.clipboard && navigator.clipboard.writeText) { await navigator.clipboard.writeText(metin); return true; }
    } catch (e) { /* aşağıdaki yedeğe düş */ }
    try {
      var ta = document.createElement('textarea');
      ta.value = metin; ta.setAttribute('readonly', ''); ta.className = 'gorsel-gizli';
      document.body.appendChild(ta); ta.select();
      var ok = document.execCommand('copy');
      document.body.removeChild(ta);
      return !!ok;
    } catch (e) { return false; }
  }

  function _komut(win) {
    var ad = _kod.adres || '', kod = _kod.kod;
    return win ? '$env:YUKI_SERVER="' + ad + '"; python agent.py --eslestir ' + kod
      : 'YUKI_SERVER=' + ad + ' python agent.py --eslestir ' + kod;
  }

  // ── Çizim ──────────────────────────────────────────────────────────────────

  function _isik(d) { return '<span class="durum-isik ' + d + '" aria-hidden="true"></span>'; }

  function _dugme(eylem, sinif, anahtar, ek) {
    ek = ek || {};
    var m = !!_mesgul[eylem] || (eylem === 'tekrar' && !!_mesgul.yenile);
    return '<button type="button" class="dg ' + sinif + '" data-cz="' + eylem + '"'
      + (ek.id ? ' data-id="' + _esc(ek.id) + '"' : '')
      + ((ek.pasif || m) ? ' disabled' : '') + (m ? ' aria-busy="true"' : '') + '>' + _t(anahtar) + '</button>';
  }

  function _qrSvg(metin) {
    try {
      if (!window.QRUret) throw new Error('QRUret yok');
      return window.QRUret.svg(window.QRUret.matris(metin), { boyut: 188 });
    } catch (e) {
      return '<div class="alan-hata">' + _t('cihaz.qr-cizilemedi') + '</div>';
    }
  }

  /* "Başka cihaz şu an bağlanabilir" — YALNIZ süreç ağ adresinden gerçekten cevap veriyorsa (sunucu soketten ölçer).
     Ayar açık ama yeniden başlatma bekliyorsa ya da HOST açık ama cevap yoksa DEĞİL. */
  function _agAcik(ag) { return !!(ag && ag.dinleniyor === true); }

  /* Ağ KULLANILAMIYORKEN neden: ayar kapalı → 'yok' · açık ama yeniden başlatma bekliyor → 'bekliyor' ·
     açık ama ağ adresinden cevap yok → 'ulasilamiyor'. Açık anahtara "önce aç" DENMEZ. */
  function _agYok(ag, tur) {
    var h = ag && ag.ag_durum, bekl = h === 'acik-bekliyor', ulas = h === 'acik-ulasilamiyor';
    if (tur === 'ekle') return bekl ? 'cihaz.ekle-ag-bekliyor' : ulas ? 'cihaz.ekle-ag-ulasilamiyor' : 'cihaz.ekle-ag-yok';
    return bekl ? 'cihaz.bos-not-ag-bekliyor' : ulas ? 'cihaz.bos-not-ag-ulasilamiyor' : 'cihaz.bos-not-ag-yok';
  }

  function _yenidenBaslatVar() { return !!(window.yukiSistem && window.yukiSistem.yenidenBaslat); }

  /* Ağ şeridi: durum ışığı + ne olduğu + ANAHTAR. Hâller (sunucunun `ag_durum`u + kilit):
     bilinmiyor · kilitsiz · kapali · acik-bekliyor · acik-dinliyor · acik-ulasilamiyor · kapanis-bekliyor. */
  function _agHal(ag) {
    if (!ag) return 'bilinmiyor';
    var d = ag.ag_durum || 'kapali';
    if (d === 'kapali' && ag.kilit_kurulu === false) return 'kilitsiz';
    return d;
  }

  function _anahtar(ag, acik) {
    var kilitsiz = ag.kilit_kurulu === false;
    var m = !!_mesgul['ag-ac'];
    /* Kilit yoksa AÇMA pasif (kapatmak her zaman serbest: açıkken anahtar etkin kalır) */
    var pasif = m || (!acik && kilitsiz);
    var ad = _czt('cihaz.ag-ac-baslik');
    var kilitli = !acik && kilitsiz;
    return '<div class="cz-ag-sw"><button type="button" role="switch" class="hq-toggle cz-sw' + (acik ? ' on' : '') + (kilitli ? ' cz-sw-kilitli' : '') + '" data-cz="ag-ac"'
      + ' aria-checked="' + (acik ? 'true' : 'false') + '" aria-label="' + _esc(ad) + '"' + (pasif ? ' disabled' : '') + (m ? ' aria-busy="true"' : '') + '></button>'
      + '<span class="cz-sw-ad"><b>' + _t('cihaz.ag-ac-baslik') + '</b><small>' + _t(acik ? 'cihaz.ag-durum-acik' : kilitli ? 'cihaz.ag-durum-kilitli' : 'cihaz.ag-durum-kapali') + '</small></span></div>';
  }

  function _agYenidenBaslat() {
    if (!_yenidenBaslatVar()) return '<p class="cz-yb-elle">' + _t('cihaz.ag-yb-elle') + '</p>';
    return '<div class="cz-yb"><button type="button" class="dg dg-birincil" data-cz="ag-yeniden">' + _t('yb.simdi') + '</button><span class="yb-durum cz-yb-durum" role="status"></span></div>';
  }

  function _serit(ag) {
    var hal = _agHal(ag);
    if (hal === 'bilinmiyor') {
      return '<div class="cz-serit">' + _isik('uyari') + '<div class="cz-serit-metin">' + _t('cihaz.ag-bilinmiyor') + '</div>'
        + _dugme('tekrar', 'dg-ikincil', 'cihaz.tekrar') + '</div>';
    }
    var acik = !!ag.ag_ayari, adres = (ag.yerel_ip || '') + ':' + (ag.port || '');
    /* Kilit çalışırken kalktıysa süreç dinler ama sunucu ağdan gelen her isteği reddeder → yeşil DEĞİL */
    var kilitKalkti = acik && ag.kilit_kurulu === false;
    var isik = (hal === 'acik-dinliyor' && !kilitKalkti) ? 'iyi' : 'uyari';
    var dikkat = (hal !== 'acik-dinliyor' && hal !== 'kapali') || kilitKalkti;
    var baslik, ne, ek = '', eylem = '', risk = '';
    if (hal === 'acik-dinliyor') {
      baslik = 'cihaz.ag-acik-baslik'; ne = _t('cihaz.ag-acik', { adres: adres });
      risk = _t('cihaz.ag-risk'); ek += '<p class="cz-not">' + _t('cihaz.ag-acik-not') + '</p>';
    } else if (hal === 'acik-bekliyor') {
      baslik = 'cihaz.ag-bekliyor-baslik'; ne = _t('cihaz.ag-bekliyor-ne', { adres: adres }); risk = _t('cihaz.ag-risk');
      eylem = _agYenidenBaslat();
    } else if (hal === 'acik-ulasilamiyor') {
      baslik = 'cihaz.ag-ulasilamiyor-baslik'; ne = _t('cihaz.ag-ulasilamiyor-ne');
    } else if (hal === 'kapanis-bekliyor') {
      baslik = 'cihaz.ag-kapanis-baslik'; ne = _t('cihaz.ag-kapanis-ne');
      eylem = _agYenidenBaslat();
    } else if (hal === 'kilitsiz') {
      baslik = 'cihaz.ag-kapali-baslik'; ne = _t('cihaz.ag-kilitsiz-ne');
      eylem = _dugme('guvenlik', 'dg-ikincil', 'cihaz.git-guvenlik');
    } else {
      baslik = 'cihaz.ag-kapali-baslik'; ne = _t('cihaz.ag-kapali-ne'); risk = _t('cihaz.ag-risk-kapali');
    }
    if (ag.kilit_dustu && hal === 'kilitsiz') ek += '<p class="cz-not cz-vurgu">' + _t('cihaz.ag-kilit-dustu') + '</p>';
    if (kilitKalkti) baslik = 'cihaz.ag-kalkti-baslik';
    if (kilitKalkti) ek += '<p class="cz-not cz-vurgu">' + _t('cihaz.ag-kilit-kalkti') + '</p>';
    if (_agHata) ek += '<p class="cz-not cz-hata" role="alert">' + _t(_agHata) + '</p>';
    return '<div class="cz-serit cz-ag' + (dikkat ? ' cz-uyari' : '') + '" data-ag-hal="' + hal + '">' + _isik(isik)
      + '<div class="cz-serit-metin"><p><b>' + _t(baslik) + '</b> ' + ne + '</p>'
      + (risk ? '<p class="cz-risk">' + risk + '</p>' : '') + ek + '</div>'
      + '<div class="cz-serit-eylem">' + _anahtar(ag, acik) + eylem + '</div></div>';
  }

  /* Durum etiketi. Anahtarsız kurulumda "Kapalı" DEĞİL "Kilitli" + kilit simgesi: kesik çerçeveli pasif anahtar
     390'da kapalı anahtardan zor ayırt ediliyordu (görsel denetim 2026-11-10) — ayrım yalnız renge/çizgiye bırakılmaz, yazıyla da söylenir. */
  var KILIT_SVG = '<svg class="cz-kilit" viewBox="0 0 16 16" width="12" height="12" aria-hidden="true" focusable="false">'
    + '<rect x="3" y="7" width="10" height="7" rx="1.5" fill="currentColor"/>'
    + '<path d="M5.5 7V5a2.5 2.5 0 0 1 5 0v2" fill="none" stroke="currentColor" stroke-width="1.6"/></svg>';
  function _izinEtiket(acik, kurulu) {
    if (!acik && !kurulu) return '<span class="cz-etiket sessiz cz-etiket-kilitli" data-izin-durum data-izin-kilitli>'
      + KILIT_SVG + _t('cihaz.izin-kilitli') + '</span>';
    return '<span class="cz-etiket sessiz" data-izin-durum>' + _t(acik ? 'cihaz.izin-acik' : 'cihaz.izin-kapali') + '</span>';
  }

  /* Riskli eylem anahtarları. Okunamadıysa anahtar ÇİZİLMEZ — kapalı görünüp açık olabilirdi. */
  function _izinSatir(iz, e) {
    var acik = !!iz.izinler[e], kurulu = iz.anahtar_kurulu !== false;
    var m = !!_mesgul['izin:' + e], form = _izinForm === e;
    var pasif = m || form || (!acik && !kurulu);
    var ad = _czt(IZIN_METIN[e][0]);
    /* Anahtar TEK BAŞINA: "Açık"/"Kapalı" yazısı yanındayken genişlik farkı anahtarı 10 px kaydırıyordu (goz #3,
       390'da sola yaslı sütunda da 1280'de sağa yaslı sütunda da). Durum yazısı adın yanında etiket. */
    var sw = '<div class="cz-ag-sw">'
      + '<button type="button" role="switch" class="hq-toggle cz-sw' + (acik ? ' on' : '') + (!acik && !kurulu ? ' cz-sw-kilitli' : '') + '"'
      + ' data-cz="izin" data-id="' + e + '" aria-checked="' + (acik ? 'true' : 'false') + '" aria-label="' + _esc(ad) + '"'
      + (pasif ? ' disabled' : '') + (m ? ' aria-busy="true"' : '') + '></button></div>';
    var ek = '', hataVar = _izinHata && _izinHata.eylem === e;
    /* `cz-kucuk cz-hata`: `cz-not` CSS'te cz-hata'dan SONRA tanımlı ve rengi griye eziyordu (goz #1) */
    var hata = hataVar ? '<p class="cz-kucuk cz-hata" role="alert" id="cz-izin-hata-' + e + '">' + _t(_izinHata.anahtar) + '</p>' : '';
    if (form) {
      var gid = 'cz-izin-anahtar-' + e;
      ek = '<div class="cz-izin-form" data-izin-form="' + e + '"><p class="cz-not">' + _t('cihaz.izin-anahtar-sor', { ad: ad }) + '</p>'
        + '<p class="cz-kucuk"><label for="' + gid + '">' + _t('cihaz.izin-anahtar-etiket') + '</label></p>'
        + '<input id="' + gid + '" class="girdi" type="password" autocomplete="off" spellcheck="false" data-cz-girdi="' + e + '"'
        + (m ? ' disabled' : '') + (hataVar ? ' aria-invalid="true" aria-describedby="cz-izin-hata-' + e + '"' : '') + '>'
        + hata + '<div class="cz-eylem">' + _dugme('izin-ac', 'dg-birincil', 'cihaz.izin-ac-dugme', { id: e, pasif: m })
        + _dugme('izin-vazgec', 'dg-sessiz', 'cihaz.izin-vazgec', { id: e, pasif: m }) + '</div></div>';
    }
    else ek = hata;              // form kapalıyken (409 · çok sık · yazılamadı) cümle metnin altında
    return '<div class="cz-serit cz-izin' + (acik ? ' cz-uyari' : '') + '" data-izin="' + e + '" data-izin-acik="' + (acik ? '1' : '0') + '">'
      + _isik(acik ? 'uyari' : '')   // kapalı = güvenli varsayılan: ışık yok (yer tutucu, hizalama bozulmasın)
      + '<div class="cz-serit-metin"><p><b>' + _t(IZIN_METIN[e][0]) + '</b> ' + _izinEtiket(acik, kurulu) + '</p><p>' + _t(IZIN_METIN[e][1]) + '</p>' + ek + '</div>'
      + '<div class="cz-serit-eylem">' + sw + '</div></div>';
  }

  function _izinler(iz) {
    if (!iz) return '<div class="cz-serit cz-izin-bas" data-izin-bilinmiyor>' + _isik('uyari')
      + '<div class="cz-serit-metin"><p><b>' + _t('cihaz.izin-baslik') + '</b> ' + _t('cihaz.izin-okunamadi') + '</p></div>'
      + '<div class="cz-serit-eylem">' + _dugme('tekrar', 'dg-ikincil', 'cihaz.tekrar') + '</div></div>';
    var not = iz.anahtar_kurulu === false
      ? '<p class="cz-not cz-vurgu" data-izin-anahtarsiz>' + _t('cihaz.izin-anahtar-yok') + '</p>' : '';
    /* Sarmalayıcı YOK: satırlar `.oda-govde`nin boşluğunu kullanır. `.cz-serit + .cz-serit` negatif payı
       bloksuz bir sarmalayıcının içinde satırları 3-4 px üst üste bindiriyordu (goz #2 #4). */
    return '<div class="cz-serit cz-izin-bas" data-izin-bas><div class="cz-serit-metin"><p><b>' + _t('cihaz.izin-baslik') + '</b> '
      + _t('cihaz.izin-not') + '</p>' + not + '</div></div>'
      + IZIN_EYLEMLER.map(function (e) { return _izinSatir(iz, e); }).join('');
  }

  function _etiket(c) {
    if (c.bagli) return '<span class="cz-etiket iyi">' + _t('cihaz.bagli') + '</span>';
    return '<span class="cz-etiket sessiz">' + _t(c.son_gorulme ? 'cihaz.cevrimdisi' : 'cihaz.hic-baglanmadi') + '</span>';
  }

  /* Kaldır iki adımlı ve SATIR İÇİ — `confirm()` Electron penceresini kilitler. */
  function _kart(c, sade) {
    var yeni = _yeni && _yeni.id === c.id;
    var ad = c.ad || _czt('cihaz.varsayilan-ad');
    var onay = _kaldirId === c.id;
    var m = !!_mesgul['sil:' + c.id];
    var alt;
    if (sade) {
      alt = '';
    } else if (onay) {
      alt = '<div class="cz-onay"><p>' + _t('cihaz.kaldir-sor', { ad: ad }) + (c.bagli ? ' ' + _t('cihaz.kaldir-bagli') : '') + '</p>'
        + (_kaldirHata === c.id ? '<p class="cz-hata" role="alert">' + _t('cihaz.kaldirilamadi') + '</p>' : '')
        + '<div class="cz-eylem">'
        + '<button type="button" class="dg dg-yikici" data-cz="kaldir-evet" data-id="' + _esc(c.id) + '"' + (m ? ' disabled aria-busy="true"' : '') + '>' + _t('cihaz.kaldir') + '</button>'
        + _dugme('vazgec', 'dg-sessiz', 'cihaz.vazgec') + '</div></div>';
    } else {
      alt = '<div class="cz-alt">' + _dugme('kaldir', 'dg-sessiz dg-tehlike', 'cihaz.kaldir', { id: c.id }) + '</div>';
    }
    return '<article class="cz-kart' + (c.bagli ? '' : ' cevrimdisi') + (yeni ? ' yeni' : '') + '">'
      + '<div class="cz-ust"><span class="cz-ekran" aria-hidden="true"></span><div class="cz-ad-kutu"><div class="cz-ad">' + _esc(ad) + '</div>'
      + '<div class="cz-etiketler">' + _etiket(c) + (yeni ? '<span class="cz-etiket kurulum">' + _t('cihaz.yeni-etiket') + '</span>' : '') + '</div></div></div>'
      + '<dl class="cz-dl"><dt>' + _t('cihaz.son-gorulme') + '</dt><dd>' + _esc(_goreli(c.son_gorulme)) + '</dd>'
      + '<dt>' + _t('cihaz.eslesti') + '</dt><dd>' + _esc(_goreli(c.eklendi)) + '</dd></dl>' + alt + '</article>';
  }

  function _ekleKarti(ag) {
    var acik = _agAcik(ag), kodAcik = _cek === 'kod' || _cek === 'onay' || !!_mesgul['kod-uret'];
    var alt = !ag ? 'cihaz.ekle-ag-bilinmiyor' : !acik ? _agYok(ag, 'ekle')
      : _cek === 'onay' ? 'cihaz.ekle-onayda' : (_cek === 'kod' || _mesgul['kod-uret']) ? 'cihaz.ekle-kod-acik' : 'cihaz.ekle-alt';
    return '<button type="button" class="cz-ekle" data-cz="ekle"' + ((!acik || kodAcik) ? ' disabled' : '') + '>'
      + '<span class="cz-arti" aria-hidden="true">+</span><b>' + _t('cihaz.ekle') + '</b><small>' + _t(alt) + '</small></button>';
  }

  function _bos(ag) {
    var acik = _agAcik(ag);
    return '<div class="cz-bos"><span class="cz-ekran" aria-hidden="true"></span><h4>' + _t('cihaz.bos-baslik') + '</h4>'
      + '<p>' + _t(acik ? 'cihaz.bos-not' : _agYok(ag, 'bos')) + '</p>'
      + '<div class="cz-eylem">' + _dugme('ekle', 'dg-birincil', 'cihaz.ekle', { pasif: !acik || _cek === 'kod' || _cek === 'onay' || !!_mesgul['kod-uret'] }) + '</div></div>';
  }

  // ── Çekmece ────────────────────────────────────────────────────────────────

  function _yetkiler() {
    return '<ul class="cz-yetkiler">' + ['ekran', 'dosya', 'program', 'pano'].map(function (k) {
      return '<li' + (k === 'dosya' ? ' class="agir"' : '') + '>' + _t('cihaz.yetki-' + k) + '</li>';
    }).join('') + '</ul>';
  }

  function _kodGovde() {
    var k = _kod.kod;
    return (QR_GOSTER ? '<div class="cz-qr">' + _qrSvg(_kod.baglanti) + '</div>' : '')
      + '<p class="cz-adim">' + _t('cihaz.kod-talimat') + '</p>'
      + '<div class="cz-kod" aria-label="' + _esc(_czt('cihaz.kod-etiket')) + '">' + _esc(k) + '</div>'
      + '<div class="cz-sure"><div class="cz-cubuk" role="progressbar" aria-valuemin="0" aria-valuemax="' + (_kod.omur_sn || 300) + '" aria-valuenow="' + (_kod.omur_sn || 300) + '"><i></i></div></div>'
      + '<p class="cz-kucuk">' + _t('cihaz.kod-sure', { dk: Math.round((_kod.omur_sn || 300) / 60) }) + '</p>'
      + '<p class="cz-kucuk" data-cz-sure>' + _t('cihaz.kod-kalan', { sure: _mmss(Math.ceil((_bitis - Date.now()) / 1000)) }) + '</p>'
      + '<div class="cz-bekle">' + _isik('kurulum') + '<span>' + _t('cihaz.bekle') + '</span></div>'
      + '<details class="cz-komut-kutu"><summary>' + _t('cihaz.komut-baslik') + '</summary>'
      + '<p class="cz-kucuk">' + _t('cihaz.komut-nasil') + '</p>'
      + '<p class="cz-kucuk cz-komut-ad">' + _t('cihaz.komut-unix') + '</p><pre class="cz-komut">' + _esc(_komut(false)) + '</pre>'
      + _dugme('kopya-komut', 'dg-ikincil', 'cihaz.komut-kopyala')
      + '<p class="cz-kucuk cz-komut-ad">' + _t('cihaz.komut-win') + '</p><pre class="cz-komut">' + _esc(_komut(true)) + '</pre>'
      + _dugme('kopya-komut-win', 'dg-ikincil', 'cihaz.komut-kopyala') + '</details>'
      + '<div class="cz-eylem">' + _dugme('kopya-kod', 'dg-ikincil', 'cihaz.kod-kopyala') + _dugme('iptal', 'dg-sessiz', 'cihaz.kodu-iptal') + '</div>';
  }

  function _cekmece() {
    var baslik = _cek === 'eslesti' ? 'cihaz.eslesti-baslik' : 'cihaz.cekmece-baslik', ic;
    if (_cek === 'onay') {
      ic = '<p class="cz-adim"><b>' + _t('cihaz.onay-baslik') + '</b></p><p class="cz-kucuk">' + _t('cihaz.onay-giris') + '</p>' + _yetkiler()
        + '<p class="cz-kucuk">' + _t('cihaz.onay-uyari') + '</p>'
        + '<div class="cz-eylem">' + _dugme('kod-uret', 'dg-birincil', 'cihaz.onay-dugme') + _dugme('kapat', 'dg-sessiz', 'cihaz.vazgec') + '</div>';
    } else if (_cek === 'kod' && _kod) {
      ic = _kodGovde();
    } else if (_cek === 'doldu') {
      ic = '<div class="cz-durum">' + _isik('uyari') + '<span>' + _t('cihaz.doldu-baslik') + '</span></div><p class="cz-kucuk">' + _t('cihaz.doldu-not') + '</p>'
        + '<div class="cz-eylem">' + _dugme('kod-uret', 'dg-birincil', 'cihaz.yeni-kod') + '</div>';
    } else if (_cek === 'eslesti') {
      ic = '<div class="cz-durum" role="status">' + _isik('iyi') + '<span>' + _t('cihaz.eslesti-ad', { ad: (_yeni && _yeni.ad) || _czt('cihaz.varsayilan-ad') }) + '</span></div>'
        + '<p class="cz-kucuk">' + _t('cihaz.eslesti-not') + '</p>'
        + '<div class="cz-eylem">' + _dugme('kod-uret', 'dg-ikincil', 'cihaz.bir-daha') + '</div>';
    } else {   // hata
      var bekle = _kodHata === 'cihaz.hata-cok-sik' ? _bekleKalan() : 0;
      ic = '<div class="cz-durum" role="alert">' + _isik('uyari') + '<span>' + _t(_kodHata || 'cihaz.kod-alinamadi') + '</span></div>'
        + '<div class="cz-eylem">' + (bekle > 0
          ? '<button type="button" class="dg dg-birincil" data-cz="kod-uret" disabled>' + _t('cihaz.tekrar-bekle', { n: bekle }) + '</button>'
          : _dugme('kod-uret', 'dg-birincil', 'cihaz.tekrar')) + '</div>';
    }
    return '<aside class="cz-cekmece" aria-labelledby="cz-cb" aria-live="polite"><div class="cz-cb-bas"><h4 id="cz-cb" tabindex="-1">' + _t(baslik) + '</h4>'
      + _dugme('kapat', 'dg-sessiz', 'cihaz.kapat') + '</div>' + ic + '</aside>';
  }

  // ── Panelin gövdesi ────────────────────────────────────────────────────────

  function _tamKart(isik, baslik, not, eylem, eylemAnahtar) {
    var kalan = (eylem === 'tekrar') ? _bekleKalan() : 0, dug;
    if (kalan > 0) {
      dug = '<button type="button" class="dg dg-birincil" data-cz="tekrar" disabled>' + _t('cihaz.tekrar-bekle', { n: kalan }) + '</button>';
    } else dug = _dugme(eylem, 'dg-birincil', eylemAnahtar);
    return '<section class="cz-tam" role="status">' + '<div class="cz-durum">' + _isik(isik) + '<span>' + _t(baslik) + '</span></div>'
      + '<p class="cz-kucuk">' + _t(not) + '</p>'
      + '<div class="cz-eylem">' + dug + '</div></section>';
  }

  /* Hata ekranında cihazlar KAYBOLMAZ: son bilinen liste "güncel değil" etiketiyle altta kalır (silindi gibi görünmesin). */
  function _eskiListe() {
    if (!_sonListe || !_sonListe.length) return '';
    return '<p class="cz-kucuk cz-eski">' + _t('cihaz.eski-liste') + '</p><div class="cz-izgara cz-eski-izgara">'
      + _sonListe.map(function (c) { return _kart(c, true); }).join('') + '</div>';
  }

  function _govde() {
    var v = _veri;
    if (!v) return '<p class="cz-kucuk">' + _t('cihaz.yukleniyor') + '</p>';
    if (v.durum === 'kilitli') return _tamKart('uyari', 'cihaz.kilitli-baslik', 'cihaz.kilitli-not', 'tekrar', 'cihaz.tekrar') + _eskiListe();
    if (v.durum === 'cok_istek') {
      return _tamKart('uyari', 'cihaz.cok-sik-baslik', 'cihaz.cok-sik-not', 'tekrar', 'cihaz.tekrar') + _eskiListe();
    }
    if (v.durum === 'ulasilamadi') return _tamKart('uyari', 'cihaz.ulasilamadi-baslik', 'cihaz.ulasilamadi-not', 'tekrar', 'cihaz.tekrar') + _eskiListe();
    if (v.durum !== 'ok') return _tamKart('uyari', 'cihaz.hata-baslik', 'cihaz.hata-not', 'tekrar', 'cihaz.tekrar') + _eskiListe();

    var kartlar = v.liste.length
      ? '<div class="cz-izgara">' + v.liste.map(function (c) { return _kart(c); }).join('') + _ekleKarti(v.ag) + '</div>'
      : _bos(v.ag);
    return _serit(v.ag) + _izinler(v.izin)
      + '<div class="cz-yerlesim' + (_cek ? ' cekmeceli' : '') + '">' + kartlar + (_cek ? _cekmece() : '') + '</div>';
  }

  function _oda(icerik) {
    return '<div class="oda cz-oda"><h2 class="gorsel-gizli">' + _t('hq.menu.cihazlar') + '</h2>'
      + '<div class="oda-bas"><div class="oda-bas-metin"><h3 class="oda-baslik">' + _t('hq.menu.cihazlar') + '</h3>'
      + '<p class="oda-amac">' + _t('cihaz.amac') + '</p></div></div>'
      + '<div class="oda-govde">' + icerik + '</div></div>';
  }

  /* Yeniden çizim odağı kaybettirmesin: odaktaki düğme (eylem + cihaz) çizimden sonra aranıp geri verilir. */
  function _odakAnahtari() {
    var a = document.activeElement;
    if (!a || !a.getAttribute) return null;
    var e = a.getAttribute('data-cz');
    return e ? { e: e, id: a.getAttribute('data-id') } : null;
  }

  function ciz() {
    var k = _el();
    if (!k) return;
    _cizildi = true;
    var odak = _odakCekmece ? null : _odakAnahtari();
    k.innerHTML = _oda(_govde());
    var girdi = _izinForm ? k.querySelector('[data-cz-girdi="' + _izinForm + '"]') : null;
    if (girdi) girdi.value = _izinGirdi;          // yazı DOM özniteliğine girmez, yalnız alanın değeri
    try {
      if (girdi && _odakIzin && !girdi.disabled) { _odakIzin = false; odak = null; girdi.focus(); }
      if (_odakCekmece) {
        _odakCekmece = false;
        var cb = k.querySelector('#cz-cb');
        if (cb && cb.focus) cb.focus();
      } else if (odak) {
        var kimler = k.querySelectorAll('[data-cz="' + odak.e + '"]');
        for (var i = 0; i < kimler.length; i++) {
          if (!odak.id || kimler[i].getAttribute('data-id') === odak.id) {
            if (!kimler[i].disabled && kimler[i].focus) kimler[i].focus();
            break;
          }
        }
      }
    } catch (e) { /* odak en iyi çaba */ }
    _sureYaz();
  }

  // ── Sayaç + yoklama ────────────────────────────────────────────────────────

  function _kalan() { return Math.ceil((_bitis - Date.now()) / 1000); }

  /* Geri sayım yeniden çizim İSTEMEZ: yalnız yazı + çubuk (ağa gitmez, odak bozulmaz). */
  function _sureYaz() {
    var k = _el();
    if (!k || _cek !== 'kod' || !_kod) return;
    var kalan = Math.max(0, _kalan()), omur = _kod.omur_sn || 300;
    var m = k.querySelector('[data-cz-sure] b');
    if (m) m.textContent = _mmss(kalan);
    var c = k.querySelector('.cz-cubuk');
    if (c) {
      c.setAttribute('aria-valuenow', String(kalan));
      var dolgu = c.querySelector('i');
      if (dolgu) dolgu.style.width = Math.max(0, Math.min(100, kalan / omur * 100)) + '%';
      if (c.parentNode && c.parentNode.classList) c.parentNode.classList.toggle('az', kalan <= 60);
    }
  }

  function _sayacBaslat() {
    _sayacDurdur();
    _tikSay = 0;
    _sayac = setInterval(_tik, 1000);
  }

  function _sayacDurdur() {
    if (_sayac) { clearInterval(_sayac); _sayac = null; }
  }

  /* ⚠️ Panel kapanınca DUR (`offsetParent`): `switchHqTab` panel kapanışını haber vermiyor. Görünmeyen
     panelin açık kodu da iptal edilir — ekranda olmayan bir kapı 5 dakika açık kalmasın. */
  function _tik() {
    var k = _el();
    if (!k || !k.offsetParent) {
      _sayacDurdur();
      if (_cek === 'kod') { _kodIptalEt(); _kod = null; _cek = null; }
      return;
    }
    if (_kalan() <= 0) {
      _kod = null; _cek = 'doldu'; _sayacDurdur(); ciz();
      return;
    }
    _sureYaz();
    _tikSay++;
    if (_tikSay % YOKLAMA_SN === 0) _yokla();
  }

  /* Kod kullanılınca tek kullanımlık kod yanar ama sunucu "kullanıldı" demez → yeni bir cihaz kimliği
     düşmesi eşleşmedir (her eşleşme yeni `id` üretir). Bekleyen kodun yoklaması yalnız bu iş için. */
  async function _yokla() {
    if (_yoklaniyor || _cek !== 'kod') return;
    _yoklaniyor = true;
    try {
      var s = await _al('/eslestirilmis');
      if (s.durum !== 'ok' || !Array.isArray(s.veri) || _cek !== 'kod') return;
      var yeniler = s.veri.filter(function (c) { return _oncekiIds.indexOf(c.id) < 0; });
      if (yeniler.length) {
        yeniler.sort(function (a, b) { return (b.eklendi || 0) - (a.eklendi || 0); });
        _veri.liste = s.veri;
        _yeni = { id: yeniler[0].id, ad: yeniler[0].ad };
        _kod = null; _cek = 'eslesti'; _sayacDurdur(); _odakCekmece = true; ciz();
      } else if (JSON.stringify(s.veri) !== JSON.stringify(_veri.liste)) {
        _veri.liste = s.veri; ciz();           // bağlı/çevrimdışı tazelendi
      }
    } finally { _yoklaniyor = false; }
  }

  // ── Eylemler ───────────────────────────────────────────────────────────────

  function _kapat() {
    if (_cek === 'kod') _kodIptalEt();
    _sayacDurdur(); _kod = null; _cek = null; _yeni = null; _kodHata = null;
    ciz();
  }

  function _kaldirEvet(id) {
    return _tekUcus('sil:' + id, async function () {
      try {
        var r = await _fetch(UC + '/eslestirilmis/' + encodeURIComponent(id), { method: 'DELETE' });
        /* 404 = zaten yok (başka pencerede kaldırılmış): sonuç aynı, liste tazelenir */
        if (r.ok || r.status === 404) {
          _kaldirId = null; _kaldirHata = null;
          if (_yeni && _yeni.id === id) { _yeni = null; if (_cek === 'eslesti') _cek = null; }
          _veri = await _oku();
        } else _kaldirHata = id;
      } catch (e) { _kaldirHata = id; }
    });
  }

  /* Anahtar: tek uçuş (çift tık = 1 istek). 409 = kilit yok (sunucu da uygular): sebep söylenir, durum yeniden okunur.
     401 → tüm panel kilitli kartına döner. Yazılamazsa anahtar eski yerinde kalır (yalan "açıldı" yok). */
  function _agDegistir(acik) {
    return _tekUcus('ag-ac', async function () {
      _agHata = null;
      var r;
      try {
        r = await _fetch(UC + '/ag', { method: 'PUT', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ acik: !!acik }) });
      } catch (e) { _agHata = 'cihaz.hata-ulasilamadi'; return; }
      if (r.status === 409) { _agHata = 'cihaz.ag-kilit-yok-kisa'; _veri = await _oku(); return; }
      var s = _sinif(r);
      if (s === 'kilitli') { _veri = await _oku(); return; }
      if (s) { _agHata = s === 'cok_istek' ? 'cihaz.hata-cok-sik' : 'cihaz.ag-yazilamadi'; return; }
      var d = await r.json();
      if (d && d.ag && _veri) _veri.ag = d.ag; else _veri = await _oku();
    });
  }

  /* İzin anahtarı. KAPATMAK anahtarsız tek istek. AÇMAK satır içi formu açar; anahtar sunucuya gider,
     cevap olduğu gibi söylenir: 409 = kurulumda AUTH_TOKEN yok · 403 = anahtar yanlış/boş · 429 = çok sık.
     Yazılamazsa anahtar eski yerinde kalır (yalan "açıldı" yok). Anahtar her denemeden sonra bellekten silinir. */
  function _izinYaz(eylem, acik, anahtar) {
    return _tekUcus('izin:' + eylem, async function () {
      _izinHata = null;
      var r, govde = { eylem: eylem, acik: !!acik };
      if (acik) govde.anahtar = anahtar || '';
      try {
        r = await _fetch(UC + '/izinler', { method: 'PUT', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(govde) });
      } catch (e) { _izinHata = { eylem: eylem, anahtar: 'cihaz.hata-ulasilamadi' }; return; }
      if (acik) _izinGirdi = '';
      if (r.status === 409) { _izinHata = { eylem: eylem, anahtar: 'cihaz.izin-hata-anahtar-yok' }; _izinForm = null; _veri = await _oku(); return; }
      if (r.status === 403) { _izinHata = { eylem: eylem, anahtar: 'cihaz.izin-hata-yanlis' }; _odakIzin = true; return; }
      var s = _sinif(r);
      if (s === 'kilitli') { _izinForm = null; _veri = await _oku(); return; }
      if (s) { _izinHata = { eylem: eylem, anahtar: s === 'cok_istek' ? 'cihaz.izin-hata-cok-sik' : 'cihaz.izin-hata-yazilamadi' }; return; }
      var d = null;
      try { d = await r.json(); } catch (e) { /* aşağıda yeniden okunur */ }
      _izinForm = null;
      if (d && d.izinler && _veri) _veri.izin = { anahtar_kurulu: d.anahtar_kurulu, izinler: d.izinler };
      else _veri = await _oku();
    });
  }

  function _izinKapatForm() { _izinForm = null; _izinGirdi = ''; _izinHata = null; ciz(); }

  /* Mevcut iki adımlı akış (`yenidenBaslatCalistir`) kullanılır; panel yalnız İKİNCİ BASIŞI görünür kılar:
     ilk basıştan sonra düğme "Emin misin? Tekrar bas" olur ve uyarı rengi alır (akış 5 sn sonra onayı düşürür → geri döner). */
  function _yenidenBaslatTikla(b) {
    if (typeof window.yenidenBaslatCalistir !== 'function') return;
    var ilk = !(b.dataset && b.dataset.onay);
    window.yenidenBaslatCalistir(b);
    if (!ilk || !b.dataset || !b.dataset.onay) return;
    var eski = b.textContent;
    b.textContent = _czt('cihaz.ag-yb-emin');
    if (b.classList) b.classList.add('cz-yb-onay');
    setTimeout(function () {
      if (b.disabled) return;
      b.textContent = eski;
      if (b.classList) b.classList.remove('cz-yb-onay');
    }, 5000);
  }

  function _olay(e) {
    var b = e.target && e.target.closest ? e.target.closest('[data-cz]') : null;
    if (!b || b.disabled) return;
    var g = b.getAttribute('data-cz'), id = b.getAttribute('data-id');
    if (g === 'ekle') {
      if (!_veri || !_agAcik(_veri.ag) || _cek === 'kod') return;
      if (_onaylandi) { kodUret(); } else { _cek = 'onay'; _odakCekmece = true; ciz(); }
    }
    else if (g === 'kod-uret') { _onaylandi = true; kodUret(); }
    else if (g === 'kapat' || g === 'iptal') _kapat();
    else if (g === 'kaldir') { _kaldirId = id; _kaldirHata = null; ciz(); }
    else if (g === 'vazgec') { _kaldirId = null; _kaldirHata = null; ciz(); }
    else if (g === 'kaldir-evet') _kaldirEvet(id);
    else if (g === 'tekrar') { yenile(true); }
    else if (g === 'guvenlik') { if (typeof window.hqGoto === 'function') window.hqGoto('cat', 'guvenlik'); }
    else if (g === 'kopya-kod' && _kod) _kopyaGeri(b, _kod.kod);
    else if (g === 'kopya-komut' && _kod) _kopyaGeri(b, _komut(false));
    else if (g === 'kopya-komut-win' && _kod) _kopyaGeri(b, _komut(true));
    else if (g === 'ag-ac') _agDegistir(b.getAttribute('aria-checked') !== 'true');
    else if (g === 'ag-yeniden') _yenidenBaslatTikla(b);
    else if (g === 'izin' && IZIN_EYLEMLER.indexOf(id) >= 0) {
      if (b.getAttribute('aria-checked') === 'true') { _izinForm = null; _izinGirdi = ''; _izinYaz(id, false); }
      else { _izinForm = id; _izinGirdi = ''; _izinHata = null; _odakIzin = true; ciz(); }
    }
    else if (g === 'izin-ac' && id === _izinForm) _izinYaz(id, true, _izinGirdi);
    else if (g === 'izin-vazgec') _izinKapatForm();
  }

  function _girdiOlay(e) {
    var t = e.target;
    if (t && t.getAttribute && t.getAttribute('data-cz-girdi') === _izinForm) _izinGirdi = t.value;
  }

  /* Enter = Aç · Esc = Vazgeç (yalnız anahtar alanındayken) */
  function _tusOlay(e) {
    var t = e.target, eylem = t && t.getAttribute ? t.getAttribute('data-cz-girdi') : null;
    if (!eylem || eylem !== _izinForm) return;
    if (e.key === 'Enter') { e.preventDefault(); _izinGirdi = t.value; if (!_mesgul['izin:' + eylem]) _izinYaz(eylem, true, _izinGirdi); }
    else if (e.key === 'Escape') { e.preventDefault(); e.stopPropagation(); _izinKapatForm(); }
  }

  /* Düğmenin kendi yazısı 1,5 sn "Kopyalandı" olur — yeniden çizim yok, odak kalır. */
  async function _kopyaGeri(btn, metin) {
    var ok = await _kopyala(metin), eski = btn.textContent;
    btn.textContent = _czt(ok ? 'cihaz.kopyalandi' : 'cihaz.kopyalanamadi');
    setTimeout(function () { btn.textContent = eski; }, 1500);
  }

  function _olaylariBagla() {
    if (_bagli) return;
    var k = _el();
    if (!k) return;
    _bagli = true;
    k.addEventListener('click', _olay);
    k.addEventListener('input', _girdiOlay);
    k.addEventListener('keydown', _tusOlay);
  }

  /* Panel her açılışta temiz başlar: bayat kod/çekmece gösterme, liste yeniden okunur (cihaz panel dışında
     da bağlanıp ayrılır). Açıkta kalmış bir kod varsa sunucuda da yakılır. */
  async function panelAc() {
    _olaylariBagla();
    if (_cek === 'kod') _kodIptalEt();
    _sayacDurdur();
    _cek = null; _kod = null; _yeni = null; _kodHata = null; _kaldirId = null; _kaldirHata = null; _onaylandi = false; _agHata = null;
    _izinForm = null; _izinGirdi = ''; _izinHata = null; _odakIzin = false;
    ciz();
    await yenile();
  }

  window.cihazlarPanelAc = panelAc;

  /* Dil tazeleyici — `dil.js::uygula` olayı WINDOW'a yayınlar (document'a değil). Ağa gitmez: son okunan
     veriyle yeniden çizer, açık kod ve geri sayım bozulmaz. Panel hiç çizilmediyse dokunmaz. */
  window.addEventListener('yuki-dil-degisti', function () {
    if (_cizildi) ciz();
  });
})();
