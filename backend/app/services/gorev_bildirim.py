"""Atölye genel bildirimi — görev bitince ve öneri açılınca kullanıcıya haber.

Kanallar: kayıtlı cihazlara Web Push (`api/push.send_push_to_all`) + "Yuki dedi" geçmişi.
Ekrandaki duyuruyu ön yüz kendisi yapar (`gorev-serit.js`, `gorev` olayından).

Kurallar:
  · metin görev içeriğini (istek, ad) TAŞIMAZ — kilit ekranında okunur; yalnız tür + sonuç
  · kullanıcının kendi durdurduğu iş (`durdu/durdur`) bildirilmez
  · sessiz saat `YUKI_ATOLYE_SESSIZ` (varsayılan 23-08) içinde push gitmez
  · `YUKI_ATOLYE_BITIS_BILDIRIM=0` bitiş bildirimini kapatır
  · gönderim hatası görevi etkilemez (ayrı asyncio görevi, hata yutulur ve loglanır)
"""

from __future__ import annotations

import asyncio
import logging
import os
import re
import time
from datetime import datetime

logger = logging.getLogger(__name__)

BASLIK = "Yuki · Atölye"   # Türkçe hâli; gönderimde `baslik()` arayüz dilinden okur
# Bildirilen son durumlar. Metin katalogda (`mesajlar` atolye.bitis-<durum>, tr/en).
# `durdu/durdur` (kullanıcı durdurdu) bilerek yok.
_SONUC = ("bitti", "yarim", "hata", "durdu")
_TURLER = ("site", "arastirma", "sahne", "deneme")


def baslik() -> str:
    from app.mesajlar import M
    return M("atolye.bildirim-baslik")


def _zaman() -> float:
    return time.time()


def sessiz_aralik() -> tuple[int, int]:
    """`YUKI_ATOLYE_SESSIZ` = "SS-SS"; bozuk değer varsayılana (23-08) düşer."""
    m = re.fullmatch(r"(\d{1,2})-(\d{1,2})", (os.environ.get("YUKI_ATOLYE_SESSIZ") or "23-08").strip())
    if m and all(0 <= int(x) <= 23 for x in m.groups()):
        return int(m.group(1)), int(m.group(2))
    return 23, 8


def sessiz_mi(an: datetime, aralik: tuple[int, int]) -> bool:
    """[bas, bit) saat aralığı; gece yarısını aşabilir (23-08). bas == bit → hiç sessiz değil."""
    bas, bit = aralik
    if bas == bit:
        return False
    s = an.hour
    return bas <= s < bit if bas < bit else (s >= bas or s < bit)


async def push_gonder(baslik: str, govde: str, url: str) -> int:
    """Kayıtlı cihazlara Web Push + "Yuki dedi" kaydı. Gönderilen cihaz sayısını döner."""
    from app.api.push import send_push_to_all, yuki_dedi_kaydet
    n = await send_push_to_all(baslik, govde, url)
    await yuki_dedi_kaydet("atolye", govde, 0, n, 0)
    return n


def bitis_metni(kayit: dict) -> str | None:
    """Bildirilecekse metin, değilse None. İçerik (istek, ad) metne girmez."""
    durum, neden = kayit.get("durum"), kayit.get("neden")
    if durum not in _SONUC or (durum == "durdu" and neden == "durdur"):
        return None
    from app.mesajlar import M
    t = str(kayit.get("tur") or "")
    tur = M(f"atolye.tur-{t}") if t in _TURLER else M("atolye.tur-varsayilan")
    return M(f"atolye.bitis-{durum}", tur=tur)


class BitisBildirimi:
    """Görev servisinin bitiş kancası: `kanca(gid, kayit)`. `gonder` testte değiştirilir."""

    def __init__(self, gonder=None) -> None:
        self.gonder = gonder or push_gonder
        self.gorevler: set[asyncio.Task] = set()

    def __call__(self, gid: str, kayit: dict) -> None:
        if (os.environ.get("YUKI_ATOLYE_BITIS_BILDIRIM") or "1").strip() == "0":
            return
        metin = bitis_metni(kayit or {})
        if metin is None:
            return
        if sessiz_mi(datetime.fromtimestamp(_zaman()), sessiz_aralik()):
            logger.info("[bildirim] %s sessiz saatte — push yok", gid)
            return
        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            return
        g = loop.create_task(self._gonder(gid, metin))
        self.gorevler.add(g)                       # zayıf referansla toplanmasın
        g.add_done_callback(self.gorevler.discard)

    async def _gonder(self, gid: str, metin: str) -> None:
        try:
            await self.gonder(baslik(), metin, "/ui/index.html#atolye")
        except Exception as e:
            logger.warning("[bildirim] %s bitiş bildirimi gitmedi: %s", gid, type(e).__name__)
