"""Faz 18 — HQ Sistem İzleme: collector + GPU + zaman serisi geçmiş + sağlık skoru."""
from app.services.monitoring.collector import SystemMonitor, monitor

__all__ = ["monitor", "SystemMonitor"]
