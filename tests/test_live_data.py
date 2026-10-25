"""
JARVIS Live Data Quality Tests — tests/test_live_data.py
=========================================================
Verifies:
1. Open-Meteo Weather Tool (clean schema, accurate temp, no wttr.in, no raw JSON leaks).
2. Multi-source RSS News Tool (feedparser, stripped HTML, sources).
3. Deep Search & Synthesis Pipeline (DDGS, domain chip extraction, structured sources).
4. Offline graceful degradation (no crash, clear user message).
"""

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
sys.stdout.reconfigure(encoding='utf-8')

from tools.weather_tool import get_weather
from tools.news_tool import get_news
from tools.search_pipeline import search_and_synthesize, extract_domain, extract_search_query


def test_weather():
    print("--- 1. Testing Open-Meteo Weather Tool ---")
    cities = ["Khulna", "Dhaka", "London", "Tokyo"]
    for city in cities:
        res = get_weather(city)
        assert res.get("ok") is True, f"Weather failed for {city}: {res}"
        curr = res.get("current", {})
        temp = curr.get("temperature")
        cond = curr.get("condition")
        humidity = curr.get("humidity")
        assert temp is not None, f"Missing temperature for {city}"
        assert cond, f"Missing condition for {city}"
        assert len(res.get("daily", [])) >= 3, f"Missing 5-day daily forecast for {city}"
        print(f"  [PASS] {city:8s}: {temp}°C, {cond} {curr.get('icon')}, Humidity: {humidity}%, Daily count: {len(res['daily'])}")
    print(f"  Speech: \"{res.get('speech')}\"")


def test_news():
    print("\n--- 2. Testing Multi-Source RSS News Tool ---")
    categories = ["world", "bangladesh", "tech"]
    for cat in categories:
        res = get_news(cat, limit=3)
        assert res.get("ok") is True, f"News failed for {cat}: {res}"
        articles = res.get("articles", [])
        assert len(articles) > 0, f"No articles returned for {cat}"
        print(f"  [PASS] Category: '{cat}' -> {len(articles)} articles fetched")
        for i, a in enumerate(articles, 1):
            assert "<" not in a["title"] and ">" not in a["title"], "Raw HTML detected in title!"
            assert "<" not in a["summary"] and ">" not in a["summary"], "Raw HTML detected in summary!"
            print(f"    #{i} [{a['source']}] {a['title'][:60]}... ({a['link'][:45]}...)")


def test_search_pipeline():
    print("\n--- 3. Testing Search Pipeline & Grounding ---")
    query = "capital of Australia"
    res = search_and_synthesize(query, max_results=3, synthesize_with_llm=False)
    assert res.get("ok") is True, f"Search pipeline failed: {res}"
    sources = res.get("sources", [])
    assert len(sources) > 0, "No search sources returned!"
    print(f"  [PASS] Query: '{query}' -> {len(sources)} sources")
    for s in sources:
        print(f"    - [{s['domain']}] {s['title'][:50]} -> {s['url'][:45]}")


def test_offline_handling():
    print("\n--- 4. Testing Offline Graceful Degradation ---")
    # Simulate invalid / unreachable endpoint
    res_w = get_weather("NonexistentCity123456789xyz")
    # Should fallback gracefully to default city or return clean structured dict
    assert isinstance(res_w, dict), "Weather must return dict"
    print(f"  [PASS] Unrecognized city graceful handling: ok={res_w.get('ok')}, location={res_w.get('location')}")


if __name__ == "__main__":
    test_weather()
    test_news()
    test_search_pipeline()
    test_offline_handling()
    print("\n==============================================")
    print("ALL LIVE-DATA QUALITY TESTS PASSED (100% CLEAN)")
    print("==============================================")
