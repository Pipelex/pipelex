"""Unit coverage for the bound ``request_id`` on the Temporal log helpers.

``WorkflowLog`` / ``ActivityLog`` are built once per workflow / activity
invocation, bound to that invocation's ``job_metadata.request_id``. The bound
id is packed into every log record's ``extra`` dict so downstream shippers read
``record.request_id``; an unbound helper emits no ``extra``.
"""

import logging
from typing import Any

import pytest
from pytest_mock import MockerFixture
from temporalio import activity, workflow

from pipelex.temporal.log_temporal import ActivityLog, WorkflowLog
from pipelex.tools.log.log_levels import LOGGING_LEVEL_DEV, LOGGING_LEVEL_VERBOSE

_LOG_CASES = [
    pytest.param(WorkflowLog, workflow.logger, id="workflow"),
    pytest.param(ActivityLog, activity.logger, id="activity"),
]

# Every severity method paired with the log level it must emit at.
_METHOD_CASES = [
    pytest.param("verbose", LOGGING_LEVEL_VERBOSE, id="verbose"),
    pytest.param("debug", logging.DEBUG, id="debug"),
    pytest.param("dev", LOGGING_LEVEL_DEV, id="dev"),
    pytest.param("info", logging.INFO, id="info"),
    pytest.param("warning", logging.WARNING, id="warning"),
    pytest.param("error", logging.ERROR, id="error"),
    pytest.param("critical", logging.CRITICAL, id="critical"),
]


class TestLogTemporalRequestId:
    @pytest.mark.parametrize(("log_class", "temporal_logger"), _LOG_CASES)
    @pytest.mark.parametrize(("method_name", "expected_level"), _METHOD_CASES)
    @pytest.mark.parametrize(
        ("request_id", "expected_extra"),
        [
            pytest.param("r-abc-123", {"request_id": "r-abc-123"}, id="bound"),
            pytest.param(None, None, id="unbound"),
        ],
    )
    def test_request_id_binding_controls_log_extra(
        self,
        mocker: MockerFixture,
        log_class: type[WorkflowLog | ActivityLog],
        temporal_logger: Any,
        method_name: str,
        expected_level: int,
        request_id: str | None,
        expected_extra: dict[str, str] | None,
    ) -> None:
        """Every severity method packs the bound request_id into ``extra`` at its own level; an unbound helper emits none."""
        mock_log = mocker.patch.object(temporal_logger, "log")
        log_method = getattr(log_class(request_id=request_id), method_name)
        log_method("hello")
        mock_log.assert_called_once_with(level=expected_level, msg="hello", extra=expected_extra)
