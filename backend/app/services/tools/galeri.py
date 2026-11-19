"""Yuki'nin galeri araçları — `list_media` (ara, listele) · `show_media` (galeride aç).

GALERİ sekmesi salt okunur bir gezgin (`api/galeri_api.py`); bu araçlar ona yeni bir
okuma yolu açmaz, aynı kapılardan geçen iki işlevi kullanır:
  · `ara_medya()` — köklerde ada göre arama (boş sorgu = en yeniler)
  · `coz_hedef()` — tam yol ya da ad → kayıt (kök dışı / medya olmayan / imzası
    tutmayan dosya None döner)
Araç HTTP'ye gitmez: kendi sunucusuna istek atan araç auth'u ikinci kez çözmek
zorunda kalırdı (`ara_medya` belgesi).

`show_media` arayüze `{"type": "galeri_ac", "id", "ad", "klasor_id"}` yayınlar; arayüz
GALERİ'ye geçip `galeri.html?ac=<id>` ile o dosyayı fişte açar (`js/galeri.js` B yolu).

🔑 Dönüş metni GERÇEKLEŞENİ söyler (`harita.py` ile aynı ilke): yayın hiçbir ekrana
ulaşmadıysa "açtım" demez. Ulaştıysa da "gönderildi" der, "açıldı" demez — arayüz cevap
vermiyor; açıldığını bilmiyoruz.
"""
from __future__ import annotations

import logging
import re

logger = logging.getLogger(__name__)

#: Modelin isteyebileceği en çok kayıt — galeri 10.000+ dosya taşıyabilir.
LISTE_TAVAN = 50
_TIPLER = {"resim", "video"}


def _satir(x: dict) -> str:
    return f"{x['ad']} · {x.get('klasor') or '?'} · {x.get('tip')} · id {x['id']}"


async def list_media(ara: str = "", tip: str | None = None, limit: int = 20) -> str:
    """Galeride ada göre ara; sorgu boşsa en yeni dosyalar."""
    from app.api import galeri_api

    tip = (tip or "").strip().lower() or None
    if tip and tip not in _TIPLER:
        return f"Bilinmeyen tür: '{tip}'. Geçerli olanlar: resim, video."
    try:
        limit = max(1, min(int(limit or 20), LISTE_TAVAN))
    except (TypeError, ValueError):
        limit = 20

    try:
        sonuc = galeri_api.ara_medya(ara, limit, tip)
    except Exception as e:  # kök okunamadı vb. — modele açık söyle, boş liste sanmasın
        logger.warning("list_media: %s", e)
        return f"Galeri okunamadı: {e}"

    if not sonuc:
        if ara:
            return f"Galeride '{ara}' adına uyan dosya yok."
        return "Galeride gösterilecek dosya yok (kök klasör ayarlanmamış ya da boş)."
    bas = f"'{ara}' için {len(sonuc)} dosya" if ara else f"En yeni {len(sonuc)} dosya"
    return bas + ":\n" + "\n".join(f"- {_satir(x)}" for x in sonuc)


async def show_media(hedef: str) -> str:
    """Bir dosyayı GALERİ sekmesinde açtırır — tam yol, dosya adı ya da ad parçası."""
    from app.api import galeri_api

    if not (hedef or "").strip():
        return "Hangi dosyanın açılacağı belirtilmedi: bir dosya adı ya da yol ver."
    hedef = hedef.strip()
    try:
        # `list_media`'nın verdiği id: aynı adlı iki dosyadan doğrusunu seçmenin tek yolu.
        # Yol yine `coz_hedef`'in kapılarından geçer (kayıttaki yol kök dışına taşınmış olabilir).
        yol = galeri_api._KAYIT.get(hedef) if re.fullmatch(r"[0-9a-f]{16}", hedef) else None
        kayit = galeri_api.coz_hedef(yol or hedef)
    except Exception as e:
        logger.warning("show_media çözüm: %s", e)
        return f"Galeri okunamadı: {e}"
    if kayit is None:
        return (f"Galeride '{hedef}' bulunamadı (kök klasörlerin dışında, medya değil "
                "ya da yok). list_media ile arayabilirsin.")

    from app.api.websocket import _manager
    ulasan = await _manager.broadcast({
        "type": "galeri_ac", "id": kayit["id"], "ad": kayit["ad"],
        "klasor_id": kayit.get("klasor_id"),
    })
    if not ulasan:
        return (f"{kayit['ad']} bulundu ama açık bir Yuki ekranı yok; galeride "
                "gösterilemedi.")
    logger.info("show_media → %s (%d ekran)", kayit["id"], ulasan)
    return f"{kayit['ad']} ({kayit.get('klasor') or '?'}) galeride açılması için ekrana gönderildi."
