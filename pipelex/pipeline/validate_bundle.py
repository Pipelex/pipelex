import ast
import asyncio
from collections.abc import Mapping
from contextlib import AbstractContextManager, nullcontext
from pathlib import Path
from typing import Sequence

from mthds.method_tree.models import MethodTree
from mthds.protocol.problem.registry import CoreCode
from pydantic import BaseModel

# TypedDict from typing_extensions, not typing: pydantic rejects typing.TypedDict as a model
# field on Python < 3.12, and ValidatedPipeEntry is a field of PipelexValidationReport.
from typing_extensions import TypedDict

from pipelex import log
from pipelex.base_exceptions import PipelexUnexpectedError
from pipelex.core.exceptions import PipelexBundleBlueprintValidationErrorData
from pipelex.core.method_trees.file_references import BundleFileOrigin
from pipelex.core.qualified_ref import QualifiedRef
from pipelex.interpreter_hub import (
    clear_current_library,
    get_current_library_id_or_none,
    get_library_manager,
    resolve_library_dirs,
    set_current_library,
)
from pipelex.libraries.bundle_resources import check_submitted_files
from pipelex.libraries.library_utils import get_pipelex_mthds_files_from_dirs
from pipelex.libraries.method_trees import list_local_method_tree
from pipelex.libraries.pipe.exceptions import EntryPipeNotFoundError
from pipelex.libraries.pipe.pipe_suggestions import close_pipe_refs, declared_pipe_refs
from pipelex.mthds_parsing.parser import MthdsParser
from pipelex.mthds_parsing.pipelex_bundle_blueprint import PipelexBundleBlueprint
from pipelex.pipe_machinery.pipe_abstract import PipeAbstract
from pipelex.pipeline.bundle_validator import BundleValidator, DryRunOutput, DryRunStatus
from pipelex.pipeline.exceptions import TreePythonSyntaxError, ValidateBundleError
from pipelex.pipeline.validate_bundle_translation import (
    reporting_host_library_faults,
    translate_to_validate_bundle_error,
    withholding_host_library_files,
)
from pipelex.system.caller_identity import CallerIdentity

PYTHON_SUFFIX = ".py"


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
    """Project a dry-run result map into the ``validated_pipes`` JSON list (agent CLI).

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


def _pipes_to_dry_run(loaded_pipes: list[PipeAbstract], *, dry_run_pipe_codes: list[str] | None) -> list[PipeAbstract]:
    """Select which loaded pipes to dry-run.

    Returns every loaded pipe when ``dry_run_pipe_codes`` is ``None`` (whole-bundle validation).
    Otherwise returns only the pipes whose bare ``code`` or qualified ``pipe_ref`` is requested —
    used by the ``--pipe`` path to validate a single implemented slice of a partially stubbed
    bundle without dry-running unrelated pipes. Filtering here, before ``BundleValidator.validate_pipes``,
    narrows the dry-run sweep to just the selected pipe (signatures are never an error either way — D-B).

    Raises:
        EntryPipeNotFoundError: when ``dry_run_pipe_codes`` names a pipe absent from the loaded
            bundle — so a typo'd ``--pipe`` argument fails loudly instead of passing vacuously. The
            selector is caller-supplied entry-shaped input, not a ref written inside a bundle, so it
            carries the INPUT domain (→ 422) rather than the undomained base class (→ 500). Every
            ``except PipeNotFoundError`` downstream still matches: it is a subclass.
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
        # The bundle-scoped wording stays the raise site's own, more precise here than the class's library-lookup message.
        loaded_refs = [pipe.pipe_ref for pipe in loaded_pipes]
        suggestions = list(dict.fromkeys(ref for code in sorted(missing) for ref in close_pipe_refs(name=code, pipe_refs=loaded_refs)))
        raise EntryPipeNotFoundError(msg).with_params(pipe=", ".join(sorted(missing)), suggestions=suggestions)
    return selected


async def validate_bundle(
    mthds_file_path: Path | None = None,
    *,
    mthds_contents: list[str] | None = None,
    mthds_sources: Sequence[str | None] | None = None,
    library_dirs: Sequence[Path] | None = None,
    allow_signatures: bool = False,
    dry_run_pipe_codes: list[str] | None = None,
    caller_identity: CallerIdentity | None = None,
    library_dirs_are_callers: bool = False,
    collect_dry_run_warnings: bool = False,
    submitted_files: Mapping[str, bytes] | None = None,
    method_dir: Path | None = None,
    methods_dirs: Sequence[Path] | None = None,
) -> ValidateBundleResult:
    """Load one bundle, or one method's tree, into a fresh library and dry-run its pipes.

    Exactly one of ``mthds_file_path``, ``mthds_contents`` and ``method_dir`` names what is validated.
    ``method_dir`` is the directory of a method's tree, the caller's own, such as the tree a host wrote out for a
    request: every bundle of the tree is loaded as a member of it and dry-run, every refusal is the caller's verdict and
    names the tree's files as the tree does, and ``methods_dirs``, laid out like ``.mthds/methods/``, hold the packages
    the caller ships with it, searched first for an address-based reference. No other library directory loads beside it.

    ``submitted_files`` are the files submitted with ``mthds_contents`` that their steps read, such as a
    ``PipeDocGen`` step's ``template_file``, keyed by canonical bundle-relative path (see
    ``canonical_submitted_files``). A file none of the submitted steps names is refused with a
    ``BundleResourceNotNamedError``, not a verdict. A bundle file reads the files of its method tree and takes none.

    ``caller_identity`` is who asked for the validation, when the host knows it; the dry-run
    sweep is attributed to that caller (see ``BundleValidator.validate_pipes``). ``None``
    inherits the caller already in scope, and with none the sweep belongs to nobody.

    ``library_dirs_are_callers`` says whose library directories are loaded beside submitted
    ``mthds_contents``, as it does on the run path (``acquire_library``). By default they are a
    host's, so the verdict names none of their files (``withholding_host_library_files``); a
    caller validating content against its own directories passes True and keeps every path. A
    bundle file is validated on the caller's own disk, among the caller's own directories, and
    keeps every path whatever this says.

    ``collect_dry_run_warnings`` is for a caller that puts what the dry runs find without failing in a
    verdict of its own, as the validate surfaces do (see ``BundleValidator.validate_pipes``); any other
    caller, a fix loop or a builder, leaves it ``False`` and the dry runs log what they find.
    """
    provided_params = sum(
        [
            mthds_contents is not None,
            mthds_file_path is not None,
            method_dir is not None,
        ]
    )
    if provided_params == 0:
        # Programmer error: a caller (the HTTP request layer, a builder op) must wire exactly one
        # input. It is not a content verdict the end user can fix → PipelexUnexpectedError (→ 500,
        # runtime.unexpected), matching the mthds_sources-mismatch guard below — never a
        # ValidateBundleError, which would 200/422 a host-wiring bug as if the bundle were invalid.
        msg = "One of mthds_contents, mthds_file_path or method_dir must be provided to validate_bundle"
        raise PipelexUnexpectedError(msg)
    if provided_params > 1:
        msg = "Only one of mthds_contents, mthds_file_path or method_dir can be provided to validate_bundle"
        raise PipelexUnexpectedError(msg)
    if method_dir is not None and library_dirs is not None:
        msg = "A method's tree validates alone: no library directory loads beside method_dir"
        raise PipelexUnexpectedError(msg)
    if methods_dirs is not None and method_dir is None:
        msg = "methods_dirs accompany method_dir, the method whose packages they hold"
        raise PipelexUnexpectedError(msg)
    if mthds_contents is not None and not mthds_contents:
        # An EMPTY list is not None, so it passes the provided-params check above — without this
        # guard it would yield a blueprint-less result that downstream consumers (the canonical
        # report's primary-blueprint selection) cannot represent.
        msg = "mthds_contents must not be empty: provide at least one MTHDS content to validate"
        raise ValidateBundleError(message=msg).with_error_code(CoreCode.REQUEST_INVALID)
    if mthds_sources is not None and (mthds_contents is None or len(mthds_sources) != len(mthds_contents)):
        # ``mthds_sources`` is a per-content source list (the host — e.g. an HTTP API —
        # threads each bundle's source onto the in-memory load path so its diagnostics carry a
        # real ``source``). It is never supplied by the end caller, so a missing-alongside /
        # length-mismatch is a host wiring bug, not bad user input: raise an internal error
        # (→ 500, runtime.unexpected) rather than ``ValidateBundleError`` (→ 422). Contrast the
        # empty-``mthds_contents`` guard above, which can legitimately reflect an end user
        # submitting no bundles and so stays the caller's input error.
        msg = "mthds_sources, when provided, must be a per-item source list matching mthds_contents in length"
        raise PipelexUnexpectedError(msg)

    if submitted_files and mthds_contents is None:
        msg = "submitted_files accompany mthds_contents: a bundle file reads the files of its method tree"
        raise PipelexUnexpectedError(msg)

    library_manager = get_library_manager()
    library_id, library = library_manager.open_library()
    success = False
    prev_library_id = get_current_library_id_or_none()
    try:
        set_current_library(library_id=library_id)

        if method_dir is not None:
            await asyncio.sleep(0)  # Yield to event loop (keeps function async-compatible)
            result = await _validate_method_dir(
                method_dir=method_dir,
                methods_dirs=methods_dirs,
                library_id=library_id,
                allow_signatures=allow_signatures,
                dry_run_pipe_codes=dry_run_pipe_codes,
                caller_identity=caller_identity,
                collect_dry_run_warnings=collect_dry_run_warnings,
            )
            success = True
            return result

        # Load libraries from resolved directories before loading the bundle
        effective_dirs, source_label = resolve_library_dirs(library_dirs)

        loaded_pipes: list[PipeAbstract] | None = None
        loaded_blueprints: list[PipelexBundleBlueprint] | None = None
        # Beside submitted content, a host's library directories are withheld from the verdict: their files are paths
        # on the host. The caller's own directories, and every directory of a bundle file, keep their paths.
        host_library_withholding: AbstractContextManager[None]
        # A host's library directories whose trees cannot be listed, or whose methods refuse to load, are the host's
        # fault, never the caller's verdict.
        host_library_tree_faults: AbstractContextManager[None]
        if mthds_contents is not None and not library_dirs_are_callers:
            host_library_withholding = withholding_host_library_files(
                library_dirs=effective_dirs,
                caller_sources=[source for source in mthds_sources or [] if source is not None],
                caller_contents=mthds_contents,
            )
            host_library_tree_faults = reporting_host_library_faults()
        else:
            host_library_withholding = nullcontext()
            host_library_tree_faults = nullcontext()
        await asyncio.sleep(0)  # Yield to event loop (keeps function async-compatible)
        with host_library_withholding, translate_to_validate_bundle_error():
            if effective_dirs:
                log.verbose(f"Loading libraries from {len(effective_dirs)} directory(ies) ({source_label}) for validation")
                with host_library_tree_faults:
                    library_manager.load_libraries(
                        library_id=library_id,
                        library_dirs=effective_dirs,
                    )
            else:
                log.verbose(f"No library directories to load ({source_label})")
            if mthds_contents is not None:
                content_sources: list[str | None] = list(mthds_sources) if mthds_sources is not None else [None] * len(mthds_contents)
                # Contents belong to no method tree: their steps read only the files submitted with them.
                loaded_blueprints = [
                    MthdsParser.make_pipelex_bundle_blueprint(
                        mthds_content=content, mthds_source=source, file_origin=BundleFileOrigin.SUBMITTED_FILES
                    )
                    for content, source in zip(mthds_contents, content_sources, strict=True)
                ]
                if submitted_files:
                    check_submitted_files(blueprints=loaded_blueprints, submitted_files=submitted_files)
                    library_manager.add_submitted_files(library_id=library_id, submitted_files=submitted_files)
                if not library_dirs_are_callers:
                    # A refusal the caller reads offers the pipes of the bundles it sent, never the host's.
                    library.pipe_library.set_caller_pipe_refs(pipe_refs=declared_pipe_refs(blueprints=loaded_blueprints))
                loaded_pipes = library_manager.load_from_blueprints(library_id=library_id, blueprints=loaded_blueprints)
                dry_run_results = await BundleValidator().validate_pipes(
                    pipes=_pipes_to_dry_run(loaded_pipes, dry_run_pipe_codes=dry_run_pipe_codes),
                    library_id=library_id,
                    allow_signatures=allow_signatures,
                    caller_identity=caller_identity,
                    # Submitted content beside a host's library directories: only its own pipes name their file,
                    # never a pipe of the host's directories, which would put a path on the host into the
                    # caller's verdict. Beside the caller's own directories, every failure names its file.
                    source_pipe_refs=None if library_dirs_are_callers else frozenset(pipe.pipe_ref for pipe in loaded_pipes),
                    collect_dry_run_warnings=collect_dry_run_warnings,
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
                    caller_identity=caller_identity,
                    # A file on the caller's own disk: every failure names its file, a sibling file of the
                    # same method included, since the library directories are the caller's own too.
                    source_pipe_refs=None,
                    collect_dry_run_warnings=collect_dry_run_warnings,
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


def _ensure_tree_python_parses(*, tree: MethodTree) -> None:
    """Refuse a method tree holding a Python file that does not parse, naming each such file by its tree path.

    Validation covers the whole tree, its Python included, by syntax alone: no module is imported, so a file no step
    calls is checked too, and a `PipeFunc`'s own module is then held to the static check of its function.

    Raises:
        ValidateBundleError: One item per Python file that is not UTF-8 text or does not parse, located on its line.
    """
    items: list[PipelexBundleBlueprintValidationErrorData] = []
    for tree_path in tree.tree_paths:
        if not tree_path.endswith(PYTHON_SUFFIX):
            continue
        try:
            source = tree.file_location(tree_path).read_bytes().decode("utf-8")
        except UnicodeDecodeError:
            items.append(
                _tree_python_item(tree_path=tree_path, finding="not UTF-8 text", message=f"The Python file '{tree_path}' is not UTF-8 text.")
            )
            continue
        try:
            ast.parse(source, filename=tree_path)
        except SyntaxError as exc:
            items.append(_tree_python_item(tree_path=tree_path, finding=f"{exc.msg} (line {exc.lineno})", line=exc.lineno, column=exc.offset))
        except ValueError as exc:
            # Python 3.11 refuses a source holding a NUL byte with a ValueError where later versions raise a SyntaxError.
            items.append(_tree_python_item(tree_path=tree_path, finding=str(exc)))
        except (RecursionError, MemoryError):
            # Nesting deep enough to exhaust the parser, which Python's own import refuses the same way.
            items.append(_tree_python_item(tree_path=tree_path, finding="it nests too deeply"))
    if items:
        message = " ".join(item.message for item in items)
        # Each item takes the code of the verdict's cause, `method.syntax`, with its own finding.
        first_finding = (items[0].params or {}).get("finding")
        raise ValidateBundleError(message=message, pipelex_bundle_blueprint_validation_errors=items) from TreePythonSyntaxError(message).with_params(
            finding=first_finding
        )


def _tree_python_item(
    *, tree_path: str, finding: str, message: str | None = None, line: int | None = None, column: int | None = None
) -> PipelexBundleBlueprintValidationErrorData:
    """The item of a Python file of a method's tree that does not parse, located on the file and, when known, its line.

    Its ``finding`` is what the parser found, the ``method.syntax`` parameter; its message says so, naming the file.
    """
    return PipelexBundleBlueprintValidationErrorData(
        source=tree_path,
        message=message or f"The Python file '{tree_path}' does not parse: {finding}.",
        line=line,
        column=column,
        params={"finding": finding},
    )


async def _validate_method_dir(
    *,
    method_dir: Path,
    methods_dirs: Sequence[Path] | None,
    library_id: str,
    allow_signatures: bool,
    dry_run_pipe_codes: list[str] | None,
    caller_identity: CallerIdentity | None,
    collect_dry_run_warnings: bool,
) -> ValidateBundleResult:
    """Load the tree of a caller's method into the open library and dry-run its pipes (see ``validate_bundle``)."""
    library_manager = get_library_manager()
    library = library_manager.get_library(library_id=library_id)
    with translate_to_validate_bundle_error():
        _ensure_tree_python_parses(tree=list_local_method_tree(handed_over=method_dir))
        loaded_pipes = library_manager.load_libraries(
            library_id=library_id,
            library_dirs=[method_dir],
            methods_dirs=list(methods_dirs) if methods_dirs is not None else None,
        )
        blueprints = library_manager.get_accumulated_blueprints(library_id)
        if not blueprints:
            msg = "The method holds no .mthds bundle, so it has nothing to validate."
            raise ValidateBundleError(message=msg)
        dry_run_results = await BundleValidator().validate_pipes(
            pipes=_pipes_to_dry_run(loaded_pipes, dry_run_pipe_codes=dry_run_pipe_codes),
            library_id=library_id,
            allow_signatures=allow_signatures,
            caller_identity=caller_identity,
            # The caller's own method: every failure names its file, by its path in the tree.
            source_pipe_refs=None,
            collect_dry_run_warnings=collect_dry_run_warnings,
        )
    return ValidateBundleResult(
        blueprints=blueprints,
        pipes=loaded_pipes,
        dry_run_result=dry_run_results,
        pending_signatures=build_pending_signatures(library.pipe_library.get_pipes_dict()),
    )


async def validate_bundles_from_directory(directory: Path, *, allow_signatures: bool = False) -> ValidateBundleResult:
    # A directory whose tree cannot be listed is the invalid verdict, as a bundle of it that does not load is.
    with translate_to_validate_bundle_error():
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
