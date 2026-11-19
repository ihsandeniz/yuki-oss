"""HQ → SİSTEM paneli (Dalga 3, 2026-09-10) — kademe ve platform kapıları.

🔑 **Neden var:** `api/monitor.py` 142 satır kod ve 8 rotayla depoda duruyordu
ama `main.py`'ye **hiç kayıtlı değildi**, üstelik dört `electron-builder*.yml`
onu müşteri paketinden ayrıca çıkarıyordu. Tek tüketicisi `game-mode.js`'ti ve
OYUN modu üründe kapalı → kod **ölüydü**. Dalga 3 onu uyandırıyor.

Bu dosyanın koruduğu üç şey:

  ① **Uyanık kalsın.** Router kaydı VE paket filtresi birlikte doğru olmalı.
     Biri düzelip öbürü unutulursa uç geliştirmede çalışır, **müşteride 404**
     olur — sessiz ve yalnız paketlenmiş kurulumda görünen bir arıza.
  ② **Panel yalnız izler.** Süreç sonlandırma ucu ve düğmesi açık kaynak
     sürümde YOK (karar: 2026-10-17 yuki-urun-acik-kaynak § Ek karar).
  ③ **Windows'ta panel çökmesin.** Sensör/güç okumaları Linux'a özel; Windows'ta
     `None` dönmeli, istisna fırlatmamalı. Bu makinede gerçek Windows yok —
     eksiklik **simüle edilerek** ölçülüyor (psutil yaması).

📏 Ders (bu turda iki kez düşüldü): *"üründe 0 satır" iddiası, özelliği ADIYLA
aramaktan doğdu. Yokluğu kimliğiyle ölçmek gerekiyor — router kaydı, `data-tab`,
builder filtresi.*
"""
from __future__ import annotations

import re
from pathlib import Path

import pytest

KOK = Path(__file__).resolve().parents[2]


# ── ① uyanık mı ─────────────────────────────────────────────────────────────
def test_monitor_router_kayitli():
    from app.main import app
    yollar = {r.path for r in app.routes if getattr(r, "path", "").startswith("/api/monitor")}
    assert "/api/monitor/snapshot" in yollar, "monitor router main.py'ye kayıtlı değil"
    assert len(yollar) == 7, f"beklenen 7 rota, bulunan {len(yollar)}: {sorted(yollar)}"


@pytest.mark.parametrize("yml", [
    "electron/electron-builder.yml",
    "electron/electron-builder-full.yml",
    "electron/electron-builder-win.yml",
    "electron/electron-builder-win-full.yml",
])
def test_monitor_musteri_paketinden_cikarilmiyor(yml):
    """Kayıt yetmez — paket filtresi de düzelmeli, yoksa müşteride 404.

    Filtre `{bio,devices_api,monitor}.py` biçiminde bir küme; `monitor` orada
    kalırsa uç yalnız GELİŞTİRMEDE çalışır. Bu asimetri en pahalı hata sınıfı:
    bizde yeşil, müşteride ölü.
    """
    metin = (KOK / yml).read_text(encoding="utf-8")
    for satir in metin.splitlines():
        s = satir.strip()
        if s.startswith("- ") and "!app/api/" in s and "monitor" in s:
            # yorum kısmı serbest — asıl desen tırnak içinde
            desen = re.search(r'"!app/api/\{([^}]*)\}\.py"', s)
            if desen and "monitor" in desen.group(1).split(","):
                pytest.fail(f"{yml}: monitor.py hâlâ paketten çıkarılıyor → {s[:70]}")


# ── ② süreç sonlandırma ucu YOK ──────────────────────────────────────────────
def test_kill_ucu_YOK():
    from app.main import app
    yollar = {r.path for r in app.routes if getattr(r, "path", "").startswith("/api/monitor")}
    assert not any(y.endswith("/kill") for y in yollar), sorted(yollar)


# ── ③ Windows'ta düşen alanlar ──────────────────────────────────────────────
def test_sicaklik_okunamazsa_None_doner(monkeypatch):
    """Windows'ta `psutil.sensors_temperatures` YOKTUR → AttributeError.

    Panel çökmemeli, alan `None` olmalı (arayüz "—" gösterir).
    """
    import psutil

    from app.services.monitoring.collector import monitor as mon

    monkeypatch.delattr(psutil, "sensors_temperatures", raising=False)
    assert mon._cpu_temp() is None
    assert mon._nvme_temp() is None


def test_guc_okunamazsa_None_doner(monkeypatch):
    """RAPL `/sys/class/powercap` Linux'a özel — Windows'ta yok."""
    from app.services.monitoring import collector as c

    monkeypatch.setattr(c.glob, "glob", lambda desen: [])
    assert c.monitor._read_rapl() is None
    assert c.monitor._power() is None


def test_snapshot_sensorsuz_makinede_de_uretiliyor(monkeypatch):
    """Uçtan uca: sensör de güç de yokken snapshot yine dolu dönmeli.

    Ölçülen şey "Windows'ta çalışıyor" DEĞİL — bu makinede gerçek Windows yok.
    Ölçülen şey: eksik sensör snapshot'ı ÇÖKERTMİYOR ve çekirdek alanlar
    (cpu/mem/disk/net) yerinde kalıyor. Gerçek Windows turu ayrı bir doğrulama.
    """
    import psutil

    from app.services.monitoring import collector as c

    monkeypatch.delattr(psutil, "sensors_temperatures", raising=False)
    monkeypatch.setattr(c.glob, "glob", lambda desen: [])
    monkeypatch.setattr(c._gpu, "amd_snapshot", lambda: None)
    monkeypatch.setattr(c._gpu, "nvidia_snapshot", lambda: None)

    snap = c.monitor.snapshot(include_processes=False)
    for alan in ("cpu", "mem", "disks", "net", "health_score", "alerts"):
        assert alan in snap, f"{alan} snapshot'tan düştü"
    assert snap["cpu"]["temp_c"] is None
    assert snap["power"] is None
    assert isinstance(snap["health_score"], int)


# ══════════════════════════════════════════════════════════════════════════
# ④ ARAYÜZ YARISI (2026-09-10 akşamı) — statik kapılar
#
# 🔑 Neden burada: bu üç şeyin ikisi **sessizce** kırılır. Panel kaydı beş
# yerden geçiyor ve biri kaçarsa hiçbir yerde hata çıkmaz — ekran boş kalır
# ya da çalışmayan bir düğme görünür. Canlı Playwright turu ayrı
# (`scratchpad/hq-sistem-canli-test.py`); bu dosya *kod diskteyken* bakar.
# ══════════════════════════════════════════════════════════════════════════
FE = KOK / "frontend"


def _oku(yol: str) -> str:
    return (FE / yol).read_text(encoding="utf-8")


def test_sistem_paneli_UC_PARCA_birden():
    """🔴 Yeni HQ paneli = HTML div + JS panel listesi + CSS açılış kuralı.

    CSS satırı unutulursa `hq.css`'teki `#tab-hq .hq-panel{display:none
    !important}` her şeyi kapatır: panel İÇERİĞİ çizilir (kişiselde ölçüldü:
    9061 karakter) ama ekranda hiçbir şey görünmez. Hata yok, log yok.
    """
    assert 'id="hq-panel-sistem"' in _oku("index.html"), "① HTML div'i yok"
    assert "'sistem'" in _oku("js/intro-sequences.js").split("var _HQ_PANELS=")[1].split("\n")[0], \
        "② _HQ_PANELS listesinde 'sistem' yok → switchHqTab paneli hiç göstermez"
    assert re.search(
        r'#tab-hq\[data-hq="sistem"\]\s+#hq-panel-sistem\s*\{[^}]*display:\s*flex\s*!important',
        _oku("css/hq-monitor.css"),
    ), "③ CSS açılış kuralı yok → panel SESSİZCE boş kalır"


def test_sistem_menude_ulasilabilir():
    """Panelin var olması, kullanıcının ona ULAŞABİLDİĞİ anlamına gelmez.

    Menü `HQ_MENU` listesinden üretiliyor; girdi yoksa panel `switchHqTab`
    ile açılabilir ama menüde **hiçbir düğmesi olmaz**. Aynı ders 09-07'de
    yüz tanımada, 09-08'de telefondaki BUGÜN panelinde ölçüldü.
    """
    js = _oku("js/intro-sequences.js")
    assert re.search(r"\{tip:'panel',\s*id:'sistem'", js), "HQ_MENU'de sistem girdisi yok"
    assert "'sistem':" in js.split("var _PANEL_IKONLARI")[1].split("var HQ_MENU")[0], \
        "_PANEL_IKONLARI'nda 'sistem' ikonu yok → menüde ham metin görünür"


def test_hq_menusunde_AYNI_AD_iki_kez_gecmiyor():
    """🔴 Canlı ekran görüntüsünde yakalandı (2026-09-10).

    SİSTEM paneli ilk sürümde `etiket:'Sistem'` ile eklendi. Ama `gelistirici`
    ayar kategorisinin etiketi **zaten "Sistem"** (`settings_api.py`) ve o da
    aynı sol menüde (GELİŞMİŞ grubunda) duruyor → kullanıcı iki özdeş adlı
    girdi görüyordu. Hiçbir test kırmızı yanmadı, konsola satır düşmedi;
    yalnız **ekrana bakınca** görüldü.

    📏 Ders: menü, paneller ile ayar kategorilerini TEK listede birleştiriyor
    (karar D5). Birleşen iki ad uzayında çakışma kaçınılmazdır ve yalnız
    mekanik olarak yakalanır — bu test o kapı.

    ⚠️ 2026-09-19 (FAZ 3 · Dalga 2) — kapı DEVREDİLDİ, gevşetilmedi. `HQ_MENU`
    artık `etiket:'hq.menu.sistem'` gibi ANAHTAR taşıyor. Eski gövde
    `etiket:'([^']+)'` okuduğu için karşılaştırma anahtar uzayına kaymıştı:
    `hq.menu.bilgisayarim` ile `Sistem` asla kesişmez → test **yeşil kalır ve
    hiçbir şeyi ölçmez.** Bu, "geçsin diye gevşetilmiş test"in kendiliğinden
    oluşan hâli ve bayat belgeden farksızdır.

    İddia artık GÖRÜNEN ada bakıyor: anahtarlar sözlükten çözülüyor ve çakışma
    **iki dilde ayrı ayrı** aranıyor. Yeni bir arıza yüzeyi de bu:
    `gelistirici` kategorisi İngilizce'de "System", SİSTEM paneli "My Computer"
    olmak zorunda — TR'de ayrı olan iki ad EN'de aynı kelimeye çevrilirse
    çakışma geri gelir ve yine yalnız ekrana bakınca görülürdü.
    """
    from yardim import sozluk

    js = _oku("js/intro-sequences.js")
    anahtarlar = re.findall(r"etiket:'([^']+)'", js)
    assert anahtarlar, "HQ_MENU'de etiket alanı okunamadı — desen bayatlamış olabilir"
    ham = [a for a in anahtarlar if not a.startswith("hq.menu.")]
    assert not ham, (
        f"panel etiketi çeviri anahtarı değil: {ham} — ham metin İngilizce "
        "müşteride Türkçe kalır (FAZ 3 · Dalga 2)"
    )

    api = (KOK / "backend/app/api/settings_api.py").read_text(encoding="utf-8")
    # Kategori satırları: {"id": "x", "label": "Y", ...}
    kat = {
        m.group(1): m.group(2)
        for m in re.finditer(r'\{"id":\s*"([a-z_]+)",\s*"label":\s*"([^"]+)"', api)
    }
    assert kat, "kategori etiketleri okunamadı — desen bayatlamış olabilir"

    for dil in ("tr", "en"):
        s = sozluk(dil)
        panel_adlari = [s[a].lower() for a in anahtarlar if a in s]
        assert len(panel_adlari) == len(anahtarlar), (
            f"{dil}: sözlükte karşılığı olmayan panel etiketi var → "
            f"{sorted(set(anahtarlar) - set(s))}"
        )
        # Kategori adı: sözlükte varsa oradan, yoksa backend `label`'ı
        # (`intro-sequences.js::_catAd` ile AYNI kademe).
        kat_adlari = [s.get("hq.cat." + kid, etiket).lower()
                      for kid, etiket in kat.items()]

        cakisan = sorted(set(panel_adlari) & set(kat_adlari))
        assert not cakisan, (
            f"{dil}: HQ menüsünde aynı ad iki kez: {cakisan} — panel adı ile "
            f"ayar kategorisi adı çakışıyor, kullanıcı iki özdeş girdi görür"
        )
        tekrar = [a for a in set(panel_adlari) if panel_adlari.count(a) > 1]
        assert not tekrar, f"{dil}: iki panel aynı adı taşıyor: {tekrar}"
        tekrar_kat = [a for a in set(kat_adlari) if kat_adlari.count(a) > 1]
        assert not tekrar_kat, f"{dil}: iki kategori aynı adı taşıyor: {tekrar_kat}"


def test_okunamayan_alan_TIRE_gosteriyor_SIFIR_degil():
    """🔴 `null` → "—", asla 0.

    Windows'ta 70 alandan ~6'sı okunamıyor (CPU/NVMe sıcaklığı, RAPL güç,
    AMD GPU). `0°C` yalan söyler ve kullanıcıyı yanlış teşhise yollar —
    ElevenLabs'in "401 = geçersiz anahtar" sanılması dersinin aynısı.
    """
    js = _oku("js/intro-sequences.js")
    assert "var TIRE='—'" in js.replace('"', "'"), "tek kaynaklı '—' sabiti yok"
    # Sıcaklık/güç/yük: null gelince `_monYaz` null alır → "—" basar
    for cagri in ("mon-cpu-temp", "mon-cpu-load", "mon-power", "mon-gpu-temp"):
        assert re.search(rf"_monYaz\('{cagri}'", js), f"{cagri} _monYaz'dan geçmiyor"
    # 🔴 En kolay kaçan hâl: `|| 0` ile null'ı sıfıra çevirmek
    for satir in js.splitlines():
        if "_monYaz(" in satir and "temp_c" in satir:
            assert "||0" not in satir.replace(" ", ""), f"null sıfıra çevrilmiş: {satir.strip()}"


def test_intel_bloklari_TASINMADI():
    """Kişiseldeki SYS HEALTH şeridi + LIVE EVENTS bilerek alınmadı.

    Onları `mon-*` değil `js/hq-monitor.js` (454 satır, ayrı istihbarat
    paneli) besliyor ve üründe o uçlar yok. Kopyalansalardı ekranda kalıcı
    "—" şeridi ve `setIntelFilter is not defined` veren altı düğme dururdu.
    Bu test bir gelecek turun onları "eksik" sanıp geri koymasını engeller —
    geri konacaksa **önce besleyicisi** taşınmalı.
    """
    html = _oku("index.html")
    for kimlik in ('id="intel-health"', 'id="sys-events-strip"', "setIntelFilter("):
        assert kimlik not in html, (
            f"{kimlik} üründe besleyicisiz — hq-monitor.js taşınmadan markup eklenmez"
        )


def test_surum_damgalari_arttI():
    """Frontend değişti → `?v=` ve `CACHE_VERSION` artmalı.

    Kural (`test_surum_zinciri.py`): ① index.html `?v=` == ② `ASSET_V`,
    ③ `sw.js CACHE_VERSION` ≥ ①. Burada ayrıca YENİ dosyanın damgalı
    çağrıldığı ölçülüyor — damgasız CSS müşteride önbellekten eski hâliyle
    gelirdi ve panel renksiz görünürdü.
    """
    html = _oku("index.html")
    assert re.search(r'css/hq-monitor\.css\?v=\d+', html), "hq-monitor.css damgasız çağrılıyor"
    assert re.search(r'js/intro-sequences\.js\?v=(2[89]|[3-9]\d)', html), \
        "intro-sequences.js ?v= artmadı (28+ bekleniyor)"
