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






