"""HQ panelleri (ayarlar · modlar · monitör/sistem · bildirim) — kabuk sözleşmesi.

Dört panel de HQ kabuğunda ve ilgili backend uçları yerinde: panel kimlikleri, menü kaydı,
bildirim odasının gelen-kutusu/alarm bölümleri ve ayarlar sıfırlama ucu. Kabuk bozulursa
(panel silinir, menüden düşer) burası kırmızı olur; panel içi davranışı mevcut testler kilitler.
"""
from __future__ import annotations

from pathlib import Path

import pytest

KOK = Path(__file__).resolve().parents[2]
INDEX = (KOK / "frontend" / "index.html").read_text(encoding="utf-8")
JS = (KOK / "frontend" / "js" / "intro-sequences.js").read_text(encoding="utf-8")

PANELLER = ["ayarlar", "modlar", "sistem", "pushlog"]


@pytest.mark.parametrize("ad", PANELLER)
def test_panel_kabukta_ve_menuye_kayitli(ad):
    assert f'id="hq-panel-{ad}"' in INDEX
    assert f"'{ad}'" in JS.split("_HQ_PANELS=[", 1)[1].split("]", 1)[0]


@pytest.mark.parametrize("kimlik", ["bd-baslik", "hq-pushlog-list", "bd-daha", "bd-alarm-girdi",
                                    "intel-reminder-count"])
def test_bildirim_odasi_bolumleri(kimlik):
    assert f'id="{kimlik}"' in INDEX


@pytest.mark.parametrize("kimlik", ["hq-modes-list", "hq-mode-form", "hq-settings-main"])
def test_modlar_ve_ayarlar_kaplari(kimlik):
    assert f'id="{kimlik}"' in INDEX


def test_backend_uclari_yerinde():
    from app.api import monitor, push, settings_api

    def yollar(m):
        return {x.path for x in m.router.routes}

    assert any(p.endswith("/yuki-dedi") for p in yollar(push))
    assert any(p.endswith("/snapshot") for p in yollar(monitor))
    assert any(p.endswith("/reset-preview") for p in yollar(settings_api))
