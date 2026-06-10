"""Scheme A backend: drive PolyU eStudent with a headless browser.

Calibrated against the live portal (2026-06). Login is PolyU's ADFS SSO:
the eStudent landing page has a single "login" button that redirects to
adfs.polyu.edu.hk, which presents NetID + password fields (no 2FA for this
account). After auth the session lands on /eStudent/secure/home.jsf and is
persisted via Playwright storage_state.
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
from ..parsers import parse_exam_schedule, parse_grades, parse_timetable
from ..registration import compute_fingerprint, summarize
from .base import EStudentBackend

# eStudent entry — the configured base_url redirects here.
ESTUDENT_LANDING = "https://www38.polyu.edu.hk/eStudent/"

# Secure-page paths, joined to whatever origin we end up on after login.
PATH_HOME = "/eStudent/secure/home.jsf"
PATH_GRADES = "/eStudent/secure/my-results/enquiry-overall-result.jsf"
PATH_TIMETABLE = "/eStudent/secure/my-timetable/enquiry-class-timetable.jsf"
PATH_EXAMS = "/eStudent/secure/my-timetable/exam-timetable.jsf"
PATH_SUBJECT_SEARCH = "/eStudent/secure/information/subject-search.jsf"
PATH_REGISTRATION = (
    "/eStudent/secure/my-subject-registration/"
    "subject-register-select-acad-year-sem.jsf"
)

# ADFS login form (standard Microsoft ADFS field ids).
SEL_NETID = "#userNameInput"
SEL_PASSWORD = "#passwordInput"
SEL_SSO_SUBMIT = "#submitButton"
SEL_LANDING_LOGIN = "input[type=submit]"

# Grades page controls.
SEL_GRADES_YEARSEM = "#mainForm\\:yearSem"
SEL_GRADES_GO = "#mainForm\\:goBtn"

DEFAULT_ORIGIN = "https://www38.polyu.edu.hk"


class PlaywrightBackend(EStudentBackend):
    def __init__(self, config: Config):
        self._cfg = config
        self._pw = None
        self._browser = None
        self._context = None
        self._page = None
        self._origin = DEFAULT_ORIGIN

    # --- lifecycle ---------------------------------------------------------

    async def _ensure_browser(self):
        if self._page is not None:
            return
        from playwright.async_api import async_playwright

        self._pw = await async_playwright().start()
        self._browser = await self._pw.chromium.launch(headless=not self._cfg.headful)
        storage = str(STORAGE_STATE_PATH) if STORAGE_STATE_PATH.exists() else None
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
            # animations='disabled' + short timeout avoids the web-font hang.
            await self._page.screenshot(path=str(path), timeout=8000)
        except Exception:
            return ""
        return str(path)

    def _secure_url(self, path: str) -> str:
        return f"{self._origin}{path}"

    async def _on_secure_page(self) -> bool:
        url = self._page.url
        return "/eStudent/secure/" in url and "adfs." not in url

    # --- auth --------------------------------------------------------------

    async def session_status(self) -> SessionState:
        await self._ensure_browser()
        try:
            await self._page.goto(
                self._secure_url(PATH_HOME), wait_until="domcontentloaded", timeout=45000
            )
            await self._page.wait_for_timeout(1500)
        except Exception as exc:
            raise LoginError(f"Could not reach portal: {exc}")
        ok = await self._on_secure_page()
        return SessionState(
            logged_in=ok,
            netid=self._cfg.netid,
            detail="Authenticated session active." if ok else "Not logged in.",
        )

    async def login(self) -> SessionState:
        await self._ensure_browser()

        # Reuse a persisted session if still valid.
        if await self._try_reuse_session():
            return SessionState(
                logged_in=True, netid=self._cfg.netid, detail="Reused saved session."
            )

        if not self._cfg.has_credentials:
            raise CredentialsError(
                "No credentials configured. Copy .env.example to .env and fill in "
                "ESTUDENT_NETID and ESTUDENT_PASSWORD."
            )

        try:
            await self._page.goto(
                ESTUDENT_LANDING, wait_until="domcontentloaded", timeout=45000
            )
            await self._page.wait_for_timeout(1000)
            # Landing -> ADFS SSO.
            async with self._page.expect_navigation(
                wait_until="domcontentloaded", timeout=30000
            ):
                await self._page.click(SEL_LANDING_LOGIN)
            # Fill ADFS credentials.
            await self._page.fill(SEL_NETID, self._cfg.netid)
            await self._page.fill(SEL_PASSWORD, self._cfg.password)
            async with self._page.expect_navigation(
                wait_until="domcontentloaded", timeout=30000
            ):
                await self._page.click(SEL_SSO_SUBMIT)
            await self._page.wait_for_timeout(2500)
        except Exception as exc:
            shot = await self._screenshot("login-error")
            raise LoginError(f"Login flow failed: {exc}", screenshot=shot)

        if "adfs." in self._page.url:
            # Still on ADFS => credentials rejected or an extra step (e.g. 2FA).
            shot = await self._screenshot("login-rejected")
            raise CredentialsError(
                "Still on the ADFS sign-in page after submitting — credentials "
                "rejected, or an extra verification step (e.g. 2FA) appeared.",
                screenshot=shot,
            )
        if not await self._on_secure_page():
            shot = await self._screenshot("login-unknown")
            raise LoginError(
                "Login did not reach an authenticated eStudent page.", screenshot=shot
            )

        # Remember the origin we actually landed on, persist the session.
        self._origin = self._page.url.split("/eStudent/")[0]
        await self._context.storage_state(path=str(STORAGE_STATE_PATH))
        return SessionState(logged_in=True, netid=self._cfg.netid, detail="Logged in.")

    async def _try_reuse_session(self) -> bool:
        try:
            await self._page.goto(
                self._secure_url(PATH_HOME), wait_until="domcontentloaded", timeout=30000
            )
            await self._page.wait_for_timeout(1200)
        except Exception:
            return False
        if await self._on_secure_page():
            self._origin = self._page.url.split("/eStudent/")[0]
            return True
        return False

    # --- read operations ---------------------------------------------------

    async def get_grades(self, term: Optional[str] = None) -> GradesReport:
        await self.login()
        try:
            await self._page.goto(
                self._secure_url(PATH_GRADES), wait_until="domcontentloaded", timeout=45000
            )
            await self._page.wait_for_timeout(2000)
            await self._page.select_option(SEL_GRADES_YEARSEM, label="All Semesters")
            await self._page.wait_for_timeout(500)
            await self._page.click(SEL_GRADES_GO)
            await self._page.wait_for_timeout(4000)
            html = await self._page.content()
        except Exception as exc:
            shot = await self._screenshot("grades")
            raise PageStructureError(f"Failed to load grades: {exc}", screenshot=shot)
        report = parse_grades(html)
        if term:
            report.entries = [e for e in report.entries if e.term == term]
        return report

    async def get_timetable(self, term: Optional[str] = None) -> list[TimetableSlot]:
        await self.login()
        try:
            await self._page.goto(
                self._secure_url(PATH_TIMETABLE),
                wait_until="domcontentloaded",
                timeout=45000,
            )
            await self._page.wait_for_timeout(2500)
            selects = self._page.locator("select")
            if term:
                await selects.nth(0).select_option(label=term)
                await self._page.wait_for_timeout(3000)
            # Second select = view; choose List for a parseable table.
            await self._page.locator("select").nth(1).select_option(label="List")
            await self._page.wait_for_timeout(3500)
            html = await self._page.content()
        except Exception as exc:
            shot = await self._screenshot("timetable")
            raise PageStructureError(f"Failed to load timetable: {exc}", screenshot=shot)
        return parse_timetable(html)

    async def get_exam_schedule(self, term: Optional[str] = None) -> list[ExamEntry]:
        await self.login()
        try:
            await self._page.goto(
                self._secure_url(PATH_EXAMS), wait_until="domcontentloaded", timeout=45000
            )
            await self._page.wait_for_timeout(2500)
            html = await self._page.content()
        except Exception as exc:
            shot = await self._screenshot("exams")
            raise PageStructureError(f"Failed to load exams: {exc}", screenshot=shot)
        return parse_exam_schedule(html)

    async def search_subjects(self, query: str) -> list[SubjectOffering]:
        # NEEDS_CALIBRATION: the subject-search page form has not been probed yet.
        raise PageStructureError(
            "search_subjects is not yet calibrated to the live subject-search page."
        )

    # --- registration (two-step) ------------------------------------------

    async def preview_registration(
        self, items: list[RegistrationItem]
    ) -> RegistrationPreview:
        await self.login()
        # NEEDS_CALIBRATION: real conflict detection navigates the registration
        # page. Fingerprint + summary are final.
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
        # NEEDS_CALIBRATION: perform the real add/drop submission.
        raise PageStructureError(
            "confirm_registration submission not yet calibrated to the live "
            "registration page."
        )
