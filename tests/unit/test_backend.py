"""Tests for the in-memory queue backend."""

from __future__ import annotations

from redis_queue_worker.backend import InMemoryBackend, QueueBackend
from redis_queue_worker.job import Job


def test_inmemory_is_a_queue_backend() -> None:
    assert isinstance(InMemoryBackend(), QueueBackend)


def test_fifo_ordering() -> None:
    backend = InMemoryBackend()
    for i in range(5):
        backend.push(Job(name="t", payload={"i": i}))

    popped = []
    while (job := backend.pop()) is not None:
        popped.append(job.payload["i"])
        backend.ack(job)

    assert popped == [0, 1, 2, 3, 4]


def test_pop_empty_returns_none() -> None:
    assert InMemoryBackend().pop() is None


def test_ack_clears_in_flight() -> None:
    backend = InMemoryBackend()
    backend.push(Job(name="t"))
    job = backend.pop()
    assert job is not None
    assert backend.in_flight
    backend.ack(job)
    assert not backend.in_flight


def test_nack_requeues_at_tail() -> None:
    backend = InMemoryBackend()
    first = Job(name="a")
    second = Job(name="b")
    backend.push(first)
    backend.push(second)

    job = backend.pop()  # 'a'
    assert job is not None and job.name == "a"
    backend.nack(job)  # 'a' goes to the tail, behind 'b'

    assert [j.name for j in backend.ready] == ["b", "a"]


def test_dead_letter_moves_job() -> None:
    backend = InMemoryBackend()
    backend.push(Job(name="t"))
    job = backend.pop()
    assert job is not None
    backend.dead_letter(job)
    assert [j.id for j in backend.dead] == [job.id]
    assert not backend.in_flight
