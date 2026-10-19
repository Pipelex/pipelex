"""Every error code a Pipelex error may carry, and what the registries declare about each.

A code is either a core code of the MTHDS standard, generated into the ``mthds`` package as
:class:`~mthds.protocol.problem.registry.CoreCode` from the core registry, or a Pipelex code, generated into
:class:`~pipelex.errors.registry.pipelex_codes.PipelexErrorCode` from Pipelex's own registry. A code
decides everything a reader branches on: its title, the domain whose actor must act, its retry verdict,
its HTTP status and its two steps. :func:`error_code_spec` reads them from the generated tables, never
from a file, so classifying an error is a pure lookup that is safe anywhere, inside a Temporal workflow's
sandbox included.

Each ``PipelexError`` subclass declares the code it raises, the set its raise sites choose from, that it
takes its cause's code, or that it is an abstract base, as :mod:`pipelex.errors.error_code_declaration`
describes. ``docs/under-the-hood/error-model.md`` explains the whole model.
"""

from __future__ import annotations

from typing import TypeAlias

from mthds.protocol.problem.registry import CORE_BASE_URL, CORE_CODE_SPECS, EXTENSION_PREFIXES, CoreCode, ProblemDomain, RetryVerdict, StepKind
from pydantic import BaseModel, ConfigDict

from pipelex.errors.registry.pipelex_codes import PIPELEX_ERROR_ENTRIES, PIPELEX_ERROR_PARAMS, PipelexErrorCode

ErrorCode: TypeAlias = CoreCode | PipelexErrorCode
"""A registered code: a core code of the MTHDS standard, or a Pipelex code."""

PIPELEX_ERROR_BASE_URL: str = EXTENSION_PREFIXES["pipelex"]
"""The base URL the core registry registers for the ``pipelex`` prefix: a Pipelex code's type URI is this URL, a slash, then the code."""


class ErrorCodeSpec(BaseModel):
    """What the registry declares about a code that classifying and reporting an error needs.

    Attributes:
        code: The code.
        title: The code's short title, the same for every occurrence.
        domain: Who must act.
        retry: Whether repeating the operation that produced the error can succeed.
        status: The HTTP status of an answer the code is the body of, ``None`` for a code a client
            raises itself or one that only rides a warning.
        detail: The template of the sentence stating one occurrence, naming parameters as ``{name}``.
        actor_step: The kind of the next step for the domain's actor.
        actor_step_detail: The template of the actor's step sentence.
        other_step: The kind of the next step for any other reader.
        other_step_detail: The template of the other reader's step sentence.
        type_uri: The code's documentation page: its registry's base URL, a slash, then the code.
        params_model: The generated model of the code's parameters.
        param_names: Every parameter the code declares.
        required_params: The parameters a caller reads on every occurrence of the code: every one the registry marks
            neither optional nor operator-only, the rule a conformance check holds a caller's problem to. A problem or
            an item that lacks one is a fault of its raise site, which
            :func:`pipelex.errors.problem.missing_required_params` names.
        operator_only_params: The parameters only whoever runs the runtime may read: they render into the
            operator's step and ride the operator's diagnostics, never a problem's ``params``.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    code: str
    title: str
    domain: ProblemDomain
    retry: RetryVerdict
    status: int | None
    detail: str
    actor_step: StepKind
    actor_step_detail: str
    other_step: StepKind
    other_step_detail: str
    type_uri: str
    params_model: type[BaseModel]
    param_names: frozenset[str]
    required_params: frozenset[str]
    operator_only_params: frozenset[str]

    @property
    def caller_param_names(self) -> frozenset[str]:
        """The parameters a caller may read: every one the code declares but the operator-only ones."""
        return self.param_names - self.operator_only_params

    @property
    def invites_retry(self) -> bool:
        """Whether the verdict invites a repeat of the operation: only ``yes``, never ``no`` nor ``outcome_unknown``."""
        match self.retry:
            case RetryVerdict.YES:
                return True
            case RetryVerdict.NO | RetryVerdict.OUTCOME_UNKNOWN:
                return False


def _build_specs() -> dict[str, ErrorCodeSpec]:
    specs: dict[str, ErrorCodeSpec] = {}
    for core_code in CoreCode:
        core_spec = CORE_CODE_SPECS[core_code]
        specs[core_code] = ErrorCodeSpec(
            code=core_code,
            title=core_spec.title,
            domain=core_spec.domain,
            retry=core_spec.retry,
            status=core_spec.status,
            detail=core_spec.detail,
            actor_step=core_spec.actor_step.kind,
            actor_step_detail=core_spec.actor_step.detail,
            other_step=core_spec.other_step.kind,
            other_step_detail=core_spec.other_step.detail,
            type_uri=f"{CORE_BASE_URL}/{core_code}",
            params_model=core_spec.params_model,
            param_names=frozenset(param.name for param in core_spec.params),
            required_params=frozenset(param.name for param in core_spec.params if not param.optional and not param.operator_only),
            operator_only_params=frozenset(param.name for param in core_spec.params if param.operator_only),
        )
    for pipelex_code in PipelexErrorCode:
        entry = PIPELEX_ERROR_ENTRIES[pipelex_code]
        params_model = PIPELEX_ERROR_PARAMS[pipelex_code]
        specs[pipelex_code] = ErrorCodeSpec(
            code=pipelex_code,
            title=entry.title,
            domain=ProblemDomain(entry.domain),
            retry=RetryVerdict(entry.retry),
            status=entry.status,
            detail=entry.detail,
            actor_step=StepKind(entry.actor_step),
            actor_step_detail=entry.actor_step_detail,
            other_step=StepKind(entry.other_step),
            other_step_detail=entry.other_step_detail,
            type_uri=f"{PIPELEX_ERROR_BASE_URL}/{pipelex_code}",
            params_model=params_model,
            param_names=frozenset(params_model.model_fields),
            required_params=frozenset(
                name for name, field in params_model.model_fields.items() if field.is_required() and name not in params_model.operator_only_params
            ),
            operator_only_params=params_model.operator_only_params,
        )
    return specs


_ERROR_CODE_SPECS: dict[str, ErrorCodeSpec] = _build_specs()


def error_code_spec(code: ErrorCode) -> ErrorCodeSpec:
    """What the registry declares about a registered code.

    Args:
        code: A core code or a Pipelex code.

    Returns:
        The code's title, domain, retry verdict, status, templates, step kinds, parameters and type URI.
    """
    return _ERROR_CODE_SPECS[code]


def parse_error_code(value: str) -> ErrorCode | None:
    """The registered code a string names, ``None`` when it names no code of either registry.

    Args:
        value: A code as a reader received it, such as ``"model.unknown"`` or ``"pipelex.config.invalid"``.

    Returns:
        The code's constant, or ``None`` for a string that is no registered code.
    """
    # A lookup by value rather than `value in CoreCode`, which raises on a string before Python 3.12.
    try:
        return CoreCode(value)
    except ValueError:
        pass
    try:
        return PipelexErrorCode(value)
    except ValueError:
        return None


def _retry_rank(*, retry: RetryVerdict) -> int:
    # A verdict that someone must fix comes before one a repeat may cure, so that no client retries what must be fixed.
    match retry:
        case RetryVerdict.NO:
            return 0
        case RetryVerdict.OUTCOME_UNKNOWN:
            return 1
        case RetryVerdict.YES:
            return 2


def _domain_rank(*, domain: ProblemDomain) -> int:
    match domain:
        case ProblemDomain.METHOD:
            return 0
        case ProblemDomain.OPERATOR:
            return 1
        case ProblemDomain.ACCOUNT:
            return 2
        case ProblemDomain.INPUT:
            return 3
        case ProblemDomain.RUNTIME:
            return 4


def first_fault_code(*, codes: list[ErrorCode]) -> ErrorCode | None:
    """The code an answer takes among the codes of several faults it reports at once, ``None`` for no codes.

    A code whose verdict is ``no`` comes before a retryable one, so that no client retries what someone must fix;
    then the method's, the operator's, the account's, the input's and the runtime's, in that order; then the first
    given. Every fault still rides the answer as an item with its own code.

    Args:
        codes: The codes of the faults, in the order they were found.

    Returns:
        The code the answer takes.
    """
    if not codes:
        return None
    return min(
        codes,
        key=lambda code: (_retry_rank(retry=error_code_spec(code).retry), _domain_rank(domain=error_code_spec(code).domain)),
    )


def code_is_method_domain(*, code: ErrorCode) -> bool:
    """Whether the method's author must act on a code: its registry domain is ``method``."""
    match error_code_spec(code).domain:
        case ProblemDomain.METHOD:
            return True
        case ProblemDomain.INPUT | ProblemDomain.ACCOUNT | ProblemDomain.OPERATOR | ProblemDomain.RUNTIME:
            return False
