"""
Stark Edition - Comms Routes
============================
FastAPI Router for notifications, reminders, and authenticated remote dispatch.
"""

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel
from typing import Optional, Dict, Any

from modules.comms.tools import (
    send_desktop_notification,
    get_notification_history,
    create_reminder,
    list_reminders,
    dismiss_reminder,
    process_remote_command
)

router = APIRouter(prefix="/api/v1/comms", tags=["comms"])

class NotifyRequest(BaseModel):
    title: str
    message: str
    level: str = "info"

class ReminderRequest(BaseModel):
    text: str
    due_in_minutes: int = 30
    priority: str = "normal"

class RemoteCommandRequest(BaseModel):
    chat_id: str
    command: str

@router.post("/notify")
async def post_notify_endpoint(req: NotifyRequest):
    """Dispatch a native desktop alert."""
    return send_desktop_notification(title=req.title, message=req.message, level=req.level)

@router.get("/notifications")
async def get_notifications_endpoint():
    """Get history of recent alerts."""
    return get_notification_history()

@router.post("/reminders")
async def post_reminder_endpoint(req: ReminderRequest):
    """Schedule a local system reminder."""
    return create_reminder(text=req.text, due_in_minutes=req.due_in_minutes, priority=req.priority)

@router.get("/reminders")
async def get_reminders_endpoint():
    """List pending reminders."""
    return list_reminders()

@router.post("/remote-dispatch")
async def post_remote_dispatch_endpoint(req: RemoteCommandRequest):
    """Process an authenticated remote command (Telegram simulator)."""
    res = process_remote_command(chat_id=req.chat_id, command_text=req.command)
    if not res.get("ok") and res.get("error") == "UNAUTHORIZED_SENDER":
        raise HTTPException(status_code=403, detail=res["message"])
    return res

