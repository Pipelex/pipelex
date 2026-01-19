from pathlib import Path

from pydantic import BaseModel, ValidationError

from pipelex.base_exceptions import PipelexError
from pipelex.core.bundles.exceptions import PipelexBundleBlueprintValidationErrorData
from pipelex.core.bundles.pipelex_bundle_blueprint import PipelexBundleBlueprint
from pipelex.core.exceptions import PipeFactoryErrorData, PipesAndConceptValidationErrorData
from pipelex.core.interpreter.exceptions import PipelexInterpreterError
from pipelex.core.interpreter.interpreter import PipelexInterpreter
from pipelex.core.pipes.exceptions import PipeFactoryError, PipeValidationError
from pipelex.core.pipes.handle_pipe_errors import (
    categorize_pipe_factory_error,
    categorize_pipe_validation_error,
    categorize_pipe_validation_with_libraries_error,
)
from pipelex.core.pipes.pipe_abstract import PipeAbstract
from pipelex.core.validation import report_validation_error
from pipelex.hub import get_library_manager, set_current_library
from pipelex.libraries.library_utils import get_pipelex_plx_files_from_dirs
from pipelex.pipe_run.dry_run import DryRunError, DryRunOutput, dry_run_pipes


class ValidateBundleError(PipelexError):
    """Raised when bundle validation fails.

    This error aggregates validation errors from different stages:
    - Blueprint validation errors (from interpreter)
    - Pipe factory errors (from PipeFactoryError exceptions, e.g., missing concepts)
    - Pipe validation errors (from PipeValidationError exceptions)
    - Pipe/Concept instantiation errors (from Pydantic ValidationError during factory instantiation)
    - Dry run errors

    All errors are categorized and stored in their respective lists.
    """

    def __init__(
        self,
        message: str,
        pipelex_bundle_blueprint_validation_errors: list[PipelexBundleBlueprintValidationErrorData] | None = None,
        pipe_factory_errors: list[PipeFactoryErrorData] | None = None,
        pipe_validation_errors: list[PipesAndConceptValidationErrorData] | None = None,
        pipe_concept_instantiation_errors: list[PipesAndConceptValidationErrorData] | None = None,
        dry_run_error_message: str | None = None,
    ):
        # Blueprint validation errors (e.g., PIPE_SEQUENCE_OUTPUT_MISMATCH)
        self.pipelex_bundle_blueprint_validation_errors = pipelex_bundle_blueprint_validation_errors or []

        # Pipe factory errors (e.g., MISSING_OUTPUT_CONCEPT)
        self.pipe_factory_errors = pipe_factory_errors or []

        # Pipe validation errors from PipeValidationError exceptions
        # (e.g., MISSING_INPUT_VARIABLE, EXTRANEOUS_INPUT_VARIABLE, INPUT_REQUIREMENT_MISMATCH, INADEQUATE_OUTPUT_CONCEPT)
        self.pipe_validation_errors = pipe_validation_errors or []

        # Pipe/Concept instantiation errors from Pydantic ValidationError
        # These occur during factory instantiation of Pipe or Concept classes
        # TODO: Currently not caught, but structure is prepared for future implementation
        self.pipe_concept_instantiation_errors = pipe_concept_instantiation_errors or []

        # Dry run errors
        self.dry_run_error_message = dry_run_error_message

        super().__init__(message)

    @property
    def pipe_validation_error_data(self) -> list[PipesAndConceptValidationErrorData]:
        """Backwards compatibility: combine pipe validation and instantiation errors.

        This property provides the old interface for accessing all pipe/concept validation errors.
        """
        # TODO: refactor so we don't need this anymore?
        return self.pipe_validation_errors + self.pipe_concept_instantiation_errors


class ValidateBundleResult(BaseModel):
    blueprints: list[PipelexBundleBlueprint]
    pipes: list[PipeAbstract]
    dry_run_result: dict[str, DryRunOutput]


async def validate_bundle(
    plx_file_path: str | None = None,
    plx_content: str | None = None,
    blueprints: list[PipelexBundleBlueprint] | None = None,
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
        raise ValidateBundleError(
            message=interpreter_error.message,
            pipelex_bundle_blueprint_validation_errors=interpreter_error.validation_errors,
        ) from interpreter_error
    except PipeFactoryError as factory_error:
        factory_error_data = categorize_pipe_factory_error(factory_error=factory_error)
        raise ValidateBundleError(
            message=f"Pipe factory error: {factory_error}",
            pipe_factory_errors=[factory_error_data],
        ) from factory_error
    except PipeValidationError as pipe_error:
        pipe_error_data = categorize_pipe_validation_with_libraries_error(pipe_error=pipe_error)
        raise ValidateBundleError(
            message=f"Pipe validation failed: {pipe_error}",
            pipe_validation_errors=[pipe_error_data],
        ) from pipe_error
    except ValidationError as validation_error:
        pipe_validation_errors = categorize_pipe_validation_error(validation_error=validation_error)
        validation_error_msg = report_validation_error(category="plx", validation_error=validation_error)
        msg = f"Could not load blueprints because of: {validation_error_msg}"
        raise ValidateBundleError(
            message=msg,
            pipe_validation_errors=pipe_validation_errors,
        ) from validation_error
    except DryRunError as dry_run_error:
        raise ValidateBundleError(
            message=dry_run_error.message,
            dry_run_error_message=dry_run_error.message,
        ) from dry_run_error

    return ValidateBundleResult(blueprints=loaded_blueprints, pipes=loaded_pipes, dry_run_result=dry_run_results)


async def validate_bundles_from_directory(directory: Path) -> ValidateBundleResult:
    plx_files = get_pipelex_plx_files_from_dirs(dirs={directory})
    all_blueprints: list[PipelexBundleBlueprint] = []

    library_manager = get_library_manager()
    library_id, _ = library_manager.open_library()
    set_current_library(library_id=library_id)
    try:
        for plx_file in plx_files:
            blueprint = PipelexInterpreter.make_pipelex_bundle_blueprint(bundle_path=str(plx_file))
            all_blueprints.append(blueprint)

        loaded_pipes = library_manager.load_libraries(library_id=library_id, library_dirs=[Path(directory)])
        dry_run_results = await dry_run_pipes(pipes=loaded_pipes, raise_on_failure=True)
    except PipelexInterpreterError as interpreter_error:
        raise ValidateBundleError(
            message=interpreter_error.message,
            pipelex_bundle_blueprint_validation_errors=interpreter_error.validation_errors,
        ) from interpreter_error
    except PipeFactoryError as factory_error:
        factory_error_data = categorize_pipe_factory_error(factory_error=factory_error)
        raise ValidateBundleError(
            message=f"Pipe factory error: {factory_error}",
            pipe_factory_errors=[factory_error_data],
        ) from factory_error
    except PipeValidationError as pipe_error:
        pipe_error_data = categorize_pipe_validation_with_libraries_error(pipe_error=pipe_error)
        raise ValidateBundleError(
            message=f"Pipe validation failed: {pipe_error}",
            pipe_validation_errors=[pipe_error_data],
        ) from pipe_error
    except ValidationError as validation_error:
        pipe_validation_errors = categorize_pipe_validation_error(validation_error=validation_error)
        validation_error_msg = report_validation_error(category="plx", validation_error=validation_error)
        msg = f"Could not load blueprints because of: {validation_error_msg}"
        raise ValidateBundleError(
            message=msg,
            pipe_validation_errors=pipe_validation_errors,
        ) from validation_error
    except DryRunError as dry_run_error:
        raise ValidateBundleError(
            message=dry_run_error.message,
            dry_run_error_message=dry_run_error.message,
        ) from dry_run_error

    return ValidateBundleResult(blueprints=all_blueprints, pipes=loaded_pipes, dry_run_result=dry_run_results)
