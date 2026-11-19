"""Postgres'siz todo yolu — satılan paketin (AppImage/zip) gerçek koşulu.

Neden var: ürün paketinde Postgres YOK (`electron/main.js`). Eskiden `api/todo.py`
yalnız asyncpg biliyordu → PLAN ekranının tüm veri uçları 503 dönüyordu, üstelik
Yuki sohbetten eklediği görev ekranda görünmüyordu (iki ayrı depo). Bu testler o
iki kusurun geri gelmesini engeller.

conftest'teki `mock_db_pool` zaten get_pool → None yapıyor = paket koşulu.
"""
import asyncio
import json

import pytest

from app.api import todo as todo_api
from app.services import todo_store
from app.services.tools import todo_tools


@pytest.fixture
def pro_lisans(monkeypatch):
    """Eski Pro kapısı fikstürü — açık kaynak sürümde kademe yok, no-op."""
    yield


@pytest.fixture(autouse=True)
def izole_depo(tmp_path, monkeypatch):
    """Her test kendi veri dosyasında koşsun (gerçek kullanıcı verisine dokunma).

    Ayrıca `api/todo.py` get_pool'u modül düzeyinde import ettiği için conftest'in
    `app.db.connection.get_pool` yaması oraya işlemiyor — o ismi ayrıca None'a çek,
    yoksa testler gerçek Postgres'e bağlanmayı dener.
    """
    monkeypatch.setattr(todo_store, "_STORE_FILE", tmp_path / "todo_store.json")
    monkeypatch.setattr(todo_store, "_LEGACY_FILE", tmp_path / "todos.json")

    async def _yok():
        return None

    monkeypatch.setattr(todo_api, "get_pool", _yok)
    return tmp_path


# ── Depo katmanı ──────────────────────────────────────────────────────────────

def test_varsayilan_gelen_kutusu_kurulur():
    lists = todo_store.get_lists()["lists"]
    assert [l["name"] for l in lists] == ["Gelen Kutusu"]
    assert lists[0]["id"] == todo_store.INBOX_ID


def test_gorev_yasam_dongusu():
    inbox = todo_store.INBOX_ID
    t = todo_store.create_task(inbox, title="süt al", priority="high")
    assert todo_store.get_tasks(inbox)["tasks"][0]["id"] == t["id"]

    todo_store.complete_task(t["id"])
    assert todo_store.get_tasks(inbox)["tasks"] == []                 # açıklarda yok
    assert len(todo_store.get_tasks(inbox, include_completed=True)["tasks"]) == 1


def test_bos_tarih_temizler_gonderilmeyen_alan_degismez():
    """PG'de `due_date=""` SİLER, alanın hiç gelmemesi dokunmaz. Depo da öyle olmalı."""
    t = todo_store.create_task(todo_store.INBOX_ID, title="x", due_date="2026-08-01")
    assert todo_store.update_task(t["id"], {"due_date": None})["due_date"] is None
    todo_store.update_task(t["id"], {"due_date": "2026-08-02"})
    assert todo_store.update_task(t["id"], {"title": "y"})["due_date"] == "2026-08-02"


def test_cop_kutusu_geri_yukleme_ve_kalici_silme():
    t = todo_store.create_task(todo_store.INBOX_ID, title="çöp adayı")
    todo_store.delete_task(t["id"])
    assert len(todo_store.get_trash()["tasks"]) == 1
    assert todo_store.get_tasks(todo_store.INBOX_ID)["tasks"] == []   # çöptekiler listede yok

    assert todo_store.restore_task(t["id"]) is True
    assert todo_store.restore_task(t["id"]) is False                  # ikinci kez olmaz

    todo_store.delete_task(t["id"])
    assert todo_store.permanent_delete_task(t["id"]) is True
    assert todo_store.get_trash()["tasks"] == []


def test_tekrarlayan_gorev_tamamlaninca_klonlanir():
    t = todo_store.create_task(todo_store.INBOX_ID, title="haftalık rapor",
                               due_date="2026-08-03", repeat="weekly")
    todo_store.complete_task(t["id"])
    acik = todo_store.get_tasks(todo_store.INBOX_ID)["tasks"]
    assert len(acik) == 1 and acik[0]["due_date"] == "2026-08-10"


def test_arama_turkce_buyuk_kucuk_duyarsiz():
    todo_store.create_task(todo_store.INBOX_ID, title="Işık faturası")
    assert len(todo_store.search_tasks("IŞIK")["tasks"]) == 1
    assert len(todo_store.search_tasks("ışık")["tasks"]) == 1


def test_butce_ozeti():
    todo_store.add_budget_entry("income", 5000, "maaş", None, "2026-07-15")
    todo_store.add_budget_entry("expense", 1200.5, "market", None, "2026-07-20")
    s = todo_store.get_budget_summary("2026-07")
    assert (s["income"], s["expense"], s["balance"]) == (5000.0, 1200.5, 3799.5)
    assert s["top_categories"][0]["category"] == "market"
    assert todo_store.get_budget_summary("2026-06")["count"] == 0


def test_bozuk_dosya_veriyi_silmez_yedekler(izole_depo):
    todo_store.create_task(todo_store.INBOX_ID, title="x")
    todo_store._STORE_FILE.write_text("{bozuk json", encoding="utf-8")
    todo_store.get_lists()                       # çökmemeli
    assert todo_store._STORE_FILE.with_suffix(".json.bozuk").exists()


def test_eski_todos_json_tasinir(izole_depo):
    """Sürüm yükseltmesinde eski düz depo kaybolmamalı."""
    todo_store._LEGACY_FILE.write_text(json.dumps([
        {"id": "aaaa1111", "title": "eski görev", "list_name": "alışveriş",
         "priority": "high", "created_at": "2026-07-20T10:00:00", "completed_at": None},
    ]), encoding="utf-8")

    lists = todo_store.get_lists()["lists"]
    assert any("lışveriş" in l["name"].lower() for l in lists)
    basliklar = {t["title"] for l in lists
                 for t in todo_store.get_tasks(l["id"], include_completed=True)["tasks"]}
    assert "eski görev" in basliklar
    assert todo_store._LEGACY_FILE.with_suffix(".json.tasindi").exists()


# ── API katmanı (PLAN ekranı) ─────────────────────────────────────────────────

@pytest.mark.anyio
async def test_plan_ekrani_uclari_503_donmez(client, pro_lisans):
    """Regresyon kilidi: bu uçlar pakette 503 dönüyordu (Postgres yok diye)."""
    for yol in ("/api/todo/lists", "/api/todo/stats", "/api/todo/trash",
                "/api/todo/filter?f=today", "/api/todo/search?q=x",
                "/api/todo/budget/summary", "/api/todo/budget/entries"):
        r = await client.get(yol)
        assert r.status_code == 200, f"{yol} → {r.status_code} {r.text[:120]}"


def test_her_planner_ucu_kapili_sayim_yapilarak():
    """Örnek değil KURAL: `/api/todo` + `/api/planner` altındaki HER uç kapılı.

    Üstteki test 5 yolu örnekliyor; yeni bir uç ayrı bir router'a ya da
    `main.py`'ye eklenirse örnekleme onu görmez. 2026-08-06'da "PLAN'ın 9
    ucundan 4'ü kapısız" diye bir bulgu kaydedilmişti; 2026-08-09'da uçlar
    tek tek sayıldı, hepsi kapılı çıktı — bu test o durumu KİLİTLER.

    `/ui/planner.html` bilerek hariç: onun kapısı router bağımlılığı değil,
    `main.py` içindeki kendi `feature_allowed("planner")` denetimi (403 +
    satış sayfası döner). Onu üstteki Free testi ölçüyor.
    """
    from app.main import app
    from app.api.todo import require_planner

    kapisiz = []
    for r in app.routes:
        yol = getattr(r, "path", "")
        if not (yol.startswith("/api/todo") or yol.startswith("/api/planner")):
            continue
        deps = getattr(getattr(r, "dependant", None), "dependencies", [])
        if not any(getattr(d, "call", None) is require_planner for d in deps):
            kapisiz.append(f"{sorted(getattr(r, 'methods', []) or [])} {yol}")

    assert not kapisiz, "kapısız PLAN ucu:\n  " + "\n  ".join(kapisiz)


@pytest.mark.anyio
async def test_free_gorevleri_sohbetten_yonetebilir():
    """Kapı Free'nin araç yolunu KESMEMELİ — vitrin '20 araç ... görev' diyor."""
    assert "eklendi" in await todo_tools.create_todo("free görevi")
    assert "free görevi" in await todo_tools.list_todos("all")


@pytest.mark.anyio
async def test_gorev_api_uctan_uca(client, pro_lisans):
    inbox = todo_store.INBOX_ID
    r = await client.post(f"/api/todo/lists/{inbox}/tasks", json={"title": "api görevi"})
    assert r.status_code == 201
    tid = r.json()["id"]

    r = await client.get(f"/api/todo/lists/{inbox}/tasks")
    assert [t["id"] for t in r.json()["tasks"]] == [tid]

    assert (await client.post(f"/api/todo/tasks/{tid}/complete")).json()["completed_at"]
    assert (await client.patch("/api/todo/tasks/yok", json={"title": "x"})).status_code == 404
    assert (await client.get("/api/todo/filter?f=saçma")).status_code == 400


# ── Sohbet ↔ ekran ortak veri ─────────────────────────────────────────────────

@pytest.mark.anyio
async def test_yuki_ve_plan_ekrani_ayni_veriyi_gorur(client, pro_lisans):
    """Ürünün tutarlılık şartı: Yuki'nin eklediği görev PLAN'da görünmeli."""
    mesaj = await todo_tools.create_todo("sohbetten eklendi")
    assert "eklendi" in mesaj

    r = await client.get(f"/api/todo/lists/{todo_store.INBOX_ID}/tasks")
    assert [t["title"] for t in r.json()["tasks"]] == ["sohbetten eklendi"]

    # ters yön: ekrandan ekle → Yuki görsün
    await client.post(f"/api/todo/lists/{todo_store.INBOX_ID}/tasks",
                      json={"title": "ekrandan eklendi"})
    cikti = await todo_tools.list_todos("all")
    assert "ekrandan eklendi" in cikti and "sohbetten eklendi" in cikti
