"""Parse the eStudent examination timetable page."""

from __future__ import annotations

from ..models import ExamEntry
from ._tables import extract_rows

HDR_CODE = "Subject Code"
HDR_TITLE = "Subject Title"
HDR_DATE = "Date"
HDR_START = "Start"
HDR_END = "End"
HDR_VENUE = "Venue"
HDR_SEAT = "Seat"


def parse_exam_schedule(html: str, table_selector: str = "table") -> list[ExamEntry]:
    exams: list[ExamEntry] = []
    for row in extract_rows(html, table_selector):
        code = row.get(HDR_CODE, "")
        if not code:
            continue
        exams.append(
            ExamEntry(
                subject_code=code,
                subject_title=row.get(HDR_TITLE, ""),
                date=row.get(HDR_DATE, ""),
                start_time=row.get(HDR_START, ""),
                end_time=row.get(HDR_END, ""),
                venue=row.get(HDR_VENUE, ""),
                seat=row.get(HDR_SEAT, ""),
            )
        )
    return exams
