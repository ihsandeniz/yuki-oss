"""Yedekleme MOTORU — yarıda kalan tur, tavan, kayıp klasör, hata dili ( panel 12).

Hepsi sahte Drive ile; her test bir kusuru ÖLÇER ve mutasyonla kırmızıya döndüğü görüldü:
· indeks yalnız kaynak sonunda yazılırsa → `test_yarida_kesilen_tur_*`
· `finally` kalkarsa → `test_istisnayla_cikan_tur_indeksi_yazar`
· hızlı elemeden önce tavan denetimi → `test_tavan_sonrasi_degismeyen_dosya_*`
"""

import asyncio
import importlib
from pathlib import Path

import httpx
import pytest


class SahteDrive:
    def __init__(self):
        self.yuklemeler = []        # (ad, dosya_id)
        self.klasorler = {}
        self._n = 0
        self.patla = {}             # dosya adı -> istisna
        self.gozlem = None          # her yüklemede çağrılır (diskteki indeksi gözlemlemek için)

    async def klasor_al_veya_olustur(self, ad, ebeveyn_id=None):
        k = f"{ebeveyn_id or 'kok'}/{ad}"
        if k not in self.klasorler:
            self._n += 1
            self.klasorler[k] = f"k{self._n}"
        return self.klasorler[k]

    async def klasor_gecerli_mi(self, i):
        return i in self.klasorler.values()

    async def dosya_yukle(self, yol, ad, e, dosya_id=None):
        if self.gozlem:
            self.gozlem()
        if ad in self.patla:
            raise self.patla[ad]
        self._n += 1
        self.yuklemeler.append((ad, dosya_id))
        return {"id": dosya_id or f"d{self._n}"}


@pytest.fixture
def ortam(tmp_path, monkeypatch):
    monkeypatch.setenv("YUKI_DATA_DIR", str(tmp_path / "veri"))
    from app.services import yedekleme as y
    y = importlib.reload(y)
    d = SahteDrive()
    for a in ("klasor_al_veya_olustur", "klasor_gecerli_mi", "dosya_yukle"):
        monkeypatch.setattr(y._g, a, getattr(d, a))
    kay = tmp_path / "belgeler"
    kay.mkdir()
    return y, d, kay


def _kur(y, *klasorler, **ayar):
    a = y.ayarlar()
    a.update({"acik": True, "yuki_verisi": False})
    a.update(ayar)
    y.ayar_yaz(a)
    for k in klasorler:
        y.kaynak_ekle(str(k))


def _dosyalar(kay, adlar="a.txt b.txt c.txt d.txt"):
    for ad in adlar.split():
        (kay / ad).write_text(ad)


def _idx(y):
    return y.indeks_oku(y.ayarlar()["kaynaklar"][0]["id"])


def _dosya_sayisi(idx):
    return len([k for k in idx if not k.startswith("#")])


# ── 1. Yarıda kalan tur: indeks kaybolmaz, ikinci tur kopya üretmez ──────────

def test_yarida_kesilen_tur_yuklenenleri_UNUTMAZ_ikinci_tur_yalniz_kalani_yukler(ortam):
    y, d, kay = ortam
    _dosyalar(kay)
    _kur(y, kay)
    d.patla["c.txt"] = RuntimeError("Drive dolu")

    r1 = asyncio.run(y.tur_calistir())
    assert r1["hata"] and r1["yuklenen"] == 2
    assert _dosya_sayisi(_idx(y)) == 2, "yüklenen 2 dosya diske yazılmadı — sonraki tur kopya üretir"

    d.patla.clear()
    d.yuklemeler.clear()
    r2 = asyncio.run(y.tur_calistir())
    assert sorted(d.yuklemeler) == [("c.txt", None), ("d.txt", None)], d.yuklemeler
    assert r2["hata"] is None and r2["yuklenen"] == 2


def test_istisnayla_cikan_tur_indeksi_yazar_ara_kayit_olmasa_bile(ortam, monkeypatch):
    """`finally`'nin kendi ölçüsü: ara kayıt devre dışı (aralık sonsuz), yine de kaydolmalı."""
    y, d, kay = ortam
    monkeypatch.setattr(y, "_INDEKS_ARALIK", 10_000)
    monkeypatch.setattr(y, "_INDEKS_SANIYE", 10_000.0)
    _dosyalar(kay)
    _kur(y, kay)
    d.patla["d.txt"] = RuntimeError("ag kesildi")
    asyncio.run(y.tur_calistir())
    assert _dosya_sayisi(_idx(y)) == 3


def test_ara_kayit_tur_SURERKEN_diske_iner(ortam, monkeypatch):
    """Uygulama turun ortasında öldürülürse `finally` da çalışmaz — kayıt ARADA yazılmış olmalı."""
    y, d, kay = ortam
    monkeypatch.setattr(y, "_INDEKS_ARALIK", 1)
    _dosyalar(kay)
    _kur(y, kay)
    gorulen = []
    d.gozlem = lambda: gorulen.append(_dosya_sayisi(_idx(y)))
    asyncio.run(y.tur_calistir())
    assert gorulen == [0, 1, 2, 3], gorulen        # her yüklemeden ÖNCE bir öncekiler diskte


def test_yarida_kesilen_tur_var_olan_dosyayi_kaynakta_yok_DAMGALAMAZ(ortam):
    y, d, kay = ortam
    _dosyalar(kay)
    _kur(y, kay)
    asyncio.run(y.tur_calistir())                   # 4 dosya yedekte
    (kay / "a.txt").write_text("degisti")           # bir dosya değişti → ikinci tur onu yükleyecek
    d.patla["a.txt"] = RuntimeError("ag kesildi")
    asyncio.run(y.tur_calistir())
    ik = _idx(y)
    assert not any(v.get("kaynakta_yok") for k, v in ik.items() if not k.startswith("#")), \
        "yarım taramanın eksik kümesiyle var olan dosyalar 'kaynakta yok' damgalandı"


# ── 2. Tavan: "başarılı" bitmek "hepsi yedekte" değil ────────────────────────

def _buyuk(kay, n=3):
    for i in range(n):
        (kay / f"f{i}.bin").write_bytes(bytes([i]) * 600_000)


def test_tur_tavani_dolunca_rapor_TAM_degil_der_hata_degil(ortam):
    y, d, kay = ortam
    _buyuk(kay)
    _kur(y, kay, tur_bayt_tavani_mb=1)
    r = asyncio.run(y.tur_calistir())
    assert r["hata"] is None and r["yuklenen"] == 2
    assert r["tavan_doldu"] is True and r["tam"] is False and r["tavan_atlanan"] == 1
    assert r["kaynaklar"][0]["durum"] == "yarim" and r["kaynaklar"][0]["tavan_atlanan"] == 1
    assert y.durum()["kaynaklar"][0]["son_yedek"] is None, "yarım tarama 'son tam yedek' sayılmamalı"


def test_tavan_sonrasi_degismeyen_dosya_tavan_atlananina_SAYILMAZ(ortam):
    y, d, kay = ortam
    (kay / "a.bin").write_bytes(b"a" * 100)
    (kay / "b.txt").write_text("b")
    (kay / "c.txt").write_text("c")
    _kur(y, kay)
    asyncio.run(y.tur_calistir())                   # hepsi yedekte
    (kay / "a.bin").write_bytes(b"A" * 1_200_000)   # yalnız a değişti ve tek başına tavanı (1 MB) aşıyor
    a = y.ayarlar(); a["tur_bayt_tavani_mb"] = 1; y.ayar_yaz(a)
    r = asyncio.run(y.tur_calistir())               # a gider, SONRA gelen b/c DEĞİŞMEDİ
    assert r["yuklenen"] == 0 and r["guncellenen"] == 1
    assert r["tam"] is True and not r.get("tavan_doldu"), \
        "değişmemiş dosyalar tavana takılı sayılıyor — panel her gün 'yarım' der"
    assert y.durum()["son_yedek"], "tam tur bitti ama son tam yedek yazılmadı"


# ── 3. Kaynak klasör kayboldu ────────────────────────────────────────────────

def test_kaynak_klasoru_kaybolunca_tur_SOYLER_ve_indekse_dokunmaz(ortam):
    y, d, kay = ortam
    _dosyalar(kay)
    _kur(y, kay)
    asyncio.run(y.tur_calistir())
    import shutil
    shutil.rmtree(kay)
    d.yuklemeler.clear()
    r = asyncio.run(y.tur_calistir())
    assert r["hata"] is None and r["tam"] is False
    assert r["kaynaklar"][0]["durum"] == "yol-yok"
    assert r["kaynakta_yok"] == 0, "klasör takılı değilken dosyalar 'silindi' diye damgalandı"
    k = y.durum()["kaynaklar"][0]
    assert k["yol_var"] is False and k["dosya"] == 4 and k["tur"]["durum"] == "yol-yok"


# ── 4. Hatada her klasörün KENDİ durumu ──────────────────────────────────────

def test_hatada_yarida_kalan_ile_sirasi_gelmeyen_AYRI_durumdur(ortam, tmp_path):
    y, d, kay = ortam
    ikinci = tmp_path / "resimler"
    ikinci.mkdir()
    _dosyalar(kay)
    _dosyalar(ikinci, "x.jpg")
    _kur(y, kay, ikinci)
    d.patla["c.txt"] = RuntimeError("Drive dolu")
    r = asyncio.run(y.tur_calistir())
    assert [k["durum"] for k in r["kaynaklar"]] == ["yarida", "sira-gelmedi"]
    assert r["kaynaklar"][0]["yuklenen"] == 2 and r["tam"] is False


def test_baska_klasor_tamamlandiysa_hata_sonrasi_TAMAM_kalir(ortam, tmp_path):
    y, d, kay = ortam
    ikinci = tmp_path / "resimler"
    ikinci.mkdir()
    _dosyalar(kay, "a.txt")
    _dosyalar(ikinci, "x.jpg")
    _kur(y, kay, ikinci)
    d.patla["x.jpg"] = RuntimeError("ag")
    r = asyncio.run(y.tur_calistir())
    assert [k["durum"] for k in r["kaynaklar"]] == ["tamam", "yarida"]
    assert y.durum()["kaynaklar"][0]["son_yedek"], "tamamlanan klasörün son yedeği yazılmadı"


# ── 5. Hata dili ─────────────────────────────────────────────────────────────

def test_ag_hatasi_HAM_istisnayi_musteri_cumlesine_koymaz(ortam):
    y, d, kay = ortam
    _dosyalar(kay, "a.txt")
    _kur(y, kay)
    d.patla["a.txt"] = httpx.RemoteProtocolError("Server disconnected without sending a response")
    r = asyncio.run(y.tur_calistir())
    assert r["hata_tur"] == "ag"
    assert "Server disconnected" not in r["hata"] and "Server disconnected" in r["teknik"]


def _yanit(kod, govde):
    return httpx.Response(kod, text=govde, request=httpx.Request("GET", "https://x"))


def test_drive_API_kapali_403_ozel_cumle_alir_ham_JSON_almaz(ortam):
    y, d, kay = ortam
    from app.services import google_client as g
    _dosyalar(kay, "a.txt")
    _kur(y, kay)
    ham = '{"error":{"errors":[{"reason":"accessNotConfigured"}],"message":"Drive API has not been used in project 123"}}'
    with pytest.raises(g.DriveHatasi) as e:
        g._drive_hatasi(_yanit(403, ham))
    assert e.value.tur == "api-kapali"
    d.patla["a.txt"] = e.value
    r = asyncio.run(y.tur_calistir())
    assert r["hata_tur"] == "api-kapali" and "accessNotConfigured" not in r["hata"] and "Drive API" in r["hata"]
    assert "accessNotConfigured" in r["teknik"]


def test_drive_dolu_ayri_etiket_ve_beklenmeyen_5xx_ham_govdeyi_gizler(ortam):
    y, d, kay = ortam
    from app.services import google_client as g
    _dosyalar(kay, "a.txt b.txt")
    _kur(y, kay)
    with pytest.raises(g.DriveHatasi) as dolu:
        g._drive_hatasi(_yanit(403, '{"reason":"storageQuotaExceeded"}'))
    d.patla["a.txt"] = dolu.value
    assert asyncio.run(y.tur_calistir())["hata_tur"] == "dolu"

    with pytest.raises(g.DriveHatasi) as bes:
        g._drive_hatasi(_yanit(503, '<html>backend error HAM-GOVDE</html>'))
    d.patla["a.txt"] = bes.value
    r = asyncio.run(y.tur_calistir())
    assert r["hata_tur"] == "drive" and "HAM-GOVDE" not in r["hata"] and "HAM-GOVDE" in r["teknik"]


def test_yetki_dustu_ve_bagli_degil_makine_etiketi_tasir(ortam, monkeypatch):
    y, d, kay = ortam
    _dosyalar(kay, "a.txt")
    _kur(y, kay)
    d.patla["a.txt"] = y._g.GoogleYetkiDustu("kopuk")
    assert asyncio.run(y.tur_calistir())["hata_tur"] == "kopuk"
    d.patla["a.txt"] = y._g.GoogleBagliDegil()
    assert asyncio.run(y.tur_calistir())["hata_tur"] == "bagli-degil"


# ── 6. durum() panelin ihtiyacı ──────────────────────────────────────────────

def test_durum_baglanti_Google_durumunu_TOKEN_dosyasindan_ayri_tasir(ortam, monkeypatch):
    y, d, kay = ortam
    monkeypatch.setattr(y._g, "token_var", lambda: True)
    monkeypatch.setattr(y._g, "durum", lambda: {"durum": "kopuk", "sebep": "invalid_grant", "son_deneme": None})
    b = y.durum()["baglanti"]
    assert b["token"] is True and b["durum"] == "kopuk" and b["sebep"] == "invalid_grant"


def test_durum_tavanlari_ve_zamanlamanin_KURULU_olup_olmadigini_soyler(ortam, monkeypatch):
    y, d, kay = ortam
    _kur(y, kay, zamanlama="03:30", tek_dosya_tavani_mb=50)
    from app.services import scheduler
    monkeypatch.setattr(scheduler, "SCHEDULER_ENABLED", False)
    du = y.durum()
    assert du["tavanlar"] == {"tek_dosya_mb": 50, "tur_mb": 2048}
    assert du["zamanlama"] == "03:30" and du["zamanlama_bilgi"]["kurulu"] is False, \
        "iş kurulu değilken 'kuruldu' denir"


def test_kapaliyken_kayitli_saat_KURULU_degildir(ortam):
    y, d, kay = ortam
    a = y.ayarlar(); a.update({"acik": False, "zamanlama": "03:30"}); y.ayar_yaz(a)
    assert y.durum()["zamanlama_bilgi"] == {"kurulu": False, "sonraki": None}


def test_calisirken_canli_sayac_ve_kaynak_durumu_okunur(ortam):
    y, d, kay = ortam
    _dosyalar(kay)
    _kur(y, kay)
    goruldu = []
    import copy
    d.gozlem = lambda: goruldu.append(copy.deepcopy(y.durum()))
    asyncio.run(y.tur_calistir())
    son = goruldu[-1]
    assert son["calisiyor"] is True and son["canli"]["yuklenen"] == 3
    assert son["kaynaklar"][0]["canli"]["durum"] == "suruyor"
    assert y.durum()["canli"] is None


# ── 7. Uç + zamanlayıcı ──────────────────────────────────────────────────────

def test_drive_kullanim_Google_dususunde_409_dur_401_DEGIL(monkeypatch):
    """401 = uygulamanın kendi oturum kilidi; panel o kodla 'oturum kilitli' der."""
    from fastapi import HTTPException
    from app.api import yedekleme as api
    from app.services import google_client as g

    async def dus():
        raise g.GoogleYetkiDustu("kopuk")
    monkeypatch.setattr(g, "kullanim", dus)
    with pytest.raises(HTTPException) as e:
        asyncio.run(api.drive_kullanim.__wrapped__(None))
    assert e.value.status_code == 409


def test_zamanlanmis_is_kacirilirsa_GEC_de_kosar(ortam, monkeypatch):
    y, d, kay = ortam
    from app.services import scheduler
    isler = {}
    sahte = type("S", (), {"get_job": lambda s, i: isler.get(i),
                           "add_job": lambda s, f, **kw: isler.__setitem__(kw["id"], kw),
                           "remove_job": lambda s, i: isler.pop(i, None)})()
    monkeypatch.setattr(scheduler, "get_scheduler", lambda: sahte)
    monkeypatch.setattr(scheduler, "SCHEDULER_ENABLED", True)
    a = y.ayarlar(); a.update({"acik": True, "zamanlama": "03:30"}); y.ayar_yaz(a)
    scheduler.yedekleme_isini_kur()
    assert isler["drive_yedekleme"]["misfire_grace_time"] >= 3600
