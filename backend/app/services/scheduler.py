"""Proaktif Scheduler — APScheduler ile zamanlanmış görevler ve hatırlatıcılar.

Faz 2: Sabah brifing (günlük 08:00), kullanıcı tanımlı hatırlatıcılar,
        ConnectionManager üzerinden WebSocket push + TTS entegrasyonu.
"""
from __future__ import annotations

import asyncio
import base64
import json
import logging
import re
import uuid
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import TYPE_CHECKING

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.jobstores.memory import MemoryJobStore

from app.config import SCHEDULER_ENABLED, SCHEDULER_TIMEZONE

logger = logging.getLogger(__name__)

if TYPE_CHECKING:
    from app.api.websocket import ConnectionManager

_scheduler: AsyncIOScheduler | None = None
_cm: ConnectionManager | None = None

def _brifing_tarih_metni(gun: date) -> str:
    """'18 Eylül 2026, Cuma' — sabah brifingindeki tarih parçası.

    🔴 2026-09-18 (FAZ 0): burası `today.strftime('%d %B %Y')` idi. `%B` işletim
    sisteminin locale'ine bağlıdır ve bu projede **hiç `setlocale` çağrılmıyor**
    (grep: 0) → Türkçe cümlenin içine İngilizce ay adı basıyordu:
    *"Günaydın. Bugün 18 **September** 2026, Cuma."* — canlı ölçüldü, yaşayan arıza.

    Ayrı fonksiyon çünkü asıl brifing async ve WS yayını yapıyor; metin böyle
    **çalıştırılarak** ölçülebiliyor (`tests/test_faz0_yerellestirme.py`).
    Gün/ay adı kopyası burada TUTULMAZ → `app.services.bicim` tek kaynaktır.
    """
    from app.services import bicim
    return f"{bicim.uzun_tarih(gun)}, {bicim.gun_adi(gun)}"


# ------------------------------------------------------------------ #
# Singleton
# ------------------------------------------------------------------ #

def get_scheduler() -> AsyncIOScheduler:
    global _scheduler
    if _scheduler is None:
        _scheduler = AsyncIOScheduler(
            jobstores={"default": MemoryJobStore()},
            timezone=SCHEDULER_TIMEZONE,
        )
    return _scheduler


def set_connection_manager(cm: ConnectionManager) -> None:
    global _cm
    _cm = cm


# ------------------------------------------------------------------ #
# Push helpers
# ------------------------------------------------------------------ #

async def _push_proactive(text: str, kaynak: str = "yuki", telefona: bool = True) -> None:
    """Yuki'nin kendiliğinden söylediği bir şeyi iletir: ekran (WS) · telefon (Web Push) · ses (TTS).

    Her kanalın sonucu `yuki_dedi`'ye yazılır — BİLDİRİM odasının "Yuki ne dedi" günlüğü.
    🔴 2026-09-27: ① `_cm` yokken erken dönüyordu → telefon bildirimi de GİTMİYORDU (açık pencere
    olmaması tam da telefonun gerektiği an). ② Ölü `app.api.intel` importu (haber izleyici artığı)
    her mesajda sessizce patlıyordu. ③ Ekran yokken de TTS sentezleniyordu (kimse dinlemiyor).
    """
    ekran = telefon = ses = 0
    if _cm:
        # frontend (core.js) bunu sohbete Yuki balonu olarak basar
        ekran = await _cm.broadcast({"type": "proactive_message", "text": text, "kaynak": kaynak}) or 0
    else:
        logger.warning("Proaktif mesaj ekrana gönderilemedi: ConnectionManager henüz ayarlanmadı.")

    if telefona:
        try:
            from app.api.push import send_push_to_all
            telefon = await send_push_to_all("Yuki 🌸", text[:120]) or 0
        except Exception as e:
            logger.debug("Web Push gönderilemedi: %s", e)

    if ekran:
        # TTS → audio frame (frontend 'audio' handler'ı oynatır)
        try:
            from app.services.tts import synthesize
            from app.services.state_machine import get_state_machine, YukiState

            sm = get_state_machine()
            await sm.transition(YukiState.TALKING)
            audio = await asyncio.wait_for(synthesize(text), timeout=20.0)
            if audio:
                ses = 1 if await _cm.broadcast({
                    "type": "audio",
                    "data": base64.b64encode(audio).decode("ascii"),
                    "text": text,
                }) else 0
            await sm.force(YukiState.IDLE)
        except asyncio.TimeoutError:
            logger.warning("Proaktif TTS zaman aşımına uğradı.")
        except Exception as e:
            logger.warning("Proaktif TTS başarısız: %s", e)

    try:
        from app.api.push import yuki_dedi_kaydet
        await yuki_dedi_kaydet(kaynak, text, ekran, telefon, ses)
    except Exception as e:  # noqa: BLE001
        logger.debug("yuki_dedi kaydı atlandı: %s", e)


# ------------------------------------------------------------------ #
# Yerleşik görevler
# ------------------------------------------------------------------ #

async def _do_morning_briefing() -> None:
    """Sabah brifing — her gün 08:00."""
    today = date.today()
    from app.mesajlar import M
    text = M("brifing.gunaydin", tarih=_brifing_tarih_metni(today))

    # Todo istatistikleri ekle
    try:
        from app.services.tools.todo_tools import get_todo_stats
        stats = await get_todo_stats()
        if stats["due_today"] > 0 or stats["overdue"] > 0:
            if stats["overdue"] > 0:
                text += M("brifing.gorevler-gecikmeli", bugun=stats["due_today"], geciken=stats["overdue"])
            else:
                text += M("brifing.gorevler", bugun=stats["due_today"])
    except Exception:
        pass

    logger.info("Sabah brifing gönderiliyor.")
    await _push_proactive(text, "sabah")


async def _sabah_telafisi() -> None:
    """Uygulama 08:00'de kapalıysa cron işi kaçar (masaüstü uygulamasında olağan durum).
    08-12 arası açılışta bugün sabah özeti gitmemişse bir kez gönderilir."""
    try:
        from app.api.push import yuki_dedi_bugun_var_mi
        if await yuki_dedi_bugun_var_mi("sabah"):
            return
    except Exception:  # noqa: BLE001
        return
    await _do_morning_briefing()


# ------------------------------------------------------------------ #
# Hatırlatıcı yönetimi
# ------------------------------------------------------------------ #

def parse_when(when: str) -> datetime | None:
    """Zaman ifadesini datetime'a çevirir.

    Desteklenen formatlar:
    - "5 dakika sonra" / "2 saat sonra" / "10 saniye sonra" / "3 gün sonra"
    - "14:30"  (bugün; geçmişse yarın)
    - ISO 8601: "2026-05-05T15:00"
    """
    now = datetime.now()
    w = when.strip().lower()

    # Geçmiş ifade alarm olamaz; aşağıdaki desen "önce"yi görmez, ileri tarihe kurardı.
    if re.search(r"\bönce\b", w):
        return None

    # "X birim sonra"
    m = re.match(r"(\d+)\s*(saniye|dakika|saat|gün)", w)
    if m:
        n = int(m.group(1))
        unit = m.group(2)
        deltas = {
            "saniye": timedelta(seconds=n),
            "dakika": timedelta(minutes=n),
            "saat":   timedelta(hours=n),
            "gün":    timedelta(days=n),
        }
        return now + deltas[unit]

    # "HH:MM"
    m = re.match(r"^(\d{1,2}):(\d{2})$", when.strip())
    if m:
        dt = now.replace(
            hour=int(m.group(1)), minute=int(m.group(2)),
            second=0, microsecond=0,
        )
        if dt <= now:
            dt += timedelta(days=1)
        return dt

    # "DD.MM.YYYY HH:MM:SS" veya "DD.MM.YYYY HH:MM"
    m = re.match(r"^(\d{1,2})\.(\d{1,2})\.(\d{4})\s+(\d{1,2}):(\d{2})(?::(\d{2}))?$", when.strip())
    if m:
        try:
            return datetime(
                int(m.group(3)), int(m.group(2)), int(m.group(1)),
                int(m.group(4)), int(m.group(5)), int(m.group(6) or 0),
            )
        except (ValueError, TypeError):
            pass

    # ISO datetime
    try:
        return _naif_yerel(datetime.fromisoformat(when.strip()))
    except (ValueError, TypeError):
        return None


def _naif_yerel(dt: datetime) -> datetime:
    """Ofsetli (aware) tarihi bu makinenin yerel saatine çevirip naif yap — öbür dallar ve `register_reminders`'ın
    `now`'ı naif yerel. Aware kalırsa `rd <= now` TypeError verir; yeniden başlatmada `except` onu yutup kaydı
    diskten SİLİYORDU (denetim 2026-11-16, MNT-F004)."""
    return dt.astimezone().replace(tzinfo=None) if dt.tzinfo is not None else dt


# ── DURABLE store (reminders.json) — restart-güvenli, yazılabilir DATA_DIR'de ──
from app.config import DATA_DIR
_REMINDERS_PATH = DATA_DIR / "reminders.json"

# Tekrarlı ifade birim eşlemesi — uzun ekler önce, tek harfler en sonda (yanlış eşleşme önlenir)
_UNIT_ORDER = [
    # 🔴 hafta/ay/yıl tek harflerden ÖNCE: yoksa "hafta" → "h" (saat), "months" → "m" (dakika)
    # eşleşiyordu — "her 2 hafta" alarmı her 2 saatte çalıyordu. Hafta gün katına çevrilir
    # (parse_recurring); ay/yıl aralıkla doğru kurulamaz (ay uzunluğu değişir) → None = red.
    ("hafta", "weeks"), ("week", "weeks"),
    ("ay", None), ("month", None), ("yıl", None), ("yil", None), ("year", None),
    ("saniye", "seconds"), ("saat", "hours"), ("dakika", "minutes"),
    ("dk", "minutes"), ("min", "minutes"), ("sn", "seconds"),
    ("sa", "hours"), ("gün", "days"), ("gun", "days"),
    ("m", "minutes"), ("h", "hours"), ("d", "days"), ("g", "days"),
]
_HUMAN_UNIT = {"seconds": "saniyede", "minutes": "dakikada", "hours": "saatte", "days": "günde"}
# Birim → katalog anahtarının son parçası. `_HUMAN_UNIT` Türkçe metni tutar ve
# bugün yalnız ESKİ kayıtların yedeği olarak duruyor; cümlenin kendisi artık
# katalogdan geliyor (aşağıda).
_UNIT_KEY = {"seconds": "saniye", "minutes": "dakika", "hours": "saat", "days": "gun"}


def insan_aralik(interval: dict | None, dil: str | None = None) -> str | None:
    """`{'minutes': 20}` → *"her 20 dakikada"* / *"every 20 minutes"*.

    🔴 Neden okuma anında: bu cümle 2026-09-20'ye kadar `add_recurring_reminder`
    içinde üretilip `reminders.json`'a **yazılıyordu**. Yani kullanıcı
    hatırlatıcıyı Türkçe arayüzdeyken kurduysa, arayüzü İngilizce'ye alsa bile
    o satır sonsuza kadar Türkçe kalıyordu — kaydın kendisi bir dil seçimi
    taşıyordu. Yapı (`interval`) zaten kayıtlıydı; eksik olan onu kullanmaktı.

    ⚠️ Çoğul ayrımı `Mc` ile DEĞİL anahtarla yapılıyor: burada iki ayrı cümle
    var ("every minute" ↔ "every 5 minutes"), sayısı değişen tek bir cümle
    değil — `n=1` hâlinde sayı hiç yazılmaz (TR'de de: *"her dakikada"*).
    """
    if not isinstance(interval, dict) or not interval:
        return None
    alan = next((a for a in ("days", "hours", "minutes", "seconds") if interval.get(a)), None)
    if alan is None:
        return None
    n = int(interval[alan])
    birim = _UNIT_KEY[alan]
    from app.mesajlar import M

    if n == 1:
        return M(f"hatirlatici.her-{birim}", dil=dil)
    return M(f"hatirlatici.her-n-{birim}", dil=dil, n=n)
# Sayısız ('her saat', 'günde bir') tekrarda örtük n=1 — yanlış eşleşmeyi önlemek için tam kelime
_FULL_UNITS = {
    "saniye": "seconds", "dakika": "minutes", "saat": "hours", "gün": "days", "gun": "days",
    "second": "seconds", "minute": "minutes", "hour": "hours", "day": "days",
    "hafta": "weeks", "week": "weeks",
}


def _load_reminders() -> list[dict]:
    # Bozuk dosya ezilmeden önce `.bozuk-<zaman>` olur (eskiden `[]` dönüp sonraki eklemede
    # tüm hatırlatıcıları yedeksiz siliyordu); yazım atomik.
    from app.services import guvenli_json
    return guvenli_json.oku(_REMINDERS_PATH, [], list)


def _save_reminders(items: list[dict]) -> None:
    from app.services import guvenli_json
    guvenli_json.yaz(_REMINDERS_PATH, items)


def _remove_reminder_record(job_id: str) -> None:
    items = _load_reminders()
    new = [r for r in items if r.get("id") != job_id]
    if len(new) != len(items):
        _save_reminders(new)


def parse_recurring(when: str) -> tuple[dict, str] | None:
    """Tekrarlı ifadeyi (interval_kwargs, insan-okur metin) döndürür; değilse None.

    Örnek: 'her 20 dakika', 'her 2 saat', '20 dakikada bir', 'every 20m'.
    """
    w = (when or "").strip().lower()
    # 🔴 Saatli tekrar ("her gün 20:00") DESTEKLENMİYOR: aralık tetikleyicisi saati yok sayıp
    # kurulduğu andan itibaren her 24 saatte çalıyordu (sessizce yanlış alarm). Reddedilir →
    # uç 400 döner, sohbet aracı kullanıcıya söyler. Kişiselde yalnız arayüz reddediyordu.
    if re.search(r"\b\d{1,2}[:.]\d{2}\b", w):
        return None
    # "her/every N birim"
    m = re.search(r"(?:her|every)\s*(\d+)\s*([a-zçğü]+)", w)
    if not m:
        # "N birimde/birimda bir"
        m = re.search(r"(\d+)\s*([a-zçğü]+?)(?:da|de|ta|te)\s*bir", w)
    if m:
        n = int(m.group(1))
        field = next((val for pre, val in _UNIT_ORDER if m.group(2).startswith(pre)), None)
        if field is None or n <= 0:
            return None
        if field == "weeks":
            field, n = "days", n * 7
        return {field: n}, f"her {n} {_HUMAN_UNIT[field]}"

    # Sayısız (örtük n=1): 'her saat', 'her gün', 'saatte bir', 'günde bir' — tam kelime şart
    m = re.search(r"(?:her|every)\s+([a-zçğü]+)", w) or re.search(r"([a-zçğü]+?)(?:da|de|ta|te)\s*bir", w)
    if m:
        field = _FULL_UNITS.get(m.group(1))
        if field == "weeks":
            return {"days": 7}, f"her 7 {_HUMAN_UNIT['days']}"
        if field:
            return {field: 1}, f"her {_HUMAN_UNIT[field]}"
    return None


async def _fire_reminder(job_id: str, message: str, kind: str) -> None:
    """Hatırlatıcı tetiklenince mesajı ilet; tek seferlikse kaydı temizle."""
    from app.mesajlar import M

    # 🔑 Bu metin üç yere birden gider: sohbet balonu · telefon bildirimi ·
    # `push_notifications` tablosu (= BİLDİRİM odasının listesi). Sabit
    # "Hatırlatma:" öneki İngilizce ekranda o listenin her satırında
    # görünüyordu ve panel turu bunu göremiyordu — liste boşken ölçülüyor.
    await _push_proactive(M("hatirlatici.bildirim", mesaj=message), "alarm")
    if kind == "once":
        try:
            _remove_reminder_record(job_id)
        except Exception:  # noqa: BLE001
            pass


def add_reminder(message: str, run_date: datetime) -> str:
    """Tek seferlik hatırlatıcı ekler (durable). job_id döner."""
    job_id = f"reminder_{uuid.uuid4().hex[:8]}"
    items = _load_reminders()
    items.append({"id": job_id, "kind": "once", "message": message,
                  "run_date": run_date.isoformat()})
    _save_reminders(items)
    get_scheduler().add_job(
        _fire_reminder, trigger="date", run_date=run_date,
        args=[job_id, message, "once"], id=job_id,
        replace_existing=True, misfire_grace_time=3600,
    )
    logger.info("Hatırlatıcı eklendi (once): %s → %s", job_id, run_date.isoformat())
    return job_id


def add_recurring_reminder(message: str, interval_kwargs: dict, human: str) -> str:
    """Tekrarlı hatırlatıcı ekler (durable). İptal edilene kadar çalar. job_id döner."""
    job_id = f"reminder_{uuid.uuid4().hex[:8]}"
    items = _load_reminders()
    items.append({"id": job_id, "kind": "repeat", "message": message,
                  "interval": interval_kwargs, "human": human})
    _save_reminders(items)
    get_scheduler().add_job(
        _fire_reminder, trigger="interval",
        args=[job_id, message, "repeat"], id=job_id,
        replace_existing=True, **interval_kwargs,
    )
    logger.info("Hatırlatıcı eklendi (repeat): %s → %s", job_id, human)
    return job_id


def list_reminders() -> list[dict]:
    """Aktif hatırlatıcıları (durable kayıttan) listeler."""
    sched = get_scheduler()
    out = []
    for r in _load_reminders():
        job = sched.get_job(r.get("id", ""))
        nrt = getattr(job, "next_run_time", None) if job else None
        nxt = nrt.isoformat() if nrt else None
        # Cümle önce YAPIDAN kurulur; yapı yoksa (2026-09-20 öncesi kayıtlar)
        # diskteki donmuş Türkçe metne düşülür — eski kayıt KAYBOLMAZ, yalnız
        # çevrilemez. Ters sıra yazılsaydı yeni mekanizma hiç devreye girmezdi.
        insan = insan_aralik(r.get("interval")) or r.get("human")
        out.append({
            "id": r.get("id"),
            "kind": r.get("kind", "once"),
            "message": r.get("message", ""),
            "human": insan,
            "next_run": nxt,
        })
    return out


def cancel_reminder(job_id: str) -> bool:
    """Hatırlatıcıyı iptal eder (job + durable kayıt). Başarılıysa True."""
    sched = get_scheduler()
    removed_job = False
    try:
        sched.remove_job(job_id)
        removed_job = True
    except Exception:  # noqa: BLE001
        pass
    before = _load_reminders()
    after = [r for r in before if r.get("id") != job_id]
    removed_rec = len(after) != len(before)
    if removed_rec:
        _save_reminders(after)
    if removed_job or removed_rec:
        logger.info("Hatırlatıcı iptal edildi: %s", job_id)
    return removed_job or removed_rec


def cancel_all_reminders() -> int:
    """Tüm hatırlatıcıları iptal eder. İptal edilen sayısını döner."""
    items = _load_reminders()
    sched = get_scheduler()
    for r in items:
        try:
            sched.remove_job(r.get("id", ""))
        except Exception:  # noqa: BLE001
            pass
    if items:
        _save_reminders([])
    return len(items)


def register_reminders() -> None:
    """Startup'ta reminders.json'daki hatırlatıcıları yeniden zamanla (restart-güvenlik)."""
    if not SCHEDULER_ENABLED:
        return
    items = _load_reminders()
    if not items:
        return
    now = datetime.now()
    keep, ok = [], 0
    for r in items:
        try:
            kind = r.get("kind", "once")
            if kind == "repeat":
                iv = r.get("interval") or {}
                if not iv:
                    continue
                get_scheduler().add_job(
                    _fire_reminder, trigger="interval",
                    args=[r["id"], r.get("message", ""), "repeat"],
                    id=r["id"], replace_existing=True, **iv,
                )
            else:
                rd = _naif_yerel(datetime.fromisoformat(r["run_date"]))  # eski aware kayıtlar da kurtulur
                # Restart sırasında zamanı geçmiş tek-seferlik → borçlu, 5 sn sonra teslim et
                if rd <= now:
                    rd = now + timedelta(seconds=5)
                get_scheduler().add_job(
                    _fire_reminder, trigger="date", run_date=rd,
                    args=[r["id"], r.get("message", ""), "once"],
                    id=r["id"], replace_existing=True, misfire_grace_time=3600,
                )
            keep.append(r)
            ok += 1
        except Exception as e:  # noqa: BLE001
            logger.warning("hatırlatıcı '%s' yeniden zamanlanamadı: %s", r.get("id"), e)
    if len(keep) != len(items):
        _save_reminders(keep)
    logger.info("hatırlatıcılar: %d/%d yeniden zamanlandı", ok, len(items))


# ------------------------------------------------------------------ #
# Periyodik Görevler
# ------------------------------------------------------------------ #

async def _do_memory_gc() -> None:
    """Hafıza GC — her gece 03:00. Eski/düşük önemli konuşma kayıtlarını siler."""
    from app.config import MEMORY_ENABLED, SESSION_ID
    if not MEMORY_ENABLED:
        return
    try:
        from app.services.memory import Memory
        mem = Memory(SESSION_ID)
        deleted = await mem.cleanup()
        logger.info("Hafıza GC tamamlandı: %d kayıt silindi.", deleted)
    except Exception as e:
        logger.warning("Hafıza GC başarısız: %s", e)


async def _do_overdue_reminder() -> None:
    """Gecikmiş görev hatırlatıcısı — her gün 09:00."""
    try:
        from app.services.tools.todo_tools import get_todo_stats
        stats = await get_todo_stats()
        if stats["overdue"] > 0:
            from app.mesajlar import M
            text = M("brifing.geciken-hatirlatma", n=stats["overdue"])
            logger.info("Gecikmiş görev bildirimi gönderiliyor: %d görev.", stats["overdue"])
            await _push_proactive(text, "gecikmis")
    except Exception as e:
        logger.warning("Gecikmiş görev bildirimi başarısız: %s", e)


# ------------------------------------------------------------------ #
# Lifecycle
# ------------------------------------------------------------------ #

def startup() -> None:
    """Scheduler'ı başlat ve sabit görevleri kaydet."""
    if not SCHEDULER_ENABLED:
        logger.info("Scheduler devre dışı (SCHEDULER_ENABLED=false).")
        return

    sched = get_scheduler()

    if not sched.get_job("morning_briefing"):
        sched.add_job(
            _do_morning_briefing,
            trigger="cron",
            hour=8, minute=0,
            id="morning_briefing",
        )
        logger.info("Sabah brifing görevi eklendi (08:00 %s).", SCHEDULER_TIMEZONE)

    # Sabah özeti telafisi — 08:00-12:00 arası açılış, 30 sn sonra (diğer servisler kalksın)
    _simdi = datetime.now()
    if 8 <= _simdi.hour < 12 and not sched.get_job("sabah_telafisi"):
        sched.add_job(_sabah_telafisi, trigger="date", run_date=_simdi + timedelta(seconds=30),
                      id="sabah_telafisi", misfire_grace_time=600)

    if not sched.get_job("memory_gc"):
        sched.add_job(
            _do_memory_gc,
            trigger="cron",
            hour=3, minute=0,
            id="memory_gc",
        )
        logger.info("Hafıza GC görevi eklendi (03:00 %s).", SCHEDULER_TIMEZONE)

    if not sched.get_job("overdue_reminder"):
        sched.add_job(
            _do_overdue_reminder,
            trigger="cron",
            hour=9, minute=0,
            id="overdue_reminder",
        )
        logger.info("Gecikmiş görev hatırlatıcısı eklendi (09:00 %s).", SCHEDULER_TIMEZONE)

    # Durable hatırlatıcıları geri yükle (restart-güvenlik)
    try:
        register_reminders()
    except Exception as e:  # noqa: BLE001
        logger.warning("Hatırlatıcılar yüklenemedi: %s", e)

    # Drive yedekleme ( FAZ 4) — ayar dosyasından okunur, restart-güvenli.
    try:
        yedekleme_isini_kur()
    except Exception as e:  # noqa: BLE001
        logger.warning("Yedekleme zamanlaması kurulamadı: %s", e)

    # Genişletme özellikleri (g4, 2026-11-12):
    # · Atölye öneri turu — yalnız ATOLYE açıkken (bayrak `.env`'den, değişince yeniden başlatma ister).
    # · Fitnes 21:00 hatırlatma + Pzt lig/özet — FITNES ayardan CANLI açılabildiği için işler hep
    #   kaydedilir, her iş koşarken bayrağa bakar (`fitnes_bildirim._is`); kapalıyken hiçbir şey yapmaz.
    from app import config as _cfg
    if getattr(_cfg, "ATOLYE", False) is True:
        try:
            from app.services import gorev_kuyrugu
            gorev_kuyrugu.zamanlayiciya_ekle(sched)
            logger.info("Atölye öneri turu eklendi (30 dk).")
        except Exception as e:  # noqa: BLE001
            logger.warning("Atölye öneri turu kurulamadı: %s", e)
    try:
        from app.services import fitnes_bildirim
        fitnes_bildirim.zamanlayiciya_ekle(sched)
    except Exception as e:  # noqa: BLE001
        logger.warning("Fitnes bildirim işleri kurulamadı: %s", e)

    sched.start()
    logger.info("Scheduler başlatıldı (%s).", SCHEDULER_TIMEZONE)


_YEDEKLEME_IS_ID = "drive_yedekleme"


def yedekleme_isini_kur() -> None:
    """Yedekleme işini ayara göre kur/kaldır. **İdempotent** — her çağrıda güvenli.

    🔑 Ayar değişince arayüz bunu çağırır; yoksa kullanıcı saati değiştirir,
    "kaydedildi" görür ve iş bir sonraki açılışa kadar eski saatte koşar —
    hiçbir yerde yazmayan bir sapma.

    ⚠️ İki kapı bilerek: saat kapatılınca iş kaldırılır (burası), tetiklenen tur
    ayrıca motorda `acik` bayrağını yeniden okur. Yarışla tetiklenen bir tur
    kullanıcının kapattığı özelliği çalıştırmasın.
    """
    if not SCHEDULER_ENABLED:
        return
    from app.services import yedekleme as _yed

    sched = get_scheduler()
    ayar = _yed.ayarlar()
    mevcut = sched.get_job(_YEDEKLEME_IS_ID)
    zaman = (ayar.get("zamanlama") or "").strip() if ayar.get("acik") else ""

    if not zaman:
        if mevcut:
            sched.remove_job(_YEDEKLEME_IS_ID)
            logger.info("Yedekleme zamanlaması kaldırıldı.")
        return

    sa, dk = zaman.split(":")
    if mevcut:
        sched.remove_job(_YEDEKLEME_IS_ID)
    # misfire: uyku/ağır yük yüzünden saat kaçtıysa 4 saate kadar geç de olsa koşsun
    # (yoksa o günün yedeği sessizce atlanırdı); birikenler tek tura çöker.
    sched.add_job(_yedekleme_turu, trigger="cron", hour=int(sa), minute=int(dk),
                  id=_YEDEKLEME_IS_ID, misfire_grace_time=4 * 3600, coalesce=True)
    logger.info("Yedekleme görevi kuruldu (%s %s).", zaman, SCHEDULER_TIMEZONE)


async def _yedekleme_turu() -> None:
    """Zamanlanmış tur. Hata YUTULMAZ, günlüğe yazılır — sessiz yedekleme yoktur."""
    from app.services import yedekleme as _yed

    if not _yed.ayarlar().get("acik"):
        return
    rapor = await _yed.tur_calistir("zamanlanmis")
    if rapor.get("hata"):
        logger.warning("Zamanlanmış yedekleme hatayla bitti: %s", rapor["hata"])
    else:
        logger.info("Zamanlanmış yedekleme: %d yeni, %d güncel, %d atlandı (%.1f sn).",
                    rapor["yuklenen"], rapor["guncellenen"], rapor["atlanan"],
                    rapor["saniye"])


def shutdown() -> None:
    """Scheduler'ı kapat."""
    global _scheduler
    if _scheduler and _scheduler.running:
        _scheduler.shutdown(wait=False)
        logger.info("Scheduler kapatıldı.")
