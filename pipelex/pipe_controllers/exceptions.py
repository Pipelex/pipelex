from pipelex.base_exceptions import PipelexError
from pipelex.errors.error_code_declaration import ABSTRACT_ERROR


class PipeControllerError(PipelexError):
    """Base of the errors of the pipe controllers."""

    error_code = ABSTRACT_ERROR
