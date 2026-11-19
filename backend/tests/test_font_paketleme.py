"""A10 — CSS'in istediği her font pakette OLMALI (2026-09-18).

🔴 Kapatılan arıza: `tokens.css::--font-mono` ve `planner.css::--font` ikisi de
'JetBrains Mono' istiyordu, font hiçbir yerde paketlenmemişti. Geliştirme
makinesinde o font SİSTEMDE kurulu olduğu için ürün JetBrains Mono ile
görünüyordu; müşteride Noto Sans Mono'ya düşüyordu.

**Ürün iki makinede iki farklı fontla görünüyordu ve bunu kimse göremezdi** —
geliştirici hiçbir zaman müşterinin gördüğü ekranı görmüyordu. Bu testin varlık
sebebi tam olarak budur: kusur ekrana bakarak YAKALANAMAZ, çünkü bakan kişinin
makinesinde font kuruludur.

Bu yüzden kapı "ekranda güzel duruyor mu" değil, **"dosya pakette var mı"** diye
sorar; ölçüsü de sistemde kurulu fontlardan bağımsızdır.
"""
from __future__ import annotations

import re
from pathlib import Path

import pytest

FRONTEND = Path(__file__).resolve().parents[2] / "frontend"

# Paketlenmesi beklenmeyen jenerik aileler (tarayıcı/işletim sistemi sağlar).
JENERIK = {
    "system-ui", "ui-monospace", "ui-sans-serif", "ui-serif", "sans-serif",
    "serif", "monospace", "cursive", "fantasy", "inherit", "initial", "unset",
    "-apple-system", "blinkmacsystemfont", "sfmono-regular", "sf mono", "menlo",
    "consolas", "monaco", "courier new", "segoe ui", "roboto", "helvetica",
    "helvetica neue", "arial", "liberation mono", "dejavu sans mono",
    "noto sans mono", "apple color emoji", "segoe ui emoji", "emoji",
}


def _css_dosyalari() -> list[Path]:
    """Frontend'in TÜM css'leri.

    ⚠️ Sadece `css/` ve `vendor/` taramak yetmez (ilk hâli öyleydi): `style.css`
    kökte duruyor ve üç aile tanımlıyor, `modes/*.css` ise kendi @font-face'ini
    taşıyor (Chakra Petch). Dar tarama, kapının yalan yeşil vermesi demekti.
    """
    return [y for y in FRONTEND.rglob("*.css") if "node_modules" not in y.parts]


def _paketli_aileler() -> set[str]:
    """@font-face ile bildirilen ve dosyası GERÇEKTEN diskte olan aileler."""
    aileler: set[str] = set()
    for css in _css_dosyalari():
        metin = css.read_text(encoding="utf-8")
        for blok in re.findall(r"@font-face\s*\{([^}]*)\}", metin):
            ad = re.search(r"font-family:\s*['\"]?([^;'\"]+)", blok)
            src = re.search(r"url\(([^)]+)\)", blok)
            if not (ad and src):
                continue
            ham = src.group(1).strip("'\" ")
            yol = (FRONTEND / ham.removeprefix("/ui/")) if ham.startswith("/ui/") \
                else (css.parent / ham)
            # Dosyası olmayan @font-face "paketli" sayılmaz — 404 veren bir
            # bildirim, fontun kendisinden daha kötüdür (sessizce fallback).
            if yol.exists():
                aileler.add(ad.group(1).strip().lower())
    return aileler


def _istenen_aileler() -> dict[str, list[str]]:
    """CSS değişkenlerinde TIRNAK İÇİNDE geçen aile adları (dosya → aileler)."""
    istenen: dict[str, list[str]] = {}
    for css in _css_dosyalari():
        metin = css.read_text(encoding="utf-8")
        # Yalnız --font* değişken TANIMLARI; kullanım yerleri (var(--font)) değil.
        for satir in re.findall(r"--font[\w-]*:\s*([^;]+);", metin):
            # ⚠️ TIRNAK ZORUNLU. `--font-color-primary: #f0f4ff` da bu desene
            # uyuyor ama font değil renktir; tırnaksız okunursa kapı "#f0f4ff
            # adlı font paketli değil" der (ilk koşuda tam olarak bu oldu).
            # Tırnaksız aileler zaten jeneriklerdir (monospace, system-ui…).
            adlar = [a.lower() for a in re.findall(r"['\"]([^'\"]+)['\"]", satir)]
            gercek = [a for a in adlar if a and a not in JENERIK]
            if gercek:
                istenen.setdefault(css.name, []).extend(gercek)
    return istenen


def test_css_istedigi_her_font_paketli():
    """🔑 Asıl kapı. Bu kırmızı yanarsa: bir CSS pakette olmayan bir font
    istiyor → geliştiricide bir türlü, müşteride başka türlü görünür."""
    paketli = _paketli_aileler()
    assert paketli, "vendor/*.css içinde hiç geçerli @font-face bulunamadı"

    eksik: list[str] = []
    for dosya, aileler in _istenen_aileler().items():
        for aile in set(aileler):
            if aile not in paketli:
                eksik.append(f"{dosya} → '{aile}'")

    assert not eksik, (
        "CSS pakette olmayan font istiyor (müşteride fallback'e düşer, "
        "geliştiricide fontu kuruluysa DÜŞMEZ → ayrışma):\n  " + "\n  ".join(sorted(eksik))
    )


def test_jetbrains_mono_dosyalari_diskte():
    """Ağırlıkların hepsi olmalı: eksik ağırlık sentetik kalınlık üretir
    (tarayıcı fontu kendi kalınlaştırır) ve mono hizalama bozulur."""
    for agirlik in (400, 500, 600, 700):
        yol = FRONTEND / "fonts" / f"JetBrainsMono-{agirlik}-latin-ext.woff2"
        assert yol.exists(), f"eksik: {yol.name}"
        assert yol.stat().st_size > 5_000, f"şüpheli küçük: {yol.name}"


def test_mono_font_turkce_glifleri_tasiyor():
    """Subset'te Latin-Ext atlanırsa Türkçe harfler BAŞKA fontla çizilir —
    aynı satırda iki font, en kolay gözden kaçan görsel kusur."""
    fontTools = pytest.importorskip("fontTools", reason="fontTools yalnız geliştirme aracı")
    from fontTools.ttLib import TTFont

    yol = FRONTEND / "fonts" / "JetBrainsMono-400-latin-ext.woff2"
    cmap = TTFont(yol).getBestCmap()
    for ch in "ğĞşŞıİöÖüÜçÇ€←→✓":
        assert ord(ch) in cmap, f"mono font '{ch}' (U+{ord(ch):04X}) taşımıyor"


def test_mono_fontu_yukleyen_sayfalar():
    """`planner.html` `vendor/fonts.css`'i yüklemiyor (ölçüldü) — mono bildirimi
    oraya ayrıca ulaşmazsa PLAN ekranı fontu ALAMAZ ve arıza yarım kapanır."""
    for sayfa in ("index.html", "planner.html"):
        metin = (FRONTEND / sayfa).read_text(encoding="utf-8")
        assert "vendor/fonts-mono.css" in metin, f"{sayfa} mono fontu yüklemiyor"


def test_fontlar_assets_disinda():
    """`frontend/assets` içindeki her şey 24,8 MB'lık medya yüküne düşer ve
    yalnız `media_id` değişince iner; font oraya konursa sıradan delta ile
    güncellenemez."""
    assert not list((FRONTEND / "assets" / "fonts").glob("JetBrainsMono*")), \
        "JetBrains Mono assets/ altına konmuş — medya yüküne düşer"
    assert (FRONTEND / "fonts" / "JetBrainsMono-400-latin-ext.woff2").exists()
