"""Bilgisayarım — GEÇMİŞ grafiği ve GÜN ÖZETİ'ni besleyen örnekleyici.

🔴 2026-09-27: Dalga 3 taşımasında (09-10) örnek yazan döngü düşmüştü. Okuyan uçlar
(`/api/monitor/history`, `/report/today`) vardı, `history.write_sample`'ı çağıran
hiçbir satır yoktu → monitor.db 0 bayt, müşteri 17 gün "veri birikiyor…" gördü.
Hiçbir test kırmızı yanmadı çünkü okuyan taraf boş veritabanında da 200 dönüyordu.
"""
import asyncio
import re
from pathlib import Path

import pytest

from app.services.monitoring import collector, history

MAIN = Path(__file__).resolve().parents[1] / "app" / "main.py"


def test_lifespan_ornekleyiciyi_yield_ONCESI_baslatiyor():
    kaynak = MAIN.read_text(encoding="utf-8")
    govde = kaynak[kaynak.index("async def lifespan"):]
    yield_yeri = govde.index("\n    yield\n")
    assert "await _monitor_ornekleyici_baslat(app)" in govde[:yield_yeri]


def test_kapanista_dongu_iptal_ediliyor():
    kaynak = MAIN.read_text(encoding="utf-8")
    govde = kaynak[kaynak.index("async def lifespan"):]
    kapanis = govde[govde.index("\n    yield\n"):]
    assert re.search(r"monitor_task.*\n.*\n\s+_mt\.cancel\(\)", kapanis)


def test_bir_ornek_gecmise_ve_gun_ozetine_dusuyor(tmp_path, monkeypatch):
    """Uçtan uca: gerçek anlık görüntü → db → okuyan uçların kullandığı sorgular."""
    from app import main

    monkeypatch.setattr(history, "_DB_PATH", tmp_path / "monitor.db")

    async def akis():
        await history.init_db()
        await asyncio.to_thread(collector.monitor.prime)
        await main._monitor_ornek_al(60)
        return await history.query_range("1h"), await history.report_today()

    ornekler, rapor = asyncio.run(akis())
    assert len(ornekler) == 1
    assert ornekler[0]["cpu"] is not None and ornekler[0]["mem"] is not None
    assert rapor["samples"] == 1
    assert rapor["top_cpu"], "gün özeti süreç toplamı boş"


def test_MONITOR_ENABLED_kapaliyken_dongu_kurulmuyor(monkeypatch):
    from types import SimpleNamespace

    from app import config, main

    monkeypatch.setattr(config, "MONITOR_ENABLED", False)
    app = SimpleNamespace(state=SimpleNamespace())
    asyncio.run(main._monitor_ornekleyici_baslat(app))
    assert not hasattr(app.state, "monitor_task")


@pytest.mark.parametrize("ad,cmd,beklenen", [
    ("MainThread", ["/opt/zen-browser-bin/zen-bin", "-contentproc"], "zen-bin"),
    ("python3", ["/usr/bin/python3", "x.py"], "python3"),
])
def test_iplik_adi_program_adina_cevriliyor(monkeypatch, ad, cmd, beklenen):
    class Sahte:
        def __init__(self, pid=1, *_a):
            self.pid = pid
            self.info = {"pid": 1, "name": ad, "username": "u", "memory_info": None,
                         "num_threads": 1, "create_time": None}

        def cpu_percent(self, _):
            return 5.0

        def cmdline(self):
            return cmd

    monkeypatch.setattr(collector.psutil, "process_iter", lambda *_a, **_k: [Sahte()])
    monkeypatch.setattr(collector.psutil, "Process", Sahte)
    satir = collector.monitor._processes(10, "cpu", {})[0]
    assert satir["name"] == beklenen
