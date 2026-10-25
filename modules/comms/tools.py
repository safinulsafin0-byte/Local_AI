"""
Stark Edition - Secure Comms Relay & Notifications
==================================================
1. Native Windows Desktop notifications (safe PowerShell balloon/toast script)
2. In-memory notification log buffer
3. Offline-safe Telegram remote relay runner (strict whitelist authentication)
4. Local reminders / mission alerts manager
"""

import os
import json
import time
import uuid
import subprocess
from pathlib import Path
from typing import Dict, Any, List, Optional

REMINDERS_FILE = Path.home() / ".jarvis" / "comms_reminders.json"
REMINDERS_FILE.parent.mkdir(parents=True, exist_ok=True)

NOTIFICATION_HISTORY: List[Dict[str, Any]] = []

def send_desktop_notification(title: str, message: str, level: str = "info") -> Dict[str, Any]:
    """
    Fires an authentic Windows desktop notification and registers it in history.
    Uses non-blocking PowerShell notification script.
    """
    entry = {
        "id": str(uuid.uuid4())[:8],
        "title": title,
        "message": message,
        "level": level,
        "timestamp": time.time(),
        "delivered": False
    }

    try:
        # Safe PowerShell toast / balloon tooltip notification script
        clean_title = title.replace('"', '`"').replace("'", "`'")
        clean_msg = message.replace('"', '`"').replace("'", "`'")
        ps_script = f"""
Add-Type -AssemblyName System.Windows.Forms
$global:balloon = New-Object System.Windows.Forms.NotifyIcon
$path = (Get-Process -id $pid).Path
$balloon.Icon = [System.Drawing.Icon]::ExtractAssociatedIcon($path)
$balloon.BalloonTipIcon = [System.Windows.Forms.ToolTipIcon]::{level.capitalize() if level in ['info', 'warning', 'error'] else 'Info'}
$balloon.BalloonTipText = "{clean_msg}"
$balloon.BalloonTipTitle = "{clean_title}"
$balloon.Visible = $true
$balloon.ShowBalloonTip(3000)
Start-Sleep -Milliseconds 200
$balloon.Dispose()
"""
        subprocess.Popen(
            ["powershell", "-NoProfile", "-WindowStyle", "Hidden", "-Command", ps_script],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL
        )
        entry["delivered"] = True
    except Exception as e:
        entry["error"] = str(e)

    NOTIFICATION_HISTORY.append(entry)
    if len(NOTIFICATION_HISTORY) > 50:
        NOTIFICATION_HISTORY.pop(0)

    return {
        "ok": True,
        "notification": entry,
        "summary": f"Notification '{title}' dispatched."
    }

def get_notification_history() -> Dict[str, Any]:
    """Returns recent notification alerts."""
    return {
        "ok": True,
        "count": len(NOTIFICATION_HISTORY),
        "notifications": list(reversed(NOTIFICATION_HISTORY[-20:]))
    }

def _load_reminders() -> List[Dict[str, Any]]:
    if REMINDERS_FILE.exists():
        try:
            with open(REMINDERS_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            pass
    return []

def _save_reminders(reminders: List[Dict[str, Any]]):
    try:
        with open(REMINDERS_FILE, "w", encoding="utf-8") as f:
            json.dump(reminders, f, indent=2)
    except Exception:
        pass

def create_reminder(text: str, due_in_minutes: int = 30, priority: str = "normal") -> Dict[str, Any]:
    """Schedules a local reminder."""
    reminders = _load_reminders()
    due_ts = time.time() + (due_in_minutes * 60)
    item = {
        "id": f"rem_{int(time.time())}_{len(reminders)+1}",
        "text": text,
        "created_at": time.time(),
        "due_at": due_ts,
        "priority": priority,
        "completed": False
    }
    reminders.append(item)
    _save_reminders(reminders)
    return {
        "ok": True,
        "reminder": item,
        "summary": f"Reminder scheduled: '{text}' in {due_in_minutes} minutes."
    }

def list_reminders() -> Dict[str, Any]:
    """Lists pending and active reminders."""
    reminders = _load_reminders()
    return {
        "ok": True,
        "count": len(reminders),
        "reminders": reminders
    }

def dismiss_reminder(reminder_id: str) -> Dict[str, Any]:
    """Dismisses or marks a reminder completed."""
    reminders = _load_reminders()
    found = False
    for r in reminders:
        if r.get("id") == reminder_id:
            r["completed"] = True
            found = True
            break
    if found:
        _save_reminders(reminders)
        return {"ok": True, "message": f"Reminder {reminder_id} dismissed."}
    return {"ok": False, "error": f"Reminder {reminder_id} not found."}

def process_remote_command(chat_id: str, command_text: str) -> Dict[str, Any]:
    """
    Simulates / processes an authenticated remote command (e.g. from Telegram).
    Strictly checks authorization against allowed chat IDs.
    Supported: /status, /briefing, /protocols, /lockdown
    """
    whitelisted_id = os.environ.get("TELEGRAM_WHITELISTED_CHAT_ID", "123456789")
    if chat_id != whitelisted_id and whitelisted_id != "*":
        return {
            "ok": False,
            "error": "UNAUTHORIZED_SENDER",
            "message": f"Sender {chat_id} is not in the authorized Stark comms whitelist."
        }

    cmd = command_text.strip().lower()
    if cmd in ["/status", "status"]:
        import psutil
        cpu = psutil.cpu_percent()
        ram = psutil.virtual_memory().percent
        return {
            "ok": True,
            "command": "/status",
            "reply": f"JARVIS Nominal. CPU: {cpu}%, RAM: {ram}%, Threat Level: GREEN."
        }
    elif cmd in ["/briefing", "briefing"]:
        from modules.briefing_protocols.tools import get_proactive_briefing
        briefing = get_proactive_briefing()
        return {
            "ok": True,
            "command": "/briefing",
            "reply": briefing.get("briefing_text", "Briefing complete.")
        }
    elif cmd in ["/lockdown", "lockdown"]:
        from modules.smart_facility.tools import activate_facility_scene
        activate_facility_scene("night_lockdown")
        return {
            "ok": True,
            "command": "/lockdown",
            "reply": "Facility Night Lockdown initiated. All perimeters sealed."
        }
    else:
        return {
            "ok": True,
            "command": cmd,
            "reply": f"Command '{cmd}' received. Available remote commands: /status, /briefing, /lockdown"
        }

def health() -> Dict[str, Any]:
    return {
        "ok": True,
        "status": "Ready",
        "notifications_sent": len(NOTIFICATION_HISTORY),
        "reminders_count": len(_load_reminders())
    }

