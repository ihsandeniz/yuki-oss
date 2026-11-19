(function(){
  var BASE = (typeof BASE_URL !== 'undefined' && BASE_URL) ? BASE_URL : '';
  function af(url, opts){ return (typeof authFetch==='function'?authFetch:fetch)(BASE+url, opts||{}); }
  function esc(s){ return String(s==null?'':s).replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;').replace(/"/g,'&quot;'); }

  /* ── Çeviri (FAZ 3 · Dalga 2, 2026-09-19) ─────────────────────────────────
     `index.html`'in çapaları (`data-i18n`) buraya ULAŞMAZ: bu dosyanın metni
     `innerHTML` şablonlarının içinde doğuyor, yani çizici onu göremez. JS'in
     kancası bu fonksiyondur ve her çağrı yeri ELLE sarılır.

     🔴 `YukiDil` yoksa anahtarı döndürüyoruz — boş string DEĞİL. Sebebi
     `dil.js::t`'nin aynısı: eksik çeviri "kayıp metin" olarak görünürse
     ekrana bakan kimse sebebini anlamaz, anahtar görünürse kusur kendini
     söyler. Yedeğe düşmek sessizleştirmekten kötü olurdu.

     ⚠️ Bu dosyada üç yerde `t` bir YEREL değişkendi (kademe nesnesi, terminal
     kimliği, yetki listesi) ve orada çeviri çağrısı gölgelenirdi — hata
     vermeden, `t is not a function` bile demeden, çünkü o kapsamda `t`
     gerçekten vardı. Üçü yeniden adlandırıldı; adı burada tekilleştirmek
     `core.js`/`map-engine.js` sıradaki dalgalarda aynı deseni kullanacağı
     için ayrıca gerekliydi. */
  function t(anahtar, degerler){
    return (window.YukiDil && window.YukiDil.t)
      ? window.YukiDil.t(anahtar, degerler) : String(anahtar);
  }

  /* Sayıya bağlı metin (`dil.js::tc` — backend `Mc` ile aynı sözleşme).
     "1 kayıt gösteriliyor" TR'de de EN'de de doğru; "5 record shown" değil. */
  function tc(anahtar, sayi, degerler){
    return (window.YukiDil && window.YukiDil.tc)
      ? window.YukiDil.tc(anahtar, sayi, degerler) : String(anahtar);
  }

  /* Tarih/saat biçimi etiketi. `'tr-TR'` yazmak metin çevrilse bile ay adını
     Türkçe bırakır — biçim de çeviriye dahildir. */
  function yerelKod(){
    return (window.YukiDil && window.YukiDil.yerel) ? window.YukiDil.yerel() : 'tr-TR';
  }

  // ── Hata yanıtı okuma — müşteriye ham teknik metin GÖSTERİLMEZ (2026-08-04) ──
  // Eskiden: 500 düz metin "Internal Server Error" dönüyordu, r.json() patlıyordu,
  // catch bloğu String(e)'yi basıyordu → müşteri "SyntaxError: Unexpected token 'I'…"
  // görüyordu. 429'da ise slowapi'nin İngilizce metni **geçersiz anahtar** sanılıyordu
  // (yanlış teşhis: müşteri sağlam anahtarını çöpe atar). Backend eşi: app/hata_yaniti.py.
  // Dönüş: {ok, kod, error, message, ...} — gövde JSON değilse insanca TR cümle üretilir.
  async function apiJson(r){
    var govde = null;
    try{ govde = await r.json(); }catch(_){ govde = null; }
    if(govde && typeof govde === 'object'){
      if(govde.ok === undefined) govde.ok = r.ok;
      // Emniyet ağı: 429'u DURUM KODUNDAN tanı, gövdenin metnine güvenme.
      // Delta güncellemede frontend ile backend farklı sürümde kalabiliyor —
      // eski backend hâlâ ham "Rate limit exceeded: 10 per 1 minute" döner ve
      // bu metin müşteriye "anahtarın geçersiz" diye okunur. Kod her sürümde doğru.
      if(r.status === 429){
        govde.ok = false;
        govde.kod = govde.kod || 'hiz_siniri';
        if(!govde.error || /rate limit/i.test(govde.error)){
          govde.error = t('hata.hiz-siniri');
        }
      }
      return govde;
    }
    // JSON değil → durum kodundan insanca sebep türet
    var m = t('hata.yanit-okunamadi', {kod: r.status, yol: t('hata.gunluk-yolu')});
    if(r.status===401 || r.status===403) m = t('hata.yetki-reddedildi');
    else if(r.status===404) m = t('hata.uc-bulunamadi');
    else if(r.status>=500) m = t('hata.sunucu', {yol: t('hata.gunluk-yolu')});
    return { ok:false, kod:'yanit_okunamadi', error:m };
  }

  // Ağ/istisna → kullanıcının dilinde cümle (FAZ 3 · Dalga 2'den beri; eskiden
  // sabit TR'ydi). `String(e)` ASLA basılmaz (TypeError: Failed to fetch…).
  function agHatasi(e){
    try{ console.error('[yuki] istek hatası:', e); }catch(_){}
    return t('hata.baglanilamadi');
  }

  // Hata tonu: hız sınırı bir arıza değil, uyarı. Kırmızı ✕ + "geçersiz" yanlış teşhis olurdu.
  function hataHtml(d){
    var uyari = (d && d.kod === 'hiz_siniri');
    return '<span style="color:'+(uyari?'var(--altin-ink)':'var(--kirmizi-ink)')+'">'+(uyari?'⚠ ':'✕ ')
         + esc((d && d.error) || t('hata.bilinmeyen'))+'</span>';
  }
  //  (2026-08-28): gövde `js/bildirim.js`'e DEVREDİLDİ; 46 çağrı yeri aynen kaldı.
  // Eski gövde tek bir `#hq-toast` düğümünü yeniden kullanıyordu → arka arkaya iki
  // bildirimde İKİNCİSİ BİRİNCİYİ SİLİYORDU (aynı `_t` zamanlayıcısı, aynı düğüm).
  // Ayrıca `.hq-toast` eski renk sözlüğündeydi; üç temada hiç ölçülmedi.
  function toast(msg,kind){
    if (typeof window.bildir === 'function') return window.bildir(msg, kind);
    console.warn('[yuki] bildirim:', kind || 'bilgi', msg);
    return null;
  }
  /* 401/403 bir VERİ yanıtı değildir (fetch reddetmez, gövdesi geçerli JSON'dur).
     authFetch token'sız 401'i kilit açılınca yeniden dener; buraya gelen 401 oturumun
     kilitli kaldığı ya da düştüğü (backend yeniden başladı) anlamına gelir. */
  function _oturumReddi(r){ return !!r && (r.status===401 || r.status===403); }

  // ── Alt-sekme geçişi ──
  var _loaded={key:false,ayarlar:false,modlar:false,memmgr:false,tts:false,pushlog:false};
  /* 🔴 Yeni panel = ÜÇ PARÇA BİRDEN: ① index.html'de `#hq-panel-X` div'i
     ② BU liste ③ `#tab-hq[data-hq="X"] #hq-panel-X{display:flex !important}`
     CSS satırı. Biri eksikse panel SESSİZCE boş kalır. */
  var _HQ_PANELS=['key','license','ayarlar','modlar','memmgr','pushlog','saglik','tema','duvar','sistem','google','cihazlar'];  /* yedekleme 11-13'te YEDEK sekmesine çıktı  — menü girdisi switchHqTab'da sekmeye yönlenir */  // google=Google hesabı bağlama (Takvim+Drive, 2026-09-14); key=BYOK sihirbazı; license=sürüm ve güncelleme (id tarihsel); saglik=kurulum denetimi+hata günlüğü (2026-08-01); sistem=HQ SİSTEM monitörü (Dalga 3, 2026-09-10); 'tts' AYARLAR>Ses&TTS'e gömüldü; yuz/evol kaldırıldı
  /* ══ SOL DİKEY MENÜ (2026-08-12, karar D5) ═══════════════════════════════
     Önce İÇ İÇE İKİ MENÜ vardı: üstte 8 sekmelik yatay şerit, AYARLAR'ın
     içinde ayrıca 7 kategorilik dikey liste. Kullanıcı "mikrofon hassasiyeti"
     için önce sekmeye, sonra kategoriye gidiyordu — iki seviye, iki ayrı yön.

     Ölçüm (2026-08-12, Playwright): 1440px'de yatay şerit 1372px yer kaplayıp
     sekmeler yalnız 805px'ini kullanıyordu → **567px ölü bant** (%41). Dikeyde
     ise az satırlı kategorilerde panelin %68'i boştu (Hafıza/Dil: 863px'in
     278px'i). geliştiricinin "boş yer kalıyor" şikâyetinin ikisi de kaynağıydı.

     Artık tek liste: paneller ve ayar kategorileri aynı düzeyde, gruplu.
     ⚠️ `switchHqTab` KORUNDU — `tab-nav.js:30` onu çağırıyor ve panel
     gösterimi hâlâ onun işi; menü yalnız üstüne biniyor. */
  var _PANEL_IKONLARI = {
    'key': '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true" width="16" height="16"><rect x="3" y="11" width="18" height="11" rx="2" ry="2"/><path d="M7 11V7a5 5 0 0 1 10 0v4"/></svg>',
    'license': '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true" width="16" height="16"><path d="M2 9a3 3 0 0 1 3-3h12a3 3 0 0 1 3 3v6a3 3 0 0 1-3 3H5a3 3 0 0 1-3-3V9z"/><path d="M6 9v6m12 0v-6m-12 3h12"/></svg>',
    'saglik': '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true" width="16" height="16"><path d="M4.8 2.3A.3.3 0 1 0 5 2H4a2 2 0 0 0-2 2v5a6 6 0 0 0 6 6v0a6 6 0 0 0 6-6V4a2 2 0 0 0-2-2h-1a.2.2 0 0 0 .3.3"/><path d="M8 15a1 1 0 0 1-1-1m10 0a1 1 0 0 1-1 1"/></svg>',
    'modlar': '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true" width="16" height="16"><circle cx="12" cy="12" r="1"/><circle cx="19" cy="12" r="1"/><circle cx="5" cy="12" r="1"/></svg>',
    'memmgr': '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true" width="16" height="16"><circle cx="12" cy="12" r="1"/><path d="M12 1v6m0 6v6M4.22 4.22l4.24 4.24m5.08 0l4.24-4.24M1 12h6m6 0h6M4.22 19.78l4.24-4.24m5.08 0l4.24 4.24"/></svg>',
    'pushlog': '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true" width="16" height="16"><path d="M18 8a6 6 0 0 0-9-5.5A6 6 0 0 0 6 19M9 13h6m-3-3v6"/></svg>',
    'tema': '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true" width="16" height="16"><circle cx="12" cy="12" r="9"/><path d="M12 3v18"/><path d="M12 3a9 9 0 0 1 0 18" fill="currentColor" stroke="none" opacity=".55"/></svg>',
    'sistem': '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true" width="16" height="16"><rect x="3" y="4" width="18" height="12" rx="2"/><path d="M8 20h8M12 16v4"/><path d="M7 11l2.5-3 2 4 2-2.5 1.5 1.5"/></svg>',
    /* Google paneli — jenerik BULUT ikonu. Google'ın kendi logosu bilerek
       kullanılmadı: marka varlıkları üçüncü taraf arayüzlerinde izinli kullanım
       kurallarına tabidir ve panel Google'ın kendisi değil, "bulut hesabı
       bağlantısı" anlamına geliyor. */
    'yedekleme': '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true" width="16" height="16"><path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4"/><path d="M7 10l5 5 5-5"/><path d="M12 15V3"/></svg>',
    /* cihazlar + duvar 09-27: cihazlar sözlükte YOKTU → menüde simge yerine "cihazlar" düz metni
       basılıyordu ('den beri); duvar Tema'nın simgesini ödünç alıyordu. Bekçi: test_duvar_paneli */
    'cihazlar': '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true" width="16" height="16"><rect x="5" y="2" width="14" height="20" rx="2"/><path d="M12 18h.01"/></svg>',
    'duvar': '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true" width="16" height="16"><rect x="3" y="3" width="18" height="18" rx="2"/><circle cx="9" cy="9" r="2"/><path d="m21 15-3.1-3.1a2 2 0 0 0-2.8 0L6 21"/></svg>',
    'google': '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true" width="16" height="16"><path d="M17.5 19a4.5 4.5 0 0 0 .5-8.97A6 6 0 0 0 6.2 10.2 3.9 3.9 0 0 0 6.5 19z"/><path d="M12 12v4m0-4l-1.5 1.5M12 12l1.5 1.5"/></svg>'
  };
  /* Ayar kategorilerinin simgeleri ( M11). Backend `icon` alanı karakter
     (◈ ♪ ✦ …) taşıyor ve menüde panellerin çizgi ikonlarıyla karışık duruyordu —
     iki ikon ailesi yan yana. Burada aynı çizgi ailesinden karşılığı var;
     tanımadığımız kategori karakterle değil nötr simgeyle çizilir. */
  var _SVG_AC='<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true" width="16" height="16">';
  var _KATEGORI_IKONLARI = {
    'llm': _SVG_AC+'<rect x="5" y="5" width="14" height="14" rx="2"/><path d="M9 9h6v6H9zM9 2v3m6-3v3M9 19v3m6-3v3M2 9h3m-3 6h3m14-6h3m-3 6h3"/></svg>',
    'ses': _SVG_AC+'<path d="M11 5 6 9H2v6h4l5 4V5z"/><path d="M15.5 8.5a5 5 0 0 1 0 7M19 5a10 10 0 0 1 0 14"/></svg>',
    'mikrofon': _SVG_AC+'<rect x="9" y="2" width="6" height="11" rx="3"/><path d="M5 11a7 7 0 0 0 14 0M12 18v3"/></svg>',
    'hafiza': _SVG_AC+'<ellipse cx="12" cy="5" rx="8" ry="3"/><path d="M4 5v6c0 1.7 3.6 3 8 3s8-1.3 8-3V5M4 11v6c0 1.7 3.6 3 8 3s8-1.3 8-3v-6"/></svg>',
    'algi': _SVG_AC+'<path d="M2 12s3.6-7 10-7 10 7 10 7-3.6 7-10 7S2 12 2 12z"/><circle cx="12" cy="12" r="3"/></svg>',
    'dil': _SVG_AC+'<circle cx="12" cy="12" r="9"/><path d="M3 12h18M12 3a14 14 0 0 1 0 18M12 3a14 14 0 0 0 0 18"/></svg>',
    'gorunum': _SVG_AC+'<path d="M4 21v-7m0-4V3m8 18v-9m0-4V3m8 18v-5m0-4V3M1 14h6m2-6h6m2 8h6"/></svg>',
    'guvenlik': _SVG_AC+'<path d="M12 22s8-4 8-10V5l-8-3-8 3v7c0 6 8 10 8 10z"/></svg>',
    'gelistirici': _SVG_AC+'<circle cx="12" cy="12" r="3"/><path d="M12 2v3m0 14v3M4.9 4.9l2.1 2.1m10 10 2.1 2.1M2 12h3m14 0h3M4.9 19.1 7 17M17 7l2.1-2.1"/></svg>'
  };
  var _KATEGORI_IKON_YEDEK = _SVG_AC+'<circle cx="12" cy="12" r="8"/><circle cx="12" cy="12" r="2"/></svg>';
  var HQ_MENU=[
    {grup:'hq.grup.kurulum', girdiler:[
      /* Bilgisayarım EN ÜSTTE (11-13, geliştirici seçimi: "HQ kişiseldeki gibi") —
         kişiselde HQ'nun ilk sekmesi SİSTEM ve HQ onunla açılır (hqAcilisPaneli). */
      {tip:'panel', id:'sistem',  ikon:'sistem', etiket:'hq.menu.bilgisayarim'},
      {tip:'panel', id:'key',     ikon:'key', etiket:'hq.menu.anahtar'},
      {tip:'panel', id:'license', ikon:'license', etiket:'hq.menu.lisans'},
      /* SAĞLIK en sağdaydı; "bir şey bozuk" anında açılan panel en uzakta
         aranmamalı — kurulum kümesine alındı. */
      {tip:'panel', id:'saglik',  ikon:'saglik', etiket:'hq.menu.saglik'},
      /* SİSTEM, SAĞLIK'ın yanında (Dalga 3). Aynı gerekçe: "bir şey yavaş/bozuk"
         anında açılan panel en uzakta aranmamalı. İkisi kardeş sorulara bakıyor —
         SAĞLIK *"kurulum tam mı"*, SİSTEM *"şu an neyi yiyor"*. Kademe **Free**
         (`packages.FEATURE_MIN_TIER["system_monitor"]`), o yüzden burada bir
         yetki koşulu aranmıyor; tablo salt-okunurdur. */
      /* 🔴 Etiket "Sistem" DEĞİL — o ad ZATEN ALINMIŞ: `gelistirici` ayar
         kategorisinin etiketi "Sistem" (`settings_api.py:253`) ve o da bu
         menüde, GELİŞMİŞ grubunda duruyor. İlk sürümde ikisi de "Sistem"
         yazıyordu; canlı ekran görüntüsünde yakalandı — aynı menüde iki
         özdeş ad, "aynı soruya iki cevap"ın kullanıcıya bakan yüzü.
         Kimlik (`sistem`, `system_monitor`) değişmedi, yalnız görünen ad. */
      /* GOOGLE — Takvim + Drive hesabı bağlama (2026-09-14).
         KURULUM grubunda çünkü Anahtar/Lisans ile aynı soruya bakıyor:
         *"Yuki'yi kullanmaya başlamak için ne girmem gerek"*.
         🔴 Kapı (`require_planner`, router düzeyi kapı) → girdi
         yalnız yetki VARKEN çizilir. `kosul` FAIL-CLOSED: `=== true` aranır,
         `!== false` DEĞİL — yetki henüz bilinmezken (açılışta lisans fetch'i
         sürerken, ya da kilit ekranı yüzünden 401 alınmışken) girdi
         GÖSTERİLMEZ. Aksi hâlde Free kullanıcı panele girip 403 yiyordu.
         ⚠️ Ad çakışması denetlendi: menüde başka "Google" yok (HQ'nun iki
         özdeş "Sistem" adı dersi). */
      {tip:'panel', id:'google',  ikon:'google', etiket:'hq.menu.google',
       kosul:function(){ return window._yukiPlannerOk === true; }},
      /* YEDEKLEME — Drive aynası ( FAZ 4B, 2026-09-14). GOOGLE'ın hemen
         ardında çünkü ondan BESLENİYOR: bağlantı yoksa buradaki düğmeler iş
         görmez ve panel kullanıcıyı oraya yollar.
         🔴 Kapı (`drive_backup`). `kosul` FAIL-CLOSED (`=== true`):
         yetki henüz BİLİNMEZKEN girdi çizilmez — `!== false` yazılsaydı açılışta
         lisans fetch'i sürerken Free kullanıcı panele girip 403 yerdi. */
      {tip:'panel', id:'yedekleme', ikon:'yedekleme', etiket:'hq.menu.yedekleme',
       kosul:function(){ return window._yukiYedekOk === true; }},
      /* CİHAZLAR — QR ile eşleştirme (2026-09-18). Kapı
         (`device_manager`). `kosul` FAIL-CLOSED (`=== true`) — yedekleme
         girdisinin gerekçesiyle aynı: yetki bilinmezken girdi çizilirse
         kullanıcı panele girip 403 yer. */
      {tip:'panel', id:'cihazlar', ikon:'cihazlar', etiket:'hq.menu.cihazlar',
       kosul:function(){ return window._yukiCihazOk === true; }}
    ]},
    {grup:'hq.grup.yuki', girdiler:[
      {tip:'cat', id:'dil'},
      {tip:'cat', id:'ses'},
      {tip:'cat', id:'mikrofon'},
      {tip:'panel', id:'modlar', ikon:'modlar', etiket:'hq.menu.modlar'}
    ]},
    {grup:'hq.grup.zeka', girdiler:[
      {tip:'cat', id:'llm'},
      {tip:'cat', id:'hafiza'}
    ]},
    /* Hafıza Yöneticisi 2026-08-29'da ZEKA'dan VERİLERİM'e taşındı. İki gerekçe:
       ① Geçmiş odası kalkınca VERİLERİM'de tek başına Bildirim kalmıştı — tek
          üyeli grup, grup değildir.
       ② Ayrım zaten buydu ve yanlış yerdeydi: ZEKA Yuki'nin NASIL düşündüğünü
          ayarlar (sağlayıcı, model, hafıza eşikleri); VERİLERİM kullanıcının
          BİRİKEN kaydını yönetir (anılar, gönderilen bildirimler). Hafıza
          Yöneticisi ikincisidir — orada ayar yok, veri var. */
    {grup:'hq.grup.verilerim', girdiler:[
      {tip:'panel', id:'memmgr', ikon:'memmgr', etiket:'hq.menu.hafiza-yoneticisi'},
      /* BİLDİRİM — telefon bildirimi geçmişi. Kapı
         (`push_notifications`, Dalga 4 · 2026-09-18). `kosul` FAIL-CLOSED
         (`=== true`) — yedekleme girdisinin gerekçesiyle birebir aynı: yetki
         BİLİNMEZKEN girdi çizilirse Free kullanıcı panele girip 403 yer. */
      {tip:'panel', id:'pushlog', ikon:'pushlog', etiket:'hq.menu.bildirim',
       kosul:function(){ return window._yukiPushOk === true; }},
      /* Güvenlik BURADA, GELİŞMİŞ'te değil: "Yuki'yi kim açabilir" günlük bir
         soru, gelişmiş bir ayar değil — gömüldüğü yerde kimse bulamaz. Grup da
         doğru: kayıtlı yüzün ve parolan senin kendi kaydın, tıpkı anıların ve
         bildirimlerin gibi. (Gizlilik ayarları GELİŞMİŞ→algı'da kalıyor;
         orası "ne gönderiliyor", burası "kim girebiliyor".) */
      {tip:'cat', id:'guvenlik'}
    ]},
    {grup:'hq.grup.gelismis', girdiler:[
      {tip:'panel', id:'tema', ikon:'tema', etiket:'hq.menu.tema'},
      /* DUVAR Tema'nın YANINDA (2026-09-08). İkisi de "uygulama nasıl
         görünüyor" sorusunun cevabı; ayrı gruplara koymak görünüm ayarlarını
         ikiye bölerdi. ⚠️ Kademe kapısı YOK — herkese açık
         üçünde de açık, o yüzden burada bir yetki koşulu aranmıyor. */
      {tip:'panel', id:'duvar', ikon:'duvar', etiket:'hq.menu.duvar-kagidi'},
      {tip:'cat', id:'gorunum'},
      {tip:'cat', id:'algi'},
      {tip:'cat', id:'gelistirici'}
    ]}
  ];

  function _menuKategorileri(){
    var m={};
    HQ_MENU.forEach(function(g){ g.girdiler.forEach(function(x){ if(x.tip==='cat') m[x.id]=1; }); });
    return m;
  }
  /* 🔴 Backend yeni bir kategori eklediğinde menüye yazmayı unutmak, o kategoriyi
     ULAŞILAMAZ yapardı (bu projenin en sık kusur sınıfı). Menüde yeri olmayan
     kategori sessizce kaybolmasın diye son gruba düşer; kapı testi
     (`test_ayar_kategorileri.py`) ayrıca uyarır. */
  /* FAZ 4 (2026-08-23): düşme SESSİZ değil artık. Eskiden bilinmeyen kategori
     GELİŞMİŞ'e eklenir, kimse fark etmezdi — kategori "orada" görünüyordu ama
     yanlış grupta ve kimse yanlış olduğunu bilmiyordu. Şimdi girdi `bilinmeyen`
     damgası taşır, menüde uyarı rozetiyle çizilir ve konsola tek satır düşer. */
  var _bilinmeyenCats = [];
  function _menuyuTamamla(){
    var var_=_menuKategorileri(), son=HQ_MENU[HQ_MENU.length-1];
    _bilinmeyenCats = [];
    _cats.forEach(function(c){
      if(!var_[c.id]){
        son.girdiler.push({tip:'cat', id:c.id, bilinmeyen:true});
        _bilinmeyenCats.push(c.id);
      }
    });
    if(_bilinmeyenCats.length){
      console.warn('[HQ] Menüde yeri olmayan ayar kategorisi GELİŞMİŞ grubuna düştü: '
        + _bilinmeyenCats.join(', ')
        + ' — intro-sequences.js HQ_MENU listesine ekle.');
    }
  }
  function _catBul(id){ return _cats.find(function(c){return c.id===id;}) || null; }

  /* Ayar kategorisinin MENÜDE görünen adı (FAZ 3 · Dalga 2).
     Kaynak: sözlük varsa oradan, yoksa backend'in `label`'ı.

     🔑 Bu çift sahiplik DEĞİL, kademeli tek sahiplik. Kategori adı bugün
     backend'de doğuyor (`settings_api.CATEGORIES`) ve backend'in 1.086 metin
     konumu henüz çevrilmedi — onu beklemek menüyü YARI çevrilmiş bırakırdı:
     İngilizce müşteri "Key · Licence · Health" ile "Ses & TTS"i aynı listede
     görürdü. Sözlük öne geçiyor, backend yedekte kalıyor.

     Ayrışmayı yorum değil KAPI engelliyor: `hq.cat.*`'ın TÜRKÇE değeri
     backend'in `label`'ıyla birebir aynı olmak zorunda
     (`test_ayar_menusu.py::test_kategori_adi_backend_ile_AYNI`). Yani TR'de
     hâlâ tek gerçek var; sözlük yalnız İngilizce'yi EKLİYOR. Backend
     çevrildiği gün yön tersine döner ve burası yedeğe iner.

     ⚠️ `t()` bilinmeyen anahtarda ANAHTARI döndürür, boş string değil — o
     yüzden "çeviri var mı" sorusu `m === a` ile sorulur. `if(!m)` yazılsaydı
     sözlükte karşılığı olmayan her kategori menüde `hq.cat.gelistirici`
     diye görünürdü. */
  function _catAd(c){
    var a = 'hq.cat.' + c.id, m = t(a);
    return (m === a) ? (c.label || c.id) : m;
  }

  /* Ayar SATIRININ etiketi — `_catAd`'ın aynısı, bir kat aşağıda (Blok 9).
     `SETTINGS_SCHEMA` 36 etiketi sabit Türkçe tutuyor ve oda gövdesinin
     yarısı bundan doğuyordu: İngilizce ekranda SES odası "Ses Hızı (örn
     +0%)" diyordu. Kademeli tek sahiplik — sözlükte varsa o, yoksa
     backend'in etiketi (yeni bir ayar eklendiğinde satır kaybolmaz,
     yalnız çevrilmemiş görünür ve kendini söyler).

     ⚠️ Anahtar KEBAB: `ayar.use-fish-tts`, `ayar.USE_FISH_TTS` değil. Panel
     turunun "sızan anahtar" süzgeci `^[a-z]+\.[a-z-]` arıyor — büyük harfli
     bir anahtar ekrana düşse o süzgeç onu göremezdi. */
  function _ayarAd(s){
    var a = 'ayar.' + String(s.key || '').toLowerCase().replace(/_/g, '-');
    var m = t(a);
    return (m === a) ? (s.label || s.key || '') : m;
  }

  window.hqMenuCiz = function(){
    var nav=document.getElementById('hq-subnav');
    if(!nav) return;
    if(_cats.length) _menuyuTamamla();
    var h='';
    HQ_MENU.forEach(function(g){
      var satirlar='';
      g.girdiler.forEach(function(x){
        if(x.tip==='cat'){
          var c=_catBul(x.id);
          if(!c) return;   // kategoriler henüz yüklenmedi → bu turda çizilmez
          /* Bilinmeyen kategori GÖRÜNÜR olmalı: menüde sessizce doğru yerdeymiş
             gibi durursa kusur hiç fark edilmez (FAZ 4 kapısı). */
          var bilinmeyen = x.bilinmeyen ? ' data-bilinmeyen="1"' : '';
          var uyari = x.bilinmeyen
            ? '<span class="hq-nav-uyari" aria-hidden="true">!</span>' : '';
          var baslik = x.bilinmeyen
            ? ' title="'+esc(t('hq.menu.tanimsiz-title'))+'"'
              : '';
          var etiketEk = x.bilinmeyen ? t('hq.menu.tanimsiz-ek') : '';
          satirlar+='<button class="hq-nav-btn" data-tip="cat" data-id="'+esc(c.id)+'"'+bilinmeyen+baslik
            +' aria-label="'+esc(_catAd(c))+esc(etiketEk)+'"'
            +' onclick="hqGoto(\'cat\',\''+esc(c.id)+'\')">'
            +'<span class="ic">'+(_KATEGORI_IKONLARI[c.id]||_KATEGORI_IKON_YEDEK)+'</span>'+esc(_catAd(c))+uyari+'</button>';
        } else {
          /* Koşullu girdi (2026-09-14): kademe kapısı olan panel, yetki yokken
             MENÜDE DE olmamalı — "ilan edilen ama çalışmayan özellik" üründe
             kusur sayılır. Koşulsuz girdiler etkilenmez. */
          if(typeof x.kosul === 'function' && !x.kosul()) return;
          satirlar+='<button class="hq-nav-btn" data-tip="panel" data-id="'+esc(x.id)+'"'
            +' data-hq="'+esc(x.id)+'" onclick="hqGoto(\'panel\',\''+esc(x.id)+'\')">'
            +'<span class="ic">'+(_PANEL_IKONLARI[x.ikon]||x.ikon)+'</span>'+esc(t(x.etiket))+'</button>';
        }
      });
      if(satirlar) h+='<div class="hq-nav-grup">'+esc(t(g.grup))+'</div>'+satirlar;
    });
    nav.innerHTML=h;
    hqMenuIsaretle();
  };

  /* 🔴 Dil değişiminde menü YENİDEN ÇİZİLİR — `dil.js`'in çizicisi buraya
     ULAŞAMAZ. Çizici `[data-i18n]` arayarak statik markup'ı tarar; bu menü
     `nav.innerHTML=h` ile JS'ten doğuyor, yani çizici bir şey bulamaz ve
     HATA DA VERMEZ: kullanıcı dili değiştirir, sekmeler İngilizce olur,
     AYAR'ın sol menüsü Türkçe kalır. Dalga 1'in hiç yaşamadığı arıza sınıfı
     (orada her metin markup'ta duruyordu), Dalga 2'nin tamamı bunu yaşar.

     Kanca `yuki-dil-degisti`: `dil.js::uygula` yayınlıyor ve **dilin
     uygulanmasından SONRA** yayınlıyor, yani bu çizim taze `_aktif` dille
     koşar. `switchTab`'ı sarmalamak yerine olaya bağlanmanın gerekçesi
     'te ölçüldü (sarmalayıcı bir frame erken koşar).

     Kapı yokken çizmemek ucuz: `#hq-subnav` yoksa iş yok. */

  /* Panel bazlı dil tazeleyicileri (FAZ 3 · Dalga 2).
     Menü tek başına yetmiyor: AÇIK PANELİN içeriği de `innerHTML` ile doğuyor
     ve çizici ona da ulaşamıyor. Blok 3'ün canlı turunda ölçüldü — sözlük
     doluyken ekranda "2026-09-19 (bugün) · 0 örnek" ve "Ağ ↓" duruyordu.

     🔴 `switchHqTab(acikPanel)` ÇAĞIRMAK ÇÖZMÜYOR: sistem paneli için o yol
     `monitorStart()`'a gidiyor ve orada `if(_monTimer)return;` var — zamanlayıcı
     zaten koşuyorsa fonksiyon hiçbir şey yapmadan dönüyor, yani hiçbir bölüm
     yeniden yüklenmiyor. Panelin kendi çizicilerini doğrudan çağırmak gerek.

     Her blok kendi panelini buraya yazar; dinleyici yalnız AÇIK olanı tazeler
     (kapalı paneli çizmek boşa ağ isteği demek). */
  var _dilTazeleyici = {
    sistem: function(){
      _monYokla();          // kartlar: güç · uyarı · GPU · AMD · ağ · disk
      _monGecmisYukle();    // grafik + "n nokta"
      _monRaporYukle();     // günlük rapor + "(bugün)" + "n örnek" + "Ağ ↓"
      _monSurecleriCek();   // tablo + "ilk n"
    },
    /* 🔑 ANAHTAR paneli (Blok 4): rehber · sağlayıcı seçici · model notu ·
       durum satırı — hepsi `innerHTML`. `keyInit` üçünü de yeniden yüklüyor
       ve ağ isteği ucuz (üç uç, hepsi yerel). `monitorStart`'taki gibi bir
       "zaten koşuyor" kapısı YOK, yani çağrı gerçekten yeniden çiziyor. */
    key: function(){ if(typeof window.keyInit === 'function') window.keyInit(); },
    /* AYAR odaları (Blok 6). `dataset.hq` kategori kimliğini DEĞİL, sabit
       'ayarlar'ı taşır (`switchHqTab('ayarlar')`) — açık odayı `_curCat`
       söyler. `hqSelectCat` zaten her menü tıklamasında koşuyor, yani
       idempotent; burada çağırmak odanın başlığını, amaç cümlesini, kaydetme
       notunu ve `render:'guvenlik'` dalındaki kilit bölümünü birden tazeler.
       ⚠️ Kategori adı backend'den geliyor ama `_catAd()` sözlüğü öne aldığı
       için yeniden fetch gerekmez — şema aynı kalır, yalnız yeniden çizilir. */
    ayarlar: function(){ if(_curCat) window.hqSelectCat(_curCat); },
    /* MODLAR paneli (Blok 7). Panelin statik kabuğu (`index.html`) `data-i18n`
       taşıyor, yani `dil.js` onu zaten çeviriyor; JS'ten doğan iki parça
       kalıyor: mod listesi ve AÇIK form.

       🔴 Liste ağa GİTMEDEN tazeleniyor (`renderModesList`, `hqLoadModes`
       değil): `hqLoadModes` üç uç birden yokluyor (platform · apps ·
       workspaces) ve bu üçünün cevabı dil değişince değişmiyor. Çevrilen şey
       listenin kabuğu, içeriği değil — mod adları kullanıcının kendi verisi.

       🔴 AÇIK FORM, YALNIZ KİRLİ DEĞİLSE yeniden çiziliyor. `renderModeForm`
       alanları depodaki değerden kurar; kullanıcı bir şey yazmışken çağırmak
       o yazıyı SESSİZCE siler. Dil değiştirmek, yarım kalmış bir formu
       çöpe atmanın bedeli değildir — kirli formda etiketler eski dilde kalır,
       kullanıcı kaydedip tekrar açınca çevrilmiş hâlini görür. */
    modlar: function(){
      renderModesList();
      var f=document.getElementById('hq-mode-form');
      if(!f || f.style.display==='none' || _modFormuKirli()) return;
      renderModeForm(_modes.find(function(x){return x.id===f.dataset.id;}));
    },
    /* 🧠 Hafıza Yöneticisi (Blok 8). Panelin statik kabuğu `data-i18n`
       taşıyor ama LİSTE tamamen JS'ten doğuyor: her satırın kategori rozeti
       (`_memmgrKatAdi`), tarihi (yerel biçim) ve "Sil" düğmesi + alttaki
       "{n} kayıt gösteriliyor" sayacı. Kayıt YAZILMADAN canlı turda ölçüldü:
       İngilizce ekranda rozetler *Konuşma / Gerçek / Tercih / Görev*, sayaç
       *"4 kayıt gösteriliyor"* olarak kalıyordu — panelin kendisi çevrilmiş,
       içi Türkçeyken.

       🔑 Ağa GİDİYOR (`memmgrInit`), çünkü tazelenmesi gereken şey yalnız
       kabuk değil satırların kendisi ve elde saklanan `_memmgrItems` ham
       veriyi taşısa da sayaç/rozet çizimi zaten listeyi baştan kurar.

       ⚠️ `_memmgrOffset` sıfırlanıyor: sayfalama açıkken (`daha fazla` ile
       80 satır yüklenmişken) offset>0 olduğu için `memmgrLoadList` satırları
       listenin SONUNA EKLER — yeniden çizim olması gereken yerde liste
       ikiye katlanırdı. Bedeli, dil değiştiren kullanıcının ilk sayfaya
       dönmesi; alternatifi bozuk bir liste.

       ⚠️ Panel kapalıyken hiç çağrılmıyor: `switchHqTab` panel kapanışını
       haber vermiyor, tek fren görünürlük denetimi (HQ monitörünün dersi). */
    memmgr: function(){
      var liste=document.getElementById('memmgr-list');
      if(!liste || !liste.offsetParent) return;
      _memmgrOffset=0;
      memmgrInit();
    },

    /* BİLDİRİM odası (Blok 10). Kabuk `data-i18n` taşıyor, yani çizici onu
       zaten çeviriyor — donan şey JS'ten doğan iki liste: bekleyen
       hatırlatıcılar ("Tekrarlı · … · sıradaki: …") ve Yuki'nin günlüğü
       (kaynak adı + kanal izi; 09-27'ye kadar bildirim kartları). İkisi de tarih biçimi taşıyor,
       yani yalnız kelime değil BİÇİM de eski dilde kalıyordu.

       🔑 SES odasından (Blok 9) farklı olarak AĞA GİDİYOR: satırların kaynağı
       sunucudur (`/api/reminders` + `/api/push/yuki-dedi`) ve elde tutulan bir
       ham kopya yok. `_loaded.pushlog` kilidi de bu yüzden atlanıyor —
       `pushlogInit` yeniden çağrılabilir (üç `fetch`, idempotent).

       ⚠️ Panel kapalıyken hiç çağrılmıyor: `switchHqTab` panel kapanışını
       haber vermiyor, tek fren görünürlük denetimi (HQ monitörünün dersi). */
    pushlog: function(){
      var kap=document.getElementById('hq-pushlog-list');
      if(!kap || !kap.offsetParent) return;
      if(typeof window.pushlogInit === 'function') window.pushlogInit();
    },
    /* SAĞLIK (panel 10). Satır metinleri BACKEND'den gelir (`M()` çağrı anında aktif dilde) → ağa gidilir;
       denetim o an sürüyorsa eski dilde biter, bittiği anda bir kez daha sorulur. Satır sonuçları
       (onarım cümlesi) eski dilde kalacağı için silinir. */
    saglik: function(){
      _sagSonuc={};
      if(_sagSurer) _sagSurer.then(function(){ saglikTara(); }); else saglikTara();
    }
  };

  window.addEventListener('yuki-dil-degisti', function(){
    try{
      if(document.getElementById('hq-subnav')) window.hqMenuCiz();
      var tabHq=document.getElementById('tab-hq');
      if(!tabHq || tabHq.hasAttribute('hidden')) return;
      var tazele=_dilTazeleyici[tabHq.dataset.hq];
      if(typeof tazele === 'function') tazele();
    }catch(e){}
  });

  /* 🔴 Kademe değişince menü YENİDEN ÇİZİLİR — koşullu girdiler (Google · Yedekleme ·
     Cihazlar · Bildirim) `kosul()`'u yalnız çizim anında okur. Eskiden menü yalnız ilk
     açılışta ve dil değişince çiziliyordu: lisans etkinleşince yeni girdiler gelmiyor,
     kaldırılınca kalıyordu (09-27 tarayıcıda ölçüldü). Olayı tab-nav.js yetki bayraklarını
     yazdıktan sonra atar. */
  document.addEventListener('yuki:entitlements', function(){
    try{ if(document.getElementById('hq-subnav')) window.hqMenuCiz(); }catch(e){}
  });

  window.hqMenuIsaretle = function(){
    var tabHq=document.getElementById('tab-hq');
    var panel=tabHq?tabHq.dataset.hq:'';
    document.querySelectorAll('#hq-subnav .hq-nav-btn').forEach(function(b){
      var aktif = (b.dataset.tip==='panel')
        ? (b.dataset.id===panel)
        : (panel==='ayarlar' && b.dataset.id===_curCat);
      b.classList.toggle('active', aktif);
    });
    /* dar pencerede şerit yatay kayar — etkin sekme görünür alanda olsun, kaydırma da
       bir ETİKET SINIRINA otursun (yarım harf kalmasın). scrollIntoView ATA kaydırıcıları da
       oynatırdı → yalnız şeridin scrollLeft'i. Ölçü: konum = düğme sol kenarı − şeridin sol payı (☰ + sekme başlığı). */
    try{
      var nav=document.getElementById('hq-subnav'), a=nav&&nav.querySelector('.hq-nav-btn.active');
      if(a && nav.scrollWidth>nav.clientWidth+1){
        var n0=nav.getBoundingClientRect().left, SAG=36,
            SOL=parseFloat(getComputedStyle(nav).paddingInlineStart)||60;   /* ☰ + sekme başlığı payı (hq.css --hq-serit-sol) */
        var x=function(b){ return b.getBoundingClientRect().left-n0+nav.scrollLeft; };
        var btns=[].slice.call(nav.querySelectorAll('.hq-nav-btn')), ax=x(a), aw=a.offsetWidth;
        var ideal=ax-(nav.clientWidth-aw)/2, sl=0;
        /* OK: şerit kayınca sol ok (#hq-serit-geri, SOL-3 … SOL+27) belirir — düğme okun SAĞINA oturur,
           yoksa etkin çipin ilk 27 px'i okun altında kalıyordu (goz 11-15). Kaydırma 0'da ok yok, pay da yok. */
        var OK=28;
        for(var i=0;i<btns.length;i++){ var c=Math.max(0,x(btns[i])-SOL-OK); if(c<=ideal) sl=c; }
        for(var j=0;j<btns.length && ax+aw>sl+nav.clientWidth-SAG;j++){ var d=x(btns[j])-SOL-OK; if(d>sl) sl=d; }
        nav.scrollLeft=sl;
      }
    }catch(e){}
    _seritOk();
  };

  /* T1 (10-11) · telefon şeridinin kaydırma okları. Kenar solması "devamı var" demeye yetmedi
     (goz: "Sağlık" yarım + soluk, kaydırılabildiği belli değil). O tarafta gizli etiket varken
     ok görünür (`#tab-hq[data-serit-sol|sag]`), basınca şerit ~bir ekran kayar; scroll-snap
     etiket sınırına oturtur. Masaüstünde şerit taşmaz → iki bayrak da düşer, oklar zaten
     yalnız ≤720px'te çizilir (hq.css). Gizli sekmede ölçü 0 → ResizeObserver açılışta tazeler. */
  function _seritOk(){
    var nav=document.getElementById('hq-subnav'), tab=document.getElementById('tab-hq');
    if(!nav || !tab) return;
    var fazla=nav.scrollWidth-nav.clientWidth, sl=Math.abs(nav.scrollLeft);
    tab.toggleAttribute('data-serit-sol', fazla>1 && sl>4);
    tab.toggleAttribute('data-serit-sag', fazla>1 && sl<fazla-4);
  }
  window.hqSeritKaydir = function(yon){
    var nav=document.getElementById('hq-subnav');
    if(!nav) return;
    var az=window.matchMedia && window.matchMedia('(prefers-reduced-motion: reduce)').matches;
    nav.scrollBy({left: yon*Math.max(80, Math.round(nav.clientWidth*0.7)), behavior: az?'auto':'smooth'});
  };
  (function(){
    var nav=document.getElementById('hq-subnav');
    if(!nav) return;
    nav.addEventListener('scroll', _seritOk, {passive:true});
    if(window.ResizeObserver) new ResizeObserver(_seritOk).observe(nav);
    else window.addEventListener('resize', _seritOk);
  })();

  /* Tek giriş noktası: menüde panel ile ayar kategorisi aynı düzeyde durur,
     ikisi arasındaki fark kullanıcıya görünmez. */

  /* ══ TEMA PANELİ ═══════════════════════════════════════════════════════
     2026-10-01: çizim + davranış `js/tema-panel.js`'e taşındı (ORTAM SEÇ, taslak B). Burada yalnız
     menü köprüsü kaldı: panel her açılışta tazelenir (`window.temaPanelAc`). */
  window.hqGoto = function(tip, id){
    if(tip==='cat'){
      switchHqTab('ayarlar');
      hqSelectCat(id);
    } else {
      switchHqTab(id);
    }
  };

  window.switchHqTab = function(name){
    /* YEDEKLEME 11-13'te ayrı sekme : menü girdisi ve eski bağlantılar oraya gider. */
    if(name==='yedekleme'){ if(typeof window.switchTab === 'function') window.switchTab('yedek'); return; }
    /* Yüz kamerası HQ içinde başka panele geçince de bırakılır: 09-27'ye kadar yalnız oda
       değişimi (hqSelectCat) kapatıyordu, panel değişince ışık + 2,5 sn tarama sürüyordu.
       Güvenlik odasına dönüşte hqSelectCat paneli baştan kurar. */
    if(window.YuzSekmesi&&window.YuzSekmesi.kapat){ try{ window.YuzSekmesi.kapat(); }catch(_){ } }
    var tabHq=document.getElementById('tab-hq'); if(tabHq) tabHq.dataset.hq=name;
    /* Menü, ayar kategorilerini de listelediği için HQ'nun HANGİ sekmesi
       açılırsa açılsın şema bir kez yüklenir (eskiden yalnız AYARLAR'a
       girilince yükleniyordu — sol menü o zaman yarım kalırdı). */
    if(!_loaded.ayarlar){ _loaded.ayarlar=true; hqLoadSettings(); }
    _HQ_PANELS.forEach(function(p){
      var el=document.getElementById('hq-panel-'+p);
      if(el) el.style.display=(p===name?'flex':'none');
    });
    /* MODLAR her açılışta tazelenir: başlatıcı ayarı, kurulu uygulamalar ve mod listesi panel
       dışında değişir (Ayarlar, sohbetten kayıt). Kirli form korunur (hqLoadModes). */
    if(name==='modlar'){ hqLoadModes(); }
    if(name==='memmgr' && !_loaded.memmgr){
      _loaded.memmgr=true; memmgrInit();
      /* Anlamca hafıza motoru pakete gömülü değil: eskiden lisans açılınca indirme önerilirdi;
         açık kaynakta ilk hafıza paneli açılışında sessizce denetlenir (eksikse önerir). */
      if(window.ModelDownloader && window.ModelDownloader.ensureMemory){
        try{ window.ModelDownloader.ensureMemory({silentInWeb:true}); }catch(e){}
      }
    }
    // SES paneli artık ayrı sekme değil — AYARLAR > Ses & TTS kategorisinde hqSelectCat ile açılır
    // GELEN KUTUSU her açılışta tazelenir: kaçan mesaj ve kanal ışığı (pencere/telefon) bayat kalmasın
    if(name==='pushlog'){ pushlogInit(); }
    /* ANAHTAR her açılışta tazelenir (anahtar/model sohbetten ya da başka pencereden değişebilir);
       yarım "değiştir" akışı ve yazılan anahtar korunur (keyInit hâli yalnız ilk yüklemede seçer) */
    if(name==='key'){ keyInit(); }
    /* SAĞLIK her açılışta denetlenir: anahtar/model/ayar panel dışında değişir; ilk açılış 401 ise "oturum
       kilitli" sayfa yenilenene dek kalıyordu (09-28). Denetim sürerken ikinci çağrı aynı isteği bekler. */
    if(name==='saglik'){ saglikTara(); }
    /* TEMA her açılışta tazelenir (`_loaded` YOK): kayıt ve bilgisayarın teması panel dışında
       değişebilir (gece OS koyuya geçer); kartlar yerinde güncellenir, odak bozulmaz. */
    if(name==='tema'){ if(typeof window.temaPanelAc === 'function') window.temaPanelAc(); }
    /* DUVAR paneli her açılışta yeniden çiziliyor (`_loaded` KULLANILMIYOR).
       Sebep: kitaplık kullanıcı dosya ekleyip silince değişir; bir kez çizip
       önbelleğe almak, sildiği duvarı listede görmeye devam etmek demekti.
       Çizim ucuz — tek `/api/duvar/liste` çağrısı. */
    if(name==='duvar'){ if(typeof window.duvarPanelCiz === 'function') window.duvarPanelCiz(); }
    /* GOOGLE (2026-09-14) — duvar gibi ÖNBELLEKSİZ: bağlantı durumu panel dışında
       değişir (kullanıcı onayı BAŞKA BİR PENCEREDE tamamlanır, ya da Google
       erişimi iptal eder). `_loaded` bayrağı konsaydı kullanıcı bağlandıktan
       sonra panele dönünce hâlâ "bağlı değil" görürdü. Çizim ucuz: tek
       `/api/planner/google/status` çağrısı. */
    if(name==='google'){ if(typeof window.googlePanelAc === 'function') window.googlePanelAc(); }
    /* Yedekleme paneli her açılışta TAZELENİR (`_loaded` bayrağı YOK): tur arka
       planda koşabilir, saat değişmiş olabilir. Bir kez yükleyip bırakmak
       kullanıcıya bayat bir "son yedekleme" tarihi gösterirdi. */
    if(name==='cihazlar'){ if(typeof window.cihazlarPanelAc === 'function') window.cihazlarPanelAc(); }
    /* SİSTEM paneli `_loaded` KULLANMAZ — canlı ölçüm gösteriyor, bir kez çizip
       bırakmak bayat sayı göstermek olurdu. Panelden çıkınca yoklama DURUR:
       görünmeyen panel için 2 sn'de bir istek atmak, HALKA turunda ölçülen
       "görünmeyen kartın besleyicisi dakikada ~35 boş istek" kusurunun aynısı. */
    if(name==='sistem'){ monitorStart(); } else { monitorStop(); }
    // yuz/evol al-panelleri kaldırıldı (ürün derin temizlik — ADIM 3)
    hqMenuIsaretle();
  };

  /* ════════ SİSTEM İZLEME (Dalga 3 · 2026-09-10) ══════════════════════════
     Kişisel Alice `frontend/js/intro-sequences.js:49-251`'den taşındı.
     Backend yarısı `b453ee2`'de indi (`api/monitor.py` → 8 rota, Free).

     🔴 Kişisel sürümden ÜÇ yerde bilerek ayrılıyor:

     ① **"—" kuralı.** Windows'ta 70 alandan ~6'sı okunamıyor (CPU/NVMe
        sıcaklığı, RAPL güç, AMD GPU). `null` gelen ETİKETLİ alan "—" gösterir,
        **0 yazmaz** — `0°C` yalan söyler ve yanlış teşhise yollar (ElevenLabs
        401'in "geçersiz anahtar" sanılması dersinin aynısı). Etiketi olmayan
        EK (disk sıcaklığı son eki, AMD satırı) ise hiç yazılmaz: orada "—",
        var olmayan bir donanımı "okunamıyor" diye gösterirdi.
     ② **Renkler token'dan okunur, sabit yazılmaz.** Kişiselde `#e8f4fa`,
        `#10b981`, `rgba(255,255,255,.08)` gömülüydü; **üründe açık tema var**
        (`tokens.css [data-tema="acik"]`) ve o renkler orada okunmaz. Tek
        kaynak `css/hq-monitor.css`'teki `--mon-*` sözlüğü.
     ③ **Süreç tablosu salt-okunurdur.** Açık kaynak sürümde süreç sonlandırma
        yok (arka uçta uç da yok). */
  var _monTimer=null, _monNetGecmis=[], _monProcSira='cpu', _monTik=0,
      _monBagli=false, _monAralik='1h', _monRepGun=null, _monRepGunler=[],
      _monRepNavBagli=false;

  function _monPanel(){ return document.getElementById('hq-panel-sistem'); }
  /* Renk tek kaynaktan: panelin kendi kapsamındaki `--mon-*`. `documentElement`
     OKUNMAZ — seri renkleri bilerek panele kapsandı (bkz. hq-monitor.css). */
  function _monRenk(ad){
    var p=_monPanel(); if(!p) return '#888';
    var v=getComputedStyle(p).getPropertyValue(ad).trim();
    return v || '#888';
  }
  var TIRE='—';
  function _monSure(s){
    if(s==null) return TIRE;
    var d=Math.floor(s/86400), h=Math.floor(s%86400/3600), m=Math.floor(s%3600/60);
    return ((d?t('mon.sure-gun',{n:d}):'')+((d||h)?t('mon.sure-saat',{n:h}):'')+t('mon.sure-dakika',{n:m})).trim();  // "0 sa 8 dk" değil "8 dk"
  }
  function _monYaz(id, deger){ var el=document.getElementById(id); if(el) el.textContent=(deger==null||deger==='')?TIRE:deger; }

  function _monSpark(id,arr,renk){
    var cv=document.getElementById(id); if(!cv)return;
    var W=cv.clientWidth||300; cv.width=W;
    var x=cv.getContext('2d'), h=cv.height; x.clearRect(0,0,W,h);
    if(arr.length<2)return;
    var mx=Math.max.apply(null,arr)||1;
    x.beginPath();
    for(var i=0;i<arr.length;i++){ var px=i/(arr.length-1)*W, py=h-(arr[i]/mx)*(h-4)-2; i?x.lineTo(px,py):x.moveTo(px,py); }
    x.strokeStyle=renk; x.lineWidth=1.6; x.stroke();
    x.lineTo(W,h); x.lineTo(0,h); x.closePath();
    /* Dolgu `globalAlpha` ile — `color-mix()` string'i canvas fillStyle'ında
       her Chromium sürümünde çözülmüyor, sessizce siyaha düşerdi. */
    x.save(); x.globalAlpha=0.18; x.fillStyle=renk; x.fill(); x.restore();
  }
  /* ── SAĞLIK ÖLÇERİ ─────────────────────────────────────────────────────────
   * `GET /api/saglik` son kaydı OKUR (ölçüm koşturmaz); düğme `POST /api/saglik/olc`.
   * ⚪ ölçülemedi ≠ ❌ kötü: ölçülemeyen sensör kırmızı değil nötr gösterilir. */
  function _monSaglikDeger(s){
    if(s.durum==='olculemedi') return t('mon.saglik-olculemedi');
    if(s.birim && s.deger!=null) return t('mon.saglik.b.'+s.birim,{n:s.deger});
    return t('mon.saglik.d.'+(s.neden||'iyi'));
  }
  function monitorSaglikRender(d){
    var liste=document.getElementById('mon-saglik-liste'); if(!liste)return;
    var ozet=document.getElementById('mon-saglik-ozet'), alt=document.getElementById('mon-saglik-alt');
    d=d||{};
    if(d.durum==='kayit-yok'||d.durum==='kayit-bozuk'){
      liste.innerHTML=''; if(ozet) ozet.textContent='';
      if(alt) alt.textContent=t(d.durum==='kayit-yok'?'mon.saglik-kayit-yok':'mon.saglik-kayit-bozuk');
      return;
    }
    var sens=Array.isArray(d.sensorler)?d.sensorler:[];
    if(ozet) ozet.textContent=(d.skor==null?TIRE:d.skor+'/100');
    liste.innerHTML=sens.map(function(s){
      var ad=esc(t('mon.saglik.s.'+s.ad));
      return '<div class="mon-ag-satir"><span class="mon-ag-ad">'+ad+'</span>'+
        '<span class="mon-ag-hiz" data-durum="'+esc(s.durum)+'">'+esc(_monSaglikDeger(s))+'</span></div>';
    }).join('');
    if(alt){
      var p=[];
      if(d.kapsam){ var k=String(d.kapsam).split('/'); p.push(t('mon.saglik-kapsam',{n:k[0],m:k[1]})); }
      if(typeof d.yas_saat==='number') p.push(t('mon.saglik-yas',{n:d.yas_saat}));
      if(d.bayat) p.push(t('mon.saglik-bayat'));
      alt.textContent=p.join(' · ');
    }
  }
  async function monitorSaglikYukle(){
    try{ var r=await af('/api/saglik'); if(r.ok) monitorSaglikRender(await r.json()); }catch(e){}
  }
  async function monitorSaglikOlc(){
    var b=document.getElementById('mon-saglik-olc'); if(!b||b.disabled)return;
    var eski=b.textContent; b.disabled=true; b.textContent=t('mon.saglik-olculuyor');
    try{
      var r=await af('/api/saglik/olc',{method:'POST'});
      if(r.ok) monitorSaglikRender(await r.json());
      else { var a=document.getElementById('mon-saglik-alt'); if(a) a.textContent=t('mon.saglik-hata'); }
    }catch(e){ var a2=document.getElementById('mon-saglik-alt'); if(a2) a2.textContent=t('mon.saglik-hata'); }
    b.disabled=false; b.textContent=eski;
  }

  function monitorStart(){
    if(_monTimer)return;
    _monBagla(); _monTik=0;
    _monSurecleriCek();
    _monGecmisYukle(); _monRaporYukle(); _monYokla(); monitorSaglikYukle();
    _monTimer=setInterval(_monYokla,2000);
  }
  function monitorStop(){ if(_monTimer){ clearInterval(_monTimer); _monTimer=null; } }
  window.monitorStart=monitorStart; window.monitorStop=monitorStop;

  async function monitorDoctor(){
    var btn=document.getElementById('mon-doctor-btn');
    var res=document.getElementById('mon-doctor-result');
    if(!btn||!res)return;
    var eski=btn.textContent;
    btn.disabled=true; btn.textContent=t('mon.bakiyor');
    try{
      var r=await af('/api/monitor/doctor');
      var d=await apiJson(r);
      res.hidden=false;
      res.textContent = (d && d.ok && d.summary) ? d.summary
        : ((d && d.error) || t('mon.yorumlayamadim'));
    }catch(e){
      res.hidden=false; res.textContent=agHatasi(e);
    }
    btn.disabled=false; btn.textContent=eski;
  }
  window.monitorDoctor=monitorDoctor;

  async function _monYokla(){
    var p=_monPanel();
    /* Panel görünmüyorsa yoklama DURUR. `offsetParent` şart: kullanıcı CHAT
       sekmesine geçtiğinde `switchHqTab` çağrılmaz (#tab-hq `hidden` olur) —
       tek fren bu. */
    if(!p || p.style.display==='none' || !p.offsetParent){ monitorStop(); return; }
    try{ var r=await af('/api/monitor/snapshot'); if(r.ok) monitorRender(await r.json()); }catch(e){}
    _monTik++;
    if(_monTik%2===1) _monSurecleriCek();                            // ~4 sn
    if(_monTik%30===0){ _monGecmisYukle(); _monRaporYukle(); }       // ~60 sn
  }

  /* ── MAKİNE yardımcıları (2026-09-27) ────────────────────────────────── */
  /* Hücre sayısı: 1 hücre = N GB. 32 GB → 32 hücre okunur; 128 GB'ta 128 hücre
     okunmaz → birim büyür. Birim altta yazılır ("her kare 2 GB"). */
  function _monHucreBirim(toplam){ return toplam<=48 ? 1 : (toplam<=96 ? 2 : 4); }
  function _monHucreCiz(id, toplam, dolu, yari, birim){
    var kap=document.getElementById(id); if(!kap) return;
    if(toplam==null){ kap.innerHTML=''; return; }
    var n=Math.max(1, Math.round(toplam/birim)), d=Math.round((dolu||0)/birim), y=Math.round((yari||0)/birim);
    if(kap.children.length!==n) kap.innerHTML=new Array(n+1).join('<i></i>');
    for(var i=0;i<n;i++) kap.children[i].className = i<d ? 'h-dolu' : (i<d+y ? 'h-onbellek' : '');
  }
  /* Sanal arayüzler (docker köprüleri, veth, sanal makine) kullanıcının "ağı" değil:
     bu makinede 17 arayüzün 15'i buydu. Kalanlara insan adı verilir. */
  var _MON_SANAL=/^(lo$|docker|br-|veth|virbr|vmnet|vboxnet|vEthernet|isatap|Teredo|Loopback|utun|awdl|llw|anpi|bridge|gif|stf)/i;
  function _monAgAdi(ad){
    if(/^(en|eth|Ethernet)/i.test(ad)) return t('mon.ag-kablo');
    if(/^(wl|wi-?fi|Wireless|WLAN)/i.test(ad)) return t('mon.ag-kablosuz');
    if(/tailscale/i.test(ad)) return 'tailscale';
    return ad;
  }
  function _monHiz(mbps){
    if(mbps==null) return TIRE;
    return mbps>=1 ? (mbps.toFixed(1)+' MB/s') : (Math.round(mbps*1024)+' kB/s');
  }

  function monitorRender(s){
    s=s||{};
    // ── Üst şerit: kim · ne kadar açık · sağlık mührü (tek yer) ──
    var mk=s.makine||{};
    var kim=[mk.ad, (mk.cpu||'').replace(/\s+\d+-Core Processor$/i,'').replace(/\(R\)|\(TM\)|CPU @.*$/gi,'').trim()]
      .filter(function(x){ return x; }).join(' · ');
    _monYaz('mon-kimlik', kim||null);
    _monYaz('mon-uptime', _monSure(s.uptime_s));
    var c=s.cpu||{};
    _monYaz('mon-cpu-temp', c.temp_c!=null?(c.temp_c+'°C'):null);   // 🔴 Windows'ta null → "—"
    var guc=s.power||null;
    _monYaz('mon-power', (guc && guc.package_w!=null) ? (guc.package_w+' W') : null);

    var skor=(s.health_score==null?null:s.health_score);
    var muhur=document.getElementById('mon-muhur');
    if(muhur) muhur.dataset.durum = skor==null ? 'yok' : (skor>=80 ? 'iyi' : (skor>=55 ? 'uyari' : 'kritik'));
    _monYaz('mon-health-val', skor);
    _monYaz('mon-muhur-durum', skor==null ? null : t(skor>=80 ? 'mon.saglikli' : (skor>=55 ? 'mon.dikkat' : 'mon.kritik')));
    var al=document.getElementById('mon-alerts');
    if(al){
      var uy=s.alerts||[];
      al.hidden=!uy.length;
      al.innerHTML=uy.map(function(a){ return '<span class="mon-alert '+(a.level==='crit'?'crit':'warn')+'">'+esc(a.msg)+'</span>'; }).join('');
    }

    // ── İŞLEMCİ: her kare bir çekirdek, parlaklık = doluluk ──
    _monYaz('mon-cpu-total', c.total!=null?t('mon.yuzde',{n:Math.round(c.total)}):null);
    _monYaz('mon-cpu-freq', c.freq_mhz!=null?((c.freq_mhz/1000).toFixed(2)+' GHz'):null);
    _monYaz('mon-cpu-load', (c.load_avg&&c.load_avg.length)?c.load_avg.map(function(x){ return Number(x).toFixed(2); }).join(' '):null);
    var kap=document.getElementById('mon-cpu-cores');
    if(kap){
      var cek=c.per_core||[];
      _monCekirdekSayisi=cek.length||_monCekirdekSayisi;
      if(kap.children.length!==cek.length){
        kap.innerHTML=cek.map(function(_,i){ return '<div class="mon-cekirdek"><b></b><i>'+esc(t('mon.cekirdek-kisa',{n:i+1}))+'</i></div>'; }).join('');
      }
      for(var i=0;i<cek.length;i++){
        var kare=kap.children[i]; if(!kare) continue;
        var v=Math.round(cek[i]||0);
        kare.style.setProperty('--d', v);
        kare.firstChild.textContent=v;
      }
    }

    // ── BELLEK: 1 hücre = N GB (kullanımda · önbellek · boş) ──
    var m=s.mem||{};
    var rb=_monHucreBirim(m.total_gb||0);
    _monYaz('mon-ram-used', m.used_gb!=null?m.used_gb.toFixed(1):null);
    _monYaz('mon-ram-total', m.total_gb!=null?(Math.round(m.total_gb)+' GB'):null);
    _monYaz('mon-ram-cache', m.cached_gb!=null?(m.cached_gb.toFixed(1)+' GB'):null);
    _monYaz('mon-swap-txt', m.swap_total_gb?((m.swap_used_gb!=null?m.swap_used_gb.toFixed(1):TIRE)+'/'+m.swap_total_gb.toFixed(0)+' GB'):null);
    _monYaz('mon-ram-birim', t('mon.her-kare-gb',{n:rb}));
    _monHucreCiz('mon-ram-cells', m.total_gb, m.used_gb, m.cached_gb, rb);

    // ── EKRAN KARTI ──
    var g=s.gpu_nvidia, gn=document.getElementById('mon-gpu-name');
    if(g){
      if(gn) gn.textContent=(g.name||t('mon.ekran-karti')).replace(/^NVIDIA GeForce /,'');
      _monYaz('mon-gpu-util', g.util!=null?t('mon.yuzde',{n:g.util}):null);
      _monYaz('mon-vram-txt', g.vram_total_mb!=null?(((g.vram_used_mb||0)/1024).toFixed(1)+'/'+(g.vram_total_mb/1024).toFixed(1)+' GB'):null);
      _monYaz('mon-gpu-temp',  g.temp_c!=null?(g.temp_c+'°C'):null);
      _monYaz('mon-gpu-power', g.power_w!=null?(g.power_w+' W'):null);
      _monYaz('mon-gpu-fan',   g.fan!=null?t('mon.yuzde',{n:g.fan}):null);
      _monHucreCiz('mon-vram-cells', g.vram_total_mb!=null?g.vram_total_mb/1024:null, (g.vram_used_mb||0)/1024, 0, 1);
      // 8 GB → 4×2 iri kare (kart İŞLEMCİ boyuna uzuyor, tek sıra boş kalıyordu); büyük kartta 8 sütun
      var _vk=document.getElementById('mon-vram-cells'); if(_vk) _vk.style.gridTemplateColumns='repeat('+(_vk.children.length<=8?4:8)+',minmax(0,1fr))';
    } else {
      if(gn) gn.textContent=t('mon.ekran-karti-okunamiyor');
      _monYaz('mon-gpu-util', null); _monYaz('mon-vram-txt', null); _monYaz('mon-gpu-temp', null);
      _monYaz('mon-gpu-power', null); _monYaz('mon-gpu-fan', null);
      _monHucreCiz('mon-vram-cells', null);
    }
    /* AMD satırı: veri yoksa BOŞ kalır, "—" YAZILMAZ (bkz. index.html yorumu). */
    var amd=document.getElementById('mon-amd');
    if(amd){
      var a=s.gpu_amd;
      amd.textContent = a ? (t('mon.amd-igpu',{yuzde:a.busy})+(a.vram_used_mb!=null?t('mon.amd-vram',{mb:a.vram_used_mb}):'')) : '';
    }

    // ── AĞ: yalnız gerçek bağlantılar ──
    var n=s.net||{}, gercek=(n.ifaces||[]).filter(function(f){ return !_MON_SANAL.test(f.name||''); }).slice(0,3);
    var nl=document.getElementById('mon-net-list');
    if(nl){
      nl.innerHTML = gercek.length ? gercek.map(function(f){
        return '<div class="mon-ag-satir"><span class="mon-ag-ad" title="'+esc(f.name)+'">'+esc(_monAgAdi(f.name))+'</span>'
          +'<span class="mon-ag-hiz inen">↓ '+esc(_monHiz(f.down_mbps))+'</span>'
          +'<span class="mon-ag-hiz giden">↑ '+esc(_monHiz(f.up_mbps))+'</span></div>';
      }).join('') : '<div class="mon-rep-empty">'+TIRE+'</div>';
    }
    var toplamInen=gercek.reduce(function(t0,f){ return t0+(f.down_mbps||0); },0);
    _monNetGecmis.push(toplamInen); if(_monNetGecmis.length>60) _monNetGecmis.shift();
    _monSpark('mon-net-spark', _monNetGecmis, _monRenk('--mon-seri-1'));
    _monYaz('mon-net-conns', n.connections!=null?t(n.connections===1?'mon.baglanti-tek':'mon.baglanti',{n:n.connections}):null);

    // ── DİSKLER ──
    var dd=document.getElementById('mon-disks');
    if(dd){
      var diskler=s.disks||[];
      dd.innerHTML = diskler.length ? diskler.map(function(d){
        var cls=d.percent>=90?'crit':(d.percent>=80?'warn':'');
        /* Etiketsiz EKLER — okunamıyorsa hiç yazılmaz. */
        var io=(d.read_mbps!=null?t('mon.disk-io',{okuma:d.read_mbps,yazma:d.write_mbps}):'');
        var tmp=(d.temp_c!=null?(' · '+d.temp_c+'°C'):'');
        return '<div class="mon-disk"><span class="mon-disk-name" title="'+esc(d.device)+'">'+esc(d.mount)+'</span>'
          +'<span class="mon-badge">'+esc(d.type)+'</span>'
          +'<div class="mon-bar"><div class="mon-bar-fill '+cls+'" style="width:'+d.percent+'%"></div></div>'
          +'<span class="mon-disk-io">'+_monGb(d.used_gb,d.total_gb)+'/'+_monGb(d.total_gb,d.total_gb)+' GB'+io+tmp+'</span></div>';
      }).join('') : '<div class="mon-rep-empty">'+TIRE+'</div>';
    }
    _monYaz('mon-ts', s.ts?new Date(s.ts*1000).toLocaleTimeString(yerelKod()):null);
  }

  /* NE YİYOR? — aynı adlı süreçler tek satır (claude ×5), en çok işlemci yiyen 3.
     Süreç listesi zaten 4 sn'de bir geliyor; ikinci bir istek atılmaz — liste CPU'ya
     göre değilse (kullanıcı tabloyu ada göre sıraladıysa) ayrıca CPU sıralı istenir. */
  /* psutil süreç yüzdesi TEK çekirdeğe göre (%100 = bir çekirdek dolu); 12 çekirdekte bir
     program %100.9 görünürken İŞLEMCİ kartı %12 diyordu. Burada makinenin payına çevrilir. */
  var _monCekirdekSayisi=1;
  /* 10 GB altı disklerde tam sayı yalan söyler: /boot "0/1 GB" yazarken çubuk %37 doluydu. */
  function _monGb(v, toplam){ return v==null ? TIRE : (toplam<10 ? Number(v).toFixed(1) : Math.round(v)); }
  function _monYiyenCiz(ps){
    var kap=document.getElementById('mon-yiyen'); if(!kap) return;
    var gr={};
    (ps||[]).forEach(function(p){
      var ad=p.name||'?', o=gr[ad]||(gr[ad]={ad:ad, adet:0, cpu:0, mem:0});
      o.adet++; o.cpu+=(p.cpu||0)/_monCekirdekSayisi; o.mem+=(p.mem_mb||0);
    });
    var liste=Object.keys(gr).map(function(k){ return gr[k]; })
      .sort(function(a,b){ return b.cpu-a.cpu; }).slice(0,3);
    if(!liste.length){ kap.innerHTML='<div class="mon-rep-empty">'+esc(t('mon.veri-yok'))+'</div>'; return; }
    var enCok=liste[0].cpu||1;
    kap.innerHTML=liste.map(function(o){
      var ram=o.mem>=1024?((o.mem/1024).toFixed(1)+' GB'):(Math.round(o.mem)+' MB');
      return '<div class="mon-yiyen-satir"><div class="mon-yiyen-ust">'
        +'<span class="mon-yiyen-ad">'+esc(o.ad)+(o.adet>1?'<small>×'+o.adet+'</small>':'')+'</span>'
        +'<span class="mon-yiyen-cpu">'+esc(t('mon.yuzde',{n:o.cpu.toFixed(1)}))+'</span>'
        +'<span class="mon-yiyen-ram">'+esc(ram)+'</span></div>'
        +'<div class="mon-yiyen-iz" style="width:'+Math.max(2,Math.min(100,o.cpu/enCok*100))+'%"></div></div>';
    }).join('');
  }

  // ── Olay bağlama (bir kez) ──
  function _monBagla(){
    if(_monBagli)return; _monBagli=true;
    var bas=document.querySelector('#hq-panel-sistem .mon-proc thead');
    if(bas) bas.addEventListener('click',function(e){
      var th=e.target.closest('th[data-sort]'); if(!th)return;
      _monProcSira=th.dataset.sort; _monSurecleriCek();
    });
    var sb=document.getElementById('mon-saglik-olc');
    if(sb) sb.addEventListener('click',function(e){ e.preventDefault(); e.stopPropagation(); monitorSaglikOlc(); });
    var govde=document.getElementById('mon-proc-body');
    if(govde) govde.addEventListener('click',function(e){
      var tr=e.target.closest('tr[data-pid]'); if(tr) _monDetay(tr.dataset.pid, tr);
    });
    var rb=document.querySelector('#hq-panel-sistem .mon-rbtns');
    if(rb) rb.addEventListener('click',function(e){
      var b=e.target.closest('.mon-rbtn'); if(!b)return;
      _monAralik=b.dataset.r;
      rb.querySelectorAll('.mon-rbtn').forEach(function(x){ x.classList.toggle('active',x===b); });
      _monGecmisYukle();
    });
  }

  // ── Geçmiş grafikleri ──
  async function _monGecmisYukle(){
    try{
      var r=await af('/api/monitor/history?range='+_monAralik); if(!r.ok)return;
      var d=await r.json(), s=d.series||[];
      _monCizgi('mon-hist-main', s, [
        {key:'cpu', color:_monRenk('--mon-seri-1')},
        {key:'mem', color:_monRenk('--mon-seri-2')},
        {key:'gpu', color:_monRenk('--mon-seri-3')}
      ], 100);
      _monCizgi('mon-hist-net', s, [
        {key:'net_down', color:_monRenk('--mon-seri-1')},
        {key:'net_up',   color:_monRenk('--mon-seri-2')}
      ], 0);
      var ec=document.getElementById('mon-hist-count'); if(ec) ec.textContent=t('mon.nokta',{n:s.length});
    }catch(e){}
  }
  function _monCizgi(cid, seri, alanlar, yMax){
    var cv=document.getElementById(cid); if(!cv)return;
    var W=cv.clientWidth||600; cv.width=W;
    var H=cv.height, x=cv.getContext('2d'); x.clearRect(0,0,W,H);
    var padL=34,padR=8,padT=8,padB=16, w=W-padL-padR, h=H-padT-padB;
    if(!seri||seri.length<2){
      x.fillStyle=_monRenk('--ink-3'); x.font='11px monospace'; x.textAlign='center';
      x.fillText(t('mon.gecmis-yok'), W/2, H/2); return;
    }
    if(!yMax){ yMax=0; alanlar.forEach(function(f){ seri.forEach(function(p){ var v=p[f.key]; if(v!=null&&v>yMax)yMax=v; }); }); yMax=yMax<=0?1:yMax*1.15; }
    x.strokeStyle=_monRenk('--kenar'); x.fillStyle=_monRenk('--ink-3'); x.font='9px monospace'; x.textAlign='right'; x.lineWidth=1;
    for(var g=0;g<=4;g++){
      var gy=padT+h*g/4;
      x.beginPath(); x.moveTo(padL,gy); x.lineTo(W-padR,gy); x.stroke();
      var val=yMax*(1-g/4);
      if(h<60 && g%2) continue;   // alçak grafikte (AĞ) 5 etiket 10px aralıkla üst üste biniyordu
      x.fillText(val===0?'0':(val>=100?Math.round(val):(val<10?val.toFixed(1):Math.round(val))), padL-4, gy+3);
    }
    var t0=seri[0].ts, t1=seri[seri.length-1].ts;
    [0,0.5,1].forEach(function(fr){
      var ts=t0+(t1-t0)*fr, d=new Date(ts*1000);
      x.textAlign = fr===1 ? 'right' : 'center';   // ortalı son etiket tuvalin dışına taşıyordu ("15:4")
      x.fillText(d.getHours()+':'+('0'+d.getMinutes()).slice(-2), padL+w*fr, H-4);
    });
    alanlar.forEach(function(f){
      x.beginPath(); var basladi=false;
      for(var i=0;i<seri.length;i++){
        var v=seri[i][f.key]; if(v==null)continue;
        var px=padL+(t1>t0?(seri[i].ts-t0)/(t1-t0):0)*w;
        var py=padT+h-(Math.max(0,Math.min(yMax,v))/yMax)*h;
        basladi?x.lineTo(px,py):(x.moveTo(px,py),basladi=true);
      }
      x.strokeStyle=f.color; x.lineWidth=1.6; x.stroke();
    });
  }

  // ── Günlük rapor ──
  function _monSaniye(s){ s=s||0; if(s>=3600)return t('mon.sure-saat',{n:(s/3600).toFixed(1)}).trim(); if(s>=60)return t('mon.sure-dakika',{n:Math.round(s/60)}); return t('mon.sure-saniye',{n:Math.round(s)}); }
  function _monRepSatir(ad, gosterim, deger, enBuyuk, renk){
    var pct=enBuyuk>0?Math.min(100,deger/enBuyuk*100):0;
    return '<div class="mon-rep-row"><span class="mon-rep-name" title="'+esc(ad)+'">'+esc(ad)+'</span>'
      +'<div class="mon-rep-bar"><div style="width:'+pct+'%;background:'+renk+'"></div></div>'
      +'<span class="mon-rep-val">'+esc(gosterim)+'</span></div>';
  }
  function _monBugun(){ var d=new Date(); return d.getFullYear()+'-'+String(d.getMonth()+1).padStart(2,'0')+'-'+String(d.getDate()).padStart(2,'0'); }
  function _monRepNavBagla(){
    if(_monRepNavBagli)return; _monRepNavBagli=true;
    var prev=document.getElementById('mon-rep-prev'), next=document.getElementById('mon-rep-next'), bugun=document.getElementById('mon-rep-today');
    if(prev) prev.addEventListener('click',function(){ _monRepNav(-1); });
    if(next) next.addEventListener('click',function(){ _monRepNav(1); });
    if(bugun) bugun.addEventListener('click',function(){ if(_monRepGun===_monBugun())return; _monRepGun=_monBugun(); _monRaporYukle(); });
  }
  function _monRepNav(yon){
    var bugun=_monBugun(), gun=_monRepGun||bugun, idx=_monRepGunler.indexOf(gun);
    if(yon<0){
      var eski = (idx>=0 && idx<_monRepGunler.length-1) ? _monRepGunler[idx+1]
               : ((idx<0 && _monRepGunler.length) ? _monRepGunler[0] : null);
      if(!eski)return; _monRepGun=eski;
    } else {
      if(gun>=bugun)return;
      _monRepGun = idx>0 ? _monRepGunler[idx-1] : bugun;
    }
    _monRaporYukle();
  }
  function _monRepNavCiz(){
    var bugun=_monBugun(), gun=_monRepGun||bugun, idx=_monRepGunler.indexOf(gun);
    var prev=document.getElementById('mon-rep-prev'), next=document.getElementById('mon-rep-next'), tb=document.getElementById('mon-rep-today');
    var eskiVar = idx>=0 ? idx<_monRepGunler.length-1 : _monRepGunler.length>0;
    if(prev) prev.disabled=!eskiVar;
    if(next) next.disabled = gun>=bugun;
    if(tb)   tb.disabled   = gun===bugun;
  }
  async function _monRepGunleriYukle(){
    try{ var r=await af('/api/monitor/report/days?limit=30'); if(r.ok){ var d=await r.json(); _monRepGunler=d.days||[]; } }catch(e){}
  }
  async function _monRaporYukle(){
    _monRepNavBagla();
    if(!_monRepGun) _monRepGun=_monBugun();
    if(!_monRepGunler.length) await _monRepGunleriYukle();
    try{
      var r=await af('/api/monitor/report/today?day='+_monRepGun); if(!r.ok)return;
      var d=await r.json(), buGun=(_monRepGun===_monBugun());
      var meta=document.getElementById('mon-rep-meta');
      if(meta) meta.textContent=d.day+(buGun?t('mon.bugun-eki'):'')+t('mon.ornek-eki',{n:(d.samples||0)});
      var bos='<div class="mon-rep-empty">'+esc(t('mon.veri-yok'))+'</div>';
      var s1=_monRenk('--mon-seri-1'), s2=_monRenk('--mon-seri-2');
      var cpu=d.top_cpu||[], cmax=cpu.length?(cpu[0].cpu_sec||0):0;
      var ec=document.getElementById('mon-rep-cpu');
      if(ec) ec.innerHTML = cpu.length ? cpu.map(function(p){ return _monRepSatir(p.name,_monSaniye(p.cpu_sec),p.cpu_sec||0,cmax,s1); }).join('') : bos;
      var mem=d.top_mem||[], mmax=mem.length?Math.max.apply(null,mem.map(function(p){return p.mem_peak_mb||0;})):0;
      var em=document.getElementById('mon-rep-mem');
      if(em) em.innerHTML = mem.length ? mem.map(function(p){
        var v=p.mem_peak_mb||0;
        return _monRepSatir(p.name, v>=1024?((v/1024).toFixed(1)+' GB'):(Math.round(v)+' MB'), v, mmax, s2);
      }).join('') : bos;
      var pk=d.peaks||{};
      var ep=document.getElementById('mon-rep-peaks');
      /* Tepe değerler büyük sayı — "gün içinde en çok nereye çıktı" tek bakışta. */
      function tepe(etiket, deger){ return '<div class="mon-tepe"><span>'+esc(etiket)+'</span><b>'+esc(deger)+'</b></div>'; }
      if(ep) ep.innerHTML =
          tepe(t('mon.tepe-cpu'),    pk.cpu!=null?t('mon.yuzde',{n:Math.round(pk.cpu)}):TIRE)
        + tepe(t('mon.tepe-bellek'), pk.mem!=null?t('mon.yuzde',{n:Math.round(pk.mem)}):TIRE)
        + tepe(t('mon.tepe-gpu'),    pk.gpu!=null?t('mon.yuzde',{n:Math.round(pk.gpu)}):TIRE)
        + tepe(t('mon.tepe-ag'),     pk.net_down!=null?_monHiz(pk.net_down):TIRE);
      _monRepNavCiz();
    }catch(e){}
  }

  // ── Süreç tablosu ──
  async function _monSurecleriCek(){
    try{
      var r=await af('/api/monitor/processes?sort='+_monProcSira+'&limit=40'); if(!r.ok) return;
      var d=await r.json(); _monSurecleriCiz(d);
      if(_monProcSira==='cpu'){ _monYiyenCiz(d.processes); return; }
      var r2=await af('/api/monitor/processes?sort=cpu&limit=40');
      if(r2.ok) _monYiyenCiz((await r2.json()).processes);
    }catch(e){}
  }
  function _monSurecleriCiz(d){
    var b=document.getElementById('mon-proc-body'); if(!b)return;
    var ps=(d&&d.processes)||[];
    var cnt=document.getElementById('mon-proc-count');
    if(cnt) cnt.textContent=t('mon.ilk-n',{n:ps.length})+' · '+_monProcSira.toUpperCase();
    b.innerHTML=ps.map(function(p){
      var mem=p.mem_mb>=1024?((p.mem_mb/1024).toFixed(1)+' GB'):(Math.round(p.mem_mb)+' MB');
      var vram=p.vram_mb?('<span class="mon-vbadge">GPU '+p.vram_mb+' MB</span>'):'';
      var cc=p.cpu>80?'hot':(p.cpu>40?'warm':'');
      return '<tr data-pid="'+p.pid+'"><td class="num">'+p.pid+'</td><td class="mon-pname">'+esc(p.name||'?')+'</td>'
        +'<td class="mon-cmd" title="'+esc(p.cmd||'')+'">'+esc(p.cmd||'')+'</td>'
        +'<td class="num '+cc+'">'+((p.cpu||0)/_monCekirdekSayisi).toFixed(1)+'</td><td class="num">'+mem+vram+'</td>'
        +'<td class="num">'+(p.threads||TIRE)+'</td><td>'+esc(p.user||TIRE)+'</td>'
        +'<td class="num">'+_monSure(p.uptime_s)+'</td></tr>';
    }).join('');
    document.querySelectorAll('#hq-panel-sistem .mon-proc th[data-sort]').forEach(function(th){
      th.classList.toggle('active', th.dataset.sort===_monProcSira);
    });
  }
  async function _monDetay(pid,tr){
    var nx=tr.nextElementSibling;
    if(nx&&nx.classList.contains('mon-detail-row')){ nx.remove(); return; }
    try{
      var r=await af('/api/monitor/process/'+pid); if(!r.ok)return;
      var d=await r.json();
      var row=document.createElement('tr'); row.className='mon-detail-row';
      row.innerHTML='<td colspan="8"><div class="mon-detail"><b>'+esc(d.name||'')+'</b> '
        +esc(t('mon.detay-ust',{pid:d.pid, durum:(d.status||TIRE), baslangic:(d.started||TIRE)}))+'<br>'
        +esc(t('mon.detay-alt',{
             cpu:(d.cpu!=null?(d.cpu+'%'):TIRE), ram:(d.mem_mb!=null?(d.mem_mb+' MB'):TIRE),
             thr:(d.threads||TIRE), okuma:(d.io_read_mb!=null?(d.io_read_mb+' MB'):TIRE),
             yazma:(d.io_write_mb!=null?(d.io_write_mb+' MB'):TIRE)}))+'<br>'
        +'<span class="mon-cmd-full">'+esc(d.cmdline||'')+'</span></div></td>';
      tr.after(row);
    }catch(e){}
  }

  // ════════ ANAHTAR · BAĞLANTI KARTI ( panel 8, 2026-09-27 — geliştirici taslak A'yı seçti) ════════
  // Soru: "anahtarım kayıtlı mı, hangi servis/model, sınırım ne". Eski panel cevabı en alttaki küçük
  // bir satıra koyuyor, anahtar kayıtlıyken bile boş anahtar kutusu gösteriyordu. İki hâl:
  //   durum → servis · anahtar (maskeli) · model satırları + ücretsiz sınır; her satırın kendi "değiştir"i
  //   kur   → 1 servisi seç · 2 anahtarını al · 3 yapıştır (Ollama'da: kur · modeli seç)
  // 🔴 2026-08-01: model listesi SABİT YAZILMAZ — /api/llm/models canlı; sunucu listeyi alamazsa kendi
  // yedeğini döner. Anahtarlar servis başına AYRI saklanır (birini girmek öbürünü silmez) →
  // anahtarı kayıtlı servise yeniden yazmadan geçilir (/api/llm/sec: önce dener, geçerse kalıcı yazar).
  var _saglayicilar=[], _anDurum=null, _anHataMetni='', _anMod=null, _anSecilen=null,
      _anDigerAcik=false, _anModelAcik=false, _anModelDuzenle=false, _anMesaj=null, _anMesgul=false,
      _anModelCache={};
  var _AN_ONDE=['openrouter','ollama'];

  function _sagBul(k){ for(var i=0;i<_saglayicilar.length;i++){ if(_saglayicilar[i].kimlik===k) return _saglayicilar[i]; } return null; }
  /* Sunucu mesajındaki **vurgu** kaçışlanmış metinde kalın olur (ham yıldız görünmesin) */
  function _anVurgu(s){ return esc(s||'').replace(/\*\*(.+?)\*\*/g,'<b>$1</b>').replace(/`([^`]+)`/g,'<code>$1</code>'); }
  function _anKurulu(){ return !!(_anDurum && (_anDurum.set || _anDurum.yerel)); }

  /* ── HQ AÇILIŞ PANELİ (11-13, geliştirici seçimi: "HQ kişiseldeki gibi") ─────────
     Kişiselde HQ, SİSTEM gözlemeviyle açılır. Üründe anahtarsız ilk kurulumda
     kullanıcının sihirbaza ihtiyacı var → kurulum tamamsa 'sistem', değilse
     'key'. Durum henüz bilinmiyorsa (alınmadı / 401) 'key' — güvenli yön:
     kurulumu eksik kullanıcı boş monitöre düşmez.
     Kanca: tab-nav.js `tabchange`i switchHqTab'dan ÖNCE ve SENKRON yayınlar,
     hedefi `window._hqHedefPanel || 'key'` diye okur → hedef BOŞSA burada
     doldurulur; çağıranın koyduğu hedef (hafıza kısayolu vb.) ezilmez. */
  window.hqAcilisPaneli = function(){ return (_anDurum && _anKurulu()) ? 'sistem' : 'key'; };
  async function _hqDurumOgren(){
    if(_anDurum) return;
    try{ var r=await af('/api/llm/key/status'); if(r.ok && !_anDurum) _anDurum=await r.json(); }catch(_){}
  }
  document.addEventListener('tabchange', function(e){
    if(!e || !e.detail || e.detail.tab!=='hq') return;
    if(!window._hqHedefPanel) window._hqHedefPanel = window.hqAcilisPaneli();
    if(!_anDurum) _hqDurumOgren();   // kilitliyken alınamadıysa bir sonraki açılışa hazır olsun
  });
  if(document.readyState==='loading') document.addEventListener('DOMContentLoaded', _hqDurumOgren); else _hqDurumOgren();
  function _anSite(u){ try{ return new URL(u).host.replace(/^www\./,''); }catch(_){ return u||''; } }

  async function _anSaglayicilariAl(){
    try{
      var r=await af('/api/llm/providers'); if(!r.ok) return;
      var d=await r.json();
      if(d && d.ok && d.saglayicilar && d.saglayicilar.length) _saglayicilar=d.saglayicilar;
    }catch(e){ /* liste yoksa kurulum adımı yalnız öndeki iki servisi gösterir */ }
  }
  async function _anModelleriAl(kimlik, taze){
    if(!kimlik) return null;
    if(_anModelCache[kimlik] && !taze) return _anModelCache[kimlik];
    try{
      var r=await af('/api/llm/models?provider='+encodeURIComponent(kimlik)); if(!r.ok) return null;
      var d=await r.json(); if(!d || !d.ok) return null;
      _anModelCache[kimlik]=d; return d;
    }catch(e){ return null; }
  }
  function _anModelBul(d, id){
    var bulunan=null;
    ((d&&d.groups)||[]).forEach(function(g){ (g.options||[]).forEach(function(o){ if(o.id===id) bulunan=o; }); });
    return bulunan;
  }
  function _anModelSecimi(d, secili){
    if(!d || !d.groups) return '<option value="'+esc(secili||'')+'">'+esc(secili||'—')+'</option>';
    return d.groups.map(function(g){
      if(!g.options || !g.options.length) return '';
      return '<optgroup label="'+esc(g.title)+'">'+g.options.map(function(o){
        return '<option value="'+esc(o.id)+'"'+(o.id===secili?' selected':'')+'>'+esc(o.label)+'</option>'; }).join('')+'</optgroup>';
    }).join('');
  }
  /* Liste durumu: bayat model / Ollama'ya ulaşılamadı / yedek liste / araçlı ücretsiz yok — EYLEM isteyenler
     uyarı rengiyle; `bilgi` true ise liste kaynağı da söylenir (kurulumda) */
  function _anListeNotu(d, kimlik, model, bilgi){
    if(!d) return '<span class="an-uyari">⚠ '+esc(t('anahtar.liste-alinamadi'))+'</span>';
    if(model && !_anModelBul(d, model)) return '<span class="an-uyari">⚠ '+esc(t('hq.anahtar.model-bayat',{model:model}))+'</span>';
    if(d.yerel && d.source==='fallback') return '<span class="an-uyari">⚠ '+_anVurgu(d.error||t('anahtar.ollama-ulasilamadi'))+'</span>';
    if(d.source==='fallback') return '<span class="an-uyari">⚠ '+esc(t('anahtar.liste-alinamadi'))+'</span>';
    if(!d.yerel && kimlik==='openrouter' && !d.free_available) return '<span class="an-uyari">⚠ '+esc(t('anahtar.ucretsiz-arac-yok'))+'</span>';
    if(!bilgi) return '';
    if(d.yerel) return t('anahtar.yerel-liste');
    if(kimlik==='openrouter') return esc(t('anahtar.liste-openrouter'));
    return esc(t('anahtar.liste-saglayicidan',{saglayici:((_sagBul(kimlik)||{}).ad||kimlik)}));
  }
  function _anRozetler(s){
    if(!s) return '';
    return (s.yerel ? '<span class="an-rozet">'+esc(t('hq.anahtar.rozet-yerel'))+'</span>'
                    : (s.ucretsiz ? '<span class="an-rozet mor">'+esc(t('hq.anahtar.rozet-ucretsiz'))+'</span>' : ''))
      +(s.dogrulandi ? '' : ' <span class="an-rozet">'+esc(t('hq.anahtar.rozet-denenmedi'))+'</span>');
  }
  function _anMesajHtml(){
    if(!_anMesaj) return '';
    return '<p class="an-sonuc '+_anMesaj.tur+'" role="status">'+_anMesaj.html+'</p>';
  }

  function _anDurumCiz(){
    var d=_anDurum, s=_sagBul(d.provider)||{ad:d.provider_ad||d.provider, yerel:d.yerel, dogrulandi:true},
        md=_anModelCache[d.provider], mo=_anModelBul(md, d.model), mesgul=_anMesgul?' disabled':'';
    var modelHucre = _anModelDuzenle
      ? '<div class="an-model-duzenle"><select class="girdi" id="hq-key-model" aria-label="'+esc(t('hq.anahtar.model'))+'">'+_anModelSecimi(md, d.model)+'</select>'
        +'<div class="an-dugmeler"><button type="button" class="dg dg-birincil" data-an="model-kaydet"'+mesgul+'>'+esc(_anMesgul?t('hq.anahtar.deneniyor'):t('hq.anahtar.kaydet-dene'))+'</button>'
        +'<button type="button" class="dg dg-sessiz" data-an="model-vazgec"'+mesgul+'>'+esc(t('hq.anahtar.vazgec'))+'</button></div>'
        +'<p class="an-ipucu">'+_anListeNotu(md, d.provider, null, true)+'</p></div>'
      : (mo ? esc(mo.label) : '<code>'+esc(d.model||'—')+'</code>')
        +(function(n){ return n?'<p class="an-ipucu">'+n+'</p>':''; })(_anListeNotu(md, d.provider, d.model, false));
    var sinir = (!d.yerel && d.ucretsiz_notu && (d.provider!=='openrouter' || /:free$/.test(d.model||'')))
      ? '<div class="an-sinir"><b>'+esc(t('hq.anahtar.ucretsiz-baslik'))+'</b><p>'+_anVurgu(d.ucretsiz_notu)+'</p></div>' : '';
    /* Yerelde bağlantı ölçülebilir (liste Ollama'dan gelmediyse sunucu yedeğe düşer): ulaşılamıyorken
       yeşil "konuşuyor" ışığı yalan olurdu (goz 09-28). Bulutta anahtar ancak kaydedilirken denenir. */
    var kopuk = !!(d.yerel && md && md.source==='fallback');
    /* Işık SAĞLIK ile ortak (ogeler.css § 14): Ollama'ya ulaşılamıyor = Yuki cevap veremez = kritik */
    return '<div class="an-kart-bas"><h4><span class="an-isik durum-isik '+(kopuk?'kritik':'iyi')+'" aria-hidden="true"></span>'
        +esc(kopuk?t('hq.anahtar.yerel-kopuk'):(d.yerel?t('hq.anahtar.yerel-bagli'):t('hq.anahtar.kayitli')))+'</h4></div>'
      +'<p class="an-alt">'+esc(d.yerel?t('hq.anahtar.yerel-saklama'):t('hq.anahtar.saklama'))+'</p>'
      /* İşletim sistemi anahtarlığı yoksa anahtar şifresiz dosyada (izin 600) — sessiz kalmak
         "korunuyor" sanısı bırakırdı. Metin dile göre sunucudan gelir. */
      +(!d.yerel && d.depo==='dosya' && d.depo_uyari ? '<p class="an-alt an-uyari">⚠ '+esc(d.depo_uyari)+'</p>' : '')
      +_anMesajHtml()
      +'<dl class="an-satirlar">'
      +'<div class="an-satir"><dt>'+esc(t('hq.anahtar.servis'))+'</dt><dd>'+esc(s.ad||d.provider_ad||'')+' '+_anRozetler(s)+'</dd>'
        +'<dd class="an-eylem"><button type="button" class="dg dg-ikincil" data-an="servis">'+esc(t('hq.anahtar.degistir'))+'</button></dd></div>'
      +(d.provider==='chatgpt' ? '<div class="an-satir"><dt>'+esc(t('hq.anahtar.chatgpt-hesap'))+'</dt><dd>'+esc(t('hq.anahtar.chatgpt-bagli'))+'</dd>'
        +'<dd class="an-eylem"><button type="button" class="dg dg-ikincil" data-an="chatgpt-cikis"'+mesgul+'>'+esc(t('hq.anahtar.chatgpt-cikis'))+'</button></dd></div>' : '')
      +(d.yerel||d.provider==='chatgpt' ? '' : '<div class="an-satir"><dt>'+esc(t('hq.anahtar.anahtar'))+'</dt><dd><code>'+esc(d.masked||'')+'</code></dd>'
        +'<dd class="an-eylem"><button type="button" class="dg dg-ikincil" data-an="anahtar">'+esc(t('hq.anahtar.yenisini-gir'))+'</button></dd></div>')
      +'<div class="an-satir'+(_anModelDuzenle?' acik':'')+'"><dt>'+esc(t('hq.anahtar.model'))+'</dt><dd>'+modelHucre+'</dd>'
        +(_anModelDuzenle?'':'<dd class="an-eylem"><button type="button" class="dg dg-ikincil" data-an="model">'+esc(t('hq.anahtar.degistir'))+'</button></dd>')+'</div>'
      +'</dl>'+sinir;
  }

  function _anServisDugmesi(s, alt){
    var var_=s.anahtar_var&&!s.yerel;
    return '<button type="button" class="an-servis'+(s.kimlik===_anSecilen?' secili':'')+'" data-an-sec="'+esc(s.kimlik)+'" aria-pressed="'+(s.kimlik===_anSecilen)+'">'
      +'<span>'+esc(s.yerel?s.ad.replace(/\s*\(.*\)$/,''):s.ad)+'</span><small>'+esc(alt)+(var_?' · '+esc(t('hq.anahtar.anahtar-var')):'')+'</small></button>';
  }
  function _anKurCiz(){
    var degisim=_anKurulu(), s=_sagBul(_anSecilen)||{kimlik:_anSecilen, ad:_anSecilen, yerel:false, dogrulandi:false},
        md=_anModelCache[_anSecilen], mesgul=_anMesgul?' disabled':'';
    var onde=_AN_ONDE.map(_sagBul).filter(Boolean), diger=_saglayicilar.filter(function(x){ return _AN_ONDE.indexOf(x.kimlik)<0; });
    var digerSecili=_AN_ONDE.indexOf(_anSecilen)<0;
    var adim1='<div class="an-secim">'
      +onde.map(function(x){ return _anServisDugmesi(x, x.yerel?t('hq.anahtar.anahtarsiz'):t('hq.anahtar.onerilen')); }).join('')
      +(diger.length?'<button type="button" class="an-servis'+(digerSecili&&!_anDigerAcik?' secili':'')+'" data-an="diger" aria-expanded="'+_anDigerAcik+'"><span>'
        +esc(digerSecili?s.ad:t('hq.anahtar.baska-servis'))+'</span><small>'
        +esc(digerSecili?t('hq.anahtar.baska-servis-degis'):t('hq.anahtar.baska-servis-alt',{adlar:diger.slice(0,3).map(function(x){return x.ad;}).join(', '),n:Math.max(0,diger.length-3)}))+'</small></button>':'')
      +'</div>'
      +(_anDigerAcik&&diger.length?'<div class="an-secim an-diger">'+diger.map(function(x){
          return _anServisDugmesi(x, x.ucretsiz?t('hq.anahtar.rozet-ucretsiz'):t('hq.anahtar.ucretli')); }).join('')+'</div>':'');
    var adim2, adim3, secilenModel=(_anDurum&&_anDurum.provider===_anSecilen&&_anModelBul(md,_anDurum.model))?_anDurum.model:((md&&md.recommended)||s.varsayilan_model||'');
    if(s.yerel){
      adim2='<h5>'+esc(t('hq.anahtar.adim-kur'))+'</h5><p class="an-ipucu">'+esc(t('anahtar.yerel-aciklama'))+'</p>'
        +'<p class="an-ipucu">'+esc(t('hq.anahtar.ollama-indir'))+' <code>ollama pull llama3.1</code></p>'
        +'<p class="an-ipucu an-uyari">⚠ '+t('anahtar.yerel-uyari')+'</p>'+(s.uyari?'<p class="an-ipucu an-uyari">⚠ '+_anVurgu(s.uyari)+'</p>':'')
        +(s.anahtar_url?'<a class="dg dg-ikincil" href="'+esc(s.anahtar_url)+'" target="_blank" rel="noopener">'+esc(t('hq.anahtar.sayfayi-ac',{site:_anSite(s.anahtar_url)}))+'</a>':'');
      adim3='<h5>'+esc(t('hq.anahtar.adim-model'))+'</h5><div class="an-satir-form"><select class="girdi" id="hq-key-model" aria-label="'+esc(t('hq.anahtar.model'))+'">'+_anModelSecimi(md, secilenModel)+'</select>'
        +'<button type="button" class="dg dg-birincil" id="hq-key-save" data-an="kaydet"'+mesgul+'>'+esc(_anMesgul?t('hq.anahtar.deneniyor'):t('hq.anahtar.kaydet-dene'))+'</button></div>'
        +_anMesajHtml()
        +'<p class="an-ipucu">'+_anListeNotu(md, _anSecilen, null, true)+'</p>';
    } else {
      adim2='<h5>'+esc(t('hq.anahtar.adim-al'))+'</h5><p class="an-ipucu">'+esc(t('hq.anahtar.al-metni'))+(s['not']?' '+esc(s['not']):'')+'</p>'
        +'<p class="an-ipucu">'+_anVurgu(s.ucretsiz||t('hq.anahtar.kademe-yok'))+'</p>'
        +(s.dogrulandi?'':'<p class="an-ipucu an-uyari">'+esc(t('hq.anahtar.denenmedi-not'))+'</p>')
        +(s.anahtar_url?'<a class="dg dg-ikincil" href="'+esc(s.anahtar_url)+'" target="_blank" rel="noopener">'+esc(t('hq.anahtar.sayfayi-ac',{site:_anSite(s.anahtar_url)}))+'</a>':'');
      var kayitliGec = s.anahtar_var && !(_anDurum && _anDurum.provider===_anSecilen && _anDurum.set);
      adim3='<h5>'+esc(t('hq.anahtar.adim-yapistir'))+'</h5>'
        +(kayitliGec?'<div class="an-kayitli"><span>'+esc(t('hq.anahtar.kayitli-anahtar'))+' <code>'+esc(s.maskeli||'')+'</code></span>'
          +'<button type="button" class="dg dg-ikincil" data-an="gec"'+mesgul+'>'+esc(t('hq.anahtar.bununla-gec'))+'</button></div><p class="an-ipucu">'+esc(t('hq.anahtar.ya-da-yeni'))+'</p>':'')
        +'<div class="an-satir-form"><input class="girdi an-anahtar" id="hq-key-input" type="password" autocomplete="off" spellcheck="false" aria-label="'+esc(t('hq.anahtar.anahtar'))+'"'
          +' placeholder="'+esc((s.on_ek&&s.on_ek.length)?(s.on_ek[0]+'…'):t('anahtar.yapistir'))+'">'
        +'<button type="button" class="dg dg-birincil" id="hq-key-save" data-an="kaydet"'+mesgul+'>'+esc(_anMesgul?t('hq.anahtar.deneniyor'):t('hq.anahtar.kaydet-dene'))+'</button></div>'
        +_anMesajHtml()
        +(_anModelAcik
          ? '<label class="an-etiket" for="hq-key-model">'+esc(t('hq.anahtar.model'))+'</label><select class="girdi" id="hq-key-model">'+_anModelSecimi(md, secilenModel)+'</select>'
            +'<p class="an-ipucu">'+_anListeNotu(md, _anSecilen, null, true)+'</p>'
          : '<p class="an-ipucu">'+esc(t('hq.anahtar.model-otomatik',{model:((_anModelBul(md,secilenModel)||{}).label||secilenModel||'—')}))
            +'</p><p class="an-ipucu"><button type="button" class="an-bag" data-an="model-ac">'+esc(t('hq.anahtar.baska-model'))+'</button></p>'
            +'<input type="hidden" id="hq-key-model" value="'+esc(secilenModel)+'">');
    }
    return '<div class="an-kart-bas"><h4>'+(degisim?'':'<span class="an-isik durum-isik kurulum" aria-hidden="true"></span>')
        +esc(degisim?t('hq.anahtar.degistir-baslik'):t('hq.anahtar.bagli-degil'))+'</h4>'
        +(degisim?'<button type="button" class="dg dg-sessiz an-vazgec" data-an="vazgec">'+esc(t('hq.anahtar.vazgec'))+'</button>':'')+'</div>'
      +(degisim?'<p class="an-alt">'+esc(t('hq.anahtar.degistir-not'))+'</p>':'')
      +'<ol class="an-adimlar">'
      +'<li class="an-adim"><span class="an-no" aria-hidden="true">1</span><div><h5>'+esc(t('hq.anahtar.adim-servis'))+'</h5>'+adim1+'</div></li>'
      +'<li class="an-adim"><span class="an-no" aria-hidden="true">2</span><div>'+adim2+'</div></li>'
      +'<li class="an-adim simdi"><span class="an-no" aria-hidden="true">3</span><div>'+adim3+'</div></li>'
      +'</ol>'
      +'<div class="an-chatgpt"><p class="an-ipucu">'+esc(t('hq.anahtar.chatgpt-ipucu'))+'</p>'
        +'<div class="an-dugmeler"><button type="button" class="dg dg-ikincil" data-an="chatgpt-giris"'+mesgul+'>'+esc(t('hq.anahtar.chatgpt-giris'))+'</button></div></div>'
      +_anMesajHtml()
      +(s.yerel?'':'<p class="an-abonelik">'+esc(t('hq.anahtar.abonelik'))+'</p>');
  }

  function _anCiz(){
    var kart=document.getElementById('hq-key-kart'); if(!kart) return;
    var inp=document.getElementById('hq-key-input'), yazi=inp?inp.value:'', odak=inp&&document.activeElement===inp;
    if(_anHataMetni){
      kart.innerHTML='<div class="an-hata"><p>'+esc(_anHataMetni)+'</p><button type="button" class="dg dg-ikincil" data-an="tekrar">'+esc(t('hq.anahtar.tekrar-dene'))+'</button></div>';
      return;
    }
    if(!_anMod){ kart.innerHTML='<p class="an-alt">'+esc(t('hq.anahtar.durum-yukleniyor'))+'</p>'; return; }
    kart.innerHTML = _anMod==='durum' ? _anDurumCiz() : _anKurCiz();
    var yeni=document.getElementById('hq-key-input');
    if(yeni && yazi){ yeni.value=yazi; if(odak) yeni.focus(); }
  }

  window.keyInit = async function(){
    _anHataMetni='';
    try{
      var r=await af('/api/llm/key/status');
      /* 401/403 = oturum kilitli ya da düşmüş (backend yeniden başladı) — VERİ DEĞİL.
         Eskiden gövde veri sayılıp "Henüz anahtar yok" yazılıyordu: kullanıcı anahtarının
         silindiğini sanıyordu (09-27 tarayıcıda ölçüldü, olcum/panel_401_olc.py). */
      if(_oturumReddi(r)){ _anHataMetni=t('hq.oturum-kilitli'); _anCiz(); return; }
      if(!r.ok) throw new Error('HTTP '+r.status);
      _anDurum=await r.json();
      // Sohbet rozeti (BAĞLI / ANAHTAR YOK) aynı hükmü okusun — core.js `_anahtarYokla`
      try{ window.dispatchEvent(new CustomEvent('yuki-anahtar-degisti')); }catch(_){}
    }catch(e){ _anHataMetni=t('anahtar.durum-alinamadi'); _anCiz(); return; }
    await _anSaglayicilariAl();
    // Hâl yalnız ilk yüklemede (ya da kurulum kalktıysa) kararlaştırılır: dil değişimi / panele
    // dönüş yarım kalan "değiştir" akışını sıfırlamasın
    if(!_anMod || (_anMod==='durum' && !_anKurulu())) _anMod=_anKurulu()?'durum':'kur';
    if(!_anSecilen) _anSecilen=(_anDurum&&_anDurum.provider)||'openrouter';
    _anModelCache={};
    await _anModelleriAl(_anMod==='durum'?_anDurum.provider:_anSecilen);
    _anCiz();
  };

  async function _anGonder(yol, govde){
    if(_anMesgul) return;
    _anMesgul=true; _anMesaj=null; _anCiz();
    try{
      var r=await af(yol,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(govde)});
      if(_oturumReddi(r)){ _anMesaj={tur:'err',html:esc(t('hq.oturum-kilitli'))}; return; }
      var d=await apiJson(r);
      // Hız sınırı arıza değil uyarı (hataHtml ile aynı ayrım); sunucunun **vurgusu** kalın basılır
      if(!d.ok){ var hz=(d.kod==='hiz_siniri'); _anMesaj={tur:hz?'uyari':'err',html:(hz?'⚠ ':'✕ ')+_anVurgu(d.error||t('hata.bilinmeyen'))}; return; }
      var mj=d.message||t('hq.anahtar.kaydedildi'), h=(/✓/.test(mj)?'':'✓ ')+_anVurgu(mj);
      // Sınırı BAŞARI anında da söyle: kullanıcı ilk 429'da değil en baştan bilsin (2026-08-05)
      if(d.uyari) h+='<br>⚠ '+esc(d.uyari);
      _anMesaj={tur:'ok',html:h};
      _anMod='durum'; _anModelDuzenle=false; _anModelAcik=false; _anDigerAcik=false; _anSecilen=null;
      var inp=document.getElementById('hq-key-input'); if(inp) inp.value='';
      _anMesgul=false;
      await keyInit();
    }catch(e){ _anMesaj={tur:'err',html:esc(agHatasi(e))}; }
    finally{ _anMesgul=false; _anCiz(); }
  }

  window.hqSaveKey = async function(){
    var s=_sagBul(_anSecilen)||{kimlik:_anSecilen||'openrouter'};
    var model=document.getElementById('hq-key-model'), m=model&&model.value?model.value:null;
    if(s.yerel) return _anGonder('/api/llm/yerel',{provider:s.kimlik, model:m});
    var input=document.getElementById('hq-key-input'), key=((input&&input.value)||'').trim();
    // Yerelde anahtar istemek yanlış olurdu; boşluk kontrolü yalnız buluta ait
    if(!key){ _anMesaj={tur:'uyari',html:esc(t('anahtar.bos'))}; _anCiz(); var yeni=document.getElementById('hq-key-input'); if(yeni) yeni.focus(); return; }
    return _anGonder('/api/llm/key',{key:key, model:m, provider:s.kimlik});
  };

  function _anEylem(ad, hedef){
    if(ad==='tekrar'){ keyInit(); return; }
    if(ad==='servis'){ _anMod='kur'; _anSecilen=_anDurum.provider; _anDigerAcik=false; _anMesaj=null; _anCiz(); return; }
    if(ad==='anahtar'){ _anMod='kur'; _anSecilen=_anDurum.provider; _anMesaj=null; _anCiz(); var i=document.getElementById('hq-key-input'); if(i) i.focus(); return; }
    if(ad==='vazgec'){ _anMod='durum'; _anSecilen=null; _anDigerAcik=false; _anModelAcik=false; _anMesaj=null; _anModelleriAl(_anDurum.provider).then(_anCiz); _anCiz(); return; }
    if(ad==='model'){ _anModelDuzenle=true; _anMesaj=null; _anCiz(); var sel=document.getElementById('hq-key-model'); if(sel) sel.focus(); return; }
    if(ad==='model-vazgec'){ _anModelDuzenle=false; _anMesaj=null; _anCiz(); return; }
    if(ad==='model-kaydet'){
      var sec=document.getElementById('hq-key-model'); if(!sec) return;
      if(_anDurum.yerel) _anGonder('/api/llm/yerel',{provider:_anDurum.provider, model:sec.value});
      else _anGonder('/api/llm/sec',{provider:_anDurum.provider, model:sec.value});
      return;
    }
    if(ad==='diger'){ _anDigerAcik=!_anDigerAcik; _anCiz(); return; }
    if(ad==='model-ac'){ _anModelAcik=true; _anCiz(); return; }
    if(ad==='gec'){ var m=document.getElementById('hq-key-model'); _anGonder('/api/llm/sec',{provider:_anSecilen, model:m&&m.value?m.value:null}); return; }
    if(ad==='kaydet'){ hqSaveKey(); return; }
    if(ad==='chatgpt-giris'){ _anChatgptGiris(); return; }
    if(ad==='chatgpt-cikis'){ _anGonder('/api/chatgpt/cikis',{}); return; }
  }
  /* "Continue with ChatGPT": tarayıcı açılır, dönüş arka planda beklenir; bitince ChatGPT etkin sağlayıcı olur.
     API anahtarı yolu (yukarısı) aynen açık kalır. */
  async function _anChatgptGiris(){
    if(_anMesgul) return;
    try{
      var r=await af('/api/chatgpt/giris',{method:'POST'});
      if(_oturumReddi(r)){ _anMesaj={tur:'err',html:esc(t('hq.oturum-kilitli'))}; _anCiz(); return; }
      _anMesaj={tur:'uyari',html:esc(t('hq.anahtar.chatgpt-bekliyor'))}; _anCiz();
      for(var i=0;i<150;i++){
        await new Promise(function(ok){ setTimeout(ok,2000); });
        var d=await (await af('/api/chatgpt/durum')).json();
        if(d.giris_durumu==='tamam'){ return _anGonder('/api/chatgpt/sec',{}); }
        if(d.giris_durumu==='hata'){ _anMesaj={tur:'err',html:'✕ '+esc(t('hq.anahtar.chatgpt-hata'))+(d.giris_hatasi?' ('+esc(d.giris_hatasi)+')':'')}; _anCiz(); return; }
        if(d.url && !d._urlGosterildi){ _anMesaj={tur:'uyari',html:esc(t('hq.anahtar.chatgpt-elle'))+' <code>'+esc(d.url)+'</code>'}; _anCiz(); }
      }
    }catch(e){ _anMesaj={tur:'err',html:esc(agHatasi(e))}; _anCiz(); }
  }
  (function(){
    var kart=document.getElementById('hq-key-kart'); if(!kart) return;
    kart.addEventListener('click', async function(e){
      var sec=e.target.closest('[data-an-sec]');
      if(sec){
        if(_anMesgul) return;
        _anSecilen=sec.getAttribute('data-an-sec'); _anModelAcik=false; _anDigerAcik=false; _anMesaj=null; _anCiz();
        await _anModelleriAl(_anSecilen); _anCiz(); return;
      }
      var b=e.target.closest('[data-an]'); if(b && !b.disabled) _anEylem(b.getAttribute('data-an'), b);
    });
    kart.addEventListener('keydown', function(e){
      if(e.key==='Enter' && e.target && e.target.id==='hq-key-input'){ e.preventDefault(); hqSaveKey(); }
    });
  })();

  // ════════ SAĞLIK · YETENEK KARTLARI ( panel 10, 2026-09-28 — geliştirici taslak B'yi seçti) ════════
  /* 🔴 2026-08-01: ürün temiz Windows'ta çalışmadı, her başarısızlık sessizdi ve müşteri bize yalnız
     "çalışmıyor" diyebildi. Bu panel o boşluğu kapatıyor.
     Taslak B (2026-09-26 HQ taslakları). Sekiz denetim kullanıcının
     YETENEĞİNE göre dört kartta (Sohbet · Ses · Görme ve hafıza · Kayıt); kartın durumu içindeki en ağır
     denetimdir. Üstte tek cümlelik hüküm + sayaç çipleri, altta hata günlüğü özeti.
     Dört durum (backend `durum`): iyi · uyari · kritik · olculemedi. 09-28'e kadar "ölçülemedi" yoktu —
     model listesi alınamayınca, disk okunamayınca panel yeşil "yolunda" çiziyordu.
     Eski kusurlar: satır içi stil/onclick, ⚠️ emoji, "Her şey yolunda" yalnız uyarı varken, çift tıkta iki
     onarım, panel yalnız ilk açılışta denetleniyordu, dil değişince kartlar eski dilde kalıyordu. */
  /* kurulum (09-28, geliştirici): anahtar hiç girilmemiş — arıza değil davet; gerçek arızanın ardında, uyarının önünde */
  var _SAG_SIRA={kritik:0, kurulum:1, uyari:2, olculemedi:3, iyi:4};
  var _SAG_YETENEK=[
    {y:'sohbet', ad:'saglik.yet.sohbet', ids:['llm_anahtar','llm_model','llm_kota']},
    {y:'ses',    ad:'saglik.yet.ses',    ids:['stt','ffmpeg']},
    {y:'hafiza', ad:'saglik.yet.hafiza', ids:['onnxruntime']},
    {y:'kayit',  ad:'saglik.yet.kayit',  ids:['veri_dizini','disk']}
  ];
  /* Bilinmeyen kimlikli denetim DÜŞMEZ: backend yeni bir denetim eklerse "Diğer" kartında çıkar. */
  var _SAG_DIGER={y:'diger', ad:'saglik.yet.diger'};
  /* Kart cümlesi: önce durum_kimlik (ses uyarısı yalnız model inmemişse "ilk konuşmada iner" der — ses
     dönüştürücü eksikken aynı cümle yalan olurdu), sonra durum, yoksa genel. Anahtarlar tam yazılır. */
  var _SAG_CUMLE={
    sohbet:{iyi:'saglik.yet.sohbet-iyi', kritik:'saglik.yet.sohbet-kritik', kurulum:'saglik.yet.sohbet-kurulum'},
    ses:{iyi:'saglik.yet.ses-iyi', kritik:'saglik.yet.ses-kritik', uyari_stt:'saglik.yet.ses-uyari-stt'},
    hafiza:{iyi:'saglik.yet.hafiza-iyi', kritik:'saglik.yet.hafiza-kritik'},
    kayit:{iyi:'saglik.yet.kayit-iyi', kritik:'saglik.yet.kayit-kritik', uyari_disk:'saglik.yet.kayit-uyari-disk',
           olculemedi_disk:'saglik.yet.kayit-olcul-disk'},
    genel:{iyi:'saglik.yet.genel-iyi', uyari:'saglik.yet.genel-uyari', kritik:'saglik.yet.genel-kritik',
           olculemedi:'saglik.yet.genel-olcul', kurulum:'saglik.yet.genel-kurulum'}
  };
  var _SAG_ETIKET={kritik:'saglik.et.kritik', kurulum:'saglik.et.kurulum', uyari:'saglik.et.uyari', olculemedi:'saglik.et.olcul', iyi:'saglik.et.iyi'};
  var _SAG_SAYAC={kritik:'saglik.sayac.kritik', kurulum:'saglik.sayac.kurulum', uyari:'saglik.sayac.uyari', olculemedi:'saglik.sayac.olcul', iyi:'saglik.sayac.iyi'};
  var _SAG_HUKUM={kurulum:'saglik.hukum.kurulum', uyari:'saglik.hukum.uyari', olculemedi:'saglik.hukum.olcul', iyi:'saglik.hukum.iyi'};

  var _sagVeri=null, _sagHata='', _sagHataTon='err', _sagZamani=null, _sagSurer=null;
  var _sagIs={};       // sürmekte olan eylemler: 'onar:<kimlik>' · 'kur:<satır>' → çift tık kilidi + düğme metni
  var _sagSonuc={};    // satır kimliği → {metin, ton, yonlendir} (onarım/kurulum sonucu satırın içinde kalır)
  var _ybBekleyen=[];  // yeniden başlayınca geçerli olacak ayarlar [{key,label}] — backend süreç belleği

  /* Eski backend `durum` taşımaz → ok/seviye'den türet (ölçülemedi'yi o bilemez) */
  function _sagDurum(x){
    if(x && _SAG_SIRA[x.durum]!=null) return x.durum;
    return (x && x.ok) ? 'iyi' : ((x && x.seviye==='kritik') ? 'kritik' : 'uyari');
  }
  function _sagEnAgir(liste){
    var en=null;
    liste.forEach(function(x){ if(!en || _SAG_SIRA[_sagDurum(x)]<_SAG_SIRA[_sagDurum(en)]) en=x; });
    return en;
  }
  function _sagKartlar(d){
    var yer={};
    _SAG_YETENEK.forEach(function(Y){ Y.ids.forEach(function(id){ yer[id]=Y.y; }); });
    var kartlar=_SAG_YETENEK.map(function(Y){ return {y:Y.y, ad:Y.ad, ds:[]}; });
    var diger={y:_SAG_DIGER.y, ad:_SAG_DIGER.ad, ds:[]};
    ((d && d.denetimler) || []).forEach(function(x){
      var y=yer[x.kimlik], k=null;
      kartlar.forEach(function(K){ if(K.y===y) k=K; });
      (k || diger).ds.push(x);
    });
    if(diger.ds.length) kartlar.push(diger);
    kartlar=kartlar.filter(function(k){ return k.ds.length; });   // backend bir denetimi kaldırırsa boş kart yok
    kartlar.forEach(function(k, i){ k.agir=_sagEnAgir(k.ds); k.durum=_sagDurum(k.agir); k.sira=i; });
    /* En ağır kart önde (goz tur 1 #5/#6: telde ölçülemedi Kayıt kartı ilk ekranın altında, tek uyarılı "Diğer"
       kartı dört yeşilin altında kalıyordu); eşit ağırlıkta sabit sıra — hepsi yolundaysa hep aynı düzen. */
    kartlar.sort(function(a, b){ return (_SAG_SIRA[a.durum]-_SAG_SIRA[b.durum]) || (a.sira-b.sira); });
    return kartlar;
  }
  function _sagKartCumle(k){
    var c=_SAG_CUMLE[k.y] || {};
    return t(c[k.durum+'_'+(k.agir && k.agir.kimlik)] || c[k.durum] || _SAG_CUMLE.genel[k.durum]);
  }
  /* "bugün 14:05" · "dün 22:40" · "26 Eylül 22:40" — biçim de dile bağlı (yerelKod) */
  function _sagZaman(tarih){
    var z=(tarih instanceof Date) ? tarih : new Date(tarih);
    if(isNaN(z)) return '';
    var saat=z.toLocaleTimeString(yerelKod(), {hour:'2-digit', minute:'2-digit'});
    var bugun=new Date(); bugun.setHours(0,0,0,0);
    var gun=new Date(z); gun.setHours(0,0,0,0);
    var fark=Math.round((bugun-gun)/86400000);
    if(fark===0) return t('saglik.zaman-bugun',{saat:saat});
    if(fark===1) return t('saglik.zaman-dun',{saat:saat});
    return z.toLocaleDateString(yerelKod(), {day:'numeric', month:'long'})+' '+saat;
  }
  /* Işık ortak sözlükten (ogeler.css § 14): aynı durum ANAHTAR'da da aynı ışık */
  function _sagIsik(durum){ return '<span class="durum-isik '+durum+'" aria-hidden="true"></span>'; }
  function _sagEtiket(durum){ return '<span class="sag-etiket '+durum+'">'+esc(t(_SAG_ETIKET[durum]))+'</span>'; }
  /* cozum_url ekranda tam adresiyle değil ev sahibi + yol olarak (taşmasın, okunsun) */
  function _sagBagMetni(u){ return String(u||'').replace(/^https?:\/\//,'').replace(/\/$/,''); }

  function _sagSatir(x){
    var durum=_sagDurum(x), k=String(x.kimlik||'');
    var h='<li class="sag-satir" data-durum="'+durum+'" data-kimlik="'+esc(k)+'">'+_sagIsik(durum);
    h+='<div class="sag-oz"><span class="sag-ad">'+esc(x.baslik||k)
      +'<span class="gorsel-gizli"> — '+esc(t(_SAG_ETIKET[durum]))+'</span></span>';
    /* Sunucu cümlesi ANAHTAR'ın çizim yolundan (`_anVurgu`: kaçış + `kod` → kod çipi); ham hata/kimlik
       yalnız `title`'da (goz tur 1 #1/#4) */
    if(x.detay) h+='<p class="sag-ne"'+(x.teknik?' title="'+esc(x.teknik)+'"':'')+'>'+_anVurgu(x.detay)+'</p>';
    var s=_sagSonuc[k], elle=!!(s && s.yonlendir==='key');
    /* Otomatik düzeltme reddedildiyse "Düzelt, … seçer" çözümü de kalkar — sonuç cümlesi yerini alır */
    if(durum!=='iyi' && x.cozum && !(elle && x.otomatik_duzeltilebilir)) h+='<p class="sag-cozum">'+_anVurgu(x.cozum)+'</p>';
    if(durum!=='iyi' && x.cozum_url){
      h+='<a class="sag-bag" href="'+esc(x.cozum_url)+'" target="_blank" rel="noopener">'+esc(_sagBagMetni(x.cozum_url))+'</a>';
    }
    /* Kuran eylem AYRI: geri alınamaz ve kullanıcının makinesine dokunur — ne olacağı düğmenin önünde yazar */
    if(x.kurulum_teklifi && x.kurulum_teklifi.uyari) h+='<p class="sag-kur-uyari">'+esc(x.kurulum_teklifi.uyari)+'</p>';
    if(s){
      h+='<p class="sag-sonuc '+s.ton+'" role="status">'+_anVurgu(s.metin)+'</p>';
    }
    h+='</div><div class="sag-ey">';
    /* Onarım "burada otomatik düzeltemiyorum" dediyse Düzelt kalkar, yerine yalnız yönlendirme (goz #9) */
    if(x.otomatik_duzeltilebilir && !elle){
      var onariyor=!!_sagIs['onar:'+k];
      h+='<button type="button" class="dg '+(durum==='kritik'?'dg-birincil':'dg-ikincil')+'" data-sag="onar" data-kimlik="'+esc(k)+'"'
        +(onariyor?' disabled aria-busy="true"':'')+'>'+esc(t(onariyor?'saglik.duzeltiliyor':'saglik.duzelt'))+'</button>';
    }
    /* Çözüm başka ekrandaysa (anahtar yok · bu serviste otomatik düzeltilemiyor) oraya götüren düğme —
       onarım sonucu da yönlendirebilir (goz tur 1: metnin içindeki bağlantı satır aralığını bozuyordu) */
    if(x.yonlendir==='key' || elle){
      /* İlk kurulumda yönlendirme ANA eylemdir ("üç adımda bağla"), arızada ikincil */
      h+= durum==='kurulum'
        ? '<button type="button" class="dg dg-birincil" data-sag="git" data-hedef="key">'+esc(t('saglik.git-kurulum'))+'</button>'
        : '<button type="button" class="dg dg-ikincil" data-sag="git" data-hedef="key">'+esc(t('saglik.git-anahtar'))+'</button>';
    }
    if(x.kurulum_teklifi){
      var kuruyor=!!_sagIs['kur:'+k];
      h+='<button type="button" class="dg dg-ikincil sag-kur" data-sag="kur" data-kimlik="'+esc(x.kurulum_teklifi.kimlik)+'" data-satir="'+esc(k)+'"'
        +(kuruyor?' disabled aria-busy="true"':'')+'>'+esc(kuruyor ? t('saglik.indiriliyor') : x.kurulum_teklifi.etiket)+'</button>';
    }
    return h+'</div></li>';
  }

  function _sagKart(k){
    var baslik=t(k.ad);
    return '<article class="sag-yet" data-durum="'+k.durum+'" data-yetenek="'+k.y+'" aria-label="'+esc(baslik)+'">'
      +'<div class="sag-yet-ust">'+_sagIsik(k.durum)+'<h4>'+esc(baslik)+'</h4>'+_sagEtiket(k.durum)+'</div>'
      +'<p class="sag-yet-cumle">'+esc(_sagKartCumle(k))+'</p>'
      +'<ul class="sag-denetimler">'+k.ds.map(_sagSatir).join('')+'</ul></article>';
  }

  function _sagHukum(d, kartlar){
    if(_sagHata){
      return '<div class="sag-hukum-bas">'+_sagIsik(_sagHataTon==='uyari'?'uyari':'kritik')
        +'<p class="sag-hata-metin">'+esc(_sagHata)+'</p></div>';
    }
    if(!d) return '<p class="sag-kucuk">'+esc(t('saglik.denetleniyor'))+'</p>';
    var say={kritik:0, kurulum:0, uyari:0, olculemedi:0, iyi:0}, liste=d.denetimler||[];
    liste.forEach(function(x){ say[_sagDurum(x)]++; });
    var genel=say.kritik?'kritik':(say.kurulum?'kurulum':(say.uyari?'uyari':(say.olculemedi?'olculemedi':'iyi')));
    var cumle;
    if(genel==='kritik'){
      /* "Yuki cevap veremez" yalnız SOHBET kartı çalışmıyorsa doğru — ses bozukken Yuki cevap verir */
      var bozuk=kartlar.filter(function(k){ return k.durum==='kritik'; });
      cumle=bozuk.some(function(k){ return k.y==='sohbet'; })
        ? t('saglik.hukum.kritik-sohbet')
        : t('saglik.hukum.kritik',{adlar:bozuk.map(function(k){ return t(k.ad); }).join(', ')});
    } else cumle=t(_SAG_HUKUM[genel]);
    var cipler=['kritik','kurulum','uyari','olculemedi','iyi'].filter(function(x){ return say[x]; }).map(function(x){
      return '<span class="sag-etiket '+x+'">'+esc(tc(_SAG_SAYAC[x], say[x], {n:say[x]}))+'</span>';
    }).join('');
    return '<div class="sag-hukum-bas">'+_sagIsik(genel)+'<h3 class="sag-hukum-metin">'+esc(cumle)+'</h3>'
      +'<div class="sag-sayac">'+cipler+'</div></div>'
      +'<p class="sag-kucuk">'+esc(t('saglik.son-denetim',{zaman:_sagZaman(_sagZamani), n:liste.length, y:kartlar.length}))+'</p>';
  }

  function _sagCiz(){
    var ozet=document.getElementById('sag-ozet'), liste=document.getElementById('sag-liste');
    var btn=document.getElementById('sag-tara');
    if(btn){
      btn.disabled=!!_sagSurer;
      if(_sagSurer) btn.setAttribute('aria-busy','true'); else btn.removeAttribute('aria-busy');
      btn.textContent=t(_sagSurer ? 'saglik.denetleniyor' : 'hq.saglik.denetle');
    }
    if(!ozet || !liste) return;
    var d=_sagHata ? null : _sagVeri;   // hata varken eski kartlar gösterilmez — bayat "yolunda" yalan olurdu
    var kartlar=_sagKartlar(d);
    ozet.dataset.durum=_sagHata ? 'hata' : (d ? 'hazir' : 'yukleniyor');
    ozet.innerHTML=_sagHukum(d, kartlar);
    liste.innerHTML=kartlar.map(_sagKart).join('');
  }

  /* Tek uçuş: denetim sürerken gelen her çağrı AYNI sözü alır — üç hızlı tık bir istek. */
  window.saglikTara = function(){
    if(_sagSurer) return _sagSurer;
    _sagSurer=_sagDenetle();
    _sagCiz();
    _sagGunlukOzet();
    return _sagSurer;
  };
  async function _sagDenetle(){
    /* Yeniden başlatma bölümü denetimden BAĞIMSIZ çiziliyor: denetim 401 alsa da (oturum kilitli)
       düğmenin görünmesi doğru — o yol Electron IPC'sinden geçer, backend auth'una hiç uğramaz. */
    yenidenBaslatBolumu('sag-yeniden-baslat');
    try{
      var r=await af('/api/self-check');
      /* 🔴 `r.ok` DENETİMİ ŞART (2026-09-08'de ekranda görüldü). Kilit kuruluyken bu uç 401 +
         `{"detail":"Unauthorized"}` döner; o gövde geçerli JSON'dur ve ekranda "undefined kritik"
         yazıyordu. 429 bir arıza değil (dakikada 20 denetim) — uyarı tonunda, ayrı cümleyle. */
      if(!r.ok){
        _sagHata = _oturumReddi(r) ? t('saglik.kilitli-denetim')
                 : (r.status===429 ? t('saglik.cok-sik') : t('saglik.denetim-http',{kod:r.status}));
        _sagHataTon = r.status===429 ? 'uyari' : 'err';
        return;
      }
      var d=await r.json();
      /* Sayılar `|| 0`'lı: uç şema değiştirip alanı kaldırırsa yine "undefined" yazardı */
      d.kritik_sayisi = d.kritik_sayisi||0;
      d.denetimler = Array.isArray(d.denetimler) ? d.denetimler : [];
      _sagVeri=d; _sagHata=''; _sagZamani=new Date();
      _ybBekleyen = Array.isArray(d.bekleyen_yeniden_baslatma) ? d.bekleyen_yeniden_baslatma : [];
    }catch(e){
      _sagHata=t('saglik.denetim-hata',{sebep:agHatasi(e)}); _sagHataTon='err';
    }finally{
      _sagSurer=null;
      _sagCiz();
      yenidenBaslatBolumu('sag-yeniden-baslat');
    }
  }

  /* Satır içi sonuç. Toast YOK: sonuç düzeltilen satırın altında kalır (LİSANS dersi — ikisi birden
     aynı cümleyi iki kez söylüyordu). */
  function _sagSonucYaz(satir, metin, ton, yonlendir){
    _sagSonuc[satir]={metin:metin, ton:ton, yonlendir:yonlendir||null};
    _sagCiz();
  }
  function _sagUcHatasi(r, anahtar){
    if(r.status===429) return {metin:t('hata.hiz-siniri'), ton:'uyari'};
    if(r.status===422) return {metin:t('saglik.istek-gecersiz'), ton:'err'};
    return {metin:t(anahtar,{kod:r.status}), ton:'err'};
  }

  window.saglikOnar = async function(kimlik, btn){
    if(!kimlik || _sagIs['onar:'+kimlik]) return;   // çift tık = tek onarım
    _sagIs['onar:'+kimlik]=true;
    delete _sagSonuc[kimlik];
    _sagCiz();
    var yenile=false;
    try{
      var r=await af('/api/self-check/repair',{method:'POST',headers:{'Content-Type':'application/json'},
        body:JSON.stringify({kimlik:kimlik})});
      if(_oturumReddi(r)){ _sagSonucYaz(kimlik, t('hq.oturum-kilitli'), 'err'); return; }   // "Düzeltilemedi" değil
      if(!r.ok){ var h=_sagUcHatasi(r, 'saglik.duzeltme-http'); _sagSonucYaz(kimlik, h.metin, h.ton); return; }
      var d=await r.json();
      /* Kalıcı yazılamadıysa "düzeldi" demek yanlış olur — backend `kalici:false` ile söyler, ton uyarı */
      var ton=d.ok ? (d.kalici===false ? 'uyari' : 'ok') : 'err';
      _sagSonucYaz(kimlik, d.mesaj || t(d.ok ? 'saglik.duzeltildi' : 'saglik.duzeltilemedi'), ton, d.yonlendir);
      yenile=!!d.ok;
    }catch(e){ _sagSonucYaz(kimlik, t('saglik.duzeltme-basarisiz',{sebep:agHatasi(e)}), 'err'); }
    finally{
      delete _sagIs['onar:'+kimlik];
      _sagCiz();
    }
    if(yenile) saglikTara();
  };

  window.saglikKur = async function(kimlik, btn){
    var satir=(btn && btn.dataset && btn.dataset.satir) || kimlik;
    if(!kimlik || _sagIs['kur:'+satir]) return;   // indirme + kurulum dakikalar sürebilir; ikinci basış yok
    _sagIs['kur:'+satir]=true;
    _sagSonucYaz(satir, t('saglik.ms-paketi'), 'surec');
    var yenile=false;
    try{
      var r=await af('/api/self-check/install',{method:'POST',headers:{'Content-Type':'application/json'},
        body:JSON.stringify({kimlik:kimlik})});
      if(_oturumReddi(r)){ _sagSonucYaz(satir, t('hq.oturum-kilitli'), 'err'); return; }
      if(!r.ok){ var h=_sagUcHatasi(r, 'saglik.kurulum-http'); _sagSonucYaz(satir, h.metin, h.ton); return; }
      var d=await r.json();
      _sagSonucYaz(satir, d.mesaj || t(d.ok ? 'saglik.kuruldu' : 'saglik.kurulamadi'), d.ok ? 'ok' : 'err');
      yenile=!!d.ok;
    }catch(e){ _sagSonucYaz(satir, t('saglik.kurulum-basarisiz',{sebep:agHatasi(e)}), 'err'); }
    finally{
      delete _sagIs['kur:'+satir];
      _sagCiz();
    }
    if(yenile) saglikTara();
  };

  /* Ortak okuyucu: gövdeyi ancak `r.ok` ise metin sayar.
     🔴 2026-09-08'de ekran görüntüsünde yakalandı: kilit kuruluyken bu uç 401 +
     `{"detail":"Unauthorized"}` dönüyordu ve o gövde HATA GÜNLÜĞÜ kutusuna
     **olduğu gibi** basılıyordu. Kopyala düğmesi de aynı metni panoya alıyordu. */
  async function _gunlukMetni(){
    var r=await af('/api/errors/export');
    if(!r.ok){
      var e=new Error('gunluk_okunamadi');
      e.kilitli=(r.status===401||r.status===403);
      e.kod=r.status;
      throw e;
    }
    return await r.text();
  }
  function _gunlukHataMetni(e){
    if(e && e.kilitli) return t('saglik.kilitli-gunluk');
    if(e && e.kod===429) return t('hata.hiz-siniri');
    if(e && e.kod)     return t('saglik.gunluk-http',{kod:e.kod});
    return t('saglik.gunluk-okunamadi');
  }

  /* Hata günlüğü özeti: son 24 saat + en sık + en son (`/api/errors/recent` → ozet). Eskiden arayüz bu
     ucu hiç kullanmıyordu; kullanıcı ne olduğunu görmek için 500 satırlık dökümü açmak zorundaydı. */
  var _sagLog={ozet:null, hata:''}, _sagLogSurer=null, _sagLogMesgul=false, _sagLogAcik=false;
  function _sagGunlukOzet(){
    if(_sagLogSurer) return _sagLogSurer;
    _sagLogSurer=(async function(){
      try{
        var r=await af('/api/errors/recent?adet=1');
        if(!r.ok){
          _sagLog={ozet:null, kilitli:_oturumReddi(r), hata:_oturumReddi(r) ? t('saglik.kilitli-gunluk')
            : (r.status===429 ? t('hata.hiz-siniri') : t('saglik.gunluk-http',{kod:r.status}))};
          return;
        }
        var d=await r.json();
        _sagLog={ozet:(d && d.ozet) || {}, hata:''};
      }catch(e){ _sagLog={ozet:null, hata:t('saglik.gunluk-okunamadi')}; }
      finally{ _sagLogSurer=null; _sagGunlukCiz(); }
    })();
    return _sagLogSurer;
  }
  function _sagKisalt(s, n){ s=String(s||'').replace(/\s+/g,' ').trim(); return s.length>n ? s.slice(0,n-1)+'…' : s; }
  function _sagGunlukCiz(){
    var kap=document.getElementById('sag-log-ozet');
    if(kap){
      var o=_sagLog.ozet, h;
      if(_sagLog.hata) h='<b>'+esc(_sagLog.hata)+'</b>';
      else if(!o) h='<span class="sag-kucuk">'+esc(t('saglik.denetleniyor'))+'</span>';
      else if(!o.toplam) h='<b>'+esc(t('saglik.gunluk-bos'))+'</b>';
      else {
        var n=o.son_24s||0, enSon=o.en_son && o.en_son.zaman ? _sagZaman(o.en_son.zaman) : '';
        if(n){
          var sik=o.en_sik_24s || {};
          h='<b>'+esc(tc('saglik.gunluk-24s', n, {n:n}))+'</b><span class="sag-kucuk">'
            +esc(t('saglik.gunluk-en-sik',{ornek:_sagKisalt(sik.ornek || sik.anahtar, 90), zaman:enSon}))+'</span>';
        } else {
          h='<b>'+esc(t('saglik.gunluk-24s-yok'))+'</b><span class="sag-kucuk">'
            +esc(tc('saglik.gunluk-toplam', o.toplam, {n:o.toplam, zaman:enSon}))+'</span>';
        }
      }
      kap.innerHTML=h;
    }
    var goster=document.querySelector('#hq-panel-saglik [data-sag="goster"]');
    if(goster){
      goster.textContent=t(_sagLogAcik ? 'saglik.gizle' : 'hq.saglik.goster');
      goster.setAttribute('aria-expanded', _sagLogAcik ? 'true' : 'false');
    }
    var pre=document.getElementById('sag-log');
    if(pre) pre.hidden=!_sagLogAcik;
    /* Günlük okunamıyorsa (oturum kilitli) Göster/Kopyala/Temizle pasif — etkin görünüp aynı hatayı
       üçüncü kez söylemesinler (goz #7) */
    var kilitli=!!_sagLog.kilitli;
    document.querySelectorAll('#hq-panel-saglik .sag-dugmeler .dg').forEach(function(b){ b.disabled=kilitli; });
  }

  window.hataGunluguYukle = async function(){
    var pre=document.getElementById('sag-log');
    var durum=document.getElementById('sag-log-durum');
    if(_sagLogAcik){ _sagLogAcik=false; _sagGunlukCiz(); return; }   // ikinci basış gizler
    if(_sagLogMesgul) return;
    _sagLogMesgul=true;
    try{
      var metin=await _gunlukMetni();
      if(pre) pre.textContent=metin;
      _sagLogAcik=true;
      if(durum) durum.textContent='';
    }catch(e){
      _sagLogAcik=false;   // bayat/yanlış metin ekranda kalmasın
      if(durum){ durum.textContent=_gunlukHataMetni(e); durum.dataset.ton='err'; }
    }finally{ _sagLogMesgul=false; _sagGunlukCiz(); }
  };

  window.hataGunluguKopyala = async function(){
    var durum=document.getElementById('sag-log-durum');
    if(_sagLogMesgul) return;
    _sagLogMesgul=true;
    try{
      var metin=await _gunlukMetni();
      await navigator.clipboard.writeText(metin);
      if(durum){ durum.textContent=t('saglik.panoya-kopyalandi'); durum.dataset.ton='ok'; }
    }catch(e){
      /* ⚠️ İki farklı arıza aynı catch'e düşüyor, ayrılmaları şart:
         ① günlük okunamadı (401/kilit) → aşağıda göstermenin anlamı yok, aynı hatayı ikinci kez üretirdi.
         ② pano izni yok → metin elde var, ekranda göstermek doğru çözüm. */
      if(e && (e.kilitli || e.kod)){
        if(durum){ durum.textContent=_gunlukHataMetni(e); durum.dataset.ton='err'; }
        return;
      }
      _sagLogMesgul=false;
      if(!_sagLogAcik) await hataGunluguYukle();   // pano izni yok → en azından ekranda göster
      if(durum){ durum.textContent=t('saglik.panoya-erisilemedi'); durum.dataset.ton='uyari'; }
    }finally{ _sagLogMesgul=false; }
  };

  /* Tek dinleyici, `data-sag` eylemleri (satır içi onclick yok). Yeniden başlat düğmesi hem burada hem
     AYARLAR şeridinde doğuyor → belge düzeyinde `data-yb`. */
  (function(){
    var kok=document.getElementById('hq-panel-saglik');
    if(kok) kok.addEventListener('click', function(e){
      var b=e.target.closest('[data-sag]');
      if(!b || !kok.contains(b) || b.disabled) return;
      var ne=b.dataset.sag;
      if(ne==='tara') saglikTara();
      else if(ne==='onar') saglikOnar(b.dataset.kimlik, b);
      else if(ne==='kur') saglikKur(b.dataset.kimlik, b);
      else if(ne==='git') window.hqGoto('panel', b.dataset.hedef);
      else if(ne==='goster') hataGunluguYukle();
      else if(ne==='kopyala') hataGunluguKopyala();
      else if(ne==='temizle') hataGunluguTemizle();
    });
    document.addEventListener('click', function(e){
      var b=e.target.closest && e.target.closest('[data-yb="calistir"]');
      if(b && !b.disabled) yenidenBaslatCalistir(b);
    });
  })();

  /* ════════ GÜVENLİ YENİDEN BAŞLATMA (2026-09-08, geliştirici isteği) ════════
   *
   * geliştirici: *"Sağlık kısmına ve diğer alanlara güvenli ve sağlıklı yeniden
   * başlatma butonu koyalım — herhangi bir ayarı değiştirdikten sonra onu
   * kullanabilirler."*
   *
   * Ürün `YUKI_RELOAD=false` ile koşuyor (paketlenmiş kurulum read-only): ayar
   * çoğu durumda ancak süreç yeniden başlayınca uygulanıyor.
   *
   * 🔑 Tek bir üretici fonksiyon var, iki yerde çağrılıyor (Sağlık odası +
   * ayar kaydedildikten sonra çıkan şerit). İkinci bir kopya yazılsaydı er geç
   * ayrışırlardı — bu depoda `surum.js` dersi tam bu.
   *
   * 09-28 (panel 10): SAĞLIK'ta backend'in tuttuğu bekleyen ayarlar varsa bölüm taslaktaki mor şerit olur
   * ("Yeniden başlatma bekliyor — değiştirdiğin N ayar …") ve odanın en üstüne çıkar; bekleyen yoksa
   * masaüstünde sessiz bir satır olarak en alta iner, tarayıcıda hiç çizilmez (yapılamayan iş).
   */
  function _yenidenBaslatDestekli(){ return !!(window.yukiSistem && window.yukiSistem.yenidenBaslat); }

  /* Metin kısmı: bekleyen varsa şerit (başlık + hangi ayarlar), yoksa sade bölüm başlığı + açıklama.
     `ek` = tarayıcı notu ya da engel satırı — metinle aynı sütunda durur. */
  function _ybMetin(bekleyen, ek){
    if(!bekleyen.length){
      return '<h4 class="oda-bolum-bas">'+esc(t('saglik.yeniden-baslatma'))+'</h4>'
        + '<p class="yb-alt">'+esc(t('yb.aciklama'))+'</p>' + ek;
    }
    var adlar=bekleyen.slice(0,3).map(function(b){ return _ayarAd(b); });
    if(bekleyen.length>3) adlar.push(t('yb.ve-fazlasi',{n:bekleyen.length-3}));
    return '<div class="yb-yay"><b class="yb-bas">'+esc(t('yb.bekliyor'))+'</b>'
      + '<p class="yb-alt">'+esc(tc('yb.bekleyen-alt', bekleyen.length, {n:bekleyen.length, adlar:adlar.join(' · ')}))+'</p>'
      + ek + '</div>';
  }

  window.yenidenBaslatBolumu = async function(kapId, opts){
    var kap = document.getElementById(kapId);
    if(!kap) return;
    opts = opts || {};
    var bekleyen = (kapId==='sag-yeniden-baslat') ? _ybBekleyen : [];
    kap.classList.toggle('yb-bekliyor', bekleyen.length>0);
    kap.innerHTML = '';

    /* Tarayıcıda backend'i Electron başlatmadığı için yeniden başlatma
       MÜMKÜN DEĞİL. Çalışmayan bir düğme göstermek yerine sebebi yazıyoruz —
       "ilan edilen ≠ uygulanan" kusurunun bu üründe bedeli ağır oldu. Bekleyen
       ayar yoksa söylenecek bir şey de yok. */
    if(!_yenidenBaslatDestekli()){
      if(opts.sessizWeb || !bekleyen.length) return;
      kap.innerHTML = _ybMetin(bekleyen, '<p class="yb-not">'+t('saglik.restart-yalniz-masaustu')+'</p>');
      return;
    }

    var durum = { yapilabilir: true, engeller: [] };
    try { durum = await window.yukiSistem.yenidenBaslatilabilirMi(); }
    catch(e){ /* durum sorulamadıysa düğmeyi göster; asıl kapı yine backend'de */ }

    if(durum && durum.engeller && durum.engeller.length){
      /* Engel varsa düğme KAPALI ve sebebi yazılı. Sessizce devre dışı bir düğme
         "bozuk" diye okunur; sebebi yazılı olan beklenir. */
      kap.innerHTML = _ybMetin(bekleyen, '<p class="yb-engel">'+esc(t('yb.guvenli-degil'))+' '+durum.engeller.map(esc).join(' · ')+'</p>')
        + '<div class="yb-eylem"><button type="button" class="dg dg-ikincil" disabled>'+esc(t('yb.dugme'))+'</button></div>';
      return;
    }
    kap.innerHTML = _ybMetin(bekleyen, '')
      + '<div class="yb-eylem"><button type="button" class="dg '+(bekleyen.length?'dg-birincil':'dg-ikincil')+'" data-yb="calistir">'
      + esc(t(bekleyen.length ? 'yb.simdi' : 'yb.dugme'))+'</button>'
      + '<span class="yb-durum" role="status"></span></div>';
  };

  /* "Diğer alanlar" — ayar ekranının altına iliştirilen ince şerit.
     Sağlık odasındaki bölümle AYNI çalıştırıcıyı kullanır; yalnız kabı farklı. */
  window.yenidenBaslatSeridi = function(){
    if(!_yenidenBaslatDestekli()) return;   // tarayıcıda şerit gösterme, yapılamaz
    var kap = document.getElementById('yb-serit');
    if(!kap){
      var ana = document.getElementById('hq-settings-main');
      if(!ana) return;
      kap = document.createElement('div');
      kap.id = 'yb-serit';
      kap.className = 'oda-bolum';
      ana.insertBefore(kap, ana.firstChild);   // en üste: aşağı kaydırmadan görünsün
    }
    yenidenBaslatBolumu('yb-serit', { sessizWeb: true });
  };

  window.yenidenBaslatCalistir = async function(btn){
    if(!_yenidenBaslatDestekli()) return;
    /* Durum satırı düğmenin YANINDAKİ: SAĞLIK ve AYARLAR bölümü aynı anda DOM'da olabiliyor,
       eski `#yb-durum` kimliği ikisinden ilkini buluyordu. */
    var d = btn && btn.parentNode ? btn.parentNode.querySelector('.yb-durum') : null;
    /* İki adım (confirm() yok — ürün kuralı): ilk basış ne olacağını söyler, 5 sn içinde
       ikinci basış yeniden başlatır. */
    if(btn && !btn.dataset.onay){
      btn.dataset.onay='1';
      if(d) d.textContent = t('yb.onay');
      setTimeout(function(){ delete btn.dataset.onay; if(d && d.textContent===t('yb.onay')) d.textContent=''; }, 5000);
      return;
    }
    if(btn) delete btn.dataset.onay;
    if(btn){ btn.disabled = true; }
    if(d) d.textContent = t('yb.baslatiliyor');
    try{
      var s = await window.yukiSistem.yenidenBaslat();
      /* ⚠️ `ok:true` gelse bile burada "başarılı" YAZMIYORUZ: uygulama ~400 ms
         içinde kapanacak, o metni kimse okumayacak. `ok:false` ise sebebi
         göstermek şart — sessizce hiçbir şey olmaması en kötü sonuç. */
      if(s && s.ok === false){
        if(btn) btn.disabled = false;
        if(d) d.textContent = (s.engeller && s.engeller.length)
          ? s.engeller.join(' · ') : t('yb.baslatilamadi');
      }
    }catch(e){
      if(btn) btn.disabled = false;
      if(d) d.textContent = t('yb.baslatilamadi-elle');
    }
  };

  /* Geri alınamaz silme → İKİ ADIM (confirm() yok — ürün kuralı). Eskiden tek tık
     doğrudan DELETE atıyordu; 401'de de "0 kayıt silindi" yazıyordu (09-27 ölçüldü).
     İkinci basış 5 sn içinde gelmezse onay düşer. Silinemezse backend artık `ok:false` döner. */
  var _gunlukSilOnay=null;
  window.hataGunluguTemizle = async function(){
    var durum=document.getElementById('sag-log-durum');
    if(!_gunlukSilOnay){
      if(durum){ durum.textContent=t('saglik.temizle-onay'); durum.dataset.ton='uyari'; }
      _gunlukSilOnay=setTimeout(function(){ _gunlukSilOnay=null; if(durum && durum.textContent===t('saglik.temizle-onay')) durum.textContent=''; }, 5000);
      return;
    }
    clearTimeout(_gunlukSilOnay); _gunlukSilOnay=null;
    if(_sagLogMesgul) return;
    _sagLogMesgul=true;
    try{
      var r=await af('/api/errors',{method:'DELETE'});
      if(_oturumReddi(r)){ if(durum){ durum.textContent=t('hq.oturum-kilitli'); durum.dataset.ton='err'; } return; }
      if(!r.ok) throw new Error('HTTP '+r.status);
      var d=await r.json();
      if(d.ok===false) throw new Error('silinemedi');
      _sagLogAcik=false;
      if(durum){ durum.textContent=tc('saglik.kayit-silindi', d.silinen||0, {n:(d.silinen||0)}); durum.dataset.ton='ok'; }
    }catch(e){ if(durum){ durum.textContent=t('saglik.kayit-silinemedi'); durum.dataset.ton='err'; } }
    finally{ _sagLogMesgul=false; _sagGunlukCiz(); _sagGunlukOzet(); }
  };

  /* SİSTEM İZLEME paneli 2026-08-28'de SÖKÜLDÜ — 211 satır.
     Ölü olduğu ölçüldü, tahmin edilmedi:
       · `monitorStart` çağıran YOK (yalnız tanımı vardı)
       · `_HQ_PANELS` listesinde 'monitor' YOK (65. satırdaki yorum
         "monitor/yuz/evol kaldırıldı" diyor — panel sökülmüş, JS'i kalmış)
       · backend'de monitor router'ı KAYITLI DEĞİL (main.py: 0 eşleşme)
       · index.html'de tek bir `mon-` markup'ı yok
     Yani hem çağıran, hem yüzey, hem uç yoktu; kod üç yanından da ölüydü.
     'de bu bloktaki 4 boş catch'e bilerek `console.warn` EKLENMEDİ:
     hiç koşmayacak koda gürültü eklemek olurdu. Geri gerekirse git geçmişi. */

  // ════════ AYARLAR ════════
  var _schema=[],_cats=[],_vals={},_live={},_curCat=null,_ttsInited=false,_varsayilan={},_degisti=[];
  window.hqLoadSettings = async function(){
    try{
      var r=await af('/api/settings'); var d=await r.json();
      _schema=d.schema||[]; _cats=d.categories||[]; _vals=d.values||{}; _live=d.live||{};
      _varsayilan=d.varsayilan||{}; _degisti=d.degisti||[];
      /* Kategoriler artık AYARLAR panelinin İÇİNDEKİ ikinci listede değil, sol
         menüde — iç içe iki menü kalktı (D5). `#hq-settings-side` DOM'da
         kaldırıldı; burada ona dokunmak eskiden zorunluydu, artık değil. */
      hqMenuCiz();
      hqSelectCat(_curCat || (_cats[0]&&_cats[0].id));
    }catch(e){ document.getElementById('hq-settings-main').innerHTML='<div class="intel-empty">'+esc(t('hq.ayarlar-yuklenemedi'))+' '+esc(e)+'</div>'; }
  };
  /* 🔴 2026-08-28 (FAZ 9): sekiz kategori odasının hepsi aynı alt başlığı
     gösteriyordu ("Değişiklikler anında kaydedilir · ⟳ …"). Bir odanın
     kimliği, o odanın NE İÇİN açıldığıdır; sekiz oda tek cümleyi paylaşınca
     hiçbiri kendini anlatmıyor. Backend şemasında kategori açıklaması yok
     (alanlar: id · label · icon — ölçüldü), o yüzden metin burada yaşıyor.
     Kaydetme davranışı ortak bir not olarak gövdenin sonuna indi: doğru bilgi
     ama odanın amacı değil. */
  var ODA_AMAC = {
    llm:        'oda.amac.llm',
    ses:        'oda.amac.ses',
    mikrofon:   'oda.amac.mikrofon',
    hafiza:     'oda.amac.hafiza',
    algi:       'oda.amac.algi',
    dil:        'oda.amac.dil',
    gorunum:    'oda.amac.gorunum',
    guvenlik:   'oda.amac.guvenlik',
    gelistirici:'oda.amac.gelistirici'
  };

  window.hqSelectCat = function(catId){
    _curCat=catId;
    // SES panelini innerHTML sıfırlamasından koru: her seçimde önce güvenli parka al + gizle
    var _ttsP=document.getElementById('hq-panel-tts');
    if(_ttsP){ document.body.appendChild(_ttsP); _ttsP.style.display='none'; }
    /* YÜZ paneli de aynı korumayı ister — o da bir oda gövdesinin İÇİNE gömülüyor
       ve `_main.innerHTML=html` her seçimde gövdeyi siliyor. Parka alınmazsa
       kullanıcı Güvenlik'ten çıkıp geri döndüğünde panel yok olur (kamera akışı
       da onunla birlikte, çünkü <video> DOM'dan koparılınca durur). */
    var _facesP=document.getElementById('faces-root');
    if(_facesP){
      /* Kamerayı ÖNCE kapat, sonra parka al. Ters sırada yapılırsa <video>
         DOM'dan koparılır ama MediaStream açık kalır — kamera ışığı yanmaya
         devam eder ve kullanıcı Yuki'nin kendisini izlediğini sanır. */
      if(window.YuzSekmesi&&window.YuzSekmesi.kapat){
        try{ window.YuzSekmesi.kapat(); }catch(_){ }
      }
      document.body.appendChild(_facesP); _facesP.style.display='none';
    }
    hqMenuIsaretle();
    var cat=_cats.find(function(c){return c.id===catId;})||{};
    var amac=ODA_AMAC[catId]?t(ODA_AMAC[catId]):'';
    var html='<div class="oda-bas"><div class="oda-bas-metin">'
      +'<h3 class="oda-baslik">'+esc(_catAd(cat))+'</h3>'
      +(amac?'<p class="oda-amac">'+esc(amac)+'</p>':'')
      +'</div></div><div class="oda-govde">';
    /* Kategori kendi çizim biçimini söyler (backend `render` alanı). Sabit
       `catId==='dil'` karşılaştırması buradaydı: backend kategoriyi ilan ediyor,
       içeriğinin olup olmadığını yalnız bu dosya biliyordu. Artık kural ölçülebilir
       → backend/tests/test_ayar_kategorileri.py */
    var render=cat.render||'';
    if(render==='live'){ html+=renderLiveTrio(); }
    else if(render==='gfx'){ html+=renderGfxBolumu(); }
    else if(render==='guvenlik'){ html+=renderGuvenlikBolumu(); }
    else {
      /* available===false → bu kurulumda karşılığı olmayan ayar (Fish, göz takibi,
         Windows'ta D-Bus). Çizilmez: açıldığında hiçbir şey olmayan düğme, müşteriye
         "ürün bozuk" dedirtiyor. Alanın kendisi YOKSA (eski backend + yeni frontend —
         delta'da ikisi farklı sürümde kalabilir) ayar gösterilir: `!==false`. */
      var rows=_schema.filter(function(s){return s.cat===catId && s.available!==false;});
      html += rows.length ? rows.map(renderSetRow).join('')
        : '<div class="bos">'
          +'<svg class="bos-ikon" viewBox="0 0 24 24" fill="none" aria-hidden="true">'
          +'<circle cx="12" cy="12" r="9"/><path d="M12 8v4M12 16h.01"/></svg>'
          +'<p class="bos-bas">'+esc(t('oda.bos-bas'))+'</p>'
          +'<p class="bos-metin">'+esc(t('oda.bos-metin'))+'</p></div>';
    }
    /* Ortak "kaydetme notu" (⟳ rozetli) kalktı (09-27): her satır artık kendi zamanını
       (HEMEN / YENİDEN BAŞLATINCA) yazıyor — aynı bilgiyi dipte tekrar etmek gürültüydü. */
    html += '</div>';   /* .oda-govde kapanışı */
    var _main=document.getElementById('hq-settings-main');
    _main.className='oda';
    _main.innerHTML=html;
    /* Ek paneller artık gövdenin İÇİNE girer — `_main` bir grid (başlık şeridi
       kaymaz / gövde kayar); doğrudan `_main`'e eklemek onları grid'in üçüncü
       satırı yapar, yani başlık şeridiyle aynı düzlemde, kaymaz alanda. */
    var _govde=_main.querySelector('.oda-govde')||_main;
    /* `extra: gorus` odası (SİSTEM): kamera görüşü + ses kimliği kartları (G8). Panel kendi `durum` uçlarına
       sorar; iki bayrak da kapalıysa (varsayılan) 404 alır ve kap gizli kalır. */
    if(cat.extra==='gorus' && window.YukiGorusPanel){
      var _gp=document.createElement('div'); _gp.setAttribute('data-gorus-panel',''); _gp.hidden=true;
      _govde.appendChild(_gp);
      try{ window.YukiGorusPanel.kur(_gp); }catch(e){ console.warn('[HQ] görüş paneli açılamadı:',e); }
    }
    // SES & TTS kategorisi: motor ayarlarının ALTINA test/profil/referans panelini göm (eski SES sekmesi)
    if(cat.extra==='tts' && _ttsP){
      _govde.appendChild(_ttsP);
      _ttsP.style.display='';
      /* Ek panelin içindeki, karşılığı olmayan özelliğe ait bölümleri de düş.
         Ayarı gizleyip aynı özelliğin dosya yükleme yüzeyini bırakmak,
         gizlemenin çözdüğü kusurun ta kendisi olurdu. */
      _ttsP.querySelectorAll('[data-ayar]').forEach(function(blok){
        var ay=_schema.find(function(s){return s.key===blok.dataset.ayar;});
        blok.style.display=(ay && ay.available===false)?'none':'';
      });
      /* İlk açılışta veriyi çek, sonraki her açılışta ELDEKİNİ yeniden çiz.
         Yeniden çizim dil değişiminin kapısı: `_dilTazeleyici.ayarlar`
         buraya `hqSelectCat` üzerinden geliyor ve panel `_ttsInited`
         kilidi yüzünden eski dilde donuyordu (Blok 9). */
      if(!_ttsInited){ _ttsInited=true; ttsInit(); }
      else _ttsCiz();
    }
    /* GÜVENLİK odası: kilit bölümünü canlı veriyle doldur + YÜZ panelini göm.
       Yüz eskiden üst sekmedeydi (`#tab-faces`); 2026-09-06'da geliştirici kararıyla
       buraya taşındı — kimlikle ilgili her şey tek odada.
       ⚠️ `_yukiFacesOk` kapısı BURADA da sorulur: özellik bir gün ücretli
       kademeye taşınırsa panel sessizce açık kalmasın (karakter kilidi dersi).
       Kapı kapalıysa panel çizilmez ama kilit bölümü durur — parola yüzden
       bağımsız bir özelliktir. */
    if(render==='guvenlik'){
      kilitDurumunuYukle();
      var _yuzKutu=_govde.querySelector('#hq-guvenlik-yuz');
      if(_facesP && window._yukiFacesOk && _yuzKutu){
        _yuzKutu.appendChild(_facesP);
        _facesP.style.display='';
        /* `kur()` her açılışta çağrılır: kütüphane bu arada indirilmiş, yüz
           kaydedilmiş ya da silinmiş olabilir. Panelin kendisi idempotent —
           içeriği baştan çizer. */
        if(window.YuzSekmesi&&window.YuzSekmesi.kur){
          try{ window.YuzSekmesi.kur(); }catch(e){ console.warn('[HQ] yüz paneli açılamadı:',e); }
        }
      }else if(_yuzKutu){
        /* Kapı KAPALI görünüyor — ama "kapalı" ile "henüz sorulmadı" aynı şey
           değil. Kilitli kurulumda kapı sayfa açılırken 401 alıp kapanmış
           olabilir (bkz. app-lock.js § kademe kapılarını tazele). Kullanıcıya
           "kullanılamıyor" demeden ÖNCE bir kez daha sor: yanlış cümle, çalışan
           bir özelliği yok sandırır. */
        _yuzKutu.insertAdjacentHTML('beforeend',
          '<p class="oda-prose" id="hq-yuz-durum">'+esc(t('guvenlik.yuz-kontrol'))+'</p>');
        if(typeof window.refreshFaceAccess==='function'){
          window.refreshFaceAccess().then(function(ok){
            if(_curCat!=='guvenlik') return;         // kullanıcı odayı değiştirdi
            if(ok){ hqSelectCat('guvenlik'); return; }  // taze cevapla yeniden çiz
            var d=document.getElementById('hq-yuz-durum');
            if(d) d.textContent=t('guvenlik.yuz-kullanilamaz');
          }).catch(function(){
            var d=document.getElementById('hq-yuz-durum');
            if(d) d.textContent=t('guvenlik.yuz-durum-okunamadi');
          });
        }else{
          var _d=document.getElementById('hq-yuz-durum');
          if(_d) _d.textContent=t('guvenlik.yuz-kullanilamaz');
        }
      }
    }
    /* 🔴 2026-08-28 (FAZ 9): "TÜM AYARLARI SIFIRLA" SEKİZ odanın da altında
       duruyordu. Sekiz kez tekrarlanan yıkıcı bir düğme iki şeyi birden
       bozuyor: ① oda-özel olmayan bir eylemi oda-özel gösteriyor — kullanıcı
       "Ses odasındaki sıfırla yalnız sesi mi sıfırlar?" diye okuyor (hayır,
       hepsini) ② her odanın kapanışını kırmızıya boyuyor. Tek yere indi:
       Sistem odası, yani ayarların en dibi. Ötekiler artık sessiz bitiyor. */
    /* Kategori KİMLİĞİ değil, kategorinin İLAN ETTİĞİ şey sorulur — backend
       `extra: "sifirla"` diyorsa bu oda sıfırlamayı taşır. Sabit kimlik yazmak
       bu projede kapalı bir kusur sınıfı (backend/tests/test_ayar_kategorileri.py). */
    if((cat.bolumler||[]).indexOf('sifirla')>=0){
      var eylem=document.createElement('div');
      eylem.className='oda-bolum';
      eylem.innerHTML='<h4 class="oda-bolum-bas">'+esc(t('oda.sifirla-bas'))+'</h4>'
        +'<p class="oda-prose">'+esc(t('oda.sifirla-metin'))+'</p>'
        +'<div class="oda-eylem"><button type="button" class="dg dg-yikici" id="ay-sifirla" '
        +'onclick="hqResetSettings()">'+esc(t('oda.sifirla-dugme'))+'</button></div>'
        +'<div id="ay-sifirla-kutu" class="ay-onizleme" hidden></div>';
      _govde.appendChild(eylem);
    }
  };
  /* ── Satır (2026-09-27 · kişisel ed907af/7e12a2d "KONTROL MASASI" satırı, ürüne yeniden yazıldı) ──
     Ad · ne işe yarar · ne zaman geçerli (HEMEN / YENİDEN BAŞLATINCA) · değiştirdiysen
     varsayılanı + "varsayılana dön". Kişiseldeki 7 bölüm rayı TAŞINMADI: üründe kategoriler
     sol menüde, panel içi ikinci menü yasak (D5, test_ayar_menusu).
     "Ne zaman geçerli" şemanın `needs_restart`'ından gelir — kişiselin `canli` işaretleri
     kopyalanmadı: üründe model adları modül başında okunuyor (yeniden başlatma ister). */
  function _ayNe(s){
    var a = 'ayar-ne.' + String(s.key || '').toLowerCase().replace(/_/g, '-');
    var m = t(a);
    return (m === a) ? '' : m;
  }
  /* Seçenek etiketi sözlükten ("passive" → "Pasif — …"); anahtar yoksa değerin kendisi (model adları) */
  function _aySecenek(s, o){
    var a = 'ayar-secenek.' + String(s.key).toLowerCase().replace(/_/g, '-') + '.' + String(o).toLowerCase();
    var m = t(a);
    return (m === a) ? String(o) : m;
  }
  function _ayDeger(v){
    if(v === true) return t('oda.deger-acik');
    if(v === false) return t('oda.deger-kapali');
    if(v == null || v === '') return t('oda.deger-bos');
    /* Sayı dilin biçimiyle: kutu "0,05" gösterirken varsayılan "0.01" yazıyordu (tur 1) */
    if(typeof v === 'number') return v.toLocaleString(yerelKod(), {maximumFractionDigits: 4});
    return String(v);
  }
  function _ayDurum(key, metin, sinif){
    var el = document.getElementById('ay-d-' + key);
    if(el){ el.textContent = metin || ''; el.className = 'ay-durum' + (sinif ? ' ' + sinif : ''); }
  }
  function renderSetRow(s){
    var v=_vals[s.key], k=esc(s.key), ad=esc(_ayarAd(s));
    var sonra = (s.needs_restart!==false);
    var zaman = '<span class="ay-zaman'+(sonra?'':' canli')+'">'+esc(t(sonra?'oda.zaman-restart':'oda.zaman-hemen'))+'</span>';
    var ctl='';
    /* Anahtar = <button role="switch">: div'di → klavyeyle açılmıyor,
       ekran okuyucu durumunu duyurmuyordu. Durum aria-checked'te de tutulur. */
    if(s.type==='toggle'){ ctl='<button type="button" role="switch" aria-checked="'+(v?'true':'false')+'" aria-label="'+ad+'" class="hq-toggle'+(v?' on':'')+'" onclick="hqToggle(this,\''+k+'\')"></button>'; }
    else if(s.type==='number'){
      /* Kaydırıcı yerine sayı kutusu: kaydırıcı değeri göstermiyor, 0.001 adımlı eşikte
         istenen değere gelmek imkânsızdı. Şema min'inin altındaki eski kayıt min gösterilir. */
      var g = (v==null) ? s.min : Math.max(Number(v), Number(s.min));
      /* type="number" DEĞİL: tarayıcı sayıyı KENDİ diliyle yazıyordu ("0,05") — iz satırı arayüz
         diliyle ("0.01") yazınca aynı satırda iki ayraç çıkıyordu (goz 09-27). Biçim de ayrıştırma da bizde. */
      ctl='<input class="girdi ay-sayi" type="text" inputmode="decimal" value="'+esc(_ayDeger(Number(g)))+'" aria-label="'+ad+'" onchange="hqSayi(this,\''+k+'\')">'; }
    else if(s.type==='select'){ ctl='<select class="hq-select" aria-label="'+ad+'" onchange="hqSet(\''+k+'\',this.value)">'+(s.options||[]).map(function(o){return '<option value="'+esc(o)+'"'+(String(o)===String(v)?' selected':'')+'>'+esc(_aySecenek(s,o))+'</option>';}).join('')+'</select>'; }
    else { ctl='<input class="girdi ay-metin" type="text" spellcheck="false" value="'+esc(v)+'" aria-label="'+ad+'" onchange="hqSet(\''+k+'\',this.value)">'; }
    var ne = _ayNe(s);
    var iz = (_degisti.indexOf(s.key) >= 0)
      ? '<div class="ay-iz"><span class="ay-degisti">'+esc(t('oda.degistirdin',{deger:_ayDeger(_varsayilan[s.key])}))+'</span>'
        + '<button type="button" onclick="hqVarsayilan(\''+k+'\')">'+esc(t('oda.varsayilana-don'))+'</button></div>'
      : '';
    return '<div class="ay-satir'+(iz?' degisti':'')+'" data-key="'+k+'">'
      + '<div class="ay-ad">'+ad+'</div>'
      + '<div class="ay-ctl">'+ctl+zaman+'</div>'
      + (ne ? '<p class="ay-ne">'+esc(ne)+'</p>' : '')
      + iz + '<p class="ay-durum" id="ay-d-'+k+'" aria-live="polite"></p></div>';
  }
  window.hqToggle=async function(el,key){
    if(el.dataset.mesgul) return;
    el.dataset.mesgul='1';
    var on=!el.classList.contains('on');
    el.classList.toggle('on',on); el.setAttribute('aria-checked',on?'true':'false');
    /* Kaydedilemezse görsel GERİ alınır — "açık görünüyor ama kaydedilmedi" en kötü hâl */
    if(!(await hqSet(key,on))){ el.classList.toggle('on',!on); el.setAttribute('aria-checked',!on?'true':'false'); }
    delete el.dataset.mesgul;
  };
  window.hqSayi=function(el,key){
    var v=parseFloat(String(el.value).trim().replace(/\s/g,'').replace(',','.')), s=_schema.find(function(x){return x.key===key;})||{};
    if(!isFinite(v) || v<Number(s.min) || v>Number(s.max)){
      _ayDurum(key, t('oda.sayi-araligi',{min:_ayDeger(Number(s.min)),max:_ayDeger(Number(s.max))}), 'hata'); el.setAttribute('aria-invalid','true'); return;
    }
    el.removeAttribute('aria-invalid');
    hqSet(key,v);
  };
  function _ozellikTazele(){
    try{ if(window.YukiOzellik) window.YukiOzellik.tazele(); }catch(_){}
    document.querySelectorAll('iframe').forEach(function(f){
      try{ var w=f.contentWindow; if(w && w.YukiOzellik) w.YukiOzellik.tazele(); }catch(_){}   // başka köken → atla
    });
  }
  /* Dönüş: true = kaydedildi (anahtar görseli geri alınabilsin diye) */
  window.hqSet=async function(key,value){
    _ayDurum(key, t('oda.kaydediliyor'));
    try{ var r=await af('/api/settings/'+encodeURIComponent(key),{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({value:value})});
      var d=await r.json().catch(function(){ return {}; });
      if(r.ok&&d.ok){
        _vals[key]=d.value;
        _degisti=_degisti.filter(function(x){return x!==key;});
        if(d.value!==_varsayilan[key]) _degisti.push(key);
        /* 🔑 geliştiricinin isteğinin ASIL yeri burası: "herhangi bir ayarı
           değiştirdikten sonra onu kullanabilirler". Şerit yalnız gerçekten
           gerektiğinde çıkıyor — her kaydetmede çıksaydı gürültü olurdu. */
        if(d.needs_restart) yenidenBaslatSeridi();
        /* Bayraklı özellik canlı açılıp kapanır (FITNES, g4 11-12): giriş düğmeleri ozellik.js
           kapısında — ana sayfada ve açık iframe'lerde (PLAN) kapıyı yeniden sor. */
        if(key==='FITNES') _ozellikTazele();
        _satirTazele(key);
        _ayDurum(key, t(d.needs_restart?'oda.kaydedildi-restart':'oda.kaydedildi-gecerli'), 'ok');
        return true; }
      _ayDurum(key, _ucHatasi('oda.kaydedilemedi', d), 'hata');
    }catch(e){ _ayDurum(key, agHatasi(e), 'hata'); }
    return false;
  };
  /* Tek satırı yerinde yeniden çiz ("değiştirdin" izi gelsin/gitsin) — tüm odayı
     çizmek odağı ve kaydırmayı sıfırlardı. */
  function _satirTazele(key){
    var eski=document.querySelector('.ay-satir[data-key="'+key+'"]');
    var s=_schema.find(function(x){return x.key===key;});
    if(!eski || !s) return;
    var tmp=document.createElement('div'); tmp.innerHTML=renderSetRow(s);
    eski.replaceWith(tmp.firstChild);
  }
  window.hqVarsayilan=async function(key){
    try{
      var r=await af('/api/settings/'+encodeURIComponent(key),{method:'DELETE'});
      var d=await r.json().catch(function(){ return {}; });
      if(!r.ok) throw _durumluHata(r, d);
      _vals[key]=d.value;
      _degisti=_degisti.filter(function(x){return x!==key;});
      if(d.needs_restart) yenidenBaslatSeridi();
      _satirTazele(key);
      _ayDurum(key, t(d.needs_restart?'oda.varsayilana-dondu-restart':'oda.varsayilana-dondu'), 'ok');
    }catch(e){ _ayDurum(key, e && e.durum ? _ucHatasi('oda.kaydedilemedi', e.govde) : agHatasi(e), 'hata'); }
  };
  /* ── Görünüm & Performans (kategori render='gfx') ─────────────────────────
     R0 ölçümü (2026-08-12): HALKA modu referans makinede %35,3 CPU yiyor ve
     HAFİF kademesi CPU'yu düşürüyor (−%46, yeniden yazımdan sonra). İki ayar
     vardı ama ikisine de AYAR panelinden ulaşılamıyordu: HAFİF `⋯` menüsünde
     gömülüydü, `PerfTier.setOverride()` API'sini çağıran hiçbir arayüz yoktu.
     Yanlış sınıflanan makinedeki kullanıcının kendini kurtarma yolu bu bölüm.

     ⚠️ İki kavram AYRI, ekranda da ayrı duruyor:
       · Gfx (data-gfx)   → KULLANICI seçimi (normal / hafif)
       · PerfTier (data-perf) → DONANIM tespiti (auto / low / mid / high)
     Tek kutuda birleştirmek "aynı soruya iki cevap" üretirdi. */
  var PERF_KADEMELERI=[
    {key:'auto', label:'gorunum.perf.auto'},
    {key:'low',  label:'gorunum.perf.low'},
    {key:'mid',  label:'gorunum.perf.mid'},
    {key:'high', label:'gorunum.perf.high'}
  ];
  /* ── Güvenlik odası ────────────────────────────────────────────────────
     İki bölüm: açılış parolası (bu dosya çizer) + yüz tanıma paneli
     (`#faces-root`, faces.js çizer, aşağıda gövdeye gömülür).

     🔑 Parola durumu SENKRON çizilemez: `/api/lock/status` ağ çağrısıdır.
     İskelet önce çizilir, `kilitDurumunuYukle()` sonra doldurur. Odanın
     tamamını `await` etmek, ağ yavaşladığında Güvenlik'e tıklayan kullanıcıya
     boş ekran gösterirdi. */
  function renderGuvenlikBolumu(){
    /* `.oda-bolum` deseni: kart içinde kart YOK, hiyerarşi başlık + boşlukla
       kurulur (hq.css'teki kural). `.oda-bolum + .oda-bolum` aradaki ayraç
       çizgisini kendisi çiziyor — elle ayraç eklemek onu ikiye katlardı. */
    return '<div class="oda-bolum" id="hq-kilit-bolum">'
      + '<h4 class="oda-bolum-bas">'+esc(t('kilit.bolum-bas'))+'</h4>'
      + '<p class="oda-prose">'+esc(t('kilit.yukleniyor'))+'</p>'
      + '</div>'
      + '<div class="oda-bolum" id="hq-guvenlik-yuz">'
      + '<h4 class="oda-bolum-bas">'+esc(t('guvenlik.yuz-bas'))+'</h4>'
      + '</div>';
  }

  /* Kilit bölümünü canlı veriyle doldur. `hqSelectCat` bittikten SONRA çağrılır. */
  async function kilitDurumunuYukle(){
    var kok=document.getElementById('hq-kilit-bolum');
    if(!kok) return;
    var d=null;
    try{
      var r=await (window.authFetch||fetch)(BASE+'/api/lock/status');
      if(r.ok) d=await r.json();
    }catch(_){ }
    if(!kok.isConnected) return;   // kullanıcı bu arada odayı değiştirdi
    var bas='<h4 class="oda-bolum-bas">'+esc(t('kilit.bolum-bas'))+'</h4>';
    if(!d){
      kok.innerHTML=bas+'<p class="oda-prose">'+esc(t('kilit.durum-okunamadi'))+'</p>';
      return;
    }
    var h=bas;
    if(d.kurulu){
      h+='<p class="oda-prose">'+esc(t('kilit.acik'))+'</p>';
      h+='<div class="hq-kilit-form">'
        +'<input type="password" class="hq-input" id="hq-kilit-mevcut" placeholder="'+esc(t('kilit.mevcut-parola'))+'" autocomplete="current-password">'
        +'<input type="password" class="hq-input" id="hq-kilit-yeni" placeholder="'+esc(t('kilit.yeni-parola-min',{n:d.min_uzunluk}))+'" autocomplete="new-password">'
        +'<button class="hq-btn" onclick="hqKilitDegistir()">'+esc(t('kilit.degistir'))+'</button>'
        +'<button class="hq-btn danger" onclick="hqKilitKaldir()">'+esc(t('kilit.kaldir'))+'</button>'
        +'<button class="hq-btn" onclick="hqSimdiKilitle()">'+esc(t('kilit.simdi-kilitle'))+'</button>'
        +'</div>';
      /* Yüzle giriş DURUMU burada söylenir. Kullanıcı yüzünü kaydetmiş olsa bile
         kütüphane inmemişse açılışta yüz seçeneği ÇIKMAZ — bunu kilidi kurduktan
         sonra öğrenmek kötü bir sürpriz olurdu.

         🔴 "Yüzü kayıtlı" ile "yüzüyle GİREBİLİR" ayrı şeyler (canlı turda
         ölçüldü): tanıma listesine eklenmek `register`, açılış hakkı `enroll`.
         Kullanıcıya bu ayrımı ANLATMIYORUZ — tek düğmeye indiriyoruz. */
      /* Yüz paneli görünüyorsa bu satırı ONUN kimlik kartı söyler (sahip, örnek, deneme) —
         iki yerde aynı durum ayrışır. Kademe kapalıysa kart yok, satır burada kalır. */
      if(window._yukiFacesOk){
        /* kimlik kartında */
      }else if(d.yuzle_girilebilir){
        h+='<p class="oda-prose">'+esc(t('kilit.yuzle-girilebilir'))+'</p>';
      }else{
        h+='<p class="oda-prose">'+esc(t('kilit.yalniz-parola'))+'</p>'
          +'<div class="hq-kilit-form">'
          +'<button class="hq-btn" onclick="hqYuzuAcilisaEkle(this)">'+esc(t('kilit.yuzumu-ekle'))+'</button>'
          +'</div>'
          +'<p class="oda-prose">'+esc(t('kilit.kamera-notu'))+'</p>';
      }
    }else{
      h+='<p class="oda-prose">'+esc(t('kilit.kapali'))+'</p>';
      h+='<div class="hq-kilit-form">'
        +'<input type="password" class="hq-input" id="hq-kilit-yeni" placeholder="'+esc(t('kilit.parola-min-karakter',{n:d.min_uzunluk}))+'" autocomplete="new-password">'
        +'<button class="hq-btn" onclick="hqKilitKur()">'+esc(t('kilit.kur'))+'</button>'
        +'</div>';
    }
    /* 🔴 DÜRÜSTLÜK — vitrinde de aynı cümle durmalı. Kilit uygulamanın kapısıdır,
       diskin değil: makinede dosyalara erişebilen biri sohbet geçmişini yine de
       okuyabilir. "Şifreliyorum" demek ölçülmemiş iddia olurdu. */
    h+='<p class="oda-prose oda-prose-uyari">'+t('kilit.durustluk')+'</p>';
    kok.innerHTML=h;
  }

  async function kilitIstek(yol, govde, basariMesaji){
    try{
      var r=await (window.authFetch||fetch)(BASE+yol,{
        method:'POST', headers:{'Content-Type':'application/json'},
        body:JSON.stringify(govde||{})
      });
      var d=null; try{ d=await r.json(); }catch(_){ }
      if(!r.ok){
        toast((d&&d.detail)||t('kilit.islem-basarisiz'),'uyari');
        return false;
      }
      toast(basariMesaji,'basari');
      return true;
    }catch(e){
      toast(t('kilit.sunucuya-ulasilamadi'),'uyari');
      return false;
    }
  }

  window.hqKilitKur=async function(){
    var yeni=(document.getElementById('hq-kilit-yeni')||{}).value||'';
    if(!yeni){ toast(t('kilit.parola-bos'),'uyari'); return; }
    if(await kilitIstek('/api/lock/set',{yeni:yeni},t('kilit.kuruldu'))) kilitDurumunuYukle();
  };

  window.hqKilitDegistir=async function(){
    var mevcut=(document.getElementById('hq-kilit-mevcut')||{}).value||'';
    var yeni=(document.getElementById('hq-kilit-yeni')||{}).value||'';
    if(!mevcut||!yeni){ toast(t('kilit.iki-alan'),'uyari'); return; }
    if(await kilitIstek('/api/lock/set',{mevcut:mevcut,yeni:yeni},t('kilit.degistirildi'))) kilitDurumunuYukle();
  };

  window.hqKilitKaldir=async function(){
    var mevcut=(document.getElementById('hq-kilit-mevcut')||{}).value||'';
    if(!mevcut){ toast(t('kilit.kaldirmak-icin-parola'),'uyari'); return; }
    if(await kilitIstek('/api/lock/disable',{parola:mevcut},t('kilit.kaldirildi'))) kilitDurumunuYukle();
  };

  window.hqYuzuAcilisaEkle=async function(btn){
    if(!window.AppLock||!window.AppLock.sahipKaydet){
      toast(t('kilit.yuz-girisi-yok'),'uyari'); return;
    }
    var eski=btn?btn.textContent:'';
    if(btn){ btn.disabled=true; btn.textContent=t('kilit.kameraya-bak'); }
    try{
      var s=await window.AppLock.sahipKaydet();
      toast(s.mesaj, s.ok?'basari':'uyari');
      if(s.ok) kilitDurumunuYukle();
    } finally {
      if(btn){ btn.disabled=false; btn.textContent=eski; }
    }
  };

  window.hqSimdiKilitle=async function(){
    if(await kilitIstek('/api/lock/lock',{},t('kilit.kilitlendi'))){
      /* Oturum düştü: elimizdeki token artık geçersiz. Sayfayı yeniden yüklemek
         kilit ekranını doğal yoldan getirir — kendi kendine "kilitli görün"
         demeye çalışmak, arka tarafla ayrışabilecek ikinci bir gerçek üretirdi. */
      if(window.AppLock&&window.AppLock.tokenSil) window.AppLock.tokenSil();
      location.reload();
    }
  };

  function renderGfxBolumu(){
    var h='';
    var G=window.Gfx;
    if(G&&G.TIERS){
      var secili=G.get();
      h+='<div class="hq-set-row"><div class="hq-set-label">'+esc(t('gorunum.grafik-kalitesi'))
        +'<span class="hq-live-badge">'+esc(t('hq.rozet.aninda'))+'</span></div><div class="hq-set-ctl">'
        +'<select class="hq-select" onchange="hqSetGfx(this.value)">'
        +G.TIERS.map(function(kad){
            return '<option value="'+esc(kad.key)+'"'+(kad.key===secili?' selected':'')+'>'
                 +esc(kad.icon+' '+t(kad.label)+' — '+t(kad.desc))+'</option>';
          }).join('')
        +'</select></div></div>';
    }
    var P=window.PerfTier;
    if(P){
      var bilgi=P.info();
      var kademe=bilgi.mode==='manuel'?bilgi.tier:'auto';
      h+='<div class="hq-set-row"><div class="hq-set-label">'+esc(t('gorunum.perf-kademesi'))
        +'<span class="hq-live-badge">'+esc(t('hq.rozet.aninda'))+'</span></div><div class="hq-set-ctl">'
        +'<select class="hq-select" onchange="hqSetPerf(this.value)">'
        +PERF_KADEMELERI.map(function(k){
            return '<option value="'+k.key+'"'+(k.key===kademe?' selected':'')+'>'
                 +esc(t(k.label))+'</option>';
          }).join('')
        +'</select></div></div>';
      h+='<div class="hq-set-row"><div class="hq-set-label">'+esc(t('gorunum.bu-makine'))+'</div>'
        +'<div class="hq-set-ctl"><span class="hq-set-teshis">'+esc(perfTeshisMetni(bilgi))
        +'</span></div></div>';
    }
    return h || '<div class="intel-empty">'+esc(t('gorunum.yuklenemedi'))+'</div>';
  }
  /* 🔴 `navigator.deviceMemory` 8'de TAVANLANABİLİR: W3C listesi 0.25…8 ile sınırlı,
     yani **8 değeri "8 veya daha fazla" demektir**. 2026-08-12'de bu tam olarak
     yanlış teşhis üretti — referans makine "8 GB" sanıldı, gerçekte 12 GB'dı ve
     darboğaz bellek değil CPU'ydu. Ham sayıyı çıplak yazmak aynı yanılgıyı
     müşteriye de yaptırır.
     ⚠️ Uyarı YALNIZ 8'de veriliyor: bazı sürümler gerçek değeri bildiriyor
     (bu makinede 32 ölçüldü) ve orada "üstünü bildirmez" demek yanlış olurdu. */
  function perfTeshisMetni(b){
    var p=[];
    p.push(b.cores!=null?t('gorunum.teshis.cekirdek',{n:b.cores}):t('gorunum.teshis.islemci-yok'));
    p.push(b.memory==null ? t('gorunum.teshis.bellek-yok')
         : b.memory===8   ? t('gorunum.teshis.bellek-tavan')
         :                  t('gorunum.teshis.bellek',{n:b.memory}));
    var son=(b.mode==='manuel')
      ? t('gorunum.teshis.elle',{kademe:b.tier,oto:b.detected})
      : t('gorunum.teshis.otomatik',{kademe:b.detected});
    return p.join(' · ')+' → '+son;
  }
  window.hqSetGfx=function(v){
    if(window.Gfx&&window.Gfx.set(v)){ toast(t('gorunum.gfx-degisti',{kademe:v}),'ok'); }
    else toast(t('gorunum.gfx-degismedi'),'err');
  };
  window.hqSetPerf=function(v){
    if(!window.PerfTier){ toast(t('gorunum.perf-degismedi'),'err'); return; }
    var yeni=window.PerfTier.setOverride(v);
    toast(t('gorunum.perf-degisti',{kademe:(v==='auto'?t('gorunum.perf-otomatik',{kademe:yeni}):yeni)}),'ok');
    hqSelectCat(_curCat);   // teşhis satırı tazelensin — bayat bilgi teşhisi bozar
  };

  function renderLiveTrio(){
    var h='';
    var L=_live.language;
    /* İki eksen (2026-10-04): önce ARAYÜZ (tr/en), sonra KONUŞMA (tr/en/ja). */
    if(L&&L.arayuz_available){ var ad=(window.YukiDil&&window.YukiDil.al)?window.YukiDil.al():L.arayuz; h+='<div class="hq-set-row"><div class="hq-set-label">'+esc(t('canli.arayuz-dili'))+' <span class="hq-live-badge">'+esc(t('hq.rozet.aninda'))+'</span></div><div class="hq-set-ctl"><select class="hq-select" onchange="hqSetArayuzDili(this.value)">'+L.arayuz_available.map(function(o){return '<option value="'+esc(o.code)+'"'+(o.code===ad?' selected':'')+'>'+esc(o.label)+'</option>';}).join('')+'</select></div></div>'; }
    if(L){ var kd=(window.YukiDil&&window.YukiDil.konusma&&window.YukiDil.konusma())||L.current; h+='<div class="hq-set-row"><div class="hq-set-label">'+esc(t('canli.asistan-dili'))+' <span class="hq-live-badge">'+esc(t('hq.rozet.aninda'))+'</span></div><div class="hq-set-ctl"><select class="hq-select" onchange="hqSetLanguage(this.value)">'+(L.available||[]).map(function(o){return '<option value="'+esc(o.code)+'"'+(o.code===kd?' selected':'')+'>'+esc(o.label)+'</option>';}).join('')+'</select></div></div>'; }
    var C=_live.character;
    if(C){ h+='<div class="hq-set-row"><div class="hq-set-label">'+esc(t('canli.karakter'))+' <span class="hq-live-badge">'+esc(t('hq.rozet.aninda'))+'</span></div><div class="hq-set-ctl"><select class="hq-select" onchange="hqSetCharacter(this.value)">'+(C.available||[]).map(function(o){var k=o.name||o.key||o.id||o; var lbl=o.label||o.title||k; var lock=o.locked?' 🔒':''; return '<option value="'+esc(k)+'"'+(k===C.current?' selected':'')+(o.locked?' disabled':'')+'>'+esc(lbl)+lock+'</option>';}).join('')+'</select></div></div>'; }
    var M=_live.llm;
    if(M&&M.presets){ var opts=''; Object.keys(M.presets).forEach(function(p){ (M.presets[p]||[]).forEach(function(m){ opts+='<option value="'+esc(p)+'||'+esc(m.id)+'"'+(m.id===M.model?' selected':'')+'>['+esc(p)+'] '+esc(m.label||m.id)+'</option>'; }); });
      h+='<div class="hq-set-row"><div class="hq-set-label">'+esc(t('canli.llm-modeli'))+' <span class="hq-live-badge">'+esc(t('hq.rozet.aninda'))+'</span></div><div class="hq-set-ctl"><select class="hq-select" onchange="hqSetModel(this.value)">'+opts+'</select></div></div>'; }
    return h || '<div class="intel-empty">'+esc(t('canli.yuklenemedi'))+'</div>';
  }
  /* 🔑 2026-09-18 (FAZ 2): burası `/api/language`'e KENDİ POST'unu atıyordu —
     yani dil değiştirmenin ikinci yoluydu. Sunucu güncelleniyordu ama
     `dil.js`'in bildiği aktif dil, `<html lang>` özniteliği ve localStorage
     önbelleği ESKİ kalıyordu: AYAR'dan dil değiştiren kullanıcıda arayüz ile
     sunucu ayrışıyordu. Artık tek kapıdan (`YukiDil.ayarla`) geçiyor; o hem
     sunucuya yazar hem ekranı ve önbelleği hizalar. */
  /* 2026-10-04: `hqSetLanguage` KONUŞMA dilidir (`konusmaAyarla`), arayüz `hqSetArayuzDili`. */
  window.hqSetLanguage=async function(v){ try{ var D=window.YukiDil; if(!D){ toast(t('canli.dil-katmani-yok'),'err'); return; } var d=await D.konusmaAyarla(v); var ok=!!(d&&d.ok!==false); toast(ok?(d.mesaj||t('canli.dil-degisti',{kod:v})):t('canli.dil-degismedi'), ok?'ok':'err'); }catch(e){toast(agHatasi(e),'err');} };
  window.hqSetArayuzDili=async function(v){ try{ var D=window.YukiDil; if(!D){ toast(t('canli.dil-katmani-yok'),'err'); return; } var d=await D.ayarla(v); var ok=!!(d&&d.ok!==false); toast(ok?t('canli.dil-degisti',{kod:v}):t('canli.dil-degismedi'), ok?'ok':'err'); }catch(e){toast(agHatasi(e),'err');} };
  window.hqSetCharacter=async function(v){ try{ var r=await af('/api/character',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({name:v})}); var d=await r.json(); toast(d.ok!==false?t('canli.karakter-degisti',{ad:v}):esc(d.error||t('hata.bilinmeyen')), d.ok!==false?'ok':'err'); }catch(e){toast(agHatasi(e),'err');} };
  window.hqSetModel=async function(v){ var p=v.split('||'); try{ var r=await af('/api/llm/config',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({provider:p[0],model:p[1]})}); var d=await r.json(); toast(d.ok!==false?t('canli.model-degisti',{ad:p[1]}):esc(d.error||t('hata.bilinmeyen')), d.ok!==false?'ok':'err'); }catch(e){toast(agHatasi(e),'err');} };
  /* Sıfırlama İKİ ADIM + ÖNİZLEME (confirm() yok — ürün kuralı). İlk basış neyin
     değişeceğini ÖLÇÜP listeler (şimdi → sonra); kişiselde önizleme "4 ayar" sanılanın
     5 olduğunu gösterdi — sıfırlama varsayılanı açık bir özelliği AÇABİLİR.
     Dil ve karakter sesleri korunur (config_manager.SIFIRLAMADA_KORUNAN). */
  window.hqResetSettings=async function(){
    var kutu=document.getElementById('ay-sifirla-kutu'); if(!kutu) return;
    kutu.hidden=false;
    /* Önizleme açıkken ilk düğme gizlenir — iki dolu kırmızı düğme hangisinin onay olduğunu söylemiyordu */
    var ilk=document.getElementById('ay-sifirla'); if(ilk) ilk.hidden=true;
    kutu.innerHTML='<p class="ay-not">'+esc(t('oda.sifirla-bakiliyor'))+'</p>';
    try{
      var r=await af('/api/settings/reset-preview'); var d=await r.json().catch(function(){ return {}; });
      if(!r.ok) throw _durumluHata(r, d);
      var liste=d.degisen||[];
      if(!liste.length){ kutu.innerHTML='<p class="ay-not">'+esc(t('oda.sifirla-degisen-yok'))+'</p>'; return; }
      kutu.innerHTML='<p class="ay-onizleme-bas">'+esc(tc('oda.sifirla-liste-bas', liste.length))+'</p><ul>'
        + liste.map(function(x){
            var s=_schema.find(function(y){return y.key===x.key;})||{key:x.key,label:x.label};
            /* Ok SVG: yazıtipi okları 1× ölçekte kıl çizgisi kalıyordu (goz 09-27, iki tur) */
            return '<li><b>'+esc(_ayarAd(s))+'</b><span class="eski">'+esc(_ayDeger(x.simdi))+'</span>'
              +'<svg class="ok" viewBox="0 0 16 10" aria-label="→"><path d="M1 5h13M10 1l4 4-4 4" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"/></svg>'
              +'<span class="yeni">'+esc(_ayDeger(x.sonra))+'</span></li>';
          }).join('')
        + '</ul><p class="ay-not">'+esc(t('oda.sifirla-korunan'))+'</p>'
        + '<div class="oda-eylem"><button type="button" class="dg dg-yikici" onclick="hqResetOnayla()">'+esc(t('oda.sifirla-evet'))+'</button>'
        + '<button type="button" class="dg dg-sessiz" onclick="hqResetVazgec()">'+esc(t('oda.vazgec'))+'</button></div>';
    }catch(e){ kutu.innerHTML='<p class="ay-not alan-hata">'+esc(e && e.durum ? _ucHatasi('sifirla.olmadi', e.govde) : agHatasi(e))+'</p>'; }
  };
  window.hqResetVazgec=function(){ var k=document.getElementById('ay-sifirla-kutu'); if(k){ k.hidden=true; k.innerHTML=''; }
    var ilk=document.getElementById('ay-sifirla'); if(ilk){ ilk.hidden=false; ilk.focus(); } };
  window.hqResetOnayla=async function(){
    try{ var r=await af('/api/settings/reset?confirm=true',{method:'PATCH'}); var d=await r.json().catch(function(){ return {}; });
      if(r.ok&&d.ok){ toast(t('sifirla.oldu'),'warn'); _curCat=null; await hqLoadSettings(); yenidenBaslatSeridi(); }
      else toast(_ucHatasi('sifirla.olmadi', d),'err');
    }catch(e){toast(agHatasi(e),'err');}
  };

  // ════════ MODLAR · BAŞLATMA IZGARASI ( panel 7, 2026-09-27) ════════
  /* Kişisel 097779b'nin tasarımı ürüne YENİDEN yazıldı (kişiselin kodu ham Türkçe +
     Hyprland/Claude'a özgü metin taşıyordu). Panel bir BAŞLATMA ekranı: her mod bir kart
     (ne açar · hedef · tetik kelimeleri · durum · BAŞLAT); karta dokununca düzenleme formu
     ızgaranın yerini alır. Platforma duyarlı: alan/özel alan yalnız `features` izin verirse.

     Kapanan ürün kusurları (09-27 harita): silme `confirm()` ile · BAŞLAT çift tıkı
     engellemiyor, hata `detail`'ini atıyordu (409 "başlatıcı kapalı" kayboluyordu) · yükleme
     `r.ok`'a bakmıyordu (401'de "Henüz mod yok") · değer taşıyan inline onclick tek tırnakta
     kırılıyordu → kartlarda olay devri + data-* · Enter'a basılmamış çip kaydederken
     kayboluyordu · panel yalnız ilk açılışta yükleniyordu · Hyprland kısayol seçici hep boştu
     (regex `bind =` arıyor, yapılandırmalar `bindd`/`bindl` kullanıyor) → kaldırıldı. */
  var _modes=[],_sel=null,_hqApps=null,_hqWs=null,_mfWsSel=null,_mfSpSel=null;
  var _mdBaslatici=null;          // true/false/null(bilinmiyor) — GET /api/settings MODE_LAUNCHER_ENABLED
  var _mdSonuc={};                // id → {tur:'ok'|'uyari'|'err'|'suruyor', metin, t}
  var _mdHata=null;               // liste okunamadıysa HTTP durumu (0 = ağ)
  // Kurulu sistem yetenekleri — /api/modes/platform ile doldurulur. Varsayılan = Hyprland-tam
  // (ilk render bozulmasın); gerçek değer fetch sonrası gelir.
  var _hqPlatform={os:'linux',desktop:'hyprland',label:'—',
    features:{apps:true,workspaces:true,workspace_move:true,specials:true}};

  /* Her yardımcı okuma `r.ok`'a bakar: hata gövdesi veri sanılmasın (eskiden platform bilgisi
     401 gövdesiyle eziliyordu). Başarısızsa bir önceki değer korunur. */
  async function _mdOku(yol){ try{ var r=await af(yol); if(!r.ok) return null; return await r.json(); }catch(e){ return null; } }
  async function _hqFetchMeta(){
    var s=await Promise.all([_mdOku('/api/modes/platform'), _hqApps?null:_mdOku('/api/modes/apps'),
                             _hqWs?null:_mdOku('/api/modes/workspaces'), _mdOku('/api/settings')]);
    if(s[0]&&s[0].features) _hqPlatform=s[0];
    if(s[1]) _hqApps=s[1].apps||[];
    if(s[2]) _hqWs=s[2];
    var v=s[3]&&s[3].values;
    _mdBaslatici = v && ('MODE_LAUNCHER_ENABLED' in v) ? !!v.MODE_LAUNCHER_ENABLED : null;
    _updateSysBadge();
  }
  function _updateSysBadge(){
    var el=document.getElementById('hq-modes-sys'); if(!el) return;
    var lbl=_hqPlatform.label||_hqPlatform.desktop||'—';
    el.textContent=lbl;
    el.title=t('hq.modlar.sistem-rozeti-title');
  }

  /* Panel HER açılışta tazelenir (switchHqTab). Açık form KİRLİYSE ızgaraya dönülmez —
     yarım kalmış düzenleme panel değişimiyle silinmesin. */
  var _mdYuklendi=false;
  window.hqLoadModes=async function(){
    /* İlk yüklemede liste gelene kadar "Henüz mod yok" GÖRÜNMEZ (markup'ta gizli) — boş durum
       ancak sunucu gerçekten boş liste dönünce söylenir. */
    if(!_mdYuklendi){ var l0=document.getElementById('hq-modes-list'); if(l0) l0.innerHTML='<p class="md-yukleniyor">'+esc(t('hq.modlar.yukleniyor'))+'</p>'; }
    await _hqFetchMeta();
    _mdHata=null;
    try{
      var r=await af('/api/modes/list');
      if(!r.ok) _mdHata=r.status; else { var d=await r.json(); _modes=d.modes||[]; }
    }catch(e){ _mdHata=0; }
    _mdYuklendi=true;
    var f=document.getElementById('hq-mode-form');
    var formAcik=f && f.style.display!=='none';
    if(formAcik && _modFormuKirli()) { renderModesList(); return; }
    if(formAcik) _mdIzgarayaDon(); else renderModesList();
  };

  function _mdAppAd(bin){
    var a=(_hqApps||[]).find(function(x){ return x.binary===bin; });
    return a ? (a.label||a.binary) : bin;
  }
  /* "Ne açar" komutlardan türetilir — açıklama alanı serbest metin, yalan söyleyebilir. */
  function _mdNeAcar(m){
    var p=[], apps=m.apps||[];
    if(apps.length) p.push(apps.slice(0,3).map(_mdAppAd).join(', ')+(apps.length>3?' +'+(apps.length-3):''));
    return p.length ? p.join(' · ') : t('hq.modlar.kart.hicbir-sey');
  }
  /* {metin, yok}: özel alan bu masaüstünde yoksa çip sessizce KAYBOLMAZ, "burada yok" der (goz tur 2) */
  function _mdHedef(m){
    var F=_hqPlatform.features;
    if(!F) return null;
    if(m.special) return F.specials ? {metin:t('hq.modlar.kart.ozel',{ad:m.special})} : {metin:t('hq.modlar.kart.ozel-yok',{ad:m.special}),yok:true};
    if(F.workspaces && m.workspace!=null) return {metin:t('hq.modlar.kart.alan',{n:m.workspace})};
    return null;
  }
  /* Kart altındaki tek satır: öncelik sırası = şu an olan > son sonuç (12 sn) > engel > bilgi */
  function _mdDurum(m){
    var s=_mdSonuc[m.id];
    if(s && (s.tur==='suruyor' || Date.now()-s.t<12000)) return s;
    if(m.enabled===false) return {tur:'soluk',metin:t('hq.modlar.kart.kapali')};
    if(_mdBaslatici===false) return {tur:'soluk',metin:t('hq.modlar.kart.baslatici-kapali')};
    var gorulen={}, cift=null;
    (m.apps||[]).forEach(function(a){ if(gorulen[a]) cift=a; gorulen[a]=1; });
    if(cift) return {tur:'uyari',metin:t('hq.modlar.kart.iki-kez',{ad:_mdAppAd(cift)})};
    var yok=(m.apps||[]).filter(function(a){ var x=(_hqApps||[]).find(function(y){return y.binary===a;}); return x && x.installed===false; });
    if(yok.length) return {tur:'uyari',metin:t('hq.modlar.kart.kurulu-degil',{ad:yok.map(_mdAppAd).join(', ')})};
    if(m.autostart) return {tur:'bilgi',metin:t('hq.modlar.kart.acilista')};
    return null;
  }

  function _mdBasDurum(){
    var el=document.getElementById('hq-modes-durum'); if(!el) return;
    var yeni=document.getElementById('hq-mode-new-btn'); if(yeni) yeni.disabled=(_mdHata===401);
    /* Oturum kilitliyken modlar görünmüyor → "başlatıcı açık" demek boşta bir iddia olurdu */
    if(_mdHata===401){ el.innerHTML=''; return; }
    var p=[];
    if(_mdBaslatici!==null) p.push('<span class="md-isik '+(_mdBaslatici?'ok':'off')+'" aria-hidden="true"></span>'+
      esc(t(_mdBaslatici?'hq.modlar.baslatici-acik':'hq.modlar.baslatici-kapali-bas')));
    if(_mdHata===null) p.push(esc(tc('hq.modlar.mod-sayisi',_modes.length)));
    var metin=p.join(' · ');
    if(_mdBaslatici===false) metin+=' <button type="button" class="md-bag" data-md-ayar>'+esc(t('hq.modlar.baslatici-ac'))+'</button>';
    else if(_mdBaslatici) metin+=' · '+esc(t('hq.modlar.tetik-notu'));
    el.innerHTML=metin;
  }

  function renderModesList(){
    var list=document.getElementById('hq-modes-list');
    var bos=document.getElementById('hq-mode-empty');
    var form=document.getElementById('hq-mode-form');
    _mdBasDurum();
    if(!list) return;
    var formAcik=form && form.style.display!=='none';
    list.hidden=formAcik;
    if(_mdHata!==null){
      if(bos) bos.style.display='none';
      list.innerHTML='<div class="md-hata"><p>'+esc(t(_mdHata===401?'hq.modlar.oturum-kilitli':'hq.modlar.liste-alinamadi'))+'</p>'
        +'<button type="button" class="dg" data-md-tekrar>'+esc(t('hq.modlar.tekrar-dene'))+'</button></div>';
      return;
    }
    /* Boş durum listenin DIŞINDA, odanın kendi öğreten bloğunda (`#hq-mode-empty`). */
    if(!_modes.length){
      list.innerHTML='';
      if(bos) bos.style.display=formAcik?'none':'';
      return;
    }
    if(bos) bos.style.display='none';
    list.innerHTML=_modes.map(function(m){
      var on=m.enabled!==false, d=_mdDurum(m), s=_mdSonuc[m.id], suruyor=s&&s.tur==='suruyor';
      var kilit=!on || _mdBaslatici===false || suruyor;
      var kw=m.trigger_keywords||[], hedef=_mdHedef(m);
      var cipler=(hedef?'<span class="md-cip'+(hedef.yok?' yok':' hedef')+'">'+esc(hedef.metin)+'</span>':'')
        +kw.slice(0,3).map(function(k){ return '<span class="md-cip">'+esc(k)+'</span>'; }).join('')
        +(kw.length>3?'<span class="md-cip">+'+(kw.length-3)+'</span>':'');
      return '<article class="md-kart'+(on&&_mdBaslatici!==false?'':' soluk')+(m.id===_sel?' secili':'')+'" data-md-kart="'+esc(m.id)+'" tabindex="0" role="button" aria-label="'+esc(t('hq.modlar.kart.duzenle',{ad:m.name||m.id}))+'">'
        +'<h4>'+esc(m.name||m.id)+'</h4>'
        +'<p class="md-ne">'+esc(_mdNeAcar(m))+'</p>'
        +(m.description?'<p class="md-aciklama">'+esc(m.description)+'</p>':'')
        +(cipler?'<div class="md-cipler">'+cipler+'</div>':'')
        +'<div class="md-alt"><span class="md-durum '+(d?d.tur:'')+'"'+(d&&d.ayrinti?' title="'+esc(d.ayrinti)+'"':'')+'>'+(d?esc(d.metin):'')+'</span>'
        +'<button type="button" class="dg '+(kilit?'dg-ikincil':'dg-birincil')+' md-baslat" data-md-baslat="'+esc(m.id)+'"'+(kilit?' disabled':'')+'>'
        +(suruyor?'<i class="md-donen" aria-hidden="true"></i>'+esc(t('hq.modlar.baslatiliyor')):'▶ '+esc(t('hq.modlar.baslat')))+'</button></div>'
        +'</article>';
    }).join('')+'<button type="button" class="md-kart md-yeni" data-md-yeni>+ '+esc(t('hq.modlar.yeni-mod'))+'</button>';
  }

  /* Olay devri: değer taşıyan inline onclick YOK (tek tırnaklı id/ad onclick'i kırıyordu). */
  document.addEventListener('click',function(e){
    var p=document.getElementById('hq-panel-modlar'); if(!p || !p.contains(e.target)) return;
    var b;
    if((b=e.target.closest('[data-md-baslat]'))){ e.stopPropagation(); hqModeRun(b.getAttribute('data-md-baslat')); return; }
    if(e.target.closest('[data-md-yeni]')){ hqModeNew(); return; }
    if(e.target.closest('[data-md-tekrar]')){ hqLoadModes(); return; }
    if(e.target.closest('[data-md-geri]')){ _mdIzgarayaDon(); return; }
    if(e.target.closest('[data-md-ayar]')){ if(typeof hqGoto==='function') hqGoto('cat','gelistirici'); return; }
    if((b=e.target.closest('[data-md-kart]'))){ hqModeSelect(b.getAttribute('data-md-kart')); }
  });
  document.addEventListener('keydown',function(e){
    if(e.key!=='Enter' && e.key!==' ') return;
    var k=e.target.closest && e.target.closest('[data-md-kart]');
    if(k && e.target===k){ e.preventDefault(); hqModeSelect(k.getAttribute('data-md-kart')); }
  });

  function _mdIzgarayaDon(){
    var f=document.getElementById('hq-mode-form'); if(f){ f.style.display='none'; f.innerHTML=''; }
    renderModesList();
  }
  window.hqModeSelect=function(id){ _sel=id; renderModeForm(_modes.find(function(x){return x.id===id;})); renderModesList(); };
  window.hqModeNew=function(){ _sel=null; renderModeForm(null); renderModesList(); };
  function chipHtml(v){ return '<span class="hq-chip" data-v="'+esc(v)+'">'+esc(v)+'<button type="button" class="hq-chip-sil" aria-label="'+esc(t('hq.modlar.cip-sil',{ad:v}))+'" onclick="this.parentNode.remove()">✕</button></span>'; }
  function chipField(label,key,arr){ return '<div class="ff"><label>'+label+'</label><div class="hq-chips" id="chips-'+key+'">'+(arr||[]).map(chipHtml).join('')+'<input class="hq-chip-input" placeholder="'+esc(t('hq.modlar.cip-ekle'))+'" onkeydown="hqChipKey(event,\''+key+'\')"></div></div>'; }
  window.hqChipKey=function(e,key){ if(e.key==='Enter'||e.key===','){ e.preventDefault(); var val=e.target.value.trim().replace(/,$/,''); if(val){ e.target.insertAdjacentHTML('beforebegin', chipHtml(val)); e.target.value=''; } } };
  /* Enter'a basılmamış çip de sayılır: kutuda yazılı kalan kelime kaydederken kayboluyordu.
     Kirlilik kontrolü aynı toplayıcıyı kullandığı için orada da görünür. */
  function chipVals(key){
    var v=Array.prototype.map.call(document.querySelectorAll('#chips-'+key+' .hq-chip'), function(c){return c.getAttribute('data-v');});
    var inp=document.querySelector('#chips-'+key+' .hq-chip-input');
    var bekleyen=inp ? inp.value.trim().replace(/,$/,'') : '';
    if(bekleyen && v.indexOf(bekleyen)<0) v.push(bekleyen);
    return v;
  }
  function _val(id){ var e=document.getElementById(id); return e?e.value.trim():''; }

  // Uygulama seçici — kurulu olanlar yeşil, kurulu olmayanlar soluk
  window.hqToggleAppPicker=function(e){
    e&&e.stopPropagation();
    var d=document.getElementById('hq-app-drop'); if(!d) return;
    var isOpen=d.classList.contains('open');
    document.querySelectorAll('.hq-app-drop.open').forEach(function(x){x.classList.remove('open');});
    if(!isOpen){
      if(_hqApps===null){
        d.innerHTML='<div class="hq-app-bos">'+esc(t('hq.modlar.yukleniyor'))+'</div>';
        d.classList.add('open');
        _mdOku('/api/modes/apps').then(function(data){ _hqApps=(data&&data.apps)||[]; _fillAppDrop(); });
      } else { _fillAppDrop(); d.classList.add('open'); }
    }
  };
  function _fillAppDrop(){
    var d=document.getElementById('hq-app-drop'); if(!d) return;
    d.innerHTML=(_hqApps||[]).map(function(a){
      return '<button type="button" class="hq-app-item" data-bin="'+esc(a.binary)+'" onclick="hqPickApp(this.dataset.bin)">'+
        '<span class="ai-dot '+(a.installed?'ok':'no')+'"></span>'+
        '<span>'+esc(a.label||a.binary)+'</span>'+
        '<code>'+esc(a.binary)+'</code>'+
      '</button>';
    }).join('')||'<div class="hq-app-bos">'+esc(t('hq.modlar.uygulama-bulunamadi'))+'</div>';
    d.classList.add('open');
  }
  window.hqPickApp=function(binary){
    var inp=document.querySelector('#chips-apps .hq-chip-input'); if(inp) inp.insertAdjacentHTML('beforebegin',chipHtml(binary));
    var d=document.getElementById('hq-app-drop'); if(d) d.classList.remove('open');
  };
  document.addEventListener('click',function(e){ if(!e.target.closest('.hq-chips-wrap')) document.querySelectorAll('.hq-app-drop.open').forEach(function(x){x.classList.remove('open');}); });

  // Hedef seçici: numaralı alan / özel alan / hiçbiri (bulunduğum alan)
  window.hqSelWs=function(id){
    _mfWsSel=id; _mfSpSel=null;
    document.querySelectorAll('.hq-ws-btn').forEach(function(b){b.classList.toggle('active-ws',String(b.dataset.wsid)===String(id==null?'':id));});
    document.querySelectorAll('.hq-sp-btn').forEach(function(b){b.classList.remove('active-sp');});
    var hw=document.getElementById('mf-ws'); if(hw) hw.value=id!=null?id:'';
    var hs=document.getElementById('mf-special'); if(hs) hs.value='';
  };
  window.hqSelSp=function(name){
    _mfSpSel=name; _mfWsSel=null;
    document.querySelectorAll('.hq-sp-btn').forEach(function(b){b.classList.toggle('active-sp',b.dataset.spname===name);});
    document.querySelectorAll('.hq-ws-btn').forEach(function(b){b.classList.remove('active-ws');});
    var hw=document.getElementById('mf-ws'); if(hw) hw.value='';
    var hs=document.getElementById('mf-special'); if(hs) hs.value=name||'';
  };

  /* "Dolu" işareti yalnız Hyprland'de gerçek: öbür masaüstlerinde /workspaces sabit 1-4 döner
     ve doluluk bilinmez (`active: null`) → işaret çizilmez, uydurma bilgi gösterilmez. */
  function _buildWsGrid(wsList){
    var hic=_mfWsSel==null&&!_mfSpSel;
    return '<div class="hq-ws-grid" id="mf-ws-grid">'
      +'<button type="button" class="hq-ws-btn hic'+(hic?' active-ws':'')+'" data-wsid="" onclick="hqSelWs(null)">'+esc(t('hq.modlar.hedef-yok'))+'</button>'
      +wsList.map(function(ws){
        var sel=_mfWsSel!=null&&String(_mfWsSel)===String(ws.id);
        return '<button type="button" class="hq-ws-btn'+(ws.active===true?' ws-live':'')+(sel?' active-ws':'')+'" data-wsid="'+esc(String(ws.id))+'" onclick="hqSelWs(+this.dataset.wsid)"'
          +(ws.active===true?' title="'+esc(t('hq.modlar.alan-dolu'))+'"':'')+'>'+esc(String(ws.name))+'</button>';
      }).join('')+'</div>'
      +(wsList.some(function(w){return w.active===true;})?'<p class="md-ipucu">'+esc(t('hq.modlar.alan-dolu-not'))+'</p>':'');
  }
  function _buildSpGrid(spList){
    return '<div class="hq-special-grid" id="mf-sp-grid">'+spList.map(function(sp){
      var sel=_mfSpSel===sp.name;
      return '<button type="button" class="hq-sp-btn'+(sel?' active-sp':'')+'" data-spname="'+esc(sp.name)+'" onclick="hqSelSp(this.dataset.spname)">'+esc(sp.name)+'</button>';   /* '@' tek aralıklı yazıda 'a' gibi okunuyordu */
    }).join('')+'</div>';
  }

  function renderModeForm(m){
    document.getElementById('hq-mode-empty').style.display='none';
    var f=document.getElementById('hq-mode-form'); f.style.display='block';
    var isNew=!m; m=m||{enabled:true};
    f.dataset.id=isNew?'':(m.id||'');
    _mfWsSel=m.workspace!=null?m.workspace:null;
    _mfSpSel=m.special||null;

    var wsList=(_hqWs&&_hqWs.workspaces)||[];
    var spList=(_hqWs&&_hqWs.specials)||[];

    var appsField='<div class="ff"><label>'+esc(t('hq.modlar.uygulamalar'))+'</label>'+
      '<div class="hq-chips-wrap">'+
        '<div class="hq-chips" id="chips-apps">'+
          (m.apps||[]).map(chipHtml).join('')+
          '<input class="hq-chip-input" placeholder="'+esc(t('hq.modlar.cip-ekle'))+'" onkeydown="hqChipKey(event,\'apps\')">'+
          '<button type="button" class="hq-app-picker-btn" onclick="hqToggleAppPicker(event)">'+esc(t('hq.modlar.sec-dugmesi'))+'</button>'+
        '</div>'+
        '<div class="hq-app-drop" id="hq-app-drop"></div>'+
      '</div>'+
    '</div>';

    // ── Kurulu sisteme göre alanları göster/gizle/yeniden adlandır ──
    var F=_hqPlatform.features||{};
    var hedefField=(F.workspaces||F.specials)
      ? '<div class="ff"><label>'+esc(t('hq.modlar.hedef'))+'</label>'
        +(F.workspaces?_buildWsGrid(wsList):'')
        +(F.specials&&spList.length?'<span class="md-alt-etiket">'+esc(t('hq.modlar.ozel-alan'))+'</span>'+_buildSpGrid(spList):'')
        +'<input type="hidden" id="mf-ws" value="'+esc(m.workspace!=null?String(m.workspace):'')+'">'
        +'<input type="hidden" id="mf-special" value="'+esc(m.special||'')+'"></div>'
      : '';
    f.innerHTML=
      '<div class="md-form-bas"><button type="button" class="dg md-geri" data-md-geri><span class="md-ok" aria-hidden="true">←</span>'+esc(t('hq.modlar.modlar'))+'</button>'
        +'<h4>'+esc(isNew?t('hq.modlar.yeni-mod'):(m.name||m.id))+'</h4></div>'+
      '<div class="md-form-izgara">'+
      '<div class="ff"><label for="mf-name">'+esc(t('hq.modlar.mod-adi'))+'</label><input type="text" id="mf-name" value="'+esc(m.name||'')+'" placeholder="'+esc(t('hq.modlar.mod-adi-ornek'))+'"></div>'+
      '<div class="ff"><label for="mf-desc">'+esc(t('hq.modlar.aciklama'))+'</label><input type="text" id="mf-desc" value="'+esc(m.description||'')+'" placeholder="'+esc(t('hq.modlar.aciklama-ornek'))+'"></div>'+
      '</div>'+
      chipField(esc(t('hq.modlar.tetik-kelimeler')),'kw',m.trigger_keywords)+
      appsField+
      hedefField+
      '<div class="md-anahtarlar">'+
      '<div class="ff md-anahtar"><label for="mf-enabled">'+esc(t('hq.modlar.durum'))+'</label><button type="button" role="switch" aria-checked="'+(m.enabled!==false?'true':'false')+'" aria-label="'+esc(t('hq.modlar.durum'))+'" class="hq-toggle'+(m.enabled!==false?' on':'')+'" id="mf-enabled" onclick="this.setAttribute(\'aria-checked\',this.classList.toggle(\'on\'))"></button></div>'+
      '<div class="ff md-anahtar"><label for="mf-autostart">'+esc(t('hq.modlar.oto-baslatma'))+' <span class="md-ipucu">'+esc(t('hq.modlar.oto-baslatma-not'))+'</span></label><button type="button" role="switch" aria-checked="'+(m.autostart?'true':'false')+'" aria-label="'+esc(t('hq.modlar.oto-baslatma'))+'" class="hq-toggle'+(m.autostart?' on':'')+'" id="mf-autostart" onclick="this.setAttribute(\'aria-checked\',this.classList.toggle(\'on\'))"></button></div>'+
      '</div>'+
      '<div class="hq-form-actions" id="md-eylem">'+
        '<button type="button" class="dg dg-birincil" onclick="hqModeSave()">'+esc(t('hq.modlar.kaydet'))+'</button>'+
        (isNew?'':'<button type="button" class="dg dg-ikincil" data-md-baslat="'+esc(m.id)+'"'+(_mdBaslatici===false||m.enabled===false?' disabled':'')+'>▶ '+esc(t('hq.modlar.baslat'))+'</button>')+
        (isNew?'':'<button type="button" class="dg dg-yikici" data-id="'+esc(m.id)+'" onclick="hqModeDelete(this.dataset.id)">'+esc(t('hq.modlar.sil'))+'</button>')+
      '</div>';

    if((F.workspaces||F.specials) && !_hqWs){
      _mdOku('/api/modes/workspaces').then(function(data){
        if(!data) return;
        _hqWs=data;
        var g=document.getElementById('mf-ws-grid'); if(g) g.outerHTML=_buildWsGrid(data.workspaces||[]);
      });
    }
    if(f.scrollIntoView) f.scrollIntoView({block:'nearest'});
  }

  /* Açık mod formunda KAYDEDİLMEMİŞ değişiklik var mı? (Blok 7)

     Yalnız dil tazeleyicisi kullanıyor: kirli formu yeniden çizmek
     kullanıcının yazdığını siler. Karşılaştırma, kaydetme yolunun KULLANDIĞI
     toplayıcılarla yapılıyor (`_val` · `chipVals`) — ayrı bir okuma
     yazılsaydı iki yol zamanla ayrışır ve "kirli değil" diyen bir form
     kaydedilince farklı bir gövde gönderirdi.

     🔑 Alan YOKSA karşılaştırılmıyor: platform yetenekleri bazı alanları hiç
     çizmiyor (Windows'ta özel alan yok).
     Olmayan alanı "boş" sayıp depodaki dolu değerle kıyaslamak, o
     kurulumlarda formu SÜREKLİ kirli gösterir ve tazeleme hiç çalışmazdı.

     🔑 Şüphede KİRLİ dendi (fonksiyonun tamamı böyle kurgulandı): yanlış
     "temiz" hükmü veri kaybettirir, yanlış "kirli" hükmü yalnız etiketi bir
     süre eski dilde bırakır. İki hatanın bedeli eşit değil. */
  function _modFormuKirli(){
    var f=document.getElementById('hq-mode-form');
    if(!f) return true;
    var kayitli=_modes.find(function(x){return x.id===f.dataset.id;})||{enabled:true};
    var dizi=function(v){ return (v||[]).join(''); };
    var metin=function(id,bekleyen){
      return document.getElementById(id) ? (_val(id)!==(bekleyen||'')) : false;
    };
    var cipler=function(key,bekleyen){
      return document.getElementById('chips-'+key) ? (dizi(chipVals(key))!==dizi(bekleyen)) : false;
    };
    var anahtar=function(id,bekleyen){
      var e=document.getElementById(id);
      return e ? (e.classList.contains('on')!==bekleyen) : false;
    };
    return metin('mf-name',kayitli.name)
        || metin('mf-desc',kayitli.description)
        || metin('mf-ws',kayitli.workspace!=null?String(kayitli.workspace):'')
        || metin('mf-special',kayitli.special)
        || cipler('kw',kayitli.trigger_keywords)
        || cipler('apps',kayitli.apps)
        || anahtar('mf-enabled',kayitli.enabled!==false)
        || anahtar('mf-autostart',!!kayitli.autostart);
  }

  window.hqModeSave=async function(){
    var f=document.getElementById('hq-mode-form'); var id=f.dataset.id;
    var name=document.getElementById('mf-name').value.trim();
    if(!name){ toast(t('hq.modlar.ad-zorunlu'),'err'); document.getElementById('mf-name').focus(); return; }
    var ws=_val('mf-ws');
    var body={ name:name, description:_val('mf-desc'),
      trigger_keywords:chipVals('kw'), apps:chipVals('apps'),
      workspace: ws===''?null:(isNaN(+ws)?ws:+ws),
      special: _val('mf-special')||null,
      enabled: document.getElementById('mf-enabled').classList.contains('on'),
      autostart: document.getElementById('mf-autostart').classList.contains('on') };
    try{
      var url=id?('/api/modes/'+encodeURIComponent(id)):'/api/modes'; var method=id?'PUT':'POST';
      var r=await af(url,{method:method,headers:{'Content-Type':'application/json'},body:JSON.stringify(body)});
      var d=null; try{ d=await r.json(); }catch(_){ }
      if(r.ok&&d&&d.ok){
        (d.warnings||[]).forEach(function(w){toast('⚠ '+w,'warn');});
        toast(t('hq.modlar.kaydedildi',{ad:(d.mode&&d.mode.name)||name}),'ok');
        _sel=d.mode&&d.mode.id;
        var fr=document.getElementById('hq-mode-form'); if(fr){ fr.style.display='none'; fr.innerHTML=''; }
        await hqLoadModes();
      }
      else toast(t('hq.modlar.kaydedilemedi',{sebep:(d&&d.detail)||t('hata.bilinmeyen')}),'err');
    }catch(e){ toast(agHatasi(e),'err'); }
  };

  /* Silme satır içinde onay ister (confirm() Electron'da pencereyi kilitler) ve tetik
     kelimelerinin de artık çalışmayacağını söyler — sohbetten başlatma da ölür. */
  window.hqModeDelete=function(id){
    var kutu=document.getElementById('md-eylem'); if(!kutu) return;
    var m=_modes.find(function(x){return x.id===id;})||{};
    var kw=(m.trigger_keywords||[]);
    var eski=kutu.innerHTML;          // vazgeçince yalnız düğmeler döner — formdaki yazı silinmez
    kutu.innerHTML='<div class="md-sil-sor" role="alert"><p><b>'+esc(t('hq.modlar.silme-onayi-ad',{ad:m.name||id}))+'</b>'
      +(kw.length?' '+esc(t('hq.modlar.silme-tetik',{kelimeler:kw.join(', ')})):'')+'</p>'
      +'<div class="md-sil-dugme"><button type="button" class="dg dg-yikici" id="md-sil-evet">'+esc(t('hq.modlar.sil'))+'</button>'
      +'<button type="button" class="dg" id="md-sil-vazgec">'+esc(t('hq.modlar.vazgec'))+'</button></div></div>';
    document.getElementById('md-sil-vazgec').onclick=function(){ kutu.innerHTML=eski; };
    document.getElementById('md-sil-evet').onclick=async function(){
      this.disabled=true;
      try{
        var r=await af('/api/modes/'+encodeURIComponent(id),{method:'DELETE'});
        var d=null; try{ d=await r.json(); }catch(_){ }
        if(r.ok&&d&&d.ok){ toast(t('hq.modlar.silindi'),'ok'); _sel=null; var fr=document.getElementById('hq-mode-form'); if(fr){ fr.style.display='none'; fr.innerHTML=''; } await hqLoadModes(); }
        else { toast(t('hq.modlar.silinemedi')+((d&&d.detail)?': '+d.detail:''),'err'); this.disabled=false; }
      }catch(e){ toast(agHatasi(e),'err'); this.disabled=false; }
    };
  };

  /* BAŞLAT: istek sürerken kilitli (çift tık = tek POST). Sonuç kartta 12 sn durur.
     Sunucunun `result` metni Türkçe üretiliyor (modes.py dil kataloğunda değil) → kartta
     dilin kendi cümlesi, sunucu metni yalnız `title`da (ayrıntı). Hata `detail`i ise
     kataloğdan geliyor (409 "başlatıcı kapalı" / "mod kapalı") → olduğu gibi gösterilir. */
  window.hqModeRun=async function(id){
    var s=_mdSonuc[id]; if(s && s.tur==='suruyor') return;
    _mdSonuc[id]={tur:'suruyor',metin:t('hq.modlar.baslatiliyor'),t:Date.now()};
    renderModesList();
    var fb=document.querySelector('#hq-mode-form [data-md-baslat]'); if(fb) fb.disabled=true;
    var sonuc;
    try{
      var r=await af('/api/modes/run/'+encodeURIComponent(id),{method:'POST'});
      var d=null; try{ d=await r.json(); }catch(_){ }
      /* Kısmen: hangi adımın olmadığı KARTTA yazar (yalnız title'da kalınca telefonda ulaşılamıyordu).
         Ayrıntı sunucunun metni — modes.py dil kataloğunda değil, Türkçe gelebilir (yan bulgu). */
      var eksik = d&&d.uyari ? String(d.result||'').split(' ⚠ ').slice(1).join('; ') : '';
      if(r.ok) sonuc = d&&d.uyari ? {tur:'uyari',metin:eksik?t('hq.modlar.kismen-ayrinti',{ayrinti:eksik}):t('hq.modlar.kismen'),ayrinti:d.result||''}
                                  : {tur:'ok',metin:t('hq.modlar.basladi'),ayrinti:(d&&d.result)||''};
      else sonuc={tur:'err',metin:(d&&d.detail)||t('hq.modlar.calistirilamadi')};
    }catch(e){ sonuc={tur:'err',metin:agHatasi(e)}; }
    sonuc.t=Date.now();
    _mdSonuc[id]=sonuc;
    if(fb){ fb.disabled=false; }
    /* Bildirim hangi moda ait olduğunu söyler — üç sonuç aynı anda gelince karta eşlenemiyordu */
    var mad=((_modes.find(function(x){return x.id===id;})||{}).name)||id;
    toast(mad+': '+sonuc.metin, sonuc.tur==='ok'?'ok':(sonuc.tur==='uyari'?'warn':'err'));
    renderModesList();
    setTimeout(function(){ if(_mdSonuc[id]===sonuc) renderModesList(); }, 12100);
  };

  // ════════ FAZ 17: GEÇMİŞ (HISTORY) ════════

  /* ── GEÇMİŞ ODASI KALDIRILDI (2026-08-29, geliştirici kararı) ──────────────────
     Oda, Hafıza Yöneticisi ile AYNI uçları çağırıyordu (`/api/memory` +
     `/api/memory/search`, aynı dört kategori) — tek farkı silme/dışa aktarma
     yetkisinin olmamasıydı. Menüde ayrı bir yerde durduğu için ("VERİLERİM ›
     Geçmiş") kullanıcı orada SOHBET geçmişi bekleyip anı kayıtları buluyordu.
     Tek işi yapan iki oda, iki oda değil bir kusurdur.
     Odanın tek özgün yeteneği — sayfalama — Hafıza Yöneticisi'ne taşındı
     (`memmgrDahaFazla`); orada altyapı vardı ama düğmesi yoktu, yani 40'tan
     sonraki anılara hiçbir yerden ulaşılamıyordu. */

  /* ── Hafıza Yöneticisi durumu ────────────────────────────────────────────
     🔴 Bu beş tanım 2026-08-31'e kadar YOKTU. Oda hiç çalışmamıştı: `memmgrLoadList`
     `_memmgrLimit`i okuyor, bildirilmediği için ReferenceError atıyor, kendi
     try/catch'i onu yakalayıp panele "Anılar yüklenemedi: ReferenceError:
     _memmgrLimit is not defined" basıyordu. Yani oda AÇILIYOR ama İÇİ yok —
     "oda açılması oda çalışması değildir". Git geçmişinde `_memmgrRenderItem`
     hiç var olmamış (`git log -S` → yalnız ilk commit), yani bu bir regresyon
     değil, baştan eksik kalmış bir parça.
     Sınır 40: sayfalama Geçmiş odasından buraya taşındığında (yukarıdaki not)
     bu odanın gösterdiği kayıt sayısı 40'tı; `memmgrDahaFazla` bunu ekler. */
  // ════════ HAFIZA · DOSYA (2026-09-27 — kişisel ae87ce4 tasarımı, ürüne yeniden yazıldı) ════════
  // Solda Yuki'nin bildikleri (fact/preference/skill/task, önem = 5 tıklanır çentik), sağda
  // konuşmalar gün gün balon + kelime araması. Kişiselden birebir alınmadı: o kod confirm(),
  // 'tr-TR' ve sabit Türkçe metin taşıyor; ürün testleri üçünü de yasaklıyor.
  // Kaynak etiketi ("sen söyledin / Yuki çıkardı") YOK: otomatik çıkarılan bilgi de role=user
  // yazılıyor (llm.py fact çıkarımı) — etiket ayırt edemediği şeyi ayırt ediyormuş gibi yapardı.
  var _memmgrLimit  = 40;      // konuşma sayfası
  var _memmgrOffset = 0;       // yüklenmiş konuşma satırı sayısı (0 = baştan)
  var _hfKonusma = [];         // yüklenen konuşmalar, yeniden eskiye
  var _hfRol = '';             // '' · 'user' · 'assistant' (istemci tarafı süzgeç)
  var _hfGorulen = {};         // id → anı (yeniden yaz için)
  var _hfAcikGrup = {};
  var _hfSayim = {};           // /stats categories
  var _hfKilitli = false;      // hafıza motoru kapalı (ayar): uçlar boş döner, veri silinmez
  var _HF_GRUP_ILK = 6;
  var _HF_GRUPLAR = ['fact','preference','skill','task'];
  /* Yarış kilidi: arka arkaya iki yükleme (Enter + boşaltınca `input`) ikincisinin
     `_memmgrOffset`'i birincinin artırdığı değerle okuyup listeyi KENDİNE eklemesine yol
     açıyordu — ölçüldü 09-27: arama temizlenince 40 yerine 80 balon. Eski cevap atılır. */
  var _hfIstek = 0;

  /* Kategori adı — grup başlığı, konuşma çipi ve arama sonucu rozeti AYNI anahtarı
     okur (markup'ta `data-scope="<kat>"` kabının ilk `data-i18n`'i). Eskiden rozet
     `fact`, süzgeç "Gerçek" diyordu — aynı ekranda aynı şeyin iki adı.
     🔴 Tablo modül düzeyinde ama içinde ANAHTAR tutuyor, `t()` çağrısı değil:
     dosya yüklenirken bir kez değerlenip açılıştaki dilde donardı.
     `skill` 09-27'de eklendi: llm.py onu yazıyordu, panel hiç göstermiyordu. */
  var _MEMMGR_KAT = {
    conversation: 'hq.hafiza.kapsam-konusma',
    fact:         'hq.hafiza.grup-kim',
    preference:   'hq.hafiza.grup-sever',
    skill:        'hq.hafiza.grup-yol',
    task:         'hq.hafiza.grup-gorev'
  };
  function _memmgrKatAdi(kat){
    return _MEMMGR_KAT[kat] ? t(_MEMMGR_KAT[kat]) : String(kat || '');
  }

  /* "Silinemedi: <sebep>" — sebep backend'den ÇEVRİLİ gelir (uçlar `M()`
     kataloğunu kullanır). Boşsa iki nokta hiç basılmaz. Ortak: SES odası ve
     `hqSet` de kullanıyor (Blok 9) — silme. */
  function _ucHatasi(anahtar, d){
    var ayrinti = (d && d.detail) ? String(d.detail) : '';
    return ayrinti
      ? t('ortak.hata-ayrinti', {mesaj: t(anahtar), ayrinti: ayrinti})
      : t(anahtar);
  }

  /* Konuşma balonu (arama sonucunda bilgi satırı da buradan geçer, rozetiyle).
     🔴 `esc()` ZORUNLU: içerik LLM'den ve kullanıcıdan gelir, innerHTML'e gidiyor.
     `data-id` silinen satırı DOM'dan kaldırmak için. */
  /* `etiket` verilirse (arama sonucu — konuşma için '') satır tarih de taşır: sonuçlar
     farklı günlerden gelir, gün başlığı yoktur. "tekrar sor" yalnız konuşmada anlamlı. */
  function _memmgrRenderItem(m, etiket){
    var sen = m.role === 'user', id = Number(m.id);
    var konusma = !m.category || m.category === 'conversation';
    var alt = (etiket != null ? _hfTarih(m.created_at) + ' · ' : '') + _hfSaat(m.created_at);
    return '<div class="hf-balon ' + (sen ? 'sen' : 'yuki') + '" data-id="' + id + '">'
      + (etiket ? '<span class="hf-etiket">' + esc(etiket) + '</span>' : '')
      + '<p class="hf-metin" onclick="this.classList.toggle(\'acik\')">' + esc(m.content || '') + '</p>'
      + '<small><span>' + esc(alt) + '</span>'
      + (sen && konusma ? '<button type="button" onclick="hfYenidenYaz(' + id + ')">' + esc(t('hq.hafiza.yeniden-yaz')) + '</button>' : '')
      + _hfSilDugmesi(id)
      + '</small></div>';
  }
  function _hfTarih(iso){
    var d = new Date(iso); if(isNaN(d)) return '';
    var o = {day:'numeric', month:'long'};
    if(d.getFullYear() !== new Date().getFullYear()) o.year = 'numeric';
    return d.toLocaleDateString(yerelKod(), o);
  }
  function _hfSaat(iso){
    var d = new Date(iso); return isNaN(d) ? '' : d.toLocaleTimeString(yerelKod(), {hour:'2-digit', minute:'2-digit'});
  }
  /* Gün anahtarı YEREL takvimden — `created_at.slice(0,10)` UTC günü verir, gece
     yarısına yakın satırlar bir önceki güne düşerdi. */
  function _hfGunAnahtari(iso){
    var d = new Date(iso); return isNaN(d) ? '' : d.getFullYear() + '-' + (d.getMonth() + 1) + '-' + d.getDate();
  }
  function _hfSilDugmesi(id){
    return '<button type="button" class="hf-sil" onclick="memmgrDelete(' + id + ', this)">' + esc(t('hq.hafiza.sil')) + '</button>';
  }
  function _hfBos(bas, metin){
    return '<div class="bos"><p class="bos-bas">' + esc(bas) + '</p>'
      + (metin ? '<p class="bos-metin">' + esc(metin) + '</p>' : '') + '</div>';
  }
  /* Önem = 5 çentik; çentiğe tıklamak önemi o kademeye çeker (0.2 … 1.0).
     Eskiden `prompt()` ile 0-1 arası sayı isteniyordu — native diyalog Electron'u kilitler. */
  function _hfCentik(m){
    var o = typeof m.importance === 'number' ? m.importance : 0, id = Number(m.id);
    var h = '<span class="hf-guc" role="group" aria-label="' + esc(t('hq.hafiza.onem-duzenle', {n: o.toFixed(2)})) + '">';
    [0.2, 0.4, 0.6, 0.8, 1].forEach(function(e, i){
      h += '<button type="button" class="' + (o >= e - 0.05 ? 'd' : '') + '" onclick="hfOnem(' + id + ',' + e + ')"'
        + ' aria-label="' + esc(t('hq.hafiza.onem-kademe', {n: i + 1})) + '"></button>';
    });
    return h + '</span>';
  }
  function _hfBilgiSatir(m){
    var id = Number(m.id);
    return '<div class="hf-bilgi" data-id="' + id + '">'
      + '<p class="hf-metin" onclick="this.classList.toggle(\'acik\')">' + esc(m.content || '') + '</p>'
      + _hfCentik(m)
      + '<small><span>' + esc(_hfTarih(m.created_at)) + '</span>' + _hfSilDugmesi(id) + '</small></div>';
  }

  window.memmgrInit=async function(){
    await memmgrLoadStats();
    await Promise.all([_hfBilgiYukle(), memmgrLoadList()]);
  };

  window.memmgrLoadStats=async function(){
    try{
      var r=await af('/api/memory/stats'); var d=await r.json();
      /* 🔴 `categories`, `scopes` DEĞİL (2026-09-20): `scopes` hibrit skorun ağırlığı,
         girdisi {count, avg_importance} NESNESİ — ekrana `[object Object]` basıyordu. */
      var kat=d.categories||{};
      _hfSayim=kat;
      _hfKilitli=(d.enabled===false);
      var kapali=_hfKilitli;   // motor kapalı (kademe kilidi yok)
      var say=function(k){ return (typeof kat[k]==='number')?kat[k]:0; };
      var bil=say('fact')+say('preference')+say('skill')+say('task');
      var pnl=document.getElementById('hq-panel-memmgr'); if(pnl) pnl.classList.toggle('hf-kilitli', _hfKilitli);
      var b=document.getElementById('hf-baslik');
      if(b){
        if(kapali) b.textContent=t('hq.hafiza.kapali-baslik');
        else if(bil) b.innerHTML=esc(tc('hq.hafiza.taniyor', bil)).replace(String(bil), '<em>'+bil+'</em>');
        else b.textContent=t('hq.hafiza.henuz-tanimiyor');
      }
      var a=document.getElementById('hf-alt');
      if(a){ a.textContent=kapali?t('hq.hafiza.kapali'):(_hfKilitli?'':t('hq.hafiza.ozet-alt', {k: say('conversation'), n: (d.total||0)})); a.classList.toggle('uyari', kapali); }
      ['conversation','fact','preference','skill','task'].forEach(function(k){
        var e2=document.getElementById('msc-'+k); if(e2) e2.textContent=say(k);
      });
    }catch(e){}
  };

  async function _hfBilgiYukle(){
    var bos=document.getElementById('hf-bilgi-bos');
    var grup=function(k){ return document.querySelector('#memmgr-scope-list .hf-grup[data-scope="'+k+'"]'); };
    if(_hfKilitli){
      _HF_GRUPLAR.forEach(function(k){ var g=grup(k); if(g) g.hidden=true; });
      if(bos) bos.hidden=true;
      return;
    }
    // Yalnız sayacı dolu gruplar istenir — boş gruba istek atılmaz
    var dolu=_HF_GRUPLAR.filter(function(k){ return (_hfSayim[k]||0)>0; });
    try{
      var sonuc=await Promise.all(dolu.map(function(k){
        return af('/api/memory?'+new URLSearchParams({limit:200, category:k})).then(function(r){ return r.ok?r.json():[]; });
      }));
      var gosterilen=0;
      _HF_GRUPLAR.forEach(function(k){
        var g=grup(k), kap=document.getElementById('hf-grup-'+k);
        var i=dolu.indexOf(k), l=(i<0?[]:(sonuc[i]||[])).slice();
        l.forEach(function(m){ _hfGorulen[m.id]=m; });
        l.sort(function(a,b){ return ((b.importance||0)-(a.importance||0)) || (b.id-a.id); });
        if(g) g.hidden=!l.length;
        if(!l.length || !kap) return;
        gosterilen+=l.length;
        var acik=_hfAcikGrup[k], gor=acik?l:l.slice(0,_HF_GRUP_ILK);
        kap.innerHTML=gor.map(_hfBilgiSatir).join('')
          + (l.length>_HF_GRUP_ILK
             ? '<button type="button" class="hf-dahasi" onclick="hfGrupAc(\''+k+'\')">'
               + esc(acik?t('hq.hafiza.daha-az'):t('hq.hafiza.n-tane-daha',{n:l.length-_HF_GRUP_ILK}))+'</button>'
             : '');
      });
      if(bos) bos.hidden=gosterilen>0;
      _hfTasmaIsaretle();
    }catch(e){
      if(bos){ bos.hidden=false; bos.textContent=t('hq.hafiza.yuklenemedi')+' '+agHatasi(e); }
    }
  }
  /* Masada sol sütun yapışkan ve kendi içinde kayar; taşıyorsa alt kenar solar (CSS) — dibe
     inince solma kalkar. Ölçü DOM'dan: CSS kabın taşıp taşmadığını bilemez. */
  function _hfTasmaIsaretle(){
    var d=document.querySelector('#hq-panel-memmgr .hf-dosya'); if(!d) return;
    var isaretle=function(){
      d.classList.toggle('tasiyor', d.scrollHeight>d.clientHeight+4);
      d.classList.toggle('dipte', d.scrollTop+d.clientHeight>=d.scrollHeight-4);
    };
    if(!d._hfDinleyici){ d.addEventListener('scroll', isaretle, {passive:true}); d._hfDinleyici=true; }
    isaretle();
  }
  window.hfGrupAc=function(k){ _hfAcikGrup[k]=!_hfAcikGrup[k]; _hfBilgiYukle(); };

  /* Günler yeniden eskiye, gün içi eskiden yeniye — sohbet gibi okunur.
     🪤 Aynı işlemde yazılan kullanıcı+Yuki satırı eşit created_at alır → gün içi
     sırayı id belirler (pgvector'de ORDER BY'a da `id DESC` eklendi). */
  function _hfAkisCiz(){
    var list=document.getElementById('memmgr-list'); if(!list) return;
    var l=_hfRol?_hfKonusma.filter(function(m){ return m.role===_hfRol; }):_hfKonusma;
    if(!l.length){
      list.innerHTML=_hfKonusma.length
        ? _hfBos(t('hq.hafiza.suzgecte-yok'))
        : _hfBos(t('hq.hafiza.hic-ani-yok'), t('hq.hafiza.hic-ani-yok-metin'));
      return;
    }
    var gunler={}, sira=[];
    l.forEach(function(m){ var g=_hfGunAnahtari(m.created_at); if(!gunler[g]){ gunler[g]=[]; sira.push(g); } gunler[g].push(m); });
    list.innerHTML=sira.map(function(g){
      var ms=gunler[g].slice().sort(function(a,b){ return (new Date(a.created_at)-new Date(b.created_at)) || (a.id-b.id); });
      return '<div class="hf-gun">'+esc(_hfTarih(ms[0].created_at))+'</div>'+ms.map(function(m){ return _memmgrRenderItem(m); }).join('');
    }).join('');
  }

  window.memmgrLoadList=async function(){
    var list=document.getElementById('memmgr-list'), daha=document.getElementById('memmgr-daha'), st=document.getElementById('memmgr-stats');
    var q=((document.getElementById('memmgr-search')||{}).value||'').trim();
    var pnl=document.getElementById('hq-panel-memmgr'); if(pnl) pnl.classList.toggle('aramada', !!q);
    var benim=++_hfIstek, bas=_memmgrOffset;
    if(_hfKilitli){ if(list) list.innerHTML=''; if(daha) daha.hidden=true; if(st) st.textContent=''; return; }
    if(list && !bas) list.innerHTML='<div class="iskelet iskelet-satir"></div>'
      +'<div class="iskelet iskelet-satir"></div><div class="iskelet iskelet-satir"></div>';
    try{
      if(q){
        /* Önce kelime araması (birebir geçenler); yoksa anlamca yakınlar. Eşik yüksek:
           düşük eşikte "sa", "selam" gibi kısa satırlar her sorguya eşleşiyordu
           (kişiselde ölçüldü 09-26: "programlama dili" → 50 sonuç, çoğu selam). */
        var r=await af('/api/memory?'+new URLSearchParams({q:q, limit:100}));
        if(_oturumReddi(r)){ if(list) list.innerHTML=_hfBos(t('hq.oturum-kilitli')); return; }
        var s=r.ok?((await r.json())||[]):[], anlamca=false;
        if(!s.length){
          var r2=await af('/api/memory/search?'+new URLSearchParams({q:q, limit:20, min_similarity:0.55}));
          s=r2.ok?((await r2.json())||[]):[]; anlamca=true;
        }
        if(benim!==_hfIstek) return;
        if(daha) daha.hidden=true;
        if(st) st.textContent='';
        s.forEach(function(m){ _hfGorulen[m.id]=m; });
        if(list) list.innerHTML=s.length
          ? '<div class="hf-gun">'+esc(anlamca?tc('hq.hafiza.yakin-sonuc', s.length, {q:q}):tc('hq.hafiza.sonuc', s.length, {q:q}))+'</div>'
            + s.map(function(m){ return _memmgrRenderItem(m, m.category==='conversation'?'':'◆ '+_memmgrKatAdi(m.category)); }).join('')
          : _hfBos(t('hq.hafiza.arama-bos-bas',{q:q}), t('hq.hafiza.arama-bos-metin'));
        return;
      }
      var r3=await af('/api/memory?'+new URLSearchParams({limit:_memmgrLimit, offset:bas, category:'conversation'}));
      if(_oturumReddi(r3)){ if(list) list.innerHTML=_hfBos(t('hq.oturum-kilitli')); return; }
      if(!r3.ok) throw new Error('HTTP '+r3.status);
      var y=(await r3.json())||[];
      if(benim!==_hfIstek) return;
      _hfKonusma=bas?_hfKonusma.concat(y):y;
      _memmgrOffset=bas+y.length;
      y.forEach(function(m){ _hfGorulen[m.id]=m; });
      _hfAkisCiz();
      if(daha) daha.hidden=y.length<_memmgrLimit;
      if(st) st.textContent=_hfKonusma.length?tc('hq.hafiza.kayit-gosteriliyor', _hfKonusma.length):'';
    }catch(e){
      if(list) list.innerHTML='<p class="alan-hata">'+esc(t('hq.hafiza.yuklenemedi'))+' '+esc(agHatasi(e))+'</p>';
    }
  };

  window.memmgrDahaFazla=function(){ memmgrLoadList(); };
  window.memmgrSearch=function(){ _memmgrOffset=0; memmgrLoadList(); };

  window.hfRolSec=function(r){
    _hfRol=r;
    document.querySelectorAll('#hq-panel-memmgr .hf-cip[data-rol]').forEach(function(b){
      var on=(b.dataset.rol===r); b.classList.toggle('on', on); b.setAttribute('aria-pressed', on?'true':'false');
    });
    var q=document.getElementById('memmgr-search');
    if(q && q.value){ q.value=''; memmgrSearch(); } else _hfAkisCiz();
    /* Telefonda akış bildiklerin ALTINDA — çipe basan sonucu görsün (goz 09-27) */
    var list=document.getElementById('memmgr-list');
    if(list && window.matchMedia && window.matchMedia('(max-width: 900px)').matches) list.scrollIntoView({block:'start', behavior:'smooth'});
  };

  /* Kendi eski mesajını sohbet kutusuna koy ve sohbete geç (kişiselde eskiden
     Yuki'nin mesajını koyuyordu + geçersiz `switchTab('classic')`). */
  window.hfYenidenYaz=function(id){
    var m=_hfGorulen[id]; if(!m) return;
    if(typeof switchTab==='function') switchTab('chat');
    var inp=document.getElementById('msg-input');
    if(inp){ inp.value=m.content||''; inp.focus(); inp.dispatchEvent(new Event('input')); }
  };

  window.hfOnem=async function(id, deger){
    try{
      var r=await af('/api/memory/'+id,{method:'PUT',headers:{'Content-Type':'application/json'},body:JSON.stringify({importance:deger})});
      if(_oturumReddi(r)){ toast(t('hq.oturum-kilitli'),'err'); return; }
      var d=await r.json();
      if(r.ok&&d.status==='ok'){
        toast(t('hq.hafiza.onem-guncellendi',{n: Math.round(deger*5)+'/5'}),'ok');
        _hfBilgiYukle();
      } else toast(_ucHatasi('hq.hafiza.guncellenemedi', d),'err');
    }catch(e){ toast(agHatasi(e),'err'); }
  };

  /* İki adımlı onay — `confirm()` YOK (native diyalog Electron penceresini kilitler,
     otomatik ölçümü asar). İlk tık düğmeyi kurar (4 sn), ikinci tık siler. */
  var _hfSilKurulu=null, _hfSilZaman=null;
  window.memmgrDelete=async function(id, btn){
    if(btn && _hfSilKurulu!==btn){
      if(_hfSilKurulu && _hfSilKurulu.isConnected){ _hfSilKurulu.classList.remove('kurulu'); _hfSilKurulu.textContent=t('hq.hafiza.sil'); }
      _hfSilKurulu=btn; btn.classList.add('kurulu'); btn.textContent=t('hq.hafiza.sil-emin');
      clearTimeout(_hfSilZaman);
      _hfSilZaman=setTimeout(function(){
        if(btn.isConnected){ btn.classList.remove('kurulu'); btn.textContent=t('hq.hafiza.sil'); }
        _hfSilKurulu=null;
      },4000);
      return;
    }
    clearTimeout(_hfSilZaman); _hfSilKurulu=null;
    try{
      var r=await af('/api/memory/'+id,{method:'DELETE'});
      if(_oturumReddi(r)){ toast(t('hq.oturum-kilitli'),'err'); return; }
      var d=await r.json();
      if(r.ok&&d.status==='ok'){
        document.querySelectorAll('#hq-panel-memmgr .hf-bilgi[data-id="'+id+'"], #hq-panel-memmgr .hf-balon[data-id="'+id+'"]')
          .forEach(function(el){ el.remove(); });
        _hfKonusma=_hfKonusma.filter(function(m){ return m.id!==id; });
        toast(t('hq.hafiza.silindi'),'ok');
        memmgrLoadStats();
      } else toast(_ucHatasi('hq.hafiza.silinemedi', d),'err');
    }catch(e){ toast(agHatasi(e),'err'); }
  };

  var _hfTemizlikOnay=null;
  window.memmgrCleanup=async function(){
    var durum=document.getElementById('memmgr-temizlik-durum');
    if(!_hfTemizlikOnay){
      if(durum) durum.textContent=t('hq.hafiza.temizlik-onayi');
      _hfTemizlikOnay=setTimeout(function(){ _hfTemizlikOnay=null; if(durum) durum.textContent=''; },5000);
      return;
    }
    clearTimeout(_hfTemizlikOnay); _hfTemizlikOnay=null;
    try{
      var r=await af('/api/memory/cleanup',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({})});
      if(_oturumReddi(r)){ if(durum) durum.textContent=t('hq.oturum-kilitli'); return; }
      var d=await r.json();
      if(r.ok&&d.status==='ok'){
        if(durum) durum.textContent=tc('hq.hafiza.temizlendi', d.deleted);
        _memmgrOffset=0; memmgrInit();
      } else if(durum) durum.textContent=t('hq.hafiza.temizlenemedi');
    }catch(e){ if(durum) durum.textContent=agHatasi(e); }
  };

  // ════════════════════════════════════════════
  //  FAZ 19 — TTS PANEL (Ses Sentezi Yönetimi)
  // ════════════════════════════════════════════

  var _ttsStatus = null;

  // Karakter başına Edge TTS ses profilleri (localStorage'da saklanır)
  var _TTS_VOICES = [
    { char:'yuki', label:'YUKI', voices:['tr-TR-EmelNeural','tr-TR-AhmetNeural','en-US-JennyNeural'] },
  ];
  var _EVOL_VOICE_KEY = 'yukiCharVoices'; // {yuki:'tr-TR-EmelNeural', ...}

  function _ttsGetVoices(){ try{ return JSON.parse(localStorage.getItem(_EVOL_VOICE_KEY)||'{}'); }catch(e){ return {}; } }
  function _ttsSetVoice(charKey,voice){
    var v=_ttsGetVoices();
    if(voice) v[charKey]=voice; else delete v[charKey];   // boş = dil varsayılanına dön
    localStorage.setItem(_EVOL_VOICE_KEY,JSON.stringify(v));
    return v;
  }

  // 🔴 2026-09-18 (FAZ 0, A6): seçim eskiden YALNIZ localStorage'a yazılıyordu ve
  // backend'de okuyan hiçbir yer yoktu — kullanıcı ses seçiyor, "✓ kaydedildi"
  // toast'ı görüyor, hiçbir şey değişmiyordu. Artık ayar ucuna da gönderilir.
  async function _ttsSunucuyaYaz(harita){
    var r = await af('/api/settings/PERSONA_VOICES', {
      method:'POST',
      headers:{'Content-Type':'application/json'},
      body: JSON.stringify({ value: JSON.stringify(harita) }),
    });
    if(!r.ok){
      var d = await r.json().catch(function(){ return {}; });
      throw new Error(d.detail || ('HTTP '+r.status));
    }
  }

  // Sunucudaki harita tek gerçek kaynaktır; localStorage yalnız hızlı önizleme.
  var _ttsDilVarsayilani = '';
  async function _ttsSunucudanOku(){
    try{
      var r = await af('/api/settings/persona-voices');
      if(!r.ok) return null;
      var d = await r.json();
      _ttsDilVarsayilani = d.dil_varsayilani || '';
      return d.secimler || {};
    }catch(e){ return null; }
  }

  window.ttsInit = async function(){
    await ttsLoadStatus();
    var sunucu = await _ttsSunucudanOku();
    if(sunucu) localStorage.setItem(_EVOL_VOICE_KEY, JSON.stringify(sunucu));
    ttsRenderVoiceGrid();
  };

  window.ttsLoadStatus = async function(){
    try{
      var r = await af('/api/tts/status');
      if(!r.ok) throw new Error(r.status);
      _ttsStatus = await r.json();
      _ttsRenderChain(_ttsStatus.chain || []);
    }catch(e){
      var d = document.getElementById('tts-chain-display');
      if(d) d.innerHTML='<span style="color:var(--kirmizi-ink);font-family:var(--font-hud);font-size:10px;">'+esc(t('hq.ses.zincir-yuklenemedi'))+' '+esc(agHatasi(e))+'</span>';
    }
  };

  /* 🔑 Not satırı (`Aktif: …`) BURAYA taşındı (Blok 9). Eskiden
     `ttsLoadStatus`'un içindeydi, yani ancak AĞ İSTEĞİYLE tazeleniyordu:
     dil değişiminde zincir yeniden çizilse bile notu çevirmenin tek yolu
     `/api/tts/status`'u yeniden yoklamaktı. Çizim ile veri çekme aynı
     fonksiyonda durdukça "yeniden çiz" hep "yeniden indir" demek olur. */
  function _ttsRenderChain(chain){
    var el = document.getElementById('tts-chain-display');
    var not = document.getElementById('tts-chain-note');
    if(not){
      var aktif = (chain||[]).filter(function(n){ return n.active; })
                             .map(function(n){ return n.label; });
      not.textContent = aktif.length
        ? t('hq.ses.aktif-zincir', {liste: aktif.join(' → ')})
        : t('hq.ses.zincir-yok');
    }
    if(!el) return;
    var html = '';
    chain.forEach(function(node,i){
      if(i>0) html += '<span class="tts-arrow">→</span>';
      html += '<div class="tts-node '+(node.active?'active':'inactive')+'">';
      html += '<span class="tts-node-dot"></span>';
      html += esc(node.label);
      html += '</div>';
    });
    el.innerHTML = html || '<span style="font-family:var(--font-hud);font-size:10px;color:var(--muted);">'+esc(t('hq.ses.zincir-bos'))+'</span>';
  }

  /* SES odası dil değişiminde: elde olanı yeniden çiz, AĞA GİTME.

     Oda `hqSelectCat` üzerinden açıldığı için `_dilTazeleyici.ayarlar`
     zaten koşuyor — ama o yalnız kabuğu ve ayar satırlarını tazeliyordu;
     TTS panelinin JS'ten doğan üç yüzeyi (zincir · not · ses ızgarası)
     eski dilde donuyordu, çünkü `ttsInit` bir kez koşup `_ttsInited`i
     kilitliyor. Kanvas turunda ölçüldü.

     🔑 `ttsInit()` ÇAĞIRMIYOR: iki uç birden yoklanırdı (`/tts/status` +
     `/settings/persona-voices`) ve ikisinin cevabı dil değişince değişmez
     (zincir düğümleri marka adı, ses kimlikleri Edge TTS değeri). Blok
     7'nin `renderModesList` kararının aynısı. */
  function _ttsCiz(){
    if(_ttsStatus) _ttsRenderChain(_ttsStatus.chain || []);
    ttsRenderVoiceGrid();
  }

  /* Edge TTS kimliği → okunur ad: "tr-TR-EmelNeural" → "Emel · tr-TR".
     Kart ~190px; ham kimlik "Dil varsayılanı (tr-TR-EmelNeural)" ile 250px'e
     çıkıp kesiliyordu. Yalnız GÖRÜNEN metin kısalır — değer kimlik kalır. */
  function _sesKisa(v, yalnizAd){
    var m = /^([a-z]{2,3}-[A-Z]{2})-(.+?)(?:Multilingual)?Neural$/.exec(String(v||''));
    if(!m) return String(v||'');
    return yalnizAd ? m[2] : m[2]+' · '+m[1];
  }

  function ttsRenderVoiceGrid(){
    var grid = document.getElementById('tts-voice-grid');
    if(!grid) return;
    var saved = _ttsGetVoices();
    var html = '';
    _TTS_VOICES.forEach(function(c){
      // Boş değer = "dil varsayılanı". A7'den beri ses kimliği dilden geliyor;
      // geri dönüş yolu olmazsa kullanıcı bir kez seçince dil sesi bir daha gelmez.
      var current = saved[c.char] || '';
      html += '<div class="tts-voice-card" data-char="'+c.char+'">';
      html += '<div class="tts-voice-card-char">'+esc(c.label)+'</div>';
      html += '<select class="tts-input" style="margin:4px 0;padding:4px 8px;" onchange="ttsVoiceSelect(\''+c.char+'\',this.value)">';
      html += '<option value=""'+(current?'':' selected')+'>'
           +  esc(_ttsDilVarsayilani
                  ? t('hq.ses.dil-varsayilani-ses',{ses:_sesKisa(_ttsDilVarsayilani, true)})
                  : t('hq.ses.dil-varsayilani'))+'</option>';
      c.voices.forEach(function(v){
        html += '<option value="'+esc(v)+'"'+(v===current?' selected':'')+' title="'+esc(v)+'">' +esc(_sesKisa(v))+'</option>';
      });
      html += '</select>';
      html += '<button class="tts-btn" style="font-size:9px;padding:4px 10px;" onclick="ttsTestChar(\''+c.char+'\')">▶ '+esc(t('hq.ses.test-et'))+'</button>';
      html += '</div>';
    });
    grid.innerHTML = html;
  }

  window.ttsVoiceSelect = async function(charKey, voice){
    var onceki = _ttsGetVoices();
    var harita = _ttsSetVoice(charKey, voice);
    try{
      await _ttsSunucuyaYaz(harita);
      // ⚠️ Onay mesajı YAZMADAN ÖNCE sunucu cevabı beklenir. Eskiden toast
      // isteksiz basılıyordu; kullanıcı "kaydedildi" görüp hiçbir şey almıyordu.
      toast(t('hq.ses.ses-atandi',{karakter:charKey.toUpperCase(), ses:(voice ? _sesKisa(voice) : t('hq.ses.dil-varsayilani'))}), 'ok');
    }catch(e){
      localStorage.setItem(_EVOL_VOICE_KEY, JSON.stringify(onceki));   // geri al
      ttsRenderVoiceGrid();
      toast(_ucHatasi('hq.ses.ses-kaydedilemedi', {detail:(e && e.message ? e.message : e)}), 'err');
    }
  };

  window.ttsTest = async function(){
    var text = (document.getElementById('tts-test-text')||{}).value || t('hq.ses.test-metni-kisa');
    if(!text.trim()) return;
    try{
      toast(t('hq.ses.ses-uretiliyor'),'ok');
      var r = await af('/api/tts/test',{
        method:'POST', headers:{'Content-Type':'application/json'},
        body: JSON.stringify({text: text.slice(0,300)})
      });
      if(!r.ok){ toast(_ucHatasi('hq.ses.tts-hatasi', await r.json().catch(function(){ return {}; })),'err'); return; }
      var d = await r.json();
      var player = document.getElementById('tts-audio-player');
      if(player && d.audio_base64){
        player.src = 'data:audio/mpeg;base64,' + d.audio_base64;
        player.style.display = 'block';
        player.play().catch(function(){});
      }
    }catch(e){ toast(agHatasi(e),'err'); }
  };

  window.ttsTestChar = async function(charKey){
    var labels = {yuki:'hq.ses.demo-yuki'};   // 11-14: yalnız Yuki (karakter eklenince buraya)
    var text = t(labels[charKey] || 'hq.ses.demo-genel');
    document.getElementById('tts-test-text').value = text;
    await ttsTest();
  };

  window.ttsUploadRef = async function(){
    var inp = document.getElementById('tts-ref-file');
    if(!inp || !inp.files[0]) return;
    var file = inp.files[0];
    document.getElementById('tts-ref-filename').textContent = file.name;
    var fd = new FormData();
    fd.append('file', file);
    try{
      toast(t('hq.ses.yukleniyor-dosya'),'ok');
      /* 🔴 Eskiden çıplak `fetch` + `_token` yazıyordu; `_token` bu dosyada da
         başka bir yerde de HİÇ bildirilmemişti. `(_token||'elakage')` yedeği
         işe yaramaz — bildirilmemiş bir ada erişmek `||`'a varmadan
         ReferenceError atar. Hata try/catch'e düşüp "Yüklenemedi" toast'ına
         dönüşüyordu, yani referans ses yükleme HER SEFERİNDE başarısızdı ve
         sebebi kullanıcıya hiç görünmüyordu. Gerçek token `core.js::_authToken`;
         bu dosyanın kendi `af()` yardımcısı zaten `authFetch` üzerinden onu
         ekliyor. `af()` Content-Type'a dokunmaz → FormData sınırı korunur. */
      var r = await af('/api/tts/reference', { method:'POST', body: fd });
      if(!r.ok){ toast(_ucHatasi('hq.ses.yukleme-hatasi', await r.json().catch(function(){ return {}; })),'err'); return; }
      var d = await r.json();
      var st = document.getElementById('tts-ref-status');
      if(st){ st.textContent = t('hq.ses.ref-kaydedildi',{yol:d.path, kb:d.size_kb}); st.style.display='block'; }
      toast(t('hq.ses.ref-yuklendi'),'ok');
    }catch(e){ toast(agHatasi(e),'err'); }
  };

  // ════════════════════════════════════════════
  //  FAZ 21 — CHARACTER EVOLUTION (Karakter Evrim Sistemi)
  // ════════════════════════════════════════════

  var _EVOL_KEY = 'yukiEvolution';
  var _EVOL_CHARS = ['yuki'];   // 11-14: yalnız Yuki — ileride karakter eklenince buraya
  // XP eşikleri → level 1-9 (index = level-1)
  var _EVOL_XP = [0,100,250,500,1000,2500,5000,10000,20000];
  /* 🔴 BEŞİNCİ kez aynı sınıf: modül düzeyi sabit. `var X = [...]` dosya
     yüklenirken BİR KEZ değerlenir — içine `t()` yazılsaydı metin o anki
     dilde donar ve dil değişince HATA VERMEDEN Türkçe kalırdı. Öncekiler:
     ODA_AMAC · PERF_KADEMELERI · gfx.TIERS · _MEMMGR_KAT. Kural aynı:
     sabit ANAHTAR tutar, çizim anında `t()` çözer. */
  var _EVOL_LABELS = ['evol.sv.baslangic','evol.sv.tanisma','evol.sv.sohbet',
    'evol.sv.guven','evol.sv.bag','evol.sv.yakin','evol.sv.derin',
    'evol.sv.akil-yurutme','evol.sv.bilinc'];
  var _EVOL_TRAITS = [
    [],
    ['evol.yetenek.selamlama-bellegi'],
    ['evol.yetenek.duygu-tespiti'],
    ['evol.yetenek.tercih-ogrenimi'],
    ['evol.yetenek.baglam-tahmini'],
    ['evol.yetenek.proaktif-oneri'],
    ['evol.yetenek.uzun-sureli-hafiza','evol.yetenek.kisisel-referans'],
    ['evol.yetenek.cok-adim-planlama','evol.yetenek.yaratici-sentez'],
    ['evol.yetenek.tam-entegrasyon','evol.yetenek.ozerk-inisiyatif'],
  ];

  /* Seviye etiketi — dizi kısa kalırsa satır KAYBOLMAZ, numarayla görünür.
     (`_catAd`/`_ayarAd`'ın kademeli tek sahiplik deseninin üçüncü hâli.) */
  function _evolEtiket(level){
    var a = _EVOL_LABELS[level-1];
    return a ? t(a) : t('evol.seviye-n', {n: level});
  }
  function _evolYetenekler(level){
    return (_EVOL_TRAITS[level-1] || []).map(function(a){ return t(a); });
  }

  function _evolGet(){
    try{
      var raw = JSON.parse(localStorage.getItem(_EVOL_KEY)||'{}');
      var out = {};
      _EVOL_CHARS.forEach(function(k){
        out[k] = raw[k] || {xp:0,messages:0,last_seen:null};
      });
      return out;
    }catch(e){ return {}; }
  }

  function _evolSave(data){ localStorage.setItem(_EVOL_KEY, JSON.stringify(data)); }

  function _evolLevel(xp){
    for(var i=_EVOL_XP.length-1;i>=0;i--){ if(xp>=_EVOL_XP[i]) return i+1; }
    return 1;
  }

  function _evolXpToNext(xp){
    var lv = _evolLevel(xp);
    if(lv>=9) return { pct:100, remaining:0, next:_EVOL_XP[8] };
    var cur = _EVOL_XP[lv-1], nxt = _EVOL_XP[lv];
    var pct = Math.round((xp-cur)/(nxt-cur)*100);
    return { pct: Math.min(pct,100), remaining: nxt-xp, next: nxt };
  }

  window.evolAddXP = function(charKey, amount){
    amount = amount || 15;
    if(!_EVOL_CHARS.includes(charKey)) return;
    var data = _evolGet();
    var before = _evolLevel(data[charKey].xp);
    data[charKey].xp += amount;
    data[charKey].messages = (data[charKey].messages||0) + 1;
    data[charKey].last_seen = new Date().toISOString();
    _evolSave(data);
    var after = _evolLevel(data[charKey].xp);
    if(after > before){
      _evolShowLevelUp(charKey, after);
    }
    _evolUpdateBadges();
  };

  /* 🔑 Bu toast Evolution'ın TEK CANLI yüzeyi: `evolAddXP` her kullanıcı
     mesajında çağrılıyor (`core.js::_ck`), yani seviye atlandığı an ekranda
     belirir. (Panel — `evolRenderPanel` — ölü; bkz. oradaki not.)
     Cümle birleştirilmiyor, her satır kendi TAM cümlesi: İngilizce'de
     "{ad} Level {n} — {etiket}" sırası TR'ninkiyle aynı olmak zorunda değil. */
  function _evolShowLevelUp(charKey, level){
    var traits = _evolYetenekler(level);
    var msg = t('evol.seviye-atlandi', {karakter: charKey.toUpperCase(),
                                        n: level, etiket: _evolEtiket(level)});
    if(traits.length) msg += '\n'+tc('evol.yeni-yetenek', traits.length,
                                     {liste: traits.join(', ')});
    toast('⚡ '+msg, 'ok');
  }

  window._evolUpdateBadges = function(){
    var data = _evolGet();
    // Game mode karakter kartları
    document.querySelectorAll('[data-char]').forEach(function(el){
      var k = el.dataset.char;
      if(!k) return;
      var xp = data[k] ? data[k].xp : 0;
      var lv = _evolLevel(xp);
      var badge = el.querySelector('.char-level-badge');
      if(!badge){
        badge = document.createElement('span');
        badge.className = 'char-level-badge';
        el.appendChild(badge);
      }
      badge.textContent = 'LV'+lv;
      badge.dataset.level = String(Math.min(lv,9));
    });
  };

  /* ⚪ ÖLÜ YÜZEY — bu turda ekranda GÖRÜLMEDİ, bilerek.
     `#hq-evol-panel` markup'ı `index.html`'de YOK ve bu fonksiyonu çağıran
     kimse yok (`_HQ_PANELS` satırındaki not: *"yuz/evol kaldırıldı"*).
     Yani `if(!panel) return` her zaman dönüyor. Yine de çevrildi: metinleri
     canlı toast ile AYNI sabitlerden okuyor, ham bırakılsaydı panel geri
     geldiği gün oda yarı Türkçe doğardı. Ölçüsü kare değil kod; hüküm
     "ekranda temiz" DEĞİL, "geri gelirse temiz gelir". */
  window.evolRenderPanel = function(){
    var panel = document.getElementById('hq-evol-panel');
    if(!panel) return;
    var data = _evolGet();
    var html = '';
    html += '<div class="tts-section-title" style="margin-bottom:10px;">◈ '+esc(t('evol.baslik'))+'</div>';
    _EVOL_CHARS.forEach(function(k){
      var d = data[k]||{xp:0,messages:0};
      var xp = d.xp||0, msgs = d.messages||0;
      var lv = _evolLevel(xp);
      var info = _evolXpToNext(xp);
      var label = _evolEtiket(lv);
      var traits = _evolYetenekler(lv);
      html += '<div class="evol-char-row">';
      html += '<div class="evol-char-key">'+k.toUpperCase()+'<span class="char-level-badge" data-level="'+Math.min(lv,9)+'">LV'+lv+'</span></div>';
      html += '<div class="evol-bar-wrap">';
      html += '<div class="evol-bar-label">'+esc(traits.length
        ? t('evol.etiket-yetenek', {etiket: label, yetenekler: traits.join(', ')})
        : label)+'</div>';
      html += '<div class="evol-bar-bg"><div class="evol-bar-fill" style="width:'+info.pct+'%"></div></div>';
      html += '<div class="evol-xp-text">'+esc(tc('evol.xp-mesaj', msgs, {xp: xp, n: msgs}))
        +(lv<9?' · '+esc(t('evol.sonraki',{n:info.remaining})):'')+'</div>';
      html += '</div>';
      html += '</div>';
    });
    panel.innerHTML = html;
  };

  // Mevcut karakter badge'larını güncelle (sayfa yüklenince)
  setTimeout(function(){ _evolUpdateBadges(); }, 500);

  // ════════ BİLDİRİM odası — ortak yardımcılar (panel aşağıda, GELEN KUTUSU) ════════

  /* Yükleme hatasını İNSANCA anlat — 401 bir veri arızası değil (2026-09-08).
     🔴 Ekranda görülen hâli: "Hatırlatıcılar yüklenemedi: HTTP 401". Teknik
     olarak doğru, teşhis olarak yanlış: kullanıcı bildirimlerinin bozulduğunu
     sanır, oysa yalnız oturumu kilitlidir. Yanlış teşhis, yanlış çözüme yollar —
     bu depoda ElevenLabs "401 = geçersiz anahtar" dersi (gerçekte kota) tam
     olarak bunun aynısıydı ve müşteriyi sağlam anahtarını değiştirmeye itiyordu. */
  /* 🔴 Cümle artık İSİM EKLENEREK kurulmuyor (FAZ 3 · Blok 10). Eski hâli
     `_yuklemeHatasi(e, 'hatırlatıcılar')` alıyor ve cümleyi birleştiriyordu;
     iki arıza birden taşıyordu:
       ① İngilizce'de "Reminders could not be loaded" sırası TR'ninkiyle aynı
          değil — çeviri sözlüğe konsa bile sıra kodda kilitli kalırdı.
       ② `ne.charAt(0).toUpperCase()` Türkçe'de 'i' → 'I' basar ('İ' değil).
          Bugün iki isim de 'h'/'b' ile başladığı için görünmüyordu; i ile
          başlayan üçüncü bir isim eklendiği gün cümle sessizce bozulurdu.
     Şimdi `on` = anahtar ÖN EKİ; her durum kendi TAM cümlesi. */
  function _yuklemeHatasi(e, on){
    var k = e && e.durum;
    if(k === 401 || k === 403) return t(on + '-kilitli');
    if(k) return t(on + '-yuklenemedi-http', {kod: k});
    return t(on + '-yuklenemedi');
  }
  function _durumluHata(r, govde){
    var e = new Error('HTTP ' + r.status);
    e.durum = r.status;      // catch tarafı sebebi AYIRT EDEBİLSİN
    e.govde = govde || null;  // ucun KENDİ cümlesi (`detail`) — varsa ekrana o çıkar
    return e;
  }
  /* Gövdesi okunmuş hata. `_durumluHata` senkron kalıyor (beş çağrı yeri onu
     `throw`'un içinde kullanıyor); gövdeye ihtiyaç duyan yol bunu çağırır. */
  async function _govdeliHata(r){
    return _durumluHata(r, await r.json().catch(function(){ return null; }));
  }

  /* Tarih/saat — `yerelKod()` ile. Eskiden `iso.replace('T',' ').slice(0,16)`
     yazıyordu: dilden bağımsız görünür ama DEĞİL, ISO sırası (YYYY-MM-DD)
     bir biçim seçimidir ve İngilizce arayüzde de Türkçe arayüzde de aynı
     kalıyordu. Biçim de çeviriye dahildir (Blok 8, `yerel()` dersi). */
  function _zamanMetni(iso){
    if(!iso) return '';
    try{
      var d = new Date(iso);
      if(isNaN(d)) return '';
      return d.toLocaleString(yerelKod(), {day:'numeric', month:'short',
                                           hour:'numeric', minute:'2-digit'});
    }catch(e){ return ''; }
  }

  /* 🔴 2026-08-28 (FAZ 9): "Bekleyen hatırlatıcılar" bölümü arayüzde vardı ama
     ÖLÜYDÜ — `#intel-reminder-list`'e hiçbir kod yazmıyordu. Bağlandı.
     2026-09-27 (GELEN KUTUSU): liste sağ sütuna taşındı; boş durum JS'ten gelir
     (statik markup kalktı), iptal İKİ ADIMLI (tarayıcı onay kutusu yok). */
  var _bdIptalKurulu = null, _bdIptalZaman = null;
  /* Alarm satırının büyük saati. `_zamanMetni` gün + ay + saat basar (alt satırda o var);
     burada yalnız saat — biçim yine dilden (12/24 saat İngilizce'de farklı). */
  function _bdSaat(iso){
    var d = iso ? new Date(iso) : null;
    if(!d || isNaN(d)) return '—';
    try {
      var saat = '', donem = '';
      new Intl.DateTimeFormat(yerelKod(), {hour: 'numeric', minute: '2-digit'}).formatToParts(d).forEach(function(p){
        if(p.type === 'dayPeriod') donem = p.value; else if(p.type !== 'literal' || !donem) saat += p.value;
      });
      /* Bugün değilse gün adı: büyük saat sütunu tek başına sırasız görünüyordu (17:14 yarının) */
      var gun = d.toDateString() === new Date().toDateString() ? '' : d.toLocaleDateString(yerelKod(), {weekday: 'short'});
      var alt = [donem, gun].filter(Boolean).join(' · ');
      return esc(saat.trim()) + (alt ? '<small>' + esc(alt) + '</small>' : '');
    } catch(e){ return '—'; }
  }

  window.hatirlaticiTazele = async function(){
    var list = document.getElementById('intel-reminder-list');
    var sayac = document.getElementById('intel-reminder-count');
    if(!list) return;
    try {
      var r = await af('/api/reminders');
      if(!r.ok) throw _durumluHata(r);
      var hatirlaticilar = await r.json();
      if(!Array.isArray(hatirlaticilar)) hatirlaticilar = [];
      if(sayac) sayac.textContent = hatirlaticilar.length;
      if(!hatirlaticilar.length){
        list.innerHTML = '<p class="bd-bos">' + esc(t('hq.bildirim.bekleyen-hatirlatici-yok')) + '</p>';
        return;
      }
      /* En yakın alarm üstte — kayıt sırası (kuruluş) kullanıcı için anlamsız */
      hatirlaticilar.sort(function(a, b){ return String(a.next_run || '~').localeCompare(String(b.next_run || '~')); });
      list.innerHTML = hatirlaticilar.map(function(h){
        var ne = _zamanMetni(h.next_run) || h.human || '—';
        return '<div class="bd-alarm' + (h.kind === 'repeat' ? ' tekrar' : '') + '">' +
          '<div class="bd-alarm-saat">' + _bdSaat(h.next_run) + '</div>' +
          '<div class="bd-alarm-govde">' +
            '<p class="bd-alarm-metin">' + esc(h.message || '—') + '</p>' +
            '<p class="bd-alarm-alt">' + esc(h.kind === 'repeat'
              ? t('hq.bildirim.satir-tekrarli', {aralik: h.human || '—', ne: ne})
              : t('hq.bildirim.satir-bir-kez', {ne: ne})) + '</p>' +
          '</div>' +
          '<button type="button" class="bd-iptal" data-id="' + esc(h.id) + '" aria-label="' + esc(t('hq.bildirim.iptal-et')) +
            '" onclick="hatirlaticiIptal(this.dataset.id, this)">' + esc(t('hq.bildirim.iptal')) + '</button>' +
        '</div>';
      }).join('');
    } catch(e) {
      if(sayac) sayac.textContent = '—';   // okunamadı ≠ alarm yok
      list.innerHTML = '<p class="alan-hata">' + esc(_yuklemeHatasi(e, 'hq.bildirim.hatirlatici')) + '</p>';
    }
  };

  /* İki adımlı: ilk tık düğmeyi kurar (4 sn), ikinci tık iptal eder. */
  window.hatirlaticiIptal = async function(id, btn){
    if(btn && _bdIptalKurulu !== btn){
      if(_bdIptalKurulu && _bdIptalKurulu.isConnected){ _bdIptalKurulu.classList.remove('kurulu'); _bdIptalKurulu.textContent = t('hq.bildirim.iptal'); }
      _bdIptalKurulu = btn; btn.classList.add('kurulu'); btn.textContent = t('hq.bildirim.iptal-emin');
      clearTimeout(_bdIptalZaman);
      _bdIptalZaman = setTimeout(function(){
        if(btn.isConnected){ btn.classList.remove('kurulu'); btn.textContent = t('hq.bildirim.iptal'); }
        _bdIptalKurulu = null;
      }, 4000);
      return;
    }
    clearTimeout(_bdIptalZaman); _bdIptalKurulu = null;
    try {
      var r = await af('/api/reminders/' + encodeURIComponent(id), { method:'DELETE' });
      if(!r.ok) throw await _govdeliHata(r);
      hatirlaticiTazele();
    } catch(e){
      /* `e.message` teknik metindir ("HTTP 404"), ucun cümlesi değil — `_ucHatasi`
         gövdeden gelen `detail`i okur, o da katalogdan geliyor (Blok 9 deseni). */
      if(window.bildir) window.bildir(_ucHatasi('hq.bildirim.iptal-edilemedi', e.govde), 'err');
    }
  };

  // ════════ BİLDİRİM · GELEN KUTUSU (2026-09-27) ════════
  // Solda "Yuki ne dedi" (`/api/push/yuki-dedi`) + kanal izi, sağda alarmlar + kanallar.
  // Kişisel 431c1ef'ten YENİDEN yazıldı: ürün testleri bu bölgede ham TR metni, `_esc`'i
  // ve sabit tarih biçimini yasaklıyor. Kaynak adları modül düzeyinde ANAHTAR tutar.
  var _BD_KAYNAK = {
    alarm:    'hq.bildirim.kaynak-alarm',
    sabah:    'hq.bildirim.kaynak-sabah',
    gecikmis: 'hq.bildirim.kaynak-gecikmis',
    rutin:    'hq.bildirim.kaynak-rutin',
    sistem:   'hq.bildirim.kaynak-sistem'
  };
  var _bdSayfa = 50, _bdEnEski = null, _bdIstek = 0;

  window.pushlogInit = function(){ pushlogRefresh(); hatirlaticiTazele(); _bdKanalCiz(); };

  /* Bir kayıt: kaynak · zaman · (KAÇIRDIN) · metin · kanal izi.
     KAÇIRDIN = ne ekrana ne telefona ulaştı (ses ekranla birlikte gider). */
  function _bdSatir(k){
    var kacti = !k.ekran && !k.telefon;
    var kaynak = _BD_KAYNAK[k.kaynak] ? t(_BD_KAYNAK[k.kaynak]) : String(k.kaynak || '');
    var iz = function(ad, sayi){
      return '<span class="bd-iz' + (sayi ? ' on' : '') + '" title="' +
        esc(t(sayi ? 'hq.bildirim.iz-ulasti' : 'hq.bildirim.iz-ulasmadi', {kanal: t(ad)})) + '">' + esc(t(ad)) + '</span>';
    };
    return '<div class="bd-kayit' + (kacti ? ' kacti' : '') + '" data-id="' + Number(k.id) + '">' +
      '<div class="bd-kayit-ust"><span class="bd-kaynak">' + esc(kaynak) + '</span>' +
        '<span class="bd-zaman">' + esc(_zamanMetni(k.ts * 1000)) + '</span>' +
        (kacti ? '<span class="bd-kacti">' + esc(t('hq.bildirim.kacirdin')) + '</span>' : '') + '</div>' +
      '<p class="bd-metin">' + esc(k.metin || '') + '</p>' +
      '<div class="bd-izler">' + iz('hq.bildirim.kanal-ekran', k.ekran) + iz('hq.bildirim.kanal-telefon', k.telefon) +
        iz('hq.bildirim.kanal-ses', k.ses) + '</div>' +
    '</div>';
  }

  window.pushlogRefresh = async function(ekle){
    var list = document.getElementById('hq-pushlog-list');
    var daha = document.getElementById('bd-daha'), ozet = document.getElementById('bd-ozet');
    if(!list) return;
    var benim = ++_bdIstek;
    if(!ekle){
      _bdEnEski = null;
      list.innerHTML = '<div class="iskelet iskelet-satir"></div><div class="iskelet iskelet-satir"></div>';
    }
    try {
      var sp = new URLSearchParams({limit: _bdSayfa});
      if(ekle && _bdEnEski) sp.set('once', _bdEnEski);
      var r = await af('/api/push/yuki-dedi?' + sp);
      if(!r.ok) throw _durumluHata(r);
      var d = await r.json();
      if(benim !== _bdIstek) return;          // yerini yeni istek aldı
      var k = d.kayitlar || [];
      if(ozet && !ekle){
        ozet.textContent = d.kacan_7g ? tc('hq.bildirim.kacan-7g', d.kacan_7g) : t('hq.bildirim.kacan-yok');
        ozet.classList.toggle('uyari', !!d.kacan_7g);
      }
      if(k.length) _bdEnEski = k[k.length - 1].id;
      if(daha) daha.hidden = k.length < _bdSayfa;
      if(!ekle && !k.length){
        /* Boş durum arayüzü ÖĞRETİR — "henüz yok" tek başına hiçbir şey söylemiyordu */
        list.innerHTML =
          '<div class="bos">' +
            '<svg class="bos-ikon" viewBox="0 0 24 24" fill="none" aria-hidden="true">' +
              '<path d="M18 8a6 6 0 1 0-12 0c0 7-3 9-3 9h18s-3-2-3-9"/>' +
              '<path d="M13.7 21a2 2 0 0 1-3.4 0"/></svg>' +
            '<p class="bos-bas">' + esc(t('hq.bildirim.gelen-bos-bas')) + '</p>' +
            '<p class="bos-metin">' + esc(t('hq.bildirim.gelen-bos-metin')) + '</p>' +
          '</div>';
        return;
      }
      var html = k.map(_bdSatir).join('');
      if(ekle) list.insertAdjacentHTML('beforeend', html); else list.innerHTML = html;
    } catch(e) {
      list.innerHTML = '<p class="alan-hata">' + esc(_yuklemeHatasi(e, 'hq.bildirim.gecmis')) + '</p>';
    }
  };
  window.pushlogDahaEski = function(){ pushlogRefresh(true); };

  /* Yuki kendiliğinden bir şey söyleyince (core.js `yuki:proaktif`) günlük tazelenir.
     Kayıt backend'de TTS bittikten sonra yazılır → iki deneme (kısa + uzun). */
  window.addEventListener('yuki:proaktif', function(){
    [2500, 22000].forEach(function(ms){
      setTimeout(function(){
        var l = document.getElementById('hq-pushlog-list');
        if(l && l.offsetParent) pushlogRefresh();
      }, ms);
    });
  });

  /* ── Tek kutudan alarm ──
     "18:30 …" · "yarın 09:00 …" · "20 dk sonra …" · "her 2 saat …" · "30 dakikada bir …"
     (+ İngilizce: "tomorrow 09:00 …" · "in 20 min …" · "every 2 hours …").
     🔴 Saatli tekrar ("her gün 20:00") REDDEDİLİR: backend aralık tetikleyicisi saati yok
     sayıyordu; artık backend de reddediyor (scheduler.parse_recurring), burada erken söylenir.
     Tek seferlik alarm burada KESİN ZAMANA çevrilir (yerel ISO) — backend'e birim kelimesi
     gitmez ("1 gün" ile "1 gun" arasındaki fark sunucuda sessizce kaybolmasın).
     Tekrar için backend'in ASCII'de de anladığı birim yollanır (dakika · saat · saniye · day).
     Birim kelimesi Türkçe harfler katlanarak aranır — tırnak içi TR harf bu bölgede yasak. */
  var _BD_BIRIM = {  // saniye cinsinden · tekrar için backend kelimesi
    dk: [60, 'dakika'], dakika: [60, 'dakika'], min: [60, 'dakika'], mins: [60, 'dakika'], minute: [60, 'dakika'], minutes: [60, 'dakika'],
    sa: [3600, 'saat'], saat: [3600, 'saat'], h: [3600, 'saat'], hour: [3600, 'saat'], hours: [3600, 'saat'],
    sn: [1, 'saniye'], saniye: [1, 'saniye'], sec: [1, 'saniye'], second: [1, 'saniye'], seconds: [1, 'saniye'],
    gun: [86400, 'day'], day: [86400, 'day'], days: [86400, 'day']
  };
  function _bdIki(n){ return ('0' + n).slice(-2); }
  function _bdIso(d){
    return d.getFullYear() + '-' + _bdIki(d.getMonth() + 1) + '-' + _bdIki(d.getDate()) +
      'T' + _bdIki(d.getHours()) + ':' + _bdIki(d.getMinutes()) + ':' + _bdIki(d.getSeconds());
  }
  function _alarmAyir(metin){
    var s = (metin || '').trim(), m, b;
    if(!s) return null;
    if(/^(her|every)\b/i.test(s) && /\b\d{1,2}[:.]\d{2}\b/.test(s)) return {hata: 'hq.bildirim.alarm-saatli-tekrar'};
    if((m = s.match(/^(\d{1,2})[:.](\d{2})\s+(.+)$/))) return {when: _bdIki(m[1]) + ':' + m[2], message: m[3], repeat: false};
    if((m = s.match(/^(yar[ıi]n|tomorrow)\s+(\d{1,2})[:.](\d{2})\s+(.+)$/i))){
      var d = new Date(); d.setDate(d.getDate() + 1); d.setHours(+m[2], +m[3], 0, 0);
      return {when: _bdIso(d), message: m[4], repeat: false};
    }
    var kalip = [
      [/^(\d+)\s*([a-zçğıöşü]+)\s+sonra\s+(.+)$/i, false],
      [/^in\s+(\d+)\s*([a-z]+)\s+(.+)$/i, false],
      [/^(?:her|every)\s+(\d*)\s*([a-zçğıöşü]+)\s+(.+)$/i, true],   // sayısız = 1 ("her gün")
      [/^(\d+)\s*([a-zçğıöşü]+?)(?:da|de|ta|te)\s*bir\s+(.+)$/i, true]
    ];
    for(var i = 0; i < kalip.length; i++){
      if((m = s.match(kalip[i][0]))){
        b = _BD_BIRIM[m[2].toLowerCase().replace(/ü/g, 'u')];
        if(m[1] === '') m[1] = '1';
        if(!b || +m[1] <= 0) return null;
        if(kalip[i][1]) return {when: 'her ' + m[1] + ' ' + b[1], message: m[3], repeat: true};
        return {when: _bdIso(new Date(Date.now() + m[1] * b[0] * 1000)), message: m[3], repeat: false};
      }
    }
    return null;
  }

  window.bdAlarmKur = async function(){
    var girdi = document.getElementById('bd-alarm-girdi'), durum = document.getElementById('bd-alarm-durum');
    var a = _alarmAyir(girdi && girdi.value);
    if(!a || a.hata){
      if(durum){ durum.className = 'bd-not alan-hata'; durum.textContent = t(a && a.hata ? a.hata : 'hq.bildirim.alarm-anlasilmadi'); }
      if(girdi) girdi.setAttribute('aria-invalid', 'true');
      return;
    }
    if(girdi) girdi.removeAttribute('aria-invalid');
    try {
      var r = await af('/api/reminders', {method: 'POST', headers: {'Content-Type': 'application/json'}, body: JSON.stringify(a)});
      if(!r.ok) throw await _govdeliHata(r);
      if(durum){ durum.className = 'bd-not'; durum.textContent = t('hq.bildirim.alarm-kuruldu', {mesaj: a.message}); }
      if(girdi) girdi.value = '';
      hatirlaticiTazele();
    } catch(e){
      if(durum){ durum.className = 'bd-not alan-hata';
        durum.textContent = e && e.durum ? _ucHatasi('hq.bildirim.alarm-kurulamadi', e.govde) : agHatasi(e); }
    }
  };

  /* ── Kanallar: EKRAN (bu pencere canlı mı) · TELEFON (kaç cihaz abone, bu cihaz dahil mi) · SES ──
     SES ekranla birlikte gider (backend yalnız açık pencereye seslendirir) — ışığı EKRAN'ınkiyle aynı;
     ayrı gösterilmeyince günlükteki yanık SES izinin karşılığı sağda yoktu (goz 09-27). */
  async function _bdKanalCiz(){
    var kap = document.getElementById('bd-kanallar'); if(!kap) return;
    var ekran = window.yukiEkranBagli ? window.yukiEkranBagli() : false;
    var abone = null, buCihaz = false;
    try { var r = await af('/api/push/subscriptions/count'); if(r.ok) abone = (await r.json()).count; } catch(e){}
    try {
      if('serviceWorker' in navigator && 'PushManager' in window && window.Notification && Notification.permission === 'granted'){
        var reg = await navigator.serviceWorker.getRegistration();
        buCihaz = !!(reg && await reg.pushManager.getSubscription());
      }
    } catch(e){}
    var satir = function(ad, acik, alt){
      return '<div class="bd-kanal' + (acik ? ' acik' : '') + '"><span class="bd-isik" aria-hidden="true"></span>' +
        '<span class="bd-kanal-ad">' + esc(t(ad)) + '</span><span class="bd-kanal-alt">' + esc(alt) + '</span></div>';
    };
    var telAlt = abone == null ? '—' : (abone ? tc('hq.bildirim.telefon-n', abone) : t('hq.bildirim.telefon-yok'));
    if(buCihaz) telAlt += ' · ' + t('hq.bildirim.bu-cihaz-bagli');
    kap.innerHTML = satir('hq.bildirim.kanal-ekran', ekran, t(ekran ? 'hq.bildirim.ekran-acik' : 'hq.bildirim.ekran-kapali')) +
      satir('hq.bildirim.kanal-telefon', !!abone, telAlt) +
      satir('hq.bildirim.kanal-ses', ekran, t('hq.bildirim.ses-ekranla'));
    var bagla = document.getElementById('bd-bagla'); if(bagla) bagla.hidden = buCihaz;
    var test = document.getElementById('bd-test'); if(test) test.disabled = !abone;
  }

  window.bdBagla = async function(){
    var durum = document.getElementById('bd-kanal-durum');
    if(!window.yukiBildirimBagla) return;
    if(durum) durum.textContent = t('hq.bildirim.baglaniyor');
    var s = await window.yukiBildirimBagla();
    if(durum) durum.textContent = s.ok ? t('hq.bildirim.baglandi') : t('hq.bildirim.baglanamadi-' + (s.neden || 'sunucu'));
    _bdKanalCiz();
  };

  window.bdTest = async function(){
    var durum = document.getElementById('bd-kanal-durum');
    try {
      var r = await af('/api/push/test', {method: 'POST'});
      var d = await r.json().catch(function(){ return {}; });
      if(!r.ok) throw _durumluHata(r, d);
      var n = d.sent || 0;
      if(durum) durum.textContent = tc('hq.bildirim.gonderildi', n, {n: n});
    } catch(e){
      if(durum) durum.textContent = e && e.durum ? _ucHatasi('hq.bildirim.gonderilemedi', e.govde) : agHatasi(e);
    }
  };

})();
