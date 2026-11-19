/*! mesh-avatar-studio 6f6d362 (c) 2026 Yuki Shindo — MIT (bkz. LICENSE). Yuki CANLI kipi motor paketi, tools/mesh-avatar/derle.sh */
var rt = Object.defineProperty;
var lt = (o, t, e) => t in o ? rt(o, t, { enumerable: !0, configurable: !0, writable: !0, value: e }) : o[t] = e;
var Fe = (o, t, e) => lt(o, typeof t != "symbol" ? t + "" : t, e);
const ee = (o, t, e) => {
  (typeof o != "number" || !Number.isFinite(o)) && e.push(`${t}: expected a finite number`);
}, ge = (o, t, e) => {
  ee(o, t, e), typeof o == "number" && o <= 0 && e.push(`${t}: must be positive`);
}, ue = (o, t, e) => {
  ge(o, t, e), typeof o == "number" && !Number.isInteger(o) && e.push(`${t}: expected an integer`);
}, ye = (o, t, e) => {
  ee(o, t, e), typeof o == "number" && !Number.isInteger(o) && e.push(`${t}: expected an integer`);
}, je = (o, t, e) => {
  (typeof o != "string" || !o.trim()) && e.push(`${t}: expected a non-empty string`);
}, le = (o, t = 0, e = 1 / 0) => (a, i, h) => {
  if (!Array.isArray(a)) {
    h.push(`${i}: expected an array`);
    return;
  }
  (a.length < t || a.length > e) && h.push(`${i}: expected ${t}..${e} items`), a.forEach((g, M) => o(g, `${i}[${M}]`, h));
}, he = le(ee, 2, 2), ie = (o, t, e) => {
  he(o, t, e), Array.isArray(o) && o.length === 2 && o[0] >= o[1] && e.push(`${t}: start must be less than end`);
}, ae = (o, t = []) => (e, a, i) => {
  if (!e || typeof e != "object" || Array.isArray(e)) {
    i.push(`${a}: expected an object`);
    return;
  }
  const h = e;
  for (const [g, M] of Object.entries(o))
    h[g] === void 0 && t.includes(g) || M(h[g], `${a}.${g}`, i);
}, Ee = { cx: ee, cy: ee, rx: ge, ry: ge }, ce = ae(Ee), Te = le(he, 3), We = le(he, 2), Ye = (o, t, e) => {
  ee(o, t, e), typeof o == "number" && (o < 0 || o > 1) && e.push(`${t}: must be between 0 and 1`);
}, ht = (o) => ae({
  version: (t, e, a) => {
    t !== 1 && a.push(`${e}: only version 1 is supported`);
  },
  image: ae({ width: ue, height: ue }),
  head: ae({
    ...Ee,
    shiftX: ee,
    shiftY: ee,
    pivotX: ee,
    pivotY: ee,
    maxRoll: ee,
    weightBand: ie,
    turnBand: ie
  }),
  body: ae({
    pivotX: ee,
    pivotY: ee,
    maxRoll: ee,
    breathBand: ie,
    rollBand: ie,
    chest: ce,
    shoulders: le(ce)
  }),
  face: ae({
    nose: ce,
    mouth: ce,
    eyeA: ce,
    eyeB: ce,
    earL: ce,
    earR: ce,
    brow: ae({ ...Ee, band: ie }),
    jaw: ae({ ...Ee, band: ie })
  }),
  buns: ae({ bunL: ce, bunR: ce }, ["bunL", "bunR"]),
  eyes: le(ae({
    opening: Te,
    roi: Te,
    x0: ee,
    x1: ee,
    top: le(ee, 24, 24),
    bot: le(ee, 24, 24)
  }, o ? ["x0", "x1", "top", "bot"] : []), 2, 2),
  mouth: ae({
    cx: ee,
    cy: ee,
    angle: ee,
    halfLen: ge,
    bow: ee,
    area: ae({ ...Ee, angle: ee })
  }),
  cheeks: le(he, 2, 2),
  strands: le(ae({ name: je, nodes: We, sigma: ge, k: ge, max: ge })),
  accessories: le(ae({
    name: je,
    pivot: he,
    tip: he,
    split: Ye,
    box: le(ye, 4, 4),
    color: ae({ redness: Ye, minRed: ee })
  })),
  hand: ae({
    outline: Te,
    jaw: We,
    jawRange: ie,
    background: Te,
    elbow: he,
    wrist: he,
    knuckle: he,
    contact: he,
    forearmShare: Ye,
    armBand: ie,
    wristBand: ie,
    handBand: ie,
    fingerXBand: ie,
    fingerYBand: ie,
    pinBand: ie
  }),
  mesh: ae({
    baseCell: ue,
    fine: ae({
      x0: ye,
      x1: ye,
      y0: ye,
      y1: ye,
      cell: ue
    }),
    handCell: ue,
    tasselCell: ue,
    eyeBallCell: ue,
    eyeCell: ue,
    spriteCell: ue
  }),
  view: ae({ padTop: ee, padSide: ee, gazeCenter: he }, ["gazeCenter"])
}, ["buns", "strands", "accessories", "hand"]);
function ct(o, t = {}) {
  const e = [];
  if (ht(t.draft ?? !1)(o, "rig", e), e.length) return e;
  const a = o;
  a.eyes.forEach((i, h) => {
    const g = ["x0", "x1", "top", "bot"];
    if (!(t.draft && g.every((M) => i[M] === void 0))) {
      if (g.some((M) => i[M] === void 0)) {
        e.push(`rig.eyes[${h}]: supply all x0/x1/top/bot fields or omit all in a draft`);
        return;
      }
      i.x0 >= i.x1 && e.push(`rig.eyes[${h}].x1: must exceed x0`), i.top.some((M, O) => M > i.bot[O]) && e.push(`rig.eyes[${h}].top: must not exceed bottom curve`);
    }
  }), (a.mesh.fine.x0 >= a.mesh.fine.x1 || a.mesh.fine.y0 >= a.mesh.fine.y1) && e.push("rig.mesh.fine: rectangle must have positive area"), (a.view.padTop <= -1 || a.view.padTop >= 1 || a.view.padSide <= -0.5) && e.push("rig.view: margins must leave a positive viewport");
  for (const [i, h] of (a.strands ?? []).entries())
    h.nodes.some((g, M) => M > 0 && g[0] === h.nodes[M - 1][0] && g[1] === h.nodes[M - 1][1]) && e.push(`rig.strands[${i}].nodes: consecutive nodes must differ`);
  for (const [i, h] of (a.accessories ?? []).entries())
    (h.box[0] < 0 || h.box[1] < 0 || h.box[2] > a.image.width || h.box[3] > a.image.height) && e.push(`rig.accessories[${i}].box: rectangle must stay inside the image`), (h.split <= 0 || h.split >= 1) && e.push(`rig.accessories[${i}].split: must be strictly between 0 and 1`), h.pivot.every((g, M) => g === h.tip[M]) && e.push(`rig.accessories[${i}].tip: must differ from pivot`), (h.box[0] >= h.box[2] || h.box[1] >= h.box[3]) && e.push(`rig.accessories[${i}].box: rectangle must have positive area`);
  return e;
}
function ut(o) {
  const t = ct(o);
  if (t.length) throw new Error(`Invalid rig:
${t.join(`
`)}`);
  return structuredClone(o);
}
const Re = [
  { id: "angleX", label: "Face angle X", min: -30, max: 30, def: 0, group: "Head and body" },
  { id: "angleY", label: "Face angle Y", min: -30, max: 30, def: 0, group: "Head and body" },
  { id: "angleZ", label: "Face roll", min: -30, max: 30, def: 0, group: "Head and body" },
  { id: "bodyAngleX", label: "Body angle X", min: -10, max: 10, def: 0, group: "Head and body" },
  { id: "bodyAngleZ", label: "Body roll", min: -10, max: 10, def: 0, group: "Head and body" },
  { id: "breath", label: "Breath", min: 0, max: 1, def: 0, group: "Head and body" },
  { id: "eyeLOpen", label: "Left eye open", min: 0, max: 1.25, def: 1, group: "Eyes and brows" },
  { id: "eyeROpen", label: "Right eye open", min: 0, max: 1.25, def: 1, group: "Eyes and brows" },
  { id: "eyeSmile", label: "Eye smile", min: 0, max: 1, def: 0, group: "Eyes and brows" },
  { id: "gazeX", label: "Gaze X", min: -1, max: 1, def: 0, group: "Eyes and brows" },
  { id: "gazeY", label: "Gaze Y", min: -1, max: 1, def: 0, group: "Eyes and brows" },
  { id: "browY", label: "Brow Y", min: -1, max: 1, def: 0, group: "Eyes and brows" },
  { id: "browAngle", label: "Brow angle", min: -1, max: 1, def: 0, group: "Eyes and brows" },
  { id: "mouthOpen", label: "Mouth open", min: 0, max: 1, def: 0, group: "Mouth and cheeks" },
  { id: "mouthForm", label: "Mouth form (i to o)", min: -1, max: 1, def: 0, group: "Mouth and cheeks" },
  { id: "blush", label: "Blush", min: 0, max: 1, def: 0, group: "Mouth and cheeks" },
  { id: "armAngle", label: "Arm angle", min: -10, max: 10, def: 0, group: "Hand" },
  { id: "handAngle", label: "Wrist angle", min: -10, max: 10, def: 0, group: "Hand" },
  { id: "fingerTap", label: "Finger tap", min: 0, max: 1, def: 0, group: "Hand" }
];
function ft(o) {
  const t = { w: o.image.width, h: o.image.height }, e = (f, u, l) => l ? Math.exp(-(((f - l.cx) / l.rx) ** 2 + ((u - l.cy) / l.ry) ** 2)) : 0, a = 24, i = o.eyes;
  function h(f, u) {
    const l = Math.min(1, Math.max(0, u)) * (a - 1), T = Math.min(Math.floor(l), a - 2), k = l - T;
    return f[T] + (f[T + 1] - f[T]) * k;
  }
  function g(f, u, l, T) {
    u = Math.min(1, Math.max(0, u));
    const k = h(f.top, u), U = h(f.bot, u), S = 1 - l, I = 4 * u * (1 - u), D = h(f.bot, 0.5) - h(f.top, 0.5), te = f.top[0] + (f.top[a - 1] - f.top[0]) * u - 0.3 * D * I, m = Math.max(k, U + 1 + (te - U - 1) * T);
    return [(m - k) * Math.max(S, -0.07), S > 0 ? (m - U) * S * T : 0];
  }
  const M = [[-2, 1], [-1, 2], [0, 3], [1, 2], [2, 1]], O = 5;
  function w(f, u, l, T) {
    let k = 0, U = 0;
    for (const [te, m] of M) {
      const [E, H] = g(f, (u + te * O - f.x0) / (f.x1 - f.x0), l, T);
      k += E * m / 9, U += H * m / 9;
    }
    const S = Math.min(1, Math.max(0, (u - f.x0) / (f.x1 - f.x0))), I = h(f.top, S), D = h(f.bot, S);
    return { top: I, bot: D, b: 1 - l, lid: I + k, bc: D + U };
  }
  function _(f, u, l, T, k, U) {
    const S = w(f, l, k, U);
    return u === "lash" ? S.lid - (S.top - T) * (1 - 0.3 * Math.min(1, Math.max(0, S.b))) : u === "low" ? T + (S.bc - S.bot) : u === "crease" ? T + (S.lid - S.top) * 0.22 : T;
  }
  function v(f, u, l) {
    const T = Math.min(1, Math.max(0, 1 - u));
    return f === "low" ? 1 - Math.min(1, T * l * 1.2) : f === "crease" ? 1 - 0.45 * T : 1;
  }
  const C = o.mouth, N = o.cheeks, x = o.head, A = o.body, y = (f, u, l) => {
    const T = Math.min(1, Math.max(0, (l - f) / (u - f)));
    return T * T * (3 - 2 * T);
  };
  function d(f, u) {
    return 1 - y(...x.weightBand, u);
  }
  function n(f, u) {
    return 1 - y(...x.turnBand, u);
  }
  const s = o.strands ?? [];
  function p(f, u, l) {
    let T = 1 / 0, k = 0;
    const U = l.length - 1;
    for (let S = 0; S < U; S++) {
      const [I, D] = l[S], [te, m] = l[S + 1], E = te - I, H = m - D, Q = Math.min(1, Math.max(0, ((f - I) * E + (u - D) * H) / (E * E + H * H))), oe = Math.hypot(f - I - E * Q, u - D - H * Q);
      oe < T && (T = oe, k = (S + Q) / U);
    }
    return [T, k];
  }
  function r(f, u, l) {
    if (l < 0.02) return [];
    const T = [];
    let k = 0;
    s.forEach((S, I) => {
      const [D, te] = p(f, u, S.nodes), m = Math.exp(-((D / S.sigma) ** 2));
      m < 0.02 || (T.push([I, m, te]), k += m);
    });
    const U = Math.max(1, k);
    return T.map(([S, I, D]) => [S, l * I / U * y(0.04, 0.55, D), D]);
  }
  function c(f, u, l = 1) {
    return {
      head: d(f, u),
      turn: n(f, u),
      strands: r(f, u, l),
      bunL: e(f, u, o.buns?.bunL),
      bunR: e(f, u, o.buns?.bunR),
      brow: e(f, u, o.face.brow) * (1 - y(...o.face.brow.band, u)),
      // chin below the mouth line drops a little when the mouth opens
      jaw: e(f, u, o.face.jaw) * y(...o.face.jaw.band, u),
      // per-feature depth for head turns (nose sticks out most, ears sit at the back)
      nose: e(f, u, o.face.nose),
      mouth: e(f, u, o.face.mouth),
      eyeA: e(f, u, o.face.eyeA),
      eyeB: e(f, u, o.face.eyeB),
      earR: e(f, u, o.face.earR),
      earL: e(f, u, o.face.earL),
      chest: e(f, u, A.chest),
      breath: 1 - y(...A.breathBand, u),
      shoulder: A.shoulders.reduce((T, k) => T + e(f, u, k), 0)
    };
  }
  function F(f, u, l, T) {
    const k = (f - x.cx) / x.rx, U = (u - x.cy) / x.ry, S = 1 - k * k - U * U;
    if (S <= 0) return [0, 0];
    const I = y(0, 0.84, S);
    return [l * x.shiftX * I, -T * x.shiftY * I];
  }
  function j(f, u, l, T) {
    const k = Math.cos(T), U = Math.sin(T), S = f[0] - u, I = f[1] - l;
    f[0] = u + S * k - I * U, f[1] = l + S * U + I * k;
  }
  function P(f, u, l, T = u) {
    const k = F(f[0], f[1], l.angleX / 30, l.angleY / 30);
    f[0] += k[0] * T, f[1] += k[1] * T, !(u <= 0) && j(f, x.pivotX, x.pivotY, -l.angleZ / 30 * x.maxRoll * u);
  }
  function L(f, u, l, T = 0, k = 1, U = 0) {
    const S = l.breath;
    f[1] -= S * (5 * k + 4 * U), f[0] += (f[0] - A.chest.cx) * 0.012 * S * T, f[0] += l.bodyAngleX / 10 * (7 + 9 * T), j(f, A.pivotX, A.pivotY, -l.bodyAngleZ / 10 * A.maxRoll * (1 - y(...A.rollBand, u)));
  }
  function Y(f, u, l, T, k, U) {
    const S = U;
    S[0] = f, S[1] = u;
    const I = k.gain;
    for (const [m, E, H] of l.strands) {
      const Q = k.strands?.[m];
      if (!Q) continue;
      const oe = H * 3, se = Math.min(2, Math.floor(oe)), me = oe - se;
      S[0] += (Q[se][0] + (Q[se + 1][0] - Q[se][0]) * me) * E * I, S[1] += (Q[se][1] + (Q[se + 1][1] - Q[se][1]) * me) * E * I;
    }
    if (S[0] += (k.bunL[0] * l.bunL + k.bunR[0] * l.bunR) * I, S[1] += (k.bunL[1] * l.bunL + k.bunR[1] * l.bunR) * I, S[1] -= T.browY * 7 * l.brow, l.brow > 0.01) {
      const m = T.browAngle * 0.12 * l.brow;
      S[1] += (f - o.face.brow.cx) * Math.sin(m);
    }
    S[1] += T.mouthOpen * 3.5 * l.jaw;
    const D = T.angleX / 30, te = T.angleY / 30;
    return S[0] += D * (8 * l.nose + 5 * l.mouth) + (f - o.face.eyeA.cx) * 0.12 * D * l.eyeA - (f - o.face.eyeB.cx) * 0.12 * D * l.eyeB - D * 9 * l.earR + D * 4 * l.earL - D * 10 * (l.bunL + l.bunR), S[1] -= te * (6 * l.nose + 3 * l.mouth), S[1] += (u - o.face.eyeA.cy) * -0.06 * Math.abs(te) * l.eyeA + (u - o.face.eyeB.cy) * -0.06 * Math.abs(te) * l.eyeB, P(S, l.head, T, l.turn), L(S, u, T, l.chest, l.breath, l.shoulder), S;
  }
  const b = o.hand, X = b?.elbow ?? [0, 0], W = b?.wrist ?? [0, 0], ne = b?.knuckle ?? [0, 0], R = b?.contact ?? [0, 0], V = b?.forearmShare ?? 0;
  function z(f, u) {
    return b ? {
      arm: 1 - y(...b.armBand, u),
      wrist: 1 - y(...b.wristBand, u),
      hand: 1 - y(...b.handBand, u),
      finger: y(...b.fingerXBand, f) * (1 - y(...b.fingerYBand, u)),
      pinBottom: y(...b.pinBand, u)
    } : { arm: 0, wrist: 0, hand: 0, finger: 0, pinBottom: 0 };
  }
  const q = (f, u, l, T) => {
    const k = f[0] - u[0], U = f[1] - u[1];
    return [u[0] + k * l - U * T, u[1] + k * T + U * l];
  }, G = (f) => Math.atan2(f[1], f[0]);
  function B(f) {
    const u = [...R];
    P(u, d(...R), f, n(...R)), L(u, R[1], f, 0, 1, 0);
    const l = [...X];
    L(l, X[1], f, 0, 0, 0);
    const k = (G([u[0] - l[0], u[1] - l[1]]) - G([R[0] - X[0], R[1] - X[1]])) * V, U = Math.cos(k), S = Math.sin(k), I = (H) => {
      const Q = q(H, X, U, S);
      return [Q[0] + l[0] - X[0], Q[1] + l[1] - X[1]];
    }, D = I(W), te = I(R), m = G([u[0] - D[0], u[1] - D[1]]) - G([te[0] - D[0], te[1] - D[1]]), E = Math.min(1.03, Math.max(0.97, Math.hypot(u[0] - D[0], u[1] - D[1]) / Math.hypot(te[0] - D[0], te[1] - D[1])));
    return { tr: I, w: D, b: m, k: E };
  }
  function Z(f, u, l, T, k, U) {
    let S = [f, u];
    S = q(S, ne, Math.cos(T.fingerTap * 0.07 * l.finger), Math.sin(T.fingerTap * 0.07 * l.finger));
    const I = -T.handAngle / 10 * 0.045 * l.wrist, D = -T.armAngle / 10 * 0.015 * l.arm;
    S = q(S, W, Math.cos(I), Math.sin(I)), S = q(S, X, Math.cos(D), Math.sin(D)), S = k.tr(S);
    const te = k.b * l.hand, m = 1 + (k.k - 1) * l.hand;
    return S = q(S, k.w, Math.cos(te) * m, Math.sin(te) * m), S[1] += (u - S[1]) * l.pinBottom, U[0] = S[0], U[1] = S[1], U;
  }
  const K = o.accessories ?? [];
  function J(f, u, l, T) {
    const k = c(f.pivot[0], f.pivot[1]);
    return Y(f.pivot[0], f.pivot[1], k, u, l, T);
  }
  return { IMG: t, EYES: i, MOUTH: C, CHEEKS: N, STRANDS: s, TASSELS: K, headWeight: d, turnWeight: n, baseWeights: c, deformBase: Y, applyHead: P, applyBody: L, handWeights: z, handFrame: B, deformHand: Z, eyePartY: _, eyePartAlpha: v, tasselAnchor: J };
}
function mt(o, t, e, a = !1) {
  const i = a ? Math.max(t, e) * 2 : 1, h = new Float32Array(o.length), g = Math.SQRT2;
  for (let M = 0; M < e; M++) for (let O = 0; O < t; O++) {
    const w = M * t + O;
    o[w] <= 3 || (h[w] = Math.min(
      O ? h[w - 1] + 1 : i,
      M ? h[w - t] + 1 : i,
      O && M ? h[w - t - 1] + g : i,
      M && O + 1 < t ? h[w - t + 1] + g : i
    ));
  }
  for (let M = e - 1; M >= 0; M--) for (let O = t - 1; O >= 0; O--) {
    const w = M * t + O;
    !o[w] || o[w] <= 3 || (h[w] = Math.min(
      h[w],
      O + 1 < t ? h[w + 1] + 1 : i,
      M + 1 < e ? h[w + t] + 1 : i,
      O && M + 1 < e ? h[w + t - 1] + g : i,
      O + 1 < t && M + 1 < e ? h[w + t + 1] + g : i
    ));
  }
  return h;
}
function Be(o, t, e) {
  return Math.exp(-(((o - e.cx) / e.rx) ** 2 + ((t - e.cy) / e.ry) ** 2));
}
function dt(o, t, e) {
  const a = ((o - e.head.cx) / e.head.rx) ** 2 + ((t - e.head.cy) / e.head.ry) ** 2;
  let i = e.head.rx * 0.8 * Math.sqrt(Math.max(0, 1 - a)) + e.body.chest.rx * 0.23 * Be(o, t, e.body.chest);
  i += e.face.nose.rx * 0.2 * Be(o, t, e.face.nose);
  for (const [h, g] of e.cheeks) i += e.head.rx * 0.012 * Be(o, t, { cx: h, cy: g, rx: e.head.rx * 0.3, ry: e.head.ry * 0.16 });
  return i;
}
function ke(o, t, e, a) {
  const i = new Float32Array(o.length), h = new Float32Array(o.length), g = (M, O, w, _, v, C) => {
    for (let N = 0; N < _; N++) {
      const x = N * C;
      let A = 0, y = 0;
      for (let d = 0; d < Math.min(a, w - 1) + 1; d++)
        A += M[x + d * v], y++;
      for (let d = 0; d < w; d++) {
        O[x + d * v] = A / y;
        const n = d + a + 1, s = d - a;
        n < w && (A += M[x + n * v], y++), s >= 0 && (A -= M[x + s * v], y--);
      }
    }
  };
  return g(o, i, t, e, 1, t), g(i, h, e, t, t, 1), h;
}
function pt(o, t, e, a) {
  const i = ke(o, e, a, 1), h = ke(o, e, a, 6), g = new Float32Array(o.length);
  for (let w = 0; w < g.length; w++) g[w] = t[w] > 128 ? i[w] - h[w] : 0;
  const M = new Float32Array(o.length * 2), O = (w, _) => g[Math.max(0, Math.min(a - 1, _)) * e + Math.max(0, Math.min(e - 1, w))];
  for (let w = 0; w < a; w++) for (let _ = 0; _ < e; _++) {
    const v = w * e + _;
    t[v] <= 128 || (M[2 * v] = Math.max(-1, Math.min(1, -(O(_ + 1, w) - O(_ - 1, w)) * 4)), M[2 * v + 1] = Math.max(-1, Math.min(1, -(O(_, w + 1) - O(_, w - 1)) * 4)));
  }
  return M;
}
function gt(o, t, e, a, i, h = !0, g) {
  const M = !!i && a[0] === 0 && a[1] === 0 && a[2] === i.image.width && a[3] === i.image.height, O = mt(o, t, e, M), w = new Float32Array(o.length), _ = a[2] / t, v = a[3] / e, C = Math.min(_, v), N = Math.min(a[2], a[3]) * 0.08;
  for (let n = 0; n < e; n++) for (let s = 0; s < t; s++) {
    const p = n * t + s;
    w[p] = (h ? Math.sqrt(O[p] * C * N) * 0.55 : 0) + (i ? dt(a[0] + (s + 0.5) * _, a[1] + (n + 0.5) * v, i) : 0);
  }
  const x = Math.max(1, Math.round(Math.min(t, e) * 0.02));
  w.set(ke(ke(w, t, e, x), t, e, x));
  const A = g ? pt(g, o, t, e) : null, y = new Uint8Array(t * e * 4), d = (n, s) => w[Math.max(0, Math.min(e - 1, s)) * t + Math.max(0, Math.min(t - 1, n))];
  for (let n = 0; n < e; n++) for (let s = 0; s < t; s++) {
    const p = -(d(s + 2, n) - d(s - 2, n)) / (4 * _), r = -(d(s, n + 2) - d(s, n - 2)) / (4 * v), c = Math.hypot(p, r, 1), F = (n * t + s) * 4, j = n * t + s;
    y[F] = Math.round((p / c * 0.5 + 0.5) * 255), y[F + 1] = Math.round((r / c * 0.5 + 0.5) * 255), y[F + 2] = Math.round(((A?.[2 * j] ?? 0) * 0.5 + 0.5) * 255), y[F + 3] = Math.round(((A?.[2 * j + 1] ?? 0) * 0.5 + 0.5) * 255);
  }
  return y;
}
const Ge = /* @__PURE__ */ new WeakMap();
function bt(o, t, e, a) {
  const i = JSON.stringify([t, e.head, e.body.chest, e.face.nose, e.cheeks, a]), h = Ge.get(o);
  if (h?.key === i) return { ...h, computed: !1, ms: 0 };
  const g = performance.now(), M = Math.min(1, 512 / Math.max(o.width, o.height)), O = Math.max(1, Math.round(o.width * M)), w = Math.max(1, Math.round(o.height * M)), _ = document.createElement("canvas");
  _.width = O, _.height = w;
  const v = _.getContext("2d", { willReadFrequently: !0 });
  v.drawImage(o, 0, 0, O, w);
  const C = v.getImageData(0, 0, O, w).data, N = new Uint8Array(O * w), x = new Float32Array(O * w);
  for (let y = 0; y < N.length; y++)
    N[y] = C[4 * y + 3], x[y] = (0.2126 * C[4 * y] + 0.7152 * C[4 * y + 1] + 0.0722 * C[4 * y + 2]) / 255;
  const A = { key: i, data: gt(N, O, w, t, e, a, a ? x : void 0), width: O, height: w };
  return Ge.set(o, A), { ...A, computed: !0, ms: performance.now() - g };
}
const be = Object.freeze({
  enabled: !1,
  x: 0.2,
  y: 0.2,
  z: 0.45,
  color: 16777215,
  strength: 0.8,
  intensity: 0.8,
  ambient: 0.4,
  mode: "soft",
  shadow: !1,
  reach: 1.2,
  ambientColor: 15659256,
  softness: 0.45,
  specular: 0.12,
  rim: 0.3,
  detail: 0.4
}), $e = {
  x: [0, 1],
  y: [0, 1],
  z: [0.1, 2],
  color: [0, 16777215],
  strength: [0, 1],
  intensity: [0, 2],
  ambient: [0, 1],
  reach: [0.2, 3],
  ambientColor: [0, 16777215],
  softness: [0, 1],
  specular: [0, 1],
  rim: [0, 1],
  detail: [0, 1]
}, yt = /* @__PURE__ */ new Set(["color", "ambientColor"]);
function xt(o) {
  if (!o || typeof o != "object" || Array.isArray(o)) return null;
  const t = o;
  if (Object.keys(t).length !== Object.keys(be).length || Object.keys(t).some((a) => !(a in be)) || ![!0, !1].includes(t.enabled) || ![!0, !1].includes(t.shadow) || !["soft", "cel"].includes(t.mode)) return null;
  const e = { ...be, enabled: t.enabled, shadow: t.shadow, mode: t.mode };
  for (const a of Object.keys($e)) {
    const i = t[a], [h, g] = $e[a];
    if (typeof i != "number" || !Number.isFinite(i) || yt.has(a) && !Number.isInteger(i)) return null;
    e[a] = Math.max(h, Math.min(g, i));
  }
  return e;
}
const Le = -0.1, At = 0.9, Mt = 1, vt = 1.06;
function Et(o, t) {
  return [(0.5 - o) * 0.12, (0.5 - t) * 0.12];
}
function wt(o, t, e, a) {
  const i = o * Math.PI / 180, h = t * Math.PI / 180, g = -e / 30 * a, M = Math.cos(i), O = Math.sin(i), w = Math.cos(h), _ = Math.sin(h), v = Math.cos(g), C = Math.sin(g);
  return [
    v * M,
    C * M,
    -O,
    v * O * _ - C * w,
    C * O * _ + v * w,
    M * _,
    v * O * w + C * _,
    C * O * w - v * _,
    M * w
  ];
}
class St {
  constructor(t, e) {
    this.gl = t, this.program = e(t, `#version 300 es
      out vec2 vUv;
      void main() { vec2 p = vec2(float((gl_VertexID << 1) & 2), float(gl_VertexID & 2)); vUv = p; gl_Position = vec4(p * 2.0 - 1.0, 0, 1); }`, `#version 300 es
      precision highp float; in vec2 vUv; out vec4 o;
      uniform sampler2D uTex; uniform vec2 uStep; uniform vec2 uShift; uniform int uPass;
      float alphaAt(vec2 p) { if (any(lessThan(p, vec2(0))) || any(greaterThan(p, vec2(1)))) return 0.0; return texture(uTex, p).a; }
      void main() {
        if (uPass == 2) { o = texture(uTex, vUv); return; }
        vec2 p = vUv - uShift;
        float a = alphaAt(p) * 0.227027;
        a += (alphaAt(p + uStep * 1.384615) + alphaAt(p - uStep * 1.384615)) * 0.316216;
        a += (alphaAt(p + uStep * 3.230769) + alphaAt(p - uStep * 3.230769)) * 0.070270;
        o = uPass == 0 ? vec4(0, 0, 0, a) : vec4(vec3(0.035, 0.045, 0.065) * a * 0.28, a * 0.28);
      }`), this.vao = t.createVertexArray(), this.targets = [];
  }
  target(t, e) {
    const a = this.gl, i = a.createTexture(), h = a.createFramebuffer();
    if (a.bindTexture(a.TEXTURE_2D, i), a.texImage2D(a.TEXTURE_2D, 0, a.RGBA, t, e, 0, a.RGBA, a.UNSIGNED_BYTE, null), a.texParameteri(a.TEXTURE_2D, a.TEXTURE_MIN_FILTER, a.LINEAR), a.texParameteri(a.TEXTURE_2D, a.TEXTURE_MAG_FILTER, a.LINEAR), a.texParameteri(a.TEXTURE_2D, a.TEXTURE_WRAP_S, a.CLAMP_TO_EDGE), a.texParameteri(a.TEXTURE_2D, a.TEXTURE_WRAP_T, a.CLAMP_TO_EDGE), a.bindFramebuffer(a.FRAMEBUFFER, h), a.framebufferTexture2D(a.FRAMEBUFFER, a.COLOR_ATTACHMENT0, a.TEXTURE_2D, i, 0), a.checkFramebufferStatus(a.FRAMEBUFFER) !== a.FRAMEBUFFER_COMPLETE) throw new Error("Shadow framebuffer unavailable");
    return { texture: i, framebuffer: h };
  }
  begin(t, e) {
    const a = this.gl;
    (this.width !== t || this.height !== e) && (this.clearTargets(), this.width = t, this.height = e, this.targets = [this.target(t, e), this.target(Math.ceil(t / 2), Math.ceil(e / 2))]), a.bindFramebuffer(a.FRAMEBUFFER, this.targets[0].framebuffer), a.viewport(0, 0, t, e), a.clearColor(0, 0, 0, 0), a.clear(a.COLOR_BUFFER_BIT);
  }
  composite(t) {
    const e = this.gl, { prog: a, u: i } = this.program, h = this.width, g = this.height;
    e.useProgram(a), e.bindVertexArray(this.vao), e.activeTexture(e.TEXTURE0), e.uniform1i(i.uTex, 0), e.disable(e.BLEND), e.bindFramebuffer(e.FRAMEBUFFER, this.targets[1].framebuffer), e.viewport(0, 0, Math.ceil(h / 2), Math.ceil(g / 2)), e.bindTexture(e.TEXTURE_2D, this.targets[0].texture), e.uniform1i(i.uPass, 0), e.uniform2f(i.uShift, 0, 0), e.uniform2f(i.uStep, 3 / h, 0), e.drawArrays(e.TRIANGLES, 0, 3), e.bindFramebuffer(e.FRAMEBUFFER, null), e.viewport(0, 0, h, g), e.clearColor(0, 0, 0, 0), e.clear(e.COLOR_BUFFER_BIT), e.enable(e.BLEND), e.bindTexture(e.TEXTURE_2D, this.targets[1].texture);
    const M = Et(t.x, t.y);
    e.uniform1i(i.uPass, 1), e.uniform2f(i.uShift, M[0], -M[1]), e.uniform2f(i.uStep, 0, 3 / g), e.drawArrays(e.TRIANGLES, 0, 3), e.bindTexture(e.TEXTURE_2D, this.targets[0].texture), e.uniform1i(i.uPass, 2), e.drawArrays(e.TRIANGLES, 0, 3), e.bindVertexArray(null);
  }
  clearTargets() {
    for (const t of this.targets)
      this.gl.deleteTexture(t.texture), this.gl.deleteFramebuffer(t.framebuffer);
    this.targets = [];
  }
  destroy() {
    this.clearTargets(), this.gl.deleteProgram(this.program.prog), this.gl.deleteVertexArray(this.vao);
  }
}
function Tt(o, t) {
  const { IMG: e, EYES: a, MOUTH: i, CHEEKS: h } = o, g = `#version 300 es
  in vec2 aPos; in vec2 aUv;
  uniform vec2 uScale; uniform vec2 uOffset;
  out vec2 vUv;
  void main() { vUv = aUv; gl_Position = vec4(aPos * uScale + uOffset, 0.0, 1.0); }`, M = `#version 300 es
  precision highp float;
  in vec2 vUv; out vec4 outColor;
  uniform sampler2D uTex;
  uniform vec4 uRect;        // layer rect in source px
  uniform int uFace;
  uniform float uAlpha;
  uniform vec4 uEyeBox[2];   // x0, x1, -, -
  uniform float uEyeTop[48]; // 2 eyes x EYE_N samples
  uniform float uEyeBot[48];
  uniform vec4 uEyeState[2]; // open, smile, ballX(px), ballY(px)
  uniform vec4 uMouth;       // cx, cy, angle, halfLen
  uniform vec4 uMouthState;  // open, form, bow, -
  uniform vec4 uCheeks;      // x0, y0, x1, y1
  uniform float uCheek;

  const int EYE_N = 24;
  float crv(int e, bool top, float u) {
    float f = clamp(u, 0.0, 1.0) * float(EYE_N - 1);
    int i = min(int(floor(f)), EYE_N - 2);
    float t = f - float(i);
    int k = e * EYE_N + i;
    return top ? mix(uEyeTop[k], uEyeTop[k + 1], t) : mix(uEyeBot[k], uEyeBot[k + 1], t);
  }

  // Upper lid line and lower lid line of eye e at column u, for the current open/smile state.
  // Must match eyeLids() in rig.js, which moves the lash meshes to the same lines.
  // Must match eyeLidsRaw() / eyeLids() in rig.js.
  vec2 eyeLidsRaw(int e, float u) {
    u = clamp(u, 0.0, 1.0);
    vec4 st = uEyeState[e];
    float top = crv(e, true, u), bot = crv(e, false, u);
    float b = 1.0 - st.x, smile = st.y, hump = 4.0 * u * (1.0 - u);
    float H = crv(e, false, 0.5) - crv(e, true, 0.5);
    float arc = mix(uEyeTop[e * EYE_N], uEyeTop[e * EYE_N + EYE_N - 1], u) - 0.3 * H * hump;
    float closed = max(top, bot + 1.0 + (arc - bot - 1.0) * smile);
    return vec2((closed - top) * max(b, -0.07), b > 0.0 ? (closed - bot) * b * smile : 0.0);
  }

  vec2 eyeLids(int e, float u, float top, float bot) {
    vec4 box = uEyeBox[e];
    float du = 5.0 / (box.y - box.x);
    vec2 raw = eyeLidsRaw(e, u);
    vec2 d = (eyeLidsRaw(e, u - 2.0 * du) + 2.0 * eyeLidsRaw(e, u - du) + 3.0 * raw
            + 2.0 * eyeLidsRaw(e, u + du) + eyeLidsRaw(e, u + 2.0 * du)) / 9.0;
    // for hiding the ball take whichever closes more: the smoothed lash can sit a little
    // above the raw lid near the corners, and the gap must show lid skin, not eye white
    return vec2(top + max(d.x, raw.x), bot + min(d.y, raw.y));
  }

  vec4 texAt(vec2 p) { return texture(uTex, (p - uRect.xy) / uRect.zw); }

  // Eye white + iris layer: shown only between the lids (the lids cover it, it never squashes);
  // the iris slides inside the opening for the gaze.
  vec4 eyeBall(int e, vec2 p) {
    vec4 box = uEyeBox[e]; vec4 st = uEyeState[e];
    float u = clamp((p.x - box.x) / (box.y - box.x), 0.0, 1.0);
    float top = crv(e, true, u), bot = crv(e, false, u);
    vec2 lids = eyeLids(e, u, top, bot);
    float v = clamp((p.y - top) / max(bot - top, 1.0), 0.0, 1.0);
    float w = sqrt(4.0 * u * (1.0 - u)) * sqrt(4.0 * v * (1.0 - v));
    vec4 c = texAt(p - vec2(st.z, st.w) * w);
      // the lash covers ~2px of the ball's upper edge, so the cut can sit under it (no seam)
    return c * smoothstep(lids.x - 1.0, lids.x + 0.5, p.y) * (1.0 - smoothstep(lids.y - 0.9, lids.y + 0.6, p.y));
  }

  vec4 mouth(vec2 p, vec4 base) {
    float open = uMouthState.x;
    if (open < 0.01) return base;
    vec2 d = vec2(cos(uMouth.z), sin(uMouth.z)), n = vec2(-d.y, d.x);
    vec2 r = p - uMouth.xy;
    float s = dot(r, d) / uMouth.w, t = dot(r, n);
    float form = uMouthState.y;                       // -1 wide "i" .. +1 round "o"
    float wf = mix(0.78, 0.46, clamp(form * 0.5 + 0.5, 0.0, 1.0));
    float k = 1.0 - (s / wf) * (s / wf);
    if (k <= 0.0) return base;
    float line = uMouthState.z * (1.0 - s * s);
    float hk = pow(k, mix(0.55, 0.85, clamp(form, 0.0, 1.0)));
    float H = mix(20.0, 26.0, clamp(form, 0.0, 1.0));
    float up = line - 0.6 - open * 2.5 * hk;
    float lo = line + open * H * hk;
    float cov = smoothstep(-0.7, 0.7, t - up) * smoothstep(-0.7, 0.7, lo - t);
    if (cov <= 0.0) return base;
    float tv = clamp((t - up) / max(lo - up, 1.0), 0.0, 1.0);
    vec3 col = mix(vec3(0.24, 0.05, 0.08), vec3(0.48, 0.15, 0.19), tv);
    float tongue = smoothstep(0.5, 0.78, tv) * (1.0 - smoothstep(0.45, 0.8, abs(s) / wf));
    col = mix(col, vec3(0.86, 0.44, 0.47), tongue * 0.9);
    float teeth = (1.0 - smoothstep(0.12, 0.22, tv)) * smoothstep(0.25, 0.45, open) * (1.0 - smoothstep(0.55, 0.85, abs(s) / wf));
    col = mix(col, vec3(0.99, 0.96, 0.94), teeth);
    float rim = 1.0 - smoothstep(0.6, 1.8, lo - t);
    col = mix(col, vec3(0.36, 0.09, 0.11), rim * 0.85);
    return vec4(mix(base.rgb, col, cov), 1.0);
  }

  void main() {
    vec2 p = uRect.xy + vUv * uRect.zw;
    vec4 c;
    if (uFace == 1) {
      c = mouth(p, texAt(p));
      float blush = exp(-dot((p - uCheeks.xy) / vec2(48.0, 22.0), (p - uCheeks.xy) / vec2(48.0, 22.0)))
                  + exp(-dot((p - uCheeks.zw) / vec2(40.0, 20.0), (p - uCheeks.zw) / vec2(40.0, 20.0)));
      c.rgb = mix(c.rgb, c.rgb * vec3(1.0, 0.62, 0.64) , clamp(blush * uCheek * 0.55, 0.0, 1.0) * c.a);
    } else if (uFace >= 2) {
      c = eyeBall(uFace - 2, p);
    } else {
      c = texAt(p);
    }
    outColor = c * uAlpha;
  }`, O = g.replace("out vec2 vUv;", "in float aHeadWeight; out float vHeadWeight; out vec2 vScreen; out vec2 vUv;").replace("vUv = aUv;", "vHeadWeight = aHeadWeight; vScreen = vec2((aPos.x * uScale.x + uOffset.x + 1.0) * 0.5, (1.0 - aPos.y * uScale.y - uOffset.y) * 0.5); vUv = aUv;"), w = M.replace("uniform sampler2D uTex;", `uniform sampler2D uTex;
    uniform sampler2D uNormal; in float vHeadWeight; in vec2 vScreen;
    uniform mat3 uHeadRotation; uniform vec3 uLight; uniform vec3 uLightColor; uniform vec3 uAmbientColor;
    uniform vec4 uLighting; uniform vec4 uSurface; uniform float uAspect; uniform int uCel;`).replace("outColor = c * uAlpha;", `
      // RG hold the smooth surface normal, BA the painting's relief (see lighting/normals.ts).
      vec4 encoded = texture(uNormal, vUv);
      vec2 base = encoded.rg * 2.0 - 1.0;
      vec3 n = vec3(base, sqrt(max(0.0, 1.0 - dot(base, base))));
      n = normalize(n + vec3((encoded.ba * 2.0 - 1.0) * uSurface.w * ${At.toFixed(3)}, 0.0));
      n = normalize(mix(n, uHeadRotation * n, vHeadWeight));
      vec2 toLight = (uLight.xy - vScreen) * vec2(uAspect, 1.0);
      vec3 light = normalize(vec3(toLight, uLight.z));
      float ndl = dot(n, light);
      float diffuse;
      if (uCel == 1) {
        float w = 0.01 + uSurface.x * 0.08;
        diffuse = 0.2 + 0.45 * smoothstep(${Le.toFixed(3)} - w, ${Le.toFixed(3)} + w, ndl) + 0.35 * smoothstep(0.55 - w, 0.55 + w, ndl);
      } else {
        float s = 0.05 + uSurface.x * 0.5;
        diffuse = smoothstep(${Le.toFixed(3)} - s, ${Le.toFixed(3)} + s, ndl) * (0.35 + 0.65 * max(0.0, ndl));
      }
      float reach = dot(toLight, toLight) / (uLighting.w * uLighting.w);
      float attenuation = 1.0 / (1.0 + reach);
      vec3 radiance = uLightColor * uLighting.y * attenuation;
      // A light close to the surface may brighten a little, but must not bleach painted colours.
      vec3 irradiance = min(uAmbientColor * uLighting.z + radiance * diffuse, vec3(${vt.toFixed(3)}));
      // Painted shadows are deeper versions of the base colour, not grey: multiply by the colour
      // itself as the surface turns away from the light.
      vec3 albedo = c.rgb / max(c.a, 1e-4);
      float dark = 1.0 - clamp(dot(irradiance, vec3(0.3333)), 0.0, 1.0);
      vec3 shaded = c.rgb * mix(vec3(1.0), albedo, dark * ${Mt.toFixed(3)}) * irradiance;
      float specular = pow(max(dot(n, normalize(light + vec3(0.0, 0.0, 1.0))), 0.0), 60.0) * uSurface.y;
      if (uCel == 1) specular = smoothstep(0.3, 0.35, specular) * uSurface.y;
      vec2 side = length(n.xy) > 0.001 ? normalize(n.xy) : vec2(0.0);
      float rim = pow(1.0 - max(n.z, 0.0), 4.0) * smoothstep(-0.2, 0.7, dot(side, normalize(toLight + vec2(1e-4)))) * uSurface.z;
      shaded += radiance * (specular * max(0.0, ndl) + rim) * c.a;
      // Strength blends between the original painting and the relit result; alpha is unchanged.
      c.rgb = clamp(mix(c.rgb, shaded, uLighting.x), vec3(0.0), vec3(c.a));
      outColor = c * uAlpha;`), _ = `#version 300 es
  in vec2 aPos; uniform vec2 uScale; uniform vec2 uOffset;
  void main() { gl_Position = vec4(aPos * uScale + uOffset, 0.0, 1.0); gl_PointSize = 7.0; }`, v = `#version 300 es
  precision mediump float; uniform vec4 uColor; out vec4 o; void main() { o = uColor; }`;
  function C(y, d, n) {
    const s = y.createProgram();
    for (const [c, F] of [[y.VERTEX_SHADER, d], [y.FRAGMENT_SHADER, n]]) {
      const j = y.createShader(c);
      if (y.shaderSource(j, F), y.compileShader(j), !y.getShaderParameter(j, y.COMPILE_STATUS)) throw new Error(y.getShaderInfoLog(j));
      y.attachShader(s, j), y.deleteShader(j);
    }
    if (y.bindAttribLocation(s, 0, "aPos"), y.bindAttribLocation(s, 1, "aUv"), y.bindAttribLocation(s, 2, "aHeadWeight"), y.linkProgram(s), !y.getProgramParameter(s, y.LINK_STATUS)) throw new Error(y.getProgramInfoLog(s));
    const p = {}, r = y.getProgramParameter(s, y.ACTIVE_UNIFORMS);
    for (let c = 0; c < r; c++) {
      const F = y.getActiveUniform(s, c).name.replace("[0]", "");
      p[F] = y.getUniformLocation(s, F);
    }
    return { prog: s, u: p };
  }
  function N(y, d, n, s) {
    const p = [y];
    let r = y;
    for (; r < y + d - 0.5; ) {
      const c = s && r >= s.from && r < s.to ? s.cell : n;
      r = Math.min(y + d, r + c), p.push(r);
    }
    return p;
  }
  function x(y, d, n, s, p = null) {
    const [r, c, F, j] = y, P = N(r, F, d, p && { from: p.x0, to: p.x1, cell: p.cell }), L = N(c, j, d, p && { from: p.y0, to: p.y1, cell: p.cell }), Y = P.length - 1, b = L.length - 1, X = (Y + 1) * (b + 1), W = new Float32Array(X * 2), ne = new Float32Array(X * 2);
    for (let G = 0; G <= b; G++) for (let B = 0; B <= Y; B++) {
      const Z = G * (Y + 1) + B;
      W[Z * 2] = P[B], W[Z * 2 + 1] = L[G], ne[Z * 2] = (P[B] - r) / F, ne[Z * 2 + 1] = (L[G] - c) / j;
    }
    const R = [], V = [], z = n.length / s, q = s === 1 ? 0 : 1;
    for (let G = 0; G < b; G++) for (let B = 0; B < Y; B++) {
      const Z = Math.floor(P[B] - r) * q - 2, K = Math.ceil(P[B + 1] - r) * q + 2, J = Math.floor(L[G] - c) * q - 2, f = Math.ceil(L[G + 1] - c) * q + 2;
      let u = !1;
      for (let S = Math.max(0, J); S < Math.min(z, f) && !u; S += 1)
        for (let I = Math.max(0, Z); I < Math.min(s, K); I += 1)
          if (n[S * s + I] > 3) {
            u = !0;
            break;
          }
      if (!u) continue;
      const l = G * (Y + 1) + B, T = l + 1, k = l + Y + 1, U = k + 1;
      R.push(l, T, k, T, U, k), V.push(l, T, l, k, T, k), B === Y - 1 && V.push(T, U), G === b - 1 && V.push(k, U);
    }
    return { rect: y, cols: Y, rows: b, rest: W, uv: ne, pos: new Float32Array(W), tris: new Uint32Array(R), lines: new Uint32Array(V) };
  }
  class A {
    // padTop / padSide: margin around the image, as a share of its height / width. A negative
    // padTop pushes the top of the image above the canvas (hides a cut-off top edge).
    constructor(d, { padTop: n = 0, padSide: s = 0, fit: p = "contain" } = {}) {
      this.pad = { top: n, side: s }, this.fit = p;
      const r = d.getContext("webgl2", { premultipliedAlpha: !0, antialias: !0, alpha: !0, preserveDrawingBuffer: !0 });
      if (!r) throw new Error("WebGL2 is not available");
      this.gl = r, this.canvas = d, this.main = C(r, g, M), this.line = C(r, _, v), this.layers = [], this.lighting = be, this.lightingStats = { normalMs: 0, computedLayers: 0, cachedLayers: 0 }, r.enable(r.BLEND), r.blendFunc(r.ONE, r.ONE_MINUS_SRC_ALPHA);
    }
    texture(d) {
      const n = this.gl, s = n.createTexture();
      return n.bindTexture(n.TEXTURE_2D, s), n.pixelStorei(n.UNPACK_PREMULTIPLY_ALPHA_WEBGL, !0), n.texImage2D(n.TEXTURE_2D, 0, n.RGBA, n.RGBA, n.UNSIGNED_BYTE, d), n.generateMipmap(n.TEXTURE_2D), n.texParameteri(n.TEXTURE_2D, n.TEXTURE_MIN_FILTER, n.LINEAR_MIPMAP_LINEAR), n.texParameteri(n.TEXTURE_2D, n.TEXTURE_MAG_FILTER, n.LINEAR), n.texParameteri(n.TEXTURE_2D, n.TEXTURE_WRAP_S, n.CLAMP_TO_EDGE), n.texParameteri(n.TEXTURE_2D, n.TEXTURE_WRAP_T, n.CLAMP_TO_EDGE), s;
    }
    addLayer(d, n, s, p = {}) {
      const r = this.gl, c = r.createVertexArray();
      r.bindVertexArray(c);
      const F = r.createBuffer();
      r.bindBuffer(r.ARRAY_BUFFER, F), r.bufferData(r.ARRAY_BUFFER, s.pos, r.DYNAMIC_DRAW);
      for (const X of [this.main, this.line]) {
        const W = r.getAttribLocation(X.prog, "aPos");
        r.enableVertexAttribArray(W), r.vertexAttribPointer(W, 2, r.FLOAT, !1, 0, 0);
      }
      const j = r.createBuffer();
      r.bindBuffer(r.ARRAY_BUFFER, j), r.bufferData(r.ARRAY_BUFFER, s.uv, r.STATIC_DRAW);
      const P = r.getAttribLocation(this.main.prog, "aUv");
      r.enableVertexAttribArray(P), r.vertexAttribPointer(P, 2, r.FLOAT, !1, 0, 0);
      const L = r.createBuffer();
      r.bindBuffer(r.ELEMENT_ARRAY_BUFFER, L), r.bufferData(r.ELEMENT_ARRAY_BUFFER, s.tris, r.STATIC_DRAW), r.bindVertexArray(null);
      const Y = r.createBuffer();
      r.bindBuffer(r.ELEMENT_ARRAY_BUFFER, Y), r.bufferData(r.ELEMENT_ARRAY_BUFFER, s.lines, r.STATIC_DRAW);
      const b = { name: d, image: n, mesh: s, tex: this.texture(n), vao: c, posBuf: F, uvBuf: j, triBuf: L, lineBuf: Y, visible: !0, face: !!p.face, eyeBall: p.eyeBall, color: p.color || [1, 1, 1, 1] };
      return this.layers.push(b), b;
    }
    destroy() {
      const d = this.gl;
      for (const n of this.layers) {
        d.deleteTexture(n.tex), n.normal && d.deleteTexture(n.normal), n.headBuf && d.deleteBuffer(n.headBuf), d.deleteVertexArray(n.vao);
        for (const s of [n.posBuf, n.uvBuf, n.triBuf, n.lineBuf]) d.deleteBuffer(s);
      }
      d.deleteProgram(this.main.prog), d.deleteProgram(this.line.prog), this.lit && d.deleteProgram(this.lit.prog), this.shadow?.destroy(), this.layers.length = 0;
    }
    setLighting(d) {
      if (this.lighting = xt({ ...be, ...d }) ?? be, !this.lighting.enabled) return;
      const n = this.gl;
      this.lit || (this.lit = C(n, O, w));
      for (const s of this.layers) {
        if (s.normal || s.overlay) continue;
        const p = bt(s.image, s.mesh.rect, t, !/^(eye|mouth)/.test(s.name));
        this.lightingStats.normalMs += p.ms, this.lightingStats[p.computed ? "computedLayers" : "cachedLayers"]++, s.normal = n.createTexture(), n.activeTexture(n.TEXTURE0), n.bindTexture(n.TEXTURE_2D, s.normal), n.pixelStorei(n.UNPACK_PREMULTIPLY_ALPHA_WEBGL, !1), n.texImage2D(n.TEXTURE_2D, 0, n.RGBA, p.width, p.height, 0, n.RGBA, n.UNSIGNED_BYTE, p.data), n.generateMipmap(n.TEXTURE_2D), n.texParameteri(n.TEXTURE_2D, n.TEXTURE_MIN_FILTER, n.LINEAR_MIPMAP_LINEAR), n.texParameteri(n.TEXTURE_2D, n.TEXTURE_MAG_FILTER, n.LINEAR), n.texParameteri(n.TEXTURE_2D, n.TEXTURE_WRAP_S, n.CLAMP_TO_EDGE), n.texParameteri(n.TEXTURE_2D, n.TEXTURE_WRAP_T, n.CLAMP_TO_EDGE);
        const r = new Float32Array(s.mesh.rest.length / 2);
        for (let c = 0; c < r.length; c++) r[c] = o.headWeight(s.mesh.rest[c * 2], s.mesh.rest[c * 2 + 1]);
        s.headBuf = n.createBuffer(), n.bindVertexArray(s.vao), n.bindBuffer(n.ARRAY_BUFFER, s.headBuf), n.bufferData(n.ARRAY_BUFFER, r, n.STATIC_DRAW), n.enableVertexAttribArray(2), n.vertexAttribPointer(2, 1, n.FLOAT, !1, 0, 0);
      }
      n.bindVertexArray(null), this.lighting.shadow && !this.shadow && (this.shadow = new St(n, C));
    }
    resize() {
      const d = this.canvas, n = Math.min(window.devicePixelRatio || 1, 2), s = Math.round(d.clientWidth * n), p = Math.round(d.clientHeight * n);
      (d.width !== s || d.height !== p) && (d.width = s, d.height = p);
      const r = (this.fit === "cover" ? Math.max : Math.min)(s / (e.w * (1 + 2 * this.pad.side)), p / (e.h * (1 + this.pad.top))), c = (s - e.w * r) / 2, F = (p - e.h * r) / (this.fit === "cover" ? 2 : 1);
      this.scale = [2 * r / s, -2 * r / p], this.offset = [-1 + 2 * c / s, 1 - 2 * F / p], this.pxScale = r, this.pxOff = [c, F];
    }
    draw(d) {
      const n = this.gl;
      this.resize(), n.viewport(0, 0, this.canvas.width, this.canvas.height), n.clearColor(0, 0, 0, 0), n.clear(n.COLOR_BUFFER_BIT);
      const s = this.lighting.enabled, p = s && this.lighting.shadow;
      p && this.shadow.begin(this.canvas.width, this.canvas.height);
      const r = s ? this.lit : this.main;
      if (this.current = r, n.useProgram(r.prog), s) {
        const c = this.lighting;
        n.uniform1i(r.u.uNormal, 1), n.uniform3f(r.u.uLight, c.x, c.y, c.z), n.uniform3f(r.u.uLightColor, (c.color >> 16 & 255) / 255, (c.color >> 8 & 255) / 255, (c.color & 255) / 255), n.uniform3f(r.u.uAmbientColor, (c.ambientColor >> 16 & 255) / 255, (c.ambientColor >> 8 & 255) / 255, (c.ambientColor & 255) / 255), n.uniform4f(r.u.uLighting, c.strength, c.intensity, c.ambient, c.reach), n.uniform4f(r.u.uSurface, c.softness, c.specular, c.rim, c.detail), n.uniform1f(r.u.uAspect, this.canvas.width / this.canvas.height), n.uniform1i(r.u.uCel, c.mode === "cel" ? 1 : 0), n.uniformMatrix3fv(r.u.uHeadRotation, !1, wt(d.angleX ?? 0, d.angleY ?? 0, d.angleZ ?? 0, t.head.maxRoll));
      }
      n.uniform2fv(r.u.uScale, this.scale), n.uniform2fv(r.u.uOffset, this.offset), n.uniform1i(r.u.uTex, 0), n.uniform4fv(r.u.uEyeBox, a.flatMap((c) => [c.x0, c.x1, 0, 0])), n.uniform1fv(r.u.uEyeTop, a.flatMap((c) => c.top)), n.uniform1fv(r.u.uEyeBot, a.flatMap((c) => c.bot)), n.uniform4fv(r.u.uEyeState, d.eyes), n.uniform4f(r.u.uMouth, i.cx, i.cy, i.angle, i.halfLen), n.uniform4f(r.u.uMouthState, d.mouthOpen, d.mouthForm, i.bow, 0), n.uniform4f(r.u.uCheeks, h[0][0], h[0][1], h[1][0], h[1][1]), n.uniform1f(r.u.uCheek, d.cheek), n.activeTexture(n.TEXTURE0);
      for (const c of this.layers)
        !c.visible || c.overlay || this.drawLayer(c, c.alpha ?? 1);
      if (this.original && d.originalAlpha > 0 && this.drawLayer(this.original, d.originalAlpha), p && this.shadow.composite(this.lighting), d.showMesh) {
        const c = this.line;
        n.useProgram(c.prog), n.uniform2fv(c.u.uScale, this.scale), n.uniform2fv(c.u.uOffset, this.offset);
        for (const F of this.layers)
          !F.visible || F.overlay || (n.bindVertexArray(F.vao), n.bindBuffer(n.ELEMENT_ARRAY_BUFFER, F.lineBuf), n.uniform4fv(c.u.uColor, F.color), n.drawElements(n.LINES, F.mesh.lines.length, n.UNSIGNED_INT, 0), n.bindBuffer(n.ELEMENT_ARRAY_BUFFER, F.triBuf));
        d.joints?.length && this.drawPoints(d.joints), n.bindVertexArray(null);
      }
    }
    drawLayer(d, n) {
      const s = this.gl, p = this.current;
      s.useProgram(p.prog), s.bindVertexArray(d.vao), s.bindBuffer(s.ARRAY_BUFFER, d.posBuf), s.bufferSubData(s.ARRAY_BUFFER, 0, d.mesh.pos), this.lighting.enabled && (s.activeTexture(s.TEXTURE1), s.bindTexture(s.TEXTURE_2D, d.normal), s.activeTexture(s.TEXTURE0)), s.bindTexture(s.TEXTURE_2D, d.tex), s.uniform4fv(p.u.uRect, d.mesh.rect), s.uniform1i(p.u.uFace, d.eyeBall !== void 0 ? 2 + d.eyeBall : d.face ? 1 : 0), s.uniform1f(p.u.uAlpha, n), s.drawElements(s.TRIANGLES, d.mesh.tris.length, s.UNSIGNED_INT, 0);
    }
    drawPoints(d) {
      const n = this.gl, s = this.line;
      if (!this.pointBuf) {
        this.pointBuf = n.createBuffer(), this.pointVao = n.createVertexArray(), n.bindVertexArray(this.pointVao), n.bindBuffer(n.ARRAY_BUFFER, this.pointBuf);
        const p = n.getAttribLocation(s.prog, "aPos");
        n.enableVertexAttribArray(p), n.vertexAttribPointer(p, 2, n.FLOAT, !1, 0, 0);
      }
      n.bindVertexArray(this.pointVao), n.bindBuffer(n.ARRAY_BUFFER, this.pointBuf), n.bufferData(n.ARRAY_BUFFER, new Float32Array(d.flat()), n.DYNAMIC_DRAW), n.uniform4f(s.u.uColor, 1, 0.85, 0.2, 1), n.drawArrays(n.POINTS, 0, d.length);
    }
    // canvas CSS px -> source image px
    toImage(d, n) {
      if (!this.pxOff) return null;
      const s = this.canvas.width / this.canvas.clientWidth;
      return [(d * s - this.pxOff[0]) / this.pxScale, (n * s - this.pxOff[1]) / this.pxScale];
    }
  }
  return { Renderer: A, buildGrid: x };
}
function Rt(o, t) {
  const { applyHead: e, applyBody: a, TASSELS: i, tasselAnchor: h } = o, g = (t.strands ?? []).map((n) => {
    if (n.nodes.length === 4) return n;
    const s = Array.from({ length: 4 }, (p, r) => {
      const c = r / 3 * (n.nodes.length - 1), F = Math.min(n.nodes.length - 2, Math.floor(c)), j = c - F;
      return [0, 1].map((P) => n.nodes[F][P] + (n.nodes[F + 1][P] - n.nodes[F][P]) * j);
    });
    return { ...n, nodes: s };
  }), M = [0, 300, 200, 140], O = 0.9, w = 7, _ = { stiff: 1.7, damp: 1.6, couple: 0.85, reach: 0.9, bind: 4 }, v = Math.min(6, g.filter((n) => n.name.startsWith("bang")).length), C = { freq: 0.7, zeta: 0.22, hang: 0.85, inertia: 0.32, wind: 0.03, max: 0.55, smooth: 6 }, N = (n, s) => [n[0] * Math.cos(s) - n[1] * Math.sin(s), n[0] * Math.sin(s) + n[1] * Math.cos(s)], x = (n, s) => {
    const p = Math.hypot(n[0], n[1]);
    if (p < 1e-6) return n;
    const r = s * Math.tanh(p / s) / p;
    return [n[0] * r, n[1] * r];
  }, A = Object.fromEntries(Object.entries(t.buns ?? {}).map(([n, s]) => [n, { at: [s.cx, s.cy], k: 260, c: 11, hang: 3, max: 4 }])), y = (n, s) => {
    const p = Math.hypot(n[0], n[1]);
    p > s && (n[0] *= s / p, n[1] *= s / p);
  };
  class d {
    constructor() {
      this.gain = 1, this.out = { gain: 1, bunL: [0, 0], bunR: [0, 0] }, this.hair = {};
      for (const s of Object.keys(A))
        this.hair[s] = { p: null, v: [0, 0] }, this.out[s] = [0, 0];
      this.strands = g.map(() => ({ p: null, v: [[0, 0], [0, 0], [0, 0], [0, 0]] })), this.out.strands = g.map(() => [[0, 0], [0, 0], [0, 0], [0, 0]]), this.chains = i.map((s) => {
        const p = s.tip[0] - s.pivot[0], r = s.tip[1] - s.pivot[1], c = Math.hypot(p, r), F = [p / c, r / c];
        return { t: s, dir: F, L1: c * s.split, L2: c * (1 - s.split), pts: null, prev: null, phi: [0, 0], anchor: [0, 0] };
      }), this.time = 0;
    }
    hairAnchor(s, p) {
      const r = [s[0], s[1]];
      return e(r, 1, p), a(r, s[1], p), r;
    }
    step(s, p) {
      const r = Math.max(1, Math.ceil(p / 0.004166666666666667)), c = Math.min(p, 0.05) / r, F = -s.angleZ / 30 * t.head.maxRoll - s.bodyAngleZ / 10 * t.body.maxRoll, j = this.gain;
      g.forEach((L, Y) => {
        const b = this.strands[Y], X = this.out.strands[Y], W = L.nodes.map((R) => this.hairAnchor(R, s));
        b.p || (b.p = W.map((R) => [...R]));
        const ne = Y * 1.7;
        for (let R = 0; R < r; R++) {
          const V = this.time + R * c;
          for (let z = 1; z < 4; z++) {
            const q = Math.hypot(L.nodes[z][0] - L.nodes[0][0], L.nodes[z][1] - L.nodes[0][1]), G = (Math.sin(V * 1.3) * 0.5 + Math.sin(V * 3.1) * 0.3 + Math.sin(V * 4.7 + ne) * 0.2) * L.max * 0.1 * z / 3, B = [b.p[z - 1][0] - W[z - 1][0], b.p[z - 1][1] - W[z - 1][1]], Z = W[z][0] + B[0] * O * _.couple - Math.sin(F) * q * 0.12 + G, K = W[z][1] + B[1] * O * _.couple, J = M[z] * L.k * _.stiff / Math.max(0.35, j), f = w * _.damp * Math.sqrt(_.stiff) / Math.max(0.5, Math.sqrt(j)), u = b.v[z], l = b.p[z];
            u[0] += (J * (Z - l[0]) - f * u[0]) * c, u[1] += (J * (K - l[1]) - f * u[1]) * c, l[0] += u[0] * c, l[1] += u[1] * c;
          }
          b.p[0] = [...W[0]];
        }
        for (let R = 0; R < 4; R++) {
          const V = [b.p[R][0] - W[R][0], b.p[R][1] - W[R][1]];
          X[R] = x(V, Math.max(0.5, L.max * _.reach * Math.max(1, j) * R / 3));
        }
      });
      for (const [L, Y] of Object.entries(A)) {
        const b = this.hair[L], X = this.hairAnchor(Y.at, s), W = Math.sin(this.time * 1.3 + Y.at[0] * 0.01) * 0.6 + Math.sin(this.time * 2.9 + Y.at[1] * 0.02) * 0.4, ne = X[0] - Math.sin(F) * Y.hang + W * Y.max * 0.12, R = X[1];
        b.p || (b.p = [ne, R]);
        const V = Y.k / Math.max(0.35, j), z = Y.c / Math.max(0.5, Math.sqrt(j));
        for (let G = 0; G < r; G++)
          b.v[0] += (V * (ne - b.p[0]) - z * b.v[0]) * c, b.v[1] += (V * (R - b.p[1]) - z * b.v[1]) * c, b.p[0] += b.v[0] * c, b.p[1] += b.v[1] * c;
        const q = [b.p[0] - X[0], b.p[1] - X[1]];
        y(q, Y.max * Math.max(1, j)), this.out[L] = q;
      }
      this.out.gain = 1;
      const P = this.out.strands;
      for (let L = 0; L < _.bind; L++) for (let Y = 1; Y < 4; Y++) {
        const b = P.slice(0, v).map((X) => [...X[Y]]);
        for (let X = 0; X < v; X++) {
          const W = b[Math.max(0, X - 1)], ne = b[Math.min(v - 1, X + 1)];
          for (const R of [0, 1]) P[X][Y][R] = b[X][R] * 0.5 + (W[R] + ne[R]) * 0.25;
        }
      }
      for (const L of this.chains) {
        const Y = h(L.t, s, this.out, [0, 0]);
        L.st || (L.st = { th: [0, 0], w: [0, 0], pos: [...Y], vel: [0, 0], acc: [0, 0] });
        const b = L.st, X = C, W = [(Y[0] - b.pos[0]) / Math.max(p, 1e-3), (Y[1] - b.pos[1]) / Math.max(p, 1e-3)], ne = 1 - Math.exp(-p * X.smooth), R = [(W[0] - b.vel[0]) / Math.max(p, 1e-3), (W[1] - b.vel[1]) / Math.max(p, 1e-3)];
        b.acc = [b.acc[0] + (R[0] - b.acc[0]) * ne, b.acc[1] + (R[1] - b.acc[1]) * ne], b.vel = [b.vel[0] + (W[0] - b.vel[0]) * ne, b.vel[1] + (W[1] - b.vel[1]) * ne], b.pos = [...Y];
        const V = [-L.dir[1], L.dir[0]], z = -(b.acc[0] * V[0] + b.acc[1] * V[1]) / (L.L1 + L.L2) * X.inertia, q = (Math.sin(this.time * 0.9 + L.t.pivot[0]) * 0.6 + Math.sin(this.time * 0.37 + L.t.pivot[1]) * 0.4) * X.wind, G = -F * X.hang + q, B = 2 * Math.PI * X.freq / Math.sqrt(Math.max(0.4, j)), Z = B * 1.35;
        for (let u = 0; u < r; u++) {
          const l = -B * B * (b.th[0] - G) - 2 * X.zeta * B * b.w[0] + z;
          b.w[0] += l * c, b.th[0] += b.w[0] * c;
          const T = -Z * Z * (b.th[1] - b.th[0]) - 2 * X.zeta * Z * b.w[1] + z * 0.4 + l * 0.5;
          b.w[1] += T * c, b.th[1] += b.w[1] * c;
        }
        b.th[0] = Math.max(-0.55, Math.min(X.max, b.th[0])), b.th[1] = Math.max(-0.55 * 1.4, Math.min(X.max * 1.4, b.th[1])), L.phi = [b.th[0], b.th[1]];
        const K = N(L.dir, b.th[0]), J = N(L.dir, b.th[1]), f = [Y[0] + K[0] * L.L1, Y[1] + K[1] * L.L1];
        L.pts = [[...Y], f, [f[0] + J[0] * L.L2, f[1] + J[1] * L.L2]], L.anchor = Y;
      }
      return this.time += p, this.out;
    }
  }
  return { Physics: d };
}
function Lt(o, t) {
  const { baseWeights: e, deformBase: a, MOUTH: i } = o, h = (p, r, c) => {
    const F = Math.min(1, Math.max(0, (c - p) / (r - p)));
    return F * F * (3 - 2 * F);
  }, g = t.mouth.area, M = {
    a: { sprite: "mouth_a", ref: 0.9, width: 1 },
    aHalf: { sprite: "mouth_a_half", ref: 0.55, width: 1 },
    i: { sprite: "mouth_i", ref: 0.55, width: 1 },
    e: { sprite: "mouth_a_half", ref: 0.65, width: 1.06 },
    o: { sprite: "mouth_o", ref: 0.75, width: 1 },
    u: { sprite: "mouth_o", ref: 0.75, width: 0.78 }
  }, O = 0.16;
  function w(p, r) {
    const F = (L, Y, b) => L >= Y - (r ? 0.07 : 0) && L < b + (r ? 0.07 : 0), j = [["i", -9, -0.55], ["e", -0.55, -0.2], ["a", -0.2, 0.35], ["o", 0.35, 0.75], ["u", 0.75, 9]], P = r && j.find((L) => L[0] === r || r === "aHalf" && L[0] === "a");
    return P && F(p, P[1], P[2]) ? P[0] : j.find((L) => p >= L[1] && p < L[2])[0];
  }
  const _ = 0.75, v = 0.3, C = 0.06;
  function N(p, r) {
    return p >= _ ? null : p < v ? r >= 0.5 ? "eyes_smile" : "eyes_closed" : "eyes_half";
  }
  function x(p, r, c) {
    return c === "open" && p >= _ - 0.05 ? "open" : c === "eyes_half" && p >= v && p < _ + 0.05 ? "eyes_half" : N(p, r) ?? "open";
  }
  function A(p, r, c = null) {
    if (p < O) return null;
    const F = w(r, c);
    return F === "a" ? p >= 0.6 ? "a" : "aHalf" : F;
  }
  function y(p) {
    return i.cy + (p - i.cx) * Math.tan(i.angle);
  }
  function d() {
    return g.cx;
  }
  function n(p, r) {
    const c = Math.cos(-g.angle), F = Math.sin(-g.angle), j = p - g.cx, P = r - g.cy, L = (j * c - P * F) / g.rx, Y = (j * F + P * c) / g.ry;
    return 1 - h(0.55, 0.95, Math.hypot(L, Y));
  }
  function s(p, r, c, F, j) {
    const P = {}, L = (R) => R.startsWith("eyes_half") ? 0 : R.startsWith("eyes_") ? 1 : 2, Y = Object.entries(r.layers).sort((R, V) => L(R[0]) - L(V[0]));
    for (const [R, V] of Y) {
      const z = F(V, t.mesh.spriteCell, j(c[R]), c[R].width), q = [], G = [];
      for (let Z = 0; Z < z.rest.length / 2; Z++) {
        const K = z.rest[Z * 2], J = z.rest[Z * 2 + 1];
        q.push(e(K, J, 0)), G.push(R.startsWith("mouth") ? n(K, J) : 0);
      }
      const B = p.addLayer(R, c[R], z, { color: [0.4, 1, 0.8, 0.6] });
      B.visible = !1, P[R] = { mesh: z, W: q, inner: G, layer: B };
    }
    const b = [0, 0];
    let X = null;
    const W = [0, 1].map(() => ({ cur: "open", prev: "open", t: 1 }));
    function ne(R, V, z, q, G = 1) {
      const B = R.mesh.rest, Z = R.mesh.pos;
      for (let K = 0; K < R.W.length; K++) {
        let J = B[K * 2], f = B[K * 2 + 1];
        const u = R.inner[K];
        if (u > 0) {
          const l = y(J);
          f = l + (f - l) * (1 + (q - 1) * u), J = d() + (J - d()) * (1 + (G - 1) * u);
        }
        a(J, f, R.W[K], V, z, b), Z[K * 2] = b[0], Z[K * 2 + 1] = b[1];
      }
    }
    return {
      /**
       * Show / hide and deform the sprites for this frame.
       * Returns which eyes are covered by a sprite, so the layered eye parts can be hidden.
       */
      update(R, V, z = 1 / 60) {
        for (const J of Object.values(P)) J.layer.visible = !1;
        const q = [!1, !1];
        [
          [R.eyeROpen, R.eyeSmile],
          [R.eyeLOpen, R.eyeSmileL ?? R.eyeSmile]
        ].forEach(([J, f], u) => {
          const l = W[u], T = x(J, f, l.cur);
          T !== l.cur && (l.prev = l.cur, l.cur = T, l.t = 0), l.t = z > 0 ? Math.min(1, l.t + z / C) : 1;
          const k = h(0, 1, l.t), U = (I, D) => {
            if (I === "open" || D <= 1e-3) return;
            const te = P[`${I}_${u}`];
            te && (te.layer.visible = !0, te.layer.alpha = D, ne(te, R, V, 1));
          }, S = (I) => I === "open" ? -1 : I === "eyes_half" ? 0 : 1;
          l.t >= 1 ? U(l.cur, 1) : S(l.cur) > S(l.prev) ? (U(l.prev, 1), U(l.cur, k)) : (U(l.cur, 1), U(l.prev, 1 - k)), q[u] = l.cur !== "open" && k >= 0.999;
        });
        const B = A(R.mouthOpen, R.mouthForm, X);
        X = B;
        const Z = B && M[B], K = Z && P[Z.sprite];
        if (K) {
          K.layer.visible = !0, K.layer.alpha = h(O, O + 0.04, R.mouthOpen);
          const J = Math.min(1.1, Math.max(0.5, R.mouthOpen / Z.ref));
          ne(K, R, V, J, Z.width);
        }
        return { eyes: q, mouth: B };
      }
    };
  }
  return { createSprites: s, mouthShape: A, eyeSprite: N };
}
const Ot = /* @__PURE__ */ new Set([
  "angleX",
  "angleY",
  "angleZ",
  "bodyAngleX",
  "bodyAngleZ",
  "armAngle",
  "handAngle",
  "gazeX",
  "gazeY"
]), Ie = {
  nod: {
    label: "Nod",
    dur: 1.7,
    tracks: {
      angleY: [[0, 0], [0.32, -13], [0.62, 2], [0.95, -9], [1.3, 1], [1.7, 0]],
      angleZ: [[0, 0], [0.4, -2], [1, -1], [1.7, 0]],
      bodyAngleX: [[0, 0], [0.5, -1.5], [1.7, 0]],
      eyeSmile: [[0, 0], [0.3, 0.45], [1.3, 0.45], [1.7, 0]],
      eyeOpen: [[0, 1], [1.7, 1]],
      mouthOpen: [[0, 0], [0.3, 0.12], [1.3, 0.12], [1.7, 0]],
      mouthForm: [[0, 0], [0.3, -0.6], [1.7, -0.3]]
    }
  },
  tilt: {
    label: "Head tilt",
    dur: 2.6,
    tracks: {
      angleZ: [[0, 0], [0.55, 17], [2, 15], [2.6, 0]],
      angleX: [[0, 0], [0.6, 8], [2, 7], [2.6, 0]],
      angleY: [[0, 0], [0.6, 4], [2.6, 0]],
      bodyAngleZ: [[0, 0], [0.8, 3], [2, 3], [2.6, 0]],
      gazeX: [[0, 0], [0.4, 0.5], [2.1, 0.4], [2.6, 0]],
      gazeY: [[0, 0], [0.4, 0.35], [2.1, 0.3], [2.6, 0]],
      browAngle: [[0, 0], [0.5, -0.7], [2.1, -0.6], [2.6, 0]],
      browY: [[0, 0], [0.5, 0.35], [2.1, 0.3], [2.6, 0]]
      // closed mouth: a barely open round mouth read as a squashed blob
    }
  },
  think: {
    label: "Thinking",
    dur: 3.6,
    tracks: {
      angleX: [[0, 0], [0.7, -11], [3, -9], [3.6, 0]],
      angleY: [[0, 0], [0.7, 9], [3, 8], [3.6, 0]],
      angleZ: [[0, 0], [0.8, 6], [3, 5], [3.6, 0]],
      gazeX: [[0, 0], [0.35, -0.8], [3.1, -0.7], [3.6, 0]],
      gazeY: [[0, 0], [0.35, 0.7], [3.1, 0.6], [3.6, 0]],
      handAngle: [[0, 0], [0.6, 3], [3, 3], [3.6, 0]],
      fingerTap: [
        [0, 0],
        [0.9, 0],
        [1.05, 1],
        [1.2, 0],
        [1.4, 1],
        [1.55, 0],
        [1.75, 1],
        [1.9, 0],
        [2.3, 0],
        [2.45, 1],
        [2.6, 0],
        [3.6, 0]
      ],
      browY: [[0, 0], [0.6, 0.25], [3, 0.2], [3.6, 0]],
      browAngle: [[0, 0], [0.6, -0.3], [3, -0.3], [3.6, 0]],
      mouthForm: [[0, 0], [0.6, 0.4], [3.6, 0]]
    }
  },
  giggle: {
    label: "Chuckle",
    dur: 2.2,
    tracks: {
      eyeOpen: [[0, 1], [2.2, 1]],
      eyeSmile: [[0, 0], [0.2, 1], [1.8, 1], [2.2, 0]],
      mouthOpen: [[0, 0], [0.2, 0.5], [0.45, 0.32], [0.7, 0.55], [0.95, 0.34], [1.2, 0.5], [1.8, 0.3], [2.1, 0]],
      mouthForm: [[0, 0], [0.2, -0.8], [2.2, -0.2]],
      blush: [[0, 0], [0.3, 0.3], [1.8, 0.3], [2.2, 0.05]],
      angleY: [[0, 0], [0.2, -5], [0.45, -1], [0.7, -6], [0.95, -2], [1.2, -5], [1.6, -2], [2.2, 0]],
      angleZ: [[0, 0], [0.3, -6], [1.8, -5], [2.2, 0]],
      bodyAngleZ: [[0, 0], [0.25, 2], [0.5, -1], [0.75, 2], [1, -1], [1.3, 1.5], [2.2, 0]],
      browY: [[0, 0], [0.3, 0.3], [1.8, 0.3], [2.2, 0]]
    }
  },
  surprise: {
    label: "Surprise",
    dur: 2,
    tracks: {
      angleY: [[0, 0], [0.12, 10], [0.5, 6], [1.5, 5], [2, 0]],
      angleX: [[0, 0], [0.12, -4], [2, 0]],
      bodyAngleX: [[0, 0], [0.15, -4], [1.5, -3], [2, 0]],
      eyeOpen: [[0, 1], [0.1, 1.25], [1.5, 1.2], [2, 1]],
      browY: [[0, 0], [0.1, 1], [1.5, 0.9], [2, 0]],
      mouthOpen: [[0, 0], [0.12, 0.6], [1.4, 0.45], [2, 0]],
      mouthForm: [[0, 0], [0.12, 0.6], [1.5, 0.55], [2, 0]],
      // o
      armAngle: [[0, 0], [0.15, -4], [1.5, -3], [2, 0]]
    }
  },
  shy: {
    label: "Shy",
    dur: 3.2,
    tracks: {
      angleX: [[0, 0], [0.6, 14], [2.6, 12], [3.2, 0]],
      angleY: [[0, 0], [0.6, -9], [2.6, -8], [3.2, 0]],
      angleZ: [[0, 0], [0.7, -8], [2.6, -7], [3.2, 0]],
      gazeX: [[0, 0], [0.3, 0.8], [1.6, 0.8], [1.9, -0.3], [2.2, 0.8], [2.8, 0.6], [3.2, 0]],
      gazeY: [[0, 0], [0.3, -0.5], [2.8, -0.4], [3.2, 0]],
      eyeOpen: [[0, 1], [0.5, 0.9], [2.7, 0.9], [3.2, 1]],
      eyeSmile: [[0, 0], [0.5, 0.5], [2.7, 0.5], [3.2, 0]],
      blush: [[0, 0], [0.8, 0.3], [2.7, 0.3], [3.2, 0]],
      browAngle: [[0, 0], [0.5, -0.6], [2.7, -0.5], [3.2, 0]],
      mouthForm: [[0, 0], [0.5, -0.4], [3.2, 0]],
      handAngle: [[0, 0], [0.8, 4], [2.6, 4], [3.2, 0]]
    }
  },
  no: {
    label: "Shake head",
    dur: 1.9,
    tracks: {
      angleX: [[0, 0], [0.2, 13], [0.45, -13], [0.7, 12], [0.95, -10], [1.2, 5], [1.5, 0]],
      angleY: [[0, 0], [0.2, -3], [1.3, -3], [1.9, 0]],
      bodyAngleX: [[0, 0], [0.3, 1.5], [0.6, -1.5], [0.9, 1], [1.3, 0]],
      eyeOpen: [[0, 1], [0.15, 0], [1.4, 0], [1.9, 1]],
      eyeSmile: [[0, 0], [0.15, 1], [1.4, 1], [1.9, 0]],
      // closed mouth while shaking the head
      browAngle: [[0, 0], [0.2, -0.5], [1.4, -0.5], [1.9, 0]]
    }
  },
  wink: {
    label: "Wink",
    dur: 2,
    tracks: {
      angleZ: [[0, 0], [0.35, -13], [1.5, -12], [2, 0]],
      angleX: [[0, 0], [0.35, 9], [1.5, 8], [2, 0]],
      bodyAngleZ: [[0, 0], [0.5, -2], [1.5, -2], [2, 0]],
      eyeOpenL: [[0, 1], [0.25, 1], [0.4, 0], [1.4, 0], [1.6, 1]],
      eyeSmileL: [[0, 0], [0.3, 1], [1.5, 1], [1.7, 0]],
      mouthOpen: [[0, 0], [2, 0]],
      // wink with a closed smile
      mouthForm: [[0, 0], [0.35, -0.8], [2, 0]],
      blush: [[0, 0], [0.4, 0.3], [1.6, 0.3], [2, 0]]
    }
  },
  greet: {
    label: "Greeting",
    dur: 2.6,
    tracks: {
      angleY: [[0, 0], [0.7, -18], [1.2, -17], [1.9, 2], [2.6, 0]],
      bodyAngleX: [[0, 0], [0.8, 2], [1.8, 0]],
      bodyAngleZ: [[0, 0], [0.8, 1.5], [2, 0]],
      armAngle: [[0, 0], [0.8, 3], [2, 0]],
      eyeOpen: [[0, 1], [1.8, 1]],
      eyeSmile: [[0, 0], [0.5, 1], [1.6, 1], [2.3, 0.4], [2.6, 0]],
      mouthOpen: [[0, 0], [1.6, 0], [1.8, 0.3], [2.3, 0.2], [2.6, 0]],
      mouthForm: [[0, 0], [1.6, -0.8], [2.6, -0.3]],
      blush: [[0, 0], [1.6, 0.3], [2.6, 0]]
    }
  }
}, Ne = {
  lookAround: {
    label: "Look around",
    dur: 5.2,
    idle: !0,
    tracks: {
      gazeX: [[0, 0], [0.25, -0.85], [1.5, -0.8], [1.8, 0.1], [2.1, 0.85], [3.4, 0.8], [3.7, 0], [5.2, 0]],
      gazeY: [[0, 0], [0.25, 0.15], [1.8, 0.25], [2.1, 0.1], [3.7, 0], [5.2, 0]],
      angleX: [[0, 0], [0.7, -20], [1.6, -18], [2.5, 19], [3.5, 17], [4.4, 0], [5.2, 0]],
      angleY: [[0, 0], [0.7, 3], [1.8, 5], [2.5, 3], [4.4, 0]],
      angleZ: [[0, 0], [0.8, 4], [1.8, 0], [2.6, -4], [4.4, 0]],
      bodyAngleX: [[0, 0], [1, -4], [2.8, 4], [4.6, 0]],
      bodyAngleZ: [[0, 0], [1, 1.5], [2.8, -1.5], [4.6, 0]],
      handAngle: [[0, 0], [1, -2], [2.8, 2], [4.6, 0]],
      browY: [[0, 0], [0.5, 0.35], [3.6, 0.3], [4.4, 0]],
      // curious: a quick inhale, held while looking, let out at the end
      breath: [[0, 0.2], [0.6, 0.85], [3.6, 0.7], [4.6, 0], [5.2, 0.1]]
    }
  },
  glance: {
    label: "Side glance",
    dur: 4.6,
    idle: !0,
    tracks: {
      gazeX: [[0, 0], [0.18, 0.9], [2.6, 0.85], [2.9, 0.15], [3.2, 0], [4.6, 0]],
      gazeY: [[0, 0], [0.18, 0.4], [2.6, 0.35], [3.2, 0]],
      angleX: [[0, 0], [0.6, 13], [2.6, 11], [3.6, 0]],
      angleY: [[0, 0], [0.6, 6], [2.6, 5], [3.6, 0]],
      angleZ: [[0, 0], [0.7, -5], [2.6, -4], [3.6, 0]],
      bodyAngleX: [[0, 0], [1, 2.5], [2.8, 2], [4, 0]],
      eyeOpen: [[0, 1], [0.3, 1.06], [2.5, 1.05], [2.8, 0.85], [3.4, 1]],
      browY: [[0, 0], [0.4, 0.4], [2.5, 0.35], [3.4, 0]],
      browAngle: [[0, 0], [0.4, -0.2], [2.5, -0.2], [3.4, 0]],
      breath: [[0, 0], [0.5, 0.6], [2.6, 0.55], [3.8, 0], [4.6, 0.3]]
    }
  },
  sway: {
    label: "Sway",
    dur: 7,
    idle: !0,
    tracks: {
      bodyAngleZ: [[0, 0], [1.6, 6], [3.4, -6], [5.2, 5], [7, 0]],
      bodyAngleX: [[0, 0], [1.6, 3], [3.4, -3], [5.2, 2.5], [7, 0]],
      angleZ: [[0, 0], [1.8, -10], [3.6, 10], [5.4, -8], [7, 0]],
      angleX: [[0, 0], [1.8, 6], [3.6, -6], [5.4, 5], [7, 0]],
      angleY: [[0, 0], [0.9, 3], [1.8, 0], [2.7, 3], [3.6, 0], [4.5, 3], [5.4, 0], [7, 0]],
      armAngle: [[0, 0], [1.6, 3], [3.4, -3], [5.2, 2], [7, 0]],
      handAngle: [[0, 0], [1.8, -4], [3.6, 4], [5.4, -3], [7, 0]],
      gazeX: [[0, 0], [1.8, -0.3], [3.6, 0.3], [5.4, -0.2], [7, 0]],
      eyeOpen: [[0, 1], [0.8, 0.82], [6.2, 0.82], [7, 1]],
      eyeSmile: [[0, 0], [0.8, 0.35], [6.2, 0.35], [7, 0]],
      // slow, even breaths in time with the sway
      breath: [[0, 0], [0.9, 1], [1.8, 0], [2.7, 1], [3.6, 0], [4.5, 1], [5.4, 0], [6.3, 0.8], [7, 0]]
    }
  },
  sigh: {
    label: "Sigh",
    dur: 5.6,
    idle: !0,
    tracks: {
      breath: [[0, 0], [1.3, 1.25], [1.9, 1.25], [3.6, 0], [5.6, 0]],
      angleY: [[0, 0], [1.3, 9], [1.9, 9], [3.3, -9], [4.6, -6], [5.6, 0]],
      angleZ: [[0, 0], [1.3, -3], [3.3, 5], [5.6, 0]],
      bodyAngleX: [[0, 0], [1.3, -2.5], [3.3, 2.5], [5.6, 0]],
      bodyAngleZ: [[0, 0], [1.9, 1], [3.3, -1.5], [5.6, 0]],
      armAngle: [[0, 0], [1.3, -2.5], [3.3, 2], [5.6, 0]],
      gazeY: [[0, 0], [1.2, 0.4], [2, 0.3], [3.2, -0.4], [4.8, -0.2], [5.6, 0]],
      eyeOpen: [[0, 1], [1, 0.95], [1.9, 0.6], [3.4, 0.6], [4.6, 0.78], [5.6, 1]],
      browY: [[0, 0], [1.3, 0.35], [3.2, -0.2], [5.6, 0]],
      browAngle: [[0, 0], [1.9, -0.4], [4.6, -0.35], [5.6, 0]]
    }
  },
  doze: {
    label: "Drowsy",
    dur: 7.2,
    idle: !0,
    tracks: {
      eyeOpen: [[0, 1], [1.8, 0.78], [3.2, 0.62], [4.5, 0.55], [4.75, 1.1], [5.6, 1.05], [7.2, 1]],
      angleY: [[0, 0], [1.8, -6], [3.2, -9], [4.5, -17], [4.75, 5], [5.6, 2], [7.2, 0]],
      angleZ: [[0, 0], [2, 4], [4.5, 10], [4.75, -2], [7.2, 0]],
      angleX: [[0, 0], [4.5, -4], [4.75, 3], [5.4, -6], [6.2, 5], [7.2, 0]],
      bodyAngleZ: [[0, 0], [4.5, 3], [4.8, -2], [7.2, 0]],
      bodyAngleX: [[0, 0], [4.5, 2], [4.8, -1.5], [7.2, 0]],
      armAngle: [[0, 0], [4.5, 3], [4.8, -2], [7.2, 0]],
      handAngle: [[0, 0], [4.5, 5], [4.8, -1], [7.2, 0]],
      gazeY: [[0, 0], [4.5, -0.4], [4.75, 0.2], [7.2, 0]],
      gazeX: [[0, 0], [4.8, 0], [5.3, -0.6], [6.1, 0.6], [6.8, 0]],
      browY: [[0, 0], [4.5, -0.35], [4.75, 0.8], [5.8, 0.3], [7.2, 0]],
      // long, slow, deepening breaths; a sharp inhale on waking
      breath: [[0, 0], [1.1, 0.7], [2.6, 0], [3.8, 0.6], [4.5, 0.2], [4.8, 1.1], [6, 0.2], [7.2, 0]]
    }
  },
  stretch: {
    label: "Stretch",
    dur: 6.2,
    idle: !0,
    tracks: {
      angleZ: [[0, 0], [1.3, -22], [2.3, -21], [3.8, 20], [4.8, 19], [6.2, 0]],
      angleY: [[0, 0], [1.3, 5], [2.3, 7], [3.1, -3], [3.8, 5], [4.8, 6], [6.2, 0]],
      angleX: [[0, 0], [1.3, -5], [3.8, 5], [6.2, 0]],
      bodyAngleZ: [[0, 0], [1.3, 4], [3.8, -4], [6.2, 0]],
      bodyAngleX: [[0, 0], [1.3, -2], [3.8, 2], [6.2, 0]],
      armAngle: [[0, 0], [1.3, 2], [3.8, -2], [6.2, 0]],
      eyeOpen: [[0, 1], [0.8, 0.62], [4.9, 0.62], [5.6, 1]],
      browAngle: [[0, 0], [1, -0.3], [4.9, -0.3], [5.8, 0]],
      breath: [[0, 0], [1.3, 1.1], [2.3, 0.9], [3.1, 0.2], [3.8, 1.1], [4.8, 0.9], [6.2, 0]]
    }
  },
  lean: {
    label: "Peek",
    dur: 4.8,
    idle: !0,
    tracks: {
      bodyAngleX: [[0, 0], [0.9, 6], [3.4, 6], [4.4, 0]],
      bodyAngleZ: [[0, 0], [0.9, -3], [3.4, -3], [4.4, 0]],
      angleX: [[0, 0], [0.9, 9], [2, 7], [2.6, 10], [3.4, 8], [4.4, 0]],
      angleY: [[0, 0], [0.9, -6], [3.4, -5], [4.4, 0]],
      angleZ: [[0, 0], [0.9, 10], [2.2, 12], [3.4, 9], [4.4, 0]],
      armAngle: [[0, 0], [0.9, -3], [3.4, -3], [4.4, 0]],
      handAngle: [[0, 0], [0.9, 3], [3.4, 3], [4.4, 0]],
      gazeY: [[0, 0], [0.6, 0.45], [3.4, 0.4], [4.2, 0]],
      gazeX: [[0, 0], [1.5, 0], [1.8, -0.3], [2.3, 0.2], [2.8, 0], [4.2, 0]],
      eyeOpen: [[0, 1], [0.6, 1.1], [3.4, 1.08], [4.2, 1]],
      browY: [[0, 0], [0.6, 0.45], [3.4, 0.4], [4.2, 0]],
      browAngle: [[0, 0], [0.6, -0.3], [3.4, -0.3], [4.2, 0]],
      blush: [[0, 0], [1.2, 0.25], [3.4, 0.25], [4.4, 0]],
      breath: [[0, 0], [0.8, 0.8], [3.4, 0.6], [4.4, 0], [4.8, 0.2]]
    }
  },
  hum: {
    label: "Listen",
    dur: 5.6,
    idle: !0,
    tracks: {
      angleY: [[0, 0], [0.45, -5], [0.9, 2], [1.35, -5], [1.8, 2], [2.25, -5], [2.7, 2], [3.15, -5], [3.6, 2], [4.05, -4], [4.8, 0]],
      angleZ: [[0, 0], [0.9, 8], [1.8, -8], [2.7, 8], [3.6, -8], [4.6, 0]],
      angleX: [[0, 0], [0.9, 4], [1.8, -4], [2.7, 4], [3.6, -4], [4.6, 0]],
      bodyAngleZ: [[0, 0], [0.9, -3], [1.8, 3], [2.7, -3], [3.6, 3], [4.6, 0]],
      bodyAngleX: [[0, 0], [1.8, 2], [3.6, -2], [4.8, 0]],
      handAngle: [[0, 0], [0.9, 3], [1.8, -3], [2.7, 3], [3.6, -3], [4.6, 0]],
      fingerTap: [[0, 0], [0.45, 1], [0.9, 0], [1.35, 1], [1.8, 0], [2.25, 1], [2.7, 0], [3.15, 1], [3.6, 0], [5.6, 0]],
      gazeX: [[0, 0], [0.9, 0.3], [1.8, -0.3], [2.7, 0.3], [3.6, -0.3], [4.6, 0]],
      eyeOpen: [[0, 1], [0.4, 0.72], [4.6, 0.72], [5.3, 1]],
      eyeSmile: [[0, 0], [0.4, 0.55], [4.6, 0.55], [5.3, 0]],
      blush: [[0, 0], [0.8, 0.3], [4.6, 0.3], [5.6, 0]],
      browY: [[0, 0], [0.5, 0.25], [4.6, 0.25], [5.4, 0]],
      breath: [[0, 0], [0.9, 0.9], [1.8, 0.2], [2.7, 0.9], [3.6, 0.2], [4.6, 0.8], [5.6, 0]]
    }
  },
  tap: {
    label: "Tap",
    dur: 5,
    idle: !0,
    tracks: {
      gazeX: [[0, 0], [0.3, -0.6], [2.2, -0.5], [2.5, -0.1], [2.8, -0.6], [4.2, -0.5], [4.7, 0]],
      gazeY: [[0, 0], [0.3, 0.55], [4.2, 0.5], [4.7, 0]],
      angleX: [[0, 0], [0.8, -11], [2.4, -9], [3, -12], [4.2, -10], [5, 0]],
      angleY: [[0, 0], [0.8, 8], [4.2, 7], [5, 0]],
      angleZ: [[0, 0], [0.8, 6], [2.4, 4], [3, 7], [4.2, 5], [5, 0]],
      bodyAngleX: [[0, 0], [1, -2], [4.2, -2], [5, 0]],
      handAngle: [[0, 0], [0.8, 3], [4.2, 3], [5, 0]],
      fingerTap: [
        [0, 0],
        [0.9, 0],
        [1.05, 1],
        [1.2, 0],
        [1.4, 1],
        [1.55, 0],
        [1.75, 1],
        [1.9, 0],
        [2.6, 0],
        [2.75, 1],
        [2.9, 0],
        [3.1, 1],
        [3.25, 0],
        [5, 0]
      ],
      browY: [[0, 0], [0.6, 0.3], [4.2, 0.25], [5, 0]],
      browAngle: [[0, 0], [0.6, -0.35], [4.2, -0.3], [5, 0]],
      eyeOpen: [[0, 1], [0.6, 0.9], [4.2, 0.9], [5, 1]],
      breath: [[0, 0], [0.8, 0.7], [2.2, 0.4], [3.2, 0.8], [4.4, 0], [5, 0.2]]
    }
  },
  readNote: {
    label: "Read script",
    dur: 2.6,
    idle: !0,
    tracks: {
      // a quick look down at the notes on the desk and back to the camera
      gazeY: [[0, 0], [0.2, -0.85], [1.5, -0.8], [1.75, 0], [2.6, 0]],
      gazeX: [[0, 0], [0.2, -0.15], [1.5, -0.1], [1.75, 0]],
      angleY: [[0, 0], [0.45, -9], [1.5, -8], [2, 1], [2.6, 0]],
      angleZ: [[0, 0], [0.5, 2], [1.6, 2], [2.6, 0]],
      eyeOpen: [[0, 1], [0.3, 0.78], [1.5, 0.78], [1.75, 1]],
      breath: [[0, 0.3], [0.8, 0.5], [1.8, 0.2], [2.6, 0.4]]
    }
  },
  waiting: {
    label: "Fidget",
    dur: 6.4,
    idle: !0,
    tracks: {
      // shifts her weight, checks the viewer, looks away, shifts back
      bodyAngleZ: [[0, 0], [0.9, 5], [2.4, 4], [3.3, -5], [5.2, -4], [6.4, 0]],
      bodyAngleX: [[0, 0], [0.9, 3], [3.3, -3], [5.2, -2], [6.4, 0]],
      angleZ: [[0, 0], [1, -6], [2.4, -4], [3.4, 6], [5.2, 5], [6.4, 0]],
      angleX: [[0, 0], [1.2, -8], [2.2, 2], [3.6, 12], [5, 10], [6.2, 0]],
      angleY: [[0, 0], [1.2, -3], [2.2, 2], [3.6, -2], [6.2, 0]],
      armAngle: [[0, 0], [0.9, 3], [3.3, -3], [5.2, -2], [6.4, 0]],
      handAngle: [[0, 0], [1.2, 3], [3.4, -3], [6.4, 0]],
      fingerTap: [[0, 0], [4.2, 0], [4.35, 1], [4.5, 0], [4.7, 1], [4.85, 0], [6.4, 0]],
      gazeX: [[0, 0], [0.9, -0.7], [1.9, -0.6], [2.1, 0], [2.7, 0], [2.9, 0.8], [5, 0.7], [5.4, 0], [6.4, 0]],
      gazeY: [[0, 0], [0.9, -0.2], [2.1, 0], [2.9, 0.3], [5.4, 0]],
      eyeOpen: [[0, 1], [2, 1], [2.2, 1.06], [2.8, 1.05], [3.1, 0.85], [5.4, 0.85], [6.2, 1]],
      browAngle: [[0, 0], [0.9, -0.35], [2, -0.35], [2.3, 0], [3.1, -0.4], [5.4, -0.35], [6.4, 0]],
      browY: [[0, 0], [2.2, 0.4], [2.8, 0.35], [3.2, 0], [6.4, 0]],
      breath: [[0, 0.3], [0.9, 0.8], [2, 0.3], [2.6, 0.9], [3.4, 0.2], [4.4, 0.8], [5.6, 0], [6.4, 0.2]]
    }
  },
  spaceOut: {
    label: "Daydream",
    dur: 7.4,
    idle: !0,
    tracks: {
      // gaze drifts up and away, breaths get slow and long, one slow blink
      gazeX: [[0, 0], [1.4, -0.55], [4.8, -0.6], [5.6, 0.1], [7, 0]],
      gazeY: [[0, 0], [1.4, 0.6], [4.8, 0.55], [5.6, 0], [7, 0]],
      angleX: [[0, 0], [2, -9], [4.8, -10], [6, 2], [7.4, 0]],
      angleY: [[0, 0], [2, 7], [4.8, 8], [6, -2], [7.4, 0]],
      angleZ: [[0, 0], [2, 9], [4.8, 11], [6, 2], [7.4, 0]],
      bodyAngleZ: [[0, 0], [2.2, 3], [4.8, 3.5], [6.4, 0]],
      bodyAngleX: [[0, 0], [2.2, -2], [4.8, -2], [6.4, 0]],
      handAngle: [[0, 0], [2.2, 4], [4.8, 5], [6.4, 0]],
      armAngle: [[0, 0], [2.2, 2], [4.8, 2], [6.4, 0]],
      eyeOpen: [[0, 1], [1.4, 0.8], [3, 0.8], [3.35, 0.56], [3.8, 0.8], [4.8, 0.8], [5.6, 1.04], [6.4, 1]],
      browY: [[0, 0], [1.6, 0.15], [4.8, 0.15], [5.6, 0.35], [6.6, 0]],
      breath: [[0, 0], [1.6, 0.9], [3.4, 0], [5, 0.9], [6.2, 0.1], [7.4, 0]]
    }
  }
};
function _t(o, t) {
  if (t <= o[0][0]) return o[0][1];
  const e = o.length - 1;
  if (t >= o[e][0]) return o[e][1];
  let a = 0;
  for (; t > o[a + 1][0]; ) a++;
  const [i, h] = o[a], [g, M] = o[a + 1], O = (A) => A <= 0 || A >= e ? 0 : (o[A + 1][1] - o[A - 1][1]) / (o[A + 1][0] - o[A - 1][0]), w = g - i, _ = (t - i) / w, v = O(a) * w, C = O(a + 1) * w, N = _ * _, x = N * _;
  return (2 * x - 3 * N + 1) * h + (x - 2 * N + _) * v + (-2 * x + 3 * N) * M + (x - N) * C;
}
const _e = {
  a: { open: 0.9, form: 0, label: "あ" },
  i: { open: 0.5, form: -0.85, label: "い" },
  u: { open: 0.4, form: 0.9, label: "う" },
  e: { open: 0.62, form: -0.4, label: "え" },
  o: { open: 0.75, form: 0.6, label: "お" },
  n: { open: 0, form: null, label: "ん" }
  // closes with the previous shape
}, kt = {
  a: "あかさたなはまやらわがざだばぱぁ",
  i: "いきしちにひみりぎじぢびぴぃ",
  u: "うくすつぬふむゆるぐずづぶぷぅゔ",
  e: "えけせてねへめれげぜでべぺぇ",
  o: "おこそとのほもよろをごぞどぼぽぉ"
}, tt = {};
for (const [o, t] of Object.entries(kt)) for (const e of t) tt[e] = o;
const Ft = /* @__PURE__ */ new Set([..."まみむめもばびぶべぼぱぴぷぺぽ"]), Yt = /* @__PURE__ */ new Set([..."あいうえおぁぃぅぇぉ"]), Ze = { ゃ: "a", ゅ: "u", ょ: "o" }, Bt = /* @__PURE__ */ new Set([..."、。，．,.！？!? 　…"]), Xt = (o) => o.replace(/[ァ-ヶ]/g, (t) => String.fromCharCode(t.charCodeAt(0) - 96));
function Ut(o, t = 0.14) {
  const e = [];
  for (const a of Xt(o)) {
    const i = e[e.length - 1];
    if (Ze[a] && i) {
      i.vowel = Ze[a];
      continue;
    }
    if (a === "ー" && i) {
      i.dur += t;
      continue;
    }
    if (a === "っ") {
      e.push({ vowel: "n", dur: t * 0.8, onset: null });
      continue;
    }
    if (a === "ん") {
      e.push({ vowel: "n", dur: t, onset: null });
      continue;
    }
    if (Bt.has(a)) {
      e.push({ vowel: "n", dur: t * 2.2, onset: null });
      continue;
    }
    const h = tt[a];
    h && e.push({ vowel: h, dur: t, onset: Ft.has(a) ? "lips" : Yt.has(a) ? null : "consonant" });
  }
  return e;
}
function It(o, t) {
  let e = 0;
  for (const a of o) {
    if (t < e + a.dur) {
      const i = (t - e) / a.dur, h = _e[a.vowel], g = a.onset === "lips" ? 0.05 : a.onset === "consonant" ? 0.45 : 1, M = i < 0.35 ? g + (1 - g) * (i / 0.35) : 1;
      return { open: h.open * M, form: h.form, vowel: a.vowel };
    }
    e += a.dur;
  }
  return null;
}
const xe = { ...Ie, ...Ne }, Ve = { amp: 1, stiff: 1.8 }, Nt = /^(angle|bodyAngle|armAngle|handAngle)/, Ct = /* @__PURE__ */ new Set([
  "eyeOpen",
  "eyeOpenL",
  "eyeSmileL",
  "eyeSmile",
  "mouthOpen",
  "mouthForm",
  "blush",
  "browY",
  "browAngle"
]), Oe = (o, t, e) => {
  const a = Math.min(1, Math.max(0, (e - o) / (t - o)));
  return a * a * (3 - 2 * a);
};
function qe(o, t) {
  const e = Math.floor(o), a = o - e, i = (g) => {
    const M = Math.sin((g + t * 57.3) * 127.1) * 43758.5453;
    return M - Math.floor(M);
  }, h = a * a * (3 - 2 * a);
  return (i(e) * (1 - h) + i(e + 1) * h) * 2 - 1;
}
const fe = (o, t) => qe(o, t) * 0.7 + qe(o * 2.3, t + 9) * 0.3, re = (o, t, e) => Math.max(t, Math.min(e, o)), nt = {
  normal: { label: "Neutral", p: {} },
  smile: { label: "Smile", p: { eyeOpen: 0, eyeSmile: 1, blush: 0.35, browY: 0.2 } },
  shy: { label: "Blush", p: { eyeOpen: 0.78, eyeSmile: 0.5, blush: 0.55, browAngle: -0.5, browY: -0.1, glance: [0.7, 0.35] } },
  jito: { label: "Half-lidded", p: { eyeOpen: 0.5, browY: -0.5, browAngle: 0.6 } },
  surprise: { label: "Surprise", p: { eyeOpen: 1.22, browY: 1, mouthOpen: 0.6, mouthForm: 0.6 } },
  wink: { label: "Wink", p: { eyeOpenL: 0, eyeSmileL: 1, blush: 0.3 } },
  // talking faces for AITuber OnAir emotion tags: eyes stay mostly open (closed / ^^ eyes are
  // what a single image fakes worst, and they would stay shut for a whole sentence)
  happyTalk: { label: "happy", p: { eyeOpen: 1, eyeSmile: 0.45, blush: 0.35, browY: 0.25, mouthForm: -0.5 } },
  sadTalk: { label: "sad", p: { eyeOpen: 0.78, browAngle: -0.8, browY: -0.2, mouthForm: 0.3, glance: [0, -0.35] } },
  angryTalk: { label: "angry", p: { eyeOpen: 0.9, browAngle: 0.85, browY: -0.55, mouthForm: 0.2 } },
  surprisedTalk: { label: "surprised", p: { eyeOpen: 1.18, browY: 0.9, mouthForm: 0.9 } },
  relaxedTalk: { label: "relaxed", p: { eyeOpen: 0.82, eyeSmile: 0.35, blush: 0.15, browY: 0.1 } }
}, Ke = {
  happy: ["happyTalk", "nod"],
  sad: ["sadTalk", "sigh"],
  angry: ["angryTalk", "no"],
  surprised: ["surprisedTalk", "surprise"],
  relaxed: ["relaxedTalk", "sway"],
  neutral: ["normal", null]
}, Pt = {
  gazeX: [260, 0.9],
  gazeY: [260, 0.9],
  angleX: [55, 0.72],
  angleY: [55, 0.72],
  angleZ: [45, 0.75],
  bodyAngleX: [14, 0.9],
  bodyAngleZ: [12, 0.9],
  armAngle: [20, 0.85],
  handAngle: [30, 0.8]
};
class zt {
  /** @param {number[]} gazeCenter */
  constructor(t) {
    this.mode = "auto", this.P = Object.fromEntries(Re.map((e) => [e.id, e.def])), this.manual = { ...this.P }, this.cur = { ...this.P }, this.vel = Object.fromEntries(Re.map((e) => [e.id, 0])), this.expr = "normal", this.exprMix = {}, this.t = 0, this.blink = { t: 0, start: 1.5, double: !1 }, this.gaze = { x: 0, y: 0, next: 0 }, this.tap = { next: 4, until: -1 }, this.pointer = null, this.faceCenter = [...t], this.lipOpen = null, this.lipForm = 0, this.speaking = !1, this.voice = 0, this.mouth = 0, this.vowel = "a", this.vowelForm = 0, this.syllableArmed = !0, this.voicePeak = 0, this.voiceTrough = 0, this.kana = null, this.lipHold = null, this.emotionUntil = 0, this.talkGain = 1, this.play = null, this.autoMotion = !0, this.nextAuto = 14, this.autoIdle = !0, this.nextIdle = 3, this.lastAuto = null, this.onMotion = null;
  }
  setExpression(t) {
    this.expr = t;
  }
  hasMotion(t) {
    return t in xe;
  }
  // ---- speech (driven from outside, e.g. by the TTS audio analyser) ----
  setVoiceLevel(t) {
    this.voice = Math.min(1, Math.max(0, Number(t) || 0));
  }
  setSpeaking(t) {
    t !== this.speaking && (this.speaking = !!t, t || (this.emotionUntil = this.t + 1.2, this.voice = 0));
  }
  /** `playMotion: false` changes only the face (a caller that picks motions itself). */
  setEmotion(t, { playMotion: e = !0 } = {}) {
    const a = Ke[t] ?? Ke.neutral;
    this.expr = a[0], this.emotionUntil = 1 / 0, a[1] && e && this.playMotion(a[1]);
  }
  /** Mouth shapes from kana text, without audio (preview / tuning). */
  /** @param {string} text @param {{ speed?: number, loop?: boolean }} [options] */
  speakKana(t, { speed: e, loop: a = !1 } = {}) {
    this.lipHold = null;
    const i = Ut(t, e === void 0 ? 0.14 : 1 / re(Number(e) || 7, 4, 12));
    this.kana = i.length ? { moras: i, t: 0, loop: a, duration: i.reduce((h, g) => h + g.dur, 0) } : null;
  }
  holdMouth(t) {
    this.kana = null, this.lipHold = Object.hasOwn(_e, t) ? t : null;
  }
  stopLipSync() {
    this.kana = null, this.lipHold = null, this.lipOpen = null, this.mouth = 0;
  }
  getLipSyncState() {
    return { active: this.kana !== null || this.lipHold !== null, open: this.P.mouthOpen, form: this.P.mouthForm };
  }
  // Mouth from the TTS loudness. A volume signal has no vowel information, so each syllable
  // (the voice dipping and rising again) gets one vowel at random, weighted towards a, and
  // keeps it until the next syllable: the drawn mouths must not change shape mid-syllable.
  // Syllables are found relative to the recent peak (not an absolute level), and the mouth
  // is scaled by where the voice sits between the recent trough and peak, so it closes in
  // the dip before each mora even when a loud voice never gets quiet.
  speechMouth(t) {
    if (this.kana || this.lipHold) {
      let v;
      if (this.lipHold ? v = _e[this.lipHold] : (this.kana.t += t, this.kana.loop && (this.kana.t %= this.kana.duration), v = It(this.kana.moras, this.kana.t)), !v)
        return this.kana = null, this.mouth > 0.01 ? [this.mouth *= 0.6, this.vowelForm] : null;
      const C = v.open > this.mouth ? 1 - Math.exp(-t * 30) : 1 - Math.exp(-t * 22);
      return this.mouth += (v.open - this.mouth) * C, v.form !== null && (this.vowelForm = v.form), [this.mouth, this.vowelForm];
    }
    const e = this.speaking ? this.voice : 0, a = 1 - Math.exp(-t * 5);
    this.voicePeak = e > this.voicePeak ? e : this.voicePeak + (e - this.voicePeak) * a, this.voiceTrough = e < this.voiceTrough ? e : this.voiceTrough + (e - this.voiceTrough) * a;
    const i = Math.max(this.voicePeak, 0.05);
    if (e < i * 0.6) this.syllableArmed = !0;
    else if (this.syllableArmed && e > i * 0.8 && e > 0.1) {
      this.syllableArmed = !1;
      const v = Math.random();
      this.vowel = v < 0.4 ? "a" : v < 0.58 ? "o" : v < 0.74 ? "e" : v < 0.88 ? "i" : "u";
    }
    const h = this.voicePeak - this.voiceTrough, g = h < i * 0.3 ? 1 : Math.max(0, (e - this.voiceTrough) / h), M = _e[this.vowel ?? "a"], O = Math.min(1, Math.pow(e, 0.7) * 1.15) * Math.pow(g, 0.3), w = this.speaking ? Math.min(0.95, O) * (0.45 + 0.55 * M.open / 0.9) : 0, _ = w > this.mouth ? 1 - Math.exp(-t * 40) : 1 - Math.exp(-t * 32);
    return this.mouth += (w - this.mouth) * _, this.speaking && (this.vowelForm = M.form), this.speaking || this.mouth > 0.01 ? [this.mouth, this.vowelForm] : null;
  }
  // Breathing: inhale ~40% of the cycle, a slower exhale, a short pause at the bottom,
  // and a period that drifts between ~3.2 and 4.6 s so it never looks metronomic.
  breathValue(t) {
    this.breathPhase = (this.breathPhase ?? 0) + t / (this.breathPeriod ?? 3.8), this.breathPhase >= 1 && (this.breathPhase -= 1, this.breathPeriod = 3.2 + Math.random() * 1.4);
    const e = this.breathPhase;
    return e < 0.4 ? Oe(0, 0.4, e) : e < 0.88 ? 1 - Oe(0.4, 0.88, e) : 0;
  }
  // pick one at random, never the one that just played
  playRandom(t) {
    const e = t.filter((a) => a !== this.lastAuto);
    this.playMotion(e[Math.floor(Math.random() * e.length)]);
  }
  playMotion(t) {
    this.lastAuto = t, this.play = { id: t, t: 0 }, this.onMotion?.(t);
  }
  blinkValue(t) {
    const e = this.blink;
    if (e.t += t, e.t < e.start) return 1;
    const a = (e.t - e.start) / 0.17;
    return a >= 1 ? (e.double ? (e.double = !1, e.start = e.t + 0.07) : (e.start = e.t + 1.8 + Math.random() * 4.2, e.double = Math.random() < 0.18), 1) : a < 0.45 ? 1 - a / 0.45 : (a - 0.45) / 0.55;
  }
  update(t) {
    this.t += t;
    const e = this.t, a = {};
    for (const x of Re) a[x.id] = x.def;
    if (this.mode === "manual")
      Object.assign(a, this.manual);
    else if (this.mode === "auto") {
      if (a.angleX = fe(e * 0.18, 1) * 10 + this.gaze.x * 11, a.angleY = fe(e * 0.15, 2) * 6 - 1 + this.gaze.y * 7, a.angleZ = fe(e * 0.12, 3) * 10, a.bodyAngleX = fe(e * 0.1, 4) * 5, a.bodyAngleZ = fe(e * 0.09, 5) * 4, a.armAngle = fe(e * 0.14, 6) * 5, a.handAngle = fe(e * 0.21, 7) * 5, e > this.gaze.next) {
        const x = Math.random();
        this.gaze.x = x < 0.45 ? 0 : (Math.random() * 2 - 1) * 0.8, this.gaze.y = x < 0.45 ? 0 : (Math.random() * 2 - 1) * 0.5, this.gaze.next = e + 0.8 + Math.random() * 2.5;
      }
      if (a.gazeX = this.gaze.x + a.angleX / 60, a.gazeY = this.gaze.y + a.angleY / 60, e > this.tap.next && (this.tap.until = e + 1.1, this.tap.next = e + 5 + Math.random() * 6), this.speaking) {
        this.nextIdle = Math.max(this.nextIdle, e + 2.5), this.nextAuto = Math.max(this.nextAuto, e + 6);
        const x = this.talkGain;
        this.talkNod = (this.talkNod ?? 0) + (this.voice * 7 * x - (this.talkNod ?? 0)) * Math.min(1, t * 6), a.angleY -= this.talkNod, a.angleX += fe(e * 0.6, 11) * 5 * x, a.angleZ += fe(e * 0.5, 12) * 4 * x;
      }
      !this.speaking && e > this.emotionUntil && (this.expr = "normal", this.emotionUntil = 1 / 0), this.speaking || (!this.play && this.autoMotion && e > this.nextAuto ? (this.playRandom(Object.keys(Ie).filter((x) => x !== "surprise" && x !== "no")), this.nextAuto = e + 15 + Math.random() * 10, this.nextIdle = Math.max(this.nextIdle, e + 5)) : !this.play && this.autoIdle && e > this.nextIdle && (this.playRandom(Object.keys(Ne)), this.nextIdle = e + 5 + Math.random() * 5));
    } else if (this.mode === "mouse" && this.pointer) {
      const x = (this.pointer[0] - this.faceCenter[0]) / 500, A = (this.pointer[1] - this.faceCenter[1]) / 500;
      a.angleX = re(x * 30, -30, 30), a.angleY = re(-A * 30, -30, 30), a.angleZ = re(-x * A * 25, -12, 12), a.bodyAngleX = re(x * 10, -10, 10) * 0.6, a.gazeX = re(x * 1.4, -1, 1), a.gazeY = re(-A * 1.4, -1, 1), a.handAngle = re(x * 4, -5, 5);
    }
    this.mode !== "manual" && (a.breath = this.breathValue(t), e < this.tap.until && (a.fingerTap = Math.max(0, Math.sin((this.tap.until - e) * Math.PI * 3.6)) ** 2));
    let i = null, h = 0;
    if (this.play) {
      const x = xe[this.play.id];
      if (this.play.t += t, this.play.t >= x.dur)
        this.play = null, this.onMotion?.(null);
      else {
        i = {};
        for (const [A, y] of Object.entries(x.tracks))
          i[A] = _t(y, this.play.t) * (x.idle && Nt.test(A) ? Ve.amp : 1);
        h = Oe(0, 0.15, this.play.t) * (1 - Oe(x.dur - 0.25, x.dur, this.play.t));
        for (const [A, y] of Object.entries(i))
          Ot.has(A) ? a[A] += y : A === "breath" ? a[A] += (y - a[A]) * h : Ct.has(A) || (a[A] = Math.max(a[A], Math.max(0, y)));
      }
    }
    this.mode !== "manual" && (a.angleY += a.breath * 1.6);
    const g = nt[this.expr].p, M = ["eyeOpen", "eyeOpenL", "eyeSmileL", "eyeSmile", "mouthOpen", "mouthForm", "blush", "browY", "browAngle", "gx", "gy"], O = {
      eyeOpen: g.eyeOpen ?? 1,
      eyeOpenL: g.eyeOpenL ?? g.eyeOpen ?? 1,
      eyeSmileL: g.eyeSmileL ?? g.eyeSmile ?? 0,
      eyeSmile: g.eyeSmile ?? 0,
      mouthOpen: g.mouthOpen ?? 0,
      mouthForm: g.mouthForm ?? 0,
      blush: g.blush ?? 0,
      browY: g.browY ?? 0,
      browAngle: g.browAngle ?? 0,
      gx: g.glance?.[0] ?? 0,
      gy: g.glance?.[1] ?? 0
    }, w = 1 - Math.exp(-t * 9);
    for (const x of M)
      this.exprMix[x] === void 0 && (this.exprMix[x] = O[x]), this.exprMix[x] += (O[x] - this.exprMix[x]) * w;
    const _ = this.exprMix, v = {};
    for (const x of Re) {
      const A = x.id;
      if (this.mode === "manual" && !i) {
        v[A] = a[A], this.cur[A] = a[A], this.vel[A] = 0;
        continue;
      }
      let [y, d] = Pt[A] ?? [120, 0.95];
      i && /^angle|^body/.test(A) && (xe[this.play?.id ?? ""]?.idle ? (y *= Ve.stiff, d = 0.8) : /^angle/.test(A) && (y *= 4.5, d = 0.75));
      const n = 2 * Math.sqrt(y) * d;
      this.vel[A] += (y * (a[A] - this.cur[A]) - n * this.vel[A]) * t, this.cur[A] += this.vel[A] * t, v[A] = this.cur[A];
    }
    let C = 1;
    if (this.mode !== "manual" ? (C = this.blinkValue(t), v.eyeROpen = _.eyeOpen * C, v.eyeLOpen = _.eyeOpenL * C, v.eyeSmile = _.eyeSmile, v.eyeSmileL = _.eyeSmileL, v.mouthOpen = _.mouthOpen, v.mouthForm = _.mouthForm, v.blush = _.blush, v.browY = _.browY + (v.angleY > 0 ? v.angleY / 60 : 0) - (1 - C) * 0.18, v.browAngle = _.browAngle, v.gazeX = re(v.gazeX + _.gx, -1, 1), v.gazeY = re(v.gazeY + _.gy, -1, 1)) : v.eyeSmileL = v.eyeSmile, i && !(this.expr !== "normal" && xe[this.play?.id ?? ""]?.idle)) {
      const x = (d, n) => {
        v[d] += (n - v[d]) * h;
      }, A = !!xe[this.play?.id ?? ""]?.idle, y = (d) => Math.min(1.3, Math.max(A ? 0.85 : 0, d));
      "eyeOpen" in i && (x("eyeROpen", y(i.eyeOpen) * C), "eyeOpenL" in i || x("eyeLOpen", y(i.eyeOpen) * C)), "eyeOpenL" in i && x("eyeLOpen", y(i.eyeOpenL) * C), "eyeSmile" in i && (x("eyeSmile", i.eyeSmile), "eyeSmileL" in i || x("eyeSmileL", i.eyeSmile)), "eyeSmileL" in i && x("eyeSmileL", i.eyeSmileL);
      for (const d of ["mouthOpen", "mouthForm", "blush", "browY", "browAngle"])
        d in i && !(A && d === "blush") && x(d, d === "mouthOpen" || d === "blush" ? Math.max(0, i[d]) : i[d]);
    }
    const N = this.speechMouth(t);
    return N ? (this.lipOpen = N[0], this.lipForm = N[1]) : this.lipOpen !== null && !this.speaking && !this.kana && (this.lipOpen = null), this.lipOpen !== null && (v.mouthOpen = Math.max(v.mouthOpen * 0.3, this.lipOpen), v.mouthForm = re(this.lipForm, -1, 1)), this.P = v, v;
  }
}
const at = {
  neutral: "normal",
  smile: "smile",
  shy: "shy",
  surprise: "surprise",
  halfLidded: "jito",
  angry: "angryTalk",
  sad: "sadTalk",
  wink: "wink"
}, Dt = { sad: { pitch: -6, gy: -0.45 }, angry: { pitch: -5, gy: 0 }, halfLidded: { pitch: -4, gy: -0.3 } }, Ae = (o, t, e) => Math.max(t, Math.min(e, o)), Me = Object.freeze({ eyeOpen: 1, eyeOpenL: 1, eyeSmile: 0, eyeSmileL: 0, blush: 0, browY: 0, browAngle: 0, mouthOpen: 0, gx: 0, gy: 0, pitch: 0 });
function Ht(o) {
  const t = nt[at[o]]?.p ?? {}, e = Dt[o] ?? {};
  return {
    eyeOpen: t.eyeOpen ?? 1,
    eyeOpenL: t.eyeOpenL ?? t.eyeOpen ?? 1,
    eyeSmile: t.eyeSmile ?? 0,
    eyeSmileL: t.eyeSmileL ?? t.eyeSmile ?? 0,
    blush: t.blush ?? 0,
    browY: t.browY ?? 0,
    browAngle: t.browAngle ?? 0,
    mouthOpen: t.mouthOpen ?? 0,
    gx: t.glance?.[0] ?? 0,
    gy: e.gy ?? t.glance?.[1] ?? 0,
    pitch: e.pitch ?? 0
  };
}
function jt(o, t) {
  const e = { ...o };
  return e.eyeROpen = (o.eyeROpen ?? 1) * t.eyeOpen, e.eyeLOpen = (o.eyeLOpen ?? 1) * t.eyeOpenL, e.eyeSmile = Math.max(o.eyeSmile ?? 0, t.eyeSmile), e.eyeSmileL = Math.max(o.eyeSmileL ?? o.eyeSmile ?? 0, t.eyeSmileL), e.blush = Math.max(o.blush ?? 0, t.blush), e.browY = Ae((o.browY ?? 0) + t.browY, -1, 1), e.browAngle = Ae((o.browAngle ?? 0) + t.browAngle, -1, 1), e.mouthOpen = Math.max(o.mouthOpen ?? 0, t.mouthOpen), e.gazeX = Ae((o.gazeX ?? 0) + t.gx, -1, 1), e.gazeY = Ae((o.gazeY ?? 0) + t.gy, -1, 1), e.angleY = Ae((o.angleY ?? 0) + t.pitch, -30, 30), e;
}
class Wt {
  constructor() {
    /** @type {keyof typeof OVERLAY_EXPRESSIONS} */
    Fe(this, "name", "neutral");
    Fe(this, "mix", { ...Me });
  }
  /** @param {string} name */
  set(t) {
    this.name = Object.hasOwn(at, t) ? (
      /** @type {keyof typeof OVERLAY_EXPRESSIONS} */
      t
    ) : "neutral";
  }
  /** True while an expression is shown or still fading out. */
  get active() {
    return this.name !== "neutral" || Object.keys(Me).some((t) => Math.abs(this.mix[t] - Me[t]) > 1e-3);
  }
  apply(t, e) {
    if (!this.active)
      return this.mix = { ...Me }, t;
    const a = Ht(this.name), i = 1 - Math.exp(-Math.max(0, e) * 12);
    for (const h of Object.keys(Me)) this.mix[h] += (a[h] - this.mix[h]) * i;
    return jt(t, this.mix);
  }
}
const Je = ["ball", "low", "crease", "lash"], Xe = /* @__PURE__ */ new Map(), Ue = /* @__PURE__ */ new Map();
async function Qe(o) {
  return Ue.has(o) || Ue.set(o, fetch(o).then((t) => {
    if (!t.ok) throw new Error(`failed to load ${o}`);
    return t.json();
  })), Ue.get(o);
}
function et(o) {
  if (Xe.has(o)) return Xe.get(o);
  const t = new Promise((e, a) => {
    const i = new Image();
    i.onload = () => e(i), i.onerror = () => a(new Error(`failed to load ${o}`)), i.src = o;
  });
  return Xe.set(o, t), t;
}
function ot(o, t) {
  const e = document.createElement("canvas");
  e.width = o.width, e.height = o.height;
  const a = e.getContext("2d");
  a.drawImage(o, 0, 0);
  const i = a.getImageData(0, 0, e.width, e.height).data, h = new Uint8Array(e.width * e.height);
  for (let g = 0; g < h.length; g++) h[g] = i[g * 4 + t];
  return h;
}
const ve = (o) => ot(o, 3);
function Gt(o, t) {
  const [e, a] = o.t.pivot, i = o.dir, h = o.pts, g = (N, x, A) => {
    const y = Math.min(1, Math.max(0, (A - N) / (x - N)));
    return y * y * (3 - 2 * y);
  }, M = Math.cos(o.phi[0]), O = Math.sin(o.phi[0]), w = Math.cos(o.phi[1]), _ = Math.sin(o.phi[1]), v = t.rest, C = t.pos;
  for (let N = 0; N < v.length; N += 2) {
    const x = v[N] - e, A = v[N + 1] - a, y = x * i[0] + A * i[1], d = h[0][0] + x * M - A * O, n = h[0][1] + x * O + A * M, s = x - i[0] * o.L1, p = A - i[1] * o.L1, r = h[1][0] + s * w - p * _, c = h[1][1] + s * _ + p * w, F = g(o.L1 * 0.55, o.L1 * 1.35, y);
    C[N] = d + (r - d) * F, C[N + 1] = n + (c - n) * F;
  }
}
async function $t(o, t) {
  const e = t.rig, a = ft(e), {
    IMG: i,
    EYES: h,
    baseWeights: g,
    deformBase: M,
    eyePartY: O,
    eyePartAlpha: w,
    handWeights: _,
    handFrame: v,
    deformHand: C,
    TASSELS: N
  } = a, { Renderer: x, buildGrid: A } = Tt(a, e), { Physics: y } = Rt(a, e), { createSprites: d } = Lt(a, e), n = (t.assetsBase ?? "").replace(/\/?$/, "/"), s = (m, E) => {
    if (t.assets) {
      if (!t.assets[m]) throw new Error(`Missing project asset: ${m}`);
      return t.assets[m];
    }
    return `${n}${m}${E === void 0 ? "" : `?b=${E}`}`;
  }, p = await Qe(s("layers.json")), r = ["base", ...e.hand ? ["hand"] : [], ...N.map((m) => m.name), ...[0, 1].flatMap((m) => Je.map((E) => `eye${m}_${E}`)), "hairmask"], c = Object.fromEntries(await Promise.all(r.map(async (m) => [m, await et(s(`${m}.png`, p.build))]))), F = ot(c.hairmask, 0), j = (m, E) => F[Math.min(i.h - 1, Math.max(0, Math.round(E))) * i.w + Math.min(i.w - 1, Math.max(0, Math.round(m)))] / 255, P = new x(o, { padTop: t.padTop ?? e.view.padTop, padSide: t.padSide ?? e.view.padSide, fit: t.fit }), L = { base: [0, 0, i.w, i.h], ...p.layers }, Y = A(L.base, e.mesh.baseCell, ve(c.base), c.base.width, e.mesh.fine), b = [];
  for (let m = 0; m < Y.rest.length / 2; m++) {
    const E = Y.rest[m * 2], H = Y.rest[m * 2 + 1];
    b.push(g(E, H, j(E, H)));
  }
  P.addLayer("base", c.base, Y, { face: !0 });
  const X = [];
  h.forEach((m, E) => {
    for (const H of Je) {
      const Q = `eye${E}_${H}`, oe = A(L[Q], H === "ball" ? e.mesh.eyeBallCell : e.mesh.eyeCell, ve(c[Q]), c[Q].width), se = [];
      for (let de = 0; de < oe.rest.length / 2; de++) se.push(g(oe.rest[de * 2], oe.rest[de * 2 + 1], 0));
      const me = P.addLayer(Q, c[Q], oe, { eyeBall: H === "ball" ? E : void 0 });
      X.push({ e: m, eye: E, part: H, mesh: oe, W: se, layer: me });
    }
  });
  let W = null, ne = !1, R = !1;
  try {
    {
      const m = await Qe(s("sprites/sprites.json"));
      R = "eyes_smile_0" in m.layers;
      const E = Object.fromEntries(await Promise.all(Object.keys(m.layers).map(async (H) => [H, await et(s(`sprites/${H}.png`, m.build))])));
      W = d(P, m, E, A, ve);
    }
  } catch (m) {
    console.warn("eye / mouth sprites not loaded:", m);
  }
  const V = N.map((m) => {
    const E = A(L[m.name], e.mesh.tasselCell, ve(c[m.name]), c[m.name].width);
    return P.addLayer(m.name, c[m.name], E);
  }), z = e.hand ? A(L.hand, e.mesh.handCell, ve(c.hand), c.hand.width) : { rest: [], pos: [] }, q = [];
  for (let m = 0; m < z.rest.length / 2; m++) q.push(_(z.rest[m * 2], z.rest[m * 2 + 1]));
  e.hand && P.addLayer("hand", c.hand, z);
  const G = new y(), B = new zt(e.view.gazeCenter ?? [e.head.cx, e.head.cy]), Z = /* @__PURE__ */ new Set();
  B.onMotion = (m) => {
    for (const E of Z) E(m);
  };
  let K = {}, J = 1, f = {};
  const u = new Wt(), l = [0, 0];
  function T(m) {
    const E = { ...B.update(m) };
    for (const [Q, oe] of Object.entries(K)) E[Q] = J === 1 ? oe : (E[Q] ?? 0) + (oe - (E[Q] ?? 0)) * J;
    B.lipOpen !== null && (E.mouthOpen = B.P.mouthOpen, (!t.preserveMouthForm || K.mouthForm === void 0) && (E.mouthForm = B.P.mouthForm));
    const H = u.apply(E, m);
    return ne && R && Math.min(H.eyeROpen ?? 1, H.eyeLOpen ?? 1) >= 0.25 ? (H.eyeROpen = H.eyeLOpen = 0.1, H.eyeSmile = H.eyeSmileL = 1) : (H.eyeSmile = 0, H.eyeSmileL = 0), f = H, H;
  }
  function k(m) {
    const E = T(m), H = G.step(E, m), Q = Y.pos, oe = Y.rest;
    for (let $ = 0; $ < b.length; $++)
      M(oe[$ * 2], oe[$ * 2 + 1], b[$], E, H, l), Q[$ * 2] = l[0], Q[$ * 2 + 1] = l[1];
    const se = ($) => W ? 1 : $;
    for (const $ of X) {
      const Se = se($.eye === 0 ? E.eyeROpen : E.eyeLOpen), Pe = $.eye === 0 ? E.eyeSmile : E.eyeSmileL ?? E.eyeSmile;
      $.layer.alpha = w($.part, Se, Pe);
      const ze = $.mesh.rest, De = $.mesh.pos;
      for (let pe = 0; pe < $.W.length; pe++) {
        const He = ze[pe * 2], it = ze[pe * 2 + 1];
        M(He, O($.e, $.part, He, it, Se, Pe), $.W[pe], E, H, l), De[pe * 2] = l[0], De[pe * 2 + 1] = l[1];
      }
    }
    const me = W?.update(E, H, m);
    if (me) for (const $ of X) me.eyes[$.eye] && ($.layer.alpha = 0);
    const de = z.pos, Ce = z.rest, st = v(E);
    for (let $ = 0; $ < q.length; $++)
      C(Ce[$ * 2], Ce[$ * 2 + 1], q[$], E, st, l), de[$ * 2] = l[0], de[$ * 2 + 1] = l[1];
    G.chains.forEach(($, Se) => Gt($, V[Se].mesh));
    const we = 7;
    P.draw({
      angleX: E.angleX,
      angleY: E.angleY,
      angleZ: E.angleZ,
      eyes: [
        se(E.eyeROpen),
        E.eyeSmile,
        E.gazeX * we,
        -E.gazeY * we * 0.6,
        se(E.eyeLOpen),
        E.eyeSmileL ?? E.eyeSmile,
        E.gazeX * we * 0.85,
        -E.gazeY * we * 0.6
      ],
      // with sprites the drawn mouths replace the shader-painted one
      mouthOpen: W ? 0 : E.mouthOpen,
      mouthForm: E.mouthForm,
      cheek: E.blush,
      showMesh: !1,
      originalAlpha: 0,
      joints: []
    });
  }
  let U = 0, S = performance.now(), I = !1;
  const D = (m) => {
    const E = Math.min(0.05, (m - S) / 1e3);
    S = m, k(E), U = requestAnimationFrame(D);
  };
  return t.manual || (U = requestAnimationFrame(D)), {
    motions: [
      ...Object.entries(Ie).map(([m, E]) => ({ id: m, label: E.label, idle: !1 })),
      ...Object.entries(Ne).map(([m, E]) => ({ id: m, label: E.label, idle: !0 }))
    ],
    setParameters(m, E = 1) {
      K = { ...m }, J = Math.min(1, Math.max(0, Number(E) || 0));
    },
    getParameters() {
      return { ...f };
    },
    /** 0..1 loudness of the voice being played (e.g. normalised RMS). */
    setVoiceLevel(m) {
      B.setVoiceLevel(m);
    },
    /** true while TTS audio is playing: idle motions pause and the head nods along. */
    setSpeaking(m) {
      B.setSpeaking(m);
    },
    /** AITuber OnAir emotion tag: happy / sad / angry / surprised / relaxed / neutral (or null). */
    setEmotion(m, E) {
      B.setEmotion(m, E);
    },
    /** Live expression layered over tracking (see OVERLAY_EXPRESSIONS); 'neutral' clears it. */
    setExpression(m) {
      u.set(m);
    },
    setKizgin(m) {
      ne = !!m;
    },
    kizginCizimVar() {
      return R;
    },
    getExpression() {
      return { name: u.name, active: u.active };
    },
    /** How much the head moves with the voice while speaking (1 = default, calmer below). */
    setTalkGain(m) {
      B.talkGain = Math.max(0, Number(m) || 0);
    },
    /** Play a motion or idle motion by id (see `motions`). */
    play(m) {
      B.hasMotion(m) && B.playMotion(m);
    },
    /** Move the mouth through the vowels of kana text (no audio; for previews). */
    speakKana(m, E) {
      B.speakKana(String(m ?? ""), E);
    },
    holdMouth(m) {
      B.holdMouth(m);
    },
    stopLipSync() {
      B.stopLipSync();
    },
    getLipSyncState() {
      return B.getLipSyncState();
    },
    setAutoIdle(m) {
      B.autoIdle = !!m;
    },
    setLighting(m) {
      P.setLighting(m);
    },
    getLightingStats() {
      return { ...P.lightingStats };
    },
    setAutoMotion(m) {
      B.autoMotion = !!m;
    },
    /** Hair / tassel sway multiplier (1 = default). */
    setSwayGain(m) {
      G.gain = m;
    },
    /** Called with the motion id when a motion starts and with null when it ends. */
    onMotion(m) {
      return Z.add(m), () => Z.delete(m);
    },
    /** Advance the simulation by `sec` and draw (for tests / hidden tabs). */
    advance(m, E = 60) {
      if (!I)
        if (m === 0) k(0);
        else for (let H = 0; H < Math.round(m * E); H++) k(1 / E);
    },
    /** Update motion and lip sync without drawing a hidden preview. */
    advanceParameters(m) {
      I || T(m);
    },
    destroy() {
      I || (I = !0, cancelAnimationFrame(U), Z.clear(), P.destroy());
    }
  };
}
async function Zt(o, t) {
  return $t(o, { ...t, rig: ut(t.rig) });
}
async function qt(o, t, e) {
  t = String(t || "").replace(/\/?$/, "/");
  const a = await fetch(t + "rig.json");
  if (!a.ok) throw new Error("rig.json yüklenemedi: " + a.status);
  const i = await a.json(), h = await Zt(o, Object.assign({}, e || {}, { rig: i, assetsBase: t + "built/" }));
  let g = !1;
  return h.kapat = function() {
    if (!g) {
      g = !0, h.destroy();
      try {
        const M = o.getContext("webgl2"), O = M && M.getExtension("WEBGL_lose_context");
        O && O.loseContext();
      } catch {
      }
    }
  }, h;
}
export {
  qt as olustur
};
