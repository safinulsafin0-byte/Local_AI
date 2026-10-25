import asyncio
import os
import sys
from pathlib import Path
from playwright.async_api import async_playwright

BASE_DIR = Path(__file__).resolve().parent.parent
SCREENSHOTS_DIR = BASE_DIR / "data" / "screenshots"
SCREENSHOTS_DIR.mkdir(parents=True, exist_ok=True)

async def capture_screenshots():
    print("=== CAPTURING CLAYMORPHISM UI SCREENSHOTS ===")
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        context = await browser.new_context(viewport={"width": 1280, "height": 800})
        page = await context.new_page()

        # 1. Main Chat UI (Clay Light)
        await page.goto("http://127.0.0.1:8765/static/index.html", wait_until="networkidle")
        await page.wait_for_timeout(2000)
        s1 = str(SCREENSHOTS_DIR / "clay_ui_light.png")
        await page.screenshot(path=s1, full_page=False)
        print(f"1. Saved Clay Light screenshot: {s1}")

        # 2. Settings Panel & Voice Doctor
        await page.click("button.panel-tab[onclick*=\"settings\"]")
        await page.wait_for_timeout(500)
        await page.click("#voice-doctor-run-btn")
        # Wait for diagnostic run (~6-8s)
        await page.wait_for_timeout(9000)
        s2 = str(SCREENSHOTS_DIR / "clay_ui_doctor.png")
        await page.screenshot(path=s2, full_page=False)
        print(f"2. Saved Voice Doctor screenshot: {s2}")

        # 3. Dark Theme Claymorphism
        await page.select_option("#setting-ui-theme", "clay-dark")
        await page.wait_for_timeout(1000)
        s3 = str(SCREENSHOTS_DIR / "clay_ui_dark.png")
        await page.screenshot(path=s3, full_page=False)
        print(f"3. Saved Clay Dark screenshot: {s3}")

        await browser.close()
    print("✓ All screenshots captured successfully.")

if __name__ == "__main__":
    asyncio.run(capture_screenshots())

