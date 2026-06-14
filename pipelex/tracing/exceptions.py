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


class EventLogSetupError(EventLogError):
    """Raised when constructing the configured event-log backend fails.

    The sibling of :class:`EventLogReadError` for the *construction* boundary:
    backends translate the infrastructure exceptions their client setup can raise
    (e.g. botocore ``ClientError`` / ``BotoCoreError`` from ``boto3.resource`` on a
    misconfigured region or credential chain) into this domain error. Best-effort
    observability callers catch the :class:`EventLogError` base so a backend that
    cannot even be built degrades to an ``*_assembly_error`` note rather than
    aborting the pipeline run.
    """
