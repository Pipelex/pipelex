"""Errors raised while loading pipeline-inputs files for the run CLI surfaces."""

from pipelex.base_exceptions import ErrorDomain, PipelexError
from pipelex.cogt.inference.error_classification import UserAction, UserActionKind


class AmbiguousInputsFilesError(PipelexError):
    """Raised when a bundle directory holds both default inputs files on auto-detect.

    Auto-detection probes for both ``inputs.json`` and ``inputs.toml``; when both
    exist there is no safe pick, so the caller must choose explicitly.
    """

    error_domain = ErrorDomain.INPUT
    user_action = UserAction(
        kind=UserActionKind.CHANGE_INPUT,
        detail="Pass --inputs explicitly to choose which inputs file to use",
    )
    # The message describes a fault in the caller's own bundle directory — caller-facing copy.
    _authors_caller_facing_message = True
