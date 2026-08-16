from pipelex.base_exceptions import PipelexConfigError, PipelexError


class TelemetryConfigError(PipelexConfigError):
    """A telemetry configuration this process cannot use.

    A :class:`PipelexConfigError` rather than a bare :class:`PipelexError`, and both halves of
    that are load-bearing. It carries ``error_domain = CONFIG`` from the class instead of from the
    agent CLI's lookup table, so the class is the single source of truth the drift test asks for;
    and it can carry a :class:`MigrationErrorBlock`, which is what lets a stale ``telemetry.toml``
    say *old* rather than *wrong* on every surface that reports it.
    """


class TelemetryConfigValidationError(TelemetryConfigError):
    pass


class LangfuseCredentialsError(PipelexError):
    pass
