"""Kurulum sihirbazı (self_check) + hata günlüğü (error_log).

🔴 2026-08-01: ürün temiz Windows'ta çalışmadı ve her başarısızlık sessizdi. Bu iki
modül "ürün kendi ortamını denetlesin ve hatasını kaydetsin" için eklendi.
"""

import json

import pytest

from app.services import error_log, self_check


@pytest.fixture(autouse=True)
def _izole_gunluk(tmp_path, monkeypatch):
    """Günlüğü geçici dizine al — gerçek kullanıcı günlüğüne dokunma."""
    monkeypatch.setattr(error_log, "_dosya", lambda: tmp_path / "hata-gunlugu.jsonl")
    yield


# ── Hata günlüğü ────────────────────────────────────────────────────────────

def test_kayit_dort_alani_da_tutuyor():
    error_log.kaydet("ses", "stt_yuklenemedi", "ctranslate2.dll bulunamadı")
    (k,) = error_log.son_kayitlar()
    assert k["kaynak"] == "ses"
    assert k["neden"] == "stt_yuklenemedi"
    assert "ctranslate2" in k["ayrinti"]
    assert k["zaman"], "zaman damgası zorunlu — 'ne zaman oldu' sorusu bunun için var"


def test_en_yeni_kayit_basta():
    error_log.kaydet("a", "birinci")
    error_log.kaydet("b", "ikinci")
    kayitlar = error_log.son_kayitlar()
    assert kayitlar[0]["neden"] == "ikinci"


def test_anahtar_maskeleniyor():
    """Günlük paylaşılacak — kullanıcının anahtarı içinde gitmemeli."""
    error_log.kaydet("llm", "401", "Authorization: Bearer sk-or-v1-abcdef0123456789abcdef0123456789")
    metin = error_log.disari_aktar()
    assert "sk-or-v1-abcdef0123456789abcdef0123456789" not in metin


def test_gunluk_sinirsiz_buyumuyor(monkeypatch):
    monkeypatch.setattr(error_log, "MAX_KAYIT", 20)
    monkeypatch.setattr(error_log, "_KIRP_PAYI", 5)
    for i in range(60):
        error_log.kaydet("test", f"kayit-{i}")
    assert len(error_log.son_kayitlar(1000)) <= 20


def test_disari_aktarma_sistem_bilgisi_iceriyor():
    error_log.kaydet("ses", "stt_yuklenemedi", "detay")
    metin = error_log.disari_aktar()
    assert "Yuki hata günlüğü" in metin
    assert "Sürüm" in metin and "Sistem" in metin
    assert "stt_yuklenemedi" in metin


def test_bos_gunluk_cokmez():
    assert "Kayıtlı hata yok" in error_log.disari_aktar()
    assert error_log.son_kayitlar() == []
    assert error_log.ozet()["toplam"] == 0


def test_gunluk_yazilamazsa_urun_durmuyor(monkeypatch):
    """Günlük yazamamak ASLA çağıranı patlatmamalı."""
    monkeypatch.setattr(error_log, "_dosya", lambda: (_ for _ in ()).throw(OSError("disk dolu")))
    error_log.kaydet("test", "olmalı-sessiz")  # exception fırlatmamalı


def test_handler_warning_yakaliyor():
    import logging
    error_log.kur()
    logging.getLogger("app.services.deneme").warning("bir şey ters gitti")
    kayitlar = error_log.son_kayitlar()
    assert any("ters gitti" in k["ayrinti"] for k in kayitlar)


def test_handler_kendini_loglamiyor():
    """Sonsuz döngü koruması."""
    import logging
    error_log.kur()
    logging.getLogger("app.services.error_log").warning("kendi hatam")
    assert not any("kendi hatam" in k["ayrinti"] for k in error_log.son_kayitlar())


def test_temizleme_calisiyor():
    error_log.kaydet("a", "b")
    assert error_log.temizle_gunluk() >= 1
    assert error_log.son_kayitlar() == []


# ── Kurulum denetimi ────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_denetim_tum_alanlari_donduruyor():
    r = await self_check.calistir()
    assert "denetimler" in r and len(r["denetimler"]) >= 6
    for d in r["denetimler"]:
        for alan in ("kimlik", "baslik", "ok", "seviye", "detay"):
            assert alan in d, f"eksik alan: {alan}"


@pytest.mark.asyncio
async def test_basarisiz_denetim_cozum_cumlesi_tasiyor():
    """'Hata kodu' yetmez — kullanıcı ne yapacağını okuyabilmeli."""
    r = await self_check.calistir()
    for d in r["denetimler"]:
        if not d["ok"]:
            assert d["cozum"].strip(), f"{d['kimlik']} çözüm metni taşımıyor"


@pytest.mark.asyncio
async def test_kalkmis_model_kritik_ve_otomatik_onarilabilir(monkeypatch):
    """07-31 senaryosu: seçili model sağlayıcıdan kalkmış."""
    from app.services import llm as llm_mod
    monkeypatch.setattr(llm_mod, "_runtime_model", "olmayan/model:free")

    async def _sahte_gruplar():
        return [{"title": "Ücretsiz — doğrulandı",
                 "options": [{"id": "google/gemma-4-26b-a4b-it:free", "label": "x"}]}]

    monkeypatch.setattr("app.api.llm_config_api._fetch_live_groups", _sahte_gruplar)

    d = await self_check._denetle_llm_model()
    assert d["ok"] is False
    assert d["seviye"] == self_check.KRITIK
    assert d["otomatik_duzeltilebilir"] is True


@pytest.mark.asyncio
async def test_onarim_modeli_calisan_bir_modele_geciriyor(monkeypatch):
    from app.services import llm as llm_mod
    monkeypatch.setattr(llm_mod, "_runtime_model", "olmayan/model:free")

    async def _sahte_gruplar():
        return [{"title": "Ücretsiz — doğrulandı",
                 "options": [{"id": "google/gemma-4-26b-a4b-it:free", "label": "x"}]}]

    monkeypatch.setattr("app.api.llm_config_api._fetch_live_groups", _sahte_gruplar)
    monkeypatch.setattr("app.api.llm_config_api._persist_env", lambda *a: None)

    r = await self_check.onar("llm_model")
    assert r["ok"] is True
    assert r["model"] == "google/gemma-4-26b-a4b-it:free"
    assert llm_mod.get_runtime_config()["model"] == "google/gemma-4-26b-a4b-it:free"


@pytest.mark.asyncio
async def test_bilinmeyen_onarim_reddediliyor():
    r = await self_check.onar("sistem_paketi_kur")
    assert r["ok"] is False


@pytest.mark.asyncio
async def test_kritik_bulgu_gunluge_dusuyor(monkeypatch):
    """Destek istendiğinde geçmiş elimizde olsun."""
    monkeypatch.setattr(self_check, "_denetle_llm_anahtar",
                        lambda: self_check._sonuc("llm_anahtar", "LLM anahtarı", False,
                                                  self_check.KRITIK, "anahtar yok", "gir"))
    await self_check.calistir()
    assert any(k["kaynak"] == "kurulum" for k in error_log.son_kayitlar())


# ── API uçları ──────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_self_check_ucu(client):
    r = await client.get("/api/self-check")
    assert r.status_code == 200
    assert "denetimler" in r.json()


@pytest.mark.asyncio
async def test_hata_uclari(client):
    error_log.kaydet("ses", "test_kaydi", "ayrıntı")
    r = await client.get("/api/errors/recent")
    assert r.status_code == 200
    assert "kayitlar" in r.json()

    r2 = await client.get("/api/errors/export")
    assert r2.status_code == 200
    assert "Yuki hata günlüğü" in r2.text


@pytest.mark.asyncio
async def test_onarim_ucu_bilinmeyeni_reddediyor(client):
    r = await client.post("/api/self-check/repair", json={"kimlik": "olmayan"})
    assert r.status_code == 200
    assert r.json()["ok"] is False
