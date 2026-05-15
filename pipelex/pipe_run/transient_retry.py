from pydantic import BaseModel


class TransientRetrySettings(BaseModel):
    """Bounded-retry policy for transient inference failures, resolved from `PipelineExecutionConfig`.

    This lives in its own dependency-free module on purpose: `PipeRouterProtocol` references it, and
    `hub.py` type-imports `PipeRouterProtocol`. Importing `pipelex.config` (or any module that reaches
    `hub`) from the protocol would form an import cycle, so the protocol carries this plain model and
    each concrete router fills it in from config at construction time.
    """

    max_transient_retries: int
    base_wait: float
    max_wait: float
    backoff_multiplier: float

    def compute_wait(self, retry_count: int) -> float:
        """Exponential-backoff wait, in seconds, before retry number `retry_count` (1-indexed)."""
        raw_wait = self.base_wait * self.backoff_multiplier ** (retry_count - 1)
        return min(raw_wait, self.max_wait)
