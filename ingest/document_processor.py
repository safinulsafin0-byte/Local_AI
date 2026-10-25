"""
JARVIS Document Processor.
Handles context budgeting, chunking, retrieval, and document turn prompting.
"""

from typing import Dict, Any, List, Tuple
from rag.embedder import get_embedder
import numpy as np

DOCUMENT_SYSTEM_PROMPT = (
    "You are JARVIS, an elite AI assistant. Analyzing the attached document, provide a concise, direct structured summary:\n"
    "1. **Summary**: 2-3 clear sentences explaining the core topic and purpose.\n"
    "2. **Key Points**: 2-3 bulleted highlights of critical facts or metrics.\n"
    "Deliver your response directly as natural language analysis without verbose preamble.\n"
    "Answer ONLY from the document content. "
    "If the user communicates in Bengali or Banglish, answer in proper Bengali script (বাংলা লিপি)."
)

DEFAULT_SUMMARY_INSTRUCTION = (
    "Please produce a concise 2-3 sentence executive summary and 2-3 key bullet points based strictly on the document. "
    "Reply in the same language as the user's prompt (English, Bangla, or Banglish)."
)

def is_general_summary_query(query: str) -> bool:
    q = (query or "").lower().strip()
    if not q:
        return True
    summary_keywords = [
        "explain", "summarize", "summary", "what is this", "ki bolche", 
        "overview", "describe", "details", "bujhiye bolo", "shonshipte bolo",
        "tell me about this", "what is in this"
    ]
    return any(kw in q for kw in summary_keywords) or len(q.split()) <= 4


def format_document_pages(pages: List[Dict[str, Any]], max_chars: int = 15000) -> Tuple[str, bool]:
    """Formats pages into clean text with page number markers."""
    formatted_sections = []
    total_len = 0
    is_truncated = False

    for page in pages:
        n = page.get("n", 1)
        text = (page.get("text") or "").strip()
        if not text:
            continue
        section = f"--- [Page {n}] ---\n{text}\n"
        if total_len + len(section) > max_chars:
            is_truncated = True
            break
        formatted_sections.append(section)
        total_len += len(section)

    return "\n".join(formatted_sections), is_truncated


def retrieve_top_chunks(query: str, pages: List[Dict[str, Any]], top_k: int = 4) -> str:
    """Uses local ONNX embeddings to retrieve the most relevant pages for a query."""
    valid_pages = [p for p in pages if (p.get("text") or "").strip()]
    if not valid_pages:
        return ""
    if len(valid_pages) <= top_k:
        text, _ = format_document_pages(valid_pages)
        return text

    try:
        embedder = get_embedder()
        texts = [p["text"][:1000] for p in valid_pages]
        page_vectors = [embedder.embed(t) for t in texts]
        query_vector = embedder.embed(query)

        # Cosine similarity
        q_norm = np.linalg.norm(query_vector)
        scores = []
        for idx, pv in enumerate(page_vectors):
            p_norm = np.linalg.norm(pv)
            sim = np.dot(query_vector, pv) / (q_norm * p_norm + 1e-9)
            scores.append((sim, valid_pages[idx]))

        scores.sort(key=lambda x: x[0], reverse=True)
        top_pages = sorted([item[1] for item in scores[:top_k]], key=lambda p: p["n"])
        formatted, _ = format_document_pages(top_pages, max_chars=18000)
        return formatted
    except Exception:
        # Fallback to first pages
        formatted, _ = format_document_pages(valid_pages[:top_k], max_chars=18000)
        return formatted


def build_document_prompt(user_query: str, doc_result: Dict[str, Any]) -> Tuple[str, str]:
    """
    Returns (system_prompt, user_content) for document turns.
    """
    kind = doc_result.get("kind", "document")
    metadata = doc_result.get("metadata", {})
    filename = metadata.get("filename", "attached document")
    pages = doc_result.get("pages", [])

    if not pages:
        err = doc_result.get("error", "Could not extract readable text from document.")
        return DOCUMENT_SYSTEM_PROMPT, f"DOCUMENT: {filename}\n\n[Extraction Failed]: {err}\n\nUser Question: {user_query}"

    # Check if general summary
    is_summary = is_general_summary_query(user_query)
    
    # Check total length
    total_text_len = sum(len(p.get("text", "")) for p in pages)
    
    if total_text_len <= 14000:
        doc_text, _ = format_document_pages(pages, max_chars=16000)
    else:
        if is_summary:
            # Map over pages: sample representative text from across pages
            # take start of each page so we cover the whole document
            sampled_sections = []
            max_per_page = max(300, 12000 // len(pages))
            for p in pages:
                sampled_sections.append(f"--- [Page {p['n']}] ---\n{p.get('text', '')[:max_per_page]}")
            doc_text = "\n".join(sampled_sections)
        else:
            doc_text = retrieve_top_chunks(user_query, pages, top_k=5)

    scan_type = "scanned" if any("[OCR Extracted]" in (p.get("text") or "") for p in pages) else "text"
    pages_count = len(pages)
    query_str = user_query.strip() if user_query else "Explain this file"
    
    user_content = (
        f"[Attachment: {filename}, {pages_count} pages, {scan_type}]\n"
        f"{doc_text}\n\n"
        f"User query: {query_str}"
    )

    return DOCUMENT_SYSTEM_PROMPT, user_content

