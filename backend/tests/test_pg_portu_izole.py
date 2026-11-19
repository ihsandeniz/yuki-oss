"""Ürünün Postgres portu KİŞİSEL Alice'inkine çarpmamalı + tek kaynaktan gelmeli.

🔑 **Neden var (2026-09-10, canlı `docker ps` ile ölçüldü):** kök
`docker-compose.yml` kendi içinde tutarsızdı ve **iki sayısı da yanlıştı**:

  · `PGPORT: 5433` → 5433 **KİŞİSEL Alice'in** veritabanı
    (`alice-ai-postgres-1`). Dosya `network_mode: host` kullanıyor, yani port
    eşlemesi/yalıtımı **yok**: bu compose ayağa kalkarsa ya bağlanamaz ya da
    kişisel kapalıyken onun portuna oturur — ve kişisel Alice sonra **ürünün**
    veritabanına bağlanır.
  · `DATABASE_URL: …@localhost:5435` → 5435 **`yuzarama-pg`**, bambaşka bir
    proje. Veri karışmadı çünkü orada `yuki` rolü yok; yani bizi kurtaran şey
    tasarım değil **şans**.

📏 Ders — `start.sh`/`stop.sh` turunun (`84af46d`) birebir aynısı: *bir dosyayı
komşu projeden kopyalamak, içindeki **adresleri de** kopyalar.*

⚠️ Bu canlı bir arıza değildi: ürün Postgres'siz çalışıyor (`todo_store.json`)
ve scriptler compose'u hiç çağırmıyor. **Kurulu bir tuzaktı** — ve tuzaklar
yalnız mekanik olarak kapatılır, yorumla değil.

Bu dosyanın koruduğu iki şey:
  ① Compose kendi içinde TUTARLI (PGPORT == healthcheck == DATABASE_URL).
     Tutarsızlık, "veritabanı bir yerde ayakta ama kimse oraya bağlanmıyor"
     sınıfını üretir ve hata vermez.
  ② Port **5433 OLAMAZ** — kişiselin portu. Bu iki depo aynı makinede komşu
     ve ikisi de belgelenmiş; ötekiler (5434 uai · 5435 yuzarama · 5436
     galleryweb) bu makineye özel, müşteride karşılığı yok → depoya
     sabitlemek yanlış olurdu.
"""
from __future__ import annotations

import re
from pathlib import Path

KOK = Path(__file__).resolve().parents[2]
COMPOSE = KOK / "docker-compose.yml"

# Kişisel Alice'in pgvector portu — iki deponun CLAUDE.md'sinde de yazılı.
KISISEL_PG_PORT = "5433"


def _metin() -> str:
    return COMPOSE.read_text(encoding="utf-8")


def _portlar() -> dict[str, str]:
    """Compose'daki üç port yazımını ayıkla.

    ⚠️ Yorum satırları AYIKLANIR — dosyanın başındaki gerekçe metni eski yanlış
    sayıları (5433/5435) *anlatmak* zorunda ve düz tarama onları "kod" sanıyordu
    (aynı tuzağa `test_hq_sistem_kapisi.py`'de de düşülmüştü).
    """
    kod = "\n".join(s for s in _metin().splitlines() if not s.lstrip().startswith("#"))
    # ⚠️ `\S+` KULLANMA: healthcheck bir JSON dizisinin içinde ve `\S+` sondaki
    # `"]`yi de yutuyor → değer `${…}"]` olur, tutarlılık testi DOĞRU dosyada
    # kırmızı yanar. (Bu turda bizzat yaşandı; kusur koddaydı sanıldı, araçtaydı.)
    # 📏 Ders — bu depoda yazılı: bir ölçüm aracı bir şey diyorsa önce
    #    ARACIN O ŞEYİ DOĞRU GÖRDÜĞÜNÜ kanıtla (`test_duvar.py` öz-sınaması).
    return {
        "pgport": (re.search(r"PGPORT:\s*([^\s\"\]]+)", kod) or [None, None])[1],
        "healthcheck": (re.search(r"pg_isready[^\"]*-p\s+([^\s\"\]]+)", kod) or [None, None])[1],
    }


def _env_ornegi_portu() -> str | None:
    """`.env.example`'daki (yorumlu) DATABASE_URL portu — compose'da backend servisi yok (11-16)."""
    m = re.search(r"DATABASE_URL=postgresql://\S*?@localhost:([0-9]+)/", (KOK / ".env.example").read_text(encoding="utf-8"))
    return m.group(1) if m else None


def _coz(deger: str) -> str:
    """`${VAR:-5437}` → `5437`. Düz sayı ise olduğu gibi döner."""
    m = re.fullmatch(r"\$\{[A-Z_]+:-([0-9]+)\}", (deger or "").strip())
    return m.group(1) if m else (deger or "").strip()


def test_compose_kendi_icinde_tutarli():
    """Üç yazımın hepsi AYNI portu göstermeli.

    Tutarsızlık sessizdir: pg bir portta kalkar, backend başka porta bağlanmaya
    çalışır, kimse hata görmez — yalnız hafıza/pgvector sessizce çalışmaz.
    """
    p = _portlar()
    for ad, deger in p.items():
        assert deger, f"{ad} compose'da bulunamadı — desen bayatlamış olabilir"
    cozulmus = {ad: _coz(d) for ad, d in p.items()}
    cozulmus["env_ornegi_database_url"] = _env_ornegi_portu()
    assert len(set(cozulmus.values())) == 1, (
        f"compose kendi içinde tutarsız: {cozulmus} — PGPORT, healthcheck ve "
        f"DATABASE_URL aynı portu göstermeli"
    )


def test_port_TEK_KAYNAKTAN_geliyor():
    """Sayı elle iki kez yazılmamalı; ikisi de aynı değişkenden gelmeli.

    Tutarlılık testi tek başına yetmez: bugün eşit olan iki sabit, yarın biri
    değiştirilince ayrışır ve ayrıştığı yere kimse bakmaz (`surum.js` dersi).
    """
    p = _portlar()
    for ad, deger in p.items():
        assert (deger or "").startswith("${"), (
            f"{ad} sabit sayı yazıyor ({deger}) — `${{YUKI_PG_PORT:-…}}` kullanılmalı"
        )


def test_kisiselin_portuna_CARPMIYOR():
    """🔴 Asıl kapı. `network_mode: host` → port yalıtımı yok.

    5433'e oturmak, kişisel Alice'in veritabanının üstüne oturmaktır.
    """
    p = {ad: _coz(d) for ad, d in _portlar().items()}
    for ad, deger in p.items():
        assert deger != KISISEL_PG_PORT, (
            f"{ad} = {KISISEL_PG_PORT} → KİŞİSEL Alice'in pgvector portu. "
            f"network_mode: host olduğu için bu bir çakışma değil, DEVRALMADIR."
        )


def test_konteyner_adi_belgeyle_tutuyor():
    """CLAUDE.md `yuki-oss-pg` diyor — compose de öyle demeli.

    Adsız bırakıldığında docker `<klasör>-postgres-1` üretiyordu ve
    belgedeki ad hiçbir zaman var olmadı: `docker ps | grep yuki-oss-pg`
    boş dönüyor, okuyan *"demek ki çalışmıyor"* diye yanlış teşhis koyuyordu.
    """
    assert "container_name: yuki-oss-pg" in _metin(), (
        "compose'da container_name yok → belgedeki 'yuki-oss-pg' adı yalan olur"
    )


def test_compose_yalniz_postgres_belgeyle_tutarli():
    """README yalnız `docker compose up -d postgres` diyor; eski backend servisi kırıktı (py3.11, frontend
    imajda yok) ve kişiselden kalmaydı (denetim 2026-11-16). Geri gelirse belgeyle birlikte gelmeli."""
    kod = "\n".join(s for s in _metin().splitlines() if not s.lstrip().startswith("#"))
    servisler = re.findall(r"^  ([a-z][\w-]*):\s*$", kod.split("\nvolumes:")[0], flags=re.M)
    assert servisler == ["postgres"], servisler
    assert "docker compose up -d postgres" in (KOK / "README.md").read_text(encoding="utf-8")
