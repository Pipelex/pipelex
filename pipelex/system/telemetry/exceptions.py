from pipelex.base_exceptions import PipelexError


class TelemetryConfigError(PipelexError):
    pass


class TelemetryConfigValidationError(TelemetryConfigError):
    pass


class LangfuseCredentialsError(PipelexError):
    pass
