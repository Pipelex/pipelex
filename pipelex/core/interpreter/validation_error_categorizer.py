from typing import Any, cast

from pydantic_core import ErrorDetails

from pipelex import log
from pipelex.core.bundles.exceptions import (
    PipelexBundleBlueprintValidationErrorData,
)
from pipelex.core.interpreter.helpers import get_error_scope
from pipelex.types import StrEnum


class ErrorCatKey(StrEnum):
    LOC = "loc"
    MSG = "msg"
    TYPE = "type"


PIPELEX_BUNDLE_BLUEPRINT_DOMAIN_FIELD = "domain"
PIPELEX_BUNDLE_BLUEPRINT_SOURCE_FIELD = "source"


def categorize_blueprint_validation_error(
    blueprint_dict: dict[str, Any],
    error: ErrorDetails,
) -> PipelexBundleBlueprintValidationErrorData | None:
    """Categorize a BLUEPRINT validation error and create structured error data or return None if the error cannot be categorized.

    Args:
        blueprint_dict: The blueprint dict being validated (for context extraction)
        error: Pydantic error from PipelexBundleBlueprint.model_validate()

    Returns:
        PipelexBundleBlueprintValidationErrorData with all relevant fields populated, or None if error cannot be categorized
    """
    domain = cast("str | None", blueprint_dict.get(PIPELEX_BUNDLE_BLUEPRINT_DOMAIN_FIELD)) if blueprint_dict else None
    source = cast("str | None", blueprint_dict.get(PIPELEX_BUNDLE_BLUEPRINT_SOURCE_FIELD)) if blueprint_dict else None

    loc = error.get(ErrorCatKey.LOC.value, ())
    error_scope = get_error_scope(loc)
    log.warning(f"Pipelex bundle blueprint validation error that is not categorized: {error_scope} - {source} - {domain}")

    return None
