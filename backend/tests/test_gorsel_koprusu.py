"""Sohbete yüklenen görsel ↔ `ocr_image`/`read_qr` köprüsü.

Kusur (2026-08-05 geliştiricinin Free turunda bulundu, 2026-08-09'da kapandı):
kullanıcı sohbete fotoğraf **yükleyip** "bunu oku" diyordu, araç çalışmıyordu.
Şüphe koddaydı sanılmıştı — dev makinede RapidOCR 1,09 sn'de TR metni doğru
okuyor. Kusur **YOLDAYDI**:

    yükle → DATA_DIR/media_uploads/<ad>  →  image_msg  →  core.js (yalnız ÇİZER)
    ocr_image(path)  ← zorunlu `path`, modelin elinde ne ad ne yol var

Sistem promptu "bu fotoğraftaki yazı → ocr_image" diyordu; ilan edilen ama
ulaşılamayan araç. Free'nin 20 aracından biri sahada ölüydü — döviz kusuruyla
aynı sınıf, aynı turda bulundu.

Bu testler OCR/QR motorunu çalıştırmaz (pakette olmayabilir) — yalnız **yol
çözümünü** ölçer, kusur oradaydı.
"""

import pytest

from app.services.tools import vision_extra as vx


@pytest.fixture
def medya(tmp_path, monkeypatch):
    """`DATA_DIR`i geçici dizine al — gerçek media_uploads'a dokunulmaz."""
    monkeypatch.setattr("app.config.DATA_DIR", tmp_path)
    d = tmp_path / "media_uploads"
    d.mkdir()
    return d


def _gorsel(dizin, ad, mtime=None):
    p = dizin / ad
    p.write_bytes(b"\x89PNG\r\n\x1a\n" + b"0" * 32)
    if mtime is not None:
        import os
        os.utime(p, (mtime, mtime))
    return p


# ── ① Asıl kusur: yol yokken en son yüklenen görsel okunmalı ─────────────────

def test_bos_path_son_yuklenen_gorseli_secer(medya):
    """"bunu oku" senaryosu: model yol veremez, araç yine de doğru dosyayı bulmalı.

    Köprü kaldırılırsa burası kırmızı yanar (yol None döner).
    """
    _gorsel(medya, "eski_aaaaaaaa.png", mtime=1_000)
    yeni = _gorsel(medya, "yeni_bbbbbbbb.png", mtime=2_000)

    yol, notu = vx._gorsel_yolunu_coz("")

    assert yol == str(yeni)
    assert notu == ""          # normal akış — kullanıcıya not gösterilmez


def test_dosya_adi_yuklenenler_icinde_aranir(medya):
    """Model dosya adını biliyorsa (galeri listesi) tam yol gerekmemeli."""
    p = _gorsel(medya, "fatura_12ab34cd.png")

    yol, notu = vx._gorsel_yolunu_coz("fatura_12ab34cd.png")

    assert yol == str(p.resolve())
    assert notu == ""


def test_gercek_tam_yol_aynen_calisir(medya, tmp_path):
    """Geliştirici/tam yol davranışı DEĞİŞMEMELİ (regresyon koruması)."""
    disarda = tmp_path / "masaustu_ss.png"
    disarda.write_bytes(b"\x89PNG\r\n\x1a\n")

    yol, notu = vx._gorsel_yolunu_coz(str(disarda))

    assert yol == str(disarda)
    assert notu == ""


# ── ② Uydurma ad → sessizce yanlış dosya okunmaz, SÖYLENİR ───────────────────

def test_uydurma_ad_son_gorsele_duser_ama_not_birakir(medya):
    """Model olmayan bir ad uydurursa son görsele düşülür — ama cevapta yazar.

    Sessiz düşüş, kullanıcının "başka bir görselin metnini" doğru sanmasına
    yol açardı; bu yüzden not zorunlu.
    """
    son = _gorsel(medya, "gercek_dosya.png")

    yol, notu = vx._gorsel_yolunu_coz("ekran_goruntusu.png")

    assert yol == str(son)
    assert "bulunamadı" in notu
    assert "gercek_dosya.png" in notu


# ── ③ Güvenlik: dizin dışına çıkılamaz ───────────────────────────────────────

@pytest.mark.parametrize("kotu", ["../gizli.png", "..\\gizli.png", "alt/../../gizli.png"])
def test_ad_cozumu_yuklenenler_disina_cikamaz(medya, tmp_path, kotu):
    """Ayraç içeren ad media_uploads'ta ARANMAZ (api/media.py::_safe_path deseni).

    ⚠️ Kapsam: bu testin koruduğu şey **ad çözümü**. Aracın mutlak yol kabul
    etmesi kusur değil, eskiden beri olan davranış — `read_file`/`list_directory`
    de P1'de. Yani `/etc/passwd` verilirse okunur ve bu köprüyle gelen bir
    yetki genişlemesi DEĞİL; yeni olan tek şey, ad→dizin eşlemesinin
    media_uploads'a çivilenmiş olması.
    """
    (tmp_path / "gizli.png").write_bytes(b"sir")
    icerdeki = _gorsel(medya, "normal.png")

    yol, _ = vx._gorsel_yolunu_coz(kotu)

    assert yol == str(icerdeki)          # ③'e düşer, dizin dışına bağlanmaz
    assert "gizli" not in (yol or "")


# ── ④ Hiç görsel yokken anlaşılır mesaj (ham istisna değil) ──────────────────

def test_hic_gorsel_yoksa_yol_yok(medya):
    yol, notu = vx._gorsel_yolunu_coz("")
    assert yol is None
    assert notu == ""


def test_gorsel_yok_mesaji_yol_verilmediyse_yonlendirir(medya):
    mesaj = vx._gorsel_yok_mesaji("")
    assert "yükle" in mesaj


def test_gorsel_yok_mesaji_yol_verildiyse_yolu_soyler(medya):
    mesaj = vx._gorsel_yok_mesaji("/yok/olan.png")
    assert "/yok/olan.png" in mesaj


def test_medya_dizini_hic_yoksa_cokmez(tmp_path, monkeypatch):
    """Temiz kurulumda media_uploads henüz oluşmamış olabilir."""
    monkeypatch.setattr("app.config.DATA_DIR", tmp_path / "bos")
    yol, notu = vx._gorsel_yolunu_coz("")
    assert yol is None


# ── ⑤ Araçlar köprüyü gerçekten kullanıyor mu (uçtan uca, motorsuz) ──────────

async def test_ocr_image_gorsel_yokken_temiz_mesaj_doner(medya):
    """Motor kurulu olmasa bile 'dosya yok' yolu ham istisna vermemeli."""
    out = await vx.ocr_image("")
    assert "yükle" in out


async def test_read_qr_gorsel_yokken_temiz_mesaj_doner(medya):
    out = await vx.read_qr("")
    assert "yükle" in out


async def test_ocr_image_desteklenmeyen_tur(medya):
    """Köprü çözdükten sonra tür denetimi hâlâ çalışıyor (regresyon)."""
    (medya / "belge.gif").write_bytes(b"GIF89a")
    out = await vx.ocr_image("belge.gif")
    assert "Desteklenmeyen dosya türü" in out
