from click import ClickException

from pipelex.exceptions import PipelexException


class PipelexCLIError(PipelexException, ClickException):
    """Raised when there's an error in CLI usage or operation."""
