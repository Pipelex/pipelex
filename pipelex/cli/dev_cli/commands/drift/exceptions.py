"""Exceptions for the drift-contracts dev CLI (`pipelex-dev drift`).

Developer tooling: `pipelex-dev drift` checks this repository's own contracts, so no caller of a method ever
reads these codes.
"""

from typing import ClassVar

from mthds.protocol.problem.registry import CoreCode

from pipelex.cli.exceptions import PipelexCLIError
from pipelex.errors.error_code_declaration import ErrorCodeDeclaration
from pipelex.errors.registry.pipelex_codes import PipelexErrorCode


class DriftError(PipelexCLIError):
    """Base error for the drift-contracts tooling, also raised directly."""

    error_code: ClassVar[ErrorCodeDeclaration] = CoreCode.RUNTIME_UNEXPECTED


class DriftManifestError(DriftError):
    """Raised when drift.toml is missing, unparseable, or schema-invalid."""

    error_code = PipelexErrorCode.CONFIG_INVALID


class DriftAckError(DriftError):
    """Raised when an ack file is invalid or an ack operation cannot proceed."""

    error_code = CoreCode.REQUEST_INVALID


class DriftGitError(DriftError):
    """Raised when a git plumbing call needed by drift fails."""

    error_code = CoreCode.RUNTIME_UNEXPECTED
