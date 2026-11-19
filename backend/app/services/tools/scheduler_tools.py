"""Hatırlatıcı/alarm araçları: kurma (tek-seferlik + tekrarlı), listeleme, iptal."""


def set_reminder(message: str, when: str, repeat: bool = False) -> str:
    """Alarm/hatırlatıcı kurar.

    İki tür:
      - Tek seferlik: when='30 dakika sonra' / '14:30' → bir kez çalar, biter.
      - Tekrarlı:    repeat=True ya da when='her 20 dakika' → iptal edilene kadar çalar.
    """
    try:
        from app.services.scheduler import (
            parse_when, parse_recurring, add_reminder, add_recurring_reminder,
        )

        # Tekrarlı mı? — when içinde 'her/every/…da bir' varsa ya da repeat=True ise
        rec = parse_recurring(when)
        if repeat and rec is None:
            # Kullanıcı tekrar istedi ama 'her' demediyse: when'i aralık say ('20 dakika' → 'her 20 dakika')
            rec = parse_recurring("her " + when)

        if rec is not None:
            kwargs, human = rec
            job_id = add_recurring_reminder(message, kwargs, human)
            return (
                f"Tekrarlı alarm kuruldu 🔁 {human} bir — {message} (id: {job_id}). "
                "Durdurmak için 'alarmı kapat' de."
            )

        run_date = parse_when(when)
        if run_date is None:
            return (
                f"Hata: '{when}' zaman ifadesi anlaşılamadı. "
                "Örnek: '30 dakika sonra', '14:30', 'her 20 dakika'."
            )
        job_id = add_reminder(message, run_date)
        return f"Alarm kuruldu ⏰ {run_date.strftime('%d.%m.%Y %H:%M')} — {message} (id: {job_id})"
    except Exception as e:
        return f"Hata: Alarm kurulamadı. {e}"


def _list_reminders() -> str:
    """Aktif hatırlatıcıları listeler (tek-seferlik + tekrarlı)."""
    try:
        from app.services.scheduler import list_reminders
        jobs = list_reminders()
        if not jobs:
            return "Aktif alarm/hatırlatıcı yok."
        lines = []
        for j in jobs:
            if j.get("kind") == "repeat":
                nxt = f" (sonraki: {j['next_run']})" if j.get("next_run") else ""
                lines.append(f"• [{j['id']}] 🔁 {j.get('human', 'tekrarlı')} bir — {j['message']}{nxt}")
            else:
                lines.append(f"• [{j['id']}] ⏰ {j.get('next_run')} — {j['message']}")
        return "\n".join(lines)
    except Exception as e:
        return f"Hata: Alarm listesi alınamadı. {e}"


def _cancel_reminder(job_id: str) -> str:
    """Bir hatırlatıcıyı iptal eder. 'all'/'hepsi' → tümünü iptal eder."""
    try:
        if job_id and job_id.strip().lower() in ("all", "hepsi", "tümü", "tumu", "*"):
            from app.services.scheduler import cancel_all_reminders
            n = cancel_all_reminders()
            return f"{n} alarm/hatırlatıcı iptal edildi." if n else "İptal edilecek alarm yok."
        from app.services.scheduler import cancel_reminder
        success = cancel_reminder(job_id)
        if success:
            return f"Alarm iptal edildi: {job_id}"
        return f"Hata: '{job_id}' bulunamadı veya zaten bitmiş."
    except Exception as e:
        return f"Hata: Alarm iptal edilemedi. {e}"
