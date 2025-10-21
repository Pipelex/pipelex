from pathlib import Path
from typing import ClassVar

from pydantic import ValidationError
from typing_extensions import override

from pipelex import log
from pipelex.core.bundles.pipelex_bundle_blueprint import PipelexBundleBlueprint
from pipelex.core.concepts.concept import Concept
from pipelex.core.concepts.concept_factory import ConceptFactory
from pipelex.core.domains.domain import Domain
from pipelex.core.domains.domain_blueprint import DomainBlueprint
from pipelex.core.domains.domain_factory import DomainFactory
from pipelex.core.interpreter import PipelexInterpreter
from pipelex.core.pipes.pipe_abstract import PipeAbstract
from pipelex.core.pipes.pipe_factory import PipeFactory
from pipelex.core.stuffs.structured_content import StructuredContent
from pipelex.core.validation import report_validation_error
from pipelex.exceptions import (
    ConceptDefinitionError,
    ConceptLibraryError,
    DomainDefinitionError,
    LibraryError,
    LibraryLoadingError,
    PipeDefinitionError,
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
    allowed_root_attributes: ClassVar[list[str]] = [
        "domain",
        "description",
        "system_prompt",
    ]

    def __init__(self):
        # UNTITLED library is the fallback library for all others
        self._libraries: dict[str, Library] = {}

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
    def create_library(self, library_id: str):
        if library_id in self._libraries:
            msg = f"Library '{library_id}' already exists"
            raise LibraryError(msg)
        self._libraries[library_id] = LibraryFactory.make_empty()

    @override
    def open_library(self, library_id: str) -> None:
        """Open a new library with the given library_id.

        The new library will inherit native concepts and base pipes from the BASE library.
        """
        if library_id in self._libraries:
            msg = f"Library '{library_id}' already exists"
            raise LibraryError(msg)

        # Create a new library that inherits from BASE
        self.create_library(library_id=library_id)

        # Load base PLX files (builder pipes) into the new library
        base_plx_paths = [
            Path("pipelex/builder/builder.plx"),
            Path("pipelex/builder/pipe/pipe_design.plx"),
            Path("pipelex/builder/concept/concept.plx"),
        ]
        self._load_plx_files_into_library(library_id=library_id, plx_file_paths=base_plx_paths)

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
        """Get the Library object for a specific library_id."""
        if library_id is None:
            library_id = SpecialLibraryId.UNTITLED
        if library_id not in self._libraries:
            msg = f"Trying to get a library that does not exist: '{library_id}'"
            raise LibraryError(msg)
        return self._libraries[library_id]

    ############################################################
    # Private methods
    ############################################################

    @override
    def load_libraries(
        self,
        library_id: str | None = None,
        library_dirs: list[Path] | None = None,
        library_file_paths: list[Path] | None = None,
    ) -> None:
        if library_id is None:
            library_id = SpecialLibraryId.UNTITLED

        # Ensure libraries exist for this library_id
        if library_id not in self._libraries:
            msg = f"Trying to load a library that does not exist: '{library_id}'"
            raise LibraryError(msg)

        # Collect directories to scan (user project directories)
        user_dirs: set[Path] = set()
        if library_dirs:
            user_dirs.update(library_dirs)
        else:
            user_dirs.add(Path(config_manager.local_root_dir))

        # Get PLX file paths
        valid_plx_paths: list[Path]
        if library_file_paths:
            valid_plx_paths = library_file_paths
        else:
            # Get PLX files from user directories
            user_plx_paths: list[Path] = get_pipelex_plx_files_from_dirs(user_dirs)

            # Get PLX files from pipelex package
            pipelex_plx_paths: list[Path] = get_pipelex_plx_files_from_package()

            # Combine and deduplicate
            all_plx_paths = user_plx_paths + pipelex_plx_paths
            seen_absolute_paths: set[str] = set()
            valid_plx_paths = []
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
        for library_dir in user_dirs:
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
            log.debug(f"Additionally scanning pipelex package filesystem: {pipelex_pkg_dir}")
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
        self._load_plx_files_into_library(library_id=library_id, plx_file_paths=valid_plx_paths)

    ############################################################
    # Private helper methods
    ############################################################

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
            domain = self._load_domain_from_blueprint(blueprint)
            all_domains.append(domain)
        library.domain_library.add_domains(domains=all_domains)

        # Load all concepts second
        all_concepts: list[Concept] = []
        for blueprint in blueprints:
            concepts = self._load_concepts_from_blueprint(blueprint)
            all_concepts.extend(concepts)
        library.concept_library.add_concepts(concepts=all_concepts)

        # Load all pipes third
        for blueprint in blueprints:
            pipes = self._load_pipes_from_blueprint(blueprint)
            all_pipes.extend(pipes)
        library.pipe_library.add_pipes(pipes=all_pipes)

        return all_pipes

    def _load_domain_from_blueprint(self, blueprint: PipelexBundleBlueprint) -> Domain:
        """Load a domain from a blueprint."""
        return DomainFactory.make_from_blueprint(
            blueprint=DomainBlueprint(
                source=blueprint.source,
                code=blueprint.domain,
                description=blueprint.description or "",
                system_prompt=blueprint.system_prompt,
            ),
        )

    def _load_plx_files_into_library(self, library_id: str, plx_file_paths: list[Path]) -> None:
        """Load PLX files into a specific library.

        This method:
        1. Parses blueprints from PLX files
        2. Loads blueprints into the specified library

        Args:
            library_id: The ID of the library to load into
            plx_file_paths: List of PLX file paths to load
        """
        blueprints: list[PipelexBundleBlueprint] = []
        for plx_file_path in plx_file_paths:
            try:
                blueprint = PipelexInterpreter(file_path=plx_file_path).make_pipelex_bundle_blueprint()
            except FileNotFoundError as file_not_found_error:
                msg = f"Could not find PLX blueprint at '{plx_file_path}'"
                raise LibraryLoadingError(msg) from file_not_found_error
            except PipeDefinitionError as pipe_def_error:
                msg = f"Could not load PLX blueprint from '{plx_file_path}': {pipe_def_error}"
                raise LibraryLoadingError(msg) from pipe_def_error
            except ValidationError as validation_error:
                validation_error_msg = report_validation_error(category="plx", validation_error=validation_error)
                msg = f"Could not load PLX blueprint from '{plx_file_path}' because of: {validation_error_msg}"
                raise LibraryLoadingError(msg) from validation_error
            blueprint.source = str(plx_file_path)
            blueprints.append(blueprint)

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
            msg = f"Could not load pipes from blueprints: {pipe_def_error}"
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

    def _load_concepts_from_blueprint(self, blueprint: PipelexBundleBlueprint) -> list[Concept]:
        """Load concepts from a blueprint."""
        if blueprint.concept is None:
            return []

        concepts: list[Concept] = []
        for concept_code, concept_blueprint_or_description in blueprint.concept.items():
            concept = ConceptFactory.make_from_blueprint_or_description(
                domain=blueprint.domain,
                concept_code=concept_code,
                concept_codes_from_the_same_domain=list(blueprint.concept.keys()),
                concept_blueprint_or_description=concept_blueprint_or_description,
            )
            concepts.append(concept)
        return concepts

    def _load_pipes_from_blueprint(self, blueprint: PipelexBundleBlueprint) -> list[PipeAbstract]:
        """Load pipes from a blueprint."""
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
        return pipes

    def remove_from_blueprint(self, library_id: str, blueprint: PipelexBundleBlueprint) -> None:
        library = self.get_library(library_id=library_id)
        if blueprint.pipe is not None:
            library.pipe_library.remove_pipes_by_codes(pipe_codes=list(blueprint.pipe.keys()))

        # Remove concepts (they may depend on domain)
        if blueprint.concept is not None:
            concept_codes_to_remove = [
                ConceptFactory.make_concept_string_with_domain(domain=blueprint.domain, concept_code=concept_code)
                for concept_code in blueprint.concept
            ]
            library.concept_library.remove_concepts_by_concept_strings(concept_strings=concept_codes_to_remove)

        library.domain_library.remove_domain_by_code(domain_code=blueprint.domain)
