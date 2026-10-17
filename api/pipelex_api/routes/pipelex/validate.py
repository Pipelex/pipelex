import asyncio
from enum import StrEnum
from typing import Annotated, Any, Literal, Self, Union

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse
from mthds.protocol.problem.models import ProblemItem
from pipelex.errors.bundle_validation_failure import BundleValidationFailure
from pipelex.errors.problem import ProblemView, caller_view_of
from pipelex.pipe_machinery.pipe_factory import PipeFactory
from pipelex.pipeline.exceptions import MethodEntryError, ValidateBundleError
from pipelex.pipeline.input_form import PipeInputFormDescriptor, PipeOutputFormDescriptor
from pipelex.pipeline.method_entry import MethodEntry
from pipelex.pipeline.validation_errors import warning_problem_items
from pipelex.pipeline.validation_render import format_validate_markdown, render_invalid_validation_markdown
from pipelex.pipeline.validation_report import PipelexValidationReport
from pipelex.system.storage_scope import validate_read_scope
from pipelex.tools.typing.pydantic_utils import empty_list_factory_of
from pydantic import BaseModel, Field, field_validator, model_validator

from pipelex_api.blob_store import RunnerBlobStore
from pipelex_api.bundle_resources import decode_bundle_resources
from pipelex_api.exception_handlers import problem_response
from pipelex_api.exceptions import CustomCodeOrigin, RunnerRequestError
from pipelex_api.json_body import JsonBodyRoute
from pipelex_api.method_source import fetched_method
from pipelex_api.method_tree_request import (
    REQUEST_METHOD_LABEL,
    RequestMethod,
    ensure_method_holds_a_bundle,
    ensure_python_allowed,
    read_request_method,
    record_request_method,
    select_tree_entry,
    tree_documents_of,
    with_resources,
    written_method,
)
from pipelex_api.middleware import request_id_of
from pipelex_api.openapi_responses import PROBLEM_404_METHOD_PACKAGE, PROBLEM_501_RUN_POLICY
from pipelex_api.problem_view import problem_view_of
from pipelex_api.routes.pipelex.pipeline import ApiRunner, get_request_user_id, resolve_blob_scope
from pipelex_api.schemas.models import RESOURCES_FIELD_DESCRIPTION, CallerAnalyticsGroupsMixin, MthdsContentsRequest

router = APIRouter(tags=["validate"], route_class=JsonBodyRoute)


class RenderFormat(StrEnum):
    """The closed set of server-side **supported** presentation formats for `/validate`.

    This is the supported-set vocabulary the route resolves request `render` tokens against —
    NOT the request-body type (the request stays `list[str]` so an unknown token is lenient-ignored,
    not 422'd). A Pipelex-API presentation concern (D-D): never the neutral protocol body.
    """

    MARKDOWN = "markdown"


def _resolve_render_formats(render: list[str]) -> set[RenderFormat]:
    """Resolve raw `render` tokens to the supported `RenderFormat` set (deduped, order-insensitive).

    Unknown/unsupported tokens are silently dropped (lenient-ignore, per-token): `render` is a
    presentation hint, not part of the verdict contract, so a stale view token never fails the call.
    """
    supported_values = {render_format.value for render_format in RenderFormat}
    return {RenderFormat(token) for token in render if token in supported_values}


class ValidationView(StrEnum):
    """The closed set of server-side **supported** structured views for `/validate`.

    The second opt-in axis beside `render`, with identical mechanics (raw `list[str]` request field,
    per-token resolution, lenient-ignore) but a different product: `render` yields *rendered text*
    under a mechanical `rendered_<format>` key, while a view attaches a *structured* artifact under a
    **same-named** top-level field. The two lists stay separate and independent — a request may carry
    both, and each resolves its own tokens against its own supported set.
    """

    INPUT_FORM = "input_form"
    OUTPUT_FORM = "output_form"


def _resolve_validation_views(views: list[str]) -> set[ValidationView]:
    """Resolve raw `views` tokens to the supported `ValidationView` set (deduped, order-insensitive).

    Unknown/unsupported tokens are silently dropped (lenient-ignore, per-token), exactly as for
    `render`: a view is an opt-in projection of facts the verdict already determined, never part of
    the verdict contract, so a stale view token must never fail the call with a 422.
    """
    supported_values = {view.value for view in ValidationView}
    return {ValidationView(token) for token in views if token in supported_values}


class ValidateRequest(MthdsContentsRequest, CallerAnalyticsGroupsMixin):
    """The shared `mthds_contents` + `allow_signatures` payload, plus optional per-file sources.

    `mthds_sources`, when provided, pairs each `mthds_contents[i]` with a logical source (e.g. the
    file's path relative to the submitted directory). The runner threads it onto
    `blueprint.source`, so the problem items in `errors` on a 200 `InvalidReport` carry a real
    `location.file` the client maps back to the owning file — without it the in-memory load path
    leaves the file unknown and cross-file diagnostics misfire. Omit it and behavior is unchanged.
    """

    mthds_sources: list[str] | None = Field(
        default=None,
        description=(
            "Optional per-file sources, parallel to `mthds_contents`. When provided, each entry is threaded "
            "onto the corresponding bundle's `source` so server-side validation errors carry a `source` pointing "
            "at the owning file. Must match `mthds_contents` in length when present."
        ),
    )
    resources: dict[str, str] | None = Field(default=None, description=RESOURCES_FIELD_DESCRIPTION)
    render: list[str] = Field(
        default_factory=list,
        description=(
            "Opt-in Pipelex-API presentation extra: view formats to render server-side. A supported token "
            "(`markdown`) adds a `rendered_<format>` field (e.g. `rendered_markdown`) to the 200 verdict, on both "
            "the valid and invalid arms. Unknown/unsupported tokens are silently ignored (presentation hint, not "
            "part of the verdict contract); the default empty list renders nothing and the response is unchanged."
        ),
    )
    views: list[str] = Field(
        default_factory=list,
        description=(
            "Opt-in Pipelex-API structured views: extra projections to attach to the 200 verdict. A supported token "
            "(`input_form`, `output_form`) adds a **same-named** top-level field to the valid arm only. Unknown/unsupported tokens are "
            "silently ignored (a view is a projection of facts the verdict already determined, not part of the verdict "
            "contract); the default empty list attaches nothing and the response is byte-identical to a request that "
            "omits the field. Independent of `render`: a request may carry both, each resolving its own tokens."
        ),
    )
    orchestration_mode: str | None = Field(
        default=None,
        description=(
            "Optional per-request orchestration-mode (backend) override for the validation dispatch (same plumbing as "
            "`/start`). An OPEN string token: `direct` validates in-process; a `temporal` mode dispatches the whole "
            "job to a worker; any plugin-provided token is accepted and an unregistered one is refused at dispatch. "
            "Honored only when the deployment sets `allow_request_orchestration_mode_override = true` in its `api.toml`; "
            "otherwise a token that differs from the deployment default is refused with a 422 "
            "`pipelex.deployment.orchestration_override_forbidden`. Omitted → the default."
        ),
    )

    read_scope: str | None = Field(
        default=None,
        description=(
            "PIPELEX-API EXTENSION (not part of the MTHDS Protocol) — the scope of the blob store a hash entry of `files` "
            "resolves in, as a run's `read_scope`: a multi-tenant host sends the one of the organization it serves. Omit it "
            "and the caller's own id is the scope."
        ),
    )

    @field_validator("read_scope")
    @classmethod
    def _validate_read_scope(cls, value: str | None) -> str | None:
        if value is None:
            return None
        return validate_read_scope(value=value)

    @model_validator(mode="after")
    def _sources_match_contents(self) -> Self:
        # `mthds_sources` labels INLINE contents; a method tree's files are named by their tree paths, so pairing the
        # two is a request-shape bug → 422.
        if self.mthds_sources is not None and self.mthds_contents is None:
            msg = "mthds_sources accompanies inline mthds_contents; the files of a method tree are named by their tree paths"
            raise ValueError(msg)
        # `resources` are the files the inline contents' steps read; a `method_ref`'s files are the package's own.
        if self.resources and self.method_ref is not None:
            msg = "resources accompany inline mthds_contents; a method_ref's files are the package's own"
            raise ValueError(msg)
        # A caller-supplied length mismatch is a request-shape bug → caught here as a 422.
        # Without this guard it reaches the runtime's `validate_bundle`, which treats the
        # mismatch as an internal host error (500) — the wrong status for caller input.
        if self.mthds_sources is not None and self.mthds_contents is not None and len(self.mthds_sources) != len(self.mthds_contents):
            msg = "mthds_sources, when provided, must be a per-item source list matching mthds_contents in length"
            raise ValueError(msg)
        return self


def _effective_default_pipe_ref(report: PipelexValidationReport) -> str | None:
    """The qualified ref of the pipe a selector-less run of inline contents would execute.

    The run routes' precedence for inline contents, minus the request selector `/validate` does not have: the
    closure's own declaration, the batch's primary blueprint's `main_pipe` (`select_primary_blueprint`), qualified by
    its domain. The report's `bundle_blueprint` IS that first declaring blueprint (`build_validation_report` selects it
    through the same `select_primary_blueprint`), so qualifying its `main_pipe` reproduces the run's own choice. A
    method tree's default is its entry pipe instead, by the protocol's rule (`select_tree_entry`).
    """
    blueprint = report.bundle_blueprint
    if not blueprint.main_pipe:
        return None
    return PipeFactory.make_pipe_ref_with_domain(domain_code=blueprint.domain, pipe_code=blueprint.main_pipe)


def _bundle_texts(*, request_method: RequestMethod) -> list[str]:
    """The texts of a method tree's `.mthds` bundles, in tree path order, as the valid verdict echoes them."""
    tree = request_method.tree
    return [tree.contents[tree_path].decode("utf-8", errors="replace") for tree_path in tree.bundle_paths]


def _optional_tree_entry(*, request_method: RequestMethod, method_label: str) -> MethodEntry | None:
    """The method's entry pipe, or None when it has none or a bundle does not parse, for the verdict to say why.

    A validation needs no entry pipe: a method without one validates, and its verdict carries no graph and no
    `default_pipe_ref`.
    """
    try:
        return select_tree_entry(tree=request_method.tree, method_label=method_label)
    except (ValidateBundleError, MethodEntryError):
        return None


class ValidReport(PipelexValidationReport):
    """The 200 **valid** arm: the canonical `PipelexValidationReport` plus this server's wire-only extras.

    The report fields are inherited — typed models, identical to what the local runtime
    returns for the same bundle, with `is_valid: Literal[True]` (from the report) as the union
    discriminant. The extras exist for HTTP clients only (the webapp reads back `mthds_contents`);
    they are NOT part of the canonical report and no in-process consumer should depend on them.

    `warnings` is re-declared as problem items: the canonical report holds the advisory findings as the validation
    items the local channels render, and the wire carries each as the problem item its type's code makes
    (`pipelex.pipeline.validation_errors.warning_problem_items`), the item shape `errors` has on the invalid arm.

    Two inherited fields are deliberately re-declared: `input_form` and `output_form`. The canonical
    report requires both (a backend that forgets to derive one must fail loudly rather than ship an
    empty view), but on the wire each is an opt-in structured view gated by the request's `views` —
    so both are re-declared with defaults here, keeping them out of the published schema's `required`
    set. The values still always arrive from the report; the route pops each when its token was not
    requested. They are separate tokens rather than one because they answer separate questions: a
    caller building a fill-in form wants the inputs, a caller rendering a result or registering a
    tool signature wants the output, and neither should pay for the other.
    """

    mthds_contents: list[str] = Field(
        ...,
        description=(
            "The MTHDS contents that were validated: the request's `mthds_contents`, or the texts of a method tree's "
            "`.mthds` bundles in tree path order."
        ),
    )
    warnings: list[ProblemItem] = Field(  # type: ignore[assignment]  # pyright: ignore[reportIncompatibleVariableOverride]
        default_factory=empty_list_factory_of(ProblemItem),
        description=(
            "Advisory findings on the valid bundle, one problem item each, with the code the finding's type names: they "
            "never flip `is_valid`. The same item shape as the invalid arm's `errors`."
        ),
    )
    message: str = Field(default="MTHDS content validated successfully", description="Status message")
    default_pipe_ref: str | None = Field(
        default=None,
        description=(
            "The qualified `domain.pipe_code` a caller gets by omitting the pipe selector — the pipe a "
            "selector-less run of THIS request would execute. For a method tree (`files` or a `method_ref`) it is "
            "the tree's entry pipe by the MTHDS protocol's rule: the `main_pipe` of the `METHODS.toml` at its root, "
            "else the one `main_pipe` its bundles declare. For inline `mthds_contents` it is the closure's primary "
            "blueprint's `main_pipe` qualified by its domain. Absent when no entry pipe is determined, in which case a "
            "selector-less run would be refused too."
        ),
    )
    input_form: dict[str, PipeInputFormDescriptor] = Field(
        default_factory=dict,
        description=(
            "Opt-in Pipelex-API structured view: per-pipe input-form descriptors keyed exactly like `pipe_io_contracts`, "
            "present only when the request's `views` includes `input_form`. Absent by default — the structured contract "
            "fields remain the verdict; this is a projection of them."
        ),
    )
    output_form: dict[str, PipeOutputFormDescriptor] = Field(
        default_factory=dict,
        description=(
            "Opt-in Pipelex-API structured view: per-pipe output-form descriptors keyed exactly like `pipe_io_contracts`, "
            "present only when the request's `views` includes `output_form`. Absent by default. Read with the output "
            "contract's `json_schema`, which states the shape of the payload this descriptor describes."
        ),
    )
    rendered_markdown: str | None = Field(
        default=None,
        description=(
            "Opt-in Pipelex-API presentation extra: a server-rendered Markdown view of the valid verdict, "
            "present only when the request's `render` includes `markdown`. Absent by default — the structured fields "
            "remain the contract; this is the view."
        ),
    )


class InvalidReport(BaseModel):
    """The 200 **invalid** arm: a produced "invalid" verdict, discriminated on `is_valid: false`.

    An invalid bundle is the *successful product* of a diagnostic call, not a transport failure
    (the request was well-formed; the bundle was not), so it rides a **200** — the global
    `problem+json` 422/5xx is reserved for the no-verdict conditions (malformed request body,
    `mthds_sources` length mismatch, auth, server fault). The structural artifacts
    (`bundle_blueprint`, `pipe_io_contracts`, `graph_spec`, `validated_pipes`) do not exist when
    load/parse/wiring failed, so this arm omits them and carries only the per-error diagnostics,
    as the problem items of the verdict's problem (`errors`), plus the runnability facts. The
    `input_form` and `output_form` views follow them into absence for the same reason — both derive
    from a crate that was never assembled — so neither is declared here and `views` has no effect
    on this arm (unlike `rendered_markdown`, which rides both arms because failure
    text is exactly what a human surface wants).
    """

    is_valid: Literal[False] = False
    """Discriminant of the invalid arm (mirrors `ValidReport`/`PipelexValidationReport`'s `Literal[True]`)."""

    errors: list[ProblemItem] = Field(
        default_factory=empty_list_factory_of(ProblemItem),
        description=(
            "One problem item per error, each with its own code, its parameters and its location — non-empty on every "
            "invalid verdict. The items of the verdict's problem, as a refusal's `errors` carry them."
        ),
    )
    pending_signatures: list[str] = Field(
        default_factory=list,
        description="Best-effort outstanding signatures; empty on the invalid arm since no library was assembled.",
    )
    is_runnable: Literal[False] = False
    """An invalid bundle is never runnable."""

    message: str = Field(default="MTHDS validation found errors", description="Human-readable summary of the verdict.")
    rendered_markdown: str | None = Field(
        default=None,
        description=(
            "Opt-in Pipelex-API presentation extra: a server-rendered Markdown view of the invalid verdict's "
            "errors, present only when the request's `render` includes `markdown`. Absent by default."
        ),
    )


# Discriminated 200 response union (D-C): a consumer pattern-matches the one mandatory `is_valid`
# field to learn the verdict, without inspecting a status code or catching an exception body.
ValidationResponse = Annotated[Union[ValidReport, InvalidReport], Field(discriminator="is_valid")]


@router.post(
    "/validate",
    response_model=ValidationResponse,
    # On top of the composite router's shared 401/413/422/500: the custom-code sandbox gate's 501
    # and the `method_ref` package-not-found 404. Note what is deliberately NOT here: an *invalid
    # bundle* is a produced verdict on a 200, never a 4xx — and a selector-resolution failure is a
    # non-2xx problem+json, never an `is_valid: false` verdict.
    responses={404: PROBLEM_404_METHOD_PACKAGE, 501: PROBLEM_501_RUN_POLICY},
    openapi_extra={"x-mthds-protocol": True},
)
async def validate_mthds(request: Request, request_data: ValidateRequest) -> JSONResponse:
    """Validate MTHDS content by parsing, loading, and dry-running pipes (MTHDS Protocol `POST /validate`).

    `/validate` is a **diagnostic endpoint**: any verdict the validator can produce — valid,
    invalid, or valid-but-not-runnable — rides a **200** discriminated in the body on `is_valid`.
    Non-2xx is reserved for the cases where *no verdict could be produced*.

    Response contract:

    - **Valid verdict (200, `is_valid: true`):** the `ValidReport` arm — the canonical report
      (primary `bundle_blueprint`, `pipe_io_contracts` keyed by namespaced `pipe_ref`, per-pipe
      `validated_pipes` sweep outcomes, `pending_signatures` + `is_runnable` runnability verdict,
      best-effort `graph_spec`) plus the wire extras (`mthds_contents` echo, `message`,
      `default_pipe_ref`). The graph is drawn from the pipe a selector-less run of this request
      would execute: on a `method_ref` request whose manifest names a `main_pipe`, that pipe;
      otherwise the primary blueprint's `main_pipe`. A bundle that declares no `main_pipe`, with
      no manifest naming one, validates fine and carries `graph_spec=null`, and so does a
      manifest `main_pipe` the closure does not resolve. Pending signatures are reported as `pending_signatures` +
      `is_runnable: false`, never as an error. `default_pipe_ref` names the pipe a selector-less
      run of this same request would execute — on a `method_ref` request that is the fetched
      manifest's `main_pipe`, which the canonical report cannot see, so the field is the only
      signal a consumer can project a by-address entry signature from.
      The opt-in `views` tokens `input_form` and `output_form` additionally attach the per-pipe
      input-form and output-form descriptors as same-named top-level fields, keyed like
      `pipe_io_contracts`; without a token the matching field is absent and the body is
      byte-identical to a request that omits `views`. They are separate tokens because they answer
      separate questions — a caller building a fill-in form wants the inputs, a caller rendering a
      result or registering a tool signature with a return type wants the output.
    - **Invalid verdict (200, `is_valid: false`):** the `InvalidReport` arm — `errors[]`, one problem item per
      error with its own code (incl. one located item per pipe whose dry run failed, with the failure's code), the
      items of the verdict's problem — + `message`, with the structural artifacts absent. The runner
      returns this as a value (a `BundleValidationFailure` with validation items) regardless of backend — the
      in-process arm from the bundle's `ValidateBundleError`, the dispatched arm recovered from the
      worker — so the route maps it to a 200 by matching validation diagnostics, never by catching an
      exception. A returned failure without validation diagnostics is a backend, configuration or runtime
      fault, and its problem is answered as every raised failure's is.
    - **Either arm:** a member with no value is absent rather than `null`, at the arm's top level and in its
      problem items; the structured artifacts of the valid arm keep their own serialization.
    - **No verdict (non-2xx):** a malformed request body, an `mthds_sources` length mismatch, or
      both/neither of `mthds_contents` / `method_ref` is a request-shape **422**, and so is a forbidden
      `orchestration_mode` override; a host-wiring programmer error or a genuine orchestrator fault is a
      **5xx**; auth is **401/403**. A `method_ref` **resolution failure** is also a no-verdict condition —
      never an `is_valid: false`: each answers the status its code declares, such as a **422** for a
      malformed reference, a **502** for a failed fetch, a **404** for no matching package in the
      repository and a **422** for the method's Python structure classes, and the custom-code sandbox gate
      a **501**. All are `application/problem+json` documents carrying a registry `code`, rendered by the
      global handlers in `pipelex_api.exception_handlers` — routes never shape them.
    """
    # Opt-in presentation formats (D-D): resolved once, threaded into both 200 arms. Empty by
    # default → no `rendered_*` field, response byte-identical to the no-`render` request.
    requested_formats = _resolve_render_formats(request_data.render)
    # Opt-in structured views (D-D, the `views` axis): resolved once, applied to the valid arm only.
    # Empty by default → neither view field, response byte-identical to the no-`views` request.
    requested_views = _resolve_validation_views(request_data.views)
    # The validation is done for the caller: its dry runs and `pipe_dry_run` event carry the
    # authenticated user and the body's groups, exactly as a run of this request would.
    user_id = get_request_user_id(request)
    # Verdict-as-value: the runner resolves the orchestration mode and dispatches through the bundle
    # validator registry, returning either a validation verdict or a failure carrying its problem.
    # Only failures with validation diagnostics are invalid-bundle verdicts (→ 200 InvalidReport);
    # a backend, configuration or runtime fault is answered as its problem, like a raised one.
    if request_data.mthds_contents is not None:
        validated_contents = request_data.mthds_contents
        verdict = await ApiRunner(
            user_id=user_id,
            extras=request_data.analytics_groups,
            submitted_files=decode_bundle_resources(resources=request_data.resources),
        ).validate_verdict(
            mthds_contents=request_data.mthds_contents,
            mthds_sources=request_data.mthds_sources,
            allow_signatures=request_data.allow_signatures,
            requested_orchestration_mode=request_data.orchestration_mode,
            graph_pipe_code=None,
        )
        default_pipe_ref_known = False
        tree_default_pipe_ref: str | None = None
    else:
        # A method tree: sent as `files`, or fetched by `method_ref` from its commit's git objects through the same path
        # as a `method_ref` run. Every failure to obtain the tree — a map that is not a tree, missing blobs, a fetch, a
        # package location, the custom-Python policy — raises OUT of this block as a non-2xx problem+json: no verdict
        # was produced, so it is never rendered as `is_valid: false` (that verdict is about the method's content).
        request_method: RequestMethod
        if request_data.method_ref is not None:
            fetched = await asyncio.to_thread(fetched_method, request_data.method_ref)
            request_method = fetched.request_method
            method_label = fetched.label
            ensure_method_holds_a_bundle(request_method=request_method, label=f"Method package {fetched.label}")
            ensure_python_allowed(request_method=request_method, label=f"Method package {fetched.label}", origin=CustomCodeOrigin.PACKAGE)
        else:
            blob_store = RunnerBlobStore.make_for_scope(scope=resolve_blob_scope(request, read_scope=request_data.read_scope))
            sent_method = await read_request_method(documents=tree_documents_of(body=await request.body()), blob_store=blob_store)
            if sent_method is None:
                # Unreachable: the envelope's selector validator already 422'd a body with no `files`.
                msg = "provide exactly one of `mthds_contents`, `files` or `method_ref`"
                raise RunnerRequestError(msg, field="files")
            request_method = with_resources(request_method=sent_method, resources=decode_bundle_resources(resources=request_data.resources))
            method_label = REQUEST_METHOD_LABEL
            ensure_method_holds_a_bundle(request_method=request_method, label="This method")
            ensure_python_allowed(request_method=request_method, label="This method", origin=CustomCodeOrigin.BUNDLE)
            await record_request_method(request_method=request_method, blob_store=blob_store)
        validated_contents = _bundle_texts(request_method=request_method)
        # The entry pipe of the tree, the one a selector-less run executes, is the graph's pipe and the default the
        # verdict reports; a tree with none still validates.
        entry = _optional_tree_entry(request_method=request_method, method_label=method_label)
        tree_default_pipe_ref = entry.pipe_ref if entry is not None else None
        default_pipe_ref_known = True
        with written_method(request_method=request_method) as written:
            verdict = await ApiRunner(
                library_dirs=[str(written.method_dir)],
                library_dirs_are_callers=True,
                methods_dirs=written.methods_dirs,
                user_id=user_id,
                extras=request_data.analytics_groups,
            ).validate_verdict(
                mthds_contents=None,
                mthds_sources=None,
                allow_signatures=request_data.allow_signatures,
                requested_orchestration_mode=request_data.orchestration_mode,
                graph_pipe_code=tree_default_pipe_ref,
                method_dir=written.method_dir,
            )
    if isinstance(verdict, BundleValidationFailure):
        if verdict.validation_errors:
            return _invalid_report_response(verdict, requested_formats=requested_formats, view=problem_view_of(request))
        return problem_response(verdict.problem.model_copy(update={"request_id": request_id_of(request)}), error=None, request=request)
    report = verdict

    # Splat the report's own field/value pairs so a future canonical field rides the wire
    # automatically — the wrapper never enumerates (and silently drops) report fields. `is_valid`
    # rides through from the report as the valid-arm discriminant (True).
    response_data = ValidReport.model_validate(
        {
            **dict(report),
            "warnings": warning_problem_items(warnings=report.warnings),
            "mthds_contents": validated_contents,
            "default_pipe_ref": tree_default_pipe_ref if default_pipe_ref_known else _effective_default_pipe_ref(report),
        }
    )
    content = _without_unset_members(response_data.model_dump(mode="json", serialize_as_any=True, by_alias=True))
    # The problem items are dumped as the standard writes them, with no member written as `null`.
    content["warnings"] = [warning.model_dump(mode="json", exclude_none=True) for warning in response_data.warnings]
    # `rendered_markdown` is a presentation extra (D-D), not part of the report: attach it only when
    # `markdown` was requested, else pop it so the response stays byte-identical to a no-`render` call
    # (the valid arm is dumped without `exclude_none`, so the default `null` would otherwise linger).
    # Rendered from the canonical report dict — the same shape the local agent CLI feeds the renderer,
    # so the valid-arm Markdown shares one source of truth and cannot drift in format/structure.
    if RenderFormat.MARKDOWN in requested_formats:
        content["rendered_markdown"] = format_validate_markdown(report.model_dump(mode="json"))
    else:
        content.pop("rendered_markdown", None)
    # `input_form` is an opt-in structured view (D-D), not part of the default verdict: the canonical
    # report always carries it (required there, so a backend that forgets to derive it fails loudly),
    # so absence on the wire is an explicit pop — never a serialization side effect, since the field
    # is a populated dict rather than a `None` `exclude_none` would drop. Popping keeps the default
    # response byte-identical for the high-frequency callers (hook pipelines, CI gates, agent loops)
    # that would otherwise pay for a form they discard.
    if ValidationView.INPUT_FORM not in requested_views:
        content.pop("input_form", None)
    if ValidationView.OUTPUT_FORM not in requested_views:
        content.pop("output_form", None)
    return JSONResponse(content=content)


def _without_unset_members(content: dict[str, Any]) -> dict[str, Any]:
    """A verdict's members without those that hold no value: a member with no value is absent, never `null`.

    Only the arm's own members are dropped: inside an extension artifact, such as the bundle blueprint or a JSON
    schema, a `null` may be the value itself.
    """
    return {name: value for name, value in content.items() if value is not None}


def _invalid_report_response(failure: BundleValidationFailure, *, requested_formats: set[RenderFormat], view: ProblemView) -> JSONResponse:
    """Render a produced "invalid" verdict as a 200 `InvalidReport` (D-A / D-C / D-D).

    The `errors[]` are the problem items of the verdict's problem, in the view of the request's reader, one per item of
    pipelex's one shared builder (`ValidateBundleError.problem_items()`), each with its own code: including one located
    item per pipe whose dry run failed — the structured-info invariant, which the parse-level residual makes total,
    guarantees this list is non-empty on every invalid verdict that reaches the wire, since the empty-`mthds_contents`
    edge case is a request-shape 422 via `min_length=1`. `message` is the problem's `detail`, the sentence its code
    renders, which reads the same in every view.
    """
    match view:
        case ProblemView.OPERATOR:
            problem = failure.problem
        case ProblemView.CALLER:
            problem = caller_view_of(problem=failure.problem)
    invalid_report = InvalidReport(errors=list(problem.errors or []), message=problem.detail)
    # `exclude_none` drops each item's unset members, as the standard writes a problem item, and the arm's own: none is
    # written as `null`, and `rendered_markdown` stays absent unless explicitly requested below.
    content = invalid_report.model_dump(mode="json", serialize_as_any=True, by_alias=True, exclude_none=True)
    # Opt-in presentation extra (D-D): the Markdown the local channels render, from the validation items the problem
    # items were built from, one for one, attached only when `markdown` was requested.
    if RenderFormat.MARKDOWN in requested_formats:
        content["rendered_markdown"] = render_invalid_validation_markdown(
            {
                "validation_errors": [item.model_dump(mode="json", exclude_none=True) for item in failure.validation_errors],
                "message": problem.detail,
            }
        )
    return JSONResponse(content=content)
