"""Factory for creating event log backends from configuration."""

from pipelex.base_exceptions import PipelexConfigError
from pipelex.system.configuration.configs import TracingBackend, TracingConfig
from pipelex.tracing.dynamodb_event_log import DynamoDBEventLog
from pipelex.tracing.event_log_protocol import EventLogProtocol
from pipelex.tracing.ndjson_event_log import NdjsonEventLog


def make_event_log(tracing_config: TracingConfig, *, writer_id: str = "primary") -> EventLogProtocol:
    """Create an event log backend from tracing configuration.

    The writer_id is stamped on every TraceEvent emitted through the resulting
    log. Defaults to "primary" so existing call sites keep emitting into the
    legacy single-writer NDJSON file / DDB sort-key shape.
    """
    match tracing_config.backend:
        case TracingBackend.NDJSON:
            if tracing_config.ndjson is None:
                msg = "ndjson config is required when backend is 'ndjson'"
                raise PipelexConfigError(msg)
            return NdjsonEventLog(traces_dir=tracing_config.ndjson.traces_dir, writer_id=writer_id)
        case TracingBackend.DYNAMODB:
            if tracing_config.dynamodb is None:
                msg = "dynamodb config is required when backend is 'dynamodb'"
                raise PipelexConfigError(msg)
            return DynamoDBEventLog(
                table_name=tracing_config.dynamodb.table_name,
                region=tracing_config.dynamodb.region,
                writer_id=writer_id,
            )
        case TracingBackend.TEMPORAL_DYNAMODB:
            if tracing_config.temporal_dynamodb is None:
                msg = "temporal_dynamodb config is required when backend is 'temporal_dynamodb'"
                raise PipelexConfigError(msg)
            return DynamoDBEventLog(
                table_name=tracing_config.temporal_dynamodb.table_name,
                region=tracing_config.temporal_dynamodb.region,
                writer_id=writer_id,
            )
