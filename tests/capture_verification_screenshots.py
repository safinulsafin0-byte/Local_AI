import os
import sys
import time
from pathlib import Path
from playwright.sync_api import sync_playwright

BASE_DIR = Path(__file__).resolve().parent.parent
SCREENSHOT_DIR = BASE_DIR / "data" / "screenshots"
SCREENSHOT_DIR.mkdir(parents=True, exist_ok=True)

TOKEN = "auQ_DGOIXStCxeEr17J2Tb5ELOjfYgr4Mov8GUwjKsA"
URL = "http://127.0.0.1:8765/"

def capture():
    print(f"Launching Playwright to capture screenshots of {URL}...")
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page(viewport={"width": 1400, "height": 900})

        page.goto(URL, wait_until="networkidle")
        page.wait_for_timeout(1500)

        # Inject auth token and mock initial messages to verify perfect contrast
        js_code = """
        () => {
            localStorage.setItem('jarvis_token', 'auQ_DGOIXStCxeEr17J2Tb5ELOjfYgr4Mov8GUwjKsA');
            localStorage.setItem('jarvis_ui_theme', 'clay-light');
            if (typeof uiSetTheme === 'function') uiSetTheme('light');

            // Render a user message and assistant reply to demonstrate contrast
            const msgs = document.getElementById('messages');
            if (msgs) {
                msgs.innerHTML = '';
                
                // User message with badge
                const userDiv = document.createElement('div');
                userDiv.className = 'msg user';
                userDiv.innerHTML = `
                    <div class="msg-avatar">👤</div>
                    <div>
                        <div class="msg-bubble">JARVIS, please verify voice output, text readability, and today's Khulna weather.</div>
                        <div class="msg-meta">10:45:00 AM <span class="lang-badge en">EN</span></div>
                    </div>`;
                msgs.appendChild(userDiv);

                // Assistant reply with badge and code
                const asstDiv = document.createElement('div');
                asstDiv.className = 'msg assistant';
                asstDiv.innerHTML = `
                    <div class="msg-avatar">🤖</div>
                    <div style="flex:1;min-width:0">
                        <div class="msg-bubble">
                            <p>Good morning! All subsystems are verified and fully operational. Text contrast strictly meets <strong>WCAG AA (13.57:1)</strong>.</p>
                            <p>খুলনার বর্তমান আবহাওয়া: রৌদ্রোজ্জ্বল, তাপমাত্রা ২৮° সেলসিয়াস, আর্দ্রতা ৬৫%।</p>
                            <pre><code>def voice_status():
    return {"voice_in": "Bilingual (BN+EN)", "voice_out": "Active", "contrast": "Pass"}</code></pre>
                        </div>
                        <div class="msg-meta">10:45:02 AM <span class="lang-badge bn">BN</span></div>
                    </div>`;
                msgs.appendChild(asstDiv);
            }
        }
        """
        page.evaluate(js_code)

        page.wait_for_timeout(800)

        # 1. Capture Light Clay Theme
        light_path = SCREENSHOT_DIR / "clay_ui_light_fixed.png"
        page.screenshot(path=str(light_path), full_page=True)
        print(f"Captured light theme screenshot: {light_path}")

        # 2. Switch to Dark Clay Theme
        page.evaluate("() => { if (typeof uiSetTheme === 'function') uiSetTheme('dark'); }")
        page.wait_for_timeout(800)

        dark_path = SCREENSHOT_DIR / "clay_ui_dark_fixed.png"
        page.screenshot(path=str(dark_path), full_page=True)
        print(f"Captured dark theme screenshot: {dark_path}")

        # 3. Switch to Settings / Voice Doctor to show unclipped tabs
        page.evaluate("() => { const t = document.querySelector('.panel-tab[onclick*=\"settings\"]'); if (t) t.click(); }")
        page.wait_for_timeout(600)

        settings_path = SCREENSHOT_DIR / "clay_ui_settings_tabs.png"
        page.screenshot(path=str(settings_path), full_page=True)
        print(f"Captured settings tab screenshot: {settings_path}")

        browser.close()
        print("Playwright screenshot capture completed successfully.")

if __name__ == "__main__":
    capture()

