"""Dışarıdan gelen içerik (P1 · E, denetim 10-06 H5 + madde 6) — saldırı vakaları.

Zincir: okutulan bir sayfadaki gizli talimat → `read_file` müşterinin token dosyasını okur →
`browse_web` ile GET'e gömüp dışarı yollar (ya da 302 ile Yuki'nin kendi uçlarını okur).
Anthropic doğrudan yolunda araç sonucu maskesiz modele gidiyordu.

🔴 Sahte sırlar kaynakta parça parça kurulur (gitleaks + vault sır süzgeci kaynakta eşleşmesin);
hiçbiri gerçek değil. Testler maskeleyici çıktısını basmaz, yalnız `in` ile bakar.
"""
from __future__ import annotations

import httpx
import pytest

from app.services import credential_scrubber
from app.services.tools import files, network

# ── sahte sırlar (çalışma anında kurulur) ────────────────────────────────────
GSK = "gsk" + "_" + "Ab3" * 18
AIZA = "AI" + "za" + "Sy" + "B" * 33
SK_ANT = "sk-" + "ant-" + "api03-" + "Cd4_" * 12
GHP = "gh" + "p_" + "E5f" * 12
TELEGRAM = "7" + "12345678" + ":" + "AAH" + "g7" * 16
REFRESH = "1//" + "0g" + "Hi8" * 14
CLIENT_SECRET = "GOC" + "SPX-" + "Jk9" * 9
GENEL = "s3cr3t" + "Deger" * 4

SIRLAR = [GSK, AIZA, SK_ANT, GHP, TELEGRAM, REFRESH, CLIENT_SECRET, GENEL]


# ═══ E4 · maskeleyici ═══════════════════════════════════════════════════════
@pytest.mark.parametrize("metin, sir", [
    ('{"api_key": "%s"}' % GENEL, GENEL),
    ('{"refresh_token": "%s", "token_uri": "https://oauth2.googleapis.com/token"}' % REFRESH, REFRESH),
    ('{"installed": {"client_secret": "%s"}}' % CLIENT_SECRET, CLIENT_SECRET),
    ("{'access_token': '%s'}" % GENEL, GENEL),
    ("anahtarım şu: %s tamam" % GSK, GSK),
    ("google: %s" % AIZA, AIZA),
    ("claude anahtarı %s" % SK_ANT, SK_ANT),
    ("github %s" % GHP, GHP),
    ("TELEGRAM_BOT_TOKEN=%s" % TELEGRAM, TELEGRAM),
    ("bot: %s çalışıyor" % TELEGRAM, TELEGRAM),
    ("GROQ_API_KEY=%s" % GSK, GSK),
    ("hf_token: %s" % GENEL, GENEL),
], ids=lambda v: "vaka" if isinstance(v, str) else None)
def test_maskeleyici_json_ve_onekli_anahtar(metin, sir):
    assert sir not in credential_scrubber.scrub(metin)


@pytest.mark.parametrize("metin", [
    '{"max_tokens": 1024, "input_tokens": 12345678}',
    "Bu bir token örneği değil, yalnız düz cümle.",
    "skor: 1234567890:42 (saat damgası değil)",
])
def test_maskeleyici_masum_metni_bozmaz(metin):
    assert credential_scrubber.scrub(metin) == metin


# ═══ E1 · read_file okuma tarafı hassas desen ════════════════════════════════
HASSAS = [
    ".env", "proje/.env.local", ".ssh/id_ed25519", ".gnupg/private-keys-v1.d/a.key",
    ".config/alice-ai/planner_tokens.json", ".config/alice-ai/oturum-anahtari",
    ".config/alice-ai/license.key", ".aws/credentials", ".git-credentials", ".netrc",
    ".config/gh/hosts.yml", ".docker/config.json", ".kube/config", "sertifika/sunucu.pem",
    ".mozilla/firefox/x.default/logins.json", ".config/google-chrome/Default/Cookies",
    ".local/share/keyrings/login.keyring", "indirilenler/client_secret_123.apps.json",
    ".password-store/banka.gpg",
]


@pytest.mark.parametrize("goreli", HASSAS)
def test_read_file_hassas_dosyayi_okumaz(tmp_path, goreli):
    p = tmp_path / goreli
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text("GIZLI_ICERIK_" + GENEL, encoding="utf-8")
    sonuc = files.read_file(str(p))
    assert GENEL not in sonuc and sonuc.startswith("Hata")


def test_diff_files_de_hassas_dosyayi_okumaz(tmp_path):
    a = tmp_path / ".env"
    a.write_text("A=" + GENEL, encoding="utf-8")
    b = tmp_path / "bos.txt"
    b.write_text("", encoding="utf-8")
    assert GENEL not in files.diff_files(str(a), str(b))


def test_read_file_hassas_dosyaya_symlink_ile_de_okumaz(tmp_path):
    hedef = tmp_path / ".ssh" / "id_rsa"
    hedef.parent.mkdir()
    hedef.write_text(GENEL, encoding="utf-8")
    bag = tmp_path / "masum.txt"
    bag.symlink_to(hedef)
    assert GENEL not in files.read_file(str(bag))


@pytest.mark.parametrize("goreli", ["notlar/alisveris.txt", "proje/README.md", "env_ornek.txt",
                                    "proje/.env.example", "kod/token_sayaci.py"])
def test_read_file_siradan_dosyayi_okur(tmp_path, goreli):
    p = tmp_path / goreli
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text("merhaba dünya", encoding="utf-8")
    assert files.read_file(str(p)) == "merhaba dünya"


# ═══ E2 · browse_web her yönlendirmede özel ağ kapısı ════════════════════════
DIS = "http://93.184.216.34"          # global adres (IP yazılı → DNS yok)


@pytest.fixture
def upstream(monkeypatch):
    yanitlar: dict[str, httpx.Response] = {}
    istenen: list[str] = []

    def isle(req: httpx.Request) -> httpx.Response:
        istenen.append(str(req.url))
        return yanitlar.get(str(req.url), httpx.Response(404))

    gercek = httpx.AsyncClient

    def sahte(*a, **k):
        k["transport"] = httpx.MockTransport(isle)
        return gercek(*a, **k)

    monkeypatch.setattr(httpx, "AsyncClient", sahte)
    network._browse_cache.clear()
    yield yanitlar, istenen
    network._browse_cache.clear()


HTML = {"content-type": "text/html; charset=utf-8"}
UZUN = "<html><title>T</title><body><p>" + "gizli yerel içerik " * 10 + "</p></body></html>"


@pytest.mark.parametrize("hedef", ["http://127.0.0.1:8791/api/settings", "http://localhost:8791/",
                                   "http://192.168.1.1/", "http://169.254.169.254/latest/meta-data/",
                                   "http://[::1]:8791/", "http://[::ffff:127.0.0.1]:8791/", "10.0.0.5"])
async def test_browse_web_dogrudan_yerel_hedefi_acmaz(upstream, hedef):
    yanitlar, istenen = upstream
    yanitlar[hedef] = httpx.Response(200, headers=HTML, text=UZUN)
    sonuc = await network.browse_web(hedef)
    assert "gizli yerel" not in sonuc and istenen == []


async def test_browse_web_yonlendirmeyle_yerele_inmez(upstream):
    yanitlar, istenen = upstream
    yanitlar[f"{DIS}/r"] = httpx.Response(302, headers={"location": "http://127.0.0.1:8791/api/settings"})
    yanitlar["http://127.0.0.1:8791/api/settings"] = httpx.Response(200, headers=HTML, text=UZUN)
    sonuc = await network.browse_web(f"{DIS}/r")
    assert "gizli yerel" not in sonuc
    assert not any("127.0.0.1" in u for u in istenen)


async def test_browse_web_dis_yonlendirmeyi_izler(upstream):
    yanitlar, _ = upstream
    yanitlar[f"{DIS}/a"] = httpx.Response(301, headers={"location": "/b"})
    yanitlar[f"{DIS}/b"] = httpx.Response(200, headers=HTML, text=UZUN.replace("gizli yerel", "dış"))
    sonuc = await network.browse_web(f"{DIS}/a")
    assert "dış içerik" in sonuc


async def test_browse_web_yonlendirme_dongusu_biter(upstream):
    yanitlar, istenen = upstream
    yanitlar[f"{DIS}/d"] = httpx.Response(302, headers={"location": f"{DIS}/d"})
    sonuc = await network.browse_web(f"{DIS}/d")
    assert sonuc.startswith("Hata") and len(istenen) <= 6


# ═══ E3 · Anthropic doğrudan yolunda araç sonucu maskelenir ══════════════════
async def test_anthropic_yolunda_arac_sonucu_maskelenir(monkeypatch):
    import types
    import anthropic

    from app.services import llm
    import app.services.tools as tools_pkg

    giden: list = []

    class _Blok:
        def __init__(self, **k):
            self.__dict__.update(k)

    class _Akis:
        """Gerçek SDK gibi: önce metin akar, sonra aynı yanıt `get_final_message` ile okunur."""

        def __init__(self, yanit):
            self.yanit = yanit

        async def __aenter__(self):
            async def _metin():
                for b in self.yanit.content:
                    if b.type == "text":
                        yield b.text
            self.text_stream = _metin()
            return self

        async def get_final_message(self):
            return self.yanit

        async def __aexit__(self, *a):
            return False

    class _Mesajlar:
        def __init__(self):
            self.n = 0

        def stream(self, **k):
            self.n += 1
            giden.append(k["messages"])
            if self.n == 1:
                return _Akis(types.SimpleNamespace(stop_reason="tool_use", content=[
                    _Blok(type="tool_use", id="t1", name="read_file", input={"path": "~/x.json"})]))
            return _Akis(types.SimpleNamespace(stop_reason="end_turn",
                                               content=[_Blok(type="text", text="bitti")]))

    class _Istemci:
        def __init__(self, **k):
            self.messages = _Mesajlar()

    async def sahte_arac(_ad, _arg):
        return '{"refresh_token": "%s", "groq": "%s"}' % (REFRESH, GSK)

    monkeypatch.setattr(anthropic, "AsyncAnthropic", _Istemci)
    monkeypatch.setattr(tools_pkg, "call_tool", sahte_arac)
    monkeypatch.setattr(llm._lp, "anahtar", lambda _s: "sahte-anahtar")

    async for _ in llm._stream_anthropic("sistem", [], "dosyayı oku"):
        pass

    dokum = repr(giden)
    assert "tool_result" in dokum, "araç sonucu modele hiç gitmedi — test kurgusu bozuk"
    for sir in (REFRESH, GSK):
        assert sir not in dokum
