"""Atölye tohumlu görev — istekte geçen atölye klasörü yeni alana KOPYALANIR.

Asıl klasöre dokunulmaz; `.gorev`/gizli dosya/sembolik bağ gelmez; kök dışı, `.kuyruk`, tavan
aşımı, dış kaynak → tohum yok. Atölye kökü pytest'in geçici dizinidir (HOME'a yazılmaz).
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from app.services.gorev import GorevServisi, TOHUM_DOSYA


# ── tohumlu görev ───────────────────────────────────────────────────────────

@pytest.fixture
def servis(tmp_path):
    return GorevServisi(kok=tmp_path / "atolye", bildir=lambda *a: None)


def _kaynak(servis, ad="gece-bahcesi") -> Path:
    k = servis.kok / "site" / ad
    (k / "css").mkdir(parents=True)
    (k / "index.html").write_text("<h1>Gece</h1>")
    (k / "css" / "stil.css").write_text("body{}")
    (k / ".gorev").mkdir()
    (k / ".gorev" / "durum.json").write_text("{}")
    (k / ".gizli").write_text("x")
    return k


def _hazirla(servis, istek, kaynak="yerel", ad="gelistir"):
    return servis._hazirla("site", ad, istek, None, kaynak, "kosuyor")


def test_tohum_kopyalanir_asil_kalir(servis):
    k = _kaynak(servis)
    d = _hazirla(servis, f"Gece Bahçesi'ni geliştir, aynı klasörde çalış: {k}/.")
    yeni = servis.kok / "site" / "gelistir"
    assert (yeni / "index.html").read_text() == "<h1>Gece</h1>"
    assert (yeni / "css" / "stil.css").is_file()
    assert not (yeni / ".gizli").exists()
    assert not (yeni / ".gorev" / "durum.json").exists()     # yeni görevin kaydı ayrı
    assert d["tohum"].rstrip("/").endswith("site/gece-bahcesi")
    assert (k / "index.html").read_text() == "<h1>Gece</h1>"
    sistem = json.loads((yeni / ".gorev" / "mesajlar.json").read_text())[0]["content"]
    assert "kopyası" in sistem and "geliştir" in sistem


def test_tohum_tilde_yolu(servis, monkeypatch, tmp_path):
    monkeypatch.setenv("HOME", str(tmp_path))
    _kaynak(servis)
    d = _hazirla(servis, "geliştir: ~/atolye/site/gece-bahcesi/")
    assert d["tohum"] == "~/atolye/site/gece-bahcesi/"
    assert (servis.kok / "site" / "gelistir" / "index.html").is_file()


def test_yol_yoksa_tohum_yok(servis):
    d = _hazirla(servis, "bana bir site yap")
    assert "tohum" not in d
    assert [p.name for p in (servis.kok / "site" / "gelistir").iterdir()] == [".gorev"]


@pytest.mark.parametrize("durum", ["kok_disi", "kuyruk", "bag", "tavan", "dis", "kendisi", "tur_koku"])
def test_tohum_kapilari(servis, tmp_path, durum):
    kaynak = "yerel"
    if durum == "kok_disi":
        dis = tmp_path / "baska"
        dis.mkdir()
        (dis / "a.html").write_text("x")
        yol = dis
    elif durum == "kuyruk":
        yol = servis.kok / ".kuyruk"
        yol.mkdir(parents=True)
        (yol / "kuyruk.json").write_text("[]")
    elif durum == "bag":
        k = _kaynak(servis)
        yol = servis.kok / "site" / "bag"
        yol.symlink_to(k)
    elif durum == "tavan":
        yol = servis.kok / "site" / "buyuk"
        yol.mkdir(parents=True)
        for i in range(TOHUM_DOSYA + 1):
            (yol / f"{i}.txt").write_text("x")
    elif durum == "dis":
        yol = _kaynak(servis)
        kaynak = "dis"
    elif durum == "kendisi":
        yol = servis.kok / "site" / "gelistir"
    else:
        _kaynak(servis)
        yol = servis.kok / "site"
    d = _hazirla(servis, f"geliştir {yol}/", kaynak=kaynak)
    assert "tohum" not in d
    icerik = sorted(p.name for p in (servis.kok / "site" / "gelistir").iterdir())
    assert icerik == [".gorev"]


def test_tohumda_bag_dosyasi_gelmez(servis, tmp_path):
    k = _kaynak(servis)
    sir = tmp_path / "sir.txt"
    sir.write_text("gizli")
    (k / "sir.txt").symlink_to(sir)
    _hazirla(servis, f"geliştir {k}")
    assert not (servis.kok / "site" / "gelistir" / "sir.txt").exists()
