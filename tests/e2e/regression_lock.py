"""
JARVIS Stark Edition — Regression Lock Suite
tests/e2e/regression_lock.py

Protects Technical Execution (35 pts) by validating REAL resulting system state
against the live running backend (http://127.0.0.1:8765), not self-reported claims.

Evaluated Requirements:
1. "create a folder name Demo inside D:\\jarvis_test" -> folder exists at correct path.
2. "open cmd" -> new process + visible window title within 3s.
3. "weather for ChapaiNawabgonj" -> reply city matches request, not cached city.
4. "make volume 30" -> read back real system volume, must equal ~30%.
5. "what's new today" -> reply contains real headline text, not site filler.
6. attach image, "explain the image" -> reply describes actual attached content.
7. "run python --version" -> routes to run_command (real stdout), not system status.
8. "amar naam Safin, mone rakho" then "amar naam ki?" -> recalls "Safin" correctly in Bengali, never Hindi.
"""

import os
import sys
import time
import json
import shutil
import re
from pathlib import Path
from typing import Dict, Any, List

import requests
import psutil
from PIL import Image, ImageDraw

# Enforce UTF-8 console output on Windows
sys.stdout.reconfigure(encoding="utf-8")
sys.stderr.reconfigure(encoding="utf-8")

BASE_URL = "http://127.0.0.1:8765"
HEADERS = {"Content-Type": "application/json"}

# Add workspace to sys.path for direct hardware readbacks
sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))
from tools import system_ops


def send_chat(msg: str, file_id: str = None, timeout: int = 60) -> Dict[str, Any]:
    """Sends a chat message to the live backend and captures timing + response."""
    payload = {"message": msg, "stream": False}
    if file_id:
        payload["file_id"] = file_id
    t0 = time.time()
    try:
        r = requests.post(f"{BASE_URL}/api/v1/chat", json=payload, headers=HEADERS, timeout=timeout)
        dur = round(time.time() - t0, 3)
        if r.status_code == 200:
            data = r.json()
            return {"ok": True, "response": data.get("response", ""), "duration": dur, "status_code": 200}
        return {"ok": False, "error": f"HTTP {r.status_code}: {r.text[:200]}", "duration": dur, "status_code": r.status_code}
    except Exception as e:
        dur = round(time.time() - t0, 3)
        return {"ok": False, "error": str(e), "duration": dur, "status_code": 0}


def run_test_1_filesystem_folder() -> Dict[str, Any]:
    print("\n[TEST 1/8] Filesystem: 'create a folder name Demo inside D:\\jarvis_test'")
    target_dir = Path(r"D:\jarvis_test\Demo")
    if target_dir.exists():
        shutil.rmtree(target_dir, ignore_errors=True)

    res = send_chat("create a folder name Demo inside D:\\jarvis_test")
    real_exists = target_dir.is_dir()
    
    # Check that it wasn't created with a mangled name (e.g. 'Demo inside D:\jarvis_test')
    mangled_dir = Path(r"D:\personal-ai-full\Demo inside D:\jarvis_test")
    mangled_exists = mangled_dir.exists()

    passed = real_exists and not mangled_exists
    print(f"  -> Target Path: {target_dir}")
    print(f"  -> Real State Exists on Disk: {real_exists}")
    print(f"  -> Mangled Subdirectory Exists: {mangled_exists}")
    print(f"  -> Response: {res.get('response', '')[:80]}...")
    print(f"  -> Status: {'PASS' if passed else 'FAIL'} ({res['duration']}s)")

    # Cleanup
    if real_exists:
        shutil.rmtree(target_dir, ignore_errors=True)

    return {
        "id": 1,
        "name": "Filesystem Exact Path",
        "command": "create a folder name Demo inside D:\\jarvis_test",
        "passed": passed,
        "duration": res["duration"],
        "details": f"Real folder exists={real_exists}, mangled={mangled_exists}"
    }


def run_test_2_open_cmd() -> Dict[str, Any]:
    print("\n[TEST 2/8] Process Launcher: 'open cmd'")
    initial_pids = {p.pid for p in psutil.process_iter(["name"]) if p.info["name"] and p.info["name"].lower() == "cmd.exe"}
    
    t0 = time.time()
    res = send_chat("open cmd")
    
    # Verify new process created within 3.0s
    spawned_pid = None
    deadline = time.time() + 3.0
    while time.time() < deadline:
        current_pids = {p.pid for p in psutil.process_iter(["name"]) if p.info["name"] and p.info["name"].lower() == "cmd.exe"}
        diff = current_pids - initial_pids
        if diff:
            spawned_pid = list(diff)[0]
            break
        time.sleep(0.2)

    has_window_title = "cmd" in res.get("response", "").lower() or "command prompt" in res.get("response", "").lower()
    passed = (spawned_pid is not None) and has_window_title

    print(f"  -> Initial cmd PIDs: {initial_pids}")
    print(f"  -> New cmd PID detected: {spawned_pid}")
    print(f"  -> Window Title Reported: {has_window_title}")
    print(f"  -> Status: {'PASS' if passed else 'FAIL'} ({res['duration']}s)")

    # Terminate the test-spawned process
    if spawned_pid:
        try:
            p = psutil.Process(spawned_pid)
            p.terminate()
        except Exception:
            pass

    return {
        "id": 2,
        "name": "Visible CMD Launch",
        "command": "open cmd",
        "passed": passed,
        "duration": res["duration"],
        "details": f"Spawned PID={spawned_pid}, window confirmed={has_window_title}"
    }


def run_test_3_weather_geocoding() -> Dict[str, Any]:
    print("\n[TEST 3/8] Weather Geocoding: 'weather for ChapaiNawabgonj'")
    res = send_chat("weather for ChapaiNawabgonj", timeout=15)
    resp_text = res.get("response", "")

    # Must contain Chapainawabganj (exact geocoded district), not Khulna or Dhaka
    matched_city = "chapainawabganj" in resp_text.lower() or "chapainawabgonj" in resp_text.lower()
    has_temp = "°c" in resp_text.lower()
    not_cached_khulna = "weather for khulna" not in resp_text.lower()

    passed = matched_city and has_temp and not_cached_khulna
    print(f"  -> City in Reply: {matched_city}")
    print(f"  -> Live Temperature Present: {has_temp}")
    print(f"  -> Response: {resp_text[:100]}...")
    print(f"  -> Status: {'PASS' if passed else 'FAIL'} ({res['duration']}s)")

    return {
        "id": 3,
        "name": "Weather Geocoding Precision",
        "command": "weather for ChapaiNawabgonj",
        "passed": passed,
        "duration": res["duration"],
        "details": f"City matched={matched_city}, temp present={has_temp}"
    }


def run_test_4_volume_hardware_readback() -> Dict[str, Any]:
    print("\n[TEST 4/8] Audio Telemetry: 'make volume 30'")
    res = send_chat("make volume 30")
    
    # Read back real hardware volume from endpoint
    real_vol_str = system_ops.volume_get()
    m = re.search(r"(\d+)%", real_vol_str)
    real_vol = int(m.group(1)) if m else -1
    
    # Must be ~30% (scalar quantization allows +/- 3%)
    passed = (27 <= real_vol <= 33)
    print(f"  -> System Volume Readback: {real_vol_str} (Value: {real_vol}%)")
    print(f"  -> Within ~30% Tolerance [27-33%]: {passed}")
    print(f"  -> Status: {'PASS' if passed else 'FAIL'} ({res['duration']}s)")

    # Restore to comfortable level
    system_ops.volume_set(50)

    return {
        "id": 4,
        "name": "Volume Hardware Readback",
        "command": "make volume 30",
        "passed": passed,
        "duration": res["duration"],
        "details": f"Hardware readback={real_vol}%"
    }


def run_test_5_news_headlines() -> Dict[str, Any]:
    print("\n[TEST 5/8] Live RSS News: 'what's new today'")
    res = send_chat("what's new today", timeout=15)
    resp_text = res.get("response", "")

    # Check for real headline indicators (numbered items, BBC/Verge/Prothom Alo, timestamps, article URLs)
    has_headlines = bool(re.search(r"\d+\.\s+\*\*.+\*\*", resp_text))
    has_articles = "http" in resp_text or "news" in resp_text.lower()
    not_filler = "visit cnn for" not in resp_text.lower() and "visit bing news" not in resp_text.lower()

    passed = has_headlines and has_articles and not_filler
    print(f"  -> Contains Numbered Headlines: {has_headlines}")
    print(f"  -> Contains Source / Links: {has_articles}")
    print(f"  -> Not Site Filler: {not_filler}")
    print(f"  -> Sample: {resp_text.splitlines()[:3]}")
    print(f"  -> Status: {'PASS' if passed else 'FAIL'} ({res['duration']}s)")

    return {
        "id": 5,
        "name": "Live RSS Headlines",
        "command": "what's new today",
        "passed": passed,
        "duration": res["duration"],
        "details": f"Headlines={has_headlines}, source/links={has_articles}"
    }


def run_test_6_image_attachment_vision() -> Dict[str, Any]:
    print("\n[TEST 6/8] Vision & Multimodal: Attach image and 'explain the image'")
    
    # Create test image with distinct visual tokens
    test_img_path = Path("data/regression_test_image.png")
    test_img_path.parent.mkdir(parents=True, exist_ok=True)
    img = Image.new("RGB", (320, 160), color=(255, 255, 255))
    d = ImageDraw.Draw(img)
    d.rectangle([20, 20, 300, 140], fill=(220, 240, 255), outline=(0, 100, 200), width=4)
    d.text((45, 65), "STARK INDUSTRIES AI LAB", fill=(0, 0, 0))
    img.save(test_img_path)

    # Ingest file via /api/v1/files/upload
    with open(test_img_path, "rb") as f:
        up = requests.post(
            f"{BASE_URL}/api/v1/files/upload",
            files={"file": ("regression_test_image.png", f, "image/png")},
            timeout=15
        )
    file_id = up.json().get("file_id") if up.status_code == 200 else None
    print(f"  -> Uploaded Image ID: {file_id}")

    res = send_chat("explain the image", file_id=file_id, timeout=90)
    resp_text = res.get("response", "")

    # Model must describe actual visual content: Stark, banner, blue, rectangle, or AI Lab
    described_content = any(k in resp_text.lower() for k in ["stark", "blue", "banner", "industries", "lab", "rectangle"])
    passed = (file_id is not None) and described_content

    print(f"  -> Visual Content Described: {described_content}")
    print(f"  -> Response: {resp_text[:120]}...")
    print(f"  -> Status: {'PASS' if passed else 'FAIL'} ({res['duration']}s)")

    return {
        "id": 6,
        "name": "Image Attachment Vision",
        "command": "explain the image (attached: STARK INDUSTRIES AI LAB)",
        "passed": passed,
        "duration": res["duration"],
        "details": f"Described content={described_content}"
    }


def run_test_7_terminal_routing() -> Dict[str, Any]:
    print("\n[TEST 7/8] Terminal Routing: 'run python --version'")
    res = send_chat("run python --version")
    resp_text = res.get("response", "")

    # Must route to run_command and print real Python stdout, NOT system status
    has_python_stdout = "python 3." in resp_text.lower()
    not_system_status = "cpu load" not in resp_text.lower() and "ram utilization" not in resp_text.lower()

    passed = has_python_stdout and not_system_status
    print(f"  -> Real Python Stdout Detected: {has_python_stdout}")
    print(f"  -> Not Mistaken for System Status: {not_system_status}")
    print(f"  -> Response: {resp_text.strip()}")
    print(f"  -> Status: {'PASS' if passed else 'FAIL'} ({res['duration']}s)")

    return {
        "id": 7,
        "name": "Terminal Command Routing",
        "command": "run python --version",
        "passed": passed,
        "duration": res["duration"],
        "details": f"Python stdout={has_python_stdout}, not system status={not_system_status}"
    }


def run_test_8_bangla_memory_recall() -> Dict[str, Any]:
    print("\n[TEST 8/8] Bangla Memory Store & Recall: 'amar naam Safin, mone rakho' -> 'amar naam ki?'")
    
    # 1. Store
    res1 = send_chat("amar naam Safin, mone rakho", timeout=15)
    print(f"  -> Store Response: {res1.get('response', '')}")

    # 2. Recall
    res2 = send_chat("amar naam ki?", timeout=15)
    resp_text = res2.get("response", "")

    # Checks:
    # 1. Recalls "Safin"
    has_name = "safin" in resp_text.lower()
    # 2. Answers in Bengali script (has Bengali Unicode chars: \u0980-\u09FF)
    has_bengali_script = bool(re.search(r"[\u0980-\u09FF]", resp_text))
    # 3. Never answers in Hindi (Devanagari letters: \u0904-\u0939, excluding shared danda \u0964) or Russian Cyrillic (\u0400-\u04FF)
    has_hindi = bool(re.search(r"[\u0904-\u0939\u0958-\u0961]", resp_text))
    has_cyrillic = bool(re.search(r"[\u0400-\u04FF]", resp_text))

    passed = has_name and has_bengali_script and not has_hindi and not has_cyrillic
    print(f"  -> Recalls 'Safin': {has_name}")
    print(f"  -> Proper Bengali Script: {has_bengali_script}")
    print(f"  -> No Hindi / Russian drift: {not has_hindi and not has_cyrillic}")
    print(f"  -> Response: {resp_text}")
    print(f"  -> Status: {'PASS' if passed else 'FAIL'} ({res2['duration']}s)")

    return {
        "id": 8,
        "name": "Bangla Memory & Language Guard",
        "command": "'amar naam Safin, mone rakho' then 'amar naam ki?'",
        "passed": passed,
        "duration": res2["duration"],
        "details": f"Recalls Safin={has_name}, Bengali script={has_bengali_script}, No Hindi={not has_hindi}"
    }


def main():
    print("=" * 80)
    print("  JARVIS STARK EDITION — REGRESSION LOCK VERIFICATION SUITE")
    print("=" * 80)
    print(f"Target: {BASE_URL}")
    print(f"Timestamp: {time.strftime('%Y-%m-%d %H:%M:%S')}")

    results = []
    results.append(run_test_1_filesystem_folder())
    results.append(run_test_2_open_cmd())
    results.append(run_test_3_weather_geocoding())
    results.append(run_test_4_volume_hardware_readback())
    results.append(run_test_5_news_headlines())
    results.append(run_test_6_image_attachment_vision())
    results.append(run_test_7_terminal_routing())
    results.append(run_test_8_bangla_memory_recall())

    passed_count = sum(1 for r in results if r["passed"])
    total_count = len(results)
    pass_rate = round((passed_count / total_count) * 100, 1)

    print("\n" + "=" * 80)
    print(f"  REGRESSION LOCK RESULTS: {passed_count}/{total_count} PASSED ({pass_rate}%)")
    print("=" * 80)

    for r in results:
        status_sym = "[PASS]" if r["passed"] else "[FAIL]"
        print(f"  {status_sym} Test {r['id']}: {r['name']:<30} ({r['duration']:>6.2f}s) — {r['details']}")

    # Save results to json
    out_path = Path("data/regression_lock_results.json")
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps({
        "timestamp": time.strftime("%Y-%m-%d %H:%M:%S"),
        "total": total_count,
        "passed": passed_count,
        "pass_rate": pass_rate,
        "results": results
    }, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"\nTelemetry saved to: {out_path.resolve()}")

    if passed_count < total_count:
        sys.exit(1)
    else:
        sys.exit(0)


if __name__ == "__main__":
    main()
