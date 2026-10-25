"""
Stark Edition - Simulation Lab Routes
=====================================
FastAPI Router for scientific engineering simulations and system integrity analysis.
"""

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel
from typing import Optional, Dict, Any

from modules.simulation_lab.tools import (
    simulate_projectile,
    simulate_heat_diffusion,
    simulate_rlc_circuit,
    simulate_beam_deflection,
    check_system_integrity
)

router = APIRouter(prefix="/api/v1/sim", tags=["simulation_lab"])

class ProjectileRequest(BaseModel):
    velocity: Optional[float] = 50.0
    angle: Optional[float] = 45.0
    drag: Optional[float] = 0.02
    mass: Optional[float] = 1.0

class HeatRequest(BaseModel):
    length: Optional[float] = 1.0
    t_left: Optional[float] = 100.0
    t_right: Optional[float] = 20.0

class RLCRequest(BaseModel):
    r: Optional[float] = 12.0
    l: Optional[float] = 0.05
    c: Optional[float] = 0.0005
    v: Optional[float] = 5.0

class BeamRequest(BaseModel):
    length: Optional[float] = 2.0
    load: Optional[float] = 1500.0
    elastic_modulus: Optional[float] = 200.0

@router.post("/projectile")
async def post_projectile_endpoint(req: ProjectileRequest):
    """Simulate ballistic trajectory with aerodynamic drag."""
    return simulate_projectile(v0=req.velocity, angle_deg=req.angle, drag_coeff=req.drag, mass=req.mass)

@router.post("/heat")
async def post_heat_endpoint(req: HeatRequest):
    """Simulate 1D transient heat diffusion along rod."""
    return simulate_heat_diffusion(length=req.length, t_left=req.t_left, t_right=req.t_right)

@router.post("/rlc")
async def post_rlc_endpoint(req: RLCRequest):
    """Simulate RLC electrical series circuit transient response."""
    return simulate_rlc_circuit(r=req.r, l=req.l, c=req.c, v_step=req.v)

@router.post("/beam")
async def post_beam_endpoint(req: BeamRequest):
    """Simulate structural cantilever beam deflection under point load."""
    return simulate_beam_deflection(length_m=req.length, point_load_n=req.load, elastic_modulus_gpa=req.elastic_modulus)

@router.get("/integrity")
async def get_integrity_endpoint():
    """Execute Windows component store integrity check (DISM /CheckHealth)."""
    return check_system_integrity()

