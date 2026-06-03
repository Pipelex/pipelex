import asyncio
from collections.abc import Generator
from contextlib import contextmanager
from pathlib import Path
from typing import Literal, Sequence, TypedDict

from pydantic import BaseModel, ValidationError
from typing_extensions import assert_never

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
from pipelex.hub import (
    clear_current_library,
    get_current_library_id_or_none,
    get_library_manager,
    resolve_library_dirs,
    set_current_library,
)
from pipelex.libraries.library_utils import get_pipelex_mthds_files_from_dirs
from pipelex.libraries.pipe.exceptions import PipeNotFoundError
from pipelex.pipe_run.exceptions import DryRunError, PipeRunError
from pipelex.pipe_signature.exceptions import SignaturesNotAllowedError
from pipelex.pipeline.bundle_validator import BundleValidator, DryRunOutput, DryRunStatus
from pipelex.pipeline.exceptions import ValidateBundleError


class ValidateBundleResult(BaseModel):
    blueprints: list[PipelexBundleBlueprint]
    pipes: list[PipeAbstract]
    dry_run_result: dict[str, DryRunOutput]


class ValidatedPipeEntry(TypedDict):
    """One entry in the ``validated_pipes`` JSON envelope returned by the validate surfaces.

    The ``pipe_code`` key carries the namespaced ``pipe_ref`` (``domain.code``) — the key name is
    kept for the published JSON contract, but the value is the qualified ref, never the bare code.
    ``status`` is a ``DryRunStatus`` (a ``StrEnum``), so it serializes to its plain string value.
    """

    pipe_code: str
    status: DryRunStatus


def build_validated_pipes(dry_run_result: dict[str, DryRunOutput]) -> list[ValidatedPipeEntry]:
    """Project a dry-run result map into the ``validated_pipes`` JSON list (agent CLI + builder ops).

    Each entry is built from the real per-pipe outcome, so allowed-to-fail FAILUREs and cross-package
    SKIPPEDs are reported truthfully rather than flattened to SUCCESS. The entry id is the namespaced
    ``pipe_ref`` (``domain.code``) on every surface — one unambiguous identity that cannot collide
    across domains, so the same pipe is never reported under two identifiers by different commands.
    """
    return [ValidatedPipeEntry(pipe_code=output.pipe_ref, status=output.status) for output in dry_run_result.values()]


@contextmanager
def _translate_to_validate_bundle_error(category: Literal["pipe", "concept"]) -> Generator[None, None, None]:
    """Translate the bundle-loading exception surface into a single ``ValidateBundleError``.

    Single source of truth for the bundle-loading error cascade, used by all
    four entry points: ``validate_bundle`` / ``validate_bundles_from_directory``
    (full pipe + dry-run path, ``category="pipe"``) and ``load_concepts_only`` /
    ``load_concepts_only_from_directory`` (concepts-only path,
    ``category="concept"``). A ``PipelexInterpreterError`` becomes a
    ``ValidateBundleError`` carrying the blueprint validation errors, a
    ``PipeFactoryError`` carries the categorized factory error, etc. Sharing one
    source of truth means a new handler only needs to be added once. The
    pipe-loading / dry-run handlers (``PipeFactoryError``, ``PipeValidationError``,
    ``PipeRunError``, ``DryRunError``, ``SignaturesNotAllowedError``) are dead code
    in the concepts-only paths (those functions never instantiate pipes or run dry
    runs), but they are harmless there — they simply never fire.

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
            case _ as unreachable:
                # ``category`` is ``Literal["pipe", "concept"]`` — pyright catches a
                # bad call site statically, but the runtime can still receive an
                # unexpected value via ``# type: ignore`` or dynamic dispatch. Loud
                # ``AssertionError`` beats silent ``UnboundLocalError`` on ``msg``.
                assert_never(unreachable)
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
    except SignaturesNotAllowedError as sig_error:
        # Strict-mode dry-run refused because the dependency graph reaches a
        # ``PipeSignature`` placeholder. Carry the error so the CLI can render the
        # offending signatures and the dependency chains that reach them.
        raise ValidateBundleError(
            message=str(sig_error),
            signature_check_error=sig_error,
        ) from sig_error


def _pipes_to_dry_run(loaded_pipes: list[PipeAbstract], dry_run_pipe_codes: list[str] | None) -> list[PipeAbstract]:
    """Select which loaded pipes to dry-run.

    Returns every loaded pipe when ``dry_run_pipe_codes`` is ``None`` (whole-bundle validation).
    Otherwise returns only the pipes whose bare ``code`` or qualified ``pipe_ref`` is requested —
    used by the ``--pipe`` path to validate a single implemented slice of a partially stubbed
    bundle without dry-running (and thus rejecting) unrelated pipes or signatures. Filtering here,
    before ``BundleValidator.validate_pipes``, also narrows its strict signature pre-check to just the selected pipe.

    Raises:
        PipeNotFoundError: when ``dry_run_pipe_codes`` names a pipe absent from the loaded bundle —
            so a typo'd ``--pipe`` argument fails loudly instead of passing vacuously.
    """
    if dry_run_pipe_codes is None:
        return loaded_pipes
    wanted = set(dry_run_pipe_codes)
    selected = [pipe for pipe in loaded_pipes if pipe.code in wanted or pipe.pipe_ref in wanted]
    matched = {pipe.code for pipe in selected} | {pipe.pipe_ref for pipe in selected}
    missing = wanted - matched
    if missing:
        missing_str = ", ".join(f"'{code}'" for code in sorted(missing))
        msg = f"Pipe(s) {missing_str} not found in the bundle. Check for typos and make sure they are declared in the bundle."
        raise PipeNotFoundError(msg)
    return selected


async def validate_bundle(
    mthds_file_path: Path | None = None,
    mthds_contents: list[str] | None = None,
    library_dirs: Sequence[Path] | None = None,
    allow_signatures: bool = False,
    dry_run_pipe_codes: list[str] | None = None,
) -> ValidateBundleResult:
    provided_params = sum(
        [
            mthds_contents is not None,
            mthds_file_path is not None,
        ]
    )
    if provided_params == 0:
        msg = "At least one of mthds_contents or mthds_file_path must be provided to validate_bundle"
        raise ValidateBundleError(message=msg)
    if provided_params > 1:
        msg = "Only one of mthds_contents or mthds_file_path can be provided to validate_bundle, not both"
        raise ValidateBundleError(message=msg)

    library_manager = get_library_manager()
    library_id, library = library_manager.open_library()
    success = False
    prev_library_id = get_current_library_id_or_none()
    try:
        set_current_library(library_id=library_id)

        # Load libraries from resolved directories before loading the bundle
        effective_dirs, source_label = resolve_library_dirs(library_dirs)

        loaded_pipes: list[PipeAbstract] | None = None
        loaded_blueprints: list[PipelexBundleBlueprint] | None = None
        await asyncio.sleep(0)  # Yield to event loop (keeps function async-compatible)
        with _translate_to_validate_bundle_error(category="pipe"):
            if effective_dirs:
                log.verbose(f"Loading libraries from {len(effective_dirs)} directory(ies) ({source_label}) for validation")
                library_manager.load_libraries(
                    library_id=library_id,
                    library_dirs=effective_dirs,
                )
            else:
                log.verbose(f"No library directories to load ({source_label})")
            if mthds_contents is not None:
                loaded_blueprints = [PipelexInterpreter.make_pipelex_bundle_blueprint(mthds_content=content) for content in mthds_contents]
                loaded_pipes = library_manager.load_from_blueprints(library_id=library_id, blueprints=loaded_blueprints)
                dry_run_results = await BundleValidator().validate_pipes(
                    pipes=_pipes_to_dry_run(loaded_pipes, dry_run_pipe_codes), library_id=library_id, allow_signatures=allow_signatures
                )
                result = ValidateBundleResult(blueprints=loaded_blueprints, pipes=loaded_pipes, dry_run_result=dry_run_results)

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

                dry_run_results = await BundleValidator().validate_pipes(
                    pipes=_pipes_to_dry_run(loaded_pipes, dry_run_pipe_codes), library_id=library_id, allow_signatures=allow_signatures
                )
                result = ValidateBundleResult(blueprints=loaded_blueprints, pipes=loaded_pipes, dry_run_result=dry_run_results)
        success = True
        return result
    finally:
        if not success:
            # Restore the caller's outer current-library FIRST so the safety
            # guarantee holds even when ``library_manager.teardown`` raises
            # (e.g. ``LibraryError`` on a double-teardown race) — otherwise the
            # outer scope is left holding the just-torn-down ``library_id``.
            # ``set_current_library`` cannot accept ``None``, so route the
            # "no outer was set" case through ``clear_current_library``.
            if prev_library_id is not None:
                set_current_library(library_id=prev_library_id)
            else:
                clear_current_library()
            library_manager.teardown(library_id=library_id)


async def validate_bundles_from_directory(directory: Path, allow_signatures: bool = False) -> ValidateBundleResult:
    mthds_files = get_pipelex_mthds_files_from_dirs(dirs={directory})
    all_blueprints: list[PipelexBundleBlueprint] = []

    library_manager = get_library_manager()
    library_id, _ = library_manager.open_library()
    success = False
    prev_library_id = get_current_library_id_or_none()
    try:
        set_current_library(library_id=library_id)
        with _translate_to_validate_bundle_error(category="pipe"):
            for mthds_file in mthds_files:
                blueprint = PipelexInterpreter.make_pipelex_bundle_blueprint(bundle_path=mthds_file)
                all_blueprints.append(blueprint)

            loaded_pipes = library_manager.load_libraries(library_id=library_id, library_dirs=[Path(directory)])
            dry_run_results = await BundleValidator().validate_pipes(pipes=loaded_pipes, library_id=library_id, allow_signatures=allow_signatures)
            result = ValidateBundleResult(blueprints=all_blueprints, pipes=loaded_pipes, dry_run_result=dry_run_results)
        success = True
        return result
    finally:
        if not success:
            # See ``validate_bundle``: restore the outer current-library before
            # ``library_manager.teardown`` so the guarantee survives a teardown raise.
            if prev_library_id is not None:
                set_current_library(library_id=prev_library_id)
            else:
                clear_current_library()
            library_manager.teardown(library_id=library_id)


class LoadConceptsOnlyResult(BaseModel):
    """Result of loading MTHDS files with concepts only (no pipes)."""

    blueprints: list[PipelexBundleBlueprint]
    concepts: list[Concept]


def load_concepts_only(
    mthds_file_path: Path | None = None,
    mthds_contents: list[str] | None = None,
    library_dirs: Sequence[Path] | None = None,
) -> LoadConceptsOnlyResult:
    """Load MTHDS files processing only domains and concepts, skipping pipes.

    This is a lightweight alternative to validate_bundle() that only processes
    domains and concepts. It does not load pipes, does not perform pipe validation,
    and does not run dry runs.

    Args:
        mthds_file_path: Path to a single MTHDS file to load (mutually exclusive with mthds_contents)
        mthds_contents: List of MTHDS content strings to load (mutually exclusive with mthds_file_path)
        library_dirs: Optional directories containing additional MTHDS library files

    Returns:
        LoadConceptsOnlyResult with blueprints and loaded concepts

    Raises:
        ValidateBundleError: If loading fails due to interpreter or validation errors
    """
    provided_params = sum([mthds_contents is not None, mthds_file_path is not None])
    if provided_params == 0:
        msg = "At least one of mthds_contents or mthds_file_path must be provided to load_concepts_only"
        raise ValidateBundleError(message=msg)
    if provided_params > 1:
        msg = "Only one of mthds_contents or mthds_file_path can be provided to load_concepts_only, not both"
        raise ValidateBundleError(message=msg)

    library_manager = get_library_manager()
    library_id, library = library_manager.open_library()
    success = False
    prev_library_id = get_current_library_id_or_none()
    try:
        set_current_library(library_id=library_id)

        # Load libraries from resolved directories before loading the bundle
        effective_dirs, source_label = resolve_library_dirs(library_dirs)

        loaded_concepts: list[Concept] | None = None
        loaded_blueprints: list[PipelexBundleBlueprint] | None = None
        with _translate_to_validate_bundle_error(category="concept"):
            if effective_dirs:
                log.verbose(f"Loading concepts only from {len(effective_dirs)} library directory(ies) ({source_label})")
                library_manager.load_libraries_concepts_only(
                    library_id=library_id,
                    library_dirs=effective_dirs,
                )
            else:
                log.verbose(f"No library directories to load ({source_label})")

            if mthds_contents is not None:
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
            # See ``validate_bundle``: restore the outer current-library before
            # ``library_manager.teardown`` so the guarantee survives a teardown raise.
            if prev_library_id is not None:
                set_current_library(library_id=prev_library_id)
            else:
                clear_current_library()
            library_manager.teardown(library_id=library_id)


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
    success = False
    prev_library_id = get_current_library_id_or_none()
    try:
        set_current_library(library_id=library_id)
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
            # See ``validate_bundle``: restore the outer current-library before
            # ``library_manager.teardown`` so the guarantee survives a teardown raise.
            if prev_library_id is not None:
                set_current_library(library_id=prev_library_id)
            else:
                clear_current_library()
            library_manager.teardown(library_id=library_id)
