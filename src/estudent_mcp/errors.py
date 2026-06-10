"""Typed errors so tools return structured failures instead of bare exceptions."""

from __future__ import annotations


class EStudentError(Exception):
    """Base class. `kind` is a stable machine-readable tag for the tool layer."""

    kind = "error"

    def __init__(self, message: str, *, screenshot: str | None = None):
        super().__init__(message)
        self.message = message
        self.screenshot = screenshot

    def to_dict(self) -> dict:
        out = {"error": self.kind, "message": self.message}
        if self.screenshot:
            out["screenshot"] = self.screenshot
        return out


class CredentialsError(EStudentError):
    """Missing or rejected credentials — user should check .env."""

    kind = "credentials"


class LoginError(EStudentError):
    """Login flow failed for a non-credential reason (network, page change)."""

    kind = "login_failed"


class PageStructureError(EStudentError):
    """The page didn't match expected structure (likely a portal redesign).

    Carries a screenshot path to help fix selectors.
    """

    kind = "page_structure"


class FrequencyError(EStudentError):
    """A sniper frequency parameter violated the safety lower bounds."""

    kind = "frequency_out_of_range"
