"""Sürüm numarası tek — mekanik bekçi (2026-11-02, ilk açık sürüm 1.0.0).

NEDEN VAR: sürüm beş yerde yazılı (electron/package.json, package-lock.json ×2,
health.py APP_VERSION, CHANGELOG başlığı, README rozet/metin). Ön yüz sürümü
package.json'dan (Electron) ya da /health'ten okur; biri geride kalırsa kullanıcı
iki farklı sayı görür. Eski ürün dönemi 0.8.x da kullanıcıya görünen yere dönmesin.
"""
from __future__ import annotations

import json
import re
from pathlib import Path

KOK = Path(__file__).resolve().parents[2]


def _app_version() -> str:
    m = re.search(r'^APP_VERSION\s*=\s*"([\d.]+)"',
                  (KOK / "backend" / "app" / "services" / "health.py").read_text(encoding="utf-8"), re.M)
    assert m, "health.py'de APP_VERSION bulunamadı"
    return m.group(1)


def test_semver_bicimi():
    assert re.fullmatch(r"\d+\.\d+\.\d+", _app_version())


def test_electron_paketi_ayni():
    pj = json.loads((KOK / "electron" / "package.json").read_text(encoding="utf-8"))
    assert pj["version"] == _app_version(), "electron/package.json ≠ APP_VERSION"


def test_package_lock_ayni():
    lk = json.loads((KOK / "electron" / "package-lock.json").read_text(encoding="utf-8"))
    v = _app_version()
    assert lk["version"] == v, "package-lock.json üst sürüm ≠ APP_VERSION"
    assert lk["packages"][""]["version"] == v, "package-lock.json packages[''] ≠ APP_VERSION"


def test_changelog_ilk_baslik_bu_surum():
    metin = (KOK / "CHANGELOG.md").read_text(encoding="utf-8")
    m = re.search(r"^## \[([^\]]+)\]", metin, re.M)
    assert m, "CHANGELOG'da sürüm başlığı yok"
    assert m.group(1) == _app_version(), f"CHANGELOG ilk başlığı [{m.group(1)}] ≠ APP_VERSION"
    assert "DRAFT" not in metin, "CHANGELOG'da taslak notu kaldı"


def test_readme_rozet_ve_metin():
    metin = (KOK / "README.md").read_text(encoding="utf-8")
    v = _app_version()
    assert f"badge/version-{v}-" in metin, "README sürüm rozeti ≠ APP_VERSION"
    assert f"**Version {v}**" in metin, "README İngilizce durum metni ≠ APP_VERSION"
    assert f"sürüm **{v}**" in metin, "README Türkçe durum metni ≠ APP_VERSION"


GORUNEN = [KOK / "README.md", KOK / "CHANGELOG.md", KOK / "electron" / "package.json"]


def _gorunen_dosyalar():
    yield from GORUNEN
    for kok in (KOK / "docs", KOK / "frontend"):
        for p in kok.rglob("*"):
            if p.suffix in {".md", ".html", ".js", ".json", ".css"} and "vendor" not in p.parts and "tests" not in p.parts:
                yield p


def test_eski_urun_surumu_gorunen_yerde_yok():
    bulunan = []
    for p in _gorunen_dosyalar():
        for i, satir in enumerate(p.read_text(encoding="utf-8", errors="ignore").splitlines(), 1):
            if re.search(r"(?<![\d.])v?0\.8\.\d+(?![\d.])", satir):
                bulunan.append(f"{p.relative_to(KOK)}:{i}")
    assert not bulunan, f"eski 0.8.x izi: {bulunan[:10]}"
