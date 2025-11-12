from pathlib import Path
from typing import TYPE_CHECKING

from pydantic import ValidationError
from typing_extensions import override

from pipelex import log
from pipelex.core.bundles.pipelex_bundle_blueprint import PipelexBundleBlueprint
from pipelex.core.concepts.concept_factory import ConceptFactory
from pipelex.core.concepts.exceptions import ConceptDefinitionError
from pipelex.core.domains.domain import Domain
from pipelex.core.domains.domain_blueprint import DomainBlueprint
from pipelex.core.domains.domain_factory import DomainFactory
from pipelex.core.domains.exceptions import DomainDefinitionError
from pipelex.core.interpreter import PipelexInterpreter
from pipelex.core.pipe_errors import PipeDefinitionError
from pipelex.core.pipes.pipe_abstract import PipeAbstract
from pipelex.core.pipes.pipe_factory import PipeFactory
from pipelex.core.stuffs.structured_content import StructuredContent
from pipelex.core.validation import report_validation_error
from pipelex.hub import get_current_library_id
from pipelex.libraries.exceptions import (
    ConceptLibraryError,
    LibraryError,
    LibraryLoadingError,
    PipeLibraryError,
)
from pipelex.libraries.library import Library
from pipelex.libraries.library_factory import LibraryFactory
from pipelex.libraries.library_ids import SpecialLibraryId
from pipelex.libraries.library_manager_abstract import LibraryManagerAbstract
from pipelex.libraries.library_utils import (
    get_pipelex_package_dir_for_imports,
    get_pipelex_plx_files_from_dirs,
    get_pipelex_plx_files_from_package,
)
from pipelex.system.configuration.config_loader import config_manager
from pipelex.system.registries.class_registry_utils import ClassRegistryUtils
from pipelex.system.registries.func_registry import func_registry
from pipelex.system.registries.func_registry_utils import FuncRegistryUtils
from pipelex.types import StrEnum

if TYPE_CHECKING:
    from pipelex.core.concepts.concept import Concept
    from pipelex.core.domains.domain import Domain


class LibraryComponent(StrEnum):
    CONCEPT = "concept"
    PIPE = "pipe"

    @property
    def error_class(self) -> type[LibraryError]:
        match self:
            case LibraryComponent.CONCEPT:
                return ConceptLibraryError
            case LibraryComponent.PIPE:
                return PipeLibraryError


class LibraryManager(LibraryManagerAbstract):
    def __init__(self):
        # UNTITLED library is the fallback library for all others
        self._libraries: dict[str, Library] = {}
        self.loaded_plx_paths: list[str] = []

    ############################################################
    # Manager lifecycle
    ############################################################
    @override
    def setup(self) -> None:
        self._libraries.clear()
        # Create and initialize UNTITLED library with base PLX files
        self.open_library(library_id=SpecialLibraryId.UNTITLED)

    @override
    def teardown(self) -> None:
        for library in self._libraries.values():
            library.teardown()
        self._libraries.clear()

    @override
    def reset(self) -> None:
        self.teardown()
        self.setup()

    @override
    def open_library(self, library_id: str) -> Library:
        """Open a library with the given library_id. Creates it if it doesn't exist."""
        if library_id not in self._libraries:
            self._libraries[library_id] = LibraryFactory.make_empty()
        return self._libraries[library_id]

    ############################################################
    # Public library accessors
    ############################################################

    @override
    def set_library(self, library_id: str, library: Library) -> None:
        if library_id not in self._libraries:
            msg = f"Library '{library_id}' does not exist"
            raise LibraryError(msg)
        self._libraries[library_id] = library

    @override
    def get_library(self, library_id: str | None = None) -> Library:
        """Get the library with the given library_id. Returns the UNTITLED library if no library_id is provided."""
        if library_id is None:
            library_id = get_current_library_id()
        if library_id not in self._libraries:
            msg = f"Library '{library_id}' does not exist"
            raise LibraryError(msg)
        return self._libraries[library_id]

    ############################################################
    # Private methods
    ############################################################

    @override
    def load_libraries(
        self,
        library_id: str,
        library_dirs: list[Path] | None = None,
        library_file_paths: list[Path] | None = None,
        load_user_dirs: bool = True,
        load_pipelex_dirs: bool = True,
    ) -> None:
        # Ensure libraries exist for this library_id
        if library_id not in self._libraries:
            msg = f"Trying to load a library that does not exist: '{library_id}'"
            raise LibraryError(msg)

        all_dirs: list[Path] = []
        all_plx_paths: list[Path] = []
        if load_user_dirs or (library_dirs is None and library_file_paths is None):
            all_dirs.append(Path(config_manager.local_root_dir))
            all_plx_paths.extend(get_pipelex_plx_files_from_dirs({Path(config_manager.local_root_dir)}))
        if load_pipelex_dirs:
            all_dirs.extend(get_pipelex_plx_files_from_package())
            all_plx_paths.extend(get_pipelex_plx_files_from_package())

        if library_dirs:
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
            )
            # Only import files that contain @pipe_func decorated functions (uses AST pre-check)
            FuncRegistryUtils.register_funcs_in_folder(
                folder_path=str(library_dir),
            )

        # Import from pipelex package
        # Always directly import critical builder modules first (works in all installation modes)
        log.verbose("About to import pipelex.builder modules for @pipe_func registration")
        self._import_pipelex_modules_directly()

        # Verify critical functions were registered
        # TODO: This should be a Unit test
        critical_functions = ["create_concept_spec", "assemble_pipelex_bundle_spec"]
        for func_name in critical_functions:
            if func_registry.has_function(func_name):
                log.verbose(f"✓ Function '{func_name}' successfully registered")
            else:
                log.error(f"✗ Function '{func_name}' NOT registered - this will cause errors!")

        # Then try filesystem-based scanning if package is accessible (for completeness)
        pipelex_pkg_dir = get_pipelex_package_dir_for_imports()
        if pipelex_pkg_dir:
            log.verbose(f"Additionally scanning pipelex package filesystem: {pipelex_pkg_dir}")
            ClassRegistryUtils.import_modules_in_folder(
                folder_path=str(pipelex_pkg_dir),
                base_class_names=[StructuredContent.__name__],
            )
            FuncRegistryUtils.register_funcs_in_folder(
                folder_path=str(pipelex_pkg_dir),
            )

        # Auto-discover and register all StructuredContent classes from sys.modules
        num_registered = ClassRegistryUtils.auto_register_all_subclasses(
            base_class=StructuredContent,
        )
        log.debug(f"Auto-registered {num_registered} StructuredContent classes from loaded modules")

        # Load PLX files into the specific library
        self._load_plx_files_into_library(library_id=library_id, valid_plx_paths=valid_plx_paths)

    ############################################################
    # Private helper methods
    ############################################################

    @override
    def load_from_blueprints(self, library_id: str, blueprints: list[PipelexBundleBlueprint]) -> list[PipeAbstract]:
        """Load domains, concepts, and pipes from a list of blueprints.

        Args:
            library_id: The ID of the library to load into
            blueprints: List of parsed PLX blueprints to load

        Returns:
            List of all pipes that were loaded
        """
        library = self.get_library()
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

        # Load all concepts second
        all_concepts: list[Concept] = []
        for blueprint in blueprints:
            if blueprint.concept is not None:
                concepts: list[Concept] = []
                for concept_code, concept_blueprint_or_description in blueprint.concept.items():
                    concept = ConceptFactory.make_from_blueprint_or_description(
                        domain=blueprint.domain,
                        concept_code=concept_code,
                        concept_codes_from_the_same_domain=list(blueprint.concept.keys()),
                        concept_blueprint_or_description=concept_blueprint_or_description,
                    )
                    concepts.append(concept)
                all_concepts.extend(concepts)
        library.concept_library.add_concepts(concepts=all_concepts)

        # Load all pipes third
        for blueprint in blueprints:
            try:
                pipes: list[PipeAbstract] = []
                if blueprint.pipe is not None:
                    for pipe_name, pipe_blueprint in blueprint.pipe.items():
                        pipe = PipeFactory.make_from_blueprint(
                            domain=blueprint.domain,
                            pipe_code=pipe_name,
                            blueprint=pipe_blueprint,
                            concept_codes_from_the_same_domain=list(blueprint.concept.keys()) if blueprint.concept else None,
                        )
                        pipes.append(pipe)
                all_pipes.extend(pipes)
            except PipeDefinitionError as pipe_def_error:
                pipe_def_error.source = blueprint.source
                raise pipe_def_error from pipe_def_error

        library.pipe_library.add_pipes(pipes=all_pipes)

        return all_pipes

    def _load_plx_files_into_library(self, library_id: str, valid_plx_paths: list[Path]) -> None:
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
                blueprint = PipelexInterpreter(file_path=plx_file_path).make_pipelex_bundle_blueprint()
                blueprint.source = str(plx_file_path)
            except FileNotFoundError as file_not_found_error:
                msg = f"Could not find PLX bundle at '{plx_file_path}'"
                raise LibraryLoadingError(msg) from file_not_found_error
            except PipeDefinitionError as pipe_def_error:
                msg = f"Could not load PLX bundle from '{plx_file_path}' because of: {pipe_def_error}"
                raise LibraryLoadingError(msg) from pipe_def_error
            except ValidationError as pipelex_bundle_validation_error:
                validation_error_msg = report_validation_error(category="plx", validation_error=pipelex_bundle_validation_error)
                msg = f"Could not load PLX bundle from '{plx_file_path}' because of: {validation_error_msg}"
                raise LibraryLoadingError(msg) from pipelex_bundle_validation_error
            blueprints.append(blueprint)

        self.loaded_plx_paths.extend([str(plx_file_path) for plx_file_path in valid_plx_paths])

        # Load all blueprints into the library
        try:
            self.load_from_blueprints(library_id=library_id, blueprints=blueprints)
        except DomainDefinitionError as domain_def_error:
            msg = f"Could not load domains from blueprints: {domain_def_error}"
            raise LibraryLoadingError(msg) from domain_def_error
        except ConceptDefinitionError as concept_def_error:
            msg = f"Could not load concepts from blueprints: {concept_def_error}"
            raise LibraryLoadingError(msg) from concept_def_error
        except PipeDefinitionError as pipe_def_error:
            msg = f"Could not load pipes from blueprints '{pipe_def_error.source}': {pipe_def_error}"
            raise LibraryLoadingError(msg) from pipe_def_error
        except ValidationError as validation_error:
            validation_error_msg = report_validation_error(category="plx", validation_error=validation_error)
            msg = f"Could not load blueprints because of: {validation_error_msg}"
            raise LibraryLoadingError(msg) from validation_error

    def _import_pipelex_modules_directly(self) -> None:
        """Import pipelex modules to register @pipe_func decorated functions.

        This ensures critical pipelex functions are registered regardless of how pipelex
        is installed (wheel, source, relative path, etc.).
        """
        import pipelex.builder  # noqa: PLC0415 - intentional local import

        log.verbose("Registering @pipe_func functions from pipelex.builder")
        functions_count = FuncRegistryUtils.register_pipe_funcs_from_package("pipelex.builder", pipelex.builder)
        log.verbose(f"Registered {functions_count} @pipe_func functions from pipelex.builder")

    def _remove_pipes_from_blueprint(self, blueprint: PipelexBundleBlueprint) -> None:
        library = self.get_library()
        if blueprint.pipe is not None:
            library.pipe_library.remove_pipes_by_codes(pipe_codes=list(blueprint.pipe.keys()))

        # Remove concepts (they may depend on domain)
        if blueprint.concept is not None:
            concept_codes_to_remove = [
                ConceptFactory.make_concept_string_with_domain(domain=blueprint.domain, concept_code=concept_code)
                for concept_code in blueprint.concept
            ]
            library.concept_library.remove_concepts_by_concept_strings(concept_strings=concept_codes_to_remove)

    def _remove_concepts_from_blueprint(self, blueprint: PipelexBundleBlueprint) -> None:
        library = self.get_library()
        if blueprint.concept is not None:
            concept_codes_to_remove = [
                ConceptFactory.make_concept_string_with_domain(domain=blueprint.domain, concept_code=concept_code)
                for concept_code in blueprint.concept
            ]
            library.concept_library.remove_concepts_by_concept_strings(concept_strings=concept_codes_to_remove)

    @override
    def remove_from_blueprint(self, library_id: str, blueprint: PipelexBundleBlueprint) -> None:
        self._remove_pipes_from_blueprint(blueprint=blueprint)
        self._remove_concepts_from_blueprint(blueprint=blueprint)

    @override
    def remove_from_blueprints(self, library_id: str, blueprints: list[PipelexBundleBlueprint]) -> None:
        for blueprint in blueprints:
            self.remove_from_blueprint(library_id=library_id, blueprint=blueprint)

    @override
    def get_loaded_plx_paths(self) -> list[str]:
        return self.loaded_plx_paths
