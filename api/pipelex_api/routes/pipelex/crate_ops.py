"""Shared crate-resolution plumbing for the `/resolve`, `/codegen` and `/pipe-io` routes.

They all take a method the same way `/validate` and the run routes do — a tree sent in `files`, with its
`dependencies` and `resources`, XOR an address-form `method_ref` — read it with the same machinery
(`pipelex_api.routes.pipelex.method_selection`), write it out as a run writes it
(`pipelex_api.method_tree_request.written_method`), and resolve it through the same engine core
(`pipelex.pipeline.resolve_bundle.resolve_crate_from_method_dir`). The resolution is static: a package the method
calls by its address loads only when the request shipped it, in `dependencies` or under a fetched package's
`.mthds/methods/`, and one nothing shipped is the invalid verdict, never a lookup among the methods installed on this
server or a fetch. They speak the same verdict vocabulary as
`POST /validate`: a produced verdict is a 200 discriminated on `is_valid`, with the invalid arm carrying the
structured `errors[]` built by pipelex's one shared builder. This module holds the pieces they share so
the envelopes cannot drift.

The invalid arm here is the *crate* verdict: it deliberately omits `/validate`'s runnability facts
(`pending_signatures`, `is_runnable`) — resolution is static (no dry-run sweep, matching
`pipelex resolve`), so runnability is not part of its vocabulary. The per-pipe route (`/pipe-io`)
rides that same static core: it reads the selected pipe's *declared* IO with no dry-run sweep.

Writing the tree, loading it, projecting the crate and tearing the library down are blocking work, so they run in one
worker thread (`project_resolved_method`), never on the event loop: a slow resolution never stalls the server's other
requests, and the current library, a context variable, is bound, read and cleared in that one thread's context.
"""

import asyncio
from collections.abc import Callable
from enum import StrEnum
from typing import Literal, NamedTuple, NoReturn, TypeVar

from fastapi import Request
from fastapi.responses import JSONResponse
from mthds.protocol.problem.models import ProblemItem
from mthds.protocol.problem.registry import CoreCode
from pipelex.errors.problem import ProblemView
from pipelex.interpreter_hub import clear_current_library, get_current_library_id_or_none, get_library_manager, get_required_entry_pipe
from pipelex.libraries.library_crate import LibraryCrate
from pipelex.libraries.pipe.exceptions import EntryPipeAmbiguousError, EntryPipeNotFoundError, PipeNotFoundError
from pipelex.methods.method_ref import looks_like_method_ref
from pipelex.pipe_machinery.pipe_abstract import PipeAbstract
from pipelex.pipeline.exceptions import ValidateBundleError
from pipelex.pipeline.resolve_bundle import resolve_crate_from_method_dir
from pipelex.tools.typing.pydantic_utils import empty_list_factory_of
from pydantic import BaseModel, Field

from pipelex_api.exceptions import RunnerRequestError
from pipelex_api.method_tree_request import RequestMethod, WrittenMethod, manifest_of, written_method
from pipelex_api.routes.pipelex.method_selection import select_request_method
from pipelex_api.schemas.models import MethodTreeRequest

#: What a route makes of a resolved method, in the worker thread that holds it loaded.
ProjectionT = TypeVar("ProjectionT")

# The `reason` of the `request.unsupported` refusing a registry-form `method_ref`, which no registry here resolves.
REGISTRY_FORM_METHOD_REF_REASON = "registry_form_method_ref"


class GeneratedArtifact(BaseModel):
    """One generated file: its path relative to the client's chosen output root, and its full content."""

    path: str = Field(..., description="Artifact path, relative to the output root the client writes into.")
    content: str = Field(..., description="Complete file content, stamp header included — write verbatim.")


class CrateInvalidReport(BaseModel):
    """The 200 **invalid** arm shared by `/resolve`, `/codegen` and `/pipe-io` — the crate-verdict vocabulary.

    Same discipline as `/validate`'s `InvalidReport`: an invalid library is the *successful
    product* of a diagnostic call (the request was well-formed; the library was not), so it rides
    a 200 discriminated on `is_valid`, carrying the same problem items in `errors` that `/validate`
    emits for the identical failure.
    """

    is_valid: Literal[False] = False
    """Discriminant of the invalid arm (mirrors the valid arms' `Literal[True]`)."""

    errors: list[ProblemItem] = Field(
        default_factory=empty_list_factory_of(ProblemItem),
        description=(
            "One problem item per error, each with its own code, its parameters and its location — non-empty on every "
            "invalid verdict. The items of the verdict's problem, as a refusal's `errors` carry them."
        ),
    )
    message: str = Field(default="MTHDS library could not be resolved", description="Human-readable summary of the verdict.")


def invalid_crate_report_response(validate_error: ValidateBundleError, *, view: ProblemView) -> JSONResponse:
    """Render a produced "could not resolve" verdict as a 200 `CrateInvalidReport`.

    The items are those of the error's problem in the view of the request's reader (`ValidateBundleError.problem_items`,
    one per item of pipelex's one shared builder), and the message is its `detail`, the sentence its code renders, which
    reads the same in every view. `exclude_none` drops each item's unset members, as the standard writes a problem item.
    """
    problem = validate_error.to_problem(view=view)
    invalid_report = CrateInvalidReport(errors=list(problem.errors or []), message=problem.detail)
    return JSONResponse(content=invalid_report.model_dump(mode="json", serialize_as_any=True, by_alias=True, exclude_none=True))


class ResolvedMethod(NamedTuple):
    """A method resolved to its crate: the normalized crate, and the method's trees as the request named them."""

    crate: LibraryCrate
    """The normalized library crate the method's tree resolved to."""

    request_method: RequestMethod
    """The method's tree and its dependency trees, read in full, so a route echoes its bundles without reading it again."""

    method_label: str
    """How the entry rule's messages name the method: as sent in the request, or by the fetched package's address."""

    @property
    def manifest_main_pipe(self) -> str | None:
        """The `main_pipe` the `METHODS.toml` at the method tree's root declares, or None without one.

        A fetched package's manifest and a manifest sent in `files` alike, since both sit at the root of the tree.

        Raises:
            MethodEntryError: The manifest is not UTF-8 text, or not a valid manifest (a 422 in the input domain).
        """
        manifest = manifest_of(tree=self.request_method.tree, label=f"the method {self.method_label}", root="")
        return manifest.main_pipe if manifest is not None else None


def _resolve_written_method(*, written: WrittenMethod) -> LibraryCrate | ValidateBundleError:
    """The crate of a method written out, or the invalid verdict when it does not resolve."""
    try:
        return resolve_crate_from_method_dir(method_dir=written.method_dir, methods_dirs=written.methods_dirs)
    except ValidateBundleError as validate_error:
        # The produced negative verdict: the core already tore its library down.
        return validate_error


def _project_written_method(
    *,
    request_method: RequestMethod,
    method_label: str,
    project: Callable[[ResolvedMethod], ProjectionT],
) -> ProjectionT | ValidateBundleError:
    """Write the method out, resolve it, hand it to `project` while it is loaded, and release everything: blocking work.

    Runs whole in one worker thread, so the library the core binds as current in this thread's context is the one
    `project` reads and the one torn down here, however `project` exits.
    """
    with written_method(request_method=request_method) as written:
        resolution = _resolve_written_method(written=written)
        if isinstance(resolution, ValidateBundleError):
            return resolution
        try:
            return project(ResolvedMethod(crate=resolution, request_method=request_method, method_label=method_label))
        finally:
            teardown_current_library()


async def project_resolved_method(
    *,
    request: Request,
    request_data: MethodTreeRequest,
    project: Callable[[ResolvedMethod], ProjectionT],
) -> ProjectionT | ValidateBundleError:
    """Resolve the method the request names into its normalized crate, and return what `project` makes of it.

    The method is read as `/validate` reads it (`select_request_method`), then written out as a run writes it and loaded
    alone as the caller's own library directory, its dependency trees as the packages it ships, in a worker thread.
    `project` runs in that thread with the freshly opened library loaded and current, so it can read live pipes, and the
    written tree held; both are released when it returns or raises. A method that does not resolve returns its invalid
    verdict instead, the `ValidateBundleError` carrying the structured validation items, with `project` never called and
    nothing left loaded.

    Raises (as problem documents): a 422 `request.unsupported` for a registry-form `method_ref`; the refusals of
    `select_request_method`; the address-form fetch and location failures (`MethodRefError` subclasses); and whatever
    `project` raises, such as a selection refusal.
    """
    if request_data.method_ref is not None and not looks_like_method_ref(request_data.method_ref):
        msg = (
            "Registry-form method_ref resolution is not available on this server: no method registry is wired. "
            "Use an address-form reference (a `github.com/...` address, e.g. `github.com/Pipelex/methods/documents@v0.1.0`) "
            "or send the method's tree in `files`."
        )
        raise (
            RunnerRequestError(msg, field="method_ref")
            .with_error_code(CoreCode.REQUEST_UNSUPPORTED)
            .with_params(reason=REGISTRY_FORM_METHOD_REF_REASON)
        )
    selected = await select_request_method(
        request=request, method_ref=request_data.method_ref, resources=request_data.resources, read_scope=request_data.read_scope
    )
    return await asyncio.to_thread(
        _project_written_method,
        request_method=selected.request_method,
        method_label=selected.method_label,
        project=project,
    )


class RequestedPipe(NamedTuple):
    """The pipe a per-pipe route was asked for: its resolved qualified ref and the live pipe."""

    ref: str
    """The qualified `domain.pipe_code` actually selected — always qualified, whatever the request spelled."""

    pipe: PipeAbstract
    """The live pipe, read from the library `project_resolved_method` holds loaded + current."""


class PipeSelectionMissKind(StrEnum):
    """Why a selection chain link selected no pipe: the two failures the engine's entry lookup names."""

    NOT_FOUND = "not_found"
    AMBIGUOUS = "ambiguous"


class SelectorOrigin(StrEnum):
    """Where a pipe selector came from, which is what its refusal must tell the caller, and who must act on it."""

    REQUEST = "request"
    MANIFEST = "manifest"
    CLOSURE = "closure"


class PipeSelectionMiss(NamedTuple):
    """A link of the pipe selection chain that selected no pipe, with the refusal a selection answers."""

    kind: PipeSelectionMissKind
    """Which entry-lookup failure this is, which picks the pipelex error class the refusal is raised as."""

    message: str
    """The detail of the `422` a selection that depends on this link raises."""

    origin: SelectorOrigin | None
    """Where the selector that missed came from, which picks the refusal's code; `None` when there was no selector
    at all, because the request named no pipe and the closure declares no single `main_pipe`."""

    selector: str | None = None
    """The selector that missed, the request's `pipe_ref` or a declared `main_pipe`; `None` when there was none."""

    candidates: list[str] | None = None
    """The qualified refs of the `main_pipe`s the closure declares, when it declares several."""


def resolve_requested_pipe(crate: LibraryCrate, *, pipe_ref: str | None, manifest_main_pipe: str | None) -> RequestedPipe:
    """Select the pipe a per-pipe route targets, defaulting to the manifest's, then the closure's, `main_pipe`.

    The request's `pipe_ref` wins; omitted, the default chain (`select_default_pipe`) decides. Every
    failed selection — an unknown ref, an ambiguous one, a chain that finds no entry pipe or several —
    is an input-domain 422 rather than an invalid-crate verdict, since nothing about the *closure* is
    wrong in any of them. It is raised as the engine's own entry-lookup error class (see
    `_raise_selection_refusal`), so an unknown or ambiguous ref carries the code the run routes
    answer for the same `pipe_code`. A chain finding no entry pipe or several has no run-route twin to
    match: this route refuses both the way the pipe-selector design classifies them.

    Must be called from the `project` of `project_resolved_method`, while its library is loaded + current.
    """
    if pipe_ref is not None:
        selected = _select_entry_pipe(pipe_ref, origin=SelectorOrigin.REQUEST)
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
    with for an unknown or ambiguous `pipe_code`. The global `PipelexError` handler then renders its
    problem exactly as it renders the run routes' refusal: the code's status and sentences, filled
    with the parameters given here, the selector that missed and the candidates. The message built
    here rides the operator's diagnostics alone.

    The no-entry-pipe miss is a not-found and the several-`main_pipe`s miss an ambiguity, the way the
    pipe-selector design classifies them.

    The code says who must act, which is where the selector came from. A selector the request named that
    misses is the caller's (`request.pipe_not_found`, `request.pipe_ambiguous`), and so is a request naming no
    pipe where the closure gives no single `main_pipe` to default to (`request.pipe_unspecified`, naming as its
    `candidates` the `main_pipe`s the closure declares when it declares several, since there is then no selector
    for `request.pipe_ambiguous` to name). A `main_pipe` the method itself declares, in the fetched package's
    manifest or in the closure, is the method's, whose author fixes the declaration: one that names no pipe of
    the closure is `method.pipe_unresolved`, naming it as the `missing` pipe, and one that matches pipes in
    several domains is `method.ref_ambiguous`, naming it as the `ref` with its `candidates`, so the refusal
    never says a pipe that exists twice does not exist.
    """
    match miss.kind:
        case PipeSelectionMissKind.NOT_FOUND:
            match miss.origin:
                case SelectorOrigin.REQUEST:
                    raise (EntryPipeNotFoundError(miss.message).with_error_code(CoreCode.REQUEST_PIPE_NOT_FOUND).with_params(pipe=miss.selector))
                case SelectorOrigin.MANIFEST | SelectorOrigin.CLOSURE:
                    raise (EntryPipeNotFoundError(miss.message).with_error_code(CoreCode.METHOD_PIPE_UNRESOLVED).with_params(missing=miss.selector))
                case None:
                    raise (EntryPipeNotFoundError(miss.message).with_error_code(CoreCode.REQUEST_PIPE_UNSPECIFIED))
        case PipeSelectionMissKind.AMBIGUOUS:
            match miss.origin:
                case SelectorOrigin.REQUEST:
                    raise (
                        EntryPipeAmbiguousError(miss.message)
                        .with_error_code(CoreCode.REQUEST_PIPE_AMBIGUOUS)
                        .with_params(pipe=miss.selector, candidates=miss.candidates)
                    )
                case None:
                    raise (
                        EntryPipeAmbiguousError(miss.message)
                        .with_error_code(CoreCode.REQUEST_PIPE_UNSPECIFIED)
                        .with_params(candidates=miss.candidates)
                    )
                case SelectorOrigin.MANIFEST | SelectorOrigin.CLOSURE:
                    raise (
                        EntryPipeAmbiguousError(miss.message)
                        .with_error_code(CoreCode.METHOD_REF_AMBIGUOUS)
                        .with_params(ref=miss.selector, candidates=miss.candidates)
                    )


def select_default_pipe(crate: LibraryCrate, *, manifest_main_pipe: str | None) -> RequestedPipe | PipeSelectionMiss:
    """The selection chain without the request's `pipe_ref`: the method's own entry pipe, or why there is none.

    The precedence is the run routes' (the protocol's entry rule, `select_tree_entry`): the `main_pipe`
    of the `METHODS.toml` at the method tree's root, a fetched package's or one sent in `files`, is the
    method author's declared entry pipe and is taken first; only without one does the closure's own
    declaration decide. That last step mirrors `pipelex codegen inputs`
    (`inputs_cmd.py::_default_main_pipe_ref`): the single declared `main_pipe`, with **both**
    un-defaultable arms missed — a closure declaring none, and one declaring several across domains.
    The chain stops at the first link present, so a manifest `main_pipe` the closure does not
    declare, or declares in several domains, is a miss rather than a fall-through to the closure's
    declarations. A tree with no manifest at its root gets exactly the closure-declared default.

    It returns the miss instead of raising, so the one chain serves both `resolve_requested_pipe`
    (which refuses with the miss's message) and `/pipe-io`'s `default_pipe_ref` (which states `null`),
    and the selection and the reported default cannot drift apart. It is deliberately NOT
    `/validate`'s `default_pipe_ref`, which is the run default and names the first of several
    declaring domains where this chain refuses to choose.

    Must be called from the `project` of `project_resolved_method`, while its library is loaded + current.
    """
    if manifest_main_pipe:
        return _select_entry_pipe(manifest_main_pipe, origin=SelectorOrigin.MANIFEST)
    candidates = [f"{domain_code}.{domain.main_pipe}" for domain_code, domain in crate.domains.items() if domain.main_pipe]
    if not candidates:
        return PipeSelectionMiss(
            kind=PipeSelectionMissKind.NOT_FOUND,
            message="No `pipe_ref` was given and the closure declares no `main_pipe` — name the pipe explicitly.",
            origin=None,
        )
    if len(candidates) > 1:
        joined = ", ".join(sorted(candidates))
        return PipeSelectionMiss(
            kind=PipeSelectionMissKind.AMBIGUOUS,
            message=f"No `pipe_ref` was given and the closure declares several `main_pipe`s ({joined}) — name the pipe explicitly.",
            origin=None,
            candidates=sorted(candidates),
        )
    return _select_entry_pipe(candidates[0], origin=SelectorOrigin.CLOSURE)


def _select_entry_pipe(selector: str, *, origin: SelectorOrigin) -> RequestedPipe | PipeSelectionMiss:
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
        case SelectorOrigin.REQUEST:
            described = f"Pipe '{selector}'"
            scope = "the submitted closure"
        case SelectorOrigin.MANIFEST:
            # The caller never spelled this selector — say where it came from, or the 422 names a pipe out of nowhere.
            described = f"Pipe '{selector}' (the `main_pipe` of the method's manifest)"
            scope = "the method's closure"
        case SelectorOrigin.CLOSURE:
            described = f"Pipe '{selector}' (the closure's declared `main_pipe`)"
            scope = "the submitted closure"
    try:
        the_pipe = get_required_entry_pipe(pipe_code=selector)
    except EntryPipeAmbiguousError as exc:
        return PipeSelectionMiss(
            kind=PipeSelectionMissKind.AMBIGUOUS,
            message=f"{described} matches pipes in several domains of {scope}, so it selects none: {exc}",
            origin=origin,
            selector=selector,
            # The qualified refs the entry lookup found, which the refusal names to the caller.
            candidates=exc.given_params.get("candidates"),
        )
    except PipeNotFoundError as exc:
        return PipeSelectionMiss(
            kind=PipeSelectionMissKind.NOT_FOUND, message=f"{described} not found in {scope}: {exc}", origin=origin, selector=selector
        )
    return RequestedPipe(ref=the_pipe.pipe_ref, pipe=the_pipe)


def teardown_current_library() -> None:
    """Tear down the library the resolution left loaded + current, once its projection is done."""
    library_id = get_current_library_id_or_none()
    clear_current_library()
    if library_id is not None:
        get_library_manager().teardown(library_id=library_id)
