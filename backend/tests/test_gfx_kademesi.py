"""HAFİF kademesinin ÖLÇÜLMÜŞ kuralları — mekanik bekçi (2026-08-12).

NEDEN VAR: HAFİF kademesi 2026-08-01'de "dönen katmanları ve glow'ları kapat" diye
yazılmıştı. 2026-08-12'de geliştiricinin Win10 makinesinde (i5-4210U, 2 çekirdek) ölçüldü:

    HALKA normal   → CPU %38,6   GPU %27,8
    HALKA + HAFİF  → CPU %37-41  GPU %18-23      ← CPU HİÇ DÜŞMEDİ

CDP ile ayırt edici deney (10× CPU kısıtlı, 8 sn pencere, sürüklenme %3,5):

    ① HALKA normal                        5,57 s
    ② HALKA + ESKİ HAFİF                  7,82 s   +%43  (DAHA PAHALI)
    ③ yalnız animasyon dur, FİLTRE KALSIN  4,67 s   −%15
    ④ yalnız filtre kapa                  6,46 s   +%18
    ⑤ animasyon dur + filtre kapa         5,93 s    +%8

🔑 Filtreli eleman kendi kompozit katmanına alınır. `filter:none` o katmanı kaldırır
ve hâlâ dönen animasyonlar ana iş parçacığında rasterize edilmeye başlar. Yani HAFİF
işi GPU'dan alıp CPU'ya taşıyordu — darboğazı zaten CPU olan makinede tam ters etki.

Doğru reçete: **hareketi durdur, filtreye DOKUNMA.** Ürünün kendi koduyla ölçülen son
hâli: 5,55 s → **3,02 s (−%46)**.

Bu dosyanın işi o reçeteyi korumak. Yorum korumaz — bu üründe "yorum yanlıştı ve
yanlış olduğu için tutulamadı" vakası zaten yaşandı (`test_surum_zinciri.py`).
"""
from __future__ import annotations

import re
from pathlib import Path

FRONTEND = Path(__file__).resolve().parents[2] / "frontend"
GFX_CSS = FRONTEND / "css" / "gfx.css"
PERF_CSS = FRONTEND / "perf-adaptive.css"
INDEX = FRONTEND / "index.html"
HUD_RING = FRONTEND / "modes" / "hud-ring.js"


def _yorumsuz(css: str) -> str:
    """CSS yorumlarını at.

    🐞 İlk sürüm bunu yapmıyordu ve kapı KENDİ AÇIKLAMA YORUMUMU kaçak sandı —
    yorumda hem `data-gfx="hafif"` hem `filter:none` geçiyordu. Yayın kapısının
    2026-08-10'da düştüğü tuzağın birebir aynısı (`yayin.py::_yorumsuz`):
    *kapı, kendi dokunmadığı metni delil sayarsa yanlış alarm verir ve
    yanlış alarm normalleşince gerçek kaçak da elle geçilir.*
    """
    return re.sub(r"/\*.*?\*/", "", css, flags=re.S)


def _hafif_bloklari(css: str) -> list[str]:
    """`html[data-gfx="hafif"]` seçicisi taşıyan kural gövdeleri."""
    bloklar = []
    for m in re.finditer(r"([^{}]*\{[^{}]*\})", _yorumsuz(css)):
        kural = m.group(1)
        if 'data-gfx="hafif"' in kural:
            bloklar.append(kural)
    return bloklar


def test_hafif_filtre_kapatmaz():
    """🔴 ÖLÇÜMLE YASAK: HAFİF kademesi `filter: none` YAZMAZ.

    Filtre = kompozit katmanı. Kaldırmak işi GPU'dan CPU'ya taşıyor ve HAFİF'i
    tabandan pahalı hâle getiriyor (yukarıdaki ④/⑤ ölçümleri).
    """
    css = GFX_CSS.read_text(encoding="utf-8")
    suclu = [b for b in _hafif_bloklari(css) if re.search(r"filter\s*:\s*none", b)]
    assert not suclu, (
        "HAFİF kademesinde `filter: none` var — bu ÖLÇÜLEREK kaldırılmıştı "
        f"(+%18 CPU). Bloklar:\n{chr(10).join(s.strip()[:200] for s in suclu)}\n\n"
        "Gerçekten gerekliyse önce ölç: HALKA'yı CDP ile 10× kısıtlı koştur, "
        "3,02 sn'nin altına inmiyorsa ekleme."
    )


def test_hafif_hareketi_durdurur():
    """HAFİF'in ASIL işi: halkada hiçbir şey hareket etmesin."""
    css = GFX_CSS.read_text(encoding="utf-8")
    duranlar = [b for b in _hafif_bloklari(css) if re.search(r"animation\s*:\s*none", b)]
    assert duranlar, "HAFİF hiçbir animasyonu durdurmuyor — kademe anlamsız"
    hedefler = " ".join(duranlar)
    # Tek tek seçici saymak sessizce eksik kalır (eski sürüm 14 seçici sayıyordu ve
    # .hr-bar / .hr-anc-card / .hr-hq-dot listenin dışında dönmeye devam ediyordu).
    assert "#hr-ring *" in hedefler, (
        "HAFİF halkanın TÜM alt elemanlarını kapsamalı (`#hr-ring *`). Seçici tek tek "
        "sayılırsa yeni eklenen her animasyon sessizce listenin dışında kalır."
    )


def _low_halka_bloklari(css: str) -> list[str]:
    """`html[data-perf="low"]` + HALKA modu seçicisi taşıyan kural gövdeleri."""
    bloklar = []
    for m in re.finditer(r"([^{}]*\{[^{}]*\})", _yorumsuz(css)):
        kural = m.group(1)
        if 'data-perf="low"' in kural and "hud-ring-mode" in kural:
            bloklar.append(kural)
    return bloklar


def test_low_kademesi_de_hareketi_durdurur():
    """🔴 2026-08-13: `low` kademesi HAFİF'in ÖLÇÜLMÜŞ dersini almamıştı.

    `gfx.css` 08-12'de *"hareketi durdur, filtreye dokunma"* diye yeniden yazıldı,
    ama **aynı düzeltme `perf-adaptive.css`'e uygulanmadı** — orası hâlâ 08-02'nin
    filtre-merkezli mantığındaydı: dönen halka bilerek KORUNUYOR, yalnız filtreler
    kapatılıyordu. Yani otomatik koruma, ölçümdeki ④ senaryosunu (+%18) uyguluyordu.

    Saha kanıtı (geliştirici, Win10 · 3 iş parçacığı · `data-perf=low` ETKİNKEN):
        HALKA + gfx NORMAL (hareket sürüyor) → CPU %68
        HALKA + gfx HAFİF  (hareket durdu)   → CPU %27

    İki kademe aynı yüzeyi hedefler; biri düzeltilip diğeri unutulursa zayıf makine
    otomatik korumadan HİÇBİR fayda görmez — hatta zarar görür.
    """
    css = PERF_CSS.read_text(encoding="utf-8")
    duranlar = [b for b in _low_halka_bloklari(css) if re.search(r"animation\s*:\s*none", b)]
    assert duranlar, (
        "`low` kademesi HALKA'da hiçbir animasyonu durdurmuyor. Zayıf makine tespit "
        "ediliyor ama CPU'yu yiyen şeye (dönen katmanlar) dokunulmuyor."
    )
    hedefler = " ".join(duranlar)
    assert "#hr-ring *" in hedefler, (
        "`low` halkanın TÜM alt elemanlarını kapsamalı (`#hr-ring *`) — `gfx.css` § ① ile "
        "aynı yüzey. Seçici tek tek sayılırsa yeni animasyonlar listenin dışında kalır."
    )


def test_low_kademesi_filtre_kapatmaz():
    """🔴 ÖLÇÜMLE YASAK — `filter: none` yasağı `low` için de geçerli.

    HAFİF'te ölçülen ④ senaryosu (+%18) kademe-bağımsız bir mekanizmadır: filtreli
    eleman kendi kompozit katmanındadır, `filter:none` o katmanı kaldırır.
    ⚠️ `backdrop-filter` bu yasağın DIŞINDA — ayrı maliyet sınıfı, ölçümü ayrı yapılır
    (bu yüzden desen `filter` sözcüğünün başına sınır koyar).
    """
    css = PERF_CSS.read_text(encoding="utf-8")
    suclu = [
        b for b in _low_halka_bloklari(css)
        if re.search(r"(?<!-)\bfilter\s*:\s*none", b)
    ]
    assert not suclu, (
        "`low` kademesinde `filter: none` var — 2026-08-13'te ÖLÇÜMLE kaldırıldı "
        f"(+%18 CPU, gfx.css ④). Bloklar:\n{chr(10).join(s.strip()[:200] for s in suclu)}"
    )


def test_hafifte_ikosahedron_donmez():
    """Merkez ikosahedron rAF ile çiziliyor — CSS `animation:none` onu DURDURAMAZ.

    Ölçüm: döngü 8 sn'lik pencerede ~0,45 sn script zamanı yakıyor. HAFİF'te tek kare
    çizilip döngü kurulmamalı (hiç çizilmezse merkez boş kalır — o yüzden "tek kare").
    """
    js = HUD_RING.read_text(encoding="utf-8")
    assert "_hafifMi()" in js, "hud-ring.js kademeyi hiç sormuyor"
    m = re.search(r"function _polyStart\(\)\s*\{(.*?)\n  \}", js, re.S)
    assert m, "_polyStart bulunamadı (yeniden adlandırıldıysa bu testi güncelle)"
    govde = m.group(1)
    assert "_hafifMi()" in govde, "_polyStart HAFİF'te de döngü kuruyor"
    assert "_polyCiz(" in govde, "_polyStart HAFİF'te tek kare çizmiyor → merkez boş kalır"


def test_perf_snippeti_gfx_snippetinden_once():
    """🔴 SIRA: zayıf makinede otomatik HAFİF kararı `data-perf`'i OKUYOR.

    `data-perf`'i basan snippet aşağı kayarsa karar sessizce hiç çalışmaz — öznitelik
    henüz yoktur, karşılaştırma false döner, hata da vermez. Tam olarak fark edilmesi
    en zor kusur sınıfı: kod duruyor, çalışmıyor.
    """
    html = INDEX.read_text(encoding="utf-8")
    i_perf = html.find("dataset.perf = t")
    i_gfx = html.find("yukiGfxOto_v1")
    assert i_perf > 0, "data-perf snippet'i bulunamadı"
    assert i_gfx > 0, "otomatik HAFİF kararı bulunamadı"
    assert i_perf < i_gfx, (
        "data-perf snippet'i otomatik HAFİF kararından SONRA geliyor → karar hiç çalışmaz"
    )


def test_oto_karar_kullanici_secimini_ezmez():
    """Otomatik karar yalnız kullanıcının HİÇ seçim yapmadığı durumda çalışır."""
    html = INDEX.read_text(encoding="utf-8")
    blok = html[html.find("var p = localStorage.getItem('yukiGfx_v1')"): html.find("data-gfx', p")]
    assert "yukiGfxOto_v1" in blok, "otomatik karar bloğu bulunamadı"
    # Karar, "depoda geçerli değer YOK" dalının içinde olmalı.
    dal = blok.find("p = 'normal';")
    assert 0 < dal < blok.find("yukiGfxOto_v1"), (
        "otomatik karar, kullanıcının kayıtlı seçimini kontrol eden daldan ÖNCE geliyor "
        "→ kullanıcının seçimini ezebilir"
    )
