"""Ayar paneli, bu kurulumda KARŞILIĞI OLMAYAN anahtarı göstermemeli.

🔴 2026-08-12 ölçümü (canlı Playwright, üç kademe): ayar panelinde 34 ayar
çiziliyordu ve bunların 7'si satılan pakette fiziksel olarak bulunmayan
özellikleri açıp kapatıyordu — Fish Speech (ayrı sunucu ister), yerel TTS
(açık kaynak sürümden çıkarıldı), göz takibi (`mediapipe` yok). Ayrıca
`DBUS_ENABLED` Windows'ta da gösteriliyordu.

Müşteri açısından sonucu tek satırla: **anahtarı açıyor, hiçbir şey olmuyor,
ürünü bozuk sanıyor.** `modes/gfx.js`'in "ya uygula, ya menüye koyma" kuralının
ayarlar panelindeki ihlali — orada ULTRA kademesi tam bu sebeple menüye
konmamıştı.

Kural: anahtar şemadan **silinmez** (kullanıcının `config.user.json` değeri
bozulmasın, paket içeriği değişirse ayar kendiliğinden dönsün), `available`
alanıyla işaretlenir; frontend `available===false` olanı çizmez.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

from app.api import settings_api

FRONTEND = Path(__file__).resolve().parents[2] / "frontend"

# Bu kurulumda karşılığı olmayan anahtarlar. 2026-08-12'de lean venv'de
# tek tek `find_spec` ile ölçüldü: TTS YOK · torch YOK · mediapipe YOK ·
# (cv2 VAR, ormsgpack VAR — bu ikisi tek başına yetmiyor).
OLU_ANAHTARLAR = {
    "USE_FISH_TTS",     # ayrı api_server ister, pakette gelmiyor
    "EYE_TRACKING_ENABLED",   # mediapipe
    "EYE_TRACKING_FPS",
    "EYE_TRACKING_CAMERA",
}


def _sema_sozluk() -> dict[str, dict]:
    return {s["key"]: s for s in settings_api._gorunur_sema()}


def test_her_ayarda_available_damgasi_var():
    """Damgasız ayar = frontend'in körlemesine çizdiği ayar."""
    for s in settings_api._gorunur_sema():
        assert "available" in s, f"{s['key']}: available damgası yok"


def test_olu_anahtarlar_bu_kurulumda_kapali():
    sema = _sema_sozluk()
    acik_kalanlar = [k for k in OLU_ANAHTARLAR if sema[k]["available"]]
    assert not acik_kalanlar, (
        f"bu kurulumda çalışmayan ama ayar panelinde görünen anahtar(lar): "
        f"{acik_kalanlar}"
    )


def test_kapali_ayar_sebebini_soyluyor():
    """'Yok' demek yetmez — neden yok, müşteriye yazılı söylenir."""
    for s in settings_api._gorunur_sema():
        if not s["available"]:
            sebep = s.get("unavailable_reason", "")
            assert sebep and len(sebep) > 10, f"{s['key']}: sebep yazılmamış"


def test_calisan_ayarlar_kapatilmadi():
    """Aşırı temizlik regresyonu: Edge TTS / ElevenLabs / mikrofon açık kalmalı.

    ElevenLabs özellikle önemli — R6 §5.1'de ses klonlamanın yerel yerine
    **BYOK bulut** yoluyla verilmesi kararlaştırıldı; o anahtar kaybolursa
    kararın kendisi uygulanamaz hale gelir.
    """
    sema = _sema_sozluk()
    for k in ("USE_ELEVENLABS_TTS", "EDGE_VOICE_RATE", "WAKE_WORD_ENABLED",
              "WHISPER_MODEL", "BROWSER_ENABLED", "MEMORY_SEARCH_LIMIT"):
        assert sema[k]["available"], f"{k} yanlışlıkla gizlendi"


def test_gizlenen_ayarin_degeri_hala_donuyor():
    """Gizlemek ≠ silmek. Değer `values` içinde kalır, kullanıcı ayarı bozulmaz."""
    degerler = settings_api._current_values()
    for k in OLU_ANAHTARLAR:
        assert k in degerler, f"{k} values'tan düşmüş — kullanıcı değeri kaybolur"


def test_needs_alani_disari_sizmiyor():
    """`needs` iç ölçüt; frontend'e gitmesi gereksiz yüzey."""
    for s in settings_api._gorunur_sema():
        assert "needs" not in s, f"{s['key']}: iç alan `needs` sızıyor"


def test_platform_olcutu_isletim_sistemine_bakiyor(monkeypatch):
    """DBUS Linux'ta açık, Windows'ta kapalı. (Ölçüt modül DEĞİL — `dbus_next`
    pakette VAR; Windows'ta bağlanacak veri yolu yok.)"""
    kayit = next(s for s in settings_api.SETTINGS_SCHEMA
                 if s["key"] == "DBUS_ENABLED")

    monkeypatch.setattr(settings_api.platform, "system", lambda: "Linux")
    assert settings_api._uygunluk(kayit)[0] is True

    monkeypatch.setattr(settings_api.platform, "system", lambda: "Windows")
    uygun, sebep = settings_api._uygunluk(kayit)
    assert uygun is False and "Linux" in sebep


def test_modul_gelirse_ayar_kendiliginden_geri_geliyor(monkeypatch):
    """Paket içeriği değişirse kapı kendini açmalı — sabit gizleme listesi yok."""
    kayit = next(s for s in settings_api.SETTINGS_SCHEMA
                 if s["key"] == "EYE_TRACKING_ENABLED")
    assert settings_api._uygunluk(kayit)[0] is False        # bugünkü gerçek

    monkeypatch.setattr(settings_api, "_modul_var", lambda ad: True)
    assert settings_api._uygunluk(kayit)[0] is True


def test_paketlenen_servis_ayari_geri_getirir(monkeypatch):
    kayit = next(s for s in settings_api.SETTINGS_SCHEMA
                 if s["key"] == "USE_FISH_TTS")
    assert settings_api._uygunluk(kayit)[0] is False

    monkeypatch.setattr(settings_api, "PAKETLI_SERVISLER", frozenset({"Fish Speech"}))
    assert settings_api._uygunluk(kayit)[0] is True


def test_modul_denetimi_tek_basina_fishi_acmiyor(monkeypatch):
    """🔑 `ormsgpack` pakette VAR ama Fish motoru değil.

    Bu test, ölçütü "modül var mı"ya çevirme eğilimine karşı duruyor: öyle
    yapılsaydı Fish `available:true` görünür, müşteri açar, hiçbir şey olmazdı —
    yani düzeltmek istediğimiz kusurun aynısı.
    """
    monkeypatch.setattr(settings_api, "_modul_var", lambda ad: True)
    kayit = next(s for s in settings_api.SETTINGS_SCHEMA
                 if s["key"] == "USE_FISH_TTS")
    assert settings_api._uygunluk(kayit)[0] is False


@pytest.mark.asyncio
async def test_api_yaniti_damgayi_tasiyor(client):
    r = await client.get("/api/settings")
    assert r.status_code == 200
    sema = {s["key"]: s for s in r.json()["schema"]}
    assert sema["EYE_TRACKING_ENABLED"]["available"] is False
    assert sema["USE_ELEVENLABS_TTS"]["available"] is True


def test_frontend_available_filtresini_uyguluyor():
    """🔴 Backend damgalıyor ama arayüz bakmıyorsa hiçbir şey değişmez.

    Bu, 2026-08-09'un karakter kilidi dersinin birebir aynısı: kapı vardı,
    arayüz kapıya bakmıyordu. Damganın üretilmesi ile kullanılması AYRI
    ölçülür.
    """
    kaynak = (FRONTEND / "js" / "intro-sequences.js").read_text(encoding="utf-8")
    satir = re.search(r"var rows\s*=\s*_schema\.filter\([^;]+;", kaynak)
    assert satir, "ayar satırlarını süzen filtre bulunamadı (yeniden mi adlandırıldı?)"
    assert "available" in satir.group(0), (
        "frontend `available` damgasına bakmıyor — gizlenen ayar yine çizilir"
    )
    # `!== false` şart: alan yoksa (eski backend + yeni frontend, delta'da olur)
    # ayar GÖSTERİLMELİ; `=== true` yazılsaydı eski backend'de panel boşalırdı.
    assert "!==false" in satir.group(0).replace(" ", ""), (
        "filtre `available!==false` olmalı — `===true` eski backend'de tüm ayarları siler"
    )


# ── Kademe yok (açık kaynak): eski "Ultra sürümde açılır" ayarları herkese açık ──
@pytest.mark.parametrize("anahtar", ["COUNCIL_MAX_TASKS", "WORKER_MAX_STEPS"])
def test_eski_ultra_ayari_kullanilabilir(anahtar):
    from app.api import settings_api
    sema = {s["key"]: s for s in settings_api._gorunur_sema()}
    assert sema[anahtar]["available"] is True, f"{anahtar} hâlâ kilitli görünüyor"


def test_ayar_anahtarlari_yazilabilir_listede(monkeypatch):
    """Şemada olup `ALLOWED_KEYS`te olmayan ayar, panelde görünür ama KAYDEDİLEMEZ."""
    from app import config_manager
    from app.api.settings_api import SETTINGS_SCHEMA
    eksik = [s["key"] for s in SETTINGS_SCHEMA if s["key"] not in config_manager.ALLOWED_KEYS]
    assert not eksik, f"panelde görünen ama kaydedilemeyen ayar: {eksik}"
