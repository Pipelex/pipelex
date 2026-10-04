import re
from collections.abc import Collection
from typing import NamedTuple, Self, TypeVar

from typing_extensions import override

from pipelex.base_exceptions import ErrorDomain, ErrorReport, PipelexError, PipelexUnexpectedError, ValidationErrorItem
from pipelex.cogt.inference.error_classification import UserAction, UserActionKind
from pipelex.core.exceptions import (
    DryRunFailureErrorData,
    PipeFactoryErrorData,
    PipelexBundleBlueprintValidationErrorData,
    PipesAndConceptValidationErrorData,
)
from pipelex.pipe_run.exceptions import find_failure_location
from pipelex.pipe_run.located_failure import build_located_failure_report, locate_failure_message
from pipelex.pipeline.validation_errors import build_validation_error_items
from pipelex.system.pipe_run_mode import PipeRunMode


class PipeExecutionError(PipelexError):
    error_domain = ErrorDomain.RUNTIME


class PipelineExecutionError(PipelexError):
    """Wraps any failure that occurred while running a pipeline, reported as its root fault.

    The runner raises it around every failure that happens once the run's job exists, so a host
    catches one class whatever went wrong. Its ``pipe_code`` and ``pipe_stack`` name the pipe where
    the failure happened and its path from the entry pipe, taken from the innermost location on the
    cause chain (the ``PipeRouterError`` of the pipe that failed). When the failure was never located
    (it happened outside any routed pipe run, or it crossed a transport boundary as a report that
    already names its pipe), ``pipe_code`` is the entry pipe and ``pipe_stack`` is empty.

    Its report is not its own. ``to_error_report()`` takes the identity (``error_type``, ``title``,
    ``type_uri``), the message and the caller-facing flag of the root fault, the innermost
    ``PipelexError`` on the cause chain, or the report such an error recovered across a transport
    boundary; the message is prefixed with the failing pipe and its path. The classification is
    inherited from the cause chain (so a categorized ``CogtError`` keeps its ``WAIT_AND_RETRY`` /
    ``CHECK_BILLING`` action), with a ``RUNTIME`` floor and, when nothing on the chain advises an
    action, a fallback that names the failing pipe. See ``pipelex.pipe_run.located_failure``.
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

    @classmethod
    def make_for_run_failure(
        cls,
        *,
        failure: PipelexError,
        run_mode: PipeRunMode,
        entry_pipe_code: str,
        output_name: str | None,
    ) -> Self:
        """Wrap a run's `failure`, located where it happened; the caller raises the result `from failure`.

        The location is the innermost ``PipeRouterError`` on the failure's cause chain, never the
        live pipe stack, which has unwound by the time the runner sees the failure.
        """
        location = find_failure_location(error=failure)
        pipe_code: str
        pipe_stack: list[str]
        if location is None:
            pipe_code = entry_pipe_code
            pipe_stack = []
        else:
            pipe_code = location.pipe_code
            pipe_stack = location.pipe_stack
        return cls(
            message=locate_failure_message(failure=failure, pipe_code=pipe_code, pipe_stack=pipe_stack),
            run_mode=run_mode,
            pipe_code=pipe_code,
            output_name=output_name,
            pipe_stack=pipe_stack,
        )

    @override
    def to_error_report(self) -> ErrorReport:
        return build_located_failure_report(
            wrapper=self,
            own_report=super().to_error_report(),
            pipe_code=self.pipe_code,
            pipe_stack=self.pipe_stack,
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


# The error-data models that carry a ``source`` beside their ``message``.
_SourcedErrorData = TypeVar(
    "_SourcedErrorData", PipelexBundleBlueprintValidationErrorData, PipesAndConceptValidationErrorData, DryRunFailureErrorData
)

# A withheld name counts only standing on its own: not preceded by a character that could continue a path, a URI
# or an identifier, and not followed by one. So a host file spelled ``notices.mthds`` is not found inside the
# caller's ``api://notices.mthds`` or a dependency's ``tide_notices.mthds``.
_NAME_START_GUARD = r"(?<![\w.\-/\\:])"
_NAME_END_GUARD = r"(?![\w.\-/\\])"


class _FileWithholding(NamedTuple):
    """The names a verdict must not carry, and what a message reads in their place."""

    names: frozenset[str]
    pattern: re.Pattern[str]
    placeholder: str

    @classmethod
    def make_from_names(cls, *, names: Collection[str], placeholder: str) -> "_FileWithholding":
        if not names:
            # Nothing to withhold: a pattern that never matches, where an empty alternation would match everywhere.
            return cls(names=frozenset(), pattern=re.compile(r"(?!)"), placeholder=placeholder)
        # Longest first, so a name that extends another is replaced whole.
        alternatives = "|".join(re.escape(name) for name in sorted(set(names), key=len, reverse=True))
        pattern = re.compile(f"{_NAME_START_GUARD}(?:{alternatives}){_NAME_END_GUARD}")
        return cls(names=frozenset(names), pattern=pattern, placeholder=placeholder)

    def withheld_text(self, *, text: str) -> str:
        return self.pattern.sub(lambda _match: self.placeholder, text)

    def withheld_errors(self, *, errors: list[_SourcedErrorData]) -> list[_SourcedErrorData]:
        """The error data without a withheld name as its ``source``, its ``field_path`` or in its ``message``.

        A pipe-validation error located from the pipe-source map carries its file as its ``field_path`` too
        (``categorize_pipe_validation_with_libraries_error``), so a withheld file leaves that field empty.
        """
        withheld: list[_SourcedErrorData] = []
        for error in errors:
            update: dict[str, str | None] = {
                "source": None if error.source in self.names else error.source,
                "message": self.withheld_text(text=error.message),
            }
            if isinstance(error, PipesAndConceptValidationErrorData) and error.field_path in self.names:
                update["field_path"] = ""
            withheld.append(error.model_copy(update=update))
        return withheld


class ValidateBundleError(PipelexError):
    """Raised when a bundle is refused while it is loaded or validated: the invalid verdict, carrying one
    structured item per refusal in ``validation_errors``. Every refusal of the bundle itself becomes one —
    every parser error, categorized or not, the factory and pipe-validation errors, one ``dry_run`` item
    per pipe whose dry run failed, an unknown model (``unknown_model``) and any other refusal of the
    caller's input — each keeping the locators its raise site had, such as a TOML syntax error's ``line``
    and ``column`` and an unresolved concept's ``declared_concepts``, while a failure of the tool or its
    environment propagates as a no-verdict fault instead. A run raises it too, when the bundle it was given
    is refused while it loads, before any pipe runs: the same verdict, with the same items, that validating
    the bundle gives.

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
        # The next step points at the items' own: each item says what is wrong and where, and carries a
        # suggested fix when one can be derived, so the top level says to follow them rather than to go read them.
        detail="Edit the bundle as each validation error says: apply its suggested fix where it has one, after confirming an unsafe one",
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

    def withholding_files(self, *, withheld_files: Collection[str], placeholder: str) -> "ValidateBundleError":
        """This verdict with the given files taken out of every channel that could name them.

        An item whose ``source`` is one of ``withheld_files`` carries no ``source``, an item whose ``field_path``
        is one carries none either, and every message, the
        items' and the verdict's own, reads ``placeholder`` where it named one of them standing on its own,
        never inside a longer name. Everything else is kept, the items' locators included, so it is the same
        answer about the same bundle. Every channel the constructor takes is carried here: a channel added to
        it must be added here too, which ``test_validate_bundle_error_withholding`` pins. A validator of
        submitted content uses it to keep the files of the host's own library directories, paths on the host,
        out of a verdict that STRICT disclosure hands the caller verbatim.

        Args:
            withheld_files: Every spelling of every file the verdict must not name.
            placeholder: What a message reads where it named one of them.

        Returns:
            A new verdict; this one is left as it is.
        """
        withholding = _FileWithholding.make_from_names(names=withheld_files, placeholder=placeholder)
        return ValidateBundleError(
            message=withholding.withheld_text(text=self.message),
            pipelex_bundle_blueprint_validation_errors=withholding.withheld_errors(errors=self.pipelex_bundle_blueprint_validation_errors),
            pipe_factory_errors=[
                error.model_copy(update={"message": withholding.withheld_text(text=error.message)}) for error in self.pipe_factory_errors
            ],
            pipe_validation_errors=withholding.withheld_errors(errors=self.pipe_validation_errors),
            pipe_concept_instantiation_errors=withholding.withheld_errors(errors=self.pipe_concept_instantiation_errors),
            dry_run_failures=withholding.withheld_errors(errors=self.dry_run_failures),
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


class PipelineInputFormatError(PipelineInputContentError):
    """A file input's format is one its input slot, or the pipe that consumes it, cannot take.

    Raised at run setup, after the setup established each file input's format from its bytes, so the
    run is refused before any pipe spends anything on it. Caller-facing on purpose, and the flag spans
    every child and every raise site: a message in this family carries only facts the caller supplied
    (the input's path in the inputs, the file's identified type) or the method declares (a pipe, a
    model, the formats that model reads), never a url, a storage key or a server-side reason.
    """

    _authors_caller_facing_message = True
    user_action = UserAction(
        kind=UserActionKind.CHANGE_INPUT,
        detail="Give the input a file in a format the method can read.",
    )


class PipelineInputNotAnImageError(PipelineInputFormatError):
    """An Image input holds a file whose bytes identify it as something other than an image.

    Refused whatever will consume it: an Image holding a PDF is wrong for every consumer, so the check
    needs no model. It fires only on a positive identification, so an image the sniffer cannot
    identify, an SVG for one, is left to its consumer.
    """

    user_action = UserAction(
        kind=UserActionKind.CHANGE_INPUT,
        detail="Give an image file, such as PNG, JPEG or WebP, to every Image input.",
    )


class PipelineInputFormatUnsupportedError(PipelineInputFormatError):
    """A file input is certain to reach a pipe whose model cannot read its format.

    Raised at run setup by the pre-run consumer check, which walks the entry pipe to find the
    operators each input reaches. It refuses only a consumer that is certain to run, reached through
    no condition and no liftable step, and resolved to a model that does not read the file's known
    format. One error lists every violation, each naming the input, the format, the pipe, the model
    and the formats that model reads.
    """

    user_action = UserAction(
        kind=UserActionKind.CHANGE_INPUT,
        detail="Give each file input in a format the model of the pipe that consumes it reads.",
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
