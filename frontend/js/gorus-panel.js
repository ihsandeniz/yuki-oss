/* Kamera görüşü + ses kimliği — ayar paneli ve RIZA EKRANI.
   İkisi de varsayılan KAPALI. Kurulum bayrağı (GORUS / SES_KIMLIK) kapalıysa sunucu 404 döner ve
   o kart hiç çizilmez. Bayrak açıksa kart görünür; "Aç" önce rıza ekranını gösterir. Rıza ekranı
   kutu işaretlenmeden onay vermez; onay sunucuya metnin SÜRÜMÜYLE gider (metin değişirse sunucu
   eski onayı kabul etmez). "Rızayı geri çek" kamerayı kapatır / ses izini siler.
   Bağlanma: sayfada `[data-gorus-panel]` öğesi varsa ona kendiliğinden kurulur; elle
   YukiGorusPanel.kur(kapsayici). Bağımlılık: gorus.js, ses-kimlik.js, css/gorus.css.
   🔴 RIZA_METNI değişirse backend/app/services/biyometrik_riza.py SURUM'u da artır. */
(function () {
  'use strict';

  var RIZA_METNI = {
    gorus: {
      surum: 1,
      baslik: 'Kamera görüşünü açmadan önce',
      maddeler: [
        'Açınca Yuki bu bilgisayarın kamerasını kullanır ve saniyede en çok bir kare alır.',
        'Kareler yalnız bu bilgisayarda, bellekte işlenir. Diske ya da günlüğe yazılmaz, internete ve buluta gönderilmez.',
        'Yaptıkları: masada biri var mı diye yüz sayar; yüzle girişte kayıtlı biri geri dönünce selam verir; 50 dakika kesintisiz oturunca mola hatırlatır; "Yuki bak" deyince tek kareyi bu bilgisayardaki görsel modele sorar.',
        'Selam ve mola cümlesi Yuki\'nin seçili ses motoruyla okunur. Bulut ses seçiliyse oraya yalnız cümlenin metni gider (adın dahil), görüntü gitmez.',
        'Yalnız bu bilgisayardan açılır. İstediğin an durdurabilir ya da rızanı geri çekebilirsin.',
      ],
      kutu: 'Okudum; kameranın bu koşullarla kullanılmasına izin veriyorum.',
    },
    ses_kimlik: {
      surum: 1,
      baslik: 'Ses kimliğini açmadan önce',
      maddeler: [
        'Birkaç kısa cümle okursun. Bu kayıtlardan sesine özgü bir "ses izi" (192 sayılık bir özet) çıkarılır.',
        'Kayıt sesleri saklanmaz. Yalnız ses izi bu bilgisayarda tutulur; internete ve buluta gönderilmez.',
        'Ses izi biyometrik veridir. Rızanı geri çektiğinde ses izi silinir.',
        'İşi televizyonu, odadaki başka birini ya da Yuki\'nin kendi sesini süzmek. Bir güvenlik kilidi değildir: kayıttan çalınan sesin geçebilir.',
      ],
      kutu: 'Okudum; ses izimin bu koşullarla çıkarılıp bu bilgisayarda saklanmasına izin veriyorum.',
    },
  };

  var NEDEN = {
    riza: 'Rıza geri çekildiği için kamera kapandı.', kapali: 'Kamera görüşü bu kurulumda kapalı.',
    yerel: 'Kamera görüşü yalnız bu bilgisayardan açılabilir.', yetki: 'Erişim anahtarı geçersiz.',
    koken: 'Bu sayfa kameraya bağlanamıyor (köken izni yok).', gizli: 'Sekme gizli kaldığı için kamera kapandı.',
    'izin-yok': 'Tarayıcı kamera izni vermedi.', 'kamera-yok': 'Bu cihazda kamera bulunamadı.',
    'kamera-acilamadi': 'Kamera açılamadı; başka bir uygulama kullanıyor olabilir.', kullanici: '',
  };

  function token() {
    try { return sessionStorage.getItem('aliceToken') || localStorage.getItem('aliceToken') || ''; }
    catch (_) { return ''; }
  }
  function istek(yol, ayar) {
    ayar = ayar || {};
    var h = ayar.headers || {};
    var t = token(); if (t) h.Authorization = 'Bearer ' + t;
    ayar.headers = h;
    return fetch(yol, ayar).then(function (r) {
      return r.json().catch(function () { return {}; }).then(function (g) { return { ok: r.ok, kod: r.status, veri: g }; });
    }, function () { return { ok: false, kod: 0, veri: { detail: 'Sunucuya ulaşılamadı.' } }; });
  }
  function json(yol, metot, govde) {
    return istek(yol, { method: metot, headers: { 'Content-Type': 'application/json' }, body: govde ? JSON.stringify(govde) : undefined });
  }
  function hataMetni(c) { var d = c.veri && c.veri.detail; return typeof d === 'string' ? d : 'İşlem tamamlanamadı (' + c.kod + ').'; }

  function el(etiket, sinif, metin) {
    var e = document.createElement(etiket);
    if (sinif) e.className = sinif;
    if (metin != null) e.textContent = metin;
    return e;
  }
  function dugme(metin, tur, fn) {
    var b = el('button', 'gp-dugme' + (tur ? ' gp-dugme--' + tur : ''), metin);
    b.type = 'button'; b.addEventListener('click', fn); return b;
  }

  // ── rıza ekranı ──────────────────────────────────────────────────────────
  function rizaSor(ozellik) {
    var m = RIZA_METNI[ozellik];
    return new Promise(function (coz) {
      var onceki = document.activeElement;
      var perde = el('div', 'gp-perde');
      var kutu = el('div', 'gp-riza');
      kutu.setAttribute('role', 'dialog'); kutu.setAttribute('aria-modal', 'true');
      kutu.setAttribute('aria-labelledby', 'gp-riza-baslik');
      kutu.dataset.ozellik = ozellik;
      var h = el('h2', 'gp-riza__baslik', m.baslik); h.id = 'gp-riza-baslik';
      var ul = el('ul', 'gp-riza__maddeler');
      m.maddeler.forEach(function (t) { ul.appendChild(el('li', null, t)); });
      var etiket = el('label', 'gp-riza__onay');
      var cb = el('input'); cb.type = 'checkbox'; cb.className = 'gp-riza__kutu';
      etiket.appendChild(cb); etiket.appendChild(el('span', null, m.kutu));
      var alt = el('div', 'gp-riza__alt');
      var vazgec = dugme('Vazgeç', 'ikincil', function () { bitir(false); });
      var onay = dugme('İzin ver ve aç', 'birincil', function () { if (cb.checked) bitir(true); });
      onay.disabled = true; onay.className += ' gp-riza__onayla';
      cb.addEventListener('change', function () { onay.disabled = !cb.checked; });
      alt.appendChild(vazgec); alt.appendChild(onay);
      kutu.appendChild(h); kutu.appendChild(ul); kutu.appendChild(etiket); kutu.appendChild(alt);
      perde.appendChild(kutu);
      function tus(e) {
        if (e.key === 'Escape') { e.preventDefault(); bitir(false); }
        else if (e.key === 'Tab') {
          var odak = [cb, vazgec].concat(onay.disabled ? [] : [onay]);
          var i = odak.indexOf(document.activeElement);
          var j = e.shiftKey ? (i <= 0 ? odak.length - 1 : i - 1) : (i === odak.length - 1 ? 0 : i + 1);
          e.preventDefault(); odak[j].focus();
        }
      }
      function bitir(sonuc) {
        document.removeEventListener('keydown', tus, true);
        perde.remove();
        if (onceki && onceki.focus) try { onceki.focus(); } catch (_) { /* */ }
        coz(sonuc ? m.surum : null);
      }
      perde.addEventListener('click', function (e) { if (e.target === perde) bitir(false); });
      document.addEventListener('keydown', tus, true);
      document.body.appendChild(perde);
      cb.focus();
    });
  }

  // ── kart iskeleti ────────────────────────────────────────────────────────
  function kart(baslik, aciklama) {
    var k = el('section', 'gp-kart');
    var ust = el('div', 'gp-kart__ust');
    var b = el('h3', 'gp-kart__baslik', baslik);
    var rozet = el('span', 'gp-rozet', 'Kapalı');
    ust.appendChild(b); ust.appendChild(rozet);
    var acik = el('p', 'gp-kart__aciklama', aciklama);
    var durum = el('p', 'gp-kart__durum'); durum.setAttribute('role', 'status'); durum.setAttribute('aria-live', 'polite');
    var hata = el('p', 'gp-kart__hata'); hata.setAttribute('role', 'alert'); hata.hidden = true;
    var eylem = el('div', 'gp-kart__eylem');
    k.appendChild(ust); k.appendChild(acik); k.appendChild(durum); k.appendChild(hata); k.appendChild(eylem);
    return {
      kok: k, eylem: eylem,
      rozet: function (metin, tur) { rozet.textContent = metin; rozet.className = 'gp-rozet' + (tur ? ' gp-rozet--' + tur : ''); },
      durum: function (metin) { durum.textContent = metin || ''; durum.hidden = !metin; },
      hata: function (metin, ayrinti) {
        hata.textContent = metin || '';
        (ayrinti || []).forEach(function (a) {
          var satir = el('span', 'gp-kart__hata-satir');
          satir.appendChild(document.createTextNode(a[0] + ' '));
          satir.appendChild(el('code', 'gp-kart__yol', a[1]));
          hata.appendChild(satir);
        });
        hata.hidden = !metin;
      },
    };
  }

  // ── kamera görüşü kartı ──────────────────────────────────────────────────
  function gorusKarti(ilk) {
    var K = kart('Kamera görüşü', 'Yuki kameradan masada olup olmadığını anlar, dönünce selam verir, uzun oturunca mola hatırlatır. "Yuki bak" dersen gördüğünü anlatır.');
    var d = ilk, istemci = null, cevap = el('p', 'gp-kart__cevap'); cevap.hidden = true;

    function istemciAl() {
      if (!istemci && window.YukiGorusApi) {
        istemci = window.YukiGorusApi.GorusOlustur({ dinle: function (m) {
          if (m.tip === 'durum-degisti') { if (m.durum === 'kapali' && m.neden && NEDEN[m.neden]) K.hata(NEDEN[m.neden]); tazele(); }
          else if (m.tip === 'durum') K.durum(m.yuz > 0 ? 'Seni görüyorum.' : 'Masada kimseyi görmüyorum.');
        } });
      }
      return istemci;
    }
    function kameraAcik() { return !!(istemci && istemci.durum().durum !== 'kapali'); }

    function ciz() {
      K.eylem.textContent = '';
      var riza = d.riza && d.riza.verildi;
      var model = d.model || {};
      if (!riza) {
        K.rozet('Kapalı');
        K.durum('Açmak için önce rıza ekranını onaylaman gerekir.');
        K.eylem.appendChild(dugme('Aç', 'birincil gp-ac', ac));
        return;
      }
      if (kameraAcik()) {
        K.rozet('Kamera açık', 'canli');
        K.durum('Kamera açık: saniyede en çok bir kare, yalnız bu bilgisayarda işleniyor.');
        K.eylem.appendChild(dugme('Yuki bak', 'birincil gp-bak', bak));
        K.eylem.appendChild(dugme('Kamerayı durdur', 'ikincil', function () { istemci.durdur(); K.durum(''); tazele(); }));
      } else {
        K.rozet('Rıza verildi', 'tamam');
        K.durum('Kamera kapalı.');
        K.eylem.appendChild(dugme('Kamerayı başlat', 'birincil gp-baslat', baslat));
      }
      K.eylem.appendChild(dugme('Rızayı geri çek', 'tehlike gp-geri', geriCek));
      if (!model.hazir) K.hata('"Yuki bak" için yerel görsel model gerekli: ' + (model.neden || 'bulunamadı') + '.');
      K.eylem.appendChild(cevap);
    }
    function tazele() {
      return json('/api/gorus/durum', 'GET').then(function (c) { if (c.ok) { d = c.veri; ciz(); } });
    }
    function ac() {
      K.hata('');
      rizaSor('gorus').then(function (surum) {
        if (surum == null) return;
        json('/api/gorus/riza', 'POST', { kabul: true, surum: surum }).then(function (c) {
          if (!c.ok) { K.hata(hataMetni(c)); return; }
          d.riza = c.veri.riza; ciz(); baslat();
        });
      });
    }
    function baslat() {
      K.hata('');
      var i = istemciAl();
      if (!i) { K.hata('Kamera bileşeni yüklenemedi.'); return; }
      i.baslat().then(ciz, function () { ciz(); K.hata(NEDEN[i.durum().neden] || 'Kamera açılamadı.'); });
    }
    function bak() {
      cevap.hidden = false; cevap.textContent = 'Bakıyorum…';
      json('/api/gorus/bak', 'POST', { soru: '' }).then(function (c) {
        cevap.textContent = c.ok ? c.veri.metin : hataMetni(c);
        cevap.classList.toggle('gp-kart__cevap--hata', !(c.ok && c.veri.ok));
      });
    }
    function geriCek() {
      if (istemci) istemci.durdur();
      json('/api/gorus/riza', 'DELETE').then(function (c) {
        if (!c.ok) { K.hata(hataMetni(c)); return; }
        d.riza = c.veri.riza; K.hata(''); cevap.hidden = true; ciz();
      });
    }
    ciz();
    return K.kok;
  }

  // ── ses kimliği kartı ────────────────────────────────────────────────────
  function sesKarti(ilk) {
    var K = kart('Ses kimliği', 'Yuki sesli komutlarda yalnız senin sesini dinler; televizyonu ve odadaki başkalarını süzer.');
    var d = ilk, mesgul = false;
    var sahne = el('div', 'gp-sahne'); sahne.hidden = true;

    function ciz() {
      K.eylem.textContent = '';
      var riza = d.riza && d.riza.verildi, kayit = d.kayit && d.kayit.var, model = d.model || {};
      if (!riza) {
        K.rozet('Kapalı');
        K.durum('Açmak için önce rıza ekranını onaylaman gerekir.');
        K.eylem.appendChild(dugme('Aç', 'birincil gp-ac', ac));
        return;
      }
      K.rozet(kayit ? 'Etkin' : 'Kayıt bekliyor', kayit ? 'canli' : 'tamam');
      K.durum(kayit ? 'Sesin kayıtlı (' + (d.kayit.konusma_sn || 0) + ' sn konuşma).' : 'Sesini tanıtmak için birkaç cümle oku.');
      if (!model.var) K.hata('Ses kimliği modeli bu bilgisayarda yok. Modeli indirip aşağıdaki yola koy.',
        [['Yol:', model.yol], ['Kaynak:', model.indir]]);
      else K.hata('');
      var kaydetD = dugme(kayit ? 'Yeniden kaydet' : 'Sesimi kaydet', 'birincil gp-kaydet', kaydet);
      kaydetD.disabled = mesgul || !model.var;
      K.eylem.appendChild(kaydetD);
      if (kayit) {
        var dene = dugme('Dene', 'ikincil', denemeYap); dene.disabled = mesgul; K.eylem.appendChild(dene);
        K.eylem.appendChild(dugme('Kaydı sil', 'ikincil', function () {
          json('/api/ses-kimlik/kayit', 'DELETE').then(function (c) { if (c.ok) { d = c.veri; ciz(); } });
        }));
      }
      K.eylem.appendChild(dugme('Rızayı geri çek', 'tehlike gp-geri', function () {
        json('/api/ses-kimlik/riza', 'DELETE').then(function (c) { if (c.ok) { d = c.veri; sahne.hidden = true; ciz(); } else K.hata(hataMetni(c)); });
      }));
      K.eylem.appendChild(sahne);
    }
    function ac() {
      rizaSor('ses_kimlik').then(function (surum) {
        if (surum == null) return;
        json('/api/ses-kimlik/riza', 'POST', { kabul: true, surum: surum }).then(function (c) {
          if (!c.ok) { K.hata(hataMetni(c)); return; }
          d = c.veri; ciz();
        });
      });
    }
    function kaydet() {
      var S = window.YukiSesKimlikApi;
      if (!S) { K.hata('Kayıt bileşeni yüklenemedi.'); return; }
      mesgul = true; ciz();
      var klipler = [];
      sahne.hidden = false;
      var i = 0;
      function sonraki() {
        if (i >= S.CUMLELER.length) return yukle();
        sahne.textContent = '';
        sahne.appendChild(el('p', 'gp-sahne__sira', 'Kayıt ' + (i + 1) + ' / ' + S.CUMLELER.length + ' — şu cümleyi sesli oku:'));
        sahne.appendChild(el('p', 'gp-sahne__cumle', '“' + S.CUMLELER[i] + '”'));
        return S.kaydet(S.KLIP_SN).then(function (b) { klipler.push(b); i++; return sonraki(); });
      }
      function yukle() {
        sahne.textContent = 'Ses izi çıkarılıyor…';
        var fd = new FormData();
        klipler.forEach(function (b, n) { fd.append('sesler', b, 'kayit' + n + '.webm'); });
        return istek('/api/ses-kimlik/kayit', { method: 'POST', body: fd }).then(function (c) {
          klipler = [];
          mesgul = false;
          if (!c.ok) { sahne.hidden = true; ciz(); K.hata(hataMetni(c)); return; }
          d = c.veri; sahne.hidden = true; ciz();
        });
      }
      sonraki().catch(function () { mesgul = false; sahne.hidden = true; ciz(); K.hata('Mikrofon açılamadı.'); });
    }
    function denemeYap() {
      var S = window.YukiSesKimlikApi; if (!S) return;
      mesgul = true; ciz(); sahne.hidden = false; sahne.textContent = 'Bir cümle söyle…';
      S.kaydet(3).then(function (b) {
        var fd = new FormData(); fd.append('ses', b, 'dene.webm');
        return istek('/api/ses-kimlik/dene', { method: 'POST', body: fd });
      }).then(function (c) {
        mesgul = false; ciz(); sahne.hidden = false;
        sahne.textContent = !c.ok ? hataMetni(c)
          : (c.veri.kabul ? 'Seni tanıdım (benzerlik ' + c.veri.skor + ').' : 'Bu sesi tanımadım (benzerlik ' + c.veri.skor + ', eşik ' + c.veri.esik + ').');
      }, function () { mesgul = false; sahne.hidden = true; ciz(); K.hata('Mikrofon açılamadı.'); });
    }
    ciz();
    return K.kok;
  }

  function kur(kapsayici) {
    if (!kapsayici || kapsayici.dataset.gpKurulu) return Promise.resolve(false);
    kapsayici.dataset.gpKurulu = '1';
    return Promise.all([json('/api/gorus/durum', 'GET'), json('/api/ses-kimlik/durum', 'GET')]).then(function (s) {
      kapsayici.textContent = '';
      // 404 = kurulum bayrağı kapalı → kart yok. Başka hata = kart yok (fail-closed).
      if (s[0].ok) kapsayici.appendChild(gorusKarti(s[0].veri));
      if (s[1].ok) kapsayici.appendChild(sesKarti(s[1].veri));
      kapsayici.classList.add('gp-panel');
      kapsayici.hidden = !(s[0].ok || s[1].ok);
      return s[0].ok || s[1].ok;
    });
  }

  window.YukiGorusPanel = { kur: kur, rizaSor: rizaSor, RIZA_METNI: RIZA_METNI };
  function otomatik() { var k = document.querySelector('[data-gorus-panel]'); if (k) kur(k); }
  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', otomatik);
  else otomatik();
})();
