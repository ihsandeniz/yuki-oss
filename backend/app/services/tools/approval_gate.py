"""Tool Approval Gate — critical tool calls require explicit user confirmation."""

from __future__ import annotations

import asyncio
import contextvars
import uuid
from typing import Any

# Tools that require approval before execution (when TOOL_APPROVAL_ENABLED=true)
CRITICAL_TOOLS: frozenset[str] = frozenset({
    "write_file",
    "append_file",
    "start_mode",
    "extract_archive",
    "compress_file",
    "delete_calendar_event",
    # Wiki sayfasını ezer; write_file ile aynı sınıf.
    "wiki_write",
    # Yerel görseli buluttaki modele gönderir.
    "analyze_image",
})

# Ayardan BAĞIMSIZ onay isteyen araçlar (kullanıcı onay sistemini kapatsa bile).
ALWAYS_APPROVE: frozenset[str] = frozenset({
    # Google Takvim'den silme (2026-10-04 yayın şartı) — geri alınamaz ve
    # KULLANICINİN takvimi. Ürünün TOOL_APPROVAL_ENABLED varsayılanı false olduğundan
    # CRITICAL_TOOLS'ta durmak tek başına hiçbir şey yapmıyordu: sohbetteki bir yanlış
    # anlama toplantıyı sessizce silebiliyordu. Kişiselde b6d9d91'de onaya alındı.
    # Ekleme (create_calendar_event) bilerek dışarıda: geri alınabilir.
    "delete_calendar_event",
})

# In-process approval store: approval_id → (event, result)
_pending: dict[str, tuple[asyncio.Event, list[bool]]] = {}

APPROVAL_TIMEOUT_SECONDS = 30


#: Son `False` kararının nedeni: "kullanici" (reddetti) · "sure" (kimse cevaplamadı).
#: Dönüş değeri bool kalır; `call_tool` modele doğru cümleyi söylemek için buradan okur.
#: Eskiden ikisi tek cümleydi ("onaylanmadı veya süre doldu") ve model süre dolmasını
#: "reddettin" diye anlatıyordu. Çağrı başına ayrı: paralel araçlar ayrı görevdir.
_son_red_nedeni: contextvars.ContextVar[str] = contextvars.ContextVar("yuki_son_red_nedeni", default="")


def onay_bekliyor() -> bool:
    """Yanıt bekleyen bir onay penceresi var mı (ses kimliği o sırada sıkı eşik uygular)."""
    return bool(_pending)


def son_red_nedeni() -> str:
    return _son_red_nedeni.get()


async def request_approval(
    name: str, args: dict[str, Any], sunum: dict[str, Any] | None = None,
) -> bool:
    """Publish a tool_approval event and block until user approves/denies or timeout.

    `sunum` (opsiyonel) — insan diline çevrilmiş gösterim: {baslik, mesaj, satirlar}.
    Verilmezse arayüz eski biçimi çizer (araç adı + ham JSON parametreler).
    🔴 Neden var: maliyet onayı bir *satış yüzeyi*. "run_team" + JSON gösteren bir
    kutu, kullanıcının parasını harcayan kararı ham geliştirici çıktısıyla soruyor —
    bu üründe ham teknik metnin kullanıcıya yanlış teşhis ettirdiği iki vaka ölçüldü.
    """
    approval_id = str(uuid.uuid4())
    event = asyncio.Event()
    result: list[bool] = [False]  # mutable container for cross-coroutine write
    _pending[approval_id] = (event, result)

    try:
        from app.services.event_bus import bus
        await bus.publish("tool_approval", {
            "approval_id": approval_id,
            "tool": name,
            "args": args,
            "timeout": APPROVAL_TIMEOUT_SECONDS,
            **({"sunum": sunum} if sunum else {}),
        })
    except Exception:
        pass

    try:
        await asyncio.wait_for(event.wait(), timeout=APPROVAL_TIMEOUT_SECONDS)
        _son_red_nedeni.set("" if result[0] else "kullanici")
        return result[0]
    except asyncio.TimeoutError:
        _son_red_nedeni.set("sure")
        return False
    finally:
        _pending.pop(approval_id, None)


def resolve_approval(approval_id: str, approved: bool) -> bool:
    """Called by the API endpoint to signal a pending approval. Returns False if not found."""
    entry = _pending.get(approval_id)
    if entry is None:
        return False
    event, result = entry
    result[0] = approved
    event.set()
    return True


def onay_payi(name: str) -> float:
    """Araç süresine eklenecek onay bekleme payı (sn).

    🔴 Onay beklemesi `call_tool` İÇİNDE; runner ise her aracı TOOL_TIMEOUT (10 sn) ile
    kesiyordu — insan 10 sn içinde onaylamazsa araç "yanıt vermedi" diye düşüyor, onay
    kapısının kendi zaman aşımı hiç gelmiyordu. Onaya tabi araçta süre = onay penceresi
    + araç süresi. Kural `dispatcher.call_tool`daki onay koşuluyla aynı.
    """
    from app.config import TOOL_APPROVAL_ENABLED
    if name in ALWAYS_APPROVE or (TOOL_APPROVAL_ENABLED and name in CRITICAL_TOOLS):
        return float(APPROVAL_TIMEOUT_SECONDS)
    return 0.0
