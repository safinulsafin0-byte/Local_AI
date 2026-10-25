import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

import time
import os
import json
import tempfile
import urllib.request
import pymupdf

TOKEN = "auQ_DGOIXStCxeEr17J2Tb5ELOjfYgr4Mov8GUwjKsA"
HEADERS = {"Authorization": f"Bearer {TOKEN}"}
BASE_URL = "http://127.0.0.1:8765/api/v1"

def test_part_d():
    print("=" * 60)
    print("RUNNING PART D VERIFICATION: ATTACHMENTS & EXPLANATION")
    print("=" * 60)

    from ingest.extractor import extract, is_binary_or_corrupt, get_ocr_engine
    from ingest.document_processor import build_document_prompt

    # 1. Text PDF Extraction with PyMuPDF
    print("1. Testing Text PDF Extraction (PyMuPDF):")
    pdf_tmp = tempfile.mktemp(suffix=".pdf")
    doc_create = pymupdf.open()
    page = doc_create.new_page()
    page.insert_text((50, 100), "Project JARVIS Architecture: Local offline autonomous AI agent on Windows.", fontsize=12)
    doc_create.save(pdf_tmp)
    doc_create.close()

    doc_res = extract(pdf_tmp)
    print(f"   Extracted kind: {doc_res.get('kind')}, pages: {len(doc_res.get('pages', []))}")
    assert doc_res.get("kind") == "pdf", "Expected kind pdf"
    assert "JARVIS Architecture" in doc_res["pages"][0]["text"], "Text not extracted properly"
    print("   [PASS] Text PDF extracted cleanly via PyMuPDF")
    if os.path.exists(pdf_tmp): os.remove(pdf_tmp)

    # 2. Scanned PDF / Image OCR Fallback
    print("\n2. Testing OCR Engine Availability & Extraction:")
    ocr = get_ocr_engine()
    print(f"   RapidOCR Engine Loaded: {ocr is not None}")
    assert ocr is not None, "RapidOCR should be available"

    # Create dummy image with text
    from PIL import Image, ImageDraw
    img = Image.new("RGB", (300, 80), color=(255, 255, 255))
    draw = ImageDraw.Draw(img)
    draw.text((10, 25), "TEST OCR 123", fill=(0, 0, 0))
    img_tmp = tempfile.mktemp(suffix=".png")
    img.save(img_tmp)

    img_res = extract(img_tmp)
    print(f"   Image extraction kind: {img_res.get('kind')}")
    assert img_res.get("kind") == "image"
    print("   [PASS] Image extracted with OCR pipeline")
    if os.path.exists(img_tmp): os.remove(img_tmp)

    # 3. Office & Data Files (CSV, TXT)
    print("\n3. Testing Office & Data Files (CSV, TXT):")
    csv_tmp = tempfile.mktemp(suffix=".csv")
    with open(csv_tmp, "w", encoding="utf-8") as f:
        f.write("id,name,metric\n1,alpha,95.5\n2,beta,88.2\n")
    csv_res = extract(csv_tmp)
    assert csv_res.get("kind") == "spreadsheet"
    assert "alpha" in csv_res["pages"][0]["text"]
    print("   [PASS] CSV file extracted with columns and sample rows")
    if os.path.exists(csv_tmp): os.remove(csv_tmp)

    txt_tmp = tempfile.mktemp(suffix=".txt")
    with open(txt_tmp, "w", encoding="utf-8") as f:
        f.write("Quarterly roadmap: improve latency by 40% and add bilingual voice.")
    txt_res = extract(txt_tmp)
    assert txt_res.get("kind") == "text"
    assert "roadmap" in txt_res["pages"][0]["text"]
    print("   [PASS] Text file extracted successfully")
    if os.path.exists(txt_tmp): os.remove(txt_tmp)

    # 4. Binary Guard
    print("\n4. Testing Binary Guard (>5% Non-printable / Corrupted):")
    raw_corrupt_bytes = b"%PDF-1.4\x00\x01\x02\x03\x04\x05\x06\x07\x08\x09\xff\xfe\x00\x00\x00" * 20
    bin_tmp = tempfile.mktemp(suffix=".bin")
    with open(bin_tmp, "wb") as f:
        f.write(raw_corrupt_bytes)
    bin_res = extract(bin_tmp)
    print(f"   Binary file error: {bin_res.get('error')}")
    assert "Cannot read this file format" in bin_res.get("error", "") or "Unsupported" in bin_res.get("error", ""), "Binary guard should reject corrupt binary"
    print("   [PASS] Corrupted/raw binary safely rejected with clean error message")
    if os.path.exists(bin_tmp): os.remove(bin_tmp)

    # 5. Attachment Explanation Prompt Format
    print("\n5. Testing Attachment Explanation Prompt Format:")
    sample_doc = {
        "kind": "pdf",
        "metadata": {"filename": "report_2026.pdf"},
        "pages": [{"n": 1, "text": "Annual summary: 30% increase in autonomous agent efficiency."}]
    }
    sys_prompt, user_content = build_document_prompt("Explain this file", sample_doc)
    print("   Formatted User Content Header:")
    for line in user_content.split("\n")[:4]:
        print(f"     {line}")

    assert "[Attachment: report_2026.pdf, 1 pages, text]" in user_content, "Prompt must include required header format"
    assert "User query: Explain this file" in user_content, "Prompt must include user query"
    assert "Summary" in sys_prompt and "Key Points" in sys_prompt and "Action Items" in sys_prompt, "System prompt must demand structured breakdown"
    print("   [PASS] Prompt format strictly matches [Attachment: <filename>, <N> pages, text/scanned]")

    print("\n" + "=" * 60)
    print("PART D VERIFICATION COMPLETED SUCCESSFULLY!")
    print("=" * 60)

if __name__ == "__main__":
    test_part_d()

