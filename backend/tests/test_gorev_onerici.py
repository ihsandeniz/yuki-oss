"""Atölye öneri motoru (`gorev_onerici`).

Kabul ölçüleri:
  · motor görev servisini/kuyruğu içe aktarmaz (AST) ve yalnız `oneri` kaydı yazar
  · üç kaynak: Plan listesi (tür sezgisi), yarım kalan iş (son 48 sa), tekrar eden iş (≥3)
  · korkuluklar: günlük tavan, açık öneri tavanı, susturma (red 7 gün / düşme 1 gün),
    pencere dışı, TÜMÜNÜ DURDUR, bozuk defter
  · bildirim: sessiz saat, aralık, kapalı ayar; metin öneri içeriğini taşımaz
  · gerçek kuyrukla: yarım iş önerisi açılır, görev KENDİLİĞİNDEN BAŞLAMAZ
Atölye kökü pytest'in geçici dizini; push sahte.
"""
import ast
import asyncio
import json
import time
from datetime import datetime
from pathlib import Path
from unittest.mock import patch

import pytest
from starlette.testclient import TestClient

from app import main as main_mod
from app.services import gorev as gorev_mod
from app.services import gorev_kapilari as kapi_mod
from app.services import gorev_onerici as om
from app.services.gorev import GorevServisi
from app.services.gorev_kuyrugu import GorevKuyrugu
from tests.atolye_yardimci import dis_origin_izni

pytestmark = pytest.mark.usefixtures("atolye_acik")

BACKEND = Path(__file__).resolve().parents[1]
SIMDI = time.mktime((2026, 11, 12, 14, 0, 0, 0, 0, -1))      # gündüz, pencere içinde
ANAHTAR = "ornek-test-anahtari-oneri"                        # ÖRNEK — yalnız bu süreçte
YETKI = {"Authorization": f"Bearer {ANAHTAR}"}


def _ts(sn_once: float) -> str:
    return time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(SIMDI - sn_once))


@pytest.fixture(autouse=True)
def _saat(monkeypatch):
    monkeypatch.setattr(om, "_zaman", lambda: SIMDI)
    monkeypatch.setattr(kapi_mod, "pencerede_mi", lambda ts: True)
    for ad in ("GUNLUK", "BILDIRIM", "BILDIRIM_DK", "KAYNAKLAR", "PLAN_LISTE"):
        monkeypatch.delenv(f"YUKI_ATOLYE_ONERI_{ad}", raising=False)
    monkeypatch.delenv("YUKI_ATOLYE_SESSIZ", raising=False)


class Sahte:
    """Bellek içi kuyruk + push kaydı."""

    def __init__(self, gorevler=None, plan=None, kayitlar=None):
        self.kayitlar = list(kayitlar or [])
        self.gorevler = list(gorevler or [])
        self.plan = list(plan or [])
        self.giden: list[tuple] = []
        self.plan_sorulan: list[str] = []

    def oner(self, tur, ad, istek, **kw):
        k = {"id": f"q{len(self.kayitlar) + 1}", "tur": tur, "ad": ad, "istek": istek,
             "durum": "oneri", **kw}
        self.kayitlar.append(k)
        return k

    async def plan_oku(self, liste):
        self.plan_sorulan.append(liste)
        return self.plan

    async def gonder(self, baslik, govde, url):
        self.giden.append((baslik, govde, url))
        return 1

    def motor(self, kok, **kw):
        return om.OneriMotoru(kok, oner=self.oner, kuyruk_liste=lambda: self.kayitlar,
                              gorev_liste=lambda: self.gorevler, plan_oku=self.plan_oku,
                              gonder=self.gonder, **kw)


def _bitti(i, istek="hava durumu sitesi için yeni sayfa tasarla", tur="site"):
    return {"id": f"{tur}/is-{i}", "tur": tur, "durum": "bitti", "istek": istek,
            "guncelleme": _ts(3600 * (10 - i))}


# ── yapı ─────────────────────────────────────────────────────────────────

def test_motor_gorev_servisini_ice_aktarmaz():
    agac = ast.parse((BACKEND / "app/services/gorev_onerici.py").read_text(encoding="utf-8"))
    adlar = set()
    for n in ast.walk(agac):
        if isinstance(n, ast.Import):
            adlar |= {a.name for a in n.names}
        elif isinstance(n, ast.ImportFrom):
            adlar.add(n.module or "")
            adlar |= {f"{n.module}.{a.name}" for a in n.names}
    yasak = {a for a in adlar if a.endswith((".gorev", ".gorev_kuyrugu"))}
    assert not yasak, yasak


# ── kaynaklar ────────────────────────────────────────────────────────────

def test_plan_tur_sezgisi_uymayani_atlar():
    a = om.plan_adaylari([{"id": "1", "baslik": "Elektrikli arabaları araştır"},
                          {"id": "2", "baslik": "Ekmek al"},
                          {"id": "3", "baslik": "Kafe için landing sayfa"},
                          {"baslik": "kimliksiz araştır"}])
    assert [(x.tur, x.kaynak_ref) for x in a] == [("arastirma", "todo:1"), ("site", "todo:3")]
    assert a[0].ad == "elektrikli-arabalari-arastir"


def test_yarim_yalniz_kendiliginden_duran_ve_taze():
    g = [{"id": "site/a", "durum": "durdu", "neden": "yeniden_baslatma", "guncelleme": _ts(60)},
         {"id": "site/b", "durum": "durdu", "neden": "kullanici", "guncelleme": _ts(60)},
         {"id": "site/c", "durum": "durdu", "neden": "kota", "guncelleme": _ts(49 * 3600)},
         {"id": "site/d", "durum": "bitti", "neden": None, "guncelleme": _ts(60)},
         {"id": "site/e", "durum": "durdu", "neden": "gece", "guncelleme": "bozuk"}]
    a = om.yarim_adaylari(g, SIMDI)
    assert [(x.devam_gid, x.oncelik, x.kaynak) for x in a] == [("site/a", 1, "yarim")]


def test_rutin_uc_benzer_bitis_ister():
    assert om.rutin_adaylari([_bitti(1), _bitti(2)]) == []
    a = om.rutin_adaylari([_bitti(1), _bitti(2), _bitti(3),
                           _bitti(4, "kuantum bilgisayarları araştır özetle", "arastirma")])
    assert len(a) == 1 and a[0].tur == "site" and a[0].kaynak == "rutin" and a[0].ad == "is-3"


def test_bozuk_ayar_varsayilana_duser(monkeypatch):
    monkeypatch.setenv("YUKI_ATOLYE_ONERI_GUNLUK", "çok")
    monkeypatch.setenv("YUKI_ATOLYE_SESSIZ", "25-99")
    monkeypatch.setenv("YUKI_ATOLYE_ONERI_KAYNAKLAR", "plan,takvim")
    a = om.ayarlar()
    assert (a["gunluk"], a["sessiz"], a["kaynaklar"]) == (3, (23, 8), ("plan",))


# ── motor korkulukları ───────────────────────────────────────────────────

def test_tur_oneri_yazar_ve_bildirir(tmp_path):
    s = Sahte(plan=[{"id": "7", "baslik": "Gizli proje X'i araştır"}])
    r = asyncio.run(s.motor(tmp_path).tur())
    assert r["yazilan"] == ["q1"] and r["bildirim"] == 1
    assert s.kayitlar[0]["kaynak"] == "plan" and s.kayitlar[0]["durum"] == "oneri"
    assert s.plan_sorulan == ["Yuki"]
    baslik, govde, url = s.giden[0]
    assert "Gizli" not in govde and "proje" not in govde      # içerik kilit ekranına çıkmaz
    assert url == "/ui/index.html#atolye-oneri=q1"


def test_gunluk_tavan(tmp_path, monkeypatch):
    monkeypatch.setenv("YUKI_ATOLYE_ONERI_GUNLUK", "2")
    plan = [{"id": str(i), "baslik": f"konu {i} araştır"} for i in range(5)]
    s = Sahte(plan=plan)
    r = asyncio.run(s.motor(tmp_path).tur())
    assert len(r["yazilan"]) == 2 and r["atlanan"]["gunluk"] == 3
    s.kayitlar.clear()                       # açık tavanı engel olmasın; defter yine 2 der
    r2 = asyncio.run(s.motor(tmp_path).tur())
    assert r2["yazilan"] == [] and r2["atlanan"]["gunluk"] == 5


def test_acik_oneri_tavani(tmp_path):
    acik = [{"id": f"x{i}", "durum": "oneri", "kaynak_ref": f"eski:{i}"} for i in range(3)]
    s = Sahte(plan=[{"id": "9", "baslik": "yeni konu araştır"}], kayitlar=acik)
    r = asyncio.run(s.motor(tmp_path).tur())
    assert r["yazilan"] == [] and r["atlanan"] == {"acik": 1}


def test_red_yedi_gun_susar_sonra_serbest(tmp_path):
    red = {"id": "x", "durum": "reddedildi", "kaynak_ref": "todo:5", "red_zaman": SIMDI - 6 * 86400}
    s = Sahte(plan=[{"id": "5", "baslik": "bunu araştır"}], kayitlar=[red])
    assert asyncio.run(s.motor(tmp_path).tur())["atlanan"] == {"susturuldu": 1}
    red["red_zaman"] = SIMDI - 8 * 86400
    assert asyncio.run(s.motor(tmp_path).tur())["yazilan"] == ["q2"]


def test_dusen_bir_gun_susar(tmp_path):
    d = {"id": "x", "durum": "dustu", "kaynak_ref": "todo:5", "son_gecerlilik": SIMDI - 3600}
    s = Sahte(plan=[{"id": "5", "baslik": "bunu araştır"}], kayitlar=[d])
    assert asyncio.run(s.motor(tmp_path).tur())["yazilan"] == []
    d["son_gecerlilik"] = SIMDI - 25 * 3600
    assert len(asyncio.run(s.motor(tmp_path).tur())["yazilan"]) == 1


def test_suren_isin_yarim_onerisi_acilmaz(tmp_path):
    g = [{"id": "site/a", "durum": "durdu", "neden": "gece", "guncelleme": _ts(60)}]
    s = Sahte(gorevler=g, kayitlar=[{"id": "x", "durum": "sirada", "devam_gid": "site/a",
                                     "kaynak_ref": "baska"}])
    assert asyncio.run(s.motor(tmp_path).tur())["atlanan"] == {"susturuldu": 1}


def test_pencere_disi_ve_tumunu_durdur_hicbir_sey_yazmaz(tmp_path, monkeypatch):
    s = Sahte(plan=[{"id": "1", "baslik": "araştır"}])
    assert asyncio.run(s.motor(tmp_path, kapali=lambda: True).tur())["atlanan"] == {"tumunu_durdur": 1}
    monkeypatch.setattr(kapi_mod, "pencerede_mi", lambda ts: False)
    assert asyncio.run(s.motor(tmp_path).tur())["atlanan"] == {"pencere": 1}
    assert s.kayitlar == [] and s.giden == []


def test_bozuk_defter_bugun_dolu_sayilir_ve_ezilmez(tmp_path):
    defter = tmp_path / ".kuyruk" / "onerici.json"
    defter.parent.mkdir(parents=True)
    defter.write_text("{bozuk", encoding="utf-8")
    s = Sahte(plan=[{"id": "1", "baslik": "araştır"}])
    r = asyncio.run(s.motor(tmp_path).tur())
    assert r["yazilan"] == [] and r["atlanan"] == {"gunluk": 1}
    assert defter.read_text(encoding="utf-8") == "{bozuk"


def test_plan_hatasi_turu_bozmaz(tmp_path):
    s = Sahte(gorevler=[{"id": "site/a", "durum": "durdu", "neden": "gece", "guncelleme": _ts(60)}])

    async def patla(_):
        raise RuntimeError("db yok")
    m = s.motor(tmp_path)
    m.plan_oku = patla
    assert len(asyncio.run(m.tur())["yazilan"]) == 1


# ── bildirim ─────────────────────────────────────────────────────────────

def test_bildirim_kapali_sessiz_aralik(tmp_path, monkeypatch):
    plan = [{"id": str(i), "baslik": f"konu {i} araştır"} for i in range(3)]
    monkeypatch.setenv("YUKI_ATOLYE_ONERI_BILDIRIM", "0")
    s = Sahte(plan=plan[:1])
    assert asyncio.run(s.motor(tmp_path / "a").tur())["bildirim"] == 0 and s.giden == []

    monkeypatch.delenv("YUKI_ATOLYE_ONERI_BILDIRIM")
    monkeypatch.setenv("YUKI_ATOLYE_SESSIZ", "13-15")      # SIMDI 14:00
    s = Sahte(plan=plan[:1])
    assert asyncio.run(s.motor(tmp_path / "b").tur())["bildirim"] == 0 and s.giden == []

    monkeypatch.delenv("YUKI_ATOLYE_SESSIZ")
    s = Sahte(plan=plan[:1])
    assert asyncio.run(s.motor(tmp_path / "c").tur())["bildirim"] == 1
    s.plan = plan[1:2]
    assert asyncio.run(s.motor(tmp_path / "c").tur())["bildirim"] == 0     # 120 dk dolmadı
    assert len(s.giden) == 1
    assert json.loads((tmp_path / "c/.kuyruk/onerici.json").read_text())["son_bildirim"] == SIMDI


def test_gonderim_hatasi_turu_bozmaz(tmp_path):
    s = Sahte(plan=[{"id": "1", "baslik": "araştır"}])

    async def patla(*a):
        raise OSError("ağ yok")
    m = s.motor(tmp_path)
    m.gonder = patla
    r = asyncio.run(m.tur())
    assert r["yazilan"] == ["q1"] and r["bildirim"] == 0


# ── gerçek kuyrukla ──────────────────────────────────────────────────────

def _durdu_alan(kok: Path, gid: str, neden: str) -> None:
    tur, ad = gid.split("/")
    d = kok / tur / ad / ".gorev"
    d.mkdir(parents=True)
    (d / "durum.json").write_text(json.dumps({
        "id": gid, "tur": tur, "ad": ad, "istek": "bir sayfa yap", "durum": "durdu",
        "neden": neden, "adim": 2, "guncelleme": _ts(120), "kaynak": "yerel",
        "olusturma": _ts(600)}), encoding="utf-8")


def test_gercek_kuyruk_yarim_oneri_acilir_gorev_baslamaz(tmp_path):
    kok = tmp_path / "atolye"
    _durdu_alan(kok, "site/yarim-is", "yeniden_baslatma")
    servis = GorevServisi(kok)
    kuyruk = GorevKuyrugu(servis)
    s = Sahte()
    r = asyncio.run(kuyruk.oneri_motoru(plan_oku=s.plan_oku, gonder=s.gonder).tur())
    assert len(r["yazilan"]) == 1
    k = kuyruk.liste()[0]
    assert (k["durum"], k["kaynak"], k.get("devam_gid")) == ("oneri", "yarim", "site/yarim-is")
    assert servis._oku("site/yarim-is")["durum"] == "durdu"          # kendiliğinden sürmedi
    # ikinci tur aynı öneriyi yeniden açmaz
    assert asyncio.run(kuyruk.oneri_motoru(plan_oku=s.plan_oku, gonder=s.gonder).tur())["yazilan"] == []


# ── uç ───────────────────────────────────────────────────────────────────

@pytest.fixture
def istemci(tmp_path, monkeypatch):
    async def bos(_):
        return []
    monkeypatch.setattr(om, "plan_listesi_oku", bos)
    s = GorevServisi(tmp_path / "atolye")
    with patch.object(gorev_mod, "_servis", s), patch.object(main_mod, "AUTH_TOKEN", ANAHTAR):
        yield TestClient(main_mod.app, base_url="http://localhost:8001", client=("127.0.0.1", 50000))


def test_tur_ucu_yerelde_calisir_disaridan_403(istemci, monkeypatch):
    ts = "https://yuki.ornek.example"
    dis_origin_izni(monkeypatch, ts)        # Origin kapısı geçse de tur ucu dışarıya kapalı
    r = istemci.post("/api/gorev/oneri/tur", headers=YETKI)
    assert r.status_code == 200, r.text
    assert r.json()["yazilan"] == []
    r = istemci.post("/api/gorev/oneri/tur", headers={**YETKI, "X-Forwarded-For": "100.64.0.9", "Origin": ts})
    assert r.status_code == 403
    assert "bilgisayardan" in r.json()["detail"]
