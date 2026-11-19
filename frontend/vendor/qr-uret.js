/* ════════════════════════════════════════════════════════════════════════════
   qr-uret.js — bağımlılıksız QR kodu üreteci (2026-09-18)

   NEDEN KENDİ KODUMUZ
   ───────────────────
   Cihaz eşleştirme QR ister. Üç yol vardı:
     · Python `qrcode` paketi  → `shell_id` DEĞİŞİR, mevcut müşteri 457 MB tam
       paket indirir. Tek bir QR için kabul edilemez takas.
     · Hazır JS kütüphanesi    → 30 KB minified, denetlenemez kod.
     · Bu dosya                → sıfır bağımlılık, `frontend/**` olduğu için
       delta yüküyle gider (1-2 MB), okunur ve denetlenebilir.

   DOĞRULAMA — "çalışıyor" iddiası ölçülmüştür
   ───────────────────────────────────────────
   Ürettiği matris PNG'ye çevrilip `zbarimg` (bağımsız okuyucu) ile okundu ve
   girdi metniyle karakter karakter karşılaştırıldı. Test:
   `frontend/tests/qr-dogrula.mjs` — kendi ürettiğimiz QR'ı KENDİMİZ okumuyoruz,
   üçüncü bir araç okuyor. (Bu vault'ta "yeşil test doğru şeye baktığını
   kanıtlamaz" dersi pahalıya öğrenildi.)

   KAPSAM
   ──────
   · Byte modu (UTF-8) — eşleştirme URL'i ASCII, ama Türkçe ad da taşınabilsin
   · Versiyon 1-10 (otomatik seçim) — 70 karakterlik URL için fazlasıyla yeter
   · ECC seviyesi M (%15 kurtarma) — telefon kamerası için dengeli
   · 8 maskenin hepsi denenir, ceza puanı en düşüğü seçilir (standart gereği)

   Kullanım:
     const matris = QRUret.matris("ws://192.168.1.5:8001/ws/agent?eslestirme=AB12");
     const svg    = QRUret.svg(matris, { kenar: 4, boyut: 256 });
   ════════════════════════════════════════════════════════════════════════════ */
(function (global) {
  'use strict';

  // ── Galois alanı GF(256) — Reed-Solomon için ──────────────────────────────
  const EXP = new Uint8Array(512);
  const LOG = new Uint8Array(256);
  (function () {
    let x = 1;
    for (let i = 0; i < 255; i++) {
      EXP[i] = x;
      LOG[x] = i;
      x <<= 1;
      if (x & 0x100) x ^= 0x11d;      // QR'ın indirgenemez polinomu
    }
    for (let i = 255; i < 512; i++) EXP[i] = EXP[i - 255];
  })();

  const carp = (a, b) => (a === 0 || b === 0) ? 0 : EXP[LOG[a] + LOG[b]];

  /** Üretici polinom: ∏(x − α^i). Katsayılar **lider önce** (yüksek→düşük derece).
   *
   * 🪤 Sıralama kritik: `eccHesapla` klasik LFSR bölmesi yapar ve `gen[0]`'ın
   * lider (=1) olduğunu varsayar. İlk yazımda katsayılar ters sıradaydı
   * (düşük→yüksek); kod "çalışıyor" görünüyordu ama ürettiği QR **hiçbir
   * okuyucu tarafından okunmuyordu**. Sessiz kalmasının sebebi: bozuk ECC de
   * geçerli bir bayt dizisidir, yalnız okuyucu reddeder.
   * Yakalayan şey: `frontend/tests/qr-dogrula.mjs` içindeki syndrome kapısı —
   * veri‖ecc polinomu üretecin katı olmalı, yani mesaj(α^i)=0.
   */
  function uretecPoli(derece) {
    let p = [1];
    for (let i = 0; i < derece; i++) {
      const yeni = new Array(p.length + 1).fill(0);
      for (let j = 0; j < p.length; j++) {
        yeni[j] ^= p[j];                        // × x  (derece +1)
        yeni[j + 1] ^= carp(p[j], EXP[i]);      // × α^i
      }
      p = yeni;
    }
    return p;
  }

  function eccHesapla(veri, eccSayisi) {
    const gen = uretecPoli(eccSayisi);
    const kalan = new Array(eccSayisi).fill(0);
    for (const bayt of veri) {
      const katsayi = bayt ^ kalan[0];
      kalan.shift();
      kalan.push(0);
      if (katsayi !== 0) {
        for (let i = 0; i < eccSayisi; i++) {
          kalan[i] ^= carp(gen[i + 1], katsayi);
        }
      }
    }
    return kalan;
  }

  // ── Versiyon tabloları (1-10, ECC seviyesi M) ─────────────────────────────
  // [toplam kod sözcüğü, ECC/blok, grup1 blok, grup1 veri, grup2 blok, grup2 veri]
  const VERSIYON_M = {
    1:  [26,   10, 1, 16,  0, 0],
    2:  [44,   16, 1, 28,  0, 0],
    3:  [70,   26, 1, 44,  0, 0],
    4:  [100,  18, 2, 32,  0, 0],
    5:  [134,  24, 2, 43,  0, 0],
    6:  [172,  16, 4, 27,  0, 0],
    7:  [196,  18, 4, 31,  0, 0],
    8:  [242,  22, 2, 38,  2, 39],
    9:  [292,  22, 3, 36,  2, 37],
    10: [346,  26, 4, 43,  1, 44],
  };

  /** Hizalama deseni merkezleri (versiyon 2+). */
  const HIZALAMA = {
    1: [], 2: [6, 18], 3: [6, 22], 4: [6, 26], 5: [6, 30],
    6: [6, 34], 7: [6, 22, 38], 8: [6, 24, 42], 9: [6, 26, 46], 10: [6, 28, 50],
  };

  function veriKapasitesi(v) {
    const [, ecc, b1, d1, b2, d2] = VERSIYON_M[v];
    return b1 * d1 + b2 * d2;
  }

  // ── Bit akışı ─────────────────────────────────────────────────────────────
  function BitAkisi() {
    this.bitler = [];
  }
  BitAkisi.prototype.ekle = function (deger, uzunluk) {
    for (let i = uzunluk - 1; i >= 0; i--) this.bitler.push((deger >> i) & 1);
  };

  // ── Veri kodlama (byte modu) ──────────────────────────────────────────────
  function veriKodla(metin) {
    const baytlar = Array.from(new TextEncoder().encode(metin));

    let versiyon = 0;
    for (let v = 1; v <= 10; v++) {
      // 4 bit mod + uzunluk alanı (v<10 → 8 bit) + veri
      const uzunlukBiti = v < 10 ? 8 : 16;
      const gereken = Math.ceil((4 + uzunlukBiti + baytlar.length * 8) / 8);
      if (gereken <= veriKapasitesi(v)) { versiyon = v; break; }
    }
    if (!versiyon) throw new Error('QR: metin çok uzun (versiyon 10 sınırı aşıldı)');

    const uzunlukBiti = versiyon < 10 ? 8 : 16;
    const akis = new BitAkisi();
    akis.ekle(0b0100, 4);                       // byte modu
    akis.ekle(baytlar.length, uzunlukBiti);
    for (const b of baytlar) akis.ekle(b, 8);

    const kapasiteBit = veriKapasitesi(versiyon) * 8;
    // Sonlandırıcı — en fazla 4 bit
    const sonlandirici = Math.min(4, kapasiteBit - akis.bitler.length);
    akis.ekle(0, sonlandirici);
    // Bayta hizala
    while (akis.bitler.length % 8 !== 0) akis.bitler.push(0);

    // Kod sözcüklerine çevir
    const kodlar = [];
    for (let i = 0; i < akis.bitler.length; i += 8) {
      let b = 0;
      for (let j = 0; j < 8; j++) b = (b << 1) | akis.bitler[i + j];
      kodlar.push(b);
    }
    // Dolgu deseni (standart: 0xEC 0x11 dönüşümlü)
    const dolgu = [0xec, 0x11];
    let k = 0;
    while (kodlar.length < veriKapasitesi(versiyon)) kodlar.push(dolgu[k++ % 2]);

    return { versiyon, kodlar };
  }

  /** Blokları böl, ECC hesapla, standardın istediği SIRAYLA ilmekle. */
  function blokla(versiyon, kodlar) {
    const [, eccSayisi, b1, d1, b2, d2] = VERSIYON_M[versiyon];
    const bloklar = [];
    let p = 0;
    for (let i = 0; i < b1; i++) { bloklar.push(kodlar.slice(p, p + d1)); p += d1; }
    for (let i = 0; i < b2; i++) { bloklar.push(kodlar.slice(p, p + d2)); p += d2; }

    const eccBloklari = bloklar.map(b => eccHesapla(b, eccSayisi));

    const sonuc = [];
    const enUzun = Math.max(...bloklar.map(b => b.length));
    for (let i = 0; i < enUzun; i++) {
      for (const b of bloklar) if (i < b.length) sonuc.push(b[i]);
    }
    for (let i = 0; i < eccSayisi; i++) {
      for (const e of eccBloklari) sonuc.push(e[i]);
    }
    return sonuc;
  }

  // ── Matris ────────────────────────────────────────────────────────────────
  function bosMatris(boyut) {
    const m = [];
    for (let i = 0; i < boyut; i++) m.push(new Array(boyut).fill(null));
    return m;
  }

  function finderKoy(m, satir, sutun) {
    for (let r = -1; r <= 7; r++) {
      for (let c = -1; c <= 7; c++) {
        const y = satir + r, x = sutun + c;
        if (y < 0 || y >= m.length || x < 0 || x >= m.length) continue;
        const kenarda = (r === -1 || r === 7 || c === -1 || c === 7);
        const dis = (r === 0 || r === 6 || c === 0 || c === 6);
        const ic = (r >= 2 && r <= 4 && c >= 2 && c <= 4);
        m[y][x] = kenarda ? 0 : (dis || ic ? 1 : 0);
      }
    }
  }

  function hizalamaKoy(m, versiyon) {
    const merkezler = HIZALAMA[versiyon];
    const son = m.length - 1;
    for (const a of merkezler) {
      for (const b of merkezler) {
        // finder'larla çakışan üç köşe atlanır
        if ((a <= 8 && b <= 8) || (a <= 8 && b >= son - 8) || (a >= son - 8 && b <= 8)) continue;
        for (let r = -2; r <= 2; r++) {
          for (let c = -2; c <= 2; c++) {
            const halka = Math.max(Math.abs(r), Math.abs(c));
            m[a + r][b + c] = (halka === 1) ? 0 : 1;
          }
        }
      }
    }
  }

  function iskeletKur(versiyon) {
    const boyut = versiyon * 4 + 17;
    const m = bosMatris(boyut);

    finderKoy(m, 0, 0);
    finderKoy(m, 0, boyut - 7);
    finderKoy(m, boyut - 7, 0);
    hizalamaKoy(m, versiyon);

    // Zamanlama desenleri
    for (let i = 8; i < boyut - 8; i++) {
      const deger = (i % 2 === 0) ? 1 : 0;
      if (m[6][i] === null) m[6][i] = deger;
      if (m[i][6] === null) m[i][6] = deger;
    }
    // Karanlık modül (standart)
    m[boyut - 8][8] = 1;
    return m;
  }

  /** Biçim bilgisi alanlarını rezerve et (geçici 0). */
  function bicimRezerve(m) {
    const boyut = m.length;
    for (let i = 0; i < 9; i++) {
      if (m[8][i] === null) m[8][i] = 0;
      if (m[i][8] === null) m[i][8] = 0;
    }
    for (let i = 0; i < 8; i++) {
      if (m[8][boyut - 1 - i] === null) m[8][boyut - 1 - i] = 0;
      if (m[boyut - 1 - i][8] === null) m[boyut - 1 - i][8] = 0;
    }
  }

  const MASKE = [
    (r, c) => (r + c) % 2 === 0,
    (r) => r % 2 === 0,
    (r, c) => c % 3 === 0,
    (r, c) => (r + c) % 3 === 0,
    (r, c) => (Math.floor(r / 2) + Math.floor(c / 3)) % 2 === 0,
    (r, c) => ((r * c) % 2) + ((r * c) % 3) === 0,
    (r, c) => (((r * c) % 2) + ((r * c) % 3)) % 2 === 0,
    (r, c) => (((r + c) % 2) + ((r * c) % 3)) % 2 === 0,
  ];

  function veriYerlestir(iskelet, veri, maskeNo) {
    const boyut = iskelet.length;
    const m = iskelet.map(satir => satir.slice());
    let bitIndex = 0;
    const toplamBit = veri.length * 8;

    let yukari = true;
    for (let sutun = boyut - 1; sutun > 0; sutun -= 2) {
      if (sutun === 6) sutun--;                 // zamanlama sütunu atlanır
      for (let i = 0; i < boyut; i++) {
        const satir = yukari ? (boyut - 1 - i) : i;
        for (let j = 0; j < 2; j++) {
          const c = sutun - j;
          if (m[satir][c] !== null) continue;   // fonksiyon deseni — dokunma
          let bit = 0;
          if (bitIndex < toplamBit) {
            bit = (veri[bitIndex >> 3] >> (7 - (bitIndex & 7))) & 1;
            bitIndex++;
          }
          if (MASKE[maskeNo](satir, c)) bit ^= 1;
          m[satir][c] = bit;
        }
      }
      yukari = !yukari;
    }
    return m;
  }

  /** Biçim bilgisi: ECC M (0b00) + maske; BCH(15,5) + XOR maskesi. */
  function bicimYaz(m, maskeNo) {
    const veri = (0b00 << 3) | maskeNo;
    let bch = veri << 10;
    for (let i = 4; i >= 0; i--) {
      if ((bch >> (i + 10)) & 1) bch ^= 0b10100110111 << i;
    }
    const bicim = ((veri << 10) | bch) ^ 0b101010000010010;

    const boyut = m.length;
    // 🪤 Bit sırası: yerleşimin İLK konumu (8,0) biçimin EN ANLAMLI bitini taşır.
    // İlk yazımda `(bicim >> i)` vardı — sıra tersti, okuyucu ECC seviyesini ve
    // maskeyi yanlış çözüyordu, QR hiç okunmuyordu. Ölçümle bulundu: qrencode'un
    // dört seviyesi (L/M/Q/H) ters sırayla okununca standart kodlara (01/00/11/10)
    // birebir oturdu, düz sırayla oturmadı.
    for (let i = 0; i < 15; i++) {
      const bit = (bicim >> (14 - i)) & 1;
      // Sol üst
      if (i < 6)       m[8][i] = bit;
      else if (i < 8)  m[8][i + 1] = bit;
      else if (i === 8) m[7][8] = bit;
      else              m[14 - i][8] = bit;
      // Kopya (sağ üst + sol alt)
      if (i < 8)  m[boyut - 1 - i][8] = bit;
      else        m[8][boyut - 15 + i] = bit;
    }
    m[boyut - 8][8] = 1;                        // karanlık modül korunur
  }

  /** Standardın 4 ceza kuralı — en düşük puanlı maske seçilir. */
  function cezaPuani(m) {
    const n = m.length;
    let puan = 0;

    // ① Aynı renkten 5+ ardışık
    for (let yon = 0; yon < 2; yon++) {
      for (let i = 0; i < n; i++) {
        let sayac = 1;
        for (let j = 1; j < n; j++) {
          const a = yon ? m[j][i] : m[i][j];
          const b = yon ? m[j - 1][i] : m[i][j - 1];
          if (a === b) { sayac++; }
          else { if (sayac >= 5) puan += 3 + (sayac - 5); sayac = 1; }
        }
        if (sayac >= 5) puan += 3 + (sayac - 5);
      }
    }
    // ② 2x2 aynı renk blokları
    for (let i = 0; i < n - 1; i++) {
      for (let j = 0; j < n - 1; j++) {
        const v = m[i][j];
        if (v === m[i][j + 1] && v === m[i + 1][j] && v === m[i + 1][j + 1]) puan += 3;
      }
    }
    // ③ Finder benzeri desen (1:1:3:1:1)
    const desen = [1, 0, 1, 1, 1, 0, 1, 0, 0, 0, 0];
    const tersDesen = desen.slice().reverse();
    const esles = (dizi, d) => {
      let s = 0;
      for (let i = 0; i + d.length <= dizi.length; i++) {
        let tam = true;
        for (let j = 0; j < d.length; j++) if (dizi[i + j] !== d[j]) { tam = false; break; }
        if (tam) s += 40;
      }
      return s;
    };
    for (let i = 0; i < n; i++) {
      const satir = m[i];
      const sutun = m.map(s => s[i]);
      puan += esles(satir, desen) + esles(satir, tersDesen);
      puan += esles(sutun, desen) + esles(sutun, tersDesen);
    }
    // ④ Siyah/beyaz dengesi
    let siyah = 0;
    for (const satir of m) for (const v of satir) if (v) siyah++;
    const oran = (siyah * 100) / (n * n);
    puan += Math.floor(Math.abs(oran - 50) / 5) * 10;

    return puan;
  }

  function matris(metin) {
    const { versiyon, kodlar } = veriKodla(metin);
    const veri = blokla(versiyon, kodlar);

    const iskelet = iskeletKur(versiyon);
    bicimRezerve(iskelet);

    let enIyi = null, enIyiPuan = Infinity;
    for (let maske = 0; maske < 8; maske++) {
      const aday = veriYerlestir(iskelet, veri, maske);
      bicimYaz(aday, maske);
      const puan = cezaPuani(aday);
      if (puan < enIyiPuan) { enIyiPuan = puan; enIyi = aday; }
    }
    return enIyi;
  }

  /** Matrisi SVG'ye çevirir — <img> yok, dış istek yok (CSP dostu). */
  function svg(m, secenek) {
    const o = secenek || {};
    const kenar = o.kenar == null ? 4 : o.kenar;         // sessiz bölge (standart: 4)
    const boyut = o.boyut || 256;
    const n = m.length + kenar * 2;
    const yollar = [];
    for (let r = 0; r < m.length; r++) {
      for (let c = 0; c < m.length; c++) {
        if (m[r][c]) yollar.push(`M${c + kenar} ${r + kenar}h1v1h-1z`);
      }
    }
    return (
      `<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 ${n} ${n}" ` +
      `width="${boyut}" height="${boyut}" shape-rendering="crispEdges" role="img" ` +
      `aria-label="Eşleştirme QR kodu">` +
      `<rect width="${n}" height="${n}" fill="#fff"/>` +
      `<path d="${yollar.join('')}" fill="#000"/></svg>`
    );
  }

  // Dahili parçalar — YALNIZ doğrulama içindir (frontend/tests/qr-dogrula.mjs).
  // Panel kodu `matris`/`svg` dışında bir şey çağırmaz.
  const API = { matris, svg, _dahili: { veriKodla, blokla, eccHesapla } };
  if (typeof module !== 'undefined' && module.exports) module.exports = API;
  global.QRUret = API;
})(typeof globalThis !== 'undefined' ? globalThis : this);
