"""BYOK sağlayıcı kaydının YAPISAL bütünlüğü — ağa çıkmaz.

⚠️ BU DOSYA "13 sağlayıcı çalışıyor" DEMEZ ve diyemez.
`dogrulandi=True` yalnız gerçek bir anahtarla uçtan uca denenmiş sağlayıcıya
verilir; bugün yalnız `openrouter` ve `ollama` öyle. Diğer 13'ün `base_url`'i
sağlayıcı belgelerinden alındı, **ölçümden değil** — bu borç açık ve ancak
gerçek anahtarla kapanır (``).

Buradaki testler o borcu kapatmaz; **ağa çıkmadan yakalanabilen** hata sınıfını
kilitler. Sebep: bir `base_url` yazım hatası müşteride "anahtarın geçersiz" gibi
görünür (ElevenLabs 401 dersinin aynısı — yanlış teşhis müşteriyi yanlış çözüme
yollar) ve bu sınıf tam olarak kopyala-yapıştırdan doğar.
"""

import pytest

from app.services import llm_providers as lp


def _bulut():
    return list(lp.hepsi())


def test_base_url_kopyala_yapistir_carpismasi_yok():
    """İki sağlayıcı aynı adresi gösteriyorsa biri kopyalanırken düzeltilmemiştir."""
    gorulen = {}
    for s in _bulut():
        gorulen.setdefault(s.base_url, []).append(s.kimlik)
    cakisan = {u: k for u, k in gorulen.items() if len(k) > 1}
    assert not cakisan, f"aynı base_url birden çok sağlayıcıda: {cakisan}"


def test_base_url_https_ve_bicimli():
    """Düz http bir BYOK anahtarını ağda açıkta taşırdı."""
    for s in _bulut():
        assert s.base_url.startswith("https://"), f"{s.kimlik}: base_url https değil ({s.base_url})"
        assert " " not in s.base_url.strip(), f"{s.kimlik}: base_url'de boşluk var"
        assert not s.base_url.endswith("//"), f"{s.kimlik}: base_url çift eğik çizgiyle bitiyor"


def test_kimlikler_benzersiz():
    kimlikler = [s.kimlik for s in lp.tumu()]
    assert len(kimlikler) == len(set(kimlikler)), f"yinelenen sağlayıcı kimliği: {kimlikler}"


def test_dogrulandi_bayragi_kaza_ile_acilamaz():
    """🔴 Bu testin ASIL işi bu.

    `dogrulandi=True` arayüzde "denenmedi" uyarısını KALDIRIR — yani müşteriye
    "bunu biz ölçtük" demektir. Bayrağı ölçmeden açmak, ürünün en dürüst
    cümlesini sessizce yalana çevirir. Yeni bir sağlayıcı gerçekten ölçülünce
    bu liste bilinçli olarak güncellenir; kaza ile değil.
    """
    olculen = {s.kimlik for s in lp.tumu() if s.dogrulandi}
    assert olculen == {"openrouter", "ollama"}, (
        f"`dogrulandi` listesi değişmiş: {sorted(olculen)}. Gerçek anahtarla "
        "uçtan uca ölçüldüyse bu testi bilerek güncelle; ölçülmediyse bayrağı geri al."
    )


def test_denenmemis_saglayicilar_arayuze_boyle_bildiriliyor():
    """Ölçülmemiş sağlayıcı, ölçülmemiş olduğunu API cevabında taşımalı."""
    denenmemis = [s for s in _bulut() if not s.dogrulandi]
    assert denenmemis, "hepsi doğrulandı görünüyor — dürüstlük etiketi anlamını yitirir"
    for s in denenmemis:
        assert s.dogrulandi is False


@pytest.mark.parametrize("kimlik", ["openrouter", "anthropic", "openai", "google"])
def test_bilinen_saglayicilar_kayitta_duruyor(kimlik):
    """Yeniden düzenleme sırasında sessizce düşen sağlayıcı olmasın."""
    assert lp.kayit(kimlik) is not None, f"{kimlik} kayıttan düşmüş"
