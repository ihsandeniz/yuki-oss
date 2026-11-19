"""API anahtarları işletim sistemi anahtarlığında (2026-10-10).

Gerçek anahtarlığa DOKUNMAZ: her test sahte bir keyring arka ucu takar (`keyring.set_keyring`)
ya da anahtarlığı yok sayar. Gerçek makinedeki deneme ayrı yapıldı (2026-10-10).

Kapılar:
- göç: `.env`'deki anahtar anahtarlığa geçer, `.env`'den silinir, diğer satırlar kalır
- veri kaybı yok: geri okuma tutmazsa / anahtarlık takılırsa satır `.env`'de kalır
- anahtarlıksız ortam: ürün açılır, anahtar `.env`'de, dosya izni 600, durum "dosya"
- yazma yolu (`_persist_env`): anahtar `.env`'e değil anahtarlığa; eski kopyası silinir
- profil ayrımı: iki veri dizini birbirinin anahtarını görmez
"""
import os
import stat
import sys
import time

import pytest

keyring = pytest.importorskip("keyring")
from keyring.backend import KeyringBackend  # noqa: E402
from keyring.backends import fail  # noqa: E402

from app.services import sirlar  # noqa: E402

SAHTE = "sk-or-v1-" + "a1b2c3d4" * 6   # biçimi gerçekçi, değeri uydurma


class _Bellek(KeyringBackend):
    priority = 10

    def __init__(self, bozuk=False, uyur=0.0):
        super().__init__()
        self.d, self.bozuk, self.uyur = {}, bozuk, uyur

    def set_password(self, servis, kullanici, parola):
        if self.uyur:
            time.sleep(self.uyur)
        self.d[(servis, kullanici)] = parola

    def get_password(self, servis, kullanici):
        if self.uyur:
            time.sleep(self.uyur)
        v = self.d.get((servis, kullanici))
        return (v + "x") if (self.bozuk and v and kullanici.endswith("_API_KEY")) else v

    def delete_password(self, servis, kullanici):
        self.d.pop((servis, kullanici), None)


@pytest.fixture
def ortam(tmp_path, monkeypatch):
    """Temiz veri dizini + temiz ortam değişkenleri + anahtarlık açık."""
    monkeypatch.delenv("YUKI_ANAHTARLIK", raising=False)
    for ad in set(sirlar.BILINEN) | {"ELEVENLABS_API_KEY"}:
        monkeypatch.delenv(ad, raising=False)
    onceki, durum = keyring.get_keyring(), sirlar.durum()
    yield tmp_path
    keyring.set_keyring(onceki)
    monkeypatch.setattr(sirlar, "_kr", None)              # modül durumu sonraki testlere sızmasın
    sirlar._durum.clear(); sirlar._durum.update(durum)


def _env(dizin, metin):
    p = dizin / ".env"
    p.write_text(metin, encoding="utf-8")
    return p


def _hicbir_dosyada_yok(kok, deger):
    for p in kok.rglob("*"):
        if p.is_file():
            assert deger not in p.read_text(encoding="utf-8", errors="replace"), f"{p} içinde"


# ── göç ────────────────────────────────────────────────────────────────

def test_env_deki_anahtar_anahtarliga_tasinir_ve_env_den_silinir(ortam):
    kr = _Bellek(); keyring.set_keyring(kr)
    env = _env(ortam, f"# yorum kalır\nOPENROUTER_API_KEY={SAHTE}\nLLM_MODEL=google/gemma:free\nPORT=8001\n")
    d = sirlar.yukle(env, ortam)
    assert d["depo"] == "anahtarlik" and d["tasinan"] == 1
    metin = env.read_text(encoding="utf-8")
    assert "OPENROUTER_API_KEY" not in metin
    assert "# yorum kalır" in metin and "LLM_MODEL=google/gemma:free" in metin and "PORT=8001" in metin
    assert os.environ["OPENROUTER_API_KEY"] == SAHTE          # kod os.getenv ile okumaya devam eder
    assert SAHTE in kr.d.values()
    _hicbir_dosyada_yok(ortam, SAHTE)


def test_ikinci_acilista_anahtar_anahtarliktan_gelir(ortam, monkeypatch):
    kr = _Bellek(); keyring.set_keyring(kr)
    env = _env(ortam, f"OPENROUTER_API_KEY={SAHTE}\n")
    sirlar.yukle(env, ortam)
    monkeypatch.delenv("OPENROUTER_API_KEY")                  # yeni süreç gibi
    d = sirlar.yukle(env, ortam)
    assert d["tasinan"] == 0 and os.environ["OPENROUTER_API_KEY"] == SAHTE


def test_kalibi_tasiyan_bilinmeyen_anahtar_da_tasinir_ve_geri_gelir(ortam, monkeypatch):
    keyring.set_keyring(_Bellek())
    env = _env(ortam, "ELEVENLABS_API_KEY=el-uydurma-123\n")
    sirlar.yukle(env, ortam)
    monkeypatch.delenv("ELEVENLABS_API_KEY")
    sirlar.yukle(env, ortam)                                  # dizin kaydı sayesinde bulunur
    assert os.environ["ELEVENLABS_API_KEY"] == "el-uydurma-123"


def test_geri_okuma_tutmazsa_satir_env_de_kalir(ortam):
    keyring.set_keyring(_Bellek(bozuk=True))
    env = _env(ortam, f"OPENROUTER_API_KEY={SAHTE}\n")
    d = sirlar.yukle(env, ortam)
    assert f"OPENROUTER_API_KEY={SAHTE}" in env.read_text(encoding="utf-8")
    assert d["tasinan"] == 0


def test_takilan_anahtarlik_acilisi_kilitlemez_env_de_birakir(ortam, monkeypatch):
    monkeypatch.setattr(sirlar, "ZAMAN_ASIMI", 0.2)
    keyring.set_keyring(_Bellek(uyur=2.0))                    # kilitli koleksiyon: parola penceresi bekler
    env = _env(ortam, f"OPENROUTER_API_KEY={SAHTE}\n")
    t0 = time.monotonic()
    d = sirlar.yukle(env, ortam)
    assert time.monotonic() - t0 < 1.5
    assert d["depo"] == "dosya" and d["sebep"].startswith("hata: TimeoutError")
    assert f"OPENROUTER_API_KEY={SAHTE}" in env.read_text(encoding="utf-8")


# ── anahtarlıksız ortam ─────────────────────────────────────────────────

@pytest.mark.skipif(sys.platform == "win32", reason="POSIX izin bitleri")
def test_anahtarlik_yoksa_env_kalir_izin_600_durum_dosya(ortam):
    keyring.set_keyring(fail.Keyring())
    env = _env(ortam, f"OPENROUTER_API_KEY={SAHTE}\n")
    os.chmod(env, 0o644)
    d = sirlar.yukle(env, ortam)
    assert d == {"depo": "dosya", "arka_uc": None, "sebep": "anahtarlik-yok", "tasinan": 0}
    assert f"OPENROUTER_API_KEY={SAHTE}" in env.read_text(encoding="utf-8")
    assert stat.S_IMODE(env.stat().st_mode) == 0o600
    assert sirlar.kaydet("OPENROUTER_API_KEY", SAHTE) is False


def test_paket_yoksa_dosya_yedegi(ortam, monkeypatch):
    monkeypatch.setitem(sys.modules, "keyring", None)         # eski pybundle: paket yok
    d = sirlar.yukle(_env(ortam, ""), ortam)
    assert d["depo"] == "dosya" and d["sebep"] == "paket-yok"


def test_ortam_degiskeniyle_kapatilabilir(ortam, monkeypatch):
    keyring.set_keyring(_Bellek())
    monkeypatch.setenv("YUKI_ANAHTARLIK", "0")
    assert sirlar.yukle(_env(ortam, ""), ortam)["sebep"] == "kapatildi"


# ── yazma yolu: key sihirbazı ───────────────────────────────────────────

@pytest.fixture
def api_env(ortam, monkeypatch):
    from app import config
    from app.api import llm_config_api as api
    env = _env(ortam, f"OPENROUTER_API_KEY=eski-duz-metin\nLLM_MODEL=a\n")
    monkeypatch.setattr(config, "ENV_PATH", env)
    return api, env


def test_sihirbaz_anahtari_anahtarliga_yazar_env_deki_eski_kopyayi_siler(api_env, ortam):
    api, env = api_env
    kr = _Bellek(); keyring.set_keyring(kr)
    sirlar.yukle(ortam / "yok.env", ortam)                    # anahtarlık açık, göç yok
    api._persist_env("OPENROUTER_API_KEY", SAHTE)
    api._persist_env("LLM_MODEL", "b")                        # sır olmayan ayar dosyada kalır
    metin = env.read_text(encoding="utf-8")
    assert "OPENROUTER_API_KEY" not in metin and "LLM_MODEL=b" in metin
    assert SAHTE in kr.d.values()
    _hicbir_dosyada_yok(ortam, SAHTE)


@pytest.mark.skipif(sys.platform == "win32", reason="POSIX izin bitleri")
def test_anahtarlik_yokken_sihirbaz_env_e_yazar_izin_600(api_env, ortam):
    api, env = api_env
    keyring.set_keyring(fail.Keyring())
    sirlar.yukle(ortam / "yok.env", ortam)
    os.chmod(env, 0o644)
    api._persist_env("OPENROUTER_API_KEY", SAHTE)
    assert f"OPENROUTER_API_KEY={SAHTE}" in env.read_text(encoding="utf-8")
    assert stat.S_IMODE(env.stat().st_mode) == 0o600


async def test_durum_ucu_depoyu_ve_uyariyi_soyler(ortam):
    from app.api import llm_config_api as api

    class _Istek:
        class _C:
            host = "127.0.0.1"
        client = _C(); headers: dict = {}; scope: dict = {"type": "http"}

    keyring.set_keyring(fail.Keyring())
    sirlar.yukle(ortam / "yok.env", ortam)
    d = await api.get_key_status.__wrapped__(_Istek())
    assert d["depo"] == "dosya" and ("şifresiz" in d["depo_uyari"] or "unencrypted" in d["depo_uyari"])
    keyring.set_keyring(_Bellek())
    sirlar.yukle(ortam / "yok.env", ortam)
    d = await api.get_key_status.__wrapped__(_Istek())
    assert d["depo"] == "anahtarlik" and d["depo_uyari"] == ""


# ── ayrım ve kayıt tutarlılığı ──────────────────────────────────────────

def test_iki_veri_dizini_birbirinin_anahtarini_gormez(ortam, tmp_path_factory, monkeypatch):
    keyring.set_keyring(_Bellek())
    a = ortam / "musteri"; a.mkdir()
    b = tmp_path_factory.mktemp("dev-profili")
    sirlar.yukle(_env(a, f"OPENROUTER_API_KEY={SAHTE}\n"), a)
    monkeypatch.delenv("OPENROUTER_API_KEY")
    sirlar.yukle(_env(b, ""), b)
    assert "OPENROUTER_API_KEY" not in os.environ


def test_bilinen_adlar_saglayici_kaydiyla_ayni():
    from app.services import llm_providers as _lp
    bulut = {s.env for s in _lp.hepsi() if not s.yerel}
    assert set(sirlar.BILINEN) == bulut
    assert all(sirlar.sir_mi(a) for a in bulut)
    assert not sirlar.sir_mi("LLM_MODEL") and not sirlar.sir_mi("OLLAMA_MODEL")


def test_sirlar_llm_providers_i_import_etmez():
    """Etseydi `llm_providers._env_yukle` anahtarlıktaki anahtarlar ortama konmadan çalışırdı."""
    kaynak = (sirlar.__file__ and open(sirlar.__file__, encoding="utf-8").read())
    kod = "\n".join(s for s in kaynak.splitlines() if not s.lstrip().startswith("#"))
    assert "import llm_providers" not in kod and "from app.services.llm_providers" not in kod
