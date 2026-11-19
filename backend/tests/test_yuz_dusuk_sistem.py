"""Düşük donanımlı makinelerde yüz tanımanın yükü — ipek kararı 2026-09-06.

📏 **Ölçüm (2026-09-06, 12 çekirdek / 31 GB):** buffalo_l'ın tamamı yüklenince
backend **1,73 GB RSS** tutuyor (1,67 GB'ı private dirty) ve **78 iş parçacığı**
açılıyor. ONNX ağırlıkları 327 MB:

    w600k_r50 167 · 1k3d68 137 · det_10g 17 · 2d106det 4,9 · genderage 1,3 MB

Bunun 138 MB'ı tanıma için gerekmiyor: `genderage` hiçbir yerde okunmuyor,
`1k3d68` yalnız göz açıklığının poz düzeltmesini besliyor.

Bu dosya üç kapıyı korur:
  ① Kullanılmayan modeller listeye geri sızmasın (eski hâl `allowed_modules=None`
    ile **hepsini** yüklüyordu — "ne olur ne olmaz" değildi, bilinçliydi, ama
    gerekçesi *"kazancı ölçülmedi"*ydi. Ölçüldü.)
  ② ONNX iş parçacığı tavanı sessizce kaybolmasın — yama insightface'in
    **iç** yapısına dayanıyor (`sess_options` API'den geçmiyor), kütüphane
    sürümü değişince ilk kırılacak yer burası.
  ③ Yama **kalıcı global** hâline gelmesin.

⚠️ `det_size=640` bilerek ELLENMEDİ: `FACE_RECOGNITION_THRESHOLD=0.45` o boyutta
kalibre; küçültmek eşiği sessizce geçersizleştirir (bkz. havuz modülü başlığı).
"""

import sys
import types

import pytest

from app.services import insightface_havuzu as havuz


# ── ① Modül listesi ────────────────────────────────────────────────────────

def test_kullanilmayan_modeller_temel_listede_yok():
    """`genderage` okunmuyor, `landmark_3d_68` koşullu — ikisi de temelde olmamalı."""
    assert "genderage" not in havuz.TEMEL_MODULLER
    assert havuz.POZ_MODULU not in havuz.TEMEL_MODULLER


def test_temel_moduller_tanima_ve_canliligi_kapsar():
    """Daraltma fazla ileri gitmemeli: bu üçü olmadan özellik ÇALIŞMAZ.

    `detection` yüzü bulur, `recognition` embedding üretir (tanımanın kendisi),
    `landmark_2d_106` göz kapağı noktalarını verir (göz kırpma = canlılık).
    Biri düşerse yüzle giriş sessizce ölür.
    """
    assert set(havuz.TEMEL_MODULLER) == {"detection", "recognition", "landmark_2d_106"}


def test_modul_adlari_insightface_taskname_yazimiyla_ayni():
    """Adlar `model_zoo/*.py::taskname` ile birebir olmalı.

    🔑 Yanlış yazılmış bir ad hata vermez — insightface o modülü sessizce
    ATLAR (`face_analysis.py:52` `model ignore:` basar) ve özellik çalışmaz.
    Bu yüzden ad denetimi teste bağlandı.
    """
    for ad in (*havuz.TEMEL_MODULLER, havuz.POZ_MODULU):
        assert ad.islower() and " " not in ad
    # 'landmark_%dd_%d' % (3, 68) biçimi — kaynaktan okundu
    assert havuz.POZ_MODULU == "landmark_3d_68"


# ── ② Poz düzeltmesi kararı ────────────────────────────────────────────────

@pytest.fixture
def cfg(monkeypatch):
    """`app.config`'i tekil olarak yamalamak için kısayol."""
    from app import config

    def ayarla(**kw):
        for k, v in kw.items():
            monkeypatch.setattr(config, k, v, raising=False)

    return ayarla


def test_poz_true_ise_her_zaman_acik(cfg, monkeypatch):
    cfg(FACE_POSE_CORRECTION="true", FACE_LOW_MEMORY_GB=8.0)
    monkeypatch.setattr(havuz, "toplam_ram_gb", lambda: 2.0)  # çok düşük RAM
    assert havuz.poz_duzeltmesi_acik() is True


def test_poz_false_ise_her_zaman_kapali(cfg, monkeypatch):
    cfg(FACE_POSE_CORRECTION="false", FACE_LOW_MEMORY_GB=8.0)
    monkeypatch.setattr(havuz, "toplam_ram_gb", lambda: 64.0)  # bol RAM
    assert havuz.poz_duzeltmesi_acik() is False


def test_auto_dusuk_ramde_kapanir(cfg, monkeypatch):
    cfg(FACE_POSE_CORRECTION="auto", FACE_LOW_MEMORY_GB=8.0)
    monkeypatch.setattr(havuz, "toplam_ram_gb", lambda: 4.0)
    assert havuz.poz_duzeltmesi_acik() is False


def test_auto_yuksek_ramde_acik_kalir(cfg, monkeypatch):
    cfg(FACE_POSE_CORRECTION="auto", FACE_LOW_MEMORY_GB=8.0)
    monkeypatch.setattr(havuz, "toplam_ram_gb", lambda: 16.0)
    assert havuz.poz_duzeltmesi_acik() is True


def test_esik_degerinde_acik_kalir(cfg, monkeypatch):
    """Tam eşikteki makine "düşük" sayılmamalı — sınır `>=`, kapsayıcı."""
    cfg(FACE_POSE_CORRECTION="auto", FACE_LOW_MEMORY_GB=8.0)
    monkeypatch.setattr(havuz, "toplam_ram_gb", lambda: 8.0)
    assert havuz.poz_duzeltmesi_acik() is True


def test_ram_olculemezse_dogruluk_korunur(cfg, monkeypatch):
    """🔑 Asimetri kararı: bilinmiyorken doğruluğu koru.

    Yanlışlıkla "düşük" sayarsak güçlü makinede canlılık sessizce zayıflar
    (görünmez hata). Yanlışlıkla "yüksek" sayarsak 137 MB fazla kullanılır
    (görünür ve `.env` ile geri alınabilir).
    """
    cfg(FACE_POSE_CORRECTION="auto", FACE_LOW_MEMORY_GB=8.0)
    monkeypatch.setattr(havuz, "toplam_ram_gb", lambda: None)
    assert havuz.poz_duzeltmesi_acik() is True


def test_gecersiz_deger_auto_gibi_davranir(cfg, monkeypatch):
    """Yazım hatası özelliği kapatmamalı; uyarır ve `auto`ya düşer."""
    cfg(FACE_POSE_CORRECTION="evet", FACE_LOW_MEMORY_GB=8.0)
    monkeypatch.setattr(havuz, "toplam_ram_gb", lambda: 4.0)
    assert havuz.poz_duzeltmesi_acik() is False  # auto + düşük RAM


def test_toplam_ram_bu_makinede_olculebiliyor():
    """Sahte değil gerçek ölçüm: `psutil` kutuda var, yol çalışmalı."""
    ram = havuz.toplam_ram_gb()
    assert ram is not None and 0.5 < ram < 10_000


# ── ③ ONNX iş parçacığı tavanı ─────────────────────────────────────────────

def test_acik_ayar_otomatigi_ezer(cfg):
    cfg(FACE_ORT_THREADS=2)
    assert havuz._ort_thread_sayisi() == 2


def test_sifir_ayar_otomatige_duser(cfg):
    cfg(FACE_ORT_THREADS=0)
    n = havuz._ort_thread_sayisi()
    assert 1 <= n <= 4  # min(4, çekirdek)


def test_otomatik_deger_asla_sifir_olmaz(cfg, monkeypatch):
    """`os.cpu_count()` `None` dönebilir; 0 thread onnxruntime'da "sınırsız" demek
    — yani tam kaçındığımız davranışa geri döneriz."""
    cfg(FACE_ORT_THREADS=0)
    monkeypatch.setattr(havuz.os, "cpu_count", lambda: None)
    assert havuz._ort_thread_sayisi() >= 1


def _sahte_insightface(monkeypatch):
    """`insightface.model_zoo.model_zoo` sahtesini `sys.modules`'a koyar.

    Gerçek kütüphane test ortamında YOK (pydeps ile sonradan iniyor), ama
    yamanın kendisi onun iç yapısına dayanıyor — sahtesiyle de olsa ölçülmeli.
    """
    class SahteSession:
        def __init__(self, model_path, **kw):
            self.model_path = model_path
            self.kw = kw

    mz = types.ModuleType("insightface.model_zoo.model_zoo")
    mz.PickableInferenceSession = SahteSession
    paket_mz = types.ModuleType("insightface.model_zoo")
    paket_mz.model_zoo = mz
    kok = types.ModuleType("insightface")
    kok.model_zoo = paket_mz
    monkeypatch.setitem(sys.modules, "insightface", kok)
    monkeypatch.setitem(sys.modules, "insightface.model_zoo", paket_mz)
    monkeypatch.setitem(sys.modules, "insightface.model_zoo.model_zoo", mz)
    return mz, SahteSession


def test_yama_sess_options_enjekte_eder(cfg, monkeypatch):
    cfg(FACE_ORT_THREADS=3)
    mz, _ = _sahte_insightface(monkeypatch)
    with havuz._sinirli_oturumlar():
        oturum = mz.PickableInferenceSession("model.onnx")
    so = oturum.kw["sess_options"]
    assert so.intra_op_num_threads == 3
    # inter_op 1: paralel modda ikinci bir havuz açılmasın
    assert so.inter_op_num_threads == 1


def test_yama_cikista_geri_alinir(cfg, monkeypatch):
    """🔑 Kalıcı global yama, aynı süreçte insightface kuran başka kodun
    ayarlarını sessizce ezerdi."""
    cfg(FACE_ORT_THREADS=2)
    mz, asil = _sahte_insightface(monkeypatch)
    with havuz._sinirli_oturumlar():
        assert mz.PickableInferenceSession is not asil
    assert mz.PickableInferenceSession is asil


def test_yama_istisnada_da_geri_alinir(cfg, monkeypatch):
    cfg(FACE_ORT_THREADS=2)
    mz, asil = _sahte_insightface(monkeypatch)
    with pytest.raises(RuntimeError):
        with havuz._sinirli_oturumlar():
            raise RuntimeError("model yüklenemedi")
    assert mz.PickableInferenceSession is asil


def test_yama_verilmis_sess_options_ezmez(cfg, monkeypatch):
    """Çağıran kendi seçeneğini verdiyse ona dokunulmaz."""
    import onnxruntime

    cfg(FACE_ORT_THREADS=3)
    mz, _ = _sahte_insightface(monkeypatch)
    benim = onnxruntime.SessionOptions()
    benim.intra_op_num_threads = 7
    with havuz._sinirli_oturumlar():
        oturum = mz.PickableInferenceSession("m.onnx", sess_options=benim)
    assert oturum.kw["sess_options"].intra_op_num_threads == 7


def test_insightface_yoksa_yama_patlamaz(cfg, monkeypatch):
    """Kütüphane henüz inmemişken de blok çalışabilmeli — `al()` zaten
    `KutuphaneYok` ile kendi hatasını verecek, yama onun önüne geçmemeli."""
    cfg(FACE_ORT_THREADS=2)
    monkeypatch.setitem(sys.modules, "insightface", None)
    with havuz._sinirli_oturumlar():
        pass  # istisna atmamalı


# ── ④ Boşta modeli düşürme ─────────────────────────────────────────────────

@pytest.fixture(autouse=True)
def _havuzu_temizle():
    """Her test kendi durumuyla başlasın — `_ornekler` modül düzeyinde global."""
    yield
    havuz._ornekler.clear()
    havuz._son_kullanim.clear()
    havuz._bekci = None


def test_coz_son_kullanim_damgasi_basar(monkeypatch):
    class SahteApp:
        def get(self, kare):
            return ["yuz"]

    monkeypatch.setattr(havuz, "al", lambda profil: SahteApp())
    havuz._son_kullanim.clear()
    assert havuz.coz("TANIMA", object()) == ["yuz"]
    assert "TANIMA" in havuz._son_kullanim


def test_coz_hata_atsa_da_damga_basilir(monkeypatch):
    """Damga `finally`'de: patlayan bir analiz modeli "hiç kullanılmamış"
    göstermemeli, yoksa bekçi çalışan bir oturumun altından modeli çeker."""
    class PatlayanApp:
        def get(self, kare):
            raise ValueError("bozuk kare")

    monkeypatch.setattr(havuz, "al", lambda profil: PatlayanApp())
    havuz._son_kullanim.clear()
    with pytest.raises(ValueError):
        havuz.coz("TANIMA", object())
    assert "TANIMA" in havuz._son_kullanim


def test_sifir_dakika_bekciyi_hic_kurmaz(cfg):
    """Kapalıyken boşuna uyanan bir iş parçacığı olmamalı."""
    cfg(FACE_IDLE_UNLOAD_MIN=0)
    havuz._bekci = None
    havuz._bosta_bekcisini_baslat()
    assert havuz._bekci is None


def test_bekci_bir_kez_kurulur(cfg):
    cfg(FACE_IDLE_UNLOAD_MIN=10)
    havuz._bekci = None
    havuz._bosta_bekcisini_baslat()
    ilk = havuz._bekci
    assert ilk is not None and ilk.daemon  # daemon: kapanışı bloklamasın
    havuz._bosta_bekcisini_baslat()
    assert havuz._bekci is ilk


def test_unut_damgalari_da_temizler():
    """Damga kalsaydı model düşmüşken "yakında kullanıldı" görünürdü."""
    havuz._ornekler["TANIMA"] = object()
    havuz._son_kullanim["TANIMA"] = 1.0
    havuz.unut()
    assert not havuz._ornekler and not havuz._son_kullanim
