import uuid
from graphlib import CycleError, TopologicalSorter
from pathlib import Path
from typing import TYPE_CHECKING

from kajson.class_registry import ClassRegistry
from mthds.package.dependency_resolver import ResolvedDependency, determine_exported_pipes, resolve_all_dependencies
from mthds.package.discovery import find_package_manifest
from mthds.package.exceptions import DependencyResolveError, ManifestError
from mthds.package.manifest.schema import MTHDS_STANDARD_VERSION, MethodsManifest
from pydantic import BaseModel, PydanticUserError, ValidationError
from typing_extensions import override

import pipelex.builder as builder_pkg  # package import — used for __file__ path
from pipelex import log
from pipelex.cli.installed_methods import find_method_by_full_address
from pipelex.core.bundles.pipelex_bundle_blueprint import PipelexBundleBlueprint
from pipelex.core.concepts.concept_blueprint import ConceptBlueprint
from pipelex.core.concepts.concept_factory import ConceptFactory
from pipelex.core.concepts.native.concept_native import NativeConceptCode
from pipelex.core.domains.domain_blueprint import DomainBlueprint
from pipelex.core.domains.domain_factory import DomainFactory
from pipelex.core.interpreter.exceptions import PipelexInterpreterError
from pipelex.core.interpreter.interpreter import PipelexInterpreter
from pipelex.core.pipes.pipe_abstract import PipeAbstract
from pipelex.core.pipes.pipe_factory import PipeFactory
from pipelex.core.qualified_ref import QualifiedRef
from pipelex.core.stuffs.structured_content import StructuredContent
from pipelex.core.validation import report_validation_error
from pipelex.hub import get_class_registry, get_current_library
from pipelex.libraries.concept.exceptions import ConceptLibraryError
from pipelex.libraries.exceptions import (
    LibraryError,
    LibraryLoadingError,
)
from pipelex.libraries.library import Library
from pipelex.libraries.library_crate import LibraryCrate
from pipelex.libraries.library_crate_factory import LibraryCrateFactory
from pipelex.libraries.library_factory import LibraryFactory
from pipelex.libraries.library_manager_abstract import LibraryManagerAbstract
from pipelex.libraries.library_utils import (
    get_pipelex_mthds_files_from_dirs,
)
from pipelex.libraries.pipe.exceptions import PipeLibraryError
from pipelex.libraries.visibility_utils import check_visibility_for_blueprints, make_visibility_checker
from pipelex.system.registries.class_registry_utils import ClassRegistryUtils
from pipelex.system.registries.func_registry_utils import FuncRegistryUtils
from pipelex.tools.misc.semver import SemVerError, parse_constraint, parse_version, version_satisfies

if TYPE_CHECKING:
    from collections.abc import Mapping

    from pipelex.core.concepts.concept import Concept
    from pipelex.core.domains.domain import Domain

MTHDS_METHODS_DIRNAME = ".mthds/methods"


def _find_methods_dirs_from_blueprints(blueprints: list[PipelexBundleBlueprint]) -> list[Path]:
    """Find .mthds/methods/ directories by walking up from blueprint source paths.

    When a bundle file is located outside the CWD (e.g. validating a
    pipelex-cookbook bundle from the pipelex repo), the standard discovery
    only checks CWD/.mthds/methods/ and ~/.mthds/methods/. This function
    walks up ancestor directories of each bundle source path to find
    additional .mthds/methods/ directories.

    Args:
        blueprints: The parsed bundle blueprints (their ``source`` field
            holds the original file path)

    Returns:
        Deduplicated list of existing .mthds/methods/ directories found
    """
    result: list[Path] = []
    seen: set[Path] = set()
    for blueprint in blueprints:
        if not blueprint.source:
            continue
        current = Path(blueprint.source).resolve().parent
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


class LibraryManager(LibraryManagerAbstract):
    def __init__(self):
        # UNTITLED library is the fallback library for all others
        self._libraries: dict[str, Library] = {}
        self._pipe_source_map: dict[str, Path] = {}  # pipe_ref (domain.pipe_code) -> source .mthds file
        self._blueprints: dict[str, list[PipelexBundleBlueprint]] = {}  # library_id -> accumulated blueprints
        self._crate_cache: dict[str, LibraryCrate] = {}  # library_id -> cached crate from get_crate()
        self._loaded_fingerprints: dict[str, set[str]] = {}  # library_id -> set of loaded crate fingerprints

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
            # Remove source map entries for pipes in this library
            for pipe_ref in library.pipe_library.root:
                self._pipe_source_map.pop(pipe_ref, None)
            library.teardown()
        finally:
            self._blueprints.pop(library_id, None)
            self._crate_cache.pop(library_id, None)
            self._loaded_fingerprints.pop(library_id, None)
        return True

    @override
    def teardown(self, library_id: str | None = None) -> None:
        if library_id:
            if not self._pop_and_teardown_library(library_id=library_id):
                msg = f"Trying to teardown a library that does not exist: '{library_id}'"
                raise LibraryError(msg)
            return

        # Same forget-even-on-raise contract as the single-id branch: entries are dropped
        # in the finally even when a library's own teardown raises mid-loop, so no kept
        # entry can poison later open_fresh_library calls on this worker.
        try:
            for lib_id in list(self._libraries):
                self._pop_and_teardown_library(library_id=lib_id)
        finally:
            self._libraries = {}
            self._pipe_source_map = {}
            self._blueprints = {}
            self._crate_cache = {}
            self._loaded_fingerprints = {}

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
            self._libraries[library_id] = the_library

        return library_id, the_library

    @override
    def open_fresh_library(self, library_id: str) -> Library:
        if self._pop_and_teardown_library(library_id=library_id):
            log.warning(
                f"open_fresh_library: tore down pre-existing library '{library_id}' — leftover of an interrupted execution whose cleanup never ran"
            )
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
    def get_pipe_source(self, pipe_code: str) -> Path | None:
        """Get the source file path for a pipe.

        Args:
            pipe_code: The pipe code or pipe_ref (domain.code) to look up.

        Returns:
            Path to the .mthds file the pipe was loaded from, or None if unknown.
        """
        # Direct lookup by pipe_ref
        result = self._pipe_source_map.get(pipe_code)
        if result is not None:
            return result
        # Bare code fallback: search for a key ending with .pipe_code
        if "." not in pipe_code:
            suffix = f".{pipe_code}"
            matches = [path for key, path in self._pipe_source_map.items() if key.endswith(suffix)]
            if len(matches) == 1:
                return matches[0]
        return None

    @override
    def get_crate(self, library_id: str) -> LibraryCrate | None:
        cached = self._crate_cache.get(library_id)
        if cached is not None:
            return cached
        accumulated = self._blueprints.get(library_id)
        if not accumulated:
            return None
        crate = LibraryCrateFactory.make_from_blueprints(blueprints=accumulated)
        self._crate_cache[library_id] = crate
        return crate

    ############################################################
    # Private methods
    ############################################################

    @override
    def load_libraries(
        self,
        library_id: str,
        library_dirs: list[Path] | None = None,
        library_file_paths: list[Path] | None = None,
    ) -> list[PipeAbstract]:
        # Ensure libraries exist for this library_id
        if library_id not in self._libraries:
            msg = f"Trying to load a library that does not exist: '{library_id}'"
            raise LibraryError(msg)

        if not library_dirs:
            library_dirs = []

        all_dirs: list[Path] = []
        all_mthds_paths: list[Path] = []
        all_dirs.extend(library_dirs)
        all_mthds_paths.extend(get_pipelex_mthds_files_from_dirs(set(library_dirs)))

        if library_file_paths:
            all_mthds_paths.extend(library_file_paths)

        # Combine and deduplicate
        seen_absolute_paths: set[str] = set()
        valid_mthds_paths: list[Path] = []
        for mthds_path in all_mthds_paths:
            try:
                absolute_path = str(mthds_path.resolve())
            except (OSError, RuntimeError):
                # For paths that can't be resolved (e.g., in zipped packages), use string representation
                absolute_path = str(mthds_path)

            if absolute_path not in seen_absolute_paths:
                valid_mthds_paths.append(mthds_path)
                seen_absolute_paths.add(absolute_path)

        # Import modules and register in global registries
        # Import from user directories
        for library_dir in all_dirs:
            # Only import files that contain StructuredContent subclasses (uses AST pre-check)
            ClassRegistryUtils.import_modules_in_folder(
                folder_path=library_dir,
                base_class_names=[StructuredContent.__name__],
                force_include_dirs=[Path(builder_pkg.__file__).parent],
            )
            # Only import files that contain @pipe_func decorated functions (uses AST pre-check)
            FuncRegistryUtils.register_funcs_in_folder(
                folder_path=library_dir,
                force_include_dirs=[Path(builder_pkg.__file__).parent],
            )

        # Auto-discover and register all StructuredContent classes from sys.modules
        num_registered = ClassRegistryUtils.auto_register_all_subclasses(
            base_class=StructuredContent,
        )
        log.verbose(f"Auto-registered {num_registered} StructuredContent classes from loaded modules")

        # Load MTHDS files into the specific library
        log.verbose(f"Loading MTHDS files from: {[str(p) for p in valid_mthds_paths]}")
        return self._load_mthds_files_into_library(library_id=library_id, valid_mthds_paths=valid_mthds_paths)

    @override
    def load_libraries_concepts_only(
        self,
        library_id: str,
        library_dirs: list[Path] | None = None,
        library_file_paths: list[Path] | None = None,
    ) -> list["Concept"]:
        """Load only domains and concepts from library directories, skipping pipes.

        This is a lightweight alternative to load_libraries() that only processes
        domains and concepts. It does not load pipes, does not perform pipe validation,
        and does not run library.validate_library().

        Args:
            library_id: The ID of the library to load into
            library_dirs: List of directories containing MTHDS files
            library_file_paths: List of specific MTHDS file paths to load

        Returns:
            List of all concepts that were loaded
        """
        # Ensure libraries exist for this library_id
        if library_id not in self._libraries:
            msg = f"Trying to load a library that does not exist: '{library_id}'"
            raise LibraryError(msg)

        if not library_dirs:
            library_dirs = []

        all_dirs: list[Path] = []
        all_mthds_paths: list[Path] = []
        all_dirs.extend(library_dirs)
        all_mthds_paths.extend(get_pipelex_mthds_files_from_dirs(set(library_dirs)))

        if library_file_paths:
            all_mthds_paths.extend(library_file_paths)

        # Combine and deduplicate
        seen_absolute_paths: set[str] = set()
        valid_mthds_paths: list[Path] = []
        for mthds_path in all_mthds_paths:
            try:
                absolute_path = str(mthds_path.resolve())
            except (OSError, RuntimeError):
                # For paths that can't be resolved (e.g., in zipped packages), use string representation
                absolute_path = str(mthds_path)

            if absolute_path not in seen_absolute_paths:
                valid_mthds_paths.append(mthds_path)
                seen_absolute_paths.add(absolute_path)

        # Import modules and register in global registries
        # Import from user directories - still needed for StructuredContent classes
        for library_dir in all_dirs:
            # Only import files that contain StructuredContent subclasses (uses AST pre-check)
            ClassRegistryUtils.import_modules_in_folder(
                folder_path=library_dir,
                base_class_names=[StructuredContent.__name__],
                force_include_dirs=[Path(builder_pkg.__file__).parent],
            )
            # NOTE: We skip FuncRegistryUtils.register_funcs_in_folder() since we're not loading pipes

        # Auto-discover and register all StructuredContent classes from sys.modules
        num_registered = ClassRegistryUtils.auto_register_all_subclasses(
            base_class=StructuredContent,
        )
        log.debug(f"Auto-registered {num_registered} StructuredContent classes from loaded modules")

        # Load MTHDS files as concepts only (no pipes)
        log.debug(f"Loading concepts only from MTHDS files: {[str(p) for p in valid_mthds_paths]}")
        library = self.get_library(library_id=library_id)
        all_concepts: list[Concept] = []
        for mthds_path in valid_mthds_paths:
            # Track loaded path (resolve if possible)
            try:
                resolved_path = mthds_path.resolve()
            except (OSError, RuntimeError):
                resolved_path = mthds_path
            library.loaded_mthds_paths.append(resolved_path)

            blueprint = PipelexInterpreter.make_pipelex_bundle_blueprint(bundle_path=mthds_path)
            concepts = self.load_concepts_only_from_blueprints(library_id=library_id, blueprints=[blueprint])
            all_concepts.extend(concepts)

        return all_concepts

    @override
    def load_from_crate(self, library_id: str, crate: LibraryCrate) -> list[PipeAbstract]:
        """Load a LibraryCrate into a live Library.

        Fingerprint idempotency: if a crate with the same fingerprint was already loaded
        into this library_id, the load is skipped and an empty list is returned.

        Note: This method does NOT resolve cross-package address-based dependencies.
        Callers must handle dependency loading before calling this method (e.g. via
        _load_address_based_dependencies). The load_from_blueprints method does this
        automatically before delegating here.

        Args:
            library_id: The library to load into
            crate: The LibraryCrate containing qualified blueprints, domain metadata, and source info

        Returns:
            List of all pipes that were loaded, or empty list if already loaded
        """
        # Fingerprint idempotency: skip if this crate was already loaded into this library
        fingerprint = crate.fingerprint
        loaded_set = self._loaded_fingerprints.setdefault(library_id, set())
        if fingerprint in loaded_set:
            log.verbose(f"Crate with fingerprint {fingerprint[:12]}... already loaded into '{library_id}', skipping")
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

        # Resolve forward references in dynamically generated structure classes
        self._rebuild_models_with_forward_refs(all_concepts)

        # Detect cycles in concept references (A -> B -> A is forbidden)
        self._detect_concept_cycles(all_concepts)

        # Precompute domain -> concept local codes mapping (avoids O(N*M) re-parsing per pipe)
        domain_concept_codes: dict[str, list[str]] = {}
        for concept_ref in crate.concepts:
            parsed_concept = QualifiedRef.parse_concept_ref(raw=concept_ref)
            if parsed_concept.domain_path is not None:
                domain_concept_codes.setdefault(parsed_concept.domain_path, []).append(parsed_concept.local_code)

        # Load pipes with domain-filtered concept codes
        all_pipes: list[PipeAbstract] = []
        for pipe_ref, pipe_blueprint in crate.pipes.items():
            parsed = QualifiedRef.parse_pipe_ref(raw=pipe_ref)
            if parsed.domain_path is None:
                msg = f"Crate pipe_ref '{pipe_ref}' must be domain-qualified"
                raise PipeLibraryError(msg)
            domain_code = parsed.domain_path
            pipe_code = parsed.local_code

            concept_codes_for_domain = domain_concept_codes.get(domain_code, [])

            pipe = PipeFactory[PipeAbstract].make_from_blueprint(
                domain_code=domain_code,
                pipe_code=pipe_code,
                blueprint=pipe_blueprint,
                concept_codes_from_the_same_domain=concept_codes_for_domain,
            )
            all_pipes.append(pipe)

            # Track source file for this pipe (used by get_pipe_source)
            source = crate.source_map.get(pipe_ref)
            if source:
                self._pipe_source_map[pipe_ref] = Path(source)

        library.pipe_library.add_pipes(pipes=all_pipes)

        library.validate_library()

        # Only cache fingerprint after the entire load succeeds — if loading fails
        # with an exception, subsequent retries must not be skipped.
        loaded_set.add(fingerprint)
        return all_pipes

    @override
    def load_from_blueprints(self, library_id: str, blueprints: list[PipelexBundleBlueprint]) -> list[PipeAbstract]:
        """Load domains, concepts, and pipes from a list of blueprints.

        Delegates through LibraryCrate: builds a crate from blueprints, then loads from the crate.
        Also accumulates blueprints for later crate retrieval via get_crate().

        Args:
            library_id: The ID of the library to load into
            blueprints: List of parsed MTHDS blueprints to load

        Returns:
            List of all pipes that were loaded
        """
        # Accumulate blueprints for later crate construction via get_crate()
        self._blueprints.setdefault(library_id, []).extend(blueprints)
        self._crate_cache.pop(library_id, None)

        # Discover and load address-based cross-package dependencies before loading pipes
        self._load_address_based_dependencies(
            library_id=library_id,
            blueprints=blueprints,
        )

        # Build the crate (merges, qualifies, detects duplicates)
        crate = LibraryCrateFactory.make_from_blueprints(blueprints=blueprints)

        # Load from crate (domains, concepts, pipes, validation)
        return self.load_from_crate(library_id=library_id, crate=crate)

    @override
    def load_concepts_only_from_blueprints(
        self,
        library_id: str,
        blueprints: list[PipelexBundleBlueprint],
    ) -> list["Concept"]:
        """Load only domains and concepts from blueprints, skipping pipes.

        This is a lightweight alternative to load_from_blueprints() that only processes
        domains and concepts. It does not load pipes, does not perform pipe validation,
        and does not run library.validate_library().

        Args:
            library_id: The ID of the library to load into
            blueprints: List of parsed MTHDS blueprints to load

        Returns:
            List of all concepts that were loaded
        """
        library = self.get_library(library_id=library_id)

        # Load all domains first
        all_domains: list[Domain] = []
        for blueprint in blueprints:
            domain = DomainFactory.make_from_blueprint(
                blueprint=DomainBlueprint(
                    source=blueprint.source,
                    code=blueprint.domain,
                    description=blueprint.description or "",
                    system_prompt=blueprint.system_prompt,
                    main_pipe=blueprint.main_pipe,
                ),
            )
            all_domains.append(domain)
        library.domain_library.add_domains(domains=all_domains)

        # Load concepts (forward references resolved after all are loaded)
        all_concepts = self._load_concepts_from_blueprints(blueprints)
        library.concept_library.add_concepts(concepts=all_concepts)

        # Resolve forward references in dynamically generated structure classes
        self._rebuild_models_with_forward_refs(all_concepts)

        # Detect cycles in concept references (A -> B -> A is forbidden)
        self._detect_concept_cycles(all_concepts)

        library.validate_domain_library_with_libraries()
        library.validate_concept_library_with_libraries()

        return all_concepts

    def _load_concepts_from_blueprints(
        self,
        blueprints: list[PipelexBundleBlueprint],
    ) -> list["Concept"]:
        """Load concepts from blueprints in topological order based on refines dependencies.

        Concepts that refine other concepts are loaded after their base concepts,
        ensuring the base class is always registered before the refining class.
        Forward references between concepts (for structure fields) are resolved
        later by _rebuild_models_with_forward_refs().

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
                        if existing_source == new_source:
                            msg = (
                                f"Concept '{concept_ref}' is declared twice in the same bundle file: '{existing_source}'. "
                                "Please remove the duplicate declaration."
                            )
                        else:
                            msg = (
                                f"Concept '{concept_ref}' is declared in two different bundle files: "
                                f"'{existing_source}' and '{new_source}'. "
                                "Please remove one of the declarations or rename one of the concepts."
                            )
                        raise ConceptLibraryError(msg)
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
            parsed = QualifiedRef.parse_concept_ref(raw=concept_ref)
            if parsed.domain_path is None:
                msg = f"Crate concept_ref '{concept_ref}' must be domain-qualified"
                raise ConceptLibraryError(msg)
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
            raise LibraryLoadingError(msg) from exc

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

    def _load_mthds_files_into_library(self, library_id: str, valid_mthds_paths: list[Path]) -> list[PipeAbstract]:
        """Load MTHDS files into a specific library.

        This method:
        1. Parses blueprints from MTHDS files
        2. Finds and loads dependency packages (if manifest has dependencies with local paths)
        3. Loads blueprints into the specified library

        Args:
            library_id: The ID of the library to load into
            valid_mthds_paths: List of MTHDS file paths to load
        """
        blueprints: list[PipelexBundleBlueprint] = []
        for mthds_file_path in valid_mthds_paths:
            try:
                blueprint = PipelexInterpreter.make_pipelex_bundle_blueprint(bundle_path=mthds_file_path)
                blueprint.source = str(mthds_file_path)
            except FileNotFoundError as file_not_found_error:
                msg = f"Could not find MTHDS bundle at '{mthds_file_path}'"
                raise LibraryLoadingError(msg) from file_not_found_error
            except PipelexInterpreterError as interpreter_error:
                # Forward BLUEPRINT validation errors from interpreter
                msg = f"Could not load MTHDS bundle from '{mthds_file_path}' because of: {interpreter_error.message}"
                raise LibraryLoadingError(
                    message=msg,
                    blueprint_validation_errors=interpreter_error.validation_errors,
                ) from interpreter_error
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
            return self.load_from_blueprints(library_id=library_id, blueprints=blueprints)
        except ValidationError as validation_error:
            validation_error_msg = report_validation_error(category="mthds", validation_error=validation_error)
            msg = f"Could not load blueprints from {[str(pth) for pth in valid_mthds_paths]} because of: {validation_error_msg}"
            raise LibraryError(
                message=msg,
            ) from validation_error

    def _warn_if_mthds_version_unsatisfied(
        self,
        mthds_version_constraint: str,
        package_address: str,
    ) -> None:
        """Emit a warning if the current MTHDS standard version does not satisfy the package's constraint."""
        try:
            constraint = parse_constraint(mthds_version_constraint)
            current_version = parse_version(MTHDS_STANDARD_VERSION)
        except SemVerError as exc:
            log.warning(f"Could not parse mthds_version constraint '{mthds_version_constraint}' for package '{package_address}': {exc}")
            return

        if not version_satisfies(current_version, constraint):
            log.warning(
                f"Package '{package_address}' requires MTHDS standard version "
                f"'{mthds_version_constraint}', but the current version is "
                f"'{MTHDS_STANDARD_VERSION}'. Some features may not work correctly."
            )

    def _check_package_visibility(
        self,
        blueprints: list[PipelexBundleBlueprint],
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
            log.warning(f"Could not parse METHODS.toml: {exc.message}")
            # Still enforce reserved domains even when manifest is unparseable
            checker = make_visibility_checker(manifest=None, blueprints=blueprints)
            reserved_errors = checker.validate_reserved_domains()
            if reserved_errors:
                error_messages = [err.message for err in reserved_errors]
                joined_errors = "\n  - ".join(error_messages)
                msg = f"Reserved domain violations found:\n  - {joined_errors}"
                raise LibraryLoadingError(msg) from exc
            return None

        if manifest is None:
            # Still enforce reserved domains even for standalone bundles
            checker = make_visibility_checker(manifest=None, blueprints=blueprints)
            reserved_errors = checker.validate_reserved_domains()
            if reserved_errors:
                error_messages = [err.message for err in reserved_errors]
                joined_errors = "\n  - ".join(error_messages)
                msg = f"Reserved domain violations found:\n  - {joined_errors}"
                raise LibraryLoadingError(msg)
            return None

        visibility_errors = check_visibility_for_blueprints(manifest=manifest, blueprints=blueprints)
        if visibility_errors:
            error_messages = [err.message for err in visibility_errors]
            joined_errors = "\n  - ".join(error_messages)
            msg = f"Package visibility violations found:\n  - {joined_errors}"
            raise LibraryLoadingError(msg)

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
            raise LibraryLoadingError(msg) from exc

        library = self.get_library(library_id=library_id)

        for resolved_dep in resolved_deps:
            self._load_single_dependency(
                library=library,
                resolved_dep=resolved_dep,
            )

        # Wire concept resolver after all deps are loaded so cross-package
        # refinement checks can traverse into child libraries
        library.concept_library.set_concept_resolver(library.resolve_concept)

    def _load_single_dependency(
        self,
        library: Library,
        resolved_dep: ResolvedDependency,
    ) -> None:
        """Load a single resolved dependency into an isolated child library.

        Creates a child Library for the dependency, loads domains/concepts/pipes
        into it, registers it in library.dependency_libraries, and adds aliased
        entries to the main library for backward-compatible cross-package lookups.

        Args:
            library: The main library to load into
            resolved_dep: The resolved dependency info
        """
        alias = resolved_dep.alias

        # Parse dependency blueprints
        dep_blueprints: list[PipelexBundleBlueprint] = []
        for mthds_path in resolved_dep.mthds_files:
            try:
                blueprint = PipelexInterpreter.make_pipelex_bundle_blueprint(bundle_path=mthds_path)
                blueprint.source = str(mthds_path)
            except (FileNotFoundError, PipelexInterpreterError) as exc:
                log.warning(f"Could not parse dependency '{alias}' bundle '{mthds_path}': {exc}")
                continue
            dep_blueprints.append(blueprint)

        if not dep_blueprints:
            log.warning(f"No valid blueprints found for dependency '{alias}'")
            return

        # Warn if the dependency requires a newer MTHDS standard version
        if resolved_dep.manifest is not None and resolved_dep.manifest.mthds_version is not None:
            self._warn_if_mthds_version_unsatisfied(
                mthds_version_constraint=resolved_dep.manifest.mthds_version,
                package_address=resolved_dep.address,
            )

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

        # Load concepts into child library
        dep_concepts = self._load_concepts_from_blueprints(dep_blueprints)
        child_library.concept_library.add_concepts(concepts=dep_concepts)

        # Collect main_pipes for auto-export
        main_pipes: set[str] = set()
        for blueprint in dep_blueprints:
            if blueprint.main_pipe:
                main_pipes.add(blueprint.main_pipe)

        # Determine if we filter by exports or load all.
        # exported_pipe_codes is None when no manifest exists (all pipes public),
        # or a set (possibly empty) when a manifest defines exports.
        if resolved_dep.exported_pipe_codes is None:
            # No manifest: all pipes are public, no filtering
            has_exports = False
            all_exported: set[str] = set()
        else:
            # Manifest exists: filter to exported pipes + main_pipes
            has_exports = True
            all_exported = resolved_dep.exported_pipe_codes | main_pipes
            # Synthetic helpers from build-time elaboration (e.g. `<code>__draft_text` and
            # `<code>__structure` produced by `structuring_method = preliminary_text`) are
            # private to their parent pipe and never listed in the manifest. When the parent
            # is exported, its helpers must travel with it — otherwise the wrapping
            # PipeSequence references unresolved pipe codes at runtime.
            # Note: `parent_pipe_code` and `synthetic_code` are bare codes within a single
            # bundle — `BundleElaborator` writes them that way today. If two bundles in the
            # same dep ever ship the same bare pipe code, this lookup would conflate their
            # helpers. The downstream factory would then fail on duplicate registration, so
            # the failure mode is loud rather than silent.
            synthetic_helpers: set[str] = set()
            for blueprint in dep_blueprints:
                if not blueprint.elaboration_metadata:
                    continue
                for synthetic_code, meta in blueprint.elaboration_metadata.items():
                    if meta.parent_pipe_code in all_exported:
                        synthetic_helpers.add(synthetic_code)
            all_exported |= synthetic_helpers

        # Temporarily register dep concepts in main library for pipe construction
        # (PipeFactory resolves concepts through the hub's current library)
        temp_concept_refs: list[str] = []
        for concept in dep_concepts:
            if not library.concept_library.is_concept_exists(concept_ref=concept.concept_ref):
                library.concept_library.add_new_concept(concept=concept)
                temp_concept_refs.append(concept.concept_ref)

        # Load exported pipes into child library, ensuring temp concepts are
        # always cleaned up even if an unexpected exception occurs
        try:
            concept_codes = [concept.code for concept in dep_concepts]
            for blueprint in dep_blueprints:
                if blueprint.pipe is None:
                    continue
                for pipe_code, pipe_blueprint in blueprint.pipe.items():
                    # If manifest has exports, only load exported pipes
                    if has_exports and pipe_code not in all_exported:
                        continue
                    try:
                        pipe = PipeFactory[PipeAbstract].make_from_blueprint(
                            domain_code=blueprint.domain,
                            pipe_code=pipe_code,
                            blueprint=pipe_blueprint,
                            concept_codes_from_the_same_domain=concept_codes,
                        )
                        child_library.pipe_library.add_new_pipe(pipe=pipe)
                    except (PipeLibraryError, ValidationError) as exc:
                        log.warning(f"Could not load dependency '{alias}' pipe '{pipe_code}': {exc}")
        finally:
            # Remove temporary concept entries from main library
            library.concept_library.remove_concepts_by_concept_refs(concept_refs=temp_concept_refs)

        # Register child library for isolation
        library.dependency_libraries[alias] = child_library

        # Add aliased entries to main library for backward-compatible cross-package lookups
        for concept in dep_concepts:
            library.concept_library.add_dependency_concept(alias=alias, concept=concept)

        for pipe in child_library.pipe_library.get_pipes():
            library.pipe_library.add_dependency_pipe(alias=alias, pipe=pipe)

        log.verbose(f"Loaded dependency '{alias}': {len(dep_concepts)} concepts, pipes from {len(dep_blueprints)} bundles")

    def _load_address_based_dependencies(
        self,
        library_id: str,
        blueprints: list[PipelexBundleBlueprint],
    ) -> None:
        """Scan blueprints for cross-package pipe refs with address-based aliases and load them.

        Collects all cross-package pipe references from controller blueprints
        (sequences, batches, conditions, parallels), identifies those whose
        alias contains '/' (i.e. a full package address), and loads each
        unique address-based dependency.

        Also searches for .mthds/methods/ directories relative to the bundle
        source path, walking up ancestor directories to find installed methods
        even when the CWD differs from the bundle's project root.

        Args:
            library_id: The library to load into
            blueprints: The parsed bundle blueprints to scan
        """
        library = self.get_library(library_id=library_id)

        # Collect unique address-based aliases from all pipe references
        address_aliases: set[str] = set()
        for blueprint in blueprints:
            for pipe_ref_str, _context in blueprint.collect_pipe_references():
                if QualifiedRef.has_cross_package_prefix(pipe_ref_str):
                    alias, _remainder = QualifiedRef.split_cross_package_ref(pipe_ref_str)
                    if QualifiedRef.is_address_based_alias(alias):
                        address_aliases.add(alias)

        if not address_aliases:
            return

        # Derive extra search dirs from bundle source paths
        extra_search_dirs = _find_methods_dirs_from_blueprints(blueprints)

        for full_address in sorted(address_aliases):
            if full_address in library.dependency_libraries:
                continue
            self._load_address_based_dependency(
                library=library,
                full_address=full_address,
                extra_search_dirs=extra_search_dirs,
            )

        # Wire concept resolver after all deps are loaded
        if address_aliases:
            library.concept_library.set_concept_resolver(library.resolve_concept)

    def _load_address_based_dependency(
        self,
        library: "Library",
        full_address: str,
        extra_search_dirs: list[Path] | None = None,
    ) -> bool:
        """Load an installed method package on demand using its full address.

        Discovers the matching installed method, builds a ResolvedDependency,
        and delegates to _load_single_dependency() to load it as a child
        library with the full address as alias.

        Args:
            library: The main library to load into
            full_address: The full package address (e.g. "github.com/Pipelex/methods/documents")
            extra_search_dirs: Additional .mthds/methods/ directories to scan

        Returns:
            True if the dependency was successfully loaded, False otherwise
        """
        installed = find_method_by_full_address(full_address=full_address, extra_search_dirs=extra_search_dirs)
        if installed is None:
            log.warning(f"No installed method found for address '{full_address}'")
            return False

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
            resolved_dep=resolved_dep,
        )

        return True

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
    def _remove_from_blueprint(self, library_id: str, blueprint: PipelexBundleBlueprint) -> None:
        self._remove_pipes_from_blueprint(blueprint=blueprint)
        self._remove_concepts_from_blueprint(blueprint=blueprint)

    @override
    def _remove_from_blueprints(self, library_id: str, blueprints: list[PipelexBundleBlueprint]) -> None:
        for blueprint in blueprints:
            self._remove_from_blueprint(library_id=library_id, blueprint=blueprint)

    def _rebuild_models_with_forward_refs(self, concepts: list["Concept"]) -> None:
        """Rebuild Pydantic models to resolve forward references.

        When dynamically generated classes have forward references (e.g., `customer: "Customer"`),
        Python's get_type_hints() cannot resolve them because the referenced classes are not
        in any accessible namespace. This method builds a namespace with all structure classes
        and calls model_rebuild() to resolve the forward references.

        Args:
            concepts: List of concepts that were just loaded
        """
        # Build namespace with all structure class names
        namespace: dict[str, type] = {}
        class_registry = get_class_registry()

        for concept in concepts:
            structure_class = class_registry.get_class(name=concept.structure_class_name)
            if structure_class is not None:
                namespace[concept.structure_class_name] = structure_class
                # Also add by concept code in case the forward ref uses the code
                namespace[concept.code] = structure_class

        # Rebuild each model with the shared namespace
        for concept in concepts:
            structure_class = class_registry.get_class(name=concept.structure_class_name)
            if structure_class is not None and issubclass(structure_class, BaseModel):
                try:
                    structure_class.model_rebuild(_types_namespace=namespace)
                except (NameError, PydanticUserError) as exc:
                    log.debug(f"Could not rebuild model for {concept.concept_ref}: {exc}")

    def _detect_concept_cycles(self, concepts: list["Concept"]) -> None:
        """Detect cycles in concept references and raise an error if found.

        Cycles like A -> B -> A are forbidden because they create infinite recursion
        in the data structure. This method traverses each concept's structure fields
        and detects if any chain of references leads back to an already-visited concept.

        Args:
            concepts: List of concepts to check for cycles
        """
        # TODO: Refactor to inspect ConceptStructureBlueprint directly (concept_ref and item_concept_ref fields)
        # instead of the generated Python types. This would be more direct and wouldn't depend on
        # how types are generated (e.g., Optional wrappers for non-required fields).
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
                origin = getattr(annotation, "__origin__", None)
                args = getattr(annotation, "__args__", ())

                if origin is None:
                    # Simple type, get its name
                    type_name = getattr(annotation, "__name__", None)
                    if type_name:
                        type_names.append(type_name)
                else:
                    # Generic type (like Optional[X], list[X], Union[X, Y], etc.)
                    # Recursively extract from all type arguments
                    for arg in args:
                        type_names.extend(extract_type_names(arg))

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

        def check_for_cycle(concept_ref: str, visiting: set[str], path: list[str]) -> None:
            """Recursively check for cycles starting from concept_ref."""
            if concept_ref in visiting:
                # Found a cycle - build error message
                cycle_start = path.index(concept_ref)
                cycle = [*path[cycle_start:], concept_ref]
                cycle_str = " -> ".join(cycle)
                msg = f"Cycle detected in concept references: {cycle_str}"
                raise LibraryLoadingError(msg)

            # Find the concept by ref
            concept = next((c for c in concepts if c.concept_ref == concept_ref), None)
            if concept is None:
                return  # External concept, skip

            visiting.add(concept_ref)
            path.append(concept_ref)

            for ref in get_referenced_concepts(concept):
                check_for_cycle(ref, visiting, path)

            path.pop()
            visiting.remove(concept_ref)

        # Check each concept as a starting point
        for concept in concepts:
            check_for_cycle(concept.concept_ref, set(), [])
