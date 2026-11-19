"""Uygulama kilidi — çekirdek, uçlar ve middleware kapısı.

Testlerin çoğu `app_lock`'un dosya yolunu geçici bir dizine çevirir: gerçek
`DATA_DIR`'e yazmak, geliştirme makinesindeki kilidi ezerdi.

🔑 Bu dosyanın asıl ölçtüğü şey "fonksiyon çalışıyor mu" değil, **kapı gerçekten
kapanıyor mu**: parola kurulduğunda korumasız bir uç kaldı mı, yanlış parola
sayacı işliyor mu, oturum token'ı olmadan istek geçiyor mu.
"""

import json

import pytest

from app.services import app_lock, login_guard


@pytest.fixture(autouse=True)
def gecici_kilit(tmp_path, monkeypatch):
    """Her test kendi boş kilit dosyasıyla ve temiz sayaçlarla başlasın.

    ⚠️ `limiter.reset()` ŞART: slowapi sayacı süreç ömrü boyunca yaşar ve tüm
    testler aynı istemci IP'sinden (127.0.0.1) koşar. Sıfırlanmazsa dosyadaki
    testler birikip 10/dk sınırını tüketir ve **sonraki testler kendi
    hatalarından değil, öncekilerin artığından** kırmızı yanar (ölçüldü: 4 test).
    """
    from app.limiter import limiter

    monkeypatch.setattr(app_lock, "KILIT_DOSYASI", tmp_path / "app_lock.json")
    monkeypatch.setattr(app_lock, "DATA_DIR", tmp_path)
    monkeypatch.setattr("app.services.app_lock.DATA_DIR", tmp_path)
    app_lock.tum_oturumlari_kapat()
    login_guard._sifirla()
    limiter.reset()
    yield
    app_lock.tum_oturumlari_kapat()
    login_guard._sifirla()
    limiter.reset()


# ══════════════════════════════════════════════════════════════════════════
#  Çekirdek
# ══════════════════════════════════════════════════════════════════════════

def test_baslangicta_kilit_yok():
    assert app_lock.kurulu() is False
    # Kapı yokken doğrulama DAİMA false — "parola boş, o hâlde herkes geçsin"
    # gibi bir yorum kapıyı tümden açardı.
    assert app_lock.parola_dogrula("") is False
    assert app_lock.parola_dogrula("herhangi") is False


def test_parola_kurulunca_dogrulanir():
    app_lock.parola_kur("gizli-parola")
    assert app_lock.kurulu() is True
    assert app_lock.parola_dogrula("gizli-parola") is True
    assert app_lock.parola_dogrula("gizli-parolb") is False


def test_parola_diskte_duz_metin_DEGIL():
    """🔴 En kritik test: dosyayı açan biri parolayı okuyamamalı."""
    app_lock.parola_kur("cok-gizli-123")
    ham = app_lock.KILIT_DOSYASI.read_text(encoding="utf-8")
    assert "cok-gizli-123" not in ham
    kayit = json.loads(ham)
    assert kayit["kdf"] == "scrypt"
    assert kayit["tuz"] and kayit["hash"]
    # Tuz gerçekten rastgele mi: aynı parola iki kez kurulunca hash FARKLI olmalı.
    # Aynı çıkarsa tuz sabittir ve gökkuşağı tablosu işe yarar.
    ilk_hash = kayit["hash"]
    app_lock.parola_kur("cok-gizli-123")
    assert json.loads(app_lock.KILIT_DOSYASI.read_text(encoding="utf-8"))["hash"] != ilk_hash


def test_kisa_parola_reddedilir():
    with pytest.raises(ValueError):
        app_lock.parola_kur("ab")


def test_asiri_uzun_parola_reddedilir():
    """scrypt'e sınırsız girdi vermek ucuz bir CPU tüketme yoludur."""
    with pytest.raises(ValueError):
        app_lock.parola_kur("a" * (app_lock.MAX_UZUNLUK + 1))
    # Doğrulama tarafı da aynı sınırı uygular ve hash HESAPLAMADAN reddeder.
    app_lock.parola_kur("normal-parola")
    assert app_lock.parola_dogrula("a" * (app_lock.MAX_UZUNLUK + 1)) is False


def test_bozuk_dosya_kilidi_kurulu_saymaz():
    """Bozuk kayıt kullanıcıyı kendi uygulamasından kilitlemez (bilinçli karar)."""
    app_lock.KILIT_DOSYASI.write_text("{bozuk json", encoding="utf-8")
    assert app_lock.kurulu() is False


def test_eksik_alanli_kayit_kurulu_saymaz():
    app_lock.KILIT_DOSYASI.write_text(json.dumps({"kdf": "scrypt"}), encoding="utf-8")
    assert app_lock.kurulu() is False


def test_kaldirinca_dosya_ve_oturumlar_gider():
    app_lock.parola_kur("parola-123")
    token = app_lock.oturum_ac()
    assert app_lock.oturum_gecerli(token) is True
    app_lock.parola_kaldir()
    assert app_lock.kurulu() is False
    # 🔑 Oturumun da düşmesi ŞART: kilit kaldırılıp YENİ bir parolayla tekrar
    # kurulduğunda eski token geçerli kalsaydı, yeni parolayı bilmeyen birinin
    # elinde çalışan bir anahtar kalırdı.
    assert app_lock.oturum_gecerli(token) is False


# ══════════════════════════════════════════════════════════════════════════
#  Oturumlar
# ══════════════════════════════════════════════════════════════════════════

def test_oturum_acilir_ve_kapanir():
    token = app_lock.oturum_ac()
    assert app_lock.oturum_gecerli(token) is True
    app_lock.oturum_kapat(token)
    assert app_lock.oturum_gecerli(token) is False


def test_gecersiz_token_kabul_edilmez():
    app_lock.oturum_ac()
    assert app_lock.oturum_gecerli("uydurma-token") is False
    assert app_lock.oturum_gecerli("") is False
    assert app_lock.oturum_gecerli(None) is False


def test_suresi_dolan_oturum_gecersiz(monkeypatch):
    zaman = {"t": 1000.0}
    monkeypatch.setattr("app.services.app_lock.time.time", lambda: zaman["t"])
    token = app_lock.oturum_ac()
    assert app_lock.oturum_gecerli(token) is True
    zaman["t"] += app_lock.OTURUM_SANIYE + 1
    assert app_lock.oturum_gecerli(token) is False


def test_oturumlar_diske_yazilmaz():
    """Oturum yalnız bellekte yaşamalı — diske yazılsaydı uygulama yeniden
    açıldığında kilit hiç sorulmazdı, yani kilit bir kez açılınca kalıcı olarak
    devre dışı kalırdı."""
    app_lock.parola_kur("parola-123")
    token = app_lock.oturum_ac()
    ham = app_lock.KILIT_DOSYASI.read_text(encoding="utf-8")
    assert token not in ham


# ══════════════════════════════════════════════════════════════════════════
#  Uçlar
# ══════════════════════════════════════════════════════════════════════════

@pytest.mark.anyio
async def test_status_parola_sizdirmaz(client):
    app_lock.parola_kur("gizli-parola")
    r = await client.get("/api/lock/status")
    assert r.status_code == 200
    govde = r.text
    assert "gizli-parola" not in govde
    d = r.json()
    assert d["kurulu"] is True
    assert "hash" not in d and "tuz" not in d


@pytest.mark.anyio
async def test_unlock_dogru_parola_token_verir(client):
    app_lock.parola_kur("parola-123")
    r = await client.post("/api/lock/unlock", json={"parola": "parola-123"})
    assert r.status_code == 200
    token = r.json()["token"]
    assert app_lock.oturum_gecerli(token) is True


@pytest.mark.anyio
async def test_unlock_yanlis_parola_401(client):
    app_lock.parola_kur("parola-123")
    r = await client.post("/api/lock/unlock", json={"parola": "yanlis"})
    assert r.status_code == 401
    assert "token" not in r.json()


@pytest.mark.anyio
async def test_kilit_yokken_unlock_409(client):
    r = await client.post("/api/lock/unlock", json={"parola": "herhangi"})
    assert r.status_code == 409


@pytest.mark.anyio
async def test_set_mevcut_parola_olmadan_degistirmez(client):
    """🔴 Açık bırakılmış bir oturum, parolayı sessizce değiştirip kalıcı
    erişime çeviremesin."""
    app_lock.parola_kur("eski-parola")
    # Oturum AÇIK — yani 401 middleware'den değil, ucun kendi kapısından gelmeli.
    # Token'sız çağırsaydık test yeşil olurdu ama ölçtüğü şey bu olmazdı.
    bas = await _oturum_basligi(client, "eski-parola")
    r = await client.post("/api/lock/set", headers=bas, json={"yeni": "yeni-parola"})
    assert r.status_code == 401
    assert "Mevcut parola" in r.json()["detail"]
    assert app_lock.parola_dogrula("eski-parola") is True
    assert app_lock.parola_dogrula("yeni-parola") is False


async def _oturum_basligi(client, parola):
    """Kilidi açıp `Authorization` başlığı üret.

    `/set` ve `/disable` kapının ARKASINDA (bkz.
    `test_kilit_yonetim_uclari_kapinin_ARKASINDA`), yani gerçek kullanıcı da
    oraya ancak kilidi açtıktan sonra ulaşır. Test o yolu birebir izler.
    """
    r = await client.post("/api/lock/unlock", json={"parola": parola})
    assert r.status_code == 200, r.text
    return {"Authorization": f"Bearer {r.json()['token']}"}


@pytest.mark.anyio
async def test_set_mevcut_parolayla_degistirir(client):
    app_lock.parola_kur("eski-parola")
    bas = await _oturum_basligi(client, "eski-parola")
    r = await client.post("/api/lock/set", headers=bas,
                          json={"mevcut": "eski-parola", "yeni": "yeni-parola"})
    assert r.status_code == 200, r.text
    assert app_lock.parola_dogrula("yeni-parola") is True
    assert app_lock.parola_dogrula("eski-parola") is False


@pytest.mark.anyio
async def test_disable_parola_ister(client):
    app_lock.parola_kur("parola-123")
    bas = await _oturum_basligi(client, "parola-123")

    r = await client.post("/api/lock/disable", headers=bas, json={"parola": "yanlis"})
    assert r.status_code == 401
    assert app_lock.kurulu() is True

    r = await client.post("/api/lock/disable", headers=bas, json={"parola": "parola-123"})
    assert r.status_code == 200, r.text
    assert app_lock.kurulu() is False


@pytest.mark.anyio
async def test_kisa_parola_ucta_422(client):
    r = await client.post("/api/lock/set", json={"yeni": "ab"})
    assert r.status_code == 422


# ══════════════════════════════════════════════════════════════════════════
#  login_guard bağlantısı
# ══════════════════════════════════════════════════════════════════════════

@pytest.mark.anyio
async def test_ust_uste_hatali_parola_yolu_kapatir(client):
    """N hatalı denemeden sonra parola yolu kapanır → 429."""
    app_lock.parola_kur("parola-123")
    from app.config import LOGIN_MAX_FAILS

    son = None
    for _ in range(LOGIN_MAX_FAILS):
        son = await client.post("/api/lock/unlock", json={"parola": "yanlis"})
    assert son.status_code == 429
    assert "Retry-After" in son.headers
    # 🔑 429'un KAYNAĞINI doğrula. slowapi'nin hız sınırı da 429 döndürür;
    # ayırt etmezsek bu test bir gün limiter yüzünden geçer, guard bozukken
    # bile yeşil kalır — "yanlış sebeple geçen test" sınıfı.
    assert "Parola" in son.json()["detail"], (
        f"429 guard'dan değil hız sınırından gelmiş olabilir: {son.json()}")

    # 🔑 Kilit DOĞRU parolayı da reddetmeli — yoksa sayaç sadece yanlış
    # denemeleri yavaşlatır, saldırıyı durdurmaz.
    r = await client.post("/api/lock/unlock", json={"parola": "parola-123"})
    assert r.status_code == 429


@pytest.mark.anyio
async def test_parola_yolu_kapaninca_yuz_yolu_acik_kalir(client):
    """Karşılıklı yol kapatma: kullanıcı asla tamamen kilitlenmez."""
    app_lock.parola_kur("parola-123")
    from app.config import LOGIN_MAX_FAILS

    for _ in range(LOGIN_MAX_FAILS):
        await client.post("/api/lock/unlock", json={"parola": "yanlis"})

    d = (await client.get("/api/lock/status")).json()
    assert d["guard"]["password"]["locked"] is True
    assert d["guard"]["face"]["locked"] is False


@pytest.mark.anyio
async def test_basarili_giris_sayaci_sifirlar(client):
    app_lock.parola_kur("parola-123")
    await client.post("/api/lock/unlock", json={"parola": "yanlis"})
    await client.post("/api/lock/unlock", json={"parola": "parola-123"})
    d = (await client.get("/api/lock/status")).json()
    assert d["guard"]["password"]["fails"] == 0


# ══════════════════════════════════════════════════════════════════════════
#  Middleware kapısı — "gerçek kapı" iddiasının kendisi
# ══════════════════════════════════════════════════════════════════════════

@pytest.mark.anyio
async def test_kilit_yokken_uclar_acik(client):
    r = await client.get("/api/ping")
    assert r.status_code != 401


@pytest.mark.anyio
async def test_kilit_kuruluyken_tokensiz_istek_401(client):
    """🔴 Bu test "perde değil gerçek kapı" iddiasını ölçer.

    Geri alınırsa (middleware'deki kilit dalı silinirse) kırmızı yanar.
    """
    app_lock.parola_kur("parola-123")
    r = await client.get("/api/ping")
    assert r.status_code == 401


@pytest.mark.anyio
async def test_kilit_kuruluyken_oturum_tokeni_gecer(client):
    app_lock.parola_kur("parola-123")
    token = (await client.post("/api/lock/unlock",
                               json={"parola": "parola-123"})).json()["token"]
    r = await client.get("/api/ping", headers={"Authorization": f"Bearer {token}"})
    assert r.status_code != 401


@pytest.mark.anyio
async def test_kilit_kuruluyken_uydurma_token_401(client):
    app_lock.parola_kur("parola-123")
    r = await client.get("/api/ping", headers={"Authorization": "Bearer uydurma"})
    assert r.status_code == 401


@pytest.mark.anyio
async def test_bos_authorization_basligi_kapiyi_acmaz(client):
    """⚠️ `compare_digest("", "")` **True** döner. AUTH_TOKEN boşken bu kontrol
    korunmazsa boş bir başlık her kapıyı açardı."""
    app_lock.parola_kur("parola-123")
    for baslik in ({"Authorization": ""}, {"Authorization": "Bearer "}):
        r = await client.get("/api/ping", headers=baslik)
        assert r.status_code == 401, f"boş başlık geçti: {baslik}"


@pytest.mark.anyio
async def test_giris_uclari_kilitliyken_de_acik(client):
    """Kilit ekranının çağırdığı uçlar kapının DIŞINDA olmalı, yoksa kullanıcı
    parolayı girecek ekranı hiç göremez (kilitli kapıya kilitli anahtar)."""
    app_lock.parola_kur("parola-123")
    for yol in ("/api/lock/status", "/api/face/login-status"):
        r = await client.get(yol)
        assert r.status_code != 401, f"{yol} kilitli — kilit ekranı açılamaz"


@pytest.mark.anyio
async def test_kilit_yonetim_uclari_kapinin_ARKASINDA(client):
    """`/set`, `/disable`, `/lock` açık uç OLMAMALI.

    `_SKIP_PATHS`'e yanlışlıkla eklenirlerse bu test kırmızı yanar: o durumda
    kilidi hiç açmamış biri parolayı değiştirebilirdi.
    """
    app_lock.parola_kur("parola-123")
    for yol in ("/api/lock/set", "/api/lock/disable", "/api/lock/lock"):
        r = await client.post(yol, json={})
        assert r.status_code == 401, f"{yol} kapının DIŞINDA kalmış"


@pytest.mark.anyio
async def test_kilit_kurulunca_kapi_YENIDEN_BASLATMADAN_kapanir(client):
    """Kilit durumu süreç ömrü boyunca önbelleğe alınmamalı: kullanıcı Ayarlar'dan
    parolayı kurduğu anda kapı kapanmalı, uygulamayı kapatıp açtığında değil."""
    assert (await client.get("/api/ping")).status_code != 401
    app_lock.parola_kur("parola-123")
    assert (await client.get("/api/ping")).status_code == 401
    app_lock.parola_kaldir()
    assert (await client.get("/api/ping")).status_code != 401
