from typing import ClassVar

from mthds.protocol.problem.registry import CoreCode

from pipelex.base_exceptions import PipelexError, PipelexUnexpectedError
from pipelex.errors.error_code_declaration import ABSTRACT_ERROR, ErrorCodeDeclaration
from pipelex.errors.registry.pipelex_codes import PipelexErrorCode


class ToolError(PipelexError):
    """The base of the errors raised by Pipelex's own tools; never raised directly."""

    error_code: ClassVar[ErrorCodeDeclaration] = ABSTRACT_ERROR


class JobMetadataError(PipelexUnexpectedError):
    """A worker was called without the job metadata every call carries: a fault of ours."""

    error_code = CoreCode.RUNTIME_UNEXPECTED


class InvocationPathError(PipelexUnexpectedError):
    """Raised when an invocation's path cannot be derived: a controller dispatched a pipe without naming its segment.

    Every controller names the place of each pipe it runs before it runs it, so this is a fault of the runtime, never
    of the method.
    """

    error_code = CoreCode.RUNTIME_UNEXPECTED


class NestedKeyConflictError(ToolError):
    """Raised when attempting to create nested keys under a non-dict value.

    Reached when a method's extra prompt parameters name a dotted key under a value that cannot hold one, so the
    method's prompt cannot be rendered.
    """

    error_code = CoreCode.PIPE_TEMPLATE_RENDER_FAILED


class EnvVarNotFoundError(ToolError):
    """A required environment variable is not set: fixed by an operator setting it, not by the caller."""

    error_code = PipelexErrorCode.CONFIG_VARIABLE_MISSING


class MissingDependencyError(PipelexError):
    """Raised when a required dependency is not installed: an optional extra the operator installs."""

    error_code = PipelexErrorCode.CONFIG_DEPENDENCY_MISSING

    def __init__(self, dependency_name: str, extra_name: str, message: str | None = None):
        self.dependency_name = dependency_name
        self.extra_name = extra_name
        error_msg = f"Required dependency '{dependency_name}' is not installed."
        if message:
            error_msg += f" {message}"
        error_msg += f" Please install it with 'uv pip install \"pipelex[{extra_name}]\"'."
        super().__init__(error_msg)


class CredentialsError(PipelexError):
    """The base of the errors about a missing or refused credential; never raised directly."""

    error_code: ClassVar[ErrorCodeDeclaration] = ABSTRACT_ERROR


class ConfigValidationError(PipelexError):
    """A configuration value this process refuses: the operator's configuration.

    It logs nothing when it is created: whoever handles it reports it, once. A load that recovers from it, by carrying a
    stale file forward through the migration ledger, has nothing to report but the warning it parks.
    """

    error_code = PipelexErrorCode.CONFIG_INVALID


class RunParameterError(PipelexError, ValueError):
    """A run parameter a host passes is not one the runtime accepts: a request id, run extras, a storage or read scope.

    Also a ``ValueError``: the same checks run inside pydantic validators, which turn only a ``ValueError`` into a
    validation error, and as plain calls at a host's entry point.
    """

    error_code = CoreCode.REQUEST_INVALID
