#!/usr/bin/env python3
"""☰ örtüşme kapısı — sol üstteki ☰ (#nav-ac) metnin üstüne binmesin.

  1) Avatar gizliyken sohbet üst çubuğu sol kenara dayanır: karakter adı ☰'ın sağında başlamalı (390 + 1280).
  2) Telefonda (390) galeri klasör çekmecesi açıkken "KLASÖRLER" başlığı ☰'ın sağında başlamalı.

YUKI_DEMO=1 ikinci örneğe karşı koş (canlı :8000/:8001 reddedilir):
    python3 frontend/tests/test_nav_ortusme.py http://127.0.0.1:8211 [--mutasyon]
--mutasyon: iki payı tek tek kaldırır (istek yolunda metin değişir), testin düştüğünü görür.
"""
import re
import sys

from playwright.sync_api import sync_playwright

ARGS = [a for a in sys.argv[1:] if not a.startswith("--")]
BASE = ARGS[0] if ARGS else "http://127.0.0.1:8211"
MUTASYON = "--mutasyon" in sys.argv
if re.search(r":(8000|8001)\b", BASE):
    sys.exit("canlı/geliştirme portu reddedildi — YUKI_DEMO=1 ikinci örneğe karşı koş")

# (ad, dosya sonu, doğru metin, kırık metin, bozması beklenen kontrol öneki)
MUTASYONLAR = [
    ("avatar-gizli-pay", "/css/sohbet.css",
     '#app[data-avatar-ayar="gizli"] #header { padding-inline-start: var(--nav-bosluk, 60px); }',
     '#app[data-avatar-ayar="gizli"] #header { }', "avatar"),
    ("galeri-cekmece-pay", "/js/tab-nav.js",
     "{.gl-ray-bas{padding-inline-start:28px!important}}", "{.gl-ray-bas{}}", "390/galeri"),
]

KAPAT = """() => { for (const id of ['auth-screen','boot-screen','yuki-opening']) {
  const e = document.getElementById(id); if (e) { e.classList.add('hidden'); e.style.display = 'none'; } }
  const app = document.getElementById('app'); if (app) app.style.display = ''; }"""


def sayfa(b, w, mut=None, avatar=None):
    ctx = b.new_context(viewport={"width": w, "height": 844 if w < 600 else 800}, service_workers="block")
    init = "try{localStorage.setItem('yukiViewMode','chat');localStorage.setItem('yukiIlkKurulum_v1','bitti');"
    if avatar:
        init += f"localStorage.setItem('yuki_avatar_v1','{avatar}');"
    ctx.add_init_script(init + "}catch(e){}")
    if mut:
        _, son, dogru, kirik, _ = mut

        def yol(route):
            r = route.fetch()
            govde = r.text()
            assert dogru in govde, f"mutasyon kalıbı bulunamadı: {son}"
            route.fulfill(response=r, body=govde.replace(dogru, kirik))
        ctx.route(re.compile(r".*" + re.escape(son) + r"(\?.*)?$"), yol)
    s = ctx.new_page()
    hatalar = []
    s.on("pageerror", lambda e: hatalar.append(str(e)[:160]))
    s.goto(BASE + "/", wait_until="domcontentloaded", timeout=30000)
    s.wait_for_timeout(3500)
    s.evaluate(KAPAT)
    s.evaluate("window.setViewMode && window.setViewMode('chat')")
    s.wait_for_timeout(1500)
    return s, hatalar


NAV_SAG = "(() => { const n = document.getElementById('nav-ac'); return n ? n.getBoundingClientRect().right : 0; })()"


def olc(b, mut=None):
    r = {}
    for w in (1280, 390):
        e = f"{w}/"
        s, h = sayfa(b, w, mut, avatar="gizli")
        sag = s.evaluate(NAV_SAG)
        a = s.evaluate("""() => { const app = document.getElementById('app');
          const ad = [...document.querySelectorAll('#header *')].find(x => x.children.length === 0 && x.textContent.trim() === 'Yuki'
                       && x.getBoundingClientRect().width > 0);
          const nokta = document.getElementById('state-dot');
          return { ayar: app && app.dataset.avatarAyar, adSol: ad ? ad.getBoundingClientRect().left : null,
                   noktaSol: nokta ? nokta.getBoundingClientRect().left : null }; }""")
        r[e + "avatar gizli kaydı okundu"] = (a["ayar"] == "gizli", a["ayar"])
        r[e + "avatar gizliyken 'Yuki' adı ☰'ın sağında"] = (a["adSol"] is not None and a["adSol"] >= sag + 4, (a, sag))
        r[e + "avatar gizliyken durum noktası ☰'ın sağında"] = (a["noktaSol"] is None or a["noktaSol"] >= sag, (a["noktaSol"], sag))
        r[e + "avatar JS 0"] = (not h, h[:2])
        s.context.close()
        if w < 600:
            s, h = sayfa(b, w, mut)
            s.evaluate("switchTab('galeri')")
            s.wait_for_timeout(3500)
            fr = next((f for f in s.frames if "galeri.html" in f.url), None)
            g = None
            if fr:
                fr.evaluate("document.getElementById('gl-ray-ac') && document.getElementById('gl-ray-ac').click()")
                s.wait_for_timeout(900)
                g = fr.evaluate("""() => { const h = document.querySelector('.gl-ray-bas .gl-hud');
                  const fe = window.frameElement ? window.frameElement.getBoundingClientRect().left : 0;
                  return h ? h.getBoundingClientRect().left + fe : null; }""")
            sag = s.evaluate(NAV_SAG)
            r[e + "galeri çekmecesinde 'KLASÖRLER' ☰'ın sağında"] = (g is not None and g >= sag + 4, (g, sag))
            r[e + "galeri JS 0"] = (not h, h[:2])
            s.context.close()
    return r


def main():
    with sync_playwright() as p:
        b = p.chromium.launch()
        if not MUTASYON:
            r = olc(b)
            kaldi = 0
            for ad, (ok, deger) in r.items():
                print(("✓ " if ok else "✗ ") + ad + ("" if ok else f"  {deger}"))
                kaldi += not ok
            print(f"geçti {len(r) - kaldi} · kaldı {kaldi}")
            b.close()
            return 1 if kaldi else 0
        yakalanan = 0
        for m in MUTASYONLAR:
            r = olc(b, m)
            dusen = [ad for ad, (ok, _) in r.items() if not ok and m[4] in ad]
            yakalanan += bool(dusen)
            print(("✓ yakalandı " if dusen else "✗ KAÇTI ") + m[0] + ("  ← " + dusen[0] if dusen else ""))
        b.close()
        print(f"mutasyon {yakalanan}/{len(MUTASYONLAR)}")
        return 0 if yakalanan == len(MUTASYONLAR) else 1


if __name__ == "__main__":
    sys.exit(main())
