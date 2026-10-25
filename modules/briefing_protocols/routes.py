"""
Stark Edition - Briefings & Protocols Routes
============================================
FastAPI Router for briefings, personality settings, and protocols.
"""

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel
from typing import Optional, Dict, Any

from modules.briefing_protocols.tools import (
    get_proactive_briefing,
    list_protocols,
    run_protocol,
    set_personality_mode,
    get_personality_mode
)

router = APIRouter(prefix="/api/v1/stark", tags=["briefing_protocols"])

class PersonalityRequest(BaseModel):
    mode: str

class RunProtocolRequest(BaseModel):
    name: str

@router.get("/briefing")
async def get_briefing_endpoint(lang: str = Query("en")):
    """Retrieve proactive executive system briefing."""
    return get_proactive_briefing(lang=lang)

@router.get("/protocols")
async def list_protocols_endpoint():
    """List all available protocols."""
    return list_protocols()

@router.post("/protocols/run")
async def run_protocol_endpoint(req: RunProtocolRequest):
    """Execute a protocol by name with step-by-step verification."""
    res = run_protocol(req.name)
    if not res.get("ok") and "not found" in res.get("error", "").lower():
        raise HTTPException(status_code=404, detail=res["error"])
    return res

@router.get("/personality")
async def get_personality_endpoint():
    """Get active Stark personality mode."""
    return {"ok": True, "mode": get_personality_mode()}

@router.post("/personality")
async def set_personality_endpoint(req: PersonalityRequest):
    """Set personality mode: Stark | Professional | Friendly."""
    return set_personality_mode(req.mode)

