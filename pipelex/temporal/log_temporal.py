import logging
from typing import Any, Union

from temporalio import activity, workflow

from pipelex import log
from pipelex.config import get_config
from pipelex.temporal.log_formatter import DeepFlowTemporalLogFormatter
from pipelex.tools.log.log_levels import LOGGING_LEVEL_DEV, LOGGING_LEVEL_VERBOSE


def configure_temporal_logs():
    """Configure Temporal logging settings based on the application configuration.

    This function sets up the log formatter, safety callable, and various logging options
    for both workflow and activity loggers.
    """
    temporal_log_config = get_config().deep_flow.temporal_config.temporal_log_config
    log.set_poor_log_formatter(DeepFlowTemporalLogFormatter())

    workflow.logger.workflow_info_on_message = temporal_log_config.is_workflow_info_on_message
    workflow.logger.workflow_info_on_extra = temporal_log_config.is_workflow_info_on_extra
    workflow.logger.full_workflow_info_on_extra = temporal_log_config.is_full_workflow_info_on_extra

    activity.logger.activity_info_on_message = temporal_log_config.is_activity_info_on_message
    activity.logger.activity_info_on_extra = temporal_log_config.is_activity_info_on_extra
    activity.logger.full_activity_info_on_extra = temporal_log_config.is_full_activity_info_on_extra


class WorkflowLog:
    """A class for logging messages in Temporal workflows with different severity levels."""

    def verbose(self, content: Union[str, Any]):
        """Log a verbose-level message in a workflow."""
        severity = LOGGING_LEVEL_VERBOSE
        workflow.logger.log(level=severity, msg=content)

    def debug(self, content: Union[str, Any]):
        """Log a debug-level message in a workflow."""
        severity = logging.DEBUG
        workflow.logger.log(level=severity, msg=content)

    def dev(self, content: Union[str, Any]):
        """Log a development-level message in a workflow."""
        severity = LOGGING_LEVEL_DEV
        workflow.logger.log(level=severity, msg=content)

    def info(self, content: Union[str, Any]):
        """Log an info-level message in a workflow."""
        severity = logging.INFO
        workflow.logger.log(level=severity, msg=content)

    def warning(self, content: Union[str, Any]):
        """Log a warning-level message in a workflow."""
        severity = logging.WARNING
        workflow.logger.log(level=severity, msg=content)

    def error(self, content: Union[str, Any]):
        """Log an error-level message in a workflow."""
        severity = logging.ERROR
        workflow.logger.log(level=severity, msg=content)

    def critical(self, content: Union[str, Any]):
        """Log a critical-level message in a workflow."""
        severity = logging.CRITICAL
        workflow.logger.log(level=severity, msg=content)


class ActivityLog:
    """A class for logging messages in Temporal activities with different severity levels."""

    def verbose(self, content: Union[str, Any]):
        """Log a verbose-level message in an activity."""
        severity = LOGGING_LEVEL_VERBOSE
        activity.logger.log(level=severity, msg=content)

    def debug(self, content: Union[str, Any]):
        """Log a debug-level message in an activity."""
        severity = logging.DEBUG
        activity.logger.log(level=severity, msg=content)

    def dev(self, content: Union[str, Any]):
        """Log a development-level message in an activity."""
        severity = LOGGING_LEVEL_DEV
        activity.logger.log(level=severity, msg=content)

    def info(self, content: Union[str, Any]):
        """Log an info-level message in an activity."""
        severity = logging.INFO
        activity.logger.log(level=severity, msg=content)

    def warning(self, content: Union[str, Any]):
        """Log a warning-level message in an activity."""
        severity = logging.WARNING
        activity.logger.log(level=severity, msg=content)

    def error(self, content: Union[str, Any]):
        """Log an error-level message in an activity."""
        severity = logging.ERROR
        activity.logger.log(level=severity, msg=content)

    def critical(self, content: Union[str, Any]):
        """Log a critical-level message in an activity."""
        severity = logging.CRITICAL
        activity.logger.log(level=severity, msg=content)


workflow_log = WorkflowLog()
activity_log = ActivityLog()
