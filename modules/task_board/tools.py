"""
Stark Edition - Task Board (House Party Protocol Swarm)
======================================================
Asynchronous parallel tool runner that coordinates background jobs (scans, builds,
simulations, telemetry captures) with live progress and cancel control.
"""

import time
import uuid
import threading
from concurrent.futures import ThreadPoolExecutor
from typing import Dict, Any, List, Optional

_EXECUTOR = ThreadPoolExecutor(max_workers=5, thread_name_prefix="JarvisSwarm")
_TASKS: Dict[str, Dict[str, Any]] = {}
_LOCK = threading.Lock()

def get_task_board_summary() -> Dict[str, Any]:
    with _LOCK:
        tasks_list = list(_TASKS.values())
        running = [t for t in tasks_list if t["status"] == "running"]
        queued = [t for t in tasks_list if t["status"] == "queued"]
        done = [t for t in tasks_list if t["status"] == "done"]
        failed = [t for t in tasks_list if t["status"] in ("failed", "aborted")]

        return {
            "ok": True,
            "total_count": len(tasks_list),
            "running_count": len(running),
            "queued_count": len(queued),
            "done_count": len(done),
            "failed_count": len(failed),
            "tasks": sorted(tasks_list, key=lambda x: x["started_at"], reverse=True)
        }

def create_task(name: str, category: str = "general", runner_func=None, args=None) -> Dict[str, Any]:
    task_id = str(uuid.uuid4())[:8]
    task_record = {
        "id": task_id,
        "name": name,
        "category": category,
        "status": "queued",
        "progress": 0,
        "started_at": time.time(),
        "completed_at": None,
        "output": None,
        "error": None,
        "cancel_requested": False
    }

    with _LOCK:
        _TASKS[task_id] = task_record

    def _worker():
        with _LOCK:
            if _TASKS[task_id]["cancel_requested"]:
                _TASKS[task_id]["status"] = "aborted"
                _TASKS[task_id]["completed_at"] = time.time()
                return
            _TASKS[task_id]["status"] = "running"
            _TASKS[task_id]["progress"] = 10

        try:
            if runner_func:
                def progress_cb(pct):
                    with _LOCK:
                        _TASKS[task_id]["progress"] = min(99, max(1, pct))

                res = runner_func(progress_cb, *(args or ()))
                with _LOCK:
                    _TASKS[task_id]["output"] = res
                    _TASKS[task_id]["progress"] = 100
                    _TASKS[task_id]["status"] = "done"
                    _TASKS[task_id]["completed_at"] = time.time()
            else:
                # Default simulated background workload
                for step in range(1, 11):
                    with _LOCK:
                        if _TASKS[task_id]["cancel_requested"]:
                            _TASKS[task_id]["status"] = "aborted"
                            _TASKS[task_id]["completed_at"] = time.time()
                            return
                        _TASKS[task_id]["progress"] = step * 10
                    time.sleep(0.4)

                with _LOCK:
                    _TASKS[task_id]["status"] = "done"
                    _TASKS[task_id]["completed_at"] = time.time()
                    _TASKS[task_id]["output"] = f"Task '{name}' completed successfully."
        except Exception as e:
            with _LOCK:
                _TASKS[task_id]["status"] = "failed"
                _TASKS[task_id]["error"] = str(e)
                _TASKS[task_id]["completed_at"] = time.time()

    _EXECUTOR.submit(_worker)
    return task_record

def cancel_task(task_id: str) -> Dict[str, Any]:
    with _LOCK:
        if task_id not in _TASKS:
            return {"ok": False, "error": f"Task '{task_id}' not found"}
        t = _TASKS[task_id]
        if t["status"] in ("done", "failed", "aborted"):
            return {"ok": False, "error": f"Task already finished with status '{t['status']}'"}
        t["cancel_requested"] = True
        t["status"] = "aborted"
        t["completed_at"] = time.time()
        return {"ok": True, "task_id": task_id, "status": "aborted"}

def clear_completed_tasks() -> Dict[str, Any]:
    global _TASKS
    with _LOCK:
        _TASKS = {tid: t for tid, t in _TASKS.items() if t["status"] in ("queued", "running")}
        return {"ok": True, "remaining": len(_TASKS)}

def spawn_demo_swarm() -> Dict[str, Any]:
    """Launch 3 simultaneous background tool operations (House Party Protocol)."""
    t1 = create_task("Telemetry Deep Scan (Hardware & RAM)", category="diagnostics")
    t2 = create_task("Cache Integrity & Disk Map Audit", category="filesystem")
    t3 = create_task("Model Parameter & Latency Benchmark", category="benchmark")

    return {
        "ok": True,
        "message": "House Party Protocol initiated: 3 parallel tasks launched across worker threads.",
        "tasks": [t1["id"], t2["id"], t3["id"]]
    }

def health() -> Dict[str, Any]:
    summary = get_task_board_summary()
    return {
        "ok": True,
        "status": "Ready",
        "details": {
            "active_workers": summary["running_count"],
            "total_tasks": summary["total_count"]
        }
    }

# Aliases
launch_swarm_demo = spawn_demo_swarm
list_active_tasks = get_task_board_summary

