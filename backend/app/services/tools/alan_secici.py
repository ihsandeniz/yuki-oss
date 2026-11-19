"""Araç şeması alan seçici — turda gerekmeyen araçların şemasını LLM'e göndermemek.

Araç şemaları her araçlı turda girdi token'ı olarak ödenir; çoğu araç çoğu turda
gereksizdir. Bu modül kullanıcının o turdaki cümlesine bakıp **ilgili alanların**
araçlarını çekirdek kümeye ekler.

- Alanlar araç ADINDAN kalıpla türetilir; yeni araç kendiliğinden bir alana düşer.
  Kapsama denetimi: `denetle()`.
- Çekirdek ölçümden gelir: `data/used_tools.json` (uygulamanın kendi tuttuğu başarılı
  araç kullanımı, `skill_events`) + oturum altyapısı. Dosya yoksa ya da boşsa
  daraltma YAPILMAZ, tam şema gider — yeni kurulumda davranış değişmez.
- Şemadan çıkmak yeteneği yok etmez: dispatch kendi zincirine bakar, onay kapısı ve
  kural motoru olduğu gibi kalır. Global `TOOLS` listesine dokunulmaz.
- Sessiz yeteneksizliğe karşı üç korkuluk: çekirdek her turda açık · model eksik
  alanı `arac_alani_ac` ile aynı turda açabilir (ve sistem promptunda bu söylenir) ·
  `YUKI_TAM_SEMA=1` ile mekanizma tamamen kapanır.
"""

from __future__ import annotations

import json
import logging
import os
import re
from contextvars import ContextVar
from pathlib import Path

logger = logging.getLogger(__name__)

_VERI = Path(__file__).resolve().parents[3] / "data"

# Aktif turun şeması — `arac_alani_ac` bunu YERİNDE genişletir. LLMRunner aynı liste
# objesini tuttuğu ve her adımda `tools=self.tools` gönderdiği için (runner.py:198)
# genişletme aynı turun bir sonraki adımında LLM'e ulaşır: ek tur gerekmez.
_aktif_sema: ContextVar[list | None] = ContextVar("_aktif_sema", default=None)


# ── Alanlar ────────────────────────────────────────────────────────────────
# arac: araç ADINA uygulanır · mesaj: kullanıcının cümlesine uygulanır
# ⚠️ Türkçe ünsüz yumuşaması: kökü mutasyondan ÖNCE kes (`hatırlat` → `hatirlat`
# değil `hat[ıi]rlat`; `renk`→`rengi` gibi kelimelerde kök kısaltılır). Kalıplar
# IGNORECASE koşar ama aksan duyarlıdır — her iki yazımı da yaz.
ALANLAR: dict[str, dict[str, str]] = {
    "takvim": {
        "arac": r"event|reminder|takvim|calendar",
        "mesaj": r"takvim|randevu|toplant|etkinlik|hat[ıi]rlat|ajanda|saat ka[cç]ta|alarm",
    },
    "todo": {
        "arac": r"todo",
        "mesaj": r"yap[ıi]lacak|g[oö]rev|todo|liste[yn]e ekle|i[sş] listesi",
    },
    "fitness": {
        "arac": r"fitness|workout|meal|exercise|kilo",
        "mesaj": r"antren|spor|kilo|kalori|egzersiz|beslen|[oö]tçün|yemek kaydet",
    },
    "dosya": {
        "arac": r"(read|write|append|search|diff)_file|list_directory|compress|extract",
        "mesaj": r"dosya|klas[oö]r|dizin|kaydet|oku|yaz[ıi]l[ıi]|belge|pdf",
    },
    "sistem": {
        "arac": r"monitor_|ping_host|package|battery|public_ip|check_service|check_updates|system_info",
        "mesaj": r"cpu|ram|disk|s[uü]re[cç]|pil\b|batarya|sistem|\bip\b|ip adres|servis|paket|ping|"
                 r"[sş]arj|yava[sş]|zorluyor|tak[ıi]ld|gecikme|kurulu|s[uü]r[uü]m|hangi adres",
    },
    "uygulama": {
        "arac": r"open_application|list_modes",
        "mesaj": r"uygulama|program|a[cç]\b|ba[sş]lat|mod(lar)?\b",
    },
    "medya": {
        "arac": r"media|youtube|volume|show_media|list_media|galeri",
        "mesaj": r"m[uü]zik|[sş]ark[ıi]|ses(i|in)?\b|video|[cç]al\b|duraklat|galeri|foto",
    },
    "web": {
        "arac": r"web_search|browse_web",
        "mesaj": r"internet|web|site|google|ara[sş]t[ıi]r|bak(ar m[ıi]s[ıi]n)?.*internet",
    },
    "wiki": {
        "arac": r"wiki_",
        "mesaj": r"wiki|ar[sş]iv|bilgi taban|not defter",
    },
    # ⚠️ Türkçe ünsüz yumuşaması: "harita" ekle değişmez ama "konum"→"konumu",
    # "deprem"→"depremi" olur; kökü mutasyondan ÖNCE kes (bu dosyanın kendi dersi).
    "harita": {
        "arac": r"map_goto|map_layer|map_status",
        "mesaj": r"harita|konum|nerede|g[oö]ster.*harita|deprem|yang[ıi]n|volkan|"
                 r"yanarda[gğ]|u[cç]ak|u[cç]u[sş]|uydu|iss\b|enlem|boylam|koordinat",
    },
    "hafiza": {
        "arac": r"memory_",
        "mesaj": r"hat[ıi]rl|unut|an[ıi]|haf[ıi]za|ne demi[sş]tim",
    },
    "kripto": {
        "arac": r"crypto|portfolio|stock|coin|budget|exchange_rate",
        "mesaj": r"kripto|borsa|portf[oö]y|coin|hisse|btc|eth|bitcoin|dolar|euro|d[oö]viz|\bkur\b|harca|b[uü]t[cç]e",
    },
    "not": {
        "arac": r"journal|note",
        "mesaj": r"\bnot\b|notlar|g[uü]nl[uü]|jurnal|defter|unutmayay|bir yere yaz",
    },
    "panel": {
        "arac": r"panel|split|switch_tab|list_tabs",
        "mesaj": r"panel|sekme|taray[ıi]c[ıi]|site a[cç]|b[oö]l\b|kanvas",
    },
    "otomasyon": {
        "arac": r"job|skill_|routine|n8n|run_team|start_mode|game|delegate",
        "mesaj": r"g[oö]rev ba[sş]lat|skill|beceri|otomasyon|ajan|tak[ıi]m|n8n|kuyru[gğ]a|"
                 r"rutin|sabahlar[ıi]|her sabah|kal[ıi]c[ıi] olsun",
    },
    "gorsel": {
        "arac": r"screenshot|ocr|qr|image|vision|gaze",
        "mesaj": r"ekran|g[oö]r[uü]nt[uü]|resim|g[oö]rsel|ocr|qr|bak(ar m[ıi]s[ıi]n)? ekran",
    },
    "cevre": {
        "arac": r"weather|earthquake|datetime|smart_home",
        "mesaj": r"hava|deprem|sars[ıi]nt|saat|tarih|bug[uü]n ne|ev(deki)? [ıi][sş][ıi]k|termostat",
    },
    "bildirim": {
        "arac": r"notification|clipboard",
        "mesaj": r"bildirim|pano|kopyala|yap[ıi][sş]t[ıi]r|uyar[ıi] g[oö]nder",
    },
    "konu_takibi": {
        "arac": r"watch(ed)?_topic|unwatch",
        "mesaj": r"konu takip|haber|izle(meye)? al|takibe al",
    },
    "git": {
        "arac": r"^git_",
        "mesaj": r"\bgit\b|commit|repo|depo|branch|dal\b",
    },
    # "masaüstüne gel / git" — masaüstü Yuki'yi aç/kapat (services/masaustu_yuki.py)
    "masaustu": {
        "arac": r"^masaustu_yuki$",
        "mesaj": r"masa[uü]st[uü]|yan[ıi]ma gel",
    },
    # "Yuki bak / ne görüyorsun" — kamera görüşü (GORUS kapalıysa araç zaten şemada yok)
    "kamera": {
        "arac": r"^kameraya_bak$",
        "mesaj": r"\bbak\b|bakar m[ıi]s[ıi]n|ne g[oö]r[uü]yorsun|kamera|elimde ne",
    },
    "dil": {
        "arac": r"set_language|language",
        "mesaj": r"dil(i|ini)? de[gğ]i[sş]|t[uü]rk[cç]e konu[sş]|japonca|ingilizce",
    },
}

# Kullanım verisinde görünmese de çekirdekte kalması gerekenler: bunlar olmadan
# çok karakterli/çok sekmeli bir oturumda diğer araçlar yanlış bağlama gider.
_ALTYAPI = {"list_tabs", "switch_tab", "switch_character", "list_characters", "arac_alani_ac"}


def _arac_adi(t: dict) -> str:
    return (t.get("function") or {}).get("name") or t.get("name") or ""


def _kullanilmis_adlar() -> set[str]:
    """3 aylık gerçek kullanım (`data/used_tools.json`). Okunamazsa BOŞ değil None
    davranışı: çekirdek daralırsa şema yanlış budanır, o yüzden hata hâlinde
    çağıran tam şemaya düşer."""
    p = _VERI / "used_tools.json"
    try:
        v = json.loads(p.read_text(encoding="utf-8"))
        return set(v.keys()) if isinstance(v, dict) else set(v)
    except Exception as e:  # dosya yok/bozuk → ölçüm yok demektir
        logger.warning("[alan_secici] used_tools.json okunamadı (%s) — tam şema gönderilecek", e)
        return set()


def alanlari_esle(mesaj: str) -> set[str]:
    """Kullanıcı cümlesi hangi alanlara işaret ediyor?"""
    if not mesaj:
        return set()
    return {ad for ad, k in ALANLAR.items() if re.search(k["mesaj"], mesaj, re.IGNORECASE)}


def _alan_araclari(alanlar: set[str], tools: list) -> set[str]:
    if not alanlar:
        return set()
    kalip = re.compile("|".join(ALANLAR[a]["arac"] for a in alanlar), re.IGNORECASE)
    return {ad for t in tools if (ad := _arac_adi(t)) and kalip.search(ad)}


def sema_sec(mesaj: str, tools: list) -> list:
    """Bu tur LLM'e gidecek araç şemasını seç. `tools` DEĞİŞTİRİLMEZ, yeni liste döner.

    Kapalıysa (`YUKI_TAM_SEMA=1`) ya da ölçüm verisi yoksa tam şema döner —
    daraltma yalnız *ölçülmüş* bir çekirdek üzerine kurulur.
    """
    if os.getenv("YUKI_TAM_SEMA", "").strip() in ("1", "true", "True"):
        _aktif_sema.set(list(tools))
        return _aktif_sema.get()

    kullanilmis = _kullanilmis_adlar()
    if not kullanilmis:
        _aktif_sema.set(list(tools))
        return _aktif_sema.get()

    cekirdek = kullanilmis | _ALTYAPI
    eslesen = alanlari_esle(mesaj)
    secilen = cekirdek | _alan_araclari(eslesen, tools)

    sema = [t for t in tools if _arac_adi(t) in secilen]
    # Boş/aşırı dar sonuç bir kusurdur, sessizce geçme: tam şemaya dön.
    if len(sema) < len(_ALTYAPI):
        logger.warning("[alan_secici] seçim aşırı daraldı (%d araç) — tam şemaya dönülüyor", len(sema))
        sema = list(tools)

    _aktif_sema.set(sema)
    logger.info("[alan_secici] %d/%d araç · alan: %s",
                len(sema), len(tools), ", ".join(sorted(eslesen)) or "—")
    return sema


def yonlendirme_notu(sema: list, tools: list) -> str:
    """Şema daraltıldıysa modele yedek yolu SÖYLE. Daraltılmadıysa boş döner.

    Bu satır olmadan model görmediği aracın eksik olduğunu fark etmez ve
    dolambaçlı yollar dener; araç açıklaması tek başına yetmiyor.

    Maliyet ~45 token — kazancın (%50+) yanında ihmal edilebilir.
    """
    if len(sema) >= len(tools):
        return ""
    return (
        "\n\nARAÇ ŞEMASI DARALTILMIŞ: şu an araçlarının yalnız bir bölümünü görüyorsun. "
        "Bir işi yapacak aracı listede bulamıyorsan ONU YAPAMAYACAĞINI VARSAYMA ve "
        "dolambaçlı yollar (kabuk komutu vb.) denemeden önce `arac_alani_ac` ile ilgili "
        "alanı aç — araç o an şemana eklenir ve aynı turda çağırabilirsin."
    )


def alan_ac(alan: str, tools: list) -> int:
    """`arac_alani_ac` aracının gövdesi: aktif turun şemasını YERİNDE genişletir.

    Yerinde olması şart — LLMRunner liste objesini `__init__`'te saklar ve her
    adımda `tools=self.tools` gönderir. Yeni liste atamak o referansı değiştirmez,
    genişletme ise aynı turun bir sonraki adımında görünür (ek tur yok).
    """
    sema = _aktif_sema.get()
    if sema is None or alan not in ALANLAR:
        return 0
    mevcut = {_arac_adi(t) for t in sema}
    kalip = re.compile(ALANLAR[alan]["arac"], re.IGNORECASE)
    eklenen = [t for t in tools
               if (ad := _arac_adi(t)) and ad not in mevcut and kalip.search(ad)]
    sema.extend(eklenen)
    logger.info("[alan_secici] '%s' alanı açıldı (+%d araç)", alan, len(eklenen))
    return len(eklenen)


def denetle(tools: list) -> dict:
    """Aracın KENDİSİNİ sına: hangi araçlar hiçbir alana düşmüyor, çekirdek ne kadar.

    Hiçbir alana düşmeyen ve çekirdekte de olmayan araç, mekanizma açıkken
    **hiçbir turda görünmez** — sessiz yeteneksizliğin tam kaynağı. Bu fonksiyon
    onu görünür kılar.
    """
    kullanilmis = _kullanilmis_adlar()
    cekirdek = kullanilmis | _ALTYAPI
    tum_alan_kalibi = re.compile("|".join(k["arac"] for k in ALANLAR.values()), re.IGNORECASE)
    adlar = [a for t in tools if (a := _arac_adi(t))]
    yetim = [a for a in adlar if a not in cekirdek and not tum_alan_kalibi.search(a)]
    return {
        "toplam": len(adlar),
        "cekirdek": len([a for a in adlar if a in cekirdek]),
        "alansiz_ve_cekirdek_disi": sorted(yetim),
        "alan_sayisi": len(ALANLAR),
    }


if __name__ == "__main__":  # pragma: no cover — elle denetim
    # 🪤 `python app/services/tools/alan_secici.py` ÇALIŞMAZ: Python script'in
    # dizinini path'in başına koyar ve `tools/calendar.py` stdlib `calendar`'ı
    # gölgeler (httpx → http.cookiejar → calendar.timegm patlar). Doğru koşum:
    #   cd backend && venv/bin/python -m app.services.tools.alan_secici
    from app.services.tools.dispatcher import TOOLS  # noqa: E402

    d = denetle(TOOLS)
    print(f"araç: {d['toplam']} · çekirdek: {d['cekirdek']} · alan: {d['alan_sayisi']}")
    if d["alansiz_ve_cekirdek_disi"]:
        print(f"\n🔴 hiçbir alana düşmeyen {len(d['alansiz_ve_cekirdek_disi'])} araç "
              f"(mekanizma açıkken GÖRÜNMEZ):")
        for a in d["alansiz_ve_cekirdek_disi"]:
            print(f"   {a}")
    else:
        print("🟢 her araç ya çekirdekte ya bir alanda")
