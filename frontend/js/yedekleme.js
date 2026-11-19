/* ⚙ AYAR → YEDEKLEME — "korunan yerler" paneli ( panel 12, 2026-10-01 — geliştirici taslak B'yi seçti).
 *
 * Motor: `backend/app/services/yedekleme.py` · uçlar `/api/yedekleme/*`.
 * Taslak B (2026-09-26 HQ taslakları)
 *
 * 🔑 Panel tek soruya cevap verir: "dosyalarım şu an güvende mi?" — üstte TEK hüküm şeridi
 *    (ışık + cümle + tek ana düğme), altında her klasörün KENDİ durumu (yedekte · yarım ·
 *    atlandı · bulunamadı · sırada…), sağda kontroller (aç/kapa · saat · Drive alanı · Google).
 *
 * 🔴 Kapanan kusurlar (BAGLAM.md § Mevcut kusurlar):
 *    · `window._yetkiFetch` hiç tanımlı değildi → uygulama kilidi kuruluyken her istek 401. Artık `authFetch`.
 *    · "Bağlı" = token dosyası var'dı (yalan yeşil). Artık backend'in `baglanti.durum` alanı (`_g.durum()`).
 *    · 401 "durum okunamadı" diyordu → "oturum kilitli"; 429 → "çok sık".
 *    · Yoklama (2 sn) formu ve mesajı siliyordu → yazı/odak/mesaj yeniden çizimde korunur.
 *    · "Şimdi yedekle" çift tıkta iki istek atabiliyordu → tek uçuş.
 *    · Kapalıyken "Her gün 03:30 için kuruldu" yalanı → backend'in `zamanlama_bilgi.kurulu` alanı konuşur.
 *    · Ham Drive/Google metni ekrana çıkıyordu → müşteri cümlesi; ham gövde yalnız "Teknik ayrıntı"da.
 *    · "Sınırı büyütebilirsin" ölü vaadi kalktı: dosya sınırı değeriyle söylenir (`tavanlar`).
 *
 * 🔴 Klasör seçimi NATIVE diyalogla (`window.yukiDosya`); tarayıcıda yol alanına düşülür ve bu söylenir.
 * 🔴 `confirm()` KULLANILMAZ (Electron'u kilitler) — Kaldır iki adımlı tık.
 * 🔴 Panel kendi markup'ını ÇİZER (google-baglanti.js deseni); HTML'e ikinci kez yazmak "aynı soruya iki cevap" olurdu.
 */
(function () {
  'use strict';

  // ── i18n sarmalayıcı ──────────────────────────────────────────────
  function _ydt(anahtar, degerler) {
    return (window.YukiDil && window.YukiDil.t) ? window.YukiDil.t(anahtar, degerler) : String(anahtar);
  }

  var UC = '/api/yedekleme';
  var BAYAT_SAAT = 36;           // son tam yedek bundan eskiyse (ve saat kuruluysa) "bayat" der
  var DRIVE_UYARI = 0.9;         // Drive alanı bu orandan doluysa uyarır

  var _durum = null;       // /durum cevabı ya da {kilitli} · {cok_istek} · {hata} · null
  var _drive = null;       // {durum: okunuyor|tamam|kopuk|bagli-degil|hata|kilitli, limit, kullanilan}
  var _cizildi = false;    // panel en az bir kez çizildi mi (dil tazeleyici için)
  var _sonMesaj = null;    // {anahtar, degerler, hata} — yeniden çizimde KALIR
  var _silOnay = null;     // Kaldir dugmesine bir kez basilan kaynagin kimligi
  var _silSayac = null;
  var _mesgul = {};        // eylem → true (düğme pasif + aria-busy)
  var _tek = {};           // eylem → sürmekte olan söz (çift tık = 1 istek)
  var _yoklama = null;
  var _yoklamaBos = 0;     // turun basladigini gormeden gelen "calismiyor" cevaplari
  var _olayBagli = false;

  /* 11-13 : panel HQ'dan YEDEK sekmesine çıktı → kök `#yedek-kok`. */
  function _el() { return document.getElementById('yedek-kok'); }

  function _esc(s) {
    return String(s == null ? '' : s).replace(/[&<>"']/g, function (c) {
      return { '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c];
    });
  }
  /* Sözlük metni: önce kaçırılır, sonra **kalın** ve `kod` (GOOGLE/SAĞLIK ile aynı kural) */
  function _vurgu(s) {
    return _esc(s || '').replace(/\*\*(.+?)\*\*/g, '<b>$1</b>').replace(/`([^`]+)`/g, '<code>$1</code>');
  }
  function _t(anahtar, degerler) { return _vurgu(_ydt(anahtar, degerler)); }

  /* Yetkili fetch — token'ı core.js `authFetch` ekler.
     🔴 `window._yetkiFetch` tab-nav.js'in İÇİNDE kalıyor, window'a verilmiyor (tarayıcıda ölçüldü):
        eski panel çıplak `fetch`'e düşüyor, uygulama kilidi kuruluyken her şey 401'di. */
  function _fetch(yol, secenek) {
    if (typeof window.authFetch === 'function') return window.authFetch(yol, secenek || {});
    return fetch(yol, secenek);
  }

  /* Tek uçuş: aynı eylem sürerken ikinci çağrı yeni istek atmaz, ilkini bekler. */
  function _tekUcus(ad, fn) {
    if (_tek[ad]) return _tek[ad];
    _mesgul[ad] = true;
    _tek[ad] = Promise.resolve().then(fn).finally(function () {
      _tek[ad] = null; _mesgul[ad] = false;
      if (_cizildi) ciz();      // `disabled` çizimle gelir → iş bitince yeniden çiz
    });
    return _tek[ad];
  }

  // ── Biçimler ────────────────────────────────────────────────────────────────
  /* Bayt → okunur birim. SI (÷1000) çünkü etiket MB/GB — `yayin.py`'nin kalibre ettiği ayrımın aynısı. */
  function _boyut(b) {
    b = Number(b) || 0;
    if (b < 1000) return b + ' B';
    var birim = ['kB', 'MB', 'GB', 'TB'], i = -1;
    do { b /= 1000; i++; } while (b >= 1000 && i < birim.length - 1);
    /* Yerel ondalık (TR virgül) + bölünmez boşluk: "2,0 GB" iki satıra kırılmaz */
    var sayi;
    try { sayi = b >= 10 ? Math.round(b).toLocaleString(_yerel()) : b.toLocaleString(_yerel(), { minimumFractionDigits: 1, maximumFractionDigits: 1 }); }
    catch (e) { sayi = b >= 10 ? String(Math.round(b)) : b.toFixed(1); }
    return sayi + '\u00a0' + birim[i];
  }

  function _sayi(n) { try { return Number(n || 0).toLocaleString(_yerel()); } catch (e) { return String(n || 0); } }
  function _yerel() { return (window.YukiDil && window.YukiDil.yerel) ? window.YukiDil.yerel() : 'tr-TR'; }
  function _gunFarki(z) {
    var bugun = new Date(); bugun.setHours(0, 0, 0, 0);
    var gun = new Date(z); gun.setHours(0, 0, 0, 0);
    return Math.round((bugun - gun) / 86400000);
  }
  function _saatMetni(z) { return z.toLocaleTimeString(_yerel(), { hour: '2-digit', minute: '2-digit' }); }

  /* "az önce" · "12 dk önce" · "bugün 14:02" · "dün 22:40" · "26 Eylül 22:40" */
  function _zaman(iso) {
    var z = new Date(iso);
    if (!iso || isNaN(z)) return '';
    var fark = Date.now() - z.getTime();
    if (fark >= 0 && fark < 60 * 1000) return _ydt('google.zaman-az-once');
    if (fark >= 0 && fark < 60 * 60 * 1000) return _ydt('google.zaman-dk-once', { n: Math.floor(fark / 60000) });
    var g = _gunFarki(z), saat = _saatMetni(z);
    if (g === 0) return _ydt('saglik.zaman-bugun', { saat: saat });
    if (g === 1) return _ydt('saglik.zaman-dun', { saat: saat });
    return z.toLocaleDateString(_yerel(), { day: 'numeric', month: 'long' }) + ' ' + saat;
  }
  /* Etiket için kısa: "bugün" · "dün" · "6 gün önce" · "12 Eyl" */
  function _kisa(iso) {
    var z = new Date(iso);
    if (!iso || isNaN(z)) return '';
    var g = _gunFarki(z);
    if (g <= 0) return _ydt('yedek.kisa-bugun');
    if (g === 1) return _ydt('yedek.kisa-dun');
    if (g <= 14) return _ydt('yedek.gun-once', { n: g });
    return z.toLocaleDateString(_yerel(), { day: 'numeric', month: 'short' });
  }
  /* Gelecek: "bugün 03:00" · "yarın 03:00" · "3 Ekim 03:00" */
  function _sonraki(iso) {
    var z = new Date(iso);
    if (!iso || isNaN(z)) return '';
    var g = -_gunFarki(z), saat = _saatMetni(z);
    if (g === 0) return _ydt('saglik.zaman-bugun', { saat: saat });
    if (g === 1) return _ydt('yedek.zaman-yarin', { saat: saat });
    return z.toLocaleDateString(_yerel(), { day: 'numeric', month: 'long' }) + ' ' + saat;
  }

  // ── Okuma ───────────────────────────────────────────────────────────────────
  async function durumAl() {
    try {
      var r = await _fetch(UC + '/durum');
      /* 401 = oturum kilitli/düşmüş — "durum okunamadı" demek sebebi saklıyordu */
      if (r.status === 401) return { kilitli: true };
      if (r.status === 429) return { cok_istek: true };
      /* Yuki'ye ulaşıldı ama cevap bozuk (5xx) — bu, ulaşılamadı DEĞİL */
      if (!r.ok) return { hata: true };
      return await r.json();
    } catch (e) { return null; }
  }

  function _gd() {
    var b = (_durum && _durum.baglanti) || {};
    return b.durum || (b.token ? 'denenmedi' : 'yok');
  }
  /* "bağlı" yalnız `bagli` (denenmiş) ya da `denenmedi` (token var, henüz sınanmadı — Google'a sormadan koptu denmez) */
  function _bagli() { var g = _gd(); return g === 'bagli' || g === 'denenmedi'; }
  function _kopuk() { return _gd() === 'kopuk'; }
  function _hazirMi() { return _durum && !_durum.kilitli && !_durum.cok_istek && !_durum.hata; }

  /* Drive alanı: Google'a çıkar (10/dk) → açılışta BİR kez, ayrıca "Yenile". Kopukken sorulmaz. */
  function driveOku(sessiz) {
    return _tekUcus('drive', async function () {
      if (!sessiz || !_drive) _drive = { durum: 'okunuyor' };
      if (_cizildi) ciz();
      var r = null, d = {};
      try {
        r = await _fetch(UC + '/drive-kullanim');
        d = await r.json().catch(function () { return {}; });
      } catch (e) { r = null; }
      if (r && r.ok) _drive = { durum: 'tamam', limit: d.limit, kullanilan: d.kullanilan };
      else if (r && r.status === 409) _drive = { durum: 'kopuk' };
      else if (r && r.status === 400) _drive = { durum: 'bagli-degil' };
      else if (r && r.status === 401) _drive = { durum: 'kilitli' };
      else _drive = { durum: 'hata' };
    });
  }

  // ── Hüküm: panelin TEK cümlesi ───────────────────────────────────────────────
  /* Dönen: {isik, baslik, alt, ana:{eylem, sinif, anahtar, pasif}, serit, belirsiz, neden:[…]}.
     Sıra önemli: önce "yedekleme hiç çalışamaz" (bağsız · kopuk), sonra "çalışıyor", "kapalı", sonra son turun sonucu. */
  function _neden(tur, govde, teknik, eylem) { return { tur: tur, govde: govde, teknik: teknik || '', eylem: eylem || null }; }

  var _KOPUK = {
    invalid_grant:       { bas: 'yedek.kopuk-baslik',        neden: 'google.neden-grant' },
    invalid_client:      { bas: 'yedek.kopuk-baslik-kimlik', neden: 'google.neden-client' },
    unauthorized_client: { bas: 'yedek.kopuk-baslik',        neden: 'google.neden-yetkisiz' },
    'kimlik-degisti':    { bas: 'yedek.kopuk-baslik',        neden: 'google.neden-kimlik-degisti' },
    'kimlik-gecersiz':   { bas: 'yedek.kopuk-baslik-kimlik', neden: 'google.neden-gecersiz' }
  };

  function _uyariVar(t) {
    if (!t) return false;
    if (t.tavan_doldu || (t.buyuk_atlandi && t.buyuk_atlandi.length)) return true;
    return (t.kaynaklar || []).some(function (k) { return k.durum === 'yol-yok'; });
  }

  function _dikkatSayisi() {
    var n = 0;
    (_durum.kaynaklar || []).forEach(function (k) {
      var s = _kartDurum(k);
      if (s.isik === 'uyari' || s.isik === 'kritik') n++;
    });
    return n;
  }

  function _hukum() {
    var d = _durum, t = d.son_tur;
    var tekrar = { eylem: 'simdi', sinif: 'dg-birincil', anahtar: 'yedek.tekrar-dene' };

    if (!_bagli() && !_kopuk()) {
      return { isik: 'kurulum', serit: '', baslik: 'yedek.bagsiz-baslik', alt: _ydt('yedek.bagsiz-alt'),
        ana: { eylem: 'google', sinif: 'dg-birincil', anahtar: 'yedek.google-paneli-ac' } };
    }
    if (_kopuk()) {
      var sebep = (d.baglanti && d.baglanti.sebep) || 'invalid_grant';
      var k = _KOPUK[sebep] || _KOPUK.invalid_grant;
      return { isik: 'kritik', serit: 'kritik', baslik: k.bas,
        alt: d.son_yedek ? _ydt('yedek.kopuk-alt', { zaman: _zaman(d.son_yedek) }) : _ydt('yedek.kopuk-alt-hic'),
        neden: [_neden('kritik', '**' + _ydt('google.neden-olabilir') + '** ' + _ydt(k.neden))],
        ana: { eylem: 'google', sinif: 'dg-birincil', anahtar: 'yedek.google-paneli-ac' } };
    }
    if (d.calisiyor) {
      var c = d.canli;
      return { isik: 'olculemedi', serit: '', baslik: 'yedek.yedekleniyor',
        alt: _ydt('yedek.suruyor-alt') + (c && c.yuklenen + c.guncellenen > 0
          ? ' ' + _ydt('yedek.suruyor-sayac', { n: _sayi(c.yuklenen + c.guncellenen), boyut: _boyut(c.bayt) }) : ''),
        belirsiz: true, ana: { eylem: 'simdi', sinif: 'dg-birincil', anahtar: 'yedek.yedekleniyor', pasif: true } };
    }
    if (!d.acik) {
      return { isik: 'uyari', serit: 'uyari', baslik: 'yedek.kapali-baslik',
        alt: d.son_yedek ? _ydt('yedek.kapali-alt', { zaman: _zaman(d.son_yedek) }) : _ydt('yedek.kapali-alt-hic'),
        ana: { eylem: 'ac', sinif: 'dg-birincil', anahtar: 'yedek.ac' } };
    }
    if (!t && !d.son_yedek) {
      var zb = d.zamanlama_bilgi || {};
      return { isik: 'kurulum', serit: '', baslik: 'yedek.ilk-baslik',
        alt: zb.kurulu ? _ydt('yedek.ilk-alt-saat', { saat: d.zamanlama }) : _ydt('yedek.ilk-alt'),
        ana: { eylem: 'simdi', sinif: 'dg-birincil', anahtar: 'yedek.ilk-yedek' } };
    }
    if (t && t.hata) {
      var tur = t.hata_tur || 'diger', yuk = (t.yuklenen || 0) + (t.guncellenen || 0);
      var tarih = _zaman(t.bitti);
      var gitti = yuk ? _ydt('yedek.hata-gitti', { n: _sayi(yuk) }) : '';
      var teknik = t.teknik || '';
      if (tur === 'dolu') {
        return { isik: 'kritik', serit: 'kritik', baslik: 'yedek.dolu-baslik',
          alt: tarih + ' · ' + (yuk ? _ydt('yedek.dolu-alt', { n: _sayi(yuk) }) : _ydt('yedek.dolu-alt-hic')),
          neden: [_neden('kritik', _ydt('yedek.dolu-ne-yapmali'), teknik)], ana: tekrar };
      }
      if (tur === 'api-kapali') {
        return { isik: 'kritik', serit: 'kritik', baslik: 'yedek.api-baslik', alt: tarih,
          neden: [_neden('kritik', t.hata, teknik, { eylem: 'simdi', anahtar: 'yedek.tekrar-dene' })],
          ana: { eylem: 'rehber', sinif: 'dg-birincil', anahtar: 'google.rehber-resimli' } };
      }
      if (tur === 'kopuk' || tur === 'bagli-degil') {
        return { isik: 'kritik', serit: 'kritik', baslik: 'yedek.izin-baslik', alt: tarih,
          neden: [_neden('kritik', t.hata, teknik)],
          ana: { eylem: 'google', sinif: 'dg-birincil', anahtar: 'yedek.google-paneli-ac' } };
      }
      /* Ağ hatasında şerit ile kutu aynı cümleyi tekrarlamaz: sebep şeridin alt satırında, kutu yalnız "Ne yapmalı" */
      if (tur === 'ag') {
        return { isik: 'kritik', serit: 'kritik', baslik: 'yedek.yarida-baslik',
          alt: tarih + (gitti ? ' · ' + gitti : '') + ' · ' + _ydt('yedek.ag-sebep'),
          neden: [_neden('kritik', _ydt('yedek.ag-ne-yapmali'), teknik)], ana: tekrar };
      }
      return { isik: 'kritik', serit: 'kritik', baslik: 'yedek.yarida-baslik',
        alt: tarih + (gitti ? ' · ' + gitti : ''), neden: [_neden('kritik', t.hata, teknik)], ana: tekrar };
    }
    // ↓ son tur başarılı
    var zb2 = d.zamanlama_bilgi || {};
    var son = d.son_yedek || (t && t.bitti);
    if (_uyariVar(t)) {
      return { isik: 'uyari', serit: 'uyari', baslik: 'yedek.uyarili-baslik',
        alt: _zaman(t.bitti) + ' · ' + _ydt('yedek.uyarili-alt', { yeni: _sayi(t.yuklenen), gunc: _sayi(t.guncellenen), boyut: _boyut(t.bayt), n: _dikkatSayisi() }),
        ana: { eylem: 'simdi', sinif: 'dg-ikincil', anahtar: 'yedek.simdi' } };
    }
    var yas = son ? (Date.now() - new Date(son).getTime()) / 3600000 : 0;
    if (d.zamanlama && yas > BAYAT_SAAT) {
      return { isik: 'uyari', serit: 'uyari', baslik: 'yedek.bayat-baslik',
        baslikDeger: { n: Math.max(1, Math.round(yas / 24)) },
        alt: _ydt('yedek.bayat-alt', { saat: d.zamanlama }),
        neden: [_neden('bilgi', _ydt('yedek.bayat-ipucu'))],
        ana: { eylem: 'simdi', sinif: 'dg-birincil', anahtar: 'yedek.simdi' } };
    }
    var h = { isik: 'iyi', serit: '', baslik: 'yedek.iyi-baslik', neden: [],
      ana: { eylem: 'simdi', sinif: 'dg-ikincil', anahtar: 'yedek.simdi' } };
    var parca = [_ydt('yedek.iyi-son', { zaman: _zaman(t.bitti) })];
    parca.push((t.yuklenen || t.guncellenen)
      ? _ydt('yedek.iyi-degisen', { yeni: _sayi(t.yuklenen), gunc: _sayi(t.guncellenen), boyut: _boyut(t.bayt) })
      : _ydt('yedek.iyi-degisen-yok'));
    if (zb2.kurulu && zb2.sonraki) parca.push(_ydt('yedek.iyi-sonraki', { zaman: _sonraki(zb2.sonraki) }));
    else if (!d.zamanlama) parca.push(_ydt('yedek.iyi-saat-yok'));
    h.alt = parca.join(' · ');
    if (_drive && _drive.durum === 'tamam' && _drive.limit && _drive.kullanilan / _drive.limit >= DRIVE_UYARI) {
      h.isik = 'uyari'; h.serit = 'uyari';   /* yeşil "güncel" ışığı altındaki uyarıyı gölgelemesin */
      h.neden.push(_neden('uyari', _ydt('yedek.drive-dolmak-uzere', { kullanilan: _boyut(_drive.kullanilan), limit: _boyut(_drive.limit) })));
    }
    return h;
  }

  // ── Klasör kartı: her klasörün KENDİ durumu ─────────────────────────────────
  /* Dönen: {isik, etiket, metin, ek} — etiket kısa hap, metin tek cümle. */
  function _kartDurum(k) {
    var d = _durum, t = d.son_tur, tu = k.tur ? k.tur.durum : null;
    var buyuk = ((t && t.buyuk_atlandi) || []).filter(function (b) { return b.kaynak === k.id; });
    var bek = { isik: 'kurulum', etiket: _ydt('yedek.et-bekliyor'), metin: _ydt('yedek.kart-bekliyor') };

    if (d.calisiyor && k.canli) {
      if (k.canli.durum === 'suruyor') return { isik: 'olculemedi', etiket: _ydt('yedek.et-suruyor'), metin: _ydt('yedek.kart-suruyor') };
      if (k.canli.durum === 'sirada') return { isik: 'olculemedi', etiket: _ydt('yedek.et-sirada'), metin: _ydt('yedek.kart-sirada') };
      if (k.canli.durum === 'tamam' || k.canli.durum === 'yarim') return { isik: 'iyi', etiket: _ydt('yedek.et-yedekte'), metin: _ydt('yedek.kart-bu-tur') };
    }
    if (k.yol_var === false) {
      return { isik: 'kritik', etiket: _ydt('yedek.et-bulunamadi'), metin: _ydt('yedek.kart-bulunamadi') };
    }
    if (!_bagli() && !_kopuk()) return bek;
    var son = k.son_yedek;
    if (_kopuk()) {
      return son ? { isik: 'uyari', etiket: _kisa(son), metin: _ydt('yedek.kart-kopuk') } : bek;
    }
    if (!d.acik) {
      return son ? { isik: 'uyari', etiket: _kisa(son), metin: _ydt('yedek.kart-kapali', { zaman: _zaman(son) }) } : bek;
    }
    if (t && t.hata) {
      var dolu = t.hata_tur === 'dolu';
      if (tu === 'yarida') return { isik: 'kritik', etiket: _ydt('yedek.et-yarida'), metin: _ydt(dolu ? 'yedek.kart-dolu' : 'yedek.kart-yarida') };
      if (tu === 'sira-gelmedi') return { isik: 'kritik', etiket: _ydt('yedek.et-sira-gelmedi'), metin: _ydt(dolu ? 'yedek.kart-dolu' : 'yedek.kart-baslanamadi') };
    }
    if (tu === 'yarim') {
      return { isik: 'uyari', etiket: _ydt('yedek.et-yarim'),
        metin: _ydt('yedek.kart-yarim', { n: _sayi(k.tur.tavan_atlanan || 0) }), ek: 'devam' };
    }
    if (buyuk.length) {
      var ilk = buyuk[0];
      return { isik: 'uyari', etiket: _ydt('yedek.et-atlandi', { n: _sayi(buyuk.length) }),
        metin: _ydt('yedek.kart-buyuk', { n: buyuk.length, mb: (d.tavanlar && d.tavanlar.tek_dosya_mb) || '' }),
        ornek: _ydt('yedek.kart-buyuk-ornek', { yol: ilk.yol, mb: ilk.mb }) };
    }
    if (son || tu === 'tamam') {
      var zm = son || (t && t.bitti);
      /* Saat kuruluyken günlerdir yedek alınmadıysa klasör "yedekte" diye yeşil yanmaz (hüküm şeridiyle aynı eşik) */
      if (d.zamanlama && zm && (Date.now() - new Date(zm).getTime()) / 3600000 > BAYAT_SAAT) {
        return { isik: 'uyari', etiket: _kisa(zm), metin: _ydt('yedek.kart-yedekte', { zaman: _zaman(zm) }) };
      }
      return { isik: 'iyi', etiket: _ydt('yedek.et-yedekte'), metin: _ydt('yedek.kart-yedekte', { zaman: _zaman(zm) }) };
    }
    return bek;
  }

  // ── Parçalar ────────────────────────────────────────────────────────────────
  function _isik(d) { return '<span class="durum-isik ' + d + '" aria-hidden="true"></span>'; }
  function _hap(tur, metin) { return '<span class="yb-hap ' + tur + '">' + _esc(metin) + '</span>'; }
  function _dugme(eylem, sinif, anahtar, pasif, ek) {
    var m = !!_mesgul[eylem];
    return '<button type="button" class="dg ' + sinif + '" data-y="' + eylem + '"' + (ek || '')
      + ((pasif || m) ? ' disabled' : '') + (m ? ' aria-busy="true"' : '') + '>' + _t(anahtar) + '</button>';
  }
  function _hapTuru(isik) {
    return isik === 'iyi' ? 'iyi' : isik === 'kritik' ? 'kritik' : isik === 'uyari' ? 'uyari' : isik === 'kurulum' ? 'kurulum' : 'sessiz';
  }

  function _nedenHtml(n) {
    var h = '<div class="yb-neden ' + n.tur + '"><div class="yb-neden-yay"><p>' + _vurgu(n.govde) + '</p>';
    if (n.teknik) {
      h += '<details><summary>' + _t('yedek.teknik') + '</summary><code>' + _esc(n.teknik) + '</code></details>';
    }
    h += '</div>';
    if (n.eylem) h += _dugme(n.eylem.eylem, 'dg-ikincil', n.eylem.anahtar);
    return h + '</div>';
  }

  function _serit(h) {
    var ana = h.ana;
    return '<section class="yb-serit ' + (h.serit || '') + '" aria-live="polite">'
      + '<div class="yb-hukum">' + _isik(h.isik) + '<div class="yb-yay"><h4>' + _t(h.baslik, h.baslikDeger) + '</h4>'
      + (h.alt ? '<p>' + _vurgu(h.alt) + '</p>' : '') + '</div></div>'
      + (ana ? _dugme(ana.eylem, ana.sinif, ana.anahtar, ana.pasif) : '')
      + (h.belirsiz ? '<div class="yb-belirsiz" role="progressbar" aria-label="' + _esc(_ydt('yedek.yedekleniyor')) + '"></div>' : '')
      + '</section>';
  }

  function _mesajKutusu() {
    var m = _sonMesaj && _sonMesaj.yer !== 'saat' ? _sonMesaj : null, metin = m ? _ydt(m.anahtar, m.degerler) : '';
    return '<p id="y-mesaj" class="ak-mesaj yb-mesaj" role="status"' + (m && m.hata ? ' data-hata="1"' : '') + '>'
      + _vurgu(metin) + '</p>';
  }

  function _kart(k) {
    var s = _kartDurum(k), sil = _silOnay === k.id;
    var devam = s.ek === 'devam' && _acikBagli() && !_durum.calisiyor;
    return '<article class="yb-kart ' + (s.isik === 'kritik' || s.isik === 'uyari' ? s.isik : '') + '">'
      + '<div class="yb-ust">' + _isik(s.isik) + '<h5>' + _esc(k.ad) + '</h5>' + _hap(_hapTuru(s.isik), s.etiket) + '</div>'
      + '<div class="yb-yol">' + (k.sistem ? _t('yedek.yuki-alt') : '<code>' + _esc(k.yol) + '</code>') + '</div>'
      + '<div class="yb-say">' + _esc(_sayi(k.dosya)) + ' <small>' + _t('yedek.dosya-boyut', { boyut: _boyut(k.bayt) }) + '</small></div>'
      + '<div class="yb-dur ' + (s.isik === 'kritik' || s.isik === 'uyari' ? s.isik : '') + '">' + _vurgu(s.metin) + '</div>'
      + (s.ornek ? '<div class="yb-kucuk">' + _vurgu(s.ornek) + '</div>' : '')
      + (k.kaynakta_yok ? '<div class="yb-kucuk">' + _t('yedek.kaynakta-yok', { n: _sayi(k.kaynakta_yok) }) + '</div>' : '')
      + (sil ? '<p class="yb-kucuk yb-sil-not" role="status">' + _t('yedek.kaldir-not') + '</p>' : '')
      + (k.sistem
        ? '<div class="yb-alt-eylem"><span class="yb-kucuk">' + _t('yedek.her-zaman') + '</span></div>'
        : '<div class="yb-alt-eylem">' + (devam ? _dugme('simdi', 'dg-ikincil', 'yedek.devam') : '')
          + '<button type="button" class="dg dg-sessiz dg-tehlike" data-y="sil" data-id="' + _esc(k.id) + '"'
          + ((_mesgul['sil:' + k.id] || (k.canli && k.canli.durum === 'suruyor')) ? ' disabled' + (_mesgul['sil:' + k.id] ? ' aria-busy="true"' : '') : '') + (sil ? ' data-onay="1"' : '') + '>'
          + _t(sil ? 'yedek.emin-misin' : 'yedek.kaldir') + '</button></div>')
      + '</article>';
  }
  function _acikBagli() { return _durum && _durum.acik && _bagli(); }

  function _ekleKarti() {
    /* Tarayıcıda native diyalog YOK — bunu gizlemek yerine söyleriz (`yukiDosya` yoksa metin alanı). */
    var win = (typeof navigator !== 'undefined' && /win/i.test(navigator.platform || ''));
    var mesgul = _mesgul.ekle ? ' disabled aria-busy="true"' : '';
    var yolOrnek = _esc(_ydt(win ? 'yedek.yol-ornek-win' : 'yedek.yol-ornek-unix'));
    var secici = window.yukiDosya
      ? '<div class="ak-dugmeler"><button id="y-ekle" data-y="ekle" class="dg dg-ikincil" type="button"' + mesgul + '>'
        + _t('yedek.klasor-ekle') + '</button></div>'
      /* Tarayıcıda native diyalog YOK — bunu gizlemek yerine söyleriz. */
      : '<div class="alan"><label for="y-yol">' + _t('yedek.klasor-yolu') + '</label>'
        + '<p class="yb-kucuk">' + _t('yedek.uygulama-icinde') + '</p>'
        + '<div class="ak-dugmeler"><input class="girdi" id="y-yol" type="text" spellcheck="false" autocomplete="off"'
        + ' placeholder="' + yolOrnek + '">'
        + '<button id="y-ekle-yol" data-y="ekle-yol" class="dg dg-ikincil" type="button"' + mesgul + '>' + _t('yedek.ekle') + '</button></div></div>';
    return '<div class="yb-kart yb-ekle">' + secici + '<p class="yb-kucuk">' + _t('yedek.ekle-alt') + '</p></div>';
  }

  /* Yuki verisi kapatılmışsa (eski panel/API ile) geri açmanın TEK yolu — sessiz veri kaybı olmasın */
  function _yukiKapaliKarti() {
    return '<div class="yb-kart yb-ekle"><p class="yb-kucuk">' + _t('yedek.yuki-kapali') + '</p>'
      + '<div class="ak-dugmeler">' + _dugme('yuki-ac', 'dg-ikincil', 'yedek.yuki-ac') + '</div></div>';
  }

  function _googleBlok() {
    var g = _gd(), b = (_durum.baglanti || {}), h = '';
    var st = _durum.son_tur, ht = (st && st.hata && !_durum.calisiyor) ? st.hata_tur : '';
    if (g === 'bagli' && ht === 'api-kapali') {
      /* Bağlantı sağlam ama yedekleme duruyor: yeşil "bağlı · başarılı" şeridin kırmızısıyla çelişirdi */
      h = _hap('uyari', _ydt('yedek.g-drive-kapali')) + ' <span class="yb-kucuk">' + _t('yedek.g-drive-kapali-alt') + '</span>';
    } else if (g === 'bagli' && (ht === 'kopuk' || ht === 'bagli-degil')) {
      h = _hap('uyari', _ydt('yedek.g-izin-yok')) + ' <span class="yb-kucuk">' + _t('yedek.g-izin-yok-alt') + '</span>';
    } else if (g === 'bagli') {
      h = _hap('iyi', _ydt('yedek.g-bagli')) + ' <span class="yb-kucuk">' + _t('yedek.g-bagli-alt', { zaman: _zaman(b.son_deneme && b.son_deneme.zaman) }) + '</span>';
    } else if (g === 'denenmedi') {
      h = _hap('sessiz', _ydt('yedek.g-denenmedi')) + ' <span class="yb-kucuk">' + _t('yedek.g-denenmedi-alt') + '</span>';
    } else if (g === 'kopuk') {
      h = _hap('kritik', _ydt('yedek.g-koptu')) + ' <span class="yb-kucuk">' + _t('yedek.g-koptu-alt') + '</span>';
    } else {
      h = _hap('kurulum', _ydt('yedek.g-yok')) + ' <span class="yb-kucuk">' + _t('yedek.g-yok-alt') + '</span>';
    }
    return '<div class="yb-blok"><span class="yb-et">Google</span><div>' + h + '</div>'
      + (((g === 'bagli' && !/^(api-kapali|kopuk|bagli-degil)$/.test(ht)) || g === 'kopuk') ? '' : _dugme('google', 'dg-ikincil', 'yedek.google-paneli')) + '</div>';
  }

  function _driveBlok() {
    var g = _gd(), v = _drive, ic = '';
    if (!_bagli() && g !== 'kopuk') ic = '<span class="yb-kucuk">' + _t('yedek.drive-baglaninca') + '</span>';
    else if (g === 'kopuk' || (v && v.durum === 'kopuk')) ic = '<span class="yb-kucuk">' + _t('yedek.drive-yeniden-baglaninca') + '</span>';
    else if (!v || v.durum === 'okunuyor') ic = '<span class="yb-kucuk">' + _t('yedek.drive-okunuyor') + '</span>';
    else if (v.durum === 'tamam') {
      if (v.limit) {
        var o = Math.min(1, v.kullanilan / v.limit), c = o >= 1 ? 'kritik' : (o >= DRIVE_UYARI ? 'uyari' : '');
        var metin = _ydt('yedek.drive-oran', { kullanilan: _boyut(v.kullanilan), limit: _boyut(v.limit) });
        ic = '<div class="yb-alan-satir"><div class="yb-olcu ' + c + '" role="img" aria-label="' + _esc(metin) + '">'
          + '<i data-oran="' + Math.round(o * 100) + '"></i></div><span class="yb-kucuk ' + c + '">' + _esc(metin)
          + (o >= 1 ? ' — ' + _esc(_ydt('yedek.drive-dolu')) : '') + '</span></div>';
      } else {
        ic = '<span class="yb-kucuk">' + _t('yedek.drive-sinirsiz', { kullanilan: _boyut(v.kullanilan) }) + '</span>';
      }
    } else if (v.durum === 'kilitli') ic = '<span class="yb-kucuk">' + _t('hq.oturum-kilitli') + '</span>';
    else ic = '<span class="yb-kucuk">' + _t('yedek.drive-okunamadi') + '</span>';
    var yenile = (_bagli() && v && v.durum !== 'okunuyor') ? _dugme('drive', 'dg-sessiz', 'yedek.yenile') : '';
    return '<div class="yb-blok"><span class="yb-et">' + _t('yedek.drive-alani') + '</span>' + ic + yenile + '</div>';
  }

  /* ── 11-14 görünüm dili kişisel Yuki "Drive" sayfası gibi (kullanıcı seçimi, madde 10) ─────────────────
     Üst çubuk (serif "Drive") · sol sütun: kadran + hüküm + cetvel satırları · orta: Akış · sağ: Klasörler.
     Arka uç AYNI (`/api/yedekleme/*`); kişiselin rclone uçları, Bulutta gezgini, Kontrol et / Kuru çalıştır
     ve 30 günlük geçmiş halkası oss'ta yok → sahte düğme/sekme konmadı. */
  function _yan() {
    var d = _durum, bag = _bagli() || _kopuk(), zb = d.zamanlama_bilgi || {}, bilgi = '';
    var durmus = _kopuk() || (d.son_tur && d.son_tur.hata && /^(api-kapali|kopuk|bagli-degil)$/.test(d.son_tur.hata_tur || ''));
    if (durmus && d.acik) bilgi = _t('yedek.saat-duruyor');
    else if (d.zamanlama && d.acik && zb.kurulu && zb.sonraki) bilgi = _t('yedek.saat-sonraki', { zaman: _sonraki(zb.sonraki) });
    else if (d.zamanlama && d.acik && !zb.kurulu) bilgi = _t('yedek.saat-kurulu-degil');
    else bilgi = _t('yedek.saat-not');
    return '<div class="yb-cetvel yb-blok"><span class="yb-et">' + _t('yedek.d-otomatik') + '</span>'
      + '<label class="yb-anahtar" title="' + _esc(_ydt(d.acik ? 'yedek.acik' : 'yedek.kapali')) + '">'
      + '<input type="checkbox" id="y-acik"' + (d.acik ? ' checked' : '') + (!bag || _mesgul.ayar ? ' disabled' : '')
      + ' aria-label="' + _esc(_ydt('yedek.d-otomatik')) + '"><span class="yb-iz" aria-hidden="true"></span></label></div>'
      + '<div class="yb-cetvel yb-blok"><label class="yb-et" for="y-saat">' + _t('yedek.her-gun-saat') + '</label><div class="yb-sira">'
      + '<input class="girdi girdi-dar" id="y-saat" type="time" value="' + _esc(d.zamanlama || '') + '"' + (!bag ? ' disabled' : '') + '>'
      + _dugme('saat', 'dg-ikincil', 'yedek.kaydet', !bag) + '</div>'
      + (_sonMesaj && _sonMesaj.yer === 'saat'
        ? '<p id="y-mesaj" class="yb-kucuk yb-saat-mesaj' + (_sonMesaj.hata ? ' hata' : '') + '" role="status"' + (_sonMesaj.hata ? ' data-hata="1"' : '') + '>'
          + _vurgu(_ydt(_sonMesaj.anahtar, _sonMesaj.degerler)) + '</p>' : '')
      + '<p class="yb-kucuk">' + bilgi + '</p></div>'
      + _driveBlok().replace('class="yb-blok"', 'class="yb-cetvel yb-blok"')
      + _googleBlok().replace('class="yb-blok"', 'class="yb-cetvel yb-blok"');
  }

  /* Kadran: sonraki yedeğe kalan süre (gün yayı). 30 günlük nokta halkası YOK — oss geçmiş tutmuyor, uydurulmaz. */
  function _kalan(ms) {
    var dk = Math.max(0, Math.round(ms / 60000));
    return dk >= 60 ? _ydt('yedek.d-sa', { n: Math.floor(dk / 60) }) : _ydt('yedek.d-dk', { n: dk });
  }
  function _kadran(h) {
    var d = _durum, zb = d.zamanlama_bilgi || {}, etiket = 'yedek.d-sonraki', sayi = '', alt = '', oran = 0, kapali = false;
    if (d.calisiyor) {
      var c = d.canli || {};
      etiket = 'yedek.d-suruyor'; sayi = _sayi((c.yuklenen || 0) + (c.guncellenen || 0));
      alt = _ydt('yedek.d-dosya-gitti', { boyut: _boyut(c.bayt || 0) }); oran = 1;
    } else if (d.acik && zb.kurulu && zb.sonraki && !isNaN(new Date(zb.sonraki))) {
      var ms = new Date(zb.sonraki).getTime() - Date.now();
      sayi = _kalan(ms); alt = _sonraki(zb.sonraki);
      oran = Math.min(1, Math.max(0, 1 - ms / 86400000));
    } else {
      kapali = true; sayi = '—';
      alt = _ydt(!d.acik ? 'yedek.d-kapali' : 'yedek.d-saat-yok');
    }
    var cevre = 2 * Math.PI * 86, yay = (oran * cevre).toFixed(1);
    var renk = { iyi: 'iyi', uyari: 'uyari', kritik: 'kritik' }[h.isik] || 'mor';
    return '<div class="yb-kadran ' + renk + (d.calisiyor ? ' suruyor' : '') + '">'
      + '<svg viewBox="-100 -100 200 200" aria-hidden="true" focusable="false">'
      + '<circle class="yb-kd-iz" r="86"/>'
      + '<circle class="yb-kd-yay" r="86" transform="rotate(-90)" stroke-dasharray="' + yay + ' ' + cevre.toFixed(1) + '"/></svg>'
      + '<div class="yb-kd-merkez"><span class="yb-kd-etiket">' + _t(etiket) + '</span>'
      + '<span class="yb-kd-sayi' + (kapali ? ' kapali' : '') + '">' + _esc(sayi) + '</span>'
      + '<span class="yb-kd-alt">' + _esc(alt) + '</span></div></div>';
  }

  /* Akış: canlı tur · planlı sonraki yedek · son tur (oss yalnız SON turu saklar). */
  function _akis() {
    var d = _durum, t = d.son_tur, zb = d.zamanlama_bilgi || {}, h = '';
    if (d.calisiyor) {
      var c = d.canli || {};
      h += '<div class="yb-olay canli"><span class="yb-nk"></span><span class="yb-z">' + _t('yedek.d-simdi') + '</span>'
        + '<span class="yb-m">' + _t('yedek.suruyor-alt') + (c.yuklenen + c.guncellenen > 0
          ? ' ' + _t('yedek.suruyor-sayac', { n: _sayi(c.yuklenen + c.guncellenen), boyut: _boyut(c.bayt) }) : '') + '</span>'
        + '<span class="yb-sag">' + _t('yedek.d-et-suruyor') + '</span></div>';
    }
    if (!d.calisiyor && d.acik && zb.kurulu && zb.sonraki) {
      h += '<div class="yb-olay gelecek"><span class="yb-nk"></span><span class="yb-z">' + _esc(_sonraki(zb.sonraki)) + '</span>'
        + '<span class="yb-m">' + _t('yedek.d-planli') + '</span>'
        + '<span class="yb-sag">' + _esc(_kalan(new Date(zb.sonraki).getTime() - Date.now())) + '</span></div>';
    }
    if (t && t.bitti) {
      var tur = t.hata ? 'e' : (_uyariVar(t) ? 'k' : '');
      /* Hatalı turda ham hata cümlesi TEKRARLANMAZ (hüküm şeridi + "ne yapmalı" kutusu onu söyler) — yalnız kısa etiket */
      var gitti = (t.yuklenen || 0) + (t.guncellenen || 0);
      var m = t.hata ? _t('yedek.yarida-baslik') + (gitti ? ' · ' + _t('yedek.hata-gitti', { n: _sayi(gitti) }) : '')
        : ((t.yuklenen || t.guncellenen)
          ? _t('yedek.iyi-degisen', { yeni: _sayi(t.yuklenen), gunc: _sayi(t.guncellenen), boyut: _boyut(t.bayt) })
          : _t('yedek.iyi-degisen-yok'));
      h += '<div class="yb-olay ' + tur + '"><span class="yb-nk"></span>'
        + '<span class="yb-z">' + _esc(_zaman(t.bitti)) + '<small>' + _t(t.tetik === 'elle' ? 'yedek.d-tetik-elle' : 'yedek.d-tetik-oto') + '</small></span>'
        + '<span class="yb-m">' + m + '</span>'
        + '<span class="yb-sag">' + (t.saniye != null ? _t('yedek.d-sure', { n: _sayi(Math.max(1, Math.round(t.saniye))) }) : '') + '</span></div>';
    }
    if (!h) h = '<p class="yb-akis-bos">' + _t('yedek.d-akis-bos') + '</p>';
    var son = d.son_yedek || (t && !t.hata && t.bitti);
    return '<section class="yb-akis" aria-labelledby="yb-akis-bas"><div class="yb-bolum-bas"><h3 id="yb-akis-bas">' + _t('yedek.d-akis') + '</h3>'
      + (son ? '<span class="yb-kucuk">' + _t('yedek.d-akis-son', { zaman: _zaman(son) }) + '</span>' : '') + '</div>'
      + '<div class="yb-olaylar">' + h + '</div></section>';
  }

  function _guven() {
    return '<p class="yb-guven">' + _t('yedek.anahtar-girmez') + ' ' + _t('yedek.silmez') + '</p>';
  }

  /* Oda: üst çubuk + gövde. `.oda-baslik` = "Drive" (kişiseldeki gibi); amaç cümlesi üst çubukta ince yol satırı. */
  function _oda(icerik) {
    return '<div class="oda yb-oda yb-drive"><h2 class="gorsel-gizli">' + _t('hq.menu.yedekleme') + '</h2>'
      + '<header class="yb-cubuk"><h3 class="oda-baslik yb-cubuk-ad">' + _t('yedek.d-ust-ad') + '</h3>'
      + '<span class="yb-cubuk-yol" title="' + _esc(_ydt('yedek.amac').replace(/\*\*/g, '')) + '">' + _t('yedek.d-ust-yol') + '</span>'
      + (_R() ? _R().ustCubuk() : '') + '</header>'
      + '<div class="oda-govde yb-govde">' + icerik + '</div>' + (_R() ? _R().pencere() : '') + '</div>';
  }

  /* Hüküm şeridi tek başına (kapı hâlleri: oturum kilitli · ulaşılamadı) */
  function _tekSerit(isik, serit, baslik, alt, ana) {
    return _serit({ isik: isik, serit: serit, baslik: baslik, alt: alt, ana: ana });
  }

  /* BULUTTA / AYARLAR sekmeleri + Kontrol et / Kuru çalıştır → js/yedek-rclone.js (karar 11-15). */
  function _R() { return window.YedekRclone || null; }

  function _icerik() {
    var r = _R() && _R().govde();
    if (r != null) return '<div class="yb-r-sayfa" role="tabpanel">' + r + '</div>';
    if (!_durum || _durum.kilitli || _durum.cok_istek || _durum.hata) {
      var sebep = !_durum ? 'google.yukiye-ulasilamadi' : _durum.kilitli ? 'hq.oturum-kilitli'
        : _durum.cok_istek ? 'google.cok-sik' : 'yedek.durum-hata';
      return '<div class="yb-tek">' + _tekSerit('uyari', '', 'yedek.okunamadi-baslik', _ydt(sebep),
        { eylem: 'tazele', sinif: 'dg-ikincil', anahtar: 'google.yeniden-dene' }) + '</div>';
    }
    var h = _hukum();
    var sol = _kadran(h) + _serit(h) + _mesajKutusu();
    (h.neden || []).forEach(function (n) { sol += _nedenHtml(n); });

    var kartlar = '';
    /* En ağır klasör ÖNCE (telefonda ilk ekranda kırmızı kart görünsün); eşitlikte özgün sıra */
    var agirlik = { kritik: 0, uyari: 1, olculemedi: 2, kurulum: 3, iyi: 4 };
    (_durum.kaynaklar || []).map(function (k, i) { return { k: k, i: i, a: agirlik[_kartDurum(k).isik] }; })
      .sort(function (x, y) { return (x.a - y.a) || (x.i - y.i); })
      .forEach(function (x) { kartlar += _kart(x.k); });
    if (_durum.yuki_verisi === false) kartlar += _yukiKapaliKarti();
    kartlar += _ekleKarti();

    return '<div class="yb-izgara"><aside class="yb-yan">' + sol + _yan() + '</aside>'
      + '<div class="yb-ana">' + _akis() + '</div>'
      + '<section class="yb-klasorler" aria-labelledby="yb-klasor-bas"><div class="yb-bolum-bas"><h3 id="yb-klasor-bas">' + _t('yedek.d-klasorler') + '</h3>'
      + '<span class="yb-kucuk">' + _t('yedek.d-klasor-say', { n: _sayi((_durum.kaynaklar || []).length) }) + '</span></div>'
      + '<div class="yb-kartlar">' + kartlar + '</div>' + _guven() + '</section></div>';
  }

  /* Yeniden çizim yazıyı, odağı ve kaydırmayı KORUR — yoklama (2 sn) eskiden formu siliyordu (tur 1'de ölçüldü). */
  function ciz() {
    var k = _el();
    if (!k) return;
    _cizildi = true;
    var taslak = {}, odak = null;
    ['y-saat', 'y-yol'].forEach(function (id) {
      var e = document.getElementById(id);
      if (e) taslak[id] = e.value;
    });
    var a = document.activeElement;
    if (a && a.id && k.contains && k.contains(a)) odak = { id: a.id, bas: a.selectionStart, son: a.selectionEnd };
    var govde = k.querySelector ? k.querySelector('.yb-govde') : null;
    var kay = govde ? govde.scrollTop : 0;

    k.innerHTML = _oda(_icerik());

    Object.keys(taslak).forEach(function (id) {
      var e = document.getElementById(id);
      if (e && taslak[id] != null) e.value = taslak[id];
    });
    var yeni = k.querySelector ? k.querySelector('.yb-govde') : null;
    if (yeni && kay) yeni.scrollTop = kay;
    if (odak) {
      var o = document.getElementById(odak.id);
      if (o && o.focus) { try { o.focus(); if (odak.bas != null && o.setSelectionRange) o.setSelectionRange(odak.bas, odak.son); } catch (e) { /* tarih/saat alanı seçim kabul etmez */ } }
    }
    /* Ölçü çubuğunun genişliği DOM özelliğiyle (`style=` metni yasak) */
    if (k.querySelectorAll) Array.prototype.forEach.call(k.querySelectorAll('.yb-olcu > i'), function (i) {
      i.style.width = (i.dataset.oran || 0) + '%';
    });
  }

  function _mesaj(anahtar, hata, degerler) {
    _sonMesaj = anahtar ? { anahtar: anahtar, degerler: degerler, hata: !!hata } : null;
    var m = document.getElementById('y-mesaj');
    if (!m) return;
    m.innerHTML = anahtar ? _vurgu(_ydt(anahtar, degerler)) : '';
    if (hata) m.dataset.hata = '1'; else delete m.dataset.hata;
  }

  /* Ortak ret okuma: 401 = bizim oturum kilidi · 429 = çok sık · ağ = Yuki'ye ulaşılamadı.
     400/404/409'un `detail`'i backend'in MÜŞTERİ dilindeki cümlesidir (katalog) — aynen gösterilir;
     başka her şeyde ham metin ekrana ÇIKMAZ. */
  function _retMesaji(r, d, yedek) {
    if (!r) return { anahtar: 'google.yukiye-ulasilamadi', hata: true };
    if (r.status === 401) return { anahtar: 'google.oturum-kilitli-eylem', hata: true };
    if (r.status === 429) return { anahtar: 'google.cok-sik', hata: true };
    if ((r.status === 400 || r.status === 404 || r.status === 409) && d && typeof d.detail === 'string') {
      return { anahtar: 'yedek.ham', degerler: { metin: d.detail }, hata: true };
    }
    return { anahtar: yedek, hata: true };
  }
  function _hata(r, d, yedek) {
    var m = _retMesaji(r, d, yedek);
    _sonMesaj = { anahtar: m.anahtar, degerler: m.degerler, hata: true };
  }

  // ── Eylemler ────────────────────────────────────────────────────────────────
  async function _istek(yol, secenek) {
    var r = null, d = {};
    try {
      r = await _fetch(yol, secenek);
      d = await r.json().catch(function () { return {}; });
    } catch (e) { r = null; }
    return { r: r, d: d };
  }

  function _ayarYaz(govde, basari) {
    return _tekUcus('ayar', async function () {
      var x = await _istek(UC + '/ayar', {
        method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(govde)
      });
      if (!x.r || !x.r.ok) { _hata(x.r, x.d, 'yedek.kaydedilemedi'); return false; }
      _durum = x.d;
      _sonMesaj = basari ? basari(x.d) : null;
      return true;
    });
  }

  function saatKaydet() {
    var v = ((document.getElementById('y-saat') || {}).value || '').trim();
    return _ayarYaz({ zamanlama: v }, function (d) {
      /* 🔴 "kuruldu" yalnız GERÇEKTEN kuruluysa: kapalıyken ya da zamanlayıcı yokken iş kurulmaz. */
      if (!v) return { anahtar: 'yedek.saat-elle', yer: 'saat' };
      if (!d.acik) return { anahtar: 'yedek.saat-kapali', yer: 'saat' };
      var zb = d.zamanlama_bilgi || {};
      if (!zb.kurulu) return { anahtar: 'yedek.saat-kurulamadi', hata: true, yer: 'saat' };
      return { anahtar: 'yedek.saat-kuruldu', yer: 'saat', degerler: { saat: v, zaman: zb.sonraki ? _sonraki(zb.sonraki) : '' } };
    });
  }

  function klasorEkle(yol) {
    yol = (yol || '').trim();
    if (!yol) return Promise.resolve();
    return _tekUcus('ekle', async function () {
      var x = await _istek(UC + '/kaynak', {
        method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ yol: yol })
      });
      if (!x.r || !x.r.ok) { _hata(x.r, x.d, 'yedek.klasor-eklenemedi'); return; }
      _durum = x.d.durum;
      _sonMesaj = { anahtar: 'yedek.klasor-eklendi' };
      var yolAlani = document.getElementById('y-yol');
      if (yolAlani) yolAlani.value = '';
    });
  }

  function klasorSec() {
    return _tekUcus('ekle', async function () {
      /* Native diyalog: kullanıcı yolu YAZMAZ, seçer. */
      var s = null;
      try { s = await window.yukiDosya.klasorSec(); }
      catch (e) { _sonMesaj = { anahtar: 'yedek.klasor-secilemedi', hata: true }; return; }
      if (!s || !s.yol) return;
      var x = await _istek(UC + '/kaynak', {
        method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ yol: s.yol })
      });
      if (!x.r || !x.r.ok) { _hata(x.r, x.d, 'yedek.klasor-eklenemedi'); return; }
      _durum = x.d.durum;
      _sonMesaj = { anahtar: 'yedek.klasor-eklendi' };
    });
  }

  function kaldir(id, onayli) {
    /* ⚠️ `confirm()` KULLANILMAZ. İki adımlı tık: ilk tık düğmeyi "Emin misin?"e çevirir (4 sn).
       Kaldırmak Drive'daki dosyaları SİLMEZ — yalnız izlemeyi bırakır; not bunu söyler. */
    if (!onayli) {
      _silOnay = id;
      clearTimeout(_silSayac);
      _silSayac = setTimeout(function () { if (_silOnay) { _silOnay = null; ciz(); } }, 4000);
      ciz();
      return Promise.resolve();
    }
    return _tekUcus('sil:' + id, async function () {
      clearTimeout(_silSayac);
      var x = await _istek(UC + '/kaynak/' + encodeURIComponent(id), { method: 'DELETE' });
      _silOnay = null;
      if (!x.r || !x.r.ok) { _hata(x.r, x.d, 'yedek.kaldirilamadi'); return; }
      _durum = x.d.durum;
      _sonMesaj = null;
    });
  }

  function simdi() {
    return _tekUcus('simdi', async function () {
      _sonMesaj = { anahtar: 'yedek.baslatildi' };
      var x = await _istek(UC + '/calistir', { method: 'POST' });
      if (!x.r || !x.r.ok) { _hata(x.r, x.d, 'yedek.baslatilamadi'); return; }
      _sonMesaj = null;
      var yeni = await durumAl();
      if (yeni && hazir(yeni)) _durum = yeni;
      _yoklamaBaslat();
    });
  }
  function hazir(d) { return d && !d.kilitli && !d.cok_istek && !d.hata; }

  function tazele() {
    return _tekUcus('tazele', async function () {
      _durum = await durumAl();
      ciz();
      if (_hazirMi() && _durum.calisiyor) _yoklamaBaslat();
      if (_hazirMi() && (_gd() === 'bagli' || _gd() === 'denenmedi')) driveOku(false);
    });
  }

  /* Tur arka planda koşar (uç hemen döner) → ilerleme yoklanır.
     ⚠️ Yoklama panel kapanınca DURUR: `offsetParent` denetimi HQ monitörünün dersi —
        `switchHqTab` panel kapanışını haber vermez. */
  function _yoklamaBaslat() {
    if (_yoklama) return;
    _yoklamaBos = 0;
    _yoklama = setInterval(async function () {
      var k = _el();
      if (!k || !k.offsetParent) { _yoklamaDurdur(); return; }
      var d = await durumAl();
      if (!d) return;
      if (!hazir(d)) { _durum = d; _yoklamaDurdur(); ciz(); return; }
      /* Tur henüz başlamadıysa ("çalışmıyor" ilk iki cevapta) bitmiş sayılmaz */
      if (!d.calisiyor && _yoklamaBos < 2 && !(_durum && _durum.calisiyor)) { _yoklamaBos++; return; }
      _durum = d;
      if (!d.calisiyor) {
        _yoklamaDurdur();
        var t = d.son_tur || {};
        if (!t.hata && t.tam !== false) _sonMesaj = { anahtar: 'yedek.bitti', degerler: { yeni: t.yuklenen || 0, gunc: t.guncellenen || 0 } };
        else _sonMesaj = null;
        ciz();
        /* Drive doluysa ya da tur Drive'ı değiştirdiyse ölçü tazelenir (sessiz: "okunuyor" yanıp sönmez) */
        if (_gd() === 'bagli' || _gd() === 'denenmedi') driveOku(true);
        return;
      }
      ciz();
    }, 2000);
  }

  function _yoklamaDurdur() {
    if (_yoklama) { clearInterval(_yoklama); _yoklama = null; }
  }

  function _olay(e) {
    var b = e.target && e.target.closest && e.target.closest('[data-y]');
    var k = _el();
    if (!b || !k || !k.contains(b) || b.disabled) return;
    var y = b.dataset.y;
    if (y.indexOf('r-') === 0) { if (_R()) _R().olay(y, b); return; }
    if (y === 'simdi') simdi();
    else if (y === 'ac') _ayarYaz({ acik: true });
    else if (y === 'saat') saatKaydet();
    else if (y === 'ekle') klasorSec();
    else if (y === 'ekle-yol') klasorEkle((document.getElementById('y-yol') || {}).value);
    else if (y === 'sil') kaldir(b.dataset.id, _silOnay === b.dataset.id);
    else if (y === 'drive') driveOku(false);
    else if (y === 'yuki-ac') _ayarYaz({ yuki_verisi: true });
    else if (y === 'tazele') tazele();
    else if (y === 'google') {
      /* Google paneli HQ'da: önce sekmeyi değiştir, sonra paneli seç (hqGoto). */
      window._hqHedefPanel = 'google';
      if (typeof window.switchTab === 'function') window.switchTab('hq');
      else if (typeof window.switchHqTab === 'function') window.switchHqTab('google');
    }
    else if (y === 'rehber') window.open('/ui/docs/google-kurulum.html', '_blank');
  }

  function _olaylariBagla() {
    var k = _el();
    if (_olayBagli || !k) return;
    _olayBagli = true;
    k.addEventListener('click', _olay);
    k.addEventListener('input', function (e) { if (_R()) _R().girdi(e); });
    k.addEventListener('keydown', function (e) { if (_R()) _R().tus(e); });
    k.addEventListener('change', function (e) {
      var h = e.target;
      if (h && h.id === 'y-acik') _ayarYaz({ acik: !!h.checked });
    });
    /* Enter alanlarda ilgili düğmeye basar — form etiketi yok (innerHTML yeniden çizimi submit'i kaçırırdı) */
    k.addEventListener('keydown', function (e) {
      if (e.key !== 'Enter' || !e.target) return;
      if (e.target.id === 'y-saat') { e.preventDefault(); saatKaydet(); }
      else if (e.target.id === 'y-yol') { e.preventDefault(); klasorEkle(e.target.value); }
    });
  }

  /* Panel her açılışta tazelenir (`switchHqTab` → önbellek YOK: tur panel dışında ilerler). */
  window.yedeklemePanelAc = function () {
    _olaylariBagla();
    _sonMesaj = null; _silOnay = null; _drive = null;
    if (_R()) _R().sifirla();
    _yoklamaDurdur();
    return tazele();
  };
  window.yedeklemeTazele = tazele;
  window.yedeklemeCiz = function () { if (_cizildi) ciz(); };

  /* ── Dil tazeleyici ──────────────────────────────────────────────────
     Panel AÇIKSA son durumdan yeniden çizer — ağa gitmez; yazı, odak ve mesaj (anahtar olarak
     saklı, yeni dilde yeniden üretilir) korunur. Panel hiç açılmadıysa dokunmaz. */
  window.addEventListener('yuki-dil-degisti', function () {
    if (!_cizildi || !_el()) return;
    ciz();
  });
})();
