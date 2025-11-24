from pipelex.base_exceptions import PipelexError
from pipelex.core.exceptions import SyntaxErrorData


class ConceptError(PipelexError):
    pass




class ConceptValueError(ValueError):
    pass


class ConceptStructureValidationError(PipelexError):
    pass


class ConceptFactoryError(PipelexError):
    pass


class StructureClassError(ConceptFactoryError):
    pass


class ConceptCodeError(ConceptError):
    pass


class ConceptStringError(ConceptError):
    pass


class ConceptRefineError(ConceptError):
    pass


class ConceptLibraryConceptNotFoundError(PipelexError):
    pass


class ConceptStructureGeneratorError(PipelexError):
    def __init__(self, message: str, structure_class_python_code: str | None = None, syntax_error_data: SyntaxErrorData | None = None):
        self.structure_class_python_code = structure_class_python_code
        self.syntax_error_data = syntax_error_data
        super().__init__(message)
