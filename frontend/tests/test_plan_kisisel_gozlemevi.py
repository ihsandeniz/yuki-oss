"""PLAN · Gözlemevi iskeleti (2026-11-13 arayüz turu).

Ne değişti: üst şerit = serif "Plan / GÖZLEMEVİ" + GÜNDEM·LİSTELER·TAKVİM·BÜTÇE·FİTNES + sayaç çipleri;
liste/takvim sütunu masaüstünde SAĞDA; GÜNDEM kart kutusu yerine "deste" (üst kıl çizgi + versal etiket +
serif italik alt yazı + canlı sayı). Görünüm `css/plan-gozlemevi.css`, FİTNES'e dokunmaz.

Çalıştırma (parolasız ikinci örnek; görev yoksa test kendi demo görevlerini ekler — yalnız o örneğin geçici verisine):
    YUKI_URL=http://127.0.0.1:8014 python frontend/tests/test_plan_kisisel_gozlemevi.py
    (pytest de toplar: `python -m pytest frontend/tests/test_plan_kisisel_gozlemevi.py -q`)

Kapılar:
  S1  plan-gozlemevi.css planner.css'ten SONRA bağlı · body.kimlik-uyum
  S2  ham renk yalnız § 0 belirteç bloğunda (kuralda #hex / rgb( yok)
  S3  renk köprüsü #fitness-view'e sızmaz (seçicide yok + hesaplanmış --text Fitnes'te köprü değeri değil)
  S4  yeni anahtarların Türkçe yedeği var; sözlükte anahtar VARSA yedek onu ezmez
  T1  1280: marka "Plan", 5 alt sekme, şeritte 4 çip, liste sütunu sağda, gündem desteleri, anahtar adı sızmıyor
  T2  390: şerit görünür, alt sekmeler gizli, yalnız 2 çip, yatay taşma yok, alt menü görünür
  T3  LİSTELER: defter açılır, mor çizgi LİSTELER'de, GÜNDEM'de değil
  T4  kabukta (index.html iframe) ☰ markayı örtmez — 390 ve 1280
  Her ekranda JS istisnası 0.
"""
from __future__ import annotations

import json
import os
import re
import sys
import time
import urllib.request
from pathlib import Path

BASE = os.getenv("YUKI_URL", "http://127.0.0.1:8014")
ON = Path(__file__).resolve().parents[1]
MOR = "rgb(169, 147, 255)"
sonuc: list[tuple[str, bool, str]] = []


def kontrol(ad, ok, ayrinti=""):
    sonuc.append((ad, bool(ok), ayrinti))
    print(("✓ " if ok else "✗ ") + ad + (f"  ({ayrinti})" if ayrinti else ""))


# ── Statik ─────────────────────────────────────────────────────────── #
def statik():
    html = (ON / "planner.html").read_text(encoding="utf-8")
    css = (ON / "css/plan-gozlemevi.css").read_text(encoding="utf-8")
    i_pl, i_go = html.find("/ui/css/planner.css"), html.find("/ui/css/plan-gozlemevi.css")
    kontrol("S1 plan-gozlemevi.css planner.css'ten sonra", 0 <= i_pl < i_go, f"{i_pl} < {i_go}")
    kontrol("S1 body.kimlik-uyum", re.search(r'<body class="kimlik-uyum">', html) is not None)

    govde = re.sub(r"/\*.*?\*/", "", css, flags=re.S)
    blok0 = re.search(r"\.kimlik-uyum \{[^}]*\}", govde)                     # § 0 belirteçler
    kalan = govde.replace(blok0.group(0), "", 1) if blok0 else govde
    ham = re.findall(r"#[0-9a-fA-F]{3,8}\b|\brgba?\(", kalan)
    kontrol("S2 ham renk yalnız belirteç bloğunda", blok0 and not ham, f"ham: {ham[:5]}")

    kopru = re.search(r"\.kimlik-uyum :is\(([^)]*)\) \{\s*--bg:", govde)
    kontrol("S3 köprü seçicisinde #fitness-view yok", kopru and "#fitness-view" not in kopru.group(1),
            kopru.group(1) if kopru else "köprü bulunamadı")


# ── Demo veri (yalnız hedef örneğin kendi verisi) ───────────────────── #
def _istek(yol, govde=None):
    v = json.dumps(govde).encode() if govde is not None else None
    r = urllib.request.Request(BASE + yol, data=v, method="POST" if v else "GET", headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(r, timeout=10) as y:
        return json.loads(y.read() or b"null")


def demo_veri():
    from datetime import date, timedelta
    l = _istek("/api/todo/lists")
    l = l.get("lists", l) if isinstance(l, dict) else l
    if len(l) > 1:
        return
    a = _istek("/api/todo/lists", {"name": "Test A", "color": "cyan"})
    lid = a.get("id") or a.get("list", {}).get("id")
    g = lambda n: (date.today() + timedelta(days=n)).isoformat()
    for t, d in [("bugün işi", g(0)), ("geciken iş", g(-2)), ("yakın iş", g(3)), ("tarihsiz iş", None)]:
        _istek(f"/api/todo/lists/{lid}/tasks", {"title": t, "due_date": d})


# ── Tarayıcı ───────────────────────────────────────────────────────── #
def tarayici_testleri():
    from playwright.sync_api import sync_playwright
    tr_ek = "window.YukiSozluk.tr['plan.marka']='Plan*';"          # S4: sözlükteki anahtar korunmalı
    with sync_playwright() as p:
        b = p.chromium.launch()

        def ac(gen, yol="/ui/planner.html", sozluk_ek=False):
            ctx = b.new_context(viewport={"width": gen, "height": 800 if gen > 500 else 844}, service_workers="block")
            ctx.add_init_script("try{localStorage.setItem('yuki_kurulum_v1','tamam');localStorage.setItem('yukiDil_v1','tr')}catch(e){}")
            if sozluk_ek:
                def tr_js(route):
                    r = route.fetch()
                    route.fulfill(response=r, body=r.text() + "\n" + tr_ek)
                ctx.route("**/js/diller/tr.js*", tr_js)
            pg = ctx.new_page()
            hatalar = []
            pg.on("pageerror", lambda e: hatalar.append(str(e)[:200]))
            pg.goto(BASE + yol)
            pg.wait_for_timeout(2500)
            return ctx, pg, hatalar

        # T1 · 1280
        ctx, pg, h = ac(1280)
        d = pg.evaluate("""() => {
          const r = s => { const e = document.querySelector(s); return e ? e.getBoundingClientRect() : null; };
          const gor = e => e && getComputedStyle(e).display !== 'none' && e.getBoundingClientRect().width > 0;
          const cipler = [...document.querySelectorAll('#tab-bar > #stats-bar .sk-cip')].filter(gor).length;
          const sizan = [...document.querySelectorAll('body *')].filter(e => e.children.length === 0 && /^plan\\.[a-z-]+$/.test((e.textContent||'').trim())).length;
          return { marka: document.querySelector('#tab-bar .marka span')?.textContent.trim(),
            altin: document.querySelector('#tab-bar .marka small')?.textContent.trim(),
            sekme: [...document.querySelectorAll('#tab-bar .sk-alt')].filter(gor).length, cipler, sizan,
            fitnesAcik: !!(window.YukiOzellik && window.YukiOzellik.acik && window.YukiOzellik.acik('fitnes')),
            sol: r('#left-panel'), orta: r('#mid-panel'), deste: document.querySelectorAll('#gundem-view .deste').length,
            sayfa: !!document.querySelector('#gundem-view .g-sayfa .ray'), em: document.querySelectorAll('#gundem-view .bas em').length,
            fitText: getComputedStyle(document.getElementById('fitness-view') || document.body).getPropertyValue('--text').trim(),
            appText: getComputedStyle(document.getElementById('app')).getPropertyValue('--text').trim(),
            hafta: document.getElementById('s-week')?.textContent.trim() };
        }""")
        kontrol("T1 marka 'Plan' + 'GÖZLEMEVİ'", d["marka"] == "Plan" and d["altin"] == "GÖZLEMEVİ", f"{d['marka']}/{d['altin']}")
        # FİTNES bayrakla gelir (ürün varsayılanı KAPALI): açıkken 5, kapalıyken 4 alt sekme.
        beklenen = 5 if d["fitnesAcik"] else 4
        kontrol(f"T1 {beklenen} alt sekme görünür (Fitnes {'açık' if d['fitnesAcik'] else 'kapalı'})", d["sekme"] == beklenen, str(d["sekme"]))
        kontrol("T1 şeritte 4 sayaç çipi", d["cipler"] == 4 and d["hafta"] not in ("", "-"), f"{d['cipler']} · hafta={d['hafta']}")
        kontrol("T1 liste sütunu sağda", d["sol"] and d["orta"] and d["sol"]["x"] > d["orta"]["x"],
                f"sol x={d['sol'] and round(d['sol']['x'])} orta x={d['orta'] and round(d['orta']['x'])}")
        kontrol("T1 gündem desteleri + günün sayfası rayı", d["deste"] >= 3 and d["sayfa"] and d["em"] >= 3, f"deste={d['deste']} em={d['em']}")
        kontrol("T1 anahtar adı ekrana sızmıyor", d["sizan"] == 0, str(d["sizan"]))
        kontrol("S3 Fitnes köprü değeri almıyor", d["appText"] != d["fitText"], f"app={d['appText']} fit={d['fitText']}")

        # T3 · LİSTELER
        pg.click("#mode-lists")
        pg.wait_for_timeout(800)
        t3 = pg.evaluate(f"""() => ({{ defter: document.body.classList.contains('defter'),
          lis: getComputedStyle(document.getElementById('mode-lists')).borderBottomColor,
          gun: getComputedStyle(document.getElementById('mode-todo')).borderBottomColor }})""")
        kontrol("T3 LİSTELER defteri açar, mor çizgi LİSTELER'de", t3["defter"] and t3["lis"] == MOR and t3["gun"] != MOR, str(t3))
        kontrol("T1/T3 JS istisnası 0 (1280)", not h, "; ".join(h[:2]))
        ctx.close()

        # T2 · 390
        ctx, pg, h = ac(390)
        d = pg.evaluate("""() => {
          const gor = e => e && getComputedStyle(e).display !== 'none' && e.getBoundingClientRect().width > 0;
          const sayfa = document.querySelector('#gundem-view .g-sayfa');
          return { serit: gor(document.getElementById('tab-bar')), nav: gor(document.querySelector('#tab-bar .sk-altlar')),
            cipler: [...document.querySelectorAll('#tab-bar > #stats-bar .sk-cip')].filter(gor).length,
            tasma: document.documentElement.scrollWidth, sag: sayfa ? sayfa.getBoundingClientRect().right : null,
            alt: gor(document.getElementById('mobile-nav')) };
        }""")
        kontrol("T2 şerit görünür, alt sekmeler gizli", d["serit"] and not d["nav"], str(d))
        kontrol("T2 telefonda 2 çip", d["cipler"] == 2, str(d["cipler"]))
        kontrol("T2 yatay taşma yok", d["tasma"] <= 390 and d["sag"] is not None and d["sag"] <= 390 - 24, f"scroll={d['tasma']} sağ={d['sag']}")
        kontrol("T2 alt menü görünür", d["alt"])
        kontrol("T2 JS istisnası 0 (390)", not h, "; ".join(h[:2]))
        ctx.close()

        # S4 · sözlükte anahtar varsa yedek ezmez
        ctx, pg, h = ac(1280, sozluk_ek=True)
        m = pg.evaluate("document.querySelector('#tab-bar .marka span')?.textContent.trim()")
        kontrol("S4 sözlükteki anahtar yedekle ezilmiyor", m == "Plan*", str(m))
        ctx.close()

        # T4 · kabukta ☰ markayı örtmez
        for gen in (390, 1280):
            ctx, pg, h = ac(gen, "/ui/index.html")
            pg.wait_for_timeout(9000)                                    # açılış animasyonu (normal mod)
            pg.evaluate("window.switchTab && switchTab('planner')")
            pg.wait_for_timeout(3500)
            fr = next((f for f in pg.frames if "planner.html" in f.url), None)
            if not fr:
                kontrol(f"T4 {gen} planner iframe yüklendi", False)
                ctx.close(); continue
            ifr = pg.locator("#planner-iframe").bounding_box()
            mk = fr.evaluate("(() => { const r = document.querySelector('#tab-bar .marka').getBoundingClientRect(); return [r.x, r.y, r.width, r.height]; })()")
            dugme = pg.evaluate("""() => { const c = [...document.querySelectorAll('button, [role=button]')].filter(e => {
                const r = e.getBoundingClientRect(), s = getComputedStyle(e);
                return r.width > 0 && r.x < 80 && r.y < 80 && s.visibility !== 'hidden' && s.display !== 'none' && !e.closest('iframe'); });
              return c.map(e => { const r = e.getBoundingClientRect(); return [r.x, r.y, r.width, r.height]; }); }""")
            mx = ifr["x"] + mk[0]; my = ifr["y"] + mk[1]
            ortu = [b_ for b_ in dugme if b_[0] < mx + mk[2] and mx < b_[0] + b_[2] and b_[1] < my + mk[3] and my < b_[1] + b_[3]]
            kontrol(f"T4 {gen} kabukta ☰ markayı örtmüyor", not ortu, f"marka x={round(mx)} örten={ortu[:1]}")
            kontrol(f"T4 {gen} kabuk JS istisnası 0", not h, "; ".join(h[:2]))
            ctx.close()
        b.close()


def calistir() -> int:
    sonuc.clear()
    statik()
    try:
        urllib.request.urlopen(BASE + "/health", timeout=3)
    except Exception:
        print(f"… sunucu yok ({BASE}) — tarayıcı kapıları atlandı")
        return sum(1 for _, ok, _ in sonuc if not ok)
    demo_veri()
    tarayici_testleri()
    kalan = sum(1 for _, ok, _ in sonuc if not ok)
    print(f"\ngeçti {len(sonuc) - kalan} · kaldı {kalan}")
    return kalan


def test_plan_gozlemevi():
    assert calistir() == 0


if __name__ == "__main__":
    sys.exit(1 if calistir() else 0)
