from typing import Any

from pydantic import BaseModel, ValidationError

from pipelex.base_exceptions import PipelexError
from pipelex.core.bundles.exceptions import PipeValidationErrorType
from pipelex.core.bundles.pipelex_bundle_blueprint import PipelexBundleBlueprint
from pipelex.core.exceptions import PipelexBundleBlueprintValidationErrorData, PipelexInterpreterError, PipeValidationError
from pipelex.core.interpreter import PipelexInterpreter
from pipelex.core.pipes.exceptions import PipeValidationErrorData
from pipelex.core.pipes.pipe_abstract import PipeAbstract
from pipelex.hub import get_library_manager, set_current_library
from pipelex.pipe_run.dry_run import DryRunError, DryRunOutput, dry_run_pipes


def categorize_pipe_validation_error_data(error_dict: dict[str, Any], pipe_code: str | None = None) -> PipeValidationErrorData:
    """Convert a Pydantic ValidationError into structured PipeValidationErrorData.

    Note: This function does NOT categorize errors into specific types because the errors
    that are auto-fixed in the builder loop (INPUT_REQUIREMENT_MISMATCH, MISSING_INPUT_VARIABLE,
    EXTRANEOUS_INPUT_VARIABLE, INADEQUATE_OUTPUT_CONCEPT) come from PipeValidationError exceptions,
    not from generic Pydantic ValidationErrors. This function is only used for unexpected
    validation errors that don't have a specific category.

    Args:
        error_dict: The error dictionary from Pydantic ValidationError.errors()
        pipe_code: Optional pipe code to associate with the error

    Returns:
        PipeValidationErrorData with UNKNOWN_VALIDATION_ERROR type
    """
    error_msg: str = str(error_dict.get("msg", ""))
    error_loc: tuple[Any, ...] = error_dict.get("loc", ())

    # Convert location tuple to field path string
    field_path = ".".join(str(loc) for loc in error_loc) if error_loc else None

    return PipeValidationErrorData(
        error_type=PipeValidationErrorType.UNKNOWN_VALIDATION_ERROR,
        domain=None,
        pipe_code=pipe_code,
        variable_names=[str(loc) for loc in error_loc] if error_loc else None,
        required_concept_codes=None,
        provided_concept_code=None,
        file_path=field_path,
        explanation=error_msg,
    )


class ValidateBundleError(PipelexError):
    """Raised when bundle validation fails.

    This error aggregates validation errors from different stages:
    - Interpreter errors (blueprint validation)
    - Library loading errors (factory and validation errors)
    - Dry run errors

    All errors are categorized and stored in validation_errors.
    """

    def __init__(
        self,
        message: str,
        pipelex_bundle_blueprint_validation_errors: list[PipelexBundleBlueprintValidationErrorData] | None = None,
        pipe_validation_error_data: list[PipeValidationErrorData] | None = None,
        dry_run_error_message: str | None = None,
    ):
        self.pipelex_bundle_blueprint_validation_errors = pipelex_bundle_blueprint_validation_errors or []
        self.pipe_validation_error_data = pipe_validation_error_data or []
        self.dry_run_error_message = dry_run_error_message
        super().__init__(message)


class ValidateBundleResult(BaseModel):
    blueprints: list[PipelexBundleBlueprint]
    pipes: list[PipeAbstract]
    dry_run_result: dict[str, DryRunOutput]


async def validate_bundle(
    plx_content: str | None = None, blueprints: list[PipelexBundleBlueprint] | None = None, plx_file_path: str | None = None
) -> ValidateBundleResult:
    provided_params = sum([blueprints is not None, plx_content is not None, plx_file_path is not None])
    if provided_params == 0:
        msg = "At least one of blueprints, plx_content, or plx_file_path must be provided to validate_bundle"
        raise ValidateBundleError(message=msg)
    if provided_params > 1:
        msg = "Only one of blueprints, plx_content, or plx_file_path can be provided to validate_bundle, not multiple"
        raise ValidateBundleError(message=msg)

    library_manager = get_library_manager()
    library_id, _ = library_manager.open_library()
    set_current_library(library_id=library_id)

    loaded_pipes: list[PipeAbstract] | None = None
    loaded_blueprints: list[PipelexBundleBlueprint] | None = None
    try:
        if blueprints is not None:
            loaded_blueprints = blueprints
            loaded_pipes = library_manager.load_from_blueprints(library_id=library_id, blueprints=blueprints)

        elif plx_content is not None:
            blueprint = PipelexInterpreter.make_pipelex_bundle_blueprint(plx_content=plx_content)
            loaded_blueprints = [blueprint]
            loaded_pipes = library_manager.load_from_blueprints(library_id=library_id, blueprints=[blueprint])

        else:  # plx_file_path is not None
            blueprint = PipelexInterpreter.make_pipelex_bundle_blueprint(bundle_path=plx_file_path)
            loaded_blueprints = [blueprint]
            loaded_pipes = library_manager.load_from_blueprints(library_id=library_id, blueprints=[blueprint])

        dry_run_results = await dry_run_pipes(pipes=loaded_pipes, raise_on_failure=True)
    except PipelexInterpreterError as interpreter_error:
        # Forward categorized validation errors from interpreter
        raise ValidateBundleError(
            message=interpreter_error.message,
            pipelex_bundle_blueprint_validation_errors=interpreter_error.validation_errors,
        ) from interpreter_error
    except PipeValidationError as pipe_error:
        # Convert PipeValidationError to PipeValidationErrorData
        pipe_error_data = PipeValidationErrorData(
            error_type=pipe_error.error_type,
            domain=pipe_error.domain,
            pipe_code=pipe_error.pipe_code,
            variable_names=pipe_error.variable_names,
            required_concept_codes=pipe_error.required_concept_codes,
            provided_concept_code=pipe_error.provided_concept_code,
            file_path=pipe_error.file_path,
            explanation=pipe_error.explanation,
        )
        raise ValidateBundleError(
            message=f"Pipe validation failed: {pipe_error}",
            pipe_validation_error_data=[pipe_error_data],
        ) from pipe_error
    except ValidationError as validation_error:
        # Convert Pydantic ValidationError to categorized PipeValidationErrorData
        pipe_error_data_list: list[PipeValidationErrorData] = []
        for error in validation_error.errors():
            # Categorize each validation error based on its content and location
            # Cast to dict[str, Any] since ErrorDetails is a TypedDict compatible with dict
            categorized_error = categorize_pipe_validation_error_data(error_dict=dict(error), pipe_code=None)
            pipe_error_data_list.append(categorized_error)
        raise ValidateBundleError(
            message=f"Validation failed: {validation_error}",
            pipe_validation_error_data=pipe_error_data_list,
        ) from validation_error
    except DryRunError as dry_run_error:
        # Forward dry run error message
        raise ValidateBundleError(
            message=dry_run_error.message,
            dry_run_error_message=dry_run_error.message,
        ) from dry_run_error

    return ValidateBundleResult(blueprints=loaded_blueprints, pipes=loaded_pipes, dry_run_result=dry_run_results)
