"""Google hesabı bağlama — token deposu, dar scope ve kimlik ucu kapıları.

🔴 **Neden bu dosya var (2026-09-14, ``):** Drive'ı ürüne taşıma kararı
alınınca OAuth akışının **zaten var olduğu** (auth-url · callback · CSRF state)
ama iki kusurla yaşadığı ölçüldü:

① **Salt okunur dizine yazma.** `api/planner.py` token'ı `backend/`e yazıyordu →
   satılan pakette o dizin salt okunur; müşteri bağlansa bile oturumu
   kaydedilemezdi. 2026-07-31'de kapatılan **dört** kusurun atlanmış beşincisi.

② **İki ayrı token dosyası.** `calendar.py` `YUKI_DATA_DIR`'e, `planner.py`
   `backend/`e bakıyordu. Kullanıcı AYAR'dan bağlanır, sohbette *"takvimime bak"*
   der, Yuki *"bağlı değilsin"* derdi — iki dosyanın adı aynı, yeri farklıydı.

Ayrıca karar gereği (2026-09-14, kimlik müşteriden)
scope **daraltıldı** ve kimlik **müşteriden** alınır hâle getirildi.
"""

import importlib
import json
import os
from pathlib import Path

import pytest

from app.services import google_token_store as depo


# ── ① Yazılabilirlik: token yazılabilir veri köküne gider ────────────────────

def test_token_yolu_YUKI_DATA_DIR_i_onurlandirir(tmp_path, monkeypatch):
    """🔴 Paketlenmiş kurulumda tek yazılabilir yer burasıdır.

    Bu kapı düşerse kusur **sessizdir**: geliştirme makinesinde her şey çalışır,
    yalnız satılan pakette token kaydedilemez.
    """
    monkeypatch.setenv("YUKI_DATA_DIR", str(tmp_path))
    assert depo.token_dosyasi() == tmp_path / "planner_tokens.json"
    assert depo.durum_dosyasi() == tmp_path / "planner_state_tokens.json"


def test_yol_paket_dizinine_SABITLENMEMIS(tmp_path, monkeypatch):
    """Yol, modülün kendi konumundan türetilip orada KALMAMALI."""
    monkeypatch.setenv("YUKI_DATA_DIR", str(tmp_path))
    yol = depo.token_dosyasi()
    assert "app/services" not in str(yol), "token hâlâ kod dizinine yazılıyor"
    assert str(yol).startswith(str(tmp_path))


def test_yazma_atomik_ve_izin_dar(tmp_path, monkeypatch):
    """Yarım yazma token dosyasını bozmamalı; dosya 0600 olmalı.

    ⚠️ Dosya **refresh token** taşır — yani kalıcı hesap erişimi. Geniş izin,
    aynı makinedeki başka bir kullanıcıya Drive/Takvim erişimi vermek demektir.
    """
    monkeypatch.setenv("YUKI_DATA_DIR", str(tmp_path))
    depo.google_yaz({"access_token": "a", "refresh_token": "r"})
    yol = depo.token_dosyasi()
    assert json.loads(yol.read_text())["google"]["refresh_token"] == "r"
    assert oct(os.stat(yol).st_mode)[-3:] == "600"
    # Atomik yazma geçici dosya bırakmaz (bırakırsa sır diskte iki yerde durur).
    assert not list(tmp_path.glob("*.tmp")), "geçici dosya temizlenmemiş"


def test_bozuk_dosya_cokmez_bos_doner(tmp_path, monkeypatch):
    """Bozuk JSON, uygulamayı açılışta düşürmemeli — bağlantı 'yok' sayılır."""
    monkeypatch.setenv("YUKI_DATA_DIR", str(tmp_path))
    (tmp_path / "planner_tokens.json").write_text("{bozuk")
    assert depo.google_al() is None


# ── ② Tek kaynak: iki tüketici aynı dosyayı görmeli ──────────────────────────

def test_planner_ve_calendar_AYNI_dosyayi_kullanir(tmp_path, monkeypatch):
    """🔴 Asıl kusur buydu: AYAR'dan bağlan, sohbette 'bağlı değilsin' al.

    Kapı davranışsal: `planner.py`'nin yazdığını `calendar.py` OKUYABİLMELİ.
    (Yol karşılaştırmak yetmez — ikisi de kendi yolunu hesaplasa ve yollar
    tesadüfen eşit olsa bile, yarın biri değişince bu test kırmızı yanar.)
    """
    monkeypatch.setenv("YUKI_DATA_DIR", str(tmp_path))
    from app.api import planner
    from app.services.tools import calendar

    planner._save_tokens({"google": {"access_token": "planner-yazdi"}, "microsoft": None})
    assert calendar._load_google_tok() == {"access_token": "planner-yazdi"}

    calendar._save_google_tok({"access_token": "calendar-yazdi"})
    assert planner._load_tokens()["google"] == {"access_token": "calendar-yazdi"}


def test_kendi_token_dosyasini_acan_modul_yok():
    """Yeni bir Google özelliği kendi deposunu AÇMAMALI (② tekrar etmesin)."""
    # ⚠️ Düz metin taraması YETMEZ: dosya adını **anlatan** bir docstring de
    #    eşleşir ve kapı yanlış yere kırmızı yanar (bu turda bizzat oldu).
    #    Aranan şey adın geçmesi değil, ona bir YOL KURULMASI.
    kok = Path(__file__).resolve().parents[1] / "app"
    kullanim = ("Path(", "/ \"planner", "/ 'planner", "open(", "read_text", "write_text")
    suclular = []
    for p in kok.rglob("*.py"):
        if p.name == "google_token_store.py":
            continue
        for satir in p.read_text(encoding="utf-8").splitlines():
            kirpik = satir.strip()
            if kirpik.startswith("#"):
                continue
            adi_geciyor = ("planner_tokens.json" in kirpik
                           or "planner_state_tokens.json" in kirpik)
            if adi_geciyor and any(k in kirpik for k in kullanim):
                suclular.append(f"{p.relative_to(kok)}: {kirpik[:70]}")
    assert not suclular, f"token dosyasına kendi yolunu kuran modül(ler): {suclular}"


# ── ③ Scope dar olmalı ───────────────────────────────────────────────────────

def test_scope_drive_file_ve_calendar_events():
    """Dar izin: `drive.file` + `calendar.events`.

    🔴 Tam `drive` Google'ın **restricted** sınıfıdır (CASA güvenlik denetimi);
    tam `calendar` ise takvim oluşturma/silme yetkisi verir ve kod onu hiç
    kullanmaz. Geniş izin, müşterinin onay ekranında gördüğü şeyi de büyütür.
    """
    from app.api import planner
    kapsam = planner._GOOGLE_SCOPES.split()
    assert "https://www.googleapis.com/auth/drive.file" in kapsam
    assert "https://www.googleapis.com/auth/calendar.events" in kapsam
    assert "https://www.googleapis.com/auth/drive" not in kapsam, "tam drive = restricted"
    assert "https://www.googleapis.com/auth/calendar" not in kapsam, "tam calendar gereksiz"


# ── ④ Kimlik ucu: müşteri kendi client_id'sini girer ─────────────────────────

@pytest.fixture
def istemci():
    from fastapi.testclient import TestClient
    from app.main import app
    return TestClient(app)


def test_kimlik_ucu_yanlis_bicimi_reddeder(monkeypatch):
    """Yanlış alan yapıştıran kullanıcı Google ekranında sebebini ANLAYAMAZ.

    (Proje numarası / API anahtarı / 'İstemci gizli anahtarı' sık karıştırılır.)
    """
    from app.api import planner
    import asyncio
    from fastapi import HTTPException

    govde = planner.GoogleKimlikBody(client_id="123456789", client_secret="GOCSPX-x")
    with pytest.raises(HTTPException) as e:
        asyncio.run(planner.google_kimlik_kaydet.__wrapped__(None, govde))
    assert e.value.status_code == 400
    assert "apps.googleusercontent.com" in e.value.detail


def test_kimlik_ucu_env_e_yazar_ve_surece_uygular(monkeypatch):
    """Kaydet → hem `.env`'e yaz hem ÇALIŞAN sürece uygula.

    ⚠️ Yalnız `.env`'e yazmak yetmez: kullanıcı kaydeder, 'Bağlan'a basar ve
    503 alır. BYOK anahtar akışında aynı kusur yaşandı (router anahtarı geç
    görüyordu) — yeniden başlatma isteyen akış terk edilir.
    """
    from app.api import planner
    import asyncio

    yazilan = {}
    monkeypatch.setattr(planner, "_persist_env" if hasattr(planner, "_persist_env") else "os",
                        planner.os, raising=False)
    import app.api.llm_config_api as llm_api
    monkeypatch.setattr(llm_api, "_persist_env", lambda k, v: yazilan.__setitem__(k, v))
    monkeypatch.delenv("GOOGLE_CLIENT_ID", raising=False)
    monkeypatch.delenv("GOOGLE_CLIENT_SECRET", raising=False)

    cid = "1234-abc.apps.googleusercontent.com"
    govde = planner.GoogleKimlikBody(client_id=cid, client_secret="GOCSPX-gizli")
    sonuc = asyncio.run(planner.google_kimlik_kaydet.__wrapped__(None, govde))

    assert yazilan["GOOGLE_CLIENT_ID"] == cid
    assert yazilan["GOOGLE_CLIENT_SECRET"] == "GOCSPX-gizli"
    assert os.environ["GOOGLE_CLIENT_ID"] == cid, "çalışan sürece uygulanmadı"
    assert "GOCSPX" not in json.dumps(sonuc), "gizli anahtar cevapta sızıyor"
    assert "…" in sonuc["client_id"], "client_id maskelenmemiş"


def test_kimlik_yoksa_hata_metni_env_demez():
    """Hata metni MÜŞTERİYE gider — `.env` diye bir dosyayı ne görür ne açar."""
    from app.api import planner
    assert ".env" not in planner._KIMLIK_YOK
    assert "AYAR" in planner._KIMLIK_YOK, "kullanıcıya nereye gideceği söylenmiyor"


# ── ⑤ Durum ucu: 'bağlı' ile 'kimlik girilmiş' ayrı sorular ──────────────────

def test_durum_eksik_izni_bildirir(tmp_path, monkeypatch):
    """Scope 09-14'te değişti → eski token Drive'ı kapsamaz.

    Söylenmezse kullanıcı 'bağlıyım' görür, Drive işi sessizce 403 alır.

    🔵 2026-09-14 (FAZ 4): test artık **depoya** yazıyor, eskiden `planner._tokens`
    global'ine yazıyordu. O global kaldırıldı (yedekleme ikinci yazar oldu ve
    kopya bayatlıyordu); testin de ölçtüğü yol gerçek yol olmalı.
    """
    from app.api import planner
    import asyncio

    monkeypatch.setenv("YUKI_DATA_DIR", str(tmp_path))
    depo.google_yaz({
        "access_token": "eski",
        "scope": "https://www.googleapis.com/auth/calendar.events",
    })
    d = asyncio.run(planner.google_status.__wrapped__(None))
    assert d["connected"] is True
    assert "https://www.googleapis.com/auth/drive.file" in d["eksik_izin"]


def test_durum_kimlik_varligini_ayri_bildirir(tmp_path, monkeypatch):
    from app.api import planner
    import asyncio

    monkeypatch.setenv("YUKI_DATA_DIR", str(tmp_path))
    depo.google_yaz(None)
    monkeypatch.delenv("GOOGLE_CLIENT_ID", raising=False)
    d = asyncio.run(planner.google_status.__wrapped__(None))
    assert d["connected"] is False and d["kimlik_var"] is False


# ── ⑥ FAZ 4C — geliştiricinin ilk GERÇEK turunda ölçülen iki kusur ─────────────────

_TAKVIM = "https://www.googleapis.com/auth/calendar.events"
_DRIVE = "https://www.googleapis.com/auth/drive.file"


def test_callback_sayfasi_EKSIK_izni_soyler_sabit_metin_degil():
    """🔴 Sayfa *"Takvim ve Drive izinleri verildi"* diye SABİT yazıyordu.

    Geliştiricinin ilk gerçek turunda Google yalnız `drive.file` verdi; panel doğru
    cevabı biliyordu (`eksik_izin`) ama kullanıcının gördüğü **ilk** ekran
    yanlış olandı. Eksik izin fark edildiği anda söylenmezse bir hafta sonra
    *"takvimimi neden görmüyor"* olarak döner.
    """
    from app.api.planner import _callback_metni

    tam, govde = _callback_metni(f"{_TAKVIM} {_DRIVE}")
    assert tam is True and "Takvim ve Drive izinleri verildi" in govde

    tam, govde = _callback_metni(_DRIVE)          # geliştiricinin turunda olan
    assert tam is False
    assert "Takvim izni verilmedi" in govde
    assert "Yeniden bağlan" in govde, "ne yapacağı söylenmiyor"

    tam, govde = _callback_metni(_TAKVIM)
    assert tam is False and "Drive izni verilmedi" in govde

    tam, govde = _callback_metni("")
    assert tam is False and "Hiçbir izin verilmedi" in govde


def test_invalid_client_KIMLIK_metni_verir_ve_tokeni_SILMEZ(tmp_path, monkeypatch):
    """🔴 Google `invalid_client`'ı **401** ile döndürüyor (FAZ 4C'de ölçüldü).

    Kod yalnız `invalid_grant` ya da 400 bekliyordu → kullanıcı ham JSON
    (`Google token yenilenemedi (401): {...}`) görüyordu. Üstelik teşhis zıttır:
    sorun oturumda değil KİMLİKTE. Token silinseydi kullanıcı boşuna yeniden
    bağlanır, kimlik hâlâ yanlış olduğu için yine düşerdi.
    """
    import asyncio
    import httpx
    from app.services import google_client as g

    monkeypatch.setenv("YUKI_DATA_DIR", str(tmp_path))
    depo.google_yaz({"access_token": "a", "refresh_token": "r"})

    class SahteCevap:
        is_success = False
        status_code = 401
        text = '{"error": "invalid_client", "error_description": "not found"}'

    class SahteIstemci:
        async def __aenter__(self):
            return self

        async def __aexit__(self, *a):
            return False

        async def post(self, *a, **k):
            return SahteCevap()

    monkeypatch.setattr(httpx, "AsyncClient", lambda **k: SahteIstemci())

    with pytest.raises(g.GoogleYetkiDustu) as hata:
        asyncio.run(g.yenile({"refresh_token": "r"}))

    metin = str(hata.value)
    assert "Değiştir" in metin and "istemci kimliğin" in metin.lower(), metin
    assert "Yeniden bağlan" not in metin, "yanlış teşhis — sorun oturumda değil kimlikte"
    assert depo.google_al(), "token silindi — kimlik hatasında oturuma dokunulmamalı"
