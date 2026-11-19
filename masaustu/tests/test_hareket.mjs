// Masaüstü Yuki doğallık katmanı (web/hareket.js) — saf testler. Kullanım: node tests/test_hareket.mjs
import { SETLER, yay, yayZinciri, gurultu, Kirpma, rastgele, hareketKur, gecisAgirlik } from '../web/hareket.js';

let gecti = 0, kaldi = 0;
const kontrol = (ad, kosul, ayrinti = '') => {
  if (kosul) { gecti++; console.log('  ✓', ad); } else { kaldi++; console.log('  ✗', ad, ayrinti); }
};
const DT = 1 / 24;

console.log('— kritik sönümlü yay');
{
  const d = { x: 0, v: 0 }; let enCok = 0, hizlar = [];
  for (let i = 0; i < 96; i++) { yay(d, 1, 1.5, DT); enCok = Math.max(enCok, d.x); hizlar.push(d.v); }
  kontrol('hedefi aşmaz (aşım yok)', enCok <= 1 + 1e-9, enCok);
  kontrol('4 sn sonra hedefte (|1-x| < 0,001)', Math.abs(1 - d.x) < 1e-3, d.x);
  // baş için iki kademeli yay: yumuşak başlangıç + ivme sürekli
  const z = { x: 0, v: 0 }, zh = []; let zCok = 0;
  for (let i = 0; i < 120; i++) { yayZinciri(z, 1, 1.6, DT); zh.push(z.v); zCok = Math.max(zCok, z.x); }
  const zTepe = Math.max(...zh);
  kontrol('zincir: ilk karede hız tepenin %20\'sinden az (S eğrisi; tek kademe %72)', zh[0] < 0.2 * zTepe, [zh[0], zTepe]);
  kontrol('zincir: tepe hıza en az 4 karede çıkar', zh.indexOf(zTepe) >= 4, zh.indexOf(zTepe));
  kontrol('zincir: aşım yok', zCok <= 1 + 1e-6, zCok);
  // hedef aniden ters dönünce bir karedeki hız değişimi küçük (üstel yumuşatmada ve tek kademede sıçrıyordu)
  const e = { x: 0, v: 0 }; for (let i = 0; i < 12; i++) yayZinciri(e, 1, 1.6, DT);
  const v0 = e.v; yayZinciri(e, -1, 1.6, DT);
  const tek = { x: 0, v: 0 }; for (let i = 0; i < 12; i++) yay(tek, 1, 1.6, DT);
  const t0 = tek.v; yay(tek, -1, 1.6, DT);
  kontrol('zincir: hedef ters dönünce bir karede hız değişimi tek kademenin üçte birinden az',
          Math.abs(e.v - v0) < Math.abs(tek.v - t0) / 3, [Math.abs(e.v - v0), Math.abs(tek.v - t0)]);
  const f = { x: 0, v: 0 }; yay(f, 1, 1.5, 5);
  kontrol('çok büyük dt\'de de kararlı (patlamaz)', Number.isFinite(f.x) && f.x <= 1 + 1e-9 && f.x >= 0, f.x);
}

console.log('— göz kırpma');
{
  const k = new Kirpma(SETLER.a, rastgele(3)); const v = []; for (let i = 0; i < 24 * 120; i++) v.push(k.adim(DT));
  const basla = []; for (let i = 1; i < v.length; i++) if (v[i] > 0.6 && v[i - 1] <= 0.6) basla.push(i);
  const sure = basla.map(i => { let j = i; while (j < v.length && v[j] > 0.3) j++; return (j - i) / 24; });
  kontrol('120 sn\'de 15-50 kırpma (insan ≈ dakikada 10-25)', basla.length >= 15 && basla.length <= 50, basla.length);
  kontrol('her kırpma tek kareden uzun (≥ 0,08 sn)', sure.every(s => s >= 0.08), sure.slice(0, 5));
  const ara = basla.slice(1).map((b, i) => (b - basla[i]) / 24);
  const uzun = ara.filter(a => a >= 0.6);
  kontrol('aralıklar sabit değil (en az 6 farklı değer)', new Set(uzun.map(a => a.toFixed(2))).size >= 6, uzun.slice(0, 6));
  kontrol('ara sıra çift kırpma var (< 0,6 sn aralık)', ara.some(a => a < 0.6), ara.filter(a => a < 0.6).length);
  // açılış kapanıştan uzun (insan gözü: hızlı kapanır, yavaş açılır)
  const i0 = basla[0]; let ust = i0; while (v[ust] < 1) ust++;
  let alt = ust; while (v[alt] > 0.05) alt++;
  let ilk = i0; while (ilk > 0 && v[ilk - 1] > 0.05) ilk--;
  kontrol('açılış kapanıştan uzun', alt - ust > ust - ilk, [ust - ilk, alt - ust]);
  const t = new Kirpma(SETLER.a, rastgele(4)); t.adim(DT); t.tetikle(1); let kirpti = false;
  for (let i = 0; i < 6; i++) if (t.adim(DT) > 0.5) kirpti = true;
  kontrol('bakış değişiminde tetiklenen kırpma 0,25 sn içinde gelir', kirpti);
}

console.log('— gürültü (tekrar eden döngü yok)');
{
  const g = gurultu(9); const s = []; for (let t = 0; t < 40; t += 0.05) s.push(g(t));
  kontrol('değer [-1, 1] aralığında', s.every(x => x >= -1 && x <= 1));
  const fark = s.slice(1).map((x, i) => Math.abs(x - s[i]));
  kontrol('sürekli (komşu örnek farkı < 0,2)', Math.max(...fark) < 0.2, Math.max(...fark));
  // periyot yok: 10 sn kaydırınca dizi kendine benzemez
  const kay = 200; let ort = 0; for (let i = 0; i + kay < s.length; i++) ort += Math.abs(s[i] - s[i + kay]);
  kontrol('10 sn kaydırınca tekrar etmiyor (ort. fark > 0,15)', ort / (s.length - kay) > 0.15, ort / (s.length - kay));
}

console.log('— hareket katmanı');
{
  const h = hareketKur('a', false, 7); const o = []; for (let i = 0; i < 24 * 20; i++) o.push(h.adim(DT, { hedef: null, uyku: false }));
  const nefes = o.map(x => x.nefes);
  kontrol('nefes 0-1 arasında ve dolu dolu', Math.min(...nefes) < 0.05 && Math.max(...nefes) > 0.95);
  const tepe = []; for (let i = 1; i < nefes.length - 1; i++) if (nefes[i] > nefes[i - 1] && nefes[i] >= nefes[i + 1] && nefes[i] > 0.9) tepe.push(i / 24);
  const per = tepe.slice(1).map((x, i) => +(x - tepe[i]).toFixed(2));
  kontrol('nefes periyodu A aralığında (4,6-5,6 sn) ve kayıyor', per.length >= 2 && per.every(p => p >= 4.4 && p <= 5.8) && new Set(per).size > 1, per);
  const ag = o.map(x => x.agirlik);
  kontrol('ağırlık aktarma var ve küçük (|x| ≤ ayar)', Math.max(...ag.map(Math.abs)) > 0.004 && Math.max(...ag.map(Math.abs)) <= SETLER.a.agirlik, Math.max(...ag));
  // bakış: göz önce, baş sonra
  const b = hareketKur('a', false, 7); for (let i = 0; i < 24; i++) b.adim(DT, { hedef: null, uyku: false });
  let gozYari = null, basYari = null;
  for (let i = 0; i < 48; i++) {
    const r = b.adim(DT, { hedef: [0.5, 0], uyku: false });
    if (gozYari === null && r.gozW >= 0.5) gozYari = i;
    if (basYari === null && r.basYaw >= 0.25) basYari = i;
  }
  kontrol('bakışta göz başı öncüler (göz %50 < baş %50)', gozYari !== null && basYari !== null && gozYari < basYari, [gozYari, basYari]);
  const u = hareketKur('a', false, 7); let r; for (let i = 0; i < 48; i++) r = u.adim(DT, { hedef: [0.5, 0], uyku: true });
  kontrol('uykuda bakış yok', r.gozW < 0.01 && Math.abs(r.basYaw) < 0.01, [r.gozW, r.basYaw]);
  const az = hareketKur('a', true, 7);
  kontrol('azaltılmış hareket: salınım ve sakkad küçülür', az.ayar.salinim < SETLER.a.salinim && az.ayar.sakkad === 0);
  kontrol('B, A\'dan canlı (salınım, bakış hızı)', SETLER.b.salinim > SETLER.a.salinim && SETLER.b.basFrek > SETLER.a.basFrek);
  kontrol('bilinmeyen set → A', hareketKur('x').ayar.ad === 'sakin');
  kontrol('geçiş ağırlığı yumuşak eğri (0 → 1, ortada 0,5, uçlarda düz)', gecisAgirlik(0, 1) === 0 && gecisAgirlik(1, 1) === 1
          && Math.abs(gecisAgirlik(0.5, 1) - 0.5) < 1e-9 && gecisAgirlik(0.05, 1) < 0.01);
}

console.log(`\nhareket: ${gecti} geçti, ${kaldi} kaldı`);
process.exit(kaldi ? 1 : 0);
