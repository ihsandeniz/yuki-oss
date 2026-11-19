"""Sistem bilgisi ve process yönetimi araçları."""
import datetime
import os
import platform
import time as _time

import psutil

from app.services.tool_cache import ttl_cache

_TR_DAYS = ["Pazartesi", "Salı", "Çarşamba", "Perşembe", "Cuma", "Cumartesi", "Pazar"]
_TR_MONTHS = ["Ocak", "Şubat", "Mart", "Nisan", "Mayıs", "Haziran",
               "Temmuz", "Ağustos", "Eylül", "Ekim", "Kasım", "Aralık"]


def get_current_datetime() -> str:
    """Anlık tarih ve saat bilgisini Türkçe döner."""
    now = datetime.datetime.now()
    return (
        f"{_TR_DAYS[now.weekday()]}, {now.day} {_TR_MONTHS[now.month - 1]} {now.year} "
        f"— Saat: {now.strftime('%H:%M:%S')}"
    )


@ttl_cache(seconds=30)
def get_system_info() -> str:
    """Returns system information: OS, CPU (anlık %), RAM, disk, uptime."""
    try:
        mem = psutil.virtual_memory()
        disk = psutil.disk_usage('/')
        cpu_freq = psutil.cpu_freq()
        boot_ts = psutil.boot_time()
        uptime_s = int(_time.time() - boot_ts)
        uptime_str = f"{uptime_s // 3600}s {(uptime_s % 3600) // 60}d"

        lines = [
            f"OS: {platform.system()} {platform.release()} ({platform.machine()})",
            f"CPU: {os.cpu_count()} çekirdek | Kullanım: {psutil.cpu_percent(interval=0.3):.1f}%"
            + (f" | Frekans: {cpu_freq.current:.0f} MHz" if cpu_freq else ""),
            f"RAM: {round(mem.used/(1024**3),1)}/{round(mem.total/(1024**3),1)} GB ({mem.percent}%)",
            f"Disk (/): {round(disk.used/(1024**3),1)}/{round(disk.total/(1024**3),1)} GB ({disk.percent}%)",
            f"Uptime: {uptime_str}",
        ]
        return "\n".join(lines)
    except Exception as e:
        return f"Hata: Sistem bilgileri alınamadı. {str(e)}"


def monitor_system() -> str:
    """Anlık sistem durumu: CPU%, RAM, disk, network, top-10 process."""
    try:
        cpu_total = psutil.cpu_percent(interval=0.5)
        cpu_per_core = psutil.cpu_percent(interval=None, percpu=True)

        mem = psutil.virtual_memory()
        mem_used_gb = round(mem.used / (1024**3), 2)
        mem_total_gb = round(mem.total / (1024**3), 2)

        disk = psutil.disk_usage('/')
        disk_used_gb = round(disk.used / (1024**3), 1)
        disk_total_gb = round(disk.total / (1024**3), 1)

        net = psutil.net_io_counters()
        net_sent_mb = round(net.bytes_sent / (1024**2), 1)
        net_recv_mb = round(net.bytes_recv / (1024**2), 1)

        process_list = []
        for p in psutil.process_iter(['name', 'pid', 'memory_percent']):
            try:
                p.cpu_percent()
                process_list.append(p)
            except (psutil.NoSuchProcess, psutil.AccessDenied):
                pass

        _time.sleep(0.5)

        procs = []
        for p in process_list:
            try:
                procs.append({
                    'name': p.info['name'],
                    'pid': p.pid,
                    'cpu_percent': p.cpu_percent(),
                    'memory_percent': p.info.get('memory_percent', 0),
                })
            except (psutil.NoSuchProcess, psutil.AccessDenied):
                pass
        top10 = sorted(procs, key=lambda x: x.get('cpu_percent') or 0, reverse=True)[:10]
        proc_lines = "\n".join(
            f"  [{p['pid']}] {p['name'][:20]:<20} CPU:{p.get('cpu_percent', 0):.1f}%  RAM:{p.get('memory_percent', 0):.1f}%"
            for p in top10
        )

        lines = [
            f"CPU (toplam): {cpu_total}%",
            f"CPU (çekirdek): {' | '.join(f'{c}%' for c in cpu_per_core)}",
            f"RAM: {mem_used_gb}/{mem_total_gb} GB  ({mem.percent}%)",
            f"Disk (/): {disk_used_gb}/{disk_total_gb} GB  ({disk.percent}%)",
            f"Network: Gönderilen={net_sent_mb} MB  Alınan={net_recv_mb} MB",
            f"Top-10 Process (CPU'ya göre):\n{proc_lines}",
        ]
        return "\n".join(lines)
    except Exception as e:
        return f"Hata: Sistem durumu alınamadı. {str(e)}"


def monitor_process(name_or_pid: str) -> str:
    """Belirli bir process'in anlık durumunu gösterir (CPU, RAM, durum)."""
    name_or_pid = (name_or_pid or "").strip()
    if not name_or_pid:
        return "Hata: Süreç adı ya da PID boş olamaz."  # boş ad `'' in ad` ile ilk süreci seçerdi
    try:
        target = None
        if name_or_pid.isdigit():
            pid = int(name_or_pid)
            if psutil.pid_exists(pid):
                target = psutil.Process(pid)
        else:
            for proc in psutil.process_iter(["pid", "name", "cmdline"]):
                try:
                    if name_or_pid.lower() in proc.info["name"].lower():
                        target = psutil.Process(proc.info["pid"])
                        break
                except (psutil.NoSuchProcess, psutil.AccessDenied):
                    continue

        if target is None:
            return f"'{name_or_pid}' adında çalışan process bulunamadı."

        with target.oneshot():
            name = target.name()
            pid = target.pid
            status = target.status()
            cpu = target.cpu_percent(interval=0.2)
            mem = target.memory_info()
            mem_mb = mem.rss / 1024 / 1024
            create_time = target.create_time()
            started = datetime.datetime.fromtimestamp(create_time).strftime("%H:%M:%S")
            try:
                cmdline = " ".join(target.cmdline())[:120]
            except Exception:
                cmdline = name

        return (
            f"Process: {name} (PID {pid})\n"
            f"Durum: {status} | Başlangıç: {started}\n"
            f"CPU: {cpu:.1f}% | RAM: {mem_mb:.1f} MB\n"
            f"Komut: {cmdline}"
        )
    except psutil.NoSuchProcess:
        return f"Process bulunamadı veya kapandı: {name_or_pid}"
    except Exception as e:
        return f"Hata: {e}"


def check_service(name: str) -> str:
    """systemd servisinin durumunu kontrol eder."""
    import re
    import subprocess
    name = name.strip()
    if not re.match(r'^[a-zA-Z0-9._\-@]+$', name):
        return "Hata: Geçersiz servis adı."
    try:
        result = subprocess.run(
            ["systemctl", "--user", "status", name, "--no-pager", "-n", "5"],
            capture_output=True, text=True, timeout=10
        )
        if result.returncode not in (0, 3):
            result = subprocess.run(
                ["systemctl", "status", name, "--no-pager", "-n", "5"],
                capture_output=True, text=True, timeout=10
            )
        out = result.stdout.strip()
        if not out:
            return f"Servis bulunamadı: {name}"
        return "\n".join(out.splitlines()[:8])
    except FileNotFoundError:
        return "Hata: systemctl bulunamadı."
    except Exception as e:
        return f"Hata: {e}"

