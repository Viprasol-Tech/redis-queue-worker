"""Tests for the Job model."""

from __future__ import annotations

from redis_queue_worker.job import Job


def test_defaults() -> None:
    job = Job(name="email")
    assert job.attempts == 0
    assert job.max_retries == 3
    assert job.payload == {}
    assert job.id  # non-empty unique id


def test_ids_are_unique() -> None:
    assert Job(name="a").id != Job(name="a").id


def test_attempted_increments_without_mutating() -> None:
    job = Job(name="a", attempts=0)
    nxt = job.attempted()
    assert job.attempts == 0  # original untouched
    assert nxt.attempts == 1
    assert nxt.id == job.id  # same logical job


def test_can_retry_budget() -> None:
    # max_retries=2 -> attempt budget of 3 (initial + 2 retries).
    job = Job(name="a", max_retries=2)
    assert job.attempted().can_retry()  # attempts=1 -> True
    assert Job(name="a", max_retries=2, attempts=2).can_retry()  # 2 <= 2
    assert not Job(name="a", max_retries=2, attempts=3).can_retry()  # 3 > 2
