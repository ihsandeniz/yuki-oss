"""Tek karakter: Yuki dışındaki karakterler kaldırıldı (ürün kararı 2026-11-14).

Karar: *"Yuki dışındaki karakterleri kaldır, onlar olmayacak; ileride başka
karakterler ekleriz belki."* Bu yüzden iki şey birlikte ölçülür:

  ① Bugün: kayıtta yalnız Yuki var, uzman ekibi YOK → ekip araçları LLM'e
     sunulmaz (olmayan yeteneği vaat etmek = kullanıcıya vaat etmek), model yine
     de çağırırsa düzgün "ekip yok" döner, AJAN sekmesi boş kadro görür.
  ② Yarın: kayda bir persona eklenince aynı araçlar KENDİLİĞİNDEN geri gelir —
     ayrı bir anahtar/liste güncellemesi gerekmez (monkeypatch ile ölçülür).
"""
import asyncio

from app.services import orchestrator as orch
from app.services import personas


def _sunulan() -> dict[str, dict]:
    from app.services.tools import get_active_tools
    return {t["function"]["name"]: t for t in get_active_tools()}


# ── ① bugün: yalnız Yuki ────────────────────────────────────────────────
def test_kayitta_yalniz_yuki():
    assert list(personas.PERSONAS) == ["yuki"]
    assert [p["name"] for p in personas.list_personas()] == ["yuki"]
    assert personas.uzman_anahtarlari() == []


def test_kaldirilan_karakterlere_gecilemez():
    # Adlar kodda geçmesin diye sabit yazılmadı: herhangi bir yabancı ad reddedilir.
    assert personas.set_persona("olmayan_karakter") is False
    assert personas.get_persona() == "yuki"


def test_uzman_yokken_ekip_araclari_sunulmaz():
    adlar = set(_sunulan())
    assert not (orch.EKIP_ARACLARI & adlar), f"uzman yok ama sunuluyor: {orch.EKIP_ARACLARI & adlar}"
    assert "switch_character" in adlar  # kayıt yapısı duruyor


def test_uzman_yokken_ekip_araclari_ekip_yok_doner():
    """Model listede olmayan aracı uydurup çağırabilir — çağrı da düzgün cevap vermeli."""
    from app.services.tools import call_tool
    tekli = asyncio.run(call_tool("delegate_to_companion", {"persona": "x", "subtask": "ara"}))
    meclis = asyncio.run(call_tool("run_team", {"goal": "araştır"}))
    dogrudan = asyncio.run(orch.delegate_to_persona("x", "ara"))
    for cikti in (tekli, meclis, dogrudan):
        assert cikti == orch.ekip_yok_metni(), cikti


def test_uzman_yokken_olay_yayinlanmaz(monkeypatch):
    """AJAN sekmesinde hayalet 'çalışıyor' kartı çıkmasın."""
    from app.services.event_bus import bus
    yayin: list = []

    async def _kaydet(konu, veri):
        yayin.append(konu)
    monkeypatch.setattr(bus, "publish", _kaydet)
    asyncio.run(orch.companion_delegate("x", "ara"))
    asyncio.run(orch.run_team("hedef"))
    assert yayin == []


def test_ajan_ekip_ucu_bos_kadro():
    from fastapi.testclient import TestClient
    from app.main import app
    e = TestClient(app).get("/api/ajan/ekip").json()
    assert e["uzmanlar"] == []
    assert e["koordinator"]["name"] == "yuki"


def test_karakter_ucu_yalniz_yuki():
    from fastapi.testclient import TestClient
    from app.main import app
    d = TestClient(app).get("/api/character").json()
    assert [p["name"] for p in d["available"]] == ["yuki"]


# ── ② yarın: persona eklenince kendiliğinden geri gelir ──────────────────
def test_persona_eklenince_ekip_araclari_geri_gelir(test_ekibi):
    s = _sunulan()
    assert orch.EKIP_ARACLARI <= set(s)
    enum = s["delegate_to_companion"]["function"]["parameters"]["properties"]["persona"]["enum"]
    assert enum == test_ekibi, "uzman listesi canlı PERSONAS'tan gelmiyor"
    assert "yuki" not in enum, "koordinatör kendine delege edilemez"
    aciklama = s["delegate_to_companion"]["function"]["description"]
    assert "{uzmanlar}" not in aciklama and test_ekibi[0] in aciklama


def test_sema_kopyasi_global_toolsu_bozmaz(test_ekibi):
    from app.services.tools.dispatcher import TOOLS
    _sunulan()
    ham = next(t for t in TOOLS if t["function"]["name"] == "delegate_to_companion")
    assert ham["function"]["parameters"]["properties"]["persona"]["enum"] == []


def test_persona_eklenince_karaktere_gecilir(test_ekibi):
    from app.services.tools.ui_tools import _karakter_anahtari
    assert _karakter_anahtari(test_ekibi[0].upper()) == test_ekibi[0]
    assert _karakter_anahtari("olmayan_karakter") is None
