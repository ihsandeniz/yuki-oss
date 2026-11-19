/**
 * Motor bekleme — "60 saniye geçti mi" değil, **"motor ilerliyor mu"**.
 *
 * 🔴 Neden ayrı dosya: eski hâli `uygulama.js` içinde gömülüydü ve yalnız gerçek bir
 * Electron penceresi kurulunca çalışıyordu → hiç test edilmemişti. Kural burada duruyor
 * ki ölçülen kod ile satılan kod aynı olsun (`dis-baglanti.js` / `surum.js` dersi).
 *
 * ── Neden yazıldı (2026-08-11, R7) ───────────────────────────────────────────────
 * Sabit tavan: `waitForBackend(retries = 120)` × 500 ms = **tam 60 saniye**.
 * geliştiricinin Win10/8GB makinesinde motor **62. saniyede** hayat belirtisi gösterdi:
 * uygulama pes ettikten 2 sn sonra. Ekranda *"Backend başlamadı"* yazıp `app.quit()`
 * edildi — oysa log'da tek bir hata satırı yoktu, her şey sağlıklı başlıyordu.
 * Motor bozuk değildi, **geç kalmıştı**. Tavan Linux'ta SICAK ölçülen 1,55 sn'nin
 * 39 katı diye "bol" sanılmıştı; Windows'ta SOĞUK açılış (Defender `pybundle-win`'in
 * binlerce dosyasını tarar) hiç ölçülmemişti.
 *
 * 🔑 Sabit süre yanlış ölçüttür: aynı iş makineye/diske/antivirüse göre 2 sn de sürer
 * 5 dk da. Doğru soru **"motor ilerliyor mu"** — backend çıktı üretmeye devam ediyorsa
 * beklenir; uzun süre hiç ses çıkmıyorsa gerçekten takılmıştır.
 *
 * ── Vazgeçme ölçütü (üçü de gerekli) ─────────────────────────────────────────────
 *   ① süreç öldüyse            → ANINDA vazgeç (beklemek anlamsız, hiç gelmeyecek)
 *   ② `enAzMs` geçti           VE
 *   ③ `durgunlukMs`'tir hiç çıktı yok
 * Yedek olarak mutlak `tavanMs` — sonsuza kadar dönen bir açılış ekranı üretmemek için.
 *
 * ⚠️ Vazgeçmek **kapatmak değildir**: çağıran taraf kullanıcıya "beklemeye devam et"
 * seçeneği sunar (`uygulama.js`). Bu yüzden yanlış alarmın bedeli artık düşük —
 * eskiden yanlış alarm uygulamayı öldürüyordu.
 *
 * ⚠️ [VARSAYIM] Eşikler ölçümle değil akıl yürütmeyle seçildi; Windows'ta soğuk açılış
 * HİÇ ölçülmedi (R7 § Ç5). Ölçüm gelince buradaki üç sayı güncellenmeli. Sayıların
 * seçilme gerekçesi:
 *   - `durgunlukMs` 90 sn: Python'un import fazı boyunca stdout'a **hiçbir şey**
 *     yazılmıyor (log'da "Waiting for application startup." ile sonraki satır arasında
 *     boşluk var). 45 sn olsaydı sağlıklı bir soğuk açılışa "takıldı" derdik.
 *   - `enAzMs` 120 sn: gözlenen en kötü hâl (>62 sn) × ~2.
 *   - `tavanMs` 15 dk: burada tek amaç sonsuz döngüyü kesmek.
 */
'use strict';

const http = require('http');
const _et = require('./dil').t;

/**
 * Tek `/health` yoklaması üreten fabrika — "hazır mı" sorusunun atomu.
 *
 * 🔴 Süre sınırı ŞART: `http.get`'in varsayılan zaman aşımı YOKTUR. Bağlantıyı kabul edip
 * yanıt vermeyen bir sokette istek sonsuza kadar asılı kalır; eski kodda bu, bekleme
 * döngüsünün bir daha hiç dönmemesi demekti — açılış ekranı sonsuza kadar, hata da yok.
 * (Sahada görülen belirti değil ama aynı sınıf: "süresiz await" tuzağı, `clearStorageData`
 * dersinin aynısı — bir iyileştirmenin uygulamayı açmaya engel olma yetkisi yoktur.)
 */
function saglikSorucu(url, { zamanAsimiMs = 4000 } = {}) {
  return () => new Promise((resolve) => {
    let bitti = false;
    const bitir = (v) => { if (!bitti) { bitti = true; resolve(v); } };
    const istek = http.get(url + '/health', (res) => {
      if (res.statusCode !== 200) { res.resume(); return bitir({ ok: false }); }
      // Gövdeyi oku: `/health` çalışan backend'in sürümünü bildiriyor
      // (`app/services/health.py::APP_VERSION` — yükün taşıdığı dosya).
      let g = '';
      res.setEncoding('utf8');
      res.on('data', (c) => { g += c; });
      res.on('end', () => {
        let surum = null;
        try { surum = JSON.parse(g).version || null; } catch (_) { /* eski backend: sürüm bildirmiyor */ }
        bitir({ ok: true, surum });
      });
    });
    istek.on('error', () => bitir({ ok: false }));
    istek.setTimeout(zamanAsimiMs, () => { try { istek.destroy(); } catch (_) {} bitir({ ok: false }); });
  });
}

/** Açılış ekranına basılacak kademeli mesajlar — bekleyen kullanıcı sabreder, bilmeyen kapatır.
 *  İkinci alan METİN değil ANAHTAR: basılırken `_et` ile çözülür — yükleme anında
 *  çözülseydi ilk dilde donardı. Sözlükte olmayan değer (test `asamalar`'ı) aynen basılır. */
const ASAMALAR = [
  [45000, 'kabuk.motor-hala-hazirlaniyor'],
  [75000, 'kabuk.motor-neredeyse-hazir'],
  [120000, 'kabuk.motor-uzun-suruyor'],
];

const VARSAYILAN = {
  aralikMs: 500,
  durgunlukMs: 90000,
  enAzMs: 120000,
  tavanMs: 15 * 60 * 1000,
};

/**
 * @param {object} o
 * @param {() => Promise<{ok: boolean, surum?: string|null}>} o.saglikSor  tek `/health` yoklaması
 * @param {() => number} o.sonCikti      backend'in son çıktı ürettiği an (ms epoch)
 * @param {() => (null|object)} o.surecDurumu  süreç yaşıyorsa null, öldüyse sebep nesnesi
 * @param {(metin: string, sari?: boolean) => void} [o.ilerleme]  açılış ekranına yaz
 * @param {() => number} [o.simdi]       saat (test için enjekte edilir)
 * @param {(ms: number) => Promise<void>} [o.uyu]
 * @returns {Promise<{hazir: boolean, surum: string|null, sebep?: string, detay?: object, gecenMs: number, durgunMs?: number}>}
 */
async function motorBekle(o) {
  const simdi = o.simdi || Date.now;
  const uyu = o.uyu || ((ms) => new Promise((r) => setTimeout(r, ms)));
  const ilerleme = o.ilerleme || (() => {});
  const asamalar = o.asamalar || ASAMALAR;
  const aralikMs = o.aralikMs ?? VARSAYILAN.aralikMs;
  const durgunlukMs = o.durgunlukMs ?? VARSAYILAN.durgunlukMs;
  const enAzMs = o.enAzMs ?? VARSAYILAN.enAzMs;
  const tavanMs = o.tavanMs ?? VARSAYILAN.tavanMs;

  const t0 = simdi();
  let sonrakiAsama = 0;

  for (;;) {
    const s = await o.saglikSor();
    if (s && s.ok) {
      return { hazir: true, surum: s.surum || null, gecenMs: simdi() - t0 };
    }

    // ① Süreç öldüyse beklemenin anlamı yok — "ilerleme" ölçütü burada asla dolmaz,
    //    kullanıcıyı `enAzMs` boyunca boşuna bekletmeyelim.
    const olu = o.surecDurumu();
    if (olu) {
      return { hazir: false, surum: null, sebep: 'surec-oldu', detay: olu, gecenMs: simdi() - t0 };
    }

    const gecenMs = simdi() - t0;
    const durgunMs = simdi() - o.sonCikti();

    // ②+③ Yeterince bekledik VE motor uzun süredir hiç ses çıkarmıyor.
    if (gecenMs >= enAzMs && durgunMs >= durgunlukMs) {
      return { hazir: false, surum: null, sebep: 'durgun', durgunMs, gecenMs };
    }
    // Yedek: çıktı akmaya devam etse bile bir yerde durmak gerekir.
    if (gecenMs >= tavanMs) {
      return { hazir: false, surum: null, sebep: 'tavan', durgunMs, gecenMs };
    }

    while (sonrakiAsama < asamalar.length && gecenMs >= asamalar[sonrakiAsama][0]) {
      ilerleme(_et(asamalar[sonrakiAsama][1]));
      sonrakiAsama++;
    }

    await uyu(aralikMs);
  }
}

module.exports = { motorBekle, saglikSorucu, ASAMALAR, VARSAYILAN };
