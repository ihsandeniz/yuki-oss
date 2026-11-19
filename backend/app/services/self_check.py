"""Kurulum sihirbazı çekirdeği — ortamı denetle, sebebini söyle, düzeltebileceğini düzelt.

🔴 Neden var (2026-08-01): ürün temiz bir Windows'ta ilk kez denendiğinde çalışmadı ve
her başarısızlık **sessizdi**. Kullanıcı "çalışmıyor" diyor, elimizde veri yok. Bu modül
ürünün kendi ortamını denetlemesini sağlar.

Tasarım kuralları:
- **Ölçer, tahmin etmez.** Her denetim gerçekten import eder / dosyaya bakar / ağa çıkar.
- **Her başarısızlık insan diliyle bir çözüm cümlesi taşır** — "hata kodu" yetmez.
- **Otomatik onarım yalnız GÜVENLİ ve GERİ ALINABİLİR işler için.** Kullanıcının
  makinesine paket kurmak, sistem ayarı değiştirmek bu modülün işi değildir; onu
  yalnız anlatır. (bkz. [[feedback_kullanici_ortamina_dokunma]] deseni)
- Sonuçlar hata günlüğüne düşer → destek istendiğinde geçmiş elimizde olur.
"""

from __future__ import annotations

import logging
import os
import platform
import shutil
import sys
from pathlib import Path

from app.mesajlar import M

logger = logging.getLogger(__name__)

KRITIK = "kritik"   # ürünün satılan bir özelliği çalışmıyor
UYARI = "uyari"     # bozulma var ama ürün ayakta
BILGI = "bilgi"
OLCULEMEDI = "olculemedi"   # arıza bulunmadı ama denetim de yapılamadı — "yolunda" DEĞİL
KURULUM = "kurulum"         # henüz kurulmadı (ilk açılış, anahtar hiç girilmemiş) — arıza DEĞİL, davet


def _sonuc(kimlik, baslik, ok, seviye, detay="", cozum="", cozum_url="",
           otomatik=False, kurulum=None, olculemedi=False, yonlendir=None, teknik="",
           ilk_kurulum=False):
    """Tek bir denetimin sonucu.

    `otomatik`  → "DÜZELT" düğmesi. Yalnız güvenli/geri alınabilir işler (bkz. `onar`).
    `kurulum`   → AYRI bir düğme: kullanıcının makinesine bir şey KURAN, geri alınabilir
                  olmayan, yönetici onayı isteyen iş (bkz. `kur`). Bilerek `otomatik`ten
                  ayrı tutulur ki toplu/otomatik bir onarım akışına asla karışmasın.
                  Şekli: {"kimlik": str, "etiket": str, "uyari": str}
    `olculemedi`→ denetim YAPILAMADI (liste alınamadı, disk okunamadı, sağlayıcı
                  denetlenemiyor). 🔴 2026-09-28 ( panel 10): bu üç yer `ok=True`
                  dönüyordu ve panel onları yeşil "yolunda" diye çiziyordu — ölçmediğimiz
                  şeye sağlam demek. `ok` geriye uyum için "arıza bulunmadı" anlamında
                  True kalır (orkestratör, eski arayüz); "yolunda" demek için `durum`'a bak.
    `yonlendir` → çözüm başka bir panelde ("key" = ANAHTAR); arayüz oraya götüren düğme koyar.
    `teknik`    → ham istisna / model kimliği. Ekrana cümle olarak GİTMEZ (goz 09-28: "[Errno 13] …"
                  kullanıcıya düşüyordu) — arayüz `title`'a koyar, kritik bulgu günlüğe onunla yazılır.

    `ilk_kurulum`→ ok=False ama arıza değil: kullanıcı bu adımı HENÜZ yapmadı (geliştirici kararı 09-28 —
                  ilk açılışta kırmızı "çalışmıyor" alarm, davet değil). `seviye` geriye uyum için
                  KRITIK kalır (eski tüketici "çalışmıyor" okur), `durum` "kurulum" olur; günlüğe yazılmaz.

    `durum` tek alan: iyi · uyari · kritik · olculemedi · kurulum.
    """
    if ok:
        durum = OLCULEMEDI if olculemedi else "iyi"
    elif ilk_kurulum:
        durum = KURULUM
    else:
        durum = KRITIK if seviye == KRITIK else UYARI
    return {
        "kimlik": kimlik,
        "baslik": baslik,
        "ok": ok,
        "durum": durum,
        "olculemedi": bool(ok and olculemedi),
        "seviye": seviye if not ok else BILGI,
        "detay": detay,
        "cozum": cozum if not ok else "",
        "cozum_url": cozum_url if not ok else "",
        "otomatik_duzeltilebilir": bool(otomatik and not ok),
        "kurulum_teklifi": kurulum if (kurulum and not ok) else None,
        "yonlendir": yonlendir if not ok else None,
        "teknik": _kisa(teknik) if teknik else "",
    }


def _kisa(metin) -> str:
    """Ev dizinini `~` yap — ekrana ve kopyalanan günlüğe kullanıcı adı gitmesin."""
    from app.services.error_log import evi_kisalt
    return evi_kisalt(str(metin))


def _hata_cumlesi(e: BaseException) -> str:
    """İstisnayı kullanıcı cümlesine çevir; ham metin `teknik` alanına gider."""
    if isinstance(e, PermissionError):
        return M("saglik.hata-izin")
    if isinstance(e, FileNotFoundError):
        return M("saglik.hata-bulunamadi")
    if isinstance(e, OSError) and getattr(e, "errno", None) == 28:
        return M("saglik.hata-disk-dolu")
    return M("saglik.hata-genel")


def _model_adi(model: str, gruplar: list | None = None) -> str:
    """ANAHTAR'ın gösterdiği okunur ad ("Gemma 4 26B — ücretsiz (önerilen)").

    Kaynak ANAHTAR ile aynı: `/api/llm/models` grupları (canlı etiket ya da `label_k` kataloğu),
    sonra sabit doğrulanmış/ücretli listeler. Listede olmayan (kaldırılmış) modelde kimlikten
    türetilen yedek: "meta-llama/llama-3.3-70b-instruct:free" → "Llama 3.3 70b instruct — ücretsiz".
    """
    try:
        from app.api.llm_config_api import VERIFIED_FREE, PAID_PICKS
        sabit = [{"options": list(VERIFIED_FREE) + list(PAID_PICKS)}]
    except Exception:
        sabit = []
    for g in (gruplar or []) + sabit:
        for o in g.get("options") or []:
            if o.get("id") == model:
                if o.get("label"):
                    return o["label"]
                if o.get("label_k"):
                    return M(o["label_k"])
    ad = (model or "").split("/")[-1]
    ucretsiz = ad.endswith(":free")
    ad = ad.removesuffix(":free").replace("-", " ").replace("_", " ").strip()
    ad = (ad[:1].upper() + ad[1:]) if ad else (model or "—")
    return M("saglik.model-ucretsiz-ad", ad=ad) if ucretsiz else ad


def _yazilabilir_yap(yol: Path) -> None:
    """Klasörü oluştur ve GERÇEKTEN yaz-sil. Başarısızsa istisna fırlatır.

    Denetim ile onarım aynı ölçüyü kullanır: onarım eskiden yalnız `mkdir` yapıp
    "oluşturuldu" diyordu — klasör zaten var ama salt okunursa mkdir sessizce geçer,
    kullanıcıya düzeldi yalanı söylenirdi.
    """
    yol.mkdir(parents=True, exist_ok=True)
    deneme = yol / ".yazma-denemesi"
    deneme.write_text("ok", encoding="utf-8")
    deneme.unlink(missing_ok=True)


# Microsoft'un resmi VC++ Redistributable indiricisi. Yalnız kullanıcı SAĞLIK
# panelinden bilerek tıklarsa çalışır — arka planda asla çağrılmaz.
VCREDIST_URL = "https://aka.ms/vs/17/release/vc_redist.x64.exe"

def _vcredist_teklifi() -> dict | None:
    """VC++ Redist kurulum teklifi — yalnız Windows'ta. Linux/mac kullanıcısına
    Windows kurucusu önerilmez (aynı `except` dalı her platformda çalışıyor)."""
    if platform.system() != "Windows":
        return None
    return {
        "kimlik": "vcredist",
        "etiket": M("saglik.vcredist-etiket"),
        "uyari": M("saglik.vcredist-uyari"),
    }


# ── Tekil denetimler ────────────────────────────────────────────────────────

def _denetle_veri_dizini() -> dict:
    """Yazılabilir veri dizini var mı?

    ADIM 24'te dört modül kendi kod dizinine yazıyordu; paketlenmiş üründe orası
    salt okunur olduğu için ayarlar/rutinler/takvim/izleme sessizce kaybolmuştu.
    """
    from app.config import DATA_DIR
    yol = Path(DATA_DIR)
    try:
        _yazilabilir_yap(yol)
        return _sonuc("veri_dizini", M("saglik.baslik-veri-dizini"), True, BILGI,
                      M("saglik.veri-dizini-iyi", yol=_kisa(yol)))
    except Exception as e:
        return _sonuc(
            "veri_dizini", M("saglik.baslik-veri-dizini"), False, KRITIK,
            M("saglik.veri-dizini-yazilamiyor", yol=_kisa(yol), neden=_hata_cumlesi(e)),
            M("saglik.veri-dizini-cozum"),
            otomatik=True, teknik=f"{type(e).__name__}: {e}",
        )


def _denetle_onnxruntime() -> dict:
    """Semantik hafıza (Ultra) · OCR · Silero VAD bu kütüphaneye bağlı."""
    try:
        import onnxruntime  # noqa: F401
        return _sonuc("onnxruntime", M("saglik.baslik-onnxruntime"), True, BILGI,
                      M("saglik.onnx-hazir"))
    except Exception as e:
        eksik = _windows_runtime_eksigi()
        detay = M("saglik.onnx-acilamadi")
        teknik = f"{type(e).__name__}: {e}"
        windows = platform.system() == "Windows"
        if eksik:
            # Runtime DLL'leri v0.5.5'ten beri paketin İÇİNDE gelir. Burada eksikse
            # sorun kullanıcının Windows'u değil, paketin kendisidir.
            teknik += M("saglik.onnx-eksik-dll", dll=", ".join(eksik))
            cozum = M("saglik.onnx-cozum-paket")
        elif windows:
            cozum = M("saglik.onnx-cozum-vcredist")
        else:
            # VC++ Windows paketidir; Linux/mac'te "aşağıdaki düğmeyle kur" düğmesiz kalıyordu (09-28)
            cozum = M("saglik.motor-cozum-diger")
        return _sonuc(
            "onnxruntime", M("saglik.baslik-onnxruntime"), False, KRITIK, detay,
            cozum, VCREDIST_URL if windows else "", kurulum=_vcredist_teklifi(), teknik=teknik,
        )


def _denetle_stt() -> dict:
    """Sesle yazma — faster-whisper + ctranslate2 native katmanı."""
    from app.services.stt import stt_status
    st = stt_status()
    if st["available"] and st["model_present"]:
        return _sonuc("stt", M("saglik.baslik-stt"), True, BILGI, M("saglik.stt-hazir"))
    if not st["available"]:
        hata = st.get("last_error")
        return _sonuc(
            "stt", M("saglik.baslik-stt"), False, KRITIK,
            M("saglik.stt-motor-yok"),
            M("saglik.stt-cozum-vcredist") if platform.system() == "Windows" else M("saglik.motor-cozum-diger"),
            VCREDIST_URL if platform.system() == "Windows" else "", kurulum=_vcredist_teklifi(), teknik=hata or "",
        )
    return _sonuc(
        "stt", M("saglik.baslik-stt"), False, UYARI,
        M("saglik.stt-model-yok"),
        M("saglik.stt-model-cozum"),
    )


def _denetle_ffmpeg() -> dict:
    """Ses ön işleme — 2026-08-02'den beri ffmpeg CLI'ına BAĞLI DEĞİL.

    Dönüşüm artık PyAV ile Python içinde yapılıyor (`stt.ensure_wav`); PyAV
    faster-whisper'ın zaten getirdiği bir bağımlılık ve iki bundle'da da var.
    ffmpeg yalnızca geliştirme yedeği.

    🔴 Eski hâli kullanıcıyı yanlış bilgilendiriyordu: Windows'ta ffmpeg hiç
    olmadığı için panel HER kullanıcıda sarı uyarı gösteriyordu ve "sessizlik
    algılama devre dışı" diyordu — o gerçekten devre dışıydı, ama artık değil.
    """
    try:
        import av  # noqa: F401
        return _sonuc("ffmpeg", M("saglik.baslik-ffmpeg"), True, BILGI,
                      M("saglik.ffmpeg-pyav"))
    except Exception:
        pass
    if shutil.which("ffmpeg"):
        return _sonuc("ffmpeg", M("saglik.baslik-ffmpeg"), True, BILGI,
                      M("saglik.ffmpeg-yedek"))
    return _sonuc(
        "ffmpeg", M("saglik.baslik-ffmpeg"), False, UYARI,
        M("saglik.ffmpeg-yok"),
        M("saglik.ffmpeg-cozum"),
    )


def _denetle_llm_anahtar() -> dict:
    from app.services.llm import has_openrouter_key, aktif_saglayici
    from app.services import llm_providers as _lp
    sag = _lp.kayit(aktif_saglayici())
    # 🔴 Yerel sağlayıcıda (Ollama) anahtar diye bir şey yok. Bu dal olmadan
    # yerel modele geçmiş kullanıcı sağlık panelinde KRİTİK bir "anahtar
    # girilmemiş" hatası görüyordu — hem yanlış, hem de onu tam da kaçındığı
    # bulut anahtarını almaya yönlendiriyordu (2026-08-08).
    if sag is not None and sag.yerel:
        return _sonuc("llm_anahtar", M("saglik.baslik-llm-anahtar"), True, BILGI,
                      M("saglik.anahtar-gerekmiyor", saglayici=sag.ad))
    # B4 (11-14, temiz kurulum denetimi): bilgisayardaki `claude` programıyla (claude_code) sohbet
    # anahtarsız çalışırken panel KRİTİK "Anahtar girilmemiş — Yuki cevap veremez" diyordu.
    if aktif_saglayici() == "claude_code":
        return _sonuc("llm_anahtar", M("saglik.baslik-llm-anahtar"), True, BILGI,
                      M("saglik.anahtar-gerekmiyor", saglayici="Claude Code"))
    if has_openrouter_key():
        girili = ", ".join(
            (_lp.kayit(k).ad if _lp.kayit(k) else k) for k in _lp.anahtarli_kimlikler()
        )
        return _sonuc("llm_anahtar", M("saglik.baslik-llm-anahtar"), True, BILGI,
                      M("saglik.anahtar-ayarli", saglayicilar=girili))
    return _sonuc(
        "llm_anahtar", M("saglik.baslik-llm-anahtar"), False, KRITIK, M("saglik.anahtar-yok"),
        M("saglik.anahtar-cozum"),
        sag.anahtar_url if sag else "https://openrouter.ai/keys",
        yonlendir="key", ilk_kurulum=True,
    )


def _denetle_ucretsiz_kota() -> dict:
    """Ücretsiz kademe kullanılıyorsa SINIRI ÖNCEDEN söyle.

    🔴 2026-08-05: ürün ücretsiz kotanın rakamını hiçbir yerde yazmıyordu.
    Kredisiz OpenRouter hesabı günde 50 istek alır; dolduğunda 429 gelir ve
    kullanıcı bunu "Yuki bozuldu" diye okur. Bu bir arıza değil, **beklenen**
    bir sınır — beklenen bir sınırı önden söylemek, sonradan hata mesajıyla
    açıklamaktan ucuz. Bu yüzden seviye BİLGİ, `ok=True`: uyarı değil, bilgi.
    """
    from app.services.llm import get_runtime_config, aktif_saglayici
    from app.services import llm_providers as _lp
    sag = _lp.kayit(aktif_saglayici())
    model = (get_runtime_config().get("model") or "")
    if sag is None:
        # Tüketici (`orchestrator._kota_metni`) METNE değil bu bayrağa bakar —
        # eskiden "bilgi yok" alt dizgisini arıyordu, metin çevrilince kırılırdı.
        return {**_sonuc("llm_kota", M("saglik.baslik-llm-kota"), True, BILGI,
                         M("saglik.kota-bilinmiyor"), olculemedi=True), "kota_bilinmiyor": True}
    if not sag.ucretsiz:
        return {**_sonuc("llm_kota", M("saglik.baslik-llm-kota"), True, BILGI,
                         M("saglik.kota-ucretli-servis", saglayici=sag.ad)), "kota_bilinmiyor": True}
    if sag.kimlik == "openrouter" and not model.endswith(":free"):
        return _sonuc("llm_kota", M("saglik.baslik-llm-kota"), True, BILGI,
                      M("saglik.kota-ucretli-model", model=_model_adi(model)))
    if sag.kimlik == "openrouter":
        # Kartta tek kısa cümle (goz 09-28: `:free`, "kota hesap bazlı değil" jargonu); ayrıntı ANAHTAR'da.
        return _sonuc("llm_kota", M("saglik.baslik-llm-kota"), True, BILGI, M("saglik.kota-openrouter"))
    # Sağlayıcının kota metni `llm_providers.py`'de TR yaşar; katalog onu çevirir
    # (`llm_config_api._sag_metin` ile aynı kural: çeviri yoksa kaynağa düş).
    anahtar = f"saglayici.{sag.kimlik}.ucretsiz"
    cev = M(anahtar)
    return _sonuc("llm_kota", M("saglik.baslik-llm-kota"), True, BILGI,
                  sag.ucretsiz if cev == anahtar else cev)


async def _denetle_llm_model() -> dict:
    """Seçili model sağlayıcıda HÂLÂ var mı?

    🔴 07-31'de tam olarak bu patladı: önerilen üç ücretsiz model kaldırılmıştı,
    kullanıcı `404 No endpoints found` alıyordu. Bu denetim onu önceden yakalar.

    ⚠️ 2026-08-05: denetim yalnız **OpenRouter** için yapılır. Canlı liste
    OpenRouter'ın herkese açık ucundan gelir; Google/OpenAI modelini o listeye
    karşı ölçmek her seferinde "model sağlayıcıda yok" diye YANLIŞ KRİTİK üretir.
    Denetleyemediğimiz yerde hüküm vermiyoruz — bunu söylüyoruz.
    """
    from app.services.llm import get_runtime_config, aktif_saglayici
    from app.services import llm_providers as _lp
    aktif = (get_runtime_config().get("model") or "").strip()
    _sag = _lp.kayit(aktif_saglayici())
    # Düzelt yalnız OpenRouter'da: canlı ücretsiz liste yalnız orada var. Başka serviste
    # "düzelt" demek ya servisi OpenRouter'a çevirmek (eski onarım bunu yapıyordu) ya da
    # denenmemiş bir model yazmak olurdu — ikisi de yalan. Orada ANAHTAR'a götürürüz.
    _or = aktif_saglayici() == "openrouter"
    if not aktif:
        return _sonuc("llm_model", M("saglik.baslik-llm-model"), False, UYARI,
                      M("saglik.model-secilmemis"),
                      M("saglik.model-sec-cozum-oto") if _or else M("saglik.model-sec-cozum"),
                      otomatik=_or, yonlendir=None if _or else "key")
    # Yerel sağlayıcı: burada canlı liste GERÇEKTEN denetlenebilir (localhost),
    # üstelik `ollama rm` ile modelin kaybolması sahada görülebilir bir durum.
    if _sag is not None and _sag.yerel:
        try:
            from app.api.llm_config_api import _yerel_modeller
            gruplar = await _yerel_modeller(_sag)
        except Exception as e:
            return _sonuc(
                "llm_model", M("saglik.baslik-llm-model"), False, KRITIK,
                M("saglik.model-ollama-ulasilamadi", model=aktif),
                M("saglik.model-ollama-cozum"), teknik=str(e)[:200],
            )
        kurulu = {o["id"] for g in gruplar for o in g["options"]}
        if aktif in kurulu or f"{aktif}:latest" in kurulu:
            return _sonuc("llm_model", M("saglik.baslik-llm-model"), True, BILGI,
                          M("saglik.model-yerel-kurulu", model=aktif))
        return _sonuc(
            "llm_model", M("saglik.baslik-llm-model"), False, KRITIK,
            M("saglik.model-yerel-yok", model=aktif),
            M("saglik.model-yerel-cozum", model=aktif),
        )
    if not _or:
        # Denetleyemediğimiz yerde hüküm yok — ama "yolunda" da yok: ölçülemedi.
        return _sonuc("llm_model", M("saglik.baslik-llm-model"), True, BILGI,
                      M("saglik.model-liste-disi", model=aktif,
                        saglayici=_sag.ad if _sag else aktif_saglayici()),
                      olculemedi=True)
    try:
        from app.api.llm_config_api import _fetch_live_groups
        gruplar = await _fetch_live_groups()
    except Exception as e:
        logger.debug("model listesi alınamadı: %s", e)
        return _sonuc("llm_model", M("saglik.baslik-llm-model"), True, BILGI,
                      M("saglik.model-liste-alinamadi", model=_model_adi(aktif)), olculemedi=True,
                      teknik=aktif)
    canli = {o["id"] for g in gruplar for o in g["options"]}
    if aktif in canli:
        return _sonuc("llm_model", M("saglik.baslik-llm-model"), True, BILGI,
                      M("saglik.model-duruyor", model=_model_adi(aktif, gruplar)), teknik=aktif)
    return _sonuc(
        "llm_model", M("saglik.baslik-llm-model"), False, KRITIK,
        M("saglik.model-kalkti", model=_model_adi(aktif, gruplar)),
        M("saglik.model-kalkti-cozum"),
        otomatik=True, teknik=aktif,
    )


def _denetle_disk() -> dict:
    from app.config import DATA_DIR
    try:
        bos = shutil.disk_usage(str(DATA_DIR)).free
    except Exception as e:
        return _sonuc("disk", M("saglik.baslik-disk"), True, BILGI,
                      M("saglik.disk-olculemedi", neden=_hata_cumlesi(e)), olculemedi=True,
                      teknik=f"{type(e).__name__}: {e}")
    gb = bos / (1024 ** 3)
    if gb >= 2:
        return _sonuc("disk", M("saglik.baslik-disk"), True, BILGI,
                      M("saglik.disk-bos", gb=f"{gb:.1f}"))
    return _sonuc(
        "disk", M("saglik.baslik-disk"), False, UYARI, M("saglik.disk-az", gb=f"{gb:.1f}"),
        M("saglik.disk-cozum"),
    )


def _onnxruntime_dizini() -> Path | None:
    """`onnxruntime/capi` dizini — modülü ÇALIŞTIRMADAN bul.

    `import onnxruntime` zaten patlıyor olabilir; `find_spec` native katmanı
    yüklemeden yalnız yolu verir.
    """
    try:
        import importlib.util
        spec = importlib.util.find_spec("onnxruntime")
        if spec and spec.submodule_search_locations:
            return Path(list(spec.submodule_search_locations)[0]) / "capi"
    except Exception:
        pass
    return None


def _windows_runtime_eksigi() -> list[str]:
    """`onnxruntime`'ın bulamayacağı MSVC runtime DLL'lerini listele.

    ÖLÇÜM (2026-08-01 → 2026-08-02, satılan zip'in import tabloları taranarak):
    `onnxruntime.dll` ve `onnxruntime_pybind11_state.pyd` **statik** olarak
    `msvcp140.dll` + `msvcp140_1.dll` ister. `msvcp140_1.dll` pakete hiç
    girmiyordu; `msvcp140.dll` vardı ama BAŞKA wheel'lerin dizinlerindeydi.

    🔴 Doğru arama yeri: **tüketicinin kendi dizini.** Windows bir `.pyd`'yi
    `LOAD_WITH_ALTERED_SEARCH_PATH` ile yükler → uygulama dizini yerine o
    dosyanın kendi dizini aranır. Bu fonksiyonun eski hâli `sys.prefix`'e
    bakıyordu; orada bulunması onnxruntime için bir şey ifade etmez.
    `vcruntime140*` istisnadır: onları `python.exe` açılışta kendi dizininden
    yükler, süreçte "zaten bellekte" olurlar.

    Boş liste = paket bütün. Dolu liste = paket eksik/bozuk indirilmiş
    (build adımı `scripts/vendor-msvc-runtime.py` atlanmış olabilir).
    """
    if platform.system() != "Windows":
        return []
    capi = _onnxruntime_dizini()
    kok = Path(sys.executable).parent
    sistem = Path(os.environ.get("SystemRoot", r"C:\Windows")) / "System32"

    eksik = []
    for d, aranacak in (
        ("msvcp140.dll", [capi, sistem]),
        ("msvcp140_1.dll", [capi, sistem]),
        ("vcruntime140.dll", [capi, kok, sistem]),
        ("vcruntime140_1.dll", [capi, kok, sistem]),
    ):
        bulundu = False
        for yer in aranacak:
            if yer is None:
                continue
            try:
                if (yer / d).exists():
                    bulundu = True
                    break
            except Exception:
                continue
        if not bulundu:
            eksik.append(d)
    return eksik


# ── Genel akış ──────────────────────────────────────────────────────────────

async def calistir() -> dict:
    """Tüm denetimleri koştur ve özet döndür."""
    sonuclar = [
        _denetle_veri_dizini(),
        _denetle_llm_anahtar(),
        await _denetle_llm_model(),
        _denetle_ucretsiz_kota(),
        _denetle_onnxruntime(),
        _denetle_stt(),
        _denetle_ffmpeg(),
        _denetle_disk(),
    ]
    kurulum = [s for s in sonuclar if s.get("durum") == KURULUM]   # arıza değil: günlüğe yazılmaz
    kritik = [s for s in sonuclar if not s["ok"] and s["seviye"] == KRITIK and s not in kurulum]
    uyari = [s for s in sonuclar if not s["ok"] and s["seviye"] == UYARI]
    olculemedi = [s for s in sonuclar if s.get("olculemedi")]

    # Kritik bulguları günlüğe düşür — destek istendiğinde geçmiş elimizde olsun.
    # 🔴 TEKİL: panel her açılışta denetliyor (GET); eskiden aynı bulgu her seferinde
    # yeniden yazılıyor, günlük aynı satırla doluyordu. Aynı bulgu 24 saatte bir kez.
    try:
        from app.services import error_log
        for s in kritik:
            ayrinti = s["detay"] + (f" · {s['teknik']}" if s.get("teknik") else "")
            error_log.kaydet_tekil("kurulum", s["kimlik"], ayrinti, seviye="error")
    except Exception:
        pass

    if kritik:
        durum = KRITIK
    elif kurulum:
        durum = KURULUM
    elif uyari:
        durum = UYARI
    elif olculemedi:
        durum = OLCULEMEDI
    else:
        durum = "iyi"

    return {
        "ok": not kritik and not kurulum,   # kurulmamış Yuki cevap veremez — "ok" demek yalan olurdu
        "durum": durum,
        "sistem": f"{platform.system()} {platform.release()}",
        "kritik_sayisi": len(kritik),
        "uyari_sayisi": len(uyari),
        "olculemedi_sayisi": len(olculemedi),
        "kurulum_sayisi": len(kurulum),
        "bekleyen_yeniden_baslatma": _bekleyen_yeniden_baslatma(),
        "otomatik_duzeltilebilir": [s["kimlik"] for s in sonuclar if s["otomatik_duzeltilebilir"]],
        "kurulum_teklifleri": sorted({s["kurulum_teklifi"]["kimlik"]
                                      for s in sonuclar if s["kurulum_teklifi"]}),
        "denetimler": sonuclar,
    }


def _bekleyen_yeniden_baslatma() -> list[dict]:
    """Kaydedilmiş ama ancak yeniden başlayınca geçerli olacak ayarlar (süreç belleği)."""
    try:
        from app.api.settings_api import bekleyen_yeniden_baslatma
        return bekleyen_yeniden_baslatma()
    except Exception:
        return []


async def onar(kimlik: str) -> dict:
    """Otomatik onarılabilir bir bulguyu düzelt.

    Yalnız güvenli ve geri alınabilir işler. Sistem paketi kurmak, ayar değiştirmek
    BU MODÜLÜN İŞİ DEĞİL — onu kullanıcıya anlatırız, onun yerine yapmayız.
    """
    from app.services import error_log

    if kimlik == "veri_dizini":
        from app.config import DATA_DIR
        yol = Path(DATA_DIR)
        vardi = yol.is_dir()
        try:
            _yazilabilir_yap(yol)
            return {"ok": True, "mesaj": M("saglik.onar-klasor-hazir", yol=_kisa(yol))}
        except Exception as e:
            error_log.kaydet("kurulum", "onarim_basarisiz", f"veri_dizini: {_kisa(e)}")
            # Klasör varsa sorun oluşturmak değil YAZMAK: "oluşturulamadı" demek yanlış teşhis olurdu.
            anahtar = "saglik.onar-klasor-yazilamiyor" if (vardi or yol.is_dir()) else "saglik.onar-klasor-olmadi"
            return {"ok": False, "mesaj": M(anahtar, yol=_kisa(yol), neden=_hata_cumlesi(e))}

    if kimlik == "llm_model":
        return await _onar_model()

    return {"ok": False, "mesaj": M("saglik.onar-desteklenmiyor", kimlik=kimlik)}


async def _onar_model() -> dict:
    """Seçili model kalkmışsa AYNI serviste çalışan bir modele geç — sağlayıcı + model birlikte kalıcı.

    🔴 2026-09-28 ( panel 10): eski onarım `set_runtime_config("openrouter", …)`
    yazıyordu — Google ya da OpenAI kullanan kullanıcının servisini sessizce OpenRouter'a
    çeviriyor, `.env`'e yalnız LLM_MODEL yazıyordu (yeniden başlayınca eski servis + yeni
    model = bozuk ikili). Şimdi: yalnız OpenRouter'da (canlı ücretsiz liste yalnız orada var)
    ve ANAHTAR'ın `/api/llm/sec`'i gibi LLM_PROVIDER + LLM_MODEL birlikte yazılır. Başka
    serviste dürüstçe "burada otomatik düzeltemiyorum, ANAHTAR'dan seç" deriz.
    """
    from app.services import error_log
    from app.services import llm_providers as _lp
    from app.services.llm import aktif_saglayici, set_runtime_config
    from app.api import llm_config_api as _api

    saglayici = aktif_saglayici()
    if saglayici != "openrouter":
        sag = _lp.kayit(saglayici)
        return {"ok": False, "yonlendir": "key",
                "mesaj": M("saglik.onar-model-elle", saglayici=sag.ad if sag else saglayici)}
    try:
        gruplar = await _api._fetch_live_groups()
    except Exception as e:
        error_log.kaydet("kurulum", "onarim_basarisiz", f"llm_model: {e}")
        return {"ok": False, "yonlendir": "key", "mesaj": M("saglik.onar-liste-alinamadi")}
    adaylar = [o["id"] for g in gruplar for o in g["options"] if o["id"].endswith(":free")]
    if not adaylar:
        return {"ok": False, "yonlendir": "key", "mesaj": M("saglik.onar-ucretsiz-model-yok")}
    yeni = _api.DEFAULT_FREE_MODEL if _api.DEFAULT_FREE_MODEL in adaylar else adaylar[0]
    set_runtime_config(saglayici, yeni)
    try:
        _api._persist_env("LLM_PROVIDER", saglayici)
        _api._persist_env("LLM_MODEL", yeni)
    except Exception as e:
        # Bu oturumda geçerli ama kalıcı değil — "düzeldi" deyip yeniden başlayınca bozulmasın
        error_log.kaydet("kurulum", "onarim_kalici_degil", f"llm_model: {_kisa(e)}")
        return {"ok": True, "kalici": False, "model": yeni,
                "mesaj": M("saglik.onar-model-gecici", model=_model_adi(yeni, gruplar))}
    return {"ok": True, "kalici": True, "model": yeni,
            "mesaj": M("saglik.onar-model-degisti", model=_model_adi(yeni, gruplar))}


async def kur(kimlik: str) -> dict:
    """Kullanıcının makinesine bir şey KURAN aksiyon — `onar`'dan bilerek ayrı.

    Neden ayrı bir fonksiyon: bu modülün kuralı *"otomatik onarım yalnız güvenli ve
    geri alınabilir işler için; kullanıcının makinesine paket kurmak bu modülün işi
    değildir"*. O kural duruyor. Buradaki iş **otomatik değil** — kullanıcı SAĞLIK
    panelinde ne olacağı yazan bir düğmeye bilerek basar, Windows da ayrıca yönetici
    onayı sorar. `onar()` ile aynı çatıya konulsaydı toplu/otomatik bir onarım
    akışına sessizce karışabilirdi.

    v0.5.5'ten beri runtime DLL'leri paketin içinde geldiği için bu yol normalde
    HİÇ gerekmez; bozuk indirme / sıra dışı sistem için **yedek**tir.
    """
    from app.services import error_log

    if kimlik != "vcredist":
        return {"ok": False, "mesaj": M("saglik.kur-bilinmeyen", kimlik=kimlik)}
    if platform.system() != "Windows":
        return {"ok": False, "mesaj": M("saglik.kur-yalniz-windows")}

    import subprocess
    import tempfile
    import urllib.request

    try:
        hedef = Path(tempfile.gettempdir()) / "vc_redist.x64.exe"
        logger.info("VC++ Redistributable indiriliyor: %s", VCREDIST_URL)
        with urllib.request.urlopen(VCREDIST_URL, timeout=120) as cevap:
            veri = cevap.read()
        if len(veri) < 1_000_000:            # ~25 MB bekleniyor; kısa cevap = hata sayfası
            raise RuntimeError(M("saglik.kur-dosya-kucuk", bayt=len(veri)))
        hedef.write_bytes(veri)
    except Exception as e:
        error_log.kaydet("kurulum", "vcredist_indirilemedi", str(e))
        return {"ok": False, "mesaj": M("saglik.kur-indirilemedi", hata=str(e), url=VCREDIST_URL)}

    try:
        # `/passive`: ilerleme çubuğu GÖRÜNÜR. Bilerek `/quiet` değil — kullanıcının
        # makinesinde sessizce iş yapmıyoruz. UAC istemini Windows kendi çıkarır.
        p = subprocess.run([str(hedef), "/install", "/passive", "/norestart"],
                           timeout=900, capture_output=True)
    except Exception as e:
        error_log.kaydet("kurulum", "vcredist_calistirilamadi", str(e))
        return {"ok": False, "mesaj": M("saglik.kur-baslatilamadi", hata=str(e))}

    # Microsoft çıkış kodları
    if p.returncode == 0:
        return {"ok": True, "mesaj": M("saglik.kur-kuruldu")}
    if p.returncode == 1638:
        return {"ok": True, "mesaj": M("saglik.kur-zaten-yeni")}
    if p.returncode == 3010:
        return {"ok": True, "mesaj": M("saglik.kur-yeniden-baslat")}
    if p.returncode == 1602:
        return {"ok": False, "mesaj": M("saglik.kur-iptal")}
    error_log.kaydet("kurulum", "vcredist_basarisiz", f"çıkış kodu {p.returncode}")  # i18n-istisna: kalıcı hata günlüğü kaydı (destek teşhisi), kullanıcı mesajı değil
    return {"ok": False, "mesaj": M("saglik.kur-basarisiz", kod=p.returncode, url=VCREDIST_URL)}
