"""Sekme menüsü ÇEKMECESİ — ☰ ile soldan açılan menünün kapısı.

2026-09-25: 60px ikon rayı ve <620px alt şerit ('in ölçeklediği şerit)
söküldü; yerine kişisel AliceAi'deki ☰ çekmece geldi. Bu dosya eski
`test_dar_serit_olcegi.py`'nin yerini aldı — o şeridin kendisi artık yok.

Kapı **statik**: dosya metnini okur. Canlı ölçüm ayrıca yapıldı (Playwright,
1280/390/360 — ☰'ın altında hiçbir etkileşimli öğe kalmadı; Ctrl+Tab, 1-6, F,
Esc çalıştı). Buradaki testler o ölçümün bozulmasını önceden yakalayacak
yapısal şartlardır.
"""

import re
from pathlib import Path

KOK = Path(__file__).resolve().parents[2] / "frontend"


def _oku(yol: str) -> str:
    return (KOK / yol).read_text(encoding="utf-8")


def _yorumsuz(metin: str) -> str:
    """CSS/JS/HTML yorumlarını atar — kalıntı taraması tarihçe notlarını saymasın."""
    metin = re.sub(r"/\*.*?\*/", "", metin, flags=re.S)
    metin = re.sub(r"<!--.*?-->", "", metin, flags=re.S)
    return re.sub(r"(?m)^\s*//.*$", "", metin)


INDEX = _oku("index.html")
KABUK = _oku("css/kabuk.css")
TOKENS = _oku("css/tokens.css")
CORE = _oku("js/core.js")
TABNAV = _oku("js/tab-nav.js")


def test_hedef_tokenlari_yerinde():
    """☰ `--hedef-mini` (36px), masaüstü dokunma hedefi `--hedef` (44px).

    ⚠️ 24px (WCAG 2.5.8) mutlak asgari — altına inen değer sessizce geçmemeli.
    """
    m = re.search(r"--hedef-mini:\s*(\d+)px", TOKENS)
    assert m and int(m.group(1)) == 36, "--hedef-mini 36px değil"
    m = re.search(r"--hedef:\s*(\d+)px", TOKENS)
    assert m and int(m.group(1)) == 44, "--hedef 44px değil"
    govde = re.search(r"#nav-ac\s*\{([^}]*)\}", KABUK)
    assert govde and "--hedef-mini" in govde.group(1), "☰ boyutu --hedef-mini'den gelmiyor"


def test_eski_ray_kalintisi_yok():
    """Ray/şerit seçicileri geri gelirse iki menü üst üste çizilir."""
    eski = ["nav-collapsed", "rail-modules", "tab-more-btn", "nav-collapse-btn", "nav-fab"]
    for ad, metin in [("index.html", INDEX), ("kabuk.css", KABUK),
                      ("style.css", _oku("style.css")), ("core.js", CORE),
                      ("tab-nav.js", TABNAV)]:
        temiz = _yorumsuz(metin)
        for s in eski:
            assert s not in temiz, f"{ad}: eski ray kalıntısı '{s}'"


def test_cekmece_markup_erisilebilir():
    """☰ çekmeceyi `aria-controls` ile gösterir; kapalı çekmece `inert` başlar.

    `inert` yoksa ekran dışındaki sekme düğmeleri Tab ile odak alır —
    görünmeyen bir yere odak gider (ölçüldü kişiselde).
    """
    ac = re.search(r"<button[^>]*id=\"nav-ac\"[^>]*>", INDEX)
    assert ac, "☰ (#nav-ac) yok"
    assert 'aria-controls="tab-nav"' in ac.group(0)
    assert 'aria-expanded="false"' in ac.group(0)
    nav = re.search(r"<nav[^>]*id=\"tab-nav\"[^>]*>", INDEX)
    assert nav and re.search(r"\sinert[\s>]", nav.group(0)), "#tab-nav inert başlamıyor"
    assert 'id="nav-backdrop"' in INDEX, "perde yok — dışarı tıklayınca kapanmaz"


def test_rakam_kisayolu_ile_dugme_basligi_ayni():
    """core.js'teki 1-N haritası ile düğme başlığındaki `[N]` aynı sekmeyi göstermeli.

    Başlık kullanıcıya "5'e bas" der; harita başka sekmeye giderse ipucu yalan olur.
    """
    m = re.search(r"const tabMap = \{([^}]*)\}", CORE)
    assert m, "core.js tabMap yok"
    harita = dict(re.findall(r"'(\d)'\s*:\s*'(\w+)'", m.group(1)))
    assert harita, "tabMap boş"
    for dugme in re.findall(r"<button[^>]*class=\"tab-btn[^\"]*\"[^>]*>", INDEX):
        sekme = re.search(r'data-tab="(\w+)"', dugme).group(1)
        baslik = re.search(r'title="\[(\d)\]', dugme)
        assert baslik, f"{sekme}: başlıkta [N] yok"
        assert harita.get(baslik.group(1)) == sekme, \
            f"{sekme}: başlık [{baslik.group(1)}] ama tabMap {harita.get(baslik.group(1))}"


def test_ctrl_tab_ve_f_kisayolu():
    """Ürün Tab'ı tarayıcıya bırakır (odak gezinmesi) — sekme geçişi Ctrl+Tab."""
    assert re.search(r"e\.ctrlKey[^\n]*e\.key === 'Tab'|e\.key === 'Tab'[^\n]*e\.ctrlKey", CORE), \
        "Ctrl+Tab işleyicisi yok"
    assert "toggleTabDropdown()" in CORE, "F kısayolu çekmeceyi açmıyor"
    assert not re.search(r"window\.switchTab\s*=(?!=)", _yorumsuz(CORE)), \
        "core.js switchTab'ı eziyor — yönlendirme tek sahipli (tab-nav.js)"


def test_esc_yalniz_cekmeceyi_kapatir():
    """Açık çekmecede Esc AYARLAR katmanını kapatmamalı, sesi kesmemeli."""
    blok = re.search(r"e\.key !== 'Escape' \|\| !_navAcikMi\(\)(.*?)\}, true\);", TABNAV, re.S)
    assert blok, "Esc işleyicisi yakalama evresinde değil"
    assert "stopImmediatePropagation" in blok.group(1)


def test_sol_ust_oge_nav_boslugu_birakir():
    """☰ sabit durur; sol üst köşedeki öğeler ona yer açar.

    Canlı ölçümde bu dördü ☰'ın altında kalıyordu. Sol üste yeni öğe konursa
    kabuk.css'teki SEKME MENÜSÜ notuna eklenmeli.
    """
    assert "--nav-bosluk" in KABUK
    # #char-bar 09-25'te alt bilgi bloğuna taşındı (akışta) — ☰ payına gerek kalmadı.
    for yol, secici in [("css/sohbet.css", '#app[data-avatar-ayar="kucuk"] #avatar-pane'),
                        ("css/hq.css", "#hq-subnav"),
                        ("css/map-hud.css", "#map-serit")]:   # 10-04 sol panel kalktı, sol üstte yer şeridi
        govde = re.search(re.escape(secici) + r"\s*\{([^}]*)\}", _yorumsuz(_oku(yol)))
        assert govde and "--nav-bosluk" in govde.group(1), f"{yol} {secici} ☰'a yer açmıyor"
    assert "yuki-nav-bosluk" in TABNAV, "PLAN iframe'ine ☰ payı eklenmiyor"
