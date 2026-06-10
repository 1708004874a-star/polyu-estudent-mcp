"""Structured data models shared across backends, parsers, and tools.

These are plain dataclasses so they serialize cleanly to JSON for MCP tool
results and are trivial to assert against in unit tests.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Literal, Optional


@dataclass
class GradeEntry:
    subject_code: str
    subject_title: str
    credits: Optional[float]
    grade: str
    term: str
    remark_code: str = ""


@dataclass
class GradesReport:
    entries: list[GradeEntry] = field(default_factory=list)
    cumulative_gpa: Optional[float] = None
    term_gpa: dict[str, float] = field(default_factory=dict)


@dataclass
class TimetableSlot:
    subject_code: str
    subject_title: str
    subject_group: str
    component: str  # e.g. "LEC001", "TUT002"
    day: str
    start_time: str
    end_time: str
    venue: str
    teaching_staff: str = ""
    weeks: str = ""  # e.g. "1-13"
    remark: str = ""


@dataclass
class ExamEntry:
    subject_code: str
    subject_title: str
    subject_group: str
    exam_component: str
    date: str
    start_time: str
    end_time: str
    venue: str
    seat: str = ""
    open_book: str = ""
    remark: str = ""


@dataclass
class SubjectGroup:
    """One teaching group of a subject, as shown on the subject-detail page.

    eStudent's Vacancies column is nuanced: a plain number is open vacancy; a
    number in round brackets like "(4)" is a *reserved* quota (held for specific
    programmes, not freely grabbable); when a waitlist exists the cell reads
    "W=… Top-up vac=…". We keep the literal cell in `vacancy_raw` and expose a
    conservative `has_open_vacancy`.
    """

    group_code: str
    group_type: str = ""
    eligible_programmes: str = ""
    group_size: Optional[int] = None
    vacancy_raw: str = ""
    vacancy: Optional[int] = None  # best-effort integer parsed from vacancy_raw
    reserved: bool = False  # True when the vacancy figure is bracketed/held
    waitlist_available: str = ""

    @property
    def has_open_vacancy(self) -> bool:
        return self.vacancy is not None and self.vacancy > 0 and not self.reserved


@dataclass
class SubjectOffering:
    """A subject as returned by the search page. `groups` is populated only after
    drilling into the subject-detail page (search results are subject-level)."""

    subject_code: str
    subject_title: str
    offering_department: str = ""
    category: str = ""
    level: str = ""
    credits: Optional[float] = None
    groups: list["SubjectGroup"] = field(default_factory=list)

    @property
    def has_vacancy(self) -> bool:
        return any(g.has_open_vacancy for g in self.groups)


# A registration action the user wants to perform.
RegistrationAction = Literal["add", "drop"]


@dataclass
class RegistrationItem:
    action: RegistrationAction
    subject_code: str
    section: str = ""


@dataclass
class RegistrationPreview:
    """Result of preview_registration. The `fingerprint` must be echoed back to
    confirm_registration so a real submission can never bypass the preview step.
    """

    items: list[RegistrationItem]
    summary: str
    conflicts: list[str] = field(default_factory=list)
    fingerprint: str = ""


@dataclass
class RegistrationReceipt:
    success: bool
    message: str
    items: list[RegistrationItem] = field(default_factory=list)


@dataclass
class SessionState:
    logged_in: bool
    netid: str = ""
    detail: str = ""
