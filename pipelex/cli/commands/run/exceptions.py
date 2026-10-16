"""Errors raised while loading pipeline-inputs files for the run CLI surfaces."""

from mthds.protocol.problem.registry import CoreCode

from pipelex.base_exceptions import PipelexError
from pipelex.cogt.inference.error_classification import UserAction, UserActionKind


class AmbiguousInputsFilesError(PipelexError):
    """Raised when a bundle directory holds both default inputs files on auto-detect.

    Auto-detection probes for both ``inputs.json`` and ``inputs.toml``; when both
    exist there is no safe pick, so the caller must choose explicitly.
    """

    error_code = CoreCode.REQUEST_INVALID
    user_action = UserAction(
        kind=UserActionKind.CHANGE_INPUT,
        detail="Pass --inputs explicitly to choose which inputs file to use",
    )
