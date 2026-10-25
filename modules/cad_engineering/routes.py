"""
Stark Edition - CAD Engineering Bay Routes
==========================================
FastAPI Router for 3D Text-to-CAD generation, hardware diagnostics, and power rerouting.
"""

from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import FileResponse
from pydantic import BaseModel
from typing import Optional, Dict, Any
from pathlib import Path

from modules.cad_engineering.tools import (
    list_cad_templates,
    generate_cad_model,
    run_hardware_diagnostics,
    reroute_system_power,
    CAD_OUTPUT_DIR
)

router = APIRouter(prefix="/api/v1/cad", tags=["cad_engineering"])

class CADGenerateRequest(BaseModel):
    query: Optional[str] = "phone stand"
    template: Optional[str] = None
    params: Optional[Dict[str, Any]] = None

class PowerRerouteRequest(BaseModel):
    mode: str = "high_performance"

@router.get("/templates")
async def get_templates_endpoint():
    """List available procedural CAD templates and their parameters."""
    return list_cad_templates()

@router.post("/generate")
async def generate_cad_endpoint(req: CADGenerateRequest):
    """Generate a watertight 3D STL CAD file."""
    res = generate_cad_model(query=req.query, template=req.template, params=req.params)
    if not res.get("ok"):
        raise HTTPException(status_code=400, detail=res.get("error", "CAD generation failed"))
    return res

@router.get("/file/{filename}")
async def get_cad_file_endpoint(filename: str):
    """Download or stream generated STL binary file for 3D viewer."""
    file_path = CAD_OUTPUT_DIR / filename
    if not file_path.exists() or not file_path.is_file():
        raise HTTPException(status_code=404, detail=f"File {filename} not found.")
    return FileResponse(path=str(file_path), media_type="model/stl", filename=filename)

@router.get("/diagnostics")
async def get_hardware_diagnostics_endpoint():
    """Execute live system & hardware health diagnostics."""
    return run_hardware_diagnostics()

@router.post("/power")
async def post_power_reroute_endpoint(req: PowerRerouteRequest):
    """Reroute power mode using Windows powercfg."""
    return reroute_system_power(mode=req.mode)

