"""DynamoDB-backed event log implementation.

Stores trace events in a DynamoDB table with the schema:
    PK: PIPELINE_RUN#{pipeline_run_id}
    SK: EVENT#{workflow_id}#{sequence:010d}
    payload: dict (full event via model_dump)

Compatible with the pipelex-api-infra TraceEventDynamoDBAdapter schema.
Requires: pip install "pipelex[dynamodb]"
"""

from typing import Any

from pydantic import TypeAdapter
from typing_extensions import override

from pipelex import log
from pipelex.system.exceptions import MissingDependencyError
from pipelex.tracing.event_log_protocol import EventLogProtocol
from pipelex.tracing.trace_events import AnyTraceEvent, TraceEvent

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
    provides natural deduplication for Temporal replay re-emissions.
    Read path: Query on PK, returns events sorted by SK which encodes
    (workflow_id, sequence) — matching the NDJSON ordering contract.

    WARNING: Do not call emit() from inside a Temporal workflow body — the
    synchronous boto3 HTTP call will block the workflow thread and trigger
    the deadlock detector. Use BufferingEventLog + act_flush_trace_events instead.
    """

    def __init__(self, table_name: str, region: str) -> None:
        if boto3 is None:
            lib_name = "boto3"
            lib_extra_name = "dynamodb"
            msg = "boto3 is required for the DynamoDB event log backend."
            raise MissingDependencyError(lib_name, lib_extra_name, msg)

        self._table_name = table_name
        self._region = region
        self._sequence: int = 0
        dynamodb: Any = boto3.resource("dynamodb", region_name=self._region)  # pyright: ignore[reportUnknownMemberType, reportUnknownVariableType]
        self._table: Any = dynamodb.Table(self._table_name)  # pyright: ignore[reportUnknownMemberType]

    @override
    def next_sequence(self) -> int:
        """Return the next sequence number. Shared by all emitters."""
        seq = self._sequence
        self._sequence += 1
        return seq

    @staticmethod
    def _make_pk(pipeline_run_id: str) -> str:
        return f"PIPELINE_RUN#{pipeline_run_id}"

    @staticmethod
    def _make_sk(workflow_id: str, sequence: int) -> str:
        return f"EVENT#{workflow_id}#{sequence:010d}"

    def _key_condition(self, pipeline_run_id: str) -> Any:
        """Build a KeyConditionExpression for querying by pipeline_run_id."""
        return DynamoKey("PK").eq(self._make_pk(pipeline_run_id))  # pyright: ignore[reportOptionalCall]

    @override
    def emit(self, event: TraceEvent) -> None:
        """Write a single event to DynamoDB. Synchronous and idempotent."""
        item: dict[str, Any] = {
            "PK": self._make_pk(event.pipeline_run_id),
            "SK": self._make_sk(event.workflow_id, event.sequence),
            "pipeline_run_id": event.pipeline_run_id,
            "workflow_id": event.workflow_id,
            "sequence": event.sequence,
            "payload": event.model_dump_json(),
        }
        self._table.put_item(Item=item)

    @override
    def read_events(self, pipeline_run_id: str) -> list[TraceEvent]:
        """Read all events for a pipeline run from DynamoDB."""
        items: list[dict[str, Any]] = []

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

        events: list[TraceEvent] = []
        for item in items:
            payload = item.get("payload")
            if payload is None:
                log.warning(f"Skipping DynamoDB item with missing payload: PK={item.get('PK')}, SK={item.get('SK')}")
                continue
            try:
                event = _any_trace_event_adapter.validate_json(payload)
                events.append(event)
            except Exception as exc:
                log.warning(f"Skipping unparseable DynamoDB item: {exc}")

        return events

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
