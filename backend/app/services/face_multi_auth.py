"""Çok kişili yüz tanıma (InsightFace buffalo_l) — ürün sürümü.

512 boyutlu ArcFace embedding · kosinüs mesafesi · JSON depo (`face_store`).

Kişisel Alice'ten taşındı ( Dalga 2 FAZ 4). **Üç bilinçli fark:**

1. **Depo pgvector değil JSON.** Satılan pakette Postgres yok; kişiseldeki kod
   olduğu gibi taşınsaydı dokuz ucun hepsi pakette 503 dönerdi (PLAN ekranını
   öldüren hatanın aynısı). Gerekçe + ölçek hesabı: `face_store.py` başlığı.
2. **`ela` bağı yok.** HDC hafızası kişisele özgü; `ela_service.py` kullanıcı
   paketinden zaten dışlanıyor. Kişiselde `ela` bir *yedek tanıyıcıydı*; burada
   tanıma tek yoldan yürür ve bu **daha dürüst**: iki tanıyıcının biri "belki"
   dediğinde çıkan `verdict="uncertain"` sonucu kullanıcıya açıklanamıyordu.
3. **Yüzle giriş canlılık ister.** Kişiselde canlılık yoktu ve orada *"statik
   fotoğraf token alır"* diye yazılıydı. `verify_owner` artık tek kare değil
   **kare dizisi** alır ve `face_liveness` kapısından geçirir.

🔌 Kütüphane pakette yok, talep üzerine iner (`app/pydeps.py`). Bu yüzden
`insightface`/`cv2` importları **fonksiyon içinde**.
"""
from __future__ import annotations

import asyncio
import logging
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass

import numpy as np

from app.config import (
    FACE_CONFIDENT_THRESHOLD,
    FACE_ENROLL_MAX_DRIFT,
    FACE_RECOGNITION_THRESHOLD,
    FACES_MAX_COUNT,
)
from app.mesajlar import M
from app.services import face_store
from app.services.insightface_havuzu import KutuphaneYok

logger = logging.getLogger(__name__)

# 2 işçi: bu çağrılar CPU-bağımlı (model çıkarımı) ve havuzun kendi kilidi zaten
# aynı anda tek analiz geçiriyor. Daha fazla işçi yalnız kuyruk uzatır.
_executor = ThreadPoolExecutor(max_workers=2, thread_name_prefix="yuz")


@dataclass(frozen=True)
class KareAnalizi:
    """Tek karenin ölçümü — tanıma ve canlılık aynı analizden beslenir.

    İkisini ayrı ayrı çalıştırmak modeli kare başına iki kez koşturur (≈2× CPU)
    ve daha kötüsü, canlılığın ölçtüğü yüzün tanınan yüz olduğunu garanti etmez.
    """

    embedding: np.ndarray          #: 512-dim, L2 normalize
    bbox: dict                     #: 0-1 normalize {x,y,w,h}
    yuz_sayisi: int
    landmark_106: np.ndarray | None   #: (106,2) — canlılık için; model vermezse None
    yaw: float | None
    pitch: float | None


def _jpeg_to_bgr(veri: bytes) -> np.ndarray:
    import cv2
    arr = np.frombuffer(veri, np.uint8)
    img = cv2.imdecode(arr, cv2.IMREAD_COLOR)
    if img is None:
        raise ValueError(M("yuz.goruntu-okunamadi"))
    return img


def _analiz_sync(veri: bytes) -> KareAnalizi:
    """JPEG/PNG baytları → `KareAnalizi`. En büyük yüz seçilir.

    bbox 0-1'e normalize edilir → arayüz video boyutundan bağımsız çizer.
    Yüz sayısı da döner: kayıtta "arkada biri var" uyarısı için gerekli.
    """
    from app.services import insightface_havuzu

    img = _jpeg_to_bgr(veri)
    h, w = img.shape[:2]
    faces = insightface_havuzu.coz("TANIMA", img)
    if not faces:
        raise ValueError(M("yuz.bulunamadi"))

    face = max(faces, key=lambda f: (f.bbox[2] - f.bbox[0]) * (f.bbox[3] - f.bbox[1]))
    x1, y1, x2, y2 = (float(v) for v in face.bbox[:4])
    bbox = {
        "x": max(0.0, round(x1 / w, 4)),
        "y": max(0.0, round(y1 / h, 4)),
        "w": round(min(1.0, (x2 - x1) / w), 4),
        "h": round(min(1.0, (y2 - y1) / h), 4),
    }

    lmk = getattr(face, "landmark_2d_106", None)
    lmk = np.asarray(lmk, dtype=float) if lmk is not None else None

    # `face.pose` = [pitch, yaw, roll] (insightface/model_zoo/landmark.py:111).
    # Sıra ezberden yazılmadı, kaynaktan okundu — ters yazılsaydı poz düzeltmesi
    # göz açıklığını yanlış yöne çeker ve canlılık sessizce güvenilmez olurdu.
    poz = getattr(face, "pose", None)
    pitch = float(poz[0]) if poz is not None else None
    yaw = float(poz[1]) if poz is not None else None

    return KareAnalizi(
        embedding=face.normed_embedding.astype(np.float32),
        bbox=bbox,
        yuz_sayisi=len(faces),
        landmark_106=lmk,
        yaw=yaw,
        pitch=pitch,
    )


async def analiz_et(veri: bytes) -> KareAnalizi:
    loop = asyncio.get_running_loop()
    return await loop.run_in_executor(_executor, _analiz_sync, veri)


def yetenek() -> dict:
    """Yüz tanıma şu an kullanılabilir mi — **veri olarak**.

    📏 Ledger: yetenek sorusu hata koduyla sorulmaz. `/status` bunu döner;
    "kütüphane inmemiş" ile "sistem bozuk" arayüzde ayırt edilebilmeli.
    """
    from app.services import insightface_havuzu
    var, sebep = insightface_havuzu.kullanilabilir()
    return {"available": var, "unavailable_reason": sebep}


# ── kayıt ───────────────────────────────────────────────────────────────────
def ad_anahtari(name: str | None) -> str:
    """Aynı kişinin farklı yazımlarını eşleyen anahtar (Türkçe büyük/küçük harf duyarlı).

    Kişisel AliceAi'de 'geliştirici' (5 örnek) ve 'Geliştirici' (2 örnek, sahip) iki AYRI kişi olarak
    duruyordu: tanıma iki "kişi" arasındaki farka baktığı için sahip girişi kararsız düşüyor,
    ad birebir karşılaştırıldığı için 'geliştirici' tanınınca giriş reddediliyordu (295059d). Ürün
    aynı koddan (09-27 okundu: register/verify `==`, delete `.lower()`). Python'un lower()'ı
    'İ'yi 'i̇' yapar → önce Türkçe eşle.
    """
    # \u0130 = "İ", \u0131 = "ı" — kaçışla yazıldı: harf eşlemesi, kullanıcıya giden metin değil
    return (name or "").strip().replace("\u0130", "i").replace("I", "\u0131").lower()


class SahipSilmeOnayi(Exception):
    """Sahibi silmek yüzle girişi kapatır — açık onay (`?sahip=1`) ister."""


async def register_face(name: str, veri: bytes) -> dict:
    """Kişiyi depoya kaydeder. Aynı isimle birden fazla kayıt eklenebilir."""
    if not name or not name.strip():
        raise ValueError(M("yuz.isim-bos"))
    name = name.strip()

    analiz = await analiz_et(veri)
    encoding = analiz.embedding

    mevcut = face_store.benzersiz_kisiler()
    # Aynı adın başka yazımı varsa ona ekle — ikiz kişi oluşmasın (bkz. ad_anahtari)
    esi = next((n for n in mevcut if n != name and ad_anahtari(n) == ad_anahtari(name)), None)
    if esi:
        name = esi
    if name not in mevcut and len(mevcut) >= FACES_MAX_COUNT:
        raise ValueError(M("yuz.maks-kisi", n=FACES_MAX_COUNT))

    # Kalite kapısı: yeni kare bu kişinin mevcut kayıtlarına ne kadar uzak?
    drift = face_store.kisiye_min_mesafe(encoding, name)
    drift = round(float(drift), 4) if drift is not None else None

    # Başka birine bu kişiden daha mı yakın? (yanlış isme kayıt uyarısı)
    yakinlar = [(ad, d) for ad, d in face_store.en_yakin_kisiler(encoding, limit=3) if ad != name]
    en_yakin_yabanci = yakinlar[0] if yakinlar else None

    face_store.ekle(name, encoding)
    adet = face_store.kisi_kayit_sayisi(name)

    warnings: list[str] = []
    if analiz.yuz_sayisi > 1:
        warnings.append(M("yuz.uyari-cok-yuz", n=analiz.yuz_sayisi))
    if drift is not None and FACE_ENROLL_MAX_DRIFT > 0 and drift > FACE_ENROLL_MAX_DRIFT:
        warnings.append(M("yuz.uyari-uzak", ad=name, mesafe=f"{drift:.2f}"))
    if en_yakin_yabanci is not None:
        yabanci_ad, yabanci_mesafe = en_yakin_yabanci
        if drift is None:
            # Bu ismin İLK kaydı. Yüz başka biri olarak zaten kayıtlıysa söyle —
            # aynı kişiyi iki isimle kaydetmenin tek uyarısı bu.
            if yabanci_mesafe < FACE_RECOGNITION_THRESHOLD:
                warnings.append(M("yuz.uyari-zaten-kayitli", ad=yabanci_ad,
                                  mesafe=f"{yabanci_mesafe:.2f}"))
        elif yabanci_mesafe < drift:
            warnings.append(M("yuz.uyari-daha-yakin", yabanci=yabanci_ad,
                              yabanci_mesafe=f"{yabanci_mesafe:.2f}", ad=name,
                              mesafe=f"{drift:.2f}"))

    logger.info("Yüz kaydedildi: %s (toplam kayıt: %d, drift=%s, yüz=%d)",
                name, adet, drift, analiz.yuz_sayisi)
    return {"ok": True, "name": name, "total_encodings": adet,
            "drift": drift, "faces_detected": analiz.yuz_sayisi,
            "bbox": analiz.bbox, "warnings": warnings}


# ── tanıma ──────────────────────────────────────────────────────────────────
def _tani(analiz: KareAnalizi) -> dict:
    """Analizden tanıma sonucu üretir (senkron — dizi doğrulamasında da kullanılır).

    `confidence` = kosinüs benzerliği (1 − mesafe). Eski formül `1 − mesafe/eşik`
    idi ve aynı kişinin canlı karesi 0,33 mesafede **%19 güven** gösteriyordu:
    formül "0 mesafe = %100" varsayıyor, ArcFace'te bu asla olmuyor.

    `margin` = ikinci en yakın KİŞİye fark. Tek başına mesafeden çok daha
    bilgilendirici: 0,33'lük eşleşme, ikinci kişi 0,86'daysa kesindir.
    """
    taban = {"bbox": analiz.bbox, "faces_detected": analiz.yuz_sayisi,
             "threshold": FACE_RECOGNITION_THRESHOLD}
    yakinlar = face_store.en_yakin_kisiler(analiz.embedding, limit=2)

    if not yakinlar:
        return {**taban, "known": False, "name": None, "distance": None,
                "confidence": 0.0, "verdict": "unknown", "margin": None, "runner_up": None}

    ad, mesafe = yakinlar[0]
    runner_up = yakinlar[1][0] if len(yakinlar) > 1 else None
    margin = round(yakinlar[1][1] - mesafe, 4) if len(yakinlar) > 1 else None

    if mesafe < FACE_RECOGNITION_THRESHOLD:
        verdict = "high" if mesafe < FACE_CONFIDENT_THRESHOLD else "uncertain"
        return {**taban, "known": True, "name": ad, "distance": round(mesafe, 4),
                "confidence": round(max(0.0, 1.0 - mesafe), 3), "verdict": verdict,
                "margin": margin, "runner_up": runner_up}

    return {**taban, "known": False, "name": None, "distance": round(mesafe, 4),
            "confidence": 0.0, "verdict": "unknown", "margin": margin,
            "runner_up": None, "closest": ad}


async def recognize_face(veri: bytes) -> dict:
    """Karedeki yüzü kayıtlarla karşılaştırır."""
    analiz = await analiz_et(veri)
    sonuc = _tani(analiz)
    if sonuc["known"]:
        logger.info("Yüz tanındı: %s (dist=%s conf=%s marj=%s verdict=%s)",
                    sonuc["name"], sonuc["distance"], sonuc["confidence"],
                    sonuc["margin"], sonuc["verdict"])
    else:
        logger.info("Yüz tanınamadı (dist=%s eşik=%.2f)",
                    sonuc["distance"], FACE_RECOGNITION_THRESHOLD)
    return sonuc


async def list_faces() -> list[dict]:
    return face_store.kisiler()


# ── sahiplik (yüzle giriş) ──────────────────────────────────────────────────
def get_owner() -> str | None:
    """Sahip kim? `FACE_OWNER_NAME` env > depodaki `owner` > tanımsız.

    Tanımsızsa giriş **reddedilir** — sessizce herkesi kabul etmez.
    """
    from app.config import FACE_OWNER_NAME
    if FACE_OWNER_NAME:
        return FACE_OWNER_NAME
    return face_store.sahip_oku()


def set_owner(name: str) -> None:
    face_store.sahip_yaz(name)


def sahip_kaydi() -> dict | None:
    """Sahibin depodaki kaydı (`{name, encodings, first_seen}`) — YAZIMDAN BAĞIMSIZ.

    HQ kimlik kartı sahibin örnek sayısını ve kalite satırını bununla bulur; ad
    eşlemesi ön yüzde tekrar yazılmasın diye burada (`ad_anahtari` tek kaynak).
    """
    sahip = get_owner()
    if not sahip:
        return None
    anahtar = ad_anahtari(sahip)
    return next((k for k in face_store.kisiler() if ad_anahtari(k["name"]) == anahtar), None)


def sahip_mi(name: str | None) -> bool:
    sahip = get_owner()
    return bool(sahip) and bool(name) and ad_anahtari(name) == ad_anahtari(sahip)


def owner_enrolled() -> bool:
    """Sahip GERÇEKTEN yüzle girebilir mi?

    🔴 **2026-09-06'da sahada bulundu.** Eski hâli `return bool(get_owner())`
    idi — yalnız sahip **adının** kayıtlı olup olmadığına bakıyordu, o adla bir
    **yüz** olup olmadığına değil. Sahibin yüzü silindiğinde ad öksüz kalıyor ve
    bu fonksiyon *"evet, kayıtlı"* demeye devam ediyordu.

    Ölçülen sonuç (geliştiricinin kurulumu): `owner="sahip"` · `faces=["geliştirici"]`.
    Yani `/api/face/login-status` **enrolled:true** dedi, kilit ekranında
    "Yüzümle gir" düğmesi çıktı, kullanıcı göz kırptı, canlılık GEÇTİ, yüz
    `verdict=high` ile TANINDI — ve giriş yine reddedildi, çünkü tanınan kişi
    ("geliştirici") sahip ("sahip") değildi. Kullanıcı için bu, sebebi hiçbir yerde
    yazmayan bir başarısızlıktır.

    📏 Ders: *bir yeteneği ilan eden bayrak, yeteneğin kendisini değil yalnız
    bir kaydın varlığını ölçüyorsa er geç yalan söyler.*
    """
    sahip = get_owner()
    if not sahip:
        return False
    try:
        return any(face_store.kisi_kayit_sayisi(n) > 0 for n in face_store.benzersiz_kisiler()
                   if ad_anahtari(n) == ad_anahtari(sahip))
    except Exception as e:   # depo okunamıyorsa "kayıtlı değil" tarafına düş
        logger.warning("Sahip kaydı doğrulanamadı: %s", e)
        return False


async def enroll_owner(veri: bytes, name: str | None = None) -> dict:
    """Sahibin yüzünü kaydeder ve sahibi işaretler."""
    from app.config import FACE_OWNER_NAME
    hedef = (name or FACE_OWNER_NAME or get_owner() or "sahip").strip()
    sonuc = await register_face(hedef, veri)
    set_owner(hedef)
    return {**sonuc, "owner": hedef}


async def verify_owner(kareler: list[bytes], meydan_id: str | None, ip: str,
                       parca: int | None = None) -> dict:
    """Yüzle giriş — **kare dizisi** + canlılık kapısı.

    Token yalnız şu üçü birden sağlanınca verilir:
      ① canlılık geçti (istenen sayıda gerçek göz kırpma, aynı kişi, kopya kare yok)
      ② tanınan kişi = sahip
      ③ `verdict == "high"` (mesafe < `FACE_CONFIDENT_THRESHOLD`)

    Kararsız bölge (0,35-0,45) girişi **geçirmez** — orada tanıma zaten güvenilmez.

    ⚠️ Canlılığın sınırı: göz kırpma basılı ve ekrandaki fotoğrafı eler,
    **video oynatmayı ve deepfake'i elemez.** → `face_liveness.py`
    """
    from app.config import FACE_LIVENESS_REQUIRED
    from app.services import face_liveness

    sahip = get_owner()
    if not sahip:
        raise RuntimeError(M("yuz.sahip-yok"))

    if FACE_LIVENESS_REQUIRED:
        canlilik = await face_liveness.dogrula(meydan_id, ip, kareler, parca)
        if not canlilik["ok"]:
            logger.info("Yüzle giriş: ✗ canlılık (%s)", canlilik["reason"])
            return {"ok": False, "owner": sahip, "name": None, "verdict": "liveness_failed",
                    "distance": None, "margin": None, "liveness": canlilik}
        analizler = canlilik.pop("_analizler")
    else:
        # Canlılık kapatılmışsa (self-host tercihi) tek kare yeter — ama bu
        # yolun ne kaybettirdiği kayıt altında: fotoğrafla giriş açılır.
        logger.warning("FACE_LIVENESS_REQUIRED=false — fotoğrafla giriş mümkün")
        if not kareler:
            raise ValueError(M("yuz.kare-yok"))
        analizler = [await analiz_et(kareler[0])]
        canlilik = {"ok": True, "reason": M("canlilik.kapali")}

    # Tanıma dizinin EN İYİ karesinden okunur: göz kırpma sırasında bazı kareler
    # kapalı gözlü ve doğal olarak daha uzak çıkar. En kötü kareye bakmak, canlı
    # kullanıcıyı kendi kırpması yüzünden reddetmek olurdu.
    sonuclar = [_tani(a) for a in analizler]
    tanindi = [s for s in sonuclar if s["known"]]
    en_iyi = min(tanindi, key=lambda s: s["distance"]) if tanindi else sonuclar[0]

    ok = (bool(en_iyi.get("known")) and ad_anahtari(en_iyi.get("name")) == ad_anahtari(sahip)
          and en_iyi.get("verdict") == "high")
    logger.info("Yüzle giriş: %s (tanınan=%s verdict=%s dist=%s kare=%d)",
                "✓" if ok else "✗", en_iyi.get("name"), en_iyi.get("verdict"),
                en_iyi.get("distance"), len(analizler))
    return {"ok": ok, "owner": sahip, "name": en_iyi.get("name"),
            "verdict": en_iyi.get("verdict"), "distance": en_iyi.get("distance"),
            "margin": en_iyi.get("margin"), "liveness": canlilik}


# ── selamlama soğuması ──────────────────────────────────────────────────────
# Her tanıma Event Bus'a `face_recognized` yayınlıyordu; canlı tarama 2,5 sn'de
# bir tarayınca her turda selamlanıyor ve TTS parçaları üst üste binip takılıyordu.
_son_selam: dict[str, float] = {}


def should_greet(name: str, cooldown: float | None = None) -> bool:
    """Bu kişi için selamlama yayınlanmalı mı? (soğuma penceresi)"""
    import time as _t

    from app.config import FACE_GREET_COOLDOWN
    if not name:
        return False
    cd = FACE_GREET_COOLDOWN if cooldown is None else cooldown
    if cd <= 0:
        return True
    simdi = _t.monotonic()
    son = _son_selam.get(name)
    if son is not None and (simdi - son) < cd:
        return False
    _son_selam[name] = simdi
    return True


# ── kalite + silme ──────────────────────────────────────────────────────────
async def face_quality() -> dict:
    """Kayıt kalitesi — kişi-içi tutarlılık + aykırı kayıtlar.

    Her kayıt için "kendi kişisinin diğer kayıtlarına en yakın mesafesi" hesaplanır.
    Bu değer eşiği aşıyorsa kayıt aykırıdır: o kare kişinin kendi kayıtlarıyla
    eşleşmiyor demektir (yanlış kişi, kötü ışık ya da çok eski kamera).
    """
    kayitlar = face_store.tum_kayitlar()

    def _d(a: np.ndarray, b: np.ndarray) -> float:
        return float(1 - np.dot(a, b) / (np.linalg.norm(a) * np.linalg.norm(b)))

    people: list[dict] = []
    outliers: list[dict] = []
    for ad in sorted({k[1] for k in kayitlar}):
        benim = [k for k in kayitlar if k[1] == ad]
        digerleri = [k for k in kayitlar if k[1] != ad]
        ciftler = [_d(a[2], b[2]) for i, a in enumerate(benim) for b in benim[i + 1:]]
        capraz = [_d(a[2], b[2]) for a in benim for b in digerleri]
        for kayit in benim:
            kalan = [o for o in benim if o[0] != kayit[0]]
            en_yakin_kendi = min((_d(kayit[2], o[2]) for o in kalan), default=None)
            if en_yakin_kendi is not None and en_yakin_kendi > FACE_RECOGNITION_THRESHOLD:
                outliers.append({"id": kayit[0], "name": ad,
                                 "nearest_own": round(en_yakin_kendi, 4),
                                 "created_at": kayit[3]})
        people.append({
            "name": ad,
            "encodings": len(benim),
            "intra_min": round(min(ciftler), 4) if ciftler else None,
            "intra_avg": round(float(np.mean(ciftler)), 4) if ciftler else None,
            "intra_max": round(max(ciftler), 4) if ciftler else None,
            "nearest_other": round(min(capraz), 4) if capraz else None,
            "nearest_other_name": min(
                ((_d(a[2], b[2]), b[1]) for a in benim for b in digerleri),
                default=(None, None))[1],
        })

    return {"people": people, "outliers": outliers,
            "threshold": FACE_RECOGNITION_THRESHOLD,
            "confident_threshold": FACE_CONFIDENT_THRESHOLD}


async def delete_encoding(enc_id: int) -> dict:
    """Tek kaydı siler (aykırı kayıt temizliği)."""
    try:
        ad = face_store.sil_kayit_denetimli(enc_id)
    except KeyError:
        raise ValueError(M("yuz.kayit-yok", id=enc_id))
    logger.info("Kayıt silindi: #%d (%s)", enc_id, ad)
    return {"ok": True, "id": enc_id, "name": ad}


async def delete_face(name: str, sahip_onay: bool = False) -> dict:
    # Sahibi silmek yüzle girişi KAPATIR — eskiden tek dokunuşla, sessizce oluyordu
    # (kişisel 517e975'in ürün karşılığı, 09-27). Yazımdan bağımsız: 'geliştirici' silinirken
    # sahip 'Geliştirici' ise de korunur.
    sahip = get_owner()
    sahibi_siliyor = bool(sahip) and ad_anahtari(sahip) == ad_anahtari(name)
    if sahibi_siliyor and not sahip_onay:
        raise SahipSilmeOnayi(M("yuz.sahip-silme-onay", ad=name))
    silinen = face_store.sil_kisi(name)
    if silinen == 0:
        raise ValueError(M("yuz.kisi-yok", ad=name))
    logger.info("Yüz silindi: %s (%d kayıt)", name, silinen)

    # 🔴 Silinen kişi SAHİP ise sahiplik kaydını da düşür (2026-09-06).
    # Eskiden `owner` alanı olduğu gibi kalıyordu: yüzü olmayan bir sahip adı.
    # `owner_enrolled()` artık bunu ayrıca ölçüyor ama tek başına yetmez —
    # öksüz kaydı bırakmak, kullanıcı aynı adla YENİ bir yüz kaydettiğinde
    # onu sessizce sahip yapardı. Sahiplik açık bir eylemle verilir (`/enroll`),
    # ad çakışmasıyla değil.
    if sahibi_siliyor:
        set_owner("")
        logger.info("Sahip kaydı düşürüldü: '%s' silindi, yüzle giriş kapandı.", name)

    return {"ok": True, "name": name, "deleted_encodings": silinen}


__all__ = [
    "KareAnalizi", "KutuphaneYok", "analiz_et", "delete_encoding", "delete_face",
    "SahipSilmeOnayi", "ad_anahtari", "enroll_owner", "face_quality", "get_owner", "list_faces", "owner_enrolled",
    "recognize_face", "register_face", "set_owner", "should_greet", "verify_owner",
    "yetenek",
]
