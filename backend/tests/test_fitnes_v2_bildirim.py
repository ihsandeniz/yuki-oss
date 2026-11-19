"""Fitnes v2 — bildirim teslimi (P4). Gerçek push YOK: sahte yürütücü (gonder/kaydet) verilir.

Korunan şeyler:
  ① günlük tavan 5, rekor tavanı 3 → taşan "bekleyen"
  ② sessiz saatte / push kapalıyken / geçmiş tarihli olayda push yok, kart var
  ③ aynı olay iki kez itilmez (itildi damgası gönderimden ÖNCE yazılır)
  ④ gönderim hata verse de olay kartta kalır, damga geri alınmaz
  ⑤ 21:00 hatırlatma ayarla kapanır
  ⑥ zamanlayıcıya 3 iş + açılış telafisi eklenir
"""
import asyncio
from datetime import date, datetime, timedelta

import pytest

from app.services import fitnes_bildirim as B

AN = datetime.now().replace(hour=12, minute=0, second=0, microsecond=0)   # bugün öğlen (tavan "bugün"ü sayar)
BUGUN = AN.date().isoformat()
DUN2 = (AN.date() - timedelta(days=2)).isoformat()
PZT = (AN.date() - timedelta(days=AN.weekday() + 7)).isoformat()


def _o(tur, tarih=None, **k):
    tarih = tarih or BUGUN
    return {"tur": tur, "anahtar": f"{tur}:{tarih}", "veri": {"tarih": tarih}, **k}


def test_tavanlar():
    assert B.teslim_karari(_o("BECERI"), AN, 5).teslim == "bekleyen"
    assert B.teslim_karari(_o("REKOR"), AN, 0, bugun_rekor=3).teslim == "bekleyen"
    assert B.teslim_karari(_o("EVRIM"), AN, 9).teslim == "ozet", "özet satırı tavana takılmaz"


def test_push_kosullari():
    assert B.teslim_karari(_o("SEVIYE"), AN, 0).push is True
    assert B.teslim_karari(_o("SEVIYE"), AN.replace(hour=23, minute=30), 0).push is False
    assert B.teslim_karari(_o("SEVIYE"), AN, 0, ayar={"push": False}).teslim == "kart"
    assert B.teslim_karari(_o("REKOR", DUN2), AN, 0).neden == "geçmiş tarihli"
    assert B.teslim_karari(_o("HAFTALIK_OZET", PZT), AN, 0).push is True, "kaçan özet yine gider"
    assert B.sessiz_mi(datetime(2026, 1, 1, 7), (23, 8)) and not B.sessiz_mi(datetime(2026, 1, 1, 8), (23, 8))


@pytest.fixture()
def depo(tmp_path, monkeypatch):
    from app.services import fitness_store as fs
    monkeypatch.setattr(fs, "_STORE_FILE", tmp_path / "fitness_store.json")
    return fs


def _olay(depo, tur, tarih=None):
    tarih = tarih or BUGUN
    from app.services import fitness_oyun as F
    with depo.islem() as db:
        F.olay_yaz(db, f"{tur}:{tarih}", tur, f"{tur} oldu", {"tarih": tarih})


class _Sahte:
    def __init__(self, hata=False):
        self.giden, self.hata = [], hata

    async def gonder(self, baslik, govde, url):
        self.giden.append(govde)
        if self.hata:
            raise RuntimeError("ağ yok")
        return 1

    async def kaydet(self, metin, telefon):
        pass


def test_ilet_bir_kez_iter(depo):
    _olay(depo, "SEVIYE")
    _olay(depo, "BECERI")
    s = _Sahte()
    sonuc = asyncio.run(B.ilet(AN, s.gonder, s.kaydet))
    assert {r["tur"]: r["teslim"] for r in sonuc} == {"SEVIYE": "anlik", "BECERI": "kart"}
    assert s.giden == ["SEVIYE oldu"]
    assert asyncio.run(B.ilet(AN, s.gonder, s.kaydet)) == [] and s.giden == ["SEVIYE oldu"]
    assert B.bugun_sayilan(depo._load(), AN.date()) == 2


def test_gonderim_hatasinda_damga_kalir(depo):
    _olay(depo, "UYANIS")
    s = _Sahte(hata=True)
    asyncio.run(B.ilet(AN, s.gonder, s.kaydet))
    o = depo._load()["olaylar"][0]
    assert o["itildi"] and o["teslim"] == "anlik"
    asyncio.run(B.ilet(AN, s.gonder, s.kaydet))
    assert len(s.giden) == 1, "hata sonrası tekrar itilmez"


def test_hatirlatma_ayarla_kapanir(depo):
    s = _Sahte()
    akşam = AN.replace(hour=21)
    depo.cfg_yaz("bildirim", {"hatirlatma": False})
    assert asyncio.run(B.hatirlatma(akşam, s.gonder, s.kaydet)) == []
    depo.cfg_yaz("bildirim", {"hatirlatma": True, "sessiz": [23, 8]})
    sonuc = asyncio.run(B.hatirlatma(akşam, s.gonder, s.kaydet))
    assert [r["tur"] for r in sonuc] == ["HATIRLATMA"] and s.giden and "görev açık" in s.giden[0]


def test_zamanlayici_isleri():
    class _Sched:
        def __init__(self):
            self.isler = {}

        def get_job(self, i):
            return self.isler.get(i)

        def add_job(self, fn, trigger, id, replace_existing=False, **kw):
            self.isler[id] = (fn, trigger, kw)

    sc = _Sched()
    B.zamanlayiciya_ekle(sc, AN)
    assert set(sc.isler) == {"fitnes_hatirlatma", "fitnes_lig", "fitnes_haftalik", "fitnes_haftalik_telafi"}
    assert sc.isler["fitnes_haftalik"][2] == {"day_of_week": "mon", "hour": 8, "minute": 30}


def test_damgali_olay_teslimsiz_kalsa_da_yeniden_itilmez(depo):
    """`itildi` damgası tek başına da korur: teslim kararı yazılmamış (eski kayıt, yarıda kalmış geçiş)
    ama damgası olan olay ikinci kez telefona gitmez — mutasyon turunda bu kapının yalnız
    `teslim is None` süzgecine yaslandığı görüldü (G3)."""
    _olay(depo, "UYANIS")
    with depo.islem() as db:
        db["olaylar"][0]["itildi"] = "2026-01-01T09:00:00+03:00"
    s = _Sahte()
    asyncio.run(B.ilet(AN, s.gonder, s.kaydet))
    assert s.giden == [], "damgalı olay yeniden itildi"
    assert depo._load()["olaylar"][0]["teslim"] == "anlik"
