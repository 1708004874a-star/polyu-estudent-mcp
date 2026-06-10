"""Parse the eStudent class timetable page."""

from __future__ import annotations

from ..models import TimetableSlot
from ._tables import extract_rows

HDR_CODE = "Subject"
HDR_ACTIVITY = "Activity"
HDR_DAY = "Day"
HDR_START = "Start"
HDR_END = "End"
HDR_VENUE = "Venue"
HDR_WEEKS = "Weeks"


def parse_timetable(html: str, table_selector: str = "table") -> list[TimetableSlot]:
    slots: list[TimetableSlot] = []
    for row in extract_rows(html, table_selector):
        code = row.get(HDR_CODE, "")
        if not code:
            continue
        slots.append(
            TimetableSlot(
                subject_code=code,
                activity=row.get(HDR_ACTIVITY, ""),
                day=row.get(HDR_DAY, ""),
                start_time=row.get(HDR_START, ""),
                end_time=row.get(HDR_END, ""),
                venue=row.get(HDR_VENUE, ""),
                weeks=row.get(HDR_WEEKS, ""),
            )
        )
    return slots
