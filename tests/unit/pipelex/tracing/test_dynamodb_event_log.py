import json
import time
from datetime import UTC, datetime
from typing import Any

import pytest
from botocore.exceptions import BotoCoreError, ClientError, EndpointConnectionError
from pydantic import ValidationError
from pytest_mock import MockerFixture

from pipelex.graph.graphspec import NodeKind
from pipelex.system.configuration.configs import DynamoDBTracingConfig, TracingConfig
from pipelex.system.pipe_run_mode import PipeRunMode
from pipelex.tracing.buffering_event_log import BufferingEventLog
from pipelex.tracing.dynamodb_event_log import DynamoDBEventLog
from pipelex.tracing.event_log_factory import make_event_log
from pipelex.tracing.event_log_protocol import EventLogProtocol
from pipelex.tracing.exceptions import EventLogReadError, EventLogSchemaMismatchError, EventLogSetupError
from pipelex.tracing.trace_events import BatchFannedOutEvent, ConditionResolvedEvent, PipeStartEvent, TraceEvent
from tests.unit.pipelex.tracing.conftest import make_trace_event

_SECONDS_PER_DAY = 86_400
_RUN_ID = "plr-decisions"
_T0 = datetime(2026, 10, 13, 9, 0, 0, tzinfo=UTC)


def _decision_events(*, mode: PipeRunMode) -> list[TraceEvent]:
    base: dict[str, Any] = {"pipeline_run_id": _RUN_ID, "workflow_id": "wf_flow", "timestamp": _T0, "mode": mode}
    return [
        PipeStartEvent(
            **base,
            sequence=0,
            node_id="g:wf_flow:node_0",
            pipe_code="flow",
            pipe_type="PipeSequence",
            node_kind=NodeKind.CONTROLLER,
            step_count=3,
        ),
        ConditionResolvedEvent(**base, sequence=1, node_id="g:wf_flow:node_1", rendered_value="unmatched", selected_outcome=None),
        BatchFannedOutEvent(
            **base,
            sequence=2,
            node_id="g:wf_flow:node_2",
            item_count=5,
            branch_pipe_code="process",
            branch_pipe_ref="flows.process",
            branch_pipe_type="PipeCompose",
        ),
    ]


class TestDynamoDBEventLog:
    def _make_event_log_with_table(self, mocker: MockerFixture, *, retention_days: int = 30) -> tuple[DynamoDBEventLog, Any]:
        # boto3.resource(...) does not perform any network call at construction.
        event_log = DynamoDBEventLog(table_name="trace-events-test", region="us-east-1", retention_days=retention_days)
        mock_table = mocker.MagicMock()
        mocker.patch.object(event_log, "_table", new=mock_table)
        return event_log, mock_table

    @staticmethod
    def _emit_and_capture_ttl(event_log: EventLogProtocol, mock_table: Any) -> tuple[int, int, int]:
        """Emit one event and return the written item's ttl with the epoch seconds read just before and just after."""
        before = int(time.time())
        event_log.emit(make_trace_event())
        after = int(time.time())
        item: dict[str, Any] = mock_table.put_item.call_args.kwargs["Item"]
        ttl = item["ttl"]
        assert isinstance(ttl, int)
        return ttl, before, after

    @pytest.mark.parametrize("retention_days", [1, 30, 365])
    def test_emit_writes_ttl_retention_days_past_the_write(self, mocker: MockerFixture, retention_days: int) -> None:
        """Every item carries a `ttl` in epoch seconds, the attribute the events table expires items on."""
        event_log, mock_table = self._make_event_log_with_table(mocker, retention_days=retention_days)

        ttl, before, after = self._emit_and_capture_ttl(event_log, mock_table)

        retention_seconds = retention_days * _SECONDS_PER_DAY
        assert before + retention_seconds <= ttl <= after + retention_seconds

    def test_make_event_log_writes_the_configured_retention(self, mocker: MockerFixture) -> None:
        """The factory hands `runtime.tracing.dynamodb.retention_days` to the writer, so the setting decides the `ttl`."""
        tracing_config = TracingConfig.model_validate(
            {
                "is_enabled": True,
                "backend": "dynamodb",
                "dynamodb": {"table_name": "trace-events-test", "region": "us-east-1", "retention_days": 7},
            }
        )
        event_log = make_event_log(tracing_config)
        assert isinstance(event_log, DynamoDBEventLog)
        mock_table = mocker.MagicMock()
        mocker.patch.object(event_log, "_table", new=mock_table)

        ttl, before, after = self._emit_and_capture_ttl(event_log, mock_table)

        assert before + 7 * _SECONDS_PER_DAY <= ttl <= after + 7 * _SECONDS_PER_DAY

    @pytest.mark.parametrize("retention_days", [0, -1])
    def test_config_refuses_a_retention_under_one_day(self, retention_days: int) -> None:
        """A retention of zero or less would expire every event as it is written, so the configuration refuses it."""
        with pytest.raises(ValidationError):
            DynamoDBTracingConfig.model_validate({"table_name": "trace-events-test", "region": "us-east-1", "retention_days": retention_days})

    @pytest.mark.parametrize("retention_days", [0, -1])
    def test_init_refuses_a_retention_under_one_day(self, retention_days: int) -> None:
        """A direct construction bypasses the config's check, so the writer refuses such a retention itself."""
        with pytest.raises(EventLogSetupError, match="at least one day"):
            DynamoDBEventLog(table_name="trace-events-test", region="us-east-1", retention_days=retention_days)

    @pytest.mark.parametrize(
        "backend_error",
        [
            ClientError(
                error_response={"Error": {"Code": "ThrottlingException", "Message": "Rate exceeded"}},
                operation_name="Query",
            ),
            EndpointConnectionError(endpoint_url="https://dynamodb.us-east-1.amazonaws.com"),
        ],
    )
    def test_read_events_translates_backend_error(self, mocker: MockerFixture, backend_error: BotoCoreError) -> None:
        # A store-level botocore failure (throttling, network) must surface as the domain
        # EventLogReadError so best-effort callers can catch a single Pipelex error.
        event_log, mock_table = self._make_event_log_with_table(mocker)
        mock_table.query.side_effect = backend_error

        with pytest.raises(EventLogReadError) as exc_info:
            event_log.read_events("plr-throttled")

        assert exc_info.value.__cause__ is backend_error

    def test_read_events_translates_error_on_pagination_query(self, mocker: MockerFixture) -> None:
        # The translation must also cover the pagination loop, not just the first query.
        event_log, mock_table = self._make_event_log_with_table(mocker)
        first_page: dict[str, Any] = {"Items": [], "LastEvaluatedKey": {"PK": "x", "SK": "y"}}
        throttle = ClientError(
            error_response={"Error": {"Code": "ThrottlingException", "Message": "Rate exceeded"}},
            operation_name="Query",
        )
        mock_table.query.side_effect = [first_page, throttle]

        with pytest.raises(EventLogReadError):
            event_log.read_events("plr-paginated")

    def test_decision_events_survive_the_buffer_and_the_table(self, mocker: MockerFixture) -> None:
        """The Temporal path: a workflow buffers the events, an activity writes them to DynamoDB, a reader reads them back whole."""
        event_log, mock_table = self._make_event_log_with_table(mocker)
        buffer = BufferingEventLog()
        events = _decision_events(mode=PipeRunMode.DRY)
        for event in events:
            buffer.emit(event)
        for event in buffer.drain():
            event_log.emit(event)
        stored_items = [call.kwargs["Item"] for call in mock_table.put_item.call_args_list]
        assert all(isinstance(item["ttl"], int) for item in stored_items)
        mock_table.query.return_value = {"Items": stored_items}

        assert event_log.read_events(_RUN_ID) == events

    def test_an_event_stored_without_a_mode_is_refused(self, mocker: MockerFixture) -> None:
        """A payload written before every event stated its mode is in a shape this version refuses, never read as live."""
        event_log, mock_table = self._make_event_log_with_table(mocker)
        payload = json.loads(_decision_events(mode=PipeRunMode.LIVE)[0].model_dump_json())
        del payload["mode"]
        mock_table.query.return_value = {
            "Items": [{"PK": f"PIPELINE_RUN#{_RUN_ID}", "SK": "EVENT#wf_flow#primary#0000000000", "payload": json.dumps(payload)}]
        }

        with pytest.raises(EventLogSchemaMismatchError):
            event_log.read_events(_RUN_ID)

    def test_init_translates_construction_error(self, mocker: MockerFixture) -> None:
        # A botocore failure while building the boto3 client (e.g. a misconfigured region) must surface as
        # the domain EventLogSetupError so best-effort callers (tracing assembly) degrade rather than abort.
        construction_error = EndpointConnectionError(endpoint_url="https://dynamodb.bad-region.amazonaws.com")
        mocker.patch("pipelex.tracing.dynamodb_event_log.boto3.resource", side_effect=construction_error)

        with pytest.raises(EventLogSetupError) as exc_info:
            DynamoDBEventLog(table_name="trace-events-test", region="bad-region", retention_days=30)

        assert exc_info.value.__cause__ is construction_error
