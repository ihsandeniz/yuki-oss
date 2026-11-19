"""Kullanıcıya gösterilen her yukarı-akış hatası KİMİN söylediğini belirtmeli.

🔴 Neden: geliştiricinin Windows turunda ekranda `401 Missing Authentication header`
çıktı ve **iki tur boyunca kaynağı bulunamadı.** 2026-08-02'de sistematik arandı:

  · Metin bizim kodumuzda YOK · venv paketlerinde YOK · node_modules'ta YOK
  · `hata-gunlugu.jsonl`'de YOK (180 kayıt) — çünkü hata günlüğü 08-01'de eklendi,
    şikâyet 07-31'de geldi: **kayıt tasarım gereği yok**
  · Dış servislerin gerçek 401 gövdeleri ÖLÇÜLDÜ (varsayılmadı), hiçbiri tutmuyor:
      fal.ai      → "Cannot access application ... Authentication is required"
      ElevenLabs  → "Neither authorization header nor xi-api-key received..."
      OpenRouter  → "No cookie auth credentials found" / "User not found."
      Google APIs → "Method doesn't allow unregistered callers..."

Yani kaynak reprodüksiyon olmadan bulunamadı. Ama **yüzey daraltıldı**: yukarı akış
metnini kullanıcı ekranına taşıyabilen yalnız birkaç uç var. Bu testler o uçların
kaynağı da yazmasını zorunlu kılar → bir dahaki sefere ekran görüntüsünün kendisi
teşhis olur, beş servisi tek tek elemek gerekmez.

⚠️ Bu dosya hatayı ÇÖZMÜYOR — tekrarlarsa **teşhis edilebilir** kılıyor.
"""

import re
from pathlib import Path

import pytest

API_KOK = Path(__file__).resolve().parents[1] / "app" / "api"

# Yukarı akış istisnasını (`{e}`) doğrudan kullanıcıya sızdıran satırları yakalar.
SIZDIRAN = re.compile(r'(?:detail=)?f"[^"]*\{e\}[^"]*"')

# Kaynak etiketi: mesajda "[kaynak: X]" geçmeli.
KAYNAK_ETIKETI = re.compile(r"\[kaynak: [^\]]+\]")


def _sizdiran_satirlar() -> list[tuple[str, int, str]]:
    bulunan: list[tuple[str, int, str]] = []
    for p in sorted(API_KOK.rglob("*.py")):
        for i, satir in enumerate(p.read_text(encoding="utf-8").splitlines(), 1):
            s = satir.strip()
            if s.startswith("#"):
                continue
            if "HTTPException" not in s and "detail=" not in s:
                continue
            if SIZDIRAN.search(s):
                bulunan.append((p.name, i, s))
    return bulunan


#  ⑥: metinler kataloğa taşındı — sızıntı artık `f"…{e}…"` değil
# `M("anahtar", sebep=e)`. Etiket satırda değil KATALOG METNİNDE durur, o
# yüzden iki dilde de aranır (TR `[kaynak:` · EN `[source:`). Yalnız eski
# biçimi arasaydı taşımadan sonra bu kapı hiçbir şey ölçmeden yeşil kalırdı.
KATALOGLU = re.compile(r'\bM\(\s*"([^"]+)"[^)\n]*\bsebep\s*=\s*(?:str\()?e\b')
ETIKET = {"tr": re.compile(r"\[kaynak: [^\]]+\]"), "en": re.compile(r"\[source: [^\]]+\]")}


def _katalog_sizintilari() -> list[tuple[str, int, str]]:
    bulunan: list[tuple[str, int, str]] = []
    for p in sorted(API_KOK.rglob("*.py")):
        for i, satir in enumerate(p.read_text(encoding="utf-8").splitlines(), 1):
            if "HTTPException" not in satir and "detail=" not in satir:
                continue
            for m in KATALOGLU.finditer(satir):
                bulunan.append((p.name, i, m.group(1)))
    return bulunan


def test_sizdiran_uc_gercekten_var():
    """Test bayatlamasın: iki desen de hiç eşleşmiyorsa kontrol anlamsızdır."""
    assert _sizdiran_satirlar() or _katalog_sizintilari(), (
        "sızdıran satır bulunamadı — desen bayatlamış olabilir"
    )


@pytest.mark.parametrize("dosya,satir_no,anahtar", _katalog_sizintilari())
def test_katalog_hatasi_kaynagini_IKI_DILDE_soyluyor(dosya, satir_no, anahtar):
    from app.mesajlar import KATALOG

    for dil, etiket in ETIKET.items():
        metin = KATALOG[dil].get(anahtar, "")
        assert etiket.search(metin), (
            f"{dosya}:{satir_no} → '{anahtar}' ({dil}) dış hatayı gösteriyor ama "
            f"kaynağını söylemiyor: {metin!r}"
        )


@pytest.mark.parametrize("dosya,satir_no,satir", _sizdiran_satirlar())
def test_yukari_akis_hatasi_kaynagini_soyluyor(dosya, satir_no, satir):
    """`{e}` ile dış hatayı ekrana taşıyan her uç `[kaynak: ...]` yazmalı."""
    assert KAYNAK_ETIKETI.search(satir), (
        f"{dosya}:{satir_no} yukarı akış hatasını kullanıcıya gösteriyor ama kaynağını "
        f"söylemiyor → ekran görüntüsü teşhis için yetersiz kalır.\n  {satir}\n"
        '  Düzeltme: mesaja "[kaynak: <servis adı>]" ekle.'
    )
