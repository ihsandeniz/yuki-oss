"""Faz ζ — Görüntü Araçları: OCR, QR ve Görüntü Üretme.

Araçlar:
    ocr_image(path)              → görüntüden metin çıkar (tesseract)
    read_qr(path)                → QR / barkod oku (pyzbar veya opencv)
    generate_image(prompt, size) → OpenRouter ile görüntü üret (GORSEL_MODELI)
"""

import asyncio
import base64
import logging
import os

logger = logging.getLogger(__name__)


_ocr_engine = None
_ocr_broken = False

# ── Sohbete yüklenen görsel ↔ araç köprüsü (2026-08-09) ──────────────────────
# 🔴 Kusur: kullanıcı sohbete görsel yükleyip "bunu oku" diyordu ve araç ölüydü.
# Sebep kodda değil YOLDAYDI: yükleme `DATA_DIR/media_uploads/`e yazılıyor,
# `image_msg` olayı yalnız ARAYÜZE gidiyor (core.js görseli çizer) — modele ne
# dosya adı ne yol ulaşıyor. Araç ise zorunlu `path` istiyordu → modelin elinde
# verecek bir tutamak yoktu. Sistem promptu "fotoğraftaki yazı → ocr_image"
# diyordu; ilan edilen ama ulaşılamayan araç.
# Köprü BACKEND'de kuruldu, frontend'den ek LLM turu tetiklenmedi: ücretsiz
# OpenRouter kotası günde 50 istek — her yüklenen görsele bir tur yazmak,
# kullanıcının kotasını onun adına harcamak olurdu.

_GORSEL_UZANTILARI = {".png", ".jpg", ".jpeg", ".bmp", ".tiff", ".tif", ".webp", ".gif"}


def _medya_dizini():
    """Sohbete yüklenen dosyaların dizini — `api/media.py::MEDIA_DIR` ile aynı yer.

    İçeriden import: `config.DATA_DIR` testlerde monkeypatch'lenebilsin ve
    modül yüklenirken dizin sabitlenmesin (AppImage'de userData'ya yönlenir).
    """
    from pathlib import Path
    from app.config import DATA_DIR
    return Path(DATA_DIR) / "media_uploads"


def _son_yuklenen_gorsel():
    """En son yüklenen görsel dosya (mtime'a göre), yoksa None."""
    try:
        adaylar = [
            p for p in _medya_dizini().iterdir()
            if p.is_file() and p.suffix.lower() in _GORSEL_UZANTILARI
        ]
    except OSError:
        return None
    return max(adaylar, key=lambda p: p.stat().st_mtime) if adaylar else None


def _gorsel_yolunu_coz(path: str):
    """Modelin verdiği `path`i gerçek bir dosyaya bağlar.

    Sıra: ① gerçek yol (geliştirici/tam yol yolu — davranış değişmedi)
          ② yalnız dosya adı → yüklenenler arasında ara (traversal kapalı)
          ③ boş **ya da bulunamadı** → en son yüklenen görsel

    ③'te uydurma bir ad sessizce başka dosyaya bağlanmasın diye çağırana bir
    **not** döndürülür ve cevabın başına yazılır — yanlış dosyayı okuduğumuzu
    kullanıcı görebilmeli.

    Returns:
        (yol | None, not_metni)
    """
    ham = (path or "").strip()

    # ① Tam/göreli gerçek yol
    genis = os.path.expanduser(ham) if ham else ""
    if genis and os.path.isfile(genis):
        return genis, ""

    # ② Yalnız dosya adı → media_uploads içinde ara
    if ham and not any(ayrac in ham for ayrac in ("/", "\\")):
        try:
            kok = _medya_dizini().resolve()
            aday = (kok / ham).resolve()
            if aday.parent == kok and aday.is_file():   # path traversal kapalı
                return str(aday), ""
        except OSError:
            pass

    # ③ Son çare: az önce yüklenen görsel
    son = _son_yuklenen_gorsel()
    if son is None:
        return None, ""
    if not ham:
        return str(son), ""
    return str(son), f"('{ham}' bulunamadı — en son yüklenen görsel okundu: {son.name})\n"


def _gorsel_yok_mesaji(path: str) -> str:
    if (path or "").strip():
        return f"Dosya bulunamadı: {path}"
    return (
        "Okunacak görsel bulunamadı. Önce sohbete bir görsel yükle "
        "(📁 düğmesi ya da kamera), sonra tekrar iste."
    )
# Gerçek TR metinde skorlar 0.96-1.00 çıktı; tek karakterlik desen gürültüsü 0.52.
_OCR_MIN_CONFIDENCE = 0.60


def _latin_orani(s: str) -> float:
    """Harflerin ne kadarı Latin alfabesinden? (ı/İ/ş/ğ/ö/ç/ü Latin sayılır)"""
    import unicodedata
    harfler = [c for c in s if c.isalpha()]
    if not harfler:
        return 1.0
    latin = sum(
        1 for c in harfler
        if "LATIN" in unicodedata.name(c, "")
    )
    return latin / len(harfler)


def _ocr_gurultu_mu(metin: str) -> bool:
    """Latin dışı yazı = uydurma. Ürün TR/EN okur; model desen gördüğünde
    yüksek güvenle (0.78!) CJK karakter üretebiliyor → skor eşiği yetmiyor.
    """
    return _latin_orani(metin) < 0.6


def _get_ocr():
    """RapidOCR motorunu tek kez kur (modeller tekerlekte gömülü, indirme YOK)."""
    global _ocr_engine, _ocr_broken
    if _ocr_engine is not None or _ocr_broken:
        return _ocr_engine
    try:
        from rapidocr import RapidOCR
        _ocr_engine = RapidOCR()
    except Exception as e:  # noqa: BLE001
        logger.warning("RapidOCR kurulamadı: %s", e)
        _ocr_broken = True
    return _ocr_engine


def _ocr_with_tesseract(path: str) -> str | None:
    """Geliştirici makinesinde tesseract varsa yedek yol; yoksa None."""
    try:
        import pytesseract
        from PIL import Image
    except ImportError:
        return None
    try:
        try:
            return pytesseract.image_to_string(Image.open(path), lang="tur+eng").strip()
        except pytesseract.TesseractError:
            return pytesseract.image_to_string(Image.open(path)).strip()
    except Exception as e:  # noqa: BLE001
        logger.warning("pytesseract yedek yolu başarısız: %s", e)
        return None


async def ocr_image(path: str = "") -> str:
    """Görüntü dosyasındaki metni OCR ile çıkarır.

    `path` boş bırakılırsa (ya da verilen ad bulunamazsa) **sohbete en son
    yüklenen görsel** okunur — kullanıcı "bunu oku" dediğinde modelin elinde
    dosya adı olmuyor, bkz. § Sohbete yüklenen görsel ↔ araç köprüsü.

    ÜRÜN MOTORU = **RapidOCR (onnxruntime)**. Sebep: satılan pakette tesseract
    ikilisi yoktu ve araç kullanıcıya "pip install pytesseract" diyordu —
    AppImage kullanıcısının yapamayacağı bir şey. Tesseract'ı gömmek 48 dağıtım
    bağımlı `.so` gerektiriyor (eski dağıtımlarda kırılır) + Windows için ayrı
    ikili ister. RapidOCR saf pip: manylinux + win tekerlekleri, modeller
    tekerleğin İÇİNDE → **hiç indirme yok**, tam-offline SKU da çalışır.
    onnxruntime hafıza motoru için zaten pakette.

    Ölçüm (TR, DejaVuSans 34px): 3/3 satır okundu — güven 1.00 / 0.97 / 0.96;
    tek hata büyük "Ç" → küçük "ç". ı/İ/ş/ğ/ö/ü doğru.

    Args:
        path: Görüntü dosyasının yolu (.png, .jpg, .jpeg, .bmp, .tiff, .webp).

    Returns:
        Tespit edilen metin. Bulunamazsa veya hata olursa açıklayıcı mesaj.
    """
    yol, notu = _gorsel_yolunu_coz(path)
    if yol is None:
        return _gorsel_yok_mesaji(path)
    return notu + await _ocr_oku(yol)


async def _ocr_oku(path: str) -> str:
    """OCR motorunu koşturur. Yol ÇÖZÜLMÜŞ gelir — bkz. `ocr_image`."""
    ext = os.path.splitext(path)[1].lower()
    if ext not in {".png", ".jpg", ".jpeg", ".bmp", ".tiff", ".tif", ".webp"}:
        return f"Desteklenmeyen dosya türü: {ext}. PNG/JPG/BMP/TIFF kullan."

    engine = await asyncio.to_thread(_get_ocr)
    if engine is not None:
        try:
            sonuc = await asyncio.to_thread(engine, path)
            txts = list(sonuc.txts or [])
            scores = list(sonuc.scores or [])
            # Güven eşiği: metin İÇERMEYEN görüntülerde (ör. QR deseni) model
            # düşük güvenle uydurma karakter üretiyordu → eşiğin altını atıyoruz.
            satirlar = [
                t.strip()
                for t, s in zip(txts, scores or [1.0] * len(txts))
                if t and t.strip()
                and s >= _OCR_MIN_CONFIDENCE
                and not _ocr_gurultu_mu(t)
            ]
            if satirlar:
                return "\n".join(satirlar)
            return "Görüntüde okunabilir metin bulunamadı."
        except Exception as e:  # noqa: BLE001
            logger.warning("RapidOCR okuma hatası: %s", e)

    yedek = await asyncio.to_thread(_ocr_with_tesseract, path)
    if yedek:
        return yedek
    if yedek == "":
        return "Görüntüde okunabilir metin bulunamadı."
    return "OCR motoru bu kurulumda yüklü değil."


async def read_qr(path: str = "") -> str:
    """Görüntü dosyasındaki QR kodu veya barkodu okur.

    `ocr_image` ile aynı köprüyü kullanır: `path` boşsa ya da bulunamazsa
    sohbete en son yüklenen görsel okunur. (Aynı kusur sınıfı — kullanıcı
    karekod fotoğrafını yükleyip "bunu oku" dediğinde modelin elinde yol yok.)

    Args:
        path: Görüntü dosyasının yolu ya da yüklenen dosyanın adı. Boş olabilir.

    Returns:
        QR/barkod içeriği. Bulunamazsa veya hata oluşursa açıklayıcı mesaj.
    """
    yol, notu = _gorsel_yolunu_coz(path)
    if yol is None:
        return _gorsel_yok_mesaji(path)
    return notu + await _qr_oku(yol)


async def _qr_oku(path: str) -> str:
    """QR motorlarını sırayla dener. Yol ÇÖZÜLMÜŞ gelir — bkz. `read_qr`."""
    # 1) zxing-cpp — ÜRÜN YOLU. Kendi native kütüphanesini tekerleğin içinde
    # taşır (Linux + Windows), sistem paketi gerektirmez → satılan pakette
    # çalışan tek seçenek. pyzbar libzbar, cv2 ise 71 MB opencv istiyordu.
    try:
        import zxingcpp
        from PIL import Image as PilImage
    except ImportError:
        pass
    else:
        try:
            results = zxingcpp.read_barcodes(PilImage.open(path))
            if not results:
                return "QR/barkod bulunamadı."
            return "\n".join(f"[{r.format.name}] {r.text}" for r in results)
        except Exception as e:  # noqa: BLE001
            logger.warning("zxing-cpp okuma hatası: %s", e)
            # düşmeye devam et — eski yollar dursun

    # 2) pyzbar / 3) cv2 — geliştirici makinesinde kuruluysa yedek yol
    pyzbar_ok = False
    try:
        from pyzbar.pyzbar import decode as pyz_decode
        from PIL import Image as PilImage
        pyzbar_ok = True
    except ImportError:
        pass

    if pyzbar_ok:
        try:
            from PIL import Image as PilImage
            from pyzbar.pyzbar import decode as pyz_decode

            img = PilImage.open(path)
            decoded = pyz_decode(img)
            if not decoded:
                return "QR/barkod bulunamadı (pyzbar)."
            results = []
            for d in decoded:
                data = d.data.decode("utf-8", errors="replace")
                kind = d.type
                results.append(f"[{kind}] {data}")
            return "\n".join(results)
        except Exception as e:
            return f"pyzbar okuma hatası: {e}"

    # cv2 fallback (QRCodeDetector — sadece QR destekler)
    try:
        import cv2
    except ImportError:
        return "QR okuma motoru bu kurulumda yüklü değil."

    try:
        img = cv2.imread(path)
        if img is None:
            return f"Görüntü açılamadı: {path}"
        detector = cv2.QRCodeDetector()
        data, _, _ = detector.detectAndDecode(img)
        if not data:
            return "QR kodu bulunamadı (opencv). Barkod için pyzbar gerekli."
        return f"[QRCODE] {data}"
    except Exception as e:
        return f"cv2 QR okuma hatası: {e}"


#: Geçerliliği OpenRouter `GET /api/v1/models?output_modalities=image` listesinden okunur;
#: `openai/dall-e-3` o listede yok (2026-11-10 ölçüldü: 66 görsel modelde dall-e yok), her çağrı hata.
GORSEL_MODELI = "recraft/recraft-v4.1-flash"

_IMZALAR = (
    (b"\x89PNG\r\n\x1a\n", "image/png"),
    (b"\xff\xd8\xff", "image/jpeg"),
    (b"GIF8", "image/gif"),
)


def _gorsel_bicimi(b64: str) -> str:
    """Modele göre biçim değişir; PNG varsaymak yerine ilk baytlara bakılır. Görsel değilse boş."""
    import base64
    try:
        bas = base64.b64decode(b64[:64] + "=" * (-len(b64[:64]) % 4))
    except ValueError:
        return ""
    if bas[:4] == b"RIFF" and bas[8:12] == b"WEBP":
        return "image/webp"
    return next((mime for imza, mime in _IMZALAR if bas.startswith(imza)), "")


async def generate_image(prompt: str, size: str = "1024x1024") -> str:
    """OpenRouter üzerinden görüntü üretir ve chat'e gönderir.

    Args:
        prompt: Görüntü açıklaması (İngilizce veya Türkçe).
        size:   "1024x1024" | "1792x1024" | "1024x1792"

    Returns:
        Başarı/hata mesajı. Görüntü chat'te image_msg olarak görünür.
    """
    from openai import AsyncOpenAI
    from app.config import OPENROUTER_API_KEY
    from app.services.event_bus import bus

    if not (prompt or "").strip():
        return "Hata: Görsel tarifi boş olamaz."

    valid_sizes = {"1024x1024", "1792x1024", "1024x1792"}
    if size not in valid_sizes:
        size = "1024x1024"

    client = AsyncOpenAI(
        base_url="https://openrouter.ai/api/v1",
        api_key=OPENROUTER_API_KEY,
    )

    try:
        response = await client.images.generate(
            model=GORSEL_MODELI,
            prompt=prompt,
            n=1,
            size=size,  # type: ignore[arg-type]
            response_format="b64_json",
        )
    except Exception as e:
        return f"Görüntü üretme hatası: {e}"

    b64 = response.data[0].b64_json if response.data else None
    if not b64:
        return "Görüntü üretilemedi (boş yanıt)."

    mime = _gorsel_bicimi(b64)
    if not mime:
        return "Görüntü üretilemedi (yanıt görsel değil)."

    # Chat'e gönder
    await bus.publish("image_msg", {"data": b64, "mime": mime})
    return f"Görüntü oluşturuldu ve chat'e gönderildi. Prompt: {prompt[:80]}"
