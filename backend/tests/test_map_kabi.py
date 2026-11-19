"""MAP harita kabına AÇIK YÜKSEKLİK veren kural duruyor mu? (2026-09-21)

🔴 Neden bu test var: `#leaflet-map` için üründe HİÇBİR CSS kuralı yoktu ve
harita HİÇ çizilmiyordu. Ölçüldü (Playwright, 1920×1080, kademe pro):
tile istekleri 200 dönüyor · `#map-center` 1056 px · `#leaflet-map` **0 px** ·
canvas 0×0 · sayfa hatası yok. Yani sessiz kusur — alt şerit
"SİSTEM HAZIR — HARİTA MODÜLLERİ AKTİF" yazarken ekran boştu.
Leaflet kabın boyutunu CSS'ten okur; `height:auto` + boş içerik = 0.

⚠️ Bu test STATİKTİR ve tavanını bilir: kuralın *yazılı olduğunu* ölçer,
*çizdiğini* değil (CLAUDE.md § "bir sınıfın anılması, kural tanımladığını
göstermez"). Çizimin kanıtı canlı turdur:
`scratchpad/` altındaki kayıt scripti kayıt sırasında kap yüksekliğini basar.
"""
from __future__ import annotations

import re
from pathlib import Path

import pytest

KOK = Path(__file__).resolve().parents[2]
CSS = KOK / "frontend" / "css" / "map-hud.css"
INDEX = KOK / "frontend" / "index.html"


def _kural_govdesi(metin: str, secici: str) -> str | None:
    """`secici { ... }` bloğunun gövdesini döndür (yoksa None)."""
    kalip = re.compile(
        r"(?:^|[},])\s*" + re.escape(secici) + r"\s*\{([^}]*)\}", re.MULTILINE
    )
    m = kalip.search(metin)
    return m.group(1) if m else None


@pytest.fixture(scope="module")
def css() -> str:
    assert CSS.exists(), f"map-hud.css yok: {CSS}"
    return CSS.read_text(encoding="utf-8")


def test_leaflet_kabi_icin_kural_VAR(css: str) -> None:
    """Kural hiç yoksa harita 0 px kalır — kusurun kendisi buydu."""
    assert _kural_govdesi(css, "#leaflet-map") is not None, (
        "#leaflet-map için map-hud.css'te kural yok. Leaflet kaba açık yükseklik "
        "ister; kuralsız `height:auto` → 0 px → harita hiç çizilmez."
    )


def test_leaflet_kabina_ACIK_yukseklik_veriliyor(css: str) -> None:
    """Kuralın VAR olması yetmez — yükseklik üreten bir bildirim taşımalı.

    İki meşru yol: `inset:0` (konumlandırılmış, kardeş HUD'larla aynı dil) ya da
    `height: 100%/100vh`. Biri bile kalmazsa kap yine sıfırlanır.
    """
    govde = _kural_govdesi(css, "#leaflet-map")
    assert govde is not None, "önce test_leaflet_kabi_icin_kural_VAR düzeltilmeli"

    duz = re.sub(r"\s+", "", govde.lower())
    inset_yolu = "inset:0" in duz and "position:absolute" in duz
    height_yolu = bool(re.search(r"height:(100%|100vh|[1-9]\d*px)", duz))

    assert inset_yolu or height_yolu, (
        "#leaflet-map kuralı var ama yükseklik üretmiyor. Gövde: " + govde.strip()
    )


def test_map_center_hala_konumlandirilmis(css: str) -> None:
    """`inset:0` yolu ebeveynin konumlandırılmış olmasına bağlı.

    `#map-center` bir gün `position:static`e dönerse çocuk `#tab-map`'e göre
    konumlanır ve düzeltme sessizce anlamını yitirir.
    """
    govde = _kural_govdesi(css, "#map-center")
    assert govde is not None, "#map-center kuralı kayboldu"
    duz = re.sub(r"\s+", "", govde.lower())
    assert "position:absolute" in duz or "position:relative" in duz, (
        "#map-center konumlandırılmamış — #leaflet-map'in inset:0'ı yanlış "
        "ataya göre hesaplanır. Gövde: " + govde.strip()
    )


def test_map_hud_damgasi_bumplandi() -> None:
    """Düzeltme müşteriye ulaşsın: `?v=` damgası 1'de kalırsa eski CSS önbellekten gelir."""
    html = INDEX.read_text(encoding="utf-8")
    m = re.search(r"map-hud\.css\?v=(\d+)", html)
    assert m, "index.html'de map-hud.css damgası bulunamadı"
    assert int(m.group(1)) >= 2, (
        f"map-hud.css?v={m.group(1)} — onarım 2026-09-21'de v2'ye bumplandı; "
        "geri düşmüş olmalı."
    )
