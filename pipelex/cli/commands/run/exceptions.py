"""Errors raised while loading pipeline-inputs files for the run CLI surfaces."""

from pipelex.base_exceptions import ErrorDomain, PipelexError
from pipelex.cogt.inference.error_classification import UserAction, UserActionKind


class InputsTimeOnlyNotSupportedError(PipelexError):
    """Raised when a loaded inputs file carries a bare TOML time-of-day value.

    TOML date and datetime literals now map to the native ``Date`` concept, but a
    time of day alone has no date to attach to and no native concept, so the inputs
    loader rejects it. (Date/datetime values are accepted; only bare times are not.)
    """

    error_domain = ErrorDomain.INPUT
    user_action = UserAction(
        kind=UserActionKind.CHANGE_INPUT,
        # The example is an unquoted TOML datetime literal (which maps to Date); quoting it would make it
        # a string (Text), i.e. the "or quote as a string" fallback — the opposite of "include the date".
        detail="A time of day alone has no date to attach to. Include the date (e.g. 2026-07-06T12:00:00), or quote the value as a string",
    )
    # The message describes a fault in the caller's own inputs file — caller-facing copy.
    _authors_caller_facing_message = True


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
