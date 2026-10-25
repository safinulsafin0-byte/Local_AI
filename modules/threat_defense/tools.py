"""
Stark Edition - Threat Defense (Civilian S.H.I.E.L.D. Module)
============================================================
Defensive security telemetry, port inventory, safe LAN device mapping,
and static code vulnerability scanner. Purely defensive; runs strictly
on user's local PC and consented LAN with zero offensive actions.
"""

import os
import re
import ast
import socket
import subprocess
import time
import psutil
from pathlib import Path
from typing import Dict, Any, List, Optional

WORKSPACE_DIR = Path(__file__).resolve().parent.parent.parent

# Known port descriptions and risk categorization
PORT_DIRECTORY = {
    21: ("FTP", "High - Insecure plaintext transfer"),
    22: ("SSH", "Medium - Secure shell remote access"),
    23: ("Telnet", "Critical - Unencrypted remote shell"),
    25: ("SMTP", "Low - Mail transfer"),
    53: ("DNS", "Low - Domain name resolution"),
    80: ("HTTP", "Low - Web server (unencrypted)"),
    135: ("RPC", "Medium - Windows RPC Endpoint"),
    139: ("NetBIOS", "Medium - Windows NetBIOS file sharing"),
    443: ("HTTPS", "Low - Secure Web server"),
    445: ("SMB", "Medium - Direct Windows file sharing"),
    1433: ("MSSQL", "Medium - Microsoft SQL Server"),
    3306: ("MySQL", "Medium - MySQL Database"),
    3389: ("RDP", "High - Remote Desktop Protocol"),
    5432: ("PostgreSQL", "Medium - PostgreSQL Database"),
    8000: ("Dev HTTP", "Low - Development server"),
    8080: ("HTTP Alt", "Low - Alternate Web/Proxy"),
    8765: ("JARVIS", "Internal - JARVIS Local Backend"),
    11434: ("Ollama", "Internal - Ollama Local LLM Server")
}

def audit_system_security() -> Dict[str, Any]:
    """
    Performs a non-invasive defensive security audit:
    - Windows Defender state
    - Firewall profile status (Domain, Private, Public)
    - Open listening ports & owning processes
    - Overall Defensive Readiness Score (0-100)
    """
    findings = []
    score = 100

    # 1. Windows Defender Status
    defender_active = False
    try:
        ps_cmd = "Get-MpComputerStatus | Select-Object -Property RealTimeProtectionEnabled, AntivirusEnabled | ConvertTo-Json"
        res = subprocess.run(["powershell", "-NoProfile", "-Command", ps_cmd], capture_output=True, text=True, timeout=5)
        if res.returncode == 0 and res.stdout.strip():
            import json
            data = json.loads(res.stdout)
            defender_active = bool(data.get("RealTimeProtectionEnabled", False))
            if defender_active:
                findings.append({"component": "Antivirus", "status": "Protected", "message": "Windows Defender Real-Time Protection is ACTIVE.", "severity": "good"})
            else:
                findings.append({"component": "Antivirus", "status": "Warning", "message": "Real-Time Protection is DISABLED.", "severity": "high"})
                score -= 30
    except Exception:
        findings.append({"component": "Antivirus", "status": "Unknown", "message": "Unable to query Windows Defender status.", "severity": "medium"})
        score -= 10

    # 2. Windows Firewall Status
    try:
        fw_cmd = "Get-NetFirewallProfile | Select-Object -Property Name, Enabled | ConvertTo-Json"
        res = subprocess.run(["powershell", "-NoProfile", "-Command", fw_cmd], capture_output=True, text=True, timeout=5)
        if res.returncode == 0 and res.stdout.strip():
            import json
            data = json.loads(res.stdout)
            if isinstance(data, dict):
                data = [data]
            all_fw_enabled = all(item.get("Enabled", False) for item in data)
            if all_fw_enabled:
                findings.append({"component": "Firewall", "status": "Active", "message": "Windows Firewall active on all profiles (Domain, Private, Public).", "severity": "good"})
            else:
                findings.append({"component": "Firewall", "status": "Degraded", "message": "One or more Firewall profiles are DISABLED.", "severity": "high"})
                score -= 25
    except Exception:
        findings.append({"component": "Firewall", "status": "Unknown", "message": "Unable to query Windows Firewall.", "severity": "low"})

    # 3. Listening Ports Mapping
    open_ports = []
    listening_counts = {"total": 0, "localhost_only": 0, "exposed_lan": 0}
    try:
        connections = psutil.net_connections(kind="inet")
        for conn in connections:
            if conn.status == "LISTEN":
                listening_counts["total"] += 1
                ip = conn.laddr.ip
                port = conn.laddr.port
                pid = conn.pid
                pname = "Unknown"
                if pid:
                    try:
                        pname = psutil.Process(pid).name()
                    except Exception:
                        pname = "System"

                is_local = (ip == "127.0.0.1" or ip == "::1")
                if is_local:
                    listening_counts["localhost_only"] += 1
                else:
                    listening_counts["exposed_lan"] += 1

                service_name, desc = PORT_DIRECTORY.get(port, ("Custom/Other", "Active listener"))
                open_ports.append({
                    "port": port,
                    "ip": ip,
                    "pid": pid,
                    "process": pname,
                    "service": service_name,
                    "is_localhost_only": is_local,
                    "description": desc
                })
    except Exception as e:
        findings.append({"component": "Ports", "status": "Error", "message": f"Failed to list network ports: {e}", "severity": "low"})

    # Deduplicate open ports by (ip, port)
    seen = set()
    dedup_ports = []
    for p in open_ports:
        key = (p["ip"], p["port"])
        if key not in seen:
            seen.add(key)
            dedup_ports.append(p)

    dedup_ports.sort(key=lambda x: (not x["is_localhost_only"], x["port"]))

    if listening_counts["exposed_lan"] > 5:
        score -= min(20, (listening_counts["exposed_lan"] - 5) * 4)
        findings.append({
            "component": "Network Exposure",
            "status": "Review",
            "message": f"{listening_counts['exposed_lan']} ports listening on all network interfaces (0.0.0.0).",
            "severity": "medium"
        })
    else:
        findings.append({
            "component": "Network Exposure",
            "status": "Optimal",
            "message": f"Network surface area minimal ({listening_counts['localhost_only']} localhost listeners, {listening_counts['exposed_lan']} LAN listeners).",
            "severity": "good"
        })

    final_score = max(20, min(100, score))
    threat_level = "GREEN (SECURE)" if final_score >= 80 else ("AMBER (ATTENTION NEEDED)" if final_score >= 50 else "RED (VULNERABLE)")

    return {
        "ok": True,
        "threat_level": threat_level,
        "readiness_score": final_score,
        "timestamp": time.time(),
        "summary": f"Defensive readiness at {final_score}%. Threat condition: {threat_level}.",
        "findings": findings,
        "ports_summary": listening_counts,
        "open_ports": dedup_ports[:25]
    }

def scan_local_network(consent: bool = False) -> Dict[str, Any]:
    """
    Safely inspects devices active on the local subnet via the system ARP table.
    Requires explicit user consent parameter (consent=True) before execution.
    NO aggressive port scans, NO offensive penetration. Strictly LAN device discovery.
    """
    if not consent:
        return {
            "ok": False,
            "error": "CONSENT_REQUIRED",
            "message": "Local network device discovery requires explicit confirmation. Set consent=True to proceed."
        }

    devices = []
    try:
        # Query Windows ARP cache (instant, passive, zero network packets sent)
        res = subprocess.run(["arp", "-a"], capture_output=True, text=True, timeout=5)
        lines = res.stdout.splitlines()

        for line in lines:
            line = line.strip()
            # Match pattern: 192.168.1.1   00-14-22-01-23-45   dynamic
            m = re.match(r"^(\d+\.\d+\.\d+\.\d+)\s+([0-9a-fA-F-]+)\s+(\w+)", line)
            if m:
                ip, mac, entry_type = m.groups()
                # Ignore broadcast and multicast addresses
                if ip.endswith(".255") or ip.startswith("224.") or ip.startswith("239.") or mac == "ff-ff-ff-ff-ff-ff":
                    continue

                hostname = "Unknown"
                try:
                    hostname = socket.gethostbyaddr(ip)[0]
                except Exception:
                    pass

                devices.append({
                    "ip": ip,
                    "mac": mac,
                    "type": entry_type,
                    "hostname": hostname
                })
    except Exception as e:
        return {"ok": False, "error": str(e), "message": "Failed to read ARP table."}

    return {
        "ok": True,
        "consent_verified": True,
        "device_count": len(devices),
        "devices": devices,
        "summary": f"Discovered {len(devices)} active devices on local subnet via passive ARP cache."
    }

def scan_code_security(target_dir: Optional[str] = None) -> Dict[str, Any]:
    """
    Static code analysis checking Python and JS files for risky patterns:
    - eval(), exec()
    - os.system(), subprocess with shell=True
    - Hardcoded secrets, API keys, passwords
    """
    scan_root = Path(target_dir) if target_dir else WORKSPACE_DIR
    if not scan_root.exists() or not scan_root.is_dir():
        scan_root = WORKSPACE_DIR

    issues = []
    files_scanned = 0

    SECRET_PATTERN = re.compile(r"""(?i)(?:api_key|secret|password|auth_token)\s*=\s*['"][a-zA-Z0-9_\-]{16,}['"]""")
    SHELL_PATTERN = re.compile(r"""shell\s*=\s*True""")
    EVAL_PATTERN = re.compile(r"""\b(?:eval|exec)\s*\(""")

    # Exclude virtual environments and git
    exclude_dirs = {".git", "venv", ".venv", "__pycache__", "node_modules", ".gemini"}

    for root, dirs, files in os.walk(scan_root):
        dirs[:] = [d for d in dirs if d not in exclude_dirs]
        for f in files:
            if f.endswith((".py", ".js", ".ts", ".html")):
                files_scanned += 1
                fpath = Path(root) / f
                try:
                    with open(fpath, "r", encoding="utf-8", errors="ignore") as code_file:
                        lines = code_file.readlines()
                        for idx, line in enumerate(lines, start=1):
                            line_str = line.strip()
                            if line_str.startswith("#") or line_str.startswith("//"):
                                continue

                            # Check for eval / exec
                            if EVAL_PATTERN.search(line_str) and not ("safe_eval" in line_str or "ast.literal_eval" in line_str):
                                issues.append({
                                    "file": str(fpath.relative_to(scan_root)),
                                    "line": idx,
                                    "severity": "HIGH",
                                    "type": "Code Execution Danger",
                                    "snippet": line_str[:100],
                                    "recommendation": "Avoid eval() and exec(). Use ast.literal_eval or safe parsers."
                                })

                            # Check for shell=True
                            if SHELL_PATTERN.search(line_str):
                                issues.append({
                                    "file": str(fpath.relative_to(scan_root)),
                                    "line": idx,
                                    "severity": "MEDIUM",
                                    "type": "Command Injection Risk",
                                    "snippet": line_str[:100],
                                    "recommendation": "Pass command arguments as a list without shell=True."
                                })

                            # Check for hardcoded secret keys
                            if SECRET_PATTERN.search(line_str):
                                issues.append({
                                    "file": str(fpath.relative_to(scan_root)),
                                    "line": idx,
                                    "severity": "CRITICAL",
                                    "type": "Hardcoded Credential",
                                    "snippet": re.sub(r"""['"][a-zA-Z0-9_\-]{8,}['"]""", "'********'", line_str)[:100],
                                    "recommendation": "Store credentials in environment variables or .env files."
                                })
                except Exception:
                    pass

    return {
        "ok": True,
        "files_scanned": files_scanned,
        "issues_found": len(issues),
        "issues": issues[:50],
        "summary": f"Scanned {files_scanned} files across {scan_root.name}. Found {len(issues)} potential security items."
    }

def health() -> Dict[str, Any]:
    return {
        "ok": True,
        "status": "Ready",
        "features": ["audit", "lan_inventory", "code_security"]
    }

