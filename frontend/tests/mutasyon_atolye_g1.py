"""G1 ön yüz kapılarının mutasyon sınavı — her kapıyı bir kez bilerek kırar, test_atolye_g1.py'nin
yakaladığını ölçer. test_atolye_g1.py ile aynı ortam değişkenleri ve sunucu gerekir; doğrudan koşulur:

    YUKI_URL=… YUKI_TEST_ANAHTAR=… python frontend/tests/mutasyon_atolye_g1.py

Çıkış 0 = hepsi yakalandı. Dosyalar her adımdan sonra geri yüklenir (ön yüz statik, restart yok).
"""
import os
import subprocess
import sys
from pathlib import Path

KOK = Path(__file__).resolve().parents[2]
MUTASYONLAR = [
    ("core.js gorev köprüsü", "frontend/js/core.js",
     "if (d && d.type === 'gorev') {", "if (false) {"),
    ("sahne tembel yükleme", "frontend/js/gorev-serit.js",
     "    if (!_acik()) return;\n    _sahneYukle();\n", "    if (!_acik()) return;\n"),
    ("kaynak noopener", "frontend/js/arastirma-sahnesi.js",
     "a.rel = 'noopener noreferrer';", "a.rel = '';"),
    ("Esc kapatır", "frontend/js/arastirma-sahnesi.js",
     "if (e.key === 'Escape' && katman && !katman.hidden) kapat();", "void 0;"),
    ("bitince kendiliğinden açılır", "frontend/js/arastirma-sahnesi.js",
     "      _listeTazele();\n      ac(g.id);\n", "      _listeTazele();\n"),
    ("ilerleme kartı", "frontend/js/arastirma-sahnesi.js",
     "if (g.durum === 'kosuyor' || kartGid === g.id) _kartGuncelle(g);", "void 0;"),
    ("bitiş duyurusu", "frontend/js/gorev-serit.js",
     "    _bitisDuyurusu(once, g);\n", ""),
    ("hareketi azalt", "frontend/js/arastirma-sahnesi.js",
     "katman.classList.toggle('az-hareket', az);", "void 0;"),
    ("odak KAPAT'a", "frontend/js/arastirma-sahnesi.js",
     "try { katman.querySelector('.sh-kapat').focus({ preventScroll: true }); } catch (_) {}", ""),
]


def kos() -> int:
    env = {k: v for k, v in os.environ.items() if k != "YUKI_EKRAN_DIZINI"}
    return subprocess.run([sys.executable, "-m", "pytest", "-q", "-x", "-p", "no:warnings",
                           "-p", "no:cacheprovider", "frontend/tests/test_atolye_g1.py"],
                          cwd=KOK, env=env, capture_output=True, text=True).returncode


def main() -> int:
    if kos() != 0:
        print("🔴 taban kırmızı — önce testleri yeşile çek")
        return 1
    kacan = []
    for ad, dosya, eski, yeni in MUTASYONLAR:
        yol = KOK / dosya
        asil = yol.read_text(encoding="utf-8")
        if asil.count(eski) != 1:
            print(f"🔴 {ad}: hedef metin {asil.count(eski)} kez bulundu")
            kacan.append(ad)
            continue
        try:
            yol.write_text(asil.replace(eski, yeni), encoding="utf-8")
            yakalandi = kos() != 0
        finally:
            yol.write_text(asil, encoding="utf-8")
        print(f"{'✅' if yakalandi else '🔴'} {ad}")
        if not yakalandi:
            kacan.append(ad)
    print(f"mutasyon {len(MUTASYONLAR) - len(kacan)}/{len(MUTASYONLAR)} yakalandı")
    return 1 if kacan else 0


if __name__ == "__main__":
    sys.exit(main())
