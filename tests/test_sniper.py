"""Sniper scheduler tests. Use a fake clock + instant sleep so the time-based
logic runs deterministically without real waiting."""

import asyncio

import pytest

from estudent_mcp.errors import (
    CredentialsError,
    FrequencyError,
    LoginError,
    PageStructureError,
)
from estudent_mcp.models import RegistrationItem
from estudent_mcp.sniper import (
    MAX_CONSECUTIVE_ERRORS,
    OPEN_TIME_MIN_RETRY_INTERVAL,
    PORTAL_DOWN_GIVE_UP,
    SniperManager,
    SniperMode,
    SniperStatus,
    validate_frequency,
)

ITEMS = [RegistrationItem("add", "COMP2011", "1A")]


# --- frequency floor enforcement ------------------------------------------


def test_open_time_below_floor_rejected():
    with pytest.raises(FrequencyError):
        validate_frequency(SniperMode.OPEN_TIME, retry_interval=0.1)


def test_open_time_over_duration_rejected():
    with pytest.raises(FrequencyError):
        validate_frequency(
            SniperMode.OPEN_TIME, retry_interval=3.0, total_duration=99999
        )


def test_watch_vacancy_below_floor_rejected():
    with pytest.raises(FrequencyError):
        validate_frequency(
            SniperMode.WATCH_VACANCY, retry_interval=5, watch_interval=5
        )


def test_floor_values_accepted():
    validate_frequency(SniperMode.OPEN_TIME, retry_interval=3.0, total_duration=1800)
    validate_frequency(SniperMode.WATCH_VACANCY, retry_interval=30, watch_interval=30)


# --- scheduler behaviour ---------------------------------------------------


class FakeClock:
    def __init__(self):
        self.t = 1000.0

    def now(self):
        return self.t

    async def sleep(self, seconds):
        # Advance virtual time instead of really waiting.
        self.t += seconds
        await asyncio.sleep(0)


class FakeBackend:
    """Records close()/set_fast_fail() calls — stands in for the browser."""

    def __init__(self):
        self.closes = 0
        self.fast_fail_calls = []

    async def close(self):
        self.closes += 1

    def set_fast_fail(self, enabled):
        self.fast_fail_calls.append(enabled)


def _manager(attempt, clock, backend=None):
    return SniperManager(
        backend=backend,
        attempt_registration=attempt,
        clock=clock.now,
        sleep=clock.sleep,
    )


async def test_open_time_succeeds_on_third_attempt():
    clock = FakeClock()
    calls = {"n": 0}

    async def attempt(_items):
        calls["n"] += 1
        return calls["n"] >= 3

    mgr = _manager(attempt, clock)
    job = mgr.start_open_time(ITEMS, open_time_epoch=clock.t + 10, retry_interval=3.0)
    await job._task
    assert job.status is SniperStatus.SUCCEEDED
    assert job.attempts == 3


async def test_open_time_times_out_when_never_available():
    clock = FakeClock()

    async def attempt(_items):
        return False

    mgr = _manager(attempt, clock)
    job = mgr.start_open_time(
        ITEMS, open_time_epoch=clock.t, retry_interval=3.0, total_duration=12.0
    )
    await job._task
    assert job.status is SniperStatus.TIMED_OUT
    assert job.attempts >= 1


async def test_watch_vacancy_grabs_when_opens():
    clock = FakeClock()
    calls = {"n": 0}

    async def attempt(_items):
        calls["n"] += 1
        return calls["n"] >= 2

    mgr = _manager(attempt, clock)
    job = mgr.start_watch_vacancy(ITEMS, watch_interval=60)
    await job._task
    assert job.status is SniperStatus.SUCCEEDED
    assert job.attempts == 2


async def test_stop_job_cancels():
    clock = FakeClock()

    async def attempt(_items):
        return False

    mgr = _manager(attempt, clock)
    job = mgr.start_watch_vacancy(ITEMS, watch_interval=60)
    await asyncio.sleep(0)  # let it start
    mgr.stop_job(job.job_id)
    try:
        await job._task
    except asyncio.CancelledError:
        pass
    assert job.status is SniperStatus.STOPPED


# --- error resilience --------------------------------------------------------


async def test_transient_error_recovers_and_resets_browser():
    """A LoginError mid-job (e.g. expired session, dead page) must not kill the
    job: the browser is reset and the next attempt succeeds."""
    clock = FakeClock()
    backend = FakeBackend()
    calls = {"n": 0}

    async def attempt(_items):
        calls["n"] += 1
        if calls["n"] == 1:
            raise LoginError("session dropped mid-grab")
        return True

    mgr = _manager(attempt, clock, backend=backend)
    job = mgr.start_open_time(ITEMS, open_time_epoch=clock.t, retry_interval=3.0)
    await job._task
    assert job.status is SniperStatus.SUCCEEDED
    assert job.attempts == 2
    assert backend.closes == 1  # browser was reset after the error
    assert job.consecutive_errors == 0
    assert job.unreachable_since is None  # success cleared the outage clock


async def test_credentials_error_is_fatal():
    clock = FakeClock()

    async def attempt(_items):
        raise CredentialsError("password rejected")

    mgr = _manager(attempt, clock)
    job = mgr.start_open_time(ITEMS, open_time_epoch=clock.t, retry_interval=3.0)
    await job._task
    assert job.status is SniperStatus.FAILED
    assert job.attempts == 1  # no pointless retries with a bad password
    assert "password rejected" in job.detail


async def test_structural_errors_escalate_after_strikes():
    """Portal-redesign errors won't fix themselves — 5 strikes ends the job."""
    clock = FakeClock()

    async def attempt(_items):
        raise PageStructureError("selector not found")

    mgr = _manager(attempt, clock, backend=FakeBackend())
    job = mgr.start_watch_vacancy(ITEMS, watch_interval=60)
    await job._task
    assert job.status is SniperStatus.FAILED
    assert job.attempts == MAX_CONSECUTIVE_ERRORS
    assert "page-structure" in job.detail


async def test_portal_outage_outlives_strike_limit():
    """A launch-day crash (continuous unreachability) must NOT die after a few
    strikes — the job keeps probing and only gives up after PORTAL_DOWN_GIVE_UP
    seconds of continuous downtime."""
    clock = FakeClock()

    async def attempt(_items):
        raise LoginError("portal down")

    mgr = _manager(attempt, clock, backend=FakeBackend())
    job = mgr.start_watch_vacancy(ITEMS, watch_interval=60)
    await job._task
    assert job.status is SniperStatus.FAILED
    assert job.attempts > MAX_CONSECUTIVE_ERRORS  # survived well past 5 strikes
    # 60s between probes => give-up needs PORTAL_DOWN_GIVE_UP worth of sleeps.
    assert job.attempts == int(PORTAL_DOWN_GIVE_UP / 60) + 1
    assert "unreachable" in job.detail


async def test_portal_recovery_resets_outage_clock():
    """Outage clock restarts when the portal answers, even with no vacancy."""
    clock = FakeClock()
    calls = {"n": 0}

    async def attempt(_items):
        calls["n"] += 1
        if calls["n"] == 2:
            return False  # portal answered: still full, but reachable
        if calls["n"] <= 3:
            raise LoginError("portal down")
        return True

    mgr = _manager(attempt, clock, backend=FakeBackend())
    job = mgr.start_watch_vacancy(ITEMS, watch_interval=60)
    await job._task
    assert job.status is SniperStatus.SUCCEEDED
    assert job.attempts == 4


async def test_open_time_toggles_fast_fail():
    clock = FakeClock()
    backend = FakeBackend()

    async def attempt(_items):
        return True

    mgr = _manager(attempt, clock, backend=backend)
    job = mgr.start_open_time(ITEMS, open_time_epoch=clock.t, retry_interval=3.0)
    await job._task
    assert job.status is SniperStatus.SUCCEEDED
    assert backend.fast_fail_calls == [True, False]  # enabled, then restored


async def test_open_time_falls_back_to_watch_vacancy():
    """then_watch=True: an unsuccessful open window continues as vacancy
    watching instead of timing out, and still grabs when a seat opens."""
    clock = FakeClock()
    calls = {"n": 0}

    async def attempt(_items):
        calls["n"] += 1
        return calls["n"] >= 8  # full through the open window, opens later

    mgr = _manager(attempt, clock)
    job = mgr.start_open_time(
        ITEMS,
        open_time_epoch=clock.t,
        retry_interval=3.0,
        total_duration=12.0,  # at most ~5 attempts inside the window
        then_watch=True,
        watch_interval=60,
    )
    await job._task
    assert job.status is SniperStatus.SUCCEEDED
    assert job.attempts == 8
    assert any("falling back" in line for line in job.log)


def test_then_watch_validates_watch_interval():
    clock = FakeClock()

    async def attempt(_items):
        return False

    mgr = _manager(attempt, clock)
    with pytest.raises(FrequencyError):
        mgr.start_open_time(
            ITEMS,
            open_time_epoch=clock.t,
            retry_interval=3.0,
            then_watch=True,
            watch_interval=5,  # below the 60s floor
        )
