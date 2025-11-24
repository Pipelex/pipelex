from pipelex.base_exceptions import PipelexError


class ConceptError(PipelexError):
    pass


class ConceptValueError(ValueError):
    pass


class ConceptFactoryError(PipelexError):
    pass


class ConceptCodeError(ConceptError):
    pass


class ConceptStringError(ConceptError):
    pass


class ConceptRefineError(ConceptError):
    pass


class ConceptLibraryConceptNotFoundError(PipelexError):
    pass
