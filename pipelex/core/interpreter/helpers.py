from pipelex.base_exceptions import PipelexUnexpectedError
from pipelex.types import StrEnum


class ValidationErrorScope(StrEnum):
    """Scope of validation errors based on loc[0]."""

    PIPE = "pipe"
    CONCEPT = "concept"
    DOMAIN = "domain"
    MAIN_PIPE = "main_pipe"
    BUNDLE = "bundle"

    @classmethod
    def is_pipe_scope(cls, scope: str) -> bool:
        match cls(scope):
            case ValidationErrorScope.PIPE:
                return True
            case ValidationErrorScope.CONCEPT:
                return False
            case ValidationErrorScope.DOMAIN:
                return False
            case ValidationErrorScope.MAIN_PIPE:
                return False
            case ValidationErrorScope.BUNDLE:
                return False

    @classmethod
    def is_concept_scope(cls, scope: str) -> bool:
        match cls(scope):
            case ValidationErrorScope.PIPE:
                return False
            case ValidationErrorScope.CONCEPT:
                return True
            case ValidationErrorScope.DOMAIN:
                return False
            case ValidationErrorScope.MAIN_PIPE:
                return False
            case ValidationErrorScope.BUNDLE:
                return False

    @classmethod
    def is_domain_scope(cls, scope: str) -> bool:
        match cls(scope):
            case ValidationErrorScope.PIPE:
                return False
            case ValidationErrorScope.CONCEPT:
                return False
            case ValidationErrorScope.DOMAIN:
                return True
            case ValidationErrorScope.MAIN_PIPE:
                return False
            case ValidationErrorScope.BUNDLE:
                return False

    @classmethod
    def is_main_pipe_scope(cls, scope: str) -> bool:
        match cls(scope):
            case ValidationErrorScope.PIPE:
                return False
            case ValidationErrorScope.CONCEPT:
                return False
            case ValidationErrorScope.DOMAIN:
                return False
            case ValidationErrorScope.MAIN_PIPE:
                return True
            case ValidationErrorScope.BUNDLE:
                return False

    @classmethod
    def is_bundle_scope(cls, scope: str) -> bool:
        match cls(scope):
            case ValidationErrorScope.PIPE:
                return False
            case ValidationErrorScope.CONCEPT:
                return False
            case ValidationErrorScope.DOMAIN:
                return False
            case ValidationErrorScope.MAIN_PIPE:
                return False
            case ValidationErrorScope.BUNDLE:
                return True


def get_error_scope(loc: tuple[int | str, ...]) -> ValidationErrorScope:
    if not loc:
        return ValidationErrorScope.BUNDLE

    first = str(loc[0])

    if ValidationErrorScope.is_pipe_scope(scope=first):
        return ValidationErrorScope.PIPE
    elif ValidationErrorScope.is_concept_scope(scope=first):
        return ValidationErrorScope.CONCEPT
    elif ValidationErrorScope.is_domain_scope(scope=first):
        return ValidationErrorScope.DOMAIN
    elif ValidationErrorScope.is_main_pipe_scope(scope=first):
        return ValidationErrorScope.MAIN_PIPE
    elif ValidationErrorScope.is_bundle_scope(scope=first):
        return ValidationErrorScope.BUNDLE
    else:
        msg = f"Unexpected validation error scope: {first}"
        raise PipelexUnexpectedError(msg)
