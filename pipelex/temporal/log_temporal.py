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


class _RequestIdLog:
    """Base for the Temporal log helpers — carries the per-invocation ``request_id``.

    A :class:`WorkflowLog` / :class:`ActivityLog` is built once per workflow or
    activity invocation, bound to that invocation's ``job_metadata.request_id``
    (``None`` when the run carries no inbound API request id). Every log call it
    makes attaches ``request_id`` to the Temporal log record via
    ``extra={"request_id": ...}``, so downstream log shippers can correlate the
    record back to the originating API request — the call site never threads the
    id itself.
    """

    def __init__(self, request_id: str | None = None) -> None:
        self._request_id = request_id

    def _build_extra(self) -> dict[str, str] | None:
        """Pack the bound ``request_id`` into the logger ``extra`` dict, omitting when absent.

        The Temporal logger merges ``extra`` into each log record so downstream
        formatters (and JSON-shipping consumers) can read ``record.request_id``.
        """
        if self._request_id is None:
            return None
        return {"request_id": self._request_id}


class WorkflowLog(_RequestIdLog):
    """Logs messages in Temporal workflows at different severity levels.

    Build one per ``@workflow.run`` invocation, bound to that run's
    ``job_metadata.request_id`` — every record it emits then carries that
    ``request_id`` (see :class:`_RequestIdLog`). The module-level
    :data:`workflow_log` singleton is unbound (``request_id is None``); it is
    used by call sites that have no ``job_metadata`` in scope.
    """

    def verbose(self, content: Union[str, Any]) -> None:
        """Log a verbose-level message in a workflow."""
        workflow.logger.log(level=LOGGING_LEVEL_VERBOSE, msg=content, extra=self._build_extra())

    def debug(self, content: Union[str, Any]) -> None:
        """Log a debug-level message in a workflow."""
        workflow.logger.log(level=logging.DEBUG, msg=content, extra=self._build_extra())

    def dev(self, content: Union[str, Any]) -> None:
        """Log a development-level message in a workflow."""
        workflow.logger.log(level=LOGGING_LEVEL_DEV, msg=content, extra=self._build_extra())

    def info(self, content: Union[str, Any]) -> None:
        """Log an info-level message in a workflow."""
        workflow.logger.log(level=logging.INFO, msg=content, extra=self._build_extra())

    def warning(self, content: Union[str, Any]) -> None:
        """Log a warning-level message in a workflow."""
        workflow.logger.log(level=logging.WARNING, msg=content, extra=self._build_extra())

    def error(self, content: Union[str, Any]) -> None:
        """Log an error-level message in a workflow."""
        workflow.logger.log(level=logging.ERROR, msg=content, extra=self._build_extra())

    def critical(self, content: Union[str, Any]) -> None:
        """Log a critical-level message in a workflow."""
        workflow.logger.log(level=logging.CRITICAL, msg=content, extra=self._build_extra())


class ActivityLog(_RequestIdLog):
    """Logs messages in Temporal activities at different severity levels.

    Build one per activity invocation, bound to that activity's
    ``job_metadata.request_id`` — every record it emits then carries that
    ``request_id`` (see :class:`_RequestIdLog`). The module-level
    :data:`activity_log` singleton is unbound (``request_id is None``); it is
    used by call sites that have no ``job_metadata`` in scope.
    """

    def verbose(self, content: Union[str, Any]) -> None:
        """Log a verbose-level message in an activity."""
        activity.logger.log(level=LOGGING_LEVEL_VERBOSE, msg=content, extra=self._build_extra())

    def debug(self, content: Union[str, Any]) -> None:
        """Log a debug-level message in an activity."""
        activity.logger.log(level=logging.DEBUG, msg=content, extra=self._build_extra())

    def dev(self, content: Union[str, Any]) -> None:
        """Log a development-level message in an activity."""
        activity.logger.log(level=LOGGING_LEVEL_DEV, msg=content, extra=self._build_extra())

    def info(self, content: Union[str, Any]) -> None:
        """Log an info-level message in an activity."""
        activity.logger.log(level=logging.INFO, msg=content, extra=self._build_extra())

    def warning(self, content: Union[str, Any]) -> None:
        """Log a warning-level message in an activity."""
        activity.logger.log(level=logging.WARNING, msg=content, extra=self._build_extra())

    def error(self, content: Union[str, Any]) -> None:
        """Log an error-level message in an activity."""
        activity.logger.log(level=logging.ERROR, msg=content, extra=self._build_extra())

    def critical(self, content: Union[str, Any]) -> None:
        """Log a critical-level message in an activity."""
        activity.logger.log(level=logging.CRITICAL, msg=content, extra=self._build_extra())


# Unbound singletons for call sites with no ``job_metadata`` in scope (e.g. the
# ``TemporalError`` severity logs). Entry points that do have ``job_metadata``
# build their own bound instance instead — see ``WfPipeRun`` / ``WfPipeRouter``.
workflow_log = WorkflowLog()
activity_log = ActivityLog()
