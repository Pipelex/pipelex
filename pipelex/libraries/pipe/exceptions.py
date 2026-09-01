from pipelex.base_exceptions import ErrorDomain
from pipelex.cogt.inference.error_classification import UserAction, UserActionKind
from pipelex.libraries.exceptions import LibraryError


class PipeLibraryError(LibraryError):
    pass


class PipeNotFoundError(PipeLibraryError):
    pass


class EntryPipeNotFoundError(PipeNotFoundError):
    """An entry-shaped `pipe_code` — one a human typed — resolved to no pipe.

    The in-body sibling `PipeNotFoundError` reports a ref written inside a bundle, which is a fault
    of the loaded methods and stays unclassified. This one reports a code the caller supplied at an
    entry point (a CLI argument, the `pipe_code` field of a run request), so it is the caller's own
    typo: INPUT domain, which every presentation derives from at once — 422 rather than a 500 that
    reads as retryable to every SDK.

    Caller-facing copy: the message names only the caller's own `pipe_code`, so STRICT disclosure
    keeps it verbatim. The flag spans every raise site of the class, and this class has exactly one.
    """

    error_domain = ErrorDomain.INPUT
    user_action = UserAction(
        kind=UserActionKind.CHANGE_INPUT,
        detail="Check the pipe code for typos and make sure the bundle declaring it is loaded.",
    )
    _declared_title = "Entry pipe not found"
    _authors_caller_facing_message = True


class EntryPipeAmbiguousError(PipeLibraryError):
    """An entry-shaped bare `pipe_code` matched pipes in several domains.

    Raised only by the entry lookup, which searches a bare code across domains precisely because a
    human typed it. Refusing to guess is the right answer, but it is the caller who picks the winner
    — INPUT domain, same reasoning as :class:`EntryPipeNotFoundError`.

    Caller-facing copy: the message names the caller's own `pipe_code` and the qualified `pipe_ref`s
    of bundles they loaded themselves, so it survives STRICT disclosure intact — and it has to, since
    the candidates are the only thing that makes the error actionable.
    """

    error_domain = ErrorDomain.INPUT
    user_action = UserAction(
        kind=UserActionKind.CHANGE_INPUT,
        detail="Name one of the listed candidates explicitly, as 'domain.pipe_code'.",
    )
    _declared_title = "Entry pipe ambiguous"
    _authors_caller_facing_message = True
