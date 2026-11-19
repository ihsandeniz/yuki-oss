"""Faz U — Media API: yükleme, listeleme, servis, sohbete gönderme."""
import base64
import logging
import mimetypes
import uuid
from pathlib import Path

from fastapi import APIRouter, HTTPException, Query, Request, UploadFile
from app.limiter import limiter
from app.mesajlar import M
from fastapi.responses import FileResponse, Response

from app.services.event_bus import bus

log = logging.getLogger(__name__)

# ── Config ────────────────────────────────────────────────────────────────────
from app.config import DATA_DIR
MEDIA_DIR = DATA_DIR / "media_uploads"   # yazılabilir dizin (read-only AppImage mount fix)
try:
    MEDIA_DIR.mkdir(parents=True, exist_ok=True)
except OSError:
    pass

IMAGE_EXT = {".jpg", ".jpeg", ".png", ".gif", ".webp"}
# Doküman türleri — içerik doc_reader ile metne çevrilip sohbete iletilir
from app.services.doc_reader import DOC_EXTENSIONS as DOC_EXT
ALLOWED_EXT = IMAGE_EXT | DOC_EXT
MAX_BYTES = 15 * 1024 * 1024  # 15 MB

_EXT_MIME = {
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
    ".png": "image/png",
    ".gif": "image/gif",
    ".webp": "image/webp",
    ".pdf": "application/pdf",
    ".xlsx": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    ".xls": "application/vnd.ms-excel",
    ".docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    ".csv": "text/csv",
    ".txt": "text/plain",
    ".md": "text/markdown",
    ".json": "application/json",
    ".log": "text/plain",
}

router = APIRouter(prefix="/api/media", tags=["media"])


# ── Yardımcı ─────────────────────────────────────────────────────────────────
def _safe_path(filename: str) -> Path:
    """Dosya adını doğrular ve güvenli tam yol döner. Path traversal önlemi."""
    safe = (MEDIA_DIR / filename).resolve()
    if safe.parent != MEDIA_DIR.resolve():
        raise HTTPException(status_code=400, detail=M("medya.gecersiz-ad"))
    return safe


def _ext_to_mime(ext: str) -> str:
    return _EXT_MIME.get(ext.lower(), "application/octet-stream")


# ── POST /api/media/upload ────────────────────────────────────────────────────
@router.post("/upload")
@limiter.limit("20/minute")
async def upload_media(request: Request, file: UploadFile):
    """Multipart dosya yükle. Döner: {filename, url}."""
    ext = Path(file.filename or "").suffix.lower()
    if ext not in ALLOWED_EXT:
        raise HTTPException(
            status_code=400,
            detail=M("medya.format", izinli=", ".join(ALLOWED_EXT)),
        )

    content = await file.read()
    if len(content) > MAX_BYTES:
        raise HTTPException(status_code=413, detail=M("medya.dosya-buyuk"))

    # Orijinal adı (güvenli hâliyle) koru — dokümanlarda ad anlamlı (rapor.pdf vb.)
    stem = "".join(c for c in Path(file.filename or "dosya").stem if c.isalnum() or c in "-_ ")[:48].strip() or "dosya"
    safe_name = f"{stem}_{uuid.uuid4().hex[:8]}{ext}"
    dest = MEDIA_DIR / safe_name
    dest.write_bytes(content)

    log.info("[media] Yüklendi: %s (%d bytes)", safe_name, len(content))
    return {
        "filename": safe_name,
        "url": f"/api/media/file/{safe_name}",
        "kind": "image" if ext in IMAGE_EXT else "doc",
    }


# ── GET /api/media/list ───────────────────────────────────────────────────────
@router.get("/list")
@limiter.limit("100/minute")
async def list_media(request: Request):
    """Kaydedilen medya dosyalarını listeler. Yeniden eskiye sıralı."""
    files = []
    for p in sorted(MEDIA_DIR.iterdir(), key=lambda x: x.stat().st_mtime, reverse=True):
        ext = p.suffix.lower()
        if ext in ALLOWED_EXT:
            st = p.stat()
            files.append(
                {
                    "filename": p.name,
                    "url": f"/api/media/file/{p.name}",
                    "size": st.st_size,
                    "created": st.st_mtime,
                    "mime": _ext_to_mime(p.suffix),
                    "kind": "image" if ext in IMAGE_EXT else "doc",
                }
            )
    return {"files": files, "count": len(files)}


# ── GET /api/media/file/{filename} ───────────────────────────────────────────
@router.get("/file/{filename}")
@limiter.limit("100/minute")
async def serve_media(request: Request, filename: str):
    """Dosyayı statik olarak servis et."""
    path = _safe_path(filename)
    if not path.exists():
        raise HTTPException(status_code=404, detail=M("medya.bulunamadi"))
    media_type = _ext_to_mime(path.suffix)
    return FileResponse(
        path=str(path),
        media_type=media_type,
        headers={"Cache-Control": "max-age=86400"},
    )


# ── POST /api/media/send-to-chat/{filename} ───────────────────────────────────
@router.post("/send-to-chat/{filename}")
@limiter.limit("30/minute")
async def send_to_chat(request: Request, filename: str):
    """GÖRSELİ base64'e çevirip image_msg event'i yayınlar → WebSocket → chat.

    Dokümanlar için bu endpoint kullanılmaz — frontend /extract ile metni alıp
    sohbet kanalından iletir.
    """
    path = _safe_path(filename)
    if not path.exists():
        raise HTTPException(status_code=404, detail=M("medya.bulunamadi"))
    if path.suffix.lower() not in IMAGE_EXT:
        raise HTTPException(status_code=400, detail=M("medya.yalniz-gorsel"))

    b64 = base64.b64encode(path.read_bytes()).decode()
    mime = _ext_to_mime(path.suffix)
    await bus.publish("image_msg", {"data": b64, "mime": mime, "source": "user_gallery"})

    log.info("[media] Sohbete gönderildi: %s", filename)
    return {"ok": True, "filename": filename}


# ── GET /api/media/extract/{filename} ────────────────────────────────────────
@router.get("/extract/{filename}")
@limiter.limit("10/minute")
async def extract_document(request: Request, filename: str):
    """Dokümandan metin çıkarır (pdf/xlsx/xls/docx/csv/txt/md/json/log).

    Frontend bu metni sohbet mesajına gömerek Yuki'ye iletir.
    """
    from app.services.doc_reader import extract_text

    path = _safe_path(filename)
    if not path.exists():
        raise HTTPException(status_code=404, detail=M("medya.bulunamadi"))
    if path.suffix.lower() not in DOC_EXT:
        raise HTTPException(status_code=400, detail=M("medya.metin-cikmaz"))

    result = extract_text(path)
    if result["error"]:
        raise HTTPException(status_code=422, detail=result["error"])
    log.info("[media] Metin çıkarıldı: %s (%d karakter)", filename, result["chars"])
    return {"filename": filename, **result}


# ── DELETE /api/media/file/{filename} ────────────────────────────────────────
@router.delete("/file/{filename}")
@limiter.limit("30/minute")
async def delete_media(request: Request, filename: str):
    """Dosyayı diskten sil."""
    path = _safe_path(filename)
    if not path.exists():
        raise HTTPException(status_code=404, detail=M("medya.bulunamadi"))
    path.unlink()
    log.info("[media] Silindi: %s", filename)
    return {"ok": True, "filename": filename}
