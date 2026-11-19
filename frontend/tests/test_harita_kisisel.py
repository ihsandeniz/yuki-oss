"""HARİTA — kişiseldeki "Gözlemevi" düzeni (2026-11-13).

İki kat:
  A · Statik (sunucusuz): index.html yerleşimi, stil bağı, map-hud.js / map-engine.js kancaları.
  B · Tarayıcı (YUKI_URL varsa): boş durum, YAKINDA süzgeci, sekmeler, 390/1280 taşma, JS istisnası 0.

Tarayıcı katı için geçici veriyle ikinci portta sunucu:
    YUKI_DATA_DIR=$(mktemp -d) AUTH_TOKEN= uvicorn app.main:app --port 18823
    YUKI_URL=http://127.0.0.1:18823 python -m pytest frontend/tests/test_harita_kisisel.py -q

🔴 Konum: tarayıcıya SAHTE konum verilir (Ankara Kızılay) ve IP'den konum servisi (ipapi.co) taklit
edilir — testin ekranına ya da çıktısına gerçek konum girmez. Deprem verisi de ağdan alınmaz:
YAKINDA süzgeci sahte olaylarla (window._mapEqSon) sınanır.
"""
from __future__ import annotations

import json
import os
import re
import time
import urllib.request
from pathlib import Path

import pytest

FE = Path(__file__).resolve().parent.parent
INDEX = (FE / "index.html").read_text(encoding="utf-8")
HUD = (FE / "js/map-hud.js").read_text(encoding="utf-8")
MOTOR = (FE / "js/map-engine.js").read_text(encoding="utf-8")
CSS = (FE / "css/map-gozlemevi.css").read_text(encoding="utf-8")
TR = (FE / "js/diller/tr.js").read_text(encoding="utf-8")

BASE = os.getenv("YUKI_URL", "http://127.0.0.1:8001")
SAHTE = {"latitude": 39.9208, "longitude": 32.8541}   # Ankara Kızılay — demo konumu


def _harita_html() -> str:
    a = INDEX.index('<div id="tab-map"')
    b = INDEX.index("<!-- Place Detail Panel", a)
    return INDEX[a:b]


# ══ A · STATİK ═══════════════════════════════════════════════════════════════

def test_gozlemevi_sinifi_ve_stil_bagi():
    assert re.search(r'<div id="tab-map" class="gozlemevi"', INDEX), "#tab-map 'gozlemevi' sınıfını taşımıyor"
    i_kont = INDEX.find("/ui/css/map-controls.css")
    i_goz = INDEX.find("/ui/css/map-gozlemevi.css")
    assert i_goz > 0, "map-gozlemevi.css bağlı değil"
    assert i_goz > i_kont, "map-gozlemevi.css map-controls.css'ten SONRA yüklenmeli (onu ezer)"


def test_bos_durum_karti():
    h = _harita_html()
    m = re.search(r'<section id="map-bos"[^>]*>', h)
    assert m and " hidden" in m.group(0), "#map-bos başlangıçta hidden olmalı (JS sayar, açar)"
    assert 'onclick="mapBosBasla()"' in h
    # mapKatmanSay görünürlüğü yönetir: 0 katmanda açık, ≥1'de gizli
    assert re.search(r"bos\.hidden\s*=\s*toplam\s*>\s*0", HUD), "mapKatmanSay #map-bos görünürlüğünü yönetmiyor"
    # mapBosBasla açık olanı KAPATMAZ (toggleLayer aç/kapa yapar)
    govde = HUD[HUD.index("window.mapBosBasla"):HUD.index("window.mapBosBasla") + 400]
    assert "aria-checked') !== 'true'" in govde, "mapBosBasla açık katmanı kapatabilir"


def test_yakinda_dunya_gundem_sekmeleri():
    h = _harita_html()
    sekmeler = re.findall(r'role="tab" class="mh-yk-sekme" data-yk="(\w+)" aria-selected="(\w+)"', h)
    assert sekmeler == [("yakin", "true"), ("dunya", "false"), ("gundem", "false")], sekmeler
    for kimlik in ("map-yakin-list", "map-dunya-list", "map-news-list", "map-gundem-sayi", "map-yk-govde", "map-yk-sor"):
        assert f'id="{kimlik}"' in h, kimlik
    # eski GÜNDEM kimlikleri korunur (map-engine.js haberleri buraya yazar)
    assert "getElementById('map-news-list')" in MOTOR or 'getElementById("map-news-list")' in MOTOR


def test_kontroller_sade():
    h = _harita_html()
    sag_ust = h[h.index('<div id="map-sag-ust">'):h.index("</div>", h.index('<div id="map-sag-ust">'))]
    assert 'id="map-gorunum"' not in sag_ust, "GÖRÜNÜM sağ üstte kalmış — sağ altta olmalı"
    alt = h[h.index('<div id="map-alt-sag">'):h.index("<!-- ROTA")]
    assert 'id="map-gorunum"' in alt
    for k in ('id="map-view-bar"', 'id="map-coords"', 'id="vbtn-scope"'):
        assert k not in alt, f"{k} sağ altta kalmış — çekmecenin GÖRÜNÜM bölümünde olmalı"
    cekmece = h[h.index('<aside id="map-katman-cekmece"'):h.index("</aside>")]
    gor = cekmece[cekmece.index('class="mk-grup mk-gorunum"'):]
    for k in ('id="map-view-bar"', 'id="map-coords"', 'id="vbtn-scope"', 'id="vbtn-tl"', "mapGorselMod('eo')"):
        assert k in gor, f"{k} çekmecenin GÖRÜNÜM bölümünde değil"


def test_gok_kp_telefonda_gorunur():
    h = _harita_html()
    gok = h[h.index('class="mh-bolum mh-gok"'):]
    gok = gok[:gok.index("</div>")]
    kp = re.search(r'<span class="([^"]*)" id="map-kp">', gok)
    assert kp and "mh-tel-gizle" not in kp.group(1) and "mh-canli" in kp.group(1), "Kp telefonda görünmeli, canlı (mavi)"
    iss = re.search(r'<span class="([^"]*)" id="map-iss-dist">', gok)
    assert iss and "mh-tel-gizle" in iss.group(1)


def test_motor_kancalari():
    assert "window._mapEqSon = d.features" in MOTOR, "deprem yanıtı YAKINDA'ya verilmiyor"
    assert "mh-dep" in MOTOR and 'class="mh-iss"' in MOTOR
    assert "createPane('mhEtiket')" in MOTOR and "pane: 'mhEtiket'" in MOTOR
    geo = MOTOR[MOTOR.index("function _onGeoSuccess"):]
    geo = geo[:geo.index("\n}\n")]
    assert "mapYakinGuncelle" in geo


def _ustvirgul(metin):
    parca, d, cur = [], 0, ""
    for c in metin:
        d += c == "("; d -= c == ")"
        if c == "," and d == 0:
            parca.append(cur); cur = ""
        else:
            cur += c
    return parca + [cur]


def test_css_tema_kapisi():
    """Gece giysisi yalnız koyu temada: B katı ':root:not([data-tema])' ile başlar."""
    b = CSS[CSS.index("══ B · GÖZLEMEVİ GECE GİYSİSİ"):]
    kurallar = [s.strip() for s in re.findall(r"\n([^\n{}/@][^{}]*)\{", b)]
    assert kurallar, "B katı boş"
    for k in kurallar:
        for secici in _ustvirgul(k):
            secici = secici.strip()
            if secici:
                assert secici.startswith(":root:not([data-tema])"), f"tema kapısız gece kuralı: {secici}"
    # A katı tema token'ı dışında ham gece rengi yazmaz
    a = CSS[:CSS.index("══ B · GÖZLEMEVİ GECE GİYSİSİ")]
    a = re.sub(r"/\*.*?\*/", "", a, flags=re.S)
    assert not re.search(r"#0[0-9a-f]{5}\b", a), "A katında ham gece rengi var — token kullan"


def test_kisisel_konum_yok():
    """Kodda/CSS'te sabit gerçek konum ya da kişisel şehir yok (demo konumu yalnız testte)."""
    for ad, metin in (("map-hud.js", HUD), ("map-gozlemevi.css", CSS)):
        assert not re.search(r"\b3[6-9]\.\d{3,}\s*,\s*2[6-9]\.\d{3,}", metin), f"{ad}: sabit koordinat"


def test_yeni_metin_anahtarlari():
    """Yeni metinler data-i18n / _t('harita.…') ile — sözlüğe ORTAK şerit ekler (birleştirmede).
    Birleştirmeden önce HİÇBİRİ sözlükte yoksa atlanır; bir kısmı varsa eksikler kusurdur."""
    h = _harita_html()
    anahtarlar = set(re.findall(r'data-i18n(?:-aria-label|-title)?="(harita\.[a-z0-9.-]+)"', h))
    anahtarlar |= set(re.findall(r"_t\('(harita\.[a-z0-9.-]+)'", HUD))
    yeni = {k for k in anahtarlar if k.startswith(("harita.bos-", "harita.yakin", "harita.yon-", "harita.once-"))}
    eksik = sorted(k for k in anahtarlar if f"'{k}'" not in TR)
    if yeni and all(f"'{k}'" not in TR for k in yeni):
        pytest.skip(f"{len(eksik)} yeni anahtar ORTAK birleştirmesini bekliyor")
    # Dinamik önek (`_t('harita.yon-' + y8[0])`): öneki değil sekiz yönün hepsini ara.
    onekler = [k for k in eksik if k.endswith("-")]
    eksik = [k for k in eksik if not k.endswith("-")]
    for on in onekler:
        assert on == "harita.yon-", f"bilinmeyen dinamik önek: {on}"
        eksik += [on + y for y in ("k", "kd", "d", "gd", "g", "gb", "b", "kb") if f"'{on}{y}'" not in TR]
    assert not eksik, f"sözlükte olmayan anahtar: {eksik}"


# ══ B · TARAYICI ═════════════════════════════════════════════════════════════

def _sunucu_var(url: str) -> bool:
    try:
        return urllib.request.urlopen(url + "/health", timeout=3).status == 200
    except Exception:
        return False


tarayici_gerek = pytest.mark.skipif(not _sunucu_var(BASE), reason=f"sunucu yok ({BASE})")
GENISLIKLER = [(390, 844), (1280, 800)]


@pytest.fixture(scope="module")
def tarayici():
    from playwright.sync_api import sync_playwright
    with sync_playwright() as p:
        b = p.chromium.launch(args=["--disable-features=LocalNetworkAccessChecks,BlockInsecurePrivateNetworkRequests"])
        yield b
        b.close()


def _sayfa(br, vp):
    from perdesiz import PERDESIZ_JS
    ctx = br.new_context(viewport={"width": vp[0], "height": vp[1]}, service_workers="block",
                         geolocation=SAHTE, permissions=["geolocation"])
    ctx.route("**/ipapi.co/**", lambda r: r.fulfill(json={**SAHTE, "city": "Ankara"}))
    pg = ctx.new_page()
    pg._hatalar = []
    pg.on("pageerror", lambda e: pg._hatalar.append(str(e)))
    pg.add_init_script(PERDESIZ_JS)
    pg.goto(BASE + "/ui/", wait_until="domcontentloaded")
    pg.wait_for_function("() => typeof window.switchTab === 'function' && typeof window.mapYakinGuncelle === 'function'")
    pg.evaluate("() => window.switchTab('map')")
    pg.wait_for_function("() => !document.getElementById('tab-map').hidden")
    pg.wait_for_timeout(600)
    return pg


def _olay(pg, dlat, dlon, mag, dk, yer):
    # Olaylar haritanın KULLANDIĞI konuma göre kurulur: demo kipi (YUKI_DEMO=1) tarayıcının konumunu
    # bilerek İstanbul'a sabitler — SAHTE'ye göre kurulursa hepsi "uzak" düşer (11-13 son birleştirme).
    lat, lon = pg.evaluate("() => [_mapUserLat, _mapUserLon]")
    return {"geometry": {"coordinates": [lon + dlon, lat + dlat, 10]},
            "properties": {"mag": mag, "place": yer, "time": int(time.time() * 1000) - dk * 60000, "src": "afad"}}


@tarayici_gerek
@pytest.mark.parametrize("vp", GENISLIKLER, ids=lambda v: f"{v[0]}")
def test_bos_durum_ve_basla(tarayici, vp):
    pg = _sayfa(tarayici, vp)
    try:
        # Yükleme sonrası katman tercihi geri gelmez → 0 katman → boş durum görünür
        pg.evaluate("() => { document.querySelectorAll('#map-katman-cekmece .mk-satir[aria-checked=\"true\"]').forEach(b => toggleLayer(b.id.replace('map-layer-',''))); mapKatmanSay(); }")
        assert pg.evaluate("() => !document.getElementById('map-bos').hidden"), "0 katmanda boş durum görünmüyor"
        kutu = pg.locator("#map-bos").bounding_box()
        assert kutu and kutu["width"] <= vp[0], "boş durum kartı ekrana sığmıyor"
        # Başla → deprem + ISS açık, kart gizli. Ağ isteklerini beklemeyiz; aria-checked anahtarı toggleLayer yazar.
        # Ağa çıkılmaz: ISS sahte konum, deprem uçları boş liste (katmanın AÇILDIĞI ölçülür, verisi değil)
        pg.route("**/api.wheretheiss.at/**", lambda r: r.fulfill(json={"latitude": 10.0, "longitude": 20.0, "altitude": 420.0, "velocity": 27600.0}))
        pg.route("**/*earthquake*", lambda r: r.fulfill(json={"type": "FeatureCollection", "features": []}))
        pg.locator("#map-bos-ac").click()
        pg.wait_for_timeout(300)
        acik = pg.evaluate("() => ['eq','iss'].map(k => document.getElementById('map-layer-'+k).getAttribute('aria-checked'))")
        assert acik == ["true", "true"], acik
        assert pg.evaluate("() => document.getElementById('map-bos').hidden"), "katman açılınca boş durum kalkmadı"
        # İkinci basış açık olanı kapatmaz
        pg.evaluate("() => mapBosBasla()")
        assert pg.evaluate("() => _layerActive.eq && _layerActive.iss")
        assert not pg._hatalar, pg._hatalar
    finally:
        pg.context.close()


@tarayici_gerek
def test_yakinda_suzgeci(tarayici):
    pg = _sayfa(tarayici, (1280, 800))
    try:
        pg.wait_for_function("() => typeof _mapUserLat !== 'undefined' && _mapUserLat !== null", timeout=10000)
        olaylar = [
            _olay(pg, 0.5, 0.5, 3.1, 30, "Yakın-yeni (AFAD)"),        # ~70 km, 30 dk
            _olay(pg, 1.5, 1.0, 4.2, 600, "Yakın-eski"),              # ~180 km, 10 sa
            _olay(pg, 0.2, 0.1, 2.6, 20 * 60, "En-yakın-ama-eski"),   # ~24 km, 20 sa
            _olay(pg, 8.0, 8.0, 6.1, 10, "Uzak-büyük"),               # > 300 km → YAKINDA'ya girmez, DÜNYA'da ilk
            _olay(pg, 0.1, 0.1, 3.0, 26 * 60, "Bayat"),               # > 24 sa → girmez
        ]
        pg.evaluate("(o) => { window._mapEqSon = o; _layerActive.eq = true; mapYakinGuncelle(); }", olaylar)
        satir = pg.evaluate("() => [...document.querySelectorAll('#map-yakin-list button.mh-olay .mh-o-ne')].map(e => e.firstChild.textContent.trim())")
        assert "Uzak-büyük" not in satir and "Bayat" not in satir, satir
        assert 1 <= len(satir) <= 3, satir
        assert satir[0] == "Yakın-yeni", f"yakın + yeni olay üstte olmalı: {satir}"
        assert pg.evaluate("() => document.querySelector('#map-yakin-list .mh-olay.yeni') !== null"), "1 saatten yeni olay işaretlenmedi"
        # yer adındaki kaynak eki temizlenir, kaynak alt satırda
        alt = pg.evaluate("() => document.querySelector('#map-yakin-list .mh-o-ne small').textContent")
        assert "AFAD" in alt and "km" in alt
        # DÜNYA sekmesi: en büyük önce
        pg.locator('#map-gundem .mh-yk-sekme[data-yk="dunya"]').click()
        assert pg.evaluate("() => !document.getElementById('map-dunya-list').hidden && document.getElementById('map-yakin-list').hidden")
        ilk = pg.evaluate("() => document.querySelector('#map-dunya-list .mh-o-tur').textContent")
        assert "6" in ilk, ilk
        # ok tuşu ile sekme değişir (tablist)
        pg.locator('#map-gundem .mh-yk-sekme[data-yk="dunya"]').press("ArrowRight")
        assert pg.evaluate("() => document.querySelector('#map-gundem').dataset.sekme") == "gundem"
        # deprem kapalı → YAKINDA 'Depremleri aç' der
        pg.evaluate("() => { _layerActive.eq = false; mapYakinGuncelle(); }")
        assert pg.evaluate("() => !!document.querySelector('#map-yakin-list [data-yk-ac=\"eq\"]')")
        assert not pg._hatalar, pg._hatalar
    finally:
        pg.context.close()


@tarayici_gerek
@pytest.mark.parametrize("vp", GENISLIKLER, ids=lambda v: f"{v[0]}")
def test_yerlesim_tasma_yok(tarayici, vp):
    pg = _sayfa(tarayici, vp)
    try:
        pg.wait_for_timeout(1500)
        olcum = pg.evaluate("""() => {
          const ids = ['map-serit','map-gundem','map-alt-sag','map-katman-ac','map-ara-ac'];
          const r = {}; for (const i of ids) { const e = document.getElementById(i); if (!e) continue;
            const b = e.getBoundingClientRect(); r[i] = [b.left, b.top, b.right, b.bottom]; }
          return { r, sw: document.documentElement.scrollWidth, w: innerWidth,
                   kucuk: [...document.querySelectorAll('#map-serit .mh-bolum, #map-gundem button, #map-alt-sag button')]
                     .filter(e => e.offsetParent && e.getBoundingClientRect().height < 24).length };
        }""")
        assert olcum["sw"] <= olcum["w"] + 1, f"yatay taşma: {olcum['sw']} > {olcum['w']}"
        for ad, (l, t, r, b) in olcum["r"].items():
            assert l >= -1 and r <= vp[0] + 1, f"{ad} ekrandan taşıyor: {l}..{r}"
        # YAKINDA kartı ile GÖRÜNÜM grubu üst üste binmez
        g, a = olcum["r"]["map-gundem"], olcum["r"]["map-alt-sag"]
        ust_uste = not (g[2] <= a[0] or a[2] <= g[0] or g[3] <= a[1] or a[3] <= g[1])
        assert not ust_uste, f"YAKINDA kartı GÖRÜNÜM ile çakışıyor: {g} ∩ {a}"
        assert not pg._hatalar, pg._hatalar
    finally:
        pg.context.close()
