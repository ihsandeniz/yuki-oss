/* ══════════════════════════════════════════════════════════════════
   GÖREV ŞERİDİ — Yuki Atölye v2, Faz 0c  + Faz 0d 
   Halka Konsolu'nun (#input-area) üstünde tek satır:
     [tür · ad]  adım n/N  ▬▬▬───  DURUM  [DURDUR | DEVAM | ONAYLA] [İPTAL]
   Veri: GET /api/gorev (açılış + 20 sn'de bir, sekme görünürken) ve WS `gorev`
   olayı (core.js → window 'yuki:gorev'). Aynı anda tek görev koşar (servis kuralı);
   şerit koşanı, yoksa onay bekleyeni, yoksa en son güncellenen durdu/yarım görevi gösterir.
   DEVAM iki dokunuşludur ("ONAYLA?", 3 sn) — karar 3: devam yalnız onayla.
   confirm()/alert() KULLANILMAZ (planner dersi: yanıtsız diyalog sessizce false).

   Faz 0d — YENİ GÖREV formu (#gorev-form, araç yayındaki "Görev" düğmesi):
     tür · ad · istek + tavanlar ve çalışma alanı yolu gösterilir → BAŞLAT.
     Masaüstü (yerel bağlam): görev hemen koşar.
     Telefon (dış bağlam): sunucu `bekliyor` taslak + tek kullanımlık kod döner;
     ikinci dokunuş ONAYLA kodu geri yollar (karar 1). Masaüstüne bildirim gider,
     onaysız taslak 5 dk'da düşer. Kod yalnız bu sekmede (sessionStorage) tutulur.
     `masaustu` kipinde telefon onaylayamaz — ekran hangi görevin masaüstünde onaylanacağını gösterir.
     Telefondan DEVAM ve tavan uzatma yok (sunucu 403) — şerit düğmeyi göstermez.

   Harness H4 — ÖNERİ kartı (#gorev-oneri, şeridin üstünde): Yuki'nin öneri motorunun yazdığı
     açık öneriler (GET /api/gorev/oneri) — en öncelikli tek kart + "+n" sayacı:
       [ÖNERİ · KAYNAK] ad · ne yapılacak   GEÇ  SONRA  ONAYLA (yarım işte DEVAM)
     GEÇ = reddet (aynı kaynak 7 gün susar) · SONRA = ertele (ertesi açılışta yeniden) ·
     ONAYLA = sıraya al (iş sırası pencere/bütçe uygunsa başlatır). Masaüstü (yerel) onaylar;
     GEÇ/SONRA her yerden.
   Harness H5 — telefon onayı + TÜMÜNÜ DURDUR:
     · Telefonda (dış bağlam, `dokunus` kipi) ONAYLA iki dokunuştur: ilki sunucudan tek
       kullanımlık kod alır ("ONAYLA?" + geri sayım), ikincisi kodu geri yollar. Kod yalnız
       bu sayfanın belleğinde. `masaustu` kipinde ve yarım işte (DEVAM) düğme gizli,
       "onay masaüstünden" yazar (sunucu da 403 verir).
     · TÜMÜNÜ DURDUR (şeritte, iş koşarken ya da sırada iş varken; telefonda da): tek
       dokunuş — koşanı durdurur, sırayı ve önerileri erteler, öneri turunu bugün kapatır.
   ══════════════════════════════════════════════════════════════════ */
(function () {
  'use strict';

  const DURUM_AD = { kosuyor: 'KOŞUYOR', durdu: 'DURDU', yarim: 'YARIM', bitti: 'BİTTİ', hata: 'HATA',
                     bekliyor: 'ONAY BEKLİYOR', dustu: 'DÜŞTÜ' };
  const NEDEN_AD = {
    durdur: 'sen durdurdun', yeniden_baslatma: 'Yuki yeniden başladı', kota: 'kota doldu',
    saglayici_hatasi: 'sağlayıcı hatası', ucretli_saglayici: 'ücretli yol kapalı',
    adim: 'adım tavanı', sure: 'süre tavanı', token: 'token tavanı',
    onay_suresi: 'onaylanmadı', yanlis_kod: 'onay kodu yanlış', iptal: 'iptal edildi',
  };
  // Tavanda kalan görevi sürdürmek tavanı uzatmayı gerektirir (yoksa hemen yine durur).
  const UZAT = { adim: { adim: 20 }, sure: { sure_sn: 900 }, token: { token: 500000 } };
  const BITTI_GORUNUR_MS = 8000;
  const KOD_ANAHTAR = 'gorev_onay_v1';     // sessionStorage: {gid: kod} — yalnız bu sekme

  let gorevler = new Map();
  let serit = null;
  let onayZamani = 0;
  let bittiZamanlayici = null;
  let sayacZamanlayici = null;
  let seritBoyu = -1;             // son bildirilen yükseklik (hidden → 0)
  let ortam = { baglam: 'yerel', onay_kipi: 'dokunus', turler: [], kok: '<atölye kökü>' };
  let oneriler = [];
  let kart = null;
  const oneriKod = new Map();     // H5: öneri id → {kod, son} — telefonda 1. dokunuşun kodu (yalnız bellek)
  let kartSayac = null;
  const KAYNAK_AD = { plan: 'PLAN', sohbet: 'SOHBET', yarim: 'YARIM İŞ', rutin: 'TEKRAR',
                      kullanici: 'SEN', takvim: 'TAKVİM' };
  const TUR_AD = { arastirma: 'ARAŞTIRMA', site: 'SİTE', deneme: 'DENEME', sahne: 'SAHNE' };

  // ── Genel bildirim: canlı izlenen görev bitince ekranda duyuru ─────────
  // Yalnız bu sekmenin KOŞARKEN gördüğü görev duyurulur (açılışta eski bitişler değil);
  // kullanıcının durdurduğu iş duyurulmaz; aynı bitiş bir kez; Yuki konuşuyorsa en çok
  // DUYURU_BEKLE_MS bekler, sonra yine söyler. Tek kanal: sohbete Yuki mesajı (toast ikilerdi). Push'u backend yollar (gorev_bildirim.py).
  const DUYURU_BEKLE_MS = 60000;
  const DUYURU_SONUC = { bitti: 'bitti', yarim: 'yarım kaldı', hata: 'hata verdi', durdu: 'durdu' };
  const duyurulan = new Set();
  const duyuruSayac = { soylenen: 0, tekrar: 0, kullanici: 0, gecikti: 0 };
  function _yukiKonusuyor() {
    try { return typeof isPlayingAudio !== 'undefined' && !!isPlayingAudio; } catch (_) { return false; }
  }
  function duyuruMetni(g) {
    if (!g || !DUYURU_SONUC[g.durum]) return null;
    if (g.durum === 'durdu' && g.neden === 'durdur') return null;
    const tur = TUR_AD[g.tur] || 'ATÖLYE';
    const k = 'gorev.duyuru-' + g.durum;     // sözlükte varsa o (tr/en), yoksa Türkçe yedek
    const m = window.YukiDil ? YukiDil.t(k, { tur: tur, ad: g.ad }) : k;
    return (m && m !== k) ? m : `Atölye · ${tur} «${g.ad}» ${DUYURU_SONUC[g.durum]}.`;
  }
  function _duyur(g, basla) {
    const metin = duyuruMetni(g);
    if (!metin) { duyuruSayac.kullanici++; return; }
    basla = basla || Date.now();
    if (_yukiKonusuyor() && Date.now() - basla < DUYURU_BEKLE_MS) {
      setTimeout(() => _duyur(g, basla), 1000);
      return;
    }
    if (Date.now() - basla >= DUYURU_BEKLE_MS) duyuruSayac.gecikti++;
    try { if (typeof addMessage === 'function') addMessage('yuki', metin); } catch (_) {}
    duyuruSayac.soylenen++;
  }
  function _bitisDuyurusu(once, g) {
    if (!once || once.durum !== 'kosuyor' || g.durum === 'kosuyor') return;
    const k = `${g.id}@${g.guncelleme || ''}`;
    if (duyurulan.has(k)) { duyuruSayac.tekrar++; return; }
    duyurulan.add(k);
    _duyur(g);
  }

  function _token() { try { return (sessionStorage.getItem('aliceToken') || localStorage.getItem('aliceToken') || ''); } catch (_) { return ''; } }
  function _istek(yol, opts = {}) {
    const t = _token();
    if (t) opts.headers = { ...(opts.headers || {}), Authorization: `Bearer ${t}` };
    return fetch(yol, opts);
  }
  async function _post(yol, govde) {
    const r = await _istek(yol, { method: 'POST', headers: { 'Content-Type': 'application/json' },
                                  body: JSON.stringify(govde || {}) });
    let veri = null;
    try { veri = await r.json(); } catch (_) {}
    if (!r.ok) {
      const d = veri && veri.detail;
      throw new Error(typeof d === 'string' ? d : `HTTP ${r.status}`);
    }
    return veri;
  }

  // ── onay kodu (dokunus kipi) ─────────────────────────────────────
  function _kodlar() {
    try { return JSON.parse(sessionStorage.getItem(KOD_ANAHTAR) || '{}') || {}; } catch (_) { return {}; }
  }
  function _kodYaz(gid, kod) {
    const k = _kodlar();
    if (kod) k[gid] = kod; else delete k[gid];
    try { sessionStorage.setItem(KOD_ANAHTAR, JSON.stringify(k)); } catch (_) {}
  }
  function _onaylanabilir(g) {
    if (!g || g.durum !== 'bekliyor') return false;
    if (ortam.baglam === 'yerel') return true;                     // masaüstü: kodsuz
    return ortam.onay_kipi === 'dokunus' && !!_kodlar()[g.id];
  }
  function _kalan(g) {
    const s = Math.max(0, Math.round((Number(g.onay_son || 0) * 1000 - Date.now()) / 1000));
    return `${Math.floor(s / 60)}:${String(s % 60).padStart(2, '0')}`;
  }

  function _sayi(n) {
    const v = Number(n || 0);
    if (v >= 1e6) return `${(v / 1e6).toLocaleString('tr-TR', { maximumFractionDigits: 1 })} M`;
    if (v >= 1e3) return `${Math.round(v / 1e3).toLocaleString('tr-TR')} B`;
    return v.toLocaleString('tr-TR');
  }
  function _tavanMetni(t) {
    if (!t) return '—';
    const dk = Math.round(Number(t.sure_sn || 0) / 60);
    return `${t.adim} adım · ${dk} dk · ${_sayi(t.token)} token`;
  }

  // ── şerit ────────────────────────────────────────────────────────
  function _kur() {
    if (serit) return serit;
    const alan = document.getElementById('input-area');
    if (!alan) return null;
    serit = document.createElement('div');
    serit.id = 'gorev-serit';
    serit.setAttribute('role', 'status');
    serit.setAttribute('aria-live', 'polite');
    serit.hidden = true;
    serit.innerHTML =
      '<span class="gs-isaret" aria-hidden="true"></span>' +
      '<span class="gs-kimlik"><span class="gs-tur"></span><span class="gs-ad"></span></span>' +
      '<span class="gs-adim"></span>' +
      '<span class="gs-cubuk" aria-hidden="true"><i></i></span>' +
      '<span class="gs-durum"></span>' +
      // Ana düğme DOM'da İLK `.gs-dugme` kalır (0c testleri ve mutasyonları onu seçer);
      // İPTAL yalnız onay bekleyen taslakta görünür, sırası CSS `order` ile.
      '<button type="button" class="gs-dugme gs-ana"></button>' +
      '<button type="button" class="gs-iptal" hidden>İPTAL</button>' +
      // H5: TÜMÜNÜ DURDUR — `.gs-dugme` sınıfı YOK (ana düğme seçicileri ona kaymasın).
      '<button type="button" class="gs-tumu" hidden aria-label="Tüm Atölye işlerini durdur, sırayı ve önerileri ertele">TÜMÜNÜ DURDUR</button>';
    serit.querySelector('.gs-ana').addEventListener('click', _dugme);
    serit.querySelector('.gs-tumu').addEventListener('click', _tumunuDurdur);
    serit.querySelector('.gs-iptal').addEventListener('click', _iptal);
    const kap = document.getElementById('input-container');
    alan.insertBefore(serit, kap || alan.firstChild);
    return serit;
  }

  function _secili() {
    const liste = [...gorevler.values()];
    const kosan = liste.find(g => g.durum === 'kosuyor');
    if (kosan) return kosan;
    const bekleyen = liste.find(g => g.durum === 'bekliyor');
    if (bekleyen) return bekleyen;
    const sirali = liste.sort((a, b) => String(b.guncelleme || '').localeCompare(String(a.guncelleme || '')));
    return sirali.find(g => g.durum === 'durdu' || g.durum === 'yarim' || g.durum === 'hata' ||
                            ((g.durum === 'bitti' || g.durum === 'dustu') && g._taze)) || null;
  }

  function _ciz() {
    const s = _kur();
    if (!s) return;
    const g = _secili();
    s.hidden = !g;
    document.body.classList.toggle('gorev-serit-acik', !!g);
    clearInterval(sayacZamanlayici);
    if (!g) { s.dataset.id = ''; _boyBildir(s); return; }
    s.dataset.id = g.id;
    s.dataset.durum = g.durum;
    const n = g.adim || 0, N = g.adim_tavani || 0;
    s.querySelector('.gs-tur').textContent = TUR_AD[g.tur] || String(g.tur || '').toLocaleUpperCase('tr');
    // biten işte ad yerine çıktının klasörü — dosyalar nerede, kartta görünsün
    const adEl = s.querySelector('.gs-ad');
    const yolKip = (g.durum === 'bitti' || g.durum === 'dustu') && !!g.alan;
    adEl.classList.toggle('gs-yol', yolKip);   // dar ekranda baştan kısalır, klasör adı kalır
    adEl.textContent = yolKip ? '\u200e' + g.alan + '\u200e' : (g.ad || '');
    adEl.title = g.alan ? `klasör: ${g.alan}` : '';
    const adim = s.querySelector('.gs-adim');
    if (g.durum === 'bekliyor') {
      adim.textContent = _kalan(g);
      adim.setAttribute('aria-label', `onay için kalan süre ${_kalan(g)}`);
      sayacZamanlayici = setInterval(() => {
        adim.textContent = _kalan(g);
        if (Number(g.onay_son || 0) * 1000 <= Date.now()) { clearInterval(sayacZamanlayici); yenile(); }
      }, 1000);
    } else if (g.sahne) {
      // araştırma sahnesinde "adım" ilerleme olayı sayısıdır — anlamlı olan kaynak/blok
      adim.textContent = `${g.sahne.kaynak || 0} kaynak · ${g.sahne.blok || 0} blok`;
      adim.removeAttribute('aria-label');
    } else {
      adim.textContent = N ? `adım ${n}/${N}` : `adım ${n}`;
      adim.removeAttribute('aria-label');
    }
    const ASAMA_PAY = { hazirlik: 5, arama: 35, yazim: 70, dizim: 95, bitti: 100 };
    s.querySelector('.gs-cubuk i').style.width = g.sahne ? `${ASAMA_PAY[g.sahne.asama] || 0}%`
      : (N ? `${Math.min(100, Math.round(100 * n / N))}%` : '0%');
    let neden = g.neden && NEDEN_AD[g.neden] ? ` · ${NEDEN_AD[g.neden]}` : '';
    const dis = ortam.baglam === 'dis';
    if (g.durum === 'bekliyor' && !_onaylanabilir(g)) neden = ' · masaüstünden';
    if ((g.durum === 'durdu' || g.durum === 'yarim') && dis) neden = ' · devam masaüstünden';
    s.querySelector('.gs-durum').textContent = (DURUM_AD[g.durum] || g.durum) + neden;
    const b = s.querySelector('.gs-ana');
    const iptal = s.querySelector('.gs-iptal');
    iptal.hidden = g.durum !== 'bekliyor';
    iptal.setAttribute('aria-label', `${g.ad} taslağını iptal et`);
    const onayBekliyor = Date.now() - onayZamani < 3000 && b.dataset.eylem === 'devam';
    if (g.durum === 'kosuyor') {
      b.hidden = false; b.dataset.eylem = 'durdur'; b.textContent = 'DURDUR';
      b.setAttribute('aria-label', `${g.ad} görevini durdur`);
    } else if (g.durum === 'bekliyor' && _onaylanabilir(g)) {
      b.hidden = false; b.dataset.eylem = 'onayla'; b.textContent = 'ONAYLA';
      b.setAttribute('aria-label', `${g.ad} görevini onayla ve başlat`);
    } else if ((g.durum === 'durdu' || g.durum === 'yarim') && !dis) {
      const uzat = g.durum === 'yarim' ? UZAT[g.neden] : null;
      b.hidden = false; b.dataset.eylem = 'devam';
      b.textContent = onayBekliyor ? 'ONAYLA?' : (uzat ? `DEVAM +${uzat.adim ? uzat.adim + ' adım' : uzat.sure_sn ? '15 dk' : 'token'}` : 'DEVAM');
      b.setAttribute('aria-label', `${g.ad} görevini sürdür (iki dokunuş)`);
    } else {
      b.hidden = true; b.dataset.eylem = '';
    }
    s.querySelector('.gs-tumu').hidden = !_tumuGorunur(g);
    _boyBildir(s);
  }

  // ── TÜMÜNÜ DURDUR (Harness H5) ───────────────────────────────────
  function _siradaSayisi() { return oneriler.filter(k => k.durum === 'sirada').length; }
  function _tumuGorunur(g) { return (!!g && g.durum === 'kosuyor') || _siradaSayisi() > 0; }

  async function _tumunuDurdur(ev) {
    ev.preventDefault();
    const b = ev.currentTarget;
    if (b.disabled) return;
    b.disabled = true;
    try {
      const r = await _post('/api/gorev/tumunu-durdur', {});
      oneriKod.clear();
      oneriler = oneriler.map(k => (['sirada', 'oneri', 'onay_bekliyor'].includes(k.durum)
        ? { ...k, durum: 'ertelendi' } : k));
      _kartCiz();
      await yenile();
      const n = (r && r.durdurulan ? r.durdurulan.length : 0);
      if (serit && !serit.hidden) {
        // goz H5 1. tur: uzun metin telefonda sarılıp adım satırını itiyordu → kısa metin, ayrıntı title'da
        const d = serit.querySelector('.gs-durum');
        d.textContent = 'TÜMÜ DURDU';
        d.title = `${n} iş durdu · sıradakiler ertelendi · öneriler yarına kadar kapalı`;
      }
    } catch (e) {
      _hataGoster(e && e.message ? e.message : 'bağlantı yok');
    } finally {
      b.disabled = false;
    }
  }

  // hud-ring widget alt payını şeridin TEPESİNDEN ölçer (`yuki:gorev-serit`). Olay içerik
  // dolduktan SONRA ve boy her değiştiğinde yayılır: 0c'de görünür olduğu an (bayat içerikle)
  // yayılıyordu; 0d taslak şeridi telefonda daha uzun → widget ONAYLA'nın üstüne biniyordu.
  function _boyBildir(s) {
    // H4: ÖNERİ kartı da şeridin üstünde yer kaplar — imza ikisini birlikte tutar (kart açılıp
    // kapanınca da widget payı yeniden ölçülsün; hud-ring.js _widgetAltPay kartın tepesine bakar).
    let boy = s.hidden ? 0 : Math.round(s.getBoundingClientRect().height);
    if (kart && !kart.hidden) boy += 1000 + Math.round(kart.getBoundingClientRect().height);
    if (boy === seritBoyu) return;
    seritBoyu = boy;
    try { window.dispatchEvent(new CustomEvent('yuki:gorev-serit', { detail: { acik: boy > 0 } })); } catch (_) {}
  }

  function _hataGoster(metin) {
    if (serit) serit.querySelector('.gs-durum').textContent = `⚠ ${metin}`;
  }

  async function _dugme(ev) {
    ev.preventDefault();
    const s = serit, b = ev.currentTarget, id = s && s.dataset.id;
    if (!id || b.disabled) return;
    const g = gorevler.get(id);
    if (b.dataset.eylem === 'devam' && Date.now() - onayZamani > 3000) {
      onayZamani = Date.now();
      b.textContent = 'ONAYLA?';
      b.classList.add('gs-onay');
      setTimeout(() => { b.classList.remove('gs-onay'); _ciz(); }, 3000);
      return;
    }
    onayZamani = 0;
    b.classList.remove('gs-onay');
    b.disabled = true;
    try {
      const yol = `/api/gorev/${encodeURIComponent(g.tur)}/${encodeURIComponent(g.ad)}/${b.dataset.eylem}`;
      let govde = {};
      if (b.dataset.eylem === 'devam') govde = { onay: true, uzat: g.durum === 'yarim' ? (UZAT[g.neden] || null) : null };
      if (b.dataset.eylem === 'onayla') govde = ortam.baglam === 'dis' ? { kod: _kodlar()[g.id] || '' } : {};
      const yeni = await _post(yol, govde);
      if (b.dataset.eylem === 'onayla') _kodYaz(g.id, null);
      _guncelle(yeni);
    } catch (e) {
      _hataGoster(e && e.message ? e.message : 'bağlantı yok');
    } finally {
      b.disabled = false;
    }
  }

  async function _iptal(ev) {
    ev.preventDefault();
    const id = serit && serit.dataset.id, g = id && gorevler.get(id), b = ev.currentTarget;
    if (!g || b.disabled) return;
    b.disabled = true;
    try {
      _guncelle(await _post(`/api/gorev/${encodeURIComponent(g.tur)}/${encodeURIComponent(g.ad)}/durdur`));
      _kodYaz(g.id, null);
    } catch (e) {
      _hataGoster(e && e.message ? e.message : 'bağlantı yok');
    } finally {
      b.disabled = false;
    }
  }

  function _guncelle(g) {
    if (!g || !g.id) return;
    const once = gorevler.get(g.id);
    _bitisDuyurusu(once, g);
    const son = g.durum === 'bitti' || g.durum === 'dustu';
    // Aynı son durum hem POST yanıtıyla hem WS olayıyla gelir — ikincisi tazeliği silmesin.
    g._taze = son && (!once || once.durum !== g.durum || !!once._taze);
    gorevler.set(g.id, g);
    if (g.durum !== 'bekliyor') _kodYaz(g.id, null);
    if (g._taze) {
      clearTimeout(bittiZamanlayici);
      bittiZamanlayici = setTimeout(() => { g._taze = false; _ciz(); }, BITTI_GORUNUR_MS);
    }
    _ciz();
    _formOlay(g);
  }

  // ── ÖNERİ kartı (Harness H4) ──────────────────────────────────────
  function _kartKur() {
    if (kart) return kart;
    const alan = document.getElementById('input-area');
    if (!alan) return null;
    kart = document.createElement('section');
    kart.id = 'gorev-oneri';
    kart.setAttribute('aria-label', 'Yuki iş önerisi');
    kart.hidden = true;
    kart.innerHTML =
      '<span class="go-isaret" aria-hidden="true"></span>' +
      '<span class="go-etiket"></span>' +
      '<span class="go-ad"></span>' +
      '<span class="go-sayac"></span>' +
      '<span class="go-metin"></span>' +
      '<span class="go-dugmeler" data-dis-etiket="' + (window.YukiDil ? YukiDil.t('gorev.onay-masaustunden') : 'onay masaüstünden') + '">' +
        '<button type="button" class="go-dugme go-gec" data-eylem="reddet">GEÇ</button>' +
        '<button type="button" class="go-dugme go-sonra" data-eylem="ertele">SONRA</button>' +
        '<button type="button" class="go-dugme go-onayla" data-eylem="onayla">ONAYLA</button>' +
      '</span>';
    kart.querySelectorAll('.go-dugme').forEach(b => b.addEventListener('click', _kartDugme));
    alan.insertBefore(kart, _kur() || document.getElementById('input-container') || alan.firstChild);
    return kart;
  }

  function _acikOneriler() {
    const m = /atolye-oneri=(Q-\d{8}-\d{4})/.exec(location.hash || '');
    const hedef = m ? m[1] : '';
    return oneriler.filter(k => k.durum === 'oneri' || k.durum === 'onay_bekliyor')
      .sort((a, b) => (b.id === hedef) - (a.id === hedef) || (a.oncelik || 2) - (b.oncelik || 2) ||
                      String(a.olusturma || '').localeCompare(String(b.olusturma || '')));
  }

  function _kartCiz() {
    const k = _kartKur();
    if (!k) return;
    const acik = _acikOneriler();
    const o = acik[0];
    k.hidden = !o;
    document.body.classList.toggle('gorev-oneri-acik', !!o);
    if (!o) { k.dataset.id = ''; return; }
    k.dataset.id = o.id;
    k.dataset.kaynak = o.kaynak || '';
    const tur = TUR_AD[o.tur] || String(o.tur || '').toLocaleUpperCase('tr');
    k.querySelector('.go-etiket').textContent = `ÖNERİ · ${KAYNAK_AD[o.kaynak] || 'YUKİ'} · ${tur}`;
    k.querySelector('.go-ad').textContent = o.ad || '';
    k.querySelector('.go-sayac').textContent = acik.length > 1 ? `+${acik.length - 1}` : '';
    k.querySelector('.go-sayac').setAttribute('aria-label', acik.length > 1 ? `${acik.length - 1} öneri daha` : '');
    const metin = o.kaynak === 'yarim' ? (o.gerekce || '') : (o.istek_kisa || o.gerekce || '');
    const m = k.querySelector('.go-metin');
    m.textContent = metin;
    m.title = o.gerekce || '';
    const dis = ortam.baglam === 'dis';
    // H5: telefonda yalnız `dokunus` kipinde ve yarım OLMAYAN öneride onay (iki dokunuş).
    const telOnay = dis && ortam.onay_kipi === 'dokunus' && o.kaynak !== 'yarim';
    const onay = k.querySelector('.go-onayla');
    onay.hidden = dis && !telOnay;
    const kod = _oneriKodu(o.id);
    clearInterval(kartSayac);
    onay.classList.toggle('go-onay', !!kod);
    if (kod) {
      const yaz = () => {
        const sn = Math.max(0, Math.round((kod.son * 1000 - Date.now()) / 1000));
        onay.textContent = `ONAYLA? ${Math.floor(sn / 60)}:${String(sn % 60).padStart(2, '0')}`;
        if (sn <= 0) { oneriKod.delete(o.id); clearInterval(kartSayac); _kartCiz(); }
      };
      yaz();
      kartSayac = setInterval(yaz, 1000);
      onay.setAttribute('aria-label', `${o.ad} önerisini onayla — ikinci dokunuş`);
    } else {
      onay.textContent = o.kaynak === 'yarim' ? 'DEVAM' : 'ONAYLA';
      onay.setAttribute('aria-label', `${o.ad} önerisini ${o.kaynak === 'yarim' ? 'sürdür' : 'onayla'}` +
                        (telOnay ? ' (iki dokunuş)' : ''));
    }
    k.querySelector('.go-gec').setAttribute('aria-label', `${o.ad} önerisini geç (7 gün sorulmaz)`);
    k.querySelector('.go-sonra').setAttribute('aria-label', `${o.ad} önerisini sonraya bırak`);
    k.classList.toggle('go-dis', dis && !telOnay);
  }

  function _oneriKodu(id) {
    const v = oneriKod.get(id);
    if (v && v.son * 1000 > Date.now()) return v;
    oneriKod.delete(id);
    return null;
  }

  async function _kartDugme(ev) {
    ev.preventDefault();
    const b = ev.currentTarget, id = kart && kart.dataset.id;
    if (!id || b.disabled) return;
    kart.querySelectorAll('.go-dugme').forEach(x => { x.disabled = true; });
    try {
      const eylem = b.dataset.eylem;
      const telefon = eylem === 'onayla' && ortam.baglam === 'dis';
      const kod = telefon ? _oneriKodu(id) : null;
      const yanit = await _post(`/api/gorev/oneri/${encodeURIComponent(id)}/${eylem}`,
                                kod ? { kod: kod.kod } : {});
      if (telefon && !kod) {
        // 1. dokunuş: sunucu kodu verdi, iş BAŞLAMADI — ikinci dokunuşu bekle.
        if (yanit && yanit.onay_kodu) oneriKod.set(id, { kod: yanit.onay_kodu, son: Number(yanit.onay_son || 0) });
        _kartCiz();
        return;
      }
      oneriKod.delete(id);
      oneriler = oneriler.filter(k => k.id !== id);
      _kartCiz();
      _boyBildir(_kur());
      await yenile();
    } catch (e) {
      oneriKod.delete(id);
      kart.querySelector('.go-onayla').classList.remove('go-onay');
      kart.querySelector('.go-metin').textContent = `⚠ ${e && e.message ? e.message : 'bağlantı yok'}`;
    } finally {
      kart.querySelectorAll('.go-dugme').forEach(x => { x.disabled = false; });
    }
  }

  async function _oneriYenile() {
    try {
      const r = await _istek('/api/gorev/oneri');
      if (!r.ok) return;
      const veri = await r.json();
      oneriler = Array.isArray(veri.oneriler) ? veri.oneriler : [];
    } catch (_) { /* backend yok — kart gizli kalır */ }
  }

  /* Atölye ilk sürümde yok: `ATOLYE=false` (varsayılan) iken /api/gorev* 404 döner ve
     ozellik.js kapıyı kapalı tutar → burada hiç istek atılmaz (20 sn'lik 404 yoklaması olmaz),
     şerit/kart/form kurulmaz. Bayrak açıksa kapı `yuki:ozellik` ile açılır ve şerit yenilenir. */
  function _acik() { return !!(window.YukiOzellik && window.YukiOzellik.acik('atolye')); }

  // Araştırma Sahnesi ön yüzü (js/arastirma-sahnesi.js + css) Atölye açıkken bir kez tembel
  // yüklenir — Atölye kapalı kurulum bu dosyaları hiç indirmez. Sürüm anahtarı burada.
  const SAHNE_V = 4;
  let sahneYuklendi = false;
  function _sahneYukle() {
    if (sahneYuklendi || window.ArastirmaSahnesi) return;
    sahneYuklendi = true;
    const css = document.createElement('link');
    css.rel = 'stylesheet';
    css.href = `/ui/css/arastirma-sahnesi.css?v=${SAHNE_V}`;
    document.head.appendChild(css);
    const js = document.createElement('script');
    js.src = `/ui/js/arastirma-sahnesi.js?v=${SAHNE_V}`;
    js.defer = true;
    js.addEventListener('error', () => { sahneYuklendi = false; });
    document.head.appendChild(js);
  }

  async function yenile() {
    if (!_acik()) return;
    _sahneYukle();
    await _oneriYenile();
    try {
      const r = await _istek('/api/gorev');
      if (!r.ok) return;
      const veri = await r.json();
      ortam = { baglam: veri.baglam || 'dis', onay_kipi: veri.onay_kipi || 'masaustu',
                turler: veri.turler || [], kok: veri.kok || '<atölye kökü>' };
      const yeni = new Map();
      for (const g of veri.gorevler || []) {
        const once = gorevler.get(g.id);
        g._taze = !!(once && once._taze && (g.durum === 'bitti' || g.durum === 'dustu'));
        yeni.set(g.id, g);
      }
      gorevler = yeni;
      _kartCiz();
      _ciz();
    } catch (_) { /* backend yok — şerit gizli kalır */ }
  }

  // ── YENİ GÖREV formu (Faz 0d) ────────────────────────────────────
  let form = null;
  let formTaslak = null;          // onay adımında gösterilen görev
  let formSayac = null;
  let formOnceOdak = null;

  function _slug(v) {
    const tr = { ç: 'c', ğ: 'g', ı: 'i', i: 'i', ö: 'o', ş: 's', ü: 'u' };
    return String(v || '').toLocaleLowerCase('tr')
      .replace(/[çğıöşü]/g, h => tr[h] || h)
      .replace(/[\s_]+/g, '-').replace(/[^a-z0-9-]/g, '').replace(/-{2,}/g, '-')
      .replace(/^-+/, '').slice(0, 40);
  }

  function _formKur() {
    if (form) return form;
    form = document.createElement('div');
    form.id = 'gorev-form';
    form.hidden = true;
    form.innerHTML =
      '<div class="gf-perde" data-kapat="1"></div>' +
      '<form class="gf-kart" role="dialog" aria-modal="true" aria-labelledby="gf-baslik" novalidate>' +
        '<header class="gf-ust"><span id="gf-baslik" class="gf-baslik">ATÖLYE · YENİ GÖREV</span>' +
          '<button type="button" class="gf-kapat" data-kapat="1" aria-label="Kapat">' +
          '<svg viewBox="0 0 24 24" aria-hidden="true"><path d="M6 6l12 12M18 6 6 18"/></svg></button></header>' +
        '<div class="gf-adim1">' +
          '<fieldset class="gf-turler"><legend>TÜR</legend><div class="gf-secenekler"></div></fieldset>' +
          '<p class="gf-tur-aciklama"></p>' +
          '<label class="gf-alan"><span>AD</span><input name="ad" type="text" inputmode="url" autocomplete="off" ' +
            'autocapitalize="off" spellcheck="false" maxlength="40" placeholder="luna-site" required></label>' +
          '<label class="gf-alan"><span>İSTEK</span><textarea name="istek" rows="3" maxlength="4000" ' +
            'placeholder="Ne yapılsın? Örn: Luna için tek sayfa tanıtım sitesi ve SVG logo." required></textarea></label>' +
          '<dl class="gf-bilgi"><div><dt>TAVAN</dt><dd class="gf-tavan"></dd></div>' +
            '<div><dt>ALAN</dt><dd class="gf-yol"></dd></div></dl>' +
          '<p class="gf-hata" role="alert"></p>' +
          '<div class="gf-eylem"><button type="submit" class="gf-ana">BAŞLAT</button></div>' +
        '</div>' +
        '<div class="gf-adim2" hidden>' +
          '<p class="gf-sayac"><span>ONAY BEKLİYOR</span><b class="gf-kalan"></b></p>' +
          '<dl class="gf-ozet">' +
            '<div><dt>TÜR</dt><dd class="gf-o-tur"></dd></div>' +
            '<div><dt>AD</dt><dd class="gf-o-ad"></dd></div>' +
            '<div><dt>TAVAN</dt><dd class="gf-o-tavan"></dd></div>' +
            '<div><dt>ALAN</dt><dd class="gf-o-yol"></dd></div>' +
            '<div><dt>KAYNAK</dt><dd>telefon · masaüstüne bildirim gitti</dd></div>' +
          '</dl>' +
          '<p class="gf-not"></p>' +
          '<p class="gf-hata" role="alert"></p>' +
          '<div class="gf-eylem"><button type="button" class="gf-ikincil gf-vazgec">VAZGEÇ</button>' +
            '<button type="button" class="gf-ana gf-onayla">ONAYLA</button></div>' +
        '</div>' +
      '</form>';
    document.body.appendChild(form);
    form.addEventListener('click', ev => { if (ev.target.closest('[data-kapat]')) formKapat(); });
    form.addEventListener('keydown', ev => { if (ev.key === 'Escape') { ev.stopPropagation(); formKapat(); } });
    const ad = form.querySelector('input[name="ad"]');
    ad.addEventListener('input', () => {
      const s = _slug(ad.value);
      if (s !== ad.value) ad.value = s;
      _formBilgi();
    });
    form.querySelector('.gf-kart').addEventListener('submit', _formGonder);
    form.querySelector('.gf-onayla').addEventListener('click', _formOnayla);
    form.querySelector('.gf-vazgec').addEventListener('click', _formVazgec);
    return form;
  }

  function _seciliTur() {
    const r = form.querySelector('input[name="tur"]:checked');
    return r ? r.value : '';
  }

  function _formBilgi() {
    const t = ortam.turler.find(x => x.ad === _seciliTur());
    const ad = form.querySelector('input[name="ad"]').value || '<ad>';
    form.querySelector('.gf-tur-aciklama').textContent = t ? t.aciklama : '';
    form.querySelector('.gf-tavan').textContent = t ? _tavanMetni(t.tavanlar) : '—';
    form.querySelector('.gf-yol').textContent = `${ortam.kok}/${_seciliTur() || '<tür>'}/${ad}/`;
  }

  function _turleriCiz() {
    const kap = form.querySelector('.gf-secenekler');
    const once = _seciliTur();
    kap.innerHTML = '';
    const turler = ortam.turler.length ? ortam.turler : [{ ad: 'site', aciklama: '' }];
    turler.forEach((t, i) => {
      const l = document.createElement('label');
      l.className = 'gf-secenek';
      const r = document.createElement('input');
      r.type = 'radio'; r.name = 'tur'; r.value = t.ad;
      r.checked = once ? once === t.ad : i === 0;
      r.addEventListener('change', _formBilgi);
      const s = document.createElement('span');
      s.textContent = String(t.ad).toLocaleUpperCase('tr');
      l.append(r, s);
      kap.appendChild(l);
    });
  }

  function _adim(n) {
    form.querySelector('.gf-adim1').hidden = n !== 1;
    form.querySelector('.gf-adim2').hidden = n !== 2;
    form.querySelector('.gf-baslik').textContent = n === 1 ? 'ATÖLYE · YENİ GÖREV' : 'ATÖLYE · ONAY';
    form.querySelectorAll('.gf-hata').forEach(e => { e.textContent = ''; });
  }

  async function formAc() {
    if (!_acik()) return;
    try { if (typeof toggleGirisAraclari === 'function') toggleGirisAraclari(null, false); } catch (_) {}
    _formKur();
    await yenile();
    formOnceOdak = document.activeElement;
    const bekleyen = [...gorevler.values()].find(g => g.durum === 'bekliyor');
    if (bekleyen) _onayAdimi(bekleyen);
    else { _turleriCiz(); _formBilgi(); _adim(1); }
    form.hidden = false;
    document.body.classList.add('gorev-form-acik');
    requestAnimationFrame(() => {
      const hedef = bekleyen ? form.querySelector('.gf-onayla:not([hidden]), .gf-vazgec')
                             : form.querySelector('input[name="ad"]');
      try { hedef && hedef.focus({ preventScroll: true }); } catch (_) {}
    });
  }

  function formKapat() {
    if (!form || form.hidden) return;
    form.hidden = true;
    clearInterval(formSayac);
    formTaslak = null;
    document.body.classList.remove('gorev-form-acik');
    try { formOnceOdak && formOnceOdak.focus && formOnceOdak.focus({ preventScroll: true }); } catch (_) {}
  }

  function _onayAdimi(g) {
    formTaslak = g;
    _adim(2);
    form.querySelector('.gf-o-tur').textContent = String(g.tur || '').toLocaleUpperCase('tr');
    form.querySelector('.gf-o-ad').textContent = g.ad || '';
    form.querySelector('.gf-o-tavan').textContent = _tavanMetni(g.tavanlar);
    form.querySelector('.gf-o-yol').textContent = g.alan || '';
    const onayla = form.querySelector('.gf-onayla');
    const ok = _onaylanabilir(g);
    onayla.hidden = !ok;
    const not = form.querySelector('.gf-not');
    form.querySelector('.gf-sayac span').textContent = ok ? 'ONAY BEKLİYOR' : 'MASAÜSTÜ ONAYI BEKLİYOR';
    if (ok) {
      not.textContent = 'Onaylamazsan 5 dakika sonra kendiliğinden düşer. Sen başlatmadıysan VAZGEÇ.';
    } else {
      not.textContent = 'Bu kipte onay yalnız masaüstünden; süre dolarsa taslak düşer. Masaüstündeki Atölye şeridinden şu görevi onayla:';
      const kod = document.createElement('code');
      kod.className = 'gf-komut';
      kod.textContent = g.id;
      not.appendChild(kod);
    }
    const kalan = form.querySelector('.gf-kalan');
    const tik = () => {
      kalan.textContent = _kalan(g);
      if (Number(g.onay_son || 0) * 1000 <= Date.now()) {
        clearInterval(formSayac);
        onayla.hidden = true;
        form.querySelector('.gf-adim2 .gf-hata').textContent = 'Süre doldu — taslak düştü.';
      }
    };
    clearInterval(formSayac);
    tik();
    formSayac = setInterval(tik, 1000);
  }

  async function _formGonder(ev) {
    ev.preventDefault();
    const hata = form.querySelector('.gf-adim1 .gf-hata');
    const ad = form.querySelector('input[name="ad"]').value.trim();
    const istek = form.querySelector('textarea[name="istek"]').value.trim();
    const tur = _seciliTur();
    if (!ad) { hata.textContent = 'Ad gerekli (küçük harf, rakam, -).'; return; }
    if (!istek) { hata.textContent = 'Ne yapılacağını yaz.'; return; }
    const b = form.querySelector('.gf-adim1 .gf-ana');
    b.disabled = true;
    hata.textContent = '';
    try {
      const g = await _post('/api/gorev/baslat', { tur, ad, istek });
      if (g.onay_kodu) _kodYaz(g.id, g.onay_kodu);
      delete g.onay_kodu;                    // kod şeride/belleğe değil yalnız sessionStorage'a
      gorevler.set(g.id, g);
      _ciz();
      if (g.durum === 'bekliyor') _onayAdimi(g);
      else { formKapat(); form.querySelector('.gf-kart').reset(); }
    } catch (e) {
      hata.textContent = e && e.message ? e.message : 'bağlantı yok';
    } finally {
      b.disabled = false;
    }
  }

  async function _formOnayla(ev) {
    ev.preventDefault();
    const g = formTaslak, b = ev.currentTarget;
    if (!g || b.disabled) return;
    const hata = form.querySelector('.gf-adim2 .gf-hata');
    b.disabled = true;
    try {
      const govde = ortam.baglam === 'dis' ? { kod: _kodlar()[g.id] || '' } : {};
      const yeni = await _post(`/api/gorev/${encodeURIComponent(g.tur)}/${encodeURIComponent(g.ad)}/onayla`, govde);
      _kodYaz(g.id, null);
      _guncelle(yeni);
      formKapat();
      form.querySelector('.gf-kart').reset();
    } catch (e) {
      hata.textContent = e && e.message ? e.message : 'bağlantı yok';
    } finally {
      b.disabled = false;
    }
  }

  async function _formVazgec(ev) {
    ev.preventDefault();
    const g = formTaslak;
    if (!g) { formKapat(); return; }
    try {
      _guncelle(await _post(`/api/gorev/${encodeURIComponent(g.tur)}/${encodeURIComponent(g.ad)}/durdur`));
    } catch (_) { /* düşmüş ya da bağlantı yok — form yine kapanır */ }
    _kodYaz(g.id, null);
    formKapat();
  }

  function _formOlay(g) {
    // Onay ekranı açıkken taslak başka yerden onaylandı/düştüyse formu kapat.
    if (form && !form.hidden && formTaslak && g.id === formTaslak.id && g.durum !== 'bekliyor') formKapat();
  }

  window.addEventListener('yuki:gorev', (e) => _guncelle(e.detail));
  window.addEventListener('hashchange', () => { if (/atolye-oneri=/.test(location.hash)) yenile(); });
  document.addEventListener('yuki:ozellik', () => { if (_acik()) yenile(); });
  document.addEventListener('visibilitychange', () => { if (!document.hidden) yenile(); });
  setInterval(() => { if (!document.hidden) yenile(); }, 20000);
  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', yenile);
  else yenile();

  window.GorevSerit = { yenile, _guncelle, formAc, formKapat, _kartCiz, duyuruMetni,
                        duyuruDurum: () => Object.assign({}, duyuruSayac) };
})();
