"""PLAN · TAKVİM ay panosu — Google uçları (2026-09-26).

Kişisel AliceAi e1dec80'deki `/google/events?baslangic` ekinin ürün karşılığı, iki farkla:
  ① `baslangic` İSTEMCİNİN yerel gece yarısıdır (saat dilimli ISO) — kişisel sabit
     UTC+3 kullanıyordu, ürünün müşterisi başka dilimde olabilir.
  ② POST'ta saat dilimi sabit "Europe/Istanbul" DEĞİL, istemcinin gönderdiği.
Google'a çıkmaz: httpx.AsyncClient sahtesi giden isteği kaydeder.
"""
import pytest


class _Yanit:
    def __init__(self, veri, kod=200):
        self._veri, self.status_code = veri, kod

    def json(self):
        return self._veri

    def raise_for_status(self):
        pass


@pytest.fixture()
def istemci(monkeypatch):
    from starlette.testclient import TestClient

    from app.api import planner
    from app.api.todo import require_planner
    from app.main import app

    kayit = []

    class _SahteHttpx:
        def __init__(self, *a, **k):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, *e):
            return False

        async def get(self, url, headers=None, params=None):
            kayit.append(("GET", params))
            return _Yanit({"items": [{"id": "e1", "summary": "Diş", "start": {"dateTime": "2026-09-01T09:30:00+03:00"},
                                      "end": {"dateTime": "2026-09-01T10:30:00+03:00"}}]})

        async def post(self, url, headers=None, json=None):
            kayit.append(("POST", json))
            return _Yanit({"id": "yeni"})

    async def _token():
        return "sahte"

    monkeypatch.setattr(planner.httpx, "AsyncClient", _SahteHttpx)
    monkeypatch.setattr(planner, "_google_token", _token)
    app.dependency_overrides[require_planner] = lambda: None
    try:
        with TestClient(app) as c:
            yield c, kayit
    finally:
        app.dependency_overrides.pop(require_planner, None)


def test_baslangic_istemcinin_yerel_gece_yarisi(istemci):
    c, kayit = istemci
    r = c.get("/api/planner/google/events",
              params={"baslangic": "2026-08-31T00:00:00-07:00", "days": 42})
    assert r.status_code == 200 and r.json()["events"][0]["title"] == "Diş"
    p = kayit[-1][1]
    assert p["timeMin"] == "2026-08-31T00:00:00-07:00", "istemcinin dilimi korunmalı (sabit +03:00 değil)"
    assert p["timeMax"].startswith("2026-10-12T00:00:00"), "42 gün sonrası"
    assert p["maxResults"] == 250, "ay panosu ~42 gün: 50 sınırı tekrar eden tek etkinlikle doluyordu"


def test_baslangicsiz_eski_davranis_ve_gun_siniri(istemci):
    c, kayit = istemci
    assert c.get("/api/planner/google/events", params={"days": 999}).status_code == 200
    from datetime import datetime
    p = kayit[-1][1]
    bas, bit = datetime.fromisoformat(p["timeMin"]), datetime.fromisoformat(p["timeMax"])
    assert (bit - bas).days == 120, "days 1..120'ye kısılmalı"


def test_gecersiz_baslangic_400(istemci):
    c, _ = istemci
    assert c.get("/api/planner/google/events", params={"baslangic": "dün"}).status_code == 400


def test_etkinlik_istemcinin_saat_diliminde(istemci):
    c, kayit = istemci
    r = c.post("/api/planner/google/events", json={"title": "spor", "start": "2026-09-26T19:00:00",
                                                    "end": "2026-09-26T20:00:00", "saat_dilimi": "America/Los_Angeles"})
    assert r.status_code == 200
    assert kayit[-1][1]["start"] == {"dateTime": "2026-09-26T19:00:00", "timeZone": "America/Los_Angeles"}


def test_saat_dilimi_yoksa_geriye_uyum_ve_gecersizse_400(istemci):
    c, kayit = istemci
    c.post("/api/planner/google/events", json={"title": "a", "start": "2026-09-26T19:00:00", "end": "2026-09-26T20:00:00"})
    assert kayit[-1][1]["start"]["timeZone"] == "Europe/Istanbul"
    r = c.post("/api/planner/google/events", json={"title": "a", "start": "2026-09-26T19:00:00",
                                                    "end": "2026-09-26T20:00:00", "saat_dilimi": "Mars/Olympus"})
    assert r.status_code == 400


def test_tum_gun_etkinlik_tarih_olarak(istemci):
    c, kayit = istemci
    c.post("/api/planner/google/events", json={"title": "Tatil", "start": "2026-09-26", "end": "2026-09-27", "all_day": True})
    assert kayit[-1][1]["start"] == {"date": "2026-09-26"} and kayit[-1][1]["end"] == {"date": "2026-09-27"}
