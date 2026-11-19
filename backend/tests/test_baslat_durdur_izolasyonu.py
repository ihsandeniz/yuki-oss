"""`start.sh` / `stop.sh` komşu kuruluma uzanmasın — mekanik bekçi (2026-09-10).

🔴 **Neden var:** ürünün bu iki scripti kişisel Alice'ten **fotokopiydi** ve
ürünü değil KİŞİSELİ hedefliyordu. Ölçüldü, dördü de gerçekti:

  ① `PID_FILE=/tmp/alice-backend.pid` — kişiselle **aynı dosya**
  ② `lsof -ti tcp:8000` — kişiselin portu (ürünün portu 8001)
  ③ `cloudflared tunnel run yuki` — kişiselin **genel** tüneli
     (kişisel alan adı → :8000); ürünü başlatmak kişiseli internete
     açıyor, durdurmak tünelini kapatıyordu
  ④ `pgrep -f "alice-ai|AliceAi/electron"` — desende kişiselin **dizin yolu**
     var; ayrıca `alice-ai` iki kurulumun paylaştığı Electron `name`'i

Ayrıca `config.py` varsayılanı `PORT=8000`'dir: script portu hiç ayarlamadığı
için ürün, `.env`'inde PORT yoksa doğrudan kişiselin portuna oturuyordu.

📏 **Ders:** bir dosyayı komşu projeden kopyalamak, içindeki **adresleri de**
kopyalar. Ürünleştirmede tehlikeli olan sabit, kodun kendisi değil kimin
kaynağını gösterdiğidir.

⚠️ Bu bir **yorum kapısı değil, içerik kapısı**: yasak dizgeler yorum
satırlarında (yukarıdaki gerekçe metni gibi) serbesttir, **çalışan kodda**
yasaktır. Kapıyı yorumlara kursaydık kendi açıklamamız testi kırardı ve test
silinirdi.
"""
from __future__ import annotations

import re
from pathlib import Path

import pytest

KOK = Path(__file__).resolve().parents[2]
SCRIPTLER = ("start.sh", "stop.sh")

#: (desen, neden) — hepsi KİŞİSEL kuruluma ait adresler.
YASAK = [
    (r"/tmp/alice-backend\.pid", "kişiselle paylaşılan PID dosyası"),
    (r"/tmp/alice-electron\.pid", "kişiselle paylaşılan Electron PID dosyası"),
    (r"\btcp:8000\b", "kişiselin portu"),
    (r"127\.0\.0\.1:8000", "kişiselin portu"),
    (r"cloudflared\s+tunnel\s+run", "kişiselin genel tüneli"),
    (r"AliceAi/", "kişiselin dizin yolu"),
    (r"pgrep\s+-f\s+.*alice-ai", "iki kurulumun paylaştığı Electron adı"),
    (r"pg_isready.*-p\s*5433", "kişiselin postgres portu"),
]


def _kod_satirlari(yol: Path) -> list[tuple[int, str]]:
    """Yorum ve boş satırlar atılmış hâli — kapı ÇALIŞAN koda kurulur.

    Satır içi yorum da kırpılır (`kill $PID  # not`), ama `#` bir dizgenin
    içindeyse kırpılmaz: `"tcp:8000"` gibi bir sabiti yorum sanıp kaçırmayalım.
    """
    cikti = []
    for no, ham in enumerate(yol.read_text(encoding="utf-8").splitlines(), 1):
        satir = re.sub(r"(?<![\"'\\])#.*$", "", ham).strip()
        if satir:
            cikti.append((no, satir))
    return cikti


@pytest.mark.parametrize("ad", SCRIPTLER)
def test_script_kisisel_kuruluma_uzanmiyor(ad):
    yol = KOK / ad
    assert yol.exists(), f"{ad} yok"

    bulgular = []
    for no, satir in _kod_satirlari(yol):
        for desen, neden in YASAK:
            if re.search(desen, satir):
                bulgular.append(f"{ad}:{no} → {neden}  ({satir[:70]})")
    assert not bulgular, "Kişisel kuruluma uzanan satır(lar):\n  " + "\n  ".join(bulgular)


@pytest.mark.parametrize("ad", SCRIPTLER)
def test_script_urun_portunu_kendisi_veriyor(ad):
    """Port varsayıma bırakılmamalı — `config.py` varsayılanı 8000'dir.

    Ürün `.env`'inde PORT yoksa ve script de vermiyorsa, ürün sessizce
    kişiselin portuna oturur.
    """
    metin = (KOK / ad).read_text(encoding="utf-8")
    assert re.search(r'PORT="\$\{YUKI_PORT:-8001\}"', metin), \
        f"{ad} ürün portunu kendisi vermiyor"


def test_stop_port_uzerinden_koru_koru_oldurmuyor():
    """`stop.sh` yalnız KENDİ başlattığını durdurmalı.

    Eski hâli PID dosyası yoksa porta bakıp öldürüyordu — kişiseli vurduğu yer
    tam olarak burasıydı. Port yoklaması bilgi vermek için kalabilir, `kill`e
    bağlanamaz.
    """
    satirlar = _kod_satirlari(KOK / "stop.sh")
    for no, satir in satirlar:
        if "lsof" in satir:
            assert "kill" not in satir, \
                f"stop.sh:{no} port taramasını doğrudan kill'e bağlıyor: {satir}"
    # `xargs kill` deseni de aynı kapıdan geçmeli.
    metin = "\n".join(s for _, s in satirlar)
    assert "xargs kill" not in metin, "stop.sh toplu kill yapıyor — kapsamı belirsiz"


def test_urunde_kisisel_toggle_kopyasi_yok():
    """`toggle-aliceai.sh` ürün deposunda DURMAMALI.

    Kişiseldekiyle bayt bayt aynıydı ve `YUKI_DIR`'i kişiseli gösteriyordu:
    ürün dizininde çalıştırılırsa kişisel Alice'i durdurur. Hyprland kısayolu
    zaten kişiseldeki kopyayı çağırıyor (ölçüldü) — burada durması yalnız
    yanlış çalıştırılma riski üretiyordu.
    """
    assert not (KOK / "toggle-aliceai.sh").exists(), \
        "toggle-aliceai.sh geri gelmiş — kişisel kuruluma uzanıyor"


def _hafiza_secimi(tmp_path, ortam_degeri=None, env_satiri=None, veri_env_satiri=None):
    """start.sh'teki MEMORY_BACKEND bloğunu tek başına koş, sonucu döndür."""
    import os
    import subprocess
    metin = (KOK / "start.sh").read_text(encoding="utf-8")
    m = re.search(r'^if \[\[ -z "\$\{MEMORY_BACKEND:-\}" \]\].*?^fi$', metin, re.S | re.M)
    assert m, "start.sh hafıza varsayılanını vermiyor"
    if env_satiri is not None:
        (tmp_path / ".env").write_text(env_satiri + "\n", encoding="utf-8")
    ortam = {k: v for k, v in os.environ.items() if k not in ("MEMORY_BACKEND", "YUKI_DATA_DIR")}
    if veri_env_satiri is not None:
        veri = tmp_path / "veri"
        veri.mkdir()
        (veri / ".env").write_text(veri_env_satiri + "\n", encoding="utf-8")
        ortam["YUKI_DATA_DIR"] = str(veri)
    if ortam_degeri is not None:
        ortam["MEMORY_BACKEND"] = ortam_degeri
    betik = f'set -euo pipefail\nROOT_DIR="{tmp_path}"\n{m.group(0)}\necho "${{MEMORY_BACKEND:-YOK}}"'
    r = subprocess.run(["bash", "-c", betik], env=ortam, capture_output=True, text=True, timeout=30)
    assert r.returncode == 0, r.stderr
    return r.stdout.strip()


def test_start_hafizayi_kapali_acmiyor(tmp_path):
    """Temiz klonda `./start.sh` hafızayı kapalı açıyordu (/health "memory": false)."""
    assert _hafiza_secimi(tmp_path) == "sqlite"


def test_start_env_secimini_ezmiyor(tmp_path):
    assert _hafiza_secimi(tmp_path, env_satiri="MEMORY_BACKEND=pgvector") == "YOK", \
        ".env'deki seçim config'e kalmalı (load_dotenv ortamdakini ezmez)"
    assert _hafiza_secimi(tmp_path, ortam_degeri="pgvector") == "pgvector"


@pytest.mark.parametrize("satir", [
    "export MEMORY_BACKEND=pgvector",   # python-dotenv bu biçimi okur
    "MEMORY_BACKEND = pgvector",
    "  MEMORY_BACKEND=pgvector",
])
def test_start_dotenv_bicimlerini_taniyor(tmp_path, satir):
    """Eskiden yalnız `MEMORY_BACKEND=` kalıbı aranıyordu; öbür biçimlerde seçim sqlite'la eziliyordu."""
    assert _hafiza_secimi(tmp_path, env_satiri=satir) == "YOK"


def test_start_config_ile_ayni_env_dosyasina_bakiyor(tmp_path):
    """config.py veri dizinindeki .env varsa yalnız onu okur; kökteki seçim orada geçersizdir."""
    a, b = tmp_path / "a", tmp_path / "b"
    a.mkdir(); b.mkdir()
    assert _hafiza_secimi(a, env_satiri="MEMORY_BACKEND=pgvector",
                          veri_env_satiri="OPENROUTER_API_KEY=x") == "sqlite"
    assert _hafiza_secimi(b, veri_env_satiri="MEMORY_BACKEND=pgvector") == "YOK"
