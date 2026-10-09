from tenacity import RetryCallState

from pipelex import log


def log_retry(retry_state: RetryCallState) -> None:
    """Called before sleeping between retries."""
    if not retry_state.outcome:
        log.error("Tenacity retry state outcome is None")
