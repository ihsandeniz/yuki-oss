"""Arch Linux sistem araçları: paket yönetimi, journal, servis."""
import re
import subprocess


def list_packages(filter_str: str = "") -> str:
    """Yüklü Arch Linux paketlerini listeler (pacman -Q). filter_str ile filtrele."""
    try:
        result = subprocess.run(
            ["pacman", "-Q"],
            capture_output=True, text=True, timeout=15
        )
        if result.returncode != 0:
            return f"Hata: pacman çalıştırılamadı. {result.stderr[:200]}"
        lines = result.stdout.strip().splitlines()
        if filter_str:
            lines = [l for l in lines if filter_str.lower() in l.lower()]
        if not lines:
            return f"'{filter_str}' ile eşleşen paket bulunamadı." if filter_str else "Paket listesi boş."
        total = len(lines)
        display = lines[:50]
        out = "\n".join(display)
        if total > 50:
            out += f"\n... ve {total - 50} paket daha (filter_str ile daralt)"
        return f"Yüklü paketler ({total} toplam):\n{out}"
    except FileNotFoundError:
        return "Hata: pacman bulunamadı (Arch Linux dışı sistem)."
    except Exception as e:
        return f"Hata: {e}"


def check_updates() -> str:
    """Arch Linux güncelleme kontrolü (checkupdates). Bekleyen güncellemeleri listeler."""
    try:
        result = subprocess.run(
            ["checkupdates"],
            capture_output=True, text=True, timeout=60
        )
        if result.returncode == 2 or (result.returncode == 0 and not result.stdout.strip()):
            return "Sistem güncel — bekleyen güncelleme yok."
        if result.returncode not in (0, 2):
            r2 = subprocess.run(
                ["pacman", "-Qu"],
                capture_output=True, text=True, timeout=30
            )
            if r2.returncode != 0:
                return f"Hata: checkupdates ve pacman -Qu başarısız. {result.stderr[:200]}"
            lines = r2.stdout.strip().splitlines()
            if not lines:
                return "Sistem güncel."
            return f"Bekleyen güncellemeler ({len(lines)}):\n" + "\n".join(lines[:30])
        lines = result.stdout.strip().splitlines()
        return f"Bekleyen güncellemeler ({len(lines)}):\n" + "\n".join(lines[:30])
    except FileNotFoundError:
        return "Hata: checkupdates bulunamadı. pacman-contrib yükle: sudo pacman -S pacman-contrib"
    except Exception as e:
        return f"Hata: {e}"


def read_journal(unit: str = "", lines: int = 50) -> str:
    """systemd journal log okur. unit: servis adı (boş=genel). lines: kaç satır."""
    lines = max(1, min(lines, 200))
    cmd = ["journalctl", "--no-pager", "-n", str(lines), "--output=short"]
    if unit:
        cmd += ["-u", unit]
    try:
        result = subprocess.run(
            cmd,
            capture_output=True, text=True, timeout=15
        )
        if result.returncode != 0:
            return f"Hata: journalctl çalıştırılamadı. {result.stderr[:200]}"
        out = result.stdout.strip()
        if not out:
            return f"{'Servis ' + unit + ' için ' if unit else ''}Log bulunamadı."
        return out
    except FileNotFoundError:
        return "Hata: journalctl bulunamadı (systemd yüklü değil)."
    except Exception as e:
        return f"Hata: {e}"
