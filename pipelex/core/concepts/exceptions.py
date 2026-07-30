from pipelex.base_exceptions import PipelexError


class ConceptError(PipelexError):
    _declared_title = "Concept error"


class ConceptValueError(ValueError):
    pass


class ConceptStructureClassNotFoundError(ConceptValueError):
    """A concept's declared `structure_class_name` does not resolve to a usable `StuffContent` class.

    Raised instead of answering a question the library cannot actually answer — "are these two
    compatible?", "what is this concept's class?". A `ConceptValueError` subclass so the guards that
    already convert that error at their own boundary keep working unchanged.
    """


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
