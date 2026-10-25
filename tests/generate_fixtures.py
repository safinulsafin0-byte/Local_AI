"""Creates test fixtures for document & image ingestion tests."""
import io
import os
from pathlib import Path
from PIL import Image, ImageDraw
import pymupdf

FIXTURES_DIR = Path(__file__).parent / "fixtures"
FIXTURES_DIR.mkdir(parents=True, exist_ok=True)

# 1. Text PDF (multi-page)
text_pdf_path = FIXTURES_DIR / "sample_text.pdf"
doc = pymupdf.open()
p1 = doc.new_page()
p1.insert_text((50, 72), "Project Apollo Mission Overview\n\nPage 1 Summary:\nThe Apollo project aims to build an autonomous agent system for Windows.\nLaunch target is Q4 2026 with a budget of 4.5 million dollars.\nKey team members: Alice, Bob, and Charlie.")
p2 = doc.new_page()
p2.insert_text((50, 72), "Technical Specifications and Milestones\n\nPage 2 Details:\nThe core engine runs locally using PyMuPDF and Ollama models.\nMilestone 1 completed in August. Milestone 2 scheduled for November.\nAction item: Validate all offline ingestion paths before deployment.")
doc.save(str(text_pdf_path))
doc.close()
print(f"Created {text_pdf_path}")

# 2. Scanned PDF (image-only)
scanned_pdf_path = FIXTURES_DIR / "sample_scanned.pdf"
img = Image.new("RGB", (800, 300), (255, 255, 255))
draw = ImageDraw.Draw(img)
draw.text((30, 80), "SCANNED INVOICE #84920\nVENDOR: ACME CLOUD SERVICES\nAMOUNT DUE: $1,250.00\nDUE DATE: NOVEMBER 15 2026", fill=(0, 0, 0))
buf = io.BytesIO()
img.save(buf, format="PNG")

doc_scan = pymupdf.open()
p_scan = doc_scan.new_page(width=600, height=300)
p_scan.insert_image(pymupdf.Rect(20, 20, 580, 280), stream=buf.getvalue())
doc_scan.save(str(scanned_pdf_path))
doc_scan.close()
print(f"Created {scanned_pdf_path}")

# 3. Large PDF (55 pages)
large_pdf_path = FIXTURES_DIR / "sample_large.pdf"
doc_large = pymupdf.open()
for i in range(1, 56):
    p = doc_large.new_page()
    p.insert_text((50, 72), f"Chapter {i}: Architectural Deep Dive\n\nThis is page {i} of the 55-page comprehensive technical manual.\nEach chapter covers distributed systems design and memory scaling.\nSecurity parameter for chapter {i} is configured at tier level {i % 5 + 1}.")
doc_large.save(str(large_pdf_path))
doc_large.close()
print(f"Created {large_pdf_path}")

# 4. Encrypted PDF
encrypted_pdf_path = FIXTURES_DIR / "sample_encrypted.pdf"
doc_enc = pymupdf.open()
p_enc = doc_enc.new_page()
p_enc.insert_text((50, 72), "CONFIDENTIAL TOP SECRET DOCUMENT\nThis content is encrypted with password 'jarvis123'.")
doc_enc.save(str(encrypted_pdf_path), encryption=pymupdf.PDF_ENCRYPT_AES_256, user_pw="jarvis123", owner_pw="jarvis123")
doc_enc.close()
print(f"Created {encrypted_pdf_path}")

# 5. Image with text (code error)
img_code_path = FIXTURES_DIR / "sample_code_error.png"
img_code = Image.new("RGB", (700, 200), (30, 30, 30))
d_code = ImageDraw.Draw(img_code)
d_code.text((25, 40), "Traceback (most recent call last):\n  File 'server.py', line 42, in <module>\nSyntaxError: unexpected EOF while parsing\nError Code: ERR_PARSER_FAIL_99", fill=(255, 100, 100))
img_code.save(str(img_code_path))
print(f"Created {img_code_path}")

# 6. Diagram image
img_diag_path = FIXTURES_DIR / "sample_diagram.png"
img_diag = Image.new("RGB", (600, 400), (245, 245, 250))
d_diag = ImageDraw.Draw(img_diag)
d_diag.rectangle([50, 50, 220, 150], fill=(70, 130, 180), outline=(0, 0, 0), width=2)
d_diag.text((70, 90), "CLIENT WEB UI", fill=(255, 255, 255))
d_diag.rectangle([350, 50, 520, 150], fill=(46, 139, 87), outline=(0, 0, 0), width=2)
d_diag.text((370, 90), "FASTAPI SERVER", fill=(255, 255, 255))
d_diag.line([(220, 100), (350, 100)], fill=(0, 0, 0), width=3)
d_diag.rectangle([200, 230, 400, 330], fill=(218, 165, 32), outline=(0, 0, 0), width=2)
d_diag.text((230, 270), "OLLAMA ENGINE", fill=(0, 0, 0))
img_diag.save(str(img_diag_path))
print(f"Created {img_diag_path}")

# 7. Corrupt binary file
corrupt_path = FIXTURES_DIR / "sample_corrupt.bin"
corrupt_path.write_bytes(b"\x00\xff\xfe\x01\x02\x03\x04\x80\x90\xa0\xb0\xc0\xd0\xe0\xf0" * 40)
print(f"Created {corrupt_path}")

