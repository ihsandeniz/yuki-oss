"""HARİTA › GÜNDEM kümeli liste — kaynak sayısı rozeti, 390 ve 1280 genişlikte, gerçek tarayıcı.

    YUKI_DATA_DIR=$(mktemp -d) python -m uvicorn app.main:app --port 18795   # backend/ içinde
    python frontend/tests/test_gundem_kume.py http://127.0.0.1:18795 [ekran-klasörü]

`/api/map/news` sahte cevapla yakalanır (ağ yok, deterministik). Kümeleme kuralı backend'de
ölçülür (`backend/tests/test_gundem_kume.py`); burada ölçülen ön yüz sözleşmesi:
- 3 kaynaklı olay tek satır, rozet "+2", rozet title'ı "{n} kaynak daha: …" (harita.gundem-kaynak) + öbür iki kaynağın adı
- tek kaynaklı satırda rozet yok, eski kaynak etiketi aynen
- kümeleme kapalı cevabı (alan yok) eskisi gibi çizilir
- rozet ve kaynak satır içinde kalır, metin kartı taşırmaz; JS istisnası 0
"""
import json
import sys
from pathlib import Path

from playwright.sync_api import sync_playwright

URL = sys.argv[1] if len(sys.argv) > 1 else "http://127.0.0.1:18795"
EKRAN = Path(sys.argv[2]) if len(sys.argv) > 2 else None
sonuc = []

KUMELI = {"items": [
    {"title": "Merkez Bankası politika faizini yüzde 40'ta sabit bıraktı - Haber A",
     "kaynak_sayisi": 3, "kaynaklar": ["Haber A", "Haber B", "Haber Cetvel Uzun Kaynak Adı"]},
    {"title": "İstanbul'da yarın yoğun kar yağışı bekleniyor - Hava D", "kaynak_sayisi": 1,
     "kaynaklar": ["Hava D"]},
    {"title": "Ege açıklarında 4,1 büyüklüğünde deprem meydana geldi - Çok Uzun Bir Haber Sitesi Adı",
     "kaynak_sayisi": 2, "kaynaklar": ["Çok Uzun Bir Haber Sitesi Adı", "Kısa"]},
], "count": 3}
HAM = {"items": [{"title": "Merkez Bankası politika faizini sabit bıraktı - Haber A"},
                 {"title": "Üniversite sınavı başvuru tarihleri duyuruldu - K2"}], "count": 2}


def kontrol(ad, kosul, ek=""):
    sonuc.append((ad, bool(kosul)))
    print(("✓ " if kosul else "✗ ") + ad + (f"  ({ek})" if ek else ""))


OLC = """() => {
  const kart = document.getElementById('map-gundem').getBoundingClientRect();
  return [...document.querySelectorAll('#map-news-list .mh-haber')].map(b => {
    const r = b.getBoundingClientRect(), n = b.querySelector('.mh-haber-n'),
          k = b.querySelector('.mh-haber-k'), t = b.querySelector('.mh-haber-t');
    const kr = k && k.getBoundingClientRect(), nr = n && n.getBoundingClientRect();
    return {rozet: n ? n.textContent : null, ipucu: n ? n.title : null,
            kaynak: k ? (k.querySelector('.mh-haber-ka') || k).textContent : null,
            satirIcinde: !k || (kr.right <= r.right + 0.5 && kr.left >= r.left - 0.5),
            rozetGorunur: !n || (nr.width > 0 && nr.right <= kr.right + 0.5),
            metinTasmaz: t.scrollWidth <= t.clientWidth + 1,
            kartIcinde: r.right <= kart.right + 0.5 && r.left >= kart.left - 0.5};
  });
}"""


def sayfa_ac(tarayici, gen, yuk, cevap, hareket="no-preference"):
    s = tarayici.new_page(viewport={"width": gen, "height": yuk}, reduced_motion=hareket,
                          service_workers="block")   # SW isteği page.route'u atlar
    hatalar = []
    s.on("pageerror", lambda e, H=hatalar: H.append(str(e)))
    s.route("**/api/map/news*", lambda r: r.fulfill(status=200, content_type="application/json",
                                                   body=json.dumps(cevap)))
    s.goto(URL + "/ui/", wait_until="load")
    s.wait_for_timeout(6000)
    atla = s.get_by_text("Şimdilik atla")
    if atla.count() and atla.first.is_visible():
        atla.first.click()
        s.wait_for_timeout(1000)
    s.evaluate("switchTab('map')")
    s.wait_for_timeout(2500)
    s.evaluate("""() => { const g = document.getElementById('map-gundem');
                          if (g && !g.classList.contains('acik')) mapGundemAc(); }""")
    # 11-13 Gözlemevi düzeni: GÜNDEM, YAKINDA · DÜNYA · GÜNDEM kartının 3. sekmesi — kullanıcının yolu sekmeye dokunmak
    sekme = s.locator('#map-gundem .mh-yk-sekme[data-yk="gundem"]')
    if sekme.count():
        sekme.click()
    # Telefonda alt sayfa ilk 2 satırı gösterir; kullanıcı tutamakla genişletir (3. satır ölçülecek)
    tutamak = s.locator('#map-gundem .mh-tutamak')
    if tutamak.count() and tutamak.is_visible():
        tutamak.click()
    s.evaluate("updateNewsCard()")
    s.wait_for_timeout(1200)
    return s, hatalar


with sync_playwright() as p:
    tarayici = p.chromium.launch()
    for gen, yuk in [(390, 844), (1280, 800)]:
        s, hatalar = sayfa_ac(tarayici, gen, yuk, KUMELI)
        o = s.evaluate(OLC)
        kontrol(f"{gen}: 3 satır", len(o) == 3, str(len(o)))
        if len(o) == 3:
            kontrol(f"{gen}: 3 kaynaklı olayda +2", o[0]["rozet"] == "+2", str(o[0]["rozet"]))
            kontrol(f"{gen}: rozet ipucu öbür kaynaklar",
                    o[0]["ipucu"] == "2 kaynak daha: Haber B · Haber Cetvel Uzun Kaynak Adı", str(o[0]["ipucu"]))
            kontrol(f"{gen}: tek kaynakta rozet yok", o[1]["rozet"] is None and o[1]["kaynak"] == "Hava D")
            kontrol(f"{gen}: uzun kaynak adında rozet görünür", o[2]["rozet"] == "+1" and o[2]["rozetGorunur"])
            kontrol(f"{gen}: kaynak satır içinde", all(x["satirIcinde"] for x in o))
            kontrol(f"{gen}: satır kart içinde", all(x["kartIcinde"] for x in o))
        kontrol(f"{gen}: sayaç 3", s.inner_text("#map-gundem-sayi").strip() == "3")
        if EKRAN:
            EKRAN.mkdir(parents=True, exist_ok=True)
            s.locator("#map-gundem").screenshot(path=str(EKRAN / f"gundem-{gen}.png"))
            s.screenshot(path=str(EKRAN / f"harita-{gen}.png"))
        kontrol(f"{gen}: JS istisnası 0 (normal/animasyonlu mod)", not hatalar, "; ".join(hatalar[:2]))
        s.close()

    # Kümeleme kapalı cevabı (eski biçim) aynen çizilir.
    s, hatalar = sayfa_ac(tarayici, 1280, 800, HAM)
    o = s.evaluate(OLC)
    kontrol("ham cevap: 2 satır, rozet yok", len(o) == 2 and all(x["rozet"] is None for x in o))
    kontrol("ham cevap: kaynak etiketi", len(o) == 2 and o[0]["kaynak"] == "Haber A")
    kontrol("ham cevap: JS istisnası 0", not hatalar, "; ".join(hatalar[:2]))
    s.close()
    tarayici.close()

kalan = sum(1 for _, ok in sonuc if not ok)
print(f"\ngeçti {len(sonuc) - kalan} · kaldı {kalan}")
sys.exit(1 if kalan else 0)
