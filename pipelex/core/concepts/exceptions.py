from pipelex.exceptions import PipelexException


class ConceptBlueprintValueError(ValueError):
    pass


class ConceptStructureBlueprintValueError(ValueError):
    pass


class ConceptFactoryError(PipelexException):
    pass


class StructureClassError(ConceptFactoryError):
    pass


class ConceptCodeError(PipelexException):
    pass


class ConceptStringError(PipelexException):
    pass


class ConceptRefineError(PipelexException):
    pass
