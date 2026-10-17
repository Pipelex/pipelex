import re
from collections.abc import Collection
from typing import Any, ClassVar, NamedTuple, Self, TypeVar, cast

from mthds.protocol.problem.models import ProblemItem, ProblemLocation
from mthds.protocol.problem.registry import CoreCode
from typing_extensions import override

from pipelex.base_exceptions import PipelexError, ValidationErrorItem
from pipelex.cogt.inference.error_classification import UserAction, UserActionKind
from pipelex.core.exceptions import (
    DryRunFailureErrorData,
    PipeFactoryErrorData,
    PipelexBundleBlueprintValidationErrorData,
    PipesAndConceptValidationErrorData,
)
from pipelex.errors.error_code_declaration import ABSTRACT_ERROR, ErrorCodeDeclaration, ErrorCodeSet, InheritsCause
from pipelex.errors.error_codes import ErrorCode, code_is_method_domain
from pipelex.errors.problem import PipelexProblem, ProblemView
from pipelex.errors.registry.pipelex_codes import PipelexErrorCode
from pipelex.pipe_run.exceptions import find_failure_location
from pipelex.pipe_run.located_failure import failure_location_of, locate_failure_message, located_problem, located_root_fault
from pipelex.pipeline.validation_errors import build_validation_error_items, problem_item_of, validation_item_code
from pipelex.system.pipe_run_mode import PipeRunMode


class PipeExecutionError(PipelexError):
    """A run the runner cannot set up: no pipe to start at, or inputs that do not fit the run's models."""

    error_code = ErrorCodeSet(default=CoreCode.RUNTIME_UNEXPECTED, others=(CoreCode.REQUEST_PIPE_UNSPECIFIED, CoreCode.INPUT_INVALID))


class PipelineExecutionError(PipelexError):
    """Wraps any failure that occurred while running a pipeline, reported as its root fault.

    The runner raises it around every failure that happens once the run's job exists, so a host
    catches one class whatever went wrong. Its ``pipe_code`` and ``pipe_stack`` name the pipe where
    the failure happened and its path from the entry pipe, taken from the innermost location on the
    cause chain (the ``PipeRouterError`` of the pipe that failed). When the failure was never located
    (it happened outside any routed pipe run, or it crossed a transport boundary as a report that
    already names its pipe), ``pipe_code`` is the entry pipe and ``pipe_stack`` is empty.

    Its problem is not its own. It takes its cause's code, and ``to_problem()`` is the root fault's, the first
    ``PipelexError`` on the cause chain that carries a code of its own, or the problem such an error recovered across
    a transport boundary, with a ``location`` naming the failing pipe and its path. See
    ``pipelex.pipe_run.located_failure``.
    """

    error_code = InheritsCause(fallback=CoreCode.RUNTIME_UNEXPECTED)

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
    def to_problem(
        self,
        *,
        view: ProblemView,
        request_id: str | None = None,
        pipeline_run_id: str | None = None,
        failure_location: ProblemLocation | None = None,
    ) -> PipelexProblem:
        location = failure_location or failure_location_of(pipe_code=self.pipe_code, pipe_stack=self.pipe_stack)
        root_fault = located_root_fault(wrapper=self)
        if root_fault is None:
            return super().to_problem(view=view, request_id=request_id, pipeline_run_id=pipeline_run_id, failure_location=location)
        return located_problem(
            wrapper=self, root_fault=root_fault, view=view, request_id=request_id, pipeline_run_id=pipeline_run_id, failure_location=location
        )


class PipeStackOverflowError(PipelexError):
    """A run nested pipes deeper than the configured limit, usually a method that recurses."""

    error_code = CoreCode.PIPE_STACK_OVERFLOW

    def __init__(self, message: str, limit: int, pipe_stack: list[str]):
        self.limit = limit
        self.pipe_stack = list(pipe_stack)  # snapshot: the live stack unwinds after this error is raised
        super().__init__(message)

    @override
    def problem_params(self) -> dict[str, Any]:
        return {"limit": self.limit}


class PipelineManagerNotFoundError(PipelexError):
    """The pipeline manager holds no run under an id it was asked for: an internal lookup of ours."""

    error_code = CoreCode.RUNTIME_UNEXPECTED


class PipelineManagerAlreadyExistsError(PipelexError):
    """A run id the caller supplied is still in flight; the next step is to pick another id."""

    error_code = PipelexErrorCode.RUN_ALREADY_EXISTS


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
        """The error data without a withheld name as its ``source``, its ``field_path``, in its ``message`` or its ``params``.

        A pipe-validation error located from the pipe-source map carries its file as its ``field_path`` too
        (``categorize_pipe_validation_with_libraries_error``), so a withheld file leaves that field empty. A dry-run
        failure's parameters render its item's sentence, so a text among them, such as the template file a host's step
        names, reads the placeholder too.
        """
        withheld: list[_SourcedErrorData] = []
        for error in errors:
            update: dict[str, Any] = {
                "source": None if error.source in self.names else error.source,
                "message": self.withheld_text(text=error.message),
            }
            if isinstance(error, PipesAndConceptValidationErrorData) and error.field_path in self.names:
                update["field_path"] = ""
            if isinstance(error, DryRunFailureErrorData) and error.params:
                update["params"] = {name: self._withheld_value(value=value) for name, value in error.params.items()}
            withheld.append(error.model_copy(update=update))
        return withheld

    def _withheld_value(self, *, value: Any) -> Any:
        """A parameter's value reading the placeholder where a text of it named a withheld file."""
        if isinstance(value, str):
            return self.withheld_text(text=value)
        if isinstance(value, list):
            return [self._withheld_value(value=item) for item in cast("list[Any]", value)]
        return value


def withhold_names_in_text(*, text: str, names: Collection[str], placeholder: str) -> str:
    """``text`` reading ``placeholder`` where it named one of ``names`` standing on its own, never inside a longer name.

    The rule a verdict's messages are withheld by (:meth:`ValidateBundleError.withholding_files`), for a channel that
    is not a verdict's error data, such as an advisory warning.
    """
    return _FileWithholding.make_from_names(names=names, placeholder=placeholder).withheld_text(text=text)


# The code of a verdict itself, which no item of it takes: its sentence says nothing of any one fault.
_VERDICT_UMBRELLA_CODES: frozenset[ErrorCode] = frozenset({CoreCode.METHOD_INVALID})


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

    Its code is ``method.invalid``, each item keeping its own code on the problem's ``errors``; a request that names
    nothing to validate, such as an empty set of bundle contents, is ``request.invalid``, chosen at its raise site.
    The validation translation builds one only when at least one item is the method's
    (``pipelex.pipeline.validate_bundle_translation``): a refusal whose every item is a fault of another actor answers
    that fault, never an invalid verdict.
    """

    error_code = ErrorCodeSet(default=CoreCode.METHOD_INVALID, others=(CoreCode.REQUEST_INVALID,))
    user_action = UserAction(
        kind=UserActionKind.CHANGE_INPUT,
        # The next step points at the items' own: each item says what is wrong and where, and carries a
        # suggested fix when one can be derived, so the top level says to follow them rather than to go read them.
        detail="Edit the bundle as each validation error says: apply its suggested fix where it has one, after confirming an unsafe one",
    )

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
        # summary derived from the already-clean per-error item messages, so every surface that
        # shows the top-line benefits (one engine), not just the CLI markdown. The raw ``message``
        # still rides the ``fallback_message`` residual, which only fires when there is no categorized
        # data (the summary is the raw message in that same case, so the two stay consistent).
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
        out of a verdict the caller reads.

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

        The one projection behind the problem's items (:meth:`problem_items`), the ``/validate`` verdict, the agent
        CLI's ``validation_errors`` array and ``pipelex fix``, so no surface can drop a channel another
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
    def problem_items(self) -> list[ProblemItem] | None:
        """One problem item per validation item, each with its own code: a dry run's the failure's, any other its type's.

        An item no stage classified takes the code of the refusal this verdict was built from when that refusal is
        the method's, and ``method.schema_violation`` otherwise, or when that code is ``method.invalid``: the verdict's
        own umbrella, whose sentence says nothing of the item.
        """
        residual_code: ErrorCode = CoreCode.METHOD_SCHEMA_VIOLATION
        # The parameters the refusal's code renders from, as a caller reads them, which an item taking its code keeps.
        residual_params: dict[str, Any] | None = None
        cause = self.__cause__
        if isinstance(cause, PipelexError):
            cause_code = cause.resolve_error_code()
            if code_is_method_domain(code=cause_code) and cause_code not in _VERDICT_UMBRELLA_CODES:
                residual_code = cause_code
                cause_params = cause.to_problem(view=ProblemView.CALLER).params
                residual_params = cause_params.as_wire() if cause_params is not None else None
        dry_run_failures = iter(self.dry_run_failures)
        items: list[ProblemItem] = []
        for item in self.validation_error_items():
            item_code: ErrorCode
            item_params: dict[str, Any] | None = None
            if item.category.is_dry_run:
                dry_run_failure = next(dry_run_failures, None)
                item_code = dry_run_failure.code if dry_run_failure is not None else CoreCode.RUNTIME_UNEXPECTED
                item_params = dry_run_failure.params if dry_run_failure is not None else None
            elif item.error_type is None:
                item_code = residual_code
                item_params = residual_params
            else:
                item_code = validation_item_code(item=item, residual_code=residual_code)
            items.append(problem_item_of(item=item, code=item_code, params=item_params))
        return items or None


class HostLibraryLoadRefusalError(PipelexError):
    """A method of this host's own library directories refused to load: the deployment's fault, never the caller's input.

    A server loads its library directories beside a request's bundles (`library_dirs_are_callers` False), and they are
    the deployment's, so a pipe there that its factory refuses, that names a model the deck does not define, or that
    refuses in any other way the caller's own content would be refused, is the deployment's configuration failing to
    validate: `pipelex.config.invalid`, the code the registry gives the libraries among the runtime's own
    configuration, and the one `HostLibraryTreeError` and `HostLibraryRequirementsError` carry for the same
    directories. Its message names the method's refusal, which only the operator reads, and the caller reads the
    code's sentence, which quotes none of the host library's text. It is deliberately no `LibraryError`, which a
    validation would report as the caller's invalid bundle.
    """

    error_code = PipelexErrorCode.CONFIG_INVALID


class PipeIOContractError(PipelexError):
    """Raised when projecting a validated pipe into its `pipe_io_contracts` IO contract fails.

    Wraps a JSON-Schema rendering failure (a pydantic schema-generation error on a
    structure class) into a structured Pipelex error, so every validate surface —
    direct and Temporal alike — reports it identically instead of leaking a raw
    third-party exception (which the Temporal error boundary would not convert and
    Temporal would pointlessly retry).
    """

    error_code = CoreCode.METHOD_CONCEPT_INVALID


class PipelineInputContentError(PipelexError):
    """A pipeline input's content reference (url) is unusable.

    Raised by the input normalizer when an Image/Document input carries a local
    path that cannot be read, or a pipelex-storage:// reference the storage
    provider refuses as a key (a path escaping local storage, for one). The
    caller supplied the value — INPUT domain, so API servers answer 422, never
    a sanitized 500 (a blank url used to surface as IsADirectoryError('.') → 500).

    The message names the resolved path and the ``OSError`` subclass that
    rejected it, or the storage provider's reason for refusing a key, which are
    server-side storage facts: it rides only the operator's diagnostics, since a
    caller reading it could probe the runner's filesystem — ``PermissionError``
    on a path that exists reads differently from ``FileNotFoundError`` on one
    that does not. The caller reads the code's sentence.

    It takes its cause's code, so a storage key refused as a traversal reports the storage error's own code,
    and a key refused for another reason the fallback, a malformed storage address. A raise site that knows
    better chooses: a reference to nothing stored (``input.reference_not_found``), a data URL or a local
    file that cannot be read (``input.file_unreadable``).
    """

    error_code: ClassVar[ErrorCodeDeclaration] = InheritsCause(
        fallback=PipelexErrorCode.STORAGE_URI_INVALID,
        others=(CoreCode.INPUT_REFERENCE_NOT_FOUND, CoreCode.INPUT_FILE_UNREADABLE),
    )
    user_action = UserAction(
        kind=UserActionKind.CHANGE_INPUT,
        detail=(
            "Provide a valid url on every Image/Document input (https://, data:, pipelex-storage://, or an existing local file when running locally)."
        ),
    )


class PipelineInputUrlInvalidError(PipelineInputContentError):
    """An Image/Document input carries an http(s) url that does not parse as one.

    The message repeats the url the caller supplied and what is wrong with its
    shape, both of which are the caller's own facts. Whether
    the resource behind a well-formed url exists is not decided here — the operator
    that consumes the input fetches it and reports a real failure.
    """

    error_code = CoreCode.INPUT_INVALID
    user_action = UserAction(
        kind=UserActionKind.CHANGE_INPUT,
        detail="Provide a well-formed http(s) URL: a scheme, a host, and no whitespace.",
    )


class PipelineInputFormatError(PipelineInputContentError):
    """A file input's format is one its input slot, or the pipe that consumes it, cannot take.

    Raised at run setup, after the setup established each file input's format from its bytes, so the
    run is refused before any pipe spends anything on it. A message in this family carries only facts the
    caller supplied (the input's path in the inputs, the file's identified type) or the method declares (a
    pipe, a model, the formats that model reads), never a url, a storage key or a server-side reason.
    """

    error_code: ClassVar[ErrorCodeDeclaration] = ABSTRACT_ERROR
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

    error_code = CoreCode.INPUT_FILE_TYPE_UNSUPPORTED

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

    error_code = CoreCode.INPUT_FILE_TYPE_UNSUPPORTED

    user_action = UserAction(
        kind=UserActionKind.CHANGE_INPUT,
        detail="Give each file input in a format the model of the pipe that consumes it reads.",
    )


class PipelineInputUrlMissingError(PipelineInputContentError):
    """An Image/Document input carries a blank url."""

    error_code = CoreCode.INPUT_INVALID


class MethodEntryError(PipelexError):
    """Raised when a method run with no pipe named has no single pipe to start at.

    The rule is the MTHDS protocol's for a run that names no `pipe_code`: the manifest's `main_pipe` when the method's
    tree holds a `METHODS.toml` at its root, else the one `main_pipe` its bundles declare. A manifest declaring none or
    a pipe no bundle defines, and a method with no manifest whose bundles declare none or several, are refused, with
    the bundles named by their tree paths. The method is the caller's own, so the message is theirs to read.

    Its code defaults to ``request.pipe_unspecified``, a run naming no pipe of a method that declares no
    ``main_pipe``; the raise site chooses ``request.pipe_ambiguous`` when several pipes qualify,
    ``method.pipe_unresolved`` when the manifest names a pipe no bundle defines, ``method.package_invalid``
    when the manifest cannot be read, ``method.syntax`` when a bundle is not text, and ``method.invalid`` when
    the method holds no bundle at all.
    """

    error_code = ErrorCodeSet(
        default=CoreCode.REQUEST_PIPE_UNSPECIFIED,
        others=(
            CoreCode.REQUEST_PIPE_AMBIGUOUS,
            CoreCode.METHOD_PIPE_UNRESOLVED,
            CoreCode.METHOD_PACKAGE_INVALID,
            CoreCode.METHOD_SYNTAX,
            CoreCode.METHOD_INVALID,
        ),
    )
    user_action = UserAction(
        kind=UserActionKind.CHANGE_INPUT,
        detail="Name the pipe to run, or declare the method's one main_pipe: in its METHODS.toml, or in one of its bundles",
    )
