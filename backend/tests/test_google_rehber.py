"""Google kurulum rehberi — kapılar ( FAZ 3).

Panel FAZ 2'de indi ve içinde **"Rehberi aç"** düğmesi var; işaret ettiği dosya ise
FAZ 3'e bırakılmıştı. Yani sürüm çıksaydı müşteri o düğmeye basıp **404** görecekti —
üstelik tam da *"kimliği nereden alacağım"* diye sorduğu anda. Bu dosyanın ilk kapısı
o kırık bağlantının bir daha doğmamasını sağlar.

Kapıların hepsi **statik** (ağa çıkmaz, backend istemez). Canlı tur ayrıca var:
`scratchpad/rehber-olcum.py` — yatay taşma · kırık görsel · token'lar uygulanmış mı.

📏 Bu projenin tekrar eden dersi: *ilan edilen yetenek ≠ ölçülen yetenek.* Bir düğme
   çizmek, bastığında bir şey olacağını garanti etmez.
"""

import re
from pathlib import Path

FRONTEND = Path(__file__).resolve().parents[2] / "frontend"
PANEL_JS = (FRONTEND / "js" / "google-baglanti.js").read_text(encoding="utf-8")
REHBER_YOL = FRONTEND / "docs" / "google-kurulum.html"
REHBER = REHBER_YOL.read_text(encoding="utf-8")
INDEX = (FRONTEND / "index.html").read_text(encoding="utf-8")


def _panelin_actigi_yol() -> str:
    """Panelin "Rehberi aç" düğmesinin gerçekten açtığı URL."""
    m = re.search(r"window\.open\(\s*'(/ui/[^']+)'", PANEL_JS)
    assert m, "panelde rehberi açan window.open bulunamadı — desen değiştiyse test güncellensin"
    return m.group(1)


def test_panelin_isaret_ettigi_rehber_diskte_var():
    """'Rehberi aç' → 404 olmasın.

    Yol **JS'ten okunur**, teste elle yazılmaz: sabit yazsaydık panel başka bir
    dosyaya yönlendirildiğinde test yeşil kalır, kullanıcı 404 görürdü.
    """
    yol = _panelin_actigi_yol()
    hedef = FRONTEND / yol[len("/ui/"):]
    assert hedef.exists(), f"panel {yol} açıyor ama dosya yok: {hedef}"
    assert hedef == REHBER_YOL, f"panel beklenmedik bir dosyaya gidiyor: {hedef}"


def test_rehberde_yayin_durumu_adimi_var():
    """🔴 7 gün tuzağı.

    OAuth izin ekranı `Testing` durumunda kalırsa Google refresh token'ı **7 günde
    iptal eder** ve varsayılan durum Testing'dir. Kullanıcı bir hafta sonra sebebi
    hiçbir yerde yazmayan bir kopma yaşar. Rehber bu adımı **atlarsa** rehber değil
    tuzaktır — o yüzden mekanik kapı.
    """
    assert "PUBLISH APP" in REHBER, "yayınlama adımının düğme adı yazılmamış"
    assert "In production" in REHBER, "hedef durum (In production) yazılmamış"
    assert "7 gün" in REHBER, "atlanınca ne olacağı (7 gün) söylenmemiş"


def test_rehber_masaustu_istemcisini_soyluyor():
    """`Desktop app` yerine `Web application` seçen kullanıcı `redirect_uri_mismatch` alır.

    Yuki'nin geri dönüş adresi çalıştığı porttan türetilir; sabit adres kaydı isteyen
    istemci türü bu akışla uyumsuzdur. Hem doğru tür hem yanlış türün adı geçmeli —
    kullanıcı hatayı gördüğünde arayacağı kelime odur.
    """
    assert "Desktop app" in REHBER
    assert "Web application" in REHBER
    assert "redirect_uri_mismatch" in REHBER, "en olası hata sorun giderme tablosunda yok"


def test_rehberdeki_gorseller_diskte_var():
    """Kırık görsel = anlatımın yarısının kaybı (rehber ekran görüntüsüne dayanıyor)."""
    kaynaklar = re.findall(r'<img[^>]+src="([^"]+)"', REHBER)
    assert kaynaklar, "rehberde hiç görsel yok — ekran görüntüsüz rehber kararı değiştiyse test güncellensin"
    eksik = [s for s in kaynaklar if not (REHBER_YOL.parent / s).exists()]
    assert not eksik, f"rehberdeki görseller diskte yok: {eksik}"


def test_rehber_index_ile_ayni_varlik_damgasini_kullaniyor():
    """Paylaşılan CSS'e iki sayfa farklı `?v=` veremez.

    🔴 2026-08-31'de aynı kusur index ↔ planner arasında ölçülmüştü: kullanıcı bir
    ekranda yeni CSS'i alıyor, öbüründe tarayıcı **eskisini** önbellekten veriyordu.
    Rehber üçüncü sayfadır ve aynı kurala tabidir; `test_surum_zinciri.py`'nin kapısı
    yalnız index/planner ikilisine bakar.
    """
    def damgalar(metin):
        return {m.group(1): m.group(2)
                for m in re.finditer(r"/ui/([\w/.-]+\.(?:css|js))\?v=([\w.]+)", metin)}

    i, r = damgalar(INDEX), damgalar(REHBER)
    ortak = set(i) & set(r)
    assert ortak, "rehber index ile hiç ortak varlık paylaşmıyor — desen değiştiyse test güncellensin"
    sapan = {k: (i[k], r[k]) for k in sorted(ortak) if i[k] != r[k]}
    assert not sapan, f"rehber bayat varlık sürümü isteyecek: {sapan}"


def test_rehber_kendi_temasini_veriyor():
    """Rehber **sistem tarayıcısında** açılır; uygulamanın tema sınıfı orada yoktur.

    `dis-baglanti.js::pencereAcmaIsleyicisi` her `window.open`'ı `openExternal`'a
    devreder (uygulama içinde pencere açılmaz). Tema özniteliği yazılmazsa sayfa
    token'ların varsayılanına düşer — bugün koyu, ama bu bir varsayım olarak kalırdı.
    """
    assert re.search(r'<html[^>]+data-tema="koyu"', REHBER), "rehber temasını kendi belirtmiyor"
