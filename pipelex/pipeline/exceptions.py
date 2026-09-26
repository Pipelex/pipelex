from typing_extensions import override

from pipelex.base_exceptions import ErrorDomain, ErrorReport, PipelexError, PipelexUnexpectedError, ValidationErrorItem
from pipelex.cogt.inference.error_classification import UserAction, UserActionKind
from pipelex.core.exceptions import (
    DryRunFailureErrorData,
    PipeFactoryErrorData,
    PipelexBundleBlueprintValidationErrorData,
    PipesAndConceptValidationErrorData,
)
from pipelex.pipeline.validation_errors import build_validation_error_items
from pipelex.system.pipe_run_mode import PipeRunMode


class PipeExecutionError(PipelexError):
    error_domain = ErrorDomain.RUNTIME


class PipelineExecutionError(PipelexError):
    """Wraps any failure that occurred while running a pipeline.

    Being a pure wrapper, it has no authoritative classification of its own:
    ``to_error_report()`` inherits ``error_domain`` / ``user_action`` from the
    wrapped ``__cause__`` chain (so a categorized ``CogtError`` keeps its
    ``WAIT_AND_RETRY`` / ``CHECK_BILLING`` action), and only falls back to a
    generic RUNTIME / UNKNOWN classification when the cause chain surfaces none.
    """

    def __init__(
        self,
        message: str,
        run_mode: PipeRunMode,
        pipe_code: str,
        output_name: str | None,
        pipe_stack: list[str],
    ):
        self.run_mode = run_mode
        self.pipe_code = pipe_code
        self.output_name = output_name
        self.pipe_stack = list(pipe_stack)  # snapshot: the live stack unwinds after this error is raised
        super().__init__(message)

    @override
    def to_error_report(self) -> ErrorReport:
        # The report is first enriched from the __cause__ chain; the generic
        # RUNTIME / UNKNOWN values are only a floor, applied when the cause
        # surfaced nothing — never overriding a categorized cause action.
        report = super().to_error_report()
        return report.model_copy(
            update={
                "error_domain": report.error_domain or ErrorDomain.RUNTIME,
                "user_action": report.user_action or UserAction(kind=UserActionKind.UNKNOWN, detail="Check pipe_stack to identify which pipe failed"),
            }
        )


class PipeStackOverflowError(PipelexError):
    def __init__(self, message: str, limit: int, pipe_stack: list[str]):
        self.limit = limit
        self.pipe_stack = list(pipe_stack)  # snapshot: the live stack unwinds after this error is raised
        super().__init__(message)


class PipelineManagerNotFoundError(PipelexError):
    pass


class PipelineManagerAlreadyExistsError(PipelexError):
    pass


class FixWriteConflictError(PipelexError):
    """A bundle changed after autofix read it but before the atomic commit."""


class FixTransactionError(PipelexUnexpectedError):
    """An autofix multi-file commit failed and could not be fully rolled back."""


def _summarize_bundle_validation_message(
    *,
    blueprint_errors: list[PipelexBundleBlueprintValidationErrorData],
    factory_errors: list[PipeFactoryErrorData],
    pipe_validation_errors: list[PipesAndConceptValidationErrorData],
    dry_run_failures: list[DryRunFailureErrorData],
    raw_message: str,
) -> str:
    """Compose a clean, author-facing top-line summary of a bundle-validation failure (disease C).

    The pydantic / interpreter path builds ``raw_message`` by ``str()``-ing a pydantic
    ``ValidationError``, leaking a ``Validation error(s): … Value errors: '<field>': Value error, …``
    dump (and prefixes like ``Pipe validation failed:`` / ``Could not load MTHDS bundle from '…'
    because of:``) into every surface that shows the top-line — the agent JSON ``message`` and the
    API report ``message`` / ``detail``. The per-error item messages are already clean and
    author-facing, so summarize from them instead of the raw pydantic string: the lone item
    message when there is one categorized error, or ``N validation errors (first: …)`` when there
    are several.

    Falls back to ``raw_message`` only when there is no categorized data at all — a parse-level
    failure (TOML syntax, an empty blueprint, a bundle elaborator) whose raw message is the
    authoritative description and the sole diagnostic. Reads only the ``message`` field off each
    error-data model — no fix planning — so it is cheap enough to run in ``__init__``. Ordering
    mirrors ``build_validation_error_items`` (blueprint → factory → pipe/concept → dry run) so the
    "first" message is the same item the structured surfaces list first.
    """
    item_messages = [error.message for error in blueprint_errors]
    item_messages += [error.message for error in factory_errors]
    item_messages += [error.message for error in pipe_validation_errors]
    item_messages += [failure.message for failure in dry_run_failures]
    if not item_messages:
        return raw_message
    first_message = item_messages[0]
    if len(item_messages) == 1:
        return first_message
    return f"{len(item_messages)} validation errors (first: {first_message})"


class ValidateBundleError(PipelexError):
    """Raised when a bundle is refused while it is loaded or validated: the invalid verdict, carrying one
    structured item per refusal in ``validation_errors``. Every refusal of the bundle itself becomes one —
    every parser error, categorized or not, the factory and pipe-validation errors, one ``dry_run`` item
    per pipe whose dry run failed, an unknown model (``unknown_model``) and any other refusal of the
    caller's input — each keeping the locators its raise site had, such as a TOML syntax error's ``line``
    and ``column`` and an unresolved concept's ``declared_concepts``, while a failure of the tool or its
    environment propagates as a no-verdict fault instead.

    This error aggregates validation errors from different stages:
    - Blueprint validation errors (from interpreter)
    - Pipe factory errors (from PipeFactoryError exceptions, e.g., missing concepts)
    - Pipe validation errors (from PipeValidationError exceptions)
    - Pipe/Concept instantiation errors (from Pydantic ValidationError during factory instantiation)
    - Dry run failures (one per failing pipe, each projected as its own ``dry_run`` item)

    Signatures are **never** an error (D-B): an unimplemented ``PipeSignature`` reached during
    validation is a runnability fact (reported library-wide via the report's ``pending_signatures``
    + ``is_runnable``), not a validation failure — so this error no longer carries a signature channel.

    All errors are categorized and stored in their respective lists.
    """

    error_domain = ErrorDomain.INPUT
    user_action = UserAction(
        kind=UserActionKind.CHANGE_INPUT,
        detail="Check the validation_errors array for specific issues",
    )
    # Bundle-validation messages describe faults in the caller's own bundle —
    # caller-facing copy, kept verbatim under STRICT disclosure.
    _authors_caller_facing_message = True

    def __init__(
        self,
        message: str,
        pipelex_bundle_blueprint_validation_errors: list[PipelexBundleBlueprintValidationErrorData] | None = None,
        pipe_factory_errors: list[PipeFactoryErrorData] | None = None,
        pipe_validation_errors: list[PipesAndConceptValidationErrorData] | None = None,
        pipe_concept_instantiation_errors: list[PipesAndConceptValidationErrorData] | None = None,
        dry_run_failures: list[DryRunFailureErrorData] | None = None,
    ):
        self.pipelex_bundle_blueprint_validation_errors = pipelex_bundle_blueprint_validation_errors or []
        self.pipe_factory_errors = pipe_factory_errors or []
        self.pipe_validation_errors = pipe_validation_errors or []

        # Pipe/Concept instantiation errors from Pydantic ValidationError during factory instantiation
        # TODO: Currently not caught, but structure is prepared for future implementation
        self.pipe_concept_instantiation_errors = pipe_concept_instantiation_errors or []

        # One located failure per pipe whose dry run failed (see ``BundleValidator``).
        self.dry_run_failures = dry_run_failures or []

        # Disease C: the top-line ``message`` is often a leaky ``str(pydantic ValidationError)``
        # (``Value errors: '<field>': Value error, …``). Replace it at the source with a clean
        # summary derived from the already-clean per-error item messages, so EVERY surface that
        # shows the top-line — the agent JSON ``message`` and the API report — benefits (one
        # engine), not just the CLI markdown. The raw ``message`` still rides ``to_error_report``'s
        # ``fallback_message`` residual, which only fires when there is no categorized data (the
        # summary is the raw message in that same case, so the two stay consistent).
        super().__init__(
            _summarize_bundle_validation_message(
                blueprint_errors=self.pipelex_bundle_blueprint_validation_errors,
                factory_errors=self.pipe_factory_errors,
                pipe_validation_errors=self.pipe_validation_error_data,
                dry_run_failures=self.dry_run_failures,
                raw_message=message,
            )
        )

    @property
    def pipe_validation_error_data(self) -> list[PipesAndConceptValidationErrorData]:
        """Backwards compatibility: combine pipe validation and instantiation errors.

        This property provides the old interface for accessing all pipe/concept validation errors.
        """
        # TODO: refactor so we don't need this anymore?
        return self.pipe_validation_errors + self.pipe_concept_instantiation_errors

    def validation_error_items(self) -> list[ValidationErrorItem]:
        """Project every channel this verdict carries into typed wire items, via the shared builder.

        The one projection behind the API report (:meth:`to_error_report`), the agent CLI's
        ``validation_errors`` array and ``pipelex fix``, so no surface can drop a channel another
        keeps. The pipe-validation arm uses :attr:`pipe_validation_error_data` (pipe validation
        **plus** pipe/concept instantiation errors) so the instantiation category is not silently
        dropped. Each dry-run failure becomes its own located ``dry_run`` item. Finally
        ``fallback_message=self.message`` is passed so a parse-level failure (TOML syntax, an empty
        blueprint, a bundle elaborator) — which carries only a message — still surfaces one
        ``blueprint_validation`` residual item. Together these make the structured-info invariant
        **total**: an invalid verdict never rides a bare ``detail`` with an empty
        ``validation_errors[]``.
        """
        return build_validation_error_items(
            blueprint_errors=self.pipelex_bundle_blueprint_validation_errors,
            factory_errors=self.pipe_factory_errors,
            pipe_validation_errors=self.pipe_validation_error_data,
            dry_run_failures=self.dry_run_failures,
            fallback_message=self.message,
        )

    @override
    def to_error_report(self) -> ErrorReport:
        """Attach the structured ``validation_errors`` list onto the base report.

        ``super().to_error_report()`` builds the report and enriches it from the
        ``__cause__`` chain; this override then attaches the per-error structured
        list from :meth:`validation_error_items` — the same items the agent CLI
        emits — so the API problem document carries machine-mappable diagnostics.
        The list is set to ``None`` when empty so it drops out of the
        ``exclude_none`` wire projection (and the round-trip stays identical to a
        plain report).
        """
        report = super().to_error_report()
        return report.model_copy(update={"validation_errors": self.validation_error_items() or None})


class PipeIOContractError(PipelexError):
    """Raised when projecting a validated pipe into its `pipe_io_contracts` IO contract fails.

    Wraps a JSON-Schema rendering failure (a pydantic schema-generation error on a
    structure class) into a structured Pipelex error, so every validate surface —
    direct and Temporal alike — reports it identically instead of leaking a raw
    third-party exception (which the Temporal error boundary would not convert and
    Temporal would pointlessly retry).
    """


class PipelineInputContentError(PipelexError):
    """A pipeline input's content reference (url) is unusable.

    Raised by the input normalizer when an Image/Document input carries a local
    path that cannot be read, or a pipelex-storage:// reference the storage
    provider refuses as a key (a path escaping local storage, for one). The
    caller supplied the value — INPUT domain, so API servers answer 422, never
    a sanitized 500 (a blank url used to surface as IsADirectoryError('.') → 500).

    Deliberately NOT caller-facing: the message names the resolved path and the
    ``OSError`` subclass that rejected it, or the storage provider's reason for
    refusing a key, which are server-side storage facts. Surviving STRICT disclosure would turn the report into an
    existence/permission oracle over the runner's filesystem for any
    authenticated caller — ``PermissionError`` on a path that exists reads
    differently from ``FileNotFoundError`` on one that does not. The
    caller-facing half of this family is ``PipelineInputUrlMissingError``,
    whose message carries nothing but the accepted schemes.
    """

    error_domain = ErrorDomain.INPUT
    user_action = UserAction(
        kind=UserActionKind.CHANGE_INPUT,
        detail=(
            "Provide a valid url on every Image/Document input (https://, data:, pipelex-storage://, or an existing local file when running locally)."
        ),
    )


class PipelineInputUrlInvalidError(PipelineInputContentError):
    """An Image/Document input carries an http(s) url that does not parse as one.

    Caller-facing on purpose: the message repeats the url the caller supplied and
    what is wrong with its shape, both of which are the caller's own facts. Whether
    the resource behind a well-formed url exists is not decided here — the operator
    that consumes the input fetches it and reports a real failure.
    """

    _authors_caller_facing_message = True
    user_action = UserAction(
        kind=UserActionKind.CHANGE_INPUT,
        detail="Provide a well-formed http(s) URL: a scheme, a host, and no whitespace.",
    )


class PipelineInputUrlMissingError(PipelineInputContentError):
    """An Image/Document input carries a blank url.

    The message states only the accepted schemes — no path, no server-side fact
    — so it is caller-facing copy and survives STRICT disclosure intact, where
    the placeholder would leave the caller with nothing to act on.
    (``caller_facing_message`` is the *report* field; the class-level flag that
    sets it is ``_authors_caller_facing_message``.)
    """

    _authors_caller_facing_message = True
