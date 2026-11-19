#!/usr/bin/env python3
"""Müşteriye giden Python kutusunun (`pybundle*`) içindekileri kilit dosyasına yaz.

🔴 NEDEN VAR (ölçüm 2026-09-04):

`dependency-scan.yml` yalnız `backend/requirements*.txt`'yi tarıyordu. Ama müşteriye
giden şey o dosya değil, `backend/pybundle/` (Linux) ve `backend/pybundle-win/`
(Windows) — ikisi de `.gitignore`'da (1,2 GB + 963 MB). CI runner'ı onları **hiç
görmedi**, dolayısıyla **hiç taramadı**. Yeşil CI, açık paket demekti: ilk elle
taramada **10 açık / 4 paket** çıktı (aiohttp · cryptography · h2 · pip), üstüne
pypdf'in 3 CVE'si. Fark aylarca görünmedi.

📏 Sorulacak soru: *taranan şey ile SATILAN şey aynı mı?*

**Çözüm:** kutuyu CI'a taşıyamayız, ama **içindekilerin listesini** taşırız.
Bu script her kutunun `*.dist-info/METADATA`'sını okuyup sabitlenmiş
(`ad==sürüm`) bir kilit dosyası üretir. Kilit dosyaları git'e girer (~4 KB),
CI onları `pip-audit --no-deps` ile tarar.

⚠️ **Kilit bayatlarsa tarama yalancı yeşile döner** — tam kaçtığımız kusurun
aynısı. O yüzden iki senkron kapısı var, ikisi de kutunun BULUNDUĞU yerde koşar:
  · `backend/tests/test_bundle_kilit.py`  (yerel pytest)
  · `scripts/yayin.py hazir`              (yayın öncesi ön kontrol)
CI'da kutu yok → test atlanır; CI'nın işi kilidi TARAMAK, tazeliğini ölçmek değil.

Kullanım:
    python3 scripts/bundle-envanter.py            # kilit dosyalarını yaz (idempotent)
    python3 scripts/bundle-envanter.py --check    # yazmadan denetle (bayatsa çıkış 1)
"""
from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

KOK = Path(__file__).resolve().parent.parent  # → depo kökü

# kutu adı → (site-packages arama deseni, kilit dosyası)
KUTULAR = {
    "pybundle": ("lib/python*/site-packages", KOK / "backend" / "pybundle-kilit.txt"),
    "pybundle-win": ("Lib/site-packages", KOK / "backend" / "pybundle-win-kilit.txt"),
}

BASLIK = """\
# ÜRETİLEN DOSYA — elle düzenleme.
# Kaynak: backend/{kutu}/  ·  üretici: scripts/bundle-envanter.py
#
# Bu, müşteriye giden Python kutusunun İÇİNDEKİ paketlerin tam listesidir.
# Kutunun kendisi .gitignore'da (GB'larca) — CI onu göremez, bu listeyi tarar:
#     pip-audit --no-deps --disable-pip -r {kilit}
# (--disable-pip şart: yoksa pip-audit çözümleme için pip'i çağırır ve Windows
#  listesi Linux runner'da ölür — pywin32 orada kurulamaz.)
#
# Tazeliği: backend/tests/test_bundle_kilit.py + scripts/yayin.py hazir
# Yeniden üret: python3 scripts/bundle-envanter.py
"""


def normalize(ad: str) -> str:
    """PEP 503 — 'Foo.Bar_baz' ve 'foo-bar-baz' aynı pakettir."""
    return re.sub(r"[-_.]+", "-", ad).lower()


def site_packages(kutu: str) -> Path | None:
    kok = KOK / "backend" / kutu
    if not kok.is_dir():
        return None
    desen, _ = KUTULAR[kutu]
    for aday in sorted(kok.glob(desen)):
        if aday.is_dir():
            return aday
    return None


def envanter(sp: Path, kutu: str) -> list[tuple[str, str]]:
    """dist-info'lardan (ad, sürüm) topla. Ad/sürüm METADATA'dan okunur —
    dizin adından DEĞİL: dizin adı normalize edilmiş olabilir, METADATA
    paketin PyPI'daki gerçek adını taşır ve pip-audit onu bekler."""
    bulunan: dict[str, tuple[str, str, str]] = {}   # norm → (ad, sürüm, dizin)
    cift: list[str] = []

    for di in sorted(sp.glob("*.dist-info")):
        meta = di / "METADATA"
        if not meta.is_file():
            cift.append(f"METADATA yok: {di.name}")
            continue
        ad = surum = None
        # METADATA RFC822 başlığı: ilk boş satıra kadar. Gövdede (açıklama metni)
        # 'Version:' geçebilir → boş satırda dur, yoksa yanlış sürüm okunur.
        for satir in meta.read_text(encoding="utf-8", errors="replace").splitlines():
            if not satir.strip():
                break
            if satir.startswith("Name:") and ad is None:
                ad = satir[5:].strip()
            elif satir.startswith("Version:") and surum is None:
                surum = satir[8:].strip()
        if not ad or not surum:
            cift.append(f"Name/Version okunamadı: {di.name}")
            continue

        n = normalize(ad)
        if n in bulunan:
            onceki = bulunan[n]
            # 🪤 Çift dist-info gerçek bir arıza: 2026-09-04'te tqdm + certifi
            # eski sürümün metadata artığını taşıyordu. importlib.metadata
            # şansa göre cevap verir; denetim araçları iki kayıt görür.
            cift.append(f"ÇİFT KAYIT: {ad} → {onceki[1]} ({onceki[2]}) ve {surum} ({di.name})")
            continue
        bulunan[n] = (ad, surum, di.name)

    if cift:
        for c in cift:
            print(f"  ✗ {c}", file=sys.stderr)
        raise SystemExit(f"✗ {kutu}: {len(cift)} bozuk kayıt — kilit üretilmedi")

    return [(ad, surum) for _, (ad, surum, _) in sorted(bulunan.items())]


def metin(kutu: str, kayitlar: list[tuple[str, str]]) -> str:
    kilit = KUTULAR[kutu][1].relative_to(KOK)
    govde = "\n".join(f"{ad}=={surum}" for ad, surum in kayitlar)
    return BASLIK.format(kutu=kutu, kilit=kilit) + govde + "\n"


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--check", action="store_true",
                    help="yazma, yalnız denetle (bayat/eksikse çıkış 1)")
    ap.add_argument("--kutu", choices=sorted(KUTULAR),
                    help="yalnız bu kutu (varsayılan: hepsi). Tek kutuyu denetlerken "
                         "hata mesajı doğru kutuyu gösterir — ikisini birden koşup "
                         "'hangisi bayat' sorusunu okuyucuya bırakma.")
    a = ap.parse_args()

    hedef = {a.kutu: KUTULAR[a.kutu]} if a.kutu else KUTULAR

    sorun = 0
    for kutu, (_, kilit) in hedef.items():
        sp = site_packages(kutu)
        if sp is None:
            # Kutu yoksa denetim SESSİZ geçilmez ama hata da değil: Windows
            # kutusu her makinede üretilmiş olmayabilir. Kilit dosyası duruyorsa
            # CI onu taramaya devam eder.
            print(f"⊘ {kutu}: kutu yok — atlandı"
                  f"{' (kilit dosyası duruyor)' if kilit.is_file() else ''}")
            continue

        kayitlar = envanter(sp, kutu)
        yeni = metin(kutu, kayitlar)
        eski = kilit.read_text(encoding="utf-8") if kilit.is_file() else None

        if a.check:
            if eski is None:
                print(f"✗ {kutu}: kilit dosyası YOK → {kilit.relative_to(KOK)}")
                sorun += 1
            elif eski != yeni:
                e = {s for s in eski.splitlines() if s and not s.startswith("#")}
                y = {s for s in yeni.splitlines() if s and not s.startswith("#")}
                print(f"✗ {kutu}: kilit BAYAT ({len(kayitlar)} paket kutuda)")
                for s in sorted(y - e):
                    print(f"    + {s}   (kutuda var, kilitte yok)")
                for s in sorted(e - y):
                    print(f"    - {s}   (kilitte var, kutuda yok)")
                sorun += 1
            else:
                print(f"✓ {kutu}: kilit güncel ({len(kayitlar)} paket)")
        else:
            if eski == yeni:
                print(f"= {kutu}: değişiklik yok ({len(kayitlar)} paket)")
            else:
                kilit.write_text(yeni, encoding="utf-8")
                print(f"✓ {kutu}: {kilit.relative_to(KOK)} yazıldı ({len(kayitlar)} paket)")

    if a.check and sorun:
        print(f"\n✗ {sorun} kutu senkron değil — `python3 scripts/bundle-envanter.py` koş")
    return 1 if sorun else 0


if __name__ == "__main__":
    raise SystemExit(main())
