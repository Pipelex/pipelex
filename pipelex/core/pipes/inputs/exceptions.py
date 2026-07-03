from pipelex.base_exceptions import ErrorDomain, PipelexError
from pipelex.cogt.inference.error_classification import UserAction, UserActionKind
from pipelex.core.memory.absence import AbsenceRecord
from pipelex.pipe_run.exceptions import PipeRunError
from pipelex.pipe_run.pipe_run_mode import PipeRunMode


class InputStuffSpecsError(PipelexError):
    pass


class InputStuffSpecsFactoryError(InputStuffSpecsError):
    pass


class InputStuffSpecNotFoundError(InputStuffSpecsError):
    pass


class PipeInputError(PipelexError):
    def __init__(
        self,
        message: str,
        pipe_code: str,
        variable_name: str | None = None,
        concept_code: str | None = None,
    ):
        self.pipe_code = pipe_code
        self.variable_name = variable_name
        self.concept_code = concept_code
        super().__init__(message)


class PipeRunInputsError(PipeRunError):
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

    ``error_domain = RUNTIME``: the failure is data-dependent — the method's assumption failed
    on this input data, not on the caller's request shape.
    """

    error_domain = ErrorDomain.RUNTIME

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


class NoInputsRequiredError(Exception):
    """Raised when a pipe has no inputs."""
