"""CI tarayıcı sözleşmesi — Atölye ekran testleri CI'da atlanmasın.

`conftest.tarayici_gerekli` chromium yoksa testi ATLAR; yalnız `YUKI_TARAYICI_ZORUNLU=1` iken
düşürür. İş akışı chromium'u kurmaz ya da bu değişkeni vermezse 7 test yeşil görünür ama
hiç koşmaz (11-02 koşu 41523183945'in tersi). Yerel ayna `scripts/ci-yerel.sh` de aynı sözü taşır.
"""
from pathlib import Path

KOK = Path(__file__).resolve().parents[2]


def test_pytest_is_akisi_chromium_kurar_ve_zorunlu_kilar():
    metin = (KOK / ".github/workflows/pytest.yml").read_text(encoding="utf-8")
    assert "playwright install --with-deps chromium" in metin
    assert "YUKI_TARAYICI_ZORUNLU: '1'" in metin


def test_ci_yerel_aynasi_ayni_sozu_tasir():
    metin = (KOK / "scripts/ci-yerel.sh").read_text(encoding="utf-8")
    assert "playwright install chromium" in metin
    assert "YUKI_TARAYICI_ZORUNLU=1" in metin
