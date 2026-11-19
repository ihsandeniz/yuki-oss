"""Sekme listesi (11-13 ORTAK şerit): PANEL kalktı, YEDEK ayrı sekme.

    # backend/ içinde, geçici veriyle ikinci port (kişisel veri yok):
    YUKI_DATA_DIR=$(mktemp -d) HOME=$(mktemp -d) python -m uvicorn app.main:app --port 8021
    python frontend/tests/test_sekme_listesi.py http://127.0.0.1:8021 [ekran-klasörü]

Ölçer (390 ve 1280, normal/animasyonlu mod — animasyon kapatılmaz):
  · sekme çubuğu tam olarak chat·planner·hq·map·ajan·yedek·galeri·dosya, PANEL düğmesi/kabı yok
  · klavye 1-8 bu sırayla sekme açar (6 → YEDEK), `switchTab('panel')` ve `#wtab=panel` sohbete düşer
  · YEDEK açılınca yedekleme paneli `#yedek-kok`'a çizilir (/api/yedekleme/durum çağrılır)
  · HQ menüsündeki "Yedekleme" girdisi YEDEK sekmesine götürür
  · panelin Google düğmesi HQ › Google paneline götürür
  · JS istisnası 0
Çıkış kodu = kalan sayısı.
"""
import sys
from pathlib import Path

from playwright.sync_api import sync_playwright

BASE = sys.argv[1] if len(sys.argv) > 1 else "http://127.0.0.1:8021"
EKRAN = Path(sys.argv[2]) if len(sys.argv) > 2 else None
BEKLENEN = ["chat", "planner", "hq", "map", "ajan", "yedek", "galeri", "dosya"]
sonuc = []


def kontrol(ad, kosul, ek=""):
    sonuc.append((ad, bool(kosul)))
    print(("✓ " if kosul else "✗ ") + ad + (f"  ({ek})" if ek else ""))


def tab(s):
    return s.evaluate("document.documentElement.getAttribute('data-tab')")


def ac(tarayici, gen, yuk, yol="/ui/"):
    s = tarayici.new_context(viewport={"width": gen, "height": yuk}).new_page()
    hatalar, istekler = [], []
    s.on("pageerror", lambda e, H=hatalar: H.append(str(e)))
    s.on("request", lambda r, I=istekler: I.append(r.url))
    s.goto(BASE + yol, wait_until="load")
    s.wait_for_timeout(6000)
    atla = s.get_by_text("Şimdilik atla")
    if atla.count() and atla.first.is_visible():
        atla.first.click()
        s.wait_for_timeout(1200)
    return s, hatalar, istekler


with sync_playwright() as p:
    tarayici = p.chromium.launch()
    for gen, yuk in ((390, 844), (1280, 800)):
        e = f"[{gen}] "
        s, hatalar, istekler = ac(tarayici, gen, yuk)
        sira = s.evaluate("[...document.querySelectorAll('#tab-items .tab-btn[data-tab]')].map(b => b.dataset.tab)")
        kontrol(e + "sekme sırası chat·planner·hq·map·ajan·yedek·galeri·dosya", sira == BEKLENEN, str(sira))
        kontrol(e + "PANEL düğmesi ve kabı yok",
                s.evaluate("!document.getElementById('tab-btn-panel') && !document.getElementById('tab-panel')"))
        kontrol(e + "kanvas kodu yüklenmedi", s.evaluate("typeof window.AliceCanvas === 'undefined'"))
        kontrol(e + "YEDEK düğmesi görünür", s.evaluate("(() => { const b = document.getElementById('tab-btn-yedek');"
                                                         " return !!b && !b.hidden; })()"))

        # klavye kısayolları (odak gövdede, metin alanında değil)
        s.evaluate("document.activeElement && document.activeElement.blur()")
        for no, ad in enumerate(BEKLENEN, start=1):
            s.keyboard.press(str(no))
            s.wait_for_timeout(500)
            if tab(s) != ad:
                kontrol(e + f"kısayol {no} → {ad}", False, f"gelen {tab(s)}")
                break
        else:
            kontrol(e + "kısayol 1-8 sırayla sekme açıyor", True)
        s.evaluate("switchTab('chat')")
        s.wait_for_timeout(500)

        s.evaluate("switchTab('panel')")
        s.wait_for_timeout(700)
        kontrol(e + "switchTab('panel') sohbete düşer", tab(s) == "chat", tab(s))

        # YEDEK sekmesi
        once = len([u for u in istekler if "/api/yedekleme/durum" in u])
        s.evaluate("switchTab('yedek')")
        s.wait_for_timeout(2500)
        kontrol(e + "switchTab('yedek') YEDEK'e geçer", tab(s) == "yedek", tab(s))
        kontrol(e + "YEDEK kabı görünür, öbürleri gizli",
                s.evaluate("(() => { const y = document.getElementById('tab-yedek'), a = document.getElementById('app');"
                           " return !y.hidden && y.getBoundingClientRect().height > 200 && a.hidden; })()"))
        kontrol(e + "yedekleme paneli #yedek-kok'a çizildi",
                s.evaluate("!!document.querySelector('#yedek-kok .yb-oda .yb-serit')"))
        kontrol(e + "sekme açılınca durum tazelendi",
                len([u for u in istekler if "/api/yedekleme/durum" in u]) > once)
        kontrol(e + "eski HQ yedekleme kabı yok", s.evaluate("!document.getElementById('hq-panel-yedekleme')"))
        tasma = s.evaluate("(() => { const k = document.getElementById('tab-yedek');"
                           " return k.scrollWidth - k.clientWidth; })()")
        kontrol(e + "YEDEK yatay taşma yok", tasma <= 1, f"{tasma}px")
        if EKRAN:
            EKRAN.mkdir(parents=True, exist_ok=True)
            s.screenshot(path=str(EKRAN / f"yedek-{gen}.png"))

        # Google düğmesi → HQ › Google
        g = s.locator("#yedek-kok [data-y=google]")
        if g.count():
            g.first.click()
            s.wait_for_timeout(1500)
            kontrol(e + "Google düğmesi HQ › Google'a götürür",
                    tab(s) == "hq" and s.evaluate("document.getElementById('tab-hq').dataset.hq") == "google",
                    f"{tab(s)} / {s.evaluate('document.getElementById(`tab-hq`).dataset.hq')}")
        else:
            kontrol(e + "Google düğmesi çizildi (bağlantısız demo)", False, "düğme yok")

        # HQ menüsündeki Yedekleme girdisi → YEDEK sekmesi
        s.evaluate("switchTab('hq')")
        s.wait_for_timeout(1500)
        girdi = s.locator("#hq-subnav .hq-nav-btn[data-id=yedekleme]")
        kontrol(e + "HQ menüsünde Yedekleme girdisi duruyor", girdi.count() == 1)
        if girdi.count():
            girdi.first.evaluate("b => b.click()")
            s.wait_for_timeout(1500)
            kontrol(e + "HQ › Yedekleme YEDEK sekmesine götürür", tab(s) == "yedek", tab(s))
        if EKRAN and gen == 1280:
            s.evaluate("switchTab('hq')")
            s.wait_for_timeout(1500)
            s.screenshot(path=str(EKRAN / f"hq-menu-{gen}.png"))
            s.evaluate("switchTab('chat')")
            s.wait_for_timeout(1500)
            s.screenshot(path=str(EKRAN / f"sohbet-{gen}.png"))
        kontrol(e + "JS istisnası 0", not hatalar, "; ".join(hatalar[:3]))
        s.context.close()

        # widget yolu
        s, hatalar, _ = ac(tarayici, gen, yuk, yol="/ui/?widget=1#wtab=panel")
        s.evaluate("location.hash = 'wtab=panel'")
        s.wait_for_timeout(1000)
        kontrol(e + "widget #wtab=panel sohbete düşer", tab(s) == "chat", tab(s))
        kontrol(e + "widget: JS istisnası 0", not hatalar, "; ".join(hatalar[:3]))
        s.context.close()
    tarayici.close()

kalan = sum(1 for _, ok in sonuc if not ok)
print(f"\ngeçti {len(sonuc) - kalan} · kaldı {kalan}")
sys.exit(kalan)
