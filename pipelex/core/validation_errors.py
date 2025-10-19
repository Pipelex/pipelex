from typing_extensions import Protocol

from pipelex.builder.validation_error_data import ConceptDefinitionErrorData


class ValidationErrorDetailsProtocol(Protocol):
    def get_concept_definition_errors(self) -> list[ConceptDefinitionErrorData]: ...
