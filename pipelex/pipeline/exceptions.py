from typing_extensions import override

from pipelex.base_exceptions import ErrorDomain, ErrorReport, PipelexError, PipelexUnexpectedError
from pipelex.cogt.inference.error_classification import UserAction, UserActionKind
from pipelex.core.bundles.exceptions import PipelexBundleBlueprintValidationErrorData
from pipelex.core.exceptions import PipeFactoryErrorData, PipesAndConceptValidationErrorData
from pipelex.pipe_run.pipe_run_mode import PipeRunMode
from pipelex.pipeline.validation_errors import build_validation_error_items


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


class JobMetadataError(PipelexUnexpectedError):
    pass


class PipelineManagerNotFoundError(PipelexError):
    pass


class PipelineManagerAlreadyExistsError(PipelexError):
    pass


class ValidateBundleError(PipelexError):
    """Raised when bundle validation fails.

    This error aggregates validation errors from different stages:
    - Blueprint validation errors (from interpreter)
    - Pipe factory errors (from PipeFactoryError exceptions, e.g., missing concepts)
    - Pipe validation errors (from PipeValidationError exceptions)
    - Pipe/Concept instantiation errors (from Pydantic ValidationError during factory instantiation)
    - Dry run errors (the residual message, projected as one ``dry_run`` item by the shared builder)

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
        dry_run_error_message: str | None = None,
    ):
        self.pipelex_bundle_blueprint_validation_errors = pipelex_bundle_blueprint_validation_errors or []
        self.pipe_factory_errors = pipe_factory_errors or []
        self.pipe_validation_errors = pipe_validation_errors or []

        # Pipe/Concept instantiation errors from Pydantic ValidationError during factory instantiation
        # TODO: Currently not caught, but structure is prepared for future implementation
        self.pipe_concept_instantiation_errors = pipe_concept_instantiation_errors or []

        self.dry_run_error_message = dry_run_error_message

        super().__init__(message)

    @property
    def pipe_validation_error_data(self) -> list[PipesAndConceptValidationErrorData]:
        """Backwards compatibility: combine pipe validation and instantiation errors.

        This property provides the old interface for accessing all pipe/concept validation errors.
        """
        # TODO: refactor so we don't need this anymore?
        return self.pipe_validation_errors + self.pipe_concept_instantiation_errors

    @override
    def to_error_report(self) -> ErrorReport:
        """Attach the structured ``validation_errors`` list onto the base report.

        ``super().to_error_report()`` builds the report and enriches it from the
        ``__cause__`` chain; this override then attaches the per-error structured
        list — the same items the agent CLI emits, via the shared
        ``build_validation_error_items`` builder — so the API 422 problem
        document carries machine-mappable diagnostics. The list is set to
        ``None`` when empty so it drops out of the ``exclude_none`` wire
        projection (and the round-trip stays identical to a plain report).

        The pipe-validation arm uses :attr:`pipe_validation_error_data` (pipe
        validation **plus** pipe/concept instantiation errors) so the
        instantiation category is not silently dropped from the wire. The
        ``dry_run_error_message`` channel is a single message, not per-error data
        with identity fields, so the shared builder projects it as one
        ``dry_run``-category item **only** when no categorized error has data —
        the structured-info invariant, so an invalid verdict never rides a bare
        ``detail`` with an empty ``validation_errors[]``.
        """
        report = super().to_error_report()
        validation_error_items = build_validation_error_items(
            blueprint_errors=self.pipelex_bundle_blueprint_validation_errors,
            factory_errors=self.pipe_factory_errors,
            pipe_validation_errors=self.pipe_validation_error_data,
            dry_run_error_message=self.dry_run_error_message,
        )
        return report.model_copy(update={"validation_errors": validation_error_items or None})


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

    Raised by the input normalizer when an Image/Document input carries a
    blank url, or a local path that cannot be read. The caller supplied the
    value — INPUT domain, so API servers answer 422, never a sanitized 500
    (a blank url used to surface as IsADirectoryError('.') → 500).
    """

    error_domain = ErrorDomain.INPUT
    user_action = UserAction(
        kind=UserActionKind.CHANGE_INPUT,
        detail=(
            "Provide a valid url on every Image/Document input (https://, data:, pipelex-storage://, or an existing local file when running locally)."
        ),
    )
    caller_facing_message = True
