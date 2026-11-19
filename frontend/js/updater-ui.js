// Sürüm & güncelleme paneli — ⚙ AYAR → LİSANS altındaki bölüm (`#hq-upd-*`).
// window.yukiUpdater yalnız Electron'da tanımlı (preload). Tarayıcı modunda
// bölüm yalnız sürümü (/health) gösterir; masaüstüne ait satırlar gizlenir.
// 2026-09-28 (HQ panel 9): satır düzeni (taslak B) — inline stil ve `color:#fff` kalktı,
// renk sonuç satırının `data-ton`'undan (hq-surum.css), düğmeler ortak `.dg` sınıfları.
(function () {
  'use strict';

  const $ = (id) => document.getElementById(id);

  // ── i18n sarmalayıcı ──────────────────────────────────────────────
  function _uut(anahtar, degerler) {
    return (window.YukiDil && window.YukiDil.t) ? window.YukiDil.t(anahtar, degerler) : String(anahtar);
  }

  // "Son denetim bugün 10:23" (taslak) — saniyeli ham toLocaleString ("28.09.2026 10:23:50") yerine
  // gün göreli + saat:dakika; daha eskiyse dilin kısa tarihi. Biçim dilin yerelinden.
  function fmtDate(ms) {
    const yer = (window.YukiDil && window.YukiDil.yerel) ? window.YukiDil.yerel() : undefined;
    try {
      const d = new Date(ms), simdi = new Date();
      const saat = d.toLocaleTimeString(yer, { hour: '2-digit', minute: '2-digit' });
      const gun = (x) => new Date(x.getFullYear(), x.getMonth(), x.getDate()).getTime();
      const fark = Math.round((gun(simdi) - gun(d)) / 864e5);
      if (fark === 0) return _uut('upd.bugun', { saat: saat });
      if (fark === 1) return _uut('upd.dun', { saat: saat });
      return d.toLocaleDateString(yer, { day: 'numeric', month: 'long' }) + ' ' + saat;
    } catch (_) { return '—'; }
  }
  // Son elle denetim "güncel" dediyse sürümün yanında rozet (taslak B) — ayrı yeşil satır yerine
  let _guncel = false;

  // ── Son sonucu yeniden çizebilmek ────────────────────────
  // Sonuç satırı bir kez yazılır; dil değişince METİN değil ÜRETİCİ tekrar
  // koşmalı, yoksa satır ilk dilde donar. `_son` = son sonucu çizen fonksiyon.
  // Kullanıcı bir akışı başlattıysa (indirme/kurulum) `null` — yeniden çizim
  // o akışın düğme durumunu sıfırlardı.
  let _son = null;
  function sonuc(ciz) { _son = ciz; ciz(); }

  // ton: bilgi · surec · ok · uyari · err → renk hq-surum.css'te (.upd-sonuc[data-ton])
  function setResult(text, ton) {
    const el = $('hq-upd-result');
    if (!el) return;
    el.textContent = text || '';
    el.dataset.ton = ton || 'bilgi';
  }

  async function refresh() {
    const verEl = $('hq-upd-version');
    const toggle = $('hq-upd-toggle');
    const btn = $('hq-upd-check');
    if (!verEl) return;

    if (!window.yukiUpdater) {
      // Tarayıcı: denetleme/kanal/anahtar masaüstüne ait → satırları gizle (devre dışı düğme
      // "neden basamıyorum" sorusu doğuruyordu), sürümü sunucudan oku, dürüst tek cümle.
      const bolum = $('hq-upd-bolum');
      if (bolum) bolum.classList.add('upd-web');
      if (toggle) toggle.disabled = true;
      if (btn) btn.disabled = true;
      let surum = (window.yukiApp && window.yukiApp.version) || '';
      if (!surum) {
        try { surum = ((await (await fetch('/health')).json()) || {}).version || ''; } catch (_) { surum = ''; }
      }
      verEl.innerHTML = '<b>' + esc(surum ? _uut('upd.yuki-surum', { surum: surum }) : 'Yuki') + '</b>';
      sonuc(() => setResult(_uut('upd.sadece-masaustu'), 'bilgi'));
      return;
    }
    try {
      const s = await window.yukiUpdater.status();
      // Delta güncelleme uygulanmışsa ÇALIŞAN sürüm paketlenmişten farklıdır.
      // İkisini de göster — "hangi sürümdeyim" sorusu tek bakışta cevaplanmalı,
      // yoksa destek istendiğinde yanlış sürüm bildirilir.
      let uygulanan = null;
      try {
        if (window.yukiUpdater.delta) uygulanan = (await window.yukiUpdater.delta.status()).applied;
      } catch (_) { /* delta yoksa sorun değil */ }

      const calisan = uygulanan ? uygulanan.version : s.currentVersion;
      verEl.innerHTML = '<b>' + esc(_uut('upd.yuki-surum', { surum: calisan })) + '</b>'
        + (uygulanan
            ? ' <span class="rozet">' + _uut('upd.paket-arti-guncelleme', { surum: esc(s.currentVersion) }) + '</span>'
            : '')
        + (_guncel ? ' <span class="rozet upd-guncel">' + _uut('upd.guncel') + '</span>' : '')
        + '<span class="upd-alt">' + (s.lastCheck ? _uut('upd.son-kontrol', { tarih: fmtDate(s.lastCheck) }) : _uut('upd.hic-denetlenmedi')) + '</span>';
      if (toggle) toggle.checked = !!s.enabled;
      const kanal = $('hq-upd-channel');
      if (kanal) kanal.value = s.channel || 'stable';
    } catch (e) {
      verEl.textContent = _uut('upd.bilgi-okunamadi');
    }
  }

  async function onToggle(e) {
    if (!window.yukiUpdater) return;
    const on = !!e.target.checked;
    try {
      await window.yukiUpdater.setEnabled(on);
      sonuc(() => setResult(on ? _uut('upd.acildi') : _uut('upd.kapandi'), 'bilgi'));
    } catch (_) {
      sonuc(() => setResult(_uut('upd.ayar-kaydedilemedi'), 'err'));
      e.target.checked = !on;
    }
  }

  async function onChannel(e) {
    if (!window.yukiUpdater || !window.yukiUpdater.setChannel) return;
    const yeni = e.target.value;
    try {
      await window.yukiUpdater.setChannel(yeni);
      sonuc(() => setResult(yeni === 'beta'
        ? _uut('upd.erken-kanal')
        : _uut('upd.kararli-kanal'), 'bilgi'));
    } catch (_) {
      sonuc(() => setResult(_uut('upd.kanal-kaydedilemedi'), 'err'));
      refresh();
    }
  }

  // Kullanıcı düğmeye bastı → ayar kapalı olsa da tek seferlik kontrol (kendi isteği).
  window.hqCheckUpdate = async function () {
    if (!window.yukiUpdater) return;
    const btn = $('hq-upd-check');
    if (btn) btn.disabled = true;
    sonuc(() => setResult(_uut('upd.kontrol-ediliyor'), 'surec'));
    try {
      const r = await window.yukiUpdater.check(true);
      _guncel = false;
      if (!r.ok) {
        sonuc(() => setResult(r.error || _uut('upd.kontrol-basarisiz'), 'err'));
      } else if (r.updateAvailable) {
        showAvailable(r);
      } else {
        // Sonuç sürümün yanındaki "güncel" rozetinde (finally'deki refresh çizer); satır boşalır
        _guncel = true;
        sonuc(() => setResult('', 'ok'));
      }
    } catch (e) {
      sonuc(() => setResult(_uut('upd.kontrol-hatasi', { hata: e.message || e }), 'err'));
    } finally {
      if (btn) btn.disabled = false;
      refresh();
    }
  };

  // Tam paketi indirmeye yönlendir — delta yolu yoksa ya da çekirdek
  // bileşenler değiştiyse (shell_id uyuşmazlığı) tek doğru yol bu.
  /**
   * Tam paket gerekiyor. 2026-08-08'e kadar buradan doğrudan tarayıcıya
   * gidiliyordu; artık ÖNCE uygulama içi kurulum denenir. Tarayıcı yalnız
   * gerçekten yapamadığımızda (izin yok / eski paket / desteklenmeyen platform)
   * son çare olarak kalır — ve o zaman sebebi de söylenir.
   */
  async function tamIndirmeyeYonlendir(el, surum, sebep) {
    _son = () => tamIndirmeyeYonlendir(el, surum, sebep);
    const tam = window.yukiUpdater && window.yukiUpdater.tam;
    let destek = null;
    if (tam) {
      try { destek = await tam.destekleniyor(); } catch (_) { destek = null; }
    }
    if (tam && destek && destek.ok) return tamUygulamaIcinde(el, surum, sebep, tam);

    el.dataset.ton = 'uyari';
    el.innerHTML = (sebep ? `<span class="upd-not">${esc(sebep)}</span>` : '')
      + (destek && destek.sebep
          ? '<span class="upd-not">' + _uut('upd.kurulamiyor', { sebep: esc(destek.sebep) }) + '</span>'
          : '')
      + _uut('upd.yeni-surum', { surum: esc(surum) }) + ' '
      + '<a href="#" id="hq-upd-open" class="upd-bag">' + _uut('upd.indirme-sayfasi') + '</a>';
    const link = $('hq-upd-open');
    if (link) {
      link.onclick = (ev) => { ev.preventDefault(); window.yukiUpdater.openReleasesPage(); };
    }
  }

  /** Uygulama içi tam güncelleme — indirme ve kurulum AYRI onay ister. */
  function tamUygulamaIcinde(el, surum, sebep, tam) {
    el.dataset.ton = 'uyari';
    el.innerHTML = (sebep ? `<span class="upd-not">${esc(sebep)}</span>` : '')
      + _uut('upd.yeni-surum', { surum: esc(surum) }) + ' — ' + _uut('upd.tam-paket-gerekli') + ' '
      + '<span class="upd-soluk">(' + _uut('upd.birkac-yuz-mb') + ')</span>'
      + '<span class="upd-eylem"><button type="button" id="hq-tam-indir" class="dg dg-ikincil">' + _uut('upd.tam-paketi-indir') + '</button>'
      + '<span id="hq-tam-durum" class="upd-durum"></span></span>';

    const btn = $('hq-tam-indir');
    const durum = $('hq-tam-durum');
    if (!btn) return;

    const bitir = tam.onProgress((p) => {
      if (p.asama !== 'indiriliyor' || !durum) return;
      const mb = (p.alinan / 1e6).toFixed(0);
      durum.textContent = p.toplam
        ? `%${Math.floor((p.alinan / p.toplam) * 100)} · ${mb} MB`
        : `${mb} MB`;
    });

    btn.onclick = async () => {
      _son = null;   // akış başladı — dil değişimi düğme durumunu sıfırlamasın
      btn.disabled = true;
      btn.textContent = _uut('upd.indiriliyor');
      try {
        const s = await tam.indir(surum);
        if (!s || !s.ok) {
          el.dataset.ton = 'err';
          // Sebebi GİZLEME: doğrulama düşmüş olabilir, kullanıcı bilmeli.
          durum.textContent = '';
          el.insertAdjacentHTML('beforeend', '<span class="upd-not">'
            + esc((s && s.error) || _uut('upd.indirilemedi')) + '</span>');
          return;
        }
        // İkinci onay: buradan sonrası uygulamayı kapatır.
        btn.disabled = false;
        btn.textContent = _uut('upd.kur-baslat');
        durum.textContent = _uut('upd.indirildi-dogrulandi', { mb: (s.boyut / 1e6).toFixed(0) });
        btn.onclick = async () => {
          btn.disabled = true;
          btn.textContent = _uut('upd.kuruluyor');
          durum.textContent = _uut('upd.yuki-kapanacak');
          const k = await tam.kurVeYenidenBaslat();
          if (!k || !k.ok) {
            btn.disabled = false;
            btn.textContent = _uut('upd.kur-baslat');
            durum.textContent = (k && k.error) || _uut('upd.kurulum-baslatilamadi');
          }
        };
      } catch (e) {
        el.dataset.ton = 'err';
        durum.textContent = _uut('upd.hata', { hata: e.message || e });
        btn.disabled = false;
        btn.textContent = _uut('upd.tam-paketi-indir');
      } finally {
        if (typeof bitir === 'function' && btn.textContent === _uut('upd.tam-paketi-indir')) bitir();
      }
    };
  }

  function esc(s) {
    return String(s).replace(/[&<>"']/g, (c) => (
      { '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));
  }

  async function showAvailable(r) {
    const el = $('hq-upd-result');
    if (!el) return;
    _son = () => showAvailable(r);
    const delta = window.yukiUpdater && window.yukiUpdater.delta;
    if (!delta) return tamIndirmeyeYonlendir(el, r.latestVersion);

    // Bu paket delta alabiliyor mu? (eski paketlerde shell-id yok)
    let durum = null;
    try { durum = await delta.status(); } catch (_) { /* yut, tam indirmeye düşeriz */ }
    if (!durum || !durum.supported) return tamIndirmeyeYonlendir(el, r.latestVersion);

    el.dataset.ton = 'uyari';
    el.innerHTML = _uut('upd.yeni-surum', { surum: esc(r.latestVersion) })
      + '<span class="upd-eylem"><button type="button" id="hq-upd-apply" class="dg dg-birincil">' + _uut('upd.simdi-guncelle') + '</button></span>'
      + '<span class="upd-soluk upd-not">' + _uut('upd.yalniz-degisen') + '</span>';

    const btn = $('hq-upd-apply');
    if (!btn) return;
    btn.onclick = async () => {
      _son = null;   // akış başladı — sonucu aşağıda yeniden kurar
      btn.disabled = true;
      btn.textContent = _uut('upd.indiriliyor');
      const bitir = delta.onProgress((p) => {
        if (p.asama === 'indiriliyor') btn.textContent = _uut('upd.indiriliyor');
        /* 'uygulanıyor' electron/delta-updater.js'in yolladığı AŞAMA DEĞERİ (veri,
           metin değil) — kuyruk2/updater-ui.json `istisna`. */
        else if (p.asama === 'uygulanıyor') btn.textContent = _uut('upd.uygulaniyor');
      });
      try {
        const s = await delta.apply(r.latestVersion);
        if (s && s.ok) {
          sonuc(() => {
            el.dataset.ton = 'ok';
            el.innerHTML = '<b>' + _uut('upd.hazir', { surum: esc(r.latestVersion) }) + '</b> '
              + _uut('upd.degisiklikler-etkin');
          });
        } else if (s && s.requiresFull) {
          // Çekirdek bileşenler değişmiş — küçük güncelleme yetmiyor, dürüstçe söyle.
          // await: fonksiyon artık async (uygulama içi kurulum destekleniyor mu
          // diye ana sürece soruyor). Beklenmezse aşağıdaki `finally` düğmeyi
          // önce sıfırlar ve kullanıcı bir an "hiçbir şey olmadı" görür.
          await tamIndirmeyeYonlendir(el, r.latestVersion, s.reason);
        } else {
          // İmza/hash doğrulaması düşmüş olabilir — sebebi GİZLEME.
          sonuc(() => {
            el.dataset.ton = 'err';
            el.innerHTML = esc((s && s.error) || _uut('upd.uygulanamadi'))
              + ' <a href="#" id="hq-upd-open" class="upd-bag">' + _uut('upd.tam-paketi-indir-bag') + '</a>';
            const l = $('hq-upd-open');
            if (l) l.onclick = (ev) => { ev.preventDefault(); window.yukiUpdater.openReleasesPage(); };
          });
        }
      } catch (e) {
        sonuc(() => {
          el.dataset.ton = 'err';
          el.textContent = _uut('upd.guncelleme-basarisiz', { hata: e.message || e });
        });
      } finally {
        if (typeof bitir === 'function') bitir();
        btn.disabled = false;
        btn.textContent = _uut('upd.simdi-guncelle');
      }
    };
  }

  document.addEventListener('DOMContentLoaded', () => {
    const toggle = $('hq-upd-toggle');
    if (toggle) toggle.addEventListener('change', onToggle);
    const kanal = $('hq-upd-channel');
    if (kanal) kanal.addEventListener('change', onChannel);
    // index.html'deki inline onclick kalktı (09-28) — düğme burada bağlanır
    const denetle = $('hq-upd-check');
    if (denetle) denetle.addEventListener('click', () => window.hqCheckUpdate());
    refresh();
    // Açılıştaki otomatik kontrol (yalnız ayar açıksa) sonuç bulursa panele düşsün.
    if (window.yukiUpdater && window.yukiUpdater.onAvailable) {
      window.yukiUpdater.onAvailable((r) => { showAvailable(r); refresh(); });
    }
  });

  // ── Dil değişiminde paneli tazele ─────────────────────────────────────
  window.addEventListener('yuki-dil-degisti', function () {
    refresh();
    if (_son) { try { _son(); } catch (_) { /* tazeleme paneli bozmaz */ } }
  });
})();
