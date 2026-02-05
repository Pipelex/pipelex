import uuid
from graphlib import CycleError, TopologicalSorter
from pathlib import Path
from typing import TYPE_CHECKING

from kajson.kajson_manager import KajsonManager
from pydantic import BaseModel, ValidationError
from typing_extensions import override

from pipelex import log
from pipelex.builder import builder
from pipelex.core.bundles.pipelex_bundle_blueprint import PipelexBundleBlueprint
from pipelex.core.concepts.concept_factory import ConceptFactory
from pipelex.core.concepts.native.concept_native import NativeConceptCode
from pipelex.core.domains.domain import Domain
from pipelex.core.domains.domain_blueprint import DomainBlueprint
from pipelex.core.domains.domain_factory import DomainFactory
from pipelex.core.interpreter.exceptions import PipelexInterpreterError
from pipelex.core.interpreter.interpreter import PipelexInterpreter
from pipelex.core.pipes.pipe_abstract import PipeAbstract
from pipelex.core.pipes.pipe_factory import PipeFactory
from pipelex.core.stuffs.structured_content import StructuredContent
from pipelex.core.validation import report_validation_error
from pipelex.hub import get_current_library
from pipelex.libraries.exceptions import (
    LibraryError,
    LibraryLoadingError,
)
from pipelex.libraries.library import Library
from pipelex.libraries.library_factory import LibraryFactory
from pipelex.libraries.library_manager_abstract import LibraryManagerAbstract
from pipelex.libraries.library_utils import (
    get_pipelex_plx_files_from_dirs,
)
from pipelex.system.registries.class_registry_utils import ClassRegistryUtils
from pipelex.system.registries.func_registry_utils import FuncRegistryUtils

if TYPE_CHECKING:
    from pipelex.core.concepts.concept import Concept
    from pipelex.core.concepts.concept_blueprint import ConceptBlueprint
    from pipelex.core.domains.domain import Domain


class LibraryManager(LibraryManagerAbstract):
    def __init__(self):
        # UNTITLED library is the fallback library for all others
        self._libraries: dict[str, Library] = {}
        self._pipe_source_map: dict[str, Path] = {}  # pipe_code -> source .plx file

    ############################################################
    # Manager lifecycle
    ############################################################
    def generate_library_id(self) -> str:
        return str(uuid.uuid4())

    @override
    def setup(self) -> None:
        pass

    @override
    def teardown(self, library_id: str | None = None) -> None:
        if library_id:
            if library_id not in self._libraries:
                msg = f"Trying to teardown a library that does not exist: '{library_id}'"
                raise LibraryError(msg)
            library = self._libraries[library_id]
            # Remove source map entries for pipes in this library
            for pipe_code in library.pipe_library.root:
                self._pipe_source_map.pop(pipe_code, None)
            library.teardown()
            del self._libraries[library_id]
            return

        for library in self._libraries.values():
            library.teardown()
        self._libraries = {}
        self._pipe_source_map = {}

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

    ############################################################
    # Public library accessors
    ############################################################

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
            pipe_code: The pipe code to look up.

        Returns:
            Path to the .plx file the pipe was loaded from, or None if unknown.
        """
        return self._pipe_source_map.get(pipe_code)

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
        all_plx_paths: list[Path] = []
        all_dirs.extend(library_dirs)
        all_plx_paths.extend(get_pipelex_plx_files_from_dirs(set(library_dirs)))

        if library_file_paths:
            all_plx_paths.extend(library_file_paths)

        # Combine and deduplicate
        seen_absolute_paths: set[str] = set()
        valid_plx_paths: list[Path] = []
        for plx_path in all_plx_paths:
            try:
                absolute_path = str(plx_path.resolve())
            except (OSError, RuntimeError):
                # For paths that can't be resolved (e.g., in zipped packages), use string representation
                absolute_path = str(plx_path)

            if absolute_path not in seen_absolute_paths:
                valid_plx_paths.append(plx_path)
                seen_absolute_paths.add(absolute_path)

        # Import modules and register in global registries
        # Import from user directories
        for library_dir in all_dirs:
            # Only import files that contain StructuredContent subclasses (uses AST pre-check)
            ClassRegistryUtils.import_modules_in_folder(
                folder_path=str(library_dir),
                base_class_names=[StructuredContent.__name__],
                force_include_dirs=[str(Path(builder.__file__).parent)],
            )
            # Only import files that contain @pipe_func decorated functions (uses AST pre-check)
            FuncRegistryUtils.register_funcs_in_folder(
                folder_path=str(library_dir),
                force_include_dirs=[str(Path(builder.__file__).parent)],
            )

        # Auto-discover and register all StructuredContent classes from sys.modules
        num_registered = ClassRegistryUtils.auto_register_all_subclasses(
            base_class=StructuredContent,
        )
        log.debug(f"Auto-registered {num_registered} StructuredContent classes from loaded modules")

        # Load PLX files into the specific library
        log.debug(f"Loading plx files from: {[str(p) for p in valid_plx_paths]}")
        return self._load_plx_files_into_library(library_id=library_id, valid_plx_paths=valid_plx_paths)

    @override
    def load_from_blueprints(self, library_id: str, blueprints: list[PipelexBundleBlueprint]) -> list[PipeAbstract]:
        """Load domains, concepts, and pipes from a list of blueprints.

        Args:
            library_id: The ID of the library to load into
            blueprints: List of parsed PLX blueprints to load

        Returns:
            List of all pipes that were loaded
        """
        library = self.get_library(library_id=library_id)
        all_pipes: list[PipeAbstract] = []

        # Load all domains first
        all_domains: list[Domain] = []
        for blueprint in blueprints:
            domain = DomainFactory.make_from_blueprint(
                blueprint=DomainBlueprint(
                    source=blueprint.source,
                    code=blueprint.domain,
                    description=blueprint.description or "",
                    system_prompt=blueprint.system_prompt,
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

        # Load all pipes
        for blueprint in blueprints:
            pipes: list[PipeAbstract] = []
            if blueprint.pipe is not None:
                for pipe_code, pipe_blueprint in blueprint.pipe.items():
                    pipe = PipeFactory[PipeAbstract].make_from_blueprint(
                        domain_code=blueprint.domain,
                        pipe_code=pipe_code,
                        blueprint=pipe_blueprint,
                        concept_codes_from_the_same_domain=[the_concept.code for the_concept in all_concepts],
                    )
                    pipes.append(pipe)
                    # Track source file for this pipe
                    if blueprint.source:
                        self._pipe_source_map[pipe_code] = Path(blueprint.source)
            all_pipes.extend(pipes)

        library.pipe_library.add_pipes(pipes=all_pipes)

        library.validate_library()
        return all_pipes

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
            blueprints: List of parsed PLX blueprints to load

        Returns:
            List of loaded concepts
        """
        # Step 1: Collect all concept entries with metadata
        ref_to_entry: dict[str, tuple[str, str, ConceptBlueprint | str]] = {}

        for blueprint in blueprints:
            if blueprint.concept is not None:
                for concept_code, concept_blueprint in blueprint.concept.items():
                    concept_ref = ConceptFactory.make_concept_ref_with_domain(
                        domain_code=blueprint.domain,
                        concept_code=concept_code,
                    )
                    ref_to_entry[concept_ref] = (
                        blueprint.domain,
                        concept_code,
                        concept_blueprint,
                    )

        # Step 2: Build dependency graph and topologically sort using graphlib
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

        # Step 3: Get sorted order (raises CycleError if cycles detected)
        try:
            sorted_refs = list(sorter.static_order())
        except CycleError as exc:
            msg = f"Cycle detected in concept refines dependencies: {exc.args[1]}"
            raise LibraryLoadingError(msg) from exc

        # Step 4: Load concepts in topological order
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

    def _load_plx_files_into_library(self, library_id: str, valid_plx_paths: list[Path]) -> list[PipeAbstract]:
        """Load PLX files into a specific library.

        This method:
        1. Parses blueprints from PLX files
        2. Loads blueprints into the specified library

        Args:
            library_id: The ID of the library to load into
            valid_plx_paths: List of PLX file paths to load
        """
        blueprints: list[PipelexBundleBlueprint] = []
        for plx_file_path in valid_plx_paths:
            try:
                blueprint = PipelexInterpreter.make_pipelex_bundle_blueprint(bundle_path=plx_file_path)
                blueprint.source = str(plx_file_path)
            except FileNotFoundError as file_not_found_error:
                msg = f"Could not find PLX bundle at '{plx_file_path}'"
                raise LibraryLoadingError(msg) from file_not_found_error
            except PipelexInterpreterError as interpreter_error:
                # Forward BLUEPRINT validation errors from interpreter
                msg = f"Could not load PLX bundle from '{plx_file_path}' because of: {interpreter_error.message}"
                raise LibraryLoadingError(
                    message=msg,
                    blueprint_validation_errors=interpreter_error.validation_errors,
                ) from interpreter_error
            blueprints.append(blueprint)

        # Store resolved absolute paths for duplicate detection in the library
        library = self.get_library(library_id=library_id)
        for plx_file_path in valid_plx_paths:
            try:
                resolved_path = plx_file_path.resolve()
            except (OSError, RuntimeError):
                resolved_path = plx_file_path
            library.loaded_plx_paths.append(resolved_path)

        try:
            return self.load_from_blueprints(library_id=library_id, blueprints=blueprints)
        except ValidationError as validation_error:
            validation_error_msg = report_validation_error(category="plx", validation_error=validation_error)
            msg = f"Could not load blueprints from {[str(pth) for pth in valid_plx_paths]} because of: {validation_error_msg}"
            raise LibraryError(
                message=msg,
            ) from validation_error

    def _remove_pipes_from_blueprint(self, blueprint: PipelexBundleBlueprint) -> None:
        library = self.get_current_library()
        if blueprint.pipe is not None:
            library.pipe_library.remove_pipes_by_codes(pipe_codes=list(blueprint.pipe.keys()))

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
        class_registry = KajsonManager.get_class_registry()

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
                except Exception as exc:
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
        class_registry = KajsonManager.get_class_registry()

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
