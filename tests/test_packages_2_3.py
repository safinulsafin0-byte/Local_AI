"""
Test Suite for JARVIS Packages 2 & 3:
- Package 2: Sidebar Chat Management & Deletion (Single delete, Clear all, Undo, Server persistence)
- Package 3: Clean Start & Empty Chat Prevention (New chat on start, never store empty chats, no duplicates)
"""

import os
import sys
import json
import time
import requests
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BASE_DIR))

API_URL = "http://127.0.0.1:8765"
CONV_DIR = BASE_DIR / "data" / "conversations"

# Read token from .env
TOKEN = ""
env_file = BASE_DIR / ".env"
if env_file.exists():
    for line in env_file.read_text(encoding="utf-8").splitlines():
        if line.startswith("JARVIS_TOKEN="):
            TOKEN = line.split("=", 1)[1].strip().strip('"\'')
            break

HEADERS = {"Authorization": f"Bearer {TOKEN}"} if TOKEN else {}


def log_test(name, passed, details=""):
    mark = "PASS" if passed else "FAIL"
    print(f"[{mark}] {name} {details}")
    if not passed:
        sys.exit(1)


def test_packages_2_and_3():
    print("=" * 60)
    print("RUNNING TESTS FOR PACKAGE 2 & PACKAGE 3")
    print("=" * 60)

    # 1. Clean slate for test
    r = requests.delete(f"{API_URL}/api/v1/conversations", headers=HEADERS)
    assert r.status_code == 200, f"Clear all failed: {r.text}"
    log_test("Pre-test clean conversations", True)

    # 2. Create 3 chats on server
    chat_ids = ["test_conv_alpha", "test_conv_beta", "test_conv_gamma"]
    for i, cid in enumerate(chat_ids):
        payload = {
            "id": cid,
            "title": f"Conversation {i+1}",
            "messages": [
                {"role": "user", "content": f"Hello {i+1}"},
                {"role": "assistant", "content": f"Hi there from assistant {i+1}"}
            ],
            "ts": time.time() * 1000 + i * 100
        }
        r = requests.post(f"{API_URL}/api/v1/conversations", headers=HEADERS, json=payload)
        assert r.status_code == 200, f"Failed creating {cid}: {r.text}"
        assert (CONV_DIR / f"{cid}.json").exists(), f"File for {cid} not created on disk"
    log_test("Create 3 chats and verify files on disk", True, "Created: " + ", ".join(chat_ids))

    # 3. List conversations
    r = requests.get(f"{API_URL}/api/v1/conversations", headers=HEADERS)
    assert r.status_code == 200, f"List failed: {r.text}"
    data = r.json()
    assert data.get("ok"), "Response not ok"
    convs = data.get("conversations", [])
    assert len(convs) >= 3, f"Expected at least 3 convs, got {len(convs)}"
    retrieved_ids = [c["id"] for c in convs]
    for cid in chat_ids:
        assert cid in retrieved_ids, f"{cid} not found in retrieved conversations"
    log_test("List conversations returns all 3", True, f"Count={len(convs)}")

    # 4. Delete 1 chat
    target = chat_ids[1]  # test_conv_beta
    r = requests.delete(f"{API_URL}/api/v1/conversations/{target}", headers=HEADERS)
    assert r.status_code == 200, f"Delete failed: {r.text}"
    assert not (CONV_DIR / f"{target}.json").exists(), f"File for {target} still exists on disk"

    # Verify 404 on get
    r = requests.get(f"{API_URL}/api/v1/conversations/{target}", headers=HEADERS)
    assert r.status_code == 404, f"Expected 404 for deleted chat, got {r.status_code}"

    # Verify list now has 2
    r = requests.get(f"{API_URL}/api/v1/conversations", headers=HEADERS)
    data = r.json()
    convs = data.get("conversations", [])
    retrieved_ids = [c["id"] for c in convs]
    assert target not in retrieved_ids, f"Deleted {target} still in list"
    assert chat_ids[0] in retrieved_ids and chat_ids[2] in retrieved_ids
    log_test("Delete single chat unlinks file & updates list", True, f"Deleted: {target}")

    # 5. Undo / Restore the deleted chat
    restore_payload = {
        "id": target,
        "title": "Conversation 2 (Restored)",
        "messages": [
            {"role": "user", "content": "Hello 2 restored"},
            {"role": "assistant", "content": "Restored message"}
        ],
        "ts": time.time() * 1000
    }
    r = requests.post(f"{API_URL}/api/v1/conversations", headers=HEADERS, json=restore_payload)
    assert r.status_code == 200, f"Restore failed: {r.text}"
    assert (CONV_DIR / f"{target}.json").exists(), f"File {target} was not recreated"
    log_test("Undo/Restore chat re-creates server conversation", True)

    # 6. Test Clear all chats
    r = requests.delete(f"{API_URL}/api/v1/conversations", headers=HEADERS)
    assert r.status_code == 200, f"Clear all failed: {r.text}"
    remaining_files = list(CONV_DIR.glob("*.json"))
    assert len(remaining_files) == 0, f"Expected 0 json files after clear all, found {len(remaining_files)}"

    r = requests.get(f"{API_URL}/api/v1/conversations", headers=HEADERS)
    data = r.json()
    assert len(data.get("conversations", [])) == 0, "Conversations list not empty after clear all"
    log_test("Clear all removes all files and empties list", True)

    # 7. Frontend code contract check (web/index.html)
    index_html = (BASE_DIR / "web" / "index.html").read_text(encoding="utf-8")

    # Contract checks
    assert "openDeletePopover(" in index_html, "Missing openDeletePopover in index.html"
    assert "confirmDeleteChat(" in index_html, "Missing confirmDeleteChat in index.html"
    assert "openChatContextMenu(" in index_html, "Missing openChatContextMenu in index.html"
    assert "renameChatPrompt(" in index_html, "Missing renameChatPrompt in index.html"
    assert "openClearAllConfirm(" in index_html, "Missing openClearAllConfirm in index.html"
    assert "confirmClearAll(" in index_html, "Missing confirmClearAll in index.html"
    assert "showUndoToast(" in index_html, "Missing showUndoToast in index.html"
    assert "undoDeleteChat(" in index_html, "Missing undoDeleteChat in index.html"
    assert 'chat-delete-popover' in index_html, "Missing #chat-delete-popover in index.html"
    assert 'clear-all-popover' in index_html, "Missing #clear-all-popover in index.html"
    assert 'chat-context-menu' in index_html, "Missing #chat-context-menu in index.html"
    assert 'undo-toast' in index_html, "Missing #undo-toast in index.html"
    assert 'setting-on-start' in index_html, "Missing #setting-on-start in index.html"
    assert "if (!chatHistory || chatHistory.length === 0) return;" in index_html, "Missing empty chat guard in index.html"
    assert "jarvis_on_start" in index_html, "Missing jarvis_on_start preference handling in index.html"

    log_test("Frontend code contract check (Package 2 & 3)", True, "All popovers, toasts, empty-guards verified")

    print("\n" + "=" * 60)
    print("ALL TESTS FOR PACKAGE 2 & PACKAGE 3 PASSED!")
    print("=" * 60)


if __name__ == "__main__":
    test_packages_2_and_3()

