"""Parse the eStudent subject search / offering list page."""

from __future__ import annotations

from ..models import SubjectOffering
from ._tables import extract_rows, to_int

HDR_CODE = "Subject Code"
HDR_TITLE = "Subject Title"
HDR_SECTION = "Section"
HDR_CAPACITY = "Capacity"
HDR_ENROLLED = "Enrolled"
HDR_VACANCY = "Vacancy"
HDR_SCHEDULE = "Schedule"


def parse_subject_search(
    html: str, table_selector: str = "table"
) -> list[SubjectOffering]:
    offerings: list[SubjectOffering] = []
    for row in extract_rows(html, table_selector):
        code = row.get(HDR_CODE, "")
        if not code:
            continue
        capacity = to_int(row.get(HDR_CAPACITY, ""))
        enrolled = to_int(row.get(HDR_ENROLLED, ""))
        vacancy = to_int(row.get(HDR_VACANCY, ""))
        # Derive vacancy if the page only gives capacity & enrolled.
        if vacancy is None and capacity is not None and enrolled is not None:
            vacancy = capacity - enrolled
        offerings.append(
            SubjectOffering(
                subject_code=code,
                subject_title=row.get(HDR_TITLE, ""),
                section=row.get(HDR_SECTION, ""),
                capacity=capacity,
                enrolled=enrolled,
                vacancy=vacancy,
                schedule=row.get(HDR_SCHEDULE, ""),
            )
        )
    return offerings
