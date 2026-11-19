"""☰ (#nav-ac) iframe'li sekmelerin sol üst öğelerini örtmüyor mu — gerçek motor + tarayıcı.

    YUKI_DATA_DIR=$(mktemp -d) python -m uvicorn app.main:app --port 18791   # backend/ içinde
    python frontend/tests/test_nav_payi.py http://127.0.0.1:18791

Ölçer (390 ve 1280): GALERİ / DOSYA / PLAN iframe'lerinin üst şeridindeki görünür öğelerin
hiçbiri ☰'ın kutusuyla kesişmiyor. 11-02'ye kadar GALERİ ve DOSYA'da pay yoktu: ☰ klasör
simgesini ve "DOSYALAR" başlığını örtüyordu (`tab-nav.js` § navPayi).
"""
import sys

from playwright.sync_api import sync_playwright

URL = sys.argv[1] if len(sys.argv) > 1 else "http://127.0.0.1:18791"
SEKMELER = {  # sekme → (iframe id, sayfa adı, üst şerit seçicisi)
    "galeri": ("galeri-iframe", "galeri.html", ".gl-ust"),
    "dosya": ("dosya-iframe", "dosya.html", ".dy-ust"),
}
sonuc = []


def kontrol(ad, kosul, ek=""):
    sonuc.append((ad, bool(kosul)))
    print(("✓ " if kosul else "✗ ") + ad + (f"  ({ek})" if ek else ""))


# Üst şeritteki görünür yaprak öğeler (metin ya da simge taşıyan), sayfa koordinatına çevrilmeden.
OGELER_JS = """sec => {
  const ust = document.querySelector(sec); if (!ust) return null;
  return [...ust.querySelectorAll('*')].filter(e => {
    const r = e.getBoundingClientRect(), cs = getComputedStyle(e);
    if (!r.width || !r.height || cs.visibility === 'hidden' || +cs.opacity === 0) return false;
    const yaprak = e.tagName === 'svg' || e.tagName === 'IMG' ||
      [...e.childNodes].some(n => n.nodeType === 3 && n.textContent.trim());
    return yaprak && !e.closest('svg:not(:scope)');
  }).map(e => { const r = e.getBoundingClientRect();
    return {ad: e.tagName + '.' + (e.getAttribute('class') || ''), x: r.left, y: r.top, r: r.right, b: r.bottom}; });
}"""


def kesisir(a, b):
    return a["x"] < b["r"] and b["x"] < a["r"] and a["y"] < b["b"] and b["y"] < a["b"]


with sync_playwright() as p:
    tarayici = p.chromium.launch()
    for gen, yuk in [(390, 844), (1280, 800)]:
        sayfa = tarayici.new_page(viewport={"width": gen, "height": yuk})
        hatalar = []
        sayfa.on("pageerror", lambda e, H=hatalar: H.append(str(e)))
        sayfa.goto(URL + "/ui/", wait_until="load")
        sayfa.wait_for_timeout(6000)
        atla = sayfa.get_by_text("Şimdilik atla")
        if atla.count() and atla.first.is_visible():
            atla.first.click()
            sayfa.wait_for_timeout(1200)
        nav = sayfa.evaluate("(() => { const r = document.getElementById('nav-ac').getBoundingClientRect();"
                             " return {x: r.left, y: r.top, r: r.right, b: r.bottom}; })()")
        for sekme, (fid, ad, sec) in SEKMELER.items():
            sayfa.evaluate(f"switchTab('{sekme}')")
            sayfa.wait_for_timeout(3000)
            kutu = sayfa.evaluate(f"(() => {{ const r = document.getElementById('{fid}').getBoundingClientRect();"
                                  " return {x: r.left, y: r.top}; })()")
            cerceve = next((f for f in sayfa.frames if ad in f.url), None)
            kontrol(f"{gen} {sekme}: iframe yüklendi", cerceve is not None)
            if cerceve is None:
                continue
            kontrol(f"{gen} {sekme}: pay stili eklendi",
                    cerceve.evaluate("!!document.getElementById('yuki-nav-bosluk')"))
            ogeler = cerceve.evaluate(OGELER_JS, sec) or []
            kontrol(f"{gen} {sekme}: üst şeritte öğe var", len(ogeler) > 0, f"{len(ogeler)} öğe")
            carpan = [o["ad"] for o in ogeler
                      if kesisir(nav, {"x": o["x"] + kutu["x"], "r": o["r"] + kutu["x"],
                                       "y": o["y"] + kutu["y"], "b": o["b"] + kutu["y"]})]
            kontrol(f"{gen} {sekme}: ☰ hiçbir öğeyi örtmüyor", not carpan, ", ".join(carpan[:4]))
        kontrol(f"{gen}: JS istisnası 0", not hatalar, "; ".join(hatalar[:2]))
        sayfa.close()
    tarayici.close()

kalan = sum(1 for _, ok in sonuc if not ok)
print(f"\ngeçti {len(sonuc) - kalan} · kaldı {kalan}")
sys.exit(1 if kalan else 0)
