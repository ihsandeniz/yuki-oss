"""FAZ 0 — global/i18n taramasının yan ürünü olarak bulunan CANLI arızalar.

Bunlar "İngilizce'ye hazırlık" değil; **bugün Türkçe üründe yanlış çalışan** şeyler.
Kaynak ölçüm: 2026-09-18 i18n taraması § 4

Kapsam (backend):
  A1 — sabah brifingi Türkçe cümlenin içine İngilizce ay adı basıyor (`%B` + setlocale yok)
  A4 — kullanıcının liste adı `.title()` ile bozuluyor ("işler" → "Işler")
  A5 — bütçe rakamı ABD biçiminde ("₺42,500"), frontend aynı sayıyı "₺42.500" gösteriyor
  A7 — persona sesi dil seçimini eziyor → dil `ja` iken ses hâlâ `tr-TR-*`
  A9 — dil tercihi kalıcı değil, backend restart'ında `tr`'ye dönüyor

⚠️ Her test önce KIRMIZI yanacak şekilde yazıldı (üreten=ölçen tuzağı).
"""
from __future__ import annotations

import json
import pathlib
import re
from datetime import date

import pytest


# --------------------------------------------------------------------------- #
# A1 — tarih metni: ay adı dile bağlı olmalı, `%B` locale'e teslim edilmemeli
# --------------------------------------------------------------------------- #

# ⚠️ Kelime sınırı ŞART: İngilizce "May", Türkçe "Mayıs"ın içinde geçiyor. Düz
# alt-dize araması 5. ayda yanlış alarm verir (bu test ilk yazıldığında verdi).
# Python `re`'de `\b` Unicode-duyarlıdır → "Mayıs" içindeki "May"den sonra 'ı'
# kelime karakteri olduğu için sınır oluşmaz ve eşleşme olmaz.
_INGILIZCE_AY_DESENI = re.compile(
    r"\b(January|February|March|April|May|June|July|"
    r"August|September|October|November|December)\b"
)


def _ingilizce_ay(metin: str) -> str | None:
    m = _INGILIZCE_AY_DESENI.search(metin)
    return m.group(0) if m else None


def test_a1_uzun_tarih_turkce_ay_adi_verir():
    from app.services.bicim import uzun_tarih

    metin = uzun_tarih(date(2026, 9, 18), "tr")
    assert "Eylül" in metin, f"Türkçe ay adı yok: {metin!r}"
    assert _ingilizce_ay(metin) is None, \
        f"Türkçe metnin içinde İngilizce ay adı: {metin!r}"


def test_a1_uzun_tarih_12_ayin_hepsinde_turkce():
    """Tek ay doğru olup diğerleri yanlış olabilir — 12'sini de ölç."""
    from app.services.bicim import AY_ADLARI, uzun_tarih

    for ay in range(1, 13):
        metin = uzun_tarih(date(2026, ay, 15), "tr")
        assert _ingilizce_ay(metin) is None, \
            f"{ay}. ayda İngilizce ad sızdı: {metin!r}"
        assert AY_ADLARI["tr"][ay] in metin, f"{ay}. ayın TR adı yok: {metin!r}"


def test_a1_mayis_yanlis_alarm_uretmez():
    """Test aracının kendisinin bekçisi — 'May' ⊂ 'Mayıs' tuzağı geri gelmesin."""
    assert _ingilizce_ay("15 Mayıs 2026") is None
    assert _ingilizce_ay("15 May 2026") == "May"


def test_a1_sabah_brifingi_ingilizce_ay_adi_icermez():
    """Asıl arıza yeri: scheduler.py sabah brifingi. Canlı metni üretip ölç."""
    from app.services import scheduler

    metin = scheduler._brifing_tarih_metni(date(2026, 9, 18))
    assert "Eylül" in metin and "Cuma" in metin, f"beklenen TR tarih yok: {metin!r}"
    assert _ingilizce_ay(metin) is None, \
        f"sabah brifingi İngilizce ay adı basıyor: {metin!r}"


def test_a1_gun_adi_tablosu_tek_kaynaktan():
    """scheduler kendi `_WEEKDAYS` kopyasını tutmamalı — 6 kopya sorunu büyümesin."""
    from app.services import scheduler

    assert not hasattr(scheduler, "_WEEKDAYS"), \
        "scheduler hâlâ kendi gün adı kopyasını taşıyor; bicim.GUN_ADLARI kullanmalı"


# --------------------------------------------------------------------------- #
# A4 — Türkçe başlık büyütme: "işler" → "İşler" (Python .title() "Işler" verir)
# --------------------------------------------------------------------------- #

@pytest.mark.parametrize(
    "girdi, beklenen",
    [
        ("işler", "İşler"),
        ("ışık", "Işık"),
        ("izmir gezisi", "İzmir Gezisi"),
        ("ıspanak listesi", "Ispanak Listesi"),
        ("İŞLER", "İşler"),
        ("gelen kutusu", "Gelen Kutusu"),
    ],
)
def test_a4_baslik_turkce_i_harfini_bozmaz(girdi, beklenen):
    from app.services.bicim import baslik

    assert baslik(girdi, "tr") == beklenen


def test_a4_todo_store_liste_adini_bozmadan_yazar(tmp_path, monkeypatch):
    """Asıl arıza yeri: `_migrate_legacy` liste adını diske KALICI yazıyor.

    ⚠️ Bu test önce kaynak metninde `.title()` arıyordu ve düzeltmeyi AÇIKLAYAN
    yorum satırına takılıp yanlış alarm verdi. Kaynak-grep kırılgandır — testi
    davranışa çevirdim: göç gerçekten koşuyor, yazılan ad okunuyor.
    """
    from app.services import todo_store

    eski = tmp_path / "todos.json"
    eski.write_text(
        json.dumps([{"list_name": "işler", "title": "fatura öde"}], ensure_ascii=False),
        encoding="utf-8",
    )
    monkeypatch.setattr(todo_store, "_LEGACY_FILE", eski)

    db = {"lists": [], "tasks": [], "subtasks": [], "deps": [], "budget": [], "trash": []}
    todo_store._migrate_legacy(db)

    adlar = [l["name"] for l in db["lists"]]
    assert "İşler" in adlar, f"liste adı Türkçe'ye uygun büyütülmedi: {adlar}"
    assert "Işler" not in adlar, f"Python .title() bozması sürüyor: {adlar}"


# --------------------------------------------------------------------------- #
# A5 — sayı/para biçimi: TR'de binlik ayracı NOKTA ("₺42.500")
# --------------------------------------------------------------------------- #

@pytest.mark.parametrize(
    "deger, lang, beklenen",
    [
        (42500, "tr", "42.500"),
        (1500, "tr", "1.500"),
        (999, "tr", "999"),
        (0, "tr", "0"),
        (-42500, "tr", "-42.500"),
        (1234567, "tr", "1.234.567"),
        (42500, "ja", "42,500"),      # JA/EN konvansiyonu: virgül
    ],
)
def test_a5_sayi_bicimi_dile_gore(deger, lang, beklenen):
    from app.services.bicim import sayi

    assert sayi(deger, lang) == beklenen


def test_a5_para_simgesi_ve_ayrac():
    from app.services.bicim import para

    assert para(42500, "tr") == "₺42.500"


async def test_a5_butce_ozeti_abd_bicimi_basmaz(monkeypatch):
    """Asıl arıza yeri: todo_tools bütçe özeti — LLM'e ve kullanıcıya giden metin.

    Aynı rakamı frontend (`planner.html:1161`, `toLocaleString('tr-TR')`) zaten
    `₺42.500` gösteriyordu; backend `₺42,500` diyordu. İki yüzey, iki biçim.
    """
    from app.services import todo_store
    from app.services.tools import todo_tools

    monkeypatch.setattr(todo_tools, "_pool", lambda: _none())
    monkeypatch.setattr(
        todo_store, "get_budget_summary",
        lambda month: {
            "income": 42500, "expense": 1500, "balance": 41000,
            "count": 2, "top_categories": [{"category": "market", "total": 1500}],
        },
    )

    metin = await todo_tools.get_budget_summary("2026-09")
    assert "₺42.500" in metin, f"TR binlik ayracı yok: {metin!r}"
    assert "₺1.500" in metin, f"kategori satırı ABD biçiminde: {metin!r}"
    assert "42,500" not in metin, f"ABD binlik ayracı sürüyor: {metin!r}"


async def _none():
    return None


# --------------------------------------------------------------------------- #
# A7 — dil ↔ ses bağı: persona sesi dil seçimini EZMEMELİ
# --------------------------------------------------------------------------- #

def test_a7_personalar_sabit_ses_kimligi_tasimaz():
    """5 personanın 5'inde de `edge_voice: tr-TR-EmelNeural` sabitti; dili eziyordu.

    Personalar ses *kimliğini* değil ses *üslubunu* (rate/pitch) taşımalı.
    """
    from app.services.personas import PERSONAS

    sabitler = {k: v["edge_voice"] for k, v in PERSONAS.items() if v.get("edge_voice")}
    assert not sabitler, f"persona sabit ses kimliği taşıyor (dili ezer): {sabitler}"


def test_a7_dil_degisince_ses_de_degisir():
    """Kanıt okuma değil ÇALIŞTIRMA ile: _edge_voice_params() gerçekten ne döndürüyor."""
    from app.config import set_language, get_language
    from app.services.tts import _edge_voice_params

    onceki = get_language()
    try:
        set_language("tr")
        tr_ses, _, _ = _edge_voice_params()
        set_language("ja")
        ja_ses, _, _ = _edge_voice_params()
    finally:
        set_language(onceki)

    assert tr_ses.startswith("tr-"), f"tr dilinde ses TR değil: {tr_ses}"
    assert ja_ses.startswith("ja-"), \
        f"dil 'ja' ama ses hâlâ '{ja_ses}' — persona ezmesi sürüyor"


def test_a7_persona_uslubu_korunuyor(test_ekibi):
    """Ses kimliği dilden gelsin ama personanın rate/pitch farkı KAYBOLMASIN."""
    from app.config import set_language, get_language
    from app.services import personas
    from app.services.tts import _edge_voice_params

    onceki_dil, onceki_p = get_language(), personas.get_persona()
    try:
        set_language("tr")
        personas.set_persona("yuki")
        _, yuki_rate, yuki_pitch = _edge_voice_params()
        personas.set_persona("uzman_a")   # test personası: edge_rate +3, edge_pitch +2
        _, diger_rate, diger_pitch = _edge_voice_params()
    finally:
        set_language(onceki_dil)
        personas.set_persona(onceki_p)

    assert (yuki_rate, yuki_pitch) != (diger_rate, diger_pitch), \
        "persona üslubu (rate/pitch) kayboldu — ses kimliğiyle birlikte silinmiş"


# --------------------------------------------------------------------------- #
# A9 — dil tercihi kalıcılığı
# --------------------------------------------------------------------------- #

def test_a9_assistant_language_yazilabilir_ayar_listesinde():
    from app import config_manager

    assert "ASSISTANT_LANGUAGE" in config_manager.ALLOWED_KEYS, \
        "ASSISTANT_LANGUAGE ALLOWED_KEYS'te yok → config.user.json'a yazılamaz"
    assert config_manager.ALLOWED_KEYS["ASSISTANT_LANGUAGE"] is str


def test_a9_set_language_diske_yazar(tmp_path, monkeypatch):
    """Dil değişimi restart'ı aşmalı — bugün süreç içi global'de kalıyor."""
    from app import config_manager
    from app.config import set_language, get_language

    hedef = tmp_path / "config.user.json"
    monkeypatch.setattr(config_manager, "CONFIG_USER_PATH", hedef)
    monkeypatch.setattr(config_manager, "_cache", None)

    onceki = get_language()
    try:
        assert set_language("ja") is True
        assert hedef.exists(), "set_language diske hiç yazmadı"
        kayit = json.loads(hedef.read_text(encoding="utf-8"))
        assert kayit.get("ASSISTANT_LANGUAGE") == "ja", f"diske yazılan: {kayit}"
    finally:
        set_language(onceki)


def test_a9_gecersiz_dil_diske_yazilmaz(tmp_path, monkeypatch):
    """Reddedilen dil kalıcılaştırılmamalı."""
    from app import config_manager
    from app.config import set_language

    hedef = tmp_path / "config.user.json"
    monkeypatch.setattr(config_manager, "CONFIG_USER_PATH", hedef)
    monkeypatch.setattr(config_manager, "_cache", None)

    assert set_language("klingonca") is False
    assert not hedef.exists(), "geçersiz dil diske yazıldı"


def test_a9_canli_uygulanan_kumesinde():
    """Dil restart istemez — arayüz 'yeniden başlatma gerekli' yazmamalı."""
    from app.api.settings_api import CANLI_UYGULANAN

    assert "ASSISTANT_LANGUAGE" in CANLI_UYGULANAN


# --------------------------------------------------------------------------- #
# A6 — TTS ses seçicisi: çizilir, "kaydedildi" der, ama backend'e hiç ulaşmazdı
# --------------------------------------------------------------------------- #

@pytest.fixture
def temiz_ayar(tmp_path, monkeypatch):
    """Her test kendi config.user.json'ıyla koşsun (gerçek ayara dokunma)."""
    from app import config_manager
    hedef = tmp_path / "config.user.json"
    monkeypatch.setattr(config_manager, "CONFIG_USER_PATH", hedef)
    monkeypatch.setattr(config_manager, "_cache", None)
    return hedef


def test_a6_secim_yoksa_dil_varsayilani_kazanir(temiz_ayar):
    from app.config import set_language, get_language
    from app.services.tts import _edge_voice_params

    onceki = get_language()
    try:
        set_language("tr", persist=False)
        assert _edge_voice_params()[0] == "tr-TR-EmelNeural"
    finally:
        set_language(onceki, persist=False)


def test_a6_kullanici_secimi_dil_varsayilanini_ezer(temiz_ayar, test_ekibi):
    """Seçim artık GERÇEKTEN uygulanıyor — eskiden localStorage'da ölüyordu."""
    from app import config_manager
    from app.config import set_language, get_language
    from app.services import personas
    from app.services.tts import _edge_voice_params

    onceki_dil, onceki_p = get_language(), personas.get_persona()
    try:
        set_language("tr", persist=False)
        personas.set_persona("yuki")
        config_manager.set_value("PERSONA_VOICES", json.dumps({"yuki": "en-US-JennyNeural"}))
        assert _edge_voice_params()[0] == "en-US-JennyNeural"
        # Başka persona etkilenmez
        personas.set_persona("uzman_b")
        assert _edge_voice_params()[0] == "tr-TR-EmelNeural"
    finally:
        set_language(onceki_dil, persist=False)
        personas.set_persona(onceki_p)


def test_a6_bos_secim_dil_varsayilanina_dondurur(temiz_ayar):
    """Geri dönüş yolu olmazsa kullanıcı bir kez seçince dil sesi bir daha gelmez."""
    from app import config_manager
    from app.config import set_language, get_language
    from app.services import personas
    from app.services.tts import _edge_voice_params

    onceki_dil, onceki_p = get_language(), personas.get_persona()
    try:
        set_language("tr", persist=False)
        personas.set_persona("yuki")
        config_manager.set_value("PERSONA_VOICES", json.dumps({"yuki": "en-US-JennyNeural"}))
        assert _edge_voice_params()[0] == "en-US-JennyNeural"
        config_manager.set_value("PERSONA_VOICES", "{}")
        assert _edge_voice_params()[0] == "tr-TR-EmelNeural"
    finally:
        set_language(onceki_dil, persist=False)
        personas.set_persona(onceki_p)


@pytest.mark.parametrize("cop", ["rm -rf /", "tr-TR", "<script>", "tr-TR-EmelNeural; ls", ""])
def test_a6_gecersiz_ses_adi_yok_sayilir(temiz_ayar, cop):
    """Değer dış servise gidiyor — biçim tutmuyorsa sessizce dil varsayılanına düş."""
    from app import config_manager
    from app.config import set_language, get_language
    from app.services import personas
    from app.services.tts import _edge_voice_params

    onceki_dil, onceki_p = get_language(), personas.get_persona()
    try:
        set_language("tr", persist=False)
        personas.set_persona("yuki")
        config_manager.set_value("PERSONA_VOICES", json.dumps({"yuki": cop}))
        assert _edge_voice_params()[0] == "tr-TR-EmelNeural"
    finally:
        set_language(onceki_dil, persist=False)
        personas.set_persona(onceki_p)


def test_a6_bozuk_json_cokertmez(temiz_ayar):
    from app import config_manager
    from app.services.tts import _edge_voice_params

    config_manager.set_value("PERSONA_VOICES", "{bu json değil")
    assert _edge_voice_params()[0].startswith(("tr-", "ja-"))


async def test_a6_uctan_uca_api_turu(client, temiz_ayar, test_ekibi):
    """POST → GET → sentez parametresi: üç ucun aynı gerçeği taşıdığını ölç."""
    from app.services import personas

    onceki_p = personas.get_persona()
    try:
        personas.set_persona("uzman_c")

        r = await client.post(
            "/api/settings/PERSONA_VOICES",
            json={"value": json.dumps({"uzman_c": "tr-TR-AhmetNeural"})},
        )
        assert r.status_code == 200, r.text
        assert r.json()["needs_restart"] is False

        g = await client.get("/api/settings/persona-voices")
        assert g.status_code == 200, g.text
        assert g.json()["secimler"] == {"uzman_c": "tr-TR-AhmetNeural"}

        from app.services.tts import _edge_voice_params
        assert _edge_voice_params()[0] == "tr-TR-AhmetNeural"
    finally:
        personas.set_persona(onceki_p)


async def test_a6_api_gecersiz_degeri_reddeder(client, temiz_ayar):
    kotu = await client.post("/api/settings/PERSONA_VOICES", json={"value": json.dumps({"yuki": "hadi be"})})
    assert kotu.status_code == 400, kotu.text

    yabanci = await client.post("/api/settings/PERSONA_VOICES", json={"value": json.dumps({"bilinmeyen": "tr-TR-EmelNeural"})})
    assert yabanci.status_code == 400, yabanci.text

    bozuk = await client.post("/api/settings/PERSONA_VOICES", json={"value": "{"})
    assert bozuk.status_code == 400, bozuk.text


def test_a6_secici_arayuzde_sunucuya_yaziyor():
    """Arayüz tarafı: seçim ağ isteği atmadan 'kaydedildi' demeyecek."""
    kaynak = (
        pathlib.Path(__file__).resolve().parents[2]
        / "frontend" / "js" / "intro-sequences.js"
    ).read_text(encoding="utf-8")

    i_yaz = kaynak.find("_ttsSunucuyaYaz")
    assert i_yaz != -1, "ses seçimi hâlâ sunucuya gönderilmiyor"
    assert "/api/settings/PERSONA_VOICES" in kaynak
    assert "/api/settings/persona-voices" in kaynak, "panel sunucudaki gerçeği okumuyor"
