from pipelex.base_exceptions import PipelexError


class PipeFuncTransportError(PipelexError):
    """A PipeFunc could not be packaged for, or rebound from, out-of-process execution.

    Raised while building the transport request (e.g. no crate is available for the current library,
    so the customer sources cannot travel) or while rehydrating the transported response.
    """


class PipeFuncExecutionError(PipelexError):
    """A transported PipeFunc failed to run to a usable result out-of-process.

    Raised by the ``direct`` executor's transported run (the code a sandbox box runs internally) when
    rehydration yields no working memory or the function exceeds its (plan-dependent) timeout — as
    opposed to the customer function itself raising, which propagates untouched.
    """
