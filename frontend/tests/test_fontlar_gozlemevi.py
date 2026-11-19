"""Gözlemevi yazı tipleri (11-13 ORTAK) — dosya, kaynak, lisans ve önbellek kapısı.

    python3 frontend/tests/test_fontlar_gozlemevi.py          # kapılar
    python3 frontend/tests/test_fontlar_gozlemevi.py --mutasyon   # her kapı bir kez bilerek kırılır

Kapılar:
  F1 fontlar-gozlemevi.css'teki her `src: url(...)` diskte var, yalnız @font-face taşıyor (seçici yok)
  F2 her woff2'nin sha256'sı KAYNAK.md tablosundaki ilk 16 haneyle aynı (sessiz değişim yok)
  F3 her aile için OFL lisans metni var ve THIRD_PARTY_LICENSES.md aileyi + dosya yolunu anıyor
  F4 frontend/ altındaki HER woff2 THIRD_PARTY_LICENSES.md'de klasörü/öneki ile anılıyor (lisanssız font girmez)
  F5 sw.js önbellek listesindeki gözlemevi girdileri diskte var ve sekiz dosyanın hepsi listede
Çıkış kodu = kalan sayısı.
"""
import hashlib
import re
import shutil
import sys
import tempfile
from pathlib import Path

KOK = Path(__file__).resolve().parents[2]


def _yollar(kok):
    fe = kok / "frontend"
    return fe, fe / "css" / "fontlar-gozlemevi.css", fe / "assets" / "fonts" / "gozlemevi", kok / "THIRD_PARTY_LICENSES.md", fe / "sw.js"


def f1(kok):
    fe, css, _, _, _ = _yollar(kok)
    metin = css.read_text(encoding="utf-8")
    govde = re.sub(r"/\*.*?\*/", "", metin, flags=re.S)
    urller = re.findall(r'url\("\.\./([^"]+)"\)', govde)
    assert len(urller) == 8, f"8 src beklenirdi, {len(urller)}"
    eksik = [u for u in urller if not (fe / u).is_file()]
    assert not eksik, f"diskte yok: {eksik}"
    secici = re.sub(r"@font-face\s*\{[^}]*\}", "", govde).strip()
    assert not secici, f"@font-face dışı kural var: {secici[:80]!r}"


def f2(kok):
    _, _, dz, _, _ = _yollar(kok)
    tablo = dict(re.findall(r"\| `([a-z-]+\.woff2)` \|.*?\| `([0-9a-f]{16})` \|", (dz / "KAYNAK.md").read_text(encoding="utf-8")))
    dosyalar = sorted(p.name for p in dz.glob("*.woff2"))
    assert sorted(tablo) == dosyalar, f"KAYNAK.md tablosu ↔ klasör: {sorted(tablo)} ≠ {dosyalar}"
    for ad, onek in tablo.items():
        h = hashlib.sha256((dz / ad).read_bytes()).hexdigest()[:16]
        assert h == onek, f"{ad}: sha256 {h} ≠ KAYNAK.md {onek}"


def f3(kok):
    _, _, dz, tpl, _ = _yollar(kok)
    lis = tpl.read_text(encoding="utf-8")
    for aile, dosya, onek in (("Fraunces", "OFL-fraunces.txt", "fraunces-"), ("Figtree", "OFL-figtree.txt", "figtree-"),
                              ("Martian Mono", "OFL-martian-mono.txt", "martian-mono-")):
        ofl = dz / dosya
        assert ofl.is_file() and "SIL OPEN FONT LICENSE Version 1.1" in ofl.read_text(encoding="utf-8"), f"{dosya} yok/bozuk"
        assert re.search(r"\| " + re.escape(aile) + r" \| `frontend/assets/fonts/gozlemevi/" + re.escape(onek), lis), \
            f"THIRD_PARTY_LICENSES.md {aile} satırı yok"


def f4(kok):
    fe, _, _, tpl, _ = _yollar(kok)
    lis = tpl.read_text(encoding="utf-8")
    anilan = re.findall(r"`(frontend/[^`*…]+)", lis)
    lisanssiz = []
    for p in fe.rglob("*.woff2"):
        if "node_modules" in p.parts:
            continue
        g = str(p.relative_to(kok))
        if not any(g.startswith(a) for a in anilan):
            lisanssiz.append(g)
    assert not lisanssiz, f"THIRD_PARTY_LICENSES.md'de anılmayan font: {lisanssiz[:5]}"


def f5(kok):
    fe, _, dz, _, sw = _yollar(kok)
    girdiler = re.findall(r"'/ui/(assets/fonts/gozlemevi/[^'?]+)'", sw.read_text(encoding="utf-8"))
    assert sorted(Path(g).name for g in girdiler) == sorted(p.name for p in dz.glob("*.woff2")), "sw.js listesi ↔ klasör ayrışmış"
    assert all((fe / g).is_file() for g in girdiler)


KAPILAR = [f1, f2, f3, f4, f5]


def _kopya():
    d = Path(tempfile.mkdtemp())
    for ad in ("frontend/css/fontlar-gozlemevi.css", "THIRD_PARTY_LICENSES.md", "frontend/sw.js"):
        (d / ad).parent.mkdir(parents=True, exist_ok=True)
        shutil.copy(KOK / ad, d / ad)
    shutil.copytree(KOK / "frontend/assets/fonts", d / "frontend/assets/fonts")
    shutil.copytree(KOK / "frontend/fonts", d / "frontend/fonts")
    return d


def _zehir_f1(d): p = d / "frontend/css/fontlar-gozlemevi.css"; p.write_text(p.read_text() + "\nbody { font-family: Fraunces; }\n")
def _zehir_f2(d): (d / "frontend/assets/fonts/gozlemevi/figtree-latin.woff2").write_bytes(b"degisti")
def _zehir_f3(d): (d / "frontend/assets/fonts/gozlemevi/OFL-figtree.txt").unlink()
def _zehir_f4(d): (d / "frontend/assets/fonts/LisanssizFont.woff2").write_bytes(b"x")
def _zehir_f5(d): p = d / "frontend/sw.js"; p.write_text(p.read_text().replace("  '/ui/assets/fonts/gozlemevi/martian-mono-latin.woff2',\n", ""))

ZEHIR = {f1: _zehir_f1, f2: _zehir_f2, f3: _zehir_f3, f4: _zehir_f4, f5: _zehir_f5}


def main():
    kalan = 0
    if "--mutasyon" in sys.argv:
        for fn, z in ZEHIR.items():
            d = _kopya()
            try:
                fn(d)   # temiz kopyada geçmeli
                z(d)
                try:
                    fn(d)
                    print(f"✗ mutasyon {fn.__name__}: zehir KAÇTI"); kalan += 1
                except AssertionError:
                    print(f"✓ mutasyon {fn.__name__}: yakalandı")
            finally:
                shutil.rmtree(d)
    else:
        for fn in KAPILAR:
            try:
                fn(KOK); print(f"✓ {fn.__name__}")
            except AssertionError as e:
                print(f"✗ {fn.__name__}: {e}"); kalan += 1
    print(f"kaldı {kalan}")
    sys.exit(kalan)


if __name__ == "__main__":
    main()
