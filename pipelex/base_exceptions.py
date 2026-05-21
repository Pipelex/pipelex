from typing import Any, ClassVar, cast

from pydantic import TypeAdapter
from pydantic.dataclasses import dataclass

from pipelex.cogt.inference.error_classification import ProviderErrorMetadata, UserAction
from pipelex.errors.error_manager import ErrorManager
from pipelex.tools.misc.string_utils import pascal_case_to_kebab, pascal_case_to_sentence
from pipelex.types import StrEnum

# Placeholder ``message`` substituted into a STRICT-mode serialization of a
# CONFIG / RUNTIME report. INPUT-domain reports keep their original message.
INTERNAL_ERROR_PLACEHOLDER = "An internal error occurred."

# Stable identifiers preserved verbatim in STRICT mode for CONFIG / RUNTIME
# reports. ``message`` is intentionally absent — STRICT replaces it with
# ``INTERNAL_ERROR_PLACEHOLDER`` unconditionally, not by passthrough.
_STRICT_KEPT_FIELDS: frozenset[str] = frozenset({"error_type", "title", "type_uri", "error_domain", "error_category", "retryable"})

# Fields already mapped into RFC 7807 standard slots (``detail`` / ``title`` /
# ``type``) by ``to_problem_document`` — must NOT be echoed as extension
# members on the returned envelope.
_RFC7807_MAPPED_FIELDS: frozenset[str] = frozenset({"message", "title", "type_uri"})


class DisclosureMode(StrEnum):
    """How much detail to include when serializing an ``ErrorReport`` for external surfaces.

    - ``VERBOSE``: all classification fields plus the original ``message``. Use for
      internal-trust boundaries (webhook payloads, internal RPCs) where the receiver
      decides what to expose further downstream. ``from_dict(to_dict(report, VERBOSE))``
      reconstructs the original report exactly.

    - ``STRICT``: stable identifiers only (``error_type``, ``error_domain``,
      ``error_category``, ``retryable``, ``title``, ``type_uri``). For
      ``CONFIG`` / ``RUNTIME`` reports, ``message`` is replaced with a generic
      placeholder and ``provider`` / ``model`` / ``provider_metadata`` /
      ``user_action`` are dropped. ``from_dict(to_dict(report, STRICT))`` for a
      CONFIG / RUNTIME report does NOT reconstruct the original — STRICT is a
      lossy projection.

      **``INPUT``-domain reports are returned unchanged in STRICT mode.** Their
      ``message`` is caller-influenced and reflecting it back is part of the
      contract. STRICT is a *classification-projection for server-side errors*,
      **not a path-leak shield**. If an ``INPUT`` message could surface a
      server-resolved path or secret, fix the upstream message — don't expand
      STRICT mode's scope.
    """

    VERBOSE = "verbose"
    STRICT = "strict"


class ErrorDomain(StrEnum):
    """Classifies where an error originates, so consumers can route it.

    - INPUT: the caller can fix it (bad .mthds, wrong args, malformed JSON).
    - CONFIG: an environment or configuration change is needed.
    - RUNTIME: a failure that occurred during execution.
    """

    INPUT = "input"
    CONFIG = "config"
    RUNTIME = "runtime"


def error_domain_to_http_status(error_domain: ErrorDomain | str | None) -> int:
    """Map an error domain to an HTTP status code.

    Domain-level building block for downstream HTTP APIs (``pipelex-relay``,
    ``pipelex-back-office``). When you have a full :class:`ErrorReport`, prefer
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


@dataclass(frozen=True, config={"extra": "forbid", "arbitrary_types_allowed": True})
class ErrorReport:
    """Structured error report — single source of truth for all error serialization.

    Used by CLI JSON output, agent output, and Temporal error details.

    ``title`` and ``type_uri`` are the stable identity pair surfaced to consumers
    (CLI, API, docs). Every ``PipelexError`` populates them automatically via
    :meth:`PipelexError.title` / :meth:`PipelexError.type_uri`; consumers never
    humanize or kebab-case a class name themselves.
    """

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

    def to_dict(self, disclosure_mode: DisclosureMode = DisclosureMode.VERBOSE) -> dict[str, Any]:
        """Return a dict with only non-None fields, projected through ``disclosure_mode``.

        ``VERBOSE`` is the strict inverse of :meth:`from_dict` — every populated
        field round-trips. ``STRICT`` is a lossy projection: for ``CONFIG`` /
        ``RUNTIME`` reports the disclosure-leaking fields (``user_action`` /
        ``model`` / ``provider`` / ``provider_metadata``) are dropped and
        ``message`` is replaced with a generic placeholder, keeping only the
        stable identifiers (see :class:`DisclosureMode`). ``INPUT``-domain
        reports pass through unchanged in STRICT mode because their ``message``
        is caller-influenced and reflecting it back is part of the contract.
        """
        payload = cast(
            "dict[str, Any]",
            _ERROR_REPORT_ADAPTER.dump_python(self, mode="python", exclude_none=True),
        )
        match disclosure_mode:
            case DisclosureMode.VERBOSE:
                return payload
            case DisclosureMode.STRICT:
                if self.error_domain == ErrorDomain.INPUT:
                    return payload
                redacted: dict[str, Any] = {key: payload[key] for key in _STRICT_KEPT_FIELDS if key in payload}
                redacted["message"] = INTERNAL_ERROR_PLACEHOLDER
                return redacted

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
        dict has exactly one ``title`` key. When the caller supplies a
        ``request_id``, it rides as an extension member too.
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
            if key in _RFC7807_MAPPED_FIELDS:
                continue
            document[key] = value
        return document

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "ErrorReport":
        """Rebuild an ``ErrorReport`` from a :meth:`to_dict` payload — the strict inverse of :meth:`to_dict`.

        Used to recover a report that crossed a serialization boundary (e.g. a
        Temporal ``ApplicationError.details`` payload) so it re-enters the
        ``to_error_report()`` world. The nested ``UserAction`` /
        ``ProviderErrorMetadata`` models round-trip through their dict form.

        Strict: ``ErrorReport`` is ``extra="forbid"``, so a malformed or
        schema-drifted dict raises :class:`pydantic.ValidationError`. Robustness
        against that failure (version skew, corrupted payload) belongs at the
        recovery call site, not here.
        """
        return _ERROR_REPORT_ADAPTER.validate_python(data)

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


# Cached at module scope because building a ``TypeAdapter`` per call rebuilds
# the validator + serializer schema (pydantic explicitly flags per-call
# construction as a hot-path pitfall). ``ErrorReport`` has no subclasses, so a
# single instance covers every ``to_dict`` / ``from_dict`` call.
_ERROR_REPORT_ADAPTER: TypeAdapter[ErrorReport] = TypeAdapter(ErrorReport)


def _humanize_class_name(class_name: str) -> str:
    """Derive a human-readable title from a ``PipelexError`` subclass name.

    Strips a trailing ``Error`` (if present) and runs the remainder through
    :func:`pipelex.tools.misc.string_utils.pascal_case_to_sentence`. Single-token
    leaves (``CogtError`` -> ``Cogt``) read awkwardly and warrant a curated
    :attr:`PipelexError._declared_title` override.
    """
    stem = class_name.removesuffix("Error") if class_name.endswith("Error") and class_name != "Error" else class_name
    return pascal_case_to_sentence(stem)


class PipelexError(Exception):
    error_domain: ErrorDomain | None = None
    user_action: UserAction | None = None

    # When declared *directly in a subclass body*, ``title()`` returns this
    # verbatim instead of auto-deriving from the class name. Use to fix awkward
    # auto-derives (e.g. ``CogtError`` -> ``Cogt``) or to publish a curated
    # user-facing label. ``title()`` consults ``cls.__dict__`` so inheritance
    # is bypassed — each class either declares its own title or auto-derives
    # from its own name. That is why the curated ``"Pipelex error"`` value is
    # set on ``PipelexError`` *itself* without leaking to bare subclasses.
    _declared_title: ClassVar[str | None] = "Pipelex error"
    # When declared *directly in a subclass body*, ``type_uri()`` returns this
    # verbatim instead of appending the kebab-cased class name to the
    # bootstrap-registered errors base URI. Same inheritance-bypass semantics
    # as ``_declared_title``.
    _declared_type_uri: ClassVar[str | None] = None

    @classmethod
    def title(cls) -> str:
        """Return the human-readable title for this error class.

        Used as the RFC 7807 ``title`` field on every ``ErrorReport``. Auto-derived
        from the class name unless a subclass sets :attr:`_declared_title` directly
        in its own body. Inheritance is bypassed so a parent's curated title does
        not silently capture every subclass — each class either declares its own
        title or auto-derives.
        """
        declared = cls.__dict__.get("_declared_title")
        if isinstance(declared, str):
            return declared
        return _humanize_class_name(cls.__name__)

    @classmethod
    def type_uri(cls) -> str:
        """Return the per-class documentation URI for this error class.

        Used as the RFC 7807 ``type`` field on every ``ErrorReport``. Auto-derived
        as ``<base_uri>/<kebab-class-name>`` unless a subclass sets
        :attr:`_declared_type_uri` directly in its own body. The ``base_uri`` is
        read from the :class:`pipelex.errors.error_manager.ErrorManager` singleton
        (which holds the :class:`pipelex.errors.errors_config.ErrorsConfig` set
        during Pipelex bootstrap); calling this before bootstrap completes raises
        :class:`RuntimeError` (callers that may run that early should declare a
        literal ``_declared_type_uri``).
        """
        declared = cls.__dict__.get("_declared_type_uri")
        if isinstance(declared, str):
            return declared
        base = ErrorManager.get_required_instance().base_uri
        return f"{base}/{pascal_case_to_kebab(cls.__name__)}"

    def __init__(self, message: str):
        super().__init__(message)
        self.message = message

    def to_error_report(self) -> ErrorReport:
        """Return a structured error report, enriched from the ``__cause__`` chain.

        Wrapper exceptions (``PipeRunError`` -> ``PipeRouterError`` ->
        ``PipelineExecutionError``) carry no ``error_category`` / ``retryable`` /
        ``model`` / ``provider`` of their own. This surfaces those classification
        fields from the underlying exception (typically a ``CogtError``) so they
        survive every wrapping layer up to the CLI / HTTP boundary.

        ``title`` / ``type_uri`` are *wrapper-wins*: enrichment never overwrites
        them with the cause's identity — the outermost wrapper's class is what
        the consumer sees.

        Subclasses override to include additional fields (error_category, model,
        etc.); an override must end with ``self._enrich_error_report_from_cause(report)``
        so the cause-chain enrichment stays uniform across the hierarchy.
        """
        report = ErrorReport(
            error_type=type(self).__name__,
            message=self.message,
            title=type(self).title(),
            type_uri=type(self).type_uri(),
            error_domain=self.error_domain,
            user_action=self.user_action,
        )
        return self._enrich_error_report_from_cause(report)

    def _enrich_error_report_from_cause(self, report: ErrorReport) -> ErrorReport:
        """Fill the ``None`` classification fields of ``report`` from the ``__cause__`` chain.

        A wrapper keeps its own ``error_type``, ``message``, ``title`` and
        ``type_uri`` but inherits every classification field it does not set
        itself — ``error_category``, ``error_domain``, ``retryable``, ``user_action``,
        ``model``, ``provider``, ``provider_metadata`` — from the underlying
        ``PipelexError`` that knows them. ``to_error_report()`` overrides call
        this so enrichment stays uniform.
        """
        cause = self.__cause__
        if not isinstance(cause, PipelexError):
            return report
        # Guard against a cyclic __cause__ chain: if self is reachable from cause, recursing
        # into cause.to_error_report() would never terminate. Bail out with the enrichment
        # gathered so far rather than raising a RecursionError from the error-reporting path.
        node: BaseException | None = cause
        seen: set[int] = set()
        while node is not None and id(node) not in seen:
            if node is self:
                return report
            seen.add(id(node))
            node = node.__cause__
        cause_report = cause.to_error_report()
        return ErrorReport(
            error_type=report.error_type,
            message=report.message,
            title=report.title,
            type_uri=report.type_uri,
            error_category=report.error_category or cause_report.error_category,
            error_domain=report.error_domain or cause_report.error_domain,
            retryable=report.retryable if report.retryable is not None else cause_report.retryable,
            user_action=report.user_action or cause_report.user_action,
            model=report.model or cause_report.model,
            provider=report.provider or cause_report.provider,
            provider_metadata=report.provider_metadata or cause_report.provider_metadata,
        )


class PipelexUnexpectedError(PipelexError):
    _declared_title = "Unexpected internal error"


class PipelexConfigError(PipelexError):
    error_domain = ErrorDomain.CONFIG


class PipelexSetupError(PipelexError):
    error_domain = ErrorDomain.CONFIG


class SecurityError(PipelexError):
    """Base for security-policy violations.

    Kept distinct from domain errors so security signals are not silently
    swallowed by domain-level `except` handlers (e.g. `except PipelexError`).
    """

    _declared_title = "Security policy violation"
