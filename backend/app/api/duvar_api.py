"""Duvar kâğıdı API — sekme bazlı arka plan (resim · GIF · kısa video).

## Tasarım kararları

**Depo backend'de, localStorage'da değil.** Kısa video ve GIF localStorage'ın
~5 MB kotasına sığmaz; ayrıca Electron penceresi ile tarayıcı ayrı depolar
kullanır, kullanıcı aynı duvarı iki yerde ayrı ayrı kurmak zorunda kalırdı.

**Dosya uçları AUTH'LU.** `<img src>` / `<video src>` `Authorization` başlığı
gönderemez — bu depoda kripto sekmesinde öğrenilen ders. İki çıkış yolu vardı:
statik serbest sunmak ya da URL'e `?token=` koymak. İkisi de reddedildi:
`cloudflared` tüneli canlı, duvar kâğıtları kullanıcının kendi görselleri ve
token URL'e konursa geçmişe/loglara sızar (eski `finance.html` hatası). Yerine
frontend dosyayı `authFetch` ile **blob** olarak çeker. Bedeli: dosya belleğe
iner — bu yüzden `AZAMI_BOYUT` var.

**Uzantıya güvenilmez, içerik doğrulanır.** Yüklenen dosyanın ilk baytları
sihirli sayıya karşı sınanır; `.png` uzantılı bir HTML dosyası kabul edilmez.
"""

from __future__ import annotations

import json
import mimetypes
import shutil
import time
import uuid
from pathlib import Path
from typing import Any

from fastapi import APIRouter, File, HTTPException, UploadFile
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field

from app.mesajlar import M

router = APIRouter(prefix="/api/duvar", tags=["duvar"])

# ── Depo ─────────────────────────────────────────────────────── #
# 🔴 ÜRÜNE TAŞIRKEN DEĞİŞEN İLK ŞEY BURASI (2026-09-08).
# Kişiselde depo `backend/data/duvar/` idi — kod dizininin içi. Üründe bu
# ÇALIŞMAZ: paketlenmiş kurulum (AppImage/zip) **salt okunur** bir mount'tur.
# Ürünün yazılabilir kökü `DATA_DIR` (= `YUKI_DATA_DIR`, Electron userData);
# `media_uploads` · `uploads/voice_refs` · `anim_cache` · `memory.db` · `.env`
# hepsi orada. Duvar da aynı desene giriyor.
# ⚠️ `YUKI_MEDIA_DIR` DEĞİL — orası güncellemenin **medya katmanı** (sürümsüz
# overlay, `main.py:56`); kullanıcı yüklemesini oraya koymak, güncelleme
# temizliğiyle kullanıcının kendi görsellerini aynı sepete atmak olurdu.
from app.config import DATA_DIR

DEPO = DATA_DIR / "duvar"
AYAR_YOLU = DEPO / "ayar.json"

AZAMI_BOYUT = 50 * 1024 * 1024          # 50 MB — blob olarak belleğe iniyor

# Geçerli sekme anahtarları — nav'daki `data-tab` ile BİREBİR aynı olmalı.
# 🔴 Kişiselin 8 sekmesi (map · drive · kripto · odak · ağ tarama) ÜRÜNDE YOK —
# ürünleştirmede sökülmüşlerdi (CLAUDE.md § Üründen SÖKÜLENLER). Listeyi
# kopyalamak, olmayan sekmeler için ayar tutmak ve kullanıcıya seçtirmek olurdu.
# Ölçüldü 2026-09-08 (`index.html` `data-tab=`): chat · planner · hq · panel.
# `jobs` (Arka Plan İşleri) açık kaynak sürümde YOK (2026-10-17, kabuk çalıştıran
# özellikler çıkarıldı); eski ayar dosyasındaki `jobs` anahtarı yok sayılır.
SEKMELER = ("chat", "planner", "hq", "panel")

# ── Kabul edilen formatlar ───────────────────────────────────── #
# (uzantı → (tip, [sihirli imzalar]))  · imza None = imza kontrolü yok
_RESIM = "resim"
_VIDEO = "video"

BICIMLER: dict[str, tuple[str, list[bytes]]] = {
    ".jpg":  (_RESIM, [b"\xff\xd8\xff"]),
    ".jpeg": (_RESIM, [b"\xff\xd8\xff"]),
    ".png":  (_RESIM, [b"\x89PNG\r\n\x1a\n"]),
    ".gif":  (_RESIM, [b"GIF87a", b"GIF89a"]),
    ".webp": (_RESIM, [b"RIFF"]),           # RIFF....WEBP — aşağıda 8. bayt da bakılır
    ".avif": (_RESIM, [b"\x00\x00\x00"]),   # ftyp kutusu — 4..8 arası 'ftyp'
    ".mp4":  (_VIDEO, [b"\x00\x00\x00"]),
    ".m4v":  (_VIDEO, [b"\x00\x00\x00"]),
    ".webm": (_VIDEO, [b"\x1a\x45\xdf\xa3"]),
    ".ogv":  (_VIDEO, [b"OggS"]),
}


def _imza_gecerli(uzanti: str, bas: bytes) -> bool:
    """İlk baytlar bu uzantı için beklenen imzaya uyuyor mu?"""
    tip, imzalar = BICIMLER[uzanti]
    if uzanti == ".webp":
        return bas[:4] == b"RIFF" and bas[8:12] == b"WEBP"
    if uzanti in (".mp4", ".m4v", ".avif"):
        # ISO-BMFF: [4 bayt boyut]['ftyp'][marka]
        return bas[4:8] == b"ftyp"
    return any(bas.startswith(i) for i in imzalar)


def _depo_hazirla() -> None:
    DEPO.mkdir(parents=True, exist_ok=True)


def _varsayilan_ayar() -> dict[str, Any]:
    return {
        # "tek"   → tek duvar tüm sekmelerde
        # "sekme" → her sekmenin kendi duvarı
        "mod": "sekme",
        "tek": None,
        "sekmeler": {},          # {"hq": "<duvar_id>", ...}
        "perde": 55,             # 0-95 · okunabilirlik perdesi (yüzde)
        "bulanik": 0,            # 0-20 px
        "sessiz": True,          # video sesi (tarayıcılar sessizsiz oto-oynatmaz)
    }


def _ayar_oku() -> dict[str, Any]:
    if not AYAR_YOLU.exists():
        return _varsayilan_ayar()
    try:
        d = json.loads(AYAR_YOLU.read_text("utf-8"))
    except Exception:
        # Bozuk ayar Yuki'yi açılışta öldürmez — varsayılana düşer.
        return _varsayilan_ayar()
    tam = _varsayilan_ayar()
    tam.update({k: v for k, v in d.items() if k in tam})
    return tam


def _ayar_yaz(d: dict[str, Any]) -> None:
    _depo_hazirla()
    gecici = AYAR_YOLU.with_suffix(".json.tmp")
    gecici.write_text(json.dumps(d, ensure_ascii=False, indent=2), "utf-8")
    gecici.replace(AYAR_YOLU)       # atomik — yarım yazılmış ayar kalmaz


def _kayitlar() -> list[dict[str, Any]]:
    """Depodaki dosyaları listele. Kaynak DİZİNİN KENDİSİ — ayrı bir indeks
    dosyası tutmuyoruz; tutsaydık ikisi ayrışır ve 'listede var, diskte yok'
    sınıfı hatalar çıkardı."""
    _depo_hazirla()
    out = []
    for p in sorted(DEPO.iterdir()):
        if p.name == "ayar.json" or p.is_dir() or p.suffix == ".tmp":
            continue
        uz = p.suffix.lower()
        if uz not in BICIMLER:
            continue
        st = p.stat()
        out.append({
            "id":     p.name,
            "ad":     p.name.split("__", 1)[-1] if "__" in p.name else p.name,
            "tip":    BICIMLER[uz][0],
            "uzanti": uz,
            "boyut":  st.st_size,
            "tarih":  int(st.st_mtime),
        })
    return sorted(out, key=lambda x: -x["tarih"])


def _yol_coz(duvar_id: str) -> Path:
    """id → dosya yolu. Path traversal kapısı."""
    # id yalnız dosya ADI olabilir; ayırıcı içeren her şey reddedilir.
    if not duvar_id or "/" in duvar_id or "\\" in duvar_id or ".." in duvar_id:
        raise HTTPException(400, M("duvar.gecersiz-kimlik"))
    p = (DEPO / duvar_id).resolve()
    if not str(p).startswith(str(DEPO.resolve())):
        raise HTTPException(400, M("duvar.gecersiz-kimlik"))
    if not p.exists() or not p.is_file():
        raise HTTPException(404, M("duvar.bulunamadi"))
    return p


# ── Uçlar ────────────────────────────────────────────────────── #

@router.get("/liste")
async def liste():
    """Yüklü duvar kâğıtları + o anki ayar."""
    return {"ok": True, "duvarlar": _kayitlar(), "ayar": _ayar_oku(),
            "sekmeler": list(SEKMELER), "azami_boyut": AZAMI_BOYUT}


@router.post("/yukle")
async def yukle(dosya: UploadFile = File(...)):
    """Duvar kâğıdı yükle. Uzantı + içerik imzası + boyut denetlenir."""
    _depo_hazirla()

    ad = Path(dosya.filename or "duvar").name
    uz = Path(ad).suffix.lower()
    if uz not in BICIMLER:
        raise HTTPException(
            400,
            M("duvar.desteklenmeyen", uzanti=uz or M("duvar.uzantisiz"),
              kabul=", ".join(sorted(BICIMLER))),
        )

    bas = await dosya.read(16)
    if not _imza_gecerli(uz, bas):
        # Uzantı doğru ama içerik değil — sessizce kaydetmek, sonra
        # tarayıcıda "bozuk görsel" olarak görünmek demektir.
        raise HTTPException(400, M("duvar.icerik-uyusmuyor", uzanti=uz))

    # Güvenli ad: rastgele önek + temizlenmiş özgün ad (kullanıcı adı yola girmez)
    temiz = "".join(c for c in Path(ad).stem if c.isalnum() or c in " -_")[:60].strip()
    hedef = DEPO / f"{uuid.uuid4().hex[:8]}__{temiz or 'duvar'}{uz}"

    yazilan = len(bas)
    gecici = hedef.with_suffix(hedef.suffix + ".tmp")
    try:
        with gecici.open("wb") as f:
            f.write(bas)
            while True:
                parca = await dosya.read(1024 * 1024)
                if not parca:
                    break
                yazilan += len(parca)
                if yazilan > AZAMI_BOYUT:
                    raise HTTPException(
                        413, M("duvar.boyut-asimi", mb=AZAMI_BOYUT // (1024*1024))
                    )
                f.write(parca)
        gecici.replace(hedef)
    except Exception:
        gecici.unlink(missing_ok=True)      # yarım dosya depoda kalmasın
        raise

    return {"ok": True, "id": hedef.name, "tip": BICIMLER[uz][0], "boyut": yazilan}


@router.get("/dosya/{duvar_id}")
async def dosya(duvar_id: str):
    """Duvar kâğıdının kendisi. Frontend bunu blob olarak çeker (bkz. modül başlığı)."""
    p = _yol_coz(duvar_id)
    tur = mimetypes.guess_type(p.name)[0] or "application/octet-stream"
    # Duvar kâğıdı nadiren değişir ve adı benzersizdir → uzun önbellek güvenli.
    return FileResponse(p, media_type=tur, headers={"Cache-Control": "private, max-age=86400"})


@router.delete("/{duvar_id}")
async def sil(duvar_id: str):
    """Duvar kâğıdını sil + ona işaret eden ayarları temizle.

    ⚠️ Ayar temizliği ŞART: silinen dosyaya bağlı bir sekme kalırsa o sekme
    açılışta 404 yer ve arka plan sessizce boş kalır — kullanıcı "duvar
    kayboldu" diye okur, sebebini göremez.
    """
    p = _yol_coz(duvar_id)
    p.unlink()

    a = _ayar_oku()
    degisti = False
    if a.get("tek") == duvar_id:
        a["tek"] = None
        degisti = True
    temiz = {k: v for k, v in (a.get("sekmeler") or {}).items() if v != duvar_id}
    if len(temiz) != len(a.get("sekmeler") or {}):
        a["sekmeler"] = temiz
        degisti = True
    if degisti:
        _ayar_yaz(a)

    return {"ok": True, "silindi": duvar_id, "ayar_guncellendi": degisti}


class DuvarAyar(BaseModel):
    mod: str = Field("sekme", pattern="^(tek|sekme|kapali)$")
    tek: str | None = None
    sekmeler: dict[str, str | None] = Field(default_factory=dict)
    perde: int = Field(55, ge=0, le=95)
    bulanik: int = Field(0, ge=0, le=20)
    sessiz: bool = True


@router.put("/ayar")
async def ayar_yaz(body: DuvarAyar):
    """Ayarı kaydet. Var olmayan duvar/sekme adları sessizce elenir."""
    mevcut = {k["id"] for k in _kayitlar()}

    tek = body.tek if body.tek in mevcut else None
    sekmeler = {
        s: v for s, v in body.sekmeler.items()
        if s in SEKMELER and v in mevcut
    }

    a = {
        "mod": body.mod,
        "tek": tek,
        "sekmeler": sekmeler,
        "perde": body.perde,
        "bulanik": body.bulanik,
        "sessiz": body.sessiz,
    }
    _ayar_yaz(a)
    return {"ok": True, "ayar": a}


@router.get("/ayar")
async def ayar_oku():
    return {"ok": True, "ayar": _ayar_oku()}


@router.post("/ornek-yukle")
async def ornek_yukle():
    """Denemelik: AliceAi'nin kendi karakter görsellerini depoya kopyalar.

    geliştiricinin *"deneme olarak AliceAi duvar kâğıdı resimlerini kullanabilirsin"*
    isteği için. Karakter fullbody görselleri + Yuki'nin bekleme klibi (mp4) —
    yani hem resim hem video yolu tek komutla denenebiliyor.
    """
    _depo_hazirla()
    kaynak = Path(__file__).resolve().parents[3] / "frontend" / "assets" / "characters"
    if not kaynak.is_dir():
        raise HTTPException(404, M("duvar.karakter-yok", yol=kaynak))

    istenen = ["yuki_fullbody.jpg", "yuki_fb_idle.mp4"]

    eklenen, atlanan = [], []
    mevcut_adlar = {k["ad"] for k in _kayitlar()}
    for ad in istenen:
        kay = kaynak / ad
        if not kay.exists():
            atlanan.append({"ad": ad, "sebep": M("duvar.sebep-kaynakta-yok")})
            continue
        if ad in mevcut_adlar:
            atlanan.append({"ad": ad, "sebep": M("duvar.sebep-zaten-yuklu")})
            continue
        if kay.stat().st_size > AZAMI_BOYUT:
            atlanan.append({"ad": ad, "sebep": M("duvar.sebep-boyut")})
            continue
        hedef = DEPO / f"{uuid.uuid4().hex[:8]}__{Path(ad).stem}{kay.suffix.lower()}"
        shutil.copy2(kay, hedef)
        eklenen.append({"id": hedef.name, "ad": ad,
                        "tip": BICIMLER[kay.suffix.lower()][0]})

    return {"ok": True, "eklenen": eklenen, "atlanan": atlanan}
