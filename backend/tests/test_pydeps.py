"""İndirilen Python paket ağaçlarının `sys.path`'e bağlanması.

🔑 NEDEN VAR ( Dalga 2 FAZ 3): yüz tanıma kütüphanesi pakete girmiyor,
talep üzerine iniyor. Electron indirilen ağacın yolunu `YUKI_PYDEPS` ile geçiyor,
`app/pydeps.py` bağlıyor.

Testlerin ağırlığı üç yerde — üçü de "sessiz yanlış" üretebilecek yerler:
  ① SIRA — ağaç `sys.path`'in SONUNA eklenmeli. Başa eklenirse indirilen
    numpy/onnxruntime kutununkini gölgeler ve hata çok sonra, anlaşılmaz
    bir yerde çıkar (ledger'daki `~/.local` tuzağının aynısı).
  ② DAYANIKLILIK — bozuk/eksik ortam değişkeni AÇILIŞI ENGELLEMEMELİ.
    Bu kod `app/__init__.py`'den çalışır; yükseltirse ürün hiç açılmaz.
  ③ DÜRÜSTLÜK — "kütüphane yok" bilgisi hata koduyla değil VERİ olarak
    verilmeli (`ui/yetenek-sorusu-hata-koduyla-sorulmaz`).
"""
from __future__ import annotations

import os
import sys

import pytest

from app import pydeps


@pytest.fixture(autouse=True)
def _temiz_durum():
    """Her test temiz `sys.path` VE temiz kayıtla başlasın.

    ⚠️ Kayıt sıfırlaması bilerek burada, `kur()` içinde değil: `kur()` çağrılar
    arasında **birikir** (açılışta bağlanamayan, indirmeden sonra bağlanan senaryo
    tek tabloda görünsün diye). Sıfırlama test izolasyonunun işi, üretim kodunun değil.
    """
    onceki = list(sys.path)
    pydeps.kur("", sifirla=True)
    yield
    sys.path[:] = onceki
    pydeps.kur("", sifirla=True)


def _agac(tmp_path, ad: str, dosya: str = "__init__.py"):
    d = tmp_path / ad
    (d / "paketim").mkdir(parents=True)
    (d / "paketim" / dosya).write_text("# test", encoding="utf-8")
    return d


# ── ① SIRA ──────────────────────────────────────────────────────────────────

def test_sona_eklenir_basa_degil(tmp_path):
    d = _agac(tmp_path, "pydeps")
    onceki_uzunluk = len(sys.path)

    eklenen = pydeps.kur(str(d))

    assert eklenen == [str(d.resolve())]
    assert len(sys.path) == onceki_uzunluk + 1
    # 🔑 Kritik iddia: SON eleman. Başa eklenseydi indirilen ağaç kutunun
    # numpy/onnxruntime/opencv sürümünü gölgeler, ürün test edilmemiş bir
    # bağımlılık kümesiyle koşardı.
    assert sys.path[-1] == str(d.resolve()), "sys.path'in SONUNA eklenmedi"


def test_birden_cok_dizin_sirayla(tmp_path):
    a, b = _agac(tmp_path, "a"), _agac(tmp_path, "b")
    eklenen = pydeps.kur(os.pathsep.join([str(a), str(b)]))
    assert eklenen == [str(a.resolve()), str(b.resolve())]
    assert sys.path[-2:] == [str(a.resolve()), str(b.resolve())]


def test_ayni_dizin_iki_kez_eklenmez(tmp_path):
    d = _agac(tmp_path, "pydeps")
    pydeps.kur(str(d))
    n = len(sys.path)
    pydeps.kur(str(d))                       # ikinci çağrı
    assert len(sys.path) == n, "sys.path şişiyor — tekrar eden çağrı biriktiriyor"
    assert any(s == "zaten sys.path'te" for _, s in
               [(a["yol"], a["sebep"]) for a in pydeps.durum()["atlanan"]])


# ── ② DAYANIKLILIK: açılış yolundayız, yükseltmek yasak ────────────────────

@pytest.mark.parametrize("deger", ["", "   ", os.pathsep, os.pathsep * 3])
def test_bos_deger_sorunsuz(deger):
    assert pydeps.kur(deger) == []


def test_olmayan_dizin_atlanir_ve_sebebi_yazilir(tmp_path):
    yok = str(tmp_path / "hic-yok")
    assert pydeps.kur(yok) == []
    atlanan = pydeps.durum()["atlanan"]
    assert len(atlanan) == 1 and "inmemiş" in atlanan[0]["sebep"]


def test_bos_dizin_baglanmaz(tmp_path):
    """Yarım kalmış indirmenin artığı boş dizin — bağlamak 'kurulu' yanılsaması üretir."""
    bos = tmp_path / "bos"
    bos.mkdir()
    assert pydeps.kur(str(bos)) == []
    assert "BOŞ" in pydeps.durum()["atlanan"][0]["sebep"]


def test_dosya_gosterilirse_sebep_DOGRU_olmali(tmp_path):
    """Dosyaya "boş dizin" demek hata ayıklamayı yanlış yere gönderir."""
    f = tmp_path / "bir.txt"
    f.write_text("x", encoding="utf-8")
    assert pydeps.kur(str(f)) == []
    sebep = pydeps.durum()["atlanan"][0]["sebep"]
    assert "dizin değil" in sebep, f"yanlış teşhis: {sebep}"


def test_saglam_ve_bozuk_karisikken_saglam_olan_baglanir(tmp_path):
    """Bir yol bozuk diye diğerleri düşmemeli — kısmi başarı tam başarısızlık değil."""
    iyi = _agac(tmp_path, "iyi")
    bos = tmp_path / "bos"; bos.mkdir()
    eklenen = pydeps.kur(os.pathsep.join([str(tmp_path / "yok"), str(bos), str(iyi)]))
    assert eklenen == [str(iyi.resolve())]
    assert len(pydeps.durum()["atlanan"]) == 2


def test_ortam_degiskeninden_okur(tmp_path, monkeypatch):
    d = _agac(tmp_path, "pydeps")
    monkeypatch.setenv(pydeps.ENV, str(d))
    assert pydeps.kur() == [str(d.resolve())]


# ── ④ DÜŞMANCA TUR (2026-09-05) — ilk turun bakmadığı yerler ───────────────

def test_calisirken_indirilirse_yeniden_baglanabiliyor(tmp_path):
    """Kullanıcı uygulama AÇIKKEN kütüphaneyi indirirse yeniden başlatmak gerekmemeli."""
    hedef = tmp_path / "pydeps" / "face"

    # 1) Açılış: dizin henüz yok
    assert pydeps.kur(str(hedef)) == []
    assert pydeps.kullanilabilir("sonradan_gelen_paket")[0] is False

    # 2) İndirme bitti
    (hedef / "sonradan_gelen_paket").mkdir(parents=True)
    (hedef / "sonradan_gelen_paket" / "__init__.py").write_text("#", encoding="utf-8")

    # 3) Yeniden bağla — yeniden başlatma YOK
    assert pydeps.kur(str(hedef)) == [str(hedef.resolve())]
    try:
        assert pydeps.kullanilabilir("sonradan_gelen_paket")[0] is True
    finally:
        sys.modules.pop("sonradan_gelen_paket", None)


def test_durum_gecmisi_SILMIYOR(tmp_path):
    """Arıza tablosu geçmişi silerse arızayı gizler.

    İlk sürüm her `kur()` çağrısında `durum()`'u sıfırlıyordu: açılışta yazılan
    "dizin yok" kaydı, indirmeden sonraki çağrıda **hiç olmamış** gibi oluyordu.
    """
    hedef = tmp_path / "p"
    pydeps.kur(str(hedef))                      # yok → atlandı
    (hedef / "paketim").mkdir(parents=True)
    (hedef / "paketim" / "__init__.py").write_text("#", encoding="utf-8")
    pydeps.kur(str(hedef))                      # şimdi bağlandı

    d = pydeps.durum()
    assert len(d["baglanan"]) == 1
    assert len(d["atlanan"]) == 1, "ilk çağrının kaydı silindi — arıza geçmişi kayboluyor"


def test_windows_ayraci_sozlesmesi(tmp_path, monkeypatch):
    """Ayraç `os.pathsep` olmalı, sabit ':' DEĞİL.

    Windows'ta ayraç ';' ve yollarda ':' geçer (`C:\\...`). Sabit ':' ile bölen
    bir kod Windows'ta her yolu ikiye keser ve HİÇBİRİ bağlanmaz — Linux'ta
    tamamen sağlıklı görünürken. Electron `path.delimiter` gönderiyor, iki taraf
    aynı sözleşmeye bağlı.
    """
    a, b = _agac(tmp_path, "a"), _agac(tmp_path, "b")
    monkeypatch.setattr(os, "pathsep", ";")
    eklenen = pydeps.kur(f"{a};{b}")
    assert eklenen == [str(a.resolve()), str(b.resolve())], "os.pathsep kullanılmıyor"


def test_ayni_cagride_tekrar_eden_yol_bir_kez_eklenir(tmp_path):
    d = _agac(tmp_path, "p")
    eklenen = pydeps.kur(os.pathsep.join([str(d), str(d)]))
    assert eklenen == [str(d.resolve())]
    assert sys.path.count(str(d.resolve())) == 1


def test_goreli_yol_MUTLAK_hale_getiriliyor(tmp_path, monkeypatch):
    """`sys.path`'te göreli yol tehlikelidir: cwd değişince anlamı değişir."""
    d = _agac(tmp_path, "p")
    monkeypatch.chdir(tmp_path)
    eklenen = pydeps.kur("p")
    assert eklenen == [str(d.resolve())]
    assert os.path.isabs(eklenen[0])


# ── ③ DÜRÜSTLÜK: yetenek sorusu veri olarak sorulur ────────────────────────

def test_kullanilabilir_var_olan_modul():
    ok, sebep = pydeps.kullanilabilir("json", "os")
    assert ok is True and sebep is None


def test_kullanilabilir_eksikte_SEBEP_veriyor():
    ok, sebep = pydeps.kullanilabilir("json", "boyle_bir_modul_yok_12345")
    assert ok is False
    # "False" tek başına arayüze yetmez — kullanıcıya ne söyleyeceğini bilmeli.
    assert "boyle_bir_modul_yok_12345" in sebep
    assert "indirilir" in sebep


def test_kullanilabilir_import_ETMIYOR(tmp_path):
    """Yetenek sorusu 300 MB'lık ağacı belleğe almamalı — yalnız 'var mı' sorulur."""
    d = tmp_path / "p"
    (d / "sondamodul").mkdir(parents=True)
    (d / "sondamodul" / "__init__.py").write_text(
        "raise RuntimeError('import edildi — find_spec kullanılmıyor')", encoding="utf-8")
    pydeps.kur(str(d))
    ok, _ = pydeps.kullanilabilir("sondamodul")
    assert ok is True, "modül bulunamadı — sys.path bağlanmamış"
    assert "sondamodul" not in sys.modules, "modül gerçekten import edildi (yan etki)"


# ── Bağlama gerçekten işe yarıyor mu (uçtan uca) ───────────────────────────

def test_baglanan_agactan_import_edilebiliyor(tmp_path):
    d = tmp_path / "p"
    (d / "gercek_paket").mkdir(parents=True)
    (d / "gercek_paket" / "__init__.py").write_text("DEGER = 42", encoding="utf-8")
    pydeps.kur(str(d))
    import importlib
    m = importlib.import_module("gercek_paket")
    try:
        assert m.DEGER == 42
    finally:
        sys.modules.pop("gercek_paket", None)


def test_app_init_kuru_calistiriyor(tmp_path):
    """`import app` bağlamayı GERÇEKTEN yapıyor mu — yoksa yukarıdakiler boşa.

    ⚠️ İlk sürümü `app/__init__.py`'nin KAYNAĞINDA "kur()" arıyordu ve YANILTICIYDI:
    o metin dosyanın docstring'inde de geçiyor, çağrı silinse bile test yeşil
    kalıyordu (mutasyonla ölçüldü, 2026-09-05). Metin arayan kapı, davranışı
    ölçmez. Artık ayrı bir süreçte gerçekten import edilip `sys.path` okunuyor.
    """
    import subprocess

    d = tmp_path / "p"
    (d / "kanit_paketi").mkdir(parents=True)
    (d / "kanit_paketi" / "__init__.py").write_text("# kanıt", encoding="utf-8")

    backend = __import__("pathlib").Path(__file__).resolve().parents[1]
    ortam = {**os.environ, pydeps.ENV: str(d), "PYTHONPATH": str(backend)}
    p = subprocess.run(
        [sys.executable, "-c",
         "import app, sys, json; print(json.dumps(sys.path))"],
        cwd=str(backend), env=ortam, capture_output=True, text=True,
    )
    assert p.returncode == 0, f"`import app` düştü:\n{p.stderr}"
    yollar = __import__("json").loads(p.stdout.strip().splitlines()[-1])
    assert str(d.resolve()) in yollar, (
        "`import app` YUKI_PYDEPS'i bağlamadı — app/__init__.py kur() çağırmıyor"
    )
    assert yollar[-1] == str(d.resolve()), "bağlandı ama SONA değil"
