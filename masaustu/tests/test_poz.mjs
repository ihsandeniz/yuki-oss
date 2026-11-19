// Masaüstü Yuki etkileşim pozları (web/poz.js) — saf testler, gerçek three r160 matematiği.
// Kullanım: node tests/test_poz.mjs
import * as T from '../../frontend/vendor/three-0.160.0/three.module.min.js';
import { POZLAR, pozCoz, ikiKemik, pozEgri, kokKonum } from '../web/poz.js';

let gecti = 0, kaldi = 0;
const kontrol = (ad, kosul, ayrinti = '') => {
  if (kosul) { gecti++; console.log('  ✓', ad); } else { kaldi++; console.log('  ✗', ad, ayrinti); }
};
const V = (x, y, z) => new T.Vector3(x, y, z);

// Yuki'ye yakın oranlı T-poz iskeleti (m, model uzayı: x = Yuki'nin solu, y yukarı, z öne)
const konum = {
  hips: V(0, 0.82, 0), spine: V(0, 0.9, 0), chest: V(0, 1.02, 0), neck: V(0, 1.3, 0), head: V(0, 1.38, 0),
  leftUpperLeg: V(0.08, 0.78, 0), leftLowerLeg: V(0.08, 0.42, 0), leftFoot: V(0.08, 0.07, 0), leftToes: V(0.08, 0.02, 0.1),
  rightUpperLeg: V(-0.08, 0.78, 0), rightLowerLeg: V(-0.08, 0.42, 0), rightFoot: V(-0.08, 0.07, 0), rightToes: V(-0.08, 0.02, 0.1),
  leftShoulder: V(0.03, 1.25, 0), leftUpperArm: V(0.15, 1.25, 0), leftLowerArm: V(0.4, 1.25, 0), leftHand: V(0.63, 1.25, 0),
  rightShoulder: V(-0.03, 1.25, 0), rightUpperArm: V(-0.15, 1.25, 0), rightLowerArm: V(-0.4, 1.25, 0), rightHand: V(-0.63, 1.25, 0),
  leftMiddleProximal: V(0.71, 1.25, 0), rightMiddleProximal: V(-0.71, 1.25, 0),
};
const ebeveyn = { hips: null, spine: 'hips', chest: 'spine', neck: 'chest', head: 'neck',
  leftUpperLeg: 'hips', leftLowerLeg: 'leftUpperLeg', leftFoot: 'leftLowerLeg', leftToes: 'leftFoot',
  rightUpperLeg: 'hips', rightLowerLeg: 'rightUpperLeg', rightFoot: 'rightLowerLeg', rightToes: 'rightFoot',
  leftShoulder: 'chest', leftUpperArm: 'leftShoulder', leftLowerArm: 'leftUpperArm', leftHand: 'leftLowerArm',
  rightShoulder: 'chest', rightUpperArm: 'rightShoulder', rightLowerArm: 'rightUpperArm', rightHand: 'rightLowerArm',
  leftMiddleProximal: 'leftHand', rightMiddleProximal: 'rightHand' };
// el kemiğinin çocuğu (parmak kökü) pozCoz'da konumlanmaz → yön, dinlenme yönünün pozlu model dönüşüyle döndürülmesi
const yonu = (c, b, cocuk) => c.P[cocuk] ? c.P[cocuk].clone().sub(c.P[b]).normalize()
  : konum[cocuk].clone().sub(konum[b]).applyQuaternion(c.model[b]).normalize();

console.log('— iki kemikli IK');
{
  const S = V(0, 0, 0), a = 0.3, b = 0.25;
  const [d1, d2] = ikiKemik(T, S, V(0.3, -0.2, 0.1), a, b, V(0, 0, -1));
  const E = S.clone().addScaledVector(d1, a), H = E.clone().addScaledVector(d2, b);
  kontrol('erişilebilir hedefe el tam varır (< 1 mm)', H.distanceTo(V(0.3, -0.2, 0.1)) < 1e-3, H.toArray());
  kontrol('dirsek kutup tarafında (z < 0)', E.z < 0, E.toArray());
  const [e1, e2] = ikiKemik(T, S, V(2, 0, 0), a, b, V(0, 1, 0));
  kontrol('erişilemez hedef: kol o yöne düz uzanır, ters bükülmez', e1.x > 0.99 && e2.x > 0.99, [e1.toArray(), e2.toArray()]);
  const [f1] = ikiKemik(T, S, V(0, 0, 0), a, b, V(0, 1, 0));
  kontrol('hedef omuzda (sıfır uzaklık): NaN yok', Number.isFinite(f1.x + f1.y + f1.z), f1.toArray());
}

console.log('— poz çözücü');
for (const ad of Object.keys(POZLAR)) {
  const c = pozCoz(T, POZLAR[ad], konum, ebeveyn);
  const nan = Object.values(c.yerel).some(q => !Number.isFinite(q.x + q.y + q.z + q.w));
  kontrol(`${ad}: tüm yerel dönüşler sonlu`, !nan);
  for (const [b, d] of Object.entries(POZLAR[ad].yon)) {
    const cocuk = { leftUpperLeg: 'leftLowerLeg', leftLowerLeg: 'leftFoot', rightUpperLeg: 'rightLowerLeg', rightLowerLeg: 'rightFoot',
      leftUpperArm: 'leftLowerArm', leftLowerArm: 'leftHand', rightUpperArm: 'rightLowerArm', rightLowerArm: 'rightHand',
      leftHand: 'leftMiddleProximal', rightHand: 'rightMiddleProximal' }[b];
    const ac = yonu(c, b, cocuk).angleTo(V(...d).normalize());
    if (ac > 0.01) kontrol(`${ad}: ${b} istenen yönde`, false, ac);
  }
  kontrol(`${ad}: yazılan uzuv yönleri tutuyor (< 0,6°)`, true);
}
{
  const c = pozCoz(T, POZLAR.otur, konum, ebeveyn);
  // (kullanıcı 10-26 "elleri havada"): bilekler üstteki (sağ) uyluğun ÜSTÜNDE, uyluk çizgisinden 7–13 cm (yüzey ≈6 cm
  // + avuç). Eski hedef dizin 8 cm üstüydü; el ön kol doğrultusunda boşluğa uzanıyordu (gerçek modelde boşluk 8–9 cm).
  const K = c.P.rightUpperLeg, D = c.P.rightLowerLeg, KD = D.clone().sub(K);
  const uylukta = p => { const t = Math.max(0, Math.min(1, p.clone().sub(K).dot(KD) / KD.lengthSq()));
    const izd = K.clone().addScaledVector(KD, t); return { t, d: p.distanceTo(izd), ust: p.y - izd.y }; };
  const ul = uylukta(c.P.leftHand), ur = uylukta(c.P.rightHand);
  kontrol('otur: iki bilek de üstteki uyluk boyunca (kalça ile diz arasında, %15–%90)',
          [ul, ur].every(u => u.t > 0.15 && u.t < 0.9), [ul, ur]);
  kontrol('otur: bilekler uyluk çizgisinin 7–13 cm üstünde (yüzeye yakın, havada değil)',
          [ul, ur].every(u => u.d >= 0.07 && u.d <= 0.13 && u.ust > 0.05), [ul, ur]);
  kontrol('otur: eller birbirinden ayrı (bilekler ≥ 10 cm; aynı noktada el–el 73 köşe giriyordu)',
          c.P.leftHand.distanceTo(c.P.rightHand) >= 0.1, c.P.leftHand.distanceTo(c.P.rightHand));
  // avuç aşağı: T-pozda avuç −y'ye bakar; pozlu el kemiğinin model dönüşü onu hâlâ aşağı tutmalı (ters dönmüş el yok)
  const avuc = b => V(0, -1, 0).applyQuaternion(c.model[b]).y;
  kontrol('otur: avuçlar aşağı, uyluğa bakıyor (avuç normali y < −0,6)', avuc('leftHand') < -0.6 && avuc('rightHand') < -0.6,
          [avuc('leftHand'), avuc('rightHand')]);
  kontrol('otur: uyluklar öne (diz kalçadan en az 25 cm önde)', c.P.leftLowerLeg.z > 0.25 && c.P.rightLowerLeg.z > 0.25);
  kontrol('otur: sağ diz soldan yüksek ve sola geçmiş (bacak bacak üstüne)',
          c.P.rightLowerLeg.y > c.P.leftLowerLeg.y && c.P.rightLowerLeg.x > konum.rightUpperLeg.x + 0.1,
          [c.P.rightLowerLeg.toArray(), c.P.leftLowerLeg.toArray()]);
  kontrol('otur: ayaklar kalçanın altında (sarkar)', c.P.leftFoot.y < c.P.hips.y - 0.25 && c.P.rightFoot.y < c.P.hips.y - 0.2);
}
{
  const c = pozCoz(T, POZLAR.uzan, konum, ebeveyn), R = c.kok;
  const dun = n => c.P[n].clone().sub(konum.hips).applyQuaternion(R);   // kalça çevresinde kök dönüşü
  //: uzanma aynalı → baş ekranın SAĞINDA, alttaki taraf Yuki'nin solu
  kontrol('uzan (aynalı): baş ekranın sağında, ayaklar solunda', dun('head').x > 0.4 && dun('rightFoot').x < -0.6, [dun('head').x, dun('rightFoot').x]);
  const egim = dun('leftFoot').y - dun('leftUpperLeg').y;      // alttaki bacak (aynalı: sol): uyluk başı → ayak bileği
  kontrol('uzan: alttaki bacak çubuğa paralel (75 cm boyunca yükseklik farkı < 6 cm)', Math.abs(egim) < 0.06, egim);
  kontrol('uzan: dirsek omzun altında (destek), omuz kalçadan yüksek',
          dun('leftLowerArm').y < dun('leftUpperArm').y - 0.1 && dun('leftUpperArm').y > 0.05,
          [dun('leftLowerArm').y, dun('leftUpperArm').y]);
}

{
  const { ayna } = await import('../web/poz.js');
  const a = ayna({ kok: [0.1, 0.2, 0.3], euler: { leftFoot: [0.1, 0.2, 0.3] }, yon: { rightUpperArm: [-0.5, 0.2, 0.1] },
                   el: { leftUpperArm: { hedef: ['rightLowerLeg', [0.05, 0.1, 0]], dirsek: [1, -0.5, 0] } } });
  kontrol('ayna: sol↔sağ adlar, x ve y/z dönüşleri ters', JSON.stringify(a.kok) === '[0.1,-0.2,-0.3]'
          && JSON.stringify(a.euler.rightFoot) === '[0.1,-0.2,-0.3]' && JSON.stringify(a.yon.leftUpperArm) === '[0.5,0.2,0.1]'
          && a.el.rightUpperArm.hedef[0] === 'leftLowerLeg' && a.el.rightUpperArm.hedef[1][0] === -0.05 && a.el.rightUpperArm.dirsek[0] === -1,
          JSON.stringify(a));
}

console.log('— kök ve geçiş');
{
  const pivot = V(0, 0.82, 0), q0 = new T.Quaternion().setFromEuler(new T.Euler(0, -0.22, 0));
  const q = new T.Quaternion().setFromEuler(new T.Euler(0, 0, Math.PI / 2));
  const p = kokKonum(T, pivot, q0, q);
  const kalca0 = pivot.clone().applyQuaternion(q0), kalca1 = pivot.clone().applyQuaternion(q).add(p);
  kontrol('kök dönerken kalça dünyada yerinde (< 0,1 mm)', kalca0.distanceTo(kalca1) < 1e-4, kalca1.toArray());
  kontrol('geçiş eğrisi 0→1, uçlarda düz (hız 0)', pozEgri(0, 0.6) === 0 && pozEgri(0.6, 0.6) === 1
          && pozEgri(0.006, 0.6) < 1e-4 && 1 - pozEgri(0.594, 0.6) < 1e-4);
  let tek = true, onceki = -1;
  for (let t = 0; t <= 0.6; t += 0.01) { const w = pozEgri(t, 0.6); if (w < onceki) tek = false; onceki = w; }
  kontrol('geçiş eğrisi tekdüze (geri gitmez)', tek);
}

console.log(`\npoz: ${gecti} geçti, ${kaldi} kaldı`);
process.exit(kaldi ? 1 : 0);
