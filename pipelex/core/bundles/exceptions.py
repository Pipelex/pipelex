from typing_extensions import Self

from pipelex.base_exceptions import PipelexError
from pipelex.builder.validation_error_data import (
    ConceptFailure,
    DomainFailure,
    PipeFailure,
    PipeInputErrorData,
    StaticValidationErrorData,
)
from pipelex.core.pipes.exceptions import PipeDefinitionErrorData


class PipelexBundleBlueprintValueError(ValueError):
    pass
