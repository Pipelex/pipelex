"""Exceptions for the drift-contracts dev CLI (`pipelex-dev drift`)."""

from pipelex.cli.exceptions import PipelexCLIError


class DriftError(PipelexCLIError):
    """Base error for the drift-contracts tooling."""


class DriftManifestError(DriftError):
    """Raised when drift.toml is missing, unparseable, or schema-invalid."""


class DriftAckError(DriftError):
    """Raised when an ack file is invalid or an ack operation cannot proceed."""


class DriftGitError(DriftError):
    """Raised when a git plumbing call needed by drift fails."""
