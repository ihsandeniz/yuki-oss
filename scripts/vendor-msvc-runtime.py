#!/usr/bin/env python3
"""Windows bundle'ındaki ÇÖZÜLEMEYEN MSVC C++ runtime importlarını kapat.

NEDEN (ölçüm 2026-08-02 — satılan `Yuki-0.5.4-win-x64-lite.zip`, 17.205 dosya;
`pybundle-win` içindeki 293 PE dosyasının import tablosu `objdump -p` ile tarandı):

  • `msvcp140_1.dll` pakete **hiç** girmiyordu. `onnxruntime.dll` ve
    `onnxruntime_pybind11_state.pyd` ikisi de import tablosunda **statik** ister.
  • `msvcp140.dll` pakette 4 kopya hâlinde vardı ama hepsi BAŞKA wheel'lerin
    dizinlerinde. Windows bir `.pyd` yüklerken `LOAD_WITH_ALTERED_SEARCH_PATH`
    kullanır → uygulama dizini yerine **yalnız o .pyd'nin kendi dizini** aranır.
    Yani ctranslate2'nin kopyası onnxruntime'ı kurtarmaz.
  • `vcruntime140*.dll` tesadüfen çalışıyordu: `python.exe` onları açılışta kendi
    dizininden yükler, sonrası "zaten bellekte" (base-name) kuralına takılır.
    `msvcp140` python tarafından hiç yüklenmez → o tesadüf ona işlemez.

ETKİ: VC++ Redistributable kurulu OLMAYAN temiz bir Win10/11'de semantik hafıza
  (Ultra'nın satılan özelliği) · `ocr_image` · `read_qr` ölür. Son ikisi **P1**'de
  = BEDAVA sürümün ilan ettiği 20 aracın 2'si. (VAD ölmez — Silero ONNX düşerse
  RMS enerji yedeğine geçer.)

NEDEN TARAMA, NEDEN ELLE LİSTE DEĞİL: ilk denemede hedefler "ürün neyi import
  ediyor?" yargısıyla elle seçilmişti ve **yanlıştı** — `pyclipper` `app/` altında
  hiç geçmiyor ama `rapidocr/ch_ppocr_det/utils.py` onu modül tepesinde import
  ediyor, yani OCR'ın canlı yolunda. Bu yüzden invaryant "kullandığımızı sandığımız
  dosyalar çalışsın" değil, **"pakette çözülemeyen tek bir MSVC importu kalmasın"**.

SÜRÜM YARIŞI: aynı base-name'den Windows süreçte **tek kopya** yükler; ilk yükleyen
  kazanır. `ctranslate2/MSVCP140.dll` adı hash'lenmemiş olduğu için yarışı O
  kazanıyordu (14.40.33810), oysa kökteki çalışan `vcruntime140.dll` 14.44.35211.
  Bu script hash'siz adlı tüm kopyaları PIN_VERSION'da tekilleştirir (MSVC 14.x'te
  **yeni** runtime eskiye uyumludur — ters yön değil). `numpy.libs`/`shapely.libs`
  kopyaları delvewheel ile hash'li adlandırıldığı için yarışa hiç girmez → dokunulmaz.

KAYNAK: PyPI `msvc-runtime` wheel'i. İçindeki DLL'ler Microsoft'un resmi
  `vc_redist.x64.exe`'sinden (Burn bundle → attached cab → `a12`) çıkarılanlarla
  **byte-byte aynı** — sha256 ile doğrulandı; aşağıdaki pin o ölçümden gelir.

Kullanım:
    python3 scripts/vendor-msvc-runtime.py            # göm (idempotent)
    python3 scripts/vendor-msvc-runtime.py --check    # sadece denetle, yazma
    python3 scripts/vendor-msvc-runtime.py --wheel /yol/msvc_runtime-*.whl

⚠️ `pybundle-win` yeniden üretildiğinde (uv cross-install) bu script TEKRAR
   çalıştırılmalı — yoksa hata sessizce geri gelir. `tests/test_msvc_runtime.py`
   bunu regresyon olarak yakalar.
"""
from __future__ import annotations

import argparse
import hashlib
import os
import shutil
import struct
import subprocess
import sys
import tempfile
import zipfile
from pathlib import Path

KOK = Path(__file__).resolve().parent.parent          # → depo kökü
BUNDLE = KOK / "backend" / "pybundle-win"

WHEEL_SPEC = "msvc-runtime==14.44.35112"
WHEEL_SHA256 = "af179a6c552070e660493765efd5856283af3fed971ddc3577203a7d3f1ee8e7"
PIN_VERSION = "14.44.35211.0"

# Bu script'in sağlayabildiği runtime DLL'leri (msvc-runtime wheel'inin içeriği).
# Listede OLMAYAN bir MSVC bağımlılığı çıkarsa sessizce geçilmez, hata verilir.
SAGLANABILIR = {
    "msvcp140.dll", "msvcp140_1.dll", "msvcp140_2.dll",
    "msvcp140_atomic_wait.dll", "msvcp140_codecvt_ids.dll",
    "vcruntime140.dll", "vcruntime140_1.dll", "vcruntime140_threads.dll",
}
# `python.exe` bunları kendi dizininden açılışta yükler → süreç genelinde
# "zaten bellekte" olurlar, ayrıca kopyalamaya gerek yok.
KOKTEN_GELEN = {"vcruntime140.dll", "vcruntime140_1.dll"}


def pe_import_eder(yol: Path) -> set[str]:
    """PE import tablosundaki DLL adları (küçük harfe indirgenmiş)."""
    try:
        cikti = subprocess.run(
            ["objdump", "-p", str(yol)],
            capture_output=True, text=True, timeout=120,
        ).stdout
    except Exception:
        return set()
    return {
        satir.split("DLL Name:")[1].strip().lower()
        for satir in cikti.splitlines()
        if "DLL Name:" in satir
    }


def pe_surum(yol: Path) -> str:
    """VS_FIXEDFILEINFO'dan dosya sürümü — '?' okunamazsa."""
    try:
        d = yol.read_bytes()
    except OSError:
        return "?"
    i = d.find(b"\xbd\x04\xef\xfe")          # VS_FIXEDFILEINFO imzası
    if i < 0:
        return "?"
    ms, ls = struct.unpack_from("<II", d, i + 8)
    return f"{ms >> 16}.{ms & 0xFFFF}.{ls >> 16}.{ls & 0xFFFF}"


def tara(bundle: Path) -> tuple[dict[Path, set[str]], list[Path], int]:
    """Bundle'ı tara.

    Döner:
      eksik   : {dizin: {gereken dll adları}} — o dizindeki bir PE dosyası
                istiyor ama ne kendi dizininde ne de bundle kökünde var
      eskiler : PIN_VERSION'da olmayan, hash'siz adlı runtime kopyaları
                (base-name yarışına giren, sürümü tekilleştirilecek olanlar)
      sayi    : taranan PE dosyası sayısı
    """
    kok_dll = {p.name.lower() for p in bundle.glob("*.dll")}
    eksik: dict[Path, set[str]] = {}
    eskiler: list[Path] = []
    sayi = 0

    for dirpath, _dirnames, files in os.walk(bundle):
        d = Path(dirpath)
        yerel = {f.lower() for f in files if f.lower().endswith(".dll")}

        # Hash'siz adlı (delvewheel'in dokunmadığı) runtime kopyaları base-name
        # yarışına girer → sürümleri tekil olmalı.
        for f in files:
            if f.lower() in SAGLANABILIR and pe_surum(d / f) != PIN_VERSION:
                eskiler.append(d / f)

        for f in files:
            if not f.lower().endswith((".pyd", ".dll")):
                continue
            sayi += 1
            for dll in pe_import_eder(d / f) & SAGLANABILIR:
                # Kendi dizininde varsa çözülür (LOAD_WITH_ALTERED_SEARCH_PATH).
                if dll in yerel:
                    continue
                # Bundle KÖKÜ, bir .pyd'nin bağımlılıkları için aranmaz. Tek istisna:
                # python.exe'nin açılışta kendi dizininden yüklediği runtime'lar —
                # onlar süreçte "zaten bellekte" olduğu için base-name'den çözülür.
                if dll in KOKTEN_GELEN and dll in kok_dll:
                    continue
                eksik.setdefault(d, set()).add(dll)
    return eksik, eskiler, sayi


def wheel_getir(verilen: str | None, tmp: Path) -> Path:
    if verilen:
        w = Path(verilen)
        if not w.is_file():
            sys.exit(f"✗ Wheel bulunamadı: {w}")
    else:
        print(f"▸ Wheel indiriliyor: {WHEEL_SPEC}")
        hedef = tmp / "whl"
        subprocess.run(
            [sys.executable, "-m", "pip", "download", WHEEL_SPEC,
             "--only-binary=:all:", "--platform", "win_amd64",
             "--python-version", "3.14", "--no-deps", "-d", str(hedef)],
            check=True, stdout=subprocess.DEVNULL,
        )
        w = next(hedef.glob("*.whl"))

    gercek = hashlib.sha256(w.read_bytes()).hexdigest()
    if gercek != WHEEL_SHA256:
        sys.exit(
            f"✗ Wheel SHA256 uyuşmadı.\n"
            f"   beklenen: {WHEEL_SHA256}\n"
            f"   gerçek  : {gercek}\n"
            f"   → wheel değişmiş; pin yeniden ölçülmeden GÖMÜLMEZ."
        )
    print("✓ Wheel SHA256 doğrulandı (Microsoft resmi redist'iyle birebir)")
    return w


def dll_cikar(wheel: Path, tmp: Path) -> dict[str, Path]:
    """Wheel'deki .data/data/*.dll → {küçük harfli ad: yol}."""
    hedef = tmp / "dll"
    hedef.mkdir(parents=True, exist_ok=True)
    bulunan: dict[str, Path] = {}
    with zipfile.ZipFile(wheel) as z:
        for isim in z.namelist():
            ad = isim.rsplit("/", 1)[-1]
            # `.data/data/Scripts/` kopyalarını atla — aynı dosyanın ikizi
            if not ad.lower().endswith(".dll") or "/Scripts/" in isim:
                continue
            if ad.lower() not in SAGLANABILIR:
                continue
            p = hedef / ad
            p.write_bytes(z.read(isim))
            bulunan[ad.lower()] = p
    return bulunan


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--check", action="store_true", help="sadece denetle, yazma")
    ap.add_argument("--wheel", help="hazır wheel yolu (ağsız çalışmak için)")
    args = ap.parse_args()

    if not BUNDLE.is_dir():
        print(f"✗ Windows bundle yok: {BUNDLE}", file=sys.stderr)
        print("  Önce pybundle-win üretilmeli (uv cross-install).", file=sys.stderr)
        return 1
    if not shutil.which("objdump"):
        print("✗ `objdump` gerekli (binutils) — import tabloları okunamıyor.", file=sys.stderr)
        return 1

    eksik, eskiler, sayi = tara(BUNDLE)
    print(f"▸ Tarandı: {sayi} PE dosyası\n")

    bilinmeyen = {d for dlls in eksik.values() for d in dlls} - SAGLANABILIR
    if bilinmeyen:
        print(f"✗ Bu script'in sağlayamadığı runtime bağımlılığı: {sorted(bilinmeyen)}",
              file=sys.stderr)
        return 1

    if not eksik and not eskiler:
        print("✓ MSVC runtime tamam — çözülemeyen import yok, sürümler tekil.")
        return 0

    if eksik:
        print("❌ ÇÖZÜLEMEYEN IMPORT:")
        for d in sorted(eksik):
            print(f"   {d.relative_to(BUNDLE)}/  ← {', '.join(sorted(eksik[d]))}")
    if eskiler:
        print("\n⚠️  BASE-NAME YARIŞINA GİREN ESKİ KOPYA:")
        for p in sorted(eskiler):
            print(f"   {p.relative_to(BUNDLE)}  ({pe_surum(p)} → {PIN_VERSION})")

    if args.check:
        print("\n✗ Düzeltmek için: python3 scripts/vendor-msvc-runtime.py", file=sys.stderr)
        return 1

    with tempfile.TemporaryDirectory() as td:
        tmp = Path(td)
        wheel = wheel_getir(args.wheel, tmp)
        dller = dll_cikar(wheel, tmp)

        print()
        yazilan = 0
        for d in sorted(eksik):
            for dll in sorted(eksik[d]):
                kaynak = dller.get(dll)
                if kaynak is None:
                    print(f"✗ Wheel'de yok: {dll}", file=sys.stderr)
                    return 1
                # Var olan dosyanın yazımını koru (case-duyarlı Linux fs'inde
                # zip'e iki ayrı dosya girmesin); yoksa import tablosundaki adı kullan.
                mevcut = next((f for f in os.listdir(d) if f.lower() == dll), None)
                hedef = d / (mevcut or kaynak.name)
                shutil.copyfile(kaynak, hedef)
                print(f"  → {hedef.relative_to(BUNDLE)}  (yok → {PIN_VERSION})")
                yazilan += 1

        for p in sorted(eskiler):
            onceki = pe_surum(p)
            kaynak = dller.get(p.name.lower())
            if kaynak is None:
                print(f"✗ Wheel'de yok: {p.name}", file=sys.stderr)
                return 1
            shutil.copyfile(kaynak, p)
            print(f"  → {p.relative_to(BUNDLE)}  ({onceki} → {PIN_VERSION})")
            yazilan += 1

    print(f"\n✓ {yazilan} dosya yazıldı. Doğrulama: "
          f"python3 scripts/vendor-msvc-runtime.py --check")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
