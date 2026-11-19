#!/usr/bin/env python3
"""Delta güncelleme yükü üret + imzala (yayıncı tarafı).

NEDEN VAR (ölçüm 2026-08-02):
  Bir sürümden diğerine paketin **15.584 dosyası aynı kalıyor**, gerçekten
  değişen ~18 dosya. Buna rağmen müşteri her sürümde **440 MiB** indirip zip'i
  elle açıyordu; mevcut `updater.js` yalnız "yeni sürüm var" deyip GitHub
  sayfasını açıyordu. Ölçülen gerçek yük: **1,20 MiB** → 367× fark.

NE GİRER, NE GİRMEZ
  ✅ `backend/app/**`      — Python uygulama kodu (tamamı, 118 dosya)
  ✅ `frontend/**`         — js/css/html/modes/fonts/vendor (56 dosya)
  ✅ `frontend/assets/**`  — 33 MB medya → **AYRI yükte** (2026-08-08, aşağıya bak)
  ❌ `pybundle*/`          — Python yorumlayıcı + wheel'ler
  ❌ `Yuki.exe` · `app.asar` — Electron katmanı; çalışırken değiştirilemez

  Yük **kümülatif**: delta değil, app kodunun tamamı. Böylece hangi sürümden
  gelirse gelsin tek adımda güncellenir — zincirleme/ara-sürüm sorunu yok.

İKİ YÜK, İKİ PARMAK İZİ (2026-08-08)
  Medya eskiden hiç taşınmıyor, üstelik `shell_id`'ye giriyordu → her görsel
  değişikliği müşteriyi **440 MB tam indirmeye** yolluyordu (karakter portresi
  yenilenince bizzat yaşandı). Artık:

    yuki-update-<v>.tar.gz  → kod   (~1,2 MiB)  · her sürümde
    yuki-media-<v>.tar.gz   → medya (~33 MB)    · yalnız `media_id` değişince inilir

  İstemci `media_id`'si tutuyorsa medya yükünü İNDİRMEZ. Böylece sürümlerin
  çoğunda medya maliyeti sıfır, değiştiğinde 33 MB — ve hiçbir durumda kullanıcı
  tarayıcıya gönderilmez.

🔒 GÜVENLİK — bu bir UZAKTAN KOD ÇALIŞTIRMA kanalıdır
  Manifest **Ed25519** ile imzalanır; ürün yalnız public key taşır. İmza ya da
  payload sha256 tutmazsa istemci **hiçbir şey yazmaz**.
  Anahtar lisans anahtarından **AYRI**: lisans anahtarı sızarsa bedava Pro üretilir,
  güncelleme anahtarı sızarsa her müşteride kod çalışır. Aynı anahtara bağlamak,
  küçük bir sızıntıyı felakete çevirir. Private key repo DIŞI (`~/.alice-issuer/`).

KABUK PARMAK İZİ (`shell_id`)
  Yük yalnız app kodunu taşır; Python runtime'ı, Electron'u ve medyayı taşımaz.
  Bu üçünden biri değiştiyse yük eski kabuğa uygulanamaz (ör. yeni bir pip
  bağımlılığı isteyen kod). `shell_id` = requirements + electron sürümü + medya
  listesinin hash'i. Paket kendi `shell_id`'sini içinde taşır; tutmuyorsa istemci
  delta yerine **tam indirme**ye düşer. Bu karar insana bırakılmaz — unutulur.

Kullanım:
    python3 scripts/update_payload.py shell-id            # hesapla ve yaz
    python3 scripts/update_payload.py keygen              # imza anahtarı (BİR KEZ)
    python3 scripts/update_payload.py build --version 0.5.6
    python3 scripts/update_payload.py verify dist/updates/yuki-update-0.5.6.json
"""
from __future__ import annotations

import argparse
import base64
import hashlib
import json
import os
import re
import stat
import gzip
import io
import sys
import tarfile
from pathlib import Path

KOK = Path(__file__).resolve().parent.parent          # → depo kökü
CIKTI = KOK / "dist" / "updates"
SHELL_ID_PATH = KOK / "electron" / "shell-id.txt"
# Paketlenmiş medyanın kimliği — `shell-id.txt`in kardeşi. Pakete girer ki
# istemci "bendeki medya güncel mi" sorusunu 33 MB'ı yeniden hash'lemeden
# cevaplayabilsin (overlay uygulanmışsa cevap `current.json`'daki mediaId'dir).
MEDIA_ID_PATH = KOK / "electron" / "media-id.txt"

ISSUER_DIR = Path(os.path.expanduser("~/.alice-issuer"))
UPDATE_PRIVATE_PATH = ISSUER_DIR / "update-private.hex"

SCHEMA = 1
PRODUCT = "yuki"

# Yüke giren kökler: (kaynak dizin, arşivdeki önek)
YUK_KOKLERI = [
    (KOK / "backend" / "app", "backend/app"),
    (KOK / "frontend", "frontend"),
    # 2026-08-03: Electron katmanı da yüke girdi. Ölçüm (win-unpacked):
    # pybundle 764 MB · assets 97 MB · Electron ikilisi ~180 MB · app.asar **162 KB**.
    # Yani müşteriye 440 MB indirten şey paketin on binde biriydi ve iki fix
    # (Windows log encoding'i · güncellemenin hiç bitmemesi) tam bu yüzden
    # sahada mahsur kaldı. ASAR'da yalnız `main.js` önyükleyicisi kalır.
    (KOK / "electron", "electron"),
]
ATLANAN_DIZIN = {"__pycache__", ".pytest_cache", ".lean-ctx", "node_modules", "assets", "dist"}
ATLANAN_UZANTI = {".pyc", ".pyo", ".log"}

# `electron/` kökü seçicidir: orada yükle ilgisi olmayan çok şey var (build
# yapılandırmaları, ikonlar, test dosyaları). Beyaz liste + iki sert yasak.
ELECTRON_UZANTI = {".js", ".html", ".css"}
# Uzantı beyaz listesi dışında kalan ama yüke GİRMESİ ŞART olan dosyalar.
#
# 🔴 `models-manifest.json` (2026-09-05 Dalga 2): indir-gerektiğinde
# yüklerin kayıt defteri. Uzantısı `.json` olduğu için beyaz listeye takılıyordu
# ve delta ile MÜŞTERİYE HİÇ GİTMİYORDU. Sonuç sessiz ve kötü olurdu: yeni bir
# yük (ör. yüz tanıma kütüphanesi) eklendiğinde `.js` dosyaları delta ile gider,
# manifest ESKİ kalır → `model-manager.js` "Bilinmeyen model" der, özellik ölür.
# Sürüm notu "yeni özellik" derken kullanıcıda hiçbir şey açılmaz.
# 📏 v0.6.13'ün dersi: *yamanın müşteriye ULAŞTIĞI ölçülmeli.*
# Güven düzeyi `.js` ile aynı: yük Ed25519 ile imzalı, imzasız manifest geçmez.
ELECTRON_EK_DOSYA = {"models-manifest.json"}

ELECTRON_YASAK = {
    "main.js",          # önyükleyici — ASAR'da kalır, kendi kendini güncelleyemez
    "onyukleme.js",     # önyükleme kararı + geri alma — kurtarma yolu güncellenemez
    "shell-id.txt",     # kabuğun kimliği — yük onu değiştirirse uyum kontrolü çöker
}


# ── yardımcılar ─────────────────────────────────────────────────────────────

def _sha256(veri: bytes) -> str:
    return hashlib.sha256(veri).hexdigest()


def _b64url(raw: bytes) -> str:
    return base64.urlsafe_b64encode(raw).decode("ascii").rstrip("=")


def _b64url_coz(s: str) -> bytes:
    return base64.urlsafe_b64decode(s + "=" * (-len(s) % 4))


def _kanonik(d: dict) -> bytes:
    """İmzalanan baytlar. Node tarafı birebir aynısını üretebilmeli:
    anahtarlar sıralı, ayraçlar boşluksuz, ASCII dışı karakter YOK.
    (`ensure_ascii=True` bilinçli — Node `JSON.stringify` ile ayrışmasın.)"""
    return json.dumps(d, sort_keys=True, separators=(",", ":"),
                      ensure_ascii=True).encode("ascii")


def agac_koku(girisler) -> str:
    """Yükün DOSYA BAZLI parmak izi — `(yol, sha256)` çiftlerinin özeti.

    Neden `payload_sha256` yetmiyor: o yalnız **indirme anını** doğrular. Overlay
    kullanıcının yazabildiği bir dizinde (`userData/updates/`) haftalarca duruyor
    ve her açılışta oradan KOD ÇALIŞTIRILIYOR. İndirme sonrası değiştirilen bir
    dosyayı hiçbir şey yakalamıyordu.

    Bu kök manifest'e girer, dolayısıyla **imzalıdır** — saldırgan dosyayı da
    listeyi de değiştirse imzayı üretemez. İstemci her açılışta overlay'i yeniden
    tarayıp bu kökü yeniden hesaplar; tutmazsa overlay kullanılmaz.

    Düz bir string üzerinden hesaplanır (iç içe JSON YOK): Python `json.dumps`
    ile Node `JSON.stringify` iç içe nesnelerde anahtar sırasında ayrışabilir ve
    imza sessizce tutmaz olurdu.

    :param girisler: (arşiv_yolu, içerik_baytları) çiftleri
    """
    h = hashlib.sha256()
    for yol, veri in sorted(girisler, key=lambda x: x[0]):
        h.update(f"{yol}:{_sha256(veri)}\n".encode("ascii"))
    return h.hexdigest()


def _yuk_dosyalari():
    """(mutlak yol, arşiv içi yol) — sıralı, deterministik."""
    for kaynak, onek in YUK_KOKLERI:
        if not kaynak.is_dir():
            continue
        for dirpath, dirnames, files in os.walk(kaynak):
            dirnames[:] = sorted(d for d in dirnames if d not in ATLANAN_DIZIN)
            if onek == "frontend" and Path(dirpath) == kaynak:
                # 2026-09-23: frontend/tests/ pakete ve yüke giriyordu — builder
                # filtresiyle (`!tests/**`) aynı sınır; koddan referans yok.
                dirnames[:] = [d for d in dirnames if d != "tests"]
            for f in sorted(files):
                if onek == "frontend" and Path(dirpath) == kaynak and f == "tasarim-kanit.html":
                    continue  # geliştirici sayfası — builder'da da `!tasarim-kanit.html`
                if Path(f).suffix in ATLANAN_UZANTI:
                    continue
                if onek == "electron":
                    if Path(f).suffix not in ELECTRON_UZANTI and f not in ELECTRON_EK_DOSYA:
                        continue
                    if f in ELECTRON_YASAK or f.endswith(".test.js"):
                        continue
                p = Path(dirpath) / f
                yield p, f"{onek}/{p.relative_to(kaynak).as_posix()}"


# ── shell-id ────────────────────────────────────────────────────────────────

# Paketin DIŞ KABUĞUNU oluşturan, derlemeyle gelen dosyalar. Yük bunlara
# erişemez: AppImage runtime dosyanın ELF başlığıdır (paket içeriği değil),
# `yuki.sh` ise `extraFiles` ile paket KÖKÜNE konur (app.asar'ın dışı).
KABUK_VARLIKLARI = (
    "scripts/vendor/appimage-runtime-x86_64",   # AppImage'ın FUSE'suz statik runtime'ı
    "electron/launcher/yuki.sh",                # tar.gz başlatıcısı (sandbox bayrağı)
    "electron/bekci-bin/SURUM",                 # süreç bekçisi ikilileri — resources/bekci, asar dışı
)


def shell_id_hesapla() -> str:
    """Yükün DOKUNAMADIĞI her şeyin parmak izi.

    Girdiler — hepsi "yük bunu güncelleyemez" kümesinde:
      · `requirements-product.txt` → Python bağımlılık ağacı (pybundle)
      · electron devDependency sürümü → Electron ikilisi
      · `KABUK_VARLIKLARI` → paketin dış kabuğu (runtime + launcher)

    🔴 2026-08-08: `frontend/assets` BU LİSTEDEN ÇIKARILDI.
    Medya artık kendi yüküyle taşınabiliyor (bkz. `medya_id_hesapla`), dolayısıyla
    tanım gereği bu kümede işi kalmadı — burada tutulsaydı taşınabilir bir şey
    "taşınamaz" diye işaretlenmiş olurdu ve her görsel değişikliği müşteriyi
    440 MB'lık tam indirmeye yollardı. Tetikleyici ölçüldü: 60 günde 3 kez.

    🔴 2026-08-10: `KABUK_VARLIKLARI` BU LİSTEYE EKLENDİ — ters yöndeki aynı hata.
    Statik AppImage runtime (`488cf09`) Kali/Debian'da uygulamanın **hiç açılmaması**
    sorununu çözüyordu, ama bu formülde yer almadığı için `shell_id` değişmiyordu:
    istemci delta iniyor, delta paketin dış kabuğuna dokunamıyor → **düzeltme
    müşteriye hiçbir zaman ulaşmıyordu.** Ekranda "güncellendi" yazıp hiçbir şeyin
    değişmemesi, bu dosyanın önlemek için var olduğu şeyin ta kendisi.

    ⚠️ Bilinen bedel: `shell_id` platformdan bağımsız TEK hash'tir. Yalnız Linux'u
    ilgilendiren bir runtime değişimi Windows müşterisini de tam indirmeye düşürür.
    Kabul edildi — runtime yılda birkaç kez değişir; alternatifi (platform başına
    ayrı parmak izi) manifest şemasını ve altı kapıyı birden değiştirmek olurdu.
    """
    h = hashlib.sha256()

    h.update(b"req:")
    h.update(_bagimlilik_imzasi().encode("ascii"))

    pkg = json.loads((KOK / "electron" / "package.json").read_text(encoding="utf-8"))
    h.update(b"|electron:")
    h.update(str(pkg.get("devDependencies", {}).get("electron", "-")).encode())

    h.update(b"|kabuk:")
    h.update(_kabuk_imzasi().encode("ascii"))

    return h.hexdigest()[:32]


def _kabuk_imzasi() -> str:
    """`KABUK_VARLIKLARI`nın içerik özeti.

    🔴 Eksik dosyada SESSİZCE devam edilmez. Yol yanlış yazılır ya da dosya
    silinirse "-" yazıp geçmek, kapıyı kalıcı olarak kör eder: hash sabitlenir,
    runtime bir daha hiç `shell_id`'ye yansımaz ve bunu kimse fark etmez.
    Derlemeyi burada durdurmak, sahada sessizce yanlış davranmaktan ucuzdur.
    """
    parcalar = []
    for rel in KABUK_VARLIKLARI:
        p = KOK / rel
        if not p.is_file():
            raise SystemExit(
                f"✗ kabuk varlığı yok: {rel}\n"
                f"  shell_id bu dosyayı içermek zorunda (paketin dış kabuğu, yük "
                f"onu güncelleyemez).\n"
                f"  Dosya bilerek kaldırıldıysa KABUK_VARLIKLARI listesinden de çıkar."
            )
        ozet = hashlib.sha256(p.read_bytes()).hexdigest()[:16]
        parcalar.append(f"{rel}:{ozet}")
    return "|".join(parcalar)


def _bagimlilik_imzasi() -> str:
    """`requirements-product.txt` → yalnız ANLAM taşıyan kısım.

    🔴 2026-08-08: eskiden dosyanın HAM BAYTLARI hash'leniyordu. Yani bir yorum
    satırı eklemek, bir satırı yeniden sıralamak ya da sondaki boşluğu değiştirmek
    `shell_id`'yi değiştiriyor ve **hiçbir şey değişmediği hâlde** tüm kurulumları
    440 MB'lık tam indirmeye düşürüyordu. Bu dosya son 60 günde 4 kez değişti;
    kaçının gerçekten pybundle'ı etkilediği belli değil.

    Soru "dosya değişti mi" değil, **"kurulacak paket kümesi değişti mi"**.
    Yorumlar, boş satırlar, satır sırası ve harf büyüklüğü cevabı değiştirmez;
    `-r` ile devredilen dosyalar da (o dosyanın kendi içeriği zaten ayrıca gelir)
    burada isim olarak kalır — çözümlemeye çalışmak, çözümleyemediğinde sessizce
    yanlış cevap veren bir yol açardı.
    """
    req = KOK / "backend" / "requirements-product.txt"
    if not req.is_file():
        return "-"
    satirlar = []
    for ham in req.read_text(encoding="utf-8").splitlines():
        s = ham.split("#", 1)[0].strip()          # satır içi yorum da düşer
        if s:
            satirlar.append(s.lower())
    # Sıra anlam taşımaz (pip çözümleyicisi sıralamaya bakmaz) → sıralı imza.
    return ";".join(sorted(satirlar))


# ── medya katmanı (2026-08-08) ──────────────────────────────────────────────
#
# NEDEN AYRI BİR YÜK: medya (33 MB) kod yükünün (1,2 MiB) yanında devasa kalır;
# her sürümde göndermek 27× israf olurdu. Ama `shell_id`'ye bağlamak da yanlıştı —
# o zaman hiç gönderilemiyordu. Çözüm: ayrı yük + ayrı parmak izi (`media_id`).
# İstemcinin `media_id`'si tutuyorsa medya yükü İNDİRİLMEZ; tutmuyorsa iner.
# Böylece medya sürümlerinin %90'ında sıfır bayt, değiştiğinde 33 MB — 440 MB değil.
#
# Kümülatif (kod yükü gibi): TÜM medyayı taşır, delta değil. Hangi sürümden
# gelinirse gelinsin tek adımda doğru medyaya varılır.

def _medya_dosyalari():
    """(mutlak yol, arşiv içi yol) — `frontend/assets` altındaki her şey."""
    kaynak = KOK / "frontend" / "assets"
    if not kaynak.is_dir():
        return
    for dirpath, dirnames, files in os.walk(kaynak):
        dirnames[:] = sorted(d for d in dirnames if d not in ATLANAN_DIZIN)
        for f in sorted(files):
            if Path(f).suffix in ATLANAN_UZANTI:
                continue
            p = Path(dirpath) / f
            yield p, f"frontend/assets/{p.relative_to(kaynak).as_posix()}"


# ── tam paket (SKU) parmak izleri ───────────────────────────────────────────
#
# NEDEN İMZALI OLMAK ZORUNDA: uygulama içi "tam güncelleme" indirdiği AppImage /
# zip'i çalıştırılabilir hâle getirip kurulumun üstüne yazar. İmzasız bir indirme,
# delta kanalında kapattığımız uzaktan kod çalıştırma açığını arka kapıdan geri
# açardı — üstelik delta'dan beter, çünkü tam paket her şeyi değiştirir.
#
# Hash'ler İMZALI manifest'e girer; istemci indirdiğini oraya karşı doğrular.
# GitHub'ın kendi bütünlüğüne güvenmiyoruz: release varlığı yeniden yüklenebilir,
# etiket taşınabilir, ayna bayat olabilir.
#
# SKU'lar `dist/` altından GLOB ile bulunur, elle liste tutulmaz: `yayin.py`de de
# bir SKULAR listesi var ve ikisi ayrışsaydı yeni bir SKU sessizce imzasız kalırdı.

def _sku_dosyalari(surum: str):
    """(dosya, ad) — o sürüme ait üretilmiş tam paket varlıkları."""
    dist = KOK / "electron" / "dist"
    if not dist.is_dir():
        return
    for p in sorted(dist.iterdir()):
        if not p.is_file():
            continue
        if not p.name.startswith(f"Yuki-{surum}-"):
            continue
        if p.suffix not in (".AppImage", ".zip", ".exe"):
            continue
        yield p, p.name


def sku_parmak_izleri(surum: str) -> str:
    """`ad:sha256:boyut` kayıtları, `;` ile ayrık, ada göre sıralı.

    🔴 DÜZ STRING, iç içe JSON DEĞİL — bilinçli. Node tarafındaki `canonical()`
    yalnız ÜST SEVİYE anahtarları sıralar; iç içe bir nesneyi
    `JSON.stringify` ekleme sırasıyla yazar. Python `json.dumps(sort_keys=True)`
    ise derinlemesine sıralar. İkisi bugün tesadüfen aynı çıktıyı verirdi
    (manifest zaten sıralı yazılıyor), ama bu, imzanın **görünmez bir
    varsayıma** dayanması demekti: manifest bir gün başka bir araçla üretilse
    ya da elle düzenlense imza sessizce tutmaz olurdu.
    `files_root` aynı sebeple düz string; kural burada da korunuyor.
    """
    kayitlar = []
    for p, ad in _sku_dosyalari(surum):
        h = hashlib.sha256()
        with open(p, "rb") as f:
            for blok in iter(lambda: f.read(1024 * 1024), b""):
                h.update(blok)
        kayitlar.append(f"{ad}:{h.hexdigest()}:{p.stat().st_size}")
    return ";".join(sorted(kayitlar))


def medya_id_hesapla() -> str:
    """Paketlenmiş medyanın parmak izi.

    `shell_id`'nin eski assets bölümü ad+boyut kullanıyordu; burada **sha256**
    kullanılıyor çünkü artık soru "değişti mi" değil, "istemcideki medya
    gönderdiğimizle AYNI mı". Aynı boyutta farklı bir görsel (yeniden üretilmiş
    bir portre tam da budur) boyut karşılaştırmasını sessizce geçerdi.
    """
    h = hashlib.sha256()
    for mutlak, ic_yol in _medya_dosyalari():
        h.update(f"{ic_yol}:{_sha256(mutlak.read_bytes())}\n".encode("ascii"))
    return h.hexdigest()[:32]


def cmd_shell_id(args) -> int:
    """`shell-id.txt` + `media-id.txt` — ikisi birlikte damgalanır.

    Aynı komutta tutuluyorlar çünkü ayrı komutlar olsaydı biri unutulurdu ve
    unutulan `media-id.txt` sessizce yanlış cevap verirdi: istemci "medyam
    güncel" sanıp eski görselle kalırdı (bu üründe *sessiz yanlış* en pahalı
    hata sınıfı — `surum.js` dersi).
    """
    sid = shell_id_hesapla()
    mid = medya_id_hesapla()
    onceki = SHELL_ID_PATH.read_text(encoding="utf-8").strip() if SHELL_ID_PATH.is_file() else None
    onceki_m = MEDIA_ID_PATH.read_text(encoding="utf-8").strip() if MEDIA_ID_PATH.is_file() else None

    if args.check:
        sorun = []
        if onceki != sid:
            sorun.append(f"shell-id  dosya:{onceki} gerçek:{sid}")
        if onceki_m != mid:
            sorun.append(f"media-id  dosya:{onceki_m} gerçek:{mid}")
        if not sorun:
            print(f"✓ shell-id güncel: {sid}\n✓ media-id güncel: {mid}")
            return 0
        print("✗ kimlik damgası bayat:\n   " + "\n   ".join(sorun), file=sys.stderr)
        print("   Düzeltme: python3 scripts/update_payload.py shell-id", file=sys.stderr)
        return 1

    SHELL_ID_PATH.write_text(sid + "\n", encoding="utf-8")
    MEDIA_ID_PATH.write_text(mid + "\n", encoding="utf-8")
    durum = "değişmedi" if onceki == sid else f"DEĞİŞTİ (önceki: {onceki})"
    durum_m = "değişmedi" if onceki_m == mid else f"DEĞİŞTİ (önceki: {onceki_m})"
    print(f"✓ {SHELL_ID_PATH.relative_to(KOK)} → {sid}  [{durum}]")
    print(f"✓ {MEDIA_ID_PATH.relative_to(KOK)} → {mid}  [{durum_m}]")
    if onceki and onceki != sid:
        print("  🔴 KABUK değişti (Python bağımlılığı · Electron sürümü · runtime/launcher) →")
        print("     delta yetmez, eski kurulumlar TAM PAKET indirir.")
    if onceki_m and onceki_m != mid:
        print("  ⚠️ MEDYA değişti → bu sürümde medya yükü de yayınlanmalı;")
        print("     `build` onu üretir, yayın adımı yüklemeyi unutmamalı.")
    return 0


# ── anahtar ─────────────────────────────────────────────────────────────────

def cmd_keygen(args) -> int:
    from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
    if UPDATE_PRIVATE_PATH.exists():
        print(f"⚠️  Zaten mevcut: {UPDATE_PRIVATE_PATH} — üzerine YAZILMADI.")
        print("   Yeni çift, eski imzaları geçersiz kılar; gerçekten istiyorsan elle taşı.")
        return 0
    ISSUER_DIR.mkdir(parents=True, exist_ok=True)
    priv = Ed25519PrivateKey.generate()
    from cryptography.hazmat.primitives import serialization
    raw = priv.private_bytes(serialization.Encoding.Raw,
                             serialization.PrivateFormat.Raw,
                             serialization.NoEncryption())
    UPDATE_PRIVATE_PATH.write_text(raw.hex() + "\n", encoding="utf-8")
    os.chmod(UPDATE_PRIVATE_PATH, stat.S_IRUSR | stat.S_IWUSR)   # 0600
    pub = priv.public_key().public_bytes(serialization.Encoding.Raw,
                                         serialization.PublicFormat.Raw)
    print(f"✓ PRIVATE → {UPDATE_PRIVATE_PATH} (0600, repo DIŞI)")
    print(f"\n  PUBLIC KEY (electron/delta-updater.js içine göm):\n\n    {pub.hex()}\n")
    print("  ⚠️ Bu anahtar LİSANS anahtarından ayrıdır ve öyle kalmalı:")
    print("     lisans sızıntısı = bedava Pro · güncelleme sızıntısı = müşteride kod çalıştırma.")
    return 0


def _private_yukle() -> str:
    if not UPDATE_PRIVATE_PATH.is_file():
        sys.exit(f"✗ İmza anahtarı yok: {UPDATE_PRIVATE_PATH}\n"
                 f"  Önce: python3 scripts/update_payload.py keygen")
    return UPDATE_PRIVATE_PATH.read_text(encoding="utf-8").strip()


# ── build ───────────────────────────────────────────────────────────────────

def _surum_tutarliligi(surum: str) -> None:
    """Yükün İDDİA ettiği sürüm ile taşıdığı KODUN bildirdiği sürüm aynı mı?

    🔴 2026-08-04'te canlı turda ölçüldü. `build --version 0.5.9` damgasız kodu
    itirazsız paketliyordu: overlay v0.5.9 diye kuruluyor, ama içindeki
    `health.py` hâlâ `APP_VERSION = "0.5.8"` diyor. Sonuç, hata değil **sessiz
    geri alma**:

      · `uygulama.js::guncellemeBasarisiniIsle` motorun bildirdiği sürümü
        beklenenle kıyaslar → UYUŞMAZLIK → `basariliIsaretle()` çağrılmaz
      · her açılış `denemeIsaretle()` sayacı artırır
      · 3. açılışta **sapasağlam güncelleme geri alınır**

    Yani müşteri güncellemeyi alır, üç kez açar, güncelleme kendini geri alır ve
    ekranda hiçbir şey görünmez. Kapı ④ (gerçek başarı ölçütü) doğru çalışırken
    yanlış veriyle beslendiği için ürünün kendisini vurur.

    `yayin.py` zincirinde tetiklenmez (`surum` → `derle` → yük sırası damgayı
    garanti eder, ve orada `--version` verilmez). Bu kapı **elle/off-chain**
    üretim içindir: `npm run update:payload`, `build --version X`.

    Kök neden sınıfı: *aynı soruya iki cevap* — manifest'in sürümü ile kodun
    kendi bildirdiği sürüm ayrı yerlerde duruyor ve ayrıştıkları yere kimse
    bakmıyordu (`surum.js`'in doğduğu dersin aynısı).
    """
    health = KOK / "backend" / "app" / "services" / "health.py"
    m = re.search(r'APP_VERSION\s*=\s*"([\d.]+)"', health.read_text(encoding="utf-8"))
    if not m:
        sys.exit(f"✗ {health.name} içinde APP_VERSION bulunamadı — damga noktası "
                 "yeniden adlandırılmış olabilir; bu kapı sessizce boşa düşmemeli.")
    kod_surumu = m.group(1)
    if kod_surumu != surum:
        sys.exit(
            f"✗ SÜRÜM AYRIŞMASI — yük v{surum} diyor, taşıdığı kod v{kod_surumu} diyor.\n"
            f"  Bu yük yayınlansaydı güncelleme uygulanır, sonra 3 açılışta\n"
            f"  SESSİZCE GERİ ALINIRDI (motor beklenen sürümü bildirmez).\n\n"
            f"  Çözüm: önce damgala → python3 scripts/yayin.py surum {surum}\n"
            f"  (health.py'yi elle düzeltme: damga birden çok dosyada, biri unutulur.)"
        )


def manifest_kanonik_denetle(manifest: dict) -> str | None:
    """Manifest, Node ile BİREBİR aynı baytlara serileşebilir mi? Sorun varsa metin.

    İki kural, ikisi de *sessiz imza hatası* üretebilecek cinsten:

    ① **ASCII dışı yok.** Python `ensure_ascii=True` kaçış yazar, Node ham UTF-8.
    ② 🔴 **İç içe yapı yok.** Node `canonical()` YALNIZ üst seviye anahtarları
       sıralar (`JSON.stringify(obj[k])` iç nesneyi ekleme sırasıyla yazar);
       Python `json.dumps(sort_keys=True)` derinlemesine sıralar. İç içe bir
       nesne bugün tesadüfen aynı baytları üretebilir — manifest zaten sıralı
       yazıldığı için — ama o an imza **görünmez bir varsayıma** dayanır:
       manifest başka bir araçla üretilse ya da elle düzenlense sessizce tutmaz.

    Bu kapı 2026-08-08'de eklendi: SKU parmak izleri ilk denemede iç içe sözlük
    olarak yazılmıştı ve tam bu tuzağa düşülmüştü. Kural CLAUDE.md'de zaten
    yazılıydı (`agac_koku` neden düz string) ama *kural yazılı olmak* onu
    uygulatmıyor — kapı uygulatıyor.
    """
    for k, v in manifest.items():
        if isinstance(v, str) and not v.isascii():
            return f"✗ Manifest alanı ASCII dışı: {k}={v!r} (imza ayrışır)"
        if isinstance(v, (dict, list)):
            return (
                f"✗ Manifest alanı iç içe yapı: {k} ({type(v).__name__}).\n"
                f"  Node canonical() ile Python json.dumps(sort_keys) burada\n"
                f"  ayrışabilir → imza SESSİZCE tutmaz olur.\n"
                f"  Çözüm: `files_root`/`skus` gibi DÜZ STRING olarak kodla."
            )
    return None


def cmd_build(args) -> int:
    from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

    surum = args.version or json.loads(
        (KOK / "electron" / "package.json").read_text(encoding="utf-8"))["version"]
    _surum_tutarliligi(surum)
    CIKTI.mkdir(parents=True, exist_ok=True)
    ark_yolu = CIKTI / f"yuki-update-{surum}.tar.gz"
    man_yolu = CIKTI / f"yuki-update-{surum}.json"

    # Format = tar.gz, bilinçli tercih: istemci ayrıştırıcısı Node'da elle yazılıyor
    # (ek bağımlılık = güvenlik-kritik yolda tedarik zinciri riski). tar'ın sabit
    # 512 baytlık başlığı, zip'in merkezi-dizin/EOCD kenar durumlarından çok daha
    # küçük bir hata yüzeyi bırakır.
    #
    # Deterministik: sıralı giriş · mtime/uid/gid sıfır · gzip mtime=0
    # → aynı girdi her zaman aynı sha256'yı verir (yayını doğrulanabilir kılar).
    dosyalar = list(_yuk_dosyalari())
    if not dosyalar:
        sys.exit("✗ Yüke girecek dosya bulunamadı.")
    ham = 0
    icerikler = []           # (arşiv yolu, bayt) — ağaç kökü için
    ham_tar = io.BytesIO()
    with tarfile.open(fileobj=ham_tar, mode="w") as t:
        for mutlak, ic_yol in dosyalar:
            veri = mutlak.read_bytes()
            icerikler.append((ic_yol, veri))
            ham += len(veri)
            ti = tarfile.TarInfo(ic_yol)
            ti.size = len(veri)
            ti.mtime = 0
            ti.mode = 0o644
            ti.uid = ti.gid = 0
            ti.uname = ti.gname = ""
            ti.type = tarfile.REGTYPE
            t.addfile(ti, io.BytesIO(veri))
    with open(ark_yolu, "wb") as f:
        with gzip.GzipFile(fileobj=f, mode="wb", compresslevel=9, mtime=0) as g:
            g.write(ham_tar.getvalue())

    payload = ark_yolu.read_bytes()
    manifest = {
        "schema": SCHEMA,
        "product": PRODUCT,
        "version": surum,
        "shell_id": shell_id_hesapla(),
        "payload_name": ark_yolu.name,
        "payload_sha256": _sha256(payload),
        "payload_size": len(payload),
        "file_count": len(dosyalar),
        # Açılış-zamanı bütünlük denetiminin çıpası — bkz. agac_koku()
        "files_root": agac_koku(icerikler),
        # Medya kimliği HER ZAMAN yazılır (yük üretilmese bile): istemci
        # "medyam güncel mi" sorusunu bununla cevaplar.
        "media_id": medya_id_hesapla(),
        # Tam paket varlıklarının imzalı parmak izleri — uygulama içi tam
        # güncellemenin güven çıpası. Boşsa (SKU'lar henüz derlenmemiş) istemci
        # tam güncellemeyi teklif ETMEZ, eski davranışa (indirme sayfası) düşer.
        "skus": sku_parmak_izleri(surum),
    }

    # ── medya yükü (opsiyonel ikinci arşiv) ─────────────────────────────────
    # `--medya-atla` yalnız medyanın değişmediğinden EMİN olunan sürümler için.
    # Atlanırsa manifest'te `media_payload_name` olmaz; medyası tutmayan bir
    # istemci o zaman tam pakete düşer (güvenli geri dönüş, sessiz hata değil).
    medya_dosyalar = list(_medya_dosyalari())
    if not args.medya_atla and medya_dosyalar:
        m_ark = CIKTI / f"yuki-media-{surum}.tar.gz"
        m_ham = 0
        m_icerikler = []
        m_tar = io.BytesIO()
        with tarfile.open(fileobj=m_tar, mode="w") as t:
            for mutlak, ic_yol in medya_dosyalar:
                veri = mutlak.read_bytes()
                m_icerikler.append((ic_yol, veri))
                m_ham += len(veri)
                ti = tarfile.TarInfo(ic_yol)
                ti.size = len(veri)
                ti.mtime = 0
                ti.mode = 0o644
                ti.uid = ti.gid = 0
                ti.uname = ti.gname = ""
                ti.type = tarfile.REGTYPE
                t.addfile(ti, io.BytesIO(veri))
        # compresslevel=1: içerik zaten sıkışık (png/mp4/vrm). 9 ile ölçüldüğünde
        # kazanç binde birkaç, maliyet onlarca saniye — yayın adımını yavaşlatır.
        with open(m_ark, "wb") as f:
            with gzip.GzipFile(fileobj=f, mode="wb", compresslevel=1, mtime=0) as g:
                g.write(m_tar.getvalue())
        m_payload = m_ark.read_bytes()
        manifest.update({
            "media_payload_name": m_ark.name,
            "media_payload_sha256": _sha256(m_payload),
            "media_payload_size": len(m_payload),
            "media_file_count": len(medya_dosyalar),
            "media_root": agac_koku(m_icerikler),
        })
        print(f"✓ Medya   : {m_ark.relative_to(KOK)}")
        print(f"  dosya   : {len(medya_dosyalar)}  ·  ham {m_ham/1048576:.1f} MiB → "
              f"sıkışık {len(m_payload)/1048576:.1f} MiB")
        print(f"  media_id: {manifest['media_id']}")
    hata_metni = manifest_kanonik_denetle(manifest)
    if hata_metni:
        sys.exit(hata_metni)

    priv = Ed25519PrivateKey.from_private_bytes(bytes.fromhex(_private_yukle()))
    imza = priv.sign(_kanonik(manifest))
    manifest["sig"] = _b64url(imza)
    man_yolu.write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n",
                        encoding="utf-8")

    print(f"✓ Yük     : {ark_yolu.relative_to(KOK)}")
    print(f"  dosya   : {len(dosyalar)}  ·  ham {ham/1048576:.2f} MiB → "
          f"sıkışık {len(payload)/1048576:.2f} MiB")
    print(f"  sha256  : {manifest['payload_sha256']}")
    print(f"  shell_id: {manifest['shell_id']}")
    print(f"✓ Manifest: {man_yolu.relative_to(KOK)} (imzalı)")

    # Yayın satırı manifest'in İDDİA ettiği dosyalardan türetilir, elle yazılmaz:
    # medya yükü listeye elle eklenseydi bir gün unutulur, istemci manifest'e
    # bakıp indirmeye çalışır ve 404 alırdı — yani güncelleme, tam da medyanın
    # değiştiği sürümde patlardı.
    yuklenecek = [ark_yolu.name, man_yolu.name]
    if manifest.get("media_payload_name"):
        yuklenecek.insert(1, manifest["media_payload_name"])
    print(f"\n  Yayın:  gh release upload v{surum} {' '.join(yuklenecek)} "
          f"--repo ihsandeniz/yuki-oss --clobber")
    if not manifest.get("media_payload_name"):
        print("  ⚠️ Medya yükü YOK (--medya-atla) → medyası eski olan istemci "
              "tam pakete düşer.")
    return 0


# ── verify ──────────────────────────────────────────────────────────────────

def cmd_verify(args) -> int:
    """İmzayı ve payload hash'ini bağımsız doğrula (yayından önce son kontrol)."""
    from cryptography.exceptions import InvalidSignature
    from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey

    man = json.loads(Path(args.manifest).read_text(encoding="utf-8"))
    sig = _b64url_coz(man.pop("sig"))
    pub_hex = args.public_key or _public_key_oku()
    try:
        Ed25519PublicKey.from_public_bytes(bytes.fromhex(pub_hex)).verify(sig, _kanonik(man))
    except InvalidSignature:
        print("✗ İMZA GEÇERSİZ", file=sys.stderr)
        return 1
    print(f"✓ İmza geçerli (public key {pub_hex[:16]}…)")

    zp = Path(args.manifest).parent / man["payload_name"]
    if not zp.is_file():
        print(f"⚠️ Payload yanında yok: {zp}")
        return 0
    gercek = _sha256(zp.read_bytes())
    if gercek != man["payload_sha256"]:
        print(f"✗ PAYLOAD HASH TUTMUYOR\n   manifest: {man['payload_sha256']}\n"
              f"   gerçek  : {gercek}", file=sys.stderr)
        return 1
    print(f"✓ Payload sha256 tutuyor ({man['payload_size']/1048576:.2f} MiB, "
          f"{man['file_count']} dosya)")
    print(f"✓ shell_id: {man['shell_id']} "
          f"({'güncel' if man['shell_id'] == shell_id_hesapla() else '⚠️ ÇALIŞMA AĞACINDAN FARKLI'})")
    return 0


def _public_key_oku() -> str:
    """Public key'i ürünün kendisinden oku — imzalayan ile doğrulayan ayrışmasın."""
    js = (KOK / "electron" / "delta-updater.js")
    if js.is_file():
        import re
        m = re.search(r"UPDATE_PUBLIC_KEY\s*=\s*'([0-9a-f]{64})'", js.read_text(encoding="utf-8"))
        if m:
            return m.group(1)
    sys.exit("✗ Public key bulunamadı (electron/delta-updater.js) — --public-key ver.")


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    alt = ap.add_subparsers(dest="cmd", required=True)

    s = alt.add_parser("shell-id", help="kabuk parmak izini hesapla/yaz")
    s.add_argument("--check", action="store_true", help="yazma, sadece güncel mi bak")
    s.set_defaults(func=cmd_shell_id)

    k = alt.add_parser("keygen", help="güncelleme imza anahtarı üret (BİR KEZ)")
    k.set_defaults(func=cmd_keygen)

    b = alt.add_parser("build", help="yük + imzalı manifest üret")
    b.add_argument("--version", help="varsayılan: electron/package.json")
    b.add_argument("--medya-atla", action="store_true",
                   help="medya yükünü üretme (medyanın değişmediğinden eminsen). "
                        "Atlanırsa medyası tutmayan istemci tam pakete düşer.")
    b.set_defaults(func=cmd_build)

    v = alt.add_parser("verify", help="imza + hash bağımsız doğrula")
    v.add_argument("manifest")
    v.add_argument("--public-key")
    v.set_defaults(func=cmd_verify)

    args = ap.parse_args()
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
