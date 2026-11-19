"""Açılış kilidi, kademe kapılarını KIRMAMALI.

🔴 **Sahada bulundu (2026-09-06, geliştirici bildirdi):** Güvenlik odası
*"Yüz tanıma bu kurulumda kullanılamıyor"* diyordu — oysa kütüphane inmişti,
model inmişti, yüz kayıtlıydı.

**Kök neden:** `tab-nav.js::refreshAllAccess()` sayfa yüklenirken **bir kez**
koşuyor. Açılış kilidi kuruluysa o an token HENÜZ YOK → `/api/license/entitlements`
**401** → `_yukiPlannerOk` · `_yukiPanelOk` · `_yukiJobsOk` · `_yukiFacesOk`
**dördü birden** `false`. Kullanıcı parolayı girip içeri giriyor ama kimse
kapıları yeniden sormuyor.

Belirti YÜZ'de göründü; kusur **dördünde birden**: kilitli bir kurulumda Pro
müşteri parolayla girse bile PLAN sekmesini göremezdi.

📏 Ders: *bir kapının fail-closed olması doğru; yanlış olan, cevabın gelebildiği
ana kadar beklememek.* Kimlik doğrulaması bir kapıyı açtığında, o kimliğe bağlı
her yetki yeniden sorulmalıdır.

Bu dosya statik metin denetimidir — JavaScript'i çalıştırmaz. Ölçtüğü şey
"zincir bağlı mı", "doğru çalışıyor mu" değil; sınırı budur. Ama zincirin
koptuğu yeri tam olarak yakalar.
"""

import re
from pathlib import Path

import pytest


def _yorumsuz(js: str) -> str:
    """`//` ve `/* */` yorumlarını sil.

    ⚠️ Şart: bu dosyanın ilk hâli kendi YORUMUNDAKİ `refreshFaceAccess()`
    metnini "çağrı" sanıp kırmızı yandı. Statik metin denetimi yaparken
    yorumlar ölçüme karışır — kodun ne yaptığını değil, ne anlattığını ölçer.
    """
    js = re.sub(r"/\*.*?\*/", "", js, flags=re.S)
    return re.sub(r"^\s*//.*$", "", js, flags=re.M)

KOK = Path(__file__).resolve().parents[2]
TAB_NAV = KOK / "frontend" / "js" / "tab-nav.js"
APP_LOCK = KOK / "frontend" / "js" / "app-lock.js"
INTRO = KOK / "frontend" / "js" / "intro-sequences.js"

pytestmark = pytest.mark.skipif(
    not (TAB_NAV.exists() and APP_LOCK.exists()),
    reason="frontend dosyaları yok",
)


def test_refreshAllAccess_disariya_aciliyor():
    """Kilit onu çağırabilmeli — IIFE içinde kapalı kalırsa zincir kurulamaz."""
    kaynak = TAB_NAV.read_text(encoding="utf-8").replace(" ", "")
    assert "window.refreshAllAccess=refreshAllAccess" in kaynak, (
        "refreshAllAccess window'a açılmıyor — app-lock.js ona ulaşamaz"
    )


def _basari_blogu() -> str:
    kod = _yorumsuz(APP_LOCK.read_text(encoding="utf-8"))
    return kod.split("function basariylaAcildi")[1].split("\n  }")[0]


def test_kilit_acilinca_kademe_kapilari_TAZELENIYOR():
    """🔑 Asıl kapı. Bu satır silinirse kilitli kurulumda tüm sekmeler kapanır.

    ⚠️ Bu testin ilk hâli `"refreshAllAccess" in blok` diyordu ve **mutasyonu
    kaçırdı**: çağrı silindiğinde bile `if (typeof window.refreshAllAccess ===
    'function')` satırı kelimeyi taşıdığı için yeşil kaldı. Adın geçmesi ile
    fonksiyonun çağrılması ayrı şeylerdir — aranan şey ÇAĞRI.
    """
    blok = _basari_blogu().replace(" ", "")
    assert "window.refreshAllAccess()" in blok, (
        "Kilit açıldıktan sonra kademe kapıları tazelenmiyor — kullanıcı parolayı "
        "girer, içeri girer ve PLAN/PANEL/JOBS/YÜZ'ü göremez (2026-09-06 sahası). "
        "Adı geçmesi yetmez, ÇAĞRILMASI gerekiyor."
    )


def test_tek_kapi_degil_HEPSI_tazeleniyor():
    """Belirti YÜZ'de göründü diye yalnız `refreshFaceAccess()` çağırmak, aynı
    kusuru öbür üç sekmede açık bırakırdı."""
    assert "refreshFaceAccess" not in _basari_blogu(), (
        "Yalnız yüz kapısı tazeleniyor — PLAN/PANEL/JOBS hâlâ kapalı kalır. "
        "refreshAllAccess() çağır."
    )


def test_kademe_kapilari_TOKENLI_istek_atiyor():
    """🔴 Asıl kök neden (2026-09-06 sahası).

    Dört kapı da şöyle yazılıydı:
        fetch(url, {headers: (typeof authHeaders === 'function' ? authHeaders() : {})})
    **`authHeaders` diye bir fonksiyon YOK** — kod tabanında hiçbir yerde tanımlı
    değil. Koşul her zaman false, istekler daima başlıksız gidiyordu.

    AUTH_TOKEN'sız kurulumda görünmüyordu (uçlar zaten açıktı); açılış kilidi
    gelince dördü birden 401 aldı.

    📏 Ders: **var olmayan bir ada `typeof` guard'ı yazmak hatayı gizler.** Kod
    savunmacı görünür, savunduğu dal hiç çalışmaz. Aynı desen bu dosyada daha
    önce `toast` ile yaşanmıştı — yorumu hâlâ orada duruyor.
    """
    kod = _yorumsuz(TAB_NAV.read_text(encoding="utf-8"))
    assert "authHeaders" not in kod, (
        "tab-nav.js hâlâ tanımsız `authHeaders`e başvuruyor — istekler token'sız "
        "gider ve kilitli kurulumda tüm kademe kapıları kapanır."
    )
    # Yetki uçlarına giden her çağrı token'lı yoldan geçmeli.
    for uc in ("/api/license'", "/api/license/entitlements'"):
        for satir in kod.splitlines():
            if uc in satir and "fetch(" in satir:
                assert "_yetkiFetch" in satir or "authFetch" in satir, (
                    f"token'sız yetki çağrısı: {satir.strip()}"
                )


def test_guvenlik_odasi_kapiyi_bir_kez_daha_soruyor():
    """Savunma katmanı: oda, kapı henüz cevaplanmamışken açılabilir (yarış).
    'Kapalı' ile 'henüz sorulmadı' ayrımı yapılmazsa kullanıcıya çalışan bir
    özellik için 'kullanılamıyor' denir.

    🔁 **2026-09-19 (FAZ 3 · Dalga 2 · Blok 6): metin ölçüsü ANAHTAR ölçüsüne
    çevrildi.** Eski hâli kaynakta `"kontrol ediliyor"` cümlesini arıyordu ve
    o cümle sözlüğe taşınınca kırıldı — ölçtüğü şey davranış değil, o günkü
    Türkçe kelimelerdi. Ayrım hâlâ ölçülüyor, ama artık dilden bağımsız:
    ① kod bekleme anında AYRI bir anahtar basıyor mu, ② o anahtarın karşılığı
    "kullanılamıyor" anahtarından FARKLI mı — her dilde ayrı ayrı. İkinci şart
    şunu yakalar: biri sözlükte iki anahtara aynı cümleyi yazarsa kod doğru
    görünür ama kullanıcı yine yanlış teşhis okur.
    """
    kaynak = INTRO.read_text(encoding="utf-8")
    assert "refreshFaceAccess" in kaynak, "oda kapıyı yeniden sormuyor"
    kod = _yorumsuz(kaynak)
    assert "guvenlik.yuz-kontrol" in kod, (
        "oda, kapı cevaplanmadan 'kullanılamıyor' diyor — bekleme anında ayrı "
        "bir metin basılmıyor"
    )
    assert "_curCat!=='guvenlik'" in kod.replace(" ", ""), (
        "yeniden çizim odadan çıkıldığını kontrol etmiyor — kullanıcı başka "
        "odadayken ekran altından değişir"
    )
    for dil in ("tr", "en"):
        sozluk = (KOK / "frontend" / "js" / "diller" / f"{dil}.js").read_text(
            encoding="utf-8"
        )
        bekleme = re.search(r"'guvenlik\.yuz-kontrol':\s*'([^']*)'", sozluk)
        yok = re.search(r"'guvenlik\.yuz-kullanilamaz':\s*'([^']*)'", sozluk)
        assert bekleme and yok, f"{dil}: yüz durumu anahtarları sözlükte eksik"
        assert bekleme.group(1) != yok.group(1), (
            f"{dil}: 'kontrol ediliyor' ile 'kullanılamıyor' AYNI cümleye "
            "düşmüş — kullanıcı bekleme anında yanlış teşhis okur"
        )
