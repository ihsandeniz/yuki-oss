"""Frontend önbellek-bust zinciri — mekanik bekçi (2026-08-03).

NEDEN VAR: Bu zincir bugüne kadar yalnız bir YORUM SATIRIYLA korunuyordu ve yorum
yanlıştı ("üç sayı da aynı kalmalı"). Yanlış olduğu için de tutulamıyordu: `sw.js`
CACHE_VERSION mod-dışı frontend değişikliklerinde de artıyor, mod zinciri artmıyor.
Sonuç: sayılar ayrıştı, iki ayrı denetimde "yüksek ciddiyetli kusur" diye raporlandı,
oysa gerçek kusur ayrışmada değil KURALDAYDI.

Gerçek kural:
  ① index.html'deki `chat-modes.js?v=N`  ==  ② chat-modes.js içindeki ASSET_V
     (①=② zorunlu: ASSET_V önbelleklenen dosyanın kendi içinde. ① artmazsa tarayıcı
      eski chat-modes.js'i verir, o da eski mod CSS'ini ister → ② tek başına işe yaramaz.)
  ③ sw.js CACHE_VERSION  >=  ①
     (③ tüm SW önbelleğini düşürür; geride kalırsa mod varlıkları eski SW önbelleğinden
      servis edilebilir. Önde olması zararsız.)
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

import pytest

FRONTEND = Path(__file__).resolve().parents[2] / "frontend"


def _index_modes_v() -> int:
    m = re.search(r"chat-modes\.js\?v=(\d+)", (FRONTEND / "index.html").read_text(encoding="utf-8"))
    assert m, "index.html'de chat-modes.js?v= bulunamadı"
    return int(m.group(1))


def _asset_v() -> int:
    m = re.search(r"ASSET_V\s*=\s*'(\d+)'", (FRONTEND / "modes" / "chat-modes.js").read_text(encoding="utf-8"))
    assert m, "chat-modes.js'te ASSET_V bulunamadı"
    return int(m.group(1))


def _cache_version() -> int:
    m = re.search(r"CACHE_VERSION\s*=\s*'yuki-v(\d+)'", (FRONTEND / "sw.js").read_text(encoding="utf-8"))
    assert m, "sw.js'te CACHE_VERSION bulunamadı"
    return int(m.group(1))


def test_index_ve_asset_v_esit():
    """①=② — eşitlik bozulursa mod CSS düzeltmesi müşteriye HİÇ ulaşmaz."""
    i, a = _index_modes_v(), _asset_v()
    assert i == a, (
        f"index.html ?v={i} ile chat-modes.js ASSET_V={a} ayrışmış. "
        "İkisi birlikte artmalı — yalnız ASSET_V'yi bump'lamak hiçbir işe yaramaz, "
        "tarayıcı eski chat-modes.js'i servis eder."
    )


def test_sw_cache_version_geride_kalmaz():
    """③ >= ① — sw.js önde olabilir (mod-dışı değişiklikler), geride kalamaz."""
    c, i = _cache_version(), _index_modes_v()
    assert c >= i, (
        f"sw.js CACHE_VERSION=yuki-v{c}, mod zinciri v{i} — SW geride kaldı. "
        "Mod varlıkları eski service worker önbelleğinden servis edilebilir."
    )


@pytest.mark.parametrize("dosya,desen", [
    ("index.html", r"chat-modes\.js\?v=\d+"),
    ("modes/chat-modes.js", r"ASSET_V\s*=\s*'\d+'"),
    ("sw.js", r"CACHE_VERSION\s*=\s*'yuki-v\d+'"),
])
def test_zincir_capalari_yerinde(dosya: str, desen: str):
    """Çapalardan biri yeniden adlandırılırsa üstteki iki test SESSİZCE boşa düşerdi."""
    assert re.search(desen, (FRONTEND / dosya).read_text(encoding="utf-8")), (
        f"{dosya} içindeki sürüm çapası kaybolmuş — zincir testleri artık hiçbir şey ölçmüyor"
    )


# ── Delta yükü: iddia edilen sürüm ↔ kodun bildirdiği sürüm ─────────────────
# 🔴 2026-08-04 canlı turunda ölçüldü. `update_payload.py build --version 0.5.9`
# damgasız kodu itirazsız paketliyordu: overlay v0.5.9 diye kuruluyor ama
# içindeki `health.py` hâlâ "0.5.8" diyor. Hata değil, **sessiz geri alma**:
# uygulama.js kapı ④ (gerçek başarı ölçütü) motorun bildirdiği sürümü
# beklenenle kıyaslar → uyuşmazlık → başarı işaretlenmez → her açılış
# `denemeIsaretle()` sayacı artar → 3. açılışta SAPASAĞLAM güncelleme geri alınır.
# Müşteri güncellemeyi alır, üç kez açar, güncelleme kendini geri alır, ekranda
# hiçbir şey görünmez.
#
# `yayin.py` zincirinde tetiklenmez (surum → derle → yük sırası damgayı garanti
# eder). Bu kapı elle/off-chain üretim içindir: `npm run update:payload`.

KOK = Path(__file__).resolve().parents[2]


def test_payload_surum_kapisi_var():
    """Kapı sökülür/yeniden adlandırılırsa bu test söyler (sessizce kaybolmasın)."""
    metin = (KOK / "scripts" / "update_payload.py").read_text(encoding="utf-8")
    assert "_surum_tutarliligi(" in metin, "sürüm tutarlılık kapısı çağrılmıyor"
    assert "APP_VERSION" in metin, "kapı health.py'nin APP_VERSION'ına bakmıyor"


def test_payload_ayrik_surumu_reddeder():
    """Damgalanmamış bir sürüm için yük üretimi DURMALI."""
    import subprocess

    kod_surumu = re.search(
        r'APP_VERSION\s*=\s*"([\d.]+)"',
        (KOK / "backend" / "app" / "services" / "health.py").read_text(encoding="utf-8"),
    ).group(1)
    # Kesinlikle damgalanmamış bir sürüm iste
    sahte = "99.99.99"
    assert sahte != kod_surumu
    r = subprocess.run(
        [sys.executable, "scripts/update_payload.py", "build", "--version", sahte],
        cwd=KOK, capture_output=True, text=True,
    )
    assert r.returncode != 0, "ayrık sürümlü yük üretimi kabul edildi"
    assert "SÜRÜM AYRIŞMASI" in (r.stdout + r.stderr), (
        f"durdu ama sebebi söylemedi: {(r.stdout + r.stderr)[:300]}"
    )
    # Hiçbir çıktı yazılmamalı
    assert not (KOK / "dist" / "updates" / f"yuki-update-{sahte}.json").exists()
    assert not (KOK / "dist" / "updates" / f"yuki-update-{sahte}.tar.gz").exists()


def test_iki_sayfa_ortak_varliklarda_ayni_surumu_ister():
    """index.html ile planner.html AYNI dosyaya farklı `?v=` veremez.

    🔴 2026-08-31'de ölçülerek bulundu: `tokens.css` index'te v7, planner'da
    v5; `ogeler.css` index'te v5, planner'da v3. İkisi de PAYLAŞILAN dosya.
    Sonuç: kullanıcı sohbet ekranında yeni CSS'i alıyor, PLAN ekranına
    geçince tarayıcı ESKİ sürümü önbellekten veriyor — aynı oturumda iki
    farklı tasarım. Sessiz bir kusur: hiçbir yerde hata çıkmaz, yalnız
    PLAN "eski" görünür ve bunun sebebi hiçbir log'da yazmaz.

    Sapma elle takip edilemez (5 ortak dosya, iki dosyada ayrı ayrı elle
    artırılıyor); bu yüzden kural mekanik.
    """
    import re as _re

    def damgalar(yol):
        metin = (KOK / "frontend" / yol).read_text(encoding="utf-8")
        return {
            m.group(1): m.group(2)
            for m in _re.finditer(r"/ui/([\w/.-]+\.(?:css|js))\?v=([\w.]+)", metin)
        }

    i = damgalar("index.html")
    p = damgalar("planner.html")
    ortak = set(i) & set(p)
    assert ortak, "iki sayfa hiç ortak varlık paylaşmıyor — desen değişmişse test güncellensin"

    sapan = {k: (i[k], p[k]) for k in sorted(ortak) if i[k] != p[k]}
    assert not sapan, (
        "index.html ile planner.html aynı dosyaya farklı ?v= veriyor "
        f"(PLAN ekranı bayat CSS alır): {sapan}"
    )


# ── package.json script bloğu — mekanik bekçi (2026-09-18) ───────────────────
#
# 🔴 NEDEN EKLENDİ: `npm run build:all` KAYNAK `electron/package.json`'ı ezip
# `scripts` bloğunun tamamını sildi (v0.6.16 derleme turunda ölçüldü). Sebep
# `extraMetadata` (yukiSku damgası) + `directories.app` tanımsızlığı: builder
# uygulama paketi olarak `electron/`i alıp damgayı kaynak dosyaya yazıyor.
#
# Fark edilmesi zor, çünkü **sürüm alanı doğru kalıyor** — yalnız `scripts`
# gidiyor. Bir sonraki turda `npm run prep` "missing script" der ve suçlu
# derleme sanılmaz; o tur yayın zincirini kırar.
#
# `yayin.py derle` artık dosyayı yedekleyip geri yüklüyor; bu test o korumanın
# delinip delinmediğini söyler.

def test_package_json_scriptleri_duruyor():
    import json
    p = KOK / "electron" / "package.json"
    d = json.loads(p.read_text(encoding="utf-8"))
    scripts = d.get("scripts", {})
    # Yayın zincirinin dayandığı komutlar — biri eksikse zincir kırılır
    for gerekli in ("prep", "build:all", "update:payload", "test"):
        assert gerekli in scripts, (
            f"electron/package.json'da `{gerekli}` scripti YOK — derleme kaynak "
            "dosyayı ezmiş olabilir (yayin.py derle koruması delindi mi?)"
        )
    assert "version" in d, "sürüm alanı kayıp"
