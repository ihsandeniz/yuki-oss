"""Yuki backend paketi.

⚠️ Burada TEK bir iş yapılır ve **erken** yapılması şarttır: indirilen Python
paket ağaçlarını (`pydeps`) `sys.path`'e bağlamak. Bu dosya `app.*` altındaki
her şeyden önce çalışır — `app.config` ve `app.main` dahil. Bağlama daha geç
yapılsaydı, modülünü daha önce import etmiş bir yol kütüphaneyi bulamazdı.

`kur()` asla yükseltmez; bozuk bir ortam değişkeni açılışı engellememeli.
→ `app/pydeps.py`
"""
from . import demo_kip as _demo_kip
from . import pydeps as _pydeps

# Demo kipi (YUKI_DEMO=1) ev/veri dizinini değiştirir → pydeps YUKI_DATA_DIR'i okumadan ÖNCE.
_demo_kip.kur()

_pydeps.kur()
