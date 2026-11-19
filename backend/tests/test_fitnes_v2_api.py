"""Fitnes v2 — HTTP uçları (P3). Gerçek istek: bayrak + PLAN kapısı + uç + depo + motor zinciri.

Korunan şeyler (uç başına bir davranış):
  ① bayrak kapalıyken yeni uçlar da 404
  ② şablon güne tek istekte yüklenir; aynı gün ikinci kez 409, `yine=1` ile geçer
  ③ yüklenen set öneridir: xp 0; dokunulunca (girildi) sayılır, rekor olayı doğar (arka plan)
  ④ bitir: yalnız onaylanan set completed olur; dokunulmamış liste döner; süre sunucuda
  ⑤ en-iyi / onceki / ozet doğru günü ve seti seçer
  ⑥ hazır şablon kopyası kararlı kimlikle yazılır, silinince hazır geri gelir
  ⑦ ayar uçları bozuk girdiyi kırpar/atar, kısmi PUT kayıtlı değeri korur
  ⑧ drop doğrulaması 400, geçersiz tarih 400
"""
from datetime import date, timedelta

import pytest
from httpx import ASGITransport, AsyncClient

pytestmark = pytest.mark.usefixtures("fitnes_acik")

GUN = "2026-11-09"
HAZIR = {"ad": "Bacak Günü", "exercises": [{"name": "Squat", "sets": [{"reps": 5, "weight": 100}] * 3}]}


@pytest.fixture()
async def c(tmp_path, monkeypatch):
    from app.api.todo import require_planner
    from app.main import app
    from app.services import fitness_store as fs
    monkeypatch.setattr(fs, "_STORE_FILE", tmp_path / "fitness_store.json")
    app.dependency_overrides[require_planner] = lambda: None
    try:
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://127.0.0.1") as ac:
            yield ac
    finally:
        app.dependency_overrides.pop(require_planner, None)


async def test_bayrak_kapaliyken_yeni_uclar_404(c, monkeypatch):
    import app.config as config
    monkeypatch.setattr(config, "FITNES", False)
    for yol in ("/api/fitness/durum", "/api/fitness/hafta-turu", "/api/fitness/ayar/hareket"):
        assert (await c.get(yol)).status_code == 404, yol


async def _yukle(c, yine=0):
    return await c.post(f"/api/fitness/templates/hazir-bacak/yukle?tarih={GUN}&yine={yine}", json=HAZIR)


async def test_sablon_yukle_tekrar_kilidi(c):
    r = await _yukle(c)
    assert r.status_code == 201 and len(r.json()["exercises"]) == 1
    r2 = await _yukle(c)
    assert r2.status_code == 409 and r2.json()["detail"] == {"zaten": 1}
    assert (await _yukle(c, yine=1)).status_code == 201
    w = (await c.get(f"/api/fitness/workouts?date={GUN}")).json()
    assert w["notes"] == "Bacak Günü" and len(w["exercises"]) == 2


async def test_oneri_seti_dokununca_sayilir_ve_rekor_dogar(c):
    ex = (await _yukle(c)).json()["exercises"][0]
    oz = (await c.get(f"/api/fitness/workouts/ozet?bas={GUN}&bit={GUN}")).json()
    assert oz[0]["yapilan"] == 0 and oz[0]["xp"] == 0, "dokunulmamış öneri sayılmamalı"
    s0 = ex["sets"][0]
    r = await c.put(f"/api/fitness/workouts/exercise/{ex['id']}/sets",
                    json={"sets": [{"id": s0["id"], "reps": 5, "weight": 100, "dokunuldu": True}]})
    assert r.status_code == 200 and r.json()["sets"][0]["girildi"]
    oz = (await c.get(f"/api/fitness/workouts/ozet?bas={GUN}&bit={GUN}")).json()
    assert oz[0]["yapilan"] == 1 and oz[0]["tonaj"] == 500 and oz[0]["pr"] == 1, "arka plan rekor olayı yazmalı"
    w = (await c.get(f"/api/fitness/workouts?date={GUN}")).json()
    assert w["exercises"][0]["rekor"] is True and w["baslangic"]


async def test_bitir_yalniz_onaylanani_sayar(c):
    ex = (await _yukle(c)).json()["exercises"][0]
    ids = [s["id"] for s in ex["sets"]]
    r = await c.post(f"/api/fitness/workouts/{GUN}/bitir", json={"onayla": ids[:1]})
    assert r.status_code == 200
    j = r.json()
    assert j["yapilan_set"] == 1 and len(j["dokunulmamis"]) == 2 and j["xp_gun"] > 0
    assert j["bitis"] and any(o["tur"] == "REKOR" for o in j["yeni_pr"])
    assert (await c.post(f"/api/fitness/workouts/{GUN}/ac")).json() == {"bitis": None}
    assert (await c.post("/api/fitness/workouts/2020-01-01/bitir", json={})).status_code == 404


async def test_basla_idempotent(c):
    a = (await c.post(f"/api/fitness/workouts/{GUN}/basla")).json()["baslangic"]
    b = (await c.post(f"/api/fitness/workouts/{GUN}/basla")).json()["baslangic"]
    assert a and a == b


async def test_en_iyi_ve_onceki(c):
    for gun, kg in (("2026-11-02", 100), ("2026-11-04", 90)):
        r = await c.post("/api/fitness/workouts/exercise",
                         json={"name": "Squat", "session_date": gun, "sets": [{"reps": 5, "weight": kg, "completed": True}]})
        assert r.status_code == 201
    en = (await c.get("/api/fitness/workouts/en-iyi", params={"adlar": ["Squat"], "once": GUN})).json()
    assert en == {"squat": {"kg": 100.0, "tekrar": 5, "tarih": "2026-11-02"}}
    on = (await c.get("/api/fitness/workouts/onceki", params={"adlar": ["squat"], "once": GUN})).json()
    assert on["squat"]["tarih"] == "2026-11-04" and on["squat"]["sets"][0]["weight"] == 90


async def test_hazir_kopya_kararli_kimlik_ve_silinince_doner(c):
    govde = {"name": "Benim Bacak", "exercises": [{"name": "Squat", "aralik": "6-8", "sets": [{"reps": 6, "weight": 90}]}]}
    a = (await c.put("/api/fitness/templates/hazir-bacak", json=govde)).json()
    b = (await c.put("/api/fitness/templates/hazir-bacak", json=govde)).json()
    assert a["id"] == b["id"] and a["hazir_slug"] == "bacak"
    assert len((await c.get("/api/fitness/templates")).json()) == 1
    bozuk = {**govde, "exercises": [{**govde["exercises"][0], "aralik": "x"}]}
    assert (await c.put("/api/fitness/templates/hazir-bacak", json=bozuk)).status_code == 400
    assert (await c.delete(f"/api/fitness/templates/{a['id']}")).status_code == 204
    assert (await c.get("/api/fitness/templates")).json() == []


async def test_son_yapilma_hazir_sablon(c):
    ex = (await _yukle(c)).json()["exercises"][0]
    assert (await c.get("/api/fitness/templates/son-yapilma?hazir=bacak")).json() == {"hazir-bacak": None}
    await c.put(f"/api/fitness/workouts/exercise/{ex['id']}/sets",
                json={"sets": [{"id": ex["sets"][0]["id"], "reps": 5, "weight": 100, "dokunuldu": True}]})
    assert (await c.get("/api/fitness/templates/son-yapilma?hazir=bacak")).json() == {"hazir-bacak": GUN}


async def test_ayarlar_temizlenir_kismi_put(c):
    r = (await c.put("/api/fitness/bildirim-ayar", json={"push": False, "sessiz": [25, 8], "x": 1})).json()
    assert r == {"push": False, "sessiz": [23, 8], "hatirlatma": True}
    r = (await c.put("/api/fitness/bildirim-ayar", json={"hatirlatma": False})).json()
    assert r["push"] is False, "kısmi PUT kayıtlı değeri korur"
    h = (await c.put("/api/fitness/ayar/hareket", json={"hiz": 9, "anlar": {"rekor": {"hiz": 0.01, "egri": "keskin"}}})).json()
    assert h["hiz"] == 2.0 and h["anlar"]["rekor"] == {"acik": True, "hiz": 0.25, "egri": "keskin"}
    f = (await c.put("/api/fitness/favoriler", json={"favoriler": [{"name": "Yulaf", "cal": 300}]})).json()
    assert (await c.get("/api/fitness/favoriler")).json() == f


async def test_hafta_turu_kurali(c):
    pzt = date.today() - timedelta(days=date.today().weekday())
    assert (await c.put("/api/fitness/hafta-turu", json={"hafta": str(pzt), "tur": "deload"})).status_code == 200
    r = await c.put("/api/fitness/hafta-turu", json={"hafta": str(pzt + timedelta(days=7)), "tur": "deload"})
    assert r.status_code == 400, "4 haftada 1 deload"
    assert (await c.put("/api/fitness/hafta-turu", json={"hafta": str(pzt + timedelta(days=1)), "tur": "deload"})).status_code == 400
    assert (await c.get("/api/fitness/hafta-turu")).json() == [{"hafta": str(pzt), "tur": "deload"}]


async def test_durum_unvan_ve_olay_goruldu(c):
    d = (await c.get("/api/fitness/durum")).json()
    assert d["seviye"] == 1 and "bekleyen_olaylar" in d and "gorevler" in d
    assert (await c.put("/api/fitness/oyun/unvan", json={"kod": "tutulmus"})).status_code == 404
    assert (await c.post("/api/fitness/olaylar/yok/goruldu")).status_code == 404


async def test_dogrulama_400(c):
    ex = (await c.post("/api/fitness/workouts/exercise", json={"name": "Squat", "sets": [{"reps": 5, "weight": 100}]})).json()
    yol = f"/api/fitness/workouts/exercise/{ex['id']}/sets"
    assert (await c.put(yol, json={"sets": [{"reps": 5, "weight": 1, "drops": [{"kg": -1, "tekrar": 5}]}]})).status_code == 400
    assert (await c.put(yol, json={"sets": [{"reps": 5, "weight": 1, "drops": [{"kg": 1, "tekrar": 1.5}]}]})).status_code == 400
    assert (await c.put(yol, json={"sets": [{"id": "x", "reps": 5, "weight": 1}]})).status_code == 400
    assert (await c.get("/api/fitness/meals?date=bozuk")).status_code == 400
    assert (await c.get("/api/fitness/workouts/ozet?bas=2026-01-01&bit=2026-06-01")).status_code == 400


async def test_ogun_ve_gunluk_toplam(c):
    await c.post("/api/fitness/meals", json={"meal": "ogle", "name": "pilav", "cal": 400, "protein": 8, "entry_date": GUN})
    g = (await c.get(f"/api/fitness/meals/gunluk?bitis={GUN}&gun=7")).json()
    assert g == [{"tarih": GUN, "cal": 400.0, "protein": 8.0, "carb": 0.0, "fat": 0.0}]
