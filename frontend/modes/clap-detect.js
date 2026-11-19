/* ════════════════════════════════════════════════════════════════════
   clap-detect.js — Arka Plan Alkış Algılama

   Her zaman aktif. Ayrı bir mikrofon akışı açar.
   1 alkış → dosya_yonetim modu  (Dolphin + alan4)
   2 alkış → kodlama modu        (VS Code + workspace 2)

   İki koşul birlikte sağlanmalı:
     1) RMS > CLAP_THRESHOLD        (yeterince yüksek ses)
     2) yüksek frekans oranı > SPECTRAL_RATIO  (alkışın tiz karakteri)
   Masa vuruşu 2. koşulu geçemez (bas ağırlıklıdır).
   ════════════════════════════════════════════════════════════════════ */
(function () {
  'use strict';

  const CLAP_THRESHOLD  = 0.22;   // RMS eşiği
  const SPECTRAL_RATIO  = 0.38;   // 2kHz+ / toplam enerji oranı — alkış ≥0.38, vuruş <0.25
  const HIGH_FREQ_HZ    = 2000;   // bu frekansın üzeri "yüksek" sayılır
  const SILENCE_RATIO   = 0.30;   // eşiğin bu katı altına düşünce yeniden silahlı
  const MIN_CLAP_GAP_MS = 300;    // iki alkış arası minimum süre
  const WINDOW_MS       = 1400;   // son alkıştan sonra bekle, sonra tetikle
  const COOLDOWN_MS     = 2000;   // mod tetiklendikten sonra görmezden gel

  const MODE_MAP = {
    1: 'dosya_yonetim',
    2: 'kodlama',
  };

  let _ctx      = null;
  let _stream   = null;
  let _running  = false;
  let _count    = 0;
  let _lastClap = 0;
  let _timer    = null;
  let _armed    = true;
  let _cooldown = false;
  let _cutBin   = 0;   // HIGH_FREQ_HZ'e karşılık gelen bin indeksi (başlatılırken hesaplanır)

  function _getAuth() {
    try { return (typeof _authToken !== 'undefined' && _authToken) ? { Authorization: 'Bearer ' + _authToken } : {}; }
    catch (e) { return {}; }
  }

  function _triggerMode(count) {
    const modeId = MODE_MAP[count];
    if (!modeId) return;
    _cooldown = true;
    setTimeout(function () { _cooldown = false; }, COOLDOWN_MS);
    console.log('[ClapDetect] ' + count + ' alkış → ' + modeId);
    fetch('/api/modes/start', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json', ..._getAuth() },
      body: JSON.stringify({ mode_id: modeId }),
    }).catch(function (e) { console.warn('[ClapDetect] istek başarısız:', e); });
  }

  function _onClap() {
    const now = Date.now();
    if (!_armed || _cooldown || now - _lastClap < MIN_CLAP_GAP_MS) return;
    _lastClap = now;
    _armed = false;
    _count++;
    clearTimeout(_timer);
    _timer = setTimeout(function () {
      const n = _count;
      _count = 0;
      _triggerMode(n);
    }, WINDOW_MS);
  }

  function _loop(analyser, timeBuf, freqBuf) {
    if (!_running) return;
    requestAnimationFrame(function () { _loop(analyser, timeBuf, freqBuf); });

    // RMS
    analyser.getFloatTimeDomainData(timeBuf);
    let sum = 0;
    for (let i = 0; i < timeBuf.length; i++) sum += timeBuf[i] * timeBuf[i];
    const rms = Math.sqrt(sum / timeBuf.length);

    // Sessizlikte yeniden silahlı
    if (!_armed && rms < CLAP_THRESHOLD * SILENCE_RATIO) _armed = true;

    if (rms > CLAP_THRESHOLD) {
      // Spektral kontrol: 2kHz+ enerjisi toplam enerjinin yeterli payını oluşturmalı
      analyser.getByteFrequencyData(freqBuf);
      let total = 0, high = 0;
      for (let i = 0; i < freqBuf.length; i++) {
        total += freqBuf[i];
        if (i >= _cutBin) high += freqBuf[i];
      }
      const isClap = total > 0 && (high / total) >= SPECTRAL_RATIO;
      if (isClap) _onClap();
    }
  }

  async function _start() {
    if (_running) return;
    try {
      // Alkış algılama sohbetle AYNI cihazı dinlemeli — yoksa kullanıcı mikrofonunu
      // seçer, alkış hâlâ sistem varsayılanını dinler ve hiç tetiklenmez.
      _stream = await navigator.mediaDevices.getUserMedia({
        audio: window.MicDevices ? window.MicDevices.constraints() : true,
        video: false,
      });
      _ctx    = new (window.AudioContext || window.webkitAudioContext)();
      const src      = _ctx.createMediaStreamSource(_stream);
      const analyser = _ctx.createAnalyser();
      analyser.fftSize = 512;
      src.connect(analyser);

      _cutBin  = Math.floor(HIGH_FREQ_HZ / (_ctx.sampleRate / analyser.fftSize));
      _running = true;
      _loop(analyser, new Float32Array(analyser.fftSize), new Uint8Array(analyser.frequencyBinCount));
      console.log('[ClapDetect] aktif — eşik:', CLAP_THRESHOLD, '| spektral oran:', SPECTRAL_RATIO, '| cutBin:', _cutBin);
    } catch (e) {
      console.warn('[ClapDetect] mikrofon erişimi reddedildi veya hata:', e);
    }
  }

  function _stop() {
    _running  = false;
    _armed    = true;
    _cooldown = false;
    _count    = 0;
    clearTimeout(_timer);
    if (_stream) { _stream.getTracks().forEach(function (t) { t.stop(); }); _stream = null; }
    if (_ctx)    { _ctx.close(); _ctx = null; }
  }

  // Alkış algılama şimdilik devre dışı — aktif etmek için: ClapDetect.start()
  // if (document.readyState === 'loading') {
  //   document.addEventListener('DOMContentLoaded', _start);
  // } else {
  //   _start();
  // }

  window.ClapDetect = { start: _start, stop: _stop };
})();
