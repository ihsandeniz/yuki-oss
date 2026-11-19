"""Tam hizala son tur (11-15): HALKA HAFIZA kartı (kişiseldeki liste kartı) + HQ sol menü üst örtüsü.

    python3 frontend/tests/test_son_tur.py [BASE]              # varsayılan http://127.0.0.1:8031
    python3 frontend/tests/test_son_tur.py [BASE] --mutasyon   # her kapıyı bir kez kır (--yalniz=ad)

BASE bir demo arka ucu olmalı (YUKI_DEMO=1; hafıza orada kapalıdır → stats `enabled:false`).
Öbür hafıza durumları (503, 500, dolu) Playwright yanıtıyla verilir. Mutasyonlar dosyayı DİSKTE değiştirmez.
SW kapalı. Normal (animasyonlu) mod.
Ölçülenler:
  kart-boy   — 390 HALKA'da HAFIZA kartı içerik boyunda (≤ 200 px) ve "Sistemler aktif" satırını (#hr-status) örtmez
  kapali     — `enabled:false` ve uç 503 → "hafıza kapalı"; 500 → "hafıza alınamadı" (kapalı denmez)
  dolu       — şerit "N anı · M tür", dağılım çubukları, olgu/tercih satırları; satıra dokununca tür + tarih
  eski-svg   — eski düğüm haritası (#hr-mem-svg) yok
  plan-gun   — 390 Plan hafta şeridinde gün adı iki harf (PT·SA·ÇA…, kişiseldeki gibi)
  asset-v    — index.html'deki chat-modes.js ?v= == ASSET_V (eşit değilse eski mod CSS'i gelir)
  hq-ortu    — 1280 HQ sol menü kaydırılınca başlık bandının pikselleri kaydırmadan öncekiyle aynı
"""
import json
import re
import sys
from playwright.sync_api import sync_playwright

ARGS = [a for a in sys.argv[1:] if not a.startswith("--")]
BASE = ARGS[0] if ARGS else "http://127.0.0.1:8031"
MUTASYON = "--mutasyon" in sys.argv

MUTASYONLAR = [
    ("hafiza-503", "/modes/hud-ring.js", "/HTTP 503/.test(", "/HTTP 999/.test("),
    ("hafiza-kapali", "/modes/hud-ring.js", "if (!st || st.enabled === false)", "if (!st)"),
    # kart içerikten bağımsız uzarsa (eski SVG kutusu gibi) "Sistemler aktif" satırını örter
    ("hafiza-boy", "/modes/hud-ring.css", ".hk-bos { display: flex; flex-direction: column; gap: 3px; padding: 14px 2px; }",
     ".hk-bos { display: flex; flex-direction: column; gap: 3px; padding: 140px 2px; }"),
    ("hafiza-liste", "/modes/hud-ring.js", ".slice(0, 8);\n    _memSon = { tur: 'dolu'", ".slice(0, 0);\n    _memSon = { tur: 'dolu'"),
    ("plan-gun", "/planner.html", "_t('tarih.gun-harf-' + k)", "_t('tarih.gun-kisa-' + k)"),
    ("asset-v", "/modes/chat-modes.js", "const ASSET_V = '199';", "const ASSET_V = '198';"),
    ("hq-ortu", "/css/hq.css", "position: sticky; inset-block-start: 0; z-index: 2;", "position: static;"),
]

HAZIR = """try{sessionStorage.setItem('yukiAcilis_v1','1');localStorage.setItem('yuki-ilk-kurulum_v1','test');
localStorage.setItem('yukiTema_v1','koyu');localStorage.setItem('yukiViewMode_v1','__KIP__');localStorage.setItem('yukiViewMode','__KIP__');
}catch(e){}"""
KART = """() => { const r = e => { if (!e || !e.getClientRects().length) return null; const b = e.getBoundingClientRect();
    return {y: b.top, alt: b.bottom, h: b.height}; };
  const w = document.querySelector('.hr-widget[data-hr-tab="memory"]');
  const g = w && !w.classList.contains('hr-w-mobil-gizli') && getComputedStyle(w).display !== 'none' ? w : null;
  const body = document.getElementById('hr-mem-body');
  return {kart: r(g), durum: r(document.getElementById('hr-status')), metin: body ? body.innerText : '',
          satir: document.querySelectorAll('#hr-mem-body .hk-ani').length,
          cubuk: document.querySelectorAll('#hr-mem-body .hk-cubuk').length,
          svg: !!document.getElementById('hr-mem-svg')}; }"""

DOLU_STATS = {"enabled": True, "total": 5, "scopes": {}, "categories": {"fact": 3, "preference": 2}}
DOLU_LISTE = {
    "fact": [{"id": 11, "content": "Kahveyi şekersiz içer", "category": "fact", "importance": 0.9, "created_at": "2026-11-01T10:00:00"}],
    "preference": [{"id": 12, "content": "Kısa cevap sever", "category": "preference", "importance": 0.7, "created_at": "2026-11-02T09:30:00"}],
}


def sayfa(b, w, kip, mut, hata, hafiza=None):
    h = 844 if w < 600 else 800
    ctx = b.new_context(viewport={"width": w, "height": h}, service_workers="block")
    ctx.add_init_script(HAZIR.replace("__KIP__", kip))
    s = ctx.new_page()
    s.on("pageerror", lambda e: hata.append(str(e)[:160]))
    if mut:
        _, son, yeni, eski = mut

        def degistir(route, *_):
            y = route.fetch(); m = y.text()
            assert yeni in m, f"mutasyon metni yok: {yeni!r}"
            route.fulfill(response=y, body=m.replace(yeni, eski))
        s.route(re.compile(re.escape(son) + r"(\?.*)?$"), degistir)
    if hafiza == "dolu":
        s.route(re.compile(r"/api/memory/stats(\?.*)?$"), lambda r, *_: r.fulfill(status=200, content_type="application/json", body=json.dumps(DOLU_STATS)))
        s.route(re.compile(r"/api/memory\?.*category=(fact|preference)"), lambda r, *_: r.fulfill(
            status=200, content_type="application/json",
            body=json.dumps(DOLU_LISTE[re.search(r"category=(\w+)", r.request.url).group(1)])))
    elif hafiza in (503, 500):
        s.route(re.compile(r"/api/memory/stats(\?.*)?$"), lambda r, *_: r.fulfill(status=hafiza, content_type="application/json", body='{"detail":"x"}'))
    s.goto(BASE + "/ui/", wait_until="domcontentloaded")
    s.wait_for_timeout(3000)
    s.evaluate("for (const id of ['auth-screen','yuki-opening']) { const e = document.getElementById(id); if (e) { e.classList.add('hidden'); e.style.display = 'none'; } }"
               "document.querySelectorAll('.ilk-kurulum').forEach(e => e.style.display = 'none'); document.documentElement.classList.remove('ilk-kurulum-acik');")
    s.evaluate(f"window.setViewMode && window.setViewMode('{kip}')")
    s.wait_for_timeout(2500)
    return s


def olc(b, mut=None):
    sonuc, hata = [], []

    def k(ad, ok, kanit=""):
        sonuc.append((ad, bool(ok), kanit))
        print(("  ✓ " if ok else "  ✗ ") + ad + (f"  [{kanit}]" if kanit else ""), flush=True)

    # demo: hafıza kapalı (stats enabled:false)
    s = sayfa(b, 390, "hud-ring", mut, hata)
    r = s.evaluate(KART)
    kart, durum = r["kart"], r["durum"]
    k("390 HAFIZA kartı görünür", kart is not None)
    k("390 kart içerik boyunda (≤ 200 px)", kart and kart["h"] <= 200, kart and round(kart["h"]))
    k("390 'Sistemler aktif' satırı görünür ve kartın üstünde", durum and kart and durum["alt"] <= kart["y"],
      (durum and round(durum["alt"]), kart and round(kart["y"])))
    k("enabled:false → 'hafıza kapalı'", "hafıza kapalı" in r["metin"], r["metin"][:60].replace("\n", " · "))
    k("eski düğüm haritası yok", not r["svg"])
    s.context.close()

    for kod, beklenen, olmamali in ((503, "hafıza kapalı", "alınamadı"), (500, "hafıza alınamadı", "hafıza kapalı")):
        s = sayfa(b, 390, "hud-ring", mut, hata, hafiza=kod)
        m = s.evaluate(KART)["metin"]
        k(f"uç {kod} → '{beklenen}'", beklenen in m and olmamali not in m, m[:60].replace("\n", " · "))
        s.context.close()

    s = sayfa(b, 390, "hud-ring", mut, hata, hafiza="dolu")
    r = s.evaluate(KART)
    k("dolu: şerit '5 anı · 2 tür'", "5 anı" in r["metin"] and "2 tür" in r["metin"], r["metin"][:40].replace("\n", " · "))
    k("dolu: 2 dağılım çubuğu + 2 olgu/tercih satırı", r["cubuk"] == 2 and r["satir"] == 2, (r["cubuk"], r["satir"]))
    if r["satir"]:
        s.locator("#hr-mem-body .hk-ani").first.click()
        s.wait_for_timeout(300)
        m = s.evaluate("(document.querySelector('#hr-mem-body .hk-ani.sel small')||{}).innerText || ''")
        k("dolu: satıra dokununca tür + tarih", "Olgu" in m and "2026-11-01 10:00" in m, m)
    else:
        k("dolu: satıra dokununca tür + tarih", False, "satır yok")
    k("dolu: kart 390'da taşmadan kayar (kart ≤ ekranın yarısı)", r["kart"] and r["kart"]["h"] <= 844 / 2, r["kart"] and round(r["kart"]["h"]))
    s.context.close()

    # HQ 1280: menü kayınca başlık bandı değişmez
    s = sayfa(b, 1280, "chat", mut, hata)
    s.evaluate("switchTab('hq')")
    s.wait_for_timeout(2500)
    nb = s.evaluate("(() => { const n = document.getElementById('hq-subnav'); const r = n.getBoundingClientRect();"
                    " return {x: r.left, y: r.top, w: r.width, max: n.scrollHeight - n.clientHeight}; })()")
    bant = {"x": nb["x"] + 1, "y": nb["y"] + 2, "width": nb["w"] - 2, "height": 44}
    once = s.screenshot(clip=bant, animations="disabled")
    s.evaluate("document.getElementById('hq-subnav').scrollTop = 120")
    s.wait_for_timeout(400)
    sonra = s.screenshot(clip=bant, animations="disabled")
    k("1280 HQ menü kaydırılabilir (sınama anlamlı)", nb["max"] >= 120, nb["max"])
    k("1280 HQ menü kayınca başlık bandı aynı (yazı başlık altına girmez)", once == sonra)
    s.context.close()

    # Plan 390: hafta şeridi gün adları
    s = sayfa(b, 390, "chat", mut, hata)
    s.evaluate("switchTab('planner')")
    s.wait_for_timeout(3500)
    fr = next((f for f in s.frames if "planner" in f.url), None)
    gun = fr.evaluate("[...document.querySelectorAll('#gundem-view .g-gun span')].map(e => e.textContent.trim())") if fr else []
    k("390 Plan hafta şeridi 7 gün, iki harf", len(gun) == 7 and all(len(g) == 2 for g in gun), gun)
    # ASSET_V: index.html'nin istediği chat-modes sürümü dosyanın kendi ASSET_V'siyle aynı
    html = s.evaluate("fetch('/ui/').then(r => r.text())")
    js = s.evaluate("fetch('/ui/modes/chat-modes.js').then(r => r.text())")
    iv = re.search(r"chat-modes\.js\?v=(\d+)", html)
    av = re.search(r"const ASSET_V = '(\d+)'", js)
    k("index chat-modes ?v= == ASSET_V", iv and av and iv.group(1) == av.group(1), (iv and iv.group(1), av and av.group(1)))
    s.context.close()

    k("JS istisnası 0", not hata, hata[:2])
    return sonuc


def main():
    with sync_playwright() as p:
        b = p.chromium.launch(args=["--use-gl=swiftshader", "--enable-unsafe-swiftshader"])
        if MUTASYON:
            sec = [a.split("=", 1)[1] for a in sys.argv if a.startswith("--yalniz=")]
            secili = [m for m in MUTASYONLAR if not sec or m[0] in sec]
            yak = 0
            for m in secili:
                kalan = [ad for ad, ok, _ in olc(b, m) if not ok]
                yak += bool(kalan)
                print(("✓ yakalandı" if kalan else "✗ KAÇTI"), m[0], ("— " + kalan[0]) if kalan else "", flush=True)
            print(f"mutasyon {yak}/{len(secili)}")
            b.close()
            return len(secili) - yak
        r = olc(b)
        b.close()
    kalan = [x for x in r if not x[1]]
    print(f"{len(r) - len(kalan)} geçti · {len(kalan)} kaldı")
    return len(kalan)


if __name__ == "__main__":
    sys.exit(main())
