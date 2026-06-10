"""Parse the eStudent grades / assessment results page.

Header names below (`HDR_*`) are calibrated to the live page during joint-debug.
Until then they target a documented generic structure exercised by the tests.
"""

from __future__ import annotations

from ..models import GradeEntry, GradesReport
from ._tables import extract_rows, to_float

HDR_CODE = "Subject Code"
HDR_TITLE = "Subject Title"
HDR_CREDITS = "Credits"
HDR_GRADE = "Grade"
HDR_TERM = "Term"


def parse_grades(html: str, table_selector: str = "table") -> GradesReport:
    rows = extract_rows(html, table_selector)
    report = GradesReport()
    term_points: dict[str, list[tuple[float, float]]] = {}

    for row in rows:
        entry = GradeEntry(
            subject_code=row.get(HDR_CODE, ""),
            subject_title=row.get(HDR_TITLE, ""),
            credits=to_float(row.get(HDR_CREDITS, "")),
            grade=row.get(HDR_GRADE, ""),
            term=row.get(HDR_TERM, ""),
        )
        if not entry.subject_code:
            continue
        report.entries.append(entry)

    return report
