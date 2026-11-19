/* qr-dogrula.mjs — qr-uret.js'in ürettiği QR'ı BAĞIMSIZ bir okuyucuya okutur.
 *
 * 🔑 Neden böyle: kendi ürettiğimiz QR'ı kendi kodumuzla çözersek yalnız
 * "kodum kendi kendisiyle tutarlı" demiş oluruz. Burada matris PBM'e yazılır ve
 * `zbarimg` (zbar projesi, bizim kodumuzla ilgisi yok) okur; çıkan metin girdiyle
 * karakter karakter karşılaştırılır. Okuyucu geliştirme makinesinde, ÜRÜNDE DEĞİL.
 *
 * Koşum:  node frontend/tests/qr-dogrula.mjs
 * Gereken: zbarimg (yoksa test ATLANIR, sessizce YEŞİL SAYILMAZ)
 */
import { execFileSync } from 'node:child_process';
import { mkdtempSync, writeFileSync, rmSync } from 'node:fs';
import { tmpdir } from 'node:os';
import { join } from 'node:path';
import { createRequire } from 'node:module';

const require = createRequire(import.meta.url);
const QRUret = require('../vendor/qr-uret.js');

const ORNEKLER = [
  'ws://192.168.1.100:8001/ws/agent?eslestirme=ABCD2345',
  'ws://10.0.0.7:8001/ws/agent?eslestirme=XYZW9876&ad=Telefon',
  'ws://127.0.0.1:8001/ws/agent?eslestirme=QRST5555',
  // uzun ad + Türkçe karakter (UTF-8 yolu sınansın)
  'ws://192.168.68.112:8001/ws/agent?eslestirme=MNPQ7788&ad=Geliştirici%20Çalışma',
];

function zbarVar() {
  try { execFileSync('which', ['zbarimg'], { stdio: 'pipe' }); return true; }
  catch { return false; }
}

/** Matrisi PBM'e yaz — modül başına ÖLÇEK piksel (okuyucu için büyütülür). */
function pbmYaz(matris, yol, olcek = 8, kenar = 4) {
  const n = matris.length;
  const tam = (n + kenar * 2) * olcek;
  const satirlar = [];
  for (let y = 0; y < tam; y++) {
    const my = Math.floor(y / olcek) - kenar;
    const satir = [];
    for (let x = 0; x < tam; x++) {
      const mx = Math.floor(x / olcek) - kenar;
      const icerde = my >= 0 && my < n && mx >= 0 && mx < n;
      satir.push(icerde && matris[my][mx] ? '1' : '0');
    }
    satirlar.push(satir.join(' '));
  }
  writeFileSync(yol, `P1\n${tam} ${tam}\n${satirlar.join('\n')}\n`);
}

function oku(yol) {
  const cikti = execFileSync('zbarimg', ['--raw', '-q', yol], { encoding: 'utf-8' });
  return cikti.replace(/\n$/, '');
}

if (!zbarVar()) {
  console.log('⚠ zbarimg yok — doğrulama ATLANDI (yeşil sayılmaz, kur: zbar)');
  process.exit(2);
}

const dizin = mkdtempSync(join(tmpdir(), 'qr-dogrula-'));
let kusur = 0;

/* ── Reed-Solomon kapısı ───────────────────────────────────────────────────
 * RS'in tanımı: veri‖ecc polinomu üreteç polinomunun KATIDIR → mesaj(α^i)=0.
 * Bu kapı olmasaydı ilk yazımdaki üreteç-sırası hatası yalnız "QR okunmuyor"
 * diye görünürdü ve sebebi aranırken saatler giderdi. Matematiğe karşı ölçer,
 * dış test vektörüne güvenmez (hafızadan yazılan vektör ilk denemede yanlıştı).
 */
{
  const EXP = new Uint8Array(512), LOG = new Uint8Array(256);
  let x = 1;
  for (let i = 0; i < 255; i++) { EXP[i] = x; LOG[x] = i; x <<= 1; if (x & 0x100) x ^= 0x11d; }
  for (let i = 255; i < 512; i++) EXP[i] = EXP[i - 255];
  const carp = (a, b) => (a === 0 || b === 0) ? 0 : EXP[LOG[a] + LOG[b]];

  for (const [ad, veri, n] of [
    ['v1-M', Array.from({ length: 16 }, (_, i) => (i * 11 + 7) & 0xff), 10],
    ['v4-M', Array.from({ length: 32 }, (_, i) => (i * 7 + 3) & 0xff), 18],
    ['v3-M', Array.from({ length: 44 }, (_, i) => (i * 13 + 5) & 0xff), 26],
  ]) {
    const ecc = QRUret._dahili.eccHesapla(veri, n);
    const mesaj = [...veri, ...ecc];
    let tamam = true;
    for (let i = 0; i < n; i++) {
      let s = 0;
      for (const k of mesaj) s = carp(s, EXP[i]) ^ k;
      if (s !== 0) { tamam = false; break; }
    }
    if (tamam) {
      console.log(`✓ RS ${ad} — syndrome hepsi 0`);
    } else {
      console.log(`✗ RS ${ad} — syndrome sıfır DEĞİL (üreteç polinomu bozuk)`);
      kusur++;
    }
  }
}

try {
  for (const metin of ORNEKLER) {
    const m = QRUret.matris(metin);
    const yol = join(dizin, 'qr.pbm');
    pbmYaz(m, yol);
    let okunan;
    try {
      okunan = oku(yol);
    } catch (e) {
      console.log(`✗ OKUNAMADI (${m.length}×${m.length}): ${metin.slice(0, 50)}…`);
      kusur++;
      continue;
    }
    if (okunan === metin) {
      console.log(`✓ ${m.length}×${m.length}  ${metin.slice(0, 52)}${metin.length > 52 ? '…' : ''}`);
    } else {
      console.log(`✗ UYUŞMUYOR\n   beklenen: ${metin}\n   okunan  : ${okunan}`);
      kusur++;
    }
  }

  // SVG çıktısı da üretilebiliyor mu (panelde bu kullanılıyor)
  const svg = QRUret.svg(QRUret.matris(ORNEKLER[0]));
  if (!svg.startsWith('<svg') || !svg.includes('</svg>')) {
    console.log('✗ SVG çıktısı bozuk');
    kusur++;
  } else {
    console.log(`✓ SVG üretildi (${svg.length} karakter, dış istek yok)`);
  }
} finally {
  rmSync(dizin, { recursive: true, force: true });
}

console.log(kusur === 0
  ? `\n✅ ${ORNEKLER.length}/${ORNEKLER.length} QR bağımsız okuyucuyla doğrulandı`
  : `\n❌ ${kusur} kusur`);
process.exit(kusur === 0 ? 0 : 1);
