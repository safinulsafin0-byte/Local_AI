import asyncio
import json
import os
import re
from pathlib import Path
from playwright.async_api import async_playwright

DOCS_DIR = Path("D:/personal-ai-full/docs")
DOCS_DIR.mkdir(parents=True, exist_ok=True)

AUTH_TOKEN = "auQ_DGOITl7r0p92gR37K0W28pPjE1fR"

TESTS = [
    ("test_a_bangla_lofi", "play bangla lofi songs on youtube"),
    ("test_b_lofi_radio", "play lofi hip hop radio"),
    ("test_c_summarize", "Summarize this YouTube video: https://youtu.be/zqGW6x_5N0k"),
    ("test_d_pause", "pause the video"),
]

async def run_tests():
    print("=== STARTING PLAYWRIGHT VERIFICATION FOR YOUTUBE FIXES ===")
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        context = await browser.new_context(viewport={"width": 1400, "height": 900})
        page = await context.new_page()

        # Listen to console logs in browser page to capture any player errors or auto-skip
        page.on("console", lambda msg: print(f"[Browser Console {msg.type}] {msg.text.encode('ascii', errors='replace').decode('ascii')}"))

        # Inject auth token into localStorage
        await page.goto("http://127.0.0.1:8765/")
        await page.evaluate(f"localStorage.setItem('jarvis_auth_token', '{AUTH_TOKEN}')")
        await page.reload()
        await page.wait_for_selector("#msg-input", timeout=10000)
        await asyncio.sleep(2)

        results = {}

        for test_key, query in TESTS:
            print(f"\n-------------------------------------------------------------")
            print(f"Running Test: {test_key} -> '{query}'")
            print(f"-------------------------------------------------------------")

            # Type query and send
            await page.fill("#msg-input", query)
            await page.click("#send-btn")

            # Wait for response completion
            start_time = asyncio.get_event_loop().time()
            full_reply = ""
            while asyncio.get_event_loop().time() - start_time < 90:
                await asyncio.sleep(2)
                assistant_bubbles = await page.query_selector_all(".msg.assistant .msg-bubble")
                if assistant_bubbles:
                    last_bubble = assistant_bubbles[-1]
                    text = await last_bubble.inner_text()
                    typing = await last_bubble.query_selector(".typing-dots")
                    send_disabled = await page.is_disabled("#send-btn")
                    if text and not typing and text != "..." and not send_disabled:
                        full_reply = text
                        await asyncio.sleep(1)
                        full_reply = await last_bubble.inner_text()
                        break

            # Give media player 3 seconds to settle or auto-skip if error
            await asyncio.sleep(3)

            # Capture screenshot
            ss_path = DOCS_DIR / f"screenshot_{test_key}.png"
            await page.screenshot(path=str(ss_path))
            print(f"Screenshot saved to: {ss_path}")
            clean_reply = full_reply.encode('ascii', errors='replace').decode('ascii')
            print(f"Assistant Reply:\n{clean_reply}\n")

            active_tab = await page.evaluate("() => { const a = document.querySelector('.panel-section.active'); return a ? a.id : 'none'; }")
            yt_status = await page.evaluate("() => { const s = document.getElementById('yt-status'); return s ? s.innerText : ''; }")
            iframe_src = await page.evaluate("() => { const f = document.querySelector('#yt-player-container iframe'); return f ? f.src : ''; }")

            yt_status_clean = yt_status.encode('ascii', errors='replace').decode('ascii')
            print(f"Active Tab: {active_tab} | Status: {yt_status_clean} | Iframe: {iframe_src}")

            results[test_key] = {
                "query": query,
                "reply": full_reply,
                "active_tab": active_tab,
                "yt_status": yt_status,
                "screenshot": str(ss_path),
            }

        await browser.close()
        print("\n=== SUMMARY OF ALL 4 YOUTUBE TESTS ===")
        for k, v in results.items():
            print(f"[{k}] Query: {v['query']}")
            print(f"Active Tab: {v['active_tab']} | Status: {v['yt_status'].encode('ascii', errors='replace').decode('ascii')}")
            rep = v['reply'][:140].replace('\n', ' ').encode('ascii', errors='replace').decode('ascii')
            print(f"Reply: {rep}...\n")

if __name__ == "__main__":
    asyncio.run(run_tests())

