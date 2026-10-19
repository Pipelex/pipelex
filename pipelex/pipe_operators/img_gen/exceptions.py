from mthds.protocol.problem.registry import CoreCode

from pipelex.base_exceptions import PipelexError
from pipelex.errors.error_code_declaration import InheritsCause


class PipeImgGenRunError(PipelexError):
    """A ``PipeImgGen`` could not gather what its prompt reads; it takes its cause's code, else a value it could not read."""

    error_code = InheritsCause(fallback=CoreCode.PIPE_INPUT_UNRESOLVED)


class PipeImgGenFactoryError(PipelexError):
    """The images a ``PipeImgGen`` prompt presents exceed what its model reads, found while the prompt is built at run time."""

    error_code = CoreCode.MODEL_CONTEXT_EXCEEDED
