import uuid
from collections.abc import Generator, Mapping
from contextlib import ExitStack, contextmanager
from graphlib import CycleError, TopologicalSorter
from pathlib import Path
from typing import TYPE_CHECKING, Any, ForwardRef, Literal, get_args, get_origin

from kajson.class_registry import ClassRegistry
from kajson.kajson_manager import KajsonManager
from mthds.method_tree.models import MethodTree, TreeLimits
from mthds.method_tree.tree_path import path_collisions, tree_path_violation
from mthds.package.dependency_resolver import ResolvedDependency, determine_exported_pipes, resolve_all_dependencies
from mthds.package.discovery import find_package_manifest
from mthds.package.exceptions import DependencyResolveError, ManifestError
from mthds.package.manifest.schema import MTHDS_STANDARD_VERSION, MethodsManifest
from mthds.protocol.problem.registry import CoreCode
from pydantic import BaseModel, PydanticUserError, ValidationError
from typing_extensions import override

from pipelex import log
from pipelex.base_exceptions import ErrorDomain, PipelexError, SecurityError, iter_cause_chain
from pipelex.cogt.exceptions import ModelChoiceNotFoundError
from pipelex.config import is_pipe_func_sandbox_hosted
from pipelex.core.bundle_resources.bundle_resource import canonical_submitted_files
from pipelex.core.bundle_resources.exceptions import BundleResourcePathError
from pipelex.core.concepts.concept_blueprint import ConceptBlueprint
from pipelex.core.concepts.concept_factory import ConceptFactory
from pipelex.core.concepts.helpers import make_qualified_structure_class_name
from pipelex.core.concepts.native.concept_native import NativeConceptCode
from pipelex.core.domains.domain_blueprint import DomainBlueprint
from pipelex.core.domains.domain_factory import DomainFactory
from pipelex.core.exceptions import PipelexBundleBlueprintValidationErrorData, PipesAndConceptValidationErrorData
from pipelex.core.method_trees.building_bundle import BuildingBundle, building_pipe_of
from pipelex.core.method_trees.method_file_store import LOCAL_METHOD_FILES, HeldFile
from pipelex.core.method_trees.tree_bundle import TreeBundle, TreeBundleRef
from pipelex.core.method_trees.tree_python import TREE_PYTHON_HOLD, sharing_module_name_checks
from pipelex.core.pipes.exceptions import PipeLoadRefusalError, PipeOperatorModelChoiceError, PipeValidationError
from pipelex.core.qualified_ref import QualifiedRef
from pipelex.core.stuffs.structured_content import StructuredContent
from pipelex.core.validation import report_validation_error
from pipelex.interpreter_hub import get_current_library, get_current_library_id_or_none, scoped_current_library
from pipelex.libraries.collision_messages import duplicate_ref_msg
from pipelex.libraries.concept.exceptions import ConceptLibraryError
from pipelex.libraries.concept_reference_validation import validate_concept_references_in_blueprints
from pipelex.libraries.crate_qualification import qualify_crate
from pipelex.libraries.exceptions import (
    LibraryError,
    LibraryLoadingError,
)
from pipelex.libraries.library import Library
from pipelex.libraries.library_crate import LibraryCrate
from pipelex.libraries.library_crate_factory import LibraryCrateFactory
from pipelex.libraries.library_factory import LibraryFactory
from pipelex.libraries.library_manager_abstract import LibraryManagerAbstract
from pipelex.libraries.method_requirements import ensure_method_requirements_met, ensure_package_requirements_met
from pipelex.libraries.method_trees import (
    LibraryBundleFile,
    LibraryTree,
    library_bundle_files_of,
    list_library_dir_trees,
    list_package_method_tree,
    listing_identity,
    local_tree_limits,
    submitted_tree_files,
    tree_bundle_of_lone_file,
    tree_bundles_of,
    tree_python_sources,
)
from pipelex.libraries.pipe.exceptions import PipeLibraryError
from pipelex.libraries.visibility_utils import check_visibility_for_blueprints, make_visibility_checker
from pipelex.libraries.written_trees import WRITTEN_METHOD_TREES
from pipelex.methods.address_dependencies import AddressDependencySources, unshipped_address_dependency_message
from pipelex.methods.exceptions import MethodDependencyFetchError, MethodDependencyNotShippedError, MethodFetchDisabledError
from pipelex.methods.fetch_on_miss import find_vendored_method, resolve_address_based_method
from pipelex.methods.structures_check import ensure_no_structured_content_in_library_sources
from pipelex.mthds_parsing.exceptions import MthdsParserError
from pipelex.mthds_parsing.handle_pipe_errors import categorize_pipe_validation_error
from pipelex.mthds_parsing.parser import MthdsParser
from pipelex.mthds_parsing.pipelex_bundle_blueprint import (
    ElaborationMetadata,
    LocatedPipeReference,
    PipeBlueprintUnion,
    PipelexBundleBlueprint,
    StepRole,
)
from pipelex.pipe_machinery.pipe_abstract import PipeAbstract
from pipelex.pipe_machinery.pipe_factory import PipeFactory
from pipelex.runtime_hub import get_class_registry
from pipelex.system.registries.class_registry_utils import ClassRegistryUtils
from pipelex.tools.log.error_fields import error_fields
from pipelex.tools.log.log_fields import USER_ACTION_FIELD
from pipelex.tools.misc.exceptions import SemVerError
from pipelex.tools.misc.semver import parse_constraint, parse_version, version_satisfies
from pipelex.validation_error_types import PipeValidationErrorType

if TYPE_CHECKING:
    from collections.abc import Iterable

    from pipelex.core.concepts.concept import Concept
    from pipelex.core.domains.domain import Domain

MTHDS_METHODS_DIRNAME = ".mthds/methods"


def find_methods_dirs_from_blueprints(blueprints: list[PipelexBundleBlueprint]) -> list[Path]:
    """Find .mthds/methods/ directories by walking up from blueprint source paths.

    When a bundle file is located outside the CWD (e.g. validating a
    pipelex-cookbook bundle from the pipelex repo), the standard discovery
    only checks CWD/.mthds/methods/ and ~/.mthds/methods/. This function
    walks up ancestor directories of each bundle source path to find
    additional .mthds/methods/ directories.

    Args:
        blueprints: The parsed bundle blueprints; only those read from a file on this host
            (``host_bundle_file``) are walked up from

    Returns:
        Deduplicated list of existing .mthds/methods/ directories found
    """
    result: list[Path] = []
    seen: set[Path] = set()
    for blueprint in blueprints:
        # Only from a file this host read the bundle from: a bundle parsed from a string carries a label at most, which
        # a caller chose, so walking up from it would search this host's directories wherever the caller pointed.
        if blueprint.host_bundle_file is None:
            continue
        current = blueprint.host_bundle_file.resolve().parent
        while True:
            candidate = current / MTHDS_METHODS_DIRNAME
            resolved_candidate = candidate.resolve()
            if resolved_candidate not in seen and candidate.is_dir():
                result.append(resolved_candidate)
                seen.add(resolved_candidate)
            parent = current.parent
            if parent == current:
                break
            current = parent
    return result


def _parse_dependency_bundle(*, mthds_path: Path, bundle_source: str, package_address: str) -> PipelexBundleBlueprint:
    """Parse one bundle of a dependency package under its caller-facing source, refusing the load when it does not parse.

    The bundle is parsed from its text under ``bundle_source`` rather than from its path, so the blueprint, every item
    a parse failure gives and every message the parser writes name the bundle by the package's address and its path
    inside the package: parsing from the path would put the host's path into a TOML error's message and into the
    blueprint's own messages. A file discovery has just listed that cannot be read is the host's fault and propagates.

    Args:
        mthds_path: The bundle's file on this host.
        bundle_source: The bundle's caller-facing name, ``<package_address>/<path inside the package>``.
        package_address: The package's address, which the refusal's summary names.

    Returns:
        The parsed blueprint, its ``source`` the caller-facing name.

    Raises:
        MthdsParserError: The bundle is not UTF-8 or does not parse; each item carries ``bundle_source`` as its source,
            and the summary names the bundle and the package.
    """
    try:
        mthds_content = mthds_path.read_text(encoding="utf-8")
    except UnicodeDecodeError as exc:
        msg = f"Bundle '{bundle_source}' of method package '{package_address}' is not valid UTF-8."
        raise (
            MthdsParserError(msg, validation_errors=[PipelexBundleBlueprintValidationErrorData(source=bundle_source, message=msg)])
            .with_error_code(CoreCode.METHOD_DEPENDENCY_INVALID)
            .with_params(package=package_address, finding=f"its bundle '{bundle_source}' is not UTF-8 text")
        ) from exc
    try:
        return MthdsParser.make_pipelex_bundle_blueprint(mthds_content=mthds_content, mthds_source=bundle_source)
    except MthdsParserError as exc:
        # Each item names the bundle in its text too: the verdict's summary is an item's message, and a caller reading
        # it must learn that the fault is in a package the bundle calls, not in the bundle itself.
        context = f"Bundle '{bundle_source}' of method package '{package_address}' does not parse"
        items = [item.model_copy(update={"source": bundle_source, "message": f"{context}: {item.message}"}) for item in exc.validation_errors]
        msg = f"{context}: {exc.message}"
        raise (
            MthdsParserError(msg, validation_errors=items or [PipelexBundleBlueprintValidationErrorData(source=bundle_source, message=msg)])
            .with_error_code(CoreCode.METHOD_DEPENDENCY_INVALID)
            .with_params(package=package_address, finding=f"its bundle '{bundle_source}' does not parse")
        ) from exc


def _public_dependency_pipe_refs(*, resolved_dep: ResolvedDependency, blueprints: list[PipelexBundleBlueprint]) -> set[str] | None:
    """The `domain.code` of every pipe a dependency makes public, or `None` when it declares no exports and all are public.

    A package's public pipes are the ones its manifest exports, read by domain so that exporting `a.x` does not
    also export a `b.x` of another domain, and the `main_pipe` of each of its bundles.
    """
    if resolved_dep.exported_pipe_codes is None:
        return None
    public_pipe_refs: set[str] = set()
    if resolved_dep.manifest is not None:
        for domain_path, domain_exports in resolved_dep.manifest.exports.items():
            public_pipe_refs.update(f"{domain_path}.{pipe_code}" for pipe_code in domain_exports.pipes)
    for blueprint in blueprints:
        if blueprint.main_pipe:
            public_pipe_refs.add(f"{blueprint.domain}.{blueprint.main_pipe}")
    return public_pipe_refs


def reachable_dependency_pipe_refs(
    *, public_pipe_refs: set[str], qualified_pipes: "Mapping[str, PipeBlueprintUnion]", package_alias: str
) -> set[str]:
    """The `domain.code` of every pipe of a dependency its public pipes reach through the package's own references.

    The pipes are the package's qualified blueprints, whose in-package refs carry `package_alias`. A public pipe's
    private helpers, a build-time elaboration's synthetic helpers among them, travel with it; a private pipe nothing
    public reaches is left out. A ref to another package, or to a pipe the package does not declare, is not followed:
    validation reports the latter. A ref written `alias->code`, with no domain, is followed as lookup resolves it, by code
    within the package: to the public pipes of that code when there are some among several, else to every pipe of it,
    lookup reporting the ambiguity when more than one remains.
    """
    reachable: set[str] = set()
    pending = [pipe_ref for pipe_ref in public_pipe_refs if pipe_ref in qualified_pipes]
    while pending:
        pipe_ref = pending.pop()
        if pipe_ref in reachable:
            continue
        reachable.add(pipe_ref)
        for dependency_ref in qualified_pipes[pipe_ref].pipe_dependencies:
            if not QualifiedRef.has_cross_package_prefix(dependency_ref):
                continue
            ref_alias, in_package_ref = QualifiedRef.split_cross_package_ref(dependency_ref)
            if ref_alias != package_alias:
                continue
            if "." in in_package_ref:
                if in_package_ref in qualified_pipes:
                    pending.append(in_package_ref)
            else:
                candidates = [candidate for candidate in qualified_pipes if candidate.rsplit(".", 1)[-1] == in_package_ref]
                # Lookup lets private pipes only break a tie (`PipeLibrary.get_optional_pipe`), so one public match is the one reached.
                public_candidates = [candidate for candidate in candidates if candidate in public_pipe_refs]
                pending.extend(public_candidates if len(candidates) > 1 and public_candidates else candidates)
    return reachable


def _dependency_entries_first(*, concepts_by_key: "Mapping[str, Concept]") -> list["Concept"]:
    """A library's concepts with its dependencies' aliased entries (`alias->domain.Code`) before its own.

    The structure-class rebuild lets a later concept win a class name two concepts share, so this order is what makes
    a main-package concept win over a dependency's of the same `domain.Code`, whichever batch loaded each.
    """
    dependency_entries = [concept for key, concept in concepts_by_key.items() if QualifiedRef.has_cross_package_prefix(key)]
    own_entries = [concept for key, concept in concepts_by_key.items() if not QualifiedRef.has_cross_package_prefix(key)]
    return [*dependency_entries, *own_entries]


def _forward_refs_missing_from(*, annotation: object, namespace: "Mapping[str, type]") -> list[str]:
    """The structure class names an annotation holds as forward references that the namespace lacks.

    The generator spells a field typed by a concept as a quoted name, `"domain__Code"`, or `"domain__Code | None"` for
    an optional one, alone or inside a `list[...]` or a `dict[...]`. A rebuild that fails leaves those names as they
    were written, a `ForwardRef` or a plain string, so a name is missing when the namespace has no entry for it.
    """
    if isinstance(annotation, ForwardRef):
        annotation = annotation.__forward_arg__
    if isinstance(annotation, str):
        names = [name.strip() for name in annotation.split("|")]
        return [name for name in names if name != "None" and name not in namespace]
    if get_origin(annotation) is Literal:
        return []
    return [name for arg in get_args(annotation) for name in _forward_refs_missing_from(annotation=arg, namespace=namespace)]


def _authored_model_field(*, step_role: StepRole) -> str:
    """The field of the authored ``preliminary_text`` PipeLLM whose model a synthetic helper was given."""
    match step_role:
        case StepRole.DRAFT_TEXT:
            return "model"
        case StepRole.STRUCTURE:
            return "model_to_structure"


def _relocate_on_authored_pipe(
    *, model_choice_error: PipeOperatorModelChoiceError, elaboration: ElaborationMetadata, domain_code: str
) -> PipeOperatorModelChoiceError:
    """Move an unknown model refused on a synthetic helper onto the authored pipe and field it came from."""
    cause = model_choice_error.__cause__
    if not isinstance(cause, ModelChoiceNotFoundError):
        return model_choice_error
    relocated = PipeOperatorModelChoiceError.make_from_model_choice_not_found(
        model_choice_error=cause,
        pipe_type="PipeLLM",
        pipe_code=elaboration.parent_pipe_code,
        domain_code=domain_code,
        field_name=_authored_model_field(step_role=elaboration.step_role),
    )
    relocated.source = model_choice_error.source
    return relocated


@contextmanager
def _locating_pipe_build_refusals(
    *, pipe_code: str, domain_code: str, source: str | None, elaboration: ElaborationMetadata | None
) -> Generator[None, None, None]:
    """Let a refusal raised while building one pipe leave the load loop located on that pipe and its file.

    The loop is the one place that holds the pipe's code, its domain and the file it is declared in at
    the moment a build fails: pipes carry no source, and the pipe-source map is filled only after a
    pipe is built. So the location is attached here, and bundle validation reads it off the refusal:

    - An unknown model is already located on its pipe and field by the operator
      (``PipeOperatorModelChoiceError``); the loop adds the file and lets it go on under its own class,
      which the validate and run paths turn into its ``unknown_model`` verdict item and the build
      surfaces render with their dedicated panel.
    - Any other refusal of the caller's input (an ``input``-domained ``PipelexError``) is raised again
      as a ``PipeLoadRefusalError`` naming the pipe and the file, ``from`` the original.
    - Everything else leaves untouched: a configuration or runtime fault keeps its identity and stays a
      no-verdict fault, a security refusal is never absorbed into a verdict, a library error keeps the
      structured items its own arm forwards, and pydantic's ``ValidationError`` and a
      ``PipeValidationError``, whose own arm locates it, keep their categorizers.

    A synthetic helper the bundle elaborator generated (the ``<code>__draft_text`` and ``<code>__structure``
    pipes of a ``preliminary_text`` PipeLLM) is not in the author's file, so its refusal is located on
    the authored pipe instead, and an unknown model on the authored field the helper's model came from.
    """
    try:
        yield
    except PipeOperatorModelChoiceError as model_choice_error:
        if model_choice_error.source is None:
            model_choice_error.source = source
        if elaboration is None:
            raise
        relocated = _relocate_on_authored_pipe(model_choice_error=model_choice_error, elaboration=elaboration, domain_code=domain_code)
        if relocated is model_choice_error:
            raise
        raise relocated from model_choice_error
    except (SecurityError, LibraryError, PipeValidationError):
        raise
    except PipelexError as refusal:
        if not ErrorDomain.from_problem_domain(refusal.resolve_domain()).is_input:
            raise
        authored_pipe_code = elaboration.parent_pipe_code if elaboration is not None else pipe_code
        raise PipeLoadRefusalError.make_from_refusal(
            refusal=refusal, pipe_code=authored_pipe_code, domain_code=domain_code, source=source
        ) from refusal


def _python_sources_by_tree(*, library_trees: list[LibraryTree], bundle_files: list[LibraryBundleFile]) -> dict[Path, dict[str, str]]:
    """The Python sources of every tree a load lists, each file keyed by its path from its library directory, grouped by tree root.

    The library directories' trees come first, nested ones included, then the tree of each bundle file named alone; a
    tree two of them list is read once.
    """
    trees: dict[tuple[str, str, bool], tuple[MethodTree, Path | None]] = {}
    for library_tree in library_trees:
        trees.setdefault(listing_identity(tree=library_tree.tree), (library_tree.tree, library_tree.library_dir))
    for bundle_file in bundle_files:
        trees.setdefault(listing_identity(tree=bundle_file.tree_bundle.tree), (bundle_file.tree_bundle.tree, None))
    sources_by_tree: dict[Path, dict[str, str]] = {}
    for tree, library_dir in trees.values():
        if tree.directory is None:
            continue
        sources_by_tree.setdefault(tree.directory, {}).update(tree_python_sources(tree=tree, library_dir=library_dir))
    return sources_by_tree


class LibraryManager(LibraryManagerAbstract):
    def __init__(self):
        # UNTITLED library is the fallback library for all others
        self._libraries: dict[str, Library] = {}
        self._pipe_source_maps: dict[str, dict[str, str]] = {}  # library_id -> pipe_ref -> source identifier
        self._blueprints: dict[str, list[PipelexBundleBlueprint]] = {}  # library_id -> accumulated blueprints
        self._crate_cache: dict[str, LibraryCrate] = {}  # library_id -> cached crate from get_crate()
        self._loaded_fingerprints: dict[str, set[str]] = {}  # library_id -> set of loaded crate fingerprints
        # library_id -> path -> file. The files submitted beside the bundles a library parses from content strings: the
        # files of its library directories whose own tree holds no bundle, and the files a caller submitted with the
        # contents. Those bundles sit at the root of the tree they make, which the library holds in the local method
        # file store, so their steps resolve a file they name in it and a run reads it by the tree's digest.
        self._submitted_files: dict[str, dict[str, HeldFile]] = {}
        # library_id -> the tree of its submitted files, as last held; dropped when a file joins.
        self._submitted_trees: dict[str, MethodTree] = {}
        # library_id -> the files its library directories submit, joined only when a bundle parsed from a content
        # string loads: a library that loads none never has two directories' files judged as one tree.
        self._library_dir_submissions: dict[str, list[dict[str, HeldFile]]] = {}

    ############################################################
    # Manager lifecycle
    ############################################################
    def generate_library_id(self) -> str:
        return str(uuid.uuid4())

    @override
    def setup(self) -> None:
        pass

    def _pop_and_teardown_library(self, library_id: str) -> bool:
        """Atomically forget a library entry, then tear it down.

        The entry is popped BEFORE ``library.teardown()`` runs and the associated maps are
        cleared in a ``finally``, so the manager forgets the library even if its teardown
        raises — a kept entry would turn ``open_fresh_library`` into a deterministic
        re-raise on every rerun of that library id on this worker (permanent worker-local
        poison). The pop also makes the operation tolerant of a concurrent teardown of the
        same id from another workflow thread: whichever caller pops the entry tears it
        down, the other sees a clean miss.

        Returns:
            True when an entry existed and was removed, False when there was none.
        """
        library = self._libraries.pop(library_id, None)
        if library is None:
            return False
        try:
            library.teardown()
        finally:
            self._pipe_source_maps.pop(library_id, None)
            self._blueprints.pop(library_id, None)
            self._crate_cache.pop(library_id, None)
            self._loaded_fingerprints.pop(library_id, None)
            self._submitted_files.pop(library_id, None)
            self._submitted_trees.pop(library_id, None)
            self._library_dir_submissions.pop(library_id, None)
            # The library's runs are over: its hold on a method tree's Python, if a PipeFunc step took one, is released,
            # and so are the trees it held for its runs to read.
            TREE_PYTHON_HOLD.release(holder=library_id)
            LOCAL_METHOD_FILES.release(holder=library_id)
        return True

    @override
    def teardown(self, library_id: str | None = None) -> None:
        if library_id:
            if not self._pop_and_teardown_library(library_id=library_id):
                msg = f"Trying to teardown a library that does not exist: '{library_id}'"
                raise LibraryError(msg)
            return

        # Same forget-even-on-raise contract as the single-id branch, extended to the loop:
        # all bookkeeping is dropped upfront, and ExitStack guarantees EVERY library's own
        # teardown is attempted even when one of them raises — the first failure propagates
        # only after the rest have run, so neither a kept entry nor a skipped sibling
        # teardown can result from a raising library.
        libraries = list(self._libraries.values())
        self._libraries = {}
        self._pipe_source_maps = {}
        self._blueprints = {}
        self._crate_cache = {}
        self._loaded_fingerprints = {}
        self._submitted_files = {}
        self._submitted_trees = {}
        self._library_dir_submissions = {}
        TREE_PYTHON_HOLD.release_all()
        LOCAL_METHOD_FILES.release_all()
        with ExitStack() as teardown_stack:
            for library in libraries:
                teardown_stack.callback(library.teardown)

    @override
    def reset(self) -> None:
        self.teardown()
        self.setup()

    @override
    def open_library(self, library_id: str | None = None) -> tuple[str, Library]:
        if not library_id:
            library_id = self.generate_library_id()

        if library_id in self._libraries:
            the_library = self._libraries[library_id]
        else:
            the_library = LibraryFactory.make_empty()
            the_library.set_class_registry(self._make_library_class_registry())
            self._libraries[library_id] = the_library

        return library_id, the_library

    @classmethod
    def _make_library_class_registry(cls) -> ClassRegistry:
        """Build the per-library ClassRegistry every manager-opened Library carries.

        Concept materialization registers dynamically generated structure classes under a
        *name* key (``domain__Concept``), and kajson's ``register_class`` overwrites an existing
        key unconditionally. A library that carried no registry of its own resolved through to the
        process-global registry, which made two libraries loading the same concept ref share one
        slot: whichever loaded last owned the class, and neither teardown removed it. Two
        contaminations followed — a later load reusing an earlier one's class (``ConceptFactory``
        reuses a registered class for a basic concept), and two concurrent loads overwriting each
        other at any ``await`` between generation and use. Both crossed request boundaries wherever
        one process serves several bundles, and the generated classes are what
        ``pipe_io_contracts`` renders schemas from.

        Giving the registry to the library at open time makes the isolation structural rather than
        opt-in: the classes a load generates live and die with the library that asked for them, and
        the process-global registry keeps only what boot put there.

        The seed is a snapshot of the process-global registry — the boot-time core and test models,
        plus anything registered outside any library — taken from ``KajsonManager`` rather than from
        the ambient ``get_class_registry()``: opening a library while another one is current must not
        copy that library's dynamic classes into the new one. Being a snapshot, it is taken at open
        time: a class registered globally *after* a library is open is not visible to that library.
        Nothing in-tree does that — boot registers before any library exists, and every load-time
        registration runs under the library it is loading into — so the ordering that would make it
        matter is a host registering classes mid-flight, which is a case for registering them at
        startup instead.
        """
        library_class_registry = ClassRegistry()
        # The global registry really is empty before boot registers anything; kajson's
        # register_classes_dict is a no-op on an empty dict, so a library opened there comes out
        # carrying its own empty registry rather than failing to open.
        library_class_registry.register_classes_dict(KajsonManager.get_class_registry().get_classes_dict())
        return library_class_registry

    @override
    def open_fresh_library(self, library_id: str) -> Library:
        try:
            removed_existing = self._pop_and_teardown_library(library_id=library_id)
        except Exception as stale_teardown_exc:  # ruff: ignore[blind-except]
            # Best-effort: the stale library's teardown runs over arbitrary half-built state
            # from an interrupted execution — its failure must never fail the fresh open
            # (worker-local leak state deciding setup success would be the M1 class again).
            # _pop_and_teardown_library forgets the entry pop-first, so the id is free either way.
            log.warning(
                "The teardown of a stale library failed, and a fresh library was made",
                fields={"library_id": library_id, **error_fields(exc=stale_teardown_exc)},
            )
        else:
            if removed_existing:
                log.warning("A library left over by an interrupted execution was torn down", fields={"library_id": library_id})
        _library_id, the_library = self.open_library(library_id=library_id)
        return the_library

    ############################################################
    # Public library accessors
    ############################################################

    @override
    def get_library_class_registry(self, library_id: str) -> ClassRegistry | None:
        """Get the ClassRegistry associated with a library, if any."""
        library = self._libraries.get(library_id)
        if library is not None:
            return library.get_class_registry()
        return None

    @override
    def get_library(self, library_id: str) -> Library:
        if library_id not in self._libraries:
            msg = f"Library '{library_id}' does not exist"
            raise LibraryError(msg)
        return self._libraries[library_id]

    @override
    def get_current_library(self) -> Library:
        library_id = get_current_library()
        if library_id not in self._libraries:
            msg = f"No current library set. Library '{library_id}' does not exist"
            raise LibraryError(msg)
        return self._libraries[library_id]

    @override
    def get_pipe_source(self, pipe_code: str) -> str | None:
        """Get the source identifier for a pipe.

        Args:
            pipe_code: The pipe code or pipe_ref (domain.code) to look up.

        Returns:
            The source the pipe was loaded from — a filesystem path or a logical URI
            (e.g. ``api://bundle-0.mthds``), preserved verbatim — or None if unknown.
        """
        library_id = get_current_library_id_or_none()
        if library_id is None:
            return None
        source_map = self._pipe_source_maps.get(library_id, {})

        # Direct lookup by pipe_ref
        result = source_map.get(pipe_code)
        if result is not None:
            return result
        # Bare code fallback: search for a key ending with .pipe_code
        if "." not in pipe_code:
            suffix = f".{pipe_code}"
            matches = [path for key, path in source_map.items() if key.endswith(suffix)]
            if len(matches) == 1:
                return matches[0]
        return None

    @override
    def get_accumulated_blueprints(self, library_id: str) -> list[PipelexBundleBlueprint]:
        return list(self._blueprints.get(library_id, []))

    @override
    def get_crate(self, library_id: str) -> LibraryCrate | None:
        cached = self._crate_cache.get(library_id)
        if cached is not None:
            return cached
        accumulated = self._blueprints.get(library_id)
        if not accumulated:
            return None
        # The crate names each tree by its digest and reads no file, so it builds after the directories the library was
        # read from are gone.
        crate = LibraryCrateFactory.make_from_blueprints(blueprints=accumulated)
        self._crate_cache[library_id] = crate
        return crate

    @override
    def add_submitted_files(self, *, library_id: str, submitted_files: "Mapping[str, bytes]") -> None:
        if not submitted_files:
            return
        if library_id not in self._libraries:
            msg = f"Trying to add submitted files to a library that does not exist: '{library_id}'"
            raise LibraryError(msg)
        canonical_files = canonical_submitted_files(files=submitted_files)
        self._join_submitted_files(
            library_id=library_id,
            files={path: HeldFile.of_bytes(data=data) for path, data in canonical_files.items()},
        )

    def _join_submitted_files(self, *, library_id: str, files: "Mapping[str, HeldFile]") -> None:
        """Join files to the ones submitted beside the library's content strings, keyed by their path from the root.

        A file already joined under the same path is kept when the new one has the same bytes. Nothing is joined when
        any file is refused, so a refusal leaves the files already joined as they were.

        Raises:
            BundleResourcePathError: A path is not a tree path, collides with another once case-folded or as a
                directory, or names a file already joined with different bytes, so the files could not make one tree.
                The message names the files by their tree paths alone, never by a host path.
        """
        if not files:
            return
        self._submitted_files[library_id] = self._joined_submitted_files(held=self._submitted_files.get(library_id, {}), files=files)
        self._submitted_trees.pop(library_id, None)
        # The cached crate was built before them.
        self._crate_cache.pop(library_id, None)

    @staticmethod
    def _joined_submitted_files(*, held: "Mapping[str, HeldFile]", files: "Mapping[str, HeldFile]") -> dict[str, HeldFile]:
        """`held` with `files` joined to it, as a new mapping, `held` itself left untouched.

        Raises:
            BundleResourcePathError: The files could not make one tree with the ones held (`_join_submitted_files`).
        """
        joined = dict(held)
        for path, held_file in files.items():
            violation = tree_path_violation(path)
            if violation is not None:
                msg = f"The file '{path}' submitted beside the method cannot be a file of its tree: {violation}."
                raise BundleResourcePathError(msg)
            already_held = joined.get(path)
            if already_held is not None and already_held.sha256 != held_file.sha256:
                msg = (
                    f"Two different files were submitted under the same path '{path}' for one library. The files submitted "
                    "beside a method's content strings, from its library directories and with its request, make one tree, "
                    "so each path names one file: give them distinct paths."
                )
                raise BundleResourcePathError(msg).with_error_code(CoreCode.REQUEST_INVALID).with_params(field="resources")
            joined[path] = held_file
        collisions = path_collisions(joined)
        if collisions:
            listed = ", ".join(f"'{collision}'" for collision in collisions)
            msg = f"The files submitted beside the method cannot make one tree: their paths collide at {listed}."
            raise BundleResourcePathError(msg).with_error_code(CoreCode.REQUEST_INVALID).with_params(field="resources")
        return joined

    def _submitted_tree(self, *, library_id: str) -> MethodTree | None:
        """The tree of the files submitted beside the library's content strings, held for its runs, or None when there are none.

        The files the library's directories submitted are joined all together or not at all: a refusal leaves every one
        of them pending, so the library's next run is refused again rather than run without them.

        Raises:
            BundleResourcePathError: The files cannot make one tree, such as two of them, from two library directories
                or from one and the request, sharing a path with different bytes.
        """
        pending = self._library_dir_submissions.get(library_id)
        if pending:
            joined: Mapping[str, HeldFile] = self._submitted_files.get(library_id, {})
            for library_dir_files in pending:
                joined = self._joined_submitted_files(held=joined, files=library_dir_files)
            self._submitted_files[library_id] = dict(joined)
            self._submitted_trees.pop(library_id, None)
            self._crate_cache.pop(library_id, None)
            del self._library_dir_submissions[library_id]
        tree = self._submitted_trees.get(library_id)
        if tree is not None:
            return tree
        files = self._submitted_files.get(library_id)
        if not files:
            return None
        tree = LOCAL_METHOD_FILES.hold_files(holder=library_id, files=files)
        self._submitted_trees[library_id] = tree
        return tree

    ############################################################
    # Private methods
    ############################################################

    @override
    def load_libraries(
        self,
        *,
        library_id: str,
        library_dirs: list[Path] | None = None,
        library_file_paths: list[Path] | None = None,
        methods_dirs: list[Path] | None = None,
        address_dependency_sources: AddressDependencySources = AddressDependencySources.ANYWHERE,
    ) -> list[PipeAbstract]:
        # `methods_dirs` are laid out like `.mthds/methods/` and hold the packages a caller ships with the method these
        # directories hold, searched first for an address-based reference of their bundles and never written.
        # `address_dependency_sources` says whether a reference they do not answer may be looked up on this host and
        # fetched (`ANYWHERE`), or is refused (`SHIPPED`, a static resolution of a caller's method).
        # Ensure libraries exist for this library_id
        if library_id not in self._libraries:
            msg = f"Trying to load a library that does not exist: '{library_id}'"
            raise LibraryError(msg)

        # Bind the target library as current for the whole load: class registration and the
        # blueprint loads beneath resolve through the ambient current library, so a load into
        # a non-current library must not read the caller's binding.
        with scoped_current_library(library_id=library_id):
            if not library_dirs:
                library_dirs = []

            all_dirs: list[Path] = []
            all_dirs.extend(library_dirs)
            # Every bundle is read as a member of its method tree: each library directory's tree and the trees nested
            # in it, then the tree of each file named alone. A file the membership rule keeps out is never read.
            # This machine's limits are read once for the whole load.
            tree_limits = local_tree_limits()
            library_trees = list_library_dir_trees(library_dirs=library_dirs, limits=tree_limits)
            all_bundle_files: list[LibraryBundleFile] = library_bundle_files_of(library_trees=library_trees)
            for library_file_path in library_file_paths or []:
                all_bundle_files.append(
                    LibraryBundleFile(
                        tree_bundle=tree_bundle_of_lone_file(bundle_file=library_file_path, limits=tree_limits),
                        path=library_file_path,
                    )
                )

            # A method declaring Python packages in its requirements.txt is refused here when the environment its
            # PipeFunc steps run in does not meet them: before any of its Python is imported or captured, and before
            # any of its pipes is built. Every listed tree counts, one holding no bundle included, such as the Python a
            # server received beside a method's bundles. A refusal may name host paths: these are the caller's own
            # directories, or the host's, whose refusal `reporting_host_library_tree_faults` withholds as its own fault.
            ensure_method_requirements_met(
                trees=[
                    *(library_tree.tree for library_tree in library_trees),
                    *(bundle_file.tree_bundle.tree for bundle_file in all_bundle_files),
                ],
                names_host_paths=True,
            )

            # A library directory whose own tree holds no bundle, such as the directory a server writes a request's
            # files into, submits its files beside the bundles parsed from content strings, which sit at the root of
            # the tree they make: nothing is read, each file being held by the hash its listing recorded.
            for library_tree in library_trees:
                library_dir_files = submitted_tree_files(library_tree=library_tree)
                if library_dir_files:
                    self._library_dir_submissions.setdefault(library_id, []).append(library_dir_files)
                    self._crate_cache.pop(library_id, None)

            # Each file once, as the member of the first tree that holds it.
            seen_locations: set[Path] = set()
            bundle_files: list[LibraryBundleFile] = []
            for bundle_file in all_bundle_files:
                location = bundle_file.tree_bundle.location
                if location not in seen_locations:
                    bundle_files.append(bundle_file)
                    seen_locations.add(location)

            # Import modules and register in global registries
            # Import from user directories
            if is_pipe_func_sandbox_hosted():
                # Sandbox-hosted mode imports no Python from a library directory, whatever its origin (an
                # inline bundle, a stored method, a host directory): importing a file runs its module-level
                # code in this process. A structure class cannot travel to a sandbox: it would have to be
                # imported here to back a concept, so the load is refused, naming each file and class, before
                # any file is kept. Every tree the load lists is scanned, a package or repository nested in a
                # library directory included. The refusal is a static scan, which a dynamically built class
                # escapes; such a file then travels as source and still never executes here.
                ensure_no_structured_content_in_library_sources(
                    sources_by_dir=_python_sources_by_tree(library_trees=library_trees, bundle_files=all_bundle_files),
                )
            else:
                for library_dir in all_dirs:
                    # Only import files that contain StructuredContent subclasses (uses AST pre-check), so
                    # concepts declared as `structure = "ClassName"` resolve that class from the registry.
                    # A PipeFunc's function is not imported here: its step imports it by its import path when
                    # it first runs.
                    ClassRegistryUtils.import_modules_in_folder(
                        folder_path=library_dir,
                        base_class_names=[StructuredContent.__name__],
                    )

            # Auto-discover and register all StructuredContent classes from sys.modules
            num_registered = ClassRegistryUtils.auto_register_all_subclasses(
                base_class=StructuredContent,
            )
            log.verbose("Auto-registered the StructuredContent classes of the loaded modules", fields={"class_count": num_registered})

            # Load MTHDS files into the specific library
            log.verbose(
                "Loading the MTHDS files into the library",
                fields={"library_id": library_id, "mthds_paths": [str(bundle_file.path) for bundle_file in bundle_files]},
            )
            return self._load_mthds_files_into_library(
                library_id=library_id,
                bundle_files=bundle_files,
                methods_dirs=methods_dirs,
                address_dependency_sources=address_dependency_sources,
            )

    @override
    def is_crate_loaded(self, *, library_id: str, fingerprint: str) -> bool:
        """Whether a crate with this fingerprint was already loaded into this library.

        Backed by the same per-library fingerprint bookkeeping that makes load_from_crate
        idempotent, so a True answer means the library's ClassRegistry already holds the
        crate's dynamic classes. Callers can use this to hydrate within an existing scope
        instead of opening a fresh one — preserving dynamic-class identity with instances
        the scope already produced.
        """
        return fingerprint in self._loaded_fingerprints.get(library_id, set())

    @override
    def load_from_crate(
        self,
        *,
        library_id: str,
        crate: LibraryCrate,
        is_crate_prevalidated: bool = False,
        written_pipe_trees: "Mapping[str, MethodTree] | None" = None,
    ) -> list[PipeAbstract]:
        """Load a LibraryCrate into a live Library, reading no file but, for its validation, files of trees this process holds.

        Fingerprint idempotency: if a crate with the same fingerprint was already loaded
        into this library_id, the load is skipped and an empty list is returned.

        Note: This method does NOT resolve cross-package address-based dependencies.
        Callers must handle dependency loading before calling this method (e.g. via
        _load_address_based_dependencies). The load_from_blueprints method does this
        automatically before delegating to the same load.

        A crate carries no dependency packages, so a crate loaded here, typically one transported to a worker
        or a sandbox, cannot tell a structure field naming a dependency's concept, which the transport left
        behind, from a field naming nothing. Its structure classes are rebuilt against what the library holds,
        and one still incomplete is left to fail at first use rather than refusing the load: the refusal
        belongs to load_from_blueprints, the load that resolves the bundle's dependencies, and the library a
        crate comes from went through it.

        Args:
            library_id: The library to load into
            crate: The LibraryCrate containing qualified blueprints, domain metadata, and source info
            is_crate_prevalidated: Skip the library validation that ends the load. Precondition: the crate
                was built from a library that this same pipelex version loaded and validated — the runner's
                crate, handed to the worker that executes it. Library validation is a pure check (it writes
                nothing a run later reads), so skipping it changes no behaviour, only the cost of reaching a
                verdict already reached. Everything else still happens: fingerprint idempotency, domain and
                concept loading with class registration, the resolution of the structure classes' references
                to one another, the concept-cycle check, pipe construction with each pipe's static validation,
                and source tracking. Leave it False for any crate whose library was not validated by this
                pipelex version.
            written_pipe_trees: The trees this process wrote out for a step to run in, by that step's pipe ref, such as
                the tree of a `PipeFunc` call written for its function to import. That step is built as a member of the
                written tree, which holds none of its tree's bundles; no other step is, a sibling of the same tree
                included.

        Every other step is built as a member of its tree when the load validates the crate and a library of this
        process holds the tree under the digest the crate names, so its checks read the files they read where the
        crate was assembled, such as a `PipeDocGen` step's HTML template file, and reach the same verdict. Otherwise
        it names its tree by digest alone, resolves a file it names lexically, and reads nothing: a load that skips
        validation, such as one inside a workflow, never reads a file.

        Returns:
            List of all pipes that were loaded, or empty list if already loaded
        """
        held_trees: dict[str, MethodTree] = {}
        if not is_crate_prevalidated:
            for tree_digest in crate.tree_digests():
                held_tree = LOCAL_METHOD_FILES.held_tree(tree_digest=tree_digest)
                if held_tree is not None:
                    held_trees[tree_digest] = held_tree
        return self._load_crate(
            library_id=library_id,
            crate=crate,
            is_crate_prevalidated=is_crate_prevalidated,
            refuses_unresolved_structures=False,
            live_trees=held_trees,
            written_pipe_trees=written_pipe_trees or {},
        )

    def _load_crate(
        self,
        *,
        library_id: str,
        crate: LibraryCrate,
        is_crate_prevalidated: bool,
        refuses_unresolved_structures: bool,
        live_trees: "Mapping[str, MethodTree]",
        written_pipe_trees: "Mapping[str, MethodTree] | None" = None,
    ) -> list[PipeAbstract]:
        """The load behind load_from_crate and load_from_blueprints.

        Args:
            library_id: The library to load into
            crate: The LibraryCrate to load
            is_crate_prevalidated: As load_from_crate describes it
            refuses_unresolved_structures: Whether a structure class still incomplete once the concepts are loaded
                refuses the load. True only where the load resolved the bundle's dependencies first, so that a
                reference which resolves to nothing is the bundle's own fault.
            live_trees: The trees this process holds, by digest: a pipe whose bundle's tree is one of them is built as a
                member of it, and every other as a member of a tree the crate names by digest alone.
            written_pipe_trees: As load_from_crate describes it: a step built in a tree this process wrote out for it,
                which wins over its tree in `live_trees`.
        """
        # Bind the target library as current for the whole load: PipeFactory and the concept
        # factories resolve concepts and the class registry through the ambient current library,
        # so a load into a non-current library must not read the caller's binding.
        with scoped_current_library(library_id=library_id), sharing_module_name_checks():
            # Cache the crate for a DIRECT crate-load (the transported-crate path used by the Temporal
            # workflow, which never populates _blueprints). This lets get_crate() hand the crate to the
            # sandbox executor. The blueprint-derived path (load_libraries -> load_from_blueprints) leaves
            # _blueprints populated and rebuilds from it instead, so it must NOT be shadowed by a cached
            # crate here.
            if library_id not in self._blueprints:
                self._crate_cache[library_id] = crate

            # Fingerprint idempotency: skip if this crate was already loaded into this library
            fingerprint = crate.fingerprint
            loaded_set = self._loaded_fingerprints.setdefault(library_id, set())
            if fingerprint in loaded_set:
                log.verbose("Skipped a crate already loaded into the library", fields={"library_id": library_id, "crate_fingerprint": fingerprint})
                return []
            library = self.get_library(library_id=library_id)

            # Load domains from crate metadata
            all_domains: list[Domain] = []
            for domain_blueprint in crate.domains.values():
                domain = DomainFactory.make_from_blueprint(blueprint=domain_blueprint)
                all_domains.append(domain)
            library.domain_library.add_domains(domains=all_domains)

            # Load concepts in topological order
            all_concepts = self._load_concepts_from_crate(crate.concepts)
            library.concept_library.add_concepts(concepts=all_concepts)

            # A main-package concept's forward references may name any concept the library holds: this batch's,
            # an earlier batch's, or a loaded dependency's aliased entry.
            self._run_concept_stage(
                loaded_concepts=all_concepts,
                visible_concepts=_dependency_entries_first(concepts_by_key=library.concept_library.root),
                concept_sources=crate.source_map,
                refuses_unresolved_structures=refuses_unresolved_structures,
            )

            # Precompute domain -> concept local codes mapping. VESTIGIAL on this path — see the note
            # on the qualification pass below: every io ref reaching PipeFactory is dotted, and the
            # factory only consults this parameter for dot-free refs. Kept until the PipeFactory
            # signature change that removes it (deferred with the concept-side work).
            # Cross-package aliased entries ('alias->...') are skipped — they resolve through the
            # dependency resolver, not by bare code, and would not parse as a concept ref.
            domain_concept_codes: dict[str, list[str]] = {}
            for concept_ref in library.concept_library.root:
                if QualifiedRef.has_cross_package_prefix(concept_ref):
                    continue
                parsed_concept = QualifiedRef.parse_concept_ref(raw=concept_ref)
                if parsed_concept.domain_path is not None:
                    domain_concept_codes.setdefault(parsed_concept.domain_path, []).append(parsed_concept.local_code)

            # Qualify in-body refs before constructing pipes, so a built pipe's sub-pipe refs are the
            # same qualified refs the normalizer would produce — one rule, stated once, read by both.
            #
            # Note what this does to `concept_codes_from_the_same_domain` below: the pass also rewrites
            # each pipe's inputs/output into `domain.Code` form, and PipeFactory only runs its
            # declared-in-this-domain check for refs with NO dot — so on this path that parameter is
            # now never consulted. Nothing is lost: an undeclared same-domain concept is still caught,
            # earlier, by `validate_concept_references_in_blueprints`, which runs on the blueprints
            # before this. The parameter is vestigial here rather than load-bearing; removing it is a
            # signature change across PipeFactory and belongs with the concept-side work.
            qualified_pipes = qualify_crate(crate).pipes

            # Load pipes with domain-filtered concept codes
            all_pipes: list[PipeAbstract] = []
            for pipe_ref, pipe_blueprint in qualified_pipes.items():
                parsed = QualifiedRef.parse_pipe_ref(raw=pipe_ref)
                if parsed.domain_path is None:
                    msg = f"Crate pipe_ref '{pipe_ref}' must be domain-qualified"
                    raise PipeLibraryError(msg).with_error_code(CoreCode.RUNTIME_UNEXPECTED)
                domain_code = parsed.domain_path
                pipe_code = parsed.local_code

                concept_codes_for_domain = domain_concept_codes.get(domain_code, [])

                source = crate.source_map.get(pipe_ref)
                # A pipe that reads a file its bundle names (a PipeDocGen `template_file`) resolves it in its bundle's
                # method tree, and in nothing else: the pipe's `source` is cleared, so neither a caller's label
                # (`source_map`) nor a `source` the bundle's text wrote on the pipe can point the read at a directory on
                # this host.
                pipe_blueprint = pipe_blueprint.model_copy(update={"source": None})
                with (
                    building_pipe_of(
                        tree_bundle=_building_bundle_of(
                            tree_bundle_ref=crate.tree_bundles.get(pipe_ref),
                            live_trees=live_trees,
                            written_tree=(written_pipe_trees or {}).get(pipe_ref),
                        )
                    ),
                    _locating_pipe_build_refusals(
                        pipe_code=pipe_code, domain_code=domain_code, source=source, elaboration=crate.elaboration_metadata.get(pipe_ref)
                    ),
                ):
                    pipe = PipeFactory[PipeAbstract].make_from_blueprint(
                        domain_code=domain_code,
                        pipe_code=pipe_code,
                        blueprint=pipe_blueprint,
                        concept_codes_from_the_same_domain=concept_codes_for_domain,
                    )
                all_pipes.append(pipe)

                # Track source file for this pipe (used by get_pipe_source)
                if source:
                    self._pipe_source_maps.setdefault(library_id, {})[pipe_ref] = source

            library.pipe_library.add_pipes(pipes=all_pipes)

            if not is_crate_prevalidated:
                library.validate_library()

            # Only cache fingerprint after the entire load succeeds — if loading fails
            # with an exception, subsequent retries must not be skipped.
            loaded_set.add(fingerprint)
            return all_pipes

    @override
    def load_from_blueprints(
        self,
        *,
        library_id: str,
        blueprints: list[PipelexBundleBlueprint],
        methods_dirs: list[Path] | None = None,
        address_dependency_sources: AddressDependencySources = AddressDependencySources.ANYWHERE,
    ) -> list[PipeAbstract]:
        """Load domains, concepts, and pipes from a list of blueprints.

        Delegates through LibraryCrate: builds a crate from blueprints, then loads from the crate.
        Also accumulates blueprints for later crate retrieval via get_crate().

        Args:
            library_id: The ID of the library to load into
            blueprints: List of parsed MTHDS blueprints to load
            methods_dirs: Directories laid out like ``.mthds/methods/`` holding packages for this load alone, such as
                the ones a request ships with its bundle. An address-based reference is looked up there first, and a
                package found there is never installed anywhere.
            address_dependency_sources: Whether a reference ``methods_dirs`` do not answer is looked up among the methods
                installed on this host and fetched on a miss (``ANYWHERE``), or refused (``SHIPPED``).

        Returns:
            List of all pipes that were loaded
        """
        # Bind the target library as current for the whole load: the factories beneath
        # (concept resolution, class-registry access) resolve through the ambient current
        # library, so a load into a non-current library must not read the caller's binding.
        with scoped_current_library(library_id=library_id), sharing_module_name_checks():
            # A bundle read from a file on this host that no loader placed in a method tree, such as a bundle file a CLI
            # names alone, is read as a member of its own file's tree: the steps of every bundle read from this host's
            # disk read only the files of their tree.
            unplaced_host_blueprints = [
                blueprint for blueprint in blueprints if blueprint.tree_bundle is None and blueprint.host_bundle_file is not None
            ]
            if unplaced_host_blueprints:
                tree_limits = local_tree_limits()
                for blueprint in unplaced_host_blueprints:
                    if blueprint.host_bundle_file is not None:
                        blueprint.place_in_tree(tree_bundle=tree_bundle_of_lone_file(bundle_file=blueprint.host_bundle_file, limits=tree_limits))
            # Every bundle read from this host's disk loads under its tree's requirements.txt, on every load: a blueprint
            # placed by an earlier load, a refused one included, is judged again rather than taken as judged.
            ensure_method_requirements_met(
                trees=[blueprint.tree_bundle.tree for blueprint in blueprints if blueprint.tree_bundle is not None],
                names_host_paths=True,
            )
            # Bundles parsed from content strings sit at the root of the tree of the files submitted beside them, when
            # there are any, so a step resolves a file it names there.
            content_blueprints = [blueprint for blueprint in blueprints if blueprint.tree_bundle is None and blueprint.host_bundle_file is None]
            if content_blueprints:
                submitted_tree = self._submitted_tree(library_id=library_id)
                if submitted_tree is not None:
                    for blueprint in content_blueprints:
                        blueprint.place_in_tree(tree_bundle=TreeBundle(tree=submitted_tree, tree_path=None))
            # The library holds every tree its bundles were read from for its runs, which read a file of one, a
            # PipeFunc call's or a PipeDocGen template, by the tree's digest through the method file store.
            live_trees = self._hold_trees_of(library_id=library_id, blueprints=blueprints)

            # Accumulate blueprints for later crate construction via get_crate()
            self._blueprints.setdefault(library_id, []).extend(blueprints)
            self._crate_cache.pop(library_id, None)

            # Discover and load address-based cross-package dependencies before loading pipes
            self._load_address_based_dependencies(
                library_id=library_id,
                blueprints=blueprints,
                methods_dirs=methods_dirs,
                address_dependency_sources=address_dependency_sources,
            )

            # Build the crate (merges, qualifies, detects duplicates)
            crate = LibraryCrateFactory.make_from_blueprints(blueprints=blueprints)

            # Validate same-domain concept references against the live library: the concepts declared
            # in this batch plus those already loaded by prior batches (e.g. via a -L library
            # directory). This is done in the loader, not the crate factory, so a bare concept ref can
            # resolve across separate load batches into the same library. The batch's own concepts are
            # not in the library yet (load_from_crate adds them below), so they come from `blueprints`.
            library = self.get_library(library_id=library_id)
            validate_concept_references_in_blueprints(
                blueprints=blueprints,
                already_loaded_concept_refs=set(library.concept_library.root.keys()),
            )

            # Load from crate (domains, concepts, pipes, validation). The dependencies were loaded above, so a
            # structure reference that still resolves to nothing is the bundle's own, and refuses the load.
            all_pipes = self._load_crate(
                library_id=library_id, crate=crate, is_crate_prevalidated=False, refuses_unresolved_structures=True, live_trees=live_trees
            )

            # Also record the aggregate crate fingerprint: get_crate() rebuilds one crate from
            # ALL accumulated blueprints, so once the library holds more than one batch its
            # fingerprint differs from every per-batch fingerprint recorded by load_from_crate.
            # Recorded only after the load succeeds, so a failed batch (whose blueprints were
            # already accumulated above) never registers a phantom fingerprint.
            if aggregate_crate := self.get_crate(library_id=library_id):
                self._loaded_fingerprints.setdefault(library_id, set()).add(aggregate_crate.fingerprint)

            return all_pipes

    def _load_concepts_from_blueprints(
        self,
        blueprints: list[PipelexBundleBlueprint],
    ) -> list["Concept"]:
        """Load concepts from blueprints in topological order based on refines dependencies.

        Concepts that refine other concepts are loaded after their base concepts,
        ensuring the base class is always registered before the refining class.
        Forward references between concepts (for structure fields) are resolved
        later by _run_concept_stage().

        Args:
            blueprints: List of parsed MTHDS blueprints to load

        Returns:
            List of loaded concepts
        """
        # Step 1: Collect all concept entries with metadata, detecting duplicates
        concept_source_in_this_load: dict[str, Path | None] = {}
        ref_to_entry: dict[str, tuple[str, str, ConceptBlueprint | str]] = {}

        for blueprint in blueprints:
            if blueprint.concept is not None:
                new_source = Path(blueprint.source) if blueprint.source else None
                for concept_code, concept_blueprint in blueprint.concept.items():
                    concept_ref = ConceptFactory.make_concept_ref_with_domain(
                        domain_code=blueprint.domain,
                        concept_code=concept_code,
                    )
                    # Detect duplicate concept declarations across different bundles in the same library
                    if concept_ref in concept_source_in_this_load:
                        existing_source = concept_source_in_this_load[concept_ref]
                        raise ConceptLibraryError(
                            duplicate_ref_msg(
                                ref_kind="concept",
                                ref=concept_ref,
                                existing_source=str(existing_source) if existing_source else None,
                                incoming_source=str(new_source) if new_source else None,
                            )
                        ).with_error_code(CoreCode.METHOD_NAME_CONFLICT)
                    concept_source_in_this_load[concept_ref] = new_source
                    ref_to_entry[concept_ref] = (
                        blueprint.domain,
                        concept_code,
                        concept_blueprint,
                    )

        return self._topological_load_concepts(ref_to_entry)

    def _load_concepts_from_crate(
        self,
        concepts: dict[str, ConceptBlueprint | str],
    ) -> list["Concept"]:
        """Load concepts from a crate's flat concept dict in topological order.

        Builds the entry map from the crate's flat dict, then delegates to
        _topological_load_concepts for sorting and instantiation.
        Duplicate detection is already done by LibraryCrateFactory.

        Args:
            concepts: Flat dict mapping concept_ref to ConceptBlueprint or string description

        Returns:
            List of loaded concepts in topological order
        """
        ref_to_entry: dict[str, tuple[str, str, ConceptBlueprint | str]] = {}
        for concept_ref, concept_blueprint in concepts.items():
            # Native concepts are auto-registered in every library (make_empty_with_native_concepts).
            # A normalized crate materializes them as explicit `native.<Code>` entries so external
            # consumers are self-contained; re-adding them here would collide with the pre-registered
            # natives. Skipping them makes a normalized crate directly loadable (round-trip), and is a
            # no-op for a transport crate (which never carries native entries).
            if NativeConceptCode.is_native_concept_ref_or_code(concept_ref_or_code=concept_ref):
                continue
            parsed = QualifiedRef.parse_concept_ref(raw=concept_ref)
            if parsed.domain_path is None:
                msg = f"Crate concept_ref '{concept_ref}' must be domain-qualified"
                raise ConceptLibraryError(msg).with_error_code(CoreCode.RUNTIME_UNEXPECTED)
            ref_to_entry[concept_ref] = (
                parsed.domain_path,
                parsed.local_code,
                concept_blueprint,
            )

        return self._topological_load_concepts(ref_to_entry)

    def _topological_load_concepts(
        self,
        ref_to_entry: "Mapping[str, tuple[str, str, ConceptBlueprint | str]]",
    ) -> list["Concept"]:
        """Sort concepts by refines dependencies and instantiate them.

        Shared helper used by both _load_concepts_from_blueprints (blueprint path)
        and _load_concepts_from_crate (crate path).

        Args:
            ref_to_entry: Mapping of concept_ref to (domain_code, concept_code, blueprint_or_string)

        Returns:
            List of loaded concepts in topological order
        """
        sorter: TopologicalSorter[str] = TopologicalSorter()

        for concept_ref, (
            domain_code,
            _concept_code,
            concept_blueprint,
        ) in ref_to_entry.items():
            dependencies: set[str] = set()

            if not isinstance(concept_blueprint, str) and concept_blueprint.refines:
                refines = concept_blueprint.refines
                # Skip native concepts (always available)
                if not NativeConceptCode.is_native_concept_ref_or_code(concept_ref_or_code=refines):
                    # Resolve to full concept ref
                    if "." in refines:
                        refined_ref = refines
                    else:
                        refined_ref = ConceptFactory.make_concept_ref_with_domain(
                            domain_code=domain_code,
                            concept_code=refines,
                        )
                    # Only add dependency if it's a concept we're loading
                    if refined_ref in ref_to_entry:
                        dependencies.add(refined_ref)

            sorter.add(concept_ref, *dependencies)

        try:
            sorted_refs = list(sorter.static_order())
        except CycleError as exc:
            msg = f"Cycle detected in concept refines dependencies: {exc.args[1]}"
            raise LibraryLoadingError(msg).with_error_code(CoreCode.METHOD_CYCLE) from exc

        all_concepts: list[Concept] = []
        for concept_ref in sorted_refs:
            domain_code, concept_code, concept_blueprint = ref_to_entry[concept_ref]
            concept = ConceptFactory.make_from_blueprint(
                domain_code=domain_code,
                concept_code=concept_code,
                blueprint_or_string_description=concept_blueprint,
            )
            all_concepts.append(concept)

        return all_concepts

    ############################################################
    # Private helper methods
    ############################################################

    @staticmethod
    def _hold_trees_of(*, library_id: str, blueprints: "Iterable[PipelexBundleBlueprint]") -> dict[str, MethodTree]:
        """Hold the trees these bundles were placed in, for the library's runs to read, and return them by digest.

        A tree listed from this host's disk is served from it, each file checked against the hash its listing recorded;
        the tree of submitted files was held when it was assembled. Two trees with one digest hold the same files, so the
        first placed is the one returned, and each tree is held once, however many of its bundles load: a holder keeps
        the first sources it held a tree with.
        """
        live_trees: dict[str, MethodTree] = {}
        for blueprint in blueprints:
            tree_bundle = blueprint.tree_bundle
            if tree_bundle is None:
                continue
            tree = tree_bundle.tree
            if tree.digest in live_trees:
                continue
            live_trees[tree.digest] = tree
            if tree.directory is not None and not LOCAL_METHOD_FILES.holds(holder=library_id, tree_digest=tree.digest):
                LOCAL_METHOD_FILES.hold_tree(holder=library_id, tree=tree)
        return live_trees

    def _load_mthds_files_into_library(
        self,
        *,
        library_id: str,
        bundle_files: list[LibraryBundleFile],
        methods_dirs: list[Path] | None = None,
        address_dependency_sources: AddressDependencySources = AddressDependencySources.ANYWHERE,
    ) -> list[PipeAbstract]:
        """Load MTHDS files into a specific library.

        This method:
        1. Parses blueprints from MTHDS files, each placed in the method tree it was listed in
        2. Finds and loads dependency packages (if manifest has dependencies with local paths)
        3. Loads blueprints into the specified library

        Args:
            library_id: The ID of the library to load into
            bundle_files: The bundle files to load, each the member of its method tree
            methods_dirs: Directories laid out like ``.mthds/methods/`` holding packages for this load alone
            address_dependency_sources: Where a package the bundles call by address may be found (``load_libraries``)
        """
        valid_mthds_paths = [bundle_file.path for bundle_file in bundle_files]
        blueprints: list[PipelexBundleBlueprint] = []
        # Each bundle as a message names it, which for a tree a host wrote out is its tree path, as for its blueprint.
        bundle_sources: list[str] = []
        for bundle_file in bundle_files:
            mthds_file_path = bundle_file.path
            # A bundle of a tree a host wrote out for a caller is named by its tree path, never by the host's directory.
            bundle_source = (
                bundle_file.tree_bundle.tree_path
                if bundle_file.tree_bundle.tree_path is not None and WRITTEN_METHOD_TREES.holds_tree(tree=bundle_file.tree_bundle.tree)
                else str(mthds_file_path)
            )
            bundle_sources.append(bundle_source)
            try:
                blueprint = MthdsParser.make_pipelex_bundle_blueprint(bundle_path=mthds_file_path, mthds_source=bundle_source)
                blueprint.place_in_tree(tree_bundle=bundle_file.tree_bundle)
            except FileNotFoundError as file_not_found_error:
                msg = f"Could not find MTHDS bundle at '{bundle_source}'"
                raise LibraryLoadingError(msg).with_error_code(CoreCode.METHOD_NOT_FOUND) from file_not_found_error
            except MthdsParserError as parser_error:
                # Forward BLUEPRINT validation errors from interpreter
                msg = f"Could not load MTHDS bundle from '{bundle_source}' because of: {parser_error.message}"
                raise LibraryLoadingError(
                    message=msg,
                    blueprint_validation_errors=parser_error.validation_errors,
                ) from parser_error
            blueprints.append(blueprint)

        # Find manifest and run package visibility validation
        manifest = self._check_package_visibility(blueprints=blueprints, mthds_paths=valid_mthds_paths)

        # Warn if the package requires a newer MTHDS standard version
        if manifest is not None and manifest.mthds_version is not None:
            self._warn_if_mthds_version_unsatisfied(
                mthds_version_constraint=manifest.mthds_version,
                package_address=manifest.address,
            )

        # Load dependency packages if manifest has local-path dependencies
        if manifest is not None and getattr(manifest, "dependencies", None):
            package_root = self._find_package_root(mthds_paths=valid_mthds_paths)
            if package_root is not None:
                self._load_dependency_packages(
                    library_id=library_id,
                    manifest=manifest,
                    package_root=package_root,
                )

        # Store resolved absolute paths for duplicate detection in the library
        library = self.get_library(library_id=library_id)
        for mthds_file_path in valid_mthds_paths:
            try:
                resolved_path = mthds_file_path.resolve()
            except (OSError, RuntimeError):
                resolved_path = mthds_file_path
            library.loaded_mthds_paths.append(resolved_path)

        try:
            return self.load_from_blueprints(
                library_id=library_id,
                blueprints=blueprints,
                methods_dirs=methods_dirs,
                address_dependency_sources=address_dependency_sources,
            )
        except ValidationError as validation_error:
            # Categorize before wrapping. `translate_to_validate_bundle_error` has its own
            # `except ValidationError` arm that categorizes, but it never sees this error: wrapping it
            # in a bare `LibraryError` here routed it to the `except LibraryError` arm instead, which
            # forwards structured data and has none to forward — so every pipe/concept error a
            # pydantic validator raises during the merge arrived on the wire as one untyped residual.
            # That is the whole reason `optional_input_unguarded` and `optional_output_required` were
            # reachable through `resolve_crate_from_contents` but not through a library directory.
            raise LibraryLoadingError(
                message=(
                    f"Could not load blueprints from {bundle_sources} because of: "
                    f"{report_validation_error(validation_error=validation_error).message}"
                ),
                pipe_concept_validation_errors=categorize_pipe_validation_error(validation_error=validation_error),
            ) from validation_error
        except (ConceptLibraryError, PipeLibraryError) as ref_error:
            # Merge-time reference errors (undeclared cross-file concept refs, signature/concrete
            # contract mismatches, duplicate refs). Add the batch's file list as context, then let the
            # outer translate_to_validate_bundle_error LibraryError arm shape it into a
            # ValidateBundleError. Re-raising rather than mutating keeps the message immutable, and
            # carrying the payload across is what keeps the re-raise from being lossy:
            # `ConceptLibraryError` is a `LibraryLoadingError` and reaches here holding the per-reference
            # items that make an unresolved concept a categorized `unresolved_concept` rather than a
            # bare residual. Reconstructing it message-only silently dropped them.
            msg = f"Could not load blueprints from {bundle_sources} because of: {ref_error}"
            # The new error keeps the code its raise site chose, which a fresh instance of the class would not carry.
            rewrapped_error: ConceptLibraryError | PipeLibraryError
            if isinstance(ref_error, LibraryLoadingError):
                rewrapped_error = type(ref_error)(
                    msg,
                    blueprint_validation_errors=ref_error.blueprint_validation_errors,
                    pipe_concept_validation_errors=ref_error.pipe_concept_validation_errors,
                )
            else:
                rewrapped_error = type(ref_error)(msg)
            chosen_code = ref_error.own_error_code
            if chosen_code is not None:
                rewrapped_error.with_error_code(chosen_code)
            raise rewrapped_error from ref_error

    def _warn_if_mthds_version_unsatisfied(
        self,
        mthds_version_constraint: str,
        *,
        package_address: str,
    ) -> None:
        """Emit a warning if the current MTHDS standard version does not satisfy the package's constraint."""
        try:
            constraint = parse_constraint(mthds_version_constraint)
            current_version = parse_version(MTHDS_STANDARD_VERSION)
        except SemVerError as exc:
            log.warning(
                "The MTHDS version constraint of a package could not be parsed",
                fields={"package_address": package_address, "mthds_version_constraint": mthds_version_constraint, **error_fields(exc=exc)},
            )
            return

        if not version_satisfies(current_version, constraint=constraint):
            log.warning(
                "A package requires another MTHDS standard version than this runtime's",
                fields={
                    "package_address": package_address,
                    "mthds_version_constraint": mthds_version_constraint,
                    "mthds_standard_version": MTHDS_STANDARD_VERSION,
                    USER_ACTION_FIELD: "Run the package on a Pipelex release that implements its MTHDS version, or some features may fail",
                },
            )

    def _check_package_visibility(
        self,
        blueprints: list[PipelexBundleBlueprint],
        *,
        mthds_paths: list[Path],
    ) -> MethodsManifest | None:
        """Check package visibility if a METHODS.toml manifest exists.

        Walks up from the first bundle path to find a METHODS.toml manifest.
        If found, validates all cross-domain pipe references against the exports.

        Args:
            blueprints: The parsed bundle blueprints
            mthds_paths: The MTHDS file paths that were loaded

        Returns:
            The manifest if found, or None
        """
        if not mthds_paths:
            return None

        # Try to find a manifest from the first bundle path
        try:
            manifest = find_package_manifest(mthds_paths[0])
        except ManifestError as exc:
            log.warning("The package's METHODS.toml could not be parsed", fields=error_fields(exc=exc))
            # Still enforce reserved domains even when manifest is unparseable
            checker = make_visibility_checker(manifest=None, blueprints=blueprints)
            reserved_errors = checker.validate_reserved_domains()
            if reserved_errors:
                error_messages = [err.message for err in reserved_errors]
                joined_errors = "\n  - ".join(error_messages)
                msg = f"Reserved domain violations found:\n  - {joined_errors}"
                raise LibraryLoadingError(msg).with_error_code(CoreCode.METHOD_NAME_CONFLICT) from exc
            return None

        if manifest is None:
            # Still enforce reserved domains even for standalone bundles
            checker = make_visibility_checker(manifest=None, blueprints=blueprints)
            reserved_errors = checker.validate_reserved_domains()
            if reserved_errors:
                error_messages = [err.message for err in reserved_errors]
                joined_errors = "\n  - ".join(error_messages)
                msg = f"Reserved domain violations found:\n  - {joined_errors}"
                raise LibraryLoadingError(msg).with_error_code(CoreCode.METHOD_NAME_CONFLICT)
            return None

        visibility_errors = check_visibility_for_blueprints(manifest=manifest, blueprints=blueprints)
        if visibility_errors:
            error_messages = [err.message for err in visibility_errors]
            joined_errors = "\n  - ".join(error_messages)
            msg = f"Package visibility violations found:\n  - {joined_errors}"
            raise LibraryLoadingError(msg).with_error_code(CoreCode.METHOD_PIPE_NOT_EXPORTED)

        return manifest

    def _find_package_root(self, mthds_paths: list[Path]) -> Path | None:
        """Find the package root directory by walking up from the first .mthds file.

        The package root is the directory containing METHODS.toml.

        Args:
            mthds_paths: The MTHDS file paths

        Returns:
            The package root path, or None
        """
        if not mthds_paths:
            return None

        current = mthds_paths[0].parent.resolve()
        while True:
            manifest_path = current / "METHODS.toml"
            if manifest_path.is_file():
                return current

            git_dir = current / ".git"
            if git_dir.exists():
                return None

            parent = current.parent
            if parent == current:
                return None
            current = parent

    def _load_dependency_packages(
        self,
        *,
        library_id: str,
        manifest: MethodsManifest,
        package_root: Path,
    ) -> None:
        """Load dependency packages into the library.

        Resolves local-path dependencies, parses their blueprints, and loads
        their concepts and exported pipes into isolated child libraries.
        Aliased entries are also added to the main library for backward-compatible lookups.

        Args:
            library_id: The library to load into
            manifest: The consuming package's manifest
            package_root: The root directory of the consuming package
        """
        try:
            resolved_deps = resolve_all_dependencies(manifest=manifest, package_root=package_root)
        except DependencyResolveError as exc:
            msg = f"Failed to resolve dependencies: {exc}"
            raise LibraryLoadingError(msg).with_error_code(CoreCode.METHOD_DEPENDENCY_MISSING) from exc

        library = self.get_library(library_id=library_id)

        # This machine's limits are read once for every package of the manifest.
        tree_limits = local_tree_limits()
        for resolved_dep in resolved_deps:
            self._load_single_dependency(
                library=library,
                library_id=library_id,
                resolved_dep=resolved_dep,
                package_address=resolved_dep.address,
                tree_limits=tree_limits,
            )

        # Wire concept resolver after all deps are loaded so cross-package
        # refinement checks can traverse into child libraries
        library.concept_library.set_concept_resolver(library.resolve_concept)

    def _load_single_dependency(
        self,
        library: Library,
        *,
        library_id: str,
        resolved_dep: ResolvedDependency,
        package_address: str,
        tree_limits: TreeLimits | None = None,
    ) -> None:
        """Load a single resolved dependency into an isolated child library.

        Creates a child Library for the dependency, loads domains/concepts/pipes
        into it, registers it in library.dependency_libraries, and adds aliased
        entries to the main library for backward-compatible cross-package lookups.

        The bundles are the ``.mthds`` files of the package's method tree, rooted at its own directory, so a file
        the membership rule keeps out of the package is neither loaded nor read by one of its steps. Each bundle's
        ``source`` is ``<package_address>/<tree path>``, never the file's path on the host, so a refusal inside the
        dependency names it that way on every surface.

        A bundle of the dependency that does not parse refuses the load (``_parse_dependency_bundle``): a
        package shipped with a request is the caller's own content, and a fetched package's author is owed
        the same report rather than a later refusal saying the package lacks a pipe.

        Args:
            library: The main library to load into
            library_id: The id the manager holds the main library under, which holds the package's tree for its runs
            resolved_dep: The resolved dependency info
            package_address: The dependency's address as a reference names it, without any ``@<tag>``
            tree_limits: The limits the package's tree is listed under, read from the configuration when not given

        Raises:
            MthdsParserError: A bundle of the dependency does not parse, its items named by the bundle's source.
            MethodRequirementsError: The package's requirements.txt holds a line the standard refuses, or names
                packages its PipeFunc environment does not hold, named by the package's address.
        """
        alias = resolved_dep.alias

        # Parse dependency blueprints: the bundles of the package's method tree, rooted at its own directory, so a file
        # the membership rule keeps out of the package is neither loaded nor read by one of its steps.
        dep_blueprints: list[PipelexBundleBlueprint] = []
        # Each bundle as the member of the package's tree, by its caller-facing source, for the pipes reading a file it names.
        tree_bundles_by_source: dict[str, TreeBundle] = {}
        # Listed under the package's address: a refusal never names the directory it was installed or fetched into.
        package_tree = list_package_method_tree(root=resolved_dep.package_root, package_address=package_address, limits=tree_limits)
        # The package's own requirements.txt is judged before any of its bundles loads, as the consumer's tree is.
        ensure_package_requirements_met(tree=package_tree, package_address=package_address)
        # Held for the consumer's runs, which read a file of the package's tree, such as one of its steps' template
        # files, by the tree's digest.
        LOCAL_METHOD_FILES.hold_tree(holder=library_id, tree=package_tree)
        for tree_bundle in tree_bundles_of(tree=package_tree):
            # The package's address and the bundle's tree path: never the host's path to the package.
            bundle_source = f"{package_address}/{tree_bundle.tree_path}"
            blueprint = _parse_dependency_bundle(mthds_path=tree_bundle.location, bundle_source=bundle_source, package_address=package_address)
            blueprint.place_in_tree(tree_bundle=tree_bundle)
            tree_bundles_by_source[bundle_source] = tree_bundle
            dep_blueprints.append(blueprint)

        if not dep_blueprints:
            log.warning("A dependency holds no valid bundle", fields={"dependency_alias": alias, "package_address": package_address})
            return

        # Warn if the dependency requires a newer MTHDS standard version
        if resolved_dep.manifest is not None and resolved_dep.manifest.mthds_version is not None:
            self._warn_if_mthds_version_unsatisfied(
                mthds_version_constraint=resolved_dep.manifest.mthds_version,
                package_address=resolved_dep.address,
            )

        # Merge the dependency's files into one crate so a multi-file package reconciles exactly like
        # the main load path: a PipeSignature header and its concrete sibling collapse to a single
        # pipe (concrete wins), and genuine duplicates / signature-concrete contract mismatches raise
        # here rather than colliding later in add_new_pipe (which the per-pipe handler below would
        # swallow as a warning, silently dropping one declaration). Same-domain concept references are
        # validated across the merged files; cross-package and external-domain refs are deferred.
        crate = LibraryCrateFactory.make_from_blueprints(blueprints=dep_blueprints)
        validate_concept_references_in_blueprints(blueprints=dep_blueprints)

        # Create isolated child library for this dependency
        child_library = LibraryFactory.make_empty()

        # Load domains into child library
        all_domains: list[Domain] = []
        for blueprint in dep_blueprints:
            domain = DomainFactory.make_from_blueprint(
                blueprint=DomainBlueprint(
                    source=blueprint.source,
                    code=blueprint.domain,
                    description=blueprint.description or "",
                    system_prompt=blueprint.system_prompt,
                ),
            )
            all_domains.append(domain)
        child_library.domain_library.add_domains(domains=all_domains)

        # Load concepts into child library. A dependency's forward references may name its own concepts and
        # nothing else: it cannot name its consumer, its own dependencies are not loaded, and a wider namespace would
        # let a reference to a domain it does not declare bind silently to a consumer's class of that name. Because its
        # own dependencies are not loaded, a structure class still incomplete does not refuse the consumer's load: it
        # may name a concept of one of them, which is no fault of the package, and it fails at first use instead.
        dep_concepts = self._load_concepts_from_blueprints(dep_blueprints)
        child_library.concept_library.add_concepts(concepts=dep_concepts)
        self._run_concept_stage(
            loaded_concepts=dep_concepts, visible_concepts=dep_concepts, concept_sources=crate.source_map, refuses_unresolved_structures=False
        )

        # What a consumer may reference: `None` when the package declares no exports, so every pipe is public.
        public_pipe_refs = _public_dependency_pipe_refs(resolved_dep=resolved_dep, blueprints=dep_blueprints)
        # The `domain.code` of each pipe meant to load that failed to build, with why, for a reference to it to name.
        unbuilt_pipe_reasons: dict[str, str] = {}

        # Temporarily register dep concepts in main library for pipe construction
        # (PipeFactory resolves concepts through the hub's current library)
        temp_concept_refs: list[str] = []
        for concept in dep_concepts:
            if not library.concept_library.is_concept_exists(concept_ref=concept.concept_ref):
                library.concept_library.add_new_concept(concept=concept)
                temp_concept_refs.append(concept.concept_ref)

        # Per-domain concept codes, mirroring load_from_crate — and VESTIGIAL for the same reason:
        # the qualification pass below rewrites every io ref to dotted form, and PipeFactory only
        # consults this parameter for dot-free refs. Kept until the deferred PipeFactory signature
        # change removes it on both paths together.
        domain_concept_codes: dict[str, list[str]] = {}
        for concept in dep_concepts:
            parsed_concept = QualifiedRef.parse_concept_ref(raw=concept.concept_ref)
            if parsed_concept.domain_path is not None:
                domain_concept_codes.setdefault(parsed_concept.domain_path, []).append(parsed_concept.local_code)

        # Load exported pipes (reconciled by the crate) into child library, ensuring temp concepts
        # are always cleaned up even if an unexpected exception occurs
        try:
            # The main load path's qualification, plus this load's alias: a dependency package's own
            # in-body refs are its own domain's, and each is stored as `alias->domain.code`, the key
            # the consumer's library holds that pipe under, so every reader of the ref (validation,
            # the pre-run walks, execution) reaches the package's pipe and never a consumer pipe of
            # the same `domain.code`. The child library itself stays keyed by `domain.code`. Inside the
            # try: qualification can raise on malformed refs, and the temp concepts must still be
            # removed from the main library.
            qualified_dep_pipes = qualify_crate(crate, package_alias=alias).pipes
            if public_pipe_refs is None:
                loaded_pipe_refs = set(qualified_dep_pipes)
            else:
                loaded_pipe_refs = reachable_dependency_pipe_refs(
                    public_pipe_refs=public_pipe_refs, qualified_pipes=qualified_dep_pipes, package_alias=alias
                )
            for pipe_ref, pipe_blueprint in qualified_dep_pipes.items():
                parsed_pipe = QualifiedRef.parse_pipe_ref(raw=pipe_ref)
                if parsed_pipe.domain_path is None:
                    msg = f"Crate pipe_ref '{pipe_ref}' must be domain-qualified"
                    raise PipeLibraryError(msg).with_error_code(CoreCode.RUNTIME_UNEXPECTED)
                domain_code = parsed_pipe.domain_path
                pipe_code = parsed_pipe.local_code
                # A private pipe nothing public reaches is never built, so a broken one cannot refuse the consumer's load.
                if pipe_ref not in loaded_pipe_refs:
                    continue
                dependency_source = crate.source_map.get(pipe_ref)
                # A pipe that reads a file its bundle names (a PipeDocGen `template_file`) resolves it in the package's
                # tree, from the bundle's tree path there. The package's address stays the source every refusal names,
                # since the host's path is not the caller's.
                dependency_tree_bundle = tree_bundles_by_source.get(dependency_source) if dependency_source is not None else None
                # Cleared, so a `source` the package's own text wrote on the pipe never names a directory.
                pipe_blueprint = pipe_blueprint.model_copy(update={"source": None})
                try:
                    # The same location the main load path attaches, so a dependency pipe's refusal
                    # names the dependency's own file.
                    with (
                        building_pipe_of(tree_bundle=dependency_tree_bundle),
                        _locating_pipe_build_refusals(
                            pipe_code=pipe_code,
                            domain_code=domain_code,
                            source=dependency_source,
                            elaboration=crate.elaboration_metadata.get(pipe_ref),
                        ),
                    ):
                        pipe = PipeFactory[PipeAbstract].make_from_blueprint(
                            domain_code=domain_code,
                            pipe_code=pipe_code,
                            blueprint=pipe_blueprint,
                            concept_codes_from_the_same_domain=domain_concept_codes.get(domain_code, []),
                        )
                    # What the pipe can tell is broken once built, such as a PipeFunc whose function the package does
                    # not hold, makes it a pipe the package could not build, refusing only a reference to it.
                    pipe.validate_once_built()
                    child_library.pipe_library.add_new_pipe(pipe=pipe)
                except ValidationError as exc:
                    log.warning(
                        "A pipe of a dependency could not be loaded",
                        fields={"dependency_alias": alias, "pipe_code": pipe_code, **error_fields(exc=exc)},
                    )
                    unbuilt_pipe_reasons[pipe_ref] = "; ".join(str(error["msg"]) for error in exc.errors()) or str(exc)
                except PipeValidationError as exc:
                    log.warning(
                        "A pipe of a dependency could not be loaded",
                        fields={"dependency_alias": alias, "pipe_code": pipe_code, **error_fields(exc=exc)},
                    )
                    unbuilt_pipe_reasons[pipe_ref] = str(exc)
        finally:
            # Remove temporary concept entries from main library
            library.concept_library.remove_concepts_by_concept_refs(concept_refs=temp_concept_refs)

        # Register child library for isolation
        library.dependency_libraries[alias] = child_library

        # Add aliased entries to main library for backward-compatible cross-package lookups
        for concept in dep_concepts:
            library.concept_library.add_dependency_concept(alias=alias, concept=concept)

        for pipe in child_library.pipe_library.get_pipes():
            is_exported = public_pipe_refs is None or pipe.pipe_ref in public_pipe_refs
            library.pipe_library.add_dependency_pipe(alias=alias, pipe=pipe, is_exported=is_exported)
        library.pipe_library.add_withheld_dependency_pipes(alias=alias, pipe_refs=set(qualified_dep_pipes) - loaded_pipe_refs)
        for pipe_ref, reason in unbuilt_pipe_reasons.items():
            library.pipe_library.add_unbuilt_dependency_pipe(alias=alias, pipe_ref=pipe_ref, reason=reason)

        log.verbose(
            "Loaded a dependency",
            fields={"dependency_alias": alias, "concept_count": len(dep_concepts), "bundle_count": len(dep_blueprints)},
        )

    def _load_address_based_dependencies(
        self,
        *,
        library_id: str,
        blueprints: list[PipelexBundleBlueprint],
        methods_dirs: list[Path] | None = None,
        address_dependency_sources: AddressDependencySources = AddressDependencySources.ANYWHERE,
    ) -> None:
        """Scan blueprints for cross-package pipe refs with address-based aliases and load them.

        Collects all cross-package pipe references from controller blueprints
        (sequences, batches, conditions, parallels), identifies those whose
        alias contains '/' (i.e. a full package address), and loads each
        unique address-based dependency. A dependency is looked up first among
        the packages of ``methods_dirs``, the load's own, then among the
        installed methods; one missing from both is fetched by address
        (honoring an ``@<tag>`` pin) and installed when fetch-on-miss is enabled.
        With ``AddressDependencySources.SHIPPED``, only ``methods_dirs`` are
        searched: nothing installed on this host is read and nothing is fetched,
        and an address they do not answer is unresolved, its item carrying
        ``unshipped_address_dependency_message``.

        A package that cannot be resolved is the caller's to fix, since the reference is part of their bundle: every
        address is tried, then the load is refused with one ``unresolved_package_dependency`` item per address that
        failed, located on the first pipe naming it. A failure of the host's own store (``MethodInstallError``) and the
        refusal of a package's Python structures (``MethodStructuresRefusedError``) propagate as they are.

        Also searches for .mthds/methods/ directories relative to the bundle
        source path, walking up ancestor directories to find installed methods
        even when the CWD differs from the bundle's project root.

        Args:
            library_id: The library to load into
            blueprints: The parsed bundle blueprints to scan
            methods_dirs: The load's own methods directories, searched before everything else and never written
            address_dependency_sources: Whether an address ``methods_dirs`` do not answer may be looked up on this host

        Raises:
            LibraryLoadingError: One or more referenced packages could not be resolved.
        """
        library = self.get_library(library_id=library_id)

        # Each address-based alias, with the first reference naming it and the bundle that makes it, in bundle order.
        first_references: dict[str, tuple[LocatedPipeReference, PipelexBundleBlueprint]] = {}
        for blueprint in blueprints:
            for reference in blueprint.collect_located_pipe_references():
                if QualifiedRef.has_cross_package_prefix(reference.pipe_ref):
                    alias, _remainder = QualifiedRef.split_cross_package_ref(reference.pipe_ref)
                    if QualifiedRef.is_address_based_alias(alias) and alias not in first_references:
                        first_references[alias] = (reference, blueprint)

        if not first_references:
            return

        # Derive extra search dirs from bundle source paths, which only a load that may read this host's methods searches.
        extra_search_dirs: list[Path] | None
        match address_dependency_sources:
            case AddressDependencySources.SHIPPED:
                extra_search_dirs = None
            case AddressDependencySources.ANYWHERE:
                extra_search_dirs = find_methods_dirs_from_blueprints(blueprints)

        unresolved_items: list[PipesAndConceptValidationErrorData] = []
        for full_address, (reference, blueprint) in first_references.items():
            if full_address in library.dependency_libraries:
                continue
            try:
                self._load_address_based_dependency(
                    library=library,
                    library_id=library_id,
                    full_address=full_address,
                    extra_search_dirs=extra_search_dirs,
                    methods_dirs=methods_dirs,
                    address_dependency_sources=address_dependency_sources,
                )
            except (MethodFetchDisabledError, MethodDependencyFetchError, MethodDependencyNotShippedError) as exc:
                # The item carries the sentence its code renders; the host's log keeps the whole cause chain, git's raw output
                # included, since a cause on the host (git missing, an unwritable clone directory) becomes an item too.
                causes = " <- ".join(f"{type(cause).__name__}: {cause}" for cause in iter_cause_chain(exc))
                log.warning("A method package could not be resolved", fields={"package_address": full_address, **error_fields(exc=exc, text=causes)})
                unresolved_items.append(
                    PipesAndConceptValidationErrorData(
                        error_type=PipeValidationErrorType.UNRESOLVED_PACKAGE_DEPENDENCY,
                        domain_code=blueprint.domain,
                        source=blueprint.source,
                        pipe_code=reference.referring_pipe_code,
                        missing_pipe_code=reference.pipe_ref,
                        message=exc.message,
                        field_path=reference.field_path,
                    )
                )

        if unresolved_items:
            raise LibraryLoadingError(
                message=" ".join(item.message for item in unresolved_items),
                pipe_concept_validation_errors=unresolved_items,
            )

        # Wire concept resolver after all deps are loaded
        library.concept_library.set_concept_resolver(library.resolve_concept)

    def _load_address_based_dependency(
        self,
        library: "Library",
        *,
        library_id: str,
        full_address: str,
        extra_search_dirs: list[Path] | None = None,
        methods_dirs: list[Path] | None = None,
        address_dependency_sources: AddressDependencySources = AddressDependencySources.ANYWHERE,
    ) -> None:
        """Load a method package on demand using its full address, fetching it on a miss.

        Looks the address up among the packages of ``methods_dirs`` first, which win over an installed copy of the same
        address since they are the ones the caller chose, and on a miss resolves it to an installed method, fetching
        and installing the package (honoring an ``@<tag>`` pin) when no installed method matches and fetch-on-miss is
        enabled. It then builds a ResolvedDependency and delegates to _load_single_dependency() to load it as a child
        library with the full address as alias.

        Args:
            library: The main library to load into
            library_id: The id the manager holds the main library under, which holds the package's tree for its runs
            full_address: The full package address (e.g. "github.com/Pipelex/methods/documents")
            extra_search_dirs: Additional .mthds/methods/ directories to scan
            methods_dirs: The load's own methods directories, searched before everything else and never written
            address_dependency_sources: ``SHIPPED`` refuses an address ``methods_dirs`` do not answer, reading nothing
                installed on this host and fetching nothing; ``ANYWHERE`` falls back to the installed methods and a fetch

        Raises:
            MethodRefError: The address resolves to no vendored or installed method and could not be
                fetched — fetch-on-miss disabled, an unfetchable address, a failed fetch,
                or a failed install. Never a silent pass.
            MethodDependencyNotShippedError: Under ``SHIPPED``, no package of ``methods_dirs`` answers the address.
        """
        vendored = find_vendored_method(full_address=full_address, methods_dirs=methods_dirs) if methods_dirs else None
        match address_dependency_sources:
            case AddressDependencySources.SHIPPED:
                if vendored is None:
                    raise MethodDependencyNotShippedError(unshipped_address_dependency_message(alias=full_address))
                installed = vendored
            case AddressDependencySources.ANYWHERE:
                installed = vendored or resolve_address_based_method(full_address=full_address, extra_search_dirs=extra_search_dirs)

        exported_pipe_codes = determine_exported_pipes(manifest=installed.manifest)

        resolved_dep = ResolvedDependency(
            alias=full_address,
            address=installed.manifest.address,
            manifest=installed.manifest,
            package_root=installed.path,
            mthds_files=installed.mthds_files,
            exported_pipe_codes=exported_pipe_codes,
        )

        self._load_single_dependency(
            library=library,
            library_id=library_id,
            resolved_dep=resolved_dep,
            # The address the lookup matched (the manifest's address and the method's name), never a tag.
            package_address=f"{installed.manifest.address}/{installed.name}",
        )

    def _remove_pipes_from_blueprint(self, blueprint: PipelexBundleBlueprint) -> None:
        library = self.get_current_library()
        if blueprint.pipe is not None:
            pipe_refs_to_remove = [
                PipeFactory.make_pipe_ref_with_domain(domain_code=blueprint.domain, pipe_code=pipe_code) for pipe_code in blueprint.pipe
            ]
            library.pipe_library.remove_pipes_by_refs(pipe_refs=pipe_refs_to_remove)

    def _remove_concepts_from_blueprint(self, blueprint: PipelexBundleBlueprint) -> None:
        library = self.get_current_library()
        if blueprint.concept is not None:
            concept_codes_to_remove = [
                ConceptFactory.make_concept_ref_with_domain(domain_code=blueprint.domain, concept_code=concept_code)
                for concept_code in blueprint.concept
            ]
            library.concept_library.remove_concepts_by_concept_refs(concept_refs=concept_codes_to_remove)

    @override
    def _remove_from_blueprint(self, *, library_id: str, blueprint: PipelexBundleBlueprint) -> None:
        # Bind the target library as current: the helpers below resolve through the ambient
        # current library, so a removal from a non-current library must honor library_id.
        with scoped_current_library(library_id=library_id):
            self._remove_pipes_from_blueprint(blueprint=blueprint)
            self._remove_concepts_from_blueprint(blueprint=blueprint)

    @override
    def _remove_from_blueprints(self, *, library_id: str, blueprints: list[PipelexBundleBlueprint]) -> None:
        for blueprint in blueprints:
            self._remove_from_blueprint(library_id=library_id, blueprint=blueprint)

    def _run_concept_stage(
        self,
        *,
        loaded_concepts: list["Concept"],
        visible_concepts: "Iterable[Concept]",
        concept_sources: "Mapping[str, str]",
        refuses_unresolved_structures: bool,
    ) -> None:
        """The steps that follow adding a batch of concepts to a library, shared by both load paths.

        The crate load and `_load_single_dependency` both call this, and nothing else does: the dependency loader
        once hand-copied these steps and dropped two of them, so a dependency's forward references were never
        resolved and its concept cycles never checked. The order is load-bearing. The cycle check reads the resolved
        field annotations, and an unresolved forward reference has no `__name__`, which is how an unrebuilt reference
        hides from it, so the rebuild and its refusal come first.

        Args:
            loaded_concepts: The concepts this batch loaded, whose structure classes are rebuilt and checked
            visible_concepts: Every concept those classes' forward references may name, the loaded ones included;
                where two share a class name, the later one wins
            concept_sources: concept_ref -> the bundle that declared it, for the refusal's message
            refuses_unresolved_structures: Whether a generated structure class still incomplete refuses the load
        """
        self._rebuild_structure_classes(
            loaded_concepts=loaded_concepts,
            visible_concepts=visible_concepts,
            concept_sources=concept_sources,
            refuses_unresolved_structures=refuses_unresolved_structures,
        )
        self._detect_concept_cycles(loaded_concepts, concept_sources=concept_sources)

    def _rebuild_structure_classes(
        self,
        *,
        loaded_concepts: list["Concept"],
        visible_concepts: "Iterable[Concept]",
        concept_sources: "Mapping[str, str]",
        refuses_unresolved_structures: bool,
    ) -> None:
        """Resolve the forward references of the loaded concepts' structure classes, and refuse any left unresolved.

        A generated structure class names another concept's class as a forward reference, spelled from the concept
        ref whatever class the concept actually has (`"invented_notes__Note"`), and pydantic resolves it only when the
        class is rebuilt against a namespace holding that name. So the namespace keys every visible concept's class
        both by its own name and by that spelling, which differ for a concept backed by a Python class
        (`structure = "CustomerPayload"`). The loaded concepts' classes are keyed by their bare concept code too: the
        generator emits a bare code only for a ref with no domain, and a bare code is ambiguous across domains, so
        that key must not widen with the rest.

        Where two visible concepts share a key, the later one wins, and the callers order the main package after its
        dependencies. A dependency concept and a main-package concept with the same `domain.Code` share that key, and
        the main package's class is the one a reference resolves to. That clash is L-260929-0584cc's.

        A generated class whose own fields name a class the namespace lacks refuses the load, when the caller asks for
        it, instead of loading and failing at first use. A class whose own fields all resolve can still be incomplete,
        because pydantic builds a held class that is incomplete inline, and the held class is the one to blame: the
        load of a dependency's class or of a Python class chose not to refuse it, so the holder is left for first use
        too, and a generated class of this batch is refused on its own. Only generated classes are checked, and a
        generated class is recognised by its name: the concept factory names every class it generates
        `make_qualified_structure_class_name(domain, code)`, while a class registered from Python for a concept keeps
        its own name. Such a class, like a native one, is left to its own module's resolution: its rebuild failing is
        only logged, as before.
        """
        class_registry = get_class_registry()
        namespace: dict[str, type] = {}
        for concept in [*visible_concepts, *loaded_concepts]:
            if structure_class := class_registry.get_class(name=concept.structure_class_name):
                namespace[concept.structure_class_name] = structure_class
                namespace[make_qualified_structure_class_name(domain_code=concept.domain_code, concept_code=concept.code)] = structure_class
        for concept in loaded_concepts:
            if structure_class := class_registry.get_class(name=concept.structure_class_name):
                namespace[concept.code] = structure_class

        refusals: list[str] = []
        for concept in loaded_concepts:
            structure_class = class_registry.get_class(name=concept.structure_class_name)
            if structure_class is None or not issubclass(structure_class, BaseModel):
                continue
            rebuild_error: NameError | PydanticUserError | None = None
            try:
                structure_class.model_rebuild(_types_namespace=namespace)
            except (NameError, PydanticUserError) as exc:
                rebuild_error = exc
            if structure_class.__pydantic_complete__:
                continue
            is_generated = concept.structure_class_name == make_qualified_structure_class_name(
                domain_code=concept.domain_code, concept_code=concept.code
            )
            missing_names = sorted(
                {
                    name
                    for field_info in structure_class.model_fields.values()
                    for name in _forward_refs_missing_from(annotation=field_info.annotation, namespace=namespace)
                }
            )
            if not (is_generated and refuses_unresolved_structures and missing_names):
                incomplete_fields: dict[str, Any] = {"concept_ref": concept.concept_ref}
                if rebuild_error is not None:
                    incomplete_fields.update(error_fields(exc=rebuild_error))
                log.debug("The structure class of a concept stays incomplete, and will fail at first use", fields=incomplete_fields)
                continue
            source = concept_sources.get(concept.concept_ref)
            where = f" (declared in '{source}')" if source else ""
            quoted_names = ", ".join(f"'{name}'" for name in missing_names)
            refusals.append(
                f"Concept '{concept.concept_ref}'{where} cannot be built: its structure names the class {quoted_names}, "
                "and no concept it can see has it."
                if len(missing_names) == 1
                else f"Concept '{concept.concept_ref}'{where} cannot be built: its structure names the classes {quoted_names}, "
                "and no concept it can see has them."
            )

        if refusals:
            refusals.append(
                "A structure field may name a concept declared by a bundle already loaded, or by a method package that "
                "one of the bundle's pipes references (`address->domain.Concept`)."
            )
            raise LibraryLoadingError(" ".join(refusals)).with_error_code(CoreCode.METHOD_CONCEPT_INVALID)

    def _detect_concept_cycles(self, concepts: list["Concept"], *, concept_sources: "Mapping[str, str]") -> None:
        """Detect cycles in concept references and raise an error if found.

        Cycles like A -> B -> A are forbidden because they create infinite recursion
        in the data structure. This method traverses each concept's structure fields
        and detects if any chain of references leads back to an already-visited concept.

        Args:
            concepts: List of concepts to check for cycles
            concept_sources: concept_ref -> the bundle that declared it, which the refusal names, since a method
                package's refs carry no address and would not say which package the cycle is in
        """
        # TODO: Refactor to inspect ConceptStructureBlueprint directly (concept_ref and item_concept_ref fields)
        # instead of the generated Python types. This would be more direct and wouldn't depend on how types
        # are generated — a coupling that has already bitten once: respelling the generator's optional fields
        # from `Optional[X]` to `X | None` silently disabled cycle detection entirely.
        class_registry = get_class_registry()

        # Build mappings from class names to concept refs
        class_to_concept: dict[str, str] = {}
        for concept in concepts:
            class_to_concept[concept.structure_class_name] = concept.concept_ref
            class_to_concept[concept.code] = concept.concept_ref

        def get_referenced_concepts(concept: "Concept") -> list[str]:
            """Get concept refs that this concept references in its structure fields."""
            refs: list[str] = []
            structure_class = class_registry.get_class(name=concept.structure_class_name)
            if structure_class is None or not issubclass(structure_class, BaseModel):
                return refs

            def extract_type_names(annotation: type) -> list[str]:
                """Recursively extract type names from possibly nested generic types."""
                if annotation is type(None):
                    return []

                type_names: list[str] = []
                # Branch on `__args__`, not `__origin__`: a PEP 604 union (`X | None`, a `types.UnionType`)
                # carries its members in `__args__` but has **no** `__origin__`, unlike `typing.Optional[X]`.
                # Keying off the origin sent every `X | None` annotation down the simple-type branch, where
                # it has no `__name__` either — so the reference vanished and no cycle was ever found.
                args = getattr(annotation, "__args__", ())

                if args:
                    # Generic or union (Optional[X], X | None, list[X], Union[X, Y], ...): recurse into members.
                    for arg in args:
                        type_names.extend(extract_type_names(arg))
                else:
                    # Simple type, get its name
                    type_name = getattr(annotation, "__name__", None)
                    if type_name:
                        type_names.append(type_name)

                return type_names

            for field_info in structure_class.model_fields.values():
                annotation = field_info.annotation
                if annotation is None:
                    continue

                # Recursively extract all type names from the annotation
                for type_name in extract_type_names(annotation):
                    if type_name in class_to_concept:
                        refs.append(class_to_concept[type_name])

            return refs

        def check_for_cycle(concept_ref: str, *, visiting: set[str], path: list[str]) -> None:
            """Recursively check for cycles starting from concept_ref."""
            if concept_ref in visiting:
                # Found a cycle - build error message
                cycle_start = path.index(concept_ref)
                cycle = [*path[cycle_start:], concept_ref]
                cycle_str = " -> ".join(cycle)
                source = concept_sources.get(concept_ref)
                where = f" (declared in '{source}')" if source else ""
                msg = f"Cycle detected in concept references: {cycle_str}{where}"
                raise LibraryLoadingError(msg).with_error_code(CoreCode.METHOD_CYCLE)

            # Find the concept by ref
            concept = next((c for c in concepts if c.concept_ref == concept_ref), None)
            if concept is None:
                return  # External concept, skip

            visiting.add(concept_ref)
            path.append(concept_ref)

            for ref in get_referenced_concepts(concept):
                check_for_cycle(ref, visiting=visiting, path=path)

            path.pop()
            visiting.remove(concept_ref)

        # Check each concept as a starting point
        for concept in concepts:
            check_for_cycle(concept.concept_ref, visiting=set(), path=[])


def _building_bundle_of(
    *, tree_bundle_ref: TreeBundleRef | None, live_trees: "Mapping[str, MethodTree]", written_tree: MethodTree | None
) -> BuildingBundle:
    """Where a pipe of a crate is built: in the tree written out for it, in a held tree the crate names, or by digest alone.

    A written tree holds none of its tree's bundles and may hold a generated `structures` module, so its own digest is
    not the crate's: the bundle carries the crate's, the one any other process knows the tree by.
    """
    if tree_bundle_ref is None:
        return None
    if written_tree is not None:
        return TreeBundle(tree=written_tree, tree_path=tree_bundle_ref.tree_path, named_digest=tree_bundle_ref.tree_digest)
    live_tree = live_trees.get(tree_bundle_ref.tree_digest)
    if live_tree is None:
        return tree_bundle_ref
    return TreeBundle(tree=live_tree, tree_path=tree_bundle_ref.tree_path)
