"""Merkezi logging yapılandırması — tüm modüller için tek format."""

import json
import logging
import os
import time
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    pass


class _ScrubFilter(logging.Filter):
    """Filter: masks secrets in log records before they reach handlers."""

    def filter(self, record: logging.LogRecord) -> bool:
        """Scrub the fully-formatted message to remove credentials."""
        try:
            from app.services.credential_scrubber import scrub
            # getMessage() msg % args'ı ORİJİNAL tiplerle uygular (%d/%f + int
            # bozulmaz); tam metni scrub'layıp args'ı temizliyoruz ki handler
            # tekrar %-format uygulamasın.
            record.msg = scrub(record.getMessage())
            record.args = ()
        except Exception:
            # Scrub başarısızsa log'u olduğu gibi geçir (fail-open)
            pass
        return True


class _JsonFormatter(logging.Formatter):
    """Compact JSON log formatter: {"t":..., "lvl":..., "logger":..., "msg":...}"""

    def format(self, record: logging.LogRecord) -> str:
        entry: dict = {
            "t": time.strftime("%H:%M:%S", time.localtime(record.created)),
            "lvl": record.levelname,
            "logger": record.name,
            "msg": record.getMessage(),
        }
        if record.exc_info:
            entry["exc"] = self.formatException(record.exc_info)
        return json.dumps(entry, ensure_ascii=False)


def setup_logging() -> None:
    """Root logger'ı yapılandır. Lifespan başında bir kez çağrılır.

    LOG_FORMAT=json  → JSON satırları (makine okunabilir, analiz için)
    LOG_FORMAT=text  → İnsan okunabilir metin (varsayılan)
    """
    level = os.getenv("LOG_LEVEL", "INFO").upper()
    log_format = os.getenv("LOG_FORMAT", "text").lower()

    root = logging.getLogger()
    root.setLevel(getattr(logging, level, logging.INFO))

    # Add credential scrubbing filter to root logger (all handlers will use it)
    root.addFilter(_ScrubFilter())

    if log_format == "json":
        handler = logging.StreamHandler()
        handler.setFormatter(_JsonFormatter())
        root.handlers.clear()
        root.addHandler(handler)
    else:
        logging.basicConfig(
            level=getattr(logging, level, logging.INFO),
            format="%(asctime)s | %(levelname)-7s | %(name)s | %(message)s",
            datefmt="%H:%M:%S",
            force=True,
        )

    # Uvicorn access loglarını sustur (her istek için satır basar)
    logging.getLogger("uvicorn.access").setLevel(logging.WARNING)
    # httpx debug loglarını sustur
    logging.getLogger("httpx").setLevel(logging.WARNING)
