#!/usr/bin/env python3
"""Model kaynağı kapısı: model paketleri YALNIZ bu deponun kendi sürümünden iner.

Neden var: gömme / ses tanıma / yüz kütüphanesi paketleri eskiden başka bir deponun
sürümünden iniyordu. O depo gizlenince (sürüm varlıkları anonim inmez) üç yer birden
sessizce kırılır: CI'ın pytest işi, yerel CI aynası ve yeni kullanıcının ilk model
indirmesi. Bu kapı adresin tek kaynakta (manifest) ve bu depoda kalmasını kilitler.

    python3 scripts/test_model_kaynagi.py        # KAPI + MUTASYON, çıkış 0 = geçti
"""
from __future__ import annotations

import hashlib
import importlib.util
import io
import json
import os
import re
import shutil
import stat
import sys
import tarfile
import tempfile
from pathlib import Path

KOK = Path(__file__).resolve().parents[1]
DEPO = "ihsandeniz/yuki-oss"
TABAN = f"https://github.com/{DEPO}/releases/download"
GH_URL = re.compile(r"^https://github\.com/([^/]+/[^/]+)/releases/download/([^/]+)/([^/]+)$")
SABIT_ADRES = re.compile(r"releases/download/v[0-9.]+-models|embedding-onnx-int8\.tar\.gz")


def _getir_modulu(kok: Path):
    spec = importlib.util.spec_from_file_location("_model_getir", kok / "scripts" / "model-getir.py")
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


def _girdiler(manifest: dict):
    for ad, m in manifest["models"].items():
        if "assets" in m:
            for plat, a in m["assets"].items():
                yield f"{ad}/{plat}", a
        else:
            yield ad, m


# ── kapılar (her biri hata listesi döner; boş = geçti) ──────────────────────────────

def kapi_manifest_bu_depoda(kok: Path) -> list[str]:
    h = []
    man = json.loads((kok / "electron/models-manifest.json").read_text(encoding="utf-8"))
    if man.get("releaseBase") != TABAN:
        h.append(f"releaseBase {man.get('releaseBase')!r} ≠ {TABAN!r}")
    for ad, a in _girdiler(man):
        url = a.get("url", "")
        e = GH_URL.match(url)
        if not e or e.group(1) != DEPO:
            h.append(f"{ad}: url bu depoda değil: {url}")
        elif e.group(3) != a.get("asset"):
            h.append(f"{ad}: url varlık adı {e.group(3)!r} ≠ asset {a.get('asset')!r}")
        if not re.fullmatch(r"[0-9a-f]{64}", a.get("sha256", "")):
            h.append(f"{ad}: sha256 yok/bozuk")
    return h


def kapi_ci_adresi_manifestten(kok: Path) -> list[str]:
    h = []
    for ad in (".github/workflows/pytest.yml", "scripts/ci-yerel.sh"):
        metin = (kok / ad).read_text(encoding="utf-8")
        for i, s in enumerate(metin.splitlines(), 1):
            if SABIT_ADRES.search(s) or re.search(r"\b[0-9a-f]{64}\b", s):
                h.append(f"{ad}:{i} sabit model adresi/sha256 (manifestten okunmalı)")
        if not re.search(r'model-getir\.py"?\s+embedding-onnx\s+"?\$', metin):   # --sha değil, gerçek indirme
            h.append(f"{ad}: model-getir.py ile indirmiyor")
    return h


def kapi_ci_token(kok: Path) -> list[str]:
    """Depo gizliyken sürüm varlığı ancak kimlikle iner: indirme adımında GH_TOKEN + contents: read."""
    metin = (kok / ".github/workflows/pytest.yml").read_text(encoding="utf-8")
    h = []
    if not re.search(r"^permissions:\s*\n\s+contents:\s*read", metin, re.M):
        h.append("pytest.yml: 'permissions: contents: read' yok")
    adim = re.search(r"- name: Gömme modelini indir.*?(?=\n      - name:|\Z)", metin, re.S)
    if not adim or "GH_TOKEN: ${{ github.token }}" not in adim.group(0):
        h.append("pytest.yml: indirme adımında GH_TOKEN yok (gizli depoda 404)")
    return h


def _paket(yol: Path) -> str:
    veri = b"model"
    with tarfile.open(yol, "w:gz") as t:
        bilgi = tarfile.TarInfo("embedding-onnx/model_int8.onnx")
        bilgi.size = len(veri)
        t.addfile(bilgi, io.BytesIO(veri))
    return hashlib.sha256(yol.read_bytes()).hexdigest()


def kapi_indirici(kok: Path) -> list[str]:
    """Sahte yürütücüyle: düz yol sha256 denetliyor mu, gh yolu doğru komutu kuruyor mu."""
    mg = _getir_modulu(kok)
    h = []
    with tempfile.TemporaryDirectory() as d:
        d = Path(d)
        paket = d / "embedding-onnx-int8.tar.gz"
        sha = _paket(paket)
        man = d / "m.json"

        def yaz(url, s):
            man.write_text(json.dumps({"models": {"embedding-onnx": {"url": url, "sha256": s}}}))

        # 1) düz yol, sha doğru → açılır
        yaz(paket.as_uri(), sha)
        try:
            mg.getir(man, "embedding-onnx", d / "h1", gh=False)
            if not (d / "h1/embedding-onnx/model_int8.onnx").is_file():
                h.append("indirici: paket açılmadı")
        except Exception as e:  # noqa: BLE001
            h.append(f"indirici: doğru sha ile düştü: {e}")
        # 2) sha yanlış → reddeder ve hiçbir şey açmaz
        yaz(paket.as_uri(), "0" * 64)
        try:
            mg.getir(man, "embedding-onnx", d / "h2", gh=False)
            h.append("indirici: yanlış sha256'yı KABUL etti")
        except mg.ModelHatasi:
            if (d / "h2/embedding-onnx").exists():
                h.append("indirici: sha tutmadığı halde paketi açtı")
        # 3) gh yolu: sahte `gh` PATH'te, aldığı argümanları kaydeder ve paketi -O'ya kopyalar
        bin_ = d / "bin"
        bin_.mkdir()
        kayit = d / "gh-args.txt"
        sahte = bin_ / "gh"
        sahte.write_text(
            "#!/usr/bin/env python3\nimport sys, shutil\n"
            f"open({str(kayit)!r}, 'w').write(' '.join(sys.argv[1:]))\n"
            "a = sys.argv[1:]\n"
            f"shutil.copy({str(paket)!r}, a[a.index('-O') + 1])\n"
        )
        sahte.chmod(sahte.stat().st_mode | stat.S_IEXEC)
        yaz(f"{TABAN}/v0.4.0-models/embedding-onnx-int8.tar.gz", sha)
        eski = os.environ.get("PATH", "")
        os.environ["PATH"] = f"{bin_}{os.pathsep}{eski}"
        try:
            yol = mg.getir(man, "embedding-onnx", d / "h3", gh=True)
            args = kayit.read_text() if kayit.exists() else ""
            beklenen = f"release download v0.4.0-models -R {DEPO} -p embedding-onnx-int8.tar.gz"
            if yol != "gh" or not args.startswith(beklenen):
                h.append(f"indirici gh yolu: komut {args!r}, beklenen {beklenen!r}…")
            if not (d / "h3/embedding-onnx/model_int8.onnx").is_file():
                h.append("indirici gh yolu: paket açılmadı")
        except Exception as e:  # noqa: BLE001
            h.append(f"indirici gh yolu düştü: {e}")
        finally:
            os.environ["PATH"] = eski
        # 4) --sha gerçek manifestteki gömme sha'sını basar (CI önbellek anahtarı buna bağlı)
        gercek = json.loads((kok / "electron/models-manifest.json").read_text())["models"]["embedding-onnx"]["sha256"]
        if mg.girdi(kok / "electron/models-manifest.json", "embedding-onnx", None)["sha256"] != gercek:
            h.append("indirici: --sha manifestle tutmuyor")
    return h


def kapi_eski_depo_adi_yok(kok: Path) -> list[str]:
    desen = re.compile(r"(?i:yuki" + r"[-_]ai)(?![a-z0-9])")
    h = []
    for ad in (".github/workflows/pytest.yml", "scripts/ci-yerel.sh", "electron/models-manifest.json",
               "THIRD_PARTY_LICENSES.md", "backend/tests/conftest.py", "scripts/model-getir.py"):
        for i, s in enumerate((kok / ad).read_text(encoding="utf-8").splitlines(), 1):
            if desen.search(s):
                h.append(f"{ad}:{i} eski depo adı")
    return h


KAPILAR = [kapi_manifest_bu_depoda, kapi_ci_adresi_manifestten, kapi_ci_token, kapi_indirici, kapi_eski_depo_adi_yok]
ESKI = "yuki-" + "ai"


# ── mutasyon: her kapıyı bir kez bilerek kır, yakalandığını gör ───────────────────────

def _degistir(eski: str, yeni: str, ad: str):
    def m(kok: Path):
        p = kok / ad
        s = p.read_text(encoding="utf-8")
        assert eski in s, f"mutasyon hedefi yok: {ad}: {eski!r}"
        p.write_text(s.replace(eski, yeni, 1), encoding="utf-8")
    return m


MUTASYONLAR = [
    ("manifest url eski depoya", kapi_manifest_bu_depoda,
     _degistir("/yuki-oss/releases/download/v0.4.0-models/whisper", f"/{ESKI}/releases/download/v0.4.0-models/whisper",
               "electron/models-manifest.json")),
    ("releaseBase eski depoya", kapi_manifest_bu_depoda,
     _degistir('"releaseBase": "https://github.com/ihsandeniz/yuki-oss', f'"releaseBase": "https://github.com/ihsandeniz/{ESKI}',
               "electron/models-manifest.json")),
    ("pytest.yml'ye sabit adres", kapi_ci_adresi_manifestten,
     _degistir("  ONNX_KOK:", f"  ONNX_URL: {TABAN}/v0.4.0-models/embedding-onnx-int8.tar.gz\n  ONNX_KOK:",
               ".github/workflows/pytest.yml")),
    ("ci-yerel.sh curl'e dönüş", kapi_ci_adresi_manifestten,
     _degistir('"$PY" "$IS/kod/scripts/model-getir.py" embedding-onnx "$ONBELLEK',
               'curl -fsSL -o x.tgz "$URL" # "$ONBELLEK', "scripts/ci-yerel.sh")),
    ("indirme adımında GH_TOKEN yok", kapi_ci_token,
     _degistir("          GH_TOKEN: ${{ github.token }}\n", "", ".github/workflows/pytest.yml")),
    ("permissions bloğu yok", kapi_ci_token,
     _degistir("permissions:\n  contents: read\n", "", ".github/workflows/pytest.yml")),
    ("indirici sha denetimini atlıyor", kapi_indirici,
     _degistir('if bulunan != m["sha256"]:', "if False:", "scripts/model-getir.py")),
    ("indirici gh'ya yanlış depo", kapi_indirici,
     _degistir('"-R", depo', '"-R", "baska/depo"', "scripts/model-getir.py")),
    ("lisans metninde eski depo", kapi_eski_depo_adi_yok,
     _degistir("release of this repository", f"release of `ihsandeniz/{ESKI}`", "THIRD_PARTY_LICENSES.md")),
]
KOPYA = [".github/workflows/pytest.yml", "scripts/ci-yerel.sh", "electron/models-manifest.json",
         "THIRD_PARTY_LICENSES.md", "backend/tests/conftest.py", "scripts/model-getir.py"]


def main() -> int:
    gecti = kaldi = 0
    print("── KAPI")
    for k in KAPILAR:
        h = k(KOK)
        print(("✓ " if not h else "🔴 ") + k.__name__ + ("" if not h else f": {h[:5]}"))
        gecti += not h
        kaldi += bool(h)
    print(f"KAPI: {gecti} geçti / {kaldi} kaldı")

    mg = mk = 0
    print("── MUTASYON")
    for ad, kapi, mut in MUTASYONLAR:
        with tempfile.TemporaryDirectory() as d:
            kopya = Path(d)
            for y in KOPYA:
                (kopya / y).parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(KOK / y, kopya / y)
            mut(kopya)
            yakaladi = bool(kapi(kopya))
        print(("✓ yakalandı: " if yakaladi else "🔴 KAÇTI: ") + ad)
        mg += yakaladi
        mk += not yakaladi
    print(f"MUTASYON: {mg} yakalandı / {mk} kaçtı")
    return 0 if kaldi == 0 and mk == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
