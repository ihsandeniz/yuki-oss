"""Google OAuth token'larının TEK kaynağı.

🔴 **Neden bu modül var — iki kusur birden (ölçüldü 2026-09-14):**

① **Salt okunur dizine yazma.** `api/planner.py` token'ı `backend/planner_tokens.json`'a
   yazıyordu: `Path(__file__).parent.parent.parent`. Satılan pakette o dizin **salt
   okunurdur** (AppImage / `resources/`), yani kullanıcı Google'a bağlansa bile oturumu
   **kaydedilemezdi**. Bu, 2026-07-31'de kapatılan dört kusurun (`config_manager` ·
   `routines.py` · `calendar.py` · `monitoring/history.py`) **atlanmış beşinci kardeşidir** —
   o turda `calendar.py` düzeltildi, aynı dosyayı yazan `planner.py` gözden kaçtı.

② **Aynı soruya iki yerde cevap.** `calendar.py` `YUKI_DATA_DIR` altına, `planner.py`
   `backend/`e bakıyordu. İkisi de "planner_tokens.json" diyordu ama **farklı dosyaydı**:
   kullanıcı AYAR'dan bağlanır, sohbette *"takvimime bak"* der ve Yuki *"bağlı değilsin"*
   cevabını verirdi. `surum.js` dersinin aynısı: aynı soruya iki cevap üretilirse er geç
   ayrışırlar ve ayrıştıkları yere kimse bakmaz.

📏 Bu yüzden yol **burada bir kez** hesaplanır. Yeni bir Google özelliği (Drive) eklerken
   kendi dosyanı açma — buradan oku.
"""

from __future__ import annotations

import json
import logging
import os
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

#: Yazılabilir veri kökü. Electron paketlenmiş koşuda `YUKI_DATA_DIR`'i
#: `<userData>`e set eder; geliştirmede proje köküne düşer.
#: ⚠️ `config.DATA_DIR`'i import ETMİYORUZ — `calendar.py` bir *araç* modülü ve
#: `app.config`'i çekmesi import zincirini ağırlaştırırdı; aynı env değişkeni okunur.
def _veri_koku() -> Path:
    ham = os.getenv("YUKI_DATA_DIR")
    if ham:
        return Path(ham)
    # backend/app/services/google_token_store.py → backend/
    return Path(__file__).resolve().parents[2]


def token_dosyasi() -> Path:
    return _veri_koku() / "planner_tokens.json"


def durum_dosyasi() -> Path:
    """OAuth CSRF `state` deposu — token'la aynı yazılabilirlik kuralına tabi."""
    return _veri_koku() / "planner_state_tokens.json"


def yukle() -> dict[str, Any]:
    """Tüm sağlayıcıların token'ları. Dosya yoksa/bozuksa boş iskelet döner."""
    yol = token_dosyasi()
    if yol.exists():
        try:
            veri = json.loads(yol.read_text())
            if isinstance(veri, dict):
                return veri
        except Exception as e:
            logger.warning("planner_tokens.json okunamadı (%s) — boş kabul edildi", e)
    return {"google": None, "microsoft": None}


def kaydet(veri: dict[str, Any]) -> None:
    """Atomik yaz + dosya iznini daralt.

    ⚠️ Yazma **atomik**: yarım yazma (disk dolu / kapanma) token dosyasını bozarsa
    kullanıcı yeniden bağlanmak zorunda kalır ve sebebi hiçbir yerde yazmaz.
    ⚠️ `chmod` Windows'ta anlamlı bir şey yapmaz ama **hata da vermez**; POSIX'te
    0600 şart — dosya refresh token taşıyor, yani kalıcı hesap erişimi.
    """
    yol = token_dosyasi()
    yol.parent.mkdir(parents=True, exist_ok=True)
    gecici = yol.with_suffix(".json.tmp")
    gecici.write_text(json.dumps(veri, indent=2))
    try:
        os.chmod(gecici, 0o600)
    except Exception:
        pass
    os.replace(gecici, yol)


def google_al() -> dict[str, Any] | None:
    return yukle().get("google")


def google_yaz(tok: dict[str, Any] | None) -> None:
    veri = yukle()
    veri["google"] = tok
    kaydet(veri)
