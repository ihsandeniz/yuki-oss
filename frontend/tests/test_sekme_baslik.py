"""Sekme başlıkları TEK TARZ (11-13) — 8 sekme × 390/1280, normal (animasyonlu) mod.

    python3 frontend/tests/test_sekme_baslik.py [BASE]              # varsayılan http://127.0.0.1:8031
    python3 frontend/tests/test_sekme_baslik.py [BASE] --mutasyon   # her kapıyı bir kez kır, yakalandığını gör

Ortak sınıf `.sekme-baslik` (css/baslik-gozlemevi.css): üst etiket Martian Mono + ad Fraunces italik.
Ölçülen (hesaplanan stil + kutu, sayfa koordinatında; iframe sekmelerinde çerçeve kayması eklenir):
  · ad: aile Fraunces, 22px, 500, italik — 8 sekmede eşit
  · etiket: aile Martian Mono, 10px, 500, büyük harf — 8 sekmede eşit, adın ÜSTÜNDE
  · sol kenar 52 px (±1), etiket üstü 5 px (±2) (11-14 çerçeve kalktı; önce 64/17) — Harita hariç: yer şeridi camının içinde (☰ engeli,
    şef onayı 11-13), orada yalnız aile/boy/ağırlık eşitliği
  · kesilme yok (scrollWidth ≤ clientWidth) · başlık kutusu üst çubuktaki düğme/giriş/rozetlerle KESİŞMEZ
  · açık ve koyu temada ad ve etiket zeminine karşı okunur (WCAG oranı ≥ 4.5)
Mutasyon diske dokunmaz: Playwright ilgili dosyayı değişmiş metinle sunar. Çalışan bir oss arka ucu ister.
"""
import re
import sys
from playwright.sync_api import sync_playwright

ARGS = [a for a in sys.argv[1:] if not a.startswith("--")]
BASE = ARGS[0] if ARGS else "http://127.0.0.1:8031"
MUTASYON = "--mutasyon" in sys.argv

# 11-14 (hizala şerit b, kullanıcı seçimi): Plan · Harita · Yedek · Galeri · Dosya kişisel Yuki'deki başlığa döndü —
# "tek tarz" ölçüsü bu beş sekmede geri alındı; onların başlık ölçüsü test_kisisel_baslik_b.py'de.
SEKMELER = ["chat", "hq", "ajan"]
# sekme → (iframe seçicisi | None, kök seçici)
KAP = {
    "chat": (None, "#header"), "planner": ("#planner-iframe", "body"), "hq": (None, "#tab-hq"),
    "map": (None, "#tab-map"), "ajan": (None, "#tab-ajan"), "yedek": (None, "#tab-yedek"),
    "galeri": ("#galeri-iframe", "body"), "dosya": ("#dosya-iframe", "body"),
}
SOL, UST = 52, 5   # 11-14 tam hizala: çerçeve kenardan kenara, ☰ (8,8) — önce 64, 17 (12 px içeride kart)
ISTISNA_YER = {"map"}
# 11-14: Sohbet kişisel düzende (● Yuki hazır üst çubuğu, tek tarz başlık bu ekranda geri alındı) —
# görünümünü frontend/tests/test_sohbet_ust_kisisel.py ölçer.
SEKMELER = [s for s in SEKMELER if s != "chat"]

# (ad, dosya sonu, doğru metin, kırık metin) — kırık metin eski/yanlış durumu canlandırır
MUTASYONLAR = [
    # anahtarsız sunucuda (HQ Anahtar odasıyla açılır, şerit kayar) ölçülür — :8031 YUKI_DEMO=1 gibi
    ("hq-serit-clip", "/css/hq.css", "clip-path: inset(0 0 0 calc(var(--hq-serit-sol, 60px) - 4px));", "clip-path: none;"),
    ("ortak-boy", "/css/baslik-gozlemevi.css", "--sb-ad-boy: 22px;", "--sb-ad-boy: 19px;"),
    ("sabit-renk", "/css/baslik-gozlemevi.css", "color: var(--sb-ad-renk, var(--ink-1, #e7e5ee));", "color: #e7e5ee;"),
    ("ajan-sinif", "/js/ajan-view.js", 'aj-baslik sekme-baslik__ad', 'aj-baslik'),
    ("hq-serit-payi", "/css/hq.css", "--hq-serit-sol: calc(var(--hq-sb-sol) + var(--hq-bas-gen) + 8px);", "--hq-serit-sol: 60px;"),
    # 11-15: HQ başlığı çerçevesiz 52/5 — kart payı düşülmezse 64'e geri kayar
    ("hq-baslik-cerceve", "/css/hq.css", "--hq-sb-sol: calc(var(--sb-sol, 64px) - 12px);", "--hq-sb-sol: var(--sb-sol, 64px);"),
]
# dosya-muhur-solda: mührü SOLA geri koymak için ikinci bir değişiklik gerekir → özel işlenir
MUHUR_SOL = ('<div class="dy-marka"><div class="sekme-baslik">',
             '<div class="dy-marka"><svg class="dy-sigil" aria-hidden="true"><use href="#i-sigil"/></svg><div class="sekme-baslik">')

OLC_JS = r"""([kok, ofx, ofy]) => {
  const R = e => { const b = e.getBoundingClientRect(); return {x: b.left + ofx, y: b.top + ofy, w: b.width, h: b.height}; };
  /* Tıklanabilir kutu: öğenin gerçekten isabet aldığı noktaların sınırı (elementsFromPoint — z sırasından
     bağımsız, clip-path ve pointer-events'e uyar, maskeye uymaz). Kaydırılıp maskeyle GÖRÜNMEZ olmuş ama
     başlığın altında hâlâ TIKLANAN düğme engel sayılır (HQ 390, Anahtar odası, 11-13); kesilmiş kısım sayılmaz. */
  const TIK = e => { const b = e.getBoundingClientRect(), N = 12, M = 4, xs = [], ys = [];
    for (let i = 0; i < N; i++) for (let j = 0; j < M; j++) {
      const x = b.left + (i + 0.5) * b.width / N, y = b.top + (j + 0.5) * b.height / M;
      if (x < 0 || y < 0 || x >= innerWidth || y >= innerHeight) continue;
      if (document.elementsFromPoint(x, y).some(el => el === e || e.contains(el))) { xs.push(x); ys.push(y); } }
    if (!xs.length) return {x: 0, y: 0, w: 0, h: 0};
    const dx = b.width / N / 2, dy = b.height / M / 2, x0 = Math.min(...xs) - dx, y0 = Math.min(...ys) - dy;
    return {x: x0 + ofx, y: y0 + ofy, w: Math.max(...xs) + dx - x0, h: Math.max(...ys) + dy - y0}; };
  const gor = e => { const b = e.getBoundingClientRect(), c = getComputedStyle(e);
    return b.width > 0 && b.height > 0 && c.visibility !== 'hidden' && c.display !== 'none' && b.bottom > 0 && b.top < innerHeight; };
  const k = document.querySelector(kok);
  if (!k) return {hata: 'kök yok: ' + kok};
  const adlar = [...k.querySelectorAll('.sekme-baslik .sekme-baslik__ad')].filter(gor);
  if (adlar.length !== 1) return {hata: 'görünür ad sayısı ' + adlar.length};
  const ad = adlar[0], bas = ad.closest('.sekme-baslik');
  const et = bas.querySelector('.sekme-baslik__etiket');
  if (!et || !gor(et)) return {hata: 'etiket yok/görünmez'};
  // oklch/rgba → rgb (tuval çevirir; oran hesabı Python'da)
  const tuv = document.createElement('canvas').getContext('2d');
  const rgb = c => { tuv.clearRect(0, 0, 1, 1); tuv.fillStyle = '#000'; tuv.fillStyle = c; tuv.fillRect(0, 0, 1, 1);
    const d = tuv.getImageData(0, 0, 1, 1).data; return `rgb(${d[0]}, ${d[1]}, ${d[2]})`; };
  const st = e => { const c = getComputedStyle(e); return {aile: c.fontFamily.split(',')[0].replace(/["']/g, '').trim(),
    boy: c.fontSize, agirlik: c.fontWeight, stil: c.fontStyle, buyuk: c.textTransform, renk: rgb(c.color)}; };
  // Zemin: rengi saydam olmayan ilk ata (yoksa gövde)
  const zemin = e => { for (let a = e; a; a = a.parentElement) { const c = getComputedStyle(a).backgroundColor;
      const m = c.match(/[\d.]+/g); if (m && (m.length < 4 || +m[3] > 0.5)) return rgb(c); }
    return rgb(getComputedStyle(document.documentElement).backgroundColor); };
  // Engel: başlıkla aynı bölgede tıklanır/duyurulur öğeler (başlığın atası ya da çocuğu sayılmaz)
  const engel = [...document.querySelectorAll('button, a[href], input:not([type=hidden]), select, label, [role=status], .hud-mem-badge, .dy-sigil')]
    .filter(e => gor(e) && !e.contains(bas) && !bas.contains(e))
    .map(e => ({ad: (e.id || e.className || e.tagName).toString().slice(0, 40), ...TIK(e)}))
    .filter(g => g.w > 0);
  return {ad: {...R(ad), ...st(ad), tasma: ad.scrollWidth - ad.clientWidth, zemin: zemin(ad)},
          et: {...R(et), ...st(et), tasma: et.scrollWidth - et.clientWidth, zemin: zemin(et)}, engel};
}"""


def parlak(c):
    v = [float(x) for x in re.findall(r"[\d.]+", c)[:3]]
    v = [x / 255 for x in v]
    v = [x / 12.92 if x <= 0.03928 else ((x + 0.055) / 1.055) ** 2.4 for x in v]
    return 0.2126 * v[0] + 0.7152 * v[1] + 0.0722 * v[2]


def oran(a, b):
    la, lb = sorted([parlak(a), parlak(b)], reverse=True)
    return (la + 0.05) / (lb + 0.05)


def kesisim(a, b):
    w = min(a["x"] + a["w"], b["x"] + b["w"]) - max(a["x"], b["x"])
    h = min(a["y"] + a["h"], b["y"] + b["h"]) - max(a["y"], b["y"])
    return w > 0.5 and h > 0.5


def sayfa(b, w, tema, mut=None):
    # service_workers=block: sw iframe isteklerini kendi önbelleğinden sunarsa mutasyon rotası atlanır (ölçüldü)
    s = b.new_context(viewport={"width": w, "height": 844 if w < 500 else 800}, service_workers="block").new_page()
    hata = []
    s.on("pageerror", lambda e: hata.append(str(e)))
    s.route("**://127.0.0.1:8000/**", lambda r: r.abort())
    if tema == "acik":
        s.add_init_script("try{localStorage.setItem('yukiTema_v1','acik')}catch(e){}")
    if mut:
        ad, son, dogru, kirik = mut

        def degistir(route):
            yanit = route.fetch()
            metin = yanit.text()
            assert dogru in metin, f"mutasyon metni dosyada yok: {dogru}"
            metin = metin.replace(dogru, kirik)
            if ad == "dosya-muhur-solda":
                metin = metin.replace(*MUHUR_SOL)
            route.fulfill(response=yanit, body=metin)
        s.route(re.compile(re.escape(son) + r"(\?.*)?$"), degistir)
    return s, hata


def kabuk_ac(s):
    s.goto(BASE + "/ui/")
    s.wait_for_timeout(6000)
    a = s.get_by_text("Şimdilik atla")
    if a.count() and a.first.is_visible():
        a.first.click()
        s.wait_for_timeout(1000)


def olc_sekme(s, sekme):
    s.evaluate(f"switchTab('{sekme}')")
    s.wait_for_timeout(3000)
    cer, kok = KAP[sekme]
    if cer:
        r = s.evaluate(f"(()=>{{const b=document.querySelector('{cer}').getBoundingClientRect();return [b.left,b.top]}})()")
        fr = s.query_selector(cer).content_frame()
        sonuc = fr.evaluate(OLC_JS, [kok, r[0], r[1]])
        # iframe dışındaki kabuk düğmesi (☰) de engel sayılır
        if "engel" in sonuc:
            sonuc["engel"].append(s.evaluate("(()=>{const b=document.getElementById('nav-ac').getBoundingClientRect();"
                                             "return {ad:'nav-ac',x:b.left,y:b.top,w:b.width,h:b.height}})()"))
        return sonuc
    return s.evaluate(OLC_JS, [kok, 0, 0])


def olc(b, mut=None):
    """{kapı adı: (geçti mi, ayrıntı)}"""
    r = {}
    for w in (1280, 390):
        s, h = sayfa(b, w, "koyu", mut)
        kabuk_ac(s)
        veri = {}
        for t in SEKMELER:
            veri[t] = olc_sekme(s, t)
        r[f"_js_{w}"] = (not h, h[:2])
        s.context.close()
        for t, d in veri.items():
            e = f"{w}/{t}"
            if "hata" in d:
                r[f"{e} başlık var"] = (False, d["hata"])
                continue
            a, et = d["ad"], d["et"]
            r[f"{e} ad Fraunces 22/500 italik"] = (
                (a["aile"], a["boy"], a["agirlik"], a["stil"]) == ("Fraunces", "22px", "500", "italic"),
                (a["aile"], a["boy"], a["agirlik"], a["stil"]))
            r[f"{e} etiket Martian Mono 10/500 büyük"] = (
                (et["aile"], et["boy"], et["agirlik"], et["buyuk"]) == ("Martian Mono", "10px", "500", "uppercase"),
                (et["aile"], et["boy"], et["agirlik"], et["buyuk"]))
            r[f"{e} etiket adın üstünde"] = (et["y"] + et["h"] <= a["y"] + 1.5 and abs(et["x"] - a["x"]) <= 1,
                                            (round(et["x"]), round(et["y"] + et["h"]), round(a["x"]), round(a["y"])))
            if t not in ISTISNA_YER:
                r[f"{e} sol {SOL}"] = (abs(a["x"] - SOL) <= 1, round(a["x"], 1))
                r[f"{e} üst {UST}"] = (abs(et["y"] - UST) <= 2, round(et["y"], 1))
            r[f"{e} kesilmiyor"] = (a["tasma"] <= 1 and et["tasma"] <= 1, (a["tasma"], et["tasma"]))
            kutu = {"x": min(a["x"], et["x"]), "y": et["y"],
                    "w": max(a["x"] + a["w"], et["x"] + et["w"]) - min(a["x"], et["x"]), "h": a["y"] + a["h"] - et["y"]}
            carp = [g["ad"] for g in d["engel"] if kesisim(kutu, g)]
            r[f"{e} çakışma yok"] = (not carp, carp[:3])
            r[f"{e} koyu okunur"] = (oran(a["renk"], a["zemin"]) >= 4.5 and oran(et["renk"], et["zemin"]) >= 4.5,
                                     (round(oran(a["renk"], a["zemin"]), 1), round(oran(et["renk"], et["zemin"]), 1)))
    # Açık tema — 1280'de okunurluk
    s, h = sayfa(b, 1280, "acik", mut)
    kabuk_ac(s)
    for t in SEKMELER:
        d = olc_sekme(s, t)
        if "hata" in d:
            r[f"acik/{t} başlık var"] = (False, d["hata"])
            continue
        a, et = d["ad"], d["et"]
        r[f"acik/{t} okunur"] = (oran(a["renk"], a["zemin"]) >= 4.5 and oran(et["renk"], et["zemin"]) >= 4.5,
                                 (round(oran(a["renk"], a["zemin"]), 1), round(oran(et["renk"], et["zemin"]), 1), a["zemin"]))
    r["_js_acik"] = (not h, h[:2])
    s.context.close()
    return r


def main():
    with sync_playwright() as p:
        b = p.chromium.launch()
        if not MUTASYON:
            r = olc(b)
            gecti = sum(1 for v in r.values() if v[0])
            for k, (ok, ay) in r.items():
                if not ok:
                    print(f"  ✗ {k}: {ay}")
            print(f"test_sekme_baslik: {gecti} geçti · {len(r) - gecti} kaldı")
            b.close()
            sys.exit(0 if gecti == len(r) else 1)
        yakalanan = 0
        sec = [a.split("=", 1)[1] for a in sys.argv if a.startswith("--yalniz=")]
        secili = [m for m in MUTASYONLAR if not sec or m[0] in sec]
        for m in secili:
            r = olc(b, m)
            dusen = [k for k, v in r.items() if not v[0]]
            ok = bool(dusen)
            yakalanan += ok
            print(f"  {'✓' if ok else '✗'} mutasyon {m[0]}: {len(dusen)} kapı düştü {dusen[:3]}")
        print(f"mutasyon: {yakalanan}/{len(secili)} yakalandı")
        b.close()
        sys.exit(0 if yakalanan == len(secili) else 1)


if __name__ == "__main__":
    main()
