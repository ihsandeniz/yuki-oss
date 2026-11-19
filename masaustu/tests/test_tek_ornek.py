#!/usr/bin/env python3
"""Tek örnek kilidi: elle run.sh + Yuki'den açılış aynı anda iki Yuki açmasın.

Ekrana bir şey AÇILMAZ: `XDG_RUNTIME_DIR` tmp'ye çevrilir, WAYLAND_DISPLAY orada olmayan bir sokete gösterir;
masaustu.py kilidi göremeyince pencere kurmadan 5 ile çıkmalı.
Kullanım: python3 tests/test_tek_ornek.py
"""
import os
import subprocess
import sys
import tempfile
import time
from pathlib import Path

KOK = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(KOK))
import tek_ornek  # noqa: E402

gecti = kaldi = 0


def kontrol(ad, kosul):
    global gecti, kaldi
    if kosul:
        gecti += 1
        print("✓", ad)
    else:
        kaldi += 1
        print("✗", ad)


with tempfile.TemporaryDirectory() as d:
    d = Path(d)
    f, pid = tek_ornek.al(d)
    kontrol("ilk al() kilidi verir, PID dosyası bizim", f is not None and pid == os.getpid()
            and (d / tek_ornek.PID_ADI).read_text() == str(os.getpid()))
    kontrol("tutuluyor_mu: başka açık dosya kilidi görür", tek_ornek.tutuluyor_mu(d) == (True, os.getpid()))

    # ikinci süreç alamaz, sahibin PID'ini görür
    kod = ("import sys; sys.path.insert(0, %r); import tek_ornek, pathlib; "
           "f, p = tek_ornek.al(pathlib.Path(%r)); print('YOK' if f is None else 'VAR', p)") % (str(KOK), str(d))
    cikti = subprocess.run([sys.executable, "-c", kod], capture_output=True, text=True, timeout=10).stdout.split()
    kontrol("ikinci süreç kilidi alamaz, sahibi görür", cikti == ["YOK", str(os.getpid())])

    # masaustu.py: kilit tutulurken pencere kurmadan 5 ile çıkar
    env = {**os.environ, "XDG_RUNTIME_DIR": str(d), "WAYLAND_DISPLAY": "olmayan-soket"}
    t0 = time.monotonic()
    vrm = d / "k.vrm"                                # model kapısı kilitten önce: sahte .vrm
    vrm.write_bytes(b"glTF")
    r = subprocess.run([sys.executable, str(KOK / "masaustu.py"), "--model", str(vrm)], env=env, capture_output=True, text=True, timeout=30)
    kontrol(f"masaustu.py zaten açıkken 5 ile çıkar ({r.returncode}, {time.monotonic() - t0:.1f} sn)",
            r.returncode == 5 and "zaten açık" in r.stderr and str(os.getpid()) in r.stderr)

    tek_ornek.birak(f, d)
    kontrol("birak(): PID dosyası silinir, kilit boşalır",
            not (d / tek_ornek.PID_ADI).exists() and tek_ornek.tutuluyor_mu(d) == (False, None))

    # süreç ölünce kilit kendiliğinden boşalır (bayat kilit yok)
    p = subprocess.Popen([sys.executable, "-c", kod.replace("print(", "import time; time.sleep(30); print(")])
    t0 = time.monotonic()
    while time.monotonic() - t0 < 5 and not tek_ornek.tutuluyor_mu(d)[0]:
        time.sleep(0.05)
    kontrol("başka süreç tutarken görülür", tek_ornek.tutuluyor_mu(d) == (True, p.pid))
    p.kill()
    p.wait(5)
    kontrol("süreç öldürülünce (SIGKILL) kilit boşalır", tek_ornek.tutuluyor_mu(d)[0] is False)
    f2, pid2 = tek_ornek.al(d)
    kontrol("bayat PID dosyasına rağmen yeniden alınır", f2 is not None and pid2 == os.getpid())
    tek_ornek.birak(f2, d)

    # --kuru kilit almaz (testler ve ölçümler gerçek örnekle yan yana koşabilsin)
    kontrol("--kuru yolunda kilit yok", "if not arg.kuru:" in (KOK / "masaustu.py").read_text())

print(f"\n{gecti}/{gecti + kaldi} geçti")
sys.exit(1 if kaldi else 0)
