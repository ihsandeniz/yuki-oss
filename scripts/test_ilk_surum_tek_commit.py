#!/usr/bin/env python3
"""ilk_surum_tek_commit.py kapıları — her kapı bilerek kırılır, yakalandığı görülür.

    python3 scripts/test_ilk_surum_tek_commit.py      # çıkış 0 = hepsi geçti

Sahte bir kaynak depo kurulur: 1. commit'te "kişisel" dosya, 2.'de silinmiş, bir
etiket. Yeni depoda o dosyanın blob'u da, eski commit de, etiket de olmamalı.
Gerçek depoya, ağa, uzak depoya dokunulmaz.
"""
from __future__ import annotations

import ast
import os
import subprocess
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import ilk_surum_tek_commit as t  # noqa: E402

ENV = {**os.environ, "GIT_AUTHOR_NAME": "x", "GIT_AUTHOR_EMAIL": "x@x",
       "GIT_COMMITTER_NAME": "x", "GIT_COMMITTER_EMAIL": "x@x"}


def sh(*arg, cwd):
    return subprocess.run(["git", *arg], cwd=cwd, env=ENV, check=True,
                          capture_output=True, text=True).stdout.strip()


def kaynak_depo(kok: Path) -> tuple[Path, str]:
    d = kok / "kaynak"
    d.mkdir()
    sh("init", "-q", "-b", "main", cwd=d)
    (d / "kisisel.txt").write_text("kişisel gizli not\n")
    (d / "README.md").write_text("ilk\n")
    sh("add", "-A", cwd=d)
    sh("commit", "-q", "-m", "eski", cwd=d)
    sh("tag", "v0-eski", cwd=d)
    gizli_blob = sh("rev-parse", "HEAD:kisisel.txt", cwd=d)
    (d / "kisisel.txt").unlink()
    (d / "README.md").write_text("temiz\n")
    sh("add", "-A", cwd=d)
    sh("commit", "-q", "-m", "temiz", cwd=d)
    return d, gizli_blob


def hazir(kok: Path):
    kaynak, blob = kaynak_depo(kok)
    hedef = kok / "yeni"
    bilgi = t.tek_commit_olustur(kaynak, "HEAD", hedef)
    return kaynak, hedef, bilgi, blob


SONUC: list[tuple[str, bool, str]] = []


def test(ad):
    def sar(f):
        with tempfile.TemporaryDirectory() as g:
            try:
                f(Path(g))
                SONUC.append((ad, True, ""))
            except AssertionError as e:
                SONUC.append((ad, False, str(e)))
        return f
    return sar


@test("temiz yol: tek commit, ağaç aynı, kapı listesi boş")
def _(g):
    kaynak, hedef, bilgi, _b = hazir(g)
    assert t.dogrula(hedef, bilgi["agac"]) == [], t.dogrula(hedef, bilgi["agac"])
    assert bilgi["agac"] == sh("rev-parse", "HEAD^{tree}", cwd=kaynak)


@test("eski kişisel blob yeni depoda YOK")
def _(g):
    _k, hedef, _bi, blob = hazir(g)
    r = subprocess.run(["git", "cat-file", "-e", blob], cwd=hedef)
    assert r.returncode != 0, "silinmiş kişisel dosyanın blob'u yeni depoda duruyor"


@test("eski etiket taşınmadı")
def _(g):
    _k, hedef, _bi, _b = hazir(g)
    assert sh("tag", "-l", cwd=hedef) == ""


@test("hedef dolu → reddeder")
def _(g):
    kaynak, _b = kaynak_depo(g)
    (g / "dolu").mkdir()
    (g / "dolu" / "x").write_text("x")
    try:
        t.tek_commit_olustur(kaynak, "HEAD", g / "dolu")
    except RuntimeError:
        return
    raise AssertionError("dolu hedefe yazdı")


# ── Mutasyonlar: her kapı bir kez kırılır ─────────────────────────────

def yakalar(hedef, agac, parca):
    h = t.dogrula(hedef, agac)
    assert any(parca in x for x in h), f"'{parca}' yakalanmadı: {h}"


@test("MUT ikinci commit → 'tek commit değil'")
def _(g):
    _k, hedef, bilgi, _b = hazir(g)
    (hedef / "ek").write_text("x")
    sh("add", "ek", cwd=hedef)
    sh("commit", "-q", "-m", "ek", cwd=hedef)
    yakalar(hedef, bilgi["agac"], "tek commit değil")


@test("MUT budanmamış geçmiş → 'commit nesnesi'")
def _(g):
    kaynak, hedef, bilgi, _b = hazir(g)
    sh("fetch", "-q", "--no-tags", str(kaynak), "HEAD", cwd=hedef)
    yakalar(hedef, bilgi["agac"], "commit nesnesi")


@test("MUT ebeveynli commit → 'ebeveyni var'")
def _(g):
    kaynak, hedef, bilgi, _b = hazir(g)
    sh("fetch", "-q", "--no-tags", str(kaynak), "HEAD", cwd=hedef)
    ust = sh("rev-parse", "FETCH_HEAD", cwd=hedef)
    c = subprocess.run(["git", "commit-tree", bilgi["agac"], "-p", ust, "-m", "m"], cwd=hedef,
                       env=ENV, capture_output=True, text=True, check=True).stdout.strip()
    sh("update-ref", "refs/heads/main", c, cwd=hedef)
    yakalar(hedef, bilgi["agac"], "ebeveyni var")


@test("MUT farklı ağaç → 'ağaç farklı'")
def _(g):
    _k, hedef, _bi, _b = hazir(g)
    yakalar(hedef, "0" * 40, "ağaç farklı")


@test("MUT yanlış yazar → 'yazar'")
def _(g):
    _k, hedef, bilgi, _b = hazir(g)
    c = subprocess.run(["git", "commit-tree", bilgi["agac"], "-m", "m"], cwd=hedef,
                       env=ENV, capture_output=True, text=True, check=True).stdout.strip()
    sh("update-ref", "refs/heads/main", c, cwd=hedef)
    sh("reflog", "expire", "--expire=now", "--all", cwd=hedef)
    sh("gc", "-q", "--prune=now", cwd=hedef)
    yakalar(hedef, bilgi["agac"], "yazar")


@test("MUT etiket → 'etiket taşındı'")
def _(g):
    _k, hedef, bilgi, _b = hazir(g)
    sh("tag", "v0", cwd=hedef)
    yakalar(hedef, bilgi["agac"], "etiket taşındı")


@test("MUT büyük dosya → 'büyük dosya'")
def _(g):
    _k, hedef, bilgi, _b = hazir(g)
    eski = t.BUYUK_DOSYA
    t.BUYUK_DOSYA = 3  # README 6 bayt
    try:
        yakalar(hedef, bilgi["agac"], "büyük dosya")
    finally:
        t.BUYUK_DOSYA = eski


@test("MUT kapı kırmızısı → main() çıkış 1")
def _(g):
    eski = t.kapilar_kos
    t.kapilar_kos = lambda h: ["temizlik: çıkış 1 — sahte"]
    try:
        kaynak, _b = kaynak_depo(g)
        eski_depo, t.DEPO = t.DEPO, kaynak
        try:
            assert t.main(["--hedef", str(g / "y")]) == 1
        finally:
            t.DEPO = eski_depo
    finally:
        t.kapilar_kos = eski


# ── İtme yok: betikte 'push' yalnız ekrana basılan metinde geçebilir ──

def push_cagrisi(kaynak: str) -> list[int]:
    satir = []
    for n in ast.walk(ast.parse(kaynak)):
        if isinstance(n, ast.Call):
            for s in ast.walk(n):
                if isinstance(s, ast.Constant) and isinstance(s.value, str) and s.value.strip() == "push":
                    satir.append(n.lineno)
    return satir


@test("betik hiçbir çağrıda 'push' geçirmez")
def _(g):
    k = Path(t.__file__).read_text()
    assert push_cagrisi(k) == [], f"push çağrısı: satır {push_cagrisi(k)}"


@test("MUT eklenen git('push') yakalanır")
def _(g):
    k = Path(t.__file__).read_text() + '\ngit("push", "origin", "main", cwd=DEPO)\n'
    assert push_cagrisi(k), "eklenen push çağrısı görülmedi"


# ── CHANGELOG yer tutucu kapısı (yalnız açılış betiğinde) ─────────────

TARIHLI = "# Changelog\n\n## [1.0.0] - 2026-11-20 — first open-source release\n\n### Added\n- x\n"
YER_TUTUCULU = "# Changelog\n\n## [1.0.0] - açılış günü — first open-source release\n"


def cl(g: Path, metin: str | None) -> list[str]:
    if metin is not None:
        (g / "CHANGELOG.md").write_text(metin, encoding="utf-8")
    return t.changelog_dogrula(g)


@test("CHANGELOG tarihli başlık → yeşil")
def _(g):
    assert cl(g, TARIHLI) == [], cl(g, TARIHLI)


@test("CHANGELOG eski sürümler alttaysa yalnız ilk başlık bakılır")
def _(g):
    assert cl(g, TARIHLI + "\n## [0.9.0] - açılış günü\n") == []


@test("MUT 'açılış günü' yer tutucusu → 'yer tutucu duruyor'")
def _(g):
    h = cl(g, YER_TUTUCULU)
    assert any("yer tutucu duruyor" in x for x in h), h


@test("MUT tarih yerine boş/TBD → kırmızı")
def _(g):
    for baslik in ("## [1.0.0]\n", "## [1.0.0] - TBD\n", "## [1.0.0] - YYYY-MM-DD\n",
                   "## [Unreleased]\n"):
        assert cl(g, "# Changelog\n\n" + baslik), f"yakalanmadı: {baslik!r}"


@test("MUT tarihli ama yer tutuculu başlık → yalnız 'yer tutucu duruyor'")
def _(g):
    h = cl(g, "## [1.0.0] - 2026-11-20 — açılış günü\n")
    assert len(h) == 1 and "yer tutucu duruyor" in h[0], h


@test("MUT yer tutucusuz ama tarihsiz başlık → yalnız 'tarihsiz'")
def _(g):
    for baslik in ("## [1.0.0] - yakında — x\n", "## [1.0.0] - 20.11.2026\n"):
        h = cl(g, baslik)
        assert len(h) == 1 and "tarihsiz" in h[0], (baslik, h)


@test("MUT geçersiz tarih → 'geçersiz tarih'")
def _(g):
    h = cl(g, "## [1.0.0] - 2026-13-45 — x\n")
    assert any("geçersiz tarih" in x for x in h), h


@test("MUT CHANGELOG yok / başlıksız → kırmızı")
def _(g):
    assert cl(g, None) == ["CHANGELOG.md yok"]
    assert cl(g, "# Changelog\n\nhiç sürüm yok\n"), "başlıksız changelog geçti"


@test("MUT yer tutucu → main() çıkış 1 (öbür kapılar yeşilken)")
def _(g):
    kaynak, _b = kaynak_depo(g)
    (kaynak / "CHANGELOG.md").write_text(YER_TUTUCULU, encoding="utf-8")
    sh("add", "-A", cwd=kaynak)
    sh("commit", "-q", "-m", "cl", cwd=kaynak)
    eski_depo, t.DEPO = t.DEPO, kaynak
    try:
        assert t.main(["--kapisiz", "--hedef", str(g / "y")]) == 1
    finally:
        t.DEPO = eski_depo


@test("tarihli CHANGELOG → main() --kapisiz çıkış 0")
def _(g):
    kaynak, _b = kaynak_depo(g)
    (kaynak / "CHANGELOG.md").write_text(TARIHLI, encoding="utf-8")
    sh("add", "-A", cwd=kaynak)
    sh("commit", "-q", "-m", "cl", cwd=kaynak)
    eski_depo, t.DEPO = t.DEPO, kaynak
    try:
        assert t.main(["--kapisiz", "--hedef", str(g / "y")]) == 0
    finally:
        t.DEPO = eski_depo


@test("günlük CI kapıları açılış betiğini koşmaz (main yer tutucuyla yeşil kalır)")
def _(g):
    wf = (Path(t.__file__).resolve().parents[1] / ".github" / "workflows")
    for y in wf.glob("*.yml"):
        for satir in y.read_text(encoding="utf-8").splitlines():
            assert "scripts/ilk_surum_tek_commit.py" not in satir, f"{y.name}: {satir.strip()}"


if __name__ == "__main__":
    for ad, ok, neden in SONUC:
        print(("🟢 " if ok else "🔴 ") + ad + (f" — {neden}" if neden else ""))
    kaldi = sum(1 for _, ok, _n in SONUC if not ok)
    print(f"geçti {len(SONUC) - kaldi} · kaldı {kaldi}")
    sys.exit(1 if kaldi else 0)
