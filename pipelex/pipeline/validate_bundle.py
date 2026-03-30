import asyncio
from pathlib import Path
from typing import Sequence

from pydantic import BaseModel, ValidationError

from pipelex import log
from pipelex.base_exceptions import PipelexError
from pipelex.core.bundles.exceptions import PipelexBundleBlueprintValidationErrorData
from pipelex.core.bundles.pipelex_bundle_blueprint import PipelexBundleBlueprint
from pipelex.core.concepts.concept import Concept
from pipelex.core.exceptions import PipeFactoryErrorData, PipesAndConceptValidationErrorData
from pipelex.core.interpreter.exceptions import MthdsDecodeError, PipelexInterpreterError
from pipelex.core.interpreter.interpreter import PipelexInterpreter
from pipelex.core.pipes.exceptions import PipeFactoryError, PipeValidationError
from pipelex.core.pipes.handle_pipe_errors import (
    categorize_pipe_factory_error,
    categorize_pipe_validation_error,
    categorize_pipe_validation_with_libraries_error,
)
from pipelex.core.pipes.pipe_abstract import PipeAbstract
from pipelex.core.validation import report_validation_error
from pipelex.hub import get_library_manager, resolve_library_dirs, set_current_library
from pipelex.libraries.library_utils import get_pipelex_mthds_files_from_dirs
from pipelex.pipe_run.dry_run import DryRunError, DryRunOutput, dry_run_pipes
from pipelex.pipe_run.exceptions import PipeRunError


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
    mthds_file_path: Path | None = None,
    mthds_contents: list[str] | None = None,
    blueprints: list[PipelexBundleBlueprint] | None = None,
    library_dirs: Sequence[Path] | None = None,
) -> ValidateBundleResult:
    provided_params = sum(
        [
            blueprints is not None,
            mthds_contents is not None,
            mthds_file_path is not None,
        ]
    )
    if provided_params == 0:
        msg = "At least one of blueprints, mthds_contents, or mthds_file_path must be provided to validate_bundle"
        raise ValidateBundleError(message=msg)
    if provided_params > 1:
        msg = "Only one of blueprints, mthds_contents, or mthds_file_path can be provided to validate_bundle, not multiple"
        raise ValidateBundleError(message=msg)

    library_manager = get_library_manager()
    library_id, library = library_manager.open_library()
    set_current_library(library_id=library_id)

    # Load libraries from resolved directories before loading the bundle
    effective_dirs, source_label = resolve_library_dirs(library_dirs)

    loaded_pipes: list[PipeAbstract] | None = None
    loaded_blueprints: list[PipelexBundleBlueprint] | None = None
    await asyncio.sleep(0)  # Yield to event loop (keeps function async-compatible)
    try:
        if effective_dirs:
            log.verbose(f"Loading libraries from {len(effective_dirs)} directory(ies) ({source_label}) for validation")
            library_manager.load_libraries(
                library_id=library_id,
                library_dirs=effective_dirs,
            )
        else:
            log.verbose(f"No library directories to load ({source_label})")
        if blueprints is not None:
            loaded_blueprints = blueprints
            loaded_pipes = library_manager.load_from_blueprints(library_id=library_id, blueprints=blueprints)
            # dry_run_results = await dry_run_pipes(pipes=loaded_pipes, raise_on_failure=True)
            return ValidateBundleResult(blueprints=loaded_blueprints, pipes=loaded_pipes, dry_run_result={})

        elif mthds_contents is not None:
            loaded_blueprints = [PipelexInterpreter.make_pipelex_bundle_blueprint(mthds_content=content) for content in mthds_contents]
            loaded_pipes = library_manager.load_from_blueprints(library_id=library_id, blueprints=loaded_blueprints)
            # dry_run_results = await dry_run_pipes(pipes=loaded_pipes, raise_on_failure=True)
            return ValidateBundleResult(blueprints=loaded_blueprints, pipes=loaded_pipes, dry_run_result={})

        else:
            assert mthds_file_path is not None
            blueprint = PipelexInterpreter.make_pipelex_bundle_blueprint(bundle_path=mthds_file_path)
            loaded_blueprints = [blueprint]

            if mthds_file_path.resolve() not in library.loaded_mthds_paths:
                # File not yet loaded - load it from the blueprint
                loaded_pipes = library_manager.load_from_blueprints(library_id=library_id, blueprints=[blueprint])
            else:
                # File already loaded - get existing pipes from library by their codes
                pipe_codes = list(blueprint.pipe.keys()) if blueprint.pipe else []
                loaded_pipes = [library.pipe_library.get_required_pipe(pipe_code=code) for code in pipe_codes]

            # dry_run_results = await dry_run_pipes(pipes=loaded_pipes, raise_on_failure=True)
            return ValidateBundleResult(blueprints=loaded_blueprints, pipes=loaded_pipes, dry_run_result={})

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
        validation_error_msg = report_validation_error(category="mthds", validation_error=validation_error)
        msg = f"Could not load blueprints because of: {validation_error_msg}"
        raise ValidateBundleError(
            message=msg,
            pipe_validation_errors=pipe_validation_errors,
        ) from validation_error
    except MthdsDecodeError as decode_error:
        msg = f"TOML syntax error at line {decode_error.lineno}, column {decode_error.colno}: {decode_error.message}"
        raise ValidateBundleError(message=msg) from decode_error
    except PipeRunError as pipe_run_error:
        raise ValidateBundleError(
            message=pipe_run_error.message,
            dry_run_error_message=pipe_run_error.message,
        ) from pipe_run_error
    except DryRunError as dry_run_error:
        raise ValidateBundleError(
            message=dry_run_error.message,
            dry_run_error_message=dry_run_error.message,
        ) from dry_run_error


async def validate_bundles_from_directory(directory: Path) -> ValidateBundleResult:
    mthds_files = get_pipelex_mthds_files_from_dirs(dirs={directory})
    all_blueprints: list[PipelexBundleBlueprint] = []

    library_manager = get_library_manager()
    library_id, _ = library_manager.open_library()
    set_current_library(library_id=library_id)
    try:
        for mthds_file in mthds_files:
            blueprint = PipelexInterpreter.make_pipelex_bundle_blueprint(bundle_path=mthds_file)
            all_blueprints.append(blueprint)

        loaded_pipes = library_manager.load_libraries(library_id=library_id, library_dirs=[Path(directory)])
        dry_run_results = await dry_run_pipes(pipes=loaded_pipes, raise_on_failure=True)
    except MthdsDecodeError as decode_error:
        msg = f"TOML syntax error at line {decode_error.lineno}, column {decode_error.colno}: {decode_error.message}"
        raise ValidateBundleError(message=msg) from decode_error
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
        validation_error_msg = report_validation_error(category="mthds", validation_error=validation_error)
        msg = f"Could not load blueprints because of: {validation_error_msg}"
        raise ValidateBundleError(
            message=msg,
            pipe_validation_errors=pipe_validation_errors,
        ) from validation_error
    except PipeRunError as pipe_run_error:
        raise ValidateBundleError(
            message=pipe_run_error.message,
            dry_run_error_message=pipe_run_error.message,
        ) from pipe_run_error
    except DryRunError as dry_run_error:
        raise ValidateBundleError(
            message=dry_run_error.message,
            dry_run_error_message=dry_run_error.message,
        ) from dry_run_error
    return ValidateBundleResult(blueprints=all_blueprints, pipes=loaded_pipes, dry_run_result=dry_run_results)


class LoadConceptsOnlyResult(BaseModel):
    """Result of loading MTHDS files with concepts only (no pipes)."""

    blueprints: list[PipelexBundleBlueprint]
    concepts: list[Concept]


def load_concepts_only(
    mthds_file_path: Path | None = None,
    mthds_contents: list[str] | None = None,
    blueprints: list[PipelexBundleBlueprint] | None = None,
    library_dirs: Sequence[Path] | None = None,
) -> LoadConceptsOnlyResult:
    """Load MTHDS files processing only domains and concepts, skipping pipes.

    This is a lightweight alternative to validate_bundle() that only processes
    domains and concepts. It does not load pipes, does not perform pipe validation,
    and does not run dry runs.

    Args:
        mthds_file_path: Path to a single MTHDS file to load (mutually exclusive with others)
        mthds_contents: List of MTHDS content strings to load (mutually exclusive with others)
        blueprints: Pre-parsed blueprints to load (mutually exclusive with others)
        library_dirs: Optional directories containing additional MTHDS library files

    Returns:
        LoadConceptsOnlyResult with blueprints and loaded concepts

    Raises:
        ValidateBundleError: If loading fails due to interpreter or validation errors
    """
    provided_params = sum([blueprints is not None, mthds_contents is not None, mthds_file_path is not None])
    if provided_params == 0:
        msg = "At least one of blueprints, mthds_contents, or mthds_file_path must be provided to load_concepts_only"
        raise ValidateBundleError(message=msg)
    if provided_params > 1:
        msg = "Only one of blueprints, mthds_contents, or mthds_file_path can be provided to load_concepts_only, not multiple"
        raise ValidateBundleError(message=msg)

    library_manager = get_library_manager()
    library_id, library = library_manager.open_library()
    set_current_library(library_id=library_id)

    # Load libraries from resolved directories before loading the bundle
    effective_dirs, source_label = resolve_library_dirs(library_dirs)

    loaded_concepts: list[Concept] | None = None
    loaded_blueprints: list[PipelexBundleBlueprint] | None = None
    try:
        if effective_dirs:
            log.verbose(f"Loading concepts only from {len(effective_dirs)} library directory(ies) ({source_label})")
            library_manager.load_libraries_concepts_only(
                library_id=library_id,
                library_dirs=effective_dirs,
            )
        else:
            log.verbose(f"No library directories to load ({source_label})")

        if blueprints is not None:
            loaded_blueprints = blueprints
            loaded_concepts = library_manager.load_concepts_only_from_blueprints(library_id=library_id, blueprints=blueprints)
            return LoadConceptsOnlyResult(blueprints=loaded_blueprints, concepts=loaded_concepts)

        elif mthds_contents is not None:
            loaded_blueprints = [PipelexInterpreter.make_pipelex_bundle_blueprint(mthds_content=content) for content in mthds_contents]
            loaded_concepts = library_manager.load_concepts_only_from_blueprints(library_id=library_id, blueprints=loaded_blueprints)
            return LoadConceptsOnlyResult(blueprints=loaded_blueprints, concepts=loaded_concepts)

        else:
            assert mthds_file_path is not None
            blueprint = PipelexInterpreter.make_pipelex_bundle_blueprint(bundle_path=mthds_file_path)
            loaded_blueprints = [blueprint]

            if mthds_file_path.resolve() not in library.loaded_mthds_paths:
                # File not yet loaded - load it from the blueprint
                loaded_concepts = library_manager.load_concepts_only_from_blueprints(library_id=library_id, blueprints=[blueprint])
            else:
                # File already loaded - get existing concepts from library
                # For concepts-only loading, we just return empty list since concepts are already in library
                loaded_concepts = []

            return LoadConceptsOnlyResult(blueprints=loaded_blueprints, concepts=loaded_concepts)

    except MthdsDecodeError as decode_error:
        msg = f"TOML syntax error at line {decode_error.lineno}, column {decode_error.colno}: {decode_error.message}"
        raise ValidateBundleError(message=msg) from decode_error
    except PipelexInterpreterError as interpreter_error:
        raise ValidateBundleError(
            message=interpreter_error.message,
            pipelex_bundle_blueprint_validation_errors=interpreter_error.validation_errors,
        ) from interpreter_error
    except ValidationError as validation_error:
        pipe_validation_errors = categorize_pipe_validation_error(validation_error=validation_error)
        validation_error_msg = report_validation_error(category="mthds", validation_error=validation_error)
        msg = f"Could not load blueprints because of: {validation_error_msg}"
        raise ValidateBundleError(
            message=msg,
            pipe_validation_errors=pipe_validation_errors,
        ) from validation_error


def load_concepts_only_from_directory(directory: Path) -> LoadConceptsOnlyResult:
    """Load MTHDS files from a directory, processing only domains and concepts, skipping pipes.

    This is a lightweight alternative to validate_bundles_from_directory() that only
    processes domains and concepts. It does not load pipes, does not perform pipe
    validation, and does not run dry runs.

    Args:
        directory: Directory containing MTHDS files to load

    Returns:
        LoadConceptsOnlyResult with blueprints and loaded concepts

    Raises:
        ValidateBundleError: If loading fails due to interpreter or validation errors
    """
    mthds_files = get_pipelex_mthds_files_from_dirs(dirs={directory})
    all_blueprints: list[PipelexBundleBlueprint] = []

    library_manager = get_library_manager()
    library_id, _ = library_manager.open_library()
    set_current_library(library_id=library_id)
    try:
        for mthds_file in mthds_files:
            blueprint = PipelexInterpreter.make_pipelex_bundle_blueprint(bundle_path=mthds_file)
            all_blueprints.append(blueprint)

        loaded_concepts = library_manager.load_concepts_only_from_blueprints(library_id=library_id, blueprints=all_blueprints)
    except MthdsDecodeError as decode_error:
        msg = f"TOML syntax error at line {decode_error.lineno}, column {decode_error.colno}: {decode_error.message}"
        raise ValidateBundleError(message=msg) from decode_error
    except PipelexInterpreterError as interpreter_error:
        raise ValidateBundleError(
            message=interpreter_error.message,
            pipelex_bundle_blueprint_validation_errors=interpreter_error.validation_errors,
        ) from interpreter_error
    except ValidationError as validation_error:
        pipe_validation_errors = categorize_pipe_validation_error(validation_error=validation_error)
        validation_error_msg = report_validation_error(category="mthds", validation_error=validation_error)
        msg = f"Could not load blueprints because of: {validation_error_msg}"
        raise ValidateBundleError(
            message=msg,
            pipe_validation_errors=pipe_validation_errors,
        ) from validation_error
    return LoadConceptsOnlyResult(blueprints=all_blueprints, concepts=loaded_concepts)
