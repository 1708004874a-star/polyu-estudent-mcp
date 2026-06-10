"""Shared helper: extract rows from an HTML table into dicts keyed by header.

eStudent renders most data as HTML tables. This generic extractor lets each
parser map header text -> field without re-implementing table walking. During
joint-debug we calibrate the `table_selector` and header names to the live page;
the row-to-dataclass mapping in each parser stays the same.
"""

from __future__ import annotations

from bs4 import BeautifulSoup


def extract_rows(html: str, table_selector: str = "table") -> list[dict[str, str]]:
    """Return one dict per data row, keyed by the table's header cell text.

    - First row containing <th> (or the first row if none) is treated as headers.
    - Cells are matched to headers positionally.
    - Whitespace is collapsed/stripped.
    """
    soup = BeautifulSoup(html, "html.parser")
    table = soup.select_one(table_selector)
    if table is None:
        return []

    rows = table.find_all("tr")
    if not rows:
        return []

    header_cells = rows[0].find_all(["th", "td"])
    headers = [_clean(c.get_text()) for c in header_cells]

    out: list[dict[str, str]] = []
    for tr in rows[1:]:
        cells = tr.find_all(["td", "th"])
        if not cells:
            continue
        values = [_clean(c.get_text()) for c in cells]
        row = {headers[i]: values[i] for i in range(min(len(headers), len(values)))}
        if any(row.values()):
            out.append(row)
    return out


def _clean(text: str) -> str:
    return " ".join(text.split()).strip()


def to_float(value: str) -> float | None:
    try:
        return float(value.strip())
    except (ValueError, AttributeError):
        return None


def to_int(value: str) -> int | None:
    try:
        return int(value.strip())
    except (ValueError, AttributeError):
        return None
