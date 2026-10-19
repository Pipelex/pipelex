"""Exceptions for the error registry tooling (`pipelex-dev generate-error-registry` and its checks)."""

from mthds.protocol.problem.registry import CoreCode

from pipelex.cli.exceptions import PipelexCLIError


class ErrorRegistryError(PipelexCLIError):
    """Raised when the error registry's source, the standard's vendored files or a generated output cannot be used.

    Dev tooling that never reaches a run, so it takes ``runtime.unexpected``.
    """

    error_code = CoreCode.RUNTIME_UNEXPECTED
