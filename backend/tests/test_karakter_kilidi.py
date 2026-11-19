"""Karakter kilidi: arayüzün gösterdiği kilit ile sunucunun verdiği yetki ayrışmamalı.

🔴 2026-08-09 ölçümü (geliştirici sordu: *"Pro'da açıksa Ultra'da da açık olması gerekmez mi?"*):
gerçek durum ikisinden de kötüydü. `chat-modes.js`'teki `UNLOCKED_CHARS = ['yuki']`
**sabitti ve hiç değişmiyordu** → kademe ne olursa olsun, parasını ödemiş Pro *ve*
Ultra müşteri de Yuki dışındaki karakterleri kilitli görüyordu. Backend doğru cevabı
üretiyordu (`characters_for`), arayüz ona hiç sormuyordu.

Hata sınıfı tanıdık: **ölçülmemiş iddia** (bkz. test_ozellik_ilani.py). Orada ilan
edilen özelliğin kapısı yoktu; burada kapı vardı ama arayüz kapıya bakmıyordu.
Bu testler o sınıfın karakter tarafında tekrarlanmasını engeller.
"""

from pathlib import Path


FRONTEND = Path(__file__).resolve().parents[2] / "frontend"
CHAT_MODES = FRONTEND / "modes" / "chat-modes.js"
HUD_RING = FRONTEND / "modes" / "hud-ring.js"


# ── Sunucu tarafı: kullanıcının asıl sorusu ─────────────────────────────
# ── Arayüz tarafı: kilit sunucudan mı geliyor ───────────────────────────
def _chat_modes() -> str:
    return CHAT_MODES.read_text(encoding="utf-8")


def test_kilit_dizisi_yeniden_atanmiyor_yerinde_guncelleniyor():
    """hud-ring.js aynı dizi nesnesini tutuyor; yeniden atama onu bayat bırakır.

    `UNLOCKED_CHARS = [...]` yazılırsa chat-modes yeni diziyi kullanır, hud-ring
    eskisini → ödeme duvarı aynı soruya iki farklı cevap verir.
    """
    s = _chat_modes()
    assert "UNLOCKED_CHARS.length = 0" in s, "dizi yerinde güncellenmiyor"
    assert "window.MODE_UNLOCKED_CHARS = UNLOCKED_CHARS" in s
    assert "window.MODE_UNLOCKED_CHARS" in HUD_RING.read_text(encoding="utf-8"), (
        "hud-ring.js kendi kopyasını tutuyorsa iki liste ayrışır"
    )


