"""Kompozit çubuğundaki her düğmenin grid'de YERİ SÖYLENMİŞ olmalı.

🔴 **Neden bu dosya var — aynı kusur iki kez çıktı:**

`#input-container` bir CSS grid. `css/sohbet.css` § ① (2026-08-28) dört öğeyi
açıkça yerleştirdi (`mic=1 · msg-input=2 · more=3 · send=4`) ve dersi de yazdı:
*"sıralamaya güvenme, YERİ SÖYLE — açıkça yerleştirilen bir grid öğesinin
konumunu `order` değiştiremez."*

Ama **beşinci öğe atlandı**: `#stop-audio-btn` yalnız Yuki konuşurken görünür,
bu yüzden o turdaki denetimde hiç görünmedi. Sonuç (geliştirici, 2026-09-06, ekran
görüntüsü): düğme çubuğun ALTINA, 2. satırın 1. sütununa düşüyordu — grid
otomatik yerleşimi ilk boş hücreyi seçtiği için.

📏 Ders: *"görünmeyen öğe denetlenmez"*. Kapı bu yüzden statik: dosyayı okur,
tarayıcı açmaya gerek kalmaz ve **koşullu görünen** öğeler de kapsanır.
"""

import re
from pathlib import Path

import pytest

KOK = Path(__file__).resolve().parents[2] / "frontend"
SOHBET = (KOK / "css" / "sohbet.css").read_text(encoding="utf-8")
INDEX = (KOK / "index.html").read_text(encoding="utf-8")
CORE = (KOK / "js" / "core.js").read_text(encoding="utf-8")

#: Kompozit çubuğunun grid hücresine oturması gereken öğeler.
#: `#input-break` bilerek DIŞARIDA: o bir flex-satır kırıcı ve grid'de
#: `display:none` — yer kaplamaz, yerleştirilmesi de anlamsız olur.
YERLESMESI_GEREKENLER = [
    "#mic-container",
    "#msg-input",
    "#input-more-btn",
    "#send-btn",
    "#stop-audio-btn",
]


@pytest.mark.parametrize("secici", YERLESMESI_GEREKENLER)
def test_grid_yeri_acikca_yazilmis(secici):
    """Her öğe hem sütununu hem SATIRINI söylemeli.

    ⚠️ Yalnız sütun YETMEZ (sohbet.css'in kendi notu): satırı belirtilmemiş öğe
    yerleştirme sırasına göre konur, o sıra `order` ile değişir ve algoritma
    imleci geri almaz.
    """
    kural = re.search(
        r"#" + secici.lstrip("#") + r"[^{}]*\{[^{}]*\}",
        SOHBET,
    )
    assert kural, f"{secici} için hiç kural yok"

    # Öğenin adı geçen TÜM blokları tara — yerleşim ayrı bir blokta olabilir.
    bloklar = re.findall(
        r"\{[^{}]*\}",
        "".join(
            m.group(0)
            for m in re.finditer(
                r"[^{}]*" + re.escape(secici) + r"[^{}]*\{[^{}]*\}", SOHBET
            )
        ),
    )
    hepsi = " ".join(bloklar)
    assert "grid-column" in hepsi, f"{secici}: grid-column yazılmamış"
    assert "grid-row" in hepsi, f"{secici}: grid-row yazılmamış (sütun tek başına yetmez)"


def test_durdurma_dugmesi_satir_iciyle_gosterilmiyor():
    """Görünürlük SINIFLA verilmeli, `style.display` ile değil.

    Satır içi stil her kuralı yener; düğme grid'deki yerini CSS'ten aldığı için
    satır içi `display` yerleşimi es geçip otomatik yerleşime bırakıyordu.
    """
    assert "classList.toggle('gorunur'" in CORE, "sınıf kancası kaybolmuş"
    assert not re.search(
        r"stop-audio-btn'\)[\s\S]{0,120}?\.style\.display\s*=", CORE
    ), "durdurma düğmesi yine satır içi display ile gösteriliyor"


def test_konusurken_bes_sutun_acilir():
    """5. sütun yalnız konuşurken açılmalı — kalıcı olsaydı ölü alan kalırdı."""
    m = re.search(
        r"#input-container\.konusuyor\s*\{[^{}]*grid-template-columns:([^;]+);",
        SOHBET,
    )
    assert m, "#input-container.konusuyor için sütun şablonu yok"
    assert m.group(1).count("var(--hedef") == 4, "4 düğme + 1 esnek sütun bekleniyor"


def test_halka_modunda_da_gorunur_kalir():
    """HALKA modunun kendi düzeni var; orada da düğme açılabilmeli.

    Satır içi display döneminde bu ayrım gerekmiyordu (satır içi her şeyi yener);
    sınıfa geçince `body:not(.hud-ring-mode)` öneki olmayan bir kural şart oldu.
    """
    assert re.search(r"(?<!\))\s#stop-audio-btn\.gorunur\s*\{[^{}]*display:\s*flex", SOHBET) \
        or re.search(r"^#stop-audio-btn\.gorunur\s*\{[^{}]*display:\s*flex", SOHBET, re.M), \
        "önek almayan .gorunur kuralı yok — HALKA modunda düğme görünmez kalır"


def test_dugme_kompozit_kabinin_icinde():
    """DOM'da da doğru yerde olmalı: grid yerleşimi ancak çocuğa uygulanır."""
    kap = INDEX.index('id="input-container"')
    stop = INDEX.index('id="stop-audio-btn"')
    send = INDEX.index('id="send-btn"')
    assert kap < stop < send + 400, "durdurma düğmesi kompozit kabın dışına çıkmış"
