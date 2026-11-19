"""Galeri sohbet araçları — `list_media` · `show_media`.

`galeri_api.py` ve `alan_secici.py` bu iki aracı anıyordu ama araç modülü yoktu: model
"şu fotoğrafı göster" dediğinde elinde araç yoktu. Burada:
  · iki araç TOOLS'ta + dispatcher'da gerçekten çağrılabilir
  · `show_media` kök DIŞINI açamaz (galeri kapılarından geçer)
  · yayın `galeri_ac` + `id` taşır → arayüz `galeri.html?ac=<id>` ile açar
  · ekrana ulaşmadıysa "gönderildi" demez

    cd backend && python -m pytest -q tests/test_galeri_arac.py
"""
from __future__ import annotations

import pytest

from app.api import galeri_api as g
from app.services.tools import galeri as arac
from tests.test_galeri import _png


@pytest.fixture()
def kok(tmp_path, monkeypatch):
    k = (tmp_path / "Galerim").resolve()
    (k / "tatil").mkdir(parents=True)
    (k / "tatil" / "deniz.png").write_bytes(_png())
    (k / "kedi.png").write_bytes(_png())
    (k / "ikiz").mkdir()
    (k / "ikiz" / "kedi.png").write_bytes(_png())       # aynı ad, başka klasör
    disari = (tmp_path / "Disari").resolve()
    disari.mkdir()
    (disari / "sir.png").write_bytes(_png())
    monkeypatch.setattr(g, "VERI", tmp_path / "veri")
    monkeypatch.setattr(g, "ONBELLEK", tmp_path / "veri" / "onbellek")
    monkeypatch.setattr(g, "AYAR_YOLU", tmp_path / "veri" / "galeri-ayar.json")
    monkeypatch.setenv("YUKI_GALERI_KOKLER", str(k))
    monkeypatch.setattr(g, "_TUM_ONBELLEK", (0.0, (), []))
    g._KAYIT.clear()
    return k, disari


class _SahteYonetici:
    def __init__(self, ulasan: int = 1):
        self.ulasan = ulasan
        self.giden: list[dict] = []

    async def broadcast(self, m: dict) -> int:
        self.giden.append(m)
        return self.ulasan


@pytest.fixture()
def ekran(monkeypatch):
    from app.api import websocket
    y = _SahteYonetici()
    monkeypatch.setattr(websocket, "_manager", y)
    return y


# ── kayıt ──────────────────────────────────────────────────────────────

def test_iki_arac_semada_ve_yetkide():
    from app.services.tools.dispatcher import TOOLS, get_active_tools
    adlar = {t["function"]["name"] for t in TOOLS}
    assert {"list_media", "show_media"} <= adlar
    etkin = {t["function"]["name"] for t in get_active_tools()}
    assert {"list_media", "show_media"} <= etkin


def test_alan_secici_galeri_mesajinda_araclari_sunar():
    from app.services.tools.alan_secici import sema_sec
    from app.services.tools.dispatcher import TOOLS
    adlar = {t["function"]["name"] for t in sema_sec("galerideki kedi fotoğrafını göster", TOOLS)}
    assert {"list_media", "show_media"} <= adlar


@pytest.mark.asyncio
async def test_dispatcher_iki_araci_gercekten_cagirir(kok, ekran, monkeypatch):
    from app.services.tools import dispatcher
    monkeypatch.setattr(dispatcher, "_is_tool_allowed", lambda n: True)
    metin = await dispatcher.call_tool("list_media", {"ara": "deniz"})
    assert "deniz.png" in metin
    metin = await dispatcher.call_tool("show_media", {"hedef": "deniz.png"})
    assert "gönderildi" in metin and ekran.giden


# ── list_media ─────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_list_media_ara_ve_bos_sorgu(kok):
    metin = await arac.list_media("deniz")
    assert "deniz.png" in metin and "tatil" in metin and "id " in metin
    hepsi = await arac.list_media()
    assert hepsi.count("\n- ") == 3


@pytest.mark.asyncio
async def test_list_media_bulamayinca_acik_soyler(kok):
    assert "yok" in await arac.list_media("zebra")


@pytest.mark.asyncio
async def test_list_media_tavan_ve_bozuk_tur(kok):
    assert (await arac.list_media("", limit=1)).count("\n- ") == 1
    assert (await arac.list_media("", limit=10_000)).count("\n- ") == 3
    assert "Bilinmeyen tür" in await arac.list_media("", tip="pdf")


# ── show_media ─────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_show_media_ad_ile_galeri_ac_yayinlar(kok, ekran):
    metin = await arac.show_media("deniz")
    assert "deniz.png" in metin and "gönderildi" in metin
    m = ekran.giden[-1]
    assert m["type"] == "galeri_ac" and m["ad"] == "deniz.png"
    # `galeri.html?ac=<id>` → `/bilgi/<id>` bu kimliği çözebilmeli (B yolu)
    assert g._KAYIT[m["id"]].endswith("deniz.png")
    assert m["klasor_id"] == g._kimlik((kok[0] / "tatil"))


@pytest.mark.asyncio
async def test_show_media_id_ile_ayni_adli_dogru_dosyayi_acar(kok, ekran):
    liste = await arac.list_media("kedi")
    ikiz_id = next(s.rsplit("id ", 1)[1] for s in liste.splitlines() if "· ikiz ·" in s)
    await arac.show_media(ikiz_id)
    assert ekran.giden[-1]["id"] == ikiz_id
    assert "/ikiz/" in g._KAYIT[ikiz_id]


@pytest.mark.asyncio
async def test_show_media_kok_disini_acamaz(kok, ekran):
    _, disari = kok
    metin = await arac.show_media(str(disari / "sir.png"))
    assert "bulunamadı" in metin
    assert ekran.giden == []


@pytest.mark.asyncio
async def test_show_media_kok_disi_kimlik_kaydi_da_kapidan_gecer(kok, ekran):
    """`_KAYIT`'a bir yolla kök dışı bir kayıt düşse bile id yolu kapıyı atlayamaz."""
    _, disari = kok
    sahte = g._kimlik(disari / "sir.png")
    assert "bulunamadı" in await arac.show_media(sahte)
    assert ekran.giden == []


@pytest.mark.asyncio
async def test_show_media_ekran_yoksa_gonderildi_demez(kok, ekran):
    ekran.ulasan = 0
    metin = await arac.show_media("deniz")
    assert "gönderildi" not in metin and "ekranı yok" in metin


@pytest.mark.asyncio
async def test_show_media_bos_hedef(kok, ekran):
    assert "belirtilmedi" in await arac.show_media("  ")
    assert ekran.giden == []
