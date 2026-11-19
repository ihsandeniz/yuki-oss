"""Notlar ve rutinler — bozuk dosya sessizce EZİLMESİN (2026-11-10 gizli hata turu).

İki depo da yazmayı atomik yapmıyordu (yarıda kesilen yazım = yarım JSON) ve okuma
hatasında boş liste dönüyordu; sonraki not/rutin ekleme dosyayı tek kayıtla yeniden
yazıp öncekilerin HEPSİNİ yedeksiz siliyordu.
"""
import importlib
import json

import pytest

YARIM = '[{"id": "a1", "title": "banka şifre ipucu", "content": "x", "created_at": "01.01.2026 10:00"}, {"id": "b'


@pytest.fixture
def notlar(tmp_path, monkeypatch):
    from app.services.tools import notes_tools as n
    monkeypatch.setattr(n, "_NOTES_FILE", tmp_path / "notes.json")
    return n, tmp_path / "notes.json"


@pytest.fixture
def rutinler(tmp_path, monkeypatch):
    from app.services import routines as r
    monkeypatch.setattr(r, "_PATH", tmp_path / "data" / "routines.json")
    monkeypatch.setattr(r, "_schedule_one", lambda routine: True)
    return r, tmp_path / "data" / "routines.json"


def test_bozuk_notlar_ezilmeden_once_yedeklenir(notlar):
    n, yol = notlar
    yol.write_text(YARIM)
    n.create_note("yeni not")
    yedek = list(yol.parent.glob("notes.json.bozuk*"))
    assert yedek and yedek[0].read_text() == YARIM, "bozuk notlar yedeksiz ezildi"


def test_bozuk_rutinler_ezilmeden_once_yedeklenir(rutinler):
    r, yol = rutinler
    yol.parent.mkdir(parents=True)
    yol.write_text('[{"id": "r1", "name": "sabah"')
    r.create_routine("akşam", "21:00", "message", "merhaba")
    assert list(yol.parent.glob("routines.json.bozuk*")), "bozuk rutinler yedeksiz ezildi"


def test_not_yazimi_ATOMIK_yarida_kalan_yazim_eskiyi_bozmaz(notlar, monkeypatch):
    n, yol = notlar
    n.create_note("ilk")
    onceki = yol.read_text()
    import os
    gercek = os.replace

    def patla(*a, **k):
        raise OSError("disk dolu")
    monkeypatch.setattr(os, "replace", patla)
    with pytest.raises(OSError):
        n.create_note("ikinci")
    monkeypatch.setattr(os, "replace", gercek)
    assert yol.read_text() == onceki, "yazım yarıda kalınca notes.json bozuldu (atomik değil)"


def test_saglam_depoda_yedek_yok_ve_veri_korunur(notlar, rutinler):
    n, nyol = notlar
    n.create_note("a")
    n.create_note("b")
    assert len(json.loads(nyol.read_text())) == 2
    r, ryol = rutinler
    r.create_routine("x", "07:00", "message", "m")
    assert not list(nyol.parent.glob("*.bozuk*")) and not list(ryol.parent.glob("*.bozuk*"))


def test_bozuk_hatirlaticilar_ezilmeden_once_yedeklenir(tmp_path, monkeypatch):
    from app.services import scheduler as s
    yol = tmp_path / "reminders.json"
    monkeypatch.setattr(s, "_REMINDERS_PATH", yol)

    class _Sahte:
        def add_job(self, *a, **k):
            pass
    monkeypatch.setattr(s, "get_scheduler", lambda: _Sahte())
    yol.write_text('[{"id": "reminder_1", "kind": "once", "message": "ilaç"')
    from datetime import datetime, timedelta
    s.add_reminder("su iç", datetime.now() + timedelta(hours=1))
    assert list(tmp_path.glob("reminders.json.bozuk*")), "bozuk hatırlatıcılar yedeksiz ezildi"


@pytest.mark.parametrize("ifade", ["her 0 dk", "every 0m", "her 00 saat", "every 0d"])
def test_sifir_aralikli_rutin_REDDEDILIR_her_saniye_kosmaz(rutinler, ifade):
    r, yol = rutinler
    assert r._parse_schedule(ifade) is None
    assert r.create_routine("spam", ifade, "team", "özetle").startswith("Hata")
    assert not yol.exists()


def test_gecerli_aralik_yine_kabul_edilir(rutinler):
    r, _ = rutinler
    assert r._parse_schedule("her 1 dk") == ("interval", {"minutes": 1})
