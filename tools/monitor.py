"""
JARVIS Real System Monitor
tools/monitor.py

Provides real CPU/RAM/disk/GPU/network metrics and top processes.
Used by server.py's background monitoring thread.
"""

from __future__ import annotations

import time
import warnings
from typing import Any

warnings.filterwarnings("ignore", category=DeprecationWarning, module="GPUtil")

try:
    import psutil
    PSUTIL_OK = True
except ImportError:
    psutil = None
    PSUTIL_OK = False

try:
    import GPUtil
    GPUTIL_OK = True
except ImportError:
    GPUtil = None
    GPUTIL_OK = False


def get_system_stats() -> dict[str, Any]:
    """
    Return a comprehensive snapshot of system metrics.
    All values are real readings from psutil.
    """
    if not PSUTIL_OK:
        return {
            "error": "psutil not installed",
            "ts": time.time(),
        }

    stats: dict[str, Any] = {"ts": time.time()}

    # ── CPU ─────────────────────────────────────────────────
    try:
        cpu_pct = psutil.cpu_percent(interval=0.1)
        cpu_count = psutil.cpu_count(logical=True)
        cpu_freq = psutil.cpu_freq()
        stats["cpu"] = {
            "percent": cpu_pct,
            "cores": cpu_count,
            "freq_mhz": round(cpu_freq.current) if cpu_freq else None,
        }
    except Exception as e:
        stats["cpu"] = {"error": str(e)}

    # ── RAM ──────────────────────────────────────────────────
    try:
        mem = psutil.virtual_memory()
        swap = psutil.swap_memory()
        stats["ram"] = {
            "percent": mem.percent,
            "used_gb": round(mem.used / 1e9, 2),
            "total_gb": round(mem.total / 1e9, 2),
            "available_gb": round(mem.available / 1e9, 2),
        }
        stats["swap"] = {
            "percent": swap.percent,
            "used_gb": round(swap.used / 1e9, 2),
            "total_gb": round(swap.total / 1e9, 2),
        }
    except Exception as e:
        stats["ram"] = {"error": str(e)}

    # ── Disk ─────────────────────────────────────────────────
    try:
        partitions = []
        for part in psutil.disk_partitions(all=False):
            try:
                usage = psutil.disk_usage(part.mountpoint)
                partitions.append({
                    "device": part.device,
                    "mountpoint": part.mountpoint,
                    "fstype": part.fstype,
                    "percent": usage.percent,
                    "used_gb": round(usage.used / 1e9, 1),
                    "total_gb": round(usage.total / 1e9, 1),
                    "free_gb": round(usage.free / 1e9, 1),
                })
            except PermissionError:
                pass
        stats["disk"] = partitions
    except Exception as e:
        stats["disk"] = {"error": str(e)}

    # ── Network ──────────────────────────────────────────────
    try:
        net = psutil.net_io_counters()
        stats["network"] = {
            "bytes_sent_mb": round(net.bytes_sent / 1e6, 1),
            "bytes_recv_mb": round(net.bytes_recv / 1e6, 1),
            "packets_sent": net.packets_sent,
            "packets_recv": net.packets_recv,
        }
    except Exception as e:
        stats["network"] = {"error": str(e)}

    # ── GPU ──────────────────────────────────────────────────
    if GPUTIL_OK:
        try:
            gpus = GPUtil.getGPUs()
            stats["gpu"] = [
                {
                    "id": g.id,
                    "name": g.name,
                    "load_pct": round(g.load * 100, 1),
                    "mem_used_mb": round(g.memoryUsed),
                    "mem_total_mb": round(g.memoryTotal),
                    "mem_pct": round(g.memoryUtil * 100, 1),
                    "temp_c": g.temperature,
                }
                for g in gpus
            ]
        except Exception as e:
            stats["gpu"] = {"error": str(e)}
    else:
        stats["gpu"] = []

    # ── Top processes ─────────────────────────────────────────
    try:
        procs = []
        cpu_cores = max(1, psutil.cpu_count(logical=True) or 1)
        for p in psutil.process_iter(["pid", "name", "cpu_percent", "memory_percent", "status"]):
            try:
                info = p.info
                pname = (info.get("name") or "").lower()
                # Exclude Windows idle and kernel pseudo-processes
                if pname in ("system idle process", "system", "idle", ""):
                    continue
                raw_cpu = info.get("cpu_percent", 0) or 0
                # Normalize process CPU across cores so it never exceeds 100%
                norm_cpu = min(100.0, round(raw_cpu / cpu_cores, 1))
                info["cpu_percent"] = norm_cpu
                if info.get("memory_percent", 0) is None:
                    info["memory_percent"] = 0
                else:
                    info["memory_percent"] = round(info["memory_percent"], 1)
                procs.append(info)
            except (psutil.NoSuchProcess, psutil.AccessDenied):
                pass
        procs.sort(key=lambda x: x.get("cpu_percent", 0), reverse=True)
        stats["top_procs"] = procs[:10]
    except Exception as e:
        stats["top_procs"] = []

    # ── Battery ───────────────────────────────────────────────
    try:
        battery = psutil.sensors_battery()
        if battery:
            stats["battery"] = {
                "percent": battery.percent,
                "plugged": battery.power_plugged,
                "secs_left": battery.secsleft if battery.secsleft != psutil.POWER_TIME_UNLIMITED else -1,
            }
    except Exception:
        pass

    # ── Alerts ────────────────────────────────────────────────
    alerts = []
    cpu_val = stats.get("cpu", {}).get("percent", 0) or 0
    ram_val = stats.get("ram", {}).get("percent", 0) or 0

    if cpu_val > 90:
        alerts.append({"type": "cpu_high", "value": cpu_val, "msg": f"High CPU usage: {cpu_val:.0f}%"})
    if ram_val > 90:
        alerts.append({"type": "ram_high", "value": ram_val, "msg": f"High RAM usage: {ram_val:.0f}%"})

    for part in (stats.get("disk") or []):
        if isinstance(part, dict) and part.get("percent", 0) > 95:
            alerts.append({
                "type": "disk_full",
                "value": part["percent"],
                "msg": f"Disk {part.get('mountpoint', '?')} at {part['percent']:.0f}%",
            })

    stats["alerts"] = alerts
    return stats


def get_natural_language_summary() -> str:
    """
    Return a human-readable summary of current system stats.
    Used by the LLM to answer "why is my PC slow?" etc.
    """
    s = get_system_stats()

    if "error" in s:
        return f"Could not read system stats: {s['error']}"

    cpu = s.get("cpu", {})
    ram = s.get("ram", {})
    disk_list = s.get("disk", [])
    top = s.get("top_procs", [])
    battery = s.get("battery")
    gpu_list = s.get("gpu", [])

    lines = [
        f"**CPU**: {cpu.get('percent', '?')}% ({cpu.get('cores', '?')} cores"
        + (f", {cpu.get('freq_mhz', '?')} MHz" if cpu.get('freq_mhz') else "")
        + ")",

        f"**RAM**: {ram.get('used_gb', '?')} GB / {ram.get('total_gb', '?')} GB used ({ram.get('percent', '?')}%)",
    ]

    # Primary disk
    if disk_list and isinstance(disk_list, list) and disk_list:
        d = disk_list[0]
        lines.append(
            f"**Disk** ({d.get('mountpoint', '?')}): "
            f"{d.get('used_gb', '?')} GB / {d.get('total_gb', '?')} GB ({d.get('percent', '?')}%)"
        )

    # GPU
    for g in (gpu_list or []):
        if isinstance(g, dict):
            lines.append(
                f"**GPU** ({g.get('name', '?')}): {g.get('load_pct', '?')}% load, "
                f"{g.get('mem_used_mb', '?')}/{g.get('mem_total_mb', '?')} MB VRAM, "
                f"{g.get('temp_c', '?')}°C"
            )

    # Battery
    if battery:
        status = "plugged in" if battery.get("plugged") else "on battery"
        lines.append(f"**Battery**: {battery.get('percent', '?')}% ({status})")

    # Top CPU hogs
    if top:
        lines.append("\n**Top processes by CPU:**")
        for p in top[:5]:
            lines.append(
                f"  - {p.get('name', '?')} (PID {p.get('pid', '?')}): "
                f"CPU {p.get('cpu_percent', 0):.1f}%, "
                f"MEM {p.get('memory_percent', 0):.1f}%"
            )

    # Alerts
    alerts = s.get("alerts", [])
    if alerts:
        lines.append("\n⚠️ **Alerts:**")
        for a in alerts:
            lines.append(f"  - {a.get('msg', '')}")

    return "\n".join(lines)

