"""
JARVIS Deep Search & Synthesis Pipeline — tools/search_pipeline.py
==================================================================
1. Extracts clean search keywords from conversational or Banglish queries.
2. Queries DuckDuckGo / DDGS with HTML fallback.
3. Extracts clean text snippets and page bodies with trafilatura.
4. Generates concise grounded answers with strict domain source chips.
5. Returns speech-ready summaries and offline graceful degradation.
"""

from __future__ import annotations

import logging
import re
import urllib.parse
from typing import Dict, Any, List, Optional
import httpx

from tools.web_tools import DDGS, DDGS_OK, TRAFILATURA_OK

logger = logging.getLogger("jarvis.tools.search")


def extract_search_query(user_query: str) -> str:
    """Removes conversational filler and Banglish question markers for clean search."""
    q = user_query.strip()
    # Strip common prefixes
    q = re.sub(r"^(?:search(?:\s+the\s+web\s+for|\s+for)?|who\s+is|what\s+is|tell\s+me\s+about|find\s+out|look\s+up)\s+", "", q, flags=re.IGNORECASE)
    # Strip Banglish question suffixes
    q = re.sub(r"\s+(?:bolo\s+to|koto\s+hobe|ki\s+chilo|chilen|koto|ki|bolun)$", "", q, flags=re.IGNORECASE)
    return q.strip() or user_query.strip()


def extract_domain(url: str) -> str:
    """Extracts clean display domain from URL (e.g. bbc.com, reuters.com)."""
    try:
        parsed = urllib.parse.urlparse(url)
        netloc = parsed.netloc.lower()
        if netloc.startswith("www."):
            netloc = netloc[4:]
        return netloc or "web"
    except Exception:
        return "web"


def fetch_page_content(url: str, timeout: float = 3.5) -> str:
    """Fetches and extracts clean body text using trafilatura."""
    if not TRAFILATURA_OK:
        return ""
    try:
        import trafilatura
        with httpx.Client(timeout=timeout, headers={"User-Agent": "Mozilla/5.0"}, follow_redirects=True) as client:
            resp = client.get(url)
            if resp.status_code == 200:
                text = trafilatura.extract(resp.text, include_links=False)
                return (text or "").strip()[:1000]
    except Exception:
        pass
    return ""


def search_and_synthesize(
    query: str,
    max_results: int = 4,
    synthesize_with_llm: bool = True,
    ollama_url: str = "http://127.0.0.1:11434",
    model: str = "qwen2.5:7b"
) -> Dict[str, Any]:
    """
    Executes search pipeline: query rewrite -> search -> extraction -> synthesis.
    Returns structured result with answer, sources, and speech summary.
    """
    clean_q = extract_search_query(query)
    results: List[Dict[str, str]] = []

    # 1. DuckDuckGo search
    if DDGS_OK:
        try:
            with DDGS() as ddgs:
                ddg_res = list(ddgs.text(clean_q, max_results=max_results))
                for r in ddg_res:
                    u = r.get("href", "") or r.get("link", "")
                    if u:
                        results.append({
                            "title": r.get("title", ""),
                            "url": u,
                            "domain": extract_domain(u),
                            "snippet": r.get("body", "") or r.get("snippet", ""),
                        })
        except Exception as e:
            logger.warning(f"DDGS search failed: {e}")

    # Fallback to direct HTML search if ddgs library was empty
    if not results:
        try:
            ddg_html_url = f"https://html.duckduckgo.com/html/?q={urllib.parse.quote(clean_q)}"
            with httpx.Client(timeout=4.0, headers={"User-Agent": "Mozilla/5.0"}) as client:
                resp = client.get(ddg_html_url)
                if resp.status_code == 200:
                    html_doc = resp.text
                    urls = re.findall(r'<a[^>]+class=[\'"]result__url[\'"][^>]*href=[\'"]([^\'"]+)[\'"]', html_doc)
                    snippets = re.findall(r'<a[^>]+class=[\'"]result__snippet[\'"][^>]*>(.*?)</a>', html_doc, re.DOTALL)
                    titles = re.findall(r'<a[^>]+class=[\'"]result__title[\'"][^>]*>(.*?)</a>', html_doc, re.DOTALL)
                    for i in range(min(max_results, len(urls))):
                        u = urls[i]
                        if "uddg=" in u:
                            m_u = re.search(r"uddg=([^&]+)", u)
                            if m_u:
                                u = urllib.parse.unquote(m_u.group(1))
                        snip = re.sub(r"<[^>]+>", "", snippets[i]).strip() if i < len(snippets) else ""
                        t = re.sub(r"<[^>]+>", "", titles[i]).strip() if i < len(titles) else clean_q
                        if u and t:
                            results.append({
                                "title": t,
                                "url": u,
                                "domain": extract_domain(u),
                                "snippet": snip,
                            })
        except Exception:
            pass

    if not results:
        return {
            "ok": False,
            "error": "offline",
            "query": clean_q,
            "answer": "I could not find web results right now. Please check your internet connection.",
            "sources": [],
            "speech": "I couldn't find web results right now. Please check your internet connection.",
        }

    # Prepare sources
    sources = results[:max_results]

    # Synthesize answer using local LLM if requested
    answer_text = ""
    if synthesize_with_llm:
        context_blocks = []
        for i, s in enumerate(sources, 1):
            context_blocks.append(f"[{i}] {s['title']} ({s['domain']}):\n{s['snippet']}")

        prompt = (
            "You are JARVIS. Answer the user's question clearly and concisely in 2-3 sentences "
            "based strictly on the search data provided. Do not invent facts. Do not output raw JSON or code blocks. "
            "Cite the source domains naturally.\n\n"
            f"Question: {query}\n\n"
            f"Search Findings:\n" + "\n\n".join(context_blocks) + "\n\n"
            "Concise Answer:"
        )

        try:
            with httpx.Client(timeout=8.0) as client:
                llm_resp = client.post(
                    f"{ollama_url}/api/chat",
                    json={
                        "model": model,
                        "messages": [{"role": "user", "content": prompt}],
                        "options": {"temperature": 0.2, "num_predict": 200},
                        "stream": False,
                    }
                )
                if llm_resp.status_code == 200:
                    answer_text = llm_resp.json().get("message", {}).get("content", "").strip()
        except Exception as e:
            logger.warning(f"Synthesis failed, falling back to top snippets: {e}")

    if not answer_text:
        # Fallback to top snippet if LLM synthesis timed out
        answer_text = sources[0]["snippet"] or sources[0]["title"]

    # Short speech summary (first 1-2 sentences)
    speech = re.split(r"(?<=[.!?])\s+", answer_text)[0] if answer_text else "Here are the top results I found."

    return {
        "ok": True,
        "query": clean_q,
        "answer": answer_text,
        "sources": sources,
        "speech": speech,
    }

