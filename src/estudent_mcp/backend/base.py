"""The backend interface every eStudent adapter must implement.

Keeping this abstract and free of Playwright/HTTP specifics is what lets the
project migrate from scheme A (Playwright) to scheme C (hybrid) later without
changing the MCP tool layer.
"""

from __future__ import annotations

from abc import ABC, abstractmethod

from ..models import (
    ExamEntry,
    GradesReport,
    RegistrationItem,
    RegistrationPreview,
    RegistrationReceipt,
    SessionState,
    SubjectOffering,
    TimetableSlot,
)


class EStudentBackend(ABC):
    """Abstract eStudent client. All methods are async."""

    @abstractmethod
    async def login(self) -> SessionState:
        """Ensure an authenticated session exists, logging in if needed."""

    @abstractmethod
    async def session_status(self) -> SessionState:
        """Report whether the current session is authenticated, without logging in."""

    @abstractmethod
    async def get_grades(self, term: str | None = None) -> GradesReport:
        ...

    @abstractmethod
    async def get_timetable(self, term: str | None = None) -> list[TimetableSlot]:
        ...

    @abstractmethod
    async def get_exam_schedule(self, term: str | None = None) -> list[ExamEntry]:
        ...

    @abstractmethod
    async def search_subjects(self, query: str) -> list[SubjectOffering]:
        ...

    @abstractmethod
    async def preview_registration(
        self, items: list[RegistrationItem]
    ) -> RegistrationPreview:
        """Compute what would happen, including conflicts. Does NOT submit."""

    @abstractmethod
    async def confirm_registration(
        self, items: list[RegistrationItem], fingerprint: str
    ) -> RegistrationReceipt:
        """Actually submit. Implementations MUST verify `fingerprint` matches a
        prior preview of `items` before submitting."""

    @abstractmethod
    async def close(self) -> None:
        """Release browser / network resources."""
