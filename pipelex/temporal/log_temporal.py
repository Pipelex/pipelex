import logging
from typing import Any, Union

from temporalio import activity, workflow

from pipelex import log
from pipelex.config import get_config
from pipelex.temporal.log_formatter import TemporalLogFormatter
from pipelex.tools.log.log_levels import LOGGING_LEVEL_DEV, LOGGING_LEVEL_VERBOSE


def configure_temporal_logs():
    """Configure Temporal logging settings based on the application configuration.

    This function sets up the log formatter, safety callable, and various logging options
    for both workflow and activity loggers.
    """
    temporal_log_config = get_config().temporal.temporal_config.temporal_log_config
    log.set_poor_log_formatter(TemporalLogFormatter())

    workflow.logger.workflow_info_on_message = temporal_log_config.is_workflow_info_on_message
    workflow.logger.workflow_info_on_extra = temporal_log_config.is_workflow_info_on_extra
    workflow.logger.full_workflow_info_on_extra = temporal_log_config.is_full_workflow_info_on_extra

    activity.logger.activity_info_on_message = temporal_log_config.is_activity_info_on_message
    activity.logger.activity_info_on_extra = temporal_log_config.is_activity_info_on_extra
    activity.logger.full_activity_info_on_extra = temporal_log_config.is_full_activity_info_on_extra


def _build_extra(request_id: str | None) -> dict[str, str] | None:
    """Pack ``request_id`` into the logger ``extra`` dict, omitting when absent.

    The Temporal logger merges ``extra`` into each log record so downstream
    formatters (and JSON-shipping consumers) can read ``record.request_id``.
    """
    if request_id is None:
        return None
    return {"request_id": request_id}


class WorkflowLog:
    """A class for logging messages in Temporal workflows with different severity levels.

    All methods accept an optional ``request_id`` kwarg — when provided, it is
    forwarded to the Temporal workflow logger via ``extra={"request_id": ...}``
    so downstream log shippers can correlate the record back to the inbound
    API request. The kwarg is accepted but not yet threaded by any caller: no
    workflow reads ``job_metadata.request_id`` and passes it in. Wiring that
    end to end is tracked as Phase 2 of the API-readiness follow-ups in the
    repo-root ``TODOS.md``.
    """

    def verbose(self, content: Union[str, Any], request_id: str | None = None) -> None:
        """Log a verbose-level message in a workflow."""
        workflow.logger.log(level=LOGGING_LEVEL_VERBOSE, msg=content, extra=_build_extra(request_id))

    def debug(self, content: Union[str, Any], request_id: str | None = None) -> None:
        """Log a debug-level message in a workflow."""
        workflow.logger.log(level=logging.DEBUG, msg=content, extra=_build_extra(request_id))

    def dev(self, content: Union[str, Any], request_id: str | None = None) -> None:
        """Log a development-level message in a workflow."""
        workflow.logger.log(level=LOGGING_LEVEL_DEV, msg=content, extra=_build_extra(request_id))

    def info(self, content: Union[str, Any], request_id: str | None = None) -> None:
        """Log an info-level message in a workflow."""
        workflow.logger.log(level=logging.INFO, msg=content, extra=_build_extra(request_id))

    def warning(self, content: Union[str, Any], request_id: str | None = None) -> None:
        """Log a warning-level message in a workflow."""
        workflow.logger.log(level=logging.WARNING, msg=content, extra=_build_extra(request_id))

    def error(self, content: Union[str, Any], request_id: str | None = None) -> None:
        """Log an error-level message in a workflow."""
        workflow.logger.log(level=logging.ERROR, msg=content, extra=_build_extra(request_id))

    def critical(self, content: Union[str, Any], request_id: str | None = None) -> None:
        """Log a critical-level message in a workflow."""
        workflow.logger.log(level=logging.CRITICAL, msg=content, extra=_build_extra(request_id))


class ActivityLog:
    """A class for logging messages in Temporal activities with different severity levels.

    All methods accept an optional ``request_id`` kwarg — when provided, it is
    forwarded to the Temporal activity logger via ``extra={"request_id": ...}``
    so downstream log shippers can correlate the record back to the inbound
    API request. The kwarg is accepted but not yet threaded by any caller: no
    activity reads ``job_metadata.request_id`` and passes it in. Wiring that
    end to end is tracked as Phase 2 of the API-readiness follow-ups in the
    repo-root ``TODOS.md``.
    """

    def verbose(self, content: Union[str, Any], request_id: str | None = None) -> None:
        """Log a verbose-level message in an activity."""
        activity.logger.log(level=LOGGING_LEVEL_VERBOSE, msg=content, extra=_build_extra(request_id))

    def debug(self, content: Union[str, Any], request_id: str | None = None) -> None:
        """Log a debug-level message in an activity."""
        activity.logger.log(level=logging.DEBUG, msg=content, extra=_build_extra(request_id))

    def dev(self, content: Union[str, Any], request_id: str | None = None) -> None:
        """Log a development-level message in an activity."""
        activity.logger.log(level=LOGGING_LEVEL_DEV, msg=content, extra=_build_extra(request_id))

    def info(self, content: Union[str, Any], request_id: str | None = None) -> None:
        """Log an info-level message in an activity."""
        activity.logger.log(level=logging.INFO, msg=content, extra=_build_extra(request_id))

    def warning(self, content: Union[str, Any], request_id: str | None = None) -> None:
        """Log a warning-level message in an activity."""
        activity.logger.log(level=logging.WARNING, msg=content, extra=_build_extra(request_id))

    def error(self, content: Union[str, Any], request_id: str | None = None) -> None:
        """Log an error-level message in an activity."""
        activity.logger.log(level=logging.ERROR, msg=content, extra=_build_extra(request_id))

    def critical(self, content: Union[str, Any], request_id: str | None = None) -> None:
        """Log a critical-level message in an activity."""
        activity.logger.log(level=logging.CRITICAL, msg=content, extra=_build_extra(request_id))


workflow_log = WorkflowLog()
activity_log = ActivityLog()
