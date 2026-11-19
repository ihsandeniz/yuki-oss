# Changelog

All notable changes to Yuki are documented here. The format follows
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/).

> 🇹🇷 Türkçe özet her sürümün altında.

## [1.0.0] - 2026-11-19 — first open-source release

The history is published as a single initial commit.

### Added
- **Health score** — `GET /api/saglik` shows the latest measurement and its age;
  "not measured" is reported separately from "failed". `POST /api/saglik/olc` runs a fresh
  measurement. Five generic sensors, shown in *My Computer › Health*.
- **Gallery** — read-only media browser. Roots come from settings; files are addressed by id,
  never by path; byte-range streaming with short-lived tickets. No delete, no move.
- **File browser** — read-only, no terminal. Same id/ticket model as the gallery.
- **Map bridge** — the assistant can move the map and switch layers (`map_goto`,
  `map_layer`, `map_status`); the result of the action is reported back to the conversation.
- **Sign in with ChatGPT** — the official OAuth (PKCE) flow; the token is stored locally with
  `0600` permissions. Bring-your-own-key keeps working.
- **HQ panels** — settings, modes, system and notifications, covered by a contract test.
- **Workshop** (on by default, `ATOLYE=false` turns it off) — background tasks in their own work
  folder (no shell, no writes outside it). Task suggestions ("shall I do this?") from a Plan
  list, unfinished tasks and repeated tasks: the engine cannot start a task, every suggestion
  waits for APPROVE; a round every 30 minutes, daily cap, quiet hours. Finish notification
  (Web Push, no task content) and a research scene view. Settings: `YUKI_ATOLYE_*` in `.env.example`.
- **Backup tab** (BACKUP) — the Drive backup screen moved out of Settings into its own tab.
- **Fitness** (off by default) — workouts with templates and focus mode, meals, history heat
  map, levels/leagues/titles, weekly summary, 21:00 reminder; English and Turkish. Switched on
  in *HQ › System › Fitness* without a restart (or `FITNES=true`). Data stays in the local store;
  old Postgres fitness data is imported once.
- **News clustering** in MAP › NEWS — one line per story with a `+N` sources badge
  (`GUNDEM_KUME=0` turns it off) — and an optional **filler sound**: a short "Hmm." when the
  reply is slow (off by default; *HQ › Voice & TTS* or `DOLGU_SESI=1`).
- **Camera vision** (`GORUS`, off by default) — "Yuki, look": one frame from the camera is
  described by a vision model **on this computer** (default: Ollama `qwen2.5vl:3b` on
  `127.0.0.1`; a non-local model address is refused). Presence, a welcome-back for an enrolled
  face login, and a break reminder after 50 minutes. Frames stay in memory, never saved or sent.
- **Voice identity** (`SES_KIMLIK`, off by default) — voice commands from anyone but the
  enrolled voice are ignored. Only a 192-number voiceprint is kept locally; recordings are not
  stored. The CAM++ model (3D-Speaker, Apache-2.0) is **not** shipped: download it from
  `https://huggingface.co/csukuangfj/speaker-embedding-models` and set `SES_KIMLIK_MODEL`.
  It filters TV and other people; it is not a security lock.
- Both biometric features need an explicit, versioned consent given **from this computer**
  (*HQ › System*); withdrawing it turns the camera off and deletes the voiceprint.
- **Send to Yuki** from the file browser (up to 10 files, 15 MB each) and optional **safe file
  operations** in Files and Gallery — move to trash, move, undo — off by default, switched on
  with the `AUTH_TOKEN` access key; one-time confirmation per operation, no permanent delete.
- **Scheduler time zone** — reminders, the morning briefing, nightly maintenance and the
  fitness "day" follow the computer's own time zone. `SCHEDULER_TIMEZONE` (IANA name, see
  `.env.example`) overrides it, e.g. on a server or container that runs in UTC.

### Fixed
- **Local model (Ollama) chat history** — with the lightweight memory, Yuki's replies were not
  saved, only your messages; after a reload the history showed one side of the conversation and
  the model did not see its own earlier answers. Replies are saved now (the cloud path already did).
- **Camera photo** — a photo taken with the camera never reached Yuki: the capture was cleared
  before the upload started. It is uploaded and sent to the chat now.
- **Copy button** on chat messages follows the interface language (it was always "COPY").
- **README** — how to get the code, `python3` vs `python`, and complete Windows steps
  (PowerShell). CI runs the README's Windows lines as written and checks `/health`.

### Removed
- **Command canvas (Command Panel)** — removed entirely: the PANEL tab, the `/api/panel/*`
  endpoints (history, saved sites, result, state), its 14 assistant tools (`open_panel` …
  `list_panel_shortcuts`), the `KOMUTA_KANVASI` flag and the desktop app's `<webview>` support
  (`webviewTag` is now always off). A leftover `KOMUTA_KANVASI` line in `.env` is ignored.

### Security
- Device agent: **writing files, deleting files and killing processes are off by default**.
  Each can be enabled with `PUT /api/devices/izinler` and only with the `AUTH_TOKEN` from
  `.env`; an empty token refuses, and clearing the token later revokes the permission.
- Clean-repo gates in CI: secret scan (gitleaks, full history), personal-data and
  internal-trace gates, asset-licence gate, read-only checks for the gallery and file browser.
- Dependencies: `pyasn1` 0.6.5 and `pypdf` 6.21.4 (CVE fixes). `pip-audit` on the shipped
  Linux and Windows bundles reports no known vulnerabilities.

### Not in this release
- 3D Yuki (needs our own VRoid model), hand+eye, Desktop Yuki.
- Flagged features (Workshop, Fitness, camera vision, voice identity): while a
  flag is off, its API returns 404, it is not in the OpenAPI schema, its tools are not offered
  to the assistant and the UI hides it.
- Desktop Yuki (`MASAUSTU_YUKI`) is also off by default but is not hidden: its switch is in
  *HQ › System* and its chat tool is offered when a message mentions the desktop. It only
  starts with your own `.vrm` model (`MASAUSTU_VRM`); none ships with Yuki.

### Known issues
- The `minimatch` advisory (GHSA-g3hv-75wg-m249) in build-time dependencies of
  `electron-builder` is closed with an `overrides` entry in `electron/package.json`
  (minimatch 11). The build tool runs on 26.18.1 (24 had 1 critical and 7 high
  build-time advisories).

### Türkçe
İlk açık kaynak sürümü (1.0.0): Sağlık skoru, salt okunur Galeri ve Dosya gezgini, Harita
köprüsü, ChatGPT ile resmî giriş, HQ panelleri, ayrı YEDEK sekmesi. Atölye varsayılan açık
(`ATOLYE=false` kapatır); Komuta kanvası (Komuta Paneli) tamamen kaldırıldı — sekmesi, `/api/panel/*`
uçları, 14 aracı, `KOMUTA_KANVASI` bayrağı ve masaüstündeki `<webview>` desteği yok. Atölye'de öneri motoru (motor görev
başlatamaz, öneri ONAYLA bekler), bitiş bildirimi ve araştırma sahnesi var. Fitnes varsayılan
kapalı, HQ › Sistem'den yeniden başlatmasız açılır. Harita gündemi aynı olayı tek satırda
topluyor; isteğe bağlı dolgu sesi varsayılan kapalı. Kamera görüşü ("Yuki bak") ve ses kimliği
varsayılan kapalı, ayrıca bu bilgisayardan verilen sürümlü rıza ister; görüntü ve ses yalnız
yerelde işlenir, ses kimliği modeli depoya girmez. Dosya gezgininden "Yuki'ye gönder";
isteğe bağlı güvenli dosya işlemleri (çöpe at, taşı, geri al; kalıcı silme yok) varsayılan
kapalı, erişim anahtarıyla açılır. Cihaz ajanında dosya yazma/silme/program
kapatma kurulumdan kapalı; açmak için `.env`'deki `AUTH_TOKEN` gerekir. 3B Yuki ve El+göz
bu sürümde yok. Düzeltilenler: yerel modelde (Ollama) hafif hafızada Yuki'nin cevapları artık geçmişe yazılıyor; kamerayla çekilen fotoğraf artık Yuki'ye gidiyor; sohbetteki kopyala düğmesi arayüz dilinde; README'de kodu alma adımı, `python3`/`python` farkı ve eksiksiz Windows adımları var, CI bu satırları aynen koşuyor. Bayrağı kapalı özellikte uç 404 döner, arayüz gizler. Masaüstü Yuki (`MASAUSTU_YUKI`) da varsayılan kapalı ama gizli değil: anahtarı
HQ › Sistem'de, sohbet aracı mesajda masaüstü geçince sunulur; yalnız kendi `.vrm` modelinle
açılır (`MASAUSTU_VRM`). Bilinen:
electron-builder'ın derleme-zamanı minimatch bulgusu `electron/package.json` override'ıyla (minimatch 11) kapandı. Paket aracı 26.18.1'e yükseltildi (24'teki 1 kritik + 7 yüksek bulgu kapandı).
