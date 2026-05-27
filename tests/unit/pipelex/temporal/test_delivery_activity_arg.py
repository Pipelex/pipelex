"""Unit round-trip test for ``DeliveryActivityArg``.

Pins nested-model serialization through ``model_dump_json`` / ``model_validate_json``
so a regression in the nested ``ErrorReport`` round-trip is caught without standing
up a real Temporal worker.
"""

from pipelex.base_exceptions import ErrorDomain, ErrorReport
from pipelex.cogt.inference.error_classification import UserAction, UserActionKind
from pipelex.pipe_run.delivery_assignment import DeliveryAssignment, DeliveryStatus, WebhookTarget
from pipelex.temporal.tprl_pipe.act_deliver import DeliveryActivityArg


class TestDeliveryActivityArg:
    def test_json_roundtrip_with_populated_error_report(self) -> None:
        """A ``DeliveryActivityArg`` carrying a fully populated nested ``ErrorReport``
        (including a nested ``UserAction``) round-trips through JSON serialization.
        """
        error_report = ErrorReport(
            error_type="CogtError",
            message="rate limited on the worker",
            title="AI inference failed",
            type_uri="https://docs.pipelex.com/latest/errors/cogt-error/",
            error_category="capacity",
            error_domain=ErrorDomain.RUNTIME,
            retryable=False,
            user_action=UserAction(kind=UserActionKind.CHECK_BILLING, detail="check your billing page"),
            model="gpt-5",
            provider="openai",
        )
        arg = DeliveryActivityArg(
            user_id="user-123",
            pipeline_run_id="plr-456",
            delivery_assignment=DeliveryAssignment(webhooks=[WebhookTarget(url="https://example.com/callback")]),
            status=DeliveryStatus.FAILED,
            error_report=error_report,
            request_id="req-abc",
        )

        restored = DeliveryActivityArg.model_validate_json(arg.model_dump_json())

        assert restored == arg
        assert restored.error_report == error_report
        assert restored.error_report is not None
        assert restored.error_report.user_action == error_report.user_action
        assert restored.request_id == "req-abc"

    def test_request_id_defaults_to_none(self) -> None:
        """A run dispatched without an inbound API request id (e.g. cron, internal job) carries ``request_id=None``."""
        arg = DeliveryActivityArg(
            user_id="user-123",
            pipeline_run_id="plr-no-req",
            delivery_assignment=DeliveryAssignment(),
            status=DeliveryStatus.COMPLETED,
        )

        assert arg.request_id is None
        restored = DeliveryActivityArg.model_validate_json(arg.model_dump_json())
        assert restored.request_id is None
