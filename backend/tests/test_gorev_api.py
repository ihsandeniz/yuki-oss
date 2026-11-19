"""Atölye görev uçları — Faz 0c .

  · /api/gorev* AUTH_TOKEN ister (main.py ara katmanı; muafiyet yok)
  · DURDUR her bağlamdan açık; DEVAM dış bağlamdan (tünel/telefon başlıkları) 403
  · DEVAM gövdesinde onay yoksa reddedilir (karar 3)
  · her kayıt yazımı `gorev` olayını yayınlar ve olay WS'in dinlediği konulardadır
LLM sahte, atölye kökü geçici dizin. Lifespan koşmaz (DB/servis açılmaz).
"""
import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from starlette.testclient import TestClient

from app import main as main_mod
from app.services import gorev as gorev_mod
from app.services.event_bus import _ALL_TOPICS, bus
from app.services.gorev import GorevServisi
from app.services.atolye.baglam import yerel_baglam
from tests.atolye_yardimci import _arac_akisi, _icerik_akisi

pytestmark = pytest.mark.usefixtures("atolye_acik")   # `ATOLYE` varsayılan kapalı → uçlar 404

TOKEN = "test-anahtari-0c"
YETKI = {"Authorization": f"Bearer {TOKEN}"}
DIS = {**YETKI, "X-Forwarded-For": "100.64.0.9"}


def _router(yanitlar):
    client = MagicMock()
    client.chat.completions.create = AsyncMock(side_effect=yanitlar)
    r = MagicMock()
    r.get_client = AsyncMock(return_value=(client, "gpt-5.6-luna"))
    return r


@pytest.fixture
def servis(tmp_path):
    s = GorevServisi(tmp_path / "atolye")
    with patch.object(gorev_mod, "_servis", s), patch.object(main_mod, "AUTH_TOKEN", TOKEN):
        yield s


@pytest.fixture
def istemci(servis):
    # `with` YOK → lifespan koşmaz. base_url localhost: "testserver" güvenilir yerel ad değil → dış sayılır.
    return TestClient(main_mod.app, base_url="http://localhost:8001", client=("127.0.0.1", 50000))


def _durdu_gorev(servis):
    """Bir görevi başlatıp 2. adımda (LLM asılıyken) durdurur → durdu, adım 1."""
    cagri = {"n": 0}

    async def _create(**kw):
        cagri["n"] += 1
        if cagri["n"] == 1:
            return _arac_akisi([("c0", "alan_yaz", {"yol": "a.txt", "icerik": "x"})])
        await asyncio.sleep(60)

    async def _kos():
        r = _router(None)
        r.get_client.return_value[0].chat.completions.create = AsyncMock(side_effect=_create)
        with patch("app.services.llm_router.get_router", return_value=r), yerel_baglam():
            await servis.baslat("deneme", "api", "yap")
            for _ in range(300):
                if cagri["n"] >= 2:
                    break
                await asyncio.sleep(0.01)
            await servis.durdur("deneme/api")
    asyncio.run(_kos())


def test_tokensiz_istek_401(istemci):
    assert istemci.get("/api/gorev").status_code == 401
    assert istemci.post("/api/gorev/deneme/x/durdur").status_code == 401
    assert istemci.post("/api/gorev/deneme/x/devam", json={"onay": True}).status_code == 401


def test_liste_kisa_gorunum_ic_metin_sizmaz(istemci, servis):
    _durdu_gorev(servis)
    r = istemci.get("/api/gorev", headers=YETKI)
    assert r.status_code == 200
    g = r.json()["gorevler"][0]
    assert set(g) == {"id", "tur", "ad", "durum", "neden", "adim", "adim_tavani", "guncelleme",
                      "kaynak", "onay_son", "alan", "tavanlar",           # Faz 0d: onay ekranı alanları
                      "dogrulama",                                       # Faz 1: hüküm özeti (metin değil)
                      "son_nabiz"}                                       # Harness H2: yalnız zaman
    assert g["dogrulama"] is None
    assert (g["id"], g["durum"], g["adim"], g["adim_tavani"]) == ("deneme/api", "durdu", 1, 10)
    assert g["kaynak"] == "yerel" and g["alan"].endswith("/deneme/api/")
    assert set(g["tavanlar"]) == {"adim", "sure_sn", "token"}


def test_dis_baglamdan_devam_403_durdur_acik(istemci, servis):
    _durdu_gorev(servis)
    r = istemci.post("/api/gorev/deneme/api/devam", json={"onay": True}, headers=DIS)
    assert r.status_code == 403 and "dış bağlam" in r.json()["detail"]
    assert servis.durum("deneme/api")["durum"] == "durdu"
    r = istemci.post("/api/gorev/deneme/api/durdur", headers=DIS)
    assert r.status_code == 200 and r.json()["durum"] == "durdu"


def test_onaysiz_devam_reddedilir(istemci, servis):
    _durdu_gorev(servis)
    for govde in ({}, {"onay": False}):
        r = istemci.post("/api/gorev/deneme/api/devam", json=govde, headers=YETKI)
        assert r.status_code == 400 and "onay" in r.json()["detail"]
    assert servis.durum("deneme/api")["durum"] == "durdu"


def test_yerel_onayli_devam_kosar(istemci, servis):
    _durdu_gorev(servis)
    r = _router([_icerik_akisi("bitti")])
    with patch("app.services.llm_router.get_router", return_value=r):
        cevap = istemci.post("/api/gorev/deneme/api/devam", json={"onay": True}, headers=YETKI)
    assert cevap.status_code == 200 and cevap.json()["durum"] == "kosuyor"


@pytest.mark.parametrize("yol", ["/api/gorev/deneme/..%2F..%2Fetc/durdur", "/api/gorev/yok/x/durdur",
                                 "/api/gorev/deneme/A/durdur"])
def test_gecersiz_kimlik_400(istemci, yol):
    assert istemci.post(yol, headers=YETKI).status_code in (400, 404)


def test_baslatma_ucu_yok(istemci):
    """Başlatma `POST /api/gorev/baslat`'tadır (Faz 0d); koleksiyona POST yok."""
    assert istemci.post("/api/gorev", json={"tur": "site", "ad": "x"}, headers=YETKI).status_code in (404, 405)


def test_gorev_konusu_ws_aboneliginde():
    assert "gorev" in _ALL_TOPICS


@pytest.mark.asyncio
async def test_her_kayit_gorev_olayi_yayinlar(tmp_path):
    q = bus.subscribe_all()
    try:
        servis = GorevServisi(tmp_path / "k")
        r = _router([_arac_akisi([("c0", "alan_yaz", {"yol": "a.txt", "icerik": "x"})]),
                     _icerik_akisi("son")])
        with patch("app.services.llm_router.get_router", return_value=r), yerel_baglam():
            await servis.baslat("deneme", "olay", "Luna için GİZLİ istek metni")
            await servis.bekle("deneme/olay", 5)
        await asyncio.sleep(0.05)
        olaylar = []
        while not q.empty():
            o = q.get_nowait()
            if o.get("type") == "gorev":
                olaylar.append(o)
    finally:
        bus.unsubscribe_all(q)
    assert [(o["durum"], o["adim"]) for o in olaylar] == [("kosuyor", 0), ("kosuyor", 1), ("bitti", 2)]
    assert all("GİZLİ" not in str(o) for o in olaylar), "istek metni olaya sızdı"
