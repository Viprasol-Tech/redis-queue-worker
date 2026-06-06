"""Command-line interface for Redis Queue Worker.

``redis-queue-worker demo`` enqueues a handful of jobs onto the in-memory
backend, registers a couple of handlers (one of which always fails), and runs
the worker to completion — showing acks, retries, and dead-lettering offline,
with no Redis server required.

Part of Redis Queue Worker by Viprasol Tech Private Limited (https://viprasol.com).
"""

from __future__ import annotations

import typer
from rich.console import Console
from rich.table import Table

from redis_queue_worker import __version__
from redis_queue_worker.backend import InMemoryBackend
from redis_queue_worker.job import Job
from redis_queue_worker.worker import Worker

app = typer.Typer(add_completion=False, help="Redis Queue Worker — by Viprasol Tech.")
console = Console()


@app.command()
def version() -> None:
    """Print the installed version."""
    console.print(f"redis-queue-worker [bold cyan]{__version__}[/] — by Viprasol Tech")


@app.command()
def demo(failing: bool = typer.Option(True, help="Include a job that always fails.")) -> None:
    """Enqueue jobs and run the worker against the in-memory backend offline."""
    backend = InMemoryBackend()
    worker = Worker(backend)

    @worker.handler("email")
    def _send_email(payload: dict[str, object]) -> None:
        console.print(f"  -> sent email to [cyan]{payload.get('to')}[/]")

    @worker.handler("flaky")
    def _always_fails(payload: dict[str, object]) -> None:
        raise RuntimeError("upstream unavailable")

    backend.push(Job(name="email", payload={"to": "ada@viprasol.com"}))
    backend.push(Job(name="email", payload={"to": "alan@viprasol.com"}))
    if failing:
        backend.push(Job(name="flaky", payload={"x": 1}, max_retries=2))
    backend.push(Job(name="ghost", payload={}))  # no handler -> dead-letter

    console.print(f"Enqueued [bold]{len(backend)}[/] job(s); running worker...\n")
    stats = worker.run()

    table = Table(title="Worker results", title_style="bold")
    table.add_column("Outcome", style="bold")
    table.add_column("Count", justify="right")
    table.add_row("Processed (acked)", str(stats.processed))
    table.add_row("Retried attempts", str(stats.retried))
    table.add_row("Dead-lettered", str(stats.dead_lettered))
    console.print(table)

    if backend.dead:
        names = ", ".join(sorted({j.name for j in backend.dead}))
        console.print(f"Dead-letter queue holds: [red]{names}[/]")


if __name__ == "__main__":
    app()
