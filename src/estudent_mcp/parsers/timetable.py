"""Parse the eStudent Class Timetable (List view).

Calibrated to the live page (2026-06): the main data table is
`table.dr-table.data-block` with columns Subject Code / Subject Title /
Subject Group / Component Code / For Every (Week) / Start Week / End Week /
Day of Week / Start Time / End Time / Venue / Teaching Staff / Remark.
"""

from __future__ import annotations

from ..models import TimetableSlot
from ._tables import extract_rows

MAIN_TABLE = "table.dr-table.data-block"

HDR_CODE = "Subject Code"
HDR_TITLE = "Subject Title"
HDR_GROUP = "Subject Group"
HDR_COMPONENT = "Component Code"
HDR_START_WEEK = "Start Week"
HDR_END_WEEK = "End Week"
HDR_DAY = "Day of Week"
HDR_START = "Start Time"
HDR_END = "End Time"
HDR_VENUE = "Venue"
HDR_STAFF = "Teaching Staff"
HDR_REMARK = "Remark"


def parse_timetable(html: str, table_selector: str = MAIN_TABLE) -> list[TimetableSlot]:
    slots: list[TimetableSlot] = []
    for row in extract_rows(html, table_selector):
        code = row.get(HDR_CODE, "")
        if not code:
            continue
        start_w = row.get(HDR_START_WEEK, "")
        end_w = row.get(HDR_END_WEEK, "")
        weeks = f"{start_w}-{end_w}" if start_w and end_w else (start_w or end_w)
        slots.append(
            TimetableSlot(
                subject_code=code,
                subject_title=row.get(HDR_TITLE, ""),
                subject_group=row.get(HDR_GROUP, ""),
                component=row.get(HDR_COMPONENT, ""),
                day=row.get(HDR_DAY, ""),
                start_time=row.get(HDR_START, ""),
                end_time=row.get(HDR_END, ""),
                venue=row.get(HDR_VENUE, ""),
                teaching_staff=row.get(HDR_STAFF, ""),
                weeks=weeks,
                remark=row.get(HDR_REMARK, ""),
            )
        )
    return slots
