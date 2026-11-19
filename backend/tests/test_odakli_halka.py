"""Odaklı Halka — HALKA merkez menüsü, yapı kapıları (2026-10-11).

Kişisel 933779b'nin ürün çevirisi. Davranış: `frontend/tests/test_odakli_halka.py`.
Burada sunucusuz:
  ① Eski çark tamamen gitti (JS üretici + CSS) — yarım söküm iki menü bırakırdı.
  ② Sekmeler gezinme çubuğundan OKUNUR (gizli = kademede kapalı → menüde yok);
    ikinci bir sekme listesi yok. Kısayol numaraları core.js tabMap ile aynı.
  ③ 🔴 Ödeme duvarı: kilitli karaktere tıklama _lockToast ile DÖNER, setCharacter
    ondan SONRA gelir.
  ④ Kara Mana yuvaları menünün düğümlerini izler (`halka:odak-ciz`).
  ⑤ Kullanılan her `hudring.od.*` anahtarı tr + en'de.
"""
from __future__ import annotations

import re

from yardim import FRONTEND, sozluk, yorumsuz

HUD = FRONTEND / "modes" / "hud-ring.js"


def _hud() -> str:
    return yorumsuz(HUD.read_text(encoding="utf-8"))


def _css_yorumsuz(yol) -> str:
    return re.sub(r"/\*.*?\*/", " ", yol.read_text(encoding="utf-8"), flags=re.S)


def test_eski_cark_tamamen_gitti():
    js = _hud()
    for eski in ("TAB_WHEEL", "_wheelHtml", "_charWheelHtml", "hr-wheel-btn", "hr-cw-btn", 'id="hr-wheel"', 'id="hr-char-wheel"'):
        assert eski not in js, f"hud-ring.js'te eski çark kalıntısı: {eski}"
    for css in (FRONTEND / "modes" / "hud-ring.css", FRONTEND / "modes" / "halka-tema" / "kara-mana-goz.css", FRONTEND / "perf-adaptive.css"):
        govde = _css_yorumsuz(css)
        for eski in (".hr-wheel-btn", ".hr-cw-btn", "#hr-char-wheel", ".hr-wb-lbl"):
            assert eski not in govde, f"{css.name}: ölü kural {eski}"
    assert '<div id="hr-odak">${_odHtml()}</div>' in js


def test_sekmeler_navdan_ve_kademe_gizlisi_dusuyor():
    js = _hud()
    m = re.search(r"return \[\.\.\.document\.querySelectorAll\('#tab-items \.tab-btn\[data-tab\]'\)\]\s*\.filter\(b => !b\.hidden\)", js)
    assert m, "sekmeler nav'dan okunmuyor ya da gizli (kademede kapalı) sekme süzülmüyor"


def test_kisayollar_core_tabmap_ile_ayni():
    js = _hud()
    od = dict(re.findall(r"(\w+): (\d)", re.search(r"const OD_KISAYOL = \{([^}]*)\}", js).group(1)))
    core = yorumsuz((FRONTEND / "js" / "core.js").read_text(encoding="utf-8"))
    tm = re.search(r"const tabMap = \{([^}]*)\}", core).group(1)
    tab = {v: k for k, v in re.findall(r"'(\d)':'(\w+)'", tm)}
    assert od == tab, f"Odaklı Halka kısayolları core.js tabMap'ten ayrıştı: {od} ≠ {tab}"


def test_odeme_duvari_kilitli_karaktere_gecis_yok():
    js = _hud()
    blok = re.search(r"kok\.addEventListener\('click', e => \{(.*?)\n    \}\);", js, re.S)
    assert blok, "Odaklı Halka tıklama işleyicisi bulunamadı"
    g = blok.group(1)
    kilit = g.find("if (_charLocked(id)) { _lockToast(id); return; }")
    gec = g.find("window.setCharacter(id)")
    assert kilit != -1, "kilitli karakter kapısı yok"
    assert gec != -1 and kilit < gec, "setCharacter kilit kapısından ÖNCE çalışıyor"


def test_kara_mana_yuvalari_menuyu_izler():
    km = yorumsuz((FRONTEND / "modes" / "halka-tema" / "kara-mana-goz.js").read_text(encoding="utf-8"))
    assert "#hr-odak .hr-od-dugum" in km and "document.addEventListener('halka:odak-ciz'" in km
    assert '<g class="kg-yuvalar">${yuvalar()}</g>' in km
    assert "document.dispatchEvent(new CustomEvent('halka:odak-ciz'" in _hud()


def test_surum_damgasi_esit():
    cm = (FRONTEND / "modes" / "chat-modes.js").read_text(encoding="utf-8")
    v = re.search(r"const ASSET_V = '(\d+)'", cm).group(1)
    assert f'/ui/modes/chat-modes.js?v={v}"' in (FRONTEND / "index.html").read_text(encoding="utf-8"), \
        "index.html chat-modes.js?v= ile ASSET_V eşit değil — hud-ring.js eski sürümde kalır"


def test_kullanilan_anahtarlar_iki_sozlukte():
    js = HUD.read_text(encoding="utf-8")
    anahtarlar = set(re.findall(r"_hrt\('(hudring\.od\.[a-z.-]+)'", js))
    # dinamik: 'hudring.od.unvan.' + c.key · 'hudring.od.ne.' + id · 'hudring.od.grup.' + k
    for on, ekler in (("hudring.od.unvan.", ("yuki",)),   # 11-14: Yuki dışı karakterler kaldırıldı
                      ("hudring.od.ne.", ("chat", "planner", "hq", "map", "ajan", "yedek", "galeri", "dosya")),   # 11-13: panel yok, yedek var
                      ("hudring.od.grup.", ("sekme", "kar"))):
        assert f"'{on}' +" in js
        anahtarlar |= {on + e for e in ekler}
    anahtarlar = {a for a in anahtarlar if not a.endswith(".")}
    assert len(anahtarlar) >= 20
    for dil in ("tr", "en"):
        s = sozluk(dil)
        eksik = sorted(a for a in anahtarlar if not s.get(a))
        assert not eksik, f"{dil} sözlüğünde eksik: {eksik}"
