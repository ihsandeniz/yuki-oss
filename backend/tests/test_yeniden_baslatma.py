"""Güvenli yeniden başlatma düğmesi — sözleşmesi bozulmasın (2026-09-08).

geliştirici: *"Sağlık kısmına ve diğer alanlara güvenli ve sağlıklı yeniden başlatma
butonu koyalım — herhangi bir ayarı değiştirdikten sonra onu kullanabilirler."*

Neden gerekliydi: ürün `YUKI_RELOAD=false` ile koşar (paketlenmiş kurulum
read-only), yani ayarların çoğu ancak süreç yeniden başlayınca uygulanır. Arayüz
bunu *"yeniden başlatma gerekli"* diye SÖYLÜYOR ama yapacak bir yol vermiyordu.

Bu dosya davranışı değil **sözleşmeyi** korur; üç şey kolayca ve sessizce bozulur:

1. Düğme tarayıcıda da görünür hâle gelirse → çalışmayan düğme. Backend sürecini
   Electron `spawn` ettiği için `/ui` tarayıcıdan açıldığında yeniden başlatma
   teknik olarak mümkün DEĞİLDİR. Bu üründe "ilan edilen ≠ uygulanan" bir kez
   ciddi kusur üretti (LİSANS paneli olmayan özellikleri "sende açık" diyordu).
2. Güvenlik kapısı düşerse → sürmekte olan indirme kesilir, kullanıcı 16-276 MB'ı
   baştan indirir.
3. İkinci bir kopya yazılırsa → iki uygulama yolu ayrışır (`surum.js` dersi).
"""

from __future__ import annotations

from pathlib import Path

KOK = Path(__file__).resolve().parents[2]
PRELOAD = KOK / "electron" / "preload.js"
UYGULAMA = KOK / "electron" / "uygulama.js"
MM = KOK / "electron" / "model-manager.js"
INTRO = KOK / "frontend" / "js" / "intro-sequences.js"
INDEX = KOK / "frontend" / "index.html"


def _oku(p: Path) -> str:
    return p.read_text(encoding="utf-8")


def test_preload_koprusu_var() -> None:
    s = _oku(PRELOAD)
    assert "yukiSistem" in s, "renderer'a yeniden başlatma köprüsü açılmamış"
    assert "sistem:yeniden-baslat-durum" in s, "önce-sor kanalı yok"
    assert "sistem:yeniden-baslat" in s


def test_ipc_yetkisiz_kaynagi_reddediyor() -> None:
    """Tüm IPC işleyicilerinin ortak kuralı — yenisi onu atlamasın."""
    s = _oku(UYGULAMA)
    blok = s[s.index("ipcMain.handle('sistem:yeniden-baslat'"):]
    blok = blok[: blok.index("});") + 3]
    assert "_isTrustedSender" in blok, (
        "yeniden başlatma kanalı gönderen denetimi yapmıyor — diğer 15 kanalın "
        "hepsinde var"
    )


def test_engel_varken_yeniden_baslatilmiyor() -> None:
    """"Güvenli" bir slogan değil, kapı."""
    s = _oku(UYGULAMA)
    assert "_yenidenBaslatmaEngelleri" in s, "güvenlik kapısı yok"
    blok = s[s.index("ipcMain.handle('sistem:yeniden-baslat'"):]
    blok = blok[: blok.index("app.relaunch()")]
    assert "engeller.length" in blok, (
        "engel denetimi relaunch'tan ÖNCE yapılmıyor — indirme yarıda kesilir"
    )


def test_engel_kaynagi_aktif_indirmeler() -> None:
    s = _oku(UYGULAMA)
    assert "aktifIndirmeler()" in s, "sürmekte olan indirme engel sayılmıyor"
    mm = _oku(MM)
    assert "aktifIndirmeler()" in mm, "model yöneticisinde karşılığı yok"
    assert "_active.keys()" in mm, (
        "`_active` bir Map — `Array.from(map)` id değil [id, deger] çifti döndürür "
        "ve kullanıcıya '[object Object]' gösterilir (ilk yazımda bu oldu)"
    )


def test_tarayicida_dugme_gosterilmiyor() -> None:
    """⚠️ 2026-09-19 (FAZ 3 · Dalga 2 · Blok 5): iddia DEVREDİLDİ, gevşetilmedi.

    Cümle artık kaynakta değil sözlükte (`saglik.restart-yalniz-masaustu`).
    Ham metni aramaya devam etmek testi kırmızıda tutardı; metni sözlükten
    okumak ise iddiayı GÜÇLENDİRİYOR — sebep cümlesinin İngilizce müşteriye de
    ulaştığını artık bu kapı denetliyor. (Çalışmayan bir düğmeyi gizleyip sebebi
    yazmamak, "ilan edilen ≠ uygulanan" kusurunun kendisidir; o sebep tek dilde
    kalırsa İngilizce müşteri için hiç yazılmamış olur.)
    """
    from yardim import sozluk

    s = _oku(INTRO)
    assert "_yenidenBaslatDestekli" in s, "Electron/tarayıcı ayrımı yapılmıyor"
    blok = s[s.index("window.yenidenBaslatBolumu"):]
    blok = blok[: blok.index("window.yenidenBaslatSeridi")]

    anahtar = "saglik.restart-yalniz-masaustu"
    assert f"t('{anahtar}')" in blok, (
        "tarayıcıda sebep yazılmıyor — çalışmayan düğme gösterilir ya da "
        "hiçbir açıklama olmadan kaybolur"
    )
    for dil in ("tr", "en"):
        metin = sozluk(dil).get(anahtar, "")
        assert metin, f"{dil} sözlüğünde '{anahtar}' yok"
        assert "<b>" in metin, (
            f"{dil}: sebep cümlesi vurgusunu kaybetmiş — 'masaüstü uygulaması' "
            "kısmı göze çarpmalı"
        )


def test_tek_uretici_iki_kap() -> None:
    """Sağlık odası ve ayar şeridi AYNI fonksiyonu çağırmalı."""
    s = _oku(INTRO)
    assert s.count("window.yenidenBaslatBolumu = ") == 1, "üretici çoğaltılmış"
    assert "yenidenBaslatBolumu('sag-yeniden-baslat')" in s, "Sağlık odasına bağlı değil"
    assert "yenidenBaslatBolumu('yb-serit'" in s, "ayar şeridine bağlı değil"


def test_serit_yalniz_gerektiginde() -> None:
    """Her kaydetmede çıkan şerit gürültüdür; gürültü okunmaz olur."""
    s = _oku(INTRO)
    assert "if(d.needs_restart) yenidenBaslatSeridi();" in s, (
        "şerit `needs_restart` koşuluna bağlı değil"
    )


def test_saglik_odasinda_kap_var() -> None:
    assert 'id="sag-yeniden-baslat"' in _oku(INDEX), "Sağlık odasında kap yok"


def test_bolum_denetimden_bagimsiz_ciziliyor() -> None:
    """Oturum kilitliyken denetim 401 alır; düğme yine görünmeli.

    Yeniden başlatma Electron IPC'sinden geçer, backend auth'una hiç uğramaz —
    kilitli kullanıcı tam da işine yarayacak düğmeyi görebilmeli.
    """
    s = _oku(INTRO)
    blok = s[s.index("window.saglikTara"):]
    blok = blok[: blok.index("var r=await af('/api/self-check')")]
    assert "yenidenBaslatBolumu('sag-yeniden-baslat')" in blok, (
        "bölüm self-check çağrısından SONRA çiziliyor — 401'de erken `return` "
        "olduğu için kilitli oturumda düğme hiç görünmez"
    )
