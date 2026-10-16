from mthds.protocol.problem.registry import CoreCode

from pipelex.errors.registry.pipelex_codes import PipelexErrorCode
from pipelex.system.exceptions import ToolError


class SecretNotFoundError(ToolError):
    """Raised when the secrets provider holds no value for a secret the configuration names."""

    error_code = PipelexErrorCode.CONFIG_VARIABLE_MISSING


class VarNotFoundError(ToolError):
    """Raised when a variable named in a ``${…}`` placeholder is set nowhere."""

    error_code = PipelexErrorCode.CONFIG_VARIABLE_MISSING

    def __init__(self, var_name: str, message: str):
        self.var_name = var_name
        super().__init__(message)


class VarFallbackPatternError(ToolError):
    """Raised when no variable of a ``${a|b}`` fallback placeholder is set."""

    error_code = PipelexErrorCode.CONFIG_VARIABLE_MISSING


class UnknownVarPrefixError(ToolError):
    """Raised when an unknown variable prefix is used in variable substitution."""

    error_code = PipelexErrorCode.CONFIG_INVALID

    def __init__(self, var_name: str, message: str):
        self.var_name = var_name
        super().__init__(message)


class SecretVersionUnsupportedError(ToolError):
    """Raised when a specific version of a secret is asked of a secrets provider that keeps no versions."""

    error_code = CoreCode.RUNTIME_UNSUPPORTED
