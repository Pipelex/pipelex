"""DynamoDB-backed event log implementation.

Stores trace events in a DynamoDB table with the schema:
    PK: PIPELINE_RUN#{pipeline_run_id}
    SK: EVENT#{chain_digest}#{writer_id}#{sequence:010d}
    payload: the full event as JSON, its lineage, workflow and attempt included

The chain digest is the SHA-256 of the event's chain key, the event's lineage
followed by its own workflow and attempt (`TraceEvent.chain_key`), so a
workflow's new attempt, whose sequence starts again, never overwrites the rows
of its earlier one, while the sort key keeps one length however deep the
lineage and however long its workflow ids: DynamoDB refuses a sort key over
1,024 bytes. The row's chain itself is read back from its payload.

The schema is this backend's own, and no other writer's is promised to match
it. A row written by a version whose sort key named the workflow and no chain
holds an event without `attempt`, `lineage` or `path`, which the read refuses
with `EventLogSchemaMismatchError` rather than deduplicating it against a
current row.

Requires: pip install "pipelex[dynamodb]"
"""

import threading
from typing import Any

from pydantic import TypeAdapter, ValidationError
from typing_extensions import override

from pipelex import log
from pipelex.system.exceptions import MissingDependencyError
from pipelex.system.execution_chain import execution_chain_digest
from pipelex.tools.log.error_fields import error_fields
from pipelex.tools.typing.pydantic_utils import format_pydantic_validation_error
from pipelex.tracing.event_log_protocol import EventLogProtocol, deduplicate_and_order_events
from pipelex.tracing.exceptions import EventLogReadError, EventLogSchemaMismatchError, EventLogSetupError
from pipelex.tracing.trace_events import AnyTraceEvent, TraceEvent, json_invalid_message

try:
    import boto3
    from boto3.dynamodb.conditions import Key as DynamoKey
except ImportError:
    boto3 = None  # type: ignore[assignment]
    DynamoKey = None  # type: ignore[assignment, misc]

_any_trace_event_adapter: TypeAdapter[TraceEvent] = TypeAdapter(AnyTraceEvent)


class DynamoDBEventLog(EventLogProtocol):
    """Event log backed by AWS DynamoDB.

    Write path: PutItem per event, synchronous. DynamoDB's PK+SK uniqueness
    provides natural deduplication for Temporal replay re-emissions, since a
    replayed event has the same chain, writer and sequence, and so the same SK.
    Read path: Query on PK, then the events ordered as every event log returns
    them (`deduplicate_and_order_events`): the SK's chain digest orders the
    rows by no chain. The rule's deduplication finds nothing to drop here,
    the key having already kept one row per event.

    WARNING: Do not call emit() from inside a Temporal workflow body — the
    synchronous boto3 HTTP call will block the workflow thread and trigger
    the deadlock detector. Use BufferingEventLog + act_flush_trace_events instead.
    """

    def __init__(self, table_name: str, region: str, writer_id: str = "primary") -> None:
        if boto3 is None:
            lib_name = "boto3"
            lib_extra_name = "dynamodb"
            msg = "boto3 is required for the DynamoDB event log backend."
            raise MissingDependencyError(lib_name, lib_extra_name, msg)

        self._table_name = table_name
        self._region = region
        self._writer_id = writer_id
        self._sequence: int = 0
        self._sequence_lock = threading.Lock()
        # Translate construction-time botocore failures (e.g. a misconfigured region) into our
        # domain EventLogSetupError, mirroring the read_events boundary. Best-effort callers
        # (tracing assembly) catch the EventLogError base and degrade rather than aborting the run.
        from botocore.exceptions import (  # ruff: ignore[import-outside-top-level] - optional dependency, lazy import
            BotoCoreError,
            ClientError,
        )

        try:
            dynamodb: Any = boto3.resource("dynamodb", region_name=self._region)  # pyright: ignore[reportUnknownMemberType, reportUnknownVariableType]
            self._table: Any = dynamodb.Table(self._table_name)  # pyright: ignore[reportUnknownMemberType]
        except (ClientError, BotoCoreError) as exc:
            msg = f"Failed to construct the DynamoDB event-log client for table={self._table_name} region={self._region}: {exc}"
            raise EventLogSetupError(msg) from exc

    @property
    @override
    def writer_id(self) -> str:
        return self._writer_id

    @override
    def next_sequence(self) -> int:
        """Return the next sequence number. Shared by all emitters.

        Guarded by a per-instance lock so concurrent activity threads
        sharing this backend cannot collide on the dedup key.
        """
        with self._sequence_lock:
            seq = self._sequence
            self._sequence += 1
            return seq

    @staticmethod
    def _make_pk(pipeline_run_id: str) -> str:
        return f"PIPELINE_RUN#{pipeline_run_id}"

    @staticmethod
    def _make_sk(*, chain_key: str, writer_id: str, sequence: int) -> str:
        """The sort key of one event: its chain, its writer and its sequence, which tell it apart from every other event
        of its run.

        The chain is written as the SHA-256 hex digest of its key, so the sort key's length does not grow with the
        lineage, and the same chain always gives the same digest, so a replayed write still overwrites its own row.
        """
        return f"EVENT#{execution_chain_digest(chain_key=chain_key)}#{writer_id}#{sequence:010d}"

    def _key_condition(self, pipeline_run_id: str) -> Any:
        """Build a KeyConditionExpression for querying by pipeline_run_id."""
        return DynamoKey("PK").eq(self._make_pk(pipeline_run_id))  # pyright: ignore[reportOptionalCall]

    @override
    def emit(self, event: TraceEvent) -> None:
        """Write a single event to DynamoDB. Synchronous and idempotent."""
        item: dict[str, Any] = {
            "PK": self._make_pk(event.pipeline_run_id),
            "SK": self._make_sk(chain_key=event.chain_key, writer_id=event.writer_id, sequence=event.sequence),
            "pipeline_run_id": event.pipeline_run_id,
            "workflow_id": event.workflow_id,
            "attempt": event.attempt,
            "writer_id": event.writer_id,
            "sequence": event.sequence,
            "payload": event.model_dump_json(),
        }
        self._table.put_item(Item=item)

    @override
    def read_events(self, pipeline_run_id: str) -> list[TraceEvent]:
        """Read all events for a pipeline run from DynamoDB.

        The events are ordered by (chain, sequence, writer_id), as every event
        log returns them, whatever order the sort keys give the rows. A row in
        the shape an earlier version wrote, without `attempt`, `lineage` or
        `path`, is refused with ``EventLogSchemaMismatchError``, never read as
        the direct mode's first attempt.

        Store-level failures (throttling, auth, network) are translated into
        ``EventLogReadError`` so best-effort callers (graph assembly) can degrade
        gracefully without catching raw botocore exceptions. Individual
        unparseable items are skipped with a warning rather than failing the read.
        """
        from botocore.exceptions import (  # ruff: ignore[import-outside-top-level] - optional dependency, lazy import
            BotoCoreError,
            ClientError,
        )

        items: list[dict[str, Any]] = []
        try:
            response = self._table.query(
                KeyConditionExpression=self._key_condition(pipeline_run_id),
                ScanIndexForward=True,
            )
            items.extend(response.get("Items", []))

            while "LastEvaluatedKey" in response:
                response = self._table.query(
                    KeyConditionExpression=self._key_condition(pipeline_run_id),
                    ScanIndexForward=True,
                    ExclusiveStartKey=response["LastEvaluatedKey"],
                )
                items.extend(response.get("Items", []))
        except (ClientError, BotoCoreError) as exc:
            msg = f"Failed to read trace events from DynamoDB for pipeline_run_id={pipeline_run_id}: {type(exc).__name__}"
            raise EventLogReadError(msg) from exc

        events: list[TraceEvent] = []
        refused_count = 0
        first_refusal: str | None = None
        for item in items:
            payload = item.get("payload")
            if payload is None:
                log.warning(
                    "A trace event item in DynamoDB has no payload, and was skipped",
                    fields={"pipeline_run_id": pipeline_run_id, "sort_key": item.get("SK")},
                )
                continue
            try:
                event = _any_trace_event_adapter.validate_json(payload)
            except ValidationError as exc:
                # `validate_json` reports unparseable input as a `json_invalid` entry rather than raising
                # `JSONDecodeError`, so the two cases are told apart by the error type. A payload the event
                # models refuse was stored whole, by a version whose event shape this one no longer accepts
                # — so it is counted and raised rather than skipped, which would have handed the caller a
                # silently truncated record of the run. This is the shape that persists across a rolling
                # deploy, where one image writes what another reads back.
                if (json_error := json_invalid_message(validation_error=exc)) is not None:
                    log.warning(
                        "A trace event item in DynamoDB is not valid JSON, and was skipped",
                        fields={"pipeline_run_id": pipeline_run_id, "sort_key": item.get("SK"), **error_fields(exc=exc, text=json_error)},
                    )
                    continue
                refused_count += 1
                if first_refusal is None:
                    first_refusal = f"PK={item.get('PK')} SK={item.get('SK')}: {format_pydantic_validation_error(exc)}"
                continue
            events.append(event)

        if refused_count:
            msg = (
                f"{refused_count} trace event(s) for pipeline_run_id={pipeline_run_id} are in a shape this version "
                f"does not accept, most likely written by an earlier one; run the pipeline again to get a log in the "
                f"current shape. First refusal: {first_refusal}"
            )
            raise EventLogSchemaMismatchError(msg)

        return deduplicate_and_order_events(events=events)

    @override
    def close(self) -> None:
        """No-op: boto3 resources are reusable across calls."""

    @override
    def cleanup(self, pipeline_run_id: str) -> None:
        """Delete all events for a pipeline run. In practice TTL handles this."""
        response = self._table.query(
            KeyConditionExpression=self._key_condition(pipeline_run_id),
            ProjectionExpression="PK, SK",
        )
        items: list[dict[str, Any]] = response.get("Items", [])
        while "LastEvaluatedKey" in response:
            response = self._table.query(
                KeyConditionExpression=self._key_condition(pipeline_run_id),
                ProjectionExpression="PK, SK",
                ExclusiveStartKey=response["LastEvaluatedKey"],
            )
            items.extend(response.get("Items", []))

        if not items:
            return

        with self._table.batch_writer() as writer:
            for item in items:
                writer.delete_item(Key={"PK": item["PK"], "SK": item["SK"]})
