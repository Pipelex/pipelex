from pipelex.base_exceptions import PipelexError


class BindingPathUnresolvedError(PipelexError):
    """A binding step's `from` path that the declared structures cannot walk.

    Raised by the derivation walk, which knows nothing of the sequence holding the step: the sequence turns
    it into a `binding_path_unresolved` validation error naming itself. The message names the segment that
    failed and the fields that were available there, so a typo can be repaired from the message alone.
    """

    def __init__(self, message: str, *, path: str, failed_segment: str, available_fields: list[str]):
        self.path = path
        self.failed_segment = failed_segment
        self.available_fields = available_fields
        super().__init__(message)


class BindingStepRunError(PipelexError):
    """A binding step that could not bind its value at run time, although its path was derived before the run.

    The derivation walk vouches for the path, so this signals a value whose shape contradicts its concept's
    declared structure, such as an attribute the declared field promised and the value lacks.
    """
