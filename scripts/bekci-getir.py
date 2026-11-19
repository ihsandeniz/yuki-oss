#!/usr/bin/env python3
"""Süreç bekçisi ikililerini pakete hazırla (surec-bekcisi FAZ 5, 2026-10-08).

    python3 scripts/bekci-getir.py linux [--kaynak ../surec-bekcisi]   # cargo build --release + kopya
    python3 scripts/bekci-getir.py win --run <id>                       # CI artifact'ından .exe
    python3 scripts/bekci-getir.py kilitle                              # SURUM dosyasını ikililerden yaz
    python3 scripts/bekci-getir.py --check                              # ikililer SURUM'la tutuyor mu

Yerleşim: `electron/bekci-bin/{linux/yuki-bekci, win/yuki-bekci.exe}` (gitignore'da, ikili) +
`electron/bekci-bin/SURUM` (depoda: kaynak commit + iki ikilinin sha256'sı). electron-builder
bunları `resources/bekci/`'e koyar → `electron/bekci.js::bekciYolu`.

🔴 Neden SURUM depoda ve `shell_id`'de (`update_payload.py::KABUK_VARLIKLARI`): bekçi ikilisi
asar'ın DIŞINDA, `resources/` altında durur → delta yükü ona dokunamaz. Parmak izine girmezse
yeni bir bekçi müşteriye hiç ulaşmaz ve ekranda "güncellendi" yazar (2026-08-10 runtime dersi).
Bedeli: SURUM her değiştiğinde o sürüm herkese TAM indirme olur.

Windows ikilisi yerelde derlenmez (mingw kurulu değil): `ihsandeniz/yuki-bekci` CI'ı
windows-latest'te derleyip `yuki-bekci-windows` artifact'ı olarak yükler.
"""
from __future__ import annotations

import argparse
import hashlib
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

KOK = Path(__file__).resolve().parents[1]
HEDEF = KOK / "electron" / "bekci-bin"
LINUX = HEDEF / "linux" / "yuki-bekci"
WIN = HEDEF / "win" / "yuki-bekci.exe"
SURUM = HEDEF / "SURUM"
DEPO = "ihsandeniz/yuki-bekci"
ARTIFACT = "yuki-bekci-windows"


def sha(p: Path) -> str:
    return hashlib.sha256(p.read_bytes()).hexdigest()


def linux(kaynak: Path) -> None:
    subprocess.run(["cargo", "build", "--release"], cwd=kaynak, check=True)
    LINUX.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(kaynak / "target" / "release" / "yuki-bekci", LINUX)
    LINUX.chmod(0o755)  # AppImage'da +x düşerse bekciYolu X_OK'ta eski yola düşer
    print(f"✓ {LINUX.relative_to(KOK)} ({LINUX.stat().st_size} B)")


def win(run_id: str) -> None:
    with tempfile.TemporaryDirectory() as d:
        subprocess.run(["gh", "run", "download", run_id, "--repo", DEPO, "-n", ARTIFACT, "-D", d], check=True)
        exe = next(Path(d).rglob("yuki-bekci.exe"), None)
        if exe is None:
            sys.exit(f"✗ artifact'ta yuki-bekci.exe yok (run {run_id})")
        WIN.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(exe, WIN)
    print(f"✓ {WIN.relative_to(KOK)} ({WIN.stat().st_size} B)")


def kilitle(kaynak: Path) -> None:
    for p in (LINUX, WIN):
        if not p.is_file():
            sys.exit(f"✗ {p.relative_to(KOK)} yok — önce `linux` ve `win`")
    commit = subprocess.run(["git", "rev-parse", "HEAD"], cwd=kaynak, capture_output=True, text=True).stdout.strip()
    SURUM.write_text(
        f"kaynak {DEPO}@{commit or '?'}\n"
        f"linux {sha(LINUX)}\n"
        f"win {sha(WIN)}\n",
        encoding="utf-8",
    )
    print(f"✓ {SURUM.relative_to(KOK)} yazıldı — commit'le; shell_id değişir (sürüm TAM indirme olur)")


def denetle() -> int:
    if not SURUM.is_file():
        print("✗ bekci-bin/SURUM yok")
        return 1
    beklenen = dict(s.split(" ", 1) for s in SURUM.read_text(encoding="utf-8").splitlines() if " " in s)
    hata = 0
    for ad, p in (("linux", LINUX), ("win", WIN)):
        if not p.is_file():
            print(f"✗ {ad}: {p.relative_to(KOK)} yok")
            hata = 1
        elif sha(p) != beklenen.get(ad):
            print(f"✗ {ad}: ikili SURUM'daki özetle tutmuyor (yeniden getir ya da kilitle)")
            hata = 1
        else:
            print(f"✓ {ad}: {p.stat().st_size} B")
    if LINUX.is_file() and not LINUX.stat().st_mode & 0o111:
        print("✗ linux ikilisinin çalıştırma biti yok")
        hata = 1
    return hata


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("komut", nargs="?", choices=["linux", "win", "kilitle"])
    ap.add_argument("--kaynak", type=Path, default=KOK.parent / "surec-bekcisi")
    ap.add_argument("--run", help="win: yuki-bekci CI koşu numarası")
    ap.add_argument("--check", action="store_true")
    a = ap.parse_args()
    if a.check:
        return denetle()
    if a.komut == "linux":
        linux(a.kaynak)
    elif a.komut == "win":
        if not a.run:
            sys.exit("win için --run <id> gerekli (gh run list --repo ihsandeniz/yuki-bekci)")
        win(a.run)
    elif a.komut == "kilitle":
        kilitle(a.kaynak)
    else:
        ap.print_help()
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(main())
