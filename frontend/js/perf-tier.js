/**
 * perf-tier.js — Cihaz performans katmanı (adaptif kalite).
 *
 * Amaç: Zayıf cihazlarda (eski laptop) ağır GPU efektlerini (backdrop-filter, glow, sürekli
 * animasyon) otomatik hafifletmek. YÜKSEK/ORTA cihazda tasarım BİREBİR korunur — hiçbir CSS
 * kuralı [data-perf] olmadan tetiklenmez, yalnız `[data-perf="low"]` seçicileri devreye girer.
 *
 * Tespit: navigator.hardwareConcurrency (çekirdek) + navigator.deviceMemory (GB).
 *   - Linux'ta Electron software GL kullandığı için GPU renderer string'i güvenilmez → sadece CPU/RAM.
 *   - deviceMemory bazı ortamlarda tanımsız olabilir → o zaman yalnız çekirdek sayısına bakılır.
 *
 * <html data-perf> attribute'u index.html'deki erken inline snippet ile FOUC olmadan set edilir;
 * bu modül override API'sini (AYAR panelinden manuel seçim) ve yeniden değerlendirmeyi sağlar.
 */
(function () {
  'use strict';

  var STORAGE_KEY = 'yuki-perf-tier'; // 'low' | 'mid' | 'high' | (yok = auto)

  /** Donanıma göre otomatik katman tespiti. */
  function detect() {
    var cores = navigator.hardwareConcurrency || 4;
    var mem = navigator.deviceMemory; // undefined olabilir (yalnız Chromium'da güvenilir)
    // Eski/zayıf laptop hedefi: 2-4 çekirdek veya ≤4GB RAM → low.
    var isLow = cores <= 4 || (typeof mem === 'number' && mem <= 4);
    // Güçlü: ≥8 çekirdek ve (RAM bilinmiyorsa yok say / ≥8GB) → high.
    var isHigh = cores >= 8 && (typeof mem !== 'number' || mem >= 8);
    return isLow ? 'low' : isHigh ? 'high' : 'mid';
  }

  /** <html>'e uygula. */
  function apply(tier) {
    document.documentElement.dataset.perf = tier;
  }

  /** Şu anki etkin katman. */
  function current() {
    return document.documentElement.dataset.perf || detect();
  }

  /**
   * Manuel override (AYAR'dan). 'auto' → localStorage temizlenir, otomatik tespite döner.
   * Sayfa yenilemeye gerek yok: data-perf değişince CSS anında uygulanır.
   */
  function setOverride(tier) {
    if (tier === 'auto') {
      try { localStorage.removeItem(STORAGE_KEY); } catch (e) {}
      apply(detect());
    } else if (tier === 'low' || tier === 'mid' || tier === 'high') {
      try { localStorage.setItem(STORAGE_KEY, tier); } catch (e) {}
      apply(tier);
    }
    return current();
  }

  /** AYAR paneli için teşhis bilgisi. */
  function info() {
    var ov = null;
    try { ov = localStorage.getItem(STORAGE_KEY); } catch (e) {}
    return {
      tier: current(),
      cores: navigator.hardwareConcurrency || null,
      memory: (typeof navigator.deviceMemory === 'number') ? navigator.deviceMemory : null,
      mode: ov ? 'manuel' : 'otomatik',
      detected: detect()
    };
  }

  // Erken snippet çalışmadıysa (ör. eski cache) güvenceye al.
  if (!document.documentElement.dataset.perf) {
    var ov = null;
    try { ov = localStorage.getItem(STORAGE_KEY); } catch (e) {}
    apply(ov || detect());
  }

  window.PerfTier = { detect: detect, current: current, setOverride: setOverride, info: info };
})();
