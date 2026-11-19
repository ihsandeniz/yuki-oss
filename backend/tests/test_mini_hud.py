"""Mini HUD kartı (2026-10-04) — kişisel 6ba78e2'nin ürüne çevrilmesi.

Ana pencere gizliyken ekranda kalan 240×180 durum kartı. Burada ölçülenler:

  ① Menü girişi: GÖRÜNÜM › PENCERE bölümünde iki satır ("Mini HUD" · "Yalnız
    Mini HUD"), bölüm kaynağının (#pencere-mod-kaynak) İÇİNDE → menüye onunla
    taşınır. Kademe kapısı YOK (Free/Pro/Ultra — geliştirici kararı).
  ② Ürünün "Mini" PENCERE MODU ile ad çakışması yok (ayrı anahtar, ayrı kimlik).
  ③ i18n: üç yeni JS dosyası kuyruk kapısının dört ölçüsünden geçer
    (Türkçe literal yok · kendi sarmalayıcısı · window'da dil dinleyicisi ·
    kullanılan her anahtar tr + en'de).
  ④ İkinci bağlantı/ölçer YOK: kart da köprü de WS/fetch/getUserMedia/
    AudioContext kullanmaz; kart adresinde token taşınmaz.
  ⑤ mini.html'in ortak dosya damgaları index.html ile AYNI — yoksa sw.js
    cache-first'ü kartı eski sözlükle bırakır.
  ⑥ Electron kabuğu: ayrı ve dar preload, delta yüküyle taşınabilir.
"""
from __future__ import annotations

import re
from pathlib import Path

from yardim import FRONTEND, sozluk, yorumsuz

KOK = FRONTEND.parent
ELECTRON = KOK / "electron"
_TR_HARF = re.compile(r"[çğıöşüÇĞİÖŞÜ]")
_LITERAL = re.compile(r"'((?:[^'\\\n]|\\.)*)'|\"((?:[^\"\\\n]|\\.)*)\"|`((?:[^`\\]|\\.)*)`", re.S)

DOSYALAR = {"js/mini-hud.js": "_mht", "js/mini-kopru.js": "_mkt"}


def _oku(yol: str) -> str:
    return (FRONTEND / yol).read_text(encoding="utf-8")


def _kaynak_blogu() -> str:
    """index.html'deki #pencere-mod-kaynak bloğu (kapanışı: sekme menüsü yorumu)."""
    html = _oku("index.html")
    bas = html.index('<div id="pencere-mod-kaynak"')
    son = html.index("<!-- Sekme menüsü", bas)
    return html[bas:son]


# ── ① menü girişi ──────────────────────────────────────────────────────────

def test_menu_satirlari_PENCERE_bolumunun_kaynaginda():
    blok = _kaynak_blogu()
    for kimlik in ("mini-hud-satirlari", "mini-hud-ac-kapat", "mini-hud-yalniz"):
        assert f'id="{kimlik}"' in blok, f"{kimlik} PENCERE bölüm kaynağının dışında — menüye taşınmaz"
    for anahtar in ("mini-hud.menu.ac", "mini-hud.menu.ac-alt",
                    "mini-hud.menu.yalniz", "mini-hud.menu.yalniz-alt"):
        assert f'data-i18n="{anahtar}"' in blok


def test_kademe_kapisi_YOK():
    """Free'de de görünür: satırlar tab-nav'ın kademe kapılarına bağlı değil ve
    köprü lisans/yetki sormuyor."""
    kopru = yorumsuz(_oku("js/mini-kopru.js"))
    assert "entitlements" not in kopru and "_yetkiFetch" not in kopru and "license" not in kopru
    tabnav = _oku("js/tab-nav.js")
    assert "mini-hud" not in tabnav, "Mini HUD satırları kademe kapısının yönettiği dosyaya bağlanmış"


def test_kopru_core_jsten_SONRA_yukleniyor():
    html = _oku("index.html")
    core = html.index('src="/ui/js/core.js?v=')
    kopru = html.index('src="/ui/js/mini-kopru.js?v=')
    assert kopru > core, "mini-kopru.js core.js'ten önce — #messages/#mic-btn/yuki-state hazır değil"


# ── ② ad çakışması ─────────────────────────────────────────────────────────

def test_mini_PENCERE_MODU_ile_karismiyor():
    blok = _kaynak_blogu()
    satirlar = blok[blok.index('id="mini-hud-satirlari"'):]
    assert "data-pencere-mod" not in satirlar, (
        "Mini HUD satırı data-pencere-mod taşıyor — tab-nav onu pencere modu sanar "
        "(Wayland kısıtında devre dışı bırakır, radyo grubuna katar)"
    )
    tr = sozluk("tr")
    assert tr["pencere.mini"] != tr["mini-hud.menu.ac"]
    assert tr["mini-hud.menu.yalniz"] != tr["pencere.mini"]
    assert "HUD" in tr["mini-hud.menu.yalniz"], "Yalnız satırı 'Mini' moduyla aynı adı taşıyor"


# ── ③ i18n ────────────────────────────────────────────────────────────────

def test_TURKCE_literal_yok():
    ihlal = []
    for yol in DOSYALAR:
        for no, satir in enumerate(yorumsuz(_oku(yol)).splitlines(), 1):
            if "console." in satir:
                continue
            for m in _LITERAL.finditer(satir):
                metin = next(g for g in m.groups() if g is not None)
                if _TR_HARF.search(metin):
                    ihlal.append(f"{yol}:{no}: {metin[:60]!r}")
    assert not ihlal, "\n".join(ihlal)


def test_sarmalayici_ve_dil_dinleyicisi():
    for yol, ad in DOSYALAR.items():
        kod = yorumsuz(_oku(yol))
        assert re.search(rf"function {ad}\(anahtar, degerler\)", kod), f"{yol}: {ad} yok"
        assert "window.YukiDil.t(anahtar, degerler)" in kod
        assert "window.addEventListener('yuki-dil-degisti'" in kod, f"{yol}: dil değişimini dinlemiyor"


def test_kullanilan_her_anahtar_iki_sozlukte():
    tr, en = sozluk("tr"), sozluk("en")
    anahtarlar: set[str] = set()
    for yol, ad in DOSYALAR.items():
        anahtarlar |= set(re.findall(rf"\b{ad}\('([a-z0-9][\w.-]*)'", yorumsuz(_oku(yol))))
    anahtarlar = {k for k in anahtarlar if not k.endswith(".")}   # ön ek birleştirmesi
    # Birleştirilen anahtarlar: durum + sahne duygusu
    anahtarlar |= {f"mini-hud.durum.{d}" for d in
                   ("idle", "listening", "thinking", "talking", "sleeping", "error")}
    kart = yorumsuz(_oku("js/mini-hud.js"))
    duygular = re.search(r"var DUYGULAR = \[([^\]]+)\]", kart).group(1)
    anahtarlar |= {f"sahne.duygu.{d}" for d in re.findall(r"'(\w+)'", duygular)}
    html = _oku("mini.html") + _kaynak_blogu()
    anahtarlar |= set(re.findall(r'data-i18n(?:-[a-z-]+)?="([^"]+)"', html))
    eksik = [f"{d}: {k}" for k in sorted(anahtarlar) for d, s in (("tr", tr), ("en", en)) if k not in s]
    assert not eksik, "Sözlükte olmayan anahtar:\n" + "\n".join(eksik)


# ── ④ ikinci bağlantı / ölçer / token yok ─────────────────────────────────

def test_ikinci_baglanti_ve_olcer_YOK():
    for yol in ("js/mini-hud.js", "js/mini-kopru.js"):
        kod = yorumsuz(_oku(yol))
        for yasak in ("getUserMedia", "AudioContext", "new WebSocket", "fetch(", "authFetch", "EventSource"):
            assert yasak not in kod, f"{yol}: {yasak} — kart veriyi ana pencereden almalı"


def test_kart_adresinde_token_YOK():
    mod = (ELECTRON / "mini-hud.js").read_text(encoding="utf-8")
    assert "loadURL(o.icOnEk + '/ui/mini.html')" in mod
    assert "token" not in yorumsuz(mod).lower()


# ── ⑤ damgalar ────────────────────────────────────────────────────────────

def test_mini_html_ortak_damgalari_index_ile_AYNI():
    damga = re.compile(r"/ui/((?:css|js|vendor)/[\w./-]+\.(?:css|js))\?v=(\d+)")
    index = dict(damga.findall(_oku("index.html")))
    mini = dict(damga.findall(_oku("mini.html")))
    ortak = {y: v for y, v in mini.items() if y in index}
    assert {"js/diller/tr.js", "js/diller/en.js", "js/dil.js", "css/tokens.css"} <= set(ortak)
    farkli = {y: (v, index[y]) for y, v in ortak.items() if v != index[y]}
    assert not farkli, f"mini.html ↔ index.html damgası ayrışmış (mini, index): {farkli}"


def test_mini_html_basligi_electron_sabitiyle_ayni():
    mod = (ELECTRON / "mini-hud.js").read_text(encoding="utf-8")
    sabit = re.search(r"const MINI_BASLIK = '([^']+)'", mod).group(1)
    assert f"<title>{sabit}</title>" in _oku("mini.html"), "Hyprland eşleşmesi başlığa bağlı"


# ── ⑥ Electron kabuğu ─────────────────────────────────────────────────────

def test_kart_preloadu_DAR():
    pre = yorumsuz((ELECTRON / "mini-preload.js").read_text(encoding="utf-8"))
    assert re.findall(r"exposeInMainWorld\('(\w+)'", pre) == ["yukiMini"]
    for yasak in ("yukiApp", "yukiSistem", "yukiUpdater", "yukiModels", "yukiDosya", "invoke("):
        assert yasak not in pre


def test_uygulama_baglantisi_ve_delta_yuku():
    uyg = (ELECTRON / "uygulama.js").read_text(encoding="utf-8")
    assert "require('./mini-hud')" in uyg
    assert "preload: kaynak('mini-preload.js')" in uyg
    assert "miniHud.anaKapandi()" in uyg, "ana pencere kapanınca kart açık kalır (motor da kapanmaz)"
    assert "miniHud.ipcBagla(ipcMain)" in uyg
    yuk = (KOK / "scripts" / "update_payload.py").read_text(encoding="utf-8")
    yasak = re.search(r"ELECTRON_YASAK = \{(.*?)\}", yuk, re.S).group(1)
    assert "mini-hud.js" not in yasak and "mini-preload.js" not in yasak
