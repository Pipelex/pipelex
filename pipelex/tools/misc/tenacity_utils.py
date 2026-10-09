from tenacity import RetryCallState

from pipelex import log


def log_retry(retry_state: RetryCallState) -> None:
    """Called before sleeping between retries: says a retry is coming, at DEBUG.

    The attempt that failed, the class of the exception it raised and the wait before the next one ride
    as fields. `exception_type` is `None` when the retry is on a result rather than on an exception, as
    when a poller retries while the job it polls is still running.
    """
    if not retry_state.outcome:
        log.error("Tenacity retry state outcome is None")
        return
    exc = retry_state.outcome.exception()
    wait_seconds = retry_state.next_action.sleep if retry_state.next_action else 0.0
    log.debug(
        "Retrying after a failed attempt",
        fields={
            "attempt_number": retry_state.attempt_number,
            "exception_type": type(exc).__name__ if exc is not None else None,
            "wait_seconds": wait_seconds,
        },
    )
