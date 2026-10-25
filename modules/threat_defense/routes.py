"""
Stark Edition - Threat Defense Routes
=====================================
FastAPI Router for defensive audits, open ports analysis, safe LAN mapping, and code scans.
"""

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel
from typing import Optional, Dict, Any

from modules.threat_defense.tools import (
    audit_system_security,
    scan_local_network,
    scan_code_security
)

router = APIRouter(prefix="/api/v1/defense", tags=["threat_defense"])

class NetworkScanRequest(BaseModel):
    consent: bool = False

class CodeScanRequest(BaseModel):
    target_dir: Optional[str] = None

@router.get("/audit")
async def get_security_audit_endpoint():
    """Retrieve full defensive security posture, firewall, antivirus, and port mapping."""
    return audit_system_security()

@router.post("/scan-lan")
async def post_scan_lan_endpoint(req: NetworkScanRequest):
    """Safely map local subnet devices via passive ARP table. Requires explicit consent."""
    res = scan_local_network(consent=req.consent)
    if not res.get("ok") and res.get("error") == "CONSENT_REQUIRED":
        raise HTTPException(status_code=403, detail=res["message"])
    return res

@router.post("/scan-code")
async def post_scan_code_endpoint(req: CodeScanRequest):
    """Scan codebase for security antipatterns and hardcoded secrets."""
    return scan_code_security(target_dir=req.target_dir)

