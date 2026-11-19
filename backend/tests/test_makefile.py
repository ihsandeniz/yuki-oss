"""Kurulum yüzeyi belgeyle uyumlu (denetim 2026-11-16, MIM): varsayılan port, Makefile, cihaz ajanı adresi.

Eskiden: `config.PORT` varsayılanı 8000 (README + start.sh 8001 diyor; 8000 başka kurulumların portu),
Makefile başka bir kurulumdan kalmaydı (8000, var olmayan `start.sh --electron`, make'in /bin/sh'inde
çalışmayan `source`, eski log yolu), cihaz ajanının varsayılan sunucu adresi :8000.
"""
from __future__ import annotations

import os
import re
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

KOK = Path(__file__).resolve().parents[2]
BACKEND = KOK / "backend"


def test_config_PORT_varsayilani_8001(tmp_path):
    """Ortamda PORT yokken taze süreçte okunan değer — modül önbelleğinden bağımsız."""
    env = {k: v for k, v in os.environ.items() if k not in ("PORT", "YUKI_PORT")}
    env["YUKI_DATA_DIR"] = str(tmp_path)
    cikti = subprocess.run([sys.executable, "-c", "from app import config; print(config.PORT)"],
                           cwd=BACKEND, env=env, capture_output=True, text=True, timeout=60)
    assert cikti.returncode == 0, cikti.stderr[-800:]
    assert cikti.stdout.strip().splitlines()[-1] == "8001"


def test_cihaz_ajani_varsayilan_adresi_8001():
    kod = (KOK / "remote_agent" / "agent.py").read_text(encoding="utf-8")
    m = re.search(r'_ortam\("SERVER",\s*"([^"]+)"\)', kod)
    assert m and ":8001/ws/agent" in m.group(1), m and m.group(1)


def _hedefler() -> list[str]:
    metin = (KOK / "Makefile").read_text(encoding="utf-8")
    return re.findall(r"^([a-z][\w-]*):", metin, flags=re.M)


@pytest.mark.skipif(not shutil.which("make"), reason="make kurulu değil")
def test_makefile_hedefleri_belgeyle_uyumlu():
    hedefler = _hedefler()
    assert {"start", "stop", "test", "install", "web"} <= set(hedefler), hedefler
    gecerli_bayrak = set(re.findall(r"^\s+(--[\w-]+)\)", (KOK / "start.sh").read_text(encoding="utf-8"), flags=re.M))
    for h in hedefler:
        r = subprocess.run(["make", "-n", "-s", h], cwd=KOK, capture_output=True, text=True, timeout=30)
        assert r.returncode == 0, (h, r.stderr)
        komut = r.stdout
        assert "8000" not in komut, (h, komut)
        assert not re.search(r"(^|\s)source\s", komut), f"{h}: make /bin/sh kullanır, `source` yok"
        assert "alice" not in komut.lower(), (h, komut)
        for b in re.findall(r"start\.sh((?:\s+--[\w-]+)*)", komut):
            for bayrak in b.split():
                assert bayrak in gecerli_bayrak, f"{h}: start.sh {bayrak} diye bir bayrak tanımıyor"


def test_compose_ve_dockerfile_yok_belgede_de_yok():
    """Backend konteyneri söküldü; README/CONTRIBUTING Dockerfile'a yönlendirmemeli."""
    assert not (BACKEND / "Dockerfile").exists()
    for ad in ("README.md", "CONTRIBUTING.md"):
        assert "Dockerfile" not in (KOK / ad).read_text(encoding="utf-8"), ad
