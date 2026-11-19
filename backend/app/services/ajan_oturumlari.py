"""Kullanıcının makinesindeki kodlama ajanları — Claude Code + Codex.

AJAN sekmesinin "dış ajan" desteleri buradan beslenir. **Salt okunur ve genel:**
hiçbir kullanıcıya özel yol, tmux düzeni ya da hook varsayılmaz. Yalnız iki
aracın KENDİ yazdığı kayıtlar okunur:

  Claude Code  `~/.claude/sessions/<pid>.json`  — canlı oturumun resmî kaydı
               (sessionId · cwd · startedAt · status busy/idle). Canlılık =
               kayıt var + pid yaşıyor + süreç gerçekten claude.
               Son etkinlik = `~/.claude/projects/*/<sessionId>.jsonl` mtime.
  Codex        `~/.codex/session_index.jsonl` (kurulu mu) +
               `~/.codex/sessions/YYYY/MM/DD/rollout-*.jsonl` (cwd + son olay).

🔒 KONUŞMA İÇERİĞİ DÖNDÜRÜLMEZ. Döndürülen tek şey durum (çalışıyor /
bekliyor / bitti), proje KLASÖRÜNÜN ADI (tam yol değil), klasörün git DALININ
ADI (göz turu 1: aynı klasörde birden çok oturum ayırt edilsin) ve süreler. Transcript'in
son satırı yalnız `stop_reason`'ı okumak için ayrıştırılır, metni dışarı çıkmaz.
Codex'in `thread_name`'i de bilerek alınmaz: başlık konuşmanın özetidir.

Yollar: `CLAUDE_CONFIG_DIR` / `CODEX_HOME` verilmişse o, yoksa ev dizini.
Windows ve macOS'ta da aynı ev-dizini düzeni kullanılır; bir kaynak yoksa boş
döner, hata vermez. Kurulu değilse `kurulu: False` → arayüz desteyi hiç çizmez.

Açık kaynak sürümde oturumlara metin gönderilmez; `gonderilebilir` alanı yalnız
bilgi amaçlıdır (oturum bir tmux bölmesinde mi).
"""
from __future__ import annotations

import json
import logging
import os
import re
import shutil
import subprocess
import time
from pathlib import Path

logger = logging.getLogger(__name__)

AKTIF_SN = 300            # end_turn yok + bundan yeni → "çalışıyor" (kişisel pano.py ölçüsü)
BITTI_PENCERE_SN = 3 * 3600   # kapanmış oturum bu kadar süre "bitti" diye görünür
BITTI_TAVAN = 6           # en fazla kaç kapanmış oturum
CODEX_TAVAN = 8
KUYRUK_BAYT = 65536

# Claude Code'un çalıştırılabilir adları. npm kurulumunda süreç `node …/cli.js`
# olarak görünür — o yol ikinci argümandan tanınır.
_CLAUDE_ADLARI = {"claude", "claude.exe"}
_YORUMLAYICILAR = {"node", "node.exe", "bun", "bun.exe"}


def claude_kok() -> Path:
    return Path(os.environ.get("CLAUDE_CONFIG_DIR") or (Path.home() / ".claude"))


def codex_kok() -> Path:
    return Path(os.environ.get("CODEX_HOME") or (Path.home() / ".codex"))


def _proje_adi(cwd: str) -> str:
    """Tam yol değil yalnız klasör adı — ev dizini ve kullanıcı adı dışarı çıkmaz."""
    ad = Path(str(cwd or "").rstrip("/\\")).name
    return ad or "—"


def _git_dali(cwd: str) -> str:
    """Klasörün (ya da üst klasörlerinin) git dalının YALNIZ adı; dal yoksa "".

    `.git/HEAD` okunur, git çalıştırılmaz. Worktree'de `.git` bir dosyadır
    (`gitdir: …`) — o izlenir. Ayrık HEAD'de (commit kimliği) boş döner:
    kimlik kullanıcıya bir şey anlatmaz.
    """
    if not cwd:
        return ""
    try:
        d = Path(cwd)
        for _ in range(8):
            g = d / ".git"
            if g.is_dir():
                head = g / "HEAD"
            elif g.is_file():
                m = re.match(r"gitdir:\s*(.+)", g.read_text(encoding="utf-8", errors="replace").strip())
                if not m:
                    return ""
                gd = Path(m.group(1).strip())
                head = (gd if gd.is_absolute() else d / gd) / "HEAD"
            else:
                if d.parent == d:
                    return ""
                d = d.parent
                continue
            ref = head.read_text(encoding="utf-8", errors="replace").strip()
            m = re.match(r"ref:\s*refs/heads/(\S+)$", ref)
            ad = m.group(1) if m else ""
            return ad if ad.isprintable() and len(ad) <= 80 else ""
    except (OSError, ValueError):
        return ""
    return ""


def _son_satir(yol: Path) -> str:
    try:
        with yol.open("rb") as f:
            f.seek(0, 2)
            boy = f.tell()
            f.seek(max(0, boy - KUYRUK_BAYT))
            veri = f.read().rstrip(b"\n")
    except OSError:
        return ""
    i = veri.rfind(b"\n")
    return veri[i + 1:].decode(errors="replace")


def _end_turn_mu(transcript: Path | None) -> bool | None:
    """Son satır `end_turn` ile biten assistant mesajı mı? (None = bilinmiyor)"""
    if transcript is None:
        return None
    try:
        k = json.loads(_son_satir(transcript))
    except ValueError:
        return None
    if k.get("type") != "assistant":
        return False
    return (k.get("message") or {}).get("stop_reason") == "end_turn"


# ── süreç doğrulaması ─────────────────────
def claude_sureci_mi(pid: int) -> tuple[bool, str]:
    """pid yaşıyor mu VE gerçekten Claude Code mu? → (evet, sebep_anahtarı)

    🔴 pid yeniden kullanılabilir: SIGKILL'le ölen oturumun kaydı diskte kalır
    ve aynı numarayı bambaşka bir süreç alabilir. Yalnız "pid var" demek o
    süreci Claude sanmak olur — gönderim kapısında bu, metni yanlış programa
    yazmak demektir.
    """
    try:
        import psutil
        p = psutil.Process(int(pid))
        ad = (p.name() or "").lower()
        cmd = p.cmdline()
        durum = p.status()
    except Exception:
        return False, "ajan.surec-yok"
    if durum in ("stopped", "tracing-stop", "zombie", "dead"):
        # Ctrl+Z ile durdurulmuş claude → terminalin önünde KABUK vardır.
        return False, "ajan.surec-durdurulmus"
    if ad in _CLAUDE_ADLARI:
        return True, ""
    # npm kurulumu: `node …/@anthropic-ai/claude-code/cli.js`. Yalnız yorumlayıcı +
    # paket yolu birlikteyse kabul — `vim claude` gibi bir dosya adı Claude sayılmaz.
    birinci = Path(cmd[0]).name.lower() if cmd else ""
    ikinci = cmd[1] if len(cmd) > 1 else ""
    if birinci in _YORUMLAYICILAR and "@anthropic-ai/claude-code" in ikinci.replace("\\", "/"):
        return True, ""
    return False, "ajan.surec-claude-degil"


def surec_terminali(pid: int) -> str:
    try:
        import psutil
        return psutil.Process(int(pid)).terminal() or ""
    except Exception:
        return ""


def on_planda_mi(pid: int) -> bool | None:
    """Süreç kendi terminalinin ÖN PLAN grubunda mı? (None = ölçülemiyor)

    Linux'ta `/proc/<pid>/stat` → pgrp == tpgid. Arka planda (`claude &`)
    duran süreçte terminale yazılan metni KABUK okur. /proc'suz sistemde
    (macOS) ölçülemez → None; çağıran taraf diğer katmanlara güvenir.
    """
    try:
        ham = Path("/proc", str(int(pid)), "stat").read_text()
    except (OSError, ValueError):
        return None
    try:
        alanlar = ham[ham.rindex(")") + 2:].split()
        pgrp, tpgid = int(alanlar[2]), int(alanlar[5])
    except (ValueError, IndexError):
        return None
    return pgrp == tpgid


def tmux_paneleri() -> list[dict]:
    """Bu kullanıcının tmux sunucusundaki pane'ler → [{pane, pid, tty}].

    tmux kurulu değilse ya da sunucu yoksa boş liste — hata değil.
    """
    from app import demo_kip
    if demo_kip.acik():
        return []
    if not shutil.which("tmux"):
        return []
    try:
        cikti = subprocess.run(
            ["tmux", "list-panes", "-a", "-F", "#{pane_id}\t#{pane_pid}\t#{pane_tty}"],
            capture_output=True, text=True, timeout=3,
        ).stdout
    except (OSError, subprocess.SubprocessError):
        return []
    paneler = []
    for satir in cikti.splitlines():
        p = satir.split("\t")
        if len(p) == 3 and p[0].startswith("%"):
            paneler.append({"pane": p[0], "pid": p[1], "tty": p[2]})
    return paneler


def pane_bul(pid: int, paneler: list[dict] | None = None) -> str:
    """Claude sürecinin oturduğu tmux pane'i — TERMİNALİNDEN eşlenir.

    🔑 Ölçüt tty: pane kimliği yalnız kendi tmux sunucusunda tekildir, tty ise
    sistemde tekildir. Claude'un kendi kaydındaki `tmux` alanı (varsa) başka bir
    sunucunun pane'ini gösterebilir; tty eşleşmesi metnin doğru terminale
    gideceğinin kanıtıdır.
    """
    tty = surec_terminali(pid)
    if not tty:
        return ""
    for p in (paneler if paneler is not None else tmux_paneleri()):
        if p["tty"] == tty:
            return p["pane"]
    return ""


# ── Claude Code ──────────────────────────────────────────────────────────────
def _transcript_bul(kok: Path, sid: str) -> Path | None:
    if not sid:
        return None
    try:
        return next((kok / "projects").glob(f"*/{sid}.jsonl"), None)
    except OSError:
        return None


def _claude_kayitlari(kok: Path) -> list[dict]:
    kayitlar = []
    d = kok / "sessions"
    if not d.is_dir():
        return kayitlar
    for f in d.glob("*.json"):
        try:
            k = json.loads(f.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            continue
        if isinstance(k, dict) and k.get("sessionId") and str(k.get("pid") or "").isdigit():
            kayitlar.append(k)
    return kayitlar


def canli_claude_kaydi(oturum: str) -> dict | None:
    """Kısa kimliği (sessionId'nin ilk 8'i) verilen, pid'i YAŞAYAN oturumun ham kaydı.

    Sürecin gerçekten Claude olup olmadığını burada SORMAZ (`claude_sureci_mi`).
    Liste ucu yalnız Claude'ları gösterir.
    """
    try:
        import psutil
    except ImportError:
        return None
    for k in _claude_kayitlari(claude_kok()):
        if str(k["sessionId"])[:8] == oturum and psutil.pid_exists(int(k["pid"])):
            return k
    return None


def _cwd_oku(transcript: Path) -> str:
    """Kapanmış oturumun klasörü — transcript'in ilk satırlarındaki `cwd` alanı.

    Yalnız bu alan okunur (regex), satırın geri kalanı ayrıştırılmaz.
    """
    try:
        with transcript.open("rb") as f:
            bas = f.read(KUYRUK_BAYT).decode(errors="replace")
    except OSError:
        return ""
    m = re.search(r'"cwd"\s*:\s*"((?:[^"\\]|\\.)*)"', bas)
    if not m:
        return ""
    try:
        return json.loads('"' + m.group(1) + '"')
    except ValueError:
        return ""


def claude_oturumlari() -> dict:
    from app import demo_kip
    if demo_kip.acik():               # demo: gerçek oturum/proje adları okunmaz
        return demo_kip.claude_oturumlari()
    kok = claude_kok()
    if not ((kok / "sessions").is_dir() or (kok / "projects").is_dir()):
        return {"kurulu": False, "oturumlar": []}
    simdi = time.time()
    paneler = tmux_paneleri()
    canli: list[dict] = []
    canli_sid: set[str] = set()
    for k in _claude_kayitlari(kok):
        pid = int(k["pid"])
        if not claude_sureci_mi(pid)[0]:
            continue                     # kapanmış ya da pid başkasının (hayalet kayıt)
        sid = str(k["sessionId"])
        canli_sid.add(sid)
        tr = _transcript_bul(kok, sid)
        try:
            son = tr.stat().st_mtime if tr else 0.0
        except OSError:
            son = 0.0
        baslangic = (k.get("startedAt") or 0) / 1000.0
        son = son or (k.get("updatedAt") or 0) / 1000.0 or baslangic
        resmi = str(k.get("status") or "")
        if resmi == "busy":
            durum = "calisiyor"
        elif resmi == "idle":
            durum = "bekliyor"
        else:   # eski sürüm: resmî durum yok → kişisel pano.py'nin end_turn ölçüsü
            et = _end_turn_mu(tr)
            durum = "bekliyor" if et else ("calisiyor" if simdi - son < AKTIF_SN else "bekliyor")
        pane = pane_bul(pid, paneler) if paneler else ""
        on_plan = on_planda_mi(pid) if pane else None
        canli.append({
            "id": sid[:8],
            "proje": _proje_adi(k.get("cwd", "")),
            "dal": _git_dali(k.get("cwd", "")),
            "durum": durum,
            "otomatik": str(k.get("entrypoint") or "").startswith("sdk"),
            "sure_sn": int(max(0, simdi - baslangic)) if baslangic else None,
            "sessiz_sn": int(max(0, simdi - son)) if son else None,
            "yuzey": "tmux" if pane else "",
            "gonderilebilir": bool(pane) and on_plan is not False,
        })

    # Kapanmış ama yakın zamanda çalışmış oturumlar — "bitti".
    biten: list[dict] = []
    pd = kok / "projects"
    if pd.is_dir():
        adaylar: list[tuple[float, Path]] = []
        try:
            for proje in os.scandir(pd):
                if not proje.is_dir():
                    continue
                for f in os.scandir(proje.path):
                    if not f.name.endswith(".jsonl"):
                        continue
                    try:
                        mt = f.stat().st_mtime
                    except OSError:
                        continue
                    if simdi - mt <= BITTI_PENCERE_SN and f.name[:-6] not in canli_sid:
                        adaylar.append((mt, Path(f.path)))
        except OSError:
            adaylar = []
        for mt, yol in sorted(adaylar, reverse=True)[:BITTI_TAVAN]:
            cwd = _cwd_oku(yol)
            biten.append({
                "id": yol.name[:8],
                "proje": _proje_adi(cwd),
                "dal": _git_dali(cwd),
                "durum": "bitti",
                "otomatik": False,
                "sure_sn": None,
                "sessiz_sn": int(max(0, simdi - mt)),
                "yuzey": "",
                "gonderilebilir": False,
            })
    sira = {"calisiyor": 0, "bekliyor": 1}
    canli.sort(key=lambda o: (sira.get(o["durum"], 2), o["sessiz_sn"] or 0))
    return {"kurulu": True, "oturumlar": canli + biten}


# ── Codex ────────────────────────────────────────────────────────────────────
def _codex_dosyalari(kok: Path, simdi: float) -> list[tuple[float, Path]]:
    """Son iki günün rollout dosyaları — tüm arşiv taranmaz (yıllarca birikir)."""
    sonuc = []
    gunler = {time.strftime("%Y/%m/%d", time.localtime(simdi - g * 86400)) for g in (0, 1)}
    for gun in gunler:
        d = kok / "sessions" / gun
        if not d.is_dir():
            continue
        for f in d.glob("rollout-*.jsonl"):
            try:
                mt = f.stat().st_mtime
            except OSError:
                continue
            if simdi - mt <= BITTI_PENCERE_SN:
                sonuc.append((mt, f))
    return sorted(sonuc, reverse=True)[:CODEX_TAVAN]


def _iso_sn(iso: str) -> float | None:
    from datetime import datetime
    try:
        return datetime.fromisoformat(iso.replace("Z", "+00:00")).timestamp()
    except (ValueError, AttributeError):
        return None


def codex_oturumlari() -> dict:
    from app import demo_kip
    if demo_kip.acik():               # demo: gerçek oturum/proje adları okunmaz
        return demo_kip.codex_oturumlari()
    kok = codex_kok()
    if not ((kok / "session_index.jsonl").is_file() or (kok / "sessions").is_dir()):
        return {"kurulu": False, "oturumlar": []}
    simdi = time.time()
    oturumlar = []
    for mt, yol in _codex_dosyalari(kok, simdi):
        try:
            with yol.open("rb") as f:
                bas = f.read(KUYRUK_BAYT).decode(errors="replace")
        except OSError:
            continue
        cwd = re.search(r'"cwd"\s*:\s*"((?:[^"\\]|\\.)*)"', bas)
        ts = re.search(r'"timestamp"\s*:\s*"([^"]+)"', bas)
        try:
            cwd_s = json.loads('"' + cwd.group(1) + '"') if cwd else ""
        except ValueError:
            cwd_s = ""
        baslangic = _iso_sn(ts.group(1)) if ts else None
        try:
            son = json.loads(_son_satir(yol))
            olay = str(((son.get("payload") or {}) if isinstance(son, dict) else {}).get("type") or "")
        except ValueError:
            olay = ""
        if olay == "task_complete":
            durum = "bekliyor" if simdi - mt < 1800 else "bitti"
        elif olay == "turn_aborted":
            durum = "bitti"
        else:
            durum = "calisiyor" if simdi - mt < AKTIF_SN else "bitti"
        m = re.search(r"([0-9a-f]{8})-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}\.jsonl$", yol.name)
        oturumlar.append({
            "id": m.group(1) if m else yol.stem[-8:],
            "proje": _proje_adi(cwd_s),
            "dal": _git_dali(cwd_s),
            "durum": durum,
            "sure_sn": int(max(0, mt - baslangic)) if baslangic else None,
            "sessiz_sn": int(max(0, simdi - mt)),
        })
    return {"kurulu": True, "oturumlar": oturumlar}
