from pathlib import Path
from typing import ClassVar

from pydantic import ValidationError
from typing_extensions import override

from pipelex import log
from pipelex.core.bundles.pipelex_bundle_blueprint import PipelexBundleBlueprint
from pipelex.core.concepts.concept import Concept
from pipelex.core.concepts.concept_factory import ConceptFactory
from pipelex.core.concepts.concept_library import ConceptLibrary
from pipelex.core.domains.domain import Domain
from pipelex.core.domains.domain_blueprint import DomainBlueprint
from pipelex.core.domains.domain_factory import DomainFactory
from pipelex.core.domains.domain_library import DomainLibrary
from pipelex.core.interpreter import PipelexInterpreter
from pipelex.core.pipes.pipe_abstract import PipeAbstract
from pipelex.core.pipes.pipe_factory import PipeFactory
from pipelex.core.pipes.pipe_library import PipeLibrary
from pipelex.core.stuffs.structured_content import StructuredContent
from pipelex.core.validation import report_validation_error
from pipelex.exceptions import (
    ConceptDefinitionError,
    ConceptLibraryError,
    ConceptLoadingError,
    DomainDefinitionError,
    DomainLoadingError,
    LibraryError,
    LibraryLoadingError,
    PipeDefinitionError,
    PipeLibraryError,
    PipeLoadingError,
)
from pipelex.libraries.library_manager_abstract import LibraryManagerAbstract
from pipelex.libraries.library_utils import (
    find_plx_files_in_dir,
    get_pipelex_package_dir_for_imports,
    get_pipelex_plx_files_from_package,
)
from pipelex.system.configuration.config_loader import config_manager
from pipelex.system.registries.class_registry_utils import ClassRegistryUtils
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
        "system_prompt_jto_structure",
        "prompt_template_to_structure",
    ]

    def __init__(
        self,
        domain_library: DomainLibrary,
        concept_library: ConceptLibrary,
        pipe_library: PipeLibrary,
    ):
        self.domain_library = domain_library
        self.concept_library = concept_library
        self.pipe_library = pipe_library

    @override
    def validate_libraries(self):
        log.debug("LibraryManager validating libraries")

        self.concept_library.validate_with_libraries()
        self.pipe_library.validate_with_libraries()
        self.domain_library.validate_with_libraries()

    @override
    def setup(self) -> None:
        self.concept_library.setup()

    @override
    def teardown(self) -> None:
        self.pipe_library.teardown()
        self.concept_library.teardown()
        self.domain_library.teardown()

    @override
    def reset(self) -> None:
        self.teardown()
        self.setup()

    def _get_pipelex_plx_files_from_dirs(self, dirs: set[Path]) -> list[Path]:
        """Get all valid Pipelex PLX files from the given directories."""
        all_plx_paths: list[Path] = []
        seen_files: set[str] = set()  # Track by absolute path to avoid duplicates

        for dir_path in dirs:
            if not dir_path.exists():
                log.debug(f"Directory does not exist, skipping: {dir_path}")
                continue

            # Find all .plx files in the directory, excluding problematic directories
            plx_files = find_plx_files_in_dir(
                dir_path=str(dir_path),
                pattern="*.plx",
                is_recursive=True,
            )

            # Filter to only include valid Pipelex files
            for plx_file in plx_files:
                absolute_path = str(plx_file.resolve())

                # Skip if already seen
                if absolute_path in seen_files:
                    log.debug(f"Skipping duplicate PLX file: {plx_file}")
                    continue

                if PipelexInterpreter.is_pipelex_file(plx_file):
                    all_plx_paths.append(plx_file)
                    seen_files.add(absolute_path)
                else:
                    log.debug(f"Skipping non-Pipelex PLX file: {plx_file}")

        return all_plx_paths

    @override
    def load_from_blueprint(self, blueprint: PipelexBundleBlueprint) -> list[PipeAbstract]:
        """Load a blueprint."""
        # Create and load domain
        try:
            domain = self._load_domain_from_blueprint(blueprint)
        except DomainDefinitionError as exc:
            msg = f"Could not load domain from PLX blueprint at '{blueprint.source}', domain code: '{blueprint.domain}': {exc}"
            raise DomainLoadingError(message=msg, domain_code=exc.domain_code, description=exc.description, source=exc.source) from exc
        self.domain_library.add_domain(domain=domain)

        # Create and load concepts
        try:
            concepts = self._load_concepts_from_blueprint(blueprint)
        except ConceptDefinitionError as exc:
            msg = f"Could not load concepts from PLX blueprint at '{blueprint.source}', domain code: '{blueprint.domain}': {exc}"
            raise ConceptLoadingError(
                message=msg, concept_definition_error=exc, concept_code=exc.concept_code, description=exc.description, source=exc.source
            ) from exc
        self.concept_library.add_concepts(concepts=concepts)

        # Create and load pipes
        try:
            pipes = self._load_pipes_from_blueprint(blueprint)
        except PipeDefinitionError as exc:
            msg = f"Could not load pipes from PLX blueprint at '{blueprint.source}', domain code: '{blueprint.domain}': {exc}"
            raise PipeLoadingError(
                message=msg, pipe_definition_error=exc, pipe_code=exc.pipe_code or "", description=exc.description or "", source=exc.source
            ) from exc
        self.pipe_library.add_pipes(pipes=pipes)

        return pipes

    @override
    def remove_from_blueprint(self, blueprint: PipelexBundleBlueprint) -> None:
        if blueprint.pipe is not None:
            self.pipe_library.remove_pipes_by_codes(pipe_codes=list(blueprint.pipe.keys()))

        # Remove concepts (they may depend on domain)
        if blueprint.concept is not None:
            concept_codes_to_remove = [
                ConceptFactory.make_concept_string_with_domain(domain=blueprint.domain, concept_code=concept_code)
                for concept_code in blueprint.concept
            ]
            self.concept_library.remove_concepts_by_codes(concept_codes=concept_codes_to_remove)

        self.domain_library.remove_domain_by_code(domain_code=blueprint.domain)

    def _load_domain_from_blueprint(self, blueprint: PipelexBundleBlueprint) -> Domain:
        return DomainFactory.make_from_blueprint(
            blueprint=DomainBlueprint(
                source=blueprint.source,
                code=blueprint.domain,
                description=blueprint.description or "",
                system_prompt=blueprint.system_prompt,
                system_prompt_to_structure=blueprint.system_prompt_to_structure,
                prompt_template_to_structure=blueprint.prompt_template_to_structure,
            ),
        )

    def _load_concepts_from_blueprint(self, blueprint: PipelexBundleBlueprint) -> list[Concept]:
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

    def _import_pipelex_modules_directly(self) -> None:
        """Import pipelex modules to register @pipe_func decorated functions.

        This ensures critical pipelex functions are registered regardless of how pipelex
        is installed (wheel, source, relative path, etc.).
        """
        import pipelex.builder  # noqa: PLC0415 - intentional local import

        log.verbose("Registering @pipe_func functions from pipelex.builder")
        functions_count = FuncRegistryUtils.register_pipe_funcs_from_package("pipelex.builder", pipelex.builder)
        log.verbose(f"Registered {functions_count} @pipe_func functions from pipelex.builder")

    @override
    def load_libraries(
        self,
        library_dirs: list[Path] | None = None,
        library_file_paths: list[Path] | None = None,
    ) -> None:
        # Collect directories to scan (user project directories)
        user_dirs: set[Path] = set()
        if library_dirs:
            user_dirs.update(library_dirs)
        else:
            user_dirs.add(Path(config_manager.local_root_dir))

        valid_plx_paths: list[Path]
        if library_file_paths:
            valid_plx_paths = library_file_paths
        else:
            # Get PLX files from user directories
            user_plx_paths: list[Path] = self._get_pipelex_plx_files_from_dirs(user_dirs)

            # Get PLX files from pipelex package using importlib.resources
            # This works reliably in all installation modes (wheel, source, relative)
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

        # Import modules to load them into sys.modules (but don't register classes yet)
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
        from pipelex.system.registries.func_registry import func_registry  # noqa: PLC0415 - intentional local import

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
        num_registered = ClassRegistryUtils.auto_register_all_subclasses(base_class=StructuredContent)
        log.debug(f"Auto-registered {num_registered} StructuredContent classes from loaded modules")

        # Parse all blueprints first
        blueprints: list[PipelexBundleBlueprint] = []
        for plx_file_path in valid_plx_paths:
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

        # Load all domains first
        all_domains: list[Domain] = []
        for blueprint in blueprints:
            try:
                domain = self._load_domain_from_blueprint(blueprint)
            except DomainDefinitionError as domain_def_error:
                msg = f"Could not load domain from PLX blueprint at '{blueprint.source}', domain code: '{blueprint.domain}': {domain_def_error}"
                raise LibraryLoadingError(msg) from domain_def_error
            except ValidationError as validation_error:
                validation_error_msg = report_validation_error(category="plx", validation_error=validation_error)
                msg = f"Could not load domain from PLX blueprint at '{blueprint.source}', domain code: '{blueprint.domain}': {validation_error_msg}"
                raise LibraryLoadingError(msg) from validation_error
            all_domains.append(domain)
        self.domain_library.add_domains(domains=all_domains)

        # Load all concepts second
        all_concepts: list[Concept] = []
        for blueprint in blueprints:
            try:
                concepts = self._load_concepts_from_blueprint(blueprint)
            except ConceptDefinitionError as concept_def_error:
                msg = f"Could not load concepts from PLX blueprint at '{blueprint.source}', domain code: '{blueprint.domain}': {concept_def_error}"
                raise LibraryLoadingError(msg) from concept_def_error
            except ValidationError as validation_error:
                validation_error_msg = report_validation_error(category="plx", validation_error=validation_error)
                msg = f"Could not load concepts from PLX blueprint at '{blueprint.source}', domain code: '{blueprint.domain}': {validation_error_msg}"
                raise LibraryLoadingError(msg) from validation_error
            all_concepts.extend(concepts)
        self.concept_library.add_concepts(concepts=all_concepts)

        # Load all pipes third
        all_pipes: list[PipeAbstract] = []
        for blueprint in blueprints:
            try:
                pipes = self._load_pipes_from_blueprint(blueprint)
            except PipeDefinitionError as pipe_def_error:
                msg = f"Could not load pipes from PLX blueprint at '{blueprint.source}', domain code: '{blueprint.domain}': {pipe_def_error}"
                raise LibraryLoadingError(msg) from pipe_def_error
            except ValidationError as validation_error:
                validation_error_msg = report_validation_error(category="plx", validation_error=validation_error)
                msg = f"Could not load pipes from PLX blueprint at '{blueprint.source}', domain code: '{blueprint.domain}': {validation_error_msg}"
                raise LibraryLoadingError(msg) from validation_error
            all_pipes.extend(pipes)
        self.pipe_library.add_pipes(pipes=all_pipes)
