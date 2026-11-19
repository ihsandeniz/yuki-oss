"""Görev türleri — takılabilir tanım (Yuki Atölye v2, Faz 0b).

Her tür VERİDİR: araç listesi + tavanlar + rehber. Döngü türden bağımsızdır
(`gorev.py`), yeni tür = bu sözlüğe bir giriş. Tanım kişisel servislere
(hafıza, ses, Halka) bağlanmaz.

İki araç sınıfı:
  · `araclar` — tür araçları (`alan.py`), çalışma alanına kilitli, onay sormaz.
  · `genel_araclar` — `call_tool` kapısından (kapsam + kural motoru + onay) geçen
    global araçlar. 🔴 Kendi içinde LLM çağıran araç buraya GİRMEZ: o çağrılar görev
    tavanlarını atlar. `_IC_LLM_ARACLARI`
    bu kuralın denetim listesidir; `tur_dogrula` ihlali kayıt anında reddeder.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

from app.services.atolye import alan
from app.services.runner import GorevTavanlari

# Kendi içinde model ya da dış ajan çağıran araçlar
# (`completions.create`/`LLMRunner`/`AsyncOpenAI(` taraması → files.analyze_image,
# vision_extra.generate_image, orchestrator; skill_forge adım
# zinciri). Görevde koşarlarsa tavan dışı ve ücretli olabilirler.
_IC_LLM_ARACLARI = frozenset({
    "delegate_to_persona", "delegate_to_companion",
    "run_team", "analyze_image", "generate_image", "skill_forge",
})
# Dışarıdan (telefon) açılan görevde hiçbir türün açamayacağı genel araçlar: genel dosya,
# ekran/pano, uygulama/oyun, sistem ve akıllı ev. Tür araçları (`alan_*`) çalışma alanına
# kilitli olduğu için bu listede değildir.
_DIS_YASAK = frozenset({
    "write_file", "append_file", "read_file", "search_file", "compress_file",
    "extract_archive", "diff_files", "check_service", "read_journal",
    "open_application", "launch_game", "close_game", "masaustu_yuki",
    "take_screenshot", "send_screenshot_to_chat", "analyze_image", "kameraya_bak",
    "get_clipboard", "set_clipboard", "start_mode", "smart_home_control",
    "list_packages", "check_updates",
})
# MCP ve skill araçları dış süreç/zincir — görevde kapalı.
_YASAK_ONEKLER = ("mcp__", "skill__")


def dis_yasak_mi(ad: str) -> bool:
    """Dışarıdan (telefon) açılmış görevde HİÇBİR türün açamayacağı genel araç.

    Genel dosya/ekran/pano/uygulama/sistem araçları (`_DIS_YASAK` — sabit küme) + kanvas paneli + MCP/skill. Tür araçları
    (`alan_*`, çalışma alanına kilitli) bu listede değildir; onlar `araclar`dan gelir."""
    return (ad in _DIS_YASAK or "panel" in ad or ad.startswith(_YASAK_ONEKLER)
            or ad in _IC_LLM_ARACLARI)


@dataclass(frozen=True)
class GorevTuru:
    ad: str
    aciklama: str
    araclar: tuple[str, ...]
    genel_araclar: tuple[str, ...] = ()
    tavanlar: GorevTavanlari = field(default_factory=GorevTavanlari)
    rehber: str = ""
    # Dışarıdan açılan görevde de açık kalacak genel araçlar (⊆ genel_araclar). Varsayılan
    # boş: telefon görevi yalnız tür araçlarıyla koşar. Faz 2 araştırma türü web OKUMA
    # araçlarını buraya yazar (karar 2); `dis_yasak_mi` olanlar yazılamaz.
    dis_araclar: tuple[str, ...] = ()
    # Faz 1: model "bitti" deyince servis çıktıyı doğrular; kirliyse geri bildirimle döngüyü
    # sürdürür (en çok `gorev.DUZELTME_TAVANI` tur). "" yok · "site" (statik + ekran + görsel)
    # · "rapor" (Faz 2, deterministik kaynak denetimi). Eski `True` = "site".
    dogrulayici: str | bool = ""
    # Ağ (web okuma) bayrağı.
    ag: bool = False
    # : "" = LLMRunner araç döngüsü (bugünkü türler) · "sahne" = Araştırma
    # Sahnesi motoru (`atolye/sahne.py`) — kendi web aramasını yapar, tür aracı ALMAZ.
    motor: str = ""

    def dogrulayici_adi(self) -> str:
        return "site" if self.dogrulayici is True else (self.dogrulayici or "")

    def semalar(self, dis: bool = False) -> list[dict]:
        """Bu türün LLM'e giden araç şeması. Genel araçlar `TOOLS`'tan süzülür. `dis`:
        dışarıdan açılmış görevde kapalı tür araçları şemaya hiç girmez."""
        out = [alan.SEMALAR[a] for a in self.araclar if not (dis and not arac_dista_acik(self, a))]
        if self.genel_araclar:
            from app.services.tools import TOOLS
            out += [t for t in TOOLS if t.get("function", {}).get("name") in self.genel_araclar]
        return out


_AG_ARACLARI = frozenset({"kaynak_ara", "kaynak_oku"})


def arac_dista_acik(tur: GorevTuru, ad: str) -> bool:
    """Tür aracı dışarıdan (telefon) açılan görevde çalışır mı? Tür araçları çalışma alanına
    kilitlidir; şimdilik hepsi açık (ileride kapatılacak bir tür aracı buraya girer)."""
    return True


def tur_dogrula(tur: GorevTuru) -> None:
    bilinmeyen = [a for a in tur.araclar if a not in alan.ARACLAR]
    if bilinmeyen:
        raise ValueError(f"{tur.ad}: tanımsız tür aracı {bilinmeyen}")
    ic_llm = sorted(set(tur.genel_araclar) & _IC_LLM_ARACLARI)
    if ic_llm:
        raise ValueError(f"{tur.ad}: iç LLM çağıran araç görevde yasak {ic_llm}")
    onekli = sorted(a for a in tur.genel_araclar if a.startswith(_YASAK_ONEKLER))
    if onekli:
        raise ValueError(f"{tur.ad}: MCP/skill aracı görevde yasak {onekli}")
    fazla = sorted(set(tur.dis_araclar) - set(tur.genel_araclar))
    if fazla:
        raise ValueError(f"{tur.ad}: dis_araclar genel_araclar'ın alt kümesi olmalı {fazla}")
    dg = tur.dogrulayici_adi()
    if dg not in ("", "site", "rapor"):
        raise ValueError(f"{tur.ad}: bilinmeyen doğrulayıcı {dg!r}")
    if dg == "site" and "alan_bitir" not in tur.araclar:
        raise ValueError(f"{tur.ad}: doğrulayıcılı tür alan_bitir aracını taşımalı")
    if dg == "rapor" and "rapor_bitir" not in tur.araclar:
        raise ValueError(f"{tur.ad}: rapor doğrulayıcılı tür rapor_bitir aracını taşımalı")
    if not tur.ag and set(tur.araclar) & _AG_ARACLARI:
        raise ValueError(f"{tur.ad}: ağ kapalı türde web aracı {sorted(set(tur.araclar) & _AG_ARACLARI)}")
    if "rapor_bitir" in tur.araclar and dg != "rapor":
        raise ValueError(f"{tur.ad}: rapor_bitir yalnız rapor doğrulayıcılı türde")
    if tur.motor not in ("", "sahne"):
        raise ValueError(f"{tur.ad}: bilinmeyen motor {tur.motor!r}")
    if tur.motor and (tur.araclar or tur.genel_araclar or dg):
        raise ValueError(f"{tur.ad}: motorlu tür araç/doğrulayıcı taşımaz (motor kendi işini yapar)")
    dis_yasak = sorted(a for a in tur.dis_araclar if dis_yasak_mi(a))
    if dis_yasak:
        raise ValueError(f"{tur.ad}: dışarıdan açılan görevde yasak araç {dis_yasak}")


_ALAN = ("alan_agac", "alan_oku", "alan_yaz")
_SITE = _ALAN + ("alan_yama", "alan_bitir")
_ARASTIRMA = _ALAN + ("alan_yama", "kaynak_ara", "kaynak_oku", "rapor_bitir")
# Rehber VERİ dosyası (kodun yanında).
_REHBER_YOLU = Path(__file__).resolve().parent.parent / "atolye_rehber.md"
_REHBER_ARASTIRMA = Path(__file__).resolve().parent.parent / "atolye_rehber_arastirma.md"


def _rehber(yol: Path = _REHBER_YOLU) -> str:
    return yol.read_text(encoding="utf-8").strip()

TURLER: dict[str, GorevTuru] = {
    # Sahte tür — döngünün türden bağımsızlığını kanıtlar (kabul ⑦). Küçük tavan.
    "deneme": GorevTuru(
        ad="deneme",
        aciklama="Deneme türü: çalışma alanına birkaç dosya yazar.",
        araclar=_ALAN,
        tavanlar=GorevTavanlari(adim=10, sure_sn=5 * 60, token=200_000),
        rehber="Bu bir deneme görevidir. İsteneni çalışma alanına yaz, sonra kısa özet ver.",
    ),
    # İlk gerçek tür (Faz 1): yama/bitir araçları, doğrulayıcı (statik + Playwright +
    # isteğe bağlı görsel kontrol), rehber `services/atolye_rehber.md`, önizleme :8011.
    "site": GorevTuru(
        ad="site",
        aciklama="Tek sayfa statik site (HTML/CSS/SVG).",
        araclar=_SITE,
        # Faz 1 ölçümü: örnek site
        # 10 adım · 112 sn · 49 bin token; bozuk siteyi düzeltme 15 adım · 44 sn · 53 bin.
        # Tavan ≈ en kötü ölçümün 2,5-8 katı: 2 düzeltme turu + görsel kontrol sığar.
        # Eski başlangıç önerisi 60 · 30 dk · 1,5 M idi (karar 4: sabit değil).
        tavanlar=GorevTavanlari(adim=40, sure_sn=15 * 60, token=400_000),
        rehber=_rehber(),
        dogrulayici="site",
    ),
    # Faz 2 : kaynaklı araştırma raporu. Web SALT-OKUNUR,
    # komut yok, genel araç yok. Tavan başlangıç önerisi — gerçek koşuda ölçülüp güncellenir
    # (site'nin deseni).
    "arastirma": GorevTuru(
        ad="arastirma",
        aciklama="Kaynaklı araştırma raporu (RAPOR.md) — web okuma, komut yok.",
        araclar=_ARASTIRMA,
        tavanlar=GorevTavanlari(adim=50, sure_sn=20 * 60, token=800_000),
        rehber=_rehber(_REHBER_ARASTIRMA),
        dogrulayici="rapor", ag=True,
    ),
    # : Araştırma Sahnesi — Anthropic API + sunucu web araması (ücretli,
    # tavan `SAHNE_TAVAN_USD`), anahtar yoksa sahte motor. Sonuç 6-12 blok `SAHNE.json`
    # + `RAPOR.md`; ön yüz HALKA'nın önüne dizer. Adım = ilerleme olayı sayısı (tavan
    # anlamsız büyük); süre tavanı motoru keser.
    "sahne": GorevTuru(
        ad="sahne",
        aciklama="Araştırma Sahnesi — web'de arar, sonucu 6-12 blok halinde ekrana dizer (API kredisi).",
        araclar=(),
        tavanlar=GorevTavanlari(adim=10_000, sure_sn=10 * 60, token=400_000),
        motor="sahne",
    ),
}

for _t in TURLER.values():
    tur_dogrula(_t)
