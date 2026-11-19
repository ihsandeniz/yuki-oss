"""Görev servisi — Yuki Atölye v2, Faz 0b (Yol A: süreç içi asyncio + adım kaydı).

Uzun görev = aynı `LLMRunner` (görev modu, Faz 0a tavanları) + türün araç kapısı +
çalışma alanı `<atölye kökü>/<tür>/<ad>/`. Her adım sonunda `.gorev/durum.json` ve
`.gorev/mesajlar.json` yazılır; DEVAM son tamamlanan adımdan sürer.

Kurallar:
  · Restart sonrası diskte `kosuyor` görünen görev → `durdu` (neden `yeniden_baslatma`).
    Kendiliğinden devam YOK; DEVAM yalnız `onay=True` ile (karar 3).
  · Aynı anda en çok 1 görev (karar 4 başlangıcı).
  · DURDUR ≤2 sn: önce iptal jetonu, `DURDUR_BEKLEME` sonra asyncio görevi iptal.
  · Dış bağlamdan (telefon) başlatma yalnız TASLAK açar (Faz 0d): görev
    `bekliyor` durumunda, tek kullanımlık onay koduyla; masaüstüne bildirim gider,
    onaysız taslak `ONAY_SURESI` (5 dk) sonra `dustu`. Onay kipi `YUKI_ATOLYE_DIS_ONAY`:
    `dokunus` telefonda ikinci dokunuş, `masaustu` yalnız yerel onay. Dış bağlamdan
    tavan verilemez, DEVAM kapalı. DURDUR her bağlamdan açık.
  · Görevin KAYNAĞI (`yerel`/`dis`) kayıtta kalır ve görevin araç bağlamını belirler:
    dışarıdan açılan görev masaüstünden onaylansa/sürdürülse de dış kalır — genel
    araçlardan yalnız türün `dis_araclar`ı, `dis_yasak_mi` olanlar hiçbir zaman.
  · Araç kapısı: yalnız türün `araclar` (çalışma alanına kilitli) + `genel_araclar`
    (`call_tool` kapısından). Listede olmayan ad — şemada olmasa bile model yazabilir —
    reddedilir; global dispatcher'a hiç ulaşmaz.

Faz 0c: her kayıt yazımı `gorev` olayını yayınlar (WS → Halka Konsolu şeridi);
HTTP uçları `api/gorev.py`.

Harness H2: koşan görevin iptal jetonu nabız tutar (`_NabizliJeton`); `gorev_nobetci`
nabzı `ASILMA_ESIGI`'nden uzun duran görevi `durdu/asildi` yapar. Her adımda
`.gorev/nabiz` yazılır (sağlık sensörü okur).

Harness H3: koşu hangi yoldan başladı (`_Kosu.yol`: `kuyruk` | `yerel`) bellekte tutulur —
gece durdurması (`gece_durdur`, nöbetçi çağırır) yalnız kuyruğun işine uygulanır. Her
koşunun başındaki sayaçlar `kosu_baslangic`'e yazılır; iş sırası günlük bütçeye bu
koşunun farkını ekler (`gorev_kapilari`).
"""

from __future__ import annotations

import asyncio
import dataclasses
import hashlib
import hmac
import json
import logging
import os
import re
import secrets
import threading
import time
from pathlib import Path

from app.services import runner as _runner_mod
from app.services.atolye import alan
from app.services.atolye.turler import TURLER, GorevTuru, arac_dista_acik, dis_yasak_mi
from app.services.runner import CancellationToken, GorevTavanlari, LLMRunner

logger = logging.getLogger(__name__)

ESZAMANLI_TAVAN = 1
DURDUR_BEKLEME = 1.5          # sn — iptal jetonunun turu kendisi bitirmesi için
DEVAM_EDILEBILIR = frozenset({"durdu", "yarim"})
_AD_DESENI = re.compile(r"^[a-z0-9][a-z0-9-]{0,39}$")
_UZATILABILIR = ("adim", "sure_sn", "token")
ISTEK_AZAMI = 4000            # krk — telefondan gelen istek metni
# Faz 0d — dış bağlam taslağı
ONAY_SURESI = 5 * 60          # sn — onaysız taslak bu sürede düşer
ESZAMANLI_TASLAK = 1          # aynı anda en çok bir onay bekleyen taslak
ONAY_DENEME_TAVANI = 3        # yanlış kodla bu kadar deneme → taslak düşer
ONAY_KIPLERI = ("dokunus", "masaustu")
# Faz 1 — bitişte doğrulama (site türü)
DUZELTME_TAVANI = 2           # model "bitti" dedi ama site kirli → en çok bu kadar geri bildirim turu
# Ekran görüntüsünü modele gösteren görsel kontrol: görüntü kabulü her sağlayıcıda ölçülmediği
# için varsayılan KAPALI (YUKI_ATOLYE_GORSEL=1 ile açılır).
def _gorsel_acik() -> bool:
    return os.environ.get("YUKI_ATOLYE_GORSEL", "").strip().lower() in ("1", "true", "yes")


GORSEL_KONTROL = _gorsel_acik()
# Harness H0: GEÇİCİ sağlayıcı hatasında (zaman aşımı, bağlantı,
# 5xx/529, akış ortası kopma) görev bu aralıklarla en çok len() kez kendiliğinden yeniden
# denenir; sonra `durdu/saglayici_gecici` (DEVAM aynı adımdan). Kalıcı hata (4xx, kimlik,
# ValueError…) yeniden denenmez → `hata`. Kota (`durdu/kota`) bu kapsamda DEĞİL.
# Restart sonrası kendiliğinden devam YOK kuralı (karar 3) bundan etkilenmez.
YENIDEN_DENEME_SN = (60, 5 * 60, 15 * 60)
_BEKLEME_ADIMI = 0.25         # sn — bekleme sırasında DURDUR'u bu sıklıkla yoklar


def _uyu(sn: float):
    """Bekleme ilkeli — testler sahte saatle değiştirir (gerçek 15 dk bekleme yok)."""
    return asyncio.sleep(sn)


# Harness H2 — nabız saati (monoton). Testler sahte saatle değiştirir; nöbetçi aynı saati okur.
_nabiz_saat = time.monotonic


def _gecici_mi(istisna: BaseException | None) -> bool:
    """Sağlayıcı istisnası GEÇİCİ mi (yeniden denemeye değer)?

    Bilinmeyen tür kalıcı sayılır (fail-closed: boşuna tekrar etme)."""
    if istisna is None:
        return False
    if isinstance(istisna, (asyncio.TimeoutError, TimeoutError, ConnectionError)):
        return True
    try:
        import httpx
        if isinstance(istisna, httpx.HTTPStatusError):
            return istisna.response.status_code >= 500
        if isinstance(istisna, (httpx.TimeoutException, httpx.NetworkError,
                                httpx.RemoteProtocolError)):
            return True
    except ImportError:                    # pragma: no cover
        pass
    try:
        import openai
        if isinstance(istisna, (openai.APITimeoutError, openai.APIConnectionError)):
            return True
        if isinstance(istisna, openai.APIStatusError):
            return istisna.status_code >= 500
    except ImportError:                    # pragma: no cover
        pass
    return False


def _kota_mi(istisna: BaseException | None) -> bool:
    """Sağlayıcı kota/oran sınırı (HTTP 429) mı? Görev `durdu/kota` olur: yeniden denemeyle
    geçmez, kuyruk bu nedenle bekleme penceresi açar (`gorev_kapilari.KOTA_BEKLEME_DK`)."""
    if istisna is None:
        return False
    try:
        import openai
        if isinstance(istisna, openai.RateLimitError):
            return True
        if isinstance(istisna, openai.APIStatusError):
            return istisna.status_code == 429
    except ImportError:                    # pragma: no cover
        pass
    try:
        import httpx
        return (isinstance(istisna, httpx.HTTPStatusError)
                and istisna.response.status_code == 429)
    except ImportError:                    # pragma: no cover
        return False


async def _kesilebilir_bekle(sn: float, iptal) -> bool:
    """`sn` kadar bekler; DURDUR gelirse erken döner. True = süre doldu, False = iptal."""
    kalan = float(sn)
    while kalan > 0:
        if iptal.is_cancelled:
            return False
        adim = min(_BEKLEME_ADIMI, kalan)
        await _uyu(adim)
        kalan -= adim
    return not iptal.is_cancelled


class GorevHatasi(Exception):
    """İstek reddedildi (geçersiz ad, kapalı bağlam, onaysız devam, tavan…).

    `http`: uç katmanına önerilen durum kodu (403 kapı · 404 yok · 409 çakışma)."""

    def __init__(self, metin: str, http: int | None = None) -> None:
        super().__init__(metin)
        self.http = http


def onay_kipi() -> str:
    """`YUKI_ATOLYE_DIS_ONAY` (varsayılan `masaustu`) — tanınmayan değer `masaustu` (dar olan) sayılır."""
    k = (os.environ.get("YUKI_ATOLYE_DIS_ONAY") or "masaustu").strip().lower()
    return k if k in ONAY_KIPLERI else "masaustu"


def _kod_ozeti(kod: str) -> str:
    return hashlib.sha256(kod.encode("utf-8")).hexdigest()


def _masaustu_bildir(baslik: str, govde: str) -> None:
    """Masaüstü bildirimi — varsayılan KAPALI (`YUKI_ATOLYE_BILDIRIM=1` ile açılır).
    Ayrı iş parçacığında; hata görevi etkilemez."""
    if os.environ.get("YUKI_ATOLYE_BILDIRIM", "").strip().lower() not in ("1", "true", "yes"):
        return

    def _gonder():
        try:
            from app.services.tools.network import send_notification
            sonuc = send_notification(baslik, govde, "critical")
            if sonuc.startswith("Hata"):
                logger.warning("[gorev] masaüstü bildirimi gitmedi: %s", sonuc)
        except Exception:
            logger.exception("[gorev] masaüstü bildirimi gitmedi")
    threading.Thread(target=_gonder, name="gorev-bildirim", daemon=True).start()


# Tohum: istekte geçen atölye klasörü yeni alana kopyalanır (`Gorevler._tohum_kopyala`)
_TOHUM_RE = re.compile(r"(?<![\w.])(?:~|/)[^\s<>\"'`]+")
TOHUM_DOSYA = 60
TOHUM_BAYT = 8 * 1024 * 1024


def _varsayilan_kok() -> Path:
    """Atölye kökü: `YUKI_ATOLYE_KOK`, yoksa kullanıcı veri dizini altında `atolye/`."""
    ayar = os.environ.get("YUKI_ATOLYE_KOK")
    if ayar:
        return Path(ayar).expanduser()
    from app import config
    return Path(config.DATA_DIR) / "atolye"


def _simdi() -> str:
    return time.strftime("%Y-%m-%d %H:%M:%S")


def _atomik_yaz(yol: Path, veri) -> None:
    gecici = yol.with_name(yol.name + ".tmp")
    gecici.write_text(json.dumps(veri, ensure_ascii=False, indent=1), encoding="utf-8")
    os.replace(gecici, yol)


def ozet(d: dict) -> dict:
    """Arayüze/olaya giden kısa görünüm — istek metni, mesajlar, özet metni GİTMEZ."""
    tav = d.get("tavanlar") or {}
    o = {
        "id": d.get("id"), "tur": d.get("tur"), "ad": d.get("ad"),
        "durum": d.get("durum"), "neden": d.get("neden"),
        "adim": d.get("adim", 0), "adim_tavani": tav.get("adim"),
        "guncelleme": d.get("guncelleme"),
        # Faz 0d: onay ekranı tür · ad · tavanlar · çalışma alanı yolunu gösterir
        "kaynak": d.get("kaynak"), "onay_son": d.get("onay_son"), "alan": d.get("alan"),
        "tavanlar": {k: tav.get(k) for k in _UZATILABILIR},
        # Faz 1: bitiş doğrulamasının hükmü (hata metinleri GİTMEZ, sayısı gider)
        "dogrulama": _dogrulama_ozeti(d.get("dogrulama")),
        # Harness H2: son adımın duvar saati (nöbetçi/sağlık sensörü görünürlüğü)
        "son_nabiz": d.get("son_nabiz"),
    }
    if d.get("sahne"):
        # Araştırma Sahnesi sayaçları (aşama · kaynak · blok · maliyet) — içerik GİTMEZ.
        # Yalnız sahne görevinde: öbür türlerin kısa görünümü (test_gorev_api izin listesi) aynı.
        o["sahne"] = d["sahne"]
    return o


def _dogrulama_ozeti(liste) -> dict | None:
    if not liste:
        return None
    son = liste[-1]
    return {"temiz": son.get("temiz"), "hata": len(son.get("hatalar") or []),
            "gorsel": son.get("gorsel", {}).get("durum"), "tur": len(liste)}


def _yayinla(d: dict) -> None:
    """`gorev` olayı — senkron yazımdan çağrılır; döngü yoksa (açılış kurtarması) sessiz geçer."""
    try:
        loop = asyncio.get_running_loop()
    except RuntimeError:
        return
    from app.services.event_bus import bus
    loop.create_task(bus.publish("gorev", ozet(d)))


class _NabizliJeton(CancellationToken):
    """İptal jetonu + nabız (Harness H2). Runner jetonu her akış parçasında, her adım
    başında ve araç çağrılarından sonra okur; H0 yeniden deneme beklemesi 0,25 sn'de bir.
    Her okuma = koşu döngüsü canlı. LLM çağrısında asılan tur jetonu OKUMAZ → nabız durur
    → `gorev_nobetci` görür. Runner'a dokunmadan canlılık ölçmenin yolu budur."""

    def __init__(self) -> None:
        super().__init__()
        self.son_nabiz = _nabiz_saat()
        self.neden: str | None = None          # nöbetçi durdurursa "asildi"

    @property
    def is_cancelled(self) -> bool:
        self.son_nabiz = _nabiz_saat()
        return super().is_cancelled

    def nabiz(self) -> None:
        self.son_nabiz = _nabiz_saat()


@dataclasses.dataclass
class _Kosu:
    task: asyncio.Task
    iptal: CancellationToken
    yol: str = "yerel"             # H3: "kuyruk" = iş sırası başlattı (gece kapısı uygulanır)


@dataclasses.dataclass
class _Taslak:
    """Onay bekleyen dış taslak — kod YALNIZ özet olarak ve YALNIZ bellekte (restart → düşer)."""
    kod_ozeti: str
    son: float
    yanlis: int = 0
    zamanlayici: asyncio.TimerHandle | None = None


class GorevServisi:
    def __init__(self, kok: Path | str | None = None,
                 turler: dict[str, GorevTuru] | None = None, bildir=None) -> None:
        self.kok = Path(kok).expanduser() if kok else _varsayilan_kok()
        self.turler = turler if turler is not None else TURLER
        self.bildir = bildir if bildir is not None else _masaustu_bildir
        self._kosan: dict[str, _Kosu] = {}
        self._taslaklar: dict[str, _Taslak] = {}
        self._bitis_kancalari: list = []
        self.nobetci = None            # Harness H2 — `gorev_nobetci.nobetciyi_bagla`
        self._kurtar()

    # ── kayıt ─────────────────────────────────────────────────────────
    def _gid(self, gid: str) -> tuple[str, str]:
        tur, _, ad = (gid or "").partition("/")
        if tur not in self.turler or not _AD_DESENI.match(ad):
            raise GorevHatasi(f"geçersiz görev kimliği: {gid!r}")
        return tur, ad

    def _alan(self, gid: str) -> Path:
        tur, ad = self._gid(gid)
        return self.kok / tur / ad

    def _kayit(self, gid: str) -> Path:
        return self._alan(gid) / alan.AYRILMIS

    def _oku(self, gid: str) -> dict:
        try:
            return json.loads((self._kayit(gid) / "durum.json").read_text(encoding="utf-8"))
        except FileNotFoundError:
            raise GorevHatasi(f"görev yok: {gid}") from None

    def _yaz(self, d: dict) -> None:
        d["guncelleme"] = _simdi()
        _atomik_yaz(self._kayit(d["id"]) / "durum.json", d)
        _yayinla(d)

    def _mesajlar(self, gid: str) -> list[dict]:
        return json.loads((self._kayit(gid) / "mesajlar.json").read_text(encoding="utf-8"))

    def _mesajlar_yaz(self, gid: str, mesajlar: list[dict]) -> None:
        _atomik_yaz(self._kayit(gid) / "mesajlar.json", mesajlar)

    def _nabiz_yaz(self, d: dict) -> None:
        """`.gorev/nabiz` — son ilerleme anı + adım (sağlık sensörü okur). Yalnız sayı/zaman."""
        d["son_nabiz"] = _simdi()
        _atomik_yaz(self._kayit(d["id"]) / "nabiz",
                    {"zaman": d["son_nabiz"], "ts": round(time.time(), 3), "adim": d.get("adim", 0)})

    def _iz(self, gid: str, olay: str, **ek) -> None:
        """İz: başlatma/onay/durdurma tek satır — içerik değil."""
        satir = {"zaman": _simdi(), "olay": olay, **ek}
        with open(self._kayit(gid) / "olaylar.jsonl", "a", encoding="utf-8") as f:
            f.write(json.dumps(satir, ensure_ascii=False) + "\n")

    def _kurtar(self) -> None:
        """Restart kurtarma (karar 3). Bu süreç yeni doğdu → diskte `kosuyor`
        görünen hiçbir görev gerçekte koşmuyor. `durdu` yap, BAŞLATMA."""
        if not self.kok.is_dir():
            return
        for dj in sorted(self.kok.glob(f"*/*/{alan.AYRILMIS}/durum.json")):
            try:
                d = json.loads(dj.read_text(encoding="utf-8"))
            except Exception:
                logger.warning("[gorev] okunamayan kayıt atlandı: %s", dj)
                continue
            if d.get("durum") == "kosuyor":
                d["durum"], d["neden"] = "durdu", "yeniden_baslatma"
                self._yaz(d)
                self._iz(d["id"], "yeniden_baslatma_durdu", adim=d.get("adim"))
                logger.info("[gorev] %s yeniden başlatmada durduruldu (adım %s) — onay bekliyor",
                            d["id"], d.get("adim"))
            elif d.get("durum") == "bekliyor":
                # Onay kodu yalnız eski sürecin belleğindeydi → taslak onaylanamaz, düşer.
                d["durum"], d["neden"] = "dustu", "yeniden_baslatma"
                self._yaz(d)
                self._iz(d["id"], "dustu", neden="yeniden_baslatma")

    # ── kapılar ───────────────────────────────────────────────────────
    @staticmethod
    def _dis_mi() -> bool:
        from app.services.atolye import baglam
        return baglam.dis_mi()

    def _dis_kapi(self, eylem: str) -> None:
        if self._dis_mi():
            raise GorevHatasi(f"dış bağlamdan görev {eylem} kapalı — masaüstünden yap", http=403)

    def _kosan_sayisi(self) -> int:
        return sum(1 for k in self._kosan.values() if not k.task.done())

    # ── taslak (Faz 0d) ───────────────────────────────────────────────
    def _dusur(self, gid: str, neden: str) -> dict:
        t = self._taslaklar.pop(gid, None)
        if t is not None and t.zamanlayici is not None:
            t.zamanlayici.cancel()
        d = self._oku(gid)
        if d.get("durum") == "bekliyor":
            d["durum"], d["neden"] = "dustu", neden
            self._yaz(d)
            self._iz(gid, "dustu", neden=neden)
        return d

    def _suresi_dolanlari_dusur(self) -> None:
        """Zamanlayıcının kaçırdığı (döngü kapanmış, saat ileri…) taslaklar için tembel denetim."""
        simdi = time.time()
        for gid, t in list(self._taslaklar.items()):
            if simdi >= t.son:
                self._dusur(gid, "onay_suresi")

    def _sure_doldu(self, gid: str) -> None:
        t = self._taslaklar.get(gid)
        if t is not None and time.time() >= t.son - 0.05:
            self._dusur(gid, "onay_suresi")

    # ── genel yüzey ───────────────────────────────────────────────────
    def liste(self) -> list[dict]:
        self._suresi_dolanlari_dusur()
        if not self.kok.is_dir():
            return []
        out = []
        for dj in sorted(self.kok.glob(f"*/*/{alan.AYRILMIS}/durum.json")):
            try:
                out.append(json.loads(dj.read_text(encoding="utf-8")))
            except Exception:
                continue
        return out

    def durum(self, gid: str) -> dict:
        self._suresi_dolanlari_dusur()
        return self._oku(gid)

    async def baslat(self, tur: str, ad: str, istek: str, tavan: dict | None = None,
                     taslak: bool = False) -> dict:
        """Yerel bağlam: görev hemen koşar (`kaynak: yerel`, `tavan` türün değerlerini ezer).

        Dış bağlam: YALNIZ `taslak=True` ile (uç katmanı Origin kapısından sonra verir) —
        görev `bekliyor` açılır, dönen sözlükte bir kez `onay_kodu` vardır (diske yazılmaz).
        `taslak` vermeyen dış çağıran (ör. `yerel_baglam` unutulmuş ayrı süreç) reddedilir."""
        dis = self._dis_mi()
        if dis and not taslak:
            raise GorevHatasi("dış bağlamdan doğrudan görev başlatma kapalı — onaylı taslak "
                              "yolu: POST /api/gorev/baslat", http=403)
        if dis and tavan:
            raise GorevHatasi("dış bağlamdan tavan verilemez — tür tavanları geçerli, "
                              "uzatma masaüstünden", http=403)
        if tur not in self.turler:
            raise GorevHatasi(f"bilinmeyen tür: {tur!r}")
        if not isinstance(ad, str) or not _AD_DESENI.match(ad):
            raise GorevHatasi("ad yalnız küçük harf, rakam ve '-' (en çok 40)")
        if not isinstance(istek, str) or not istek.strip():
            raise GorevHatasi("istek boş")
        if len(istek) > ISTEK_AZAMI:
            raise GorevHatasi(f"istek en çok {ISTEK_AZAMI} karakter")
        for k, v in (tavan or {}).items():
            if k not in _UZATILABILIR or isinstance(v, bool) or not isinstance(v, (int, float)) or v <= 0:
                raise GorevHatasi(f"geçersiz tavan: {k}={v!r}")
        if dis:
            self._suresi_dolanlari_dusur()
            if len(self._taslaklar) >= ESZAMANLI_TASLAK:
                raise GorevHatasi("onay bekleyen bir görev zaten var — onu onayla ya da iptal et",
                                  http=409)
        elif self._kosan_sayisi() >= ESZAMANLI_TAVAN:
            raise GorevHatasi(f"aynı anda en çok {ESZAMANLI_TAVAN} görev koşabilir")
        d = self._hazirla(tur, ad, istek, tavan, "dis" if dis else "yerel",
                          "bekliyor" if dis else "kosuyor")
        if dis:
            return self._taslak_ac(d)
        self._yaz(d)
        self._iz(d["id"], "baslat", kaynak="yerel")
        self._kos_baslat(d["id"])
        return d

    def kuyruktan_baslat(self, tur: str, ad: str, istek: str, kaynak: str) -> dict:
        """Harness H1: ONAYI iş sırasında (`gorev_kuyrugu`) zaten verilmiş kaydı koşturur.

        Çağıranın bağlamına BAKMAZ — kaynağı kuyruk kaydındaki onaydan alır (
        telefondan onaylanan iş `dis`, dar yetkiyle koşar). Tanınmayan kaynak `dis`
        (fail-closed). Tavan verilmez (türün değerleri). Eşzamanlılık tavanı burada da
        denetlenir: kuyruğun kendi kapısı kaçsa bile ikinci görev koşmaz. Senkron: arada
        `await` yok → aynı döngüde iki çağrı yarışamaz."""
        if tur not in self.turler:
            raise GorevHatasi(f"bilinmeyen tür: {tur!r}")
        if not isinstance(ad, str) or not _AD_DESENI.match(ad):
            raise GorevHatasi("ad yalnız küçük harf, rakam ve '-' (en çok 40)")
        if not isinstance(istek, str) or not istek.strip() or len(istek) > ISTEK_AZAMI:
            raise GorevHatasi("istek boş ya da çok uzun")
        if self._kosan_sayisi() >= ESZAMANLI_TAVAN:
            raise GorevHatasi(f"aynı anda en çok {ESZAMANLI_TAVAN} görev koşabilir", http=409)
        kaynak = "yerel" if kaynak == "yerel" else "dis"
        d = self._hazirla(tur, ad, istek, None, kaynak, "kosuyor")
        self._yaz(d)
        self._iz(d["id"], "baslat", kaynak=kaynak, yol="kuyruk")
        self._kos_baslat(d["id"], yol="kuyruk")
        return d

    def kuyruktan_surdur(self, gid: str) -> dict:
        """Harness H4: yarım iş ÖNERİSİ onaylandı → aynı görevi kaldığı adımdan sürdürür
        (karar 3: devam yalnız onayla — onay kuyrukta verildi). `devam`ın aynısı, şu farkla:
        çağıranın bağlamına bakmaz (onay kuyrukta yerel olmak zorunda), tavan uzatmaz,
        koşu `kuyruk` yolundan sayılır (H3 gece kapısı ona da bakar). Senkron."""
        self._gid(gid)
        if gid in self._kosan and not self._kosan[gid].task.done():
            raise GorevHatasi("görev zaten koşuyor", http=409)
        if self._kosan_sayisi() >= ESZAMANLI_TAVAN:
            raise GorevHatasi(f"aynı anda en çok {ESZAMANLI_TAVAN} görev koşabilir", http=409)
        d = self._oku(gid)
        if d["durum"] not in DEVAM_EDILEBILIR:
            raise GorevHatasi(f"'{d['durum']}' durumundaki görev sürdürülemez")
        d["durum"], d["neden"] = "kosuyor", None
        d["devam_sayisi"] = d.get("devam_sayisi", 0) + 1
        self._yaz(d)
        self._iz(gid, "devam_onay", kaynak="yerel", yol="kuyruk")
        self._kos_baslat(gid, yol="kuyruk")
        return d

    def bitis_kancasi_ekle(self, kanca) -> None:
        """Harness H1: `kanca(gid, kayit)` her koşu bittiğinde (asyncio görevi tamamlanınca)
        çağrılır — görev artık `_kosan`'da sayılmaz. Restart kurtarması (`_kurtar`) kanca
        ÇAĞIRMAZ: o görev bu süreçte koşmadı (karar 3)."""
        self._bitis_kancalari.append(kanca)

    def _tohum_kopyala(self, istek: str, hedef: Path) -> str | None:
        """İstekte geçen ilk atölye klasörünü (`<atölye kökü>/<tür>/<ad>/`) yeni alana kopyalar.

        "Şu siteyi geliştir" işinin aynı dosyalardan sürmesi için: görev var olan klasörde
        açılamaz (ad çakışması), o yüzden kaynak KOPYALANIR, asıl klasöre dokunulmaz.
        Kapılar: yalnız atölye kökü içi, `.`-li segment (.kuyruk/.gorev) yok, sembolik bağ yok,
        ≤ TOHUM_DOSYA dosya / ≤ TOHUM_BAYT bayt; aşan ya da bozuk kaynakta tohum yok."""
        kok = self.kok.resolve()
        ev = str(Path.home())
        for m in _TOHUM_RE.finditer(istek or ""):
            ham = m.group(0).rstrip("/.,;:)'\"")
            yol = Path(ev + ham[1:] if ham.startswith("~") else ham)
            try:
                if yol.is_symlink() or not yol.is_dir():
                    continue
                kaynak = yol.resolve()
                rel = kaynak.relative_to(kok)
            except (OSError, ValueError):
                continue
            if len(rel.parts) < 2 or any(p.startswith(".") for p in rel.parts):
                continue
            if kaynak == hedef.resolve():
                continue
            dosyalar, toplam = [], 0
            for f in sorted(kaynak.rglob("*")):
                fr = f.relative_to(kaynak)
                if any(p.startswith(".") for p in fr.parts) or f.is_symlink():
                    continue
                if f.is_file():
                    toplam += f.stat().st_size
                    dosyalar.append(fr)
            if not dosyalar or len(dosyalar) > TOHUM_DOSYA or toplam > TOHUM_BAYT:
                logger.warning("[gorev] tohum atlandı (%s): %d dosya, %d bayt", rel, len(dosyalar), toplam)
                continue
            for fr in dosyalar:
                (hedef / fr).parent.mkdir(parents=True, exist_ok=True)
                (hedef / fr).write_bytes((kaynak / fr).read_bytes())
            gorunum = str(kaynak) + "/"
            return "~" + gorunum[len(ev):] if gorunum.startswith(ev + "/") else gorunum
        return None

    def _hazirla(self, tur: str, ad: str, istek: str, tavan: dict | None, kaynak: str,
                 durum: str) -> dict:
        """Çalışma alanını + mesaj kaydını açar, kayıt sözlüğünü döner (`durum.json`'u YAZMAZ)."""
        gid = f"{tur}/{ad}"
        yol = self._alan(gid)
        if yol.exists() or yol.is_symlink():
            raise GorevHatasi(f"bu adla görev zaten var: {gid}")
        (self.kok / tur).mkdir(parents=True, exist_ok=True)
        if self.kok.is_symlink() or (self.kok / tur).is_symlink():
            raise GorevHatasi("atölye kökü sembolik bağ olamaz")
        yol.mkdir()
        self._kayit(gid).mkdir()
        tohum = self._tohum_kopyala(istek, yol) if kaynak != "dis" else None

        t = self.turler[tur]
        tavanlar = dataclasses.asdict(t.tavanlar)
        tavanlar.update(tavan or {})
        ev = str(Path.home())
        alan_gorunum = str(yol) + "/"
        if alan_gorunum.startswith(ev + "/"):
            alan_gorunum = "~" + alan_gorunum[len(ev):]
        d = {
            "id": gid, "tur": tur, "ad": ad, "istek": istek,
            "durum": durum, "neden": None,
            "kaynak": kaynak, "alan": alan_gorunum,
            "adim": 0, "token": 0, "sure_sn": 0.0, "son_araclar": [],
            "tavanlar": tavanlar,
            "devam_sayisi": 0, "ozet": "", "olusturma": _simdi(),
        }
        sistem = (f"{t.rehber}\n\nÇalışma alanın bu göreve ayrılmış bir klasör. Dosya "
                  "yollarını GÖRELİ ver (ör. index.html); alan dışına yazamazsın. İş "
                  "bitince araç çağırmadan kısa bir özet yaz.")
        if tohum:
            d["tohum"] = tohum
            sistem += (f"\n\nAlan boş başlamadı: istekte geçen {tohum} klasörünün kopyası "
                       "burada. Önce mevcut dosyaları oku, sıfırdan yazmak yerine onları geliştir.")
        self._mesajlar_yaz(gid, [{"role": "system", "content": sistem},
                                 {"role": "user", "content": istek}])
        return d

    def _taslak_ac(self, d: dict) -> dict:
        gid = d["id"]
        sure = float(ONAY_SURESI)
        kod = secrets.token_urlsafe(18)
        t = _Taslak(kod_ozeti=_kod_ozeti(kod), son=time.time() + sure)
        d["onay_son"] = round(t.son, 3)
        self._yaz(d)
        self._taslaklar[gid] = t
        try:
            t.zamanlayici = asyncio.get_running_loop().call_later(sure, self._sure_doldu, gid)
        except RuntimeError:
            pass                                   # döngü yok → tembel denetim düşürür
        self._iz(gid, "taslak", kaynak="dis", onay_kipi=onay_kipi())
        dk = max(1, round(sure / 60))
        istek = " ".join(d["istek"].split())
        self.bildir(
            "Yuki Atölye — telefondan görev isteği",
            f"{gid} onay bekliyor ({dk} dk; onaylanmazsa düşer).\n"
            f"İstek: {istek[:80]}{'…' if len(istek) > 80 else ''}\n"
            f"Sen değilsen dokunma. Onay: Atölye şeridinden onayla {gid}",
        )
        return {**d, "onay_kodu": kod}

    async def onayla(self, gid: str, kod: str | None = None) -> dict:
        """Taslağı koşturur. Yerel: kod gerekmez (masaüstü onayı).
        Dış: yalnız `dokunus` kipinde ve doğru tek kullanımlık kodla (a)."""
        dis = self._dis_mi()
        self._gid(gid)
        self._suresi_dolanlari_dusur()
        d = self._oku(gid)
        if d.get("durum") != "bekliyor":
            raise GorevHatasi(f"'{d.get('durum')}' durumundaki görev onaylanamaz", http=409)
        t = self._taslaklar.get(gid)
        if t is None:
            raise GorevHatasi("bu taslağın onay kaydı yok (süreç yeniden başlamış olabilir)",
                              http=409)
        if dis:
            if onay_kipi() != "dokunus":
                raise GorevHatasi("dış bağlamdan onay kapalı (masaüstü kipi) — "
                                  f"masaüstünden: Atölye şeridinden onayla {gid}", http=403)
            if not isinstance(kod, str) or not hmac.compare_digest(_kod_ozeti(kod), t.kod_ozeti):
                t.yanlis += 1
                self._iz(gid, "yanlis_kod", kaynak="dis", deneme=t.yanlis)
                if t.yanlis >= ONAY_DENEME_TAVANI:
                    self._dusur(gid, "yanlis_kod")
                raise GorevHatasi("onay kodu yanlış", http=403)
        if self._kosan_sayisi() >= ESZAMANLI_TAVAN:
            raise GorevHatasi(f"aynı anda en çok {ESZAMANLI_TAVAN} görev koşabilir")
        self._taslaklar.pop(gid, None)
        if t.zamanlayici is not None:
            t.zamanlayici.cancel()
        d["durum"], d["neden"], d["onay_son"] = "kosuyor", None, None
        self._yaz(d)
        self._iz(gid, "onay", kaynak="dis" if dis else "yerel")
        self._kos_baslat(gid)
        return d

    async def durdur(self, gid: str) -> dict:
        """Her bağlamdan açık. Koşmuyorsa kaydı olduğu gibi döner."""
        self._gid(gid)
        if gid in self._taslaklar:
            self._iz(gid, "iptal", kaynak="dis" if self._dis_mi() else "yerel")
            return self._dusur(gid, "iptal")
        k = self._kosan.get(gid)
        if k is None or k.task.done():
            return self._oku(gid)
        self._iz(gid, "durdur", kaynak="dis" if self._dis_mi() else "yerel")
        k.iptal.cancel()
        bitti, _ = await asyncio.wait({k.task}, timeout=DURDUR_BEKLEME)
        if not bitti:
            # LLM çağrısını bekleyen tur iptal jetonunu görmez → görevi iptal et.
            k.task.cancel()
            await asyncio.wait({k.task}, timeout=0.5)
        return self._oku(gid)

    async def asildi_durdur(self, gid: str, sessiz_sn: float, esik: float) -> dict:
        """Harness H2 — nöbetçi çağırır: nabzı eşikten uzun duran görev `durdu/asildi`.
        Asılan tur jetonu görmez → DURDUR_BEKLEME beklenmez, görev hemen iptal edilir.
        DEVAM her `durdu` gibi yalnız onayla (karar 3); sıra ilerlemez (ILERLETEN dışı)."""
        k = self._kosan.get(gid)
        if k is None or k.task.done():
            return self._oku(gid)
        self._iz(gid, "asildi", sessiz_sn=round(sessiz_sn, 1), esik_sn=round(esik, 1))
        logger.warning("[gorev] %s %.0f sn ilerlemedi (eşik %.0f) — asıldı, durduruluyor",
                       gid, sessiz_sn, esik)
        k.iptal.neden = "asildi"
        k.iptal.cancel()
        k.task.cancel()
        await asyncio.wait({k.task}, timeout=DURDUR_BEKLEME)
        return self._oku(gid)

    async def gece_durdur(self, gid: str, kalan_sn: float) -> dict:
        """Harness H3 — nöbetçi çağırır: gündüz penceresi bitti, kuyruğun işi sığmıyor →
        `durdu/gece`. DURDUR gibi: önce jeton (tur kendisi biter), sonra görev iptali.
        DEVAM yalnız onayla (karar 3); sıra ilerlemez (ILERLETEN dışı); açılış telafisi sorar."""
        k = self._kosan.get(gid)
        if k is None or k.task.done():
            return self._oku(gid)
        self._iz(gid, "gece_durdur", kalan_tahmini_sn=round(kalan_sn))
        logger.info("[gorev] %s gündüz penceresi bitti (kalan tahmini %.0f sn) — durduruluyor",
                    gid, kalan_sn)
        k.iptal.neden = "gece"
        k.iptal.cancel()
        bitti, _ = await asyncio.wait({k.task}, timeout=DURDUR_BEKLEME)
        if not bitti:
            k.task.cancel()
            await asyncio.wait({k.task}, timeout=0.5)
        return self._oku(gid)

    async def devam(self, gid: str, onay: bool = False, uzat: dict | None = None) -> dict:
        self._dis_kapi("devam")
        if onay is not True:
            raise GorevHatasi("DEVAM kullanıcı onayı ister (onay=True)")
        self._gid(gid)
        if gid in self._kosan and not self._kosan[gid].task.done():
            raise GorevHatasi("görev zaten koşuyor")
        if self._kosan_sayisi() >= ESZAMANLI_TAVAN:
            raise GorevHatasi(f"aynı anda en çok {ESZAMANLI_TAVAN} görev koşabilir")
        d = self._oku(gid)
        if d["durum"] not in DEVAM_EDILEBILIR:
            raise GorevHatasi(f"'{d['durum']}' durumundaki görev sürdürülemez")
        for k, v in (uzat or {}).items():
            if k not in _UZATILABILIR or not isinstance(v, (int, float)) or v <= 0:
                raise GorevHatasi(f"geçersiz uzatma: {k}={v!r}")
            d["tavanlar"][k] += v
        d["durum"], d["neden"] = "kosuyor", None
        d["devam_sayisi"] = d.get("devam_sayisi", 0) + 1
        self._yaz(d)
        self._iz(gid, "devam_onay", kaynak="yerel", uzat=uzat or {})
        self._kos_baslat(gid)
        return d

    async def bekle(self, gid: str, zaman_asimi: float | None = None) -> dict:
        k = self._kosan.get(gid)
        if k is not None:
            await asyncio.wait({k.task}, timeout=zaman_asimi)
        return self._oku(gid)

    # ── koşu ──────────────────────────────────────────────────────────
    def _kos_baslat(self, gid: str, yol: str = "yerel") -> None:
        iptal = _NabizliJeton()
        task = asyncio.create_task(self._kos(gid, iptal), name=f"gorev:{gid}")
        kosu = _Kosu(task, iptal, yol)
        self._kosan[gid] = kosu

        def _temizle(_t, gid=gid, kosu=kosu):
            if self._kosan.get(gid) is kosu:
                del self._kosan[gid]
            if not self._bitis_kancalari:
                return
            try:
                kayit = self._oku(gid)
            except Exception:
                logger.exception("[gorev] %s bitiş kaydı okunamadı — kanca çağrılmadı", gid)
                return
            for kanca in list(self._bitis_kancalari):
                try:
                    kanca(gid, kayit)
                except Exception:
                    logger.exception("[gorev] %s bitiş kancası hata verdi", gid)
        task.add_done_callback(_temizle)
        if self.nobetci is not None:
            self.nobetci.uyandir()

    async def _arac(self, t: GorevTuru, kok: Path, ad: str, args: dict, dis: bool = True) -> str:
        """Görevin TEK araç kapısı — izin listesi dışı ad dispatcher'a ulaşmaz.

        `dis`: görevin KAYNAĞI (çağıranın bağlamı değil). Dış görevde genel araç yalnız
        türün `dis_araclar`ındaysa ve `dis_yasak_mi` değilse `call_tool`'a gider."""
        if ad in t.araclar:
            if dis and not arac_dista_acik(t, ad):
                return f"Hata: '{ad}' dışarıdan (telefon) açılan görevde kapalı (tür: {t.ad})."
            return await asyncio.to_thread(alan.ARACLAR[ad], kok, **args)
        if ad in t.genel_araclar:
            if dis and (ad not in t.dis_araclar or dis_yasak_mi(ad)):
                return f"Hata: '{ad}' dışarıdan (telefon) açılan görevde kapalı (tür: {t.ad})."
            from app.services.tools import call_tool
            return await call_tool(ad, args)
        return f"Hata: '{ad}' bu görevde izinli değil (tür: {t.ad})."

    async def _kos(self, gid: str, iptal: CancellationToken) -> None:
        from app.services.atolye import baglam
        d = self._oku(gid)
        t = self.turler[d["tur"]]
        if t.motor == "sahne":
            await self._kos_sahne(gid, iptal, d)
            return
        # Bağlam görevin KAYNAĞINDAN: telefon taslağını masaüstü onaylasa da görev dış kalır.
        # Kaynağı yazılı olmayan (Faz 0d öncesi) kayıt dış sayılır — fail-closed.
        dis = d.get("kaynak") != "yerel"
        baglam.dis_yaz(dis)
        kok = self._alan(gid)
        runner: LLMRunner | None = None
        metin: list[str] = []
        onceki = (d["adim"], d["token"], d["sure_sn"])

        async def _arac(ad, args):
            return await self._arac(t, kok, ad, args, dis)

        async def _adim(step, mesajlar):
            # Araç sonuçları eklendi → tutarlı nokta. DEVAM buradan sürer.
            iptal.nabiz()
            d.update(
                adim=onceki[0] + step,
                token=onceki[1] + runner.sonuc.token,
                sure_sn=round(onceki[2] + _runner_mod._saat() - runner._t0, 3),
                son_araclar=list(runner.sonuc.son_araclar),
            )
            self._mesajlar_yaz(gid, mesajlar)
            self._nabiz_yaz(d)
            self._yaz(d)

        # H3: bu koşunun başındaki sayaçlar — günlük bütçe koşu farkını sayar
        d["kosu_baslangic"] = {"token": d["token"], "sure_sn": d["sure_sn"]}
        self._nabiz_yaz(d)
        durum, neden = "hata", "baslamadi"
        duzeltme = 0
        deneme = 0                    # H0: bu koşudaki otomatik yeniden deneme sayısı
        while True:
            istisna: BaseException | None = None
            runner = None
            try:
                from app.services.llm_router import get_router
                router = get_router()
                client, model = await router.get_client()
                while True:
                    onceki = (d["adim"], d["token"], d["sure_sn"])
                    tav = GorevTavanlari(**d["tavanlar"])
                    kalan = dataclasses.replace(
                        tav,
                        adim=max(0, tav.adim - onceki[0]),
                        sure_sn=tav.sure_sn - onceki[2],
                        token=tav.token - onceki[1],
                    )
                    metin = []
                    runner = LLMRunner(client, model, t.semalar(dis=dis), cancel_token=iptal,
                                       gorev=kalan, arac_cagir=_arac, adim_bildir=_adim)
                    async for parca in runner.run(self._mesajlar(gid)):
                        metin.append(parca)
                    s = runner.sonuc
                    durum, neden = ("durdu", "durdur") if s.durum == "iptal" else (s.durum, s.neden)
                    istisna = s.istisna         # H0: `durdu` yolunda runner istisnayı yuttu
                    if durum == "hata" and _kota_mi(istisna):
                        durum, neden = "durdu", "kota"
                    d["token"] = onceki[1] + s.token
                    d["sure_sn"] = round(onceki[2] + s.sure_sn, 3)
                    if durum == "bitti":
                        # Son adım araçsızdı → adım kancası çağrılmadı; sayıyı burada tamamla.
                        d["adim"] = onceki[0] + s.son_adim
                        ozet_metni = "".join(metin)
                        if ozet_metni:
                            m = self._mesajlar(gid)
                            m.append({"role": "assistant", "content": ozet_metni})
                            self._mesajlar_yaz(gid, m)
                    runner = None
                    if durum != "bitti" or not t.dogrulayici:
                        break
                    # ── Faz 1: bitiş doğrulaması (model "bitti" dedi; servis ölçer) ──
                    rapor = await self._dogrula(kok, client, router, model, d, t)
                    d.setdefault("dogrulama", []).append(rapor)
                    self._yaz(d)
                    self._iz(gid, "dogrulama", temiz=rapor["temiz"], hata=len(rapor["hatalar"]),
                             gorsel=rapor.get("gorsel", {}).get("durum"))
                    if rapor["temiz"]:
                        break
                    if duzeltme >= DUZELTME_TAVANI or iptal.is_cancelled:
                        durum, neden = "yarim", "dogrulama"
                        break
                    duzeltme += 1
                    m = self._mesajlar(gid)
                    m.append({"role": "user", "content": _geri_bildirim(rapor, duzeltme)})
                    self._mesajlar_yaz(gid, m)
            except asyncio.CancelledError:
                durum, neden = "durdu", "durdur"
            except Exception as e:
                istisna = e
                if _gecici_mi(e):
                    logger.warning("[gorev] %s geçici sağlayıcı hatası: %s: %s",
                                   gid, type(e).__name__, str(e)[:200])
                else:
                    logger.exception("[gorev] %s beklenmedik hata", gid)
                durum, neden = ("durdu", "kota") if _kota_mi(e) else ("hata", type(e).__name__)

            if runner is not None and runner.sonuc is not None:
                # Döngü ortasında kesildi (iptal/hata) → o turun sayaçları
                s = runner.sonuc
                d["token"] = onceki[1] + s.token
                d["sure_sn"] = round(onceki[2] + s.sure_sn, 3)
                if istisna is None:
                    istisna = s.istisna

            # ── H0: geçici sağlayıcı hatası → bekle, son kayıtlı adımdan yeniden dene ──
            gecici = durum in ("hata", "durdu") and neden != "durdur" and _gecici_mi(istisna)
            if not gecici or iptal.is_cancelled:
                break
            if deneme >= len(YENIDEN_DENEME_SN):
                durum, neden = "durdu", "saglayici_gecici"
                self._iz(gid, "yeniden_deneme_bitti", deneme=deneme, sebep=type(istisna).__name__)
                break
            bekle = YENIDEN_DENEME_SN[deneme]
            deneme += 1
            d["durum"], d["neden"] = "kosuyor", f"yeniden_deneme_{deneme}"
            d["yeniden_deneme"] = {"no": deneme, "bekle_sn": bekle, "sebep": type(istisna).__name__}
            self._yaz(d)
            self._iz(gid, "yeniden_deneme", deneme=deneme, bekle_sn=bekle,
                     sebep=type(istisna).__name__, adim=d["adim"])
            try:
                suresi_doldu = await _kesilebilir_bekle(bekle, iptal)
            except asyncio.CancelledError:
                suresi_doldu = False
            if not suresi_doldu:
                durum, neden = "durdu", "durdur"
                break

        d.pop("yeniden_deneme", None)
        if durum == "durdu" and neden == "durdur" and getattr(iptal, "neden", None):
            neden = iptal.neden            # H2/H3: nöbetçi durdurdu → `asildi` | `gece`
        d["durum"], d["neden"] = durum, neden
        d["ozet"] = "".join(metin)[-4000:]
        self._yaz(d)
        self._iz(gid, "son", durum=durum, neden=neden, adim=d["adim"])

    async def _kos_sahne(self, gid: str, iptal: CancellationToken, d: dict) -> None:
        """Araştırma Sahnesi koşusu — LLMRunner yerine `atolye/sahne.py` motoru.

        İlerleme her olayda kayda + `gorev` olayına yazılır (şerit ve sahne kartı okur):
        `d["sahne"] = {asama, kaynak, blok, motor, maliyet_usd, hazir}`. Süre tavanı
        `asyncio.wait_for` ile; DURDUR iptal jetonuyla (motor her akış olayında okur).
        Sonuç: ≥6 blok → `bitti`, 1-5 blok → `yarim/az_blok`, biçim/anahtar → `hata`."""
        from app.services.atolye import sahne
        kok = self._alan(gid)
        d["kosu_baslangic"] = {"token": d["token"], "sure_sn": d["sure_sn"]}
        t0, onceki_sure = time.monotonic(), d["sure_sn"]
        try:
            motor = sahne.motor_adi()
        except sahne.SahneHatasi as e:
            motor = None
            d["durum"], d["neden"], d["ozet"] = "hata", "anahtar_yok", str(e)
        d["sahne"] = {"asama": "hazirlik", "kaynak": 0, "blok": 0, "motor": motor,
                      "maliyet_usd": 0.0, "tavan_usd": sahne.tavan_usd(), "hazir": False}
        self._nabiz_yaz(d)
        self._yaz(d)
        if motor is None:
            self._iz(gid, "son", durum="hata", neden="anahtar_yok", adim=d["adim"])
            return

        def ilerle(asama: str, kaynak: int, blok: int) -> None:
            iptal.nabiz()
            d["sahne"].update(asama=asama, kaynak=kaynak, blok=blok)
            d["adim"] = d.get("adim", 0) + 1
            d["sure_sn"] = round(onceki_sure + time.monotonic() - t0, 3)
            self._nabiz_yaz(d)
            self._yaz(d)

        durum, neden = "hata", "baslamadi"
        try:
            kalan = max(1.0, float(d["tavanlar"].get("sure_sn") or 600) - onceki_sure)
            sonuc = await asyncio.wait_for(sahne.arastir(d["istek"], ilerle, iptal, motor=motor),
                                           timeout=kalan)
            sonuc.sahne["meta"]["gid"] = gid
            sahne.kaydet(kok, sonuc.sahne)
            u = sonuc.usage
            d["token"] = d["token"] + int(u.get("input_tokens", 0)) + int(u.get("output_tokens", 0))
            d["sahne"].update(maliyet_usd=sonuc.maliyet_usd, blok=len(sonuc.sahne["bloklar"]),
                              hazir=True, tavan_asildi=sonuc.tavan_asildi)
            if motor == "anthropic":
                sahne.harcama_yaz(self.kok, gid, sonuc.sahne["meta"]["model"], sonuc.maliyet_usd)
            n = len(sonuc.sahne["bloklar"])
            durum, neden = ("bitti", None) if n >= sahne.BLOK_ALT else ("yarim", "az_blok")
            d["ozet"] = sonuc.sahne["baslik"]
        except (sahne.Iptal, asyncio.CancelledError):
            durum, neden = "durdu", (getattr(iptal, "neden", None) or "durdur")
        except asyncio.TimeoutError:
            durum, neden = "durdu", "sure"
        except sahne.SahneHatasi as e:
            durum, neden, d["ozet"] = "hata", "bicim", str(e)[:400]
        except Exception as e:
            # 🔴 Anthropic hata metni anahtarı içermez, yine de yalnız tür adı kayda girer.
            logger.warning("[gorev] %s sahne motoru hata: %s", gid, type(e).__name__)
            durum, neden = "hata", type(e).__name__
        d["sure_sn"] = round(onceki_sure + time.monotonic() - t0, 3)
        d["sahne"]["asama"] = "bitti" if durum == "bitti" else durum
        d["durum"], d["neden"] = durum, neden
        self._yaz(d)
        self._iz(gid, "son", durum=durum, neden=neden, adim=d["adim"],
                 maliyet_usd=d["sahne"].get("maliyet_usd"))

    def sahne_oku(self, gid: str) -> dict:
        """Kayıtlı sahne (SAHNE.json) — yalnız `sahne` türü; yoksa GorevHatasi."""
        tur, _ = self._gid(gid)
        if self.turler[tur].motor != "sahne":
            raise GorevHatasi(f"sahne türü değil: {gid}")
        from app.services.atolye import sahne
        try:
            return json.loads((self._alan(gid) / sahne.SAHNE_DOSYA).read_text(encoding="utf-8"))
        except FileNotFoundError:
            raise GorevHatasi(f"görev yok: {gid} sahnesi hazır değil", http=404) from None

    def sahneler(self) -> list[dict]:
        """Kayıtlı sahnelerin kısa listesi (en yeni önce) — yeniden açmak için."""
        from app.services.atolye import sahne
        out = []
        for tur, t in self.turler.items():
            if t.motor != "sahne" or not (self.kok / tur).is_dir():
                continue
            for sj in (self.kok / tur).glob(f"*/{sahne.SAHNE_DOSYA}"):
                try:
                    s = json.loads(sj.read_text(encoding="utf-8"))
                except Exception:
                    continue
                m = s.get("meta") or {}
                out.append({"id": f"{tur}/{sj.parent.name}", "baslik": s.get("baslik"),
                            "blok": len(s.get("bloklar") or []), "tarih": m.get("tarih"),
                            "motor": m.get("motor"), "maliyet_usd": m.get("maliyet_usd", 0)})
        return sorted(out, key=lambda x: x.get("tarih") or "", reverse=True)

    async def _dogrula(self, kok: Path, client, router, model: str, d: dict,
                       t: GorevTuru | None = None) -> dict:
        """Bitiş doğrulaması: model `alan_bitir` ile aynı içeriği ölçtürdüyse o sonuç kullanılır
        (parmak izi eşit), yoksa yeniden ölçülür. Sayısal temizse ekran görüntüleri modele
        gider (görsel kontrol); ciddi kusur bulursa hüküm kirli olur. Görsel kontrolün
        token'ı görev tavanına sayılır, ücretli yola düşmez."""
        from app.services.atolye import dogrulayici, rapor_dogrulayici
        if t is not None and t.dogrulayici_adi() == "rapor":
            # Faz 2: deterministik kaynak denetimi — LLM/görsel kontrol YOK (karar F2 a).
            sonuc = rapor_dogrulayici.son_sonuc(kok)
            if sonuc is None:
                sonuc = await asyncio.to_thread(rapor_dogrulayici.dogrula, kok)
            return {k: sonuc[k] for k in ("temiz", "hatalar", "uyarilar", "olcum", "sure_sn")}
        sonuc = dogrulayici.son_sonuc(kok)
        if sonuc is None:
            sonuc = await asyncio.to_thread(dogrulayici.dogrula, kok)
        sonuc = {k: sonuc[k] for k in ("temiz", "hatalar", "uyarilar", "olcum", "sure_sn")}
        if sonuc["temiz"] and GORSEL_KONTROL:
            gorsel = await _gorsel_kontrol(kok, client, router, model)
            d["token"] = d.get("token", 0) + gorsel.get("token", 0)
            sonuc["gorsel"] = gorsel
            if gorsel["durum"] == "kusurlu":
                sonuc["temiz"] = False
                sonuc["hatalar"] = [f"görsel: {k}" for k in gorsel["ciddi"]]
        return sonuc


def _geri_bildirim(rapor: dict, tur_no: int) -> str:
    satirlar = [f"Bitiş doğrulaması KİRLİ (düzeltme turu {tur_no}/{DUZELTME_TAVANI}). "
                "Şunları düzelt, sonra alan_bitir çağır:"]
    satirlar += [f"- {h}" for h in rapor["hatalar"][:12]]
    return "\n".join(satirlar)


_GORSEL_ISTEM = (
    "Sen bir web sitesi görsel denetçisisin. İki ekran görüntüsü var: masaüstü (1440 px) "
    "ve telefon (390 px). YALNIZ ciddi kusurları say: üst üste binen ya da kesilen metin, "
    "okunmayacak kadar küçük ya da zeminle aynı renkte yazı, bozuk/boş görünen bölüm, "
    "taşma, kırık görsel, telefonda kullanılamayan düzen. Zevk meselesi ciddi DEĞİL. "
    'Yalnız JSON döndür: {"ciddi": ["…"], "kucuk": ["…"]} — her madde tek kısa cümle, '
    "en çok 4'er madde. Kusur yoksa boş liste.")


async def _gorsel_kontrol(kok: Path, client, router, model: str) -> dict:
    """Ekran görüntülerini (doğrulayıcının `.gorev/ekran/`) modele verir. Varsayılan
    kapalı (`GORSEL_KONTROL`). Hata hükmü bozmaz."""
    import base64
    ekran = kok / alan.AYRILMIS / "ekran"
    resimler = [ekran / "1440.png", ekran / "390.png"]
    if not all(r.is_file() for r in resimler):
        return {"durum": "atlandi", "neden": "ekran görüntüsü yok", "ciddi": [], "kucuk": [],
                "token": 0}
    icerik: list[dict] = [{"type": "text", "text": "1. görüntü 1440 px, 2. görüntü 390 px."}]
    for r in resimler:
        icerik.append({"type": "image_url", "image_url": {
            "url": "data:image/png;base64," + base64.b64encode(r.read_bytes()).decode()}})
    try:
        cevap = await client.chat.completions.create(
            model=model, messages=[{"role": "system", "content": _GORSEL_ISTEM},
                                   {"role": "user", "content": icerik}],
            stream=False)
        yazi = cevap.choices[0].message.content or ""
        usage = getattr(cevap, "usage", None)
        token = int(getattr(usage, "total_tokens", 0) or 0)
    except Exception as e:
        logger.warning("[gorev] görsel kontrol yapılamadı: %s", e)
        return {"durum": "yapilamadi", "neden": type(e).__name__, "ciddi": [], "kucuk": [],
                "token": 0}
    m = re.search(r"\{.*\}", yazi, re.S)
    try:
        veri = json.loads(m.group(0)) if m else {}
        ciddi = [str(x)[:200] for x in (veri.get("ciddi") or [])][:4]
        kucuk = [str(x)[:200] for x in (veri.get("kucuk") or [])][:4]
    except (ValueError, AttributeError):
        return {"durum": "yapilamadi", "neden": "JSON okunamadı", "ciddi": [], "kucuk": [],
                "token": token, "ham": yazi[:300]}
    return {"durum": "kusurlu" if ciddi else "temiz", "ciddi": ciddi, "kucuk": kucuk,
            "token": token}


_servis: GorevServisi | None = None


def get_gorev_servisi() -> GorevServisi:
    """Süreç başına tek servis. İlk erişimde restart kurtarması koşar."""
    global _servis
    if _servis is None:
        _servis = GorevServisi()
        # Harness H1: iş sırası servisle birlikte doğar → bitiş kancası her koşuda bağlı,
        # açılış kurtarması sırayı da `durdu` yapar (sıradakini BAŞLATMAZ, karar 3).
        try:
            from app.services.gorev_kuyrugu import kuyrugu_bagla
            kuyrugu_bagla(_servis)
        except Exception:
            # Sıra açılamazsa görev servisi yine çalışır; sıra uçları hata döner.
            logger.exception("[gorev] iş sırası bağlanamadı")
        # Harness H2: nöbetçi — koşan görev varken uyanır, yokken hiç çalışmaz.
        try:
            from app.services.gorev_nobetci import nobetciyi_bagla
            nobetciyi_bagla(_servis)
        except Exception:
            logger.exception("[gorev] nöbetçi bağlanamadı")
        # Genel bildirim: görev bitince kayıtlı cihazlara push (içerik taşımaz).
        try:
            from app.services.gorev_bildirim import BitisBildirimi
            _servis.bitis_kancasi_ekle(BitisBildirimi())
        except Exception:
            logger.exception("[gorev] bitiş bildirimi bağlanamadı")
    return _servis
