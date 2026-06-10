"""Sniper scheduler tests. Use a fake clock + instant sleep so the time-based
logic runs deterministically without real waiting."""

import asyncio

import pytest

from estudent_mcp.errors import FrequencyError
from estudent_mcp.models import RegistrationItem
from estudent_mcp.sniper import (
    OPEN_TIME_MIN_RETRY_INTERVAL,
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
            SniperMode.OPEN_TIME, retry_interval=3.0, total_duration=999
        )


def test_watch_vacancy_below_floor_rejected():
    with pytest.raises(FrequencyError):
        validate_frequency(
            SniperMode.WATCH_VACANCY, retry_interval=5, watch_interval=5
        )


def test_floor_values_accepted():
    validate_frequency(SniperMode.OPEN_TIME, retry_interval=3.0, total_duration=120)
    validate_frequency(SniperMode.WATCH_VACANCY, retry_interval=60, watch_interval=60)


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


def _manager(attempt, clock):
    return SniperManager(
        backend=None,
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
