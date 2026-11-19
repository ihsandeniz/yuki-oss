"""Paket filtresi ile canlı kod ayrışmasın — 2026-09-01'de bu ayrışma ÜRÜNÜ KIRDI.

NEDEN VAR
  `electron/electron-builder*.yml` müşteri paketine hangi backend dosyalarının
  gireceğini seçer. 2026-07-29'da şu satır yazıldı:

      - "!app/api/{bio,devices_api,fitness,monitor}.py"   # main.py'de KAYITLI DEĞİL

  Doğruydu — o gün. 2026-08-23'te `8c7b22c` (*"fitnes: sunucu senkronu açıldı —
  router kaydı"*) `fitness`'ı main.py'ye geri bağladı; **filtre güncellenmedi**.
  Sonuç: paketlenen uygulama açılışta

      ImportError: cannot import name 'fitness' from 'app.api'

  verip ölüyordu. v0.6.11 bu hâlde YAYINLANDI. Kimse fark etmedi çünkü delta
  güncelleme dosyayı ayrıca taşıyor — yani *mevcut* kullanıcılar sağlamdı,
  yalnız **sıfırdan indirenler** açılmayan bir uygulama alıyordu.

NE ÖLÇER
  Paket filtresinde DIŞLANAN her python modülü, canlı kodda import EDİLMEMELİ.
  İhlal = paket açılmaz.

NE ÖLÇMEZ (dürüst sınır)
  Dinamik import (`importlib.import_module(ad)`), string'den kurulan modül adları
  ve koşullu import'lar bu taramada görünmez. Bu test statik `import` satırlarını
  ölçer — kapsamı odur.
"""
from __future__ import annotations

import re
from pathlib import Path

import pytest

KOK = Path(__file__).resolve().parents[2]          # depo kökü
BACKEND = KOK / "backend"
CONFIGLER = sorted((KOK / "electron").glob("electron-builder*.yml"))


def _brace_ac(desen: str) -> list[str]:
    """`app/api/{a,b}.py` → ['app/api/a.py', 'app/api/b.py']. Tek seviye yeter."""
    m = re.search(r"\{([^}]*)\}", desen)
    if not m:
        return [desen]
    return [desen[: m.start()] + p.strip() + desen[m.end() :] for p in m.group(1).split(",")]


def dislanan_moduller() -> dict[str, set[str]]:
    """config → dışlanan .py yollarının kümesi (backend köküne göreli)."""
    sonuc: dict[str, set[str]] = {}
    for cfg in CONFIGLER:
        dis: set[str] = set()
        for satir in cfg.read_text(encoding="utf-8").splitlines():
            s = satir.strip()
            if not s.startswith("- "):
                continue
            s = s[2:].split("#")[0].strip().strip('"').strip("'")
            if not s.startswith("!") or not s.endswith(".py"):
                continue           # yalnız tek dosya dışlamaları; `**` blokları ayrı sınıf
            for yol in _brace_ac(s[1:]):
                dis.add(yol)
        sonuc[cfg.name] = dis
    return sonuc


def import_edilen_moduller() -> dict[str, str]:
    """'app/api/fitness.py' → onu import eden ilk dosya (backend/app altındaki statik import'lar).

    ⚠️ Regex ile YAZILMAZ. İlk sürümü `[\\w,\\s]+` kullanıyordu; `\\s` satır sonunu da
    yuttuğu için parantezli/çok satırlı import'larda 'app/limiter/limiter\\n\\nrouter.py'
    gibi uydurma yollar üretti ve gerçek eşleşmeyi kaçırdı. `ast` kesin ayrıştırır.
    """
    import ast

    bulunan: dict[str, str] = {}
    for py in sorted((BACKEND / "app").rglob("*.py")):
        if "__pycache__" in py.parts:
            continue
        rel = py.relative_to(BACKEND).as_posix()
        try:
            agac = ast.parse(py.read_text(encoding="utf-8", errors="replace"), filename=str(py))
        except SyntaxError:
            continue                                   # ayrıştırılamayan dosya bu testin konusu değil
        for d in ast.walk(agac):
            if isinstance(d, ast.ImportFrom):
                if d.level or not d.module or not d.module.startswith("app"):
                    continue                           # göreli import bu kapının kapsamı dışında
                taban = d.module.replace(".", "/")
                for ad in d.names:
                    if ad.name == "*":
                        continue
                    # `from app.api import fitness` → app/api/fitness.py
                    # `from app.api.fitness import router` → app/api/fitness.py
                    bulunan.setdefault(f"{taban}/{ad.name}.py", rel)
                bulunan.setdefault(f"{taban}.py", rel)
            elif isinstance(d, ast.Import):
                for ad in d.names:
                    if ad.name.startswith("app."):
                        bulunan.setdefault(ad.name.replace(".", "/") + ".py", rel)
    return bulunan


@pytest.mark.parametrize("cfg", [c.name for c in CONFIGLER])
def test_dislanan_modul_import_edilmiyor(cfg: str) -> None:
    dis = dislanan_moduller()[cfg]
    edilen = import_edilen_moduller()
    carpisma = sorted(dis & edilen.keys())
    assert not carpisma, (
        f"{cfg} bu modülleri paketten DIŞLIYOR ama canlı kod onları import ediyor — "
        f"paketlenen uygulama açılışta ImportError verir:\n"
        + "\n".join(f"  · {y}  ← {edilen[y]}" for y in carpisma)
        + "\n\nYa filtreden çıkar, ya import'u kaldır. (2026-09-01: fitness.py bu yüzden ürünü kırdı)"
    )


def test_kendini_sina() -> None:
    """Kapı kör olmasın: bilinen bir çarpışma ateşlemeli, temiz durum susmalı."""
    edilen = import_edilen_moduller()
    assert "app/api/fitness.py" in edilen, (
        "main.py'nin fitness import'u artık taranmıyor — tarayıcı kör kalmış olabilir. "
        "Import gerçekten kaldırıldıysa bu satırı güncelle."
    )
    # yapay dışlama listesiyle ateşleme sınaması
    sahte_dis = {"app/api/fitness.py"}
    assert sahte_dis & edilen.keys(), "kesişim mantığı çalışmıyor"
    # temiz durumda susmalı
    assert not ({"app/api/olmayan_modul.py"} & edilen.keys())


def test_configler_senkron() -> None:
    """4 config aynı dışlama listesini taşımalı — biri güncellenip öbürü unutulmasın."""
    hepsi = dislanan_moduller()
    assert len(hepsi) >= 2, "beklenen electron-builder config'leri bulunamadı"
    referans_ad, referans = next(iter(hepsi.items()))
    for ad, dis in hepsi.items():
        fark = dis ^ referans
        assert not fark, (
            f"{ad} ile {referans_ad} arasındaki dışlama listesi ayrışmış: {sorted(fark)}\n"
            "Bu listeler elle senkron tutuluyor; biri düzeltilip öbürü unutulursa "
            "o SKU kırık çıkar (Linux düzelir, Windows kırık kalır)."
        )


# ── Ayar şablonu müşteriye ULAŞIYOR mu (2026-09-08) ────────────────
#
# 'un ilk yarısı şablonu DEPOYA koydu (bfe2b5e) ama paket yarısı açıktı:
# AppImage/zip kuran müşteri 142 satırlık şablonu hiçbir yerde göremiyordu.
# Bu iki kapı, işin iki ucunu birden korur — biri şablonun girdiğini, öbürü
# girmesi için YANLIŞ yolun (filtre gevşetme) seçilmediğini garanti eder.

SABLON = KOK / ".env.example"


def test_ayar_sablonu_depoda_ve_dolu() -> None:
    """Şablonun kendisi kaybolmasın — paketleme girdisi ona bakıyor."""
    assert SABLON.exists(), ".env.example depoda yok — 4 config'in extraResources girdisi kırık"
    satir = SABLON.read_text(encoding="utf-8").splitlines()
    assert len(satir) > 100, f"şablon beklenmedik şekilde küçülmüş ({len(satir)} satır)"


@pytest.mark.parametrize("cfg", CONFIGLER, ids=lambda p: p.name)
def test_ayar_sablonu_pakete_giriyor(cfg: Path) -> None:
    """4 SKU'nun DÖRDÜ de şablonu taşımalı — biri unutulursa o SKU'nun müşterisi göremez."""
    metin = cfg.read_text(encoding="utf-8")
    kod = re.sub(r"(?m)^\s*#.*$", "", metin)      # yorumda geçmesi SAYILMAZ
    assert "../.env.example" in kod, (
        f"{cfg.name} şablonu paketlemiyor. extraResources'a şu girdi gerekli:\n"
        "  - from: ../.env.example\n    to: .env.example"
    )


@pytest.mark.parametrize("cfg", CONFIGLER, ids=lambda p: p.name)
def test_gercek_env_dislamasi_GEVSETILMEDI(cfg: Path) -> None:
    """🔴 `!.env` / `!.env.*` filtresi backend girdisinde KALMALI.

    Bu testin varlık sebebi bir yanlış çözümü engellemek: "şablon pakete
    girmiyor" sorununu filtreyi açarak çözmeye kalkmak. Ölçüldü (09-08):
    o filtre `../backend`'e uygulanıyor, kökteki gerçek şablon zaten onun
    kapsamında DEĞİL — yani gevşetmek sorunu çözmez, sadece **geliştiricinin gerçek
    `.env`'ini ve `.pem` anahtarlarını müşteri paketine sokma** riskini açar.
    """
    kod = re.sub(r"(?m)^\s*#.*$", "", cfg.read_text(encoding="utf-8"))
    for filtre in ('"!.env"', '"!.env.*"'):
        assert filtre in kod, (
            f"{cfg.name} içinde {filtre} filtresi YOK. Şablonu paketlemek için bunu "
            "kaldırma — şablon AYRI bir extraResources girdisiyle geliyor "
            "(test_ayar_sablonu_pakete_giriyor). Bu filtre gerçek anahtarları dışarıda tutar."
        )
