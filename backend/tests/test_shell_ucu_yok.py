"""`/api/shell` sökülmüş kalmalı (v0.8.1, denetim H2): kapısız `bash -c` HTTP ucu."""
from fastapi.testclient import TestClient

from app.main import app


def test_shell_ucu_kayitli_degil():
    yollar = {getattr(r, "path", "") for r in app.routes}
    assert "/api/shell" not in yollar


def test_shell_ucu_404():
    c = TestClient(app, base_url="http://127.0.0.1:8791")
    r = c.post("/api/shell", json={"message": "echo saldiri"})
    assert r.status_code in (404, 405)
