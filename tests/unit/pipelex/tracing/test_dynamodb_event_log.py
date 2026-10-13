import json
from datetime import UTC, datetime
from typing import Any

import pytest
from botocore.exceptions import BotoCoreError, ClientError, EndpointConnectionError
from pytest_mock import MockerFixture

from pipelex.graph.graphspec import NodeKind
from pipelex.system.execution_chain import ExecutionAttempt
from pipelex.system.pipe_run_mode import PipeRunMode
from pipelex.tracing.buffering_event_log import BufferingEventLog
from pipelex.tracing.dynamodb_event_log import DynamoDBEventLog
from pipelex.tracing.exceptions import EventLogReadError, EventLogSchemaMismatchError, EventLogSetupError
from pipelex.tracing.in_memory_event_log import InMemoryEventLog
from pipelex.tracing.trace_events import BatchFannedOutEvent, ConditionResolvedEvent, PipeStartEvent, TraceEvent

# DynamoDB refuses a sort key longer than this many bytes.
_DYNAMODB_MAX_SORT_KEY_BYTES = 1024

_RUN_ID = "plr-decisions"
_T0 = datetime(2026, 10, 13, 9, 0, 0, tzinfo=UTC)


def _decision_events(*, mode: PipeRunMode) -> list[TraceEvent]:
    base: dict[str, Any] = {
        "pipeline_run_id": _RUN_ID,
        "workflow_id": "wf_flow",
        "attempt": 1,
        "lineage": [],
        "path": None,
        "timestamp": _T0,
        "mode": mode,
    }
    return [
        PipeStartEvent(
            pipe_ref=None,
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


def _chain_event(*, lineage: list[ExecutionAttempt], workflow_id: str, attempt: int, sequence: int, writer_id: str = "primary") -> PipeStartEvent:
    return PipeStartEvent(
        pipeline_run_id=_RUN_ID,
        workflow_id=workflow_id,
        attempt=attempt,
        lineage=lineage,
        path=None,
        writer_id=writer_id,
        timestamp=_T0,
        mode=PipeRunMode.LIVE,
        sequence=sequence,
        pipe_ref=None,
        node_id=f"g:{workflow_id}:node_{sequence}",
        pipe_code="step",
        pipe_type="PipeCompose",
        node_kind=NodeKind.OPERATOR,
    )


class _FakeEventsTable:
    """A DynamoDB table holding one item per (PK, SK), which a query returns in sort-key order, as DynamoDB does."""

    def __init__(self) -> None:
        self.items: dict[tuple[str, str], dict[str, Any]] = {}

    def put_item(self, *, Item: dict[str, Any]) -> None:  # ruff: ignore[invalid-argument-name]  # boto3 kwarg name
        self.items[Item["PK"], Item["SK"]] = Item

    def query(self, *, KeyConditionExpression: Any, **_: Any) -> dict[str, Any]:  # ruff: ignore[invalid-argument-name]  # boto3 kwarg name
        partition_key = KeyConditionExpression.get_expression()["values"][1]
        return {"Items": [item for (pk, _sk), item in sorted(self.items.items()) if pk == partition_key]}


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

    def _make_event_log_with_fake_table(self, mocker: MockerFixture) -> tuple[DynamoDBEventLog, _FakeEventsTable]:
        event_log = DynamoDBEventLog(table_name="trace-events-test", region="us-east-1")
        fake_table = _FakeEventsTable()
        mocker.patch.object(event_log, "_table", new=fake_table)
        return event_log, fake_table

    def test_the_sort_key_stays_bounded_however_deep_and_long_the_lineage(self, mocker: MockerFixture) -> None:
        """Nested batches dispatched under long workflow ids give a chain key far past DynamoDB's sort-key limit: the sort
        key carries a digest of the chain, so its length does not grow with it, while a replayed write still overwrites
        its own row and every attempt keeps its own.
        """
        event_log, fake_table = self._make_event_log_with_fake_table(mocker)
        lineage = [ExecutionAttempt(execution=f"run-{depth:02d}-" + "x" * 200, attempt=depth + 1) for depth in range(12)]
        first_attempt = _chain_event(lineage=lineage, workflow_id="item-" + "y" * 300, attempt=1, sequence=7, writer_id="act_4242_abcdef12")
        second_attempt = first_attempt.model_copy(update={"attempt": 2})
        assert len(first_attempt.chain_key.encode()) > 2 * _DYNAMODB_MAX_SORT_KEY_BYTES

        event_log.emit(first_attempt)
        event_log.emit(first_attempt)
        event_log.emit(second_attempt)

        sort_keys = [sort_key for (_partition_key, sort_key) in fake_table.items]
        assert len(sort_keys) == 2
        for sort_key in sort_keys:
            assert len(sort_key.encode()) <= _DYNAMODB_MAX_SORT_KEY_BYTES
            assert sort_key.startswith("EVENT#")
            assert sort_key.endswith("#act_4242_abcdef12#0000000007")
        # The chain itself is read back whole from the row's payload.
        assert event_log.read_events(_RUN_ID) == [first_attempt, second_attempt]

    def test_read_events_dedupes_and_orders_as_every_event_log_does(self, mocker: MockerFixture) -> None:
        """The sort keys order the rows by the digest of their chains, which is no order of the run: the read returns
        the events deduplicated and ordered by (chain, sequence, writer), as the in-memory and NDJSON logs do, and a
        row written twice under two sort keys, as before and after the sort key changed shape, is read once.
        """
        event_log, fake_table = self._make_event_log_with_fake_table(mocker)
        run_attempt = ExecutionAttempt(execution="exec-run", attempt=1)
        events = [
            _chain_event(lineage=[run_attempt], workflow_id="exec-item-2", attempt=1, sequence=0),
            _chain_event(lineage=[], workflow_id="exec-run", attempt=1, sequence=1, writer_id="act_9_0000"),
            _chain_event(lineage=[run_attempt], workflow_id="exec-item-1", attempt=1, sequence=0),
            _chain_event(lineage=[], workflow_id="exec-run", attempt=1, sequence=0),
            _chain_event(lineage=[], workflow_id="exec-run", attempt=1, sequence=2),
        ]
        for event in events:
            event_log.emit(event)
        legacy_row = {**fake_table.items[next(iter(fake_table.items))], "SK": "EVENT#exec-run@1/exec-item-2@1#primary#0000000000"}
        fake_table.put_item(Item=legacy_row)
        reference_log = InMemoryEventLog()
        for event in events:
            reference_log.emit(event)

        read_back = event_log.read_events(_RUN_ID)

        assert [(event.chain_key, event.sequence, event.writer_id) for event in read_back] == [
            ("exec-run@1", 0, "primary"),
            ("exec-run@1", 1, "act_9_0000"),
            ("exec-run@1", 2, "primary"),
            ("exec-run@1/exec-item-1@1", 0, "primary"),
            ("exec-run@1/exec-item-2@1", 0, "primary"),
        ]
        assert read_back == reference_log.read_events(_RUN_ID)

    def test_init_translates_construction_error(self, mocker: MockerFixture) -> None:
        # A botocore failure while building the boto3 client (e.g. a misconfigured region) must surface as
        # the domain EventLogSetupError so best-effort callers (tracing assembly) degrade rather than abort.
        construction_error = EndpointConnectionError(endpoint_url="https://dynamodb.bad-region.amazonaws.com")
        mocker.patch("pipelex.tracing.dynamodb_event_log.boto3.resource", side_effect=construction_error)

        with pytest.raises(EventLogSetupError) as exc_info:
            DynamoDBEventLog(table_name="trace-events-test", region="bad-region")

        assert exc_info.value.__cause__ is construction_error
