"""Dosya gezgini API — SALT OKUNUR (yazma ucu, silme, taşıma, terminal YOK).

## Kararlar
**D1 · Kök klasör listesi AYARDAN gelir.** Öncelik: `YUKI_DOSYA_KOKLER` ortam
değişkeni (`os.pathsep` ile ayrılmış yollar) → `<veri dizini>/dosya/dosya-ayar.json`
(`{"kokler": [...]}`) → kullanıcının ev dizini. Gizli girdiler (`.ssh`, `.config` …)
varsayılan listede YOK; `gizli=1` ile görünür olurlar ama hassas yollar
(`_is_sensitive_read_path`: `.ssh`, `.gnupg`, anahtar/token dosyaları) o zaman bile 403'tür.
**D2 · Ayrı kök listesi** — galerinin `galeri-ayar.json`'u DEĞİL.
**D3 · YAZMA UCU YOK.** Her uç GET (yalnız `/git` POST'tur ve diske yazmaz —
yolu gövdede taşır ki adres loglara düşmesin). `scripts/test_temizlik.py` bunu denetler.

## Güvenlik — galerinin katmanları ÇAĞRILIR, kopyalanmaz
1. `resolve()` — symlink çözülür, sonra karar verilir (`~/x → /etc` reddedilir;
   `..` ile dizin dışına çıkış da burada çözülüp 2. katmanda düşer)
2. kök kapısı: `galeri_api._kok_altinda(gercek, dosya_kokleri)` — ayarlı kökler içinde mi
3. gizli kapısı: kökten sonraki herhangi bir parça `.` ile başlıyorsa (gizli=0) 403
4. hassas kapısı: `tools._base._is_sensitive_read_path` — gizli=1'de de geçerli
Akış/indirme `galeri_api._dosya_yanit` (Range, RFC 6266 Türkçe ad) ile; küçük resim
`galeri_api._kucuk_uret` + `_imza_tamam` ile.

🔴 `id` ham yol DEĞİL (sha1[:16]) — galeri deseni. Kayıt bellektedir; bilinmeyen id
404 döner, istemci köke düşer.

🔴 Bilet akışı `/api/galeri/akis/d/{bilet}` yolunda — main.py `_SKIP_PREFIXES`
`/api/galeri/akis/` önekini auth'tan muaf tutar. Yetkiyi bilet taşır (auth'lu
`/api/dosya/bilet/{id}` verir, tek dosyaya bağlı, 5 dk'da düşer).
"""

from __future__ import annotations

import hashlib
import json
import logging
import mimetypes
import os
import stat as _stat
import time
from pathlib import Path
from typing import Any

from fastapi import APIRouter, HTTPException, Query, Request
from fastapi.responses import FileResponse
from pydantic import BaseModel

from app.api import galeri_api as g
from app.config import DATA_DIR
from app.services.tools._base import _SENSITIVE_READ_DIRS, _is_sensitive_read_path

logger = logging.getLogger(__name__)

router = APIRouter(tags=["dosya"])

AYAR_YOLU = DATA_DIR / "dosya" / "dosya-ayar.json"
SAYFA_VARSAYILAN = 200
SAYFA_AZAMI = 1000
METIN_AZAMI = 64 * 1024
BILET_OMUR = 300.0
_LISTE_ONBELLEK_OMUR = 30.0          # aynı klasörün sonraki sayfaları diske inmesin

METIN_UZANTI = {
    ".txt", ".md", ".log", ".json", ".yaml", ".yml", ".toml", ".ini", ".cfg", ".conf",
    ".csv", ".tsv", ".py", ".js", ".ts", ".css", ".html", ".xml", ".sh", ".rs", ".go",
    ".c", ".h", ".cpp", ".java", ".sql", ".lua", ".srt",
}

_KAYIT: dict[str, str] = {}
_BILETLER: dict[str, tuple[str, float]] = {}
_LISTE_ONBELLEK: dict[tuple, tuple[float, list[dict[str, Any]]]] = {}


# ── Ayar + kökler ────────────────────────────────────────────────── #

def _varsayilan_ayar() -> dict[str, Any]:
    ortam = os.environ.get("YUKI_DOSYA_KOKLER", "")
    if ortam.strip():
        return {"kokler": [x for x in ortam.split(os.pathsep) if x.strip()]}
    return {"kokler": [str(Path.home())]}


def _ayar_oku() -> dict[str, Any]:
    if os.environ.get("YUKI_DOSYA_KOKLER", "").strip() or not AYAR_YOLU.exists():
        return _varsayilan_ayar()
    try:
        d = json.loads(AYAR_YOLU.read_text("utf-8"))
    except Exception:
        logger.warning("dosya-ayar.json okunamadı, varsayılana düşülüyor", exc_info=True)
        return _varsayilan_ayar()
    return {"kokler": [str(x) for x in (d.get("kokler") or []) if isinstance(x, str)]}


def _kokler() -> list[Path]:
    out = []
    for s in _ayar_oku()["kokler"]:
        try:
            p = Path(s).expanduser().resolve()
        except Exception:
            continue
        if p.is_dir():
            out.append(p)
    return out


def _kimlik(p: Path) -> str:
    kid = hashlib.sha1(str(p).encode("utf-8", "surrogateescape")).hexdigest()[:16]
    _KAYIT[kid] = str(p)
    return kid


def _coz(kid: str) -> Path:
    yol = _KAYIT.get(kid)
    if yol is None:
        raise HTTPException(404, "Kimlik bulunamadı (sunucu yeniden başlamış olabilir).")
    return Path(yol)


# ── Kapılar ──────────────────────────────────────────────────────── #

def _ait_kok(gercek: Path, kokler: list[Path]) -> Path | None:
    """En uzun eşleşen kök (iç içe kök: ~ ve ~/x → ~/x)."""
    adaylar = [k for k in kokler if g._kok_altinda(gercek, [k])]
    return max(adaylar, key=lambda k: len(str(k))) if adaylar else None


def _guvenli(p: Path, gizli: bool = False) -> tuple[Path, Path]:
    """Dört katman. Geçerse (gerçek yol, kök); geçemezse HTTPException."""
    try:
        gercek = p.resolve()                                  # katman 1
    except (OSError, RuntimeError):
        raise HTTPException(404, "Yol bulunamadı.")
    kokler = _kokler()
    if not g._kok_altinda(gercek, kokler):                   # katman 2 — kök kapısı
        raise HTTPException(403, "Bu yol dosya yöneticisinin köklerinin dışında.")
    kok = _ait_kok(gercek, kokler)
    goreli = gercek.relative_to(kok).parts if kok else ()
    if not gizli and any(x.startswith(".") for x in goreli):  # katman 3
        raise HTTPException(403, "Gizli klasör/dosya (göstermek için 'gizli' aç).")
    # `_is_sensitive_read_path` dizinin KENDİSİNİ (son parça `.ssh`) yakalamaz — yalnız
    # içindekileri; dosya yöneticisi klasörü de listeleyeceği için son parça da bakılır.
    if _is_sensitive_read_path(gercek) or gercek.name.lower() in _SENSITIVE_READ_DIRS:  # katman 4
        raise HTTPException(403, "Hassas yol — dosya yöneticisi açmaz.")
    if not gercek.exists():
        raise HTTPException(404, "Yol bulunamadı.")
    return gercek, kok


def _tur(ad: str, klasor: bool) -> str:
    if klasor:
        return "klasor"
    uz = os.path.splitext(ad)[1].lower()
    if uz in g.RESIM_UZANTI:
        return "resim"
    if uz in g.VIDEO_UZANTI:
        return "video"
    if uz == ".pdf":
        return "pdf"
    if uz in METIN_UZANTI:
        return "metin"
    if uz in {".mp3", ".ogg", ".wav", ".flac", ".m4a", ".opus"}:
        return "ses"
    if uz in {".zip", ".tar", ".gz", ".xz", ".7z", ".rar", ".zst"}:
        return "arsiv"
    return "dosya"


# ── Listeleme ────────────────────────────────────────────────────── #

def _tara(klasor: Path, gizli: bool) -> list[dict[str, Any]]:
    """Tek scandir; girdi başına bir lstat (DirEntry önbelleği). Symlink'in hedefi
    burada izlenmez — açılırken `_guvenli` karar verir."""
    out = []
    with os.scandir(klasor) as it:
        for e in it:
            ad = e.name
            if not gizli and ad.startswith("."):
                continue
            try:
                st = e.stat(follow_symlinks=False)
            except OSError:
                continue
            bag = _stat.S_ISLNK(st.st_mode)
            dizin = _stat.S_ISDIR(st.st_mode)
            if bag:
                try:
                    dizin = e.is_dir()          # hedef dizin mi (kapıdan geçmesi ayrı)
                except OSError:
                    dizin = False
            out.append({"ad": ad, "klasor": dizin, "boyut": 0 if dizin else st.st_size,
                        "tarih": int(st.st_mtime), "bag": bag})
    return out


SIRALAR = {"ad", "tarih", "boyut", "tur"}


def _sirala(kayit: list[dict[str, Any]], sira: str, yon: str) -> list[dict[str, Any]]:
    ters = yon == "azalan"
    if sira == "tarih":
        anahtar = lambda d: d["tarih"]
    elif sira == "boyut":
        anahtar = lambda d: d["boyut"]
    elif sira == "tur":
        anahtar = lambda d: (os.path.splitext(d["ad"])[1].lower(), d["ad"].lower())
    else:
        anahtar = lambda d: d["ad"].lower()
    sirali = sorted(kayit, key=anahtar, reverse=ters)
    # Klasör önce — yönden bağımsız (ters sıralamada da klasörler üstte)
    return [d for d in sirali if d["klasor"]] + [d for d in sirali if not d["klasor"]]


def _liste_al(klasor: Path, gizli: bool, sira: str, yon: str) -> list[dict[str, Any]]:
    try:
        mt = klasor.stat().st_mtime_ns
    except OSError:
        mt = 0
    anahtar = (str(klasor), gizli, sira, yon, mt)
    simdi = time.monotonic()
    kayit = _LISTE_ONBELLEK.get(anahtar)
    if kayit and simdi - kayit[0] < _LISTE_ONBELLEK_OMUR:
        return kayit[1]
    sonuc = _sirala(_tara(klasor, gizli), sira, yon)
    if len(_LISTE_ONBELLEK) > 32:
        _LISTE_ONBELLEK.clear()
    _LISTE_ONBELLEK[anahtar] = (simdi, sonuc)
    return sonuc


def _kirinti(gercek: Path, kok: Path) -> list[dict[str, str]]:
    out = [{"id": _kimlik(kok), "ad": kok.name or str(kok)}]
    cur = kok
    for parca in gercek.relative_to(kok).parts:
        cur = cur / parca
        out.append({"id": _kimlik(cur), "ad": parca})
    return out


# ── Uçlar ────────────────────────────────────────────────────────── #

@router.get("/api/dosya/kokler")
async def kokler():
    return {"ok": True, "kokler": [{"id": _kimlik(k), "ad": k.name or str(k), "yol": str(k)}
                                   for k in _kokler()]}


class Git(BaseModel):
    yol: str
    gizli: bool = False


@router.post("/api/dosya/git")
async def git(body: Git):
    """Elle yazılan yol → kimlik. Gövdede taşınır (adres loglara düşmez). Diske yazmaz."""
    ham = body.yol.strip()
    if not ham:
        raise HTTPException(400, "Yol boş.")
    p = Path(ham).expanduser()
    if not p.is_absolute():
        raise HTTPException(400, "Tam yol yazın (/ ya da ~ ile başlayan).")
    gercek, _ = _guvenli(p, body.gizli)
    return {"ok": True, "id": _kimlik(gercek), "klasor": gercek.is_dir()}


@router.get("/api/dosya/liste/{kid}")
async def liste(kid: str,
                offset: int = Query(0, ge=0),
                limit: int = Query(SAYFA_VARSAYILAN, ge=1, le=SAYFA_AZAMI),
                sira: str = Query("ad", pattern="^(ad|tarih|boyut|tur)$"),
                yon: str = Query("artan", pattern="^(artan|azalan)$"),
                gizli: int = Query(0, ge=0, le=1)):
    gercek, kok = _guvenli(_coz(kid), bool(gizli))
    if not gercek.is_dir():
        raise HTTPException(400, "Bu bir klasör değil.")
    try:
        tum = _liste_al(gercek, bool(gizli), sira, yon)
    except PermissionError:
        raise HTTPException(403, "Bu klasörü okuma izniniz yok.")
    except FileNotFoundError:
        raise HTTPException(404, "Klasör artık yok.")
    sayfa = []
    for d in tum[offset:offset + limit]:
        sayfa.append({**d, "id": _kimlik(gercek / d["ad"]), "tur": _tur(d["ad"], d["klasor"])})
    ust = _kimlik(gercek.parent) if gercek != kok else None
    return {"ok": True, "id": kid, "ad": gercek.name or str(gercek), "yol": str(gercek),
            "ust": ust, "kirinti": _kirinti(gercek, kok), "toplam": len(tum),
            "offset": offset, "girdiler": sayfa}


# ── F2 · Özyinelemeli arama (2026-10-30) ─────────────────── #
# Ad içinde geçen metin, açık klasörün ALTINDA. Kapılar okuma ile aynı, ek olarak:
#   · symlink İZLENMEZ (ne dizin ne dosya olarak inilir) → arama kök dışına taşamaz
#   · gizli=0'da `.` ile başlayan her parça atlanır · hassas dizinler HİÇ taranmaz
#   · süre (ARA_SURE_SN) ve sonuç (limit) tavanı: dolarsa `tamam=false` döner, kısmi sonuç verilir
# İptal istemcide (AbortController); sunucu tarafı süre tavanıyla sınırlı kalır.
ARA_SURE_SN = 3.0
ARA_AZAMI = 500


def _kucuk(s: str) -> str:
    """Türkçe küçültme (istemcideki toLocaleLowerCase('tr') ile aynı): I→ı, İ→i."""
    return s.replace("İ", "i").replace("I", "ı").lower()


def _ara(bas: Path, kok: Path, q: str, gizli: bool, limit: int, sure: float) -> dict[str, Any]:
    t0 = time.monotonic()
    bitis = t0 + sure
    sonuc: list[dict[str, Any]] = []
    taranan = 0
    yigin = [bas]
    tamam = True
    while yigin:
        if time.monotonic() > bitis:
            tamam = False
            break
        klasor = yigin.pop()
        try:
            it = os.scandir(klasor)
        except OSError:
            continue
        with it:
            altlar = []
            for e in it:
                ad = e.name
                if not gizli and ad.startswith("."):
                    continue
                try:
                    st = e.stat(follow_symlinks=False)
                except OSError:
                    continue
                taranan += 1
                bag = _stat.S_ISLNK(st.st_mode)
                dizin = _stat.S_ISDIR(st.st_mode)
                yol = Path(e.path)
                if dizin and ad.lower() in _SENSITIVE_READ_DIRS:
                    continue
                if not bag and _is_sensitive_read_path(yol):
                    continue
                if q in _kucuk(ad):
                    if len(sonuc) >= limit:
                        tamam = False
                        yigin = []
                        break
                    sonuc.append({"id": _kimlik(yol), "ad": ad, "klasor": dizin,
                                  "tur": _tur(ad, dizin), "boyut": 0 if dizin else st.st_size,
                                  "tarih": int(st.st_mtime), "bag": bag, "ust": _kimlik(yol.parent),
                                  "konum": str(yol.parent.relative_to(bas)) if yol.parent != bas else ""})
                if dizin and not bag:
                    altlar.append(yol)
            yigin.extend(sorted(altlar, reverse=True))   # ad sırasıyla derinlemesine
    return {"sonuclar": sonuc, "tamam": tamam, "taranan": taranan,
            "sure_ms": int((time.monotonic() - t0) * 1000)}


@router.get("/api/dosya/ara/{kid}")
def ara(kid: str,
        q: str = Query(..., min_length=1, max_length=200),
        limit: int = Query(200, ge=1, le=ARA_AZAMI),
        gizli: int = Query(0, ge=0, le=1)):
    """Sync uç (FastAPI iş parçacığında koşar) — tarama olay döngüsünü kilitlemez."""
    gercek, kok = _guvenli(_coz(kid), bool(gizli))
    if not gercek.is_dir():
        raise HTTPException(400, "Bu bir klasör değil.")
    aranan = _kucuk(q.strip())
    if not aranan:
        raise HTTPException(400, "Aranacak metin boş.")
    return {"ok": True, "id": kid, "q": q.strip(),
            **_ara(gercek, kok, aranan, bool(gizli), limit, ARA_SURE_SN)}


@router.get("/api/dosya/bilgi/{kid}")
async def bilgi(kid: str, gizli: int = Query(0, ge=0, le=1)):
    gercek, _ = _guvenli(_coz(kid), bool(gizli))
    try:
        st = gercek.stat()
    except PermissionError:
        raise HTTPException(403, "Bu yolu okuma izniniz yok.")
    klasor = gercek.is_dir()
    return {"ok": True, "id": kid, "ad": gercek.name, "yol": str(gercek), "klasor": klasor,
            "tur": _tur(gercek.name, klasor), "boyut": 0 if klasor else st.st_size,
            "tarih": int(st.st_mtime), "mime": None if klasor else mimetypes.guess_type(gercek.name)[0],
            "izin": _stat.filemode(st.st_mode)}


@router.get("/api/dosya/onizle/{kid}")
async def onizle(kid: str, gizli: int = Query(0, ge=0, le=1), k: int = Query(800)):
    """Resim → küçük resim (WebP, galeri önbelleği) · metin → ilk 64 KB.
    Video/PDF/indirme bilet ister (`/bilet/{id}`)."""
    gercek, _ = _guvenli(_coz(kid), bool(gizli))
    if not gercek.is_file():
        raise HTTPException(400, "Önizleme yalnız dosyada.")
    tur = _tur(gercek.name, False)
    if tur == "resim":
        if not g._imza_tamam(gercek):
            raise HTTPException(415, "Dosya içeriği uzantısıyla uyuşmuyor.")
        kenar = k if k in g.KUCUK_KADEMELER else 800
        hedef = g._kucuk_uret(gercek, kenar)
        if hedef is None:
            raise HTTPException(500, "Küçük resim üretilemedi.")
        return FileResponse(hedef, media_type="image/webp",
                            headers={"Cache-Control": "private, max-age=86400"})
    if tur == "metin" or gercek.suffix == "":
        try:
            with gercek.open("rb") as f:
                ham = f.read(METIN_AZAMI + 1)
        except PermissionError:
            raise HTTPException(403, "Bu dosyayı okuma izniniz yok.")
        if b"\x00" in ham[:4096]:
            raise HTTPException(415, "İkili dosya — metin önizlemesi yok.")
        return {"ok": True, "tur": "metin", "metin": ham[:METIN_AZAMI].decode("utf-8", "replace"),
                "kesildi": len(ham) > METIN_AZAMI}
    raise HTTPException(415, "Bu tür için önizleme bilet ile açılır.")


def _bilet_temizle() -> None:
    simdi = time.time()
    for b in [k for k, (_, t) in _BILETLER.items() if t < simdi]:
        _BILETLER.pop(b, None)


@router.get("/api/dosya/bilet/{kid}")
async def bilet(kid: str, gizli: int = Query(0, ge=0, le=1)):
    import secrets as _secrets
    gercek, _ = _guvenli(_coz(kid), bool(gizli))
    if not gercek.is_file():
        raise HTTPException(400, "Bilet yalnız dosyaya verilir.")
    _bilet_temizle()
    b = _secrets.token_urlsafe(24)
    _BILETLER[b] = (str(gercek), time.time() + BILET_OMUR)
    return {"ok": True, "bilet": b, "omur": int(BILET_OMUR), "url": f"/api/galeri/akis/d/{b}"}


@router.get("/api/galeri/akis/d/{bilet_kodu}")
async def akis(bilet_kodu: str, request: Request, indir: int = Query(0, ge=0, le=1)):
    """Biletli akış (video/PDF/indirme) — Range'li. Kapılar burada da koşar:
    bilet eskiyebilir, ayar değişip yol kökten çıkmış olabilir."""
    _bilet_temizle()
    kayit = _BILETLER.get(bilet_kodu)
    if not kayit:
        raise HTTPException(403, "Bilet geçersiz ya da süresi dolmuş.")
    yol, _ = kayit
    _BILETLER[bilet_kodu] = (yol, time.time() + BILET_OMUR)
    gercek, _ = _guvenli(Path(yol), gizli=True)   # gizlilik bilet verilirken denetlendi
    if not gercek.is_file():
        raise HTTPException(404, "Dosya bulunamadı.")
    return g._dosya_yanit(gercek, request.headers.get("range"), indir=bool(indir))
