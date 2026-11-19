#!/usr/bin/env python3
"""Hizala şerit b (11-14, kullanıcı seçimi madde 10-14 "kişiseldeki gibi"): Yedek · Galeri · Plan · Harita · Dosya
ekranlarının üst kısmı kişisel Yuki'deki gibi mi — ve sahte düğme yok mu.

    python3 frontend/tests/test_kisisel_baslik_b.py [BASE]               # varsayılan http://127.0.0.1:8161 (YUKI_DEMO=1)
    python3 frontend/tests/test_kisisel_baslik_b.py [BASE] --mutasyon    # her kapıyı bir kez bilerek kır, yakalanmalı

Ölçülen (390 ve 1280, normal/animasyonlu mod, reduced-motion verilmez):
  Galeri  — başlık düz satır (ortak .sekme-baslik yok), telefonda klasör simgeli düğme, "kök klasör ekle" düğmesi GERÇEK (11-15 kararı: tık seçiciyi açar)
            (oss'ta kök ekleme ucu yok: galeri_api K6 — düğme koyulsaydı sahte olurdu)
  Plan    — "Plan" adı üstte, GÖZLEMEVİ etiketi altta, serif italik
  Harita  — yer hücresinde yalnız yer adı (HARİTA etiketi görünmez), yatay, serif italik 19 px
  Dosya   — altın büyük harf "DOSYALAR", mühür adın SOLUNDA
  Yedek   — üst çubukta serif "Drive" (52 px'ten), eski köşe başlığı görünmez, kadran + Akış + Klasörler;
            1280'de çok sütun, 390'da tek sütun; dolu hâlde (Google bağlı, son tur var) Akış 2 olay + anahtar görünür
  Hepsi   — JS istisnası 0, yatay taşma yok
"""
import json
import re
import sys
from datetime import datetime, timedelta, timezone

from playwright.sync_api import sync_playwright

ARGS = [a for a in sys.argv[1:] if not a.startswith("--")]
BASE = ARGS[0] if ARGS else "http://127.0.0.1:8161"
MUTASYON = "--mutasyon" in sys.argv
if re.search(r":(8000|8001)\b", BASE):
    sys.exit("canlı/geliştirme portu reddedildi — YUKI_DEMO=1 ikinci örneğe karşı koş")

# (ad, dosya sonu, doğru metin, kırık metin, bozması beklenen kontrol öneki)
MUTASYONLAR = [
    ("galeri-sahte-kok-ekle", "/js/galeri.js", "$('gl-ekle').addEventListener('click', function () { cekmece(null, false); seciciAc(null); });",
     "", "galeri"),
    ("galeri-tel-simge", "/galeri.html", '<svg class="gl-ik"><use href="#i-klasor"/></svg>\n    <span class="gl-klasor-dugme-ad"',
     '<span class="gl-klasor-dugme-ad"', "galeri"),
    ("plan-etiket-ustte", "/css/plan-gozlemevi.css", "display: flex; flex-direction: column; justify-content: center; flex-shrink: 0;",
     "display: flex; flex-direction: column-reverse; justify-content: center; flex-shrink: 0;", "plan"),
    ("harita-etiket", "/css/map-gozlemevi.css", "#map-serit .mh-yer > .sekme-baslik__etiket { display: none; }",
     "#map-serit .mh-yer > .sekme-baslik__etiket { }", "harita"),
    ("dosya-muhur-sagda", "/dosya.html", '<svg class="dy-sigil" aria-hidden="true"><use href="#i-sigil"/></svg><h1>DOSYALAR</h1>',
     '<h1>DOSYALAR</h1><svg class="dy-sigil" aria-hidden="true"><use href="#i-sigil"/></svg>', "dosya"),
    ("yedek-eski-kose", "/css/yedek.css", ".yedek-sekme-baslik { display: none; }", ".yedek-sekme-baslik { }", "yedek"),
    ("yedek-tel-izgara", "/css/yedek.css", "  #tab-yedek .yb-izgara { display: block; }", "  #tab-yedek .yb-izgara { }", "yedek"),
    ("yedek-kadran-yok", "/js/yedekleme.js", "var sol = _kadran(h) + _serit(h)", "var sol = _serit(h)", "yedek"),
    ("yedek-anahtar-0px", "/css/yedek.css", ".yb-et:first-child + :not(.yb-anahtar) { inline-size: auto; }",
     ".yb-et:first-child + * { inline-size: auto; }", "yedek-dolu"),
]

HAZIR = """try{sessionStorage.setItem('yukiAcilis_v1','1');localStorage.setItem('yuki-ilk-kurulum_v1','test');
localStorage.setItem('yukiTema_v1','koyu');localStorage.setItem('yukiViewMode_v1','chat');}catch(e){}"""
KATMAN = """() => { for (const id of ['auth-screen','boot-screen','yuki-opening']) { const e = document.getElementById(id);
  if (e) { e.classList.add('hidden'); e.style.display = 'none'; } } }"""
GORUNUR = """e => { if (!e) return false; const r = e.getBoundingClientRect(), c = getComputedStyle(e);
  return r.width > 0 && r.height > 0 && c.visibility !== 'hidden' && c.display !== 'none' && +c.opacity > 0; }"""


def _z(**k):
    return (datetime.now(timezone.utc) - timedelta(**k)).isoformat()


def dolu_durum():
    kay = lambda ad, i: {"id": i, "ad": ad, "yol": f"/home/kullanici/{ad}", "dosya": 12, "bayt": 4_100_000, "kaynakta_yok": 0,
                         "sistem": i == "yuki", "yol_var": True, "son_yedek": _z(hours=9), "tur": {"durum": "tamam"}, "canli": None}
    return {"acik": True, "yuki_verisi": True, "zamanlama": "03:30", "zamanlama_bilgi": {"kurulu": True, "sonraki": _z(hours=-6)},
            "tavanlar": {"tek_dosya_mb": 200, "tur_mb": 2048}, "kaynaklar": [kay("Yuki verisi", "yuki"), kay("Belgeler", "k1")],
            "tum_kaynaklar": [], "calisiyor": False, "canli": None,
            "son_tur": {"tetik": "elle", "bitti": _z(hours=9), "saniye": 12.0, "yuklenen": 3, "guncellenen": 1, "atlanan": 9,
                        "bayt": 2_000_000, "kaynakta_yok": 0, "buyuk_atlandi": [], "hata": None, "tam": True, "kaynaklar": []},
            "son_yedek": _z(hours=9),
            "baglanti": {"token": True, "kimlik": True, "durum": "bagli", "sebep": None, "son_deneme": {"ok": True, "zaman": _z(minutes=3)}}}


def sayfa(b, w, mut=None, dolu=False):
    ctx = b.new_context(viewport={"width": w, "height": 844 if w < 600 else 800}, service_workers="block")
    ctx.add_init_script(HAZIR)
    if mut:
        _, son, dogru, kirik, _ = mut

        def degistir(route):
            r = route.fetch()
            metin = r.text()
            assert dogru in metin, f"mutasyon metni bulunamadı: {mut[0]}"
            route.fulfill(response=r, body=metin.replace(dogru, kirik, 1))
        ctx.route(re.compile(re.escape(son) + r"(\?.*)?$"), degistir)
    if dolu:
        ctx.route("**/api/yedekleme/durum", lambda r: r.fulfill(status=200, content_type="application/json", body=json.dumps(dolu_durum())))
        ctx.route("**/api/yedekleme/drive-kullanim", lambda r: r.fulfill(status=200, content_type="application/json",
                                                                          body=json.dumps({"limit": 15e9, "kullanilan": 6e9})))
    s = ctx.new_page()
    hatalar = []
    s.on("pageerror", lambda e: hatalar.append(str(e)[:160]))
    s.goto(BASE + "/", wait_until="domcontentloaded")
    s.wait_for_timeout(2500)
    s.evaluate(KATMAN)
    s.wait_for_timeout(500)
    return s, hatalar


def ac(s, tab, iframe=None, bekle=2800):
    s.evaluate(f"switchTab('{tab}')")
    s.wait_for_timeout(bekle)
    if not iframe:
        return s
    fr = s.frame_locator(iframe)
    s.wait_for_function(f"() => {{ const f = document.querySelector('{iframe}'); return f && f.contentDocument && f.contentDocument.readyState === 'complete'; }}")
    s.wait_for_timeout(1500)
    return s.query_selector(iframe).content_frame()


def tasma(f):
    return f.evaluate("() => document.documentElement.scrollWidth - document.documentElement.clientWidth")


def olc(b, mut=None):
    r = {}
    for w in (1280, 390):
        e = f"{w}/"
        # ── Galeri
        s, h = sayfa(b, w, mut)
        f = ac(s, "galeri", "#galeri-iframe")
        g = f.evaluate("""() => { const v = """ + GORUNUR + """;
          const ad = document.getElementById(innerWidth > 700 ? 'gl-yol-ad' : 'gl-tel-ad');
          const tel = document.getElementById('gl-ray-ac');
          return { ortak: document.querySelectorAll('.sekme-baslik').length, ad: v(ad), adTxt: ad && ad.textContent,
                   stil: ad && getComputedStyle(ad).fontStyle, ekle: !!document.getElementById('gl-ekle'),
                   telSimge: !!(tel && tel.querySelector(':scope > svg.gl-ik use[href="#i-klasor"]')) }; }""")
        r[e + "galeri düz başlık (ortak sınıf yok, ad görünür, italik değil)"] = (g["ortak"] == 0 and g["ad"] and g["stil"] == "normal", g)
        if w < 600:
            r[e + "galeri telefon düğmesinde klasör simgesi"] = (g["telSimge"], g["telSimge"])
        r[e + "galeri taşma yok"] = (tasma(f) <= 0, tasma(f))
        if g["ekle"]:
            f.evaluate("document.getElementById('gl-ekle').click()")
            s.wait_for_timeout(1500)
        secici = f.evaluate("(() => { const m = document.getElementById('gl-secici'); return !!(m && !m.hidden); })()")
        r[e + "galeri 'kök klasör ekle' düğmesi gerçek (tık seçiciyi açar)"] = (g["ekle"] and secici, (g["ekle"], secici))
        r[e + "galeri JS 0"] = (not h, h[:2])
        s.context.close()
        # ── Plan
        s, h = sayfa(b, w, mut)
        f = ac(s, "planner", "#planner-iframe")
        p = f.evaluate("""() => { const m = document.querySelector('#tab-bar .marka'); if (!m) return null;
          const a = m.querySelector('span[data-i18n="plan.marka"]'), k = m.querySelector('small');
          const ra = a.getBoundingClientRect(), rk = k.getBoundingClientRect();
          return { ortak: m.classList.contains('sekme-baslik'), adUst: ra.bottom <= rk.top + 2, stil: getComputedStyle(m).fontStyle,
                   adTxt: a.textContent.trim(), etTxt: k.textContent.trim() }; }""")
        r[e + "plan: ad üstte, GÖZLEMEVİ altta, serif italik"] = (bool(p) and not p["ortak"] and p["adUst"] and p["stil"] == "italic", p)
        r[e + "plan taşma yok"] = (tasma(f) <= 0, tasma(f))
        r[e + "plan JS 0"] = (not h, h[:2])
        s.context.close()
        # ── Harita
        s, h = sayfa(b, w, mut)
        ac(s, "map", None, 4500)
        m = s.evaluate("""() => { const v = """ + GORUNUR + """; const y = document.querySelector('#map-serit .mh-yer');
          const c = document.getElementById('map-city'), cs = getComputedStyle(c);
          return { etiket: v(y.querySelector('.sekme-baslik__etiket')), yon: getComputedStyle(y).flexDirection,
                   boy: cs.fontSize, stil: cs.fontStyle, sehir: v(c) }; }""")
        r[e + "harita: yalnız yer adı, yatay, italik 19px"] = (not m["etiket"] and m["yon"] == "row" and m["boy"] == "19px"
                                                         and m["stil"] == "italic" and m["sehir"], m)
        r[e + "harita JS 0"] = (not h, h[:2])
        s.context.close()
        # ── Dosya
        s, h = sayfa(b, w, mut)
        f = ac(s, "dosya", "#dosya-iframe")
        d = f.evaluate("""() => { const v = """ + GORUNUR + """; const h1 = document.querySelector('.dy-marka h1'),
          sg = document.querySelector('.dy-marka .dy-sigil');
          return { txt: h1 && h1.textContent.trim(), ortak: document.querySelectorAll('.sekme-baslik').length,
                   h1: v(h1), sg: v(sg), solda: !!(sg && h1) && sg.compareDocumentPosition(h1) === Node.DOCUMENT_POSITION_FOLLOWING
                     && (!v(sg) || !v(h1) || sg.getBoundingClientRect().right <= h1.getBoundingClientRect().left) }; }""")
        r[e + "dosya: DOSYALAR, ortak sınıf yok, mühür solda"] = (d["txt"] == "DOSYALAR" and d["ortak"] == 0 and d["solda"], d)
        if w >= 600:
            r[e + "dosya: ad ve mühür görünür"] = (d["h1"] and d["sg"], d)
        r[e + "dosya taşma yok"] = (tasma(f) <= 0, tasma(f))
        r[e + "dosya JS 0"] = (not h, h[:2])
        s.context.close()
        # ── Yedek (demo: Google bağlı değil)
        s, h = sayfa(b, w, mut)
        ac(s, "yedek")
        y = s.evaluate("""() => { const v = """ + GORUNUR + """; const k = document.getElementById('tab-yedek');
          const ad = k.querySelector('.yb-cubuk-ad'), yan = k.querySelector('.yb-yan'), ana = k.querySelector('.yb-ana'),
                kl = k.querySelector('.yb-klasorler'), kr = k.getBoundingClientRect();
          const gr = x => x ? x.getBoundingClientRect() : null;
          return { ad: v(ad) ? ad.textContent.trim() : null, adSol: ad ? Math.round(gr(ad).left) : null,
                   eskiKose: v(k.querySelector('.yedek-sekme-baslik')), kadran: v(k.querySelector('.yb-kadran svg')),
                   yanW: Math.round(gr(yan).width), kabW: Math.round(kr.width), anaSol: Math.round(gr(ana).left - gr(yan).left),
                   klasor: v(kl), tasma: Math.max(...[...k.querySelectorAll('*')].map(x => Math.round(x.getBoundingClientRect().right - kr.right))) }; }""")
        r[e + "yedek: üst çubukta 'Drive', eski köşe başlığı yok"] = (y["ad"] == "Drive" and not y["eskiKose"], y)
        if w >= 600:
            r[e + "yedek: 'Drive' 52 px'ten"] = (y["adSol"] == 52, y["adSol"])   # 11-14 çerçeve kalktı (kişisel de 52)
            r[e + "yedek: çok sütun (akış sol sütunun sağında)"] = (y["anaSol"] >= 300 and y["yanW"] < y["kabW"] / 2, y)
        else:
            r[e + "yedek: tek sütun"] = (y["yanW"] >= y["kabW"] - 2 and y["anaSol"] == 0, y)
        r[e + "yedek: kadran + klasörler görünür"] = (y["kadran"] and y["klasor"], y)
        r[e + "yedek taşma yok"] = (y["tasma"] <= 1, y["tasma"])
        r[e + "yedek JS 0"] = (not h, h[:2])
        s.context.close()
        # ── Yedek dolu hâl (sahte /durum: Google bağlı, saat kurulu, son tur var)
        s, h = sayfa(b, w, mut, dolu=True)
        ac(s, "yedek")
        y = s.evaluate("""() => { const k = document.getElementById('tab-yedek'), a = k.querySelector('.yb-anahtar');
          return { olay: k.querySelectorAll('.yb-akis .yb-olay').length, gelecek: !!k.querySelector('.yb-olay.gelecek'),
                   anahtarW: a ? Math.round(a.getBoundingClientRect().width) : 0, yay: (k.querySelector('.yb-kd-yay') || {}).getAttribute
                     ? k.querySelector('.yb-kd-yay').getAttribute('stroke-dasharray') : null }; }""")
        r[e + "yedek-dolu: Akış'ta planlı + son tur, anahtar 48 px"] = (y["olay"] == 2 and y["gelecek"] and y["anahtarW"] == 48, y)
        r[e + "yedek-dolu: kadran yayı dolu (>0)"] = (bool(y["yay"]) and float(y["yay"].split()[0]) > 0, y["yay"])
        r[e + "yedek-dolu JS 0"] = (not h, h[:2])
        s.context.close()
    return r


def main():
    with sync_playwright() as p:
        b = p.chromium.launch()
        if not MUTASYON:
            r = olc(b)
            kal = [k for k, (ok, _) in r.items() if not ok]
            for k, (ok, v) in r.items():
                print(("✓ " if ok else "✗ ") + k + ("" if ok else f"  {v}"))
            print(f"\ngeçti {len(r) - len(kal)} · kaldı {len(kal)}")
            b.close()
            sys.exit(1 if kal else 0)
        yakalanan = 0
        sec = [a.split("=", 1)[1] for a in sys.argv if a.startswith("--yalniz=")]
        secili = [m for m in MUTASYONLAR if not sec or m[0] in sec[0].split(",")]
        for mut in secili:
            r = olc(b, mut)
            kirik = [k for k, (ok, _) in r.items() if not ok]
            hedefte = [k for k in kirik if k.split("/", 1)[1].startswith(mut[4])]
            ok = bool(hedefte)
            yakalanan += ok
            print(("✓ yakalandı " if ok else "✗ KAÇTI ") + mut[0] + (f"  ← {hedefte[0]}" if ok else f"  (kırılan: {kirik[:2]})"))
        print(f"\nmutasyon {yakalanan}/{len(secili)}")
        b.close()
        sys.exit(0 if yakalanan == len(secili) else 1)


if __name__ == "__main__":
    main()
