import asyncio
from collections.abc import Generator
from contextlib import contextmanager
from pathlib import Path
from typing import Sequence

from pydantic import BaseModel, ValidationError

# TypedDict from typing_extensions, not typing: pydantic rejects typing.TypedDict as a model
# field on Python < 3.12, and ValidatedPipeEntry is a field of PipelexValidationReport.
from typing_extensions import TypedDict

from pipelex import log
from pipelex.base_exceptions import PipelexUnexpectedError
from pipelex.core.pipes.exceptions import PipeFactoryError, PipeRunError, PipeValidationError
from pipelex.core.qualified_ref import QualifiedRef
from pipelex.core.validation import report_validation_error
from pipelex.interpreter_hub import (
    clear_current_library,
    get_current_library_id_or_none,
    get_library_manager,
    resolve_library_dirs,
    set_current_library,
)
from pipelex.libraries.exceptions import LibraryError, LibraryLoadingError
from pipelex.libraries.library_utils import get_pipelex_mthds_files_from_dirs
from pipelex.libraries.pipe.exceptions import PipeNotFoundError
from pipelex.mthds_parsing.exceptions import MthdsParserError
from pipelex.mthds_parsing.handle_pipe_errors import (
    categorize_pipe_factory_error,
    categorize_pipe_validation_error,
    categorize_pipe_validation_with_libraries_error,
)
from pipelex.mthds_parsing.parser import MthdsParser
from pipelex.mthds_parsing.pipelex_bundle_blueprint import PipelexBundleBlueprint
from pipelex.pipe_machinery.pipe_abstract import PipeAbstract
from pipelex.pipe_run.exceptions import DryRunError
from pipelex.pipeline.bundle_validator import BundleValidator, DryRunOutput, DryRunStatus
from pipelex.pipeline.exceptions import ValidateBundleError
from pipelex.system.registries.exceptions import FuncRegistryError


class ValidateBundleResult(BaseModel):
    blueprints: list[PipelexBundleBlueprint]
    pipes: list[PipeAbstract]
    dry_run_result: dict[str, DryRunOutput]
    pending_signatures: list[str]
    """Qualified refs of pipes still declared as ``PipeSignature`` in the assembled library.

    These are the unimplemented headers left after the merge: a forward-declared pipe that no
    concrete definition has satisfied yet. Computed library-wide (not just from the triggering
    file's pipes), so a lenient ``--allow-signatures`` success can report exactly what remains to
    be implemented even when validating one file of a multi-file library at a time.
    """


class ValidatedPipeEntry(TypedDict):
    """One entry in the ``validated_pipes`` JSON envelope returned by the validate surfaces.

    The ``pipe_ref`` key carries the namespaced ``pipe_ref`` (``domain.code``) — never the bare code.
    ``status`` is a ``DryRunStatus`` (a ``StrEnum``), so it serializes to its plain string value.
    """

    pipe_ref: str
    status: DryRunStatus


def build_validated_pipes(dry_run_result: dict[str, DryRunOutput]) -> list[ValidatedPipeEntry]:
    """Project a dry-run result map into the ``validated_pipes`` JSON list (agent CLI + builder ops).

    Each entry is built from the real per-pipe outcome, so allowed-to-fail FAILUREs and cross-package
    SKIPPEDs are reported truthfully rather than flattened to SUCCESS. The entry id is the namespaced
    ``pipe_ref`` (``domain.code``) on every surface — one unambiguous identity that cannot collide
    across domains, so the same pipe is never reported under two identifiers by different commands.
    """
    return [ValidatedPipeEntry(pipe_ref=output.pipe_ref, status=output.status) for output in dry_run_result.values()]


def build_pending_signatures(pipes_by_ref: dict[str, PipeAbstract]) -> list[str]:
    """Qualified refs of pipes still declared as ``PipeSignature`` (unsatisfied forward declarations).

    Once a concrete pipe reconciles with a signature, the concrete replaces it in the merged
    library (Part A), so the unsatisfied set is exactly the pipes still typed ``PipeSignature`` —
    no ``{signatures} - {concretes}`` arithmetic needed. Pass the assembled library's pipe map
    (``pipe_library.get_pipes_dict()``, not a single file's pipes) to get the library-wide set.

    Cross-package dependency pipes (keyed ``alias->...`` by the loader) are excluded: another
    package's unimplemented headers are not the caller's to satisfy, so they must not appear in the
    "what remains to implement" nudge.
    """
    return sorted(pipe.pipe_ref for ref_key, pipe in pipes_by_ref.items() if pipe.is_signature and not QualifiedRef.has_cross_package_prefix(ref_key))


def _backfill_pipe_error_source(pipe_error: PipeValidationError) -> None:
    """Backfill ``file_path`` on a pipe-channel error from the library manager's pipe-source map.

    Raise sites (``PipeAbstract`` input checks, ``PipeSequence`` output checks) don't know their
    file — pipes deliberately carry no source; provenance lives in the crate's ``source_map``,
    mirrored into the current library's source map during load, *before* ``validate_library``
    runs. Intercepting once at this catch boundary covers every raise site, present and future.

    Lookup is by the full ``domain.pipe_code`` ref only — never the bare-code suffix fallback
    (under the strict own-domain resolution rule, a bare-code suffix match would guess a file
    where the qualified ref did not resolve). A miss leaves ``file_path`` as ``None``: the fix stays source-less and
    falls under the conservative single-file rule, which is the safe direction.
    """
    if pipe_error.file_path is not None:
        return
    if pipe_error.domain_code is None or pipe_error.pipe_code is None:
        return
    source = get_library_manager().get_pipe_source(f"{pipe_error.domain_code}.{pipe_error.pipe_code}")
    if source is not None:
        # Compatibility boundary: injected managers written against the previous protocol may
        # still return ``Path``. Normalize before assigning to the string-only error model.
        pipe_error.file_path = str(source)


@contextmanager
def translate_to_validate_bundle_error() -> Generator[None, None, None]:
    """Translate the bundle-loading exception surface into a single ``ValidateBundleError``.

    Single source of truth for the bundle-loading error cascade, shared by the
    bundle-loading entry points: ``validate_bundle``, ``validate_bundles_from_directory``,
    and ``pipelex.pipeline.resolve_bundle.resolve_crate_from_contents``.
    A ``MthdsParserError`` becomes a ``ValidateBundleError`` carrying the
    blueprint validation errors, a ``PipeFactoryError`` carries the categorized
    factory error, etc. Sharing one source of truth means a new handler only
    needs to be added once.
    """
    try:
        yield
    except MthdsParserError as parser_error:
        raise ValidateBundleError(
            message=parser_error.message,
            pipelex_bundle_blueprint_validation_errors=parser_error.validation_errors,
        ) from parser_error
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
        _backfill_pipe_error_source(pipe_error)
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
    except PipeNotFoundError:
        # PipeNotFoundError is a PipeLibraryError (hence a LibraryError), but it is NOT a bundle
        # merge/load failure: it means a requested --pipe slice names a pipe absent from the bundle.
        # It has its own dedicated CLI handler (execute_validate's `except PipeNotFoundError`), so it
        # must propagate raw rather than be folded into a ValidateBundleError by the arm below.
        raise
    except LibraryError as library_error:
        # Library merge / load failures that are NOT pydantic ValidationErrors: undeclared
        # cross-file concept references (ConceptLibraryError), signature/concrete contract
        # mismatches and duplicate concept/pipe refs (ConceptLibraryError / PipeLibraryError), and
        # the structured LibraryLoadingError aggregate (concept cycles, reserved-domain
        # violations, factory failures). Surface them as a clean ValidateBundleError instead of a
        # raw traceback. LibraryLoadingError carries blueprint- and pipe/concept-validation errors;
        # forward them so the CLI renders the same structured detail it does for the other arms.
        if isinstance(library_error, LibraryLoadingError):
            blueprint_validation_errors = library_error.blueprint_validation_errors
            pipe_concept_validation_errors = library_error.pipe_concept_validation_errors
        else:
            blueprint_validation_errors = None
            pipe_concept_validation_errors = None
        raise ValidateBundleError(
            message=library_error.message,
            pipelex_bundle_blueprint_validation_errors=blueprint_validation_errors,
            pipe_validation_errors=pipe_concept_validation_errors,
        ) from library_error
    except FuncRegistryError as func_registry_error:
        # A duplicate @pipe_func name across the scanned library dirs. Raised while loading the
        # library, so it lands here rather than on the PipeFunc field validator's ValueError path.
        # It is caller-fixable input (rename one with @pipe_func(name=...)), so it must produce a
        # verdict — `is_valid: false` — not the "no verdict could be produced" exit 2 / 5xx an
        # untranslated error would give.
        raise ValidateBundleError(message=func_registry_error.message) from func_registry_error
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


def _pipes_to_dry_run(loaded_pipes: list[PipeAbstract], *, dry_run_pipe_codes: list[str] | None) -> list[PipeAbstract]:
    """Select which loaded pipes to dry-run.

    Returns every loaded pipe when ``dry_run_pipe_codes`` is ``None`` (whole-bundle validation).
    Otherwise returns only the pipes whose bare ``code`` or qualified ``pipe_ref`` is requested —
    used by the ``--pipe`` path to validate a single implemented slice of a partially stubbed
    bundle without dry-running unrelated pipes. Filtering here, before ``BundleValidator.validate_pipes``,
    narrows the dry-run sweep to just the selected pipe (signatures are never an error either way — D-B).

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
    *,
    mthds_contents: list[str] | None = None,
    mthds_sources: Sequence[str | None] | None = None,
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
        # Programmer error: a caller (the HTTP request layer, a builder op) must wire exactly one
        # input. It is not a content verdict the end user can fix → PipelexUnexpectedError (→ 500,
        # redacted under STRICT), matching the mthds_sources-mismatch guard below — never a
        # ValidateBundleError, which would 200/422 a host-wiring bug as if the bundle were invalid.
        msg = "At least one of mthds_contents or mthds_file_path must be provided to validate_bundle"
        raise PipelexUnexpectedError(msg)
    if provided_params > 1:
        msg = "Only one of mthds_contents or mthds_file_path can be provided to validate_bundle, not both"
        raise PipelexUnexpectedError(msg)
    if mthds_contents is not None and not mthds_contents:
        # An EMPTY list is not None, so it passes the provided-params check above — without this
        # guard it would yield a blueprint-less result that downstream consumers (the canonical
        # report's primary-blueprint selection) cannot represent.
        msg = "mthds_contents must not be empty: provide at least one MTHDS content to validate"
        raise ValidateBundleError(message=msg)
    if mthds_sources is not None and (mthds_contents is None or len(mthds_sources) != len(mthds_contents)):
        # ``mthds_sources`` is a per-content source list (the host — e.g. an HTTP API —
        # threads each bundle's source onto the in-memory load path so its diagnostics carry a
        # real ``source``). It is never supplied by the end caller, so a missing-alongside /
        # length-mismatch is a host wiring bug, not bad user input: raise an internal error
        # (→ 500, redacted under STRICT) rather than ``ValidateBundleError`` (→ caller-facing
        # 422). Contrast the empty-``mthds_contents`` guard above, which can legitimately
        # reflect an end user submitting no bundles and so stays a caller-facing input error.
        msg = "mthds_sources, when provided, must be a per-item source list matching mthds_contents in length"
        raise PipelexUnexpectedError(msg)

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
        with translate_to_validate_bundle_error():
            if effective_dirs:
                log.verbose(f"Loading libraries from {len(effective_dirs)} directory(ies) ({source_label}) for validation")
                library_manager.load_libraries(
                    library_id=library_id,
                    library_dirs=effective_dirs,
                )
            else:
                log.verbose(f"No library directories to load ({source_label})")
            if mthds_contents is not None:
                content_sources: list[str | None] = list(mthds_sources) if mthds_sources is not None else [None] * len(mthds_contents)
                loaded_blueprints = [
                    MthdsParser.make_pipelex_bundle_blueprint(mthds_content=content, mthds_source=source)
                    for content, source in zip(mthds_contents, content_sources, strict=True)
                ]
                loaded_pipes = library_manager.load_from_blueprints(library_id=library_id, blueprints=loaded_blueprints)
                dry_run_results = await BundleValidator().validate_pipes(
                    pipes=_pipes_to_dry_run(loaded_pipes, dry_run_pipe_codes=dry_run_pipe_codes),
                    library_id=library_id,
                    allow_signatures=allow_signatures,
                )
                result = ValidateBundleResult(
                    blueprints=loaded_blueprints,
                    pipes=loaded_pipes,
                    dry_run_result=dry_run_results,
                    pending_signatures=build_pending_signatures(library.pipe_library.get_pipes_dict()),
                )

            else:
                assert mthds_file_path is not None
                blueprint = MthdsParser.make_pipelex_bundle_blueprint(bundle_path=mthds_file_path)
                loaded_blueprints = [blueprint]

                if mthds_file_path.resolve() not in library.loaded_mthds_paths:
                    # File not yet loaded - load it from the blueprint
                    loaded_pipes = library_manager.load_from_blueprints(library_id=library_id, blueprints=[blueprint])
                else:
                    # File already loaded - get existing pipes from library by their refs. A bundle's
                    # `[pipe.<code>]` keys are bare and belong to the bundle's own domain, so they are
                    # qualified here rather than searched for: the library is keyed by qualified ref.
                    pipe_codes = list(blueprint.pipe.keys()) if blueprint.pipe else []
                    loaded_pipes = [library.pipe_library.get_required_pipe(pipe_code=f"{blueprint.domain}.{code}") for code in pipe_codes]

                dry_run_results = await BundleValidator().validate_pipes(
                    pipes=_pipes_to_dry_run(loaded_pipes, dry_run_pipe_codes=dry_run_pipe_codes),
                    library_id=library_id,
                    allow_signatures=allow_signatures,
                )
                result = ValidateBundleResult(
                    blueprints=loaded_blueprints,
                    pipes=loaded_pipes,
                    dry_run_result=dry_run_results,
                    pending_signatures=build_pending_signatures(library.pipe_library.get_pipes_dict()),
                )
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


async def validate_bundles_from_directory(directory: Path, *, allow_signatures: bool = False) -> ValidateBundleResult:
    mthds_files = get_pipelex_mthds_files_from_dirs(dirs={directory})
    all_blueprints: list[PipelexBundleBlueprint] = []

    library_manager = get_library_manager()
    library_id, library = library_manager.open_library()
    success = False
    prev_library_id = get_current_library_id_or_none()
    try:
        set_current_library(library_id=library_id)
        with translate_to_validate_bundle_error():
            for mthds_file in mthds_files:
                blueprint = MthdsParser.make_pipelex_bundle_blueprint(bundle_path=mthds_file)
                all_blueprints.append(blueprint)

            loaded_pipes = library_manager.load_libraries(library_id=library_id, library_dirs=[Path(directory)])
            dry_run_results = await BundleValidator().validate_pipes(pipes=loaded_pipes, library_id=library_id, allow_signatures=allow_signatures)
            result = ValidateBundleResult(
                blueprints=all_blueprints,
                pipes=loaded_pipes,
                dry_run_result=dry_run_results,
                pending_signatures=build_pending_signatures(library.pipe_library.get_pipes_dict()),
            )
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
