"""monitor.py — HQ Sistem İzleme API (Faz 18 / Faz 0).

Yapısal sistem metrikleri (CPU/RAM/GPU/disk/ağ/process) + zaman serisi geçmiş.
Auth: global auth_middleware (Bearer) tüm /api/* yollarını korur — ek Depends gerekmez.
Bloklayan psutil çağrıları asyncio.to_thread ile event loop dışına alınır.
"""
from __future__ import annotations

import asyncio

from fastapi import APIRouter, HTTPException, Query, Request
from app.limiter import limiter
from app.mesajlar import M

from app.services.monitoring import history as _history
from app.services.monitoring.collector import monitor

router = APIRouter(prefix="/api/monitor", tags=["monitor"])


@router.get("/snapshot")
@limiter.limit("100/minute")
async def snapshot(request: Request):

    """Anlık sistem durumu (process'siz hızlı snapshot — frontend canlı polling)."""
    return await asyncio.to_thread(monitor.snapshot, include_processes=False)


@router.get("/processes")
@limiter.limit("100/minute")
async def processes(
    request: Request,
    sort: str = Query("cpu", pattern="^(cpu|mem|pid|name)$"),
    limit: int = Query(40, ge=1, le=200),
):
    """btop benzeri process tablosu (sıralı, top-N)."""
    snap = await asyncio.to_thread(
        monitor.snapshot, include_processes=True, proc_limit=limit, proc_sort=sort)
    return {"ts": snap["ts"], "processes": snap.get("processes", [])}


@router.get("/history")
@limiter.limit("30/minute")
async def history(request: Request, range: str = Query("1h", pattern="^(1h|24h|7d)$")):

    """Zaman serisi geçmiş (1h/24h/7d) — soğuk örnekleyici (60s) verisinden."""
    return {"range": range, "series": await _history.query_range(range)}


@router.get("/report/today")
@limiter.limit("30/minute")
async def report_today(request: Request, day: str | None = Query(None, pattern=r"^\d{4}-\d{2}-\d{2}$")):

    """Belirli bir günün (varsayılan bugün) en çok CPU/RAM tüketen programları + zirve değerler."""
    return await _history.report_today(day)


@router.get("/report/days")
@limiter.limit("30/minute")
async def report_days(request: Request, limit: int = Query(30, ge=1, le=365)):

    """Raporu olan günlerin listesi (en yeni önce) — geçmiş gün gezinmesi için."""
    return {"days": await _history.report_available_days(limit)}


@router.get("/process/{pid}")
@limiter.limit("30/minute")
async def process_detail(request: Request, pid: int):

    """Tek bir process'in ayrıntısı (tam komut, durum, I/O)."""
    d = await asyncio.to_thread(monitor.process_detail, pid)
    if d is None:
        raise HTTPException(status_code=404, detail=M("monitor.surec-bulunamadi"))
    return d


@router.get("/doctor")
@limiter.limit("100/minute")
async def doctor(request: Request):

    """Yuki Sistem Doktoru — snapshot özeti → kısa Türkçe AI yorum."""
    from app.services.llm import quick_ask

    snap = await asyncio.to_thread(monitor.snapshot, include_processes=False)
    hist = await _history.query_range("1h")
    rep = await _history.report_today()

    cpu = snap.get("cpu") or {}
    mem = snap.get("mem") or {}
    gnv = snap.get("gpu_nvidia") or {}

    lines = [
        f"Sağlık: {snap.get('health_score', '?')}/100",  # i18n-istisna: LLM'e giden prompt/özet
        f"CPU: %{cpu.get('total', 0):.0f}, {cpu.get('temp_c', '?')}°C, yük {cpu.get('load_avg', [0])[0]:.1f}",  # i18n-istisna: LLM'e giden prompt/özet
        f"RAM: {mem.get('used_gb', 0):.1f}/{mem.get('total_gb', 0):.0f}GB (%{mem.get('percent', 0):.0f})",
    ]
    if gnv:
        lines.append(
            f"GPU: {gnv.get('name', '')}, util%{gnv.get('util', 0)}, "
            f"VRAM {gnv.get('vram_used_mb', 0)}/{gnv.get('vram_total_mb', 0)}MB, {gnv.get('temp_c', '?')}°C"
        )
    if hist:
        tail = hist[-5:]
        cpu_tr = [f"%{r.get('cpu', 0):.0f}" for r in tail]
        lines.append(f"1s CPU trendi: {', '.join(cpu_tr)}")
    if rep.get("top_cpu"):
        top = rep["top_cpu"][0]
        lines.append(f"Bugün en çok CPU: {top['name']} ({top['cpu_sec']}s)")  # i18n-istisna: LLM'e giden prompt/özet
    alerts = snap.get("alerts", [])
    alert_txt = "; ".join(a.get("msg", "") for a in alerts) if alerts else "yok"
    lines.append(f"Uyarılar: {alert_txt}")  # i18n-istisna: LLM'e giden prompt/özet

    summary_text = "\n".join(lines)
    prompt = (
        f"Mevcut sistem durumu:\n{summary_text}\n\n"
        "Bu verilere göre 2-3 cümlelik kısa Türkçe yorum yaz. "  # i18n-istisna: LLM'e giden prompt/özet
        "Kullanıcıya hitap et, samimi ol. Sorun yoksa kısa onayla; "  # i18n-istisna: LLM'e giden prompt/özet
        "varsa açık öneri ver."  # i18n-istisna: LLM'e giden prompt/özet
    )
    text = await quick_ask(
        prompt,
        system="Sen Yuki, kullanıcının kişisel AI asistanısın. Sistem durumunu analiz et, samimi ve özlü yaz.",  # i18n-istisna: LLM'e giden prompt/özet
    )
    if not text:
        text = M("monitor.doktor-yorumlanamadi")

    return {
        "ok": bool(text),
        "summary": text,
        "ts": snap.get("ts"),
        "health": snap.get("health_score"),
    }
