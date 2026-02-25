from tenacity import RetryCallState

from pipelex import log


def log_retry(retry_state: RetryCallState) -> None:
    """Called before sleeping between retries."""
    if not retry_state.outcome:
        log.error("Tenacity retry state outcome is None")
        return
    exc = retry_state.outcome.exception()
    attempt = retry_state.attempt_number
    wait_duration = retry_state.next_action.sleep if retry_state.next_action else 0.0
    log.verbose(f"Tenacity retry #{attempt} due to '{type(exc).__name__}'.")
    log.verbose(f"Wait duration before next attempt: {wait_duration:.4f}s")
