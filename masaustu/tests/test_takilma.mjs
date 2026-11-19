// Masaüstü Yuki takılma sayacı (web/takilma.js) — saf testler. Kullanım: node tests/test_takilma.mjs
import { esik, sayacKur, araligiKaydet, isKaydet, SON_N } from '../web/takilma.js';

let gecti = 0, kaldi = 0;
const kontrol = (ad, kosul, ayrinti = '') => {
  if (kosul) { gecti++; console.log('  ✓', ad); } else { kaldi++; console.log('  ✗', ad, ayrinti); }
};

console.log('— eşik');
kontrol('uyanık 24 fps → 120 ms', esik(24) === 120, esik(24));
kontrol('uyku 10 fps → 250 ms (2,5 kare)', esik(10) === 250, esik(10));
kontrol('fps 0 bölme hatası vermez', Number.isFinite(esik(0)), esik(0));

console.log('— kare aralığı');
{
  const S = sayacKur();
  kontrol('normal kare (42 ms) takılma değil', araligiKaydet(S, 42, 24, 1) === null && S.sayi === 0);
  kontrol('eşikte (120 ms) takılma değil', araligiKaydet(S, 120, 24, 2) === null && S.sayi === 0);
  kontrol('121 ms uyanıkken takılma', araligiKaydet(S, 121, 24, 3) === 'takilma' && S.sayi === 1);
  kontrol('uykuda 200 ms takılma değil', araligiKaydet(S, 200, 10, 4) === null && S.sayi === 1);
  kontrol('uykuda 260 ms takılma', araligiKaydet(S, 260, 10, 5) === 'takilma' && S.sayi === 2);
  kontrol('≥ 2 sn boşluk takılma değil, uzun sayılır', araligiKaydet(S, 2500, 24, 6) === 'uzun' && S.sayi === 2 && S.uzun === 1);
  kontrol('son kayıt [saat, ms]', JSON.stringify(S.son) === JSON.stringify([[3, 121], [5, 260]]), JSON.stringify(S.son));
  kontrol('en uzun takılma', S.max_ms === 260, S.max_ms);
  kontrol('her kare sayılır', S.kare === 6, S.kare);
  kontrol('negatif/NaN aralık yok sayılır', araligiKaydet(S, NaN, 24, 7) === null && araligiKaydet(S, -5, 24, 8) === null && S.sayi === 2);
  for (let i = 0; i < 30; i++) araligiKaydet(S, 300, 24, 100 + i);
  kontrol(`son ${SON_N} kayıt tutulur, en yenisi sonda`, S.son.length === SON_N && S.son[SON_N - 1][0] === 129, S.son.length);
}

console.log('— iş süresi');
{
  const S = sayacKur();
  isKaydet(S, 4.26); isKaydet(S, 2, 3.04); isKaydet(S, 9.1, 1);
  kontrol('kare işi en çok', S.is_max_ms === 9.1, S.is_max_ms);
  kontrol('bölge okuma son + en çok', S.bolge_son_ms === 1 && S.bolge_max_ms === 3, [S.bolge_son_ms, S.bolge_max_ms]);
}

console.log(`\n${gecti} geçti · ${kaldi} kaldı`);
process.exit(kaldi ? 1 : 0);
