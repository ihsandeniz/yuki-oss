"""rclone ile yedek denetimi — Yedek sekmesinin BULUTTA / AYARLAR / Kontrol et / Kuru çalıştır yüzü.

Kişisel Yuki'deki rclone panosunun (`/api/drive/*`) oss uyarlaması. Fark:

* **Hiçbir kişisel bilgi yok.** Uzak adı, uzaktaki yol, bant sınırı, hariç desenler
  AYARDAN gelir; varsayılanların hepsi boştur. Kod hiçbir uzak/kova/hesap adı bilmez.
* **Yazmaz.** Bu modül yalnız OKUR: `rclone lsjson` (gezgin), `rclone check`
  (karşılaştırma), `rclone copy --dry-run` (ne yükleneceği). Asıl yedeği Yuki'nin kendi
  Drive turu (`services/yedekleme.py`) alır; systemd/zamanlayıcı yoktur.
* **rclone yoksa çökmez.** `durum()` sade bir neden kodu döner (`kurulu-degil`,
  `uzak-yok`, `uzak-secilmedi`, `uzak-bulunamadi`); arayüz bunu Türkçe cümleye çevirir.

Karşılaştırma eşlemesi: her yedek klasörü `<uzak>:<yol>/<klasör adı>` ile karşılaştırılır
(Yuki'nin Drive turu da `Yuki Yedek/<klasör adı>` düzenini kullanır; kullanıcı `yol`'a
`Yuki Yedek` yazarsa aynı yere bakar).

🔑 rclone ikilisi: `YUKI_RCLONE` ortam değişkeni (testler sahte rclone verir) → `PATH`.
🔴 Bayrak enjeksiyonu: kullanıcı metni hiçbir zaman ayrı bir argv öğesi olarak `-` ile
başlayamaz — uzak adı düzenli ifadeyle sınırlı, hariç desenler `--exclude=<desen>`
bitişik biçimde verilir, yerel yollar mutlaktır (`/` ile başlar).
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import re
import shutil
import tempfile
from datetime import datetime
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

_DATA_ROOT = Path(os.getenv("YUKI_DATA_DIR") or Path(__file__).resolve().parents[2])
AYAR_YOLU = _DATA_ROOT / "data" / "rclone-yedek.json"

VARSAYILAN: dict[str, Any] = {
    "uzak": "",            # rclone uzak adı (`rclone listremotes` çıktısından, iki nokta olmadan)
    "yol": "",             # uzaktaki klasör (boş = uzağın kökü)
    "bant": "",            # --bwlimit (boş = sınırsız)
    "aktarim": 4,          # --transfers
    "denetleyici": 8,      # --checkers
    "haric": [],           # ek --exclude desenleri
}

UZAK_DESEN = re.compile(r"^[A-Za-z0-9_][A-Za-z0-9_. -]{0,62}$")
BANT_DESEN = re.compile(r"^(\d{1,6}(\.\d{1,3})?[KMGkmg]?)?$")
YOL_AZAMI = 512
DESEN_AZAMI = 100
SURUM_SURE = 10
GOZAT_SURE = 60
IS_SURE = 1800          # tek klasör kontrol/kuru çalıştırma tavanı (sn)
SATIR_AZAMI = 40        # sonuçta klasör başına gösterilen dosya satırı


class AyarHatasi(ValueError):
    """Arayüze KOD olarak gider (`yedek.r-hata-<kod>`)."""

    def __init__(self, kod: str):
        super().__init__(kod)
        self.kod = kod


# ── Ayar ─────────────────────────────────────────────────────────────────────

def ayar_oku() -> dict[str, Any]:
    d = dict(VARSAYILAN)
    try:
        ham = json.loads(AYAR_YOLU.read_text("utf-8"))
        if isinstance(ham, dict):
            for k in VARSAYILAN:
                if k in ham:
                    d[k] = ham[k]
    except FileNotFoundError:
        pass
    except Exception:
        logger.warning("rclone-yedek.json okunamadı, varsayılana düşülüyor", exc_info=True)
    d["haric"] = [x for x in (d.get("haric") or []) if isinstance(x, str)]
    return d


def _ayar_yaz(d: dict[str, Any]) -> None:
    AYAR_YOLU.parent.mkdir(parents=True, exist_ok=True)
    gecici = AYAR_YOLU.with_suffix(".json.tmp")
    gecici.write_text(json.dumps(d, ensure_ascii=False, indent=2), "utf-8")
    gecici.replace(AYAR_YOLU)


def yol_temizle(ham: str | None) -> str:
    """Uzaktaki göreli yol: `..` yok, mutlak değil, denetim karakteri yok, `:` yok."""
    yol = (ham or "").strip().strip("/")
    if not yol:
        return ""
    if len(yol) > YOL_AZAMI or any(ord(c) < 32 for c in yol) or ":" in yol or "\\" in yol:
        raise AyarHatasi("yol")
    parcalar = [p for p in yol.split("/") if p]
    if any(p in (".", "..") for p in parcalar) or parcalar[0].startswith("-"):
        raise AyarHatasi("yol")
    return "/".join(parcalar)


def _desen_temizle(ham: list[str]) -> list[str]:
    out = []
    for x in ham:
        x = (x or "").strip()
        if not x:
            continue
        if len(x) > 200 or any(ord(c) < 32 for c in x):
            raise AyarHatasi("desen")
        out.append(x)
    if len(out) > DESEN_AZAMI:
        raise AyarHatasi("desen")
    return out


def ayar_kaydet(yeni: dict[str, Any], uzaklar: list[str] | None) -> dict[str, Any]:
    d = ayar_oku()
    if "uzak" in yeni and yeni["uzak"] is not None:
        u = str(yeni["uzak"]).strip().rstrip(":")
        if u and not UZAK_DESEN.fullmatch(u):
            raise AyarHatasi("uzak")
        # rclone kuruluysa uzak gerçekten tanımlı olmalı (yazım hatası sessizce kalmasın)
        if u and uzaklar is not None and u not in uzaklar:
            raise AyarHatasi("uzak-bulunamadi")
        d["uzak"] = u
    if "yol" in yeni and yeni["yol"] is not None:
        d["yol"] = yol_temizle(yeni["yol"])
    if "bant" in yeni and yeni["bant"] is not None:
        b = str(yeni["bant"]).strip()
        if not BANT_DESEN.fullmatch(b):
            raise AyarHatasi("bant")
        d["bant"] = b
    if "aktarim" in yeni and yeni["aktarim"] is not None:
        d["aktarim"] = max(1, min(32, int(yeni["aktarim"])))
    if "denetleyici" in yeni and yeni["denetleyici"] is not None:
        d["denetleyici"] = max(1, min(64, int(yeni["denetleyici"])))
    if "haric" in yeni and yeni["haric"] is not None:
        d["haric"] = _desen_temizle(list(yeni["haric"]))
    _ayar_yaz(d)
    return d


# ── rclone çağrısı ───────────────────────────────────────────────────────────

def rclone_yolu() -> str | None:
    ortam = os.environ.get("YUKI_RCLONE", "").strip()
    if ortam:
        return ortam if os.path.isfile(ortam) and os.access(ortam, os.X_OK) else None
    return shutil.which("rclone")


async def _kos(argv: list[str], sure: float) -> tuple[int, str, str]:
    """rclone'u kabuksuz çalıştır. Zaman aşımında süreci öldürür."""
    ikili = rclone_yolu()
    if not ikili:
        return 127, "", "rclone yok"
    try:
        proc = await asyncio.create_subprocess_exec(
            ikili, *argv, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE,
            stdin=asyncio.subprocess.DEVNULL)
    except OSError as e:
        return 127, "", str(e)
    try:
        out, err = await asyncio.wait_for(proc.communicate(), timeout=sure)
    except asyncio.TimeoutError:
        try:
            proc.kill()
            await proc.wait()
        except ProcessLookupError:
            pass
        return 124, "", "zaman aşımı"
    return proc.returncode or 0, out.decode(errors="replace"), err.decode(errors="replace")


def _ortak_bayraklar(a: dict[str, Any]) -> list[str]:
    b = [f"--checkers={int(a.get('denetleyici') or 8)}", f"--transfers={int(a.get('aktarim') or 4)}"]
    if a.get("bant"):
        b.append(f"--bwlimit={a['bant']}")
    return b


def _hedef(a: dict[str, Any], alt: str = "") -> str:
    parca = "/".join(x for x in (a.get("yol") or "", alt) if x)
    return f"{a['uzak']}:{parca}"


async def uzaklar() -> list[str] | None:
    """Tanımlı uzak adları; rclone yoksa None."""
    if not rclone_yolu():
        return None
    kod, out, _ = await _kos(["listremotes"], SURUM_SURE)
    if kod != 0:
        return []
    return [s.strip().rstrip(":") for s in out.splitlines() if s.strip().endswith(":")]


async def durum() -> dict[str, Any]:
    a = ayar_oku()
    ikili = rclone_yolu()
    surum = None
    liste: list[str] = []
    if ikili:
        kod, out, _ = await _kos(["version"], SURUM_SURE)
        if kod == 0 and out.strip():
            surum = out.strip().splitlines()[0][:80]
        liste = await uzaklar() or []
    if not ikili:
        neden = "kurulu-degil"
    elif not liste:
        neden = "uzak-yok"
    elif not a["uzak"]:
        neden = "uzak-secilmedi"
    elif a["uzak"] not in liste:
        neden = "uzak-bulunamadi"
    else:
        neden = None
    return {"kurulu": bool(ikili), "surum": surum, "uzaklar": liste, "ayar": a,
            "hazir": neden is None, "neden": neden,
            "kontrol": _ozet_durum("kontrol"), "kuru": _ozet_durum("kuru")}


async def gozat(alt: str | None) -> dict[str, Any]:
    d = await durum()
    if not d["hazir"]:
        return {"ok": False, "neden": d["neden"], "ogeler": []}
    a = d["ayar"]
    alt_yol = yol_temizle(alt)
    kod, out, err = await _kos(["lsjson", "--max-depth=1", "--no-mimetype", _hedef(a, alt_yol)], GOZAT_SURE)
    if kod != 0:
        return {"ok": False, "neden": "zaman-asimi" if kod == 124 else "okunamadi",
                "ayrinti": err.strip()[-300:], "ogeler": [], "yol": alt_yol}
    try:
        ham = json.loads(out or "[]")
    except Exception:
        return {"ok": False, "neden": "okunamadi", "ogeler": [], "yol": alt_yol}
    ogeler = [{"ad": str(x.get("Name", "")), "klasor": bool(x.get("IsDir")),
               "boyut": int(x.get("Size") or 0) if not x.get("IsDir") else None,
               "tarih": str(x.get("ModTime", ""))[:19]} for x in ham if isinstance(x, dict)]
    ogeler.sort(key=lambda o: (not o["klasor"], o["ad"].lower()))
    return {"ok": True, "yol": alt_yol, "kok": _hedef(a), "ogeler": ogeler}


# ── Arka plan işleri (Kontrol et · Kuru çalıştır) ────────────────────────────

_ISLER: dict[str, dict[str, Any]] = {
    ad: {"calisiyor": False, "basladi": None, "bitti": None, "ilerleme": "", "sonuc": None}
    for ad in ("kontrol", "kuru")
}
_GOREVLER: dict[str, asyncio.Task] = {}


def _ozet_durum(ad: str) -> dict[str, Any]:
    s = _ISLER[ad]
    return {"calisiyor": s["calisiyor"], "basladi": s["basladi"], "bitti": s["bitti"],
            "ilerleme": s["ilerleme"], "sonuc": s["sonuc"]}


def is_durumu(ad: str) -> dict[str, Any]:
    return _ozet_durum(ad)


def _kaynaklar() -> list[dict[str, Any]]:
    from app.services import yedekleme as _y
    return _y.etkin_kaynaklar()


def _haric(a: dict[str, Any]) -> list[str]:
    from app.services import yedekleme as _y
    desenler = list(_y.VARSAYILAN_ISTISNALAR) + list(a.get("haric") or [])
    return [f"--exclude={d}" for d in desenler if d]


def _satir_say(yol: Path) -> tuple[int, list[str]]:
    try:
        satirlar = [s for s in yol.read_text("utf-8", errors="replace").splitlines() if s.strip()]
    except FileNotFoundError:
        return 0, []
    return len(satirlar), satirlar[:SATIR_AZAMI]


async def _kontrol_tek(a: dict, kaynak: dict, gecici: Path) -> dict[str, Any]:
    eksik_f, fark_f = gecici / f"{kaynak['id']}-eksik", gecici / f"{kaynak['id']}-fark"
    argv = ["check", kaynak["yol"], _hedef(a, kaynak["ad"]), "--one-way", "--size-only",
            f"--missing-on-dst={eksik_f}", f"--differ={fark_f}", *_ortak_bayraklar(a), *_haric(a)]
    kod, _out, err = await _kos(argv, IS_SURE)
    if kod == 124:
        return {"klasor": kaynak["ad"], "ok": False, "neden": "zaman-asimi"}
    eksik, eksik_s = _satir_say(eksik_f)
    fark, fark_s = _satir_say(fark_f)
    # rclone check fark bulunca 1 döner — bu hata değil. Rapor dosyası hiç yazılmadıysa
    # ve kod sıfır değilse gerçekten koşamadı (uzak yok, ağ yok…).
    if kod not in (0, 1) or (kod == 1 and not eksik_f.exists() and not fark_f.exists()):
        return {"klasor": kaynak["ad"], "ok": False, "neden": "okunamadi", "ayrinti": err.strip()[-300:]}
    return {"klasor": kaynak["ad"], "hedef": _hedef(a, kaynak["ad"]), "ok": True,
            "esit": eksik == 0 and fark == 0, "eksik": eksik, "fark": fark,
            "eksik_satir": eksik_s, "fark_satir": fark_s}


_KURU_SATIR = re.compile(r"NOTICE: (.+?): Skipped (copy|update modification time|make directory)")


async def _kuru_tek(a: dict, kaynak: dict, _gecici: Path) -> dict[str, Any]:
    argv = ["copy", kaynak["yol"], _hedef(a, kaynak["ad"]), "--dry-run", *_ortak_bayraklar(a), *_haric(a)]
    kod, out, err = await _kos(argv, IS_SURE)
    if kod == 124:
        return {"klasor": kaynak["ad"], "ok": False, "neden": "zaman-asimi"}
    if kod != 0:
        return {"klasor": kaynak["ad"], "ok": False, "neden": "okunamadi", "ayrinti": err.strip()[-300:]}
    dosyalar = [m.group(1) for m in _KURU_SATIR.finditer(out + "\n" + err) if m.group(2) == "copy"]
    return {"klasor": kaynak["ad"], "hedef": _hedef(a, kaynak["ad"]), "ok": True,
            "gidecek": len(dosyalar), "satirlar": dosyalar[:SATIR_AZAMI]}


async def _is_kos(ad: str, a: dict, kaynaklar: list[dict]) -> None:
    s = _ISLER[ad]
    sonuclar: list[dict[str, Any]] = []
    tek = _kontrol_tek if ad == "kontrol" else _kuru_tek
    try:
        with tempfile.TemporaryDirectory(prefix="yuki-rclone-") as g:
            for i, k in enumerate(kaynaklar, 1):
                s["ilerleme"] = f"{i}/{len(kaynaklar)} · {k['ad']}"
                if k.get("id") == "yuki":
                    # Yuki verisi desenle seçilmiş dosyaları yedekler; klasörün tamamıyla
                    # karşılaştırmak "binlerce eksik" diye yanlış alarm verirdi.
                    sonuclar.append({"klasor": k["ad"], "ok": False, "neden": "yuki-atlandi"})
                    continue
                if not Path(k["yol"]).is_dir():
                    sonuclar.append({"klasor": k["ad"], "ok": False, "neden": "yerel-yok"})
                    continue
                sonuclar.append(await tek(a, k, Path(g)))
    except Exception:
        logger.exception("rclone %s işi düştü", ad)
    finally:
        tamam = [r for r in sonuclar if r.get("ok")]
        ozet: dict[str, Any] = {"klasorler": sonuclar, "toplam": len(kaynaklar),
                                "denetlenen": len(tamam)}
        if ad == "kontrol":
            ozet["eksik"] = sum(r.get("eksik", 0) for r in tamam)
            ozet["fark"] = sum(r.get("fark", 0) for r in tamam)
            ozet["hepsi_esit"] = bool(tamam) and all(r["esit"] for r in tamam)
        else:
            ozet["gidecek"] = sum(r.get("gidecek", 0) for r in tamam)
        s.update({"calisiyor": False, "sonuc": ozet, "ilerleme": "",
                  "bitti": datetime.now().isoformat(timespec="seconds")})


async def is_baslat(ad: str) -> dict[str, Any]:
    """`kontrol` ya da `kuru` işini arka planda başlat. Hemen döner."""
    s = _ISLER[ad]
    if s["calisiyor"]:
        return {"ok": True, "baslatildi": False, "calisiyor": True}
    d = await durum()
    if not d["hazir"]:
        return {"ok": False, "neden": d["neden"]}
    kaynaklar = _kaynaklar()
    if not [k for k in kaynaklar if k.get("id") != "yuki"]:
        return {"ok": False, "neden": "klasor-yok"}
    s.update({"calisiyor": True, "basladi": datetime.now().isoformat(timespec="seconds"),
              "bitti": None, "ilerleme": "", "sonuc": None})
    _GOREVLER[ad] = asyncio.create_task(_is_kos(ad, d["ayar"], kaynaklar))
    return {"ok": True, "baslatildi": True, "calisiyor": True}
