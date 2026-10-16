"""Exceptions for the error registry tooling (`pipelex-dev generate-error-registry` and its checks)."""

from pipelex.cli.exceptions import PipelexCLIError


class ErrorRegistryError(PipelexCLIError):
    """Raised when the error registry's source, the standard's vendored files or a generated output cannot be used."""
