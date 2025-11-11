from click import ClickException

from pipelex.base_exceptions import PipelexException


class PipelexCLIError(PipelexException, ClickException):
    """Raised when there's an error in CLI usage or operation."""


class ReadinessCheckError(PipelexCLIError):
    """Raised when readiness checks fail (missing dependencies or dev mode without venv)."""
