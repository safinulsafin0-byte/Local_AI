"""
JARVIS Central Tool Registry — tools/registry.py
================================================
Single source of truth for all tools in JARVIS:
filesystem, system/pc, browser, youtube, web, memory, rag, scheduler.
"""

from __future__ import annotations

import inspect
import json
import logging
from typing import Any, Callable, Dict, List, Optional

from config import REQUIRE_CONFIRMATION_FOR, TRUST_MODE

logger = logging.getLogger("jarvis.registry")


class Tool:
    def __init__(
        self,
        name: str,
        description: str,
        parameters: Dict[str, Any],
        handler: Callable[..., Any],
        destructive: bool = False,
    ):
        self.name = name
        self.description = description
        self.parameters = parameters
        self.handler = handler
        self.destructive = destructive

    def to_ollama_dict(self) -> Dict[str, Any]:
        """Format as Ollama tool call definition."""
        return {
            "type": "function",
            "function": {
                "name": self.name,
                "description": self.description,
                "parameters": self.parameters,
            },
        }


class ToolRegistry:
    def __init__(self):
        self._tools: Dict[str, Tool] = {}

    def register(
        self,
        name: str,
        description: str,
        parameters: Dict[str, Any],
        handler: Callable[..., Any],
        destructive: bool = False,
    ) -> None:
        self._tools[name] = Tool(
            name=name,
            description=description,
            parameters=parameters,
            handler=handler,
            destructive=destructive,
        )

    def get(self, name: str) -> Optional[Tool]:
        return self._tools.get(name)

    def list_tools(self) -> List[Dict[str, Any]]:
        return [tool.to_ollama_dict() for tool in self._tools.values()]

    def get_descriptions_text(self) -> str:
        """Formatted textual descriptions for model prompt fallback."""
        lines = []
        for name, tool in self._tools.items():
            props = tool.parameters.get("properties", {})
            param_str = ", ".join(props.keys())
            lines.append(f"{name}({param_str}): {tool.description}")
        return "\n".join(lines)

    def execute(
        self,
        name: str,
        args: Dict[str, Any],
        trust_mode: Optional[str] = None,
        confirmed: bool = False,
    ) -> str:
        tool = self._tools.get(name)
        if not tool:
            # Try aliases or case-insensitive
            for k, v in self._tools.items():
                if k.lower() == name.lower():
                    tool = v
                    break
        if not tool:
            return f"ERROR: Unknown tool '{name}'."

        mode = trust_mode or TRUST_MODE
        if mode == "confirm_destructive" and tool.destructive and not confirmed:
            return f"CONFIRMATION_NEEDED: '{name}' is a destructive action. Confirm to proceed."

        try:
            return str(tool.handler(**args))
        except TypeError as e:
            # Argument mismatch
            return f"ERROR: Invalid arguments for {name}: {e}"
        except Exception as e:
            return f"ERROR: Tool {name} execution failed: {e}"


# Global registry instance
registry = ToolRegistry()


# ── Lazy Auto-registration ────────────────────────────────────────────────────

def _register_all():
    from tools import file_ops, system_ops, monitor, web_tools, youtube_tools, scheduler

    # ── Filesystem ────────────────────────────────────────────────────────────
    registry.register(
        "filesystem.list_dir",
        "List files and folders in a directory.",
        {"type": "object", "properties": {"path": {"type": "string", "description": "Folder path", "default": "."}}},
        file_ops.list_dir,
    )
    registry.register(
        "filesystem.read_file",
        "Read full contents of a text file.",
        {"type": "object", "properties": {"path": {"type": "string", "description": "File path"}}, "required": ["path"]},
        file_ops.read_file,
    )
    registry.register(
        "filesystem.create_file",
        "Create a new file with text content.",
        {"type": "object", "properties": {"path": {"type": "string"}, "content": {"type": "string", "default": ""}}, "required": ["path"]},
        file_ops.create_file,
    )
    registry.register(
        "filesystem.write_file",
        "Overwrite a file with new content.",
        {"type": "object", "properties": {"path": {"type": "string"}, "content": {"type": "string"}}, "required": ["path", "content"]},
        file_ops.write_file,
    )
    registry.register(
        "filesystem.append_file",
        "Append text to an existing file.",
        {"type": "object", "properties": {"path": {"type": "string"}, "content": {"type": "string"}}, "required": ["path", "content"]},
        file_ops.append_file,
    )
    registry.register(
        "filesystem.create_folder",
        "Create a directory folder.",
        {"type": "object", "properties": {"path": {"type": "string"}}, "required": ["path"]},
        file_ops.create_folder,
    )
    registry.register(
        "filesystem.rename",
        "Rename a file or folder.",
        {"type": "object", "properties": {"path": {"type": "string"}, "new_name": {"type": "string"}}, "required": ["path", "new_name"]},
        file_ops.rename,
    )
    registry.register(
        "filesystem.move",
        "Move a file or folder to a destination folder.",
        {"type": "object", "properties": {"path": {"type": "string"}, "destination": {"type": "string"}}, "required": ["path", "destination"]},
        file_ops.move,
    )
    registry.register(
        "filesystem.copy",
        "Copy a file or folder to a destination folder.",
        {"type": "object", "properties": {"path": {"type": "string"}, "destination": {"type": "string"}}, "required": ["path", "destination"]},
        file_ops.copy,
    )
    registry.register(
        "filesystem.delete_file",
        "Safely move a file to the Windows Recycle Bin.",
        {"type": "object", "properties": {"path": {"type": "string"}}, "required": ["path"]},
        file_ops.delete_file,
        destructive=True,
    )
    registry.register(
        "filesystem.delete_folder",
        "Safely move a folder to the Windows Recycle Bin.",
        {"type": "object", "properties": {"path": {"type": "string"}}, "required": ["path"]},
        file_ops.delete_folder,
        destructive=True,
    )
    registry.register(
        "filesystem.search_files",
        "Search files by name pattern and optional text content.",
        {"type": "object", "properties": {"root": {"type": "string", "default": "."}, "pattern": {"type": "string", "default": "*"}, "content_query": {"type": "string"}}},
        file_ops.search_files,
    )
    registry.register(
        "filesystem.find_duplicates",
        "Find duplicate files in a folder by MD5 checksum.",
        {"type": "object", "properties": {"root": {"type": "string", "default": "."}}},
        file_ops.find_duplicates,
    )
    registry.register(
        "filesystem.organize_by_type",
        "Sort loose files into category folders (Images, Documents, Code, etc.).",
        {"type": "object", "properties": {"root": {"type": "string", "default": "."}}},
        file_ops.organize_by_type,
    )
    registry.register(
        "filesystem.tree_summary",
        "Show a visual directory tree summary.",
        {"type": "object", "properties": {"root": {"type": "string", "default": "."}, "max_depth": {"type": "integer", "default": 3}}},
        file_ops.tree_summary,
    )

    # ── System / Apps / PC Control ────────────────────────────────────────────
    registry.register(
        "system.open_app",
        "Launch an application by name (e.g. notepad, chrome, code, calc).",
        {"type": "object", "properties": {"command": {"type": "string"}}, "required": ["command"]},
        system_ops.open_app,
    )
    registry.register(
        "system.close_app",
        "Close an application by name (e.g. notepad, chrome).",
        {"type": "object", "properties": {"name": {"type": "string"}}, "required": ["name"]},
        system_ops.close_app,
    )
    registry.register(
        "system.kill_process",
        "Kill a process by PID or name.",
        {"type": "object", "properties": {"pid_or_name": {"type": "string"}}, "required": ["pid_or_name"]},
        system_ops.kill_process,
        destructive=True,
    )
    registry.register(
        "system.list_windows",
        "List all open desktop windows.",
        {"type": "object", "properties": {}},
        system_ops.list_windows,
    )
    registry.register(
        "system.focus_window",
        "Bring a window to the front by title.",
        {"type": "object", "properties": {"title": {"type": "string"}}, "required": ["title"]},
        system_ops.focus_window,
    )
    registry.register(
        "system.minimize_window",
        "Minimize a window by title.",
        {"type": "object", "properties": {"title": {"type": "string"}}, "required": ["title"]},
        system_ops.minimize_window,
    )
    registry.register(
        "system.maximize_window",
        "Maximize a window by title.",
        {"type": "object", "properties": {"title": {"type": "string"}}, "required": ["title"]},
        system_ops.maximize_window,
    )
    registry.register(
        "system.type_text",
        "Type text using the keyboard.",
        {"type": "object", "properties": {"text": {"type": "string"}}, "required": ["text"]},
        system_ops.type_text,
    )
    registry.register(
        "system.press",
        "Press a keyboard key (e.g. enter, esc, f5).",
        {"type": "object", "properties": {"key": {"type": "string"}}, "required": ["key"]},
        system_ops.press,
    )
    registry.register(
        "system.hotkey",
        "Press a key combination (e.g. ctrl+c, alt+tab, win+d).",
        {"type": "object", "properties": {"keys": {"type": "string"}}, "required": ["keys"]},
        system_ops.hotkey,
    )
    registry.register(
        "system.click",
        "Click the mouse at (x, y) coordinates.",
        {"type": "object", "properties": {"x": {"type": "integer"}, "y": {"type": "integer"}, "button": {"type": "string", "default": "left"}}, "required": ["x", "y"]},
        system_ops.click,
    )
    registry.register(
        "system.scroll",
        "Scroll the mouse wheel.",
        {"type": "object", "properties": {"amount": {"type": "integer", "default": -300}}, "required": ["amount"]},
        system_ops.scroll,
    )
    registry.register(
        "system.screenshot",
        "Take a full screen screenshot and save to disk.",
        {"type": "object", "properties": {"path": {"type": "string"}}},
        system_ops.screenshot,
    )
    registry.register(
        "system.clipboard_set",
        "Copy text to the Windows clipboard.",
        {"type": "object", "properties": {"text": {"type": "string"}}, "required": ["text"]},
        system_ops.clipboard_set,
    )
    registry.register(
        "system.clipboard_get",
        "Get text currently stored in the Windows clipboard.",
        {"type": "object", "properties": {}},
        system_ops.clipboard_get,
    )
    registry.register(
        "system.system_status",
        "Get comprehensive live CPU, RAM, disk, GPU, top processes metrics.",
        {"type": "object", "properties": {}},
        system_ops.system_status,
    )
    registry.register(
        "system.volume_set",
        "Set master system volume (0-100).",
        {"type": "object", "properties": {"level": {"type": "integer"}}, "required": ["level"]},
        system_ops.volume_set,
    )
    registry.register(
        "system.volume_get",
        "Get current volume status.",
        {"type": "object", "properties": {}},
        system_ops.volume_get,
    )
    registry.register(
        "system.brightness_set",
        "Set screen brightness (0-100).",
        {"type": "object", "properties": {"level": {"type": "integer"}}, "required": ["level"]},
        system_ops.brightness_set,
    )
    registry.register(
        "system.lock_workstation",
        "Lock the PC workstation.",
        {"type": "object", "properties": {}},
        system_ops.lock_workstation,
    )
    registry.register(
        "system.sleep_pc",
        "Put the PC into sleep mode.",
        {"type": "object", "properties": {}},
        system_ops.sleep_pc,
    )
    registry.register(
        "system.shutdown",
        "Schedule computer shutdown.",
        {"type": "object", "properties": {"delay_seconds": {"type": "integer", "default": 25}}},
        system_ops.shutdown,
        destructive=True,
    )
    registry.register(
        "system.cancel_shutdown",
        "Cancel a scheduled shutdown.",
        {"type": "object", "properties": {}},
        system_ops.cancel_shutdown,
    )
    registry.register(
        "system.restart",
        "Schedule computer restart.",
        {"type": "object", "properties": {"delay_seconds": {"type": "integer", "default": 25}}},
        system_ops.restart,
        destructive=True,
    )
    registry.register(
        "system.network_info",
        "Get network interfaces, IP addresses, and Wi-Fi SSID.",
        {"type": "object", "properties": {}},
        system_ops.network_info,
    )
    registry.register(
        "system.battery_info",
        "Get battery percentage and power status.",
        {"type": "object", "properties": {}},
        system_ops.battery_info,
    )
    registry.register(
        "system.installed_apps",
        "List installed desktop software.",
        {"type": "object", "properties": {}},
        system_ops.installed_apps,
    )
    registry.register(
        "system.run_shell",
        "Run a PowerShell / command line instruction.",
        {"type": "object", "properties": {"command": {"type": "string"}, "timeout_seconds": {"type": "integer", "default": 30}}, "required": ["command"]},
        system_ops.run_shell,
    )

    # ── Web & Research ────────────────────────────────────────────────────────
    registry.register(
        "web.search",
        "Search the web for fresh information using DuckDuckGo/Wikipedia.",
        {"type": "object", "properties": {"query": {"type": "string"}, "max_results": {"type": "integer", "default": 5}}, "required": ["query"]},
        web_tools.web_search,
    )
    registry.register(
        "web.fetch_page",
        "Fetch and extract readable clean text from a URL.",
        {"type": "object", "properties": {"url": {"type": "string"}}, "required": ["url"]},
        web_tools.fetch_page,
    )
    registry.register(
        "web.research",
        "Deep research question across web pages with cited source URLs.",
        {"type": "object", "properties": {"question": {"type": "string"}}, "required": ["question"]},
        web_tools.research,
    )
    registry.register(
        "web.weather",
        "Get live weather report for a location.",
        {"type": "object", "properties": {"city": {"type": "string", "default": ""}}},
        web_tools.weather,
    )
    registry.register(
        "web.news",
        "Get latest news headlines on a topic.",
        {"type": "object", "properties": {"topic": {"type": "string", "default": "world"}}},
        web_tools.news,
    )
    registry.register(
        "web.currency_convert",
        "Convert currency using live exchange rates.",
        {"type": "object", "properties": {"amount": {"type": "number"}, "from_curr": {"type": "string"}, "to_curr": {"type": "string"}}, "required": ["amount", "from_curr", "to_curr"]},
        web_tools.currency_convert,
    )

    # ── YouTube ───────────────────────────────────────────────────────────────
    registry.register(
        "youtube.search",
        "Search YouTube videos.",
        {"type": "object", "properties": {"query": {"type": "string"}}, "required": ["query"]},
        youtube_tools.youtube_search,
    )
    registry.register(
        "youtube.play",
        "Play a YouTube video by query or URL.",
        {"type": "object", "properties": {"query_or_url": {"type": "string"}}, "required": ["query_or_url"]},
        youtube_tools.youtube_play,
    )
    registry.register(
        "youtube.pause",
        "Pause the playing YouTube video.",
        {"type": "object", "properties": {}},
        youtube_tools.youtube_pause,
    )
    registry.register(
        "youtube.resume",
        "Resume playback of the YouTube video.",
        {"type": "object", "properties": {}},
        youtube_tools.youtube_resume,
    )
    registry.register(
        "youtube.fullscreen",
        "Toggle fullscreen YouTube video mode.",
        {"type": "object", "properties": {}},
        youtube_tools.youtube_fullscreen,
    )
    registry.register(
        "youtube.speed",
        "Change playback speed (e.g. 1.25, 1.5, 2.0).",
        {"type": "object", "properties": {"rate": {"type": "number"}}, "required": ["rate"]},
        youtube_tools.youtube_speed,
    )
    registry.register(
        "youtube.seek",
        "Seek forward or backward in YouTube video by seconds.",
        {"type": "object", "properties": {"seconds": {"type": "integer"}}, "required": ["seconds"]},
        youtube_tools.youtube_seek,
    )
    registry.register(
        "youtube.next",
        "Skip to next YouTube video.",
        {"type": "object", "properties": {}},
        youtube_tools.youtube_next,
    )
    registry.register(
        "youtube.previous",
        "Go back to previous YouTube video.",
        {"type": "object", "properties": {}},
        youtube_tools.youtube_previous,
    )
    registry.register(
        "youtube.mute",
        "Toggle mute state of video.",
        {"type": "object", "properties": {}},
        youtube_tools.youtube_mute,
    )
    registry.register(
        "youtube.summarize",
        "Summarize a YouTube video transcript.",
        {"type": "object", "properties": {"url": {"type": "string"}, "language": {"type": "string", "default": "English"}}, "required": ["url"]},
        youtube_tools.youtube_summarize,
    )
    registry.register(
        "youtube.ask",
        "Ask a specific question about the video content.",
        {"type": "object", "properties": {"url": {"type": "string"}, "question": {"type": "string"}}, "required": ["url", "question"]},
        youtube_tools.youtube_ask,
    )
    registry.register(
        "youtube.control",
        "Control YouTube playback (pause, seek, next, prev, mute, fullscreen).",
        {"type": "object", "properties": {"action": {"type": "string"}, "seconds": {"type": "integer", "default": 0}}, "required": ["action"]},
        youtube_tools.youtube_control,
    )
    registry.register(
        "browser.youtube_control",
        "Control YouTube playback (pause, seek, next, prev, mute, fullscreen).",
        {"type": "object", "properties": {"action": {"type": "string"}, "seconds": {"type": "integer", "default": 0}}, "required": ["action"]},
        youtube_tools.youtube_control,
    )


    # ── Scheduling ────────────────────────────────────────────────────────────
    registry.register(
        "schedule.add_reminder",
        "Schedule a reminder message after N seconds.",
        {"type": "object", "properties": {"delay_seconds": {"type": "integer"}, "message": {"type": "string"}}, "required": ["delay_seconds", "message"]},
        scheduler.add_reminder,
    )
    registry.register(
        "schedule.list_jobs",
        "List all currently scheduled reminders and tasks.",
        {"type": "object", "properties": {}},
        scheduler.list_jobs,
    )
    registry.register(
        "schedule.cancel_job",
        "Cancel a scheduled reminder by ID.",
        {"type": "object", "properties": {"job_id": {"type": "string"}}, "required": ["job_id"]},
        scheduler.cancel_job,
    )

    # ── Image Generation ──────────────────────────────────────────────────────
    try:
        from image_generation.image_generator import image_generate_tool
        registry.register(
            "image.generate",
            "Generate an image from a detailed English text description using local offline SD-Turbo.",
            {
                "type": "object",
                "properties": {
                    "prompt": {"type": "string", "description": "Text description of the image to generate."},
                    "steps": {"type": "integer", "description": "Number of inference steps (1-4). Default is 1.", "default": 1},
                    "seed": {"type": "integer", "description": "Random seed for reproducibility."}
                },
                "required": ["prompt"]
            },
            image_generate_tool,
        )
    except Exception as _e:
        logger.warning(f"Could not register image.generate tool: {_e}")


# Automatically initialize on import
try:
    _register_all()
except Exception as _e:
    logger.warning(f"Tool registry initialization warning: {_e}")

