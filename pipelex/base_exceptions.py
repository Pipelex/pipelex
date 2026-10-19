from collections.abc import Iterator
from enum import StrEnum
from typing import Any, ClassVar, Self

from mthds.protocol.problem.registry import CoreCode, ProblemDomain
from pydantic import BaseModel, ConfigDict, Field
from typing_extensions import override

from pipelex.cogt.inference.error_classification import ProviderErrorMetadata, UserAction
from pipelex.errors.error_code_declaration import (
    ABSTRACT_ERROR,
    AbstractError,
    ErrorCodeDeclaration,
    ErrorCodeSet,
    InheritsCause,
    declared_error_codes,
    describe_error_code_declaration,
)
from pipelex.errors.error_codes import ErrorCode, error_code_spec
from pipelex.errors.registry.pipelex_codes import PipelexErrorCode
from pipelex.migration.plan import MigrationPlan
from pipelex.suggested_fix import SuggestedFix
from pipelex.validation_error_types import ValidationErrorType


def iter_cause_chain(exc: BaseException) -> Iterator[BaseException]:
    """Yield ``exc`` and each error along its ``__cause__`` chain, exactly once.

    The single cycle-guarded ``__cause__`` walk shared across the error-reporting
    paths — classification recovery (``find_inference_error_category_in_chain``),
    the is-self cycle check in ``_enrich_error_report_from_cause``, LLM-error
    formatting (``PipeLLM._format_llm_error``), and the agent-CLI source-location
    extraction. The ``id()`` set makes a cyclic ``__cause__`` chain terminate
    instead of spinning forever. That walk runs *on the error path*, so getting it
    wrong would turn the failure being reported into a hang — centralizing it here
    means it is written, and audited, once.
    """
    node: BaseException | None = exc
    seen: set[int] = set()
    while node is not None and id(node) not in seen:
        seen.add(id(node))
        yield node
        node = node.__cause__


# Placeholder ``message`` substituted into a STRICT-mode serialization of a
# report whose ``message`` is not caller-facing copy. A report flagged
# ``caller_facing_message`` keeps its original ``message`` instead.
INTERNAL_ERROR_PLACEHOLDER = "An internal error occurred."

# Stable identifiers preserved verbatim on every STRICT envelope, regardless of
# the report's ``caller_facing_message`` flag. ``message`` and ``user_action``
# are intentionally absent and handled separately by the two STRICT branches:
# the caller-facing branch keeps both, the redacted branch replaces ``message``
# with ``INTERNAL_ERROR_PLACEHOLDER`` and drops ``user_action``.
# ``provider_metadata`` is also absent here — it is reattached on both branches
# as a curated subset (see ``_STRICT_PROVIDER_METADATA_KEPT_FIELDS``).
# Provider/model attribution (``provider``, ``model``) is unconditionally
# excluded: it never belongs on an external surface, whatever the report's
# ``error_domain``. The internal ``caller_facing_message`` flag is likewise
# excluded — it is redaction plumbing that rides only the VERBOSE round-trip
# format, never the lossy external projection.
#
# Single source of truth for both STRICT branches. Adding a new top-level
# ``ErrorReport`` field is one decision: include it here to surface it on both
# branches, or leave it out to keep both branches consistently silent.
#
# ``validation_errors`` IS surfaced: it describes the caller's own submitted
# bundle (per-error diagnostics on a ``ValidateBundleError``), not server
# internals, so redacting it would gut the hosted path's diagnostics. It only
# ever rides a ``ValidateBundleError`` report (a caller-facing INPUT error), but
# it is kept here — not by the caller-facing branch's bespoke logic — so the
# decision lives in this one allowlist.
#
# Caveat — ``validation_errors[].source``: on the *in-memory* validate and run
# paths ``source`` is the caller-supplied logical source (e.g. ``api://bundle-0.mthds``),
# which is the hosted/STRICT case and safe to surface; a bundle of an address-based
# dependency is named by the package's address and its path inside the package, and
# a file of the host's own library directories is withheld from the verdict, source
# and messages alike (``withholding_host_library_files``). On the *on-disk* path a
# ``source`` is a real server filesystem path, and STRICT does NOT redact it
# (consistent with ``DisclosureMode`` being a classification-projection, not a
# path-leak shield — see its docstring). A hosted surface that validates from disk
# should therefore use the in-memory path with logical sources rather than rely on
# STRICT to scrub the path.
#
# ``migration`` is NOT surfaced, and the contrast with ``validation_errors`` is
# the whole reason: a pending configuration migration describes the *host's* own
# configuration directories — server filesystem paths, and the shape of a
# deployment's settings — never anything the caller submitted. It is diagnostics
# for whoever runs the process, which on a hosted surface is not the caller.
_STRICT_KEPT_FIELDS: frozenset[str] = frozenset(
    {"code", "error_type", "title", "type_uri", "error_domain", "error_category", "retryable", "validation_errors"}
)

# The curated subset of ``ProviderErrorMetadata`` that survives STRICT
# projection. ``status_code`` and ``retry_after_seconds`` are actionable client
# hints (HTTP status mapping, ``Retry-After`` header) — they are not provider
# attribution. Every other ``ProviderErrorMetadata`` field carries either
# provider identity (``provider``, ``provider_error_code``, ``sdk_exception_type``)
# or internal correlation IDs / free-form text (``request_id``, ``message``) that
# the external surface has no business seeing.
_STRICT_PROVIDER_METADATA_KEPT_FIELDS: frozenset[str] = frozenset({"status_code", "retry_after_seconds"})


def _redact_provider_metadata_for_strict(metadata_payload: dict[str, Any]) -> dict[str, Any] | None:
    """Project a ``ProviderErrorMetadata`` payload through STRICT's curated subset.

    Keeps only the fields in :data:`_STRICT_PROVIDER_METADATA_KEPT_FIELDS`
    (``status_code`` / ``retry_after_seconds``). Returns ``None`` when no curated
    field is present, so the caller can omit the key entirely rather than emit
    an empty dict on the wire.
    """
    curated = {key: value for key, value in metadata_payload.items() if key in _STRICT_PROVIDER_METADATA_KEPT_FIELDS}
    return curated or None


# Fields already mapped into RFC 7807 standard slots (``detail`` / ``title`` /
# ``type``) by ``to_problem_document`` — must NOT be echoed as extension
# members on the returned envelope.
_RFC7807_MAPPED_FIELDS: frozenset[str] = frozenset({"message", "title", "type_uri"})

# Fields ``to_problem_document`` must not surface as RFC 7807 extension members:
# the standard-slot mappings plus ``caller_facing_message``, which is internal
# redaction plumbing carried on the serialized report, not consumer-facing
# classification.
_PROBLEM_DOCUMENT_OMITTED_FIELDS: frozenset[str] = _RFC7807_MAPPED_FIELDS | frozenset({"caller_facing_message"})


class DisclosureMode(StrEnum):
    """How much detail to include when serializing an ``ErrorReport`` for external surfaces.

    - ``VERBOSE``: all classification fields plus the original ``message``. Use for
      internal-trust boundaries (webhook payloads, internal RPCs) where the receiver
      decides what to expose further downstream. ``from_dict(to_dict(report, VERBOSE))``
      reconstructs the original report exactly.

    - ``STRICT``: a lossy projection for untrusted external surfaces.
      ``provider`` / ``model`` are dropped unconditionally — provider/model
      attribution never belongs on an external surface. ``provider_metadata`` is
      projected through a curated subset: only ``status_code`` and
      ``retry_after_seconds`` survive (actionable HTTP client hints, not provider
      attribution). The ``message`` is then projected by *provenance*:

      - A report flagged :attr:`ErrorReport.caller_facing_message` keeps its
        ``message`` and ``user_action``. The flag is set by error classes whose
        message is genuinely caller-facing copy — text describing the *caller's
        own* input, e.g. ``MthdsParserError`` (a ``.mthds`` syntax error)
        or ``ValidateBundleError`` (a failed bundle validation) — or, for a
        class raised both for the caller's faults and for others, by the raise
        site that knows, through :meth:`PipelexError.as_caller_fault`.
      - Every other report has its ``message`` replaced with a generic
        placeholder and its ``user_action`` dropped, keeping only the stable
        identifiers (``error_type``, ``error_domain``, ``error_category``,
        ``retryable``, ``title``, ``type_uri``).

      ``from_dict(to_dict(report, STRICT))`` does NOT reconstruct the original —
      STRICT is lossy. Beyond the redacted message and dropped fields, a STRICT
      payload that carries ``provider_metadata`` cannot be rehydrated at all:
      the curated dict lacks the ``provider`` / ``sdk_exception_type`` fields
      required by :class:`pipelex.cogt.inference.error_classification.ProviderErrorMetadata`,
      so :meth:`ErrorReport.from_dict` raises :class:`pydantic.ValidationError`.
      Consumers of a STRICT payload must read the dict directly (e.g. via
      :meth:`ErrorReport.to_problem_document`) rather than rebuilding an
      ``ErrorReport`` through ``from_dict``. Use VERBOSE on any surface that
      needs round-trip semantics (webhook payloads, internal RPCs).

      STRICT keys the ``message`` decision on the *provenance of the message*,
      not on ``error_domain``: ``error_domain`` is inherited up the ``__cause__``
      chain, so a domain-less wrapper raised ``from`` an ``INPUT`` cause is
      classified ``INPUT`` while still carrying its own internal ``message`` —
      which STRICT must redact. ``caller_facing_message`` is not inherited, so it
      tracks the wrapper's own message correctly. STRICT is a
      *classification-projection*, **not a path-leak shield**: if a genuinely
      caller-facing ``message`` could surface a server-resolved path or secret,
      fix the upstream message — don't expand STRICT mode's scope.

      The curated ``provider_metadata`` subset, in contrast, IS inherited up the
      ``__cause__`` chain via :meth:`PipelexError._enrich_error_report_from_cause`
      and is preserved on both STRICT branches. A wrapper error (e.g.
      ``PipelexUnexpectedError``) raised ``from`` a categorized ``CogtError``
      therefore surfaces the cause's ``status_code`` / ``retry_after_seconds`` on
      the STRICT envelope, even though the wrapper itself advertises no provider
      relationship. This is deliberate, by the same reasoning as the previous
      paragraph: the curated fields are HTTP client hints (status mapping,
      ``Retry-After`` header), not provider attribution, and STRICT does not
      hide internal failure topology.
    """

    VERBOSE = "verbose"
    STRICT = "strict"


class ErrorDomain(StrEnum):
    """Classifies where an error originates, so consumers can route it.

    - INPUT: the caller can fix it (bad .mthds, wrong args, malformed JSON).
    - CONFIG: an environment or configuration change is needed.
    - RUNTIME: a failure that occurred during execution.

    A report's domain is no longer declared by an error class: it is read from the domain the registry
    gives the error's code, through :meth:`from_problem_domain`, until the problem document carries that
    domain itself.
    """

    INPUT = "input"
    CONFIG = "config"
    RUNTIME = "runtime"

    @classmethod
    def from_problem_domain(cls, problem_domain: ProblemDomain) -> "ErrorDomain":
        """The report domain of a code's registry domain.

        The caller's input and the method the caller sent are both the caller's to change, so both read
        ``INPUT``; the account's owner and whoever runs the runtime act outside the request, so both read
        ``CONFIG``; and ``runtime`` stays ``RUNTIME``.
        """
        match problem_domain:
            case ProblemDomain.INPUT | ProblemDomain.METHOD:
                return cls.INPUT
            case ProblemDomain.ACCOUNT | ProblemDomain.OPERATOR:
                return cls.CONFIG
            case ProblemDomain.RUNTIME:
                return cls.RUNTIME

    @property
    def is_input(self) -> bool:
        """True for the caller-fixable input domain — read state through the enum rather than ``== ErrorDomain.INPUT``.

        Exhaustive ``match`` so a future domain forces this helper to be revisited
        rather than silently classifying as non-input.
        """
        match self:
            case ErrorDomain.INPUT:
                return True
            case ErrorDomain.CONFIG | ErrorDomain.RUNTIME:
                return False


def error_domain_to_http_status(error_domain: ErrorDomain | str | None) -> int:
    """Map an error domain to an HTTP status code.

    Domain-level building block for downstream HTTP APIs that render an
    :class:`ErrorReport` as a response. When you have a full report, prefer
    :attr:`ErrorReport.http_status` — it layers the provider 429 (rate-limit)
    passthrough on top of this mapping. The library itself stays HTTP-agnostic —
    no web-framework import lives here, only the mapping table.

    Accepts a raw ``str`` because ``ErrorReport.error_domain`` is serialized as
    one. A value this version does not recognize (e.g. a report serialized by a
    newer Pipelex) is treated as unclassified rather than crashing rendering.

    - ``INPUT`` -> 422: the caller sent something it can fix (bad input).
    - ``CONFIG`` / ``RUNTIME`` -> 500: a server-side problem.
    - unknown / ``None`` -> 500: unclassified, treated as a server-side problem.
    """
    if isinstance(error_domain, str):
        try:
            error_domain = ErrorDomain(error_domain)
        except ValueError:
            error_domain = None
    match error_domain:
        case ErrorDomain.INPUT:
            return 422
        case ErrorDomain.CONFIG | ErrorDomain.RUNTIME:
            return 500
        case None:
            return 500


def error_domain_is_input(error_domain: ErrorDomain | str | None) -> bool:
    """True when ``error_domain`` is the caller-fixable ``INPUT`` domain.

    The serialized-form counterpart to :attr:`ErrorDomain.is_input`, mirroring
    :func:`error_domain_to_http_status`: it accepts the raw ``str`` / ``None``
    shape that :attr:`ErrorReport.error_domain` carries (and the value pulled out
    of a serialized problem-document dict), so HTTP consumers can branch on
    "is this the caller's mistake?" without re-implementing the coercion. Holds
    a single source of truth — it delegates the per-value decision to
    :attr:`ErrorDomain.is_input`.

    ``None`` or an unrecognized string (e.g. a report serialized by a newer
    Pipelex) is treated as non-input — the conservative default those consumers
    want, matching :func:`error_domain_to_http_status` which maps the same cases
    to a server-side 500.
    """
    if error_domain is None:
        return False
    try:
        return ErrorDomain(error_domain).is_input
    except ValueError:
        return False


class ValidationErrorCategory(StrEnum):
    """Which validation stage produced a :class:`ValidationErrorItem`.

    Mirrors the categorized error-data lists aggregated by ``ValidateBundleError``:
    blueprint validation (from the interpreter), pipe-factory failures (e.g. a
    missing concept), pipe/concept validation (e.g. a missing input variable
    or a type mismatch), and ``dry_run`` — one item per pipe whose dry run failed,
    located at the innermost failing pipe. On the report's advisory ``warnings``,
    ``dry_run`` marks a finding a dry run made without failing, such as a warning of
    a ``PipeDocGen`` step's template check.
    """

    BLUEPRINT_VALIDATION = "blueprint_validation"
    PIPE_FACTORY = "pipe_factory"
    PIPE_VALIDATION = "pipe_validation"
    DRY_RUN = "dry_run"

    @property
    def is_dry_run(self) -> bool:
        match self:
            case ValidationErrorCategory.DRY_RUN:
                return True
            case ValidationErrorCategory.BLUEPRINT_VALIDATION | ValidationErrorCategory.PIPE_FACTORY | ValidationErrorCategory.PIPE_VALIDATION:
                return False


class ValidationErrorItem(BaseModel):
    """One structured bundle-validation error, projected onto the error wire.

    The typed wire item carried by :attr:`ErrorReport.validation_errors`. Its
    fields are the *union* across the three ``ValidateBundleError`` error-data
    models (``PipelexBundleBlueprintValidationErrorData``, ``PipeFactoryErrorData``,
    ``PipesAndConceptValidationErrorData``); a given item only populates the
    subset its :attr:`category` produces, and the unset fields drop out of the
    ``exclude_none`` wire projection.

    The error channel is built exclusively by
    ``pipelex.pipeline.validation_errors.build_validation_error_items``, which both the agent
    CLI (``extract_validation_errors``) and the API path
    (``ValidateBundleError.to_error_report``) call — so the CLI's structured
    output and the API's 422 ``validation_errors`` can never drift. The same
    item type also carries the report's advisory ``warnings``, built by
    ``pipelex.pipeline.advisory_warnings``: a warning is the same shape of
    diagnostic, differing only in that it does not make the verdict invalid.

    ``source`` is the declaring file path (CLI) or the per-content source the API
    threads onto the in-memory load path — it hands a consumer the owning file
    for cross-file diagnostics. Lives here, alongside :class:`ErrorReport`,
    rather than next to the source error-data models because ``ErrorReport``
    references it as a typed field and ``base_exceptions`` must not import the
    ``pipelex.core`` error modules (which import back into this module).
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    category: ValidationErrorCategory = Field(strict=False)
    message: str
    # Typed against the closed registry in ``pipelex.validation_error_types``, so the vocabulary a
    # consumer can observe here IS that registry — an unregistered string cannot be constructed
    # onto an item. ``None`` stays legal for the parse-level residual, which reports a message with
    # no identified fault behind it. No ``strict=False`` here, unlike ``category`` above: pydantic
    # refuses that constraint on a union field, and the model declares no strict config, so the
    # union already validates leniently — a plain wire string resolves to its registry member.
    error_type: ValidationErrorType | None = None
    pipe_code: str | None = None
    concept_code: str | None = None
    domain_code: str | None = None
    source: str | None = None
    field_path: str | None = None
    field_name: str | None = None
    variable_names: list[str] | None = None
    missing_concept_code: str | None = None
    missing_pipe_code: str | None = None
    declared_concepts: list[str] | None = None
    # The 1-based position a TOML syntax error was found at, carried by the parse-level residual so an
    # editor can anchor the diagnostic. Optional and additive, like ``declared_concepts``.
    line: int | None = None
    column: int | None = None
    # The unknown-model locators, carried by an ``unknown_model`` item: the model reference exactly as
    # the author wrote it, the model type the field takes (``llm``, ``text_extractor``, ``img_gen``,
    # ``search``), and the deck's close matches of the same kind, each spelled as a reference the field
    # accepts. Optional and additive, like ``declared_concepts``: every other item serializes unchanged.
    model_reference: str | None = None
    model_type: str | None = None
    suggestions: list[str] | None = None
    # The template-check locators, carried by a ``template_check_warning`` item: the template file as the
    # ``PipeDocGen`` step names it, and the place in it the engine's finding names, in the engine's own words
    # (a defined name, a Table, a cell, a shape, a tag). Optional and additive, like ``declared_concepts``.
    template_file: str | None = None
    template_location: str | None = None
    # Structured, deterministic fix for this error, when the fix planner derived one from the
    # enriched error data. Optional and additive: non-fixable items serialize unchanged under
    # ``exclude_none``.
    suggested_fix: SuggestedFix | None = None


class MigrationErrorBlock(BaseModel):
    """A pending configuration migration, reported alongside the error it explains.

    The structured half of the answer to *why does my configuration not load* — carried by
    :attr:`ErrorReport.migration`, and present only when a scan of this machine's configuration
    directories found something to say. **Consumers branch on its presence**, never on the
    message text: an absent block means the failure is not staleness.

    ``plans`` is the same shape ``pipelex-agent migrate --dry-run --format json`` emits under its
    own ``plans`` key, deliberately — an agent that reads one has already parsed the other, and a
    projection of its own here would be a second contract to keep in step with the first.

    Declared in this module rather than beside the migration engine for the same reason
    :class:`ValidationErrorItem` is: :class:`ErrorReport` references it as a typed field, and
    ``base_exceptions`` must not import the migration package's error modules, which import back
    into this one. ``pipelex.migration.plan`` holds itself to stdlib + pydantic + low-level
    siblings precisely so this import stays legal.

    > **No value read from a user's file is ever rendered** here either. The plans carry paths,
    > operation kinds and ledger-supplied values, and nothing else — the same mechanical rule the
    > migration report and the CLI output obey, on the third of the three channels it names.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    remedy: str
    """The command that applies whatever can be applied without a decision."""

    would_write: bool
    """Whether running ``remedy`` would actually rewrite any of these files.

    The block's *presence* says the migration history has something to report about this machine.
    It does not say the remedy repairs it, and this field is what separates the two. A block whose
    ``would_write`` is False carries a diagnosis and nothing to apply — a path no entry explains, a
    file that could not be read, an entry blocked before any of its operations landed — so naming
    ``remedy`` there would send a reader to a run that visits the files, writes nothing, and leaves
    the same refusal standing. The dry run is what carries the answer on that side.

    Independent of :attr:`needs_attention`, and the pair is never both False: a file with nothing to
    write and nothing for a person is clean, and clean files are not in ``plans``."""

    needs_attention: bool
    """Whether something here is a person's to resolve rather than the tool's — a blocked file, a
    blocked entry, or a path no ledger entry explains. When this is False, running ``remedy`` is
    expected to be enough."""

    plans: list[MigrationPlan]
    """One per configuration file the scan found something in. Files with nothing to say are left
    out: unlike the ``migrate`` commands' report, which answers *what did the walk visit*, this
    block answers *what is wrong with this machine's configuration*."""


class ErrorReport(BaseModel):
    """Structured error report — single source of truth for all error serialization.

    Used by CLI JSON output, agent output, and Temporal error details.

    ``code`` is the registry code the error resolved to (:meth:`PipelexError.resolve_error_code`): a core code
    of the MTHDS standard or a Pipelex code. ``title`` and ``type_uri`` are the code's title and the code's
    documentation page, and ``error_domain`` and ``retryable`` are read from the domain and the retry verdict
    the registry gives the code, so that no raise site sets them independently: two cases that need different
    verdicts are two codes. Consumers never humanize or kebab-case a class name themselves.

    Frozen: wrappers must rebuild via :meth:`model_copy` rather than mutate, so
    a cause-enrichment pass cannot accidentally overwrite an outer wrapper's
    identity in-place.
    """

    model_config = ConfigDict(frozen=True, extra="forbid", arbitrary_types_allowed=True)

    code: str
    error_type: str
    message: str
    title: str
    type_uri: str
    error_category: str | None = None
    error_domain: str | None = None
    retryable: bool | None = None
    user_action: UserAction | None = None
    model: str | None = None
    provider: str | None = None
    provider_metadata: ProviderErrorMetadata | None = None
    # True when ``message`` was authored as caller-facing copy — set at report
    # construction from ``PipelexError._authors_caller_facing_message``, or from
    # the raise site's :meth:`PipelexError.as_caller_fault`. STRICT
    # disclosure keys its ``message`` passthrough on this flag (see
    # :class:`DisclosureMode`). Defaults to False so an unflagged report — and
    # any payload that predates the field — is redacted, never leaked.
    caller_facing_message: bool = False
    # Structured per-error diagnostics on a bundle-validation failure. Populated
    # only by ``ValidateBundleError.to_error_report`` (None on every other
    # report), so the 422 problem document carries the same machine-mappable
    # items the agent CLI emits. Surfaced under STRICT disclosure (see
    # ``_STRICT_KEPT_FIELDS``): these describe the caller's own submitted bundle,
    # not server internals.
    validation_errors: list[ValidationErrorItem] | None = None
    # A pending configuration migration that explains this failure. Populated only by
    # ``PipelexConfigError`` reports whose raiser ran a scan (see
    # ``pipelex.core.validation.report_validation_error``); None on every other report, so a
    # consumer branching on its presence is asking exactly "is my configuration stale?".
    # Deliberately outside ``_STRICT_KEPT_FIELDS`` — it describes the host's own configuration
    # directories, not the caller's submission.
    migration: MigrationErrorBlock | None = None

    def to_dict(self, *, disclosure_mode: DisclosureMode = DisclosureMode.VERBOSE) -> dict[str, Any]:
        """Return a dict with only non-None fields, projected through ``disclosure_mode``.

        ``VERBOSE`` is the strict inverse of :meth:`from_dict` — every populated
        field round-trips. ``STRICT`` is a lossy projection (see
        :class:`DisclosureMode`): ``provider`` / ``model`` are always dropped,
        ``provider_metadata`` is projected through the curated subset (just
        ``status_code`` and ``retry_after_seconds``), and unless the report is
        flagged :attr:`caller_facing_message` its ``message`` is replaced with a
        generic placeholder and ``user_action`` is dropped, leaving only the
        stable identifiers plus the curated ``provider_metadata`` slice.
        """
        payload = self.model_dump(exclude_none=True)
        if self.migration is not None:
            # JSON mode for this field alone. ``MigrationPlan`` carries real ``Path`` values, and
            # a payload holding one is not serializable by ``json.dumps`` — which is what the
            # webhook delivery path hands this dict to. Dumping the whole report in JSON mode
            # instead would re-serialize every other field too, so the narrow fix is the safe one.
            # ``from_dict`` still round-trips: pydantic accepts a string for a ``Path`` field.
            payload["migration"] = self.migration.model_dump(mode="json")
        # ``caller_facing_message`` is redaction plumbing, not consumer-facing
        # classification: emit it only when set, so the common (non-caller-facing)
        # report serializes exactly as a report without the field would.
        # ``from_dict`` defaults it back to False when absent, so the round-trip
        # still holds.
        if not self.caller_facing_message:
            payload.pop("caller_facing_message", None)
        match disclosure_mode:
            case DisclosureMode.VERBOSE:
                return payload
            case DisclosureMode.STRICT:
                # Both STRICT branches start from the same allowlist — single
                # source of truth, so adding a new top-level ``ErrorReport``
                # field is one decision (include / exclude), not two.
                projected: dict[str, Any] = {key: payload[key] for key in _STRICT_KEPT_FIELDS if key in payload}
                if self.caller_facing_message:
                    # The error class that authored this message designed it as
                    # caller-facing copy — reflect it (and ``user_action``) back
                    # on top of the shared allowlist.
                    projected["message"] = payload["message"]
                    if "user_action" in payload:
                        projected["user_action"] = payload["user_action"]
                else:
                    projected["message"] = INTERNAL_ERROR_PLACEHOLDER
                # Reattach a curated ``provider_metadata`` slice — even on the
                # fully-redacted branch, ``status_code`` and ``retry_after_seconds``
                # are actionable client hints (HTTP status mapping, ``Retry-After``
                # header) that the HTTP adapter needs to emit a useful response.
                if "provider_metadata" in payload:
                    curated_metadata = _redact_provider_metadata_for_strict(payload["provider_metadata"])
                    if curated_metadata is not None:
                        projected["provider_metadata"] = curated_metadata
                return projected

    def to_problem_document(
        self,
        *,
        instance: str | None = None,
        request_id: str | None = None,
        disclosure_mode: DisclosureMode = DisclosureMode.VERBOSE,
    ) -> dict[str, Any]:
        """Render this report as an RFC 7807 ``application/problem+json`` envelope.

        The runner stays HTTP-agnostic — this returns a plain ``dict`` that
        downstream HTTP adapters serialize as JSON. The standard 7807 slots are
        sourced from the report:

        - ``type`` from :attr:`type_uri`
        - ``title`` from :attr:`title`
        - ``status`` from :attr:`http_status`
        - ``detail`` from :attr:`message` (subject to ``disclosure_mode`` redaction)
        - ``instance`` from the ``instance`` arg (URN provided by the caller)

        Pipelex-native classification fields ride as extension members
        (``error_type`` / ``error_domain`` / ``error_category`` / ``retryable`` /
        ``user_action`` / ``model`` / ``provider`` / ``provider_metadata``).
        ``type_uri`` and ``title`` are mapped — not duplicated — so the returned
        dict has exactly one ``title`` key. The ``caller_facing_message`` flag is
        internal redaction plumbing and is never echoed onto the envelope. When
        the caller supplies a ``request_id``, it rides as an extension member too.
        """
        payload = self.to_dict(disclosure_mode=disclosure_mode)
        document: dict[str, Any] = {
            "type": self.type_uri,
            "title": self.title,
            "status": self.http_status,
            "detail": payload["message"],
        }
        if instance is not None:
            document["instance"] = instance
        if request_id is not None:
            document["request_id"] = request_id
        for key, value in payload.items():
            if key in _PROBLEM_DOCUMENT_OMITTED_FIELDS:
                continue
            document[key] = value
        return document

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "ErrorReport":
        """Rebuild an ``ErrorReport`` from a :meth:`to_dict` payload — the strict inverse of :meth:`to_dict` in ``VERBOSE`` mode.

        Used to recover a report that crossed a serialization boundary (e.g. a
        Temporal ``ApplicationError.details`` payload) so it re-enters the
        ``to_error_report()`` world. The nested ``UserAction`` /
        ``ProviderErrorMetadata`` models round-trip through their dict form.

        Strict: ``ErrorReport`` is ``extra="forbid"``, so a malformed dict
        raises :class:`pydantic.ValidationError`. Within a single deploy the
        writer (activity bridge) and reader (submitter) share the schema, so a
        validation failure is an internal contract bug. ``recover_error_report``
        catches it to keep failure-webhook delivery intact; any other caller
        should treat it as a bug to fix.
        """
        return cls.model_validate(data)

    @classmethod
    def make_for_code(
        cls,
        *,
        code: ErrorCode,
        error_type: str,
        message: str,
        user_action: UserAction | None = None,
        caller_facing_message: bool = False,
        validation_errors: list[ValidationErrorItem] | None = None,
    ) -> "ErrorReport":
        """Build the report of an error that carries ``code``, reading from the registry what the code decides.

        The title, the documentation page, the domain and the retry verdict are the code's, so a report built here
        can never disagree with its code. ``PipelexError.to_error_report`` builds every error's report this way.

        Args:
            code: The registry code the error resolved to.
            error_type: The error's class name.
            message: The error's message.
            user_action: The next step its raise site named, when it named one.
            caller_facing_message: Whether the message is caller-facing copy, which STRICT disclosure keeps.
            validation_errors: The structured items of a bundle-validation refusal.

        Returns:
            The report.
        """
        spec = error_code_spec(code)
        return cls(
            code=code,
            error_type=error_type,
            message=message,
            title=spec.title,
            type_uri=spec.type_uri,
            error_domain=ErrorDomain.from_problem_domain(spec.domain),
            retryable=spec.invites_retry,
            user_action=user_action,
            caller_facing_message=caller_facing_message,
            validation_errors=validation_errors,
        )

    def user_action_detail(self) -> str | None:
        """Return the free-form advice text on ``user_action``, or ``None`` when absent."""
        return self.user_action.detail if self.user_action is not None else None

    @property
    def http_status(self) -> int:
        """HTTP status code for this error, for downstream HTTP API adapters.

        A provider 429 (rate limit) takes precedence so the API can surface a
        ``Retry-After`` header from ``provider_metadata.retry_after_seconds``;
        otherwise the status follows ``error_domain`` (see
        :func:`error_domain_to_http_status`, which also tolerates an
        ``error_domain`` string this version does not recognize — e.g. a report
        serialized by a newer Pipelex — rather than crashing response rendering).
        """
        if self.provider_metadata is not None and self.provider_metadata.status_code == 429:
            return 429
        return error_domain_to_http_status(self.error_domain)


_FALLBACK_ERROR_CODE: ErrorCode = CoreCode.RUNTIME_UNEXPECTED
"""The code of an error whose cause chain names none: the catch-all, ``runtime.unexpected``, step ``report``."""


class PipelexError(Exception):
    """The root of every error Pipelex raises, each carrying a registry code.

    Every subclass declares ``error_code`` in its own class body, as :mod:`pipelex.errors.error_code_declaration`
    describes: the code it raises, the set its raise sites choose from, that it takes its cause's code, or that it
    is an abstract base. The code decides the report's title, documentation page, domain and retry verdict, so a
    class declares none of them; ``tests/unit/pipelex/errors/test_error_code_gate.py`` fails the build on a
    subclass that declares no code, and ``docs/under-the-hood/error-model.md`` explains the model.
    """

    error_code: ClassVar[ErrorCodeDeclaration] = ABSTRACT_ERROR
    user_action: UserAction | None = None

    # When True, ``ErrorReport``s built from this class keep their ``message``
    # verbatim under STRICT disclosure (see :class:`DisclosureMode`). Set it on
    # classes whose ``message`` is genuinely caller-facing copy — text describing
    # the *caller's own* input (a ``.mthds`` syntax error, a failed bundle
    # validation). It is consulted by plain attribute access, so it inherits
    # normally — a subclass of a caller-facing error stays caller-facing.
    _authors_caller_facing_message: ClassVar[bool] = False
    # The per-instance counterpart of ``_authors_caller_facing_message``, set only by
    # :meth:`as_caller_fault`, for a class whose instances are not all the caller's fault.
    _raised_as_caller_fault: bool = False
    # The code the raise site chose with :meth:`with_error_code`, from the codes the class declares.
    _chosen_error_code: ErrorCode | None = None

    def __init_subclass__(cls, **kwargs: Any) -> None:
        super().__init_subclass__(**kwargs)
        declaration = cls.__dict__.get("error_code")
        if declaration is not None and not isinstance(declaration, (CoreCode, PipelexErrorCode, ErrorCodeSet, InheritsCause, AbstractError)):
            msg = (
                f"{cls.__qualname__}.error_code must be a CoreCode, a PipelexErrorCode, an ErrorCodeSet, an InheritsCause "
                f"or ABSTRACT_ERROR, not {declaration!r}."
            )
            raise TypeError(msg)

    def __init__(self, message: str):
        super().__init__(message)
        self.message = message

    def with_error_code(self, error_code: ErrorCode) -> Self:
        """Choose, where this error is raised, which of its class's codes it carries.

        A class whose raise sites need different codes declares them as an :class:`ErrorCodeSet`, or as the
        codes an :class:`InheritsCause` class's raise site may choose, and the raise site that knows which
        applies chooses it here: ``raise SomeError(msg).with_error_code(CoreCode.MODEL_UNAVAILABLE)``. A chosen
        code stops the cause walk at this error, as a declared code does.

        Args:
            error_code: One of the codes the class declares.

        Returns:
            This error, so that the raise site reads ``raise SomeError(msg).with_error_code(code)``.

        Raises:
            ValueError: When the class does not declare the code, which is a fault of the raise site; the gate
                test checks every raise site that chooses a code on the class it constructs.
        """
        declared_codes = declared_error_codes(type(self).error_code)
        if error_code not in declared_codes:
            declared = describe_error_code_declaration(type(self).error_code)
            msg = f"{type(self).__name__} does not declare the code '{error_code}': its declaration is {declared}."
            raise ValueError(msg)
        self._chosen_error_code = error_code
        return self

    @property
    def own_error_code(self) -> ErrorCode | None:
        """The code this error carries by itself, ``None`` when it takes its cause's.

        The code its raise site chose; else its class's code, or the default of its class's set; else ``None``
        for a class that takes its cause's code or an abstract base.
        """
        if self._chosen_error_code is not None:
            return self._chosen_error_code
        declaration = type(self).error_code
        if isinstance(declaration, ErrorCodeSet):
            return declaration.default
        if isinstance(declaration, (InheritsCause, AbstractError)):
            return None
        return declaration

    @property
    def implied_error_code(self) -> ErrorCode | None:
        """The code this error implies without carrying it, ``None`` for an error that implies none.

        An inference error built by hand with a category and no code implies its category's code
        (``CogtError``). :meth:`resolve_error_code` reads it in the same walk as the codes the chain carries: a code
        any error along the chain carries by itself wins over it, and the deepest implied code wins over a wrapper's
        fallback.
        """
        return None

    def resolve_error_code(self) -> ErrorCode:
        """The registry code this error reports, resolved along its ``__cause__`` chain.

        The walk starts at this error and stops at the first error that carries a code by itself
        (:attr:`own_error_code`). It descends through every error that takes its cause's code, and through an
        abstract base raised by mistake, and stops at a cause that is not a Pipelex error. When no error along
        the way carries a code, the error reports the code the deepest error implies (:attr:`implied_error_code`),
        else the fallback of the deepest error that takes its cause's code, and ``runtime.unexpected`` when none
        names one. The walk is the one cycle-guarded ``iter_cause_chain``, which no error's code walks again.
        """
        implied_code: ErrorCode | None = None
        fallback: ErrorCode | None = None
        for node in iter_cause_chain(self):
            if not isinstance(node, PipelexError):
                break
            own_code = node.own_error_code
            if own_code is not None:
                return own_code
            implied_code = node.implied_error_code or implied_code
            declaration = type(node).error_code
            if isinstance(declaration, InheritsCause):
                fallback = declaration.fallback
        return implied_code or fallback or _FALLBACK_ERROR_CODE

    def as_caller_fault(self, *, user_action: UserAction | None = None) -> Self:
        """Say, where this error is raised, that its message describes only the caller's own method or inputs.

        Its report then carries a caller-facing ``message``, which STRICT disclosure keeps (see
        :class:`DisclosureMode`): the fact a class declares with ``_authors_caller_facing_message = True``. It
        serves a class raised both for the caller's faults and for faults that are not the caller's, which
        therefore cannot declare it: the raise site that knows says so there, for this one error. Who must act
        is the code's domain, which the raise site chooses with :meth:`with_error_code` when the class declares
        a set. A plain wrapper raised from this error never inherits the caller-facing flag, since its own
        message is not this one.

        The raise site vouches for the message: it names only the caller's own method and data
        (pipe codes, concept codes, variable names, the values the caller sent), never a server
        path, a secret, or the text of an exception that is not a Pipelex error.

        Args:
            user_action: The next step for the caller, when the raise site can name one.

        Returns:
            This error, so that the raise site reads ``raise SomeError(msg).as_caller_fault()``.
        """
        self._raised_as_caller_fault = True
        if user_action is not None:
            self.user_action = user_action
        return self

    def to_error_report(self) -> ErrorReport:
        """Return a structured error report, enriched from the ``__cause__`` chain.

        The report's ``code`` is :meth:`resolve_error_code`, and its title, documentation page, domain and
        retry verdict are the code's. Wrapper exceptions (``PipeRunError`` -> ``PipeRouterError`` ->
        ``PipelineExecutionError``) carry no ``error_category`` / ``model`` / ``provider`` of their own: this
        surfaces those fields from the underlying exception (typically a ``CogtError``) so they survive every
        wrapping layer up to the CLI / HTTP boundary.

        Subclasses override to include additional fields (error_category, model,
        etc.); an override must end with ``self._enrich_error_report_from_cause(report)``
        so the cause-chain enrichment stays uniform across the hierarchy.
        """
        report = ErrorReport.make_for_code(
            code=self.resolve_error_code(),
            error_type=type(self).__name__,
            message=self.message,
            user_action=self.user_action,
            caller_facing_message=self._authors_caller_facing_message or self._raised_as_caller_fault,
        )
        return self._enrich_error_report_from_cause(report)

    def _enrich_error_report_from_cause(self, report: ErrorReport) -> ErrorReport:
        """Fill the ``None`` diagnostic fields of ``report`` from the ``__cause__`` chain.

        A wrapper keeps its own ``code`` and everything the code decides, ``error_type``, ``message`` and
        ``caller_facing_message``, but inherits every field it does not set itself — ``error_category``,
        ``user_action``, ``model``, ``provider``, ``provider_metadata`` — from the underlying ``PipelexError``
        that knows them. The code needs no inheriting here: :meth:`resolve_error_code` already walked the chain.
        ``caller_facing_message`` is pointedly NOT inherited: it records the provenance of ``report.message``,
        which is always the wrapper's own message. ``to_error_report()`` overrides call this so enrichment stays
        uniform.
        """
        cause = self.__cause__
        if not isinstance(cause, PipelexError):
            return report
        # Guard against a cyclic __cause__ chain: if self is reachable from cause, recursing
        # into cause.to_error_report() would never terminate. Bail out with the enrichment
        # gathered so far rather than raising a RecursionError from the error-reporting path.
        if any(node is self for node in iter_cause_chain(cause)):
            return report
        cause_report = cause.to_error_report()
        # Only the cause-merged diagnostic fields are updated; the wrapper-wins
        # fields (code, error_type, message, title, type_uri, error_domain, retryable,
        # caller_facing_message) stay untouched, so a future wrapper-wins field added
        # to ErrorReport does not need to be re-listed here.
        # Footgun: ``provider_metadata`` uses whole-object OR, and a Pydantic
        # model instance is always truthy — a wrapper that attached
        # attribution-only metadata (no ``status_code`` / ``retry_after_seconds``)
        # discards the cause's actionable hints. Pinned by
        # ``tests/unit/pipelex/cogt/test_cogt_provider_metadata_wrapper_wins.py``.
        return report.model_copy(
            update={
                "error_category": report.error_category or cause_report.error_category,
                "user_action": report.user_action or cause_report.user_action,
                "model": report.model or cause_report.model,
                "provider": report.provider or cause_report.provider,
                "provider_metadata": report.provider_metadata or cause_report.provider_metadata,
            }
        )


class PipelexUnexpectedError(PipelexError):
    """A fault of ours: an invariant that did not hold, or a host wired wrongly."""

    error_code: ClassVar[ErrorCodeDeclaration] = CoreCode.RUNTIME_UNEXPECTED


class PipelexConfigError(PipelexError):
    """A configuration this process cannot use, optionally with the migration that explains it."""

    error_code: ClassVar[ErrorCodeDeclaration] = ErrorCodeSet(
        default=PipelexErrorCode.CONFIG_INVALID,
        others=(PipelexErrorCode.CONFIG_SYNTAX, PipelexErrorCode.CONFIG_FILE_MISSING),
    )

    def __init__(self, message: str, *, migration: MigrationErrorBlock | None = None):
        super().__init__(message)
        self.migration = migration

    @override
    def to_error_report(self) -> ErrorReport:
        report = super().to_error_report()
        if self.migration is None:
            return report
        return report.model_copy(update={"migration": self.migration})


class PipelexSetupError(PipelexError):
    """A boot that cannot complete: an embedding host calling it wrongly, or a configuration it wraps."""

    error_code: ClassVar[ErrorCodeDeclaration] = InheritsCause(
        fallback=CoreCode.RUNTIME_MISCONFIGURED,
        others=(
            CoreCode.RUNTIME_UNEXPECTED,
            PipelexErrorCode.CONFIG_FILE_MISSING,
            PipelexErrorCode.CONFIG_INVALID,
            PipelexErrorCode.CONFIG_SYNTAX,
        ),
    )


class SecurityError(PipelexError):
    """Base for security-policy violations.

    Kept distinct from domain errors so security signals are not silently
    swallowed by domain-level `except` handlers (e.g. `except PipelexError`).
    """

    error_code: ClassVar[ErrorCodeDeclaration] = ABSTRACT_ERROR
