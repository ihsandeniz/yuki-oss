"""Tam hizala (11-14): kişisel Yuki ile kalan farklar + temiz kurulum denetiminin B1/B2/B3/B5/B7/B13'ü.

    python3 frontend/tests/test_tam_hizala.py [BASE]              # varsayılan http://127.0.0.1:8031
    python3 frontend/tests/test_tam_hizala.py [BASE] --mutasyon   # her kapıyı bir kez kır

BASE bir demo arka ucu olmalı (YUKI_DEMO=1 + sahte model): B2 gerçek bir cevap bekler.
Mutasyonlar dosyayı DİSKTE değiştirmez — Playwright yanıtı değiştirir. SW kapalı. Normal (animasyonlu) mod.
Ölçülenler:
  çerçeve   — içerik kenardan kenara (.kabuk-icerik = görünüm alanı), ☰ köşeden 8 px
  B1        — 390 HALKA'da ⋯ menüsünün her düğmesi basılabilir (elementFromPoint düğmenin kendisi)
  B2        — HALKA'da cevap "bir şey sor" satırında görünür (1280 + 390)
  duygu     — SAKİN yazısı 44 px (1280) / 28 px (390), Chakra Petch
  sahne     — RESİM sahnesi 1280'de 422 px (clamp 340, 33vw, 520)
  telefon   — 390 HALKA'da kayıtlı açık widget görünür, halka üst yarıda
  B3        — tanıtım oynarken sihirbaz görünmez
  B5        — 401 ham hatası sade cümleye döner
  B7        — Claude modundan dönüş varsayılanı ücretsiz model
"""
import re
import sys
from playwright.sync_api import sync_playwright

ARGS = [a for a in sys.argv[1:] if not a.startswith("--")]
BASE = ARGS[0] if ARGS else "http://127.0.0.1:8031"
MUTASYON = "--mutasyon" in sys.argv

MUTASYONLAR = [
    ("cerceve", "/css/kabuk.css", "  inset: 0;\n  border-radius: 0;\n  background: var(--yuzey-1);", "  inset: var(--b-5);\n  background: var(--yuzey-1);"),
    ("b1-katman", "/modes/hud-ring.css", "body.hud-ring-mode #input-container:has(#input-secondary-btns.acik) { position: relative; z-index: var(--z-acilir, 500); }", ""),
    ("b2-yazilmaz", "/modes/hud-ring.js", "if (m !== _sonCevap) { _sonCevap = m; _promptYaz(); }", "void 0;"),
    ("duygu-boyu", "/modes/sohbet-sahne.css", "font: 700 44px / 1 'Chakra Petch', var(--font);", "font: 700 21px / 1 var(--font);"),
    ("sahne-genislik", "/modes/sohbet-sahne.css", "flex-basis: clamp(340px, 33vw, 520px);", "flex-basis: 35%;"),
    ("telefon-widget", "/modes/hud-ring.js", "if (!acik.length) return;", "document.querySelectorAll('.hr-widget').forEach(w => w.classList.add('hr-w-mobil-gizli')); return;"),
    ("b3-sihirbaz", "/css/ilk-kurulum.css", "html:has(#yuki-opening:not(:empty)) .ilk-kurulum { visibility: hidden;", "html:has(#yuki-opening-YOK) .ilk-kurulum { visibility: hidden;"),
    ("b5-ham", "/js/ilk-kurulum.js", "return t('ik.hata.anahtar');", "return String(ham);"),
    ("serit-ok", "/css/hq.css", "    scroll-padding-inline-start: calc(var(--hq-serit-sol, 60px) + 28px);\n", ""),
    ("b7-ucretli", "/js/core.js", "const _DEFAULT_MODEL         = 'google/gemma-4-26b-a4b-it:free';", "const _DEFAULT_MODEL         = 'openai/gpt-4.1-mini';"),
]

HAZIR = """try{sessionStorage.setItem('yukiAcilis_v1','1');localStorage.setItem('yuki-ilk-kurulum_v1','test');
localStorage.setItem('yukiTema_v1','koyu');localStorage.setItem('yukiViewMode_v1','__KIP__');localStorage.setItem('yukiViewMode','__KIP__');
localStorage.setItem('yukiSohbetKip_v1','__SK__')}catch(e){}"""
MENU = """() => [...document.querySelectorAll('#input-secondary-btns .more-item')]
  .filter(b => b.offsetParent && b.getBoundingClientRect().width > 0).map(b => {
    const r = b.getBoundingClientRect(); const e = document.elementFromPoint(r.x + r.width/2, r.y + r.height/2);
    return !!(e && (b === e || b.contains(e))); })"""
GORUNUR = """(s) => { const e = document.querySelector(s); if (!e) return null; const r = e.getBoundingClientRect();
  let g = r.width > 0 && r.height > 0 && r.bottom > 0 && r.top < innerHeight;
  for (let x = e; x && g; x = x.parentElement) { const c = getComputedStyle(x);
    if (c.display === 'none' || c.visibility === 'hidden' || +c.opacity === 0) g = false; }
  return g; }"""


def sayfa(b, w, kip, sk, mut, hata):
    h = 844 if w < 600 else 800
    ctx = b.new_context(viewport={"width": w, "height": h}, service_workers="block")
    ctx.add_init_script(HAZIR.replace("__KIP__", kip).replace("__SK__", sk))
    s = ctx.new_page()
    s.on("pageerror", lambda e: hata.append(str(e)[:160]))
    if mut:
        _, son, yeni, eski = mut

        def degistir(route, *_):
            y = route.fetch(); m = y.text()
            assert yeni in m, f"mutasyon metni yok: {yeni!r}"
            route.fulfill(response=y, body=m.replace(yeni, eski))
        s.route(re.compile(re.escape(son) + r"(\?.*)?$"), degistir)
    s.goto(BASE + "/ui/", wait_until="domcontentloaded")
    s.wait_for_timeout(3000)
    # giriş/açılış katmanları kişiselin kendi testlerindeki gibi gizlenir (silinmez: core.js onlara yazar)
    s.evaluate("for (const id of ['auth-screen','yuki-opening']) { const e = document.getElementById(id); if (e) { e.classList.add('hidden'); e.style.display = 'none'; } }"
               "document.querySelectorAll('.ilk-kurulum').forEach(e => e.style.display = 'none'); document.documentElement.classList.remove('ilk-kurulum-acik');")
    s.evaluate(f"window.setViewMode && window.setViewMode('{kip}')")
    s.wait_for_timeout(2500)
    return s


def olc(b, mut=None):
    sonuc = []
    hata = []

    def k(ad, ok, kanit=""):
        sonuc.append((ad, bool(ok), kanit))
        print(("✓" if ok else "✗"), ad, "" if ok else f"— {kanit}", flush=True)

    for w in (1280, 390):
        # çerçeve + duygu + sahne (SOHBET / RESİM)
        s = sayfa(b, w, "chat", "resim", mut, hata)
        r = s.evaluate("""() => { const i = document.querySelector('.kabuk-icerik').getBoundingClientRect();
          const n = document.getElementById('nav-ac').getBoundingClientRect();
          const d = document.querySelector('.ss-duygu-ad'); const c = d ? getComputedStyle(d) : {};
          return {icerik: [i.x, i.y, i.width, i.height], nav: [n.x, n.y], fs: c.fontSize, ff: c.fontFamily || '',
                  sahne: document.getElementById('avatar-pane').getBoundingClientRect().width, W: innerWidth, H: innerHeight}; }""")
        k(f"{w} çerçeve kenardan kenara", r["icerik"] == [0, 0, r["W"], r["H"]], r["icerik"])
        k(f"{w} ☰ köşeden 8 px", r["nav"] == [8, 8], r["nav"])
        hedef = "44px" if w > 800 else "28px"
        k(f"{w} SAKİN {hedef} Chakra Petch", r["fs"] == hedef and "Chakra Petch" in r["ff"], (r["fs"], r["ff"][:30]))
        if w == 1280:
            k("1280 RESİM sahnesi 422 px", abs(r["sahne"] - 422.4) < 1.5, r["sahne"])
            # B7: Claude modundan dönüş ücretsiz modele
            k("B7 varsayılan model ücretsiz", s.evaluate("_DEFAULT_MODEL") == "google/gemma-4-26b-a4b-it:free", s.evaluate("_DEFAULT_MODEL"))
            # B5: 401 → sade cümle
            m = s.evaluate("""() => window.YukiIlkKurulum && YukiIlkKurulum.hataMetni(
                "Error code: 401 - {'error': {'message': 'User not found.', 'code': 401}}")""")
            k("B5 401 sade cümle", m and "geçersiz" in m and "{" not in m, m)
            k("B5 kısa ve anlaşılır hata korunur", s.evaluate("YukiIlkKurulum.hataMetni('Sunucuya ulaşılamadı.')") == "Sunucuya ulaşılamadı.")
            # B3: tanıtım oynarken sihirbaz görünmez, kalkınca görünür
            g = s.evaluate("""() => { const o = document.createElement('div'); o.id = 'yuki-opening'; o.appendChild(document.createElement('i'));
                document.body.appendChild(o); const z = document.createElement('div'); z.className = 'ilk-kurulum'; z.textContent = 'x';
                document.body.appendChild(z); const a = getComputedStyle(z).visibility; o.remove(); const b = getComputedStyle(z).visibility;
                z.remove(); return [a, b]; }""")
            k("B3 tanıtım oynarken sihirbaz gizli, sonra görünür", g == ["hidden", "visible"], g)
        s.context.close()

        # HALKA: B1 menü + telefon widget + B2 cevap
        s = sayfa(b, w, "hud-ring", "canli", mut, hata)
        if w == 390:
            t = s.evaluate("""() => { const w = [...document.querySelectorAll('.hr-widget')].filter(x =>
                !x.classList.contains('hr-w-hidden') && !x.classList.contains('hr-w-mobil-gizli') && x.getBoundingClientRect().height > 0);
                const h = document.getElementById('hr-ring-wrap').getBoundingClientRect();
                return {widget: w.length, halkaAlt: Math.round(h.bottom), H: innerHeight}; }""")
            k("390 açılışta tek widget görünür", t["widget"] == 1, t)
            k("390 halka üst yarıda", t["halkaAlt"] < t["H"] * 0.55, t)
        s.click("#input-more-btn")
        s.wait_for_timeout(700)
        m = s.evaluate(MENU)
        k(f"{w} B1 ⋯ menüsü basılabilir", len(m) >= 10 and all(m), f"{sum(m)}/{len(m)}")
        s.keyboard.press("Escape")
        s.wait_for_timeout(300)
        if s.evaluate("document.querySelector('#input-secondary-btns.acik') !== null"):
            s.click("#input-more-btn"); s.wait_for_timeout(300)
        once = s.evaluate("document.getElementById('hr-prompt-text').textContent")
        s.fill("#msg-input", "Merhaba Yuki, bugün hava nasıl?")
        s.press("#msg-input", "Enter")
        cevap = None
        for _ in range(20):
            s.wait_for_timeout(1000)
            c = s.evaluate("(() => { const t = document.getElementById('hr-prompt-text'); return t && t.classList.contains('hr-son-cevap') ? t.textContent : null })()")
            if c:
                cevap = c
                break
        k(f"{w} B2 cevap halkada yazılı", bool(cevap) and cevap != once, cevap)
        k(f"{w} B2 cevap görünür", bool(cevap) and s.evaluate(GORUNUR, "#hr-prompt-text"), cevap)
        s.context.close()
    # 11-15 (goz): telefonda HQ şeridi kaydırılınca etkin çip sol okun (#hq-serit-geri) altına girmez
    s = sayfa(b, 390, "chat", "yazi", mut, hata)
    s.evaluate("switchTab('hq')"); s.wait_for_timeout(1500)
    for oda in ("Anahtar", "Sağlık", "Hafıza"):
        s.locator(".hq-nav-btn", has_text=re.compile(rf"^\s*{oda}\s*$")).first.click(force=True); s.wait_for_timeout(1800)
        r = s.evaluate("""() => { const a = document.querySelector('#hq-subnav .hq-nav-btn.active'), g = document.getElementById('hq-serit-geri');
          const ra = a.getBoundingClientRect(), rg = g.getBoundingClientRect();
          return [Math.round(ra.left), getComputedStyle(g).display !== 'none' ? Math.round(rg.right) : null]; }""")
        k(f"390 HQ {oda} çipi okun sağında", r[1] is not None and r[0] >= r[1], r)
    s.context.close()
    k("JS istisnası 0", not hata, hata[:2])
    return sonuc


def main():
    with sync_playwright() as p:
        b = p.chromium.launch(args=["--use-gl=swiftshader", "--enable-unsafe-swiftshader"])
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
    print(f"{len(r) - len(kalan)} geçti · {len(kalan)} kaldı")
    return len(kalan)


if __name__ == "__main__":
    sys.exit(main())
