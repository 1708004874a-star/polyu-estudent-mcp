"""Scheme A backend: drive eStudent with a real (headless) browser.

What is calibrated during joint-debug (marked `NEEDS_CALIBRATION`): the exact
URLs, login form field selectors, and the table selectors passed to parsers.
Everything else — session persistence, login orchestration, the preview/confirm
invariant, screenshot-on-failure — is final.
"""

from __future__ import annotations

from datetime import datetime
from typing import Optional

from ..config import SCREENSHOT_DIR, STORAGE_STATE_PATH, Config
from ..errors import CredentialsError, LoginError, PageStructureError
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
from ..parsers import (
    parse_exam_schedule,
    parse_grades,
    parse_subject_search,
    parse_timetable,
)
from ..registration import compute_fingerprint, summarize
from .base import EStudentBackend

# --- NEEDS_CALIBRATION: live portal coordinates ----------------------------
# Filled in during joint-debug by walking the real pages with a headful browser.
LOGIN_URL = "{base}/login"
GRADES_URL = "{base}/grades"
TIMETABLE_URL = "{base}/timetable"
EXAMS_URL = "{base}/exams"
SUBJECT_SEARCH_URL = "{base}/subjects"
REGISTRATION_URL = "{base}/registration"

SEL_NETID_INPUT = "#username"
SEL_PASSWORD_INPUT = "#password"
SEL_LOGIN_SUBMIT = "button[type=submit]"
SEL_LOGGED_IN_MARKER = "text=Logout"  # presence => authenticated
SEL_LOGIN_ERROR = ".login-error"

SEL_GRADES_TABLE = "table"
SEL_TIMETABLE_TABLE = "table"
SEL_EXAMS_TABLE = "table"
SEL_SUBJECTS_TABLE = "table"
# ---------------------------------------------------------------------------


class PlaywrightBackend(EStudentBackend):
    def __init__(self, config: Config):
        self._cfg = config
        self._pw = None
        self._browser = None
        self._context = None
        self._page = None

    # --- lifecycle ---------------------------------------------------------

    async def _ensure_browser(self):
        if self._page is not None:
            return
        # Imported lazily so importing this module (e.g. for tests) doesn't
        # require Playwright's browsers to be installed.
        from playwright.async_api import async_playwright

        self._pw = await async_playwright().start()
        self._browser = await self._pw.chromium.launch(headless=not self._cfg.headful)
        storage = (
            str(STORAGE_STATE_PATH) if STORAGE_STATE_PATH.exists() else None
        )
        self._context = await self._browser.new_context(storage_state=storage)
        self._page = await self._context.new_page()

    async def close(self) -> None:
        if self._context is not None:
            try:
                await self._context.storage_state(path=str(STORAGE_STATE_PATH))
            except Exception:
                pass
        for obj, meth in (
            (self._context, "close"),
            (self._browser, "close"),
            (self._pw, "stop"),
        ):
            if obj is not None:
                try:
                    await getattr(obj, meth)()
                except Exception:
                    pass
        self._pw = self._browser = self._context = self._page = None

    async def _screenshot(self, tag: str) -> str:
        path = SCREENSHOT_DIR / f"{tag}-{datetime.now():%Y%m%d-%H%M%S}.png"
        try:
            await self._page.screenshot(path=str(path))
        except Exception:
            return ""
        return str(path)

    async def _is_logged_in(self) -> bool:
        try:
            return (await self._page.query_selector(SEL_LOGGED_IN_MARKER)) is not None
        except Exception:
            return False

    # --- auth --------------------------------------------------------------

    async def session_status(self) -> SessionState:
        await self._ensure_browser()
        # Hitting the grades URL is a cheap authenticated-page probe.
        try:
            await self._page.goto(
                GRADES_URL.format(base=self._cfg.base_url), wait_until="domcontentloaded"
            )
        except Exception as exc:
            raise LoginError(f"Could not reach portal: {exc}")
        ok = await self._is_logged_in()
        return SessionState(
            logged_in=ok,
            netid=self._cfg.netid,
            detail="Authenticated session active." if ok else "Not logged in.",
        )

    async def login(self) -> SessionState:
        if not self._cfg.has_credentials:
            raise CredentialsError(
                "No credentials configured. Copy .env.example to .env and fill in "
                "ESTUDENT_NETID and ESTUDENT_PASSWORD."
            )
        await self._ensure_browser()

        # Reuse an existing valid session if storage_state carried one over.
        status = await self.session_status()
        if status.logged_in:
            return status

        try:
            await self._page.goto(
                LOGIN_URL.format(base=self._cfg.base_url),
                wait_until="domcontentloaded",
            )
            await self._page.fill(SEL_NETID_INPUT, self._cfg.netid)
            await self._page.fill(SEL_PASSWORD_INPUT, self._cfg.password)
            await self._page.click(SEL_LOGIN_SUBMIT)
            await self._page.wait_for_load_state("networkidle")
        except Exception as exc:
            shot = await self._screenshot("login-error")
            raise LoginError(f"Login flow failed: {exc}", screenshot=shot)

        if await self._page.query_selector(SEL_LOGIN_ERROR) is not None:
            raise CredentialsError("Portal rejected the credentials. Check .env.")
        if not await self._is_logged_in():
            shot = await self._screenshot("login-unknown")
            raise LoginError(
                "Login did not reach an authenticated page.", screenshot=shot
            )

        await self._context.storage_state(path=str(STORAGE_STATE_PATH))
        return SessionState(logged_in=True, netid=self._cfg.netid, detail="Logged in.")

    # --- read operations ---------------------------------------------------

    async def _fetch_html(self, url_tmpl: str, tag: str) -> str:
        await self.login()
        try:
            await self._page.goto(
                url_tmpl.format(base=self._cfg.base_url),
                wait_until="domcontentloaded",
            )
            return await self._page.content()
        except Exception as exc:
            shot = await self._screenshot(tag)
            raise PageStructureError(
                f"Failed to load {tag} page: {exc}", screenshot=shot
            )

    async def get_grades(self, term: Optional[str] = None) -> GradesReport:
        html = await self._fetch_html(GRADES_URL, "grades")
        report = parse_grades(html, SEL_GRADES_TABLE)
        if term:
            report.entries = [e for e in report.entries if e.term == term]
        return report

    async def get_timetable(self, term: Optional[str] = None) -> list[TimetableSlot]:
        html = await self._fetch_html(TIMETABLE_URL, "timetable")
        return parse_timetable(html, SEL_TIMETABLE_TABLE)

    async def get_exam_schedule(self, term: Optional[str] = None) -> list[ExamEntry]:
        html = await self._fetch_html(EXAMS_URL, "exams")
        return parse_exam_schedule(html, SEL_EXAMS_TABLE)

    async def search_subjects(self, query: str) -> list[SubjectOffering]:
        html = await self._fetch_html(SUBJECT_SEARCH_URL, "subjects")
        offerings = parse_subject_search(html, SEL_SUBJECTS_TABLE)
        q = query.upper().strip()
        if q:
            offerings = [
                o
                for o in offerings
                if q in o.subject_code.upper() or q in o.subject_title.upper()
            ]
        return offerings

    # --- registration (two-step) ------------------------------------------

    async def preview_registration(
        self, items: list[RegistrationItem]
    ) -> RegistrationPreview:
        await self.login()
        # NEEDS_CALIBRATION: real conflict detection navigates the registration
        # page and reads the system's validation response. The fingerprint and
        # summary are final and independent of the live page.
        fingerprint = compute_fingerprint(items)
        return RegistrationPreview(
            items=items,
            summary=summarize(items),
            conflicts=[],
            fingerprint=fingerprint,
        )

    async def confirm_registration(
        self, items: list[RegistrationItem], fingerprint: str
    ) -> RegistrationReceipt:
        expected = compute_fingerprint(items)
        if fingerprint != expected:
            return RegistrationReceipt(
                success=False,
                message=(
                    "Fingerprint mismatch — these items were not previewed. "
                    "Run preview_registration first and pass back its fingerprint."
                ),
                items=items,
            )
        await self.login()
        # NEEDS_CALIBRATION: perform the real add/drop submission on the
        # registration page and read back the system receipt.
        raise PageStructureError(
            "confirm_registration submission not yet calibrated to the live "
            "registration page (joint-debug phase)."
        )
