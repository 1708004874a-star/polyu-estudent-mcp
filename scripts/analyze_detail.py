"""Offline analysis of the captured subject detail (group/vacancy) HTML."""

from pathlib import Path

from bs4 import BeautifulSoup

OUT = Path(__file__).resolve().parents[1] / ".runtime" / "probe"
soup = BeautifulSoup((OUT / "subject_detail.html").read_text(), "html.parser")

# Subject code/title from the details-table.
dt = soup.find("table", class_="details-table")
if dt:
    print("=== details-table rows ===")
    for r in dt.find_all("tr"):
        cells = [c.get_text(" ", strip=True) for c in r.find_all(["th", "td"])]
        if cells:
            print("  ", cells)

grp = soup.find("table", id=lambda x: x and "groupTable" in x)
print("\n=== groupTable rows ===")
if grp:
    for r in grp.find_all("tr"):
        cells = [c.get_text(" ", strip=True) for c in r.find_all(["th", "td"])]
        print("  ", cells)
