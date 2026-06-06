"""Tests for the worker dispatch, retry, and dead-letter logic."""

from __future__ import annotations

from typing import Any

from redis_queue_worker.backend import InMemoryBackend
from redis_queue_worker.job import Job
from redis_queue_worker.worker import Worker


def test_success_acks_job() -> None:
    backend = InMemoryBackend()
    worker = Worker(backend)
    seen: list[dict[str, Any]] = []
    worker.register("ok", lambda payload: seen.append(payload))

    backend.push(Job(name="ok", payload={"v": 7}))
    stats = worker.run()

    assert seen == [{"v": 7}]
    assert stats.processed == 1
    assert stats.dead_lettered == 0
    assert not backend.ready and not backend.in_flight and not backend.dead


def test_failing_handler_retries_then_dead_letters() -> None:
    backend = InMemoryBackend()
    worker = Worker(backend)
    calls = {"n": 0}

    @worker.handler("flaky")
    def _always_fails(payload: dict[str, Any]) -> None:
        calls["n"] += 1
        raise RuntimeError("boom")

    backend.push(Job(name="flaky", max_retries=2))
    stats = worker.run()

    # Attempt budget = max_retries + 1 = 3 total runs of the handler.
    assert calls["n"] == 3
    assert stats.retried == 2
    assert stats.dead_lettered == 1
    assert stats.processed == 0
    assert len(backend.dead) == 1
    assert backend.dead[0].attempts == 3


def test_retry_then_eventual_success() -> None:
    backend = InMemoryBackend()
    worker = Worker(backend)
    calls = {"n": 0}

    @worker.handler("eventually")
    def _succeeds_third_time(payload: dict[str, Any]) -> None:
        calls["n"] += 1
        if calls["n"] < 3:
            raise RuntimeError("not yet")

    backend.push(Job(name="eventually", max_retries=5))
    stats = worker.run()

    assert calls["n"] == 3
    assert stats.processed == 1
    assert stats.retried == 2
    assert stats.dead_lettered == 0
    assert not backend.dead


def test_unknown_job_name_is_dead_lettered() -> None:
    backend = InMemoryBackend()
    worker = Worker(backend)

    backend.push(Job(name="does-not-exist"))
    stats = worker.run()

    assert stats.dead_lettered == 1
    assert stats.processed == 0
    assert stats.retried == 0
    assert len(backend.dead) == 1
    assert backend.dead[0].name == "does-not-exist"


def test_process_one_on_empty_returns_none() -> None:
    worker = Worker(InMemoryBackend())
    assert worker.process_one() is None


def test_fifo_processing_order() -> None:
    backend = InMemoryBackend()
    worker = Worker(backend)
    order: list[int] = []
    worker.register("rec", lambda payload: order.append(int(payload["i"])))

    for i in range(4):
        backend.push(Job(name="rec", payload={"i": i}))
    worker.run()

    assert order == [0, 1, 2, 3]
