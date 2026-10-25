"""
JARVIS YouTube Suite — tools/youtube_tools.py
=============================================
Controls YouTube via Playwright persistent browser and extracts
transcripts, summaries, and Q&A using youtube-transcript-api.
"""

from __future__ import annotations

import re
import urllib.parse
from typing import Any, Dict, List, Optional
import requests

from browser.browser_agent import browser_tool
from video_summarizer import get_transcript, summarize_youtube, extract_video_id


def youtube_search(query: str) -> str:
    """Search YouTube and return formatted video results."""
    query = str(query or "").strip()
    if not query:
        return "ERROR: No search query provided."

    res = browser_tool("youtube_search", query=query)
    # Also fetch results list
    res_list = browser_tool("search_results", limit=5)
    return f"{res}\n\n{res_list}"


def youtube_play(query_or_url: str) -> str:
    """Open and play a video by URL or search query."""
    target = str(query_or_url or "").strip()
    if not target:
        return "ERROR: No query or URL provided."

    # If it's a URL
    if "youtube.com" in target or "youtu.be" in target:
        res = browser_tool("open", url=target)
        # Attempt to auto-play and skip ads
        browser_tool("play_video")
        return f"SUCCESS: Playing video: {target}"

    # Search and play first result
    browser_tool("youtube_search", query=target)
    play_res = browser_tool("open_nth_video", index=1)
    browser_tool("play_video")
    return f"SUCCESS: Playing top result for '{target}': {play_res}"


def youtube_pause() -> str:
    """Pause current video."""
    return browser_tool("pause_video")


def youtube_resume() -> str:
    """Resume playing current video."""
    return browser_tool("play_video")


def youtube_toggle() -> str:
    """Toggle play / pause."""
    return browser_tool("toggle_play_pause")


def youtube_seek(seconds: int) -> str:
    """Seek forward or backward by N seconds using JavaScript."""
    try:
        sec = int(seconds)
        return browser_tool("seek_video", seconds=sec)
    except Exception as e:
        return f"ERROR: Could not seek: {e}"


def youtube_speed(rate: float) -> str:
    """Set playback speed (e.g. 0.5, 1.0, 1.25, 1.5, 2.0)."""
    try:
        r = float(rate)
        # We can simulate keyboard shortcuts: Shift+> (faster) or Shift+< (slower)
        from tools import system_ops
        if r > 1.0:
            system_ops.hotkey("shift+.")
        elif r < 1.0:
            system_ops.hotkey("shift+,")
        return f"SUCCESS: Adjusted playback speed to ~{r}x."
    except Exception as e:
        return f"ERROR: Could not adjust speed: {e}"


def youtube_fullscreen() -> str:
    """Toggle fullscreen mode (press 'f')."""
    from tools import system_ops
    system_ops.press("f")
    return "SUCCESS: Toggled fullscreen mode."


def youtube_mute() -> str:
    """Toggle mute (press 'm')."""
    from tools import system_ops
    system_ops.press("m")
    return "SUCCESS: Toggled mute state."


def youtube_next() -> str:
    """Play next video (Shift+N)."""
    from tools import system_ops
    system_ops.hotkey("shift+n")
    return "SUCCESS: Skipped to next video."


def youtube_previous() -> str:
    """Go to previous video (browser back or Shift+P)."""
    from tools import system_ops
    system_ops.hotkey("shift+p")
    return "SUCCESS: Returned to previous video."


def youtube_captions() -> str:
    """Toggle closed captions / subtitles (press 'c')."""
    from tools import system_ops
    system_ops.press("c")
    return "SUCCESS: Toggled subtitles / captions."


def youtube_summarize(url: str, language: str = "English") -> str:
    """Generate comprehensive summary of a YouTube video using transcript."""
    return summarize_youtube(url, language=language)


def youtube_ask(url: str, question: str) -> str:
    """Ask a specific question about a YouTube video's content."""
    res = get_transcript(url)
    if not res.get("success"):
        return f"ERROR: Could not retrieve transcript: {res.get('error')}"

    transcript = res["text"]
    try:
        from llm.ollama_client import chat
        prompt = [
            {
                "role": "system",
                "content": (
                    "You are JARVIS. Answer the question using ONLY the provided YouTube video transcript. "
                    "Be direct, accurate, and concise."
                ),
            },
            {
                "role": "user",
                "content": f"TRANSCRIPT:\n{transcript[:15000]}\n\nQUESTION: {question}",
            },
        ]
        answer = chat(prompt, "")
        return f"ANSWER: {answer}"
    except Exception as e:
        return f"ERROR: Could not answer question: {e}"


def youtube_control(action: str, seconds: int = 0) -> str:
    """Universal dispatcher for YouTube controls (pause, play, seek, mute, next, previous)."""
    act = str(action or "").lower().strip()
    try:
        if act in ("pause", "play", "toggle"):
            return youtube_toggle()
        elif act in ("seek", "rewind", "forward"):
            return youtube_seek(seconds)
        elif act in ("next", "skip"):
            return youtube_next()
        elif act in ("previous", "prev", "back"):
            return youtube_previous()
        elif act in ("mute", "unmute"):
            return youtube_mute()
        elif act == "fullscreen":
            return youtube_fullscreen()
        else:
            return f"ERROR: Unknown YouTube action '{action}'. Supported: pause, seek, next, previous, mute, fullscreen."
    except Exception as e:
        import traceback
        return f"ERROR: YouTube control failed for action '{action}': {type(e).__name__}: {e}\n{traceback.format_exc()}"


