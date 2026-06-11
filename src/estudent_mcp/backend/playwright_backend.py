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
from ..parsers import (
    parse_exam_schedule,
    parse_grades,
    parse_subject_detail,
    parse_subject_search,
    parse_timetable,
)
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

# Subject-search page controls.
SEL_SEARCH_BY_SUBJECT = "#mainForm\\:bySubject"
SEL_SEARCH_BY_PROGRAMME = "#mainForm\\:byProgramme"
SEL_SEARCH_YEARSEM = "#mainForm\\:yearsem"
SEL_SEARCH_SUBJCODE = "#mainForm\\:subjCode"
SEL_SEARCH_SUBJTITLE = "#mainForm\\:subjTitle"
# By-programme cascade: pick a hosting department, which AJAX-fills progId.
SEL_SEARCH_PROG_DEPT = "#mainForm\\:progOrgUnitId"
SEL_SEARCH_PROG_ID = "#mainForm\\:progId"
SEL_SEARCH_BTN = "#mainForm\\:searchBtn"
SEL_SEARCH_TABLE = "table[id$=searchTable]"
# First subject-code drill-in link in the result table.
SEL_SEARCH_FIRST_CODE = "a[id$=':0:subjCode']"

DEFAULT_ORIGIN = "https://www38.polyu.edu.hk"

# Navigation budgets (ms). Fast mode is enabled by the sniper during a grab
# window: when the portal is down, a probe should cost ~12s, not a 45s wait —
# what wins the course is how soon the first attempt lands after recovery.
NAV_TIMEOUT_DEFAULT_MS = 45000
NAV_TIMEOUT_FAST_MS = 12000

import re as _re

# A subject code is letters optionally followed by digits, e.g. "COMP", "COMP1011".
_CODE_RE = _re.compile(r"^[A-Za-z]{2,4}\d{0,4}[A-Za-z]?$")


def _looks_like_code(query: str) -> bool:
    return bool(_CODE_RE.match(query.strip()))


class PlaywrightBackend(EStudentBackend):
    def __init__(self, config: Config):
        self._cfg = config
        self._pw = None
        self._browser = None
        self._context = None
        self._page = None
        self._origin = DEFAULT_ORIGIN
        self._nav_timeout_ms = NAV_TIMEOUT_DEFAULT_MS

    def set_fast_fail(self, enabled: bool) -> None:
        self._nav_timeout_ms = NAV_TIMEOUT_FAST_MS if enabled else NAV_TIMEOUT_DEFAULT_MS

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

        nav = self._nav_timeout_ms
        try:
            await self._page.goto(
                ESTUDENT_LANDING, wait_until="domcontentloaded", timeout=nav
            )
            await self._page.wait_for_timeout(1000)
            # Landing -> ADFS SSO.
            async with self._page.expect_navigation(
                wait_until="domcontentloaded", timeout=min(30000, nav)
            ):
                await self._page.click(SEL_LANDING_LOGIN)
            # Fill ADFS credentials.
            await self._page.fill(SEL_NETID, self._cfg.netid)
            await self._page.fill(SEL_PASSWORD, self._cfg.password)
            async with self._page.expect_navigation(
                wait_until="domcontentloaded", timeout=min(30000, nav)
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
                self._secure_url(PATH_HOME),
                wait_until="domcontentloaded",
                timeout=min(30000, self._nav_timeout_ms),
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

    async def _open_search(self):
        await self._page.goto(
            self._secure_url(PATH_SUBJECT_SEARCH),
            wait_until="domcontentloaded",
            timeout=45000,
        )
        await self._page.wait_for_timeout(2500)

    async def _available_terms(self) -> list[str]:
        """Real year/sem option labels (excluding the placeholder), in page order."""
        labels = await self._page.eval_on_selector_all(
            f"{SEL_SEARCH_YEARSEM} option",
            "els => els.map(o => o.text.trim())",
        )
        return [t for t in labels if t and "Please Select" not in t]

    async def _search_once(self, query: str, term: str) -> str:
        await self._open_search()
        await self._page.check(SEL_SEARCH_BY_SUBJECT)
        await self._page.wait_for_timeout(500)
        await self._page.select_option(SEL_SEARCH_YEARSEM, label=term)
        await self._page.wait_for_timeout(800)
        # A code-looking query goes to subjCode; otherwise treat it as a title.
        field = SEL_SEARCH_SUBJCODE if _looks_like_code(query) else SEL_SEARCH_SUBJTITLE
        await self._page.fill(field, query)
        await self._page.click(SEL_SEARCH_BTN)
        await self._page.wait_for_timeout(3500)
        return await self._page.content()

    async def _run_subject_search(
        self, query: str, term: Optional[str]
    ) -> tuple[str, str]:
        """Run the search; if no term is given, try each offered term until one
        yields results. Returns (html, term_used)."""
        await self._open_search()
        terms = [term] if term else await self._available_terms()
        last_html = ""
        for t in terms:
            last_html = await self._search_once(query, t)
            if parse_subject_search(last_html):
                return last_html, t
        return last_html, (terms[-1] if terms else "")

    async def _collect_search_results(self) -> list[SubjectOffering]:
        """Walk the RichFaces datascroller, collecting every result page.

        Results are paginated (~20/page); the "next" scroller button carries an
        onclick only while enabled, so an empty `td[onclick*=next]` match means
        we are on the last page. Dedupe by code and cap iterations for safety.
        """
        seen: dict[str, SubjectOffering] = {}
        order: list[str] = []
        for _ in range(60):  # safety cap (~1200 subjects)
            html = await self._page.content()
            new_on_page = False
            for o in parse_subject_search(html):
                if o.subject_code not in seen:
                    seen[o.subject_code] = o
                    order.append(o.subject_code)
                    new_on_page = True
            nxt = self._page.locator('td[onclick*="next"]')
            if await nxt.count() == 0 or not new_on_page:
                break
            try:
                await nxt.first.click()
            except Exception:
                break
            await self._page.wait_for_timeout(2000)
        return [seen[c] for c in order]

    async def _attach_groups_if_single(
        self, offerings: list[SubjectOffering]
    ) -> None:
        """When exactly one subject matched, drill in to populate its groups."""
        if len(offerings) != 1:
            return
        try:
            await self._page.click(SEL_SEARCH_FIRST_CODE)
            await self._page.wait_for_timeout(3000)
            detail = parse_subject_detail(await self._page.content())
            if detail.subject_code == offerings[0].subject_code:
                offerings[0].groups = detail.groups
        except Exception:
            pass  # keep subject-level result if drill-in fails

    async def _select_option_containing(
        self, selector: str, needle: str, what: str
    ) -> str:
        """Select the <option> whose label matches `needle`, returning that label.

        Prefers a bracketed code match ("[COMP]") then exact, then unique
        substring. Raises PageStructureError on no/ambiguous match so the caller
        can narrow down rather than silently picking the wrong programme.
        """
        opts = await self._page.eval_on_selector_all(
            f"{selector} option", "els => els.map(o => o.text.trim())"
        )
        real = [o for o in opts if o and "Please Select" not in o]
        n = needle.strip()
        nl = n.lower()
        bracket = f"[{n.upper()}]"
        matches = [o for o in real if bracket in o.upper()]
        if not matches:
            matches = [o for o in real if o.lower() == nl]
        if not matches:
            matches = [o for o in real if nl in o.lower()]
        if not matches:
            raise PageStructureError(
                f"No {what} matches {needle!r}. e.g. available: {real[:6]}"
            )
        if len(matches) > 1:
            raise PageStructureError(
                f"{what} {needle!r} is ambiguous ({len(matches)} matches): "
                f"{matches[:8]} — please be more specific."
            )
        await self._page.select_option(selector, label=matches[0])
        return matches[0]

    async def search_subjects(
        self, query: str, term: Optional[str] = None
    ) -> list[SubjectOffering]:
        await self.login()
        try:
            await self._run_subject_search(query, term)
            offerings = await self._collect_search_results()
        except Exception as exc:
            shot = await self._screenshot("subject-search")
            raise PageStructureError(f"Subject search failed: {exc}", screenshot=shot)
        await self._attach_groups_if_single(offerings)
        return offerings

    async def search_subjects_by_program(
        self, department: str, program: str, term: Optional[str] = None
    ) -> list[SubjectOffering]:
        """By-programme search: select a hosting department (which AJAX-fills the
        programme list), pick the programme, then search. Returns the same
        subject-level grid as by-subject (with single-match drill-in)."""
        await self.login()
        try:
            await self._open_search()
            await self._page.check(SEL_SEARCH_BY_PROGRAMME)
            await self._page.wait_for_timeout(600)
            dept_label = await self._select_option_containing(
                SEL_SEARCH_PROG_DEPT, department, "department"
            )
            # Wait for the AJAX cascade to fill the programme dropdown.
            await self._page.wait_for_timeout(2500)
            await self._select_option_containing(
                SEL_SEARCH_PROG_ID, program, "programme"
            )
            await self._page.wait_for_timeout(600)
            if term:
                await self._page.select_option(SEL_SEARCH_YEARSEM, label=term)
            else:
                await self._page.select_option(SEL_SEARCH_YEARSEM, index=1)
            await self._page.wait_for_timeout(600)
            await self._page.click(SEL_SEARCH_BTN)
            await self._page.wait_for_timeout(3500)
            offerings = await self._collect_search_results()
        except PageStructureError:
            raise
        except Exception as exc:
            shot = await self._screenshot("by-program-search")
            raise PageStructureError(
                f"By-programme search failed (dept={department!r}, "
                f"program={program!r}): {exc}",
                screenshot=shot,
            )
        await self._attach_groups_if_single(offerings)
        return offerings

    async def get_subject_groups(
        self, subject_code: str, term: Optional[str] = None
    ) -> SubjectOffering:
        await self.login()
        try:
            html, _ = await self._run_subject_search(subject_code, term)
            offerings = parse_subject_search(html)
            # Find the exact-code row index, then click that drill-in link.
            idx = next(
                (i for i, o in enumerate(offerings)
                 if o.subject_code.upper() == subject_code.upper()),
                None,
            )
            if idx is None:
                raise PageStructureError(
                    f"Subject {subject_code} not found for the selected term."
                )
            await self._page.click(f"a[id$=':{idx}:subjCode']")
            await self._page.wait_for_timeout(3000)
            return parse_subject_detail(await self._page.content())
        except PageStructureError:
            raise
        except Exception as exc:
            shot = await self._screenshot("subject-groups")
            raise PageStructureError(
                f"Could not read groups for {subject_code}: {exc}", screenshot=shot
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
