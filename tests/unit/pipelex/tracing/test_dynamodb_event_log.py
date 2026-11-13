import json
import math
import time
from datetime import UTC, datetime, timedelta
from typing import Any

import pytest
from botocore.exceptions import BotoCoreError, ClientError, EndpointConnectionError
from pydantic import ValidationError
from pytest_mock import MockerFixture
from typing_extensions import override

from pipelex.cogt.llm.llm_report import LLMTokensUsage
from pipelex.cogt.usage.cost_category import CostCategory
from pipelex.cogt.usage.token_category import TokenCategory
from pipelex.graph.graphspec import GraphSpec, IOSpec, NodeKind, NodeSpec
from pipelex.system.configuration.configs import DynamoDBTracingConfig, TracingConfig
from pipelex.system.execution_chain import ExecutionAttempt
from pipelex.system.job_metadata import JobCategory, JobMetadata, RunMetadata, UnitJobId
from pipelex.system.pipe_run_mode import PipeRunMode
from pipelex.tracing.buffering_event_log import BufferingEventLog
from pipelex.tracing.dynamodb_event_log import DynamoDBEventLog, dynamodb_item_size
from pipelex.tracing.event_log_factory import make_event_log
from pipelex.tracing.event_log_protocol import EventLogProtocol
from pipelex.tracing.exceptions import EventLogReadError, EventLogSchemaMismatchError, EventLogSetupError, TraceEventTooLargeError
from pipelex.tracing.graphspec_assembler import GraphSpecAssembler
from pipelex.tracing.in_memory_event_log import InMemoryEventLog
from pipelex.tracing.trace_events import (
    BatchFannedOutEvent,
    ConditionResolvedEvent,
    ExecutionDataEvent,
    PipeEndSuccessEvent,
    PipeStartEvent,
    TraceEvent,
    UsageReportEvent,
)
from tests.unit.pipelex.tracing.conftest import make_trace_event

# DynamoDB refuses a sort key longer than this many bytes.
_DYNAMODB_MAX_SORT_KEY_BYTES = 1024

# DynamoDB refuses an item larger than this many bytes, its attribute names and values counted together.
_DYNAMODB_MAX_ITEM_BYTES = 409_600
# DynamoDB stores a number in at most this many bytes.
_DYNAMODB_MAX_NUMBER_BYTES = 21

_SECONDS_PER_DAY = 86_400
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


def _dynamodb_item_bytes(item: dict[str, Any]) -> int:
    """The size DynamoDB counts for an item: each attribute's name and value, a string in UTF-8, a number at its bound."""
    total = 0
    for name, value in item.items():
        total += len(name.encode("utf-8"))
        if isinstance(value, str):
            total += len(value.encode("utf-8"))
        else:
            total += _DYNAMODB_MAX_NUMBER_BYTES
    return total


class _SizeLimitedEventsTable(_FakeEventsTable):
    """An events table that refuses an item over DynamoDB's size limit, with the error DynamoDB raises."""

    @override
    def put_item(self, *, Item: dict[str, Any]) -> None:
        if _dynamodb_item_bytes(Item) > _DYNAMODB_MAX_ITEM_BYTES:
            raise ClientError(
                error_response={"Error": {"Code": "ValidationException", "Message": "Item size has exceeded the maximum allowed size"}},
                operation_name="PutItem",
            )
        super().put_item(Item=Item)


_BIG_RUN_ID = "plr-big-inputs"
_BIG_WORKFLOW_ID = "wf_big"
_BIG_GRAPH_ID = "big_graph"
_SEQUENCE_NODE_ID = f"{_BIG_GRAPH_ID}:{_BIG_WORKFLOW_ID}:node_sequence"
_FIRST_STEP_NODE_ID = f"{_BIG_GRAPH_ID}:{_BIG_WORKFLOW_ID}:node_first"
_READER_STEP_NODE_ID = f"{_BIG_GRAPH_ID}:{_BIG_WORKFLOW_ID}:node_reader"
_LAST_STEP_NODE_ID = f"{_BIG_GRAPH_ID}:{_BIG_WORKFLOW_ID}:node_last"
_RATES = {CostCategory.INPUT: 3.0, CostCategory.OUTPUT: 15.0}
_COST_OF_ONE_RATED_CALL = 100 * 3.0 / 1_000_000 + 50 * 15.0 / 1_000_000
# A web page as an extraction leaves it, a few hundred kilobytes, with characters that UTF-8 writes in two bytes.
_PAGE_TEXT = "Prix publics, tarif hors taxes: 1 250 €. " * 7_000
# A rendered prompt quoting several such pages, about 2 MB.
_PROMPT_TEXT = "Lis les pages suivantes et relève chaque prix public. " * 38_000


def _big_base(*, sequence: int) -> dict[str, Any]:
    return {
        "pipeline_run_id": _BIG_RUN_ID,
        "workflow_id": _BIG_WORKFLOW_ID,
        "attempt": 1,
        "lineage": [],
        "path": None,
        "timestamp": _T0 + timedelta(seconds=sequence),
        "sequence": sequence,
        "mode": PipeRunMode.LIVE,
    }


def _page_spec(*, index: int) -> IOSpec:
    """A page input, each index a few kilobytes longer than the one before, so the largest is known."""
    page_text = _PAGE_TEXT + "Note de bas de page. " * 200 * index
    return IOSpec(
        name=f"page_{index}",
        concept="Page",
        content_type="text/plain",
        preview=page_text[:100],
        size=len(page_text),
        digest=f"digest_page_{index}",
        data={"text": page_text, "url": f"https://example.com/prix/{index}"},
        multiplicity=None,
    )


def _step_start(
    *,
    sequence: int,
    node_id: str,
    parent_node_id: str | None,
    node_kind: NodeKind,
    pipe_type: str,
    input_specs: list[IOSpec] | None = None,
    pipe_data: dict[str, Any] | None = None,
    concept_data: list[dict[str, Any]] | None = None,
) -> PipeStartEvent:
    return PipeStartEvent(
        **_big_base(sequence=sequence),
        node_id=node_id,
        parent_node_id=parent_node_id,
        pipe_code=node_id.rsplit(":", 1)[-1],
        pipe_ref=None,
        pipe_type=pipe_type,
        node_kind=node_kind,
        input_specs=input_specs or [],
        pipe_data=pipe_data or {},
        concept_data=concept_data or [],
    )


def _step_end(*, sequence: int, node_id: str, output_spec: IOSpec | None = None) -> PipeEndSuccessEvent:
    return PipeEndSuccessEvent(
        **_big_base(sequence=sequence),
        node_id=node_id,
        pipe_code=node_id.rsplit(":", 1)[-1],
        pipe_ref=None,
        pipe_type="PipeLLM",
        ended_at=_T0 + timedelta(seconds=sequence),
        output_spec=output_spec,
    )


def _prompt_execution_data(*, sequence: int, node_id: str) -> ExecutionDataEvent:
    return ExecutionDataEvent(
        **_big_base(sequence=sequence),
        node_id=node_id,
        execution_data={
            "resolved_model": "claude-5-sonnet",
            "resolved_model_for_object": "claude-5-sonnet",
            "is_multiple_output": False,
            "rendered_system_prompt": "Tu es un assistant qui relève les prix.",
            "rendered_user_prompt": _PROMPT_TEXT,
            "structuring_path": None,
        },
    )


def _reader_usage(*, sequence: int) -> UsageReportEvent:
    return UsageReportEvent(
        **_big_base(sequence=sequence),
        node_id=_READER_STEP_NODE_ID,
        tokens_usage=LLMTokensUsage(
            job_metadata=JobMetadata(
                run_metadata=RunMetadata(storage_scope="test/scope", read_scope=None, user_id="user_test", pipeline_run_id=_BIG_RUN_ID),
                pipe_code="node_reader",
                unit_job_id=UnitJobId.LLM_GEN_TEXT,
                job_category=JobCategory.LLM_JOB,
            ),
            inference_model_name="claude-5-sonnet",
            inference_model_id="claude-5-sonnet-id",
            unit_costs=_RATES,
            nb_tokens_by_category={TokenCategory.INPUT: 100, TokenCategory.OUTPUT: 50},
        ),
    )


def _node_by_id(graph_spec: GraphSpec, *, node_id: str) -> NodeSpec:
    return next(node for node in graph_spec.nodes if node.node_id == node_id)


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

    def test_a_refusal_locates_the_field_and_never_quotes_the_traced_value(self, mocker: MockerFixture) -> None:
        """The refusal travels into the run's assembly errors: it names the refused field, never the traced value it held."""
        event_log, mock_table = self._make_event_log_with_table(mocker)
        payload = json.loads(_decision_events(mode=PipeRunMode.LIVE)[0].model_dump_json())
        payload["sequence"] = "traced-value-from-the-run"
        mock_table.query.return_value = {
            "Items": [{"PK": f"PIPELINE_RUN#{_RUN_ID}", "SK": "EVENT#wf_flow#primary#0000000000", "payload": json.dumps(payload)}]
        }

        with pytest.raises(EventLogSchemaMismatchError) as refusal:
            event_log.read_events(_RUN_ID)

        assert f"{payload['event_kind']}.sequence: Input should be a valid integer" in str(refusal.value)
        assert "traced-value-from-the-run" not in str(refusal.value)

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
        event_log = DynamoDBEventLog(table_name="trace-events-test", region="us-east-1", retention_days=30)
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
            DynamoDBEventLog(table_name="trace-events-test", region="bad-region", retention_days=30)

        assert exc_info.value.__cause__ is construction_error

    def _make_event_log_with_size_limited_table(self, mocker: MockerFixture) -> tuple[DynamoDBEventLog, _SizeLimitedEventsTable]:
        event_log = DynamoDBEventLog(table_name="trace-events-test", region="us-east-1", retention_days=30)
        size_limited_table = _SizeLimitedEventsTable()
        mocker.patch.object(event_log, "_table", new=size_limited_table)
        return event_log, size_limited_table

    def test_a_start_event_with_oversized_inputs_is_written_with_their_data_left_out(self, mocker: MockerFixture) -> None:
        """Inputs of a few hundred kilobytes each make a start event too large for its row: it is written with the data
        of its largest inputs left out and marked with its size, until it fits, everything else about each input unchanged.
        """
        event_log, size_limited_table = self._make_event_log_with_size_limited_table(mocker)
        input_specs = [_page_spec(index=index) for index in range(3)]
        start_event = _step_start(
            sequence=0,
            node_id=_READER_STEP_NODE_ID,
            parent_node_id=None,
            node_kind=NodeKind.OPERATOR,
            pipe_type="PipeLLM",
            input_specs=input_specs,
        )
        assert _dynamodb_item_bytes({"payload": start_event.model_dump_json()}) > _DYNAMODB_MAX_ITEM_BYTES

        event_log.emit(start_event)

        assert len(size_limited_table.items) == 1
        [read_back] = event_log.read_events(_BIG_RUN_ID)
        assert isinstance(read_back, PipeStartEvent)
        assert read_back.model_dump(exclude={"input_specs"}) == start_event.model_dump(exclude={"input_specs"})
        assert len(read_back.input_specs) == len(input_specs)
        # The two largest inputs are enough to leave out; the smallest is kept whole.
        assert read_back.input_specs[0] == input_specs[0]
        for written_spec, original_spec in zip(read_back.input_specs[1:], input_specs[1:], strict=True):
            assert written_spec.data is None
            assert written_spec.extra == {
                "data_omitted_bytes": len(json.dumps(original_spec.data, ensure_ascii=False, separators=(",", ":")).encode())
            }
            assert written_spec.model_dump(exclude={"data", "extra"}) == original_spec.model_dump(exclude={"data", "extra"})

    def test_an_execution_data_event_with_an_oversized_prompt_is_written_with_the_prompt_left_out(self, mocker: MockerFixture) -> None:
        """A rendered prompt of about 2 MB is left out and marked with its size, and the small values stay."""
        event_log, size_limited_table = self._make_event_log_with_size_limited_table(mocker)
        execution_data_event = _prompt_execution_data(sequence=0, node_id=_READER_STEP_NODE_ID)
        assert len(_PROMPT_TEXT.encode()) > 1_900_000

        event_log.emit(execution_data_event)

        assert len(size_limited_table.items) == 1
        [read_back] = event_log.read_events(_BIG_RUN_ID)
        assert isinstance(read_back, ExecutionDataEvent)
        assert read_back.execution_data == {
            "resolved_model": "claude-5-sonnet",
            "resolved_model_for_object": "claude-5-sonnet",
            "is_multiple_output": False,
            "rendered_system_prompt": "Tu es un assistant qui relève les prix.",
            "structuring_path": None,
            "omitted_bytes": {"rendered_user_prompt": len(json.dumps(_PROMPT_TEXT, ensure_ascii=False).encode())},
        }

    def test_an_event_under_the_budget_is_written_as_it_always_was(self, mocker: MockerFixture) -> None:
        """An event that fits is written unchanged: its payload is its own JSON, with no marker anywhere."""
        event_log, mock_table = self._make_event_log_with_table(mocker)
        start_event = _step_start(
            sequence=4,
            node_id=_FIRST_STEP_NODE_ID,
            parent_node_id=None,
            node_kind=NodeKind.OPERATOR,
            pipe_type="PipeLLM",
            input_specs=[_page_spec(index=0)],
        )

        event_log.emit(start_event)

        item: dict[str, Any] = mock_table.put_item.call_args.kwargs["Item"]
        assert item["payload"] == start_event.model_dump_json()
        assert "omitted_bytes" not in item["payload"]
        assert set(item) == {"PK", "SK", "pipeline_run_id", "workflow_id", "attempt", "writer_id", "sequence", "payload", "ttl"}

    def test_a_reduced_event_keeps_its_row(self, mocker: MockerFixture) -> None:
        """A reduced event keeps its sort key, so a replay writing it again overwrites its own row."""
        event_log, size_limited_table = self._make_event_log_with_size_limited_table(mocker)
        execution_data_event = _prompt_execution_data(sequence=3, node_id=_READER_STEP_NODE_ID)

        event_log.emit(execution_data_event)
        event_log.emit(execution_data_event)

        assert len(size_limited_table.items) == 1
        [(partition_key, sort_key)] = size_limited_table.items
        assert partition_key == f"PIPELINE_RUN#{_BIG_RUN_ID}"
        assert sort_key.endswith("#primary#0000000003")

    def test_the_worst_start_event_still_fits(self, mocker: MockerFixture) -> None:
        """Every bulky field of a start event oversized at once, its registries included, still gives a row that fits."""
        event_log, size_limited_table = self._make_event_log_with_size_limited_table(mocker)
        start_event = _step_start(
            sequence=0,
            node_id=_READER_STEP_NODE_ID,
            parent_node_id=None,
            node_kind=NodeKind.OPERATOR,
            pipe_type="PipeLLM",
            input_specs=[_page_spec(index=index) for index in range(8)],
            pipe_data={"domain_code": "prix", "code": "lire_prix_publics", "prompt": _PROMPT_TEXT},
            concept_data=[{"domain_code": "prix", "code": f"Page{index}", "description": _PAGE_TEXT} for index in range(3)],
        )

        event_log.emit(start_event)

        [item] = size_limited_table.items.values()
        assert _dynamodb_item_bytes(item) <= _DYNAMODB_MAX_ITEM_BYTES
        [read_back] = event_log.read_events(_BIG_RUN_ID)
        assert isinstance(read_back, PipeStartEvent)
        assert read_back.node_id == start_event.node_id
        assert all(spec.data is None and "data_omitted_bytes" in spec.extra for spec in read_back.input_specs)
        assert [spec.digest for spec in read_back.input_specs] == [spec.digest for spec in start_event.input_specs]

    def test_a_reduced_row_still_passes_the_pipe_meter_filter(self, mocker: MockerFixture) -> None:
        """The pipe meter selects end events with contains(payload, '"pipe_end_success"'): a reduced row still carries it."""
        event_log, size_limited_table = self._make_event_log_with_size_limited_table(mocker)
        output_spec = _page_spec(index=0).model_copy(update={"data": {"pages": [_PAGE_TEXT] * 3}})
        end_event = _step_end(sequence=6, node_id=_READER_STEP_NODE_ID, output_spec=output_spec)

        event_log.emit(end_event)

        [item] = size_limited_table.items.values()
        assert '"pipe_end_success"' in item["payload"]
        [read_back] = event_log.read_events(_BIG_RUN_ID)
        assert isinstance(read_back, PipeEndSuccessEvent)
        assert read_back.output_spec is not None
        assert read_back.output_spec.data is None
        assert read_back.output_spec.digest == output_spec.digest

    def test_every_step_of_a_run_with_oversized_events_is_a_node_carrying_its_cost(self, mocker: MockerFixture) -> None:
        """The regression: a sequence's middle step reads pages too large for one row and renders a 2 MB prompt. Written
        through the DynamoDB log and assembled, every step is a node, the middle step carries its inference, the sequence's
        subtree cost includes it and nothing is left unattributed.
        """
        event_log, _size_limited_table = self._make_event_log_with_size_limited_table(mocker)
        events: list[TraceEvent] = [
            _step_start(sequence=0, node_id=_SEQUENCE_NODE_ID, parent_node_id=None, node_kind=NodeKind.CONTROLLER, pipe_type="PipeSequence"),
            _step_start(
                sequence=1, node_id=_FIRST_STEP_NODE_ID, parent_node_id=_SEQUENCE_NODE_ID, node_kind=NodeKind.OPERATOR, pipe_type="PipeExtract"
            ),
            _step_end(sequence=2, node_id=_FIRST_STEP_NODE_ID),
            _step_start(
                sequence=3,
                node_id=_READER_STEP_NODE_ID,
                parent_node_id=_SEQUENCE_NODE_ID,
                node_kind=NodeKind.OPERATOR,
                pipe_type="PipeLLM",
                input_specs=[_page_spec(index=index) for index in range(5)],
            ),
            _reader_usage(sequence=4),
            _prompt_execution_data(sequence=5, node_id=_READER_STEP_NODE_ID),
            _step_end(sequence=6, node_id=_READER_STEP_NODE_ID),
            _step_start(sequence=7, node_id=_LAST_STEP_NODE_ID, parent_node_id=_SEQUENCE_NODE_ID, node_kind=NodeKind.OPERATOR, pipe_type="PipeFunc"),
            _step_end(sequence=8, node_id=_LAST_STEP_NODE_ID),
            _step_end(sequence=9, node_id=_SEQUENCE_NODE_ID),
        ]
        for event in events:
            event_log.emit(event)

        graph_spec = GraphSpecAssembler.assemble(events=event_log.read_events(_BIG_RUN_ID), graph_id=_BIG_GRAPH_ID)

        assert {node.node_id for node in graph_spec.nodes} == {_SEQUENCE_NODE_ID, _FIRST_STEP_NODE_ID, _READER_STEP_NODE_ID, _LAST_STEP_NODE_ID}
        reader_usage = _node_by_id(graph_spec, node_id=_READER_STEP_NODE_ID).usage
        assert reader_usage is not None
        assert reader_usage.inference_calls == 1
        sequence_usage = _node_by_id(graph_spec, node_id=_SEQUENCE_NODE_ID).usage
        assert sequence_usage is not None
        assert sequence_usage.subtree_cost is not None
        assert math.isclose(sequence_usage.subtree_cost, _COST_OF_ONE_RATED_CALL, rel_tol=1e-9)
        assert graph_spec.usage is not None
        assert graph_spec.usage.unattributed.inference_calls == 0
        assert graph_spec.usage.unattributed.cost is None

    def test_an_event_that_cannot_fit_is_refused_with_a_typed_error(self, mocker: MockerFixture) -> None:
        """Were the budget smaller than an event's identifiers, the fully reduced event would still not fit: the write is
        refused with a typed error naming what was left out, never sent to the table to fail there.
        """
        event_log, size_limited_table = self._make_event_log_with_size_limited_table(mocker)
        mocker.patch("pipelex.tracing.dynamodb_event_log.EVENTS_TABLE_ITEM_BUDGET_BYTES", new=100)

        with pytest.raises(TraceEventTooLargeError, match=r"execution_data\.rendered_user_prompt") as refusal:
            event_log.emit(_prompt_execution_data(sequence=0, node_id=_READER_STEP_NODE_ID))

        assert size_limited_table.items == {}
        assert "claude-5-sonnet" not in str(refusal.value)

    def test_an_oversized_rendered_value_is_cut_with_a_stated_suffix(self, mocker: MockerFixture) -> None:
        """A condition's rendered value too large for the row keeps its first characters and states the size of the whole."""
        event_log, _size_limited_table = self._make_event_log_with_size_limited_table(mocker)
        rendered_value = "résumé " * 80_000
        condition_event = ConditionResolvedEvent(
            **_big_base(sequence=0), node_id=_SEQUENCE_NODE_ID, rendered_value=rendered_value, selected_outcome="long"
        )

        event_log.emit(condition_event)

        [read_back] = event_log.read_events(_BIG_RUN_ID)
        assert isinstance(read_back, ConditionResolvedEvent)
        whole_bytes = len(json.dumps(rendered_value, ensure_ascii=False).encode())
        assert read_back.rendered_value == rendered_value[:200] + f"… [left out for size: {whole_bytes} bytes]"
        assert read_back.selected_outcome == "long"

    @pytest.mark.parametrize(
        ("item", "expected_bytes"),
        [
            ({"PK": "ab"}, 4),
            ({"payload": "€"}, 10),
            ({"sequence": 7, "ttl": 1_800_000_000}, 8 + 21 + 3 + 21),
        ],
    )
    def test_the_item_size_counts_names_and_values_as_dynamodb_does(self, item: dict[str, Any], expected_bytes: int) -> None:
        """A string counts its UTF-8 bytes, a number its 21-byte bound, and every attribute its name."""
        assert dynamodb_item_size(item=item) == expected_bytes
