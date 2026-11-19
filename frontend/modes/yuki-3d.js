/* ════════════════════════════════════════════════════════════════
   yuki-3d.js — VRM 3D Avatar Modu (Faz 0)

   Three.js + @pixiv/three-vrm ile #yuki-3d-canvas'a render eder.
   chat-modes.js tarafından lazy-load edilir; window.Yuki3D export.

   API:
     Yuki3D.activate()        → render loop başlat
     Yuki3D.deactivate()      → render loop durdur, canvas temizle
     Yuki3D.gesture(name)     → wave | greet | point | bow | curtsy
     Yuki3D.setState(s)       → idle | talking | listening | thinking
   ════════════════════════════════════════════════════════════════ */
(function () {
  'use strict';

  function _y3t(anahtar, degerler){ return (window.YukiDil && window.YukiDil.t) ? window.YukiDil.t(anahtar, degerler) : String(anahtar); }
  // Açık tanı şeridi (15 sn) dil değişince tazelenir; detay ham hata metnidir, çevrilmez.
  window.addEventListener('yuki-dil-degisti', function () {
    document.querySelectorAll('.yuki3d-tani').forEach(function (t) {
      t.textContent = _y3t('yuki3d.hata', { detay: t.dataset.detay || '' });
    });
  });

  const VRM_PATH   = '/ui/assets/characters/yuki3d.vrm';
  // yuki3d.vrm depoya girmez (yeniden dağıtım lisansı yok); kullanıcı kendi modelini buraya koyar.
  function _modelVar() {
    return fetch(VRM_PATH, { method: 'HEAD', cache: 'no-store' }).then(r => r.ok, () => false);
  }

  // ── durum ──
  let _active = false, _animId = null;
  let _vrm = null, _scene = null, _renderer = null, _camera = null, _controls = null;
  let _lookTarget = null;
  const B = {};
  const mouse = { x: 0, y: 0 };
  const sm = {
    headYaw: 0, headPit: 0, weight: 1, wTgt: 1, wT: 6,
    nod: 0, nodT: 2, blink: 0, blinkT: 3, mouth: 0, hipsY0: null,
  };
  let _state = 'idle', _clock = null;
  let _frozen = false;
  let _gest = null, _gestT = 0;
  let _stateTimer = 4, _seqI = 0;
  const SEQ = [['idle',5],['talking',6],['listening',3],['idle',4],['thinking',3.5]];
  let _realDriven = false; // Gerçek sinyaller gelirse true
  let _extMouth = null;    // Dış lip-sync kontrolü (null/0-1 sayı)

  // ── yardımcılar ──
  let _THREE, _OrbitControls, _GLTFLoader, _VRMLoaderPlugin, _VRMUtils;
  const D = r => r * Math.PI / 180;
  const clamp = (v, a, b) => Math.max(a, Math.min(b, v));
  const noise = (t, s=0) => Math.sin(t*0.31+s)*0.6 + Math.sin(t*0.73+s*1.7)*0.3 + Math.sin(t*1.13+s*2.9)*0.1;
  const easeIO = x => x < 0.5 ? 2*x*x : 1 - Math.pow(-2*x+2,2)/2;

  // ── Görünürlük pause durumu ──
  let _visPaused = false;

  // ── Pixel ratio hedefi: tamponu ~1600px'i aşmasın ──
  function _pixelCap() {
    if (!_renderer || !_scene) return Math.min(devicePixelRatio, 2);
    const paneWidth = _renderer.domElement?.parentElement?.clientWidth || 1;
    return Math.max(1, Math.min(devicePixelRatio, 2, 1600 / Math.max(paneWidth, 1)));
  }

  // ── Parçacık sistemi (tema-parametrik) ──
  let _particles = null;
  function _buildParticles(theme) {
    if (_particles) _scene.remove(_particles);
    const T = _THREE;
    const cfg = theme || { color: 0xbfe8ff, count: 220, size: 0.035, speedY: 0.3, sway: 0.15 };

    // CanvasTexture sprite — radyal beyaz→şeffaf gradient
    const canvas = document.createElement('canvas');
    canvas.width = 16; canvas.height = 16;
    const ctx = canvas.getContext('2d');
    const grad = ctx.createRadialGradient(8, 8, 0, 8, 8, 8);
    grad.addColorStop(0, 'rgba(255, 255, 255, 1)');
    grad.addColorStop(1, 'rgba(255, 255, 255, 0)');
    ctx.fillStyle = grad;
    ctx.fillRect(0, 0, 16, 16);
    const spriteTexture = new T.CanvasTexture(canvas);

    const positions = new Float32Array(cfg.count * 3);
    for (let i = 0; i < cfg.count; i++) {
      positions[i*3]   = (Math.random() - 0.5) * 6;     // x: [-3, 3]
      positions[i*3+1] = Math.random() * 5;             // y: [0, 5]
      positions[i*3+2] = (Math.random() - 0.5) * 4;     // z: [-2, 2]
    }
    const geo = new T.BufferGeometry();
    geo.setAttribute('position', new T.BufferAttribute(positions, 3));

    const mat = new T.PointsMaterial({
      color: cfg.color,
      size: cfg.size,
      map: spriteTexture,
      transparent: true,
      opacity: 0.75,
      depthWrite: false,
      sizeAttenuation: true,
      blending: T.AdditiveBlending,
    });
    _particles = new T.Points(geo, mat);
    _particles._cfg = cfg;
    // Hızları eşitle
    _particles._velocities = new Float32Array(cfg.count * 3);
    for (let i = 0; i < cfg.count; i++) {
      _particles._velocities[i*3]   = (Math.random() - 0.5) * cfg.sway;
      _particles._velocities[i*3+1] = -cfg.speedY;
      _particles._velocities[i*3+2] = (Math.random() - 0.5) * cfg.sway;
    }
    _scene.add(_particles);
  }

  // ── jestler ──
  const GEST = {
    wave:   { dur:2.6, fn:(p,e)=>({ rightUpperArm:{z:D(-176)*e,x:D(8)*e}, rightLowerArm:{y:(D(18)+Math.sin(p*Math.PI*2*5)*D(26))*e}, head:{z:D(5)*e}, _expr:{happy:0.45*e} }) },
    greet:  { dur:2.2, fn:(p,e)=>({ rightUpperArm:{z:D(-158)*e}, rightLowerArm:{y:D(-30)*e}, head:{z:D(6)*e,x:D(5)*e}, _expr:{happy:0.6*e} }) },
    point:  { dur:2.2, fn:(p,e)=>({ rightUpperArm:{z:D(-72)*e,y:D(-62)*e}, rightLowerArm:{y:D(-8)*e}, head:{y:D(-7)*e} }) },
    bow:    { dur:2.4, fn:(p,e)=>({ spine:{x:D(16)*e}, chest:{x:D(6)*e}, head:{x:D(8)*e}, leftUpperArm:{x:D(10)*e}, rightUpperArm:{x:D(10)*e} }) },
    curtsy: { dur:3.2, hipsY:-0.11, fn:(p,e)=>({ hips:{z:D(3)*e}, spine:{x:D(5)*e,z:D(6)*e}, head:{x:D(11)*e,z:D(11)*e}, leftUpperLeg:{z:D(13)*e}, rightUpperLeg:{z:D(-13)*e}, leftLowerLeg:{x:D(26)*e}, rightLowerLeg:{x:D(26)*e}, leftUpperArm:{z:D(14)*e,x:D(16)*e}, rightUpperArm:{z:D(-14)*e,x:D(16)*e}, leftLowerArm:{y:D(-22)*e}, rightLowerArm:{y:D(22)*e} }) },
  };

  function _applyOff(off) {
    let expr = null;
    for (const [bn, r] of Object.entries(off)) {
      if (bn === '_expr') { expr = r; continue; }
      const b = B[bn]; if (!b) continue;
      if (r.x != null) b.rotation.x += r.x;
      if (r.y != null) b.rotation.y += r.y;
      if (r.z != null) b.rotation.z += r.z;
    }
    return expr;
  }

  function _tickState(dt) {
    if (_realDriven) return; // Gerçek sinyaller gelince demo SEQ döngüsü durdur
    _stateTimer -= dt;
    if (_stateTimer <= 0) {
      _seqI = (_seqI + 1) % SEQ.length;
      _state = SEQ[_seqI][0];
      _stateTimer = SEQ[_seqI][1];
    }
  }

  // ── ana render döngüsü ──
  function _animate() {
    if (!_active) return;
    _animId = requestAnimationFrame(_animate);
    const dt = Math.min(_clock.getDelta(), 0.05);
    const t  = _clock.elapsedTime;

    // Kamera giriş animasyonu (z: 2.6 → 2.0, ≈0.9s ease)
    if (_camera && _camera._animTime < _camera._animDur) {
      _camera._animTime += dt;
      const p = _camera._animTime / _camera._animDur; // [0, 1]
      const eased = easeIO(p); // smooth easing
      _camera.position.z = 2.6 + (2.0 - 2.6) * eased;
    }

    if (_controls) _controls.update();

    // Parçacık animasyonu
    if (_particles) {
      const pos = _particles.geometry.attributes.position.array;
      const vel = _particles._velocities;
      const cfg = _particles._cfg;
      for (let i = 0; i < cfg.count; i++) {
        pos[i*3]   += vel[i*3]   * dt * 1.5;
        pos[i*3+1] += vel[i*3+1] * dt * 1.5;
        pos[i*3+2] += vel[i*3+2] * dt * 1.5;
        // Y < 0 olunca yukarı sarıl, yeni sway ata
        if (pos[i*3+1] < 0) {
          pos[i*3+1] = 5;
          vel[i*3] = (Math.random() - 0.5) * cfg.sway;
          vel[i*3+2] = (Math.random() - 0.5) * cfg.sway;
        }
      }
      _particles.geometry.attributes.position.needsUpdate = true;
    }

    // Zemin glow ring — nabız animasyonu (~20s döngü)
    const ring = _scene._glowRing;
    if (ring) {
      ring._pulse = (ring._pulse + dt * 0.05) % (2 * Math.PI);
      ring.material.opacity = 0.25 + Math.sin(ring._pulse) * 0.05;
    }

    if (_vrm && _frozen) { _vrm.update(dt); _renderer.render(_scene, _camera); return; }
    if (_vrm) {
      _tickState(dt);
      const talking = _state === 'talking', thinking = _state === 'thinking', listening = _state === 'listening';

      sm.wT -= dt; if (sm.wT <= 0) { sm.wTgt = -sm.wTgt; sm.wT = 7 + Math.random()*7; }
      sm.weight += (sm.wTgt - sm.weight) * dt * 0.5;
      const W = sm.weight;
      const br = Math.sin(t * 0.23 * Math.PI * 2), brOff = Math.sin((t-0.5)*0.23*Math.PI*2);

      if (B.hips)        { B.hips.position.y = sm.hipsY0; B.hips.rotation.set(0, noise(t,3)*D(0.6), W*D(3.2)); }
      if (B.spine)       B.spine.rotation.set(br*D(0.8), noise(t,7)*D(0.5), -W*D(1.4));
      const chest = B.upperChest || B.chest;
      if (chest)         chest.rotation.set(D(2)+br*D(1.4), 0, -W*D(0.8));
      if (B.leftShoulder)  B.leftShoulder.rotation.z =  brOff*D(0.9);
      if (B.rightShoulder) B.rightShoulder.rotation.z = -brOff*D(0.9);

      const swayL = noise(t,11)*D(1.6), swayR = noise(t,17)*D(1.6);
      let gestR = 0, gestL = 0, elbow = 0;
      if (talking) { gestR=(Math.sin(t*3.1)*0.5+0.5)*D(10); gestL=(Math.sin(t*2.3+1)*0.5+0.5)*D(6); elbow=D(8); }
      if (B.leftUpperArm)  B.leftUpperArm.rotation.set(D(6),0,D(-68)+swayL-gestL*0.3);
      if (B.rightUpperArm) B.rightUpperArm.rotation.set(D(6),0,D(68)+swayR+gestR*0.3);
      if (B.leftLowerArm)  B.leftLowerArm.rotation.set(0,-elbow*0.5,D(-12)-gestL);
      if (B.rightLowerArm) B.rightLowerArm.rotation.set(0,elbow*0.5,D(12)+gestR);
      ['leftUpperLeg','rightUpperLeg','leftLowerLeg','rightLowerLeg','leftFoot','rightFoot'].forEach(n=>{if(B[n]) B[n].rotation.set(0,0,0);});

      // bakış
      if (_lookTarget && B.head) {
        const _v = new _THREE.Vector3();
        B.head.getWorldPosition(_v);
        let gx = mouse.x*1.6, gy = mouse.y*1.1;
        if (thinking) { gx = -0.9; gy = 1.0; }
        _lookTarget.position.lerp(new _THREE.Vector3(_v.x+gx, _v.y+gy, _v.z+1.5), 0.2);
      }

      // kafa
      let tYaw = clamp(mouse.x*0.42,-0.5,0.5) + noise(t,21)*D(2.2);
      let tPit = clamp(-mouse.y*0.28,-0.32,0.32) + noise(t,29)*D(1.6);
      let tRoll = W*D(2.2) + noise(t,5)*D(1.0);
      if (thinking) { tYaw += D(-10); tPit += D(-6); tRoll += D(7); }
      sm.nodT -= dt; if (sm.nodT <= 0 && (listening||talking)) { sm.nod=1; sm.nodT=listening?1.4+Math.random():2.5+Math.random()*2; }
      sm.nod = Math.max(0, sm.nod - dt*3.5);
      const nodAmt = Math.sin(sm.nod*Math.PI)*D(7);
      const talkBob = talking ? Math.sin(t*7)*D(1.8) : 0;
      sm.headYaw += (tYaw - sm.headYaw)*0.12; sm.headPit += (tPit - sm.headPit)*0.12;
      if (B.neck) B.neck.rotation.set(sm.headPit*0.3, sm.headYaw*0.35, tRoll*0.3);
      if (B.head) B.head.rotation.set(sm.headPit*0.7+nodAmt+talkBob, sm.headYaw*0.65, tRoll*0.7);

      // jest overlay
      let gestExpr = null;
      if (_gest) {
        const g = GEST[_gest]; _gestT += dt;
        const p = Math.min(_gestT / g.dur, 1), e = easeIO(p < 0.25 ? p/0.25 : p > 0.72 ? (1-p)/0.28 : 1);
        if (g.hipsY != null && B.hips) B.hips.position.y = sm.hipsY0 + g.hipsY*e;
        gestExpr = _applyOff(g.fn(p, e));
        if (p >= 1) _gest = null;
      }

      // ifadeler
      const em = _vrm.expressionManager;
      if (em) {
        // Dış kontrol varsa onu kullan, yoksa kendi talking sinyali
        const mouthTarget = _extMouth != null ? _extMouth : (talking ? Math.max(0, Math.sin(t*9))*(0.45+0.45*Math.sin(t*2.3))*0.85 : 0);
        sm.mouth += (mouthTarget - sm.mouth)*0.4; em.setValue('aa', sm.mouth);
        sm.blinkT -= dt; if (sm.blinkT <= 0) { sm.blink=1; sm.blinkT=(talking?4:2.5)+Math.random()*3; }
        sm.blink = Math.max(0, sm.blink - dt*9); em.setValue('blink', sm.blink);
        let happy = talking ? 0.25 : 0.15;
        if (gestExpr && gestExpr.happy != null) happy = Math.max(happy, gestExpr.happy);
        if (em.expressionMap['happy'])   em.setValue('happy', happy);
        if (em.expressionMap['relaxed']) em.setValue('relaxed', thinking ? 0.3 : 0);
      }
      _vrm.update(dt);
    }
    _renderer.render(_scene, _camera);
  }

  // ── VRM yükleme (lazy) ──
  let _loaded = false, _loading = false, _loadCbs = [];
  async function _ensureLoaded() {
    if (_loaded) return;
    if (_loading) return new Promise(r => _loadCbs.push(r));
    _loading = true;

    // window._load3DDeps: index.html'de type="module" script içinde tanımlı.
    // Module context'te çalıştığından importmap çözümlemesi her tarayıcıda garantili.
    if (typeof window._load3DDeps !== 'function') {
      throw new Error('_load3DDeps undefined — index.html module script not loaded');
    }
    const deps = await window._load3DDeps();
    _THREE           = deps.THREE;
    _OrbitControls   = deps.OrbitControls;
    _GLTFLoader      = deps.GLTFLoader;
    _VRMLoaderPlugin = deps.VRMLoaderPlugin;
    _VRMUtils        = deps.VRMUtils;

    _loaded = true; _loading = false;
    _loadCbs.forEach(r => r()); _loadCbs = [];
  }

  async function _buildScene(canvas) {
    await _ensureLoaded();
    const T = _THREE;

    // Şeffaf canvas — OYUN modunun DOM sahnesi (halka/zemin/parçacık) arkada görünür
    _renderer = new T.WebGLRenderer({ canvas, antialias: true, alpha: true });
    _renderer.setPixelRatio(_pixelCap());
    _renderer.outputColorSpace = T.SRGBColorSpace;
    _renderer.setClearColor(0x070b14, 0);

    _scene = new T.Scene();

    _camera = new T.PerspectiveCamera(50, 1, 0.1, 50);
    _camera.position.set(0, 0.85, 2.6); // Giriş: z 2.6
    _camera._targetZ = 2.0;             // Hedef: z 2.0
    _camera._animTime = 0;
    _camera._animDur = 0.9;

    _controls = new _OrbitControls(_camera, _renderer.domElement);
    _controls.target.set(0, 0.85, 0); _controls.update();
    _controls.enablePan = false; _controls.maxDistance = 4.0; _controls.minDistance = 0.8;
    _controls.enableDamping = true; _controls.dampingFactor = 0.08;

    // Hemisphere — doğal gökyüzü/zemin ışığı (yumuşatıldı)
    _scene.add(new T.HemisphereLight(0xb0c8e8, 0x0a1a2e, 0.55)); // 0.7 → 0.55

    // Key light — sağ üstten sıcak ana ışık
    const key = new T.DirectionalLight(0xfff8f0, 1.3); // 1.6 → 1.3 (azaltıldı)
    key.position.set(1.2, 2.5, 2.0); _scene.add(key);

    // Rim light — TEK cyan vurgusu (soldan geri)
    const rim  = new T.DirectionalLight(0x00d2ff, 1.1); // 2.4 → 1.1 (ciddi azaltıldı)
    rim.position.set(-1.5, 1.8, -2.5); _scene.add(rim);

    // Siber grid zemin (opacity düşürüldü)
    const grid = new T.GridHelper(8, 24, 0x00d2ff, 0x001a2e);
    grid.position.y = 0.0;
    grid.material.transparent = true; grid.material.opacity = 0.12; // 0.2 → 0.12
    _scene.add(grid);

    // Zemin glow halkası — ayakla orantılı boyut, yere yatırılmış
    const ringGeo = new T.RingGeometry(0.5, 0.72, 64);
    const ringMat = new T.MeshBasicMaterial({
      color: 0x00d2ff,
      transparent: true,
      opacity: 0.25,
      side: T.DoubleSide,
      blending: T.AdditiveBlending,
    });
    const ring = new T.Mesh(ringGeo, ringMat);
    ring.position.y = 0.01;
    ring.rotation.x = -Math.PI / 2; // Yere yatır (XY düzlemden XZ düzlemine)
    ring._pulse = 0;
    _scene.add(ring);
    _scene._glowRing = ring;

    _clock = new T.Clock();

    _buildParticles({ color: 0xbfe8ff, count: 220, size: 0.035, speedY: 0.3, sway: 0.15 });

    return new Promise((res, rej) => {
      const loader = new _GLTFLoader();
      loader.register(p => new _VRMLoaderPlugin(p));
      loader.load(VRM_PATH, gltf => {
        _vrm = gltf.userData.vrm;
        try { _VRMUtils.removeUnnecessaryVertices(gltf.scene); } catch(e) {}
        if (_vrm.meta?.metaVersion === '0') { try { _VRMUtils.rotateVRM0(_vrm); } catch(e) {} }
        _scene.add(_vrm.scene);
        const H = n => _vrm.humanoid.getNormalizedBoneNode(n);
        ['hips','spine','chest','upperChest','neck','head','leftShoulder','rightShoulder',
         'leftUpperArm','rightUpperArm','leftLowerArm','rightLowerArm',
         'leftUpperLeg','rightUpperLeg','leftLowerLeg','rightLowerLeg','leftFoot','rightFoot'
        ].forEach(n => B[n] = H(n));
        if (B.hips) sm.hipsY0 = B.hips.position.y;
        _lookTarget = new T.Object3D(); _scene.add(_lookTarget);
        _vrm.lookAt.target = _lookTarget;
        res();
      }, undefined, rej);
    });
  }

  function _resize(canvas) {
    const pane = canvas.parentElement;
    if (!pane || !_renderer || !_camera) return;
    const w = pane.clientWidth || 300, h = pane.clientHeight || 500;
    canvas.width = w; canvas.height = h;
    _renderer.setSize(w, h, false);
    // Pencere büyürse pixel ratio yeniden hesapla
    _renderer.setPixelRatio(_pixelCap());
    _camera.aspect = w / h; _camera.updateProjectionMatrix();
  }

  // ── mouse takibi (avatar-pane üzerinden) ──
  let _mouseHandler = null;
  function _attachMouse(pane) {
    _mouseHandler = e => {
      const r = pane.getBoundingClientRect();
      mouse.x = ((e.clientX - r.left) / r.width)  * 2 - 1;
      mouse.y = -(((e.clientY - r.top) / r.height) * 2 - 1);
    };
    pane.addEventListener('pointermove', _mouseHandler);
  }

  let _resizeObs = null;

  // ── Görünürlük değişikliği dinleyicisi (modül seviyesi) ──
  function _onVisibilityChange() {
    if (document.hidden) {
      // Sayfa gizlendi → rAF iptal
      _visPaused = true;
      if (_animId) { cancelAnimationFrame(_animId); _animId = null; }
    } else {
      // Sayfa görünür oldu → rAF devam (eğer _active ise)
      _visPaused = false;
      if (_active && !_animId) {
        _animate();
      }
    }
  }

  // ══════════════════════════════════════════════
  // PUBLIC API
  // ══════════════════════════════════════════════

  let _sceneReady = false, _activating = false;

  window.Yuki3D = {

    async activate() {
      if (_active) return true;
      _active = true; _activating = true;
      const canvas = document.getElementById('yuki-3d-canvas');
      if (!canvas) { _active = false; console.error('Yuki3D: #yuki-3d-canvas bulunamadı'); return false; }
      canvas.style.display = 'block';
      // CSS'e ek olarak JS ile de gizle — 3d-mode.css yüklenme gecikmesine karşı
      ['yuki-video','yuki-canvas','yuki-fullbody-img','yuki-fb-video','yuki-fal-overlay']
        .forEach(id => { const el = document.getElementById(id); if (el) el.style.display = 'none'; });

      try {
        if (!_sceneReady && !(await _modelVar())) {
          // Model depoda dağıtılmıyor (NOTICE); yoksa 3B sessizce kapalı kalır — tanı şeridi yok.
          console.info('Yuki3D: ' + VRM_PATH + ' yok, 3B kapalı');
          _active = false; _activating = false;
          canvas.style.display = 'none';
          return false;
        }
        if (!_sceneReady) {
          await _buildScene(canvas);
          _sceneReady = true;
        } else {
          // renderer'ı bu canvas'a yeniden bağla
          _renderer.domElement = canvas;
        }
        _resize(canvas);
        _attachMouse(canvas.parentElement || document.getElementById('avatar-pane'));

        _resizeObs = new ResizeObserver(() => _resize(canvas));
        _resizeObs.observe(canvas.parentElement || document.body);

        // Görünürlük dinleyicisini kur (BİR KEZ)
        document.addEventListener('visibilitychange', _onVisibilityChange);

        _activating = false;
        _animate();
        return true;
      } catch (err) {
        console.error('Yuki3D activate hatası:', err);
        _active = false; _activating = false;
        canvas.style.display = 'none';
        // Telefonda görünür tanı
        const t = document.createElement('div');
        t.style.cssText = 'position:fixed;bottom:80px;left:8px;right:8px;background:#640;color:#ff0;' +
          'padding:10px;z-index:99999;font:11px/1.4 monospace;border-radius:4px;word-break:break-all;';
        t.className = 'yuki3d-tani';
        t.dataset.detay = (err && (err.message || String(err))) || '';
        t.textContent = _y3t('yuki3d.hata', { detay: t.dataset.detay });
        document.body.appendChild(t);
        setTimeout(() => t.remove(), 15000);
        return false;
      }
    },

    deactivate() {
      _active = false;
      if (_animId) { cancelAnimationFrame(_animId); _animId = null; }
      if (_resizeObs) { _resizeObs.disconnect(); _resizeObs = null; }
      if (_mouseHandler) {
        const pane = document.getElementById('avatar-pane');
        if (pane) pane.removeEventListener('pointermove', _mouseHandler);
        _mouseHandler = null;
      }
      // Parçacıklar sahnede KALIR: rAF durduğu için maliyet yok; sökülürse
      // _sceneReady cache'i yüzünden VID→3D dönüşünde geri gelmez (denetim fix'i).
      // Tam temizlik dispose()'un işi.
      const canvas = document.getElementById('yuki-3d-canvas');
      if (canvas) canvas.style.display = 'none';
      // 2D elemanları geri aç
      const vid = document.getElementById('yuki-video');
      if (vid) vid.style.display = '';
    },

    dispose() {
      // deactivate'i çağır
      this.deactivate();

      // Dinleyiciyi kaldır
      document.removeEventListener('visibilitychange', _onVisibilityChange);

      // Sahneyi traverse et, tüm geometry/material/texture dispose et
      if (_scene) {
        _scene.traverse(obj => {
          if (obj.geometry) obj.geometry.dispose();
          if (obj.material) {
            if (Array.isArray(obj.material)) {
              obj.material.forEach(m => m.dispose());
            } else {
              obj.material.dispose();
            }
          }
        });
      }

      // VRM derinlemesine dispose (try/catch)
      if (_vrm) {
        try {
          if (_VRMUtils && _VRMUtils.deepDispose) {
            _VRMUtils.deepDispose(_vrm.scene);
          }
        } catch (e) { /* yut */ }
      }

      // Renderer dispose
      if (_renderer) {
        _renderer.dispose();
      }

      // Kontrolleri dispose
      if (_controls) {
        try { _controls.dispose(); } catch (e) { /* yok */ }
      }

      // Tüm referansları temizle
      _scene = null;
      _vrm = null;
      _camera = null;
      _renderer = null;
      _particles = null;
      _lookTarget = null;
      _visPaused = false;
      _sceneReady = false;
    },

    gesture(name) {
      if (!GEST[name]) return;
      _gest = name; _gestT = 0;
    },

    setState(s) {
      if (['idle','talking','listening','thinking'].includes(s)) _state = s;
    },

    setMouth(v) {
      if (v == null) {
        _extMouth = null; // Dış kontrol temizle
      } else {
        _extMouth = Math.max(0, Math.min(1, parseFloat(v) || 0)); // 0-1 clamp
      }
    },

    listGestures() { return Object.keys(GEST); },

    _debug() {
      return {
        lights: _scene.children.filter(c => c.isLight).map(c => ({ type: c.type, intensity: c.intensity, position: c.position })),
        particles: _particles ? { count: _particles._cfg.count, color: '0x' + _particles._cfg.color.toString(16).padStart(6, '0') } : null,
        sceneChildren: _scene.children.length,
        pixelRatio: _renderer ? _renderer.getPixelRatio() : null,
        cameraZ: _camera ? _camera.position.z : null,
        glowRing: _scene._glowRing ? { opacity: _scene._glowRing.material.opacity, pulse: _scene._glowRing._pulse } : null,
        visPaused: _visPaused,
        disposed: !_scene || !_renderer,
        state: _state,
        realDriven: _realDriven,
        extMouth: _extMouth,
        mouth: sm.mouth,
      };
    },
  };

  // WS mesajlarıyla otomatik senkron (core.js'den updateState çağrısında dispatch edilir)
  document.addEventListener('yuki-state', e => {
    if (e.detail && e.detail.state) {
      _realDriven = true; // İlk gerçek event'te demo döngüsünü durdur
      window.Yuki3D.setState(e.detail.state);
    }
  });

})();
