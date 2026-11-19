"""Transkripsiyon düzenleme mesajı — bozuk TEK bir mesaj oturumu düşürmemeli.

🔴 2026-08-02 (kişisel Alice'te canlıda yaşandı, üründe aynı kod bulundu):
`ERROR | app.api.websocket | Beklenmedik hata: 'NoneType' object has no attribute 'strip'`

Sebep: `edit_msg.get("text", "")` — anahtar YOKSA `""` döner, ama anahtar VARSA ve
değeri `null` ise `None` döner. Varsayılan devreye girmez. `None.strip()` patlar ve
`ws_realtime` handler'ının TAMAMI düşer → kullanıcı cevabını hiç alamadan soket ölür.

Frontend `confirm_transcription` mesajını `{"type": ..., "text": inp.value}` ile
kuruyor; `inp.value` bir yarış durumunda null'a düşerse istemci hiç fark etmez —
sunucu tarafında oturum sessizce ölür.
"""

import json

import pytest

from app.api.websocket import duzenlemeyi_uygula


def _mesaj(govde) -> dict:
    return {"text": json.dumps(govde)}


# ── Asıl kusur ──────────────────────────────────────────────────────

def test_null_text_cokmez_orijinali_korur():
    """`"text": null` → eskiden AttributeError, artık orijinal metin."""
    sonuc = duzenlemeyi_uygula(
        _mesaj({"type": "confirm_transcription", "text": None}), "merhaba nasılsın"
    )
    assert sonuc == "merhaba nasılsın"


def test_text_anahtari_hic_yoksa_da_calisir():
    sonuc = duzenlemeyi_uygula(_mesaj({"type": "confirm_transcription"}), "orijinal")
    assert sonuc == "orijinal"


# ── Mutlu yol bozulmadı ─────────────────────────────────────────────

def test_gercek_duzenleme_uygulaniyor():
    sonuc = duzenlemeyi_uygula(
        _mesaj({"type": "confirm_transcription", "text": "düzeltilmiş metin"}), "ham metin"
    )
    assert sonuc == "düzeltilmiş metin"


def test_bosluklar_kirpiliyor():
    sonuc = duzenlemeyi_uygula(
        _mesaj({"type": "confirm_transcription", "text": "  kırpılmış  "}), "ham"
    )
    assert sonuc == "kırpılmış"


def test_sadece_bosluk_orijinali_korur():
    """Kullanıcı kutuyu boşaltırsa transkripsiyon silinmemeli."""
    sonuc = duzenlemeyi_uygula(
        _mesaj({"type": "confirm_transcription", "text": "   "}), "orijinal"
    )
    assert sonuc == "orijinal"


# ── Diğer bozuk girdiler de oturumu düşürmemeli ────────────────────

@pytest.mark.parametrize("bozuk", [
    {"text": "{bozuk json"},                                  # ayrıştırılamaz
    {"text": json.dumps(["liste", "değil", "sözlük"])},        # yanlış tip
    {"text": json.dumps("düz string")},                        # yanlış tip
    {"text": json.dumps(None)},                                # null gövde
    {"text": ""},                                              # boş çerçeve
    {"bytes": b"\x00\x01"},                                    # metin değil ikili
    {},                                                        # boş sözlük
])
def test_bozuk_mesajlar_orijinali_korur(bozuk):
    assert duzenlemeyi_uygula(bozuk, "korunacak metin") == "korunacak metin"


def test_baska_tipte_mesaj_yoksayilir():
    """`confirm_transcription` olmayan bir mesaj metni değiştirmemeli."""
    sonuc = duzenlemeyi_uygula(_mesaj({"type": "ping", "text": "yoksay"}), "orijinal")
    assert sonuc == "orijinal"
