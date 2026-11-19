"""Açılışta müşterinin GÖRDÜĞÜ şeyi koruyan mekanik kapılar (2026-08-13).

NEDEN VAR — geliştiricinin gerçek Windows saha raporu (v0.6.2, 08-13):
    "ilk başta açtık mı o şifre alanı gösteriyor, sonra bir anda tekrar
     Ctrl+R yapıyormuş gibi yeniden yükleniyor"

İki AYRI kusur çıktı, ikisi de koda dayanıyordu:

① `#auth-screen` `index.html`de **sınıfsız** duruyordu. CSS'te yalnız
  `#auth-screen.hidden { display:none }` var → yani varsayılan GÖRÜNÜR.
  `core.js::_authCheckAndInit` `/api/ping`'e sorup 401 GELMEZSE ekranı
  gizliyor; ama o cevap gelene kadar parola kutusu ekranda duruyor.
  Soğuk Windows açılışında motor 7-10 sn geç geldiği için müşteri
  "parola mı isteyecek?" diye düşünüyordu — oysa satılan pakette
  `AUTH_TOKEN` boş, auth kapalı, ekran hiç gösterilmeyecekti.
  🔑 Sınıf, gizlenmeyi *koda* değil *belgeye* bağlıyordu.

② Service worker `activated` olunca `window.location.reload()` çağrılıyordu —
  **ilk kurulumda da**. Oysa `navigator.serviceWorker.controller` yoksa sayfayı
  yöneten bir SW hiç yoktu, yani tazelenecek bayat önbellek de yok. Sonuç:
  temiz kurulumda ekran kendiliğinden bir kez sıfırlanıyordu.

Bu dosya iki kuralı da mekanik olarak korur. Yorum korumaz.
"""
from __future__ import annotations

import re
from pathlib import Path

FRONTEND = Path(__file__).resolve().parents[2] / "frontend"
INDEX = FRONTEND / "index.html"
CORE = FRONTEND / "js" / "core.js"
STYLE = FRONTEND / "style.css"


def test_auth_ekrani_varsayilan_gizli():
    """① Parola ekranı sınıfsız açılmaz — `hidden` ile başlar."""
    html = INDEX.read_text(encoding="utf-8")
    m = re.search(r'<div\s+id="auth-screen"([^>]*)>', html)
    assert m, "#auth-screen bulunamadı (yeniden adlandırıldıysa bu testi güncelle)"
    nitelikler = m.group(1)
    assert "hidden" in nitelikler, (
        "#auth-screen `hidden` sınıfı OLMADAN açılıyor → parola kutusu, JS "
        "/api/ping cevabını alana kadar ekranda kalır. Soğuk Windows açılışında "
        "bu 7-10 saniye sürüyor ve müşteri parola isteneceğini sanıyor "
        "(geliştirici saha raporu 2026-08-13). Auth GEREKİYORSA _showAuthScreen() "
        "sınıfı kaldırıp gösteriyor — varsayılan gizli olmak yetenek kaybı değil."
    )


def test_gizleme_kurali_hala_var():
    """`hidden` sınıfının bir karşılığı olmalı — yoksa ① sessizce boşa düşer.

    Kapının kendisi de kapıya muhtaç: `index.html`e sınıf yazıp CSS kuralını
    silmek testi yeşil bırakır ama ekran yine görünür.
    """
    css = STYLE.read_text(encoding="utf-8")
    assert re.search(r"#auth-screen\.hidden\s*\{[^}]*display\s*:\s*none", css), (
        "`#auth-screen.hidden { display:none }` kuralı yok — index.html'deki "
        "`hidden` sınıfı hiçbir şey yapmıyor demektir."
    )


def test_ilk_kurulumda_sayfa_yenilenmez():
    """② SW ilk kurulumunda `location.reload()` çağrılmaz.

    Ölçüt: `reload()` çağrısı, `navigator.serviceWorker.controller` kontrolüyle
    aynı blokta korunuyor olmalı. Kontrol kaldırılırsa temiz kurulumda ekran
    yine kendiliğinden sıfırlanır.
    """
    js = CORE.read_text(encoding="utf-8")
    # 🐞 İlk sürüm bloğu girinti sayısıyla (`\n\s{6}\}\);`) yakalamaya çalışıyordu ve
    # kendi düzeltmem girintiyi değiştirdiği için eşleşmedi — kapı, ölçtüğü şeyin
    # BİÇİMİNE bağlanmıştı. Artık niyet doğrudan ölçülüyor: `updatefound` ile ona ait
    # `reload()` çağrısı ARASINDA controller kontrolü var mı? Girintiden bağımsız.
    i = js.find("'updatefound'")
    assert i != -1, "SW `updatefound` kaydı bulunamadı (yeniden yazıldıysa testi güncelle)"
    j = js.find("location.reload", i)
    assert j != -1, "SW güncelleme yolunda yenileme hiç yok"
    arada = js[i:j]
    assert "serviceWorker.controller" in arada, (
        "SW `updatefound` bloğu `navigator.serviceWorker.controller` kontrolü "
        "YAPMIYOR → ilk kurulumda da sayfa yeniliyor. Temiz kurulumda tazelenecek "
        "bayat önbellek yoktur; yenileme yalnız GÜNCELLEME durumunda anlamlıdır."
    )
