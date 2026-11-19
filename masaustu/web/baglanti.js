// Masaüstü Yuki F2 — bağlantının sayfa yarısı. İki kipte de (portre · tam) aynı dosya.
// Host (masaustu/balon.py Kopru) /ws/realtime olaylarını çevirip buradaki window.yukiBag'i çağırır:
//   yuz(duygu, ms) · selam() · dusun(bool) · konus(bool) · konusSure(sn) · sesCal(base64, cal)
// Sayfanın verdiği kancalar (ince): window.yukiMotor = {kip, av | vrm} · window.yukiUyandir() ·
// kip tam'da her karede window.yukiEk(dt, B, em) çağrısı (kemik ofsetleri o karenin içinde kalmalı).
//
// Ses: `audio` yalnız mesajı gönderen sokete gelir (backend). Masaüstünün kendi turunun sesi burada ÇALAR
// (cal=true, tek kaynak); proaktif ses herkese gider ve ana pencere çalar → burada sessiz (gain 0) oynatılır,
// yalnız seviyesi ağza verilir. Ana pencerenin turunda ses hiç gelmez → ağız yapay hareketle oynar.
(function () {
  'use strict';
  const B = window.yukiBag = {
    dusunuyor: false, konusuyor: false, konusBitis: 0, sesVar: false, seviye: 0, gecmis: [],
    sesSay: { cal: 0, sessiz: 0, hata: 0 },
  };
  let ctx = null, analiz = null, buf = null, kaynak = null, dongu = 0, dw = 0, son = 0;

  function iz(x) {
    B.gecmis.push(x); if (B.gecmis.length > 60) B.gecmis.shift();
    const d = window.yukiDurum; if (d && d.gecmis) d.gecmis.push('bag:' + x);
  }
  function uyandir() { if (window.yukiUyandir) window.yukiUyandir(); }
  function aktif() { return B.dusunuyor || konusmaVar() || dw > 0.01; }
  function konusmaVar() { return B.konusuyor || B.sesVar || performance.now() < B.konusBitis; }

  B.yuz = function (duygu, ms) { iz('yuz:' + duygu); return window.yukiYuz ? window.yukiYuz(duygu, ms || 8000) : false; };
  B.selam = function () { iz('selam'); return window.yukiYuz ? window.yukiYuz('wave', 3000) : false; };
  B.dusun = function (on) {
    on = !!on; if (B.dusunuyor === on) return; B.dusunuyor = on; iz(on ? 'dusun' : 'dusun-bitti');
    if (on) uyandir(); basla();
  };
  B.konus = function (on) {
    on = !!on; const once = konusmaVar();
    B.konusuyor = on; if (!on) B.konusBitis = 0;
    if (once !== konusmaVar() || on) iz(on ? 'konus' : 'konus-bitti');
    if (on) uyandir(); basla();
  };
  // Ana pencerenin turu: `done` geldi ama ses orada sürüyor → tahmini süre kadar daha konuşur.
  B.konusSure = function (sn) {
    B.konusuyor = false; B.konusBitis = sn > 0 ? performance.now() + sn * 1000 : 0;
    iz('konus-sure:' + (+sn).toFixed(1)); basla();
  };
  B.sesCal = async function (b64, cal) {
    try {
      const AC = window.AudioContext || window.webkitAudioContext;
      if (!AC) throw new Error('AudioContext yok');
      if (!ctx) {
        ctx = new AC(); analiz = ctx.createAnalyser(); analiz.fftSize = 512;
        buf = new Float32Array(analiz.fftSize);
      }
      if (ctx.state === 'suspended') await ctx.resume().catch(() => {});
      const ham = Uint8Array.from(atob(b64), c => c.charCodeAt(0)).buffer;
      const tampon = await ctx.decodeAudioData(ham);
      if (kaynak) { try { kaynak.stop(); } catch (e) { /* bitmiş */ } }
      const k = kaynak = ctx.createBufferSource(); k.buffer = tampon;
      const kazanc = ctx.createGain(); kazanc.gain.value = cal ? 1 : 0;
      k.connect(analiz); analiz.connect(kazanc); kazanc.connect(ctx.destination);
      k.onended = () => { if (kaynak === k) { kaynak = null; B.sesVar = false; iz('ses-bitti'); } };
      B.sesVar = true; uyandir(); k.start();
      B.sesSay[cal ? 'cal' : 'sessiz']++;
      iz('ses:' + (cal ? 'cal' : 'sessiz') + ':' + tampon.duration.toFixed(2));
      basla();
      return +tampon.duration.toFixed(2);
    } catch (e) {
      B.sesSay.hata++; iz('ses-hata'); console.warn('[masaustu] ses çözülemedi:', e && e.message || e);
      return null;
    }
  };
  B.durum = function () {
    return { dusunuyor: B.dusunuyor, konusuyor: konusmaVar(), seviye: +B.seviye.toFixed(3),
             sesSay: B.sesSay, gecmis: B.gecmis.slice(-20) };
  };

  // 0..1 ağız seviyesi: gerçek ses varsa onun gücü, yoksa konuşurken yapay hece ritmi
  function seviyeOlc(t) {
    if (B.sesVar && analiz) {
      analiz.getFloatTimeDomainData(buf);
      let top = 0; for (let i = 0; i < buf.length; i++) top += buf[i] * buf[i];
      return Math.min(1, Math.sqrt(top / buf.length) * 10);
    }
    if (!konusmaVar()) return 0;
    const v = 0.45 + 0.35 * Math.sin(t * 13.0) * Math.sin(t * 3.1 + 0.6);   // ~4-6 hece/sn
    return Math.max(0, Math.min(1, v));
  }

  // her kare: seviye + düşünme ağırlığı (yumuşak geçiş)
  function adim(dt) {
    const t = performance.now() / 1000;
    const hedef = seviyeOlc(t);
    B.seviye += (hedef - B.seviye) * Math.min(1, dt * 18);
    dw += ((B.dusunuyor ? 1 : 0) - dw) * Math.min(1, dt * 4);
    if (!B.dusunuyor && dw < 0.01) dw = 0;
    if (!konusmaVar() && B.seviye < 0.01) B.seviye = 0;
    const d = window.yukiDurum;                 // ölçüm: ağız ne kadar açıldı (kuru test okur)
    if (d && B.seviye > (d.agiz_tepe || 0)) d.agiz_tepe = +B.seviye.toFixed(3);
  }

  // kip tam: sayfa her karede çağırır (kemikler o karede dinlenme pozundan kurulur, ofset birikmez)
  window.yukiEk = function (dt, kemik, em) {
    adim(dt);
    if (em) em.setValue('aa', B.seviye * 0.75);
    const bas = kemik && kemik('head'), boyun = kemik && kemik('neck');
    if (bas) {
      if (dw > 0) { bas.rotateZ(0.13 * dw); bas.rotateX(-0.10 * dw); }   // düşünürken başını yana eğip yukarı bakar
      if (B.seviye > 0) bas.rotateX(0.05 * B.seviye);                      // konuşurken hafif baş sallama
    }
    if (boyun && dw > 0) boyun.rotateY(0.12 * dw);
  };

  // kip portre: motorun kendi çağrıları; döngü yalnız etkinken koşar (boşta işlemci yemez)
  function portreAdim() {
    dongu = 0;
    const m = window.yukiMotor;
    if (!m || m.kip !== 'portre' || !m.av) return;
    const simdi = performance.now(), dt = Math.min(0.1, (simdi - (son || simdi)) / 1000) || 1 / 30;
    son = simdi;
    adim(dt);
    const k = konusmaVar();
    m.av.setSpeaking(k); m.av.setVoiceLevel(k ? B.seviye : 0);
    if (dw > 0) m.av.setParameters({ angleX: -9, angleY: 11, angleZ: 7 }, dw);
    else m.av.setParameters({}, 0);
    if (aktif()) dongu = setTimeout(portreAdim, 33);
    else { son = 0; m.av.setSpeaking(false); m.av.setVoiceLevel(0); }
  }
  function basla() {
    const m = window.yukiMotor;
    if (m && m.kip === 'portre' && !dongu) dongu = setTimeout(portreAdim, 0);
  }
})();
