from typing import ClassVar

from mthds.protocol.problem.registry import CoreCode

from pipelex.base_exceptions import PipelexError
from pipelex.errors.error_code_declaration import ABSTRACT_ERROR, ErrorCodeDeclaration, ErrorCodeSet


class ConceptError(PipelexError):
    error_code: ClassVar[ErrorCodeDeclaration] = ABSTRACT_ERROR


class ConceptValueError(PipelexError, ValueError):
    """A concept that breaks a rule of the language, or that cannot be rendered as the caller asked.

    A ``ValueError`` too, since the concept's pydantic validators raise it and pydantic wraps nothing else. The
    rendering of a concept that has no Python representation chooses ``request.unsupported``.
    """

    error_code: ClassVar[ErrorCodeDeclaration] = ErrorCodeSet(default=CoreCode.METHOD_SCHEMA_VIOLATION, others=(CoreCode.REQUEST_UNSUPPORTED,))


class ConceptStructureClassNotFoundError(ConceptValueError):
    """A concept's declared `structure_class_name` does not resolve to a usable `StuffContent` class.

    Raised instead of answering a question the library cannot actually answer — "are these two
    compatible?", "what is this concept's class?". A `ConceptValueError` subclass so the guards that
    already convert that error at their own boundary keep working unchanged.
    """

    error_code = CoreCode.METHOD_CONCEPT_INVALID


class ConceptFactoryError(PipelexError):
    """A concept that cannot be built from its blueprint.

    The default ``method.concept_invalid`` is a structure that cannot be generated or refined; a malformed concept
    ref chooses ``method.schema_violation``, and a type invariant the blueprint guarantees ``runtime.unexpected``.
    """

    error_code = ErrorCodeSet(
        default=CoreCode.METHOD_CONCEPT_INVALID,
        others=(CoreCode.METHOD_SCHEMA_VIOLATION, CoreCode.RUNTIME_UNEXPECTED),
    )


class ConceptCodeError(ConceptError):
    error_code = CoreCode.METHOD_SCHEMA_VIOLATION


class ConceptStringError(ConceptError):
    error_code = CoreCode.METHOD_SCHEMA_VIOLATION


class ConceptLibraryConceptNotFoundError(PipelexError):
    """A concept the library does not hold, named by an input; ``runtime.unexpected`` for a native concept it lacks."""

    error_code = ErrorCodeSet(default=CoreCode.INPUT_WRONG_CONCEPT, others=(CoreCode.RUNTIME_UNEXPECTED,))


class ConceptRefAmbiguousError(ConceptError):
    """A bare `<domain>.<Code>` ref matches more than one concept the provider holds.

    A stuff on the wire names its concept as `<domain>.<Code>`, and that spelling is not unique
    across a crate: a host bundle and a dependency package may each declare it, the dependency's
    entry being keyed `<alias>-><domain>.<Code>`. Picking a winner would bind one package's
    definition to the other's data without a word, so the ambiguity is raised instead, naming
    every key that matched.
    """

    error_code = CoreCode.METHOD_REF_AMBIGUOUS
