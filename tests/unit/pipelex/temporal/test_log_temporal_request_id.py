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

_LOG_CASES = [
    pytest.param(WorkflowLog, workflow.logger, id="workflow"),
    pytest.param(ActivityLog, activity.logger, id="activity"),
]


class TestLogTemporalRequestId:
    @pytest.mark.parametrize(("log_class", "temporal_logger"), _LOG_CASES)
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
        request_id: str | None,
        expected_extra: dict[str, str] | None,
    ) -> None:
        """A bound request_id rides in every record's ``extra``; an unbound helper emits none."""
        mock_log = mocker.patch.object(temporal_logger, "log")
        log_class(request_id=request_id).info("hello")
        mock_log.assert_called_once_with(level=logging.INFO, msg="hello", extra=expected_extra)
