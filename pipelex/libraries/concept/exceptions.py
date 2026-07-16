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
    """
