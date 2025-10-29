from typing_extensions import Protocol

from pipelex.core.concepts.exceptions import ConceptDefinitionErrorData


class ValidationErrorDetailsProtocol(Protocol):
    def get_concept_definition_errors(self) -> list[ConceptDefinitionErrorData]: ...
