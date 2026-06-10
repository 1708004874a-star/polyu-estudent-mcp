"""Offline analysis of the saved grades HTML to design the parser."""
from pathlib import Path
from bs4 import BeautifulSoup

html = (Path(".runtime/probe/results_loaded.html")).read_text()
soup = BeautifulSoup(html, "html.parser")

# Find grade tables: those whose header cells include Code + Grade.
for ti, t in enumerate(soup.find_all("table")):
    headers = [th.get_text(strip=True) for th in t.find_all("th")]
    if "Code" in headers and "Grade" in headers:
        # Look backwards for the nearest non-empty text (likely the term heading).
        head = ""
        node = t
        for _ in range(8):
            node = node.find_previous(string=lambda s: s and s.strip())
            if node and node.strip():
                head = node.strip()
                break
        rows = t.find_all("tr")
        sample = [td.get_text(strip=True) for td in rows[1].find_all("td")] if len(rows) > 1 else []
        print(f"GRADE TABLE #{ti}: heading={head!r}")
        print(f"   headers={headers}")
        print(f"   row1={sample}  (rows={len(rows)})")

# GPA-related text
print("\n--- GPA / summary lines ---")
for line in soup.get_text("\n").split("\n"):
    s = line.strip()
    if s and ("GPA" in s or "Grade Point" in s or "Credits" in s.title()):
        print("  ", s[:90])
