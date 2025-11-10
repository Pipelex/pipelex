from typing_extensions import Self, override

from pipelex.builder.validation_error_data import (
    ConceptFailure,
    DomainFailure,
    PipeFailure,
    PipeInputErrorData,
    StaticValidationErrorData,
)
from pipelex.core.concepts.exceptions import ConceptDefinitionErrorData, PipelexValidationExceptionAbstract
from pipelex.core.pipes.exceptions import PipeDefinitionErrorData


class PipelexBundleSpecValueError(ValueError):
    pass


class PipelexBundleError(PipelexValidationExceptionAbstract):
    """Main bundle error that aggregates multiple types of errors."""

    def __init__(
        self: Self,
        message: str,
        static_validation_error: StaticValidationErrorData | None = None,
        domain_failures: list[DomainFailure] | None = None,
        pipe_failures: list[PipeFailure] | None = None,
        concept_failures: list[ConceptFailure] | None = None,
        concept_definition_errors: list[ConceptDefinitionErrorData] | None = None,
        pipe_definition_errors: list[PipeDefinitionErrorData] | None = None,
        pipe_input_errors: list[PipeInputErrorData] | None = None,
    ) -> None:
        self.static_validation_error = static_validation_error
        self.domain_failures = domain_failures
        self.pipe_input_errors = pipe_input_errors
        self.pipe_failures = pipe_failures
        self.concept_failures = concept_failures
        self.concept_definition_errors = concept_definition_errors
        self.pipe_definition_errors = pipe_definition_errors
        super().__init__(message)

    @override
    def get_concept_definition_errors(self) -> list[ConceptDefinitionErrorData]:
        return self.concept_definition_errors or []
