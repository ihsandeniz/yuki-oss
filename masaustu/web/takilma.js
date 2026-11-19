// Masaüstü Yuki takılma sayacı — saf, GTK/WebGL'siz (test: node tests/test_takilma.mjs).
// NEDEN VAR: "arada takılıyor" ölçülemiyordu — takılma anında kimse saat tutmuyordu (2026-10-25
// takılma ölçümü). Sayfa iki kare arası beklenenden uzunsa kendisi kaydeder; host saniyede bir
// okuyup log'a yazar (yuki_govde.py _bolge_yokla). Böylece kullanıcı "şimdi takıldı" deyince saat elde olur.
//
// Eşik: uyanık 24 fps'te 120 ms (≈3 kare), uyku 10 fps'te 250 ms (2,5 kare) — max(120, 2,5 × kare süresi).
// ≥ 2 sn'lik boşluk takılma sayılmaz, ayrı sayılır (`uzun`): gizli/örtülü pencerede WebKit zamanlayıcıyı kısar.
export const ESIK_MIN_MS = 120, ESIK_KAT = 2.5, UZUN_MS = 2000, SON_N = 20;

export const esik = fps => Math.max(ESIK_MIN_MS, ESIK_KAT * 1000 / Math.max(1, fps));

export function sayacKur() {
  return { kare: 0, sayi: 0, uzun: 0, son: [], max_ms: 0, is_max_ms: 0, bolge_max_ms: 0, bolge_son_ms: 0 };
}

const r1 = x => Math.round(x * 10) / 10;

// Bir kare aralığını kaydet. `saat` duvar saati ms (Date.now) — log'a basılır. Dönen: 'takilma' | 'uzun' | null.
export function araligiKaydet(S, aralikMs, fps, saat) {
  S.kare++;
  if (!(aralikMs > 0)) return null;
  if (aralikMs >= UZUN_MS) { S.uzun++; return 'uzun'; }
  if (aralikMs <= esik(fps)) return null;
  S.sayi++;
  if (aralikMs > S.max_ms) S.max_ms = r1(aralikMs);
  S.son.push([saat, Math.round(aralikMs)]);
  if (S.son.length > SON_N) S.son.shift();
  return 'takilma';
}

// Kare işinin (güncelle + çiz) ve saniyelik tıklama bölgesi okumasının süresi: takılma sayfanın kendi işinden mi?
export function isKaydet(S, isMs, bolgeMs = null) {
  if (isMs > S.is_max_ms) S.is_max_ms = r1(isMs);
  if (bolgeMs != null) { S.bolge_son_ms = r1(bolgeMs); if (bolgeMs > S.bolge_max_ms) S.bolge_max_ms = r1(bolgeMs); }
}
