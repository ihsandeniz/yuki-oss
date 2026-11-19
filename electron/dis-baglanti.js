/**
 * Dış bağlantı yönlendirmesi — uygulama penceresi yalnız kendi arayüzünü gösterir.
 *
 * 🔴 2026-08-06 — ÖLÇÜLDÜ (`scratchpad/dis-link-canli-test.js`, gerçek Electron 29,
 * xvfb içinde): hiçbir pencere-açma işleyicisi kurulu değilken `target="_blank"`
 * sistem tarayıcısını AÇMIYOR — uygulamanın içinde yeni bir BrowserWindow yaratıyor
 * (`did-create-window` tetiklendi, `shell.openExternal` hiç çağrılmadı). O pencerede
 * adres çubuğu, geri düğmesi, sekme yok; kullanıcının tarayıcı oturumu ve parola
 * yöneticisi de yok — üstelik Google/GitHub OAuth gömülü pencereleri sık reddeder.
 *
 * Vurduğu yer teorik değil: BYOK rehberinin **1. adımı** bir dış bağlantı
 * ("openrouter.ai/keys → giriş yap"). Anahtarını alamayan müşteri hiç sohbet edemez.
 * Aynı sınıftan 4 bağlantı var: anahtar rehberi (index.html + intro-sequences.js),
 * 🩺 SAĞLIK'taki çözüm URL'i.
 *
 * Bu modül AYRI dosya çünkü canlı test onu `uygulama.js`'ten bağımsız (Electron
 * penceresi + backend gerektirmeden) koşabilsin: ölçülen kod ile satılan kod aynı
 * olsun. Kopyalanmış bir kural, ayrıştığı gün kimsenin bakmadığı yerde ayrışır.
 */

/**
 * @param {object} secenekler
 * @param {(url: string) => any} secenekler.openExternal  genelde `shell.openExternal`
 * @param {string} secenekler.icOnEk   uygulamanın kendi kökü (BACKEND_URL) — bu önekle
 *                                     başlayan gezinme "dışarı" sayılmaz
 * @param {(mesaj: string) => void} [secenekler.kaydet]   günlükleyici
 */
function disBaglantiKurallari({ openExternal, icOnEk, kaydet = () => {} }) {
  /** Dış URL'i kullanıcının kendi tarayıcısında aç. Açıldıysa true. */
  const ac = (url) => {
    let protokol;
    try { protokol = new URL(url).protocol; } catch (_) {
      kaydet(`dış bağlantı reddedildi (çözümlenemeyen URL): ${url}`);
      return false;
    }
    // Yalnız http/https. `file:`/`javascript:`/özel şema açmak, arayüzden gelen bir
    // metnin keyfi şema tetiklemesine izin vermek olurdu.
    if (protokol !== 'http:' && protokol !== 'https:') {
      kaydet(`dış bağlantı reddedildi (şema ${protokol}): ${url}`);
      return false;
    }
    try {
      const p = openExternal(url);
      if (p && typeof p.catch === 'function') {
        p.catch((e) => kaydet(`dış bağlantı açılamadı: ${e.message}`));
      }
    } catch (e) {
      kaydet(`dış bağlantı açılamadı: ${e.message}`);
      return false;
    }
    return true;
  };

  /** Uygulamanın KENDİ sayfası mı? (gezinmesi engellenmez)
   *
   * ⚠️ Ölçüt `file://` DEĞİL: arayüz `loadURL(BACKEND_URL)` ile gelir, yalnız açılış
   * ekranı `file://`. Ölçütü sadece `file://` yazmak PLAN ekranına geçişi
   * (`/ui/planner.html`) ve her yeniden yüklemeyi "dışarı" sayıp keserdi —
   * düzeltmenin kendisi ürünü kırardı. (Bu tuzağa yazarken düşüldü, testi var.)
   */
  const icerdeMi = (url) => url.startsWith('file://') || url.startsWith(icOnEk);

  return {
    ac,
    icerdeMi,
    /** `webContents.setWindowOpenHandler` gövdesi — uygulama içinde ASLA pencere açılmaz. */
    pencereAcmaIsleyicisi: ({ url }) => {
      ac(url);
      return { action: 'deny' };
    },
    /** `will-navigate` gövdesi: `target` olmadan da dışarı gidilebilir; o zaman ana
     *  pencere arayüzden ayrılır ve geri dönüş yolu kalmaz. */
    gezinmeIsleyicisi: (olay, url) => {
      if (icerdeMi(url)) return false;
      try { olay.preventDefault(); } catch (_) {}
      ac(url);
      return true;
    },
  };
}

module.exports = { disBaglantiKurallari };
