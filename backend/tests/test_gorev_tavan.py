"""Yuki Atölye — görev modunda döngü tavanları.

Kabul ölçüleri:
  ① "hiç bitirmeyen" sahte LLM → TAM tavanda `yarim` + son adım; araçsız
     son çağrı yok (bitmemiş işi "bitti" diye özetletmez)
  ② süre/token tavanı adım başında; usage yoksa token tahmin edilir
  ③ sohbet yolu değişmez (`gorev=None`): sohbet çağrısına görev parametresi sızmaz,
     araç kesintisi sabit
"""
import asyncio
import json
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest

from app.services import runner as r
from tests.atolye_yardimci import _arac_akisi, _icerik_akisi, _sahte_client, _sahte_router


def _usage_akisi(ic, prompt: int, completion: int):
    """Var olan sahte akışın sonuna `choices=[]` + usage parçası ekler."""
    async def _aiter():
        async for p in ic:
            yield p
        yield SimpleNamespace(choices=[], usage=SimpleNamespace(
            prompt_tokens=prompt, completion_tokens=completion, cached_tokens=0))
    m = MagicMock()
    m.__aiter__ = lambda self: _aiter()
    return m


def _bitmeyen(n: int, usage: tuple[int, int] | None = None):
    """Her adımda yine araç isteyen model — kendiliğinden hiç bitmez."""
    out = []
    for i in range(n):
        a = _arac_akisi([(f"c{i}", "list_tabs", {})])
        out.append(_usage_akisi(a, *usage) if usage else a)
    return out


async def _kos(runner: r.LLMRunner, client, router=None, arac=None):
    if router is None:
        router = _sahte_router(client)
        # MagicMock'un uydurma adı izinli listede yok → görev "ücretli" sanıp durur.
        arac = arac or AsyncMock(return_value="ok")
    with patch("app.services.llm_router.get_router", return_value=router), \
         patch("app.services.runner.call_tool", new=arac):
        metin = "".join([c async for c in runner.run([{"role": "user", "content": "site yap"}])])
    return metin, arac


# ══════════════════════════════════════════════════════════════════════════
#  ① Adım / süre / token tavanı
# ══════════════════════════════════════════════════════════════════════════

@pytest.mark.asyncio
async def test_hic_bitirmeyen_model_tam_adim_tavaninda_yarim():
    tavan = r.GorevTavanlari(adim=7)
    client = _sahte_client(_bitmeyen(7) + [_icerik_akisi("bunu çağırmamalı")])
    run = r.LLMRunner(client, "m", [{"type": "function"}], max_steps=99, gorev=tavan)
    metin, arac = await _kos(run, client)

    assert client.chat.completions.create.await_count == 7, "tam tavanda durmalı, fazlası yok"
    assert arac.await_count == 7
    assert run.sonuc.durum == "yarim" and run.sonuc.neden == "adim"
    assert run.sonuc.son_adim == 7
    assert run.sonuc.son_araclar == ["list_tabs"]
    assert metin == "", "tavanda araçsız 'bitti' özeti yazılmamalı"


@pytest.mark.asyncio
async def test_adim_tavani_max_steps_yerine_turden_gelir():
    """`max_steps=5` verilse de görevde tavan türün `adim`ıdır."""
    client = _sahte_client(_bitmeyen(12))
    run = r.LLMRunner(client, "m", [], max_steps=5, gorev=r.GorevTavanlari(adim=12))
    await _kos(run, client)
    assert client.chat.completions.create.await_count == 12
    assert run.sonuc.son_adim == 12


@pytest.mark.asyncio
async def test_model_kendisi_bitirirse_bitti():
    client = _sahte_client([_arac_akisi([("c1", "list_tabs", {})]), _icerik_akisi("Tamam bitti.")])
    run = r.LLMRunner(client, "m", [], gorev=r.GorevTavanlari(adim=10))
    metin, _ = await _kos(run, client)
    assert run.sonuc.durum == "bitti" and run.sonuc.neden is None
    assert run.sonuc.son_adim == 2
    assert "Tamam bitti." in metin


@pytest.mark.asyncio
async def test_sure_tavani_adim_basinda_keser():
    """Sahte saat: her adım 100 sn sürüyor gibi; tavan 250 sn → 3. adım koşar, 4. koşmaz."""
    saat = {"t": 0.0}

    def _sahte_saat():
        return saat["t"]

    async def _yavas_arac(ad, args):
        saat["t"] += 100.0
        return "ok"

    client = _sahte_client(_bitmeyen(20))
    run = r.LLMRunner(client, "m", [], gorev=r.GorevTavanlari(adim=20, sure_sn=250))
    with patch("app.services.runner._saat", _sahte_saat):
        await _kos(run, client, arac=AsyncMock(side_effect=_yavas_arac))
    assert client.chat.completions.create.await_count == 3
    assert run.sonuc.durum == "yarim" and run.sonuc.neden == "sure"
    assert run.sonuc.son_adim == 3
    assert run.sonuc.sure_sn == 300.0


@pytest.mark.asyncio
async def test_token_tavani_adim_basinda_keser():
    """Her adım 1000+200 token; tavan 3000 → 3 adım (3600 ≥ 3000), 4. koşmaz."""
    client = _sahte_client(_bitmeyen(20, usage=(1000, 200)))
    run = r.LLMRunner(client, "m", [], gorev=r.GorevTavanlari(adim=20, token=3000))
    await _kos(run, client)
    assert client.chat.completions.create.await_count == 3
    assert run.sonuc.durum == "yarim" and run.sonuc.neden == "token"
    assert run.sonuc.token == 3600
    assert run.sonuc.token_tahmini is False


@pytest.mark.asyncio
async def test_usage_gelmezse_token_tahmin_edilir_tavan_kor_kalmaz():
    """Sağlayıcı usage vermezse tavan sessizce kör kalmamalı — karakterden tahmin."""
    client = _sahte_client(_bitmeyen(50))
    run = r.LLMRunner(client, "m", [], gorev=r.GorevTavanlari(adim=50, token=200))
    await _kos(run, client)
    assert run.sonuc.neden == "token"
    assert run.sonuc.token_tahmini is True
    assert client.chat.completions.create.await_count < 50


@pytest.mark.asyncio
async def test_iptal_edilen_gorev_iptal_der():
    client = _sahte_client(_bitmeyen(10))
    run = r.LLMRunner(client, "m", [], gorev=r.GorevTavanlari(adim=10))

    async def _iptal_eden(ad, args):
        run.cancel_token.cancel()
        return "ok"

    await _kos(run, client, arac=AsyncMock(side_effect=_iptal_eden))
    assert run.sonuc.durum == "iptal"
    assert client.chat.completions.create.await_count == 1


# ══════════════════════════════════════════════════════════════════════════
#  R2 — araç zaman aşımı görevde türden gelir
# ══════════════════════════════════════════════════════════════════════════

async def _yavas(ad, args):
    await asyncio.sleep(0.3)
    return "yavaş ama geldi"


@pytest.mark.asyncio
async def test_gorevde_arac_zaman_asimi_turden_kisa():
    client = _sahte_client([_arac_akisi([("c1", "list_tabs", {})]), _icerik_akisi("son")])
    run = r.LLMRunner(client, "m", [], gorev=r.GorevTavanlari(adim=5, arac_zaman_asimi=0.05))
    await _kos(run, client, arac=AsyncMock(side_effect=_yavas))
    ikinci = client.chat.completions.create.await_args_list[1].kwargs["messages"]
    arac_sonucu = [m for m in ikinci if m.get("role") == "tool"][0]["content"]
    assert "0.05s içinde yanıt vermedi" in arac_sonucu


@pytest.mark.asyncio
async def test_gorevde_arac_zaman_asimi_sabit_10sn_degil():
    """TOOL_TIMEOUT kısaltılsa bile görev kendi değerini kullanır (sabite bağlı değil)."""
    client = _sahte_client([_arac_akisi([("c1", "list_tabs", {})]), _icerik_akisi("son")])
    run = r.LLMRunner(client, "m", [], gorev=r.GorevTavanlari(adim=5, arac_zaman_asimi=2.0))
    with patch("app.services.runner.TOOL_TIMEOUT", 0.05):
        await _kos(run, client, arac=AsyncMock(side_effect=_yavas))
    ikinci = client.chat.completions.create.await_args_list[1].kwargs["messages"]
    arac_sonucu = [m for m in ikinci if m.get("role") == "tool"][0]["content"]
    assert arac_sonucu == "yavaş ama geldi"


# ══════════════════════════════════════════════════════════════════════════
#  ③ Sohbet yolu aynen kalır
# ══════════════════════════════════════════════════════════════════════════

@pytest.mark.asyncio
async def test_sohbet_cagrisina_yeni_parametre_sizmaz():
    client = _sahte_client([_icerik_akisi("selam")])
    router = _sahte_router(client)
    run = r.LLMRunner(client, "m", [{"type": "function", "function": {"name": "x"}}])
    await _kos(run, client, router=router)
    kw = client.chat.completions.create.await_args.kwargs
    assert set(kw) == {"model", "messages", "tools", "tool_choice", "stream", "timeout"}
    assert run.sonuc is None and run.gorev is None


@pytest.mark.asyncio
async def test_sohbette_arac_zaman_asimi_hala_sabit():
    client = _sahte_client([_arac_akisi([("c1", "list_tabs", {})]), _icerik_akisi("son")])
    run = r.LLMRunner(client, "m", [])
    with patch("app.services.runner.TOOL_TIMEOUT", 0.05):
        await _kos(run, client, arac=AsyncMock(side_effect=_yavas))
    ikinci = client.chat.completions.create.await_args_list[1].kwargs["messages"]
    arac_sonucu = [m for m in ikinci if m.get("role") == "tool"][0]["content"]
    assert "0.05s içinde yanıt vermedi" in arac_sonucu


def test_sohbet_turu_gorev_vermez():
    """`llm.py` sohbet turu `gorev` vermeden kurar — görev modu yalnız görev servisinden açılır."""
    import inspect
    from app.services import llm
    assert "gorev=" not in inspect.getsource(llm.chat_stream)


def test_varsayilan_tavanlar_plandaki_baslangic():
    t = r.GorevTavanlari()
    assert (t.adim, t.sure_sn) == (60, 1800)
    assert t.arac_zaman_asimi > r.TOOL_TIMEOUT
