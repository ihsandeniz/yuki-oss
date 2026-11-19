"""Kullanıcıya giden metnin MERKEZİ kataloğu (FAZ 3, 2026-09-18).

Bugüne kadar backend'de böyle bir şey YOKTU — ölçüldü: 1.086 kullanıcı metni
86 dosyada, uçlarda elle yazılmış; `app/hata_yaniti.py` yalnız iki global
işleyici (429 + 500), sözlük değil. Yani dil değiştirilse bile metinlerin
tamamı Türkçe kalıyordu (2026-09-18 i18n taraması).

    from app.mesajlar import M
    raise HTTPException(403, detail=M("kademe.plan-pro"))

── Neden frontend'in sözlüğüne bakmıyor ────────────────────────────────────
Backend'in metni istemciden bağımsız üretilmeli: sohbetin araç dönüşleri LLM'e
de gidiyor ve orada DOM yok. İki katman ayrı, ama **aynı dil anahtarını**
okuyorlar (`config.get_arayuz_dili()` — ARAYÜZ ekseni), yani ayrışamazlar.

── İki eksen (2026-10-04) ──────────────────────────────────────────────────
Bu katalog kullanıcıya giden EKRAN metnidir → arayüz dilinden okur (tr/en).
LLM'in ÇIKTI dili konuşma ekseninden gelir (`config.yanit_dili()`, tr/en/ja):
Japonca konuşan Türk kullanıcı hataları Türkçe okur, Yuki ona Japonca cevap verir.

── 🔴 Arayüz etiketleri TEK YERDE: `ui.*` ──────────────────────────────────
Mesajların bir kısmı arayüz yolu tarif ediyor (*"⚙ AYAR → 🔑 ANAHTAR"*). Bu
etiketler cümlelerin içine GÖMÜLMEZ, `{ui_ayar}` gibi enterpolasyonla girer.
Sebep ölçülmüş bir kısıt (SENTEZ § 6, bağlayıcı kısıt ⑥): frontend'de `AYAR`
→ `SETTINGS` olurken backend cümlesi "AYAR" demeye devam ederse mesaj
**olmayan bir menüyü** tarif eder. Tek yerde durursa ayrışamaz; `ui.ayar`'ın
frontend sözlüğündeki karşılığıyla aynı olduğunu `test_faz3_backend_i18n.py`
mekanik olarak denetliyor.

── Yedek zinciri ───────────────────────────────────────────────────────────
`ja` → `en` → `tr` → anahtarın kendisi. Arayüz dili artık `ja` OLAMAZ
(2026-10-04), yani bu dal yalnız açıkça `dil="ja"` geçen çağrı içindir; `ja`
kataloğu yazılmayacak (karar). Japonca isteyene Türkçe göstermek İngilizce
göstermekten kötüdür. Anahtarın kendisini döndürmek de bilinçli: boş string "kayıp metin"
üretir, anahtar görünürse kusur kendini söyler.
"""
from __future__ import annotations

from . import en as _en
from . import tr as _tr

KAYNAK = "tr"
KATALOG: dict[str, dict[str, str]] = {"tr": _tr.METINLER, "en": _en.METINLER}
YEDEK: dict[str, list[str]] = {"ja": ["en"]}

__all__ = ["M", "Mc", "KATALOG", "KAYNAK", "YEDEK", "mevcut_dil"]


def mevcut_dil() -> str:
    """Aktif ARAYÜZ dili (tr/en). İki eksen kararı (2026-10-04): ekran metni
    konuşma dilinden değil arayüz dilinden okunur — `get_language()` DEĞİL."""
    try:
        from app import config

        return config.get_arayuz_dili()
    except Exception:  # pragma: no cover — config yoksa ürün zaten açılmaz
        return KAYNAK


def _ui_degerleri(dil: str) -> dict[str, str]:
    """`ui.ayar` → `{ui_ayar}`. Her çağrı yerinde elle geçirilmesi gerekseydi
    biri er geç unutur ve cümleye sabit "AYAR" yazardı — kısıt ⑥ tam oradan
    kaçardı. Otomatik verilir, çağıran yine de ezebilir."""
    cikti: dict[str, str] = {}
    for aday in [KAYNAK, *reversed(YEDEK.get(dil, [])), dil]:
        for anahtar, deger in KATALOG.get(aday, {}).items():
            if anahtar.startswith("ui."):
                cikti["ui_" + anahtar[3:].replace("-", "_")] = deger
    return cikti


def _ham(anahtar: str, dil: str) -> str | None:
    for aday in [dil, *YEDEK.get(dil, []), KAYNAK]:
        metin = KATALOG.get(aday, {}).get(anahtar)
        if metin is not None:
            return metin
    return None


def M(anahtar: str, /, dil: str | None = None, **degerler: object) -> str:
    """Katalogdan metin getir, `{ad}` yer tutucularını doldur.

    `dil` verilmezse aktif dil okunur. Açıkça verilmesi testler ve ileride
    istek-başı dil (`Accept-Language`) için: bugün dil durumu **süreç
    genelinde** tutuluyor (`config._arayuz_dili`), yani çok kullanıcılı
    bir kurulumda bir kişinin seçimi herkesi etkiler. Bu imza o değişikliği
    bugünden mümkün kılıyor; katalog çağrılarının hiçbiri yeniden yazılmayacak.
    """
    d = dil or mevcut_dil()
    metin = _ham(anahtar, d)
    if metin is None:
        return anahtar
    if "{" not in metin:
        return metin
    try:
        return metin.format(**{**_ui_degerleri(d), **degerler})
    except (KeyError, IndexError):
        # Eksik yer tutucu metni çöpe çevirmesin — ham hâli görünsün ki
        # kusur ekranda kendini söylesin (anahtarı döndürme kuralının eşi).
        return metin


def Mc(anahtar: str, sayi: int, /, dil: str | None = None, **degerler: object) -> str:
    """Sayıya bağlı metin. `n == 1` → `anahtar`, değilse `anahtar + '-cogul'`.

    🔑 Türkçe'de sayıdan sonra çoğul eki GELMEZ ("5 dakika"), İngilizce'de
    gelir ("5 minutes"). Bu yüzden `-cogul` anahtarı yalnız gereken dilde
    tanımlanır ve yoksa tekile düşülür — parite kapısı bu tek istisnayı
    tanıyor (`test_faz3_backend_paritesi`).
    """
    d = dil or mevcut_dil()
    if sayi != 1:
        cogul = _ham(anahtar + "-cogul", d)
        if cogul is not None:
            try:
                return cogul.format(**{**_ui_degerleri(d), "n": sayi, **degerler})
            except (KeyError, IndexError):
                return cogul
    return M(anahtar, dil=d, n=sayi, **degerler)
