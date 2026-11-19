/* ── YÜZ · KİMLİK KARTI ( →  panel 6, 2026-09-27) ────────────────
 * Kişisel Alice 517e975'in ürüne YENİDEN yazılmış hâli (kişiselin kodu değil
 * tasarımı alındı: orada ham Türkçe metin + innerHTML vardı, burada her metin
 * sözlükten gelir ve `textContent` ile basılır).
 *
 * Yerleşim: üstte KİMLİK KARTI — yüzle giriş durumu, sahip + örnek sayısı,
 * canlılık, bu cihazdaki başarısız denemeler, kayıtların tutarlılığı, aykırı
 * örnekler, GİRİŞİ DENE, ÖRNEK EKLE · 5 POZ. Altında kamera | tanıdığım kişiler.
 *
 * 🔑 Bu panel LLM ARACI DEĞİL (geliştirici kararı 2026-09-05): Yuki kendi başına
 * "şu kim" diye kamera açamaz; tarama yalnız kullanıcının tıklamasıyla olur.
 *
 * 🔴 Kamera izni ancak kullanıcı bir düğmeye bastığında istenir ve panel
 * görünmez olduğu AN bırakılır: HQ'da başka panele geçiş (switchHqTab), oda
 * değişimi (hqSelectCat), pencere gizlenmesi (visibilitychange), sayfadan çıkış
 * (pagehide). 09-27'ye kadar yalnız ilk ikisinden biri vardı — başka panele
 * geçince kamera ışığı ve 2,5 sn'lik tarama döngüsü sürüyordu.
 *
 * Ad eşlemesi (geliştirici / Geliştirici) burada YAPILMAZ — sunucu söyler: `/status`
 * `sahip_kaydi`, `/scan` `sahip`. Tek kaynak `face_multi_auth.ad_anahtari`.
 */
(function () {
  'use strict';

  var KOK_ID = 'faces-root';
  var akis = null;            // MediaStream
  var video = null;
  var canliTimer = null;
  var ui = {};                // o anki çizimin düğümleri
  var v = {};                 // o anki veri: status, liste, kalite, kilit (+ hata alanları)
  var sihirbaz = null;        // {ad, adim}
  var OLCEK = 0.7;            // tutarlılık ölçeğinin sağ ucu (0.6'da 'sınır 0,45' etiketi sağdan taşıyordu)

  function af(url, opts) {
    var f = (typeof window.authFetch === 'function') ? window.authFetch : window.fetch.bind(window);
    return f(url, opts || {});
  }

  /* Çeviri: `intro-sequences.js:22`'nin aynısı (iki ayrı IIFE, ortak kaynak `YukiDil`).
     Metin `textContent`e gider — ayrıca kaçırılmaz. */
  function t(anahtar, degerler) {
    return (window.YukiDil && window.YukiDil.t)
      ? window.YukiDil.t(anahtar, degerler) : String(anahtar);
  }
  function tc(anahtar, sayi, degerler) {
    return (window.YukiDil && window.YukiDil.tc)
      ? window.YukiDil.tc(anahtar, sayi, degerler) : String(anahtar);
  }
  function yerel() { return (window.YukiDil && window.YukiDil.yerel) ? window.YukiDil.yerel() : undefined; }
  function sayi(x) { return Number(x).toLocaleString(yerel(), { minimumFractionDigits: 2, maximumFractionDigits: 2 }); }

  function el(etiket, sinif, metin) {
    var d = document.createElement(etiket);
    if (sinif) d.className = sinif;
    if (metin != null) d.textContent = metin;      // ⚠️ innerHTML DEĞİL — XSS kapısı
    return d;
  }
  function dugme(sinif, metin, tik) {
    var b = el('button', sinif, metin);
    b.type = 'button';
    if (tik) b.onclick = tik;
    return b;
  }

  function bildir(mesaj, tur) {
    if (typeof window.bildir === 'function') window.bildir(mesaj, tur || 'bilgi');
    else console.log('[yuz]', tur || '', mesaj);
  }

  function kokAl() { return document.getElementById(KOK_ID); }
  function temizle(k) { while (k.firstChild) k.removeChild(k.firstChild); }
  function basHarf(ad) {
    var h = Array.from(String(ad || '').trim())[0] || '?';
    return h.toLocaleUpperCase(yerel());
  }

  /* Kütüphane inmemiş ekranı — "hata" DEĞİL: özellik açık, dosya henüz inmemiş. */
  function indirmeEkrani(kok, sebep) {
    var k = el('div', 'yk-indir');
    k.appendChild(el('b', null, t('yuz.indirilmedi-bas')));
    k.appendChild(el('p', null, sebep || t('yuz.indirilmedi-sebep')));
    k.appendChild(el('p', null, t('yuz.indirme-notu')));
    var btn = dugme('dg dg-birincil', t('yuz.kutuphaneyi-indir'));
    btn.onclick = async function () {
      btn.disabled = true;
      btn.textContent = t('yuz.indiriliyor');
      var ok = false;
      try {
        ok = window.ModelDownloader && window.ModelDownloader.ensureFaceLib
          ? await window.ModelDownloader.ensureFaceLib() : false;
      } catch (e) { ok = false; }
      btn.disabled = false;
      btn.textContent = t('yuz.kutuphaneyi-indir');
      if (ok) kur(true);
      else bildir(t('yuz.indirilemedi'), 'uyari');
    };
    k.appendChild(btn);
    kok.appendChild(k);
  }

  // ── kamera ────────────────────────────────────────────────────────────────
  async function kamerayiAc() {
    if (akis) return true;
    try {
      akis = await navigator.mediaDevices.getUserMedia({ video: { width: 640, height: 480 } });
      if (!video || !video.isConnected) { kamerayiKapat(); return false; }   // bu arada panel kapandı
      video.srcObject = akis;
      await video.play();
      kameraUi();
      return true;
    } catch (e) {
      akis = null;
      var sebep = e && e.name ? e.name : t('yuz.bilinmeyen-hata');
      /* http'de (güvenli olmayan köken) tarayıcı kamerayı hiç vermez — sebebi söyle */
      if (!window.isSecureContext) sebep = t('yuz.guvensiz-koken');
      if (ui.sonuc) ui.sonuc.textContent = t('yuz.kameraya-erisilemedi', { sebep: sebep });
      return false;
    }
  }

  function kamerayiKapat() {
    if (canliTimer) { clearInterval(canliTimer); canliTimer = null; }
    if (akis) {
      akis.getTracks().forEach(function (iz) { iz.stop(); });
      akis = null;
    }
    if (video) video.srcObject = null;
    if (sihirbaz) sihirbaz = null;
    kameraUi();
  }

  function kameraUi() {
    if (!ui.kamDurum) return;
    var acik = !!akis;
    ui.kamDurum.textContent = t(acik ? 'yuz.kamera-acik' : 'yuz.kamera-kapali-kisa');
    ui.kamDurum.className = 'yk-hud-deger' + (acik ? ' acik' : '');
    ui.perde.hidden = acik;
    ui.btnKamera.textContent = t(acik ? 'yuz.kamerayi-kapat' : 'yuz.kamerayi-ac');
    ui.btnKamera.className = 'dg ' + (acik ? 'dg-ikincil' : 'dg-birincil');
    ui.btnCanli.textContent = t(canliTimer ? 'yuz.canli-durdur' : 'yuz.canli-tanima');
    ui.btnCanli.setAttribute('aria-pressed', String(!!canliTimer));
    sihirbazCiz();
  }

  /* Kareyi JPEG blob'a çevir. 640×480 q=0.85 ≈ 40-70 KB (sunucu tavanı 5 MB). */
  function kareAl() {
    return new Promise(function (cozumle) {
      var c = document.createElement('canvas');
      c.width = video.videoWidth || 640;
      c.height = video.videoHeight || 480;
      c.getContext('2d').drawImage(video, 0, 0, c.width, c.height);
      c.toBlob(function (b) { cozumle(b); }, 'image/jpeg', 0.85);
    });
  }

  async function detay(r, yedek) {
    try { var d = await r.json(); return (d && d.detail) || yedek; } catch (_) { return yedek; }
  }

  // ── sunucu ────────────────────────────────────────────────────────────────
  /* Dört okuma paralel; her biri kendi hatasını taşır — biri düşerse kart kalanını
     yine çizer ("okunamadı" yalnız o parçada yazar). */
  async function veriyiOku() {
    function oku(yol) {
      return af(yol).then(function (r) {
        if (!r.ok) return { hata: r.status };
        return r.json().then(function (d) { return { veri: d }; });
      }).catch(function () { return { hata: 0 }; });
    }
    var s = await Promise.all([oku('/api/face/status'), oku('/api/face/list'),
                               oku('/api/face/quality'), oku('/api/lock/status')]);
    v = { status: s[0].veri || null, statusHata: s[0].hata,
          liste: s[1].veri ? (s[1].veri.faces || []) : null, listeHata: s[1].hata,
          kalite: s[2].veri || null, kaliteHata: s[2].hata,
          kilit: s[3].veri || null };
  }

  async function tazele() {
    await veriyiOku();
    if (!ui.kart || !ui.kart.isConnected) return;
    kartCiz(); kaliteCiz(); listeCiz();
  }

  function sahipKaydiAdi() { return (v.status && (v.status.sahip_kaydi || v.status.owner)) || ''; }

  // ── KİMLİK KARTI ──────────────────────────────────────────────────────────
  function kartCiz() {
    var st = v.status, k = v.kilit, ton = 'ok', baslik, satirlar = [], eylem = 'giris';
    if (!st) {
      ton = 'err'; baslik = t('yuz.kart.okunamadi'); eylem = 'tekrar';
    } else if (!st.enabled) {
      ton = 'off'; baslik = t('yuz.kart.kapali-bas');
      satirlar.push([t('yuz.kart.kapali-alt')]);
      eylem = null;
    } else if (!st.owner) {
      ton = 'warn'; baslik = t('yuz.kart.sahip-yok-bas');
      satirlar.push([t('yuz.kart.sahip-yok-alt')]);
      eylem = 'sahip';
    } else if (!st.sahip_ornek) {
      ton = 'err'; baslik = t('yuz.kart.sahip-bas', { ad: st.owner });
      satirlar.push([t('yuz.kart.ornek-yok')]);
    } else {
      baslik = t('yuz.kart.sahip-bas', { ad: st.sahip_kaydi });
      satirlar.push([tc('yuz.kart.ornek', st.sahip_ornek) + ' · ',
                     st.canlilik ? t('yuz.kart.canlilik-acik')
                                 : { uyari: t('yuz.kart.canlilik-kapali') }]);
    }
    /* Kilit kurulu değilse yüzle giriş devrede değil: yüz kaydı var diye "açık" demek yalan olurdu */
    var yuzKilitli = false;
    if (st && st.enabled && k && !k.kurulu) {
      ton = 'off'; baslik = t('yuz.kart.kilit-yok-bas');
      satirlar.unshift([t('yuz.kart.kilit-yok-alt')]);
      if (eylem === 'giris') eylem = 'kilit';      // ana eylem: parola kilidi kur (yüzü denemek anlamsız)
    } else if (st && st.enabled && k && k.guard && k.guard.face) {
      var g = k.guard.face;
      if (g.locked) {
        yuzKilitli = true;
        if (ton === 'ok') ton = 'warn';
        satirlar.push([{ uyari: tc('yuz.kart.yuz-kilitli', Math.max(1, Math.ceil(g.seconds_left / 60))) }]);
      } else if (g.fails) {
        satirlar.push([tc('yuz.kart.basarisiz', g.fails, { kalan: g.remaining == null ? '∞' : g.remaining })]);
      } else {
        satirlar.push([t('yuz.kart.basarisiz-yok')]);
      }
    }

    ui.isik.className = 'yk-isik ' + ton;
    ui.baslik.textContent = baslik;
    temizle(ui.alt);
    satirlar.forEach(function (parcalar) {
      var p = el('p');
      parcalar.forEach(function (x) {
        if (typeof x === 'string') p.appendChild(document.createTextNode(x));
        else p.appendChild(el('span', 'yk-uyari', x.uyari));
      });
      ui.alt.appendChild(p);
    });
    var ad = st && (st.sahip_kaydi || st.owner);
    ui.avatar.textContent = ad ? basHarf(ad) : '?';
    ui.avatar.classList.toggle('soluk', !(st && st.sahip_ornek));

    temizle(ui.eylem);
    if (eylem === 'tekrar') {
      ui.eylem.appendChild(dugme('dg dg-ikincil', t('yuz.tekrar-dene'), tazele));
    } else if (eylem === 'sahip') {
      ui.eylem.appendChild(dugme('dg dg-birincil', t('yuz.kart.sahip-ekle'), sahipEkle));
    } else if (eylem === 'kilit') {
      ui.eylem.appendChild(dugme('dg dg-birincil', t('yuz.kart.kilide-git'), kilideGit));
      ui.eylem.appendChild(dugme('dg dg-ikincil', t('yuz.kart.ornek-ekle'), function () { sihirbaziBaslat(sahipKaydiAdi()); }));
    } else if (eylem === 'giris') {
      /* Yüzle giriş kilitliyken denemek ikincil — birincil vurgu yanlış eylemi öne çıkarıyordu */
      ui.eylem.appendChild(dugme(yuzKilitli ? 'dg dg-ikincil' : 'dg dg-birincil', t('yuz.kart.girisi-dene'), girisiDene));
      ui.eylem.appendChild(dugme('dg dg-ikincil', t('yuz.kart.ornek-ekle'), function () {
        sihirbaziBaslat(sahipKaydiAdi());
      }));
    }
  }

  function kilideGit() {
    var k = document.getElementById('hq-kilit-bolum');
    if (!k) return;
    k.scrollIntoView({ block: 'start', behavior: 'smooth' });
    var g = document.getElementById('hq-kilit-yeni');
    if (g) setTimeout(function () { g.focus({ preventScroll: true }); }, 350);
  }

  /* Sahip yoksa: kilit bölümünün düğmesiyle AYNI yol (AppLock.sahipKaydet → /enroll).
     O kendi kamerasını açar — bizimkini önce bırak, iki akış aynı cihazı çekişmesin. */
  async function sahipEkle(e) {
    kamerayiKapat();
    if (typeof window.hqYuzuAcilisaEkle === 'function') await window.hqYuzuAcilisaEkle(e && e.currentTarget);
    tazele();
  }

  // GİRİŞİ DENE: kilit ekranının TANIMA hükmü (sahip + kesin eşleşme), selamsız.
  // Canlılık adımı (göz kırpma) burada koşmaz — bunu açıkça söyler.
  async function girisiDene() {
    var yaz = function (metin, ton) { ui.mesaj.textContent = metin; ui.mesaj.className = 'yk-mesaj ' + (ton || ''); };
    if (!sahipKaydiAdi()) { yaz(t('yuz.giris.sahip-yok'), 'err'); return; }
    yaz(t('yuz.giris.bakiyorum'));
    if (!(await kamerayiAc())) { yaz(ui.sonuc.textContent, 'err'); return; }
    await new Promise(function (c) { setTimeout(c, 500); });   // pozlama otursun
    var s = await taraIstek(true);
    if (!s.veri) { yaz(s.hata || t('yuz.tarama-basarisiz'), 'err'); return; }
    var d = s.veri;
    if (d.sahip && d.verdict === 'high') {
      yaz(t('yuz.giris.acilirdi', { ad: d.name }) + (v.status && v.status.canlilik ? ' ' + t('yuz.giris.goz-kirp') : ''), 'ok');
    } else if (d.sahip) {
      yaz(t('yuz.giris.emin-degil'), 'err');
    } else if (d.known) {
      yaz(t('yuz.giris.baskasi', { ad: d.name }), 'err');
    } else {
      yaz(t(d.faces_detected === 0 ? 'yuz.giris.yuz-yok' : 'yuz.giris.tanimadim'), 'err');
    }
  }

  // ── tutarlılık ────────────────────────────────────────────────────────────
  function yer(x) { return Math.max(0, Math.min(100, (x / OLCEK) * 100)).toFixed(1) + '%'; }

  function kaliteCiz() {
    var kutu = ui.kalite;
    temizle(kutu);
    var hud = el('div', 'yk-hud');
    var hudAd = el('span', null, t('yuz.kalite.bas'));
    var hudDeger = el('span', 'yk-hukum');
    hud.appendChild(hudAd); hud.appendChild(hudDeger);
    kutu.appendChild(hud);
    var q = v.kalite;
    if (!q) {
      hudDeger.remove();
      var h = el('div', 'yk-bos');
      h.appendChild(el('span', 'yk-hata', t('yuz.kalite.okunamadi')));
      h.appendChild(dugme('dg', t('yuz.tekrar-dene'), tazele));
      kutu.appendChild(h);
      return;
    }
    var kisiler = q.people || [];
    var p = kisiler.filter(function (k) { return k.name === (v.status && v.status.sahip_kaydi); })[0] || kisiler[0];
    if (!p) { hudDeger.remove(); kutu.appendChild(el('small', null, t('yuz.kalite.kayit-yok'))); return; }
    if (kisiler.length > 1) hudAd.appendChild(el('b', null, ' · ' + p.name));
    var esik = q.threshold, kesin = q.confident_threshold, aciklama;
    if (p.encodings < 2 || p.intra_max == null) {
      hudDeger.textContent = t('yuz.kalite.olculemez'); hudDeger.className = 'yk-hukum warn';
      aciklama = t('yuz.kalite.tek-ornek');
    } else {
      var lo = p.intra_min != null ? p.intra_min : p.intra_max;
      var iyi = p.intra_max <= esik;
      hudDeger.textContent = t(p.intra_max <= kesin ? 'yuz.kalite.cok-iyi' : iyi ? 'yuz.kalite.iyi' : 'yuz.kalite.tutarsiz');
      hudDeger.className = 'yk-hukum ' + (iyi ? 'ok' : 'err');
      aciklama = t(iyi ? 'yuz.kalite.aciklama-iyi' : 'yuz.kalite.aciklama-kotu',
                   { lo: sayi(lo), hi: sayi(p.intra_max), esik: sayi(esik) });
      var olcek = el('div', 'yk-olcek');
      olcek.setAttribute('role', 'img');
      olcek.setAttribute('aria-label', aciklama);
      olcek.appendChild(el('div', 'yol'));
      var ar = el('div', 'aralik');
      ar.style.left = yer(lo);
      ar.style.width = 'max(6px, calc(' + yer(p.intra_max) + ' - ' + yer(lo) + '))';
      if (p.intra_max > OLCEK) ar.classList.add('tasiyor');
      olcek.appendChild(ar);
      olcek.appendChild(el('span', 'uc', sayi(0)));
      olcek.appendChild(el('span', 'uc sag', (p.intra_max > OLCEK ? '≥ ' : '') + sayi(OLCEK)));
      [[kesin, 'yuz.kalite.kesin', 'sol'], [esik, 'yuz.kalite.sinir', '']].forEach(function (c) {
        var cz = el('div', 'cizgi ' + c[2]);
        cz.style.left = yer(c[0]);
        cz.appendChild(el('i', null, t(c[1], { n: sayi(c[0]) })));
        olcek.appendChild(cz);
      });
      kutu.appendChild(olcek);
      kutu.appendChild(el('span', 'yk-olcek-not', t('yuz.kalite.olcek-not')));
    }
    kutu.appendChild(el('small', null, aciklama));
    if (p.nearest_other != null && p.nearest_other < esik) {
      kutu.appendChild(el('small', 'yk-uyari', t('yuz.kalite.ikiz', { ad: p.nearest_other_name, d: sayi(p.nearest_other) })));
    }
    /* Yalnız gösterilen kişinin aykırıları: başkasınınki buraya düşünce onunmuş gibi okunuyordu */
    var aykiri = (q.outliers || []).filter(function (o) { return o.name === p.name; });
    if (aykiri.length) {
      var a = el('div', 'yk-aykiri');
      a.appendChild(el('small', null, tc('yuz.kalite.aykiri', aykiri.length)));
      aykiri.forEach(function (o) { a.appendChild(aykiriSatir(o)); });
      kutu.appendChild(a);
    }
  }

  // Aykırı örnek — satır içi iki adımlı silme (confirm() yok: Electron'da pencereyi kilitler)
  function aykiriSatir(o) {
    var s = el('div', 'yk-aykiri-satir');
    var ciz = function (durum, hata) {
      temizle(s);
      s.appendChild(el('span', null, t('yuz.kalite.aykiri-satir', { ad: o.name, id: o.id, d: sayi(o.nearest_own) })));
      if (durum === 'sor') {
        var k = el('span', 'yk-onay');
        k.appendChild(el('span', null, t('yuz.kalite.aykiri-sor')));
        var kd = el('span', 'yk-onay-dugme');
        kd.appendChild(dugme('dg dg-yikici', t('yuz.sil'), sil));
        kd.appendChild(dugme('dg', t('yuz.vazgec'), function () { ciz(); }));
        k.appendChild(kd);
        s.appendChild(k);
      } else if (durum === 'siliniyor') {
        s.appendChild(el('span', 'yk-onay', t('yuz.siliniyor')));
      } else {
        if (hata) s.appendChild(el('span', 'yk-onay yk-hata', hata));
        s.appendChild(dugme('dg', t('yuz.sil'), function () { ciz('sor'); }));
      }
    };
    var sil = async function () {
      ciz('siliniyor');
      try {
        var r = await af('/api/face/encoding/' + encodeURIComponent(o.id), { method: 'DELETE' });
        if (!r.ok) { ciz(null, await detay(r, t('yuz.silinemedi'))); return; }
        tazele();
      } catch (e) { ciz(null, t('yuz.silme-hatasi')); }
    };
    ciz();
    return s;
  }

  // ── tarama ────────────────────────────────────────────────────────────────
  async function taraIstek(sessiz) {
    var blob = await kareAl();
    var fd = new FormData();
    fd.append('file', blob, 'kare.jpg');
    // notify=false: canlı tarama / giriş denemesi her turda Yuki'yi konuşturmasın
    fd.append('notify', sessiz ? 'false' : 'true');
    try {
      var r = await af('/api/face/scan', { method: 'POST', body: fd });
      if (!r.ok) return { hata: await detay(r, t('yuz.tarama-basarisiz')) };
      return { veri: await r.json() };
    } catch (e) { return { hata: t('yuz.baglanti-hatasi') }; }
  }

  async function kimsin(sessiz) {
    if (!(await kamerayiAc())) return;
    var s = await taraIstek(sessiz);
    if (!ui.sonuc) return;
    if (!s.veri) { if (!sessiz) ui.sonuc.textContent = s.hata; return; }
    var d = s.veri;
    ui.sonuc.textContent = d.known
      ? t('yuz.guven', { ad: d.name, n: Math.round((d.confidence || 0) * 100) }) + (d.verdict === 'uncertain' ? t('yuz.kararsiz') : '')
      : t(d.faces_detected === 0 ? 'yuz.giris.yuz-yok' : 'yuz.taninmadi');
  }

  // ── kayıt + 5 pozlu sihirbaz ──────────────────────────────────────────────
  var POZLAR = ['yuz.poz.duz', 'yuz.poz.sag', 'yuz.poz.sol', 'yuz.poz.yukari', 'yuz.poz.asagi'];

  async function kareyiKaydet(ad) {
    var fd = new FormData();
    fd.append('name', ad);
    fd.append('file', await kareAl(), 'kare.jpg');
    try {
      var r = await af('/api/face/register', { method: 'POST', body: fd });
      if (!r.ok) return { hata: await detay(r, t('yuz.kayit-basarisiz')) };
      return { veri: await r.json() };
    } catch (e) { return { hata: t('yuz.kayit-baglanti-hatasi') }; }
  }

  async function tekKareKaydet() {
    var ad = (ui.ad.value || '').trim();
    if (!ad) { ui.kayitSonuc.textContent = t('yuz.isim-gir'); ui.ad.focus(); return; }
    if (!(await kamerayiAc())) return;
    var s = await kareyiKaydet(ad);
    if (!s.veri) { ui.kayitSonuc.textContent = s.hata; return; }
    var m = t('yuz.kaydedildi', { ad: s.veri.name || ad, n: s.veri.total_encodings });
    if (s.veri.warnings && s.veri.warnings.length) m += ' ⚠ ' + s.veri.warnings.join(' ');
    ui.kayitSonuc.textContent = m;
    tazele();
  }

  async function sihirbaziBaslat(ad) {
    ad = (ad || (ui.ad && ui.ad.value) || '').trim();
    if (!ad) { ui.kayitSonuc.textContent = t('yuz.isim-gir'); ui.ad.focus(); return; }
    if (!(await kamerayiAc())) return;
    if (canliTimer) { clearInterval(canliTimer); canliTimer = null; }
    sihirbaz = { ad: ad, adim: 0, mesaj: '' };
    kameraUi();
    if (ui.kamera.scrollIntoView) ui.kamera.scrollIntoView({ block: 'nearest', behavior: 'smooth' });
  }

  function sihirbazCiz() {
    if (!ui.sihirbaz) return;
    temizle(ui.sihirbaz);
    ui.sihirbaz.hidden = !sihirbaz;
    if (!sihirbaz) return;
    var sb = sihirbaz;
    var bas = el('div', 'yk-sihirbaz-bas');
    bas.appendChild(el('b', null, t('yuz.poz.baslik', { ad: sb.ad })));
    bas.appendChild(el('span', 'yk-hud-deger', t('yuz.poz.adim', { i: Math.min(sb.adim + 1, 5), n: 5 })));
    ui.sihirbaz.appendChild(bas);
    var noktalar = el('div', 'yk-noktalar');
    POZLAR.forEach(function (_, i) { noktalar.appendChild(el('i', i < sb.adim ? 'dolu' : i === sb.adim ? 'simdi' : '')); });
    ui.sihirbaz.appendChild(noktalar);
    ui.sihirbaz.appendChild(el('p', null, sb.adim < 5 ? t(POZLAR[sb.adim]) : t('yuz.poz.bitti', { ad: sb.ad })));
    if (sb.mesaj) ui.sihirbaz.appendChild(el('small', 'yk-uyari', sb.mesaj));
    var d = el('div', 'yk-dugmeler');
    if (sb.adim < 5) {
      var cek = dugme('dg dg-birincil', t('yuz.poz.cek'), async function () {
        cek.disabled = true;
        var s = await kareyiKaydet(sb.ad);
        if (sihirbaz !== sb) return;                 // bu arada kapandı
        if (s.veri) { sb.adim++; sb.mesaj = (s.veri.warnings || []).join(' '); }
        else sb.mesaj = s.hata;
        if (sb.adim >= 5) tazele();
        sihirbazCiz();
      });
      d.appendChild(cek);
      d.appendChild(dugme('dg', t('yuz.vazgec'), function () { sihirbaz = null; sihirbazCiz(); if (sb.adim) tazele(); }));
    } else {
      d.appendChild(dugme('dg dg-ikincil', t('yuz.tamam'), function () { sihirbaz = null; sihirbazCiz(); }));
    }
    ui.sihirbaz.appendChild(d);
  }

  // ── kişiler ───────────────────────────────────────────────────────────────
  function listeCiz() {
    var kutu = ui.liste;
    temizle(kutu);
    if (v.liste == null) {
      ui.kisiSayi.textContent = '';
      var b = el('div', 'yk-bos');
      b.appendChild(el('span', 'yk-hata', t('yuz.liste-alinamadi')));
      b.appendChild(dugme('dg', t('yuz.tekrar-dene'), tazele));
      kutu.appendChild(b);
      return;
    }
    var sahipAd = v.status && v.status.sahip_kaydi;
    var kisiler = v.liste.slice().sort(function (a, b2) { return (b2.name === sahipAd) - (a.name === sahipAd); });
    ui.kisiSayi.textContent = String(kisiler.length);
    if (!kisiler.length) { kutu.appendChild(el('div', 'yk-bos', t('yuz.kisi-yok'))); return; }
    kisiler.forEach(function (k) { kutu.appendChild(kisiSatiri(k, k.name === sahipAd)); });
  }

  /* Sil: 1. dokunuş "emin misin", 2. dokunuş istek; sahipse sunucu 409 der →
     3. dokunuş `?sahip=1` (silinirse yüzle giriş kapanır). */
  function kisiSatiri(k, sahip) {
    var satir = el('div', 'yk-kisi');
    satir.appendChild(el('div', 'yk-kisi-bas', basHarf(k.name)));
    var p = el('p');
    p.appendChild(document.createTextNode(k.name));
    if (sahip) p.appendChild(el('span', 'yk-sahip', t('yuz.sahip')));
    p.appendChild(el('small', null, tc('yuz.ornek-sayisi', k.encodings)));
    satir.appendChild(p);
    var sil = dugme('dg', t('yuz.sil'));
    var sifirla = function () { sil.dataset.onay = ''; sil.dataset.sahip = ''; sil.textContent = t('yuz.sil'); sil.className = 'dg'; };
    sil.onclick = async function () {
      if (sil.dataset.onay !== '1') {
        sil.dataset.onay = '1';
        sil.textContent = t(sahip ? 'yuz.sahip-sil-onay' : 'yuz.emin-misiniz');
        sil.className = 'dg dg-yikici';
        if (sahip) sil.dataset.sahip = '1';
        setTimeout(function () { if (sil.dataset.onay === '1') sifirla(); }, 5000);
        return;
      }
      sil.disabled = true;
      try {
        var sahipOnay = sil.dataset.sahip === '1';
        var r = await af('/api/face/' + encodeURIComponent(k.name) + (sahipOnay ? '?sahip=1' : ''), { method: 'DELETE' });
        sil.disabled = false;
        if (r.status === 409 && !sahipOnay) {
          sil.dataset.sahip = '1';
          sil.textContent = t('yuz.sahip-sil-onay');
          return;
        }
        if (r.ok) { bildir(t('yuz.silindi', { ad: k.name }), 'basari'); tazele(); }
        else { bildir(await detay(r, t('yuz.silinemedi')), 'uyari'); sifirla(); }
      } catch (e) { sil.disabled = false; bildir(t('yuz.silme-hatasi'), 'uyari'); sifirla(); }
    };
    satir.appendChild(sil);
    return satir;
  }

  // ── ana ekran ─────────────────────────────────────────────────────────────
  function hud(ad, degerSinif) {
    var h = el('div', 'yk-hud');
    h.appendChild(el('span', null, ad));
    var d = el('span', 'yk-hud-deger' + (degerSinif ? ' ' + degerSinif : ''));
    h.appendChild(d);
    return [h, d];
  }

  function calisirEkran(kok) {
    ui = {};
    // KİMLİK KARTI
    var kart = el('div', 'yk-kart');
    var kim = el('div', 'yk-kimlik');
    ui.avatar = el('div', 'yk-avatar soluk', '?');
    kim.appendChild(ui.avatar);
    var km = el('div', 'yk-kimlik-metin');
    var bas = el('div', 'yk-durum');
    ui.isik = el('i', 'yk-isik');
    ui.baslik = el('b', null, t('yuz.yukleniyor'));
    bas.appendChild(ui.isik); bas.appendChild(ui.baslik);
    km.appendChild(bas);
    ui.alt = el('div', 'yk-durum-alt');
    km.appendChild(ui.alt);
    kim.appendChild(km);
    kart.appendChild(kim);
    ui.kalite = el('div', 'yk-kalite');
    kart.appendChild(ui.kalite);
    var ek = el('div', 'yk-eylem-kutu');
    ui.eylem = el('div', 'yk-eylem');
    ek.appendChild(ui.eylem);
    ui.mesaj = el('p', 'yk-mesaj');
    ui.mesaj.setAttribute('aria-live', 'polite');
    ek.appendChild(ui.mesaj);
    kart.appendChild(ek);
    ui.kart = kart;
    kok.appendChild(kart);

    var alt = el('div', 'yk-alt');
    // KAMERA
    var kam = el('section', 'yk-kamera');
    var kh = hud(t('yuz.kamera'));
    ui.kamDurum = kh[1];
    kam.appendChild(kh[0]);
    var kutu = el('div', 'yk-video');
    video = document.createElement('video');
    video.autoplay = true; video.muted = true; video.playsInline = true;
    kutu.appendChild(video);
    ui.perde = el('div', 'yk-perde');
    ui.perde.appendChild(el('i', 'yk-oval'));
    ui.perde.appendChild(el('b', null, t('yuz.kamera-kapali-kisa')));
    ui.perde.appendChild(el('small', null, t('yuz.kamera-kapali-not')));
    kutu.appendChild(ui.perde);
    kam.appendChild(kutu);
    ui.sihirbaz = el('div', 'yk-sihirbaz');
    ui.sihirbaz.hidden = true;
    kam.appendChild(ui.sihirbaz);
    ui.sonuc = el('p', 'yk-sonuc');
    ui.sonuc.setAttribute('aria-live', 'polite');
    kam.appendChild(ui.sonuc);
    var d = el('div', 'yk-dugmeler');
    ui.btnKamera = dugme('dg dg-birincil', t('yuz.kamerayi-ac'), function () {
      if (akis) { kamerayiKapat(); ui.sonuc.textContent = ''; } else kamerayiAc();
    });
    d.appendChild(ui.btnKamera);
    d.appendChild(dugme('dg', t('yuz.tani'), function () { kimsin(false); }));
    ui.btnCanli = dugme('dg', t('yuz.canli-tanima'), async function () {
      if (canliTimer) { clearInterval(canliTimer); canliTimer = null; kameraUi(); return; }
      if (!(await kamerayiAc())) return;
      // 2,5 sn: kişiselde ölçülen aralık. Daha sık taramak modeli kuyruğa sokar.
      canliTimer = setInterval(function () { kimsin(true); }, 2500);
      kameraUi();
    });
    d.appendChild(ui.btnCanli);
    kam.appendChild(d);
    ui.kamera = kam;
    alt.appendChild(kam);

    // KİŞİLER
    var ks = el('section', 'yk-kisiler');
    var sh = hud(t('yuz.kisiler'));
    ui.kisiSayi = sh[1];
    ks.appendChild(sh[0]);
    ui.liste = el('div', 'yk-liste');
    ui.liste.id = 'faces-list';
    ks.appendChild(ui.liste);
    var form = el('div', 'yk-tanit');
    form.appendChild(el('b', null, t('yuz.tanit.bas')));
    ui.ad = document.createElement('input');
    ui.ad.type = 'text'; ui.ad.className = 'girdi'; ui.ad.maxLength = 60;
    ui.ad.placeholder = t('yuz.isim');
    ui.ad.setAttribute('aria-label', t('yuz.isim'));
    form.appendChild(ui.ad);
    var fd = el('div', 'yk-dugmeler');
    fd.appendChild(dugme('dg dg-ikincil', t('yuz.tanit.bes-poz'), function () { sihirbaziBaslat(); }));
    fd.appendChild(dugme('dg', t('yuz.kareyi-kaydet'), tekKareKaydet));
    form.appendChild(fd);
    ui.kayitSonuc = el('p', 'yk-sonuc');
    ui.kayitSonuc.setAttribute('aria-live', 'polite');
    form.appendChild(ui.kayitSonuc);
    form.appendChild(el('small', null, t('yuz.tanit.ipucu')));
    ks.appendChild(form);
    alt.appendChild(ks);
    kok.appendChild(alt);

    kameraUi();
    kaliteCiz();
    tazele();
  }

  // ── kurulum ───────────────────────────────────────────────────────────────
  /* Her çağrıda baştan çizer: 09-27'ye kadar `kuruldu` bayrağı ikinci açılışı
     erken döndürüyordu → silinen/eklenen kişi listede görünmüyordu. Çizim ucuz. */
  async function kur() {
    var kok = kokAl();
    if (!kok) return;
    kamerayiKapat();
    ui = {};
    temizle(kok);
    kok.appendChild(el('p', 'alan-ipucu', t('yuz.yukleniyor')));

    /* ⚠️ Üç durum (2026-09-08): "kurulu" · "kurulu değil" · **"bilinmiyor"** (yetki reddi).
       Eskiden 401'de doğrudan indirme ekranı açılıyordu → kurulu kütüphane için "indir". */
    var yetenek = { available: false, unavailable_reason: null, bilinmiyor: false };
    try {
      var r = await af('/api/pydeps/status');
      if (r.ok) {
        var veri = await r.json();
        var c = (veri && veri.capabilities && veri.capabilities.face_recognition) || {};
        yetenek.available = !!c.available;
        yetenek.unavailable_reason = c.unavailable_reason || null;
      } else if (r.status === 401 || r.status === 403) {
        yetenek.bilinmiyor = true;
      }
    } catch (e) { /* ağ hatası → indirme ekranı; sessizce "çalışıyor" deme */ }

    temizle(kok);
    if (yetenek.bilinmiyor) kok.appendChild(el('p', 'alan-ipucu', t('yuz.oturum-kilitli')));
    else if (yetenek.available) calisirEkran(kok);
    else indirmeEkrani(kok, yetenek.unavailable_reason);
  }

  function gorunur() {
    var kok = kokAl();
    return !!(kok && kok.isConnected && kok.offsetParent !== null);
  }

  document.addEventListener('tabchange', function (e) {
    var tab = e && e.detail && e.detail.tab;
    if (tab === 'faces') kur();
    else kamerayiKapat();
  });
  // Pencere gizlenince / sayfadan çıkınca kamera bırakılır (ışık yanık kalmasın)
  document.addEventListener('visibilitychange', function () { if (document.hidden) kamerayiKapat(); });
  window.addEventListener('pagehide', kamerayiKapat);

  /* Dil değişince paneli KENDİ tazeler. Sıra: kamerayı ÖNCE kapat (kur bunu yapar),
     sonra çiz — ters sırada DOM'dan kopan <video>'nun akışı açık kalırdı.
     Görünmüyorsa çizmez: odaya dönüşte `hqSelectCat` zaten `kur()`'u çağırır. */
  window.addEventListener('yuki-dil-degisti', function () { if (gorunur()) kur(); });

  window.YuzSekmesi = { kur: kur, kapat: kamerayiKapat, listeyiTazele: tazele };
})();
