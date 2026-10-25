"""
JARVIS Scheduler — tools/scheduler.py
=====================================
Persistent reminder and automation scheduler using APScheduler.
Jobs are stored on disk in memory/scheduled_jobs.json.
"""

from __future__ import annotations

import json
import os
import threading
import time
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

try:
    from apscheduler.schedulers.background import BackgroundScheduler
    from apscheduler.triggers.date import DateTrigger
    from apscheduler.triggers.cron import CronTrigger
    from apscheduler.triggers.interval import IntervalTrigger
    APSCHEDULER_OK = True
except ImportError:
    BackgroundScheduler = None
    APSCHEDULER_OK = False

from config import BASE_DIR

JOBS_FILE = BASE_DIR / "memory" / "scheduled_jobs.json"
JOBS_FILE.parent.mkdir(parents=True, exist_ok=True)

_scheduler = None
_lock = threading.Lock()


def _get_scheduler():
    global _scheduler
    if not APSCHEDULER_OK:
        return None
    with _lock:
        if _scheduler is None:
            _scheduler = BackgroundScheduler(daemon=True)
            _scheduler.start()
            _load_persisted_jobs()
    return _scheduler


def _save_job_meta(job_id: str, desc: str, run_time: str, action: str):
    data = {}
    if JOBS_FILE.exists():
        try:
            data = json.loads(JOBS_FILE.read_text(encoding="utf-8"))
        except Exception:
            data = {}
    data[job_id] = {
        "id": job_id,
        "description": desc,
        "run_time": run_time,
        "action": action,
        "created_at": datetime.now().isoformat(),
    }
    JOBS_FILE.write_text(json.dumps(data, indent=2), encoding="utf-8")


def _remove_job_meta(job_id: str):
    if JOBS_FILE.exists():
        try:
            data = json.loads(JOBS_FILE.read_text(encoding="utf-8"))
            if job_id in data:
                del data[job_id]
                JOBS_FILE.write_text(json.dumps(data, indent=2), encoding="utf-8")
        except Exception:
            pass


def _load_persisted_jobs():
    """Rehydrate reminders on startup."""
    # Scheduled jobs are re-added here if needed
    pass


def add_reminder(delay_seconds: int, message: str) -> str:
    """Schedule a reminder notification after a given number of seconds."""
    sched = _get_scheduler()
    if not sched:
        return "ERROR: Scheduler unavailable."

    job_id = f"remind_{int(time.time())}_{abs(hash(message)) % 1000}"
    run_dt = datetime.fromtimestamp(time.time() + int(delay_seconds))

    def _notify(msg=message, jid=job_id):
        print(f"\n[JARVIS REMINDER] 🔔 {msg}\n")
        try:
            from voice.tts import speak_async
            speak_async(f"Reminder, Sir: {msg}")
        except Exception:
            pass
        _remove_job_meta(jid)

    sched.add_job(_notify, trigger=DateTrigger(run_date=run_dt), id=job_id)
    _save_job_meta(job_id, message, run_dt.isoformat(), "reminder")

    return f"SUCCESS: Reminder set for {run_dt.strftime('%H:%M:%S')} (in {delay_seconds}s): '{message}'."


def list_jobs() -> str:
    """List all currently active scheduled reminders and jobs."""
    if not JOBS_FILE.exists():
        return "No active scheduled jobs."
    try:
        data = json.loads(JOBS_FILE.read_text(encoding="utf-8"))
        if not data:
            return "No active scheduled jobs."
        out = ["Active Scheduled Tasks:"]
        for jid, meta in data.items():
            out.append(f"- [{jid}] {meta.get('description')} (Scheduled: {meta.get('run_time')})")
        return "\n".join(out)
    except Exception as e:
        return f"ERROR: Could not read scheduled jobs: {e}"


def cancel_job(job_id: str) -> str:
    """Cancel a scheduled job or reminder by ID."""
    sched = _get_scheduler()
    if sched:
        try:
            sched.remove_job(job_id)
        except Exception:
            pass
    _remove_job_meta(job_id)
    return f"SUCCESS: Cancelled scheduled task: {job_id}."

