"""Yuki ↔ MAP sekmesi köprüsü — komut gider, **sonuç geri gelir**.

🔴 **NEDEN GERİ BİLDİRİMLİ:** `switch_tab` deseni ateşle-unut
(`broadcast`) çalışır ve orada bu yeterlidir — sekme değiştirmek ya olur ya
olmaz, yanlış giden bir şey yoktur. Harita farklı: *"Ankara'yı göster"* denince
harita kapalı olabilir, yer adı çözülemeyebilir, katman adı yanlış olabilir.
Ateşle-unut olsaydı Yuki bunların hiçbirini bilmeden *"gösterdim"* derdi —
canlı ölçümle yakalanan sınıfın birebir aynısı (*model işi yapmadan
"yaptım" diyordu*). Bu yüzden her komutun bir kimliği ve bir cevabı vardır.

🔑 **Geocoding BACKEND'E TAŞINMADI.** Yer adı → koordinat çözümü zaten
`map-engine.js` içinde Nominatim ile yapılıyor (üç ayrı çağrı noktası).
Buraya ikinci bir çözücü koymak, ikinci bir bayatlama kaynağı açardı: biri
User-Agent/limit politikası değişince güncellenir, öbürü geride kalır. Komut
yer **adını** taşır, çözümü tek sahibi yapar.

## Akış

    araç (tools/harita.py)
      → gonder({...}) ──WS broadcast──▶ frontend (js/map-kopru.js)
                                          uygular, sonucu WS ile yollar
      ◀── sonuc_geldi(istek_id, veri) ──┘
      → aracın dönüş metni GERÇEKLEŞENİ anlatır

Cevap gelmezse (harita sekmesi hiç açılmamış, WS kopuk) `TimeoutError` değil
**"ulaşılamadı" sonucu** döner: araç katmanı kullanıcıya sebebi söyleyebilsin.
"""
from __future__ import annotations

import asyncio
import logging
import secrets

logger = logging.getLogger(__name__)

#: Frontend'in cevabı için beklenecek süre. Nominatim çağrısı araya girebildiği
#: için ölçülü cömert; aşılırsa arıza değil **bilgi** döner ("ulaşılamadı").
BEKLEME_SN: float = 8.0

_bekleyenler: dict[str, asyncio.Future] = {}
#: istek_id → gelen ilk BAŞARISIZ cevap (bkz. `sonuc_geldi` yarış notu)
_basarisizlar: dict[str, dict] = {}


def _yeni_id() -> str:
    return secrets.token_urlsafe(8)


async def gonder(komut: dict) -> dict:
    """Komutu frontend'e yolla ve sonucunu bekle.

    Dönüş her zaman bir sözlüktür; `ulasildi=False` ise harita cevap vermedi
    (sekme açılmamış / WS kopuk) — bu bir **istisna değil sonuçtur**, çağıran
    kullanıcıya ne olduğunu anlatabilsin.
    """
    from app.api.websocket import _manager

    istek_id = _yeni_id()
    beklenen: asyncio.Future = asyncio.get_running_loop().create_future()
    _bekleyenler[istek_id] = beklenen
    try:
        await _manager.broadcast({"type": "harita_komut", "istek_id": istek_id, **komut})
        try:
            veri = await asyncio.wait_for(beklenen, timeout=BEKLEME_SN)
        except asyncio.TimeoutError:
            # Başarısız cevap gelmiş ama başarılı hiç gelmediyse onu kullan:
            # "hiç cevap yok" ile "cevap var ama olumsuz" ayrı şeylerdir.
            bekleyen_hata = _basarisizlar.get(istek_id)
            if bekleyen_hata is not None:
                return {"ulasildi": True, **bekleyen_hata}
            logger.info("harita_kopru: cevap yok (%s) — MAP sekmesi açık değil olabilir",
                        komut.get("eylem"))
            return {"ulasildi": False,
                    "hata": "Harita cevap vermedi — MAP sekmesi açık olmayabilir."}
        return {"ulasildi": True, **veri}
    finally:
        # 🔑 `finally`: broadcast patlasa da kayıt silinir. Silinmezse her
        # başarısız komut sözlükte bir Future bırakır ve sızıntı birikir.
        _bekleyenler.pop(istek_id, None)
        _basarisizlar.pop(istek_id, None)


def sonuc_geldi(istek_id: str, veri: dict) -> bool:
    """Frontend'in cevabını bekleyen çağrıya teslim et.

    🔴 **ÇOK İSTEMCİ YARIŞI (canlı turda görüldü).** `broadcast`
    bağlı **her** istemciye gider: aynı anda Electron + tarayıcı +
    telefon (tünel) bağlı olabiliyor. MAP sekmesi yalnız birinde açıksa üç cevap
    döner ve ilk gelen kazanırdı — yani harita gerçekten Ankara'ya uçmuşken
    Yuki *"MAP sekmesi açılmadı"* diyebilirdi.

    Kural: **başarılı cevap kazanır.** `ok=False` hemen teslim edilmez, kenarda
    tutulur; `ok=True` gelirse o teslim edilir, hiç gelmezse zaman aşımında
    kenardaki hata kullanılır (`gonder`). Böylece "hiç cevap yok" ile "cevap var
    ama olumsuz" da ayrı kalır.

    ⚠️ Bilinmeyen/geç gelen kimlik **sessizce atılır** (False döner): zaman
    aşımına uğramış bir isteğin cevabı sonradan gelirse, o cevabı bir sonraki
    isteğe teslim etmek iki komutu birbirine karıştırırdı.
    """
    f = _bekleyenler.get(istek_id)
    if f is None or f.done():
        return False
    if not veri.get("ok"):
        # İlk hatayı sakla (sonrakiler aynı sınıftır, ilki en erken bilgidir).
        _basarisizlar.setdefault(istek_id, veri)
        return False
    f.set_result(veri)
    return True


def _sifirla() -> None:
    """YALNIZ testler için."""
    _bekleyenler.clear()
    _basarisizlar.clear()
