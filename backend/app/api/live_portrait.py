"""
Faz 13 — fal.ai Micro-Animation API
Model: fal-ai/wan/v2.1/image-to-video (WAN i2v)

Yuki avatar için mikro animasyon klipleri üretir ve disk'e önbelleğe alır.
Bir aksiyon ilk kez istendiğinde fal.ai'ye istek gider, MP4 kaydedilir.
Sonraki istekler disk cache'den hızlıca sunulur.
"""
import logging
import os
from pathlib import Path

import fal_client
import httpx
from fastapi import APIRouter, HTTPException, Request, Response
from fastapi.responses import FileResponse

from app.limiter import limiter
from app.mesajlar import M

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/live-portrait", tags=["live-portrait"])

# fal-client FAL_KEY env'den otomatik okur; eksikse uyar
if not os.getenv("FAL_KEY"):
    logger.warning("FAL_KEY .env'de tanımlı değil — fal.ai animasyon devre dışı")

# Circuit breaker — art arda hata sonrası fal.ai çağrılarını durdurur
_fal_fail_count = 0
_FAL_CIRCUIT_OPEN = False
_FAL_MAX_FAILS = 3

# ── Disk cache dizini ────────────────────────────────────────────────────────
_BACKEND_DIR = Path(__file__).parent.parent.parent   # avatar görseli okuması için (read-only OK)
from app.config import DATA_DIR
CACHE_DIR = DATA_DIR / "anim_cache"   # yazılabilir dizin (read-only AppImage mount fix)
try:
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
except OSError:
    pass

# ── fal.ai model ─────────────────────────────────────────────────────────────
_MODEL = "fal-ai/wan/v2.1/image-to-video"

# Avatar URL — fal.ai storage'a bir kez yüklenir, bellekte tutulur
_avatar_fal_url: str | None = None

# ── Aksiyon → prompt haritası ─────────────────────────────────────────────────
_ACTION_PROMPTS: dict[str, dict] = {
    "eye_blink": {
        "prompt": "anime girl gently blinks her eyes once, natural slow blink, face and body perfectly still otherwise, subtle eyelid movement",
        "num_frames": 17,
        "resolution": "480p",
    },
    "eye_blink_double": {
        "prompt": "anime girl blinks her eyes twice in quick succession, natural double blink, head and body completely still",
        "num_frames": 25,
        "resolution": "480p",
    },
    "breath": {
        "prompt": "anime girl breathes gently, very subtle chest rise and fall, calm breathing, face expression unchanged, no head movement",
        "num_frames": 33,
        "resolution": "480p",
    },
    "head_tilt": {
        "prompt": "anime girl tilts her head slightly to the left, gentle curious tilt, soft expression, returns to neutral",
        "num_frames": 25,
        "resolution": "480p",
    },
    "look_away": {
        "prompt": "anime girl briefly glances to the upper right with her eyes, natural eye movement, head stays still, then looks back forward",
        "num_frames": 25,
        "resolution": "480p",
    },
    "look_at_user": {
        "prompt": "anime girl looks directly forward with a gentle focused gaze, eyes soft and attentive, slight smile",
        "num_frames": 17,
        "resolution": "480p",
    },
    "head_nod": {
        "prompt": "anime girl gives a subtle single approving nod, small gentle head movement downward then back up, calm expression",
        "num_frames": 25,
        "resolution": "480p",
    },
}

VALID_ACTIONS = set(_ACTION_PROMPTS.keys())


async def _get_avatar_fal_url() -> str:
    """Yuki avatar'ını fal.ai storage'a yükler (bellekte önbelleğe alınır)."""
    global _avatar_fal_url
    if _avatar_fal_url:
        return _avatar_fal_url

    avatar_path = _BACKEND_DIR.parent / "frontend" / "assets" / "characters" / "yuki_avatar.png"
    if not avatar_path.exists():
        raise FileNotFoundError(M("portre.avatar-yok", yol=str(avatar_path)))

    logger.info("fal.ai storage'a avatar yükleniyor: %s", avatar_path)
    url = await fal_client.upload_file_async(str(avatar_path))
    _avatar_fal_url = url
    logger.info("Avatar yüklendi: %s", url)
    return url


async def _generate_clip(action: str) -> Path:
    """fal.ai'den MP4 klip üretir ve disk cache'e kaydeder."""
    cfg = _ACTION_PROMPTS[action]
    avatar_url = await _get_avatar_fal_url()

    logger.info("fal.ai'den '%s' klibi üretiliyor…", action)
    result = await fal_client.run_async(
        _MODEL,
        arguments={
            "image_url": avatar_url,
            "prompt": cfg["prompt"],
            "num_frames": cfg["num_frames"],
            "resolution": cfg["resolution"],
            "motion_strength": 0.7,
        },
    )

    # Sonuç URL'sini al
    video_url: str | None = None
    if isinstance(result, dict):
        video_url = (
            result.get("video", {}).get("url")
            or result.get("video_url")
            or result.get("url")
        )
    if not video_url:
        raise ValueError(M("portre.video-url-yok", sonuc=str(result)))

    # MP4'ü indir ve cache'e kaydet
    out_path = CACHE_DIR / f"{action}.mp4"
    async with httpx.AsyncClient(timeout=60) as client:
        resp = await client.get(video_url)
        resp.raise_for_status()
        out_path.write_bytes(resp.content)

    logger.info("Klip kaydedildi: %s (%d bytes)", out_path, len(resp.content))
    return out_path


# ── Endpoint ──────────────────────────────────────────────────────────────────

_CLIP_HEADERS = {
    "Cache-Control": "public, max-age=604800",  # 7 gün
    "Accept-Ranges": "bytes",
}


@router.api_route("/clip", methods=["GET", "HEAD"])
@limiter.limit("20/minute")
async def get_clip(request: Request, action: str):
    """
    Micro-animation klibi döndürür.
    Disk cache varsa anında sunar; yoksa fal.ai'den üretir, sonra sunar.

    HEAD desteklenir: frontend (`core.js` → `playFalAnimation`) videoyu `<video>`'ya
    vermeden önce HEAD ile "servis ayakta mı" yokluyordu, ama uç yalnız GET kabul
    ettiği için her sayfa açılışında konsola **405** düşüyordu. HEAD artık ucuz
    kontrolleri (aksiyon geçerli mi · circuit açık mı · FAL_KEY var mı) çalıştırıp
    yanıt verir; pahalı fal.ai üretimini **tetiklemez** — o GET'e bırakılır.

    Query param:
      action: eye_blink | eye_blink_double | breath | head_tilt |
              look_away | look_at_user | head_nod
    """
    _head = request.method == "HEAD"
    if action not in VALID_ACTIONS:
        raise HTTPException(
            status_code=400,
            detail=M("portre.gecersiz-aksiyon", gecerliler=str(sorted(VALID_ACTIONS))),
        )

    cached = CACHE_DIR / f"{action}.mp4"
    if not cached.exists():
        global _fal_fail_count, _FAL_CIRCUIT_OPEN
        if _FAL_CIRCUIT_OPEN:
            raise HTTPException(
                status_code=503,
                detail=M("portre.devre-acik"),
            )
        fal_key = os.getenv("FAL_KEY")
        if not fal_key:
            raise HTTPException(
                status_code=503,
                detail=M("portre.anahtar-yok"),
            )
        if _head:
            # Ön yoklama başarılı: servis ayakta, üretim GET geldiğinde yapılacak.
            return Response(status_code=200, media_type="video/mp4", headers=_CLIP_HEADERS)
        try:
            cached = await _generate_clip(action)
            _fal_fail_count = 0  # başarıda sıfırla
        except Exception as e:
            _fal_fail_count += 1
            if _fal_fail_count >= _FAL_MAX_FAILS:
                _FAL_CIRCUIT_OPEN = True
                logger.error("fal.ai circuit breaker açıldı (%d art arda hata). Klip istekleri reddedilecek.", _fal_fail_count)
            else:
                logger.error("fal.ai klip üretimi başarısız (%s): %s", action, e)
            raise HTTPException(status_code=502, detail=M("portre.klip-hatasi", sebep=str(e)))

    if _head:
        return Response(status_code=200, media_type="video/mp4", headers=_CLIP_HEADERS)

    return FileResponse(
        path=str(cached),
        media_type="video/mp4",
        headers=_CLIP_HEADERS,
    )


@router.delete("/cache")
@limiter.limit("10/minute")
async def clear_cache(request: Request):
    """Tüm önbelleğe alınmış klipleri siler (yeniden üretmek için)."""
    global _avatar_fal_url
    deleted = []
    for f in CACHE_DIR.glob("*.mp4"):
        f.unlink()
        deleted.append(f.name)
    _avatar_fal_url = None  # avatar URL'sini de sıfırla
    return {"deleted": deleted}


@router.get("/status")
@limiter.limit("100/minute")
async def cache_status(request: Request):
    """Mevcut cache durumunu + katmanın KULLANILABİLİR olup olmadığını döndürür.

    🔴 2026-08-28: `available` alanı buraya eklendi çünkü arayüzün
    "bu özellik var mı" sorusunu sorabileceği tek yer `/clip`in HEAD yoklamasıydı
    ve o yoklama **503** döndürüyordu. Davranış doğruydu (katman kalıcı olarak
    kapanıyor, tek bir console.warn basılıyor) ama tarayıcı her 4xx/5xx için
    kendi *"Failed to load resource"* **error** satırını yazar — yani C1 kapısı
    (*açılışta konsol hatası = 0*) HER kullanıcıda, HER açılışta düşüyordu.
    Ölçüldü: `/ui/` yüklemesinde tek 4xx/5xx isteği buydu.

    Yetenek sorusu hata koduyla değil **veriyle** cevaplanır — ürünün başka
    yerinde zaten böyle (`/api/settings` → `available` + `unavailable_reason`,
    `/api/modes/platform` → `features`). Ayrıca sebep artık istemcinin durum
    kodundan tahmin ettiği şey değil, sunucunun bildiği şey.
    """
    clips = {}
    for action in VALID_ACTIONS:
        p = CACHE_DIR / f"{action}.mp4"
        clips[action] = {"cached": p.exists(), "size": p.stat().st_size if p.exists() else 0}

    onbellekte_var = any(v["cached"] for v in clips.values())
    anahtar_var = bool(os.getenv("FAL_KEY"))
    if _FAL_CIRCUIT_OPEN:
        sebep = M("portre.durum-devre-acik")
    elif not anahtar_var and not onbellekte_var:
        # Anahtar yok AMA klip önbellekteyse katman yine çalışır — üretim gerekmez.
        sebep = M("portre.durum-anahtar-yok")
    else:
        sebep = None

    return {
        "cache_dir": str(CACHE_DIR),
        "clips": clips,
        "circuit_open": _FAL_CIRCUIT_OPEN,
        "fail_count": _fal_fail_count,
        "available": sebep is None,
        "unavailable_reason": sebep,
    }


@router.post("/circuit-reset")
@limiter.limit("30/minute")
async def reset_circuit(request: Request):
    """Circuit breaker'ı sıfırlar (fal.ai yeniden denenebilir)."""
    global _fal_fail_count, _FAL_CIRCUIT_OPEN
    _fal_fail_count = 0
    _FAL_CIRCUIT_OPEN = False
    return {"ok": True, "circuit_open": False}
