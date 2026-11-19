/* ============================================================================
   YUKI · DİL ANAHTARI  (2026-09-18 — FAZ 2, i18n iskelesi)

   `tema.js`'in kardeşi: aynı sözleşme (`al` · `ayarla` · `secenekler`), aynı
   yükleme kuralı. Değerler sözlüklerde (`js/diller/*.js`), burada YALNIZ
   seçim + kalıcılık + yayma + çeviri mantığı var.

   🔴 Bu dosya <head>'de, sözlüklerden SONRA, SENKRON yüklenir. Sebebi FOUT:
   defer/async olsaydı ilk kare Türkçe basılır, sonra çevrilirdi — İngilizce
   kullanıcı her açılışta gözüne bir Türkçe flaş yer. `tema.js:7-9`'daki FOUC
   gerekçesinin birebir aynısı.

   ── 🔑 TEMADAN TEK FARKI: OTORİTE KİMDE ─────────────────────────────────
   Temanın gerçeği localStorage'dır. Dilin gerçeği **backend**'dir
   (`config.user.json` → `ARAYUZ_DILI`) — çünkü backend'in ekran metni
   (`mesajlar.M()`) ve Electron kabuğu da aynı kaydı okuyor; localStorage'ı
   onlar göremez.

   ── 🔑 İKİ EKSEN (2026-10-04, geliştirici) ───────────────────────────────────
   ARAYÜZ dili (tr/en) ≠ KONUŞMA dili (tr/en/ja). Japonca konuşan kullanıcının
   ekranı seçtiği TR/EN'de kalır. Bu dosyanın `_aktif`'i ARAYÜZ dilidir;
   `_konusma` yalnız backend'in konuşma kaydının AYNASIDIR (saklanmaz, ekranı
   sürmez). 09-18'in tek eksen kararı geçersiz.

   Buradaki localStorage bir ÖNBELLEKTİR, ikinci bir kaynak değil: ilk kare
   backend'e soramaz (o çağrı async'tir), o yüzden son bilinen dille çizer.
   `core.js::initLanguageSelector` açılışta gerçeği sorar ve ayrışma varsa
   **backend kazanır**. Bunu "iki sistem" sanıp ikisini eşit otorite yapmak,
   `tema.js`'in eski `data-theme`/`data-tema` arızasının dil hâli olurdu.

   ── Her eksenin TEK KAPISI ──────────────────────────────────────────────
   Arayüz: `ayarla()` (→ backend `config.set_arayuz_dili`).
   Konuşma: `konusmaAyarla()` (→ backend `config.set_language`).
   `core.js` seçicileri ve AYAR yalnız bunlardan geçer; `/api/language`'e POST
   yazan ikinci bir yol, diskle ekranın ayrışması demektir.
   ========================================================================= */
(function () {
  'use strict';

  var ANAHTAR = 'yukiDil_v1';
  var KAYNAK = 'tr';   // eksik çeviri buraya düşer

  /* Dile özel yedek zinciri (FAZ 3).
     `ja` sözlüğü bilerek KISMİ: kapsam kararı "yalnız en" (2026-09-18, geliştirici)
     ve Japonca'yı bu turda ölçemiyoruz — 300 satır uydurmak, eksikliği
     kaydetmekten kötüdür. Ama eksik anahtarda düz `tr`'ye düşmek Japonca
     konuşan kullanıcıya TÜRKÇE gösterirdi; İngilizce'ye düşmek hem daha
     okunur hem daha dürüst. Zincir bu yüzden dile göre ayarlanabilir. */
  var YEDEK = { ja: ['en'] };

  /* 🔑 YALNIZ KONUŞMA dilleri (2026-10-04): arayüzü YOK, karşılığı yanında.
     `ja.js` yüklü kalıyor (4 anahtar, ratchet testi) ama arayüz dili olamaz —
     menüde Japonca arayüz vaadi yarım bir dil vaadiydi. Eski önbellekte `ja`
     duran kurulum ilk karede bugün gördüğünü (`en`) görür; backend göçüyle aynı
     kural (`config._arayuz_karsiligi`). */
  var YALNIZ_KONUSMA = { ja: 'en' };

  /* Geçerli diller SÖZLÜKLERDEN türetilir — ikinci bir liste tutulmaz.
     Elle yazılsaydı dördüncü dil eklendiğinde burası unutulur ve dil
     "kayıtlı ama seçilemez" olurdu (backend'de `set_language` çalışıp araç
     şemasının enum'unun geride kalmasıyla aynı kusur sınıfı). */
  function sozlukler() { return window.YukiSozluk || {}; }
  function gecerliMi(kod) { return !!(kod && sozlukler()[kod] && !YALNIZ_KONUSMA[kod]); }

  var _aktif = KAYNAK;
  /* Konuşma dili — backend kaydının aynası; `sunucudan()`/yanıtlar günceller. */
  var _konusma = null;
  var _konusmaListesi = [];
  /* `/api/language`'in `available` listesi (ad + bayrak orada yaşar).
     Boş başlar; `core.js::initLanguageSelector` açılışta doldurur. */
  var _sunucuListesi = [];

  function oku() {
    try {
      var k = localStorage.getItem(ANAHTAR);
      if (YALNIZ_KONUSMA[k]) k = YALNIZ_KONUSMA[k];
      if (gecerliMi(k)) return k;
    } catch (e) {}
    return KAYNAK;
  }

  /* ── Çeviri ───────────────────────────────────────────────────────────
     Eksik anahtarda sırayla: aktif dil → kaynak dil (tr) → anahtarın kendisi.
     Anahtarı döndürmek bilinçli: boş string dönseydi eksik çeviri "kayıp
     metin" olarak görünür ve ekrana bakan kimse sebebini anlayamazdı.
     Anahtar görünürse kusur kendini söyler. */
  function t(anahtar, degerler) {
    var s = sozlukler();
    var metin = (s[_aktif] && s[_aktif][anahtar]);
    var zincir = (YEDEK[_aktif] || []).concat([KAYNAK]);
    for (var i = 0; metin == null && i < zincir.length; i++) {
      metin = (s[zincir[i]] && s[zincir[i]][anahtar]);
    }
    if (metin == null) return String(anahtar);
    if (!degerler) return metin;
    return String(metin).replace(/\{(\w+)\}/g, function (tam, ad) {
      return Object.prototype.hasOwnProperty.call(degerler, ad) ? String(degerler[ad]) : tam;
    });
  }

  /* Sayıya bağlı metin — backend `mesajlar/__init__.py::Mc` ile BİREBİR aynı
     sözleşme: `n === 1` → `anahtar`, değilse `anahtar + '-cogul'`, o yoksa
     tekile düş. İki katmanın kuralı ayrışırsa aynı sayı backend mesajında
     "5 minutes", arayüzde "5 minute" olur ve kimse yan yana görmez.
     🔑 `-cogul` yalnız gereken dilde tanımlanır: Türkçe'de sayıdan sonra çoğul
     eki gelmez ("5 kayıt"), İngilizce'de gelir ("5 records"). */
  function tc(anahtar, sayi, degerler) {
    var d = degerler || {};
    if (d.n === undefined) d = Object.assign({}, d, { n: sayi });
    if (sayi !== 1) {
      var s = sozlukler();
      var zincir = [_aktif].concat(YEDEK[_aktif] || [], [KAYNAK]);
      for (var i = 0; i < zincir.length; i++) {
        if (s[zincir[i]] && s[zincir[i]][anahtar + '-cogul'] != null) {
          return t(anahtar + '-cogul', d);
        }
      }
    }
    return t(anahtar, d);
  }

  /* Tarih/saat/sayı biçimi için BCP-47 etiketi. `toLocale*` çağrılarına
     `'tr-TR'` yazmak metin çevrilse bile biçimi Türkçe bırakır — "15 Eyl 2026"
     İngilizce ekranda Türkçe bir ay adıdır (Blok 3'ün TR BİÇİM dersi).
     Eşleme burada TEK yerde; yeni dil eklenince yalnız bu satır büyür. */
  var YEREL = { tr: 'tr-TR', en: 'en-US', ja: 'ja-JP' };
  function yerel() { return YEREL[_aktif] || _aktif; }

  /* ── Çizici (FAZ 3) ───────────────────────────────────────────────────
     Statik markup'ın çeviri kancası. Dört öznitelik, üç kural:

       data-i18n="k"            → textContent = t(k)     (çocuğu OLMAYAN eleman)
       data-i18n-html="k"       → innerHTML   = t(k)      (cümle <b>/<a> ile kaynaşmış)
       data-i18n-<öznitelik>="k"→ setAttribute            (title/aria-label/placeholder/alt)
       data-i18n-yok            → çizici bu elemana DOKUNMAZ (metnini JS yazar)

     🔴 `data-i18n-html` yalnız SUNUMSAL satır-içi çocuğu olanda kullanılır.
     İçinde `id=`/`onclick=` taşıyan bir düğüm varsa `innerHTML` onu silerdi;
     `mon-cpu-temp` gibi JS'in doldurduğu her span bu yolla kaybolurdu. Ayrım
     mekanik kapıda: `test_faz3_html_kancasi_js_dugumu_silmiyor`.

     🔑 YAZDIĞINI HATIRLAR. `_yazilan` (WeakMap) çizicinin en son bastığı değeri
     tutar; eleman o değerden sapmışsa JS araya girmiştir ve çizici GERİ ÇEKİLİR.
     Bu olmasaydı `#mon-doctor-result` gibi bir alanda duran canlı sonuç, kullanıcı
     dil değiştirdiği an yerini yer tutucu metne bırakırdı — yani çeviri, veriyi
     silerdi. "Bir alanın tek bir sahibi olur" kuralının çizici tarafındaki hâli. */
  var OZNITELIKLER = ['title', 'aria-label', 'placeholder', 'alt', 'value', 'label'];
  var _yazilan = (typeof WeakMap === 'function') ? new WeakMap() : null;

  function _hatirla(el, alan, deger) {
    if (!_yazilan) return;
    var k = _yazilan.get(el) || {};
    k[alan] = deger;
    _yazilan.set(el, k);
  }

  function _sahibiBizMiyiz(el, alan, simdiki) {
    if (!_yazilan) return true;
    var k = _yazilan.get(el);
    // Hiç yazmadıysak eleman HTML'den geldiği gibi duruyor → bizimdir.
    return !k || !(alan in k) || k[alan] === simdiki;
  }

  function ciz(kok) {
    var k = kok || document;
    if (!k || !k.querySelectorAll) return;

    var i, el, liste, anahtar;

    liste = k.querySelectorAll('[data-i18n]');
    for (i = 0; i < liste.length; i++) {
      el = liste[i];
      if (el.hasAttribute('data-i18n-yok')) continue;
      if (!_sahibiBizMiyiz(el, 'metin', el.textContent)) continue;
      el.textContent = t(el.getAttribute('data-i18n'));
      _hatirla(el, 'metin', el.textContent);
    }

    liste = k.querySelectorAll('[data-i18n-html]');
    for (i = 0; i < liste.length; i++) {
      el = liste[i];
      if (el.hasAttribute('data-i18n-yok')) continue;
      if (!_sahibiBizMiyiz(el, 'html', el.innerHTML)) continue;
      el.innerHTML = t(el.getAttribute('data-i18n-html'));
      _hatirla(el, 'html', el.innerHTML);
    }

    for (var a = 0; a < OZNITELIKLER.length; a++) {
      var oz = OZNITELIKLER[a];
      liste = k.querySelectorAll('[data-i18n-' + oz + ']');
      for (i = 0; i < liste.length; i++) {
        el = liste[i];
        /* 🔴 `data-i18n-yok` denetimi BU DÖNGÜDE EKSİKTİ (2026-09-20).
           Metin ve HTML döngülerinde vardı, öznitelik döngüsünde yoktu — yani
           "çizici bu elemana DOKUNMAZ" beyanı `title`/`aria-label` için
           geçerli DEĞİLDİ. Bugün bunu tetikleyen bir eleman yoktu (ölçüldü:
           ikisini birden taşıyan 0 eleman), ama beyanın yarısının çalışması
           en kötü türden bir kusurdur: belge doğru, davranış değil. */
        if (el.hasAttribute('data-i18n-yok')) continue;
        anahtar = el.getAttribute('data-i18n-' + oz);
        if (!_sahibiBizMiyiz(el, oz, el.getAttribute(oz))) continue;
        el.setAttribute(oz, t(anahtar));
        _hatirla(el, oz, el.getAttribute(oz));
      }
    }
  }

  /* ── Uygula ───────────────────────────────────────────────────────────
     `kaydet`     → localStorage önbelleğini tazele
     `sunucuyaYaz`→ backend'e POST at (TEK yazma yolu buradan geçer)

     `sunucuyaYaz=false` şart: backend'den gelen `language_changed` olayını
     işlerken true olsaydı aynı değişikliği sunucuya geri yollardık — sonsuz
     gidiş-geliş. (`tema.js`'in `uygula(tema, kaydet)` desenine bir parametre
     ekliyor, sebebi de bu.) */
  function uygula(kod, kaydet, sunucuyaYaz) {
    if (!gecerliMi(kod)) kod = KAYNAK;
    _aktif = kod;

    /* `lang` özniteliği kozmetik değil: ekran okuyucu telaffuzu, tarayıcı
       yazım denetimi ve CSS `:lang()` bunu okur. */
    try {
      document.documentElement.setAttribute('lang', kod);
      document.documentElement.setAttribute('data-dil', kod);
    } catch (e) {}

    if (kaydet) {
      try { localStorage.setItem(ANAHTAR, kod); } catch (e) {}
    }

    /* Gövde varsa hemen çiz. İlk çağrıda (dosya <head>'de koşarken) gövde
       YOKTUR — o turu gövdenin sonundaki senkron çağrı yapar, ilk kareden
       önce. Buraya `DOMContentLoaded` beklemek konsaydı İngilizce kullanıcı
       her açılışta bir Türkçe flaş görürdü (`tema.js:7-9` FOUC gerekçesi). */
    try { if (document.body) ciz(document); } catch (e) {}

    // PLAN iframe'ine haber ver (ayrı belge — tema.js:49-52 deseni)
    try {
      var f = document.getElementById('planner-iframe');
      if (f && f.contentWindow) f.contentWindow.postMessage({ type: 'dil', dil: kod }, '*');
    } catch (e) {}

    /* 🔴 OLAY, SUNUCU YAZIMINDAN SONRA YAYINLANIR (FAZ 3 · Dalga 2, 09-19).

       Bu olayı dinleyenler `innerHTML` ile doğan panelleri yeniden çiziyor
       (`intro-sequences.js::_dilTazeleyici`) ve o panellerin bir kısmı içeriğini
       BACKEND'DEN çekiyor — sağlayıcı rehberi, ölçüm uyarıları, durum satırı.

       Eskiden yayın POST'tan ÖNCEYDİ ve bu bir YARIŞ üretiyordu: tazeleyici
       `/api/llm/key/status`'u çağırıyor, backend'in dili henüz değişmemiş
       oluyor ve panel ESKİ DİLDE veriyle doluyordu. Canlı turda ölçüldü —
       arayüz İngilizce'ye geçmişken sağlayıcı adı "Ollama (kendi bilgisayarın)"
       kalıyordu. Hata da vermiyordu: istek başarılıydı, yalnız erkendi.

       Yerel çizim (`ciz(document)`) yukarıda ve HÂLÂ HEMEN koşuyor, yani
       statik markup gecikmiyor — ertelenen tek şey JS panellerinin tazelenmesi.
       Sunucu yazımı düşerse de yayın yapılır: arayüzün dili değişmiş durumda,
       panelleri eski dilde bırakmak daha kötü olurdu. */
    function yayinla() {
      try {
        window.dispatchEvent(new CustomEvent('yuki-dil-degisti', { detail: { dil: kod } }));
      } catch (e) {}
    }

    if (sunucuyaYaz) {
      return sunucuyaGonder({ arayuz: kod }).then(function (y) {
        yayinla();
        return y;
      }, function (e) {
        yayinla();
        throw e;
      });
    }
    yayinla();
    return Promise.resolve({ ok: true, language: kod, yerel: true });
  }

  /* Backend'e yaz. `authFetch` core.js'te tanımlı ve bu dosyadan SONRA
     yüklenir; o yüzden çağrı anında bakılır, dosya başında değil.

     🔴 `authFetch` yoksa SESSİZCE `fetch`'e DÜŞMÜYORUZ. core.js:113-121 bu
     tuzağı adıyla anlatıyor: sekiz dosya `typeof window.authFetch === 'function'
     ? … : fetch` diye yedeğe düşüyor ve token'sız istek **hata vermeden 401**
     üretiyor — yani dil değişmemiş olur, kimse sebebini görmez. Burada açıkça
     söylüyoruz; yanlış "başarılı" yanıtı döndürmüyoruz.

     URL göreli: `/api/language`. core.js'teki `BASE_URL` bir `const` ve global
     nesneye YAZILMAZ (`window.BASE_URL` her zaman undefined) — ona bakan bir
     kontrol sessizce boş string kullanır, yani zaten göreli yol olurdu.
     Aynı origin olduğu için göreli yol doğru ve dürüst olanı. */
  function sunucuyaGonder(govde) {
    var f = window.authFetch;
    if (typeof f !== 'function') {
      console.warn('[dil] authFetch yok — dil sunucuya YAZILAMADI:', govde);
      return Promise.resolve({ ok: false, error: 'authFetch yok' });
    }
    try {
      return f('/api/language', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(govde)
      }).then(function (r) { return r.json(); }).then(function (y) {
        /* Yanıt iki ekseni taşır. Arayüz değişince konuşma da (ayrıca seçilmemişse)
           birlikte taşınmış olabilir — aynayı buradan tazele. */
        if (y && y.ok && y.language) konusmayiYansit(y.language);
        return y;
      });
    } catch (e) {
      return Promise.reject(e);
    }
  }

  /* Konuşma aynasını güncelle; değiştiyse YALNIZ konuşma olayını yay —
     arayüz yeniden çizilmez (Japonca'ya geçmek ekranı değiştirmez). */
  function konusmayiYansit(kod) {
    if (!kod || kod === _konusma) return;
    _konusma = kod;
    try {
      window.dispatchEvent(new CustomEvent('yuki-konusma-dili-degisti', { detail: { dil: kod } }));
    } catch (e) {}
  }

  // İlk boyamadan önce uygula (sunucuya yazmadan — bu bir okuma, seçim değil)
  uygula(oku(), false, false);

  // iframe tarafı: ebeveynden gelen dil mesajını dinle
  window.addEventListener('message', function (e) {
    if (e && e.data && e.data.type === 'dil') uygula(e.data.dil, true, false);
  });

  /* Emniyet ağı: gövde sonundaki senkron çağrı bir sayfada unutulursa
     (ör. yeni bir HTML dosyası eklenir) arayüz çevirisiz kalmasın. Geç
     kalması FOUT üretir ama SESSİZ KALMAKTAN iyidir — kapı testi ayrıca
     senkron çağrının varlığını denetliyor. */
  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', function () { ciz(document); });
  }

  window.YukiDil = {
    al: function () { return _aktif; },
    t: t,
    tc: tc,
    yerel: yerel,
    ciz: ciz,

    /* ARAYÜZ dili — kullanıcı seçimi, backend'e DE yazar. */
    ayarla: function (kod) { return uygula(kod, true, true); },

    /* KONUŞMA dili — kullanıcı seçimi. Ekranı DEĞİŞTİRMEZ; yalnız backend'e
       yazar ve aynayı tazeler (yanıt `mesaj` = Yuki'nin yeni dildeki onayı). */
    konusmaAyarla: function (kod) { return sunucuyaGonder({ language: kod }); },

    /* Aktif konuşma dili (backend aynası; açılış sorgusundan önce null). */
    konusma: function () { return _konusma; },

    /* Backend zaten değiştirdi (WS `language_changed`, sesli komut, başka bir
       istemci, açılış sorgusu): ekranı hizala ama geri yazma.
       `durum` = `{language, arayuz}` (`config.dil_durumu()`). Arayüz yalnız
       `arayuz` alanından okunur — `language` KONUŞMA dilidir; onu arayüze
       uygulamak 09-18 tek ekseninin arızasını geri getirirdi. */
    sunucudan: function (durum) {
      if (durum && typeof durum === 'object') {
        if (durum.language) konusmayiYansit(durum.language);
        if (!durum.arayuz) return Promise.resolve({ ok: true, yerel: true });
        if (durum.arayuz === _aktif) return Promise.resolve({ ok: true, language: _aktif, yerel: true });
        return uygula(durum.arayuz, true, false);
      }
      return uygula(durum, true, false);   // düz kod = arayüz kodu
    },

    /* tema.js ile aynı biçim: [{anahtar, ad, aciklama}].
       Liste `/api/language`'ten gelir; `core.js::initLanguageSelector` doldurur.
       Boşken de çalışır — o an yalnız yüklü sözlükler görünür. */
    secenekler: function () {
      var s = sozlukler();
      return (_sunucuListesi.length ? _sunucuListesi : Object.keys(s).filter(gecerliMi).map(function (k) {
        return { code: k, name: k.toUpperCase(), flag: '' };
      })).map(function (o) {
        return { anahtar: o.code, ad: o.name, aciklama: o.flag || '' };
      });
    },

    /* Konuşma seçenekleri (tr/en/ja) — `secenekler()` ile aynı biçim. */
    konusmaSecenekleri: function () {
      return _konusmaListesi.map(function (o) {
        return { anahtar: o.code, ad: o.name, aciklama: o.flag || '' };
      });
    },

    /* `/api/language` listelerini sakla: `arayuzListesi` → arayüz (tr/en),
       `konusmaListesi` → konuşma (tr/en/ja). */
    listeyiKur: function (konusmaListesi, arayuzListesi) {
      if (Array.isArray(konusmaListesi) && konusmaListesi.length) _konusmaListesi = konusmaListesi;
      if (Array.isArray(arayuzListesi) && arayuzListesi.length) {
        _sunucuListesi = arayuzListesi.filter(function (o) { return gecerliMi(o.code); });
      }
    },

    /* Hata ayıklama: eksik çeviri avı. */
    eksikler: function (kod) {
      var s = sozlukler(), hedef = s[kod || _aktif] || {}, kaynak = s[KAYNAK] || {};
      return Object.keys(kaynak).filter(function (k) { return !(k in hedef); });
    }
  };
})();
