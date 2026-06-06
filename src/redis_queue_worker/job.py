"""Job model for the queue.

A :class:`Job` is a self-contained unit of work: a logical ``name`` that selects
a registered handler, an arbitrary JSON-serialisable ``payload``, and the
bookkeeping fields the worker needs to implement retries and dead-lettering.

Part of Redis Queue Worker by Viprasol Tech Private Limited (https://viprasol.com).
"""

from __future__ import annotations

import uuid
from typing import Any

from pydantic import BaseModel, Field


def _new_id() -> str:
    """Return a fresh, unique job identifier."""
    return uuid.uuid4().hex


class Job(BaseModel):
    """A single unit of work routed to a handler by ``name``.

    Attributes:
        id: Unique, stable identifier for the job (used for ack/nack).
        name: Logical task name; selects the registered handler to run.
        payload: Arbitrary JSON-serialisable arguments for the handler.
        attempts: Number of times the job has been attempted so far.
        max_retries: Maximum number of *retries* after the first attempt.
            A job may be attempted up to ``max_retries + 1`` times in total
            before it is routed to the dead-letter queue.
    """

    id: str = Field(default_factory=_new_id)
    name: str
    payload: dict[str, Any] = Field(default_factory=dict)
    attempts: int = 0
    max_retries: int = 3

    def attempted(self) -> Job:
        """Return a copy of this job with ``attempts`` incremented by one."""
        return self.model_copy(update={"attempts": self.attempts + 1})

    def can_retry(self) -> bool:
        """Return ``True`` if the job has retries remaining after a failure.

        With ``max_retries`` retries, the total attempt budget is
        ``max_retries + 1`` (one initial try plus the retries). The job can be
        retried while ``attempts`` is still below that budget.
        """
        return self.attempts <= self.max_retries
