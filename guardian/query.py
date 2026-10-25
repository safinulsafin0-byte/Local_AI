"""
Guardian Query Tool: Answers PC security, performance, process, and network questions
grounded entirely in Guardian monitor telemetry and psutil (NO web search).
"""

import psutil
from typing import Dict, Any, List
from guardian.monitor import get_guardian


def handle_guardian_query(query: str) -> str:
    q = query.lower()
    guardian = get_guardian()
    status = guardian.get_status()
    alerts = guardian.alerts

    # 1. Suspicious activity / security alerts / status
    if any(k in q for k in ["suspicious", "security", "alert", "threat", "hack", "infection", "safe", "virus"]):
        recent_alerts = [a for a in alerts if a.get("status") in ("new", "active")]
        if not recent_alerts:
            return (
                f"🛡️ Guardian Security Monitor Status: OK\n\n"
                f"• No active suspicious alerts detected on this system.\n"
                f"• Monitored areas: Processes (%TEMP%, Downloads, spoofing), Listening Ports, Autostarts, Ransomware Watcher, and Windows Defender.\n"
                f"• Limited mode: {'Yes (Admin required for some security event logs)' if status.get('limited_mode') else 'No'}\n"
                f"• Whitelisted entries: {status.get('whitelist_count')}\n"
                f"Everything appears normal."
            )
        else:
            lines = [f"🛡️ Guardian Security Monitor: Found {len(recent_alerts)} suspicious alert(s):\n"]
            for a in recent_alerts[:5]:
                lines.append(f"• [{a['severity'].upper()}] {a['title']}: {a['reason']}")
                det = a.get("details", {})
                if "path" in det:
                    lines.append(f"  Path: {det['path']}")
                if "pid" in det:
                    lines.append(f"  PID: {det['pid']}")
                if "port" in det:
                    lines.append(f"  Port: {det['port']}")
            return "\n".join(lines)

    # 2. What is <process> doing? (e.g. "what is python.exe doing?")
    if "doing" in q or "process" in q or "running" in q:
        target_name = None
        for word in q.replace("?", "").replace("'", "").replace('"', "").split():
            if word.endswith(".exe") or word in ["python", "node", "chrome", "code", "ollama", "discord", "powershell"]:
                target_name = word.lower()
                if not target_name.endswith(".exe"):
                    target_name += ".exe"
                break

        if target_name:
            matches = []
            for p in psutil.process_iter(['pid', 'name', 'exe', 'cpu_percent', 'memory_info']):
                try:
                    if (p.info.get('name') or '').lower() == target_name:
                        matches.append(p)
                except Exception:
                    pass

            if not matches:
                return f"Process '{target_name}' is currently not running on this system."

            lines = [f"📊 Process details for '{target_name}' ({len(matches)} instance(s) running):"]
            for p in matches[:4]:
                try:
                    mem_mb = (p.info.get('memory_info').rss / (1024*1024)) if p.info.get('memory_info') else 0
                    cpu_p = p.cpu_percent(interval=0.1)
                    exe_p = p.info.get('exe', 'Unknown path')
                    lines.append(f"• PID {p.pid}: CPU {cpu_p:.1f}%, RAM {mem_mb:.1f} MB, Path: {exe_p}")
                except Exception:
                    lines.append(f"• PID {p.pid}: Running")
            return "\n".join(lines)

    # 3. What is using my network? / network connections / ports
    if any(k in q for k in ["network", "port", "internet", "bandwidth", "connection"]):
        listeners = []
        for c in psutil.net_connections(kind='inet'):
            try:
                if c.status == 'LISTEN' and c.laddr:
                    proc_name = psutil.Process(c.pid).name() if c.pid else "Unknown"
                    listeners.append((c.laddr.port, proc_name, c.pid))
            except Exception:
                pass
        listeners = sorted(list(set(listeners)), key=lambda x: x[0])[:10]
        lines = ["🌐 Network Activity & Listening Ports:"]
        for port, pname, pid in listeners:
            lines.append(f"• Port {port}: {pname} (PID {pid})")
        return "\n".join(lines)

    # 4. Why is my PC slow? / CPU load
    if any(k in q for k in ["slow", "lag", "cpu", "ram", "memory", "heavy", "freeze"]):
        cpu = psutil.cpu_percent(interval=0.3)
        mem = psutil.virtual_memory()
        procs = []
        for p in psutil.process_iter(['pid', 'name', 'cpu_percent', 'memory_info']):
            try:
                name = p.info.get('name') or ''
                if name.lower() in ("system idle process", "idle"):
                    continue
                procs.append((p.info.get('cpu_percent') or 0.0, p.info.get('name'), p.pid))
            except Exception:
                pass
        procs.sort(reverse=True)
        lines = [
            f"⚡ System Performance Status:\n",
            f"• Overall CPU Usage: {cpu:.1f}%",
            f"• RAM Usage: {mem.percent:.1f}% ({mem.used / (1024**3):.1f} GB / {mem.total / (1024**3):.1f} GB)",
            f"\nTop CPU Consumers:"
        ]
        for cp, name, pid in procs[:5]:
            lines.append(f"• {name} (PID {pid}): {cp:.1f}%")
        return "\n".join(lines)

    # Default Guardian summary
    return (
        f"🛡️ Guardian Security Monitor:\n"
        f"• Status: {'Active' if guardian.enabled and not guardian.paused else 'Paused'}\n"
        f"• Total alerts recorded: {status.get('total_alerts')}\n"
        f"• Unread alerts: {status.get('unread_alerts')}\n"
        f"• Whitelisted entries: {status.get('whitelist_count')}\n"
        f"• Guardian footprint: {status.get('guardian_cpu_pct')}% CPU, {status.get('guardian_mem_mb')} MB RAM"
    )

