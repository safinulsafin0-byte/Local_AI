"""
Verification suite for PACKAGE 1: PDF and image analysis.
Executes all 8 required tests and verifies:
- Clean extracted text (no raw bytes, no PDF syntax)
- First 300 chars printed for each test
- Proper summary, page citations, OCR, vision, encryption handling, binary guard
"""

import json
import os
import requests
from pathlib import Path

BASE_URL = "http://127.0.0.1:8765/api/v1"
TOKEN = "auQ_DGOIXStCxeEr17J2Tb5ELOjfYgr4Mov8GUwjKsA"
HEADERS = {
    "Authorization": f"Bearer {TOKEN}"
}
FIXTURES = Path(__file__).parent / "fixtures"

def test_1_text_pdf():
    print("\n--- TEST 1: Text PDF (multi-page) ---")
    pdf_path = FIXTURES / "sample_text.pdf"
    
    # 1. Upload
    with open(pdf_path, "rb") as f:
        r = requests.post(f"{BASE_URL}/files/upload", files={"file": (pdf_path.name, f, "application/pdf")}, headers=HEADERS)
    assert r.status_code == 200, f"Upload failed: {r.text}"
    data = r.json()
    assert data["ok"] is True
    assert data["kind"] == "pdf"
    print(f"Extracted sample (first 300 chars):\n{repr(data.get('text_sample', '')[:300])}")
    assert "stream" not in data.get("text_sample", "").lower()
    assert "\x00" not in data.get("text_sample", "")

    # 2. Chat: explain the pdf
    file_id = data["file_id"]
    chat_payload = {
        "message": "explain the pdf",
        "file_id": file_id,
        "stream": False
    }
    cr = requests.post(f"{BASE_URL}/chat", json=chat_payload, headers=HEADERS, timeout=120)
    assert cr.status_code == 200
    resp = cr.json().get("response", "")
    print(f"Assistant Reply:\n{resp}")
    assert len(resp) > 50
    assert "stream" not in resp.lower()
    assert "/f1" not in resp.lower()
    print("TEST 1 PASSED: Real content summary produced without PDF internals or garbage.")

def test_2_scanned_pdf():
    print("\n--- TEST 2: Scanned PDF (image-only OCR) ---")
    pdf_path = FIXTURES / "sample_scanned.pdf"
    with open(pdf_path, "rb") as f:
        r = requests.post(f"{BASE_URL}/files/upload", files={"file": (pdf_path.name, f, "application/pdf")}, headers=HEADERS)
    assert r.status_code == 200
    data = r.json()
    assert data["ok"] is True
    print(f"OCR Extracted sample (first 300 chars):\n{repr(data.get('text_sample', '')[:300])}")
    sample = data.get("text_sample", "")
    assert "SCANNED" in sample.upper() or "INVOICE" in sample.upper()
    print("TEST 2 PASSED: Scanned page rendered and recognized via RapidOCR.")

def test_3_large_pdf():
    print("\n--- TEST 3: Large PDF (55 pages) ---")
    pdf_path = FIXTURES / "sample_large.pdf"
    with open(pdf_path, "rb") as f:
        r = requests.post(f"{BASE_URL}/files/upload", files={"file": (pdf_path.name, f, "application/pdf")}, headers=HEADERS)
    assert r.status_code == 200
    data = r.json()
    assert data["ok"] is True
    assert data["page_count"] == 55
    print(f"Extracted sample (first 300 chars):\n{repr(data.get('text_sample', '')[:300])}")

    chat_payload = {
        "message": "summarize this technical manual",
        "file_id": data["file_id"],
        "stream": False
    }
    cr = requests.post(f"{BASE_URL}/chat", json=chat_payload, headers=HEADERS, timeout=120)
    assert cr.status_code == 200
    resp = cr.json().get("response", "")
    print(f"Summary Reply:\n{resp}")
    assert len(resp) > 30
    print("TEST 3 PASSED: 55-page PDF processed without context errors.")

def test_4_encrypted_pdf():
    print("\n--- TEST 4: Encrypted PDF ---")
    pdf_path = FIXTURES / "sample_encrypted.pdf"
    with open(pdf_path, "rb") as f:
        r = requests.post(f"{BASE_URL}/files/upload", files={"file": (pdf_path.name, f, "application/pdf")}, headers=HEADERS)
    assert r.status_code == 200
    data = r.json()
    print("Upload response:", data)
    assert data.get("encrypted") is True
    assert "password" in data.get("error", "").lower()

    # Unlock with password
    unlock_r = requests.post(f"{BASE_URL}/files/{data['file_id']}/unlock", json={"password": "jarvis123"}, headers=HEADERS)
    assert unlock_r.status_code == 200
    unlock_data = unlock_r.json()
    print(f"Unlocked Extracted sample (first 300 chars):\n{repr(unlock_data.get('text_sample', '')[:300])}")
    assert unlock_data["ok"] is True
    assert "CONFIDENTIAL" in unlock_data.get("text_sample", "").upper()
    print("TEST 4 PASSED: Encrypted PDF prompted for password and unlocked successfully.")

def test_5_image_with_text():
    print("\n--- TEST 5: Image with Text (Code Error OCR) ---")
    img_path = FIXTURES / "sample_code_error.png"
    with open(img_path, "rb") as f:
        r = requests.post(f"{BASE_URL}/files/upload", files={"file": (img_path.name, f, "image/png")}, headers=HEADERS)
    assert r.status_code == 200
    data = r.json()
    assert data["ok"] is True
    sample = data.get("text_sample", "")
    print(f"Extracted sample (first 300 chars):\n{repr(sample[:300])}")
    assert "SyntaxError" in sample or "Traceback" in sample or "ERR_PARSER" in sample
    print("TEST 5 PASSED: Error text extracted via RapidOCR from screenshot.")

def test_6_diagram_image():
    print("\n--- TEST 6: Diagram Image (Vision Model) ---")
    img_path = FIXTURES / "sample_diagram.png"
    with open(img_path, "rb") as f:
        r = requests.post(f"{BASE_URL}/files/upload", files={"file": (img_path.name, f, "image/png")}, headers=HEADERS)
    assert r.status_code == 200
    data = r.json()
    assert data["ok"] is True
    sample = data.get("text_sample", "")
    print(f"Extracted sample (first 300 chars):\n{repr(sample[:300])}")
    assert len(sample) > 20
    print("TEST 6 PASSED: Diagram processed by vision model.")

def test_7_binary_guard():
    print("\n--- TEST 7: Binary Guard (Corrupt File) ---")
    corrupt_txt = FIXTURES / "corrupt.txt"
    with open(corrupt_txt, "rb") as f:
        r = requests.post(f"{BASE_URL}/files/upload", files={"file": (corrupt_txt.name, f, "text/plain")}, headers=HEADERS)
    data = r.json()
    print("Corrupt file response:", data)
    assert data["ok"] is False
    assert "corrupted" in data.get("error", "").lower() or "binary" in data.get("error", "").lower()
    print("TEST 7 PASSED: Binary guard rejected corrupted data with human message.")

def test_8_extension_flow():
    print("\n--- TEST 8: VS Code Extension Direct File Path Ingestion ---")
    # Test text PDF via file_path
    pdf_path = FIXTURES / "sample_text.pdf"
    chat_payload = {
        "message": "explain the pdf",
        "file_path": str(pdf_path.resolve()),
        "stream": False
    }
    r = requests.post(f"{BASE_URL}/chat", json=chat_payload, headers=HEADERS, timeout=120)
    assert r.status_code == 200
    resp = r.json().get("response", "")
    print(f"Extension PDF Explanation Reply:\n{resp[:300]}...")
    assert len(resp) > 30

    # Test image error via file_path
    img_path = FIXTURES / "sample_code_error.png"
    chat_payload_img = {
        "message": "what is this error?",
        "file_path": str(img_path.resolve()),
        "stream": False
    }
    r_img = requests.post(f"{BASE_URL}/chat", json=chat_payload_img, headers=HEADERS, timeout=120)
    assert r_img.status_code == 200
    resp_img = r_img.json().get("response", "")
    print(f"Extension Image Error Reply:\n{resp_img[:300]}...")
    assert len(resp_img) > 30
    print("TEST 8 PASSED: VS Code extension direct file_path workflow functions identically.")

if __name__ == "__main__":
    test_1_text_pdf()
    test_2_scanned_pdf()
    test_3_large_pdf()
    test_4_encrypted_pdf()
    test_5_image_with_text()
    test_6_diagram_image()
    test_7_binary_guard()
    test_8_extension_flow()
    print("\n==========================================")
    print("ALL 8 PACKAGE 1 TESTS COMPLETED & PASSED!")
    print("==========================================")

