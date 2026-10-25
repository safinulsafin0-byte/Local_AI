import re
import urllib.request
import urllib.parse
import json
import logging
from typing import Optional, Dict, Any, List, Tuple

logger = logging.getLogger("jarvis.youtube_router")

YOUTUBE_URL_REGEX = re.compile(
    r'https?://(?:www\.)?(?:youtube\.com/(?:watch\?(?:.*&)?v=|embed/|shorts/|live/)|youtu\.be/)([a-zA-Z0-9_-]{11})',
    re.IGNORECASE
)

def extract_youtube_url_and_id(text: str) -> Tuple[Optional[str], Optional[str]]:
    """Extract YouTube URL and 11-char video ID from text if present."""
    if not text:
        return None, None
    m = YOUTUBE_URL_REGEX.search(text)
    if m:
        vid = m.group(1)
        full_url = m.group(0)
        return full_url, vid
    return None, None

def is_embeddable(video_id: str) -> Tuple[bool, str]:
    """Check whether a YouTube video is embeddable using YouTube's official oEmbed endpoint."""
    if not video_id or len(video_id) != 11:
        return False, ""
    try:
        url = f"https://www.youtube.com/oembed?url=https://www.youtube.com/watch?v={video_id}&format=json"
        req = urllib.request.Request(
            url,
            headers={"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"}
        )
        with urllib.request.urlopen(req, timeout=4) as r:
            if r.status == 200:
                data = json.loads(r.read().decode("utf-8", errors="replace"))
                return True, data.get("title", "")
    except Exception as e:
        logger.debug(f"oEmbed check failed for {video_id}: {e}")
    return False, ""

def search_youtube_videos(query: str, max_results: int = 10) -> List[Dict[str, str]]:
    """Search YouTube using yt-dlp ytsearch10:<exact user query> or fallback."""
    results = []
    # 1. Try yt-dlp first with exact query
    try:
        import yt_dlp
        ydl_opts = {
            "quiet": True,
            "extract_flat": True,
            "skip_download": True,
            "no_warnings": True,
        }
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            search_str = f"ytsearch{max_results}:{query}"
            info = ydl.extract_info(search_str, download=False)
            entries = info.get("entries", []) if info else []
            for e in entries:
                if not e:
                    continue
                vid = e.get("id")
                title = e.get("title", "")
                if vid and len(vid) == 11:
                    results.append({"id": vid, "title": title, "url": f"https://www.youtube.com/watch?v={vid}"})
    except Exception as e:
        logger.warning(f"yt-dlp search failed ({e}), falling back to web scrape")

    # 2. Fallback: lightweight YouTube HTML search scrape
    if not results:
        try:
            search_url = f"https://www.youtube.com/results?search_query={urllib.parse.quote(query)}"
            req = urllib.request.Request(search_url, headers={
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
                "Accept-Language": "en-US,en;q=0.9"
            })
            with urllib.request.urlopen(req, timeout=5) as resp:
                html = resp.read().decode("utf-8", errors="replace")
                vid_ids = re.findall(r'"videoId":"([a-zA-Z0-9_-]{11})"', html)
                seen = set()
                for v in vid_ids:
                    if v not in seen:
                        seen.add(v)
                        results.append({"id": v, "title": query, "url": f"https://www.youtube.com/watch?v={v}"})
                        if len(results) >= max_results:
                            break
        except Exception as e:
            logger.error(f"HTML search fallback failed: {e}")

    return results

def get_embeddable_video(query: str, max_results: int = 10) -> Tuple[Optional[Dict[str, str]], List[Dict[str, str]]]:
    """Find the first embeddable video for query and return it along with all candidates.
    Logs query and top 5 titles to server console as required."""
    candidates = search_youtube_videos(query, max_results=max_results)

    # Log query and top 5 titles to server console
    print(f"\n[YouTube Search] Query: \"{query}\"")
    logger.info(f"[YouTube Search] Query: \"{query}\"")
    for idx, c in enumerate(candidates[:5]):
        t_clean = c.get("title", "").encode("ascii", errors="replace").decode("ascii")
        log_line = f"  Top {idx+1}: [{c.get('id')}] {t_clean}"
        print(log_line)
        logger.info(log_line)

    # Check embeddability for each candidate using oEmbed (non-200 = not embeddable)
    for c in candidates:
        ok, title = is_embeddable(c["id"])
        if ok:
            if title:
                c["title"] = title
            return c, candidates

    # If all candidates failed oEmbed, return the first candidate along with list
    if candidates:
        return candidates[0], candidates
    return None, []

def parse_youtube_intent(text: str) -> Optional[Dict[str, Any]]:
    """Parse user text for YouTube intent in exact order:
    1. Summarize flow: summarize/summary/transcript/ki bolche/explain + URL/ID
    2. Media Control Commands: pause/resume/mute/next
    3. Direct URL Play flow: YouTube URL with play/open intent
    4. Play flow: play/chalao/search/khuj/dekhao + query
    """
    if not text:
        return None
    t = text.lower().strip()

    yt_url, yt_vid = extract_youtube_url_and_id(text)

    # ── 1. SUMMARIZE FLOW ──
    # If message contains summarize|summary|transcript|ki bolche|explain AND a YouTube URL/ID
    is_summarize_intent = bool(re.search(
        r'\b(summarize|summary|summarise|transcript|transcribe|ki bolche|explain|bujhie dao|bujhao)\b',
        t,
        re.IGNORECASE
    ))
    if is_summarize_intent and (yt_url or yt_vid or "youtube" in t or "yt" in t):
        target_url = yt_url if yt_url else (f"https://www.youtube.com/watch?v={yt_vid}" if yt_vid else "")
        return {
            "type": "summarize",
            "url": target_url,
            "video_id": yt_vid,
            "raw_text": text
        }

    # ── 2. MEDIA CONTROL COMMANDS ──
    if (re.search(r'\b(pause|stop|thamo|thamao|ruk|roko)\b', t) and any(w in t for w in ['video', 'youtube', 'yt', 'music', 'song', 'playback'])) or t in ['pause', 'stop video', 'pause the video', 'pause video']:
        return {"type": "control", "action": "pause"}
    if re.search(r'\b(resume|unpause|chalu)\b', t) and any(w in t for w in ['video', 'youtube', 'yt', 'music', 'song', 'playback']):
        return {"type": "control", "action": "resume"}
    if re.search(r'\b(mute)\b', t) and any(w in t for w in ['video', 'youtube', 'yt', 'music', 'song', 'playback', 'audio']):
        return {"type": "control", "action": "mute"}
    if re.search(r'\b(next|skip)\b', t) and any(w in t for w in ['video', 'youtube', 'yt', 'song']):
        return {"type": "control", "action": "next"}

    # ── 3. DIRECT URL PLAY / OPEN FLOW ──
    # If user message contains a YouTube URL with play/open/dekhao/chalao intent, extract video ID directly
    has_play_action = bool(re.search(
        r'\b(search|play|open|chalao|khuj|khujo|dekhao|bajao|shuno|koro|listen|watch)\b|খুঁজো|চালাও|দেখাও|বাজাও|শুনো',
        t,
        re.IGNORECASE
    ))
    if yt_vid and (has_play_action or len(t.split()) <= 4):
        ok, title = is_embeddable(yt_vid)
        return {
            "type": "direct_play",
            "video_id": yt_vid,
            "title": title or "YouTube Video",
            "url": yt_url or f"https://www.youtube.com/watch?v={yt_vid}"
        }

    # ── 4. PLAY / SEARCH FLOW ──
    # Matches (youtube|yt|ইউটিউব) + action or play/search ... on youtube
    has_yt = bool(re.search(r'\b(youtube|yt|ইউটিউব)\b|youtube\s*a\b', t))

    if not ((has_yt and has_play_action) or (has_yt and len(t.split()) >= 3) or re.match(r'^(play|search)\s+.+\b(youtube|yt)\b', t) or (t.startswith("play ") and len(t.split()) >= 2)):
        return None

    # Clean query to preserve the exact search intent
    cleaned = text
    # Remove YouTube mentions
    cleaned = re.sub(r'\b(on\s+youtube|on\s+yt|in\s+youtube|in\s+yt|from\s+youtube|from\s+yt|youtube\s+a\b|youtube\s+e\b|youtube|yt|ইউটিউব(ে)?)\b', '', cleaned, flags=re.I)
    # Remove opening action verbs
    cleaned = re.sub(r'^(please\s+|can\s+you\s+|could\s+you\s+)?(search\s+for|search|play|open|listen\s+to|find|chalao|khujo?|dekhao)\s+', '', cleaned.strip(), flags=re.I)
    # Remove trailing particles
    cleaned = re.sub(r'\s+(search\s+koro|koro|korun|chalao|khujo?|dekhao|bajao|shuno|gan)$', '', cleaned.strip(), flags=re.I)
    # Remove leading particles
    cleaned = re.sub(r'^[aA]\s+', '', cleaned.strip())
    query = cleaned.strip(" \t\n\r.,!?:;\"'")
    if not query:
        query = "lofi music"

    return {"type": "play", "query": query}
