"""scripts/yayin.py — test kapısı + sürüm etiketi (CI FAZ 3, 2026-10-10).

Neden var: `cmd_hazir` testler düşünce "⚠ N sorun — yine de devam edilebilir" deyip DAİMA
0 dönüyordu, yani `yayin.py tam` kırmızı testle yayına çıkabiliyordu. Ayrıca sürümlerin git
izi yoktu: hangi commit'in derlendiği commit mesajından tahmin ediliyordu.

Testler gerçek alt süreçleri (npm/pytest/gh) KOŞMAZ. `subprocess.run` ve `kos` içindeki
dış komutlar taklit edilir; git komutları geçici bir depoda GERÇEKTEN koşar.
"""
from __future__ import annotations

import argparse
import importlib.util
import json
import os
import subprocess
from pathlib import Path

import pytest

_YOL = Path(__file__).resolve().parents[2] / "scripts" / "yayin.py"


@pytest.fixture
def yayin():
    spec = importlib.util.spec_from_file_location("yayin_test_kopyasi", _YOL)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


@pytest.fixture
def depo(tmp_path, monkeypatch, yayin):
    """Ürün deposunun damga iskeleti: electron/package.json + health.py, git'li, v9.9.9."""
    monkeypatch.setenv("GIT_CONFIG_GLOBAL", os.devnull)
    monkeypatch.setenv("GIT_CONFIG_NOSYSTEM", "1")
    for k, d in {"GIT_AUTHOR_NAME": "t", "GIT_AUTHOR_EMAIL": "t@t", "GIT_COMMITTER_NAME": "t",
                 "GIT_COMMITTER_EMAIL": "t@t"}.items():
        monkeypatch.setenv(k, d)
    kok = tmp_path / "urun"
    (kok / "electron").mkdir(parents=True)
    (kok / "backend" / "app" / "services").mkdir(parents=True)
    (kok / "electron" / "package.json").write_text(json.dumps({"name": "alice-ai", "version": "9.9.9"}))
    (kok / "backend" / "app" / "services" / "health.py").write_text('APP_VERSION = "9.9.9"\n')
    for c in (["init", "-q", "-b", "main"], ["add", "-A"], ["commit", "-q", "-m", "ilk"]):
        subprocess.run(["git", *c], cwd=kok, check=True)
    monkeypatch.setattr(yayin, "KOK", kok)
    monkeypatch.setattr(yayin, "DAMGALAR", [
        (kok / "electron" / "package.json", r'("version":\s*")[\d.]+(")'),
        (kok / "backend" / "app" / "services" / "health.py", r'(APP_VERSION\s*=\s*")[\d.]+(")'),
    ])
    monkeypatch.setattr(yayin, "site_surumu", lambda: None)
    return kok


def _git(kok, *a) -> str:
    return subprocess.run(["git", *a], cwd=kok, capture_output=True, text=True, check=True).stdout.strip()


def _sahte_testler(monkeypatch, yayin, *, pytest_rc=0, npm_rc=0):
    """npm test / pytest / bundle-envanter taklidi; git gerçek koşar."""
    gercek = subprocess.run

    def run(cmd, *a, **k):
        metin = " ".join(map(str, cmd))
        if cmd[0] == "npm":
            return subprocess.CompletedProcess(cmd, npm_rc, "ok\n" if not npm_rc else "", "")
        if "pytest" in metin:
            cikti = ("FAILED tests/test_x.py::test_y - assert 1 == 2\n1 failed, 9 passed\n"
                     if pytest_rc else "10 passed\n")
            return subprocess.CompletedProcess(cmd, pytest_rc, cikti, "")
        if "bundle-envanter" in metin:
            return subprocess.CompletedProcess(cmd, 0, "", "")
        return gercek(cmd, *a, **k)

    monkeypatch.setattr(yayin.subprocess, "run", run)


def _ns(**k):
    return argparse.Namespace(**{"hizli": False, "zorla": False, **k})


# ── hazir: test kapısı ───────────────────────────────────────────────────────

def test_hazir_kirmizi_pytest_1_doner(depo, yayin, monkeypatch, capsys):
    _sahte_testler(monkeypatch, yayin, pytest_rc=1)
    assert yayin.cmd_hazir(_ns()) == 1
    cikti = capsys.readouterr().out
    assert "python testleri DÜŞTÜ" in cikti and "--zorla" in cikti
    assert "FAILED tests/test_x.py::test_y" in cikti, "ilk kırmızılar basılmalı"


def test_hazir_kirmizi_electron_1_doner(depo, yayin, monkeypatch):
    _sahte_testler(monkeypatch, yayin, npm_rc=1)
    assert yayin.cmd_hazir(_ns()) == 1


def test_hazir_zorla_bilincli_gecer(depo, yayin, monkeypatch, capsys):
    _sahte_testler(monkeypatch, yayin, pytest_rc=1)
    assert yayin.cmd_hazir(_ns(zorla=True)) == 0
    assert "BİLİNÇLİ" in capsys.readouterr().out


def test_hazir_yesil_0_doner(depo, yayin, monkeypatch, capsys):
    _sahte_testler(monkeypatch, yayin)
    assert yayin.cmd_hazir(_ns()) == 0
    assert "yayına hazır" in capsys.readouterr().out


def test_tam_hazir_dusunce_zincir_durur(depo, yayin, monkeypatch):
    _sahte_testler(monkeypatch, yayin, pytest_rc=1)
    sonraki = []
    for ad in ("cmd_surum", "cmd_surum_commit", "cmd_derle", "cmd_taslak", "cmd_vitrin",
               "cmd_yayinla", "cmd_denetle"):
        monkeypatch.setattr(yayin, ad, lambda a, ad=ad: sonraki.append(ad) or 0)
    a = argparse.Namespace(surum="9.9.9", baslik="t", notlar=None, sw=False, deploy=False,
                           on_yayin=False, zorla=False)
    with pytest.raises(SystemExit) as e:
        yayin.cmd_tam(a)
    assert "hazir" in str(e.value) and "zincir durdu" in str(e.value)
    assert sonraki == [], f"hazir düştükten sonra adım koştu: {sonraki}"


def test_tam_zorla_hazir_dan_gecer(depo, yayin, monkeypatch):
    _sahte_testler(monkeypatch, yayin, pytest_rc=1)
    sonraki = []
    for ad in ("cmd_surum", "cmd_surum_commit", "cmd_derle", "cmd_taslak", "cmd_vitrin",
               "cmd_yayinla", "cmd_denetle"):
        monkeypatch.setattr(yayin, ad, lambda a, ad=ad: sonraki.append(ad) or 0)
    a = argparse.Namespace(surum="9.9.9", baslik="t", notlar=None, sw=False, deploy=False,
                           on_yayin=False, zorla=True)
    assert yayin.cmd_tam(a) == 0
    assert sonraki[:2] == ["cmd_surum", "cmd_surum_commit"]


# ── etiket ───────────────────────────────────────────────────────────────────

def _gh_taklit(monkeypatch, yayin) -> list:
    """`kos` içindeki gh çağrılarını yakala; git gerçek koşsun."""
    gh = []
    gercek = yayin.kos

    def kos(cmd, cwd=None, sessiz=False):
        if cmd[0] == "gh":
            gh.append(cmd)
            return ""
        return gercek(cmd, cwd=cwd, sessiz=sessiz)

    monkeypatch.setattr(yayin, "kos", kos)
    return gh


def test_yayinla_yerel_etiket_atar(depo, yayin, monkeypatch):
    gh = _gh_taklit(monkeypatch, yayin)
    assert yayin.cmd_yayinla(argparse.Namespace(deploy=False, on_yayin=False)) == 0
    assert gh, "release yayına alınmalıydı"
    assert _git(depo, "tag", "-l", "v9.9.9").splitlines() == ["v9.9.9"]
    assert _git(depo, "cat-file", "-t", "v9.9.9") == "tag", "açıklamalı (-a) etiket olmalı"
    assert _git(depo, "rev-parse", "v9.9.9^{commit}") == _git(depo, "rev-parse", "HEAD")


def test_on_yayin_da_etiket_atar_ve_tekrar_kosu_serbest(depo, yayin, monkeypatch):
    _gh_taklit(monkeypatch, yayin)
    assert yayin.cmd_yayinla(argparse.Namespace(deploy=False, on_yayin=True)) == 0
    assert _git(depo, "tag", "-l", "v9.9.9") == "v9.9.9"
    # ön-yayından sonra aynı commit'te stable'a alma: etiket zaten HEAD'de → durmaz
    assert yayin.cmd_yayinla(argparse.Namespace(deploy=False, on_yayin=False)) == 0


def test_etiket_baska_committe_varsa_durur_ve_yayinlamaz(depo, yayin, monkeypatch, capsys):
    gh = _gh_taklit(monkeypatch, yayin)
    _git(depo, "tag", "-a", "v9.9.9", "-m", "eski")
    (depo / "not.txt").write_text("x")
    _git(depo, "add", "not.txt"); _git(depo, "commit", "-q", "-m", "sonraki")
    assert yayin.cmd_yayinla(argparse.Namespace(deploy=False, on_yayin=False)) == 1
    assert gh == [], "etiket engeli varken release'e dokunuldu"
    assert "zaten var" in capsys.readouterr().out


def test_damga_commitlenmemisse_durur_ve_yayinlamaz(depo, yayin, monkeypatch, capsys):
    gh = _gh_taklit(monkeypatch, yayin)
    pj = depo / "electron" / "package.json"
    pj.write_text(json.dumps({"name": "alice-ai", "version": "9.9.10"}))
    assert yayin.cmd_yayinla(argparse.Namespace(deploy=False, on_yayin=False)) == 1
    assert gh == []
    assert "commit'lenmemiş" in capsys.readouterr().out
    assert _git(depo, "tag", "-l") == ""


def test_surum_commit_yalniz_damgayi_commitler_sonra_etiket(depo, yayin, monkeypatch):
    _gh_taklit(monkeypatch, yayin)
    yayin.cmd_surum(argparse.Namespace(surum="9.9.10", sw=False))
    (depo / "baska.txt").write_text("commit'e girmemeli")
    assert yayin.cmd_surum_commit(argparse.Namespace()) == 0
    assert _git(depo, "log", "-1", "--format=%s") == "surum: v9.9.10"
    assert sorted(_git(depo, "show", "--name-only", "--format=", "HEAD").splitlines()) == [
        "backend/app/services/health.py", "electron/package.json"]
    assert "?? baska.txt" in _git(depo, "status", "--porcelain")
    assert yayin.cmd_yayinla(argparse.Namespace(deploy=False, on_yayin=False)) == 0
    assert _git(depo, "rev-parse", "v9.9.10^{commit}") == _git(depo, "rev-parse", "HEAD")


def test_elle_etiket_komutu(depo, yayin, capsys):
    assert yayin.cmd_etiket(argparse.Namespace()) == 0
    assert _git(depo, "tag", "-l") == "v9.9.9"
    (depo / "electron" / "package.json").write_text(json.dumps({"name": "alice-ai", "version": "9.9.11"}))
    assert yayin.cmd_etiket(argparse.Namespace()) == 1, "commit'lenmemiş damgaya etiket atıldı"
    assert _git(depo, "tag", "-l") == "v9.9.9"
