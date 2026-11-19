"""goz düzeltmeleri (birleşik arayüz, 11-13) — 7 ölçü, 390 + 1280, normal (animasyonlu) mod.

    python3 frontend/tests/test_goz_duzelt.py [BASE]              # varsayılan http://127.0.0.1:8031
    python3 frontend/tests/test_goz_duzelt.py [BASE] --mutasyon   # her kapıyı bir kez kır, yakalandığını gör

Mutasyon diske dokunmaz: Playwright ilgili dosyayı düzeltme ÖNCESİ metinle (tersine replace)
sunar. Çalışan bir oss arka ucu ister (demo, sahte veri).
"""
import re
import sys
from playwright.sync_api import sync_playwright

ARGS = [a for a in sys.argv[1:] if not a.startswith("--")]
BASE = ARGS[0] if ARGS else "http://127.0.0.1:8031"
MUTASYON = "--mutasyon" in sys.argv

# Her kapı: (ad, dosya sonu, düzeltilmiş metin, düzeltme öncesi metin)
MUTASYONLAR = [
    # 11-14: hq.css satırı '#tab-hq { --hq-serit-boy: 68px; --hq-bas-gen: …' oldu — kalıp yalnız değişkeni hedefler
    ("hq-serit-boy", "/css/hq.css", "#tab-hq { --hq-serit-boy: 68px;", "#tab-hq { --hq-serit-boy: 45px;"),
    # mon-meta-nowrap mutasyonu yok: telefonda .mon-meta flex (öğe = atomik kutu), nowrap orada
    # zaten gereksiz; kural 721 px üstündeki satır içi düzen için güvence, ölçüsü yukarıdaki kapı.
    ("mon-meta-ayrac", "/css/hq-monitor.css", ".mon-meta > .mon-nokta { display: none; }", ".mon-meta > .mon-nokta { }"),
    ("ws-durum-rozeti", "/css/kabuk.css", "content: attr(data-baglanti-metni)", "content: attr(data-durum-metni)"),
    ("ws-nokta-kutusu", "/css/kabuk.css", "clip-path: inset(50%); white-space: nowrap; padding: 0; border: 0;", "white-space: nowrap;"),
    ("galeri-tek-ay", "/js/galeri.js", "aylar.length < 2", "aylar.length < 1"),
    ("dosya-form-yazi", "/css/dosya.css", "padding-right: 26px; font-family: var(--t-govde-font)", "padding-right: 26px; font-family: var(--t-baslik-font)"),
    ("dosya-kurdele", "/css/dosya.css", "top: 6px; right: 78px", "top: -1px; right: 78px"),
    # 11-14 (hizala şerit b): Yedek kişisel "Drive" düzenine geçti — ölçü artık üst çubuktaki "Drive" adının sol kenarı
    ("yedek-sol-kenar", "/css/yedek.css", "padding: 0 24px 0 52px;", "padding: 0 24px 0 24px;"),
]


def sayfa(b, w, mut=None):
    s = b.new_context(viewport={"width": w, "height": 844 if w < 500 else 800}).new_page()
    hata = []
    s.on("pageerror", lambda e: hata.append(str(e)))
    s.route("**://127.0.0.1:8000/**", lambda r: r.abort())
    if mut:
        _, son, yeni, eski = mut

        def degistir(route):
            yanit = route.fetch()
            metin = yanit.text()
            assert yeni in metin, f"mutasyon metni dosyada yok: {yeni}"
            route.fulfill(response=yanit, body=metin.replace(yeni, eski))
        s.route(re.compile(re.escape(son) + r"(\?.*)?$"), degistir)
    return s, hata


def kabuk_ac(s, sekme):
    s.goto(BASE + "/ui/")
    s.wait_for_timeout(6000)
    a = s.get_by_text("Şimdilik atla")
    if a.count() and a.first.is_visible():
        a.first.click()
        s.wait_for_timeout(1000)
    s.evaluate(f"switchTab('{sekme}')")
    s.wait_for_timeout(3000)


def olc(b, mut=None):
    """{kapı adı: (geçti mi, ayrıntı)}"""
    r = {}
    # ── HQ 390: ✕ ve ☰ şeridin içinde; meta parçaları tek satır
    s, h = sayfa(b, 390, mut)
    kabuk_ac(s, "hq")
    o = s.evaluate("""(()=>{const R=id=>document.getElementById(id).getBoundingClientRect();
      const n=R('hq-subnav'),x=R('hq-katman-kapat'),m=R('nav-ac');
      return {serit:n.bottom,kapat:x.bottom,menu:m.bottom}})()""")
    r["hq-serit-boy"] = (o["kapat"] <= o["serit"] and o["menu"] <= o["serit"], o)
    s.evaluate("""(()=>{const p=document.getElementById('mon-power');p.textContent='22.3 W';
      document.getElementById('mon-uptime').textContent='3 sa 0 dk';document.getElementById('mon-cpu-temp').textContent='40.2°C'})()""")
    s.wait_for_timeout(200)
    # Etiket ile değer aynı satırda mı (üst kenar farkı) — değer alt satıra yetim düşmesin.
    og = s.evaluate("""[...document.querySelectorAll('.mon-meta-oge')].map(e=>{
      const a=e.firstElementChild.getBoundingClientRect(), z=e.lastElementChild.getBoundingClientRect();
      return Math.round(Math.abs(z.top-a.top))})""")
    r["mon-meta-nowrap"] = (len(og) == 3 and all(n <= 2 for n in og), og)
    nok = s.evaluate("[...document.querySelectorAll('.mon-meta > .mon-nokta')].map(e=>getComputedStyle(e).display)")
    r["mon-meta-ayrac"] = (bool(nok) and all(d == "none" for d in nok), nok)
    r["_js_hq390"] = (not h, h[:2])
    s.context.close()

    # ── Sohbet 390 (HALKA): nokta kutusu yok; kopukken rozet "BAĞLANTI YOK", başlık taşmaz
    s, h = sayfa(b, 390, mut)
    kabuk_ac(s, "chat")
    on = s.evaluate("(()=>{const r=document.getElementById('ws-pill').getBoundingClientRect();return [document.body.classList.contains('hud-ring-mode'),r.width,r.height]})()")
    r["ws-nokta-kutusu"] = (on[0] and on[1] <= 1 and on[2] <= 1, on)
    s.evaluate("_setWsPill(false)")
    s.wait_for_timeout(400)
    off = s.evaluate("""(()=>{const b=document.getElementById('state-badge');const hd=document.getElementById('header');
      return [getComputedStyle(b,'::after').content, hd.scrollWidth<=hd.clientWidth]})()""")
    r["ws-durum-rozeti"] = ("BAĞLANTI YOK" in off[0] and off[1], off)
    s.evaluate("_setWsPill(true)")
    r["_js_chat390"] = (not h, h[:2])
    s.context.close()

    # ── Galeri: tek ayda telefonda omurga yok, masaüstünde var
    for w, beklenen in ((366, "none"), (1256, "flex")):
        s, h = sayfa(b, w, mut)
        s.goto(BASE + "/ui/galeri.html")
        s.wait_for_timeout(4000)
        d = s.evaluate("[getComputedStyle(document.getElementById('gl-omurga')).display, document.querySelectorAll('#gl-om-liste .gl-om-ay').length]")
        anahtar = "galeri-tek-ay" if w < 500 else "_galeri-masaustu"
        r[anahtar] = (d[1] != 1 or d[0] == beklenen, d)
        r[f"_js_galeri{w}"] = (not h, h[:2])
        s.context.close()

    # ── Dosya 1280: form denetimi gövde yazısı; kurdele çerçevenin altında, çizgi kurdeleye değmez
    s, h = sayfa(b, 1256, mut)
    s.goto(BASE + "/ui/dosya.html")
    s.wait_for_timeout(3500)
    d = s.evaluate("""(()=>{const f=e=>getComputedStyle(e).fontFamily;
      const g=f(document.body), sel=f(document.getElementById('dy-sira')), kir=document.querySelector('.dy-kir');
      const on=document.getElementById('dy-onizleme').getBoundingClientRect(), k=document.querySelector('.dy-kurdele').getBoundingClientRect(),
            fo=document.querySelector('.dy-folyo').getBoundingClientRect();
      return {govde:g, secim:sel, kirinti:kir?f(kir):g, kurdeleUst:k.top-on.top, folyoSag:fo.right, kurdeleSol:k.left}})()""")
    r["dosya-form-yazi"] = (d["secim"] == d["govde"] and d["kirinti"] == d["govde"], d)
    r["dosya-kurdele"] = (d["kurdeleUst"] >= 6 and d["folyoSag"] < d["kurdeleSol"], d)
    r["_js_dosya"] = (not h, h[:2])
    s.context.close()

    # ── Yedek 1280 (11-14 kişisel "Drive" düzeni): "Drive" adı 64 px'ten (Plan/Dosya ile aynı), ☰'a binmez,
    #    gövde ızgarası kabın tamamını kullanır (kişiseldeki gibi kenardan kenara)
    s, h = sayfa(b, 1280, mut)
    kabuk_ac(s, "yedek")
    y = s.evaluate("""(()=>{const k=document.getElementById('tab-yedek');const t=k.querySelector('.oda-baslik').getBoundingClientRect();
      const g=k.querySelector('.oda-govde').firstElementChild.getBoundingClientRect(), kr=k.getBoundingClientRect();
      return [Math.round(t.left),Math.round(g.left-kr.left),Math.round(kr.right-g.right)]})()""")
    r["yedek-sol-kenar"] = (y[0] == 52 and y[1] == 0 and y[2] == 0, y)   # 11-14 tam hizala: çerçeve kalktı, ☰ (8,8) → 52 (önce 64)
    r["_js_yedek"] = (not h, h[:2])
    s.context.close()
    return r


def main():
    kalan = 0
    with sync_playwright() as p:
        b = p.chromium.launch()
        sonuc = olc(b)
        for ad, (ok, ayr) in sonuc.items():
            print("✓" if ok else "✗", ad, "" if ok else ayr)
            kalan += not ok
        gecti = sum(1 for v in sonuc.values() if v[0])
        print(f"geçti {gecti} · kaldı {kalan}")
        if MUTASYON:
            yakalanan = 0
            for m in MUTASYONLAR:
                rm = olc(b, m)
                ok = not rm[m[0]][0]
                yakalanan += ok
                print("  mutasyon", m[0], "YAKALANDI" if ok else "KAÇTI", rm[m[0]][1] if not ok else "")
            print(f"mutasyon {yakalanan}/{len(MUTASYONLAR)}")
            kalan += len(MUTASYONLAR) - yakalanan
        b.close()
    sys.exit(1 if kalan else 0)


if __name__ == "__main__":
    main()
