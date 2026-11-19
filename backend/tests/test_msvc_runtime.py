"""Windows paketinde çözülemeyen MSVC C++ runtime importu kalmasın.

🔴 NEDEN VAR (ölçüm 2026-08-02, satılan `Yuki-0.5.4-win-x64-lite.zip` açılarak):

`onnxruntime.dll` ve `onnxruntime_pybind11_state.pyd` import tablolarında
`msvcp140_1.dll` istiyordu; o DLL paketin **17.205 dosyasının hiçbirinde yoktu**.
`msvcp140.dll` pakette 4 kopya hâlinde vardı ama hepsi BAŞKA wheel'lerin
dizinlerinde — Windows bir `.pyd`'yi `LOAD_WITH_ALTERED_SEARCH_PATH` ile yükler,
yani **yalnız o dosyanın kendi dizinini** arar; başka bir wheel'in kopyası işe yaramaz.

Sonuç: VC++ Redistributable kurulu OLMAYAN temiz bir Win10/11'de
  · semantik hafıza (Ultra'nın satılan özelliği)
  · `ocr_image`  ← P1, BEDAVA sürümün ilan ettiği 20 araçtan biri
  · `read_qr`    ← P1, aynı şekilde
sessizce ölüyordu.

Düzeltme `scripts/vendor-msvc-runtime.py` ile bundle'a gömüldü. Bu test onun
**geri gelmesini** engeller: `pybundle-win` her yeniden üretildiğinde (uv
cross-install) gömme adımı atlanırsa hata sessizce döner.

⚠️ Wine yeşili KANIT DEĞİL — Wine kendi `msvcp140` uyarlamasını sağladığı için
   `pybundle-win/python.exe`'yi Wine altında koşurken `import onnxruntime` ÇALIŞIR
   (docs/arsiv/URUN_DURUM.md § Wine turu tam bu yüzden yanlış yeşil verdi). Tek geçerli
   ölçüm: PE import tablosu + dosya varlığı.
"""
from __future__ import annotations

import os
import re
import shutil
import struct
import subprocess
from pathlib import Path

import pytest

KOK = Path(__file__).resolve().parent.parent.parent      # → depo kökü
BUNDLE = KOK / "backend" / "pybundle-win"

PIN_VERSION = "14.44.35211.0"

# `msvc-runtime` wheel'inin sağladığı, base-name yarışına giren runtime DLL'leri
SAGLANABILIR = {
    "msvcp140.dll", "msvcp140_1.dll", "msvcp140_2.dll",
    "msvcp140_atomic_wait.dll", "msvcp140_codecvt_ids.dll",
    "vcruntime140.dll", "vcruntime140_1.dll", "vcruntime140_threads.dll",
}
# `python.exe` bunları açılışta kendi dizininden yükler → süreçte "zaten bellekte"
KOKTEN_GELEN = {"vcruntime140.dll", "vcruntime140_1.dll"}

pytestmark = [
    pytest.mark.skipif(not BUNDLE.is_dir(),
                       reason="pybundle-win yok (Windows bundle üretilmemiş)"),
    pytest.mark.skipif(shutil.which("objdump") is None,
                       reason="objdump yok (binutils) — PE import tablosu okunamıyor"),
]


def _importlar(yol: Path) -> set[str]:
    cikti = subprocess.run(["objdump", "-p", str(yol)],
                           capture_output=True, text=True, timeout=120).stdout
    return {s.split("DLL Name:")[1].strip().lower()
            for s in cikti.splitlines() if "DLL Name:" in s}


def _surum(yol: Path) -> str:
    d = yol.read_bytes()
    i = d.find(b"\xbd\x04\xef\xfe")          # VS_FIXEDFILEINFO imzası
    if i < 0:
        return "?"
    ms, ls = struct.unpack_from("<II", d, i + 8)
    return f"{ms >> 16}.{ms & 0xFFFF}.{ls >> 16}.{ls & 0xFFFF}"


def _pe_dosyalari():
    for dirpath, _d, files in os.walk(BUNDLE):
        for f in files:
            if f.lower().endswith((".pyd", ".dll")):
                yield Path(dirpath) / f


def test_cozulemeyen_msvc_importu_yok():
    """Paketteki HER PE dosyasının MSVC runtime bağımlılığı çözülebilmeli.

    İnvaryant bilerek "kullandığımızı sandığımız modüller çalışsın" DEĞİL:
    ilk denemede hedefler elle seçilmişti ve `pyclipper` atlanmıştı — `app/`
    altında hiç geçmiyor ama `rapidocr/ch_ppocr_det/utils.py` onu modül
    tepesinde import ediyor, yani OCR'ın canlı yolunda. Yargıya değil taramaya güven.
    """
    kok_dll = {p.name.lower() for p in BUNDLE.glob("*.dll")}
    eksik: dict[str, set[str]] = {}
    sayi = 0

    for pe in _pe_dosyalari():
        sayi += 1
        yerel = {p.name.lower() for p in pe.parent.glob("*.dll")}
        for dll in _importlar(pe) & SAGLANABILIR:
            if dll in yerel:
                continue
            if dll in KOKTEN_GELEN and dll in kok_dll:
                continue
            eksik.setdefault(str(pe.parent.relative_to(BUNDLE)), set()).add(dll)

    assert sayi > 100, f"tarama şüpheli derecede az dosya gördü: {sayi}"
    assert not eksik, (
        "Çözülemeyen MSVC runtime importu var — temiz bir Windows'ta sessizce ölür.\n"
        + "\n".join(f"  {d}/ ← {', '.join(sorted(v))}" for d, v in sorted(eksik.items()))
        + "\n\nDüzeltme: python3 scripts/vendor-msvc-runtime.py"
    )


def test_runtime_surumleri_tekil():
    """Hash'siz adlı runtime kopyaları aynı sürümde olmalı.

    Windows aynı base-name'den süreçte TEK kopya yükler; ilk yükleyen kazanır.
    `ctranslate2/MSVCP140.dll` adı hash'lenmemiş olduğu için yarışı O kazanıyordu
    (14.40.33810), oysa kökteki çalışan `vcruntime140.dll` 14.44.35211'di →
    onnxruntime import sırasına göre eski CRT'ye düşebilirdi.

    `numpy.libs`/`shapely.libs` kopyaları delvewheel ile hash'li adlandırıldığı
    için yarışa hiç girmez; bu test onları bilerek kapsamaz.
    """
    sapan = {
        str(p.relative_to(BUNDLE)): _surum(p)
        for p in _pe_dosyalari()
        if p.name.lower() in SAGLANABILIR and _surum(p) != PIN_VERSION
    }
    assert not sapan, (
        f"Base-name yarışına giren farklı sürümler var (beklenen {PIN_VERSION}):\n"
        + "\n".join(f"  {k} → {v}" for k, v in sorted(sapan.items()))
        + "\n\nDüzeltme: python3 scripts/vendor-msvc-runtime.py"
    )


def _ihrac_edilenler(dll: Path) -> set[str]:
    """PE export adı tablosu."""
    cikti = subprocess.run(["objdump", "-x", str(dll)],
                           capture_output=True, text=True, timeout=120).stdout
    syms, icinde = set(), False
    for satir in cikti.splitlines():
        if "[Ordinal/Name Pointer] Table" in satir:
            icinde = True
            continue
        if not icinde:
            continue
        m = re.match(r"\s*\[\s*\d+\]\s*\+base\[\s*\d+\]\s+[0-9a-f]{4}\s+(\S+)", satir)
        if m:
            syms.add(m.group(1))
        elif not satir.strip() and syms:
            break
    return syms


def _ithal_edilenler(pe: Path, dll_adi: str) -> set[str]:
    """PE import tablosunda `dll_adi`'ndan istenen sembol adları."""
    cikti = subprocess.run(["objdump", "-p", str(pe)],
                           capture_output=True, text=True, timeout=120).stdout
    syms, mevcut = set(), None
    for satir in cikti.splitlines():
        m = re.search(r"DLL Name:\s*(\S+)", satir)
        if m:
            mevcut = m.group(1).lower()
            continue
        if mevcut != dll_adi.lower():
            continue
        # sütunlar: vma  <none>|ordinal  hint  Member-Name
        m2 = re.match(r"\s*[0-9a-f]{6,}\s+(?:<none>|\d+)\s+[0-9a-f]{4}\s+(\S+)", satir)
        if m2:
            syms.add(m2.group(1))
    return syms


def test_gomulen_dll_tuketicilerin_her_sembolunu_karsiliyor():
    """Sürüm tekilleştirmesi bir tüketiciyi aç bırakmasın.

    `ctranslate2/MSVCP140.dll` 14.40.33810'dan 14.44.35211'e **yükseltildi** — o dosya
    faster-whisper'ın (STT) canlı bağımlılığı ve bu değişiklik Windows'ta hiç
    çalıştırılmadı. MSVC 14.x'te yeni runtime eskiye uyumludur, ama "uyumlu olmalı"
    bir ölçüm değil; bu test sembol düzeyinde **ölçer**.

    Aynı test ileriye dönük de korur: bir wheel yükseltilip daha yeni bir CRT'ye
    ihtiyaç duyduğunda pin'in yetersiz kaldığını burada görürüz.
    """
    capi = BUNDLE / "Lib" / "site-packages" / "onnxruntime" / "capi"
    if not capi.is_dir():
        pytest.skip("onnxruntime bundle'da yok")
    # Ad harf duyarsız aranır: Windows'ta `MSVCP140.dll` = `msvcp140.dll`. Eski wheel büyük
    # harfli kopya getiriyordu; vendor-msvc-runtime.py ise küçük harfle yazar (onnxruntime 1.27
    # kendi kopyasını getirmiyor). Linux'ta sabit büyük harf yolu dosyayı kaçırıp 0 sembol
    # okuyordu (2026-11-12, çapraz üretilen kutuda ölçüldü).
    def _bul(ad: str) -> Path:
        for f in capi.iterdir():
            if f.name.lower() == ad:
                return f
        pytest.fail(f"{ad} onnxruntime/capi'de yok")
    ihrac = {
        "msvcp140.dll": _ihrac_edilenler(_bul("msvcp140.dll")),
        "msvcp140_1.dll": _ihrac_edilenler(_bul("msvcp140_1.dll")),
    }
    assert len(ihrac["msvcp140.dll"]) > 1000, "export tablosu okunamadı (parser bozuk?)"

    acik: dict[str, set[str]] = {}
    for pe in _pe_dosyalari():
        for dll, exp in ihrac.items():
            eksik = _ithal_edilenler(pe, dll) - exp
            if eksik:
                acik[f"{pe.relative_to(BUNDLE)} ← {dll}"] = eksik

    assert not acik, (
        "Gömülen runtime, tüketicinin istediği bazı sembolleri ihraç etmiyor:\n"
        + "\n".join(f"  {k}: {sorted(v)[:3]}" for k, v in sorted(acik.items()))
    )


def test_onnxruntime_kendi_dizininde_ikisini_de_tasiyor():
    """En kritik tüketici için açık, okunabilir bir kontrol.

    Yukarıdaki genel tarama bunu zaten kapsar; bu test hata mesajını
    "hangi dosya, neden önemli" diye somutlaştırır.
    """
    capi = BUNDLE / "Lib" / "site-packages" / "onnxruntime" / "capi"
    if not capi.is_dir():
        pytest.skip("onnxruntime bundle'da yok")
    mevcut = {p.name.lower() for p in capi.glob("*.dll")}
    for gerekli in ("msvcp140.dll", "msvcp140_1.dll"):
        assert gerekli in mevcut, (
            f"{gerekli} onnxruntime/capi/ içinde yok → VC++ Redist'siz Windows'ta "
            f"semantik hafıza + OCR ölür (ocr_image ve read_qr P1'de = bedava sürüm)."
        )
