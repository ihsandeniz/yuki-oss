"""Kamera görüşü — kareyi BELLEKTE çöz, yüz say, (gelişte) kayıtlı yüzlerle karşılaştır.

Gizlilik sınırı: kare diske, günlüğe, buluta GİTMEZ. Baytlar yalnız `np.frombuffer` →
`cv2.imdecode` ile çözülür; dosya ya da geçici dosya açılmaz, bayt loglanmaz.
Test: tests/test_gorus_varlik.py::test_kare_bellekte_cozulur_diske_yazilmaz.

Yüz SAYMAK için OpenCV'nin pakette gelen Haar sınıflandırıcısı kullanılır (CPU, ek model
indirmesi yok, kimlik çıkarmaz). Kim olduğunu bulmak (selam için) yalnız `VarlikIzleyici`
`tanima_iste` dediğinde ve yalnız yüzle giriş için zaten kayıtlı yüzlerle karşılaştırarak
olur (`face_multi_auth.recognize_face`); yeni yüz kaydı açılmaz. Tanıma modeli yoksa ad
gelmez, selam da söylenmez.
"""
from __future__ import annotations

import threading
import time

import numpy as np

from app.services.gorus_bak import MAX_BAYT

MAX_KENAR = 1920
HEDEF_KENAR = 640


class KareHatasi(ValueError):
    pass


_haar = None
_haar_kilit = threading.Lock()


def _cv2():
    """OpenCV geç yüklenir: modül `main.py` üzerinden her açılışta içe aktarılıyor, kamera görüşü
    kapalıyken de. Boş Linux'ta (`libxcb` yok) modül düzeyinde `import cv2` backend'i hiç
    açtırmıyordu (G4b temiz kurulum sınavı). Şimdi yalnız kare işlenirken yüklenir."""
    import cv2
    return cv2


def _dedektor():
    global _haar
    cv2 = _cv2()
    with _haar_kilit:
        if _haar is None:
            # OpenCV 5.0'da CascadeClassifier ana modülden çıktı. Yoksa AttributeError
            # WS döngüsünü düşürmesin; kamera panelinde "yüz dedektörü yok" hatası görünsün.
            sinif = getattr(cv2, "CascadeClassifier", None)
            if sinif is None:
                raise KareHatasi("yuz-dedektoru-yok")
            yol = cv2.data.haarcascades + "haarcascade_frontalface_default.xml"
            d = sinif(yol)
            if d.empty():
                raise KareHatasi("yuz-dedektoru-yok")
            _haar = d
        return _haar


def kare_coz(jpeg: bytes) -> np.ndarray:
    cv2 = _cv2()
    if not jpeg:
        raise KareHatasi("bos")
    if len(jpeg) > MAX_BAYT:
        raise KareHatasi("buyuk")
    kare = cv2.imdecode(np.frombuffer(jpeg, dtype=np.uint8), cv2.IMREAD_COLOR)
    if kare is None:
        raise KareHatasi("cozulemedi")
    y, g = kare.shape[:2]
    if max(y, g) > MAX_KENAR:
        raise KareHatasi("boyut")
    if max(y, g) > HEDEF_KENAR:
        o = HEDEF_KENAR / max(y, g)
        kare = cv2.resize(kare, (int(g * o), int(y * o)), interpolation=cv2.INTER_AREA)
    return kare


def yuz_say(jpeg: bytes) -> tuple[int, float]:
    """(yüz sayısı, ms). Senkron — çağıran `asyncio.to_thread` ile koşar."""
    t0 = time.perf_counter()
    cv2 = _cv2()
    gri = cv2.cvtColor(kare_coz(jpeg), cv2.COLOR_BGR2GRAY)
    yuzler = _dedektor().detectMultiScale(gri, scaleFactor=1.15, minNeighbors=5, minSize=(48, 48))
    del gri
    return len(yuzler), (time.perf_counter() - t0) * 1000


async def tani(jpeg: bytes) -> str | None:
    """Kayıtlı bir yüzse adı, değilse None. Yeni kayıt açmaz; hata = None."""
    try:
        from app.services.face_multi_auth import recognize_face
        sonuc = await recognize_face(jpeg)
    except Exception:
        return None
    return sonuc.get("name") if sonuc.get("known") else None
