from abc import ABC, abstractmethod

from pipelex.builder.validation_error_data import ConceptDefinitionErrorData


class PipelexValidationExceptionAbstract(Exception, ABC):
    @abstractmethod
    def get_concept_definition_errors(self) -> list[ConceptDefinitionErrorData]:
        pass
