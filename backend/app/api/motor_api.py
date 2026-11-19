"""`POST /api/motor/kapan` — motoru zarifçe kapat. Gerekçe → app/motor_kapanis.py

Kapı: yalnız Electron'un verdiği oturum anahtarıyla açılmış motorda çalışır. Çerezi
`YerelKapi` doğrular (en dış katman); uygulama kilidinin Bearer kapısı bu yola uygulanmaz
(`main.py::auth_middleware`), çünkü kapanışı isteyen Electron/bekçi kilit token'ını taşımaz —
kilitli kurulumda kapanış yine zorla olurdu. Anahtar yoksa (elle başlatılmış geliştirme motoru)
uç kapalıdır: o durumda çerez kuralı da kapalı olduğundan kimliksiz bir istek motoru kapatabilirdi.
"""

from fastapi import APIRouter
from fastapi.responses import JSONResponse

from app import motor_kapanis
from app.yerel_kapi import oturum_anahtari

router = APIRouter(prefix="/api/motor", tags=["motor"])

KAPAN_YOLU = "/api/motor/kapan"


@router.post("/kapan")
async def motor_kapan():
    if not oturum_anahtari():
        return JSONResponse({"detail": "oturum anahtarı yok — uç kapalı"}, status_code=403)
    if not motor_kapanis.iste():
        return JSONResponse({"detail": "bu motor zarif kapanışı desteklemiyor (reload modu)"}, status_code=409)
    return JSONResponse({"durum": "kapaniyor"}, status_code=202)
