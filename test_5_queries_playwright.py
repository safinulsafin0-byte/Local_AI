import asyncio
import json
import os
import re
from pathlib import Path
from playwright.async_api import async_playwright

DOCS_DIR = Path("D:/personal-ai-full/docs")
DOCS_DIR.mkdir(parents=True, exist_ok=True)

AUTH_TOKEN = "auQ_DGOITl7r0p92gR37K0W28pPjE1fR"

TEST_QUERIES = [
    ("test1_whats_new", "so jarvis what's new for today?"),
    ("test2_play_bangla_lofi", "play bangla lofi on youtube"),
    ("test3_arijit_singh", "youtube a arijit singh search koro"),
    ("test4_pause", "pause the video"),
    ("test5_president", "who is the current president of USA"),
]

async def run_tests():
    print("=== STARTING PLAYWRIGHT VERIFICATION FOR 5 TEST QUERIES ===")
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        context = await browser.new_context(viewport={"width": 1400, "height": 900})
        page = await context.new_page()

        # Inject auth token into localStorage
        await page.goto("http://127.0.0.1:8765/")
        await page.evaluate(f"localStorage.setItem('jarvis_auth_token', '{AUTH_TOKEN}')")
        await page.reload()
        await page.wait_for_selector("#msg-input", timeout=10000)
        await asyncio.sleep(2)

        results = {}

        for test_name, query in TEST_QUERIES:
            print(f"\n--- Running: '{query}' ({test_name}) ---")
            
            # Type into #msg-input
            await page.fill("#msg-input", query)
            await page.click("#send-btn")

            # Wait for response completion
            start_time = asyncio.get_event_loop().time()
            full_reply = ""
            while asyncio.get_event_loop().time() - start_time < 120:
                await asyncio.sleep(2)
                # Check the last assistant bubble using exact CSS selector: .msg.assistant .msg-bubble
                assistant_bubbles = await page.query_selector_all(".msg.assistant .msg-bubble")
                if assistant_bubbles:
                    last_bubble = assistant_bubbles[-1]
                    text = await last_bubble.inner_text()
                    # Check if typing dots are still active
                    typing = await last_bubble.query_selector(".typing-dots")
                    send_disabled = await page.is_disabled("#send-btn")
                    if text and not typing and text != "..." and not send_disabled:
                        full_reply = text
                        await asyncio.sleep(1)
                        full_reply = await last_bubble.inner_text()
                        break

            # Capture screenshot
            ss_path = DOCS_DIR / f"screenshot_{test_name}.png"
            await page.screenshot(path=str(ss_path))
            print(f"Screenshot saved to: {ss_path}")
            clean_print_reply = full_reply.encode('ascii', errors='replace').decode('ascii')
            print(f"Assistant Reply:\n{clean_print_reply}\n")

            # Check right panel tab active
            active_tab = await page.evaluate("() => { const a = document.querySelector('.panel-section.active'); return a ? a.id : 'none'; }")
            yt_status = await page.evaluate("() => { const s = document.getElementById('yt-status'); return s ? s.innerText : ''; }")

            results[test_name] = {
                "query": query,
                "reply": full_reply,
                "screenshot": str(ss_path),
                "active_tab": active_tab,
                "yt_status": yt_status
            }

        await browser.close()
        print("\n=== SUMMARY OF ALL 5 TESTS ===")
        for k, v in results.items():
            print(f"\n[{k}] Query: {v['query']}")
            tab_str = str(v['active_tab'])
            status_clean = str(v['yt_status']).encode('ascii', errors='replace').decode('ascii')
            print(f"Active Tab: {tab_str} | YT Status: {status_clean}")
            reply_clean = str(v['reply'][:180]).encode('ascii', errors='replace').decode('ascii')
            print(f"Reply Preview: {reply_clean}...")

if __name__ == "__main__":
    asyncio.run(run_tests())

