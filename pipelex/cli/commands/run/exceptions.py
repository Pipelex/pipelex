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
    # The message describes a fault in the caller's own bundle directory — caller-facing copy.
    _authors_caller_facing_message = True


class AutoDetectedInputsFileError(PipelexError):
    """Raised when the inputs file auto-detection finds in a bundle directory is not a regular file.

    Auto-detection reads ``inputs.json`` or ``inputs.toml`` only when it is a regular file, judged without
    following a link, so a symbolic link in a method's folder never carries data from outside the folder
    into a run; a directory or any other entry of either name is refused the same way.
    """

    error_code = CoreCode.REQUEST_INVALID
    user_action = UserAction(
        kind=UserActionKind.CHANGE_INPUT,
        detail="Replace it with the file itself, or name the inputs file with --inputs <path>",
    )
    # The message describes a fault in the caller's own bundle directory — caller-facing copy.
    _authors_caller_facing_message = True
