"""İlk açılış sihirbazı — gerçek motor + tarayıcı (temiz veri klasörü).

    YUKI_DATA_DIR=$(mktemp -d) python -m uvicorn app.main:app --port 18791   # backend/ içinde
    python frontend/tests/test_ilk_kurulum_e2e.py http://127.0.0.1:18791 <ekran-klasörü>

Ölçer: temiz kurulumda sihirbaz açılıyor · 4 adım · yanlış anahtar REDDEDİLİYOR ve
kaydedilmiyor (providers'ta anahtar_var hâlâ False) · "Şimdilik atla" kapatıyor ve
yeniden yüklemede bir daha açılmıyor.
"""
import json
import sys
import urllib.request
from pathlib import Path

from playwright.sync_api import sync_playwright

URL = sys.argv[1] if len(sys.argv) > 1 else "http://127.0.0.1:18791"
EKRAN = Path(sys.argv[2]) if len(sys.argv) > 2 else Path(".")
sonuc = []


def kontrol(ad, kosul, ek=""):
    sonuc.append((ad, bool(kosul)))
    print(("✓ " if kosul else "✗ ") + ad + (f"  ({ek})" if ek else ""))


def anahtar_var_mi():
    with urllib.request.urlopen(URL + "/api/llm/providers") as r:
        return any(s["anahtar_var"] for s in json.load(r)["saglayicilar"])


with sync_playwright() as p:
    tarayici = p.chromium.launch()
    sayfa = tarayici.new_page(viewport={"width": 1100, "height": 760})
    sayfa.goto(URL + "/", wait_until="networkidle")
    kutu = sayfa.locator(".ilk-kurulum .ik-kutu")
    # B3 (11-14): tanıtım (#yuki-opening) oynarken sihirbaz görünmez; tanıtım bitince belirir.
    oynuyor = sayfa.evaluate("() => { const o = document.getElementById('yuki-opening'); return !!(o && o.firstChild); }")
    if oynuyor:
        kontrol("tanıtım oynarken sihirbaz gizli", not kutu.is_visible())
    try:
        kutu.wait_for(state="visible", timeout=20000)
    except Exception:  # noqa: BLE001 — aşağıdaki kontrol düşer
        pass
    kontrol("temiz kurulumda sihirbaz açılıyor", kutu.is_visible())
    kontrol("4 adım noktası", sayfa.locator(".ik-adimlar li").count() == 4)
    sayfa.screenshot(path=str(EKRAN / "sihirbaz-1-dil.png"))

    sayfa.locator(".ik-kart[data-dil='en']").click()
    sayfa.wait_for_timeout(400)
    kontrol("dil İngilizce'ye geçiyor", "language" in kutu.inner_text().lower(), kutu.inner_text()[:40])
    sayfa.locator(".ik-kart[data-dil='tr']").click()
    sayfa.wait_for_timeout(400)
    sayfa.locator(".ik-ileri[data-git='saglayici']").click()
    kartlar = sayfa.locator(".ik-kart[data-sag]")
    kontrol("sağlayıcı listesi dolu", kartlar.count() >= 2, f"{kartlar.count()} sağlayıcı")
    kontrol("ileri seçimsiz kapalı", sayfa.locator(".ik-ileri[data-git='anahtar']").is_disabled())
    sayfa.locator(".ik-kart[data-sag='openrouter']").click()
    sayfa.screenshot(path=str(EKRAN / "sihirbaz-2-saglayici.png"))
    sayfa.locator(".ik-ileri[data-git='anahtar']").click()

    sayfa.locator(".ik-ileri[data-sina]").click()
    kontrol("boş anahtar uyarısı", sayfa.locator(".ik-mesaj.hata").is_visible())
    sayfa.fill(".ik-girdi", "sk-or-v1-" + "0" * 64)
    sayfa.locator(".ik-ileri[data-sina]").click()
    sayfa.wait_for_selector(".ik-mesaj.hata", timeout=30000)
    sayfa.wait_for_function("!document.querySelector('.ik-ileri[data-sina]').disabled", timeout=30000)
    hata = sayfa.locator(".ik-mesaj.hata").inner_text()
    kontrol("yanlış anahtar reddedildi (ekranda hata)", bool(hata.strip()), hata[:80])
    kontrol("yanlış anahtar KAYDEDİLMEDİ", not anahtar_var_mi())
    kontrol("hâlâ anahtar adımında", sayfa.locator(".ik-girdi").is_visible())
    sayfa.screenshot(path=str(EKRAN / "sihirbaz-3-yanlis-anahtar.png"))

    sayfa.locator(".ik-atla").click()
    kontrol("Şimdilik atla kapatıyor", sayfa.locator(".ilk-kurulum").count() == 0)
    sayfa.reload(wait_until="networkidle")
    sayfa.wait_for_timeout(800)
    kontrol("atlandıktan sonra yeniden açılmıyor", sayfa.locator(".ilk-kurulum").count() == 0)
    tarayici.close()

kalan = [a for a, ok in sonuc if not ok]
print(f"\ngeçti {len(sonuc) - len(kalan)} · kaldı {len(kalan)}")
sys.exit(1 if kalan else 0)
