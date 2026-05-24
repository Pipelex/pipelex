import asyncio
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path
from typing import Literal, Sequence

from pydantic import BaseModel, ValidationError

from pipelex import log
from pipelex.core.bundles.pipelex_bundle_blueprint import PipelexBundleBlueprint
from pipelex.core.concepts.concept import Concept
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
from pipelex.hub import get_library_manager, resolve_library_dirs, set_current_library, teardown_current_library
from pipelex.libraries.library_utils import get_pipelex_mthds_files_from_dirs
from pipelex.pipe_run.dry_run import DryRunOutput, dry_run_pipes
from pipelex.pipe_run.exceptions import DryRunError, PipeRunError
from pipelex.pipeline.exceptions import ValidateBundleError


class ValidateBundleResult(BaseModel):
    blueprints: list[PipelexBundleBlueprint]
    pipes: list[PipeAbstract]
    dry_run_result: dict[str, DryRunOutput]


@contextmanager
def _translate_to_validate_bundle_error(category: Literal["pipe", "concept"]) -> Iterator[None]:
    """Translate the bundle-loading exception surface into a single ``ValidateBundleError``.

    Single source of truth for the bundle-loading error cascade, used by all
    four entry points: ``validate_bundle`` / ``validate_bundles_from_directory``
    (full pipe + dry-run path, ``category="pipe"``) and ``load_concepts_only`` /
    ``load_concepts_only_from_directory`` (concepts-only path,
    ``category="concept"``). A ``PipelexInterpreterError`` becomes a
    ``ValidateBundleError`` carrying the blueprint validation errors, a
    ``PipeFactoryError`` carries the categorized factory error, etc. Sharing one
    source of truth means a new handler only needs to be added once. The four
    pipe-loading / dry-run handlers (``PipeFactoryError``, ``PipeValidationError``,
    ``PipeRunError``, ``DryRunError``) are dead code in the concepts-only paths
    (those functions never instantiate pipes or run dry runs), but they are
    harmless there — they simply never fire.

    ``category`` controls the user-facing framing for the one branch that fires
    from both paths: the ``except ValidationError`` arm catches pydantic
    validation errors raised during model construction. A concepts-only path
    that fails ``Concept`` validation must not be framed as a pipe-validation
    error — pass ``category="concept"`` to surface concept-aware copy.
    """
    try:
        yield
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
    # Cascade order: ``except PipeValidationError`` must precede
    # ``except ValidationError``. Their sibling-under-``ValueError``
    # relationship (``PipeValidationError(ValueError)``, not a subclass of
    # ``pydantic.ValidationError``) is pinned by
    # ``tests/unit/pipelex/pipeline/test_validate_bundle_helper.py``.
    except PipeValidationError as pipe_error:
        pipe_error_data = categorize_pipe_validation_with_libraries_error(pipe_error=pipe_error)
        raise ValidateBundleError(
            message=f"Pipe validation failed: {pipe_error}",
            pipe_validation_errors=[pipe_error_data],
        ) from pipe_error
    except ValidationError as validation_error:
        pipe_validation_errors = categorize_pipe_validation_error(validation_error=validation_error)
        validation_error_msg = report_validation_error(category="mthds", validation_error=validation_error)
        match category:
            case "pipe":
                msg = f"Could not load blueprints because of: {validation_error_msg}"
            case "concept":
                msg = f"Could not load concepts because of: {validation_error_msg}"
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
    success = False
    try:
        with _translate_to_validate_bundle_error(category="pipe"):
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
                # TODO: wip - restore or refactor dry run
                # dry_run_results = await dry_run_pipes(pipes=loaded_pipes, raise_on_failure=True)
                result = ValidateBundleResult(blueprints=loaded_blueprints, pipes=loaded_pipes, dry_run_result={})

            elif mthds_contents is not None:
                loaded_blueprints = [PipelexInterpreter.make_pipelex_bundle_blueprint(mthds_content=content) for content in mthds_contents]
                loaded_pipes = library_manager.load_from_blueprints(library_id=library_id, blueprints=loaded_blueprints)
                # TODO: wip - restore or refactor dry run
                # dry_run_results = await dry_run_pipes(pipes=loaded_pipes, raise_on_failure=True)
                result = ValidateBundleResult(blueprints=loaded_blueprints, pipes=loaded_pipes, dry_run_result={})

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

                # TODO: wip - restore or refactor dry run
                # dry_run_results = await dry_run_pipes(pipes=loaded_pipes, raise_on_failure=True)
                result = ValidateBundleResult(blueprints=loaded_blueprints, pipes=loaded_pipes, dry_run_result={})
        success = True
        return result
    finally:
        if not success:
            library_manager.teardown(library_id=library_id)
            teardown_current_library()


async def validate_bundles_from_directory(directory: Path) -> ValidateBundleResult:
    mthds_files = get_pipelex_mthds_files_from_dirs(dirs={directory})
    all_blueprints: list[PipelexBundleBlueprint] = []

    library_manager = get_library_manager()
    library_id, _ = library_manager.open_library()
    set_current_library(library_id=library_id)
    success = False
    try:
        with _translate_to_validate_bundle_error(category="pipe"):
            for mthds_file in mthds_files:
                blueprint = PipelexInterpreter.make_pipelex_bundle_blueprint(bundle_path=mthds_file)
                all_blueprints.append(blueprint)

            loaded_pipes = library_manager.load_libraries(library_id=library_id, library_dirs=[Path(directory)])
            dry_run_results = await dry_run_pipes(pipes=loaded_pipes, raise_on_failure=True)
            result = ValidateBundleResult(blueprints=all_blueprints, pipes=loaded_pipes, dry_run_result=dry_run_results)
        success = True
        return result
    finally:
        if not success:
            library_manager.teardown(library_id=library_id)
            teardown_current_library()


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
    success = False
    try:
        with _translate_to_validate_bundle_error(category="concept"):
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
                result = LoadConceptsOnlyResult(blueprints=loaded_blueprints, concepts=loaded_concepts)

            elif mthds_contents is not None:
                loaded_blueprints = [PipelexInterpreter.make_pipelex_bundle_blueprint(mthds_content=content) for content in mthds_contents]
                loaded_concepts = library_manager.load_concepts_only_from_blueprints(library_id=library_id, blueprints=loaded_blueprints)
                result = LoadConceptsOnlyResult(blueprints=loaded_blueprints, concepts=loaded_concepts)

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

                result = LoadConceptsOnlyResult(blueprints=loaded_blueprints, concepts=loaded_concepts)
        success = True
        return result
    finally:
        if not success:
            library_manager.teardown(library_id=library_id)
            teardown_current_library()


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
    success = False
    try:
        with _translate_to_validate_bundle_error(category="concept"):
            for mthds_file in mthds_files:
                blueprint = PipelexInterpreter.make_pipelex_bundle_blueprint(bundle_path=mthds_file)
                all_blueprints.append(blueprint)

            loaded_concepts = library_manager.load_concepts_only_from_blueprints(library_id=library_id, blueprints=all_blueprints)
            result = LoadConceptsOnlyResult(blueprints=all_blueprints, concepts=loaded_concepts)
        success = True
        return result
    finally:
        if not success:
            library_manager.teardown(library_id=library_id)
            teardown_current_library()
