"""Kaçırılan araç uyarısı testleri.

En büyük risk işlevsizlik değil **gürültü**: yanlış zamanda ya da çok sık
konuşursa kullanıcı kartı görmezden gelmeye alışır. Bu yüzden testlerin çoğu
"ne zaman SUSMALI" sorusunu kapatır.
"""

import pytest

from app.services import arac_ipucu as ai


@pytest.fixture(autouse=True)
def temiz():
    """Her test kendi susturma durumuyla başlasın."""
    ai._son_hatirlatma.clear()
    yield
    ai._son_hatirlatma.clear()


def test_arac_KULLANILDIYSA_susar():
    """En önemli kapı: iş zaten yapıldıysa hatırlatacak bir şey yok."""
    assert ai.ipucu_bul("yapılacaklarımı listele", arac_cagri_sayisi=1) is None
    assert ai.ipucu_bul("yapılacaklarımı listele", arac_cagri_sayisi=3) is None


def test_arac_kullanilmadiysa_ve_kalip_tutuyorsa_hatirlatir():
    ip = ai.ipucu_bul("yapılacaklarım neydi acaba", arac_cagri_sayisi=0)
    assert ip is not None
    assert "list_todos" in ip["araclar"]


def test_ayni_kural_yakin_zamanda_TEKRAR_etmez():
    """Israr etmemeli — aynı kural susma penceresi içinde bir kez konuşur."""
    ilk = ai.ipucu_bul("notlarımda ne var", arac_cagri_sayisi=0)
    ikinci = ai.ipucu_bul("notlarımda ne var", arac_cagri_sayisi=0)
    assert ilk is not None
    assert ikinci is None


def test_cok_kisa_mesajda_kural_aranmaz():
    """'tamam', 'peki' gibi mesajlarda ipucu gürültüdür."""
    assert ai.ipucu_bul("tamam", arac_cagri_sayisi=0) is None
    assert ai.ipucu_bul("ok", arac_cagri_sayisi=0) is None


def test_alakasiz_mesaj_ipucu_uretmez():
    """Yanlış pozitif, ipucunu değersizleştiren asıl tehlikedir."""
    for mesaj in [
        "bugün nasılsın, biraz sohbet edelim mi",
        "bana bir şiir yaz lütfen uzun olsun",
        "teşekkür ederim çok yardımcı oldun",
    ]:
        assert ai.ipucu_bul(mesaj, arac_cagri_sayisi=0) is None, mesaj


def test_turkce_ek_almis_bicimler_yakalanir():
    """🔴 Türkçe kök ek alınca değişir (not→notlarım, takvim→takvime).

    Kalıp yalnız kökü tutarsa gerçek cümlelerin çoğunu kaçırır — vault'ta
    aynı hata ölçülmüştü (`\\bgrafik` deseni 'grafiği'yi yakalamıyordu).
    """
    vakalar = [
        ("bunu takvime ekler misin", "takvim"),
        ("notlarıma bak bakalım", "not-oku"),
        ("bu hafta kaç antrenman yaptım", "fitness"),
    ]
    for mesaj, beklenen_kural in vakalar:
        ai._son_hatirlatma.clear()
        ip = ai.ipucu_bul(mesaj, arac_cagri_sayisi=0)
        assert ip is not None, f"yakalanmadı: {mesaj}"
        assert ip["kural"] == beklenen_kural, f"{mesaj} → {ip['kural']}"


def test_taze_acilmis_makinede_de_konusur(monkeypatch):
    """Açılıştan sonraki ilk 30 dakikada susmamalı: `time.monotonic()` taze
    makinede küçüktür; "hiç söylenmedi" için 0.0 varsayılanı uyarıyı susturur."""
    monkeypatch.setattr(ai.time, "monotonic", lambda: 12.0)   # açılıştan 12 sn sonra
    ip = ai.ipucu_bul("yapılacaklarım neydi acaba", arac_cagri_sayisi=0)
    assert ip is not None, "taze açılmış makinede dedektör sustu"
    assert ip["kural"] == "todo-listele"


def test_taze_makinede_de_ISRAR_etmez(monkeypatch):
    """Düzeltme susturmayı bozmamalı — ilk konuşur, ikincisinde susar."""
    monkeypatch.setattr(ai.time, "monotonic", lambda: 12.0)
    assert ai.ipucu_bul("notlarımda ne var", arac_cagri_sayisi=0) is not None
    assert ai.ipucu_bul("notlarımda ne var", arac_cagri_sayisi=0) is None


def test_tablodaki_araclar_dispatcher_da_GERCEKTEN_var():
    """Kural var olmayan araca işaret ederse ipucu yalan söyler.

    Araç yeniden adlandırıldığında tablo sessizce çürür; kart "şunu
    yapabilirim" der ama o araç yoktur.
    """
    from app.services.tools.dispatcher import TOOLS
    mevcut = {(t.get("function") or {}).get("name") for t in TOOLS}
    for k in ai._yukle():
        olu = [a for a in k["araclar"] if a not in mevcut]
        assert not olu, f"kural '{k['ad']}' ölü araca işaret ediyor: {olu}"


def test_tablo_bozuksa_sessizce_kapanir(monkeypatch, tmp_path):
    """Ölçüm/yardımcı katman, ana akışı ASLA bozmamalı."""
    monkeypatch.setattr(ai, "_TABLO_YOLU", tmp_path / "yok.json")
    monkeypatch.setattr(ai, "_kurallar", None)
    assert ai.ipucu_bul("yapılacaklarım neydi", arac_cagri_sayisi=0) is None


def test_her_kuralin_iki_dilde_metni_var():
    """Kart metni `ipucu.<kural>` anahtarıyla arayüz dilinde kurulur; anahtar
    eksikse kart yedek Türkçe metne düşer ve İngilizce arayüzde Türkçe konuşur."""
    from pathlib import Path
    kok = Path(__file__).resolve().parents[2] / "frontend/js/diller"
    for dil in ("tr", "en"):
        metin = (kok / f"{dil}.js").read_text(encoding="utf-8")
        for k in ai._yukle():
            assert f"'ipucu.{k['ad']}':" in metin, f"{dil}.js: ipucu.{k['ad']} yok"
        assert "'beceri.ipucu.banner':" in metin, f"{dil}.js: kart başlığı yok"


def test_kart_tipi_onyuzde_tanimli():
    from pathlib import Path
    js = (Path(__file__).resolve().parents[2] / "frontend/modes/skill-card.js").read_text(encoding="utf-8")
    assert "ipucu:" in js and "beceri.ipucu.banner" in js, "skill-card.js 'ipucu' tipini tanımıyor"


def test_sohbet_akisi_uyariyi_cagiriyor():
    """Yapı testi: araçlı ana yol tur sonunda `belki_hatirlat`'ı araç sayısıyla çağırmalı."""
    import inspect
    from app.services import llm
    kaynak = inspect.getsource(llm.chat_stream)
    assert "belki_hatirlat(message, runner.total_tool_calls)" in kaynak
