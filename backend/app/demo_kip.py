"""Demo veri kipi — `YUKI_DEMO=1` ile açılır, varsayılan KAPALI.

Ne için: ekran görüntüsü, video, tanıtım. Arayüz bu makinenin kişisel verisini
(ev klasörü, resim arşivi, konum, ajan oturum adları, süreç komut satırları)
GÖSTERMESİN; yerine genel, açık lisanslı örnek veri görünsün.

Kapılar (her biri testte bir kez bilerek kırılır → `tests/test_demo_kip.py`):

1. **Ev değişir.** `kur()` her `app.*` modülünden ÖNCE koşar (`app/__init__.py`):
   `HOME`/`XDG_*`/`YUKI_DATA_DIR` geçici bir demo köküne çevrilir, depodaki
   `demo_veri/ev` oraya kopyalanır. `Path.home()` okuyan her kod demo evi görür.
   Gerçek ev yolunu taşıyan `YUKI_*`/`XDG_*`/`CLAUDE_*`/`CODEX_*` değişkenleri silinir.
2. **Dosya + Galeri kökü** demo evine sabitlenir (ortam değişkeni ayar dosyasını ezer).
3. **Ajan oturumları ve süreçler** sabit demo listesinden gelir; psutil'e ve
   `~/.claude`'a hiç gidilmez. Makine adı `yuki-demo`.
4. **Konum:** HTML yanıtlarına `demo-kip.js` eklenir — tarayıcının konum sorusu
   ve IP-konum servisleri (ipapi vb.) İstanbul merkeze sabitlenir, ağa çıkmaz.
   `Permissions-Policy: geolocation=()` gerçek konumu ikinci kez kapatır.
   Arka uçtaki genel IP aracı (`get_public_ip`) belgeleme adresini döner.
5. **Son süzgeç:** JSON yanıtlarında gerçek ev yolu ve kullanıcı adı kalırsa
   `~` / `demo` ile değiştirilir (ilk dört kapı kaçırırsa).

Harita katmanları (deprem, hava, yangın…) zaten kamu kaynaklıdır, olduğu gibi kalır.
"""
from __future__ import annotations

import getpass
import os
import re
import shutil
import tempfile
import time
from pathlib import Path

VERI_KAYNAK = Path(__file__).resolve().parent.parent / "demo_veri"
SEHIR = {"ad": "İstanbul", "lat": 41.0082, "lon": 28.9784}
MAKINE_ADI = "yuki-demo"
DEMO_KULLANICI = "demo"
BELGELEME_IP = "203.0.113.10"   # RFC 5737 belgeleme bloğu — gerçek kimse değil

_GERCEK_EV: str = ""
_GERCEK_KULLANICI: str = ""
_KURULDU = False


def acik() -> bool:
    return os.environ.get("YUKI_DEMO", "").strip().lower() in ("1", "true", "yes", "on", "evet")


def demo_kok() -> Path:
    ham = os.environ.get("YUKI_DEMO_KOK", "").strip()
    if ham:
        return Path(ham)
    uid = os.getuid() if hasattr(os, "getuid") else 0
    return Path(tempfile.gettempdir()) / f"yuki-demo-{uid}"


def _tarihleri_dagit(ev: Path) -> None:
    """Kopyalanan dosyaların hepsi "bugün" görünmesin: galeri aylara, dosya gezgini
    tarihlere dağılsın. Ad'dan türeyen sabit gün kayması → her açılışta aynı tablo."""
    import zlib
    taban = 1793491200  # 2026-11-01 00:00 UTC — sabit, saatten bağımsız
    # Önce dosyalar, sonra klasörler en derinden — klasöre yazılan dosya klasör tarihini bozmasın.
    for p in sorted(ev.rglob("*"), key=lambda x: (x.is_dir(), -len(x.parts))):
        gun = zlib.crc32(p.name.encode("utf-8")) % 540
        t = taban - gun * 86400 - (zlib.crc32(p.name[::-1].encode("utf-8")) % 86400)
        try:
            os.utime(p, (t, t))
        except OSError:
            pass


def kur() -> bool:
    """Demo kipi açıksa ortamı demo evine çevirir. İkinci çağrı bir şey yapmaz."""
    global _GERCEK_EV, _GERCEK_KULLANICI, _KURULDU
    if not acik() or _KURULDU:
        return _KURULDU
    _GERCEK_EV = str(Path(os.path.expanduser("~")).resolve())
    try:
        _GERCEK_KULLANICI = getpass.getuser()
    except Exception:  # noqa: BLE001
        _GERCEK_KULLANICI = ""

    kok = demo_kok()
    ev, veri = kok / "ev", kok / "veri"
    if (VERI_KAYNAK / "ev").is_dir():
        shutil.copytree(VERI_KAYNAK / "ev", ev, dirs_exist_ok=True)
    ev.mkdir(parents=True, exist_ok=True)
    _tarihleri_dagit(ev)
    veri.mkdir(parents=True, exist_ok=True)
    # Boş .env: yoksa config backend/.env'e düşer — o dosya geliştiricinin kişisel ayarı olabilir.
    (veri / ".env").touch(exist_ok=True)
    tohumla(ev, veri)

    # Gerçek evi işaret eden kişisel yollar düşer (PATH gibi sistem değişkenlerine dokunulmaz).
    for k in list(os.environ):
        if k.startswith(("YUKI_", "XDG_", "CLAUDE_", "CODEX_")) and _GERCEK_EV in os.environ[k]:
            del os.environ[k]
    os.environ.update({
        "HOME": str(ev), "USERPROFILE": str(ev),
        "XDG_CONFIG_HOME": str(ev / ".config"), "XDG_CACHE_HOME": str(ev / ".cache"),
        "XDG_DATA_HOME": str(ev / ".local/share"), "XDG_PICTURES_DIR": str(ev / "Resimler"),
        "YUKI_DATA_DIR": str(veri),
        "YUKI_DOSYA_KOKLER": str(ev),
        "YUKI_GALERI_KOKLER": str(ev / "Resimler"),
        "CLAUDE_CONFIG_DIR": str(ev / ".claude"),
        "CODEX_HOME": str(ev / ".codex"),
    })
    _KURULDU = True
    return True


# ── Plan + Yedek tohumu ───────────────────────────────────────────────────────
# Demo boş açılmasın (Plan "0 görev", Yedek tek boş kart). Tarihler açılış gününe
# göre kurulur → ekran her gün "bugün / yaklaşan / gecikmiş" dolu görünür.
# Yedekte SAHTE "son yedek" yok: demo kipinde Google bağlı değil; bağlı olmayan
# hesaba yedek tarihi yazmak Anahtar ↔ BAĞLI türünden yeni bir çelişki olurdu.
# Kurulmuş ama henüz bağlanmamış düzen gösterilir (klasörler + saat).
_LISTELER = [  # id, ad, renk, simge
    ("00000000-0000-0000-0000-000000000001", "Gelen Kutusu", "cyan", "⬡"),
    ("de000000-0000-0000-0000-000000000002", "Ev", "gold", "⌂"),
    ("de000000-0000-0000-0000-000000000003", "İş", "purple", "◆"),
    ("de000000-0000-0000-0000-000000000004", "Öğrenme", "green", "✦"),
]
_GOREVLER = [  # liste sırası, başlık, öncelik, gün (bugüne göre; None = tarihsiz), saat (nota yazılır), bitti mi, etiketler
    (1, "Market alışverişi — süt, ekmek, zeytin", "mid", 0, "18:30", False, ["ev"]),
    (2, "Haftalık rapor taslağını gönder", "high", 0, "11:00", True, ["iş"]),
    (2, "Toplantı notlarını düzenle", "mid", 0, "15:00", False, []),
    (3, "Python kursu — 4. bölüm", "low", 0, None, False, ["kurs"]),
    (1, "Kombi bakımı için servis çağır", "high", -2, None, False, ["ev"]),
    (2, "Sunum slaytlarını gözden geçir", "high", 1, "10:00", False, ["iş"]),
    (1, "Faturaları öde", "mid", 2, None, False, ["ev", "fatura"]),
    (3, "Kitap: Sapiens — 3 bölüm", "low", 3, None, False, ["okuma"]),
    (0, "Diş hekimi randevusu", "mid", 5, "14:30", False, []),
    (2, "Proje planını ekiple paylaş", "mid", 6, None, False, ["iş"]),
    (0, "Tatil için otel bak", "low", None, None, False, []),
    (3, "İngilizce kelime tekrarı", "low", None, None, False, ["dil"]),
]


def tohumla(ev: Path, veri: Path) -> None:
    """Plan ve Yedek demo verisi. Dosya zaten varsa dokunmaz (kullanıcının demo değişikliği kalır)."""
    import json
    from datetime import date, datetime, timedelta, timezone
    simdi = datetime.now(timezone.utc).replace(microsecond=0)
    bugun = date.today()

    plan = veri / "todo_store.json"
    if not plan.exists():
        listeler = [{"id": i, "name": a, "color": r, "icon": s, "position": float(n),
                     "is_archived": False, "created_at": (simdi - timedelta(days=30)).isoformat()}
                    for n, (i, a, r, s) in enumerate(_LISTELER)]
        gorevler = []
        for n, (li, baslik, onc, gun, saat, bitti, etiket) in enumerate(_GOREVLER):
            tarih = None if gun is None else (bugun + timedelta(days=gun)).isoformat()
            gorevler.append({
                "id": f"de000000-0000-0000-0001-{n:012d}", "list_id": _LISTELER[li][0],
                "title": baslik, "priority": onc,
                "status": "done" if bitti else "todo", "start_date": None,
                "due_date": tarih,   # yalnız gün (YYYY-MM-DD) — Plan ön yüzü saatli değeri "NaN" gösterir
                "notes": f"Saat {saat}" if saat else None,
                "reminder_at": None, "repeat": "none", "tags": etiket, "position": float(n),
                "estimated_time": None, "section_name": None, "is_archived": False,
                "completed_at": simdi.isoformat() if bitti else None, "deleted_at": None,
                "calendar_event_id": None, "calendar_synced": False,
                "created_at": (simdi - timedelta(days=7 - n % 5)).isoformat(),
            })
        plan.write_text(json.dumps({"version": 1, "lists": listeler, "tasks": gorevler,
                                    "subtasks": [], "dependencies": [], "budget": []},
                                   ensure_ascii=False, indent=2), encoding="utf-8")

    yedek = veri / "data" / "yedekleme.json"
    if not yedek.exists():
        kaynaklar = [{"id": f"demo{ad.lower()}", "yol": str(ev / ad), "ad": ad,
                      "acik": True, "drive_klasor_id": None}
                     for ad in ("Belgeler", "Resimler") if (ev / ad).is_dir()]
        yedek.parent.mkdir(parents=True, exist_ok=True)
        yedek.write_text(json.dumps({"acik": True, "yuki_verisi": True, "kaynaklar": kaynaklar,
                                     "zamanlama": "03:30"}, ensure_ascii=False, indent=2),
                         encoding="utf-8")


# ── Ajan oturumları ───────────────────────────────────────────────────────────
def claude_oturumlari() -> dict:
    o = [
        ("a1b2c3d4", "tarif-defteri", "main", "calisiyor", False, 1260, 4, "tmux", True),
        ("e5f60718", "hava-panosu", "ozellik/grafik", "bekliyor", False, 3480, 410, "tmux", True),
        ("90abcdef", "blog-sitesi", "main", "bitti", False, None, 5400, "", False),
    ]
    return {"kurulu": True, "oturumlar": [
        {"id": i, "proje": p, "dal": d, "durum": du, "otomatik": ot, "sure_sn": s,
         "sessiz_sn": se, "yuzey": y, "gonderilebilir": g}
        for i, p, d, du, ot, s, se, y, g in o]}


def codex_oturumlari() -> dict:
    return {"kurulu": True, "oturumlar": [
        {"id": "13579bdf", "proje": "ogrenme-notlari", "dal": "main", "durum": "bekliyor",
         "sure_sn": 900, "sessiz_sn": 620},
    ]}


# ── Süreçler ──────────────────────────────────────────────────────────────────
_SURECLER = [
    # pid, ad, cpu, mem_mb, iş parçacığı, komut
    (1, "systemd", 0.0, 12.4, 1, "/sbin/init"),
    (412, "Xorg", 1.8, 96.0, 8, "/usr/lib/Xorg :0"),
    (980, "pipewire", 0.4, 18.2, 3, "/usr/bin/pipewire"),
    (1204, "firefox", 6.2, 812.5, 92, "/usr/lib/firefox/firefox"),
    (1288, "Web Content", 3.1, 344.0, 28, "/usr/lib/firefox/firefox -contentproc"),
    (1530, "code", 2.4, 512.3, 41, "/usr/share/code/code"),
    (1702, "python3", 4.7, 210.8, 14, "python3 run.py"),
    (1811, "yuki-oss", 1.2, 286.4, 33, "yuki-oss"),
    (1990, "spotify", 0.9, 240.1, 30, "/usr/bin/spotify"),
    (2050, "thunderbird", 0.3, 198.7, 47, "/usr/lib/thunderbird/thunderbird"),
    (2210, "node", 1.6, 154.2, 11, "node server.js"),
    (2390, "gnome-terminal", 0.2, 64.0, 6, "/usr/bin/gnome-terminal"),
    (2477, "bash", 0.0, 5.1, 1, "bash"),
    (2600, "NetworkManager", 0.1, 21.3, 4, "/usr/bin/NetworkManager --no-daemon"),
    (2711, "dbus-daemon", 0.0, 4.4, 1, "dbus-daemon --session"),
]
_BASLANGIC = time.time() - 3 * 3600


def surecler(limit: int = 40, sort_key: str = "cpu") -> list[dict]:
    rows = [{"pid": p, "name": n, "cpu": c, "mem_mb": m, "threads": t, "user": DEMO_KULLANICI,
             "uptime_s": int(time.time() - _BASLANGIC) - p, "vram_mb": None, "cmd": cmd}
            for p, n, c, m, t, cmd in _SURECLER]
    key = {"cpu": "cpu", "mem": "mem_mb", "pid": "pid", "name": "name"}.get(sort_key, "cpu")
    if key == "name":
        rows.sort(key=lambda r: r["name"].lower())
    else:
        rows.sort(key=lambda r: r[key] or 0, reverse=(key != "pid"))
    return rows[:limit]


def surec_ayrinti(pid: int) -> dict | None:
    for r in surecler(len(_SURECLER), "pid"):
        if r["pid"] == pid:
            return {"pid": pid, "name": r["name"], "status": "sleeping", "cpu": r["cpu"],
                    "mem_mb": r["mem_mb"], "threads": r["threads"], "user": DEMO_KULLANICI,
                    "started": time.strftime("%H:%M:%S", time.localtime(_BASLANGIC)),
                    "uptime_s": r["uptime_s"], "cmdline": r["cmd"], "io_read_mb": 12.0, "io_write_mb": 3.5}
    return None


def disk_temizle(disk: dict) -> dict:
    """Bağlama noktası gerçek ev yolunu/kullanıcı adını taşıyorsa genelleştirir."""
    d = dict(disk)
    for alan in ("mount", "device"):
        if isinstance(d.get(alan), str):
            d[alan] = metin_temizle(d[alan])
    return d


# ── Son süzgeç ────────────────────────────────────────────────────────────────
def metin_temizle(s: str) -> str:
    if not acik():
        return s
    if _GERCEK_EV and len(_GERCEK_EV) > 1:
        s = s.replace(_GERCEK_EV, "~")
    if _GERCEK_KULLANICI and len(_GERCEK_KULLANICI) >= 3:
        s = re.sub(r"(?<![\w-])" + re.escape(_GERCEK_KULLANICI) + r"(?![\w-])", DEMO_KULLANICI, s)
    return s


def bayt_temizle(govde: bytes) -> bytes:
    try:
        metin = govde.decode("utf-8")
    except UnicodeDecodeError:
        return govde
    yeni = metin_temizle(metin)
    return govde if yeni == metin else yeni.encode("utf-8")


# ── Tarayıcı tarafı ───────────────────────────────────────────────────────────
ENJEKTE = '<script src="/demo/demo-kip.js"></script>'


def html_enjekte(govde: bytes) -> bytes:
    """`<head>`'in hemen ardına demo betiği — haritanın konum kodundan önce koşar."""
    if ENJEKTE.encode() in govde:
        return govde
    m = re.search(rb"<head[^>]*>", govde, re.IGNORECASE)
    if not m:
        return govde
    return govde[:m.end()] + ENJEKTE.encode() + govde[m.end():]


def tarayici_betigi() -> str:
    lat, lon = SEHIR["lat"], SEHIR["lon"]
    return (VERI_KAYNAK / "demo-kip.js").read_text("utf-8") \
        .replace("__LAT__", repr(lat)).replace("__LON__", repr(lon))
