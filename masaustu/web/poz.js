// Masaüstü Yuki — arayüzle etkileşim pozları. Saf hesap: THREE dışarıdan verilir, node ile gerçek three
// matematiğiyle test edilir (masaustu/tests/test_poz.mjs). yuki-tam.html pozun hedef kemik dönüşlerini kurulumda bir kez
// çözer (pozCoz), her karede mixer'ın sonucundan bu hedefe ağırlıkla geçer (slerp).
//
// Neden "uzuv yönü + el hedefi": VRM normalize kemiklerinin dinlenme pozu T-pozudur ve yerel eksenleri model eksenleriyle
// hizalıdır (x = Yuki'nin solu, y = yukarı, z = öne/izleyene). Pozu Euler açılarıyla yazmak her kemikte eksen sırası
// tahmini ister; "sol uyluk öne-aşağı baksın" yazmak okunur, çözücü ebeveyn zincirine göre yerel dönüşe çevirir (swing).
// El, dizin ya da çubuğun üstündeki bir noktaya iki kemikli analitik IK ile gider (dirsek yönü verilir).
//
// Pozlar (kullanıcı 10-25 ~21:00, iki ekran görüntüsü):
//   otur — PANEL'in üst kenarına oturur, sağ bacak sol dizin üstünden atılı (bacak bacak üstüne), eller üstteki uylukta.
//   uzan — giriş çubuğunun ÜSTÜNE yan uzanır (şef kararı 21:42): sağ yanı çubukta, sağ ön kol çubuğa dayalı (destek),
//          gövde hafif doğrulmuş, bacaklar çubuk boyunca, üstteki (sol) bacak dizden hafif kırık. Baş solda (ekranın ortasına);: aynalı kullanılır → baş SAĞDA (aşağıda ayna()).
// Kök (vrm.scene) dönüşü kalça çevresinde: kalça yerinde kalır, beden onun etrafında döner (uzan = yana yatma).

export const POZLAR = {
  otur: {
    kok: [0, -0.22, 0],               // ayaktaki ile aynı: yüzü hafifçe ekranın ortasına
    euler: {
      hips: [0.0, 0, 0],
      spine: [-0.05, 0, 0], chest: [0.03, 0, 0],       // dik oturuş, göğüs hafif öne
      leftFoot: [0.35, 0, 0], rightFoot: [0.55, 0, 0], // ayak uçları uzanır (zarif çizgi)
      leftToes: [0, 0, 0], rightToes: [0, 0, 0],        // boşta klibi parmakları oynatmasın (kadraj animasyonsuz ölçülür)
    },
    yon: {
      leftUpperLeg: [-0.12, -0.17, 1], leftLowerLeg: [-0.2, -1, -0.04],         // alttaki (sol) bacak: uyluk öne, baldır aşağı
      rightUpperLeg: [0.42, 0.44, 1],  rightLowerLeg: [0.46, -1, 0.24],         // üstteki (sağ): sol dizin üstünden çapraz,
                                                                                // baldırlar V açar (1×'te iki bacak ayrı okunur)
      // (kullanıcı 10-26 "elleri havada duruyor"): avuç aşağı, parmaklar uyluk boyunca dize doğru, uç hafif aşağı.
      // Yön verilmezse el ön kol doğrultusunda boşluğa uzanıyordu.
      leftHand: [0.066, 0.255, 0.965], rightHand: [0.534, 0.216, 0.817],
    },
    // İki el üstteki (sağ) UYLUĞUN üstünde: sol el dizin 12 cm gerisinde, sağ el 24 cm gerisinde (kalçaya yakın). Dirsek
    // aşağı, gövdeye yakın (yanlara açık dirsek "eller belde" gibi okunuyordu — goz). Hedef = bilek; avuç yüzeyden
    // ≈1 cm yukarıda (uyluk üst normali boyunca 9,5–10,5 cm). Eski hedef dizin 8 cm ÜSTÜYDÜ → el–bacak boşluğu 8–9 cm.
    // Daha alçağı (≤ 9 cm) yukiIcIce'yi 13'ün üstüne çıkarıyor; 7 cm'de el deriye gömülüyor (yüzey normaline göre 270+
    // köşe). Ölçüm: 2026-10-26, poz turu 4.
    el: {
      leftUpperArm: { hedef: ['rightLowerLeg', [-0.06, 0.033, -0.174]], dirsek: [0.5, -1, -0.3] },
      rightUpperArm: { hedef: ['rightLowerLeg', [-0.123, -0.002, -0.274]], dirsek: [-0.5, -1, -0.3] },
    },
    kol: true,                         // üst klip (el sallama) oynarken kollar klibe bırakılır
    temas: 'otur',
  },
  uzan: {
    kok: [0, 0, Math.PI / 2],          // +90° Z: baş ekranın soluna, sağ yanı aşağı; kalça → ayak çizgisi çubuğa paralel
    euler: {
      hips: [0, 0, 0],
      spine: [0, 0.08, -0.42], chest: [0, 0.06, -0.3],  // yan bükülme: omuzlar çubuktan kalkar, izleyene hafif döner
      neck: [0, 0, 0.16], head: [0.05, 0, 0.22],         // baş gövde çizgisinden hafif doğrulur
      leftFoot: [0.45, 0, 0], rightFoot: [0.5, 0, 0], leftToes: [0, 0, 0], rightToes: [0, 0, 0],
      rightHand: [0, 0, -0.45],                            // destek eli çubukta düz (sarkmasın)
    },
    yon: {
      rightUpperLeg: [-0.06, -1, 0.04],  rightLowerLeg: [-0.03, -1, -0.02],    // alttaki bacak çubuk boyunca düz
      leftUpperLeg: [-0.08, -1, 0.3],    leftLowerLeg: [-0.06, -1, -0.02],     // üstteki: diz hafif öne kırık, alttakine batmaz
      rightUpperArm: [-0.88, 0.22, 0.52], rightLowerArm: [-0.08, 1, 0.45],       // destek: dirsek çubukta, ön kol başa doğru
      leftUpperArm: [-0.25, -1, 0.3],    leftLowerArm: [-0.18, -1, 0.5],       // üstteki kol yan boyunca, el kalçada
    },
    el: {},
    kol: false,                        // destek kolu klip oynarken de yerinde kalır
    temas: 'alt',
  },
};

// Ayna: sol ↔ sağ kemik adları, x bileşeni ve y/z dönüşleri ters. Uzanma aynalı kullanılır: baş çubuğun SAĞ
// ucunda. Neden: "…bir şey sor" başlığı ve durum satırı ortalı; sağ uçta yazısız alan soldakinden geniş (1900×1015'te
// 195 px'e 126 px) → dirsekli pozun omzu/saçı durum yazısına binmiyor (solda "Si" harflerine biniyordu, 262–281 px).
const _taraf = b => b.startsWith('left') ? 'right' + b.slice(4) : b.startsWith('right') ? 'left' + b.slice(5) : b;
export function ayna(spec) {
  const ad = o => Object.fromEntries(Object.entries(o || {}).map(([b, v]) => [_taraf(b), v]));
  const vx = v => [-v[0], v[1], v[2]], eul = e => [e[0], -e[1], -e[2]];
  return { ...spec, kok: eul(spec.kok),
    euler: Object.fromEntries(Object.entries(ad(spec.euler)).map(([b, e]) => [b, eul(e)])),
    yon: Object.fromEntries(Object.entries(ad(spec.yon)).map(([b, v]) => [b, vx(v)])),
    el: Object.fromEntries(Object.entries(ad(spec.el)).map(([b, e]) => [b, { hedef: [_taraf(e.hedef[0]), vx(e.hedef[1])], dirsek: vx(e.dirsek) }])) };
}
POZLAR.uzan = ayna(POZLAR.uzan);

const SIRA = ['hips', 'spine', 'chest', 'upperChest', 'neck', 'head',
  'leftUpperLeg', 'leftLowerLeg', 'leftFoot', 'leftToes', 'rightUpperLeg', 'rightLowerLeg', 'rightFoot', 'rightToes',
  'leftShoulder', 'leftUpperArm', 'leftLowerArm', 'leftHand', 'rightShoulder', 'rightUpperArm', 'rightLowerArm', 'rightHand'];
const COCUK = { leftUpperLeg: 'leftLowerLeg', leftLowerLeg: 'leftFoot', rightUpperLeg: 'rightLowerLeg', rightLowerLeg: 'rightFoot',
  leftUpperArm: 'leftLowerArm', leftLowerArm: 'leftHand', rightUpperArm: 'rightLowerArm', rightLowerArm: 'rightHand',
  leftHand: 'leftMiddleProximal', rightHand: 'rightMiddleProximal' };   // el yönü = bilek → orta parmak kökü
export const KOL_KEMIK = new Set(['leftUpperArm', 'leftLowerArm', 'leftHand', 'rightUpperArm', 'rightLowerArm', 'rightHand']);

// İki kemikli analitik IK: omuz S, hedef H, kemik boyları a (üst) b (alt), dirsek yönü kutup → [üst yön, alt yön].
// Hedef erişilemezse kol o yöne uzanır (|S-H| a+b'ye kenetlenir), dirsek hiç ters bükülmez.
export function ikiKemik(T, S, H, a, b, kutup) {
  const fark = H.clone().sub(S), d0 = fark.length() || 1e-6;
  const d = Math.min(Math.max(d0, Math.abs(a - b) + 1e-4), a + b - 1e-4);
  const u = fark.divideScalar(d0);
  const v = kutup.clone().sub(u.clone().multiplyScalar(kutup.dot(u)));
  if (v.lengthSq() < 1e-8) v.set(0, 0, 1).sub(u.clone().multiplyScalar(u.z));
  v.normalize();
  const cosA = (a * a + d * d - b * b) / (2 * a * d), sinA = Math.sqrt(Math.max(0, 1 - cosA * cosA));
  const E = S.clone().add(u.clone().multiplyScalar(a * cosA)).add(v.clone().multiplyScalar(a * sinA));
  const Hd = S.clone().add(u.clone().multiplyScalar(d));
  return [E.clone().sub(S).normalize(), Hd.sub(E).normalize()];
}

// Pozu çöz: konum = {kemik: Vector3} dinlenme (T-poz) model uzayı konumları, ebeveyn = {kemik: ebeveyn kemik | null}.
// Döner: { yerel: {kemik: Quaternion}, model: {kemik: Quaternion}, P: {kemik: Vector3 (pozlu konum)}, kok: Quaternion }.
export function pozCoz(T, spec, konum, ebeveyn) {
  const yerel = {}, model = {}, P = {};
  const I = new T.Quaternion();
  const swing = (b, d) => {          // dinlenme yönünden (kemik→çocuk) istenen yöne en kısa dönüş, model uzayında
    const r = konum[COCUK[b]].clone().sub(konum[b]).normalize();
    return new T.Quaternion().setFromUnitVectors(r, new T.Vector3(...d).normalize());
  };
  const koy = (b, Qm) => {
    const ana = ebeveyn[b], Qa = ana ? model[ana] : I;
    model[b] = Qm;
    yerel[b] = Qa.clone().invert().multiply(Qm);
    P[b] = ana ? P[ana].clone().add(konum[b].clone().sub(konum[ana]).applyQuaternion(model[ana])) : konum[b].clone();
  };
  const elYon = {};
  for (const b of SIRA) {
    if (!konum[b]) continue;
    const ana = ebeveyn[b], Qa = ana ? model[ana] : I;
    if (spec.el && spec.el[b] && !elYon[b]) {        // el hedefi: bacaklar çözülmüş olmalı (SIRA'da önce gelir)
      const e = spec.el[b], alt = COCUK[b], uc = COCUK[alt];
      // omuz konumu: ebeveyn zinciri pozlu (P[ana] hazır)
      const S = P[ana].clone().add(konum[b].clone().sub(konum[ana]).applyQuaternion(Qa));
      const H = P[e.hedef[0]].clone().add(new T.Vector3(...e.hedef[1]));
      const a = konum[alt].distanceTo(konum[b]), bb = konum[uc].distanceTo(konum[alt]);
      const [d1, d2] = ikiKemik(T, S, H, a, bb, new T.Vector3(...e.dirsek).normalize());
      elYon[b] = d1.toArray(); elYon[alt] = d2.toArray();
    }
    const yon = elYon[b] || (spec.yon && spec.yon[b]);
    if (yon && COCUK[b] && konum[COCUK[b]]) koy(b, swing(b, yon));
    else if (spec.euler && spec.euler[b]) koy(b, Qa.clone().multiply(new T.Quaternion().setFromEuler(new T.Euler(...spec.euler[b], 'YXZ'))));
    else koy(b, Qa.clone());
  }
  const kok = new T.Quaternion().setFromEuler(new T.Euler(...spec.kok, 'YXZ'));
  return { yerel, model, P, kok };
}

// Poza giriş/çıkış ağırlığı: yumuşak başlar, yumuşak oturur (smootherstep). t sn, sure sn → 0..1
export function pozEgri(t, sure) {
  const x = Math.min(1, Math.max(0, t / sure));
  return x * x * x * (x * (x * 6 - 15) + 10);
}

// Kalça çevresinde kök dönüşü: kalça dünya konumu değişmesin. pivot = kalçanın vrm.scene yerel konumu,
// q0 = varsayılan kök dönüşü (ayakta), q = istenen. Döner: vrm.scene.position.
export function kokKonum(T, pivot, q0, q) {
  return pivot.clone().applyQuaternion(q0).sub(pivot.clone().applyQuaternion(q));
}
