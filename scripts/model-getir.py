#!/usr/bin/env python3
"""model-getir.py — `electron/models-manifest.json`'daki bir model paketini indir + sha256 denetle + aç.

Model adresinin TEK kaynağı manifesttir. CI (`.github/workflows/pytest.yml`) ve yerel aynası
(`scripts/ci-yerel.sh`) URL/sha256'yı kendileri yazmaz, buradan alır; böylece paketler başka
bir sürüme taşındığında yalnız manifest değişir.

İndirme yolu:
  - `gh` kurulu ve kimlikli ise (CI'da `GH_TOKEN`, yerelde `gh auth login`) → `gh release download`.
    Depo gizliyken sürüm varlıkları anonim inmez; bu yol gizli depoda da çalışır.
  - yoksa düz HTTPS (depo herkese açıkken yeterli).

Kullanım:
    python3 scripts/model-getir.py embedding-onnx <hedef_dizin>     # indir + aç
    python3 scripts/model-getir.py embedding-onnx --sha              # yalnız sha256 bas
    python3 scripts/model-getir.py embedding-onnx --url              # yalnız adres bas
Seçenekler: --platform linux-x64 (çok platformlu paket) · --manifest <yol> · --gh-yok (düz HTTPS zorla)
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
import tarfile
import tempfile
import urllib.request
from pathlib import Path

KOK = Path(__file__).resolve().parents[1]
MANIFEST = KOK / "electron" / "models-manifest.json"
GH_URL = re.compile(r"^https://github\.com/([^/]+/[^/]+)/releases/download/([^/]+)/([^/]+)$")


class ModelHatasi(Exception):
    pass


def girdi(manifest: Path, model: str, platform: str | None) -> dict:
    data = json.loads(manifest.read_text(encoding="utf-8"))
    m = data.get("models", {}).get(model)
    if m is None:
        raise ModelHatasi(f"manifestte model yok: {model!r} (var: {sorted(data.get('models', {}))})")
    if "assets" in m:
        if not platform:
            raise ModelHatasi(f"{model} platforma özel; --platform ver ({sorted(m['assets'])})")
        m = m["assets"].get(platform)
        if m is None:
            raise ModelHatasi(f"{model} için {platform} paketi yok")
    if not m.get("url") or not m.get("sha256") or m["sha256"] == "TBD":
        raise ModelHatasi(f"{model}: url/sha256 eksik")
    return m


def gh_komutu(url: str, cikti: Path) -> list[str] | None:
    """GitHub sürüm adresi → `gh release download` komutu; başka adres → None."""
    e = GH_URL.match(url)
    if not e:
        return None
    depo, etiket, varlik = e.groups()
    return ["gh", "release", "download", etiket, "-R", depo, "-p", varlik, "-O", str(cikti), "--clobber"]


def gh_kullanilabilir() -> bool:
    if not shutil.which("gh"):
        return False
    if os.environ.get("GH_TOKEN") or os.environ.get("GITHUB_TOKEN"):
        return True
    return subprocess.run(["gh", "auth", "status"], capture_output=True).returncode == 0


def sha256(yol: Path) -> str:
    h = hashlib.sha256()
    with yol.open("rb") as f:
        for parca in iter(lambda: f.read(1 << 20), b""):
            h.update(parca)
    return h.hexdigest()


def indir(url: str, cikti: Path, gh: bool) -> str:
    komut = gh_komutu(url, cikti) if gh else None
    if komut:
        r = subprocess.run(komut, capture_output=True, text=True)
        if r.returncode != 0:
            raise ModelHatasi(f"gh release download başarısız ({r.returncode}): {r.stderr.strip()[:400]}")
        return "gh"
    with urllib.request.urlopen(url, timeout=120) as yanit, cikti.open("wb") as f:
        shutil.copyfileobj(yanit, f)
    return "https"


def getir(manifest: Path, model: str, hedef: Path, platform: str | None = None, gh: bool | None = None) -> str:
    m = girdi(manifest, model, platform)
    hedef.mkdir(parents=True, exist_ok=True)
    gh = gh_kullanilabilir() if gh is None else gh
    with tempfile.TemporaryDirectory(dir=hedef) as gecici:
        paket = Path(gecici) / "paket.tgz"
        yol = indir(m["url"], paket, gh)
        bulunan = sha256(paket)
        if bulunan != m["sha256"]:
            raise ModelHatasi(f"sha256 tutmuyor: beklenen {m['sha256']}, gelen {bulunan} ({m['url']})")
        with tarfile.open(paket, "r:gz") as tar:
            tar.extractall(hedef, filter="data")
    return yol


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("model")
    ap.add_argument("hedef", nargs="?", type=Path)
    ap.add_argument("--platform")
    ap.add_argument("--manifest", type=Path, default=MANIFEST)
    ap.add_argument("--sha", action="store_true")
    ap.add_argument("--url", action="store_true")
    ap.add_argument("--gh-yok", action="store_true")
    a = ap.parse_args(argv)
    try:
        if a.sha or a.url:
            m = girdi(a.manifest, a.model, a.platform)
            print(m["sha256"] if a.sha else m["url"])
            return 0
        if a.hedef is None:
            ap.error("hedef dizin gerekli (ya da --sha / --url)")
        yol = getir(a.manifest, a.model, a.hedef, a.platform, gh=False if a.gh_yok else None)
        print(f"✓ {a.model} → {a.hedef} ({yol}, sha256 doğru)")
        return 0
    except ModelHatasi as e:
        print(f"❌ {e}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
