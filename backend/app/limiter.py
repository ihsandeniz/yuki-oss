"""Rate limiter singleton — döngüsel import'u önlemek için ayrı modül."""

from slowapi import Limiter
from starlette.requests import Request


def _get_rate_limit_key(request: Request) -> str:
    """İstemci anahtarı — X-Forwarded-For'un değerine güvenme (istemci uydurur).

    `request.client.host` de uvicorn `proxy_headers` açıkken bu başlıktan yeniden yazılır;
    vekil başlıklı istekler tek kovada sayılır → `ag_ayari.deneme_anahtari` (SEC-F002).
    """
    from app.services.ag_ayari import deneme_anahtari
    return deneme_anahtari(request)


limiter = Limiter(key_func=_get_rate_limit_key)
