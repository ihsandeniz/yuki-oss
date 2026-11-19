"""Memory API — Yuki'nin hafıza sistemini yönetmek için REST endpoint'leri.

GET  /api/memory            → anı listesi (pagination)
GET  /api/memory/search     → semantik arama (?q=)
POST /api/memory            → manuel anı ekle
DELETE /api/memory/{id}     → tek anı sil
POST /api/memory/cleanup    → eski/önemsiz anıları temizle
GET  /api/memory/stats      → toplam sayı + memory durumu
"""

from __future__ import annotations

from datetime import datetime
from typing import Optional

from fastapi import APIRouter, HTTPException, Query, Request
from pydantic import BaseModel, Field

from app.config import MEMORY_ENABLED, SESSION_ID
from app.limiter import limiter
from app.mesajlar import M
from app.services.memory import get_memory_service

router = APIRouter(prefix="/api/memory", tags=["memory"])


# ------------------------------------------------------------------ #
# Pydantic modeller
# ------------------------------------------------------------------ #


# Canlı persona kaydı — karakter eklenince/çıkınca burası ayrıca güncellenmez.
from app.services.personas import PERSONAS as _VALID_CHARS  # noqa: E402


class MemoryItem(BaseModel):
    id: int
    session_id: str
    role: str
    content: str
    category: str
    scope: Optional[str] = None
    importance: float
    created_at: datetime
    similarity: float = 0.0
    character_key: str = "yuki"


class AddMemoryRequest(BaseModel):
    content: str = Field(min_length=1, max_length=2000)
    role: str = "system"
    category: str = Field(default="fact", pattern="^(conversation|preference|fact|task)$")
    importance: float = Field(default=0.8, ge=0.0, le=1.0)
    session_id: str = SESSION_ID
    character_key: Optional[str] = None


class UpdateMemoryRequest(BaseModel):
    importance: Optional[float] = Field(default=None, ge=0.0, le=1.0)
    content: Optional[str] = Field(default=None, min_length=1, max_length=2000)


class CleanupRequest(BaseModel):
    importance_threshold: float = Field(default=0.35, ge=0.0, le=1.0)
    days_old: int = Field(default=7, ge=1)
    session_id: str = SESSION_ID
    character_key: Optional[str] = None


# ------------------------------------------------------------------ #
# Endpoint'ler
# ------------------------------------------------------------------ #


def _check_enabled():
    if not MEMORY_ENABLED:
        raise HTTPException(status_code=503, detail=M("hafiza.devre-disi"))


def _semantic_entitled() -> bool:
    """Bu kurulumda semantik hafıza (Ultra) yetkisi var mı?

    llm.py `_semantic_memory_allowed()` ile aynı kaynak — tek fark, buradaki REST
    yüzeyi sohbet akışından bağımsız çağrılabildiği için gate'in burada da olması
    gerekir. Olmadığında Free kullanıcı POST /api/memory ile semantik depoya yazıp
    /search ile anlamca arayabiliyordu (paywall fiilen delik).
    Hata → False (Ultra sızmasın), dev YUKI_PACKAGE=full → True.
    """
    try:
        from app.services import yetki
        return yetki.feature_allowed("semantic_memory")
    except Exception:
        return False


def _require_semantic():
    """Yazma yolu: yetkisizse net reddet (sessiz başarısızlık kullanıcıyı yanıltır)."""
    if not _semantic_entitled():
        raise HTTPException(status_code=403, detail=M("hafiza.semantik-ultra"))


def _motor_hazir() -> bool:
    """Gömme motoru çalışabilir mi — sohbetin lite'a düşme kararıyla aynı kaynak (llm.py)."""
    try:
        from app.services.llm import _embedding_engine_ready
        return _embedding_engine_ready()
    except Exception:
        return False


def _require_motor():
    """Gömme gerektiren yazma: model yoksa 503 + ne yapılacağı. Eskiden README yolunda
    (MEMORY_BACKEND=sqlite, model yok) ModuleNotFoundError → 'Beklenmeyen hata' 500 idi
    (temiz klonda ölçüldü)."""
    if not _motor_hazir():
        raise HTTPException(status_code=503, detail=M("hafiza.model-yok"))


def _validate_char(character_key: Optional[str]) -> Optional[str]:
    """character_key geçerli mi kontrol et; geçersizse 422 fırlat."""
    if character_key is not None and character_key not in _VALID_CHARS:
        raise HTTPException(
            status_code=422,
            detail=M("hafiza.gecersiz-karakter",
                     kod=character_key, gecerli=sorted(_VALID_CHARS)),
        )
    return character_key


@router.get("", response_model=list[MemoryItem])
@limiter.limit("100/minute")
async def list_memories(
    request: Request,
    session_id: str = SESSION_ID,
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    category: Optional[str] = None,
    character_key: Optional[str] = Query(default=None),
    q: Optional[str] = Query(default=None, max_length=200),
):
    """Tüm anıları listele (yeniden eskiye). character_key belirtilmezse aktif persona kullanılır.

    `q` = kelime araması (içerikte birebir geçen, Türkçe harf katlamalı). Anlamca
    arama (`/search`) kısa satırlara ("sa", "selam") her sorguda yüksek benzerlik
    veriyordu — HAFIZA paneli önce buna bakar, sonuç yoksa anlamcaya düşer."""
    _check_enabled()
    # Okuma yolu: yetkisizken 403 yerine boş liste — hafıza paneli bu ucu doğrudan
    # çağırıyor, 403 UI'ı kırardı. Veri silinmez; Ultra'ya dönünce yine görünür.
    if not _semantic_entitled():
        return []
    mem = get_memory_service()
    items = await mem.list_all(
        session_id=session_id, limit=limit, offset=offset, category=category,
        character_key=_validate_char(character_key), icerik=(q or "").strip() or None,
    )
    return [MemoryItem(**vars(m)) for m in items]


@router.get("/export")
@limiter.limit("100/minute")
async def export_memories(
    request: Request,
    session_id: str = SESSION_ID,
    character_key: Optional[str] = Query(default=None),
):
    """Tüm anıları indirilebilir JSON olarak dışa aktar (B8 — gizlilik/kullanıcı kontrolü).

    'Her şey senin, istediğinde dışa aktar' — veri makinede kalır, kullanıcı sahibidir.

    🔴 2026-08-06 — SATILAN PAKETTE ölçüldü (Yuki-0.5.8-lite.AppImage): bu uç
    kapısızdı ve **anıların tam içeriğini Free kademede döküyordu**, aynı anda
    `list` boş liste, `stats` `total: 0` diyorken. Yani gizleme kararı üç uçta
    uygulanmış, dördüncüsünde atlanmıştı — 2026-07-28'deki kusurun aynı sınıfı.

    Neden `list` gibi boş dönmüyor da 403: `list`in yumuşatılma gerekçesi
    "hafıza paneli bu ucu doğrudan çağırıyor, 403 UI'ı kırardı". Export panel
    açılışında değil, kullanıcının bastığı düğmeden çağrılıyor
    (`frontend/js/core.js`) → o gerekçe burada geçerli değil, sessizce boş
    dosya indirtmek kullanıcıyı yanıltır.
    """
    _check_enabled()
    _require_semantic()
    from fastapi.responses import JSONResponse
    from fastapi.encoders import jsonable_encoder
    mem = get_memory_service()
    items = await mem.list_all(
        session_id=session_id, limit=100000, offset=0,
        character_key=_validate_char(character_key),
    )
    data = [jsonable_encoder(MemoryItem(**vars(m))) for m in items]
    return JSONResponse(
        content={"exported_at": datetime.now().isoformat(), "count": len(data), "memories": data},
        headers={"Content-Disposition": "attachment; filename=yuki-hafiza.json"},
    )


@router.get("/search", response_model=list[MemoryItem])
@limiter.limit("20/minute")
async def search_memories(
    request: Request,
    q: str = Query(..., min_length=1),
    session_id: str = SESSION_ID,
    limit: int = Query(default=10, ge=1, le=50),
    min_similarity: float = Query(default=0.3, ge=0.0, le=1.0),
    category: Optional[str] = None,
    character_key: Optional[str] = Query(default=None),
):
    """Semantik benzerlikle anı ara. character_key belirtilmezse aktif persona kullanılır."""
    _check_enabled()
    # Ultra özelliğinin ta kendisi — yetkisizde boş sonuç (bkz. list_memories notu).
    # Gömme modeli yoksa da boş: sohbet bu durumda lite hafızaya düşer, uç 500 vermesin.
    if not _semantic_entitled() or not _motor_hazir():
        return []
    mem = get_memory_service()
    items = await mem.search(
        query=q,
        limit=limit,
        session_id=session_id,
        min_similarity=min_similarity,
        category=category,
        character_key=_validate_char(character_key),
    )
    return [MemoryItem(**vars(m)) for m in items]


@router.get("/engine")
@limiter.limit("100/minute")
async def memory_engine(request: Request):
    """Semantik hafıza motorunun durumu — frontend'in model indirme kararı için.

    `ready=false` + `needs_model=true` → embedding modeli eksik (indir-gerektiğinde);
    `allowed=false` → kademe yetmiyor (Free/Pro), model indirmenin anlamı yok.
    """
    from app.config import EMBED_BACKEND, MEMORY_BACKEND
    from app.services import embedding_onnx

    try:
        from app.services import yetki
        allowed = yetki.feature_allowed("semantic_memory")
    except Exception:
        allowed = False

    onnx_ready = embedding_onnx.available()
    # "st" modunda sentence-transformers kuruluysa model dosyası gerekmez (geliştirme).
    needs_model = (EMBED_BACKEND != "st") and not onnx_ready
    return {
        "memory_backend": MEMORY_BACKEND,
        "embed_backend": EMBED_BACKEND,
        "model_present": onnx_ready,
        "allowed": allowed,
        "needs_model": bool(needs_model),
        "ready": bool(MEMORY_ENABLED and allowed and not needs_model),
    }


@router.get("/stats")
@limiter.limit("100/minute")
async def memory_stats(
    request: Request,
    session_id: str = SESSION_ID,
    character_key: Optional[str] = Query(default=None),
):
    """Hafıza durumu, toplam anı sayısı ve kapsam bazlı dağılım."""
    if not MEMORY_ENABLED or not _semantic_entitled():
        # Yetkisizken "enabled: true, total: 5" demek yanıltıcı olurdu — panelde
        # görünmeyen anıların sayısını sızdırır. Kapalı durum tek biçimde raporlanır.
        # `yetkili`: panel "Ultra gerekli" ile "hafıza bu kurulumda kapalı"yı ayırsın —
        # ikisi de enabled=false; kapalıyken "Ultra'ya geç" demek Ultra kullanıcıya yalan olurdu.
        return {"enabled": False, "total": 0, "session_id": session_id,
                "scopes": {}, "categories": {}, "yetkili": _semantic_entitled()}
    mem = get_memory_service()
    data = await mem.stats(session_id=session_id, character_key=_validate_char(character_key))
    return {
        "enabled": True,
        "total": data.get("total", 0),
        "character_key": data.get("character_key", "?"),
        "session_id": session_id,
        "scopes": data.get("scopes", {}),
        # Süzgeç sayaçlarının kaynağı — `scopes` DEĞİL (ayrı kavram, bkz.
        # `memory.py::stats` yorumu). Panel bu alanı okur.
        "categories": data.get("categories", {}),
    }


@router.post("", response_model=dict)
@limiter.limit("50/minute")
async def add_memory(request: Request, req: AddMemoryRequest):
    """Manuel anı ekle (tercih, gerçek, not gibi kalıcı bilgiler için)."""
    _check_enabled()
    _require_semantic()   # yazma yolu = paywall'ın asıl kapısı
    _require_motor()
    mem = get_memory_service()
    memory_id = await mem.add(
        content=req.content,
        role=req.role,
        category=req.category,
        importance=req.importance,
        session_id=req.session_id,
        character_key=_validate_char(req.character_key),
    )
    return {"status": "ok", "id": memory_id}


@router.put("/{memory_id}", response_model=dict)
@limiter.limit("30/minute")
async def update_memory(request: Request, memory_id: int, req: UpdateMemoryRequest):

    """Anının importance veya içeriğini güncelle."""
    _check_enabled()
    _require_semantic()   # yazma yolu — POST ile aynı sınıf (2026-08-06'da eksikti)
    if req.importance is None and req.content is None:
        raise HTTPException(status_code=400, detail=M("hafiza.alan-eksik"))
    if req.content is not None:
        _require_motor()   # içerik değişirse vektör yeniden hesaplanır
    mem = get_memory_service()
    updated = await mem.update(memory_id, importance=req.importance, content=req.content)
    if not updated:
        raise HTTPException(status_code=404, detail=M("hafiza.ani-bulunamadi", id=memory_id))
    return {"status": "ok", "updated_id": memory_id}


@router.delete("/{memory_id}")
@limiter.limit("30/minute")
async def delete_memory(request: Request, memory_id: int):

    """Tek anıyı sil."""
    _check_enabled()
    # 🔴 Ölçüldü (satılan paket, 2026-08-06): kapısızdı — Free kademe Ultra
    # döneminde yazılmış anıyı gerçekten SİLİYORDU (HTTP 200, deleted_id döndü).
    # Yıkıcı yol, okuma yumuşatmasına girmez.
    _require_semantic()
    mem = get_memory_service()
    deleted = await mem.delete(memory_id)
    if not deleted:
        raise HTTPException(status_code=404, detail=M("hafiza.ani-bulunamadi", id=memory_id))
    return {"status": "ok", "deleted_id": memory_id}


@router.post("/cleanup")
@limiter.limit("100/minute")
async def cleanup_memories(request: Request, req: CleanupRequest = CleanupRequest()):

    """Eski ve düşük önemli conversation anılarını temizle."""
    _check_enabled()
    _require_semantic()   # toplu silme — yıkıcı, yazma yolu (2026-08-06'da eksikti)
    mem = get_memory_service()
    deleted_count = await mem.cleanup(
        session_id=req.session_id,
        importance_threshold=req.importance_threshold,
        days_old=req.days_old,
        character_key=_validate_char(req.character_key),
    )
    return {"status": "ok", "deleted": deleted_count}
