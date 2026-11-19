"""InsightFace analizör havuzu — tek kurulum yolu (ürün sürümü).

Kişisel Alice'ten taşındı ( Dalga 2 FAZ 4) ve **daraltıldı**: orada üç profil
vardı (TANIMA · TAKIP · HARITA) çünkü göz takibi ve offline harita üretimi de aynı
modeli kullanıyordu. Üründe o iki yol **yok** — kullanılmayan profil, ilan edilip
uygulanmamış özelliktir; menüde durup hiçbir şey yapmayan seçenekle aynı sınıf.

⚠️ **`det_size=640` keyfi değil:** `FACE_RECOGNITION_THRESHOLD = 0.45` bu boyutta
kalibre edildi. Küçültmek eşiği **sessizce** geçersizleştirir → yanlış kişiyi kabul
etme riski. Değiştirilecekse eşik yeniden ölçülür.

🔌 **Kütüphane pakette YOK** ( kararı B): `insightface` + `onnx` talep üzerine
indirilen `pydeps` ağacından gelir (`app/pydeps.py`). Bu yüzden import **fonksiyon
içinde** yapılır: modül tepesine konsaydı kütüphane inmemişken `app.main`'in import
zinciri kırılır ve **uygulama hiç açılmazdı**.
"""
from __future__ import annotations

import contextlib
import logging
import os
import threading
import time
from pathlib import Path

logger = logging.getLogger(__name__)

#: Yüz tanıma için gereken modüller — `pydeps` inmemişse bunlar bulunamaz.
GEREKEN_MODULLER = ("insightface", "onnx")


def model_koku() -> str:
    """`buffalo_l`'ın indiği/aranacağı kök dizin.

    🔴 **2026-09-06'da ölçülerek bulunan kusur:** `electron/uygulama.js`
    `INSIGHTFACE_HOME` ortam değişkenini set ediyordu ve backlog notu buna
    dayanarak *"model models-cache'e yönlendirilmiş, çift indirme yok"* diyordu.

    **insightface o değişkeni hiç okumuyor.** Kök, `FaceAnalysis.__init__`'in
    `root='~/.insightface'` **varsayılan parametresinden** gelir; paketin tamamı
    tarandı, `INSIGHTFACE_*` diye bir ortam okuması yok. Yani model her zaman
    kullanıcının **ev dizinine** iniyordu.

    Diskteki kanıt (bu makine): `~/.insightface` **601 MB** — açılmış `buffalo_l`
    **ve** silinmemiş `buffalo_l.zip` (289 MB). Kullanıcı tarafında sonucu üç katlı:
      ① model uygulamanın veri klasöründe değil → "modelleri kaldır" onu görmez,
        uygulama silinince 601 MB ev dizininde kalır
      ② kaldırılamayan bir indirme, indirme yöneticisinin muhasebesinin dışında
      ③ bizim katman da indirmeye başlarsa **iki kopya** olur — backlog'un
        "çift indirme yok" dediği durumun tam tersi

    Çözüm ortam değişkenini silmek değil, **kullanmak**: `root` parametresi
    açıkça geçiliyor. Değişken yoksa insightface'in kendi varsayılanına düşülür
    (davranış değişmez).
    """
    ham = os.getenv("INSIGHTFACE_HOME") or ""
    if not ham:
        return "~/.insightface"
    kok = Path(ham).expanduser()
    try:
        kok.mkdir(parents=True, exist_ok=True)
    except OSError as e:
        # Yazılamıyorsa sessizce ev dizinine düş — özelliği tamamen öldürmektense
        # yanlış yere indirmek iyidir; sebebi log'a düşer.
        logger.warning("InsightFace kökü hazırlanamadı (%s): %s — ev dizinine düşülüyor",
                       kok, e)
        return "~/.insightface"
    return str(kok)

#: Yüz tanıma + canlılık için **gerçekten** kullanılan insightface modülleri.
#: Adlar kaynaktan okundu (`model_zoo/{scrfd,arcface_onnx,landmark}.py::taskname`),
#: ezberden yazılmadı — yanlış ad sessizce "o modül hiç yüklenmedi" demek olurdu.
#:   detection       → yüzü bul
#:   recognition     → 512-dim embedding (tanımanın kendisi)
#:   landmark_2d_106 → göz kapağı noktaları → CANLILIK (göz kırpma)
TEMEL_MODULLER = ("detection", "recognition", "landmark_2d_106")

#: Yalnız `face.pose` (pitch/yaw/roll) üretir → göz açıklığının poz düzeltmesi.
#: **137 MB** (`1k3d68.onnx`) — paketteki en büyük ikinci model.
POZ_MODULU = "landmark_3d_68"

#: `genderage` (1,3 MB) hiçbir yerde okunmuyor — listeye bilerek alınmadı.

PROFILLER: dict[str, dict] = {
    "TANIMA": {"det_size": (640, 640), "ctx_id": 0},
}


def toplam_ram_gb() -> float | None:
    """Makinenin toplam RAM'i (GB). Ölçülemezse `None` — **tahmin edilmez**.

    Ölçülemediğinde çağıran "düşük bellek" varsaymaz: yanlış tarafa düşmenin
    bedeli asimetriktir. Yanlışlıkla *düşük* sayarsak güçlü bir makinede
    canlılık doğruluğu sessizce zayıflar; yanlışlıkla *yüksek* sayarsak yalnız
    137 MB fazladan kullanılır. İkincisi görünür ve geri alınabilir.
    """
    try:
        import psutil  # noqa: PLC0415 — pybundle'da var, ama yokluğu ölümcül değil
        return psutil.virtual_memory().total / (1024 ** 3)
    except Exception:  # noqa: BLE001 — psutil yoksa/patlarsa POSIX yoluna düş
        pass
    try:
        return (os.sysconf("SC_PAGE_SIZE") * os.sysconf("SC_PHYS_PAGES")) / (1024 ** 3)
    except (ValueError, OSError, AttributeError):
        # Windows'ta SC_PHYS_PAGES yok. psutil zaten kutuda; ikisi de olmazsa
        # bilinmiyor deriz — uydurmaktansa.
        return None


def poz_duzeltmesi_acik() -> bool:
    """`landmark_3d_68` yüklensin mi? (geliştirici kararı 2026-09-06: "az RAM'de kapat")

    ⚠️ Kapalıyken canlılık **çalışmaya devam eder**: `face_multi_auth.py:100`
    `getattr(face, "pose", None)` ile okur ve `goz_acikligi()` poz almadan da
    ölçer. Kaybedilen tek şey **aşırı** kafa açısındaki düzeltmedir.
    """
    from app import config  # noqa: PLC0415 — döngüsel import kaçınması

    secim = getattr(config, "FACE_POSE_CORRECTION", "auto")
    if secim == "true":
        return True
    if secim == "false":
        return False
    if secim != "auto":
        logger.warning("FACE_POSE_CORRECTION geçersiz (%r) — 'auto' varsayılıyor", secim)

    ram = toplam_ram_gb()
    if ram is None:
        return True  # bilinmiyor → doğruluğu koru (yukarıdaki asimetri notu)
    esik = getattr(config, "FACE_LOW_MEMORY_GB", 8.0)
    return ram >= esik


def _ort_thread_sayisi() -> int:
    """ONNX havuzunun iş parçacığı tavanı. 0/negatif config → otomatik."""
    from app import config  # noqa: PLC0415

    ayar = int(getattr(config, "FACE_ORT_THREADS", 0) or 0)
    if ayar > 0:
        return ayar
    # min(4, çekirdek): 4'ten sonrası bu iş yükünde ölçülebilir kazanç vermiyor
    # ama her model kendi havuzunu açtığı için maliyet modelle ÇARPILIYOR.
    return max(1, min(4, os.cpu_count() or 1))


@contextlib.contextmanager
def _sinirli_oturumlar():
    """`FaceAnalysis` kurulurken ONNX oturumlarına thread tavanı enjekte eder.

    🔑 **Neden yama gerekiyor:** insightface `sess_options`'ı geçirmiyor.
    `FaceAnalysis.__init__` `**kwargs`'ı `model_zoo.get_model`'e devrediyor, o da
    (`model_zoo.py:94-96`) yalnız `providers` ve `provider_options`'ı alıp
    `ModelRouter.get_model`'e veriyor — `sess_options` yolda düşüyor. Oturumu
    gerçekten kuran sınıf `PickableInferenceSession`, ve o modül-global adla
    çağrıldığı için (`model_zoo.py:40`) çağrı anında yamayı görür.

    Yama **kurulum süresince** yaşar ve `finally` ile geri alınır: kalıcı bir
    global yama, aynı süreçte insightface'i başka amaçla kuran bir kodun
    ayarlarını da sessizce ezerdi.

    ⚠️ Ayarlanmazsa onnxruntime'ın varsayılanı *"fiziksel çekirdek sayısı"*dır
    ve bu **her oturum için ayrı** havuz demektir; 12 çekirdekli bu makinede
    ölçülen sonuç 78 iş parçacığıydı.
    """
    n = _ort_thread_sayisi()
    try:
        import onnxruntime  # noqa: PLC0415 — insightface'in zaten sert bağımlılığı
        from insightface.model_zoo import model_zoo as _mz  # noqa: PLC0415
    except ImportError:  # pragma: no cover — kütüphane yoksa al() zaten patlar
        yield
        return

    asil = _mz.PickableInferenceSession

    class _ThreadSinirliSession(asil):  # type: ignore[misc, valid-type]
        def __init__(self, model_path, **kw):
            if "sess_options" not in kw:
                so = onnxruntime.SessionOptions()
                so.intra_op_num_threads = n
                # inter_op yalnız PARALLEL modda anlamlı; varsayılan SEQUENTIAL'da
                # da yazılabilir ve mod sonradan değişirse tavan yerinde olur.
                so.inter_op_num_threads = 1
                kw["sess_options"] = so
            super().__init__(model_path, **kw)

    _mz.PickableInferenceSession = _ThreadSinirliSession
    try:
        yield
    finally:
        _mz.PickableInferenceSession = asil

_ornekler: dict[str, object] = {}
_kurulum_kilidi = threading.Lock()
_analiz_kilitleri: dict[str, threading.Lock] = {ad: threading.Lock() for ad in PROFILLER}
#: Profil → son `coz()` çağrısının `time.monotonic()` damgası (boşta bekçisi okur).
#: `monotonic` bilerek: sistem saati geri alınırsa duvar saati negatif süre üretir.
_son_kullanim: dict[str, float] = {}
_bekci: threading.Thread | None = None


class KutuphaneYok(RuntimeError):
    """`insightface` inmemiş. Hata **değil**, henüz indirilmemiş bir yetenek.

    Ayrı bir tür olması şart: çağıran bunu "sistem bozuk" ile karıştırmamalı,
    kullanıcıya *"kütüphaneyi indir"* demeli.
    """


def kullanilabilir() -> tuple[bool, str | None]:
    """Yüz tanıma **şu an** çalışabilir mi? Import ETMEDEN bakar.

    📏 Ledger dersi (`ui/yetenek-sorusu-hata-koduyla-sorulmaz`): yetenek sorusu
    4xx/5xx ile sorulmaz — tarayıcı her hata kodu için konsola satır yazar ve
    "özellik yok" ile "sistem bozuk" ayırt edilemez olur. Yetenek **veri**dir.
    """
    from app import pydeps
    return pydeps.kullanilabilir(*GEREKEN_MODULLER)


def al(profil: str):
    """Profilin paylaşılan `FaceAnalysis` örneği — ilk çağrıda kurulur.

    Çift kontrollü kilit: model yüklemesi saniyeler sürer, iki iş parçacığı aynı
    anda isterse ikisi de kurmasın.
    """
    if profil not in PROFILLER:
        raise KeyError(f"Bilinmeyen profil: {profil}. Geçerli: {list(PROFILLER)}")  # i18n-istisna: programlama hatası (geçersiz profil adı)
    ornek = _ornekler.get(profil)
    if ornek is not None:
        return ornek
    with _kurulum_kilidi:
        ornek = _ornekler.get(profil)
        if ornek is not None:
            return ornek

        var, sebep = kullanilabilir()
        if not var:
            from app.mesajlar import M  # noqa: PLC0415 — pydeps ile aynı gerekçe: erken yüklenen modül
            raise KutuphaneYok(sebep or M("pydeps.eksik", moduller=", ".join(GEREKEN_MODULLER)))

        import insightface  # noqa: PLC0415 — bilerek geç import (yukarıdaki nota bak)

        p = PROFILLER[profil]
        kok = model_koku()
        moduller = list(TEMEL_MODULLER)
        if poz_duzeltmesi_acik():
            moduller.append(POZ_MODULU)

        with _sinirli_oturumlar():
            app = insightface.app.FaceAnalysis(
                name="buffalo_l",
                root=kok,   # ⚠️ ŞART — bkz. model_koku(): env DEĞİL parametre okunuyor
                providers=["CPUExecutionProvider"],
                allowed_modules=moduller,
            )
            app.prepare(ctx_id=p["ctx_id"], det_size=p["det_size"])
        _ornekler[profil] = app
        _son_kullanim[profil] = time.monotonic()
        _bosta_bekcisini_baslat()
        logger.info(
            "InsightFace buffalo_l yüklendi (profil=%s, det_size=%s, modüller=%s, "
            "ort_thread=%s, kök=%s)",
            profil, p["det_size"], moduller, _ort_thread_sayisi(), kok,
        )
        return app


def kilit(profil: str) -> threading.Lock:
    """Profilin analiz kilidi — `with` ile kullanılır.

    Tek örneğe inince `analyzer.get()` paylaşılan duruma dönüşür; iki eşzamanlı
    HTTP isteği aynı örneğe farklı iş parçacıklarından girebilir. Serileştirmenin
    bedeli bu ölçekte sıfıra yakın; yarışın bedeli teşhisi çok zor bir hatadır.
    """
    if profil not in _analiz_kilitleri:
        raise KeyError(f"Bilinmeyen profil: {profil}")
    return _analiz_kilitleri[profil]


def coz(profil: str, kare):
    """Kilitli tek analiz çağrısı — çağıranların ezici çoğunluğu bunu ister."""
    app = al(profil)
    try:
        with _analiz_kilitleri[profil]:
            return app.get(kare)
    finally:
        # Damga **sonda** basılır: canlılık dizisi 40 kareyi ~4 sn'de işler ve
        # her kare ayrı `coz()` çağrısıdır. Başta bassaydık uzun bir analizin
        # ortasında boşta sayılabilirdi.
        _son_kullanim[profil] = time.monotonic()


def _bosta_bekcisini_baslat() -> None:
    """Boşta kalan modeli bellekten düşüren arka plan bekçisi (bir kez kurulur).

    🔑 **Neden gerekli:** model zaten tembel yükleniyordu, ama bir kez yüklenince
    süreç ömrü boyunca kalıyordu. Tek bir yüzle giriş, uygulama kapanana kadar
    ~330 MB ONNX ağırlığını (+ çalışma arenaları) rehin alıyordu.

    ⚠️ Düşürmek **çalışan bir isteği bozmaz**: `coz()` örneği yerel değişkene
    almış durumdadır, `_ornekler.clear()` yalnız sözlükteki referansı düşürür;
    Python nesneyi son kullanan bitene kadar canlı tutar.
    """
    global _bekci
    if _bekci is not None and _bekci.is_alive():
        return
    from app import config  # noqa: PLC0415

    dakika = float(getattr(config, "FACE_IDLE_UNLOAD_MIN", 10) or 0)
    if dakika <= 0:
        return  # 0 = kapalı; bekçi hiç kurulmaz, boşuna uyanan iş parçacığı olmaz

    esik = dakika * 60.0

    def _dongu() -> None:
        # Yoklama aralığı eşiğin dörtte biri: eşikten büyük olsaydı 10 dakikalık
        # ayar pratikte 20 dakika gibi davranır ve ayar yalan söylerdi.
        aralik = max(15.0, esik / 4)
        while True:
            time.sleep(aralik)
            if not _ornekler:
                continue
            simdi = time.monotonic()
            en_son = max(_son_kullanim.values(), default=simdi)
            if simdi - en_son < esik:
                continue
            with _kurulum_kilidi:
                # Kilit alınana kadar yeni istek gelmiş olabilir — yeniden ölç.
                if _ornekler and simdi - max(_son_kullanim.values(), default=simdi) >= esik:
                    _ornekler.clear()
                    _son_kullanim.clear()
                    logger.info("InsightFace boşta (%.0f dk) — model bellekten düşürüldü",
                                dakika)

    _bekci = threading.Thread(target=_dongu, name="yuz_bosta_bekcisi", daemon=True)
    _bekci.start()


def kurulu_profiller() -> list[str]:
    """Tanı amaçlı: şu ana kadar gerçekten yüklenmiş profiller."""
    return sorted(_ornekler)


def yuklu(profil: str) -> bool:
    """Profil **şu anda** bellekte mi — yüklemeyi TETİKLEMEDEN.

    `al()` yoksa yükler; bu soru sormak için kullanılamaz. Isıtma ucu
    (`/api/face/warmup`) zaten hazır olan bir modeli ikinci kez ısıtmaya
    kalkmasın diye ayrı duruyor.

    ⚠️ Cevap **anlıktır**: boşta bekçisi (`FACE_IDLE_UNLOAD_MIN`) modeli
    aradan düşürebilir. Çağıran bunu bir garanti değil, ipucu saymalı.
    """
    return profil in _ornekler


def unut() -> None:
    """Yüklü örnekleri düşür — kütüphane **sonradan** indirildiğinde gerekir.

    Kullanıcı uygulama açıkken kütüphaneyi indirirse, o ana kadar `KutuphaneYok`
    almış bir profil belleğe hiç kurulmamıştır; burada silinecek bir şey yoktur.
    Ama tersi de mümkün (kütüphane silinip yeniden indirildi) ve o durumda eski
    örnek bayat yollara tutunur. Ucuz sigorta.
    """
    with _kurulum_kilidi:
        _ornekler.clear()
        _son_kullanim.clear()
