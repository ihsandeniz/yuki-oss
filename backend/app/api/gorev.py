"""Atölye görev uçları — Yuki Atölye v2, Faz 0c (görünürlük) + Faz 0d (telefondan başlatma).

  GET  /api/gorev                        görev listesi (kısa görünüm, `gorev.ozet`) +
                                         isteyenin bağlamı, onay kipi, tür kartları
  POST /api/gorev/baslat                 {"tur","ad","istek","tavan"?}
                                         yerel → görev hemen koşar · dış → `bekliyor` taslak +
                                         tek kullanımlık `onay_kodu` (yalnız bu yanıtta)
  POST /api/gorev/{tur}/{ad}/onayla      {"kod"?} — yerel kodsuz · dış yalnız `dokunus` kipinde, kodla
  POST /api/gorev/{tur}/{ad}/durdur      her bağlamdan açık; taslağı iptal eder
  POST /api/gorev/{tur}/{ad}/devam       gövde {"onay": true, "uzat"?: {...}} — dış bağlamdan KAPALI
  GET  /api/gorev/{tur}/{ad}/onizleme    Faz 1: önizlemeyi (127.0.0.1:8011, CSP sandbox) açar,
                                         adresini + son doğrulamayı döner — dış bağlamdan KAPALI

Harness H1 — iş sırası (`services/gorev_kuyrugu.py`). Bu uçlar `/{tur}/{ad}/…` uçlarından
ÖNCE tanımlanır: `/oneri/<id>/onayla` yoksa tür adı "oneri" sayılıp görev onayına giderdi.
  GET  /api/gorev/oneri                  sıra (kısa görünüm, `gorev_kuyrugu.ozet`)
  POST /api/gorev/oneri                  {"tur","ad","istek","gerekce"?} — yerel; dış 403
  POST /api/gorev/oneri/{id}/onayla      {"kod"?} — yerel kodsuz · dış yalnız `dokunus`
                                         kipinde iki dokunuş (kodsuz → `onay_kodu`, kodlu → onay)
  POST /api/gorev/oneri/{id}/reddet      her bağlamdan açık
  POST /api/gorev/oneri/{id}/ertele      H4 SONRA — her bağlamdan açık; ertesi açılışta yeniden sorulur
  POST /api/gorev/oneri/surdur           restart/DURDUR sonrası sırayı sürdürür — dış 403

Harness H5:
  POST /api/gorev/tumunu-durdur          TÜMÜNÜ DURDUR — her bağlamdan açık (telefon dahil, ⑭);
                                         koşanı durdurur, sırayı/önerileri erteler, öneri
                                         turunu gün sonuna kadar kapatır. Origin kapısı (⑮)

Araştırma Sahnesi (`/{tur}/{ad}/…` uçlarından ÖNCE — "sahne" tür adıyla çakışmasın):
  GET  /api/gorev/sahne                  kayıtlı sahnelerin kısa listesi + toplam API harcaması
  GET  /api/gorev/sahne/{ad}             bir sahnenin blokları (SAHNE.json) — yeniden açma

Kimlik: ① yerel anahtar kapısı (`yerel_kapi`) ve uygulama kilidi bu uçların önündedir
② dış başlatma/onay yalnız `ALLOWED_ORIGINS` içindeki https adreslerinden (`_origin_kapisi`)
③ dış taslak kodla ya da masaüstünden onaylanır.
Bağlam: her uç `mark_request_context` (= `atolye.baglam.isaretle`) çağırır; çağırmazsa
varsayılan DIŞ'tır (fail-closed).
"""

from __future__ import annotations

from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, ConfigDict, Field

from app.services import gorev_kuyrugu
from app.services.gorev import GorevHatasi, get_gorev_servisi, onay_kipi, ozet
from app.services.atolye.baglam import isaretle as mark_request_context

from app import config as _config


def atolye_kapisi() -> None:
    """`ATOLYE` kapalıysa (varsayılan) her `/api/gorev*` ucu 404 — kayıtsız uçla aynı yanıt.

    Bayrak istek anında okunur (`app.config.ATOLYE`), modül yüklenirken değil: ayar
    değişince router yeniden kurulmadan kapı açılır/kapanır. Bekçi: tests/test_atolye_bayrak.py
    """
    if not getattr(_config, "ATOLYE", False):
        raise HTTPException(status_code=404, detail="Not Found")


router = APIRouter(prefix="/api/gorev", tags=["gorev"], dependencies=[Depends(atolye_kapisi)])


class DevamIstegi(BaseModel):
    onay: bool = False
    uzat: dict | None = None


class BaslatIstegi(BaseModel):
    # extra=forbid: tanınmayan alan (ör. "tavanlar", "adim") sessizce yutulmaz → 422.
    model_config = ConfigDict(extra="forbid")
    tur: str = Field(max_length=40)
    ad: str = Field(max_length=40)
    istek: str = Field(max_length=4000)
    tavan: dict | None = None        # yalnız yerel; dış bağlamda 403 (⑬)


class OnayIstegi(BaseModel):
    model_config = ConfigDict(extra="forbid")
    kod: str | None = Field(default=None, max_length=200)


class OneriIstegi(BaseModel):
    # Kaynak alanı YOK: uçtan açılan öneri her zaman `kullanici` (öneri motoru H4 içeriden yazar).
    model_config = ConfigDict(extra="forbid")
    tur: str = Field(max_length=40)
    ad: str = Field(max_length=40)
    istek: str = Field(max_length=4000)
    gerekce: str = Field(default="", max_length=300)


def dis_originler() -> list[str]:
    """Dış başlatmanın kabul edildiği Origin'ler: `ALLOWED_ORIGINS` içindeki https adresleri
    (kullanıcının kendi eklediği güvenilir dış adres). localhost bu listede DEĞİL."""
    from app.config import ALLOWED_ORIGINS
    return [o for o in ALLOWED_ORIGINS if o.startswith("https://")]


def _origin_kapisi(request: Request, dis: bool) -> None:
    """Başlat/onay uçlarının Origin kapısı.

    · Dış istek: Origin ZORUNLU ve `dis_originler()`'den biri (tam eşleşme).
    · Yerel istek: Origin yoksa (CLI, curl) geçer; varsa `ALLOWED_ORIGINS`'te olmalı —
      masaüstündeki yabancı bir sayfanın localhost'a istek atması (CSRF) kapanır.
    Origin istemci beyanıdır: tarayıcı dışı istemci taklit edebilir. Bu kapı kimlik değil,
    tarayıcı yolunu daraltan katmandır; kimlik oturum anahtarı + uygulama kilidi."""
    origin = request.headers.get("origin", "")
    if dis:
        if origin not in dis_originler():
            raise HTTPException(403, "dış başlatma yalnız izinli https adresinden")
        return
    if origin:
        from app.config import ALLOWED_ORIGINS
        if origin not in ALLOWED_ORIGINS:
            raise HTTPException(403, "izin verilmeyen Origin")


def _hata(e: GorevHatasi) -> HTTPException:
    metin = str(e)
    if e.http:
        return HTTPException(e.http, metin)
    if "dış bağlam" in metin:
        return HTTPException(403, metin)
    if metin.startswith("görev yok"):
        return HTTPException(404, metin)
    return HTTPException(409 if "koşuyor" in metin or "en çok" in metin else 400, metin)


def _tur_kartlari() -> list[dict]:
    out = []
    for t in get_gorev_servisi().turler.values():
        out.append({"ad": t.ad, "aciklama": t.aciklama,
                    "tavanlar": {"adim": t.tavanlar.adim, "sure_sn": t.tavanlar.sure_sn,
                                 "token": t.tavanlar.token}})
    return out


@router.get("")
async def gorev_listesi(request: Request) -> dict:
    dis = mark_request_context(request)
    s = get_gorev_servisi()
    kok, ev = str(s.kok), str(Path.home())
    return {"gorevler": [ozet(d) for d in s.liste()],
            "baglam": "dis" if dis else "yerel", "onay_kipi": onay_kipi(),
            "turler": _tur_kartlari(),
            "kok": "~" + kok[len(ev):] if kok.startswith(ev + "/") else kok}


@router.post("/baslat")
async def gorev_baslat(govde: BaslatIstegi, request: Request) -> dict:
    dis = mark_request_context(request)
    _origin_kapisi(request, dis)
    try:
        d = await get_gorev_servisi().baslat(govde.tur, govde.ad, govde.istek,
                                             tavan=govde.tavan, taslak=dis)
    except GorevHatasi as e:
        raise _hata(e) from None
    cevap = ozet(d)
    if d.get("onay_kodu"):
        # Kod yalnız bu yanıtta; dokunus kipinde telefon ikinci dokunuşta geri yollar.
        cevap["onay_kodu"] = d["onay_kodu"] if onay_kipi() == "dokunus" else None
    return cevap


@router.get("/oneri")
async def oneri_listesi(request: Request) -> dict:
    dis = mark_request_context(request)
    try:
        sira = gorev_kuyrugu.get_gorev_kuyrugu().liste()
    except GorevHatasi as e:
        raise _hata(e) from None
    return {"oneriler": [gorev_kuyrugu.ozet(k) for k in sira],
            "baglam": "dis" if dis else "yerel", "onay_kipi": onay_kipi()}


@router.post("/oneri")
async def oneri_ac(govde: OneriIstegi, request: Request) -> dict:
    dis = mark_request_context(request)
    _origin_kapisi(request, dis)
    try:
        return gorev_kuyrugu.ozet(gorev_kuyrugu.get_gorev_kuyrugu().oner(
            govde.tur, govde.ad, govde.istek, gerekce=govde.gerekce, kaynak="kullanici"))
    except GorevHatasi as e:
        raise _hata(e) from None


@router.post("/oneri/surdur")
async def oneri_surdur(request: Request) -> dict:
    dis = mark_request_context(request)
    _origin_kapisi(request, dis)
    try:
        k = gorev_kuyrugu.get_gorev_kuyrugu().surdur()
    except GorevHatasi as e:
        raise _hata(e) from None
    return {"baslayan": gorev_kuyrugu.ozet(k) if k else None}


@router.post("/oneri/tur")
async def oneri_turu_calistir(request: Request) -> dict:
    """Öneri motorunu bir kez koşturur (yalnız yerel). Motor yalnız `oneri` kaydı yazar."""
    dis = mark_request_context(request)
    if dis:
        raise HTTPException(403, "öneri turu yalnız bu bilgisayardan")
    _origin_kapisi(request, dis)
    return await gorev_kuyrugu.get_gorev_kuyrugu().oneri_motoru().tur()


@router.post("/tumunu-durdur")
async def tumunu_durdur(request: Request) -> dict:
    dis = mark_request_context(request)
    _origin_kapisi(request, dis)
    try:
        return await gorev_kuyrugu.get_gorev_kuyrugu().tumunu_durdur()
    except GorevHatasi as e:
        raise _hata(e) from None


@router.post("/oneri/{qid}/onayla")
async def oneri_onayla(qid: str, govde: OnayIstegi, request: Request) -> dict:
    dis = mark_request_context(request)
    _origin_kapisi(request, dis)
    try:
        k = gorev_kuyrugu.get_gorev_kuyrugu().onayla(qid, kod=govde.kod)
    except GorevHatasi as e:
        raise _hata(e) from None
    cevap = gorev_kuyrugu.ozet(k)
    if k.get("onay_kodu"):
        cevap["onay_kodu"], cevap["onay_son"] = k["onay_kodu"], k.get("onay_son")
    return cevap


@router.post("/oneri/{qid}/reddet")
async def oneri_reddet(qid: str, request: Request) -> dict:
    dis = mark_request_context(request)
    _origin_kapisi(request, dis)
    try:
        return gorev_kuyrugu.ozet(gorev_kuyrugu.get_gorev_kuyrugu().reddet(qid))
    except GorevHatasi as e:
        raise _hata(e) from None


@router.post("/oneri/{qid}/ertele")
async def oneri_ertele(qid: str, request: Request) -> dict:
    dis = mark_request_context(request)
    _origin_kapisi(request, dis)
    try:
        return gorev_kuyrugu.ozet(gorev_kuyrugu.get_gorev_kuyrugu().ertele(qid))
    except GorevHatasi as e:
        raise _hata(e) from None


@router.get("/sahne")
async def sahne_listesi(request: Request) -> dict:
    mark_request_context(request)
    from app.services.atolye import sahne
    s = get_gorev_servisi()
    return {"sahneler": s.sahneler(), "harcama_usd": sahne.harcama_toplam(s.kok),
            "tavan_usd": sahne.tavan_usd()}


@router.get("/sahne/{ad}")
async def sahne_getir(ad: str, request: Request) -> dict:
    mark_request_context(request)
    try:
        return get_gorev_servisi().sahne_oku(f"sahne/{ad}")
    except GorevHatasi as e:
        raise _hata(e) from None


@router.post("/{tur}/{ad}/onayla")
async def gorev_onayla(tur: str, ad: str, govde: OnayIstegi, request: Request) -> dict:
    dis = mark_request_context(request)
    _origin_kapisi(request, dis)
    try:
        return ozet(await get_gorev_servisi().onayla(f"{tur}/{ad}", kod=govde.kod))
    except GorevHatasi as e:
        raise _hata(e) from None


@router.post("/{tur}/{ad}/durdur")
async def gorev_durdur(tur: str, ad: str, request: Request) -> dict:
    mark_request_context(request)
    try:
        return ozet(await get_gorev_servisi().durdur(f"{tur}/{ad}"))
    except GorevHatasi as e:
        raise _hata(e) from None


@router.post("/{tur}/{ad}/devam")
async def gorev_devam(tur: str, ad: str, govde: DevamIstegi, request: Request) -> dict:
    mark_request_context(request)
    try:
        return ozet(await get_gorev_servisi().devam(f"{tur}/{ad}", onay=govde.onay, uzat=govde.uzat))
    except GorevHatasi as e:
        raise _hata(e) from None


@router.get("/{tur}/{ad}/onizleme")
async def gorev_onizleme(tur: str, ad: str, request: Request) -> dict:
    """Önizleme yalnız masaüstünde anlamlı (127.0.0.1) — dış bağlamdan 403, telefona adres
    sızdırılmaz. Sunucu süreç başına bir kez açılır (`onizleme.paylasilan`)."""
    if mark_request_context(request):
        raise HTTPException(403, "önizleme yalnız masaüstünden")
    s = get_gorev_servisi()
    try:
        d = s.durum(f"{tur}/{ad}")
    except GorevHatasi as e:
        raise _hata(e) from None
    from app.services.atolye import onizleme
    try:
        srv = onizleme.paylasilan(s.kok)
    except OSError as e:
        raise HTTPException(503, f"önizleme portu açılamadı: {e.strerror}") from None
    son = (d.get("dogrulama") or [None])[-1]
    return {"url": srv.url(tur, ad), "dogrulama": son}
