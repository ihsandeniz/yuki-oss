"""Yedekleme — testlerin kaçırdığı iki sessiz kusur (2026-11-10 gizli hata turu).

① WAL'daki yazı ana `.db` dosyasının boyut/mtime'ını değiştirmez → hızlı eleme
   veritabanını "değişmedi" sayar, yeni satırlar hiç yedeğe girmez.
② Kullanıcı Drive'da yedeklenmiş bir dosyayı ya da alt klasörü silerse saklı kimlik
   ölür → PATCH/POST 404 alır, tur düşer ve dosya her gün değiştiği için YEDEK
   KALICI OLARAK durur (kendini onaramaz).
"""

import asyncio
import importlib
import sqlite3
from pathlib import Path

import pytest

from app.services import google_client as _gc


class SahteDrive:
    def __init__(self):
        self.yuklemeler = []        # (ad, ebeveyn, dosya_id, icerik)
        self.klasorler = {}
        self.dosyalar = set()
        self.olu = set()            # kullanıcının Drive'da sildiği kimlikler
        self._n = 0

    async def klasor_al_veya_olustur(self, ad, ebeveyn_id=None):
        k = f"{ebeveyn_id or 'kok'}/{ad}"
        if k not in self.klasorler or self.klasorler[k] in self.olu:
            self._n += 1
            self.klasorler[k] = f"k{self._n}"
        return self.klasorler[k]

    async def klasor_gecerli_mi(self, i):
        return i in self.klasorler.values() and i not in self.olu

    async def dosya_yukle(self, yol, ad, ebeveyn, dosya_id=None):
        if ebeveyn in self.olu or (dosya_id and (dosya_id in self.olu or dosya_id not in self.dosyalar)):
            raise _gc.DriveHatasi("bulunamadı", "bulunamadi", '{"error":{"code":404}}')
        self._n += 1
        yeni = dosya_id or f"d{self._n}"
        self.dosyalar.add(yeni)
        self.yuklemeler.append((ad, ebeveyn, dosya_id, Path(yol).read_bytes()))
        return {"id": yeni}


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
    a = y.ayarlar()
    a.update({"acik": True, "yuki_verisi": False})
    y.ayar_yaz(a)
    y.kaynak_ekle(str(kay))
    return y, d, kay


def test_WAL_deki_yeni_satir_ikinci_turda_YEDEGE_GIRER(ortam, tmp_path):
    y, d, kay = ortam
    db = kay / "hafiza.db"
    c = sqlite3.connect(db)
    c.execute("PRAGMA journal_mode=WAL")
    c.execute("PRAGMA wal_autocheckpoint=0")     # canlı uygulama: checkpoint ara sıra olur
    c.execute("CREATE TABLE t (x TEXT)")
    c.execute("INSERT INTO t VALUES ('ilk')")
    c.commit()
    try:
        r1 = asyncio.run(y.tur_calistir())
        assert r1["hata"] is None and r1["yuklenen"] == 1

        c.execute("INSERT INTO t VALUES ('ikinci')")
        c.commit()
        d.yuklemeler.clear()
        r2 = asyncio.run(y.tur_calistir())
        gonderilen = [i for a, _, _, i in d.yuklemeler if a == "hafiza.db"]
        assert gonderilen, f"WAL'daki yeni satır yedeğe hiç gitmedi (rapor: atlanan={r2['atlanan']})"
        kopya = tmp_path / "geri.db"
        kopya.write_bytes(gonderilen[-1])
        k = sqlite3.connect(kopya)
        try:
            assert [r[0] for r in k.execute("SELECT x FROM t ORDER BY rowid")] == ["ilk", "ikinci"]
        finally:
            k.close()
    finally:
        c.close()


def test_WAL_degismediyse_db_yine_HASHLENMEZ(ortam, monkeypatch):
    """Düzeltme hızlı elemeyi öldürmesin: değişmeyen WAL'lı db her turda anlık görüntü almaz."""
    y, d, kay = ortam
    db = kay / "hafiza.db"
    c = sqlite3.connect(db)
    c.execute("PRAGMA journal_mode=WAL")
    c.execute("PRAGMA wal_autocheckpoint=0")
    c.execute("CREATE TABLE t (x TEXT)")
    c.execute("INSERT INTO t VALUES ('ilk')")
    c.commit()
    try:
        asyncio.run(y.tur_calistir())
        sayac = {"n": 0}
        gercek = y._sqlite_anlik
        monkeypatch.setattr(y, "_sqlite_anlik", lambda p: (sayac.__setitem__("n", sayac["n"] + 1), gercek(p))[1])
        r = asyncio.run(y.tur_calistir())
        assert sayac["n"] == 0 and r["atlanan"] == 1
    finally:
        c.close()


def test_Drivedan_SILINEN_dosya_yedegi_kalici_dusurmez_yeniden_olusturulur(ortam):
    y, d, kay = ortam
    f = kay / "notlar.txt"
    f.write_text("v1")
    asyncio.run(y.tur_calistir())
    eski_id = next(iter(d.dosyalar))
    d.olu.add(eski_id)                       # kullanıcı Drive'da sildi (çöpü boşalttı)

    f.write_text("v2 — daha uzun içerik")
    r = asyncio.run(y.tur_calistir())
    assert r["hata"] is None, f"tur düştü: {r['hata']} — yedek her gün böyle kalır"
    assert d.yuklemeler[-1][3] == "v2 — daha uzun içerik".encode()
    yeni_id = y.indeks_oku(y.ayarlar()["kaynaklar"][0]["id"])["notlar.txt"]["drive_id"]
    assert yeni_id != eski_id


def test_Drivedan_SILINEN_alt_klasor_yedegi_kalici_dusurmez(ortam):
    y, d, kay = ortam
    (kay / "alt").mkdir()
    (kay / "alt" / "a.txt").write_text("a")
    asyncio.run(y.tur_calistir())
    alt_id = y.indeks_oku(y.ayarlar()["kaynaklar"][0]["id"])["#dizin:alt"]["drive_id"]
    d.olu.add(alt_id)                        # alt klasör Drive'da silindi (içindeki dosyayla)
    d.olu.update(d.dosyalar)

    (kay / "alt" / "b.txt").write_text("b")
    (kay / "alt" / "a.txt").write_text("a2")
    r = asyncio.run(y.tur_calistir())
    assert r["hata"] is None, f"tur düştü: {r['hata']}"
    adlar = sorted(a for a, *_ in d.yuklemeler[1:])
    assert adlar == ["a.txt", "b.txt"], adlar
    yeni_alt = y.indeks_oku(y.ayarlar()["kaynaklar"][0]["id"])["#dizin:alt"]["drive_id"]
    assert yeni_alt != alt_id


def test_Drive_404_ONARILABILIR_etiket_tasir_digeri_degil():
    import httpx
    istek = httpx.Request("PATCH", "https://x")
    with pytest.raises(_gc.DriveHatasi) as e:
        _gc._drive_hatasi(httpx.Response(404, text='{"error":"notFound"}', request=istek))
    assert e.value.tur == "bulunamadi"
    with pytest.raises(_gc.DriveHatasi) as e:
        _gc._drive_hatasi(httpx.Response(500, text="x", request=istek))
    assert e.value.tur == "hata"
