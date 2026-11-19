"""Uyandırma kelimesi ("Hey Yuki") — filtre gerçekten çalışıyor mu (2026-08-05).

🔴 Bulunan tutarsızlık: arayüzdeki "👂 Her zaman dinle" düğmesi açılınca banner
*'"Hey Yuki" dinleniyor'* yazıyordu. Ama `WAKE_WORD_ENABLED` varsayılanı **false**
ve o durumda `check_wake_word()` **her zaman True** dönüyor → Yuki duyduğu HER
cümleye yanıt veriyor: yanındaki konuşmaya, televizyona, kendi mırıldanmana.
Kullanıcı "uyandırma kelimesiyle çalışıyor" sanıyordu.

İkinci hata aynı sınıftan: `check_wake_word` modül-tepesindeki sabitten okuyordu.
O sabit import anında donar → ⚙ AYAR'dan anahtarı açmak **hiçbir şey yapmıyordu**,
ancak yeniden başlatınca etkili oluyordu. (BYOK anahtarında da aynı desen vardı:
`llm_router` donmuş anahtarla istemci kuruyordu.)

Bu testler ağa çıkmaz, model yüklemez.
"""

import pytest

from app import config as cfg
from app.services import stt


@pytest.fixture
def kapali(monkeypatch):
    monkeypatch.setattr(cfg, "WAKE_WORD_ENABLED", False, raising=False)


@pytest.fixture
def acik(monkeypatch):
    monkeypatch.setattr(cfg, "WAKE_WORD_ENABLED", True, raising=False)
    monkeypatch.setattr(cfg, "WAKE_WORDS", ["yuki", "hey yuki", "ey yuki"], raising=False)


# ── Ayar CANLI okunuyor mu ───────────────────────────────────────────

def test_ayar_restart_beklemeden_etkili(monkeypatch):
    """🔴 Kök hata buydu: değer import anında donmuştu.

    Aynı süreç içinde ayarı açıp kapatmak davranışı DEĞİŞTİRMELİ.
    """
    monkeypatch.setattr(cfg, "WAKE_WORD_ENABLED", False, raising=False)
    assert stt.wake_word_acik() is False
    assert stt.check_wake_word("müziği durdur") is True      # filtre yok → geçer

    monkeypatch.setattr(cfg, "WAKE_WORD_ENABLED", True, raising=False)
    assert stt.wake_word_acik() is True
    assert stt.check_wake_word("müziği durdur") is False     # artık eleniyor


# ── Filtre KAPALI: her şey geçer (varsayılan davranış korunuyor) ─────

def test_kapaliyken_her_cumle_geciyor(kapali):
    for c in ["müziği durdur", "yuki naber", "", "televizyondan gelen laf"]:
        assert stt.check_wake_word(c) is True
    assert stt.strip_wake_word("hey yuki müziği durdur") == "hey yuki müziği durdur"


# ── Filtre AÇIK: eleme ve temizleme ──────────────────────────────────

@pytest.mark.parametrize("cumle", [
    "Hey Yuki müziği durdur",
    "hey yuki, saat kaç",
    "Yuki dolar kaç TL",
    "ey Yuki not al",
    "YUKI UYAN",                       # büyük harf
    "Yuki'ye söyle hava nasıl",        # TR eki, kesme işaretli
    "yukiye söyle hava nasıl",         # ses tanıma kesme işaretini düşürebilir
])
def test_acikken_uyandirma_kelimesi_geciyor(acik, cumle):
    assert stt.check_wake_word(cumle) is True


@pytest.mark.parametrize("cumle", [
    "müziği durdur",
    "saat kaç",
    "yarın hava nasıl olacak",
    "yukarıdaki dosyayı aç",           # "yukarı" wake-word'e benzemez
    "büyük bir sorun var",
    "",
])
def test_acikken_uyandirma_kelimesiz_cumle_eleniyor(acik, cumle):
    assert stt.check_wake_word(cumle) is False


@pytest.mark.parametrize("girdi,beklenen", [
    ("Hey Yuki müziği durdur", "müziği durdur"),
    ("hey yuki, saat kaç", "saat kaç"),
    ("Yuki not al: süt", "not al: süt"),
    ("ey Yuki hava nasıl", "hava nasıl"),
])
def test_uyandirma_kelimesi_metinden_temizleniyor(acik, girdi, beklenen):
    assert stt.strip_wake_word(girdi) == beklenen


def test_yalniz_uyandirma_kelimesi_varsa_metin_bosalmiyor(acik):
    """"Yuki" deyip susmak → LLM'e boş mesaj gitmemeli; ham metin korunur."""
    assert stt.strip_wake_word("Yuki") == "Yuki"


# ── Uç: banner gerçeği buradan öğreniyor ─────────────────────────────

@pytest.mark.asyncio
async def test_wake_word_ucu_gercek_durumu_donuyor(monkeypatch):
    from app.api import settings_api

    class _İstek:
        class _C:
            host = "127.0.0.1"
        client = _C()
        headers: dict = {}
        scope: dict = {"type": "http"}

    monkeypatch.setattr(cfg, "WAKE_WORD_ENABLED", False, raising=False)
    d = await settings_api.get_wake_word.__wrapped__(_İstek())
    assert d["enabled"] is False and "hey yuki" in d["words"]

    monkeypatch.setattr(cfg, "WAKE_WORD_ENABLED", True, raising=False)
    d = await settings_api.get_wake_word.__wrapped__(_İstek())
    assert d["enabled"] is True


@pytest.mark.asyncio
async def test_ayar_yazinca_restart_istenmiyor(monkeypatch, tmp_path):
    """Banner'daki seçim düğmesi bu ucu çağırıyor; "yeniden başlat" demek
    özelliği o an kullanılamaz kılardı."""
    from app.api import settings_api
    from app import config_manager

    class _İstek:
        class _C:
            host = "127.0.0.1"
        client = _C()
        headers: dict = {}
        scope: dict = {"type": "http"}

    monkeypatch.setattr(config_manager, "set_value", lambda k, v: (True, ""))
    monkeypatch.setattr(config_manager, "get", lambda k: True)

    d = await settings_api.set_setting.__wrapped__(
        _İstek(), "WAKE_WORD_ENABLED", settings_api.SettingUpdate(value=True)
    )
    assert d["ok"] is True and d["needs_restart"] is False
