"""Sohbet ekranı kişisel Yuki düzeninde (2026-11-14) — üst çubuk · boş ekran · araç yayı · kip seçici · tek karakter.

Geliştirici seçimi (11-14 işaretleme sayfası): madde 1-4 "kişiseldeki gibi" + "Yuki dışındaki karakterleri kaldır".

Çalıştırma:
    python3 -m pytest frontend/tests/test_sohbet_ust_kisisel.py -q                         # yalnız yapı kapıları
    YUKI_URL=http://127.0.0.1:8151 python3 -m pytest frontend/tests/test_sohbet_ust_kisisel.py -q
Tarayıcı testleri sunucu yoksa atlanır; yapı kapıları her zaman koşar.
"""
from __future__ import annotations

import os
import re
import urllib.request
from pathlib import Path

import pytest

FE = Path(__file__).resolve().parents[1]
BASE = os.getenv("YUKI_URL", "http://127.0.0.1:8001")


def _oku(yol: str) -> str:
    return (FE / yol).read_text(encoding="utf-8")


def _header() -> str:
    h = _oku("index.html")
    return h.split('<header id="header">', 1)[1].split("</header>", 1)[0]


# ── Yapı kapıları (sunucusuz) ──────────────────────────────────────────

def test_ust_cubuk_kisisel_duzen():
    h = _header()
    assert 'class="hud-unit-label">Yuki<' in h, "kimlik: ● Yuki hazır"
    assert "sekme-baslik" not in h, "Sohbet'te eski serif 'YUKI / Sohbet' başlığı geri gelmiş"
    assert 'id="theme-btn"' not in h, "kişiselde üst çubukta tema düğmesi yok (tema HQ'da)"
    assert 'id="header-actions-toggle"' not in h, "katlanır ⋯ başlık menüsü kalkmıştı"
    sira = [h.index(f'id="{k}"') for k in ("vol-wrap", "mem-num", "mode-toggle", "avatar-toggle", "ub-temizle", "ub-disa")]
    assert sira == sorted(sira), "sıra: ses · hafıza · görünüm · avatar · temizle · dışa aktar"


def test_bos_ekran_kartsiz():
    h = _oku("index.html")
    bos = h.split('id="chat-empty-state"', 1)[1].split("</div>", 1)[0]
    assert "empty-card" not in h and "empty-cards" not in h, "öneri kartları geri gelmiş"
    assert bos.count("data-i18n=") == 2, "iki satır: merhaba + yardım sorusu"
    assert "baslangicOnerisi" not in _oku("js/core.js"), "kart işleyicisi ölü kod olarak kalmış"


def test_arac_yayi_ve_hep_dinle():
    h = _oku("index.html")
    assert "girdi.yuki-ye-yaz" in h
    tr = _oku("js/diller/tr.js")
    assert "'girdi.yuki-ye-yaz': 'Yuki\\'ye yaz… (/ komutlar)'" in tr, "yer tutucu komut ipucunu taşımalı"
    assert 'id="team-btn"' not in h, "uzman ekibi yok → düğmesi de yok"
    satir = h.split('<div id="hizli-satir"', 1)[1].split("</div>\n      </div>", 1)[0]
    assert 'id="hep-dinle-anahtar"' in satir and 'role="switch"' in satir
    core = _oku("js/core.js")
    assert "function _girisYayiDiz(sec)" in core
    assert "_hepDinleAnahtarTazele();" in core.split("async function toggleAlwaysOn() {", 1)[1][:200], \
        "anahtar her değişimde tazelenmeli"


def test_ses_ikonu_emojiye_donmez():
    core = _oku("js/core.js")
    assert "icon.textContent = _audioMuted" not in core and "icon.textContent = '🔇'" not in core, \
        "ses ikonu textContent ile emojiye çevrilip SVG'yi siliyordu"
    assert core.count("icon.dataset.durum =") == 3


def test_tek_karakter_ve_varliklar_yok():
    cm = _oku("modes/chat-modes.js")
    liste = re.search(r"const CHARACTERS = \[(.*?)\];", cm, re.S).group(1)
    assert re.findall(r"_kar\('(\w+)'", liste) == ["yuki"]
    assert "if (!COK_KARAKTER) return;" in cm, "tek karakterde seçici şerit kurulmamalı"
    kalan = sorted(p.name for p in (FE / "assets/characters").iterdir())
    for ad in ("nova", "kira", "sera", "rei"):
        assert not any(k.startswith(ad + "_") for k in kalan), f"{ad} görseli depoda kalmış"
    assert "const CHARACTER_KEYS = ['yuki'];" in _oku("js/core.js")
    for dil in ("tr", "en"):
        s = _oku(f"js/diller/{dil}.js")
        assert not re.search(r"'karakter\.(nova|kira|sera|rei)\.", s), f"{dil}: silinen karakterin metni kalmış"


def test_kisisel_css_yuklu_ve_mod_cssini_yener():
    h = _oku("index.html")
    i_gk = h.index('href="/ui/css/giris-konsol.css')
    i_sk = h.index('href="/ui/css/sohbet-kisisel.css')
    assert i_sk > i_gk, "giris-konsol.css'ten SONRA yüklenmeli"
    css = _oku("css/sohbet-kisisel.css")
    # tembel yüklenen mod CSS'leri (1 id) bu dosyayı ezmesin → kurallar 2 id ile
    for kural in ("#app #header #mode-toggle {", "#app #input-area #input-secondary-btns {", "body.sohbet-mode #app .ss-kip button[aria-checked=\"true\"] {"):
        assert kural in css, kural


# ── Tarayıcı testleri ─────────────────────────────────────────────────

def _sunucu_var() -> bool:
    try:
        urllib.request.urlopen(BASE + "/health", timeout=2)
        return True
    except Exception:
        return False


tarayici = pytest.mark.skipif(not _sunucu_var(), reason=f"sunucu yok: {BASE}")

HAZIR = """try{sessionStorage.setItem('yukiAcilis_v1','1');localStorage.setItem('yuki-ilk-kurulum_v1','test');
 localStorage.setItem('yukiViewMode_v1','%s');localStorage.setItem('yukiSohbetKip_v1','canli');}catch(e){}"""


def _sayfa(p, gen, mod="chat"):
    br = p.chromium.launch()
    ctx = br.new_context(viewport={"width": gen, "height": 844 if gen < 500 else 800})
    ctx.add_init_script(HAZIR % mod)
    pg = ctx.new_page()
    hatalar = []
    pg.on("pageerror", lambda e: hatalar.append(str(e)))
    pg.goto(BASE + "/", wait_until="load")
    pg.wait_for_function("() => !document.getElementById('yuki-opening') || getComputedStyle(document.getElementById('yuki-opening')).display === 'none' || !document.getElementById('yuki-opening').firstChild", timeout=15000)
    pg.wait_for_timeout(1200)
    return br, pg, hatalar


@tarayici
@pytest.mark.parametrize("gen", [1280, 390])
def test_ust_cubuk_ve_bos_ekran_tarayicida(gen):
    from playwright.sync_api import sync_playwright
    with sync_playwright() as p:
        br, pg, hatalar = _sayfa(p, gen)
        d = pg.evaluate("""() => {
          const ad = document.querySelector('#header .hud-unit-label');
          const b = document.getElementById('state-badge');
          const kart = document.querySelectorAll('#chat-empty-state .empty-card').length;
          const bas = getComputedStyle(document.querySelector('#chat-empty-state .empty-title'));
          const r = document.getElementById('header').getBoundingClientRect();
          const tasan = [...document.querySelectorAll('#header button, #header .hud-mem-badge')]
            .filter(e => e.offsetParent && (e.getBoundingClientRect().right > innerWidth + 1)).map(e => e.id || e.className);
          return { ad: ad.textContent, durum: getComputedStyle(b, '::after').content, kart,
                   font: bas.fontFamily, kip: !!document.getElementById('char-bar'), tasan, h: r.height,
                   dalga: document.getElementById('waveform-hud') ? getComputedStyle(document.getElementById('waveform-hud')).display : 'yok' };
        }""")
        assert d["ad"] == "Yuki"
        assert d["durum"].strip('"').lower() in ("hazır", "kurulum gerekli", "anahtar yok") or d["durum"] != "none", d
        assert d["kart"] == 0
        assert "Mono" in d["font"] or "mono" in d["font"], "boş ekran daktilo (mono) yazısı değil: " + d["font"]
        assert not d["kip"], "tek karakterde Y·N·K·S·R şeridi çizilmiş"
        assert d["tasan"] == [], f"üst çubuktan taşan öğe: {d['tasan']}"
        assert d["dalga"] in ("none", "yok")
        assert hatalar == [], hatalar
        br.close()


@tarayici
@pytest.mark.parametrize("gen,mod", [(1280, "chat"), (390, "chat"), (1280, "hud-ring")])
def test_arac_yayi_acilir_kapanir(gen, mod):
    from playwright.sync_api import sync_playwright
    with sync_playwright() as p:
        br, pg, hatalar = _sayfa(p, gen, mod)
        pg.click("#input-more-btn")
        pg.wait_for_timeout(600)
        d = pg.evaluate("""() => {
          const sec = document.getElementById('input-secondary-btns');
          const dug = [...sec.querySelectorAll(':scope > .more-item')].filter(b => getComputedStyle(b).display !== 'none' && !b.hidden);
          const ad = dug.map(b => (b.querySelector('.yay-ad') || {}).textContent || '');
          const xs = dug.map(b => b.getBoundingClientRect());
          const ust = Math.min(...xs.map(r => r.top));
          const ekranda = xs.every(r => r.left >= -1 && r.right <= innerWidth + 1 && r.top >= 0);
          return { n: dug.length, ad, ekranda, acik: sec.classList.contains('acik'),
                   gor: getComputedStyle(sec).visibility, tik: getComputedStyle(dug[0]).pointerEvents,
                   y0: xs[0].top, yOrta: xs[Math.floor(xs.length/2)].top };
        }""")
        assert d["acik"] and d["gor"] == "visible" and d["tik"] == "auto", d
        assert d["n"] >= 9, d
        assert all(d["ad"]), "her düğümün kısa adı olmalı: %s" % d["ad"]
        assert d["ekranda"], "yay düğümü ekran dışına taşıyor"
        if gen > 800:
            assert d["yOrta"] < d["y0"] - 30, "masaüstünde yay: orta düğüm uçlardan yukarıda olmalı"
        pg.keyboard.press("Escape")
        pg.wait_for_timeout(400)
        assert not pg.evaluate("document.getElementById('input-secondary-btns').classList.contains('acik')")
        assert hatalar == [], hatalar
        br.close()


@tarayici
def test_hep_dinle_anahtari_durumu_izler():
    from playwright.sync_api import sync_playwright
    with sync_playwright() as p:
        br, pg, hatalar = _sayfa(p, 1280)
        once = pg.evaluate("[document.getElementById('hep-dinle-anahtar').getAttribute('aria-checked'), document.getElementById('hep-dinle-yazi').textContent]")
        assert once[0] == "false" and "kapalı" in once[1], once
        sonra = pg.evaluate("() => { alwaysOnMode = true; _hepDinleAnahtarTazele(); const a = document.getElementById('hep-dinle-anahtar'); return [a.getAttribute('aria-checked'), a.classList.contains('acik'), document.getElementById('hep-dinle-yazi').textContent]; }")
        assert sonra[0] == "true" and sonra[1] and "açık" in sonra[2], sonra
        assert hatalar == [], hatalar
        br.close()


@tarayici
def test_ses_ikonu_svg_kalir():
    from playwright.sync_api import sync_playwright
    with sync_playwright() as p:
        br, pg, hatalar = _sayfa(p, 1280, "hud-ring")
        d = pg.evaluate("() => { _setVolume(0.3); const a = document.getElementById('vol-icon'); const r = [!!a.querySelector('svg'), a.dataset.durum]; _toggleMute(); r.push(a.dataset.durum, !!a.querySelector('svg')); return r; }")
        assert d == [True, "kisik", "kapali", True], d
        assert hatalar == [], hatalar
        br.close()


@tarayici
def test_kip_secici_secili_kip_adiyla():
    from playwright.sync_api import sync_playwright
    with sync_playwright() as p:
        br, pg, hatalar = _sayfa(p, 1280)
        d = pg.evaluate("""() => {
          const sec = document.querySelector('#ss-kip button[aria-checked="true"]');
          if (!sec) return null;
          const ad = sec.querySelector('.ss-kip-ad');
          return { ad: ad && getComputedStyle(ad).display, renk: getComputedStyle(sec).color };
        }""")
        assert d, "kip seçici yok"
        assert d["ad"] != "none", "seçili kipin adı görünmeli (kişiseldeki etiketli hap)"
        assert hatalar == [], hatalar
        br.close()


@tarayici
def test_halka_tema_mod_menusunde():
    from playwright.sync_api import sync_playwright
    with sync_playwright() as p:
        br, pg, hatalar = _sayfa(p, 1280, "hud-ring")
        pg.wait_for_function("() => !!window.HalkaTema", timeout=8000)
        pg.click("#mode-toggle")
        pg.wait_for_timeout(400)
        segler = pg.evaluate("[...document.querySelectorAll('#view-mode-menu .vmm-tema:not([hidden]) .vmm-seg')].map(b => b.dataset.halkatema)")
        assert len(segler) >= 2, segler
        hedef = [s for s in segler if s != pg.evaluate("window.HalkaTema.al()")][0]
        pg.click(f'#view-mode-menu .vmm-seg[data-halkatema="{hedef}"]')
        pg.wait_for_timeout(500)
        assert pg.evaluate("window.HalkaTema.al()") == hedef
        # SOHBET'te tema satırı gizli
        pg.evaluate("window.setViewMode('chat')")
        pg.wait_for_timeout(600)
        pg.click("#mode-toggle")
        pg.wait_for_timeout(300)
        assert pg.evaluate("document.querySelector('#view-mode-menu .vmm-tema').hidden")
        assert hatalar == [], hatalar
        br.close()
