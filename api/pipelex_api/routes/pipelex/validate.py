from enum import StrEnum
from typing import Annotated, Literal, Self, Union

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse
from pipelex.base_exceptions import ErrorReport, ValidationErrorItem
from pipelex.core.qualified_ref import QualifiedRef
from pipelex.pipe_machinery.pipe_factory import PipeFactory
from pipelex.pipeline.input_form import PipeInputFormDescriptor, PipeOutputFormDescriptor
from pipelex.pipeline.validation_render import format_validate_markdown, render_invalid_validation_markdown
from pipelex.pipeline.validation_report import PipelexValidationReport
from pipelex.tools.typing.pydantic_utils import empty_list_factory_of
from pydantic import BaseModel, Field, model_validator

from pipelex_api.errors import raise_validation_error
from pipelex_api.exception_handlers import problem_response_from_error_report
from pipelex_api.json_body import JsonBodyRoute
from pipelex_api.method_source import fetched_method_source
from pipelex_api.openapi_responses import PROBLEM_403_RUN_POLICY, PROBLEM_404_METHOD_PACKAGE
from pipelex_api.routes.pipelex.pipeline import ApiRunner, get_request_user_id
from pipelex_api.schemas.models import CallerAnalyticsGroupsMixin, MthdsContentsRequest

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
    `blueprint.source`, so the structured `validation_errors` on a 200 `InvalidReport` carry a real
    `source` the client maps back to the owning file — without it the in-memory load path leaves
    `source` null and cross-file diagnostics misfire. Omit it and behavior is unchanged.
    """

    mthds_sources: list[str] | None = Field(
        default=None,
        description=(
            "Optional per-file sources, parallel to `mthds_contents`. When provided, each entry is threaded "
            "onto the corresponding bundle's `source` so server-side validation errors carry a `source` pointing "
            "at the owning file. Must match `mthds_contents` in length when present."
        ),
    )
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
            "otherwise a token that differs from the deployment default is refused with a 403. Omitted → the default."
        ),
    )

    @model_validator(mode="after")
    def _sources_match_contents(self) -> Self:
        # `mthds_sources` labels INLINE contents; a `method_ref`'s sources are the package's own
        # file names, so pairing the two is a request-shape bug → 422.
        if self.mthds_sources is not None and self.method_ref is not None:
            msg = "mthds_sources accompanies inline mthds_contents; a method_ref's sources are the package's own file names"
            raise ValueError(msg)
        # A caller-supplied length mismatch is a request-shape bug → caught here as a 422.
        # Without this guard it reaches the runtime's `validate_bundle`, which treats the
        # mismatch as an internal host error (500) — the wrong status for caller input.
        if self.mthds_sources is not None and self.mthds_contents is not None and len(self.mthds_sources) != len(self.mthds_contents):
            msg = "mthds_sources, when provided, must be a per-item source list matching mthds_contents in length"
            raise ValueError(msg)
        return self


def _qualify_manifest_main_pipe(main_pipe: str, *, pipe_refs: list[str]) -> str | None:
    """Qualify a manifest's bare `main_pipe` against the pipes the verdict actually saw.

    A `METHODS.toml` `main_pipe` is a bare pipe code, and the runner resolves it exactly as it
    resolves a human-supplied selector (`get_optional_entry_pipe`): an already-qualified ref matches
    outright, a bare code is matched across the library's own domains, and an ambiguous bare code
    resolves to nothing rather than picking a winner. That rule is mirrored here against
    `pipe_io_contracts`' keys — the verdict's own complete, qualified pipe set — because the
    validate path holds no loaded library to ask (the Temporal-dispatched arm never loaded one in
    this process at all).

    Cross-package keys (`alias->domain.code`) are excluded, as they are in the engine: an installed
    dependency must never make a host package's own entry pipe ambiguous.

    Returns:
        The qualified ref, or None when the closure declares no such pipe or declares it in several
        domains — both cases in which a selector-less run by this address would fail to resolve it.
    """
    own_refs = [ref for ref in pipe_refs if not QualifiedRef.has_cross_package_prefix(ref)]
    if main_pipe in own_refs:
        return main_pipe
    matches = sorted({ref for ref in own_refs if ref.rpartition(".")[2] == main_pipe})
    if len(matches) == 1:
        return matches[0]
    return None


def _effective_default_pipe_ref(report: PipelexValidationReport, *, manifest_main_pipe: str | None) -> str | None:
    """The qualified ref of the pipe a selector-less run of THIS request would execute.

    The run routes' precedence, minus the request selector `/validate` does not have
    (`pipeline.py`: `pipe_code or fetched.main_pipe`, then the batch's primary blueprint via
    `select_primary_blueprint`): a fetched package's manifest `main_pipe` wins, and only when there
    is none does the closure's own declaration decide. The per-pipe tooling route applies that same
    chain in `crate_ops.resolve_requested_pipe`, so a caller reading this field and a caller omitting
    `pipe_ref` on `/pipe-io` are told about the same pipe wherever `/pipe-io` defaults at all — see
    the one case below where it refuses to.

    It deliberately states the RUN default, not the per-pipe route's stricter one: a closure whose
    domains each declare a `main_pipe` is refused by `/pipe-io` but runs happily — `execute` and
    `start` take the first declaring blueprint — so reporting `null` for it would make a consumer
    refuse to prepare a method the server would run. The report's `bundle_blueprint` IS that first
    declaring blueprint (`build_validation_report` selects it through the same
    `select_primary_blueprint`), so qualifying its `main_pipe` reproduces the run's own choice.

    Inline `mthds_contents` carry no manifest, so for them the chain is exactly the closure's
    declaration.
    """
    if manifest_main_pipe is not None:
        # A manifest entry that does not resolve yields None rather than falling through to the
        # closure's declaration: the run would pass the manifest's code and fail, so naming the
        # closure's pipe here would report a pipe no selector-less run of this address executes.
        return _qualify_manifest_main_pipe(manifest_main_pipe, pipe_refs=list(report.pipe_io_contracts))
    blueprint = report.bundle_blueprint
    if not blueprint.main_pipe:
        return None
    return PipeFactory.make_pipe_ref_with_domain(domain_code=blueprint.domain, pipe_code=blueprint.main_pipe)


class ValidReport(PipelexValidationReport):
    """The 200 **valid** arm: the canonical `PipelexValidationReport` plus this server's wire-only extras.

    The report fields are inherited — typed models, identical to what the local runtime
    returns for the same bundle, with `is_valid: Literal[True]` (from the report) as the union
    discriminant. The extras exist for HTTP clients only (the webapp reads back `mthds_contents`);
    they are NOT part of the canonical report and no in-process consumer should depend on them.

    Two inherited fields are deliberately re-declared: `input_form` and `output_form`. The canonical
    report requires both (a backend that forgets to derive one must fail loudly rather than ship an
    empty view), but on the wire each is an opt-in structured view gated by the request's `views` —
    so both are re-declared with defaults here, keeping them out of the published schema's `required`
    set. The values still always arrive from the report; the route pops each when its token was not
    requested. They are separate tokens rather than one because they answer separate questions: a
    caller building a fill-in form wants the inputs, a caller rendering a result or registering a
    tool signature wants the output, and neither should pay for the other.
    """

    mthds_contents: list[str] = Field(..., description="The MTHDS contents that were validated (echo of the request)")
    message: str = Field(default="MTHDS content validated successfully", description="Status message")
    default_pipe_ref: str | None = Field(
        default=None,
        description=(
            "The qualified `domain.pipe_code` a caller gets by omitting the pipe selector — the pipe a "
            "selector-less run of THIS request would execute. On a `method_ref` request it is the fetched "
            "package manifest's `main_pipe` (the package author's declared entry pipe, qualified against the "
            "closure); otherwise, and when the manifest declares none, it is the closure's primary blueprint's "
            "`main_pipe` qualified by its domain. `null` when no entry pipe is determined: no blueprint declares "
            "`main_pipe`, or a manifest names a pipe the closure does not declare (or declares ambiguously), in "
            "which case a selector-less run by this address would fail to resolve it too."
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
    load/parse/wiring failed, so this arm omits them and carries only the per-error diagnostics
    plus the runnability facts. The `input_form` and `output_form` views follow them into absence for
    the same reason — both derive from a crate that was never assembled — so neither is declared here and `views`
    has no effect on this arm (unlike `rendered_markdown`, which rides both arms because failure
    text is exactly what a human surface wants).
    """

    is_valid: Literal[False] = False
    """Discriminant of the invalid arm (mirrors `ValidReport`/`PipelexValidationReport`'s `Literal[True]`)."""

    validation_errors: list[ValidationErrorItem] = Field(
        default_factory=empty_list_factory_of(ValidationErrorItem),
        description="Per-error diagnostics, built by pipelex's one shared builder — non-empty on every invalid verdict.",
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
            "`validation_errors`, present only when the request's `render` includes `markdown`. Absent by default."
        ),
    )


# Discriminated 200 response union (D-C): a consumer pattern-matches the one mandatory `is_valid`
# field to learn the verdict, without inspecting a status code or catching an exception body.
ValidationResponse = Annotated[Union[ValidReport, InvalidReport], Field(discriminator="is_valid")]


@router.post(
    "/validate",
    response_model=ValidationResponse,
    # On top of the composite router's shared 401/413/422/500: the policy 403s (the
    # `orchestration_mode` override gate it shares with `/start`, plus — for a `method_ref` —
    # the custom-code sandbox gate and the structures refusal) and the `method_ref`
    # package-not-found 404. Note what is deliberately NOT here: an *invalid bundle* is a
    # produced verdict on a 200, never a 4xx — and a selector-resolution failure is a non-2xx
    # problem+json, never an `is_valid: false` verdict.
    responses={403: PROBLEM_403_RUN_POLICY, 404: PROBLEM_404_METHOD_PACKAGE},
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
    - **Invalid verdict (200, `is_valid: false`):** the `InvalidReport` arm — `validation_errors[]`
      (the structured per-error diagnostics, built by pipelex's one shared builder, incl. one
      located `dry_run` item per pipe whose dry run failed) + `message`, with the structural artifacts absent. The runner
      returns this as a value (`ErrorReport` with `validation_errors`) regardless of backend — the
      in-process arm from the bundle's `ValidateBundleError`, the dispatched arm recovered from the
      worker — so the route maps it to a 200 by matching validation diagnostics, never by catching an
      exception. Returned `ErrorReport`s without validation diagnostics are backend/config/runtime
      faults and keep the global RFC 7807 problem response path.
    - **No verdict (non-2xx):** a malformed request body, an `mthds_sources` length mismatch, or
      both/neither of `mthds_contents` / `method_ref` is a request-shape **422**; a forbidden
      `orchestration_mode` override is a **403**; a host-wiring programmer error or a genuine
      orchestrator fault is a **5xx**; auth is **401/403**. A `method_ref` **resolution failure**
      is also a no-verdict condition — never an `is_valid: false`: a malformed reference or a
      failed fetch is a **422**, no matching package in the repository a **404**, and the
      custom-Python policy (the sandbox gate, the structures refusal) a **403**, each with the
      originating error class as `error_type`. All are RFC 7807 `application/problem+json`
      rendered by the global handler in `pipelex_api.exception_handlers` — routes never shape them.
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
    # validator registry, returning either a validation verdict or a classified fault report.
    # Only `ErrorReport`s with validation diagnostics are invalid-bundle verdicts (→ 200
    # InvalidReport); backend/config/runtime reports keep the global problem+json mapping.
    if request_data.method_ref is not None:
        # Validate-by-address (the addressing design's Phase 2 delta): the runner resolves the
        # `method_ref` through the SAME fetch path as a `method_ref` run, and the package's real
        # file names feed `mthds_sources` so diagnostics carry true per-file labels. Every
        # selector-resolution failure — parse, fetch, no package, ambiguity, the custom-Python
        # policy — raises OUT of this block as a non-2xx problem+json: no verdict was produced,
        # so it is never rendered as `is_valid: false` (that verdict is about MTHDS content).
        with fetched_method_source(request_data.method_ref) as fetched:
            validated_contents = fetched.mthds_contents
            # The manifest's declared entry pipe outranks the closure's own in the default chain the
            # run routes and `/pipe-io` share, so it must reach `default_pipe_ref` — the report itself
            # is manifest-blind — and the graph arm, which would otherwise draw the primary blueprint's
            # `main_pipe`: a different pipe when the two disagree, and no graph at all when the bundles
            # declare none.
            # The bare code is passed as is, so the graph arm resolves it exactly as the run does.
            manifest_main_pipe = fetched.main_pipe
            verdict = await ApiRunner(
                library_dirs=fetched.library_dirs,
                user_id=user_id,
                extras=request_data.analytics_groups,
            ).validate_verdict(
                mthds_contents=fetched.mthds_contents,
                mthds_sources=fetched.mthds_sources,
                allow_signatures=request_data.allow_signatures,
                requested_orchestration_mode=request_data.orchestration_mode,
                graph_pipe_code=manifest_main_pipe,
            )
    elif request_data.mthds_contents is not None:
        validated_contents = request_data.mthds_contents
        # Inline contents carry no manifest, so the closure's own declaration is the whole chain.
        manifest_main_pipe = None
        verdict = await ApiRunner(user_id=user_id, extras=request_data.analytics_groups).validate_verdict(
            mthds_contents=request_data.mthds_contents,
            mthds_sources=request_data.mthds_sources,
            allow_signatures=request_data.allow_signatures,
            requested_orchestration_mode=request_data.orchestration_mode,
            graph_pipe_code=None,
        )
    else:
        # Unreachable: the envelope's XOR validator already 422'd this shape. Kept for the type
        # checker (and as a defensive backstop should the envelope ever loosen).
        raise_validation_error(message="provide exactly one of `mthds_contents` or `method_ref`")
    if not isinstance(verdict, PipelexValidationReport):
        if verdict.validation_errors:
            return _invalid_report_response(verdict, requested_formats=requested_formats)
        return problem_response_from_error_report(verdict, request=request)
    report = verdict

    # Splat the report's own field/value pairs so a future canonical field rides the wire
    # automatically — the wrapper never enumerates (and silently drops) report fields. `is_valid`
    # rides through from the report as the valid-arm discriminant (True).
    response_data = ValidReport.model_validate(
        {
            **dict(report),
            "mthds_contents": validated_contents,
            "default_pipe_ref": _effective_default_pipe_ref(report, manifest_main_pipe=manifest_main_pipe),
        }
    )
    content = response_data.model_dump(mode="json", serialize_as_any=True, by_alias=True)
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


def _invalid_report_response(error_report: ErrorReport, *, requested_formats: set[RenderFormat]) -> JSONResponse:
    """Render a produced "invalid" verdict as a 200 `InvalidReport` (D-A / D-C / D-D).

    The `validation_errors[]` come straight from pipelex's one shared builder via
    `ValidateBundleError.to_error_report()`, so the hosted invalid arm carries the same typed
    items the agent CLI emits (including one located `dry_run` item per pipe whose dry run failed —
    the structured-info invariant, which the parse-level `blueprint_validation` residual makes total,
    guarantees this list is non-empty on every invalid verdict that reaches the wire,
    since the empty-`mthds_contents` edge case is a request-shape 422 via `min_length=1`).
    `message` is the caller-facing summary the error report already carries.
    """
    invalid_report = InvalidReport(
        validation_errors=error_report.validation_errors or [],
        message=error_report.message,
    )
    # `exclude_none` drops each item's unset locators, so the wire items match the agent CLI's
    # `extract_validation_errors` byte-for-byte (it dumps items the same way) — the "one error item,
    # two surfaces" guarantee. The invalid arm's own fields are all non-None, so none are lost; and
    # `rendered_markdown` stays absent here unless explicitly requested below.
    content = invalid_report.model_dump(mode="json", serialize_as_any=True, by_alias=True, exclude_none=True)
    # Opt-in presentation extra (D-D): a faithful render of the structured `validation_errors`,
    # attached only when `markdown` was requested. Built from the just-dumped content so the renderer
    # reads the same items the wire carries.
    if RenderFormat.MARKDOWN in requested_formats:
        content["rendered_markdown"] = render_invalid_validation_markdown(content)
    return JSONResponse(content=content)
