#!/usr/bin/env python3
"""Masaüstü Yuki ses/konuşma — ekrana çıkmadan.

Kök neden: komutlar olay akışından koşuyor (evaluate_javascript donma yaptığı için kaldırıldı) ve
kullanıcı hareketi sayılmıyor → WebKit'in otomatik oynatma kuralı AudioContext'i 'suspended' bırakıyor, resume()
dönmüyordu: Yuki ağzını oynatıp SESSİZ kalıyordu. Burada ölçülen: kurulan WebView'in otomatik oynatma kuralı ALLOW,
medya kullanıcı hareketi istemiyor; log eki ses sayaçlarını basıyor. Kurulan WebView ölçümü kullanıcının kendi VRM'ini ister: `YUKI_TEST_VRM=/yol/model.vrm` yoksa atlanır.

Kullanım: python3 tests/test_konusma.py
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

KOK = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(KOK))
from davranis import ses_ozeti  # noqa: E402

gecti = kaldi = 0


def kontrol(ad: str, kosul: bool, ayrinti: str = "") -> None:
    global gecti, kaldi
    if kosul:
        gecti += 1
        print("  ✓", ad)
    else:
        kaldi += 1
        print("  ✗", ad, ayrinti)


def main() -> int:
    print("— log eki")
    kontrol("bag yoksa boş", ses_ozeti(None) == "" and ses_ozeti({"x": 1}) == "")
    kontrol("sayaçlar basılır", ses_ozeti({"sesSay": {"cal": 2, "sessiz": 5, "hata": 0}}) == " · ses 2/5/0 çal/sessiz/hata")
    print("— kurulan WebView (kuru)")
    vrm = os.environ.get("YUKI_TEST_VRM")
    if not vrm:
        print("  – atlandı: YUKI_TEST_VRM yok (depoda model bulunmaz)")
    for kip in ("tam",) if vrm else ():
        r = subprocess.run([sys.executable, str(KOK / "masaustu.py"), "--kuru", "--model", vrm, "--sure", "2", "--tezgah", "0",
                            "--baglantisiz"], capture_output=True, text=True, timeout=120)
        try:
            o = json.loads(r.stdout.strip().splitlines()[-1])
        except (ValueError, IndexError):
            kontrol(f"{kip}: JSON özet", False, r.stderr[-300:])
            continue
        kontrol(f"{kip}: otomatik oynatma ALLOW (ses kullanıcı hareketi beklemeden başlar)",
                o.get("otomatik_oynatma") == "allow", str(o.get("otomatik_oynatma")))
        kontrol(f"{kip}: medya kullanıcı hareketi istemiyor", o.get("ses_hareket_ister") is False, str(o.get("ses_hareket_ister")))
    print(f"\n{gecti} geçti · {kaldi} kaldı")
    return 1 if kaldi else 0


if __name__ == "__main__":
    sys.exit(main())
