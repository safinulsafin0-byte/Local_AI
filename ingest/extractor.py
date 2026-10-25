"""
JARVIS Document and Image Ingestion Engine.
Converts any attached file to clean text or structured visual understanding
BEFORE the LLM sees it. Prevents raw binary data from ever reaching the prompt.
"""

import base64
import csv
import io
import json
import logging
import os
import zipfile
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import charset_normalizer
import requests

from config import OLLAMA_HOST

logger = logging.getLogger("jarvis.ingest")

# Lazy-loaded RapidOCR instance
_OCR_ENGINE = None

def get_ocr_engine():
    global _OCR_ENGINE
    if _OCR_ENGINE is None:
        try:
            from rapidocr_onnxruntime import RapidOCR
            _OCR_ENGINE = RapidOCR()
        except Exception as e:
            logger.warning(f"Failed to initialize RapidOCR: {e}")
            _OCR_ENGINE = False
    return _OCR_ENGINE if _OCR_ENGINE is not False else None


def is_binary_or_corrupt(text: Any, threshold: float = 0.05) -> bool:
    """
    Checks if text has a high ratio of non-printable or Unicode replacement characters (>5%).
    Used to guarantee raw bytes or corrupt decodings never reach the LLM prompt.
    Supports both str and raw bytes.
    """
    if not text:
        return False
    if isinstance(text, bytes):
        try:
            text = text.decode("utf-8", errors="replace")
        except Exception:
            return True
    elif not isinstance(text, str):
        text = str(text)

    # Count non-printable characters (excluding common whitespace) and replacement char \ufffd
    bad_count = 0
    for ch in text:
        if ch == "\ufffd":
            bad_count += 1
        elif not ch.isprintable() and ch not in "\r\n\t":
            bad_count += 1
    
    ratio = bad_count / max(len(text), 1)
    return ratio > threshold


def run_ocr(img_data: Any) -> Tuple[str, List[str]]:
    """Runs RapidOCR on an image (bytes, path, or numpy array)."""
    ocr = get_ocr_engine()
    if not ocr:
        return "", ["OCR engine (rapidocr-onnxruntime) is unavailable."]
    try:
        result, _ = ocr(img_data)
        if result:
            lines = [item[1] for item in result if len(item) > 1 and item[1]]
            return "\n".join(lines), []
        return "", []
    except Exception as e:
        logger.warning(f"OCR execution failed: {e}")
        return "", [f"OCR error: {e}"]


def describe_image_with_vision(image_bytes: bytes, prompt: str = "Describe this image in detail, noting any diagrams, charts, text, or objects.") -> Tuple[str, List[str]]:
    """Runs vision model via Ollama with image bytes."""
    warnings = []
    try:
        # Check available vision model
        b64 = base64.b64encode(image_bytes).decode("utf-8")
        vision_model = "moondream:latest"
        
        # Check if qwen2.5vl:3b or minicpm-v is installed
        try:
            r = requests.get(f"{OLLAMA_HOST}/api/tags", timeout=2)
            if r.ok:
                models = [m.get("name", "") for m in r.json().get("models", [])]
                for cand in ["qwen2.5vl:3b", "minicpm-v", "llava"]:
                    for m in models:
                        if cand in m:
                            vision_model = m
                            break
        except Exception:
            pass

        payload = {
            "model": vision_model,
            "prompt": prompt,
            "images": [b64],
            "stream": False
        }
        res = requests.post(f"{OLLAMA_HOST}/api/generate", json=payload, timeout=60)
        if res.ok:
            desc = res.json().get("response", "").strip()
            return desc, []
        else:
            warnings.append(f"Vision model {vision_model} returned status {res.status_code}")
            return "", warnings
    except Exception as e:
        warnings.append(f"Vision model invocation failed: {e}")
        return "", warnings


def extract_pdf(path: Path, password: Optional[str] = None) -> Dict[str, Any]:
    """Extracts PDF text, tables, and scanned pages with PyMuPDF and RapidOCR."""
    import pymupdf
    warnings = []
    pages = []
    metadata = {
        "filename": path.name,
        "file_size": path.stat().st_size,
    }

    try:
        doc = pymupdf.open(str(path))
    except Exception as e:
        return {
            "kind": "pdf",
            "encrypted": False,
            "error": f"Failed to open PDF: {e}",
            "pages": [],
            "metadata": metadata,
            "warnings": [str(e)],
        }

    if doc.is_encrypted:
        if password:
            if not doc.authenticate(password):
                return {
                    "kind": "pdf",
                    "encrypted": True,
                    "error": "Incorrect password provided for encrypted PDF.",
                    "pages": [],
                    "metadata": metadata,
                    "warnings": ["Incorrect password"],
                }
        else:
            return {
                "kind": "pdf",
                "encrypted": True,
                "error": "PDF is password-protected. Please provide password to unlock.",
                "pages": [],
                "metadata": metadata,
                "warnings": ["Encrypted PDF requires password"],
            }

    metadata["page_count"] = len(doc)
    metadata["title"] = doc.metadata.get("title") or ""
    metadata["author"] = doc.metadata.get("author") or ""

    total_extracted_images = 0

    for idx, page in enumerate(doc, start=1):
        # 1. Page text
        page_text = page.get_text("text").strip()

        # Extract tables
        try:
            tabs = page.find_tables()
            if tabs and tabs.tables:
                for tab in tabs.tables:
                    extracted_table = tab.extract()
                    if extracted_table:
                        tbl_md = "\n" + "\n".join([" | ".join(str(cell or "").strip() for cell in row) for row in extracted_table]) + "\n"
                        page_text += "\n\n" + tbl_md
        except Exception:
            pass

        # 2. Scanned page check: if < 30 chars, render to image and OCR
        if len(page_text) < 30:
            try:
                pix = page.get_pixmap(dpi=200)
                img_bytes = pix.tobytes("png")
                ocr_text, ocr_warn = run_ocr(img_bytes)
                warnings.extend(ocr_warn)
                if ocr_text:
                    page_text = f"[OCR Extracted]:\n{ocr_text}"
                else:
                    page_text = "[Scanned page: no legible text detected]"
            except Exception as e:
                warnings.append(f"Page {idx} OCR failed: {e}")

        # Check for binary corruption
        if is_binary_or_corrupt(page_text):
            warnings.append(f"Page {idx} had high ratio of corrupted characters. Re-reading with OCR fallback.")
            try:
                pix = page.get_pixmap(dpi=200)
                ocr_text, _ = run_ocr(pix.tobytes("png"))
                page_text = ocr_text or "[Corrupted page text]"
            except Exception:
                page_text = "[Corrupted page text]"

        pages.append({
            "n": idx,
            "text": page_text,
            "images": []
        })

    doc.close()

    return {
        "kind": "pdf",
        "encrypted": False,
        "pages": pages,
        "metadata": metadata,
        "warnings": warnings,
    }


def extract_image(path: Path) -> Dict[str, Any]:
    """Extracts text via OCR and semantic description via Vision model."""
    warnings = []
    metadata = {
        "filename": path.name,
        "file_size": path.stat().st_size,
        "page_count": 1,
    }

    try:
        img_bytes = path.read_bytes()
    except Exception as e:
        return {
            "kind": "image",
            "encrypted": False,
            "error": f"Failed to read image file: {e}",
            "pages": [],
            "metadata": metadata,
            "warnings": [str(e)],
        }

    # 1. OCR for text
    ocr_text, ocr_warn = run_ocr(img_bytes)
    warnings.extend(ocr_warn)

    # 2. Vision model for semantic description
    vision_desc, vision_warn = describe_image_with_vision(img_bytes)
    warnings.extend(vision_warn)

    parts = []
    if ocr_text:
        parts.append(f"### Extracted Text (OCR)\n{ocr_text}")
    if vision_desc:
        parts.append(f"### Visual Description\n{vision_desc}")
    if not parts:
        parts.append("[No text or visual description could be extracted]")

    combined_text = "\n\n".join(parts)

    return {
        "kind": "image",
        "encrypted": False,
        "pages": [{"n": 1, "text": combined_text, "images": []}],
        "metadata": metadata,
        "warnings": warnings,
    }


def extract_docx(path: Path) -> Dict[str, Any]:
    """Extracts text and tables from Word documents (.docx)."""
    import docx
    warnings = []
    try:
        doc = docx.Document(str(path))
        lines = []
        for p in doc.paragraphs:
            if p.text.strip():
                lines.append(p.text.strip())
        for table in doc.tables:
            tbl_lines = []
            for row in table.rows:
                cells = [cell.text.strip().replace("\n", " ") for cell in row.cells]
                tbl_lines.append(" | ".join(cells))
            if tbl_lines:
                lines.append("\n" + "\n".join(tbl_lines) + "\n")
        full_text = "\n\n".join(lines)
        return {
            "kind": "docx",
            "encrypted": False,
            "pages": [{"n": 1, "text": full_text, "images": []}],
            "metadata": {"filename": path.name, "file_size": path.stat().st_size, "page_count": 1},
            "warnings": warnings,
        }
    except Exception as e:
        return {
            "kind": "docx",
            "encrypted": False,
            "error": f"Failed to extract DOCX: {e}",
            "pages": [],
            "metadata": {"filename": path.name, "file_size": path.stat().st_size},
            "warnings": [str(e)],
        }


def extract_spreadsheet(path: Path) -> Dict[str, Any]:
    """Extracts samples of rows and column headers from CSV or Excel (.xlsx)."""
    warnings = []
    lines = []
    metadata = {"filename": path.name, "file_size": path.stat().st_size, "page_count": 1}

    if path.suffix.lower() == ".csv":
        try:
            with open(path, "r", encoding="utf-8", errors="replace") as f:
                reader = csv.reader(f)
                rows = list(reader)
                if rows:
                    headers = rows[0]
                    lines.append(f"Columns ({len(headers)}): " + ", ".join(headers))
                    lines.append(f"Sample data (showing {min(len(rows)-1, 25)} of {len(rows)-1} rows):")
                    for r in rows[1:26]:
                        lines.append(" | ".join(r))
        except Exception as e:
            warnings.append(f"CSV read error: {e}")
    else:
        try:
            import openpyxl
            wb = openpyxl.load_workbook(str(path), data_only=True, read_only=True)
            for sheetname in wb.sheetnames[:5]:
                ws = wb[sheetname]
                lines.append(f"--- Sheet: {sheetname} ---")
                sheet_rows = []
                for row_idx, row in enumerate(ws.iter_rows(values_only=True)):
                    if row_idx > 25:
                        break
                    non_empty = [str(c) if c is not None else "" for c in row]
                    if any(non_empty):
                        sheet_rows.append(" | ".join(non_empty))
                lines.extend(sheet_rows)
            wb.close()
        except Exception as e:
            warnings.append(f"Excel read error: {e}")

    full_text = "\n".join(lines) if lines else "[Empty spreadsheet or could not read rows]"
    return {
        "kind": "spreadsheet",
        "encrypted": False,
        "pages": [{"n": 1, "text": full_text, "images": []}],
        "metadata": metadata,
        "warnings": warnings,
    }


def extract_presentation(path: Path) -> Dict[str, Any]:
    """Extracts slides and notes from PowerPoint presentations (.pptx)."""
    import pptx
    warnings = []
    pages = []
    metadata = {"filename": path.name, "file_size": path.stat().st_size}

    try:
        prs = pptx.Presentation(str(path))
        metadata["page_count"] = len(prs.slides)
        for idx, slide in enumerate(prs.slides, start=1):
            slide_text = []
            for shape in slide.shapes:
                if shape.has_text_frame:
                    for paragraph in shape.text_frame.paragraphs:
                        if paragraph.text.strip():
                            slide_text.append(paragraph.text.strip())
            pages.append({
                "n": idx,
                "text": "\n".join(slide_text) if slide_text else "[Slide with no text content]",
                "images": []
            })
        return {
            "kind": "presentation",
            "encrypted": False,
            "pages": pages,
            "metadata": metadata,
            "warnings": warnings,
        }
    except Exception as e:
        return {
            "kind": "presentation",
            "encrypted": False,
            "error": f"Failed to extract PPTX: {e}",
            "pages": [],
            "metadata": metadata,
            "warnings": [str(e)],
        }


def extract_plain_text(path: Path) -> Dict[str, Any]:
    """Reads text/code with automatic encoding detection."""
    warnings = []
    try:
        matches = charset_normalizer.from_path(path)
        best = matches.best()
        text = str(best) if best is not None else path.read_text(encoding="utf-8", errors="replace")
    except Exception as e:
        warnings.append(f"Charset detection fallback: {e}")
        try:
            text = path.read_text(encoding="utf-8", errors="replace")
        except Exception as exc:
            return {
                "kind": "text",
                "encrypted": False,
                "error": f"Could not read text file: {exc}",
                "pages": [],
                "metadata": {"filename": path.name, "file_size": path.stat().st_size},
                "warnings": [str(exc)],
            }

    if is_binary_or_corrupt(text):
        return {
            "kind": "text",
            "encrypted": False,
            "error": "Cannot read this file format",
            "pages": [],
            "metadata": {"filename": path.name, "file_size": path.stat().st_size},
            "warnings": ["Corrupted binary content rejected by binary guard"],
        }

    return {
        "kind": "text",
        "encrypted": False,
        "pages": [{"n": 1, "text": text, "images": []}],
        "metadata": {"filename": path.name, "file_size": path.stat().st_size, "page_count": 1},
        "warnings": warnings,
    }


def extract_archive(path: Path) -> Dict[str, Any]:
    """Lists contents of zip archives without extracting unsafe files."""
    warnings = []
    lines = [f"Archive Contents for {path.name}:"]
    try:
        with zipfile.ZipFile(str(path), 'r') as z:
            infos = z.infolist()
            for info in infos[:100]:
                lines.append(f"- {info.filename} ({info.file_size} bytes)")
            if len(infos) > 100:
                lines.append(f"... and {len(infos) - 100} more files.")
    except Exception as e:
        warnings.append(f"Zip read error: {e}")

    return {
        "kind": "archive",
        "encrypted": False,
        "pages": [{"n": 1, "text": "\n".join(lines), "images": []}],
        "metadata": {"filename": path.name, "file_size": path.stat().st_size, "page_count": 1},
        "warnings": warnings,
    }


def extract(file_path: Any, mime: Optional[str] = None, password: Optional[str] = None) -> Dict[str, Any]:
    """
    Universal ingestion entry point.
    Returns:
    {
        "kind": "pdf" | "image" | "docx" | "spreadsheet" | "presentation" | "text" | "archive" | "unsupported",
        "encrypted": bool,
        "pages": [{"n": int, "text": str, "images": [...] }],
        "metadata": dict,
        "warnings": list,
        "error": str (optional)
    }
    """
    path = Path(file_path)
    if not path.exists():
        return {
            "kind": "missing",
            "encrypted": False,
            "error": f"File does not exist: {path}",
            "pages": [],
            "metadata": {"filename": path.name},
            "warnings": ["File not found"],
        }

    suffix = path.suffix.lower()

    # Routing based on extension / mime
    if suffix == ".pdf" or mime == "application/pdf":
        return extract_pdf(path, password=password)

    if suffix in {".png", ".jpg", ".jpeg", ".webp", ".bmp", ".gif"} or (mime and mime.startswith("image/")):
        return extract_image(path)

    if suffix in {".docx", ".doc"}:
        return extract_docx(path)

    if suffix in {".xlsx", ".xls", ".csv"}:
        return extract_spreadsheet(path)

    if suffix in {".pptx", ".ppt"}:
        return extract_presentation(path)

    if suffix in {".zip"}:
        return extract_archive(path)

    if suffix in {".txt", ".md", ".py", ".js", ".ts", ".html", ".css", ".json", ".xml", ".yaml", ".yml", ".c", ".cpp", ".java", ".rs", ".go", ".sql", ".sh", ".bat", ".ps1"}:
        return extract_plain_text(path)

    # Fallback: attempt plain text with binary guard
    doc = extract_plain_text(path)
    if not doc.get("error"):
        return doc

    return {
        "kind": "unsupported",
        "encrypted": False,
        "error": f"Unsupported file type: {suffix or 'unknown'}",
        "pages": [],
        "metadata": {"filename": path.name, "file_size": path.stat().st_size},
        "warnings": [f"Unsupported extension: {suffix}"],
    }

