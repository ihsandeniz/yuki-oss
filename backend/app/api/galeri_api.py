"""Galeri API — PC'deki resim/video klasörlerinde SALT OKUNUR gezgin.

## Tasarım kararları

**K1 · Dosyalar KOPYALANMAZ, yerinde okunur.** Galeri bir *gezgindir*; dosyaları
kopyalamak diski ikiye katlar ve "hangisi güncel?" sorusunu doğurur.

**K2 · Kök klasör listesi AYARDAN gelir.** Öncelik: `YUKI_GALERI_KOKLER` ortam
değişkeni (`os.pathsep` ile ayrılmış yollar) → `<veri dizini>/galeri/galeri-ayar.json`
(`{"kokler": [...]}`) → kullanıcının `~/Pictures` / `~/Resimler` klasörü.

**K3 · Küçük resim üretilir ve önbelleğe alınır** (`<veri dizini>/galeri/onbellek/`).
Kod dizinine YAZILMAZ — paketli uygulama salt okunur olabilir.

**K4 · Video AKITILIR, blob'a indirilmez.** `/dosya` ucu `Range` başlığını
destekler (`206 Partial Content`).

**K6 · SALT OKUNUR.** Silme / taşıma / yeniden adlandırma / çöpe atma uçları
YOKTUR. Tek yazma: kök klasör LİSTESİ (`POST /kok`, `DELETE /kok/{id}`, seçici
`GET /gozat`) — yalnız ayar dosyasına yazar, dosyalara dokunmaz. Kapısı
`_ekleme_kapisi` (aşağıda § Kök ekleme).

## Güvenlik — beş katman, her uçta

1. `_yol_uygun` — `_is_safe_path`'i (tools/_base.py'deki mevcut fonksiyon,
   kopyalanmaz, çağrılır) sarmalar ve üstüne takılı diskleri ekler.
2. Ayarlı kökler içinde mi — ev dizininin tamamı DEĞİL (`~/.ssh` de ev dizinindedir)
3. Uzantı beyaz listesinde mi
4. Dosya imzası uzantıyla uyuşuyor mu (`duvar_api._imza_gecerli`)
5. Sembolik bağ çözülüp tekrar kontrol edilir

🔴 `id` ham yol DEĞİLDİR. URL'de ham yol taşımak traversal yüzeyidir ve loglara
sızar. Sunucu her yola kısa bir kimlik verir (sha1[:16]); istemci yalnız kimliği
görür. Kayıt bellektedir — süreç yeniden başlayınca `_yeniden_tara()` ile
tembel olarak geri kurulur.
"""

from __future__ import annotations

import errno
import hashlib
import json
import logging
import mimetypes
import os
import re
import time
from pathlib import Path
from typing import Any, Iterator
from urllib.parse import quote as _urlquote

from fastapi import APIRouter, HTTPException, Query, Request
from pydantic import BaseModel
from fastapi.responses import FileResponse, StreamingResponse

from app.api.duvar_api import BICIMLER, _imza_gecerli
from app.services.tools._base import _is_safe_path

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/galeri", tags=["galeri"])

# ── Depo ─────────────────────────────────────────────────────────── #
from app.config import DATA_DIR

VERI = DATA_DIR / "galeri"
AYAR_YOLU = VERI / "galeri-ayar.json"
ONBELLEK = VERI / "onbellek"

# ── Kabul edilen biçimler ────────────────────────────────────────── #
# duvar_api.BICIMLER'in alt kümesi: galeri .ogv taşımaz (tarayıcı desteği zayıf),
# gerisi aynı. Tek kaynak orada — imza tablosu iki yerde tutulmaz.
RESIM_UZANTI = {".jpg", ".jpeg", ".png", ".webp", ".avif", ".gif"}
VIDEO_UZANTI = {".mp4", ".m4v", ".webm"}
MEDYA_UZANTI = RESIM_UZANTI | VIDEO_UZANTI

# Küçük resim kademeleri (uzun kenar px). İstemci kutucuk boyutuna göre ister:
# 🔴 Tek boyut yanlıştı — 400px "çok büyük" kademede (sütun 440-620px) BULANIK
# görünüyor, "küçük" kademede (120px) ise gereksiz bayt. Kademeler önbellekte
# ayrı dosyalardır (ad özetine boyut da girer).
# 1400: "çok büyük" kademede kart ~620px; 2× ekranda 1240px ister. 800 ile
# sınırlamak orada bulanıklık üretiyordu.
KUCUK_KADEMELER = (200, 400, 800, 1400)
KUCUK_KENAR = 400          # varsayılan (istemci belirtmezse)
KUCUK_KALITE = 78
TARAMA_DERINLIK = 6        # kökten itibaren en fazla bu kadar alt klasör
TARAMA_AZAMI = 20000       # kayıt patlamasına karşı sert tavan
_AKIS_PARCA = 512 * 1024   # video akıtma parça boyutu


# ── Kimlik kaydı (yol ↔ id) ──────────────────────────────────────── #
_KAYIT: dict[str, str] = {}      # id → mutlak yol (str)
_son_tarama = 0.0


def _kimlik(p: Path) -> str:
    """Yol → kısa kimlik. Deterministik: aynı yol her zaman aynı id."""
    kid = hashlib.sha1(str(p).encode("utf-8")).hexdigest()[:16]
    _KAYIT[kid] = str(p)
    return kid


def _varsayilan_kokler() -> list[str]:
    ortam = os.environ.get("YUKI_GALERI_KOKLER", "")
    if ortam.strip():
        return [x for x in ortam.split(os.pathsep) if x.strip()]
    ev = Path.home()
    adaylar = [ev / "Resimler", ev / "Pictures"]
    return [str(a.resolve()) for a in adaylar if a.is_dir()]


def _varsayilan_ayar() -> dict[str, Any]:
    return {"kokler": _varsayilan_kokler()}


def _ayar_oku() -> dict[str, Any]:
    if os.environ.get("YUKI_GALERI_KOKLER", "").strip() or not AYAR_YOLU.exists():
        return _varsayilan_ayar()
    try:
        d = json.loads(AYAR_YOLU.read_text("utf-8"))
    except Exception:
        # Bozuk ayar galeriyi öldürmez — varsayılana düşer (duvar_api deseni).
        logger.warning("galeri-ayar.json okunamadı, varsayılana düşülüyor", exc_info=True)
        return _varsayilan_ayar()
    kokler = [str(x) for x in (d.get("kokler") or []) if isinstance(x, str)]
    out: dict[str, Any] = {"kokler": kokler}
    return out


def _takilabilir_kokler() -> list[Path]:
    """udisks2'nin kullanıcı disklerini bağladığı yerler — yalnız VAR OLANLAR.

    Önbelleklenmez: disk takılıp çıkarılır, sonuç her çağrıda yeniden ölçülür
    (iki `is_dir()` syscall'ı, kök listesi zaten her istekte okunuyor).
    """
    kullanici = os.environ.get("USER") or ""
    if not kullanici:
        return []
    adaylar = [Path("/run/media") / kullanici, Path("/media") / kullanici]
    return [a for a in adaylar if a.is_dir()]


def _yol_uygun(p: Path) -> bool:
    """Katman 1 (galeri sürümü): ev + /tmp **ya da** takılı bir disk altında mı?

    🔴 `_is_safe_path` GENİŞLETİLMEDİ, sarmalandı. O fonksiyon `write_file` /
    `append_file` gibi **YAZAN** araçların da kapısıdır (`tools/_base.py` →
    `_is_safe_write_path` onu çağırır); `/run/media`'yı oraya eklemek galeriyle
    hiç ilgisi olmayan bir yazma yüzeyi açardı. Galeri salt okunur olduğu için
    (K6) kapı yalnız bu modülde genişletilir.

    ⚠️ Diğer dört katman aynen koşar: ayarlı kök üyeliği (`_kok_altinda`),
    uzantı beyaz listesi, dosya imzası, `resolve()` sonrası tekrar kontrol.
    Yani takılı disk *gezilebilir* hâle gelir — otomatik olarak *taranmaz*;
    kullanıcı onu ＋ Klasör ile kök olarak eklemedikçe galeriye girmez.
    """
    if _is_safe_path(p):
        return True
    try:
        gercek = p.resolve()
    except Exception:
        return False
    gs = str(gercek)
    return any(gercek == k or gs.startswith(str(k) + os.sep)
               for k in _takilabilir_kokler())


def _kok_yollari() -> list[Path]:
    """Ayarlı kökler — var olan ve güvenli olanlar. Silinmiş klasör sessizce elenir."""
    out = []
    for s in _ayar_oku()["kokler"]:
        try:
            p = Path(s).expanduser().resolve()
        except Exception:
            continue
        if p.is_dir() and _yol_uygun(p):
            out.append(p)
    return out


# ── Güvenlik ─────────────────────────────────────────────────────── #

def _kok_altinda(p: Path, kokler: list[Path] | None = None) -> bool:
    """Katman 2: yol ayarlı köklerden birinin altında mı?

    `_is_safe_path` tek başına YETMEZ — o ev dizininin tamamına izin verir,
    `~/.ssh` de ev dizinindedir.
    """
    kokler = kokler if kokler is not None else _kok_yollari()
    ps = str(p)
    return any(p == k or ps.startswith(str(k) + os.sep) for k in kokler)


def _atla_mi(p: Path) -> bool:
    """Bu dizin/dosya taramanın DIŞINDA mı?

    🔴 Galerinin kendi veri dizini (küçük resim önbelleği) taranmamalı: veri
    dizini bir kökün altındaysa galeri kendi ürettiği küçük resimleri içerik
    sanardı.
    Gizli dosyalar da burada elenir (tek kapı, üç yerde ayrı kural olmasın).
    """
    if p.name.startswith("."):
        return True
    try:
        return p == VERI or str(p).startswith(str(VERI) + os.sep)
    except Exception:
        return False


def _medya_mi(p: Path) -> bool:
    return p.suffix.lower() in MEDYA_UZANTI


def _tip(p: Path) -> str:
    return "video" if p.suffix.lower() in VIDEO_UZANTI else "resim"


# ── Disk okunamıyor ────────────────────────────────────────────── #
# 🔴 Çıkarılabilir disk koparsa klasör listesi çekirdeğin önbelleğinden gelmeye
# devam eder ama dosyalar okunamaz (EIO). `_imza_tamam` bunu sessizce False'a
# çevirirse kullanıcı 415 "içerik uyuşmuyor" görür ve dosyaları bozuk sanar.
# Aygıt hatası uzantı hatasından AYRI: 503 + kök başına uyarı.
_DISK_ERRNO = {errno.EIO, errno.ENXIO, errno.ENODEV}
_DISK_HATASI: dict[str, float] = {}      # kök → son disk hatası zamanı
DISK_HATA_PENCERE = 120.0                # /kokler bu kadar sn "disk hatası" der
_DISK_LOG_ARALIK = 60.0


class DiskOkunamiyor(Exception):
    pass


def _disk_hatasi_mi(e: BaseException) -> bool:
    return isinstance(e, OSError) and e.errno in _DISK_ERRNO


def _disk_hatasi_kaydet(p: Path, e: OSError) -> None:
    kok = next((str(k) for k in _kok_yollari() if _kok_altinda(p, [k])), str(p.parent))
    simdi = time.time()
    onceki = _DISK_HATASI.get(kok, 0.0)
    _DISK_HATASI[kok] = simdi
    if simdi - onceki >= _DISK_LOG_ARALIK:
        logger.warning("galeri: disk okunamıyor (%s, errno %s) — kök %s; aygıt kopmuş "
                       "olabilir, yeniden bağlayıp kilidini açın", e.strerror, e.errno, kok)


def _disk_503() -> HTTPException:
    return HTTPException(503, "Disk okunamıyor — bağlantı kopmuş olabilir.",
                         headers={"X-Galeri-Hata": "disk", "Cache-Control": "no-store"})


def _imza_tamam(p: Path) -> bool:
    """Katman 4: içerik uzantıyla uyuşuyor mu? (.jpg adlı metin dosyası reddedilir)

    Aygıt hatasında (EIO…) False DEMEZ, `DiskOkunamiyor` atar — yukarıdaki not."""
    uz = p.suffix.lower()
    if uz not in BICIMLER:
        return False
    try:
        with p.open("rb") as f:
            bas = f.read(16)
    except OSError as e:
        if _disk_hatasi_mi(e):
            _disk_hatasi_kaydet(p, e)
            raise DiskOkunamiyor() from e
        return False
    return _imza_gecerli(uz, bas)


def _guvenli_dosya(p: Path) -> Path:
    """Beş katmanın hepsi. Geçemezse HTTPException."""
    try:
        gercek = p.resolve()                        # katman 5: symlink çözülür
    except OSError:
        raise HTTPException(404, "Dosya bulunamadı.")
    if not _yol_uygun(gercek):                   # katman 1
        raise HTTPException(403, "Bu yola erişim yok.")
    if not _kok_altinda(gercek):                    # katman 2
        raise HTTPException(403, "Bu yol galeri klasörlerinin dışında.")
    if not gercek.is_file():
        raise HTTPException(404, "Dosya bulunamadı.")
    if not _medya_mi(gercek):                       # katman 3
        raise HTTPException(415, "Desteklenmeyen dosya türü.")
    try:
        imza = _imza_tamam(gercek)                  # katman 4
    except DiskOkunamiyor:
        raise _disk_503()
    if not imza:
        raise HTTPException(415, "Dosya içeriği uzantısıyla uyuşmuyor.")
    return gercek


def _guvenli_klasor(p: Path) -> Path:
    try:
        gercek = p.resolve()
    except OSError:
        raise HTTPException(404, "Klasör bulunamadı.")
    if not _yol_uygun(gercek):
        raise HTTPException(403, "Bu yola erişim yok.")
    if not _kok_altinda(gercek):
        raise HTTPException(403, "Bu klasör galeri klasörlerinin dışında.")
    if not gercek.is_dir():
        raise HTTPException(404, "Klasör bulunamadı.")
    return gercek


# ── Tarama ───────────────────────────────────────────────────────── #

def _gizli(p: Path) -> bool:
    return p.name.startswith(".")


def _yeniden_tara() -> int:
    """Kökleri yürü, kimlik kaydını doldur.

    Neden: kayıt bellektedir. Backend yeniden başlayınca panelde açık duran
    galerinin id'leri ölürdü — kullanıcı için bu "galeri bozuldu" demektir.
    Bulunamayan bir id geldiğinde bir kez bu çalışır, sonra tekrar bakılır.
    """
    global _son_tarama
    sayac = 0
    for kok in _kok_yollari():
        _kimlik(kok)
        yigin: list[tuple[Path, int]] = [(kok, 0)]
        while yigin and sayac < TARAMA_AZAMI:
            klasor, derinlik = yigin.pop()
            try:
                girisler = list(os.scandir(klasor))
            except OSError:
                continue
            for g in girisler:
                if sayac >= TARAMA_AZAMI:
                    break
                ad = g.name
                if _atla_mi(Path(g.path)):
                    continue
                try:
                    if g.is_dir(follow_symlinks=False):
                        if derinlik < TARAMA_DERINLIK:
                            yigin.append((Path(g.path), derinlik + 1))
                            _kimlik(Path(g.path))
                            sayac += 1
                    elif g.is_file(follow_symlinks=False) and Path(ad).suffix.lower() in MEDYA_UZANTI:
                        _kimlik(Path(g.path))
                        sayac += 1
                except OSError:
                    continue
    _son_tarama = time.time()
    return sayac


def _coz(kid: str) -> Path:
    """id → yol. Bilinmiyorsa bir kez yeniden tara, sonra pes et."""
    if not kid or not re.fullmatch(r"[0-9a-f]{16}", kid):
        raise HTTPException(400, "Geçersiz kimlik.")
    yol = _KAYIT.get(kid)
    if yol is None:
        _yeniden_tara()
        yol = _KAYIT.get(kid)
    if yol is None:
        raise HTTPException(404, "Bu kimlik artık geçerli değil (dosya taşınmış olabilir).")
    return Path(yol)


def _video_olcu(p: Path) -> tuple[int | None, int | None]:
    """Videonun en×boy'u — ffprobe ile, tek çağrı.

    Nehir düzeninde video kartı da doğru oranda dursun diye. ffprobe yoksa
    (None, None) → istemci 16/9 varsayar.
    """
    import subprocess
    try:
        r = subprocess.run(
            ["ffprobe", "-v", "error", "-select_streams", "v:0",
             "-show_entries", "stream=width,height", "-of", "csv=p=0:s=x", str(p)],
            capture_output=True, text=True, timeout=8)
        en, boy = r.stdout.strip().split("x")[:2]
        return int(en), int(boy)
    except Exception:
        return None, None


def _olcu(p: Path) -> tuple[int, int] | tuple[None, None]:
    """Resmin en×boy'u — **dosyayı açmadan**, yalnız başlıktan.

    Nehir (masonry) düzeni için şart: oran bilinmezse kart yüklenince yükseklik
    değişir ve sütunlar zıplar. Pillow `Image.open` tembeldir, `.size` başlığı
    okur (~0,15 ms); 120'lik sayfada ~18 ms.
    """
    if p.suffix.lower() in VIDEO_UZANTI:
        return _video_olcu(p)
    try:
        from PIL import Image
        with Image.open(p) as im:
            en, boy = im.size
            # EXIF 5-8 = 90°/270° dönük → en/boy yer değiştirir, yoksa dikey
            # telefon fotoğrafı ızgarada yatay kutu ister ve düzen bozulur.
            try:
                yon = (im.getexif() or {}).get(274, 1)
                if yon in (5, 6, 7, 8):
                    en, boy = boy, en
            except Exception:
                pass
            return int(en), int(boy)
    except Exception:
        return None, None


# ── Küçük resim ──────────────────────────────────────────────────── #

def _kucuk_ad(p: Path, kenar: int = KUCUK_KENAR) -> str:
    """Kaynak yol + mtime + boyut + KENAR özeti. Dosya değişirse ad değişir →
    bayat küçük resim gösterilmez (önbellek anahtarı içeriğe bağlı)."""
    try:
        st = p.stat()
        imza = f"{p}|{int(st.st_mtime)}|{st.st_size}|{kenar}"
    except OSError:
        imza = f"{p}|{kenar}"
    return hashlib.sha1(imza.encode("utf-8")).hexdigest()[:24] + ".webp"


def _video_karesi(kaynak: Path, hedef: Path, kenar: int = KUCUK_KENAR) -> bool:
    """Videonun ilk anlamlı karesini WebP küçük resme çevir.

    🔑 Neden eklendi (2026-09-12): ilk sürümde video kartları boş "VİDEO"
    kutusuydu; video ağırlıklı klasörlerde nehir düzeninin büyük kısmı
    boş kutuya dönüyordu.
    ⚠️ 1. saniyeden alınır: birçok videonun 0. karesi siyah açılıştır.
    Video 1 sn'den kısaysa ffmpeg boş çıktı verir → 0. kareye düşülür.
    """
    import subprocess
    gecici = hedef.with_suffix(".webp.tmp")
    for saniye in ("1", "0"):
        try:
            r = subprocess.run(
                # 🔴 `-f webp` ŞART: çıktı adı `.webp.tmp` ile bitiyor ve ffmpeg
                # biçimi uzantıdan türetir — bayrak olmadan "bilinmeyen format"
                # deyip sessizce 0 baytla çıkıyordu (09-12'de tam bu yaşandı,
                # elle koşan komut çalışırken Python'daki çağrı hep başarısızdı).
                ["ffmpeg", "-y", "-ss", saniye, "-i", str(kaynak), "-frames:v", "1",
                 "-vf", f"scale='min({kenar},iw)':-2", "-f", "webp",
                 str(gecici)],
                capture_output=True, timeout=20)
            if r.returncode == 0 and gecici.exists() and gecici.stat().st_size > 0:
                gecici.replace(hedef)
                return True
            if saniye == "0":
                logger.info("video karesi alınamadı (%s): %s", kaynak.name,
                            (r.stderr or b"")[-200:].decode("utf-8", "replace"))
            gecici.unlink(missing_ok=True)
        except Exception:
            logger.info("video karesi alınamadı: %s", kaynak, exc_info=True)
            gecici.unlink(missing_ok=True)
            return False
    return False


# Disk önbelleği sınırı. 6.981 medya × 3 kademe × ~20 KB ≈ 400 MB'a kadar
# büyüyebilir; kişisel makinede sessizce yer yemesin.
ONBELLEK_AZAMI_MB = 300
_uretim_sayaci = 0


def _onbellek_buda(zorla: bool = False) -> int:
    """Önbellek sınırı aşıldıysa EN ESKİ ERİŞİLENDEN başlayarak buda.

    🔑 Ölçüt `st_atime` (son erişim) — `mtime` üretim anını tutar, oysa asıl
    soru "bu küçük resme hâlâ bakılıyor mu". Silinen dosya kaybolmaz, yalnız
    bir sonraki isteğe yeniden üretilir (~40 ms).
    ⚠️ Her üretimde değil, 200 üretimde bir çalışır: dizini her seferinde
    taramak, önlemeye çalıştığı maliyetin kendisi olurdu.
    """
    global _uretim_sayaci
    _uretim_sayaci += 1
    if not zorla and _uretim_sayaci % 200 != 0:
        return 0
    if not ONBELLEK.is_dir():
        return 0
    try:
        dosyalar = [(p, p.stat()) for p in ONBELLEK.glob("*.webp")]
    except OSError:
        return 0
    toplam = sum(st.st_size for _, st in dosyalar)
    sinir = ONBELLEK_AZAMI_MB * 1048576
    if toplam <= sinir:
        return 0
    dosyalar.sort(key=lambda x: x[1].st_atime)          # en eski erişilen önce
    silinen = 0
    hedef = sinir * 0.8                                  # %80'e in, sınırda yalpalama olmasın
    for yol, st in dosyalar:
        if toplam <= hedef:
            break
        try:
            yol.unlink()
            toplam -= st.st_size
            silinen += 1
        except OSError:
            continue
    logger.info("galeri önbelleği budandı: %d dosya silindi, %.0f MB kaldı",
                silinen, toplam / 1048576)
    return silinen


def _kucuk_uret(kaynak: Path, kenar: int = KUCUK_KENAR) -> Path | None:
    """WebP küçük resim üret (önbellekliyse yeniden üretmez)."""
    ONBELLEK.mkdir(parents=True, exist_ok=True)
    hedef = ONBELLEK / _kucuk_ad(kaynak, kenar)
    if hedef.exists() and hedef.stat().st_size > 0:
        return hedef
    if kaynak.suffix.lower() in VIDEO_UZANTI:
        if not _video_karesi(kaynak, hedef, kenar):
            return None
        _onbellek_buda()
        return hedef
    try:
        from PIL import Image, ImageOps
    except ImportError:      # pragma: no cover — Pillow yoksa ızgara tam boyuta düşer
        logger.warning("Pillow yok — küçük resim üretilemiyor")
        return None
    try:
        with Image.open(kaynak) as im:
            im = ImageOps.exif_transpose(im)     # telefon fotoğrafı yan durmasın
            im.thumbnail((kenar, kenar))
            if im.mode not in ("RGB", "RGBA"):
                im = im.convert("RGB")
            gecici = hedef.with_suffix(".webp.tmp")
            im.save(gecici, "WEBP", quality=KUCUK_KALITE, method=4)
            gecici.replace(hedef)                # atomik — yarım dosya okunmaz
        _onbellek_buda()
        return hedef
    except Exception as e:
        if _disk_hatasi_mi(e):                   # başlık önbellekteydi, gövde okunamadı
            _disk_hatasi_kaydet(kaynak, e)
            raise _disk_503()
        logger.info("küçük resim üretilemedi: %s", kaynak, exc_info=True)
        return None


# ── Range (video akıtma) ─────────────────────────────────────────── #

_RANGE_RE = re.compile(r"bytes=(\d*)-(\d*)")


def _parcali_oku(p: Path, bas: int, uzunluk: int) -> Iterator[bytes]:
    kalan = uzunluk
    with p.open("rb") as f:
        f.seek(bas)
        while kalan > 0:
            parca = f.read(min(_AKIS_PARCA, kalan))
            if not parca:
                break
            kalan -= len(parca)
            yield parca


def _indirme_basligi(ad: str) -> str:
    """`Content-Disposition: attachment` — ASCII yedeği + UTF-8 gerçek ad.

    🔴 Sadece `filename=` yazmak YETMEZ: dosya adları Türkçe (`kış tatili.jpg`)
    ve başlık gövdesi latin-1 kodlanır → UnicodeEncodeError ile 500. RFC 6266
    ikili yazım şart: ASCII'ye indirgenmiş yedek + `filename*=UTF-8''<yüzde>`.
    """
    yedek = ad.encode("ascii", "replace").decode("ascii").replace('"', "_")
    return f"attachment; filename=\"{yedek}\"; filename*=UTF-8''{_urlquote(ad)}"


def _dosya_yanit(p: Path, range_basligi: str | None, indir: bool = False):
    """Tam gövde ya da `206 Partial Content`.

    🔴 Video için Range ŞART: blob'a indirmek belleği şişirir ve tarayıcı ileri
    saramaz. Starlette'in kendi Range desteğine yaslanmıyoruz — davranışı burada
    açık yazmak onu ölçülebilir kılar (`olc_galeri.py`).

    `indir=True` → `Content-Disposition: attachment`. Telefonda `<a download>`
    tek başına güvenilmez (mobil tarayıcı resmi indirmek yerine sekmede açar);
    hükmü sunucu verir.
    """
    tur = mimetypes.guess_type(p.name)[0] or "application/octet-stream"
    boyut = p.stat().st_size
    ortak = {
        "Accept-Ranges": "bytes",
        # Dosya kimliği içeriğe bağlı değil (yol özeti) → uzun önbellek yanlış
        # olurdu; kısa tutup doğrulamayı tarayıcıya bırakıyoruz.
        "Cache-Control": "private, max-age=300",
    }
    if indir:
        ortak["Content-Disposition"] = _indirme_basligi(p.name)

    if not range_basligi:
        return FileResponse(p, media_type=tur, headers=ortak)

    m = _RANGE_RE.fullmatch(range_basligi.strip())
    if not m:
        return FileResponse(p, media_type=tur, headers=ortak)

    bas_s, son_s = m.group(1), m.group(2)
    if bas_s == "":                      # "bytes=-500" → son 500 bayt
        if son_s == "":
            return FileResponse(p, media_type=tur, headers=ortak)
        uzun = min(int(son_s), boyut)
        bas, son = boyut - uzun, boyut - 1
    else:
        bas = int(bas_s)
        son = int(son_s) if son_s else boyut - 1
    son = min(son, boyut - 1)

    if bas >= boyut or bas > son:
        return StreamingResponse(
            iter(()), status_code=416,
            headers={"Content-Range": f"bytes */{boyut}", **ortak},
        )

    uzunluk = son - bas + 1
    return StreamingResponse(
        _parcali_oku(p, bas, uzunluk),
        status_code=206,
        media_type=tur,
        headers={
            "Content-Range": f"bytes {bas}-{son}/{boyut}",
            "Content-Length": str(uzunluk),
            **ortak,
        },
    )


# ── Uçlar ────────────────────────────────────────────────────────── #

@router.get("/kokler")
async def kokler():
    """Ayarlı kök klasörler + her birinin medya sayısı.

    🔑 Sayım `_tum_medya()` önbelleğinden türer, kök başına ayrı ağaç yürüyüşüyle
    değil. Ölçüldü: ayrı sayım bu ucu **36 ms**'ye çıkarıyordu ve aynı diski
    `/hepsi` için ikinci kez taramak demekti. Aynı veriden iki cevap üretmek
    ayrıca ikisinin ayrışma riskidir (kökte 6.981, akışta başka sayı).
    """
    kok_listesi = _kok_yollari()
    sayim: dict[str, int] = {str(k): 0 for k in kok_listesi}
    for kayit in _tum_medya():
        yol = _KAYIT.get(kayit["id"], "")
        for k in kok_listesi:
            ks = str(k)
            if yol.startswith(ks + os.sep):
                sayim[ks] += 1
                break
    out = []
    for k in kok_listesi:
        out.append({
            "id": _kimlik(k),
            "ad": k.name or str(k),
            "yol": str(k),
            "sayi": sayim[str(k)],
            "disk_hatasi": time.time() - _DISK_HATASI.get(str(k), 0.0) < DISK_HATA_PENCERE,
        })
    return {"ok": True, "kokler": out,
            "uzantilar": {"resim": sorted(RESIM_UZANTI), "video": sorted(VIDEO_UZANTI)}}


# ── Kök ekleme (seçici) ─────────────────────────────────────────── #
# Kişisel Yuki'deki `/kok` + `/gozat` uçlarının oss karşılığı. Kişiseldekinden
# DAR kapı: /tmp kabul edilmez, sistem dizinleri ve gizli klasörler reddedilir,
# istek yalnız bu bilgisayardan gelir (telefon/LAN kök ekleyemez, gezemez).
#
# İzinli üst dizinler (`_ekleme_kokleri`):
#   1. kullanıcının ev dizini
#   2. takılı kullanıcı diskleri (`/run/media/$USER`, `/media/$USER`)
#   3. `YUKI_GALERI_IZINLI` ortam değişkeni (`os.pathsep` ile ayrılmış, mutlak yollar)
# Kapı sırası: tip/uzunluk → mutlak mı → resolve() (sembolik bağ çözülür) →
# izinli üst dizinlerden birinin altında mı → sistem dizini mi → izinli köke göre
# göreli yolda gizli parça var mı → galerinin kendi veri dizini mi.

_SISTEM_DIZINLERI = frozenset(Path(x) for x in (
    "/", "/bin", "/boot", "/dev", "/etc", "/lib", "/lib32", "/lib64", "/opt",
    "/proc", "/root", "/run", "/sbin", "/srv", "/sys", "/usr", "/var", "/home",
    "/media", "/mnt", "/tmp",
))
_YOL_AZAMI = 4096


def _yerel_istek(request: Request) -> None:
    from app.services.ag_ayari import loopback_istemci
    if not loopback_istemci(request.client.host if request.client else None):
        raise HTTPException(403, "Kök klasör yalnız bu bilgisayardan eklenir ya da çıkarılır.")


def _sistem_mi(p: Path) -> bool:
    return p in _SISTEM_DIZINLERI


def _ekleme_kokleri() -> list[Path]:
    """Kök eklenebilecek ve seçicide gezilebilecek üst dizinler (var olanlar)."""
    adaylar: list[Path] = [Path.home()]
    adaylar += _takilabilir_kokler()
    for parca in os.environ.get("YUKI_GALERI_IZINLI", "").split(os.pathsep):
        parca = parca.strip()
        if parca and Path(parca).expanduser().is_absolute():
            adaylar.append(Path(parca).expanduser())
    out: list[Path] = []
    for a in adaylar:
        try:
            g = a.resolve()
        except Exception:
            continue
        # İzinli kök olarak sistem dizini (ör. YUKI_GALERI_IZINLI=/) kabul edilmez;
        # ev dizini /root olsa bile ev sayılır (yalnız "/" değilse).
        sistem = _sistem_mi(g) if a is not adaylar[0] else g == Path("/")
        if g.is_dir() and not sistem and g not in out:
            out.append(g)
    return out


def _ekleme_kapisi(ham: str | None) -> Path:
    """Kullanıcının verdiği yolu doğrula; güvenliyse ÇÖZÜLMÜŞ yolu döndür."""
    if not isinstance(ham, str) or not ham.strip() or len(ham) > _YOL_AZAMI or "\x00" in ham:
        raise HTTPException(400, "Geçersiz yol.")
    try:
        ham_yol = Path(ham).expanduser()
        if not ham_yol.is_absolute():
            raise HTTPException(400, "Yol tam (mutlak) olmalı.")
        gercek = ham_yol.resolve()          # sembolik bağ burada çözülür
    except HTTPException:
        raise
    except Exception:
        raise HTTPException(400, "Geçersiz yol.")
    if _sistem_mi(gercek):
        raise HTTPException(403, "Sistem klasörleri galeriye eklenemez.")
    ust = next((k for k in _ekleme_kokleri()
                if gercek == k or str(gercek).startswith(str(k) + os.sep)), None)
    if ust is None:
        raise HTTPException(403, "Yalnız ev klasörün, takılı diskler ya da izin verilen klasörler eklenebilir.")
    if any(parca.startswith(".") for parca in gercek.relative_to(ust).parts):
        raise HTTPException(403, "Gizli klasörler galeriye eklenemez.")
    try:
        veri = VERI.resolve()
    except Exception:
        veri = VERI
    if gercek == veri or str(gercek).startswith(str(veri) + os.sep):
        raise HTTPException(403, "Galerinin kendi veri klasörü eklenemez.")
    return gercek


def _ayar_yaz(d: dict[str, Any]) -> None:
    VERI.mkdir(parents=True, exist_ok=True)
    gecici = AYAR_YOLU.with_suffix(".json.tmp")
    gecici.write_text(json.dumps(d, ensure_ascii=False, indent=2), "utf-8")
    gecici.replace(AYAR_YOLU)      # atomik — yarım yazılmış ayar kalmaz


def _ortam_sabit() -> None:
    if os.environ.get("YUKI_GALERI_KOKLER", "").strip():
        raise HTTPException(409, "Kökler YUKI_GALERI_KOKLER ortam değişkeninden geliyor; "
                                 "arayüzden değiştirilemez.")


class KokEkle(BaseModel):
    yol: str


@router.post("/kok")
async def kok_ekle(body: KokEkle, request: Request):
    """Yeni kök klasör ekle (galerideki "+ KÖK KLASÖR EKLE" seçicisi çağırır)."""
    _yerel_istek(request)
    _ortam_sabit()
    p = _ekleme_kapisi(body.yol)
    if not p.is_dir():
        raise HTTPException(404, "Böyle bir klasör yok.")
    a = _ayar_oku()
    mevcut = set()
    for x in a["kokler"]:
        try:
            mevcut.add(str(Path(x).expanduser().resolve()))
        except Exception:
            continue
    if str(p) in mevcut:
        return {"ok": True, "zaten_var": True, "id": _kimlik(p)}
    a["kokler"] = [*a["kokler"], str(p)]
    _ayar_yaz(a)
    global _TUM_ONBELLEK
    _TUM_ONBELLEK = (0.0, (), [])      # akış yeni kökü hemen görsün
    return {"ok": True, "id": _kimlik(p), "ad": p.name, "yol": str(p)}


@router.delete("/kok/{kid}")
async def kok_sil(kid: str, request: Request):
    """Kökü listeden çıkar. 🔴 Dosyalara DOKUNMAZ — galeri salt okunurdur."""
    _yerel_istek(request)
    _ortam_sabit()
    if not kid or not re.fullmatch(r"[0-9a-f]{16}", kid):
        raise HTTPException(400, "Geçersiz kimlik.")
    a = _ayar_oku()
    kalan, cikan = [], None
    for x in a["kokler"]:
        try:
            gx = Path(x).expanduser().resolve()
        except Exception:
            kalan.append(x)
            continue
        if cikan is None and _kimlik(gx) == kid:
            cikan = gx
            continue
        kalan.append(x)
    if cikan is None:
        raise HTTPException(404, "Bu kök listede yok.")
    a["kokler"] = kalan
    _ayar_yaz(a)
    global _TUM_ONBELLEK
    _TUM_ONBELLEK = (0.0, (), [])
    return {"ok": True, "cikarilan": cikan.name}


@router.get("/gozat")
async def gozat(request: Request, yol: str | None = Query(None)):
    """Klasör seçici — yalnız DİZİNLERİ döner, gizli ve sembolik bağlı olanları listelemez.

    Sınır `_ekleme_kapisi`: ev + takılı diskler + açıkça izinli kökler. `diskler`
    takılı diskleri ve ev dışı izinli kökleri kısayol olarak verir — seçici ev
    dizininden başladığı için onlarsız ulaşılamazlar.
    """
    _yerel_istek(request)
    hedef = _ekleme_kapisi(yol) if yol else Path.home().resolve()
    if not hedef.is_dir():
        raise HTTPException(404, "Klasör bulunamadı.")
    klasorler, medya = [], 0
    try:
        for g in os.scandir(hedef):
            if _atla_mi(Path(g.path)):
                continue
            try:
                if g.is_dir(follow_symlinks=False):
                    klasorler.append({"ad": g.name, "yol": g.path})
                elif g.is_file(follow_symlinks=False) and Path(g.name).suffix.lower() in MEDYA_UZANTI:
                    medya += 1
            except OSError:
                continue
    except PermissionError:
        raise HTTPException(403, "Klasör okunamıyor (izin yok).")
    ust = None
    if hedef != hedef.parent:
        try:
            ust = str(_ekleme_kapisi(str(hedef.parent)))
        except HTTPException:
            ust = None
    ev = Path.home().resolve()
    kisayol = []
    for k in _ekleme_kokleri():
        if k == ev:
            continue
        if k in _takilabilir_kokler():
            try:
                for g in sorted(os.scandir(k), key=lambda x: x.name.lower()):
                    if not g.name.startswith(".") and g.is_dir(follow_symlinks=False):
                        kisayol.append({"ad": g.name, "yol": g.path})
            except OSError:
                continue
        else:
            kisayol.append({"ad": k.name or str(k), "yol": str(k)})
    return {"ok": True, "yol": str(hedef), "ad": hedef.name or str(hedef),
            "ust": ust, "medya": medya, "diskler": kisayol,
            "klasorler": sorted(klasorler, key=lambda x: x["ad"].lower())}


# ── Sıralama ─────────────────────────────────────────────────────── #
# 🔑 Sıralama SUNUCUDA yapılır, istemcide değil: akış sayfalı (`offset`/`limit`)
# ve istemcide sıralamak yalnız elde olan sayfayı dizerdi — "en büyük dosya"
# ilk sayfanın en büyüğü olurdu, yani yanlış cevap.
SIRALAR = {
    "tarih": lambda x: x["tarih"],
    "ad":    lambda x: x["ad"].lower(),
    "boyut": lambda x: x["boyut"],
    "tip":   lambda x: (x["tip"], x["ad"].lower()),
}
SIRA_DESEN = "^(tarih|ad|boyut|tip)$"


def _sirala(kayitlar: list[dict[str, Any]], sirala: str, yon: str) -> list[dict[str, Any]]:
    """Kayıtları yerinde değil KOPYA üzerinde dizer.

    ⚠️ `_tum_medya()` bellekte **paylaşılan** önbellek listesini döndürür;
    `.sort()` ile yerinde dizmek o önbelleği kalıcı olarak bozar ve sonraki
    istek başka bir sırayla gelir (istek sırası sonucu değiştirir — teşhisi
    zor bir kusur sınıfı).
    """
    anahtar = SIRALAR.get(sirala) or SIRALAR["tarih"]
    # Varsayılan: tarih ve boyutta BÜYÜKTEN küçüğe (yeni/büyük önce), ad ve
    # tipte A→Z. "azalan" kullanıcının beklediği yön her ölçüde aynı değildir.
    ters = (yon == "azalan") if yon in ("artan", "azalan") else sirala in ("tarih", "boyut")
    return sorted(kayitlar, key=anahtar, reverse=ters)


@router.get("/liste")
async def liste(id: str = Query(..., description="klasör kimliği"),
                offset: int = Query(0, ge=0),
                limit: int = Query(120, ge=1, le=300),
                sirala: str = Query("tarih", pattern=SIRA_DESEN),
                yon: str = Query("", pattern="^(artan|azalan|)$"),
                tip: str | None = Query(None, pattern="^(resim|video)$"),
                altklasor: int = Query(0, ge=0, le=1)):
    """Bir klasörün içeriği: alt klasörler + medya dosyaları (SAYFALI).

    🔴 Sayfalama sonradan eklendi, ölçüm zorladı: 5.124 dosyalı bir klasörde bu uç
    **25,2 saniye** sürüyordu. Sebep tek tek Pillow başlığı okumaktı — ölçü
    (`en`/`boy`) tüm klasöre uygulanıyordu. Artık yalnız DÖNEN SAYFAYA uygulanır
    ve `_olcu_ekle` onu paralel + önbellekli yapar.
    ⚠️ Alt klasörler yalnız ilk sayfada döner; her sayfada tekrar göndermek
    istemciyi aynı listeyi yeniden çizmeye zorlardı.
    """
    klasor = _guvenli_klasor(_coz(id))
    kokler = _kok_yollari()

    alt, dosyalar = [], []

    def tara(hedef: Path, derinlik: int) -> None:
        try:
            girisler = list(os.scandir(hedef))
        except PermissionError:
            if hedef == klasor:
                raise HTTPException(403, "Klasör okunamıyor (izin yok).")
            return                      # alt klasörde izin yoksa sessizce atla
        except OSError:
            return
        for g in girisler:
            p = Path(g.path)
            if _atla_mi(p):
                continue
            try:
                if g.is_dir(follow_symlinks=False):
                    if hedef == klasor:
                        alt.append({"id": _kimlik(p), "ad": g.name})
                    # 🔴 `altklasor=1` iken ağaç gezilir ama DERİNLİK SINIRLI
                    # (`TARAMA_DERINLIK`) — sınırsız gezinme sembolik bağ
                    # döngüsünde ya da devasa ağaçta ucu kilitler.
                    if altklasor and derinlik < TARAMA_DERINLIK:
                        tara(p, derinlik + 1)
                elif g.is_file(follow_symlinks=False) and p.suffix.lower() in MEDYA_UZANTI:
                    st = g.stat()
                    # 🔑 Ölçü BURADA alınmaz — tüm klasöre Pillow açmak 5.124
                    # dosyada 25 saniyeydi. Yalnız dönen sayfaya, paralel ve
                    # önbellekli eklenir.
                    dosyalar.append({
                        "id": _kimlik(p), "ad": g.name, "tip": _tip(p),
                        "klasor": hedef.name, "klasor_id": _kimlik(hedef),
                        "boyut": st.st_size, "tarih": int(st.st_mtime),
                    })
            except OSError:
                continue

    tara(klasor, 0)

    # Kök mü, değilse üst klasörün kimliği (tek seviye geri için)
    kok_mu = any(klasor == k for k in kokler)
    ust = None
    if not kok_mu and _kok_altinda(klasor.parent, kokler):
        ust = _kimlik(klasor.parent)

    if tip:
        dosyalar = [x for x in dosyalar if x["tip"] == tip]
    dosyalar = _sirala(dosyalar, sirala, yon)
    dilim = dosyalar[offset:offset + limit]
    return {
        "ok": True, "id": id, "ad": klasor.name or str(klasor), "yol": str(klasor),
        "kok_mu": kok_mu, "ust": ust, "offset": offset, "toplam": len(dosyalar),
        "bitti": offset + len(dilim) >= len(dosyalar),
        "klasorler": sorted(alt, key=lambda x: x["ad"].lower()) if offset == 0 else [],
        "dosyalar": _olcu_ekle(dilim),
    }


@router.get("/hepsi")
async def hepsi(offset: int = Query(0, ge=0),
                limit: int = Query(120, ge=1, le=300),
                tip: str | None = Query(None, pattern="^(resim|video)$"),
                sirala: str = Query("tarih", pattern=SIRA_DESEN),
                yon: str = Query("", pattern="^(artan|azalan|)$")):
    """**Tüm** köklerin medyası, yeniden eskiye, sayfalı.

    Hiçbir kök seçili değilken de hepsi görünür. Kök seçmek
    bir filtredir, zorunluluk değil.

    🔴 Sayfalama şart: tek seferde 10.918 kart çizmek tarayıcıyı dondurur.
    İstemci sona yaklaşınca sonraki sayfayı ister (sonsuz akış).
    """
    tum = _tum_medya()
    if tip:
        tum = [x for x in tum if x["tip"] == tip]
    # ⚠️ `_tum_medya()` zaten tarihe göre yeniden eskiye gelir; başka bir ölçü
    # istenince YENİDEN dizilir (kopya üzerinde — paylaşılan önbellek bozulmaz).
    if sirala != "tarih" or yon == "artan":
        tum = _sirala(tum, sirala, yon)
    dilim = tum[offset:offset + limit]
    return {"ok": True, "toplam": len(tum), "offset": offset,
            "dosyalar": _olcu_ekle(dilim),
            "bitti": offset + len(dilim) >= len(tum)}


@router.get("/bilgi/{kid}")
async def bilgi(kid: str):
    """Tek dosyanın künyesi + bulunduğu klasörün kimliği.

    Yuki `show_media` ile galeriyi `?ac=<id>` diye açtığında arayüz bununla
    dosyanın hangi klasörde olduğunu öğrenir — ızgarayı doğru klasörde kurar,
    ileri/geri gezinme çalışır (yoksa tek dosyalık çıkmaz sokak olurdu).
    """
    p = _guvenli_dosya(_coz(kid))
    st = p.stat()
    en, boy = _olcu(p)
    return {"ok": True, "id": kid, "ad": p.name, "tip": _tip(p),
            "klasor": p.parent.name, "klasor_id": _kimlik(p.parent),
            "boyut": st.st_size, "tarih": int(st.st_mtime), "en": en, "boy": boy}


@router.get("/kucuk/{kid}")
async def kucuk(kid: str, k: int = Query(KUCUK_KENAR, description="uzun kenar (200/400/800)")):
    """Küçük resim (WebP, önbellekli). Video için ffmpeg ilk kareyi çıkarır;
    çıkaramazsa 500 → istemci VİDEO rozetine düşer."""
    p = _guvenli_dosya(_coz(kid))
    # Beyaz liste: istemci rastgele kenar isteyip önbelleği şişiremesin.
    kenar = k if k in KUCUK_KADEMELER else KUCUK_KENAR
    hedef = _kucuk_uret(p, kenar)
    if hedef is None:
        # Üretilemedi (bozuk dosya / Pillow yok) → tam dosyaya düşme, çünkü
        # ızgarada 30 tam boyut resim indirmek tam da kaçındığımız şey.
        raise HTTPException(500, "Küçük resim üretilemedi.")
    return FileResponse(hedef, media_type="image/webp",
                        headers={"Cache-Control": "private, max-age=86400"})


@router.get("/dosya/{kid}")
async def dosya(kid: str, request: Request, indir: int = Query(0, ge=0, le=1)):
    """Dosyanın kendisi. Resimde tam gövde (frontend blob'a çeker),
    videoda `Range` destekli akıtma. `?indir=1` → tarayıcı kaydetsin."""
    p = _guvenli_dosya(_coz(kid))
    return _dosya_yanit(p, request.headers.get("range"), indir=bool(indir))


# ── Bilet — videonun auth sorunu ─────────────────────────────────── #
# 🔴 `<video src>` `Authorization` başlığı gönderemez ve video BLOB olamaz
# (K4: bellek şişer, ileri sarma ölür). Geriye iki yol kalıyordu:
#   ① URL'e `?token=<AUTH_TOKEN>` koymak — middleware bunu kabul ediyor ama
#      ana token erişim loguna ve panel geçmişine sızar (eski finance.html hatası);
#   ② kısa ömürlü, tek dosyaya bağlı bir bilet — middleware'in kendi yorumunda
#      "kalıcı çözüm" diye işaret ettiği şey.
# ②'yi seçtik. Bilet `authFetch` ile alınır, yalnız o dosyayı açar, erişildikçe
# tazelenir (uzun video ortasında ölmesin) ama hiç dokunulmazsa 5 dakikada düşer.
BILET_OMUR = 300.0
_BILETLER: dict[str, tuple[str, float]] = {}      # bilet → (yol, son_gecerlilik)


def _bilet_temizle() -> None:
    simdi = time.time()
    for b in [k for k, (_, t) in _BILETLER.items() if t < simdi]:
        _BILETLER.pop(b, None)


@router.get("/bilet/{kid}")
async def bilet(kid: str):
    """Kısa ömürlü erişim bileti (auth'lu uç — bileti sadece kimliği
    doğrulanmış istemci alabilir).

    İki kullanıcısı var: ① video oynatma (`<video src>` başlık gönderemez)
    ② **indirme** — `<a href>` de başlık gönderemez, resim/video farketmez."""
    import secrets as _secrets
    p = _guvenli_dosya(_coz(kid))
    _bilet_temizle()
    b = _secrets.token_urlsafe(24)
    _BILETLER[b] = (str(p), time.time() + BILET_OMUR)
    return {"ok": True, "bilet": b, "omur": int(BILET_OMUR),
            "url": f"/api/galeri/akis/{b}"}


@router.get("/akis/{bilet_kodu}")
async def akis(bilet_kodu: str, request: Request, indir: int = Query(0, ge=0, le=1)):
    """Biletli akış — `Range` destekli. Auth middleware'inden muaftır
    (bkz. main.py `_SKIP_PREFIXES`), yetkiyi biletin kendisi taşır.

    `?indir=1` yalnız `Content-Disposition`'ı değiştirir — yetki kapısı aynı
    kapıdır, indirme ayrı bir yol AÇMAZ (bilet neyi oynatabiliyorsa onu
    indirebilir; beş katman aşağıda yine koşar)."""
    _bilet_temizle()
    kayit = _BILETLER.get(bilet_kodu)
    if not kayit:
        raise HTTPException(403, "Bilet geçersiz ya da süresi dolmuş.")
    yol, _ = kayit
    _BILETLER[bilet_kodu] = (yol, time.time() + BILET_OMUR)   # kayan süre
    # 🔑 Beş katman burada da koşar: bilet zamanla eskiyebilir, ayar değişip
    # klasör kökten çıkmış olabilir.
    p = _guvenli_dosya(Path(yol))
    return _dosya_yanit(p, request.headers.get("range"), indir=bool(indir))


@router.get("/bul")
async def bul(ara: str = Query("", description="ad parçası"),
              limit: int = Query(30, ge=1, le=200),
              tip: str | None = Query(None, pattern="^(resim|video)$")):
    """Ada göre medya ara — Yuki'nin `list_media`/`show_media` araçları bunu kullanır."""
    return {"ok": True, "sonuc": ara_medya(ara, limit, tip)}


# ══════════════════════════════════════════════════════════════════ #
# BİLGİ & KEŞİF — EXIF · harita · kopya · istatistik (2026-09-20)
#
# GalleryWeb'den taşınan yetenekler. **Hiçbiri diske yazmaz** — K6 (salt
# okunur) bozulmadı; üretilen tek şey bellekteki okuma önbellekleri.
#
# 🔴 İKİSİ KADEMELİ (`/harita`, `/kopyalar`): GalleryWeb'de bu uçlar tüm
#    kütüphaneyi tek istekte tarar ve orada doğrudur — klasör başına birkaç
#    yüz dosya var. Burada `_tum_medya()` **11.044 kayıt** döndürüyor; her
#    birine Pillow açmak `/liste` ucunun 25 saniyelik kusurunun (09-12,
#    § Performans turu) birebir tekrarı olurdu. İstemci `offset`/`limit` ile
#    dilim dilim ilerler, ilerlemeyi gösterir; sonuçlar süreç ömrü boyunca
#    önbellekte birikir → ikinci açılış anında gelir (ölçüldü: 38 sn → 0,1 sn).
# ══════════════════════════════════════════════════════════════════ #

# Tarama önbellekleri — anahtar `id:mtime` (dosya değişirse kendiliğinden
# geçersiz olur; `_OLCU_ONBELLEK` deseninin aynısı).
_GPS_ONBELLEK: dict[str, tuple[float, float] | None] = {}
_HASH_ONBELLEK: dict[str, int | None] = {}
_ONBELLEK_TAVAN = 40000


def _exif_ham(p: Path) -> dict[str, Any]:
    """Resmin EXIF'i — **Pillow ile**, ek bağımlılık yok.

    GalleryWeb `pyexiv2` kullanıyor (daha zengin okur) ama o paket bu venv'de
    kurulu değil ve galeri için EXIF *ikincil* bir bilgi — yeni bir C
    bağımlılığı (exiv2) getirmeye değmez. Pillow zaten küçük resim üretiminde
    kullanılıyor ve kamera/tarih/pozlama alanlarını okuyor.
    """
    from PIL import Image, ExifTags

    out: dict[str, Any] = {}
    with Image.open(p) as im:
        ham = im.getexif()
        if not ham:
            return out
        for etiket, deger in ham.items():
            ad = ExifTags.TAGS.get(etiket)
            if ad:
                out[ad] = _exif_degeri(deger)
        # 🔴 IFD'ler AYRI sözlüklerde durur: pozlama/ISO/diyafram `Exif`
        # IFD'sindedir, üst seviyede YOKTUR. Yalnız `ham.items()` okumak
        # "kamera var ama diyafram yok" gibi yarım bir künye üretirdi.
        for ifd, tablo in ((ExifTags.IFD.Exif, ExifTags.TAGS),
                           (ExifTags.IFD.GPSInfo, ExifTags.GPSTAGS)):
            try:
                alt = ham.get_ifd(ifd)
            except Exception:
                continue
            for etiket, deger in (alt or {}).items():
                ad = tablo.get(etiket)
                if ad:
                    out[ad] = _exif_degeri(deger)
    return out


def _exif_degeri(v: Any) -> Any:
    """EXIF değerini JSON'a girebilir hâle getir.

    ⚠️ Ham EXIF `IFDRational`, `bytes` ve iç içe demet taşır; doğrudan yanıta
    konursa uç **500** döner (serileştirilemez). MakerNote gibi alanlar
    kilobaytlarca ikili veri olabilir — kırpılır.
    """
    if isinstance(v, bytes):
        return v[:64].hex() if len(v) > 24 else v.decode("utf-8", "replace").strip("\x00")
    if isinstance(v, (tuple, list)):
        return [_exif_degeri(x) for x in v[:16]]
    if isinstance(v, (int, float, str)):
        return v.strip() if isinstance(v, str) else v
    try:                                   # IFDRational → float
        return round(float(v), 6)
    except Exception:
        return str(v)[:120]


def _gps_coz(exif: dict[str, Any]) -> tuple[float, float] | None:
    """EXIF GPS alanlarını ondalık dereceye çevir. Yoksa/geçersizse None."""
    try:
        lat = exif.get("GPSLatitude")
        lon = exif.get("GPSLongitude")
        if not lat or not lon or len(lat) < 3 or len(lon) < 3:
            return None
        d = float(lat[0]) + float(lat[1]) / 60 + float(lat[2]) / 3600
        g = float(lon[0]) + float(lon[1]) / 60 + float(lon[2]) / 3600
        if str(exif.get("GPSLatitudeRef", "N")).upper().startswith("S"):
            d = -d
        if str(exif.get("GPSLongitudeRef", "E")).upper().startswith("W"):
            g = -g
        # 🔴 (0,0) REDDEDİLİR: bazı makineler GPS alanlarını sıfırla doldurur.
        # Kabul edilseydi haritada Gine Körfezi'nde sahte bir yığın belirirdi.
        if abs(d) < 1e-7 and abs(g) < 1e-7:
            return None
        if not (-90 <= d <= 90 and -180 <= g <= 180):
            return None
        return (round(d, 6), round(g, 6))
    except Exception:
        return None


def _video_kunye(p: Path) -> dict[str, Any]:
    """Videonun künyesi — ffprobe tek çağrı. ffprobe yoksa boş döner.

    🔴 `-select_streams v:0` ŞART. Onsuz ffprobe HER akışı basar ve düz
    `anahtar=değer` çıktısında ses akışı video akışının üstüne yazar: ölçüldü
    (2026-09-20), bir mp4 için `codec_name=aac` ve `r_frame_rate=0/0` döndü —
    panel videonun kodeğini **ses kodeği** diye gösteriyordu. Yanlış değer boş
    değerden kötüdür: boşta kullanıcı bilmediğini bilir.
    """
    import subprocess
    try:
        r = subprocess.run(
            ["ffprobe", "-v", "error", "-select_streams", "v:0", "-show_entries",
             "format=duration,bit_rate,format_long_name:stream=codec_name,width,height,r_frame_rate",
             "-of", "default=noprint_wrappers=1", str(p)],
            capture_output=True, text=True, timeout=8)
    except Exception:
        return {}
    out: dict[str, Any] = {}
    for satir in r.stdout.splitlines():
        if "=" not in satir:
            continue
        k, v = satir.split("=", 1)
        if v and v != "N/A":
            out[k] = v
    return out


@router.get("/exif/{kid}")
async def exif(kid: str):
    """Dosyanın künyesi + EXIF. Salt okuma — dosyaya dokunulmaz."""
    p = _guvenli_dosya(_coz(kid))
    st = p.stat()
    en, boy = _olcu(p)
    yanit: dict[str, Any] = {
        "ok": True, "id": kid, "ad": p.name, "tip": _tip(p),
        "klasor": p.parent.name, "boyut": st.st_size,
        "degisti": int(st.st_mtime), "en": en, "boy": boy,
        "exif": {}, "gps": None, "video": {},
    }
    if _tip(p) == "video":
        yanit["video"] = _video_kunye(p)
        return yanit
    try:
        ham = _exif_ham(p)
    except Exception as e:                       # EXIF'siz dosya OLAĞANDIR
        logger.debug("EXIF okunamadı (%s): %s", p, e)
        return yanit
    konum = _gps_coz(ham)
    # 🔴 GPS alanları künyeden ÇIKARILIR. Ham hâlleri derece/dakika demetidir
    # (okunmaz) ve asıl sakıncası: panelde ham koordinat göstermek onu ekran
    # görüntüsüne, oradan dışarı taşır. Konum yalnız `gps` alanında durur ve
    # yalnız kullanıcı haritayı açarsa kullanılır.
    yanit["exif"] = {k: v for k, v in ham.items() if not k.startswith("GPS")}
    yanit["gps"] = {"lat": konum[0], "lon": konum[1]} if konum else None
    return yanit


def _gps_oku(kayit: dict[str, Any]) -> dict[str, Any] | None:
    """Tek kaydın GPS'i (önbellekli). Yoksa None."""
    anahtar = f"{kayit['id']}:{kayit.get('tarih', 0)}"
    if anahtar not in _GPS_ONBELLEK:
        yol = _KAYIT.get(kayit["id"])
        konum = None
        if yol:
            try:
                konum = _gps_coz(_exif_ham(Path(yol)))
            except Exception:
                konum = None
        _GPS_ONBELLEK[anahtar] = konum
    konum = _GPS_ONBELLEK[anahtar]
    if not konum:
        return None
    return {"id": kayit["id"], "ad": kayit["ad"], "tip": kayit["tip"],
            "lat": konum[0], "lon": konum[1], "tarih": kayit.get("tarih", 0)}


@router.get("/harita")
async def harita(offset: int = Query(0, ge=0),
                 limit: int = Query(400, ge=1, le=1000)):
    """GPS taşıyan fotoğrafları döndür — **kademeli**.

    İstemci `bitti` gelene dek offset'i ilerletir. Dönen `taranan`/`toplam`
    ilerleme çubuğunu besler: tek istek dakikalarca sürerdi ve arayüz o süre
    boyunca donuk görünürdü.

    ⚠️ Yalnız RESİMLER taranır — video EXIF'i Pillow'la okunamaz ve on bin
    dosya için ffprobe çağırmak taramayı saatlere çıkarırdı.
    """
    from concurrent.futures import ThreadPoolExecutor

    if len(_GPS_ONBELLEK) > _ONBELLEK_TAVAN:
        _GPS_ONBELLEK.clear()

    resimler = [x for x in _tum_medya() if x["tip"] == "resim"]
    dilim = resimler[offset:offset + limit]
    with ThreadPoolExecutor(max_workers=8) as havuz:     # I/O ağırlıklı
        bulunan = [x for x in havuz.map(_gps_oku, dilim) if x]
    return {"ok": True, "toplam": len(resimler),
            "taranan": min(offset + len(dilim), len(resimler)),
            "noktalar": bulunan,
            "bitti": offset + len(dilim) >= len(resimler)}


# Yanlış pozitif kapıları — ikisi de ÖLÇÜMLE kondu (2026-09-20, ekran
# görüntüsünde görülen "grup #2" vakası). Ayrıntı `_ozet`in altında.
_ORAN_TOLERANS = 0.08      # en/boy farkı bundan büyükse kopya sayılmaz
_BIT_ALT, _BIT_UST = 14, 50   # hash bu aralığın dışındaysa ayırt edici değil


def _dhash(p: Path) -> int | None:
    """64 bitlik algısal özet (difference hash).

    🔴 `imagehash` KURULMADI — bu venv'de yok ve tek bir uç için yeni bir
    bağımlılık (+ sürüm riski) getirmeye değmez. dHash on satırdır ve
    imagehash'in kendi `dhash`'iyle aynı algoritmadır: 9×8'e küçült, gri yap,
    komşu piksel karşılaştır. Yeniden boyutlandırma/sıkıştırma/hafif renk
    değişimine dayanıklı; kırpma ve dönmeye değil.
    Ölçüldü (2026-09-20): aynı resmin yarı boyu → hamming 4 · farklı resim → 31.
    """
    ozet = _ozet(p)
    return ozet[0] if ozet else None


def _ozet(p: Path) -> tuple[int, float] | None:
    """(dHash, en/boy oranı). Oran yanlış pozitifleri elemek için taşınır."""
    try:
        from PIL import Image
        import numpy as np
        with Image.open(p) as im:
            en, boy = im.size
            k = im.convert("L").resize((9, 8), Image.Resampling.LANCZOS)
            a = np.asarray(k, dtype=np.int16)
        if not en or not boy:
            return None
        bitler = (a[:, 1:] > a[:, :-1]).flatten()
        # 64 biti tek adımda paketle — Python döngüsü resim başına 64 tur dönerdi.
        h = int.from_bytes(np.packbits(bitler).tobytes(), "big")
        return (h, en / boy)
    except Exception:
        return None


def _hash_oku(kayit: dict[str, Any]) -> None:
    anahtar = f"{kayit['id']}:{kayit.get('tarih', 0)}"
    if anahtar in _HASH_ONBELLEK:
        return
    yol = _KAYIT.get(kayit["id"])
    _HASH_ONBELLEK[anahtar] = _ozet(Path(yol)) if yol else None


@router.get("/kopyalar")
async def kopyalar(offset: int = Query(0, ge=0),
                   limit: int = Query(400, ge=1, le=1000),
                   esik: int = Query(6, ge=0, le=16)):
    """Birbirinin kopyası/benzeri resimleri grupla — **kademeli**.

    Tarama `offset`/`limit` ile ilerler; gruplar **yalnız tarama bittiğinde**
    hesaplanır. Eksik özet kümesiyle gruplamak "3 kopya" deyip sonraki dilimde
    "7 kopya" demek olurdu — kullanıcı ilk sayıya göre karar verir.

    🔑 Galeri salt okunurdur: bu uç kopyaları **bulur**, silmez. Ne yapılacağı
    kullanıcıya kalır.
    """
    from concurrent.futures import ThreadPoolExecutor

    if len(_HASH_ONBELLEK) > _ONBELLEK_TAVAN:
        _HASH_ONBELLEK.clear()

    resimler = [x for x in _tum_medya() if x["tip"] == "resim"]
    dilim = resimler[offset:offset + limit]
    with ThreadPoolExecutor(max_workers=8) as havuz:
        list(havuz.map(_hash_oku, dilim))

    taranan = min(offset + len(dilim), len(resimler))
    bitti = offset + len(dilim) >= len(resimler)
    yanit: dict[str, Any] = {
        "ok": True, "toplam": len(resimler), "taranan": taranan,
        "bitti": bitti, "gruplar": [], "kopya_sayisi": 0, "kazanc": 0,
        "kesildi": False,
    }
    if not bitti:
        return yanit

    # ── Gruplama ────────────────────────────────────────────────────
    # 🔴 NUMPY ŞART, saf Python DEĞİL. Eşleştirme O(n²) ve n burada 10.729;
    # GalleryWeb'in iç içe `for` döngüsü (orada klasör başına birkaç yüz dosya
    # olduğu için doğru) burada **57 milyon** `bin(x^y).count('1')` çağrısı
    # demekti. `np.bitwise_count` aynı işi satır satır değil dizi dizi yapar.
    import numpy as np

    # 🔴 İKİ YANLIŞ POZİTİF KAPISI — ikisi de gerçek bir vakadan doğdu.
    # 2026-09-20 ekran denetiminde "grup #2" şunları BİR ARADA gösteriyordu:
    # dört koyu ekran görüntüsü + bir barkod fotoğrafı + bir el yazısı notu.
    # Ölçüldü: altısının da hash'i `…909090…` deseninde ve popcount **13-18**
    # (normal bir resimde ~32). Sebep dHash'in yapısal zayıflığı: düşük
    # kontrastlı görüntüde 9×8 küçültmeden sonra komşu farkları hep aynı yöne
    # düşer, dolayısıyla BİRBİRİNE BENZEMEYEN düz resimler kaçınılmaz olarak
    # yakın hamming mesafesi verir.
    #   ① oran kapısı  — aynı görüntünün kopyası aynı en/boy oranını taşır;
    #      o gruptaki oran farkları %10-94'tü (gerçek kopyalarda %0).
    #   ② bit kapısı   — aşırı dengesiz hash "ayırt edici değil" demektir;
    #      böyle bir resmi gruplamak, ölçemediğin şey hakkında hüküm vermektir.
    # Yanlış pozitif burada yanlış negatiften pahalıdır: kullanıcı bu listeye
    # bakıp dosya SİLMEYE karar verir.
    ozetler: list[int] = []
    oranlar: list[float] = []
    kayitlar: list[dict[str, Any]] = []
    elenen_duz = 0
    for x in resimler:
        o = _HASH_ONBELLEK.get(f"{x['id']}:{x.get('tarih', 0)}")
        if not o:
            continue
        h, oran = o
        if not (_BIT_ALT <= bin(h).count("1") <= _BIT_UST):
            elenen_duz += 1                      # ② ayırt edici olmayan görüntü
            continue
        ozetler.append(h)
        oranlar.append(oran)
        kayitlar.append(x)

    gruplar: list[list[dict[str, Any]]] = []
    if kayitlar:
        dizi = np.array(ozetler, dtype=np.uint64)
        oran_d = np.array(oranlar, dtype=np.float64)
        kalan = np.ones(len(dizi), dtype=bool)
        for i in range(len(dizi)):
            if not kalan[i]:
                continue
            uzaklik = np.bitwise_count(np.bitwise_xor(dizi, dizi[i]))
            oran_fark = np.abs(oran_d - oran_d[i]) / np.maximum(oran_d, oran_d[i])
            esles = (uzaklik <= esik) & (oran_fark <= _ORAN_TOLERANS) & kalan   # ①
            esles[i] = False
            idx = np.flatnonzero(esles)
            if idx.size:
                kalan[idx] = False
                kalan[i] = False
                # `oran` yanıta girer: kapının GERÇEKTEN uygulandığı ancak bu
                # alanla dışarıdan ölçülebiliyor. Boyut farkına bakmak dolaylı
                # ve yanıltıcıydı — aynı resmin jpg/png hâli arasında ×52 fark
                # ölçüldü ve o **meşru** bir kopyadır.
                gruplar.append([
                    {**kayitlar[k], "oran": round(float(oran_d[k]), 4)}
                    for k in [i] + idx.tolist()
                ])
            if len(gruplar) >= 200:      # arayüz sınırı; 200 grup zaten okunmaz
                break
    yanit["elenen_duz"] = elenen_duz

    # En çok yer kaplayan grup üstte — kullanıcının sorusu "hangisi diski yiyor".
    gruplar.sort(key=lambda g: -sum(x["boyut"] for x in g[1:]))
    yanit["gruplar"] = gruplar
    yanit["kopya_sayisi"] = sum(len(g) - 1 for g in gruplar)
    yanit["kazanc"] = sum(sum(x["boyut"] for x in g[1:]) for g in gruplar)
    # ⚠️ Sınıra dayandıysak BUNU SÖYLE. Sessiz kırpma "toplam 200 grup var"
    # diye okunur ve kullanıcı eksik bir tabloya göre karar verir.
    yanit["kesildi"] = len(gruplar) >= 200
    return yanit


@router.get("/istatistik")
async def istatistik():
    """Kütüphane özeti. `_tum_medya()` önbelleğinden okur — ek tarama yok."""
    import datetime

    tum = _tum_medya()
    resim = [x for x in tum if x["tip"] == "resim"]
    video = [x for x in tum if x["tip"] == "video"]

    # Aylık dağılım (son 24 ay) — "ne zaman ne biriktirdim" sorusunun cevabı.
    aylik: dict[str, int] = {}
    for x in tum:
        try:
            ay = datetime.datetime.fromtimestamp(x["tarih"]).strftime("%Y-%m")
        except Exception:
            continue
        aylik[ay] = aylik.get(ay, 0) + 1
    aylar = sorted(aylik.items())[-24:]

    # Kök başına dağılım — hangi klasör ne kadar yer kaplıyor.
    kok_ozet = []
    for k in _kok_yollari():
        onek = str(k) + os.sep
        icinde = [x for x in tum if (_KAYIT.get(x["id"]) or "").startswith(onek)]
        kok_ozet.append({"ad": k.name, "sayi": len(icinde),
                         "bayt": sum(x["boyut"] for x in icinde)})
    kok_ozet.sort(key=lambda x: -x["bayt"])

    uzanti: dict[str, int] = {}
    for x in tum:
        uz = Path(x["ad"]).suffix.lower() or "?"
        uzanti[uz] = uzanti.get(uz, 0) + 1

    tarihler = [x["tarih"] for x in tum if x["tarih"]]
    return {
        "ok": True,
        "toplam": len(tum), "resim": len(resim), "video": len(video),
        "bayt": sum(x["boyut"] for x in tum),
        "en_eski": min(tarihler) if tarihler else None,
        "en_yeni": max(tarihler) if tarihler else None,
        "aylik": [{"ay": a, "sayi": n} for a, n in aylar],
        "kokler": kok_ozet,
        "uzantilar": sorted([{"uz": u, "sayi": n} for u, n in uzanti.items()],
                            key=lambda x: -x["sayi"])[:12],
        "en_buyuk": sorted(tum, key=lambda x: -x["boyut"])[:10],
    }


# ══════════════════════════════════════════════════════════════════ #
# ARŞİV — klasör rayı + zaman omurgası (2026-09-28, Taslak B)
#
# İki OKUMA ucu. İkisi de `_tum_medya()` önbelleğinden türer — yeni tarama,
# dosya açma, EXIF, Pillow YOK. `/kokler` ve `/istatistik` ile aynı kaynak:
# aynı soruya iki ayrı sayım üretmek (rayda 7.099, akışta başka sayı) bu
# depoda yaşanmış kusur sınıfıdır.
#
# Güvenlik: istemci ham yol GÖNDERMEZ ve ham yol ALMAZ — yalnız sha1 kimliği
# ve kökten göreli ad. Klasör süzgeci `/liste` ile aynı kapıdan geçer
# (`_guvenli_klasor(_coz(id))` → katman 1-2-5 + dizin mi). Dosya düzeyindeki
# 3-4. katmanlar (uzantı, imza) dosya SUNULURKEN koşar; burada dosya sunulmaz,
# yalnız sayılır — `/hepsi` ile aynı sözleşme.
# ══════════════════════════════════════════════════════════════════ #

def _ay_anahtari(ts: int) -> str | None:
    """Zaman damgası → 'YYYY-MM' (yerel saat — istemcinin ay başlığıyla aynı)."""
    import datetime
    try:
        return datetime.datetime.fromtimestamp(ts).strftime("%Y-%m")
    except (OverflowError, OSError, ValueError):
        return None


@router.get("/klasorler")
async def klasorler():
    """Klasör rayı: medyalı her klasör, doğrudan + alt ağaç sayısıyla.

    Yanıt ham yol TAŞIMAZ. Ağaç `ust` kimliğiyle kurulur; `goreli` kökten
    göreli addır (ör. `tatil/2026 yaz`) — yalnız ipucu metni için.
    """
    tum = _tum_medya()
    kokler = _kok_yollari()
    kok_str = [str(k) for k in kokler]

    dogrudan: dict[str, int] = {}              # klasör yolu → doğrudan medya
    for x in tum:
        yol = _KAYIT.get(x["klasor_id"])
        if yol:
            dogrudan[yol] = dogrudan.get(yol, 0) + 1

    toplam: dict[str, int] = {}                # klasör yolu → alt ağaç dahil
    kok_of: dict[str, str] = {}
    for yol, n in dogrudan.items():
        kok = next((k for k in kok_str if yol == k or yol.startswith(k + os.sep)), None)
        if kok is None:                        # kökten çıkarılmış eski kayıt
            continue
        p = Path(yol)
        while True:
            s = str(p)
            toplam[s] = toplam.get(s, 0) + n
            kok_of[s] = kok
            if s == kok or p.parent == p:
                break
            p = p.parent

    out_kok, out_kl = [], []
    for k in kokler:
        ks = str(k)
        out_kok.append({"id": _kimlik(k), "ad": k.name or ks,
                        "sayi": toplam.get(ks, 0), "dogrudan": dogrudan.get(ks, 0)})
    for s, n in toplam.items():
        kok = kok_of[s]
        if s == kok:
            continue
        p = Path(s)
        goreli = os.path.relpath(s, kok)
        out_kl.append({
            "id": _kimlik(p), "ad": p.name, "ust": _kimlik(p.parent),
            "kok": _kimlik(Path(kok)), "goreli": goreli,
            "derinlik": goreli.count(os.sep) + 1,
            "sayi": dogrudan.get(s, 0), "toplam": n,
        })
    out_kl.sort(key=lambda x: (x["derinlik"], -x["toplam"], x["ad"].lower()))
    return {"ok": True, "toplam": len(tum), "kokler": out_kok, "klasorler": out_kl}


@router.get("/aylik")
async def aylik(id: str | None = Query(None, description="klasör kimliği (yoksa HEPSİ)"),
                altklasor: int = Query(0, ge=0, le=1),
                tip: str | None = Query(None, pattern="^(resim|video)$"),
                yon: str = Query("", pattern="^(artan|azalan|)$")):
    """Zaman omurgası: süzgece göre ay ay sayım + her ayın akıştaki OFSETİ.

    🔑 Ofset sunucuda hesaplanır: tarih sırasında o aydan DAHA ÖNCE gelen
    kayıtların sayısı. İstemci aya atlarken `/hepsi` (ya da `/liste?id=`)
    ucunu bu ofsetle çağırır — liste o aydan yeniden kurulur. Sıra `/hepsi`
    ve `/liste`'nin tarih sırasıyla birebir aynıdır (ay sınırında eşit zaman
    damgası aynı aya düşer, yani ofset sıra bağından etkilenmez).

    ⚠️ Kaynak `_tum_medya()` önbelleği (30 sn). O pencerede diske yeni dosya
    düşerse ofset birkaç kayıt kayabilir; istemci bunu başlık ayından okur.
    ⚠️ Klasör kipinde derinlik kökten sayılır (`TARAMA_DERINLIK`); `/liste`
    klasörden sayar. Kökten 7+ seviye derin ağaçta ikisi ayrışabilir.
    """
    tum = _tum_medya()
    if id:
        klasor = _guvenli_klasor(_coz(id))
        if altklasor:
            onek = str(klasor) + os.sep
            tum = [x for x in tum if (_KAYIT.get(x["id"]) or "").startswith(onek)]
        else:
            kid = _kimlik(klasor)
            tum = [x for x in tum if x["klasor_id"] == kid]
    if tip:
        tum = [x for x in tum if x["tip"] == tip]

    artan = yon == "artan"
    sayim: dict[str, int] = {}
    for x in tum:
        ay = _ay_anahtari(x["tarih"])
        if ay:
            sayim[ay] = sayim.get(ay, 0) + 1
    aylar, ofset = [], 0
    for ay in sorted(sayim, reverse=not artan):
        aylar.append({"ay": ay, "sayi": sayim[ay], "ofset": ofset})
        ofset += sayim[ay]
    return {"ok": True, "toplam": len(tum), "yon": "artan" if artan else "azalan",
            "aylar": aylar}


# ── Araçların çağırdığı iç fonksiyon ─────────────────────────────── #

_TUM_ONBELLEK: tuple[float, tuple[str, ...], list[dict[str, Any]]] = (0.0, (), [])
_TUM_TTL = 30.0


def _tum_medya() -> list[dict[str, Any]]:
    """Tüm köklerdeki medya, yeniden eskiye. 30 sn önbellekli.

    🔑 Ölçü buraya girmez (`en`/`boy`): binlerce dosyanın hepsine Pillow açmak
    saniyeler sürerdi. Ölçü yalnız **döndürülen sayfaya** eklenir.

    🔴 Önbellek anahtarı KÖK LİSTESİNİ de içerir. Yalnız süreye baksaydı —
    ölçüldü 2026-09-12 — yeni kök eklendikten sonra 30 saniye boyunca eski
    toplam dönerdi: kullanıcı klasörü ekler, hiçbir şey değişmez, "eklenmedi mi?"
    diye ikinci kez eklemeye çalışır.
    """
    global _TUM_ONBELLEK
    simdi = time.time()
    kokler = _kok_yollari()
    imza = tuple(str(k) for k in kokler)
    if (simdi - _TUM_ONBELLEK[0] < _TUM_TTL and _TUM_ONBELLEK[1] == imza
            and _TUM_ONBELLEK[2]):
        return _TUM_ONBELLEK[2]

    bulunan: list[dict[str, Any]] = []
    for kok in kokler:
        yigin: list[tuple[Path, int]] = [(kok, 0)]
        while yigin:
            klasor, d = yigin.pop()
            try:
                girisler = list(os.scandir(klasor))
            except OSError:
                continue
            for g in girisler:
                p = Path(g.path)
                if _atla_mi(p):
                    continue
                try:
                    if g.is_dir(follow_symlinks=False):
                        if d < TARAMA_DERINLIK:
                            yigin.append((p, d + 1))
                        continue
                    if p.suffix.lower() not in MEDYA_UZANTI:
                        continue
                    st = g.stat()
                    bulunan.append({
                        "id": _kimlik(p), "ad": g.name, "tip": _tip(p),
                        "klasor": klasor.name, "klasor_id": _kimlik(klasor),
                        "boyut": st.st_size, "tarih": int(st.st_mtime),
                    })
                except OSError:
                    continue
    bulunan.sort(key=lambda x: -x["tarih"])
    _TUM_ONBELLEK = (simdi, imza, bulunan)
    return bulunan


_OLCU_ONBELLEK: dict[str, tuple[int | None, int | None]] = {}


def _olcu_ekle(kayitlar: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Sayfalanmış kayıtlara en/boy ekle (nehir düzeni zıplamasın).

    ⚠️ Ölçüldü: 120 dosyaya seri Pillow başlığı **0,55 sn** — sonsuz akışta
    hissedilir. İki çare birlikte: (a) bellekte önbellek, anahtar `id+mtime`
    (dosya değişirse ölçü bayatlamaz), (b) I/O ağırlıklı olduğu için havuzla
    paralel oku.
    """
    from concurrent.futures import ThreadPoolExecutor

    def tek(k: dict[str, Any]) -> dict[str, Any]:
        anahtar = f"{k['id']}:{k.get('tarih', 0)}"
        if anahtar not in _OLCU_ONBELLEK:
            yol = _KAYIT.get(k["id"])
            _OLCU_ONBELLEK[anahtar] = _olcu(Path(yol)) if yol else (None, None)
        en, boy = _OLCU_ONBELLEK[anahtar]
        return {**k, "en": en, "boy": boy}

    if len(_OLCU_ONBELLEK) > 40000:      # sınırsız büyümesin
        _OLCU_ONBELLEK.clear()
    with ThreadPoolExecutor(max_workers=8) as havuz:
        return list(havuz.map(tek, kayitlar))


def ara_medya(ara: str = "", limit: int = 30, tip: str | None = None) -> list[dict[str, Any]]:
    """Köklerde ada göre arama. Boş sorgu = en yeni dosyalar.

    Araçlar HTTP üzerinden değil doğrudan buradan okur — kendi sunucusuna
    HTTP isteği atan araç, auth'u ikinci kez çözmek zorunda kalır.
    """
    q = (ara or "").strip().lower()
    sonuc = [
        x for x in _tum_medya()
        if (not tip or x["tip"] == tip) and (not q or q in x["ad"].lower())
    ]
    return _olcu_ekle(sonuc[:limit])


def coz_hedef(yol_veya_ad: str) -> dict[str, Any] | None:
    """`show_media` için: tam yol ya da dosya adı → kayıt. Bulamazsa None."""
    s = (yol_veya_ad or "").strip()
    if not s:
        return None

    # 1) Tam yol verildiyse doğrudan çöz (güvenlik kapılarından geçerek)
    aday = Path(s).expanduser()
    if aday.is_absolute() or s.startswith("~"):
        try:
            gercek = aday.resolve()
            if (_yol_uygun(gercek) and _kok_altinda(gercek)
                    and gercek.is_file() and _medya_mi(gercek) and _imza_tamam(gercek)):
                st = gercek.stat()
                return {"id": _kimlik(gercek), "ad": gercek.name, "tip": _tip(gercek),
                        "klasor": gercek.parent.name, "klasor_id": _kimlik(gercek.parent),
                        "boyut": st.st_size, "tarih": int(st.st_mtime)}
        except OSError:
            pass
        return None

    # 2) Ad parçası → arama; birebir ad eşleşmesi önceliklidir
    sonuc = ara_medya(s, limit=20)
    if not sonuc:
        return None
    tam = [x for x in sonuc if x["ad"].lower() == s.lower()]
    return (tam or sonuc)[0]
