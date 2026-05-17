"""Unit tests for the Temporal error bridge (``TemporalError``).

Covers the category-aware retry decision and the ``ErrorReport`` details
payload that survives the activity → workflow boundary:

- ``from_message_exception`` derives ``non_retryable`` from
  ``InferenceErrorCategory.is_retryable`` for a ``CogtError`` carrying a category
  — including one wrapped under non-``CogtError`` exceptions — and falls back to
  the class-name list otherwise.
- ``to_error_report().to_dict()`` is packed into ``ApplicationError.details``
  and round-trips through Temporal's failure serialization intact.
- Log severity (critical / error) matches the retry decision on both the
  ``from_message_exception`` and ``from_app_error`` paths.
"""

from typing import Any

import pytest
from pytest_mock import MockerFixture
from temporalio.api.failure.v1 import Failure
from temporalio.converter import default as default_converter
from temporalio.exceptions import ApplicationError

from pipelex.base_exceptions import PipelexError
from pipelex.cogt.exceptions import CogtError, InferenceErrorCategory
from pipelex.cogt.inference.error_classification import UserAction, UserActionKind
from pipelex.temporal.tprl.temporal_error import TemporalError


class ModelNotFoundError(PipelexError):
    """Non-``CogtError`` ``PipelexError`` whose name is in the default non-retryable list."""


class UnlistedRuntimeError(PipelexError):
    """Non-``CogtError`` ``PipelexError`` whose name is absent from the non-retryable list."""


class PipeWrapperError(PipelexError):
    """Non-``CogtError`` ``PipelexError`` wrapper — stands in for the real pipe-execution
    wrappers (``PipeRunError`` / ``PipeRouterError`` / ``PipelineExecutionError``), none of
    which are ``CogtError`` subclasses, so a retry decision cannot read a category off them.
    """


def _round_trip_application_error(exc: ApplicationError) -> ApplicationError:
    """Serialize an ``ApplicationError`` to a Temporal ``Failure`` and back.

    Mirrors what Temporal does when an activity raises across the
    activity → workflow boundary, so the test exercises real payload conversion
    rather than an in-process shortcut.
    """
    converter = default_converter()
    failure = Failure()
    converter.failure_converter.to_failure(exc, converter.payload_converter, failure)
    recovered = converter.failure_converter.from_failure(failure, converter.payload_converter)
    assert isinstance(recovered, ApplicationError)
    return recovered


def _chain(outermost: PipelexError, *causes: BaseException) -> PipelexError:
    """Link exceptions into a ``__cause__`` chain, outermost first, and return ``outermost``.

    ``_chain(a, b, c)`` sets ``a.__cause__ = b`` and ``b.__cause__ = c`` — the chain that
    ``raise a from b`` / ``raise b from c`` would build inside nested ``except`` blocks.
    """
    current: BaseException = outermost
    for cause in causes:
        current.__cause__ = cause
        current = cause
    return outermost


class TestTemporalErrorBridge:
    @pytest.fixture
    def log_mocks(self, mocker: MockerFixture) -> tuple[Any, Any]:
        """Replace the whole ``_log_critical`` / ``_log_error`` helpers — they
        require a live Temporal context.

        Not ``autouse``: ``test_log_helpers_route_to_the_active_temporal_context``
        needs the real helpers. Every other test must opt in, since
        ``from_message_exception`` / ``from_app_error`` log unconditionally.

        Returns the ``(critical, error)`` mocks so a test can assert which
        severity the retry decision routed the log line to.
        """
        critical_mock = mocker.patch.object(TemporalError, "_log_critical")
        error_mock = mocker.patch.object(TemporalError, "_log_error")
        return critical_mock, error_mock

    @pytest.mark.parametrize(
        ("error_category", "expected_non_retryable"),
        [
            pytest.param(InferenceErrorCategory.TRANSIENT, False, id="transient-retryable"),
            pytest.param(InferenceErrorCategory.CONFIGURATION, True, id="configuration-non-retryable"),
            pytest.param(InferenceErrorCategory.CONTENT, True, id="content-non-retryable"),
            pytest.param(InferenceErrorCategory.CAPACITY, True, id="capacity-non-retryable"),
            pytest.param(InferenceErrorCategory.AMBIGUOUS, True, id="ambiguous-non-retryable"),
            pytest.param(InferenceErrorCategory.UNKNOWN, True, id="unknown-non-retryable"),
        ],
    )
    def test_cogt_error_category_drives_retryability(
        self,
        log_mocks: tuple[Any, Any],
        error_category: InferenceErrorCategory,
        expected_non_retryable: bool,
    ) -> None:
        """A ``CogtError`` with a category sets ``non_retryable = not is_retryable``."""
        critical_mock, error_mock = log_mocks

        exc = CogtError("boom", error_category=error_category)
        temporal_error = TemporalError.from_message_exception(exc=exc)

        assert temporal_error.non_retryable is expected_non_retryable
        assert temporal_error.error_report is not None
        assert temporal_error.error_report["error_category"] == error_category
        assert temporal_error.error_report["retryable"] is (not expected_non_retryable)

        if expected_non_retryable:
            assert critical_mock.call_count == 1
            assert error_mock.call_count == 0
        else:
            assert error_mock.call_count == 1
            assert critical_mock.call_count == 0

    @pytest.mark.parametrize(
        ("exc", "expected_non_retryable"),
        [
            pytest.param(ModelNotFoundError("missing model"), True, id="listed-name-non-retryable"),
            pytest.param(UnlistedRuntimeError("hiccup"), False, id="unlisted-name-retryable"),
        ],
    )
    def test_non_cogt_pipelex_error_uses_name_list_fallback(
        self,
        log_mocks: tuple[Any, Any],
        exc: PipelexError,
        expected_non_retryable: bool,
    ) -> None:
        """A non-``CogtError`` ``PipelexError`` decides retryability by class name."""
        _ = log_mocks  # silences the bridge log helpers; severity is asserted elsewhere
        temporal_error = TemporalError.from_message_exception(exc=exc)

        assert temporal_error.non_retryable is expected_non_retryable
        assert temporal_error.error_report is not None
        assert temporal_error.error_report["error_type"] == type(exc).__name__

    def test_cogt_error_without_category_falls_back_to_name_list(self, log_mocks: tuple[Any, Any]) -> None:
        """A ``CogtError`` raised without a category falls back to the name list — no crash."""
        _ = log_mocks  # silences the bridge log helpers; severity is asserted elsewhere
        exc = CogtError("boom")
        assert exc.error_category is None

        temporal_error = TemporalError.from_message_exception(exc=exc)

        # "CogtError" is not in the default non-retryable list → retryable.
        assert temporal_error.non_retryable is False
        assert temporal_error.error_report is not None
        assert temporal_error.error_report["error_type"] == "CogtError"

    @pytest.mark.parametrize(
        ("error_category", "expected_non_retryable"),
        [
            pytest.param(InferenceErrorCategory.TRANSIENT, False, id="transient-retryable"),
            pytest.param(InferenceErrorCategory.CONFIGURATION, True, id="configuration-non-retryable"),
            pytest.param(InferenceErrorCategory.CONTENT, True, id="content-non-retryable"),
            pytest.param(InferenceErrorCategory.CAPACITY, True, id="capacity-non-retryable"),
            pytest.param(InferenceErrorCategory.AMBIGUOUS, True, id="ambiguous-non-retryable"),
            pytest.param(InferenceErrorCategory.UNKNOWN, True, id="unknown-non-retryable"),
        ],
    )
    def test_wrapped_cogt_error_category_drives_retryability(
        self,
        log_mocks: tuple[Any, Any],
        error_category: InferenceErrorCategory,
        expected_non_retryable: bool,
    ) -> None:
        """A categorized ``CogtError`` buried under non-``CogtError`` wrappers still drives
        the retry decision — the bridge walks the ``__cause__`` chain, not just the outer
        exception.

        Mirrors the production chain ``PipelineExecutionError`` -> ``PipeRouterError`` ->
        ``PipeRunError`` -> ``CogtError``: the outer exception is not a ``CogtError``, so a
        decision based on the outer type alone would wrongly fall back to the name list and
        leave a non-retryable inference failure (content, configuration, capacity) retryable.
        """
        _ = log_mocks  # silences the bridge log helpers; severity is asserted elsewhere

        wrapped = _chain(
            PipeWrapperError("pipeline run failed"),
            PipeWrapperError("pipe failed"),
            CogtError("inference boom", error_category=error_category),
        )

        temporal_error = TemporalError.from_message_exception(exc=wrapped)

        assert temporal_error.non_retryable is expected_non_retryable
        assert temporal_error.error_report is not None
        # The outer wrapper keeps its own error_type; the category is recovered from the cause.
        assert temporal_error.error_report["error_type"] == "PipeWrapperError"
        assert temporal_error.error_report["error_category"] == error_category
        # non_retryable must agree with the chain-enriched `retryable` shipped alongside it.
        assert temporal_error.error_report["retryable"] is (not expected_non_retryable)

    def test_error_report_round_trips_through_temporal_serialization(
        self,
        log_mocks: tuple[Any, Any],
    ) -> None:
        """The ``ErrorReport`` details payload survives the activity → workflow boundary."""
        critical_mock, error_mock = log_mocks

        exc = CogtError(
            "rate limited",
            error_category=InferenceErrorCategory.CAPACITY,
            user_action=UserAction(kind=UserActionKind.CHECK_BILLING, detail="check your billing page"),
        )
        activity_side = TemporalError.from_message_exception(exc=exc)

        serialized: ApplicationError = _round_trip_application_error(exc=activity_side)
        workflow_side = TemporalError.from_app_error(exc=serialized)

        assert workflow_side.non_retryable is True
        report: dict[str, Any] | None = workflow_side.error_report
        assert report is not None
        assert report["error_type"] == "CogtError"
        assert report["message"] == "rate limited"
        assert report["error_category"] == InferenceErrorCategory.CAPACITY
        assert report["retryable"] is False
        assert report["user_action"]["kind"] == UserActionKind.CHECK_BILLING
        assert report["user_action"]["detail"] == "check your billing page"

        # CAPACITY is non-retryable → both bridge hops log at critical severity.
        assert critical_mock.call_count == 2
        assert error_mock.call_count == 0

    @pytest.mark.parametrize(
        "in_activity",
        [
            pytest.param(True, id="in-activity-uses-activity-log"),
            pytest.param(False, id="not-in-activity-uses-workflow-log"),
        ],
    )
    def test_log_helpers_route_to_the_active_temporal_context(
        self,
        mocker: MockerFixture,
        in_activity: bool,
    ) -> None:
        """``_log_critical`` / ``_log_error`` route through ``activity_log`` inside an
        activity and ``workflow_log`` otherwise.

        ``from_message_exception`` runs activity-side and ``from_app_error``
        workflow-side; ``workflow.logger`` raises ``_NotInWorkflowEventLoopError``
        outside a workflow event loop, so the logger must follow the context.
        """
        mocker.patch("pipelex.temporal.tprl.temporal_error.activity.in_activity", return_value=in_activity)
        activity_log_mock = mocker.patch("pipelex.temporal.tprl.temporal_error.activity_log")
        workflow_log_mock = mocker.patch("pipelex.temporal.tprl.temporal_error.workflow_log")

        TemporalError._log_critical("non-retryable message")  # noqa: SLF001 # pyright: ignore[reportPrivateUsage]
        TemporalError._log_error("retryable message")  # noqa: SLF001 # pyright: ignore[reportPrivateUsage]

        if in_activity:
            activity_log_mock.critical.assert_called_once_with("non-retryable message")
            activity_log_mock.error.assert_called_once_with("retryable message")
            workflow_log_mock.critical.assert_not_called()
            workflow_log_mock.error.assert_not_called()
        else:
            workflow_log_mock.critical.assert_called_once_with("non-retryable message")
            workflow_log_mock.error.assert_called_once_with("retryable message")
            activity_log_mock.critical.assert_not_called()
            activity_log_mock.error.assert_not_called()
