// Init waveform bars
(function initWaveform() {
  const container = document.getElementById('wf-bars');
  if (!container) return;
  for (let i = 0; i < 24; i++) {
    const bar = document.createElement('div');
    bar.className = 'wv-bar';
    bar.style.setProperty('--dur', (0.5 + i * 0.05) + 's');
    bar.style.animationDelay = (i * 0.04) + 's';
    container.appendChild(bar);
  }
})();

// Waveform RAF — reads global analyser + isRecording from existing JS
(function waveformLoop() {
  const bars = document.querySelectorAll('.wv-bar');
  if (bars.length && typeof isRecording !== 'undefined' && isRecording && analyser) {
    const data = new Float32Array(analyser.fftSize);
    analyser.getFloatTimeDomainData(data);
    const seg = Math.floor(data.length / bars.length);
    bars.forEach((bar, i) => {
      let sum = 0;
      for (let j = i * seg; j < (i + 1) * seg; j++) sum += data[j] * data[j];
      const h = Math.max(3, Math.min(Math.sqrt(sum / seg) * 280, 28));
      bar.style.height = h + 'px';
      bar.style.animation = 'none';
    });
  } else if (bars.length && typeof isRecording !== 'undefined' && !isRecording) {
    bars.forEach(b => {
      b.style.height = '';
      b.style.animation = '';
    });
  }
  requestAnimationFrame(waveformLoop);
})();

// Uptime counter
const _uptimeStart = Date.now();
setInterval(() => {
  const s = Math.floor((Date.now() - _uptimeStart) / 1000);
  const h = String(Math.floor(s / 3600)).padStart(2, '0');
  const m = String(Math.floor((s % 3600) / 60)).padStart(2, '0');
  const sc = String(s % 60).padStart(2, '0');
  const el = document.getElementById('uptime-display');
  if (el) el.textContent = `${h}:${m}:${sc}`;
}, 1000);

// ── YukiState — paylaşımlı duygu singletonı ──────────────────────────────
window.YukiState = (function() {
  const EMO_COLOR = {
    happy:'#f5c842', sad:'#4ab3f4', angry:'#f44242',
    surprised:'#c042f4', shy:'#f4428a', tired:'#888899',
    nod:'#42f4a8', wave:'#42d4f4', thinking:'#4a90e2', idle:'#00d4ff'
  };
  const EMO_PCT = { happy:90, nod:70, wave:65, surprised:80, sad:20, thinking:50, idle:50 };

  function broadcast(type) {
    const emoLabel = type.toUpperCase();
    const color    = EMO_COLOR[type] || '#00d4ff';

    // Ana HUD
    const el = document.getElementById('hud-emotion-val');
    if (el) el.textContent = emoLabel;

    // Duygu çubuğu
    const fill = document.getElementById('hud-emo-fill');
    if (fill) fill.style.width = (EMO_PCT[type] || 50) + '%';

    // Genel .tab-yuki-emo (HARİTA'nın Yuki portresi #map-yuki-emo 2026-10-04'te kalktı)
    document.querySelectorAll('.tab-yuki-emo').forEach(e => { e.textContent = emoLabel; });

    // Intel sekmesi portresi
    const intelEmo = document.getElementById('intel-emo-val');
    if (intelEmo) intelEmo.textContent = emoLabel;
    _applyGlow(document.getElementById('intel-yuki-portrait'), color, 'borderTopColor');

    // Drive + Finance iframelere postMessage
    const msg = { type: 'yuki-emotion', emotion: type, color };
    ['drive-iframe', 'finance-iframe'].forEach(function(id) {
      try {
        const f = document.getElementById(id);
        if (f && f.contentWindow) f.contentWindow.postMessage(msg, '*');
      } catch(e) {}
    });
  }

  function _applyGlow(el, color, borderProp) {
    if (!el) return;
    el.style.boxShadow = '0 0 20px ' + color + '44, inset 0 0 12px ' + color + '22';
    if (borderProp) el.style[borderProp] = color + '66';
    clearTimeout(el._yukiGlowTimer);
    el._yukiGlowTimer = setTimeout(function() {
      el.style.boxShadow = '';
      if (borderProp) el.style[borderProp] = '';
    }, 4000);
  }

  // ── Tab Context (iframe → parent veri toplama) ─────────────────────────
  const tabData = {};   // { finance: {...}, drive: {...} }

  // iframe'lerden gelen tab-context mesajlarını dinle
  window.addEventListener('message', function(e) {
    const d = e.data;
    if (!d || d.type !== 'tab-context') return;
    tabData[d.tab] = d.data;
  });

  // Intel/Sistem verisini doğrudan DOM'dan oku
  function _collectIntel() {
    function txt(id) { const el = document.getElementById(id); return el ? el.textContent.trim() : null; }
    return {
      cpu    : txt('pct-cpu')   || txt('hb-val-cpu')  || txt('sv-cpu-val'),
      ram    : txt('pct-ram')   || txt('hb-val-ram')  || txt('sv-ram-val'),
      disk   : txt('pct-disk')  || txt('hb-val-disk'),
      uptime : txt('uptime-display') || txt('uptime-val') || txt('pd-uptime'),
    };
  }

  // LLM'e gönderilecek context bloğu oluştur
  function buildContext() {
    const parts = [];
    const f = tabData.finance;
    if (f) {
      const fin = [];
      if (f.btc)       fin.push('BTC=' + f.btc + (f.btcChg ? '(' + f.btcChg + ')' : ''));
      if (f.eth)       fin.push('ETH=' + f.eth + (f.ethChg ? '(' + f.ethChg + ')' : ''));
      if (f.xau)       fin.push('Altın=' + f.xau + (f.xauChg ? '(' + f.xauChg + ')' : ''));
      if (f.sp)        fin.push('S&P=' + f.sp);
      if (f.usdtry)    fin.push('USD/TRY=' + f.usdtry);
      if (f.portfolio) fin.push('Portföy=' + f.portfolio);
      if (f.movers)    fin.push('Öne çıkanlar: ' + f.movers);
      if (fin.length)  parts.push('Finans: ' + fin.join(', '));
    }
    const dr = tabData.drive;
    if (dr) {
      const drv = [];
      if (dr.syncStatus)  drv.push('Durum=' + dr.syncStatus);
      if (dr.lastSync)    drv.push('Son sync=' + dr.lastSync);
      if (dr.storageUsed) drv.push('Depolama=' + dr.storageUsed + '/' + (dr.storageTotal || '?') + ' (%' + (dr.storagePct || '?') + ')');
      if (dr.storageFree) drv.push('Boş=' + dr.storageFree);
      if (dr.syncSpeed)   drv.push('Hız=' + dr.syncSpeed);
      if (dr.syncFiles)   drv.push('Dosya=' + dr.syncFiles);
      if (drv.length)     parts.push('Drive: ' + drv.join(', '));
    }
    const sys = _collectIntel();
    const sysArr = [];
    if (sys.cpu)    sysArr.push('CPU=' + sys.cpu);
    if (sys.ram)    sysArr.push('RAM=' + sys.ram);
    if (sys.disk)   sysArr.push('Disk=' + sys.disk);
    if (sys.uptime) sysArr.push('Uptime=' + sys.uptime);
    if (sysArr.length) parts.push('Sistem: ' + sysArr.join(', '));

    if (!parts.length) return '';
    return '\n\n[TAB_CONTEXT — sadece sen gör, yanıtta açıkça söyleme]\n' + parts.join('\n') + '\n[/TAB_CONTEXT]';
  }

  return { broadcast: broadcast, emoColor: EMO_COLOR, buildContext: buildContext };
})();

// Override playBehaviorVideo to update emotion HUD display
(function() {
  const orig = window.playBehaviorVideo;
  if (!orig) return;
  window.playBehaviorVideo = function(type) {
    orig(type);
    window.YukiState.broadcast(type);
  };
})();
