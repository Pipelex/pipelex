"""The problem document every Pipelex error becomes, and the views its readers see it through.

A failure, on any wire or at rest, is one problem document: the MTHDS core's :class:`~mthds.protocol.problem.models.Problem`,
an RFC 9457 document carrying a registry code, the code's domain, retry verdict and next step, the code's typed
parameters, the location and the itemized errors, extended by Pipelex with the request id, the problem of a failed
run nested in the problem of a read of its results (``run_error``), and the diagnostics only an operator reads.

**The views.** Who reads a problem decides what of it they see, and the identity a boundary authenticates picks the
view, never a deployment's mode:

- The caller view is the problem without ``diagnostics``, with the step aimed at the caller: the code's actor step,
  except for a code of the ``operator`` domain, whose actor is whoever runs the runtime, where it is the step aimed at
  any other reader.
- The operator view adds ``diagnostics`` and gives the actor's step for every code, rendered with the parameters only
  an operator may read as well.
- The metadata view (:class:`ProblemMetadata`) holds codes, domains, verdicts, step kinds, the shape of the location,
  ids and versions, and no sentence, no parameter and no name a user wrote.

**The sentences.** ``detail`` and the step's ``detail`` are rendered from the code's templates and its parameters, and
a raise site never writes them: the exception's own message rides ``diagnostics.message``. Rendering is total: a
template that cannot be rendered, because a parameter it names was not given, falls back to the code's title for
``detail`` and to a generic sentence of the step's kind for the step, and the failure is logged so that the raise site
can be given the parameter.

**The parameters.** A problem's ``params`` hold the parameters the code declares and the raise site gave, validated
against the code's generated model: an undeclared parameter, or one of the wrong type, is dropped and logged. A
parameter the registry declares operator-only never rides ``params`` in any view; it renders into the operator's step
and rides ``diagnostics.params``.

**The bound.** Every text a raise site, a provider or a caller wrote is capped at :data:`MAX_PROBLEM_TEXT_LENGTH`
characters, keeping its head, which names the fault: an exception's message, a provider's message and every text
parameter. The full text is left to the logs.

**No null member.** A problem is written without a member whose value is ``null``, since the protocol leaves a member
with no value out and a strict reader refuses a declared member written as ``null``: :meth:`PipelexProblem.to_wire`.
"""

from __future__ import annotations

import functools
import logging
import math
from collections.abc import Mapping, Sequence
from enum import Enum, StrEnum
from pathlib import Path
from typing import Any, cast

from mthds.protocol.problem.client_problems import render_template
from mthds.protocol.problem.models import NextStep, Problem, ProblemItem, ProblemLocation, ProblemParams
from mthds.protocol.problem.registry import ProblemDomain, StepKind
from pydantic import BaseModel, ConfigDict, SerializerFunctionWrapHandler, ValidationError, model_serializer
from typing_extensions import override

from pipelex.errors.error_codes import ErrorCode, ErrorCodeSpec, error_code_spec, parse_error_code
from pipelex.migration.plan import MigrationPlan
from pipelex.tools.log.log_context import get_log_context
from pipelex.tools.log.log_fields import attach_log_record_extra, build_log_record_extra
from pipelex.tools.misc.package_utils import get_package_version

MAX_PROBLEM_TEXT_LENGTH = 2000
"""The most characters a text written by a raise site, a provider or a caller keeps on a problem.

It bounds an exception's message on ``diagnostics.message``, a provider's message on ``diagnostics.provider.message``
and every text parameter. A structured output's validation failure can run to hundreds of thousands of characters,
every completion an output parser retried included, and none of it may travel whole into a stored run report, a
response or a client. A capped text keeps its head, which names the fault, and ends with :data:`TRUNCATION_MARKER`.
"""

TRUNCATION_MARKER = " […]"
"""What a capped text ends with, so that its reader knows the rest was cut."""


def cap_problem_text(*, text: str) -> str:
    """A text bounded to :data:`MAX_PROBLEM_TEXT_LENGTH` characters, its head kept and the cut marked.

    Args:
        text: A text a raise site, a provider or a caller wrote.

    Returns:
        The text itself when it fits, else its head followed by :data:`TRUNCATION_MARKER`, the two within the bound.
    """
    if len(text) <= MAX_PROBLEM_TEXT_LENGTH:
        return text
    return text[: MAX_PROBLEM_TEXT_LENGTH - len(TRUNCATION_MARKER)] + TRUNCATION_MARKER


class ProblemView(StrEnum):
    """The view of a problem document a reader sees, picked by the identity a boundary authenticates.

    The third view, the metadata channel's, is no problem document: :class:`ProblemMetadata`.
    """

    CALLER = "caller"
    OPERATOR = "operator"

    @property
    def shows_diagnostics(self) -> bool:
        """Whether the view carries ``diagnostics``: only the operator's."""
        match self:
            case ProblemView.OPERATOR:
                return True
            case ProblemView.CALLER:
                return False


class MigrationErrorBlock(BaseModel):
    """A pending configuration migration, reported alongside the error it explains.

    The structured half of the answer to *why does my configuration not load*, carried by the operator's
    ``diagnostics.migration`` and present only when a scan of this machine's configuration directories found something
    to say. **Consumers branch on its presence**, never on the message text: an absent block means the failure is not
    staleness. It describes the host's own configuration directories, so only an operator reads it.

    ``plans`` is the same shape ``pipelex-agent migrate --dry-run --format json`` emits under its own ``plans`` key,
    deliberately: an agent that reads one has already parsed the other.

    > **No value read from a user's file is ever rendered** here either. The plans carry paths, operation kinds and
    > ledger-supplied values, and nothing else.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    remedy: str
    """The command that applies whatever can be applied without a decision."""

    would_write: bool
    """Whether running ``remedy`` would actually rewrite any of these files.

    The block's *presence* says the migration history has something to report about this machine. It does not say the
    remedy repairs it, and this field is what separates the two. A block whose ``would_write`` is False carries a
    diagnosis and nothing to apply. Independent of :attr:`needs_attention`, and the pair is never both False."""

    needs_attention: bool
    """Whether something here is a person's to resolve rather than the tool's: a blocked file, a blocked entry, or a
    path no ledger entry explains. When this is False, running ``remedy`` is expected to be enough."""

    plans: list[MigrationPlan]
    """One per configuration file the scan found something in. Files with nothing to say are left out."""


class DiagnosticCause(BaseModel):
    """One error of a failure's cause chain, by its class and the code it carries by itself."""

    model_config = ConfigDict(frozen=True, extra="allow")

    error_class: str
    code: str | None = None


class ProviderDiagnostics(BaseModel):
    """What the inference provider said about a failed call, for an operator."""

    model_config = ConfigDict(frozen=True, extra="allow")

    name: str | None = None
    status: int | None = None
    code: str | None = None
    request_id: str | None = None
    message: str | None = None


class ProblemDiagnostics(BaseModel):
    """What only an operator reads of a problem: the operator view's ``diagnostics`` member.

    Attributes:
        error_class: The class of the error the problem was built from, the identity ``error_type`` once was.
        message: The error's own message, capped.
        causes: The errors below it on its cause chain, by class and code.
        params: The parameters the code declares operator-only.
        model: The model a failed inference call addressed.
        provider: What the provider said about the call.
        migration: A pending configuration migration that explains the failure.
        runtime_version: The version of the Pipelex runtime that built the problem.
        trace_id: The trace of the Pipelex span the failure happened in.
        span_id: That span.
    """

    model_config = ConfigDict(frozen=True, extra="allow")

    error_class: str
    message: str
    causes: list[DiagnosticCause] | None = None
    params: dict[str, Any] | None = None
    model: str | None = None
    provider: ProviderDiagnostics | None = None
    migration: MigrationErrorBlock | None = None
    runtime_version: str | None = None
    trace_id: str | None = None
    span_id: str | None = None


class PipelexProblem(Problem):
    """The MTHDS problem document with Pipelex's members.

    Attributes:
        request_id: The request that carried the failure, when known.
        run_error: On a read of a failed run's results, the run's own problem.
        diagnostics: What only an operator reads; present in the operator view alone.
    """

    request_id: str | None = None
    run_error: PipelexProblem | None = None
    diagnostics: ProblemDiagnostics | None = None

    @model_serializer(mode="wrap")
    def _drop_null_members(self, handler: SerializerFunctionWrapHandler):
        # Unannotated on purpose: a return annotation would replace the model's published serialization schema.
        # Whoever dumps a problem, alone or nested in a model that holds one (a graph node, a trace event, a webhook's
        # payload), gets it with no member written as `null`, which a strict reader refuses.
        return _without_null_members(value=handler(self))

    def to_wire(self) -> dict[str, Any]:
        """The problem in JSON types, with no member written as ``null``.

        Returns:
            The members of the problem that hold a value, nested ones included.
        """
        return self.model_dump(mode="json")

    @override
    def as_wire(self) -> dict[str, Any]:
        return self.to_wire()


def _without_null_members(*, value: Any) -> Any:
    """``value`` with every member of every object it nests that is ``None`` left out."""
    if isinstance(value, dict):
        return {key: _without_null_members(value=item) for key, item in cast("dict[str, Any]", value).items() if item is not None}
    if isinstance(value, list):
        return [_without_null_members(value=item) for item in cast("list[Any]", value)]
    return value


# The sentence of a step whose template could not be rendered: one per kind, naming no parameter.
_GENERIC_STEP_SENTENCES: dict[StepKind, str] = {
    StepKind.RETRY: "Send the request again.",
    StepKind.WAIT: "Wait, then send the request again.",
    StepKind.READ_RUN: "Read the run to learn its outcome before sending the request again.",
    StepKind.REFRESH: "Fetch the latest state, then apply the change again.",
    StepKind.CHANGE_INPUT: "Correct the request or its inputs as the problem describes, then send it again.",
    StepKind.CHANGE_METHOD: "Correct the method as the problem describes, then validate it again.",
    StepKind.CHANGE_MODEL: "Choose another model, then send the request again.",
    StepKind.CHECK_CREDENTIALS: "Check the credential the request carries, then send it again.",
    StepKind.REQUEST_ACCESS: "Ask for the access this operation needs, then send the request again.",
    StepKind.CHECK_ACCOUNT: "Check the account's plan, credit and quotas.",
    StepKind.FIX_CONFIGURATION: "Correct the runtime's configuration, then restart it.",
    StepKind.UPGRADE: "Upgrade the client or the runtime so that both implement the same protocol version.",
    StepKind.CONTACT_OWNER: "Ask the owner of the method or of the account to act on this problem.",
    StepKind.REPORT: "Report this problem with its request id.",
}


# The logger of the faults of a raise site this module finds while it builds a problem. This module sits under the
# import chain of `pipelex.log` itself, whose configuration loads the error classes that build problems, so it cannot
# import the log, and emits its records on this stdlib logger instead, with the same attached fields, through the
# handlers the log configured, as `pipelex.system.exceptions` does.
_problem_logger = logging.getLogger(__name__)


def _warn(*, message: str, fields: Mapping[str, Any]) -> None:
    """Emit a warning record about a raise site's fault, its values attached as fields, never in the message."""
    if not _problem_logger.isEnabledFor(logging.WARNING):
        return
    record = _problem_logger.makeRecord(
        name=_problem_logger.name,
        level=logging.WARNING,
        fn=__file__,
        lno=0,
        msg=message,
        args=(),
        exc_info=None,
    )
    attach_log_record_extra(record=record, extra=build_log_record_extra(context=get_log_context(), fields=fields, data=None))
    _problem_logger.handle(record)


def _render_sentence(*, template: str, params: Mapping[str, Any], code: str, part: str) -> str | None:
    """A template rendered with the parameters, or ``None``, logged, when it names a parameter not given."""
    try:
        return render_template(template, params=params)
    except ValueError as exc:
        _warn(
            message="A problem's sentence could not be rendered from its template",
            fields={"error.code": code, "template_part": part, "reason": str(exc)},
        )
        return None


def _param_value(*, value: Any) -> Any:
    """A parameter's value in the JSON types its model validates: a text capped, a sequence as a list, an enum as its value."""
    if isinstance(value, StrEnum):
        return cap_problem_text(text=str(value))
    if isinstance(value, Enum):
        return _param_value(value=value.value)
    if isinstance(value, str):
        return cap_problem_text(text=value)
    if isinstance(value, Path):
        return cap_problem_text(text=str(value))
    if isinstance(value, bool | int | float):
        return value
    if isinstance(value, Sequence | set | frozenset):
        items = cast("Sequence[Any] | set[Any] | frozenset[Any]", value)
        return [_param_value(value=item) for item in items]
    return value


def accepted_params(*, code: ErrorCode, params: Mapping[str, Any]) -> dict[str, Any]:
    """The parameters of ``params`` the code declares, each of the type its model requires.

    A parameter the code does not declare, or one of the wrong type, is dropped and logged: it is a fault of the
    raise site, which must never turn the error it reports into another. A parameter given as ``None`` is left out.

    Args:
        code: The code the parameters are given for.
        params: The parameters the raise site gave, by name.

    Returns:
        The accepted parameters, in JSON types, texts capped.
    """
    spec = error_code_spec(code)
    accepted: dict[str, Any] = {}
    for name, value in params.items():
        if value is None:
            continue
        if name not in spec.param_names:
            _warn(message="An error gives a parameter its code does not declare", fields={"error.code": code, "param": name})
            continue
        accepted[name] = _param_value(value=value)
    try:
        spec.params_model.model_validate(accepted)
    except ValidationError as validation_error:
        for error in validation_error.errors(include_url=False, include_input=False):
            if error["type"] == "missing" or not error["loc"]:
                continue
            refused_name = str(error["loc"][0])
            if accepted.pop(refused_name, None) is not None:
                _warn(
                    message="An error gives a parameter of the wrong type for its code",
                    fields={"error.code": code, "param": refused_name, "reason": error["type"]},
                )
    return accepted


def _caller_step_is_actor_step(*, domain: ProblemDomain) -> bool:
    """Whether the caller reads the actor's step: for every domain but ``operator``, whose actor is whoever runs the runtime."""
    match domain:
        case ProblemDomain.INPUT | ProblemDomain.METHOD | ProblemDomain.ACCOUNT | ProblemDomain.RUNTIME:
            return True
        case ProblemDomain.OPERATOR:
            return False


def _next_step(*, spec: ErrorCodeSpec, view: ProblemView, params: Mapping[str, Any]) -> NextStep:
    """The step of a view, rendered with the parameters the view may read, a generic sentence of its kind when it cannot be."""
    kind: StepKind
    template: str
    match view:
        case ProblemView.OPERATOR:
            kind, template = spec.actor_step, spec.actor_step_detail
        case ProblemView.CALLER:
            if _caller_step_is_actor_step(domain=spec.domain):
                kind, template = spec.actor_step, spec.actor_step_detail
            else:
                kind, template = spec.other_step, spec.other_step_detail
    detail = _render_sentence(template=template, params=params, code=spec.code, part=f"step.{kind}")
    return NextStep(kind=kind, detail=detail or _GENERIC_STEP_SENTENCES[kind])


def _is_usable_delay(*, seconds: float | None) -> bool:
    """Whether a delay before a retry can ride a problem: a finite, non-negative number of seconds."""
    return seconds is not None and math.isfinite(seconds) and seconds >= 0


def _members(**members: Any) -> dict[str, Any]:
    """The members that hold a value, so that no declared member is built as ``null``."""
    return {name: value for name, value in members.items() if value is not None}


def make_problem(
    *,
    code: ErrorCode,
    view: ProblemView,
    params: Mapping[str, Any] | None = None,
    location: ProblemLocation | None = None,
    errors: list[ProblemItem] | None = None,
    retry_after: float | None = None,
    pipeline_run_id: str | None = None,
    request_id: str | None = None,
    diagnostics: ProblemDiagnostics | None = None,
) -> PipelexProblem:
    """Build a problem in a view, reading from the registry everything its code decides.

    Args:
        code: The registry code.
        view: The view of the reader the problem is built for.
        params: The parameters the raise site gave, operator-only ones included; they are validated by
            :func:`accepted_params`.
        location: Where the error happened.
        errors: One item per fault, for a refusal with several.
        retry_after: The delay before a retry, kept only when the code's verdict is ``yes`` and the delay is a finite,
            non-negative number of seconds: a provider can send any value, ``inf`` included, and the wire takes none of those.
        pipeline_run_id: The run the error belongs to.
        request_id: The request that carried it.
        diagnostics: What only an operator reads; kept in the operator view alone, with the operator-only parameters.

    Returns:
        The problem, without a ``status``, which the HTTP response that carries it adds.
    """
    spec = error_code_spec(code)
    given = accepted_params(code=code, params=params or {})
    caller_params = {name: value for name, value in given.items() if name not in spec.operator_only_params}
    operator_params = {name: value for name, value in given.items() if name in spec.operator_only_params}
    detail = _render_sentence(template=spec.detail, params=caller_params, code=code, part="detail") or spec.title
    step_params = given if view.shows_diagnostics else caller_params
    view_diagnostics: ProblemDiagnostics | None = None
    if view.shows_diagnostics and diagnostics is not None:
        view_diagnostics = diagnostics.model_copy(update={"params": operator_params or None}) if operator_params else diagnostics
    invites_retry = spec.invites_retry
    return PipelexProblem.model_validate(
        _members(
            type=spec.type_uri,
            title=spec.title,
            detail=detail,
            code=spec.code,
            domain=spec.domain,
            retry=spec.retry,
            retry_after=retry_after if invites_retry and _is_usable_delay(seconds=retry_after) else None,
            next_step=_next_step(spec=spec, view=view, params=step_params),
            params=ProblemParams.model_validate(caller_params) if caller_params else None,
            location=location,
            errors=errors or None,
            pipeline_run_id=pipeline_run_id,
            request_id=request_id,
            diagnostics=view_diagnostics,
        )
    )


def make_problem_item(
    *,
    code: ErrorCode,
    params: Mapping[str, Any] | None = None,
    location: ProblemLocation | None = None,
    suggestions: list[str] | None = None,
    suggested_fix: Mapping[str, Any] | None = None,
) -> ProblemItem:
    """Build one item of a problem with several faults, its sentence rendered from its code's template.

    An item is the same in every view: its parameters are the caller's, a parameter its code declares operator-only
    being left out, and its sentence falls back on the code's title when the template cannot be rendered.

    Args:
        code: The item's registry code.
        params: The parameters the raise site gave.
        location: Where the fault is.
        suggestions: The names a near miss most likely meant.
        suggested_fix: The deterministic fix of the fault, in its wire form.

    Returns:
        The item.
    """
    spec = error_code_spec(code)
    given = accepted_params(code=code, params=params or {})
    caller_params = {name: value for name, value in given.items() if name not in spec.operator_only_params}
    detail = _render_sentence(template=spec.detail, params=caller_params, code=code, part="detail") or spec.title
    return ProblemItem.model_validate(
        _members(
            code=spec.code,
            detail=detail,
            params=ProblemParams.model_validate(caller_params) if caller_params else None,
            location=location,
            suggestions=suggestions or None,
            suggested_fix=dict(suggested_fix) if suggested_fix is not None else None,
        )
    )


def make_location(
    *,
    pipe: str | None = None,
    path: Sequence[str] | None = None,
    input_name: str | None = None,
    field: str | None = None,
    item: int | None = None,
    attempt: int | None = None,
    file: str | None = None,
    line: int | None = None,
    column: int | None = None,
) -> ProblemLocation | None:
    """A location holding the members given, ``None`` when none is.

    Args:
        pipe: The failing pipe's code.
        path: The pipe codes from the run's main pipe down to the failing one.
        input_name: An input's name.
        field: A dotted path inside an input or a request body.
        item: An index in a batch.
        attempt: The attempt, from 1.
        file: The method's source file.
        line: The line in it, from 1.
        column: The column in it, from 1.

    Returns:
        The location, or ``None`` when it would be empty.
    """
    members = _members(
        pipe=pipe,
        path=list(path) if path else None,
        input=input_name,
        field=field,
        item=item,
        attempt=attempt,
        file=file,
        line=line,
        column=column,
    )
    if not members:
        return None
    return ProblemLocation.model_validate(members)


def merge_locations(*, base: ProblemLocation | None, override: ProblemLocation) -> ProblemLocation:
    """A location holding the members of both, ``override``'s winning where both hold one.

    Args:
        base: The location an error knows about itself, such as the input or the field at fault.
        override: The location found around it, such as the failing pipe and its path.

    Returns:
        The merged location.
    """
    base_members = base.as_wire() if base is not None else {}
    return ProblemLocation.model_validate({**base_members, **override.as_wire()})


def caller_view_of(*, problem: PipelexProblem) -> PipelexProblem:
    """The caller's view of a problem built in the operator's: ``diagnostics`` dropped, the step re-aimed at the caller.

    The operator view holds everything the caller view does, so a reader holding the operator's record, such as the
    hosted plane's stored run report, serves its caller from it. For a code of the ``operator`` domain the step is
    rendered again from the problem's ``params``, which never hold an operator-only parameter; any other code's step is
    the caller's already. A code neither registry holds keeps its step. A nested ``run_error`` is projected the same way.

    Args:
        problem: A problem in any view.

    Returns:
        The caller view.
    """
    members = problem.to_wire()
    members.pop("diagnostics", None)
    if problem.run_error is not None:
        members["run_error"] = caller_view_of(problem=problem.run_error).to_wire()
    code = parse_error_code(problem.code)
    if code is not None:
        params = problem.params.as_wire() if problem.params is not None else {}
        members["next_step"] = _next_step(spec=error_code_spec(code), view=ProblemView.CALLER, params=params).as_wire()
    return PipelexProblem.model_validate(members)


class LocationShape(BaseModel):
    """The shape of a problem's location, naming nothing: how deep the failing pipe is, the attempt and the batch index."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    depth: int | None = None
    attempt: int | None = None
    item: int | None = None


class ProblemMetadata(BaseModel):
    """The metadata view of a problem: what may leave a perimeter, with no sentence, parameter or name a user wrote.

    Attributes:
        code: The registry code.
        domain: Who must act.
        retry: The retry verdict.
        next_step_kind: The kind of the problem's step.
        location: The shape of the location, when the problem has one.
        item_codes: The codes of the problem's items, in order.
        pipeline_run_id: The run the problem belongs to.
        request_id: The request that carried it.
        runtime_version: The version of the Pipelex runtime that built it.
        run_error: The metadata of a nested run problem.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    code: str
    domain: str
    retry: str
    next_step_kind: str
    location: LocationShape | None = None
    item_codes: list[str] | None = None
    pipeline_run_id: str | None = None
    request_id: str | None = None
    runtime_version: str | None = None
    run_error: ProblemMetadata | None = None

    def to_wire(self) -> dict[str, Any]:
        """The metadata in JSON types, with no member written as ``null``."""
        return self.model_dump(mode="json", exclude_none=True)


def problem_metadata(*, problem: PipelexProblem) -> ProblemMetadata:
    """The metadata view of a problem built in any view.

    Args:
        problem: The problem.

    Returns:
        Its codes, domain, verdict, step kind, location shape, ids and versions.
    """
    location_shape: LocationShape | None = None
    if problem.location is not None:
        location_shape = LocationShape(
            depth=len(problem.location.path) if problem.location.path else None,
            attempt=problem.location.attempt,
            item=problem.location.item,
        )
    return ProblemMetadata(
        code=problem.code,
        domain=str(problem.domain),
        retry=str(problem.retry),
        next_step_kind=str(problem.next_step.kind),
        location=location_shape,
        item_codes=[item.code for item in problem.errors] if problem.errors else None,
        pipeline_run_id=problem.pipeline_run_id,
        request_id=problem.request_id,
        runtime_version=problem.diagnostics.runtime_version if problem.diagnostics is not None else None,
        run_error=problem_metadata(problem=problem.run_error) if problem.run_error is not None else None,
    )


@functools.cache
def runtime_version() -> str:
    """The version of the installed Pipelex runtime, which an operator's diagnostics name."""
    return get_package_version()
