"""401 bir VERİ yanıtı değildir — arayüz onu veri gibi göstermesin.

🔴 Ölçülen kusur (2026-09-08, geliştiricinin ekran görüntüleri + Playwright turu):
uygulama kilidi kuruluyken açılışta **8 istek token'sız gidiyor** (t≈0,45 sn) ve
401 alıyor; kilit t≈6,06 sn'de açılıyor. Kilit sonrası `refreshAllAccess()` yalnız
KADEME KAPILARINI tazeliyordu — paneller ve yüz kütüphanesi kontrolü
yeniden sorulmuyordu. Dört yerde birden görünen sonuç:

  · Sağlık › özet        → "undefined kritik"      (`d.kritik_sayisi` yok)
  · Sağlık › HATA GÜNLÜĞÜ→ ham `{"detail":"Unauthorized"}` ekrana basılıyordu
  · Bildirim ×2          → "… yüklenemedi: HTTP 401" (yanlış teşhis)
  · Güvenlik › yüz       → kurulu kütüphane için sürekli "indir" ekranı

🔑 Ortak sebep tek: **`fetch` 401'de reddetmez ve 401 gövdesi geçerli JSON'dur.**
`r.ok` denetlenmezse `try/catch` hiç ateşlemez; kimlik hatası veri hatası gibi
görünür ve kullanıcı yanlış çözüme yollanır. Bu depoda aynı sınıf daha önce iki
kez çıktı:  (`model-downloader.js` düz `fetch` → sessiz 401) ve ElevenLabs
"401 = geçersiz anahtar" (gerçekte kota) — ikisi de müşteriyi yanlış işe itti.

⚠️ Bu dosya statik bekçidir, kanıt değildir. Kanıt canlı ölçümdür
(2026-09-08 ayar turu, tarayıcıda). Buradaki testler yalnız
kapatılan kusurun sessizce geri dönmesini engeller.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

FE = Path(__file__).resolve().parents[2] / "frontend"
CORE = FE / "js" / "core.js"
INTRO = FE / "js" / "intro-sequences.js"
INDIRICI = FE / "js" / "model-downloader.js"
FACES = FE / "js" / "faces.js"


def _oku(p: Path) -> str:
    return p.read_text(encoding="utf-8")


# ── ① Merkezî halka: token gelince bekleyen istek yeniden denenir ───────────

def test_authfetch_token_bekleyip_yeniden_deniyor() -> None:
    s = _oku(CORE)
    assert "_tokenBekle" in s, "401 sonrası token bekleme halkası yok"
    assert "_tokenBekleyenler" in s, "bekleyen istek kuyruğu yok"
    assert re.search(r"r\.status\s*!==\s*401", s), (
        "authFetch 401'i ayırt etmiyor — yeniden deneme koşulu kaybolmuş"
    )


def test_setauthtoken_bekleyenleri_uyandiriyor() -> None:
    """Token yazıldığı an kuyruk boşaltılmazsa istekler tavana kadar asılı kalır."""
    s = _oku(CORE)
    blok = s[s.index("window.setAuthToken"):]
    blok = blok[: blok.index("\n};") + 3]
    assert "_tokenBekleyenler" in blok, (
        "setAuthToken bekleyenleri uyandırmıyor — token gelse de istekler "
        "zaman aşımına kadar bekler, panel boş kalır"
    )


def test_token_beklemesinin_tavani_var() -> None:
    """Süresiz bekleme, paneli sonsuza asar (motor-bekle.js dersi)."""
    s = _oku(CORE)
    assert re.search(r"_tokenBekle\s*\(\s*ms\w*\s*=\s*\d+", s), (
        "_tokenBekle zaman aşımı almıyor — kullanıcı kilidi hiç açmazsa "
        "bekleyen istekler süresiz asılır"
    )


def test_authfetch_token_varken_yeniden_denemiyor() -> None:
    """Token varken alınan 401 GERÇEK yetki reddidir; tekrar denemek döngü olur."""
    s = _oku(CORE)
    assert "tokenVardi" in s, (
        "authFetch, isteğin token'lı mı token'sız mı gittiğini ayırt etmiyor — "
        "token'lı 401'i yeniden denemek sonsuz döngü üretir ve kilit ekranı hiç açılmaz"
    )


def test_window_authfetch_acikca_yaziliyor() -> None:
    """8 dosya `window.authFetch` yoksa düz `fetch`'e SESSİZCE düşüyor.

    Bugün çalışmasının tek sebebi core.js'in klasik script olması (üst düzey
    `function` bildirimi global nesneye de yazar). core.js bir gün IIFE'ye ya da
    modüle sarılsa sekizi birden token'sız fetch'e düşerdi — hata vermeden.
    """
    assert "window.authFetch = authFetch" in _oku(CORE), (
        "window.authFetch açıkça atanmıyor — örtük global'e bel bağlanmış"
    )


# ── ② Paneller: 401'i veri sanmayacak ───────────────────────────────────────

def test_saglik_ozeti_r_ok_denetliyor() -> None:
    """`undefined kritik` tam olarak bu denetimin yokluğundan doğdu."""
    s = _oku(INTRO)
    blok = s[s.index("window.saglikTara"):]
    blok = blok[: blok.index("window.saglikOnar")]
    assert "if(!r.ok)" in blok, "self-check yanıtı r.ok denetlenmeden JSON sayılıyor"
    assert "d.kritik_sayisi||0" in blok.replace(" ", ""), (
        "kritik sayısı için yedek değer yok — alan gelmezse yine 'undefined' yazar"
    )


def test_hata_gunlugu_ham_govde_basmiyor() -> None:
    """401 gövdesi `<pre>`'ye basılırsa kullanıcı onu hata günlüğü sanır."""
    s = _oku(INTRO)
    assert "_gunlukMetni" in s, "günlük okuma ortak kapıdan geçmiyor"
    blok = s[s.index("async function _gunlukMetni"):]
    blok = blok[: blok.index("window.hataGunluguYukle")]
    assert "if(!r.ok)" in blok, (
        "hata günlüğü yanıtı r.ok denetlenmeden metin sayılıyor — 401 gövdesi "
        "doğrudan ekrana (ve KOPYALA ile panoya) giderdi"
    )


def test_bildirim_panelleri_401i_oturum_sorunu_diye_anlatiyor() -> None:
    s = _oku(INTRO)
    assert "_yuklemeHatasi" in s, "yükleme hatası insanca metne çevrilmiyor"
    assert "HTTP ' + r.status" not in s or "_durumluHata" in s, (
        "ham 'HTTP 401' metni kullanıcıya gösteriliyor"
    )
    # Eski, yanlış teşhis koyan metinler geri gelmesin.
    for eski in ("Hatırlatıcılar yüklenemedi: ' + _esc(e.message)",
                 "Bildirimler yüklenemedi: ' + _esc(e.message)"):
        assert eski not in s, f"eski yanlış teşhis metni geri gelmiş: {eski}"


# ── ③ En pahalı hata: kurulu kütüphaneyi tekrar indirtmek ───────────────────

@pytest.mark.parametrize("dosya", [INDIRICI, FACES])
def test_yetki_reddinde_indirme_ekrani_acilmiyor(dosya: Path) -> None:
    """"Bilinmiyor" ≠ "kurulu değil".

    Yanlış yönde hata yapmanın bedeli asimetrik: kurulu olanı tekrar indirtmek
    kullanıcıya "bozuk" hissi verir; kurulu olmayanı bir tur sonra sormak bedava.
    """
    s = _oku(dosya)
    assert re.search(r"r\.status\s*===\s*401", s), (
        f"{dosya.name}: /api/pydeps/status yetki reddi ayrı ele alınmıyor — "
        f"401 sessizce 'kurulu değil' sayılıp indirme ekranı açılır"
    )


def test_faces_bilinmiyor_durumunu_ayri_tutuyor() -> None:
    s = _oku(FACES)
    assert "bilinmiyor" in s, (
        "faces.js iki durumla (kurulu / değil) çalışıyor; üçüncüsü 'bilinmiyor' eksik"
    )


# ── ③ Oturum düşmüşken (token VAR, sunucu 401) paneller — 2026-09-27, Faz 0.6 ──
# Tarayıcıda ölçüldü (2026-09-26, HQ sekmesi Playwright ölçümü):
#   Anahtar → "Henüz anahtar yok" · Lisans → "FREE (Lite)" · Google → "durum okunamadı" ·
#   Sağlık onar → "Düzeltilemedi." · Günlük Temizle → TEK TIKLA onaysız DELETE + "0 kayıt silindi".
# authFetch token'lı 401'i doğrudan panele verir (backend yeniden başlayıp oturum düşünce).

def _blok(s: str, bas: str, son: str) -> str:
    b = s[s.index(bas):]
    return b[: b.index(son)]


@pytest.mark.parametrize("bas,son", [
    ("window.keyInit = async function", "window.hqSaveKey"),
])
def test_durum_panelleri_401i_veri_saymiyor(bas, son) -> None:
    blok = _blok(_oku(INTRO), bas, son)
    assert "_oturumReddi(r)" in blok and "t('hq.oturum-kilitli')" in blok, f"{bas}: 401 ayırt edilmiyor"
    assert blok.index("_oturumReddi(r)") < blok.index("r.json()"), f"{bas}: 401 gövdesi önce veri sayılıyor"


@pytest.mark.parametrize("bas,son", [
    ("window.saglikOnar = async function", "window.saglikKur"),
    ("window.saglikKur = async function", "async function _gunlukMetni"),
])
def test_saglik_eylemleri_401i_oturum_diye_anlatiyor(bas, son) -> None:
    blok = _blok(_oku(INTRO), bas, son)
    assert blok.index("_oturumReddi(r)") < blok.index("r.json()")


def test_gunluk_temizle_iki_adim_ve_r_ok() -> None:
    blok = _blok(_oku(INTRO), "window.hataGunluguTemizle = async function", "// ════════ AYARLAR")
    assert "_gunlukSilOnay" in blok and "t('saglik.temizle-onay')" in blok, "tek tıkla silme geri gelmiş"
    assert blok.index("return;") < blok.index("method:'DELETE'"), "onaydan önce DELETE gidiyor"
    assert "confirm(" not in blok, "native diyalog — ürün kuralı iki adımlı onay"
    assert "if(!r.ok)" in blok and "yuz.silinemedi" not in blok


def test_google_401i_kilit_diye_ayiriyor() -> None:
    s = _oku(FE / "js" / "google-baglanti.js")
    assert "r.status === 401) return { kilitli: true }" in s and "_durum.kilitli" in s


def test_oturum_metinleri_iki_dilde() -> None:
    for dil in ("tr", "en"):
        s = _oku(FE / "js" / "diller" / f"{dil}.js")
        for k in ("hq.oturum-kilitli", "saglik.temizle-onay", "saglik.kayit-silinemedi"):
            assert f"'{k}':" in s, f"{dil}: {k} yok"
