import json
from datetime import UTC, datetime
from typing import Any

import pytest
from botocore.exceptions import BotoCoreError, ClientError, EndpointConnectionError
from pytest_mock import MockerFixture

from pipelex.graph.graphspec import NodeKind
from pipelex.system.pipe_run_mode import PipeRunMode
from pipelex.tracing.buffering_event_log import BufferingEventLog
from pipelex.tracing.dynamodb_event_log import DynamoDBEventLog
from pipelex.tracing.exceptions import EventLogReadError, EventLogSchemaMismatchError, EventLogSetupError
from pipelex.tracing.trace_events import BatchFannedOutEvent, ConditionResolvedEvent, PipeStartEvent, TraceEvent

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


class TestDynamoDBEventLogReadEvents:
    def _make_event_log_with_table(self, mocker: MockerFixture) -> tuple[DynamoDBEventLog, Any]:
        # boto3.resource(...) does not perform any network call at construction.
        event_log = DynamoDBEventLog(table_name="trace-events-test", region="us-east-1")
        mock_table = mocker.MagicMock()
        mocker.patch.object(event_log, "_table", new=mock_table)
        return event_log, mock_table

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
            DynamoDBEventLog(table_name="trace-events-test", region="bad-region")

        assert exc_info.value.__cause__ is construction_error
