"""Joint-debug probe for the Subject Search page (by subject / by program).

Reuses the calibrated login, navigates to the subject-search page, dumps the
form structure (inputs / selects / buttons), then optionally runs one real
search so we can capture the result-table HTML and calibrate the parser.

Usage:
    uv run python scripts/probe_subject_search.py            # dump form only
    uv run python scripts/probe_subject_search.py COMP        # search "COMP"

Saved artifacts go to .runtime/probe/ (gitignored, may contain real data).
"""

import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from estudent_mcp.backend.playwright_backend import (  # noqa: E402
    PATH_SUBJECT_SEARCH,
    PlaywrightBackend,
)
from estudent_mcp.config import load_config  # noqa: E402

OUT = Path(__file__).resolve().parents[1] / ".runtime" / "probe"
OUT.mkdir(parents=True, exist_ok=True)


async def dump_controls(page, tag: str):
    inputs = await page.eval_on_selector_all(
        "input",
        "els => els.map(e => ({type:e.type, name:e.name, id:e.id, "
        "value:e.value, ph:e.placeholder}))",
    )
    selects = await page.eval_on_selector_all(
        "select",
        "els => els.map(e => ({name:e.name, id:e.id, "
        "options:[...e.options].map(o=>o.text)}))",
    )
    buttons = await page.eval_on_selector_all(
        "button, input[type=submit], input[type=button], a.button, a[onclick]",
        "els => els.map(e => ({tag:e.tagName, type:e.type, id:e.id, "
        "name:e.name, text:(e.value||e.textContent||'').trim().slice(0,40)}))",
    )
    print(f"\n===== {tag}: inputs ({len(inputs)}) =====")
    for i in inputs:
        print("  ", i)
    print(f"\n===== {tag}: selects ({len(selects)}) =====")
    for s in selects:
        print("  ", s)
    print(f"\n===== {tag}: buttons ({len(buttons)}) =====")
    for b in buttons:
        print("  ", b)


async def main():
    query = sys.argv[1] if len(sys.argv) > 1 else None
    cfg = load_config()
    backend = PlaywrightBackend(cfg)
    try:
        await backend.login()
        page = backend._page
        url = backend._secure_url(PATH_SUBJECT_SEARCH)
        print(f"Navigating to: {url}")
        await page.goto(url, wait_until="domcontentloaded", timeout=45000)
        await page.wait_for_timeout(3000)
        print(f"Final URL: {page.url}")
        print(f"Title:     {await page.title()}")

        await dump_controls(page, "search-form")
        (OUT / "subject_search_form.html").write_text(await page.content())
        await page.screenshot(path=str(OUT / "subject_search_form.png"))

        if query:
            print(f"\n>>> Searching by subject code {query!r} in 2025/26 Sem 1")
            await page.check("#mainForm\\:bySubject")
            await page.wait_for_timeout(800)
            await page.select_option(
                "#mainForm\\:yearsem", label="2025/26 Semester 1"
            )
            await page.wait_for_timeout(800)
            await page.fill("#mainForm\\:subjCode", query)
            await page.click("#mainForm\\:searchBtn")
            await page.wait_for_timeout(4000)
            print(f"Result URL: {page.url}")
            html = await page.content()
            (OUT / "subject_search_result.html").write_text(html)
            await page.screenshot(path=str(OUT / "subject_search_result.png"))

            # Summarise tables so we can locate the result grid.
            tables = await page.eval_on_selector_all(
                "table",
                "els => els.map(e => ({cls:e.className, id:e.id, "
                "rows:e.rows.length, "
                "head:e.rows[0]?[...e.rows[0].cells].map(c=>c.textContent.trim()):[]}))",
            )
            print(f"\n===== result tables ({len(tables)}) =====")
            for t in tables:
                print("  ", t)

            # Drill into the first subject code to reach the group/vacancy page.
            print("\n>>> Drilling into first subject code ...")
            await page.click("#mainForm\\:searchTable\\:0\\:subjCode")
            await page.wait_for_timeout(4000)
            print(f"Detail URL: {page.url}")
            (OUT / "subject_detail.html").write_text(await page.content())
            await page.screenshot(path=str(OUT / "subject_detail.png"))
            dtables = await page.eval_on_selector_all(
                "table",
                "els => els.map(e => ({cls:e.className, id:e.id, "
                "rows:e.rows.length, "
                "head:e.rows[0]?[...e.rows[0].cells].map(c=>c.textContent.trim()):[]}))",
            )
            print(f"\n===== detail tables ({len(dtables)}) =====")
            for t in dtables:
                print("  ", t)

        print(f"\nSaved HTML + screenshot to {OUT}")
    finally:
        await backend.close()


if __name__ == "__main__":
    asyncio.run(main())
