"""UI-F001 (H9, 10-06 güvenlik denetimi) — sohbet geçmişi onaysız ve kalıcı siliniyordu.

Çöp kutusu, palet "temizle" ve Ctrl+L (yazarken bile) `clearHistory()`'yi çağırıyor,
o da tek adımda `POST /api/chat/clear-messages` + `innerHTML = ''` yapıyordu.

Bu dosya DAVRANIŞI gerçek Chromium'da ölçer (`bildirim.js` + `gecmis-temizle.js`,
sunucu isteği sahte): onay sorulmadan istek gitmez · vazgeç hiçbir şey silmez ·
geri al düğümleri aynen geri koyar ve istek HİÇ gitmez · süre dolunca tek istek gider ·
istek düşerse mesajlar geri gelir + hata bildirimi. Ctrl+L'nin yazarken tetiklenmemesi
ve üç giriş yolunun aynı fonksiyondan geçmesi kaynakta denetlenir.

Mutasyon (2026-10-09): `clearHistory` eski gövdesine döndürülünce statik testler kırmızı;
`iste()` doğrudan `sil()` çağırınca onay testi kırmızı.
"""
from __future__ import annotations

import re
from pathlib import Path

import pytest

from yardim import yorumsuz

pw = pytest.importorskip("playwright.sync_api")

KOK = Path(__file__).resolve().parents[2]
JS = KOK / "frontend" / "js"
CORE = JS / "core.js"

SAYFA = """<!doctype html><html><body>
<textarea id="msg-input"></textarea>
<div id="messages"><div class="msg">bir</div><div class="msg">iki</div></div>
</body></html>"""

KUR = """() => {
  window.istekler = [];
  window.gonderSonucu = { ok: true, status: 200 };
  window.gonder = (keepalive) => { window.istekler.push(keepalive); return Promise.resolve(window.gonderSonucu); };
}"""


@pytest.fixture(scope="module")
def tarayici():
    with pw.sync_playwright() as p:
        try:
            b = p.chromium.launch()
        except Exception as e:  # tarayıcı kurulu değilse ölçülemedi — yeşil SAYILMAZ
            pytest.skip(f"chromium açılamadı: {e}")
        yield b
        b.close()


@pytest.fixture
def sayfa(tarayici):
    s = tarayici.new_page()
    s.clock.install()
    s.set_content(SAYFA)
    s.add_script_tag(path=str(JS / "bildirim.js"))
    s.add_script_tag(path=str(JS / "gecmis-temizle.js"))
    s.evaluate(KUR)
    yield s
    s.close()


def mesaj_sayisi(s):
    return s.locator("#messages .msg").count()


def dugme(s, ad):
    return s.locator(".bildirim-eylem", has_text=ad)


def test_iste_onay_sorar_istek_gondermez(sayfa):
    sayfa.evaluate("window.gecmisTemizle.iste(window.gonder)")
    assert dugme(sayfa, "sohbet.temizle-evet").count() == 1
    assert dugme(sayfa, "sohbet.temizle-vazgec").count() == 1
    assert mesaj_sayisi(sayfa) == 2
    sayfa.clock.run_for(60_000)          # soru kendiliğinden kapanır = vazgeç
    assert sayfa.evaluate("window.istekler.length") == 0
    assert mesaj_sayisi(sayfa) == 2


def test_vazgec_hicbir_sey_silmez(sayfa):
    sayfa.evaluate("window.gecmisTemizle.iste(window.gonder)")
    dugme(sayfa, "sohbet.temizle-vazgec").click()
    sayfa.clock.run_for(10_000)
    assert mesaj_sayisi(sayfa) == 2
    assert sayfa.evaluate("window.istekler.length") == 0


def test_geri_al_dugumleri_geri_koyar_istek_hic_gitmez(sayfa):
    sayfa.evaluate("window.gecmisTemizle.iste(window.gonder)")
    dugme(sayfa, "sohbet.temizle-evet").click()
    assert mesaj_sayisi(sayfa) == 0                      # ekrandan kalktı
    assert dugme(sayfa, "sohbet.geri-al").count() == 1
    sayfa.clock.run_for(4_000)                           # 5 sn dolmadan
    dugme(sayfa, "sohbet.geri-al").click()
    assert sayfa.locator("#messages .msg").all_inner_texts() == ["bir", "iki"]
    sayfa.clock.run_for(10_000)
    assert sayfa.evaluate("window.istekler.length") == 0


def test_sure_dolunca_tek_istek_gider(sayfa):
    sayfa.evaluate("window.gecmisTemizle.iste(window.gonder)")
    dugme(sayfa, "sohbet.temizle-evet").click()
    sayfa.clock.run_for(4_900)
    assert sayfa.evaluate("window.istekler.length") == 0
    sayfa.clock.run_for(200)
    assert sayfa.evaluate("window.istekler") == [False]
    assert mesaj_sayisi(sayfa) == 0


def test_istek_duserse_mesajlar_geri_gelir_hata_gorunur(sayfa):
    sayfa.evaluate("window.gonderSonucu = { ok: false, status: 500 }")
    sayfa.evaluate("window.gecmisTemizle.iste(window.gonder)")
    dugme(sayfa, "sohbet.temizle-evet").click()
    sayfa.clock.run_for(5_100)
    sayfa.wait_for_selector('.bildirim[data-tip="hata"]')
    assert mesaj_sayisi(sayfa) == 2
    assert "sohbet.temizlenemedi" in sayfa.locator('.bildirim[data-tip="hata"]').inner_text()


def test_sayfa_kapanirken_bekleyen_silme_keepalive_ile_gider(sayfa):
    sayfa.evaluate("window.gecmisTemizle.iste(window.gonder)")
    dugme(sayfa, "sohbet.temizle-evet").click()
    sayfa.evaluate("window.dispatchEvent(new Event('pagehide'))")
    assert sayfa.evaluate("window.istekler") == [True]


def test_bos_gecmiste_soru_yok(sayfa):
    sayfa.evaluate("document.getElementById('messages').innerHTML = ''")
    sayfa.evaluate("window.gecmisTemizle.iste(window.gonder)")
    assert dugme(sayfa, "sohbet.temizle-evet").count() == 0
    assert sayfa.evaluate("window.istekler.length") == 0


# ── kaynak denetimi: üç giriş yolu + Ctrl+L ─────────────────────────────

def _core():
    return yorumsuz(CORE.read_text(encoding="utf-8"))


def test_clear_history_dogrudan_silmez():
    m = re.search(r"function clearHistory\(\)\s*\{(.*?)\n\}", _core(), re.S)
    assert m, "clearHistory bulunamadı"
    govde = m.group(1)
    assert "gecmisTemizle.iste" in govde
    assert "innerHTML" not in govde, "clearHistory ekranı doğrudan temizliyor (onaysız)"


def test_ctrl_l_yazarken_tetiklenmez():
    m = re.search(r"e\.key === 'l'([^{]*)\{", _core())
    assert m, "Ctrl+L dalı bulunamadı"
    assert "!inInput" in m.group(1), "Ctrl+L metin kutusunda yazarken de geçmişi temizliyor"


def test_uc_giris_yolu_clear_history_uzerinden():
    html = (KOK / "frontend" / "index.html").read_text(encoding="utf-8")
    assert 'onclick="clearHistory()"' in html                       # çöp kutusu
    assert "eylem: () => clearHistory()" in _core()                 # palet 'temizle'
    assert "clear-messages" not in re.sub(r"function clearHistory\(\).*?\n\}", "", _core(), flags=re.S), \
        "clear-messages clearHistory dışından da çağrılıyor — onay atlanır"
