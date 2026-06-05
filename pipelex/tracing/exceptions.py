from pipelex.base_exceptions import PipelexError


class EventLogError(PipelexError):
    """Base error for trace-event log backend failures."""


class EventLogReadError(EventLogError):
    """Raised when reading trace events from the configured backend fails.

    Backends translate their own infrastructure exceptions (e.g. botocore
    ``ClientError`` / ``BotoCoreError`` from DynamoDB on throttling, auth, or
    network failures) into this domain error at the boundary. That lets
    best-effort observability callers — graph assembly degrades to ``None``
    rather than failing the pipeline run — catch a single Pipelex error instead
    of re-widening their ``except`` clauses to raw third-party exception types.
    """
