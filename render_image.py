import asyncio
from playwright.async_api import async_playwright
import os

HTML_PATH = os.path.abspath("layout_carousel_4.html")
OUTPUT_PATH = os.path.abspath("test_carousel_4.jpg")

async def render_screenshot():
    print("[*] Starting browser engine...")
    async with async_playwright() as p:
        # headless=True means browser background me chalega, dikhega nahi
        browser = await p.chromium.launch(headless=True)
        
        # Instagram portrait size (1080x1350)
        # device_scale_factor=2 se image exact 2K/4K resolution me export hogi (2160 x 2700)
        page = await browser.new_page(
            viewport={"width": 1080, "height": 1350},
            device_scale_factor=2
        )
        
        print(f"[*] Loading HTML design: {HTML_PATH}")
        # Local file path ko browser URL me convert karna
        file_url = f"file:///{HTML_PATH.replace(os.sep, '/')}"
        await page.goto(file_url)
        
        # Wait for Google Fonts to load fully before screenshot
        await page.evaluate("document.fonts.ready")
        
        print("[*] Taking True 2K High-Quality Screenshot...")
        await page.screenshot(path=OUTPUT_PATH, type="jpeg", quality=95, full_page=True)
        
        await browser.close()
        print(f"[SUCCESS] Image saved as: {OUTPUT_PATH}")

if __name__ == "__main__":
    asyncio.run(render_screenshot())
