"""Küçük JSON depoları için güvenli okuma/yazma.

🔴 Neden var (2026-11-10 gizli hata turu): notlar ve rutinler düz `write_text` ile yazılıyor,
okuma hatasında boş liste dönülüyordu. Yarıda kesilen bir yazım (kapanma, disk dolu) yarım JSON
bırakır → sonraki okuma `[]` → sonraki ekleme dosyayı tek kayıtla yeniden yazar → öncekilerin
HEPSİ yedeksiz gider. Burada: yazım atomik, bozuk dosya ezilmeden önce `.bozuk-<zaman>` olur.
"""

from __future__ import annotations

import json
import logging
import os
import shutil
import time
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)


def oku(yol: Path, varsayilan: Any, tur: type) -> Any:
    """`tur` tipinde içerik; dosya yoksa `varsayilan`, bozuksa kopyalanır ve `varsayilan`."""
    try:
        veri = json.loads(Path(yol).read_text(encoding="utf-8"))
    except FileNotFoundError:
        return varsayilan
    except OSError as e:
        logger.warning("%s okunamadı: %s", Path(yol).name, e)
        return varsayilan
    except ValueError as e:                 # JSONDecodeError + UnicodeDecodeError
        bozugu_sakla(yol, e)
        return varsayilan
    if isinstance(veri, tur):
        return veri
    bozugu_sakla(yol, ValueError(f"beklenen {tur.__name__}, gelen {type(veri).__name__}"))
    return varsayilan


def bozugu_sakla(yol: Path, sebep: Exception) -> None:
    yol = Path(yol)
    yedek = yol.with_name(f"{yol.name}.bozuk-{time.strftime('%Y%m%d-%H%M%S')}")
    try:
        if not yedek.exists():
            shutil.copy2(yol, yedek)
        logger.error("%s okunamadı (%s) — kopyası %s; boş başlanıyor", yol.name, sebep, yedek.name)
    except OSError as e:
        logger.error("bozuk %s yedeklenemedi (%s)", yol.name, e)


def yaz(yol: Path, veri: Any) -> None:
    """Geçici dosyaya yaz + `os.replace`: yarıda kalan yazım eski dosyayı bozmaz."""
    yol = Path(yol)
    yol.parent.mkdir(parents=True, exist_ok=True)
    gecici = yol.with_name(f".{yol.name}.{os.getpid()}.tmp")
    try:
        gecici.write_text(json.dumps(veri, ensure_ascii=False, indent=2), encoding="utf-8")
        os.replace(gecici, yol)
    except BaseException:
        gecici.unlink(missing_ok=True)
        raise
