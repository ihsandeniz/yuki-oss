#!/usr/bin/env python3
"""Profil adı kapısı: açık kaynak Yuki kişisel AliceAi ile aynı veri klasörünü KULLANAMAZ.

Electron userData'yı `package.json` `name`'inden kurar (`productName` asar'da yok):
`name: alice-ai` → `~/.config/alice-ai` = kişisel AliceAi'nin klasörü. İki uygulama
aynı makinede birbirinin .env'ini, kilidini, sohbet geçmişini ezer (2026-10-18 deneme raporu 🔴 2).

    python3 scripts/test_profil_adi.py
"""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path

KOK = Path(__file__).resolve().parents[1]
AD = "yuki-oss"
YASAK = "alice-ai"
hatalar: list[str] = []


def kontrol(kosul: bool, mesaj: str) -> None:
    print(("✓ " if kosul else "✗ ") + mesaj)
    if not kosul:
        hatalar.append(mesaj)


pj = json.loads((KOK / "electron/package.json").read_text())
kontrol(pj.get("name") == AD, f"electron/package.json name = {AD!r} (bulunan {pj.get('name')!r})")
kontrol("productName" not in pj or YASAK not in pj["productName"].lower(), "package.json productName alice-ai değil")

for yml in sorted((KOK / "electron").glob("electron-builder*.yml")):
    m = re.search(r"^appId:\s*(\S+)", yml.read_text(), re.M)
    kontrol(bool(m) and YASAK not in m.group(1), f"{yml.name} appId alice-ai içermiyor ({m.group(1) if m else 'yok'})")

baslatici = (KOK / "electron/launcher/yuki.sh").read_text()
kontrol(f'"$DIR/{AD}"' in baslatici, f"launcher/yuki.sh ikili adı {AD}")

kontrol(f"PENCERE_SINIFI = '{AD}'" in (KOK / "electron/pencere-yetenek.js").read_text(),
        f"pencere sınıfı {AD}")
kontrol(f'SERVIS = "{AD}"' in (KOK / "backend/app/services/sirlar.py").read_text(),
        f"anahtarlık servis adı {AD} (eski yuki-urun kaydı sızmasın)")

# Çalışan kodda kişisel veri klasörüne giden varsayılan yol kalmasın
yol_deseni = re.compile(r'"\.config"\s*/\s*"alice-ai"|\.config/alice-ai')
for py in sorted((KOK / "backend/app").rglob("*.py")):
    for i, satir in enumerate(py.read_text(encoding="utf-8").splitlines(), 1):
        if yol_deseni.search(satir):
            kontrol(False, f"{py.relative_to(KOK)}:{i} kişisel veri klasörüne yol: {satir.strip()[:80]}")

if hatalar:
    sys.exit(f"\n✗ {len(hatalar)} kapı kaldı")
print("\n✓ profil adı kapısı geçti")
