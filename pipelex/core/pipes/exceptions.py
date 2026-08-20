from typing_extensions import override

from pipelex.base_exceptions import PipelexError
from pipelex.cogt.extract.extract_setting import ExtractModelChoice
from pipelex.cogt.img_gen.img_gen_setting import ImgGenModelChoice
from pipelex.cogt.llm.llm_setting import LLMModelChoice
from pipelex.cogt.model_backends.model_type import ModelType
from pipelex.cogt.models.model_reference import ModelReference
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
    def __init__(
        self,
        message: str,
        pipe_type: str,
        pipe_code: str,
        model_type: ModelType,
        model_choice: LLMModelChoice | ExtractModelChoice | ImgGenModelChoice,
    ):
        self.pipe_type = pipe_type
        self.pipe_code = pipe_code
        self.model_type = model_type
        self.model_choice = model_choice
        super().__init__(message)

    def desc(self) -> str:
        msg = f"{self.message}"
        msg += f" • pipe='{self.pipe_code}' ({self.pipe_type})"
        msg += f" • model_type='{self.model_type}'"

        # Extract the choice identifier from the model_choice union type
        if isinstance(self.model_choice, str):
            # It's a raw string (shouldn't happen but handle it)
            msg += f" • choice='{self.model_choice}'"
        elif isinstance(self.model_choice, ModelReference):
            # It's a ModelReference with kind and name
            msg += f" • choice='{self.model_choice.raw}' ({self.model_choice.kind})"
        else:
            # It's a Setting object with a model field and optional desc()
            msg += f" • choice={self.model_choice.desc()}"

        return msg

    @override
    def __str__(self) -> str:
        return self.desc()


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
