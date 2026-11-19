"""AppImage kap sınavının ölçüm yarısı — kabın içinde, Electron'a CDP ile bağlanır.

`scripts/appimage-kap-sinavi.sh` çağırır; tek başına anlamı yok. Yalnız ham gerçek basar
(`ADIM <ad> <değer>`), hükmü kabuk betiği verir.

Adımlar: pencere (CDP'de sayfa) · motor (sayfanın kökenindeki /health) · arayuz (sayfa
motordan yüklendi) · sihirbaz (.ilk-kurulum görünür) · js_istisna (sayfa hatası sayısı).
Ekran: 1280×800 ve 390×844, normal (animasyonlu) mod — reduced-motion zorlanmaz.
"""
import json
import os
import sys
import time
import urllib.request
from pathlib import Path

from playwright.sync_api import sync_playwright

CIKTI = Path(sys.argv[1] if len(sys.argv) > 1 else "/cikti")
# Windows/wine sınavı (windows-wine-sinavi.sh) aynı ölçümü başka portla kullanır.
CDP = os.environ.get("YUKI_CDP", "http://127.0.0.1:9222")


def adim(ad, deger):
    print(f"ADIM {ad} {deger}", flush=True)


def cdp_bekle(sure=240):
    son = None
    for _ in range(sure):
        try:
            with urllib.request.urlopen(CDP + "/json/version", timeout=2) as r:
                return json.loads(r.read())
        except Exception as e:  # uygulama henüz kalkmadı
            son = e
            time.sleep(1)
    raise RuntimeError(f"CDP gelmedi: {son}")


def hedef_bekle(sure=240):
    """CDP hedef listesinde motordan yüklenen ana sayfa görünene dek bekle.

    Playwright'a erken bağlanmak işe yaramaz: pencere file:// splash'tan http:// ana
    sayfaya geçerken Chromium süreç değiştirir, Playwright'ın sayfa nesnesi eski
    adreste kalır (ölçüldü 11-12: /json/list ana sayfayı gösterirken Playwright splash
    diyordu). O yüzden önce hedef listesinden bakılır, Playwright sonra bağlanır.
    """
    son = []
    for _ in range(sure):
        try:
            with urllib.request.urlopen(CDP + "/json/list", timeout=3) as r:
                son = [(h.get("type"), h.get("url")) for h in json.loads(r.read())]
        except Exception:
            son = []
        if any(t == "page" and u.startswith("http://127.0.0.1:") and "/ui/mini" not in u for t, u in son):
            return True, son
        time.sleep(1)
    return False, son


def ana_sayfa(tarayici):
    for bag in tarayici.contexts:
        for s in bag.pages:
            if s.url.startswith("http://127.0.0.1:") and "/ui/mini" not in s.url:
                return s
    return None


def main():
    try:
        cdp_bekle()
    except Exception as e:
        adim("pencere", f"yok {e}")
        return 1
    with sync_playwright() as p:
        tamam, hedefler = hedef_bekle()
        if not tamam:
            adim("pencere", "ok (yalnız splash)")
            adim("arayuz", f"yok hedefler={hedefler}")
            return 1
        time.sleep(3)  # ana sayfa yüklenmesini bitirsin
        tarayici = p.chromium.connect_over_cdp(CDP)
        sayfa = ana_sayfa(tarayici)
        if not sayfa:
            adim("pencere", "ok")
            adim("arayuz", f"yok playwright={[s.url for b in tarayici.contexts for s in b.pages]} hedefler={hedefler}")
            return 1
        adim("pencere", "ok")
        istisnalar = []
        sayfa.on("pageerror", lambda e: istisnalar.append(str(e)))
        # Hata dinleyicisi bağlanmadan önce olan istisnaları da yakalamak için baştan yükle.
        sayfa.reload(wait_until="load")
        koken = sayfa.url.split("/", 3)[:3]
        koken = "/".join(koken)
        try:
            with urllib.request.urlopen(koken + "/health", timeout=5) as r:
                adim("motor", f"{r.status} {koken}")
        except Exception as e:
            adim("motor", f"{getattr(e, 'code', 0)} {koken} {e}")
        adim("arayuz", f"ok {sayfa.url}")
        try:
            sayfa.wait_for_selector(".ilk-kurulum", state="visible", timeout=60000)
            adim("sihirbaz", "ok")
        except Exception as e:
            adim("sihirbaz", f"yok {str(e)[:120]}")
        for gen, yuk in ((1280, 800), (390, 844)):
            sayfa.set_viewport_size({"width": gen, "height": yuk})
            time.sleep(2.5)  # açılış animasyonu oturana dek (normal mod)
            sayfa.screenshot(path=str(CIKTI / f"sihirbaz-{gen}.png"))
        # Bir adım ilerle: sağlayıcı seçimine geçebiliyor mu (motorla konuşan adım).
        try:
            sayfa.set_viewport_size({"width": 1280, "height": 800})
            dugme = sayfa.locator(".ilk-kurulum button").filter(has_text="Devam").first
            if dugme.count() == 0:
                dugme = sayfa.locator(".ilk-kurulum button").last
            dugme.click(timeout=5000)
            time.sleep(2)
            sayfa.screenshot(path=str(CIKTI / "sihirbaz-2-1280.png"))
            adim("sihirbaz_ileri", "ok")
        except Exception as e:
            adim("sihirbaz_ileri", f"yok {str(e)[:120]}")
        (CIKTI / "istisnalar.json").write_text(json.dumps(istisnalar, ensure_ascii=False, indent=1))
        adim("js_istisna", len(istisnalar))
    return 0


if __name__ == "__main__":
    sys.exit(main())
