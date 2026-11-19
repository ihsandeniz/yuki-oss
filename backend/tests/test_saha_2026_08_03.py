"""2026-08-03 saha raporu regresyonları — Windows 10, gerçek müşteri makinesi.

Şikâyetler (hata-gunlugu.jsonl + ipek'ın gözlemi):
  ① "genel bazı ücretsiz modeller çalışmıyor"
  ② "pro ve ultra'da PLAN sekmesi geliyor ama Yuki'nin bundan haberi yok"
  ③ "erişim yapamıyor, araçlarını listelemiyor"

Bu dosya her birinin KÖK NEDENİNİ kilitler; testler ağa çıkmaz.
"""
from __future__ import annotations

import asyncio

import pytest


# ── ② PLAN sekmesi: hayalet sekmeler ────────────────
def test_sekme_tablosu_yalnizca_uruntteki_sekmeler():
    """`_TABS` kişisel sürümden kopyalanmıştı: map/finance/drive/faces/nmap.

    Bu sekmeler satılan üründe YOK → `list_tabs` müşteriye olmayan sekmeleri
    sayıyor, `switch_tab("harita")` "geçildi" diye yalan söylüyordu.
    """
    from app.services.tools import ui_tools
    assert set(ui_tools._TABS) == {"chat", "planner", "hq"}
    # Kişisel sürümün sekmeleri takma ad olarak da kalmamalı
    for hayalet in ("harita", "finans", "drive", "yüz", "sce", "nmap", "borsa"):
        assert ui_tools._resolve(hayalet) is None, f"'{hayalet}' hâlâ çözülüyor"


def test_gecersiz_sekme_yalan_soylemez():
    from app.services.tools import ui_tools
    sonuc = asyncio.run(ui_tools.switch_tab("harita"))
    assert "geçildi" not in sonuc.lower()
    assert "yalnız" in sonuc.lower() or "geçersiz" in sonuc.lower()


def test_plan_kapaliyken_sebebini_soyler(monkeypatch):
    """PLAN kapalıyken araç sessizce başarısız olmak yerine sebep söylemeli.

    Açık kaynakta satış kademesi yok: sebep "Pro gerekir" değil "bu kurulumda kapalı"."""
    from app.services.tools import ui_tools
    monkeypatch.setattr(ui_tools, "_kademe_izin_veriyor", lambda c: c != "planner")

    sonuc = asyncio.run(ui_tools.switch_tab("plan"))
    assert "geçildi" not in sonuc.lower()
    assert "kapalı" in sonuc.lower() and "pro" not in sonuc.lower()

    liste = asyncio.run(ui_tools.list_tabs())
    assert "kapalı" in liste.lower()


def test_switch_tab_semasi_planner_i_taniyor():
    """Araç şemasının açıklaması PLAN'dan hiç söz etmiyordu → model bilmiyordu."""
    from app.services.tools.dispatcher import TOOLS
    sema = next(t for t in TOOLS if t["function"]["name"] == "switch_tab")
    aciklama = sema["function"]["description"].lower()
    assert "planner" in aciklama and "plan" in aciklama


# ── ③ Araç envanteri: prompt 20 araçlık dünyada kalmıştı ────────────
def test_sistem_promptu_acik_araclari_sayiyor(monkeypatch):
    """Prompt, o anki lisansta AÇIK olan araçları ada ada saymalı.

    ⚠️ Bu testin ilk hâli YALANDI (2026-08-03, doğrulama turunda yakalandı):
    varsayılan test ortamı Free (20 araç) ve o 20 adın hepsi promptun SABİT
    "Niyet → Araç" örneklerinde zaten geçiyor → envanter tamamen kapalıyken
    bile yeşil yanıyordu. Ders: bir testin kırmızı yanabildiğini görmeden
    "kanıtlandı" sayma. Artık statik metinde ASLA geçmeyecek sentinel adlar
    kullanılıyor.
    """
    from app import config
    import app.services.tools as tools_pkg

    sahte = [
        {"type": "function", "function": {"name": "zzz_sentinel_arac_bir"}},
        {"type": "function", "function": {"name": "zzz_sentinel_arac_iki"}},
    ]
    monkeypatch.setattr(tools_pkg, "get_active_tools", lambda: sahte)

    prompt = config.build_system_prompt()
    assert "zzz_sentinel_arac_bir" in prompt
    assert "zzz_sentinel_arac_iki" in prompt
    assert "2 araç" in prompt  # sayı da geçmeli ("Şu an sende AÇIK olan N araç")


def test_envanter_gercek_arac_setini_kapsiyor(monkeypatch):
    """Gerçek araç kaydıyla: statik örneklerde GEÇMEYEN adlar da promptta mı."""
    from app import config
    import app.services.tools as tools_pkg
    from app.services.tools.dispatcher import TOOLS

    ultra = sorted(t["function"]["name"] for t in TOOLS)
    monkeypatch.setattr(
        tools_pkg, "get_active_tools",
        lambda: [{"type": "function", "function": {"name": n}} for n in ultra],
    )
    prompt = config.build_system_prompt()
    # Bu üçü sabit "Niyet → Araç" örneklerinde YOK — yalnız envanterden gelebilir
    for ad in ("memory_search", "take_screenshot", "wiki_write"):
        assert ad in ultra
        assert ad in prompt, f"{ad} envanterde var ama promptta görünmüyor"


def test_prompt_olmayan_araci_vaat_etmez(monkeypatch):
    """Prompt, o an AÇIK OLMAYAN bir aracı örnek olarak göstermemeli.

    Bu kusuru fix'in kendi ölçümü yakaladı: sekme örneği önce statik listeye
    yazılmıştı → `switch_tab` Free'de yokken bile promptta görünüyordu, yani
    "olmayan yeteneği vaat etme" hatasını düzeltirken aynısı üretilmişti.
    """
    from app import config
    import app.services.tools as tools_pkg
    from app.services.tools.dispatcher import TOOLS

    free = sorted(t["function"]["name"] for t in TOOLS
                  if t["function"]["name"] not in ("switch_tab", "list_tabs"))
    monkeypatch.setattr(
        tools_pkg, "get_active_tools",
        lambda: [{"type": "function", "function": {"name": n}} for n in free],
    )
    prompt = config.build_system_prompt()
    assert "switch_tab" not in prompt
    assert "list_tabs" not in prompt


def test_envanter_kademe_degisince_tazelenir(monkeypatch):
    """Prompt cache'i araç setini imzalamazsa lisans etkinleştirince BAYAT kalır."""
    from app import config
    from app.services import tools as tools_pkg

    tam = tools_pkg.get_active_tools()
    assert len(tam) > 1

    ilk = config.build_system_prompt()
    monkeypatch.setattr(config, "_tool_inventory", lambda: ("\nSADECE: web_search\n", "test-imza"))
    ikinci = config.build_system_prompt()
    assert ikinci != ilk and "SADECE: web_search" in ikinci


# ── ① Boş yanıt: 200 OK ama içerik yok → eskiden tamamen sessizdi ──
class _SahteDelta:
    def __init__(self, content=None, tool_calls=None):
        self.content = content
        self.tool_calls = tool_calls


class _SahteChoice:
    def __init__(self, delta):
        self.delta = delta
        self.finish_reason = None


class _SahteChunk:
    def __init__(self, delta):
        self.choices = [_SahteChoice(delta)]


class _SahteStream:
    """`nvidia/nemotron-nano-9b-v2:free` davranışı: 200 OK, içerik boş, araç yok."""

    def __init__(self, chunks):
        self._chunks = chunks

    def __aiter__(self):
        async def gen():
            for c in self._chunks:
                yield c
        return gen()

    async def close(self):
        pass


@pytest.mark.asyncio
async def test_bos_yanit_sessiz_kalmaz(monkeypatch):
    from app.services import runner as runner_mod

    class _SahteClient:
        base_url = "https://openrouter.ai/api/v1"

        class chat:
            class completions:
                @staticmethod
                async def create(**kw):
                    return _SahteStream([_SahteChunk(_SahteDelta(content=""))])

    class _SahteRouter:
        async def get_client(self):
            return _SahteClient(), "sahte-model"

        def record_success(self, *a, **k):
            pass

        def record_failure(self, *a, **k):
            pass

    monkeypatch.setattr(runner_mod, "get_router", lambda: _SahteRouter(), raising=False)
    import app.services.llm_router as lr
    monkeypatch.setattr(lr, "get_router", lambda: _SahteRouter())

    r = runner_mod.LLMRunner(client=_SahteClient(), model="sahte-model", tools=[], max_steps=2)
    parcalar = [p async for p in r.run([{"role": "user", "content": "selam"}])]

    metin = "".join(parcalar)
    assert metin.strip(), "boş yanıtta kullanıcıya HİÇBİR ŞEY gitmiyor (sessiz ölüm)"
    assert "boş yanıt" in metin.lower()
    assert "anahtar" in metin.lower()  # ne yapacağını söylüyor mu


@pytest.mark.asyncio
async def test_dolu_yanitta_ek_mesaj_eklenmez(monkeypatch):
    """Uyarı yalnız GERÇEKTEN boş olduğunda çıkmalı — normal cevaba bulaşmamalı."""
    from app.services import runner as runner_mod

    class _SahteClient:
        base_url = "https://openrouter.ai/api/v1"

        class chat:
            class completions:
                @staticmethod
                async def create(**kw):
                    return _SahteStream([
                        _SahteChunk(_SahteDelta(content="Merhaba")),
                        _SahteChunk(_SahteDelta(content=" ipek.")),
                    ])

    class _SahteRouter:
        async def get_client(self):
            return _SahteClient(), "sahte-model"

        def record_success(self, *a, **k):
            pass

        def record_failure(self, *a, **k):
            pass

    import app.services.llm_router as lr
    monkeypatch.setattr(lr, "get_router", lambda: _SahteRouter())

    r = runner_mod.LLMRunner(client=_SahteClient(), model="sahte-model", tools=[], max_steps=2)
    metin = "".join([p async for p in r.run([{"role": "user", "content": "selam"}])])
    assert metin == "Merhaba ipek."
    assert "boş yanıt" not in metin.lower()


# ══ İKİNCİ SAHA RAPORU (16c462ae, 2026-08-03 10:24) ═════════════════
# ① control_media Windows'ta playerctl çağırıyordu (Linux'a özel program)
# ② backend log'u okunamıyordu (Türkçe harfler "�", "→" → "→")
# ③ günler önce çözülmüş hatalar raporun başında "güncel" gibi duruyordu


def _sahte_user32(kayit: list):
    class _U32:
        @staticmethod
        def keybd_event(vk, scan, flags, extra):
            kayit.append((vk, flags))
    return _U32()


def test_windows_medya_playerctl_cagirmaz(monkeypatch):
    """Kök neden: playerctl MPRIS/D-Bus'tır — Windows'ta HİÇ yoktur.

    Müşteri "müziği durdur" diyor, komut sessizce düşüyordu. Üstelik `control_media`
    FREE kademesinde satılan 20 araçtan biri.
    """
    import ctypes
    from app.services.tools import media

    cagrilan_kabuk: list = []
    monkeypatch.setattr(media, "_playerctl", lambda c: cagrilan_kabuk.append(c) or "ok")
    monkeypatch.setattr(media.sys, "platform", "win32")

    basilan: list = []
    monkeypatch.setattr(ctypes, "WinDLL", lambda *a, **k: _sahte_user32(basilan), raising=False)

    sonuc = media.control_media("pause")

    assert cagrilan_kabuk == [], f"Windows'ta kabuk komutu çalıştırıldı: {cagrilan_kabuk}"
    assert basilan, "medya tuşu hiç gönderilmedi"
    assert basilan[0][0] == 0xB3, "VK_MEDIA_PLAY_PAUSE beklenirken başka tuş"
    assert len(basilan) == 2, "tuş bas+bırak çifti olmalı (yalnız basılı kalmamalı)"
    assert "hata" not in sonuc.lower()


def test_windows_medya_tuslari_dogru_eslenir(monkeypatch):
    import ctypes
    from app.services.tools import media

    monkeypatch.setattr(media.sys, "platform", "win32")
    beklenen = {
        "next": 0xB0, "prev": 0xB1, "previous": 0xB1, "stop": 0xB2,
        "volume_up": 0xAF, "volume_down": 0xAE, "mute": 0xAD,
        "play": 0xB3, "pause": 0xB3, "play_pause": 0xB3,
    }
    for eylem, vk in beklenen.items():
        basilan: list = []
        monkeypatch.setattr(ctypes, "WinDLL", lambda *a, **k: _sahte_user32(basilan), raising=False)
        media.control_media(eylem)
        assert basilan and basilan[0][0] == vk, f"{eylem} → {vk:#x} bekleniyordu"


def test_windows_play_pause_farkini_gizlemez(monkeypatch):
    """Windows'ta çal/duraklat TEK tuştur. 'Duraklatıldı' deyip toggle basmak yalandır."""
    import ctypes
    from app.services.tools import media

    monkeypatch.setattr(media.sys, "platform", "win32")
    monkeypatch.setattr(ctypes, "WinDLL", lambda *a, **k: _sahte_user32([]), raising=False)
    sonuc = media.control_media("pause")
    assert "tek tuş" in sonuc.lower()


def test_linux_medya_hala_playerctl(monkeypatch):
    """Windows dalı eklenirken Linux yolu bozulmamalı (ipek'ın kendi makinesi)."""
    from app.services.tools import media

    cagrilan: list = []
    monkeypatch.setattr(media, "_playerctl", lambda c: cagrilan.append(c) or "ok")
    monkeypatch.setattr(media.sys, "platform", "linux")
    media.control_media("pause")
    assert cagrilan == ["playerctl pause"]


def test_gecersiz_medya_eylemi_windowsta_da_soylenir(monkeypatch):
    import ctypes
    from app.services.tools import media

    monkeypatch.setattr(media.sys, "platform", "win32")
    monkeypatch.setattr(ctypes, "WinDLL", lambda *a, **k: _sahte_user32([]), raising=False)
    sonuc = media.control_media("teleport")
    assert "geçersiz" in sonuc.lower()


def test_backend_logu_utf8_zorlanir():
    """Windows'ta Python stderr'i cp1254 → Node utf8 sanıp çözüyor → her harf '�'.

    Müşteriden istediğimiz teşhis dosyası okunamaz geliyordu. İki değişken de şart:
    PYTHONUTF8 dosya/argüman katmanı, PYTHONIOENCODING akış katmanı.
    """
    from pathlib import Path
    # Backend'i spawn eden dosyada aranır — 2026-08-03'te gövde `main.js`'ten
    # `uygulama.js`'e taşındı (ASAR'da yalnız önyükleyici kaldı). Dosya adına
    # değil, işi yapan koda bak: aksi hâlde test taşınmayı fark etmeden yeşil kalır.
    electron = Path(__file__).resolve().parents[2] / "electron"
    # 2026-10-08: motor bekçi bayrağıyla `spawn(baslat.komut, …)` üzerinden başlar.
    adaylar = [p for p in electron.glob("*.js")
               if any(k in p.read_text(encoding="utf-8") for k in ("spawn(python", "spawn(baslat.komut"))]
    assert adaylar, "backend'i spawn eden dosya bulunamadı"
    for p in adaylar:
        metin = p.read_text(encoding="utf-8")
        assert "PYTHONIOENCODING: 'utf-8'" in metin, f"{p.name}: PYTHONIOENCODING yok"
        assert "PYTHONUTF8: '1'" in metin, f"{p.name}: PYTHONUTF8 yok"


def test_eski_kayit_gun_etiketi_alir():
    """Çözülmüş eski hata 'şu an bozuk' gibi görünmemeli — yaşı yazılı olsun."""
    from datetime import datetime, timedelta
    from app.services.error_log import _yas_etiketi

    simdi = datetime.now().astimezone()
    assert _yas_etiketi(simdi.isoformat(), simdi) is None, "taze kayıt etiketlenmemeli"
    assert _yas_etiketi((simdi - timedelta(hours=5)).isoformat(), simdi) is None
    etiket = _yas_etiketi((simdi - timedelta(days=2, hours=1)).isoformat(), simdi)
    assert etiket and "2 gün önce" in etiket
    assert _yas_etiketi(None, simdi) is None
    assert _yas_etiketi("bozuk-tarih", simdi) is None
