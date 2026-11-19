"""Sistem metrik toplayıcı — tek paylaşımlı örnekleyici (psutil + GPU).

Bloklayan psutil çağrıları çağıran taraf `asyncio.to_thread` ile sarmalı.
Delta hesapları (CPU/net/disk/RAPL) çağrılar arası saklanan durumdan üretilir;
`prime()` ilk-çağrı 0 sorununu giderir. Eşzamanlı erişim `_lock` ile serileşir.
"""
from __future__ import annotations

import glob
import logging
import os
import threading
import time as _time

import psutil

from app.services.monitoring import gpu as _gpu
from app.services.monitoring import health as _health


_MAKINE: dict | None = None
_IPLIK_ADLARI = {"MainThread"}


def _cpu_modeli() -> str | None:
    """İşlemcinin pazarlama adı ("AMD Ryzen 5 7600X 6-Core Processor"). Okunamazsa None.

    Ürün Linux + Windows (+ macOS) koşuyor: `/proc/cpuinfo` yalnız Linux'ta var —
    kişisel sürüm yalnız onu okuyordu. `platform.processor()` Windows'ta
    "Intel64 Family 6 Model …" gibi ailesel kod verir, ad değil → son çare."""
    import platform
    import sys
    try:
        if sys.platform.startswith("linux"):
            with open("/proc/cpuinfo", encoding="utf-8", errors="replace") as f:
                for satir in f:
                    if satir.lower().startswith(("model name", "hardware")):
                        return satir.split(":", 1)[1].strip() or None
        elif sys.platform == "win32":
            import winreg
            with winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE,
                                r"HARDWARE\DESCRIPTION\System\CentralProcessor\0") as k:
                return str(winreg.QueryValueEx(k, "ProcessorNameString")[0]).strip() or None
        elif sys.platform == "darwin":
            import subprocess
            r = subprocess.run(["sysctl", "-n", "machdep.cpu.brand_string"],
                               capture_output=True, text=True, timeout=2)
            return r.stdout.strip() or None
    except Exception as e:  # noqa: BLE001
        logger.debug("işlemci modeli okunamadı: %s", e)
    return platform.processor() or None


def _demo_disk(diskler: list) -> list:
    """Demo kipinde bağlama noktası gerçek ev yolunu/kullanıcı adını göstermesin."""
    from app import demo_kip
    return [demo_kip.disk_temizle(d) for d in diskler] if demo_kip.acik() else diskler


def makine_bilgisi() -> dict:
    """Bilgisayarın adı + işlemci modeli — değişmez, bir kez okunur (SİSTEM başlığı)."""
    global _MAKINE
    if _MAKINE is None:
        import platform
        from app import demo_kip
        ad = demo_kip.MAKINE_ADI if demo_kip.acik() else (platform.node() or None)
        _MAKINE = {"ad": ad, "cpu": _cpu_modeli()}
    return _MAKINE

logger = logging.getLogger(__name__)

_PSEUDO_FS = {
    "proc", "sysfs", "tmpfs", "devtmpfs", "devpts", "cgroup", "cgroup2",
    "overlay", "squashfs", "mqueue", "debugfs", "tracefs", "securityfs",
    "pstore", "bpf", "configfs", "fusectl", "hugetlbfs", "autofs", "ramfs",
    "efivarfs", "binfmt_misc", "fuse.portal", "nsfs",
}


def _disk_type(device: str) -> str:
    d = device.lower()
    if "nvme" in d:
        return "nvme"
    if "mmc" in d:
        return "mmc"
    if "sd" in d:
        return "sata"
    if "zram" in d:
        return "zram"
    return "disk"


class SystemMonitor:
    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._prev_net = None      # (per-nic counters, monotonic ts)
        self._prev_disk = None     # (per-disk counters, monotonic ts)
        self._prev_rapl = None     # (energy_uj, monotonic ts)
        self._primed = False
        self._boot = psutil.boot_time()

    # ── baseline priming ─────────────────────────────────────────────────
    def prime(self) -> None:
        try:
            psutil.cpu_percent(interval=None, percpu=True)
            psutil.cpu_percent(interval=None)
            mono = _time.monotonic()
            self._prev_net = (psutil.net_io_counters(pernic=True), mono)
            self._prev_disk = (psutil.disk_io_counters(perdisk=True) or {}, mono)
            self._prev_rapl = self._read_rapl()
            for p in psutil.process_iter():
                try:
                    p.cpu_percent(None)
                except (psutil.NoSuchProcess, psutil.AccessDenied):
                    pass
            self._primed = True
        except Exception as e:  # noqa: BLE001
            logger.warning("prime hatası: %s", e)

    # ── ana snapshot ─────────────────────────────────────────────────────
    def snapshot(self, *, include_processes: bool = False,
                 proc_limit: int = 40, proc_sort: str = "cpu") -> dict:
        if not self._primed:
            self.prime()
            _time.sleep(0.2)  # delta için minik pencere

        with self._lock:
            now = _time.time()
            mono = _time.monotonic()

            per_core = psutil.cpu_percent(interval=None, percpu=True)
            total = round(sum(per_core) / len(per_core), 1) if per_core else 0.0
            try:
                fq = psutil.cpu_freq()
                freq_mhz = round(fq.current) if fq else None
            except Exception:
                freq_mhz = None
            try:
                load = list(os.getloadavg())
            except Exception:
                load = None

            cpu = {
                "total": total,
                "per_core": [round(c, 1) for c in per_core],
                "freq_mhz": freq_mhz,
                "load_avg": [round(x, 2) for x in load] if load else None,
                "temp_c": self._cpu_temp(),
            }

            vm = psutil.virtual_memory()
            sw = psutil.swap_memory()
            mem = {
                "used_gb": round(vm.used / 1024**3, 2),
                "total_gb": round(vm.total / 1024**3, 2),
                "percent": vm.percent,
                "swap_used_gb": round(sw.used / 1024**3, 2),
                "swap_total_gb": round(sw.total / 1024**3, 2),
                "cached_gb": round(getattr(vm, "cached", 0) / 1024**3, 2),
            }

            gnv = _gpu.nvidia_snapshot()
            proc_vram: dict = {}
            if gnv:
                proc_vram = gnv.pop("_proc_vram", {})
            gamd = _gpu.amd_snapshot()

            snap = {
                "ts": now,
                "uptime_s": int(now - self._boot),
                "cpu": cpu,
                "mem": mem,
                "gpu_nvidia": gnv,
                "gpu_amd": gamd,
                "disks": _demo_disk(self._disks(mono)),
                "net": self._net(mono),
                "power": self._power(),
                "makine": makine_bilgisi(),
            }
            snap["health_score"] = _health.health_score(snap)
            snap["alerts"] = _health.eval_alerts(snap)

            if include_processes:
                snap["processes"] = self._processes(proc_limit, proc_sort, proc_vram)
            return snap

    # ── alt parçalar ─────────────────────────────────────────────────────
    def _cpu_temp(self):
        try:
            temps = psutil.sensors_temperatures()
        except Exception:
            return None
        if not temps:
            return None
        for key in ("k10temp", "coretemp", "zenpower", "acpitz"):
            arr = temps.get(key)
            if arr:
                for t in arr:
                    if t.label in ("Tctl", "Tdie", "Package id 0", ""):
                        return round(t.current, 1)
                return round(arr[0].current, 1)
        for arr in temps.values():
            if arr:
                return round(arr[0].current, 1)
        return None

    def _nvme_temp(self):
        try:
            temps = psutil.sensors_temperatures()
        except Exception:
            return None
        arr = temps.get("nvme") if temps else None
        return round(arr[0].current, 1) if arr else None

    def _disks(self, mono):
        try:
            io_now = psutil.disk_io_counters(perdisk=True) or {}
        except Exception:
            io_now = {}
        prev_io, prev_ts = self._prev_disk or ({}, mono)
        dt = max(mono - prev_ts, 1e-6)
        io_rates = {}
        for dev, c in io_now.items():
            p = prev_io.get(dev)
            if p:
                io_rates[dev] = (
                    max(c.read_bytes - p.read_bytes, 0) / dt / 1024**2,
                    max(c.write_bytes - p.write_bytes, 0) / dt / 1024**2,
                )
        self._prev_disk = (io_now, mono)

        out, seen = [], set()
        try:
            parts = psutil.disk_partitions(all=False)
        except Exception:
            parts = []
        nvme_temp = self._nvme_temp()
        for part in parts:
            if not part.fstype or part.fstype in _PSEUDO_FS:
                continue
            if part.mountpoint in seen:
                continue
            seen.add(part.mountpoint)
            try:
                u = psutil.disk_usage(part.mountpoint)
            except Exception:
                continue
            base = os.path.basename(part.device)
            r = w = None
            for dn, (rr, ww) in io_rates.items():
                if base.startswith(dn):
                    r, w = round(rr, 2), round(ww, 2)
                    break
            dtype = _disk_type(part.device)
            out.append({
                "mount": part.mountpoint,
                "device": base,
                "type": dtype,
                "used_gb": round(u.used / 1024**3, 1),
                "total_gb": round(u.total / 1024**3, 1),
                "percent": u.percent,
                "read_mbps": r,
                "write_mbps": w,
                "temp_c": nvme_temp if dtype == "nvme" else None,
            })
        return out

    def _net(self, mono):
        try:
            now = psutil.net_io_counters(pernic=True) or {}
        except Exception:
            now = {}
        prev, prev_ts = self._prev_net or ({}, mono)
        dt = max(mono - prev_ts, 1e-6)
        ifaces = []
        for name, c in now.items():
            if name == "lo":
                continue
            p = prev.get(name)
            up = down = 0.0
            if p:
                up = max(c.bytes_sent - p.bytes_sent, 0) / dt / 1024**2
                down = max(c.bytes_recv - p.bytes_recv, 0) / dt / 1024**2
            ifaces.append({
                "name": name,
                "up_mbps": round(up, 3),
                "down_mbps": round(down, 3),
                "sent_total_mb": round(c.bytes_sent / 1024**2, 1),
                "recv_total_mb": round(c.bytes_recv / 1024**2, 1),
            })
        self._prev_net = (now, mono)
        try:
            conns = len(psutil.net_connections(kind="inet"))
        except Exception:
            conns = None
        ifaces.sort(key=lambda i: i["down_mbps"] + i["up_mbps"], reverse=True)
        return {"ifaces": ifaces, "connections": conns}

    def _read_rapl(self):
        best = None
        for f in glob.glob("/sys/class/powercap/*/energy_uj"):
            # yalnız üst-düzey domain (intel-rapl:0, amd) — iç-domain'leri (intel-rapl:0:0) atla
            domain = f.rsplit("/", 2)[1]
            if domain.count(":") > 1:
                continue
            try:
                with open(f) as fh:
                    e = int(fh.read().strip())
                best = e if best is None else best + e
            except Exception:
                pass
        return (best, _time.monotonic()) if best is not None else None

    def _power(self):
        # 1) hwmon power*_input (mikrowatt, anlık, root'suz) — PPT vb. RAPL root-only olduğu için tercih.
        for f in glob.glob("/sys/class/hwmon/hwmon*/power1_input"):
            try:
                with open(f) as fh:
                    uw = int(fh.read().strip())
                lbl = None
                try:
                    with open(f.replace("input", "label")) as lf:
                        lbl = lf.read().strip()
                except Exception:
                    pass
                return {"package_w": round(uw / 1e6, 1), "label": lbl or "PPT"}
            except Exception:
                continue
        # 2) RAPL energy delta (genelde root gerekir → izin yoksa None)
        cur = self._read_rapl()
        if cur is None:
            return None
        if self._prev_rapl is None:
            self._prev_rapl = cur
            return None
        e0, t0 = self._prev_rapl
        e1, t1 = cur
        self._prev_rapl = cur
        de, dt = e1 - e0, max(t1 - t0, 1e-6)
        if de < 0:  # sayaç sarması
            return None
        return {"package_w": round(de / 1e6 / dt, 1), "label": "RAPL"}

    def _processes(self, limit, sort_key, proc_vram):
        from app import demo_kip
        if demo_kip.acik():           # demo: bu makinenin süreç adları/komutları görünmez
            return demo_kip.surecler(limit, sort_key)
        rows = []
        for p in psutil.process_iter(["pid", "name", "username", "memory_info",
                                      "num_threads", "create_time"]):
            try:
                info = p.info
                cpu = p.cpu_percent(None)  # process_iter cache → son döngüden delta
                mi = info.get("memory_info")
                rows.append({
                    "pid": info["pid"],
                    "name": info.get("name") or "?",
                    "cpu": round(cpu, 1),
                    "mem_mb": round((mi.rss if mi else 0) / 1024**2, 1),
                    "threads": info.get("num_threads"),
                    "user": info.get("username"),
                    "uptime_s": int(_time.time() - info["create_time"]) if info.get("create_time") else None,
                    "vram_mb": proc_vram.get(info["pid"]),
                })
            except (psutil.NoSuchProcess, psutil.AccessDenied):
                continue

        key = {"cpu": "cpu", "mem": "mem_mb", "pid": "pid", "name": "name"}.get(sort_key, "cpu")
        if key == "name":
            rows.sort(key=lambda r: (r.get("name") or "").lower())
        else:
            rows.sort(key=lambda r: (r.get(key) or 0), reverse=True)
        top = rows[:limit]

        for r in top:  # komut satırını yalnız görünen top-N için çek (maliyet)
            try:
                cl = psutil.Process(r["pid"]).cmdline()
                r["cmd"] = (" ".join(cl))[:140] if cl else r["name"]
                # Firefox türevi içerik süreçleri kendini "MainThread" diye adlandırır —
                # "ne yiyor" listesinde iş parçacığı adı değil program adı görünsün.
                if r["name"] in _IPLIK_ADLARI and cl:
                    r["name"] = os.path.basename(cl[0]) or r["name"]
            except (psutil.NoSuchProcess, psutil.AccessDenied):
                r["cmd"] = r["name"]
        return top

    def process_detail(self, pid: int):
        from app import demo_kip
        if demo_kip.acik():
            return demo_kip.surec_ayrinti(pid)
        try:
            p = psutil.Process(pid)
            with p.oneshot():
                name = p.name()
                status = p.status()
                try:
                    cpu = round(p.cpu_percent(None), 1)
                except Exception:
                    cpu = None
                mi = p.memory_info()
                mem_mb = round(mi.rss / 1024**2, 1)
                threads = p.num_threads()
                ct = p.create_time()
                try:
                    cmd = " ".join(p.cmdline())[:400] or name
                except Exception:
                    cmd = name
                try:
                    io = p.io_counters()
                    ior, iow = round(io.read_bytes / 1024**2, 1), round(io.write_bytes / 1024**2, 1)
                except Exception:
                    ior = iow = None
                try:
                    user = p.username()
                except Exception:
                    user = None
            import datetime as _d
            return {
                "pid": pid, "name": name, "status": status, "cpu": cpu,
                "mem_mb": mem_mb, "threads": threads, "user": user,
                "started": _d.datetime.fromtimestamp(ct).strftime("%H:%M:%S"),
                "uptime_s": int(_time.time() - ct),
                "cmdline": cmd, "io_read_mb": ior, "io_write_mb": iow,
            }
        except psutil.NoSuchProcess:
            return None
        except Exception as e:  # noqa: BLE001
            return {"error": str(e)}


monitor = SystemMonitor()
