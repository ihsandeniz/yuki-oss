"""Sohbet bağlantı rozeti ↔ HQ › Anahtar aynı hükmü söyler (goz 11-13: rozet "BAĞLI", Anahtar "Henüz bağlı değil").

    python3 frontend/tests/test_anahtar_rozeti.py [BASE]              # varsayılan http://127.0.0.1:8031
    python3 frontend/tests/test_anahtar_rozeti.py [BASE] --mutasyon   # her kapıyı bir kez kır, yakalandığını gör

Rozetin üç hâli: BAĞLI (backend + model hazır) · ANAHTAR YOK (backend var, servis kurulu değil, sarı)
· BAĞLANTI YOK (backend yok). `/api/llm/key/status` Playwright'la taklit edilir — arka ucun gerçek
anahtar durumuna bağlı değil. 390'da (HALKA) rozet çekili, hâl durum rozetinin içinde (::after).
Normal (animasyonlu) modda koşar. Mutasyon diske dokunmaz: dosya tarayıcıya bozuk metinle sunulur.
"""
import json
import re
import sys
from playwright.sync_api import sync_playwright

ARGS = [a for a in sys.argv[1:] if not a.startswith("--")]
BASE = ARGS[0] if ARGS else "http://127.0.0.1:8031"
MUTASYON = "--mutasyon" in sys.argv

MUTASYONLAR = [
    ("baglaninca-yoklama", "/js/core.js", "    _setWsPill(true);\n    _anahtarYokla();\n", "    _setWsPill(true);\n"),
    ("yerel-hazir-sayilir", "/js/core.js", "!!(d && (d.set || d.yerel))", "!!(d && d.set)"),
    ("anahtar-yok-metni", "/js/core.js", "lbl.textContent = _t('ust.anahtar-yok'); return;", "lbl.textContent = _t('ust.bagli'); return;"),
    ("degisim-olayi", "/js/core.js", "window.addEventListener('yuki-anahtar-degisti', _anahtarYokla);", ""),
    ("hq-olay-yayar", "/js/intro-sequences.js", "window.dispatchEvent(new CustomEvent('yuki-anahtar-degisti'));", "void 0;"),
    ("sari-nokta", "/css/kabuk.css", "#ws-pill.anahtar-yok #ws-dot { background: #f0b429;", "#ws-pill.anahtar-yok #ws-dot { background: #22c55e;"),
    ("halka-telefon-metni", "/css/kabuk.css", "content: attr(data-anahtar-metni)", "content: none"),
    ("telefon-ses-cekilir", "/css/kabuk.css", "body.hud-ring-mode #header:has(#ws-pill.anahtar-yok) #vol-icon { display: none; }", "body.hud-ring-mode #header:has(#ws-pill.anahtar-yok) #vol-icon { }"),
    ("masaustu-durum-rozeti", "/css/kabuk.css", "#header:has(#ws-pill.anahtar-yok) #state-badge.state-idle::after { content: attr(data-anahtar-metni);", "#header:has(#ws-pill.anahtar-yok) #state-badge.state-idle::after { content: attr(data-durum-metni);"),
    ("baglanti-yok-oncelikli", "/js/core.js", "const anahtarYok = online && _anahtarHazir === false;", "const anahtarYok = _anahtarHazir === false;"),
]

DURUMLAR = {
    "yok": (200, {"set": False, "yerel": False, "provider": "openrouter"}),
    "var": (200, {"set": True, "yerel": False, "provider": "openrouter", "masked": "sk-…abcd"}),
    "yerel": (200, {"set": False, "yerel": True, "provider": "ollama"}),
    "kilitli": (401, {"detail": "oturum"}),
}


def sayfa(b, w, durum, mut=None):
    # SW kapalı: sayfayı devralınca /api isteklerini o yapar ve page.route taklidi onları görmez
    # (gerçek kullanıcıda SW /api'yi ağa geçirir, sw.js `/api/` dalı — davranış aynı).
    s = b.new_context(viewport={"width": w, "height": 844 if w < 500 else 800},
                      service_workers="block").new_page()
    hata = []
    s.on("pageerror", lambda e: hata.append(str(e)))
    s.route("**://127.0.0.1:8000/**", lambda r: r.abort())
    kutu = {"durum": durum}

    def anahtar(route):
        kod, govde = DURUMLAR[kutu["durum"]]
        route.fulfill(status=kod, content_type="application/json", body=json.dumps(govde))
    s.route(re.compile(r"/api/llm/key/status(\?.*)?$"), anahtar)
    if mut:
        _, son, yeni, eski = mut

        def degistir(route):
            yanit = route.fetch()
            metin = yanit.text()
            assert yeni in metin, f"mutasyon metni dosyada yok: {yeni!r}"
            route.fulfill(response=yanit, body=metin.replace(yeni, eski))
        s.route(re.compile(re.escape(son) + r"(\?.*)?$"), degistir)
    s.goto(BASE + "/ui/")
    s.wait_for_timeout(6000)
    a = s.get_by_text("Şimdilik atla")
    if a.count() and a.first.is_visible():
        a.first.click()
        s.wait_for_timeout(1000)
    s.evaluate("switchTab('chat')")
    s.wait_for_timeout(1500)
    return s, hata, kutu


def rozet(s):
    return s.evaluate("""() => {
      const p = document.getElementById('ws-pill'), l = document.getElementById('ws-label');
      const b = document.getElementById('state-badge');
      const sonra = b ? getComputedStyle(b, '::after').content : '';
      return {sinif: p.className, metin: l.textContent.trim(), baslik: p.title,
              nokta: getComputedStyle(document.getElementById('ws-dot')).backgroundColor,
              sonra: sonra, halka: document.body.classList.contains('hud-ring-mode')};
    }""")


def olc(b, mut=None):
    sonuc = []

    def kontrol(ad, kosul, ayrinti=""):
        sonuc.append((ad, bool(kosul), ayrinti))

    for w in (390, 1280):
        # 1) anahtar yok → ANAHTAR YOK, sarı; 390'da durum rozetinin içinde
        s, hata, kutu = sayfa(b, w, "yok", mut)
        r = rozet(s)
        kontrol(f"{w} anahtar yok → sınıf", "anahtar-yok" in r["sinif"].split() and "online" in r["sinif"].split(), r)
        kontrol(f"{w} anahtar yok → metin", r["metin"] == "ANAHTAR YOK", r["metin"])
        kontrol(f"{w} anahtar yok → ipucu", "Anahtar" in r["baslik"], r["baslik"])
        if w >= 1000:
            kontrol(f"{w} anahtar yok → sarı nokta", r["nokta"] == "rgb(240, 180, 41)", r["nokta"])
            # boştaki durum rozeti "HAZIR" (yeşil) demez; bağlantı rozeti görsel olarak çekilir (goz 11-13 #1)
            kontrol(f"{w} anahtar yok → durum rozeti ANAHTAR YOK", "ANAHTAR YOK" in r["sonra"], r["sonra"])
            gen = s.evaluate("document.getElementById('ws-pill').getBoundingClientRect().width")
            kontrol(f"{w} anahtar yok → bağlantı rozeti çift söylemez", gen <= 1, gen)
        else:
            kontrol(f"{w} anahtar yok → durum rozetinde metin", "ANAHTAR YOK" in r["sonra"], r["sonra"])
        # üst çubukta görünen hiçbir düğme ekran dışına itilmez (390'da ⋯ kesiliyordu, goz-öncesi ölçüm 11-13)
        tasan = s.evaluate("""() => [...document.querySelectorAll('#header button, #header label, #header a, #header input:not([type=hidden])')]
            .filter(e => { const r = e.getBoundingClientRect(); return r.width > 0 && r.height > 0
                && getComputedStyle(e).visibility !== 'hidden' && r.right > innerWidth + 0.5; })
            .map(e => (e.id || e.className || e.tagName) + ':' + Math.round(e.getBoundingClientRect().right))""")
        kontrol(f"{w} anahtar yok → çubuk taşmıyor", not tasan, tasan)
        # 2) Ayar › Anahtar açılınca (kayıt sonrası aynı yol) rozet tazelenir
        kutu["durum"] = "var"
        s.evaluate("switchTab('hq')")
        s.wait_for_timeout(2000)
        s.evaluate("switchHqTab('key')")      # kullanıcının Ayar › Anahtar'a girmesi
        s.wait_for_timeout(2500)
        r = rozet(s)
        kontrol(f"{w} HQ anahtarı okuyunca → BAĞLI", r["metin"] == "BAĞLI" and "anahtar-yok" not in r["sinif"], r)
        # 3) olay → tazelenir (ilk kurulum sihirbazı da bunu yayar)
        kutu["durum"] = "yok"
        s.evaluate("window.dispatchEvent(new CustomEvent('yuki-anahtar-degisti'))")
        s.wait_for_timeout(800)
        kontrol(f"{w} olay → ANAHTAR YOK", rozet(s)["metin"] == "ANAHTAR YOK", rozet(s))
        # 4) bağlantı yoksa BAĞLANTI YOK önce gelir (anahtar yokken de)
        s.evaluate("_setWsPill(false)")
        r = rozet(s)
        kontrol(f"{w} kopuk → BAĞLANTI YOK", r["metin"] == "BAĞLANTI YOK" and r["sinif"] == "offline", r)
        s.evaluate("_setWsPill(true)")
        kontrol(f"{w} JS istisnası 0 (yok)", not hata, hata[:2])
        s.context.close()
        # 5) anahtar var / yerel model / oturum kilitli (bilinmiyor) → BAĞLI
        for d in ("var", "yerel", "kilitli"):
            s, hata, _ = sayfa(b, w, d, mut)
            r = rozet(s)
            kontrol(f"{w} {d} → BAĞLI", r["metin"] == "BAĞLI" and r["sinif"] == "online", r)
            kontrol(f"{w} JS istisnası 0 ({d})", not hata, hata[:2])
            s.context.close()
    return sonuc


def main():
    with sync_playwright() as p:
        b = p.chromium.launch()
        if MUTASYON:
            yakalanan = 0
            for m in MUTASYONLAR:
                kalan = [ad for ad, ok, _ in olc(b, m) if not ok]
                yakalanan += bool(kalan)
                print(("✓ yakalandı" if kalan else "✗ KAÇTI"), m[0], ("— " + kalan[0]) if kalan else "")
            print(f"mutasyon {yakalanan}/{len(MUTASYONLAR)}")
            b.close()
            return len(MUTASYONLAR) - yakalanan
        sonuc = olc(b)
        b.close()
    gecti = sum(ok for _, ok, _ in sonuc)
    for ad, ok, ay in sonuc:
        if not ok:
            print("✗", ad, str(ay)[:300])
    print(f"{gecti} geçti · {len(sonuc) - gecti} kaldı")
    return len(sonuc) - gecti


if __name__ == "__main__":
    sys.exit(main())
