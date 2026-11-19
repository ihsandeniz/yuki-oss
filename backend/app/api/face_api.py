"""Yüz tanıma API — kayıt · tanıma · yönetim · yüzle giriş (canlılık kapılı).

Kişisel Alice'ten taşındı ( Dalga 2 FAZ 4, Free kademe).

    Korumalı (Bearer token ister)
      POST   /api/face/enroll            sahibin yüzünü kaydet + sahibi işaretle
      POST   /api/face/register          kişiyi isme göre kaydet
      POST   /api/face/scan              karedeki kişiyi tanı
      GET    /api/face/list              kayıtlı kişiler
      GET    /api/face/quality           kayıt kalitesi + aykırı kayıtlar
      GET    /api/face/status            tam durum (sahip adı dâhil)
      DELETE /api/face/encoding/{id}     tek kaydı sil
      DELETE /api/face/{name}            kişiyi sil

    Açık (giriş ekranı — kullanıcı henüz oturum açmamış olabilir)
      GET    /api/face/login-status      yüzle giriş mümkün mü + kilit durumu
      POST   /api/face/liveness/challenge  canlılık meydan okuması al
      POST   /api/face/frames            kare dizisinin bir dilimi (token ÜRETMEZ)
      POST   /api/face/verify            kare dizisi + meydan okuma → token
      POST   /api/face/warmup            modeli arka planda yüklemeye başlat

🔑 **Açık uçlar sahip ADINI sızdırmaz.** Kişiselde `/status` sahibin adını
oturum açmamış çağırana da dönüyordu; tek kullanıcılı kişisel kurulumda zararsız,
satılan üründe **kimlik ifşasıdır**. Ürün ikiye ayırdı: `login-status` yalnız
"kayıt var mı" der, ad `status`'ta ve token arkasında kalır.

🔴 **Yetenek sorusu hata koduyla sorulmaz** (ledger). Kütüphane inmemişken
`login-status` ve `status` **200 + veri** döner (`available: false` +
`unavailable_reason`). 503 yalnız gerçekten *yapılamayan bir eylem* için.
"""
from __future__ import annotations

import logging

from fastapi import APIRouter, File, Form, HTTPException, Request, UploadFile

from app.config import FACE_AUTH_ENABLED
from app.limiter import limiter
from app.mesajlar import M, Mc

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/face", tags=["face"])

#: Tek kare üst sınırı (SECURITY.md § 8: görseller 5 MB)
_MAX_KARE = 5 * 1024 * 1024
#: Canlılık dizisindeki tek kare — dizi 40 kare olabildiği için daha dar
_MAX_DIZI_KARE = 2 * 1024 * 1024
#: Canlılık dizisinin toplamı
_MAX_DIZI_TOPLAM = 24 * 1024 * 1024

_JPEG = b"\xff\xd8\xff"
_PNG = b"\x89PNG\r\n\x1a\n"


def _kapali_mi() -> None:
    if not FACE_AUTH_ENABLED:
        raise HTTPException(status_code=503, detail=M("yuz.devre-disi"))


def _tur_dogrula(veri: bytes) -> None:
    """Dosya türünü **sunucu tarafında** doğrula (SECURITY.md § 8).

    İstemcinin gönderdiği `content-type`'a bakılmaz — onu saldırgan yazar.
    Sihirli baytlar okunur.
    """
    if veri[:3] == _JPEG or veri[:8] == _PNG:
        return
    raise HTTPException(status_code=415, detail=M("yuz.tur"))


async def _kare_oku(file: UploadFile, sinir: int = _MAX_KARE) -> bytes:
    veri = await file.read()
    if len(veri) > sinir:
        raise HTTPException(status_code=413,
                            detail=M("yuz.dosya-buyuk", mb=sinir // (1024 * 1024)))
    if not veri:
        raise HTTPException(status_code=422, detail=M("yuz.bos-dosya"))
    _tur_dogrula(veri)
    return veri


def _istemci_ip(request: Request) -> str:
    from app.services.ag_ayari import deneme_anahtari
    return deneme_anahtari(request)


def _hata_cevir(e: Exception, islem: str):
    """Servis hatalarını HTTP'ye çevir — iç ayrıntı sızdırmadan.

    SECURITY.md § 9: istemciye stack trace / iç yol dönme. Buradaki `ValueError`
    ve `RuntimeError` metinleri **kullanıcıya yazılmak üzere** üretilmiş
    cümlelerdir ("Yüz bulunamadı…"); beklenmeyen her şey genel mesaja düşer.
    """
    from app.services.insightface_havuzu import KutuphaneYok

    if isinstance(e, KutuphaneYok):
        # Eylem gerçekten yapılamıyor → 503 doğru. Yetenek SORUSU değil bu.
        raise HTTPException(status_code=503, detail=str(e))
    if isinstance(e, ValueError):
        raise HTTPException(status_code=422, detail=str(e))
    if isinstance(e, RuntimeError):
        raise HTTPException(status_code=503, detail=str(e))
    logger.error("%s hatası: %s", islem, e, exc_info=True)
    raise HTTPException(status_code=500,
                        detail=M("yuz.islem-hatasi", islem=M(f"yuz.islem.{islem}")))


# ══════════════════════════════════════════════════════════════════════════
#  Açık uçlar — giriş ekranı
# ══════════════════════════════════════════════════════════════════════════

@router.get("/login-status")
@limiter.limit("60/minute")
async def login_status(request: Request):
    """Yüzle giriş denenebilir mi? **Ad sızdırmaz.**"""
    from app.services import face_multi_auth, login_guard

    yetenek = face_multi_auth.yetenek()
    return {
        **yetenek,
        "enabled": FACE_AUTH_ENABLED,
        "enrolled": face_multi_auth.owner_enrolled(),
        "guard": login_guard.state(_istemci_ip(request)),
    }


@router.post("/liveness/challenge")
@limiter.limit("20/minute")
async def liveness_challenge(request: Request):
    """Canlılık meydan okuması üret (tek kullanımlık, süreli)."""
    _kapali_mi()
    from app.services import face_liveness, login_guard

    ip = _istemci_ip(request)
    kalan = login_guard.locked_for(login_guard.FACE, ip)
    if kalan > 0:
        # Kilitliyken meydan okuma dağıtmak, kilidi anlamsız kılar.
        raise HTTPException(
            status_code=429,
            detail=login_guard.lock_message(
                login_guard.FACE, kalan,
                login_guard.locked_for(login_guard.PASSWORD, ip) == 0),
            headers={"Retry-After": str(int(kalan))},
        )
    return await face_liveness.olustur(ip)


@router.post("/warmup")
@limiter.limit("20/minute")
async def warmup(request: Request):
    """Modeli **arka planda** yüklemeye başlat — çağıran beklemez.

    🔑 **Neden var:** yüzle girişte model yüklemesi (2-4 sn CPU) bugüne kadar
    kareler gönderildikten *sonra* başlıyordu, yani kullanıcının beklediği
    sürenin üstüne biniyordu. Oysa istemci ondan önce ~6 sn boyunca zaten
    meşgul: geri sayım (2,1 sn) + 40 kare toplama (4 sn). Bu uç o ölü zamanı
    doldurur — davranış değişmez, yalnız bekleme öne alınır.

    ⚠️ **Yanıt "model hazır" demek DEĞİL**, "yükleme başladı" demek. Hazır
    olmasını beklemek çağıranın işine yaramaz; beklerse kazanç sıfırlanır.

    🔴 Yetenek sorusu hata koduyla sorulmaz (modül başlığındaki ledger notu):
    kütüphane inmemişse **200 + `basladi: false`** döner. Isıtma bir
    iyileştirmedir; başarısızlığı giriş akışını durdurmamalı.
    """
    _kapali_mi()
    import asyncio  # noqa: PLC0415 — yalnız bu uçta gerekli

    from app.services import insightface_havuzu as havuz

    var, sebep = havuz.kullanilabilir()
    if not var:
        return {"basladi": False, "hazir": False, "sebep": sebep}

    if havuz.yuklu("TANIMA"):
        return {"basladi": False, "hazir": True}

    def _isit() -> None:
        try:
            havuz.al("TANIMA")
        except Exception as e:  # noqa: BLE001 — ısıtma sessizce başarısız olabilir
            # Gerçek giriş isteği aynı hatayı kendi yolunda üretecek ve
            # kullanıcıya oradan söyleyecek; burada susmak doğru.
            logger.warning("Model ısıtma başarısız: %s", e)

    asyncio.get_running_loop().run_in_executor(None, _isit)
    return {"basladi": True, "hazir": False}


@router.post("/frames")
@limiter.limit("40/minute")
async def frames(
    request: Request,
    challenge_id: str = Form(...),
    parca: int = Form(...),
    files: list[UploadFile] = File(...),
):
    """Kare dizisinin bir **dilimini** erkenden yolla — analiz şimdiden başlasın.

    🔑 **Neden var (2026-09-10):** istemci 40 kareyi ~4 sn boyunca topluyor ve
    sunucu o sürede boş duruyordu; analiz ancak son kare toplandıktan sonra
    başlıyor, kullanıcı ikisinin **toplamını** bekliyordu. Dilimler toplanırken
    gönderilince analiz toplamanın altına gizlenir.

    ⚠️ **Bu uç TOKEN ÜRETMEZ ve giriş kararı vermez** — yalnız kare biriktirir.
    Karar tek yerde kalır: `/verify`. Deneme kilidi (`login_guard`) da orada
    işler; burada bir deneme sayılmaz, çünkü burada bir deneme yapılmıyor.

    Sıra (`parca`) **istemciden alınır**: kırpma sayımı açık→kapalı→açık
    geçişlerini arayan bir durum makinesidir, ağ sırası bozulursa yanlış sayar.
    Aynı sıra ikinci kez kabul edilmez (tekrar oynatma kapısı).

    🔴 Yetenek/durum sorusu değil, **eylem**: meydan okuma geçersizse 422 döner.
    """
    _kapali_mi()
    from app.config import AUTH_TOKEN
    from app.services import app_lock, face_liveness, face_multi_auth, login_guard

    # ⚠️ `/verify`'ın ön koşulları BURADA DA uygulanır. Bu uç kimlik
    # doğrulamasından muaf; yüzle giriş hiç mümkün değilken (kilit kurulu değil
    # ya da kayıtlı sahip yok) açık bırakmak, hiçbir girişe yol açmayan bir
    # kanalı bedavaya açmak olurdu. Kapı `verify` ile aynı yerde durmalı.
    if not AUTH_TOKEN and not app_lock.kurulu():
        raise HTTPException(
            status_code=503,
            detail=M("yuz.kilit-yok"))
    if not face_multi_auth.owner_enrolled():
        raise HTTPException(status_code=404,
                            detail=M("yuz.kayitli-yuz-yok"))

    ip = _istemci_ip(request)
    kalan = login_guard.locked_for(login_guard.FACE, ip)
    if kalan > 0:
        # Kilitliyken kare biriktirmek, kilidin CPU tarafını anlamsız kılardı.
        raise HTTPException(
            status_code=429,
            detail=login_guard.lock_message(
                login_guard.FACE, kalan,
                login_guard.locked_for(login_guard.PASSWORD, ip) == 0),
            headers={"Retry-After": str(int(kalan))},
        )

    toplam = 0
    kareler: list[bytes] = []
    for f in files:
        veri = await _kare_oku(f, _MAX_DIZI_KARE)
        toplam += len(veri)
        if toplam > _MAX_DIZI_TOPLAM:
            raise HTTPException(status_code=413, detail=M("canlilik.dizi-buyuk"))
        kareler.append(veri)

    try:
        sonuc = await face_liveness.parca_ekle(challenge_id, ip, kareler, parca)
    except HTTPException:
        raise
    except Exception as e:
        _hata_cevir(e, "kare")

    if not sonuc["ok"]:
        raise HTTPException(status_code=422, detail=sonuc["reason"])
    return sonuc


@router.post("/verify")
@limiter.limit("10/minute")
async def verify(
    request: Request,
    challenge_id: str = Form(...),
    files: list[UploadFile] = File(...),
    parca: int | None = Form(default=None),
):
    """Yüzle giriş — kare dizisi + canlılık. Başarıda bir giriş token'ı döner.

    Hangi token döndüğü kurulu olan kapıya bağlıdır:

    - **Uygulama kilidi** kuruluysa → kısa ömürlü **oturum token'ı**
      (`app_lock.oturum_ac()`). Tercih edilen yol: parolanın kendisi değildir,
      yalnız bellekte yaşar ve uygulama kapanınca ölür.
    - Yoksa `AUTH_TOKEN` → tünel kurulumlarında yüzle giriş bugüne kadar böyle
      çalışıyordu, davranış korunuyor.

    ⚠️ Başarısızlıkta **kimin tanındığı söylenmez** — açık uçtur; "yüz X'e
    benziyor" demek kayıtlı kişilerin adını sızdırır.
    """
    _kapali_mi()
    from app.config import AUTH_TOKEN
    from app.services import app_lock, face_multi_auth, login_guard

    kilit_kurulu = app_lock.kurulu()
    if not AUTH_TOKEN and not kilit_kurulu:
        # Açılacak bir kapı yok. 503 doğru: yetenek sorusu değil, ortamda bu
        # eylemin karşılığı yok. (Kullanıcı önce Ayarlar → Güvenlik'ten kilit
        # kurmalı; yüz tanımanın kendisi kilitten bağımsız çalışmaya devam eder.)
        raise HTTPException(
            status_code=503,
            detail=M("yuz.kilit-yok"))

    ip = _istemci_ip(request)
    kalan = login_guard.locked_for(login_guard.FACE, ip)
    if kalan > 0:
        raise HTTPException(
            status_code=429,
            detail=login_guard.lock_message(
                login_guard.FACE, kalan,
                login_guard.locked_for(login_guard.PASSWORD, ip) == 0),
            headers={"Retry-After": str(int(kalan))},
        )

    if not face_multi_auth.owner_enrolled():
        raise HTTPException(status_code=404,
                            detail=M("yuz.kayitli-yuz-yok"))

    toplam = 0
    kareler: list[bytes] = []
    for f in files:
        veri = await _kare_oku(f, _MAX_DIZI_KARE)
        toplam += len(veri)
        if toplam > _MAX_DIZI_TOPLAM:
            raise HTTPException(status_code=413, detail=M("canlilik.dizi-buyuk"))
        kareler.append(veri)

    try:
        sonuc = await face_multi_auth.verify_owner(kareler, challenge_id, ip, parca)
    except HTTPException:
        raise
    except Exception as e:
        _hata_cevir(e, "dogrulama")

    if sonuc["ok"]:
        login_guard.record_success(login_guard.FACE, ip)
        # Kilit kuruluysa oturum token'ı üstündür — AUTH_TOKEN'ı döndürmek,
        # parolanın kendisini istemciye vermek demektir.
        token = app_lock.oturum_ac() if kilit_kurulu else AUTH_TOKEN
        return {"ok": True, "token": token}

    basarisiz = login_guard.record_fail(login_guard.FACE, ip)
    if basarisiz["locked"]:
        raise HTTPException(
            status_code=429,
            detail=login_guard.lock_message(
                login_guard.FACE, basarisiz["lock_seconds"],
                login_guard.locked_for(login_guard.PASSWORD, ip) == 0),
            headers={"Retry-After": str(int(basarisiz["lock_seconds"]))},
        )

    kalan_hak = basarisiz["remaining"]
    ek = " " + Mc("yuz.kalan-hak", kalan_hak) if kalan_hak is not None else ""
    canlilik = sonuc.get("liveness") or {}

    if sonuc.get("verdict") == "liveness_failed":
        # Canlılığın sebebi söylenebilir: kullanıcıya ne yapacağını anlatır ve
        # kayıtlı kimlikler hakkında hiçbir şey açıklamaz.
        raise HTTPException(status_code=401,
                            detail=f"{canlilik.get('reason') or M('canlilik.dogrulanamadi')}{ek}")
    if sonuc.get("verdict") == "uncertain":
        raise HTTPException(
            status_code=401,
            detail=M("yuz.belirsiz") + ek)
    raise HTTPException(status_code=401, detail=M("yuz.eslesmedi") + ek)


# ══════════════════════════════════════════════════════════════════════════
#  Korumalı uçlar
# ══════════════════════════════════════════════════════════════════════════

@router.get("/status")
@limiter.limit("60/minute")
async def status(request: Request):
    """Tam durum — sahip adı dâhil (token arkasında).

    `canlilik` + `sahip_kaydi`/`sahip_ornek` HQ kimlik kartı için (09-27): kart
    "sahibin kaç örneği var, kilit fotoğrafla açılabilir mi" diye soruyor.
    """
    from app.config import FACE_LIVENESS_REQUIRED
    from app.services import face_multi_auth

    sahip = face_multi_auth.get_owner()
    try:
        kayit = face_multi_auth.sahip_kaydi()
    except Exception as e:   # depo okunamasa da durum cevabı ölmesin
        logger.warning("Sahip kaydı okunamadı: %s", e)
        kayit = None
    return {
        **face_multi_auth.yetenek(),
        "enabled": FACE_AUTH_ENABLED,
        "enrolled": bool(sahip),
        "owner": sahip,
        "canlilik": FACE_LIVENESS_REQUIRED,
        "sahip_kaydi": kayit["name"] if kayit else None,
        "sahip_ornek": kayit["encodings"] if kayit else 0,
    }


@router.post("/enroll")
@limiter.limit("20/minute")
async def enroll(request: Request, file: UploadFile = File(...)):
    """Sahibin yüzünü kaydeder (ilk kayıt ya da ek kare)."""
    _kapali_mi()
    from app.services import face_multi_auth

    veri = await _kare_oku(file)
    try:
        res = await face_multi_auth.enroll_owner(veri)
    except HTTPException:
        raise
    except Exception as e:
        _hata_cevir(e, "yuz-kaydi")
    mesaj = Mc("yuz.kaydedildi", res["total_encodings"], sahip=res["owner"])
    if res.get("warnings"):
        mesaj += " ⚠ " + " ".join(res["warnings"])
    return {"ok": True, "message": mesaj, **res}


@router.post("/register")
@limiter.limit("20/minute")
async def register(request: Request, name: str = Form(...), file: UploadFile = File(...)):
    """Kişiyi isme göre kaydeder. Aynı isimle farklı açı/ışık kareleri eklenebilir."""
    _kapali_mi()
    from app.services import face_multi_auth

    if not name or not name.strip():
        raise HTTPException(status_code=422, detail=M("yuz.isim-bos"))
    veri = await _kare_oku(file)
    try:
        return await face_multi_auth.register_face(name.strip(), veri)
    except HTTPException:
        raise
    except Exception as e:
        _hata_cevir(e, "kayit")


@router.post("/scan")
@limiter.limit("60/minute")
async def scan(request: Request, file: UploadFile = File(...), notify: bool = Form(True)):
    """Karedeki kişiyi tanır.

    Tanındıysa Event Bus'a `face_recognized` düşer → Yuki sesli selamlar.
    İki fren: `notify=false` (canlı tarama modu her turda selamlamasın) ve
    `FACE_GREET_COOLDOWN` (aynı kişi için tekrar selamlama atlanır).
    Tanıma sonucu her koşulda döner; frenler yalnız SESE uygulanır.
    """
    _kapali_mi()
    from app.services import face_multi_auth

    veri = await _kare_oku(file)
    try:
        sonuc = await face_multi_auth.recognize_face(veri)
    except HTTPException:
        raise
    except Exception as e:
        _hata_cevir(e, "tarama")

    # Kimlik kartındaki GİRİŞİ DENE bunu okur: tanınan kişi sahip mi (yazımdan bağımsız)
    sonuc["sahip"] = bool(sonuc.get("known")) and face_multi_auth.sahip_mi(sonuc.get("name"))

    if sonuc["known"] and notify and face_multi_auth.should_greet(sonuc.get("name")):
        try:
            from app.services.event_bus import bus
            await bus.publish("face_recognized",
                              {"name": sonuc["name"], "confidence": sonuc["confidence"]})
        except Exception as bus_hata:
            logger.warning("Event Bus face_recognized gönderilemedi: %s", bus_hata)
    return sonuc


@router.get("/list")
@limiter.limit("60/minute")
async def list_registered(request: Request):
    _kapali_mi()
    from app.services import face_multi_auth
    try:
        return {"faces": await face_multi_auth.list_faces()}
    except Exception as e:
        _hata_cevir(e, "liste")


@router.get("/quality")
@limiter.limit("30/minute")
async def quality_report(request: Request):
    """Kayıt kalitesi: kişi-içi tutarlılık, en yakın yabancı, aykırı kayıtlar."""
    _kapali_mi()
    from app.services import face_multi_auth
    try:
        return await face_multi_auth.face_quality()
    except Exception as e:
        _hata_cevir(e, "kalite")


@router.delete("/encoding/{enc_id}")
@limiter.limit("30/minute")
async def delete_single_encoding(request: Request, enc_id: int):
    """Tek yüz kaydını siler — aykırı kayıt temizliği."""
    _kapali_mi()
    from app.services import face_multi_auth
    try:
        return await face_multi_auth.delete_encoding(enc_id)
    except HTTPException:
        raise
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        _hata_cevir(e, "kayit-silme")


@router.delete("/{name}")
@limiter.limit("30/minute")
async def delete_person(request: Request, name: str, sahip: int = 0):
    """Kişiyi ve tüm kayıtlarını siler. Sahibi silmek `?sahip=1` ister (yoksa 409) —
    sahip silinince yüzle giriş kapanır."""
    _kapali_mi()
    from app.services import face_multi_auth
    try:
        return await face_multi_auth.delete_face(name, sahip_onay=bool(sahip))
    except HTTPException:
        raise
    except face_multi_auth.SahipSilmeOnayi as e:
        raise HTTPException(status_code=409, detail=str(e))
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        _hata_cevir(e, "silme")
