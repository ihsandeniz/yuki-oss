"""Anthropic yolu — sessiz para ve veri kusurları (2026-11-10 gizli hata turu).

① Araçsız her cevap İKİ kez üretiliyordu: önce `messages.create` (tam cevap, ücretli),
   sonra aynı mesajlarla `messages.stream` (yine tam cevap, yine ücretli). İlk cevap atılıyordu.
③ Akış korunmalı: cevap parça parça gelmeli (çift üretimi kapatırken akış kaybolmasın).
② `max_tokens=1024` tavanında kesilen yanıttaki araç çağrısı yarım girdiyle YÜRÜTÜLÜYORDU
   (ör. `write_file` içeriğin yarısıyla) ve kesildiği söylenmiyordu.
"""
import types

import pytest


class _Blok:
    def __init__(self, **k):
        self.__dict__.update(k)


def _kur(monkeypatch, yanitlar):
    import anthropic
    from app.services import llm
    import app.services.tools as tools_pkg

    k = {"create": [], "stream": [], "arac": [], "parca": []}

    class _Akis:
        """Gerçek SDK gibi: metin PARÇA PARÇA akar, sonra aynı yanıt `get_final_message`."""

        def __init__(self, kw):
            k["stream"].append(kw)
            self.yanit = yanitlar.pop(0)

        async def __aenter__(self):
            yanit = self.yanit

            async def _metin():
                for b in yanit.content:
                    if b.type == "text":
                        for i in range(0, len(b.text), 3):
                            k["parca"].append(b.text[i:i + 3])
                            yield b.text[i:i + 3]
            self.text_stream = _metin()
            return self

        async def get_final_message(self):
            return self.yanit

        async def __aexit__(self, *a):
            return False

    class _Mesajlar:
        async def create(self, **kw):
            k["create"].append(kw)
            return yanitlar.pop(0)

        def stream(self, **kw):
            return _Akis(kw)

    class _Istemci:
        def __init__(self, **kw):
            self.messages = _Mesajlar()

    async def sahte_arac(ad, arg):
        k["arac"].append((ad, arg))
        return "ok"

    monkeypatch.setattr(anthropic, "AsyncAnthropic", _Istemci)
    monkeypatch.setattr(tools_pkg, "call_tool", sahte_arac)
    monkeypatch.setattr(llm._lp, "anahtar", lambda _s: "sahte")
    return llm, k


async def _topla(llm, mesaj="selam"):
    return "".join([p async for p in llm._stream_anthropic("sistem", [], mesaj)])


def _metin(t, dur="end_turn"):
    return types.SimpleNamespace(content=[_Blok(type="text", text=t)], stop_reason=dur)


@pytest.mark.asyncio
async def test_aracsiz_cevap_TEK_kez_uretilir(monkeypatch):
    llm, k = _kur(monkeypatch, [_metin("Merhaba!")])
    metin = await _topla(llm)
    toplam = len(k["create"]) + len(k["stream"])
    assert toplam == 1, f"aynı cevap {toplam} kez üretildi (create={len(k['create'])}, stream={len(k['stream'])})"
    assert metin == "Merhaba!"


@pytest.mark.asyncio
async def test_arac_sonrasi_final_de_TEK_kez(monkeypatch):
    llm, k = _kur(monkeypatch, [
        types.SimpleNamespace(content=[_Blok(type="tool_use", id="t1", name="saat", input={})],
                              stop_reason="tool_use"),
        _metin("Saat 10."),
    ])
    metin = await _topla(llm)
    assert len(k["create"]) + len(k["stream"]) == 2 and metin == "Saat 10."
    assert k["arac"] == [("saat", {})]


@pytest.mark.asyncio
async def test_tavanda_kesilen_arac_cagrisi_YURUTULMEZ_ve_soylenir(monkeypatch):
    llm, k = _kur(monkeypatch, [types.SimpleNamespace(
        content=[_Blok(type="text", text="Yazıyorum"),
                 _Blok(type="tool_use", id="t1", name="write_file", input={"path": "a.txt"})],
        stop_reason="max_tokens")])
    metin = await _topla(llm, "uzun dosya yaz")
    assert k["arac"] == [], "yarım girdili araç çağrısı yürütüldü"
    assert metin.startswith("Yazıyorum") and llm.M("llm.cevap-kesildi") in metin


@pytest.mark.asyncio
async def test_tavan_1024_degil(monkeypatch):
    llm, k = _kur(monkeypatch, [_metin("x")])
    await _topla(llm)
    assert (k["create"] + k["stream"])[0]["max_tokens"] == llm.ANTHROPIC_MAX_TOKENS >= 4096


@pytest.mark.asyncio
async def test_cevap_AKARAK_gelir_tek_parca_degil(monkeypatch):
    """Çift üretimi kapatmak akışı öldürmesin: metin parçalar halinde iletilmeli."""
    llm, k = _kur(monkeypatch, [_metin("Merhaba, nasılsın bugün?")])
    parcalar = [p async for p in llm._stream_anthropic("sistem", [], "selam")]
    assert len(parcalar) > 1, "cevap tek parça geldi — akış kayboldu"
    assert "".join(parcalar) == "Merhaba, nasılsın bugün?"
    assert k["create"] == [] and len(k["stream"]) == 1
    assert k["stream"][0].get("tools") is not None, "akış çağrısı araçsız — model araç kullanamaz"
