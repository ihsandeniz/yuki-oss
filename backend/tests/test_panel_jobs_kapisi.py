"""Arka Plan İşleri araçları — açık kaynak sürümde YOK.

(Bu dosyanın panel araçları kısmı Komuta Paneli ile birlikte 11-13'te kalktı;
yokluğu tests/test_komuta_paneli_yok.py tutar.)
"""
from __future__ import annotations

from app.services.tools import dispatcher

# Arka Plan İşleri (job_status/list_jobs/job_output/cancel_job) açık kaynak sürümde
# YOK — kabuk komutu çalıştıran özellik çıkarıldı (2026-10-17).
JOBS_TOOLS_YOK = [
    "job_status", "list_jobs", "job_output", "cancel_job",
]


def test_jobs_araclari_yok():
    aktif = {t["function"]["name"] for t in dispatcher.get_active_tools()}
    for tool in JOBS_TOOLS_YOK:
        assert tool not in aktif, f"{tool} hâlâ LLM listesinde"
