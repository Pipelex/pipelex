from typing import ClassVar

from pipelex.base_exceptions import PipelexConfigError, PipelexError
from pipelex.errors.error_code_declaration import ABSTRACT_ERROR, ErrorCodeDeclaration
from pipelex.errors.registry.pipelex_codes import PipelexErrorCode


class TelemetryConfigError(PipelexConfigError):
    """A telemetry configuration this process cannot use; never raised directly.

    A :class:`PipelexConfigError` rather than a bare :class:`PipelexError`, so that it can carry a
    :class:`MigrationErrorBlock`, which is what lets a stale ``telemetry.toml`` say *old* rather than *wrong*
    on every surface that reports it. Its subclasses carry a ``pipelex.config.*`` code, the operator's.
    """

    error_code: ClassVar[ErrorCodeDeclaration] = ABSTRACT_ERROR


class TelemetryConfigValidationError(TelemetryConfigError):
    """The telemetry configuration does not parse or does not validate."""

    error_code = PipelexErrorCode.CONFIG_INVALID


class TelemetryApiKeyMissingError(TelemetryConfigError):
    """A telemetry destination is enabled without the API key it sends with: a variable the operator sets."""

    error_code = PipelexErrorCode.CONFIG_VARIABLE_MISSING


class LangfuseCredentialsError(PipelexError):
    """Langfuse telemetry is enabled without its keys: a variable the operator sets."""

    error_code = PipelexErrorCode.CONFIG_VARIABLE_MISSING
