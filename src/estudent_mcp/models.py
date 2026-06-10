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


@dataclass
class GradesReport:
    entries: list[GradeEntry] = field(default_factory=list)
    cumulative_gpa: Optional[float] = None
    term_gpa: dict[str, float] = field(default_factory=dict)


@dataclass
class TimetableSlot:
    subject_code: str
    activity: str  # e.g. "Lecture", "Tutorial"
    day: str
    start_time: str
    end_time: str
    venue: str
    weeks: str = ""


@dataclass
class ExamEntry:
    subject_code: str
    subject_title: str
    date: str
    start_time: str
    end_time: str
    venue: str
    seat: str = ""


@dataclass
class SubjectOffering:
    subject_code: str
    subject_title: str
    section: str
    capacity: Optional[int]
    enrolled: Optional[int]
    vacancy: Optional[int]
    schedule: str = ""

    @property
    def has_vacancy(self) -> bool:
        return self.vacancy is not None and self.vacancy > 0


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
