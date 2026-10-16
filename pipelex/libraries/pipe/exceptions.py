from typing import ClassVar

from mthds.protocol.problem.registry import CoreCode

from pipelex.cogt.inference.error_classification import UserAction, UserActionKind
from pipelex.errors.error_code_declaration import ErrorCodeDeclaration, ErrorCodeSet
from pipelex.libraries.exceptions import LibraryError


class PipeLibraryError(LibraryError):
    """A pipe library that cannot hold the pipes it is given.

    The default ``method.name_conflict`` is two declarations of one pipe; a raise site chooses
    ``method.ref_ambiguous`` for a bare code matching several packages, ``method.signature_mismatch`` for a concrete
    pipe whose contract differs from its signature, ``request.unsupported`` for a form of request the resolve does not
    take, and ``runtime.unexpected`` for an invariant of the crate.
    """

    error_code: ClassVar[ErrorCodeDeclaration] = ErrorCodeSet(
        default=CoreCode.METHOD_NAME_CONFLICT,
        others=(CoreCode.METHOD_REF_AMBIGUOUS, CoreCode.METHOD_SIGNATURE_MISMATCH, CoreCode.REQUEST_UNSUPPORTED, CoreCode.RUNTIME_UNEXPECTED),
    )


class PipeNotFoundError(PipeLibraryError):
    """A pipe ref written inside a bundle that names no pipe the library holds."""

    error_code: ClassVar[ErrorCodeDeclaration] = CoreCode.METHOD_PIPE_UNRESOLVED


class EntryPipeNotFoundError(PipeNotFoundError):
    """An entry-shaped `pipe_code` — one a human typed — resolved to no pipe.

    The in-body sibling `PipeNotFoundError` reports a ref written inside a bundle, which is a fault
    of the loaded methods and stays unclassified. This one reports a code the caller supplied at an
    entry point (a CLI argument, the `pipe_code` field of a run request, the `--pipe` / `pipe_ref`
    slice selector of bundle validation), so it is the caller's own typo: ``request.pipe_not_found``, or
    ``request.pipe_unspecified`` where the caller named no pipe and the method declares no entry pipe. An entry pipe
    the method itself declares that names no pipe of the method chooses ``method.pipe_unresolved``.

    The message names only the caller's own `pipe_code`, and each raise site owes that invariant: a
    message here may name what the caller typed and nothing from the loaded library.
    """

    error_code = ErrorCodeSet(
        default=CoreCode.REQUEST_PIPE_NOT_FOUND,
        others=(CoreCode.REQUEST_PIPE_UNSPECIFIED, CoreCode.METHOD_PIPE_UNRESOLVED),
    )
    user_action = UserAction(
        kind=UserActionKind.CHANGE_INPUT,
        # Scope-neutral on purpose, because a class-level detail cannot name the scope its raise
        # sites work in and they do not share one: the entry lookup serves run, show and build as
        # much as validate, and misses because nothing loaded declares the code, while the `--pipe`
        # slice misses because the bundle being sliced does not declare it — even when another
        # loaded bundle does. Either wording that names one of those scopes is false at the other
        # site. Both raise sites carry a precise message of their own, so the detail only has to
        # stop asserting a scope it cannot know.
        detail="Check the pipe code for typos and make sure the bundle in scope for this operation declares it.",
    )


class EntryPipeAmbiguousError(PipeLibraryError):
    """An entry-shaped bare `pipe_code` matched pipes in several domains.

    Raised only by the entry lookup, which searches a bare code across domains precisely because a
    human typed it. Refusing to guess is the right answer, but it is the caller who picks the winner
    — ``request.pipe_ambiguous``, same reasoning as :class:`EntryPipeNotFoundError`; several entry pipes the method
    itself declares choose ``method.pipe_unresolved``.

    The message names the caller's own `pipe_code` and the qualified `pipe_ref`s of bundles they
    loaded themselves, the candidates being the only thing that makes the error actionable, and a raise
    site gives them as the code's `candidates` parameter, which the caller reads. That holds because the entry
    library carries only the caller's own bundles: the runner passes no `library_dirs` and no
    deployment sets `PIPELEXPATH`, so no host-private `.mthds` is merged into it. It is a property of
    how the runner is deployed, not a rule this class enforces — a deployment that did merge a host
    library would put host `pipe_ref`s in this message.
    """

    error_code = ErrorCodeSet(default=CoreCode.REQUEST_PIPE_AMBIGUOUS, others=(CoreCode.METHOD_PIPE_UNRESOLVED,))
    user_action = UserAction(
        kind=UserActionKind.CHANGE_INPUT,
        # Both spellings, because both raise sites reach this one detail: the bare-code arm is fixed by
        # 'domain.pipe_code', while the cross-package arm translated from the alias-scoped search needs
        # the alias too — a bare 'domain.pipe_code' does not reach a dependency pipe at all.
        detail="Name one candidate explicitly: 'domain.pipe_code', or 'alias->domain.pipe_code' for a cross-package code.",
    )
