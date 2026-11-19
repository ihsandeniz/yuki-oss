"""HALKA modu snap bölgeleri — üst üste binen tasarım geri gelmesin.

🔴 Ölçülen kusur (2026-08-04, geliştiricinin Windows turu): bölge konumları **boş
alanın** (`ch - wh`) kesirleriydi (0.28 · 0.5 · 0.72) ama her bölge kutusu
**widget yüksekliği** kadar çiziliyordu. Widget uzadıkça boş alan küçülür,
5 konum daralan bir şeride sıkışır, kutular aynı kalır → bölgeler birbirinin
üstüne biner.

Varsayılan FİNANS widget'ında (320×380, tuval 1532×900) ÖLÇÜLDÜ:
  Sol Üst ↔ Sol Üst-Orta   %80 · Sol Üst-Orta ↔ Sol Orta %70
  Sol Orta ↔ Sol Alt-Orta  %70 · Sol Alt-Orta ↔ Sol Alt  %64
Yani 5 bölge fiilen 1,5 bölgeydi: kullanıcı nereye bıraktığını göremiyor,
bıraktığı yer gösterilenden başkası oluyordu.

Bu dosya **statik bekçidir, kanıt değildir.** Kanıt ölçümdür:
`scratchpad/halka-snap-olc.py` (canlı tarayıcıda bölge dikdörtgenlerini okur ve
komşu örtüşmesini yüzde olarak hesaplar; düzeltmeden sonra her widget
yüksekliğinde %0). Buradaki testler yalnız kırık tasarımın sessizce geri
dönmesini engeller.
"""
from __future__ import annotations

import re
from pathlib import Path

import pytest

HUD = Path(__file__).resolve().parents[2] / "frontend" / "modes" / "hud-ring.js"


@pytest.fixture(scope="module")
def kaynak() -> str:
    return HUD.read_text(encoding="utf-8")


def test_bolgeler_uretilir_sabit_liste_degil(kaynak: str):
    """Bölgeler (tuval, widget) girdisinden hesaplanmalı."""
    assert "function _computeSnapZones(" in kaynak, "bölge üreticisi yok"
    assert "const SNAP_ZONES = [" not in kaynak, (
        "sabit 12'li bölge listesi geri gelmiş — widget uzayınca üst üste biner"
    )
    assert "getPos" not in kaynak, "eski getPos deseni kalmış"


def test_bos_alan_kesirleri_geri_gelmemis(kaynak: str):
    """`(ch-wh)*0.28` sınıfı konumlandırma kusurun ta kendisiydi."""
    kotu = re.findall(r"\(\s*ch\s*-\s*wh\s*\)\s*\*\s*0?\.\d+", kaynak)
    assert not kotu, f"boş-alan kesri geri gelmiş: {kotu}"


def test_cizim_ve_secim_ayni_kaynaktan(kaynak: str):
    """Gösterilen kutu ile bırakılan yer ayrışmasın — tek gerçek kaynak.

    Ayrı hesaplasalardı önizleme yalan söylerdi; bu dosyada bir kez yaşanmış
    hata sınıfı ("aynı soruya iki cevap").
    """
    for fn in ("_showSnapZones", "_findNearestZone"):
        govde = _fonksiyon_govdesi(kaynak, fn)
        assert "_computeSnapZones(" in govde, f"{fn} bölgeleri kendi üretiyor"


def test_slot_sayisi_widget_yuksekligine_bagli(kaynak: str):
    govde = _fonksiyon_govdesi(kaynak, "_snapSlotSayisi")
    assert "wh" in govde, "slot sayısı widget yüksekliğine bakmıyor"
    assert "Math.max(1" in govde, "en az 1 slot güvencesi yok"


@pytest.mark.parametrize("ad", ["SNAP_UST", "SNAP_ARA", "SNAP_MAKS_SLOT"])
def test_geometri_sabitleri_adlandirilmis(kaynak: str, ad: str):
    """Sihirli sayı yerine adlandırılmış sabit — biri değişince niyeti okunsun."""
    assert re.search(rf"const {ad}\s*=", kaynak), f"{ad} sabiti yok"


def _fonksiyon_govdesi(kaynak: str, ad: str) -> str:
    """`function ad(` ile başlayan bloğu süslü parantez dengesiyle çıkar."""
    i = kaynak.find(f"function {ad}(")
    assert i >= 0, f"{ad} bulunamadı — test sessizce boşa düşerdi"
    j = kaynak.index("{", i)
    derinlik = 0
    for k in range(j, len(kaynak)):
        if kaynak[k] == "{":
            derinlik += 1
        elif kaynak[k] == "}":
            derinlik -= 1
            if derinlik == 0:
                return kaynak[j:k + 1]
    raise AssertionError(f"{ad} gövdesi kapanmıyor")
