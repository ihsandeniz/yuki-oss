"""Direct tool endpoints — wiki search + reminders + approval gate (bypasses LLM)."""
from fastapi import APIRouter, HTTPException, Query, Request
from app.limiter import limiter
from app.mesajlar import M
from pydantic import BaseModel

router = APIRouter()


# ── WIKI SEARCH ──────────────────────────────────────────────────────────────

@router.get("/api/wiki/search")
@limiter.limit("100/minute")
async def wiki_search_endpoint(request: Request, q: str = Query(..., min_length=1)):

    from app.services.tools.wiki import wiki_search
    result = wiki_search(q)
    return {"result": result}


# ── REMINDERS ────────────────────────────────────────────────────────────────

class ReminderCreate(BaseModel):
    message: str
    when: str  # "15 dakika sonra" / "14:30" / ISO datetime / "her 20 dakika"
    repeat: bool = False  # true → iptal edilene kadar periyodik tekrarlar


@router.get("/api/reminders")
@limiter.limit("100/minute")
async def get_reminders(request: Request):

    from app.services.scheduler import list_reminders
    return list_reminders()


@router.post("/api/reminders")
@limiter.limit("30/minute")
async def create_reminder(request: Request, body: ReminderCreate):

    from app.services.scheduler import (
        parse_when, parse_recurring, add_reminder, add_recurring_reminder,
        insan_aralik,
    )
    rec = parse_recurring(body.when)
    if body.repeat and rec is None:
        rec = parse_recurring("her " + body.when)
    if rec is not None:
        kwargs, human = rec
        job_id = add_recurring_reminder(body.message, kwargs, human)
        # `human` PARSE anında üretilen Türkçe metin; yanıtın cümlesi okuma
        # anında kurulur (`list_reminders` ile aynı kaynak). Kayda yazılan
        # `human` yalnız eski okuyucular için duruyor.
        return {"job_id": job_id, "kind": "repeat",
                "interval": insan_aralik(kwargs) or human}
    run_date = parse_when(body.when)
    if run_date is None:
        raise HTTPException(status_code=400,
                            detail=M("hatirlatici.gecersiz-zaman", ifade=repr(body.when)))
    job_id = add_reminder(body.message, run_date)
    return {"job_id": job_id, "kind": "once", "run_date": run_date.isoformat()}


@router.delete("/api/reminders/{job_id}")
@limiter.limit("30/minute")
async def delete_reminder(request: Request, job_id: str):

    from app.services.scheduler import cancel_reminder
    ok = cancel_reminder(job_id)
    if not ok:
        raise HTTPException(status_code=404, detail=M("hatirlatici.bulunamadi"))
    return {"ok": True}


# ── MODES ─────────────────────────────────────────────────────────────────────

class ModeStartRequest(BaseModel):
    mode_id: str


@router.post("/api/modes/start")
@limiter.limit("30/minute")
async def start_mode_endpoint(request: Request, body: ModeStartRequest):

    from app.services.tools.modes import start_mode
    result = await start_mode(body.mode_id)
    if result.startswith("Hata:"):
        raise HTTPException(status_code=404, detail=result)
    return {"ok": True, "result": result}


@router.get("/api/modes")
@limiter.limit("100/minute")
async def list_modes_endpoint(request: Request):

    from app.services.tools.modes import list_modes
    return {"result": list_modes()}


# ── TOOL APPROVAL GATE ───────────────────────────────────────────────────────

class ToolApprovalRequest(BaseModel):
    approval_id: str
    approved: bool


@router.post("/api/tool-approval")
@limiter.limit("100/minute")
async def resolve_tool_approval(request: Request, body: ToolApprovalRequest):

    from app.services.tools.approval_gate import resolve_approval
    ok = resolve_approval(body.approval_id, body.approved)
    if not ok:
        raise HTTPException(status_code=404, detail=M("onay.talep-yok"))
    return {"ok": True, "approved": body.approved}
