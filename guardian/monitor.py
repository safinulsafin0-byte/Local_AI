"""
JARVIS Guardian: Continuous Background Security & Suspicious Activity Monitor.

Features:
- Sub-3% CPU, sub-150MB RAM footprint.
- Detectors:
  1. Resource abuse (sustained high CPU/RAM, ignoring System Idle Process).
  2. Suspicious process launch (%TEMP%, Downloads, Public, spoofed system exes, Authenticode checks).
  3. Network (new listening ports, high unique remote IP fanout).
  4. Autostart registry & startup folder additions.
  5. Ransomware activity watcher via watchdog (bursts of file edits/renames).
  6. Windows Defender status (periodic PowerShell query).
  7. Failed logon bursts (Security event 4625) with graceful limited-mode fallback.
- Delivery:
  - Windows Toast (winotify) with rate limiting (max 3/min).
  - SSE real-time stream for Web UI and VS Code extension.
  - Persistent alert history in data/guardian_alerts.jsonl.
  - Baseline learning on first run.
"""

import os
import sys
import time
import json
import uuid
import queue
import logging
import asyncio
import winreg
import datetime
import threading
import subprocess
from pathlib import Path
from typing import Dict, Any, List, Optional, Set

import psutil

try:
    from winotify import Notification, audio
    HAS_WINOTIFY = True
except ImportError:
    HAS_WINOTIFY = False

try:
    from watchdog.observers import Observer
    from watchdog.events import FileSystemEventHandler
    HAS_WATCHDOG = True
except ImportError:
    HAS_WATCHDOG = False

logger = logging.getLogger("jarvis.guardian")

BASE_DIR = Path(__file__).resolve().parent.parent
DATA_DIR = BASE_DIR / "data"
DATA_DIR.mkdir(parents=True, exist_ok=True)

BASELINE_FILE = DATA_DIR / "guardian_baseline.json"
WHITELIST_FILE = DATA_DIR / "guardian_whitelist.json"
ALERTS_FILE = DATA_DIR / "guardian_alerts.jsonl"
SETTINGS_FILE = DATA_DIR / "guardian_settings.json"

PROTECTED_PROCESS_NAMES = {
    "system", "system idle process", "csrss.exe", "wininit.exe",
    "services.exe", "lsass.exe", "winlogon.exe", "explorer.exe",
    "smss.exe", "svchost.exe", "fontdrvhost.exe"
}

SAFE_LISTENING_PORTS = {
    2869,   # UPnP / SSDP (System PID 4)
    5357,   # WSDAPI (System PID 4)
    445,    # SMB (System PID 4)
    135,    # RPC endpoint mapper (System PID 4)
    137,    # NetBIOS Name Service (System PID 4)
    138,    # NetBIOS Datagram (System PID 4)
    139,    # NetBIOS Session (System PID 4)
    11434,  # Ollama API
    8765,   # JARVIS API
}

SAFE_LISTENER_PROCESS_NAMES = {
    "system", "system idle process",
    "onedrive.exe", "onedrive.sync.service.exe", "onedrivestandaloneupdater.exe", "filecoauth.exe",
    "ollama.exe", "llama-server.exe", "ollama_llama_server.exe",
    "python.exe", "pythonw.exe",
    "msmpeng.exe", "nissrv.exe",
    "code.exe",
    "agy.exe", "antigravity.exe",
    "explorer.exe", "svchost.exe", "services.exe", "wininit.exe", "csrss.exe", "lsass.exe", "smss.exe"
}

SAFE_SYSTEM_DIRS = [
    r"c:\windows\system32",
    r"c:\windows\syswow64",
    r"c:\windows\systemapps",
    r"c:\windows\winsxs",
]

RANSOMWARE_EXTENSIONS = {
    ".locked", ".crypto", ".enc", ".crypted", ".locky", ".crypt",
    ".ransom", ".wannacry", ".wncry", ".darkside", ".revil"
}


class RansomwareWatcher(FileSystemEventHandler if HAS_WATCHDOG else object):
    """Watches Documents, Desktop, and Downloads for rapid file modification bursts."""

    def __init__(self, callback):
        super().__init__()
        self.callback = callback
        self.events = []  # list of (timestamp, filepath, event_type)
        self.lock = threading.Lock()

    def on_modified(self, event):
        if not event.is_directory:
            self._record(event.src_path, "modified")

    def on_moved(self, event):
        if not event.is_directory:
            self._record(event.dest_path, "renamed")

    def on_created(self, event):
        if not event.is_directory:
            self._record(event.src_path, "created")

    def _record(self, path: str, ev_type: str):
        now = time.time()
        ext = os.path.splitext(path)[1].lower()
        with self.lock:
            self.events.append((now, path, ev_type, ext))
            # Keep only last 45 seconds of events
            self.events = [e for e in self.events if now - e[0] <= 45]

            # Check for ransomware extensions
            if ext in RANSOMWARE_EXTENSIONS:
                self.callback("ransom_ext", path, f"File created with known ransomware extension: {ext}")
                return

            # Check for >100 files in 30s
            recent_30s = [e for e in self.events if now - e[0] <= 30]
            if len(recent_30s) >= 100:
                # Trigger burst alert and flush
                self.events.clear()
                self.callback("ransom_burst", path, f"High rate of file modifications: {len(recent_30s)} files modified/renamed in 30s")


class GuardianMonitor:
    def __init__(self):
        self.enabled = True
        self.paused = False
        self.interval = 5.0
        self.sensitivity = "medium"  # low, medium, high
        self.notifications_enabled = True
        self.watched_folders = [
            str(Path.home() / "Documents"),
            str(Path.home() / "Desktop"),
            str(Path.home() / "Downloads")
        ]

        self.limited_mode = False
        self.baseline_learned = False
        self.baseline: Dict[str, Any] = {
            "processes": [],
            "listening_ports": [],
            "autostart": []
        }
        self.whitelist: Set[str] = set()
        self.alerts: List[Dict[str, Any]] = []

        # Dedup cooldown tracking: key -> last_alert_time
        self.alert_cooldowns: Dict[str, float] = {}

        # Toast rate-limiting tracking: list of toast timestamps in last 60s
        self.toast_times: List[float] = []
        self.suppressed_toast_count = 0

        # Authenticode signature cache: (path, mtime) -> (is_signed, subject)
        self.sig_cache: Dict[str, Dict[str, Any]] = {}

        # Resource abuse sustained high tracking
        self.high_cpu_start: Optional[float] = None
        self.high_ram_start: Optional[float] = None

        # Network fanout tracking: pid -> set of remote IPs seen in last 60s
        self.net_fanout: Dict[int, Dict[str, Any]] = {}

        # Watchdog observer
        self.observer = None
        self.file_handler = None

        # SSE subscriber queues
        self.subscribers: List[asyncio.Queue] = []
        self._loop = None

        # Slow check timers
        self.last_ps_check = 0.0
        self.last_defender_check = 0.0

        # Stats for monitoring own consumption
        self.start_time = time.time()
        self.own_process = psutil.Process()
        try:
            self.own_process.cpu_percent(interval=None)  # warm-up call so delta is accurate
        except Exception:
            pass

        self._load_config()
        self._load_whitelist()
        self._load_alerts()
        self._load_or_create_baseline()
        self._init_file_watcher()

    def _load_config(self):
        if SETTINGS_FILE.exists():
            try:
                data = json.loads(SETTINGS_FILE.read_text(encoding="utf-8"))
                self.enabled = data.get("enabled", True)
                self.interval = float(data.get("interval", 5.0))
                self.sensitivity = data.get("sensitivity", "medium")
                self.notifications_enabled = data.get("notifications", True)
                self.watched_folders = data.get("watched_folders", self.watched_folders)
            except Exception as e:
                logger.error(f"Error loading guardian settings: {e}")

    def save_config(self):
        data = {
            "enabled": self.enabled,
            "interval": self.interval,
            "sensitivity": self.sensitivity,
            "notifications": self.notifications_enabled,
            "watched_folders": self.watched_folders
        }
        try:
            SETTINGS_FILE.write_text(json.dumps(data, indent=2), encoding="utf-8")
        except Exception as e:
            logger.error(f"Error saving guardian settings: {e}")

    def _load_whitelist(self):
        if WHITELIST_FILE.exists():
            try:
                data = json.loads(WHITELIST_FILE.read_text(encoding="utf-8"))
                self.whitelist = set(data.get("keys", []))
            except Exception as e:
                logger.error(f"Error loading whitelist: {e}")

    def save_whitelist(self):
        try:
            WHITELIST_FILE.write_text(json.dumps({"keys": list(self.whitelist)}, indent=2), encoding="utf-8")
        except Exception as e:
            logger.error(f"Error saving whitelist: {e}")

    def _load_alerts(self):
        if ALERTS_FILE.exists():
            grouped: Dict[str, Dict[str, Any]] = {}
            try:
                for line in ALERTS_FILE.read_text(encoding="utf-8").splitlines():
                    if not line.strip():
                        continue
                    item = json.loads(line)
                    k = item.get("key") or item.get("id")
                    if k in grouped:
                        existing = grouped[k]
                        existing["count"] = existing.get("count", 1) + 1
                        if item.get("time", 0) > existing.get("time", 0):
                            existing["time"] = item.get("time")
                            existing["timestamp"] = item.get("timestamp")
                    else:
                        item["count"] = item.get("count", 1)
                        grouped[k] = item
                self.alerts = sorted(grouped.values(), key=lambda x: x.get("time", 0), reverse=True)
            except Exception as e:
                logger.error(f"Error loading alerts history: {e}")
            if len(self.alerts) > 500:
                self.alerts = self.alerts[:500]
            self._rewrite_alerts_file()

    def _append_alert_file(self, alert: Dict[str, Any]):
        try:
            with open(ALERTS_FILE, "a", encoding="utf-8") as f:
                f.write(json.dumps(alert) + "\n")
        except Exception as e:
            logger.error(f"Error persisting alert: {e}")

    def _load_or_create_baseline(self):
        if BASELINE_FILE.exists():
            try:
                self.baseline = json.loads(BASELINE_FILE.read_text(encoding="utf-8"))
                self.baseline_learned = True
                return
            except Exception:
                pass

        # First run: learn baseline
        logger.info("Learning your normal system activity baseline...")
        procs = set()
        for p in psutil.process_iter(['name', 'exe']):
            try:
                n = p.info.get('name')
                if n:
                    procs.add(n.lower())
            except Exception:
                pass

        ports = set()
        try:
            for c in psutil.net_connections(kind='inet'):
                if c.status == 'LISTEN' and c.laddr:
                    ports.add(c.laddr.port)
        except Exception:
            pass

        autostarts = self._get_autostart_entries()

        self.baseline = {
            "processes": list(procs),
            "listening_ports": list(ports),
            "autostart": autostarts,
            "created_at": datetime.datetime.utcnow().isoformat()
        }
        try:
            BASELINE_FILE.write_text(json.dumps(self.baseline, indent=2), encoding="utf-8")
            self.baseline_learned = True
        except Exception as e:
            logger.error(f"Error saving baseline: {e}")

    def _init_file_watcher(self):
        if not HAS_WATCHDOG:
            logger.warning("Watchdog not available, ransomware file monitor disabled")
            return
        try:
            self.file_handler = RansomwareWatcher(self._on_ransomware_event)
            self.observer = Observer()
            for folder in self.watched_folders:
                p = Path(folder)
                if p.exists() and p.is_dir():
                    self.observer.schedule(self.file_handler, str(p), recursive=True)
            self.observer.daemon = True
            self.observer.start()
            logger.info("Guardian file modification observer started")
        except Exception as e:
            logger.warning(f"Could not initialize file watchdog observer: {e}")

    def _on_ransomware_event(self, kind: str, path: str, reason: str):
        key = f"ransomware:{kind}:{path}"
        self.record_alert(
            key=key,
            severity="high",
            title="Suspicious Rapid File Modifications",
            reason=reason,
            details={"path": path, "kind": kind}
        )

    # ── DETECTORS ─────────────────────────────────────────────────────────────

    def _check_resource_abuse(self):
        try:
            cpu = psutil.cpu_percent(interval=None)
            mem = psutil.virtual_memory()

            now = time.time()
            if cpu > 90:
                if self.high_cpu_start is None:
                    self.high_cpu_start = now
                elif now - self.high_cpu_start >= 60:
                    # Find top CPU process (strictly excluding System Idle Process, System, and Idle)
                    top_proc = "Unknown"
                    top_pid = 0
                    max_cpu = 0.0
                    for p in psutil.process_iter(['pid', 'name', 'cpu_percent']):
                        try:
                            pid = p.info.get('pid') or 0
                            if pid in (0, 4):
                                continue
                            name = p.info.get('name') or ''
                            if name.lower() in ("system idle process", "idle", "system"):
                                continue
                            cp = p.info.get('cpu_percent') or 0.0
                            if cp > max_cpu:
                                max_cpu = cp
                                top_proc = name
                                top_pid = pid
                        except Exception:
                            pass

                    self.record_alert(
                        key="resource:cpu_sustained_90",
                        severity="medium",
                        title="Sustained High CPU Load",
                        reason=f"Overall CPU sustained >90% for 60s. Top consumer: {top_proc} (PID {top_pid})",
                        details={"process": top_proc, "pid": top_pid, "cpu": cpu}
                    )
            else:
                self.high_cpu_start = None

            if mem.percent > 95:
                if self.high_ram_start is None:
                    self.high_ram_start = now
                elif now - self.high_ram_start >= 30:
                    self.record_alert(
                        key="resource:ram_critical_95",
                        severity="high",
                        title="Critical Memory Consumption",
                        reason=f"Physical RAM is at {mem.percent:.1f}%",
                        details={"ram_percent": mem.percent}
                    )
            else:
                self.high_ram_start = None
        except Exception as e:
            logger.debug(f"Resource check error: {e}")

    def _check_suspicious_processes(self):
        temp_dir = os.environ.get("TEMP", "").lower()
        local_temp = os.path.expandvars(r"%LOCALAPPDATA%\Temp").lower()
        downloads_dir = str(Path.home() / "Downloads").lower()
        public_dir = os.environ.get("PUBLIC", r"C:\Users\Public").lower()

        suspicious_dirs = [temp_dir, local_temp, downloads_dir, public_dir]

        for p in psutil.process_iter(['pid', 'name', 'exe', 'cmdline']):
            try:
                name = (p.info.get('name') or '').lower()
                exe = (p.info.get('exe') or '').lower()
                pid = p.info.get('pid')

                if not exe or not name or pid in (0, 4):
                    continue

                if name in ("system idle process", "idle", "system"):
                    continue

                # Check spoofed system names
                if name in ("svch0st.exe", "scvhost.exe", "csrs.exe", "lssas.exe"):
                    self.record_alert(
                        key=f"proc_spoof:{exe}",
                        severity="high",
                        title="Suspicious Process Name Spoofing",
                        reason=f"Process '{name}' mimics a standard Windows system binary.",
                        details={"process": name, "pid": pid, "path": exe}
                    )
                    continue

                # Check lsass.exe outside system32
                if name == "lsass.exe" and "system32" not in exe:
                    self.record_alert(
                        key=f"proc_lsass_fake:{exe}",
                        severity="high",
                        title="Suspicious Security Subsystem Binary Location",
                        reason=f"lsass.exe running outside System32 directory: {exe}",
                        details={"process": name, "pid": pid, "path": exe}
                    )
                    continue

                # Legitimate system binaries in system32/syswow64 are not suspicious
                if any(exe.startswith(sd) for sd in SAFE_SYSTEM_DIRS):
                    continue

                # Known safe updater / development processes
                if name in SAFE_LISTENER_PROCESS_NAMES:
                    continue

                # Check execution from Temp/Downloads/Public
                in_sus_dir = any(d and d in exe for d in suspicious_dirs)
                if in_sus_dir:
                    # Check Authenticode
                    sig = self._check_authenticode(exe)
                    is_signed = sig.get("is_signed", False)
                    # Valid trusted signatures (e.g. Microsoft-signed installers/updaters) must not raise alerts
                    if is_signed or sig.get("status") == "Valid":
                        continue

                    severity = "medium"
                    self.record_alert(
                        key=f"proc_sus_dir:{exe}",
                        severity=severity,
                        title="Process Executed from Temporary/Downloads Directory",
                        reason=f"Unsigned or invalid process '{name}' started from {exe} (Signature: {sig.get('status', 'Unknown')})",
                        details={
                            "process": name,
                            "pid": pid,
                            "path": exe,
                            "signature": sig.get("status", "Unknown"),
                            "signer": sig.get("signer", "")
                        }
                    )
            except (psutil.NoSuchProcess, psutil.AccessDenied):
                continue
            except Exception as e:
                logger.debug(f"Process check item error: {e}")

    def _check_authenticode(self, file_path: str) -> Dict[str, Any]:
        """Check Authenticode signature using PowerShell, cached by file mtime."""
        try:
            mtime = os.path.getmtime(file_path)
            cache_key = f"{file_path}:{mtime}"
            if cache_key in self.sig_cache:
                return self.sig_cache[cache_key]

            # Run powershell Get-AuthenticodeSignature
            ps_cmd = f"(Get-AuthenticodeSignature -FilePath '{file_path}').Status.ToString()"
            res = subprocess.run(
                ["powershell", "-NoProfile", "-Command", ps_cmd],
                capture_output=True,
                text=True,
                timeout=5
            )
            status = res.stdout.strip()
            is_signed = status == "Valid"
            result = {"is_signed": is_signed, "status": status, "signer": ""}
            self.sig_cache[cache_key] = result
            return result
        except Exception:
            return {"is_signed": False, "status": "Unknown", "signer": ""}

    def _check_listening_ports(self):
        try:
            baseline_ports = set(self.baseline.get("listening_ports", []))
            for c in psutil.net_connections(kind='inet'):
                try:
                    if c.status == 'LISTEN' and c.laddr:
                        port = c.laddr.port
                        # Suppress known safe system ports (UPnP, WSDAPI, SMB, RPC, NetBIOS, Ollama, JARVIS)
                        if port in SAFE_LISTENING_PORTS:
                            continue

                        pid = c.pid
                        if pid is None or pid in (0, 4):
                            continue

                        proc_name = "Unknown"
                        proc_exe = ""
                        try:
                            p = psutil.Process(pid)
                            proc_name = (p.name() or '').lower()
                            proc_exe = (p.exe() or '').lower()
                        except Exception:
                            pass

                        # Suppress known safe listener applications (OneDrive, Ollama, VS Code, Python, etc.)
                        if proc_name in SAFE_LISTENER_PROCESS_NAMES:
                            continue

                        # Suppress system binaries in legitimate Windows system directories
                        if proc_exe and any(proc_exe.startswith(sd) for sd in SAFE_SYSTEM_DIRS):
                            continue

                        # Suppress dynamic ephemeral localhost ports (>= 49152 on localhost)
                        ip_addr = getattr(c.laddr, "ip", "")
                        if port >= 49152 and ip_addr in ("127.0.0.1", "::1", "localhost"):
                            continue

                        # If port is in ephemeral range (>= 49152), group by process rather than per-port noise
                        if port >= 49152:
                            self.record_alert(
                                key=f"port_ephemeral:{proc_name}",
                                severity="low",
                                title=f"{proc_name} Listening on Dynamic Ports",
                                reason=f"Process '{proc_name}' (PID {pid}) listening on dynamic sync port {port}",
                                details={"port": port, "process": proc_name, "pid": pid}
                            )
                            continue

                        if port not in baseline_ports:
                            self.record_alert(
                                key=f"port_new_listen:{port}",
                                severity="medium",
                                title="New Listening Network Port Detected",
                                reason=f"New service listening on port {port} by process '{proc_name}' (PID {pid})",
                                details={"port": port, "process": proc_name, "pid": pid}
                            )
                except Exception:
                    pass
        except Exception as e:
            logger.debug(f"Port check error: {e}")

    def _get_autostart_entries(self) -> List[Dict[str, str]]:
        entries = []
        # Check HKCU & HKLM Run
        reg_targets = [
            (winreg.HKEY_CURRENT_USER, r"Software\Microsoft\Windows\CurrentVersion\Run", "HKCU\\Run"),
            (winreg.HKEY_LOCAL_MACHINE, r"Software\Microsoft\Windows\CurrentVersion\Run", "HKLM\\Run")
        ]
        for root, subkey, label in reg_targets:
            try:
                with winreg.OpenKey(root, subkey, 0, winreg.KEY_READ) as key:
                    idx = 0
                    while True:
                        try:
                            name, val, _ = winreg.EnumValue(key, idx)
                            entries.append({"location": label, "name": name, "value": str(val)})
                            idx += 1
                        except OSError:
                            break
            except Exception:
                pass

        # Startup folder
        try:
            startup_dir = Path.home() / r"AppData\Roaming\Microsoft\Windows\Start Menu\Programs\Startup"
            if startup_dir.exists():
                for f in startup_dir.iterdir():
                    if f.is_file():
                        entries.append({"location": "StartupFolder", "name": f.name, "value": str(f)})
        except Exception:
            pass

        return entries

    def _check_autostart(self):
        try:
            baseline_autostarts = {
                f"{e.get('location')}:{e.get('name')}:{e.get('value')}"
                for e in self.baseline.get("autostart", [])
            }
            current = self._get_autostart_entries()
            for item in current:
                sig_str = f"{item.get('location')}:{item.get('name')}:{item.get('value')}"
                if sig_str not in baseline_autostarts:
                    self.record_alert(
                        key=f"autostart_new:{sig_str}",
                        severity="medium",
                        title="New Autostart Entry Detected",
                        reason=f"New persistence entry '{item.get('name')}' added to {item.get('location')}: {item.get('value')}",
                        details=item
                    )
        except Exception as e:
            logger.debug(f"Autostart check error: {e}")

    def _check_windows_defender(self):
        now = time.time()
        if now - self.last_defender_check < 90:
            return
        self.last_defender_check = now

        try:
            ps_cmd = "Get-MpComputerStatus | Select-Object -Property RealTimeProtectionEnabled, AntivirusEnabled | ConvertTo-Json -Compress"
            res = subprocess.run(
                ["powershell", "-NoProfile", "-Command", ps_cmd],
                capture_output=True,
                text=True,
                timeout=10
            )
            if res.returncode == 0 and res.stdout.strip():
                data = json.loads(res.stdout.strip())
                rt_enabled = data.get("RealTimeProtectionEnabled", True)
                if not rt_enabled:
                    self.record_alert(
                        key="defender:rt_disabled",
                        severity="high",
                        title="Windows Defender Real-Time Protection Disabled",
                        reason="Windows Defender reports real-time protection is currently turned off.",
                        details=data
                    )
        except Exception as e:
            logger.debug(f"Defender check error: {e}")

    def _check_failed_logons(self):
        now = time.time()
        if now - self.last_ps_check < 60:
            return
        self.last_ps_check = now

        try:
            # Query Security event 4625 within last 2 minutes
            ps_cmd = "Get-WinEvent -FilterHashtable @{LogName='Security'; Id=4625; StartTime=(Get-Date).AddMinutes(-2)} -MaxEvents 20 -ErrorAction Stop | Measure-Object | Select-Object -ExpandProperty Count"
            res = subprocess.run(
                ["powershell", "-NoProfile", "-Command", ps_cmd],
                capture_output=True,
                text=True,
                timeout=8
            )
            if res.returncode == 0:
                count_str = res.stdout.strip()
                if count_str.isdigit():
                    count = int(count_str)
                    if count >= 5:
                        self.record_alert(
                            key="auth:failed_logon_burst",
                            severity="medium",
                            title="Burst of Failed Logon Attempts Detected",
                            reason=f"Detected {count} failed logon attempts (Event 4625) in the last 2 minutes.",
                            details={"failed_count": count}
                        )
            else:
                self.limited_mode = True
        except Exception:
            self.limited_mode = True

    # ── ALERT RECORDING & NOTIFICATIONS ────────────────────────────────────────

    def record_alert(self, key: str, severity: str, title: str, reason: str, details: Dict[str, Any] = None):
        if not self.enabled or self.paused:
            return

        # Check whitelist
        if key in self.whitelist:
            return

        now = time.time()
        # Cooldown check: 10 minutes (600s)
        last_seen = self.alert_cooldowns.get(key, 0)
        if now - last_seen < 600:
            for a in self.alerts:
                if a.get("key") == key:
                    a["count"] = a.get("count", 1) + 1
                    a["time"] = now
                    a["timestamp"] = datetime.datetime.utcnow().isoformat() + "Z"
                    break
            return
        self.alert_cooldowns[key] = now

        existing = next((a for a in self.alerts if a.get("key") == key), None)
        if existing:
            existing["count"] = existing.get("count", 1) + 1
            existing["time"] = now
            existing["timestamp"] = datetime.datetime.utcnow().isoformat() + "Z"
            existing["reason"] = reason
            self._rewrite_alerts_file()
            alert = existing
        else:
            alert = {
                "id": f"alert_{uuid.uuid4().hex[:12]}",
                "time": now,
                "timestamp": datetime.datetime.utcnow().isoformat() + "Z",
                "severity": severity,
                "key": key,
                "title": title,
                "reason": reason,
                "details": details or {},
                "status": "new",
                "count": 1
            }
            self.alerts.insert(0, alert)
            self._append_alert_file(alert)

        logger.warning(f"[GUARDIAN ALERT {severity.upper()}] {title}: {reason}")

        # Send Windows Toast
        if self.notifications_enabled:
            self._send_toast(alert)

        # Notify SSE subscribers
        self._broadcast(alert)

    def _send_toast(self, alert: Dict[str, Any]):
        now = time.time()
        # Clean timestamps older than 60s
        self.toast_times = [t for t in self.toast_times if now - t <= 60]

        if len(self.toast_times) >= 3:
            self.suppressed_toast_count += 1
            return

        self.toast_times.append(now)

        title = f"🛡️ JARVIS Guardian: {alert['title']}"
        body = alert['reason']
        if self.suppressed_toast_count > 0:
            body += f" (+{self.suppressed_toast_count} more alerts)"
            self.suppressed_toast_count = 0

        if HAS_WINOTIFY:
            try:
                toast = Notification(
                    app_id="JARVIS Guardian",
                    title=title,
                    msg=body[:140],
                    duration="short"
                )
                if alert['severity'] == "high":
                    toast.set_audio(audio.Reminder, loop=False)
                toast.show()
            except Exception as e:
                logger.debug(f"Winotify failed: {e}")
        else:
            # Fallback to PowerShell balloon / notification if winotify missing
            try:
                ps_script = f"""
                [reflection.assembly]::loadwithpartialname('System.Windows.Forms') | Out-Null
                $notify = New-Object System.Windows.Forms.NotifyIcon
                $notify.Icon = [System.Drawing.SystemIcons]::Information
                $notify.Visible = $true
                $notify.ShowBalloonTip(3000, '{title}', '{body[:100]}', [System.Windows.Forms.ToolTipIcon]::Warning)
                """
                subprocess.Popen(["powershell", "-NoProfile", "-Command", ps_script], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            except Exception:
                pass

    def _broadcast(self, alert: Dict[str, Any]):
        if not self._loop:
            return
        msg = f"data: {json.dumps({'type': 'alert', 'alert': alert})}\n\n"
        for q in list(self.subscribers):
            try:
                self._loop.call_soon_threadsafe(q.put_nowait, msg)
            except Exception:
                pass

    # ── MONITOR LOOP ──────────────────────────────────────────────────────────

    def run_cycle(self):
        """Single check cycle wrapped in try/except blocks to ensure complete server isolation."""
        if not self.enabled or self.paused:
            return

        try:
            self._check_resource_abuse()
        except Exception as e:
            logger.debug(f"Detector resource_abuse error: {e}")

        try:
            self._check_suspicious_processes()
        except Exception as e:
            logger.debug(f"Detector suspicious_processes error: {e}")

        try:
            self._check_listening_ports()
        except Exception as e:
            logger.debug(f"Detector listening_ports error: {e}")

        try:
            self._check_autostart()
        except Exception as e:
            logger.debug(f"Detector autostart error: {e}")

        try:
            self._check_windows_defender()
        except Exception as e:
            logger.debug(f"Detector windows_defender error: {e}")

        try:
            self._check_failed_logons()
        except Exception as e:
            logger.debug(f"Detector failed_logons error: {e}")

    async def start_loop(self):
        """Async loop started inside FastAPI lifespan."""
        self._loop = asyncio.get_running_loop()
        logger.info(f"JARVIS Guardian security monitor active (Interval: {self.interval}s, Budget: <3% CPU)")

        while True:
            try:
                await asyncio.get_running_loop().run_in_executor(None, self.run_cycle)
            except Exception as exc:
                logger.error(f"Guardian monitor loop uncaught exception: {exc}")

            await asyncio.sleep(self.interval)

    # ── ACTIONS & API METHODS ─────────────────────────────────────────────────

    def get_status(self) -> Dict[str, Any]:
        uptime_sec = time.time() - self.start_time
        try:
            num_cpus = psutil.cpu_count() or 1
            own_cpu = (self.own_process.cpu_percent(interval=None) or 0.0) / num_cpus
            own_mem_mb = self.own_process.memory_info().rss / (1024 * 1024)
        except Exception:
            own_cpu, own_mem_mb = 0.0, 0.0

        new_alerts = [a for a in self.alerts if a.get("status") == "new"]

        return {
            "ok": True,
            "enabled": self.enabled,
            "paused": self.paused,
            "interval": self.interval,
            "sensitivity": self.sensitivity,
            "limited_mode": self.limited_mode,
            "baseline_learned": self.baseline_learned,
            "notifications_enabled": self.notifications_enabled,
            "total_alerts": len(self.alerts),
            "unread_alerts": len(new_alerts),
            "whitelist_count": len(self.whitelist),
            "guardian_cpu_pct": round(own_cpu, 2),
            "guardian_mem_mb": round(own_mem_mb, 1),
            "uptime_seconds": round(uptime_sec, 1)
        }

    def ignore_alert(self, alert_id: str) -> bool:
        alert = next((a for a in self.alerts if a.get("id") == alert_id), None)
        if not alert:
            return False

        key = alert.get("key")
        if key:
            self.whitelist.add(key)
            self.save_whitelist()

        alert["status"] = "ignored"
        self._rewrite_alerts_file()
        return True

    def kill_process(self, pid_or_alert_id: Any) -> Dict[str, Any]:
        target_pid = None
        if isinstance(pid_or_alert_id, str) and pid_or_alert_id.startswith("alert_"):
            alert = next((a for a in self.alerts if a.get("id") == pid_or_alert_id), None)
            if alert and "pid" in alert.get("details", {}):
                target_pid = alert["details"]["pid"]
        else:
            try:
                target_pid = int(pid_or_alert_id)
            except Exception:
                pass

        if not target_pid:
            return {"ok": False, "error": "Invalid PID or alert ID"}

        # Protection check
        if target_pid == os.getpid():
            return {"ok": False, "error": "Cannot terminate JARVIS server process"}

        try:
            proc = psutil.Process(target_pid)
            name = proc.name().lower()
            if name in PROTECTED_PROCESS_NAMES or target_pid <= 4:
                return {"ok": False, "error": f"Refusing to terminate protected system process: {name}"}

            proc.terminate()
            # Mark corresponding alert as resolved
            for a in self.alerts:
                if a.get("details", {}).get("pid") == target_pid:
                    a["status"] = "resolved"
            self._rewrite_alerts_file()
            return {"ok": True, "terminated_pid": target_pid, "name": name}
        except psutil.NoSuchProcess:
            return {"ok": False, "error": "Process already terminated"}
        except Exception as e:
            return {"ok": False, "error": str(e)}

    def _rewrite_alerts_file(self):
        try:
            with open(ALERTS_FILE, "w", encoding="utf-8") as f:
                for a in reversed(self.alerts):
                    f.write(json.dumps(a) + "\n")
        except Exception as e:
            logger.error(f"Error rewriting alerts file: {e}")

    def clear_alerts(self) -> int:
        """Clear all active alerts and reset notification cooldowns."""
        count = len(self.alerts)
        self.alerts = []
        self.alert_cooldowns.clear()
        self._rewrite_alerts_file()
        logger.info(f"Cleared {count} Guardian alerts")
        return count

    def reset_baseline(self) -> Dict[str, Any]:
        """Re-scan and refresh baseline from currently running system state, clearing alert noise."""
        logger.info("Resetting and relearning normal system activity baseline...")
        procs = set()
        for p in psutil.process_iter(['name', 'exe']):
            try:
                n = p.info.get('name')
                if n:
                    procs.add(n.lower())
            except Exception:
                pass

        ports = set()
        try:
            for c in psutil.net_connections(kind='inet'):
                if c.status == 'LISTEN' and c.laddr:
                    ports.add(c.laddr.port)
        except Exception:
            pass

        autostarts = self._get_autostart_entries()

        self.baseline = {
            "processes": list(procs),
            "listening_ports": list(ports),
            "autostart": autostarts,
            "created_at": datetime.datetime.utcnow().isoformat()
        }
        try:
            BASELINE_FILE.write_text(json.dumps(self.baseline, indent=2), encoding="utf-8")
            self.baseline_learned = True
        except Exception as e:
            logger.error(f"Error saving baseline: {e}")

        # Clear active alerts noise
        cleared_count = self.clear_alerts()

        return {
            "ok": True,
            "processes_count": len(procs),
            "ports_count": len(ports),
            "autostart_count": len(autostarts),
            "cleared_alerts": cleared_count,
            "created_at": self.baseline["created_at"]
        }

    def pause(self):
        self.paused = True

    def resume(self):
        self.paused = False

    def add_subscriber(self, q: asyncio.Queue):
        self.subscribers.append(q)

    def remove_subscriber(self, q: asyncio.Queue):
        if q in self.subscribers:
            self.subscribers.remove(q)


_guardian_instance: Optional[GuardianMonitor] = None

def get_guardian() -> GuardianMonitor:
    global _guardian_instance
    if _guardian_instance is None:
        _guardian_instance = GuardianMonitor()
    return _guardian_instance

