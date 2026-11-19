// ── İndir-gerektiğinde: model indirme UX ────────────────────────────────────
// Ağır modeller (whisper STT vb.) uygulamayla gelmez; ilk kullanımda indirilir.
// window.yukiModels (Electron preload) varsa gerçek indirme; web modunda bilgilendirme.
//
// Ana API:  await ModelDownloader.ensureSTT()  → true (kullanılabilir) | false (iptal/yok)
//   mic butonu tıklanınca çağrılır: model yoksa onay+indirme modalı açar.
(() => {
  'use strict';

  // ── i18n sarmalayıcı ──────────────────────────────────────────────
  function _mdlt(anahtar, degerler) {
    return (window.YukiDil && window.YukiDil.t) ? window.YukiDil.t(anahtar, degerler) : String(anahtar);
  }

  /* Metin ya düz dize ya da çağrıldığında o anki dilde dize döndüren fonksiyon:
     açık modal dil değişince fonksiyonları yeniden çözer (bkz. dosya sonu). */
  const _coz = (v) => (typeof v === 'function' ? v() : v);
  const _acikModaller = new Set();

  const fmtMB = (b) => (b ? (b / 1048576).toFixed(0) + ' MB' : '?');

  function injectStyle() {
    if (document.getElementById('md-style')) return;
    const s = document.createElement('style');
    s.id = 'md-style';
    s.textContent = `
    .md-overlay{position:fixed;inset:0;z-index:9000;display:flex;align-items:center;justify-content:center;
      background:rgba(2,8,18,.62);backdrop-filter:var(--glass-blur,blur(10px));-webkit-backdrop-filter:var(--glass-blur,blur(10px));
      animation:mdFade .18s ease}
    @keyframes mdFade{from{opacity:0}to{opacity:1}}
    .md-card{width:min(92vw,420px);background:var(--bg-panel,rgba(1,13,31,.92));border:1px solid rgba(60,207,232,.28);
      border-radius:16px;padding:26px 24px 20px;box-shadow:0 20px 60px rgba(0,0,0,.5);color:var(--text-bright,#e8f4fa);
      text-align:center;animation:mdPop .22s cubic-bezier(.2,.8,.25,1)}
    @keyframes mdPop{from{transform:translateY(10px) scale(.97);opacity:0}to{transform:none;opacity:1}}
    .md-icon{font-size:38px;line-height:1;margin-bottom:10px}
    .md-title{margin:0 0 6px;font-size:18px;font-weight:600;letter-spacing:.2px}
    .md-desc{margin:0 0 16px;font-size:13.5px;line-height:1.55;opacity:.82}
    .md-desc b{color:var(--accent,#3ccfe8);font-weight:600}
    .md-progress{margin:6px 0 16px;display:none}
    .md-progress.on{display:block}
    .md-bar{height:8px;border-radius:6px;background:rgba(255,255,255,.09);overflow:hidden}
    .md-bar-fill{height:100%;width:0;border-radius:6px;background:linear-gradient(90deg,var(--accent,#3ccfe8),var(--gold,#d9b45a));
      transition:width .2s ease}
    .md-bar-fill.indet{width:35%;animation:mdIndet 1.1s ease-in-out infinite}
    @keyframes mdIndet{0%{margin-left:-35%}100%{margin-left:100%}}
    .md-meta{margin-top:8px;font-size:12px;opacity:.72;font-variant-numeric:tabular-nums}
    .md-error{display:none;margin:0 0 14px;font-size:13px;color:#ff8f8f;line-height:1.5}
    .md-error.on{display:block}
    .md-actions{display:flex;gap:10px;justify-content:center}
    .md-btn{flex:1;max-width:150px;padding:10px 14px;border-radius:10px;font-size:14px;font-weight:600;cursor:pointer;
      border:1px solid transparent;transition:filter .15s,background .15s,border-color .15s}
    .md-btn:focus-visible{outline:2px solid var(--accent,#3ccfe8);outline-offset:2px}
    .md-secondary{background:transparent;border-color:rgba(255,255,255,.18);color:var(--text-bright,#e8f4fa)}
    .md-secondary:hover{border-color:rgba(255,255,255,.4)}
    .md-primary{background:var(--accent,#3ccfe8);color:#04121a}
    .md-primary:hover{filter:brightness(1.08)}
    @media (prefers-reduced-motion:reduce){.md-overlay,.md-card{animation:none}.md-bar-fill,.md-bar-fill.indet{transition:none;animation:none}}
    `;
    document.head.appendChild(s);
  }

  // Tek modal — durum geçişleri: confirm → downloading → done/error. Promise<boolean> döner.
  function openModal({ icon = '🎤', title, desc, confirmLabel = () => _mdlt('mdl.indir'), mode = 'confirm', metaText = '' }) {
    injectStyle();
    const overlay = document.createElement('div');
    overlay.className = 'md-overlay';
    overlay.innerHTML = `
      <div class="md-card" role="dialog" aria-modal="true">
        <div class="md-icon">${icon}</div>
        <h3 class="md-title"></h3>
        <p class="md-desc"></p>
        <div class="md-progress"><div class="md-bar"><div class="md-bar-fill"></div></div><div class="md-meta"></div></div>
        <p class="md-error"></p>
        <div class="md-actions"></div>
      </div>`;
    const $ = (sel) => overlay.querySelector(sel);
    let baslik = title;          // setDone() başlığı değiştirir → o da tazelenir
    let sonDugmeler = [];
    const metinleriYaz = () => {
      $('.md-card').setAttribute('aria-label', _coz(title));
      $('.md-title').textContent = _coz(baslik);
      $('.md-desc').innerHTML = _coz(desc);
    };
    metinleriYaz();
    $('.md-meta').textContent = metaText;
    document.body.appendChild(overlay);

    const fill = $('.md-bar-fill');
    const progWrap = $('.md-progress');
    const meta = $('.md-meta');
    const errEl = $('.md-error');
    const actions = $('.md-actions');

    const api = {
      el: overlay,
      onProgress: null, onConfirm: null, onCancel: null, onClose: null, onRetry: null,
      setActions(btns) {
        sonDugmeler = btns;
        actions.innerHTML = '';
        btns.forEach((b) => {
          const el = document.createElement('button');
          el.className = 'md-btn ' + (b.primary ? 'md-primary' : 'md-secondary');
          el.textContent = _coz(b.label);
          el.onclick = b.onClick;
          actions.appendChild(el);
        });
      },
      toDownloading() {
        progWrap.classList.add('on');
        fill.classList.remove('indet'); fill.style.width = '0%';
        errEl.classList.remove('on');
        $('.md-desc').style.display = 'none';
        this.setActions([{ label: () => _mdlt('mdl.iptal'), onClick: () => this.onCancel && this.onCancel() }]);
      },
      setProgress(p) {
        if (p.phase === 'extract') {
          fill.classList.add('indet'); meta.textContent = _mdlt('mdl.aciliyor');
        } else if (p.phase === 'done') {
          fill.classList.remove('indet'); fill.style.width = '100%'; meta.textContent = '';
        } else {
          fill.classList.remove('indet');
          const pct = p.total ? Math.min(100, Math.round((p.received / p.total) * 100)) : null;
          fill.style.width = (pct == null ? 5 : pct) + '%';
          meta.textContent = pct == null
            ? _mdlt('mdl.indirildi', { boyut: fmtMB(p.received) })
            : `${pct}%  ·  ${fmtMB(p.received)} / ${fmtMB(p.total)}`;
        }
      },
      setDone(msg = () => _mdlt('mdl.hazir')) {
        baslik = msg;
        $('.md-title').textContent = _coz(msg);
        fill.classList.remove('indet'); fill.style.width = '100%'; meta.textContent = '';
        this.setActions([]);
      },
      setError(msg) {
        progWrap.classList.remove('on');
        errEl.textContent = msg; errEl.classList.add('on');
        this.setActions([
          { label: () => _mdlt('mdl.kapat'), onClick: () => this.onClose && this.onClose() },
          { label: () => _mdlt('mdl.tekrar-dene'), primary: true, onClick: () => this.onRetry && this.onRetry() },
        ]);
      },
      close() { _acikModaller.delete(api); try { overlay.remove(); } catch (_) {} },
      /* Dil değişti: başlık/açıklama/düğmeler yeniden çözülür. İlerleme satırı
         bir sonraki ilerleme olayında, hata metni (backend'den gelir) olduğu gibi kalır. */
      dilYenile() {
        metinleriYaz();
        const eski = sonDugmeler;
        if (eski.length) this.setActions(eski);
      },
    };

    if (mode === 'confirm') {
      api.setActions([
        { label: () => _mdlt('mdl.vazgec'), onClick: () => api.onCancel && api.onCancel() },
        { label: confirmLabel, primary: true, onClick: () => api.onConfirm && api.onConfirm() },
      ]);
    } else if (mode === 'info') {
      api.setActions([{ label: () => _mdlt('mdl.tamam'), primary: true, onClick: () => api.onClose && api.onClose() }]);
    }
    // Escape / overlay-tık = vazgeç (indirme sırasında iptal)
    overlay.addEventListener('click', (e) => { if (e.target === overlay) (api.onCancel || api.onClose || (()=>{}))(); });
    _acikModaller.add(api);
    return api;
  }

  function infoModal(title, desc, icon = 'ℹ️') {
    return new Promise((resolve) => {
      const m = openModal({ icon, title, desc, mode: 'info' });
      m.onClose = () => { m.close(); resolve(false); };
    });
  }

  // Model indirme akışı (onay → indir → doğrula → reload). Promise<boolean>.
  function runDownload(id, ms, opts) {
    opts = opts || {};
    return new Promise((resolve) => {
      const sizeTxt = fmtMB(ms.downloadBytes || ms.sizeBytes);
      const m = openModal({
        icon: opts.icon || '🎤',
        title: ms.name || (() => _mdlt('mdl.model-indir')),
        desc: () => _mdlt('mdl.indir-aciklama', { ozellik: ms.feature || _mdlt('mdl.bu-ozellik'), boyut: sizeTxt }),
        confirmLabel: () => _mdlt('mdl.indir-boyut', { boyut: sizeTxt }),
      });

      let unsub = null, finished = false;
      const cleanup = () => { if (unsub) { unsub(); unsub = null; } };

      const start = () => {
        m.toDownloading();
        if (window.yukiModels.onProgress) unsub = window.yukiModels.onProgress((p) => {
          if (p.id === id) m.setProgress(p);
        });
        window.yukiModels.download(id).then(async (res) => {
          if (finished) return; finished = true; cleanup();
          if (res && res.ok) {
            if (opts.reloadUrl !== null) {
              //  · LOG: indirme BAŞARILI ama backend modeli yeniden yüklemedi.
              // Kullanıcıya söylenmez (model diskte, sonraki açılışta gelir) ama izsiz
              // kalırsa "indirdim, hâlâ çalışmıyor" şikâyeti teşhis edilemez.
              /* ⚠️ authFetch ŞART (2026-09-06'de bulundu): bu çağrı düz
                 `fetch` ile yazılmıştı. `AUTH_TOKEN` tanımlıyken reload uçları
                 401 döner, hata da try/catch'e düşmez (fetch 401'de reject
                 ETMEZ) → "indirdim ama çalışmıyor" sınıfı sessiz arıza.
                 Yanıtı ayrıca kontrol ediyoruz; sessiz 401 bir daha olmasın. */
              try {
                const f = (typeof window.authFetch === 'function') ? window.authFetch : fetch;
                const rr = await f(opts.reloadUrl || '/api/stt/reload', { method: 'POST' });
                if (!rr.ok) console.warn('[yuki] reload ucu', rr.status, opts.reloadUrl || '/api/stt/reload');
              }
              catch (e) { console.warn('[yuki] model indirildi ama reload başarısız:', e); }
            }
            m.setDone();
            setTimeout(() => { m.close(); resolve(true); }, 750);
          } else {
            finished = false;   // tekrar denenebilsin
            m.setError((res && res.error) || _mdlt('mdl.indirme-basarisiz'));
          }
        }).catch((e) => {
          if (finished) return; finished = false; cleanup();
          m.setError(e && e.message ? e.message : _mdlt('mdl.indirme-hatasi'));
        });
      };

      m.onConfirm = start;
      m.onRetry = () => { m.el.querySelector('.md-error').classList.remove('on'); start(); };
      m.onCancel = () => { cleanup(); if (window.yukiModels.cancel) window.yukiModels.cancel(id); m.close(); resolve(false); };
      m.onClose = () => { cleanup(); m.close(); resolve(false); };
    });
  }

  // ── Ana giriş: STT kullanılabilir mi? Değilse indir. ──
  async function ensureSTT() {
    let status = null;
    try {
      const r = await fetch('/api/stt/status');
      if (r.ok) status = await r.json();
      else console.warn('[yuki] /api/stt/status', r.status, '— mikrofon fail-open ile açılıyor');
    } catch (e) { console.warn('[yuki] /api/stt/status ulaşılamadı:', e); }

    // Durum alınamadıysa (eski backend / ağ hatası) mikrofonu ENGELLEME — backend zaten
    // model yoksa graceful-degrade eder (boş transkript). Fail-open.
    if (!status) return true;
    if (status.model_present) return true;   // model diskte → devam

    // Electron değil (web) → indirilemez
    if (!window.yukiModels) {
      return infoModal(() => _mdlt('mdl.sesle-konusma'),
        () => _mdlt('mdl.sesle-konusma-aciklama'));
    }

    let ms = null;
    try { ms = await window.yukiModels.status('whisper-small'); }
    catch (e) { console.warn('[yuki] whisper-small model durumu okunamadı:', e); }

    // Dosya diskte var ama backend henüz görmemiş → reload + devam
    if (ms && ms.present) {
      try { await fetch('/api/stt/reload', { method: 'POST' }); }
      catch (e) { console.warn('[yuki] /api/stt/reload başarısız (model diskte, devam ediliyor):', e); }
      return true;
    }
    if (!ms || !ms.downloadable) {
      return infoModal(() => _mdlt('mdl.ses-tanima'),
        () => _mdlt('mdl.ses-paketi-yok'));
    }
    return runDownload('whisper-small', ms, { icon: '🎤' });
  }

  // ── Semantik hafıza ("Unutmayan Yuki") motoru hazır mı? Değilse indir. ──
  // HQ hafıza paneli ilk açılışında çağrılır. Sessiz başarısızlık ilkesi:
  // model gelmezse uygulama çalışmaya devam eder, hafıza basit moda düşer.
  async function ensureMemory(opts) {
    opts = opts || {};
    let st = null;
    try {
      const r = await fetch('/api/memory/engine');
      if (r.ok) st = await r.json();
      else console.warn('[yuki] /api/memory/engine', r.status, '— hafıza basit moda düşüyor');
    } catch (e) { console.warn('[yuki] /api/memory/engine ulaşılamadı:', e); }

    if (!st) return false;              // eski backend / ağ hatası → sessiz geç
    if (!st.allowed) return false;      // motor kapalı → indirmenin anlamı yok
    if (!st.needs_model) return true;   // motor zaten hazır

    if (!window.yukiModels) {           // tarayıcı modu → indiremeyiz
      if (opts.silentInWeb) return false;
      return infoModal(() => _mdlt('mdl.hafiza'),
        () => _mdlt('mdl.hafiza-aciklama'), '🧠');
    }

    let ms = null;
    try { ms = await window.yukiModels.status('embedding-onnx'); }
    catch (e) { console.warn('[yuki] embedding-onnx model durumu okunamadı:', e); }
    if (ms && ms.present) return true;  // dosya diskte; backend ilk kullanımda yükler
    if (!ms || !ms.downloadable) return false;

    return runDownload('embedding-onnx', ms, { icon: '🧠', reloadUrl: null });
  }

  /* ── Yüz tanıma KÜTÜPHANESİ hazır mı? Değilse indir. ──────────────
   *
   * Model değil KÜTÜPHANE indiriyoruz: `insightface` + `onnx` pakete konmadı
   * (paket boyutu kararı B). Yük platforma özel (~16 MB) ve `models-cache`
   * altına açılıyor; backend onu `sys.path`'in SONUNA bağlıyor.
   *
   * 🔑 `reloadUrl` BURADA HAYATİ: `/api/pydeps/reload` çağrılmazsa kullanıcı
   * indirmeyi bitirir, dosya diske iner ve özellik **yine kapalı görünür** —
   * çünkü `pydeps.kur()` yalnız açılışta koşuyordu. Eksik olan halka buydu.
   */
  async function ensureFaceLib(opts) {
    opts = opts || {};

    // Zaten kullanılabilir mi? Backend'e sor — dosya varlığına bakmak yetmez,
    // asıl soru "import edilebiliyor mu".
    /* 🔴 "BİLMİYORUM" ≠ "KURULU DEĞİL" (2026-09-08, geliştirici sahada buldu).
       Eski hâlde `r.ok` false olunca kod sessizce aşağı düşüyor ve indirme
       ekranını açıyordu. Uygulama kilidi kuruluyken bu uç **401** döner →
       "kurulu mu?" sorusu HİÇ cevaplanmamış olur → kütüphane diskte dururken
       (ölçüldü: `models-cache/pydeps/face/insightface` dolu, backend token'la
       `available:true` diyor) kullanıcıya sürekli "indir" gösteriliyordu.
       geliştiricinin cümlesi: *"her zaman indirme çıkıyor, indirmiş olmama rağmen."*

       🔑 Yetki hatasında indirme ekranı AÇILMAZ. Yanlış yönde hata yapmanın
       bedeli asimetrik: kurulu olanı tekrar indirtmek 16 MB + kullanıcıya
       "bozuk" hissi verir; kurulu olmayanı bir tur sonra sormak bedavadır. */
    try {
      const f = (typeof window.authFetch === 'function') ? window.authFetch : fetch;
      const r = await f('/api/pydeps/status');
      if (r.ok) {
        const st = await r.json();
        const c = (st.capabilities && st.capabilities.face_recognition) || {};
        if (c.available) return true;
      } else if (r.status === 401 || r.status === 403) {
        console.warn('[yuki] /api/pydeps/status yetki reddetti (%s) — kurulu olup olmadığı BİLİNMİYOR, indirme ekranı açılmıyor.', r.status);
        if (opts.silentInWeb) return false;
        return infoModal(() => _mdlt('mdl.yuz-tanima'),
          () => _mdlt('mdl.oturum-kilitli'), '🙂');
      }
    } catch (e) { console.warn('[yuki] /api/pydeps/status ulaşılamadı:', e); }

    if (!window.yukiModels) {          // tarayıcı modu → indiremeyiz
      if (opts.silentInWeb) return false;
      return infoModal(() => _mdlt('mdl.yuz-tanima'),
        () => _mdlt('mdl.yuz-tanima-masaustu'), '🙂');
    }

    let ms = null;
    try { ms = await window.yukiModels.status('face-pydeps'); }
    catch (e) { console.warn('[yuki] face-pydeps durumu okunamadı:', e); }

    if (!ms || !ms.downloadable) {
      /* Manifest'te kayıt "yakında" durumundaysa (asset henüz release'e
         yüklenmemiş) burada dürüst olmak şart — "indir" düğmesi gösterip
         404 aldırmak, kullanıcıyı bozuk bir şey sanmaya iter. */
      return infoModal(() => _mdlt('mdl.yuz-tanima'),
        () => _mdlt('mdl.yuz-paketi-yok'), '🙂');
    }
    const kutuphane = await runDownload('face-pydeps', ms,
                                        { icon: '🙂', reloadUrl: '/api/pydeps/reload' });
    if (!kutuphane) return false;

    /* ── Model de BURADA iner ────────────────────────────────────
       🔴 Neden burada: kütüphane inince özellik "hazır" görünüyordu, ama ilk
       "Tanı" tıklamasında insightface kendi indiricisiyle 276 MB'ı SESSİZCE
       çekiyordu — ilerleme yok, iptal yok, SHA yok. Kullanıcı için bu, donmuş
       bir uygulamadır.

       İkisini tek akışta indirmek dürüst olanı: kullanıcı "yüz tanımayı aç"
       dediğinde toplam maliyeti bir kez görür (16 MB + 276 MB), ortada bir yerde
       sürpriz beklemez.

       ⚠️ Model indirilemezse `false` DÖNMÜYORUZ: kütüphane indi ve insightface
       modeli kendi yolundan yine çekebilir — yavaş ve göstergesiz ama çalışır.
       Burada `false` dönmek, çalışabilecek bir özelliği kapatırdı. */
    let mm = null;
    try { mm = await window.yukiModels.status('face-model'); }
    catch (e) { console.warn('[yuki] face-model durumu okunamadı:', e); }
    if (mm && mm.downloadable && !mm.present) {
      try {
        await runDownload('face-model', mm, { icon: '🙂' });
      } catch (e) {
        console.warn('[yuki] yüz modeli indirilemedi, insightface kendi yolundan çekecek:', e);
      }
    }
    return true;
  }

  window.ModelDownloader = { ensureSTT, ensureMemory, ensureFaceLib };

  /* Dil tazeleyici: yalnız ŞU AN açık modalların metni yeniden çözülür;
     indirme sürüyorsa dokunulmaz (düğme/ilerleme durumu korunur). */
  window.addEventListener('yuki-dil-degisti', () => {
    _acikModaller.forEach((m) => { try { m.dilYenile(); } catch (_) {} });
  });
})();
