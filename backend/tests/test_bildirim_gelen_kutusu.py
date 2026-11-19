"""BİLDİRİM · GELEN KUTUSU — Yuki'nin kendiliğinden söyledikleri + kanal izi (2026-09-27).

Eski oda yalnız telefona GİDEN push'ları listeliyordu (`push_notifications`); ekrana
ulaşıp ulaşmadığını, sesin çalıp çalmadığını bilmiyordu. Kullanıcının asıl sorusu
"Yuki bana bir şey söyledi mi, kaçırdım mı?" idi. Yeni günlük `yuki_dedi` tablosu:
her proaktif mesaj + her kanalın sonucu. İkisi de 0 → KAÇIRDIN.

Ölçülen üç arıza bu dosyada bekçiye bağlı:
  ① `_push_proactive` pencere yokken (`_cm` None) ERKEN DÖNÜYORDU → telefon bildirimi de
     gitmiyordu; açık pencere olmaması tam da telefonun gerektiği an.
  ② `parse_recurring("her gün 20:00")` saati YOK SAYIP "her 1 gün"e çeviriyordu →
     alarm kurulduğu andan itibaren 24 saatte bir çalıyordu, 20:00'de değil.
  ③ Proaktif mesaj ekranda HİÇBİR YERE basılmıyordu (core.js'te karşılayıcı yoktu) —
     yalnız ses geliyordu.
"""
from __future__ import annotations

import time
from pathlib import Path

import pytest

from app.api import push
from app.services import scheduler

KOK = Path(__file__).resolve().parents[2]


@pytest.fixture
async def db(tmp_path, monkeypatch):
    monkeypatch.setattr(push, "_DB_PATH", tmp_path / "push.db")
    await push.init_push_db()
    return tmp_path / "push.db"


async def _oku(**kw):
    # limiter dekoratörü `request` ister; gövdeyi doğrudan çağır
    return await push.get_yuki_dedi.__wrapped__(None, **kw)


async def test_kayit_yeniden_eskiye_ve_kacan_sayaci(db):
    await push.yuki_dedi_kaydet("alarm", "çamaşır", ekran=1, telefon=0, ses=1)
    await push.yuki_dedi_kaydet("sabah", "günaydın", ekran=0, telefon=0, ses=0)   # kaçtı
    await push.yuki_dedi_kaydet("rutin", "su iç", ekran=0, telefon=2, ses=0)     # telefona ulaştı
    d = await _oku(limit=50)
    assert [k["kaynak"] for k in d["kayitlar"]] == ["rutin", "sabah", "alarm"]
    assert d["kacan_7g"] == 1
    assert set(d["kayitlar"][0]) >= {"id", "ts", "kaynak", "metin", "ekran", "telefon", "ses"}


async def test_sayfalama_once_ile(db):
    for i in range(5):
        await push.yuki_dedi_kaydet("alarm", f"m{i}", 1, 0, 0)
    ilk = (await _oku(limit=2))["kayitlar"]
    sonraki = (await _oku(limit=2, once=ilk[-1]["id"]))["kayitlar"]
    assert [k["metin"] for k in ilk + sonraki] == ["m4", "m3", "m2", "m1"]


async def test_bugun_var_mi_yalniz_bugunu_sayar(db):
    import aiosqlite
    async with aiosqlite.connect(db) as c:
        await c.execute("INSERT INTO yuki_dedi (ts, kaynak, metin) VALUES (?, 'sabah', 'dün')",
                        (time.time() - 2 * 86400,))
        await c.commit()
    assert not await push.yuki_dedi_bugun_var_mi("sabah")
    await push.yuki_dedi_kaydet("sabah", "bugün", 1, 0, 0)
    assert await push.yuki_dedi_bugun_var_mi("sabah")
    assert not await push.yuki_dedi_bugun_var_mi("alarm")


async def test_pencere_yokken_telefona_yine_gider_ve_KACAN_olarak_yazilir(db, monkeypatch):
    """① `_cm` None iken erken dönüş → push gitmiyordu. Şimdi gider, iz düşer."""
    giden = []

    async def sahte_push(baslik, govde, url="/"):
        giden.append(govde)
        return 0          # abone cihaz yok

    monkeypatch.setattr(push, "send_push_to_all", sahte_push)
    monkeypatch.setattr(scheduler, "_cm", None)
    await scheduler._push_proactive("ilaç saati", "alarm")
    assert giden == ["ilaç saati"], "pencere yokken telefona gitmedi"
    k = (await _oku(limit=5))["kayitlar"][0]
    assert (k["kaynak"], k["ekran"], k["telefon"], k["ses"]) == ("alarm", 0, 0, 0)
    assert (await _oku(limit=5))["kacan_7g"] == 1


async def test_sistem_mesaji_telefona_gitmez(db, monkeypatch):
    """dbus_watcher (USB takıldı vb.) yalnız ekrana — telefonu masaüstü olayıyla doldurma."""
    giden = []

    async def sahte_push(*a, **kw):
        giden.append(a)
        return 1

    class Cm:
        async def broadcast(self, veri):
            return 1 if veri.get("type") == "proactive_message" else 0

    monkeypatch.setattr(push, "send_push_to_all", sahte_push)
    monkeypatch.setattr(scheduler, "_cm", Cm())
    await scheduler._push_proactive("USB takıldı", "sistem", telefona=False)
    assert giden == []
    k = (await _oku(limit=5))["kayitlar"][0]
    assert (k["kaynak"], k["ekran"], k["telefon"]) == ("sistem", 1, 0)


@pytest.mark.parametrize("ifade", ["her gün 20:00", "her gun 8.30", "every day 07:15"])
def test_saatli_tekrar_REDDEDILIR_sessizce_araliga_donmez(ifade):
    """② Saat yok sayılıp 24 saatlik aralığa çevrilirse alarm yanlış saatte çalar."""
    assert scheduler.parse_recurring(ifade) is None


@pytest.mark.parametrize("ifade,beklenen", [
    ("her 2 saat", {"hours": 2}), ("20 dakikada bir", {"minutes": 20}),
    ("every 20m", {"minutes": 20}), ("her gün", {"days": 1}), ("her 3 day", {"days": 3}),
])
def test_aralikli_tekrar_bozulmadi(ifade, beklenen):
    assert scheduler.parse_recurring(ifade)[0] == beklenen


def test_proaktif_mesaj_EKRANDA_karsilaniyor():
    """③ core.js'te `proactive_message` karşılayıcısı yoktu — mesaj ekrana hiç basılmıyordu."""
    core = (KOK / "frontend" / "js" / "core.js").read_text(encoding="utf-8")
    i = core.index("d.type === 'proactive_message'")
    govde = core[i:i + 400]
    assert "addMessage('yuki', d.text)" in govde, "sohbete balon basılmıyor"
    assert "yuki:proaktif" in govde, "BİLDİRİM odası haberdar edilmiyor"


def test_eski_duzenle_sil_uclari_KALKTI():
    """Günlüğü düzenlemek onu yalancı yapar; elle bildirim formu da söküldü."""
    yollar = {getattr(r, "path", "") for r in push.router.routes}
    for olu in ("/api/push/send", "/api/push/history", "/api/push/notifications",
                "/api/push/notifications/{notif_id}"):
        assert olu not in yollar, f"{olu} hâlâ kayıtlı"
    assert "/api/push/yuki-dedi" in yollar


def test_panel_confirm_KULLANMIYOR():
    """Üründe confirm()/prompt() yasak — alarm iptali iki adımlı."""
    kod = (KOK / "frontend" / "js" / "intro-sequences.js").read_text(encoding="utf-8")
    bolge = kod[kod.index("BİLDİRİM odası — ortak yardımcılar"):]
    assert "confirm(" not in bolge and "prompt(" not in bolge
    assert "classList.add('kurulu')" in bolge, "iki adımlı iptal yok"
