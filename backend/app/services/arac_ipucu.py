"""Kaçırılan araç uyarısı — "bunu bir araçla da yapabilirdim".

Model cevabını verdikten **sonra** çalışır; üç koşul birden sağlanmalı:
  1. O turda hiç araç çağrılmamış (`runner.total_tool_calls == 0`)
  2. Kullanıcının cümlesi bir kurala uyuyor
  3. O kural yakın zamanda (SUSMA_SN) hatırlatılmamış

Sonuç bir `skill_event` kartıdır (tip `ipucu`); metin `ipucu.<kural>` anahtarıyla
arayüz dilinde kurulur. Gürültü bu özelliği öldürür: kalıplar dar, tekrar susturulur,
araç kullanıldıysa hiç konuşulmaz.

Kural eklemek için `arac-yonlendirme.json` (bu dizinde) düzenlenir. Denetim:
    cd backend && python -m app.services.arac_ipucu --denetle
"""
from __future__ import annotations

import json
import logging
import re
import time
from pathlib import Path
from typing import Any, Optional

log = logging.getLogger(__name__)

_TABLO_YOLU = Path(__file__).resolve().parent / "arac-yonlendirme.json"

# Aynı kural bu süre içinde tekrar hatırlatılmaz (saniye).
# 30 dk: aynı oturumda ısrar etmez ama ertesi gün yeniden hatırlatır.
SUSMA_SN = 1800

# Çok kısa mesajlarda ("tamam", "peki") kural aramak gürültüdür.
ASGARI_UZUNLUK = 8

_kurallar: Optional[list[dict]] = None
_son_hatirlatma: dict[str, float] = {}


def _yukle() -> list[dict]:
    global _kurallar
    if _kurallar is not None:
        return _kurallar
    try:
        ham = json.loads(_TABLO_YOLU.read_text(encoding="utf-8"))
        out = []
        for k in ham.get("kurallar", []):
            try:
                out.append({
                    "ad": k["ad"],
                    "re": re.compile(k["kalip"], re.IGNORECASE),
                    "araclar": k.get("araclar", []),
                    "mesaj": k.get("mesaj", ""),
                })
            except re.error as e:
                log.warning("arac-yonlendirme: '%s' kalıbı derlenemedi: %s", k.get("ad"), e)
        _kurallar = out
    except Exception as e:
        log.warning("arac-yonlendirme.json okunamadı (ipucu kapalı): %s", e)
        _kurallar = []
    return _kurallar


def ipucu_bul(mesaj: str, arac_cagri_sayisi: int) -> Optional[dict[str, Any]]:
    """Kaçırılan fırsat var mı? Varsa kart yükü, yoksa None.

    Args:
        mesaj: kullanıcının ham cümlesi
        arac_cagri_sayisi: o turda çalışan araç sayısı (`runner.total_tool_calls`)
    """
    # 🔴 En önemli kapı: araç zaten kullanıldıysa hatırlatacak bir şey yok.
    if arac_cagri_sayisi > 0:
        return None
    if not mesaj or len(mesaj.strip()) < ASGARI_UZUNLUK:
        return None

    dusuk = mesaj.lower()
    simdi = time.monotonic()
    for k in _yukle():
        if not k["re"].search(dusuk):
            continue
        # "Hiç söylenmedi" için 0.0 varsayılanı KULLANMA: `time.monotonic()` taze
        # açılmış makinede küçüktür, `simdi - 0.0 < SUSMA_SN` doğru çıkar ve
        # uyarı açılıştan sonraki ilk 30 dakika hiç konuşmaz.
        son = _son_hatirlatma.get(k["ad"])
        if son is not None and simdi - son < SUSMA_SN:
            return None          # yakında söylendi — ısrar etme
        _son_hatirlatma[k["ad"]] = simdi
        return {
            "kural": k["ad"],
            "araclar": k["araclar"],
            "mesaj": k["mesaj"],
        }
    return None


async def belki_hatirlat(mesaj: str, arac_cagri_sayisi: int) -> None:
    """Fırsat varsa kartı yayınla. Asla çağıranı bozmaz."""
    try:
        ip = ipucu_bul(mesaj, arac_cagri_sayisi)
        if not ip:
            return
        from app.services.skill_events import emit
        await emit(
            "ipucu",
            ip["mesaj"] or "Bunu bir araçla da yapabilirim",
            name_key=f"ipucu.{ip['kural']}",
            tag=" · ".join(ip["araclar"][:3]),
        )
    except Exception as e:
        log.debug("araç ipucu yayınlanamadı: %s", e)


# ── denetim ────────────────────────────────────────────────────────────────
def _denetle() -> int:
    """Ölü araç adı / bozuk regex / çakışan kalıp var mı?

    Bu denetim olmadan tablo sessizce çürür: araç yeniden adlandırılır, kural
    hiçbir şeye işaret etmez, ipucu "şunu yapabilirim" der ama araç yoktur.
    """
    import sys
    sorun = 0
    try:
        ham = json.loads(_TABLO_YOLU.read_text(encoding="utf-8"))
    except Exception as e:
        print(f"🔴 tablo okunamadı: {e}")
        return 1

    try:
        from app.services.tools.dispatcher import TOOLS
        mevcut = {(t.get("function") or {}).get("name") for t in TOOLS}
    except Exception as e:
        print(f"⚠️  dispatcher okunamadı, araç adı denetimi atlandı: {e}")
        mevcut = None

    adlar = set()
    print(f"kural sayısı: {len(ham.get('kurallar', []))}")
    for k in ham.get("kurallar", []):
        ad = k.get("ad", "?")
        if ad in adlar:
            print(f"🔴 {ad}: yinelenen kural adı"); sorun += 1
        adlar.add(ad)
        try:
            re.compile(k["kalip"])
        except re.error as e:
            print(f"🔴 {ad}: regex bozuk — {e}"); sorun += 1
        if mevcut is not None:
            olu = [a for a in k.get("araclar", []) if a not in mevcut]
            if olu:
                print(f"🔴 {ad}: dispatcher'da OLMAYAN araç → {olu}"); sorun += 1
        if not k.get("mesaj"):
            print(f"⚠️  {ad}: mesaj boş — kart anlamsız görünür")

    print("🟢 temiz" if not sorun else f"🔴 {sorun} sorun")
    return 1 if sorun else 0


if __name__ == "__main__":
    import sys
    if "--denetle" in sys.argv:
        sys.exit(_denetle())
    print(__doc__)
