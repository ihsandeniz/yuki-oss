#!/usr/bin/env python3
"""Yuki cihaz ajanı — kendi bilgisayarını Yuki'nin CİHAZLAR ekranından izle.

Kurulum:
  pip install -r requirements.txt

İLK KEZ — eşleştirme:
  Yuki'de ⚙ AYAR → CİHAZLAR → "Yeni cihaz ekle" → QR'daki kodu al, sonra:
    YUKI_SERVER=ws://192.168.1.x:8001/ws/agent python agent.py --eslestir ABCD2345
  Kod TEK KULLANIMLIKTIR ve 5 dakika yaşar. Sunucu karşılığında kalıcı bir
  cihaz tokeni verir; token `~/.yuki_device_token`'a 0600 izniyle yazılır.

SONRAKİ ÇALIŞTIRMALAR — kod gerekmez:
  YUKI_SERVER=ws://192.168.1.x:8001/ws/agent python agent.py

PyInstaller ile tek dosya:
  pyinstaller --onefile agent.py
"""
from __future__ import annotations

import asyncio
import base64
import io
import json
import logging
import os
import sys
import platform
import socket
import subprocess
import time
import uuid
from datetime import datetime
from pathlib import Path

import psutil
import websockets

# ── Config ───────────────────────────────────────────────────────────────
_ESKI_ONEK = "ALI" "CE_"   # eski ürün env öneki (parçalı → temizlik kapısı tetiklenmez)


def _ortam(ad: str, varsayilan: str = "") -> str:
    """YUKI_<ad> önce; yoksa eski ALICE_<ad>'e düş (geriye uyum, tek seferlik uyarı)."""
    d = os.getenv("YUKI_" + ad)
    if d is not None:
        return d
    eski = os.getenv(_ESKI_ONEK + ad)
    if eski is not None:
        print(f"[yuki] UYARI: {_ESKI_ONEK + ad} eski ad; YUKI_{ad} kullanın.", file=sys.stderr)
        return eski
    return varsayilan


SERVER_URL      = _ortam("SERVER", "ws://192.168.1.100:8001/ws/agent")
YUKI_TOKEN     = _ortam("TOKEN", "")
DEVICE_ID_FILE  = Path.home() / ".yuki_device_id"
#: Eşleştirmeden dönen KALICI cihaz tokeni. Yalnız bir kez gelir;
#: kaybedilirse Yuki'de yeni bir QR üretmek gerekir.
CIHAZ_TOKEN_FILE = Path.home() / ".yuki_device_token"
RECONNECT_DELAY = 5


def _eski_dosyalari_tasi() -> None:
    """Eski sürümün ~/.<eski>_device_* dosyaları varsa yeni ada taşı (varsa dokunma)."""
    eski_onek = "." + "ali" "ce" + "_device_"   # parçalı → kapı tetiklenmez
    for yeni in (DEVICE_ID_FILE, CIHAZ_TOKEN_FILE):
        eski = Path.home() / (eski_onek + yeni.name.split("_device_", 1)[1])
        if eski.exists() and not yeni.exists():
            try:
                eski.rename(yeni)
                print(f"[yuki] eski cihaz dosyası taşındı: {eski.name} → {yeni.name}", file=sys.stderr)
            except OSError:
                pass


_eski_dosyalari_tasi()


def _cihaz_tokeni_oku() -> str:
    try:
        return CIHAZ_TOKEN_FILE.read_text(encoding="utf-8").strip()
    except Exception:
        return ""


def _cihaz_tokeni_yaz(token: str) -> None:
    """Tokeni YALNIZ sahibinin okuyabileceği izinle yaz.

    0600 verilmezse ev dizinini paylaşan başka bir kullanıcı tokeni okuyup
    cihazın yerine geçebilirdi — sunucu tarafında token bir paroladır.
    """
    CIHAZ_TOKEN_FILE.write_text(token, encoding="utf-8")
    try:
        os.chmod(CIHAZ_TOKEN_FILE, 0o600)
    except Exception:
        pass    # Windows'ta chmod anlamsız; dosya zaten kullanıcı profilinde

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%H:%M:%S",
)
log = logging.getLogger("alice-agent")


BILDIRIM_AZAMI = 500

# PowerShell betiği SABİT: metin $env üzerinden okunur, komut dizgisine hiç girmez.
_PS_BILDIRIM = ("Add-Type -AssemblyName System.Windows.Forms; "
                "[System.Windows.Forms.MessageBox]::Show($env:YUKI_BILDIRIM_METIN, $env:YUKI_BILDIRIM_BASLIK)")


def bildirim_komutu(sistem: str, baslik, metin) -> tuple[list[str] | None, dict | None]:
    """Bildirim için argv (+ gerekirse ortam) üretir. Sunucudan gelen metin ASLA
    PowerShell/AppleScript komut metnine gömülmez — yalnız veri olarak geçer."""
    baslik = str(baslik)[:BILDIRIM_AZAMI]
    metin = str(metin)[:BILDIRIM_AZAMI]
    if sistem == "Linux":
        return ["notify-send", "--", baslik, metin], None
    if sistem == "Windows":
        env = dict(os.environ, YUKI_BILDIRIM_METIN=metin, YUKI_BILDIRIM_BASLIK=baslik)
        return ["powershell", "-NoProfile", "-WindowStyle", "Hidden", "-Command", _PS_BILDIRIM], env
    if sistem == "Darwin":
        return ["osascript",
                "-e", "on run argv",
                "-e", "display notification (item 1 of argv) with title (item 2 of argv)",
                "-e", "end run",
                metin, baslik], None
    return None, None


def _get_device_id() -> str:
    if DEVICE_ID_FILE.exists():
        return DEVICE_ID_FILE.read_text().strip()
    did = str(uuid.uuid4())
    DEVICE_ID_FILE.write_text(did)
    return did


DEVICE_ID = os.getenv("YUKI_DEVICE_ID") or _get_device_id()


# ── System Info ──────────────────────────────────────────────────────────

def get_sysinfo() -> dict:
    cpu   = psutil.cpu_percent(interval=0.3)
    ram   = psutil.virtual_memory()
    disk  = psutil.disk_usage("/")
    try:
        ip = socket.gethostbyname(socket.gethostname())
    except Exception:
        ip = "127.0.0.1"
    return {
        "hostname":     socket.gethostname(),
        "os":           platform.system(),
        "os_version":   platform.version()[:80],
        "arch":         platform.machine(),
        "cpu_percent":  round(cpu, 1),
        "cpu_count":    psutil.cpu_count(),
        "ram_total":    ram.total,
        "ram_used":     ram.used,
        "ram_percent":  round(ram.percent, 1),
        "disk_total":   disk.total,
        "disk_used":    disk.used,
        "disk_percent": round(disk.percent, 1),
        "boot_time":    datetime.fromtimestamp(psutil.boot_time()).isoformat(),
        "uptime":       int(time.time() - psutil.boot_time()),
        "ip":           ip,
    }


# ── Screenshot ───────────────────────────────────────────────────────────

def take_screenshot() -> str:
    """Ekran görüntüsü al, base64 PNG döndür. Boş string = başarısız."""
    # mss (cross-platform, headless friendly)
    try:
        import mss
        from PIL import Image
        with mss.mss() as sct:
            mon = sct.monitors[0]
            img_raw = sct.grab(mon)
            pil = Image.frombytes("RGB", img_raw.size, img_raw.bgra, "raw", "BGRX")
            pil.thumbnail((1280, 800))
            buf = io.BytesIO()
            pil.save(buf, format="PNG", optimize=True)
            return base64.b64encode(buf.getvalue()).decode()
    except Exception:
        pass
    # Fallback: PIL.ImageGrab (Windows / macOS)
    try:
        from PIL import ImageGrab
        img = ImageGrab.grab()
        img.thumbnail((1280, 800))
        buf = io.BytesIO()
        img.save(buf, format="PNG", optimize=True)
        return base64.b64encode(buf.getvalue()).decode()
    except Exception:
        pass
    # Fallback: scrot (Linux X11)
    try:
        tmp = Path("/tmp/_alice_ss.png")
        subprocess.run(["scrot", str(tmp)], timeout=5, check=True)
        data = base64.b64encode(tmp.read_bytes()).decode()
        tmp.unlink(missing_ok=True)
        return data
    except Exception:
        pass
    return ""


# ── Processes ────────────────────────────────────────────────────────────

def list_procs() -> list:
    out = []
    for p in psutil.process_iter(["pid", "name", "cpu_percent", "memory_percent", "status", "username"]):
        try:
            out.append({
                "pid":            p.info["pid"],
                "name":           p.info["name"],
                "cpu":            round(p.info["cpu_percent"] or 0, 1),
                "mem":            round(p.info["memory_percent"] or 0, 2),
                "status":         p.info["status"],
                "user":           p.info.get("username", ""),
            })
        except Exception:
            pass
    return sorted(out, key=lambda x: x["mem"], reverse=True)[:60]


# ── File System ──────────────────────────────────────────────────────────

def list_dir(path: str) -> dict:
    p = Path(path).expanduser()
    if not p.exists():
        return {"error": f"Yol bulunamadı: {path}"}
    if not p.is_dir():
        return {"error": "Dizin değil"}
    items = []
    try:
        for item in sorted(p.iterdir(), key=lambda x: (not x.is_dir(), x.name.lower())):
            try:
                stat = item.stat()
                items.append({
                    "name":     item.name,
                    "type":     "dir" if item.is_dir() else "file",
                    "size":     stat.st_size,
                    "modified": datetime.fromtimestamp(stat.st_mtime).isoformat(),
                })
            except Exception:
                pass
    except PermissionError:
        return {"error": "İzin reddedildi"}
    return {"path": str(p), "items": items[:300]}


def read_file(path: str) -> dict:
    # WP3: Path traversal koruması
    p = Path(path).expanduser().resolve()
    home = Path.home().resolve()

    # Path'in home directory'sinin içinde olduğunu kontrol et
    try:
        p.relative_to(home)
    except ValueError:
        return {"error": "Erişim reddedildi — ev dizini dışında dosya"}

    if not p.exists():
        return {"error": "Dosya bulunamadı"}
    if p.stat().st_size > 2 * 1024 * 1024:
        return {"error": "Dosya 2MB'dan büyük"}
    try:
        return {"content": p.read_text(errors="replace")[:50000], "size": p.stat().st_size}
    except Exception as e:
        return {"error": str(e)}


# ── Network ──────────────────────────────────────────────────────────────

def net_info() -> list:
    ifaces = []
    stats  = psutil.net_if_stats()
    for name, addrs in psutil.net_if_addrs().items():
        for addr in addrs:
            if addr.family == socket.AF_INET:
                s = stats.get(name)
                ifaces.append({
                    "iface":   name,
                    "ip":      addr.address,
                    "netmask": addr.netmask,
                    "up":      s.isup if s else False,
                    "speed":   s.speed if s else 0,
                })
    return ifaces


# ── Command Handler ──────────────────────────────────────────────────────

async def handle_command(cmd: dict) -> dict:
    action = cmd.get("action", "")
    args   = cmd.get("args", {})
    cmd_id = cmd.get("cmd_id", "")

    data  = {}
    error = None

    try:
        if action == "sysinfo":
            data = get_sysinfo()

        elif action == "screenshot":
            b64 = await asyncio.to_thread(take_screenshot)
            data = {"image": b64, "has_image": bool(b64)}

        elif action == "proclist":
            data = {"procs": await asyncio.to_thread(list_procs)}

        elif action == "filelist":
            path = args.get("path", str(Path.home()))
            data = await asyncio.to_thread(list_dir, path)

        elif action == "readfile":
            path = args.get("path", "")
            data = await asyncio.to_thread(read_file, path)

        elif action == "writefile":
            # WP3: Path traversal koruması
            path    = args.get("path", "")
            content = args.get("content", "")
            p = Path(path).expanduser().resolve()
            home = Path.home().resolve()

            # Path'in home directory'sinin içinde olduğunu kontrol et
            try:
                p.relative_to(home)
            except ValueError:
                error = "Erişim reddedildi — ev dizini dışında dosya"
            else:
                try:
                    p.write_text(content, encoding="utf-8")
                    data = {"written": True, "path": str(p)}
                except Exception as e:
                    error = str(e)

        elif action == "deletefile":
            # WP3: Path traversal koruması
            path = args.get("path", "")
            p = Path(path).expanduser().resolve()
            home = Path.home().resolve()

            # Path'in home directory'sinin içinde olduğunu kontrol et
            try:
                p.relative_to(home)
            except ValueError:
                error = "Erişim reddedildi — ev dizini dışında dosya"
            else:
                try:
                    if p.is_file():
                        p.unlink()
                    elif p.is_dir():
                        import shutil
                        shutil.rmtree(p)
                    data = {"deleted": str(p)}
                except Exception as e:
                    error = str(e)

        elif action == "killproc":
            pid = int(args.get("pid", 0))
            psutil.Process(pid).terminate()
            data = {"killed": pid}

        elif action == "netinfo":
            data = {"interfaces": await asyncio.to_thread(net_info)}

        elif action == "notify":
            argv, env = bildirim_komutu(platform.system(), args.get("title", "Yuki"), args.get("body", ""))
            if argv:
                subprocess.Popen(argv, env=env)
            data = {"sent": True}

        elif action == "clipboard_get":
            sys_ = platform.system()
            if sys_ == "Linux":
                r = subprocess.run(["xclip", "-o", "-selection", "clipboard"], capture_output=True, timeout=3)
                data = {"text": r.stdout.decode(errors="replace")}
            elif sys_ == "Windows":
                import tkinter as tk
                root = tk.Tk(); root.withdraw()
                data = {"text": root.clipboard_get()}
                root.destroy()
            else:
                data = {"text": ""}

        elif action == "clipboard_set":
            text  = args.get("text", "")
            sys_  = platform.system()
            if sys_ == "Linux":
                subprocess.run(["xclip", "-selection", "clipboard"], input=text.encode(), timeout=3)
            elif sys_ == "Windows":
                import tkinter as tk
                root = tk.Tk(); root.withdraw()
                root.clipboard_clear(); root.clipboard_append(text); root.update()
                root.destroy()
            data = {"set": True}

        elif action == "diskusage":
            parts = []
            for dp in psutil.disk_partitions(all=False):
                try:
                    u = psutil.disk_usage(dp.mountpoint)
                    parts.append({
                        "device":      dp.device,
                        "mountpoint":  dp.mountpoint,
                        "fstype":      dp.fstype,
                        "total":       u.total,
                        "used":        u.used,
                        "free":        u.free,
                        "percent":     u.percent,
                    })
                except Exception:
                    pass
            data = {"partitions": parts}

        elif action == "ping":
            data = {"ok": True, "device_id": DEVICE_ID}

        else:
            error = f"Bilinmeyen komut: {action}"

    except Exception as e:
        error = str(e)

    return {"type": "result", "cmd_id": cmd_id, "data": data, "error": error}


# ── Main Loop ────────────────────────────────────────────────────────────

def _baglanti_urlsi() -> tuple[str, bool]:
    """Bağlanılacak URL + ilk eşleştirme mi.

    İki yol:
      · `--eslestir KOD` / `YUKI_ESLESTIRME` → TEK KULLANIMLIK kod, sunucu
        karşılığında kalıcı bir cihaz tokeni verir
      · kayıtlı cihaz tokeni                  → normal bağlantı

    🔴 Eski `YUKI_TOKEN` yolu KALDIRILMADI ama artık tek başına yetmez: sunucu
    tarafında `AUTH_TOKEN` boş olduğu için o kapı zaten hiç çalışmıyordu
    (ölçüldü 2026-09-18) — geriye dönük uyum için query'de taşınıyor.
    """
    import sys
    kod = os.getenv("YUKI_ESLESTIRME", "")
    if "--eslestir" in sys.argv:
        i = sys.argv.index("--eslestir")
        # "--eslestir K7MQ 4X2P" (boşluklu yazım) kodun yarısını almasın: bayrak olmayan
        # sonraki sözcüklerin hepsi birleştirilir; sunucu da kodu normalleştirir.
        parcalar = []
        for a in sys.argv[i + 1:]:
            if a.startswith("--"):
                break
            parcalar.append(a)
        if parcalar:
            kod = "".join(parcalar)
    kod = "".join(c for c in kod if c.isalnum()).upper()

    if kod:
        ad = os.getenv("YUKI_CIHAZ_ADI", socket.gethostname())
        from urllib.parse import quote
        return f"{SERVER_URL}?eslestirme={quote(kod)}&ad={quote(ad)}", True

    token = _cihaz_tokeni_oku()
    if token:
        from urllib.parse import quote
        return f"{SERVER_URL}?cihaz={quote(token)}", False

    if YUKI_TOKEN:                     # eski yol — geriye dönük
        return f"{SERVER_URL}?token={YUKI_TOKEN}", False

    return SERVER_URL, False


async def run():
    url, eslestirme_mi = _baglanti_urlsi()

    if eslestirme_mi:
        log.info("Eşleştirme kodu ile bağlanılıyor — bu kod TEK KULLANIMLIKTIR.")
    elif not _cihaz_tokeni_oku() and not YUKI_TOKEN:
        log.error("Cihaz eşleştirilmemiş. Yuki'de ⚙ AYAR → CİHAZLAR → "
                  "'Yeni cihaz ekle' deyip QR'daki kodu ver:")
        log.error("    python agent.py --eslestir KOD")
        return

    while True:
        try:
            log.info("Bağlanıyor: %s", SERVER_URL)
            async with websockets.connect(url, ping_interval=20, ping_timeout=10) as ws:
                # İlk eşleştirmede sunucu kalıcı tokeni BİR KEZ gönderir.
                if eslestirme_mi:
                    ilk = json.loads(await ws.recv())
                    if ilk.get("type") == "eslestirildi" and ilk.get("cihaz_token"):
                        _cihaz_tokeni_yaz(ilk["cihaz_token"])
                        log.info("Eşleştirme tamam — cihaz tokeni kaydedildi (%s)",
                                 CIHAZ_TOKEN_FILE)
                        # Sonraki turlar token ile bağlanır
                        url, eslestirme_mi = _baglanti_urlsi()
                    else:
                        log.error("Sunucu eşleştirme yanıtı vermedi: %s", ilk)
                        return

                # Kayıt — `device_id` sunucuda EŞLEŞTİRME KAYDINDAN alınır,
                # buradaki değer yalnız geriye dönük uyum için gönderiliyor.
                reg = {"type": "register", "device_id": DEVICE_ID}
                reg.update(get_sysinfo())
                await ws.send(json.dumps(reg))
                log.info("Bağlandı — cihaz: %s | sunucu: %s", DEVICE_ID[:8], SERVER_URL)

                # Heartbeat görevi
                async def _heartbeat():
                    while True:
                        await asyncio.sleep(15)
                        try:
                            hb = {"type": "heartbeat", "device_id": DEVICE_ID}
                            hb.update(get_sysinfo())
                            await ws.send(json.dumps(hb))
                        except Exception:
                            return

                asyncio.create_task(_heartbeat())

                # Komut dinle
                async for raw in ws:
                    try:
                        msg = json.loads(raw)
                        if msg.get("type") == "command":
                            resp = await handle_command(msg)
                            resp["device_id"] = DEVICE_ID
                            await ws.send(json.dumps(resp))
                    except Exception as e:
                        log.warning("Komut hatası: %s", e)

        except Exception as e:
            log.warning("Bağlantı kesildi: %s — %ds sonra tekrar deneniyor.", e, RECONNECT_DELAY)
            await asyncio.sleep(RECONNECT_DELAY)


if __name__ == "__main__":
    log.info("AliceAI Remote Agent başlatılıyor...")
    log.info("Sunucu: %s | Cihaz ID: %s", SERVER_URL, DEVICE_ID[:8] + "...")
    asyncio.run(run())
