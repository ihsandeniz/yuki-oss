"""Yuki Atölye v2 — Faz 0b: görev servisi .

Kabul ölçüleri (Atölye v2 planı § 2 Faz 0b):
  ④ çalışma alanı dışına yazma ≥10 deneme → hepsi red
  ⑤ DURDUR ≤2 sn, sonraki adım koşmaz
  ⑥ restart → `durdu`, kendiliğinden devam etmez, onayla aynı adımdan sürer
     (gerçek süreç öldürmeli hâli: test_gorev_restart.py)
  ⑦ site + deneme türü aynı döngüden geçer

LLM sahte, atölye kökü pytest'in geçici dizini — gerçek veri dizinine dokunulmaz.
"""
import asyncio
import json
import os
import time
import types
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.services import gorev as gorev_mod
from app.services.atolye import alan
from app.services.atolye.turler import TURLER, GorevTuru, tur_dogrula
from app.services.gorev import GorevHatasi, GorevServisi
from app.services.runner import GorevTavanlari
from app.services.atolye.baglam import yerel_baglam
from tests.atolye_yardimci import _arac_akisi, _icerik_akisi, _sahte_router


# ══════════════════════════════════════════════════════════════════════════
#  Sahte LLM
# ══════════════════════════════════════════════════════════════════════════

class SahteLLM:
    """`create()` her çağrıda sıradaki yanıtı verir; çağrıların mesajlarını saklar.

    yanit: akış nesnesi ya da `async () -> akış` (yavaş/asılı model için)."""

    def __init__(self, yanitlar):
        self.yanitlar = list(yanitlar)
        self.cagrilar: list[list[dict]] = []
        self.client = MagicMock()
        self.client.chat.completions.create = AsyncMock(side_effect=self._create)

    async def _create(self, **kw):
        self.cagrilar.append(json.loads(json.dumps(kw["messages"], default=str)))
        y = self.yanitlar.pop(0)
        # ⚠️ `callable(y)` DEĞİL: sahte akışlar MagicMock → onlar da çağrılabilir.
        return await y() if isinstance(y, types.FunctionType) else y

    async def bekle(self, n, sure=5.0):
        """n. çağrıya kadar bekle — görev hatayla biterse sonsuza asılma."""
        son = time.monotonic() + sure
        while len(self.cagrilar) < n:
            assert time.monotonic() < son, f"{n}. LLM çağrısı {sure} sn içinde gelmedi"
            await asyncio.sleep(0.01)

    def router(self):
        r = _sahte_router(self.client)
        return r


def _yaz(i, yol, icerik="x"):
    return _arac_akisi([(f"c{i}", "alan_yaz", {"yol": yol, "icerik": icerik})])


@pytest.fixture
def kok(tmp_path):
    return tmp_path / "atolye"


async def _kos_bitir(servis, llm, tur, ad, istek="yap", zaman=5):
    with patch("app.services.llm_router.get_router", return_value=llm.router()), yerel_baglam():
        await servis.baslat(tur, ad, istek)
        return await servis.bekle(f"{tur}/{ad}", zaman)


# ══════════════════════════════════════════════════════════════════════════
#  ④ Çalışma alanı kilidi — ≥10 kaçış denemesi
# ══════════════════════════════════════════════════════════════════════════

def _hazir_alan(tmp_path):
    kok = tmp_path / "alan"
    kok.mkdir()
    dis = tmp_path / "dis"
    dis.mkdir()
    (dis / "hedef.txt").write_text("DOKUNULMAMALI")
    (kok / "bag_dizin").symlink_to(dis, target_is_directory=True)
    (kok / "bag_dosya").symlink_to(dis / "hedef.txt")
    (kok / "alt").mkdir()
    (kok / "alt" / "ic_bag").symlink_to(dis, target_is_directory=True)
    (kok / alan.AYRILMIS).mkdir()
    (kok / alan.AYRILMIS / "durum.json").write_text('{"durum":"kosuyor"}')
    return kok, dis


KACIS = [
    "../kacis.txt",
    "../../kacis.txt",
    "alt/../../kacis.txt",
    "alt/./../../kacis.txt",
    "/tmp/kacis.txt",
    "/etc/passwd",
    "~/.ssh/authorized_keys",
    os.path.expanduser("~/.ssh/authorized_keys"),
    "bag_dizin/hedef.txt",            # dizine sembolik bağ
    "bag_dosya",                      # dosyaya sembolik bağ
    "alt/ic_bag/yeni.txt",            # derindeki bağ
    "bag_dizin/yeni/derin.txt",       # bağın altına yeni dizin
    ".gorev/durum.json",              # servis kaydı
    "a\x00/../../kacis.txt",          # NUL + ..
    "a\x00b.txt",                     # yalnız NUL
    "",                               # boş
    "a/" * 130 + "x",                 # aşırı uzun (bileşenler kısa — OS sınırına takılmaz)
]


@pytest.mark.parametrize("yol", KACIS)
def test_calisma_alani_disina_yazma_reddedilir(tmp_path, yol):
    kok, dis = _hazir_alan(tmp_path)
    once = sorted(p.name for p in tmp_path.iterdir()) + sorted(p.name for p in dis.iterdir())
    sonuc = alan.alan_yaz(kok, yol, "SALDIRI")
    assert sonuc.startswith("Hata:"), f"{yol!r} kabul edildi: {sonuc}"
    assert (dis / "hedef.txt").read_text() == "DOKUNULMAMALI"
    assert (kok / alan.AYRILMIS / "durum.json").read_text() == '{"durum":"kosuyor"}'
    sonra = sorted(p.name for p in tmp_path.iterdir()) + sorted(p.name for p in dis.iterdir())
    assert once == sonra, "alan dışında yeni dosya oluştu"


@pytest.mark.parametrize("yol,katman", [
    ("../kacis.txt", "'..'"),
    ("alt/../../kacis.txt", "'..'"),
    ("bag_dizin/hedef.txt", "sembolik bağ"),
    ("bag_dosya", "sembolik bağ"),
    ("alt/ic_bag/yeni.txt", "sembolik bağ"),
    ("a\x00b.txt", "NUL"),
    ("/etc/passwd", "mutlak"),
    (".gorev/durum.json", "görev kaydı"),
])
def test_her_katman_kendi_nedeniyle_reddeder(tmp_path, yol, katman):
    """Katmanlar birbirini örter (son savunma: yolun alan dışına çözülmesi). Her katmanı
    AYRI ölçmek için red nedeni de denetlenir — yoksa sökülen katmanı arkadaki gizler."""
    kok, _ = _hazir_alan(tmp_path)
    with pytest.raises(alan.AlanHatasi, match=katman):
        alan.guvenli_yol(kok, yol)


def test_son_savunma_alan_disina_cozulen_yolu_reddeder(tmp_path):
    """Bağ denetimi atlatılmış gibi (bağ, denetimden SONRA kurulmuş): yol yine de
    alan dışına çözüldüğü için reddedilir."""
    from pathlib import Path
    kok, _ = _hazir_alan(tmp_path)
    with patch.object(Path, "is_symlink", return_value=False):
        with pytest.raises(alan.AlanHatasi, match="dışına çözülüyor"):
            alan.guvenli_yol(kok, "bag_dizin/hedef.txt")


def test_kacis_deneme_sayisi_en_az_10():
    assert len(KACIS) >= 10


@pytest.mark.parametrize("yol", ["../kacis.txt", "/etc/hostname", "bag_dosya", "bag_dizin/hedef.txt",
                                 ".gorev/durum.json"])
def test_calisma_alani_disindan_okuma_reddedilir(tmp_path, yol):
    kok, _ = _hazir_alan(tmp_path)
    sonuc = alan.alan_oku(kok, yol)
    assert sonuc.startswith("Hata:") and "DOKUNULMAMALI" not in sonuc


def test_denetim_atlatilsa_bile_acma_bagi_izlemez(tmp_path):
    """3. katman: denetimle açma arasında dosya bağa çevrilirse O_NOFOLLOW reddeder."""
    kok, dis = _hazir_alan(tmp_path)
    with patch("app.services.atolye.alan.guvenli_yol", side_effect=lambda k, y: k / y):
        sonuc = alan.alan_yaz(kok, "bag_dosya", "SALDIRI")
    assert sonuc.startswith("Hata:")
    assert (dis / "hedef.txt").read_text() == "DOKUNULMAMALI"


def test_denetim_atlatilsa_bile_okuma_bagi_izlemez(tmp_path):
    kok, _ = _hazir_alan(tmp_path)
    with patch("app.services.atolye.alan.guvenli_yol", side_effect=lambda k, y: k / y):
        sonuc = alan.alan_oku(kok, "bag_dosya")
    assert sonuc.startswith("Hata:") and "DOKUNULMAMALI" not in sonuc


def test_alan_icinde_yazma_okuma_agac_calisir(tmp_path):
    kok, _ = _hazir_alan(tmp_path)
    assert alan.alan_yaz(kok, "css/stil.css", "body{}").startswith("yazıldı")
    assert alan.alan_oku(kok, "css/stil.css") == "body{}"
    agac = alan.alan_agac(kok)
    assert "css/stil.css" in agac and ".gorev" not in agac


def test_agac_agac_kokunden_disari_bag_izlemez(tmp_path):
    kok, _ = _hazir_alan(tmp_path)
    assert "hedef.txt" not in alan.alan_agac(kok)


@pytest.mark.asyncio
async def test_model_alan_disina_yazamaz_servis_yolundan(kok, tmp_path):
    """Aynı kilit, gerçek görev döngüsünden geçerken de tutar."""
    llm = SahteLLM([_yaz(0, "../../kacis.txt"), _yaz(1, "/tmp/kacis-gorev.txt"),
                    _yaz(2, "tamam.txt", "ok"), _icerik_akisi("bitti")])
    d = await _kos_bitir(GorevServisi(kok), llm, "deneme", "kilit")
    assert d["durum"] == "bitti"
    assert not (tmp_path / "kacis.txt").exists() and not (kok / "kacis.txt").exists()
    assert not os.path.exists("/tmp/kacis-gorev.txt")
    assert (kok / "deneme" / "kilit" / "tamam.txt").read_text() == "ok"
    arac_sonuclari = [m["content"] for m in llm.cagrilar[-1] if m["role"] == "tool"]
    assert arac_sonuclari[0].startswith("Hata:") and arac_sonuclari[1].startswith("Hata:")


# ══════════════════════════════════════════════════════════════════════════
#  Araç kapısı — izin listesi dışı ad dispatcher'a ulaşmaz
# ══════════════════════════════════════════════════════════════════════════

@pytest.mark.asyncio
@pytest.mark.parametrize("arac", ["write_file", "komut_calistir", "delegate_to_persona", "mcp__fs__write"])
async def test_tur_disi_arac_reddedilir_dispatchera_gitmez(kok, arac):
    llm = SahteLLM([_arac_akisi([("c0", arac, {"path": "/tmp/x", "content": "x"})]),
                    _icerik_akisi("bitti")])
    with patch("app.services.tools.call_tool", new=AsyncMock(return_value="ÇALIŞTI")) as ct:
        d = await _kos_bitir(GorevServisi(kok), llm, "deneme", "izin")
    assert ct.await_count == 0
    sonuc = [m["content"] for m in llm.cagrilar[-1] if m["role"] == "tool"][0]
    assert "izinli değil" in sonuc
    assert d["durum"] == "bitti"


def test_tur_araclari_global_semaya_sizmaz():
    from app.services.tools import TOOLS
    adlar = {t["function"]["name"] for t in TOOLS}
    assert not adlar & set(alan.ARACLAR), "tür araçları sohbet şemasına/api'ye sızdı"


def test_ic_llm_cagiran_arac_ture_eklenemez():
    with pytest.raises(ValueError, match="iç LLM"):
        tur_dogrula(GorevTuru("x", "x", ("alan_yaz",), genel_araclar=("analyze_image",)))
    with pytest.raises(ValueError, match="MCP"):
        tur_dogrula(GorevTuru("x", "x", ("alan_yaz",), genel_araclar=("mcp__fs__write",)))
    for t in TURLER.values():
        tur_dogrula(t)




@pytest.mark.asyncio
async def test_gorevde_ekran_baglami_enjekte_edilmez(kok):
    llm = SahteLLM([_icerik_akisi("bitti")])
    with patch("app.services.runner._inject_screen_context",
               side_effect=lambda m: [{"role": "system", "content": "EKRAN-SIZINTISI"}] + m):
        await _kos_bitir(GorevServisi(kok), llm, "deneme", "ekran")
    assert "EKRAN-SIZINTISI" not in json.dumps(llm.cagrilar[0], ensure_ascii=False)


# ══════════════════════════════════════════════════════════════════════════
#  ⑦ Türden bağımsızlık + adım kaydı
# ══════════════════════════════════════════════════════════════════════════

@pytest.mark.asyncio
async def test_site_ve_deneme_ayni_donguden_gecer(kok):
    kurulan = []
    gercek = gorev_mod.LLMRunner

    def _casus(*a, **kw):
        r = gercek(*a, **kw)
        kurulan.append(r)
        return r

    # Faz 1: site türünün bitiş doğrulaması bu testin konusu değil (⑦ = aynı döngü);
    # doğrulama döngüsü tests/test_atolye_site.py'de ölçülür.
    import dataclasses
    servis = GorevServisi(kok, turler={**TURLER, "site": dataclasses.replace(
        TURLER["site"], dogrulayici=False)})
    with patch("app.services.gorev.LLMRunner", side_effect=_casus):
        d1 = await _kos_bitir(servis, SahteLLM([_yaz(0, "index.html", "<h1>Luna</h1>"),
                                                 _yaz(1, "logo.svg", "<svg/>"),
                                                 _icerik_akisi("site hazır")]), "site", "luna")
        d2 = await _kos_bitir(servis, SahteLLM([_yaz(0, "not.txt", "deneme"),
                                                 _icerik_akisi("tamam")]), "deneme", "bir")
    assert [r.gorev is not None for r in kurulan] == [True, True]
    assert all(type(r) is gercek for r in kurulan)
    assert [s["function"]["name"] for s in kurulan[0].tools] == list(TURLER["site"].araclar)
    assert kurulan[0].gorev.adim == 40 and kurulan[1].gorev.adim == 10   # tavan türden (Faz 1 ㉓)
    assert (d1["durum"], d1["adim"]) == ("bitti", 3) and (d2["durum"], d2["adim"]) == ("bitti", 2)
    assert (kok / "site" / "luna" / "index.html").read_text() == "<h1>Luna</h1>"
    assert (kok / "site" / "luna" / "logo.svg").exists()
    assert (kok / "deneme" / "bir" / "not.txt").exists()
    assert d1["ozet"].strip() == "site hazır"
    assert {g["id"] for g in servis.liste()} == {"site/luna", "deneme/bir"}


@pytest.mark.asyncio
async def test_durum_json_her_adimda_yazilir(kok):
    servis = GorevServisi(kok)
    gorulen = []
    gercek_yaz = servis._yaz

    def _izle(d):
        gercek_yaz(d)
        gorulen.append((d["durum"], d["adim"]))

    servis._yaz = _izle
    llm = SahteLLM([_yaz(i, f"d{i}.txt") for i in range(3)] + [_icerik_akisi("son")])
    await _kos_bitir(servis, llm, "deneme", "adimlar")
    assert gorulen == [("kosuyor", 0), ("kosuyor", 1), ("kosuyor", 2), ("kosuyor", 3), ("bitti", 4)]
    mesajlar = json.loads((kok / "deneme" / "adimlar" / ".gorev" / "mesajlar.json").read_text())
    assert mesajlar[-1] == {"role": "assistant", "content": "son "}


@pytest.mark.asyncio
async def test_adim_tavaninda_yarim_ve_uzatma_ile_devam(kok):
    servis = GorevServisi(kok)
    tur = GorevTuru("kucuk", "k", ("alan_yaz",), tavanlar=GorevTavanlari(adim=2))
    servis.turler = {"kucuk": tur}
    llm = SahteLLM([_yaz(0, "a"), _yaz(1, "b"), _yaz(2, "c"), _icerik_akisi("son")])
    d = await _kos_bitir(servis, llm, "kucuk", "t")
    assert (d["durum"], d["neden"], d["adim"]) == ("yarim", "adim", 2)
    with patch("app.services.llm_router.get_router", return_value=llm.router()), yerel_baglam():
        await servis.devam("kucuk/t", onay=True, uzat={"adim": 5})
        d = await servis.bekle("kucuk/t", 5)
    assert (d["durum"], d["adim"], d["tavanlar"]["adim"]) == ("bitti", 4, 7)


# ══════════════════════════════════════════════════════════════════════════
#  ⑤ DURDUR ≤2 sn — sonraki adım koşmaz
# ══════════════════════════════════════════════════════════════════════════

def _yavas_tur():
    return {"yavas": GorevTuru("yavas", "y", ("alan_yaz",), genel_araclar=("yavas_arac",),
                               tavanlar=GorevTavanlari(adim=20))}


@pytest.mark.asyncio
async def test_durdur_iki_saniyede_ve_sonraki_adim_kosmaz(kok):
    async def _yavas(ad, args):
        await asyncio.sleep(30)
        return "geç"

    llm = SahteLLM([_yaz(0, "ilk.txt"), _arac_akisi([("c1", "yavas_arac", {})])]
                   + [_yaz(i, f"{i}.txt") for i in range(2, 10)])
    servis = GorevServisi(kok, turler=_yavas_tur())
    with patch("app.services.llm_router.get_router", return_value=llm.router()), \
         patch("app.services.tools.call_tool", new=AsyncMock(side_effect=_yavas)), yerel_baglam():
        await servis.baslat("yavas", "d", "yap")
        await llm.bekle(2)
        await asyncio.sleep(0.1)                     # yavaş araç koşuyor
        t0 = time.monotonic()
        d = await servis.durdur("yavas/d")
        gecen = time.monotonic() - t0
        await asyncio.sleep(2.5)                     # bir adım daha koşacak mı?
    assert gecen <= 2.0, f"DURDUR {gecen:.2f} sn sürdü"
    assert (d["durum"], d["neden"]) == ("durdu", "durdur")
    assert len(llm.cagrilar) == 2, "durdurulan görevde sonraki adım koştu"
    assert d["adim"] == 1, "yarım kalan adım sayılmamalı (DEVAM onu yeniden koşar)"
    assert servis.durum("yavas/d")["durum"] == "durdu"


@pytest.mark.asyncio
async def test_durdur_asili_llm_cagrisinda_da_iki_saniye(kok):
    """Tur LLM yanıtını beklerken iptal jetonunu göremez → görev iptali devreye girer."""
    async def _asili():
        await asyncio.sleep(60)

    llm = SahteLLM([_yaz(0, "ilk.txt"), _asili])
    servis = GorevServisi(kok)
    with patch("app.services.llm_router.get_router", return_value=llm.router()), yerel_baglam():
        await servis.baslat("deneme", "asili", "yap")
        await llm.bekle(2)
        t0 = time.monotonic()
        d = await servis.durdur("deneme/asili")
        gecen = time.monotonic() - t0
    assert gecen <= 2.0
    assert (d["durum"], d["neden"], d["adim"]) == ("durdu", "durdur", 1)


@pytest.mark.asyncio
async def test_durdurulan_gorev_onayla_ayni_adimdan_surer(kok):
    async def _asili():
        await asyncio.sleep(60)

    llm = SahteLLM([_yaz(0, "a.txt"), _yaz(1, "b.txt"), _asili,
                    _yaz(2, "c.txt"), _icerik_akisi("bitti")])
    servis = GorevServisi(kok)
    with patch("app.services.llm_router.get_router", return_value=llm.router()), yerel_baglam():
        await servis.baslat("deneme", "surer", "yap")
        await llm.bekle(3)
        await servis.durdur("deneme/surer")
        kayitli = json.loads((kok / "deneme" / "surer" / ".gorev" / "mesajlar.json").read_text())
        # sistem + istek + 2 tamamlanan adım × (asistan araç çağrısı + araç sonucu)
        assert len(kayitli) == 6, f"adım mesajları kaydedilmemiş: {len(kayitli)}"
        with pytest.raises(GorevHatasi, match="onay"):
            await servis.devam("deneme/surer")
        await servis.devam("deneme/surer", onay=True)
        d = await servis.bekle("deneme/surer", 5)
    assert llm.cagrilar[3] == kayitli, "DEVAM son tamamlanan adımın mesajlarıyla başlamalı"
    assert (d["durum"], d["adim"], d["devam_sayisi"]) == ("bitti", 4, 1)
    assert sorted(p.name for p in (kok / "deneme" / "surer").iterdir() if p.is_file()) == \
        ["a.txt", "b.txt", "c.txt"]


# ══════════════════════════════════════════════════════════════════════════
#  ⑥ Restart (süreç içi) — yeni servis 'kosuyor'u 'durdu' yapar, kendisi koşmaz
#  Gerçek süreç öldürmeli hâli: tests/test_gorev_restart.py
# ══════════════════════════════════════════════════════════════════════════

def test_yeni_servis_kosuyor_kaydini_durdu_yapar_ve_baslatmaz(kok):
    yol = kok / "deneme" / "yarim" / ".gorev"
    yol.mkdir(parents=True)
    (yol / "durum.json").write_text(json.dumps({"id": "deneme/yarim", "durum": "kosuyor", "adim": 3}))
    servis = GorevServisi(kok)
    d = servis.durum("deneme/yarim")
    assert (d["durum"], d["neden"], d["adim"]) == ("durdu", "yeniden_baslatma", 3)
    assert servis._kosan == {}
    assert "yeniden_baslatma_durdu" in (yol / "olaylar.jsonl").read_text()


# ══════════════════════════════════════════════════════════════════════════
#  Kapılar — dış bağlam, eşzamanlılık, ad, durum
# ══════════════════════════════════════════════════════════════════════════

@pytest.mark.asyncio
async def test_dis_baglamdan_baslatma_ve_devam_kapali_durdur_acik(kok):
    servis = GorevServisi(kok)
    with pytest.raises(GorevHatasi, match="dış bağlam"):        # varsayılan bağlam = dış
        await servis.baslat("deneme", "dis", "yap")
    assert not (kok / "deneme" / "dis").exists()

    async def _asili():
        await asyncio.sleep(60)

    llm = SahteLLM([_asili])
    with patch("app.services.llm_router.get_router", return_value=llm.router()):
        with yerel_baglam():
            await servis.baslat("deneme", "yerel", "yap")
        d = await servis.durdur("deneme/yerel")                  # dış bağlamda DURDUR açık
        assert d["durum"] == "durdu"
        with pytest.raises(GorevHatasi, match="dış bağlam"):
            await servis.devam("deneme/yerel", onay=True)


@pytest.mark.asyncio
async def test_ayni_anda_tek_gorev(kok):
    async def _asili():
        await asyncio.sleep(60)

    llm = SahteLLM([_asili])
    servis = GorevServisi(kok)
    with patch("app.services.llm_router.get_router", return_value=llm.router()), yerel_baglam():
        await servis.baslat("deneme", "bir", "yap")
        with pytest.raises(GorevHatasi, match="en çok 1"):
            await servis.baslat("site", "iki", "yap")
        await servis.durdur("deneme/bir")
    assert not (kok / "site" / "iki").exists()


@pytest.mark.asyncio
@pytest.mark.parametrize("ad", ["../kacis", "A", "a/b", "", "-bas", "x" * 41, "..", "a b"])
async def test_gecersiz_ad_reddedilir(kok, ad):
    with yerel_baglam(), pytest.raises(GorevHatasi):
        await GorevServisi(kok).baslat("deneme", ad, "yap")
    assert not kok.exists() or not any((kok.parent).glob("kacis*"))


@pytest.mark.parametrize("gid", ["deneme/../../etc", "../deneme/x", "yok/x", "deneme", "deneme/A"])
def test_gecersiz_kimlik_okunamaz(kok, tmp_path, gid):
    # Kimlik doğrulanmazsa "deneme/../../etc" kökün DIŞINDAKİ bu kaydı okurdu.
    tuzak = tmp_path / "etc" / ".gorev"
    tuzak.mkdir(parents=True)
    (tuzak / "durum.json").write_text('{"id": "TUZAK", "durum": "bitti"}')
    with pytest.raises(GorevHatasi, match="geçersiz"):
        GorevServisi(kok).durum(gid)


@pytest.mark.asyncio
async def test_biten_gorev_surdurulemez_ve_ad_tekrar_kullanilamaz(kok):
    servis = GorevServisi(kok)
    await _kos_bitir(servis, SahteLLM([_icerik_akisi("bitti")]), "deneme", "tek")
    with yerel_baglam():
        with pytest.raises(GorevHatasi, match="sürdürülemez"):
            await servis.devam("deneme/tek", onay=True)
        with pytest.raises(GorevHatasi, match="zaten var"):
            await servis.baslat("deneme", "tek", "yap")


@pytest.mark.asyncio
@pytest.mark.parametrize("uzat", [{"adim": -5}, {"ucretli_dusus": 1}, {"arac_zaman_asimi": 999}, {"adim": "9"}])
async def test_gecersiz_uzatma_reddedilir(kok, uzat):
    servis = GorevServisi(kok, turler={"k": GorevTuru("k", "k", ("alan_yaz",),
                                                      tavanlar=GorevTavanlari(adim=1))})
    await _kos_bitir(servis, SahteLLM([_yaz(0, "a"), _icerik_akisi("x")]), "k", "u")
    with yerel_baglam(), pytest.raises(GorevHatasi, match="uzatma"):
        await servis.devam("k/u", onay=True, uzat=uzat)


