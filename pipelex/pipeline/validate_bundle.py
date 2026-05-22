import asyncio
from pathlib import Path
from typing import Sequence

from pydantic import BaseModel, ValidationError

from pipelex import log
from pipelex.base_exceptions import ErrorDomain, PipelexError
from pipelex.cogt.inference.error_classification import UserAction, UserActionKind
from pipelex.config import get_config
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
from pipelex.pipe_run.exceptions import PipeRunError
from pipelex.pipe_run.pipe_run_mode import PipeRunMode
from pipelex.pipeline.exceptions import PipeExecutionError, PipelineExecutionError
from pipelex.pipeline.runner import PipelexRunner


class ValidateBundleError(PipelexError):
    """Raised when bundle validation fails.

    This error aggregates validation errors from different stages:
    - Blueprint validation errors (from interpreter)
    - Pipe factory errors (from PipeFactoryError exceptions, e.g., missing concepts)
    - Pipe validation errors (from PipeValidationError exceptions)
    - Pipe/Concept instantiation errors (from Pydantic ValidationError during factory instantiation)
    - Dry run errors
    """

    error_domain = ErrorDomain.INPUT
    user_action = UserAction(
        kind=UserActionKind.CHANGE_INPUT,
        detail="Check the validation_errors array for specific issues",
    )

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
        self.pipe_validation_errors = pipe_validation_errors or []

        # Pipe/Concept instantiation errors from Pydantic ValidationError
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
    dry_run_failures: dict[str, str]


async def dry_run_loaded_pipes(
    pipe_refs: list[str],
    library_id: str,
) -> dict[str, str]:
    """Run each pipe in DRY mode via :class:`PipelexRunner`; return failures.

    The library identified by ``library_id`` must already be open and loaded — this helper
    reuses it (``keep_library_loaded=True``) so it survives across iterations. Each pipe gets
    its own runner invocation with ``is_mock_inputs=True`` so missing inputs are auto-generated.

    Returns:
        A dict mapping the pipe_ref of failed pipes to a human-readable error message.
        Successful pipes are absent from the dict.
    """
    execution_config = get_config().pipelex.pipeline_execution_config.with_graph_config_overrides(mock_inputs=True)
    failures: dict[str, str] = {}
    for pipe_ref in pipe_refs:
        runner = PipelexRunner(
            library_id=library_id,
            library_dirs=[],
            pipe_run_mode=PipeRunMode.DRY,
            execution_config=execution_config,
            keep_library_loaded=True,
        )
        try:
            await runner.execute_pipeline(pipe_code=pipe_ref)
        except (PipelineExecutionError, PipeExecutionError, PipeRunError) as exc:
            failures[pipe_ref] = exc.message
    return failures


async def dry_run_loaded_pipes_or_raise(pipe_refs: list[str], library_id: str) -> dict[str, str]:
    """Dry-run pipes and raise an aggregated :class:`PipeRunError` if any fail."""
    failures = await dry_run_loaded_pipes(pipe_refs=pipe_refs, library_id=library_id)
    if failures:
        details = "\n".join(f"'{ref}': {msg}" for ref, msg in failures.items())
        msg = f"Dry run failed for {len(failures)} pipe(s):\n{details}"
        first_failed_ref = next(iter(failures))
        raise PipeRunError(message=msg, run_mode=PipeRunMode.DRY, pipe_code=first_failed_ref)
    return failures


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

    loaded_pipes: list[PipeAbstract]
    loaded_blueprints: list[PipelexBundleBlueprint]
    dry_run_failures: dict[str, str] = {}
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
        elif mthds_contents is not None:
            loaded_blueprints = [PipelexInterpreter.make_pipelex_bundle_blueprint(mthds_content=content) for content in mthds_contents]
            loaded_pipes = library_manager.load_from_blueprints(library_id=library_id, blueprints=loaded_blueprints)
        else:
            assert mthds_file_path is not None
            blueprint = PipelexInterpreter.make_pipelex_bundle_blueprint(bundle_path=mthds_file_path)
            loaded_blueprints = [blueprint]

            if mthds_file_path.resolve() not in library.loaded_mthds_paths:
                loaded_pipes = library_manager.load_from_blueprints(library_id=library_id, blueprints=[blueprint])
            else:
                pipe_codes = list(blueprint.pipe.keys()) if blueprint.pipe else []
                loaded_pipes = [library.pipe_library.get_required_pipe(pipe_code=code) for code in pipe_codes]

        dry_run_failures = await dry_run_loaded_pipes(
            pipe_refs=[pipe.pipe_ref for pipe in loaded_pipes],
            library_id=library_id,
        )
        if dry_run_failures:
            details = "\n".join(f"'{ref}': {msg}" for ref, msg in dry_run_failures.items())
            aggregated = f"Dry run failed for {len(dry_run_failures)} pipe(s):\n{details}"
            raise ValidateBundleError(message=aggregated, dry_run_error_message=aggregated)
        return ValidateBundleResult(blueprints=loaded_blueprints, pipes=loaded_pipes, dry_run_failures=dry_run_failures)

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
        dry_run_failures = await dry_run_loaded_pipes_or_raise(
            pipe_refs=[pipe.pipe_ref for pipe in loaded_pipes],
            library_id=library_id,
        )
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
    return ValidateBundleResult(blueprints=all_blueprints, pipes=loaded_pipes, dry_run_failures=dry_run_failures)


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
    """Load MTHDS files from a directory, processing only domains and concepts, skipping pipes."""
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
