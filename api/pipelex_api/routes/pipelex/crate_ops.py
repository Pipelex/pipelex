"""Shared crate-resolution plumbing for the `/resolve`, `/codegen` and `/pipe-io` routes.

They all select a closure the same way (inline `files[]` XOR `method_ref`), resolve it through the
same engine core (`pipelex.pipeline.resolve_bundle.resolve_crate_from_contents`), and speak the same
verdict vocabulary as `POST /validate`: a produced verdict is a 200 discriminated on `is_valid`, with
the invalid arm carrying the structured `validation_errors[]` built by pipelex's one shared builder.
This module holds the pieces they share so the envelopes cannot drift.

The invalid arm here is the *crate* verdict: it deliberately omits `/validate`'s runnability facts
(`pending_signatures`, `is_runnable`) — resolution is static (no dry-run sweep, matching
`pipelex resolve`), so runnability is not part of its vocabulary. The per-pipe route (`/pipe-io`)
rides that same static core: it reads the selected pipe's *declared* IO with no dry-run sweep.
"""

from enum import StrEnum
from typing import Literal, NamedTuple, NoReturn

from fastapi.responses import JSONResponse
from pipelex.base_exceptions import ErrorReport, ValidationErrorItem
from pipelex.cogt.inference.error_classification import UserAction, UserActionKind
from pipelex.interpreter_hub import clear_current_library, get_current_library_id_or_none, get_library_manager, get_required_entry_pipe
from pipelex.libraries.library_crate import LibraryCrate
from pipelex.libraries.pipe.exceptions import EntryPipeAmbiguousError, EntryPipeNotFoundError, PipeNotFoundError
from pipelex.methods.method_ref import looks_like_method_ref
from pipelex.pipe_machinery.pipe_abstract import PipeAbstract
from pipelex.pipeline.resolve_bundle import resolve_crate_from_contents
from pipelex.tools.typing.pydantic_utils import empty_list_factory_of
from pydantic import BaseModel, Field

from pipelex_api.error_types import ErrorType
from pipelex_api.errors import raise_not_implemented
from pipelex_api.method_source import fetch_method_mthds_files
from pipelex_api.schemas.models import MthdsFileItem, MthdsFilesRequest


class GeneratedArtifact(BaseModel):
    """One generated file: its path relative to the client's chosen output root, and its full content."""

    path: str = Field(..., description="Artifact path, relative to the output root the client writes into.")
    content: str = Field(..., description="Complete file content, stamp header included — write verbatim.")


class CrateInvalidReport(BaseModel):
    """The 200 **invalid** arm shared by `/resolve` and `/codegen` — the crate-verdict vocabulary.

    Same discipline as `/validate`'s `InvalidReport`: an invalid library is the *successful
    product* of a diagnostic call (the request was well-formed; the library was not), so it rides
    a 200 discriminated on `is_valid`, carrying the same structured `ValidationErrorItem`s the
    local CLI and `/validate` emit for the identical failure.
    """

    is_valid: Literal[False] = False
    """Discriminant of the invalid arm (mirrors the valid arms' `Literal[True]`)."""

    validation_errors: list[ValidationErrorItem] = Field(
        default_factory=empty_list_factory_of(ValidationErrorItem),
        description="Per-error diagnostics, built by pipelex's one shared builder — non-empty on every invalid verdict.",
    )
    message: str = Field(default="MTHDS library could not be resolved", description="Human-readable summary of the verdict.")


def invalid_crate_report_response(error_report: ErrorReport) -> JSONResponse:
    """Render a produced "could not resolve" verdict as a 200 `CrateInvalidReport`.

    `exclude_none` drops each item's unset locators so the wire items match the agent CLI's
    byte-for-byte — the "one error item, two surfaces" guarantee `/validate` already keeps.
    """
    invalid_report = CrateInvalidReport(
        validation_errors=error_report.validation_errors or [],
        message=error_report.message,
    )
    return JSONResponse(content=invalid_report.model_dump(mode="json", serialize_as_any=True, by_alias=True, exclude_none=True))


class SelectedFiles(NamedTuple):
    """What the closure selector resolved to: the files, plus the fetched manifest's entry pipe when there is one."""

    files: list[MthdsFileItem]
    """The `.mthds` files forming the closure — inline `files[]` verbatim, or the fetched package's."""

    manifest_main_pipe: str | None
    """The fetched package manifest's `main_pipe` (a bare pipe code). Always None for inline `files[]`, which carry no manifest."""


def selected_files(request_data: MthdsFilesRequest) -> SelectedFiles:
    """The files the closure selector names: inline `files[]`, or an address `method_ref`'s package.

    Every route on the `files[]` envelope reaches it through `resolve_requested_crate`, so they all
    give the same answer on every selector.

    An **address-form** `method_ref` (`github.com/<owner>/<repo>[/<selector>][@<tag>]`) resolves
    through the same fetch path the run routes use: the package's `.mthds` files come back as
    `files[]` items with their real relative paths as per-file sources, and the manifest's
    `main_pipe` rides beside them so the per-pipe route can default its selector the way a run
    by address does. Only `.mthds` data travels — the package's Python (if any) never loads
    on these routes. The **registry form** (any non-address reference) stays reserved and keeps
    its 501 until the packaging program's registry phase.

    Raises:
        ApiError: 501 for a registry-form `method_ref`; 422 for a fetched package this server
            cannot accept.
        MethodRefError subclasses: parse, fetch, location, and bounds failures on the address
            form, rendered as `problem+json` by the global handler.
    """
    if request_data.method_ref is not None:
        if looks_like_method_ref(request_data.method_ref):
            fetched = fetch_method_mthds_files(request_data.method_ref)
            return SelectedFiles(files=fetched.files, manifest_main_pipe=fetched.main_pipe)
        raise_not_implemented(
            "Registry-form method_ref resolution is not available on this server: no method registry is wired. "
            "Use an address-form reference (a `github.com/...` address, e.g. `github.com/Pipelex/methods/documents@v0.1.0`) "
            "or submit inline `files[]`.",
            error_type=ErrorType.METHOD_REF_NOT_SUPPORTED,
        )
    return SelectedFiles(files=request_data.files or [], manifest_main_pipe=None)


class ResolvedClosure(NamedTuple):
    """A resolved closure: its normalized crate, the files it was resolved from, and the fetched manifest's entry pipe."""

    crate: LibraryCrate
    """The normalized library crate the closure resolved to."""

    files: list[MthdsFileItem]
    """The `.mthds` files the crate was resolved from, carried through from `selected_files` so no route fetches twice."""

    manifest_main_pipe: str | None
    """The fetched package manifest's `main_pipe`, carried through from `selected_files` (None for inline `files[]`)."""


def resolve_requested_crate(request_data: MthdsFilesRequest) -> ResolvedClosure:
    """Resolve the request's closure selector into a normalized library crate.

    Inherits the engine core's **loaded-on-success contract**: on success the freshly opened
    library is loaded and current (so a route can read live pipes from it) and the route owns its
    teardown — call `teardown_current_library()` in a `finally`. On failure the core has already
    torn down and restored.

    The fetched manifest's `main_pipe` (when the selector was a `method_ref`) rides beside the
    crate so a per-pipe route can hand it to `resolve_requested_pipe` — the crate itself only
    knows the domains' own `main_pipe` declarations. The selected files ride beside it too, so a
    route that echoes the closure (`/pipe-io` with `include_files`) reads them here rather than
    calling `selected_files` again, which would fetch a `method_ref` a second time.

    Raises:
        ValidateBundleError: the produced negative verdict (route maps it to the 200 invalid arm).
        ApiError: 501 for a registry-form `method_ref` (see `selected_files`).
        MethodRefError subclasses: address-form fetch/location failures (see `selected_files`).
    """
    selection = selected_files(request_data)
    crate = resolve_crate_from_contents(
        mthds_contents=[item.content for item in selection.files],
        mthds_sources=[item.source for item in selection.files],
    )
    return ResolvedClosure(crate=crate, files=selection.files, manifest_main_pipe=selection.manifest_main_pipe)


class RequestedPipe(NamedTuple):
    """The pipe a per-pipe route was asked for: its resolved qualified ref and the live pipe."""

    ref: str
    """The qualified `domain.pipe_code` actually selected — always qualified, whatever the request spelled."""

    pipe: PipeAbstract
    """The live pipe, read from the library `resolve_requested_crate` left loaded + current."""


class PipeSelectionMissKind(StrEnum):
    """Why a selection chain link selected no pipe: the two failures the engine's entry lookup names."""

    NOT_FOUND = "not_found"
    AMBIGUOUS = "ambiguous"


class PipeSelectionMiss(NamedTuple):
    """A link of the pipe selection chain that selected no pipe, with the refusal a selection answers."""

    kind: PipeSelectionMissKind
    """Which entry-lookup failure this is, which picks the pipelex error class the refusal is raised as."""

    message: str
    """The detail of the `422` a selection that depends on this link raises."""

    user_action: UserAction | None = None
    """The fix to name instead of the error class's own, when the class's is wrong for this miss."""


class _SelectorOrigin(StrEnum):
    """Where a pipe selector came from, which is what its refusal must tell the caller."""

    REQUEST = "request"
    MANIFEST = "manifest"
    CLOSURE = "closure"


def resolve_requested_pipe(crate: LibraryCrate, *, pipe_ref: str | None, manifest_main_pipe: str | None) -> RequestedPipe:
    """Select the pipe a per-pipe route targets, defaulting to the manifest's, then the closure's, `main_pipe`.

    The request's `pipe_ref` wins; omitted, the default chain (`select_default_pipe`) decides. Every
    failed selection — an unknown ref, an ambiguous one, a chain that finds no entry pipe or several —
    is an input-domain 422 rather than an invalid-crate verdict, since nothing about the *closure* is
    wrong in any of them. It is raised as the engine's own entry-lookup error class (see
    `_raise_selection_refusal`), so an unknown or ambiguous ref carries the `error_type` the run routes
    answer for the same `pipe_code`. A chain finding no entry pipe or several has no run-route twin to
    match: this route refuses both the way the pipe-selector design classifies them.

    Must be called while the library `resolve_requested_crate` opened is still loaded + current.
    """
    if pipe_ref is not None:
        selected = _select_entry_pipe(pipe_ref, origin=_SelectorOrigin.REQUEST)
    else:
        selected = select_default_pipe(crate, manifest_main_pipe=manifest_main_pipe)
    if isinstance(selected, PipeSelectionMiss):
        _raise_selection_refusal(selected)
    return selected


def _raise_selection_refusal(miss: PipeSelectionMiss) -> NoReturn:
    """Raise a selection miss as the pipelex entry-lookup error class that names its failure.

    A selection refusal must not share `ValidationError` with a malformed request, or a client has no
    field to tell the two apart. So it is raised as `EntryPipeNotFoundError` or
    `EntryPipeAmbiguousError`, the classes the engine's entry lookup raises and the run routes answer
    with for an unknown or ambiguous `pipe_code`. The global `PipelexError` handler then renders it —
    the class name as `error_type`, the INPUT domain as a 422, the class's `user_action` — exactly as
    it renders the run routes' refusal. Both classes declare their messages caller-facing, which every
    message built here honours: it names the caller's selector, the manifest's `main_pipe`, or the
    qualified refs of the closure the caller submitted, and nothing from a host library.

    The no-entry-pipe miss is a not-found and the several-`main_pipe`s miss an ambiguity, the way the
    pipe-selector design classifies them. Neither is a typo in a pipe code, so each carries its own
    `user_action`, which replaces the class's code-typo advice for that one error.
    """
    match miss.kind:
        case PipeSelectionMissKind.NOT_FOUND:
            raise EntryPipeNotFoundError(miss.message).as_caller_fault(user_action=miss.user_action)
        case PipeSelectionMissKind.AMBIGUOUS:
            raise EntryPipeAmbiguousError(miss.message).as_caller_fault(user_action=miss.user_action)


def select_default_pipe(crate: LibraryCrate, *, manifest_main_pipe: str | None) -> RequestedPipe | PipeSelectionMiss:
    """The selection chain without the request's `pipe_ref`: the method's own entry pipe, or why there is none.

    The precedence is the run routes' (`pipeline.py`: `pipe_code or fetched.main_pipe`): a fetched
    package's manifest `main_pipe` is the package author's declared entry pipe and is taken first;
    only without one does the closure's own declaration decide. That last step mirrors `pipelex
    codegen inputs` (`inputs_cmd.py::_default_main_pipe_ref`): the single declared `main_pipe`, with
    **both** un-defaultable arms missed — a closure declaring none, and one declaring several across
    domains. The chain stops at the first link present, so a manifest `main_pipe` the closure does
    not declare, or declares in several domains, is a miss rather than a fall-through to the
    closure's declarations. Inline `files[]` carry no manifest, so for them the chain is exactly the
    closure-declared default.

    It returns the miss instead of raising, so the one chain serves both `resolve_requested_pipe`
    (which refuses with the miss's message) and `/pipe-io`'s `default_pipe_ref` (which states `null`),
    and the selection and the reported default cannot drift apart. It is deliberately NOT
    `/validate`'s `default_pipe_ref`, which is the run default and names the first of several
    declaring domains where this chain refuses to choose.

    Must be called while the library `resolve_requested_crate` opened is still loaded + current.
    """
    if manifest_main_pipe:
        return _select_entry_pipe(manifest_main_pipe, origin=_SelectorOrigin.MANIFEST)
    candidates = [f"{domain_code}.{domain.main_pipe}" for domain_code, domain in crate.domains.items() if domain.main_pipe]
    if not candidates:
        return PipeSelectionMiss(
            kind=PipeSelectionMissKind.NOT_FOUND,
            message="No `pipe_ref` was given and the closure declares no `main_pipe` — name the pipe explicitly.",
            user_action=UserAction(
                kind=UserActionKind.CHANGE_INPUT,
                detail="Send a `pipe_ref` naming the pipe to select, since the closure declares no `main_pipe` to default to.",
            ),
        )
    if len(candidates) > 1:
        joined = ", ".join(sorted(candidates))
        return PipeSelectionMiss(
            kind=PipeSelectionMissKind.AMBIGUOUS,
            message=f"No `pipe_ref` was given and the closure declares several `main_pipe`s ({joined}) — name the pipe explicitly.",
            user_action=UserAction(
                kind=UserActionKind.CHANGE_INPUT,
                detail="Send a `pipe_ref` naming one of the declared `main_pipe`s.",
            ),
        )
    return _select_entry_pipe(candidates[0], origin=_SelectorOrigin.CLOSURE)


def _select_entry_pipe(selector: str, *, origin: _SelectorOrigin) -> RequestedPipe | PipeSelectionMiss:
    """Look one selector up through the engine's entry lookup, the way every selection chain link does.

    The returned `ref` is read back off the **resolved pipe**, never echoed from the selector: the
    engine's entry lookup accepts a bare code too (falling back across domains), so a caller that
    submits `"echo"` must still be told `"smoke.echo"` — the valid arms promise a qualified ref, and
    echoing the request back would quietly break that promise for exactly the callers who leaned on
    the fallback. A manifest `main_pipe` is always a bare code, so it rides that same fallback.

    A bare code declared in several domains resolves to no pipe rather than to a first match, and
    the miss says so — it names the candidates the engine lists — instead of calling the pipe
    missing, which would contradict the candidates in the same sentence.
    """
    match origin:
        case _SelectorOrigin.REQUEST:
            described = f"Pipe '{selector}'"
            scope = "the submitted closure"
        case _SelectorOrigin.MANIFEST:
            # The caller never spelled this selector — say where it came from, or the 422 names a pipe out of nowhere.
            described = f"Pipe '{selector}' (the fetched package manifest's `main_pipe`)"
            scope = "the package's closure"
        case _SelectorOrigin.CLOSURE:
            described = f"Pipe '{selector}' (the closure's declared `main_pipe`)"
            scope = "the submitted closure"
    try:
        the_pipe = get_required_entry_pipe(pipe_code=selector)
    except EntryPipeAmbiguousError as exc:
        return PipeSelectionMiss(
            kind=PipeSelectionMissKind.AMBIGUOUS,
            message=f"{described} matches pipes in several domains of {scope}, so it selects none: {exc}",
        )
    except PipeNotFoundError as exc:
        return PipeSelectionMiss(kind=PipeSelectionMissKind.NOT_FOUND, message=f"{described} not found in {scope}: {exc}")
    return RequestedPipe(ref=the_pipe.pipe_ref, pipe=the_pipe)


def teardown_current_library() -> None:
    """Tear down the library `resolve_requested_crate` left loaded + current (success-path cleanup)."""
    library_id = get_current_library_id_or_none()
    clear_current_library()
    if library_id is not None:
        get_library_manager().teardown(library_id=library_id)
