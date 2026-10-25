"""
JARVIS Multi-Source RSS News Tool — tools/news_tool.py
======================================================
Fetches live headlines from trusted RSS feeds using feedparser.
Uses httpx with strict timeout and desktop User-Agent to prevent socket hangs.
Sources:
- BBC World News
- Reuters / Google News World
- The Daily Star (Bangladesh)
- Prothom Alo English (Bangladesh)
- TechCrunch / Tech News
- DuckDuckGo News search fallback for custom topical queries.
NEVER emits unparsed raw markup.
"""

from __future__ import annotations

import logging
import re
from typing import Dict, Any, List, Optional
import feedparser
import httpx

logger = logging.getLogger("jarvis.tools.news")

DEFAULT_USER_AGENT = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"

FEEDS = {
    "world": [
        {"name": "BBC News", "url": "https://feeds.bbci.co.uk/news/world/rss.xml"},
        {"name": "Google News", "url": "https://news.google.com/rss/search?q=world+news&hl=en-US&gl=US&ceid=US:en"},
    ],
    "tech": [
        {"name": "TechCrunch", "url": "https://techcrunch.com/feed/"},
        {"name": "The Verge", "url": "https://www.theverge.com/rss/index.xml"},
    ],
    "bangladesh": [
        {"name": "The Daily Star", "url": "https://www.thedailystar.net/frontpage/rss.xml"},
        {"name": "Prothom Alo", "url": "https://en.prothomalo.com/feed"},
    ],
}


def clean_html(text: str) -> str:
    """Removes HTML tags and entities from RSS summaries."""
    if not text:
        return ""
    clean = re.sub(r"<[^>]+>", "", text)
    clean = re.sub(r"&[a-z]+;", " ", clean)
    clean = re.sub(r"\s+", " ", clean).strip()
    return clean


def get_news(topic: str = "", limit: int = 5, timeout: float = 2.0) -> Dict[str, Any]:
    """
    Fetches latest news articles for a category or custom topic.
    Returns structured articles with titles, sources, links, and clean summaries.
    """
    topic_clean = (topic or "").strip().lower()

    # Determine feed category
    category = "world"
    if any(w in topic_clean for w in ("bangladesh", "bd", "dhaka", "khulna", "দেশ", "বাংলাদেশ")):
        category = "bangladesh"
    elif any(w in topic_clean for w in ("tech", "technology", "ai", "software", "computer")):
        category = "tech"

    feed_list = FEEDS.get(category, FEEDS["world"])
    articles: List[Dict[str, Any]] = []

    with httpx.Client(timeout=timeout, headers={"User-Agent": DEFAULT_USER_AGENT}, follow_redirects=True) as client:
        for f_info in feed_list:
            feed_url = f_info["url"]
            source_name = f_info["name"]
            try:
                resp = client.get(feed_url)
                if resp.status_code == 200:
                    feed = feedparser.parse(resp.text)
                    for entry in feed.entries[:limit]:
                        title = clean_html(entry.get("title", ""))
                        link = entry.get("link", "")
                        published = entry.get("published", "") or entry.get("updated", "")
                        summary = clean_html(entry.get("summary", "") or entry.get("description", ""))
                        if len(summary) > 200:
                            summary = summary[:197] + "..."

                        if title and link:
                            articles.append({
                                "title": title,
                                "source": source_name,
                                "link": link,
                                "published": published,
                                "summary": summary,
                            })
                        if len(articles) >= limit:
                            break
            except Exception as e:
                logger.warning(f"Error fetching feed {feed_url}: {e}")

            if len(articles) >= limit:
                break

    # If category RSS yielded no items (or custom topic searched), try DuckDuckGo News
    if not articles and topic_clean:
        try:
            from tools.web_tools import DDGS, DDGS_OK
            if DDGS_OK:
                with DDGS() as ddgs:
                    ddg_news = list(ddgs.news(topic_clean, max_results=limit))
                    for a in ddg_news:
                        articles.append({
                            "title": a.get("title", ""),
                            "source": a.get("source", "DuckDuckGo"),
                            "link": a.get("url", "") or a.get("link", ""),
                            "published": a.get("date", ""),
                            "summary": clean_html(a.get("body", "")),
                        })
        except Exception as exc:
            logger.warning(f"DDG news fallback failed: {exc}")

    if not articles:
        return {
            "ok": False,
            "error": "offline",
            "message": "News feeds are currently unavailable offline. Please check your internet connection.",
            "articles": []
        }

    # Generate speech summary
    speech_lines = [f"Here are the latest news headlines:"]
    for i, a in enumerate(articles[:3], 1):
        speech_lines.append(f"{i}. {a['title']} from {a['source']}.")

    return {
        "ok": True,
        "topic": topic or category,
        "count": len(articles),
        "articles": articles[:limit],
        "speech": " ".join(speech_lines),
    }

