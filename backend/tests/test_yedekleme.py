"""Drive yedekleme motoru — kapılar ( FAZ 4).

Bir yedekleme aracının kusurları **sessizdir**: kullanıcı yedeği olduğunu sanar,
olmadığını ancak ihtiyacı olduğu gün öğrenir. O yüzden burada test edilen şey
"kod çalışıyor mu" değil, **üç politika kararı** ve onları bozan somut senaryolar:

① kaynakta silinen dosya Drive'dan **silinmez** (ayna ≠ iki yönlü eşitleme)
② sır dosyaları (`.env`, Google token'ları, VAPID) yedeğe **girmez**
③ `.db` dosyaları sqlite anlık görüntüsüyle kopyalanır (yırtık yedek yoktur)

Testler ağa çıkmaz: Drive katmanı (`google_client`) sahte bir kayıtçıyla
değiştirilir ve **ne gönderildiği** ölçülür.
"""

import asyncio
import json
import sqlite3
from pathlib import Path

import pytest


# ── Sahte Drive ──────────────────────────────────────────────────────────────

class SahteDrive:
    """Yüklenenleri kaydeder. Gerçek Drive'ın iki davranışını taklit eder:
    kimlikle güncelleme (PATCH) ve adla oluşturma (POST)."""

    def __init__(self):
        self.yuklemeler = []       # (ad, klasor_id, dosya_id, icerik)
        self.klasorler = {}
        self._sayac = 0

    async def klasor_al_veya_olustur(self, ad, ebeveyn_id=None):
        anahtar = f"{ebeveyn_id or 'kok'}/{ad}"
        if anahtar not in self.klasorler:
            self._sayac += 1
            self.klasorler[anahtar] = f"klasor{self._sayac}"
        return self.klasorler[anahtar]

    async def klasor_gecerli_mi(self, dosya_id):
        return dosya_id in self.klasorler.values()

    async def dosya_yukle(self, yerel_yol, ad, ebeveyn_id, dosya_id=None):
        icerik = Path(yerel_yol).read_bytes()
        self.yuklemeler.append((ad, ebeveyn_id, dosya_id, icerik))
        self._sayac += 1
        return {"id": dosya_id or f"dosya{self._sayac}", "name": ad}

    def adlar(self):
        return [a for a, *_ in self.yuklemeler]


@pytest.fixture
def ortam(tmp_path, monkeypatch):
    """İzole veri kökü + sahte Drive. Modül yeniden yüklenir (yollar import anında kurulur)."""
    monkeypatch.setenv("YUKI_DATA_DIR", str(tmp_path / "veri"))
    import importlib
    from app.services import yedekleme as y
    y = importlib.reload(y)

    drive = SahteDrive()
    monkeypatch.setattr(y._g, "klasor_al_veya_olustur", drive.klasor_al_veya_olustur)
    monkeypatch.setattr(y._g, "klasor_gecerli_mi", drive.klasor_gecerli_mi)
    monkeypatch.setattr(y._g, "dosya_yukle", drive.dosya_yukle)

    kaynak = tmp_path / "belgeler"
    kaynak.mkdir()
    return y, drive, kaynak


def _kur(y, kaynak, **ayar):
    temel = y.ayarlar()
    temel.update({"acik": True, "yuki_verisi": False})
    temel.update(ayar)
    y.ayar_yaz(temel)
    y.kaynak_ekle(str(kaynak))


# ── ① Silinen dosya politikası ───────────────────────────────────────────────

def test_kaynakta_silinen_dosya_driveda_silinmez(ortam):
    """🔴 Ayna deyip iki yönlü eşitlemek, bir YEDEKLEME aracında veri kaybıdır.

    Yanlışlıkla sildiğin dosya bir sonraki turda yedeğinden de silinseydi
    kurtarma diye bir şey kalmazdı. Dosya yalnız `kaynakta_yok` işaretlenir.
    """
    y, drive, kaynak = ortam
    (kaynak / "rapor.txt").write_text("veri")
    _kur(y, kaynak)

    asyncio.run(y.tur_calistir())
    (kaynak / "rapor.txt").unlink()
    rapor = asyncio.run(y.tur_calistir())

    assert rapor["kaynakta_yok"] == 1
    kid = y.ayarlar()["kaynaklar"][0]["id"]
    kayit = y.indeks_oku(kid)["rapor.txt"]
    assert kayit["kaynakta_yok"] is True
    assert kayit["drive_id"], "Drive kimliği silinmiş — dosya yedekten düşmüş olur"


# ── ② Sır politikası ─────────────────────────────────────────────────────────

@pytest.mark.parametrize("ad", [
    ".env", "planner_tokens.json", "planner_state_tokens.json",
    "vapid_private.pem", "acilis.log",
])
def test_sir_dosyalari_yedege_girmez(ortam, ad):
    """Yedek müşterinin kendi Drive'ına gitse de, hesap erişimi sağlayan bir sırrı
    sormadan buluta kopyalamak sessiz bir karardır. Anahtar yeniden girilebilir;
    sohbet geçmişi girilemez."""
    y, drive, kaynak = ortam
    (kaynak / ad).write_text("gizli")
    (kaynak / "normal.txt").write_text("açık")
    _kur(y, kaynak)

    asyncio.run(y.tur_calistir())
    assert "normal.txt" in drive.adlar()
    assert ad not in drive.adlar()


# ── ③ sqlite politikası ──────────────────────────────────────────────────────

def test_db_dosyasi_sqlite_anlik_goruntusuyle_gider(ortam):
    """🔴 Çalışan bir WAL veritabanını düz kopyalamak YIRTIK dosya üretir: yükleme
    başarılı görünür, geri yükleyince veritabanı bozuktur. Bir yedekleme aracının
    yapabileceği en kötü hata, başarılı sandığın bozuk yedektir.

    Ölçü: yüklenen baytlar **açılabilir bir veritabanı** mı ve satır orada mı?
    """
    y, drive, kaynak = ortam
    db = kaynak / "kayit.db"

    # 🔑 Senaryo GERÇEK olmalı: Yuki **koşarken** yedek alınır. Bağlantı açık ve
    # WAL devredeyken satırlar `.db` dosyasının kendisinde DEĞİL, `-wal`dedir.
    # Bağlantıyı kapatsaydık sqlite checkpoint yapar, düz kopya da doğru çıkar ve
    # test kusuru göremezdi (ilk sürümünde tam bu yüzden mutasyonu kaçırdı).
    baglanti = sqlite3.connect(db)
    baglanti.execute("PRAGMA journal_mode=WAL")
    baglanti.execute("CREATE TABLE t (x TEXT)")
    baglanti.execute("INSERT INTO t VALUES ('merhaba')")
    baglanti.commit()
    try:
        _kur(y, kaynak)
        asyncio.run(y.tur_calistir())
        gonderilen = [i for a, _, _, i in drive.yuklemeler if a == "kayit.db"]
        assert gonderilen, "db dosyası hiç yüklenmedi"
        assert gonderilen[0] != db.read_bytes(), (
            "yüklenen bayt, çalışan veritabanının DÜZ kopyası — anlık görüntü alınmamış"
        )

        kopya = kaynak.parent / "gelen.db"
        kopya.write_bytes(gonderilen[0])
        c = sqlite3.connect(kopya)
        try:
            assert c.execute("SELECT x FROM t").fetchone()[0] == "merhaba", (
                "yedekteki veritabanında satır yok — yırtık yedek"
            )
        finally:
            c.close()
    finally:
        baglanti.close()


def test_wal_ve_shm_ayrica_yuklenmez(ortam):
    """Anlık görüntü zaten bütünü taşır; `-wal`/`-shm` yollamak hem gereksiz hem
    yanıltıcıdır (geri yüklemede eski WAL yeni db'nin üstüne gelir)."""
    y, drive, kaynak = ortam
    # Boş :memory: veritabanını eski SQLite (CI runner) serileştiremez: "unable to serialize 'main'".
    bellek = sqlite3.connect(":memory:")
    bellek.execute("CREATE TABLE t (x)")
    (kaynak / "a.db").write_bytes(bellek.serialize())
    bellek.close()
    (kaynak / "a.db-wal").write_text("x")
    (kaynak / "a.db-shm").write_text("x")
    _kur(y, kaynak)

    asyncio.run(y.tur_calistir())
    assert not [a for a in drive.adlar() if a.endswith(("-wal", "-shm"))]


# ── Ayna mantığı ─────────────────────────────────────────────────────────────

def test_degismeyen_dosya_ikinci_turda_yuklenmez(ortam, monkeypatch):
    """Yöntemin bütün gerekçesi bu: değişmeyeni yeniden yüklemek, tek-zip yolunun
    kullanıcının hattını yakan davranışıdır.

    🔑 İKİ ayrı şey ölçülür, çünkü ikisinin bedeli farklıdır:
    ① dosya **yüklenmedi** (ağ/alan) · ② dosya **okunmadı** (disk/CPU).
    İlk sürüm yalnız ①'i ölçüyordu ve boyut+mtime hızlı elemesini bozan bir
    mutasyonu **kaçırdı**: md5 yolu yine eşleşip yüklemeyi engelliyordu, ama her
    turda her dosya baştan hash'leniyordu — milyon dosyalı bir klasörde tur
    saatlere çıkar ve bunu hiçbir test görmezdi.
    """
    y, drive, kaynak = ortam
    (kaynak / "a.txt").write_text("sabit")
    _kur(y, kaynak)

    asyncio.run(y.tur_calistir())
    ilk = len(drive.yuklemeler)

    sayac = {"n": 0}
    gercek_md5 = y._md5
    monkeypatch.setattr(y, "_md5", lambda p: (sayac.__setitem__("n", sayac["n"] + 1),
                                              gercek_md5(p))[1])
    rapor = asyncio.run(y.tur_calistir())

    assert len(drive.yuklemeler) == ilk, "değişmeyen dosya yeniden yüklendi"
    assert rapor["atlanan"] >= 1 and rapor["yuklenen"] == 0
    assert sayac["n"] == 0, "değişmeyen dosya yine de hash'lendi — hızlı eleme çalışmıyor"


def test_degisen_dosya_KIMLIKLE_guncellenir_kopya_uretmez(ortam):
    """🔴 Drive dosyaları **adla değil kimlikle** ayırır: aynı adla yeniden POST
    etmek ikinci bir dosya yaratır. Ayna bunu bilmezse her turda kopya üretir ve
    kullanıcının alanı sessizce dolar."""
    y, drive, kaynak = ortam
    d = kaynak / "a.txt"
    d.write_text("ilk")
    _kur(y, kaynak)
    asyncio.run(y.tur_calistir())

    d.write_text("ikinci içerik — boyut da değişti")
    rapor = asyncio.run(y.tur_calistir())

    assert rapor["guncellenen"] == 1 and rapor["yuklenen"] == 0
    son = drive.yuklemeler[-1]
    assert son[2], "güncelleme dosya kimliği olmadan gönderildi → Drive'da kopya doğar"
    assert son[3] == b"ikinci i\xc3\xa7erik \xe2\x80\x94 boyut da de\xc4\x9fi\xc5\x9fti"


def test_icerik_ayniysa_mtime_degisse_bile_yuklenmez(ortam):
    """Kopyalama/senkron araçları mtime'ı oynatır. md5 aynıysa bant harcanmaz."""
    y, drive, kaynak = ortam
    d = kaynak / "a.txt"
    d.write_text("sabit")
    _kur(y, kaynak)
    asyncio.run(y.tur_calistir())
    ilk = len(drive.yuklemeler)

    import os
    st = d.stat()
    os.utime(d, (st.st_atime + 500, st.st_mtime + 500))
    asyncio.run(y.tur_calistir())

    assert len(drive.yuklemeler) == ilk


def test_buyuk_dosya_atlanir_ve_SOYLENIR(ortam):
    """Sessizce atlamak, 'yedeğim var' sanan kullanıcı üretir — rapor onu sayar."""
    y, drive, kaynak = ortam
    # Tavan MB cinsinden TAM SAYI (uç `>= 1` doğruluyor) → sınırı 1 MB'la sınarız.
    (kaynak / "buyuk.bin").write_bytes(b"x" * (2 * 1024 * 1024))
    (kaynak / "kucuk.txt").write_text("ok")
    _kur(y, kaynak, tek_dosya_tavani_mb=1)

    rapor = asyncio.run(y.tur_calistir())
    assert "kucuk.txt" in drive.adlar() and "buyuk.bin" not in drive.adlar()
    assert [x["yol"] for x in rapor["buyuk_atlandi"]] == ["buyuk.bin"]


def test_klasor_agaci_aynalanir(ortam):
    """Alt klasörler Drive'da da alt klasör olmalı; hepsi kökte düzleşirse aynı
    adlı iki dosya birbirini ezer."""
    y, drive, kaynak = ortam
    (kaynak / "alt").mkdir()
    (kaynak / "alt" / "a.txt").write_text("1")
    (kaynak / "a.txt").write_text("2")
    _kur(y, kaynak)

    asyncio.run(y.tur_calistir())
    klasorler = {k for _, k, _, _ in drive.yuklemeler}
    assert len(klasorler) == 2, "iki farklı dizindeki dosya aynı klasöre yüklendi"


# ── Kaynak yönetimi ──────────────────────────────────────────────────────────

def test_ic_ice_klasor_reddedilir(ortam):
    """Aynı dosyalar iki kez yüklenir, iki indekste izlenir ve alan boşuna iki
    katına çıkar."""
    y, drive, kaynak = ortam
    (kaynak / "alt").mkdir()
    y.kaynak_ekle(str(kaynak))
    with pytest.raises(y.YedeklemeHatasi):
        y.kaynak_ekle(str(kaynak / "alt"))


def test_kaynak_silinince_indeksi_de_gider(ortam):
    """Kalsaydı klasör yeniden eklendiğinde indeks 'bunlar zaten yüklü' der ve
    hiçbir dosya gitmezdi — boş yedek."""
    y, drive, kaynak = ortam
    (kaynak / "a.txt").write_text("v")
    _kur(y, kaynak)
    asyncio.run(y.tur_calistir())
    kid = y.ayarlar()["kaynaklar"][0]["id"]
    assert y.indeks_oku(kid)

    y.kaynak_sil(kid)
    assert y.indeks_oku(kid) == {}


def test_diskin_tamami_eklenemez(ortam):
    y, drive, kaynak = ortam
    with pytest.raises(y.YedeklemeHatasi):
        y.kaynak_ekle(str(Path(kaynak.anchor)))


# ── Yuki verisi beyaz listesi ────────────────────────────────────────────────

def test_yuki_verisi_BEYAZ_liste_cop_dizinleri_almaz(tmp_path, monkeypatch):
    """🔴 Kara liste yazılamaz: `YUKI_DATA_DIR` Electron'un userData'sıdır ve
    içinde Chromium'un `Cache`/`GPUCache`'i, `models-cache` (GB'larca model)
    durur. Kara liste yazsaydık her yeni Electron sürümü yeni bir çöp dizini
    ekler ve biz onu müşterinin Drive'ına yüklerdik."""
    veri = tmp_path / "veri"
    (veri / "Cache").mkdir(parents=True)
    (veri / "Cache" / "c.bin").write_text("çöp")
    (veri / "models-cache").mkdir()
    (veri / "models-cache" / "m.onnx").write_text("model")
    (veri / "data").mkdir()
    (veri / "data" / "routines.json").write_text("[]")
    (veri / "chat_history.json").write_text("[]")
    (veri / ".env").write_text("GOOGLE_CLIENT_SECRET=abc")

    monkeypatch.setenv("YUKI_DATA_DIR", str(veri))
    import importlib
    from app.services import yedekleme as y
    y = importlib.reload(y)

    kaynak = y._yuki_kaynagi()
    bulunan = {g for _, g, _, _ in y.tara(kaynak, y.VARSAYILAN_ISTISNALAR)}
    assert bulunan == {"chat_history.json", "data/routines.json"}


def test_yedeklemenin_KENDI_durum_dosyalari_yedege_girmez(tmp_path, monkeypatch):
    """🔴 FAZ 4C'de GERÇEK Drive'a karşı ölçülen kusur (2026-09-14).

    `data/**` beyaz listesi `data/yedekleme.json` ile `data/yedek-indeks/*`'ı da
    kapsıyordu; ikisi de **her turun sonunda** yazılır. Sonuç: hiçbir şey
    değişmediği turda bile dosya yüklenir — *"değişmeyeni atlar"* vaadi bozulur
    ve müşterinin Drive'ına her gece boşuna yazılır. Sahte Drive'lı testler bunu
    göremezdi çünkü kusur dosya sayısında değil **turlar arası durumda** yaşıyor.
    """
    veri = tmp_path / "veri"
    (veri / "data" / "yedek-indeks").mkdir(parents=True)
    (veri / "data" / "yedekleme.json").write_text("{}")
    (veri / "data" / "yedek-indeks" / "yuki.json").write_text("{}")
    (veri / "data" / "routines.json").write_text("[]")     # kullanıcı verisi — GİRMELİ
    (veri / "chat_history.json").write_text("[]")

    monkeypatch.setenv("YUKI_DATA_DIR", str(veri))
    import importlib
    from app.services import yedekleme as y
    y = importlib.reload(y)

    bulunan = {g for _, g, _, _ in y.tara(y._yuki_kaynagi(), y.VARSAYILAN_ISTISNALAR)}
    assert bulunan == {"chat_history.json", "data/routines.json"}, (
        "yedekleme kendi durum dosyalarını yedekliyor → her tur yeniden yükler"
    )


def test_ikinci_tur_YUKI_VERISIYLE_de_hicbir_sey_yuklemez(ortam):
    """Aynı kusurun uçtan uca ölçüsü: `yuki_verisi` AÇIKKEN ikinci tur boş geçmeli.

    ⚠️ Mevcut testlerin hepsi `yuki_verisi=False` ile koşuyordu (fixture böyle
    kuruyor) — kusur tam da o kapalı kapının ardında duruyordu. Gerçek kurulumda
    varsayılan **açık**tır.
    """
    y, drive, kaynak = ortam
    (kaynak / "rapor.txt").write_text("veri")
    temel = y.ayarlar()
    temel.update({"acik": True, "yuki_verisi": True})
    y.ayar_yaz(temel)
    y.kaynak_ekle(str(kaynak))

    asyncio.run(y.tur_calistir())
    ikinci = asyncio.run(y.tur_calistir())

    assert (ikinci["yuklenen"], ikinci["guncellenen"]) == (0, 0), (
        f"ikinci tur boşuna yükledi: {ikinci['yuklenen']} yeni, "
        f"{ikinci['guncellenen']} güncelleme"
    )


# ── Yetki kapısı ────────────────────────────────────────────────────────────

def test_kapi_FAIL_CLOSED(monkeypatch):
    """Yetki *bilinemiyorsa* da kapalı — yetki katmanı patlarsa kapı açık kalmaz."""
    from app.api import yedekleme as api
    from app.services import yetki as ent
    from fastapi import HTTPException

    monkeypatch.setattr(ent, "feature_allowed", lambda f: (_ for _ in ()).throw(RuntimeError("x")))
    with pytest.raises(HTTPException) as e:
        api.require_yedekleme()
    assert e.value.status_code == 403


def test_router_kapisi_ROUTER_duzeyinde():
    """Uç uç yazılan kapıda bir uç atlanır ve kimse fark etmez (todo.py dersi)."""
    from app.api import yedekleme as api
    bagimliliklar = [d.dependency for d in api.router.dependencies]
    assert api.require_yedekleme in bagimliliklar


# ── Zamanlama ────────────────────────────────────────────────────────────────

def test_kapaliyken_zamanlanmis_is_kurulmaz(ortam, monkeypatch):
    """Özellik kapalıyken saat dolu kalmış olabilir; iş kurulursa kullanıcı
    kapattığını sandığı şey gece koşar."""
    y, drive, kaynak = ortam
    from app.services import scheduler

    isler = {}
    sahte = type("S", (), {
        "get_job": lambda self, i: isler.get(i),
        "add_job": lambda self, f, **kw: isler.__setitem__(kw["id"], kw),
        "remove_job": lambda self, i: isler.pop(i, None),
    })()
    monkeypatch.setattr(scheduler, "get_scheduler", lambda: sahte)
    monkeypatch.setattr(scheduler, "SCHEDULER_ENABLED", True)

    ayar = y.ayarlar(); ayar.update({"acik": False, "zamanlama": "03:30"}); y.ayar_yaz(ayar)
    scheduler.yedekleme_isini_kur()
    assert "drive_yedekleme" not in isler

    ayar["acik"] = True; y.ayar_yaz(ayar)
    scheduler.yedekleme_isini_kur()
    assert isler["drive_yedekleme"]["hour"] == 3 and isler["drive_yedekleme"]["minute"] == 30


def test_saat_degisince_is_YENIDEN_kurulur(ortam, monkeypatch):
    """Yoksa kullanıcı saati değiştirir, 'kaydedildi' görür ve iş bir sonraki
    açılışa kadar eski saatte koşar — hiçbir yerde yazmayan bir sapma."""
    y, drive, kaynak = ortam
    from app.services import scheduler

    isler = {}
    sahte = type("S", (), {
        "get_job": lambda self, i: isler.get(i),
        "add_job": lambda self, f, **kw: isler.__setitem__(kw["id"], kw),
        "remove_job": lambda self, i: isler.pop(i, None),
    })()
    monkeypatch.setattr(scheduler, "get_scheduler", lambda: sahte)
    monkeypatch.setattr(scheduler, "SCHEDULER_ENABLED", True)

    ayar = y.ayarlar(); ayar.update({"acik": True, "zamanlama": "03:30"}); y.ayar_yaz(ayar)
    scheduler.yedekleme_isini_kur()
    ayar["zamanlama"] = "22:15"; y.ayar_yaz(ayar)
    scheduler.yedekleme_isini_kur()

    assert isler["drive_yedekleme"]["hour"] == 22 and isler["drive_yedekleme"]["minute"] == 15


# ── Rapor / hata dili ────────────────────────────────────────────────────────

def test_baglanti_yoksa_tur_COKMEZ_sebebini_soyler(ortam, monkeypatch):
    """ElevenLabs '401 = kota' dersi: doğru teşhis, doğru çözüme yollar."""
    y, drive, kaynak = ortam
    (kaynak / "a.txt").write_text("v")
    _kur(y, kaynak)

    async def bagli_degil(*a, **kw):
        raise y._g.GoogleBagliDegil()
    monkeypatch.setattr(y._g, "klasor_al_veya_olustur", bagli_degil)

    rapor = asyncio.run(y.tur_calistir())
    assert rapor["hata"] and "AYAR" in rapor["hata"]
    assert y.ayarlar()["son_tur"]["hata"], "hata son_tur'a yazılmadı — panel sebebi gösteremez"


def test_yetki_dustu_metni_7_GUN_tuzagini_anlatir():
    """Rehberin kırmızı kutusuyla aynı sebep: 'Testing' kalan izin ekranı."""
    from app.services import google_client as g
    assert "7 gün" in g._YETKI_METNI and "Yeniden bağlan" in g._YETKI_METNI
