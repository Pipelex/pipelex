from pipelex.builder.validation_error_data import ConceptDefinitionErrorData, SyntaxErrorData
from pipelex.exceptions import PipelexException


class ConceptError(PipelexException):
    pass


class ConceptBlueprintValueError(ValueError):
    pass


class ConceptStructureBlueprintValueError(ValueError):
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
