"""
tools/pc_actions.py — Deterministic & Safe PC Control with 10s Confirmation Countdown
===================================================================================
1. Destructive actions: shutdown, restart, sleep, empty_recycle_bin, delete_file.
   - 10-second cancelable confirmation countdown.
   - Spoken warning: "Shutting down the PC in 10 seconds. Say cancel to abort."
   - Immediate cancellation if user types/says "cancel" or clicks button.
2. Non-destructive actions: volume (up/down/mute/set), brightness, lock, screenshot, open/close app.
   - Executes IMMEDIATELY without delay.
"""

from __future__ import annotations

import logging
import os
import subprocess
import threading
import time
from pathlib import Path
from typing import Any, Callable, Dict, Optional

logger = logging.getLogger("jarvis.pc_actions")

DESTRUCTIVE_ACTIONS = {
    "shutdown",
    "restart",
    "sleep",
    "empty_recycle_bin",
    "delete_file",
    "delete_folder",
}


class PendingAction:
    def __init__(self, action_id: str, action: str, details: Dict[str, Any], callback: Callable[[], Any]):
        self.action_id = action_id
        self.action = action
        self.details = details
        self.callback = callback
        self.created_at = time.time()
        self.cancelled = False
        self.executed = False
        self.timer: Optional[threading.Timer] = None


_active_pending_action: Optional[PendingAction] = None
_lock = threading.Lock()


def cancel_pending_action(action_id: Optional[str] = None) -> bool:
    """Cancels any active pending destructive action and aborts system shutdown if scheduled."""
    global _active_pending_action
    with _lock:
        if _active_pending_action and not _active_pending_action.executed:
            if action_id is None or _active_pending_action.action_id == action_id:
                _active_pending_action.cancelled = True
                if _active_pending_action.timer:
                    _active_pending_action.timer.cancel()
                if _active_pending_action.action in ("shutdown", "restart"):
                    try:
                        from tools.system_ops import cancel_shutdown
                        cancel_shutdown()
                    except Exception:
                        pass
                logger.info(f"Action {_active_pending_action.action_id} cancelled.")
                _active_pending_action = None
                return True
    return False


def confirm_pending_action(action_id: str) -> Dict[str, Any]:
    """Confirms and executes the pending action if not cancelled."""
    global _active_pending_action
    with _lock:
        if _active_pending_action and _active_pending_action.action_id == action_id and not _active_pending_action.cancelled:
            if _active_pending_action.timer:
                _active_pending_action.timer.cancel()
            _active_pending_action.executed = True
            act = _active_pending_action
            _active_pending_action = None
            try:
                res = act.callback()
                return {"ok": True, "result": str(res)}
            except Exception as exc:
                logger.error(f"Error executing pending action {action_id}: {exc}")
                return {"ok": False, "error": str(exc)}
    return {"ok": False, "error": "No matching active pending action."}


def execute_immediate_action(action: str, params: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    """Executes non-destructive PC actions immediately."""
    from tools import system_ops

    params = params or {}
    act = action.lower().strip()

    if act in ("volume_up", "vol_up"):
        steps = int(params.get("step", params.get("value", 10)))
        res = system_ops.volume_up(steps)
        return {"ok": "SUCCESS" in res, "message": res.replace("SUCCESS: ", ""), "result": res}

    if act in ("volume_down", "vol_down"):
        steps = int(params.get("step", params.get("value", 10)))
        res = system_ops.volume_down(steps)
        return {"ok": "SUCCESS" in res, "message": res.replace("SUCCESS: ", ""), "result": res}

    if act in ("volume_get", "get_volume"):
        res = system_ops.volume_get()
        return {"ok": "SUCCESS" in res, "message": res.replace("SUCCESS: ", ""), "result": res}

    if act in ("volume_mute", "mute"):
        res = system_ops.volume_mute()
        return {"ok": "SUCCESS" in res, "message": res.replace("SUCCESS: ", ""), "result": res}

    if act in ("volume_unmute", "unmute"):
        res = system_ops.volume_mute()
        return {"ok": "SUCCESS" in res, "message": res.replace("SUCCESS: ", ""), "result": res}

    if act in ("volume_set", "set_volume", "volume"):
        val = int(params.get("level", params.get("value", 50)))
        res = system_ops.volume_set(val)
        return {"ok": "SUCCESS" in res, "message": res.replace("SUCCESS: ", ""), "result": res}

    if act in ("brightness_set", "brightness"):
        val = int(params.get("value", 70))
        return {"ok": True, "message": f"Brightness set to {val}%.", "result": system_ops.brightness_set(val)}

    if act in ("lock", "lock_pc", "lock_workstation"):
        return {"ok": True, "message": "Workstation locked.", "result": system_ops.lock_workstation()}

    if act in ("screenshot", "take_screenshot"):
        res = system_ops.screenshot()
        import re
        m_p = re.search(r"saved to:\s*(.+)$", res)
        fpath = m_p.group(1).strip() if m_p else ""
        fname = Path(fpath).name if fpath else "screenshot.png"
        return {
            "ok": "SUCCESS" in res,
            "message": res.replace("SUCCESS: ", ""),
            "url": f"/data/screenshots/{fname}",
            "path": fpath,
            "result": res,
        }

    if act in ("open_app", "launch_app"):
        app = params.get("app") or params.get("name") or ""
        res = system_ops.open_app(app)
        return {"ok": "SUCCESS" in res, "message": res.replace("SUCCESS: ", ""), "result": res}

    if act in ("close_app", "kill_app"):
        app = params.get("app") or params.get("name") or ""
        res = system_ops.close_app(app)
        return {"ok": "SUCCESS" in res, "message": res.replace("SUCCESS: ", ""), "result": res}

    return {"ok": False, "error": f"Unknown immediate action: {act}"}


def schedule_destructive_action(action: str, params: Optional[Dict[str, Any]] = None, countdown_sec: int = 10) -> Dict[str, Any]:
    """Schedules a destructive action with a 10s cancelable countdown."""
    global _active_pending_action
    params = params or {}
    action_id = f"act_{int(time.time()*1000)}"

    def _execute():
        from tools import system_ops
        if action == "shutdown":
            system_ops.shutdown(delay_seconds=0)
        elif action == "restart":
            system_ops.restart(delay_seconds=0)
        elif action == "sleep":
            system_ops.sleep_pc()
        elif action == "empty_recycle_bin":
            system_ops.empty_recycle_bin()
        elif action == "delete_file":
            from tools.file_ops import delete_file
            target = params.get("path", "")
            delete_file(target)
        elif action == "delete_folder":
            from tools.file_ops import delete_folder
            target = params.get("path", "")
            delete_folder(target)

    with _lock:
        if _active_pending_action and not _active_pending_action.executed:
            if _active_pending_action.timer:
                _active_pending_action.timer.cancel()

        pending = PendingAction(action_id, action, params, _execute)
        timer = threading.Timer(countdown_sec, lambda: confirm_pending_action(action_id))
        pending.timer = timer
        _active_pending_action = pending
        timer.start()

    action_label = {
        "shutdown": "Shutting down the PC",
        "restart": "Restarting the PC",
        "sleep": "Putting the PC to sleep",
        "empty_recycle_bin": "Emptying Recycle Bin",
        "delete_file": f"Deleting file {params.get('path', '')}",
        "delete_folder": f"Deleting folder {params.get('path', '')}",
    }.get(action, f"Executing {action}")

    return {
        "ok": True,
        "action_id": action_id,
        "action": action,
        "countdown": countdown_sec,
        "label": action_label,
        "speech": f"{action_label} in {countdown_sec} seconds. Say cancel to abort.",
    }
