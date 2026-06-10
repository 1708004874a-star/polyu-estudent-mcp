"""Parse the eStudent Assessment Results page (All Semesters view).

Calibrated to the live page (2026-06): one HTML <table> per semester, columns
`Code / Title / Credit / Grade / Remark Code`. The semester each table belongs
to is the nearest preceding text matching SEM_RE (e.g. "2024/25 Semester 1").
GPA figures on this page are split label/value across panels and are captured
best-effort.
"""

from __future__ import annotations

import re

from bs4 import BeautifulSoup

from ..models import GradeEntry, GradesReport
from ._tables import to_float

SEM_RE = re.compile(r"20\d\d/\d\d?\s+Semester\s+\d")


def _is_grade_table(table) -> bool:
    headers = {th.get_text(strip=True) for th in table.find_all("th")}
    return "Code" in headers and "Grade" in headers


def _term_for(table) -> str:
    node = table
    for _ in range(40):
        node = node.find_previous(string=SEM_RE)
        if node:
            return node.strip()
    return ""


def parse_grades(html: str) -> GradesReport:
    soup = BeautifulSoup(html, "html.parser")
    report = GradesReport()

    for table in soup.find_all("table"):
        if not _is_grade_table(table):
            continue
        term = _term_for(table)
        rows = table.find_all("tr")
        for tr in rows[1:]:
            cells = [td.get_text(strip=True) for td in tr.find_all("td")]
            if len(cells) < 4 or not cells[0]:
                continue
            report.entries.append(
                GradeEntry(
                    subject_code=cells[0],
                    subject_title=cells[1],
                    credits=to_float(cells[2]),
                    grade=cells[3],
                    term=term,
                    remark_code=cells[4] if len(cells) > 4 else "",
                )
            )

    return report
