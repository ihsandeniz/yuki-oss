"""Medya katmanı — statik sunum zinciri + shell_id'nin medyadan kurtulması.

BAĞLAM (2026-08-08): `frontend/assets` eskiden `shell_id`'ye giriyordu; medya
değişen her sürümde delta reddediliyor ve müşteri tarayıcıya gönderilip 440 MB
tam paket indiriyordu. Artık medyanın kendi yükü ve kendi parmak izi var.

Buradaki iki soru, ikisi de SESSİZ hata üretebilecek cinsten:
  ① `shell_id` gerçekten medyadan bağımsız mı? (değilse hiçbir şey değişmemiş olur)
  ② İndirilen medya, paketin fabrika medyasının ÖNÜNDE mi sunuluyor?
     (değilse kullanıcı 33 MB indirir, ekranda eski görseli görmeye devam eder)
"""
from __future__ import annotations

import importlib
import sys
from pathlib import Path

import pytest
from starlette.staticfiles import StaticFiles

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent / "scripts"))


# ── ① shell_id / media_id ayrımı ────────────────────────────────────────────

def _up():
    return importlib.import_module("update_payload")


def test_shell_id_medyadan_etkilenmez(tmp_path, monkeypatch):
    """Medyaya dokunmak `shell_id`'yi DEĞİŞTİRMEMELİ.

    Bu testin tersi, bu turda düzeltilen kusurun ta kendisiydi.
    """
    up = _up()
    kok = tmp_path
    (kok / "backend").mkdir()
    (kok / "backend" / "requirements-product.txt").write_text("fastapi==1.0\n")
    (kok / "electron").mkdir()
    (kok / "electron" / "package.json").write_text('{"devDependencies":{"electron":"29.0.0"}}')
    assets = kok / "frontend" / "assets"
    assets.mkdir(parents=True)
    (assets / "yuki.png").write_bytes(b"ESKI-GORSEL")
    _kabuk_varliklari_yaz(kok)

    monkeypatch.setattr(up, "KOK", kok)
    once_shell = up.shell_id_hesapla()
    once_media = up.medya_id_hesapla()

    (assets / "yuki.png").write_bytes(b"YENI-GORSEL-AYNI-BOYUT")
    (assets / "yeni_klip.mp4").write_bytes(b"KLIP")

    assert up.shell_id_hesapla() == once_shell, (
        "medya değişimi shell_id'yi değiştirdi → delta yine reddedilir, "
        "düzeltme hiçbir işe yaramamış olur"
    )
    assert up.medya_id_hesapla() != once_media, "medya değişimi media_id'de görünmeli"


def test_media_id_ayni_boyutlu_farkli_icerigi_yakalar(tmp_path, monkeypatch):
    """`media_id` sha256 kullanır, boyut değil.

    Yeniden üretilmiş bir portre tam olarak aynı boyutta olabilir; boyut
    karşılaştırması onu sessizce geçirir ve kullanıcı eski görselde kalırdı.
    """
    up = _up()
    kok = tmp_path
    (kok / "backend").mkdir()
    (kok / "backend" / "requirements-product.txt").write_text("x\n")
    (kok / "electron").mkdir()
    (kok / "electron" / "package.json").write_text('{"devDependencies":{"electron":"29.0.0"}}')
    assets = kok / "frontend" / "assets"
    assets.mkdir(parents=True)
    (assets / "portre.png").write_bytes(b"A" * 512)
    monkeypatch.setattr(up, "KOK", kok)
    once = up.medya_id_hesapla()

    (assets / "portre.png").write_bytes(b"B" * 512)      # aynı boyut, farklı içerik
    assert up.medya_id_hesapla() != once


def test_shell_id_runtime_degisimini_hala_yakalar(tmp_path, monkeypatch):
    """Kabuk gerçekten değiştiğinde (Python bağımlılığı) shell_id DEĞİŞMELİ —
    medyayı çıkarırken bu koruma da düşmüş olmamalı."""
    up = _up()
    kok = tmp_path
    (kok / "backend").mkdir()
    req = kok / "backend" / "requirements-product.txt"
    req.write_text("fastapi==1.0\n")
    (kok / "electron").mkdir()
    (kok / "electron" / "package.json").write_text('{"devDependencies":{"electron":"29.0.0"}}')
    _kabuk_varliklari_yaz(kok)
    monkeypatch.setattr(up, "KOK", kok)
    once = up.shell_id_hesapla()

    req.write_text("fastapi==1.0\nyeni-paket==2.0\n")
    assert up.shell_id_hesapla() != once, "yeni pip bağımlılığı tam pakete düşürmeli"

    req.write_text("fastapi==1.0\nyeni-paket==2.0\n")
    (kok / "electron" / "package.json").write_text('{"devDependencies":{"electron":"30.0.0"}}')
    assert up.shell_id_hesapla() != once, "Electron sürümü değişimi tam pakete düşürmeli"


# ── ② statik sunum zinciri ──────────────────────────────────────────────────

def _katmanli(birincil: Path, yedekler: list[Path], medya: Path | None = None):
    from app.main import KatmanliStatik
    return KatmanliStatik(directory=str(birincil), fallbacks=yedekler,
                          oncelikliler=[medya] if medya else [])


def _bul(statik, yol: str):
    full, stat_result = statik.lookup_path(yol)
    return (Path(full).read_bytes() if stat_result is not None else None)


def test_medya_katmani_paketin_ONUNDE_sunulur(tmp_path):
    """İndirilen medya, paketin fabrika medyasını GÖLGELEMELİ.

    🔴 Sıra ters olsaydı: kullanıcı 33 MB'ı indirir, ekranda eski görseli
    görmeye devam eder ve buna bakan hiç kimse güncellemenin indiğini anlamaz.
    """
    overlay = tmp_path / "overlay"        # kod overlay'i — medya taşımaz
    medya = tmp_path / "medya"            # indirilmiş medya katmanı
    paket = tmp_path / "paket"            # fabrika
    for d in (overlay, medya, paket):
        (d / "assets").mkdir(parents=True)

    (paket / "assets" / "yuki.png").write_bytes(b"FABRIKA")
    (medya / "assets" / "yuki.png").write_bytes(b"INDIRILEN")
    (overlay / "core.js").write_bytes(b"YENI-KOD")
    (paket / "core.js").write_bytes(b"ESKI-KOD")

    st = _katmanli(overlay, [paket], medya=medya)
    assert _bul(st, "assets/yuki.png") == b"INDIRILEN", "medya paketi gölgelemeli"
    assert _bul(st, "core.js") == b"YENI-KOD", "kod overlay'i birincil kalmalı"


def test_OVERLAY_YOKKEN_de_medya_paketi_golgeler(tmp_path):
    """🔴 Canlı turda bulunan kusurun regresyon testi (2026-08-08).

    Kurulumların ÇOĞUNDA overlay yoktur (henüz kod güncellemesi almamış ya da
    geri alınmış kurulum). O durumda `/ui`nin birincil dizini paketin kendisidir
    ve aranan görsel orada DA vardır. Medya yalnız *yedek* olarak verilseydi
    birincil kazanır, medyaya hiç bakılmazdı.

    Birim testler bunu kaçırdı çünkü hepsi overlay'i birincil varsayıyordu;
    kusur ancak gerçek backend HTTP'den sorgulanınca göründü.
    """
    paket = tmp_path / "paket"
    medya = tmp_path / "medya"
    (paket / "assets").mkdir(parents=True)
    (medya / "assets").mkdir(parents=True)
    (paket / "assets" / "yuki.png").write_bytes(b"FABRIKA")
    (medya / "assets" / "yuki.png").write_bytes(b"INDIRILEN")

    # Overlay YOK → birincil = paket (gerçek kurulumdaki hâl)
    st = _katmanli(paket, [], medya=medya)
    assert _bul(st, "assets/yuki.png") == b"INDIRILEN", (
        "overlay yokken medya katmanı yok sayıldı — kullanıcı 33 MB indirip "
        "fabrika görselini görmeye devam ederdi"
    )


def test_zincir_bulunamayani_sondaki_koke_kadar_arar(tmp_path):
    overlay = tmp_path / "o"
    medya = tmp_path / "m"
    paket = tmp_path / "p"
    for d in (overlay, medya, paket):
        d.mkdir()
    (paket / "sadece_pakette.vrm").write_bytes(b"VRM")

    st = _katmanli(overlay, [medya, paket])
    assert _bul(st, "sadece_pakette.vrm") == b"VRM"
    assert _bul(st, "hic_yok.png") is None


def test_yedeksiz_davranis_degismedi(tmp_path):
    """Yedek verilmeyen (geliştirme/paketlenmiş) çalışmada davranış eskisiyle aynı."""
    kok = tmp_path / "k"
    kok.mkdir()
    (kok / "a.txt").write_bytes(b"A")
    st = _katmanli(kok, [])
    assert _bul(st, "a.txt") == b"A"
    assert _bul(st, "yok.txt") is None


def test_tekil_fallback_geriye_uyumlu(tmp_path):
    """Eski `fallback=` (tekil) çağrıları birebir aynı davranmalı."""
    from app.main import KatmanliStatik
    kok = tmp_path / "k"
    yedek = tmp_path / "y"
    kok.mkdir()
    yedek.mkdir()
    (yedek / "b.txt").write_bytes(b"B")
    st = KatmanliStatik(directory=str(kok), fallback=yedek)
    assert _bul(st, "b.txt") == b"B"


# ── shell_id: gürültüye değil, ANLAMA duyarlı ───────────────────────────────

def _kabuk_varliklari_yaz(kok: Path) -> None:
    """Sahte KOK'a `KABUK_VARLIKLARI`nın hepsini yazar.

    Listenin ÜZERİNDEN döner, yolları elle yazmaz: kabuk kümesine yeni bir dosya
    eklendiğinde bu yardımcı onu kendiliğinden kurar. Elle yazılsaydı her ekleme
    dört testi birden kırar ve düzeltme dört yere dağılırdı.
    """
    up = _up()
    for rel in up.KABUK_VARLIKLARI:
        p = kok / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_bytes(b"SAHTE-" + rel.encode())


def _kok_kur(tmp_path, req_icerik: str):
    (tmp_path / "backend").mkdir(exist_ok=True)
    (tmp_path / "backend" / "requirements-product.txt").write_text(req_icerik)
    (tmp_path / "electron").mkdir(exist_ok=True)
    (tmp_path / "electron" / "package.json").write_text(
        '{"devDependencies":{"electron":"29.0.0"}}')
    _kabuk_varliklari_yaz(tmp_path)
    return tmp_path


def test_shell_id_yorum_ve_siralamadan_etkilenmez(tmp_path, monkeypatch):
    """🔴 Gereksiz tam indirme kaynağı (2026-08-08'de kapatıldı).

    Yorum eklemek ya da satırları sıralamak kurulacak paket kümesini
    değiştirmez — ama `shell_id`'yi değiştirseydi bütün kurulumlar boş yere
    440 MB indirirdi.
    """
    up = _up()
    monkeypatch.setattr(up, "KOK", _kok_kur(tmp_path, "fastapi==1.0\nnumpy==2.0\n"))
    once = up.shell_id_hesapla()

    _kok_kur(tmp_path, "# yeni bir açıklama satırı\n\nnumpy==2.0\nfastapi==1.0   \n")
    assert up.shell_id_hesapla() == once, (
        "yorum/boşluk/sıra değişimi tam indirmeye düşürdü — anlam değişmedi"
    )


def test_shell_id_gercek_paket_degisimini_yakalar(tmp_path, monkeypatch):
    """Gürültüyü elerken sinyali de elememiş olmalıyız."""
    up = _up()
    monkeypatch.setattr(up, "KOK", _kok_kur(tmp_path, "fastapi==1.0\n"))
    once = up.shell_id_hesapla()

    _kok_kur(tmp_path, "fastapi==1.1\n")
    assert up.shell_id_hesapla() != once, "sürüm yükseltmesi yakalanmalı"

    _kok_kur(tmp_path, "fastapi==1.0\nyeni==0.1\n")
    assert up.shell_id_hesapla() != once, "yeni bağımlılık yakalanmalı"


# ── Kabuk varlıkları: paketin DIŞ kabuğu (2026-08-10) ───────────────────────

def test_shell_id_kabuk_varligi_degisimini_yakalar(tmp_path, monkeypatch):
    """🔴 Bu testin yokluğu, düzeltmenin müşteriye HİÇ ulaşmamasıydı.

    AppImage runtime dosyanın ELF başlığıdır, `yuki.sh` ise `extraFiles` ile
    paket köküne konur — ikisi de delta yükünün erişemediği yerde. Formülde
    olmadıkları için `488cf09`'un FUSE düzeltmesi `shell_id`'yi değiştirmiyor,
    istemci delta iniyor ve dış kabuk olduğu gibi kalıyordu: ekranda
    "güncellendi" yazıyor, Kali'de uygulama yine açılmıyordu.

    Her varlık TEK TEK ölçülür — biri listede olup hash'e karışmasaydı toplu
    bir test bunu göremezdi.
    """
    up = _up()
    kok = _kok_kur(tmp_path, "fastapi==1.0\n")
    monkeypatch.setattr(up, "KOK", kok)

    for rel in up.KABUK_VARLIKLARI:
        once = up.shell_id_hesapla()
        p = kok / rel
        eski = p.read_bytes()
        p.write_bytes(eski + b"-DEGISTI")
        assert up.shell_id_hesapla() != once, (
            f"{rel} değişti ama shell_id aynı kaldı → müşteri delta iner, "
            f"paketin dış kabuğu eski sürümde kalır"
        )
        p.write_bytes(eski)                       # sıradaki varlık izole ölçülsün
        assert up.shell_id_hesapla() == once, f"{rel} geri konunca shell_id dönmeli"


def test_shell_id_eksik_kabuk_varliginda_DURUR(tmp_path, monkeypatch):
    """Eksik dosyada sessizce devam etmek kapıyı kalıcı olarak kör ederdi.

    Yol yanlış yazılır ya da dosya kaldırılırsa hash sabitlenir ve runtime bir
    daha hiç `shell_id`'ye yansımaz — üstelik hiçbir belirti vermeden. Derleme
    burada durmalı; sahada sessizce yanlış davranmaktan ucuz.
    """
    up = _up()
    kok = _kok_kur(tmp_path, "fastapi==1.0\n")
    monkeypatch.setattr(up, "KOK", kok)
    up.shell_id_hesapla()                          # önce sağlıklı hâlde geçtiğini gör

    (kok / up.KABUK_VARLIKLARI[0]).unlink()
    with pytest.raises(SystemExit) as e:
        up.shell_id_hesapla()
    assert up.KABUK_VARLIKLARI[0] in str(e.value), "hata hangi dosyanın eksik olduğunu söylemeli"


def test_kabuk_varliklari_gercek_repoda_MEVCUT():
    """Liste gerçek ağaca karşı doğrulanır — sahte KOK'lu testler bunu göremez.

    Dosya taşınır ya da yeniden adlandırılırsa diğer testler yeşil kalmaya devam
    eder (kendi sahte ağaçlarını kuruyorlar); kırılan yalnız gerçek derleme olur
    ve bunu ilk gören geliştirici değil, `prep` adımı olmalı.
    """
    up = _up()
    eksik = [r for r in up.KABUK_VARLIKLARI if not (up.KOK / r).is_file()]
    assert not eksik, f"KABUK_VARLIKLARI listesi gerçekle uyuşmuyor, eksik: {eksik}"


# ── Manifest kanonik biçim kapısı ───────────────────────────────────────────

def test_manifest_ic_ice_yapiyi_REDDEDER():
    """🔴 Sessiz imza hatasının kapısı (2026-08-08).

    Node `canonical()` yalnız üst seviyeyi sıralar, Python `sort_keys=True`
    derinlemesine. İç içe bir alan bugün tesadüfen aynı baytları üretse bile
    imzayı görünmez bir varsayıma bağlar. SKU parmak izleri ilk denemede iç içe
    sözlüktü — bu kapı o yüzden var.
    """
    up = _up()
    # (test verisi de ASCII olmalı — "düz" yazmıştım, kapı haklı olarak durdurdu)
    assert up.manifest_kanonik_denetle({"a": "duz", "b": 1}) is None

    hata = up.manifest_kanonik_denetle({"skus": {"Yuki.AppImage": {"sha256": "x"}}})
    assert hata and "iç içe" in hata, "iç içe sözlük geçmemeliydi"

    hata = up.manifest_kanonik_denetle({"liste": ["a", "b"]})
    assert hata and "iç içe" in hata, "liste de geçmemeliydi"


def test_manifest_ascii_disi_reddeder():
    up = _up()
    assert up.manifest_kanonik_denetle({"ad": "Yuki"}) is None
    hata = up.manifest_kanonik_denetle({"ad": "Yükü"})
    assert hata and "ASCII" in hata


def test_sku_parmak_izi_duz_string_ve_sirali(tmp_path, monkeypatch):
    """SKU izleri düz string olmalı (iç içe olsaydı yukarıdaki kapı durdururdu)
    ve sıralı — aynı girdi her zaman aynı imzalanacak baytları vermeli."""
    up = _up()
    dist = tmp_path / "electron" / "dist"
    dist.mkdir(parents=True)
    (dist / "Yuki-9.9.9-offline.AppImage").write_bytes(b"B" * 10)
    (dist / "Yuki-9.9.9-lite.AppImage").write_bytes(b"A" * 5)
    (dist / "Yuki-9.9.9-win-x64-lite.zip").write_bytes(b"C" * 7)
    (dist / "baska-surum-Yuki-1.0.0-lite.AppImage").write_bytes(b"X")
    monkeypatch.setattr(up, "KOK", tmp_path)

    iz = up.sku_parmak_izleri("9.9.9")
    assert isinstance(iz, str)
    adlar = [k.split(":")[0] for k in iz.split(";")]
    assert adlar == sorted(adlar), "sıralı olmalı (deterministik imza)"
    assert len(adlar) == 3, "yalnız o sürümün varlıkları"
    assert all(a.startswith("Yuki-9.9.9-") for a in adlar)
    assert up.sku_parmak_izleri("9.9.9") == iz, "aynı girdi → aynı çıktı"
    assert up.sku_parmak_izleri("0.0.1") == "", "varlık yoksa boş (self-update teklif edilmez)"
