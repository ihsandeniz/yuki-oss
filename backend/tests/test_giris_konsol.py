"""Halka Konsolu yazı çubuğu — yapı kapıları (2026-10-11).

Davranış tarayıcıda: `frontend/tests/test_giris_konsol.py` (sunucu gerekli).
Burada sunucusuz:
  ① DOM'a dokunulmadı: grid öğeleri yerinde, hap bir `::before` katmanı ve
    düğmelerin ALTINDA (isolation + z-index:-1 birlikte — biri düşerse hap
    backdrop-filter yüzünden gönder/⋯ üstüne boyanır).
  ② Küçük hâl gizlemesi !important — sohbet.css'in flex dönemi kalıntısı
    `#input-more-btn { display:flex !important }` onu eziyordu.
  ③ "/" taslağı SİLMEZ ve küçük hâli açar (core.js).
  ④ Ürün kararları korunur: ⋯ menüsü etiketli kalır (yay yok), mikrofonda
    boşta süs halka yok (sohbet.css § ②), altın renk yok.
  ⑤ Çeviri: yeni anahtarlar tr + en; giris-konsol.js kuyruk kapısında.
"""
from __future__ import annotations

import re

from yardim import FRONTEND, sozluk, yorumsuz

CSS = FRONTEND / "css" / "giris-konsol.css"
JS = FRONTEND / "js" / "giris-konsol.js"


def _css() -> str:
    return re.sub(r"/\*.*?\*/", " ", CSS.read_text(encoding="utf-8"), flags=re.S)


def _html() -> str:
    return (FRONTEND / "index.html").read_text(encoding="utf-8")


def test_dosyalar_bagli_ve_sirali():
    html = _html()
    css = html.index("/ui/css/giris-konsol.css")
    assert html.index("/ui/css/sohbet.css") < css and html.index("/ui/modes/sohbet-sahne.css") < css, \
        "giris-konsol.css sohbet.css ve sohbet-sahne.css'ten SONRA yüklenmeli (onları ezer)"
    assert html.index("/ui/js/core.js") < html.index("/ui/js/giris-konsol.js")


def test_hap_katmani_dugmelerin_altinda():
    css = _css()
    blok = re.search(r"body:not\(\.hud-ring-mode\) #input-container::before \{([^}]*)\}", css)
    assert blok, "hap ::before katmanı yok"
    g = blok.group(1)
    assert "grid-column: 2 / -1" in g and "grid-row: 1" in g
    assert "z-index: -1" in g and "position: relative" in g
    assert "pointer-events: none" in g
    assert re.search(r"body:not\(\.hud-ring-mode\) #input-container \{[^}]*isolation: isolate", css)


def test_kucuk_hal_gizlemesi_important():
    css = _css()
    m = re.search(r"((?:#input-area\.kucuk [^,{]+,\s*)+#input-area\.kucuk #hizli-satir) \{ display: none !important; \}", css)
    assert m, "küçük hâl gizlemesi !important değil"
    for kimlik in ("#msg-input", "#input-more-btn", "#send-btn", "#hizli-satir", "#input-container::before"):
        assert f"#input-area.kucuk {kimlik}" in m.group(1)


def test_yaz_ve_kucult_dugmeleri_yerinde():
    html = _html()
    kap = html[html.index('<div id="input-container">'):html.index('<div id="hizli-satir"')]
    assert 'id="giris-ac"' in kap and 'onclick="girisKucult(false)"' in kap
    assert re.search(r'<button[^>]*id="giris-ac"[^>]*hidden>', kap.replace("\n", " ")), "YAZ düğmesi gizli doğmalı"
    haplar = html[html.index('class="hizli-haplar"'):]
    assert 'id="giris-kucult"' in haplar[:3000] and 'onclick="girisKucult(true)"' in haplar[:3000]
    for a in ('data-i18n-aria-label="girdi.kucult"', 'data-i18n="girdi.yaz"', 'data-i18n-aria-label="girdi.yaz-ac"'):
        assert a in html


def test_slash_taslagi_silmez():
    core = yorumsuz((FRONTEND / "js" / "core.js").read_text(encoding="utf-8"))
    m = re.search(r"if \(e\.key === '/' && !inInput[^{]*\{(.*?)\n  \}", core, re.S)
    assert m, "/ kısayolu bulunamadı"
    govde = m.group(1)
    assert "inp.value = ''" not in govde, "/ yarım taslağı siliyor"
    assert "window.GirisKonsol.ac()" in govde


def test_urun_kararlari_korunur():
    html = _html()
    # 11-14 (geliştirici seçimi "kişiseldeki gibi"): ⋯ menüsü kişiseldeki gibi
    # araç YAYI oldu — 08-03 "etiketli menü" kararı bu ekran için geri alındı. Etiket kaybolmadı:
    # her düğümün kısa adı (.yay-ad) + tam adı title/aria-label'da.
    assert 'id="input-secondary-btns" class="giris-yayi" role="menu"' in html, "araç yayı kabı"
    yay = re.sub(r'<!--.*?-->', '', html.split('id="input-secondary-btns"', 1)[1].split('id="input-more-btn"', 1)[0], flags=re.S)
    for dugme in re.findall(r'<button[^>]*class="more-item"[^>]*>.*?</button>', yay, re.S):
        # model + konuşma dili durum satırında; yayda gizli (css/sohbet-kisisel.css)
        if 'id="model-selector-btn"' in dugme or 'id="lang-toggle-btn"' in dugme:
            continue
        assert 'class="yay-ad"' in dugme, f"yay düğümünde görünen kısa ad yok: {dugme[:80]}"
    css = _css()
    # 10-11 (geliştirici kararı): boştaki süs halka ALINDI — ama giris-konsol.css'te ayrı
    # bir ::after ile değil, sohbet.css § ②'de mevcut #mic-level-ring'in kesikli hâliyle (tek halka).
    # Kapısı: test_birebir_konsol.py::test_mikrofon_bosta_kesikli_halka_cizer.
    assert "#mic-container::after" not in css, "ikinci bir süs halka katmanı açma — halka tek: #mic-level-ring"


def test_js_kalici_anahtar_ve_api():
    js = yorumsuz(JS.read_text(encoding="utf-8"))
    assert "var ANAHTAR = 'giris_kucuk_v1';" in js
    assert "window.girisKucult = kucult;" in js and "window.GirisKonsol" in js


def test_anahtarlar_iki_sozlukte():
    for dil in ("tr", "en"):
        s = sozluk(dil)
        for a in ("girdi.kucult", "girdi.yaz", "girdi.yaz-ac", "girdi.yaz-ac-ipucu"):
            assert s.get(a), f"{dil}: {a} yok"
