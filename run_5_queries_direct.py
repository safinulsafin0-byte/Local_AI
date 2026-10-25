import requests
import json
import time

url = 'http://127.0.0.1:8765/api/v1/chat'
headers = {
    'Content-Type': 'application/json',
    'Authorization': 'Bearer auQ_DGOITl7r0p92gR37K0W28pPjE1fR'
}

queries = [
    "so jarvis what's new for today?",
    "play bangla lofi on youtube",
    "youtube a arijit singh search koro",
    "pause the video",
    "who is the current president of USA"
]

for q in queries:
    print('=' * 60)
    print(f"QUERY: {q}")
    t0 = time.time()
    try:
        r = requests.post(url, headers=headers, json={'message': q, 'mode': 'chat', 'stream': True}, stream=True, timeout=120)
        tokens = []
        events = []
        for line in r.iter_lines():
            line_str = line.decode('utf-8', errors='replace')
            if line_str.startswith('data: '):
                evt = json.loads(line_str[6:])
                etype = evt.get('type')
                events.append(etype)
                if etype == 'token':
                    tokens.append(evt.get('text', ''))
                elif etype in ('youtube_play', 'youtube_control', 'tool_start', 'tool_result'):
                    print(f"  [EVENT: {etype}] {evt}")
        dur = time.time() - t0
        print(f"DURATION: {dur:.1f}s")
        print(f"EVENT TYPES: {set(events)}")
        full_text = "".join(tokens)
        print(f"REPLY:\n{full_text}")
    except Exception as e:
        print(f"ERROR: {e}")

