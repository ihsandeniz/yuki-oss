"""Delta güncelleme overlay'i — katmanlı frontend sunumu.

🔴 NEDEN VAR: güncelleme yükü (~1,2 MiB) `frontend/assets`'i TAŞIMAZ — orası
121 MiB medya ve sürümler arası sabit. Overlay'den çalışırken `FRONTEND_DIR`
overlay'i gösterir ve orada `assets/` yoktur; katmanlı sunum olmasa
**güncelleme sonrası bütün görseller/videolar 404 olurdu.**

Uçtan uca ölçüldü (2026-08-02, gerçek backend overlay'den koşturularak):
  · Python kodu overlay'den geldi (health 9.9.9-OVERLAY)
  · js overlay'den geldi
  · 4,9 MB'lık mp4 paketten geldi, bayt-bayt tam
Bu testler o davranışın regresyonunu engeller.
"""
from __future__ import annotations

import importlib
import os
import sys
from pathlib import Path

import pytest


@pytest.fixture
def katmanli(tmp_path, monkeypatch):
    """Overlay + paket ikilisi kur, `app.main`'i o ortamla yeniden yükle."""
    overlay = tmp_path / "overlay" / "frontend"
    paket = tmp_path / "paket" / "frontend"
    (overlay / "js").mkdir(parents=True)
    (paket / "js").mkdir(parents=True)
    (paket / "assets").mkdir()

    # overlay: güncel kod · paket: eski kod + medya
    (overlay / "js" / "core.js").write_text("// YENİ", encoding="utf-8")
    (paket / "js" / "core.js").write_text("// ESKİ", encoding="utf-8")
    (paket / "js" / "eski-modul.js").write_text("// yalnız pakette", encoding="utf-8")
    (paket / "assets" / "video.mp4").write_bytes(b"\x00" * 2048)
    (overlay / "index.html").write_text("<b>yeni</b>", encoding="utf-8")

    monkeypatch.setenv("YUKI_FRONTEND_FALLBACK", str(paket))
    import app.main as m
    importlib.reload(m)
    monkeypatch.setattr(m, "FRONTEND_DIR", overlay)
    monkeypatch.setattr(m, "FRONTEND_FALLBACK_DIR", paket)
    yield m, overlay, paket
    importlib.reload(m)          # sonraki testler etkilenmesin


def test_overlay_dosyasi_paketi_ezer(katmanli):
    """İki tarafta da varsa overlay kazanmalı — güncelleme bunun için var."""
    m, overlay, _ = katmanli
    yol = m.frontend_dosyasi("js/core.js")
    assert yol.read_text(encoding="utf-8") == "// YENİ"
    assert yol.is_relative_to(overlay)


def test_overlayde_olmayan_paketten_gelir(katmanli):
    """Yükte olmayan dosya (medya, eski modül) paketten servis edilmeli.

    Bu düşerse güncelleme sonrası tüm görseller/videolar 404 olur.
    """
    m, _, paket = katmanli
    for rel in ("js/eski-modul.js", "assets/video.mp4"):
        yol = m.frontend_dosyasi(rel)
        assert yol.exists(), f"{rel} paketten bulunmalıydı"
        assert yol.is_relative_to(paket)


def test_hicbir_yerde_yoksa_birincil_dondurulur(katmanli):
    """404 üretilecek — ama sessizce yanlış dosya DEĞİL."""
    m, overlay, _ = katmanli
    yol = m.frontend_dosyasi("yok/olmayan.js")
    assert not yol.exists()
    assert yol.is_relative_to(overlay)


def test_fallback_yokken_davranis_degismez(tmp_path, monkeypatch):
    """Overlay'siz (normal paketlenmiş) çalışmada mantık eskisiyle birebir aynı.

    Delta güncelleme kullanmayan müşterinin davranışı hiç değişmemeli.
    """
    monkeypatch.delenv("YUKI_FRONTEND_FALLBACK", raising=False)
    import app.main as m
    importlib.reload(m)
    assert m.FRONTEND_FALLBACK_DIR is None
    kok = tmp_path / "frontend"
    (kok / "js").mkdir(parents=True)
    (kok / "js" / "a.js").write_text("x", encoding="utf-8")
    monkeypatch.setattr(m, "FRONTEND_DIR", kok)
    assert m.frontend_dosyasi("js/a.js").read_text(encoding="utf-8") == "x"
    assert m.frontend_dosyasi("js/yok.js") == kok / "js" / "yok.js"
    importlib.reload(m)


def test_katmanli_statik_lookup(katmanli):
    """`KatmanliStatik` gerçekten iki köke de bakıyor mu (mount'un kullandığı yol)."""
    m, overlay, paket = katmanli
    s = m.KatmanliStatik(directory=str(overlay), fallback=paket)
    _, st_yeni = s.lookup_path("js/core.js")
    assert st_yeni is not None, "overlay dosyası bulunmalı"
    tam_yedek, st_yedek = s.lookup_path("assets/video.mp4")
    assert st_yedek is not None, "paket yedeğinden gelmeliydi"
    assert str(paket) in tam_yedek

    # Yol güvenliği ÜSTTEKİ sınıfta — override onu delmemeli
    _, st_kacis = s.lookup_path("../../gizli.txt")
    assert st_kacis is None, "dizin dışına çıkış reddedilmeli"
