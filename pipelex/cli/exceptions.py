from typing import ClassVar

from click import ClickException
from mthds.protocol.problem.registry import CoreCode

from pipelex.base_exceptions import PipelexError
from pipelex.cogt.inference.error_classification import UserAction, UserActionKind
from pipelex.errors.error_code_declaration import ErrorCodeDeclaration, InheritsCause
from pipelex.errors.registry.pipelex_codes import PipelexErrorCode


class PipelexCLIError(PipelexError, ClickException):
    """Raised when there's an error in CLI usage or operation.

    Most raise sites wrap the error that decides the code, so the class takes its cause's code. A raise site
    that names a misconfiguration itself chooses ``pipelex.config.invalid``, and the model-listing wrappers
    choose the code of the fault their uncoded cause stands for.
    """

    error_code: ClassVar[ErrorCodeDeclaration] = InheritsCause(
        fallback=CoreCode.RUNTIME_UNEXPECTED,
        others=(
            PipelexErrorCode.CONFIG_INVALID,
            PipelexErrorCode.CONFIG_VARIABLE_MISSING,
            PipelexErrorCode.CONFIG_CREDENTIAL_MISSING,
            CoreCode.PROVIDER_CREDENTIAL_REFUSED,
            CoreCode.PROVIDER_FAILED,
        ),
    )


class ReadinessCheckError(PipelexCLIError):
    """Raised when readiness checks fail (missing dependencies or dev mode without venv).

    Developer tooling: it fires only on a development install of Pipelex without a virtual environment.
    """

    error_code = CoreCode.RUNTIME_MISCONFIGURED


class MethodNotFoundError(PipelexError):
    """Raised when no installed method matches the given name."""

    error_code = CoreCode.METHOD_NOT_FOUND


class DuplicateMethodNameError(PipelexError):
    """Raised when two installed methods share the same name."""

    error_code = CoreCode.METHOD_AMBIGUOUS


class ExportedPipeNotFoundError(PipelexError):
    """Raised when no installed method exports the given pipe code."""

    error_code = CoreCode.REQUEST_PIPE_NOT_FOUND


class ExportedPipeAmbiguousError(PipelexError):
    """Raised when several installed methods export the given pipe code."""

    error_code = CoreCode.REQUEST_PIPE_AMBIGUOUS


class BundleClosureEmptyError(PipelexError):
    """Raised when the bundle closure a command assembled holds no .mthds bundle, so there is no method to read."""

    error_code = CoreCode.METHOD_NOT_FOUND


class AgentBootError(PipelexError):
    """``pipelex-agent`` could not boot Pipelex, and nothing along the failure's chain says what to do about it.

    Raised by the agent CLI's boot over a failure that carries no advice of its own, so the recovery path an agent can
    run reaches it as the problem's tip: diagnose with ``doctor``, bring an out-of-date configuration up to date with
    ``migrate``, or write a fresh one with ``init``. It takes its cause's code, so the problem stays the cause's.
    """

    error_code = InheritsCause(fallback=CoreCode.RUNTIME_UNEXPECTED)
    user_action = UserAction(
        kind=UserActionKind.UNKNOWN,
        detail=(
            "Run 'pipelex-agent doctor' to diagnose the installation and its configuration. An out-of-date configuration is "
            "brought up to date by 'pipelex-agent migrate --dry-run --format json', shown to the user, then "
            "'pipelex-agent migrate --yes'; 'pipelex-agent init' (--global for the home configuration) writes a fresh one "
            "instead, discarding its settings."
        ),
    )
