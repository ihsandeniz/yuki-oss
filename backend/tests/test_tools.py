"""Sandbox ve dosya aracı (path traversal) testleri."""

import subprocess
import sys
from pathlib import Path
from unittest.mock import patch

import pytest

from app.services.tools._base import _apply_sandbox_limits  # noqa: F401  (import edilebilirlik)
from app.services.tools.files import list_directory, read_file


# ── Sandbox preexec_fn testleri ─────────────────────────────────────

def test_sandbox_limits_callable():
    """_apply_sandbox_limits() exception fırlatmamalı — AMA ÇOCUK SÜREÇTE.

    ⚠️ Bu fonksiyon bir `preexec_fn`'dir: RLIMIT_CPU/RLIMIT_AS/RLIMIT_FSIZE'ı
    ve `os.setsid()`'i **kendisini çağıran sürece** uygular. Eskiden doğrudan
    pytest'in içinde çağrılıyordu → test runner'ın bellek/CPU tavanı kısılıyor
    ve süreç grubu koparılıyordu; sonraki testler (test_vision → PIL/base64)
    o tavana çarpıp **tüm suite'i kilitliyordu**. Tek dosya koşulunca fark
    edilmiyordu, bu yüzden aylarca sessiz kaldı.
    """
    kod = (
        "from app.services.tools._base import _apply_sandbox_limits; "
        "_apply_sandbox_limits(); print('ok')"
    )
    r = subprocess.run(
        [sys.executable, "-c", kod],
        capture_output=True, text=True, timeout=30,
        cwd=Path(__file__).resolve().parents[1],
    )
    assert r.returncode == 0, r.stderr
    assert "ok" in r.stdout


# ── Path traversal testleri ─────────────────────────────────────────

def test_list_directory_blocks_root():
    result = list_directory("/etc")
    assert "Güvenlik" in result or "Hata" in result


def test_read_file_blocks_etc_passwd():
    result = read_file("/etc/passwd")
    assert "Güvenlik" in result or "Hata" in result


def test_read_file_size_limit(tmp_path):
    """1MB üzeri dosya reddedilmeli."""
    big = tmp_path / "big.txt"
    big.write_bytes(b"x" * (2 * 1024 * 1024))
    result = read_file(str(big))
    assert "büyük" in result.lower() or "Hata" in result
