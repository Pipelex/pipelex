import uuid
from pathlib import Path
from typing import TYPE_CHECKING

from pydantic import ValidationError
from typing_extensions import override

from pipelex import log
from pipelex.core.bundles.pipelex_bundle_blueprint import PipelexBundleBlueprint
from pipelex.core.concepts.concept_factory import ConceptFactory
from pipelex.core.concepts.exceptions import ConceptFactoryError
from pipelex.core.domains.domain import Domain
from pipelex.core.domains.domain_blueprint import DomainBlueprint
from pipelex.core.domains.domain_factory import DomainFactory
from pipelex.core.domains.exceptions import DomainFactoryError
from pipelex.core.exceptions import PipelexBundleBlueprintValidationErrorData, PipelexInterpreterError
from pipelex.core.interpreter import PipelexInterpreter
from pipelex.core.pipe_errors import PipeDefinitionError
from pipelex.core.pipes.pipe_abstract import PipeAbstract
from pipelex.core.pipes.pipe_factory import PipeFactory, PipeFactoryError
from pipelex.core.stuffs.structured_content import StructuredContent
from pipelex.core.validation import report_validation_error
from pipelex.core.validation_error_categorizer import categorize_and_create_error_data
from pipelex.hub import get_current_library_id
from pipelex.libraries.concept.exceptions import ConceptLibraryError
from pipelex.libraries.domain.exceptions import DomainLibraryError
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
from pipelex.libraries.pipe.exceptions import PipeLibraryError
from pipelex.system.registries.class_registry_utils import ClassRegistryUtils
from pipelex.system.registries.func_registry_utils import FuncRegistryUtils

if TYPE_CHECKING:
    from pipelex.core.concepts.concept import Concept
    from pipelex.core.domains.domain import Domain


class LibraryManager(LibraryManagerAbstract):
    def __init__(self):
        # UNTITLED library is the fallback library for all others
        self._libraries: dict[str, Library] = {}
        self.loaded_plx_paths: list[str] = []

    ############################################################
    # Manager lifecycle
    ############################################################
    def generate_library_id(self) -> str:
        return str(uuid.uuid4())

    @override
    def setup(self) -> None:
        self._libraries.clear()

    @override
    def teardown(self, library_id: str | None = None) -> None:
        if library_id:
            if library_id not in self._libraries:
                msg = f"Trying to teardown a library that does not exist: '{library_id}'"
                raise LibraryError(msg)
            library = self._libraries[library_id]
            library.teardown()
            del self._libraries[library_id]
            return

        for library in self._libraries.values():
            library.teardown()
        self._libraries.clear()

    @override
    def reset(self) -> None:
        self.teardown()
        self.setup()

    @override
    def open_library(self, library_id: str | None = None) -> tuple[str, Library]:
        if not library_id:
            library_id = self.generate_library_id()
            self._libraries[library_id] = LibraryFactory.make_empty()
        if library_id not in self._libraries:
            self._libraries[library_id] = LibraryFactory.make_empty()
        return library_id, self._libraries[library_id]

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
    ) -> None:
        # Ensure libraries exist for this library_id
        if library_id not in self._libraries:
            msg = f"Trying to load a library that does not exist: '{library_id}'"
            raise LibraryError(msg)

        if not library_dirs:
            library_dirs = [Path()]

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
            )
            # Only import files that contain @pipe_func decorated functions (uses AST pre-check)
            FuncRegistryUtils.register_funcs_in_folder(
                folder_path=str(library_dir),
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
        library = self.get_library(library_id=library_id)
        all_pipes: list[PipeAbstract] = []

        # Load all domains first
        all_domains: list[Domain] = []
        for blueprint in blueprints:
            try:
                domain = DomainFactory.make_from_blueprint(
                    blueprint=DomainBlueprint(
                        source=blueprint.source,
                        code=blueprint.domain,
                        description=blueprint.description or "",
                        system_prompt=blueprint.system_prompt,
                    ),
                )
            except DomainFactoryError as domain_factory_error:
                msg = f"Could not load domain from blueprint '{blueprint.source}': {domain_factory_error}"
                raise LibraryLoadingError(msg) from domain_factory_error
            except ValidationError as validation_error:
                msg = f"Could not load domain from blueprint '{blueprint.source}': {validation_error}"
                raise LibraryLoadingError(msg) from validation_error
            all_domains.append(domain)
        try:
            library.domain_library.add_domains(domains=all_domains)
        except DomainLibraryError as domain_library_error:
            msg = f"Could not add domains to domain library: {domain_library_error}"
            raise LibraryLoadingError(msg) from domain_library_error

        # Load all concepts second
        all_concepts: list[Concept] = []
        for blueprint in blueprints:
            if blueprint.concept is not None:
                concepts: list[Concept] = []
                for concept_code, concept_blueprint_or_description in blueprint.concept.items():
                    try:
                        concept = ConceptFactory.make_from_blueprint_or_description(
                            domain=blueprint.domain,
                            concept_code=concept_code,
                            concept_codes_from_the_same_domain=list(blueprint.concept.keys()),
                            concept_blueprint_or_description=concept_blueprint_or_description,
                        )
                    except ConceptFactoryError as concept_factory_error:
                        msg = f"Could not load concept from blueprint '{blueprint.source}': {concept_factory_error}"
                        raise LibraryLoadingError(msg) from concept_factory_error
                    except ValidationError as validation_error:
                        msg = f"Could not load concept from blueprint '{blueprint.source}': {validation_error}"
                        raise LibraryLoadingError(msg) from validation_error
                    concepts.append(concept)
                all_concepts.extend(concepts)
        try:
            library.concept_library.add_concepts(concepts=all_concepts)
        except ConceptLibraryError as concept_library_error:
            msg = f"Could not add concepts to concept library: {concept_library_error}"
            raise LibraryLoadingError(msg) from concept_library_error

        # Load all pipes third
        for blueprint in blueprints:
            pipes: list[PipeAbstract] = []
            if blueprint.pipe is not None:
                for pipe_name, pipe_blueprint in blueprint.pipe.items():
                    try:
                        pipe = PipeFactory.make_from_blueprint(
                            domain=blueprint.domain,
                            pipe_code=pipe_name,
                            blueprint=pipe_blueprint,
                            concept_codes_from_the_same_domain=list(blueprint.concept.keys()) if blueprint.concept else None,
                        )
                    except PipeFactoryError as pipe_factory_error:
                        msg = f"Could not load pipe from blueprint '{blueprint.source}': {pipe_factory_error}"
                        raise LibraryLoadingError(msg) from pipe_factory_error
                    except ValidationError as validation_error:
                        msg = f"Could not load pipe from blueprint '{blueprint.source}': {validation_error}"
                        raise LibraryLoadingError(msg) from validation_error
                    pipes.append(pipe)
            all_pipes.extend(pipes)

        try:
            library.pipe_library.add_pipes(pipes=all_pipes)
        except PipeLibraryError as pipe_library_error:
            msg = f"Could not add pipes to pipe library: {pipe_library_error}"
            raise LibraryLoadingError(msg) from pipe_library_error

        try:
            library.validate_library()
        except (ValidationError, ValueError) as validation_error:
            msg = f"Could not validate library for blueprints: {validation_error}"
            raise LibraryLoadingError(msg) from validation_error
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
                blueprint = PipelexInterpreter.make_pipelex_bundle_blueprint(bundle_path=str(plx_file_path))
                blueprint.source = str(plx_file_path)
            except FileNotFoundError as file_not_found_error:
                msg = f"Could not find PLX bundle at '{plx_file_path}'"
                raise LibraryLoadingError(msg) from file_not_found_error
            except PipelexInterpreterError as interpreter_error:
                # Forward categorized validation errors from interpreter
                msg = f"Could not load PLX bundle from '{plx_file_path}' because of: {interpreter_error.message}"
                raise LibraryLoadingError(
                    message=msg,
                    validation_errors=interpreter_error.validation_errors,
                ) from interpreter_error
            except PipeDefinitionError as pipe_def_error:
                msg = f"Could not load PLX bundle from '{plx_file_path}' because of: {pipe_def_error}"
                raise LibraryLoadingError(msg) from pipe_def_error
            blueprints.append(blueprint)

        self.loaded_plx_paths.extend([str(plx_file_path) for plx_file_path in valid_plx_paths])

        # Load all blueprints into the library
        try:
            self.load_from_blueprints(library_id=library_id, blueprints=blueprints)
        except PipeDefinitionError as pipe_def_error:
            msg = f"Could not load pipes from blueprints '{pipe_def_error.source}': {pipe_def_error}"
            raise LibraryLoadingError(msg) from pipe_def_error
        except ValidationError as validation_error:
            # Categorize and forward Pydantic validation errors
            validation_errors: list[PipelexBundleBlueprintValidationErrorData] = []
            for error in validation_error.errors():
                val_error = categorize_and_create_error_data(
                    error=error,
                    blueprint_dict=None,
                    domain=None,
                    source=None,
                )
                validation_errors.append(val_error)

            validation_error_msg = report_validation_error(category="plx", validation_error=validation_error)
            msg = f"Could not load blueprints because of: {validation_error_msg}"
            raise LibraryLoadingError(
                message=msg,
                validation_errors=validation_errors,
            ) from validation_error

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
