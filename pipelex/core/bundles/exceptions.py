from pydantic import BaseModel

from pipelex.types import StrEnum


class PipelexBundleBlueprintFixableErrorType(StrEnum):
    """Types of fixable validation errors in Pipelex bundle blueprints.

    These error types represent validation issues that are actually fixed
    in the builder loop auto-fix system.
    """


class PipelexBundleBlueprintValidationErrorData(BaseModel):
    """Structured validation error data for bundle blueprint validation errors.

    This model captures information about validation errors that are actually fixed
    in the builder loop auto-fix system.
    """
