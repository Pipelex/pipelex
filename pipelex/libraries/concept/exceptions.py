from mthds.protocol.problem.registry import CoreCode

from pipelex.errors.error_code_declaration import ErrorCodeSet
from pipelex.libraries.exceptions import LibraryLoadingError


class ConceptLibraryError(LibraryLoadingError):
    """A concept-library failure (unresolved / duplicate / invalid concept reference).

    Extends ``LibraryLoadingError`` so it can carry the structured
    ``pipe_concept_validation_errors`` that the bundle-validation error cascade
    forwards onto ``validation_errors[]`` — an unresolved concept reference then
    surfaces as a categorized ``pipe_validation`` item (with the referencing
    pipe/field and the missing concept) rather than a bare message-only residual.
    Call sites that only pass a message keep working: the structured lists default
    to empty, so those raises behave exactly as before (one fallback residual).

    The default ``method.concept_unresolved`` is a reference to a concept nothing declares; a raise site chooses
    ``method.name_conflict`` for two declarations of one concept, and ``runtime.unexpected`` for an invariant of the
    crate.
    """

    error_code = ErrorCodeSet(
        default=CoreCode.METHOD_CONCEPT_UNRESOLVED,
        others=(CoreCode.METHOD_NAME_CONFLICT, CoreCode.RUNTIME_UNEXPECTED),
    )
