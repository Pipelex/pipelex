from typing import ClassVar

from mthds.protocol.problem.registry import CoreCode

from pipelex.base_exceptions import PipelexError
from pipelex.cogt.inference.error_classification import UserAction, UserActionKind
from pipelex.core.memory.absence import AbsenceRecord
from pipelex.core.pipes.exceptions import PipeRunError
from pipelex.errors.error_code_declaration import ABSTRACT_ERROR, ErrorCodeDeclaration, ErrorCodeSet
from pipelex.system.pipe_run_mode import PipeRunMode


class InputStuffSpecsError(PipelexError):
    error_code: ClassVar[ErrorCodeDeclaration] = ABSTRACT_ERROR


class InputStuffSpecsFactoryError(InputStuffSpecsError):
    """An input's concept spec that does not parse, which the blueprint validators refuse first in practice."""

    error_code = CoreCode.METHOD_SCHEMA_VIOLATION


class InputStuffSpecNotFoundError(InputStuffSpecsError):
    """A pipe's inputs lack a variable its wiring names."""

    error_code = CoreCode.METHOD_WIRING_INVALID


class PipeRunInputsError(PipeRunError):
    """A pipe's input cannot be found when it runs.

    Its raise site chooses the code: ``input.missing`` for an input the run's caller did not send,
    ``input.reference_not_found`` for an input whose resource does not resolve, ``method.wiring_invalid`` for a
    wiring that names no input, and the default ``pipe.input_unresolved`` for a value no earlier step produced.
    """

    error_code = ErrorCodeSet(
        default=CoreCode.PIPE_INPUT_UNRESOLVED,
        others=(CoreCode.INPUT_MISSING, CoreCode.INPUT_REFERENCE_NOT_FOUND, CoreCode.METHOD_WIRING_INVALID),
    )

    def __init__(
        self,
        message: str,
        run_mode: PipeRunMode,
        pipe_code: str,
        missing_inputs: list[str] | None = None,
        variable_name: str | None = None,
        concept_code: str | None = None,
    ):
        self.missing_inputs = missing_inputs
        self.variable_name = variable_name
        self.concept_code = concept_code
        super().__init__(message, run_mode, pipe_code)


class OptionalValueAbsentError(PipeRunError):
    """A force-marked (`!`) input was fed a recorded absence at run time (D9).

    The method force-unwraps a value that this input data does not contain. Carries the
    variable name, the consuming pipe, and the full provenance chain from the absence ledger,
    so the report can say where the absence entered the flow and why.

    ``pipe.forced_input_absent``: the failure is data-dependent — the method's assumption failed
    on this input data, not on the caller's request shape.

    ``_authors_caller_facing_message``: the message and user action describe the caller's own
    method and data (pipe codes, variable names, ledger reasons — no server internals), and the
    caller is the only one who can act on them; they must survive STRICT disclosure.
    """

    error_code = CoreCode.PIPE_FORCED_INPUT_ABSENT
    _authors_caller_facing_message = True

    def __init__(
        self,
        message: str,
        *,
        run_mode: PipeRunMode,
        pipe_code: str,
        variable_name: str,
        absence_record: AbsenceRecord,
    ):
        self.variable_name = variable_name
        self.absence_record = absence_record
        self.user_action = UserAction(
            kind=UserActionKind.CHANGE_INPUT,
            detail=(
                f"The method force-unwraps ('!') the input '{variable_name}', which is absent for this input data. "
                f"Provide input data that contains this value, or change the method to tolerate absence "
                f"(declare the input optional with '?', or let the step skip by removing '!')."
            ),
        )
        super().__init__(message, run_mode, pipe_code)

    @classmethod
    def make(
        cls,
        *,
        run_mode: PipeRunMode,
        pipe_code: str,
        variable_name: str,
        concept_ref: str,
        absence_record: AbsenceRecord,
    ) -> "OptionalValueAbsentError":
        """Compose the D9 failure message from the provenance chain."""
        origin = absence_record.origin()
        if origin.producing_pipe:
            origin_clause = f"pipe '{origin.producing_pipe}' produced no value — \"{origin.reason}\""
        else:
            origin_clause = f'"{origin.reason}"'
        message = (
            f"Pipe '{pipe_code}' requires '{variable_name}' to be present (declared '{concept_ref}!'), but it is absent.\n"
            f"Absence origin: {origin_clause}\n"
            f"Fix in the method: declare the input '{concept_ref}?' and guard its uses, or let the step skip "
            f"by removing '!'. Fix in the data: provide input data that contains this value."
        )
        return cls(
            message,
            run_mode=run_mode,
            pipe_code=pipe_code,
            variable_name=variable_name,
            absence_record=absence_record,
        )


class NoInputsRequiredError(PipelexError):
    """Raised when a pipe has no inputs.

    A signal rather than an error: every caller answers it with an empty template or a notice. It carries
    ``request.unsupported`` until it becomes a return value.
    """

    error_code = CoreCode.REQUEST_UNSUPPORTED
