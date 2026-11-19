/**
 * vrm-worker.js — VRM animasyon hesaplamaları (main thread'den ayrı)
 *
 * Neden Worker?
 *   - Sinüs/BCurve animasyon hesaplamaları her frame ~0.2-0.8ms alır.
 *   - Main thread'de renderer + LLM SSE + WebSocket zaten yoğun.
 *   - Worker → main thread iletişimi postMessage ile (SharedArrayBuffer gerekmez).
 *
 * Kullanım (index.html):
 *   const worker = new Worker('vrm-worker.js');
 *   worker.postMessage({ type: 'tick', delta, elapsed, mouthValue, blinkValue });
 *   worker.onmessage = ({ data }) => applyBoneTransforms(data);
 */

'use strict';

// ------------------------------------------------------------------ //
// Animasyon hesaplama fonksiyonları (Three.js bağımsız — saf math)
// ------------------------------------------------------------------ //

/**
 * Nefes animasyonu — göğüs hafif sinüs hareketi.
 * @returns {number} chest.rotation.x değeri (radyan)
 */
function calcBreath(elapsed) {
  return Math.sin(elapsed * 0.7) * 0.014;
}

/**
 * Idle baş hareketi — yavaş sinüs.
 * @returns {{ y: number, x: number }} head rotation
 */
function calcHeadIdle(elapsed) {
  return {
    y: Math.sin(elapsed * 0.4) * 0.06,
    x: Math.sin(elapsed * 0.31) * 0.04 - 0.03,
  };
}

/**
 * A-pose kol açısı — sabit değer, her frame hesaplamak gerekmez
 * ama Worker mimarisini kesmemek için burada.
 */
function calcArmPose() {
  return { left: -Math.PI / 4.5, right: Math.PI / 4.5 };
}

/**
 * Göz kırpma state machine.
 * State: { phase, progress, timer, eyeValue }
 * @returns {{ phase, progress, timer, eyeValue }}
 */
function tickBlink(state, delta) {
  const CLOSE_SPEED = 1 / 0.07;  // 70ms'de kapan
  const OPEN_SPEED  = 1 / 0.09;  // 90ms'de aç
  const BLINK_INTERVAL_MIN = 2.5;
  const BLINK_INTERVAL_MAX = 6.0;

  let { phase, progress, timer, eyeValue } = state;
  timer -= delta;

  if (phase === 'open' && timer <= 0) {
    phase = 'closing';
    progress = 0;
  } else if (phase === 'closing') {
    progress = Math.min(1, progress + delta * CLOSE_SPEED);
    eyeValue = progress;
    if (progress >= 1) { phase = 'opening'; progress = 0; }
  } else if (phase === 'opening') {
    progress = Math.min(1, progress + delta * OPEN_SPEED);
    eyeValue = 1 - progress;
    if (progress >= 1) {
      phase = 'open';
      timer = BLINK_INTERVAL_MIN + Math.random() * (BLINK_INTERVAL_MAX - BLINK_INTERVAL_MIN);
      eyeValue = 0;
    }
  }
  return { phase, progress, timer, eyeValue };
}

// ------------------------------------------------------------------ //
// Worker state
// ------------------------------------------------------------------ //

let blinkState = {
  phase: 'open',
  progress: 0,
  timer: 3.0,
  eyeValue: 0,
};

// ------------------------------------------------------------------ //
// Message handler
// ------------------------------------------------------------------ //

self.onmessage = function (e) {
  const { type, delta, elapsed, mouthValue } = e.data;

  if (type !== 'tick') return;

  blinkState = tickBlink(blinkState, delta);

  self.postMessage({
    type: 'frame',
    chestX:    calcBreath(elapsed),
    head:      calcHeadIdle(elapsed),
    arms:      calcArmPose(),
    eyeValue:  blinkState.eyeValue,
    mouthOpen: mouthValue ?? 0,
  });
};
