"""Factory for creating event log backends from configuration."""

from pipelex.base_exceptions import PipelexConfigError
from pipelex.hub import get_event_log
from pipelex.system.configuration.configs import TracingBackend, TracingConfig
from pipelex.tracing.dynamodb_event_log import DynamoDBEventLog
from pipelex.tracing.event_log_protocol import EventLogProtocol
from pipelex.tracing.ndjson_event_log import NdjsonEventLog


def make_event_log(tracing_config: TracingConfig) -> EventLogProtocol:
    """Create or retrieve an event log backend based on tracing configuration.

    Resolution order:
    1. If an event log was injected via Pipelex.setup(event_log=...), use it
    2. Otherwise create a backend based on tracing_config.backend
    """
    injected = get_event_log()
    if injected is not None:
        return injected

    match tracing_config.backend:
        case TracingBackend.NDJSON:
            if tracing_config.ndjson is None:
                msg = "ndjson config is required when backend is 'ndjson'"
                raise PipelexConfigError(msg)
            return NdjsonEventLog(traces_dir=tracing_config.ndjson.traces_dir)
        case TracingBackend.DYNAMODB:
            if tracing_config.dynamodb is None:
                msg = "dynamodb config is required when backend is 'dynamodb'"
                raise PipelexConfigError(msg)
            return DynamoDBEventLog(
                table_name=tracing_config.dynamodb.table_name,
                region=tracing_config.dynamodb.region,
            )
