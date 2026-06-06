"""The worker loop: pop, dispatch, ack/retry/dead-letter.

A :class:`Worker` binds a :class:`~redis_queue_worker.backend.QueueBackend` to a
registry of named handlers. For each job it pops, it runs the matching handler
and then resolves the outcome:

* handler succeeds  -> ``ack`` the job (done).
* handler raises and retries remain  -> ``nack`` the job (re-enqueued).
* handler raises and retries exhausted  -> ``dead_letter`` the job.
* no handler registered for the job name  -> ``dead_letter`` immediately.

Part of Redis Queue Worker by Viprasol Tech Private Limited (https://viprasol.com).
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any

from redis_queue_worker.backend import QueueBackend
from redis_queue_worker.job import Job

Handler = Callable[[dict[str, Any]], None]
"""A handler receives a job's ``payload`` and returns ``None``; it signals
failure by raising any exception."""


class UnknownJobError(Exception):
    """Raised internally when a job names a handler that is not registered."""


@dataclass
class WorkerStats:
    """Counters describing what a worker did during a run.

    Attributes:
        processed: Jobs handled successfully and acked.
        retried: Individual failed attempts that were re-enqueued.
        dead_lettered: Jobs routed to the dead-letter queue.
    """

    processed: int = 0
    retried: int = 0
    dead_lettered: int = 0


@dataclass
class Worker:
    """Pops jobs from a backend and dispatches them to registered handlers.

    Args:
        backend: The queue backend to pull jobs from and report outcomes to.
        handlers: Optional initial mapping of job name to handler callable.
    """

    backend: QueueBackend
    handlers: dict[str, Handler] = field(default_factory=dict)
    stats: WorkerStats = field(default_factory=WorkerStats)

    def register(self, name: str, handler: Handler) -> None:
        """Register ``handler`` to run for jobs named ``name``."""
        self.handlers[name] = handler

    def handler(self, name: str) -> Callable[[Handler], Handler]:
        """Decorator form of :meth:`register` for a handler named ``name``."""

        def decorator(fn: Handler) -> Handler:
            self.register(name, fn)
            return fn

        return decorator

    def process_one(self) -> Job | None:
        """Pop and process a single job.

        Returns the job that was processed (regardless of outcome), or ``None``
        if the ready queue was empty.
        """
        job = self.backend.pop()
        if job is None:
            return None

        attempt = job.attempted()
        handler = self.handlers.get(attempt.name)
        if handler is None:
            # Unknown job name: it can never succeed, so dead-letter at once.
            self.backend.dead_letter(attempt)
            self.stats.dead_lettered += 1
            return attempt

        try:
            handler(attempt.payload)
        except Exception:
            if attempt.can_retry():
                self.backend.nack(attempt)
                self.stats.retried += 1
            else:
                self.backend.dead_letter(attempt)
                self.stats.dead_lettered += 1
            return attempt

        self.backend.ack(attempt)
        self.stats.processed += 1
        return attempt

    def run(self, max_jobs: int | None = None) -> WorkerStats:
        """Drain the ready queue until empty (or ``max_jobs`` are processed).

        Because a failed job is re-enqueued, this loop naturally performs the
        retries before eventually acking or dead-lettering every job.

        Args:
            max_jobs: Optional cap on the number of pop iterations, useful to
                bound runs in tests. ``None`` means run until the queue drains.

        Returns:
            The accumulated :class:`WorkerStats` for this worker.
        """
        seen = 0
        while max_jobs is None or seen < max_jobs:
            job = self.process_one()
            if job is None:
                break
            seen += 1
        return self.stats
