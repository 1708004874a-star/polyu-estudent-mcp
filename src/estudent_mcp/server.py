"""FastMCP server exposing eStudent operations as 9 tools.

Tool layer responsibilities only: parameter shaping, the two-step confirmation
contract, and structured error conversion. All portal interaction is delegated
to an `EStudentBackend`.
"""

from __future__ import annotations

import dataclasses
from datetime import datetime, timezone
from typing import Any, Optional

from fastmcp import FastMCP

from .backend.base import EStudentBackend
from .backend.playwright_backend import PlaywrightBackend
from .config import load_config
from .errors import EStudentError
from .models import RegistrationItem
from .registration import compute_fingerprint
from .sniper import SniperManager

mcp = FastMCP("estudent")

_backend: EStudentBackend | None = None
_sniper: SniperManager | None = None


def _get_backend() -> EStudentBackend:
    global _backend
    if _backend is None:
        _backend = PlaywrightBackend(load_config())
    return _backend


def _get_sniper() -> SniperManager:
    global _sniper
    if _sniper is None:
        backend = _get_backend()

        async def attempt(items: list[RegistrationItem]) -> bool:
            preview = await backend.preview_registration(items)
            if preview.conflicts:
                return False
            receipt = await backend.confirm_registration(items, preview.fingerprint)
            return receipt.success

        _sniper = SniperManager(backend, attempt)
    return _sniper


def _dump(obj: Any) -> Any:
    """Serialize dataclasses (and lists of them) to plain dicts for MCP."""
    if dataclasses.is_dataclass(obj) and not isinstance(obj, type):
        return {k: _dump(v) for k, v in dataclasses.asdict(obj).items()}
    if isinstance(obj, list):
        return [_dump(x) for x in obj]
    return obj


def _safe(coro):
    """Await a backend coroutine, converting EStudentError to a structured dict."""

    async def runner():
        try:
            return _dump(await coro)
        except EStudentError as exc:
            return exc.to_dict()

    return runner()


# --- read-only tools -------------------------------------------------------


@mcp.tool()
async def session_status() -> dict:
    """Report whether there is a live authenticated eStudent session."""
    return await _safe(_get_backend().session_status())


@mcp.tool()
async def get_grades(term: Optional[str] = None) -> dict:
    """Get subject grades and GPA. Optionally filter to a single term."""
    return await _safe(_get_backend().get_grades(term))


@mcp.tool()
async def get_timetable(term: Optional[str] = None) -> dict:
    """Get the class timetable (lecture/tutorial slots, venues, times)."""
    return await _safe(_get_backend().get_timetable(term))


@mcp.tool()
async def get_exam_schedule(term: Optional[str] = None) -> dict:
    """Get the examination timetable (date, time, venue, seat)."""
    return await _safe(_get_backend().get_exam_schedule(term))


@mcp.tool()
async def search_subjects(query: str) -> dict:
    """Search subject offerings by code or keyword; includes vacancy info."""
    return await _safe(_get_backend().search_subjects(query))


# --- registration (two-step confirmation) ----------------------------------


@mcp.tool()
async def preview_registration(actions: list[dict]) -> dict:
    """Preview add/drop actions WITHOUT submitting.

    `actions`: list of {"action": "add"|"drop", "subject_code": str,
    "section": str (optional)}. Returns a summary, any conflicts, and a
    `fingerprint` that must be passed to confirm_registration.
    """
    items = [
        RegistrationItem(
            action=a["action"],
            subject_code=a["subject_code"],
            section=a.get("section", ""),
        )
        for a in actions
    ]
    return await _safe(_get_backend().preview_registration(items))


@mcp.tool()
async def confirm_registration(actions: list[dict], fingerprint: str) -> dict:
    """Submit add/drop actions for real. Requires the `fingerprint` returned by
    preview_registration for the SAME actions — otherwise it is rejected."""
    items = [
        RegistrationItem(
            action=a["action"],
            subject_code=a["subject_code"],
            section=a.get("section", ""),
        )
        for a in actions
    ]
    return await _safe(_get_backend().confirm_registration(items, fingerprint))


# --- course sniper ---------------------------------------------------------


@mcp.tool()
async def start_course_sniper(
    actions: list[dict],
    mode: str = "watch_vacancy",
    open_time_iso: Optional[str] = None,
    retry_interval_seconds: float = 3.0,
    total_duration_seconds: float = 120.0,
    watch_interval_seconds: float = 60.0,
) -> dict:
    """Start an automated course-grab job (restrained; hard frequency floors).

    mode="open_time": wait until `open_time_iso` (ISO 8601), then submit, retrying
    every `retry_interval_seconds` (>=3s) for up to `total_duration_seconds` (<=120s).
    mode="watch_vacancy": poll every `watch_interval_seconds` (>=60s) until a
    vacancy is grabbed. Sub-floor intervals are rejected.
    """
    items = [
        RegistrationItem(
            action=a.get("action", "add"),
            subject_code=a["subject_code"],
            section=a.get("section", ""),
        )
        for a in actions
    ]
    sniper = _get_sniper()
    try:
        if mode == "open_time":
            if not open_time_iso:
                return {"error": "bad_args", "message": "open_time mode needs open_time_iso."}
            dt = datetime.fromisoformat(open_time_iso)
            if dt.tzinfo is None:
                dt = dt.astimezone()
            epoch = dt.astimezone(timezone.utc).timestamp()
            job = sniper.start_open_time(
                items,
                open_time_epoch=epoch,
                retry_interval=retry_interval_seconds,
                total_duration=total_duration_seconds,
            )
        elif mode == "watch_vacancy":
            job = sniper.start_watch_vacancy(items, watch_interval=watch_interval_seconds)
        else:
            return {"error": "bad_args", "message": f"unknown mode '{mode}'."}
    except EStudentError as exc:
        return exc.to_dict()
    return job.public_dict()


@mcp.tool()
async def sniper_status(job_id: Optional[str] = None, stop: bool = False) -> dict:
    """List sniper jobs, inspect one by `job_id`, or stop one (job_id + stop=true)."""
    sniper = _get_sniper()
    if job_id is None:
        return {"jobs": sniper.list_jobs()}
    if stop:
        ok = sniper.stop_job(job_id)
        return {"stopped": ok, "job_id": job_id}
    job = sniper.get_job(job_id)
    if job is None:
        return {"error": "not_found", "message": f"no job {job_id}"}
    return job.public_dict()


def main() -> None:
    mcp.run()


if __name__ == "__main__":
    main()
