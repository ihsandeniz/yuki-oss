"""Araç şeması alan seçici: kazanç gerçek mi, yetenek kaybı var mı?

    cd backend && venv/bin/python -m pytest tests/test_alan_secici.py -q

Testlerin çoğu "ne zaman DARALTMAMALI" sorusunu kapatır: daraltmanın kazancını
ölçmek kolay, **sessiz yeteneksizliği** ölçmek zordur — yanlış eşleşmede model
"yapamıyorum" der, hata düşmez.
"""

import json
from pathlib import Path

import pytest

from app.services.tools import alan_secici
from app.services.tools.alan_secici import (
    ALANLAR, _ALTYAPI, alan_ac, alanlari_esle, denetle, sema_sec, _aktif_sema,
)
from app.services.tools.dispatcher import TOOLS

# CI'da `data/used_tools.json` yok (`backend/data/*` git dışı) → daraltma hiç olmaz
# ve testler "daraltma bozuldu" gibi düşer. Gerçek veri yoksa temsili listeye düşülür.
_CI_FIXTURE = Path(__file__).parent / "fixtures" / "used_tools.ci.json"


@pytest.fixture(autouse=True)
def _cekirdek_verisi(tmp_path, monkeypatch):
    """Gerçek `used_tools.json` varsa ONA dokunma; yoksa fixture'a düş.

    Veri yoksa testler sessizce anlamsızlaşacağına temsili çekirdekle davranışı ölçer.
    """
    if (alan_secici._VERI / "used_tools.json").exists():
        return
    hedef = tmp_path / "used_tools.json"
    hedef.write_text(_CI_FIXTURE.read_text(encoding="utf-8"), encoding="utf-8")
    monkeypatch.setattr(alan_secici, "_VERI", tmp_path)


def _ad(t):
    return (t.get("function") or {}).get("name") or t.get("name") or ""


def _alan_disi(alan):
    """Alanın çekirdekte OLMAYAN araçları — daraltmayı ölçmek için bunlar gerekir."""
    import re
    from app.services.tools.alan_secici import _kullanilmis_adlar
    k = re.compile(ALANLAR[alan]["arac"], re.IGNORECASE)
    return {_ad(t) for t in TOOLS if k.search(_ad(t))} - _kullanilmis_adlar() - _ALTYAPI


def _tok(liste):
    return len(json.dumps(liste, ensure_ascii=False)) / 3.6


# ── Kazanç ─────────────────────────────────────────────────────────────────
def test_sema_gercekten_daraliyor():
    """Alakasız bir cümlede şema tam şemanın en çok %70'i olmalı."""
    s = sema_sec("bugün nasılsın", TOOLS)
    assert _tok(s) < 0.7 * _tok(TOOLS), f"şema {_tok(s):.0f}/{_tok(TOOLS):.0f} token — daraltma çalışmıyor"
    assert len(s) < len(TOOLS)


def test_ilgili_alan_aciliyor():
    """Cümle bir alana işaret ediyorsa o alanın araçları şemaya girmeli."""
    kripto = _alan_disi("kripto")
    assert kripto, "fixture çekirdeği kripto araçlarının hepsini içeriyor — test bir şey ölçmez"
    acik = {_ad(t) for t in sema_sec("portföyüm ne durumda, bitcoin kaç", TOOLS)}
    assert kripto <= acik, "kripto alanı açılmadı"
    # Kontrol grubu: alakasız cümlede aynı araçlar GİRMEMELİ, yoksa test
    # daraltmayı değil yalnız varlığı ölçmüş olur.
    duz = {_ad(t) for t in sema_sec("bugün nasılsın", TOOLS)}
    assert not (kripto & duz), "kripto alanı alakasız cümlede de açıldı"


# ── Yetenek kaybı olmamalı ─────────────────────────────────────────────────
def test_calismis_araclar_HER_turda_semada():
    """🔴 En kritik test: bir kez bile çalışmış araç hiçbir turda düşmemeli.

    Düşerse ölçülmüş bir davranış bozulur ve ancak model 'yapamıyorum'
    dediğinde fark edilir.
    """
    from app.services.tools.alan_secici import _kullanilmis_adlar
    kullanilmis = _kullanilmis_adlar() & {_ad(t) for t in TOOLS}
    assert kullanilmis, "used_tools.json boş — bu test hiçbir şey ölçmez"
    for mesaj in ["merhaba", "x", "bugün hava nasıl", "teşekkürler", ""]:
        semada = {_ad(t) for t in sema_sec(mesaj, TOOLS)}
        eksik = kullanilmis - semada
        assert not eksik, f"{mesaj!r} turunda çalışmış araçlar düştü: {sorted(eksik)[:5]}"


def test_altyapi_araclari_her_turda():
    for mesaj in ["merhaba", "kripto", ""]:
        semada = {_ad(t) for t in sema_sec(mesaj, TOOLS)}
        assert _ALTYAPI <= semada | {"arac_alani_ac"}, f"{mesaj!r}: altyapı eksik"


def test_her_arac_ya_cekirdekte_ya_bir_alanda():
    """Hiçbir alana düşmeyen araç, mekanizma açıkken HİÇBİR turda görünmez."""
    # Çekirdek BOŞ varsayılır: fixture'daki kullanılmış araçlar yetimleri gizlemesin.
    from unittest.mock import patch
    with patch.object(alan_secici, "_kullanilmis_adlar", lambda: set()):
        d = denetle(TOOLS)
    assert not d["alansiz_ve_cekirdek_disi"], (
        "şu araçlar hiçbir turda görünmez: " + ", ".join(d["alansiz_ve_cekirdek_disi"]))


# ── Korkuluklar ────────────────────────────────────────────────────────────
def test_kapatma_anahtari_tam_semayi_geri_veriyor(monkeypatch):
    """Geri alma tek satır olmalı: YUKI_TAM_SEMA=1."""
    monkeypatch.setenv("YUKI_TAM_SEMA", "1")
    assert len(sema_sec("bugün nasılsın", TOOLS)) == len(TOOLS)


def test_olcum_verisi_yoksa_daraltma_YAPILMAZ(monkeypatch):
    """Çekirdek ölçümden gelir; ölçüm yoksa daraltmak körlemesine budamaktır."""
    monkeypatch.setattr("app.services.tools.alan_secici._kullanilmis_adlar", lambda: set())
    assert len(sema_sec("bugün nasılsın", TOOLS)) == len(TOOLS)


def test_global_TOOLS_degismiyor():
    """Araç doğrulaması ve /api/tool-call tam listeyi görmeye devam etmeli."""
    once = len(TOOLS)
    imza = [_ad(t) for t in TOOLS]
    sema_sec("takvimime bak", TOOLS)
    assert len(TOOLS) == once and [_ad(t) for t in TOOLS] == imza


# ── Yedek yol: aynı turun içinde alan açma ─────────────────────────────────
def test_alan_ac_semayi_YERINDE_genisletiyor():
    """Yerinde olmalı — LLMRunner liste referansını __init__'te saklıyor.

    Yeni liste atansaydı genişleme runner'a hiç ulaşmaz, model 'alanı açtım'
    der ama aracı yine göremezdi (sessiz başarısızlığın tam tarifi).
    """
    sema = sema_sec("merhaba", TOOLS)
    obj_id = id(sema)
    once = len(sema)
    eklenen = alan_ac("kripto", TOOLS)
    assert eklenen > 0, "kripto araçları eklenmedi"
    assert id(sema) == obj_id, "liste objesi DEĞİŞTİ — runner genişlemeyi görmez"
    assert len(sema) == once + eklenen
    assert _alan_disi("kripto") <= {_ad(t) for t in sema}


def test_bilinmeyen_alan_sessizce_gecmiyor():
    sema_sec("merhaba", TOOLS)
    assert alan_ac("boyle-bir-alan-yok", TOOLS) == 0


def test_alan_ac_aktif_sema_yokken_patlamiyor():
    _aktif_sema.set(None)
    assert alan_ac("kripto", TOOLS) == 0


# ── Alan tablosunun kendisi ────────────────────────────────────────────────
@pytest.mark.parametrize("alan,ornek", [
    ("takvim", "yarın takvimimde ne var"),
    ("dosya", "şu dosyayı oku"),
    ("kripto", "portföyüm ne durumda"),
    ("wiki", "wiki'ye yaz"),
    ("medya", "şarkıyı duraklat"),
    ("harita", "haritada depremleri göster"),
    ("sistem", "ram ne kadar dolu"),
    ("git", "son commit ne"),
    ("uygulama", "firefox'u aç"),
])
def test_mesaj_kaliplari_gercek_cumleleri_yakaliyor(alan, ornek):
    assert alan in alanlari_esle(ornek), f"{ornek!r} → {alan} alanını yakalamadı"


def test_alan_kaliplari_gecerli_regex():
    import re
    for ad, k in ALANLAR.items():
        re.compile(k["arac"])
        re.compile(k["mesaj"])


# ── Runner istisnası: alan açıldıktan sonra döngü sürmeli ──────────────────
def test_runner_alan_acildiginda_finale_KACMIYOR():
    """`arac_alani_ac` iş yapmaz, yalnız şemayı genişletir. Runner araç sonrası
    doğrudan `_stream_final`e geçerse model genişlemiş listeyi hiç görmez ve
    işi yapmadan "yaptım" der. Ölçü yapıdır (metin araması yorum satırında
    kalan adı da sayar): koşulunda `arac_alani_ac` geçen bir `if` düğümünün
    gövdesinde `continue` bulunmalı.
    """
    import ast
    import inspect
    import textwrap
    from app.services.runner import LLMRunner

    # Döngü `_dongu`da; `run` onu sarıp görev sonucunu kapatır (Atölye görev modu).
    agac = ast.parse(textwrap.dedent(inspect.getsource(LLMRunner._dongu)))
    bulundu = False
    for dugum in ast.walk(agac):
        if not isinstance(dugum, ast.If) or "arac_alani_ac" not in ast.dump(dugum.test):
            continue
        govde = ast.Module(body=dugum.body, type_ignores=[])
        if any(isinstance(x, ast.Continue) for x in ast.walk(govde)):
            bulundu = True
            break
    assert bulundu, (
        "runner'da `arac_alani_ac` koşullu `continue` yok — alan açıldıktan sonra "
        "final cevaba kaçılır, model genişleyen şemayı göremez ve işi yapmadan "
        "'yaptım' der")
