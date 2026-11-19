// Host → sayfa komut akışı. Host eskiden komutları evaluate_javascript ile kosturuyordu; her çağrı
// arayüz sürecinde JSC'yi dolduruyor, ilk çöp toplamada Yuki son karede donuyordu (2026-10-25
// takılma düzeltmesi). Artık host yerel sunucunun /_yuki/komut akışına yazar, burada kosar. Anahtar URL'de (?anahtar=)
// yalnız canlıda verilir; kuru ölçümde yok → host evaluate_javascript kullanır, bu dosya hiçbir şey yapmaz.
(function () {
  const anahtar = new URLSearchParams(location.search).get('anahtar');
  if (!anahtar || !window.EventSource) return;
  const kos = (0, eval);   // dolaylı eval: komut genel kapsamda kosar (window.yukiBak … gibi)
  const bagla = () => {
    const es = new EventSource('/_yuki/komut?anahtar=' + encodeURIComponent(anahtar));
    const K = window.yukiKomut = { es, sayi: 0, hata: 0 };   // sayaçlar durum POST'uyla host'a gider (log satırı)
    es.onmessage = e => { K.sayi++; try { kos(JSON.parse(e.data)); } catch (h) { K.hata++; console.warn('[masaustu] komut', h); } };
  };
  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', bagla, { once: true });
  else bagla();
})();
