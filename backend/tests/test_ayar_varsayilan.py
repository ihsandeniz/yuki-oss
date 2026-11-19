"""HQ › Ayarlar — boş kutu, varsayılana dön, sıfırlama önizlemesi, kullanılamayan ayar (2026-09-27).

Kişisel AliceAi ed907af'ın ürün karşılığı. Üründe ölçülen kusurlar:
  ① `LLM_MODEL_FAST` kutusu boş kaydedilince `""` kalıcı kayıt oluyordu; yeniden başlatınca
     varsayılan `openai/gpt-4o-mini` yerine BOŞ model kalıyordu (izole 8001'de ölçüldü).
  ② "Varsayılana dön" ucu yoktu — tek yol tüm ayarları sıfırlamaktı.
  ③ Sıfırlama neyi değiştireceğini söylemiyordu.
  ④ Ultra ayarı yalnız arayüzde gizleniyordu; uç Free'de de kaydediyordu.
Ayar dosyası conftest'te geçici dizine yönlendirili (canli_dosyaya_yazmasin).
"""
import json

import pytest
from starlette.testclient import TestClient

from app import config as cfg
from app import config_manager
from app.main import app

c = TestClient(app)


@pytest.fixture()
def model_geri():
    """Uç bellekteki global'i de yazıyor — test sonunda eski değer geri."""
    eski = cfg.LLM_MODEL_FAST
    yield
    cfg.LLM_MODEL_FAST = eski


def _dosya() -> dict:
    p = config_manager.CONFIG_USER_PATH
    return json.loads(p.read_text(encoding="utf-8")) if p.exists() else {}


def test_bos_kutu_dolu_varsayilani_ezmez(model_geri):
    assert cfg.PANEL_ONCESI.get("LLM_MODEL_FAST"), "ön koşul: varsayılan dolu"
    r = c.post("/api/settings/LLM_MODEL_FAST", json={"value": "   "})
    assert r.status_code == 400
    assert "LLM_MODEL_FAST" not in _dosya(), "boş değer diske yazılmamalı"


def test_varsayilana_don_kaydi_siler_ve_degeri_geri_ceker(model_geri):
    assert c.post("/api/settings/LLM_MODEL_FAST", json={"value": "x/deneme"}).status_code == 200
    assert _dosya()["LLM_MODEL_FAST"] == "x/deneme" and cfg.LLM_MODEL_FAST == "x/deneme"
    r = c.delete("/api/settings/LLM_MODEL_FAST")
    assert r.status_code == 200 and r.json()["value"] == cfg.PANEL_ONCESI["LLM_MODEL_FAST"]
    assert "LLM_MODEL_FAST" not in _dosya()
    assert cfg.LLM_MODEL_FAST == cfg.PANEL_ONCESI["LLM_MODEL_FAST"]
    assert c.delete("/api/settings/LLM_MODEL_FAST").status_code == 200, "kayıt yokken de başarılı"
    assert c.delete("/api/settings/OLMAYAN_ANAHTAR").status_code == 400


def test_sifirlama_onizlemesi_simdi_ve_sonrayi_soyler(model_geri):
    c.post("/api/settings/LLM_MODEL_FAST", json={"value": "x/deneme"})
    d = c.get("/api/settings/reset-preview").json()
    kalem = next(k for k in d["degisen"] if k["key"] == "LLM_MODEL_FAST")
    assert kalem["simdi"] == "x/deneme" and kalem["sonra"] == cfg.PANEL_ONCESI["LLM_MODEL_FAST"]
    c.delete("/api/settings/LLM_MODEL_FAST")
    assert not [k for k in c.get("/api/settings/reset-preview").json()["degisen"] if k["key"] == "LLM_MODEL_FAST"]


def test_sifirlama_dili_ve_karakter_seslerini_KORUR():
    """🔴 Önizleme "dil korunur" diyordu, `reset()` dosyanın tamamını siliyordu → yeniden
    başlatınca dil `.env`'e dönüyor, karakter sesi seçimleri kayboluyordu."""
    config_manager.set_value("ASSISTANT_LANGUAGE", "en")
    config_manager.set_value("PERSONA_VOICES", '{"yuki": "tr-TR-EmelNeural"}')
    config_manager.set_value("VAD_THRESHOLD", 0.05)
    assert config_manager.reset()
    kalan = _dosya()
    assert kalan.get("ASSISTANT_LANGUAGE") == "en"
    assert "PERSONA_VOICES" in kalan
    assert "VAD_THRESHOLD" not in kalan, "sıfırlama asıl ayarı silmedi"
    config_manager.reset()
    config_manager.sil("ASSISTANT_LANGUAGE"); config_manager.sil("PERSONA_VOICES")


def test_onizleme_korunanlari_LISTELEMEZ():
    config_manager.set_value("PERSONA_VOICES", '{"yuki": "tr-TR-EmelNeural"}')
    try:
        d = c.get("/api/settings/reset-preview").json()
        assert all(k["key"] not in config_manager.SIFIRLAMADA_KORUNAN for k in d["degisen"])
    finally:
        config_manager.sil("PERSONA_VOICES")


def test_liste_varsayilan_ve_degisti_tasir(model_geri):
    """Satır "SEN DEĞİŞTİRDİN · varsayılan: X" gösterir; varsayılanla AYNI kayıt 'değişti' sayılmaz."""
    vars_ = cfg.PANEL_ONCESI["LLM_MODEL_FAST"]
    c.post("/api/settings/LLM_MODEL_FAST", json={"value": "x/deneme"})
    try:
        d = c.get("/api/settings").json()
        assert d["varsayilan"]["LLM_MODEL_FAST"] == vars_
        assert "LLM_MODEL_FAST" in d["degisti"]
        c.post("/api/settings/LLM_MODEL_FAST", json={"value": vars_})   # geri aldı
        assert "LLM_MODEL_FAST" not in c.get("/api/settings").json()["degisti"]
    finally:
        c.delete("/api/settings/LLM_MODEL_FAST")
