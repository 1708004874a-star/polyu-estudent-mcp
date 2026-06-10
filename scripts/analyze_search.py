"""Offline analysis of the captured subject-search result HTML."""

import sys
from pathlib import Path

from bs4 import BeautifulSoup

OUT = Path(__file__).resolve().parents[1] / ".runtime" / "probe"
html = (OUT / "subject_search_result.html").read_text()
soup = BeautifulSoup(html, "html.parser")

table = soup.select_one("#mainForm\\:searchTable") or soup.find(
    "table", id=lambda x: x and "searchTable" in x
)
print("found searchTable:", table is not None)
if table:
    rows = table.find_all("tr")
    print(f"rows: {len(rows)}")
    for r in rows[:4]:
        cells = r.find_all(["th", "td"])
        print("  cells:", [c.get_text(strip=True) for c in cells])
        # show any links / onclick in the first cell
        for c in cells[:1]:
            a = c.find("a")
            if a:
                print("    link:", {"href": a.get("href"), "onclick": a.get("onclick"), "id": a.get("id"), "name": a.get("name"), "text": a.get_text(strip=True)})
