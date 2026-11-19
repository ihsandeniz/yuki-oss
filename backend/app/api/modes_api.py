"""modes_api.py — HQ Mod Yöneticisi CRUD.

modes.json'daki masaüstü-otomasyon modlarını arayüzden ekle/sil/düzenle/aç-kapat.
Çalıştırma (`POST /api/modes/start`) ve formatlı listeleme (`GET /api/modes`) zaten
tools_api.py'de; bu router yapısal listeleme + yazma işlemlerini ekler.

Güvenlik: yazma öncesi APP_WHITELIST + şema doğrulaması. modes.py.save_modes_file
atomic yazar + .backup alır + cache invalidate eder.
"""
from __future__ import annotations

import json
import re
import shutil
import subprocess
from pathlib import Path
from typing import Optional, Union

from fastapi import APIRouter, HTTPException, Request
from app.limiter import limiter
from app.mesajlar import M
from pydantic import BaseModel

from app.services.tools.desktop_env import detect_env, env_label
from app.services.tools.modes import list_modes_struct, save_modes_file, start_mode

router = APIRouter(prefix="/api/modes", tags=["modes"])


# ── Şema ─────────────────────────────────────────────────────────────────────
class ModeSchema(BaseModel):
    id: Optional[str] = None
    name: str
    description: str = ""
    trigger_keywords: list[str] = []
    apps: list[str] = []
    workspace: Union[int, str, None] = None
    special: Optional[str] = None
    enabled: bool = True
    autostart: bool = False


_TR = str.maketrans("çğıöşüÇĞİÖŞÜ", "cgiosucgiosu")  # i18n-istisna: slug harf tablosu (veri)


def _slug(text: str) -> str:
    s = (text or "").translate(_TR).lower().strip()
    s = re.sub(r"[^a-z0-9]+", "_", s).strip("_")
    return s or "mod"


def _clean(mode: ModeSchema, existing_ids: set[str], *, keep_id: str | None = None) -> tuple[dict, list[str]]:
    """ModeSchema → temiz dict + uyarılar. id üret/benzersizleştir, special↔workspace çöz."""
    warnings: list[str] = []
    name = (mode.name or "").strip()
    if not name:
        raise HTTPException(status_code=400, detail=M("mod.ad-zorunlu"))

    mid = _slug(mode.id) if mode.id else _slug(name)
    # benzersizlik (güncellemede kendi id'sini hariç tut)
    base, n = mid, 2
    taken = existing_ids - ({keep_id} if keep_id else set())
    while mid in taken:
        mid = f"{base}_{n}"
        n += 1

    kws = [k.strip() for k in (mode.trigger_keywords or []) if k.strip()]
    # aynı uygulama iki kez yazılırsa iki pencere açılır — sırayı koruyarak tekille
    apps = list(dict.fromkeys(a.strip() for a in (mode.apps or []) if a.strip()))

    # APP_WHITELIST uyarısı (engellemez — kullanıcı özel uygulama tanımlayabilir)
    try:
        from app.config import APP_WHITELIST, APP_ALIASES
        known = {a.lower() for a in APP_WHITELIST} | {a.lower() for a in APP_ALIASES}
        for a in apps:
            if a.lower() not in known:
                warnings.append(M("mod.uyari-whitelist", uygulama=a))
    except Exception:
        pass

    special = (mode.special or "").strip() or None
    workspace = mode.workspace if mode.workspace not in ("", None) else None
    if special and workspace is not None:
        warnings.append(M("mod.uyari-ozel-alan"))
        workspace = None

    if not apps and special is None and workspace is None:
        warnings.append(M("mod.uyari-bos"))

    clean = {
        "id": mid,
        "name": name,
        "description": (mode.description or "").strip(),
        "trigger_keywords": kws,
        "apps": apps,
        "enabled": bool(mode.enabled),
        "autostart": bool(mode.autostart),
    }
    if special:
        clean["special"] = special
    elif workspace is not None:
        clean["workspace"] = workspace
    return clean, warnings


# ── Endpoint'ler ─────────────────────────────────────────────────────────────
@router.get("/list")
@limiter.limit("100/minute")
async def list_modes_structured(request: Request):

    """Yapısal mod listesi (devre dışı olanlar dahil) — UI mod yöneticisi için."""
    return {"modes": list_modes_struct()}


@router.get("/platform")
@limiter.limit("100/minute")
async def platform_info(request: Request):

    """Kurulu sistemi (OS + masaüstü) ve yetenek haritasını döner.

    UI mod formu buna göre alanları gösterir/gizler/yeniden adlandırır; böylece
    aynı Mod Yöneticisi Hyprland'de tam, başka Linux/Windows'ta uygun şekilde çalışır.
    """
    env = detect_env()
    return {**env, "label": env_label()}


@router.post("")
@limiter.limit("30/minute")
async def create_mode(request: Request, body: ModeSchema):

    modes = list_modes_struct()
    ids = {m.get("id") for m in modes if m.get("id")}
    clean, warnings = _clean(body, ids)
    modes.append(clean)
    ok, msg = save_modes_file(modes)
    if not ok:
        raise HTTPException(status_code=500, detail=M("ayar.kaydedilemedi", sebep=msg))
    return {"ok": True, "mode": clean, "warnings": warnings}


@router.put("/{mode_id}")
@limiter.limit("30/minute")
async def update_mode(request: Request, mode_id: str, body: ModeSchema):

    modes = list_modes_struct()
    idx = next((i for i, m in enumerate(modes) if m.get("id") == mode_id), None)
    if idx is None:
        raise HTTPException(status_code=404, detail=M("mod.bulunamadi", id=mode_id))
    ids = {m.get("id") for m in modes if m.get("id")}
    # Ad değişince id DEĞİŞMEZ: arayüz PUT'ta id göndermiyor, eskiden id yeni addan
    # türüyordu → yeniden adlandırılan mod kimliğini (ve arayüzdeki seçimini) kaybediyordu
    if not body.id:
        body.id = mode_id
    clean, warnings = _clean(body, ids, keep_id=mode_id)
    modes[idx] = clean
    ok, msg = save_modes_file(modes)
    if not ok:
        raise HTTPException(status_code=500, detail=M("ayar.kaydedilemedi", sebep=msg))
    return {"ok": True, "mode": clean, "warnings": warnings}


@router.delete("/{mode_id}")
@limiter.limit("30/minute")
async def delete_mode(request: Request, mode_id: str):

    modes = list_modes_struct()
    new = [m for m in modes if m.get("id") != mode_id]
    if len(new) == len(modes):
        raise HTTPException(status_code=404, detail=M("mod.bulunamadi", id=mode_id))
    ok, msg = save_modes_file(new)
    if not ok:
        raise HTTPException(status_code=500, detail=M("ayar.kaydedilemedi", sebep=msg))
    return {"ok": True}


@router.patch("/{mode_id}/toggle")
@limiter.limit("30/minute")
async def toggle_mode(request: Request, mode_id: str):

    modes = list_modes_struct()
    idx = next((i for i, m in enumerate(modes) if m.get("id") == mode_id), None)
    if idx is None:
        raise HTTPException(status_code=404, detail=M("mod.bulunamadi", id=mode_id))
    modes[idx]["enabled"] = not modes[idx].get("enabled", True)
    ok, msg = save_modes_file(modes)
    if not ok:
        raise HTTPException(status_code=500, detail=M("ayar.kaydedilemedi", sebep=msg))
    return {"ok": True, "enabled": modes[idx]["enabled"]}


@router.post("/run/{mode_id}")
@limiter.limit("20/minute")
async def run_mode(request: Request, mode_id: str):

    """Modu hemen başlat (HQ › MODLAR BAŞLAT düğmesi).

    Panel id'yi BİREBİR bilir → gevşek eşleşmeye düşülmez. Eskiden `start_mode`'un gevşek
    eşleşmesi kullanılıyordu; kapalı modlar yükleyicide süzüldüğü için kapalı "dosya"
    modunun id'si açık "Dosya Yönetimi"ni başlatıyordu (ölçüldü 2026-09-27). Kapalı mod 409.
    `uyari`: bazı adımlar başarısızsa (uygulama bulunamadı vb.) arayüz sarı gösterir.
    Sesli/LLM yolu (`start_mode` aracı) gevşek eşleşmeyi korur — kullanıcı serbest söyler.
    """
    from app import config as _cfg
    if not _cfg.MODE_LAUNCHER_ENABLED:   # eskiden 200 + "başlatıldı" olurdu (start_mode kapıyı taşır)
        raise HTTPException(status_code=409, detail=M("mod.baslatici-kapali"))
    mod = next((m for m in list_modes_struct() if m.get("id") == mode_id), None)
    if mod is None:
        raise HTTPException(status_code=404, detail=M("mod.bulunamadi", id=mode_id))
    if mod.get("enabled") is False:
        raise HTTPException(status_code=409, detail=M("mod.kapali", ad=mod.get("name") or mode_id))
    result = await start_mode(mode_id)
    if result.startswith("Hata:"):
        raise HTTPException(status_code=404, detail=result)
    return {"ok": True, "result": result, "uyari": " ⚠ " in result}


@router.get("/apps")
@limiter.limit("100/minute")
async def list_apps(request: Request):

    """Mod formundaki uygulama seçici için: whitelist + alias'lar + kurulum durumu."""
    try:
        from app.config import APP_WHITELIST, APP_ALIASES
    except Exception:
        return {"apps": []}

    # binary → görünen ad eşlemesi (alias'tan ters çevir)
    alias_rev: dict[str, str] = {}
    for label, binary in APP_ALIASES.items():
        alias_rev.setdefault(binary.lower(), label)

    apps = []
    seen: set[str] = set()
    for binary in APP_WHITELIST:
        key = binary.lower()
        if key in seen:
            continue
        seen.add(key)
        installed = shutil.which(binary) is not None
        apps.append({
            "binary": binary,
            "label": alias_rev.get(key, binary),
            "installed": installed,
        })

    # alias'lardan whitelist'te olmayan binary'leri de ekle
    for label, binary in APP_ALIASES.items():
        key = binary.lower()
        if key not in seen:
            seen.add(key)
            installed = shutil.which(binary) is not None
            apps.append({"binary": binary, "label": label, "installed": installed})

    apps.sort(key=lambda x: (not x["installed"], x["binary"]))
    return {"apps": apps}


@router.get("/workspaces")
@limiter.limit("100/minute")
async def list_workspaces(request: Request):

    """Mod formundaki alan seçici için: hyprctl aktif workspace'ler + özel alanlar.

    Hyprland dışı sistemlerde özel alan/silent-move yoktur → sade numaralı liste döner
    (yetenek yoksa boş). UI bu boş listeyi görünce alan seçiciyi gizler.
    """
    feats = detect_env()["features"]
    if not feats["specials"]:  # Hyprland değil
        if not feats["workspaces"]:
            return {"workspaces": [], "specials": []}
        # Generic Linux (wmctrl) / Windows (sanal masaüstü): sade 1-4. Doluluk BİLİNMİYOR →
        # `active: None` (eskiden `i == 1` sabitti: panel "alan 1 dolu" diye uydurma bilgi gösterirdi).
        return {
            "workspaces": [{"id": i, "name": str(i), "active": None} for i in range(1, 5)],
            "specials": [],
        }

    workspaces: list[dict] = []
    specials: list[dict] = []

    # Hyprland çalışıyorsa aktif workspace'leri al
    try:
        out = subprocess.run(
            ["hyprctl", "workspaces", "-j"],
            capture_output=True, text=True, timeout=2
        )
        if out.returncode == 0:
            for ws in json.loads(out.stdout or "[]"):
                wid = ws.get("id", 0)
                name = ws.get("name", str(wid))
                if wid < 0:  # özel alan (id < 0 Hyprland'da)
                    specials.append({"name": name[8:] if name.startswith("special:") else name, "active": True})
                else:
                    workspaces.append({"id": wid, "name": name, "active": True})
    except Exception:
        pass

    # 1-10 arası eksik workspace'leri doldur
    active_ids = {w["id"] for w in workspaces}
    for i in range(1, 11):
        if i not in active_ids:
            workspaces.append({"id": i, "name": str(i), "active": False})
    workspaces.sort(key=lambda x: x["id"])

    # Özel alanlar: hyprctl'den gelenlere + hyprland.conf bind'leri + modes.json
    known_specials: set[str] = set()

    # ~/.config/hypr/ altındaki tüm .conf dosyalarından togglespecialworkspace bind'lerini parse et
    import glob as _glob
    _hypr_pattern = re.compile(r"togglespecialworkspace\s*,\s*(\S+)")
    for _conf in _glob.glob(str(Path.home() / ".config/hypr/**/*.conf"), recursive=True) + \
                 [str(Path.home() / ".config/hypr/hyprland.conf")]:
        try:
            with open(_conf, encoding="utf-8", errors="ignore") as _f:
                for _line in _f:
                    _m = _hypr_pattern.search(_line)
                    if _m:
                        known_specials.add(_m.group(1).strip())
        except Exception:
            pass

    # modes.json'da daha önce kullanılmış özel alanları da ekle
    try:
        for m in list_modes_struct():
            sp = (m.get("special") or "").strip()
            if sp:
                known_specials.add(sp)
    except Exception:
        pass

    active_special_names = {s["name"] for s in specials}
    for name in sorted(known_specials):
        if name not in active_special_names:
            specials.append({"name": name, "active": False})

    return {"workspaces": workspaces, "specials": specials}
