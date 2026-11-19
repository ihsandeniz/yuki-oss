"""Anahtar yokken Halka "hazır" görünmez (goz 11-13 #1b) — merkez etiketi, durum satırı, kayan yazı ve
model çipi sohbet rozetiyle AYNI hükmü (`/api/llm/key/status`, `set || yerel`) söyler; anahtar Ayar ›
Anahtar'dan kaydedilince (gerçek arayüz yolu: hqSaveKey → POST /api/llm/key → keyInit) hepsi tazelenir.

    python3 frontend/tests/test_halka_anahtar.py [BASE]              # varsayılan http://127.0.0.1:8031
    python3 frontend/tests/test_halka_anahtar.py [BASE] --mutasyon   # her kapıyı bir kez kır

/api/llm/key/status ve POST /api/llm/key Playwright'la taklit edilir (gerçek anahtar yazılmaz, sunucu
ayarı değişmez). SW kapalı (devralınca /api isteklerini page.route göremez). Normal (animasyonlu) mod.
"""
import json
import re
import sys
from playwright.sync_api import sync_playwright

ARGS = [a for a in sys.argv[1:] if not a.startswith("--")]
BASE = ARGS[0] if ARGS else "http://127.0.0.1:8031"
MUTASYON = "--mutasyon" in sys.argv

MUTASYONLAR = [
    ("olay-yayilmaz", "/js/core.js", "window.dispatchEvent(new CustomEvent('yuki-anahtar-durum', { detail: { hazir: _anahtarHazir } }));", ""),
    ("durum-satiri", "/modes/hud-ring.js", "_hrt(_anahtarYok() ? 'hudring.durum.anahtar-yok' : 'hudring.durum.idle')", "_hrt('hudring.durum.idle')"),
    ("merkez-etiket", "/modes/hud-ring.js", "(!STATE_LBL[s] || s === 'idle') && _anahtarYok() ? 'durum.anahtar-yok' :", "false ? 'durum.anahtar-yok' :"),
    # kayan-yazi mutasyonu yok: kayan yazı açılıştan beri olay döndürür ("Halka modu aktif · saat");
    # varsayılan metin yalnız olay listesi boşken görünür → olağan akışta ölçülemez (11-13, KAÇTI → çıkarıldı).
    ("halka-dinlemez", "/modes/hud-ring.js", "window.addEventListener('yuki-anahtar-durum', () => {", "window.addEventListener('yuki-anahtar-durum-YOK', () => {"),
    ("cip-sinifi", "/modes/sohbet-sahne.js", "hapMod.classList.toggle('anahtar-yok', yok);", "hapMod.classList.toggle('anahtar-yok', false);"),
    ("cip-css", "/modes/sohbet-sahne.css", "#hap-model.anahtar-yok .hap-kur { display: inline;", "#hap-model.anahtar-yok .hap-kur { display: none;"),
    ("cip-popover-geri", "/modes/sohbet-sahne.js", "hapMod.setAttribute('popovertarget', hedefPop);", "void 0;"),
    ("sahne-kurulum-sinifi", "/modes/hud-ring.js", "stage.className = 'hr-idle' + (_anahtarYok() ? ' hr-anahtar-yok' : '');", "stage.className = 'hr-idle';"),
    ("cip-kesilmez", "/modes/sohbet-sahne.css", "#hap-model.anahtar-yok .hap-kur { display: inline; max-inline-size: none; }", "#hap-model.anahtar-yok .hap-kur { display: inline; }"),
    # 11-14 birleşik: telefonda model çipi daralabilir (sohbet-kisisel.css) — anahtar yokken daralmaz
    ("cip-daralmaz", "/css/sohbet-kisisel.css", "#hap-model.anahtar-yok { flex-shrink: 0; }", "#hap-model.anahtar-yok { }"),
    ("sari-durum", "/modes/hud-ring.css", "#hr-stage.hr-idle.hr-anahtar-yok #hr-status { color: #f5cf73; }", "#hr-stage.hr-idle.hr-anahtar-yok #hr-status { }"),
]


def olc_sayfa(s):
    return s.evaluate("""() => {
      const g = e => { if (!e) return false; const r = e.getBoundingClientRect(), c = getComputedStyle(e);
        return r.width > 0 && r.height > 0 && c.display !== 'none' && c.visibility !== 'hidden'; };
      const m = document.getElementById('hap-model'), kur = document.getElementById('hap-model-kur');
      const gorunenCip = m ? [...m.querySelectorAll('.hap-metin')].filter(g).map(e => e.textContent.trim()).join('|') : '';
      return {
        merkez: (document.getElementById('hr-core-status') || {}).textContent || '',
        durum: (document.getElementById('hr-status') || {}).textContent || '',
        durumRenk: document.getElementById('hr-status') ? getComputedStyle(document.getElementById('hr-status')).color : '',
        kayan: (document.getElementById('hr-ticker-txt') || {}).textContent || '',
        cipSinif: m ? m.className : '', cip: gorunenCip, pop: m ? m.getAttribute('popovertarget') : null,
        kurGorunur: g(kur), kurKesik: kur ? kur.scrollWidth > kur.clientWidth + 0.5 : null,
      };
    }""")


def olc(b, mut=None):
    sonuc = []

    def k(ad, kosul, ay=""):
        sonuc.append((ad, bool(kosul), ay))

    # 360: 11-15 — 390'da çipin yeri bol (çerçeve kalktı), cip-daralmaz kapısı yalnız daha dar telefonda sınanır
    for w in (360, 390, 1280):
        s = b.new_context(viewport={"width": w, "height": 844 if w < 500 else 800}, service_workers="block").new_page()
        hata = []
        s.on("pageerror", lambda e: hata.append(str(e)))
        s.route("**://127.0.0.1:8000/**", lambda r: r.abort())
        kutu = {"set": False, "post": 0}

        def durum(route, *_):
            route.fulfill(status=200, content_type="application/json", body=json.dumps(
                {"set": kutu["set"], "yerel": False, "provider": "openrouter", "provider_ad": "OpenRouter",
                 "model": "google/gemma-4-26b-a4b-it:free", "masked": "sk-or-…test" if kutu["set"] else "",
                 "anahtar_gerekir": True, "saglayicilar": {}}))

        def kaydet(route, req):
            if req.method != "POST":
                return route.continue_()
            kutu["post"] += 1
            kutu["set"] = True       # sunucu anahtarı kaydetti — sonraki status bunu söyler
            route.fulfill(status=200, content_type="application/json", body=json.dumps({"ok": True, "message": "✓ Kaydedildi"}))
        s.route(re.compile(r"/api/llm/key/status(\?.*)?$"), durum)
        s.route(re.compile(r"/api/llm/key$"), kaydet)
        if mut:
            _, son, yeni, eski = mut

            def degistir(route, *_):
                y = route.fetch(); m = y.text()
                assert yeni in m, f"mutasyon metni yok: {yeni!r}"
                route.fulfill(response=y, body=m.replace(yeni, eski))
            s.route(re.compile(re.escape(son) + r"(\?.*)?$"), degistir)
        s.goto(BASE + "/ui/")
        s.wait_for_timeout(6500)
        a = s.get_by_text("Şimdilik atla")
        if a.count() and a.first.is_visible():
            a.first.click(); s.wait_for_timeout(1000)
        s.evaluate("switchTab('chat')")
        s.wait_for_timeout(2000)

        r = olc_sayfa(s)
        k(f"{w} yok → merkez ANAHTAR YOK", r["merkez"].strip() == "ANAHTAR YOK", r["merkez"])
        k(f"{w} yok → durum satırı kurulum", "Kurulum gerekli" in r["durum"] and "Sistemler aktif" not in r["durum"], r["durum"])
        k(f"{w} yok → durum satırı sarı", r["durumRenk"] == "rgb(245, 207, 115)", r["durumRenk"])
        k(f"{w} yok → kayan yazı 'Sistemler aktif' demez", "Sistemler aktif" not in r["kayan"], r["kayan"])
        k(f"{w} yok → çip kurulum gerekli", "anahtar-yok" in r["cipSinif"] and r["kurGorunur"]
          and r["cip"] == "kurulum gerekli" and r["pop"] is None, r)
        k(f"{w} yok → çip metni kesilmez", r["kurKesik"] is False, r["kurKesik"])
        # çipe basınca Ayar › Anahtar açılır
        s.click("#hap-model")
        s.wait_for_timeout(2500)
        yer = s.evaluate("[document.documentElement.getAttribute('data-tab'), (document.getElementById('tab-hq')||{dataset:{}}).dataset.hq]")
        k(f"{w} çip → Ayar › Anahtar", yer == ["hq", "key"], yer)
        # gerçek arayüz yolu: anahtarı yaz, Kaydet ve dene (çip açmadıysa — yukarıda kaldı — yine de Anahtar'a git)
        if yer != ["hq", "key"]:
            s.evaluate("switchTab('hq'); switchHqTab('key')"); s.wait_for_timeout(2500)
        try:
            s.wait_for_selector("#hq-key-input", timeout=10000)
            s.fill("#hq-key-input", "sk-or-v1-ornek-test")
            s.click("#hq-key-save")
            s.wait_for_timeout(3000)
        except Exception as e:  # noqa: BLE001
            k(f"{w} Anahtar formu açılır", False, str(e)[:120])
        k(f"{w} POST /api/llm/key gitti", kutu["post"] == 1, kutu["post"])
        s.evaluate("switchTab('chat')")
        s.wait_for_timeout(2000)
        r = olc_sayfa(s)
        k(f"{w} kayıt → merkez HAZIR", r["merkez"].strip() == "HAZIR", r["merkez"])
        k(f"{w} kayıt → durum satırı", "Sistemler aktif" in r["durum"], r["durum"])
        k(f"{w} kayıt → çip model adı", "anahtar-yok" not in r["cipSinif"] and not r["kurGorunur"]
          and "gemma" in r["cip"] and r["pop"] == "model-popover", r)
        k(f"{w} JS istisnası 0", not hata, hata[:2])
        s.context.close()
    return sonuc


def main():
    with sync_playwright() as p:
        b = p.chromium.launch()
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
    for ad, _, ay in kalan:
        print("✗", ad, str(ay)[:300])
    print(f"{len(r) - len(kalan)} geçti · {len(kalan)} kaldı")
    return len(kalan)


if __name__ == "__main__":
    sys.exit(main())
