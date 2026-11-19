"""FAZ 1 — İngilizce dil kaydı (2026-09-18).

Bağlam: ürün İngilizce bir vitrinden $14.99'a satılıyordu ama desteklenen dil
yalnız `tr` + `ja`'ydı — müşteri İngilizce ödeyip tamamen Türkçe bir uygulama
indiriyordu. FAZ 1 dil KAYDINI açar (arayüz metin katmanı FAZ 2-3'tür).

Bu dosya üç şeyi ölçer:
  ① `en` kaydı gerçekten çalışıyor mu (okuma değil ÇALIŞTIRMA ile)
  ② `İngilizce` tuzağı — `.lower()`'ın Türkçe `İ`'de ürettiği ayrı nokta
  ③ bayatlama kapıları — araç şeması ve API listesi kaynaktan türüyor mu
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

BACKEND_DIR = Path(__file__).resolve().parents[1]


@pytest.fixture
def temiz_ayar(tmp_path, monkeypatch):
    """Her test kendi config.user.json'ıyla koşsun (gerçek ayara dokunma).

    PERSONA_VOICES de böylece boş kalır — `_edge_voice_params()` dil
    varsayılanını döndürür, kullanıcı seçimini değil.
    """
    from app import config_manager

    hedef = tmp_path / "config.user.json"
    monkeypatch.setattr(config_manager, "CONFIG_USER_PATH", hedef)
    monkeypatch.setattr(config_manager, "_cache", None)
    return hedef


# --------------------------------------------------------------------------- #
# ① `en` kaydı
# --------------------------------------------------------------------------- #

def test_en_kaydi_var_ve_alanlari_tam():
    """Eksik alan sessiz arıza üretir: `whisper` yoksa STT, `edge_voice` yoksa TTS düşer."""
    from app.config import LANGUAGES

    assert "en" in LANGUAGES, "İngilizce kaydı yok — ürün kendi vitrininin dilini konuşamıyor"
    en = LANGUAGES["en"]
    for alan in ("name", "flag", "edge_voice", "whisper", "prompt_rule"):
        assert en.get(alan), f"LANGUAGES['en']['{alan}'] boş/eksik"
    assert en["whisper"] == "en"


def test_set_language_en_edge_sesini_degistirir(temiz_ayar):
    """🔑 FAZ 1'in ASIL ölçüsü — okuma değil çalıştırma.

    `set_language('en')` sonrası TTS gerçekten İngilizce sese geçmeli. Kayıt
    eklenip `_edge_voice_params()` yine `tr-TR-*` dönseydi kullanıcı İngilizce
    yazan ama Türkçe aksanla okuyan bir asistan alırdı.
    """
    from app.config import set_language, get_language
    from app.services.tts import _edge_voice_params

    onceki = get_language()
    try:
        assert set_language("en", persist=False) is True
        assert get_language() == "en"
        ses = _edge_voice_params()[0]
        assert ses.startswith("en-"), f"dil 'en' ama Edge sesi hâlâ: {ses}"
    finally:
        set_language(onceki, persist=False)


def test_prompt_rule_ingilizce_yazilmis():
    """Her dilin kuralı KENDİ dilindedir; `en` kuralı Türkçe kalsaydı model
    İngilizce isteyen kullanıcıya Türkçe yanıt verirdi (kural prompta girer:
    `_YUKI_BASE.format(language_rule=...)`)."""
    from app.config import LANGUAGES

    kural = LANGUAGES["en"]["prompt_rule"]
    assert kural.isascii(), f"'en' prompt_rule'ü İngilizce değil: {kural!r}"
    assert "English" in kural


# --------------------------------------------------------------------------- #
# ② `İngilizce` tuzağı — ölçüldü 2026-09-18
# --------------------------------------------------------------------------- #

def test_normalize_buyuk_i_tuzagi():
    """`"İngilizce".lower()` → `"i" + U+0307`, `"ingilizce"` DEĞİL.

    Python'un `lower()`'ı noktalı büyük `İ`'yi küçültürken noktayı AYRI bir
    birleştirici kod noktası olarak bırakır. Normalizasyon olmasaydı alias
    sözlüğü ıskalardı. `Türkçe`/`Japonca` bu tuzağa düşmez (baş harfleri T/J) —
    kusur bu yüzden `en` eklenene kadar hiç görünmedi.
    """
    from app.config import _normalize_lang_key

    assert "İngilizce".lower() != "ingilizce", "tuzak kalktıysa bu testin gerekçesi değişti"
    assert _normalize_lang_key("İngilizce") == "ingilizce"
    # Normalizasyon diğer dilleri bozmamalı
    assert _normalize_lang_key("  Türkçe ") == "türkçe"
    assert _normalize_lang_key("日本語") == "日本語"
    assert _normalize_lang_key(None) == ""


@pytest.mark.parametrize(
    "girdi",
    ["en", "EN", "english", "English", "ingilizce", "İngilizce", "  İNGİLİZCE  ", "eng"],
)
def test_serbest_metin_en_olarak_cozulur(girdi, temiz_ayar):
    """Kullanıcı ve LLM bu kelimelerin hepsini yazabilir; hepsi `en` olmalı."""
    from app.config import set_language, get_language

    onceki = get_language()
    try:
        assert set_language(girdi, persist=False) is True, f"çözülemedi: {girdi!r}"
        assert get_language() == "en"
    finally:
        set_language(onceki, persist=False)


def test_gecersiz_dil_hala_reddedilir(temiz_ayar):
    """Normalizasyon kapıyı gevşetmemeli."""
    from app.config import set_language, get_language

    onceki = get_language()
    try:
        for cop in ["", "klingon", "e", "rm -rf /", None]:
            assert set_language(cop, persist=False) is False, f"kabul edildi: {cop!r}"
        assert get_language() == onceki, "reddedilen değer yine de dili değiştirdi"
    finally:
        set_language(onceki, persist=False)


# --------------------------------------------------------------------------- #
# ③ Bayatlama kapıları — ikinci bir dil listesi tutulmamalı
# --------------------------------------------------------------------------- #

def test_arac_semasi_enumu_kaynaktan_turer():
    """🔴 Enum elle yazılıydı. `en` eklenip burası unutulsaydı `set_language`
    çalışır ama LLM'e sunulan şema `en`'i geçersiz gösterirdi → model dili
    HİÇ seçemezdi. Teşhisi zor, çünkü backend tarafı sağlam görünür."""
    from app.config import LANGUAGES
    from app.services.tools.dispatcher import TOOLS

    sema = next(t for t in TOOLS if t["function"]["name"] == "set_language")
    enum = sema["function"]["parameters"]["properties"]["language"]["enum"]
    assert set(enum) == set(LANGUAGES), (
        f"araç şeması LANGUAGES ile ayrıştı — şema: {sorted(enum)}, "
        f"kayıt: {sorted(LANGUAGES)}"
    )


def test_arac_aciklamasi_ingilizce_tetik_tasir():
    """Araç açıklaması davranışsaldır: İngilizce kullanıcı 'speak English'
    dediğinde model bu aracı seçebilmeli."""
    from app.services.tools.dispatcher import TOOLS

    sema = next(t for t in TOOLS if t["function"]["name"] == "set_language")
    aciklama = sema["function"]["description"]
    assert "English" in aciklama


def test_language_api_en_sunuyor():
    """Arayüzün dil seçicisi bu uçtan besleniyor."""
    from app.api.language_api import _available

    kodlar = {d["code"] for d in _available()}
    assert "en" in kodlar
    for d in _available():
        assert d["name"] and d["flag"], f"eksik alan: {d}"


# --------------------------------------------------------------------------- #
# ④ Restart'ı aşma — GERÇEK ikinci süreçle
# --------------------------------------------------------------------------- #

def test_dil_secimi_gercek_restarti_asar(tmp_path):
    """Kartın ölçüsü: 'restart'tan sonra dil `en` kalmalı'.

    Bunu süreç içinde taklit etmek yanıltıcı olurdu (global zaten bellekte).
    Burada iki AYRI Python süreci koşar: birincisi seçer, ikincisi taze import
    edip okur — yani gerçek bir yeniden başlatma.
    """
    ayar = tmp_path / "config.user.json"
    ortam = {**os.environ, "CONFIG_USER_PATH": str(ayar), "ASSISTANT_LANGUAGE": "tr"}

    yaz = subprocess.run(
        [sys.executable, "-c", "from app import config; print(config.set_language('en'))"],
        cwd=BACKEND_DIR, env=ortam, capture_output=True, text=True, timeout=120,
    )
    assert yaz.returncode == 0, yaz.stderr
    assert yaz.stdout.strip() == "True", yaz.stdout

    assert ayar.exists(), "dil seçimi diske hiç yazılmadı"
    assert json.loads(ayar.read_text())["ASSISTANT_LANGUAGE"] == "en"

    # ── restart ──
    oku = subprocess.run(
        [sys.executable, "-c", "from app import config; print(config.get_language())"],
        cwd=BACKEND_DIR, env=ortam, capture_output=True, text=True, timeout=120,
    )
    assert oku.returncode == 0, oku.stderr
    assert oku.stdout.strip() == "en", (
        f"restart sonrası dil 'en' değil: {oku.stdout.strip()!r} — "
        "kullanıcı her açılışta Türkçe'ye düşer"
    )


# --------------------------------------------------------------------------- #
# ⑤ Onay cümlesi + frontend'in ikinci dil listesi tutmaması
# --------------------------------------------------------------------------- #

@pytest.mark.asyncio
async def test_dil_degisiminde_onay_cumlesi_o_dilde_doner(temiz_ayar):
    """`en`'e geçen kullanıcı Türkçe bir onay cümlesi görmemeli.

    Frontend'de sabit iki dal vardı (`ja` ? 日本語 : Türkçe) → `en` seçilince
    "Türkçe'ye geçtim." basardı: kullanıcı dilini değiştirdiğini kendi dilinde
    öğrenemezdi.
    """
    import httpx
    from httpx import ASGITransport
    from app.main import app
    from app.config import set_language, get_language, LANGUAGES

    onceki = get_language()
    try:
        transport = ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://127.0.0.1") as c:
            for kod in LANGUAGES:
                r = await c.post("/api/language", json={"language": kod})
                assert r.status_code == 200, r.text
                d = r.json()
                assert d["ok"] is True and d["language"] == kod
                assert d.get("mesaj"), f"'{kod}' için onay cümlesi yok"
                assert d["mesaj"] == LANGUAGES[kod]["switch_msg"]
        # Her dilin kendi cümlesi ayrı olmalı (kopyala-yapıştır kalıntısı olmasın)
        cumleler = [v["switch_msg"] for v in LANGUAGES.values()]
        assert len(set(cumleler)) == len(cumleler)
    finally:
        set_language(onceki, persist=False)


def test_frontend_dil_listesini_sabitlemiyor():
    """🔴 Statik kapı — `core.js` ikinci bir dil kaydı tutmamalı.

    Eski hâli `(lang === 'ja') ? 'ja' : 'tr'` idi: backend `en`'e geçse bile
    arayüz `tr` gösteriyordu (`tema.js`'in çift-sistem arızasının dil hâli) ve
    iki durumlu toggle üçüncü dile HİÇ ulaşamıyordu. Bu testin dosyayı okuması
    bilinçli: kural kodun kendisinde yaşamalı, kopyasında değil.
    """
    ham = (BACKEND_DIR.parent / "frontend" / "js" / "core.js").read_text(encoding="utf-8")
    # ⚠️ Yorum satırları AYIKLANIR: bu dosyada kaldırılan kusurlar gerekçeleriyle
    # birlikte yorumda alıntılanıyor (depo deseni). Ham metinde arasaydık test
    # kendi açıklamasını "kusur" sanardı — ilk koşuda tam olarak bu oldu.
    core = "\n".join(
        satir for satir in ham.splitlines() if not satir.lstrip().startswith("//")
    )

    assert "lang === 'ja'" not in core, "dil hâlâ iki duruma sabitlenmiş"
    assert "_currentLang === 'tr'" not in core, "toggle hâlâ iki durumlu"
    # Onay cümlesi backend'den
    assert "d.mesaj" in core, "onay cümlesi hâlâ frontend'de sabit"

    # ── 2026-09-18, FAZ 2 · iddia DEVREDİLDİ ────────────────────────────────
    # Burada eskiden `_LANGS` ve `d.available` ARANIYORDU: FAZ 1'de dil listesi
    # core.js'te yaşıyordu ve "API'den besleniyor mu" sorusu orada sorulurdu.
    # FAZ 2'de liste `js/dil.js`'e (window.YukiDil) taşındı — core.js artık HİÇ
    # dil durumu tutmamalı, bu daha güçlü bir kural ve
    # `test_faz2_dil_iskelesi.py::test_core_js_ikinci_dil_durumu_tutmuyor`
    # onu ölçüyor.
    #
    # ⚠️ Test "geçsin diye" gevşetilmedi, koruduğu şey YUKARI taşındı. Eski
    # assert olduğu gibi bırakılsaydı doğru mimariyi kırmızı gösterirdi —
    # bayat testin bayat belgeden farkı yok (CLAUDE.md § Bağlam Hijyeni k.5).
    assert "window.YukiDil" in core or "YukiDil" in core, \
        "core.js dil katmanını hiç kullanmıyor — tek kapı kopmuş olabilir"


def test_frontend_surum_damgasi_bumplandi():
    """`sw.js` cache-first: damga atlanırsa test yeşil kalır, müşteri ESKİ
    core.js'i çalıştırır ve dil düğmesi hiç değişmemiş gibi davranır."""
    kok = BACKEND_DIR.parent / "frontend"
    index = (kok / "index.html").read_text(encoding="utf-8")
    sw = (kok / "sw.js").read_text(encoding="utf-8")

    import re
    m = re.search(r"core\.js\?v=(\d+)", index)
    assert m, "core.js ?v= damgası bulunamadı"
    assert int(m.group(1)) >= 27, "core.js FAZ 1'de değişti ama ?v= bumplanmamış"
    m2 = re.search(r"CACHE_VERSION = 'yuki-v(\d+)'", sw)
    assert m2, "CACHE_VERSION bulunamadı"
    assert int(m2.group(1)) >= 246, "frontend değişti ama sw.js CACHE_VERSION bumplanmamış"
