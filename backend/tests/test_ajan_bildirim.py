"""Cihaz ajanı bildirimi: sunucudan gelen başlık/metin komut metnine GÖMÜLMEZ.

Eski kod metni PowerShell `-Command` / `osascript -e` dizgisine f-string ile koyuyordu →
`"); Start-Process calc; ("` gibi bir metin komut çalıştırıyordu (exec kaldırılmasını dolanıyordu).
"""
import importlib.util
from pathlib import Path

import pytest

KOK = Path(__file__).resolve().parents[2]
KOTU = ['"); Start-Process calc; ("', '" & do shell script "id" & "', "'; id; '", "$(id)", "-u critical"]


@pytest.fixture(scope="module")
def ajan():
    spec = importlib.util.spec_from_file_location("ajan_bildirim", KOK / "remote_agent" / "agent.py")
    try:
        m = importlib.util.module_from_spec(spec); spec.loader.exec_module(m)
    except ImportError as e:
        pytest.skip(f"ajan bağımlılığı yok: {e}")
    return m


@pytest.mark.parametrize("sistem", ["Windows", "Darwin", "Linux"])
@pytest.mark.parametrize("kotu", KOTU)
def test_kotu_metin_komut_metnine_girmez(ajan, sistem, kotu):
    argv, env = ajan.bildirim_komutu(sistem, kotu, kotu)
    if sistem == "Windows":
        betik = argv[argv.index("-Command") + 1]
        assert betik == ajan._PS_BILDIRIM, "PowerShell betiği sabit olmalı"
        assert argv[-1] == betik, "-Command'dan sonra ek argüman yok (PowerShell onları komuta ekler)"
        assert env["YUKI_BILDIRIM_METIN"] == kotu and env["YUKI_BILDIRIM_BASLIK"] == kotu
    elif sistem == "Darwin":
        betikler = [argv[i + 1] for i, a in enumerate(argv) if a == "-e"]
        assert all(kotu not in b for b in betikler)
        assert argv[-2:] == [kotu, kotu]
    else:
        assert argv[:2] == ["notify-send", "--"]
    for i, a in enumerate(argv):
        if a == kotu:
            continue
        assert kotu not in a, f"metin komut parçasına gömülmüş: {a!r}"


def test_uzunluk_sinirli(ajan):
    argv, _ = ajan.bildirim_komutu("Darwin", "b" * 5000, "m" * 5000)
    assert len(argv[-2]) == ajan.BILDIRIM_AZAMI and len(argv[-1]) == ajan.BILDIRIM_AZAMI


def test_bilinmeyen_sistemde_hicbir_sey_calismaz(ajan):
    assert ajan.bildirim_komutu("Plan9", "a", "b") == (None, None)
