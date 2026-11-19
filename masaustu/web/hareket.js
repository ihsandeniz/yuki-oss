// Masaüstü Yuki — doğallık katmanı. Saf hesap: THREE'ye bağımlı değil, node ile test edilir
// (masaustu/tests/test_hareket.mjs). yuki-tam.html her karede Hareket.adim()'ı çağırır, dönen ofsetleri kemiklere uygular.
//
// Teşhis (2026-10-25 doğallık ölçümü) → burada karşılığı:
//   bakış hedef değişince hız sıçrıyordu (üstel yumuşatma)      → baş: iki kademeli kritik sönümlü yay (hız + ivme sürekli),
//                                                                 göz önce (hızlı yay) / baş sonra
//   göz kırpma tek kare, seyrek, hep aynı                       → kapanma 70 ms + açılma 130 ms eğrisi, rastgele aralık, çift kırpma
//   nefes tek sinüs, sabit 4,2 sn                               → asimetrik nefes (alış kısa, veriş uzun), periyot yavaşça kayar
//   duruş donuk (kalça 0 m kayma), baş iki sabit sinüs          → ağırlık aktarma (omurga yana, göğüs ters) + yavaş gürültü
//   gözler dondurulmuş gibi                                     → boşta sakkad (küçük göz sıçramaları)
// Ayar setleri: a = sakin (varsayılan), b = canlı. prefers-reduced-motion: genlikler küçülür, sakkad kapanır.

export const SETLER = {
  a: {
    ad: 'sakin',
    nefesSn: [4.6, 5.6], nefesGogus: 0.018, nefesOmurga: 0.006, nefesOmuz: 0.014,
    agirlikSn: 11, agirlik: 0.022, salinim: 0.016, salinimSn: 7,
    gozFrek: 4.5, basFrek: 1.6, basGecikme: 0.14, govdePay: 0.12, bakisEgme: 0.0,
    kirpAra: [2.6, 6.2], kirpCift: 0.12, kirpBakis: 0.3, kirpKapan: 0.075, kirpTut: 0.03, kirpAcil: 0.14,
    sakkadAra: [1.6, 4.2], sakkad: 0.035,
    kolGevse: 0.07, dirsek: 0.10,
    gecisSn: 0.5, donusSn: 0.8, klipPay: 0.7, ifadeHiz: 4.5, irkilme: 0.035,
  },
  b: {
    ad: 'canli',
    nefesSn: [3.8, 4.8], nefesGogus: 0.024, nefesOmurga: 0.009, nefesOmuz: 0.02,
    agirlikSn: 8, agirlik: 0.034, salinim: 0.026, salinimSn: 5,
    gozFrek: 6, basFrek: 2.4, basGecikme: 0.09, govdePay: 0.18, bakisEgme: 0.07,
    kirpAra: [2.0, 5.0], kirpCift: 0.2, kirpBakis: 0.45, kirpKapan: 0.065, kirpTut: 0.02, kirpAcil: 0.12,
    sakkadAra: [1.0, 3.0], sakkad: 0.05,
    kolGevse: 0.09, dirsek: 0.14,
    gecisSn: 0.38, donusSn: 0.6, klipPay: 1.0, ifadeHiz: 6.5, irkilme: 0.055,
  },
};

// Kritik sönümlü yay (kapalı biçim, her dt'de kararlı): aşım yok, hız hedef değişince sıçramaz.
export function yay(d, hedef, frek, dt) {
  const w = 2 * Math.PI * frek, e = Math.exp(-w * dt), fark = d.x - hedef;
  const t1 = (d.v + w * fark) * dt;
  d.x = hedef + (fark + t1) * e;
  d.v = (d.v - w * t1) * e;
  return d.x;
}

// İki kademeli yay: hedef önce hızlı bir yaydan geçer → başlangıç S eğrisi, ivme de sürekli (tek kademede ivme
// hedef değişince bir anda ω²·fark oluyordu; 24 fps'de tepe hıza 2,5 karede çıkıyordu — test_hareket ölçtü).
export function yayZinciri(d, hedef, frek, dt) {
  if (!d.ara) d.ara = { x: d.x, v: 0 };
  return yay(d, yay(d.ara, hedef, frek * 1.7, dt), frek, dt);
}

export const yumusak = x => (x <= 0 ? 0 : x >= 1 ? 1 : x * x * (3 - 2 * x));
const yumusak5 = x => (x <= 0 ? 0 : x >= 1 ? 1 : x * x * x * (x * (6 * x - 15) + 10));

// Tohumlu rastgele (mulberry32) — testte ve kayıtta aynı dizi.
export function rastgele(tohum = 1) {
  let s = tohum >>> 0;
  return () => {
    s = (s + 0x6D2B79F5) | 0;
    let t = Math.imul(s ^ (s >>> 15), 1 | s);
    t = (t + Math.imul(t ^ (t >>> 7), 61 | t)) ^ t;
    return ((t ^ (t >>> 14)) >>> 0) / 4294967296;
  };
}

// 1B değer gürültüsü: tamsayı noktalarda rastgele değer, arası yumuşak ara değer → [-1, 1], tekrarsız yavaş salınım.
export function gurultu(tohum) {
  const r = rastgele(tohum), tablo = Array.from({ length: 256 }, () => r() * 2 - 1);
  return t => {
    const i = Math.floor(t), f = t - i;
    const a = tablo[((i % 256) + 256) % 256], b = tablo[(((i + 1) % 256) + 256) % 256];
    return a + (b - a) * yumusak5(f);
  };
}

// Göz kırpma: kapanma (hızlanarak) → kısa tutma → açılma (yavaşlayarak). Aralık rastgele, ara sıra çift.
export class Kirpma {
  constructor(ayar, r) { this.a = ayar; this.r = r; this.t = 0; this.sonraki = this._ara(); this.faz = -1; this.cift = false; }
  _ara() { const [a, b] = this.a.kirpAra; return a + (b - a) * Math.pow(this.r(), 1.4); }
  tetikle(olasilik = 1) { if (this.faz < 0 && this.r() < olasilik) this.sonraki = Math.min(this.sonraki, this.t + 0.05); }
  adim(dt) {
    this.t += dt;
    const { kirpKapan: k, kirpTut: tu, kirpAcil: ac } = this.a;
    if (this.faz < 0 && this.t >= this.sonraki) { this.faz = 0; }
    if (this.faz < 0) return 0;
    this.faz += dt;
    const f = this.faz;
    let v;
    if (f < k) v = Math.pow(f / k, 2);                       // kapanış: yavaş başlar, hızlanır
    else if (f < k + tu) v = 1;
    else if (f < k + tu + ac) v = 1 - yumusak((f - k - tu) / ac);
    else {
      v = 0; this.faz = -1;
      if (!this.cift && this.r() < this.a.kirpCift) { this.cift = true; this.sonraki = this.t + 0.12 + this.r() * 0.1; }
      else { this.cift = false; this.sonraki = this.t + this._ara(); }
    }
    return v;
  }
}

// Bütün katmanlar: tek nesne, kare başına adim().
export function hareketKur(ad = 'a', azalt = false, tohum = 7) {
  const A = { ...(SETLER[ad] || SETLER.a) };
  if (azalt) {           // prefers-reduced-motion: süs hareketleri küçülür, işlevsel olanlar (bakış, kırpma) kalır
    for (const k of ['agirlik', 'salinim', 'nefesOmuz', 'kolGevse', 'irkilme', 'bakisEgme']) A[k] *= 0.35;
    A.sakkad = 0; A.basFrek *= 0.8; A.govdePay *= 0.5;
  }
  const r = rastgele(tohum);
  const g = [gurultu(tohum + 1), gurultu(tohum + 2), gurultu(tohum + 3), gurultu(tohum + 4), gurultu(tohum + 5), gurultu(tohum + 6)];
  const kirpma = new Kirpma(A, r);
  const S = {
    t: 0, nefesFaz: 0,
    goz: { x: 0, v: 0 }, basYaw: { x: 0, v: 0 }, basPitch: { x: 0, v: 0 },
    hedef: null, hedefDegisti: -9, basHedef: [0, 0], sakkad: [0, 0], sakkadSonraki: 1 + r() * 2,
    irkilme: { x: 0, v: 0 }, irkilmeHedef: 0, irkilmeBitis: 0,
  };
  return {
    ayar: A, kirpma,
    // hedef: [yaw, pitch] (rad, baş için kenetli) ya da null · uyku: boolean
    adim(dt, { hedef, uyku }) {
      S.t += dt;
      const t = S.t;
      // nefes: periyot gürültüyle yavaşça kayar; dalga asimetrik (alış %40, veriş %60)
      const per = A.nefesSn[0] + (A.nefesSn[1] - A.nefesSn[0]) * (0.5 + 0.5 * g[0](t / 13)) * (uyku ? 1.25 : 1);
      S.nefesFaz = (S.nefesFaz + dt / per) % 1;
      const f = S.nefesFaz, nefes = f < 0.4 ? yumusak(f / 0.4) : 1 - yumusak((f - 0.4) / 0.6);
      // ağırlık aktarma + baş salınımı: çok yavaş gürültü
      const agirlik = A.agirlik * g[1](t / A.agirlikSn) * (uyku ? 0.4 : 1);
      const sal = uyku ? [0, 0, 0] : [A.salinim * g[2](t / A.salinimSn), A.salinim * 1.2 * g[3](t / (A.salinimSn * 1.3)),
                                      A.salinim * 0.8 * g[4](t / (A.salinimSn * 0.9))];
      // bakış: hedef değişince gözler hemen (hızlı yay), baş basGecikme sonra (yavaş yay); gövde başın bir payı
      const yeni = hedef ? hedef.map(v => +v.toFixed(3)).join() : '';
      if (yeni !== S.hedef) {
        const buyuk = !S.hedef || !hedef || Math.abs(hedef[0] - S.basHedef[0]) > 0.25;
        if (buyuk) kirpma.tetikle(A.kirpBakis);                 // büyük bakış değişiminde göz kırpması (insanlarda olağan)
        S.hedef = yeni; S.hedefDegisti = t;
      }
      const aktif = hedef && !uyku;
      const gozW = yay(S.goz, aktif ? 1 : 0, A.gozFrek, dt);
      if (t - S.hedefDegisti >= A.basGecikme) S.basHedef = aktif ? hedef : [0, 0];
      const basYaw = yayZinciri(S.basYaw, S.basHedef[0], A.basFrek, dt);
      const basPitch = yayZinciri(S.basPitch, S.basHedef[1], A.basFrek, dt);
      // sakkad: boştayken gözler ara sıra küçük bir noktadan ötekine sıçrar (yalnız göz, baş değil)
      if (t >= S.sakkadSonraki) {
        S.sakkad = A.sakkad ? [(r() * 2 - 1) * A.sakkad, (r() * 2 - 1) * A.sakkad * 0.6] : [0, 0];
        S.sakkadSonraki = t + A.sakkadAra[0] + r() * (A.sakkadAra[1] - A.sakkadAra[0]);
      }
      // ırkılma (tepki öncesi hazırlık): kısa bir dikleşme, yayla söner
      if (t >= S.irkilmeBitis) S.irkilmeHedef = 0;
      const irk = yay(S.irkilme, S.irkilmeHedef, 3.5, dt);
      const kirp = kirpma.adim(dt);
      return {
        nefes, agirlik, sal, kirp, gozW, basYaw, basPitch, govdeYaw: basYaw * A.govdePay,
        egme: basYaw * A.bakisEgme, sakkad: uyku ? [0, 0] : S.sakkad, irk,
      };
    },
    irkil() { S.irkilmeHedef = A.irkilme; S.irkilmeBitis = S.t + 0.12; },
  };
}

// Klip ağırlığı: geçiş süresince yumuşak eğri (doğrusal crossfade yerine) — 0..1.
export function gecisAgirlik(gecen, sure) { return yumusak(gecen / sure); }
