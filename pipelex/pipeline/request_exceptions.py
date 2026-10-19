"""The refusal of a request's argument, raised by the runtime as both the protocol's class and a coded Pipelex error."""

from __future__ import annotations

from mthds.protocol.exceptions import PipelineRequestError
from mthds.protocol.problem.client_problems import make_client_problem
from mthds.protocol.problem.registry import CoreCode

from pipelex.base_exceptions import PipelexError
from pipelex.errors.error_code_declaration import ErrorCodeSet

# The status a runner answers a refused request field with, the same for both codes of the class.
_REFUSED_REQUEST_STATUS = 422


class PipelexRequestError(PipelineRequestError, PipelexError):
    """A request argument the runtime refuses before running anything: ``request.invalid`` or ``request.unsupported``.

    It is both the standard's :class:`~mthds.protocol.exceptions.PipelineRequestError`, which a client of the
    protocol catches whatever runner refused its request, and a :class:`~pipelex.base_exceptions.PipelexError`
    carrying the matching code, so the runtime's own boundaries report it like any other error (the census's
    question 13). Its ``problem`` is the standard's problem document for the same code, built from the registry.

    The code follows from the arguments: a field this runtime does not accept in the form it was sent, named
    with ``unsupported_reason``, is ``request.unsupported``; any other refused field is ``request.invalid``.
    """

    error_code = ErrorCodeSet(default=CoreCode.REQUEST_INVALID, others=(CoreCode.REQUEST_UNSUPPORTED,))

    def __init__(self, message: str, *, field: str, unsupported_reason: str | None = None) -> None:
        """Build the refusal of one request field.

        Args:
            message: What is wrong with the field, for a person; it names only what the caller sent.
            field: The refused field, by name, as the request spells it.
            unsupported_reason: Why this runtime does not accept the field's form, as an identifier such as
                ``extension_args_on_local_execute``; ``None`` for a field whose value is simply invalid.
        """
        code: CoreCode
        params: dict[str, str]
        if unsupported_reason is None:
            code = CoreCode.REQUEST_INVALID
            params = {"field": field}
        else:
            code = CoreCode.REQUEST_UNSUPPORTED
            params = {"field": field, "reason": unsupported_reason}
        super().__init__(message, problem=make_client_problem(code, params=params, status=_REFUSED_REQUEST_STATUS))
        # The protocol's class appends the problem's next step to the exception's text; the report's message
        # is the refusal alone, since the report states its next step on its own.
        self.message = message
        self.field = field
        self.with_error_code(code).with_params(**params)
