"""Devices API — Remote Agent yönetimi + WebSocket sunucu (kademe: **Ultra**).

Riskli eylemler (writefile · deletefile · killproc) varsayılan KAPALI: `services/cihaz_yetki.py`.

🔴 **2026-09-18 — bu modül uyandırılmadan önce açık bir kapısı vardı.**
`/ws/agent` şöyle korunuyordu:

    if AUTH_TOKEN and not secrets.compare_digest(_token, AUTH_TOKEN):

Üründe `AUTH_TOKEN` varsayılanı **boş** → `and`in solu falsy → koşul kısa devre →
`ws.close()` hiç çağrılmaz. Canlı ölçüldü: token vermeden bağlanılıp sahte cihaz
kaydedildi. Kimlik doğrulaması artık `services/cihaz_eslestirme.py`'de ve bir sır
**boş olamaz**: yoksa reddeder, atlamaz.

⚠️ **İKİ router var.** `router` (REST) kademe kapısını `dependencies` ile alır;
`ws_router` prefix'sizdir ve `Depends` ile korunamaz — WebSocket el sıkışmasında
`HTTPException` doğru davranış değildir, `ws.close(code=…)` gerekir. O yüzden WS
kapısı handler'ın **ilk satırlarında** el-içi yazılır. Birini kapatıp öbürünü
unutmak bu dosyanın en kolay hatasıdır; `tests/test_cihaz_kapisi.py` ikisini de ölçer.
"""
from __future__ import annotations

import json
import logging
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Request, WebSocket, WebSocketDisconnect
from pydantic import BaseModel

from app.limiter import limiter
from app.mesajlar import M
from app.services import cihaz_eslestirme as ce
from app.services import device_manager as dm

log = logging.getLogger(__name__)


def _izin_var() -> bool:
    """Kademe izni — **fail-closed**: entitlements patlarsa kapalı sayılır."""
    try:
        from app.services import yetki
        return bool(yetki.feature_allowed("device_manager"))
    except Exception:
        return False


def require_devices() -> None:
    """Cihaz yönetimi kademe kapısı — **Ultra** (REST uçları için)."""
    if not _izin_var():
        raise HTTPException(
            status_code=403,
            detail=M("cihaz.ultra-gerekli"),
        )


router    = APIRouter(prefix="/api/devices", tags=["devices"],
                     dependencies=[Depends(require_devices)])
ws_router = APIRouter()  # /ws/agent — prefix yok; kapısı handler içinde (yukarı bak)


def _yerel_ip() -> str:
    """Bu makinenin yerel ağdaki IP'si — dışarıya paket GÖNDERMEDEN.

    UDP soketi `connect` çağrısı yalnız yönlendirme tablosuna bakar, veri
    göndermez; yönlendirilemez bir adres seçildiği için internet gerekmez
    (kapalı ağda da doğru cevap verir). `gethostbyname(gethostname())`
    kullanılmadı: çoğu Linux'ta 127.0.1.1 döndürür ve QR sessizce bozulur.
    """
    import socket
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        s.connect(("10.255.255.255", 1))
        return s.getsockname()[0]
    except Exception:
        return "127.0.0.1"
    finally:
        s.close()


def _ag_durumu() -> dict:
    """Cihaz gerçekten bağlanabilir mi — panelde DÜRÜST gösterilir.

    🔴 Ürün varsayılanı `HOST=127.0.0.1`: sunucu yalnız bu bilgisayardan
    erişilebilir, yani QR okutulsa bile telefon bağlanamaz. Bunu saklamak
    "çalışıyor gibi görünen ama çalışmayan" bir ekran üretirdi.
    """
    from app.config import HOST, PORT
    agda = HOST not in ("127.0.0.1", "localhost", "::1", "")
    ip = _yerel_ip() if agda else "127.0.0.1"
    return {
        "host": HOST,
        "port": PORT,
        "yerel_ip": _yerel_ip(),
        "ws_adres": f"ws://{ip}:{PORT}/ws/agent",
        "agda_erisilebilir": agda,
        "uyari": None if agda else M("cihaz.ag-yalniz-yerel"),
    }


async def _ag_tam() -> dict:
    """`_ag_durumu` + ağa açma ayarı (soket ölçümü iş parçacığında: bağlanma denemesi bloklar)."""
    import asyncio
    from app.services import ag_ayari
    ag = _ag_durumu()
    ag.update(await asyncio.to_thread(ag_ayari.durum_ozeti, ag["yerel_ip"], ag["port"]))
    return ag


class AgAyari(BaseModel):
    acik: bool


class IzinAyari(BaseModel):
    eylem:   str
    acik:    bool
    anahtar: str = ""


# ── REST API ─────────────────────────────────────────────────────────── #

@router.get("")
@limiter.limit("100/minute")
async def list_devices(request: Request):
    return [_dev_dict(d) for d in dm.get_all()]


# ⚠️ Aşağıdaki sabit yollar `/{device_id}`'den ÖNCE tanımlanmak ZORUNDA —
# sonra gelselerdi `/{device_id}` onları yakalar ve `eslestirme` bir cihaz
# kimliği sanılırdı (404 döner, sebebi hiçbir yerde yazmaz).

@router.post("/eslestirme")
@limiter.limit("10/minute")
async def eslestirme_baslat(request: Request):
    """QR için kod + bağlantı adresi üretir (tek kullanımlık, 5 dk).

    Adres **yerel IP** ile verilir: kullanıcının alan adı yok (geliştirici kararı
    2026-09-18), telefon ancak aynı ağdaki IP'ye bağlanabilir.
    """
    kod = ce.kod_uret()
    ag = _ag_durumu()
    return {
        **kod,
        "adres": ag["ws_adres"],
        "baglanti": f"{ag['ws_adres']}?eslestirme={kod['kod']}",
        "ag": ag,
    }


@router.delete("/eslestirme")
@limiter.limit("30/minute")
async def eslestirme_iptal(request: Request):
    ce.kod_iptal()
    return {"ok": True}


@router.get("/eslestirilmis")
@limiter.limit("100/minute")
async def eslestirilmis_cihazlar(request: Request):
    """Eşleştirilmiş cihazlar + o an bağlı olup olmadıkları."""
    bagli = {d.device_id for d in dm.get_all()}
    return [{**c, "bagli": c["id"] in bagli} for c in ce.cihazlar()]


@router.delete("/eslestirilmis/{cihaz_id}")
@limiter.limit("30/minute")
async def eslestirme_kaldir(request: Request, cihaz_id: str):
    if not ce.cihaz_sil(cihaz_id):
        raise HTTPException(404, M("cihaz.bulunamadi"))
    # 🔴 Kayıt silinince açık bağlantı KESİLMELİ: token yalnız bağlanırken denetlenir,
    # kesilmezse "Kaldır"a basılan cihaz soket açık kaldığı sürece komut almaya
    # devam eder (panel "kaldırıldı" derken). Bağlı değilse yapılacak bir şey yok.
    d = dm.get(cihaz_id)
    if d is not None:
        try:
            await d.ws.close(code=4401, reason=M("cihaz.ws-taninmiyor"))
        except Exception:
            pass
        dm.unregister(cihaz_id)
    return {"ok": True}


@router.get("/ag")
@limiter.limit("60/minute")
async def ag_durumu(request: Request):
    return await _ag_tam()


@router.put("/ag")
@limiter.limit("10/minute")
async def ag_ayarla(request: Request, govde: AgAyari):
    """Yuki'yi yerel ağa aç / kapat (ayar; yeniden başlatınca geçerli olur).

    🔴 AÇMAK uygulama kilidi ister — kilit yoksa 409 (arayüzün düğmeyi pasif tutması yetmez, kapı burada).
    KAPATMAK her zaman serbest: kilit olsa da olmasa da, ağ açık da kapalı da olsa."""
    from app.services import ag_ayari
    if govde.acik and not ag_ayari.kilit_kurulu():
        raise HTTPException(status_code=409, detail=M("cihaz.ag-kilit-yok"))
    ok, sebep = ag_ayari.yaz(govde.acik)
    if not ok:
        raise HTTPException(status_code=500, detail=M("ayar.kaydedilemedi", sebep=sebep))
    return {"ok": True, "ag": await _ag_tam()}


@router.get("/izinler")
@limiter.limit("60/minute")
async def izin_durumu(request: Request):
    from app.services import cihaz_yetki
    return cihaz_yetki.durum()


@router.put("/izinler")
@limiter.limit("10/minute")
async def izin_ayarla(request: Request, govde: IzinAyari):
    """Riskli eylemi (dosya yazma/silme, program kapatma) aç / kapat.

    🔴 AÇMAK erişim anahtarı ister: `AUTH_TOKEN` boşsa 409, anahtar yanlış/boşsa 403.
    KAPATMAK her zaman serbest."""
    from app.services import cihaz_yetki
    if govde.eylem not in cihaz_yetki.RISKLI_EYLEMLER:
        raise HTTPException(status_code=400, detail=M("cihaz.eylem-yok"))
    if govde.acik:
        if not cihaz_yetki.anahtar_kurulu():
            raise HTTPException(status_code=409, detail=M("cihaz.izin-anahtar-yok"))
        if not cihaz_yetki.anahtar_dogru(govde.anahtar):
            raise HTTPException(status_code=403, detail=M("cihaz.izin-anahtar-yanlis"))
    ok, sebep = cihaz_yetki.yaz(govde.eylem, govde.acik)
    if not ok:
        raise HTTPException(status_code=500, detail=M("ayar.kaydedilemedi", sebep=sebep))
    return {"ok": True, **cihaz_yetki.durum()}


@router.get("/{device_id}")
@limiter.limit("100/minute")
async def get_device(request: Request, device_id: str):
    d = dm.get(device_id)
    if not d:
        raise HTTPException(404, M("cihaz.bagli-degil"))
    return _dev_dict(d)


#: Ajanın yaptığı eylemler. Komut çalıştırma ("exec") açık kaynak sürümde YOK:
#: eski bir ajan programı hâlâ biliyor olsa da sunucu bu listede olmayanı göndermez.
#: 🔴 writefile/deletefile/killproc listede ama VARSAYILAN KAPALI — `services/cihaz_yetki.py`.
IZINLI_EYLEMLER = frozenset({
    "sysinfo", "screenshot", "proclist", "filelist", "readfile", "writefile", "deletefile",
    "killproc", "netinfo", "notify", "clipboard_get", "clipboard_set", "diskusage", "ping",
})


class CmdRequest(BaseModel):
    action:  str
    args:    dict = {}
    timeout: float = 30.0


@router.post("/{device_id}/command")
@limiter.limit("30/minute")
async def send_command(request: Request, device_id: str, body: CmdRequest):
    d = dm.get(device_id)
    if not d:
        raise HTTPException(404, M("cihaz.bagli-degil"))
    if body.action not in IZINLI_EYLEMLER:
        raise HTTPException(400, M("cihaz.eylem-yok"))
    from app.services import cihaz_yetki
    if not cihaz_yetki.izinli(body.action):
        raise HTTPException(403, M("cihaz.izin-kapali"))
    result = await d.send_command(body.action, body.args, body.timeout)
    return result


def _dev_dict(d) -> dict:
    return {
        "device_id":    d.device_id,
        "hostname":     d.hostname,
        "os":           d.os,
        "os_version":   d.os_version,
        "arch":         d.arch,
        "ip":           d.ip,
        "cpu_percent":  d.cpu_percent,
        "cpu_count":    d.cpu_count,
        "ram_total":    d.ram_total,
        "ram_used":     d.ram_used,
        "ram_percent":  d.ram_percent,
        "disk_total":   d.disk_total,
        "disk_used":    d.disk_used,
        "disk_percent": d.disk_percent,
        "uptime":       d.uptime,
        "connected_at": d.connected_at,
        "last_seen":    d.last_seen,
    }


# ── Agent WebSocket ──────────────────────────────────────────────────── #

@ws_router.websocket("/ws/agent")
async def agent_ws(ws: WebSocket):
    """Cihaz bağlantısı — iki yol: eşleştirme kodu (ilk kez) veya cihaz tokeni.

    🔴 Eski hâli `if AUTH_TOKEN and …` idi ve AUTH_TOKEN üründe boş olduğu için
    kapı hiç çalışmıyordu (ölçüldü 2026-09-18). Burada sır boş olamaz: `eslestirme`
    de `cihaz` de yoksa bağlantı **reddedilir**.
    """
    # ① Kademe kapısı — Ultra. REST tarafı `Depends` ile alır, burada el-içi:
    #    WS el sıkışmasında HTTPException'ın karşılığı yok, close(code) gerekir.
    if not _izin_var():
        await ws.close(code=4403, reason=M("cihaz.ws-ultra"))
        return

    # ①b Ağ kapısı: ağa açma ayarıyla açılmış süreçte kilit YOKSA uzaktan (loopback dışı) gelen ajan reddedilir.
    #    Cihaz token'ı kilit token'ı değildir (uzaktaki ajanın kilit oturumu olamaz) ama kilit kalkmışken
    #    eşleşmiş cihaz da girmemeli. Aynı şart bağlantı sürerken her mesajda yeniden bakılır (aşağıda).
    from app.services import ag_ayari
    _istemci = getattr(ws.client, "host", None) if ws.client else None
    if not ag_ayari.uzak_izin(_istemci, ag_ayari.kilit_kurulu()):
        await ws.close(code=4403, reason=M("cihaz.ag-kilitsiz-uzak"))
        return

    # ② Kimlik. `eslestirme` TEK KULLANIMLIK koddur; doğrulanınca kalıcı token üretir
    #    ve cihaza bir kez gönderilir. Sonraki bağlantılar `cihaz=<token>` kullanır.
    eslestirme_kodu = ws.query_params.get("eslestirme", "")
    cihaz_tokeni = ws.query_params.get("cihaz", "")
    yeni_token: Optional[str] = None

    if eslestirme_kodu:
        yeni_token = ce.kod_dogrula(eslestirme_kodu, ws.query_params.get("ad", ""))
        if not yeni_token:
            await ws.close(code=4401, reason=M("cihaz.ws-kod-gecersiz"))
            return
        kayit = ce.token_dogrula(yeni_token)
    elif cihaz_tokeni:
        kayit = ce.token_dogrula(cihaz_tokeni)
        if not kayit:
            await ws.close(code=4401, reason=M("cihaz.ws-taninmiyor"))
            return
    else:
        await ws.close(code=4401, reason=M("cihaz.ws-kimlik-yok"))
        return

    if not kayit:                      # savunma: token üretildi ama okunamadı
        await ws.close(code=4401, reason=M("cihaz.ws-dogrulanamadi"))
        return

    await ws.accept()

    # ③ Cihaz kimliği SUNUCUDAN gelir, mesajdan değil. Eskiden `msg.get("device_id")`
    #    kullanılıyordu — cihaz kendini başka bir cihaz gibi tanıtıp onun kaydını
    #    ezebilirdi. Artık eşleştirme kaydındaki id bağlayıcı.
    device_id: Optional[str] = kayit["id"]

    if yeni_token:
        # Token cihaza YALNIZ BURADA, bir kez gider. Diske düz yazılmadı (sha256).
        await ws.send_text(json.dumps({
            "type": "eslestirildi",
            "cihaz_token": yeni_token,
            "cihaz_id": device_id,
        }))

    try:
        async for raw in ws.iter_text():
            # Kilit bağlantı sürerken kalkarsa uzak ajan bir sonraki mesajda (heartbeat ~15 sn) kesilir.
            # Süreç ortasında anında kesmek için kilit kaldırma ucunda ajan listesine dokunmak gerekirdi; yapılmadı.
            if not ag_ayari.uzak_izin(_istemci, ag_ayari.kilit_kurulu()):
                await ws.close(code=4403, reason=M("cihaz.ag-kilitsiz-uzak"))
                break
            try:
                msg      = json.loads(raw)
                msg_type = msg.get("type")

                # 🔴 `msg.get("device_id")` ARTIK KULLANILMIYOR. Üç dalın
                # üçü de mesajdaki id'yi öncelerdi; eşleştirilmiş bir cihaz
                # başkasının id'sini yazıp onun kaydını ezebilir, komut
                # sonuçlarını onun adına gönderebilirdi. Kimlik el sıkışmada
                # belirlenir ve bu döngü boyunca DEĞİŞMEZ.
                if msg_type == "register":
                    dm.register(device_id, msg, ws)
                    ce.gorundu(device_id)

                elif msg_type == "heartbeat":
                    dm.update(device_id, msg)
                    ce.gorundu(device_id)

                elif msg_type == "result":
                    did    = device_id
                    dev    = dm.get(did) if did else None
                    cmd_id = msg.get("cmd_id", "")
                    if dev and cmd_id:
                        dev.resolve(cmd_id, {
                            "data":  msg.get("data"),
                            "error": msg.get("error"),
                        })

            except Exception as e:
                log.warning("Agent mesaj hatası: %s", e)

    except WebSocketDisconnect:
        pass
    except Exception as e:
        log.warning("Agent WS hatası: %s", e)
    finally:
        if device_id:
            dm.unregister(device_id)
