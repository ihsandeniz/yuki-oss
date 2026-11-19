"""Sistem sağlık skoru (0-100) + eşik-bazlı uyarılar."""
from __future__ import annotations


def _band_penalty(value: float, comfort: float, crit: float) -> float:
    """Eşik (comfort) altında 0 ceza; comfort→crit arası lineer 0-100 ceza.

    Böylece normal/boşta sistem ~100 skorlar; ceza yalnız gerçek baskı zonunda başlar.
    """
    if value <= comfort:
        return 0.0
    return max(0.0, min(100.0, (value - comfort) / max(crit - comfort, 1e-6) * 100))


def health_score(snap: dict) -> int:
    """CPU %30 + RAM %30 + Disk %20 + Sıcaklık %20 kompozit. 100 = sağlıklı.

    Baskı-bandı modeli: rahat eşiğin altında ceza yok (ör. %50 RAM = sağlıklı).
    """
    cpu = (snap.get("cpu") or {}).get("total") or 0
    mem = (snap.get("mem") or {}).get("percent") or 0
    disks = snap.get("disks") or []
    disk = max((d.get("percent") or 0 for d in disks), default=0)

    temps = []
    ct = (snap.get("cpu") or {}).get("temp_c")
    gt = (snap.get("gpu_nvidia") or {}).get("temp_c")
    if ct:
        temps.append(ct)
    if gt:
        temps.append(gt)
    temp = max(temps) if temps else 0.0

    penalty = (
        _band_penalty(cpu, 70, 100) * 0.30
        + _band_penalty(mem, 75, 100) * 0.30
        + _band_penalty(disk, 80, 100) * 0.20
        + _band_penalty(temp, 70, 90) * 0.20
    )
    return int(max(0, min(100, round(100 - penalty))))


def eval_alerts(snap: dict, *, cpu_warn: int = 90, mem_warn: int = 90,
                disk_warn: int = 90, temp_warn: int = 80) -> list[dict]:
    """Eşik aşan metrikler için {level, metric, msg} listesi."""
    alerts: list[dict] = []

    cpu = (snap.get("cpu") or {}).get("total") or 0
    if cpu >= cpu_warn:
        alerts.append({"level": "warn", "metric": "cpu", "msg": f"CPU %{cpu:.0f}"})

    mem = (snap.get("mem") or {}).get("percent") or 0
    if mem >= mem_warn:
        alerts.append({"level": "warn", "metric": "mem", "msg": f"RAM %{mem:.0f}"})

    for d in snap.get("disks") or []:
        pct = d.get("percent") or 0
        if pct >= disk_warn:
            alerts.append({"level": "warn", "metric": "disk",
                           "msg": f"Disk {d.get('mount')} %{pct:.0f}"})

    ct = (snap.get("cpu") or {}).get("temp_c")
    if ct and ct >= temp_warn:
        alerts.append({"level": "crit", "metric": "cpu_temp", "msg": f"CPU {ct:.0f}°C"})

    gt = (snap.get("gpu_nvidia") or {}).get("temp_c")
    if gt and gt >= temp_warn:
        alerts.append({"level": "crit", "metric": "gpu_temp", "msg": f"GPU {gt:.0f}°C"})

    return alerts
