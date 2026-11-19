#!/usr/bin/env python3
"""İlk açık sürüm: geçmişi sıfırdan TEK commit'lik depo hazırla — KURU KOŞU.

Karar 10-27 #5: "aynı depo, geçmiş sıfırdan (tek temiz başlangıç commit'i)".
Kişisel izler eski commit'lerde; açılışta yalnız bugünün ağacı gider.

Bu betik HİÇBİR ŞEY İTMEZ. Geçici bir dizinde yeni bir depo kurar, REF'in
ağacını ebeveynsiz tek commit olarak yazar, kapıları o depoda koşar ve yayın
adımlarını ekrana basar. Push kodu bilerek yok (test_ilk_surum_tek_commit.py
bunu ölçer); yayını depo sahibi elle yapar.

    python3 scripts/ilk_surum_tek_commit.py                 # REF=HEAD
    python3 scripts/ilk_surum_tek_commit.py --ref oss/ilk-a --hedef /tmp/yeni
    python3 scripts/ilk_surum_tek_commit.py --kapisiz        # yalnız yapı (hızlı)

Çıkış 0 = tek commit hazır ve bütün kapılar yeşil. CHANGELOG'daki ilk sürüm
başlığında "açılış günü" yer tutucusu duruyorsa (gerçek tarih yoksa) kırmızı;
bu kapı yalnız burada koşar, CI'daki günlük main kapıları onu görmez.

⚠️ 2026-11-02 bulgusu: GitHub `refs/pull/*` ref'lerini sildirmez. Mevcut depoda
PR varsa `main`'i zorla itmek eski commit'leri PR sayfalarından erişilebilir
bırakır. Bu yüzden basılan önerilen yol "depoyu sil + aynı adla boş aç + it".
"""
from __future__ import annotations

import argparse
import os
import re
import subprocess
import sys
import tempfile
from datetime import date
from pathlib import Path

DEPO = Path(__file__).resolve().parents[1]
YAZAR_AD = "ihsandeniz"
YAZAR_EPOSTA = "ihsandeniz@users.noreply.github.com"
MESAJ = "Yuki — ilk açık kaynak sürümü"
UZAK = "ihsandeniz/yuki-oss"
# GitHub 100 MB'ın üstünü reddeder; 50 MB'da uyarır. Altında kalmak yetmez,
# o boyda bir dosya zaten depoya girmemeli (model/kutu) → 50 MB = kırmızı.
BUYUK_DOSYA = 50 * 1024 * 1024
# CHANGELOG'daki ilk sürüm başlığı açılışta gerçek tarih taşımalı:
#   ## [1.0.0] - 2026-11-20 — first open-source release
# "açılış günü" gibi yer tutucu kalırsa İngilizce changelog'a Türkçe metin çıkar.
SURUM_BASLIGI = re.compile(r"^## \[(\d+\.\d+\.\d+)\] - (\d{4}-\d{2}-\d{2})(?:\s|$)")
YER_TUTUCU = re.compile(r"açılış günü|acilis gunu|YYYY-MM-DD|\bTBD\b|\bunreleased\b", re.I)


def git(*arg: str, cwd: Path, env: dict | None = None) -> str:
    r = subprocess.run(["git", *arg], cwd=cwd, capture_output=True, text=True, env=env)
    if r.returncode != 0:
        raise RuntimeError(f"git {' '.join(arg)}: {r.stderr.strip()}")
    return r.stdout.strip()


def tek_commit_olustur(depo: Path, ref: str, hedef: Path) -> dict:
    """hedef'te yeni depo: REF'in ağacı, ebeveynsiz tek commit, dal main.

    Eski nesneler fetch ile gelir, sonra reflog + gc ile budanır; dogrula()
    depoda tek commit nesnesi kaldığını ayrıca ölçer.
    """
    agac = git("rev-parse", f"{ref}^{{tree}}", cwd=depo)
    kaynak = git("rev-parse", "--short", ref, cwd=depo)
    hedef.mkdir(parents=True, exist_ok=True)
    if any(hedef.iterdir()):
        raise RuntimeError(f"hedef boş değil: {hedef}")
    git("init", "-q", "-b", "main", cwd=hedef)
    git("fetch", "-q", "--no-tags", str(depo), ref, cwd=hedef)
    env = {**os.environ,
           "GIT_AUTHOR_NAME": YAZAR_AD, "GIT_AUTHOR_EMAIL": YAZAR_EPOSTA,
           "GIT_COMMITTER_NAME": YAZAR_AD, "GIT_COMMITTER_EMAIL": YAZAR_EPOSTA}
    commit = git("commit-tree", agac, "-m", MESAJ, cwd=hedef, env=env)
    git("update-ref", "refs/heads/main", commit, cwd=hedef)
    git("checkout", "-q", "main", cwd=hedef)
    # FETCH_HEAD eski geçmişi tutuyor; sil, reflog'u boşalt, buda.
    (hedef / ".git" / "FETCH_HEAD").unlink(missing_ok=True)
    git("reflog", "expire", "--expire=now", "--all", cwd=hedef)
    git("gc", "-q", "--prune=now", cwd=hedef)
    return {"agac": agac, "commit": commit, "kaynak": kaynak}


def dogrula(hedef: Path, beklenen_agac: str) -> list[str]:
    """Yapı kapıları — her biri ayrı hata satırı döner (boş liste = yeşil)."""
    hata: list[str] = []
    commitler = git("rev-list", "--all", cwd=hedef).split()
    if len(commitler) != 1:
        hata.append(f"tek commit değil: {len(commitler)} commit erişilebilir")
    nesne = git("cat-file", "--batch-all-objects", "--batch-check=%(objecttype)", cwd=hedef)
    n_commit = nesne.split().count("commit")
    if n_commit != 1:
        hata.append(f"depoda {n_commit} commit nesnesi var (eski geçmiş budanmadı)")
    ebeveyn = git("rev-list", "--parents", "-n1", "HEAD", cwd=hedef).split()[1:]
    if ebeveyn:
        hata.append(f"commit'in ebeveyni var: {ebeveyn}")
    agac = git("rev-parse", "HEAD^{tree}", cwd=hedef)
    if agac != beklenen_agac:
        hata.append(f"ağaç farklı: {agac} ≠ {beklenen_agac}")
    yazar = git("log", "-1", "--format=%an <%ae>|%cn <%ce>", cwd=hedef)
    if yazar != f"{YAZAR_AD} <{YAZAR_EPOSTA}>|{YAZAR_AD} <{YAZAR_EPOSTA}>":
        hata.append(f"yazar/işleyen yanlış: {yazar}")
    etiket = git("tag", "-l", cwd=hedef)
    if etiket:
        hata.append(f"etiket taşındı: {etiket.split()}")
    for satir in git("ls-tree", "-r", "-l", "HEAD", cwd=hedef).splitlines():
        meta, yol = satir.split("\t", 1)
        boyut = meta.split()[3]
        if boyut != "-" and int(boyut) >= BUYUK_DOSYA:
            hata.append(f"büyük dosya ({int(boyut) // (1024 * 1024)} MB): {yol}")
    return hata


def changelog_dogrula(hedef: Path) -> list[str]:
    """Açılış kapısı: CHANGELOG'daki ilk sürüm başlığı gerçek ISO tarih taşımalı.

    Yalnız bu betikte (açılış kuru koşusu) koşar; CI'daki günlük kapılara
    bağlı değil — bugünkü main yer tutucuyla yeşil kalır, açılış kırmızı olur.
    """
    yol = hedef / "CHANGELOG.md"
    if not yol.is_file():
        return ["CHANGELOG.md yok"]
    baslik = next((s for s in yol.read_text(encoding="utf-8").splitlines()
                   if s.startswith("## [")), None)
    if baslik is None:
        return ["CHANGELOG.md: '## [x.y.z] - YYYY-MM-DD' sürüm başlığı yok"]
    hata: list[str] = []
    if YER_TUTUCU.search(baslik):
        hata.append(f"CHANGELOG.md yer tutucu duruyor: {baslik.strip()!r} → gerçek tarih yaz")
    m = SURUM_BASLIGI.match(baslik)
    if not m:
        hata.append(f"CHANGELOG.md ilk sürüm başlığı tarihsiz: {baslik.strip()!r}")
    else:
        try:
            date.fromisoformat(m.group(2))
        except ValueError:
            hata.append(f"CHANGELOG.md geçersiz tarih: {m.group(2)}")
    return hata


def kapilar_kos(hedef: Path) -> list[str]:
    """CI temizlik işinin aynısı, YENİ depoda: temizlik + profil adı + gitleaks."""
    hata: list[str] = []
    adimlar = [
        ("temizlik", [sys.executable, "scripts/test_temizlik.py", str(hedef)]),
        ("profil adı", [sys.executable, "scripts/test_profil_adi.py"]),
        ("gitleaks git", ["gitleaks", "git", ".", "--no-banner", "-c", ".gitleaks.toml", "--redact"]),
    ]
    for ad, komut in adimlar:
        try:
            r = subprocess.run(komut, cwd=hedef, capture_output=True, text=True)
        except FileNotFoundError:
            hata.append(f"{ad}: araç yok ({komut[0]})")
            continue
        if r.returncode != 0:
            son = (r.stdout + r.stderr).strip().splitlines()[-3:]
            hata.append(f"{ad}: çıkış {r.returncode} — {' / '.join(son)}")
    return hata


def yayin_adimlari(hedef: Path) -> str:
    return f"""
── Yayın adımları (depo sahibi ELLE; bu betik itmez) ─────────────────────────
ÖNERİLEN — yeni boş depo, aynı ad (eski PR ref'leri de gider):
  1. gh repo delete {UZAK}            # geri alınamaz: PR/issue/ayar/sır gider
  2. gh repo create {UZAK} --private   # açmadan önce bir kez daha bak
  3. git -C {hedef} remote add origin git@github.com:{UZAK}.git
  4. git -C {hedef} push -u origin main
  5. Ayarlar: dependabot, dal koruması, Actions sırları (yeniden)
  6. CI yeşil → görünürlük public (karar 10-27 #8: hepsi bitince)

ALTERNATİF — aynı depoda main'i zorla itmek:
  ⚠️ refs/pull/* (şu an 17 PR) GitHub'da silinemez → eski commit'ler PR
  sayfalarından görünür kalır. Kişisel iz eski commit'lerdeyse bu yol açık bırakır.
"""


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    p.add_argument("--ref", default="HEAD")
    p.add_argument("--hedef", help="yeni deponun dizini (boş olmalı); yoksa geçici dizin")
    p.add_argument("--kapisiz", action="store_true", help="temizlik/gitleaks kapılarını atla")
    a = p.parse_args(argv)

    hedef = Path(a.hedef) if a.hedef else Path(tempfile.mkdtemp(prefix="yuki-oss-tek-"))
    bilgi = tek_commit_olustur(DEPO, a.ref, hedef)
    print(f"kaynak {a.ref} ({bilgi['kaynak']}) → {hedef}")
    print(f"tek commit {bilgi['commit'][:12]} · ağaç {bilgi['agac'][:12]}")

    hata = dogrula(hedef, bilgi["agac"]) + changelog_dogrula(hedef)
    if not a.kapisiz:
        hata += kapilar_kos(hedef)
    for h in hata:
        print(f"✗ {h}")
    if hata:
        print(f"\n🔴 {len(hata)} kapı kırmızı — yayınlanmaz.")
        return 1
    print("🟢 yapı kapıları yeşil" + ("" if a.kapisiz else " · temizlik + profil + gitleaks yeşil"))
    print(yayin_adimlari(hedef))
    return 0


if __name__ == "__main__":
    sys.exit(main())
