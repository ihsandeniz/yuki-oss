"""Dosya araçları + görsel üretme — ikili okuma, .env adı, zip, düz tar, görsel modeli.

Yan etki yok: dosyalar geçici dizinde, OpenRouter sahte istemciyle.
· D25 ikili dosya `errors='ignore'` ile metin sanılıp modele çöp olarak gidiyordu
· D26 `.env` alt dizgesi `my.environment.txt` gibi masum adları da yazmaya kapatıyordu
· D27 klasörün içine yazılan zip kendini içeriyordu
· D28 düz `.tar` "desteklenmeyen biçim" diye reddediliyordu
· G1 `openai/dall-e-3` OpenRouter'ın görsel model listesinde yok → her çağrı hata;
     biçim PNG sanılıyordu (webp/jpeg dönen modelde bozuk görsel)
"""
from __future__ import annotations

import base64
import tarfile
import types
import zipfile

import pytest

from app.services.tools import files
from app.services.tools._base import _is_safe_write_path


def test_d25_ikili_dosya_dokulmez(tmp_path):
    p = tmp_path / "g.png"
    p.write_bytes(b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00")
    r = files.read_file(str(p))
    assert r.startswith("Hata") and "IHDR" not in r


def test_d25_metin_ve_bozuk_utf8_aynen_okunur(tmp_path):
    (tmp_path / "t.txt").write_text("çığ öşü\nikinci\n", encoding="utf-8")
    assert files.read_file(str(tmp_path / "t.txt")) == "çığ öşü\nikinci\n"
    (tmp_path / "l.txt").write_bytes("abc\xfe".encode("latin-1"))
    assert files.read_file(str(tmp_path / "l.txt")) == "abc"


@pytest.mark.parametrize("ad", ["my.environment.txt", "a.envelope.md", "kisisel.envanter"])
def test_d26_env_benzeri_ad_yazilir(tmp_path, ad):
    assert _is_safe_write_path(tmp_path / ad)[0]


@pytest.mark.parametrize("ad", [".env", ".env.local", ".env.example", "prod.env", ".envrc",
                                ".env-yedek", ".env_eski", "x.env.bak", ".env/ic.txt"])
def test_d26_gercek_env_yine_reddedilir(tmp_path, ad):
    ok, err = _is_safe_write_path(tmp_path / ad)
    assert not ok and "hassas" in err


def test_d27_zip_kendini_icermez(tmp_path):
    k = tmp_path / "repo"
    (k / "alt").mkdir(parents=True)
    (k / "a.txt").write_text("a")
    (k / "alt/b.txt").write_text("b")
    assert files.compress_file(str(k), str(k / "ic.zip")).startswith("Sıkıştırıldı")
    adlar = zipfile.ZipFile(k / "ic.zip").namelist()
    assert not any(a.endswith("ic.zip") for a in adlar)
    assert {"repo/a.txt", "repo/alt/b.txt"} <= set(adlar)


def _tar(yol, ad="t.txt"):
    kaynak = yol.parent / "kaynak.txt"
    kaynak.write_text("merhaba")
    with tarfile.open(yol, "w") as tf:
        tf.add(kaynak, arcname=ad)


def test_d28_duz_tar_acilir(tmp_path):
    _tar(tmp_path / "duz.tar")
    r = files.extract_archive(str(tmp_path / "duz.tar"), str(tmp_path / "c"))
    assert r.startswith("Çıkarıldı") and (tmp_path / "c/t.txt").read_text() == "merhaba"


def test_d28_duz_tar_kacisi_reddedilir(tmp_path):
    _tar(tmp_path / "k.tar", ad="../kacis.txt")
    r = files.extract_archive(str(tmp_path / "k.tar"), str(tmp_path / "c"))
    assert "path traversal" in r and not (tmp_path / "kacis.txt").exists()


def test_d28_duz_tar_bagi_reddedilir(tmp_path):
    with tarfile.open(tmp_path / "b.tar", "w") as tf:
        bilgi = tarfile.TarInfo("bag")
        bilgi.type = tarfile.SYMTYPE
        bilgi.linkname = "/etc/passwd"
        tf.addfile(bilgi)
    r = files.extract_archive(str(tmp_path / "b.tar"), str(tmp_path / "c"))
    assert "symlink" in r and not (tmp_path / "c/bag").exists()


# ── G1 generate_image ─────────────────────────────────────────────────────────

def _kur_gorsel(monkeypatch, bayt):
    import openai
    from app.services import event_bus
    giden, yayin = [], []

    class _Gorseller:
        async def generate(self, **k):
            giden.append(k)
            return types.SimpleNamespace(data=[types.SimpleNamespace(
                b64_json=base64.b64encode(bayt).decode())])

    class _Istemci:
        def __init__(self, **k):
            self.images = _Gorseller()

    async def _yayinla(olay, veri):
        yayin.append((olay, veri))

    monkeypatch.setattr(openai, "AsyncOpenAI", _Istemci)
    monkeypatch.setattr(event_bus.bus, "publish", _yayinla)
    return giden, yayin


@pytest.mark.asyncio
async def test_g1_model_listede_olan_model_ve_gercek_bicim(monkeypatch):
    from app.services.tools import vision_extra as v
    giden, yayin = _kur_gorsel(monkeypatch, b"RIFF\x00\x00\x00\x00WEBPVP8 ")
    r = await v.generate_image("kedi")
    assert giden[0]["model"] != "openai/dall-e-3" and giden[0]["model"] == v.GORSEL_MODELI
    assert r.startswith("Görüntü oluşturuldu")
    assert yayin[0][1]["mime"] == "image/webp", "webp yanıt PNG diye gönderildi"


@pytest.mark.asyncio
async def test_g1_gorsel_olmayan_yanit_sohbete_gonderilmez(monkeypatch):
    from app.services.tools import vision_extra as v
    _, yayin = _kur_gorsel(monkeypatch, b"<html>hata</html>")
    r = await v.generate_image("kedi")
    assert yayin == [] and "görsel değil" in r
