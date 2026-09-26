from pipelex.base_exceptions import ErrorDomain, PipelexError
from pipelex.cogt.exceptions import ModelChoiceNotFoundError
from pipelex.cogt.model_backends.model_type import ModelType
from pipelex.system.pipe_run_mode import PipeRunMode
from pipelex.validation_error_types import PipeFactoryErrorType, PipeValidationErrorType


class PipeFactoryError(PipelexError):
    """Raised when a pipe cannot be created from a blueprint.

    This error includes structured data about the failure.

    Attributes:
        message: Human-readable error message
        error_type: The type of factory error
        pipe_code: The pipe code that failed to be created
        domain: The domain of the pipe
        missing_concept_code: The concept code that is missing (for MISSING_OUTPUT_CONCEPT errors)
        declared_concepts: List of concepts declared in the domain
    """

    def __init__(
        self,
        message: str,
        error_type: PipeFactoryErrorType = PipeFactoryErrorType.UNKNOWN_FACTORY_ERROR,
        pipe_code: str | None = None,
        domain_code: str | None = None,
        missing_concept_code: str | None = None,
        declared_concepts: list[str] | None = None,
    ):
        self.error_type = error_type
        self.pipe_code = pipe_code
        self.domain_code = domain_code
        self.missing_concept_code = missing_concept_code
        self.declared_concepts = declared_concepts or []
        super().__init__(message)


class PipeVariableMultiplicityError(ValueError):
    pass


class PipeRunError(PipelexError):
    """A pipe failed while running, with the run mode and the pipe it failed in.

    Base of the run-failure family, and it sits here rather than with the pipe-run machinery because
    the kernel layer subclasses it: `PipeRunInputsError` and `OptionalValueAbsentError` in
    `core.pipes.inputs.exceptions` derive from it, so filing the base with the machinery put a
    module of `pipe_run` — and its whole import chain — inside every kernel import closure.
    """

    def __init__(self, message: str, run_mode: PipeRunMode, pipe_code: str):
        self.run_mode = run_mode
        self.pipe_code = pipe_code
        super().__init__(message)


class PipeOperatorModelChoiceError(PipelexError):
    """Raised by a pipe operator (``PipeLLM``, ``PipeStructure``, ``PipeImgGen``, ``PipeExtract``, ``PipeSearch``)
    when it is built from its blueprint and a model field names a model the model deck does not define.
    Bundle validation reports it as an invalid verdict whose item has the error type ``unknown_model``,
    and a run, which loads its bundle before any pipe runs, refuses the bundle with that same verdict.

    The pipe operator raises it from the ``ModelChoiceNotFoundError`` its deck check raised, located on
    the pipe (its code, type and domain) and on the field (``model``, or ``model_to_structure`` on a
    ``PipeLLM``), and the library load adds the file the pipe is declared in. Every pipe type that names
    a model raises this same error, so every one of them gives the same verdict item.

    The message names the pipe and the field, then keeps the deck check's sentence and its suggestions,
    so it is caller-facing copy: it names only the caller's own model reference and the deck's public
    handles, and it must reach a hosted caller under STRICT disclosure.
    """

    error_domain = ErrorDomain.INPUT
    _authors_caller_facing_message = True

    def __init__(
        self,
        message: str,
        *,
        pipe_type: str,
        pipe_code: str,
        domain_code: str,
        field_name: str,
        model_type: ModelType,
        model_choice: str,
        suggestions: list[str] | None = None,
        source: str | None = None,
    ):
        self.pipe_type = pipe_type
        self.pipe_code = pipe_code
        self.domain_code = domain_code
        self.field_name = field_name
        self.model_type = model_type
        # The reference exactly as the author wrote it (``gpt-5.1``, ``@best-sonet``, ``$writting-factual``).
        self.model_choice = model_choice
        # The deck's close matches of the same kind, each spelled as a reference the field accepts.
        self.suggestions = suggestions or []
        # The file declaring the pipe. The operator does not know it — pipes carry no source — so the
        # library load fills it from the crate's source map before the error leaves the load loop.
        self.source = source
        super().__init__(message)

    @classmethod
    def make_from_model_choice_not_found(
        cls,
        *,
        model_choice_error: ModelChoiceNotFoundError,
        pipe_type: str,
        pipe_code: str,
        domain_code: str,
        field_name: str,
    ) -> "PipeOperatorModelChoiceError":
        """Locate the deck check's refusal on the pipe and the field that named the model."""
        message = f"Pipe '{pipe_code}' ({pipe_type}), field '{field_name}': {model_choice_error.message}"
        return cls(
            message,
            pipe_type=pipe_type,
            pipe_code=pipe_code,
            domain_code=domain_code,
            field_name=field_name,
            model_type=model_choice_error.model_type,
            model_choice=model_choice_error.model_choice,
            suggestions=list(model_choice_error.suggestions),
        )


class PipeLoadRefusalError(PipelexError):
    """Raised by the library load when building one pipe of a bundle raises a refusal of the caller's input
    that carries no locator of its own. It names the pipe and its file, and bundle validation reports it
    as an invalid verdict.

    The load raises it ``from`` the refusal, so the original stays the ``__cause__``. Bundle validation
    turns it into one ``pipe_validation`` item carrying the pipe code, the domain and the source, with no
    ``error_type``, since the refusal has no closed code. Only an ``input``-domained refusal is wrapped: a
    fault of the configuration or of the runtime keeps its own identity and stays a no-verdict fault.

    Its message is built only from caller-facing material, the caller's own pipe code and either the
    refusal's message, when that message is caller-facing, or the refusal's title, so it is kept under
    STRICT disclosure.
    """

    error_domain = ErrorDomain.INPUT
    _authors_caller_facing_message = True

    def __init__(self, message: str, *, pipe_code: str, domain_code: str, source: str | None):
        self.pipe_code = pipe_code
        self.domain_code = domain_code
        self.source = source
        super().__init__(message)

    @classmethod
    def make_from_refusal(cls, *, refusal: PipelexError, pipe_code: str, domain_code: str, source: str | None) -> "PipeLoadRefusalError":
        """Locate a refusal on the pipe being built, keeping its message only when it is caller-facing."""
        message = f"Pipe '{pipe_code}' could not be loaded: {caller_facing_refusal_text(refusal=refusal)}"
        return cls(message, pipe_code=pipe_code, domain_code=domain_code, source=source)


def caller_facing_refusal_text(*, refusal: PipelexError) -> str:
    """The refusal's message when it was authored as caller-facing copy, otherwise its title.

    A validation verdict is caller-facing as a whole — ``ValidateBundleError`` keeps its message under
    STRICT disclosure — so text taken from a refusal onto a verdict item must be caller-facing too: a
    refusal whose message is internal is named by its title, which is always public.
    """
    if refusal.to_error_report().caller_facing_message:
        return refusal.message
    return type(refusal).title()


class PipeValidationError(ValueError):
    def __init__(
        self,
        message: str,
        error_type: PipeValidationErrorType | None = None,
        domain_code: str | None = None,
        pipe_code: str | None = None,
        variable_names: list[str] | None = None,
        required_concept_codes: list[str] | None = None,
        provided_concept_code: str | None = None,
        expected_output_ref: str | None = None,
        expected_inputs: dict[str, str] | None = None,
        declared_inputs: dict[str, str] | None = None,
        file_path: str | None = None,
        explanation: str | None = None,
    ):
        self.error_type = error_type
        self.domain_code = domain_code
        self.pipe_code = pipe_code
        self.variable_names = variable_names
        self.required_concept_codes = required_concept_codes
        self.provided_concept_code = provided_concept_code
        # The output ref the pipe should declare (full bundle representation: concept +
        # multiplicity + presence marker), set only where the validator knows the correct
        # value at detection time — the semantic fact the fix planner translates into a
        # suggested fix.
        self.expected_output_ref = expected_output_ref
        # The full inputs mapping the pipe should declare (variable name → bundle-representation
        # ref), set only at the controller input-drift raise sites where ``needed_inputs()`` is
        # in hand — the semantic fact the fix planner translates into a sync-controller-inputs fix.
        # ``declared_inputs`` is the pipe's current declaration rendered the same way, so the
        # planner (pure, no file access) can emit a minimal diff instead of a table rewrite.
        self.expected_inputs = expected_inputs
        self.declared_inputs = declared_inputs
        self.file_path = file_path
        self.explanation = explanation
        super().__init__(message)

    def desc(self) -> str:
        msg = f"{self.error_type} • domain_code='{self.domain_code}'"
        if self.pipe_code:
            msg += f" • pipe='{self.pipe_code}'"
        if self.variable_names:
            msg += f" • variable='{self.variable_names}'"
        if self.required_concept_codes:
            msg += f" • required_concept_codes='{self.required_concept_codes}'"
        if self.provided_concept_code:
            msg += f" • provided_concept_code='{self.provided_concept_code}'"
        if self.expected_output_ref:
            msg += f" • expected_output_ref='{self.expected_output_ref}'"
        if self.expected_inputs:
            msg += f" • expected_inputs='{self.expected_inputs}'"
        if self.declared_inputs:
            msg += f" • declared_inputs='{self.declared_inputs}'"
        if self.file_path:
            msg += f" • file='{self.file_path}'"
        if self.explanation:
            msg += f" • explanation='{self.explanation}'"
        return msg
