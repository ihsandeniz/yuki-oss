"""electron-builder altındaki minimatch kopyaları açıklı sürümde kalmasın (GHSA-g3hv-75wg-m249).

`electron/package.json` `overrides` 9.x ve 10.x kopyalarını 11.0.8+'ya taşır. Kilit dosyası
yeniden üretilirken override düşerse (ör. `npm install` ile elle silinirse) bu test kırılır.
3.x ve 5.x kopyaları bilerek yerinde: override yalnız iki açıklı dalı hedefliyor.
Ağ gerekmez: yalnız `electron/package-lock.json` okunur.
"""
from __future__ import annotations

import json
from pathlib import Path

KOK = Path(__file__).resolve().parents[2]
KILIT = KOK / "electron" / "package-lock.json"
PAKET = KOK / "electron" / "package.json"


def _surum(s: str) -> tuple[int, ...]:
    return tuple(int(p) for p in s.split("-")[0].split("."))


def _minimatchler() -> dict[str, str]:
    paketler = json.loads(KILIT.read_text(encoding="utf-8"))["packages"]
    return {yol: v["version"] for yol, v in paketler.items()
            if yol.endswith("node_modules/minimatch") and "version" in v}


def test_kilitte_minimatch_var():
    # Boş sonuç = test sessizce yeşil; ağaçta en az bir kopya olmalı.
    assert _minimatchler(), "kilit dosyasında minimatch bulunamadı"


def test_acikli_dallar_kilitte_yok():
    kotu = {yol: s for yol, s in _minimatchler().items()
            if _surum(s)[0] in (9, 10) or (_surum(s)[0] == 11 and _surum(s) < (11, 0, 8))}
    assert not kotu, f"açıklı minimatch kopyası: {kotu}"


def test_override_paket_json_da():
    ov = json.loads(PAKET.read_text(encoding="utf-8")).get("overrides", {})
    assert ov.get("minimatch@^10.2.5") and ov.get("minimatch@^9.0.3"), ov
