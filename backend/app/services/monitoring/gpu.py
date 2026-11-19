"""GPU telemetri — NVIDIA (pynvml/nvidia-ml-py) + AMD iGPU (sysfs).

GPU yoksa/sürücü erişilemezse sessizce None döner (sert hata yok).
"""
from __future__ import annotations

import glob
import logging

logger = logging.getLogger(__name__)

_nvml_ready = False
_nvml_failed = False


def _ensure_nvml() -> bool:
    global _nvml_ready, _nvml_failed
    if _nvml_ready:
        return True
    if _nvml_failed:
        return False
    try:
        import pynvml
        pynvml.nvmlInit()
        _nvml_ready = True
        return True
    except Exception as e:  # noqa: BLE001
        logger.info("NVML kullanılamıyor (NVIDIA GPU yok/sürücü yok): %s", e)
        _nvml_failed = True
        return False


def _decode(v):
    return v.decode() if isinstance(v, (bytes, bytearray)) else v


def nvidia_snapshot() -> dict | None:
    """NVIDIA GPU özeti. `_proc_vram` anahtarı pid→VRAM(MB) haritasıdır (dahili)."""
    if not _ensure_nvml():
        return None
    try:
        import pynvml
        h = pynvml.nvmlDeviceGetHandleByIndex(0)
        util = pynvml.nvmlDeviceGetUtilizationRates(h)
        mem = pynvml.nvmlDeviceGetMemoryInfo(h)
        try:
            temp = pynvml.nvmlDeviceGetTemperature(h, pynvml.NVML_TEMPERATURE_GPU)
        except Exception:
            temp = None
        try:
            power = round(pynvml.nvmlDeviceGetPowerUsage(h) / 1000.0, 1)  # mW → W
        except Exception:
            power = None
        try:
            fan = pynvml.nvmlDeviceGetFanSpeed(h)
        except Exception:
            fan = None

        proc_vram: dict[int, int] = {}
        for fn in (pynvml.nvmlDeviceGetComputeRunningProcesses,
                   pynvml.nvmlDeviceGetGraphicsRunningProcesses):
            try:
                for p in fn(h):
                    used = getattr(p, "usedGpuMemory", None)
                    if used:
                        proc_vram[p.pid] = proc_vram.get(p.pid, 0) + int(used // (1024 * 1024))
            except Exception:
                pass

        return {
            "name": _decode(pynvml.nvmlDeviceGetName(h)),
            "util": util.gpu,
            "mem_util": util.memory,
            "vram_used_mb": int(mem.used // (1024 * 1024)),
            "vram_total_mb": int(mem.total // (1024 * 1024)),
            "temp_c": temp,
            "power_w": power,
            "fan": fan,
            "_proc_vram": proc_vram,
        }
    except Exception as e:  # noqa: BLE001
        logger.warning("NVIDIA snapshot hatası: %s", e)
        return None


def _read_int(path: str) -> int | None:
    try:
        with open(path) as f:
            return int(f.read().strip())
    except Exception:
        return None


def amd_snapshot() -> dict | None:
    """AMD GPU busy% + (varsa) VRAM — sysfs üzerinden, kütüphanesiz."""
    busy_files = sorted(glob.glob("/sys/class/drm/card*/device/gpu_busy_percent"))
    if not busy_files:
        return None
    path = busy_files[0]
    busy = _read_int(path)
    if busy is None:
        return None
    base = path.rsplit("/", 1)[0]
    out: dict = {"name": "AMD iGPU", "busy": busy}
    vram_used = _read_int(f"{base}/mem_info_vram_used")
    vram_total = _read_int(f"{base}/mem_info_vram_total")
    if vram_used is not None and vram_total:
        out["vram_used_mb"] = vram_used // (1024 * 1024)
        out["vram_total_mb"] = vram_total // (1024 * 1024)
    return out


def shutdown() -> None:
    global _nvml_ready
    if _nvml_ready:
        try:
            import pynvml
            pynvml.nvmlShutdown()
        except Exception:
            pass
        _nvml_ready = False
