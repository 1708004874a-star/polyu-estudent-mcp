"""Parse the eStudent subject-search result list and subject-detail pages.

Calibrated against the live portal (2026-06):
- Search results live in table#mainForm:searchTable (class dr-table rich-table),
  one row per subject: Subject Code / Title / Offering Department / Category /
  Subject Level / Credit(s). Subject-level only — no vacancy here.
- Drilling into a subject (subject-search-details.jsf) shows table#mainForm:
  groupTable with per-group Group Size / Vacancies* / Waitlist columns.
"""

from __future__ import annotations

import re

from ..models import SubjectGroup, SubjectOffering
from ._tables import extract_rows, to_float, to_int

# --- search result table ---------------------------------------------------

SEARCH_TABLE = "table[id$=searchTable]"

HDR_CODE = "Subject Code"
HDR_TITLE = "Subject Title"
HDR_DEPT = "Subject Offering Department"
HDR_CATEGORY = "Category"
HDR_LEVEL = "Subject Level"
HDR_CREDITS = "Credit(s)"

# --- subject-detail group table --------------------------------------------

GROUP_TABLE = "table[id$=groupTable]"

HDR_GROUP = "Subject Group"
HDR_ELIGIBLE = "Students of these programmes are eligible for taking this subject group"
HDR_GROUP_TYPE = "Group Type"
HDR_GROUP_SIZE = "Group Size"
HDR_VACANCY = "Vacancies*"
HDR_WAITLIST = "Waitlist available if no vacancy"

_BRACKETED = re.compile(r"^\((\d+)\)$")
_PLAIN_INT = re.compile(r"-?\d+")


def parse_subject_search(
    html: str, table_selector: str = SEARCH_TABLE
) -> list[SubjectOffering]:
    """Subject-level results. Groups are left empty (filled by drill-in)."""
    offerings: list[SubjectOffering] = []
    for row in extract_rows(html, table_selector):
        code = row.get(HDR_CODE, "")
        if not code:
            continue
        offerings.append(
            SubjectOffering(
                subject_code=code,
                subject_title=row.get(HDR_TITLE, ""),
                offering_department=row.get(HDR_DEPT, ""),
                category=row.get(HDR_CATEGORY, ""),
                level=row.get(HDR_LEVEL, ""),
                credits=to_float(row.get(HDR_CREDITS, "")),
            )
        )
    return offerings


def parse_vacancy(raw: str) -> tuple[int | None, bool]:
    """Return (best-effort integer, reserved?) for a Vacancies cell.

    "5" -> (5, False); "(4)" -> (4, True) reserved/held; "0" -> (0, False);
    "W=3 Top-up vac=2" -> (2, False) using the top-up figure; else (None, False).
    """
    raw = raw.strip()
    if not raw:
        return None, False
    m = _BRACKETED.match(raw)
    if m:
        return int(m.group(1)), True
    topup = re.search(r"Top-up vac\s*=\s*(\d+)", raw, re.I)
    if topup:
        return int(topup.group(1)), False
    m = _PLAIN_INT.search(raw)
    if m:
        return int(m.group(0)), False
    return None, False


def parse_subject_groups(
    html: str, table_selector: str = GROUP_TABLE
) -> list[SubjectGroup]:
    groups: list[SubjectGroup] = []
    for row in extract_rows(html, table_selector):
        gcode = row.get(HDR_GROUP, "")
        if not gcode:
            continue
        vacancy, reserved = parse_vacancy(row.get(HDR_VACANCY, ""))
        groups.append(
            SubjectGroup(
                group_code=gcode,
                group_type=row.get(HDR_GROUP_TYPE, ""),
                eligible_programmes=row.get(HDR_ELIGIBLE, ""),
                group_size=to_int(row.get(HDR_GROUP_SIZE, "")),
                vacancy_raw=row.get(HDR_VACANCY, ""),
                vacancy=vacancy,
                reserved=reserved,
                waitlist_available=row.get(HDR_WAITLIST, ""),
            )
        )
    return groups


def parse_subject_detail(html: str) -> SubjectOffering:
    """Parse the subject-detail page into a SubjectOffering with its groups.

    Subject code/title come from the leading details-table (label/value rows).
    """
    from bs4 import BeautifulSoup

    soup = BeautifulSoup(html, "html.parser")
    fields: dict[str, str] = {}
    dt = soup.find("table", class_="details-table")
    if dt:
        for tr in dt.find_all("tr"):
            cells = tr.find_all(["th", "td"])
            if len(cells) >= 2:
                label = " ".join(cells[0].get_text().split())
                value = " ".join(cells[1].get_text().split())
                fields.setdefault(label, value)

    # "COMP1002 [Synopsis ...]" -> take the leading token as the code.
    code_cell = fields.get("Subject Code", "")
    code = code_cell.split()[0] if code_cell else ""
    return SubjectOffering(
        subject_code=code,
        subject_title=fields.get("Subject Title", ""),
        offering_department=fields.get("Offering Department", ""),
        category=fields.get("Category", ""),
        level=fields.get("Level", ""),
        credits=to_float(fields.get("Credit(s)", "")),
        groups=parse_subject_groups(html),
    )
