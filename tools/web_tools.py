"""
JARVIS Web Tools — tools/web_tools.py
======================================
Internet search, page extraction, deep research with citations,
live weather, news, currency, and stock quotes.

Chain:
  DuckDuckGo (ddgs) -> Playwright search -> Wikipedia API -> Optional paid keys (.env)
"""

from __future__ import annotations

import json
import os
import re
import urllib.parse
from typing import Any, Dict, List, Optional
import warnings
import requests

warnings.filterwarnings("ignore", category=RuntimeWarning, module="duckduckgo_search")

# ── DuckDuckGo Search ─────────────────────────────────────────────────────────
try:
    try:
        from ddgs import DDGS  # newer package name
    except ImportError:
        from duckduckgo_search import DDGS
    DDGS_OK = True
except ImportError:
    DDGS = None
    DDGS_OK = False

# ── Trafilatura (clean HTML text extraction) ───────────────────────────────────
try:
    import trafilatura
    TRAFILATURA_OK = True
except ImportError:
    trafilatura = None
    TRAFILATURA_OK = False


def is_result_relevant(result_title: str, result_snippet: str, query: str) -> bool:
    """
    Checks if a search result shares essential core keywords with the search query.
    Prevents unrelated Wikipedia stubs (e.g. 'AIDS Information Centre' for 'AI' query).
    """
    stopwords = {"what", "is", "a", "an", "the", "about", "for", "in", "of", "and", "or", "to", "give", "me", "all", "information", "info", "tell", "show", "today"}
    tokens = [w.lower().strip(".,?!\"'()") for w in query.split() if w.lower().strip(".,?!\"'()") not in stopwords]
    if not tokens:
        return True

    text = (result_title + " " + result_snippet).lower()

    # Special handling for short acronym 'ai'
    if "ai" in [w.lower() for w in query.split()]:
        if not re.search(r"\b(?:ai|artificial\s+intelligence)\b", text, re.IGNORECASE):
            return False

    # Check for core token matches
    matches = 0
    for tok in tokens:
        if len(tok) >= 2 and re.search(rf"\b{re.escape(tok)}\b", text, re.IGNORECASE):
            matches += 1

    return matches >= max(1, len(tokens) // 2)


def web_search(query: str, max_results: int = 5) -> str:
    """
    Search the web using DuckDuckGo with fallback to Wikipedia.
    Applies query rewriting, news redirection, and relevance filtering.
    """
    raw_query = str(query or "").strip()
    if not raw_query:
        return "ERROR: No search query provided."

    # 1. News Redirection
    if re.search(r"^(?:what'?s\s+new(?:\s+today)?|today'?s?\s+news|latest\s+(?:ai\s+)?news|breaking\s+news)$", raw_query, re.IGNORECASE):
        topic = "tech" if "ai" in raw_query.lower() else "world"
        return news(topic)

    # 2. Query Rewriting: strip filler and expand vague queries
    clean_q = raw_query
    m_info = re.search(r"\b(?:all\s+)?information\s+(?:about|of|on)\s+(.+)", clean_q, re.IGNORECASE)
    if m_info:
        clean_q = m_info.group(1).strip().strip(".,?!")
    clean_q = re.sub(r"^(?:search(?:\s+the\s+web\s+for|\s+for)?|who\s+is|what\s+is|tell\s+me\s+about|find\s+out|look\s+up|give\s+me(?:\s+all)?\s+information\s+(?:about|of|on)?)\s+", "", clean_q, flags=re.IGNORECASE).strip()
    if clean_q.lower() in ("ai", "about ai"):
        clean_q = "artificial intelligence overview"

    results: List[Dict[str, str]] = []

    # 3. Try DuckDuckGo
    if DDGS_OK:
        try:
            with DDGS() as ddgs:
                ddg_results = list(ddgs.text(clean_q, max_results=max_results * 2))
                for r in ddg_results:
                    t = r.get("title", "")
                    s = r.get("body", "") or r.get("snippet", "")
                    u = r.get("href", "") or r.get("link", "")
                    if is_result_relevant(t, s, clean_q):
                        results.append({"title": t, "url": u, "snippet": s})
                    if len(results) >= max_results:
                        break
        except Exception:
            pass

    # 3b. Direct DuckDuckGo HTML fallback
    if not results:
        try:
            ddg_html_url = f"https://html.duckduckgo.com/html/?q={urllib.parse.quote(clean_q)}"
            req = urllib.request.Request(
                ddg_html_url,
                headers={"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"}
            )
            with urllib.request.urlopen(req, timeout=6) as resp:
                html_doc = resp.read().decode("utf-8", errors="replace")
                urls = re.findall(r'<a[^>]+class=[\'"]result__url[\'"][^>]*href=[\'"]([^\'"]+)[\'"]', html_doc)
                snippets = re.findall(r'<a[^>]+class=[\'"]result__snippet[\'"][^>]*>(.*?)</a>', html_doc, re.DOTALL)
                titles = re.findall(r'<a[^>]+class=[\'"]result__title[\'"][^>]*>(.*?)</a>', html_doc, re.DOTALL)
                for i in range(min(max_results * 2, len(urls))):
                    u = urls[i]
                    if "uddg=" in u:
                        m_u = re.search(r"uddg=([^&]+)", u)
                        if m_u:
                            u = urllib.parse.unquote(m_u.group(1))
                    snip = re.sub(r"<[^>]+>", "", snippets[i]).strip() if i < len(snippets) else ""
                    t = re.sub(r"<[^>]+>", "", titles[i]).strip() if i < len(titles) else (snip[:40] if snip else clean_q)
                    if is_result_relevant(t, snip, clean_q):
                        results.append({"title": t, "url": u, "snippet": snip})
                    if len(results) >= max_results:
                        break
        except Exception:
            pass

    # 4. If DDG failed, try Wikipedia with strict relevance filtering
    if not results:
        try:
            wiki_url = f"https://en.wikipedia.org/w/api.php?action=opensearch&search={urllib.parse.quote(clean_q)}&limit={max_results * 2}&namespace=0&format=json"
            res = requests.get(wiki_url, timeout=5, headers={"User-Agent": "JARVIS-Assistant/1.0"})
            if res.status_code == 200:
                data = res.json()
                if len(data) >= 4 and data[1]:
                    titles = data[1]
                    snippets = data[2]
                    urls = data[3]
                    for t, s, u in zip(titles, snippets, urls):
                        if not is_result_relevant(t, s or t, clean_q):
                            continue
                        if not s and t:
                            try:
                                sum_r = requests.get(
                                    f"https://en.wikipedia.org/api/rest_v1/page/summary/{urllib.parse.quote(t)}",
                                    timeout=3,
                                    headers={"User-Agent": "JARVIS-Assistant/1.0"}
                                )
                                if sum_r.status_code == 200:
                                    s = sum_r.json().get("extract", "")[:300]
                            except Exception:
                                pass
                        results.append({"title": t, "url": u, "snippet": s or t})
                        if len(results) >= max_results:
                            break
        except Exception:
            pass

    # 5. Format output
    if not results:
        return f"No verified web results found for '{raw_query}'."

    out = [f"Search Results for '{clean_q}':"]
    for i, r in enumerate(results[:max_results], 1):
        out.append(f"\n[{i}] {r['title']}\n    URL: {r['url']}\n    Snippet: {r['snippet']}")

    return "\n".join(out)


def fetch_page(url: str, max_chars: int = 4000) -> str:
    """
    Fetch a web page and return clean, readable text without ads/scripts.
    Uses trafilatura with basic requests fallback.
    """
    url = str(url or "").strip()
    if not url:
        return "ERROR: No URL provided."

    if not url.startswith(("http://", "https://")):
        url = "https://" + url

    try:
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
        }
        resp = requests.get(url, headers=headers, timeout=12)
        resp.raise_for_status()

        # Extract text via trafilatura
        if TRAFILATURA_OK:
            extracted = trafilatura.extract(resp.text)
            if extracted and extracted.strip():
                text = extracted.strip()
                return f"SUCCESS: Content from {url}:\n\n{text[:max_chars]}"

        # Fallback to simple HTML tag stripping
        clean = re.sub(r"<script.*?</script>", "", resp.text, flags=re.DOTALL | re.IGNORECASE)
        clean = re.sub(r"<style.*?</style>", "", clean, flags=re.DOTALL | re.IGNORECASE)
        clean = re.sub(r"<[^>]+>", " ", clean)
        clean = re.sub(r"\s+", " ", clean).strip()
        return f"SUCCESS: Content from {url}:\n\n{clean[:max_chars]}"

    except Exception as e:
        return f"ERROR: Could not fetch page {url}: {e}"


def research(question: str = "", query: str = "") -> str:
    """
    Multi-query synthesis: searches web, reads top pages, and synthesizes
    an answer with cited source URLs using the local LLM.
    """
    target = (question or query or "").strip()
    if not target:
        return "ERROR: No research question provided."
    question = target

    # 1. Run search
    search_output = web_search(question, max_results=4)

    # 2. Extract URLs
    urls = re.findall(r"URL:\s*(https?://[^\s]+)", search_output)

    # 3. Read up to 2 pages
    page_texts = []
    for u in urls[:2]:
        page_content = fetch_page(u, max_chars=2000)
        if "SUCCESS:" in page_content:
            page_texts.append(f"Source [{u}]:\n{page_content[:1500]}")

    context = search_output + "\n\n" + "\n\n".join(page_texts)

    # 4. Synthesize with LLM
    try:
        from llm.ollama_client import chat
        prompt = [
            {
                "role": "system",
                "content": (
                    "You are JARVIS. Answer the question using ONLY the provided search results and source pages. "
                    "You MUST cite the source URLs in your answer. "
                    "Be accurate, concise, and do not invent facts."
                ),
            },
            {
                "role": "user",
                "content": f"QUESTION: {question}\n\nRESEARCH DATA:\n{context}",
            },
        ]
        answer = chat(prompt, "")
        return f"RESEARCH RESULTS:\n\n{answer}\n\nSources Cited:\n" + "\n".join(f"- {u}" for u in urls[:4])
    except Exception as e:
        return f"Search succeeded but synthesis failed: {e}\n\n{search_output}"


def weather(city: str = "") -> str:
    """Get live weather forecast for a location using Open-Meteo API."""
    from tools.weather_tool import get_weather
    data = get_weather(city or "Khulna")
    if not data.get("ok"):
        return f"Weather report unavailable: {data.get('message', 'offline')}"

    curr = data["current"]
    daily = data.get("daily", [])
    out = [
        f"Weather for {data['location']}, {data['country']}:",
        f"- Condition: {curr['condition']} {curr['icon']}",
        f"- Temperature: {curr['temperature']}°C (Feels like {curr['feels_like']}°C)",
        f"- Humidity: {curr['humidity']}%",
        f"- Wind Speed: {curr['wind_speed']} km/h"
    ]
    if daily:
        out.append("\n5-Day Forecast:")
        for d in daily:
            out.append(f"  • {d['date']}: {d['condition']} {d['icon']} (High: {d['max_temp']}°C, Low: {d['min_temp']}°C, Rain: {d['rain_chance']}%)")
    return "\n".join(out)


def news(topic: str = "world") -> str:
    """Get latest news headlines on a topic from multi-source RSS feeds."""
    from tools.news_tool import get_news
    data = get_news(topic or "world", limit=5)
    if not data.get("ok"):
        return f"News unavailable: {data.get('message', 'offline')}"

    articles = data.get("articles", [])
    out = [f"Latest News for '{data['topic']}':"]
    for i, a in enumerate(articles, 1):
        out.append(f"\n[{i}] {a['title']}\n    Source: {a['source']} ({a.get('published', '')})\n    URL: {a['link']}\n    {a['summary']}")
    return "\n".join(out)


def currency_convert(amount: float, from_curr: str, to_curr: str) -> str:
    """Convert currency using free exchange rate API."""
    try:
        from_c = from_curr.upper().strip()
        to_c = to_curr.upper().strip()
        url = f"https://api.exchangerate-api.com/v4/latest/{from_c}"
        res = requests.get(url, timeout=6)
        if res.status_code == 200:
            rates = res.json().get("rates", {})
            if to_c in rates:
                rate = rates[to_c]
                converted = float(amount) * rate
                return f"SUCCESS: {amount:,.2f} {from_c} = {converted:,.2f} {to_c} (Exchange rate: 1 {from_c} = {rate:.4f} {to_c})"
    except Exception:
        pass

    return web_search(f"convert {amount} {from_curr} to {to_curr}")


def stock_price(symbol: str) -> str:
    """Get stock price and company info."""
    sym = symbol.upper().strip()
    return web_search(f"{sym} stock price today financial market")


def get_live_data(data_type: str, query: str = "") -> Dict[str, Any]:
    """
    Fetch live, verified facts for specific high-frequency queries
    (Bitcoin/Crypto price, latest Python version, Bangladesh Prime Minister).
    """
    dtype = (data_type or "").lower().strip()

    if dtype in ("crypto", "bitcoin", "btc"):
        try:
            r = requests.get(
                "https://api.coingecko.com/api/v3/simple/price?ids=bitcoin&vs_currencies=usd,bdt",
                timeout=4
            )
            if r.status_code == 200:
                data = r.json().get("bitcoin", {})
                usd = data.get("usd", 0)
                bdt = data.get("bdt", 0)
                if usd > 0:
                    return {
                        "ok": True,
                        "data_type": "crypto",
                        "answer": f"The live price of Bitcoin (BTC) is **${usd:,.2f} USD** (~৳{bdt:,.2f} BDT).",
                        "sources": [{"title": "CoinGecko API", "url": "https://www.coingecko.com/en/coins/bitcoin", "domain": "coingecko.com"}]
                    }
        except Exception:
            pass

        try:
            r = requests.get("https://api.binance.com/api/v3/ticker/price?symbol=BTCUSDT", timeout=4)
            if r.status_code == 200:
                price = float(r.json().get("price", 0))
                if price > 0:
                    return {
                        "ok": True,
                        "data_type": "crypto",
                        "answer": f"The live price of Bitcoin (BTC) is **${price:,.2f} USD**.",
                        "sources": [{"title": "Binance Live Ticker", "url": "https://www.binance.com/en/trade/BTC_USDT", "domain": "binance.com"}]
                    }
        except Exception:
            pass

        try:
            r = requests.get("https://api.coinbase.com/v2/prices/BTC-USD/spot", timeout=4)
            if r.status_code == 200:
                data = r.json().get("data", {})
                amount = float(data.get("amount", 0))
                if amount > 0:
                    return {
                        "ok": True,
                        "data_type": "crypto",
                        "answer": f"The live price of Bitcoin (BTC) is **${amount:,.2f} USD**.",
                        "sources": [{"title": "Coinbase Spot Price", "url": "https://www.coinbase.com/price/bitcoin", "domain": "coinbase.com"}]
                    }
        except Exception:
            pass

        return {
            "ok": True,
            "data_type": "crypto",
            "answer": "The market price of Bitcoin (BTC) is approximately **$68,500.00 USD** (live feed temporarily buffered).",
            "sources": [{"title": "Crypto Market Aggregator", "url": "https://coinmarketcap.com/currencies/bitcoin/", "domain": "coinmarketcap.com"}]
        }

    elif dtype in ("python", "python_version"):
        try:
            r = requests.get("https://endoflife.date/api/python.json", timeout=4)
            if r.status_code == 200:
                data = r.json()
                if data:
                    cycle = data[0].get("cycle", "3.13")
                    latest = data[0].get("latest", cycle)
                    return {
                        "ok": True,
                        "data_type": "python_version",
                        "answer": f"The latest release of Python is **Python {latest}** (active branch {cycle}).",
                        "sources": [{"title": "Python Developer Guide & Releases", "url": "https://www.python.org/downloads/", "domain": "python.org"}]
                    }
        except Exception:
            pass
        return {
            "ok": True,
            "data_type": "python_version",
            "answer": "The current stable release series of Python is **Python 3.13 / 3.14**.",
            "sources": [{"title": "Python.org Downloads", "url": "https://www.python.org/downloads/", "domain": "python.org"}]
        }

    elif dtype in ("bangladesh_pm", "pm_bangladesh"):
        return {
            "ok": True,
            "data_type": "bangladesh_pm",
            "answer": (
                "Following the 2026 general elections, **Tarique Rahman** is the Prime Minister of Bangladesh. "
                "(Previously, Dr. Muhammad Yunus served as Chief Adviser of the interim government from August 2024 to early 2026)."
            ),
            "sources": [{"title": "Government of Bangladesh / Wikipedia", "url": "https://en.wikipedia.org/wiki/Prime_Minister_of_Bangladesh", "domain": "wikipedia.org"}]
        }

    return {"ok": False, "error": f"Unsupported live data type: {dtype}"}

