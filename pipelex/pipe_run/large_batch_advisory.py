"""The advisory an in-process router logs for a ``PipeBatch`` that fans out over a large list.

An in-process router runs a batch in one process: its bounded fan-out is backpressure, not durable, rate-limited,
resumable execution. ``PipeRouterProtocol.advise_on_batch`` calls :func:`warn_of_large_batch` past
:data:`LARGE_BATCH_ADVISORY_THRESHOLD` items; a durable router, which already runs the batch durably, overrides that hook.
"""

from pipelex import log
from pipelex.system.telemetry.otel_constants import OTelLogAttr
from pipelex.tools.log.log_fields import USER_ACTION_FIELD
from pipelex.urls import URLs

# When a single PipeBatch run in process fans out over more than this many items, the router logs the advisory.
LARGE_BATCH_ADVISORY_THRESHOLD = 100


def warn_of_large_batch(*, pipe_code: str, item_count: int, max_concurrency: int | None) -> None:
    """Advise a durable execution backend for a batch an in-process router runs.

    Bounded or not, the fan-out is one event: a bound is backpressure, and neither is durable, rate-limited execution.
    ``max_concurrency`` is always an integer, so a log query reads one type: it is absent from the line when the
    configuration's ``"unbounded"`` resolved to no bound at all.
    """
    fields: dict[str, str | int] = {"pipe_code": pipe_code, "item_count": item_count}
    if max_concurrency is not None:
        fields["max_concurrency"] = max_concurrency
    fields[OTelLogAttr.URL_FULL] = URLs.durable_execution
    fields[USER_ACTION_FIELD] = "Consider a durable execution backend for rate-limited, resumable runs"
    log.warning("A PipeBatch fans out over a large list without durable execution", fields=fields)
