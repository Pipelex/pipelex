from pydantic import BaseModel

from pipelex.core.pipes.exceptions import PipeValidationErrorType
from pipelex.types import StrEnum


class PipelexBundleBlueprintFixableErrorType(StrEnum):
    """Types of fixable validation errors in Pipelex bundle blueprints.

    These error types represent validation issues that are actually fixed
    in the builder loop auto-fix system.
    """


class PipelexBundleBlueprintValidationErrorData(BaseModel):
    """Structured validation error data for bundle blueprint validation errors.

    This model captures information about validation errors that occur during
    blueprint validation (before pipe instantiation).
    """

    error_type: PipeValidationErrorType | None = None
    domain_code: str | None = None
    source: str | None = None
    pipe_code: str | None = None
    message: str
    variable_names: list[str] | None = None
