from typing import Any

from tenacity import RetryCallState

from pipelex import log
from pipelex.tools.log.error_fields import ERROR_TYPE_FIELD


def log_retry(retry_state: RetryCallState) -> None:
    """Called before sleeping between retries: says a retry is coming, at DEBUG.

    The message names the outcome, a retry, and not a failure, because a retry is not always one: a
    poller retries on a result, while the job it polls is still queued or running. The attempt just made
    and the wait before the next one ride as fields, and `error.type`, the class of what the attempt
    raised, only when it raised.
    """
    if not retry_state.outcome:
        log.error("A retry state carries no outcome")
        return
    exc = retry_state.outcome.exception()
    wait_seconds = retry_state.next_action.sleep if retry_state.next_action else 0.0
    fields: dict[str, Any] = {
        "attempt_number": retry_state.attempt_number,
        "wait_seconds": wait_seconds,
    }
    if exc is not None:
        fields[ERROR_TYPE_FIELD] = type(exc).__name__
    log.debug("Retrying", fields=fields)
