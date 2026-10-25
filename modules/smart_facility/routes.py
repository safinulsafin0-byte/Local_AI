"""
Stark Edition - Smart Facility Routes
=====================================
FastAPI Router for smart facility telemetry, device manipulation, and scenes.
"""

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel
from typing import Optional, Dict, Any

from modules.smart_facility.tools import (
    get_facility_state,
    update_device_state,
    activate_facility_scene
)

router = APIRouter(prefix="/api/v1/facility", tags=["smart_facility"])

class DeviceUpdateRequest(BaseModel):
    device_id: str
    updates: Dict[str, Any]

class SceneRequest(BaseModel):
    scene: str

@router.get("/state")
async def get_state_endpoint():
    """Retrieve full real-time virtual smart facility state and power metrics."""
    return get_facility_state()

@router.post("/device")
async def post_device_endpoint(req: DeviceUpdateRequest):
    """Adjust settings for a smart device fixture (light, climate, lock, fan)."""
    res = update_device_state(req.device_id, req.updates)
    if not res.get("ok"):
        raise HTTPException(status_code=400, detail=res.get("error"))
    return res

@router.post("/scene")
async def post_scene_endpoint(req: SceneRequest):
    """Trigger coordinated facility preset scene."""
    res = activate_facility_scene(req.scene)
    if not res.get("ok"):
        raise HTTPException(status_code=400, detail=res.get("error"))
    return res

