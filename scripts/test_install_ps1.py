#!/usr/bin/env python3
"""install.ps1 kapıları — ağsız, gerçek kurulum yok (o ~1.3 GB; gerçek Windows'ta ölçülür).

PowerShell: yerelde `pwsh` varsa o, yoksa `mcr.microsoft.com/powershell` kabı (docker/podman).
Linux'taki pwsh Windows değildir: yol ve kısayol davranışı değil, yalnız koruma kapıları sınanır:
  1. iex / Invoke-Expression / boru-ile-çalıştır önerisi yok; yönetici (RunAs) istemez
  2. tehlikeli önek (kök, kullanıcı klasörü, LOCALAPPDATA) → çıkış 2, hiçbir şey silinmez
  3. olmayan kaynak → 2, önek ve geçici klasör oluşmaz
  4. kaynakta requirements.txt yoksa → 1, önek yok, geçici klasör kalmaz
  5. -Kaldir yalnız öneki siler, ~/.yuki ve komşu dosyalar durur
Çıkış 0 = hepsi geçti · 2 = PowerShell bulunamadı.
"""
import io, os, shutil, subprocess, sys, tarfile, tempfile
from pathlib import Path

BETIK = Path(os.environ.get("YUKI_INSTALL_PS1", Path(__file__).with_name("install.ps1"))).resolve()
IMAJ = "mcr.microsoft.com/powershell:lts-ubuntu-22.04"
gecti = kaldi = 0

def kontrol(ad, kosul, detay=""):
    global gecti, kaldi
    if kosul: gecti += 1; print(f"  🟢 {ad}")
    else: kaldi += 1; print(f"  🔴 {ad} {detay}")

metin = BETIK.read_text(encoding="utf-8")
alt = metin.lower()
kontrol("iex/Invoke-Expression yok", "invoke-expression" not in alt and not any(
    t in alt for t in (" iex ", "| iex", "|iex", "iex(")))
kontrol("yönetici istemez (RunAs yok)", "runas" not in alt and "requires -runasadministrator" not in alt)

kap = None
if shutil.which("pwsh"):
    calistir = lambda ev, arg: subprocess.run(["pwsh", "-NoProfile", "-File", str(BETIK), *arg],
        env={"HOME": str(ev), "PATH": os.environ["PATH"], "LOCALAPPDATA": str(ev / "AppData/Local")},
        capture_output=True, text=True, timeout=120)
    yol = lambda p: str(p)
else:
    kap = os.environ.get("YUKI_KONTEYNER") or ("podman" if shutil.which("podman") else "docker" if shutil.which("docker") else None)
    if not kap: print("🔴 pwsh da docker/podman da yok"); sys.exit(2)

with tempfile.TemporaryDirectory() as t:
    t = Path(t); ev = t / "ev"; ev.mkdir(); (ev / "AppData/Local").mkdir(parents=True)
    if kap:
        # Kapta ev = /ev (bağlı klasör), betik /b/install.ps1. Kullanıcı kimliği eşlenir ki silmeler denensin.
        def calistir(_ev, arg):
            return subprocess.run([kap, "run", "--rm", "--network=none", "-u", f"{os.getuid()}:{os.getgid()}",
                "-e", "HOME=/ev", "-e", "LOCALAPPDATA=/ev/AppData/Local", "-v", f"{t}/ev:/ev",
                "-v", f"{BETIK}:/b/install.ps1:ro", IMAJ, "pwsh", "-NoProfile", "-File", "/b/install.ps1", *arg],
                capture_output=True, text=True, timeout=180)
        yol = lambda p: "/ev/" + str(p.relative_to(ev)) if p != ev else "/ev"
    nobet = ev / "dokunma.txt"; nobet.write_text("x")

    for ad, onek in (("kök", "/"), ("kullanıcı klasörü", yol(ev)), ("LOCALAPPDATA", yol(ev / "AppData/Local")),
                     ("LOCALAPPDATA/ (sonda ayraç)", yol(ev / "AppData/Local") + "/")):
        r = calistir(ev, ["-Onek", onek, "-Kaldir"])
        kontrol(f"önek {ad} reddedilir → 2", r.returncode == 2 and nobet.exists() and (ev / "AppData/Local").exists(),
                f"rc={r.returncode} {r.stderr[-200:]}")

    onek = ev / "kur"
    r = calistir(ev, ["-Onek", yol(onek), "-Kaynak", yol(ev / "yok.tar.gz")])
    artik = [p for p in ev.iterdir() if ".yeni." in p.name]
    kontrol("olmayan kaynak → 2 (kaynak yok), artık yok", r.returncode == 2 and "kaynak yok" in r.stderr and not onek.exists() and not artik, f"rc={r.returncode} {artik}")

    bos = ev / "bos.tar.gz"
    with tarfile.open(bos, "w:gz") as tf:
        b = b"merhaba"; ti = tarfile.TarInfo("yuki-oss/README.md"); ti.size = len(b); tf.addfile(ti, io.BytesIO(b))
    # Python bulunamazsa 2 ile erken çıkar; kapta python yok → bu kapıyı yalnız python varsa sına.
    r = calistir(ev, ["-Onek", yol(onek), "-Kaynak", yol(bos)])
    artik = [p for p in ev.iterdir() if ".yeni." in p.name]
    if "Python 3.12" in r.stderr:
        kontrol("python yoksa → 2, artık yok", r.returncode == 2 and not onek.exists() and not artik, f"rc={r.returncode}")
    else:
        kontrol("eksik kaynak → 1, önek yok, artık yok", r.returncode == 1 and not onek.exists() and not artik,
                f"rc={r.returncode} {artik} {r.stderr[-200:]}")

    onek.mkdir(); (onek / "a").write_text("x")
    veri = ev / ".yuki"; veri.mkdir(); (veri / "hafiza.db").write_text("x")
    komsu = ev / "AppData/Local/Baska"; komsu.mkdir(); (komsu / "f").write_text("x")
    r = calistir(ev, ["-Onek", yol(onek), "-Kaldir"])
    kontrol("-Kaldir öneki siler", r.returncode == 0 and not onek.exists(), f"rc={r.returncode} {r.stderr[-200:]}")
    kontrol("-Kaldir veriye/komşuya dokunmaz", (veri / "hafiza.db").exists() and (komsu / "f").exists() and nobet.exists())

print(f"geçti {gecti} · kaldı {kaldi}")
sys.exit(1 if kaldi else 0)
