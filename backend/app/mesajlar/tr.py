"""Kullanıcı metinleri — Türkçe (KAYNAK dil).

Bir anahtar başka dilde eksikse buraya düşülür; yani buradaki her anahtar
DOLU olmak zorundadır. Biçim: `alan.oge`, yer tutucu `{ad}`.

🔴 `ui.*` bölümü arayüz etiketlerinin TEK kaydıdır. Cümlelere gömme —
`{ui_ayar}` ile çağır (gerekçe: `__init__.py` başlığı).
"""
from __future__ import annotations

METINLER: dict[str, str] = {
    # ── Arayüz etiketleri — cümlelere GÖMÜLMEZ, enterpolasyonla girer ─────
    "ui.ayar": "⚙ AYAR",
    "ui.anahtar": "🔑 ANAHTAR",
    "ui.saglik": "🩺 SAĞLIK",
    "ui.kopyala": "📋 KOPYALA",
    "ui.lisans": "🎫 LİSANS",
    "ui.plan": "PLAN",
    "ui.google": "GOOGLE",
    "ui.ses": "Ses",
    # 🔴 KOMUT TOKENİ — arayüzde görünen etiket ve burada TANINAN ön ek aynı
    # dizgedir. `websocket.py` gelen metni bununla eşleştirip LLM'i atlıyor;
    # frontend `komut.ogren.etiket` ile aynı olmak ZORUNDA, yoksa kullanıcı
    # komutu yazar, hiçbir şey kaydedilmez ve hata da almaz.
    # Kapı: `test_komut_ogren_oneki_FRONTEND_ILE_AYNI`.
    "ui.komut-ogren": "/öğren",
    "ui.menu-anahtar": "Anahtar",
    "ui.menu-ses": "Ses & TTS",

    # ── Global hata işleyicileri (429 / 500) ──────────────────────────────
    "hata.hiz-siniri": (
        "Çok sık denedin — {ne_kadar} bekleyip tekrar dene. "
        "Bu anahtarınla ilgili bir sorun DEĞİL."
    ),
    "hata.sure-dakika": "{n} dakika",
    "hata.sure-saniye": "{n} saniye",
    "hata.sure-kisa": "kısa bir süre",
    "hata.beklenmeyen": (
        "Beklenmeyen bir hata oluştu. Tekrar dene; sürerse "
        "{ui_ayar} → {ui_saglik} → {ui_kopyala} ile hata günlüğünü paylaş."
    ),


    # ── Açılış denetimi ───────────────────────────────────────────────────
    "acilis.anahtar-yok": (
        "OPENROUTER_API_KEY yok — sohbet için {ui_ayar} → {ui_anahtar}'dan bir "
        "anahtar gir (openrouter.ai/keys, ücretsiz). Anahtar girilene kadar "
        "sohbet çalışmaz."
    ),
    "acilis.hafiza-kapali": (
        "Hafıza devre dışı — MEMORY_BACKEND=pgvector seçili ama DATABASE_URL boş. "
        "Gömülü hafıza için .env'de MEMORY_BACKEND=sqlite yaz (kurulum gerektirmez)."
    ),

    # ── Kapalı özellik kapıları ───────────────────────────────────────────────────
    "kademe.plan-pro": (
        "{ui_plan} ekranı bu kurulumda kapalı. Görevlerini "
        "Yuki'ye söyleyerek yönetebilirsin ('süt al diye görev ekle')."
    ),
    "kademe.plan-pro-baslik": "{ui_plan} ekranı kapalı",
    "kademe.plan-pro-govde": (
        "Görevlerini Yuki'ye söyleyerek yönetebilirsin —<br>"
        "<i>“süt al diye görev ekle”</i>, <i>“bugünkü görevlerim ne?”</i>"
    ),

    # ── Anahtar / sağlayıcı ───────────────────────────────────────────────
    "anahtar.saglayici-yok": (
        "LLM anahtarı ayarlanmadı. {ui_ayar} → {ui_anahtar}'dan bir sağlayıcı "
        "seçip anahtarını gir."
    ),
    "anahtar.yerel-yanit-yok": (
        "{saglayici} yanıt vermiyor. Kurulu ve çalışıyor mu? Kurulum: {url}"
    ),
    "anahtar.saglayici-anahtari-yok": (
        "{saglayici} anahtarı ayarlanmadı. {ui_ayar} → {ui_anahtar}'dan "
        "{saglayici} anahtarını gir{url}."
    ),

    # ── Sekme / karakter araçları (LLM'e de döner) ────────────────────────
    "sekme.gecersiz": (
        "Geçersiz sekme: '{sekme}'. Bu uygulamada yalnız şu sekmeler var: {liste}"
    ),
    "sekme.kapali": (
        "{ad} sekmesi bu kurulumda kapalı. Görevlerini bana "
        "söyleyerek yönetebilirsin: 'yapılacaklara ... ekle', 'görevlerim'."
    ),
    "sekme.gecildi": "{ad} sekmesine geçildi.",
    "sekme.mevcut": "Mevcut sekmeler: {liste}",
    "sekme.kapali-eki": "kapalı",
    "karakter.gecersiz": "Geçersiz karakter: '{karakter}'. Geçerli karakterler: {liste}",
    "karakter.kilitli": (
        "'{karakter}' karakteri bu kurulumda kapalı."
    ),
    "karakter.gecilemedi": "Karaktere geçilemedi: '{karakter}'.",

    # ── LLM sağlayıcı hataları ────────────────────────────────────────────
    "llm.anahtar-gecersiz": (
        "{saglayici} anahtarın geçersiz ya da iptal edilmiş. "
        "{ui_ayar} → {ui_anahtar}'dan yeni bir anahtar gir ({url})."
    ),
    "llm.model-erisimi-yok": (
        "Bu anahtarın seçili modele erişimi yok. {ui_ayar} → {ui_anahtar}'dan "
        "başka bir model seç ya da anahtarı değiştir."
    ),
    "llm.ulasilamadi": "LLM sağlayıcısına ulaşılamadı — internet bağlantını kontrol et.",

    # ── `/öğren` komutu (websocket.py — LLM atlanır, beceri belleğine yazılır)
    # ⚠️ Örnek cümle komut tokenini ENTERPOLASYONLA alıyor: gömülü olsaydı
    # İngilizce metin "/öğren …" diye olmayan bir komutu örnek gösterirdi.
    "ogren.kaydedildi": "Öğrendim: {bilgi} ✦",
    "ogren.ne-ogreneyim": "Ne öğreneyim? Örn: {ui_komut_ogren} kahveyi sade severim",
    "ogren.model-yok": "Bunu kaydedemedim: hafıza anlama modeli kurulu değil (README → Optional → Semantic memory model, EMBED_ONNX_DIR).",
    "ogren.kaydedilemedi": "Bunu kaydedemedim — hafızaya yazılırken bir hata oldu. Ayrıntı backend günlüğünde.",
    "llm.bakiye-bitti": (
        "{saglayici} bakiyen bitmiş. Hesabına kredi ekle ya da "
        "{ui_ayar} → {ui_anahtar}'dan ücretsiz bir model/sağlayıcı seç."
    ),
    "llm.model-bulunamadi": (
        "Seçili model bulunamadı — {ui_ayar} → {ui_anahtar}'dan listeden "
        "başka bir model seç."
    ),
    "llm.anahtar-bicimi": (
        "Yapay zekâ anahtarın geçersiz biçimde. OpenRouter anahtarları `sk-or-` "
        "ile başlar. Lisans anahtarını buraya yapıştırmış olabilirsin — o "
        "{ui_ayar} → {ui_lisans} sekmesine girilir."
    ),
    "llm.anthropic-anahtari-yok": (
        "Hata: Anthropic anahtarı yok. {ui_ayar} → {ui_anahtar}'dan gir "
        "(console.anthropic.com/settings/keys)."
    ),
    "llm.reddedildi-detayli": "LLM sağlayıcısı isteği reddetti (HTTP {kod}): {detay}",
    "llm.reddedildi": "LLM sağlayıcısı isteği reddetti (HTTP {kod}).",

    # ── Kota (429) — GÜNLÜK ile DAKİKALIK ayrımı gövdeden gelir ───────────
    "llm.kota-gunluk": (
        "Günlük ücretsiz istek kotan doldu — beklemekle geçmez, kota ertesi gün "
        "sıfırlanır."
    ),
    "llm.kota-openrouter-eki": (
        " OpenRouter'da kredisiz hesap günde 50 istek alır; hesabına bir kez 10$ "
        "kredi eklersen bu 1.000'e çıkar (yeni hesap açmak işe yaramaz, kota "
        "geneldir)."
    ),
    "llm.kota-alternatif": (
        " Alternatif: {ui_ayar} → {ui_anahtar}'dan başka bir sağlayıcı/model seç."
    ),
    "llm.kota-dakikalik": "Çok hızlı istek gönderildi — birkaç saniye bekleyip tekrar dene.",
    "llm.kota-ucretsiz-eki": (
        " (Ücretsiz modellerde dakikalık sınır dar; günlük kotan da olabilir.)"
    ),

    # ── Sağlayıcı metinleri (FAZ 3 · Dalga 2 · Blok 4B, 2026-09-19) ───────
    # 🔴 Kaynağı `services/llm_providers.py::SAGLAYICILAR` — bu katalog onu
    # ÇEVİRİYOR, yeniden yazmıyor. Türkçe değerler dataclass'takiyle BİREBİR
    # aynı olmak zorunda (kapı: test_saglayici_metni_KAYNAKLA_AYNI); ayrışırsa
    # ölçüm değişince arayüz bayatlar ve kimse fark etmez.
    "saglayici.anthropic.not": "⚠ Claude Pro/Max aboneliği API değildir — console.anthropic.com'da ayrıca bakiye gerekir.",
    "saglayici.cerebras.ucretsiz": "Ücretsiz kullanım hakkı var (günlük token sınırıyla).",
    "saglayici.chutes.ucretsiz": "Ücretsiz kullanım hakkı var (günlük istek sınırıyla).",
    "saglayici.deepseek.not": "Ucuz ama ücretli — kredi yüklemek gerekir.",
    "saglayici.google.not": "AI Studio anahtarı. Vertex AI (Google Cloud) anahtarı DEĞİL.",
    "saglayici.google.ucretsiz": "Google AI Studio anahtarının ücretsiz kullanım hakkı var (model başına günlük/dakikalık istek sınırıyla).",
    "saglayici.groq.not": "Çok hızlı çıkarım. Model listesi dar.",
    "saglayici.groq.ucretsiz": "Ücretsiz kullanım hakkı var (dakikalık/günlük istek ve token sınırıyla).",
    "saglayici.mistral.ucretsiz": "Ücretsiz (deneysel) kullanım hakkı var.",
    "saglayici.nebius.ucretsiz": "Kayıtta deneme bakiyesi veriyor.",
    "saglayici.ollama.ad": "Ollama (kendi bilgisayarın)",
    "saglayici.ollama.not": "Önce ollama.com/download'dan Ollama'yı kur, sonra `ollama pull llama3.1` ile bir model indir. Anahtar gerekmez.",
    "saglayici.ollama.ucretsiz": "kota ve istek sınırı yok, model senin bilgisayarında çalışır. Karşılığı donanım: 8B'lik bir model için ~8 GB RAM (ya da VRAM) ister ve bulut modellerinden yavaştır.",
    "saglayici.ollama.uyari": "Yuki'nin sistem promptu + araç tanımları ≈ 4.100 token. Ollama'nın varsayılan bağlam penceresi çoğu kurulumda bundan küçüktür ve prompt sessizce kırpılır → yanıtlar biçimsiz gelir. Sunucuyu `OLLAMA_CONTEXT_LENGTH=8192 ollama serve` ile başlat. Ayrıca küçük modeller (8B) araç çağırabilse de Yuki'nin yanıt biçimini bulut modelleri kadar tutarlı izlemez.",
    "saglayici.openai.not": "⚠ ChatGPT Plus aboneliği API değildir — platform.openai.com'da ayrıca bakiye gerekir.",
    "saglayici.openrouter.not": "Tek anahtarla yüzlerce model. Ücretsiz başlamak için en kolayı.",
    "saglayici.openrouter.ucretsiz": "Ücretsiz (`:free`) modeller kredi yüklemeden çalışır. Sınır: dakikada 20, günde 50 istek. Hesabına bir kez 10$ kredi alırsan günlük sınır 1.000'e çıkar. Yeni hesap/anahtar açmak sınırı değiştirmez — kota hesap bazlı değil, genel.",
    "saglayici.together.ucretsiz": "Bazı modellerde ücretsiz kullanım sunuyor.",
    "yerel.ulasilamadi": "{adres} adresinde Ollama'ya ulaşılamadı — kurulu ve çalışıyor mu? Kurulum: ollama.com/download, sonra terminalde `ollama serve`. (teknik: {teknik})",

    # ── Eksik isteğe bağlı kütüphane (Blok 6B, 2026-09-19) ────────────────
    "pydeps.eksik": "Gerekli kütüphane inmemiş: {moduller}. Özelliği ilk kez açtığında indirilir.",

    # ── Açılış kilidi (FAZ 3 · Dalga 2 · Blok 6, 2026-09-19) ──────────────
    # 🔴 Bu metinler GÜVENLİK odasının panelinde ve KİLİT EKRANINDA görünür.
    #    Panelin frontend yarısı Blok 6'da çevrildi; bunlar onun backend
    #    yarısı — `d.detail` olarak aynı toast'a düşüyorlar (Blok 4B dersi:
    #    bir panel, onu DOLDURAN her kaynak çevrilene kadar çevrilmiş sayılmaz).
    "kilit.kurulu-degil": "Uygulama kilidi kurulu değil.",
    "kilit.parola-yanlis": "Parola yanlış.",
    "kilit.mevcut-parola-yanlis": "Mevcut parola yanlış.",
    "kilit.kaydedilemedi": "Parola kaydedilemedi.",
    "kilit.uzunluk": "Parola {min}-{max} karakter olmalı.",
    # 🔑 Çoğul: TR'de sayıdan sonra ek GELMEZ ("3 deneme hakkın kaldı"),
    #    İngilizce'de gelir → `-cogul` yalnız `en.py`'de tanımlı (Mc kuralı).
    "kilit.kalan-hak": "{n} deneme hakkın kaldı.",

    # 🔴 Dört ayrı anahtar, iki şablon DEĞİL. Eski kod cümleyi kelime
    #    yerleştirerek kuruyordu (`{yol} girişi … {alt} gir`) ve o yol yalnız
    #    Türkçe'de çalışıyordu: "yüzünle gir" ile "parolayla gir" farklı
    #    ek taşıyor, İngilizce'de ise alternatif cümlenin sonunda bambaşka bir
    #    yapı istiyor ("use your face instead"). Kelime yerleştirmeli tek
    #    şablon, üçüncü dilde sessizce bozuk cümle üretirdi.
    "giris-kilidi.parola-alt-var": "Parola girişi {kez} hatalı denemeden sonra {dk} dk kapatıldı — yüzünle gir.",
    "giris-kilidi.yuz-alt-var": "Yüz tanıma girişi {kez} hatalı denemeden sonra {dk} dk kapatıldı — parolayla gir.",
    "giris-kilidi.parola-alt-yok": "Parola girişi {dk} dk kapalı. Diğer yol da kapalı — süre bitene kadar bekle.",
    "giris-kilidi.yuz-alt-yok": "Yüz tanıma girişi {dk} dk kapalı. Diğer yol da kapalı — süre bitene kadar bekle.",

    # ── Hafıza uçları (FAZ 3 · Dalga 2 · Blok 8, 2026-09-20) ──────────────
    # Bu dördü Hafıza Yöneticisi odasının EKRANINA düşüyor: panel `detail`
    # alanını doğrudan bildirime basıyor (`_memmgrHata`). Uç çevrilmeseydi
    # İngilizce ekranda Türkçe bir sebep görünürdü — odanın kendisi temiz
    # sayılırken. (Blok 4B'nin dersi: bir paneli onu DOLDURAN her kaynak
    # çevrilene kadar çevrilmiş sayma.)
    "hafiza.devre-disi": (
        "Hafıza sistemi devre dışı — .env'de MEMORY_BACKEND=sqlite yaz "
        "(gömülü, kurulum gerektirmez) ya da pgvector için DATABASE_URL ver."
    ),
    "hafiza.semantik-ultra": (
        "Semantik hafıza bu kurulumda kapalı; Yuki "
        "kısa dönem (lite) hafıza kullanır."
    ),
    "hafiza.model-yok": (
        "Hafıza anlama modeli kurulu değil; anı eklenemez. Modeli indirip EMBED_ONNX_DIR ile "
        "göster (README → Optional → Semantic memory model). Sohbet bu arada kısa dönem hafızayla sürer."
    ),
    "hafiza.gecersiz-karakter": "Geçersiz character_key: '{kod}'. Geçerli değerler: {gecerli}",
    "hafiza.ani-bulunamadi": "Anı bulunamadı: {id}",
    # `importance` / `content` alan adlarıdır — istemcinin göndereceği şey,
    # çevrilirse geliştirici yanlış alanı arar (`.env` anahtarlarıyla aynı kural).
    "hafiza.alan-eksik": "importance veya content belirtilmeli.",

    # ── Ayar yazma yolu (FAZ 3 · Dalga 2 · Blok 9, 2026-09-20) ────────────
    # Bu beşi HER odanın ekranına düşüyor: `hqSet` başarısız yanıtın
    # `detail`ini doğrudan bildirime basıyor (`_ucHatasi`). SES odasında
    # ses seçmek tam bu yoldan geçiyor (`PERSONA_VOICES`).
    # ⚠️ Ayar ANAHTARI (`{anahtar}`) çevrilmez: kullanıcının .env'de arayacağı
    #    ad odur — çevirmek onu olmayan bir anahtarı aramaya yollar.
    "ayar.bilinmeyen-anahtar": "Bilinmeyen/izinsiz ayar: {anahtar}",
    "ayar.gecersiz-dil": "Geçersiz dil: '{deger}'. Seçenekler: {secenekler}",
    "ayar.ses-haritasi-json": "Ses haritası geçerli JSON değil.",
    "ayar.bilinmeyen-karakter": "Bilinmeyen karakter: {karakter}",
    "ayar.gecersiz-ses": "Geçersiz ses adı: '{ses}' (örn. 'tr-TR-EmelNeural')",
    "ayar.kaydedilemedi": "Kaydedilemedi: {sebep}",

    # ── TTS uçları (Blok 9) ───────────────────────────────────────────────
    # 🔴 Bu dördü 2026-09-20'ye kadar EKRANA HİÇ ULAŞMIYORDU: arayüz
    # `throw new Error(r.status)` yazıyor, ekranda "TTS hatası: Error: 415"
    # görünüyordu. Önce sebep görünür yapıldı, sonra çevrildi — sırası ters
    # olsaydı çevrilmiş bir metni kimse görmeyecekti.
    "ses.test-metni-uzun": "Test metni en fazla 300 karakter olabilir.",
    # Kaynak adı bilerek duruyor (2026-08-02 dersi): yukarı akışın metnini
    # sızdıran uç, KİMİN konuştuğunu da söylemek zorunda.
    "ses.tts-hatasi": "TTS hatası [kaynak: TTS zinciri]: {sebep}",
    "ses.ref-bicim": "WAV veya MP3 formatı gerekli.",
    "ses.ref-buyuk": "Dosya çok büyük (en fazla 10 MB).",

    # ── Ayar sıfırlama (Blok 10) ──────────────────────────────────────────
    # Blok 9'un açık maddesiydi: bu iki `detail` yalnız `sifirla` bölümünü
    # ilan eden odada çizilir, SES odasının ekranında yoktu.
    # ⚠️ `?confirm=true` bir sorgu parametresidir — çevrilmez, aynen yazılır.
    "ayar.sifirla-onay": "Onay gerekli: ?confirm=true",
    "ayar.sifirlama-basarisiz": "Sıfırlama başarısız",
    # 09-27: boş kutu dolu varsayılanı ezmez · kullanılamayan ayar yazılmaz
    "ayar.masaustu-acilamadi": "Masaüstü Yuki açılamadı: {hata}",
    "ayar.masaustu-kapanmadi": "Masaüstü Yuki kapanmadı: {hata}",
    "ayar.bos-olamaz": "Bu ayar boş bırakılamaz — varsayılana dönmek için 'varsayılana dön'ü kullan.",
    "ayar.kullanilamaz": "Bu ayar şu an kullanılamaz: {sebep}",

    # ── Hatırlatıcı (Blok 10) ─────────────────────────────────────────────
    # 🔴 `her {n} dakikada` metni 2026-09-20'ye kadar KAYDA yazılıyordu
    # (`reminders.json::human`), yani dil değişse bile o kaydın metni
    # Türkçe donuyordu. Artık kayıt `interval` (yapı) tutuyor, cümle OKUMA
    # anında kuruluyor. Aynı ders sözlük tarafında `_EVOL_LABELS`'te.
    "hatirlatici.her-saniye": "her saniyede",
    "hatirlatici.her-dakika": "her dakikada",
    "hatirlatici.her-saat": "her saatte",
    "hatirlatici.her-gun": "her günde",
    "hatirlatici.her-n-saniye": "her {n} saniyede",
    "hatirlatici.her-n-dakika": "her {n} dakikada",
    "hatirlatici.her-n-saat": "her {n} saatte",
    "hatirlatici.her-n-gun": "her {n} günde",
    "hatirlatici.gecersiz-zaman": "Geçersiz zaman ifadesi: {ifade}",
    "hatirlatici.bulunamadi": "Hatırlatıcı bulunamadı",
    # 🔑 Bu metin TELEFONA gider ve `push_notifications` tablosuna yazılır —
    # yani BİLDİRİM odasının "Gönderilmiş bildirimler" listesinde de görünür.
    # Odanın ekranını dolduran kaynaklardan biri burasıdır.
    "hatirlatici.bildirim": "Hatırlatma: {mesaj}",

    # ── Telefon bildirimi (Blok 10) ───────────────────────────────────────
    "bildirim.pro-ozelligi": "Telefon bildirimleri bu kurulumda kapalı.",
    "bildirim.test-metni": "Test bildirimi — bağlantı çalışıyor!",
    # `str(e)` yerine: ham istisna metni kullanıcıya teşhis değil korku verir
    # (CLAUDE.md § "kullanıcıya ham teknik metin GÖSTERİLMEZ"). Sebep log'a.
    "bildirim.anahtar-uretilemedi": (
        "Bildirim anahtarları üretilemedi — telefon bildirimi bu kurulumda "
        "kullanılamıyor."
    ),

    # ⚪ Onay / panel köprüsü uçları — ekranda GÖRÜLMEDİ (Blok 10 turu
    # BİLDİRİM odasını ölçtü, onay akışını değil). Yine de kataloğa alındı:
    # dosyanın kapısı artık istisnasız ("ham TR detail kalmadı") ve bayat
    # bir süzgeç yerine ölçülmemiş bir kalem bırakıyoruz.
    "onay.talep-yok": "Onay talebi bulunamadı veya süresi doldu",

    # ── Lisans — 🎫 LİSANS paneli + etkinleştirme toast'ı ────────
    # `LicenseError` metni değil bu anahtarları taşır; `status()` her okumada
    # aktif dilde yeniden üretir (licensing/verify.py başlığı).
    "lisans.bos": "Lisans anahtarı boş.",
    "lisans.etkinlestirildi": "{kademe} paketi etkinleştirildi.",
    # 09-28 (HQ panel 9): kullanıcı dili — "nokta ayracı", "expires alanı", "grace", "şema" gibi
    # geliştirici sözcükleri kullanıcıya gidiyordu. Metin ne olduğunu + ne yapılacağını söyler.
    "lisans.format-hatali": (
        "Bu bir Yuki lisans anahtarına benzemiyor — satın alma e-postandaki anahtarın "
        "tamamını yapıştır."
    ),
    "lisans.okunamadi": (
        "Lisans anahtarı okunamadı — kopyalarken bir kısmı eksik kalmış olabilir. "
        "Anahtarın tamamını (boşluksuz) yeniden yapıştır."
    ),
    "lisans.imza-gecersiz": (
        "Bu anahtar doğrulanamadı — bozulmuş ya da Yuki için verilmemiş. "
        "Satın alma e-postandaki anahtarı kullan."
    ),
    "lisans.icerik-bozuk": (
        "Lisans anahtarının içeriği bozuk — anahtarı yeniden yapıştır, "
        "sorun sürerse satın alma e-postandaki anahtarı kullan."
    ),
    "lisans.baska-urun": "Bu anahtar başka bir ürün için — Yuki anahtarını yapıştır.",
    "lisans.sema-desteklenmiyor": (
        "Bu anahtar Yuki'nin bu sürümüyle açılamıyor — Yuki'yi güncelle, sonra yeniden dene."
    ),
    "lisans.bitis-okunamadi": (
        "Lisansın bitiş tarihi okunamadı — satın alma e-postandaki anahtarı yeniden yapıştır."
    ),
    "lisans.grace-kaldi": "Lisansının süresi doldu — {n} gün içinde yenilemezsen bazı özellikler kapanır.",
    "lisans.grace-bitti": (
        "Lisansının süresi {n} gün önce doldu, bazı özellikler kapandı. "
        "Yenilediğinde yeni anahtarı buraya yapıştır."
    ),
    "lisans.env-arac-listesi": "Geliştirici kurulumu — araçlar elle seçildi.",
    "lisans.env-tam": "Geliştirici kurulumu — her şey açık.",
    "lisans.kaldirilamadi": (
        "Lisans kaldırılamadı: dosya silinemedi, Yuki hâlâ {kademe} paketinde. "
        "Yuki'yi kapatıp açtıktan sonra yeniden dene."
    ),
    # ──  ⑤ yüz giriş / canlılık (face_api · face_liveness · face_multi_auth · face_store)
    "canlilik.talimat": "Kameraya bak ve {n} kez göz kırp.",
    "canlilik.alinmadi": "Canlılık meydan okuması alınmadı.",
    "canlilik.alinmadi-once": "Canlılık meydan okuması alınmadı. Önce /api/face/liveness/challenge çağır.",
    "canlilik.bulunamadi": "Meydan okuma bulunamadı veya süresi doldu.",
    "canlilik.kullanildi": "Bu meydan okuma zaten kullanıldı — yenisini iste.",
    "canlilik.suresi-doldu": "Meydan okumanın süresi doldu — yenisini iste.",
    "canlilik.baska-istemci": "Meydan okuma başka bir istemciye ait.",
    "canlilik.parca-alindi": "Bu parça zaten alındı.",
    "canlilik.kare-tavani": "Kare tavanı aşıldı ({tavan}).",
    "canlilik.dizi-buyuk": "Kare dizisi çok büyük.",
    "canlilik.gecersiz": "Meydan okuma artık geçerli değil.",
    "canlilik.yetersiz-kare": "Yetersiz kare ({kare}/{en_az}). Kameranın önünde biraz daha kal.",
    "canlilik.kopya": "Kareler birbirinin kopyası — canlı görüntü gerekiyor.",
    "canlilik.yuz-yok": "Karelerin çoğunda yüz görünmüyor ({yuzsuz}/{toplam}).",
    "canlilik.yuzlu-az": "Yüz görünen kare sayısı yetersiz.",
    "canlilik.goz-noktasi-yok": "Canlılık ölçülemedi: yüz modeli göz noktalarını vermedi.",
    "canlilik.hareket-yok": "Gözlerde hareket yok — canlı görüntü gerekiyor.",
    "canlilik.kirpma-uyusmadi": "{istenen} kırpma istendi, {kirpma} algılandı.",
    "canlilik.birden-fazla": "Dizide birden fazla kişi görünüyor — tek kişi olarak tekrar dene.",
    "canlilik.sinirlar": "Göz kırpma basılı/ekran fotoğrafını eler; video oynatmayı ve deepfake'i elemez.",
    "canlilik.dogrulanamadi": "Canlılık doğrulanamadı.",
    "canlilik.kapali": "canlılık kapalı (FACE_LIVENESS_REQUIRED=false)",
    "yuz.devre-disi": "Yüz tanıma devre dışı (FACE_AUTH_ENABLED).",
    "yuz.tur": "Sadece JPEG/PNG desteklenir.",
    "yuz.dosya-buyuk": "Dosya çok büyük (maks {mb} MB).",
    "yuz.bos-dosya": "Boş dosya.",
    "yuz.islem-hatasi": "{islem} sırasında bir hata oluştu.",
    "yuz.islem.kare": "Kare gönderimi",
    "yuz.islem.dogrulama": "Doğrulama",
    "yuz.islem.yuz-kaydi": "Yüz kaydı",
    "yuz.islem.kayit": "Kayıt",
    "yuz.islem.tarama": "Tarama",
    "yuz.islem.liste": "Liste",
    "yuz.islem.kalite": "Kalite raporu",
    "yuz.islem.kayit-silme": "Kayıt silme",
    "yuz.islem.silme": "Silme",
    "yuz.kilit-yok": "Açılış kilidi kurulu değil — yüzle giriş kullanılamaz.",
    "yuz.kayitli-yuz-yok": "Kayıtlı yüz bulunamadı. Önce yüzünü kaydet.",
    "yuz.kalan-hak": "{n} deneme hakkın kaldı.",
    "yuz.belirsiz": "Yüz net eşleşmedi — ışığı düzeltip tekrar dene ya da parolanı kullan.",
    "yuz.eslesmedi": "Yüz eşleşmedi.",
    "yuz.kaydedildi": "Yüz kaydedildi ({sahip} · {n} görüntü).",
    "yuz.isim-bos": "İsim boş olamaz.",
    "yuz.goruntu-okunamadi": "Görüntü okunamadı.",
    "yuz.bulunamadi": "Yüz bulunamadı. Kameranı yüzüne doğrult.",
    "yuz.maks-kisi": "Maksimum kişi sayısına ({n}) ulaşıldı.",
    "yuz.uyari-cok-yuz": "Karede {n} yüz var — en büyüğü kaydedildi. Yanlış kişiyi kaydetmemek için tek başına çek.",
    "yuz.uyari-uzak": "Bu kare '{ad}' kişisinin mevcut kayıtlarına uzak (mesafe {mesafe}). Farklı bir kişi ya da çok kötü ışık olabilir.",
    "yuz.uyari-zaten-kayitli": "Bu yüz zaten '{ad}' olarak kayıtlı (mesafe {mesafe}). Yeni bir kişi mi kaydediyorsun, yoksa isim mi yanlış?",
    "yuz.uyari-daha-yakin": "Dikkat: bu kare '{yabanci}' kişisine ({yabanci_mesafe}) '{ad}' kişisinden ({mesafe}) daha yakın.",
    "yuz.sahip-yok": "Yüz sahibi tanımlı değil. Parola ile girip 'Yüzümü kaydet' yap ya da FACE_OWNER_NAME ayarla.",
    "yuz.kare-yok": "Kare gönderilmedi.",
    "yuz.kayit-yok": "#{id} numaralı kayıt bulunamadı.",
    "yuz.kisi-yok": "'{ad}' adında kayıtlı kişi bulunamadı.",
    "yuz.sahip-silme-onay": "'{ad}' sahip — silinirse yüzle giriş kapanır. Onay gerekli.",
    "yuz.tek-kayit": "'{ad}' kişisinin tek kaydı bu — silmek kişiyi tanınmaz yapar. Kişiyi tamamen silmek için kişi kartını kullan.",
    # ──  ⑧ kalan backend metinleri (elle; birlestir.py'nin bloğu DIŞINDA)
    "saglik.kota-bilinmiyor": "Bu servisin günlük sınırı bilinmiyor.",
    "ekip.kota": "Ücretsiz kotan: {detay}",
    "ekip.maliyet-mesaj": "Ekip bu işi {gorevler} uzmana bölecek. Tahmini maliyet: {en_az}-{en_cok} model isteği.",
    "ekip.maliyet-baslik": "Ekip çalışması — maliyet onayı",
    "llm.claude-cli-yok": "'claude' CLI bulunamadı. Claude Code kurulu olmalı.",
    "llm.bilinmeyen-saglayici": "Bilinmeyen sağlayıcı: {kimlik}",
    "llm.env-ayarlanmamis": "{env} ayarlanmamış — {ui_ayar} → {ui_anahtar}'dan gir.",
    "llm.anahtar-bos": "Anahtar boş.",
    "chatgpt.giris-yok": "Önce ChatGPT ile giriş yap.",
    "chatgpt.plan-kapali": "ChatGPT girişinde plan kullanımı izni verilmedi — çıkarım yapılamaz.",
    "chatgpt.secildi": "ChatGPT hesabı seçildi ({model}).",
    "llm.yerel-anahtar-istemez": "{ad} anahtar istemez — model senin bilgisayarında çalışır. Sağlayıcıyı seçip **Kaydet ve dene**'ye basman yeterli.",
    "llm.env-yazilamadi": ".env yazılamadı: {sebep}",
    "llm.depo-dosya": "Anahtarın bu bilgisayarda şifresiz bir dosyada saklanıyor (yalnız senin kullanıcın okuyabilir). İşletim sisteminin anahtarlığı bulunamadı. Linux'ta GNOME Anahtarlığı ya da KWallet kurulup açılırsa Yuki bir sonraki açılışta anahtarı oraya taşır.",
    "llm.yerel-degil": "Yerel sağlayıcı değil: {kimlik}",
    "llm.bos": "(boş)",
    "llm.yerel-hazir": "{model} bu bilgisayarda çalışıyor — sohbete hazır ✓",
    "stt.metne-cevrilemedi": "Konuşma metne çevrilemedi — tekrar dener misin?",
    "ses.yanit-zaman-asimi": "Yanıt zaman aşımı",
    "ses.gecersiz-json": "Geçersiz JSON",
    "ses.sunucu-hatasi": "Sunucu hatası: {sebep}",
    "belge.desteklenmeyen": "Desteklenmeyen doküman türü: {uzanti}",
    "belge.metin-yok": "Dosyadan metin çıkarılamadı (boş ya da taranmış görüntü olabilir).",
    "cihaz.zaman-asimi": "Zaman aşımı",
    "yedek.klasor-yok": "Klasör bulunamadı: {yol}",
    "yedek.yalniz-klasor": "Yalnız klasör eklenebilir (tek dosya değil).",
    "yedek.disk-koku": "Diskin tamamı yedeklenemez — içinden bir klasör seç (ör. Belgeler, Masaüstü, Resimler).",
    "yedek.zaten-ekli": "Bu klasör zaten ekli.",
    "yedek.ust-klasor-ekli": "'{var}' zaten ekli ve bu klasörü kapsıyor.",
    "yedek.alt-klasor-ekli": "Bu klasör zaten ekli olan '{var}' klasörünü kapsıyor — önce onu kaldır.",
    "yedek.google-bagla": "Google hesabın bağlı değil — {ui_ayar} → {ui_google}'dan bağlan, sonra yedekleme çalışabilir.",
    "yedek.tamamlanamadi": "Yedekleme tamamlanamadı: {sebep}",
    "llm.model-gemma": "Gemma 4 26B — ücretsiz (önerilen)",
    "llm.model-gptoss": "gpt-oss 20B — ücretsiz (yedek)",
    "llm.model-gpt41mini": "GPT-4.1 mini — ücretli, daha güçlü",
    "llm.grup-ucretsiz-dogrulandi": "Ücretsiz — doğrulandı",
    "llm.grup-ucretsiz-canli": "Ücretsiz — canlı listeden (denenmedi)",
    "llm.grup-ucretli": "Ücretli",
    "llm.grup-kurulu": "Bilgisayarında kurulu modeller",
    "llm.grup-onerilenler-anahtarsiz": "{ad} — önerilenler (anahtar girilince tam liste gelir)",
    "llm.grup-onerilen": "{ad} — önerilen",
    "llm.grup-onerilenler": "{ad} — önerilenler",
    "llm.grup-tum": "{ad} — tüm modeller",
    "llm.grup-ad": "{ad}",
    "llm.yerel-model-yok": "Ollama çalışıyor ama hiç sohbet modeli kurulu değil. Terminalde `ollama pull llama3.1` çalıştır.",
    "llm.lisans-anahtari-kutusu": "Bu bir **lisans anahtarı**, yapay zekâ anahtarı değil. Lisansını {ui_ayar} → {ui_lisans} sekmesine gir. Buraya {ad} anahtarın gelir — {url} adresinden alınır. Mevcut anahtarına dokunulmadı.",
    "llm.anahtar-bicim": "{ad} anahtarları `{onek}` ile başlar; girdiğin değer öyle değil. Anahtarı {url} adresinden kopyala. (Not: **abonelik** değil, **API anahtarı** gerekir.) Mevcut anahtarına dokunulmadı.",
    "llm.anahtar-reddedildi": "Anahtar denendi ama {ad} kabul etmedi: {sebep} — **mevcut anahtarın korundu**, hiçbir şey değiştirilmedi.",
    "llm.anahtar-reddedildi-ilk": "Anahtar denendi ama {ad} kabul etmedi: {sebep} — hiçbir şey kaydedilmedi.",
    "llm.anahtar-calisiyor": "{ad} anahtarı çalışıyor — sohbete hazır ✓",
    "llm.secim-anahtar-yok": "{ad} için kayıtlı anahtar yok — önce anahtarını gir.",
    "llm.secim-denenemedi": "{ad} bu modelle ({model}) cevap vermedi: {sebep} — **önceki ayar korundu**.",
    "llm.secim-uygulandi": "{ad} · {model} seçildi ve denendi ✓",
    "llm.ollama-ulasilamadi": "{adres} adresinde Ollama'ya ulaşılamadı ({teknik}). Ollama kurulu mu ve çalışıyor mu? Kurulum: ollama.com/download — sonra terminalde `ollama serve`. Mevcut ayarına dokunulmadı.",
    "llm.yerel-model-kurulu-degil-liste": "`{model}` bu bilgisayarda kurulu değil. Terminalde `ollama pull {model}` çalıştır. Kurulu olanlar: {kurulu}. Mevcut ayarına dokunulmadı.",
    "llm.yerel-model-kurulu-degil": "`{model}` bu bilgisayarda kurulu değil. Terminalde `ollama pull {model}` çalıştır. Şu an hiç model kurulu değil. Mevcut ayarına dokunulmadı.",
    "llm.yerel-model-yanitsiz": "`{model}` yüklenemedi ya da yanıt vermedi: {sebep} — **mevcut ayarın korundu**. Model ilk çağrıda belleğe yüklenir; büyük bir modelde bu uzun sürebilir, tekrar dene.",
    "ses.konusma-algilanamadi": "Ses geldi ama konuşma algılanamadı — mikrofon seviyesi düşük olabilir.",
    "ses.kayitli-ses-degil": "Bu ses kayıtlı sesle eşleşmedi; komutu yok saydım.",
    "ses.uyandirma-yok": "Uyandırma kelimesi yok — mesajın için önce 'Yuki' de.",
    # ── / ⑧
    # ──  ⑨ ekranda görünen kalan backend metinleri (paket 1, 2026-09-25)
    "llm.saglayici-genel": "Sağlayıcı",
    "llm.baglanamadi-tekrar": "LLM sağlayıcısına bağlanılamadı, tekrar dene.",
    "llm.hata-onek": "Hata: {mesaj}",
    "llm.claude-code-baglanti": "Claude Code bağlantısı başarısız — {sebep}",
    "llm.cevap-kesildi": "\n\n[Cevap uzunluk sınırında kesildi. 'Devam' dersen sürdürürüm.]",
    "llm.bos-cevap": "Model boş cevap döndü, sana bir şey yazamadım. Yeniden sorar mısın?",
    "llm.anthropic-baglanti": "Anthropic bağlantısı başarısız — {sebep}",
    "llm.islem-sorunu": "İşlem sırasında bir sorun oluştu, tekrar dene.",
    "llm.anthropic-paket-yok": "'anthropic' paketi kurulu değil. `pip install anthropic` çalıştır.",
    "llm.claude-cli-hata": "Claude CLI — {sebep}",
    "llm.bilinmeyen-hata": "bilinmeyen hata",
    "llm.claude-cli-zaman-asimi": "Claude CLI zaman aşımı ({sn} sn).",
    "llm.yanit-alinamadi": "Yanıt alınamadı.",
    "llm.arac-kullaniyor": "Yuki '{arac}' aracını kullanıyor…",
    "llm.model-bos-yanit": (
        "Seçili model boş yanıt döndürdü (istek başarılı ama içerik gelmedi). "
        "Bu, bazı ücretsiz modellerde olur. {ui_ayar} → {ui_anahtar} içinden başka bir "
        "model seçmeyi dene — '{grup}' grubundakiler ölçüldü."
    ),
    "llm.preset-gpt41-mini": "GPT-4.1 Mini (Varsayılan)",
    "llm.preset-gpt41": "GPT-4.1 (Güçlü)",
    "brifing.gunaydin": "Günaydın. Bugün {tarih}. Sistemin hazır. İyi günler.",
    "brifing.gorevler": " Bugün {bugun} görevin var.",
    "brifing.gorevler-gecikmeli": " Bugün {bugun} görevin var, {geciken} tanesi gecikmiş.",
    "brifing.geciken-hatirlatma": "Hatırlatma: {n} gecikmiş görevin var. Planner'ı açıp kontrol etmek ister misin?",
    "bildirim.haber-baslik": "Haber güncellemesi ({saat}):",
    "bildirim.uyanis": "Hoş geldin! Uykudan uyanmak nasıldı? ❄",
    "bildirim.internet-kesildi": "İnternet bağlantısı kesildi.",
    "bildirim.internet-geldi": "İnternet bağlantısı kuruldu. 🌐",
    "bildirim.deprem-baslik": "🌍 Deprem Uyarısı",
    "bildirim.deprem-metin": "M{buyukluk} deprem — {yer} (derinlik {derinlik} km)",
    "bildirim.tanidim": "Merhaba {ad}! Seni tanıdım.",
    "acilis.playwright-yok": "BROWSER_ENABLED=true ama playwright yüklü değil",
    "acilis.auth-acik": (
        "AUTH_TOKEN boş ve sunucu {host} adresine bağlı — auth DEVRE DIŞI, "
        "bu adres dışarıdan erişilebilir. .env'de güçlü bir AUTH_TOKEN (≥32 karakter) ayarla."
    ),
    "ses.edge-notu": "Microsoft — her zaman hazır (yedek)",
    "ses.google-notu": "Google çeviri sesi — yalnız Edge yanıt vermezse (metin Google'a gider)",
    "ses.test-metni": "Merhaba! Ses sistemi hazır ve çalışıyor.",
    "ses.fish-referans-notu": "FISH_REFERENCE_AUDIO ortam değişkenini bu yola ayarlayıp servisi yeniden başlat.",
    "hata.tekrar-dene": "Bir hata oluştu, lütfen tekrar dene.",
    "pydeps.bulunamadi": "Yeni kütüphane bulunamadı — indirme tamamlanmamış olabilir.",
    "ayar.izinsiz-anahtar": "İzin verilmeyen ayar anahtarı: {anahtar}",
    # ── / ⑨
    # ──  ⑥ backend hata metinleri (birlestir.py üretir — elle düzenleme)
    "cihaz.ag-yalniz-yerel": "Sunucu şu an yalnız bu bilgisayardan erişilebilir. Başka bir cihazın bağlanabilmesi için HQ › Cihazlar'dan Yuki'yi yerel ağa aç.",
    "cihaz.ag-kilit-yok": "Yuki'yi ağa açmak için önce uygulama kilidini kur (Ayarlar › Güvenlik).",
    "api.cok-yanlis-anahtar": "Çok fazla yanlış anahtar denemesi — geçici olarak kapalı.",
    "cihaz.ag-kilitsiz-uzak": "Uygulama kilidi yok; Yuki ağa kapalı. Bu isteği yalnız bu bilgisayar yapabilir.",
    "cihaz.bagli-degil": "Cihaz bağlı değil",
    "cihaz.eylem-yok": "Bu eylem desteklenmiyor",
    "cihaz.izin-kapali": "Bu eylem kapalı. HQ › Cihazlar'dan erişim anahtarıyla açabilirsin.",
    "cihaz.izin-anahtar-yok": "Bu yetkiyi açmak için önce .env dosyasında AUTH_TOKEN (erişim anahtarı) belirle.",
    "cihaz.izin-anahtar-yanlis": "Erişim anahtarı yanlış ya da boş.",
    "cihaz.bulunamadi": "Cihaz bulunamadı",
    "cihaz.ultra-gerekli": "Cihaz yönetimi bu kurulumda kapalı.",
    "cihaz.ws-dogrulanamadi": "Kimlik doğrulanamadı",
    "cihaz.ws-kimlik-yok": "Kimlik yok",
    "cihaz.ws-kod-gecersiz": "Eşleştirme kodu geçersiz",
    "cihaz.ws-taninmiyor": "Cihaz tanınmıyor",
    "cihaz.ws-ultra": "Cihaz yönetimi kapalı",
    "duvar.boyut-asimi": "Dosya {mb} MB sınırını aşıyor.",
    "duvar.bulunamadi": "Duvar kâğıdı bulunamadı.",
    "duvar.desteklenmeyen": "Desteklenmeyen biçim: {uzanti}. Kabul edilenler: {kabul}",
    "duvar.gecersiz-kimlik": "Geçersiz duvar kimliği.",
    "duvar.icerik-uyusmuyor": "Dosya içeriği {uzanti} biçimiyle uyuşmuyor.",
    "duvar.karakter-yok": "Karakter varlıkları bulunamadı: {yol}",
    "duvar.sebep-boyut": "boyut sınırı",
    "duvar.sebep-kaynakta-yok": "kaynakta yok",
    "duvar.sebep-zaten-yuklu": "zaten yüklü",
    "duvar.uzantisiz": "(uzantısız)",
    "fitness.egzersiz-yok": "Egzersiz bulunamadı",
    "fitness.ogun-yok": "Öğün bulunamadı",
    "fitness.sablon-yok": "Şablon bulunamadı",
    "fitness.tarih-gecersiz": "Geçersiz tarih: {deger} — beklenen biçim YYYY-AA-GG",
    "google.bagli-degil": "Google hesabı bağlı değil",
    "google.drive-dolu": "Google Drive alanın dolu — yedekleme duraklatıldı. Drive'da yer açtıktan sonra 'Şimdi yedekle' ile devam edebilirsin.",
    "google.drive-api-kapali": "Google Cloud projende Drive API'si açık değil — rehberin 2. adımındaki \"Google Drive API\"yi etkinleştir, sonra tekrar dene.",
    "yedek.ag-hatasi": "Yedekleme yarıda kaldı — internet bağlantısı kesilmiş ya da Google geçici olarak yanıt vermemiş olabilir. Birkaç dakika sonra tekrar dene; yedekleme yalnız kalanı gönderir.",
    "yedek.drive-gecici": "Google Drive şu an isteği kabul etmedi — birkaç dakika sonra tekrar dene; yedekleme yalnız kalanı gönderir.",
    "yedek.drive-reddetti": "Google Drive bu isteği reddetti. Ayrıntı \"Teknik ayrıntı\" altında; sürerse Google panelinden yeniden bağlan.",
    "google.drive-hatasi": "Google Drive hatası ({kod}): {govde}",
    "google.drive-izin-yok": "Bu bağlantı Drive iznini kapsamıyor — {ui_ayar} → {ui_google} → 'Yeniden bağlan' ve onay ekranında Drive iznini işaretli bırak.",
    "google.drive-reddetti": "Google Drive reddetti (403): {govde}",
    "google.kimlik-gecersiz": "Google istemci kimliğin geçersiz — {ui_ayar} → {ui_google} → 'Değiştir' ile İstemci kimliği ve gizli anahtarı yeniden gir. En sık sebebi: Google Cloud'da istemcinin silinmesi ya da eksik kopyalanması. Adımlar aynı ekrandaki 'Resimli rehberi aç' düğmesinde.",
    "google.token-yenilenemedi": "Google token yenilenemedi ({kod}): {govde}",
    "google.yetki-dustu": "Google bağlantın düştü — Google bu bağlantının iznini artık kabul etmiyor. Üç olası sebep: ① izin Google hesabından kaldırıldı (myaccount.google.com/permissions) ② hesap parolası değişti ya da Google güvenlik nedeniyle oturumları kapattı ③ Google Cloud'daki izin ekranı hâlâ 'Testing' durumunda — Google o durumda izni 7 günde iptal eder (rehberin 4. adımı: Publishing status → In production). Çoğu zaman çözüm aynı: {ui_ayar} → {ui_google} → 'Yeniden bağlan'.",
    "google.kimlik-degisti": "İstemci kimliğini değiştirdin — eski bağlantı yeni kimlikle çalışmaz. {ui_ayar} → {ui_google} → 'Yeniden bağlan'.",
    "google.istemci-yetkisiz": "Google bu bağlantıyı kayıtlı istemci kimliğiyle yenilemiyor — bağlantı başka bir kimlikle kurulmuş ya da istemcinin türü değişmiş. {ui_ayar} → {ui_google} → 'Yeniden bağlan'; sürerse rehberden kimliğin türünün 'Desktop app' olduğunu kontrol et.",
    "gorme.ekran-alinamadi": "Ekran görüntüsü alınamadı",
    "gorme.izleyici-henuz-yok": "Ambient Watcher henüz başlatılmadı.",
    "gorme.izleyici-yok": "Ambient Watcher başlatılmadı.",
    "gorme.kapali": "AMBIENT_ENABLED=false — önce .env'de aktif et.",
    "harita.adsb-basarisiz": "Tüm ADSB kaynakları başarısız",
    "harita.afad-bos": "AFAD boş liste döndü",
    "harita.afad-format": "AFAD beklenmedik format",
    "harita.ais-anahtar-yok": "AISStream API key gerekli — AISSTREAM_API_KEY .env'e ekle",
    "harita.cctv-basarisiz": "Tüm CCTV kaynakları başarısız: {kaynaklar}",
    "harita.firms-bos": "FIRMS CSV boş veya parse edilemedi",
    "harita.gdelt-format": "GDELT lastupdate formatı beklenmedik",
    "harita.gdelt-indirilemedi": "GDELT export dosyalarının hiçbiri indirilemedi",
    "harita.haber-bos": "Google News RSS boş/parse edilemedi",
    "harita.kp-parse": "NOAA K-index verisi parse edilemedi",
    "harita.open-meteo-aq-sehir-yok": "Open-Meteo AQ: hiçbir şehir alınamadı",
    "harita.open-meteo-sehir-yok": "Open-Meteo: hiçbir şehir alınamadı",
    "harita.openaq-bos": "OpenAQ istasyon listesi boş",
    "harita.opensky-bos": "OpenSky boş state listesi döndü",
    "harita.poi-alan-zorunlu": "name, lat, lng zorunlu",
    "harita.poi-bulunamadi": "POI bulunamadı",
    "harita.pro-gerekli": "Harita panosu bu kurulumda kapalı.",
    "harita.sismik-ayrisamadi": "Sismik Harita kayıt bildirdi ama hiçbiri ayrıştırılamadı",
    "harita.sismik-format": "Sismik Harita beklenmedik format: {ham}",
    "harita.tle-basarisiz": "Tüm TLE kaynakları başarısız",
    "harita.usgs-format": "USGS feed beklenmedik format",
    "harita.volkan-bos": "USGS volkan listesi boş/parse edilemedi",
    "medya.bulunamadi": "Dosya bulunamadı",
    "medya.dosya-buyuk": "Dosya çok büyük (max 10 MB)",
    "medya.format": "Desteklenmeyen format. İzin verilenler: {izinli}",
    "medya.gecersiz-ad": "Geçersiz dosya adı",
    "medya.metin-cikmaz": "Bu dosya türünden metin çıkarılamaz",
    "medya.yalniz-gorsel": "Bu endpoint yalnız görseller için — dokümanlar için /extract kullan",
    "mod.ad-zorunlu": "Mod adı zorunlu.",
    "mod.bulunamadi": "Mod bulunamadı: {id}",
    "mod.kapali": "'{ad}' modu kapalı — önce aç.",
    "mod.baslatici-kapali": "Mod Başlatıcı kapalı — {ui_ayar} → Sistem → Mod Başlatıcı'dan aç.",
    "mod.uyari-bos": "Mod boş görünüyor (uygulama/alan yok) — başlatınca bir şey yapmaz.",
    "mod.uyari-ozel-alan": "Hem özel alan hem çalışma alanı verildi — özel alan kullanılacak.",
    "mod.uyari-whitelist": "'{uygulama}' uygulaması whitelist'te değil — açılmayabilir.",
    "monitor.doktor-yorumlanamadi": "Şu an sistem durumunu yorumlayamıyorum, lütfen tekrar dene.",
    "monitor.surec-bulunamadi": "Süreç bulunamadı",
    "planlayici.baslangic-gecersiz": "baslangic geçersiz — beklenen biçim 2026-08-31T00:00:00+03:00",
    "planlayici.saat-dilimi-gecersiz": "Saat dilimi tanınmadı",
    "planlayici.basliksiz": "(Başlıksız)",
    "planlayici.env-yazilamadi": "Ayar dosyasına yazılamadı: {sebep} [kaynak: .env yazımı]",
    "planlayici.gecersiz-state": "Geçersiz state token — CSRF saldırısı tespit edildi. Yeniden dene.",
    "planlayici.hesap-baglandi": "Google hesabın bağlandı",
    "planlayici.izin-drive-yok": "Takvim izni verildi, <b>Drive izni verilmedi</b> — Yuki Drive'a yedekleme yapamaz. {duzelt}",
    "planlayici.izin-duzelt": "Düzeltmek için: {ui_ayar} → {ui_google} → <b>Yeniden bağlan</b> ve onay ekranında <b>iki kutuyu da işaretli bırak</b>.",
    "planlayici.izin-hic-yok": "<b>Hiçbir izin verilmedi</b> — Yuki ne takvimini okuyabilir ne de Drive'a yedekleyebilir. {duzelt}",
    "planlayici.izin-takvim-yok": "Drive izni verildi, <b>Takvim izni verilmedi</b> — Yuki takvimini okuyamaz ve etkinlik ekleyemez. {duzelt}",
    "planlayici.izin-tam": "Takvim ve Drive izinleri verildi. Bu sekmeyi kapatıp <b>Yuki</b>'ye dönebilirsin.",
    "planlayici.kimlik-bicimsiz": "Bu bir Google istemci kimliği gibi görünmüyor — sonu '{ek}' ile bitmeli. Google Cloud Console → Kimlik Bilgileri ekranından 'İstemci Kimliği' alanını kopyala.",
    "planlayici.kimlik-bos": "İstemci kimliği ve gizli anahtar boş olamaz.",
    "planlayici.kimlik-yok": "Google hesabı bağlamak için önce kendi Google istemci kimliğini girmelisin: {ui_ayar} → {ui_google} → 'İstemci kimliği'. Nasıl alınacağı adım adım yazılı: aynı ekrandaki 'Resimli rehberi aç' düğmesi.",
    "planlayici.takvim-bagli-degil": "Google Calendar bağlı değil",
    "planlayici.token-gecersiz": "Google token geçersiz — yeniden bağlan",
    "planlayici.donus-basarisiz": "Google hesabı bağlanamadı",
    "planlayici.donus-eski-baglanti": "Bu onay bağlantısı eski ya da daha önce kullanılmış. Yuki'ye dönüp 'Google ile bağla'ya yeniden bas.",
    "planlayici.donus-google-hatasi": "Google bağlantıyı tamamlamadı (kod {kod}). Biraz sonra Yuki'den yeniden dene.",
    "planlayici.donus-kapat": "Bu sekmeyi kapatıp Yuki'ye dönebilirsin.",
    "planlayici.donus-kod-gecersiz": "Onay kodunun süresi dolmuş ya da daha önce kullanılmış. Yuki'ye dönüp 'Google ile bağla'ya yeniden bas.",
    "planlayici.donus-reddedildi": "Onay ekranında izin verilmedi ya da işlem iptal edildi. Yuki'de {ui_ayar} → {ui_google} → 'Google ile bağla' ile yeniden deneyebilirsin.",
    "planlayici.donus-ulasilamadi": "Yuki Google'a ulaşamadı — internet bağlantını kontrol edip Yuki'den yeniden dene.",
    "planlayici.donus-yonlendirme": "Google dönüş adresini kabul etmedi (redirect_uri_mismatch) — istemci kimliğinin türü büyük ihtimalle 'Web application'. Rehberdeki gibi türü 'Desktop app' olan yeni bir kimlik oluştur ve Yuki'de 'Değiştir' ile gir.",
    "planlayici.google-cevapsiz": "Google Takvim şu an cevap vermedi — bağlantın yerinde, biraz sonra yeniden dene.",
    "planlayici.google-yogun": "Google şu an çok fazla istek aldığını söylüyor — birkaç dakika sonra yeniden dene.",
    "planlayici.hesap-baglandi-eksik": "Google hesabın bağlandı — ama bir izin eksik",
    "planlayici.takvim-izni-yok": "Takvim izni verilmemiş — Google bu bağlantıya takvimine erişim vermiyor. {ui_ayar} → {ui_google} → 'Yeniden bağlan' ve onay ekranında takvim kutusunu işaretli bırak.",
    "takvim.arac-bagli-degil": "Google Takvim bağlı değil. Bağlamak için: {ui_ayar} → {ui_google}.",
    "takvim.arac-hata": "Google Takvim isteği tamamlamadı (kod {kod}).",
    "takvim.arac-ulasilamadi": "Google Takvim'e şu an ulaşılamadı — biraz sonra yeniden dene.",
    "takvim.sil-adsiz": "(adsız etkinlik)",
    "takvim.sil-onay-baslik": "Takvimden etkinlik silinsin mi?",
    "takvim.sil-onay-etiket": "Silinecek etkinlik:",
    "takvim.sil-onay-mesaj": "Yuki Google Takvim'inden bir etkinliği silmek istiyor. Bu işlem geri alınamaz.",
    "portre.anahtar-yok": "FAL_KEY .env'de tanımlı değil — fal.ai animasyon kullanılamaz.",
    "portre.avatar-yok": "Yuki avatar bulunamadı: {yol}",
    "portre.devre-acik": "fal.ai devre dışı (circuit breaker açık — art arda hata).",
    "portre.durum-anahtar-yok": "FAL_KEY tanımlı değil — mikro animasyon katmanı kapalı.",
    "portre.durum-devre-acik": "fal.ai devre dışı (art arda hata — circuit breaker açık).",
    "portre.gecersiz-aksiyon": "Geçersiz aksiyon. Geçerliler: {gecerliler}",
    "portre.klip-hatasi": "Klip üretimi başarısız [kaynak: fal.ai]: {sebep}",
    "portre.video-url-yok": "fal.ai yanıtında video URL bulunamadı: {sonuc}",
    "saglik.anahtar-ayarli": "{saglayicilar} anahtarı kayıtlı.",
    "saglik.anahtar-cozum": "{ui_menu_anahtar} ekranında bir servis seçip anahtarını gir — OpenRouter ücretsiz başlar, kredi kartı istemez.",
    "saglik.anahtar-gerekmiyor": "Anahtar gerekmiyor — {saglayici} bu bilgisayarda çalışıyor.",
    "saglik.anahtar-yok": "Anahtar girilmemiş — Yuki cevap veremez.",
    "saglik.baslik-disk": "Boş alan",
    "saglik.baslik-ffmpeg": "Ses dönüştürme",
    "saglik.baslik-llm-anahtar": "Yapay zekâ anahtarı",
    "saglik.baslik-llm-kota": "Ücretsiz kullanım",
    "saglik.baslik-llm-model": "Model",
    "saglik.baslik-onnxruntime": "Görme ve anlamca hafıza",
    "saglik.baslik-stt": "Sesle yazma",
    "saglik.baslik-veri-dizini": "Veri klasörü",
    "saglik.disk-az": "Yalnız {gb} GB boş.",
    "saglik.disk-bos": "{gb} GB boş.",
    "saglik.disk-cozum": "Ses tanıma ve hafıza modelleri için en az 2 GB boş alan gerekiyor.",
    "saglik.disk-olculemedi": "Boş alan okunamadı ({neden}).",
    "saglik.ffmpeg-cozum": "Bir şey yapman gerekmiyor; ses tanıma çalışmaya devam eder.",
    "saglik.ffmpeg-pyav": "Telefondan gelen ses kayıtları okunabiliyor.",
    "saglik.ffmpeg-yedek": "Telefondan gelen ses kayıtları okunabiliyor (ffmpeg ile).",
    "saglik.ffmpeg-yok": "Ses dönüştürücü bulunamadı — ses yine de metne çevriliyor, yalnız sessizlik algılama kapalı.",
    "saglik.kota-ucretli-model": "{model} ücretli bir model — ücretsiz günlük sınır uygulanmaz.",
    "saglik.kur-basarisiz": "Kurulum başarısız (kod {kod}). Elle deneyebilirsin: {url}",
    "saglik.kur-baslatilamadi": "Kurulum başlatılamadı: {hata}",
    "saglik.kur-bilinmeyen": "Bilinmeyen kurulum: {kimlik}",
    "saglik.kur-dosya-kucuk": "indirilen dosya beklenenden küçük ({bayt} bayt)",
    "saglik.kur-indirilemedi": "İndirilemedi: {hata} — tarayıcıdan elle indirip kurabilirsin: {url}",
    "saglik.kur-iptal": "Kurulum iptal edildi (yönetici onayı verilmedi).",
    "saglik.kur-kuruldu": "Kuruldu. Yuki'yi kapatıp yeniden aç.",
    "saglik.kur-yalniz-windows": "Bu kurulum yalnız Windows'ta geçerli.",
    "saglik.kur-yeniden-baslat": "Kuruldu — Windows'u yeniden başlatman gerekiyor.",
    "saglik.kur-zaten-yeni": "Zaten daha yeni bir sürüm kurulu — sorun başka yerde. Hata günlüğünü paylaş.",
    "saglik.model-kalkti": "Seçili model ({model}) OpenRouter'dan kaldırılmış — Yuki cevap veremiyor.",
    "saglik.model-kalkti-cozum": "Düzelt, aynı serviste çalışan ücretsiz bir model seçer. Servisin değişmez.",
    "saglik.model-liste-alinamadi": "{model} seçili; OpenRouter'a ulaşılamadığı için hâlâ duruyor mu ölçülemedi.",
    "saglik.model-liste-disi": "`{model}` seçili; {saglayici} modelinin hâlâ durduğu buradan ölçülemiyor — bu denetim yalnız OpenRouter'da ve bu bilgisayardaki modellerde yapılabiliyor.",
    "saglik.model-ollama-cozum": "Ollama çalışıyor mu? Terminalde `ollama serve` ile başlat.",
    "saglik.model-ollama-ulasilamadi": "Ollama'ya ulaşılamadı — `{model}` şu an cevap veremez.",
    "saglik.model-sec-cozum": "{ui_menu_anahtar} ekranından bir model seç.",
    "saglik.model-secilmemis": "Model seçilmemiş — Yuki cevap veremez.",
    "saglik.model-yerel-cozum": "Terminalde `ollama pull {model}` çalıştır ya da kurulu bir model seç.",
    "saglik.model-yerel-kurulu": "`{model}` bu bilgisayarda kurulu.",
    "saglik.model-yerel-yok": "`{model}` bu bilgisayarda kurulu değil — Yuki cevap veremez.",
    "saglik.onar-desteklenmiyor": "'{kimlik}' otomatik onarılamıyor — çözüm metnini izle.",
    "saglik.onar-klasor-olmadi": "`{yol}` klasörü oluşturulamadı ({neden}).",
    "saglik.onar-model-degisti": "Model {model} olarak değiştirildi — servisin aynı kaldı, seçim kalıcı.",
    "saglik.onar-ucretsiz-model-yok": "OpenRouter'da şu an kullanılabilir ücretsiz model yok. {ui_menu_anahtar} ekranından ücretli bir model seçebilirsin.",
    "saglik.onnx-cozum-paket": "Kurulum paketi eksik ya da yarım inmiş görünüyor. Önce Yuki'yi siteden yeniden indirip kurmayı dene. Sorun sürerse aşağıdaki düğmeyle Microsoft'un runtime paketini kurabilirsin.",
    "saglik.onnx-cozum-vcredist": "Runtime kütüphaneleri pakette mevcut, yükleme yine de başarısız. Aşağıdaki düğmeyle Microsoft Visual C++ Redistributable (x64) kurup uygulamayı yeniden başlat.",
    "saglik.onnx-eksik-dll": " · pakette bulunmayan runtime kütüphanesi: {dll}",
    "saglik.stt-cozum-vcredist": "Aşağıdaki düğmeyle Microsoft Visual C++ Redistributable (x64) kurup uygulamayı yeniden başlat.",
    "saglik.stt-model-cozum": "İlk konuşmada kendiliğinden iner (~500 MB); o konuşma biraz gecikir. İstersen şimdiden {ui_menu_ses} ayarlarından indirebilirsin.",
    "saglik.stt-model-yok": "Ses motoru hazır ama konuşma modeli henüz inmemiş.",
    "saglik.stt-motor-yok": "Ses tanıma motoru açılamadı — sesle yazma çalışmıyor.",
    "saglik.vcredist-etiket": "Microsoft VC++ paketini kur",
    "saglik.vcredist-uyari": "Microsoft'un sunucusundan ~25 MB indirilir ve kurulum başlatılır. Windows yönetici onayı (UAC) soracak. Bu, pek çok programın ihtiyaç duyduğu ücretsiz bir Microsoft paketidir.",
    "saglik.veri-dizini-cozum": "Uygulamayı yönetici olarak değil, normal kullanıcı olarak çalıştır. Sorun sürerse kurulum klasörünü Program Files dışına taşı.",
    "saglik.veri-dizini-yazilamiyor": "`{yol}` klasörüne yazılamıyor ({neden}) — ayarların ve konuşmaların kaydedilemez.",
    "saglik.kota-ucretli-servis": "{saglayici} ücretli bir servis — ücretsiz günlük sınır uygulanmaz.",
    "saglik.model-duruyor": "OpenRouter'da duruyor: {model}.",
    "saglik.model-sec-cozum-oto": "Düzelt, OpenRouter'da çalışan ücretsiz bir model seçer. Servisin değişmez.",
    "saglik.onar-klasor-hazir": "Veri klasörü hazır — `{yol}` artık yazılabiliyor.",
    "saglik.onar-klasor-yazilamiyor": "`{yol}` klasörü var ama yazılamıyor ({neden}). Yuki'yi yönetici olarak değil, normal kullanıcı olarak çalıştır; sürerse klasörün izinlerine bak.",
    "saglik.onar-liste-alinamadi": "OpenRouter'a ulaşılamadı, çalışan modellerin listesi alınamadı. Biraz sonra yeniden dene ya da {ui_menu_anahtar} ekranından bir model seç.",
    "saglik.onar-model-elle": "{saglayici} için otomatik düzeltemiyorum — çalışan modelleri yalnız OpenRouter'da listeleyebiliyorum. {ui_menu_anahtar} ekranından bir model seç.",
    "saglik.onar-model-gecici": "Model {model} olarak değiştirildi ama ayar dosyasına yazılamadı — Yuki yeniden başlayınca eski modele döner. {ui_menu_anahtar} ekranından modeli yeniden seç.",
    "saglik.onnx-acilamadi": "Motor açılamadı — resimdeki yazıyı okuma ve anlamca hafıza çalışmıyor.",
    "saglik.onnx-hazir": "Resimdeki yazıyı okuma, QR ve anlamca hafıza kullanılabilir.",
    "saglik.stt-hazir": "Ses motoru ve konuşma modeli hazır.",
    "saglik.veri-dizini-iyi": "Ayarların ve konuşmaların kaydedilebiliyor (`{yol}`).",
    "saglik.gunluk-silinemedi": "Hata günlüğü silinemedi — dosya kullanımda ya da yazma izni yok.",
    "saglik.hata-izin": "erişim izni yok",
    "saglik.hata-bulunamadi": "klasör bulunamadı",
    "saglik.hata-disk-dolu": "disk dolu",
    "saglik.hata-genel": "sistem izin vermedi — ayrıntı hata günlüğünde",
    "saglik.kota-openrouter": "Günde 50 mesaj, dakikada 20 — sınır dolarsa ertesi gün yeniden açılır, Yuki bozulmuş değildir.",
    "saglik.model-ucretsiz-ad": "{ad} — ücretsiz",
    "saglik.motor-cozum-diger": "Yuki'yi siteden yeniden indirip kurmayı dene; sorun sürerse hata günlüğünü Kopyala ile alıp destek isterken gönder.",
    "stt.bilinmiyor": "bilinmiyor",
    "stt.dosya-buyuk": "Dosya çok büyük (max 25MB)",
    "stt.format": "Desteklenmeyen ses formatı",
    "stt.model-yok": "Ses tanıma modeli henüz indirilmemiş.",
    "stt.model-indirilemedi": "Ses tanıma modeli indirilemedi (internet bağlantısını ya da huggingface.co erişimini denetle). Ayrıntı: {ayrinti}",
    "stt.motor-yuklenemedi": "Ses tanıma motoru bu makinede yüklenemedi (genelde eksik sistem kütüphanesi). Ayrıntı: {ayrinti}",
    "todo.alt-gorev-yok": "Subtask bulunamadı",
    "todo.gecersiz-filtre": "Geçersiz filtre: {filtre}. Geçerliler: {gecerli}",
    "todo.gorev-copte-degil": "Görev bulunamadı veya çöp kutusunda değil",
    "todo.gorev-yok": "Görev bulunamadı",
    "todo.gorev-zaten-aktif": "Görev bulunamadı veya zaten aktif",
    "todo.kayit-yok": "Kayıt bulunamadı",
    "todo.kendine-bagimli": "Görev kendisine bağımlı olamaz",
    "todo.liste-yok": "Liste bulunamadı",
    "todo.takvim-esitleme-hatasi": "Calendar sync hatası [kaynak: Google Calendar API]: {sebep}",
    "todo.takvim-etkinligi-yok": "Takvim eventi bulunamadı",
    "todo.takvim-silme-hatasi": "Calendar silme hatası [kaynak: Google Calendar API]: {sebep}",
    "todo.tarihsiz-takvim": "Tarih olmadan takvime eklenemez",
    "yedek.en-az-bir": "{alan} en az 1 olmalı.",
    "yedek.google-bagli-degil": "Google hesabın bağlı değil.",
    "yedek.kapali": "Yedekleme kapalı — önce panelden aç.",
    "yedek.kaynak-yok": "Kaynak bulunamadı.",
    "yedek.pro-ozelligi": "Google Drive yedekleme bu kurulumda kapalı.",
    "yedek.tur-suruyor": "Bir yedekleme turu zaten sürüyor.",
    "yedek.zamanlama-bicim": "Zamanlama 'SS:DD' biçiminde olmalı (ör. 03:30).",
    # ── Atölye bildirimleri (g4 2026-11-12; services/gorev_bildirim · gorev_onerici)
    "atolye.bildirim-baslik": "Yuki · Atölye",
    "atolye.bitis-bitti": "{tur} görevi bitti — sonucu Atölye'de.",
    "atolye.bitis-yarim": "{tur} görevi yarım kaldı — Atölye'de bakabilirsin.",
    "atolye.bitis-hata": "{tur} görevi hata verdi — ayrıntı Atölye'de.",
    "atolye.bitis-durdu": "{tur} görevi durdu — devam etmek için Atölye'ye bak.",
    "atolye.tur-site": "Site",
    "atolye.tur-arastirma": "Araştırma",
    "atolye.tur-sahne": "Araştırma sahnesi",
    "atolye.tur-deneme": "Deneme",
    "atolye.tur-varsayilan": "Atölye",
    "atolye.oneri-cok": "{n} iş önerisi var — Atölye'de ONAYLA ya da GEÇ.",
    "atolye.oneri-tek": "Yeni bir iş önerisi var — Atölye'de ONAYLA ya da GEÇ.",
    # ── / ⑥
}
