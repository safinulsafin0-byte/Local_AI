"""
Stark Edition - Task Board Routes
=================================
FastAPI Router for parallel background task monitoring and controls.
"""

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from typing import Optional, Dict, Any

from modules.task_board.tools import (
    get_task_board_summary,
    create_task,
    cancel_task,
    clear_completed_tasks,
    spawn_demo_swarm
)

router = APIRouter(prefix="/api/v1/tasks", tags=["task_board"])

class CreateTaskRequest(BaseModel):
    name: str
    category: Optional[str] = "general"

class CancelTaskRequest(BaseModel):
    task_id: str

@router.get("/board")
async def get_board_endpoint():
    """Retrieve full task board summary with all running and completed tasks."""
    return get_task_board_summary()

@router.post("/create")
async def create_task_endpoint(req: CreateTaskRequest):
    """Enqueue a new background task."""
    return create_task(req.name, category=req.category)

@router.post("/cancel")
async def cancel_task_endpoint(req: CancelTaskRequest):
    """Abort a running or queued background task."""
    res = cancel_task(req.task_id)
    if not res.get("ok"):
        raise HTTPException(status_code=400, detail=res["error"])
    return res

@router.post("/clear")
async def clear_tasks_endpoint():
    """Remove finished/aborted tasks from the board."""
    return clear_completed_tasks()

@router.post("/swarm/demo")
async def spawn_swarm_endpoint():
    """Trigger House Party Protocol: launch 3 parallel tasks."""
    return spawn_demo_swarm()

