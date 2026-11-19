"""İlk sürümde olmayan özellikler (Atölye · PLAN›FİTNES) arayüzde kapalı mı; PANEL (Komuta kanvası) 11-13'ten beri hiç yok.

    # backend/ içinde, iki motor: biri varsayılan (üçü kapalı), biri üç bayrak açık
    YUKI_DATA_DIR=$(mktemp -d) python -m uvicorn app.main:app --port 18791
    ATOLYE=true KOMUTA_KANVASI=true FITNES=true YUKI_DATA_DIR=$(mktemp -d) python -m uvicorn app.main:app --port 18792
    python frontend/tests/test_ozellik_kapisi.py http://127.0.0.1:18791 http://127.0.0.1:18792

Kapı `frontend/js/ozellik.js` (karar 2026-11-01: üçü "sonraya", varsayılan kapalı).
Atölye bayrağı arka uçta (`ATOLYE`, kapalıyken /api/gorev 404). Fitnes de arka uçta
bayraklı (`FITNES` → `/api/yetki` features.fitnes); açık motor bayraklarla kalkar, yanıt yine de
garanti için Playwright'la açık işaretlenir. Komuta kanvası 11-13'te iki uçtan da silindi:
yanıta bilerek `komuta_kanvasi: true` eklenir, kapının bu adı tanımadığı ölçülür.
Ölçer (390 ve 1280, normal/animasyonlu mod): kapalıyken giriş görünmez, doğrudan yol
(switchTab, widget #wtab, setMode, mobileTab, formAc) içeri sokmaz, Atölye 404 yoklaması
yapılmaz, kanvas kurulmaz; açıkken hepsi geri gelir. JS istisnası 0.
"""
import json
import sys

from playwright.sync_api import sync_playwright

KAPALI = sys.argv[1] if len(sys.argv) > 1 else "http://127.0.0.1:18791"
ACIK = sys.argv[2] if len(sys.argv) > 2 else "http://127.0.0.1:18792"
sonuc = []


def kontrol(ad, kosul, ek=""):
    sonuc.append((ad, bool(kosul)))
    print(("✓ " if kosul else "✗ ") + ad + (f"  ({ek})" if ek else ""))


GORUNUM_JS = "id => { const e = document.getElementById(id); return e ? getComputedStyle(e).display : 'YOK'; }"


def yetki_ac(route):
    """/api/yetki yanıtında komuta_kanvasi + fitnes açık olsun (motor bayraksız kalktıysa da)."""
    r = route.fetch()
    d = r.json()
    d.setdefault("features", {}).update({"komuta_kanvasi": True, "fitnes": True})
    route.fulfill(response=r, body=json.dumps(d), headers={**r.headers, "content-type": "application/json"})


def ac(tarayici, url, gen, yuk, yetki_acik=False, yol="/ui/"):
    # SW engelli: SW'nin attığı istek (PLAN iframe'i) page.route'a görünmez, "açık" hâl ölçülemezdi.
    sayfa = tarayici.new_context(viewport={"width": gen, "height": yuk},
                                 service_workers="block" if yetki_acik else "allow").new_page()
    hatalar, istekler = [], []
    sayfa.on("pageerror", lambda e, H=hatalar: H.append(str(e)))
    sayfa.on("request", lambda r, I=istekler: I.append(r.url))
    if yetki_acik:
        sayfa.route("**/api/yetki", yetki_ac)
    sayfa.goto(url + yol, wait_until="load")
    sayfa.wait_for_timeout(6000)
    atla = sayfa.get_by_text("Şimdilik atla")
    if atla.count() and atla.first.is_visible():
        atla.first.click()
        sayfa.wait_for_timeout(1200)
    return sayfa, hatalar, istekler


def plan_cerceve(sayfa):
    sayfa.evaluate("switchTab('planner')")
    sayfa.wait_for_timeout(3500)
    fr = sayfa.frame_locator("#planner-iframe")
    fr.locator("#mode-todo").wait_for(state="attached", timeout=10000)
    return next(f for f in sayfa.frames if "planner.html" in f.url)


with sync_playwright() as p:
    tarayici = p.chromium.launch()
    for gen, yuk in [(390, 844), (1280, 800)]:
        e = f"[{gen}] "

        # ── KAPALI (varsayılan kurulum) ───────────────────────────────────
        sayfa, hatalar, istekler = ac(tarayici, KAPALI, gen, yuk)
        kontrol(e + "kapalı: Atölye 'Görev' düğmesi gizli",
                sayfa.evaluate(GORUNUM_JS, "gorev-baslat-btn") == "none",
                sayfa.evaluate(GORUNUM_JS, "gorev-baslat-btn"))
        sayfa.evaluate("window.GorevSerit && GorevSerit.formAc()")
        sayfa.wait_for_timeout(600)
        kontrol(e + "kapalı: formAc() Atölye formunu açmıyor",
                sayfa.evaluate("(() => { const f = document.getElementById('gorev-form'); return !f || f.hidden; })()"))
        sayfa.evaluate("document.dispatchEvent(new Event('visibilitychange'))")
        sayfa.wait_for_timeout(800)
        kontrol(e + "kapalı: görev şeridi /api/gorev/oneri yoklamıyor",
                not any("/api/gorev/oneri" in u for u in istekler),
                str([u for u in istekler if "/api/gorev" in u][:4]))
        # 11-13 : PANEL sekmesi arayüzden KALDIRILDI — düğme ve kap hiç yok.
        kontrol(e + "kapalı: PANEL sekme düğmesi yok",
                sayfa.evaluate(GORUNUM_JS, "tab-btn-panel") == "YOK",
                sayfa.evaluate(GORUNUM_JS, "tab-btn-panel"))
        sayfa.evaluate("switchTab('panel')")
        sayfa.wait_for_timeout(800)
        kontrol(e + "kapalı: switchTab('panel') sohbete düşer",
                sayfa.evaluate("document.documentElement.getAttribute('data-tab')") == "chat")
        # 11-13: Komuta Paneli ön yüz izi de silindi — köprü fonksiyonu hiç yok.
        kontrol(e + "kapalı: kanvas köprüsü yok (_kanvas tanımsız)",
                sayfa.evaluate("typeof _kanvas === 'undefined' && typeof _panelExecHata === 'undefined'"))
        kontrol(e + "kapalı: PANEL kabı yok",
                sayfa.evaluate("!document.getElementById('panel-content') && !document.getElementById('tab-panel')"))
        pf = plan_cerceve(sayfa)
        kontrol(e + "kapalı: PLAN›FİTNES düğmesi gizli",
                pf.evaluate(GORUNUM_JS, "mode-fitness") == "none", pf.evaluate(GORUNUM_JS, "mode-fitness"))
        kontrol(e + "kapalı: mobil şerit FİTNES gizli",
                pf.evaluate(GORUNUM_JS, "mnav-fitness") in ("none", "YOK"), pf.evaluate(GORUNUM_JS, "mnav-fitness"))
        kontrol(e + "kapalı: widget ANTRENMAN/BESLENME gizli",
                pf.evaluate("[...document.querySelectorAll('.wnav-btn[data-ozellik=fitnes]')]"
                            ".every(b => getComputedStyle(b).display === 'none')"))
        pf.evaluate("setMode('fitness')")
        pf.wait_for_timeout(400)
        kontrol(e + "kapalı: setMode('fitness') FİTNES'i açmıyor",
                pf.evaluate("getComputedStyle(document.getElementById('fitness-view')).display === 'none'"
                            " && _currentMode === 'todo'"))
        pf.evaluate("typeof mobileTab === 'function' && mobileTab('fitness')")
        pf.wait_for_timeout(400)
        kontrol(e + "kapalı: mobileTab('fitness') FİTNES'i açmıyor",
                pf.evaluate("getComputedStyle(document.getElementById('fitness-view')).display === 'none'"))
        if gen <= 768:  # mobil şerit yalnız dar ekranda; gizli FİTNES "seçili" kalmamalı, GÖREVLER yanar
            kontrol(e + "kapalı: mobileTab('fitness') sonrası seçili şerit düğmesi GÖREVLER",
                    pf.evaluate("(document.querySelector('.mnav-btn.active') || {}).id") == "mnav-tasks",
                    str(pf.evaluate("(document.querySelector('.mnav-btn.active') || {}).id")))
        kontrol(e + "kapalı: JS istisnası 0", not hatalar, "; ".join(hatalar[:3]))
        sayfa.context.close()

        # widget yolu: #wtab=panel → sohbet
        sayfa, hatalar, _ = ac(tarayici, KAPALI, gen, yuk, yol="/ui/?widget=1#wtab=panel")
        sayfa.evaluate("location.hash = 'wtab=panel'")
        sayfa.wait_for_timeout(1000)
        kontrol(e + "kapalı: widget #wtab=panel sohbete düşer",
                sayfa.evaluate("document.documentElement.getAttribute('data-tab')") == "chat")
        kontrol(e + "kapalı (widget): JS istisnası 0", not hatalar, "; ".join(hatalar[:3]))
        sayfa.context.close()

        # ── AÇIK (ATOLYE=true + yetki yanıtında kanvas/fitnes) ────────────
        sayfa, hatalar, istekler = ac(tarayici, ACIK, gen, yuk, yetki_acik=True)
        kontrol(e + "açık: Atölye 'Görev' düğmesi görünür",
                sayfa.evaluate(GORUNUM_JS, "gorev-baslat-btn") not in ("none", "YOK"),
                sayfa.evaluate(GORUNUM_JS, "gorev-baslat-btn"))
        kontrol(e + "açık: görev şeridi /api/gorev/oneri yokluyor",
                any("/api/gorev/oneri" in u for u in istekler))
        sayfa.evaluate("window.GorevSerit && GorevSerit.formAc()")
        sayfa.wait_for_timeout(800)
        kontrol(e + "açık: formAc() Atölye formunu açıyor",
                sayfa.evaluate("(() => { const f = document.getElementById('gorev-form'); return !!f && !f.hidden; })()"))
        sayfa.evaluate("GorevSerit.formKapat()")
        # 11-13 : bayrak açık olsa da PANEL arayüzü yok — kanvas kodu yüklenmez, sekme sohbete düşer.
        kontrol(e + "açık bayrak: PANEL sekme düğmesi yine yok",
                sayfa.evaluate(GORUNUM_JS, "tab-btn-panel") == "YOK")
        sayfa.evaluate("switchTab('panel')")
        sayfa.wait_for_timeout(1200)
        kontrol(e + "açık bayrak: switchTab('panel') sohbete düşer",
                sayfa.evaluate("document.documentElement.getAttribute('data-tab')") == "chat")
        kontrol(e + "açık bayrak: kanvas kodu yüklenmedi", sayfa.evaluate("typeof window.AliceCanvas === 'undefined'"))
        # Sunucu (eski/taklit) features.komuta_kanvasi=true dese de kapı bu adı artık tanımaz.
        kontrol(e + "açık bayrak: özellik kapısı komuta_kanvasi'yi tanımaz",
                sayfa.evaluate("!document.documentElement.hasAttribute('data-oz-komuta_kanvasi')"
                               " && window.YukiOzellik.acik('komuta_kanvasi') === false"))
        pf = plan_cerceve(sayfa)
        kontrol(e + "açık: PLAN›FİTNES düğmesi görünür", pf.evaluate(GORUNUM_JS, "mode-fitness") != "none")
        pf.evaluate("setMode('fitness')")
        pf.wait_for_timeout(600)
        kontrol(e + "açık: setMode('fitness') FİTNES'i açar",
                pf.evaluate("getComputedStyle(document.getElementById('fitness-view')).display !== 'none'"))
        kontrol(e + "açık: JS istisnası 0", not hatalar, "; ".join(hatalar[:3]))
        sayfa.context.close()
    tarayici.close()

gecti = sum(1 for _, s in sonuc if s)
kaldi = len(sonuc) - gecti
print(f"\ngeçti {gecti} · kaldı {kaldi}")
sys.exit(1 if kaldi else 0)
