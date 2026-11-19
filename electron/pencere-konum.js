// Pencere konumu yardımcıları — Electron'a bağımlı DEĞİL, bu yüzden test edilebilir.
// (main.js `require('electron')` yaptığı için düz node testinden çağrılamaz.)

/**
 * Kayıtlı pencere konumunu gerçekten görünür bir ekrana sığdır.
 *
 * NEDEN: Kaydedilen x/y hiç doğrulanmıyordu. Harici monitör çıkarılınca, çözünürlük
 * değişince ya da laptop dock'tan alınınca kayıtlı koordinat masaüstünün DIŞINDA
 * kalıyor → uygulama sorunsuz çalışıyor ama pencere görünmüyor. Kullanıcı için bu
 * "açılmadı"dan ayırt edilemez.
 *
 * @param {object} state  {x,y,width,height,...}
 * @param {Array}  alanlar Ekranların çalışma alanları [{x,y,width,height}]
 */
function gorunurAlanaSigdir(state, alanlar) {
  const s = { ...state };
  if (!Array.isArray(alanlar) || alanlar.length === 0) return s;

  // Boyut: hiçbir ekrana sığmayan pencere de kullanılamaz.
  const enGenis = Math.max(...alanlar.map((a) => a.width));
  const enYuksek = Math.max(...alanlar.map((a) => a.height));
  s.width = Math.max(480, Math.min(s.width || 900, enGenis));
  s.height = Math.max(600, Math.min(s.height || 700, enYuksek));

  // Geçerli bir sayı değilse (yok / null / NaN / "100" / Infinity) konumu DÜŞÜR.
  // Olduğu gibi bırakmak yetmez: bozuk bir window-state.json'daki NaN doğrudan
  // BrowserWindow'a geçer ve pencerenin nereye açılacağı tanımsızlaşır.
  if (!Number.isFinite(s.x) || !Number.isFinite(s.y)
      || typeof s.x !== 'number' || typeof s.y !== 'number') {
    delete s.x; delete s.y;
    return s;   // → Electron ortalar
  }

  // Tutma çıtası: başlık şeridinden en az bu kadarı bir ekranın içinde kalmalı,
  // yoksa pencere ne görünür ne de fareyle geri sürüklenebilir.
  const EN_AZ_GENIS = 120;
  const EN_AZ_YUKSEK = 40;
  const gorunur = alanlar.some((a) => {
    const ortakG = Math.min(s.x + s.width, a.x + a.width) - Math.max(s.x, a.x);
    const ortakY = Math.min(s.y + s.height, a.y + a.height) - Math.max(s.y, a.y);
    return ortakG >= EN_AZ_GENIS && ortakY >= EN_AZ_YUKSEK;
  });
  if (!gorunur) { delete s.x; delete s.y; }   // → Electron ortalar
  return s;
}

module.exports = { gorunurAlanaSigdir };
