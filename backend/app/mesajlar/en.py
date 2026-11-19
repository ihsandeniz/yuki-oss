"""User-facing messages — English.

Karşılıklar frontend sözlüğüyle (`frontend/js/diller/en.js`) tutarlı olmak
zorunda; `ui.*` etiketlerinin aynılığı testle kilitli.

⚠️ `-cogul` ile biten anahtarlar İngilizce'ye ÖZGÜdür: Türkçe'de sayıdan
sonra çoğul eki gelmez ("5 dakika"), İngilizce'de gelir ("5 minutes").
Parite kapısı bu tek istisnayı tanır (`Mc()` — bkz. `__init__.py`).
"""
from __future__ import annotations

METINLER: dict[str, str] = {
    # ── UI labels — never inlined into sentences ─────────────────────────
    # 🔴 `nav.ayar` (frontend) ile BİREBİR aynı olmalı: test kilitliyor.
    "ui.ayar": "⚙ SETTINGS",
    "ui.anahtar": "🔑 KEY",
    "ui.saglik": "🩺 HEALTH",
    "ui.kopyala": "📋 COPY",
    "ui.lisans": "🎫 LICENCE",
    "ui.plan": "PLAN",
    "ui.google": "GOOGLE",
    "ui.ses": "Voice",
    "ui.komut-ogren": "/teach",
    "ui.menu-anahtar": "API Key",
    "ui.menu-ses": "Voice & TTS",

    # ── Global error handlers (429 / 500) ────────────────────────────────
    "hata.hiz-siniri": (
        "You tried too often — wait {ne_kadar} and try again. "
        "This is NOT a problem with your key."
    ),
    "hata.sure-dakika": "{n} minute",
    "hata.sure-dakika-cogul": "{n} minutes",
    "hata.sure-saniye": "{n} second",
    "hata.sure-saniye-cogul": "{n} seconds",
    "hata.sure-kisa": "a short while",
    "hata.beklenmeyen": (
        "Something went wrong. Try again; if it keeps happening, share the error "
        "log via {ui_ayar} → {ui_saglik} → {ui_kopyala}."
    ),


    # ── Startup validation ───────────────────────────────────────────────
    "acilis.anahtar-yok": (
        "No OPENROUTER_API_KEY — to chat, enter a key from {ui_ayar} → "
        "{ui_anahtar} (openrouter.ai/keys, free). Chat will not work until a "
        "key is entered."
    ),
    "acilis.hafiza-kapali": (
        "Memory is disabled — MEMORY_BACKEND=pgvector is selected but DATABASE_URL "
        "is empty. For built-in memory, set MEMORY_BACKEND=sqlite in .env (no "
        "installation required)."
    ),

    # ── Plan gates ───────────────────────────────────────────────────────
    "kademe.plan-pro": (
        "The {ui_plan} screen is disabled in this install. You can manage your tasks "
        "by telling Yuki ('add a task to buy milk')."
    ),
    "kademe.plan-pro-baslik": "The {ui_plan} screen is disabled",
    "kademe.plan-pro-govde": (
        "You can manage your tasks by telling Yuki —<br>"
        "<i>“add a task to buy milk”</i>, <i>“what are my tasks today?”</i>"
    ),

    # ── Key / provider ───────────────────────────────────────────────────
    "anahtar.saglayici-yok": (
        "No LLM key configured. Choose a provider and enter its key from "
        "{ui_ayar} → {ui_anahtar}."
    ),
    "anahtar.yerel-yanit-yok": (
        "{saglayici} is not responding. Is it installed and running? Setup: {url}"
    ),
    "anahtar.saglayici-anahtari-yok": (
        "No {saglayici} key configured. Enter your {saglayici} key from "
        "{ui_ayar} → {ui_anahtar}{url}."
    ),

    # ── Tab / character tools (these also go to the LLM) ─────────────────
    "sekme.gecersiz": (
        "Invalid tab: '{sekme}'. This app only has these tabs: {liste}"
    ),
    "sekme.kapali": (
        "The {ad} tab is disabled in this install. "
        "You can manage your tasks by telling me: 'add ... to my tasks', 'my tasks'."
    ),
    "sekme.gecildi": "Switched to the {ad} tab.",
    "sekme.mevcut": "Available tabs: {liste}",
    "sekme.kapali-eki": "disabled",
    "karakter.gecersiz": "Invalid character: '{karakter}'. Valid characters: {liste}",
    "karakter.kilitli": (
        "The '{karakter}' character is disabled in this install."
    ),
    "karakter.gecilemedi": "Could not switch character: '{karakter}'.",

    # ── LLM provider errors ──────────────────────────────────────────────
    "llm.anahtar-gecersiz": (
        "Your {saglayici} key is invalid or has been revoked. Enter a new key "
        "from {ui_ayar} → {ui_anahtar} ({url})."
    ),
    "llm.model-erisimi-yok": (
        "This key has no access to the selected model. Pick another model from "
        "{ui_ayar} → {ui_anahtar}, or change the key."
    ),
    "llm.ulasilamadi": "Could not reach the LLM provider — check your internet connection.",

    "ogren.kaydedildi": "Got it: {bilgi} ✦",
    "ogren.ne-ogreneyim": "What should I learn? e.g. {ui_komut_ogren} I take my coffee black",
    "ogren.model-yok": "I couldn't save that: the memory understanding model isn't installed (README → Optional → Semantic memory model, EMBED_ONNX_DIR).",
    "ogren.kaydedilemedi": "I couldn't save that — writing to memory failed. Details are in the backend log.",
    "llm.bakiye-bitti": (
        "Your {saglayici} balance is empty. Add credit to your account, or pick a "
        "free model/provider from {ui_ayar} → {ui_anahtar}."
    ),
    "llm.model-bulunamadi": (
        "The selected model was not found — pick another one from the list in "
        "{ui_ayar} → {ui_anahtar}."
    ),
    "llm.anahtar-bicimi": (
        "Your AI key is in the wrong format. OpenRouter keys start with `sk-or-`. "
        "You may have pasted your licence key here — that one goes into the "
        "{ui_ayar} → {ui_lisans} tab."
    ),
    "llm.anthropic-anahtari-yok": (
        "Error: no Anthropic key. Enter one from {ui_ayar} → {ui_anahtar} "
        "(console.anthropic.com/settings/keys)."
    ),
    "llm.reddedildi-detayli": "The LLM provider rejected the request (HTTP {kod}): {detay}",
    "llm.reddedildi": "The LLM provider rejected the request (HTTP {kod}).",

    # ── Quota (429) — daily vs per-minute is decided from the body ───────
    "llm.kota-gunluk": (
        "You have used up your free daily request quota — waiting will not help, "
        "the quota resets tomorrow."
    ),
    "llm.kota-openrouter-eki": (
        " On OpenRouter an account without credit gets 50 requests a day; adding "
        "$10 of credit once raises that to 1,000 (opening a new account does not "
        "help, the quota is account-wide)."
    ),
    "llm.kota-alternatif": (
        " Alternative: pick another provider/model from {ui_ayar} → {ui_anahtar}."
    ),
    "llm.kota-dakikalik": "Requests are coming in too fast — wait a few seconds and try again.",
    "llm.kota-ucretsiz-eki": (
        " (Free models have a tight per-minute limit; it could also be your daily quota.)"
    ),

    # ── Sağlayıcı metinleri (FAZ 3 · Dalga 2 · Blok 4B, 2026-09-19) ───────
    # 🔴 Kaynağı `services/llm_providers.py::SAGLAYICILAR` — bu katalog onu
    # ÇEVİRİYOR, yeniden yazmıyor. Türkçe değerler dataclass'takiyle BİREBİR
    # aynı olmak zorunda (kapı: test_saglayici_metni_KAYNAKLA_AYNI); ayrışırsa
    # ölçüm değişince arayüz bayatlar ve kimse fark etmez.
    "saglayici.anthropic.not": "⚠ A Claude Pro/Max subscription is not an API — you also need credit on console.anthropic.com.",
    "saglayici.cerebras.ucretsiz": "Has a free tier (with a daily token limit).",
    "saglayici.chutes.ucretsiz": "Has a free tier (with a daily request limit).",
    "saglayici.deepseek.not": "Cheap but paid — you need to add credit.",
    "saglayici.google.not": "An AI Studio key. NOT a Vertex AI (Google Cloud) key.",
    "saglayici.google.ucretsiz": "Google AI Studio keys have a free tier (with per-model daily and per-minute request limits).",
    "saglayici.groq.not": "Very fast inference. Narrow model list.",
    "saglayici.groq.ucretsiz": "Has a free tier (with per-minute/daily request and token limits).",
    "saglayici.mistral.ucretsiz": "Has a free (experimental) tier.",
    "saglayici.nebius.ucretsiz": "Gives trial credit on sign-up.",
    "saglayici.ollama.ad": "Ollama (your own computer)",
    "saglayici.ollama.not": "First install Ollama from ollama.com/download, then pull a model with `ollama pull llama3.1`. No key required.",
    "saglayici.ollama.ucretsiz": "no quota and no request limit, the model runs on your own computer. The trade-off is hardware: an 8B model needs ~8 GB of RAM (or VRAM) and is slower than cloud models.",
    "saglayici.ollama.uyari": "Yuki's system prompt + tool definitions are ≈ 4,100 tokens. Ollama's default context window is smaller than that in most installations and the prompt is silently truncated → answers come back malformed. Start the server with `OLLAMA_CONTEXT_LENGTH=8192 ollama serve`. Also, small models (8B) can call tools but follow Yuki's response format less consistently than cloud models.",
    "saglayici.openai.not": "⚠ A ChatGPT Plus subscription is not an API — you also need credit on platform.openai.com.",
    "saglayici.openrouter.not": "Hundreds of models with a single key. The easiest way to start free.",
    "saglayici.openrouter.ucretsiz": "Free (`:free`) models work without adding credit. Limits: 20 requests per minute, 50 per day. Adding $10 of credit once raises the daily limit to 1,000. Opening a new account or key does not change it — the quota is global, not per key.",
    "saglayici.together.ucretsiz": "Offers a free tier on some models.",
    "yerel.ulasilamadi": "Could not reach Ollama at {adres} — is it installed and running? Install it from ollama.com/download, then run `ollama serve` in the terminal. (technical: {teknik})",

    # ── Missing optional library (Blok 6B, 2026-09-19) ────────────────────
    "pydeps.eksik": "A required library has not been downloaded: {moduller}. It is downloaded the first time you open the feature.",

    # ── App lock (FAZ 3 · Dalga 2 · Blok 6, 2026-09-19) ───────────────────
    "kilit.kurulu-degil": "The app lock is not set up.",
    "kilit.parola-yanlis": "Wrong password.",
    "kilit.mevcut-parola-yanlis": "Your current password is wrong.",
    "kilit.kaydedilemedi": "The password could not be saved.",
    "kilit.uzunluk": "The password must be {min}-{max} characters.",
    # `-cogul` is English-only on purpose: Turkish takes no plural suffix
    # after a number. See `Mc` in `mesajlar/__init__.py`.
    "kilit.kalan-hak": "You have {n} attempt left.",
    "kilit.kalan-hak-cogul": "You have {n} attempts left.",

    "giris-kilidi.parola-alt-var": "Password sign-in was disabled for {dk} min after {kez} failed attempts — use your face instead.",
    "giris-kilidi.yuz-alt-var": "Face sign-in was disabled for {dk} min after {kez} failed attempts — use your password instead.",
    "giris-kilidi.parola-alt-yok": "Password sign-in is disabled for {dk} min. The other method is disabled too — wait until the time is up.",
    "giris-kilidi.yuz-alt-yok": "Face sign-in is disabled for {dk} min. The other method is disabled too — wait until the time is up.",

    # ── Memory endpoints (FAZ 3 · Wave 2 · Block 8, 2026-09-20) ───────────
    # `.env` / `MEMORY_BACKEND` / `DATABASE_URL` stay untranslated: they are
    # literal setting names the user must type, not prose.
    "hafiza.devre-disi": (
        "The memory system is disabled — set MEMORY_BACKEND=sqlite in .env "
        "(embedded, no setup needed) or provide DATABASE_URL for pgvector."
    ),
    "hafiza.semantik-ultra": (
        "Semantic memory is disabled in this install; Yuki uses "
        "short-term (lite) memory."
    ),
    "hafiza.model-yok": (
        "The memory understanding model is not installed, so memories can't be added. Download it "
        "and point EMBED_ONNX_DIR at it (README → Optional → Semantic memory model). Chat keeps "
        "using short-term memory meanwhile."
    ),
    "hafiza.gecersiz-karakter": "Invalid character_key: '{kod}'. Valid values: {gecerli}",
    "hafiza.ani-bulunamadi": "Memory not found: {id}",
    "hafiza.alan-eksik": "Either importance or content must be provided.",

    # ── Settings write path (FAZ 3 · Wave 2 · Block 9, 2026-09-20) ────────
    # The setting key itself ({anahtar}) is never translated: it is the name
    # the user will look for in .env.
    "ayar.bilinmeyen-anahtar": "Unknown or not permitted setting: {anahtar}",
    "ayar.gecersiz-dil": "Invalid language: '{deger}'. Options: {secenekler}",
    "ayar.ses-haritasi-json": "The voice map is not valid JSON.",
    "ayar.bilinmeyen-karakter": "Unknown character: {karakter}",
    "ayar.gecersiz-ses": "Invalid voice name: '{ses}' (e.g. 'tr-TR-EmelNeural')",
    "ayar.kaydedilemedi": "Could not save: {sebep}",

    # ── TTS endpoints (Block 9) ───────────────────────────────────────────
    "ses.test-metni-uzun": "Test text can be at most 300 characters.",
    "ses.tts-hatasi": "TTS error [source: TTS chain]: {sebep}",
    "ses.ref-bicim": "A WAV or MP3 file is required.",
    "ses.ref-buyuk": "File is too large (10 MB maximum).",

    # ── Settings reset (Block 10) ─────────────────────────────────────────
    # `?confirm=true` is a query parameter — never translated.
    "ayar.sifirla-onay": "Confirmation required: ?confirm=true",
    "ayar.sifirlama-basarisiz": "Reset failed",
    "ayar.masaustu-acilamadi": "Desktop Yuki couldn't start: {hata}",
    "ayar.masaustu-kapanmadi": "Desktop Yuki didn't close: {hata}",
    "ayar.bos-olamaz": "This setting can't be empty — use 'back to default' to reset it.",
    "ayar.kullanilamaz": "This setting isn't available right now: {sebep}",

    # ── Reminders (Block 10) ──────────────────────────────────────────────
    # 🔑 The plural split lives in the KEY here, not in `Mc`: Turkish writes
    # "her 5 dakikada" with no plural suffix, English needs "every 5 minutes"
    # AND a numberless "every minute" — two different sentences, not one
    # sentence with a count.
    "hatirlatici.her-saniye": "every second",
    "hatirlatici.her-dakika": "every minute",
    "hatirlatici.her-saat": "every hour",
    "hatirlatici.her-gun": "every day",
    "hatirlatici.her-n-saniye": "every {n} seconds",
    "hatirlatici.her-n-dakika": "every {n} minutes",
    "hatirlatici.her-n-saat": "every {n} hours",
    "hatirlatici.her-n-gun": "every {n} days",
    "hatirlatici.gecersiz-zaman": "Invalid time expression: {ifade}",
    "hatirlatici.bulunamadi": "Reminder not found",
    "hatirlatici.bildirim": "Reminder: {mesaj}",

    # ── Phone notifications (Block 10) ────────────────────────────────────
    "bildirim.pro-ozelligi": "Phone notifications are disabled in this install.",
    "bildirim.test-metni": "Test notification — the connection works!",
    "bildirim.anahtar-uretilemedi": (
        "Notification keys could not be generated — phone notifications are "
        "unavailable in this installation."
    ),

    # ⚪ Onay / panel köprüsü uçları — ekranda GÖRÜLMEDİ (Blok 10 turu
    # BİLDİRİM odasını ölçtü, onay akışını değil). Yine de kataloğa alındı:
    # dosyanın kapısı artık istisnasız ("ham TR detail kalmadı") ve bayat
    # bir süzgeç yerine ölçülmemiş bir kalem bırakıyoruz.
    "onay.talep-yok": "The approval request was not found or has expired",

    # ── License — 🎫 LICENSE panel + activation toast ───────────
    "lisans.bos": "The license key is empty.",
    "lisans.etkinlestirildi": "{kademe} plan activated.",
    "lisans.format-hatali": (
        "This doesn't look like a Yuki license key — paste the whole key from your "
        "purchase email."
    ),
    "lisans.okunamadi": (
        "The license key could not be read — part of it may have been lost while "
        "copying. Paste the whole key again (without spaces)."
    ),
    "lisans.imza-gecersiz": (
        "This key could not be verified — it is damaged or was not issued for Yuki. "
        "Use the key from your purchase email."
    ),
    "lisans.icerik-bozuk": (
        "The license key's contents are corrupted — paste the key again; if the "
        "problem persists, use the key from your purchase email."
    ),
    "lisans.baska-urun": "This license is for another product — paste your Yuki key.",
    "lisans.sema-desteklenmiyor": (
        "This key can't be opened by this version of Yuki — update Yuki, then try again."
    ),
    "lisans.bitis-okunamadi": (
        "The license end date could not be read — paste the key from your purchase email again."
    ),
    "lisans.grace-kaldi": "Your license has expired — renew within {n} day or some features turn off.",
    "lisans.grace-kaldi-cogul": "Your license has expired — renew within {n} days or some features turn off.",
    "lisans.grace-bitti": (
        "Your license expired {n} day ago and some features turned off. "
        "When you renew, paste the new key here."
    ),
    "lisans.grace-bitti-cogul": (
        "Your license expired {n} days ago and some features turned off. "
        "When you renew, paste the new key here."
    ),
    "lisans.env-arac-listesi": "Developer install — tools chosen by hand.",
    "lisans.env-tam": "Developer install — everything unlocked.",
    "lisans.kaldirilamadi": (
        "The license could not be removed: the file could not be deleted, Yuki is still on "
        "{kademe}. Close and reopen Yuki, then try again."
    ),
    # ──  ⑤ face login / liveness
    "canlilik.talimat": "Look at the camera and blink {n} time.",
    "canlilik.talimat-cogul": "Look at the camera and blink {n} times.",
    "canlilik.alinmadi": "No liveness challenge was received.",
    "canlilik.alinmadi-once": "No liveness challenge was received. Call /api/face/liveness/challenge first.",
    "canlilik.bulunamadi": "Challenge not found or expired.",
    "canlilik.kullanildi": "This challenge was already used — request a new one.",
    "canlilik.suresi-doldu": "The challenge has expired — request a new one.",
    "canlilik.baska-istemci": "The challenge belongs to another client.",
    "canlilik.parca-alindi": "This chunk was already received.",
    "canlilik.kare-tavani": "Frame limit exceeded ({tavan}).",
    "canlilik.dizi-buyuk": "Frame sequence is too large.",
    "canlilik.gecersiz": "The challenge is no longer valid.",
    "canlilik.yetersiz-kare": "Not enough frames ({kare}/{en_az}). Stay in front of the camera a little longer.",
    "canlilik.kopya": "Frames are copies of each other — a live image is required.",
    "canlilik.yuz-yok": "No face visible in most frames ({yuzsuz}/{toplam}).",
    "canlilik.yuzlu-az": "Not enough frames with a visible face.",
    "canlilik.goz-noktasi-yok": "Liveness could not be measured: the face model returned no eye landmarks.",
    "canlilik.hareket-yok": "No eye movement — a live image is required.",
    "canlilik.kirpma-uyusmadi": "{istenen} blinks requested, {kirpma} detected.",
    "canlilik.birden-fazla": "More than one person appears in the sequence — try again alone.",
    "canlilik.sinirlar": "Blinking rejects printed/on-screen photos; it does NOT reject video playback or deepfakes.",
    "canlilik.dogrulanamadi": "Liveness could not be verified.",
    "canlilik.kapali": "liveness disabled (FACE_LIVENESS_REQUIRED=false)",
    "yuz.devre-disi": "Face recognition is disabled (FACE_AUTH_ENABLED).",
    "yuz.tur": "Only JPEG/PNG is supported.",
    "yuz.dosya-buyuk": "File is too large (max {mb} MB).",
    "yuz.bos-dosya": "Empty file.",
    "yuz.islem-hatasi": "An error occurred during {islem}.",
    "yuz.islem.kare": "frame upload",
    "yuz.islem.dogrulama": "verification",
    "yuz.islem.yuz-kaydi": "face enrollment",
    "yuz.islem.kayit": "enrollment",
    "yuz.islem.tarama": "scan",
    "yuz.islem.liste": "listing",
    "yuz.islem.kalite": "quality report",
    "yuz.islem.kayit-silme": "record deletion",
    "yuz.islem.silme": "deletion",
    "yuz.kilit-yok": "The startup lock is not set up — face login is unavailable.",
    "yuz.kayitli-yuz-yok": "No enrolled face found. Enroll first.",
    "yuz.kalan-hak": "{n} attempt left.",
    "yuz.kalan-hak-cogul": "{n} attempts left.",
    "yuz.belirsiz": "Face did not match clearly — fix the lighting and try again, or use your password.",
    "yuz.eslesmedi": "Face did not match.",
    "yuz.kaydedildi": "Face saved ({sahip} · {n} image).",
    "yuz.kaydedildi-cogul": "Face saved ({sahip} · {n} images).",
    "yuz.isim-bos": "Name cannot be empty.",
    "yuz.goruntu-okunamadi": "Image could not be read.",
    "yuz.bulunamadi": "No face found. Point your camera at your face.",
    "yuz.maks-kisi": "Maximum number of people ({n}) reached.",
    "yuz.uyari-cok-yuz": "{n} faces in the frame — the largest one was saved. Take the photo alone to avoid enrolling the wrong person.",
    "yuz.uyari-uzak": "This frame is far from the existing records of '{ad}' (distance {mesafe}). It may be a different person or very poor lighting.",
    "yuz.uyari-zaten-kayitli": "This face is already enrolled as '{ad}' (distance {mesafe}). Are you enrolling a new person, or is the name wrong?",
    "yuz.uyari-daha-yakin": "Warning: this frame is closer to '{yabanci}' ({yabanci_mesafe}) than to '{ad}' ({mesafe}).",
    "yuz.sahip-yok": "No face owner is set. Log in with your password and use 'Save my face', or set FACE_OWNER_NAME.",
    "yuz.kare-yok": "No frame was sent.",
    "yuz.kayit-yok": "Record #{id} not found.",
    "yuz.kisi-yok": "No enrolled person named '{ad}' found.",
    "yuz.sahip-silme-onay": "'{ad}' is the owner — deleting turns off face login. Confirmation required.",
    "yuz.tek-kayit": "This is the only record of '{ad}' — deleting it makes the person unrecognizable. Use the person card to delete the person entirely.",
    # ──  ⑧ kalan backend metinleri (elle; birlestir.py'nin bloğu DIŞINDA)
    "saglik.kota-bilinmiyor": "This service's daily limit is unknown.",
    "ekip.kota": "Your free quota: {detay}",
    "ekip.maliyet-mesaj": "The team will split this into {gorevler} specialists. Estimated cost: {en_az}-{en_cok} model requests.",
    "ekip.maliyet-baslik": "Team run — cost approval",
    "llm.claude-cli-yok": "'claude' CLI not found. Claude Code must be installed.",
    "llm.bilinmeyen-saglayici": "Unknown provider: {kimlik}",
    "llm.env-ayarlanmamis": "{env} is not set — enter it in {ui_ayar} → {ui_anahtar}.",
    "llm.anahtar-bos": "The key is empty.",
    "chatgpt.giris-yok": "Sign in with ChatGPT first.",
    "chatgpt.plan-kapali": "The ChatGPT sign-in did not grant plan usage — inference is not possible.",
    "chatgpt.secildi": "ChatGPT account selected ({model}).",
    "llm.yerel-anahtar-istemez": "{ad} doesn't need a key — the model runs on your computer. Just pick the provider and press **Save and test**.",
    "llm.env-yazilamadi": "Couldn't write .env: {sebep}",
    "llm.depo-dosya": "Your key is stored unencrypted in a file on this computer (readable only by your user). No operating-system keyring was found. On Linux, once GNOME Keyring or KWallet is installed and unlocked, Yuki moves the key there on the next start.",
    "llm.yerel-degil": "Not a local provider: {kimlik}",
    "llm.bos": "(empty)",
    "llm.yerel-hazir": "{model} is running on this computer — ready to chat ✓",
    "stt.metne-cevrilemedi": "Couldn't turn your speech into text — could you try again?",
    "ses.yanit-zaman-asimi": "Response timed out",
    "ses.gecersiz-json": "Invalid JSON",
    "ses.sunucu-hatasi": "Server error: {sebep}",
    "belge.desteklenmeyen": "Unsupported document type: {uzanti}",
    "belge.metin-yok": "Couldn't extract text from the file (it may be empty or a scanned image).",
    "cihaz.zaman-asimi": "Timed out",
    "yedek.klasor-yok": "Folder not found: {yol}",
    "yedek.yalniz-klasor": "Only folders can be added (not single files).",
    "yedek.disk-koku": "The whole disk can't be backed up — pick a folder inside it (e.g. Documents, Desktop, Pictures).",
    "yedek.zaten-ekli": "This folder is already added.",
    "yedek.ust-klasor-ekli": "'{var}' is already added and contains this folder.",
    "yedek.alt-klasor-ekli": "This folder contains '{var}', which is already added — remove that one first.",
    "yedek.google-bagla": "Your Google account isn't connected — connect it in {ui_ayar} → {ui_google}, then backup can run.",
    "yedek.tamamlanamadi": "Backup couldn't finish: {sebep}",
    "llm.model-gemma": "Gemma 4 26B — free (recommended)",
    "llm.model-gptoss": "gpt-oss 20B — free (backup)",
    "llm.model-gpt41mini": "GPT-4.1 mini — paid, more capable",
    "llm.grup-ucretsiz-dogrulandi": "Free — verified",
    "llm.grup-ucretsiz-canli": "Free — from the live list (not tested)",
    "llm.grup-ucretli": "Paid",
    "llm.grup-kurulu": "Models installed on your computer",
    "llm.grup-onerilenler-anahtarsiz": "{ad} — recommended (full list appears once you enter a key)",
    "llm.grup-onerilen": "{ad} — recommended",
    "llm.grup-onerilenler": "{ad} — recommended",
    "llm.grup-tum": "{ad} — all models",
    "llm.grup-ad": "{ad}",
    "llm.yerel-model-yok": "Ollama is running but no chat model is installed. Run `ollama pull llama3.1` in the terminal.",
    "llm.lisans-anahtari-kutusu": "This is a **license key**, not an AI key. Enter your license in {ui_ayar} → {ui_lisans}. Your {ad} key goes here — you can get it at {url}. Your current key was not touched.",
    "llm.anahtar-bicim": "{ad} keys start with `{onek}`; what you entered doesn't. Copy the key from {url}. (Note: you need an **API key**, not a **subscription**.) Your current key was not touched.",
    "llm.anahtar-reddedildi": "The key was tried but {ad} rejected it: {sebep} — **your current key was kept**, nothing was changed.",
    "llm.anahtar-reddedildi-ilk": "The key was tried but {ad} rejected it: {sebep} — nothing was saved.",
    "llm.anahtar-calisiyor": "{ad} key works — ready to chat ✓",
    "llm.secim-anahtar-yok": "No saved key for {ad} — enter your key first.",
    "llm.secim-denenemedi": "{ad} did not answer with this model ({model}): {sebep} — **your previous setting was kept**.",
    "llm.secim-uygulandi": "{ad} · {model} selected and tested ✓",
    "llm.ollama-ulasilamadi": "Could not reach Ollama at {adres} ({teknik}). Is Ollama installed and running? Install: ollama.com/download — then run `ollama serve` in the terminal. Your current settings were not touched.",
    "llm.yerel-model-kurulu-degil-liste": "`{model}` isn't installed on this computer. Run `ollama pull {model}` in the terminal. Installed: {kurulu}. Your current settings were not touched.",
    "llm.yerel-model-kurulu-degil": "`{model}` isn't installed on this computer. Run `ollama pull {model}` in the terminal. No models are installed right now. Your current settings were not touched.",
    "llm.yerel-model-yanitsiz": "`{model}` couldn't be loaded or didn't respond: {sebep} — **your current settings were kept**. The model is loaded into memory on first use; with a large model this can take a while, try again.",
    "ses.konusma-algilanamadi": "Audio arrived but no speech was detected — your microphone level may be low.",
    "ses.kayitli-ses-degil": "This voice did not match the enrolled voice; the command was ignored.",
    "ses.uyandirma-yok": "No wake word — say 'Yuki' first for your message.",
    # ── / ⑧
    # ──  ⑨ ekranda görünen kalan backend metinleri (paket 1, 2026-09-25)
    "llm.saglayici-genel": "Provider",
    "llm.baglanamadi-tekrar": "Couldn't reach the LLM provider — try again.",
    "llm.hata-onek": "Error: {mesaj}",
    "llm.claude-code-baglanti": "Claude Code connection failed — {sebep}",
    "llm.cevap-kesildi": "\n\n[The answer hit the length limit. Say 'continue' and I'll go on.]",
    "llm.bos-cevap": "The model returned an empty answer, so I have nothing to show. Could you ask again?",
    "llm.anthropic-baglanti": "Anthropic connection failed — {sebep}",
    "llm.islem-sorunu": "Something went wrong while processing — try again.",
    "llm.anthropic-paket-yok": "The 'anthropic' package isn't installed. Run `pip install anthropic`.",
    "llm.claude-cli-hata": "Claude CLI — {sebep}",
    "llm.bilinmeyen-hata": "unknown error",
    "llm.claude-cli-zaman-asimi": "Claude CLI timed out ({sn} s).",
    "llm.yanit-alinamadi": "No response received.",
    "llm.arac-kullaniyor": "Yuki is using the '{arac}' tool…",
    "llm.model-bos-yanit": (
        "The selected model returned an empty response (the request succeeded but no content came back). "
        "This happens with some free models. Try picking another model in {ui_ayar} → {ui_anahtar} "
        "— the ones in the '{grup}' group were tested."
    ),
    "llm.preset-gpt41-mini": "GPT-4.1 Mini (Default)",
    "llm.preset-gpt41": "GPT-4.1 (Strong)",
    "brifing.gunaydin": "Good morning. Today is {tarih}. Your system is ready. Have a good day.",
    "brifing.gorevler": " You have {bugun} tasks due today.",
    "brifing.gorevler-gecikmeli": " You have {bugun} tasks due today, {geciken} of them overdue.",
    "brifing.geciken-hatirlatma": "Reminder: you have {n} overdue tasks. Would you like to open the planner to check them?",
    "bildirim.haber-baslik": "News update ({saat}):",
    "bildirim.uyanis": "Welcome back! How was waking up from sleep? ❄",
    "bildirim.internet-kesildi": "Internet connection lost.",
    "bildirim.internet-geldi": "Internet connection restored. 🌐",
    "bildirim.deprem-baslik": "🌍 Earthquake Alert",
    "bildirim.deprem-metin": "M{buyukluk} earthquake — {yer} (depth {derinlik} km)",
    "bildirim.tanidim": "Hello {ad}! I recognized you.",
    "acilis.playwright-yok": "BROWSER_ENABLED=true but playwright isn't installed",
    "acilis.auth-acik": (
        "AUTH_TOKEN is empty and the server is bound to {host} — auth is DISABLED and "
        "this address is reachable from outside. Set a strong AUTH_TOKEN (32+ characters) in .env."
    ),
    "ses.edge-notu": "Microsoft — always available (fallback)",
    "ses.google-notu": "Google Translate voice — only if Edge does not respond (text is sent to Google)",
    "ses.test-metni": "Hello! The voice system is ready and working.",
    "ses.fish-referans-notu": "Set the FISH_REFERENCE_AUDIO environment variable to this path and restart the service.",
    "hata.tekrar-dene": "Something went wrong — please try again.",
    "pydeps.bulunamadi": "No new library found — the download may not have finished.",
    "ayar.izinsiz-anahtar": "Setting key not allowed: {anahtar}",
    # ── / ⑨
    # ──  ⑥ backend hata metinleri (birlestir.py üretir — elle düzenleme)
    "cihaz.ag-yalniz-yerel": "The server is currently reachable only from this computer. To let another device connect, open Yuki to the local network from HQ › Devices.",
    "cihaz.ag-kilit-yok": "Set up the app lock first (Settings › Security) to open Yuki to your network.",
    "api.cok-yanlis-anahtar": "Too many wrong key attempts — temporarily locked.",
    "cihaz.ag-kilitsiz-uzak": "There is no app lock, so Yuki is closed to the network. Only this computer can make this request.",
    "cihaz.bagli-degil": "Device not connected",
    "cihaz.eylem-yok": "This action is not supported",
    "cihaz.izin-kapali": "This action is turned off. You can enable it in HQ › Devices with your access key.",
    "cihaz.izin-anahtar-yok": "To enable this permission, first set AUTH_TOKEN (access key) in your .env file.",
    "cihaz.izin-anahtar-yanlis": "The access key is wrong or empty.",
    "cihaz.bulunamadi": "Device not found",
    "cihaz.ultra-gerekli": "Device management is disabled in this install.",
    "cihaz.ws-dogrulanamadi": "Authentication failed",
    "cihaz.ws-kimlik-yok": "No credentials",
    "cihaz.ws-kod-gecersiz": "Invalid pairing code",
    "cihaz.ws-taninmiyor": "Device not recognized",
    "cihaz.ws-ultra": "Device management disabled",
    "duvar.boyut-asimi": "File exceeds the {mb} MB limit.",
    "duvar.bulunamadi": "Wallpaper not found.",
    "duvar.desteklenmeyen": "Unsupported format: {uzanti}. Accepted: {kabul}",
    "duvar.gecersiz-kimlik": "Invalid wallpaper ID.",
    "duvar.icerik-uyusmuyor": "File content does not match the {uzanti} format.",
    "duvar.karakter-yok": "Character assets not found: {yol}",
    "duvar.sebep-boyut": "size limit",
    "duvar.sebep-kaynakta-yok": "missing from source",
    "duvar.sebep-zaten-yuklu": "already uploaded",
    "duvar.uzantisiz": "(no extension)",
    "fitness.egzersiz-yok": "Exercise not found",
    "fitness.ogun-yok": "Meal not found",
    "fitness.sablon-yok": "Template not found",
    "fitness.tarih-gecersiz": "Invalid date: {deger} — expected format YYYY-MM-DD",
    "google.bagli-degil": "Google account not connected",
    "google.drive-dolu": "Your Google Drive storage is full — backup paused. Free up space in Drive, then continue with 'Back up now'.",
    "google.drive-api-kapali": "The Drive API isn't enabled in your Google Cloud project — enable \"Google Drive API\" (step 2 of the guide), then try again.",
    "yedek.ag-hatasi": "Backup stopped midway — your internet may have dropped or Google didn't answer for a moment. Try again in a few minutes; backup only sends what is left.",
    "yedek.drive-gecici": "Google Drive didn't accept the request just now — try again in a few minutes; backup only sends what is left.",
    "yedek.drive-reddetti": "Google Drive refused this request. Details are under \"Technical detail\"; if it persists, reconnect from the Google panel.",
    "google.drive-hatasi": "Google Drive error ({kod}): {govde}",
    "google.drive-izin-yok": "This connection does not include Drive access — {ui_ayar} → {ui_google} → 'Reconnect' and keep the Drive permission checked on the consent screen.",
    "google.drive-reddetti": "Google Drive refused (403): {govde}",
    "google.kimlik-gecersiz": "Your Google client ID is invalid — re-enter the client ID and client secret via {ui_ayar} → {ui_google} → 'Change'. The most common cause: the client was deleted in Google Cloud or copied incompletely. The steps are behind the 'Open illustrated guide' button on the same screen.",
    "google.token-yenilenemedi": "Could not refresh the Google token ({kod}): {govde}",
    "google.yetki-dustu": "Your Google connection dropped — Google no longer accepts this connection's permission. Three possible causes: ① the permission was removed from your Google account (myaccount.google.com/permissions) ② the account password changed or Google signed sessions out for security reasons ③ the consent screen in Google Cloud is still in 'Testing' status — in that state Google revokes access after 7 days (step 4 of the guide: Publishing status → In production). The fix is usually the same: {ui_ayar} → {ui_google} → 'Reconnect'.",
    "google.kimlik-degisti": "You changed the client ID — the old connection doesn't work with the new one. {ui_ayar} → {ui_google} → 'Reconnect'.",
    "google.istemci-yetkisiz": "Google won't refresh this connection with the saved client ID — the connection was made with a different client, or the client type changed. {ui_ayar} → {ui_google} → 'Reconnect'; if it persists, check in the guide that the client type is 'Desktop app'.",
    "gorme.ekran-alinamadi": "Couldn't capture the screen",
    "gorme.izleyici-henuz-yok": "Ambient Watcher hasn't started yet.",
    "gorme.izleyici-yok": "Ambient Watcher is not started.",
    "gorme.kapali": "AMBIENT_ENABLED=false — enable it in .env first.",
    "harita.adsb-basarisiz": "All ADS-B sources failed",
    "harita.afad-bos": "AFAD returned an empty list",
    "harita.afad-format": "Unexpected AFAD format",
    "harita.ais-anahtar-yok": "AISStream API key required — add AISSTREAM_API_KEY to .env",
    "harita.cctv-basarisiz": "All CCTV sources failed: {kaynaklar}",
    "harita.firms-bos": "FIRMS CSV is empty or could not be parsed",
    "harita.gdelt-format": "Unexpected GDELT lastupdate format",
    "harita.gdelt-indirilemedi": "None of the GDELT export files could be downloaded",
    "harita.haber-bos": "Google News RSS is empty or could not be parsed",
    "harita.kp-parse": "NOAA K-index data could not be parsed",
    "harita.open-meteo-aq-sehir-yok": "Open-Meteo AQ: no city could be fetched",
    "harita.open-meteo-sehir-yok": "Open-Meteo: no city could be fetched",
    "harita.openaq-bos": "OpenAQ station list is empty",
    "harita.opensky-bos": "OpenSky returned an empty state list",
    "harita.poi-alan-zorunlu": "name, lat and lng are required",
    "harita.poi-bulunamadi": "POI not found",
    "harita.pro-gerekli": "The map dashboard is disabled in this install.",
    "harita.sismik-ayrisamadi": "Sismik Harita reported records but none could be parsed",
    "harita.sismik-format": "Unexpected Sismik Harita format: {ham}",
    "harita.tle-basarisiz": "All TLE sources failed",
    "harita.usgs-format": "Unexpected USGS feed format",
    "harita.volkan-bos": "USGS volcano list is empty or could not be parsed",
    "medya.bulunamadi": "File not found",
    "medya.dosya-buyuk": "File too large (max 10 MB)",
    "medya.format": "Unsupported format. Allowed: {izinli}",
    "medya.gecersiz-ad": "Invalid file name",
    "medya.metin-cikmaz": "Text can't be extracted from this file type",
    "medya.yalniz-gorsel": "This endpoint is for images only — use /extract for documents",
    "mod.ad-zorunlu": "Mode name is required.",
    "mod.bulunamadi": "Mode not found: {id}",
    "mod.kapali": "'{ad}' mode is turned off — turn it on first.",
    "mod.baslatici-kapali": "Mode launcher is off — turn it on in {ui_ayar} → System → Mode launcher.",
    "mod.uyari-bos": "The mode looks empty (no apps/workspace) — starting it won't do anything.",
    "mod.uyari-ozel-alan": "Both a special workspace and a workspace were given — the special workspace will be used.",
    "mod.uyari-whitelist": "'{uygulama}' isn't on the whitelist — it may not open.",
    "monitor.doktor-yorumlanamadi": "I can't interpret the system status right now, please try again.",
    "monitor.surec-bulunamadi": "Process not found",
    "planlayici.baslangic-gecersiz": "Invalid baslangic — expected format 2026-08-31T00:00:00+03:00",
    "planlayici.saat-dilimi-gecersiz": "Unknown time zone",
    "planlayici.basliksiz": "(Untitled)",
    "planlayici.env-yazilamadi": "Couldn't write the settings file: {sebep} [source: .env write]",
    "planlayici.gecersiz-state": "Invalid state token — possible CSRF attack detected. Please try again.",
    "planlayici.hesap-baglandi": "Your Google account is connected",
    "planlayici.izin-drive-yok": "Calendar access granted, <b>Drive access was not</b> — Yuki can't back up to Drive. {duzelt}",
    "planlayici.izin-duzelt": "To fix it: {ui_ayar} → {ui_google} → <b>Reconnect</b>, and on the consent screen <b>leave both boxes checked</b>.",
    "planlayici.izin-hic-yok": "<b>No access was granted</b> — Yuki can neither read your calendar nor back up to Drive. {duzelt}",
    "planlayici.izin-takvim-yok": "Drive access granted, <b>Calendar access was not</b> — Yuki can't read your calendar or add events. {duzelt}",
    "planlayici.izin-tam": "Calendar and Drive access granted. You can close this tab and return to <b>Yuki</b>.",
    "planlayici.kimlik-bicimsiz": "This doesn't look like a Google client ID — it should end with '{ek}'. Copy the 'Client ID' field from Google Cloud Console → Credentials.",
    "planlayici.kimlik-bos": "Client ID and client secret can't be empty.",
    "planlayici.kimlik-yok": "To connect a Google account, first enter your own Google client ID: {ui_ayar} → {ui_google} → 'Client ID'. Step-by-step instructions are behind the 'Open illustrated guide' button on the same screen.",
    "planlayici.takvim-bagli-degil": "Google Calendar is not connected",
    "planlayici.token-gecersiz": "Google token is invalid — please reconnect",
    "planlayici.donus-basarisiz": "Couldn't connect your Google account",
    "planlayici.donus-eski-baglanti": "This approval link is old or was already used. Go back to Yuki and press 'Connect with Google' again.",
    "planlayici.donus-google-hatasi": "Google didn't complete the connection (code {kod}). Try again from Yuki in a moment.",
    "planlayici.donus-kapat": "You can close this tab and return to Yuki.",
    "planlayici.donus-kod-gecersiz": "The approval code expired or was already used. Go back to Yuki and press 'Connect with Google' again.",
    "planlayici.donus-reddedildi": "Permission wasn't granted on the consent screen, or the process was cancelled. You can try again in Yuki: {ui_ayar} → {ui_google} → 'Connect with Google'.",
    "planlayici.donus-ulasilamadi": "Yuki couldn't reach Google — check your internet connection and try again from Yuki.",
    "planlayici.donus-yonlendirme": "Google rejected the return address (redirect_uri_mismatch) — the client type is most likely 'Web application'. As in the guide, create a new client of type 'Desktop app' and enter it in Yuki with 'Change'.",
    "planlayici.google-cevapsiz": "Google Calendar didn't respond just now — your connection is fine, try again in a moment.",
    "planlayici.google-yogun": "Google says it's receiving too many requests — try again in a few minutes.",
    "planlayici.hesap-baglandi-eksik": "Your Google account is connected — but a permission is missing",
    "planlayici.takvim-izni-yok": "Calendar permission wasn't granted — Google doesn't let this connection access your calendar. {ui_ayar} → {ui_google} → 'Reconnect' and leave the calendar box checked on the consent screen.",
    "takvim.arac-bagli-degil": "Google Calendar isn't connected. To connect: {ui_ayar} → {ui_google}.",
    "takvim.arac-hata": "Google Calendar didn't complete the request (code {kod}).",
    "takvim.arac-ulasilamadi": "Google Calendar can't be reached right now — try again in a moment.",
    "takvim.sil-adsiz": "(untitled event)",
    "takvim.sil-onay-baslik": "Delete this calendar event?",
    "takvim.sil-onay-etiket": "Event to delete:",
    "takvim.sil-onay-mesaj": "Yuki wants to delete an event from your Google Calendar. This can't be undone.",
    "portre.anahtar-yok": "FAL_KEY is not set in .env — fal.ai animation unavailable.",
    "portre.avatar-yok": "Yuki avatar not found: {yol}",
    "portre.devre-acik": "fal.ai disabled (circuit breaker open — repeated errors).",
    "portre.durum-anahtar-yok": "FAL_KEY is not set — micro-animation layer is off.",
    "portre.durum-devre-acik": "fal.ai disabled (repeated errors — circuit breaker open).",
    "portre.gecersiz-aksiyon": "Invalid action. Valid: {gecerliler}",
    "portre.klip-hatasi": "Clip generation failed [source: fal.ai]: {sebep}",
    "portre.video-url-yok": "No video URL in the fal.ai response: {sonuc}",
    "saglik.anahtar-ayarli": "{saglayicilar} key saved.",
    "saglik.anahtar-cozum": "Choose a service on the {ui_menu_anahtar} screen and enter its key — OpenRouter starts free, no credit card required.",
    "saglik.anahtar-gerekmiyor": "No key needed — {saglayici} runs on this computer.",
    "saglik.anahtar-yok": "No key entered — Yuki can't reply.",
    "saglik.baslik-disk": "Free space",
    "saglik.baslik-ffmpeg": "Audio conversion",
    "saglik.baslik-llm-anahtar": "AI key",
    "saglik.baslik-llm-kota": "Free usage",
    "saglik.baslik-llm-model": "Model",
    "saglik.baslik-onnxruntime": "Vision and semantic memory",
    "saglik.baslik-stt": "Voice typing",
    "saglik.baslik-veri-dizini": "Data folder",
    "saglik.disk-az": "Only {gb} GB free.",
    "saglik.disk-bos": "{gb} GB free.",
    "saglik.disk-cozum": "Speech recognition and memory models need at least 2 GB of free space.",
    "saglik.disk-olculemedi": "Free space couldn't be read ({neden}).",
    "saglik.ffmpeg-cozum": "Nothing to do; speech recognition keeps working.",
    "saglik.ffmpeg-pyav": "Voice recordings from your phone can be read.",
    "saglik.ffmpeg-yedek": "Voice recordings from your phone can be read (via ffmpeg).",
    "saglik.ffmpeg-yok": "No audio converter found — speech is still transcribed, only silence detection is off.",
    "saglik.kota-ucretli-model": "{model} is a paid model — no free daily limit applies.",
    "saglik.kur-basarisiz": "Installation failed (code {kod}). You can try manually: {url}",
    "saglik.kur-baslatilamadi": "Could not start the installer: {hata}",
    "saglik.kur-bilinmeyen": "Unknown installation: {kimlik}",
    "saglik.kur-dosya-kucuk": "downloaded file is smaller than expected ({bayt} bytes)",
    "saglik.kur-indirilemedi": "Download failed: {hata} — you can download and install it manually in your browser: {url}",
    "saglik.kur-iptal": "Installation cancelled (administrator approval not given).",
    "saglik.kur-kuruldu": "Installed. Close and reopen Yuki.",
    "saglik.kur-yalniz-windows": "This installation only applies to Windows.",
    "saglik.kur-yeniden-baslat": "Installed — you need to restart Windows.",
    "saglik.kur-zaten-yeni": "A newer version is already installed — the problem is elsewhere. Share the error log.",
    "saglik.model-kalkti": "The selected model ({model}) was removed from OpenRouter — Yuki can't reply.",
    "saglik.model-kalkti-cozum": "Fix picks a free model that works on the same service. Your service stays the same.",
    "saglik.model-liste-alinamadi": "{model} is selected; OpenRouter couldn't be reached, so whether it's still available couldn't be checked.",
    "saglik.model-liste-disi": "`{model}` is selected; whether this {saglayici} model is still available can't be checked from here — this check only works on OpenRouter and for models on this computer.",
    "saglik.model-ollama-cozum": "Is Ollama running? Start it in a terminal with `ollama serve`.",
    "saglik.model-ollama-ulasilamadi": "Ollama couldn't be reached — `{model}` can't reply right now.",
    "saglik.model-sec-cozum": "Choose a model on the {ui_menu_anahtar} screen.",
    "saglik.model-secilmemis": "No model selected — Yuki can't reply.",
    "saglik.model-yerel-cozum": "Run `ollama pull {model}` in a terminal or choose an installed model.",
    "saglik.model-yerel-kurulu": "`{model}` is installed on this computer.",
    "saglik.model-yerel-yok": "`{model}` isn't installed on this computer — Yuki can't reply.",
    "saglik.onar-desteklenmiyor": "'{kimlik}' can't be fixed automatically — follow the suggested solution.",
    "saglik.onar-klasor-olmadi": "The folder `{yol}` couldn't be created ({neden}).",
    "saglik.onar-model-degisti": "Model switched to {model} — your service stayed the same, and the choice is saved.",
    "saglik.onar-ucretsiz-model-yok": "No free model is available on OpenRouter right now. You can choose a paid model on the {ui_menu_anahtar} screen.",
    "saglik.onnx-cozum-paket": "The installer looks incomplete or partially downloaded. First try downloading and installing Yuki again from the website. If the problem persists, you can install Microsoft's runtime package with the button below.",
    "saglik.onnx-cozum-vcredist": "The runtime libraries are in the package, but loading still failed. Install Microsoft Visual C++ Redistributable (x64) with the button below and restart the app.",
    "saglik.onnx-eksik-dll": " · runtime library missing from the package: {dll}",
    "saglik.stt-cozum-vcredist": "Install Microsoft Visual C++ Redistributable (x64) with the button below and restart the app.",
    "saglik.stt-model-cozum": "It downloads by itself on your first voice message (~500 MB); that one will be a little slower. You can also download it now in the {ui_menu_ses} settings.",
    "saglik.stt-model-yok": "The speech engine is ready but the speech model hasn't been downloaded yet.",
    "saglik.stt-motor-yok": "The speech recognition engine couldn't start — voice typing doesn't work.",
    "saglik.vcredist-etiket": "Install the Microsoft VC++ package",
    "saglik.vcredist-uyari": "About 25 MB is downloaded from Microsoft's server and the installer starts. Windows will ask for administrator approval (UAC). This is a free Microsoft package many programs need.",
    "saglik.veri-dizini-cozum": "Run the app as a normal user, not as administrator. If the problem persists, move the install folder out of Program Files.",
    "saglik.veri-dizini-yazilamiyor": "The folder `{yol}` isn't writable ({neden}) — your settings and conversations can't be saved.",
    "saglik.kota-ucretli-servis": "{saglayici} is a paid service — no free daily limit applies.",
    "saglik.model-duruyor": "Available on OpenRouter: {model}.",
    "saglik.model-sec-cozum-oto": "Fix picks a free model that works on OpenRouter. Your service stays the same.",
    "saglik.onar-klasor-hazir": "Data folder ready — `{yol}` is writable now.",
    "saglik.onar-klasor-yazilamiyor": "The folder `{yol}` exists but isn't writable ({neden}). Run Yuki as a normal user, not as administrator; if it persists, check the folder's permissions.",
    "saglik.onar-liste-alinamadi": "OpenRouter couldn't be reached, so the list of working models couldn't be fetched. Try again shortly or choose a model on the {ui_menu_anahtar} screen.",
    "saglik.onar-model-elle": "I can't fix this automatically for {saglayici} — I can only list working models on OpenRouter. Choose a model on the {ui_menu_anahtar} screen.",
    "saglik.onar-model-gecici": "Model switched to {model}, but it couldn't be written to the settings file — Yuki will go back to the old model after a restart. Choose the model again on the {ui_menu_anahtar} screen.",
    "saglik.onnx-acilamadi": "The engine couldn't start — reading text in images and semantic memory don't work.",
    "saglik.onnx-hazir": "Reading text in images, QR codes and semantic memory are available.",
    "saglik.stt-hazir": "Speech engine and speech model are ready.",
    "saglik.veri-dizini-iyi": "Your settings and conversations can be saved (`{yol}`).",
    "saglik.gunluk-silinemedi": "The error log couldn't be deleted — the file is in use or can't be written.",
    "saglik.hata-izin": "no permission",
    "saglik.hata-bulunamadi": "folder not found",
    "saglik.hata-disk-dolu": "disk full",
    "saglik.hata-genel": "the system refused — details are in the error log",
    "saglik.kota-openrouter": "50 messages a day, 20 a minute — if you hit the limit it reopens the next day; Yuki isn't broken.",
    "saglik.model-ucretsiz-ad": "{ad} — free",
    "saglik.motor-cozum-diger": "Try downloading and installing Yuki again from the website; if it persists, use Copy on the error log and send it when asking for support.",
    "stt.bilinmiyor": "unknown",
    "stt.dosya-buyuk": "File too large (max 25MB)",
    "stt.format": "Unsupported audio format",
    "stt.model-yok": "The speech recognition model hasn't been downloaded yet.",
    "stt.model-indirilemedi": "The speech recognition model couldn't be downloaded (check your internet connection or access to huggingface.co). Details: {ayrinti}",
    "stt.motor-yuklenemedi": "The speech recognition engine couldn't load on this machine (usually a missing system library). Details: {ayrinti}",
    "todo.alt-gorev-yok": "Subtask not found",
    "todo.gecersiz-filtre": "Invalid filter: {filtre}. Valid filters: {gecerli}",
    "todo.gorev-copte-degil": "Task not found or not in the trash",
    "todo.gorev-yok": "Task not found",
    "todo.gorev-zaten-aktif": "Task not found or already active",
    "todo.kayit-yok": "Entry not found",
    "todo.kendine-bagimli": "A task cannot depend on itself",
    "todo.liste-yok": "List not found",
    "todo.takvim-esitleme-hatasi": "Calendar sync error [source: Google Calendar API]: {sebep}",
    "todo.takvim-etkinligi-yok": "Calendar event not found",
    "todo.takvim-silme-hatasi": "Calendar delete error [source: Google Calendar API]: {sebep}",
    "todo.tarihsiz-takvim": "A task without a date cannot be added to the calendar",
    "yedek.en-az-bir": "{alan} must be at least 1.",
    "yedek.google-bagli-degil": "Your Google account isn't connected.",
    "yedek.kapali": "Backup is off — turn it on in the panel first.",
    "yedek.kaynak-yok": "Source not found.",
    "yedek.pro-ozelligi": "Google Drive backup is disabled in this install.",
    "yedek.tur-suruyor": "A backup run is already in progress.",
    "yedek.zamanlama-bicim": "Schedule must be in 'HH:MM' format (e.g. 03:30).",
    # ── Workshop notifications (g4 2026-11-12; services/gorev_bildirim · gorev_onerici)
    "atolye.bildirim-baslik": "Yuki · Workshop",
    "atolye.bitis-bitti": "{tur} task finished — see the result in Workshop.",
    "atolye.bitis-yarim": "{tur} task left unfinished — check it in Workshop.",
    "atolye.bitis-hata": "{tur} task failed — details in Workshop.",
    "atolye.bitis-durdu": "{tur} task stopped — open Workshop to continue.",
    "atolye.tur-site": "Site",
    "atolye.tur-arastirma": "Research",
    "atolye.tur-sahne": "Research scene",
    "atolye.tur-deneme": "Trial",
    "atolye.tur-varsayilan": "Workshop",
    "atolye.oneri-cok": "{n} task suggestions — APPROVE or SKIP in Workshop.",
    "atolye.oneri-tek": "A new task suggestion — APPROVE or SKIP in Workshop.",
    # ── / ⑥
}
