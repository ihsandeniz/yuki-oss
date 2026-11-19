"""Atölye genel bildirimi (`gorev_bildirim`).

Kabul ölçüleri:
  · bitti/yarım/hata/durdu bildirilir; kullanıcının durdurduğu iş bildirilmez
  · metin görev içeriğini (istek, ad) taşımaz
  · sessiz saatte ve `YUKI_ATOLYE_BITIS_BILDIRIM=0` iken push yok
  · gönderim hatası kancayı/görevi bozmaz
  · gerçek görev servisi: koşu bitince kanca bir kez çağrılır (sahte LLM, geçici kök)
  · üretim servisi kancayı bağlar
"""
import asyncio
import time
from datetime import datetime
from unittest.mock import patch

import pytest

from app.services import gorev as gorev_mod
from app.services import gorev_bildirim as gb
from app.services.atolye.baglam import yerel_baglam
from app.services.gorev import GorevServisi
from tests.atolye_yardimci import _icerik_akisi
from tests.test_gorev_servisi import SahteLLM

OGLE = time.mktime((2026, 11, 12, 14, 0, 0, 0, 0, -1))
GECE = time.mktime((2026, 11, 12, 23, 30, 0, 0, 0, -1))


@pytest.fixture(autouse=True)
def _ortam(monkeypatch):
    monkeypatch.delenv("YUKI_ATOLYE_SESSIZ", raising=False)
    monkeypatch.delenv("YUKI_ATOLYE_BITIS_BILDIRIM", raising=False)
    monkeypatch.setattr(gb, "_zaman", lambda: OGLE)


class Kayit:
    def __init__(self, hata=None):
        self.giden = []
        self.hata = hata

    async def __call__(self, baslik, govde, url):
        if self.hata:
            raise self.hata
        self.giden.append((baslik, govde, url))
        return 1


def _calistir(kanca, *kayitlar):
    async def _k():
        for gid, k in kayitlar:
            kanca(gid, k)
        await asyncio.gather(*list(kanca.gorevler))
    asyncio.run(_k())


def test_bitis_metni_ve_kullanici_durdurmasi():
    assert gb.bitis_metni({"durum": "bitti", "tur": "site"}).startswith("Site görevi bitti")
    assert "Araştırma" in gb.bitis_metni({"durum": "hata", "tur": "arastirma", "neden": "X"})
    assert gb.bitis_metni({"durum": "durdu", "neden": "gece", "tur": "site"})
    assert gb.bitis_metni({"durum": "durdu", "neden": "durdur", "tur": "site"}) is None
    assert gb.bitis_metni({"durum": "kosuyor", "tur": "site"}) is None
    assert gb.bitis_metni({"durum": "bitti", "tur": "bilinmeyen"}).startswith("Atölye görevi")


def test_metin_icerik_tasimaz():
    g = Kayit()
    _calistir(gb.BitisBildirimi(g), ("site/gizli-musteri", {
        "durum": "bitti", "tur": "site", "ad": "gizli-musteri", "istek": "Gizli Müşteri A.Ş. sitesi"}))
    (baslik, govde, url), = g.giden
    assert "gizli" not in govde.lower() and "müşteri" not in govde.lower()
    assert baslik == gb.baslik() == gb.BASLIK and url == "/ui/index.html#atolye"


def test_sessiz_saat_ve_kapali_ayar(monkeypatch):
    g = Kayit()
    k = gb.BitisBildirimi(g)
    monkeypatch.setattr(gb, "_zaman", lambda: GECE)
    _calistir(k, ("site/a", {"durum": "bitti", "tur": "site"}))
    assert g.giden == []
    monkeypatch.setattr(gb, "_zaman", lambda: OGLE)
    monkeypatch.setenv("YUKI_ATOLYE_BITIS_BILDIRIM", "0")
    _calistir(k, ("site/a", {"durum": "bitti", "tur": "site"}))
    assert g.giden == []
    monkeypatch.setenv("YUKI_ATOLYE_BITIS_BILDIRIM", "1")
    _calistir(k, ("site/a", {"durum": "bitti", "tur": "site"}))
    assert len(g.giden) == 1


def test_sessiz_aralik_ayari(monkeypatch):
    assert gb.sessiz_aralik() == (23, 8)
    monkeypatch.setenv("YUKI_ATOLYE_SESSIZ", "22-07")
    assert gb.sessiz_aralik() == (22, 7)
    monkeypatch.setenv("YUKI_ATOLYE_SESSIZ", "25-99")
    assert gb.sessiz_aralik() == (23, 8)


def test_sessiz_saat_gece_yarisini_asar():
    assert gb.sessiz_mi(datetime(2026, 1, 1, 23, 30), (23, 8))
    assert gb.sessiz_mi(datetime(2026, 1, 1, 7, 59), (23, 8))
    assert not gb.sessiz_mi(datetime(2026, 1, 1, 8, 0), (23, 8))
    assert gb.sessiz_mi(datetime(2026, 1, 1, 14, 0), (13, 15))
    assert not gb.sessiz_mi(datetime(2026, 1, 1, 12, 0), (9, 9))


def test_gonderim_hatasi_yutulur():
    k = gb.BitisBildirimi(Kayit(hata=OSError("ağ yok")))
    _calistir(k, ("site/a", {"durum": "bitti", "tur": "site"}))     # istisna yükselmez


def test_dongu_yoksa_sessiz_gecer():
    g = Kayit()
    gb.BitisBildirimi(g)("site/a", {"durum": "bitti", "tur": "site"})
    assert g.giden == []


@pytest.mark.asyncio
async def test_gercek_servis_bitince_bir_kez_bildirir(tmp_path):
    g = Kayit()
    servis = GorevServisi(tmp_path / "atolye")
    kanca = gb.BitisBildirimi(g)
    servis.bitis_kancasi_ekle(kanca)
    llm = SahteLLM([_icerik_akisi("tamam")])
    with patch("app.services.llm_router.get_router", return_value=llm.router()), yerel_baglam():
        await servis.baslat("deneme", "bildirim", "bir şey yap")
        await servis.bekle("deneme/bildirim", 5)
    for _ in range(100):
        if g.giden:
            break
        await asyncio.sleep(0.01)
    assert servis._oku("deneme/bildirim")["durum"] == "bitti"
    assert len(g.giden) == 1 and "bitti" in g.giden[0][1]


def test_uretim_servisi_kancayi_baglar(tmp_path, monkeypatch):
    monkeypatch.setattr(gorev_mod, "_servis", None)
    monkeypatch.setattr(gorev_mod, "_varsayilan_kok", lambda: tmp_path / "atolye")
    s = gorev_mod.get_gorev_servisi()
    try:
        assert any(isinstance(k, gb.BitisBildirimi) for k in s._bitis_kancalari)
    finally:
        monkeypatch.setattr(gorev_mod, "_servis", None)
