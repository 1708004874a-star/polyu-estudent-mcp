"""Parse the eStudent Exam Timetable page.

Calibrated to the live page (2026-06): the main data table is
`table.dr-table.data-block` with columns Subject Code / Subject Title /
Subject Group / Exam Component / Date / Start Time / End Time / Venue /
Seat No / Open Book / Remark.
"""

from __future__ import annotations

from ..models import ExamEntry
from ._tables import extract_rows

MAIN_TABLE = "table.dr-table.data-block"

HDR_CODE = "Subject Code"
HDR_TITLE = "Subject Title"
HDR_GROUP = "Subject Group"
HDR_COMPONENT = "Exam Component"
HDR_DATE = "Date"
HDR_START = "Start Time"
HDR_END = "End Time"
HDR_VENUE = "Venue"
HDR_SEAT = "Seat No"
HDR_OPEN_BOOK = "Open Book"
HDR_REMARK = "Remark"


def parse_exam_schedule(html: str, table_selector: str = MAIN_TABLE) -> list[ExamEntry]:
    exams: list[ExamEntry] = []
    for row in extract_rows(html, table_selector):
        code = row.get(HDR_CODE, "")
        if not code:
            continue
        exams.append(
            ExamEntry(
                subject_code=code,
                subject_title=row.get(HDR_TITLE, ""),
                subject_group=row.get(HDR_GROUP, ""),
                exam_component=row.get(HDR_COMPONENT, ""),
                date=row.get(HDR_DATE, ""),
                start_time=row.get(HDR_START, ""),
                end_time=row.get(HDR_END, ""),
                venue=row.get(HDR_VENUE, ""),
                seat=row.get(HDR_SEAT, ""),
                open_book=row.get(HDR_OPEN_BOOK, ""),
                remark=row.get(HDR_REMARK, ""),
            )
        )
    return exams
