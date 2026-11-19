"""İlan edilen özellik ile GERÇEKTEN uygulanan özellik ayrışmamalı.

🔴 2026-08-01 ölçümü: `FEATURE_MIN_TIER` 8 özellik ilan ediyordu, yalnız 4'ünün
gerçek kapısı vardı. LİSANS paneli ilan edilen her şeyi "✓ sende açık" gösterdiği
için **Ultra müşterisi üründe hiç olmayan "OYUN modu" ve "3D Yuki"yi açık sanıyordu.**

Galerideki olmayan ekranlar ve vitrindeki "110+ araç" ile aynı hata sınıfı:
ölçülmemiş iddia. Bu testler o sınıfın bu dosyada tekrarlanmasını engeller.
"""

from pathlib import Path

import pytest


KOD_KOKU = Path(__file__).resolve().parents[1] / "app"
FRONTEND = Path(__file__).resolve().parents[2] / "frontend"



def _yorumsuz_html(metin: str) -> str:
    """HTML yorumlarını at — yorumdaki bir açıklama 'kod' sanılmasın.

    (Bu testin ilk hali kendi açıklama yorumumu 'çağrı' diye yakaladı; tek satır
    kontrolü çok satırlı yorumu görmüyordu.)
    """
    import re
    return re.sub(r"<!--.*?-->", "", metin, flags=re.DOTALL)


def test_urunde_yok_denenler_gercekten_erisilemez():
    """OYUN modu ve 3D: frontend'de erişim yolu kalmamalı."""
    modes_js = (FRONTEND / "modes" / "chat-modes.js").read_text(encoding="utf-8")
    # MODES dizisinde 'game' anahtarı bulunmamalı (yorumda geçebilir)
    mode_satirlari = [s for s in modes_js.splitlines()
                      if "key:" in s and not s.strip().startswith("//")]
    assert not any("'game'" in s for s in mode_satirlari), \
        "game_mode 'urunde_yok' deniyor ama mod seçicide duruyor"

    index = _yorumsuz_html((FRONTEND / "index.html").read_text(encoding="utf-8"))
    cagrilar = [s for s in index.splitlines()
                if "_load3DDeps" in s and "window._load3DDeps" not in s]
    assert not cagrilar, f"avatar_3d 'urunde_yok' deniyor ama çağrı var: {cagrilar}"


def _chat_modes_kaynagi() -> str:
    return (FRONTEND / "modes" / "chat-modes.js").read_text(encoding="utf-8")


def test_oyun_modu_beyaz_listede_yok():
    """MODES = tek gerçek kaynak; 'game' oraya girerse OYUN üründe açılır."""
    src = _chat_modes_kaynagi()
    assert "VALID = MODES.map" in src, (
        "VALID artık MODES'ten türemiyor — beyaz liste kapısı değişmiş, "
        "game_mode/avatar_3d'nin 'urunde_yok' durumu yeniden ölçülmeli"
    )
    modes_blok = src.split("const MODES")[1].split("];")[0]
    assert "'game'" not in modes_blok and '"game"' not in modes_blok, (
        "'game' MODES listesine girmiş → OYUN modu üründe erişilebilir. "
        "avatar_3d'nin kendi kapısı YOK, onunla birlikte sızar."
    )


def test_gecersiz_mod_anahtari_chate_dusuruluyor():
    """Düğmenin olmaması erişilemezlik değildir — guard iki yerde de şart.

    Kullanıcı localStorage'a 'game' yazabilir ya da konsoldan
    setViewMode('game') çağırabilir. Her iki yol da 'chat'e düşmeli.
    """
    src = _chat_modes_kaynagi()
    assert "if (!VALID.includes(_mode))" in src, \
        "açılış guard'ı kalkmış: localStorage'daki 'game' geri yüklenebilir"
    assert "if (!VALID.includes(key)) key = 'chat';" in src, \
        "setViewMode guard'ı kalkmış: konsoldan OYUN modu açılabilir"


def test_3d_yalniz_oyun_modundan_yukleniyor():
    """avatar_3d'nin erişilemezliği game_mode'a bağımlı — bağ kopmamalı.

    3D yükleyici game-mode.js DIŞINDA bir yerden çağrılırsa, avatar_3d
    game'in guard'ından bağımsız hale gelir ve kapısız açılır.
    """
    # ⚠️ "yuki-3d.js geçiyor mu" diye aramak YETMEZ — ilk yazımda bu test
    # `core.js`'i suçlu buldu, oysa oradaki tek eşleşme bir YORUM satırıydı
    # (`// FAZ 3a: yuki-3d.js'ye durum sinyali gönder`; kod yalnızca bir
    # CustomEvent yayınlıyor). Aranan şey geçen ad değil, **yükleme yolu**:
    # bir script etiketine/import'a verilen '/ui/modes/yuki-3d.js' yolu.
    YUKLEME_YOLU = "modes/yuki-3d.js"
    yukleyenler = [
        p for p in FRONTEND.rglob("*.js")
        if YUKLEME_YOLU in p.read_text(encoding="utf-8", errors="ignore")
        and p.name != "yuki-3d.js"
    ]
    adlar = sorted(p.name for p in yukleyenler)
    assert adlar == ["game-mode.js"], (
        f"yuki-3d.js'yi yükleyen dosyalar: {adlar} — beklenen yalnız "
        "game-mode.js. Yeni bir yükleyici avatar_3d'yi kapısız açar."
    )
