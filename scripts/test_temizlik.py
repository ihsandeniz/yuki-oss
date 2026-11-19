"""Temiz depo kapısı — açık kaynak deposuna sır, kişisel veri ya da iç dosya girmesin.

Koşturma:  python3 scripts/test_temizlik.py [kök]   (varsayılan: deponun kökü)
Kapılar:
  1. gitleaks = 0 bulgu (.gitleaks.toml izin listesiyle)
  2. geliştirici ev dizini yolu ve kişisel e-posta = 0
  3. kişisel veri / yerel durum dosyası = 0
  4. iç çalışma dosyaları (scratchpad, iç notlar, kişisel kurulum) = 0
  5. lisans: LICENSE saf MIT, görsel istisnası NOTICE'ta; frontend/assets'teki her görsel NOTICE kapsamında
  6. kademe kilidi kalmadı: ön yüzde /api/license ve görünür Lite/Pro/Ultra = 0
  7. açık kaynağa girmeyecekler dönmedi: yerel ses (XTTS/RVC/Coqui), gerçek terminal
     (kabuk/paket kurma/süreç öldürme/pty), masaüstü ele geçirme (fare/klavye/pencere),
     güvenlik araçları (SCE/nmap), yazan/terminalli dosya yöneticisi, Modlar'ın komut
     çalıştırması ve Arka Plan İşleri (komut kuyruğu) — kod ve arayüzde 0.
     Tek istisna: SALT OKUNUR + TERMİNALSİZ dosya gezgini (kapı 14); istisna yalnız
     o gezginin beş dosya adını kapsar, genel bir "dosya" muafiyeti yoktur.
  14. dosya gezgini salt okunur: yazma ucu (POST/PUT/PATCH/DELETE, write/unlink/rename/
     shutil.move…) ve pty/xterm/terminal izi = 0; adı "dosya" geçen başka dosya = 0
  8. açık kaynak belgeleri yerinde: README (İngilizce, görsel hakları, buffalo_l uyarısı),
     CONTRIBUTING, CODE_OF_CONDUCT, THIRD_PARTY_LICENSES, issue şablonları, CI sır taraması
  13. varlık lisansı (test_varlik_lisans): depoda .vrm 0; models-manifest.json'un
     indirilebilir `models` bölümünde ticari olmayan lisanslı model (buffalo_l vb.) 0.
     Tek başına:  python3 scripts/test_temizlik.py --kapi test_varlik_lisans
  16. yapay zekâ commit kimliği (test_yz_kimligi_yok): yapay zekâ aracının git kimliği
     (noreply e-postası), Co-Authored-By satırı ve "Generated with" imzası dosyalarda = 0.
     Sağlayıcı konsolu bağlantısı (anahtar alma adresi) meşrudur, desende yok.
  15. iç rapor/karar yolu (test_ic_yol_yok): geliştiricinin çalışma alanına ait
     `reports/20xx-…` ve WIKI/decisions|syntheses|daily… yolları = 0, TAVANSIZ. Ürünün kendi
     wiki aracının yolları (WIKI/sources/…, WIKI/index|log|hot.md) meşrudur, kurala girmez.
"""
import re
import tempfile
import shutil
import subprocess
import sys
from pathlib import Path

# `--kapi <ad>` değerini kök yolu sanma.
_argk = [a for i, a in enumerate(sys.argv[1:], 1)
         if not a.startswith("--") and sys.argv[i - 1] != "--kapi"]
KOK = Path(_argk[0] if _argk else Path(__file__).resolve().parents[1])

# Desenler parçalı yazıldı: bu dosya kendini yakalamasın.
SIZINTI = re.compile("/home/" + "ihsan" + "|" + r"@gmail\." + "com")
KISISEL = {
    ".env", "license.key", "vapid_private.pem", "vapid_public.pem", "memory.db",
    "faces.json", "chat_history.json", "user_profile.json", "todo_store.json",
    "fitness_store.json", "login_guard_state.json", "app_lock.json",
    "config.user.json", "hata-gunlugu.jsonl", "monitor.db",
    # ChatGPT resmî giriş: oturum token'ı (access/refresh/id) ve kurulum kimliği
    "chatgpt_token.json", "chatgpt_host.json", "chatgpt_token.lock",
}
IC = ["scratchpad", "_arsiv-medya", "docs/arsiv", "docs/CLAUDE-ek.md", "CLAUDE.md",
      "agent-run.sh", "launch-agents.sh", "yuki.service", "waybar-yuki.py",
      # gözetimsiz (bulut) koşuların rapor dosyaları — dalda kalır, depoya girmez
      "GECE-RAPOR.md", "IKINCI-GOZ.md"]
ATLA = {".git", "node_modules", "venv", ".venv", "__pycache__", ".pytest_cache", ".ruff_cache", ".mypy_cache"}


def dosyalar():
    for p in KOK.rglob("*"):
        if p.is_file() and not ATLA.intersection(p.relative_to(KOK).parts):
            yield p


def test_gitleaks():
    assert shutil.which("gitleaks"), "gitleaks kurulu değil"
    # Kökten göreli tara: .gitleaks.toml'daki yol izin listesi göreli yazıldı.
    r = subprocess.run(["gitleaks", "dir", ".", "--no-banner", "-c", ".gitleaks.toml"],
                       cwd=KOK, capture_output=True, text=True)
    assert r.returncode == 0, f"gitleaks bulgu verdi (çıkış {r.returncode})"


def test_sizinti_yok():
    bulunan = []
    for p in dosyalar():
        try:
            if SIZINTI.search(p.read_text(errors="ignore")):
                bulunan.append(str(p.relative_to(KOK)))
        except OSError:
            pass
    assert not bulunan, f"ev dizini/e-posta izi: {bulunan}"


def test_kisisel_dosya_yok():
    bulunan = [str(p.relative_to(KOK)) for p in dosyalar()
               if p.name in KISISEL or p.name.startswith("memory.db")]
    assert not bulunan, f"kişisel veri dosyası: {bulunan}"


# Resmî "Sign in with ChatGPT" yolu dışında ChatGPT erişimi girmez: başka bir istemcinin
# (Codex CLI) kimliğine bürünme ya da chatgpt.com özel uçları = 0. Desen parçalı: dosya kendini yakalamasın.
CHATGPT_YASAK = re.compile("codex" + "_cli_rs|originator|chatgpt" + r"\.com/backend-api|services/codex|CodexAsync")


def test_chatgpt_kimlik_izi_yok():
    bulunan = []
    for kok in ("backend", "frontend", "electron", "remote_agent"):
        for p in dosyalar():
            y = p.relative_to(KOK).as_posix()
            if y.startswith(kok + "/") and p.suffix in {".py", ".js", ".mjs", ".html", ".json", ".txt"}:
                if CHATGPT_YASAK.search(p.read_text(errors="ignore")):
                    bulunan.append(y)
    assert not sorted(set(bulunan)), f"ChatGPT kimlik bürünme izi: {sorted(set(bulunan))}"


def test_ic_dosya_yok():
    bulunan = [y for y in IC if (KOK / y).exists()]
    bulunan += [str(p.relative_to(KOK)) for p in KOK.glob("generate_*.py")]
    assert not bulunan, f"iç dosya: {bulunan}"


GORSEL = {".png", ".jpg", ".jpeg", ".webp", ".gif", ".svg", ".ico", ".mp4", ".webm", ".vrm"}


def test_lisans_gorseller_kapsamda():
    lisans = (KOK / "LICENSE").read_text()
    # LICENSE saf MIT kalır (GitHub "MIT" tanısın); görsel istisnası NOTICE'ta
    assert lisans.startswith("MIT License"), "LICENSE MIT başlığıyla başlamıyor"
    assert lisans.rstrip().endswith("OTHER DEALINGS IN THE\nSOFTWARE."), "LICENSE saf MIT değil: sonda ek paragraf var"
    assert "EXCEPTION" not in lisans and "All Rights Reserved" not in lisans, "görsel istisnası LICENSE'ta, NOTICE'a ait"
    notice = (KOK / "NOTICE").read_text()
    assert "All Rights Reserved" in notice and "does NOT" in notice, "NOTICE görsel istisnasını taşımıyor"
    kaliplar = [s.strip() for s in notice.splitlines() if s.strip().startswith("frontend/assets/")]
    assert kaliplar, "NOTICE'te görsel yolu yok"
    disarida = []
    for p in (KOK / "frontend" / "assets").rglob("*"):
        if p.is_file() and p.suffix.lower() in GORSEL:
            y = p.relative_to(KOK).as_posix()
            if not any(y == k or (k.endswith("/**") and y.startswith(k[:-2])) for k in kaliplar):
                disarida.append(y)
    assert not disarida, f"NOTICE kapsamı dışında görsel: {disarida}"


# Kademe değil, dış ürün adı (Anthropic aboneliği) — görünür metinde kalabilir.
KADEME_ISTISNA = ("Claude Pro",)


def test_kademe_kalmadi():
    bulunan = []
    for p in (KOK / "frontend").rglob("*"):
        if not p.is_file() or p.suffix not in (".js", ".html") or "vendor" in p.parts:
            continue
        for i, satir in enumerate(p.read_text(errors="ignore").splitlines(), 1):
            s = satir.strip()
            if s.startswith(("//", "*", "/*", "<!--")):
                continue
            temiz = satir
            for ist in KADEME_ISTISNA:
                temiz = temiz.replace(ist, "")
            if "/api/license" in temiz or re.search(r"['\">][^'\"<]*\b(Lite|Pro|Ultra)\b", temiz):
                bulunan.append(f"{p.relative_to(KOK)}:{i}")
    assert not bulunan, f"kademe izi: {bulunan[:10]}"


# ── Arka uç satış dili (BL-51 3a, 2026-11-04) ──────────────────────────────────
# Açık kaynakta satılan kademe, "müşteri" yok. Üç kural, yalnız backend/app/**.py:
#   1) "müşteri" HİÇBİR yerde (kod, dizgi, yorum) — 11-04: 134 → 0.
#   2) Kullanıcıya görünen dizgide (docstring olmayan STRING) Lite/Pro/Ultra/kademe 0.
#      İstisnalar aşağıda, her biri gerekçeli.
#   3) Yorum + docstring'deki kademe dili TAVANLI: yeni yazılamaz, yalnız azalabilir.
#      Kalan tarihçe anlatısı (eski Free/Pro/Ultra kapılarının neden kurulduğu); temizlendikçe
#      tavanı düşür. 11-04 ölçümü: 147 eşleşme (galeri küçük resim "kademeleri" dahil).
SATIS_MUSTERI = re.compile("müş" + "teri", re.I)
SATIS_KADEME = re.compile(r"kademe|\b(?:lite|pro|ultra)\b", re.I)
SATIS_DIZGI_ISTISNA = (
    re.compile(r"Claude Pro"),                         # dış ürün (Anthropic aboneliği)
    re.compile(r"[\w.]+-pro\b"),                       # model kimliği: gemini-2.5-pro
    re.compile(r"[\w.]+-lite\b"),                      # model kimliği: gemini-3.5-flash-lite (küçük harf; "Lite plan" yakalanır)
    re.compile(r"^[\"'][a-z0-9_-]+(?:\.[a-z0-9_-]+)+[\"']$"),  # mesaj anahtarı: "kademe.plan-pro"
    re.compile(r"\{kademe\}"),                         # biçim alanı adı (lisans.* mesajları)
    re.compile(r"\(?\blite\b\)? (?:hafıza|memory)", re.I), # hafıza kipi adı (kısa dönem), satış değil
)
SATIS_YORUM_TAVAN = 147


_FSTRING_ORTA = getattr(__import__("tokenize"), "FSTRING_MIDDLE", -1)   # 3.12+: f-string gövdesi STRING değil


def _satis_tara():
    import io
    import tokenize
    musteri, dizgi, yorum = [], [], 0
    for p in sorted((KOK / "backend" / "app").rglob("*.py")):
        try:
            toks = list(tokenize.generate_tokens(io.StringIO(p.read_text(encoding="utf-8")).readline))
        except (OSError, SyntaxError, tokenize.TokenError):
            continue
        ad = p.relative_to(KOK)
        derinlik, deyim_basi = 0, True          # docstring = parantez dışında deyimin kendisi olan dizgi
        for t in toks:
            belge = t.type == tokenize.STRING and derinlik == 0 and deyim_basi
            if t.type == tokenize.OP:
                derinlik += (t.string in "([{") - (t.string in ")]}")
            if t.type in (tokenize.NEWLINE, tokenize.INDENT, tokenize.DEDENT):
                deyim_basi = True
            elif t.type not in (tokenize.NL, tokenize.COMMENT) and not belge:
                deyim_basi = False
            if SATIS_MUSTERI.search(t.string):
                musteri.append(f"{ad}:{t.start[0]}")
            if t.type not in (tokenize.COMMENT, tokenize.STRING, _FSTRING_ORTA) or not SATIS_KADEME.search(t.string):
                continue
            if t.type == tokenize.COMMENT or belge:
                yorum += len(SATIS_KADEME.findall(t.string))
                continue
            temiz = t.string
            for ist in SATIS_DIZGI_ISTISNA:
                temiz = ist.sub("", temiz)
            if SATIS_KADEME.search(temiz):
                dizgi.append(f"{ad}:{t.start[0]}: {t.string[:60]}")
    return musteri, dizgi, yorum


def test_backend_satis_dili_yok():
    musteri, dizgi, yorum = _satis_tara()
    assert not musteri, f"backend'de 'müşteri' ({len(musteri)}): {musteri[:10]}"
    assert not dizgi, f"görünür dizgide kademe dili ({len(dizgi)}): {dizgi[:10]}"
    assert yorum <= SATIS_YORUM_TAVAN, (
        f"yorum/docstring'de kademe dili {yorum} > tavan {SATIS_YORUM_TAVAN} — yeni yazma")


# Karar (2026-10-17): açık kaynak sürüme girmeyecek bileşenler.
YASAK = re.compile(
    # Önek eşleşmesi: XTTS_GPU / RVC_MODEL gibi alt çizgili adlar da yakalansın
    # (\bxtts\b alt çizgide kelime sınırı görmez — 10-17 mutasyonda kaçtı).
    r"\b(?:xtts|rvc|coqui)\w*|\b(run_shell|execute_command|install_package|kill_process|"
    r"type_text|mouse_click|mouse_move|mouse_drag|mouse_scroll|press_keys|control_window|"
    r"list_monitors|get_active_window|screen_target|DEV_TOOLS(_ENABLED)?|pty|xterm|"
    r"sce|nmap|dosya_terminal|file_manager|kitty_commands|jobs_api|jobs_tools|"
    r"jobs-view|background_jobs|cancel_job|list_jobs|yetki-komut)\b"
    # Cihaz ajanının uzaktan komut çalıştırması (10-19 son taramada bulundu).
    r"""|action\s*==\s*["']exec["']""", re.I)
YASAK_KOK = ("backend/app", "frontend", "electron", "remote_agent", "backend/requirements-product.txt")
YASAK_UZANTI = {".py", ".js", ".mjs", ".html", ".css", ".json", ".yml", ".txt"}


def test_girmeyecekler_yok():
    bulunan = []
    for kok in YASAK_KOK:
        yol = KOK / kok
        dosyalar_ = [yol] if yol.is_file() else (yol.rglob("*") if yol.exists() else [])
        for p in dosyalar_:
            parcalar = p.relative_to(KOK).parts
            if (not p.is_file() or p.suffix not in YASAK_UZANTI or ATLA.intersection(parcalar)
                    or "vendor" in parcalar or p.name.endswith("-lock.json")):
                continue
            for i, satir in enumerate(p.read_text(errors="ignore").splitlines(), 1):
                m = YASAK.search(satir)
                if m:
                    bulunan.append(f"{p.relative_to(KOK)}:{i}:{m.group(0)}")
    assert not bulunan, f"{len(bulunan)} iz: {bulunan[:12]}"



# PowerShell -Command / osascript -e dizgisine f-string ile veri gömmek = komut enjeksiyonu
# (ajan bildirimi exec kaldırılmasını böyle dolanıyordu). Çağrı birkaç satıra
# yayılabildiği için 4 satırlık pencerede aranır.
KABUK_FSTRING = re.compile(r"""["'](?:osascript|powershell(?:\.exe)?)["'](?:[^\n]*\n){0,3}?[^\n]*\bf['"][^\n]*\{""", re.I)


# 14 · Dosya gezgini: YALNIZ salt okunur + terminalsiz. Kapı 7'nin "dosya yöneticisi" yasağı
# bu gezgin için daraltıldı; daraltma AD LİSTESİDİR (geniş "dosya" muafiyeti yok): aşağıdaki
# beş yol dışında adında dosya/file-manager geçen hiçbir kaynak kabul edilmez. pty/xterm/terminal/
# SCE/nmap yasağı (YASAK, kapı 7) bu dosyalarda da aynen geçerlidir.
DOSYA_API = "backend/app/api/dosya_api.py"
DOSYA_EKRAN = ("frontend/dosya.html", "frontend/js/dosya.js", "frontend/css/dosya.css")
DOSYA_ISTISNA = {DOSYA_API, "backend/tests/test_dosya.py", *DOSYA_EKRAN}
# 14b · Güvenli dosya işlemleri (2026-11-12, kullanıcı kararıyla bu sürüme girdi): çöpe at · taşı ·
# geri al, VARSAYILAN KAPALI. Yazma dosya gezgininde (DOSYA_API) DEĞİL, aşağıda ADIYLA listelenen ayrı
# dosyalarda yaşar; gezgin salt okunur kalır (14 aynen geçerli). Bu dosyalar için ek kapı
# (test_guvenli_dosya_kalici_silmez_ve_kapali): kalıcı silme/süreç çağrısı yok (yalnız taşıma),
# yazan her uç önce `_kapi()`yı sorar, ayar yalnız gerçek True ile açılır.
GUVENLI_DOSYA_SUNUCU = ("backend/app/services/guvenli_dosya.py", "backend/app/api/guvenli_dosya_api.py")
GUVENLI_DOSYA = {*GUVENLI_DOSYA_SUNUCU, "frontend/js/dosya-guvenli.js", "frontend/css/dosya-guvenli.css",
                 "backend/tests/test_guvenli_dosya.py", "frontend/tests/test_dosya_gonder_guvenli.py",
                 "frontend/tests/dosya_sinav_sunucu.py"}
DOSYA_ISTISNA |= GUVENLI_DOSYA
GUVENLI_KALICI_SIL = re.compile(r"\.(?:unlink|rmdir)\(|\b(?:shutil|os)\.(?:rmtree|remove|removedirs|unlink|rmdir)\b"
                                r"|\b(?:subprocess|pty)\b|\bos\.system\b")
GUVENLI_YAZAN_UC = re.compile(r'@router\.(post|put|patch|delete)\(\s*"([^"]+)"\)\s*\n(?:async\s+)?def\s+\w+\([^)]*\)[^:]*:\s*\n'
                              r'((?:[ \t]+.*\n){1,2})')
DOSYA_ADI = re.compile(r"dosya|file[_-]?manager|filemanager", re.I)
DOSYA_ADI_KOK = ("backend/app", "frontend", "electron", "remote_agent")
# Sunucu: yazma/silme/taşıma çağrıları, yazan HTTP yöntemi, WebSocket, süreç/pty.
DOSYA_YAZMA = re.compile(
    r"\.(?:write_text|write_bytes|unlink|rename|rmdir|mkdir|touch|symlink_to|hardlink_to|chmod|chown|truncate)\("
    r"|\b(?:shutil|os)\.(?:move|copy\w*|rmtree|remove|removedirs|rename|renames|replace|makedirs|mkdir|unlink|rmdir"
    r"|chmod|chown|truncate|symlink|link|write)\b"
    r"|\bopen\([^)]*,\s*['\"][^'\"]*[wax+]"
    r"|\b(?:WebSocket|websocket|subprocess|pty|xterm|terminal|guvenli_dosya)\b"
    r"|\.(?:api_route|route|add_api_route|add_api_websocket_route|websocket)\(")
DOSYA_ROTA = re.compile(r"@\w+\.(post|put|patch|delete)\(\s*['\"]([^'\"]*)['\"]", re.I)
DOSYA_POST_IZIN = {("post", "/api/dosya/git")}     # yolu çözer, diske yazmaz
# Ekran: terminal/pty izi, yazan yöntemler, sürükle-taşı, WebSocket.
DOSYA_EKRAN_YASAK = re.compile(r"xterm|\bpty\b|terminal|cekmece|/duzen|X-Duzenleme|draggable|WebSocket", re.I)
DOSYA_EKRAN_YONTEM = re.compile(r"method\s*:\s*['\"](POST|PUT|PATCH|DELETE)['\"]", re.I)


def test_dosya_gezgini_salt_okunur():
    bulunan = []
    for kok in DOSYA_ADI_KOK:
        yol = KOK / kok
        for p in (yol.rglob("*") if yol.exists() else []):
            g = p.relative_to(KOK).as_posix()
            if (not p.is_file() or ATLA.intersection(p.relative_to(KOK).parts) or "vendor" in p.parts
                    or g in KENDI):
                continue
            if DOSYA_ADI.search(p.name) and g not in DOSYA_ISTISNA:
                bulunan.append(f"{g}: istisna listesinde olmayan dosya-gezgini adı")
    api = KOK / DOSYA_API
    if api.exists():
        metin = re.sub(r'(?s)""".*?"""', "", api.read_text(errors="ignore"))
        for i, satir in enumerate(metin.splitlines(), 1):
            kod = satir.split("#", 1)[0]
            if not kod.strip():
                continue
            if DOSYA_YAZMA.search(kod):
                bulunan.append(f"{DOSYA_API}:{i}: yazma/terminal izi: {DOSYA_YAZMA.search(kod).group(0)}")
            m = DOSYA_ROTA.search(kod)
            if m and (m.group(1).lower(), m.group(2)) not in DOSYA_POST_IZIN:
                bulunan.append(f"{DOSYA_API}:{i}: yazma ucu {m.group(1).upper()} {m.group(2)}")
    for g in DOSYA_EKRAN:
        p = KOK / g
        if not p.exists():
            continue
        metin = p.read_text(errors="ignore")
        for i, satir in enumerate(metin.splitlines(), 1):
            m = DOSYA_EKRAN_YASAK.search(satir)
            if m:
                bulunan.append(f"{g}:{i}: terminal/yazma izi: {m.group(0)}")
        for m in DOSYA_EKRAN_YONTEM.finditer(metin):
            onceki = metin[max(0, m.start() - 160):m.start()]
            if not (m.group(1).upper() == "POST" and "/api/dosya/git" in onceki):
                bulunan.append(f"{g}: yazan istek {m.group(1).upper()}")
    assert not bulunan, f"{len(bulunan)} iz: {bulunan[:10]}"


def test_guvenli_dosya_kalici_silmez_ve_kapali():
    bulunan = []
    for g in GUVENLI_DOSYA_SUNUCU:
        p = KOK / g
        if not p.exists():
            continue
        metin = re.sub(r'(?s)""".*?"""', "", p.read_text(errors="ignore"))
        for i, satir in enumerate(metin.splitlines(), 1):
            m = GUVENLI_KALICI_SIL.search(satir.split("#", 1)[0])
            if m:
                bulunan.append(f"{g}:{i}: kalıcı silme/süreç çağrısı: {m.group(0)}")
    api = KOK / GUVENLI_DOSYA_SUNUCU[1]
    if api.exists():
        for m in GUVENLI_YAZAN_UC.finditer(api.read_text(errors="ignore")):
            if m.group(2) != "/ayar" and "_kapi()" not in m.group(3):
                bulunan.append(f"{GUVENLI_DOSYA_SUNUCU[1]}: {m.group(1).upper()} {m.group(2)} kapıyı (_kapi) sormuyor")
    srv = KOK / GUVENLI_DOSYA_SUNUCU[0]
    if srv.exists() and '.get("acik") is True' not in srv.read_text(errors="ignore"):
        bulunan.append(f"{GUVENLI_DOSYA_SUNUCU[0]}: ayar yalnız gerçek True ile açılmalı (varsayılan kapalı)")
    assert not bulunan, f"{len(bulunan)} iz: {bulunan[:10]}"


def test_kabuk_dizgisine_fstring_yok():
    bulunan = []
    for kok in ("backend/app", "remote_agent", "electron", "scripts"):
        for p in (KOK / kok).rglob("*.py"):
            if ATLA.intersection(p.relative_to(KOK).parts):
                continue
            metin = p.read_text(errors="ignore")
            for m in KABUK_FSTRING.finditer(metin):
                bulunan.append(f"{p.relative_to(KOK)}:{metin.count(chr(10), 0, m.start()) + 1}")
    assert not bulunan, f"kabuk komutuna f-string: {bulunan}"

BELGELER = {
    "README.md": ("Run from source", "all rights reserved", "non-commercial", "BYOK"),
    "CONTRIBUTING.md": ("Pull requests", "Never commit secrets"),
    "CODE_OF_CONDUCT.md": ("Contributor Covenant",),
    "THIRD_PARTY_LICENSES.md": ("Open Font License", "buffalo_l", "non-commercial"),
    "LICENSE": ("MIT License",),
    "NOTICE": ("All Rights Reserved",),
    "SECURITY.md": ("Report a vulnerability",),
    ".github/ISSUE_TEMPLATE/bug_report.yml": ("Steps to reproduce",),
    ".github/ISSUE_TEMPLATE/feature_request.yml": ("problem",),
    ".github/workflows/temizlik.yml": ("gitleaks git", "test_temizlik.py"),
}


def test_acik_kaynak_belgeleri():
    eksik = []
    for ad, zorunlu in BELGELER.items():
        p = KOK / ad
        if not p.is_file():
            eksik.append(f"{ad}: yok")
            continue
        metin = p.read_text(errors="ignore").lower()
        eksik += [f"{ad}: '{z}' yok" for z in zorunlu if z.lower() not in metin]
    assert not eksik, f"belge eksiği: {eksik}"


# İç iz: vault görev/kart numaraları, geliştiricinin adı, kişisel alan adı, eski depo adı.
# Desenler parçalı yazıldı ki bu dosya kendini yakalamasın. Eski depo adı İSTİSNASIZ yasak:
# model paketleri bu deponun kendi sürümünden iner (electron/models-manifest.json); eski
# depoya giden tek bir indirme adresi o depo gizlenince CI'ı ve ilk kurulumu kırar.
IC_IZ = re.compile(r"\bG-[a-z0-9]{6}\b|\bBL-[0-9]+|" + r"(?i:ih" + r"san)(?!deniz)|" + r"(?i:yuki" + r"[-_]ai)(?![a-z0-9])")
IC_IZ_ISTISNA = {"backend/tests/test_sohbet_canli.py",   # "yasak kelime" listesini taşır
                 "scripts/test_temizlik.py"}


def test_ic_referans_yok():
    bulunan = []
    for p in dosyalar():
        ad = str(p.relative_to(KOK))
        if ad in IC_IZ_ISTISNA or p.suffix in {".png", ".jpg", ".webp", ".glb", ".woff2", ".onnx"}:
            continue
        try:
            ham = p.read_bytes()
            if b"\0" in ham[:8192]:      # ikili dosya
                continue
            for i, satir in enumerate(ham.decode(errors="ignore").splitlines(), 1):
                if IC_IZ.search(satir):
                    bulunan.append(f"{ad}:{i}")
        except OSError:
            pass
    assert not bulunan, f"iç iz ({len(bulunan)}): {bulunan[:10]}"


# 15 · İç rapor/karar yolu: kod/yorum/belge, geliştiricinin kendi çalışma alanındaki rapor
# ve karar dosyalarına işaret etmesin (açık kaynakta o dosyalar yok; okura anlamsız, iç iz).
# Kural TAVANSIZ: 11-10'da 39 yol genel ifadeye çevrildi (tarih + konu kalır, yol gider) → 0.
# AYRIM: ürünün wiki aracı (services/tools/wiki.py) kullanıcının KENDİ wiki'sinde
# WIKI/sources/…, WIKI/index.md, WIKI/log.md, WIKI/hot.md yollarıyla çalışır — bunlar meşru,
# desende yok. Yalnız ürünün wiki aracının hiç kullanmadığı alt klasörler/defterler yakalanır.
IC_YOL = re.compile(
    r"\b" + "rep" + r"orts/20\d{2}-"                                     # reports/2026-…
    + r"|\bWIKI/(?:" + "deci" + r"sions|syntheses|daily|concepts|entities|bilgi-arsivi"
    + r"|archive|gelen|memory-mirror|tools)/"                              # vault alt klasörleri
    + r"|\bWIKI/(?:backlog|ledger|tasks|dashboard|health|sistem-haritasi|REHBER)\.md"
    + r"|(?<![\w/])" + "deci" + r"sions/20\d{2}-\d{2}-\d{2}-")            # WIKI/'siz karar yolu


def test_ic_yol_yok():
    bulunan = []
    for p in dosyalar():
        ad = p.relative_to(KOK).as_posix()
        if ad in KENDI or p.suffix in {".png", ".jpg", ".jpeg", ".webp", ".glb", ".woff2", ".onnx", ".vrm"}:
            continue
        try:
            ham = p.read_bytes()
            if b"\0" in ham[:8192]:      # ikili dosya
                continue
            for i, satir in enumerate(ham.decode(errors="ignore").splitlines(), 1):
                m = IC_YOL.search(satir)
                if m:
                    bulunan.append(f"{ad}:{i}:{m.group(0)}")
        except OSError:
            pass
    assert not bulunan, f"iç rapor/karar yolu ({len(bulunan)}): {bulunan[:10]}"


# ── FAZ 1 (G-cst2bp): kişisel + eski ürün birleşimi için kapı sertleştirme ──
# Birleşimde kişiselden (AliceAi) çok daha fazla desen gelecek. Aşağıdaki iki kapı
# o birleşimi korur; ayrıca her desen sınıfı mutasyonla (zehirli fixture) sınanır.
# Desen metinleri parçalı yazıldı ki bu dosya kendini yakalamasın.
KENDI = {"scripts/test_temizlik.py"}

# 11 · Marka kalıntısı: eski ürün/kişisel adın açık kaynak kopyada izi.
#  - ~/.alice_*  kişisel cihaz dosyaları (remote_agent)
#  - ALICE_*     ürün env öneki (run.py, testler, .env.example)
#  - "Alice AI"  kullanıcıya görünen ürün adı (manifest, html)
MARKA = re.compile(
    r"\." + "alice" + "_"                            # ~/.alice_device_token / _id
    + "|" + r"\b" + "ALICE" + r"_[A-Z0-9]"           # ALICE_DATA_DIR / ALICE_RELOAD …
    + "|" + "[Aa]lice" + r"[ \-–—]" + "[Aa][Ii]" + r"\b"   # "Alice AI" / "Alice-AI"
)
MARKA_KOK = ("backend", "remote_agent", "electron", "frontend", ".env.example")
# Kişisel profili (alice-ai) BİLEREK referanslayan ayrışma/güvenlik kapıları:
# bu dosyalar "alice-ai"yi yasak-değer ya da engellenecek-hedef olarak NAMELER;
# yeniden adlandırmak korumayı bozar (profil çakışması, token sızması). Bu yüzden
# istisna — marka kapısının kendini dışlaması (KENDI) ile aynı ilke. (G-csvip5)
MARKA_ISTISNA = {
    "scripts/test_profil_adi.py",               # profil adı kapısı: name != alice-ai
    "backend/tests/test_baslat_durdur_izolasyonu.py",  # yuki, kişisel alice-ai'yi öldürmesin
    "backend/tests/test_dis_icerik_kapisi.py",  # .config/alice-ai/* sızma hedefi (engellenir)
    "backend/tests/test_mod_kapisi.py",
    "backend/tests/test_pg_portu_izole.py",
    "backend/tests/test_saglik_kartlari.py",
    "backend/tests/test_yayin_kapisi.py",       # yayın kapısı fixture'ı: name=alice-ai reddi
    "electron/onyukleme.js",                    # yorum: kişisel alice-ai ile çakışmaz
}


def test_marka_kalintisi_yok():
    """🔴 main'de bilerek KIRMIZI döner — 3 bilinen kalıntı FAZ 2'de düzeltilecek
    (device_token yolu · ALICE_ env · manifest adı). Kapının yakaladığını kanıtlar."""
    bulunan = []
    for kok in MARKA_KOK:
        yol = KOK / kok
        kaynak = [yol] if yol.is_file() else (yol.rglob("*") if yol.exists() else [])
        for p in kaynak:
            parcalar = p.relative_to(KOK).parts
            if (not p.is_file() or ATLA.intersection(parcalar) or "vendor" in parcalar
                    or str(p.relative_to(KOK)) in KENDI
                    or str(p.relative_to(KOK)) in MARKA_ISTISNA
                    or p.suffix in {".png", ".jpg", ".jpeg", ".webp", ".woff2", ".onnx", ".vrm", ".glb"}):
                continue
            try:
                for i, satir in enumerate(p.read_text(errors="ignore").splitlines(), 1):
                    m = MARKA.search(satir)
                    if m:
                        bulunan.append(f"{p.relative_to(KOK)}:{i}:{m.group(0)}")
            except OSError:
                pass
    assert not bulunan, f"marka kalıntısı ({len(bulunan)}): {bulunan[:15]}"


# 12 · Ağ/entegrasyon izi: kişisele özgü ağ ve iç servis bağları.
#  - Tailscale host IP (100.64–127.x.x) — CIDR aralığı (…/N) MEŞRU, hariç tutulur
#  - iç servis portları :8790 (kripto paneli) · :8794 (ajan komuta)
#  - Dia / hermes / KAGE kişisel entegrasyonları
TAILSCALE = re.compile(r"\b100\.(?:6[4-9]|[7-9]\d|1[01]\d|12[0-7])\.\d{1,3}\.\d{1,3}(?!/)")
IC_PORT = re.compile(r":879[04]\b")
IC_SERVIS = re.compile(r"\b(?:" + "dia" + "|" + "hermes" + "|" + "kage" + r")\b", re.I)
AG_KOK = ("backend/app", "remote_agent", "electron", "frontend")


def test_ag_izi_yok():
    """main'de temiz geçer (bu entegrasyonlar yuki-oss türetilirken çıkarılmıştı);
    mutasyon testi gerçek bir sızıntıyı yakalayacağını kanıtlar. Test fixture IP'leri
    (backend/tests) kapsam dışı — gerçek değil."""
    bulunan = []
    for kok in AG_KOK:
        yol = KOK / kok
        if not yol.exists():
            continue
        for p in yol.rglob("*"):
            parcalar = p.relative_to(KOK).parts
            if (not p.is_file() or ATLA.intersection(parcalar) or "vendor" in parcalar
                    or str(p.relative_to(KOK)) in KENDI or p.suffix not in YASAK_UZANTI):
                continue
            testte = "tests" in parcalar or p.name.startswith("test_")
            try:
                for i, satir in enumerate(p.read_text(errors="ignore").splitlines(), 1):
                    m = (None if testte else TAILSCALE.search(satir)) or IC_PORT.search(satir) or IC_SERVIS.search(satir)
                    if m:
                        bulunan.append(f"{p.relative_to(KOK)}:{i}:{m.group(0)}")
            except OSError:
                pass
    assert not bulunan, f"ağ/entegrasyon izi ({len(bulunan)}): {bulunan[:15]}"


# 13 · Varlık lisansı — dağıtma hakkımız olmayan model/varlık depoya ve indirme listesine girmesin.
#  - .vrm: önceki yuki3d.vrm yeniden dağıtımı yasaklayan bir örnek avatar türeviydi (karar
#    2026-10-27 #3). Kendi modelimiz gelince bu kural VRM meta lisansına bakan bir kurala dönüşür.
#  - manifest `models`: buradaki her girdi kullanıcıya bizim sunucumuzdan indirilir. InsightFace
#    buffalo_l/antelope ağırlıkları "ticari olmayan araştırma" lisanslı (karar #2) → `externalModels`.
TICARI_OLMAYAN = re.compile(r"buffalo|antelope|non-?commercial|cc[ -]by-nc", re.I)
MANIFEST_ALANLARI = ("asset", "url", "license", "name", "feature")


def _izlenen_dosyalar():
    """Git deposuysa izlenen dosyalar (kullanıcının yerel .vrm'i sayılmaz), değilse dosya ağacı
    (git archive ile açılmış temiz kopya, mutasyon fixture'ı)."""
    if (KOK / ".git").exists():
        r = subprocess.run(["git", "ls-files", "-z"], cwd=KOK, capture_output=True, text=True,
                           env={k: v for k, v in __import__("os").environ.items()
                                if k not in ("GIT_DIR", "GIT_INDEX_FILE", "GIT_WORK_TREE")})
        if r.returncode == 0:
            return [y for y in r.stdout.split("\0") if y]
    return [p.relative_to(KOK).as_posix() for p in dosyalar()]


def test_varlik_lisans():
    bulunan = [f"{y}: VRM depoda" for y in _izlenen_dosyalar() if y.lower().endswith(".vrm")]
    mf = KOK / "electron" / "models-manifest.json"
    if mf.is_file():
        import json
        try:
            veri = json.loads(mf.read_text())
        except ValueError as e:
            raise AssertionError(f"models-manifest.json okunamadı: {e}")
        for mid, m in (veri.get("models") or {}).items():
            parcalar = [mid] + [str(m.get(a, "")) for a in MANIFEST_ALANLARI]
            for alt in (m.get("assets") or {}).values():          # platforma özel asset'ler
                parcalar += [str(alt.get(a, "")) for a in ("asset", "url")]
            esl = TICARI_OLMAYAN.search(" ".join(parcalar))
            if esl:
                bulunan.append(f"models-manifest.json models.{mid}: {esl.group(0)}")
    assert not bulunan, f"dağıtma hakkı olmayan varlık ({len(bulunan)}): {bulunan[:10]}"


# ── Mutasyon: her desen sınıfı için zehirli (uydurma ama gerçekçi) fixture üret,
# kapıyı o fixture'a karşı koştur, KIRMIZI döndüğünü gör. Fixture'lar tmp'de kalır,
# depoya yazılmaz; literal'ler parçalı ki bu dosya kendi kapılarını tetiklemesin. ──
def _mutasyon(fn, hazirla):
    """hazirla(tmp): tmp ağacına zehir koy. fn() AssertionError atmalı (kapı yakaladı)."""
    global KOK
    eski = KOK
    with tempfile.TemporaryDirectory() as d:
        KOK = Path(d)
        try:
            hazirla(KOK)
            fn()
        except AssertionError:
            return True          # kapı zehri yakaladı ✓
        finally:
            KOK = eski
    raise AssertionError(f"MUTASYON KAÇTI: {fn.__name__} zehirli fixture'ı yakalamadı")


def _yaz(kok, yol, metin):
    p = kok / yol
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(metin)


def test_mut_sizinti():
    # e-posta dalı (SIZINTI'nin ikinci yarısı); kişisel ev yolu literal'i yazmadan.
    _mutasyon(test_sizinti_yok, lambda k: _yaz(k, "backend/x.py", "SAHIP = 'biri" + "@gmail" + ".com'"))

def test_mut_kisisel_dosya():
    _mutasyon(test_kisisel_dosya_yok, lambda k: _yaz(k, "memory.db", "x"))

def test_mut_chatgpt_token():
    _mutasyon(test_kisisel_dosya_yok, lambda k: _yaz(k, "chatgpt_plan/chatgpt_token.json", "{}"))


def test_mut_chatgpt_kimlik():
    _mutasyon(test_chatgpt_kimlik_izi_yok,
              lambda k: _yaz(k, "backend/app/x.py", 'H = {"originator": "codex" + "_cli_rs"}'))


def test_mut_marka_yol():
    _mutasyon(test_marka_kalintisi_yok,
              lambda k: _yaz(k, "remote_agent/agent.py", "T = Path.home() / '." + "alice" + "_device_token'"))

def test_mut_marka_env():
    _mutasyon(test_marka_kalintisi_yok,
              lambda k: _yaz(k, "backend/run.py", "os.getenv('" + "ALICE" + "_DATA_DIR')"))

def test_mut_marka_ad():
    _mutasyon(test_marka_kalintisi_yok,
              lambda k: _yaz(k, "frontend/manifest.json", '{"name": "Yuki — ' + "Alice" + ' AI"}'))

def test_mut_tailscale():
    _mutasyon(test_ag_izi_yok,
              lambda k: _yaz(k, "backend/app/sunucu.py", "UZAK = '" + "100.101" + ".42.3'"))

def test_mut_ic_port():
    _mutasyon(test_ag_izi_yok,
              lambda k: _yaz(k, "backend/app/vekil.py", "URL = 'http://localhost" + ":8794" + "/x'"))

def test_mut_ic_servis():
    _mutasyon(test_ag_izi_yok,
              lambda k: _yaz(k, "backend/app/kopru.py", "import " + "hermes" + " as h"))

def test_mut_girmeyecekler():
    _mutasyon(test_girmeyecekler_yok,
              lambda k: _yaz(k, "backend/app/arac.py", "def " + "run_shell" + "(): pass"))

def test_mut_ic_referans():
    _mutasyon(test_ic_referans_yok,
              lambda k: _yaz(k, "backend/x.py", "# görev " + "G-" + "abc123 tamam"))


_IC_YOL_ZEHIR = {
    "karar yolu yorumda": ("backend/app/x.py", "# Karar: WIKI/" + "deci" + "sions/2026-10-17-ornek.md\n"),
    "rapor yolu css": ("frontend/css/x.css", "/* Taslak: " + "rep" + "orts/2026-09-26-ornek/t.html */\n"),
    "rapor yolu belge": ("docs/x.md", "Ölçüm: `" + "rep" + "orts/2026-10-25-ornek/RAPOR.md`\n"),
    "wikisiz karar": ("electron/x.js", "// bkz. " + "deci" + "sions/2026-08-09-ornek.md\n"),
    "vault defteri": ("backend/tests/test_x.py", "# WIKI/" + "ledger" + ".md satırı\n"),
}


def test_mut_ic_yol():
    for ad, (yol, zehir) in _IC_YOL_ZEHIR.items():
        try:
            _mutasyon(test_ic_yol_yok, lambda k, y=yol, z=zehir: _yaz(k, y, z))
        except AssertionError as e:
            raise AssertionError(f"{e} [{ad}]")


def test_mut_ic_yol_urun_wiki_gecer():
    """Ürünün wiki aracının yolları yanlış alarm vermez (kullanıcının kendi wiki'si)."""
    global KOK
    eski = KOK
    with tempfile.TemporaryDirectory() as d:
        KOK = Path(d)
        try:
            _yaz(KOK, "backend/app/services/tools/wiki.py",
                 'O = "WIKI/sources/projects/2026-04-25-ornek-sayfa.md"\n'
                 'P = {"WIKI/index.md", "WIKI/log.md", "WIKI/hot.md"}\n'
                 '# kullanıcı raporları: reports/ klasörü (tarihsiz)\n')
            test_ic_yol_yok()
        finally:
            KOK = eski


_SATIS_ZEHIR = {
    "yorumda musteri": "# " + "Müş" + "teriye gider\nX = 1\n",
    "gorunur mesaj": 'M = {"a.b": "Harita panosu ' + "Pro" + ' sürümün özelliğidir."}\n',
    "f-string": 'def f(ad):\n    return f"{ad} ' + "Ul" + 'tra gerekir"\n',
    "model istisnasi kademeyi yutmaz": 'M = {"a.b": "' + "Li" + 'te planda kapalı", "c": "x-' + "Li" + 'te"}\n',
    "parantezli coklu satir": 'M = {\n    "a.b": (\n        "Bu ekran "\n        "' + "Pro" + ' ile açılır."\n    ),\n}\n',
    "tavan asildi": "".join(f"# eski {'kade' + 'me'} {i}\n" for i in range(SATIS_YORUM_TAVAN + 1)),
}


def test_mut_satis_dili():
    for ad, zehir in _SATIS_ZEHIR.items():
        try:
            _mutasyon(test_backend_satis_dili_yok, lambda k, z=zehir: _yaz(k, "backend/app/x.py", z))
        except AssertionError as e:
            raise AssertionError(f"{e} [{ad}]")


def test_mut_satis_istisnalar_gecer():
    """İstisnalar yanlış alarm vermez: model kimliği, mesaj anahtarı, docstring tarihçesi, lite hafıza."""
    global KOK
    eski = KOK
    with tempfile.TemporaryDirectory() as d:
        KOK = Path(d)
        try:
            _yaz(KOK, "backend/app/x.py",
                 '"""Eski ' + "Pro" + ' kapısı burada dururdu."""\n'
                 'MODEL = "gemini-2.5-' + 'pro"\n'
                 'G = "google/gemini-3.5-flash-' + 'lite"\n'
                 'K = M("' + 'kade' + 'me.plan-pro")\n'
                 'N = "⚠ Claude ' + 'Pro' + '/Max aboneliği API değildir"\n'
                 'H = "kısa dönem (' + 'lite' + ') hafıza"\n')
            test_backend_satis_dili_yok()
        finally:
            KOK = eski


def test_mut_varlik_vrm():
    _mutasyon(test_varlik_lisans,
              lambda k: _yaz(k, "frontend/assets/characters/yeni.vrm", "glTF"))

def test_mut_varlik_manifest():
    # Ölü buffalo girdisinin geri dönmesi (build-face-model-package.sh manifesti yeniden yazabilir).
    _mutasyon(test_varlik_lisans,
              lambda k: _yaz(k, "electron/models-manifest.json",
                             '{"models": {"face-model": {"asset": "' + "buf" + 'falo-l.tar.gz"}}}'))

def test_mut_varlik_platform_asset():
    _mutasyon(test_varlik_lisans,
              lambda k: _yaz(k, "electron/models-manifest.json",
                             '{"models": {"yuz": {"assets": {"linux-x64": {"url": "https://x/' + "ante" + 'lopev2.tgz"}}}}}'))


def test_mut_dosya_yazma_ucu():
    """(a) dosya API'sine yazan HTTP ucu + silme çağrısı."""
    _mutasyon(test_dosya_gezgini_salt_okunur,
              lambda k: _yaz(k, DOSYA_API, "@router." + "delete" + '("/api/dosya/sil/{kid}")\n'
                             "async def sil(kid): _yol(kid)." + "unlink()\n"))

def test_mut_dosya_yazma_post():
    _mutasyon(test_dosya_gezgini_salt_okunur,
              lambda k: _yaz(k, DOSYA_API, "@router." + "post" + '("/api/dosya/duzen/yaz")\n'
                             "async def yaz(): pass\n"))

def test_mut_dosya_yazma_cagri():
    _mutasyon(test_dosya_gezgini_salt_okunur,
              lambda k: _yaz(k, DOSYA_API, "import shutil\nshutil." + "move" + "(a, b)\n"))

def test_mut_dosya_ekran_terminal():
    """(b) dosya ekranına pty/xterm/terminal izi."""
    _mutasyon(test_dosya_gezgini_salt_okunur,
              lambda k: _yaz(k, "frontend/dosya.html", '<script src="/ui/vendor/' + "xterm" + '/xterm.js"></script>\n'
                             '<section id="dy-' + "terminal" + '"></section>'))

def test_mut_dosya_ekran_yazma_istegi():
    _mutasyon(test_dosya_gezgini_salt_okunur,
              lambda k: _yaz(k, "frontend/js/dosya.js", "json('/api/dosya/sil', { method: 'DELETE' });"))

def test_mut_dosya_genis_istisna_yok():
    """Adı dosya geçen, listede OLMAYAN dosya kapıdan geçemez (geniş 'dosya' muafiyeti yok)."""
    _mutasyon(test_dosya_gezgini_salt_okunur,
              lambda k: _yaz(k, "backend/app/api/dosya_yonetici.py", "x = 1\n"))

def test_mut_dosya_terminal_pty_global():
    """Kapı 7 aynen duruyor: dosya ekranında bile pty yasağı genel kapıdan da düşer."""
    _mutasyon(test_girmeyecekler_yok,
              lambda k: _yaz(k, "frontend/js/dosya.js", "const t = new " + "pty" + "();"))


_GUVENLI_API_TEMIZ = ('@router.post("/hazirla")\ndef hazirla(body: H):\n    _kapi()\n    return 1\n'
                      '@router.put("/ayar")\nasync def ayar(body: A):\n    return 1\n')
_GUVENLI_SRV_TEMIZ = 'def ayar_acik():\n    return json.loads(x).get("acik") is True\nshutil.move(a, b)\n'

def test_mut_guvenli_kalici_silme():
    """14b: güvenli dosya modülüne kalıcı silme girerse kapı düşer."""
    _mutasyon(test_guvenli_dosya_kalici_silmez_ve_kapali,
              lambda k: _yaz(k, GUVENLI_DOSYA_SUNUCU[0], _GUVENLI_SRV_TEMIZ + "shutil." + "rmtree(cop)\n"))

def test_mut_guvenli_kapisiz_uc():
    _mutasyon(test_guvenli_dosya_kalici_silmez_ve_kapali,
              lambda k: (_yaz(k, GUVENLI_DOSYA_SUNUCU[0], _GUVENLI_SRV_TEMIZ),
                         _yaz(k, GUVENLI_DOSYA_SUNUCU[1], _GUVENLI_API_TEMIZ +
                              '@router.post("/uygula")\ndef uygula(body: U):\n    return gd.uygula(body.onay)\n')))

def test_mut_guvenli_varsayilan_acik():
    _mutasyon(test_guvenli_dosya_kalici_silmez_ve_kapali,
              lambda k: _yaz(k, GUVENLI_DOSYA_SUNUCU[0], 'def ayar_acik():\n    return json.loads(x).get("acik", True)\n'))

def test_mut_guvenli_temiz_gecer():
    """Negatif yön: kurala uyan güvenli dosya modülü + gezgin dosyaları yeşil kalır."""
    global KOK
    eski = KOK
    with tempfile.TemporaryDirectory() as d:
        KOK = Path(d)
        try:
            _yaz(KOK, GUVENLI_DOSYA_SUNUCU[0], _GUVENLI_SRV_TEMIZ)
            _yaz(KOK, GUVENLI_DOSYA_SUNUCU[1], _GUVENLI_API_TEMIZ)
            _yaz(KOK, "frontend/js/dosya-guvenli.js", "x = 1;\n")
            test_guvenli_dosya_kalici_silmez_ve_kapali()
            test_dosya_gezgini_salt_okunur()
        finally:
            KOK = eski


def test_mut_temiz_gecer():
    """Negatif yön: zehir yoksa yeni kapılar YEŞİL (yanlış pozitif yok)."""
    global KOK
    eski = KOK
    with tempfile.TemporaryDirectory() as d:
        KOK = Path(d)
        try:
            _yaz(KOK, "backend/app/net.py", "CGNAT = '100.64.0.0/10'  # Tailscale aralığı meşru")
            _yaz(KOK, "backend/app/x.py", "PORT = 8791  # motor portu")
            # externalModels'taki buffalo notu meşru (dağıtmıyoruz, yönlendiriyoruz)
            _yaz(KOK, "electron/models-manifest.json",
                 '{"models": {"stt": {"asset": "whisper.tgz"}}, "externalModels": {"face-model": '
                 '{"license": "non-commercial", "name": "' + "buf" + 'falo_l"}}}')
            test_marka_kalintisi_yok()   # zehir yok → atmamalı
            test_ag_izi_yok()
            test_varlik_lisans()
            # salt okunur gezgin: yalnız GET + /git (diske yazmaz) → yeşil kalmalı
            _yaz(KOK, DOSYA_API, '"""salt okunur (terminal yok)"""\n@router.get("/api/dosya/liste/{kid}")\nasync def l(kid): return 1\n'
                 '@router.post("/api/dosya/git")\nasync def g(b): return 1\n')
            _yaz(KOK, "frontend/js/dosya.js", "json('/api/dosya/git', { method: 'POST' });")
            test_dosya_gezgini_salt_okunur()
        finally:
            KOK = eski



# 16 · Yapay zekâ commit kimliği: gözetimsiz koşu raporları ve kopyalanan commit metinleri
# aracın git kimliğini depoya taşıyabiliyor (gece raporu ölçüldü: kapı 18/0 geçmişti).
# Parçalı yazıldı: bu dosya kendini yakalamasın.
YZ_KIMLIK = re.compile(
    r"noreply@" + "anthropic" + r"\.com"
    + r"|Co-Authored-By:\s*" + "Cla" + "ude"
    + r"|Generated with \[?" + "Cla" + "ude Code",
    re.I)


def test_yz_kimligi_yok():
    bulunan = []
    for p in dosyalar():
        if p.suffix in GORSEL or p.suffix in {".onnx", ".woff2", ".glb"}:
            continue
        try:
            ham = p.read_bytes()
        except OSError:
            continue
        if b"\0" in ham[:8192]:
            continue
        for i, satir in enumerate(ham.decode(errors="ignore").splitlines(), 1):
            if YZ_KIMLIK.search(satir):
                bulunan.append(f"{p.relative_to(KOK)}:{i}")
    assert not bulunan, f"yapay zekâ commit kimliği ({len(bulunan)}): {bulunan[:10]}"


def test_mut_yz_kimligi():
    _mutasyon(test_yz_kimligi_yok,
              lambda k: _yaz(k, "docs/notlar.md", "Kimlik: Cla" + "ude <noreply@" + "anthropic.com>\n"))


def test_mut_yz_coauthor():
    _mutasyon(test_yz_kimligi_yok,
              lambda k: _yaz(k, "CHANGELOG.md", "x\n\nCo-Authored-By: Cla" + "ude Opus <x@y>\n"))


def test_mut_yz_saglayici_konsolu_gecer():
    """Anahtar alma bağlantısı (console.<sağlayıcı>.com) kimlik değildir; kapı bunu yakalamamalı."""
    global KOK
    eski, tmp = KOK, Path(tempfile.mkdtemp())
    try:
        KOK = tmp
        _yaz(tmp, ".env.example", "# https://console." + "anthropic" + ".com/settings/keys\n")
        test_yz_kimligi_yok()
    finally:
        KOK = eski
        shutil.rmtree(tmp, ignore_errors=True)


def test_mut_gece_raporu():
    _mutasyon(test_ic_dosya_yok, lambda k: _yaz(k, "GECE-RAPOR.md", "# rapor\n"))

GATE = [test_gitleaks, test_sizinti_yok, test_kisisel_dosya_yok, test_ic_dosya_yok,
        test_lisans_gorseller_kapsamda, test_kademe_kalmadi,
        test_girmeyecekler_yok, test_kabuk_dizgisine_fstring_yok,
        test_acik_kaynak_belgeleri, test_ic_referans_yok,
        test_marka_kalintisi_yok, test_ag_izi_yok, test_varlik_lisans,
        test_chatgpt_kimlik_izi_yok, test_dosya_gezgini_salt_okunur, test_guvenli_dosya_kalici_silmez_ve_kapali,
        test_backend_satis_dili_yok, test_ic_yol_yok, test_yz_kimligi_yok]
MUTASYON = [test_mut_yz_kimligi, test_mut_yz_coauthor, test_mut_yz_saglayici_konsolu_gecer, test_mut_gece_raporu,
            test_mut_sizinti, test_mut_kisisel_dosya, test_mut_chatgpt_token, test_mut_chatgpt_kimlik, test_mut_marka_yol, test_mut_marka_env,
            test_mut_marka_ad, test_mut_tailscale, test_mut_ic_port, test_mut_ic_servis,
            test_mut_girmeyecekler, test_mut_ic_referans, test_mut_varlik_vrm,
            test_mut_varlik_manifest, test_mut_varlik_platform_asset,
            test_mut_dosya_yazma_ucu, test_mut_dosya_yazma_post, test_mut_dosya_yazma_cagri,
            test_mut_dosya_ekran_terminal, test_mut_dosya_ekran_yazma_istegi,
            test_mut_dosya_genis_istisna_yok, test_mut_dosya_terminal_pty_global, test_mut_temiz_gecer,
            test_mut_satis_dili, test_mut_satis_istisnalar_gecer,
            test_mut_ic_yol, test_mut_ic_yol_urun_wiki_gecer,
            test_mut_guvenli_kalici_silme, test_mut_guvenli_kapisiz_uc, test_mut_guvenli_varsayilan_acik,
            test_mut_guvenli_temiz_gecer]


def _kos(testler, baslik):
    kalan = 0
    print(f"── {baslik} ──")
    for t in testler:
        try:
            t()
            print(f"🟢 {t.__name__}")
        except AssertionError as e:
            kalan += 1
            print(f"🔴 {t.__name__}: {e}")
    print(f"geçti {len(testler) - kalan} · kaldı {kalan}\n")
    return kalan


# İçerik desenlerinin birleşimi — pre-commit yalnız STAGE'lenmiş dosyalara bakar,
# böylece mevcut FAZ 2 kalıntıları commit'i bloke etmez ama YENİ kalıntı girmez.
ICERIK_DESENLERI = [("sızıntı", SIZINTI), ("marka", MARKA), ("girmeyecek", YASAK),
                    ("iç-iz", IC_IZ), ("iç-yol", IC_YOL), ("tailscale", TAILSCALE), ("iç-port", IC_PORT)]


def _staged_tara():
    r = subprocess.run(["git", "diff", "--cached", "--name-only", "--diff-filter=ACM"],
                       cwd=KOK, capture_output=True, text=True)
    bulunan = []
    for ad in r.stdout.split("\n"):
        if not ad.strip():
            continue
        p = KOK / ad
        parcalar = Path(ad).parts
        if (not p.is_file() or ATLA.intersection(parcalar) or "vendor" in parcalar
                or ad in KENDI or p.suffix in {".png", ".jpg", ".jpeg", ".webp", ".woff2", ".onnx", ".vrm", ".glb"}):
            continue
        if p.name in KISISEL or p.name.startswith("memory.db"):
            bulunan.append(f"{ad}: kişisel veri dosyası")
            continue
        # Staged tarama tam kapının KAPSAMINI yansıtır (yoksa tam kapıdan sıkı olur):
        marka_muaf = ad in MARKA_ISTISNA               # kişisel profili bilerek referanslayan kapılar
        testte = "tests" in parcalar or p.name.startswith("test_")
        kod_dizini = any(ad.startswith(k) for k in YASAK_KOK)  # YASAK yalnız uygulama kodunda
        try:
            for i, satir in enumerate(p.read_text(errors="ignore").splitlines(), 1):
                for ad_d, dsn in ICERIK_DESENLERI:
                    if ad_d == "marka" and marka_muaf:
                        continue
                    if ad_d == "girmeyecek" and (testte or not kod_dizini):
                        continue                       # tam kapı YASAK'ı testlerde taramaz
                    if ad_d == "tailscale" and testte:
                        continue                       # test fixture IP'leri gerçek değil
                    m = dsn.search(satir)
                    if m:
                        bulunan.append(f"{ad}:{i}:{ad_d}:{m.group(0)}")
        except OSError:
            pass
    return bulunan


if __name__ == "__main__":
    if "--staged" in sys.argv:
        b = _staged_tara()
        if b:
            print("🔴 STAGE'lenen dosyada kalıntı — commit durduruldu:")
            for x in b[:30]:
                print(f"   {x}")
            sys.exit(1)
        print("🟢 stage temiz")
        sys.exit(0)
    if "--kapi" in sys.argv:
        # Tek kapı (temiz kurulum sınavı bunu çağırır): python3 scripts/test_temizlik.py --kapi <ad>
        i = sys.argv.index("--kapi")
        ad = sys.argv[i + 1] if i + 1 < len(sys.argv) else ""
        secilen = [t for t in GATE if t.__name__ == ad]
        if not secilen:
            print(f"🔴 bilinmeyen kapı: {ad!r} · seçenekler: {', '.join(t.__name__ for t in GATE)}")
            sys.exit(2)
        sys.exit(1 if _kos(secilen, f"KAPI {ad}") else 0)
    if "--mutasyon" in sys.argv:
        # Kapının her desen sınıfını yakaladığını kanıtlar; YEŞİL olmalı (çıkış 0).
        sys.exit(1 if _kos(MUTASYON, "MUTASYON (kapı etkinliği)") else 0)
    if _argk:
        KOK = Path(_argk[0])
    # Tam kapı: main'de marka kalıntısı nedeniyle KIRMIZI dönmesi BEKLENİR (FAZ 2).
    g = _kos(GATE, "KAPI (depo taraması)")
    m = _kos(MUTASYON, "MUTASYON (kapı etkinliği)")
    sys.exit(1 if (g or m) else 0)
