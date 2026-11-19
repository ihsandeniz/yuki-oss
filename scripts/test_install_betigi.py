#!/usr/bin/env python3
"""install.sh kapıları — konteynersiz, ağsız, saniyeler içinde.

Gerçek kurulum (~1.3 GB) burada koşmaz; o, raporda docker'da ölçüldü. Bu test
yalnız betiğin koruma kapılarını sınar:
  1. sözdizimi (bash -n)
  2. tehlikeli önek (/, $HOME) → çıkış 2, hiçbir şey silinmez
  3. bilinmeyen seçenek → çıkış 2
  4. kaynakta requirements.txt yoksa → çıkış 1, önek oluşmaz, geçici klasör kalmaz
  5. --kaldir yalnız önek + başlatıcı + menü girdisini siler, ~/.yuki durur
  6. curl | bash önerisi yok; sudo yok
Çıkış 0 = hepsi geçti.
"""
import os, subprocess, sys, tarfile, tempfile, io
from pathlib import Path

BETIK = Path(os.environ.get("YUKI_INSTALL_SH", Path(__file__).with_name("install.sh")))
gecti = kaldi = 0

def kontrol(ad, kosul, detay=""):
    global gecti, kaldi
    if kosul: gecti += 1; print(f"  🟢 {ad}")
    else: kaldi += 1; print(f"  🔴 {ad} {detay}")

def kos(home, *arg):
    env = {"HOME": str(home), "PATH": os.environ["PATH"], "XDG_DATA_HOME": str(home / ".local/share")}
    return subprocess.run(["bash", str(BETIK), *arg], env=env, capture_output=True, text=True, timeout=60)

kontrol("sözdizimi", subprocess.run(["bash", "-n", str(BETIK)]).returncode == 0)
metin = BETIK.read_text()
kontrol("curl|bash önerisi yok", "| bash" not in metin and "|bash" not in metin)
kontrol("sudo komutu yok", not any(l.strip().startswith("sudo") for l in metin.splitlines()))

with tempfile.TemporaryDirectory() as t:
    home = Path(t) / "ev"; home.mkdir()
    nobet = home / "dokunma.txt"; nobet.write_text("x")
    r = kos(home, "--onek", "/")
    kontrol("önek / reddedilir", r.returncode == 2, r.stderr)
    r = kos(home, "--onek", str(home))
    kontrol("önek $HOME reddedilir", r.returncode == 2 and nobet.exists(), r.stderr)
    r = kos(home, "--onek", str(home) + "/")
    kontrol("önek $HOME/ reddedilir", r.returncode == 2 and nobet.exists(), r.stderr)
    r = kos(home, "--yok")
    kontrol("bilinmeyen seçenek → 2", r.returncode == 2)

    bos = Path(t) / "bos.tar.gz"
    with tarfile.open(bos, "w:gz") as tf:
        b = b"merhaba"; ti = tarfile.TarInfo("yuki-oss/README.md"); ti.size = len(b); tf.addfile(ti, io.BytesIO(b))
    onek = home / "kur"
    r = kos(home, "--onek", str(onek), "--kaynak", str(bos))
    artik = [p for p in home.iterdir() if ".yeni." in p.name]
    kontrol("eksik kaynak → 1, önek yok, artık yok", r.returncode == 1 and not onek.exists() and not artik, f"rc={r.returncode} {artik}")

    onek.mkdir(); (onek / "a").write_text("x")
    bin_ = home / ".local/bin"; bin_.mkdir(parents=True); (bin_ / "yuki").write_text("x"); (bin_ / "baska").write_text("x")
    veri = home / ".yuki"; veri.mkdir(); (veri / "hafiza.db").write_text("x")
    r = kos(home, "--onek", str(onek), "--kaldir")
    kontrol("--kaldir önek+başlatıcıyı siler", r.returncode == 0 and not onek.exists() and not (bin_ / "yuki").exists())
    kontrol("--kaldir kullanıcı verisine ve başka dosyaya dokunmaz", (veri / "hafiza.db").exists() and (bin_ / "baska").exists() and nobet.exists())

print(f"geçti {gecti} · kaldı {kaldi}")
sys.exit(1 if kaldi else 0)
