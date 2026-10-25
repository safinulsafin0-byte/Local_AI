import os
import sys
import json
import io
import urllib.request
import urllib.error
from PIL import Image

TOKEN = "auQ_DGOIXStCxeEr17J2Tb5ELOjfYgr4Mov8GUwjKsA"
BASE_URL = "http://127.0.0.1:8765"

def test_health():
    req = urllib.request.Request(f"{BASE_URL}/health")
    with urllib.request.urlopen(req) as resp:
        data = json.loads(resp.read().decode())
        print(f"[HEALTH] status={resp.status}, ok={data.get('ok')}")
        assert data.get("ok") is True

def test_attachment_upload_and_view():
    print("\n--- Testing BUG 4: Attachment Upload, View & Vision Prompt ---")
    # 1. Create a simple test image
    img = Image.new("RGB", (100, 100), color=(73, 109, 137))
    img_byte_arr = io.BytesIO()
    img.save(img_byte_arr, format='PNG')
    img_bytes = img_byte_arr.getvalue()

    # 2. Upload via multipart/form-data
    boundary = "----WebKitFormBoundary7MA4YWxkTrZu0gW"
    body = (
        f"--{boundary}\r\n"
        f'Content-Disposition: form-data; name="file"; filename="test_demo.png"\r\n'
        f"Content-Type: image/png\r\n\r\n"
    ).encode("utf-8") + img_bytes + f"\r\n--{boundary}--\r\n".encode("utf-8")

    req = urllib.request.Request(
        f"{BASE_URL}/api/v1/files/upload",
        data=body,
        headers={
            "Content-Type": f"multipart/form-data; boundary={boundary}",
            "Authorization": f"Bearer {TOKEN}"
        }
    )
    with urllib.request.urlopen(req) as resp:
        upload_res = json.loads(resp.read().decode())
        print(f"[UPLOAD] Response: {upload_res}")
        attachment_id = upload_res.get("attachment_id") or upload_res.get("file_id")
        assert attachment_id, "No attachment_id returned"

    # 3. Test viewing the uploaded file via GET /api/v1/files/{file_id}/view
    view_req = urllib.request.Request(
        f"{BASE_URL}/api/v1/files/{attachment_id}/view",
        headers={"Authorization": f"Bearer {TOKEN}"}
    )
    with urllib.request.urlopen(view_req) as resp:
        content_type = resp.headers.get("Content-Type")
        view_bytes = resp.read()
        print(f"[VIEW] Status: {resp.status}, Content-Type: {content_type}, Size: {len(view_bytes)} bytes")
        assert resp.status == 200
        assert len(view_bytes) == len(img_bytes)

    import uuid

    # 4. Send chat message with attachment_ids
    turn_id = f"test-turn-attach-{uuid.uuid4().hex[:8]}"
    chat_payload = {
        "message": "Please describe what is shown in this attached image.",
        "attachment_ids": [attachment_id],
        "turn_id": turn_id
    }
    chat_req = urllib.request.Request(
        f"{BASE_URL}/api/v1/chat",
        data=json.dumps(chat_payload).encode("utf-8"),
        headers={
            "Content-Type": "application/json",
            "Authorization": f"Bearer {TOKEN}"
        }
    )
    
    events = []
    with urllib.request.urlopen(chat_req) as resp:
        while True:
            line = resp.readline()
            if not line:
                break
            line_str = line.decode("utf-8", errors="ignore").strip()
            if line_str.startswith("data:"):
                payload_str = line_str[5:].strip()
                if payload_str:
                    try:
                        evt = json.loads(payload_str)
                        events.append(evt)
                        if evt.get("type") == "token":
                            print(f"[TOKEN] {evt.get('text')}", end="", flush=True)
                    except Exception:
                        pass
            if len(events) > 8 and any(e.get("type") == "token" for e in events):
                print("\n[STREAM] Received tokens successfully, breaking early.", flush=True)
                break

    print(f"[CHAT] Received {len(events)} SSE events with attachment")
    
    # 5. Check last_prompt.json
    prompt_file = os.path.join("data", "debug", "last_prompt.json")
    if os.path.exists(prompt_file):
        with open(prompt_file, "r", encoding="utf-8") as f:
            last_prompt = json.load(f)
            print(f"[DEBUG PROMPT] Saved at {prompt_file}:")
            print(f"  File ID: {last_prompt.get('file_id')}")
            print(f"  Kind: {last_prompt.get('kind')}")
            assert last_prompt.get("file_id") == attachment_id, "Attachment ID does not match in prompt"
            print("  [SUCCESS] Attachment ID correctly verified in model input prompt!")
    else:
        print(f"[WARN] {prompt_file} not found")

def test_live_filesystem_chat():
    print("\n--- Testing BUG 1 & BUG 2 via Chat Stream ---")
    import uuid
    chat_payload = {
        "message": r"create a folder name Demo inside D:\jarvis_test",
        "turn_id": f"test-turn-fs-{uuid.uuid4().hex[:8]}"
    }
    chat_req = urllib.request.Request(
        f"{BASE_URL}/api/v1/chat",
        data=json.dumps(chat_payload).encode("utf-8"),
        headers={
            "Content-Type": "application/json",
            "Authorization": f"Bearer {TOKEN}"
        }
    )
    
    tool_results = []
    tokens = []
    with urllib.request.urlopen(chat_req) as resp:
        while True:
            line = resp.readline()
            if not line:
                break
            line_str = line.decode("utf-8", errors="ignore").strip()
            if line_str.startswith("data:"):
                payload_str = line_str[5:].strip()
                if payload_str:
                    try:
                        evt = json.loads(payload_str)
                        if evt.get("type") == "tool_result":
                            tool_results.append(evt)
                        elif evt.get("type") == "token":
                            tokens.append(evt.get("text", ""))
                    except Exception:
                        pass

    print(f"[FS CHAT] Tool results: {tool_results}")
    print(f"[FS CHAT] Tokens response snippet: {''.join(tokens)[:120]}...")
    target_dir = r"D:\jarvis_test\Demo"
    exists = os.path.isdir(target_dir)
    print(f"[FS CHAT] Verification on disk: {target_dir} exists = {exists}")
    assert exists, f"Directory {target_dir} was not created"
    if tool_results:
        assert tool_results[0].get("ok") is True, f"Tool result ok is not True: {tool_results[0]}"

if __name__ == "__main__":
    test_health()
    test_attachment_upload_and_view()
    test_live_filesystem_chat()
    print("\nALL LIVE TESTS PASSED!")
