"""HTML -> structured data parsers.

Pure functions (HTML string in, dataclass out). Shared by every backend and the
main unit-testable surface of this project. Real selectors are filled in during
the joint-debug phase using saved HTML fixtures from the live portal.
"""

from .grades import parse_grades
from .timetable import parse_timetable
from .exams import parse_exam_schedule
from .subjects import parse_subject_search

__all__ = [
    "parse_grades",
    "parse_timetable",
    "parse_exam_schedule",
    "parse_subject_search",
]
