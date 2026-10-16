from mthds.protocol.problem.registry import CoreCode

from pipelex.base_exceptions import PipelexError
from pipelex.errors.error_code_declaration import InheritsCause


class PipeFuncTransportError(PipelexError):
    """A PipeFunc could not be packaged for, or rebound from, out-of-process execution.

    Raised while building the transport request (e.g. no crate is available for the current library,
    so the customer sources cannot travel) or while rehydrating the transported response: the library was not
    loaded the way out-of-process execution needs, which is the deployment's to fix.
    """

    error_code = CoreCode.RUNTIME_MISCONFIGURED


class PipeFuncExecutionError(PipelexError):
    """A transported PipeFunc failed to run to a usable result out-of-process.

    Raised by the ``direct`` executor's transported run (the code a sandbox box runs internally) when
    rehydration yields no working memory or the function exceeds its (plan-dependent) timeout — as
    opposed to the customer function itself raising, which propagates untouched. It takes its cause's code,
    else ``runtime.unexpected``; the timeout's raise site chooses ``pipe.function_timed_out``.
    """

    error_code = InheritsCause(fallback=CoreCode.RUNTIME_UNEXPECTED, others=(CoreCode.PIPE_FUNCTION_TIMED_OUT,))


class PipeFuncFunctionError(PipelexError):
    """A `PipeFunc`'s `function_name` names no function the step may call.

    Raised when the module the import path names is not found, when the function is not a top-level `def` or
    `async def` of that module carrying the `@pipe_func()` marker, or, once the module is imported, when the function
    does not follow the calling convention. The message names the step and the function, and describes the
    caller's own method, so it is kept under STRICT disclosure.
    """

    error_code = CoreCode.METHOD_FUNCTION_INVALID
    _authors_caller_facing_message = True
