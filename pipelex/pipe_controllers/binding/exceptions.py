from typing import Any

from mthds.protocol.problem.registry import CoreCode
from typing_extensions import override

from pipelex.base_exceptions import PipelexError
from pipelex.errors.error_code_declaration import ErrorCodeSet


class BindingPathUnresolvedError(PipelexError):
    """A binding step's `from` path that cannot be walked before the run: the declared structures do not hold it,
    or the concept of its root is not known.

    Raised by the derivation walk, which knows nothing of the sequence holding the step: the sequence turns
    it into a `binding_path_unresolved` validation error naming itself. The message names the segment that
    failed and the fields that were available there, so a typo can be repaired from the message alone. A
    root whose values have different concepts, as the outcomes of a condition storing it under different
    concepts, is refused the same way, the message naming each outcome and the concept it stores.
    """

    error_code = CoreCode.METHOD_FIELD_PATH_UNRESOLVED

    def __init__(self, message: str, *, path: str, failed_segment: str, available_fields: list[str]):
        self.path = path
        self.failed_segment = failed_segment
        self.available_fields = available_fields
        super().__init__(message)

    @override
    def problem_params(self) -> dict[str, Any]:
        return {"path": self.path, "segment": self.failed_segment, "available_fields": self.available_fields}


class BindingStepRunError(PipelexError):
    """A binding step that could not bind its value at run time, although its path was derived before the run.

    The derivation walk vouches for the path, so this signals a value whose shape contradicts its concept's
    declared structure, such as an attribute the declared field promised and the value lacks, or the derived
    multiplicity, such as a list held by a root derived as a single value. A binding whose root a pipe that
    did not resolve at validation stored is derived when it runs, and a result that contradicts the sequence's
    output, or the input of the step reading it, is reported this way too.

    Its code is ``pipe.binding_failed``; a raise site finding a root that holds a list where a single value was
    derived, or the reverse, chooses ``pipe.output_multiplicity``.
    """

    error_code = ErrorCodeSet(default=CoreCode.PIPE_BINDING_FAILED, others=(CoreCode.PIPE_OUTPUT_MULTIPLICITY,))
