#!/usr/bin/env python3
"""Yuki yayın hattı — sürüm damgala, derle, yükle, vitrini güncelle, doğrula.

NEDEN VAR: Yayın elle yapıldığında hep aynı sınıf hatalar çıktı ve hepsi **sessiz**:
  · sürüm bir dosyada güncellenip öbüründe unutuldu (site v0.5.3 gösterirken ürün v0.5.4'tü)
  · boyut iddiaları elle yazıldı, ölçülmedi → vitrinde karşılıksız sayı (545 MB → gerçekte 520)
  · doğrulama yanlış URL'e yapıldı (deployment URL bayat içerik döndürüp 200 verdi)
  · linkler release'ten ÖNCE yayına çıktı → indirme 404
Bu script o dört tuzağı kapatır: **sürüm tek komutla damgalanır, boyutlar ÖLÇÜLÜR,
doğrulama içerikten yapılır, linkler artefaktlar yüklendikten sonra güncellenir.**

KULLANIM
    python3 scripts/yayin.py hazir                    # ön kontrol (hiçbir şeye dokunmaz)
    python3 scripts/yayin.py surum 0.5.6 [--sw]      # sürümü her yere damgala
    python3 scripts/yayin.py derle                    # prep + 4 SKU + ölçüm
    python3 scripts/yayin.py taslak --baslik "..."   # TASLAK release + artefaktlar + delta yükü
    python3 scripts/yayin.py vitrin                   # site linkleri + ÖLÇÜLEN boyutlar
    python3 scripts/yayin.py yayinla                  # release'i yayına al + Vercel deploy
    python3 scripts/yayin.py denetle                  # her link + iki site içerikten doğrulanır
    python3 scripts/yayin.py etiket                   # yerel v<sürüm> etiketi (yayinla da atar; push yok)

    python3 scripts/yayin.py tam 0.5.6 --baslik "..." # hepsi sırayla (her adım kapıdan geçer)
                                                      # testler kırmızıysa `hazir` durdurur (--zorla)

SIRA ÖNEMLİ: taslak → vitrin → yayinla. Vitrin release'ten önce güncellenirse
kullanıcı henüz var olmayan bir dosyaya yönlendirilir.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
import urllib.request
from pathlib import Path

KOK = Path(__file__).resolve().parent.parent          # depo kökü
VAULT = KOK.parent.parent                              # depo kökünün iki üstü — yayıncının kendi çalışma alanı (vitrin sayfaları orada)
DIST = KOK / "electron" / "dist"
REPO = "ihsandeniz/yuki-oss"

# Derlemeye AİT Wine prefix'i — kullanıcının ~/.wine'ına dokunulmaz (oyun kurulumları orada).
# Repo dışında durur ki `git status` kirlenmesin ve /tmp temizliğinde silinmesin.
WINE_PREFIX = Path.home() / ".cache" / "yuki-build-wine"

# ── SKU tanımı ────────────────────────────────────────────────────────────────
# `birim`: vitrinde hangi ölçekte gösterilir. Sayısal eşikle SEÇİLMEZ — offline
# paketler 983 MB bile olsa "0,98 GB" diye gösteriliyor (tutarlı okuma için).
SKULAR = [
    {"kalip": "Yuki-{v}-lite.AppImage",         "ad": "Hafif · Linux",       "birim": "MB"},
    {"kalip": "Yuki-{v}-win-x64-lite.zip",      "ad": "Hafif · Windows",     "birim": "MB"},
    {"kalip": "Yuki-{v}-offline.AppImage",      "ad": "Tam offline · Linux", "birim": "GB"},
    {"kalip": "Yuki-{v}-win-x64-offline.zip",   "ad": "Tam offline · Win",   "birim": "GB"},
]

# Yayınlanır ama VİTRİNDE GÖSTERİLMEZ (2026-08-09).
# tar.gz bir *kurtarma yolu*: AppImage açılmayan sistemler için. Vitrine 5. indirme
# kartı koymak seçim yorgunluğu yaratırdı — müşterinin %99'u AppImage'ı indirip
# açabiliyor. İndirme bölümündeki "Linux'ta hiçbir şey olmuyorsa" notu buna yönlendirir.
# 🔴 `yerel_varliklar` yalnız SKULAR'a bakar ve `cmd_vitrin` sayısını denetler; tar.gz'yi
# oraya koymak "önce derle" kapısını yanlış yere düşürürdü. Bu yüzden AYRI liste.
# Yoksa sessizce atlanır — varlık eksikse yükleme adımı uyarır, derleme durmaz.
EK_VARLIKLAR = [
    "Yuki-{v}-lite.tar.gz",
]

# Sürüm damgasının geçtiği her yer. Biri unutulursa `hazir` bunu yakalar.
DAMGALAR = [
    (KOK / "electron" / "package.json",             r'("version":\s*")[\d.]+(")'),
    (KOK / "backend" / "app" / "services" / "health.py", r'(APP_VERSION\s*=\s*")[\d.]+(")'),
]

# Vitrin dosyaları (ayrı git depoları — bu script commit ETMEZ, sadece yazar).
VITRIN = [
    VAULT / "projects" / "yuki-site" / "index.html",
    VAULT / "projects" / "geliştirici-web-site" / "yuki.html",
    VAULT / "projects" / "geliştirici-web-site" / "projects-data.js",
]

# Doğrulama hedefleri. URL 200 dönmesi YETMEZ — sayfa yeni sürümü İÇERMELİ.
# (Geçmiş hata: deployment URL'i 200 döndü ama bayat içerik sunuyordu.)
CANLI = [
    ("yuki-site",  "https://yuki-site-nine.vercel.app"),
    ("portfolyo",  "https://ihsandeniz.net.tr/yuki.html"),
]

# Her sitenin canlıya çıkış YOLU farklı — ikisine de `vercel deploy` demek YANLIŞ.
# Ölçüldü 2026-08-02: portfolyoya `vercel deploy --prod` başarıyla çalıştı ve BİR ŞEY
# DEĞİŞTİRMEDİ; `ihsandeniz.net.tr` yerel `.vercel/project.json`'un gösterdiği projeden
# DEĞİL, GitHub push'undan besleniyor. Denetim bunu yakaladı (site hâlâ 0.5.5 diyordu).
SITELER = [
    {"dizin": VAULT / "projects" / "yuki-site",      "ad": "yuki-site",  "yol": "vercel"},
    {"dizin": VAULT / "projects" / "geliştirici-web-site", "ad": "portfolyo",  "yol": "git"},
]


# ── yardımcılar ───────────────────────────────────────────────────────────────
def yaz(m: str) -> None:
    print(m, flush=True)


def bolum(m: str) -> None:
    yaz(f"\n\033[1;36m━━ {m} ━━\033[0m")


def hata(m: str) -> "SystemExit":
    return SystemExit(f"\033[1;31m✗ {m}\033[0m")


def kos(cmd: list[str], cwd: Path | None = None, sessiz: bool = False) -> str:
    p = subprocess.run(cmd, cwd=cwd, capture_output=True, text=True)
    if p.returncode != 0:
        raise hata(f"komut düştü: {' '.join(cmd)}\n{p.stdout}\n{p.stderr}")
    if not sessiz and p.stdout.strip():
        yaz(p.stdout.strip())
    return p.stdout


def boyut_yaz(bayt: int, birim: str) -> str:
    """Vitrindeki biçim. SI (÷1000) — etiket MB/GB olduğu için doğrusu bu.

    Bayt sayısını ELLE yazma diye var: 'yaklaşık şu kadardı' bir iddiadır, ölçüm değil.
    """
    if birim == "GB":
        return f"{bayt / 1e9:.2f}".replace(".", ",") + " GB"
    return f"{round(bayt / 1e6)} MB"


def vercel_yolu() -> str | None:
    """`vercel` nvm altında kurulu ve login kabuğu dışında PATH'te OLMAYABİLİR.
    (2026-08-02: yayın zinciri tam bu yüzden son adımda düştü.) Önce PATH, sonra nvm."""
    import shutil
    bulunan = shutil.which("vercel")
    if bulunan:
        return bulunan
    adaylar = sorted(Path.home().glob(".nvm/versions/node/*/bin/vercel"))
    return str(adaylar[-1]) if adaylar else None


def damga_oku(yol: Path, kalip: str) -> str:
    """Damga kalıbının yakaladığı sürümü döndür. Kalıp `(önek)SÜRÜM(sonek)` biçiminde."""
    m = re.search(kalip, yol.read_text())
    if not m:
        return "BULUNAMADI"
    return m.group(0)[len(m.group(1)):-len(m.group(2))]


def mevcut_surum() -> str:
    pj = json.loads((KOK / "electron" / "package.json").read_text())
    return pj["version"]


def site_surumu() -> str | None:
    """Vitrinin ilan ettiği sürüm — TÜM vitrin dosyalarından, en ESKİSİ.

    🔴 2026-08-11: eskiden yalnız `VITRIN[0]`'a bakıyordu. `cmd_vitrin` dosyaları
    sırayla yazar; biri yazılıp sonraki adımda durulursa (kısmi başarı) ikinci
    koşuda o ilk dosya "güncel" cevabını verir, `eski == v` olur ve **değişim de
    kontrol de** devre dışı kalır → geride kalan dosya sessizce yayına gider.
    Bizzat yaşandı: ilk koşu iki dosyayı yazıp hata verdi, ikinci koşu
    *"vitrin zaten v0.6.1"* dedi ve hiçbir şeyi denetlemedi.

    En YENİSİ değil en ESKİSİ döndürülür: geride kalan dosya varsa değişim
    kuralları onu da toparlasın. En yenisini almak kaçağı görünmez yapardı.
    """
    bulunan = {m for y in VITRIN
               for m in re.findall(r"Yuki-(\d+\.\d+\.\d+)-lite\.AppImage", y.read_text())}
    if not bulunan:
        return None
    return min(bulunan, key=lambda s: tuple(int(x) for x in s.split(".")))


def gh_varliklar(surum: str) -> dict[str, int]:
    """Yayınlanmış release'in artefakt boyutları — vitrindeki ESKİ metni üretmek için."""
    p = subprocess.run(
        ["gh", "release", "view", f"v{surum}", "--repo", REPO, "--json", "assets"],
        capture_output=True, text=True)
    if p.returncode != 0:
        return {}
    return {a["name"]: a["size"] for a in json.loads(p.stdout).get("assets", [])}


def yerel_varliklar(surum: str) -> dict[str, tuple[Path, int]]:
    sonuc = {}
    for s in SKULAR:
        ad = s["kalip"].format(v=surum)
        yol = DIST / ad
        if yol.exists():
            sonuc[ad] = (yol, yol.stat().st_size)
    return sonuc


def http(url: str, aralik: bool = False) -> tuple[int, str]:
    istek = urllib.request.Request(url, headers={"User-Agent": "yuki-yayin"})
    if aralik:
        istek.add_header("Range", "bytes=0-1023")
    try:
        with urllib.request.urlopen(istek, timeout=30) as r:
            return r.status, r.read(200_000).decode("utf-8", "replace")
    except urllib.error.HTTPError as e:
        return e.code, ""
    except Exception as e:
        return 0, str(e)


# ── komutlar ──────────────────────────────────────────────────────────────────
def cmd_hazir(a) -> int:
    """Yayına girmeden önce: ağaç temiz mi, sürümler tutarlı mı, testler yeşil mi."""
    bolum("ÖN KONTROL")
    sorun = 0

    kirli = kos(["git", "status", "--porcelain"], cwd=KOK, sessiz=True).strip()
    if kirli:
        yaz(f"⚠ ürün deposu kirli ({len(kirli.splitlines())} dosya) — commit edilmeden yayın çıkma")
        sorun += 1
    else:
        yaz("✓ ürün deposu temiz")

    v = mevcut_surum()
    yaz(f"  ürün sürümü: v{v}   ·   vitrin: v{site_surumu()}")
    for yol, kalip in DAMGALAR:
        deger = damga_oku(yol, kalip)
        if deger != v:
            sorun += 1
        yaz(f"  {'✓' if deger == v else '✗'} {yol.relative_to(KOK)} → {deger}")

    # 🔴 müşteriye giden kutunun kilidi taze mi (`--hizli`da bile koşar)
    # CI `backend/pybundle*-kilit.txt`'yi tarıyor ama kutuları göremiyor (gitignore).
    # Kilit bayatsa CI yalancı yeşil verir. Tazeliği ancak kutunun BULUNDUĞU yerde
    # ölçebiliriz — burası o yer, ve yayın her seferinde buradan geçiyor.
    p = subprocess.run([sys.executable, str(KOK / "scripts" / "bundle-envanter.py"), "--check"],
                       cwd=KOK, capture_output=True, text=True)
    if p.returncode != 0:
        yaz("  ✗ kutu kilidi BAYAT — CI taraması yanlış listeyi denetliyor")
        for satir in (p.stdout + p.stderr).strip().splitlines():
            yaz(f"      {satir}")
        yaz("      düzelt: python3 scripts/bundle-envanter.py")
        sorun += 1
    else:
        yaz("  ✓ kutu kilitleri güncel (pip-audit bunları tarıyor)")

    # 🔴 CI FAZ 3 (2026-10-10): testler kırmızıyken bu adım eskiden "⚠ N sorun — yine de
    # devam edilebilir" deyip DAİMA 0 dönüyordu → `tam` zinciri kırmızı testle yayına
    # çıkabiliyordu. Artık test düşerse 1 döner ve `tam` durur. Bilinçli geçiş `--zorla`.
    # Diğer sorunlar (kirli ağaç, damga, kilit) eskisi gibi UYARI — kapsam yalnız testler.
    test_dustu = []
    if not a.hizli:
        yaz("  testler koşuyor…")
        p = subprocess.run(["npm", "test"], cwd=KOK / "electron", capture_output=True, text=True)
        if p.returncode != 0:
            yaz("  ✗ electron testleri DÜŞTÜ"); sorun += 1; test_dustu.append("electron")
            for satir in (p.stdout + p.stderr).strip().splitlines()[-10:]:
                yaz(f"      {satir}")
        else:
            yaz("  ✓ electron testleri")
        p = subprocess.run([str(KOK / "backend" / "venv" / "bin" / "python"), "-m", "pytest", "-q"],
                           cwd=KOK / "backend", capture_output=True, text=True)
        if p.returncode != 0:
            yaz("  ✗ python testleri DÜŞTÜ"); sorun += 1; test_dustu.append("python")
            for satir in [x for x in p.stdout.splitlines() if x.startswith(("FAILED", "ERROR"))][:20]:
                yaz(f"      {satir}")
            son = p.stdout.strip().splitlines()[-1:] or [""]
            yaz(f"      {son[0][:100]}")
        else:
            yaz(f"  ✓ python testleri ({p.stdout.strip().splitlines()[-1][:60]})")

    if test_dustu:
        if getattr(a, "zorla", False):
            yaz(f"\n\033[1;31m⚠ {'+'.join(test_dustu)} testleri KIRMIZI — --zorla ile BİLİNÇLİ geçildi\033[0m")
            return 0
        yaz(f"\n\033[1;31m✗ {'+'.join(test_dustu)} testleri KIRMIZI — yayın durdu "
            f"(bilinçli geçiş: --zorla)\033[0m")
        return 1

    yaz("\n" + ("\033[1;32m✓ yayına hazır\033[0m" if not sorun
                else f"\033[1;33m⚠ {sorun} sorun — yine de devam edilebilir\033[0m"))
    return 0


def cmd_surum(a) -> int:
    """Sürümü TÜM damga noktalarına yaz. Elle yazmak = birini unutmak."""
    bolum(f"SÜRÜM DAMGASI → v{a.surum}")
    if not re.fullmatch(r"\d+\.\d+\.\d+", a.surum):
        raise hata(f"geçersiz sürüm: {a.surum}")
    eski = mevcut_surum()
    for yol, kalip in DAMGALAR:
        s = yol.read_text()
        yeni, n = re.subn(kalip, lambda m: m.group(1) + a.surum + m.group(2), s)
        if n != 1:
            raise hata(f"{yol}: {n} eşleşme (1 bekleniyordu) — kalıp bayatlamış")
        yol.write_text(yeni)
        yaz(f"  ✓ {yol.relative_to(KOK)}  {eski} → {a.surum}")

    if a.sw:
        sw = KOK / "frontend" / "sw.js"
        s = sw.read_text()
        m = re.search(r"(CACHE_VERSION\s*=\s*'yuki-v)(\d+)(')", s)
        if not m:
            raise hata("sw.js CACHE_VERSION bulunamadı")
        yeni_n = int(m.group(2)) + 1
        sw.write_text(s[:m.start()] + f"{m.group(1)}{yeni_n}{m.group(3)}" + s[m.end():])
        yaz(f"  ✓ sw.js  yuki-v{m.group(2)} → yuki-v{yeni_n}")
    else:
        yaz("  · sw.js atlandı (frontend değişmediyse doğrusu bu — --sw ile bump edilir)")

    # Bayat damga taraması — ama YALNIZ sürüm gerçekten değiştiyse.
    # Aksi hâlde "eski" ile "yeni" aynı metindir ve tarama kendi yazdığımız
    # doğru damgayı bayat sanıp zinciri durdurur. 2026-08-03'te tam bu oldu:
    # sürüm elle damgalanmış, ardından `tam 0.5.8` koşulmuş, adım kendi
    # çıktısını kusur olarak raporlamıştı. `-F`: sürüm noktaları regex değil.
    if eski == a.surum:
        yaz(f"  · zaten v{a.surum} — bayat damga taraması atlandı (eski = yeni)")
    else:
        kalan = subprocess.run(
            ["grep", "-rnF", eski, "electron/package.json", "backend/app/services/health.py"],
            cwd=KOK, capture_output=True, text=True).stdout.strip()
        if kalan:
            raise hata(f"eski sürüm hâlâ duruyor:\n{kalan}")
    yaz(f"\n\033[1;32m✓ v{a.surum} damgalandı\033[0m")
    return 0


def cmd_derle(a) -> int:
    bolum("DERLEME (4 SKU)")
    v = mevcut_surum()
    yaz(f"  sürüm: v{v}   ·   npm run prep + build:all")
    yaz("  (uzun sürer — MSVC DLL gömme + shell-id + 4 paket)\n")

    # 🔴 Windows SKU'su `Yuki.exe`'ye sürüm/ikon gömmek için `wine rcedit-ia32.exe` koşar.
    # Kullanıcının ~/.wine prefix'i kullanılırsa derleme SESSİZCE ASILIR: `wineboot --init`
    # eski prefix'i yeni Wine sürümü altında yükseltmeye çalışıp **Wine Mono kurulum
    # penceresini** açar (`control.exe appwiz.cpl install_mono`) ve cevap bekler — pencere
    # görünmediği için sonsuza kadar. İmza: %0 CPU, ağ bağlantısı yok, tek satır log yok,
    # dosyalara saatlerce dokunulmaz. Ölçüldü **iki kez**: 2026-08-31 (3 sa) · 2026-09-04 (2 sa 13 dk).
    # İlkinde çözüm yalnız ledger'a yazıldı, koda geçmediği için ikinci kez tekrarladı.
    # → Derlemeye kendi prefix'ini ver, mono/gecko kurulumunu kapat. Temiz prefix'te
    #   `wineboot --init` saniyeler içinde döner. ⚠️ ~/.wine'ı SİLME — kullanıcının
    #   oyun/uygulama kurulumları orada (bu makinede TLauncher).
    ortam = {
        **os.environ,
        "WINEPREFIX": str(WINE_PREFIX),
        "WINEDLLOVERRIDES": "mscoree,mshtml=",   # mono + gecko kurulum penceresini kapat
        "WINEDEBUG": "-all",
    }
    WINE_PREFIX.mkdir(parents=True, exist_ok=True)
    yaz(f"  wine prefix: {WINE_PREFIX}  (kullanıcının ~/.wine'ı kullanılmaz)\n")

    # 🔴 2026-09-18: `build:all` KAYNAK `electron/package.json`'ı EZİYOR — `scripts`
    # bloğunun tamamı (11 komut: prep/build/test/update:payload…) siliniyor. Sebep
    # `extraMetadata` (yukiSku damgası): `directories.app` tanımlı olmadığı için
    # electron-builder uygulama paketi olarak `electron/`i alıyor ve damgayı
    # oraya, yani kaynak dosyaya yazıyor.
    # Fark edilmesi zor: sürüm alanı DOĞRU kalıyor, yalnız `scripts` gidiyor —
    # bir sonraki turda `npm run prep` "missing script" der ve suçlu derleme
    # sanılmaz. v0.6.16 turunda elle yakalandı, kalıcı koruma burada.
    yedek = (KOK / "electron" / "package.json").read_text(encoding="utf-8")

    p = subprocess.run(["npm", "run", "build:all"], cwd=KOK / "electron", env=ortam)
    if p.returncode != 0:
        raise hata("derleme düştü")

    hedef = KOK / "electron" / "package.json"
    if hedef.read_text(encoding="utf-8") != yedek:
        hedef.write_text(yedek, encoding="utf-8")
        yaz("  \033[1;33m⚠ electron/package.json derlemede değişti — geri yüklendi"
            " (extraMetadata kaynak dosyaya yazıyor)\033[0m")

    bolum("ÖLÇÜM")
    yerel = yerel_varliklar(v)
    eksik = [s["kalip"].format(v=v) for s in SKULAR if s["kalip"].format(v=v) not in yerel]
    if eksik:
        raise hata("üretilmeyen artefakt:\n  " + "\n  ".join(eksik))
    for s in SKULAR:
        ad = s["kalip"].format(v=v)
        _, bayt = yerel[ad]
        yaz(f"  {s['ad']:<22} {ad:<34} {bayt:>13,} B  → vitrin: {boyut_yaz(bayt, s['birim'])}")
    return 0


def cmd_taslak(a) -> int:
    """TASLAK release + artefaktlar + delta yükü.

    Taslak kullanılır çünkü `gh release create` yayınlanmış bir release'e dosyaları
    TEK TEK yükler: yayın anıyla son dosyanın bitişi arasında kullanıcı yarım bir
    release görür. Taslakta yükleme biter, sonra tek hamlede yayına alınır.
    """
    bolum("TASLAK RELEASE")
    v = mevcut_surum()
    yerel = yerel_varliklar(v)
    if len(yerel) != len(SKULAR):
        raise hata("önce `derle` — artefaktlar eksik")

    bolum("DELTA YÜKÜ")
    onceki = site_surumu()
    kos([sys.executable, "scripts/update_payload.py", "build"], cwd=KOK)
    delta = sorted((KOK / "dist" / "updates").glob(f"yuki-update-{v}.*"))
    if len(delta) != 2:
        raise hata(f"delta yükü eksik: {[d.name for d in delta]}")

    man = json.loads((KOK / "dist" / "updates" / f"yuki-update-{v}.json").read_text())

    # 🔴 2026-08-08: MEDYA YÜKÜ. Yukarıdaki glob `yuki-update-*` olduğu için medya
    # arşivi (`yuki-media-*`) listeye HİÇ girmiyordu → release'e yüklenmez,
    # manifest onu iddia ettiği için istemci indirmeye kalkar ve 404 alırdı.
    # Yani güncelleme, tam da medyanın değiştiği sürümde patlardı.
    # Liste manifest'in İDDİASINDAN türetiliyor, elle yazılmıyor: iddia ile
    # yüklenen dosya ayrışırsa burada durur, müşteride değil.
    medya_ad = man.get("media_payload_name")
    if medya_ad:
        m = KOK / "dist" / "updates" / medya_ad
        if not m.is_file():
            raise hata(f"manifest {medya_ad} diyor ama dosya yok — istemci 404 alırdı")
        delta = list(delta) + [m]
        yaz(f"  · medya yükü: {m.name}  · media_id {man.get('media_id', '?')}")
    else:
        yaz("  · medya yükü yok (bu sürümde medya değişmedi ya da --medya-atla)")

    for d in delta:
        yaz(f"  ✓ {d.name}  ({d.stat().st_size:,} B)")
    yaz(f"  shell_id: {man.get('shell_id', '?')}")
    onceki_man = None
    if onceki:
        try:
            _, g = http(f"https://github.com/{REPO}/releases/download/v{onceki}/yuki-update-{onceki}.json")
            onceki_man = json.loads(g) if g else None
        except Exception:
            pass
    if onceki_man and onceki_man.get("shell_id") != man.get("shell_id"):
        yaz(f"  \033[1;33m⚠ shell_id DEĞİŞTİ (v{onceki} → v{v}) — mevcut kurulumlar delta ALAMAZ,"
            f"\n    tam paket indirmeye yönlendirilecekler. Beklenen bir şeyse sorun yok.\033[0m")
    elif onceki_man:
        yaz(f"  ✓ shell_id v{onceki} ile aynı — mevcut kurulumlar delta ile güncellenebilir")

    bolum("YÜKLEME")
    varsa = subprocess.run(["gh", "release", "view", f"v{v}", "--repo", REPO],
                           capture_output=True, text=True).returncode == 0
    if not varsa:
        kos(["gh", "release", "create", f"v{v}", "--repo", REPO, "--draft",
             "--title", a.baslik or f"Yuki v{v}", "--notes", a.notlar or ""], sessiz=True)
        yaz(f"  ✓ taslak release v{v} oluşturuldu")
    else:
        yaz(f"  · v{v} zaten var — üzerine yükleniyor")
    # Tek tek + boyut eşleşiyorsa ATLA. Sebep: 3 GB'lık yükleme yarıda kesilebiliyor
    # (ölçüldü 2026-08-02: SIGTERM, 6 varlıktan 3'ü yüklenmiş). Toplu `upload --clobber`
    # yeniden çalıştırıldığında biten dosyaları da baştan gönderirdi. Artık komut
    # DEVAM EDER — kesilirse tekrar çalıştırmak kaldığı yerden sürdürür.
    # Liste HER dosyadan önce tazelenir. Başta bir kez okumak yetmiyor: kesilen bir
    # çalıştırmanın `gh` alt süreci arkada devam edip dosyayı bitirebiliyor (ölçüldü).
    # Bayat listeyle `--clobber` o dosyayı SİLİP baştan gönderir — 984 MB boşuna.
    dosyalar = [yerel[s["kalip"].format(v=v)][0] for s in SKULAR] + list(delta)
    # Ek varlıklar (tar.gz gibi): VARSA yüklenir, yoksa sessizce atlanır. SKULAR gibi
    # zorunlu değiller — biri üretilmemişse yayın durmamalı, çünkü vitrin onlara
    # dayanmıyor. Eksikliği burada görünür olsun diye tek satır yazılır.
    for kalip in EK_VARLIKLAR:
        ek = DIST / kalip.format(v=v)
        if ek.exists():
            dosyalar.append(ek)
        else:
            yaz(f"  · {ek.name} yok — atlandı (zorunlu değil)")
    for d in dosyalar:
        bayt = d.stat().st_size
        yuklu = {a["name"]: a["size"] for a in json.loads(subprocess.run(
            ["gh", "release", "view", f"v{v}", "--repo", REPO, "--json", "assets"],
            capture_output=True, text=True).stdout or '{"assets":[]}').get("assets", [])}
        if yuklu.get(d.name) == bayt:
            yaz(f"  · {d.name}  (zaten yüklü, {bayt:,} B)")
            continue
        yaz(f"  ↑ {d.name}  ({bayt:,} B)…")
        kos(["gh", "release", "upload", f"v{v}", str(d), "--repo", REPO, "--clobber"], sessiz=True)
        yaz(f"  ✓ {d.name}")
    return 0


def _yorumsuz(s: str) -> str:
    """Yorumları çıkarır — `kalan` kontrolü YALNIZ müşterinin gördüğü metne bakmalı.

    2026-08-09'da yakalandı: v0.6.0'ı kararlıya alırken kapı düştü, sebebi iki
    HTML yorumuydu — `<!-- 2026-08-06 (v0.5.9): iki boşluk kapatıldı. -->` gibi
    TARİHSEL notlar. Bunlar vitrin metni değil; kimse onlara bakıp eski paketi
    indirmez. Kök neden asimetri: `degisim` yalnız `Yuki-<v>-` kalıbını ve boyut
    metnini değiştiriyor, kontrol ise ÇIPLAK sürüm dizisini arıyordu → değiştirmediği
    bir şeyi "kaldı" diye rapor ediyordu. Yorumlar biriktikçe kapı her sürümde
    yanlış alarm verir ve **gerçek bir kaçağı da bu gürültünün içinde kaybederdi.**

    Satır içi `//` bilerek DIŞARIDA: indirme linkleri `https://…` içeriyor ve sürüm
    damgası tam da orada geçmeli — onu elemek kapının asıl işini kör ederdi.
    """
    s = re.sub(r"<!--.*?-->", "", s, flags=re.S)      # HTML
    s = re.sub(r"/\*.*?\*/", "", s, flags=re.S)       # JS blok
    s = re.sub(r"(?m)^\s*//.*$", "", s)               # JS satır (yalnız satır başı)
    return s


def cmd_vitrin(a) -> int:
    """Site linkleri + ÖLÇÜLEN boyutlar. Eski boyut metni yayınlanmış release'ten türetilir."""
    bolum("VİTRİN")
    v = mevcut_surum()
    eski = site_surumu()
    if eski == v:
        yaz(f"  · vitrin zaten v{v}")
    yerel = yerel_varliklar(v)
    if len(yerel) != len(SKULAR):
        raise hata("önce `derle`")
    eski_boyut = gh_varliklar(eski) if eski else {}

    degisim: list[tuple[str, str]] = []
    if eski and eski != v:
        degisim.append((f"Yuki-{eski}-", f"Yuki-{v}-"))
    for s in SKULAR:
        yeni_ad = s["kalip"].format(v=v)
        eski_ad = s["kalip"].format(v=eski) if eski else None
        yb = boyut_yaz(yerel[yeni_ad][1], s["birim"])
        if eski_ad and eski_ad in eski_boyut:
            eb = boyut_yaz(eski_boyut[eski_ad], s["birim"])
            if eb != yb:
                degisim.append((eb, yb))
                yaz(f"  boyut {s['ad']:<22} {eb} → {yb}")
            else:
                yaz(f"  boyut {s['ad']:<22} {yb} (değişmedi)")
        else:
            yaz(f"  \033[1;33m⚠ {s['ad']}: eski boyut bilinmiyor, metin ELLE kontrol edilmeli"
                f" (ölçülen: {yb})\033[0m")

    for yol in VITRIN:
        s = yol.read_text()
        toplam = 0
        for a_, b_ in degisim:
            s, n = re.subn(re.escape(a_), b_, s)
            toplam += n
        if toplam:
            yol.write_text(s)
        yaz(f"  {'✓' if toplam else '·'} {yol.relative_to(VAULT)}  ({toplam} değişiklik)")

    # 🔴 2026-08-11: kapı ÜRÜNE AİT damga arar, çıplak sürüm dizisi DEĞİL.
    # Eskiden `eski in metin` yazıyordu → `projects-data.js`'teki
    # `status: '🟢 Aktif — v0.6.0'` satırını ürün kaçağı sandı ve yayını durdurdu.
    # O satır ürünün değil, portfolyodaki **KİŞİSEL Alice** kartının durumu
    # (aynı dosyada GalleryWeb'in `v1.1.0`'ı 10 kez geçiyor — çıplak arama onları
    # da yakalayacaktı). Ölçüldü: `projects-data.js` hiçbir `Yuki-<v>-` damgası
    # taşımıyor, yani ürün adına söyleyecek sözü yok.
    # 08-09'daki `_yorumsuz()` düzeltmesiyle (`175c565`) aynı sınıf: kapı kendi
    # dokunmadığı bir şeyi "kaldı" sanıyordu. Yanlış alarmın asıl zararı kendisi
    # değil, NORMALLEŞMESİ — her sürümde bağıran kapı, gerçek kaçağı da geçirtir.
    kalan = [str(y.relative_to(VAULT)) for y in VITRIN
             if eski and eski != v and f"Yuki-{eski}-" in _yorumsuz(y.read_text())]
    if kalan:
        raise hata("eski sürüm vitrinde kaldı: " + ", ".join(kalan))
    return 0


def _damga_yollari() -> list[str]:
    """Sürüm damgasını taşıyan, depoya göreli yollar (+ varsa sw.js)."""
    yollar = [str(yol.relative_to(KOK)) for yol, _ in DAMGALAR]
    if (KOK / "frontend" / "sw.js").exists():
        yollar.append("frontend/sw.js")
    return yollar


def etiket_engeli(v: str) -> str | None:
    """`v<sürüm>` etiketi HEAD'e atılabilir mi? Atılamazsa nedenini döndür, atılabilirse None.

    CI FAZ 3 (2026-10-10): sürüm izi yoktu. Hangi commit'in derlendiği commit mesajından
    tahmin ediliyordu (v0.8.1 → 2a80ca7 mi 4c776c9 mu?). Etiket bu yüzden YALNIZ damgası
    commit'lenmiş HEAD'e atılır; ağaçtaki commit'lenmemiş damga derlenen kaynağın
    HEAD'de olmadığı anlamına gelir.
    """
    ad = f"v{v}"
    if kos(["git", "tag", "-l", ad], cwd=KOK, sessiz=True).strip():
        hedef = kos(["git", "rev-parse", f"{ad}^{{commit}}"], cwd=KOK, sessiz=True).strip()
        bas = kos(["git", "rev-parse", "HEAD"], cwd=KOK, sessiz=True).strip()
        if hedef != bas:
            return (f"etiket {ad} zaten var ve başka commit'te ({hedef[:7]}, HEAD {bas[:7]}) — "
                    "ikinci kez atılmaz, sürümü artır ya da etiketi elle incele")
        return None   # aynı commit'te: yeniden koşu (ör. --deploy tekrarı) serbest
    p = subprocess.run(["git", "show", "HEAD:electron/package.json"], cwd=KOK,
                       capture_output=True, text=True)
    bas_v = json.loads(p.stdout).get("version") if p.returncode == 0 else None
    if bas_v != v:
        return (f"HEAD'deki sürüm v{bas_v}, yayınlanan v{v} — damga commit'lenmemiş. "
                f"Önce: git commit -m 'surum: v{v}' -- {' '.join(_damga_yollari())}")
    kirli = kos(["git", "status", "--porcelain", "--", *_damga_yollari()], cwd=KOK, sessiz=True).strip()
    if kirli:
        return f"damga dosyalarında commit'lenmemiş değişiklik var:\n{kirli}"
    return None


def etiket_at(v: str) -> None:
    """Yerel, açıklamalı etiket. PUSH YOK — `git push origin v<sürüm>` geliştirici'da."""
    ad = f"v{v}"
    if kos(["git", "tag", "-l", ad], cwd=KOK, sessiz=True).strip():
        yaz(f"  · etiket {ad} zaten HEAD'de")
        return
    kos(["git", "tag", "-a", ad, "-m", f"Yuki {ad}"], cwd=KOK, sessiz=True)
    yaz(f"  ✓ yerel etiket {ad} → {kos(['git', 'rev-parse', '--short', 'HEAD'], cwd=KOK, sessiz=True).strip()}"
        f"  (gönder: git push origin {ad})")


def cmd_surum_commit(a) -> int:
    """`tam` zincirinde damgadan hemen sonra: YALNIZ damga dosyalarını commit'le.

    `surum` dosyaları yazar ama commit etmez; `tam` zincirinde bu adım olmasaydı `yayinla`
    anında HEAD damgasız kalır ve etiket derlenmeyen bir commit'e giderdi. `hazir` ağacın
    temiz olduğunu zaten doğruladı, yani commit'e damgadan başka şey girmez.
    """
    v = mevcut_surum()
    yollar = _damga_yollari()
    if not kos(["git", "status", "--porcelain", "--", *yollar], cwd=KOK, sessiz=True).strip():
        yaz(f"  · damga zaten commit'li (v{v})")
        return 0
    kos(["git", "add", "--", *yollar], cwd=KOK, sessiz=True)
    kos(["git", "commit", "-q", "-m", f"surum: v{v}", "--", *yollar], cwd=KOK, sessiz=True)
    yaz(f"  ✓ damga commit'lendi: surum: v{v}")
    return 0


def cmd_etiket(a) -> int:
    """Etiketi elle at (ör. `yayinla` etiketten önce durduysa, commit sonrası)."""
    v = mevcut_surum()
    engel = etiket_engeli(v)
    if engel:
        yaz(f"  ✗ {engel}")
        return 1
    etiket_at(v)
    return 0


def cmd_yayinla(a) -> int:
    bolum("YAYINA ALMA")
    v = mevcut_surum()

    # Etiket denetimi YAYINDAN ÖNCE: engel varsa release'e hiç dokunulmaz
    # (yayında olup izi olmayan sürüm, tam da kapatılan sorun).
    engel = etiket_engeli(v)
    if engel:
        yaz(f"  ✗ {engel}")
        return 1

    # ── ÖN-YAYIN (2026-08-08) ────────────────────────────────────────────────
    # Yeni bir sürümü önce TEK makinede denemek için. `--on-yayin` ile:
    #   · release `prerelease` işaretlenir → `/releases/latest` onu DÖNDÜRMEZ,
    #     yani `stable` kanalındaki müşteriler görmez (updater.js kanal mantığı)
    #   · `--latest` verilmez → GitHub'ın "Latest" rozeti eski sürümde kalır
    #   · siteler GÜNCELLENMEZ, `--deploy` verilse bile: vitrin hâlâ yayındaki
    #     sürümü satmalı. Ön-yayını vitrine yazmak, indirme linkini test
    #     edilmemiş bir pakete çevirirdi.
    if a.on_yayin:
        kos(["gh", "release", "edit", f"v{v}", "--repo", REPO,
             "--draft=false", "--prerelease"], sessiz=True)
        yaz(f"  ✓ release v{v} ÖN-YAYIN olarak yayında")
        etiket_at(v)
        yaz("  · müşteriler görmez (stable kanalı `latest`e bakar)")
        yaz("  · siteler bilinçli olarak GÜNCELLENMEDİ — vitrin yayındaki sürümü satar")
        yaz(f"\n  \033[1;33m→ Test makinesinde: ⚙ AYAR → 🎫 LİSANS → Güncelleme kanalı = beta\033[0m")
        yaz(f"  \033[1;33m→ Test bitince stable'a al:  python3 scripts/yayin.py yayinla --deploy\033[0m")
        return 0

    kos(["gh", "release", "edit", f"v{v}", "--repo", REPO, "--draft=false",
         "--prerelease=false", "--latest"], sessiz=True)
    yaz(f"  ✓ release v{v} yayında (stable)")
    etiket_at(v)
    if not a.deploy:
        yaz("  · siteler atlandı (--deploy ile çıkar)")
        return 0

    vc = vercel_yolu()
    for s in SITELER:
        bolum(f"SİTE — {s['ad']}  ({s['yol']})")
        if s["yol"] == "git":
            # Bu site GitHub entegrasyonundan besleniyor: commit + push = deploy.
            kirli = kos(["git", "status", "--porcelain"], cwd=s["dizin"], sessiz=True).strip()
            if kirli:
                yaz(f"  ✗ commit edilmemiş değişiklik var — önce commit et:\n{kirli}")
                continue
            kos(["git", "push", "origin", "HEAD"], cwd=s["dizin"], sessiz=True)
            yaz("  ✓ push edildi — GitHub entegrasyonu deploy edecek (~1 dk)")
        else:
            if not vc:
                yaz("  ✗ vercel bulunamadı (PATH'te de nvm'de de)"); continue
            p = subprocess.run([vc, "deploy", "--prod", "--yes"], cwd=s["dizin"],
                               capture_output=True, text=True)
            # Adresi ÇIKTIDAN OKU, proje adından üretme (Vercel alias'ı 41 karakterde kırpar).
            m = re.search(r"https://\S+?[\"\s]", p.stdout + p.stderr + " ")
            yaz(f"  {'✓' if p.returncode == 0 else '✗'} {m.group(0).strip(chr(34)) if m else '(adres okunamadı)'}")
            if p.returncode != 0:
                yaz((p.stderr or p.stdout).strip()[-500:])
    yaz("\n  \033[1;33m→ deploy'lar yayılana kadar 1-2 dk; sonra `denetle` çalıştır\033[0m")
    return 0


def cmd_denetle(a) -> int:
    """İçerikten doğrula. 200 dönmesi bir şey KANITLAMAZ — bayat içerik de 200 döner."""
    bolum("DENETİM")
    v = mevcut_surum()
    kotu = 0

    yaz("  indirme linkleri (Range ile — dosya gerçekten var mı):")
    for s in SKULAR:
        ad = s["kalip"].format(v=v)
        url = f"https://github.com/{REPO}/releases/latest/download/{ad}"
        kod, _ = http(url, aralik=True)
        ok = kod in (200, 206)
        kotu += 0 if ok else 1
        yaz(f"    {'✓' if ok else '✗'} {kod}  {ad}")

    for ad in (f"yuki-update-{v}.json", f"yuki-update-{v}.tar.gz"):
        kod, _ = http(f"https://github.com/{REPO}/releases/download/v{v}/{ad}", aralik=True)
        ok = kod in (200, 206)
        kotu += 0 if ok else 1
        yaz(f"    {'✓' if ok else '✗'} {kod}  {ad}  (delta)")

    yaz("\n  canlı siteler (İÇERİK kontrolü — sadece 200 yetmez):")
    for ad, url in CANLI:
        kod, govde = http(url)
        icerir = f"Yuki-{v}-" in govde
        bayat = re.findall(r"Yuki-(\d+\.\d+\.\d+)-", govde)
        ok = kod == 200 and icerir and set(bayat) == {v}
        kotu += 0 if ok else 1
        yaz(f"    {'✓' if ok else '✗'} {kod}  {ad:<12} {url}")
        if not ok:
            yaz(f"        sayfadaki sürümler: {sorted(set(bayat)) or '—'} (beklenen: {v})")

    yaz("\n" + ("\033[1;32m✓ denetim temiz\033[0m" if not kotu
                else f"\033[1;31m✗ {kotu} kontrol düştü\033[0m"))
    return 1 if kotu else 0


def cmd_tam(a) -> int:
    for ad, fn, arg in [
        ("hazir", cmd_hazir, argparse.Namespace(hizli=False, zorla=a.zorla)),
        ("surum", cmd_surum, argparse.Namespace(surum=a.surum, sw=a.sw)),
        ("surum-commit", cmd_surum_commit, argparse.Namespace()),
        ("derle", cmd_derle, argparse.Namespace()),
        ("taslak", cmd_taslak, argparse.Namespace(baslik=a.baslik, notlar=a.notlar)),
        # Ön-yayında vitrin GÜNCELLENMEZ ve denetlenmez: site hâlâ yayındaki
        # sürümü satmalı. Ön-yayını vitrine yazmak, müşterinin indirme linkini
        # test edilmemiş bir pakete çevirirdi.
        *([] if a.on_yayin else [("vitrin", cmd_vitrin, argparse.Namespace())]),
        ("yayinla", cmd_yayinla, argparse.Namespace(deploy=a.deploy, on_yayin=a.on_yayin)),
        *([] if a.on_yayin else [("denetle", cmd_denetle, argparse.Namespace())]),
    ]:
        if fn(arg):
            raise hata(f"`{ad}` adımı düştü — zincir durdu")
    return 0


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    alt = p.add_subparsers(dest="komut", required=True)

    h = alt.add_parser("hazir"); h.add_argument("--hizli", action="store_true", help="testleri atla")
    h.add_argument("--zorla", action="store_true", help="kırmızı testle BİLİNÇLİ geç (0 döner)")
    h.set_defaults(fn=cmd_hazir)

    s = alt.add_parser("surum"); s.add_argument("surum"); s.add_argument("--sw", action="store_true",
        help="frontend değiştiyse service worker cache sürümünü de artır")
    s.set_defaults(fn=cmd_surum)

    alt.add_parser("derle").set_defaults(fn=cmd_derle)

    t = alt.add_parser("taslak"); t.add_argument("--baslik"); t.add_argument("--notlar")
    t.set_defaults(fn=cmd_taslak)

    alt.add_parser("vitrin").set_defaults(fn=cmd_vitrin)

    y = alt.add_parser("yayinla"); y.add_argument("--deploy", action="store_true")
    y.add_argument("--on-yayin", action="store_true",
                   help="ön-yayın: müşteriler görmez, siteler güncellenmez "
                        "(test makinesinde kanal=beta ile alınır)")
    y.set_defaults(fn=cmd_yayinla)

    alt.add_parser("denetle").set_defaults(fn=cmd_denetle)

    alt.add_parser("etiket", help="yerel v<sürüm> etiketi (push yok)").set_defaults(fn=cmd_etiket)

    f = alt.add_parser("tam"); f.add_argument("surum"); f.add_argument("--baslik")
    f.add_argument("--notlar"); f.add_argument("--sw", action="store_true")
    f.add_argument("--zorla", action="store_true", help="hazir: kırmızı testle BİLİNÇLİ geç")
    f.add_argument("--deploy", action="store_true")
    f.add_argument("--on-yayin", action="store_true",
                   help="ön-yayın: vitrin ve denetim atlanır, müşteriler görmez")
    f.set_defaults(fn=cmd_tam)

    a = p.parse_args()
    return a.fn(a)


if __name__ == "__main__":
    sys.exit(main())
