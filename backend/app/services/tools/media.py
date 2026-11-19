"""Medya, ekran ve pencere yönetimi araçları."""
import asyncio
import base64
import io
import logging
import os
import re
import subprocess
import sys
import tempfile

from PIL import Image
from mss import mss

from app.config import MEDIA_CONTROL_ENABLED, APP_WHITELIST, APP_ALIASES, GAME_REGISTRY
from app.services.tools._base import _build_wayland_env

logger = logging.getLogger(__name__)


def take_screenshot() -> str:
    """Takes a screenshot. Tries grim (Wayland) first, falls back to mss (X11)."""
    try:
        tmp_fd, tmp_img = tempfile.mkstemp(suffix=".png")
        os.close(tmp_fd)
        try:
            grim_env = _build_wayland_env()
            grim_ok = False
            try:
                subprocess.run(
                    ["grim", tmp_img],
                    check=True,
                    timeout=6,
                    env=grim_env,
                    capture_output=True,
                )
                grim_ok = True
            except (subprocess.CalledProcessError, FileNotFoundError, subprocess.TimeoutExpired):
                pass

            if grim_ok:
                img = Image.open(tmp_img)
            else:
                with mss() as sct:
                    monitor = sct.monitors[1]
                    sct_img = sct.grab(monitor)
                    img = Image.frombytes("RGB", sct_img.size, sct_img.bgra, "raw", "BGRX")

            img.thumbnail((1024, 1024))
        finally:
            if os.path.exists(tmp_img):
                os.unlink(tmp_img)

        if img.mode in ("RGBA", "P"):
            img = img.convert("RGB")

        buffered = io.BytesIO()
        img.save(buffered, format="JPEG", quality=80)
        img_base64 = base64.b64encode(buffered.getvalue()).decode("utf-8")
        return f"SCREENSHOT_DATA:{img_base64}"
    except Exception as e:
        import traceback
        error_detail = traceback.format_exc()
        logger.error("Ekran görüntüsü hatası: %s", error_detail)
        return f"Hata: Ekran görüntüsü alınırken teknik bir sorun oluştu. Detay: {str(e)}"


async def send_screenshot_to_chat() -> str:
    """Ekran görüntüsü alır ve chat'e görsel olarak gönderir (analiz yapmaz)."""
    from app.services.event_bus import bus
    raw = await asyncio.to_thread(take_screenshot)
    if not raw.startswith("SCREENSHOT_DATA:"):
        return raw
    b64 = raw[len("SCREENSHOT_DATA:"):]
    await bus.publish("image_msg", {"data": b64, "mime": "image/jpeg"})
    return "Ekran görüntüsü chate gönderildi."


_MEDIA_ACTIONS_LINUX: dict[str, str] = {
    "play":         "playerctl play",
    "pause":        "playerctl pause",
    "play_pause":   "playerctl play-pause",
    "next":         "playerctl next",
    "prev":         "playerctl previous",
    "previous":     "playerctl previous",
    "stop":         "playerctl stop",
    "volume_up":    "playerctl volume 0.05+",
    "volume_down":  "playerctl volume 0.05-",
    "mute":         "playerctl volume 0",
}

# Windows sanal tuş kodları (WinUser.h). Medya tuşları olan/olmayan her klavyede
# çalışır — tuşa fiziksel olarak basılmış gibi sentezlenir, sistemin o anki aktif
# medya oturumuna (Spotify/tarayıcı/YouTube Music…) gider.
_MEDIA_VK_WIN: dict[str, int] = {
    "play":         0xB3,  # VK_MEDIA_PLAY_PAUSE
    "pause":        0xB3,
    "play_pause":   0xB3,
    "next":         0xB0,  # VK_MEDIA_NEXT_TRACK
    "prev":         0xB1,  # VK_MEDIA_PREV_TRACK
    "previous":     0xB1,
    "stop":         0xB2,  # VK_MEDIA_STOP
    "volume_up":    0xAF,  # VK_VOLUME_UP
    "volume_down":  0xAE,  # VK_VOLUME_DOWN
    "mute":         0xAD,  # VK_VOLUME_MUTE
}

# Windows'ta karşılığı Linux'takiyle birebir aynı DEĞİL — kullanıcıya doğrusunu söyle.
# (Sessiz "yaptım" demek, yapmamaktan kötüdür: kullanıcı neden çalışmadığını anlamaz.)
_MEDIA_NOT_WIN: dict[str, str] = {
    "play":       " (Windows'ta çal/duraklat tek tuştur — çalıyorsa duraklatır)",
    "pause":      " (Windows'ta çal/duraklat tek tuştur — duraklamışsa çalar)",
    "volume_up":  " — sistem sesi",
    "volume_down": " — sistem sesi",
    "mute":       " — sistem sesi (aç/kapa)",
}

_MEDIA_ETIKET: dict[str, str] = {
    "play": "Çal", "pause": "Duraklat", "play_pause": "Çal/duraklat",
    "next": "Sonraki parça", "prev": "Önceki parça", "previous": "Önceki parça",
    "stop": "Durduruldu", "volume_up": "Ses artırıldı", "volume_down": "Ses azaltıldı",
    "mute": "Sessize alındı",
}


def _control_media_windows(action: str) -> str:
    """Windows'ta medya tuşunu sentezler (ctypes → user32.keybd_event).

    Dış program gerektirmez. playerctl **Linux'a özeldir** (MPRIS/D-Bus) — Windows'ta
    hiç yoktur; eskiden burada da o çağrılıyordu ve komut sessizce başarısız oluyordu.
    """
    import ctypes

    vk = _MEDIA_VK_WIN.get(action)
    if vk is None:
        return f"Hata: Geçersiz medya aksiyonu '{action}'. Geçerli: {list(_MEDIA_VK_WIN)}"
    try:
        user32 = ctypes.WinDLL("user32", use_last_error=True)  # type: ignore[attr-defined]
        KEYEVENTF_EXTENDEDKEY = 0x0001
        KEYEVENTF_KEYUP = 0x0002
        user32.keybd_event(vk, 0, KEYEVENTF_EXTENDEDKEY, 0)
        user32.keybd_event(vk, 0, KEYEVENTF_EXTENDEDKEY | KEYEVENTF_KEYUP, 0)
    except Exception as e:  # noqa: BLE001 — kullanıcıya sebebi söylenmeli
        logger.warning("Windows medya tuşu gönderilemedi (%s): %s", action, e)
        return f"Medya tuşu gönderilemedi: {e}"

    return _MEDIA_ETIKET.get(action, action) + _MEDIA_NOT_WIN.get(action, "") + "."


def control_media(action: str) -> str:
    """Medya oynatıcıyı kontrol eder (Linux: playerctl · Windows: medya tuşları)."""
    if not MEDIA_CONTROL_ENABLED:
        return "Medya kontrolü devre dışı."

    act = (action or "").lower().strip()

    if sys.platform == "win32":
        return _control_media_windows(act)

    if sys.platform == "darwin":
        return (
            "Medya kontrolü macOS'ta henüz desteklenmiyor "
            "(playerctl Linux'a, medya tuşları Windows'a özel)."
        )

    cmd = _MEDIA_ACTIONS_LINUX.get(act)
    if not cmd:
        return f"Hata: Geçersiz medya aksiyonu '{action}'. Geçerli: {list(_MEDIA_ACTIONS_LINUX)}"
    return _playerctl(cmd)


def _playerctl(cmd: str) -> str:
    """Sabit argv'li playerctl çağrısı (kabuk yok; cmd yalnız _MEDIA_ACTIONS_LINUX'tan gelir)."""
    try:
        r = subprocess.run(cmd.split(), shell=False, capture_output=True, text=True, timeout=15)
    except FileNotFoundError:
        return "Hata: playerctl bulunamadı."
    except subprocess.TimeoutExpired:
        return "Hata: playerctl zaman aşımına uğradı."
    out = [f"[STDOUT]\n{r.stdout.strip()}"] if r.stdout.strip() else []
    if r.stderr.strip():
        out.append(f"[STDERR]\n{r.stderr.strip()}")
    return "\n\n".join(out) or "Komut başarıyla çalıştırıldı (çıktı yok)."


def _norm_game(s: str) -> str:
    """Oyun adını eşleştirme için normalize et: küçük harf, alfanümerik + boşluk."""
    return re.sub(r'[^a-z0-9]+', ' ', s.lower()).strip()


def _match_game(query: str):
    """Oyun adını GAME_REGISTRY'de fuzzy eşleştir → (kanonik_ad, appid) veya None."""
    q = _norm_game(query)
    if not q:
        return None
    norm = {name: _norm_game(name) for name in GAME_REGISTRY}
    # 1) tam eşleşme
    for name, n in norm.items():
        if n == q:
            return name, GAME_REGISTRY[name]
    # 2) alt-dize (her iki yön)
    for name, n in norm.items():
        if q in n or n in q:
            return name, GAME_REGISTRY[name]
    # 3) anlamlı kelime kesişimi (>=4 harf — "2","iii" gibi yanlış eşleşmeyi önler)
    qwords = {w for w in q.split() if len(w) >= 4}
    for name, n in norm.items():
        if qwords & set(n.split()):
            return name, GAME_REGISTRY[name]
    return None


def launch_game(game_name: str) -> str:
    """Steam oyununu AppID ile başlatır (steam://rungameid/<appid>).

    Kullanıcı oyun istemcisinin kendisini ("steam", "lutris", "heroic") isterse
    open_application'a yönlendirir — böylece "Steam'i aç" da çalışır.
    """
    _q = (game_name or "").lower().strip()
    # Oyun istemcisi/launcher'ın kendisi mi istendi? → uygulama olarak aç
    if _q in APP_WHITELIST:
        return open_application(_q)

    match = _match_game(game_name)
    if not match:
        return (
            f"Hata: '{game_name}' oyun kaydında yok. "
            f"Kayıtlı oyunlar: {', '.join(GAME_REGISTRY)}. "
            f"Steam istemcisini açmak için uygulama olarak 'steam'i başlat."
        )
    name, appid = match
    try:
        subprocess.Popen(
            ["steam", f"steam://rungameid/{appid}"],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            start_new_session=True,
            env=_build_wayland_env(),
        )
        return f"'{name}' başlatılıyor (Steam AppID {appid})."
    except FileNotFoundError:
        return "Hata: 'steam' bulunamadı (PATH'te değil veya kurulu değil)."
    except Exception as e:
        return f"Hata: Oyun başlatılamadı: {e}"


def update_game(game_name: str) -> str:
    """Steam oyununu günceller ama BAŞLATMAZ (steam://install/<appid>).

    launch_game'in aksine steam://rungameid kullanmaz — Steam bu URI ile
    indirme/güncellemeyi yapar, tamamlanınca oyunu otomatik açmaz.
    """
    match = _match_game(game_name)
    if not match:
        return (
            f"Hata: '{game_name}' oyun kaydında yok. "
            f"Kayıtlı oyunlar: {', '.join(GAME_REGISTRY)}."
        )
    name, appid = match
    try:
        subprocess.Popen(
            ["steam", f"steam://install/{appid}"],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            start_new_session=True,
            env=_build_wayland_env(),
        )
        return f"'{name}' güncelleniyor (Steam AppID {appid}) — güncelleme bitince oyun otomatik AÇILMAYACAK."
    except FileNotFoundError:
        return "Hata: 'steam' bulunamadı (PATH'te değil veya kurulu değil)."
    except Exception as e:
        return f"Hata: Güncelleme başlatılamadı: {e}"


def close_game(game_name: str) -> str:
    """Açık oyun penceresini hyprctl ile bulup kapatır (PID → SIGTERM)."""
    import json as _json
    import signal as _signal

    # Aranacak adaylar: kullanıcının verdiği ad + registry kanonik adı
    candidates = {_norm_game(game_name)}
    match = _match_game(game_name)
    if match:
        candidates.add(_norm_game(match[0]))
    candidates.discard("")
    if not candidates:
        return "Hata: Geçerli bir oyun adı verilmedi."

    try:
        result = subprocess.run(
            ["hyprctl", "clients", "-j"],
            capture_output=True, text=True, timeout=5,
        )
        clients = _json.loads(result.stdout) if result.returncode == 0 else []
    except Exception:
        clients = []

    uygulama_penceresi = None
    for c in clients:
        hay = _norm_game(f"{c.get('class', '')} {c.get('title', '')}")
        hay_words = set(hay.split())
        matched = any(cand in hay for cand in candidates) or any(
            w in hay_words for cand in candidates for w in cand.split() if len(w) >= 4
        )
        if matched:
            # Bilinen uygulama oyun değildir: başlığında oyun adı geçen tarayıcı ya da terminal kapanmaz.
            sinif = str(c.get("class", "")).lower().rsplit(".", 1)[-1]
            if sinif in APP_WHITELIST:
                uygulama_penceresi = uygulama_penceresi or c.get("class")
                continue
            pid = c.get("pid")
            title = c.get("title", "") or c.get("class", "")
            if not pid or int(pid) <= 1:
                return f"'{game_name}' penceresi bulundu ama PID alınamadı."
            try:
                os.kill(int(pid), _signal.SIGTERM)
                return f"'{title}' kapatıldı (PID {pid})."
            except ProcessLookupError:
                return f"'{game_name}' süreci zaten kapalı."
            except PermissionError:
                return f"Hata: '{game_name}' kapatma izni reddedildi (PID {pid})."
            except Exception as e:
                return f"Hata: Oyun kapatılamadı: {e}"

    if uygulama_penceresi:
        return (f"'{game_name}' için oyun penceresi yok; eşleşen pencere bir uygulama "
                f"({uygulama_penceresi}), kapatmadım.")
    return f"'{game_name}' açık pencereler arasında bulunamadı — şu an çalışmıyor olabilir."


# ── YouTube Music (ytmdesktop2) kontrol — port 13091 REST API ──────────
# API auth'suz. Etkinleştirme: uygulama Ayarlar → API/Entegrasyon toggle.
_YTM_API = "http://127.0.0.1:13091"
# Türkçe/sinonim aksiyon → API operasyonu (POST /track/<op>)
_YTM_OPS = {
    "play": "play", "çal": "play", "cal": "play", "başlat": "play", "devam": "play",
    "pause": "pause", "duraklat": "pause", "durdur": "pause", "dur": "pause",
    "toggle": "toggle", "play_pause": "toggle", "çaldur": "toggle",
    "next": "next", "sonraki": "next", "ileri_şarkı": "next", "geç": "next",
    "prev": "prev", "previous": "prev", "önceki": "prev", "geri_şarkı": "prev",
    "forward": "forward", "ileri": "forward", "ileri_sar": "forward",
    "backward": "backward", "geri": "backward", "geri_sar": "backward",
    "like": "like", "beğen": "like", "begen": "like",
    "dislike": "dislike", "beğenme": "dislike",
    "shuffle": "shuffle", "karıştır": "shuffle", "karistir": "shuffle",
    "repeat": "repeat", "tekrarla": "repeat", "tekrar": "repeat",
}
# Mevcut şarkı bilgisi isteyen aksiyonlar (GET /track)
_YTM_INFO = {"current", "track", "song", "now", "info", "durum", "ne çalıyor", "ne caliyor", "şu an", "su an", "çalan", "calan", "state"}


def youtube_music(action: str, value: str = "") -> str:
    """YouTube Music (ytmdesktop2) oynatma kontrolü — port 13091 REST API.

    Aksiyonlar: play/pause/toggle/next/prev/forward/backward/like/dislike/
    shuffle/repeat (kontrol) · current/track (şu an çalan şarkı).
    """
    import httpx
    act = (action or "").lower().strip()

    try:
        # Mevcut şarkı bilgisi
        if act in _YTM_INFO:
            r = httpx.get(f"{_YTM_API}/track", timeout=4.0)
            r.raise_for_status()
            t = r.json()
            if not t:
                return "Şu an YouTube Music'te bir şey çalmıyor."
            title = t.get("title") or t.get("name") or "?"
            artist = t.get("author") or t.get("artist") or t.get("subtitle") or ""
            return f"Çalan: {title}" + (f" — {artist}" if artist else "")

        op = _YTM_OPS.get(act)
        if not op:
            return (
                f"Geçersiz aksiyon '{action}'. Geçerli: çal, duraklat, sonraki, önceki, "
                f"ileri, geri, beğen, beğenme, karıştır, tekrarla, durum."
            )
        body = {}
        if op == "seek" and value:
            body = {"position": value}
        r = httpx.post(f"{_YTM_API}/track/{op}", json=body, timeout=4.0)
        r.raise_for_status()
        _label = {
            "play": "Oynatıldı", "pause": "Duraklatıldı", "toggle": "Çal/duraklat",
            "next": "Sonraki şarkı", "prev": "Önceki şarkı",
            "forward": "İleri sarıldı", "backward": "Geri sarıldı",
            "like": "Beğenildi", "dislike": "Beğenilmedi",
            "shuffle": "Karıştırma açıldı/kapandı", "repeat": "Tekrar modu değişti",
        }.get(op, op)
        return f"YouTube Music: {_label}."
    except (httpx.ConnectError, httpx.ConnectTimeout):
        return (
            "YouTube Music API'sine bağlanılamadı (port 13091 kapalı). "
            "Uygulamada Ayarlar → API/Entegrasyon'u etkinleştir."
        )
    except Exception as e:
        return f"YouTube Music kontrol hatası: {e}"


def _resolve_app(app_name: str) -> str | None:
    """Sözle söylenen adı whitelist binary'sine çözer (alias + normalize + alt-dize)."""
    raw = (app_name or "").lower().strip()
    if raw in APP_WHITELIST:
        return raw
    if APP_ALIASES.get(raw) in APP_WHITELIST:
        return APP_ALIASES[raw]
    norm = re.sub(r'[^a-z0-9]+', ' ', raw).strip()
    if APP_ALIASES.get(norm) in APP_WHITELIST:
        return APP_ALIASES[norm]
    # Normalize edilmiş whitelist eşleşmesi (tam veya anlamlı alt-dize)
    for w in APP_WHITELIST:
        wn = re.sub(r'[^a-z0-9]+', ' ', w).strip()
        if wn == norm or (len(norm) >= 4 and norm in wn):
            return w
    return None


def open_application(app_name: str, url: str = "") -> str:
    """Uygulamayı arka planda başlatır. Güvenlik: sadece beyaz listede olanlar."""
    _name = _resolve_app(app_name)
    if not _name:
        return (
            f"Hata: '{app_name}' uygulama listesinde yok. "
            f"İzin verilenler: {APP_WHITELIST}"
        )
    try:
        cmd = [_name]
        if url and _name in ("firefox", "chromium", "brave-browser"):
            cmd.append(url)
        # GUI uygulamaları için Wayland/Hyprland ortamını garantiye al
        # (backend systemd/farklı oturumdan başlatılsa bile ekrana erişebilsin)
        subprocess.Popen(
            cmd,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            start_new_session=True,
            env=_build_wayland_env(),
        )
        return f"'{_name}' başlatıldı." + (f" URL: {url}" if url else "")
    except FileNotFoundError:
        return f"Hata: '{_name}' sistemde bulunamadı (kurulu değil veya PATH'te yok)."
    except Exception as e:
        return f"Hata: Uygulama başlatılamadı: {e}"
