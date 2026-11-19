#!/usr/bin/env python3
"""Windows paket kapısı: Linux'ta çapraz derlenen Windows kurulum paketinin (NSIS) doğru ayarla
ve doğru içerikle çıktığını denetler. AppImage kapısının (test_appimage_paket.py) ikizi.

    python3 scripts/test_windows_paket.py                 # ayar kapıları (derleme gerekmez)
    python3 scripts/test_windows_paket.py --paket         # + electron/dist/win-unpacked + Setup.exe
    python3 scripts/test_windows_paket.py --mutasyon      # her kapıyı bilerek kırar, yakalandı mı

Ayar kapıları:
  W1 hedef      electron-builder-win.yml win hedefleri nsis + zip (zip = uygulama içi tam güncelleme varlığı)
  W2 sir        backend filtresinde .env / .env.* / *.pem / token.json / data/** dışlanır
  W3 linux      Linux kutusu (pybundle) ve eski venv Windows paketine girmez
  W4 kullanici  NSIS kullanıcı başına kurar (perMachine false: yönetici izni istemez), sihirbazlı
  W5 derle      windows-derle.sh kendi WINEPREFIX'ini ve wine'lı makensis'i electron-builder'dan ÖNCE kurar
  W6 surum      electron-builder major 26 (eb26 dalı: npm audit kritik/yüksek kapandı)
  W8 nsis       windows-derle.sh --nsis-bul NSIS önbelleğini 24 VE 26 düzeninde bulur (sahte önbellekte koşar)
  W9 sinav      windows-wine-sinavi.sh sessiz kurulumda wine'ın sahte powershell.exe'sini kapatır
                (26'nın NSIS'i onu 'uygulama açık' sanıp çıkış 2 ile hiçbir şey kurmuyordu)
  W7 kutu       pybundle-win-uret.sh CPython sha256'sını denetler, Linux ikilisi kapısı var, MSVC gömer
Paket kapıları (--paket, derleme sonrası):
  P1 kutu       resources/backend/pybundle-win/python.exe + python314.dll var (motor paketin İÇİNDE)
  P2 sir_yok    resources/ altında .env, *.pem, token.json yok (pybundle-win hariç: certifi CA paketi)
  P3 test_yok   resources/backend/tests ve frontend/tests yok
  P4 lisans     .vrm yok, buffalo (InsightFace) yok
  P5 sablon     resources/.env.example var
  P6 linux_yok  resources/backend/pybundle (Linux) yok, ELF (Linux ikilisi) yok
  P7 msvc       onnxruntime/capi'de msvcp140.dll + msvcp140_1.dll var (VC++ redist'siz makine)
  P8 kurulum    dist/Yuki-Setup-*.exe var, PE (MZ) ve Nullsoft kurulum dosyası
"""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path

KOK = Path(__file__).resolve().parents[1]
YML = KOK / "electron/electron-builder-win.yml"
DERLE = KOK / "scripts/windows-derle.sh"
KUTU = KOK / "scripts/pybundle-win-uret.sh"
SINAV = KOK / "scripts/windows-wine-sinavi.sh"
PJ = KOK / "electron/package.json"
ACIK = KOK / "electron/dist/win-unpacked/resources"


def _backend_filtre(yml: str) -> list[str]:
    m = re.search(r"- from: \.\./backend\n\s+to: backend\n\s+filter:\n((?:\s+- .*\n|\s*#.*\n)+)", yml)
    if not m:
        return []
    return [re.sub(r"\s+#.*$", "", s).strip().strip('"') for s in re.findall(r"^\s+- (.*)$", m.group(1), re.M)]


def _blok(yml: str, ad: str) -> str:
    m = re.search(rf"^{ad}:\n((?:[ \t].*\n|[ \t]*\n)+)", yml, re.M)
    return m.group(1) if m else ""


def _kod(metin: str) -> list[str]:
    return [l for l in metin.splitlines() if l.strip() and not l.lstrip().startswith("#")]


def ayar_kapilari(yml: str, derle: str, kutu: str, pj: dict) -> dict[str, str | None]:
    """Her kapı için None (geçti) ya da hata metni."""
    s: dict[str, str | None] = {}
    win = _blok(yml, "win")
    hedef = re.findall(r"target:\s*(\w+)", win) + re.findall(r"^\s+-\s*(\w+)\b", win, re.M)
    s["W1 hedef"] = None if {"nsis", "zip"} <= set(hedef) else f"win hedefi {hedef} (nsis + zip gerekli)"
    filtre = _backend_filtre(yml)
    eksik = [d for d in ("!.env", "!.env.*", "!*.pem", "!token.json", "!data/**") if d not in filtre]
    s["W2 sir"] = f"eksik dışlama {eksik}" if eksik or not filtre else None
    eksik = [d for d in ("!pybundle/**", "!venv/**") if d not in filtre]
    s["W3 linux"] = f"eksik dışlama {eksik}" if eksik or not filtre else None
    nsis = _blok(yml, "nsis")
    s["W4 kullanici"] = (None if re.search(r"perMachine:\s*false", nsis) and re.search(r"oneClick:\s*false", nsis)
                         else "nsis perMachine/oneClick false değil")
    satir = _kod(derle)
    eb = next((i for i, l in enumerate(satir) if "electron-builder --win" in l), None)
    onek = next((i for i, l in enumerate(satir) if re.search(r"export WINEPREFIX=", l)), None)
    nsisd = next((i for i, l in enumerate(satir) if "export ELECTRON_BUILDER_NSIS_DIR=" in l), None)
    sarmal = any('exec wine "$DIR/makensis.exe"' in l for l in satir)
    tamam = eb is not None and onek is not None and nsisd is not None and onek < eb and nsisd < eb and sarmal
    s["W5 derle"] = None if tamam else f"sıra WINEPREFIX={onek} NSIS_DIR={nsisd} builder={eb} sarmal={sarmal}"
    eb_surum = pj.get("devDependencies", {}).get("electron-builder", "")
    major = re.search(r"(\d+)", eb_surum)
    s["W6 surum"] = None if major and major.group(1) == "26" else f"electron-builder {eb_surum!r}"
    k = _kod(kutu)
    sha = any("sha256sum -c" in l for l in k)
    etiket = any("win_amd64" in l for l in k) and any("-name '*.so'" in l for l in k)
    msvc = any("vendor-msvc-runtime.py" in l for l in k)
    platform = any("--python-platform x86_64-pc-windows-msvc" in l for l in k)
    s["W7 kutu"] = (None if sha and etiket and msvc and platform
                    else f"sha256={sha} linux_kapisi={etiket} msvc={msvc} platform={platform}")
    return s


def nsis_kapisi(derle_metni: str) -> str | None:
    """W8: betiği (verilen metinle) sahte önbelleklerde `--nsis-bul` kipinde koşturur.
    26 düzeni, 24 düzeni ve boş önbellek ayrı ayrı; elevate.exe'siz klasör sayılmaz."""
    import subprocess
    import tempfile

    with tempfile.TemporaryDirectory() as g:
        betik = Path(g) / "windows-derle.sh"
        betik.write_text(derle_metni)

        def kos(onbellek: Path) -> str:
            r = subprocess.run(["bash", str(betik), "--nsis-bul"], capture_output=True, text=True, timeout=30,
                               env={"PATH": "/usr/bin:/bin", "HOME": g, "ELECTRON_BUILDER_CACHE": str(onbellek)})
            return r.stdout.strip() if r.returncode == 0 else f"çıkış {r.returncode}: {r.stderr.strip()[:200]}"

        def kur(d: Path, elevate: bool = True) -> Path:
            d.mkdir(parents=True)
            (d / "makensis.exe").write_bytes(b"MZ")
            if elevate:
                (d / "elevate.exe").write_bytes(b"MZ")
            return d

        hatalar = []
        yeni = kur(Path(g) / "c26/nsis-3.0.4.1/nsis-3.0.4.1-1mx3n")
        if kos(Path(g) / "c26") != str(yeni):
            hatalar.append(f"26 düzeni bulunmadı ({kos(Path(g) / 'c26')!r})")
        eski = kur(Path(g) / "c24/nsis/nsis-3.0.4.1")
        if kos(Path(g) / "c24") != str(eski):
            hatalar.append(f"24 düzeni bulunmadı ({kos(Path(g) / 'c24')!r})")
        (Path(g) / "bos").mkdir()
        if kos(Path(g) / "bos") != "":
            hatalar.append(f"boş önbellekte yol döndü ({kos(Path(g) / 'bos')!r})")
        kur(Path(g) / "yarim/nsis-3.0.4.1/nsis-3.0.4.1-x", elevate=False)
        if kos(Path(g) / "yarim") != "":
            hatalar.append("elevate.exe'siz klasör kabul edildi (26 override'da elevate.exe arar)")
        return "; ".join(hatalar) or None


def sinav_kapisi(sinav_metni: str) -> str | None:
    """W9: kurulum dosyasını /S ile çalıştıran satır powershell.exe=d taşımalı."""
    kur = [l for l in _kod(sinav_metni) if 'wine "$KUR" /S' in l]
    if not kur:
        return "sınavda sessiz kurulum satırı yok"
    return None if all("powershell.exe=d" in l for l in kur) else "sessiz kurulumda powershell.exe kapatılmamış"


def _ici(kok: Path, ad: str) -> Path | None:
    """Windows'ta ad harf duyarsız: `MSVCP140.dll` = `msvcp140.dll`."""
    if not kok.is_dir():
        return None
    return next((f for f in kok.iterdir() if f.name.lower() == ad), None)


def paket_kapilari(kok: Path) -> dict[str, str | None]:
    s: dict[str, str | None] = {}
    if not kok.is_dir():
        return {"P0 derleme": f"{kok} yok — önce bash scripts/windows-derle.sh"}
    pw = kok / "backend/pybundle-win"
    eksik = [a for a in ("python.exe", "python314.dll") if not (pw / a).is_file()]
    s["P1 kutu"] = f"pybundle-win'de yok: {eksik}" if eksik else None
    dosyalar = [p for p in kok.rglob("*") if p.is_file()]
    sir = [str(p.relative_to(kok)) for p in dosyalar
           if (p.name in (".env", "token.json") or p.suffix == ".pem")
           and "pybundle-win" not in p.relative_to(kok).parts]
    s["P2 sir_yok"] = f"sır dosyası {sir[:5]}" if sir else None
    testler = [d for d in ("backend/tests", "frontend/tests") if (kok / d).exists()]
    s["P3 test_yok"] = f"pakette {testler}" if testler else None
    lisans = [str(p.relative_to(kok)) for p in kok.rglob("*")
              if p.suffix.lower() == ".vrm" or "buffalo" in p.name.lower()]
    s["P4 lisans"] = f"dağıtılamaz {lisans[:5]}" if lisans else None
    s["P5 sablon"] = None if (kok / ".env.example").is_file() else ".env.example yok"
    elf = []
    for p in dosyalar:
        if p.suffix in (".so", "") or ".so." in p.name:
            try:
                with p.open("rb") as f:
                    if f.read(4) == b"\x7fELF":
                        elf.append(str(p.relative_to(kok)))
            except OSError:
                pass
    linux = (kok / "backend/pybundle").exists()
    s["P6 linux_yok"] = (None if not elf and not linux
                         else f"Linux kutusu={linux} ELF={elf[:5]}")
    capi = pw / "Lib/site-packages/onnxruntime/capi"
    yok = [a for a in ("msvcp140.dll", "msvcp140_1.dll") if _ici(capi, a) is None]
    s["P7 msvc"] = f"onnxruntime/capi'de yok: {yok}" if yok else None
    kurulumlar = sorted(kok.parent.parent.glob("Yuki-Setup-*.exe"))
    if not kurulumlar:
        s["P8 kurulum"] = "dist/Yuki-Setup-*.exe yok"
    else:
        veri = kurulumlar[-1].read_bytes()
        s["P8 kurulum"] = (None if veri[:2] == b"MZ" and b"Nullsoft" in veri[:2_000_000]
                           else f"{kurulumlar[-1].name} NSIS kurulum dosyası değil")
    return s


def _yaz(baslik: str, sonuc: dict[str, str | None]) -> int:
    print(baslik)
    for ad, hata in sonuc.items():
        print(f"  {'✓' if hata is None else '✗'} {ad}" + ("" if hata is None else f" — {hata}"))
    kalan = sum(1 for h in sonuc.values() if h is not None)
    print(f"geçti {len(sonuc) - kalan} · kaldı {kalan}\n")
    return kalan


def mutasyon() -> int:
    """Her kapıyı tek tek kırar; kırılan kapı kırmızı vermezse kapı ölüdür."""
    import shutil
    import tempfile

    yml, derle, kutu, pj = YML.read_text(), DERLE.read_text(), KUTU.read_text(), json.loads(PJ.read_text())
    tanik = ayar_kapilari(yml, derle, kutu, pj)
    sonuc: dict[str, str | None] = {"M temel (gerçek ayar yeşil)": None if all(v is None for v in tanik.values()) else str(tanik)}
    ayar = [
        ("W1 hedef", yml.replace("    - nsis", "    - portable", 1), derle, kutu, pj),
        ("W1 hedef (zip)", yml.replace("    - zip", "    - 7z", 1), derle, kutu, pj),
        ("W2 sir", yml.replace('- "!.env"', '- "!.env-YOK"', 1), derle, kutu, pj),
        ("W3 linux", yml.replace('- "!pybundle/**"', '- "!pybundle-xx/**"', 1), derle, kutu, pj),
        ("W4 kullanici", yml.replace("perMachine: false", "perMachine: true", 1), derle, kutu, pj),
        ("W5 derle", yml, "\n".join(l for l in derle.splitlines() if "export WINEPREFIX=" not in l), kutu, pj),
        ("W6 surum", yml, derle, kutu, {**pj, "devDependencies": {**pj["devDependencies"], "electron-builder": "^24.13.3"}}),
        ("W7 kutu", yml, derle, "\n".join(l for l in kutu.splitlines() if "sha256sum -c" not in l), pj),
    ]
    for ad, y, d, k, p in ayar:
        h = ayar_kapilari(y, d, k, p)[ad.split(" (")[0]]
        sonuc[f"M {ad}"] = None if h else "kırıldı ama yakalanmadı"
    sinav = SINAV.read_text()
    sonuc["M temel W9 (gerçek sınav yeşil)"] = sinav_kapisi(sinav)
    sonuc["M W9 sinav (powershell kapatma silindi)"] = (
        None if sinav_kapisi(sinav.replace(';powershell.exe=d', '', 1)) else "kırıldı ama yakalanmadı")
    sonuc["M temel W8 (gerçek betik yeşil)"] = nsis_kapisi(derle)
    kirik = derle.replace('"$kok"/nsis-3.0.4.1/nsis-3.0.4.1-* ', "", 1)   # yalnız 26 deseni gider, 24 kalır
    assert kirik != derle, "W8 mutasyonu betikte deseni bulamadı"
    sonuc["M W8 nsis (26 düzeni silindi)"] = None if nsis_kapisi(kirik) else "kırıldı ama yakalanmadı"
    with tempfile.TemporaryDirectory() as g:
        # Gerçek düzen: dist/win-unpacked/resources + dist/Yuki-Setup-*.exe
        sahte = Path(g) / "dist/win-unpacked/resources"
        capi = sahte / "backend/pybundle-win/Lib/site-packages/onnxruntime/capi"
        capi.mkdir(parents=True)
        for a in ("python.exe", "python314.dll"):
            (sahte / "backend/pybundle-win" / a).write_bytes(b"MZ")
        (capi / "msvcp140.dll").write_bytes(b"MZ")
        (capi / "MSVCP140_1.dll").write_bytes(b"MZ")      # büyük harf de sayılmalı
        (sahte / ".env.example").write_text("")
        (Path(g) / "dist/Yuki-Setup-sahte.exe").write_bytes(b"MZ....Nullsoft Install System")
        temel = paket_kapilari(sahte)
        sonuc["M temel (sahte temiz paket yeşil)"] = None if all(v is None for v in temel.values()) else str(temel)
        bozan = {
            "P1 kutu": lambda k: (k / "backend/pybundle-win/python314.dll").unlink(),
            "P2 sir_yok": lambda k: (k / "backend/.env").write_text("ANTHROPIC_API_KEY=x"),
            "P3 test_yok": lambda k: (k / "backend/tests").mkdir(),
            "P4 lisans": lambda k: (k / "frontend").mkdir() or (k / "frontend/yuki3d.vrm").write_text(""),
            "P5 sablon": lambda k: (k / ".env.example").unlink(),
            "P6 linux_yok": lambda k: (k / "backend/libx.so").write_bytes(b"\x7fELF\x02"),
            "P7 msvc": lambda k: (k / "backend/pybundle-win/Lib/site-packages/onnxruntime/capi/MSVCP140_1.dll").unlink(),
            "P8 kurulum": lambda k: (k.parent.parent / "Yuki-Setup-sahte.exe").write_bytes(b"PK\x03\x04 zip"),
        }
        for ad, boz in bozan.items():
            kok_kopya = Path(g) / f"k-{ad.split()[0]}"
            shutil.copytree(Path(g) / "dist", kok_kopya / "dist")
            kopya = kok_kopya / "dist/win-unpacked/resources"
            boz(kopya)
            sonuc[f"M {ad}"] = None if paket_kapilari(kopya)[ad] else "kırıldı ama yakalanmadı"
    return _yaz("MUTASYON (kapı etkinliği)", sonuc)


def main() -> int:
    if "--mutasyon" in sys.argv:
        return 1 if mutasyon() else 0
    ayar = ayar_kapilari(YML.read_text(), DERLE.read_text(), KUTU.read_text(), json.loads(PJ.read_text()))
    ayar["W8 nsis"] = nsis_kapisi(DERLE.read_text())
    ayar["W9 sinav"] = sinav_kapisi(SINAV.read_text())
    kalan = _yaz("AYAR", ayar)
    if "--paket" in sys.argv:
        kalan += _yaz(f"PAKET ({ACIK})", paket_kapilari(ACIK))
    return 1 if kalan else 0


if __name__ == "__main__":
    sys.exit(main())
