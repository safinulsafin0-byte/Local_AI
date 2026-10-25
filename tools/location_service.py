"""
JARVIS Location Service — tools/location_service.py
===================================================
Manages location detection, IP-based approximation, manual city overrides,
and consented browser-based precise geolocation.

Ground rules:
- IP geolocation is approximate (city/ISP level).
- Exact coordinates require explicit browser permission (navigator.geolocation).
- Users can manually override their city in settings anytime.
"""

from __future__ import annotations

import json
import logging
import time
from pathlib import Path
from typing import Dict, Any, Optional

import httpx

logger = logging.getLogger("jarvis.location")

BASE_DIR = Path(__file__).resolve().parent.parent
DATA_DIR = BASE_DIR / "data"
DATA_DIR.mkdir(parents=True, exist_ok=True)

IP_LOCATION_FILE = DATA_DIR / "detected_location.json"
OVERRIDE_FILE = DATA_DIR / "location_override.json"
PRECISE_FILE = DATA_DIR / "precise_location.json"

DEFAULT_FALLBACK = {
    "city": "Khulna",
    "region": "Khulna Division",
    "country": "Bangladesh",
    "lat": 22.8456,
    "lon": 89.5403,
    "source": "fallback",
    "approximate": True
}


def detect_ip_location(force_refresh: bool = False, timeout: float = 3.0) -> Dict[str, Any]:
    """
    Detect approximate city from public IP using ip-api.com.
    Caches result for 24 hours to avoid redundant API hits.
    """
    if not force_refresh and IP_LOCATION_FILE.exists():
        try:
            cached = json.loads(IP_LOCATION_FILE.read_text(encoding="utf-8"))
            # 24 hour TTL
            if time.time() - cached.get("cached_at", 0) < 86400:
                return cached
        except Exception as e:
            logger.debug(f"Failed to read cached IP location: {e}")

    try:
        with httpx.Client(timeout=timeout) as client:
            resp = client.get("http://ip-api.com/json/")
            if resp.status_code == 200:
                data = resp.json()
                if data.get("status") == "success":
                    city = data.get("city", "").replace(" City", "").strip() or "Khulna"
                    result = {
                        "city": city,
                        "region": data.get("regionName", ""),
                        "country": data.get("country", "Bangladesh"),
                        "lat": data.get("lat", 22.8456),
                        "lon": data.get("lon", 89.5403),
                        "isp": data.get("isp", ""),
                        "source": "ip",
                        "approximate": True,
                        "cached_at": time.time()
                    }
                    IP_LOCATION_FILE.write_text(json.dumps(result, indent=2), encoding="utf-8")
                    logger.info(f"[LOCATION] Detected approximate location: {city}, {result['country']} (via IP)")
                    return result
    except Exception as exc:
        logger.warning(f"[LOCATION] IP geolocation request failed: {exc}")

    # Fallback to existing cache if available
    if IP_LOCATION_FILE.exists():
        try:
            return json.loads(IP_LOCATION_FILE.read_text(encoding="utf-8"))
        except Exception:
            pass

    return DEFAULT_FALLBACK


def get_current_location() -> Dict[str, Any]:
    """
    Returns current active location with source priority:
    1. Consented precise geolocation (if set in session/file)
    2. User manual override (if set in settings)
    3. Approximate IP-detected city
    4. Default fallback (Khulna)
    """
    # 1. Precise location
    if PRECISE_FILE.exists():
        try:
            p_data = json.loads(PRECISE_FILE.read_text(encoding="utf-8"))
            # 1 hour TTL for browser precise location
            if time.time() - p_data.get("timestamp", 0) < 3600:
                return {
                    "city": p_data.get("city", "My Location"),
                    "lat": p_data.get("lat"),
                    "lon": p_data.get("lon"),
                    "source": "precise",
                    "approximate": False,
                    "accuracy_m": p_data.get("accuracy_m")
                }
        except Exception:
            pass

    # 2. Manual override
    if OVERRIDE_FILE.exists():
        try:
            o_data = json.loads(OVERRIDE_FILE.read_text(encoding="utf-8"))
            if o_data.get("city"):
                return {
                    "city": o_data.get("city"),
                    "lat": o_data.get("lat"),
                    "lon": o_data.get("lon"),
                    "source": "manual_override",
                    "approximate": False
                }
        except Exception:
            pass

    # 3. IP detected location
    return detect_ip_location()


def set_manual_override(city_name: str, lat: Optional[float] = None, lon: Optional[float] = None) -> Dict[str, Any]:
    """Set manual user city override."""
    city_clean = city_name.strip()
    data = {
        "city": city_clean,
        "lat": lat,
        "lon": lon,
        "updated_at": time.time()
    }
    OVERRIDE_FILE.write_text(json.dumps(data, indent=2), encoding="utf-8")
    return {"ok": True, "location": data}


def clear_manual_override() -> Dict[str, Any]:
    """Reset manual override to IP detection."""
    if OVERRIDE_FILE.exists():
        try:
            OVERRIDE_FILE.unlink()
        except Exception:
            pass
    return {"ok": True, "message": "Manual override cleared, using IP detection."}


def set_precise_location(lat: float, lon: float, accuracy_m: Optional[float] = None, city: Optional[str] = None) -> Dict[str, Any]:
    """Record consented browser geolocation coordinates."""
    data = {
        "lat": lat,
        "lon": lon,
        "accuracy_m": accuracy_m,
        "city": city or "Exact Device Location",
        "timestamp": time.time()
    }
    PRECISE_FILE.write_text(json.dumps(data, indent=2), encoding="utf-8")
    logger.info(f"[LOCATION] Precise geolocation updated: ({lat}, {lon}) ~{accuracy_m}m")
    return {"ok": True, "location": data}


def clear_precise_location() -> Dict[str, Any]:
    if PRECISE_FILE.exists():
        try:
            PRECISE_FILE.unlink()
        except Exception:
            pass
    return {"ok": True, "message": "Precise location cleared."}


def get_location_info() -> Dict[str, Any]:
    """Returns comprehensive location state for UI and endpoints."""
    ip_data = detect_ip_location()
    active = get_current_location()
    has_override = OVERRIDE_FILE.exists()
    override_city = ""
    if has_override:
        try:
            override_city = json.loads(OVERRIDE_FILE.read_text(encoding="utf-8")).get("city", "")
        except Exception:
            pass
    has_precise = PRECISE_FILE.exists()
    return {
        "active_city": active.get("city", "Khulna"),
        "active_source": active.get("source", "ip"),
        "is_approximate": active.get("approximate", True),
        "ip_city": ip_data.get("city", "Khulna"),
        "ip_region": ip_data.get("region", ""),
        "ip_country": ip_data.get("country", "Bangladesh"),
        "has_manual_override": has_override,
        "manual_override_city": override_city,
        "has_precise_location": has_precise
    }

