"""Müşteriye giden kutunun kilit dosyası, kutunun kendisiyle senkron kalsın.

🔴 NEDEN VAR (2026-09-05):

`dependency-scan.yml` artık `backend/pybundle-kilit.txt` +
`backend/pybundle-win-kilit.txt`'yi tarıyor — çünkü kutuların kendisi
`.gitignore`'da (1,2 GB + 963 MB) ve CI runner'ı onları göremiyor.

Ama kilit **bayatlarsa tarama yalancı yeşile döner**: kutuya yeni/eski bir paket
girer, kilit eski hâlini gösterir, CI "0 açık" der. Bu'ün kapatmaya
çalıştığı kusurun ta kendisidir — sadece bir kat aşağı taşınmış hâli.
📏 *Taranan şey ile satılan şey aynı mı?*

Bu yüzden tazelik kapısı kutunun **bulunduğu** yerde koşar: burada (yerel pytest)
ve `scripts/yayin.py hazir`'da (yayın öncesi ön kontrol). CI'da kutu yok → senkron
testi atlanır; CI'nın işi kilidi TARAMAK, tazeliğini ölçmek değil.

⚠️ Atlanan test yeşil görünür. O yüzden `test_kilit_dosyalari_git_te_ve_dolu`
**her yerde** koşar (kutu gerektirmez): kilit silinir/boşalırsa burada patlar.
"""
from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pytest

KOK = Path(__file__).resolve().parent.parent.parent      # → depo kökü
ARAC = KOK / "scripts" / "bundle-envanter.py"

KUTULAR = [
    ("pybundle", KOK / "backend" / "pybundle", KOK / "backend" / "pybundle-kilit.txt"),
    ("pybundle-win", KOK / "backend" / "pybundle-win", KOK / "backend" / "pybundle-win-kilit.txt"),
]

# Taban ölçümü 2026-09-05: Linux 150 · Windows 152 paket. Alt sınır kabaca
# yarısı — amaç "kaç paket doğru" demek değil, kilidin BOŞALMASINI yakalamak.
ASGARI_PAKET = 100


def _satirlar(kilit: Path) -> list[str]:
    return [s for s in kilit.read_text(encoding="utf-8").splitlines()
            if s.strip() and not s.startswith("#")]


@pytest.mark.parametrize("ad,_kutu,kilit", KUTULAR, ids=[k[0] for k in KUTULAR])
def test_kilit_dosyalari_git_te_ve_dolu(ad: str, _kutu: Path, kilit: Path) -> None:
    """Kutu olmadan da koşar — CI'ın taradığı dosya gerçekten var ve dolu mu."""
    assert kilit.is_file(), (
        f"{kilit.name} YOK — CI bu dosyayı tarıyor, yoksa tarama hiç koşmaz. "
        f"Üret: python3 scripts/bundle-envanter.py"
    )
    satirlar = _satirlar(kilit)
    assert len(satirlar) >= ASGARI_PAKET, (
        f"{kilit.name} şüpheli derecede kısa ({len(satirlar)} paket) — "
        f"boş/bozuk kilit 'açık yok' der ve yalancı yeşil üretir"
    )
    sabitsiz = [s for s in satirlar if "==" not in s]
    assert not sabitsiz, (
        f"{kilit.name}: sabitlenmemiş satır var {sabitsiz[:3]} — "
        f"pip-audit --no-deps tam sürüm ister"
    )


@pytest.mark.parametrize("ad,kutu,_kilit", KUTULAR, ids=[k[0] for k in KUTULAR])
def test_kilit_kutuyla_senkron(ad: str, kutu: Path, _kilit: Path) -> None:
    """Kilit, kutunun ŞU ANKİ içeriğini yansıtıyor mu. Kutu yoksa atlanır."""
    if not kutu.is_dir():
        pytest.skip(f"{ad} yok (bu makinede üretilmemiş) — senkron ölçülemez")

    # --kutu ŞART: ikisini birden denetlersek Linux kilidi bayatken Windows testi
    # de kırmızıya düşer ve "pybundle-win bayat" der — yanlış yeri işaret eden
    # kırmızı, kırmızı olmamaktan az zararlı değildir. (mutasyonla ölçüldü)
    p = subprocess.run([sys.executable, str(ARAC), "--check", "--kutu", ad],
                       cwd=KOK, capture_output=True, text=True)
    assert p.returncode == 0, (
        f"{ad} kilidi BAYAT — kutu değişmiş, kilit güncellenmemiş.\n"
        f"CI bu kilidi tarıyor; bayat kilit = taranmayan paket.\n"
        f"Düzelt: python3 scripts/bundle-envanter.py\n\n{p.stdout}{p.stderr}"
    )


# ── Kaynak ↔ kutu sürüm uyumu (2026-11-10, oauthlib CVE-2026-49272) ──────────
#
# Bir açık kapatılırken sürüm ÜÇ yerde birden yükselmeli: kaynak
# (`requirements-product.txt`, kutu bundan üretilir) + iki kilit (CI bunları
# tarar). Yalnız kilidi yükseltmek CI'ı yeşile çevirir ama bir sonraki kutu eski
# sürümle üretilir; yalnız kaynağı yükseltmek CI'ı kırmızıda bırakır. Bu test
# ikisi de gerekmeden (kutu olmadan) her yerde koşar.
KAYNAK = KOK / "backend" / "requirements-product.txt"

# Bilinen, açık OLMAYAN eski kayma: kutu kaynaktan yeni tqdm taşıyor. Kapatılınca
# buradan sil — aşağıdaki test kayma kapanınca listeyi temizlemeni ister.
BILINEN_KAYMA = {"tqdm"}


def _sabitler(yol: Path) -> dict[str, str]:
    import re
    d: dict[str, str] = {}
    for s in yol.read_text(encoding="utf-8").splitlines():
        s = s.split("#", 1)[0].split(";", 1)[0].strip()
        if "==" not in s or s.startswith("-"):
            continue
        ad, surum = s.split("==", 1)
        ad = re.sub(r"[-_.]+", "-", ad.split("[", 1)[0]).lower()
        d[ad] = surum.strip()
    return d


@pytest.mark.parametrize("ad,_kutu,kilit", KUTULAR, ids=[k[0] for k in KUTULAR])
def test_kaynak_ve_kilit_ayni_surumu_sabitliyor(ad: str, _kutu: Path, kilit: Path) -> None:
    kaynak, kutu = _sabitler(KAYNAK), _sabitler(kilit)
    ortak = set(kaynak) & set(kutu)
    assert len(ortak) >= ASGARI_PAKET, f"{ad}: ortak paket az ({len(ortak)}) — ayrıştırma bozuk"
    fark = {p: (kaynak[p], kutu[p]) for p in ortak if kaynak[p] != kutu[p]}
    yeni = {p: v for p, v in fark.items() if p not in BILINEN_KAYMA}
    assert not yeni, (
        f"{ad}: kaynak ile kilit farklı sürüm sabitliyor (kaynak, kilit): {yeni} — "
        f"açık kapatırken üç dosyayı birlikte yükselt"
    )
    kapanmis = BILINEN_KAYMA - set(fark)
    assert not kapanmis, f"{ad}: {kapanmis} artık kaymıyor — BILINEN_KAYMA'dan sil"
