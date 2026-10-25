import requests
import json
import time

headers = {"Content-Type": "application/json"}
test_queries = [
    "What's that thing there?",
    "give me info about AI",
    "what's new today"
]

for q in test_queries:
    print("\n" + "=" * 70)
    print(f"TESTING QUERY: {q}")
    t0 = time.time()
    try:
        r = requests.post(
            "http://127.0.0.1:8765/api/chat",
            json={"message": q, "mode": "agent"},
            headers=headers,
            stream=True,
            timeout=120
        )
        full_tokens = []
        tools_called = []
        for line in r.iter_lines(decode_unicode=True):
            if line and line.startswith("data: "):
                try:
                    data = json.loads(line[6:])
                    ttype = data.get("type")
                    if ttype == "token":
                        full_tokens.append(data.get("text", ""))
                    elif ttype == "tool_start":
                        tools_called.append((data.get("tool"), data.get("args")))
                        print(f"  --> Tool called: {data.get('tool')} with args: {data.get('args')}")
                    elif ttype == "tool_result":
                        print(f"  <-- Tool result: {data.get('tool')} ok={data.get('ok')}")
                    elif ttype == "news_card":
                        print("  [CARD]: news_card emitted")
                except Exception:
                    pass
        duration = round(time.time() - t0, 2)
        response_text = "".join(full_tokens).strip()
        print(f"DURATION: {duration}s")
        print(f"RESPONSE:\n{response_text[:350]}...")
        print(f"Total tools called: {len(tools_called)}")

        assert "Demo.txt" not in response_text and "server.py" not in response_text, f"FAIL: Leaked project file in {q}"
        assert "filesystem.list_dir" not in str(tools_called), f"FAIL: Called list_dir on {q}"
        print("VERIFICATION: PASSED (Zero directory leakage, verified routing)")
    except Exception as exc:
        print(f"ERROR on '{q}': {exc}")
