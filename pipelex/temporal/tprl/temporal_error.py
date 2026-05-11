from temporalio.exceptions import ApplicationError

from pipelex.base_exceptions import PipelexError
from pipelex.config import get_config
from pipelex.temporal.log_temporal import workflow_log
from pipelex.types import Self


class TemporalError(ApplicationError):
    def __init__(self, message: str, error_type: str | None):
        super().__init__(
            message=message,
            type=error_type,
        )

    @classmethod
    def from_app_error(cls, exc: ApplicationError) -> Self:
        message = exc.message
        error_type = exc.type
        temporal_config = get_config().temporal
        all_non_retryable = temporal_config.worker_config.all_non_retryable_error_types(
            queue_options_by_queue=temporal_config.queue_options,
        )
        if error_type in all_non_retryable:
            workflow_log.critical(f"Non retryable error from ApplicationError[{error_type}]: {message}")
        else:
            workflow_log.error(f"Error from ApplicationError[{error_type}]: {message}")
        return cls(
            message=message,
            error_type=error_type,
        )

    @classmethod
    def from_message_exception(cls, exc: PipelexError) -> Self:
        message = exc.message
        error_type = exc.__class__.__name__
        temporal_config = get_config().temporal
        all_non_retryable = temporal_config.worker_config.all_non_retryable_error_types(
            queue_options_by_queue=temporal_config.queue_options,
        )
        if error_type in all_non_retryable:
            workflow_log.critical(f"Non retryable error from PipelexError[{error_type}]: {message}")
        else:
            workflow_log.error(f"Retryable error from PipelexError[{error_type}]: {message}")
        return cls(
            message=message,
            error_type=error_type,
        )
