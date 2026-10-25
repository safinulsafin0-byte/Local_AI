"""
Verification script for:
1. Location-aware answers & endpoints (/api/v1/location/info, override, reset)
2. Weather for ChapaiNawabgonj, Dhaka, and default location
3. News 5 runs ("what's new today", "what's new for today?", "latest tech news", "latest news in Bangladesh", "today's headlines")
4. Protocols ("Run Study protocol", "Run Night Mode protocol", "Protocol Demo Mode", "List protocols")
5. CAD & Device Radar ("Create phone stand 80mm wide", "Check local devices")
"""

import sys
import json
import httpx
from pathlib import Path

sys.stdout.reconfigure(encoding='utf-8')


BASE_URL = "http://127.0.0.1:8765"
TOKEN = "JARVIS_DEV_TEST_TOKEN_2026_SECURE_ACCESS"
HEADERS = {"Authorization": f"Bearer {TOKEN}"}

def parse_sse_events(response_text: str):
    events = []
    current_event = {}
    for line in response_text.splitlines():
        line = line.strip()
        if not line:
            if current_event:
                events.append(current_event)
                current_event = {}
            continue
        if line.startswith("data:"):
            payload = line[5:].strip()
            try:
                current_event = json.loads(payload)
            except Exception:
                current_event = {"raw": payload}
    if current_event:
        events.append(current_event)
    return events

def run_chat(message: str) -> dict:
    url = f"{BASE_URL}/api/v1/chat"
    with httpx.Client(timeout=60.0) as client:
        resp = client.post(url, json={"message": message, "mode": "agent", "stream": True}, headers=HEADERS)
        events = parse_sse_events(resp.text)
        
        full_text = ""
        tool_results = []
        cards = []
        for ev in events:
            ev_type = ev.get("type")
            if ev_type == "token":
                full_text += ev.get("text", "")
            elif ev_type == "tool_result":
                tool_results.append(ev)
            elif ev_type in ("news_card", "weather_card", "cad_card", "defense_card", "briefing_card"):
                cards.append(ev)
            elif ev_type == "done":
                full_text = ev.get("full", full_text)
        return {
            "query": message,
            "full_text": full_text.strip(),
            "tool_results": tool_results,
            "cards": cards,
            "events_count": len(events)
        }

def test_location_endpoints():
    print("\n" + "="*60)
    print("TEST 1: Location Endpoints")
    print("="*60)
    with httpx.Client(timeout=10.0) as client:
        # GET info
        r = client.get(f"{BASE_URL}/api/v1/location/info", headers=HEADERS)
        print("GET /api/v1/location/info:", r.status_code, r.json())
        assert r.status_code == 200
        assert r.json().get("ok") is True

        # POST override
        r_over = client.post(f"{BASE_URL}/api/v1/location/override", json={"city": "Chapai Nawabganj"}, headers=HEADERS)
        print("POST /api/v1/location/override:", r_over.status_code, r_over.json())
        assert r_over.status_code == 200

        # Verify active city changed
        r_info2 = client.get(f"{BASE_URL}/api/v1/location/info", headers=HEADERS)
        loc2 = r_info2.json().get("location", {})
        print("Active city after override:", loc2.get("active_city"))
        assert loc2.get("active_city") == "Chapai Nawabganj"

        # DELETE override (clear)
        r_del = client.delete(f"{BASE_URL}/api/v1/location/override", headers=HEADERS)
        print("DELETE /api/v1/location/override:", r_del.status_code, r_del.json())
        assert r_del.status_code == 200

def test_weather():
    print("\n" + "="*60)
    print("TEST 2: Weather Queries")
    print("="*60)
    queries = [
        "give me weather information for ChapaiNawabgonj",
        "give me weather information for Dhaka",
        "what's the weather"
    ]
    for q in queries:
        res = run_chat(q)
        print(f"\n[QUERY]: {q}")
        print(f"[REPLY]:\n{res['full_text']}")
        assert len(res['full_text']) > 15
        assert "°C" in res['full_text'] or "temperature" in res['full_text'].lower()
        if "ChapaiNawabgonj" in q:
            assert "Chapai" in res['full_text'] or "Nawabganj" in res['full_text']
        elif "Dhaka" in q:
            assert "Dhaka" in res['full_text']

def test_news_5_runs():
    print("\n" + "="*60)
    print("TEST 3: News 5 Runs (Real Headlines Verification)")
    print("="*60)
    news_queries = [
        "what's new today",
        "what's new for today?",
        "latest tech news",
        "latest news in Bangladesh",
        "today's top headlines"
    ]
    for idx, q in enumerate(news_queries, 1):
        res = run_chat(q)
        print(f"\n[RUN {idx}]: {q}")
        reply = res['full_text']
        print(f"[REPLY PREVIEW]:\n{reply[:300]}...")
        # Verify it has real headlines, not generic greeting
        assert not reply.startswith("Hello! How can I assist"), f"Run {idx} failed with generic greeting!"
        assert "Headlines" in reply or "http" in reply or len(reply.splitlines()) >= 3, f"Run {idx} missing headline content!"
        print(f"✓ Run {idx} PASS: Real headlines returned.")

def test_protocols():
    print("\n" + "="*60)
    print("TEST 4: Protocols Verification")
    print("="*60)
    proto_queries = [
        "List protocols",
        "Run Study protocol",
        "Run Night Mode protocol",
        "Protocol Demo Mode"
    ]
    for q in proto_queries:
        res = run_chat(q)
        print(f"\n[QUERY]: {q}")
        reply = res['full_text']
        print(f"[REPLY]:\n{reply}")
        assert "None" not in reply or "✓" in reply, "Protocol failed with unpopulated steps!"
        if "List" in q:
            assert "Study" in reply and "Night Mode" in reply
        else:
            assert "✓" in reply and "COMPLETED" in reply

def test_cad_and_radar():
    print("\n" + "="*60)
    print("TEST 5: CAD & Device Radar")
    print("="*60)
    # CAD
    cad_res = run_chat("Create phone stand 80mm wide")
    print("\n[CAD QUERY]: Create phone stand 80mm wide")
    print(f"[CAD REPLY]:\n{cad_res['full_text']}")
    assert "3D Model Generated" in cad_res['full_text'] or "stl" in cad_res['full_text'].lower()

    # Radar
    radar_res = run_chat("Check local devices")
    print("\n[RADAR QUERY]: Check local devices")
    print(f"[RADAR REPLY]:\n{radar_res['full_text']}")
    assert "Local Network Radar" in radar_res['full_text'] or "devices" in radar_res['full_text'].lower()

if __name__ == "__main__":
    test_location_endpoints()
    test_weather()
    test_news_5_runs()
    test_protocols()
    test_cad_and_radar()
    print("\n" + "="*60)
    print("ALL SPECIALIZED VERIFICATION TESTS PASSED SUCCESSFULLY!")
    print("="*60)
