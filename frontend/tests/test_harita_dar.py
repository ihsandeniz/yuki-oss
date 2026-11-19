"""Harita alt şeridi dar ekranda: ⌕ ezilmiyor, KATMANLAR taşmıyor — gerçek motor + tarayıcı.

    YUKI_DATA_DIR=$(mktemp -d) python -m uvicorn app.main:app --port 18791   # backend/ içinde
    python frontend/tests/test_harita_dar.py http://127.0.0.1:18791

11-02'ye kadar 390'da #map-ara-ac (⌕) esnek satırda 14 px'e eziliyordu (map-hud.css).
"""
import sys

from playwright.sync_api import sync_playwright

URL = sys.argv[1] if len(sys.argv) > 1 else "http://127.0.0.1:18791"
sonuc = []


def kontrol(ad, kosul, ek=""):
    sonuc.append((ad, bool(kosul)))
    print(("✓ " if kosul else "✗ ") + ad + (f"  ({ek})" if ek else ""))


OLC = """() => {
  const k = id => { const e = document.getElementById(id), r = e.getBoundingClientRect();
    return {x: r.left, r: r.right, y: r.top, b: r.bottom, w: r.width, sw: e.scrollWidth, cw: e.clientWidth}; };
  return {ara: k('map-ara-ac'), katman: k('map-katman-ac'), en: innerWidth};
}"""

with sync_playwright() as p:
    tarayici = p.chromium.launch()
    for gen, yuk in [(360, 780), (390, 844), (1280, 800)]:
        sayfa = tarayici.new_page(viewport={"width": gen, "height": yuk})
        hatalar = []
        sayfa.on("pageerror", lambda e, H=hatalar: H.append(str(e)))
        sayfa.goto(URL + "/ui/", wait_until="load")
        sayfa.wait_for_timeout(6000)
        atla = sayfa.get_by_text("Şimdilik atla")
        if atla.count() and atla.first.is_visible():
            atla.first.click()
            sayfa.wait_for_timeout(1000)
        sayfa.evaluate("switchTab('map')")
        sayfa.wait_for_timeout(2500)
        o = sayfa.evaluate(OLC)
        a, k = o["ara"], o["katman"]
        kontrol(f"{gen}: ⌕ en az 36 px", a["w"] >= 36, f"{a['w']:.1f} px")
        # 2B kutu kesişimi (11-13, Gözlemevi düzeni): telefonda ⌕ yer kartında üstte, KATMANLAR alt sırada —
        # yalnız x eksenine bakmak aynı sütunda farklı satırdaki iki düğmeyi çakışıyor sayardı.
        kontrol(f"{gen}: ⌕ ile KATMANLAR çakışmıyor",
                a["r"] <= k["x"] + 0.5 or k["r"] <= a["x"] + 0.5 or a["b"] <= k["y"] + 0.5 or k["b"] <= a["y"] + 0.5,
                f"⌕ {a['x']:.0f},{a['y']:.0f}–{a['r']:.0f},{a['b']:.0f} · KATMANLAR {k['x']:.0f},{k['y']:.0f}–{k['r']:.0f},{k['b']:.0f}")
        kontrol(f"{gen}: KATMANLAR metni taşmıyor", k["sw"] <= k["cw"] + 1, f"{k['sw']}/{k['cw']}")
        kontrol(f"{gen}: ekran içinde", a["x"] >= 0 and k["r"] <= o["en"])
        # Dar düzende sağ yarı ⌕ + KATMANLAR'ındır; taşan satır sola, GÜNDEM'in üstüne biner.
        kontrol(f"{gen}: ⌕ sağ yarıda", a["x"] >= o["en"] / 2, f"x={a['x']:.0f}")
        kontrol(f"{gen}: JS istisnası 0", not hatalar, "; ".join(hatalar[:2]))
        sayfa.close()
    tarayici.close()

kalan = sum(1 for _, ok in sonuc if not ok)
print(f"\ngeçti {len(sonuc) - kalan} · kaldı {kalan}")
sys.exit(1 if kalan else 0)
