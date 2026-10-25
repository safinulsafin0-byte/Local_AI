"""
Stark Edition - Smart Facility & Virtual Smart Room
====================================================
Interactive virtual smart facility model managing lights, climate, locks,
power load, and pre-programmed Stark facility scenes.
Includes persistent state and Home Assistant / MQTT adapter readiness.
"""

import os
import json
import time
from pathlib import Path
from typing import Dict, Any, Optional

STATE_FILE = Path.home() / ".jarvis" / "smart_facility_state.json"
STATE_FILE.parent.mkdir(parents=True, exist_ok=True)

DEFAULT_FACILITY_STATE = {
    "name": "Stark Malibu Workshop - Sector 4",
    "status": "Nominal",
    "devices": {
        "arc_light": {
            "name": "Overhead Arc Chandelier",
            "type": "light",
            "power": True,
            "brightness": 85,
            "color": "#00e5ff",
            "rated_watts": 80
        },
        "workshop_spot": {
            "name": "CAD Workbench Floodlight",
            "type": "light",
            "power": True,
            "brightness": 100,
            "color": "#ffffff",
            "rated_watts": 120
        },
        "thermostat": {
            "name": "HVAC Climate Control",
            "type": "climate",
            "power": True,
            "mode": "Cool",
            "target_temp": 21.0,
            "current_temp": 21.8,
            "rated_watts": 1400
        },
        "air_purifier": {
            "name": "HEPA Ion Air Purifier",
            "type": "fan",
            "power": True,
            "speed": "Medium", # Off, Low, Medium, High
            "rated_watts": 45
        },
        "door_lock": {
            "name": "Pneumatic Blast Door",
            "type": "lock",
            "locked": True,
            "status": "Secured",
            "rated_watts": 15
        }
    },
    "active_scene": "Normal Operations"
}

PRESET_SCENES = {
    "movie_night": {
        "name": "Cinema / Presentation Mode",
        "settings": {
            "arc_light": {"power": True, "brightness": 15, "color": "#ff9800"},
            "workshop_spot": {"power": False},
            "thermostat": {"power": True, "mode": "Cool", "target_temp": 22.0},
            "air_purifier": {"power": True, "speed": "Low"},
            "door_lock": {"locked": True}
        }
    },
    "engineering_focus": {
        "name": "Deep Engineering Focus",
        "settings": {
            "arc_light": {"power": True, "brightness": 100, "color": "#00f0ff"},
            "workshop_spot": {"power": True, "brightness": 100, "color": "#ffffff"},
            "thermostat": {"power": True, "mode": "Cool", "target_temp": 20.0},
            "air_purifier": {"power": True, "speed": "High"},
            "door_lock": {"locked": True}
        }
    },
    "night_lockdown": {
        "name": "Facility Night Lockdown",
        "settings": {
            "arc_light": {"power": False},
            "workshop_spot": {"power": False},
            "thermostat": {"power": True, "mode": "Eco", "target_temp": 24.0},
            "air_purifier": {"power": True, "speed": "Low"},
            "door_lock": {"locked": True}
        }
    },
    "clean_slate": {
        "name": "Clean Slate / Standby",
        "settings": {
            "arc_light": {"power": True, "brightness": 50, "color": "#ffffff"},
            "workshop_spot": {"power": False},
            "thermostat": {"power": False},
            "air_purifier": {"power": False},
            "door_lock": {"locked": False}
        }
    }
}

def _load_state() -> Dict[str, Any]:
    if STATE_FILE.exists():
        try:
            with open(STATE_FILE, "r", encoding="utf-8") as f:
                data = json.load(f)
                return data
        except Exception:
            pass
    return json.loads(json.dumps(DEFAULT_FACILITY_STATE))

def _save_state(state: Dict[str, Any]):
    try:
        with open(STATE_FILE, "w", encoding="utf-8") as f:
            json.dump(state, f, indent=2)
    except Exception:
        pass

def calculate_power_draw(state: Dict[str, Any]) -> float:
    """Calculates total instantaneous kW draw of the facility."""
    total_watts = 0.0
    for dev_id, dev in state.get("devices", {}).items():
        if dev.get("power", False) or dev.get("locked", False):
            base_w = dev.get("rated_watts", 50)
            if dev.get("type") == "light":
                brightness = dev.get("brightness", 100) / 100.0
                total_watts += base_w * brightness
            elif dev.get("type") == "fan":
                spd = dev.get("speed", "Medium").lower()
                multiplier = 1.0 if spd == "high" else (0.6 if spd == "medium" else 0.3)
                total_watts += base_w * multiplier
            else:
                total_watts += base_w
    return round(total_watts / 1000.0, 3) # in kW

def get_facility_state() -> Dict[str, Any]:
    """Returns real-time status of all facility devices and energy load."""
    state = _load_state()
    kw_draw = calculate_power_draw(state)
    return {
        "ok": True,
        "facility_name": state.get("name", "Stark Facility"),
        "status": state.get("status", "Nominal"),
        "active_scene": state.get("active_scene", "Normal"),
        "instantaneous_power_kw": kw_draw,
        "devices": state.get("devices", {}),
        "preset_scenes": list(PRESET_SCENES.keys())
    }

def update_device_state(device_id: str, updates: Dict[str, Any]) -> Dict[str, Any]:
    """Modifies settings for a single smart fixture (light, thermostat, lock, fan)."""
    state = _load_state()
    devices = state.setdefault("devices", {})

    if device_id not in devices:
        return {"ok": False, "error": f"Device '{device_id}' does not exist in facility."}

    dev = devices[device_id]
    for k, v in updates.items():
        dev[k] = v

    # Validate lock status text
    if "locked" in dev:
        dev["status"] = "Secured" if dev["locked"] else "Unlocked"

    _save_state(state)
    return {
        "ok": True,
        "device_id": device_id,
        "device": dev,
        "total_power_kw": calculate_power_draw(state),
        "summary": f"{dev.get('name', device_id)} updated successfully."
    }

def activate_facility_scene(scene_key: str) -> Dict[str, Any]:
    """Applies a multi-fixture coordinated facility profile."""
    key = scene_key.lower().replace(" ", "_")
    if key not in PRESET_SCENES:
        return {
            "ok": False,
            "error": f"Unknown scene '{scene_key}'. Available: {list(PRESET_SCENES.keys())}"
        }

    scene = PRESET_SCENES[key]
    state = _load_state()

    for dev_id, settings in scene["settings"].items():
        if dev_id in state["devices"]:
            for k, v in settings.items():
                state["devices"][dev_id][k] = v
            if "locked" in state["devices"][dev_id]:
                state["devices"][dev_id]["status"] = "Secured" if state["devices"][dev_id]["locked"] else "Unlocked"

    state["active_scene"] = scene["name"]
    _save_state(state)

    return {
        "ok": True,
        "scene": scene["name"],
        "total_power_kw": calculate_power_draw(state),
        "devices": state["devices"],
        "summary": f"Facility transition complete: {scene['name']} is now ACTIVE."
    }

def health() -> Dict[str, Any]:
    return {
        "ok": True,
        "status": "Ready",
        "details": {
            "fixtures_managed": len(DEFAULT_FACILITY_STATE["devices"]),
            "preset_scenes_count": len(PRESET_SCENES)
        }
    }

