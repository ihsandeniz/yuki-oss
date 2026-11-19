"""Çalışma alanı kilidi + tür araçları (Yuki Atölye v2, Faz 0b; yama/bitir Faz 1).

Görev araçları YALNIZ kendi çalışma alanında (`<atölye kökü>/<tür>/<ad>/`) okur/yazar.
Kilit üç katmanlıdır:
  1. Metin: mutlak yol, `~`, `..`, NUL ve ayrılmış `.gorev/` reddedilir.
  2. Sembolik bağ: yolun var olan HER bileşeni `lstat` ile denetlenir; bağ varsa red.
  3. Açma: son bileşen `O_NOFOLLOW` ile açılır — denetimle açma arasında bağa
     çevrilen dosya da reddedilir (yarış penceresi daralır).

🔴 Bu araçlar global `TOOLS`'ta YOK: sohbetin şemasına girmez, `/api/tool-call`
ile çağrılamaz. Tek yol görev servisinin araç kapısıdır (`gorev.py`).
"""

from __future__ import annotations

import os
from pathlib import Path, PurePosixPath

AYRILMIS = ".gorev"          # servis kaydı (durum.json, mesajlar.json) — araçlara kapalı
MAKS_BOYUT = 1_000_000       # bayt, tek dosya
MAKS_DOSYA = 500             # çalışma alanında toplam dosya
MAKS_YOL = 240               # karakter, göreli yol


class AlanHatasi(Exception):
    """Yol çalışma alanının dışına çıkıyor ya da kilitli bir yere değiyor."""


def guvenli_yol(kok: Path, yol: str) -> Path:
    """Göreli `yol`u çalışma alanı içinde mutlak yola çevir — dışarı çıkarsa `AlanHatasi`."""
    if not isinstance(yol, str) or not yol.strip():
        raise AlanHatasi("yol boş")
    if "\x00" in yol:
        raise AlanHatasi("yolda NUL karakteri")
    if len(yol) > MAKS_YOL:
        raise AlanHatasi("yol çok uzun")
    if yol.startswith(("/", "~")):
        raise AlanHatasi("mutlak ya da ev yolu yasak — göreli yol ver (ör. index.html)")
    parcalar = PurePosixPath(yol).parts
    if not parcalar:
        raise AlanHatasi("yol boş")
    if ".." in parcalar:
        raise AlanHatasi("'..' yasak — çalışma alanı dışına çıkılamaz")
    if parcalar[0] == AYRILMIS:
        raise AlanHatasi(f"'{AYRILMIS}/' görev kaydıdır, araçlara kapalı")

    if kok.is_symlink():
        raise AlanHatasi("çalışma alanı kökü sembolik bağ")
    kok_r = kok.resolve(strict=True)
    gecerli = kok_r
    for p in parcalar:
        gecerli = gecerli / p
        if gecerli.is_symlink():
            raise AlanHatasi(f"sembolik bağ üzerinden geçilemez: {p}")
    if not gecerli.resolve(strict=False).is_relative_to(kok_r):
        raise AlanHatasi("yol çalışma alanının dışına çözülüyor")
    return gecerli


def _dosyalar(kok: Path) -> list[str]:
    out: list[str] = []
    for dizin, altlar, dosyalar in os.walk(kok, followlinks=False):
        rel = Path(dizin).relative_to(kok)
        if rel.parts[:1] == (AYRILMIS,):
            altlar[:] = []
            continue
        altlar[:] = sorted(a for a in altlar if not (rel == Path(".") and a == AYRILMIS))
        for d in sorted(dosyalar):
            out.append(str(rel / d) if rel != Path(".") else d)
    return out


# ------------------------------------------------------------------ #
# Tür araçları — imza: (kok, **args) -> str. Hata DÖNDÜRÜLÜR (model görsün),
# fırlatılmaz; kilit ihlali "Hata: …" ile başlar.
# ------------------------------------------------------------------ #

def alan_agac(kok: Path) -> str:
    liste = _dosyalar(kok)
    if not liste:
        return "(çalışma alanı boş)"
    return "\n".join(liste[:MAKS_DOSYA])


def alan_oku(kok: Path, yol: str) -> str:
    try:
        hedef = guvenli_yol(kok, yol)
        fd = os.open(hedef, os.O_RDONLY | os.O_NOFOLLOW)
    except AlanHatasi as e:
        return f"Hata: {e}"
    except FileNotFoundError:
        return f"Hata: '{yol}' yok"
    except OSError as e:
        return f"Hata: '{yol}' açılamadı ({e.strerror})"
    with os.fdopen(fd, "rb") as f:
        veri = f.read(MAKS_BOYUT + 1)
    if len(veri) > MAKS_BOYUT:
        return f"Hata: '{yol}' {MAKS_BOYUT} bayttan büyük"
    return veri.decode("utf-8", "replace")


def alan_yaz(kok: Path, yol: str, icerik: str) -> str:
    if not isinstance(icerik, str):
        return "Hata: içerik metin olmalı"
    veri = icerik.encode("utf-8")
    if len(veri) > MAKS_BOYUT:
        return f"Hata: içerik {MAKS_BOYUT} bayttan büyük"
    try:
        hedef = guvenli_yol(kok, yol)
        if not hedef.exists() and len(_dosyalar(kok)) >= MAKS_DOSYA:
            return f"Hata: çalışma alanında en çok {MAKS_DOSYA} dosya olabilir"
        hedef.parent.mkdir(parents=True, exist_ok=True)
        guvenli_yol(kok, yol)   # mkdir sonrası yeniden: arada bağa çevrilen dizin yakalanır
        fd = os.open(hedef, os.O_WRONLY | os.O_CREAT | os.O_TRUNC | os.O_NOFOLLOW, 0o644)
    except AlanHatasi as e:
        return f"Hata: {e}"
    except OSError as e:
        return f"Hata: '{yol}' yazılamadı ({e.strerror})"
    with os.fdopen(fd, "wb") as f:
        f.write(veri)
    return f"yazıldı: {yol} ({len(veri)} bayt)"


def alan_yama(kok: Path, yol: str, eski: str, yeni: str) -> str:
    """Dosyada `eski` metni `yeni` ile değiştirir — `eski` dosyada TAM BİR kez geçmeli."""
    if not isinstance(eski, str) or not eski:
        return "Hata: 'eski' boş olamaz"
    if not isinstance(yeni, str):
        return "Hata: 'yeni' metin olmalı"
    mevcut = alan_oku(kok, yol)
    if mevcut.startswith("Hata:"):
        return mevcut
    n = mevcut.count(eski)
    if n == 0:
        return f"Hata: '{yol}' içinde 'eski' metin bulunamadı — önce alan_oku ile bak"
    if n > 1:
        return f"Hata: 'eski' metin '{yol}' içinde {n} kez geçiyor — tek yeri seçecek kadar uzun ver"
    sonuc = alan_yaz(kok, yol, mevcut.replace(eski, yeni, 1))
    return sonuc.replace("yazıldı:", "yamalandı:", 1) if sonuc.startswith("yazıldı:") else sonuc


def alan_bitir(kok: Path, ozet: str = "") -> str:
    """İşi bitirdiğini bildirir: doğrulayıcı (statik + 1440/390 ekran) koşar, rapor döner.
    Temizse model araçsız özetle biter; kirliyse hataları düzeltip yeniden çağırır.
    Sonuç `.gorev/dogrulama.json`'a yazılır — görev servisi son kararı oradan okur."""
    from app.services.atolye import dogrulayici
    try:
        return dogrulayici.metin(dogrulayici.dogrula(kok))
    except Exception as e:     # doğrulayıcı çökerse model "temiz" sanmasın
        return f"Hata: doğrulama koşamadı ({type(e).__name__}: {str(e)[:120]})"


ARACLAR = {"alan_agac": alan_agac, "alan_oku": alan_oku, "alan_yaz": alan_yaz,
           "alan_yama": alan_yama, "alan_bitir": alan_bitir}

SEMALAR = {
    "alan_agac": {"type": "function", "function": {
        "name": "alan_agac",
        "description": "Çalışma alanındaki dosyaları listeler (göreli yollar).",
        "parameters": {"type": "object", "properties": {}, "required": []},
    }},
    "alan_oku": {"type": "function", "function": {
        "name": "alan_oku",
        "description": "Çalışma alanındaki bir dosyayı okur. Yol göreli olmalı (ör. index.html).",
        "parameters": {"type": "object", "properties": {
            "yol": {"type": "string", "description": "Göreli dosya yolu"},
        }, "required": ["yol"]},
    }},
    "alan_yaz": {"type": "function", "function": {
        "name": "alan_yaz",
        "description": "Çalışma alanına dosya yazar (varsa üzerine). Yol göreli olmalı; "
                       "alan dışına, mutlak yola ya da sembolik bağa yazılamaz.",
        "parameters": {"type": "object", "properties": {
            "yol": {"type": "string", "description": "Göreli dosya yolu (ör. css/stil.css)"},
            "icerik": {"type": "string", "description": "Dosyanın tam içeriği"},
        }, "required": ["yol", "icerik"]},
    }},
    "alan_yama": {"type": "function", "function": {
        "name": "alan_yama",
        "description": "Dosyada küçük değişiklik: 'eski' metni 'yeni' ile değiştirir. 'eski' "
                       "dosyada tam bir kez geçmeli. Küçük düzeltmede tüm dosyayı yeniden "
                       "yazmak yerine bunu kullan.",
        "parameters": {"type": "object", "properties": {
            "yol": {"type": "string", "description": "Göreli dosya yolu"},
            "eski": {"type": "string", "description": "Değişecek metin (birebir, tek geçen)"},
            "yeni": {"type": "string", "description": "Yerine gelecek metin"},
        }, "required": ["yol", "eski", "yeni"]},
    }},
    "alan_bitir": {"type": "function", "function": {
        "name": "alan_bitir",
        "description": "İş bittiğinde çağır: doğrulayıcı siteyi ölçer (dış kaynak, kırık "
                       "bağlantı, JS hatası, 1440 ve 390 genişlikte yatay taşma). TEMİZ derse "
                       "araçsız kısa özet yaz; KİRLİ derse hataları düzelt, yeniden çağır.",
        "parameters": {"type": "object", "properties": {
            "ozet": {"type": "string", "description": "Ne yaptığının bir cümlelik özeti"},
        }, "required": []},
    }},
}

# Faz 2 : araştırma türünün araçları aynı kayıt defterine girer → TEK araç kümesi;
# genel dispatcher'a (`TOOLS`) HİÇ girmezler; testi bunu ölçer.
from app.services.atolye import kaynak as _kaynak  # noqa: E402  (kaynak alan'ı içe aktarır)

ARACLAR.update(_kaynak.ARACLAR)
SEMALAR.update(_kaynak.SEMALAR)
