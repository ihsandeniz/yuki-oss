"""Zamanlayıcının saat dilimi makineninkiyle aynı olmalı.

`parse_when` / hatırlatıcılar / Atölye açılış turu naif yerel tarih üretir; APScheduler naif
tarihi kendi saat diliminde okur. Varsayılan sabit "Europe/Istanbul" iken UTC makinede
"10 dakika sonra" alarmı 3 saat GEÇMİŞE kuruluyordu.
Ad bulunamayan makinede (minimal kap, `/etc/localtime` yok) yedek de yerel farkla aynı olmalı;
sabit bir ülke varsayılanı aynı kaymayı geri getirir.
"""
import importlib
import os
import subprocess
import sys
import textwrap
from pathlib import Path

import pytest

BACKEND = Path(__file__).resolve().parents[1]


def _kos(tz: str, ek_ortam: dict | None = None, tzlocal_ad: str | None = "") -> str:
    """Ayrı süreçte (TZ süreç başında okunur) zamanlayıcıya 10 dk sonraki alarmı kur,
    gerçek çalışma anıyla istenen an arasındaki farkı dakika olarak döndür."""
    # tzlocal_ad: "" → gerçek tzlocal · None → tzlocal ad bulamaz (patlar) · "X" → tzlocal "X" der
    sahte = "" if tzlocal_ad == "" else textwrap.dedent(f"""
        import tzlocal
        def _sahte():
            if {tzlocal_ad!r} is None:
                raise RuntimeError("saat dilimi adı yok")
            return {tzlocal_ad!r}
        tzlocal.get_localzone_name = _sahte
    """)
    kod = sahte + textwrap.dedent("""
        from datetime import datetime, timedelta
        from apscheduler.schedulers.background import BackgroundScheduler
        from app import config
        s = BackgroundScheduler(timezone=config.SCHEDULER_TIMEZONE)
        istenen = datetime.now() + timedelta(minutes=10)
        j = s.add_job(print, trigger="date", run_date=istenen)
        s.start(paused=True)
        j = s.get_job(j.id)
        print(config.SCHEDULER_TIMEZONE, round((j.next_run_time - istenen.astimezone()).total_seconds() / 60))
    """)
    ortam = {k: v for k, v in os.environ.items() if k != "SCHEDULER_TIMEZONE"}
    ortam.update({"TZ": tz, "PYTHONPATH": str(BACKEND)})
    ortam.update(ek_ortam or {})
    r = subprocess.run([sys.executable, "-c", kod], cwd=BACKEND, env=ortam,
                       capture_output=True, text=True, timeout=120)
    assert r.returncode == 0, r.stderr[-2000:]
    return r.stdout.strip().splitlines()[-1]


@pytest.mark.parametrize("tz", ["UTC", "America/New_York", "Asia/Tokyo", "Europe/Istanbul"])
def test_alarm_makinenin_saatinde_calisir(tz):
    ad, fark = _kos(tz).split()
    assert ad == tz
    assert fark == "0", f"{tz}: alarm {fark} dk kaydı"


def test_ortam_degiskeni_hala_oncelikli(monkeypatch):
    ad, _ = _kos("UTC", {"SCHEDULER_TIMEZONE": "Asia/Tokyo"}).split()
    assert ad == "Asia/Tokyo"


@pytest.mark.parametrize("tz,beklenen", [
    ("UTC", "UTC"),                 # /etc/localtime'sız minimal kap: yerel saat UTC
    ("Asia/Tokyo", "Etc/GMT-9"),
    ("America/New_York", None),     # yaz/kış farkı değişir → yalnız kayma ölçülür
    ("<+03>-3", "Etc/GMT-3"),       # IANA adı olmayan POSIX TZ
])
def test_ad_bulunamazsa_yerel_farka_duser(tz, beklenen):
    """Ad bulunamayınca sabit bir ülkeye (eskiden Europe/Istanbul) DÜŞMEZ: yerel fark kullanılır,
    alarm kaymaz."""
    ad, fark = _kos(tz, tzlocal_ad=None).split()
    if beklenen:
        assert ad == beklenen
    assert ad != "Europe/Istanbul"
    assert fark == "0", f"{tz}: ad bulunamayınca alarm {fark} dk kaydı ({ad})"


def test_tzlocal_gecersiz_ad_verirse_kullanilmaz():
    """Geçersiz IANA adı zamanlayıcıyı açılışta düşürmesin; yerel farka inilsin."""
    ad, fark = _kos("Asia/Tokyo", tzlocal_ad="Bogus/Zone").split()
    assert ad == "Etc/GMT-9" and fark == "0"


def test_tzlocal_yerel_saatle_celisirse_kullanilmaz():
    """tzlocal bir ad verse de (ör. POSIX TZ'de "Etc/UTC") yerel fark tutmuyorsa alarm kayar;
    ad yerine farktan türetilen ad seçilmeli."""
    ad, fark = _kos("<+03>-3", tzlocal_ad="Etc/UTC").split()
    assert ad == "Etc/GMT-3" and fark == "0"


def test_ofsetten_ad_isaret_ters():
    from datetime import timedelta
    from app import config
    assert config._ofsetten_saat_dilimi(timedelta(0)) == "UTC"
    assert config._ofsetten_saat_dilimi(timedelta(hours=3)) == "Etc/GMT-3"
    assert config._ofsetten_saat_dilimi(timedelta(hours=-5)) == "Etc/GMT+5"
    assert config._ofsetten_saat_dilimi(timedelta(hours=5, minutes=30)) == "UTC"
    assert config._ofsetten_saat_dilimi(None) == "UTC"
