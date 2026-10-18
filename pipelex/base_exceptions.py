from collections.abc import Iterator
from enum import StrEnum
from typing import Any, ClassVar, NamedTuple, Self

from mthds.protocol.problem.models import ProblemItem, ProblemLocation
from mthds.protocol.problem.registry import CoreCode, ProblemDomain
from opentelemetry import trace
from pydantic import BaseModel, ConfigDict, Field
from typing_extensions import override

from pipelex.cogt.inference.error_classification import UserAction
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
from pipelex.errors.problem import (
    DiagnosticCause,
    MigrationErrorBlock,
    PipelexProblem,
    ProblemDiagnostics,
    ProblemView,
    ProviderDiagnostics,
    accepted_params,
    cap_problem_text,
    make_problem,
    merge_locations,
    recovered_problem_in_view,
    runtime_version,
)
from pipelex.errors.registry.pipelex_codes import PipelexErrorCode
from pipelex.errors.security_target import SecurityTargetClass
from pipelex.suggested_fix import SuggestedFix
from pipelex.system.telemetry.current_span import current_span_context_for_logs, pipelex_span_context_for_logs
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


def iter_traceback_chain(exc: BaseException) -> Iterator[BaseException]:
    """Yield ``exc`` and each exception a traceback of it prints, outermost first, exactly once.

    The walk a traceback makes, where :func:`iter_cause_chain` follows ``__cause__`` alone: an explicit cause
    (``raise ... from``) is followed, else the exception being handled when it was raised, ``__context__``, unless the
    raise suppressed it (``from None``). It is for a reader that must account for everything a traceback would print
    of a failure, such as a log record naming the chain's classes in place of the traceback, or a classifier looking
    for a transport failure anywhere below the error it received. Cycle-guarded like :func:`iter_cause_chain`, since it
    runs on the error path.
    """
    node: BaseException | None = exc
    seen: set[int] = set()
    while node is not None and id(node) not in seen:
        seen.add(id(node))
        yield node
        if node.__cause__ is not None:
            node = node.__cause__
        elif node.__suppress_context__:
            node = None
        else:
            node = node.__context__


def iter_pipelex_cause_chain(exc: BaseException) -> Iterator["PipelexError"]:
    """Yield ``exc`` and each Pipelex error below it along its ``__cause__`` chain, stopping at the first that is not one.

    A foreign exception raised from an earlier failure is a new failure, raised by code of its own, so nothing below it
    belongs to the error above it: neither a code, a fact, a location, an item nor a piece of advice. Every walk that
    reads an error's chain for its problem reads it through this one, over the cycle-guarded :func:`iter_cause_chain`.
    """
    for node in iter_cause_chain(exc):
        if not isinstance(node, PipelexError):
            return
        yield node


class ErrorDomain(StrEnum):
    """The three-way reading of who acts that the CLIs' error output and the usage statistics still carry.

    - INPUT: the caller can fix it (bad .mthds, wrong args, malformed JSON).
    - CONFIG: an environment or configuration change is needed.
    - RUNTIME: a failure that occurred during execution.

    The problem document carries the code's own domain, from the MTHDS core's closed list; this reading is derived
    from it through :meth:`from_problem_domain` for the surfaces that have not moved to it.
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


def error_domain_is_input(error_domain: ErrorDomain | str | None) -> bool:
    """True when ``error_domain`` is the caller-fixable ``INPUT`` domain.

    The serialized-form counterpart to :attr:`ErrorDomain.is_input`: it accepts the raw ``str`` / ``None`` shape a
    CLI's JSON envelope carries, so a consumer can branch on "is this the caller's mistake?" without re-implementing
    the coercion. ``None`` or an unrecognized string is treated as non-input, the conservative default.
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
    """One structured bundle-validation error, as the validation verdicts carry it.

    The typed item of an invalid verdict's ``validation_errors``; the problem document of a refusal carries each as an
    ``errors`` item instead (``pipelex.pipeline.validation_errors.problem_item_of``). Its
    fields are the *union* across the three ``ValidateBundleError`` error-data
    models (``PipelexBundleBlueprintValidationErrorData``, ``PipeFactoryErrorData``,
    ``PipesAndConceptValidationErrorData``); a given item only populates the
    subset its :attr:`category` produces, and the unset fields drop out of the
    ``exclude_none`` wire projection.

    The error channel is built exclusively by
    ``pipelex.pipeline.validation_errors.build_validation_error_items``, which both the agent
    CLI (``extract_validation_errors``) and the API path
    (``ValidateBundleError.validation_error_items``) call — so the CLI's structured
    output and the API's invalid verdict can never drift. The same
    item type also carries the report's advisory ``warnings``, built by
    ``pipelex.pipeline.advisory_warnings``: a warning is the same shape of
    diagnostic, differing only in that it does not make the verdict invalid.

    ``source`` is the declaring file path (CLI) or the per-content source the API
    threads onto the in-memory load path — it hands a consumer the owning file
    for cross-file diagnostics. Lives here rather than next to the source error-data
    models because ``base_exceptions`` must not import the ``pipelex.core`` error
    modules (which import back into this module).
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
    # The identifier locator, carried by an ``invalid_pipe_code_syntax`` item: the name that breaks the naming rules, as
    # the method writes it, a declaration key or the ``main_pipe`` value, which ``field_path`` (``main_pipe``) tells
    # apart. Optional and additive, like ``declared_concepts``.
    identifier_name: str | None = None
    # The hint locator, carried by a hint lint item: the hint key the finding is about, elided as its message quotes it,
    # which its problem item names as the code's ``hint`` parameter. Optional and additive, like ``declared_concepts``.
    hint_key: str | None = None
    # The parameters of its problem item's code the stage that found it knows about this one item, by the registry's
    # names, beside those its locators give: the facts a raise site gave its refusal (the concept a step declares and
    # those it expects), and on an item no ``error_type`` classifies, which takes the code of the refusal it rides,
    # those of this one fault where the refusal's own describe only its first. Optional and additive, like
    # ``declared_concepts``.
    params: dict[str, Any] | None = None
    # Structured, deterministic fix for this error, when the fix planner derived one from the
    # enriched error data. Optional and additive: non-fixable items serialize unchanged under
    # ``exclude_none``.
    suggested_fix: SuggestedFix | None = None


_FALLBACK_ERROR_CODE: ErrorCode = CoreCode.RUNTIME_UNEXPECTED
"""The code of an error whose cause chain names none: the catch-all, ``runtime.unexpected``, step ``report``."""


class ProblemFacts(NamedTuple):
    """The facts an error knows that its problem's operator diagnostics and retry delay carry.

    An error contributes the facts it holds (:meth:`PipelexError.problem_facts`), and a problem takes, for each, the
    one nearest the error it is built from along the cause chain, so that a wrapper that knows a fact overrides its
    cause and a wrapper that does not inherits it.

    Attributes:
        model: The model a failed inference call addressed.
        provider: What the provider said about the call.
        migration: A pending configuration migration that explains the failure.
        retry_after: The delay the provider asked for before a retry, in seconds.
    """

    model: str | None = None
    provider: ProviderDiagnostics | None = None
    migration: MigrationErrorBlock | None = None
    retry_after: float | None = None


def _merged_provider(*, nearer: ProviderDiagnostics | None, farther: ProviderDiagnostics | None) -> ProviderDiagnostics | None:
    """What two errors of one chain say about the provider, member by member, the nearer error's winning."""
    if nearer is None or farther is None:
        return nearer or farther
    return ProviderDiagnostics.model_validate({**farther.model_dump(exclude_none=True), **nearer.model_dump(exclude_none=True)})


class PipelexError(Exception):
    """The root of every error Pipelex raises, each carrying a registry code, and each becoming a problem document.

    Every subclass declares ``error_code`` in its own class body, as :mod:`pipelex.errors.error_code_declaration`
    describes: the code it raises, the set its raise sites choose from, that it takes its cause's code, or that it
    is an abstract base. The code decides the problem's title, documentation page, domain, retry verdict, step and
    sentences, so a class declares none of them; ``tests/unit/pipelex/errors/test_error_code_gate.py`` fails the build
    on a subclass that declares no code, and ``docs/under-the-hood/error-model.md`` explains the model.

    :meth:`to_problem` builds the error's problem document in the view of its reader. The error's own message is the
    operator's diagnostics, never a caller's sentence: the caller reads the code's templates, rendered from the
    parameters the raise site gives (:meth:`with_params`) or the class derives (:meth:`problem_params`).
    """

    error_code: ClassVar[ErrorCodeDeclaration] = ABSTRACT_ERROR
    # Advice a local reader of the error can act on, which the human and agent CLIs print as a tip. It never reaches a
    # problem document, whose step is the code's.
    user_action: UserAction | None = None

    # The code the raise site chose with :meth:`with_error_code`, from the codes the class declares.
    _chosen_error_code: ErrorCode | None = None
    # The parameters the raise site gave with :meth:`with_params`.
    _given_params: dict[str, Any] | None = None
    # The items the raise site gave with :meth:`with_items`, one per fault of a refusal of several.
    _given_items: list[ProblemItem] | None = None
    # The class of destination a security refusal refused, stated by the raise site with
    # :meth:`with_security_target_class`; the security event carries it and nothing else about the target.
    _security_target_class: SecurityTargetClass | None = None

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

    def with_params(self, **params: Any) -> Self:
        """Give, where this error is raised, the parameters its code's sentences are rendered from.

        A raise site gives the facts its code declares, by the names the registry gives them, such as
        ``raise PipeRunError(...).with_error_code(CoreCode.PIPE_CONDITION_UNMATCHED).with_params(pipe=self.code)``. A
        parameter the code does not declare, or one of the wrong type, is dropped and logged when the problem is
        built, and a parameter given here overrides one the class derives.

        Args:
            **params: The parameters, by name.

        Returns:
            This error, so that the raise site reads ``raise SomeError(msg).with_params(name=value)``.
        """
        self._given_params = {**(self._given_params or {}), **params}
        return self

    def with_items(self, *, items: list[ProblemItem]) -> Self:
        """Give, where this error is raised, one item per fault when it refuses several at once.

        A raise site that finds several faults of one kind reports them all, each item rendered from its own
        parameters with :func:`pipelex.errors.problem.make_problem_item`, while the error's own code and parameters
        describe the first. A subclass that derives its items overrides :meth:`problem_items` instead.

        Args:
            items: The items, one per fault.

        Returns:
            This error, so that the raise site reads ``raise SomeError(msg).with_items(items=items)``.
        """
        self._given_items = list(items)
        return self

    def advised_action(self) -> UserAction | None:
        """The advice nearest this error along its cause chain, which a local CLI prints as a tip; never part of a problem."""
        for node in iter_pipelex_cause_chain(self):
            if node.user_action is not None:
                return node.user_action
        return None

    @property
    def given_params(self) -> dict[str, Any]:
        """The parameters the raise site gave with :meth:`with_params`."""
        return dict(self._given_params or {})

    def with_security_target_class(self, target_class: SecurityTargetClass | None) -> Self:
        """State, where a security refusal is decided, which class of destination it refused.

        The security event (:mod:`pipelex.errors.security_event`) names that class, a loopback or a private address,
        a cloud metadata endpoint, a scheme the runtime does not read, and never the destination itself. Only the
        raise site knows it: the SSRF guard has the address in hand, the read scope the reason. ``None`` leaves the
        class unknown, for a site that refused something it cannot classify, such as a name that resolved to nothing.

        Args:
            target_class: The class of destination refused, or ``None`` when the site cannot tell.

        Returns:
            This error, so that the raise site reads ``raise SomeError(msg).with_security_target_class(target_class)``.
        """
        self._security_target_class = target_class
        return self

    @property
    def security_target_class(self) -> SecurityTargetClass | None:
        """The class of destination this security refusal refused, ``None`` when nobody stated it."""
        return self._security_target_class

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
        for node in iter_pipelex_cause_chain(self):
            own_code = node.own_error_code
            if own_code is not None:
                return own_code
            implied_code = node.implied_error_code or implied_code
            declaration = type(node).error_code
            if isinstance(declaration, InheritsCause):
                fallback = declaration.fallback
        return implied_code or fallback or _FALLBACK_ERROR_CODE

    def resolve_domain(self) -> ProblemDomain:
        """Who must act on this error: the domain the registry gives the code it resolves to."""
        return error_code_spec(self.resolve_error_code()).domain

    def code_carrier(self) -> "PipelexError":
        """The error along the cause chain whose code this one reports, which gives the problem its facts about the fault.

        The first error that carries a code by itself, as :meth:`resolve_error_code` walks; else the deepest error that
        implies one; else this error, whose code is a fallback.
        """
        implied_node: PipelexError | None = None
        for node in iter_pipelex_cause_chain(self):
            if node.own_error_code is not None:
                return node
            if node.implied_error_code is not None:
                implied_node = node
        return implied_node or self

    def problem_params(self) -> dict[str, Any]:
        """The facts this error holds that its codes declare as parameters, by the registry's names.

        A subclass that holds such facts overrides it. A fact the resolved code does not declare is left out
        silently, since a class's codes declare different parameters, and a parameter its raise site gave
        (:meth:`with_params`) overrides a fact of the same name.
        """
        return {}

    def chain_items(self) -> list[ProblemItem] | None:
        """The items of the first error along the cause chain that refuses several faults at once."""
        for node in iter_pipelex_cause_chain(self):
            items = node.problem_items()
            if items:
                return items
        return None

    def chain_location(self, *, carrier: "PipelexError") -> ProblemLocation | None:
        """The location this error and the errors below it know, down to ``carrier``, the nearest the fault winning.

        A wrapper that takes its cause's code often knows where its cause was met, the pipe, the field or the file, which
        the cause does not: each error's own location is merged over the ones above it, member by member, so a member
        the error whose code the problem reports knows wins, and the wrappers fill the members it lacks.
        """
        location: ProblemLocation | None = None
        for node in iter_pipelex_cause_chain(self):
            node_location = node.problem_location()
            if node_location is not None:
                location = merge_locations(base=location, override=node_location)
            if node is carrier:
                break
        return location

    def problem_location(self) -> ProblemLocation | None:
        """Where this error happened, when it knows; a subclass that holds a place overrides it."""
        return None

    def problem_items(self) -> list[ProblemItem] | None:
        """One item per fault, for an error that refuses several at once: those its raise site gave with :meth:`with_items`.

        A subclass that holds several faults of its own overrides it.
        """
        return list(self._given_items) if self._given_items else None

    def recovered_problem(self) -> PipelexProblem | None:
        """The problem this error carries from across a transport boundary, in the operator's view; ``None`` for any other error.

        A host plugin's carrier of a problem a far worker packed overrides it, and is the only kind of error that does:
        :meth:`to_problem` then reports that problem rather than one built from the carrier's class
        (:func:`pipelex.errors.problem.recovered_problem_in_view`), and a located wrapper above the carrier reports it as
        it is (``pipelex.pipe_run.located_failure``). Overriding :meth:`to_problem` for any other reason makes no carrier.
        """
        return None

    def errors_above(self, *, carrier: "PipelexError") -> list["PipelexError"]:
        """The errors from this one down to ``carrier``, ``carrier`` left out, this one first; empty when the chain never reaches it."""
        errors: list[PipelexError] = []
        for node in iter_pipelex_cause_chain(self):
            if node is carrier:
                return errors
            errors.append(node)
        return []

    def problem_facts(self) -> ProblemFacts:
        """The facts this error itself holds for its problem's diagnostics; a subclass that holds some overrides it."""
        return ProblemFacts()

    def chain_facts(self) -> ProblemFacts:
        """For each fact, the one nearest this error along its cause chain, which ends at the first foreign exception.

        The provider's answer is merged member by member, the nearest error's winning: a wrapper a worker attributed
        to its backend names the provider, while the cause it wraps keeps what the provider answered.
        """
        model: str | None = None
        provider: ProviderDiagnostics | None = None
        migration: MigrationErrorBlock | None = None
        retry_after: float | None = None
        for node in iter_pipelex_cause_chain(self):
            facts = node.problem_facts()
            model = model or facts.model
            provider = _merged_provider(nearer=provider, farther=facts.provider)
            migration = migration or facts.migration
            retry_after = retry_after if retry_after is not None else facts.retry_after
        return ProblemFacts(model=model, provider=provider, migration=migration, retry_after=retry_after)

    def _diagnostics(self, *, facts: ProblemFacts) -> ProblemDiagnostics:
        """The operator's diagnostics of this error: its class, its message capped, its causes and its facts."""
        causes: list[DiagnosticCause] = []
        for node in iter_cause_chain(self):
            if node is self:
                continue
            own_code = node.own_error_code if isinstance(node, PipelexError) else None
            causes.append(DiagnosticCause(error_class=type(node).__name__, code=own_code))
        span_context = pipelex_span_context_for_logs() or current_span_context_for_logs()
        return ProblemDiagnostics(
            error_class=type(self).__name__,
            message=cap_problem_text(text=self.message),
            causes=causes or None,
            model=facts.model,
            provider=facts.provider,
            migration=facts.migration,
            runtime_version=runtime_version(),
            trace_id=trace.format_trace_id(span_context.trace_id) if span_context is not None else None,
            span_id=trace.format_span_id(span_context.span_id) if span_context is not None else None,
        )

    def to_problem(
        self,
        *,
        view: ProblemView,
        request_id: str | None = None,
        pipeline_run_id: str | None = None,
        failure_location: ProblemLocation | None = None,
    ) -> PipelexProblem:
        """This error as a problem document, in the view of its reader.

        The code is :meth:`resolve_error_code`'s, and everything the code decides is the registry's. The rest is
        :meth:`problem_reported_by`'s, this error being its own reporter. An error carrying a problem recovered across a
        transport boundary (:meth:`recovered_problem`) reports that problem instead, in the view asked for.

        Args:
            view: The view of the reader the problem is built for, picked by the identity the boundary authenticated.
            request_id: The request that carried the failure, when known.
            pipeline_run_id: The run the failure belongs to, when one exists.
            failure_location: Where a run's failing pipe is, when the failure was located at a pipe.

        Returns:
            The problem.
        """
        recovered = self.recovered_problem()
        if recovered is not None:
            return recovered_problem_in_view(
                problem=recovered, view=view, request_id=request_id, pipeline_run_id=pipeline_run_id, failure_location=failure_location
            )
        return self.problem_reported_by(
            reporter=self, view=view, request_id=request_id, pipeline_run_id=pipeline_run_id, failure_location=failure_location
        )

    def caller_params(self) -> dict[str, Any]:
        """The parameters this error's problem carries as a caller reads them, read without building the problem.

        They are the parameters :meth:`to_problem` gives in the caller's view, its items' aside: a refusal whose faults
        its items carry gives none of its own for a code that requires some, which building its problem would log as a
        fault, while a reader wanting only the parameters, such as a verdict whose items take this refusal's code, has
        nothing to report.
        """
        recovered = self.recovered_problem()
        if recovered is not None:
            recovered_params = self.to_problem(view=ProblemView.CALLER).params
            return recovered_params.as_wire() if recovered_params is not None else {}
        code = self.resolve_error_code()
        params, _ = self._reported_params_and_location(reporter=self, failure_location=None)
        operator_only_params = error_code_spec(code).operator_only_params
        return {name: value for name, value in accepted_params(code=code, params=params).items() if name not in operator_only_params}

    def _reported_params_and_location(
        self, *, reporter: "PipelexError", failure_location: ProblemLocation | None
    ) -> tuple[dict[str, Any], ProblemLocation | None]:
        """The parameters and the location of this error's problem as ``reporter`` reports it (see :meth:`problem_reported_by`)."""
        code = self.resolve_error_code()
        carrier = self.code_carrier()
        wrappers = reporter.errors_above(carrier=carrier)
        facts = reporter.chain_facts()
        spec = error_code_spec(code)
        params: dict[str, Any] = {}
        for wrapper in wrappers:
            # Given in order from the reporter down, so a wrapper nearer the carrier wins over one above it; checked
            # against the carrier's code when the problem is built, an undeclared one being dropped and logged.
            params.update(wrapper.given_params)
        params.update({name: value for name, value in carrier.problem_params().items() if name in spec.param_names})
        params.update(carrier.given_params)
        location = reporter.chain_location(carrier=carrier)
        if failure_location is not None:
            location = merge_locations(base=location, override=failure_location)
        if location is not None and location.pipe is not None and "pipe" in spec.param_names:
            params.setdefault("pipe", location.pipe)
        if facts.model is not None and "model" in spec.param_names:
            params.setdefault("model", facts.model)
        if facts.provider is not None and facts.provider.name is not None and "provider" in spec.param_names:
            params.setdefault("provider", facts.provider.name)
        return params, location

    def problem_reported_by(
        self,
        *,
        reporter: "PipelexError",
        view: ProblemView,
        request_id: str | None = None,
        pipeline_run_id: str | None = None,
        failure_location: ProblemLocation | None = None,
    ) -> PipelexProblem:
        """This error's problem as ``reporter`` reports it: this error itself, or a wrapper above it that located it.

        A run failure is reported as its root fault under the wrappers that located or carried it
        (``pipelex.pipe_run.located_failure``), and those wrappers may know what the root fault does not, so the problem
        is this error's, read along the reporter's chain:

        - the code is this error's (:meth:`resolve_error_code`), and the parameters are those of the error whose code it
          is (:meth:`code_carrier`): the facts it holds and the parameters its raise site gave, then, for a parameter it
          gives none of, the one the nearest error between the reporter and it gave with :meth:`with_params`, a
          parameter its code does not declare being dropped and logged;
        - the items are those of the first error at or below the error whose code it is that refuses several faults,
          then those each error between the reporter and it refuses, the nearest it first;
        - the location is assembled from the reporter down to the error whose code it is, each error's own location
          winning over those above it member by member, so a wrapper that knows the pipe, the field or the file a cause
          was met at locates a cause that does not; the location of the failing pipe a run found (``failure_location``)
          then takes precedence for the pipe and its path, and the pipe names the pipe parameter of a code that declares one;
        - the facts are the nearest the reporter along its chain, so a fact a wrapper above this error holds, such as
          the model and the backend a worker attributed it to, overrides its cause's;
        - the operator view's diagnostics name this error: its class, its message and its causes.

        Args:
            reporter: This error, or an error above it on whose cause chain it sits.
            view: The view of the reader the problem is built for, picked by the identity the boundary authenticated.
            request_id: The request that carried the failure, when known.
            pipeline_run_id: The run the failure belongs to, when one exists.
            failure_location: Where a run's failing pipe is, when the failure was located at a pipe.

        Returns:
            The problem.
        """
        code = self.resolve_error_code()
        carrier = self.code_carrier()
        # The wrappers between the reporter and the error whose code the problem reports, the reporter first.
        wrappers = reporter.errors_above(carrier=carrier)
        facts = reporter.chain_facts()
        params, location = self._reported_params_and_location(reporter=reporter, failure_location=failure_location)
        items = list(carrier.chain_items() or [])
        for wrapper in reversed(wrappers):
            items.extend(wrapper.problem_items() or [])
        return make_problem(
            code=code,
            view=view,
            params=params,
            location=location,
            errors=items or None,
            retry_after=facts.retry_after,
            pipeline_run_id=pipeline_run_id,
            request_id=request_id,
            diagnostics=self._diagnostics(facts=facts) if view.shows_diagnostics else None,
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
    def problem_facts(self) -> ProblemFacts:
        return ProblemFacts(migration=self.migration)


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
