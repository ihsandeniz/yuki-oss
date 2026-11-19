"""Görev nöbetçisi — Yuki Harness H2.

Koşan Atölye görevinin nabzını izler. Nabzı `ASILMA_ESIGI`'nden uzun duran görev
`durdu/asildi` olur. Bu, "LLM çağrısını bekleyen tur iptal jetonunu görmez" boşluğunu
dışarıdan kapatır: kimse DURDUR'a basmasa da asılan görev sonsuza dek `kosuyor` kalmaz,
iş sırası (H1) kilitlenmez. DEVAM her `durdu` gibi yalnız onayla (karar 3).

Nabız: `gorev._NabizliJeton`. Runner iptal jetonunu her akış parçasında, adım başında ve
araç çağrılarından sonra okur; H0 yeniden deneme beklemesi 0,25 sn'de bir okur. Her okuma
nabızdır. Yani uzun ama akan bir cevap ya da 15 dk'lık H0 beklemesi asılma SAYILMAZ; yalnız
hiç ilerlemeyen bir bekleme sayılır.

Zamanlama — tasarımdan bilerek sapma: APScheduler interval işi DEĞİL. Nöbet döngüsü bir
görev başlarken (`_kos_baslat`) doğar, koşan görev kalmayınca kendiliğinden biter. Boştayken
hiç uyanmaz (H2-b). `scheduler.py` ve `main.py` değişmez.

Eşik: görev başına `max(ASILMA_ESIGI, 3 × tavanlar.arac_zaman_asimi)`. Varsayılan
3 × 60 = 180 sn. Görevde araçlar paralel koşar ve `arac_zaman_asimi` ile kesilir, uzun
araçlar (`_LONG_TOOLS`) görevde kapalı; meşru bir sessizlik eşiği aşmaz. Asılan görev en
geç `son nabız + eşik + NOBET_ARALIK` anında durdurulur (H2-a).

Harness H3 — gece (HARNESS-TASARIM § 7): aynı tur, İŞ SIRASININ başlattığı koşuya gündüz
penceresi dışında bakar. Kalan tahmini (`gorev_kapilari.kalan_tahmini`) `GECE_PAYI`'nı
(15 dk) aşıyorsa ya da pencere biteli `GECE_PAYI` geçtiyse `durdu/gece`. Elle başlatılan
ya da sürdürülen koşuya dokunmaz. Döngü yine yalnız koşan görev varken yaşar (H2-b).
"""

from __future__ import annotations

import asyncio
import logging

from app.services import gorev as _gorev
from app.services import gorev_kapilari as _kapi

logger = logging.getLogger(__name__)

ASILMA_ESIGI = 180.0          # sn — 3 × arac_zaman_asimi (60), tasarım § 5
NOBET_ARALIK = 60.0           # sn — iki denetim arası


def _uyu(sn: float):
    """Bekleme ilkeli — testler sahte saatle değiştirir."""
    return asyncio.sleep(sn)


class Nobetci:
    def __init__(self, servis) -> None:
        self.servis = servis
        # H2-b ölçüsü: `tur` yalnız koşan görev varken artar.
        self.sayac = {"tur": 0, "denetlenen": 0, "asildi": 0, "gece": 0}
        self._dongu_gorevi: asyncio.Task | None = None

    def uyandir(self) -> None:
        """Görev başlarken çağrılır. Döngü zaten koşuyorsa bir şey yapmaz."""
        if self._dongu_gorevi is not None and not self._dongu_gorevi.done():
            return
        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            return
        self._dongu_gorevi = loop.create_task(self._dongu(), name="gorev-nobetci")

    async def _dongu(self) -> None:
        while self.servis._kosan_sayisi() > 0:
            await _uyu(NOBET_ARALIK)
            try:
                await self.tur()
            except Exception:
                # Nöbetçi düşerse görev durmaz; bir sonraki görev döngüyü yeniden doğurur.
                logger.exception("[nobetci] denetim turu hata verdi")

    def esik(self, gid: str) -> float:
        try:
            tav = self.servis._oku(gid).get("tavanlar") or {}
            arac = float(tav.get("arac_zaman_asimi") or 0)
        except Exception:
            arac = 0.0
        return max(ASILMA_ESIGI, 3 * arac)

    async def tur(self) -> list[str]:
        """Bir denetim. Koşan görev yoksa HİÇBİR ŞEY yapmaz (sayaç artmaz)."""
        kosan = [(gid, k) for gid, k in list(self.servis._kosan.items()) if not k.task.done()]
        if not kosan:
            return []
        self.sayac["tur"] += 1
        durdurulan: list[str] = []
        simdi = _gorev._nabiz_saat()
        for gid, k in kosan:
            self.sayac["denetlenen"] += 1
            sessiz = simdi - k.iptal.son_nabiz
            esik = self.esik(gid)
            if sessiz >= esik:
                await self.servis.asildi_durdur(gid, sessiz, esik)
                self.sayac["asildi"] += 1
                durdurulan.append(gid)
                continue
            kalan = self.gece_kalani(gid, k)
            if kalan is not None:
                await self.servis.gece_durdur(gid, kalan)
                self.sayac["gece"] += 1
                durdurulan.append(gid)
        return durdurulan

    def gece_kalani(self, gid: str, k) -> float | None:
        """Kuyruğun koşusu pencere dışında ve sığmıyorsa kalan tahmini (sn); yoksa None."""
        if getattr(k, "yol", None) != "kuyruk":
            return None
        from app.services.gorev_kuyrugu import _zaman
        simdi = _zaman()
        if _kapi.pencerede_mi(simdi):
            return None
        disari = _kapi.pencere_disi_sn(simdi)
        try:
            kalan = _kapi.kalan_tahmini(self.servis._oku(gid))
        except Exception:
            kalan = float("inf")                 # ölçülemiyor → sığmıyor say
        if kalan > _kapi.GECE_PAYI or disari >= _kapi.GECE_PAYI:
            return kalan
        return None


def nobetciyi_bagla(servis) -> Nobetci:
    """Servise nöbetçi tak (get_gorev_servisi çağırır). İkinci çağrı aynı nöbetçiyi döner."""
    if getattr(servis, "nobetci", None) is None:
        servis.nobetci = Nobetci(servis)
    return servis.nobetci
