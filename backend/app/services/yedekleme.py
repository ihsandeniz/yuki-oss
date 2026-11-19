"""Drive yedekleme motoru — **dosya aynası** ( FAZ 4).

Karar (geliştirici, 2026-09-14): kapsam = *Yuki'nin kendi verisi + kullanıcının seçtiği
klasörler* · kademe = **Pro** · yöntem = **değişeni yükle** (tam arşiv değil).

🔑 **Neden ayna, neden zip değil:** tek zip her turda TAM yükleme demektir; 5 GB'lık
bir klasör her gece 5 GB upload eder ve kullanıcının hem alanını hem hattını yakar.
Ayna, dosya başına parmak izi tutar ve yalnız değişeni gönderir. Bedeli: durum
dosyası, silinme politikası ve kimlik takibi — hepsi burada.

🔴 **rclone/systemctl KULLANILMAZ.** Kullanıcı tabanı Windows; `systemctl --user`
orada yok, rclone da kurulu değil. Zamanlama ürünün kendi APScheduler'ından
(`services/scheduler.py`) gelir, dosya işleri saf `pathlib` + `httpx` ile yapılır —
tek bir `subprocess` yok, yani platform farkı yok.

## Üç politika kararı (hepsi bilinçli)

**① Kaynakta silinen dosya Drive'da SİLİNMEZ.** Ayna deyince akla iki yönlü
eşitleme gelir; bir *yedekleme* aracında bu veri kaybıdır: yanlışlıkla sildiğin
dosya bir sonraki turda yedeğinden de silinir ve kurtarma diye bir şey kalmaz.
Bunun yerine indeks dosyayı `kaynakta_yok` diye işaretler, rapor sayısını söyler.

**② Sır dosyaları yedeğe girmez** (`.env`, Google token'ları, VAPID anahtarları).
Yedek kullanıcının kendi Drive'ına gitse de, hesap erişimi sağlayan bir sırrı
kullanıcıya sormadan bulut hesabına kopyalamak sessiz bir karardır. Anahtarlar
zaten yeniden girilebilir; sohbet geçmişi girilemez.

**③ `.db` dosyaları sqlite'ın kendi yedek API'siyle kopyalanır.** Çalışan bir
WAL veritabanını düz kopyalamak **yırtık** bir dosya üretir: yükleme başarılı
görünür, geri yükleyince veritabanı bozuktur. Bir yedekleme aracının yapabileceği
en kötü hata, başarılı sandığın bozuk yedektir.
"""

from __future__ import annotations

import asyncio
import fnmatch
import hashlib
import json
import logging
import os
import shutil
import sqlite3
import tempfile
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterator

from app.mesajlar import M
from app.services import google_client as _g

logger = logging.getLogger(__name__)

_DATA_ROOT = Path(os.getenv("YUKI_DATA_DIR") or Path(__file__).resolve().parents[2])
_AYAR_YOLU = _DATA_ROOT / "data" / "yedekleme.json"
_INDEKS_DIZINI = _DATA_ROOT / "data" / "yedek-indeks"

#: Drive'da açılan kök klasörün adı. Kullanıcı Drive'da bunu görür.
KOK_KLASOR = "Yuki Yedek"

#: Yuki'nin kendi verisi — **beyaz liste**. Kara liste yazılamaz: `YUKI_DATA_DIR`
#: Electron'un userData'sıdır ve içinde Chromium'un `Cache`, `GPUCache`,
#: `Service Worker` dizinleri, ayrıca `models-cache` (yüz/ses modelleri, GB'larca)
#: durur. Kara liste yazsaydık her yeni Electron sürümü yeni bir çöp dizini ekler
#: ve biz onu kullanıcının Drive'ına yüklerdik.
YUKI_VERI_DESENLERI = [
    "chat_history.json",     # sohbet geçmişi — geri getirilemez olan asıl şey
    "memory.db",             # gömülü hafıza (sqlite; ② ve ③ politikaları geçerli)
    "user_profile.json",
    "faces.json",            # yüzle giriş kayıtları
    "app_lock.json",
    "modes.json",
    "data/**",               # rutinler, todo deposu, bildirim/monitör db'leri
    "duvar/**",              # kullanıcının yüklediği duvar kâğıtları
    "media_uploads/**",      # kullanıcının yüklediği medya
]

#: Hiçbir kaynakta yedeklenmeyen desenler. Sır + çöp + kendi ürettiğimiz artık.
VARSAYILAN_ISTISNALAR = [
    ".env", ".env.*",
    "planner_tokens.json", "planner_state_tokens.json",   # hesap erişimi (politika ②)
    "vapid_private.pem", "vapid_public.pem",
    "*.log", "*.log.*", "hata-gunlugu.jsonl", "acilis.log",
    "*.db-wal", "*.db-shm",          # sqlite yardımcıları — anlık görüntüde zaten var
    "*.tmp", "*.temp", "~$*", ".DS_Store", "Thumbs.db", "desktop.ini",
    "__pycache__", "node_modules", ".git", "venv", ".venv",
    "models-cache", "updates",       # indirilebilir / yeniden üretilebilir
]

_VARSAYILAN_AYAR: dict[str, Any] = {
    "acik": False,                  # özellik kurulumda KAPALI gelir (kullanıcı açar)
    "yuki_verisi": True,            # Yuki'nin kendi verisi (karar: varsayılan açık)
    "kaynaklar": [],                # kullanıcının eklediği klasörler
    "zamanlama": None,              # "HH:MM" ya da None (yalnız elle)
    "istisnalar": [],               # kullanıcının EKLEDİĞİ desenler (varsayılanlara eklenir)
    "tek_dosya_tavani_mb": 200,
    "tur_bayt_tavani_mb": 2048,
    "kok_klasor_id": None,
    "son_tur": None,
}

#: Aynı anda iki tur koşamaz: zamanlayıcı 03:30'da başlatırken kullanıcı "şimdi
#: yedekle" derse iki tur aynı indekse yazar ve indeks yarış koşuluyla bozulur.
_KILIT = asyncio.Lock()
_CALISIYOR = False

#: Sürmekte olan turun CANLI raporu (aynı sözlük `tur_calistir`in doldurduğu). Panel
#: "sürüyor" derken kaç dosya gittiğini ve hangi klasörün sırada olduğunu buradan okur.
_CANLI: dict[str, Any] | None = None

#: İndeks yarıda kalan tura dayanıklı olsun diye bu kadar yüklemede (ya da bu kadar
#: saniyede) bir diske yazılır. Yalnız kaynak SONUNDA yazılırken: ağ kesilince / Drive
#: dolunca / uygulama kapanınca yüklenen dosyaların kaydı kaybolur ve sonraki tur HEPSİNİ
#: yeni dosya sanıp Drive'a ikinci kez yüklerdi (kopya + boşa giden alan).
_INDEKS_ARALIK = 20
_INDEKS_SANIYE = 5.0
_META = "#meta"        # indeks içinde dosya olmayan kayıtlar `#` ile başlar (`#dizin:…`, `#meta`)


# ── Ayarlar ──────────────────────────────────────────────────────────────────

def ayarlar() -> dict[str, Any]:
    veri = dict(_VARSAYILAN_AYAR)
    try:
        okunan = json.loads(_AYAR_YOLU.read_text(encoding="utf-8"))
        if isinstance(okunan, dict):
            veri.update(okunan)
    except FileNotFoundError:
        pass
    except Exception as e:  # noqa: BLE001
        # Bozuk ayar dosyası özelliği öldürmez; varsayılana düşer ve söyler.
        logger.warning("yedekleme.json okunamadı (%s) — varsayılanlar kullanıldı", e)
    return veri


def ayar_yaz(veri: dict[str, Any]) -> None:
    _AYAR_YOLU.parent.mkdir(parents=True, exist_ok=True)
    gecici = _AYAR_YOLU.with_suffix(".json.tmp")
    gecici.write_text(json.dumps(veri, ensure_ascii=False, indent=2), encoding="utf-8")
    os.replace(gecici, _AYAR_YOLU)


def _istisnalar(ayar: dict) -> list[str]:
    return VARSAYILAN_ISTISNALAR + list(ayar.get("istisnalar") or [])


# ── Kaynaklar ────────────────────────────────────────────────────────────────

class YedeklemeHatasi(Exception):
    """Kullanıcıya gösterilebilir hata (metin doğrudan arayüze gider)."""


def kaynak_ekle(yol: str) -> dict:
    """Klasör ekle. İç içe klasörleri REDDEDER.

    ⚠️ İç içelik denetimi gerçek bir kusuru önler: `/ev/belgeler` ve
    `/ev/belgeler/fatura` birlikte eklenirse aynı dosyalar **iki kez** yüklenir,
    iki ayrı indekste izlenir ve kullanıcının alanı sebepsiz iki katına çıkar.
    """
    p = Path(yol).expanduser()
    try:
        p = p.resolve(strict=True)
    except Exception:
        raise YedeklemeHatasi(M("yedek.klasor-yok", yol=yol))
    if not p.is_dir():
        raise YedeklemeHatasi(M("yedek.yalniz-klasor"))
    if p == Path(p.anchor):
        raise YedeklemeHatasi(M("yedek.disk-koku"))

    ayar = ayarlar()
    for k in ayar["kaynaklar"]:
        var = Path(k["yol"])
        if var == p:
            raise YedeklemeHatasi(M("yedek.zaten-ekli"))
        if var in p.parents:
            raise YedeklemeHatasi(M("yedek.ust-klasor-ekli", var=var))
        if p in var.parents:
            raise YedeklemeHatasi(M("yedek.alt-klasor-ekli", var=var))

    kaynak = {"id": uuid.uuid4().hex[:12], "yol": str(p), "ad": p.name or str(p),
              "acik": True, "drive_klasor_id": None}
    ayar["kaynaklar"].append(kaynak)
    ayar_yaz(ayar)
    return kaynak


def kaynak_sil(kaynak_id: str) -> bool:
    ayar = ayarlar()
    kalan = [k for k in ayar["kaynaklar"] if k["id"] != kaynak_id]
    if len(kalan) == len(ayar["kaynaklar"]):
        return False
    ayar["kaynaklar"] = kalan
    ayar_yaz(ayar)
    # İndeks de gitsin: klasör yeniden eklenirse baştan taranmalı, yoksa eski
    # indeks "bunlar zaten yüklü" der ve hiçbir dosya gitmez.
    (_INDEKS_DIZINI / f"{kaynak_id}.json").unlink(missing_ok=True)
    return True


def _yuki_kaynagi() -> dict:
    """Yuki'nin kendi verisi — sentetik kaynak (kullanıcı yolunu seçmez)."""
    return {"id": "yuki", "yol": str(_DATA_ROOT), "ad": "Yuki verisi",
            "acik": True, "desenler": YUKI_VERI_DESENLERI}


def etkin_kaynaklar(ayar: dict | None = None) -> list[dict]:
    ayar = ayar or ayarlar()
    kaynaklar = [k for k in ayar["kaynaklar"] if k.get("acik", True)]
    if ayar.get("yuki_verisi", True):
        kaynaklar.insert(0, _yuki_kaynagi())
    return kaynaklar


# ── İndeks ───────────────────────────────────────────────────────────────────

def indeks_oku(kaynak_id: str) -> dict[str, dict]:
    try:
        veri = json.loads((_INDEKS_DIZINI / f"{kaynak_id}.json").read_text(encoding="utf-8"))
        return veri if isinstance(veri, dict) else {}
    except FileNotFoundError:
        return {}
    except Exception as e:  # noqa: BLE001
        # Bozuk indeks = "hiç yüklenmemiş" kabul edilir. Sonucu fazladan yükleme
        # (pahalı ama güvenli); tersi sessizce eksik yedek olurdu.
        logger.warning("yedek indeksi okunamadı (%s) — sıfırdan sayılıyor", e)
        return {}


def indeks_yaz(kaynak_id: str, indeks: dict[str, dict]) -> None:
    _INDEKS_DIZINI.mkdir(parents=True, exist_ok=True)
    yol = _INDEKS_DIZINI / f"{kaynak_id}.json"
    gecici = yol.with_suffix(".json.tmp")
    gecici.write_text(json.dumps(indeks, ensure_ascii=False), encoding="utf-8")
    os.replace(gecici, yol)


# ── Tarama ───────────────────────────────────────────────────────────────────

def _eslesir(ad: str, desenler: list[str]) -> bool:
    return any(fnmatch.fnmatch(ad, d) for d in desenler)


def _desen_kapsar(gorece: str, desenler: list[str]) -> bool:
    """Yuki verisi beyaz listesi: 'data/**' dizini, 'memory.db' tek dosyayı tutar."""
    for d in desenler:
        if d.endswith("/**"):
            if gorece == d[:-3] or gorece.startswith(d[:-2]):
                return True
        elif fnmatch.fnmatch(gorece, d):
            return True
    return False


def tara(kaynak: dict, istisnalar: list[str]) -> Iterator[tuple[Path, str, int, float]]:
    """(mutlak yol, göreli yol, boyut, mtime) — deterministik sırada."""
    kok = Path(kaynak["yol"])
    if not kok.is_dir():
        return
    beyaz = kaynak.get("desenler")
    for dizin, altlar, dosyalar in os.walk(kok):
        altlar[:] = sorted(a for a in altlar if not _eslesir(a, istisnalar))
        d = Path(dizin)
        for ad in sorted(dosyalar):
            if _eslesir(ad, istisnalar):
                continue
            tam = d / ad
            gorece = tam.relative_to(kok).as_posix()
            if beyaz is not None and not _desen_kapsar(gorece, beyaz):
                continue
            if _kendi_durumu(tam):
                continue
            try:
                st = tam.stat()
            except OSError:
                continue           # yarışta silinmiş / izin yok → atla, tur durmaz
            yield tam, gorece, st.st_size, st.st_mtime


def _kendi_durumu(tam: Path) -> bool:
    """Yedeklemenin KENDİ durum dosyaları mı?

    🔴 **FAZ 4C'de gerçek Drive'a karşı ölçüldü (2026-09-14):** `data/**` beyaz
    listesi `data/yedekleme.json` ile `data/yedek-indeks/*.json`'u da kapsıyordu
    ve ikisi de **her turun sonunda yazılır** (`son_tur` raporu + dosya indeksi).
    Sonuç: hiçbir şey değişmediği turda bile 3 dosya yeniden yükleniyordu —
    *"ikinci tur değişmeyeni atlar"* vaadi sessizce bozuktu ve kullanıcının Drive'ına
    her gece boşuna yazılıyordu. Sahte Drive'lı birim test bunu göremezdi: kusur
    dosya sayısında değil **turlar arası durumda** yaşıyor.

    ⚠️ Desen listesine (`VARSAYILAN_ISTISNALAR`) yazılmadı bilerek: orası **ad**
    eşler, yani kullanıcının kendi klasöründeki `yedekleme.json` adlı masum bir
    dosyayı da yedekten düşürürdü. Burada **mutlak yol** karşılaştırılır.
    """
    try:
        return tam == _AYAR_YOLU or _INDEKS_DIZINI in tam.parents
    except Exception:  # noqa: BLE001
        return False


def _wal_imzasi(tam: Path) -> list | None:
    """`.db` için `-wal` dosyasının (boyut, mtime) imzası; yoksa None.

    🔴 WAL kipinde yeni satırlar ana dosyaya değil `-wal`e yazılır; ana `.db`nin boyutu
    ve mtime'ı checkpoint'e kadar DEĞİŞMEZ. Hızlı eleme yalnız ana dosyaya baksaydı
    çalışan Yuki'nin hafızası günlerce "değişmedi" sayılır, yeni satırlar yedeğe girmezdi.
    """
    if tam.suffix != ".db":
        return None
    try:
        st = Path(f"{tam}-wal").stat()
    except OSError:
        return None
    return [st.st_size, st.st_mtime]


def _md5(yol: Path) -> str:
    h = hashlib.md5()
    with open(yol, "rb") as f:
        for blok in iter(lambda: f.read(1024 * 1024), b""):
            h.update(blok)
    return h.hexdigest()


def _sqlite_anlik(kaynak: Path) -> Path:
    """Çalışan sqlite veritabanının tutarlı anlık görüntüsü (politika ③)."""
    hedef = Path(tempfile.mkdtemp(prefix="yuki-yedek-")) / kaynak.name
    src = sqlite3.connect(f"file:{kaynak}?mode=ro", uri=True)
    try:
        dst = sqlite3.connect(str(hedef))
        try:
            src.backup(dst)
        finally:
            dst.close()
    finally:
        src.close()
    return hedef


# ── Tur ──────────────────────────────────────────────────────────────────────

def calisiyor_mu() -> bool:
    return _CALISIYOR


async def tur_calistir(tetik: str = "elle") -> dict:
    """Bir yedekleme turu. Rapor döndürür; istisna atmaz — rapor `hata` taşır.

    Rapor alanları (panelin tek kaynağı):
    · `hata` kullanıcı cümlesi, `hata_tur` makine etiketi (`bagli-degil` · `kopuk` · `dolu` ·
      `api-kapali` · `ag` · `drive` · `diger`), `teknik` Google'ın ham gövdesi (yalnız ayrıntı)
    · `tam` — tur HER dosyayı gözden geçirdi mi. `tavan_doldu` / hata / klasör yoksa False:
      "başarılı" bitmek "hepsi yedekte" demek değildir.
    · `kaynaklar[]` — kaynak başına `durum` (`tamam` · `yarim` · `yol-yok` · `yarida` ·
      `sira-gelmedi`) + sayaçlar.
    """
    global _CALISIYOR, _CANLI
    if _KILIT.locked():
        raise YedeklemeHatasi(M("yedek.tur-suruyor"))

    async with _KILIT:
        _CALISIYOR = True
        basladi = datetime.now(timezone.utc)
        ayar = ayarlar()
        rapor: dict[str, Any] = {
            "tetik": tetik,
            "basladi": basladi.isoformat(),
            "yuklenen": 0, "guncellenen": 0, "atlanan": 0, "bayt": 0,
            "kaynakta_yok": 0, "buyuk_atlandi": [], "hata": None,
            "kaynaklar": [],
        }
        _CANLI = rapor
        try:
            await _tur_govde(ayar, rapor)
        except _g.GoogleBagliDegil:
            rapor["hata"], rapor["hata_tur"] = M("yedek.google-bagla"), "bagli-degil"
        except _g.GoogleYetkiDustu as e:
            rapor["hata"], rapor["hata_tur"] = str(e), "kopuk"
        except YedeklemeHatasi as e:
            rapor["hata"], rapor["hata_tur"] = str(e), "diger"
        except _g.DriveHatasi as e:
            logger.warning("yedekleme: Drive hatası (%s): %s", e.tur, e.teknik)
            rapor["hata_tur"], rapor["teknik"] = ("dolu" if e.tur == "dolu" else
                                                  "api-kapali" if e.tur == "api-kapali" else "drive"), e.teknik
            rapor["hata"] = (str(e) if e.tur in ("dolu", "api-kapali")
                             else M("yedek.drive-reddetti" if e.tur == "reddetti" else "yedek.drive-gecici"))
        except Exception as e:  # noqa: BLE001
            # Ağ kesildi / Google yanıt vermedi: ham istisna metni ("Server disconnected…")
            # kullanıcı cümlesi değildir → `teknik`e gider, ekrana söylenecek şey `ag-hatasi`.
            logger.exception("yedekleme turu düştü")
            rapor["hata"], rapor["hata_tur"], rapor["teknik"] = M("yedek.ag-hatasi"), "ag", str(e)
        finally:
            _CALISIYOR = False
            _CANLI = None

        if rapor["hata"]:
            # Yarıda kalan kaynak "yarida", hiç sıra gelmeyenler "sira-gelmedi": panel
            # her klasörün KENDİ durumunu söyler (hepsi "hata" demek yanlış olurdu).
            for k in rapor["kaynaklar"]:
                if k["durum"] == "suruyor":
                    k["durum"] = "yarida"
                elif k["durum"] == "sirada":
                    k["durum"] = "sira-gelmedi"
        rapor["tam"] = (not rapor["hata"]) and not rapor.get("tavan_doldu") \
            and not any(k["durum"] == "yol-yok" for k in rapor["kaynaklar"])
        rapor["bitti"] = datetime.now(timezone.utc).isoformat()
        rapor["saniye"] = round((datetime.now(timezone.utc) - basladi).total_seconds(), 1)
        ayar = ayarlar()                      # tur sırasında ayar değişmiş olabilir
        ayar["son_tur"] = rapor
        ayar_yaz(ayar)
        return rapor


async def _tur_govde(ayar: dict, rapor: dict) -> None:
    istisnalar = _istisnalar(ayar)
    tavan_bayt = int(ayar.get("tek_dosya_tavani_mb", 200)) * 1024 * 1024
    tur_tavani = int(ayar.get("tur_bayt_tavani_mb", 2048)) * 1024 * 1024

    kaynaklar = etkin_kaynaklar(ayar)
    # Hepsi baştan "sirada": hata ortasında kesilen turda hangi klasöre HİÇ sıra
    # gelmediği de raporda yazılı kalır (panel "yedekte" sanmasın).
    for kaynak in kaynaklar:
        rapor["kaynaklar"].append({
            "id": kaynak["id"], "ad": kaynak["ad"], "durum": "sirada",
            "yuklenen": 0, "guncellenen": 0, "atlanan": 0, "kaynakta_yok": 0,
            "buyuk_atlandi": 0, "tavan_atlanan": 0,
        })

    kok_id = await _kok_klasor_id(ayar)

    for kaynak, k_rapor in zip(kaynaklar, rapor["kaynaklar"]):
        # 🔴 Klasör yok (harici disk çıkarıldı / yeniden adlandırıldı / silindi): `tara()` sessizce
        # boş dönerdi ve tur "hatasız, 0 yeni" biterdi. Burada SÖYLENİR; indekse ve Drive'a
        # dokunulmaz — silindi mi takılı değil mi bilemeyiz, yedeği "kaynakta yok" diye
        # işaretleyip eski kaydı bozmak da yanlış olurdu.
        if not Path(kaynak["yol"]).is_dir():
            k_rapor["durum"] = "yol-yok"
            continue

        k_rapor["durum"] = "suruyor"
        indeks = indeks_oku(kaynak["id"])
        gorulen: set[str] = set()
        yazilmayan, son_yazim = 0, time.monotonic()

        try:
            klasor_id = await _kaynak_klasoru(kaynak, kok_id, ayar)

            for tam, gorece, boyut, mtime in tara(kaynak, istisnalar):
                gorulen.add(gorece)
                kayit = indeks.get(gorece)

                if boyut > tavan_bayt:
                    # Sessizce atlamak, "yedeğim var" sanan kullanıcı üretir.
                    rapor["buyuk_atlandi"].append({"yol": gorece, "mb": round(boyut / 1048576, 1),
                                                   "kaynak": kaynak["id"]})
                    k_rapor["buyuk_atlandi"] += 1
                    k_rapor["atlanan"] += 1
                    continue

                # Hızlı eleme: boyut ve mtime aynıysa dosyaya hiç dokunma. Milyonlarca
                # dosyada md5 hesaplamak turu saatlere çıkarırdı. (Tavan denetiminden ÖNCE:
                # tavan dolduktan sonra değişmemiş dosyalar "tavan yüzünden atlandı"
                # sayılmasın — yoksa her gün "yarım" görünürdü.)
                wal = _wal_imzasi(tam)
                if (kayit and kayit.get("boyut") == boyut and kayit.get("mtime") == mtime
                        and kayit.get("wal") == wal):
                    k_rapor["atlanan"] += 1
                    rapor["atlanan"] += 1
                    continue

                if rapor["bayt"] >= tur_tavani:
                    rapor["tavan_doldu"] = True
                    rapor["tavan_atlanan"] = rapor.get("tavan_atlanan", 0) + 1
                    k_rapor["tavan_atlanan"] += 1
                    continue

                gecici_dizin = None
                yuklenecek = tam
                try:
                    if tam.suffix == ".db":
                        yuklenecek = _sqlite_anlik(tam)
                        gecici_dizin = yuklenecek.parent
                    ozet = _md5(yuklenecek)
                    if kayit and kayit.get("md5") == ozet:
                        # İçerik aynı, yalnız mtime oynamış (kopyalama/senkron aracı).
                        kayit.update({"boyut": boyut, "mtime": mtime, "wal": wal})
                        k_rapor["atlanan"] += 1
                        rapor["atlanan"] += 1
                        continue

                    hedef_klasor = await _alt_klasor(klasor_id, Path(gorece).parent, kaynak, indeks)
                    try:
                        sonuc = await _g.dosya_yukle(
                            yuklenecek, Path(gorece).name, hedef_klasor,
                            dosya_id=(kayit or {}).get("drive_id"),
                        )
                    except _g.DriveHatasi as e:
                        if e.tur != "bulunamadi":
                            raise
                        # Saklı kimlik ölü: kullanıcı dosyayı ya da üst klasörünü Drive'da
                        # sildi. Kimlikleri bırak, klasör zincirini yeniden kur, dosyayı YENİ
                        # olarak bir kez daha gönder. (Onarmazsak dosya her gün değiştiği için
                        # tur her gün aynı 404'e çarpar ve yedek kalıcı olarak durur.)
                        _dizin_onbellegini_dusur(indeks, Path(gorece).parent)
                        hedef_klasor = await _alt_klasor(klasor_id, Path(gorece).parent, kaynak, indeks)
                        sonuc = await _g.dosya_yukle(yuklenecek, Path(gorece).name, hedef_klasor)
                except FileNotFoundError:
                    continue           # tur sırasında silindi
                except PermissionError:
                    k_rapor["atlanan"] += 1
                    continue
                finally:
                    if gecici_dizin:
                        shutil.rmtree(gecici_dizin, ignore_errors=True)

                yeni = bool(kayit is None or not kayit.get("drive_id"))
                indeks[gorece] = {
                    "md5": ozet, "boyut": boyut, "mtime": mtime, "wal": wal,
                    "drive_id": sonuc.get("id"),
                    "yuklendi": datetime.now(timezone.utc).isoformat(),
                }
                rapor["bayt"] += boyut
                if yeni:
                    k_rapor["yuklenen"] += 1
                    rapor["yuklenen"] += 1
                else:
                    k_rapor["guncellenen"] += 1
                    rapor["guncellenen"] += 1

                # Ara kayıt: tur burada kesilirse (hata, uygulama kapanışı) yüklenenler
                # indekste durur ve sonraki tur yalnız kalanı gönderir.
                yazilmayan += 1
                if yazilmayan >= _INDEKS_ARALIK or time.monotonic() - son_yazim >= _INDEKS_SANIYE:
                    indeks_yaz(kaynak["id"], indeks)
                    yazilmayan, son_yazim = 0, time.monotonic()

            # Politika ①: kaynakta olmayanı Drive'dan SİLME — yalnız işaretle.
            # (Yalnız tarama TAMAMLANDIYSA: yarıda kalan turun `gorulen` kümesi eksiktir,
            # eksik kümeyle işaretlemek var olan dosyaları "kaynakta yok" diye damgalardı.)
            yok = 0
            for gorece, kayit in indeks.items():
                if gorece.startswith("#"):
                    continue
                if gorece not in gorulen:
                    kayit["kaynakta_yok"] = True
                    yok += 1
                else:
                    kayit.pop("kaynakta_yok", None)
            k_rapor["kaynakta_yok"] = yok
            rapor["kaynakta_yok"] += yok

            k_rapor["durum"] = "yarim" if k_rapor["tavan_atlanan"] else "tamam"
            if k_rapor["durum"] == "tamam":
                indeks[_META] = {**(indeks.get(_META) or {}), "son_tam": datetime.now(timezone.utc).isoformat()}
        finally:
            # Normal da, hata da, iptal de: yüklenenin kaydı HER ZAMAN diske iner.
            try:
                indeks_yaz(kaynak["id"], indeks)
            except OSError as e:  # noqa: BLE001
                logger.warning("yedek indeksi yazılamadı (%s)", e)


async def _kok_klasor_id(ayar: dict) -> str:
    """Drive'daki 'Yuki Yedek' klasörü — kimliği saklanır ama DOĞRULANIR.

    Kullanıcı klasörü Drive'da silerse saklı kimlik ölür; doğrulamasak her yükleme
    404 alır ve kullanıcı sebebini asla öğrenemez.
    """
    kid = ayar.get("kok_klasor_id")
    if kid and await _g.klasor_gecerli_mi(kid):
        return kid
    kid = await _g.klasor_al_veya_olustur(KOK_KLASOR)
    ayar["kok_klasor_id"] = kid
    ayar_yaz(ayar)
    return kid


async def _kaynak_klasoru(kaynak: dict, kok_id: str, ayar: dict) -> str:
    kid = kaynak.get("drive_klasor_id")
    if kid and await _g.klasor_gecerli_mi(kid):
        return kid
    kid = await _g.klasor_al_veya_olustur(kaynak["ad"], kok_id)
    if kaynak["id"] != "yuki":
        for k in ayar["kaynaklar"]:
            if k["id"] == kaynak["id"]:
                k["drive_klasor_id"] = kid
        ayar_yaz(ayar)
    else:
        kaynak["drive_klasor_id"] = kid
    return kid


def _dizin_onbellegini_dusur(indeks: dict, gorece_dizin: Path) -> None:
    """Dosyanın klasör zincirindeki `#dizin:` kimliklerini unut (Drive'da silinmiş olabilirler)."""
    parca_yolu = ""
    for parca in gorece_dizin.parts:
        if parca in (".", ""):
            continue
        parca_yolu = f"{parca_yolu}/{parca}" if parca_yolu else parca
        indeks.pop(f"#dizin:{parca_yolu}", None)


async def _alt_klasor(kok_id: str, gorece_dizin: Path, kaynak: dict, indeks: dict) -> str:
    """Drive'da klasör ağacını aynala. Kimlikler indekste `#dizin:` ile saklanır.

    ⚠️ Her yüklemede klasör aramak, derin ağaçta dosya sayısı kadar ek istek eder
    (Drive kotası istek başına sayar). Kimlikler bu yüzden indekste taşınır; indeks
    dosya kayıtlarıyla aynı yerde durduğu için kaynak silinince birlikte gider.
    """
    if str(gorece_dizin) in (".", ""):
        return kok_id
    parca_yolu = ""
    ebeveyn = kok_id
    for parca in gorece_dizin.parts:
        parca_yolu = f"{parca_yolu}/{parca}" if parca_yolu else parca
        anahtar = f"#dizin:{parca_yolu}"
        kayit = indeks.get(anahtar)
        if kayit and kayit.get("drive_id"):
            ebeveyn = kayit["drive_id"]
            continue
        ebeveyn = await _g.klasor_al_veya_olustur(parca, ebeveyn)
        indeks[anahtar] = {"drive_id": ebeveyn}
    return ebeveyn


# ── Durum ────────────────────────────────────────────────────────────────────

def _son_turdaki(son_tur: dict | None, kaynak_id: str) -> dict | None:
    for k in (son_tur or {}).get("kaynaklar") or []:
        if k.get("id") == kaynak_id:
            return k
    return None


def _zamanlama_bilgisi(ayar: dict) -> dict:
    """Saat KAYITLI olmak ile işin GERÇEKTEN kurulu olması ayrı sorular: kapalıyken ya da
    `SCHEDULER_ENABLED=false` iken kayıtlı saat hiçbir şey çalıştırmaz."""
    bilgi = {"kurulu": False, "sonraki": None}
    if not (ayar.get("zamanlama") and ayar.get("acik")):
        return bilgi
    try:
        from app.services import scheduler
        if not scheduler.SCHEDULER_ENABLED:
            return bilgi
        is_ = scheduler.get_scheduler().get_job(scheduler._YEDEKLEME_IS_ID)
        if is_:
            bilgi["kurulu"] = True
            z = getattr(is_, "next_run_time", None)
            bilgi["sonraki"] = z.isoformat() if z else None
    except Exception as e:  # noqa: BLE001
        logger.debug("zamanlama bilgisi okunamadı: %s", e)
    return bilgi


def durum() -> dict:
    ayar = ayarlar()
    son_tur = ayar.get("son_tur")
    canli = _CANLI if _CALISIYOR else None
    kaynaklar = []
    son_yedekler = []
    for k in etkin_kaynaklar(ayar):
        indeks = indeks_oku(k["id"])
        dosyalar = [v for a, v in indeks.items() if not a.startswith("#")]
        son_tam = (indeks.get(_META) or {}).get("son_tam")
        if son_tam:
            son_yedekler.append(son_tam)
        tur = _son_turdaki(son_tur, k["id"])
        kaynaklar.append({
            "id": k["id"], "ad": k["ad"], "yol": k["yol"],
            "dosya": len(dosyalar),
            "bayt": sum(int(v.get("boyut", 0)) for v in dosyalar),
            "kaynakta_yok": sum(1 for v in dosyalar if v.get("kaynakta_yok")),
            "sistem": k["id"] == "yuki",
            "yol_var": Path(k["yol"]).is_dir(),
            "son_yedek": son_tam,                   # bu klasörün SON TAM taramasının zamanı
            "tur": tur,                             # son turdaki durumu (tamam · yarim · yarida …)
            "canli": (_son_turdaki(canli, k["id"]) if canli else None),
        })
    return {
        "acik": ayar.get("acik", False),
        "yuki_verisi": ayar.get("yuki_verisi", True),
        "zamanlama": ayar.get("zamanlama"),
        "zamanlama_bilgi": _zamanlama_bilgisi(ayar),
        "tavanlar": {"tek_dosya_mb": int(ayar.get("tek_dosya_tavani_mb", 200)),
                     "tur_mb": int(ayar.get("tur_bayt_tavani_mb", 2048))},
        "kaynaklar": kaynaklar,
        "tum_kaynaklar": ayar["kaynaklar"],
        "calisiyor": calisiyor_mu(),
        "canli": ({"yuklenen": canli["yuklenen"], "guncellenen": canli["guncellenen"],
                   "bayt": canli["bayt"]} if canli else None),
        "son_tur": son_tur,
        "son_yedek": max(son_yedekler) if son_yedekler else None,   # en az bir klasörün son TAM yedeği
        "baglanti": _baglanti(),
    }


def _baglanti() -> dict:
    """`token`/`kimlik` eski alanlar (geriye uyum). Asıl hüküm `durum` — token DOSYASI var
    demek bağlantı SAĞLAM demek değildir (panel 11'in "yalan yeşil" dersi); ağsız okunur."""
    g = _g.durum()
    return {"token": _g.token_var(), "kimlik": _g.kimlik_var(),
            "durum": g["durum"], "sebep": g["sebep"], "son_deneme": g["son_deneme"]}
