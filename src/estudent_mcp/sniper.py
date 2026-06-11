"""Course sniper: scheduled submission and vacancy watching.

Deliberately restrained. Hard lower bounds on polling frequency prevent
"bombing" the server — see README for why high-frequency polling is both risky
for the user (rate-limit / WAF bans) and unfair to others. The sniper reuses the
backend's preview -> confirm path so the "see before submit" invariant holds
even for automated grabs.
"""

from __future__ import annotations

import asyncio
import time
import uuid
from dataclasses import dataclass, field
from enum import Enum
from typing import Awaitable, Callable, Optional

from .backend.base import EStudentBackend
from .errors import CredentialsError, FrequencyError
from .models import RegistrationItem

# --- Frequency safety bounds (seconds) -------------------------------------
# These are the floor. Configuring below them raises FrequencyError.
OPEN_TIME_MIN_RETRY_INTERVAL = 3.0      # retries no faster than every 3s
OPEN_TIME_MAX_TOTAL_DURATION = 120.0    # stop retrying after 2 minutes
WATCH_VACANCY_MIN_INTERVAL = 60.0       # check vacancy no more than once a minute

# Same transient error this many times in a row => the problem isn't going
# away on its own (portal redesign, network down); stop burning attempts.
MAX_CONSECUTIVE_ERRORS = 5


class SniperMode(str, Enum):
    OPEN_TIME = "open_time"
    WATCH_VACANCY = "watch_vacancy"


class SniperStatus(str, Enum):
    PENDING = "pending"
    RUNNING = "running"
    SUCCEEDED = "succeeded"
    FAILED = "failed"
    STOPPED = "stopped"
    TIMED_OUT = "timed_out"


def validate_frequency(
    mode: SniperMode,
    *,
    retry_interval: float,
    total_duration: float | None = None,
    watch_interval: float | None = None,
) -> None:
    """Raise FrequencyError if requested cadence is faster than the safe floor."""
    if mode is SniperMode.OPEN_TIME:
        if retry_interval < OPEN_TIME_MIN_RETRY_INTERVAL:
            raise FrequencyError(
                f"open_time retry interval {retry_interval}s is below the minimum "
                f"{OPEN_TIME_MIN_RETRY_INTERVAL}s. High-frequency retries risk an "
                f"account/IP ban and may violate the university's acceptable-use policy."
            )
        if total_duration is not None and total_duration > OPEN_TIME_MAX_TOTAL_DURATION:
            raise FrequencyError(
                f"open_time total duration {total_duration}s exceeds the cap "
                f"{OPEN_TIME_MAX_TOTAL_DURATION}s."
            )
    elif mode is SniperMode.WATCH_VACANCY:
        interval = watch_interval if watch_interval is not None else retry_interval
        if interval < WATCH_VACANCY_MIN_INTERVAL:
            raise FrequencyError(
                f"watch_vacancy interval {interval}s is below the minimum "
                f"{WATCH_VACANCY_MIN_INTERVAL}s."
            )


@dataclass
class SniperJob:
    job_id: str
    mode: SniperMode
    items: list[RegistrationItem]
    status: SniperStatus = SniperStatus.PENDING
    detail: str = ""
    open_time_epoch: Optional[float] = None
    retry_interval: float = OPEN_TIME_MIN_RETRY_INTERVAL
    total_duration: float = OPEN_TIME_MAX_TOTAL_DURATION
    watch_interval: float = WATCH_VACANCY_MIN_INTERVAL
    then_watch: bool = False
    attempts: int = 0
    consecutive_errors: int = 0
    log: list[str] = field(default_factory=list)
    _task: Optional[asyncio.Task] = field(default=None, repr=False)

    def public_dict(self) -> dict:
        return {
            "job_id": self.job_id,
            "mode": self.mode.value,
            "status": self.status.value,
            "detail": self.detail,
            "then_watch": self.then_watch,
            "attempts": self.attempts,
            "items": [
                {"action": i.action, "subject_code": i.subject_code, "section": i.section}
                for i in self.items
            ],
            "log": self.log[-20:],
        }


# A notifier is called with a short human-readable message on terminal events.
Notifier = Callable[[str], Awaitable[None]]


async def _noop_notifier(_msg: str) -> None:
    return None


class SniperManager:
    """Owns running sniper jobs. One instance per server process."""

    def __init__(
        self,
        backend: EStudentBackend,
        attempt_registration: Callable[[list[RegistrationItem]], Awaitable[bool]],
        notifier: Notifier | None = None,
        clock: Callable[[], float] = time.time,
        sleep: Callable[[float], Awaitable[None]] = asyncio.sleep,
    ):
        """`attempt_registration` performs one preview->confirm attempt and returns
        True on success. Injected so tests can drive the scheduler without a browser.
        `clock`/`sleep` are injectable for fast deterministic tests."""
        self._backend = backend
        self._attempt = attempt_registration
        self._notify = notifier or _noop_notifier
        self._clock = clock
        self._sleep = sleep
        self._jobs: dict[str, SniperJob] = {}

    def list_jobs(self) -> list[dict]:
        return [j.public_dict() for j in self._jobs.values()]

    def get_job(self, job_id: str) -> SniperJob | None:
        return self._jobs.get(job_id)

    def stop_job(self, job_id: str) -> bool:
        job = self._jobs.get(job_id)
        if job is None:
            return False
        if job._task is not None and not job._task.done():
            job._task.cancel()
        if job.status in (SniperStatus.PENDING, SniperStatus.RUNNING):
            job.status = SniperStatus.STOPPED
            job.detail = "Stopped by user."
        return True

    def start_open_time(
        self,
        items: list[RegistrationItem],
        open_time_epoch: float,
        retry_interval: float = OPEN_TIME_MIN_RETRY_INTERVAL,
        total_duration: float = OPEN_TIME_MAX_TOTAL_DURATION,
        then_watch: bool = False,
        watch_interval: float = WATCH_VACANCY_MIN_INTERVAL,
    ) -> SniperJob:
        validate_frequency(
            SniperMode.OPEN_TIME,
            retry_interval=retry_interval,
            total_duration=total_duration,
        )
        if then_watch:
            validate_frequency(
                SniperMode.WATCH_VACANCY,
                retry_interval=watch_interval,
                watch_interval=watch_interval,
            )
        job = SniperJob(
            job_id=uuid.uuid4().hex[:8],
            mode=SniperMode.OPEN_TIME,
            items=items,
            open_time_epoch=open_time_epoch,
            retry_interval=retry_interval,
            total_duration=total_duration,
            then_watch=then_watch,
            watch_interval=watch_interval,
        )
        self._jobs[job.job_id] = job
        job._task = asyncio.ensure_future(self._run_open_time(job))
        return job

    def start_watch_vacancy(
        self,
        items: list[RegistrationItem],
        watch_interval: float = WATCH_VACANCY_MIN_INTERVAL,
    ) -> SniperJob:
        validate_frequency(
            SniperMode.WATCH_VACANCY,
            retry_interval=watch_interval,
            watch_interval=watch_interval,
        )
        job = SniperJob(
            job_id=uuid.uuid4().hex[:8],
            mode=SniperMode.WATCH_VACANCY,
            items=items,
            watch_interval=watch_interval,
        )
        self._jobs[job.job_id] = job
        job._task = asyncio.ensure_future(self._run_watch_vacancy(job))
        return job

    async def _safe_attempt(self, job: SniperJob) -> bool:
        """Run one registration attempt; transient failures count as a miss.

        A session that expired mid-job heals itself: every attempt begins with
        backend.login(), which re-authenticates automatically. What login()
        cannot heal is a dead browser/page object, so on any unexpected error
        we also close the backend — the next attempt relaunches it from
        scratch (fresh browser, fresh login). Only CredentialsError (wrong
        password — retrying is pointless) or MAX_CONSECUTIVE_ERRORS identical
        failures in a row escape to the caller and end the job.
        """
        try:
            ok = await self._attempt(job.items)
        except (asyncio.CancelledError, CredentialsError):
            raise
        except Exception as exc:  # noqa: BLE001 - transient: log, reset, retry
            job.consecutive_errors += 1
            job.log.append(
                f"attempt {job.attempts}: {type(exc).__name__}: {exc} "
                f"({job.consecutive_errors} consecutive)"
            )
            if job.consecutive_errors >= MAX_CONSECUTIVE_ERRORS:
                raise RuntimeError(
                    f"{job.consecutive_errors} consecutive errors, last: {exc}"
                ) from exc
            if self._backend is not None:
                try:
                    await self._backend.close()
                except Exception:  # noqa: BLE001
                    pass
            return False
        job.consecutive_errors = 0
        if not ok:
            job.log.append(f"attempt {job.attempts}: no luck")
        return ok

    async def _watch_loop(self, job: SniperJob) -> None:
        """Poll for a vacancy forever (caller-bounded only by stop_job)."""
        job.status = SniperStatus.RUNNING
        while True:
            job.attempts += 1
            if await self._safe_attempt(job):
                job.status = SniperStatus.SUCCEEDED
                job.detail = f"Grabbed vacancy after {job.attempts} attempt(s)."
                job.log.append(job.detail)
                await self._notify(f"[sniper {job.job_id}] {job.detail}")
                return
            await self._sleep(job.watch_interval)

    async def _run_open_time(self, job: SniperJob) -> None:
        try:
            # Wait until the registration window opens.
            wait = (job.open_time_epoch or self._clock()) - self._clock()
            if wait > 0:
                job.status = SniperStatus.PENDING
                job.detail = f"Waiting {wait:.0f}s until open time."
                await self._sleep(wait)

            job.status = SniperStatus.RUNNING
            deadline = self._clock() + job.total_duration
            while self._clock() <= deadline:
                job.attempts += 1
                if await self._safe_attempt(job):
                    job.status = SniperStatus.SUCCEEDED
                    job.detail = f"Registered after {job.attempts} attempt(s)."
                    job.log.append(job.detail)
                    await self._notify(f"[sniper {job.job_id}] {job.detail}")
                    return
                await self._sleep(job.retry_interval)

            if job.then_watch:
                job.detail = (
                    f"Open window ended after {job.attempts} attempt(s); "
                    f"falling back to vacancy watching every {job.watch_interval:.0f}s."
                )
                job.log.append(job.detail)
                await self._notify(f"[sniper {job.job_id}] {job.detail}")
                await self._watch_loop(job)
                return

            job.status = SniperStatus.TIMED_OUT
            job.detail = f"Gave up after {job.attempts} attempt(s)."
            await self._notify(f"[sniper {job.job_id}] {job.detail}")
        except asyncio.CancelledError:
            job.status = SniperStatus.STOPPED
            raise
        except Exception as exc:  # noqa: BLE001 - report, don't crash the server
            job.status = SniperStatus.FAILED
            job.detail = f"Error: {exc}"
            job.log.append(job.detail)
            await self._notify(f"[sniper {job.job_id}] {job.detail}")

    async def _run_watch_vacancy(self, job: SniperJob) -> None:
        try:
            await self._watch_loop(job)
        except asyncio.CancelledError:
            job.status = SniperStatus.STOPPED
            raise
        except Exception as exc:  # noqa: BLE001
            job.status = SniperStatus.FAILED
            job.detail = f"Error: {exc}"
            job.log.append(job.detail)
            await self._notify(f"[sniper {job.job_id}] {job.detail}")
