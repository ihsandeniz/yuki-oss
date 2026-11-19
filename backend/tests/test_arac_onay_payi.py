"""Onay bekleyen araç, araç süresi dolduğu için düşmez.

Onay beklemesi `call_tool` İÇİNDE (approval_gate 30 sn), runner ise her aracı TOOL_TIMEOUT
(10 sn) ile kesiyordu: insan 10 sn içinde onaylamazsa araç "yanıt vermedi" diye düşüyor,
onay kartı ekranda asılı kalıyordu. Anthropic yolunda süre sabit 10 sn'ydi — uzun araçlar
(run_team 180 sn) da 10 sn'de kesiliyordu. Kişisel Yuki'deki "onay payı" düzeltmesinin
yeniden yazımı: süre tek yerden (`runner.arac_suresi`), onaya tabi araçta + onay penceresi.
"""
import asyncio
import inspect
import json
from types import SimpleNamespace

from app.services import llm, runner
from app.services.tools import approval_gate as ag


def _tc(ad):
    return SimpleNamespace(id="t1", function=SimpleNamespace(name=ad, arguments=json.dumps({})))


def _kos(ad, monkeypatch, gecikme):
    monkeypatch.setattr(runner, "TOOL_TIMEOUT", 0.1)
    monkeypatch.setattr(ag, "APPROVAL_TIMEOUT_SECONDS", 1)

    async def _arac(name, args):
        await asyncio.sleep(gecikme)        # insan onayı bu sürede gelir
        return "tamam"

    class _Bus:
        async def publish(self, *a, **k):
            pass
    oz = SimpleNamespace(cancel_token=runner.CancellationToken(), gorev=None, total_tool_calls=0,
                         arac_kayitlari=[])   # f1-cevap: runner araç kaydı tutar
    return asyncio.run(runner.LLMRunner._execute_tools(oz, [_tc(ad)], _arac, _Bus()))


def test_onaya_tabi_arac_onay_suresince_bekler(monkeypatch):
    monkeypatch.setattr("app.config.TOOL_APPROVAL_ENABLED", True)
    assert _kos("write_file", monkeypatch, 0.3)[0][2] == "tamam"


def test_her_zaman_onayli_arac_ayar_kapaliyken_de_bekler(monkeypatch):
    monkeypatch.setattr("app.config.TOOL_APPROVAL_ENABLED", False)
    ad = next(iter(ag.ALWAYS_APPROVE))
    assert _kos(ad, monkeypatch, 0.3)[0][2] == "tamam"


def test_onaysiz_arac_eski_surede_kesilir(monkeypatch):
    monkeypatch.setattr("app.config.TOOL_APPROVAL_ENABLED", True)
    assert "yanıt vermedi" in _kos("get_time", monkeypatch, 0.3)[0][2]


def test_onay_payi_degerleri(monkeypatch):
    monkeypatch.setattr("app.config.TOOL_APPROVAL_ENABLED", False)
    assert ag.onay_payi("write_file") == 0.0
    monkeypatch.setattr("app.config.TOOL_APPROVAL_ENABLED", True)
    assert ag.onay_payi("write_file") == float(ag.APPROVAL_TIMEOUT_SECONDS)
    assert ag.onay_payi("get_time") == 0.0
    assert runner.arac_suresi("run_team") >= runner.LONG_TOOL_TIMEOUT


def test_anthropic_yolu_ayni_sureyi_kullanir():
    # f1-cevap Anthropic adım döngüsünü _anthropic_adimlari'na ayırdı; ikisi birlikte sınanır
    kaynak = inspect.getsource(llm._stream_anthropic) + inspect.getsource(llm._anthropic_adimlari)
    assert "arac_suresi(" in kaynak and "timeout=10.0" not in kaynak
