"""Electron zarifsiz ölünce (SIGKILL, oturum kapanışında ekran sunucusunun gitmesi)
motor 8791'de öksüz kalıyordu — ölçüm `scratchpad/sinyal-kapanis-canli.py`. Bu testler
bekçinin sözleşmesini sabitler; gerçek süreç davranışı canlı betikle ölçülür."""
from pathlib import Path

from app import ebeveyn_bekcisi as b


def test_electron_disinda_kurulmaz():
    assert b.yoklayici_kur({}) is None
    assert b.yoklayici_kur({"YUKI_EBEVEYN_PID": "abc"}) is None


def test_arada_sarmalayici_varsa_kurulmaz():
    """Ebeveyn beklenen PID değilse bekçi kendini öldürmesin — kurulmaz."""
    assert b.yoklayici_kur({"YUKI_EBEVEYN_PID": "100"}, platform="linux", getppid=lambda: 42) is None


def test_posix_ebeveyn_degisince_olu_sayilir():
    ppid = {"v": 100}
    yasiyor = b.yoklayici_kur({"YUKI_EBEVEYN_PID": "100"}, platform="linux", getppid=lambda: ppid["v"])
    assert yasiyor() is True
    ppid["v"] = 1  # init'e devredildi
    assert yasiyor() is False


def test_windows_psutil_yoluna_gider():
    istenen = []
    b.yoklayici_kur({"YUKI_EBEVEYN_PID": "777"}, platform="win32",
                    windows_yoklayici=lambda pid: istenen.append(pid) or (lambda: True))
    assert istenen == [777]


def test_windows_pid_yeniden_kullanimi_ebeveyn_sanilmaz(monkeypatch):
    import psutil

    class P:
        zaman = 1000.0

        def __init__(self, pid):
            pass

        def create_time(self):
            return P.zaman

    monkeypatch.setattr(psutil, "Process", P)
    yasiyor = b._windows_yoklayici(5)
    assert yasiyor() is True
    P.zaman = 2000.0  # aynı PID, başka süreç
    assert yasiyor() is False


def test_dongu_ebeveyn_olunce_kapatir():
    durum = iter([True, True, False])
    kapandi = []
    t = b.baslat({"YUKI_EBEVEYN_PID": "1"}, yoklayici=lambda: next(durum),
                 kapat=lambda: kapandi.append(1), uyu=lambda _: None)
    t.join(2)
    assert kapandi == [1]


def test_kurulmazsa_is_parcacigi_yok():
    assert b.baslat({}) is None


def test_run_py_bekciyi_baslatiyor_ve_electron_pid_veriyor():
    """Modülün var olması kurulduğunu göstermez — iki uç da bağlı mı?"""
    kok = Path(__file__).resolve().parents[2]
    assert "ebeveyn_bekcisi.baslat()" in (kok / "backend/run.py").read_text()
    assert "YUKI_EBEVEYN_PID: String(process.pid)" in (kok / "electron/uygulama.js").read_text()
