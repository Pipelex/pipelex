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

from pipelex.errors.registry.pipelex_codes import PIPELEX_ERROR_ENTRIES, PipelexErrorCode

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
        actor_step: The kind of the next step for the domain's actor.
        other_step: The kind of the next step for any other reader.
        type_uri: The code's documentation page: its registry's base URL, a slash, then the code.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    code: str
    title: str
    domain: ProblemDomain
    retry: RetryVerdict
    status: int | None
    actor_step: StepKind
    other_step: StepKind
    type_uri: str

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
            actor_step=core_spec.actor_step.kind,
            other_step=core_spec.other_step.kind,
            type_uri=f"{CORE_BASE_URL}/{core_code}",
        )
    for pipelex_code in PipelexErrorCode:
        entry = PIPELEX_ERROR_ENTRIES[pipelex_code]
        specs[pipelex_code] = ErrorCodeSpec(
            code=pipelex_code,
            title=entry.title,
            domain=ProblemDomain(entry.domain),
            retry=RetryVerdict(entry.retry),
            status=entry.status,
            actor_step=StepKind(entry.actor_step),
            other_step=StepKind(entry.other_step),
            type_uri=f"{PIPELEX_ERROR_BASE_URL}/{pipelex_code}",
        )
    return specs


_ERROR_CODE_SPECS: dict[str, ErrorCodeSpec] = _build_specs()


def error_code_spec(code: ErrorCode) -> ErrorCodeSpec:
    """What the registry declares about a registered code.

    Args:
        code: A core code or a Pipelex code.

    Returns:
        The code's title, domain, retry verdict, status, step kinds and type URI.
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
