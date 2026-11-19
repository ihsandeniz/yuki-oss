import os
import threading

# Test koşusu işletim sistemi anahtarlığına DOKUNMAZ: `app.config` import edilirken
# `sirlar.yukle()` kök `.env`'deki API anahtarlarını anahtarlığa TAŞIR. Geliştirici
# makinesinde bu, `pytest` çalıştırmanın gerçek `.env`'i değiştirmesi demekti. Anahtarlık
# davranışı `test_sirlar.py`'de sahte arka uçla sınanır. `app` import'undan ÖNCE durmalı.
os.environ.setdefault("YUKI_ANAHTARLIK", "0")
# Genişletme bayrağı (g4, 2026-11-12): ürün varsayılanı ATOLYE AÇIK, ama test takımı "kapalı başlar,
# sınayan dosya fikstürle açar" (`atolye_acik`) diye yazıldı: kapalı-404 ve şema kapısı testleri modül
# yüklenirken okunan değere bakıyor. Bu yüzden test süreci onu kapalı başlatır; ÜRÜN varsayılanı ayrı
# süreçte, bu ortam olmadan ölçülür (test_atolye_bayrak.py · test_g4_varsayilanlar.py).
os.environ.setdefault("ATOLYE", "false")

import pytest  # noqa: E402
from httpx import AsyncClient, ASGITransport  # noqa: E402
from app.main import app  # noqa: E402


@pytest.fixture(autouse=True)
def mock_db_pool(mocker):
    """Tüm testlerde DB pool'u mock'la — PostgreSQL gerektirmez."""
    mocker.patch("app.db.connection.get_pool", return_value=None)
    mocker.patch("app.services.memory.get_pool", return_value=None)


@pytest.fixture(autouse=True)
def sahte_llm_anahtari(mocker):
    """Testlerde LLM anahtarı VARMIŞ gibi davran.

    `/api/chat` gerçek istekten önce `_llm_key_missing()` kapısından geçiyor;
    geliştirici ortamında anahtar olmayınca istek LLM'e hiç gitmeden 503
    dönüyordu ve mock'lanmış testler "assert 503 == 200" ile kırılıyordu.
    Bu anahtar hiçbir yere gönderilmez — yalnız kapıyı açar.
    """
    mocker.patch("app.config.OPENROUTER_API_KEY", "sk-or-v1-test-yalnizca-testte")


@pytest.fixture(autouse=True)
def canli_dosyaya_yazmasin(tmp_path, monkeypatch):
    """Testler geliştirme verisine değil GEÇİCİ dizine yazsın (yüz, kilit, sohbet, profil, ayar, hata günlüğü).

    İkisi de `DATA_DIR`'e (pytest'te depo kökü) yazıyor. 09-27 ölçüldü:
    `test_yuz_sahiplik` yanlış adları yamaladığı (`DEPO_YOLU`/`STORE_PATH`… — gerçek ad
    `_DOSYA`) için her koşu kökteki `faces.json`'u BOŞALTIYORDU; `test_app_lock` kökteki
    `login_guard_state.json`'a yazıyordu. Kök, `start.sh` ile YUKI_DATA_DIR'siz koşan
    geliştirme backend'inin gerçek veri dizinidir. Kişisel AliceAi 295059d'deki düzeltmenin
    ürün karşılığı. Bir test kendi yolunu yamalarsa (test_face_store) o kazanır.
    """
    import app.config as config
    from app import config_manager
    from app.services import face_store, fitness_store, lite_memory, login_guard, todo_store
    monkeypatch.setattr(face_store, "_DOSYA", tmp_path / "faces.json")
    monkeypatch.setattr(login_guard, "LOCK_STATE_FILE", tmp_path / "login_guard_state.json")
    # Aynı ölçümde (tam takım, işaret dosyasından yeni olanlar) kökte bunlar da değişiyordu:
    # sohbet geçmişi + kullanıcı profili (lite_memory), hata günlüğü (DATA_DIR'i çağrıda okur),
    # ayar dosyası `backend/config.user.json` + tek yedeği.
    monkeypatch.setattr(lite_memory, "_HISTORY_FILE", tmp_path / "chat_history.json")
    monkeypatch.setattr(lite_memory, "_PROFILE_FILE", tmp_path / "user_profile.json")
    monkeypatch.setattr(config, "DATA_DIR", tmp_path)
    monkeypatch.setattr(config_manager, "CONFIG_USER_PATH", tmp_path / "config.user.json")
    # Postgres'siz gömülü depolar (10-17 ölçüldü: tam takım kökte ikisini de yaratıyordu).
    monkeypatch.setattr(todo_store, "_STORE_FILE", tmp_path / "todo_store.json")
    monkeypatch.setattr(fitness_store, "_STORE_FILE", tmp_path / "fitness_store.json")
    from app.services.monitoring import history
    monkeypatch.setattr(history, "_DB_PATH", tmp_path / "data" / "monitor.db")
    yield


@pytest.fixture(autouse=True)
def gomme_modeli_yoksa_acik_hata(monkeypatch):
    """ONNX gömme modeli yokken ona muhtaç testler TEK TİP, yolu söyleyen mesajla düşsün.

    `memory._use_onnx()` `auto` kipinde modeli `EMBED_ONNX_DIR`'de arar; yoksa
    sentence-transformers'a düşer, o da (torch'suz) kurulu değil. 10-10 ölçüldü: temiz
    venv + `.env`'siz kopyada 25 test dağınık `ModuleNotFoundError` ile düşüyordu
    ("torch" sanıldı). Skip DEĞİL: CI'da modelin yokluğu kırmızı görünmeli.
    Model varsa ya da `EMBED_BACKEND=st` bilinçli seçildiyse hiçbir şeye dokunmaz.
    """
    from app import config
    from app.services import embedding_onnx, memory
    if config.EMBED_BACKEND == "st" or embedding_onnx.available():
        yield
        return

    yol = embedding_onnx._dir()
    mesaj = (
        f"GÖMME MODELİ YOK: {yol} altında {embedding_onnx.MODEL_FILE} + "
        f"{embedding_onnx.TOKENIZER_FILE} bulunamadı. EMBED_ONNX_DIR'i modelin olduğu "
        "dizine ver (geliştirici: backend/models-cache/embedding-onnx) ya da "
        "`python3 scripts/model-getir.py embedding-onnx <dizin>` ile indir (adres: electron/models-manifest.json)."
    )

    def _yok(*_a, **_k):
        pytest.fail(mesaj, pytrace=False)

    monkeypatch.setattr(memory, "_load_model", _yok)
    monkeypatch.setattr(embedding_onnx, "encode", _yok)
    yield


@pytest.fixture
async def client():
    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://127.0.0.1",
    ) as ac:
        yield ac


@pytest.fixture
def atolye_acik(monkeypatch):
    """Atölye uçlarını sınayan dosyalar için `ATOLYE` bayrağını açar (varsayılan kapalı → 404).

    Kullanım: dosya başında `pytestmark = pytest.mark.usefixtures("atolye_acik")`.
    Bayrağın kapalı davranışı: tests/test_atolye_bayrak.py
    """
    import app.config as config
    monkeypatch.setattr(config, "ATOLYE", True)
    yield


_TARAYICI_DURUMU: list = []   # oturum boyunca tek ölçüm: [None] açıldı · ["<hata>"] açılamadı


def _chromium_acilamiyor() -> str | None:
    """Chromium gerçekten başlıyor mu — `executable_path` yetmez: başsız kip ayrı ikili ister."""
    if not _TARAYICI_DURUMU:
        sonuc: list = []

        def _dene():
            try:
                from playwright.sync_api import sync_playwright
                with sync_playwright() as p:
                    p.chromium.launch().close()
                sonuc.append(None)
            except Exception as e:  # ImportError dahil
                sonuc.append(f"{type(e).__name__}: {str(e).splitlines()[0][:200]}")

        # Ayrı iş parçacığı: async testlerde çalışan olay döngüsü sync API'yi reddeder.
        t = threading.Thread(target=_dene, daemon=True)
        t.start()
        t.join(60)
        _TARAYICI_DURUMU.append(sonuc[0] if sonuc else "chromium 60 sn içinde açılmadı")
    return _TARAYICI_DURUMU[0]


@pytest.fixture
def tarayici_gerekli():
    """Gerçek chromium açan testler (Atölye doğrulayıcısının ekran ölçümü, önizleme yalıtımı).

    Tarayıcı yoksa geliştirici makinesinde ATLANIR, nedeni yazılır. `YUKI_TARAYICI_ZORUNLU=1`
    (CI) iken atlanmaz, KIRMIZI düşer: 11-02 GitHub koşusu 41523183945 bu 7 testte
    "Executable doesn't exist … chromium_headless_shell" ile düşmüştü (iş akışında kurulum yoktu).
    """
    hata = _chromium_acilamiyor()
    if hata is None:
        return
    mesaj = (f"CHROMIUM YOK: {hata} — `python -m playwright install chromium` "
             "(CI: pytest.yml 'Playwright chromium' adımı)")
    if os.environ.get("YUKI_TARAYICI_ZORUNLU") == "1":
        pytest.fail(mesaj, pytrace=False)
    pytest.skip(mesaj)


@pytest.fixture
def fitnes_acik(monkeypatch):
    """Fitnes (`/api/fitness*` + fitness araçları) için `FITNES` bayrağını açar (varsayılan kapalı)."""
    import app.config as config
    monkeypatch.setattr(config, "FITNES", True)
    yield


# Yuki dışındaki karakterler 2026-11-14'te kaldırıldı → gerçek kayıtta uzman yok.
# Ekip mekaniği (meclis, delege, olaylar, maliyet kapısı) persona eklendiği gün
# kendiliğinden geri geldiği için ölçülmeye devam eder: bu fikstür kayda geçici,
# ADI ÜRÜNDE OLMAYAN test uzmanları ekler. Bekçi: tests/test_tek_karakter.py
TEST_UZMANLARI = ("uzman_a", "uzman_b", "uzman_c", "uzman_d")


@pytest.fixture
def test_ekibi(monkeypatch):
    from app.services import personas
    for i, k in enumerate(TEST_UZMANLARI):
        monkeypatch.setitem(personas.PERSONAS, k, {
            "label": f"Uzman {k[-1].upper()}", "title": f"Test Uzmanı {i + 1}",
            "identity": f"Adın Uzman {k[-1].upper()}.", "personality": "- Test.",
            "edge_rate": 3 * (i + 1), "edge_pitch": 2 * (i + 1),
        })
    return list(TEST_UZMANLARI)
