"""modes.py — Mod Başlatma: adlandırılmış masaüstü otomasyon senaryoları.

Bir "mod" = {
  id, name, trigger_keywords[], apps[], workspace|special
}
Tetik: LLM `start_mode(mode_id)` (sesli/yazılı). Akış:
  1) apps → ilgili workspace/özel-alana SESSİZCE yerleştir (hyprctl exec [workspace .. silent])
  2) workspace'i GÖSTER (özel alan: togglespecialworkspace · numaralı: focusworkspaceoncurrentmonitor)
  3) frontend'e MOD kartı yayınla (skill_events → SkillCard)

Açık kaynak sürümde modlar KABUK KOMUTU ÇALIŞTIRMAZ: eski modes.json'lardaki
terminal/arka plan komut alanları yok sayılır (hata vermez, çalıştırılmaz).

Mod tanımları config.MODES_PATH (paketli üründe userData) modes.json'dan yüklenir, yoksa paketteki tohumdan; mtime ile cache'lenir.
hyprctl exec ile silent yerleştirme search-2 araştırmasından (WIKI: hyprland-mod-launcher-python.md).
"""
from __future__ import annotations

import asyncio
import json
import logging
import os
import shutil
import subprocess
import time
from typing import Optional

from app.config import MODES_PATH, MODES_SEED_PATH
from app.services.tools._base import _build_wayland_env
from app.services.tools.desktop_env import detect_env
from app.services.tools.media import _resolve_app, open_application

log = logging.getLogger(__name__)

import threading

_modes_cache: Optional[dict[str, dict]] = None
_modes_mtime: float = 0.0
_modes_lock = threading.RLock()  # cache load'u eşzamanlı isteklere karşı korur (yarım-yazılmış cache riski)


# ── Platform-güvenli çalıştırma yardımcıları ─────────────────────────
def _safe_env() -> dict:
    """Linux'ta zengin Wayland env; Windows/macOS'ta düz kopya (os.getuid POSIX-only)."""
    if detect_env()["os"] == "linux":
        try:
            return _build_wayland_env()
        except Exception:
            return os.environ.copy()
    return os.environ.copy()


def _popen_detached(argv: list[str], env: Optional[dict] = None) -> subprocess.Popen:
    """Bağımsız (detached) süreç başlat — start_new_session yalnız POSIX'te."""
    kw: dict = dict(stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                    env=env if env is not None else _safe_env())
    if os.name == "posix":
        kw["start_new_session"] = True
    return subprocess.Popen(argv, **kw)


# ── Yükleme ──────────────────────────────────────────────────────────
def _okunacak_yol() -> str:
    """Kullanıcının modes.json'u; henüz yoksa paketle gelen tohum (bkz. config.MODES_SEED_PATH).

    Tohumdan okumak eski kurulumları da taşır: paket dizini yazılabilir olan kurulumda (Windows
    zip) modlar oraya kaydedilmişti — ilk kayıtta kullanıcı dosyasına geçerler."""
    if os.path.exists(MODES_PATH) or not os.path.exists(MODES_SEED_PATH):
        return MODES_PATH
    return MODES_SEED_PATH


def _load_modes(force: bool = False) -> dict[str, dict]:
    """modes.json → {id_lower: mode}. Dosya mtime değişince otomatik reload."""
    global _modes_cache, _modes_mtime
    try:
        with _modes_lock:  # stat→parse→cache-yaz atomik olsun (Thread B yarım cache okumasın)
            yol = _okunacak_yol()
            st = os.stat(yol)
            if not force and _modes_cache is not None and st.st_mtime == _modes_mtime:
                return _modes_cache
            with open(yol, "r", encoding="utf-8") as f:
                data = json.load(f)
            raw = data.get("modes", data.get("mods", [])) if isinstance(data, dict) else data
            mods: dict[str, dict] = {}
            for m in raw or []:
                mid = m.get("id")
                if mid and m.get("enabled", True):
                    mods[str(mid).strip().lower()] = m
            _modes_cache, _modes_mtime = mods, st.st_mtime
            return mods
    except FileNotFoundError:
        log.warning("modes.json bulunamadı: %s", MODES_PATH)
        return {}
    except Exception as e:
        log.error("modes.json okunamadı (%s): %s", MODES_PATH, e)
        return {}


def _find_mode(query: str) -> Optional[dict]:
    """Sırayla: id → id(boşluk→_) → trigger_keywords → name → kısmi eşleşme."""
    if not query:
        return None
    mods = _load_modes()
    q = query.strip().lower()
    if q in mods:
        return mods[q]
    if q.replace(" ", "_") in mods:
        return mods[q.replace(" ", "_")]
    for m in mods.values():
        kws = [str(k).strip().lower() for k in m.get("trigger_keywords", [])]
        if q in kws or q == str(m.get("name", "")).strip().lower():
            return m
    # gevşek kısmi eşleşme (kullanıcı serbest söyleyebilir)
    for m in mods.values():
        hay = [str(m.get("name", "")).lower(), *[str(k).lower() for k in m.get("trigger_keywords", [])]]
        for h in hay:
            if h and (h in q or q in h):
                return m
    return None


def find_mode_by_trigger(message: str) -> Optional[dict]:
    """LLM bypass için güvenli mod tespiti: exact id/keyword ve 'X mod[*]' prefix.

    Gevşek kısmi eşleşme YOK — false positive önlenir.
    Eşleşme sırası:
      1) exact id / id_with_underscores
      2) exact trigger_keyword veya name
      3) message "<keyword> mod[…]" ile başlıyorsa (örn. "claude kk mod başlat")
    """
    if not message:
        return None
    mods = _load_modes()
    q = message.strip().lower()
    # 1) exact id
    if q in mods:
        return mods[q]
    if q.replace(" ", "_") in mods:
        return mods[q.replace(" ", "_")]
    for m in mods.values():
        kws = [str(k).strip().lower() for k in m.get("trigger_keywords", [])]
        name = str(m.get("name", "")).strip().lower()
        # 2) exact keyword / name
        if q in kws or q == name:
            return m
        # 3) "keyword mod[*]" prefix — "claude kk mod başlat" gibi
        for kw in kws:
            if kw and q.startswith(kw):
                rest = q[len(kw):].strip()
                if not rest or rest.startswith("mod"):
                    return m
    return None


# ── hyprctl yardımcıları ─────────────────────────────────────────────
def _lua_str(s: str) -> str:
    """Python dizesini Lua dize sabitine çevir (hyprctl dispatch 'hl.dsp…' içine gömmek için)."""
    return '"' + s.replace("\\", "\\\\").replace('"', '\\"') + '"'


def _hypr(lua: str, *args: str) -> tuple[bool, str]:
    """Hyprland dispatch — conf + Lua ayarı. Lua ayarında (0.56+ `hyprland.lua`, 0.57'de
    tek biçim) eski biçim ("movetoworkspacesilent …") ÖLÜ (çıkış 7), conf ayarında Lua biçimi
    "Invalid dispatcher" döner ve iş yapmaz (ölçüldü 2026-09-27) → önce `lua`, çıktısı tam "ok"
    değilse eski `args`."""
    try:
        env = _build_wayland_env()
        r = subprocess.run(["hyprctl", "dispatch", lua],
                           capture_output=True, text=True, timeout=4, env=env)
        if (r.stdout or "").strip() == "ok":
            return True, "ok"
        r = subprocess.run(
            ["hyprctl", "dispatch", *args],
            capture_output=True, text=True, timeout=4, env=env,
        )
        out = (r.stdout or r.stderr or "").strip()
        return (r.returncode == 0 and "ok" in (r.stdout or "").lower()), out
    except FileNotFoundError:
        return False, "hyprctl yok (Hyprland çalışmıyor)"
    except Exception as e:
        return False, str(e)


def _ws_target(mode: dict) -> Optional[str]:
    """hyprctl exec kuralı için workspace hedefi: 'special:alan4' | '3' | 'name:foo'."""
    if mode.get("special"):
        return f"special:{mode['special']}"
    ws = mode.get("workspace")
    if ws is None or ws == "":
        return None
    return str(ws) if str(ws).isdigit() else f"name:{ws}"


def _open_app(app: str, ws_target: Optional[str]) -> tuple[bool, str]:
    """Uygulamayı (whitelist'li) aç; Hyprland'de yeni pencereyi hedef alana sessizce taşı."""
    binary = _resolve_app(app)
    if not binary:
        return False, f"'{app}' izin listesinde yok"
    # Yalnız Hyprland pencereyi güvenilir taşıyabilir (workspace_move)
    if ws_target and detect_env()["features"]["workspace_move"]:
        env = _safe_env()
        before = _get_window_addrs(env)
        try:
            _popen_detached([binary], env)
        except Exception as e:
            return False, str(e)
        moved = _move_new_win(before, ws_target, env)
        if moved:
            return True, f"{binary}→{ws_target}"
        # Pencere görünmediyse (yavaş açılış, tek örnekli uygulama) başarı denmez.
        return False, f"{binary} başlatıldı, pencere doğrulanmadı"
    # Diğer platformlar: sadece aç (alan geçişi _reveal_ws'te best-effort)
    res = open_application(app)
    return (not res.lower().startswith("hata")), res


def _get_window_addrs(env: dict) -> set[str]:
    """Aktif Hyprland pencere adreslerini döner."""
    try:
        r = subprocess.run(
            ["hyprctl", "clients", "-j"],
            capture_output=True, text=True, timeout=4, env=env,
        )
        if r.returncode != 0:
            log.warning("hyprctl clients -j başarısız rc=%d stderr=%s", r.returncode, r.stderr[:200])
            return set()
        clients = json.loads(r.stdout or "[]")
        addrs = {c.get("address", "") for c in clients}
        log.debug("pencere listesi: %d pencere, adresler: %s", len(clients), addrs)
        return addrs
    except Exception as e:
        log.warning("_get_window_addrs hata: %s", e)
        return set()


def _move_new_win(before: set[str], ws_target: str, env: dict) -> bool:
    """Yeni pencere çıkana kadar bekle (max 5s), çıkınca ws_target'a taşı."""
    log.warning("_move_new_win: hedef=%s, önce=%d pencere, bekleniyor...", ws_target, len(before))
    for i in range(25):  # 25 × 0.2s = 5s
        time.sleep(0.2)
        after = _get_window_addrs(env)
        new_addrs = after - before
        if new_addrs:
            addr = next(iter(new_addrs))
            ok, out = _hypr(
                f"hl.dsp.window.move({{ workspace = {_lua_str(ws_target)}, follow = false, window = {_lua_str('address:' + addr)} }})",
                "movetoworkspacesilent", f"{ws_target},address:{addr}")
            log.warning("movetoworkspacesilent %s addr=%s → ok=%s çıktı=%s", ws_target, addr, ok, out)
            return ok
        if i % 5 == 4:
            log.warning("poll %ds: henüz yeni pencere yok (toplam=%d)", (i + 1) // 5, len(after))
    log.warning("_move_new_win: 5s içinde yeni pencere bulunamadı")
    return False


def _reveal_ws(mode: dict) -> tuple[bool, str]:
    """Workspace'i göster — platforma göre: Hyprland (hyprctl) · Linux (wmctrl) · diğer (atla)."""
    feats = detect_env()["features"]
    # Hyprland: özel alan → toggle; numaralı → focus
    if feats["specials"] and mode.get("special"):
        return _hypr(f"hl.dsp.workspace.toggle_special({_lua_str(str(mode['special']))})",
                     "togglespecialworkspace", str(mode["special"]))
    ws = mode.get("workspace")
    if ws is None or ws == "":
        return True, ""
    if feats["workspace_move"]:  # Hyprland numaralı/isimli
        if str(ws).isdigit():
            return _hypr(f"hl.dsp.focus({{ workspace = {_lua_str(str(ws))}, on_current_monitor = true }})",
                         "focusworkspaceoncurrentmonitor", str(ws))
        return _hypr(f"hl.dsp.focus({{ workspace = {_lua_str('name:' + str(ws))} }})",
                     "workspace", f"name:{ws}")
    # Generic Linux: wmctrl ile numaralı masaüstüne geç (0-index)
    if feats["workspaces"] and detect_env()["os"] == "linux" and str(ws).isdigit():
        try:
            r = subprocess.run(["wmctrl", "-s", str(max(0, int(ws) - 1))],
                               capture_output=True, timeout=3)
            return r.returncode == 0, "wmctrl -s"
        except Exception as e:
            return False, str(e)
    # Windows/macOS: sanal masaüstü geçişi henüz yok — best-effort atlanır
    return True, ""


def _run_mode_actions(mode: dict) -> tuple[list[str], list[str]]:
    """Modun tüm aksiyonlarını (bloklayan subprocess) sırayla çalıştır → (yapılanlar, hatalar)."""
    feats = detect_env()["features"]
    # ws_target yalnız Hyprland'de anlamlı (yeni pencereyi sessizce taşımak için)
    ws_target = _ws_target(mode) if feats["workspace_move"] else None
    done: list[str] = []
    errs: list[str] = []

    for app in mode.get("apps", []) or []:
        ok, msg = _open_app(app, ws_target)
        (done if ok else errs).append(msg)

    # Eski şemadaki komut alanları bilerek YOK SAYILIR (kabuk yok).

    # Alanı göster (Hyprland tam; generic Linux wmctrl; diğer no-op)
    if mode.get("special") or mode.get("workspace") not in (None, ""):
        if feats["workspace_move"]:
            time.sleep(0.3)  # pencereler yerleşsin
        rok, rmsg = _reveal_ws(mode)
        if not rok and rmsg:
            errs.append(f"alan: {rmsg}")

    return done, errs


async def _emit_card(mode: dict) -> None:
    """Frontend SkillCard (Tensura "kazanım kartı") ile MOD bildirimi — asla raise etmez."""
    try:
        from app.services.skill_events import emit
        area = (mode.get("special") and f"alan:{mode['special']}") or (
            mode.get("workspace") not in (None, "") and f"ws:{mode['workspace']}") or None
        apps = ", ".join(mode.get("apps", []) or []) or None
        tag = " · ".join([t for t in (apps, area) if t]) or None
        # i18n: banner/sub/varsayılan etiket frontend'in `mode` kalıbından
        # (skill-card.js PRESET.mode) arayüz dilinde gelir — buradan Türkçe
        # banner/sub gönderilirse kalıbı EZER ve EN kullanıcı Türkçe kart görür.
        # Mod adı ve uygulama listesi kullanıcının kendi verisidir, çevrilmez.
        await emit("mode", str(mode.get("name", mode.get("id", "MOD"))).upper(), tag=tag)
    except Exception as e:
        log.debug("mod kartı yayınlanamadı: %s", e)


# ── Tool yüzeyleri ───────────────────────────────────────────────────
async def start_mode(mode_id: str) -> str:
    """Adlandırılmış masaüstü otomasyon modunu başlat.

    MODE_LAUNCHER_ENABLED kapalıysa HİÇBİR eylem çalışmaz. Bayrak AYARLAR › Sistem'de
    "Mod Başlatıcı" anahtarı olarak duruyordu ama hiçbir kod okumuyordu (2026-09-27 ölçüldü —
    kapatınca modlar yine başlıyordu; kişiselde SOZ-F007). Beş başlatma yolu da (panel /run,
    /api/tools, LLM aracı, sohbet ön-tetiği, açılışta autostart) buradan geçer.
    Her çağrıda `app.config`'ten okunur: ayar ucu `setattr` ile yazar → kapatma ANINDA geçer.
    """
    from app import config as _cfg
    if not _cfg.MODE_LAUNCHER_ENABLED:
        from app.mesajlar import M
        return M("mod.baslatici-kapali")
    mode = _find_mode(mode_id)
    if not mode:
        avail = ", ".join(_load_modes().keys()) or "tanımlı mod yok"
        return f"Hata: '{mode_id}' modu bulunamadı. Mevcut modlar: {avail}"
    name = mode.get("name", mode.get("id", mode_id))
    # Bloklayan subprocess'leri event loop dışında çalıştır
    done, errs = await asyncio.to_thread(_run_mode_actions, mode)
    await _emit_card(mode)
    summary = f"'{name}' modu başlatıldı."
    if done:
        summary += " ✓ " + " · ".join(done[:5])
    if errs:
        summary += " ⚠ " + " · ".join(errs[:4])
    return summary


def list_modes() -> str:
    """Tanımlı tüm modları listele."""
    mods = _load_modes()
    if not mods:
        return "Tanımlı mod yok (modes.json boş veya bulunamadı)."
    lines = []
    for m in mods.values():
        bits = []
        if m.get("apps"):
            bits.append("uygulama: " + ", ".join(m["apps"]))
        if m.get("special"):
            bits.append(f"özel alan: {m['special']}")
        elif m.get("workspace") not in (None, ""):
            bits.append(f"çalışma alanı: {m['workspace']}")
        lines.append(f"• {m.get('name', m['id'])} ({m['id']}) — " + (" · ".join(bits) or "boş"))
    return "Mevcut modlar:\n" + "\n".join(lines)


# ── HQ Mod Yöneticisi: yapısal okuma + güvenli yazma ─────────────────────────
def list_modes_struct() -> list[dict]:
    """modes.json'daki TÜM modları (devre dışı olanlar dahil) ham liste olarak döner.
    UI mod yöneticisi için — `_load_modes()` enabled filtreler, bu filtrelemez."""
    try:
        with open(_okunacak_yol(), "r", encoding="utf-8") as f:
            data = json.load(f)
        raw = data.get("modes", data.get("mods", [])) if isinstance(data, dict) else data
        return list(raw or [])
    except FileNotFoundError:
        return []
    except Exception as e:
        log.error("list_modes_struct okunamadı: %s", e)
        return []


def save_modes_file(modes_list: list[dict]) -> tuple[bool, str]:
    """modes.json'a güvenli yaz: tek yedek (.backup) + atomic (tmp→rename) + cache invalidate.
    (ok, mesaj). Çağıran tarafın şema/whitelist doğrulamasını yapması beklenir."""
    try:
        # mevcut version/_note alanlarını koru
        version, note = "1.0", ""
        kaynak = _okunacak_yol()   # ilk kayıtta tohum: başlık alanları oradan gelir
        if os.path.exists(kaynak):
            try:
                with open(kaynak, "r", encoding="utf-8") as f:
                    old = json.load(f)
                if isinstance(old, dict):
                    version = old.get("version", version)
                    note = old.get("_note", note)
            except Exception:
                pass
        if os.path.exists(MODES_PATH):
            # tek rolling yedek (yalnız kullanıcının kendi dosyası — tohum paketin malı)
            shutil.copy2(MODES_PATH, MODES_PATH + ".backup")
        os.makedirs(os.path.dirname(MODES_PATH) or ".", exist_ok=True)
        payload = {"version": version, "_note": note, "modes": modes_list}
        tmp = MODES_PATH + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(payload, f, indent=2, ensure_ascii=False)
        os.replace(tmp, MODES_PATH)
        _load_modes(force=True)  # cache invalidate
        log.info("modes.json kaydedildi (%d mod)", len(modes_list))
        return True, "ok"
    except Exception as e:
        log.error("save_modes_file başarısız: %s", e)
        return False, str(e)
