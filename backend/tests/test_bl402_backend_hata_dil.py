""" ⑥ — backend hata/durum metinleri dil kapısı (22 dosya, 179 anahtar).

Frontend iki dilde çevrildikten sonra EN ekranında hâlâ Türkçe cümle kalıyordu:
toast'lar, SAĞLIK paneli satırları, harita/duvar/yedekleme hataları backend'den
geliyordu. Blok 4B'nin dersi yine geçerli: *ekran, onu dolduran her kaynak
çevrilene kadar çevrilmiş sayılmaz.*

Kapı üç şeyi ölçer:
  1. 22 dosya kullanıcıya ham Türkçe dizgi göndermiyor — log/yorum/docstring ve
     `# i18n-istisna: <gerekçe>` işaretli satırlar hariç (LLM'e giden araç
     sonucu, veri değeri, metne karşı eşleşen sözleşme…). Gerekçesiz istisna
     istisna değildir: işaret boş bırakılırsa kapı kırmızı.
  2. Bu dalganın önekleri iki dilde dolu, EN Türkçe harf taşımıyor, yer
     tutucular iki dilde aynı (düşen `{sebep}` müşteriye hatanın nedenini
     söylemeyen bir cümle bırakır).
  3. Metin ÇAĞRI anında üretiliyor — modül düzeyinde donmuş sabit yok.
"""
from __future__ import annotations

import re
from pathlib import Path

import pytest

from app import config
from app.mesajlar import KATALOG, M

_BACKEND = Path(__file__).resolve().parents[1]
_TR = re.compile(r"[çğıöşüÇĞİÖŞÜ]")
_YT = re.compile(r"\{(\w+)")
_ISTISNA = "i18n-istisna:"

DOSYALAR = (
    "app/services/self_check.py", "app/api/monitor.py", "app/api/push.py",
    "app/api/todo.py", "app/api/planner.py", "app/api/fitness.py",
    "app/api/map.py", "app/api/duvar_api.py", "app/api/devices_api.py",
    "app/services/cihaz_eslestirme.py", "app/services/google_client.py",
    "app/api/media.py", "app/api/live_portrait.py", "app/api/vision.py",
    "app/api/voice.py", "app/services/stt.py", "app/services/native_audio.py",
    "app/api/yedekleme.py", "app/api/modes_api.py",
    "app/services/tools/smart_home.py",
    # ⑧ — kalan 29 satır + aynı dosyalarda ölçüyle çıkan ekran metinleri
    "app/api/character_api.py", "app/api/language_api.py",
    "app/api/llm_config_api.py", "app/api/websocket.py",
    "app/api/websocket_native.py", "app/services/ambient.py",
    "app/services/device_manager.py", "app/services/doc_reader.py",
    "app/services/yedekleme.py", "app/services/error_log.py",
    "app/services/face_regions.py", "app/services/health.py",
    "app/services/insightface_havuzu.py",
    # ⑨ — ekranda görünen kalan metinler (paket 1, 2026-09-25); llm/scheduler/
    #     config/news_watcher/settings_api'de istem + veri kaldığı için henüz yok
    "app/services/runner.py", "app/services/startup_validator.py",
    "app/services/dbus_watcher.py", "app/services/disaster_watch.py",
    "app/api/tts_api.py", "app/api/chat.py", "app/api/pydeps_api.py",
    "app/config_manager.py", "app/main.py",
    # ⑩ — AJAN sekmesi (2026-10-04): doğarken kapının içinde
    "app/api/ajan_api.py", "app/services/ajan_oturumlari.py",
)
ONEKLER = ("saglik.", "monitor.", "todo.", "planlayici.", "fitness.", "harita.",
           "duvar.", "cihaz.", "google.", "medya.", "portre.", "gorme.", "stt.",
           "yedek.", "is.", "mod.", "ekip.", "belge.", "ses.", "llm.",
           "brifing.", "bildirim.", "acilis.", "pydeps.", "ayar.", "hata.", "ajan.")


def _kod_satirlari(kaynak: str) -> list[str]:
    """Docstring/log/yorum elenir, satır numarası korunur; istisna satırı boşalır."""
    bos = lambda m: "\n" * m.group(0).count("\n")  # noqa: E731
    kaynak = "\n".join("" if _ISTISNA in s else s for s in kaynak.splitlines())
    kaynak = re.sub(r'"""(?:.|\n)*?"""', bos, kaynak)
    kaynak = re.sub(r"'''(?:.|\n)*?'''", bos, kaynak)
    kaynak = re.sub(r"\b(?:logger|log|_log|logging|print)(?:\.\w+)?\("
                    r"(?:[^()]|\((?:[^()]|\([^()]*\))*\))*\)", bos, kaynak)
    return [s.split("#", 1)[0] for s in kaynak.splitlines()]


@pytest.mark.parametrize("yol", DOSYALAR)
def test_dosya_KULLANICIYA_ham_Turkce_gondermiyor(yol):
    kaynak = (_BACKEND / yol).read_text(encoding="utf-8")
    kalan = [f"{n}: {m.group(0)}"
             for n, s in enumerate(_kod_satirlari(kaynak), 1)
             for m in re.finditer(r"""[rbfu]*(["'])(?:(?!\1)[^\\\n]|\\.)*\1""", s)
             if _TR.search(m.group(0))]
    assert not kalan, f"{yol}: ham Türkçe dizgi → {kalan[:5]}"


@pytest.mark.parametrize("yol", DOSYALAR)
def test_istisna_isareti_GEREKCESIZ_degil(yol):
    for n, s in enumerate((_BACKEND / yol).read_text(encoding="utf-8").splitlines(), 1):
        if _ISTISNA in s:
            gerekce = s.split(_ISTISNA, 1)[1].strip()
            assert len(gerekce) >= 8, f"{yol}:{n} istisna gerekçesiz → {s.strip()}"


def _dalga_anahtarlari() -> list[str]:
    return sorted(k for k in KATALOG["tr"] if k.startswith(ONEKLER))


def test_dalga_anahtarlari_IKI_DILDE_dolu_ve_yer_tutucu_esit():
    anahtarlar = _dalga_anahtarlari()
    assert len(anahtarlar) >= 179, f"anahtar sayısı düştü: {len(anahtarlar)}"
    for k in anahtarlar:
        tr, en = KATALOG["tr"][k], KATALOG["en"].get(k)
        assert en, f"en: '{k}' eksik/boş"
        assert not _TR.search(en), f"en: '{k}' Türkçe harf taşıyor → {en!r}"
        assert set(_YT.findall(tr)) == set(_YT.findall(en)), (
            f"'{k}': yer tutucu farkı TR {sorted(set(_YT.findall(tr)))} ≠ "
            f"EN {sorted(set(_YT.findall(en)))}"
        )


def test_kullanilan_her_anahtar_katalogda():
    """`M()` bilinmeyen anahtarda ANAHTARI döndürür — ekranda `harita.xyz` görünür."""
    eksik = []
    for yol in DOSYALAR:
        kaynak = (_BACKEND / yol).read_text(encoding="utf-8")
        for k in re.findall(r"\bMc?\(\s*f?\"([a-z][\w.-]+)\"", kaynak):
            if k not in KATALOG["tr"]:
                eksik.append(f"{yol}: {k}")
    assert not eksik, eksik


@pytest.fixture
def dil_geri():
    onceki = config.get_arayuz_dili()
    yield
    config.set_arayuz_dili(onceki, persist=False)


def test_self_check_metni_CAGRI_ANINDA_aktif_dilde(dil_geri):
    """SAĞLIK paneli en çok satır taşıyan yüzey — ve açılışta bir kez üretilseydi
    dil değişince eski dilde kalırdı. Aynı süreçte TR → EN geçişi ölçülür."""
    from app.services import self_check

    def _metinler():
        # Ağa çıkmayan senkron denetimler — `calistir()` LLM ucuna gider.
        kalemler = (self_check._denetle_veri_dizini(), self_check._denetle_disk(),
                    self_check._denetle_llm_anahtar())
        return " ".join(f"{x.get('baslik', '')} {x.get('detay', '')} {x.get('cozum', '')}"
                        for x in kalemler)

    config.set_arayuz_dili("tr", persist=False)
    tr = _metinler()
    config.set_arayuz_dili("en", persist=False)
    en = _metinler()
    assert tr and en and tr != en, "SAĞLIK metni dil değişimine tepki vermiyor"
    assert _TR.search(tr), tr[:200]
    # Dosya yolu veridir (bu makinede `Masaüstü` geçiyor) — ölçüden çıkar.
    assert not _TR.search(re.sub(r"\S*/\S*", "", en)), en[:200]


def test_ui_yolu_AKTIF_dilde_cozuluyor(dil_geri):
    """`{ui_ayar} → {ui_google}` elle geçirilmez, M() doldurur — EN'de TR etiket kalmaz."""
    k = "planlayici.kimlik-yok"
    if k not in KATALOG["tr"]:
        k = next(a for a in _dalga_anahtarlari() if "{ui_" in KATALOG["tr"][a])
    en = M(k, dil="en")
    assert "{" not in en and not _TR.search(en), en


def test_ekip_kota_satiri_METNE_degil_BAYRAGA_bakar(dil_geri):
    """Eskiden `_kota_metni` SAĞLIK detayında "bilgi yok" alt dizgisini arıyordu —
    metin çevrilince EN'de "no info" satırı maliyet onayına sızardı."""
    from app.services import orchestrator, self_check

    bilinmiyor = {"detay": M("saglik.kota-bilinmiyor"), "kota_bilinmiyor": True}
    config.set_arayuz_dili("en", persist=False)
    bilinmiyor_en = {"detay": M("saglik.kota-bilinmiyor"), "kota_bilinmiyor": True}
    kaydet = self_check._denetle_ucretsiz_kota
    try:
        for d in (bilinmiyor, bilinmiyor_en):
            self_check._denetle_ucretsiz_kota = lambda d=d: d
            assert orchestrator._kota_metni() == "", d
        self_check._denetle_ucretsiz_kota = lambda: {"detay": "50/day"}
        assert "50/day" in orchestrator._kota_metni()
    finally:
        self_check._denetle_ucretsiz_kota = kaydet


def test_model_listesi_ONBELLEKTEN_de_aktif_dilde(dil_geri):
    """Liste 30 dk önbellekte kalır — başlık dolum anında üretilseydi dil
    değişince eski dilde gelirdi. Önbellekte anahtar durur, metin çıkışta çözülür."""
    from app.api import llm_config_api as api

    ham = {"ok": True, "groups": api._fallback_groups()}
    config.set_arayuz_dili("tr", persist=False)
    tr = api._cikis(ham, cached=True)
    config.set_arayuz_dili("en", persist=False)
    en = api._cikis(ham, cached=True)
    metin = lambda d: " ".join(g["title"] + " " + " ".join(o["label"] for o in g["options"])  # noqa: E731
                               for g in d["groups"])
    assert _TR.search(metin(tr)), metin(tr)
    assert not _TR.search(metin(en)) and "llm." not in metin(en), metin(en)
    assert "title" not in ham["groups"][0], "önbellek metin taşıyor, anahtar değil"
