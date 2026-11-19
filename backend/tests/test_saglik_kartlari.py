"""SAĞLIK · YETENEK KARTLARI ( panel 10, 2026-09-28 — geliştirici taslak B'yi seçti).

Kapanan kusurlar ve buradaki kapıları:
- Yalan yeşil: ölçülemeyen denetim (disk okunamadı, model listesi alınamadı, sağlayıcı
  denetlenemiyor) `ok:true` + "yolunda" çiziliyordu → `durum: "olculemedi"`.
- Düzelt yalanı: model onarımı servisi OpenRouter'a ZORLUYOR ve yalnız LLM_MODEL'i yazıyordu;
  veri klasörü onarımı klasör salt okunurken "oluşturuldu" diyordu.
- Günlük şişmesi: her GET denetimi aynı kritik bulguyu yeniden yazıyordu (canlıda 415 kayıt).
- `temizle_gunluk` silemeyince uç `ok:true` dönüyordu.
- Tam yol (kullanıcı adı) ekrana ve desteğe kopyalanan günlüğe gidiyordu.
- Arayüz: satır içi onclick/stil/emoji, panel yalnız ilk açılışta denetleniyordu, çift tık iki istek.
"""
from __future__ import annotations

import logging
import re
from datetime import datetime, timedelta
from pathlib import Path

import pytest

from app.db.connection import get_pool as _gercek_get_pool   # conftest her testte get_pool'u saplıyor
from app.services import error_log, self_check
from tests.yardim import FRONTEND, sozluk, yorumsuz

INTRO = FRONTEND / "js" / "intro-sequences.js"
INDEX = FRONTEND / "index.html"


@pytest.fixture(autouse=True)
def _izole_gunluk(tmp_path, monkeypatch):
    monkeypatch.setattr(error_log, "_dosya", lambda: tmp_path / "hata-gunlugu.jsonl")
    yield


def _saglik_blogu() -> str:
    s = INTRO.read_text(encoding="utf-8")
    blok = s[s.index("// ════════ SAĞLIK · YETENEK KARTLARI"):]
    return blok[: blok.index("// ════════ AYARLAR")]


# ── ① Dört durum: ölçülemeyen "yolunda" değildir ─────────────────────────────

def test_sonuc_dort_durumu_ayiriyor():
    assert self_check._sonuc("a", "A", True, self_check.BILGI)["durum"] == "iyi"
    o = self_check._sonuc("a", "A", True, self_check.BILGI, olculemedi=True)
    assert o["durum"] == "olculemedi" and o["ok"] is True and o["olculemedi"] is True
    assert self_check._sonuc("a", "A", False, self_check.UYARI, cozum="x")["durum"] == "uyari"
    assert self_check._sonuc("a", "A", False, self_check.KRITIK, cozum="x")["durum"] == "kritik"


def test_disk_olculemezse_yesil_yanmaz(monkeypatch):
    def _patla(_yol):
        raise OSError("okunamadı")
    monkeypatch.setattr(self_check.shutil, "disk_usage", _patla)
    d = self_check._denetle_disk()
    assert d["durum"] == "olculemedi", "okunamayan disk 'yolunda' çiziliyor"
    assert d["seviye"] != self_check.KRITIK


@pytest.mark.asyncio
async def test_model_listesi_alinamazsa_olculemedi(monkeypatch):
    from app.services import llm as llm_mod
    monkeypatch.setattr(llm_mod, "_runtime_provider", "openrouter", raising=False)
    monkeypatch.setattr(llm_mod, "_runtime_model", "google/gemma-4-26b-a4b-it:free", raising=False)
    monkeypatch.setattr(llm_mod, "USE_LOCAL_LLM", False, raising=False)

    async def _ag_yok():
        raise RuntimeError("ağ yok")
    monkeypatch.setattr("app.api.llm_config_api._fetch_live_groups", _ag_yok)
    d = await self_check._denetle_llm_model()
    assert d["durum"] == "olculemedi" and d["otomatik_duzeltilebilir"] is False


@pytest.mark.asyncio
async def test_genel_durum_olculemedi_ve_sayaci(monkeypatch):
    iyi = lambda k: self_check._sonuc(k, k, True, self_check.BILGI)  # noqa: E731
    for ad in ("_denetle_veri_dizini", "_denetle_llm_anahtar", "_denetle_ucretsiz_kota",
               "_denetle_onnxruntime", "_denetle_stt", "_denetle_ffmpeg"):
        monkeypatch.setattr(self_check, ad, lambda ad=ad: iyi(ad))
    monkeypatch.setattr(self_check, "_denetle_disk",
                        lambda: self_check._sonuc("disk", "Boş alan", True, self_check.BILGI, olculemedi=True))

    async def _model():
        return iyi("llm_model")
    monkeypatch.setattr(self_check, "_denetle_llm_model", _model)
    r = await self_check.calistir()
    assert r["ok"] is True and r["kritik_sayisi"] == 0
    assert r["durum"] == "olculemedi" and r["olculemedi_sayisi"] == 1


# ── ② Düzelt yalan söylemez ─────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_model_onarimi_servisi_openroutera_zorlamaz(monkeypatch):
    from app.services import llm as llm_mod
    from app.api import llm_config_api as api
    monkeypatch.setattr(llm_mod, "_runtime_provider", "google", raising=False)
    monkeypatch.setattr(llm_mod, "_runtime_model", "gemini-eski", raising=False)
    monkeypatch.setattr(llm_mod, "USE_LOCAL_LLM", False, raising=False)
    yazilan = []
    monkeypatch.setattr(api, "_persist_env", lambda k, v: yazilan.append((k, v)))

    gidildi = []

    async def _liste():   # liste GELİYOR — koruma yoksa onarım onu seçip servisi çevirirdi
        gidildi.append(1)
        return [{"options": [{"id": "google/gemma-4-26b-a4b-it:free", "label": "x"}]}]
    monkeypatch.setattr(api, "_fetch_live_groups", _liste)

    r = await self_check.onar("llm_model")
    assert r["ok"] is False and r.get("yonlendir") == "key"
    assert not gidildi, "OpenRouter listesine gidildi — başka servisin modeli oradan seçilemez"
    assert llm_mod.get_runtime_config()["provider"] == "google", "servis sessizce değiştirildi"
    assert yazilan == [], ".env'e yazıldı"


@pytest.mark.asyncio
async def test_model_onarimi_saglayici_ve_modeli_birlikte_yazar(monkeypatch):
    from app.services import llm as llm_mod
    from app.api import llm_config_api as api
    monkeypatch.setattr(llm_mod, "_runtime_provider", "openrouter", raising=False)
    monkeypatch.setattr(llm_mod, "_runtime_model", "olmayan/model:free", raising=False)
    monkeypatch.setattr(llm_mod, "USE_LOCAL_LLM", False, raising=False)
    yazilan = []
    monkeypatch.setattr(api, "_persist_env", lambda k, v: yazilan.append((k, v)))

    async def _gruplar():
        return [{"options": [{"id": "google/gemma-4-26b-a4b-it:free", "label": "x"}]}]
    monkeypatch.setattr(api, "_fetch_live_groups", _gruplar)

    r = await self_check.onar("llm_model")
    assert r["ok"] is True and r["kalici"] is True
    assert dict(yazilan) == {"LLM_PROVIDER": "openrouter", "LLM_MODEL": "google/gemma-4-26b-a4b-it:free"}


@pytest.mark.asyncio
async def test_model_kalici_yazilamazsa_duzeldi_demez(monkeypatch):
    from app.services import llm as llm_mod
    from app.api import llm_config_api as api
    monkeypatch.setattr(llm_mod, "_runtime_provider", "openrouter", raising=False)
    monkeypatch.setattr(llm_mod, "_runtime_model", "olmayan/model:free", raising=False)
    monkeypatch.setattr(llm_mod, "USE_LOCAL_LLM", False, raising=False)

    def _yazamaz(k, v):
        raise PermissionError("salt okunur")
    monkeypatch.setattr(api, "_persist_env", _yazamaz)

    async def _gruplar():
        return [{"options": [{"id": "google/gemma-4-26b-a4b-it:free", "label": "x"}]}]
    monkeypatch.setattr(api, "_fetch_live_groups", _gruplar)

    r = await self_check.onar("llm_model")
    assert r["ok"] is True and r["kalici"] is False
    assert r["mesaj"] != self_check.M("saglik.onar-model-degisti", model=r["model"])


@pytest.mark.asyncio
async def test_klasor_var_ama_yazilamiyorsa_olusturuldu_demez(tmp_path, monkeypatch):
    import app.config as config
    monkeypatch.setattr(config, "DATA_DIR", tmp_path)   # klasör VAR

    def _yazamaz(_yol):
        raise PermissionError("izin yok")
    monkeypatch.setattr(self_check, "_yazilabilir_yap", _yazamaz)
    r = await self_check.onar("veri_dizini")
    assert r["ok"] is False
    assert r["mesaj"] != self_check.M("saglik.onar-klasor-hazir", yol="~")
    assert "yazılamıyor" in r["mesaj"] or "writable" in r["mesaj"], r["mesaj"]


# ── ③ Günlük: tekrar yazılmaz · 24 saat özeti · silinemezse ok:false · ev dizini ──

@pytest.mark.asyncio
async def test_ayni_kritik_bulgu_gunluge_bir_kez(monkeypatch):
    monkeypatch.setattr(self_check, "_denetle_llm_anahtar",
                        lambda: self_check._sonuc("llm_anahtar", "A", False, self_check.KRITIK,
                                                  "anahtar yok", "gir"))
    for _ in range(3):
        await self_check.calistir()
    kurulum = [k for k in error_log.son_kayitlar() if k["kaynak"] == "kurulum" and k["neden"] == "llm_anahtar"]
    assert len(kurulum) == 1, f"her denetim aynı bulguyu yeniden yazıyor ({len(kurulum)} kayıt)"


def test_ozet_yalniz_son_24_saati_sayar(tmp_path):
    import json
    eski = (datetime.now().astimezone() - timedelta(days=3)).isoformat(timespec="seconds")
    (tmp_path / "hata-gunlugu.jsonl").write_text(
        json.dumps({"zaman": eski, "kaynak": "ses", "neden": "eski", "ayrinti": "x", "seviye": "error"}) + "\n",
        encoding="utf-8")
    error_log.kaydet("llm", "404", "model bulunamadı")
    error_log.kaydet("llm", "404", "model bulunamadı")
    o = error_log.ozet()
    assert o["toplam"] == 3 and o["son_24s"] == 2
    assert o["en_sik_24s"]["anahtar"] == "llm/404" and o["en_sik_24s"]["adet"] == 2


@pytest.mark.asyncio
async def test_gunluk_silinemezse_ok_false(client, monkeypatch):
    def _silemez():
        raise PermissionError("kullanımda")
    monkeypatch.setattr(error_log, "temizle_gunluk", _silemez)
    r = await client.delete("/api/errors")
    assert r.status_code == 200 and r.json()["ok"] is False


def test_ev_dizini_kisaltiliyor(monkeypatch, tmp_path):
    ev = tmp_path / "kullanici-adi"
    monkeypatch.setattr(Path, "home", classmethod(lambda cls: ev))
    import app.config as config
    monkeypatch.setattr(config, "DATA_DIR", ev / ".config" / "alice-ai")
    d = self_check._denetle_veri_dizini()
    assert "kullanici-adi" not in d["detay"] and "~" in d["detay"]
    error_log.kaydet("kurulum", "x", f"{ev}/gizli.txt yazılamadı")
    assert "kullanici-adi" not in error_log.son_kayitlar()[0]["ayrinti"]


# ── ④ Bekleyen yeniden başlatma: süreç belleği, geri alınınca düşer ──────────

def test_bekleyen_yeniden_baslatma_geri_alininca_duser(monkeypatch):
    from app.api import settings_api as sa
    monkeypatch.setattr(sa, "_ACILIS_DEGERI", {})
    monkeypatch.setattr(sa, "_BEKLEYEN", {})
    sa._bekleyen_isaretle("TTS_RATE", "+0%", "+10%")
    assert [b["key"] for b in sa.bekleyen_yeniden_baslatma()] == ["TTS_RATE"]
    sa._bekleyen_isaretle("TTS_RATE", "+10%", "+0%")   # açılıştaki değere döndü
    assert sa.bekleyen_yeniden_baslatma() == []


# ── ⑤ Postgres uyarısı tekrarlanmaz ─────────────────────────────────────────

@pytest.mark.asyncio
async def test_ayni_pg_hatasi_ikinci_kez_warning_basmaz(monkeypatch, caplog):
    from app.db import connection as c

    async def _patla(*a, **k):
        raise ConnectionRefusedError(111, "Connection refused")
    monkeypatch.setattr(c, "DATABASE_URL", "postgresql://x@localhost:1/y")
    monkeypatch.setattr(c, "_pool", None)
    monkeypatch.setattr(c, "_son_uyari", None)
    monkeypatch.setattr(c.asyncpg, "create_pool", _patla)
    caplog.set_level(logging.DEBUG, logger="app.db.connection")
    for _ in range(3):
        monkeypatch.setattr(c, "_pool_fail_at", None)   # yeniden deneme penceresini atla
        assert await _gercek_get_pool() is None
    uyarilar = [r for r in caplog.records if r.name == "app.db.connection" and r.levelno >= logging.WARNING]
    assert len(uyarilar) == 1, f"aynı bağlantı hatası {len(uyarilar)} kez WARNING — günlüğü dolduruyor"


# ── ⑥ Arayüz kapıları ───────────────────────────────────────────────────────

def test_arayuz_satir_ici_onclick_stil_emoji_yok():
    blok = yorumsuz(_saglik_blogu())
    assert "onclick=" not in blok and "style=" not in blok, "satır içi onclick/stil geri gelmiş"
    assert "⚠" not in blok and "✓" not in blok and "✕" not in blok
    s = INDEX.read_text(encoding="utf-8")
    panel = s[s.index('<div id="hq-panel-saglik"'):]
    panel = panel[: panel.index('id="sag-yeniden-baslat"') + 200]
    assert "onclick=" not in panel and "style=" not in panel
    assert "/ui/css/hq-saglik.css" in s


def test_panel_her_acilista_denetler_ve_cift_tik_tek_istek():
    s = yorumsuz(INTRO.read_text(encoding="utf-8"))
    assert "if(name==='saglik'){ saglikTara(); }" in s, "SAĞLIK yalnız ilk açılışta denetleniyor"
    assert "_loaded.saglik" not in s
    blok = _saglik_blogu()
    govde = blok[blok.index("window.saglikTara = function"):]
    govde = govde[: govde.index("async function _sagDenetle")]
    assert govde.index("if(_sagSurer) return _sagSurer;") < govde.index("_sagDenetle()"), (
        "denetim sürerken yeni istek gidiyor — üç hızlı tık üç istek")
    onar = blok[blok.index("window.saglikOnar = async function"):]
    assert "_sagIs['onar:'+kimlik]) return;" in onar[:400], "Düzelt çift tıkta iki onarım yollar"


def test_bilinmeyen_denetim_diger_kartina_duser_ve_olculemedi_ayri():
    blok = _saglik_blogu()
    assert "(k || diger).ds.push(x)" in blok, "bilinmeyen kimlikli denetim kartsız kalıyor"
    assert "olculemedi:'saglik.sayac.olcul'" in blok and "olculemedi:'saglik.et.olcul'" in blok
    s = INTRO.read_text(encoding="utf-8")
    tablo = s[s.index("var _dilTazeleyici = {"):]
    assert "saglik: function()" in tablo[: tablo.index("\n  };")], "dil değişince SAĞLIK eski dilde kalır"


def test_hukum_uyari_varken_her_sey_yolunda_demez():
    tr = sozluk("tr")
    blok = _saglik_blogu()
    # "Her şey yolunda" yalnız hiç kritik/uyarı/ölçülemedi yokken seçilir
    assert ("var genel=say.kritik?'kritik':(say.kurulum?'kurulum':(say.uyari?'uyari':"
            "(say.olculemedi?'olculemedi':'iyi')));") in blok
    assert tr["saglik.hukum.iyi"] == "Her şey yolunda"
    assert "yolunda" not in tr["saglik.hukum.uyari"] and "yolunda" not in tr["saglik.hukum.olcul"]


def test_sagligin_tum_anahtarlari_iki_dilde():
    blok = _saglik_blogu()
    anahtarlar = set(re.findall(r"\bt[c]?\(\s*'([a-z0-9_.-]+)'", blok))
    anahtarlar |= set(re.findall(r"'((?:hq\.)?saglik\.[a-z0-9_.-]+|yb\.[a-z0-9_.-]+)'", blok))
    tr, en = sozluk("tr"), sozluk("en")
    eksik = sorted(k for k in anahtarlar if k not in tr or k not in en)
    assert not eksik, f"sözlükte yok: {eksik}"
    assert len(anahtarlar) >= 50


# ── ⑦ goz tur 1: ham hata ekrana gitmez · okunur model adı · ortak ışık · gerçek ekran adları ──

def test_ham_hata_ekrana_degil_teknik_alana(monkeypatch):
    def _izin_yok(_yol):
        raise PermissionError(13, "Permission denied", "/home/biri/.config/alice-ai")
    monkeypatch.setattr(self_check.shutil, "disk_usage", _izin_yok)
    d = self_check._denetle_disk()
    assert "Errno" not in d["detay"] and "Permission" not in d["detay"], d["detay"]
    assert "Errno" in d["teknik"] or "Permission" in d["teknik"]


def test_model_satiri_okunur_ad_gosterir():
    assert self_check._model_adi("google/gemma-4-26b-a4b-it:free") == self_check.M("llm.model-gemma")
    ad = self_check._model_adi("meta-llama/llama-3.3-70b-instruct:free")
    assert "/" not in ad and ":free" not in ad and ad.startswith("Llama")


def test_kota_karti_kisa_ve_jargonsuz(monkeypatch):
    from app.services import llm as llm_mod
    monkeypatch.setattr(llm_mod, "_runtime_provider", "openrouter", raising=False)
    monkeypatch.setattr(llm_mod, "_runtime_model", "google/gemma-4-26b-a4b-it:free", raising=False)
    monkeypatch.setattr(llm_mod, "USE_LOCAL_LLM", False, raising=False)
    d = self_check._denetle_ucretsiz_kota()
    assert ":free" not in d["detay"] and "50" in d["detay"] and len(d["detay"]) < 130


def test_ekran_adlari_raydakiyle_ayni():
    from app.mesajlar import KATALOG
    for dil in ("tr", "en"):
        sz = sozluk(dil)
        assert KATALOG[dil]["ui.menu-anahtar"] == sz["hq.menu.anahtar"]
        assert KATALOG[dil]["ui.menu-ses"] == sz["hq.cat.ses"]
    for k in ("saglik.anahtar-cozum", "saglik.model-sec-cozum", "saglik.stt-model-cozum", "saglik.onar-model-elle"):
        assert "{ui_ayar}" not in KATALOG["tr"][k] and "{ui_anahtar}" not in KATALOG["tr"][k], k


def test_isik_ortak_sozlukte_anahtar_ve_saglik_ayni():
    ogeler = (FRONTEND / "css" / "ogeler.css").read_text(encoding="utf-8")
    for d in ("iyi", "uyari", "kritik", "olculemedi"):
        assert f".durum-isik.{d}" in ogeler
    uyari = re.search(r"\.durum-isik\.uyari \{([^}]*)\}", ogeler).group(1)
    assert "transparent" in uyari and "border" in uyari, "uyarı yeşilden yalnız renkle ayrılıyor"
    s = INTRO.read_text(encoding="utf-8")
    assert "sag-isik" not in s and "an-isik yok" not in s and "'yok':'ok'" not in s
    assert "durum-isik" in _saglik_blogu() and "an-isik durum-isik" in s


# ── ⑧ İlk kurulum = davet, arıza değil (geliştirici 09-28) · VC++ yalnız Windows ─────

@pytest.mark.asyncio
async def test_anahtar_hic_yoksa_kurulum_durumu_alarm_degil(monkeypatch):
    from app.services import llm as llm_mod
    monkeypatch.setattr(llm_mod, "_runtime_provider", "openrouter", raising=False)
    monkeypatch.setattr(llm_mod, "USE_LOCAL_LLM", False, raising=False)
    monkeypatch.setattr(llm_mod, "has_openrouter_key", lambda: False)
    d = self_check._denetle_llm_anahtar()
    assert d["durum"] == "kurulum" and d["ok"] is False and d["yonlendir"] == "key"
    iyi = lambda k: self_check._sonuc(k, k, True, self_check.BILGI)  # noqa: E731
    for ad in ("_denetle_veri_dizini", "_denetle_ucretsiz_kota", "_denetle_onnxruntime",
               "_denetle_stt", "_denetle_ffmpeg", "_denetle_disk"):
        monkeypatch.setattr(self_check, ad, lambda ad=ad: iyi(ad))

    async def _model():
        return iyi("llm_model")
    monkeypatch.setattr(self_check, "_denetle_llm_model", _model)
    r = await self_check.calistir()
    assert r["durum"] == "kurulum" and r["kurulum_sayisi"] == 1 and r["kritik_sayisi"] == 0
    assert r["ok"] is False, "kurulmamış Yuki cevap veremez"
    assert not any(k["kaynak"] == "kurulum" for k in error_log.son_kayitlar()), "ilk açılış hata günlüğüne yazıldı"


def test_kurulum_isigi_ortak_ve_uyaridan_bicimle_ayri():
    ogeler = (FRONTEND / "css" / "ogeler.css").read_text(encoding="utf-8")
    kur = re.search(r"\.durum-isik\.kurulum \{([^}]*)\}", ogeler).group(1)
    assert "--mor-ink" in kur and "radial-gradient" in kur, "kurulum ışığı uyarı halkasından biçimle ayrılmıyor"
    s = INTRO.read_text(encoding="utf-8")
    assert "an-isik durum-isik kurulum" in s, "ANAHTAR ilk kurulum başlığı hâlâ kırmızı"
    blok = _saglik_blogu()
    assert "kurulum:'saglik.hukum.kurulum'" in blok and "kurulum:'saglik.sayac.kurulum'" in blok


@pytest.mark.parametrize("sistem, vcpp", [("Linux", False), ("Darwin", False), ("Windows", True)])
def test_vcpp_cumlesi_yalniz_windowsta(monkeypatch, sistem, vcpp):
    monkeypatch.setattr(self_check.platform, "system", lambda: sistem)
    import app.services.stt as stt_mod
    monkeypatch.setattr(stt_mod, "stt_status", lambda: {"available": False, "model_present": False, "last_error": "x"})
    d = self_check._denetle_stt()
    assert ("Visual C++" in d["cozum"] or "VC++" in d["cozum"]) is vcpp, d["cozum"]
    assert bool(d["cozum_url"]) is vcpp
