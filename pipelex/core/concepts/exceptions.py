from abc import ABC, abstractmethod

from pydantic import BaseModel, Field

from pipelex.base_exceptions import PipelexException
from pipelex.core.exceptions import SyntaxErrorData


class ConceptError(PipelexException):
    pass


class ConceptBlueprintValueError(ValueError):
    pass


class ConceptStructureBlueprintValueError(ValueError):
    pass


class ConceptStructureValidationError(PipelexException):
    pass


class ConceptFactoryError(PipelexException):
    pass


class StructureClassError(ConceptFactoryError):
    pass


class ConceptCodeError(ConceptError):
    pass


class ConceptStringError(ConceptError):
    pass


class ConceptRefineError(ConceptError):
    pass


class ConceptLibraryConceptNotFoundError(PipelexException):
    pass


class ConceptDefinitionErrorData(BaseModel):
    """Structured data for ConceptDefinitionError."""

    message: str = Field(description="The error message")
    domain_code: str = Field(description="The domain code")
    concept_code: str = Field(description="The concept code")
    description: str = Field(description="Description of the concept")
    structure_class_python_code: str | None = Field(None, description="Python code for the structure class if available")
    structure_class_syntax_error_data: SyntaxErrorData | None = Field(None, description="Syntax error data for the structure class if available")
    source: str | None = Field(None, description="Source of the error")


class ConceptDefinitionError(PipelexException):
    def __init__(
        self,
        message: str,
        domain_code: str,
        concept_code: str,
        description: str,
        structure_class_python_code: str | None = None,
        structure_class_syntax_error_data: SyntaxErrorData | None = None,
        source: str | None = None,
    ):
        self.domain_code = domain_code
        self.concept_code = concept_code
        self.description = description
        self.structure_class_python_code = structure_class_python_code
        self.structure_class_syntax_error_data = structure_class_syntax_error_data
        self.source = source
        super().__init__(message)

    def as_structured_content(self) -> ConceptDefinitionErrorData:
        return ConceptDefinitionErrorData(
            message=str(self),
            domain_code=self.domain_code,
            concept_code=self.concept_code,
            description=self.description,
            structure_class_python_code=self.structure_class_python_code,
            structure_class_syntax_error_data=self.structure_class_syntax_error_data,
            source=self.source,
        )


class ConceptStructureGeneratorError(PipelexException):
    def __init__(self, message: str, structure_class_python_code: str | None = None, syntax_error_data: SyntaxErrorData | None = None):
        self.structure_class_python_code = structure_class_python_code
        self.syntax_error_data = syntax_error_data
        super().__init__(message)


class PipelexValidationExceptionAbstract(PipelexException, ABC):
    @abstractmethod
    def get_concept_definition_errors(self) -> list[ConceptDefinitionErrorData]:
        pass
