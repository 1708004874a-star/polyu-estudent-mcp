"""Joint-debug probe: open the eStudent entry in a visible browser, follow
redirects, and capture screenshot + HTML + final URL so we can calibrate the
login selectors. Does NOT type any credentials — observation only.
"""

import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from estudent_mcp.config import load_config  # noqa: E402

OUT = Path(__file__).resolve().parents[1] / ".runtime" / "probe"


async def main():
    from playwright.async_api import async_playwright

    cfg = load_config()
    # Candidate entry points for PolyU eStudent.
    target = cfg.base_url

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=False)
        ctx = await browser.new_context()
        page = await ctx.new_page()
        print(f"Navigating to: {target}")
        await page.goto(target, wait_until="domcontentloaded", timeout=60000)
        await page.wait_for_timeout(4000)  # let any SSO redirect settle

        final_url = page.url
        title = await page.title()
        print(f"Final URL: {final_url}")
        print(f"Title: {title}")

        await page.screenshot(path=str(OUT / "01_entry.png"), full_page=True)
        (OUT / "01_entry.html").write_text(await page.content())

        # Report any input fields visible (helps locate the login form).
        inputs = await page.eval_on_selector_all(
            "input",
            "els => els.map(e => ({type:e.type, name:e.name, id:e.id, ph:e.placeholder}))",
        )
        print("Inputs found:")
        for i in inputs:
            print("  ", i)

        await browser.close()
    print(f"\nSaved screenshot + HTML to {OUT}")


if __name__ == "__main__":
    asyncio.run(main())
