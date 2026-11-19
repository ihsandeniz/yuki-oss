"""Canlılık (liveness) — meydan okumalı göz kırpma.

🔴 **NEDEN VAR (geliştirici kararı, 2026-09-05):** kişisel Alice'te yüzle giriş vardı ve
kodunda şu yazılıydı: *"Canlılık kontrolü YOK — statik bir fotoğraf token almaya
yeter."* geliştirici o riski **kendisi için** kabul etmişti. Aynı kodu kullanıcıya satmak
başka bir şey: kullanıcının sosyal medyadaki fotoğrafı, uygulamasının anahtarı olurdu.

## Ne yapar

1. Sunucu bir **meydan okuma** üretir: *"N kez göz kırp"* — N rastgele (2 ya da 3).
2. İstemci kısa bir kare dizisi gönderir (~5 sn).
3. Sunucu dizide şunları arar:
   - istenen sayıda **gerçek geçiş**: açık → kapalı → açık
   - **tek kişi**: her karenin embedding'i referans kareye yakın olmalı
   - **kopya olmayan kareler**: aynı kare N kez gönderilmemiş
   - göz açıklığında gerçek **değişim** (hiç oynamayan dizi = donuk görüntü)

Meydan okuma **tek kullanımlıktır** ve süresi doludur; kaydedilmiş bir diziyi
tekrar oynatmak, hem farklı bir N istendiği hem de kimlik tek kullanımlık olduğu
için tutmaz.

## 🔴 Ne YAPMAZ — bu satırlar vitrinde de yazılmalı

Göz kırpma **basılı fotoğrafı** ve **ekranda gösterilen durağan fotoğrafı** eler.
**Video oynatmayı ELEMEZ.** **Deepfake'i ELEMEZ.** Bunları elemek için doku/derinlik
analizi (ayrı bir anti-spoof modeli, ayrı bir indirme) gerekir ve bu turda yapılmadı.
Bunu "canlılık kontrolü var" diye genel geçer bir güvenceye çevirmek, ürünün
kendi kurallarında yasak olan **ölçülmemiş iddia** olur.

## Eşikler nereden geldi

`face_regions.GOZ_KAPALI_ESIGI` = 0,18 — kişiselde 22 karede ölçüldü (açık göz
0,284–0,428 · kapalı 0,094–0,113) ve 6 farklı yüzde ikinci kez doğrulandı
(0,268–0,396). Açık eşiği 0,225 o iki kümenin **arasındaki boşluğa** kondu;
histerezis, tek bir gürültülü karenin sahte kırpma saymasını engeller.
"""
from __future__ import annotations

import asyncio
import hashlib
import logging
import secrets
import time
from dataclasses import dataclass, field

import numpy as np

from app.config import (
    FACE_LIVENESS_MAX_FRAMES,
    FACE_LIVENESS_MIN_FRAMES,
    FACE_LIVENESS_TTL,
    FACE_RECOGNITION_THRESHOLD,
)
from app.mesajlar import M, Mc
from app.services import face_regions

logger = logging.getLogger(__name__)

#: Göz "kapandı" sayılır — ölçülmüş eşik, `face_regions`'tan gelir (tek kaynak).
KAPALI_ESIGI: float = face_regions.GOZ_KAPALI_ESIGI

#: Göz "yeniden açıldı" sayılır. KAPALI'dan yüksek olması ŞART (histerezis):
#: tek eşikle, eşiğin tam üstünde titreşen gürültülü bir ölçüm sahte kırpma üretir.
ACIK_ESIGI: float = 0.225

#: Kaç kırpma istenebilir. Sabit olsaydı, kaydedilmiş tek bir dizi her seferinde
#: geçerdi; rastgele seçim kaydı işe yaramaz kılar.
KIRPMA_SECENEKLERI: tuple[int, ...] = (2, 3)

#: Göz açıklığı dizisinin en az bu kadar oynaması gerekir. Donuk bir görüntüde
#: (fotoğraf) ölçüm gürültüsü bunun çok altında kalır.
MIN_ACIKLIK_OYNAMASI: float = 0.06

#: Karelerin en fazla bu oranı yüzsüz olabilir. Üstü = kullanılamaz dizi.
MAKS_YUZSUZ_ORAN: float = 0.25

#: Farklı (kopya olmayan) kare oranının alt sınırı.
MIN_TEKIL_KARE_ORANI: float = 0.6

#: Bir meydan okumaya parçalarla biriktirilebilecek toplam bayt.
#: `face_api._MAX_DIZI_TOPLAM` ile aynı değer ve aynı amaç — ama o **istek
#: başına** ölçer. Parçalı gönderim tek isteği çok isteğe böldüğü için o sınır
#: tek başına kalsaydı tavan istek sayısıyla çarpılırdı.
MAKS_BIRIKIM_BAYT: int = 24 * 1024 * 1024


@dataclass
class Meydan:
    """Tek kullanımlık canlılık meydan okuması.

    `parcalar`, kareler **toplanırken** gelen dilimlerin analizini tutar
    (bkz. `parca_ekle`). Anahtar dilimin sırasıdır: kırpma sayımı bir **durum
    makinesidir**, sıra bozulursa açık→kapalı→açık geçişi yanlış sayılır. Ağ
    sırasına güvenmek yerine sıra istemciden alınır ve burada sıralanır.
    """

    id: str
    kirpma: int
    ip: str
    olusturuldu: float = field(default_factory=time.monotonic)
    kullanildi: bool = False
    #: parça sırası → [(kare sha256, analiz | None)] — None = o karede yüz yok
    parcalar: dict[int, list[tuple[str, object | None]]] = field(default_factory=dict)
    #: parçalarda biriken toplam kare sayısı (tavan denetimi için)
    biriken: int = 0
    #: parçalarda biriken toplam bayt (tavan denetimi için)
    biriken_bayt: int = 0


_meydanlar: dict[str, Meydan] = {}
_kilit = asyncio.Lock()


def _temizle() -> None:
    """Süresi dolmuş meydan okumaları at — bellek sınırsız büyümesin."""
    simdi = time.monotonic()
    olu = [k for k, m in _meydanlar.items()
           if simdi - m.olusturuldu > FACE_LIVENESS_TTL * 2]
    for k in olu:
        _meydanlar.pop(k, None)


async def olustur(ip: str) -> dict:
    """Yeni meydan okuma üret — istemciye ne yapması gerektiğini söyler."""
    async with _kilit:
        _temizle()
        m = Meydan(id=secrets.token_urlsafe(18),
                   kirpma=secrets.choice(KIRPMA_SECENEKLERI),
                   ip=ip or "-")
        _meydanlar[m.id] = m
    return {
        "challenge_id": m.id,
        "action": "blink",
        "blinks": m.kirpma,
        "ttl_seconds": FACE_LIVENESS_TTL,
        "min_frames": FACE_LIVENESS_MIN_FRAMES,
        "instruction": Mc("canlilik.talimat", m.kirpma),
    }


def _kirpma_say(acikliklar: list[float]) -> int:
    """Açık→kapalı→açık geçişlerini say (histerezisli durum makinesi).

    🔑 **Önce AÇIK bir kare görülmeden kapanma sayılmaz.** İlk sürüm bunu
    yapmıyordu ve testi yakaladı: `[kapalı, açık]` dizisi bir kırpma sayıyordu.
    Saldırgan için bu bedava bir kırpma demekti — sahibin gözü kapalı bir
    fotoğrafı ile açık bir fotoğrafı yan yana konunca "kırptı" oluyordu.
    Gerçek kırpma açık → kapalı → açık'tır; dizinin nerede başladığı saldırganın
    seçimidir, bizim varsayımımız olamaz.
    """
    sayi = 0
    acik_gorildi = False
    kapali_mi = False
    for a in acikliklar:
        if a > ACIK_ESIGI:
            if kapali_mi:
                sayi += 1
                kapali_mi = False
            acik_gorildi = True
        elif a < KAPALI_ESIGI and acik_gorildi:
            kapali_mi = True
    return sayi


def _red(sebep: str, **ek) -> dict:
    return {"ok": False, "reason": sebep, **ek}


def _ozetle(kareler: list[bytes]) -> list[str]:
    """Kare baytlarının sha256'sı — **ucuz** kapı, modelden ÖNCE koşabilsin.

    Özet **her** kare için hesaplanır (yüzsüz olanlar dâhil): aksi hâlde
    saldırgan aynı yüzsüz kareyi doldurup tekillik oranını şişirirdi.
    """
    return [hashlib.sha256(k).hexdigest() for k in kareler]


async def _olc(kareler: list[bytes], ozetler: list[str] | None = None
               ) -> list[tuple[str, object | None]]:
    """Kareleri ölç: `(bayt özeti, analiz | None)`. Yüz bulunamayan kare `None`."""
    from app.services.face_multi_auth import analiz_et

    ozetler = ozetler if ozetler is not None else _ozetle(kareler)
    cikti: list[tuple[str, object | None]] = []
    for kare, ozet in zip(kareler, ozetler, strict=True):
        try:
            cikti.append((ozet, await analiz_et(kare)))
        except ValueError:
            cikti.append((ozet, None))   # yüz yok — dizi boyunca birkaçı normal
    return cikti


async def parca_ekle(meydan_id: str | None, ip: str, kareler: list[bytes],
                     parca: int) -> dict:
    """Kare dizisinin bir **dilimini** erkenden ölç ve meydan okumada biriktir.

    🔑 **Neden var (2026-09-10):** istemci 40 kareyi 4 sn boyunca topluyor, sonra
    tek pakette yolluyordu; sunucu o 4 sn boyunca **boş duruyor**, kullanıcı ise
    toplama + analizin **toplamını** bekliyordu. Dilimler toplanırken gönderilince
    analiz toplamanın altına gizlenir. Ölçülen kazanç: 12,9 sn → ~9,0 sn.

    ⚠️ **Meydan okumayı TÜKETMEZ.** Tüketen tek yer `dogrula`; parça eklemek bir
    giriş denemesi değildir. Bunun karşılığında tavan denetimi burada yapılır:
    bir meydan okumaya `FACE_LIVENESS_MAX_FRAMES`'ten fazla kare biriktirilemez,
    yoksa tek meydan okuma sınırsız model çıkarımı satın alan bir kanal olurdu.
    """
    if not meydan_id:
        return _red(M("canlilik.alinmadi"))

    async with _kilit:
        m = _meydanlar.get(meydan_id)
        if m is None:
            return _red(M("canlilik.bulunamadi"))
        if m.kullanildi:
            return _red(M("canlilik.kullanildi"))
        if time.monotonic() - m.olusturuldu > FACE_LIVENESS_TTL:
            _meydanlar.pop(meydan_id, None)
            return _red(M("canlilik.suresi-doldu"))
        if m.ip != (ip or "-"):
            return _red(M("canlilik.baska-istemci"))
        if parca in m.parcalar:
            # Aynı sırayı ikinci kez kabul etmek, tekrar oynatmanın en ucuz
            # biçimidir: saldırgan kırpma içeren dilimi çoğaltıp sayıyı şişirir.
            return _red(M("canlilik.parca-alindi"))
        if m.biriken + len(kareler) > FACE_LIVENESS_MAX_FRAMES:
            return _red(M("canlilik.kare-tavani", tavan=FACE_LIVENESS_MAX_FRAMES))
        bayt = sum(len(k) for k in kareler)
        if m.biriken_bayt + bayt > MAKS_BIRIKIM_BAYT:
            return _red(M("canlilik.dizi-buyuk"))
        # Yer AYIRILIYOR: ölçüm kilidin dışında (saniyeler sürer), bu arada gelen
        # ikinci bir parça aynı sırayı ya da aynı yeri kapmasın.
        m.parcalar[parca] = []
        m.biriken += len(kareler)
        m.biriken_bayt += bayt

    olculen = await _olc(kareler)

    async with _kilit:
        m = _meydanlar.get(meydan_id)
        if m is None or m.kullanildi:
            # Ölçüm sürerken meydan okuma tüketildi/düştü — sonucu atmak doğru.
            return _red(M("canlilik.gecersiz"))
        m.parcalar[parca] = olculen
    return {"ok": True, "reason": None, "received": len(kareler), "buffered": m.biriken}


async def dogrula(meydan_id: str | None, ip: str, kareler: list[bytes],
                  parca: int | None = None) -> dict:
    """Kare dizisini meydan okumaya karşı doğrula.

    Başarıda dönen sözlükte `_analizler` anahtarı vardır: karelerin `KareAnalizi`
    listesi. Çağıran (`verify_owner`) tanımayı **bu analizlerden** yapar — modeli
    ikinci kez koşturmamak için değil, asıl olarak *canlılığı ölçülen yüz ile
    tanınan yüz aynı olsun* diye.

    `parca` verilirse `kareler` dizinin **son dilimidir**: daha önce
    `parca_ekle` ile biriktirilen dilimler sıraya göre önüne eklenir.
    `parca` **None** ise eski davranış birebir korunur — birikmiş ne varsa
    atılır ve yalnız bu çağrıdaki kareler değerlendirilir. İstemci parça
    gönderirken bir hata alırsa bu yola düşer; yarım kalmış bir birikimin
    sessizce karışması, sebebi hiçbir yerde yazmayan bir canlılık reddi üretirdi.
    """
    # ── meydan okuma kapısı ────────────────────────────────────────────────
    if not meydan_id:
        return _red(M("canlilik.alinmadi-once"))

    async with _kilit:
        m = _meydanlar.get(meydan_id)
        if m is None:
            return _red(M("canlilik.bulunamadi"))
        if m.kullanildi:
            # Tek kullanım: aynı meydan okumayla ikinci deneme, kaydedilmiş bir
            # dizinin tekrar oynatılmasının en ucuz biçimidir.
            _meydanlar.pop(meydan_id, None)
            return _red(M("canlilik.kullanildi"))
        if time.monotonic() - m.olusturuldu > FACE_LIVENESS_TTL:
            _meydanlar.pop(meydan_id, None)
            return _red(M("canlilik.suresi-doldu"))
        if m.ip != (ip or "-"):
            return _red(M("canlilik.baska-istemci"))
        # Sonucu ne olursa olsun tüketilmiş sayılır: başarısız denemeyi tekrar
        # tekrar aynı kimlikle sürmek, deneme kilidini de anlamsızlaştırırdı.
        m.kullanildi = True
        istenen = m.kirpma
        # Birikim meydan okumayla birlikte tüketilir: kalırsa bir sonraki
        # denemeye sızar ve o denemenin kırpmaları bu dizininkilerle karışırdı.
        birikmis = [d for _, d in sorted(m.parcalar.items())] if parca is not None else []
        m.parcalar = {}
        m.biriken = 0
        m.biriken_bayt = 0

    # ── ucuz kapılar ÖNCE, model SONRA ─────────────────────────────────────
    # 🔴 Sıra kapının kendisi kadar önemli: kopya kare kapısı bayt özetiyle
    # koşar ve 40 kez model çalıştırmadan reddedebilir. Analizi öne alsaydık
    # "aynı fotoğrafı 40 kez gönder" saldırısı reddedilmeden ÖNCE tam bedelini
    # ödetirdi. Biriken dilimlerin özetleri zaten elimizde; yalnız bu çağrının
    # kareleri için hesaplanır.
    yeni_ozetler = _ozetle(kareler)
    tum_ozetler = [o for d in birikmis for o, _ in d] + yeni_ozetler
    tum_ozetler = tum_ozetler[:FACE_LIVENESS_MAX_FRAMES]
    toplam_kare = len(tum_ozetler)

    if toplam_kare < FACE_LIVENESS_MIN_FRAMES:
        return _red(
            M("canlilik.yetersiz-kare", kare=toplam_kare, en_az=FACE_LIVENESS_MIN_FRAMES),
            required_blinks=istenen)

    # Aynı fotoğrafı N kez göndermek en basit saldırı. Bayt özeti bunu yakalar;
    # yakalamadığı durumu (her karesi hafifçe farklı bir video) aşağıdaki
    # kimlik + oynama kapıları da tam olarak ELEMEZ — üstteki dürüstlük notu.
    if len(set(tum_ozetler)) < max(2, int(toplam_kare * MIN_TEKIL_KARE_ORANI)):
        return _red(M("canlilik.kopya"),
                    required_blinks=istenen)

    # ── dilimleri birleştir ────────────────────────────────────────────────
    # Sıra: önce biriktirilen dilimler (parça sırasına göre), sonra bu çağrının
    # kareleri. Kırpma sayımı sıraya bağlıdır — birleştirme sırası kapıdır.
    olculen: list[tuple[str, object | None]] = [k for d in birikmis for k in d]
    olculen += await _olc(kareler, yeni_ozetler)
    olculen = olculen[:FACE_LIVENESS_MAX_FRAMES]

    # ── kare kare analiz ───────────────────────────────────────────────────
    analizler = [a for _, a in olculen if a is not None]
    yuzsuz = len(olculen) - len(analizler)

    if yuzsuz > len(olculen) * MAKS_YUZSUZ_ORAN:
        return _red(M("canlilik.yuz-yok", yuzsuz=yuzsuz, toplam=len(olculen)),
                    required_blinks=istenen)
    if len(analizler) < FACE_LIVENESS_MIN_FRAMES:
        return _red(M("canlilik.yuzlu-az"), required_blinks=istenen)

    # ── landmark var mı ────────────────────────────────────────────────────
    # 🔴 Landmark yoksa göz açıklığı ölçülemez. Bu durumda canlılığı "geçti"
    # saymak, kontrolü sessizce kapatmak olur — en tehlikeli başarısızlık biçimi.
    if any(a.landmark_106 is None for a in analizler):
        logger.error("landmark_2d_106 yok — canlılık ölçülemiyor (model profili eksik?)")
        return _red(M("canlilik.goz-noktasi-yok"),
                    required_blinks=istenen)

    # ── göz açıklığı dizisi ────────────────────────────────────────────────
    # İki gözün BÜYÜĞÜ alınır (`gozler_acik_mi` ile aynı ölçüt): tek gözün saç/
    # kadraj yüzünden bozuk ölçülmesi diziyi sahte kırpmayla doldurmasın.
    acikliklar = [
        max(face_regions.goz_acikligi(a.landmark_106, "sag", a.yaw, a.pitch),
            face_regions.goz_acikligi(a.landmark_106, "sol", a.yaw, a.pitch))
        for a in analizler
    ]
    oynama = max(acikliklar) - min(acikliklar)
    if oynama < MIN_ACIKLIK_OYNAMASI:
        return _red(M("canlilik.hareket-yok"),
                    required_blinks=istenen, blinks_detected=0)

    kirpma = _kirpma_say(acikliklar)
    if kirpma < istenen:
        return _red(M("canlilik.kirpma-uyusmadi", istenen=istenen, kirpma=kirpma),
                    required_blinks=istenen, blinks_detected=kirpma)

    # ── kimlik tutarlılığı ─────────────────────────────────────────────────
    # 🔑 EN KRİTİK KAPI. Onsuz saldırı şu: saldırgan bir kısım karede KENDİ canlı
    # yüzünü gösterip kırpar, bir kısmında sahibin FOTOĞRAFINI tutar. Canlılık
    # saldırganın kırpmasından geçer, tanıma fotoğraftan geçer, giriş açılır.
    # Bu yüzden dizideki HER kare aynı kişi olmalı.
    referans = analizler[int(np.argmax(acikliklar))].embedding
    mesafeler = [
        float(1 - np.dot(referans, a.embedding)
              / (np.linalg.norm(referans) * np.linalg.norm(a.embedding)))
        for a in analizler
    ]
    en_uzak = max(mesafeler)
    if en_uzak > FACE_RECOGNITION_THRESHOLD:
        logger.warning("Canlılık: dizide kimlik değişimi (en uzak kare %.3f)", en_uzak)
        return _red(M("canlilik.birden-fazla"),
                    required_blinks=istenen, blinks_detected=kirpma)

    logger.info("Canlılık geçti: %d/%d kırpma, %d kare, oynama %.3f, kimlik sapması %.3f",
                kirpma, istenen, len(analizler), oynama, en_uzak)
    return {
        "ok": True,
        "reason": None,
        "required_blinks": istenen,
        "blinks_detected": kirpma,
        "frames_used": len(analizler),
        "openness_range": round(oynama, 4),
        "identity_spread": round(en_uzak, 4),
        # ⚠️ Bu sınır kullanıcıya da gösterilebilsin diye veriyle taşınıyor.
        "limits": M("canlilik.sinirlar"),
        "_analizler": analizler,
    }


def _sifirla() -> None:
    """YALNIZ testler için."""
    _meydanlar.clear()
