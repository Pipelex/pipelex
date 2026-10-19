from mthds.protocol.problem.registry import CoreCode

from pipelex.cogt.exceptions import CogtError
from pipelex.errors.error_code_declaration import ErrorCodeSet


class ExtractInputError(CogtError):
    """An extraction handed an input it cannot take.

    ``runtime.unexpected`` for an input with neither or both of an image and a document, which our own code builds,
    and ``model.capability_unsupported`` for an input of a kind the model does not read, which its raise site chooses.
    """

    error_code = ErrorCodeSet(default=CoreCode.RUNTIME_UNEXPECTED, others=(CoreCode.MODEL_CAPABILITY_UNSUPPORTED,))
