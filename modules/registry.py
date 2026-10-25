"""
JARVIS Stark Edition - Module Registry & Lazy Loader
===================================================
Manages modular plug-and-play capabilities:
- Lazy loading and mounting of FastAPI routers
- Manifest inspection (tools, intents, permissions, resource budget)
- Runtime enabling/disabling of modules from Settings / API
- Health checking and resource estimation for HUD display
"""

import os
import sys
import json
import logging
from pathlib import Path
from typing import Dict, Any, List, Optional
from fastapi import APIRouter, FastAPI

logger = logging.getLogger("jarvis.modules")

MODULES_DIR = Path(__file__).resolve().parent
BASE_DIR = MODULES_DIR.parent
CONFIG_STATE_FILE = BASE_DIR / "data" / "modules_state.json"

_REGISTERED_MODULES: Dict[str, Dict[str, Any]] = {}

def _load_state() -> Dict[str, bool]:
    if CONFIG_STATE_FILE.exists():
        try:
            return json.loads(CONFIG_STATE_FILE.read_text(encoding="utf-8"))
        except Exception as e:
            logger.warning(f"Failed to read modules_state.json: {e}")
    return {}

def _save_state(state: Dict[str, bool]) -> None:
    try:
        CONFIG_STATE_FILE.parent.mkdir(parents=True, exist_ok=True)
        CONFIG_STATE_FILE.write_text(json.dumps(state, indent=2), encoding="utf-8")
    except Exception as e:
        logger.warning(f"Failed to save modules_state.json: {e}")

def discover_modules() -> Dict[str, Dict[str, Any]]:
    """Scan modules/ for subdirectories with manifest.json."""
    global _REGISTERED_MODULES
    discovered = {}
    saved_state = _load_state()

    for item in MODULES_DIR.iterdir():
        if not item.is_dir() or item.name.startswith(("_", ".")):
            continue
        manifest_file = item / "manifest.json"
        if manifest_file.exists():
            try:
                manifest = json.loads(manifest_file.read_text(encoding="utf-8"))
                mod_id = manifest.get("id", item.name)
                # State preference: saved_state overrides manifest default
                enabled = saved_state.get(mod_id, manifest.get("enabled", True))
                manifest["enabled"] = enabled
                manifest["dir"] = str(item)
                discovered[mod_id] = manifest
            except Exception as e:
                logger.error(f"Error loading manifest for module {item.name}: {e}")

    _REGISTERED_MODULES = discovered
    return _REGISTERED_MODULES

def get_module(mod_id: str) -> Optional[Dict[str, Any]]:
    if not _REGISTERED_MODULES:
        discover_modules()
    return _REGISTERED_MODULES.get(mod_id)

def list_modules() -> List[Dict[str, Any]]:
    if not _REGISTERED_MODULES:
        discover_modules()
    result = []
    for mod_id, meta in _REGISTERED_MODULES.items():
        h = check_module_health(mod_id)
        entry = dict(meta)
        entry["health"] = h
        result.append(entry)
    return result

def check_module_health(mod_id: str) -> Dict[str, Any]:
    mod_meta = _REGISTERED_MODULES.get(mod_id)
    if not mod_meta:
        return {"ok": False, "status": "Not Found", "details": {}}
    if not mod_meta.get("enabled", True):
        return {"ok": True, "status": "Disabled", "details": {"active": False}}

    mod_dir = Path(mod_meta["dir"])
    tools_file = mod_dir / "tools.py"
    if not tools_file.exists():
        return {"ok": True, "status": "Ready", "details": {"has_tools": False}}

    try:
        # Import health if defined
        module_path = f"modules.{mod_dir.name}.tools"
        if module_path in sys.modules:
            tools_mod = sys.modules[module_path]
        else:
            import importlib
            tools_mod = importlib.import_module(module_path)

        if hasattr(tools_mod, "health"):
            return tools_mod.health()
        return {"ok": True, "status": "Healthy", "details": {"imported": True}}
    except Exception as e:
        return {"ok": False, "status": "Degraded", "details": {"error": str(e)}}

def toggle_module(mod_id: str, enabled: bool) -> Dict[str, Any]:
    if not _REGISTERED_MODULES:
        discover_modules()
    if mod_id not in _REGISTERED_MODULES:
        return {"ok": False, "error": f"Module '{mod_id}' does not exist"}

    _REGISTERED_MODULES[mod_id]["enabled"] = enabled
    state = _load_state()
    state[mod_id] = enabled
    _save_state(state)
    logger.info(f"Module '{mod_id}' state updated to enabled={enabled}")
    return {"ok": True, "id": mod_id, "enabled": enabled}

def load_and_mount_modules(app: FastAPI) -> None:
    """Mount routers for all enabled modules into the FastAPI app."""
    discover_modules()
    for mod_id, meta in _REGISTERED_MODULES.items():
        if not meta.get("enabled", True):
            continue
        mod_dir = Path(meta["dir"])
        routes_file = mod_dir / "routes.py"
        if routes_file.exists():
            try:
                import importlib
                module_path = f"modules.{mod_dir.name}.routes"
                routes_mod = importlib.import_module(module_path)
                if hasattr(routes_mod, "router"):
                    app.include_router(routes_mod.router)
                    logger.info(f"Mounted router for Stark module: {mod_id}")
            except Exception as e:
                logger.error(f"Failed to mount router for module {mod_id}: {e}")

def get_all_module_intents() -> List[Dict[str, Any]]:
    """Returns keywords and slot definitions from all enabled modules."""
    if not _REGISTERED_MODULES:
        discover_modules()
    intents = []
    for mod_id, meta in _REGISTERED_MODULES.items():
        if not meta.get("enabled", True):
            continue
        mod_intents = meta.get("intents", [])
        keywords = meta.get("keywords", {})
        for item in mod_intents:
            intents.append({
                "module_id": mod_id,
                "intent": item,
                "keywords": keywords.get(item, []),
                "risk_level": meta.get("risk_level", "low")
            })
    return intents

