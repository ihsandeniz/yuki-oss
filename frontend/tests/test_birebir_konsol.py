"""Kişiselle birebir yazı çubuğu — tarayıcı testleri (2026-10-11).

Yapı kapıları: `backend/tests/test_birebir_konsol.py`.

Çalıştırma (sunucu gerekli — ikinci port):
    YUKI_URL=http://127.0.0.1:8021 backend/venv/bin/python -m pytest frontend/tests/test_birebir_konsol.py -q

Ölçülenler (390 ve 1280, normal/animasyonlu mod):
  1. Mikrofon boşta: kesikli halka GÖRÜNÜR; kayıtta kesik kalkar, seviye halkası çizer.
  2. Durum satırı ince (≤30px), "model · dil · küçült" ve çipsiz; her düğmenin dokunma
     alanı 44×44 (elementFromPoint), komşusunu ve yazı alanını çalmıyor.
  3. Çiplerin dört işlevi ⋯ menüsünde, menü ekranın içinde ve son öğesi ("Arayüz dili")
     ulaşılabilir (dar ekranda AKTAR'ın menüye dönmesi menüyü uzattı).
  4. küçült hâlâ çalışıyor; JS istisnası 0; yatay taşma 0.
"""
from __future__ import annotations

import os

import pytest

from perdesiz import PERDESIZ_JS   # açılış sinematiği + ilk kurulum perdesi tıklamayı keser

BASE = os.getenv("YUKI_URL", "http://127.0.0.1:8001")


def _sunucu_var() -> bool:
    import urllib.request
    try:
        return urllib.request.urlopen(BASE + "/health", timeout=3).status == 200
    except Exception:
        return False


pytestmark = pytest.mark.skipif(not _sunucu_var(), reason=f"sunucu yok: {BASE}")
GENISLIK = [(390, 844), (1280, 800)]


@pytest.fixture(scope="module")
def tarayici():
    from playwright.sync_api import sync_playwright
    with sync_playwright() as p:
        b = p.chromium.launch()
        yield b
        b.close()


def _sohbet(br, vp, tema="dark"):
    ctx = br.new_context(viewport={"width": vp[0], "height": vp[1]}, service_workers="block", color_scheme=tema)
    ctx.grant_permissions(["clipboard-read", "clipboard-write"], origin=BASE)
    pg = ctx.new_page()
    pg.add_init_script(PERDESIZ_JS)
    pg._hatalar = []
    pg.on("pageerror", lambda e: pg._hatalar.append(str(e)))
    pg.add_init_script("if (!sessionStorage.getItem('_k')) { localStorage.setItem('yukiViewMode','chat'); "
                       "localStorage.removeItem('giris_kucuk_v1'); sessionStorage.setItem('_k','1'); }")
    pg.goto(BASE + "/ui/", wait_until="networkidle")
    pg.wait_for_selector("#hizli-satir:not([hidden])")
    pg.wait_for_timeout(400)
    return pg


@pytest.mark.parametrize("vp", GENISLIK, ids=["390", "1280"])
def test_mikrofon_bosta_kesikli_kayitta_seviye(tarayici, vp):
    pg = _sohbet(tarayici, vp)
    try:
        bos = pg.evaluate("""() => { const r = document.getElementById('mic-level-ring'), bg = r.querySelector('.ring-bg');
            const s = getComputedStyle(r), b = r.getBoundingClientRect();
            return { op: +s.opacity, vis: s.visibility, disp: s.display, w: b.width, dash: getComputedStyle(bg).strokeDasharray }; }""")
        assert bos["op"] > 0.9 and bos["vis"] == "visible" and bos["disp"] != "none", bos
        assert bos["w"] >= 48, f"halka mikrofonun çevresini sarmalı: {bos}"
        assert bos["dash"] not in ("none", ""), f"boşta kesikli olmalı: {bos}"
        kayit = pg.evaluate("""() => { document.getElementById('mic-btn').classList.add('recording');
            const r = document.getElementById('mic-level-ring');
            const lv = r.querySelector('.ring-level'); lv.setAttribute('stroke-dasharray', '72 144.51');
            return { op: +getComputedStyle(r).opacity, dash: getComputedStyle(r.querySelector('.ring-bg')).strokeDasharray,
                     lv: getComputedStyle(lv).stroke, lvd: lv.getAttribute('stroke-dasharray') }; }""")
        assert kayit["op"] > 0.9 and kayit["dash"] in ("none", ""), f"kayıtta düz halka: {kayit}"
        assert kayit["lv"] not in ("none", "") and kayit["lvd"].startswith("72"), kayit
        assert pg._hatalar == [], pg._hatalar
    finally:
        pg.context.close()


SATIR_OLC = """() => {
  const s = document.getElementById('hizli-satir'), sb = s.getBoundingClientRect();
  const d = ['hap-model', 'hap-dil', 'hep-dinle-anahtar', 'giris-kucult'].map(id => {
    const e = document.getElementById(id), b = e.getBoundingClientRect();
    const cx = b.x + b.width / 2, cy = b.y + b.height / 2;
    const vur = (x, y) => { const t = document.elementFromPoint(x, y); return !!t && (t === e || e.contains(t)); };
    return { id, w: b.width, h: b.height, x: b.x, gor: getComputedStyle(e).display !== 'none',
      dikey: vur(cx, cy - 21) && vur(cx, cy + 21), yatay: vur(cx - Math.min(21, b.width / 2 + 8), cy) && vur(cx + Math.min(21, b.width / 2 + 8), cy) };
  });
  const hap = document.getElementById('msg-input').getBoundingClientRect();
  const ayrac = [...s.querySelectorAll('.hizli-ayrac')].filter(a => getComputedStyle(a).display !== 'none').length;
  return { h: sb.height, cip: document.querySelectorAll('#hizli-satir .hizli-cip').length, d, ayrac,
    metin: s.innerText.replace(/\\s+/g, ' ').trim(),
    yaziAlani: (() => { const t = document.elementFromPoint(hap.x + hap.width / 2, hap.bottom - 2); return t && t.id; })(),
    tasma: document.documentElement.scrollWidth - innerWidth };
}"""


@pytest.mark.parametrize("vp", GENISLIK, ids=["390", "1280"])
def test_durum_satiri_ince_ve_44px(tarayici, vp):
    pg = _sohbet(tarayici, vp)
    try:
        r = pg.evaluate(SATIR_OLC)
        assert r["cip"] == 0, r
        assert r["h"] <= 30, f"satır ince olmalı (≤30px): {r['h']}"
        # 11-14 (kişisel düzen): durum satırına "Hep dinle" anahtarı geldi — model · dil · hep dinle · küçült
        assert [x["id"] for x in sorted(r["d"], key=lambda x: x["x"])] == ["hap-model", "hap-dil", "hep-dinle-anahtar", "giris-kucult"]
        for x in r["d"]:
            assert x["gor"] and x["dikey"] and x["yatay"], f"44px dokunma alanı yok: {x}"
        # ayraçlar telefonda gizli (sohbet-kisisel.css ≤800), masaüstünde üç
        assert r["ayrac"] == (0 if vp[0] <= 800 else 3), r
        assert r["metin"].count("·") == r["ayrac"] and "TR" in r["metin"] and "Hep dinle" in r["metin"], r["metin"]
        assert r["yaziAlani"] == "msg-input", f"dokunma alanı yazı alanının altını çalıyor: {r['yaziAlani']}"
        assert r["tasma"] <= 0, r
        assert pg._hatalar == [], pg._hatalar
    finally:
        pg.context.close()


MENU_OLC = """() => {
  const m = document.getElementById('input-secondary-btns'), mb = m.getBoundingClientRect();
  const gor = id => { const e = typeof id === 'string' ? document.getElementById(id) : id; return !!e && !e.hidden && getComputedStyle(e).display !== 'none'; };
  const fn = f => [...m.querySelectorAll('.more-item')].find(b => (b.getAttribute('onclick') || '') === f);
  const son = document.getElementById('arayuz-toggle-btn');
  son.scrollIntoView({ block: 'nearest' });
  const sb = son.getBoundingClientRect(), mb2 = m.getBoundingClientRect();
  // Her görünen öğe kendi noktasında TIKLANABİLİR mi (sütunun dışı kırpılıyordu: 390'da
  // üst öğeler sahnenin altında kalıp tıklama karakter şeridine gidiyordu)
  const tiklanmaz = [...m.querySelectorAll('.more-item')].filter(b => gor(b) && b.getBoundingClientRect().height > 0).filter(b => {
    b.scrollIntoView({ block: 'nearest' });
    const r = b.getBoundingClientRect(), t = document.elementFromPoint(r.x + r.width / 2, r.y + r.height / 2);
    return !(t && (t === b || b.contains(t)));
  }).map(b => b.textContent.trim().slice(0, 24));
  return { tiklanmaz, pano: gor(fn('qaClipboard()')), ara: gor(fn('qaSearch()')), aktar: gor('menu-aktar'), ekran: gor('menu-ekran'),
    icinde: mb.top >= 0 && mb.bottom <= innerHeight + 1 && mb.left >= 0 && mb.right <= innerWidth + 1,
    sonGorunur: sb.top >= mb2.top - 1 && sb.bottom <= mb2.bottom + 1 && sb.height > 0 };
}"""


@pytest.mark.parametrize("vp", GENISLIK, ids=["390", "1280"])
def test_cip_islevleri_menude_ve_menu_ulasilir(tarayici, vp):
    pg = _sohbet(tarayici, vp)
    try:
        pg.click("#input-more-btn")
        pg.wait_for_timeout(300)
        r = pg.evaluate(MENU_OLC)
        assert r["pano"] and r["ara"] and r["aktar"], f"çip işlevi menüde görünmüyor: {r}"
        assert r["icinde"] and r["sonGorunur"], f"menü taşıyor ya da son öğe ulaşılamaz: {r}"
        assert r["tiklanmaz"] == [], f"menüde tıklanamayan öğe (başka katmanın altında): {r['tiklanmaz']}"
        # PANO menüden gerçekten çalışır
        pg.keyboard.press("Escape")
        pg.evaluate("() => navigator.clipboard.writeText('panodan merhaba')")
        pg.click("#input-more-btn")
        pg.locator("#menu-pano").click()
        pg.wait_for_function("() => document.getElementById('msg-input').value === 'panodan merhaba'", timeout=3000)
        assert pg._hatalar == [], pg._hatalar
    finally:
        pg.context.close()


def test_ekran_ogesi_yetki_kapisinda(tarayici):
    """Ekran aracı `/api/yetki` → tools listesinde yoksa menüde EKRAN yok (eski çipin kapısı)."""
    pg = _sohbet(tarayici, (1280, 800))
    try:
        tools = pg.evaluate("() => fetch('/api/yetki').then(r => r.json()).then(d => d.tools)")
        izinli = tools == "all" or (isinstance(tools, list) and "take_screenshot" in tools)
        assert pg.evaluate("() => !document.getElementById('menu-ekran').hidden") == izinli
    finally:
        pg.context.close()


@pytest.mark.parametrize("vp", GENISLIK, ids=["390", "1280"])
def test_kucult_yeni_dugmeden_calisir(tarayici, vp):
    pg = _sohbet(tarayici, vp)
    try:
        pg.click("#giris-kucult")
        pg.wait_for_function("() => document.getElementById('input-area').classList.contains('kucuk')")
        assert pg.evaluate("() => getComputedStyle(document.getElementById('hizli-satir')).display") == "none"
        pg.click("#giris-ac")
        pg.wait_for_function("() => !document.getElementById('input-area').classList.contains('kucuk')")
        assert pg._hatalar == [], pg._hatalar
    finally:
        pg.context.close()
