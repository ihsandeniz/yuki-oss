#!/usr/bin/env python3
"""AppImage paket kapısı — yalnız Linux AppImage'ın (ilk sürüm kararı 2026-11-12) doğru
ayarla ve doğru içerikle çıktığını denetler.

    python3 scripts/test_appimage_paket.py                 # ayar kapıları (derleme gerekmez)
    python3 scripts/test_appimage_paket.py --paket         # + electron/dist/linux-unpacked içeriği
    python3 scripts/test_appimage_paket.py --mutasyon      # her kapıyı bilerek kırar, yakalandı mı

Ayar kapıları:
  A1 hedef      electron-builder.yml linux hedefleri AppImage x64 içerir
  A2 sir        backend filtresinde .env / .env.* / *.pem / token.json / data/** dışlanır
  A3 win        Windows kutusu (pybundle-win) ve eski venv Linux paketine girmez
  A4 runtime    linux-derle.sh statik runtime'ı SON electron-builder çağrısından ÖNCE kurar (FUSE 2'siz açılış)
  A5 surum      electron-builder major 26 (24'ün 1 kritik + 7 yüksek audit bulgusu, 11-12)
  A6 temiz      önbellek yoksa ön derleme araçları indirir (yoksa temiz makinede runtime adımı durur)
  A7 duzen      appimage-statik-runtime.sh electron-builder 26 önbellek düzenindeki runtime'ı bulup
                değiştirir (sahte önbellekte betik GERÇEKTEN koşturulur; 24 düzeni de)
Paket kapıları (--paket, derleme sonrası):
  P1 kutu       resources/backend/pybundle/bin/python3 var (motor AppImage İÇİNDE)
  P2 sir_yok    resources/ altında .env, *.pem, token.json yok
  P3 test_yok   resources/backend/tests ve frontend/tests yok
  P4 lisans     .vrm yok, buffalo (InsightFace) yok
  P5 sablon     resources/.env.example var (ilk açılışta userData'ya kopyalanır)
  P6 fuse       dist/*.AppImage'ın başındaki runtime libfuse.so.2 aramıyor (statik runtime pakete girdi)
"""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path

KOK = Path(__file__).resolve().parents[1]
YML = KOK / "electron/electron-builder.yml"
DERLE = KOK / "scripts/linux-derle.sh"
PJ = KOK / "electron/package.json"
ACIK = KOK / "electron/dist/linux-unpacked/resources"
DIST = KOK / "electron/dist"
RUNTIME_BETIK = KOK / "scripts/appimage-statik-runtime.sh"
VENDOR = KOK / "scripts/vendor"


def _backend_filtre(yml: str) -> list[str]:
    m = re.search(r"- from: \.\./backend\n\s+to: backend\n\s+filter:\n((?:\s+- .*\n|\s*#.*\n)+)", yml)
    if not m:
        return []
    return [re.sub(r"\s+#.*$", "", s).strip().strip('"') for s in re.findall(r"^\s+- (.*)$", m.group(1), re.M)]


def _linux_hedefler(yml: str) -> list[str]:
    m = re.search(r"^linux:\n((?:[ \t].*\n|\s*\n)+)", yml, re.M)
    if not m:
        return []
    return re.findall(r"target:\s*(\w[\w.]*)", m.group(1))


def ayar_kapilari(yml: str, derle: str, pj: dict) -> dict[str, str | None]:
    """Her kapı için None (geçti) ya da hata metni."""
    s: dict[str, str | None] = {}
    hedef = _linux_hedefler(yml)
    s["A1 hedef"] = None if "AppImage" in hedef and re.search(r"arch:\s*x64", yml) else f"linux hedefi {hedef}"
    filtre = _backend_filtre(yml)
    eksik = [d for d in ("!.env", "!.env.*", "!*.pem", "!token.json", "!data/**") if d not in filtre]
    s["A2 sir"] = f"eksik dışlama {eksik}" if eksik or not filtre else None
    eksik = [d for d in ("!pybundle-win/**", "!venv/**") if d not in filtre]
    s["A3 win"] = f"eksik dışlama {eksik}" if eksik or not filtre else None
    satirlar = [l for l in derle.splitlines() if not l.lstrip().startswith("#")]
    rt = next((i for i, l in enumerate(satirlar) if "appimage-statik-runtime.sh" in l), None)
    ebler = [i for i, l in enumerate(satirlar) if "electron-builder" in l and "AppImage" in l]
    eb = ebler[-1] if ebler else None
    s["A4 runtime"] = None if rt is not None and eb is not None and rt < eb else f"sıra runtime={rt} son builder={eb}"
    on = [i for i in ebler if rt is not None and i < rt]
    kosul = any("runtime-x64" in l and ("compgen" in l or "-e " in l or "ls " in l) for l in satirlar)
    s["A6 temiz"] = None if on and kosul else f"önbelleksiz ön derleme yok (ön builder={on}, koşul={kosul})"
    eb_surum = pj.get("devDependencies", {}).get("electron-builder", "")
    major = re.search(r"(\d+)", eb_surum)
    s["A5 surum"] = None if major and major.group(1) == "26" else f"electron-builder {eb_surum!r}"
    return s


def duzen_kapisi(betik: str) -> str | None:
    """A7: betiği sahte önbellekte koşturur; iki düzende de runtime vendor dosyasıyla değişmeli."""
    import subprocess
    import tempfile

    with tempfile.TemporaryDirectory() as g:
        g = Path(g)
        (g / "scripts").mkdir()
        (g / "scripts/vendor").symlink_to(VENDOR)
        (g / "scripts/rt.sh").write_text(betik)
        duzenler = {"26": g / "eb/appimage-12.0.1/appimage-12.0.1-abcde/runtime-x64",
                    "24": g / "eb/appimage/appimage-12.0.1/runtime-x64"}
        for yol in duzenler.values():
            yol.parent.mkdir(parents=True)
            yol.write_bytes(b"\x7fELF dlopen libfuse.so.2")
        r = subprocess.run(["bash", str(g / "scripts/rt.sh")], capture_output=True, text=True,
                           env={"ELECTRON_BUILDER_CACHE": str(g / "eb"), "PATH": "/usr/bin:/bin"})
        vendor = (VENDOR / "appimage-runtime-x86_64").read_bytes()
        kalan = [d for d, yol in duzenler.items() if yol.read_bytes() != vendor]
        if r.returncode != 0 or kalan:
            return f"çıkış {r.returncode}, değişmeyen düzen {kalan}: {(r.stderr or r.stdout).strip()[-160:]}"
    return None


def paket_kapilari(kok: Path) -> dict[str, str | None]:
    s: dict[str, str | None] = {}
    if not kok.is_dir():
        return {"P0 derleme": f"{kok} yok — önce bash scripts/linux-derle.sh"}
    py = kok / "backend/pybundle/bin/python3"
    s["P1 kutu"] = None if py.exists() else "pybundle/bin/python3 yok"
    # pybundle/ hariç: oradaki *.pem certifi'nin herkese açık CA paketi (HTTPS için gerekli).
    sir = [str(p.relative_to(kok)) for p in kok.rglob("*")
           if (p.name in (".env", "token.json") or p.suffix == ".pem")
           and "pybundle" not in p.relative_to(kok).parts]
    s["P2 sir_yok"] = f"sır dosyası {sir[:5]}" if sir else None
    testler = [d for d in ("backend/tests", "frontend/tests") if (kok / d).exists()]
    s["P3 test_yok"] = f"pakette {testler}" if testler else None
    lisans = [str(p.relative_to(kok)) for p in kok.rglob("*")
              if p.suffix.lower() == ".vrm" or "buffalo" in p.name.lower()]
    s["P4 lisans"] = f"dağıtılamaz {lisans[:5]}" if lisans else None
    s["P5 sablon"] = None if (kok / ".env.example").is_file() else ".env.example yok"
    imajlar = sorted(kok.parent.parent.glob("*.AppImage"))
    if not imajlar:
        s["P6 fuse"] = "dist/*.AppImage yok"
    else:
        bas = imajlar[-1].read_bytes()[:200_000]
        s["P6 fuse"] = f"{imajlar[-1].name} runtime'ı libfuse.so.2 arıyor" if b"libfuse.so.2" in bas else None
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

    yml, derle, pj = YML.read_text(), DERLE.read_text(), json.loads(PJ.read_text())
    ayar = [
        ("A1 hedef", yml.replace("target: AppImage", "target: deb"), derle, pj),
        ("A2 sir", yml.replace('- "!.env"', '- "!.env-YOK"', 1), derle, pj),
        ("A3 win", yml.replace('- "!pybundle-win/**"', '- "!pybundle-xx/**"', 1), derle, pj),
        ("A4 runtime", yml, "\n".join(l for l in derle.splitlines()
                                       if "appimage-statik-runtime.sh" not in l), pj),
        ("A5 surum", yml, derle, {**pj, "devDependencies": {**pj["devDependencies"],
                                                              "electron-builder": "^24.13.3"}}),
        ("A6 temiz", yml, "\n".join(l for l in derle.splitlines() if "runtime-x64" not in l), pj),
    ]
    sonuc: dict[str, str | None] = {}
    for ad, y, d, p in ayar:
        h = ayar_kapilari(y, d, p)[ad]
        sonuc[f"M {ad}"] = None if h else "kırıldı ama yakalanmadı"
    # A7: 26 düzenini arayan satır çıkarılınca betik yalnız 24 yolunu bilir (yükseltme öncesi hâl)
    eski = "\n".join(l for l in RUNTIME_BETIK.read_text().splitlines()
                     if 'appimage-*/appimage-*/runtime-x64' not in l)
    sonuc["M A7 duzen"] = None if duzen_kapisi(eski) else "kırıldı ama yakalanmadı"
    with tempfile.TemporaryDirectory() as g:
        # Gerçek düzen: dist/linux-unpacked/resources + dist/*.AppImage
        sahte = Path(g) / "dist/linux-unpacked/resources"
        (sahte / "backend/pybundle/bin").mkdir(parents=True)
        (Path(g) / "dist/Yuki-sahte.AppImage").write_bytes(b"\x7fELF statik runtime")
        (sahte / "backend/pybundle/bin/python3").write_text("")
        (sahte / ".env.example").write_text("")
        temel = paket_kapilari(sahte)
        sonuc["M temel (sahte temiz paket yeşil)"] = None if all(v is None for v in temel.values()) else str(temel)
        bozan = {
            "P1 kutu": lambda k: (k / "backend/pybundle/bin/python3").unlink(),
            "P2 sir_yok": lambda k: (k / "backend/.env").write_text("ANTHROPIC_API_KEY=x"),
            "P3 test_yok": lambda k: (k / "backend/tests").mkdir(),
            "P4 lisans": lambda k: (k / "frontend").mkdir() or (k / "frontend/yuki3d.vrm").write_text(""),
            "P5 sablon": lambda k: (k / ".env.example").unlink(),
            "P6 fuse": lambda k: (k.parent.parent / "Yuki-sahte.AppImage").write_bytes(b"\x7fELF dlopen libfuse.so.2"),
        }
        for ad, boz in bozan.items():
            kok_kopya = Path(g) / f"k-{ad.split()[0]}"
            shutil.copytree(Path(g) / "dist", kok_kopya / "dist")
            kopya = kok_kopya / "dist/linux-unpacked/resources"
            boz(kopya)
            sonuc[f"M {ad}"] = None if paket_kapilari(kopya)[ad] else "kırıldı ama yakalanmadı"
    return _yaz("MUTASYON (kapı etkinliği)", sonuc)


def main() -> int:
    if "--mutasyon" in sys.argv:
        return 1 if mutasyon() else 0
    ayar = ayar_kapilari(YML.read_text(), DERLE.read_text(), json.loads(PJ.read_text()))
    ayar["A7 duzen"] = duzen_kapisi(RUNTIME_BETIK.read_text())
    kalan = _yaz("AYAR", ayar)
    if "--paket" in sys.argv:
        kalan += _yaz(f"PAKET ({ACIK})", paket_kapilari(ACIK))
    return 1 if kalan else 0


if __name__ == "__main__":
    sys.exit(main())
