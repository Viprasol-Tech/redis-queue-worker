"""Pluggable queue backends.

The :class:`QueueBackend` protocol is the single seam between the worker and
its storage. Any object implementing ``push`` / ``pop`` / ``ack`` / ``nack`` /
``dead_letter`` can drive the worker, which keeps the core logic free of
storage concerns and trivially testable.

:class:`InMemoryBackend` is a fully functional, FIFO, in-process implementation
used for tests and the offline demo. To run over real Redis, implement the
``QueueBackend`` protocol with a ``redis`` client (e.g. ``RPOPLPUSH`` for a
reliable ready->in-flight queue); the package itself imports no network deps.

Part of Redis Queue Worker by Viprasol Tech Private Limited (https://viprasol.com).
"""

from __future__ import annotations

from collections import deque
from typing import Protocol, runtime_checkable

from redis_queue_worker.job import Job


@runtime_checkable
class QueueBackend(Protocol):
    """Storage seam for the worker.

    A backend owns three logical queues: the *ready* queue (jobs waiting to be
    processed), an *in-flight* set (jobs popped but not yet ack/nack-ed), and a
    *dead-letter* queue (jobs that exhausted their retries).
    """

    def push(self, job: Job) -> None:
        """Append ``job`` to the tail of the ready queue."""
        ...

    def pop(self) -> Job | None:
        """Remove and return the head of the ready queue, or ``None`` if empty.

        The returned job is moved to the in-flight set until ``ack`` or ``nack``
        is called for it.
        """
        ...

    def ack(self, job: Job) -> None:
        """Acknowledge successful processing; drop ``job`` from in-flight."""
        ...

    def nack(self, job: Job) -> None:
        """Return a failed ``job`` to the ready queue for another attempt."""
        ...

    def dead_letter(self, job: Job) -> None:
        """Route a permanently failed ``job`` to the dead-letter queue."""
        ...


class InMemoryBackend:
    """A fully functional, FIFO, in-process :class:`QueueBackend`.

    Suitable for tests, local development, and the offline demo. Not durable and
    not safe across processes; back the ``QueueBackend`` protocol with Redis for that.
    """

    def __init__(self) -> None:
        self._ready: deque[Job] = deque()
        self._in_flight: dict[str, Job] = {}
        self._dead: list[Job] = []

    def push(self, job: Job) -> None:
        """Append ``job`` to the tail of the ready queue (FIFO order)."""
        self._ready.append(job)

    def pop(self) -> Job | None:
        """Pop the head of the ready queue and mark it in-flight."""
        if not self._ready:
            return None
        job = self._ready.popleft()
        self._in_flight[job.id] = job
        return job

    def ack(self, job: Job) -> None:
        """Drop ``job`` from the in-flight set after success."""
        self._in_flight.pop(job.id, None)

    def nack(self, job: Job) -> None:
        """Re-enqueue a failed ``job`` at the tail of the ready queue."""
        self._in_flight.pop(job.id, None)
        self._ready.append(job)

    def dead_letter(self, job: Job) -> None:
        """Move a permanently failed ``job`` to the dead-letter queue."""
        self._in_flight.pop(job.id, None)
        self._dead.append(job)

    def __len__(self) -> int:
        """Return the number of jobs currently waiting in the ready queue."""
        return len(self._ready)

    @property
    def ready(self) -> list[Job]:
        """A snapshot list of jobs currently waiting to be processed."""
        return list(self._ready)

    @property
    def in_flight(self) -> list[Job]:
        """A snapshot list of jobs popped but not yet ack/nack-ed."""
        return list(self._in_flight.values())

    @property
    def dead(self) -> list[Job]:
        """A snapshot list of jobs in the dead-letter queue."""
        return list(self._dead)
