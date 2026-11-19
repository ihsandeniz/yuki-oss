"""Plan üst şeridi BUGÜN sayacı = bitmiş / (bitmiş + açık). `due_today` yalnız açık görevleri sayar;
eskiden 1 biten + 3 açık "1/3" görünüyordu (goz 11-13).

    python3 frontend/tests/test_plan_bugun_sayac.py [BASE]              # varsayılan http://127.0.0.1:8031
    python3 frontend/tests/test_plan_bugun_sayac.py [BASE] --mutasyon   # eski formülü sun, yakalandığını gör

/api/todo/stats Playwright'la taklit edilir (arka uç verisine bağlı değil). Normal (animasyonlu) mod.
"""
import json
import re
import sys
from playwright.sync_api import sync_playwright

ARGS = [a for a in sys.argv[1:] if not a.startswith("--")]
BASE = ARGS[0] if ARGS else "http://127.0.0.1:8031"
MUTASYON = "--mutasyon" in sys.argv
DURUMLAR = [  # (stats gövdesi, beklenen BUGÜN metni)
    ({"due_today": 3, "done_today": 1, "overdue": 1, "due_week": 8, "total_done": 1, "total_open": 11}, "1/4"),
    ({"due_today": 0, "done_today": 2, "overdue": 0, "due_week": 0, "total_done": 2, "total_open": 0}, "2/2"),
    ({"due_today": 0, "done_today": 0, "overdue": 0, "due_week": 0, "total_done": 0, "total_open": 0}, "0/0"),
    ({"done_today": 1}, "-"),          # alan eksik → "bilinmiyor"
]
ESKI = ("ikili(s.done_today, (s.due_today === undefined || s.due_today === null || s.done_today == null)\n"
        "    ? s.due_today : s.done_today + s.due_today)", "ikili(s.done_today, s.due_today)")


def olc(b, mut):
    sonuc = []
    for w in (390, 1280):
        for govde, bek in DURUMLAR:
            s = b.new_context(viewport={"width": w, "height": 844 if w < 500 else 800}, service_workers="block").new_page()
            hata = []
            s.on("pageerror", lambda e: hata.append(str(e)))
            s.route("**://127.0.0.1:8000/**", lambda r: r.abort())
            govde_json = json.dumps(govde)
            s.route(re.compile(r"/api/todo/stats(\?.*)?$"),
                    lambda r, *_a, g=govde_json: r.fulfill(status=200, content_type="application/json", body=g))
            if mut:
                def degistir(route):
                    y = route.fetch(); m = y.text()
                    assert ESKI[0] in m, "mutasyon metni yok"
                    route.fulfill(response=y, body=m.replace(*ESKI))
                s.route(re.compile(r"/planner\.html(\?.*)?$"), degistir)
            s.goto(BASE + "/ui/planner.html")
            s.wait_for_timeout(3500)
            metin = s.evaluate("(document.getElementById('s-today')||{}).textContent")
            sonuc.append((f"{w} {govde} → {bek}", metin == bek and not hata, (metin, hata[:1])))
            s.context.close()
    return sonuc


def main():
    with sync_playwright() as p:
        b = p.chromium.launch()
        r = olc(b, MUTASYON)
        b.close()
    kalan = [x for x in r if not x[1]]
    if MUTASYON:
        print(("✓ yakalandı" if kalan else "✗ KAÇTI"), "eski-formul —", kalan[0][0] if kalan else "")
        print(f"mutasyon {int(bool(kalan))}/1")
        return 0 if kalan else 1
    for ad, ok, ay in kalan:
        print("✗", ad, ay)
    print(f"{len(r) - len(kalan)} geçti · {len(kalan)} kaldı")
    return len(kalan)


if __name__ == "__main__":
    sys.exit(main())
