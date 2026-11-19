"""Sandbox ve yol güvenliği yardımcıları — tüm tool modülleri bu modülü kullanır."""
import os
import re
try:
    import resource as _resource  # Unix-only; Windows'ta yok (sandbox limitleri POSIX'e özgü)
except ImportError:  # pragma: no cover - Windows
    _resource = None
from pathlib import Path

from app.config import (
    CMD_SANDBOX_ENABLED, CMD_MAX_MEMORY_MB, CMD_MAX_CPU_SECONDS, CMD_MAX_FILE_SIZE_MB,
)

_HOME_DIR = Path.home().resolve()

_SAFE_ROOTS = [
    _HOME_DIR,
    Path("/tmp").resolve(),
]

#: `.env` yol PARÇASI olarak aranır: `.env.local`, `prod.env`, `.envrc` düşer; `my.environment.txt` düşmez
#: (eskiden alt dizge araması masum adları da yazmaya kapatıyordu).
_ENV_PARCASI = re.compile(r"\.env(?:$|[._-]|rc$)")
_SENSITIVE_WRITE_PATTERNS = (
    ".ssh", ".gnupg", ".bashrc", ".zshrc",
    ".bash_profile", ".bash_logout", ".profile",
    ".config/sops", ".password-store",
    # Yuki'nin kendi güvenlik/ayar dosyaları (2026-10-01): araç `config.user.json`a `AG_ACIK:true` yazıp ağ
    # kapısını kendi başına açabilirdi; kilit ve giriş sayacı dosyaları da aynı sınıfta. (.backup/.tmp dahil)
    "config.user.json", "app_lock.json", "login_guard_state.json",
    # P1 F (denetim 10-06 H8): kalıcı başlatma — mod dosyası (autostart komutları), oturum
    # açılışı ve kullanıcı servisleri. Mod kaydının onay kapısı dosya yoluyla atlanamasın.
    "modes.json", ".config/autostart", ".config/systemd", "Start Menu",
    # P1 E: motor kapısının tek sırrı (v0.8.1 A) — araç onu da yazamasın
    "oturum-anahtari",
)


def _apply_sandbox_limits() -> None:
    """Subprocess preexec_fn — fork() sonrası resource limitlerini set eder."""
    if _resource is None:  # Windows — POSIX rlimit yok
        return
    try:
        cpu = CMD_MAX_CPU_SECONDS
        _resource.setrlimit(_resource.RLIMIT_CPU, (cpu, cpu))

        mem = CMD_MAX_MEMORY_MB * 1024 * 1024
        _resource.setrlimit(_resource.RLIMIT_AS, (mem, mem))

        fsize = CMD_MAX_FILE_SIZE_MB * 1024 * 1024
        _resource.setrlimit(_resource.RLIMIT_FSIZE, (fsize, fsize))

        os.setsid()
    except Exception:
        pass


def _build_wayland_env() -> dict:
    """grim için Wayland ortam değişkenlerini hazırla."""
    env = os.environ.copy()
    uid = os.getuid() if hasattr(os, "getuid") else 0  # os.getuid Unix-only; Windows'ta yok (grim=Wayland zaten Linux'a özgü)
    xdg = env.get("XDG_RUNTIME_DIR") or f"/run/user/{uid}"
    env.setdefault("XDG_RUNTIME_DIR", xdg)

    if not env.get("WAYLAND_DISPLAY"):
        import glob as _glob
        sockets = _glob.glob(f"{xdg}/wayland-*")
        sockets = [s for s in sockets if not s.endswith(".lock")]
        if sockets:
            env["WAYLAND_DISPLAY"] = os.path.basename(sorted(sockets)[0])
        else:
            env["WAYLAND_DISPLAY"] = "wayland-1"

    if not env.get("HYPRLAND_INSTANCE_SIGNATURE"):
        import glob as _glob
        try:
            sigs = _glob.glob(f"{xdg}/hypr/*")
            if sigs:
                # En son değiştirilen (aktif) Hyprland instance'ını seç.
                # getmtime race: glob ile max arasında dosya silinebilir → var olmayanı 0 say.
                newest = max(sigs, key=lambda p: os.path.getmtime(p) if os.path.exists(p) else 0)
                if os.path.basename(newest):
                    env["HYPRLAND_INSTANCE_SIGNATURE"] = os.path.basename(newest)
        except (FileNotFoundError, ValueError, OSError):
            pass  # fallback: HYPRLAND_INSTANCE_SIGNATURE default kalır

    return env


def _is_safe_path(p: Path) -> bool:
    resolved = p.resolve()
    return any(resolved == root or str(resolved).startswith(str(root) + os.sep) for root in _SAFE_ROOTS)


# ── Okuma tarafı hassas yollar (P1 E, denetim 10-06 H5) ──────────────────────
# `read_file` tüm $HOME'u okuyordu. Okutulan bir sayfadaki gizli talimat kullanıcının
# token/kimlik dosyalarını okutup `browse_web` ile dışarı yollatabiliyordu. Maskeleyici
# ikinci kat; asıl kapı burada: bu dosyalar modele HİÇ okunmaz.
# Dizin parçası (yolun herhangi bir yerinde geçen klasör):
_SENSITIVE_READ_DIRS = (
    ".ssh", ".gnupg", ".password-store", ".aws", ".kube", ".docker", ".azure",
    ".config/gcloud", ".config/gh", ".config/sops", ".local/share/keyrings",
    ".mozilla", ".config/google-chrome", ".config/chromium", ".config/BraveSoftware",
    ".config/microsoft-edge", ".thunderbird",
)
# Dosya adı (tam ad, küçük harf):
_SENSITIVE_READ_NAMES = frozenset({
    ".netrc", ".git-credentials", ".pgpass", ".npmrc", ".pypirc",
    "credentials", "credentials.json", "client_secret.json", "token.json", "tokens.json",
    # Yuki'nin kendi veri dizini (~/.config/yuki-oss): oturum anahtarı motor kapısının
    # tek sırrı (v0.8.1 A), lisans, Google token'ı, yüz verisi, kilit.
    "oturum-anahtari", "license.key", "planner_tokens.json", "planner_state_tokens.json",
    "faces.json", "app_lock.json", "login_guard_state.json", "config.user.json",
    "cookies", "login data", "logins.json", "key4.db", "cert9.db",
})
_SENSITIVE_READ_SUFFIXES = (".pem", ".key", ".p12", ".pfx", ".keystore", ".jks", ".kdbx", ".gpg", ".asc")
# `.env`, `.env.local`, `.env.production`… — ama `.env.example`/`.env.sample` şablondur, okunur.
_ENV_SABLON = (".example", ".sample", ".template", ".dist")


def _is_sensitive_read_path(p: Path) -> bool:
    """Yol (sembolik bağ çözülmüş hâli dahil) kimlik/token dosyası mı."""
    for aday in {p, p.resolve()}:
        ad = aday.name.lower()
        if ad == ".env" or (ad.startswith(".env.") and not ad.endswith(_ENV_SABLON)):
            return True
        if ad in _SENSITIVE_READ_NAMES or ad.endswith(_SENSITIVE_READ_SUFFIXES):
            return True
        if ad.startswith("client_secret") and ad.endswith(".json"):
            return True
        if ad.startswith(("id_rsa", "id_ed25519", "id_ecdsa", "id_dsa")):
            return True
        yol = aday.as_posix()
        if any(f"/{d}/" in yol or yol.endswith(f"/{d}") for d in _SENSITIVE_READ_DIRS):
            return True
    return False


def _is_safe_write_path(p: Path) -> tuple[bool, str]:
    if not _is_safe_path(p):
        return False, f"Güvenlik — sadece {_HOME_DIR} ve /tmp altına yazılabilir."
    path_str = str(p)
    if any(_ENV_PARCASI.search(parca) for parca in p.parts):
        return False, "Güvenlik — bu dosyaya yazma izni yok (hassas yol)."
    for pattern in _SENSITIVE_WRITE_PATTERNS:
        if pattern in path_str:
            return False, "Güvenlik — bu dosyaya yazma izni yok (hassas yol)."
    return True, ""
