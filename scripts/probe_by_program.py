"""Probe the By Programme search cascade.

Selecting a Programme Hosting Department (progOrgUnitId) populates the
Programme dropdown (progId) via AJAX. We observe that cascade, then run a real
by-programme search to capture the result-table structure.

Usage:
    uv run python scripts/probe_by_program.py            # dept -> progId options
    uv run python scripts/probe_by_program.py search     # also run a search
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

DEPT_LABEL = "[COMP] DEPARTMENT OF COMPUTING"


async def options(page, sel):
    return await page.eval_on_selector_all(
        f"{sel} option", "els => els.map(o => o.text.trim())"
    )


async def main():
    do_search = len(sys.argv) > 1 and sys.argv[1] == "search"
    backend = PlaywrightBackend(load_config())
    try:
        await backend.login()
        page = backend._page
        await page.goto(
            backend._secure_url(PATH_SUBJECT_SEARCH),
            wait_until="domcontentloaded",
            timeout=45000,
        )
        await page.wait_for_timeout(2500)

        await page.check("#mainForm\\:byProgramme")
        await page.wait_for_timeout(800)
        print("progId BEFORE dept:", await options(page, "#mainForm\\:progId"))

        # Select the hosting department; observe the AJAX cascade fill progId.
        await page.select_option("#mainForm\\:progOrgUnitId", label=DEPT_LABEL)
        await page.wait_for_timeout(3000)
        progs = await options(page, "#mainForm\\:progId")
        print(f"\nprogId AFTER dept '{DEPT_LABEL}' ({len(progs)}):")
        for p in progs:
            print("  ", p)

        if do_search and len(progs) > 1:
            # Try Sem 1 + each programme until one returns a result table.
            for idx in range(1, min(len(progs), 12)):
                # Re-select dept each loop is unnecessary; re-pick term + prog.
                await page.select_option(
                    "#mainForm\\:yearsem", label="2025/26 Semester 1"
                )
                await page.wait_for_timeout(500)
                await page.select_option("#mainForm\\:progId", index=idx)
                await page.wait_for_timeout(600)
                await page.click("#mainForm\\:searchBtn")
                await page.wait_for_timeout(3500)
                html = await page.content()
                has_table = "searchTable" in html
                print(f"  [{idx}] {progs[idx]!r:45} -> searchTable={has_table}")
                if has_table:
                    (OUT / "by_program_result.html").write_text(html)
                    tables = await page.eval_on_selector_all(
                        "table",
                        "els => els.map(e => ({cls:e.className, id:e.id, "
                        "rows:e.rows.length, head:e.rows[0]?"
                        "[...e.rows[0].cells].map(c=>c.textContent.trim()):[]}))",
                    )
                    print(f"\n===== result tables ({len(tables)}) =====")
                    for t in tables:
                        if t["id"] or "dr-table" in t["cls"]:
                            print("  ", t)
                    break
                # Re-open the form for the next attempt (results page differs).
                await page.goto(
                    backend._secure_url(PATH_SUBJECT_SEARCH),
                    wait_until="domcontentloaded",
                    timeout=45000,
                )
                await page.wait_for_timeout(2000)
                await page.check("#mainForm\\:byProgramme")
                await page.wait_for_timeout(600)
                await page.select_option(
                    "#mainForm\\:progOrgUnitId", label=DEPT_LABEL
                )
                await page.wait_for_timeout(2500)
        print(f"\nSaved to {OUT}")
    finally:
        await backend.close()


if __name__ == "__main__":
    asyncio.run(main())
