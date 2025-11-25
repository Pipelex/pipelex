from pipelex.types import StrEnum


class ValidationErrorScope(StrEnum):
    PIPE = "pipe"
    CONCEPT = "concept"
    DOMAIN = "domain"
    MAIN_PIPE = "main_pipe"
    BUNDLE = "bundle"

    @classmethod
    def is_pipe_scope(cls, scope: str) -> bool:
        try:
            scope_enum = cls(scope)
        except ValueError:
            return False
        match scope_enum:
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


def get_error_scope(loc: tuple[int | str, ...]) -> ValidationErrorScope:
    """Get the scope of a validation error from its location tuple.

    Args:
        loc: Location tuple from Pydantic validation error

    Returns:
        ValidationErrorScope - defaults to BUNDLE if scope cannot be determined
    """
    if not loc:
        return ValidationErrorScope.BUNDLE

    scope = str(loc[0])

    try:
        scope_enum = ValidationErrorScope(scope)
    except ValueError:
        return ValidationErrorScope.BUNDLE

    match scope_enum:
        case ValidationErrorScope.PIPE:
            return ValidationErrorScope.PIPE
        case ValidationErrorScope.CONCEPT:
            return ValidationErrorScope.CONCEPT
        case ValidationErrorScope.DOMAIN:
            return ValidationErrorScope.DOMAIN
        case ValidationErrorScope.MAIN_PIPE:
            return ValidationErrorScope.MAIN_PIPE
        case ValidationErrorScope.BUNDLE:
            return ValidationErrorScope.BUNDLE
